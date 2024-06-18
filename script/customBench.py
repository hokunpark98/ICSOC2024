import subprocess
import time
import requests
import json
import argparse

def manage_kubernetes_deployment(action, file_path):
    try:
        print(f"{action.capitalize()} Kubernetes deployment from: {file_path}")
        subprocess.run(["kubectl", action, "-f", file_path], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Kubernetes {action} failed with error: {e}")

def run_script(script_path, args, wait_time=None, timeout=1000):
    try:
        print(f"Running script: {script_path} with arguments: {args}")
        result = subprocess.run(
            ["python3", script_path] + args, 
            check=True, 
            capture_output=True, 
            text=True, 
            timeout=timeout
        )
        print(result.stdout)
        if wait_time:
            print(f"Waiting for {wait_time} seconds...")
            time.sleep(wait_time)
    except subprocess.CalledProcessError as e:
        print(f"Script {script_path} failed with error: {e}")
    except subprocess.TimeoutExpired:
        print(f"Script {script_path} timed out after {timeout} seconds")

def delete_kubernetes_resources():
    try:
        print("Deleting virtual services in namespace paper2...")
        subprocess.run(["kubectl", "delete", "vs", "-n", "paper2", "--all"], check=True)
        print("Deleting destination rules in namespace paper2...")
        subprocess.run(["kubectl", "delete", "dr", "-n", "paper2", "--all"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Failed to delete resources with error: {e}")
        with open('/home/dnc/master/paper2024/result/virtual_user_result.txt', 'a') as file:
            file.write(f"Failed to delete resources with error: {e}\n")

def log_message(message):
    print(message)
    with open('/home/dnc/master/paper2024/result/virtual_user_result.txt', 'a') as file:
        file.write(message + "\n")

def main():
    kubernetes_custom_bench_deployment = "/home/dnc/master/customBench/yaml/deployment"
    kubernetes_traffic_yaml = "/home/dnc/master/paper2024/trafficyaml"
    custom_bench_script = "/home/dnc/master/customBench/code/virtual_user_bench.py"
    paper_script = "/home/dnc/master/paper2024/code/main.py"
    
    # Define the arguments for the custom bench script
    custom_url = "http://10.110.11.106:11000/a?value=1"
    custom_threshold = "250"
    usr = "1"
    custom_args = [custom_url, custom_threshold, usr]
    
    # Define the arguments for the paper script
    paper_arg1 = "paper2"
    paper_arg2 = "http://10.101.177.122:8080"
    paper_arg3 = "250"
    paper_args = [paper_arg1, paper_arg2, paper_arg3]

    for i in range(10):
        # Manage Kubernetes deployments (without deleting services)
        delete_kubernetes_resources()
        manage_kubernetes_deployment("delete", kubernetes_custom_bench_deployment)
        manage_kubernetes_deployment("delete", kubernetes_traffic_yaml)
        manage_kubernetes_deployment("create", kubernetes_custom_bench_deployment)
        
        # Wait for Kubernetes deployment to stabilize
        log_message(f"{i}번째 실험 시작")
        time.sleep(20)

        # Run the first sequence
        log_message("기본 전송")
        run_script(custom_bench_script, custom_args)
        
        # Run the paper script
        log_message("제안 기법 적용_1")
        run_script(paper_script, paper_args, wait_time=60)  # No wait after this script
        time.sleep(60)

        # Run the second sequence
        log_message("제안 기법 적용_1 적용해서 전송한 결과")
        run_script(custom_bench_script, custom_args)

        # Run the paper script
        log_message("제안 기법 적용_2")
        run_script(paper_script, paper_args, wait_time=60)  # No wait after this script
        time.sleep(60)
    
        # Run the second sequence
        log_message("제안 기법 적용_2 적용해서 전송한 결과")
        run_script(custom_bench_script, custom_args)

                # Run the paper script
        log_message("제안 기법 적용_3")
        run_script(paper_script, paper_args, wait_time=60)  # No wait after this script
        time.sleep(60)
    
        # Run the second sequence
        log_message("제안 기법 적용_3 적용해서 전송한 결과")
        run_script(custom_bench_script, custom_args)
        log_message("----------------------------------")


if __name__ == "__main__":
    main()
