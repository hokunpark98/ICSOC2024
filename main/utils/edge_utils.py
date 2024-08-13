from collections import defaultdict

def print_paths(paths, title):
    print(f"{title}:")
    for path, total_duration in paths:
        print("Path:", " -> ".join(path), "Total Duration:", total_duration)

def print_edges(edges, title):
    print(f"{title}:")
    for edge in edges:
        print(f"Edge: {edge}")

