from kube_client import KubernetesClient
from istio_metrics import IstioMetrics
from DAG import DAG
import copy

def print_node_connections(graph):
    for node in graph.nodes:
        upstream = list(graph.predecessors(node))
        downstream = list(graph.successors(node))
        print(f"Node: {node}, Upstream: {upstream}, Downstream: {downstream}")

def main():
    
    namespace = "paper2"
    prometheus_url = "http://10.109.129.191:8080"
    threshold = 1000  # Example threshold value, you can set this to your desired value

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

    #재배치할 노드
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


if __name__ == "__main__":
    main()
