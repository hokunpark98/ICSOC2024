#!/bin/bash

# Define the arguments for the paper script

paper_arg1="paper2"
paper_arg2="http://10.108.230.9:8080"
paper_arg3="local"
paper_args=("$paper_arg1" "$paper_arg2" "$paper_arg3")
clusterIP="10.102.123.170"
  
# Define the path for the deployment YAML files
path="/home/dnc/master/customBench/yaml/deployment"
#path="/home/dnc/master/customBench/yaml/deployment2" #기본 스케줄러가 알아서 배치

# QPS 값 목록
 qps_values=(10 50 100 150 200)

for QPS in "${qps_values[@]}"; do
    # 기존의 Deployment 삭제 및 재생성
    echo "Deleting existing deployments..."
    kubectl delete -Rf $path
    sleep 10

    echo "Creating new deployments..."
    kubectl create -Rf $path
    sleep 30

    # 기존에 있던 Destination Rules와 Virtual Services 삭제
    echo "Deleting existing virtual services..."
    kubectl delete vs -n $paper_arg1 --all
    
    # 첫 번째 wrk2 명령어 실행 및 결과 추가 저장
    echo "Running first wrk2 load test with QPS=$QPS..."
    wrk2 -t2 -c10 -d300s -R$QPS --latency "http://$clusterIP:11000/a?value=1" -s /home/dnc/master/paper2024/benchcode/load_test.lua | tee -a /home/dnc/master/paper2024/result/$paper_arg3/result${QPS}_1.txt

    # main.py 실행, 인수 전달
    echo "Running main.py with provided arguments..."
    python3 /home/dnc/master/paper2024/code/main.py "${paper_args[@]}"
    sleep 10

    # 두 번째 wrk2 명령어 실행 및 결과 추가 저장
    echo "Running second wrk2 load test with QPS=$QPS..."
    wrk2 -t2 -c10 -d300s -R$QPS --latency "http://$clusterIP:11000/a?value=1" -s /home/dnc/master/paper2024/benchcode/load_test.lua | tee -a /home/dnc/master/paper2024/result/$paper_arg3/result${QPS}_2.txt
done

echo "Script execution completed."
