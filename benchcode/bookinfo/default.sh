#!/bin/bash

# Define the arguments for the paper script
paper_arg1="bookinfo"
paper_arg2="http://10.108.230.9:8080"
paper_arg3="default"
paper_args=("$paper_arg1" "$paper_arg2")
  
# Define the path for the deployment YAML files
path="/home/dnc/master/bookinfoBench/deployment_placement_x"
#path="/home/dnc/master/customBench/yaml/deployment2" #기본 스케줄러가 알아서 배치

# QPS 값 목록
qps_values=(10 20 30 40 50)

# Number of repetitions
repetitions=10


echo "Deleting existing deployments..."
kubectl delete -Rf $path
sleep 60

# 기존에 있던 Destination Rules와 Virtual Services 삭제
echo "Deleting existing virtual services..."
kubectl delete vs -n $paper_arg1 --all
kubectl delete dr -n $paper_arg1 --all
sleep 10


echo "Creating new deployments..."
kubectl create -Rf $path
sleep 60
wrk2 -t4 -c10 -d60s -R50 --latency http://10.108.73.23:9080/productpage

for ((i=1; i<=repetitions; i++)); do
    result_dir="/home/dnc/master/paper2024/result/bookinfo/default/${paper_arg3}_${i}"

    # Create the directory if it doesn't exist
    mkdir -p "$result_dir"
    

    for QPS in "${qps_values[@]}"; do
        echo "Deleting existing virtual services..."
        kubectl delete vs -n $paper_arg1 --all
        kubectl delete dr -n $paper_arg1 --all

        echo "Running first wrk2 load test with QPS=$QPS..."
        sleep 10
        wrk2 -t4 -c10 -d180s -R$QPS --latency http://10.108.73.23:9080/productpage  | tee -a "$result_dir/result${QPS}_1.txt"

        # main.py 실행, 인수 전달
        echo "Running main.py with provided arguments..."
        python3 /home/dnc/master/paper2024/code/main.py "${paper_args[@]}"
        sleep 10

        # 두 번째 wrk2 명령어 실행 및 결과 추가 저장
        echo "Running second wrk2 load test with QPS=$QPS..."
        wrk2 -t4 -c10 -d180s -R$QPS --latency http://10.108.73.23:9080/productpage  | tee -a "$result_dir/result${QPS}_2.txt"
    done
done

kubectl delete -Rf $path

echo "Script execution completed."
