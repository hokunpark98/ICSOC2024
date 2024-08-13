import yaml
from kubernetes import client, config
from kubernetes.client.rest import ApiException
import os
from collections import defaultdict


def load_kube_config():
    config.load_kube_config()
    v1 = client.CoreV1Api()
    apps_v1 = client.AppsV1Api()
    custom_objects_api = client.CustomObjectsApi()
    return v1, apps_v1, custom_objects_api


def get_service_versions(v1, namespace):
    services = v1.list_namespaced_service(namespace).items
    versions = {}

    for service in services:
        service_name = service.metadata.name
        versions[service_name] = set()

        pods = v1.list_namespaced_pod(namespace, label_selector=f'app={service_name}').items
        for pod in pods:
            version = pod.metadata.labels.get('version')
            if version:
                versions[service_name].add(version)

    return versions

def get_versions_on_nodes(v1, namespace):
    pods = v1.list_namespaced_pod(namespace).items
    node_map = {}

    for pod in pods:
        version = pod.metadata.labels.get('version')
        node_name = pod.spec.node_name

        if version:
            if version not in node_map:
                node_map[version] = []
            node_map[version].append(node_name)

    return node_map

'''
서비스들 간의 관계를 파악할 때 사용
'''
def get_services_relation(prom, namespace):
    # Istio telemetry data query (entire period)
    query = f'sum(istio_requests_total{{reporter="source", destination_service_namespace="{namespace}"}}) by (source_app, destination_app)'
    results = prom.custom_query(query)

    # Upstream and Downstream mapping dictionaries initialization
    upstream_map = defaultdict(list)
    downstream_map = defaultdict(list)

    for result in results:
        source = result['metric']['source_app']
        destination = result['metric']['destination_app']
        if source != 'unknown' and destination != 'unknown':
            downstream_map[source].append(destination)
            upstream_map[destination].append(source)

    # Final result dictionary initialization
    services_dict = defaultdict(lambda: {"upstream": [], "downstream": []})

    # Setting Upstream and Downstream relationships
    for svc, upstreams in upstream_map.items():
        if svc != 'unknown':
            services_dict[svc]["upstream"].extend(upstreams)

    for svc, downstreams in downstream_map.items():
        if svc != 'unknown':
            services_dict[svc]["downstream"].extend(downstreams)

    return services_dict


'''
처음 배치할 떄 가용자원 검색하는 거
'''
def get_allocatable_resources(v1, node_name):
    # 노드의 현재 상태를 읽어옵니다.
    node = v1.read_node(node_name)
    capacity = node.status.capacity

    # 노드에 할당된 리소스를 계산합니다.
    pods = v1.list_pod_for_all_namespaces(field_selector=f"spec.nodeName={node_name}")
    total_cpu_requests = 0
    total_memory_requests = 0

    for pod in pods.items:
        for container in pod.spec.containers:
            if container.resources.requests:
                total_cpu_requests += convert_cpu_to_millicores(container.resources.requests.get('cpu', '0'))
                total_memory_requests += convert_memory_to_mebibytes(container.resources.requests.get('memory', '0Mi'))

    # 노드의 capacity에서 요청된 리소스를 뺀 값을 계산합니다.
    available_cpu = int(convert_cpu_to_millicores(capacity["cpu"]) - total_cpu_requests)
    available_memory = int(convert_memory_to_mebibytes(capacity["memory"]) - total_memory_requests)

    return {
        "available_cpu": available_cpu,
        "available_memory": available_memory
    }

def convert_cpu_to_millicores(cpu):
    if cpu.endswith('m'):
        return int(cpu[:-1])
    return int(float(cpu) * 1000)

def convert_memory_to_mebibytes(memory):
    if memory.endswith('Ki'):
        return int(memory[:-2]) / 1024
    if memory.endswith('Mi'):
        return int(memory[:-2])
    if memory.endswith('Gi'):
        return int(memory[:-2]) * 1024
    return int(memory) / (1024 * 1024)





'''
아래는 yaml 업데이트 하는 거 vs랑 dr
'''

def apply_yaml(custom_objects_api, yaml_content):
    yaml_string = yaml.dump(yaml_content, default_flow_style=False)
    yaml_object = yaml.safe_load(yaml_string)
    group, version = yaml_object["apiVersion"].split('/')
    plural = yaml_object["kind"].lower() + "s"
    name = yaml_object["metadata"]["name"]
    namespace = yaml_object.get("metadata", {}).get("namespace", "default")

    try:
        custom_objects_api.create_namespaced_custom_object(
            group=group,
            version=version,
            namespace=namespace,
            plural=plural,
            body=yaml_object
        )
    except ApiException as e:
        if e.status == 409:
            existing_object = custom_objects_api.get_namespaced_custom_object(
                group=group,
                version=version,
                namespace=namespace,
                plural=plural,
                name=name
            )
            yaml_object["metadata"]["resourceVersion"] = existing_object["metadata"]["resourceVersion"]
            custom_objects_api.replace_namespaced_custom_object(
                group=group,
                version=version,
                namespace=namespace,
                plural=plural,
                name=name,
                body=yaml_object
            )
        else:
            raise

