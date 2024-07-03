from collections import defaultdict

def filter_edges(remove_edge_list, replace_node_list):
    return [
        edge for edge in remove_edge_list
        if edge[0] not in replace_node_list and edge[1] not in replace_node_list
    ]

def print_paths(paths, title):
    print(f"{title}:")
    for path, total_duration in paths:
        print("Path:", " -> ".join(path), "Total Duration:", total_duration)

def print_edges(edges, title):
    print(f"{title}:")
    for edge in edges:
        print(f"Edge: {edge}")

