import copy
from collections import defaultdict
import networkx as nx
import pulp
import random
from kube.kube_client import *
from utils.edge_utils import *

def create_graph_map(dag):
    return {
        node: {
            "upstream": list(dag.predecessors(node)),
            "downstream": list(dag.successors(node))
        }
        for node in dag.nodes
    }

def print_graph_map(graph_map):
    for node, connections in graph_map.items():
        print(f"Node: {node}")
        print(f"  Upstream: {connections['upstream']}")
        print(f"  Downstream: {connections['downstream']}")

def remove_edges(graph_map, edges_to_remove):
    for source, destination in edges_to_remove:
        if destination in graph_map[source]["downstream"]:
            graph_map[source]["downstream"].remove(destination)
        if source in graph_map[destination]["upstream"]:
            graph_map[destination]["upstream"].remove(source)

def convert_to_network(graph_map, nodes):
    network = {node: {'upstream': [], 'downstream': []} for node in nodes}
    for node in nodes:
        connections = graph_map.get(node, {'upstream': [], 'downstream': []})
        network[node]['upstream'] = [up_node for up_node in connections['upstream'] if up_node in nodes]
        network[node]['downstream'] = [down_node for down_node in connections['downstream'] if down_node in nodes]
    return network

def calculate_required_traffic(upstream_count, downstream_count, downstream_nodes):
    total_traffic = upstream_count * 100
    if downstream_count == 0:
        return {}

    traffic_per_downstream = total_traffic // downstream_count
    remainder = total_traffic % downstream_count

    downstream_traffic = {node: traffic_per_downstream for node in downstream_nodes}

    i = 0
    downstream_nodes_list = list(downstream_traffic.keys())
    while remainder > 0:
        downstream_traffic[downstream_nodes_list[i % downstream_count]] += 1
        remainder -= 1
        i += 1

    return downstream_traffic

def get_traffic_requirements(nodes, source_service, destination_service):
    upstream_nodes = [node for node in nodes if node.startswith(source_service)]
    downstream_nodes = [node for node in nodes if node.startswith(destination_service)]
    upstream_traffic = {node: 100 for node in upstream_nodes}
    downstream_traffic = calculate_required_traffic(len(upstream_traffic), len(downstream_nodes), downstream_nodes)
    return downstream_traffic, upstream_traffic

def check_fair_distribution(network, downstream_traffic, upstream_traffic):
    G = nx.DiGraph()
    G.add_node('source')
    G.add_node('sink')

    for u_node in upstream_traffic:
        G.add_edge('source', u_node, capacity=upstream_traffic[u_node])
    for u_node in network:
        for d_node in network[u_node]['downstream']:
            G.add_edge(u_node, d_node, capacity=float('inf'))
    for d_node in downstream_traffic:
        G.add_edge(d_node, 'sink', capacity=downstream_traffic[d_node])

    flow_value, flow_dict = nx.maximum_flow(G, 'source', 'sink')

    actual_downstream_traffic = {d: 0 for d in downstream_traffic}
    actual_upstream_traffic = {u: 0 for u in upstream_traffic}
    for u_node in flow_dict:
        if u_node in upstream_traffic:
            for d_node, flow in flow_dict[u_node].items():
                if d_node != 'sink':
                    actual_downstream_traffic[d_node] += flow
                    actual_upstream_traffic[u_node] += flow

    is_fair = True
    for d in downstream_traffic:
        if actual_downstream_traffic[d] != downstream_traffic[d]:
            is_fair = False
    for u in upstream_traffic:
        if actual_upstream_traffic[u] != upstream_traffic[u]:
            is_fair = False

    return is_fair


def generate_combinations(items):
    combinations = []

    def backtrack(current_combination, start):
        combinations.append(current_combination[:])
        for i in range(start, len(items)):
            current_combination.append(items[i])
            backtrack(current_combination, i + 1)
            current_combination.pop()

    backtrack([], 0)
    return combinations



