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
        cmd = ["python3", script_path] + args
        print(f"Executing command: {' '.join(cmd)}")  # 추가된 디버깅 출력
        result = subprocess.run(
            cmd, 
            check=True, 
            capture_output=True, 
            text=True, 
            timeout=timeout
        )
        print("Script output:", result.stdout)
        print("Script error:", result.stderr)
        if wait_time:
            print(f"Waiting for {wait_time} seconds...")
            time.sleep(wait_time)
    except subprocess.CalledProcessError as e:
        print(f"Script {script_path} failed with error: {e}")
        print("Error output:", e.stdout)
        print("Error details:", e.stderr)
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
    kubernetes_custom_bench_deployment = "/home/dnc/master/customBench/yaml/deployment2"
    kubernetes_traffic_yaml = "/home/dnc/master/paper2024/trafficyaml"
    custom_bench_script = "/home/dnc/master/customBench/code/virtual_user_bench.py"
    paper_script = "/home/dnc/master/paper2024/repackaging/main.py"
    
    # Define the arguments for the custom bench script
    custom_url = "http://10.110.152.34:11000/a?value=1"
    custom_threshold = "100"
    duration = "180"
    
    # Define the arguments for the paper script
    paper_arg1 = "paper2"
    paper_arg2 = "http://10.101.177.122:8080"

    paper_args = [paper_arg1, paper_arg2, custom_threshold]

    # Run the paper script
    log_message("제안 기법 적용")
    print(f"Executing: python3 {paper_script} {paper_args}")  # 추가된 디버깅 출력
    run_script(paper_script, paper_args, wait_time=10,timeout=10)  
    time.sleep(20)
 
    for i in range(1):
        # Manage Kubernetes deployments (without deleting services)
        delete_kubernetes_resources()
        manage_kubernetes_deployment("delete", kubernetes_custom_bench_deployment)
        manage_kubernetes_deployment("delete", kubernetes_traffic_yaml)
        manage_kubernetes_deployment("create", kubernetes_custom_bench_deployment)
        
        # Wait for Kubernetes deployment to stabilize
        log_message(f"{i}번째 실험 시작")
        time.sleep(10)

        # Run the custom bench script
        log_message("기본 전송(QPS 300)")
        custom_args = [custom_url, custom_threshold, '20', duration]
        run_script(custom_bench_script, custom_args)
        '''
        log_message("기본 전송(QPS 400)")
        custom_args = [custom_url, custom_threshold, '30', duration]
        run_script(custom_bench_script, custom_args)
        
        log_message("기본 전송(QPS 500)")
        custom_args = [custom_url, custom_threshold, '40', duration]
        run_script(custom_bench_script, custom_args)
        
        log_message("기본 전송(QPS 600)")
        custom_args = [custom_url, custom_threshold, '50', duration]
        run_script(custom_bench_script, custom_args)
        
        log_message("기본 전송(QPS 700)")
        custom_args = [custom_url, custom_threshold, '70', duration]
        run_script(custom_bench_script, custom_args)
        '''
        # Run the paper script
        log_message("제안 기법 적용")
        run_script(paper_script, paper_args, timeout=3600)  
        time.sleep(20)

        log_message("제안기법 전송(QPS 300)")
        custom_args = [custom_url, custom_threshold, '20', duration]
        run_script(custom_bench_script, custom_args)
        
        log_message("제안기법 전송(QPS 400)")
        custom_args = [custom_url, custom_threshold, '30', duration]
        run_script(custom_bench_script, custom_args)
        
        log_message("제안기법 전송(QPS 500)")
        custom_args = [custom_url, custom_threshold, '40', duration]
        run_script(custom_bench_script, custom_args)
        
        log_message("제안기법 전송(QPS 600)")
        custom_args = [custom_url, custom_threshold, '50', duration]
        run_script(custom_bench_script, custom_args)
        
        log_message("제안기법 전송(QPS 700)")
        custom_args = [custom_url, custom_threshold, '70', duration]
        run_script(custom_bench_script, custom_args)


if __name__ == "__main__":
    main()
