from kube_client import KubernetesClient
from istio_metrics import IstioMetrics
from DAG import DAG
from collections import defaultdict
import copy


def select_edges_to_remove_candidate(dag, threshold):
    all_paths_with_durations = dag.find_all_paths_with_durations()
    filtered_sorted_paths_with_durations = dag.filter_and_sort_paths(all_paths_with_durations)
    below_threshold, above_threshold = dag.separate_paths_by_threshold(filtered_sorted_paths_with_durations, threshold)
    
    print("\nPaths Below Threshold:")
    for path, total_duration in below_threshold:
        print("Path:", " -> ".join(path), "Total Duration:", total_duration)
    
    print("\nPaths Above Threshold:")
    for path, total_duration in above_threshold:
        print("Path:", " -> ".join(path), "Total Duration:", total_duration)
    
    edges_to_remove_candidate = dag.get_edges_above_threshold(above_threshold)

    print("\nEdges to Remove Candidate:")
    for edge in edges_to_remove_candidate:
        print(f"Edge: {edge}")
    print()

    return edges_to_remove_candidate, above_threshold, below_threshold


def edge_difference(paths_above, paths_below, edges_to_remove_candidate):
    difference = defaultdict(int)
    for path, _ in paths_above:
        for i in range(len(path) - 1):
            edge = (path[i], path[i + 1])
            if edge in edges_to_remove_candidate:
                difference[edge] -= 1  # Above threshold: decrement
    for path, _ in paths_below:
        for i in range(len(path) - 1):
            edge = (path[i], path[i + 1])
            if edge in edges_to_remove_candidate:
                difference[edge] += 1  # Below threshold: increment
    return sorted(difference.items(), key=lambda x: x[1])


def select_edges_to_remove(dag, edges_to_remove_candidate, paths_above_threshold, below_threshold):
    def edge_difference(paths_above, paths_below, edges_to_remove_candidate):
        difference = defaultdict(int)
        for path, _ in paths_above:
            for i in range(len(path) - 1):
                edge = (path[i], path[i + 1])
                if edge in edges_to_remove_candidate:
                    difference[edge] -= 1  # Above threshold: decrement
        for path, _ in paths_below:
            for i in range(len(path) - 1):
                edge = (path[i], path[i + 1])
                if edge in edges_to_remove_candidate:
                    difference[edge] += 1  # Below threshold: increment
        return sorted(difference.items(), key=lambda x: x[1])

    def backtrack(current_edges, start_index):
        nonlocal best_edges, min_underload_replicas, found_optimal_solution, final_underload_replicas
        
        is_all_removed, number_of_underload_replicas, underload_replicas = dag.check_paths_removed(current_edges, paths_above_threshold)
        
        if is_all_removed:
            if number_of_underload_replicas < min_underload_replicas:
                min_underload_replicas = number_of_underload_replicas
                best_edges = copy.deepcopy(current_edges)
                final_underload_replicas = copy.deepcopy(underload_replicas)
                if number_of_underload_replicas < 4:
                    found_optimal_solution = True
                    return
        
        if found_optimal_solution:
            return
        
        for i in range(start_index, len(sorted_edges_to_remove_candidate)):
            edge, _ = sorted_edges_to_remove_candidate[i]
            current_edges.append(edge)
            backtrack(current_edges, i + 1)
            current_edges.pop()
    
    sorted_edges_to_remove_candidate = edge_difference(paths_above_threshold, below_threshold, edges_to_remove_candidate)

    print("\nSorted Edges to Remove Candidate (ascending order):")
    for edge, count in sorted_edges_to_remove_candidate:
        print(f"Edge: {edge}, Count: {count}")

    best_edges = []
    min_underload_replicas = float('inf')
    found_optimal_solution = False
    final_underload_replicas = []
    backtrack([], 0)
    dag.graph.remove_edges_from(best_edges)

    print("\nFinal Edges to Remove:")
    for edge in best_edges:
        print(f"Edge: {edge}")
    print('min_underload_replicas', min_underload_replicas)
    print('Underloaded replicas:', final_underload_replicas)

    return best_edges


def distribute_traffic_and_create_service_routes(k8s_client, dag, edges_to_remove):
    service_versions = k8s_client.get_service_versions()
    downstream_versions = {}
    for source, destination in edges_to_remove:
        if source not in downstream_versions:
            downstream_versions[source] = set()
        destination_name, destination_version = k8s_client.get_labels_from_deployment(destination)
        downstream_versions[source].add(destination_version)

    # Create service routes based on edges_to_remove
    service_routes = []
    for source, destination in edges_to_remove:
        source_name, source_version = k8s_client.get_labels_from_deployment(source)
        destination_name, destination_version = k8s_client.get_labels_from_deployment(destination)
        service_routes.append((source_name, source_version, destination_name, destination_version, 0))
        
        # Get downstream connections for the source
        downstream_edges = list(dag.graph.successors(source))
        remaining_destinations = [dest for dest in downstream_edges if (source, dest) not in edges_to_remove]

        if remaining_destinations:
            equal_weight = 100 // len(remaining_destinations)
            for dest in remaining_destinations:
                dest_name, dest_version = k8s_client.get_labels_from_deployment(dest)
                service_routes.append((source_name, source_version, dest_name, dest_version, equal_weight))
        else:
            for dest in downstream_edges:
                dest_name, dest_version = k8s_client.get_labels_from_deployment(dest)
                service_routes.append((source_name, source_version, dest_name, dest_version, 0))
    
    return service_routes, service_versions, downstream_versions


def main():
    namespace = "paper2"
    prometheus_url = "http://10.107.248.100:8080"
    threshold = 600  # Example threshold value, you can set this to your desired value

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
    dag.draw_dag("/home/dnc/master/paper2024/code/python/DAG.png")
    original_dag = copy.deepcopy(dag)

    print("\nInitial Node Connections:")
    dag.print_node_connections()

    # Remove paths and get edges to remove
    edges_to_remove_candidate, above_threshold, below_threshold = select_edges_to_remove_candidate(dag, threshold)
    edges_to_remove = select_edges_to_remove(dag, edges_to_remove_candidate, above_threshold, below_threshold)
    
    # Distribute traffic and create service routes
    service_routes, service_versions, downstream_versions = distribute_traffic_and_create_service_routes(k8s_client, dag, edges_to_remove)

    dag.print_node_connections()
    # Apply VirtualService and DestinationRule
    k8s_client.apply_virtual_service(service_routes, downstream_versions)
    k8s_client.apply_destination_rules(service_versions)

if __name__ == "__main__":
    main()
