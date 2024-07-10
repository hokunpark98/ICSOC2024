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
            downstream_groups = details['downstream']
            for i in range(len(downstream_groups)):
                upstream_traffic[f"{node}_out{i+1}"] += 100

        for i, destination_service in enumerate(downstream_services):
            downstream_nodes = [node for node in nodes if node.startswith(destination_service)]
            required_traffic = calculate_required_traffic(len(upstream_nodes), downstream_nodes)
            for node, traffic in required_traffic.items():
                downstream_traffic[f"{node}_in"] += traffic

    return dict(downstream_traffic), dict(upstream_traffic)

def build_flow_graph(upstream_nodes, downstream_nodes, upstream_traffic, downstream_traffic, edge_weights):
    G = nx.DiGraph()

    for u_node in upstream_nodes:
        for d_node in downstream_nodes:
            in_node = f"{d_node}_in"
            out_node = f"{u_node}_out"
            
            G.add_node(out_node, demand=-upstream_traffic.get(out_node, 100))
            G.add_node(in_node, demand=downstream_traffic.get(in_node, 0))
            G.add_edge(out_node, in_node, weight=edge_weights[(u_node, d_node)], capacity=100)
            #print(f"Edge from {out_node} to {in_node} with weight {edge_weights[(u_node, d_node)]}")

    total_demand = 0
    for node, data in G.nodes(data=True):
        demand = data.get('demand', 0)
        print(f"Node {node} has demand {demand}")
        total_demand += demand

    print(f"Total demand in the graph: {total_demand}")

    return G

def find_optimal_routing(upstream_nodes, downstream_nodes, upstream_traffic, downstream_traffic, edge_weights):
    G = build_flow_graph(upstream_nodes, downstream_nodes, upstream_traffic, downstream_traffic, edge_weights)
    
    if G.number_of_nodes() == 0:
        return {}

    flow_dict = nx.min_cost_flow(G)
    
    return flow_dict

def create_service_pairs(services_dict):
    service_pairs = []

    for downstream_service, connections in services_dict.items():
        for upstream_service in connections['upstream']:
            service_pairs.append((upstream_service, downstream_service))

    return service_pairs

def traffic_allocation(v1, prom, namespace, dag):
    services_dict = get_services_relation(prom, namespace)
    service_versions = get_service_versions(v1, namespace)
    version_node_map = get_versions_on_nodes(v1, namespace)
    node_to_node_durations = get_probe_icmp_durations(prom)
    
    service_pairs = create_service_pairs(services_dict)

    aggregated_flow_dict = {}
    for pair in service_pairs:
        print('--------------------')
        print('pair', pair)
        u_service, d_service = pair
        upstream_nodes = [node for node in version_node_map if node.startswith(u_service)]
        downstream_nodes = [node for node in version_node_map if node.startswith(d_service)]
        
        if not upstream_nodes or not downstream_nodes:
            print(f"Warning: No nodes found for service pair {pair}")
            continue

        edge_weights = {(u_node, d_node): int(node_to_node_durations[version_node_map[u_node][0]][version_node_map[d_node][0]]) 
                        for u_node in upstream_nodes for d_node in downstream_nodes}

        nodes = upstream_nodes + downstream_nodes
        downstream_traffic, upstream_traffic = get_traffic_requirements(nodes, services_dict)
        
        flow_dict = find_optimal_routing(upstream_nodes, downstream_nodes, upstream_traffic, downstream_traffic, edge_weights)
        
        # Aggregate the flow_dict results
        for u_key in flow_dict:
            if u_key not in aggregated_flow_dict:
                aggregated_flow_dict[u_key] = {}
            for d_key, flow in flow_dict[u_key].items():
                if d_key not in aggregated_flow_dict[u_key]:
                    aggregated_flow_dict[u_key][d_key] = 0
                aggregated_flow_dict[u_key][d_key] += flow
        print('--------------------')

    service_routes = []
    for u_node in aggregated_flow_dict:
        for d_node, flow in aggregated_flow_dict[u_node].items():
            if flow > 0:
                u_node_base = u_node.split("_out")[0]
                d_node_base = d_node.split("_in")[0]
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

    print(service_routes)
    return service_routes, service_versions
