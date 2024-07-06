import copy
from collections import defaultdict
import networkx as nx
import pulp
import random
from kube.kube_client import *
from utils.edge_utils import *
from istio.istio_metrics import get_probe_icmp_durations
import cvxpy as cp
import matplotlib.pyplot as plt

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


def get_traffic_requirements(nodes, services_dict):
    upstream_traffic = defaultdict(int)
    downstream_traffic = defaultdict(int)

    for source_service, details in services_dict.items():
        upstream_nodes = [node for node in nodes if node.startswith(source_service)]
        downstream_services = details['downstream']
        if not downstream_services:
            continue

        # Assign traffic to each out node separately
        for node in upstream_nodes:
            downstream_groups = details['downstream']
            for i in range(len(downstream_groups)):
                upstream_traffic[f"{node}_out{i+1}"] += 100

        for i, destination_service in enumerate(downstream_services):
            downstream_nodes = [node for node in nodes if node.startswith(destination_service)]
            required_traffic = calculate_required_traffic(len(upstream_nodes), downstream_nodes)
            for node, traffic in required_traffic.items():
                downstream_traffic[f"{node}_in"] += traffic

    return dict(downstream_traffic), dict(upstream_traffic)




def build_flow_graph(graph_map, upstream_traffic, downstream_traffic, edge_weights):
    G = nx.DiGraph()

    for node in graph_map:
        downstream_groups = graph_map[node]['downstream']
        print('nod', node)
        for i, group in enumerate(downstream_groups):
            print('i, group', i, group)
            out_node = f"{node}_out{i+1}"
            G.add_node(out_node, demand=-upstream_traffic.get(out_node, 0))
            for d_node in group:
                in_node = f"{d_node}_in"
                print('d_node', in_node)
                print(downstream_traffic.get(in_node, 0))
                G.add_node(in_node, demand=downstream_traffic.get(in_node, 0))
            G.add_edge(in_node, out_node, weight=0, capacity=100)

    for u_node in graph_map:
        downstream_groups = graph_map[u_node]['downstream']
        for i, group in enumerate(downstream_groups):
            u_out_node = f"{u_node}_out{i+1}"
            print('u_out_node', u_out_node)
            for d_node in group:
                print('d_node', d_node)
                d_in_node = f"{d_node}_in"
                G.add_edge(u_out_node, d_in_node, weight=edge_weights[(u_node, d_node)], capacity=100)
                print(f"Edge from {u_out_node} to {d_in_node} {edge_weights[(u_node, d_node)]}")


    total_demand = 0
    for node, data in G.nodes(data=True):
        demand = data.get('demand', 0)
        print(f"Node {node} has demand {demand}")
        total_demand += demand

    print(f"Total demand in the graph: {total_demand}")

    return G




def find_optimal_routing(graph_map, upstream_traffic, downstream_traffic, edge_weights, filename='graph.png'):
    G = build_flow_graph(graph_map, upstream_traffic, downstream_traffic, edge_weights)
    
    # 그래프 시각화
    pos = nx.spring_layout(G)
    edge_labels = nx.get_edge_attributes(G, 'weight')
    
    plt.figure(figsize=(12, 8))
    nx.draw(G, pos, with_labels=True, node_size=2000, node_color='lightblue', font_size=10, font_weight='bold')
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels)
    plt.title("Graph Visualization")
    
    # 그래프를 PNG 파일로 저장
    plt.savefig(filename)
    
    flow_dict = nx.min_cost_flow(G)
    
    return flow_dict

def create_graph_map2(service_versions, services_dict):
    graph_map = {}

    # Initialize graph map with empty upstream and downstream lists
    for service, versions in service_versions.items():
        for version in versions:
            graph_map[version] = {'upstream': [], 'downstream': []}

    # Fill in the upstream and downstream connections
    for service, connections in services_dict.items():
        for upstream_service in connections['upstream']:
            for u_version in service_versions[upstream_service]:
                for d_version in service_versions[service]:
                    if d_version not in graph_map:
                        graph_map[d_version] = {'upstream': [], 'downstream': []}
                    if u_version not in graph_map:
                        graph_map[u_version] = {'upstream': [], 'downstream': []}

                    graph_map[d_version]['upstream'].append(u_version)
                    graph_map[u_version]['downstream'].append(d_version)

    # Ensure nested list format for upstream and downstream connections
    for node, connections in graph_map.items():
        # Group downstream connections by their service
        downstream_groups = defaultdict(list)
        for downstream_node in connections['downstream']:
            service_name = downstream_node.split('-')[0]
            downstream_groups[service_name].append(downstream_node)
        
        # Convert to list of lists format
        connections['downstream'] = [group for group in downstream_groups.values()]

        # Ensure upstream connections are also in a nested list format if needed
        if connections['upstream'] and not isinstance(connections['upstream'][0], list):
            connections['upstream'] = [connections['upstream']]

    return graph_map




