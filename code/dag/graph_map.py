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
        for node in upstream_nodes:
            upstream_traffic[node] += 100
        
        for destination_service in downstream_services:
            downstream_nodes = [node for node in nodes if node.startswith(destination_service)]
            required_traffic = calculate_required_traffic(len(upstream_nodes), downstream_nodes)
            for node, traffic in required_traffic.items():
                downstream_traffic[node] += traffic
    
    return dict(downstream_traffic), dict(upstream_traffic)

def build_flow_graph(graph_map, upstream_traffic, downstream_traffic, edge_weights):
    '''
    in: 받아야하는거
    out: 보낼거
    '''
    G = nx.DiGraph()
    #print('upstream_traffic', upstream_traffic)
    #print('downstream', downstream_traffic)
    for node in graph_map:
        in_node = f"{node}_in"
        out_node = f"{node}_out"
        G.add_node(in_node, demand=downstream_traffic.get(node, 0))
        G.add_node(out_node, demand=-upstream_traffic.get(node, 0))
        G.add_edge(in_node, out_node, weight=0, capacity=100)

    
    # 중간 노드들의 간선 설정
    for u_node in graph_map:
        u_out_node = f"{u_node}_out"
        for d_node in graph_map[u_node]['downstream']:
            d_in_node = f"{d_node}_in"
            G.add_edge(u_out_node, d_in_node, weight=edge_weights[(u_node, d_node)], capacity=100)
            #print(f"Edge from {u_out_node} to {d_in_node}")
    
    # 각 노드의 수요 출력
    '''
    total_demand = 0
    for node, data in G.nodes(data=True):
        demand = data['demand']
        print(f"Node {node} has demand {demand}")
        total_demand += demand
    
    print(f"Total demand in the graph: {total_demand}")
    '''
    
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
    #print('findOptimal')
    
    return flow_dict

def traffic_allocation(graph_map, v1, prom, namespace, dag):
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

    #print('edge_weights', edge_weights)
    nodes = list(graph_map.keys())
    downstream_traffic, upstream_traffic = get_traffic_requirements(nodes, services_dict)
    
    flow_dict = find_optimal_routing(graph_map, upstream_traffic, downstream_traffic, edge_weights)

    service_routes = []

    for u_node in flow_dict:
        for d_node, flow in flow_dict[u_node].items():
            if flow > 0:
                u_node_base = u_node.replace("_out", "")
                d_node_base = d_node.replace("_in", "")
                source_service, source_version = None, None
                dest_service, dest_version = None, None

                for service, versions in service_versions.items():
                    if u_node_base in versions:
                        source_service = service
                        source_version = u_node_base
                    if d_node_base in versions:
                        dest_service = service
                        dest_version = d_node_base

                if source_service and dest_service:
                    service_routes.append((source_service, source_version, dest_service, dest_version, int(flow)))

    #print('traffic_allocation')
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
