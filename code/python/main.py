from kube_client import KubernetesClient
from istio_metrics import IstioMetrics
from DAG import DAG
from graph_map import GraphMap
from collections import defaultdict


def distribute_traffic_and_create_service_routes(k8s_client, dag, edges_to_remove):
    service_versions = k8s_client.get_service_versions()
    downstream_versions = {}
    for source, destination in edges_to_remove:
        if source not in downstream_versions:
            downstream_versions[source] = set()
        destination_name, destination_version = k8s_client.get_labels_from_deployment(destination)
        downstream_versions[source].add(destination_version)

    service_routes = []
    for source, destination in edges_to_remove:
        source_name, source_version = k8s_client.get_labels_from_deployment(source)
        destination_name, destination_version = k8s_client.get_labels_from_deployment(destination)
        service_routes.append((source_name, source_version, destination_name, destination_version, 0))

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
    
    # 간선 사용 빈도를 계산하는 대신, 유니크한 간선 구하기
    unique_edges = set()
    for path, _ in above_threshold:
        for i in range(len(path) - 1):
            edge = (path[i], path[i + 1])
            unique_edges.add(edge)

    print("\nEdges to Remove Candidat:")
    for edge in unique_edges:
        print(f"Edge: {edge}")
    print()

    return list(unique_edges), above_threshold, below_threshold



def main():
    namespace = "paper2"
    prometheus_url = "http://10.101.177.122:8080"
    threshold = 800  

    # DAG 생성
    k8s_client = KubernetesClient(namespace)
    deployment = list()
    istio_metrics = IstioMetrics(prometheus_url)
    edges = istio_metrics.get_request_durations(namespace)
    
    edges_with_deployments = []
    for source, destination, duration in edges:
        deployment.append(source)
        deployment.append(destination)
        source_deployment = source
        destination_deployment = destination
        
        if source_deployment != 'unknown' and destination_deployment != 'unknown':
            edges_with_deployments.append((source_deployment, destination_deployment, duration))

    unique_deployments = set(deployment)
    
    dag = DAG()
    dag.create_dag(unique_deployments, edges_with_deployments)

    # 제거할 후보 간선을 찾음
    edges_to_remove_candidate, above_threshold, below_threshold = select_edges_to_remove_candidate(dag, threshold)

    # 어떤 간선을 제거할 것인지 체크
    graph_map = GraphMap(dag)
    graphMap = graph_map.create_graph_map()

    removed_most_used_edges, removed_most_used_edges_map = graph_map.remove_most_used_edges(graphMap, above_threshold, edges_to_remove_candidate)
    remove_most_stream_edges, remove_most_stream_edges_map = graph_map.remove_most_stream_edges(graphMap, above_threshold, edges_to_remove_candidate)
    
    removed_most_used_edges_isolated = graph_map.find_replacement_node(graphMap, removed_most_used_edges_map)
    removed_most_stream_edges_isolated = graph_map.find_replacement_node(graphMap, remove_most_stream_edges_map)

    remove_edge_list = []
    replace_node_list = []
    if len(removed_most_used_edges_isolated) <= len(removed_most_stream_edges_isolated):
        remove_edge_list = removed_most_used_edges
        replace_node_list = removed_most_used_edges_isolated
    else:
        remove_edge_list = remove_most_stream_edges
        replace_node_list = removed_most_stream_edges_isolated

    print('remove_edge_list', remove_edge_list)
    print('replace_node_list', replace_node_list)


    service_routes, service_versions, downstream_versions = distribute_traffic_and_create_service_routes(k8s_client, dag, remove_edge_list)
    k8s_client.apply_virtual_service(service_routes, downstream_versions)
    k8s_client.apply_destination_rules(service_versions)
    
if __name__ == "__main__":
    main()

