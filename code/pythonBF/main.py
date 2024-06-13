import copy
import yaml
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from kube_client import KubernetesClient
from istio_metrics import IstioMetrics
from DAG import DAG

def print_node_connections(graph):
    for node in graph.nodes:
        upstream = list(graph.predecessors(node))
        downstream = list(graph.successors(node))
        print(f"Node: {node}, Upstream: {upstream}, Downstream: {downstream}")

def create_virtual_service_yaml(service_routes):
    grouped_routes = {}
    for route in service_routes:
        source, source_version, destination, destination_version, weight = route
        key = (source, destination)
        if key not in grouped_routes:
            grouped_routes[key] = {}
        match_key = (source_version, destination)
        if match_key not in grouped_routes[key]:
            grouped_routes[key][match_key] = []
        grouped_routes[key][match_key].append((destination_version, weight))
    
    yamls = {}
    for (source, destination), matches in grouped_routes.items():
        matches_yaml = ""
        for (source_version, dest), routes in matches.items():
            routes_yaml = ""
            for dest_version, weight in routes:
                routes_yaml += f"""
    - destination:
        host: {dest}
        subset: {dest_version}
      weight: {weight}"""
            matches_yaml += f"""
  - match:
    - sourceLabels:
        app: {source}
        version: {source_version}
    route:{routes_yaml}"""
        
        yaml_content = f"""
apiVersion: networking.istio.io/v1alpha3
kind: VirtualService
metadata:
  name: {source}-to-{destination}-vs
  namespace: paper2
spec:
  hosts:
  - {destination}
  http:{matches_yaml}
"""
        yamls[(source, destination)] = yaml_content
    
    return yamls

def create_destination_rule_yaml(service, versions):
    subsets = ""
    for version in versions:
        subsets += f"""
  - name: {version}
    labels:
      version: {version}"""
    
    return f"""
apiVersion: networking.istio.io/v1alpha3
kind: DestinationRule
metadata:
  name: {service}-dr
  namespace: paper2
spec:
  host: {service}
  subsets:{subsets}
  trafficPolicy:
    loadBalancer:
      simple: LEAST_CONN
"""

def apply_yaml(yaml_content):
    k8s_client = client.CustomObjectsApi()
    yaml_object = yaml.safe_load(yaml_content)
    group, version = yaml_object["apiVersion"].split('/')
    plural = yaml_object["kind"].lower() + "s"
    name = yaml_object["metadata"]["name"]
    namespace = yaml_object.get("metadata", {}).get("namespace", "default")
    
    try:
        k8s_client.create_namespaced_custom_object(
            group=group,
            version=version,
            namespace=namespace,
            plural=plural,
            body=yaml_object
        )
    except ApiException as e:
        if e.status == 409:
            # If the object already exists, fetch the existing object
            existing_object = k8s_client.get_namespaced_custom_object(
                group=group,
                version=version,
                namespace=namespace,
                plural=plural,
                name=name
            )
            # Set the resourceVersion from the existing object
            yaml_object["metadata"]["resourceVersion"] = existing_object["metadata"]["resourceVersion"]
            # Replace the existing object with the new one
            k8s_client.replace_namespaced_custom_object(
                group=group,
                version=version,
                namespace=namespace,
                plural=plural,
                name=name,
                body=yaml_object
            )
        else:
            raise

def get_service_versions(namespace):
    config.load_kube_config()
    v1 = client.CoreV1Api()
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

def get_labels_from_deployment(namespace, deployment_name):
    config.load_kube_config()
    apps_v1 = client.AppsV1Api()
    deployment = apps_v1.read_namespaced_deployment(name=deployment_name, namespace=namespace)
    return deployment.metadata.labels.get('app'), deployment.metadata.labels.get('version')

def reset_weights(original_edges, namespace):
    for edge in original_edges:
        source, destination, weight = edge
        source_name, source_version = get_labels_from_deployment(namespace, source)
        destination_name, destination_version = get_labels_from_deployment(namespace, destination)
        virtual_service_yaml = create_virtual_service_yaml([(source_name, source_version, destination_name, destination_version, weight)])
        print(f"Resetting weight for {source} to {destination} to {weight}")
        apply_yaml(virtual_service_yaml[(source_name, destination_name)])

def distribute_remaining_weights(source, destination_weights):
    remaining_destinations = [dest for dest, weight in destination_weights.items() if weight != 0]
    if not remaining_destinations:
        return

    equal_weight = 100 // len(remaining_destinations)
    for dest in remaining_destinations:
        destination_weights[dest] = equal_weight

