import subprocess
from kube_client import KubernetesClient
from istio_metrics import IstioMetrics
from DAG import DAG
from graph_map import GraphMap
from collections import defaultdict
import os
import yaml


def filter_edges(remove_edge_list, replace_node_list):
    filtered_edge_list = [
        edge for edge in remove_edge_list
        if edge[0] not in replace_node_list and edge[1] not in replace_node_list
    ]
    return filtered_edge_list


def get_node_resources(self, node_name):
    node = self.v1.read_node(node_name)
    allocatable = node.status.allocatable
    return {
        "cpu": allocatable["cpu"],
        "memory": allocatable["memory"]
    }


def distribute_traffic_and_create_service_routes(k8s_client, current_map):
    service_versions = k8s_client.get_service_versions()

    service_routes = []

    for source in current_map:
        source_name, source_version = k8s_client.get_labels_from_deployment(source)
        downstream_edges = current_map[source]['downstream']

        if downstream_edges:
            equal_weight = 100 // len(downstream_edges)
            remaining_weight = 100 % len(downstream_edges)

            for dest in downstream_edges:
                dest_name, dest_version = k8s_client.get_labels_from_deployment(dest)
                weight = equal_weight + (remaining_weight > 0)
                remaining_weight -= 1
                service_routes.append((source_name, source_version, dest_name, dest_version, weight))


    # Formatted output
    print("Service Routes:")
    for route in service_routes:
        print(f"  Source: {route[0]} (version: {route[1]}) -> Destination: {route[2]} (version: {route[3]}), Weight: {route[4]}")
    
    print("\nService Versions:")
    for service, versions in service_versions.items():
        versions_str = ", ".join(versions)
        print(f"  {service}: {versions_str}")

    return service_routes, service_versions



def select_edges_to_remove_candidate(graph_map, threshold):
    all_paths_with_durations = graph_map.find_all_paths_with_durations()
    filtered_sorted_paths_with_durations = graph_map.filter_and_sort_paths(all_paths_with_durations)
    below_threshold, above_threshold = graph_map.separate_paths_by_threshold(filtered_sorted_paths_with_durations, threshold)

    print("\nPaths Below Threshold:")
    for path, total_duration in below_threshold:
        print("Path:", " -> ".join(path), "Total Duration:", total_duration)

    print("\nPaths Above Threshold:")
    for path, total_duration in above_threshold:
        print("Path:", " -> ".join(path), "Total Duration:", total_duration)

    unique_edges = set()
    for path, _ in above_threshold:
        for i in range(len(path) - 1):
            edge = (path[i], path[i + 1])
            unique_edges.add(edge)

    print("\nEdges to Remove Candidate:")
    for edge in unique_edges:
        print(f"Edge: {edge}")
    print()

    return list(unique_edges), above_threshold, below_threshold


def find_replacement_nodes(current_map, replace_node_list, k8s_client):
    replacement_nodes = {}

    for node in replace_node_list:
        app_label, _ = k8s_client.get_labels_from_deployment(node)
        if not app_label:
            print(f"App label not found for deployment: {node}")
            continue

        candidate_versions = []
        versions = k8s_client.get_versions_for_service(app_label)
        for version in versions:
            pods = k8s_client.v1.list_namespaced_pod(k8s_client.namespace, label_selector=f'app={app_label},version={version}').items
            pod_name = pods[0].metadata.name

            upstream_count = len(current_map[version]['upstream']) if version in current_map else 0
            downstream_count = len(current_map[version]['downstream']) if version in current_map else 0
            up_down_count = upstream_count + downstream_count

            node_for_pod = k8s_client.get_node_for_pod(pod_name)
            candidate_versions.append((version, node_for_pod, up_down_count))

        candidate_versions.sort(key=lambda x: x[2], reverse=True)

        for version, node_name, _ in candidate_versions:
            resources = k8s_client.get_node_resources(node_name)
            if resources["cpu"] > "0" and resources["memory"] > "0":
                replacement_nodes[node] = (version, node_name)
                break

    return replacement_nodes


def main():
    namespace = "paper2"
    prometheus_url = "http://10.101.177.122:8080"
    threshold = 100

    k8s_client = KubernetesClient(namespace)
    istio_metrics = IstioMetrics(prometheus_url)
    edges = istio_metrics.get_request_durations(namespace)
    
    edges_with_deployments = []
    for source, destination, duration in edges:
        source_deployment = source
        destination_deployment = destination

        if source_deployment != 'unknown' and destination_deployment != 'unknown':
            edges_with_deployments.append((source_deployment, destination_deployment, duration))

    unique_deployments = set([source for source, _, _ in edges_with_deployments] + [destination for _, destination, _ in edges_with_deployments])

    dag = DAG()
    dag.create_dag(unique_deployments, edges_with_deployments)

    edges_to_remove_candidate, above_threshold, below_threshold = select_edges_to_remove_candidate(dag, threshold)

    # above_threshold가 빈 리스트인 경우 프로그램 종료
    if not above_threshold:
        print("No paths above threshold. Program will exit.")
        return

    graph_map = GraphMap(dag)
    graphMap = graph_map.create_graph_map()

    removed_most_used_edges, removed_most_used_edges_map = graph_map.remove_most_used_edges(graphMap, above_threshold, edges_to_remove_candidate)
    remove_most_stream_edges, remove_most_stream_edges_map = graph_map.remove_most_stream_edges(graphMap, above_threshold, edges_to_remove_candidate)

    removed_most_used_edges_isolated = graph_map.find_replacement_node(graphMap, removed_most_used_edges_map)
    removed_most_stream_edges_isolated = graph_map.find_replacement_node(graphMap, remove_most_stream_edges_map)

    current_map = {}

    if len(removed_most_used_edges_isolated) <= len(removed_most_stream_edges_isolated):
        remove_edge_list = removed_most_used_edges
        replace_node_list = removed_most_used_edges_isolated
        current_map = removed_most_used_edges_map
    else:
        remove_edge_list = remove_most_stream_edges
        replace_node_list = remove_most_stream_edges_map
        current_map = remove_most_stream_edges_map

    # Filter the remove_edge_list using the replace_node_list
    remove_edge_list = filter_edges(remove_edge_list, replace_node_list)

    graph_map.print_graph_map(current_map)
    replacement_nodes = find_replacement_nodes(current_map, replace_node_list, k8s_client)
    print('remove_edge_list', remove_edge_list)
    print('replacement_nodes', replacement_nodes)

    # Update the node selector of the deployments
    # k8s_client.update_node_selector(replacement_nodes)

    # Apply the virtual services and destination rules
    service_routes, service_versions = distribute_traffic_and_create_service_routes(k8s_client, current_map)
    k8s_client.apply_virtual_service(service_routes)
    k8s_client.apply_destination_rules(service_versions)

if __name__ == "__main__":
    main()
