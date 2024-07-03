import yaml
from kubernetes import client, config
from kubernetes.client.rest import ApiException
import os

def load_kube_config():
    config.load_kube_config()
    v1 = client.CoreV1Api()
    apps_v1 = client.AppsV1Api()
    custom_objects_api = client.CustomObjectsApi()
    return v1, apps_v1, custom_objects_api


def get_upstream_services(custom_objects_api, namespace, service_name):
    upstream_services = set()
    try:
        virtual_services = custom_objects_api.list_namespaced_custom_object(
            group="networking.istio.io",
            version="v1alpha3",
            namespace=namespace,
            plural="virtualservices"
        )
        for vs in virtual_services.get("items", []):
            if "spec" in vs and "http" in vs["spec"]:
                for http in vs["spec"]["http"]:
                    for route in http.get("route", []):
                        destination_host = route.get("destination", {}).get("host")
                        if destination_host == service_name:
                            for match in http.get("match", []):
                                source_service = match.get("sourceLabels", {}).get("app")
                                if source_service:
                                    upstream_services.add(source_service)
    except ApiException as e:
        print(f"Error getting upstream services: {e}")
    return list(upstream_services)

def get_downstream_services(custom_objects_api, namespace, service_name):
    downstream_services = set()
    try:
        virtual_services = custom_objects_api.list_namespaced_custom_object(
            group="networking.istio.io",
            version="v1alpha3",
            namespace=namespace,
            plural="virtualservices"
        )
        for vs in virtual_services.get("items", []):
            if "spec" in vs and "http" in vs["spec"]:
                for http in vs["spec"]["http"]:
                    for route in http.get("route", []):
                        source_host = vs["spec"]["hosts"][0]
                        destination_host = route.get("destination", {}).get("host")
                        if source_host == service_name:
                            downstream_services.add(destination_host)
    except ApiException as e:
        print(f"Error getting downstream services: {e}")
    return list(downstream_services)

def get_pods_for_service(v1, namespace, service_name):
    pods = v1.list_namespaced_pod(namespace, label_selector=f'app={service_name}').items
    return [pod.metadata.name for pod in pods]


#가용 자원 얻는 함수
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


def get_node_for_pod(v1, namespace, pod_name):
    pod = v1.read_namespaced_pod(pod_name, namespace)
    return pod.spec.node_name

def get_service_by_deployment(apps_v1, namespace, deployment_name):
    try:
        deployment = apps_v1.read_namespaced_deployment(name=deployment_name, namespace=namespace)
        return deployment.metadata.labels.get('app')
    except ApiException as e:
        print(f"Error getting service by deployment: {e}")
    return None

def get_service_by_version(apps_v1, namespace, version_name):
    try:
        deployments = apps_v1.list_namespaced_deployment(namespace)
        for deployment in deployments.items:
            labels = deployment.metadata.labels
            if labels.get('version') == version_name:
                return labels.get('app')
    except ApiException as e:
        print(f"Error getting service by version: {e}")
    return None

def get_service_connections(custom_objects_api, namespace, service_name):
    upstream_services = get_upstream_services(custom_objects_api, namespace, service_name)
    downstream_services = get_downstream_services(custom_objects_api, namespace, service_name)
    return {
        "upstream": upstream_services,
        "downstream": downstream_services
    }

def get_service_for_deployment(apps_v1, v1, namespace, deployment_name):
    deployment = apps_v1.read_namespaced_deployment(name=deployment_name, namespace=namespace)
    deployment_labels = deployment.spec.selector.match_labels
    label_selector = ",".join([f"{key}={value}" for key, value in deployment_labels.items()])
    services = v1.list_namespaced_service(namespace, label_selector=label_selector).items
    return [service.metadata.name for service in services]

def get_versions_for_service(v1, namespace, service_name):
    pods = v1.list_namespaced_pod(namespace, label_selector=f'app={service_name}').items
    versions = set()
    for pod in pods:
        version = pod.metadata.labels.get('version')
        if version:
            versions.add(version)
    return versions

def get_pods(v1, namespace):
    pods = v1.list_namespaced_pod(namespace).items
    return [pod.metadata.name for pod in pods]

def get_upstream_downstream_services(custom_objects_api, namespace, service_name):
    upstream_services = set()
    downstream_services = set()
    
    try:
        virtual_services = custom_objects_api.list_namespaced_custom_object(
            group="networking.istio.io",
            version="v1alpha3",
            namespace=namespace,
            plural="virtualservices"
        )
        for vs in virtual_services.get("items", []):
            if "spec" in vs and "http" in vs["spec"]:
                for http in vs["spec"]["http"]:
                    for route in http.get("route", []):
                        destination_host = route.get("destination", {}).get("host")
                        if service_name in destination_host:
                            for match in http.get("match", []):
                                source_service = match.get("sourceLabels", {}).get("app")
                                if source_service:
                                    upstream_services.add(source_service)
                        source_host = vs["spec"]["hosts"][0]
                        if service_name in source_host:
                            for route in http.get("route", []):
                                destination_service = route.get("destination", {}).get("host")
                                downstream_services.add(destination_service)
    except client.ApiException as e:
        print(f"Error getting upstream and downstream services: {e}")

    return list(upstream_services), list(downstream_services)

def get_versions_with_nodes(v1, namespace, service_name):
    versions_with_nodes = {}
    pods = v1.list_namespaced_pod(namespace, label_selector=f'app={service_name}').items
    for pod in pods:
        version = pod.metadata.labels.get('version')
        node_name = pod.spec.node_name
        if version and node_name:
            if version not in versions_with_nodes:
                versions_with_nodes[version] = node_name
    return versions_with_nodes



