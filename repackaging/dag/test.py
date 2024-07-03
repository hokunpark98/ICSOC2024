import cvxpy as cp
import numpy as np

import cvxpy as cp
import numpy as np

def distribute_traffic_ilp(network, downstream_traffic, upstream_traffic, edge_weights):
    # Initialize variables
    traffic_vars = {}
    for u_node in upstream_traffic:
        for d_node in network[u_node]['downstream']:
            traffic_vars[(u_node, d_node)] = cp.Variable(integer=True)

    # Define constraints
    constraints = []

    # Constraint: upstream traffic must sum to 100%
    for u_node in upstream_traffic:
        constraints.append(cp.sum([traffic_vars[(u_node, d_node)] for d_node in network[u_node]['downstream']]) == 100)

    # Constraint: downstream traffic must meet requirements
    for d_node in downstream_traffic:
        constraints.append(
            cp.sum([traffic_vars[(u_node, d_node)] * upstream_traffic[u_node] / 100 for u_node in upstream_traffic if (u_node, d_node) in traffic_vars]) == downstream_traffic[d_node]
        )

    # Constraints: traffic percentages must be between 0 and 100
    for var in traffic_vars.values():
        constraints.append(var >= 0)
        constraints.append(var <= 100)

    # Define the objective function
    objective = cp.Minimize(cp.sum([edge_weights[(u_node, d_node)] * traffic_vars[(u_node, d_node)] * upstream_traffic[u_node] / 100 for u_node, d_node in traffic_vars]))

    # Solve the problem
    problem = cp.Problem(objective, constraints)
    problem.solve()

    # Check if a feasible solution exists
    if problem.status not in [cp.OPTIMAL, cp.OPTIMAL_INACCURATE]:
        return None, float('inf')

    # Extract the results
    flow_dict = {u_node: {} for u_node in upstream_traffic}
    for (u_node, d_node), var in traffic_vars.items():
        value = var.value if var.value > 1e-6 else 0  # Treat small values as zero
        flow_dict[u_node][d_node] = value

    return flow_dict, problem.value

# Example usage with the updated downstream_traffic and upstream_traffic
network = {
    'A1': {'downstream': ['B1', 'B2']},
    'A2': {'downstream': ['B1', 'B2']},
    'A3': {'downstream': ['B1', 'B2']},
    'A4': {'downstream': ['B1', 'B2']}
}

downstream_traffic = {
    'B1': 200,
    'B2': 200
}

upstream_traffic = {
    'A1': 100,
    'A2': 100,
    'A3': 100,
    'A4': 100
}

edge_weights = {
    ('A1', 'B1'): 1,
    ('A1', 'B2'): 8,
    ('A2', 'B1'): 0,
    ('A2', 'B2'): 7,
    ('A3', 'B1'): 3,
    ('A3', 'B2'): 5,
    ('A4', 'B1'): 7,
    ('A4', 'B2'): 0
}

flow_percentage_dict, min_value = distribute_traffic_ilp(network, downstream_traffic, upstream_traffic, edge_weights)

print(f"Flow Percentages: {flow_percentage_dict}")
print(f"Minimum Objective Value: {min_value}")
