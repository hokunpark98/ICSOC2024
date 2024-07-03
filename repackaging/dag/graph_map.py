import copy
from collections import defaultdict
import networkx as nx
import pulp
import random
from kube.kube_client import *
from utils.edge_utils import *
from istio.istio_metrics import get_probe_icmp_durations

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
    return graph_map

def convert_to_network(graph_map, nodes):
    network = {node: {'upstream': [], 'downstream': []} for node in nodes}
    for node in nodes:
        connections = graph_map.get(node, {'upstream': [], 'downstream': []})
        network[node]['upstream'] = [up_node for up_node in connections['upstream'] if up_node in nodes]
        network[node]['downstream'] = [down_node for down_node in connections['downstream'] if down_node in nodes]
    return network

def calculate_required_traffic(upstream_count, downstream_nodes):
    total_traffic = upstream_count * 100
    downstream_count = len(downstream_nodes)
    
    if downstream_count == 0:
        return {}
    
    traffic_per_downstream = total_traffic // downstream_count
    remainder = total_traffic % downstream_count
    
    downstream_traffic = {node: traffic_per_downstream for node in downstream_nodes}
    
    i = 0
    while remainder > 0:
        downstream_traffic[downstream_nodes[i % downstream_count]] += 1
        remainder -= 1
        i += 1
    
    return downstream_traffic

def get_traffic_requirements(nodes, source_service, destination_service):
    upstream_nodes = [node for node in nodes if node.startswith(source_service)]
    downstream_nodes = [node for node in nodes if node.startswith(destination_service)]
    upstream_traffic = {node: 100 for node in upstream_nodes}
    downstream_traffic = calculate_required_traffic(len(upstream_traffic), downstream_nodes)
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

def crossover(parent1, parent2):
    if len(parent1) == 1:
        cut = 1
    else:
        cut = random.randint(1, len(parent1) - 1)
    child1 = parent1[:cut] + [edge for edge in parent2[cut:] if edge not in parent1[:cut]]
    child2 = parent2[:cut] + [edge for edge in parent1[cut:] if edge not in parent2[:cut]]
    return child1, child2

def mutate(individual, mutation_rate, all_edges):
    individual_set = set(individual)
    for i in range(len(individual)):
        if random.random() < mutation_rate:
            new_edge = random.choice(all_edges)
            while new_edge in individual_set:
                new_edge = random.choice(all_edges)
            individual[i] = new_edge
            individual_set.add(new_edge)
    return individual


def distribute_traffic_ilp(network, downstream_traffic, upstream_traffic, edge_weights, version_node_map):
    prob = pulp.LpProblem("TrafficDistribution", pulp.LpMinimize)

    # Create decision variables
    traffic_vars = {}
    for u_node in upstream_traffic:
        for d_node in network[u_node]['downstream']:
            traffic_vars[(u_node, d_node)] = pulp.LpVariable(f"traffic_{u_node}_{d_node}", 0, upstream_traffic[u_node], cat='Continuous')

    # Add constraints for upstream traffic
    for u_node in upstream_traffic:
        prob += pulp.lpSum(traffic_vars[(u_node, d_node)] for d_node in network[u_node]['downstream']) == upstream_traffic[u_node]
    
    # Add constraints for downstream traffic
    for d_node in downstream_traffic:
        prob += pulp.lpSum(traffic_vars[(u_node, d_node)] for u_node in upstream_traffic if (u_node, d_node) in traffic_vars) <= downstream_traffic[d_node]

    prob += pulp.lpSum(edge_weights[(u_node, d_node)] * traffic_vars[(u_node, d_node)] for u_node, d_node in traffic_vars)

    # Solve the problem
    prob.solve(pulp.PULP_CBC_CMD(msg=False))

    # Extract the results
    flow_dict = {u_node: {} for u_node in upstream_traffic}
    for (u_node, d_node), var in traffic_vars.items():
        value = var.varValue if var.varValue > 1e-6 else 0  # Treat small values as zero
        flow_dict[u_node][d_node] = value

    return flow_dict, prob.objective.value()


def generate_initial_population(edges, population_size, dag):
    population = []
        
    for _ in range(population_size):
        weights = [dag[u_node][d_node]['weight'] for u_node, d_node in edges]
        total_weight = sum(weights)
        probabilities = [weight / total_weight for weight in weights]
        individual = random.choices(edges, probabilities, k=random.randint(1, len(edges)))
        population.append(individual)
    return population



