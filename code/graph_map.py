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
    


    def remove_most_used_edges(self, graph_map, paths_above_threshold):
        '''
        paths_above_threshold에서 많이 사용된 간선을 위주로 제거
        '''
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
        '''
        가장 간선을 제거해도 재배치대상이 되지 않을 순으로 제거
        '''
        temp_map = copy.deepcopy(graph_map)
        removed_edges = []

        # 모든 paths_above_threshold가 제거될 때까지 반복
        while paths_above_threshold:
            # Step 1: 분리된 간선 리스트 초기화
            high_degree_edges = []  # 잘라도 이상 없는 애
            low_degree_edges = []  # 자르면 재배치될 애

            # Step 2: 간선을 제거하였을 때 source의 downstream이 2 이상이고, destination의 upstream이 2 이상인 간선을 대상으로 나눔
            for source, destination in edges_to_remove_candidate:
                if len(temp_map[source]["downstream"]) >= 2 and len(temp_map[destination]["upstream"]) >= 2:
                    high_degree_edges.append((source, destination))
                else:
                    low_degree_edges.append((source, destination))

            # Step 3: 간선을 upstream과 downstream의 합이 큰 순서대로 정렬
            def edge_degree_sum(edge):
                source, destination = edge
                return len(temp_map[source]["downstream"]) + len(temp_map[destination]["upstream"])

            # Step 4: high_degree_edges에 값이 하나라도 있다면 여기에 있는 간선을 제거할 거기 때문에 high_degree_edges만 정렬.
            # 값이 없다면, low_degree_edges에서 제거해야 하기 때문에 이걸 정렬
            if high_degree_edges:
                high_degree_edges.sort(key=edge_degree_sum, reverse=True)
            else:
                low_degree_edges.sort(key=edge_degree_sum, reverse=True)

            # Step 5: high_degree_edges의 첫 번째 요소를 제거, high_degree_edges가 없다면 low_degree_edges의 첫 번째 요소를 제거
            edge_to_remove = []
            if high_degree_edges:
                edge_to_remove = high_degree_edges[0]
            else:
                edge_to_remove = low_degree_edges[0]
            
            # edges_to_remove_candidate에서 edge_to_remove 제거
            edges_to_remove_candidate = [edge for edge in edges_to_remove_candidate if edge != edge_to_remove]

            self.remove_edges(temp_map, [edge_to_remove])
            removed_edges.append(edge_to_remove)
            
            # 남은 paths_above_threshold에서 제거된 경로 제외
            remaining_paths = []
            for path, duration in paths_above_threshold:
                if not any((path[i], path[i + 1]) == edge_to_remove for i in range(len(path) - 1)):
                    remaining_paths.append((path, duration))

            paths_above_threshold = remaining_paths
            #print('paths_above_threshold', paths_above_threshold)
            

        return removed_edges, temp_map


    

    def find_replacement_node(self, original_map, temp_map, k8s_client):
        replacement_nodes = set()

        # 제거 대상 노드를 찾음
        for node in original_map:
            original_upstream = set(original_map[node]["upstream"])
            original_downstream = set(original_map[node]["downstream"])
            temp_upstream = set(temp_map[node]["upstream"])
            temp_downstream = set(temp_map[node]["downstream"])

            # Upstream이 있었는데 없어졌다면
            if original_upstream and not temp_upstream:
                replacement_nodes.add(node)
            # Downstream이 있었는데 없어졌다면
            if original_downstream and not temp_downstream:
                replacement_nodes.add(node)

        # 제거 대상 노드의 up 그리고 downstream을 처리
        for replacement_node in replacement_nodes:
            # temp_map에서 자신을 검색후 upstream/downstream 빈 값으로 만들기
            temp_map[replacement_node]["upstream"] = []
            temp_map[replacement_node]["downstream"] = []

            # 자신의 서비스와 연결된 서비스들 중 upstream 서비스를 찾기
            source_name, source_version = k8s_client.get_labels_from_deployment(replacement_node)
            source_service = k8s_client.get_service_by_version(source_version)
            service_connections = self.get_service_connections(source_service)

            for upstream_service in service_connections["upstream"]:
                upstream_nodes = [node for node in temp_map if upstream_service in node]
                for upstream_node in upstream_nodes:
                    if replacement_node not in temp_map[upstream_node]["downstream"]:
                        temp_map[upstream_node]["downstream"].append(replacement_node)
            for downstream_service in service_connections["downstream"]:
                downstream_nodes = [node for node in temp_map if downstream_service in node]
                for downstream_node in downstream_nodes:
                    if downstream_node not in temp_map[replacement_node]["downstream"]:
                        temp_map[replacement_node]["downstream"].append(downstream_node)

        # 중복 제거를 위해 set을 사용하고 다시 list로 변환
        for node in temp_map:
            temp_map[node]["upstream"] = list(set(temp_map[node]["upstream"]))
            temp_map[node]["downstream"] = list(set(temp_map[node]["downstream"]))

        return replacement_nodes, temp_map

    


    def get_service_connections(self, service_name):
        upstream_services = set()
        downstream_services = set()

        for node, connections in self.dag.nodes(data=True):
            if service_name in node:
                upstream_services.update(self.dag.predecessors(node))
                downstream_services.update(self.dag.successors(node))

        return {
            "upstream": list(upstream_services),
            "downstream": list(downstream_services)
        }