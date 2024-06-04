import networkx as nx
import matplotlib.pyplot as plt
from collections import defaultdict

class DAG:
    def __init__(self):
        self.graph = nx.DiGraph()

    def create_dag(self, pods, edges):
        self.graph.clear()
        for pod in pods:
            self.graph.add_node(pod)
        for edge in edges:
            if len(edge) == 3:
                source, destination, data_size = edge
                if source in pods and destination in pods:
                    self.graph.add_edge(source, destination, weight=data_size)
            elif len(edge) == 2:
                source, destination = edge
                if source in pods and destination in pods:
                    self.graph.add_edge(source, destination)

    def draw_dag(self, file_name="dag.png"):
        pos = nx.spring_layout(self.graph)
        weights = nx.get_edge_attributes(self.graph, 'weight')
        
        plt.figure(figsize=(12, 8))
        nx.draw(self.graph, pos, with_labels=True, node_size=3000, node_color='skyblue', font_size=10, font_weight='bold', edge_color='gray')
        nx.draw_networkx_edge_labels(self.graph, pos, edge_labels=weights)
        
        plt.title("Kubernetes Pods DAG in Namespace 'paper2'")
        plt.savefig(file_name)
        plt.close()

    def find_all_paths_with_durations(self):
        all_paths = []
        for source in self.graph.nodes:
            for target in self.graph.nodes:
                if source != target:
                    paths = list(nx.all_simple_paths(self.graph, source=source, target=target))
                    for path in paths:
                        total_duration = 0
                        for i in range(len(path) - 1):
                            total_duration += self.graph[path[i]][path[i + 1]]['weight']
                        all_paths.append((path, round(total_duration)))
        return all_paths

    def filter_and_sort_paths(self, all_paths_with_durations):
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
        
        # Sort paths by total duration in descending order
        filtered_paths.sort(key=lambda x: x[1], reverse=True)
        
        return filtered_paths

    def separate_paths_by_threshold(self, filtered_sorted_paths, threshold):
        below_threshold = [path for path in filtered_sorted_paths if path[1] <= threshold]
        above_threshold = [path for path in filtered_sorted_paths if path[1] > threshold]
        return below_threshold, above_threshold

    def count_edge_occurrences(self, paths):
        edge_count = defaultdict(int)
        for path, _ in paths:
            for i in range(len(path) - 1):
                edge = (path[i], path[i + 1])
                edge_count[edge] += 1
        return edge_count

    def evaluate_edges(self, below_threshold_paths, above_threshold_paths):
        below_edge_count = self.count_edge_occurrences(below_threshold_paths)
        above_edge_count = self.count_edge_occurrences(above_threshold_paths)
        
        edge_evaluation = {}
        all_edges = set(below_edge_count.keys()).union(set(above_edge_count.keys()))
        
        for edge in all_edges:
            below_count = below_edge_count.get(edge, 0)
            above_count = above_edge_count.get(edge, 0)
            difference = below_count - above_count
            edge_evaluation[edge] = difference
        
        return edge_evaluation

    def check_isolated_nodes(self, graph, edges_to_remove):
            for edge in edges_to_remove:
                source, destination = edge
                if source in graph.nodes and destination in graph.nodes:
                    graph.remove_edge(source, destination)


            

    def create_dag_without_nodes(self, nodes_to_remove, edges):
        remaining_nodes = [node for node in self.graph.nodes if node not in nodes_to_remove]
        remaining_edges = [edge for edge in edges if edge[0] not in nodes_to_remove and edge[1] not in nodes_to_remove]
        self.create_dag(remaining_nodes, remaining_edges)