def distribute_traffic_and_create_service_routes(current_map, v1, namespace, dag):
    service_versions = get_service_versions(v1, namespace)
    version_node_map = get_versions_on_nodes(v1, namespace)
    service_routes = []
    edge_weights = {(u, v): data['weight'] for u, v, data in dag.edges(data=True)}
    global_min_latnecy = 0

    for service, versions in service_versions.items():    
        downstream_nodes = set()    
        for version in versions:
            if version not in current_map:
                print(f"Warning: {version} not found in current_map")
                continue
            for downstream_node in current_map[version]['downstream']:
                downstream_nodes.add(downstream_node)
        
        downstream_nodes = list(downstream_nodes)
        
        if not downstream_nodes:
            continue

        downstream_traffic = calculate_required_traffic(len(versions), downstream_nodes)
        upstream_traffic = {u_node: 100 for u_node in versions}

        # ILP로 up/down 간의 트래픽 최적화
        flow_dict, min_latency = distribute_traffic_ilp(current_map, downstream_traffic, upstream_traffic, edge_weights, version_node_map)

        #서비스내 전체 합을 구해야함
        global_min_latnecy = global_min_latnecy + min_latency
        for u_node in flow_dict:
            for d_node, flow in flow_dict[u_node].items():
                if flow > 0:
                    source_service, source_version = None, None
                    dest_service, dest_version = None, None

                    for service, versions in service_versions.items():
                        if u_node in versions:
                            source_service = service
                            source_version = u_node
                        if d_node in versions:
                            dest_service = service
                            dest_version = d_node

                    if source_service and dest_service:
                        service_routes.append((source_service, source_version, dest_service, dest_version, int(flow)))

    return service_routes, service_versions, global_min_latnecy

def calculate_fitness(individual, graph_map, filtered_sorted_paths_with_durations, apps_v1, namespace, v1, dag):
    temp_map = copy.deepcopy(graph_map)
    temp_map = remove_edges(temp_map, individual)

    # 공정한지 확인
    is_fair = True
    for edge in individual:
        source_service = get_service_by_version(apps_v1, namespace, edge[0])
        destination_service = get_service_by_version(apps_v1, namespace, edge[1])
        downstream_traffic, upstream_traffic = get_traffic_requirements(temp_map, source_service, destination_service)
        is_fair = check_fair_distribution(temp_map, downstream_traffic, upstream_traffic)
        if not is_fair:
            return temp_map, [], {}, 1e10  # 매우 큰 값을 반환하여 해당 개체를 선택하지 않도록 함

    # ILP 문제를 풀어 트래픽 분배 및 목적 함수 값을 계산
    service_routes, service_versions, objective_value = distribute_traffic_and_create_service_routes(temp_map, v1, namespace, dag)
    #print('objective_value', objective_value)
    #print('individual', individual)
    return temp_map, service_routes, service_versions, objective_value


def select_remove_edges_genetic(graph_map, filtered_sorted_paths_with_durations, apps_v1, namespace, v1, dag, population_size=300, generations=100, mutation_rate=0.04):
    edges_to_remove_candidate = defaultdict(int)

    for path, _ in filtered_sorted_paths_with_durations:
        for i in range(len(path) - 1):
            edges_to_remove_candidate[(path[i], path[i + 1])] += 1

    all_edges = list(edges_to_remove_candidate.keys())
    population = generate_initial_population(all_edges, population_size, dag)

    best_individual = None
    best_fitness = float('inf')
    best_service_routes = None
    best_service_versions = None
    best_map = None
    same_fitness_counter = 0
    max_no_improvement_generations = 10

    for generation in range(generations):
        print(f"Generation {generation + 1}/{generations}")
        
        # Calculate fitness for all individuals in the population
        population_fitness = []
        for individual in population:
            temp_map, service_routes, service_versions, objective_value = calculate_fitness(individual, graph_map, filtered_sorted_paths_with_durations, apps_v1, namespace, v1, dag)
            population_fitness.append((individual, (temp_map, service_routes, service_versions, objective_value)))
        
        population_fitness.sort(key=lambda x: x[1][3])  # Sorting based on objective_value
        
        # Elitism
        next_generation = [population_fitness[0][0]]

        while len(next_generation) < population_size:
            parent1, parent2 = random.choices(population_fitness[:population_size//2], k=2)
            child1, child2 = crossover(parent1[0], parent2[0])
            next_generation.extend([mutate(child1, mutation_rate, all_edges), mutate(child2, mutation_rate, all_edges)])

        population = next_generation

        temp_map, current_best_routes, current_best_versions, current_best_fitness = calculate_fitness(population[0], graph_map, filtered_sorted_paths_with_durations, apps_v1, namespace, v1, dag)

        if current_best_fitness < best_fitness:
            best_fitness = current_best_fitness
            best_individual = population[0]
            best_service_routes = current_best_routes
            best_service_versions = current_best_versions
            best_map = temp_map
            same_fitness_counter = 0
            print('best_fitness', best_fitness)
            for best_service_route in best_service_routes:
                print('best_service_route', best_service_route)
        else:
            same_fitness_counter += 1

        print(f"Best fitness in generation {generation + 1}: {best_fitness}")
        
        if same_fitness_counter >= max_no_improvement_generations:
            print(f"No improvement for {max_no_improvement_generations} generations. Increasing mutation rate.")
            mutation_rate = min(mutation_rate * 1.1, 1.0)  # Increase mutation rate up to 100%

        if best_fitness == 0.0:
            print("Stopping early due to achieving perfect fitness.")
            break

        if same_fitness_counter > 15:
            break
        print('---------------------')
    return best_map, best_service_routes, best_service_versions
