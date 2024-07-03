
import os
import argparse
import sys
from dag.DAG import *
from dag.graph_map import *
from istio.istio_metrics import *
from kube.kube_client import *
from utils.edge_utils import *
from utils.node_utils import *
from utils.traffic_utils import *


    

def run_proposed_method(namespace, prometheus_url, threshold):
    vspath = "/home/dnc/master/paper2024/trafficyaml"
    
    print("Running proposed method with args:", namespace, prometheus_url, threshold)  # 디버깅 출력
    
    print('threshold', threshold)
    #os.makedirs(vspath, exist_ok=True)

    # 쿠버네티스와 프로메테우스 연결
    v1, apps_v1, custom_objects_api = load_kube_config()
    prom = connect_to_prometheus(prometheus_url)
    
    # istio에서 측정한 reqeust_durations 값 가져옴
    edges = get_request_durations(prom, namespace)

    # 데이터 전처리함
    edges_with_deployments = [
        (source, destination, duration) for source, destination, duration in edges
        if source != 'unknown' and destination != 'unknown'
    ]
    unique_deployments = set(
        [source for source, _, _ in edges_with_deployments] + 
        [destination for _, destination, _ in edges_with_deployments]
    )
    
    # 가져온 데이터들을 DAG로 표현함
    dag = create_dag(unique_deployments, edges_with_deployments)

    #경로 중 above_threshold인 (제거 대상 경로) 경로를 찾음
    all_paths_with_durations = find_all_paths_with_durations(dag)
    filtered_sorted_paths_with_durations = filter_and_sort_paths(all_paths_with_durations)
    below_threshold, above_threshold = separate_paths_by_threshold(filtered_sorted_paths_with_durations, threshold)
    print('above_threshold_path')
    for above_threshold_path in above_threshold:
        print(above_threshold_path)

    
    if not above_threshold:
        print("No paths above threshold. Program will exit.")
        return
    
    # DAG로 그래프 맵을 생성하고 현재 그래프 맵을 출력함
    graph_map = create_graph_map(dag)
    print('original graph map')
    print_graph_map(graph_map)

    
    # above_threshold 경로 중 제거해야할 간선을 MILP 최적화로 공식화하고, 유전알고리즘을 사용하여 찾음
    _, removed_most_used_edges_map, is_fair = select_remove_edges_genetic(graph_map, above_threshold, apps_v1, namespace)
    print_graph_map(removed_most_used_edges_map)

    # 간선을 제거하고 난 후 변경된 토폴로지에 대하여 공정하게 traffic을 분배하면서 local에 가장 많은 트래픽을 보내는 값을 찾음
    service_routes, service_versions = distribute_traffic_and_create_service_routes(removed_most_used_edges_map, v1, namespace, prom)
    print('service_routes')
    for service_route in service_routes:
        print(service_route)

    # 정보를 반영함    
    apply_virtual_service(custom_objects_api, service_routes, vspath)
    apply_destination_rules(namespace, custom_objects_api, service_versions, vspath)
    
    print("Complete")




def run_localization(namespace, prometheus_url):
    vspath = "/home/dnc/master/paper2024/trafficyaml"
    '''
    트래픽 localization 코드
    자신과 가장 가까운 노드에 보내버림
    '''
    os.makedirs(vspath, exist_ok=True)

    # 쿠버네티스와 프로메테우스 연결
    v1, apps_v1, custom_objects_api = load_kube_config()
    prom = connect_to_prometheus(prometheus_url)
    
    # istio에서 측정한 reqeust_durations 값 가져옴
    edges = get_request_durations(prom, namespace)

    # 데이터 전처리함
    edges_with_deployments = [
        (source, destination, duration) for source, destination, duration in edges
        if source != 'unknown' and destination != 'unknown'
    ]
    unique_deployments = set(
        [source for source, _, _ in edges_with_deployments] + 
        [destination for _, destination, _ in edges_with_deployments]
    )
    
    # 가져온 데이터들을 DAG로 표현하고, graph map을 생성함
    dag = create_dag(unique_deployments, edges_with_deployments)
    graph_map = create_graph_map(dag)

    # 간선을 제거하고 난 후 변경된 토폴로지에 대하여 공정하게 traffic을 분배하면서 local에 가장 많은 트래픽을 보내는 값을 찾음
    service_routes, service_versions = distribute_traffic_and_create_service_routes_localization(graph_map, v1, namespace, prom)
    print('service_routes')
    for service_route in service_routes:
        print(service_route)

    # 정보를 반영함    
    apply_virtual_service(custom_objects_api, service_routes, vspath)
    apply_destination_rules(namespace, custom_objects_api, service_versions, vspath)



if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python main.py <namespace> <prometheus_url> <threshold>")
        sys.exit(1)
    
    namespace = sys.argv[1]
    prometheus_url = sys.argv[2]
    threshold = int(sys.argv[3])
    print(namespace, prometheus_url, threshold)
    #run_proposed_method(namespace, prometheus_url, threshold)
    run_localization(namespace, prometheus_url)
