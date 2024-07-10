#!/bin/bash

# Define the arguments for the paper script
paper_arg1="bookinfo"
paper_arg2="http://10.108.230.9:8080"
paper_arg3="proposed"
paper_args=("$paper_arg1" "$paper_arg2")
  
# Define the path for the deployment YAML files
path="/home/dnc/master/bookinfoBench/deployment"
#path="/home/dnc/master/customBench/yaml/deployment2" #기본 스케줄러가 알아서 배치

# QPS 값 목록
qps_values=(10 30 50 80 100 150)

# Number of repetitions
repetitions=2

for ((i=1; i<=repetitions; i++)); do
    result_dir="/home/dnc/master/paper2024/result/bookinfo/proposed/${paper_arg3}_${i}"

    # Create the directory if it doesn't exist
    mkdir -p "$result_dir"

    for QPS in "${qps_values[@]}"; do
        # 기존의 Deployment 삭제 및 재생성
        echo "Deleting existing deployments..."
        kubectl delete -Rf $path
        sleep 10

        # 기존에 있던 Destination Rules와 Virtual Services 삭제
        echo "Deleting existing virtual services..."
        kubectl delete vs -n $paper_arg1 --all
        kubectl delete dr -n $paper_arg1 --all

        echo "Creating new deployments..."
        kubectl create -Rf $path
        sleep 30
        
        # 첫 번째 wrk2 명령어 실행 및 결과 추가 저장
        echo "Running first wrk2 load test with QPS=$QPS..."
        # 캐싱으로 인한 성능 향상 제거
        wrk2 -t2 -c10 -d60s -R$QPS --latency http://10.97.31.177:9080/productpage        
        wrk2 -t2 -c10 -d120s -R$QPS --latency http://10.97.31.177:9080/productpage  | tee -a "$result_dir/result${QPS}_1.txt"

        # main.py 실행, 인수 전달
        echo "Running main.py with provided arguments..."
        python3 /home/dnc/master/paper2024/code/main.py "${paper_args[@]}"
        sleep 10

        # 두 번째 wrk2 명령어 실행 및 결과 추가 저장
        echo "Running second wrk2 load test with QPS=$QPS..."
        # 캐싱으로 인한 성능 향상 제거
        wrk2 -t2 -c10 -d60s -R$QPS --latency http://10.97.31.177:9080/productpage          
        wrk2 -t2 -c10 -d120s -R$QPS --latency http://10.97.31.177:9080/productpage  | tee -a "$result_dir/result${QPS}_2.txt"
    done
done

kubectl delete -Rf $path

echo "Script execution completed."
