from collections import Counter

def get_node_resources(node):
    allocatable = node.status.allocatable
    return {
        "cpu": allocatable["cpu"],
        "memory": allocatable["memory"]
    }

def find_replacement_nodes(replace_node_list, k8s_client, remove_edge_list):
    replacement_nodes = {}
    node_resources = {}

    nodes = k8s_client.v1.list_node().items
    for node in nodes:
        node_name = node.metadata.name
        allocatable = node.status.allocatable
        cpu_value = int(allocatable["cpu"].rstrip('m')) if 'm' in allocatable["cpu"] else int(float(allocatable["cpu"]) * 1000)
        memory_value = int(allocatable["memory"].rstrip('Ki')) // 1024 if 'Ki' in allocatable["memory"] else int(allocatable["memory"].rstrip('Mi'))

        node_resources[node_name] = {
            "cpu": cpu_value,
            "memory": memory_value
        }

    node_frequency = Counter(node for edge in remove_edge_list for node in edge)
    replace_node_list.sort(key=lambda x: node_frequency.get(x, 0), reverse=True)

    for node in replace_node_list:
        app_label, _ = k8s_client.get_labels_from_deployment(node)
        if not app_label:
            continue

        candidate_versions = []
        versions = k8s_client.get_versions_for_service(app_label)
        for version in versions:
            pods = k8s_client.v1.list_namespaced_pod(k8s_client.namespace, label_selector=f'app={app_label},version={version}').items
            if not pods:
                continue
            pod_name = pods[0].metadata.name
            node_for_pod = k8s_client.get_node_for_pod(pod_name)
            if node_for_pod != node:
                candidate_versions.append((version, node_for_pod))

        for version, node_name in candidate_versions:
            resources = node_resources[node_name]
            deployment_resources = k8s_client.get_deployment_resources(node, k8s_client.namespace, k8s_client)

            if (resources["cpu"] >= deployment_resources["cpu"]) and (resources["memory"] >= deployment_resources["memory"]):
                node_resources[node_name]["cpu"] -= deployment_resources["cpu"]
                node_resources[node_name]["memory"] -= deployment_resources["memory"]
                replacement_nodes[node] = (version, node_name)
                break

    return replacement_nodes
