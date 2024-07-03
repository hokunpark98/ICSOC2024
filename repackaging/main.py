
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
    
    
    print("Running proposed method with args:", namespace, prometheus_url, threshold)  # 디버깅 출력
    
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
    #filtered_sorted_paths_with_durations = separate_top_30_percent_paths(filtered_sorted_paths_with_durations)

    
    print('filtered_sorted_paths_with_durations')
    for filtered_sorted_paths_with_duration in filtered_sorted_paths_with_durations:
        print('filtered_sorted_paths_with_durations', filtered_sorted_paths_with_duration)
    

    # DAG로 그래프 맵을 생성하고 현재 그래프 맵을 출력함
    graph_map = create_graph_map(dag)
    print('original graph map')
    print_graph_map(graph_map)
    
    # above_threshold 경로 중 제거해야할 간선을 ILP 최적화로 공식화하고, 유전알고리즘을 사용하여 찾음
    best_map, service_routes, service_versions = select_remove_edges_genetic(graph_map=graph_map, filtered_sorted_paths_with_durations=filtered_sorted_paths_with_durations, apps_v1=apps_v1, namespace=namespace, v1=v1, dag=dag)
    print_graph_map(best_map)

    print('service_routes')
    for service_route in service_routes:
        print(service_route)

    # 정보를 반영함    
    apply_virtual_service(custom_objects_api, service_routes)
    apply_destination_rules(namespace, custom_objects_api, service_versions)
    
    print("Complete")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python main.py <namespace> <prometheus_url> <threshold>")
        sys.exit(1)
    
    namespace = sys.argv[1]
    prometheus_url = sys.argv[2]
    threshold = int(sys.argv[3])
    run_proposed_method(namespace, prometheus_url, threshold)
