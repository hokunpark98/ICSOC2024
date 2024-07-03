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
            source, destination, data_size = edge
            if source in pods and destination in pods:
                graph.add_edge(source, destination, weight=data_size)
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

def separate_paths_by_threshold(filtered_sorted_paths, threshold):
    below_threshold = [path for path in filtered_sorted_paths if path[1] <= threshold]
    above_threshold = [path for path in filtered_sorted_paths if path[1] > threshold]
    return below_threshold, above_threshold


