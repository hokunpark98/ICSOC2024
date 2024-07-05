import argparse
import subprocess
from kubernetes import client, config
import json
from collections import defaultdict
from dag.DAG import *
from dag.graph_map import *
from istio.istio_metrics import *
from kube.kube_client import *
from utils.edge_utils import *

prometheus_url = "http://10.108.230.9:8080"
config.load_kube_config()
v1 = client.CoreV1Api()
prom = connect_to_prometheus(prometheus_url)


def read_json(file_path):
    with open(file_path, 'r') as file:
        data = json.load(file)
    return data


def calculate_average_replicas(services):
    total_replicas = sum(service['replica'] for service in services)
    average_replicas = total_replicas // len(services)  # 소수점 버림
    return average_replicas

def distribute_to_groups_round_robin(services, average_replicas):
    groups = [[] for _ in range(average_replicas)]
    service_counters = defaultdict(int)

    for service in services:
        group_index = 0  # 다른 서비스로 넘어가면 인덱스를 초기화
        replicas_remaining = service['replica']
        
        while replicas_remaining > 0:
            service_counters[service['service-name']] += 1
            groups[group_index].append({
                'service-name': service['service-name'],
                'id': service_counters[service['service-name']],
                'required_CPU': service['required_CPU'],
                'required_MEM': service['required_MEM'],
                'path': service['path']
            })
            replicas_remaining -= 1
            group_index = (group_index + 1) % average_replicas
    
    return groups


def calculate_total_resources_for_groups(groups):
    total_resources = []
    for group in groups:
        total_cpu = sum(service['required_CPU'] for service in group)
        total_mem = sum(service['required_MEM'] for service in group)
        total_resources.append({
            'total_CPU': total_cpu,
            'total_MEM': total_mem
        })
    return total_resources

def build_latency_matrix(nodes, durations):
    matrix = []
    for node in nodes:
        row = []
        for target_node in nodes:
            if node == target_node:
                row.append(0)
            else:
                row.append(durations.get(node, {}).get(target_node, float('inf')))
        matrix.append(row)
    return matrix

def assign_workers_to_groups(groups, nodes, latency_matrix):
    total_resources = calculate_total_resources_for_groups(groups)
    node_resources = {node: get_allocatable_resources(v1, node) for node in nodes}
    print('node_resources', node_resources)

    assignments = [-1] * len(groups)
    node_usage = {node: {"cpu": 0, "memory": 0} for node in nodes}

    def can_assign(group_resources, node):
        available_cpu = node_resources[node]['available_cpu'] - node_usage[node]["cpu"]
        available_memory = node_resources[node]['available_memory'] - node_usage[node]["memory"]
        return (group_resources['total_CPU'] <= available_cpu and
                group_resources['total_MEM'] <= available_memory)

    best_combination = None
    min_total_latency = float('inf')

    # 그룹[0]을 배치할 수 있는 후보 노드를 찾기
    for node in nodes:
        if can_assign(total_resources[0], node):
            # 후보 노드에 대해 임시 할당 및 사용량 업데이트
            temp_assignments = [-1] * len(groups)
            temp_node_usage = {k: v.copy() for k, v in node_usage.items()}
            used_nodes = set()

            temp_assignments[0] = node
            temp_node_usage[node]["cpu"] += total_resources[0]['total_CPU']
            temp_node_usage[node]["memory"] += total_resources[0]['total_MEM']
            used_nodes.add(node)

            total_latency = 0

            # 나머지 그룹을 그리디 방식으로 배치
            for group_index in range(1, len(groups)):
                best_node = None
                best_latency = float('inf')
                
                for temp_node in nodes:
                    if temp_node not in used_nodes and can_assign(total_resources[group_index], temp_node):
                        current_latency = latency_matrix[nodes.index(temp_assignments[0])][nodes.index(temp_node)]
                        if current_latency < best_latency:
                            best_latency = current_latency
                            best_node = temp_node
                
                if best_node is not None:
                    temp_assignments[group_index] = best_node
                    temp_node_usage[best_node]["cpu"] += total_resources[group_index]['total_CPU']
                    temp_node_usage[best_node]["memory"] += total_resources[group_index]['total_MEM']
                    total_latency += best_latency
                    used_nodes.add(best_node)
            
            # 최적의 조합을 찾기
            if total_latency < min_total_latency:
                min_total_latency = total_latency
                best_combination = temp_assignments
    
    # 최적의 할당을 실제 할당에 반영
    if best_combination is not None:
        assignments = best_combination

    return assignments

def update_deployment_files(groups):
    for group in groups:
        for service in group:
            worker = service['worker']
            version = f"{service['service-name']}{service['id']}"
            path = service['path']
            
            with open(path, 'r') as file:
                deployment = file.read()
            
            # 찾아서 대체하는 부분 수정
            deployment_lines = deployment.split('\n')
            for i in range(len(deployment_lines)):
                if f'version: {version}' in deployment_lines[i]:
                    for j in range(i, len(deployment_lines)):
                        if 'values:' in deployment_lines[j]:
                            if deployment_lines[j+1].strip().startswith('-'):
                                deployment_lines[j+1] = f'                - {worker}'
                            break
                    break
            
            updated_deployment = '\n'.join(deployment_lines)
            
            with open(path, 'w') as file:
                file.write(updated_deployment)

def calculate_total_resources(groups):
    total_resources = []
    for group in groups:
        total_cpu = 0
        total_mem = 0
        worker = None
        for service in group:
            total_cpu += service['required_CPU']
            total_mem += service['required_MEM']
            worker = service['worker']
        total_resources.append({
            'total_CPU': total_cpu,
            'total_MEM': total_mem,
            'worker': worker
        })
    return total_resources

def apply_deployments(data):
    for service in data['services']:
        path = service['path']

        try:
            subprocess.run(["kubectl", "create", "-f", path], check=True)
            print(f"Applied deployment: {path}")
        except subprocess.CalledProcessError as e:
            print(f"Error applying deployment {path}: {e}")
    

def main(file_path):
    data = read_json(file_path)
    services = data['services']
    
    average_replicas = calculate_average_replicas(services)
    print(f"Average Replicas: {average_replicas}")
    
    groups = distribute_to_groups_round_robin(services, average_replicas)
    for group in groups:
        print(group)
        print('---------')
    
    nodes = ['worker1', 'worker2', 'worker3', 'worker4']
    durations = get_probe_icmp_durations(prom)
    print('durations', durations)
    latency_matrix = build_latency_matrix(nodes, durations)
    
    worker_assignments = assign_workers_to_groups(groups, nodes, latency_matrix)
    print('worker_assignments', worker_assignments)
    for idx, group in enumerate(groups):
        for service in group:
            service['worker'] = worker_assignments[idx]
    
    
    update_deployment_files(groups)
    
    total_resources = calculate_total_resources(groups)
    
    for idx, resources in enumerate(total_resources):
        print(f"Group {idx+1}: {resources}")

    apply_deployments(data)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Process the deployment configuration file.')
    parser.add_argument('file_path', type=str, help='The path to the JSON configuration file.')
    args = parser.parse_args()
    main(args.file_path)
