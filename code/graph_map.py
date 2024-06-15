import copy
from collections import defaultdict

class GraphMap:
    def __init__(self, dag):
        self.dag = dag.graph  # DAG 객체의 graph 속성에 접근
    
    def create_graph_map(self):
        graph_map = {}
        for node in self.dag.nodes:
            upstream = list(self.dag.predecessors(node))
            downstream = list(self.dag.successors(node))
            graph_map[node] = {"upstream": upstream, "downstream": downstream}
        return graph_map
    
    def print_graph_map(self, graph_map):
        for node, connections in graph_map.items():
            print(f"Node: {node}")
            print(f"  Upstream: {connections['upstream']}")
            print(f"  Downstream: {connections['downstream']}")
    
    def is_node_isolated(self, temp_map, node):
        connections = temp_map[node]
        return not connections['upstream'] and not connections['downstream']
    
    def remove_edge(self, temp_map, source, destination):
        if destination in temp_map[source]["downstream"]:
            temp_map[source]["downstream"].remove(destination)
        if source in temp_map[destination]["upstream"]:
            temp_map[destination]["upstream"].remove(source)
    

    def remove_edges(self, temp_map, edges_to_remove):
        for edge in edges_to_remove:
            source, destination = edge
            self.remove_edge(temp_map, source, destination)
    

    def check_all_paths_removed(self, temp_map, paths_above_threshold):
        for path, _ in paths_above_threshold:
            path_removed = False
            for i in range(len(path) - 1):
                if path[i + 1] not in temp_map[path[i]]['downstream']:
                    path_removed = True
                    break
            if not path_removed:
                return False
        return True
    


    def remove_most_used_edges(self, graph_map, paths_above_threshold, edges_to_remove_candidate):
        temp_map = copy.deepcopy(graph_map)
        removed_edges = []

        while paths_above_threshold:
            # 간선 사용 빈도를 계산하여 소팅
            edge_usage = defaultdict(int)
            for path, _ in paths_above_threshold:
                for i in range(len(path) - 1):
                    edge = (path[i], path[i + 1])
                    edge_usage[edge] += 1

            # 사용 빈도가 높은 순으로 간선을 정렬
            edges_to_remove_candidate = sorted(edge_usage.keys(), key=lambda edge: edge_usage[edge], reverse=True)
            
            # 가장 많이 사용된 간선 제거
            most_used_edge = edges_to_remove_candidate[0]
            self.remove_edges(temp_map, [most_used_edge])
            removed_edges.append(most_used_edge)

            # 남은 paths_above_threshold에서 제거된 경로 제외
            remaining_paths = []
            for path, duration in paths_above_threshold:
                if not any((path[i], path[i + 1]) == most_used_edge for i in range(len(path) - 1)):
                    remaining_paths.append((path, duration))
            
            paths_above_threshold = remaining_paths

        return removed_edges, temp_map
    

    def remove_most_stream_edges(self, graph_map, paths_above_threshold, edges_to_remove_candidate):
        temp_map = copy.deepcopy(graph_map)
        removed_edges = []

        while paths_above_threshold:
            # 간선 사용 빈도를 계산하여 소팅
            edge_usage = defaultdict(int)
            for path, _ in paths_above_threshold:
                for i in range(len(path) - 1):
                    edge = (path[i], path[i + 1])
                    edge_usage[edge] += 1

            # 사용 빈도가 높은 순으로 간선을 정렬
            edges_to_remove_candidate = sorted(edge_usage.keys(), key=lambda edge: edge_usage[edge], reverse=True)

            # 가장 많이 사용된 간선 제거
            most_used_edge = edges_to_remove_candidate[0]
            self.remove_edges(temp_map, [most_used_edge])
            removed_edges.append(most_used_edge)

            # 남은 paths_above_threshold에서 제거된 경로 제외
            remaining_paths = []
            for path, duration in paths_above_threshold:
                if not any((path[i], path[i + 1]) == most_used_edge for i in range(len(path) - 1)):
                    remaining_paths.append((path, duration))
            
            paths_above_threshold = remaining_paths
        
        return removed_edges, temp_map
    

    def find_replacement_node(self, original_map, temp_map):
        isolated_nodes = set()
        while True:
            temp2_map = copy.deepcopy(temp_map)
            for node in original_map:
                original_upstream = set(original_map[node]["upstream"])
                original_downstream = set(original_map[node]["downstream"])
                temp_upstream = set(temp_map[node]["upstream"])
                temp_downstream = set(temp_map[node]["downstream"])
                # Upstream이 있었는데 없어졌다면
                if original_upstream and not temp_upstream:
                    isolated_nodes.add(node)
                # Downstream이 있었는데 없어졌다면
                if original_downstream and not temp_downstream:
                    isolated_nodes.add(node)
                    
                #isolated_node와 연관된 애들한테서 isolated_node를 지움    
                for isolated_node in isolated_nodes: 
                    for downstream in temp_map[isolated_node]["downstream"]:
                        if isolated_node in temp_map[downstream]["upstream"]:
                            temp_map[downstream]["upstream"].remove(isolated_node)
                    for upstream in temp_map[isolated_node]["upstream"]:
                        if isolated_node in temp_map[upstream]["downstream"]:
                            temp_map[upstream]["downstream"].remove(isolated_node)
                    temp_map[isolated_node]["upstream"] = []
                    temp_map[isolated_node]["downstream"] = []
                
            original_map = temp2_map
            if original_map == temp_map:
                break
        
        return isolated_nodes