def create_virtual_service_yaml(service_routes, virtualservice_dir, namespace):
    grouped_routes = {}
    for route in service_routes:
        source, source_version, destination, destination_version, weight = route
        key = (source, source_version)
        if key not in grouped_routes:
            grouped_routes[key] = {}
        if destination not in grouped_routes[key]:
            grouped_routes[key][destination] = {}
        grouped_routes[key][destination][destination_version] = weight

    yamls = {}
    for (source, source_version), destinations in grouped_routes.items():
        for destination, version_weights in destinations.items():
            file_path = os.path.join(virtualservice_dir, f"{source}-to-{destination}-vs.yaml")

            # Create new YAML content
            routes_yaml = []
            for version, weight in version_weights.items():
                routes_yaml.append({
                    'destination': {
                        'host': destination,
                        'subset': version
                    },
                    'weight': weight
                })

            match_entry = {
                'match': [
                    {
                        'sourceLabels': {
                            'app': source,
                            'version': source_version
                        }
                    }
                ],
                'route': routes_yaml
            }

            if os.path.exists(file_path):
                with open(file_path, 'r') as file:
                    existing_content = yaml.safe_load(file)

                # Check if the same source version exists
                updated = False
                for http_entry in existing_content['spec']['http']:
                    match = http_entry['match'][0]
                    if match['sourceLabels']['version'] == source_version:
                        http_entry['route'] = routes_yaml
                        updated = True
                        break

                if not updated:
                    existing_content['spec']['http'].append(match_entry)

                yaml_content = existing_content
            else:
                yaml_content = {
                    'apiVersion': 'networking.istio.io/v1alpha3',
                    'kind': 'VirtualService',
                    'metadata': {
                        'name': f'{source}-to-{destination}-vs',
                        'namespace': namespace
                    },
                    'spec': {
                        'hosts': [destination],
                        'http': [match_entry]
                    }
                }

            yamls[(source, source_version)] = yaml_content

            # Save to file
            with open(file_path, 'w') as file:
                yaml.dump(yaml_content, file, default_flow_style=False)
            #print(f"Updated/Created VirtualService YAML at {file_path}")

    return yamls

def create_destination_rule_yaml(service, versions, namespace):
    subsets = ""
    for version in versions:
        subsets += f"""
  - name: {version}
    labels:
      version: {version}"""
    
    yaml_content = f"""
apiVersion: networking.istio.io/v1alpha3
kind: DestinationRule
metadata:
  name: {service}-dr
  namespace: {namespace}
spec:
  host: {service}
  subsets:{subsets}
  trafficPolicy:
    loadBalancer:
      simple: LEAST_REQUEST
"""

    return yaml.safe_load(yaml_content)


def apply_virtual_service(custom_objects_api, service_routes, namespace, vspath):
    # Delete existing files in the virtualservice and trafficyaml directories

    for directory in [vspath]:
        for filename in os.listdir(directory):
            file_path = os.path.join(directory, filename)
            if os.path.isfile(file_path):
                try:
                    os.remove(file_path)
                except FileNotFoundError:
                    # Ignore the error if the file does not exist
                    pass

    virtual_service_yamls = create_virtual_service_yaml(service_routes, vspath, namespace)
    for vs_yaml in virtual_service_yamls.values():
        apply_yaml(custom_objects_api, vs_yaml)
        # yaml 저장하기
        file_path = os.path.join(vspath, f"{vs_yaml['metadata']['name']}.yaml")
        with open(file_path, 'w') as file:
            yaml.dump(vs_yaml, file, default_flow_style=False)

def apply_destination_rules(namespace, custom_objects_api, service_versions):
    vspath = "/home/dnc/master/paper2024/trafficyaml"

    for service, versions in service_versions.items():
        destination_rule_yaml = create_destination_rule_yaml(service, versions, namespace)
        apply_yaml(custom_objects_api, destination_rule_yaml)
        # yaml 저장하기
        file_path = os.path.join(vspath, f"{service}-dr.yaml")
        with open(file_path, 'w') as file:
            yaml.dump(destination_rule_yaml, file, default_flow_style=False)





