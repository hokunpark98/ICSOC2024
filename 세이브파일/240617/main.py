import subprocess
from kube_client import KubernetesClient
from istio_metrics import IstioMetrics
from DAG import DAG
from graph_map import GraphMap
from collections import defaultdict
import os
import yaml
from collections import Counter



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
    downstream_counts = {node: len(current_map[node]['downstream']) for node in current_map}

    for source in current_map:
        source_name, source_version = k8s_client.get_labels_from_deployment(source)
        downstream_edges = current_map[source]['downstream']
        all_versions = service_versions.get(source_name, [])

        # Identify downstream services
        downstream_services = set()
        for dest in downstream_edges:
            dest_name, dest_version = k8s_client.get_labels_from_deployment(dest)
            downstream_services.add(dest_name)

        # Check if all downstream deployments are included in the current map
        all_downstream_in_map = all(
            k8s_client.get_labels_from_deployment(dep)[1] in downstream_edges for dep in downstream_edges
        )

        if all_downstream_in_map:
            # Distribute 100% of the traffic if all downstream deployments are in the current map
            if downstream_edges:
                equal_weight = 100 // len(downstream_edges)
                remaining_weight = 100 % len(downstream_edges)

                for dest in downstream_edges:
                    dest_name, dest_version = k8s_client.get_labels_from_deployment(dest)
                    weight = equal_weight + (remaining_weight > 0)
                    remaining_weight -= 1
                    service_routes.append((source_name, source_version, dest_name, dest_version, weight))
        else:
            # Distribute 95% of the traffic if not all downstream deployments are in the current map
            if downstream_edges:
                equal_weight = 95 // len(downstream_edges)
                remaining_weight = 95 % len(downstream_edges)

                for dest in downstream_edges:
                    dest_name, dest_version = k8s_client.get_labels_from_deployment(dest)
                    weight = equal_weight + (remaining_weight > 0)
                    remaining_weight -= 1
                    service_routes.append((source_name, source_version, dest_name, dest_version, weight))

            # Distribute 5% of the traffic to non-downstream deployments in downstream services
            for downstream_service in downstream_services:
                non_downstream_deployments = [
                    dep for dep in service_versions[downstream_service]
                    if k8s_client.get_labels_from_deployment(dep)[1] not in downstream_edges
                ]
                if non_downstream_deployments:
                    non_downstream_weight = 5 // len(non_downstream_deployments)
                    remaining_non_downstream_weight = 5 % len(non_downstream_deployments)

                    for dest in non_downstream_deployments:
                        dest_name, dest_version = k8s_client.get_labels_from_deployment(dest)
                        weight = non_downstream_weight + (remaining_non_downstream_weight > 0)
                        remaining_non_downstream_weight -= 1
                        service_routes.append((source_name, source_version, dest_name, dest_version, weight))

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



def find_replacement_nodes(replace_node_list, k8s_client, remove_edge_list):
    replacement_nodes = {}

    # 워커 노드의 자원을 관리하는 딕셔너리
    node_resources = {}

    # 모든 노드의 자원을 미리 가져와서 딕셔너리에 저장
    nodes = k8s_client.v1.list_node().items
    for node in nodes:
        node_name = node.metadata.name
        allocatable = node.status.allocatable
        cpu_value = allocatable["cpu"]
        if cpu_value.endswith('m'):
            cpu_value = int(cpu_value.rstrip('m'))
        else:
            cpu_value = int(float(cpu_value) * 1000)  # Convert cores to millicores

        memory_value = allocatable["memory"]
        if memory_value.endswith('Ki'):
            memory_value = int(memory_value.rstrip('Ki')) // 1024  # Convert Ki to Mi
        elif memory_value.endswith('Mi'):
            memory_value = int(memory_value.rstrip('Mi'))
        elif memory_value.endswith('Gi'):
            memory_value = int(float(memory_value.rstrip('Gi')) * 1024)  # Convert Gi to Mi

        node_resources[node_name] = {
            "cpu": cpu_value,
            "memory": memory_value
        }

    # remove_edge_list에서 각 노드의 출현 빈도를 계산
    node_frequency = Counter(node for edge in remove_edge_list for node in edge)

    # 출현 빈도에 따라 replace_node_list를 정렬
    replace_node_list = list(replace_node_list)
    replace_node_list.sort(key=lambda x: node_frequency.get(x, 0), reverse=True)

    for node in replace_node_list:
        app_label, _ = k8s_client.get_labels_from_deployment(node)
        if not app_label:
            print(f"App label not found for deployment: {node}")
            continue

        candidate_versions = []
        versions = k8s_client.get_versions_for_service(app_label)
        for version in versions:
            pods = k8s_client.v1.list_namespaced_pod(k8s_client.namespace, label_selector=f'app={app_label},version={version}').items
            if not pods:
                continue
            pod_name = pods[0].metadata.name

            node_for_pod = k8s_client.get_node_for_pod(pod_name)
            candidate_versions.append((version, node_for_pod))

        for version, node_name in candidate_versions:
            resources = node_resources[node_name]

            # 재배치 대상 노드의 요청 자원을 가져옴
            deployment_resources = k8s_client.get_deployment_resources(node, k8s_client.namespace, k8s_client)

            if (resources["cpu"] >= deployment_resources["cpu"]) and (resources["memory"] >= deployment_resources["memory"]):
                # 자원이 충분한 경우, 자원 업데이트
                node_resources[node_name]["cpu"] -= deployment_resources["cpu"]
                node_resources[node_name]["memory"] -= deployment_resources["memory"]

                replacement_nodes[node] = (version, node_name)
                break

    return replacement_nodes




def main(namespace, prometheus_url, threshold):
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

    print('remove_edge_list11', remove_edge_list)
    # Filter the remove_edge_list using the replace_node_list
    final_remove_edge_list = filter_edges(remove_edge_list, replace_node_list)

    graph_map.print_graph_map(current_map)
    replacement_nodes = find_replacement_nodes(replace_node_list, k8s_client, remove_edge_list)

    print('remove_edge_list', final_remove_edge_list)
    print('replacement_nodes', replacement_nodes)

    # Update the node selector of the deployments
    #k8s_client.update_node_selector(replacement_nodes)

    # Apply the virtual services and destination rules
    service_routes, service_versions = distribute_traffic_and_create_service_routes(k8s_client, current_map)
    k8s_client.apply_virtual_service(service_routes)
    k8s_client.apply_destination_rules(service_versions)

    print("complete")

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 4:
        print("Usage: python main.py <namespace> <prometheus_url> <threshold>")
        sys.exit(1)
    
    namespace = sys.argv[1]
    prometheus_url = sys.argv[2]
    threshold = int(sys.argv[3])

    main(namespace, prometheus_url, threshold)