def select_remove_edges(graph_map, paths_above_threshold, apps_v1, namespace):
    edges_to_remove_candidate = defaultdict(int)
    for path, _ in paths_above_threshold:
        for i in range(len(path) - 1):
            edges_to_remove_candidate[(path[i], path[i + 1])] += 1

    all_edge_combinations = generate_combinations(list(edges_to_remove_candidate.keys()))

    alpha = 0.5  
    beta = 1 - alpha 

    max_duration = 0
    avg_duration = 9999999
    best_score = 999999
    best_map = {}
    best_remove_edges = []

    for edge_combination in all_edge_combinations:
        temp_above_threshold = copy.deepcopy(paths_above_threshold)
        temp_map = copy.deepcopy(graph_map)
        remove_edges(temp_map, edge_combination)

        #공정한지 확인
        is_fair = False
        for edge in edge_combination:
            source_service = get_service_by_version(apps_v1, namespace, edge[0])
            destination_service = get_service_by_version(apps_v1, namespace, edge[1])
            downstream_traffic, upstream_traffic = get_traffic_requirements(temp_map, source_service, destination_service)
            is_fair = check_fair_distribution(temp_map, downstream_traffic, upstream_traffic)
            if not is_fair:
                print('is not fair')
                print('edge_combination', edge_combination)
                break
    
        if not is_fair:
            continue

        #잔여 경로 구함
        remaining_paths = [
            (path, duration) for path, duration in temp_above_threshold
            if not any((path[i], path[i + 1]) == edge_combination for i in range(len(path) - 1))
        ]
       
        #잔여 경로의 총 duration
        total_duration = 0
        for remaining_path in remaining_paths:
            total_duration = total_duration + remaining_path[1]
        
        #기존 총 duration
        original_total_duration = 0
        for path_above_threshold in paths_above_threshold:
            original_total_duration = original_total_duration + path_above_threshold[1]

        max_duration = max(remaining_paths, key=lambda x: x[1], default=(None, 0))[1]
        original_max_duration = max(paths_above_threshold, key=lambda x: x[1], default=(None, 0))[1]
        rate_max = max_duration / original_max_duration * 100
        rate_total = total_duration / original_total_duration * 100
        print(rate_max, rate_total)
        score = alpha * rate_max + beta * rate_total
        
        if score < best_score:
            best_score = score
            best_remove_edges = edge_combination
            best_map = temp_map

        print('edge_combination', edge_combination)
        print('max_duration', max_duration)
        print('avg_duration', avg_duration)
        
        if max_duration == 0:
            break


    print('best_remove_edges')
    for best_remove_edge in best_remove_edges:
        print(best_remove_edge) 
    
    return best_remove_edges, best_map



def generate_initial_population(edges, population_size):
    population = []
    for _ in range(population_size):
        individual = random.sample(edges, random.randint(1, len(edges)))
        population.append(individual)
    return population

def calculate_fitness(individual, graph_map, paths_above_threshold, apps_v1, namespace):
    temp_map = copy.deepcopy(graph_map)
    
    remove_edges(temp_map, individual)

    # 기존의 업스트림 및 다운스트림 연결 수 추적
    original_upstream_count = {node: len(connections['upstream']) for node, connections in graph_map.items()}
    original_downstream_count = {node: len(connections['downstream']) for node, connections in graph_map.items()}

    # 공정한지 확인
    is_fair = True
    for edge in individual:
        source_service = get_service_by_version(apps_v1, namespace, edge[0])
        destination_service = get_service_by_version(apps_v1, namespace, edge[1])
        downstream_traffic, upstream_traffic = get_traffic_requirements(temp_map, source_service, destination_service)
        is_fair = check_fair_distribution(temp_map, downstream_traffic, upstream_traffic)
        if not is_fair:
            return float('inf')  # 공정하지 않으면 매우 큰 값을 반환

    # 모든 노드에 대해 최소 하나의 업스트림 또는 다운스트림 연결이 유지되는지 확인
    for node in temp_map:
        if original_upstream_count[node] > 0 and len(temp_map[node]['upstream']) == 0:
            return float('inf')  # 하나 이상의 업스트림 연결이 있었으나 현재는 없음
        if original_downstream_count[node] > 0 and len(temp_map[node]['downstream']) == 0:
            return float('inf')  # 하나 이상의 다운스트림 연결이 있었으나 현재는 없음

    # 잔여 경로 구함
    remaining_paths = [
        (path, duration) for path, duration in paths_above_threshold
        if not any((path[i], path[i + 1]) in individual for i in range(len(path) - 1))
    ]
        
    # 잔여 경로의 총 duration
    total_duration = sum(duration for _, duration in remaining_paths)
    original_total_duration = sum(duration for _, duration in paths_above_threshold)
    max_duration = max(remaining_paths, key=lambda x: x[1], default=(None, 0))[1]
    original_max_duration = max(paths_above_threshold, key=lambda x: x[1], default=(None, 0))[1]
    rate_max = max_duration / original_max_duration * 100
    rate_total = total_duration / original_total_duration * 100
    
    # Fitness 계산
    alpha = 0.5
    beta = 1 - alpha
    score = alpha * rate_max + beta * rate_total
    return score