def get_deployment_resources(apps_v1, namespace, deployment_name):
    deployment = apps_v1.read_namespaced_deployment(deployment_name, namespace)
    containers = deployment.spec.template.spec.containers
    total_cpu = 0
    total_memory = 0

    for container in containers:
        if container.resources.requests:
            if container.resources.requests.get("cpu"):
                cpu_request = container.resources.requests["cpu"]
                if cpu_request.endswith('m'):
                    total_cpu += int(cpu_request.rstrip('m'))
                else:
                    total_cpu += int(float(cpu_request) * 1000)  # Convert cores to millicores

            if container.resources.requests.get("memory"):
                memory_request = container.resources.requests["memory"]
                if memory_request.endswith('Mi'):
                    total_memory += int(memory_request.rstrip('Mi'))
                elif memory_request.endswith('Gi'):
                    total_memory += int(float(memory_request.rstrip('Gi')) * 1024)  # Convert Gi to Mi
                elif memory_request.endswith('Ki'):
                    total_memory += int(memory_request.rstrip('Ki')) // 1024  # Convert Ki to Mi

    return {"cpu": total_cpu, "memory": total_memory}

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

def get_labels_from_deployment(apps_v1, namespace, deployment_name):
    deployment = apps_v1.read_namespaced_deployment(name=deployment_name, namespace=namespace)
    return deployment.metadata.labels.get('app'), deployment.metadata.labels.get('version')

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

def create_virtual_service_yaml(service_routes, virtualservice_dir):
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
                        'namespace': 'paper2'
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
      simple: LEAST_CONN
"""

    return yaml.safe_load(yaml_content)


def apply_virtual_service(custom_objects_api, service_routes):
    # Delete existing files in the virtualservice and trafficyaml directories
    vspath = "/home/dnc/master/paper2024/trafficyaml"

    for directory in [vspath]:
        for filename in os.listdir(directory):
            file_path = os.path.join(directory, filename)
            if os.path.isfile(file_path):
                try:
                    os.remove(file_path)
                except FileNotFoundError:
                    # Ignore the error if the file does not exist
                    pass

    virtual_service_yamls = create_virtual_service_yaml(service_routes, vspath)
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

def update_node_selector(apps_v1, replacement_nodes, namespace):
    for service, (version, worker) in replacement_nodes.items():
        deployment_name = service
        try:
            deployment = apps_v1.read_namespaced_deployment(name=deployment_name, namespace=namespace)
        except client.exceptions.ApiException as e:
            print(f"Failed to get deployment {deployment_name}: {e}")
            continue

        try:
            node_affinity = deployment.spec.template.spec.affinity.node_affinity
            current_workers = set()

            if node_affinity:
                node_selector_terms = node_affinity.required_during_scheduling_ignored_during_execution.node_selector_terms
                for term in node_selector_terms:
                    for expression in term.match_expressions:
                        if expression.key == "kubernetes.io/hostname":
                            current_workers.update(expression.values)

            if worker in current_workers:
                print(f"Node selector for deployment {deployment_name} is already set to {worker}. Skipping update.")
                continue

            if not node_affinity:
                deployment.spec.template.spec.affinity = client.V1Affinity(
                    node_affinity=client.V1NodeAffinity(
                        required_during_scheduling_ignored_during_execution=client.V1NodeSelector(
                            node_selector_terms=[
                                client.V1NodeSelectorTerm(
                                    match_expressions=[
                                        client.V1NodeSelectorRequirement(
                                            key="kubernetes.io/hostname",
                                            operator="In",
                                            values=[worker]
                                        )
                                    ]
                                )
                            ]
                        )
                    )
                )
            else:
                node_selector_terms = node_affinity.required_during_scheduling_ignored_during_execution.node_selector_terms
                worker_added = False
                for term in node_selector_terms:
                    for expression in term.match_expressions:
                        if expression.key == "kubernetes.io/hostname":
                            if worker not in expression.values:
                                expression.values.append(worker)
                            worker_added = True
                            break
                    if worker_added:
                        break
                if not worker_added:
                    node_selector_terms.append(
                        client.V1NodeSelectorTerm(
                            match_expressions=[
                                client.V1NodeSelectorRequirement(
                                    key="kubernetes.io/hostname",
                                    operator="In",
                                    values=[worker]
                                )
                            ]
                        )
                    )
        except KeyError as e:
            print(f"KeyError: {e} in deployment {deployment_name}")
            continue

        try:
            apps_v1.patch_namespaced_deployment(
                name=deployment_name,
                namespace=namespace,
                body=deployment
            )
            #print(f"Updated nodeSelector for deployment {deployment_name} to {worker}")
        except client.exceptions.ApiException as e:
            print(f"Failed to update deployment {deployment_name}: {e}")

def find_connected_deployments(apps_v1, v1, namespace, deployment_name):
    app_label, version_label = get_labels_from_deployment(apps_v1, namespace, deployment_name)
    connected_deployments = {}

    if not app_label:
        print(f"App label not found for deployment: {deployment_name}")
        return connected_deployments

    service_name = get_service_for_deployment(apps_v1, v1, namespace, deployment_name)

    services = v1.list_namespaced_service(namespace).items
    connected_services = [svc.metadata.name for svc in services if svc.metadata.name != service_name]

    for connected_service in connected_services:
        connected_deployments[connected_service] = get_versions_for_service(v1, namespace, connected_service)

    return connected_deployments



