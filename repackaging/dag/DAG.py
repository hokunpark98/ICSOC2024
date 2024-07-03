import networkx as nx
import matplotlib.pyplot as plt
from collections import defaultdict, Counter
import copy

def create_dag(pods, edges):
    graph = nx.DiGraph()
    for pod in pods:
        graph.add_node(pod)
    for edge in edges:
        if len(edge) == 3:
            source, destination, latency = edge
            if source in pods and destination in pods:
                graph.add_edge(source, destination, weight=int(latency))
        elif len(edge) == 2:
            source, destination = edge
            if source in pods and destination in pods:
                graph.add_edge(source, destination)
    return graph

def find_all_paths_with_durations(graph):
    all_paths = []
    for source in graph.nodes:
        for target in graph.nodes:
            if source != target:
                paths = list(nx.all_simple_paths(graph, source=source, target=target))
                for path in paths:
                    total_duration = 0
                    for i in range(len(path) - 1):
                        total_duration += graph[path[i]][path[i + 1]]['weight']
                    all_paths.append((path, round(total_duration)))
    return all_paths

def filter_and_sort_paths(all_paths_with_durations):
    def is_sub_path(path, other_path):
        if len(path) >= len(other_path):
            return False
        for i in range(len(other_path) - len(path) + 1):
            if other_path[i:i + len(path)] == path:
                return True
        return False

    filtered_paths = []
    paths_list = [path for path, duration in all_paths_with_durations]

    for path, duration in all_paths_with_durations:
        if not any(is_sub_path(path, other_path) for other_path in paths_list if path != other_path):
            filtered_paths.append((path, duration))

    filtered_paths.sort(key=lambda x: x[1], reverse=True)

    return filtered_paths

def separate_top_30_percent_paths(filtered_sorted_paths):
    """
    주어진 경로 리스트에서 상위 30% 경로를 반환
    """
    # 경로 리스트의 길이를 계산합니다.
    total_paths = len(filtered_sorted_paths)

    # 상위 20% 경로의 수를 계산합니다.
    top_30_percent_count = max(1, int(total_paths * 0.3))

    # 경로를 길이(또는 다른 기준)로 정렬합니다.
    sorted_paths = sorted(filtered_sorted_paths, key=lambda x: x[1], reverse=True)

    # 상위 20% 경로를 선택합니다.
    top_30_percent_paths = sorted_paths[:top_30_percent_count]

    return top_30_percent_paths


