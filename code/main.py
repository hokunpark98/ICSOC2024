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



def distribute_traffic_and_create_service_routes(k8s_client, graph_map, current_map):
    service_versions = k8s_client.get_service_versions()
    service_routes = []

    for source in current_map:
        source_name, source_version = k8s_client.get_labels_from_deployment(source)
        source_service = k8s_client.get_service_by_version(source_version)
        service_connections = graph_map.get_service_connections(source_service)

        downstream_edges = current_map[source]['downstream']

        if downstream_edges:
            remaining_percentage = 100
            equal_weight = remaining_percentage // len(downstream_edges)
            remaining_weight = remaining_percentage % len(downstream_edges)

            for dest in downstream_edges:
                dest_name, dest_version = k8s_client.get_labels_from_deployment(dest)
                weight = equal_weight + (remaining_weight > 0)
                remaining_weight -= 1
                service_routes.append((source_name, source_version, dest_name, dest_version, weight))

    return service_routes, service_versions


'''
def distribute_traffic_and_create_service_routes(k8s_client, graph_map, current_map):
    service_versions = k8s_client.get_service_versions()
    service_routes = []

    for source in current_map:
        source_name, source_version = k8s_client.get_labels_from_deployment(source)
        source_service = k8s_client.get_service_by_version(source_version)
        service_connections = graph_map.get_service_connections(source_service)
        print('-------------------------')
        print('source', source)
        print('source_service', source_service)
        print('service_connections', service_connections)

        downstream_edges = current_map[source]['downstream']

        # 서비스 중 current_map에 없는 서비스들 찾기
        non_current_map_downstream_nodes = list(set(service_connections['downstream']) - set(downstream_edges))
        print("non_current_map_downstream_node", non_current_map_downstream_nodes)
        
        # 현재 맵에 없는 서비스들에게 1% 트래픽 할당
        for dest in non_current_map_downstream_nodes:
            dest_name, dest_version = k8s_client.get_labels_from_deployment(dest)
            service_routes.append((source_name, source_version, dest_name, dest_version, 1))

        # 나머지 트래픽을 현재 맵에 있는 다운스트림 서비스들에게 분배
        print('downstream_edges', downstream_edges)
        if downstream_edges:
            remaining_percentage = 100 - len(non_current_map_downstream_nodes) * 1
            equal_weight = remaining_percentage // len(downstream_edges)
            remaining_weight = remaining_percentage % len(downstream_edges)

            for dest in downstream_edges:
                dest_name, dest_version = k8s_client.get_labels_from_deployment(dest)
                weight = equal_weight + (remaining_weight > 0)
                remaining_weight -= 1
                service_routes.append((source_name, source_version, dest_name, dest_version, weight))

    return service_routes, service_versions
'''

def distribute_traffic_and_create_service_routes(k8s_client, graph_map, current_map):
    service_versions = k8s_client.get_service_versions()
    service_routes = []

    for source in current_map:
        source_name, source_version = k8s_client.get_labels_from_deployment(source)
        downstream_edges = current_map[source]['downstream']
     
        if downstream_edges:
            remaining_percentage = 100
            equal_weight = remaining_percentage // len(downstream_edges)
            remaining_weight = remaining_percentage % len(downstream_edges)

            for dest in downstream_edges:
                dest_name, dest_version = k8s_client.get_labels_from_deployment(dest)
                weight = equal_weight + (remaining_weight > 0)
                remaining_weight -= 1
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
            if node_for_pod != node:  # Ensure the node does not select itself
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

    if not above_threshold:
        print("No paths above threshold. Program will exit.")
        return

    graph_map = GraphMap(dag)
    graphMap = graph_map.create_graph_map()

    removed_most_used_edges, removed_most_used_edges_map = graph_map.remove_most_used_edges(graphMap, above_threshold)
    removed_most_used_edges_isolated, removed_most_used_edges_map = graph_map.find_replacement_node(graphMap, removed_most_used_edges_map, k8s_client)
    
    remove_most_stream_edges, remove_most_stream_edges_map = graph_map.remove_most_stream_edges(graphMap, above_threshold, edges_to_remove_candidate)
    removed_most_stream_edges_isolated, remove_most_stream_edges_map = graph_map.find_replacement_node(graphMap, remove_most_stream_edges_map, k8s_client)

    current_map = {}
    
    if len(removed_most_used_edges_isolated) <= len(removed_most_stream_edges_isolated):
        remove_edge_list = removed_most_used_edges
        replace_node_list = removed_most_used_edges_isolated
        current_map = removed_most_used_edges_map
        print("제거 간선 중 가장 사용빈도 높은애로 제거")
        print("removed_most_used_edges_isolated", removed_most_used_edges_isolated)
    else:
        remove_edge_list = remove_most_stream_edges
        replace_node_list = remove_most_stream_edges_map
        current_map = remove_most_stream_edges_map
        print("제거 간선 중 가장 재배치 적게 발생할 간선을 제거")
        print("removed_most_stream_edges_isolated", removed_most_stream_edges_isolated)

    print("removed_most_used_edges_isolated", removed_most_used_edges_isolated)
    print("removed_most_stream_edges_isolated", removed_most_stream_edges_isolated)
    print('current_map')
   
    replacement_nodes = find_replacement_nodes(replace_node_list, k8s_client, remove_edge_list)
    graph_map.print_graph_map(current_map)

    k8s_client.update_node_selector(replacement_nodes)

    # Apply the virtual services and destination rules
    service_routes, service_versions = distribute_traffic_and_create_service_routes(k8s_client,graph_map, current_map)
    for service_route in service_routes:
        print(service_route)
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