def traffic_allocation(v1, prom, namespace, dag):
    services_dict = get_services_relation(prom, namespace)
    service_versions = get_service_versions(v1, namespace)
    version_node_map = get_versions_on_nodes(v1, namespace)
    node_to_node_durations = get_probe_icmp_durations(prom)
    graph_map = create_graph_map2(service_versions, services_dict)
    #print(services_dict)
    print('-----------------------------')
    print_graph_map(graph_map)

    edge_weights = {}
    for u_node in graph_map:
        for downstream_group in graph_map[u_node]['downstream']:
            for d_node in downstream_group:
                u_version = version_node_map[u_node][0]
                d_version = version_node_map[d_node][0]
                edge_weights[(u_node, d_node)] = int(node_to_node_durations[u_version][d_version])

    nodes = list(graph_map.keys())
    downstream_traffic, upstream_traffic = get_traffic_requirements(nodes, services_dict)
    #print('downstream_traffic', downstream_traffic)
    #print('upstream_traffic', upstream_traffic)
    
    flow_dict = find_optimal_routing(graph_map, upstream_traffic, downstream_traffic, edge_weights)
    #print(flow_dict)
    service_routes = []

    for u_node in flow_dict:
        for d_node, flow in flow_dict[u_node].items():
            #print('u_node d_node flow', u_node, d_node, flow)
            if flow > 0:
                u_node_base = u_node.split("_out")[0]
                d_node_base = d_node.split("_in")[0]
                source_service, source_version = None, None
                dest_service, dest_version = None, None
                #print('u_node_base', u_node_base)
                #print('d_node_base', d_node_base)
                
                for service, versions in service_versions.items():
                    #print('service, versions', service, versions)
                    if u_node_base in versions:
                        source_service = service
                        source_version = u_node_base
                        
                    if d_node_base in versions:
                        dest_service = service
                        dest_version = d_node_base

                if source_service and dest_service:
                    service_routes.append((source_service, source_version, dest_service, dest_version, int(flow)))
                    #print('sdafasdf', (source_service, source_version, dest_service, dest_version, int(flow)))

    print(service_routes)
    return service_routes, service_versions





'''
localizaiton 부분임.
'''

def distribute_traffic_greedy_localization(network, downstream_traffic, upstream_traffic, edge_weights):
    # 초기 변수
    traffic_vars = {}
    for u_node in upstream_traffic:
        for d_node in network[u_node]['downstream']:
            traffic_vars[(u_node, d_node)] = 100 if d_node == sorted(network[u_node]['downstream'], key=lambda d: edge_weights[(u_node, d)])[0] else 0

    # 결과 추출 및 정수형 변환
    flow_dict = {u_node: {} for u_node in upstream_traffic}
    for (u_node, d_node), value in traffic_vars.items():
        flow_dict[u_node][d_node] = int(value) if value > 1e-6 else 0  # 작은 값을 0으로 처리하고 정수형 변환

    return flow_dict

def traffic_allocation_localization(graph_map, v1, prom, namespace, dag):
    services_dict = get_services_relation(prom, namespace)
    service_versions = get_service_versions(v1, namespace)
    version_node_map = get_versions_on_nodes(v1, namespace)
    node_to_node_durations = get_probe_icmp_durations(prom)

    edge_weights = {}
    for u_node in graph_map:
        for d_node in graph_map[u_node]['downstream']:
            u_version = version_node_map[u_node][0]
            d_version = version_node_map[d_node][0]
            edge_weights[(u_node, d_node)] = int(node_to_node_durations[u_version][d_version])
            
    service_routes = []

    for service in services_dict:
        source_service = service
        destination_services = services_dict[service]['downstream']

        if destination_services:
            # downstream 서비스가 여러 개일 수 있으니
            for destination_service in destination_services:
                downstream_traffic, upstream_traffic = get_traffic_requirements(graph_map, source_service, destination_service)

                # 그리디 방식으로 up/down 간의 트래픽 최적화
                flow_dict = distribute_traffic_greedy_localization(graph_map, downstream_traffic, upstream_traffic, edge_weights)
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

    return service_routes, service_versions
