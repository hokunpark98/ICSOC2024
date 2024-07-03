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


def get_node_resources(v1, node_name):
    node = v1.read_node(node_name)
    allocatable = node.status.allocatable
    return {
        "cpu": allocatable["cpu"],
        "memory": allocatable["memory"]
    }

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


def apply_virtual_service(custom_objects_api, service_routes, vspath):
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

    virtual_service_yamls = create_virtual_service_yaml(service_routes, vspath)
    for vs_yaml in virtual_service_yamls.values():
        apply_yaml(custom_objects_api, vs_yaml)
        # Save to trafficyaml directory
        file_path = os.path.join(vspath, f"{vs_yaml['metadata']['name']}.yaml")
        with open(file_path, 'w') as file:
            yaml.dump(vs_yaml, file, default_flow_style=False)

def apply_destination_rules(namespace, custom_objects_api, service_versions, vspath):
    for service, versions in service_versions.items():
        destination_rule_yaml = create_destination_rule_yaml(service, versions, namespace)
        apply_yaml(custom_objects_api, destination_rule_yaml)
        # Save to trafficyaml directory
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



'''
def reset_weights(apps_v1, custom_objects_api, original_edges, namespace):
    for edge in original_edges:
        source, destination, weight = edge
        source_name, source_version = get_labels_from_deployment(apps_v1, namespace, source)
        destination_name, destination_version = get_labels_from_deployment(apps_v1, namespace, destination)
        virtual_service_yaml = create_virtual_service_yaml([(source_name, source_version, destination_name, destination_version, weight)], virtualservice_dir)
        apply_yaml(custom_objects_api, virtual_service_yaml[(source_name, destination_name)])

def distribute_remaining_weights(source, destination_weights):
    remaining_destinations = [dest for dest, weight in destination_weights.items() if weight != 0]
    if not remaining_destinations:
        return

    equal_weight = 100 // len(remaining_destinations)
    for dest in remaining_destinations:
        destination_weights[dest] = equal_weight
'''


'''

def distribute_traffic_and_create_service_routes(current_map, v1, namespace):
    service_versions = get_service_versions(v1, namespace)
    service_routes = []


    for service_version in service_versions:
        upstream_nodes = get_versions_for_service(v1, namespace, service_version)
        downstream_nodes = set()
        for upsteam_node in upstream_nodes:
            for downstream_node in current_map[upsteam_node]['downstream']:
                downstream_nodes.add(downstream_node)
        downstream_nodes = list(downstream_nodes)

        if downstream_nodes == []:
            break
        # Create a directed graph for max-flow calculation
        G = nx.DiGraph()

        for source in upstream_nodes:
            for downstream in current_map[source]['downstream']:
                G.add_edge(source, downstream, capacity=100)

        # Calculate the traffic requirements
        downstream_traffic = calculate_required_traffic(len(upstream_nodes), downstream_nodes)
        upstream_traffic = {u_node: 100 for u_node in upstream_nodes}
        #print('downstream_traffic', downstream_traffic)
        #print('upstream_traffic', upstream_traffic)
        flow_dict = distribute_traffic(current_map, downstream_traffic, upstream_traffic)

        for u_node in flow_dict:
            if u_node in upstream_traffic:
                for d_node, flow in flow_dict[u_node].items():
                    if d_node != 'sink' and flow > 0:
                        source_service, source_version = None, None
                        dest_service, dest_version = None, None

                        for service, versions in service_versions.items():
                            if u_node in versions:
                                source_service = service
                                source_version = u_node
                            if d_node in versions:
                                dest_service = service
                                dest_version = d_node

                        if source_service and dest_service:
                            service_routes.append((source_service, source_version, dest_service, dest_version, flow))

    print('service_routes', service_routes)
    return service_routes, service_versions

이 부분을 ILP로 바꾸고싶어.

목적은 current_map을 참고하여 source-service와 destination-service로의 트래픽 전송 시 total node latency를 줄이는 거야. 
각 upstream-service에 속한 노드는 100씩 보내고 downstream은 up/down만큼 수신해야해. 그리고, 
node-to-node latency는 
```
def get_probe_icmp_durations(prom):
    query = 'probe_icmp_duration_seconds{phase="rtt"}'
    result = prom.custom_query(query)
    return parse_probe_icmp_durations(result)

def parse_probe_icmp_durations(result):
    durations = {}
    for item in result:
        instance = item['metric']['instance']
        job = item['metric']['job']
        value_seconds = float(item['value'][1])
        value_ms = round(value_seconds * 1000, 1)
        if job not in durations:
            durations[job] = {}
        durations[job][instance] = value_ms
    return durations

```
이걸 사용하면 되고, 

'''