def main():
    namespace = "paper2"
    prometheus_url = "http://10.109.129.191:8080"
    threshold = 850  # Example threshold value, you can set this to your desired value

    # Kubernetes 클라이언트 설정 및 파드 가져오기
    k8s_client = KubernetesClient(namespace)
    pods = k8s_client.get_pods()
    deployment = list()
    
    # Istio 메트릭 데이터 수집
    istio_metrics = IstioMetrics(prometheus_url)
    edges = istio_metrics.get_request_durations(namespace)

    # 간선에서 파드 이름을 배포 이름으로 변환
    edges_with_deployments = []
    for source, destination, duration in edges:
        deployment.append(source)
        deployment.append(destination)
        source_deployment = source
        destination_deployment = destination
        
        if source_deployment != 'unknown' and destination_deployment != 'unknown':
            edges_with_deployments.append((source_deployment, destination_deployment, duration))

    # 중복을 제거한 배포 이름 목록 생성
    unique_deployments = set(deployment)
    
    # DAG 생성 및 시각화
    dag = DAG()
    dag.create_dag(unique_deployments, edges_with_deployments)
    
    original = copy.deepcopy(dag)

    print("\nInitial Node Connections:")
    print_node_connections(dag.graph)

    all_paths_with_durations = dag.find_all_paths_with_durations()
    filtered_sorted_paths_with_durations = dag.filter_and_sort_paths(all_paths_with_durations)
    below_threshold, above_threshold = dag.separate_paths_by_threshold(filtered_sorted_paths_with_durations, threshold)
    
    print("\nPaths Below Threshold:")
    for path, total_duration in below_threshold:
        print("Path:", " -> ".join(path), "Total Duration:", total_duration)
    
    print("\nPaths Above Threshold:")
    for path, total_duration in above_threshold:
        print("Path:", " -> ".join(path), "Total Duration:", total_duration)
    
    # 각 간선의 사용 횟수를 계산하고 평가
    edge_evaluation = dag.evaluate_edges(below_threshold, above_threshold)
    edges_to_remove = []
    for edge, difference in edge_evaluation.items():
        if difference < 0:
            edges_to_remove.append(edge)

    print("\nEdges to Remove:")
    for edge in edges_to_remove:
        print(f"Edge: {edge}")
    print()
    # 재배치할 노드
    nodes_to_relocate = []
    dag.check_isolated_nodes(dag.graph, edges_to_remove)
    for node in dag.graph.nodes:
        upstream = list(dag.graph.predecessors(node))
        upstream_original = list(original.graph.predecessors(node))
        downstream = list(dag.graph.successors(node))
        downstream_original = list(original.graph.successors(node))
        print(f"Node: {node}\n Upstream: {upstream}, Downstream: {downstream}\n UpstreamORI: {upstream_original}, DownstreamORI: {downstream_original}\n")

        if (upstream_original != [] and upstream == []) or (downstream_original != [] and downstream == []):
            print("Remove node", node)
            nodes_to_relocate.append(node)
    
    
    print("\nNodes to be Relocated:")
    for node in nodes_to_relocate:
        print(f"Node: {node}")

    
    # 0으로 할 간선들 - 재배치 노드 제외하고
    edges_to_remove = [edge for edge in edges_to_remove if edge[0] not in nodes_to_relocate and edge[1] not in nodes_to_relocate]

    print("\nFiltered Edges to Remove:")
    for edge in edges_to_remove:
        print(f"Edge: {edge}")

    # Store original edges with their weights
    original_edges = [(edge[0], edge[1], 100) for edge in edges_to_remove]  # Assuming original weight was 100
    
    # Create and apply Istio YAML with all routes
    service_routes = []
    for edge in edges_to_remove:
        source, destination = edge
        source_name, source_version = get_labels_from_deployment(namespace, source)
        destination_name, destination_version = get_labels_from_deployment(namespace, destination)
        service_routes.append((source_name, source_version, destination_name, destination_version, 0))
        
        # Get downstream connections for the source
        downstream_edges = list(dag.graph.successors(source))
        destination_weights = {dest: 100 for dest in downstream_edges}
        destination_weights[destination] = 0
        
        # Distribute remaining weights
        distribute_remaining_weights(source, destination_weights)
        
        # Add new weights for remaining destinations to the routes list
        for dest, weight in destination_weights.items():
            if dest != destination:
                dest_name, dest_version = get_labels_from_deployment(namespace, dest)
                service_routes.append((source_name, source_version, dest_name, dest_version, weight))
    
    all_paths_with_durations = dag.find_all_paths_with_durations()
    print("DADD")
    for path, total_duration in all_paths_with_durations:
        print("Path:", " -> ".join(path), "Total Duration:", total_duration) 


    virtual_service_yamls = create_virtual_service_yaml(service_routes)
    for vs_yaml in virtual_service_yamls.values():
        print(vs_yaml)
        apply_yaml(vs_yaml)

    # Apply DestinationRule for all services involved
    service_versions = get_service_versions(namespace)
    for service, versions in service_versions.items():
        destination_rule_yaml = create_destination_rule_yaml(service, versions)
        print(destination_rule_yaml)
        #apply_yaml(destination_rule_yaml)
    
if __name__ == "__main__":
    main()