def crossover(parent1, parent2):
    if len(parent1) == 1:
        cut = 1
    else:
        cut = random.randint(1, len(parent1) - 1)
    child1 = parent1[:cut] + parent2[cut:]
    child2 = parent2[:cut] + parent1[cut:]
    return child1, child2

def mutate(individual, mutation_rate, all_edges):
    for i in range(len(individual)):
        if random.random() < mutation_rate:
            individual[i] = random.choice(all_edges)
    return individual

def select_remove_edges_genetic(graph_map, paths_above_threshold, apps_v1, namespace, population_size=100, generations=30, mutation_rate=0.04):
    edges_to_remove_candidate = defaultdict(int)
    for path, _ in paths_above_threshold:
        for i in range(len(path) - 1):
            edges_to_remove_candidate[(path[i], path[i + 1])] += 1

    all_edges = list(edges_to_remove_candidate.keys())
    population = [random.sample(all_edges, k=random.randint(1, len(all_edges))) for _ in range(population_size)]

    for generation in range(generations):
        print(f"Generation {generation + 1}/{generations}")
        
        population_fitness = [(individual, calculate_fitness(individual, graph_map, paths_above_threshold, apps_v1, namespace)) for individual in population]
        population_fitness.sort(key=lambda x: x[1])

        next_generation = population_fitness[:population_size//2]

        while len(next_generation) < population_size:
            parent1, parent2 = random.choices(next_generation, k=2)
            child1, child2 = crossover(parent1[0], parent2[0])
            next_generation.extend([(mutate(child1, mutation_rate, all_edges), None), (mutate(child2, mutation_rate, all_edges), None)])

        population = [individual for individual, fitness in next_generation]

        # Optional: Print the best fitness score of the current generation
        best_individual = min(population, key=lambda individual: calculate_fitness(individual, graph_map, paths_above_threshold, apps_v1, namespace))
        best_fitness = calculate_fitness(best_individual, graph_map, paths_above_threshold, apps_v1, namespace)
        print(f"Best fitness in generation {generation + 1}: {best_fitness}")
        if best_fitness == 0.0:
            break

    best_individual = min(population, key=lambda individual: calculate_fitness(individual, graph_map, paths_above_threshold, apps_v1, namespace))
    best_fitness = calculate_fitness(best_individual, graph_map, paths_above_threshold, apps_v1, namespace)
    print('remove edges', best_individual)
    temp_map = copy.deepcopy(graph_map)
    remove_edges(temp_map, best_individual)

    is_fair = True
    for edge in best_individual:
        source_service = get_service_by_version(apps_v1, namespace, edge[0])
        destination_service = get_service_by_version(apps_v1, namespace, edge[1])
        downstream_traffic, upstream_traffic = get_traffic_requirements(temp_map, source_service, destination_service)
        is_fair = check_fair_distribution(temp_map, downstream_traffic, upstream_traffic)
        print(f"Is the distribution fair after removing edge {edge}? {is_fair}")
        if not is_fair:
            break

    return best_individual, temp_map, is_fair
