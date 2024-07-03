import copy
import pulp
from itertools import combinations
import networkx as nx
from istio.istio_metrics import *
from kube.kube_client import *
from utils.edge_utils import *
from utils.node_utils import *
from utils.traffic_utils import *



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

def distribute_traffic_ilp(network, downstream_traffic, upstream_traffic, node_to_node_durations, version_node_map):
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

    # Objective function: Minimize the total weighted latency
    prob += pulp.lpSum(node_to_node_durations[version_node_map[u_node][0]][version_node_map[d_node][0]] * traffic_vars[(u_node, d_node)] for u_node, d_node in traffic_vars)

    # Solve the problem
    prob.solve()

    # Extract the results
    flow_dict = {u_node: {} for u_node in upstream_traffic}
    for (u_node, d_node), var in traffic_vars.items():
        if var.varValue > 0:
            flow_dict[u_node][d_node] = int(var.varValue)

    # Print the minimum total weighted latency
    print("Minimum total weighted latency:", prob.objective.value())

    return flow_dict


def distribute_traffic_and_create_service_routes(current_map, v1, namespace, prom):
    service_versions = get_service_versions(v1, namespace)
    version_node_map = get_versions_on_nodes(v1, namespace)
    node_to_node_durations = get_probe_icmp_durations(prom)
    service_routes = []

    for service, versions in service_versions.items():    
        downstream_nodes = set()    
        for version in versions:
            if version not in current_map:
                print(f"Warning: {version} not found in current_map")
                continue
            for downstream_node in current_map[version]['downstream']:
                downstream_nodes.add(downstream_node)
        
        downstream_nodes = list(downstream_nodes)
        
        print('service', service)
        print('upstream_nodes,', versions)
        print('downstream_nodes', downstream_nodes)
           
        if not downstream_nodes:
            continue

        # Calculate the traffic requirements
        downstream_traffic = calculate_required_traffic(len(versions), downstream_nodes)
        upstream_traffic = {u_node: 100 for u_node in versions}

        # Distribute traffic using ILP optimization
        flow_dict = distribute_traffic_ilp(current_map, downstream_traffic, upstream_traffic, node_to_node_durations, version_node_map)
        print('flow dict', flow_dict)
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

    print('service_routes', service_routes)
    return service_routes, service_versions



def distribute_traffic_and_create_service_routes_localization(current_map, v1, namespace, prom):
    service_versions = get_service_versions(v1, namespace)
    version_node_map = get_versions_on_nodes(v1, namespace)
    node_to_node_durations = get_probe_icmp_durations(prom)
    service_routes = []

    for service, versions in service_versions.items():
        downstream_nodes = set()
        for version in versions:
            for downstream_node in current_map[version]['downstream']:
                downstream_nodes.add(downstream_node)

        downstream_nodes = list(downstream_nodes)

        print('service', service)
        print('upstream_nodes,', versions)
        print('downstream_nodes', downstream_nodes)

        if not downstream_nodes:
            continue

        # Calculate the traffic requirements
        downstream_traffic = calculate_required_traffic(len(versions), downstream_nodes)
        upstream_traffic = {u_node: 100 for u_node in versions}

        flow_dict = {u_node: {} for u_node in upstream_traffic}

        for u_node in upstream_traffic:
            closest_d_node = None
            min_latency = float('inf')
            for d_node in current_map[u_node]['downstream']:
                latency = node_to_node_durations[version_node_map[u_node][0]][version_node_map[d_node][0]]
                if latency < min_latency:
                    min_latency = latency
                    closest_d_node = d_node

            if closest_d_node:
                flow_dict[u_node][closest_d_node] = upstream_traffic[u_node]

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

    print('service_routes', service_routes)
    return service_routes, service_versions
[]