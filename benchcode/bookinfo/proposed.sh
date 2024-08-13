#!/bin/bash

# Define the arguments for the paper script
paper_arg1="bookinfo"
paper_arg2="http://10.108.230.9:8080"
paper_arg3="proposed"
paper_args=("$paper_arg1" "$paper_arg2")
  
# Define the path for the deployment YAML files
path="/home/dnc/master/bookinfoBench/deployment"

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
sleep 10
echo "Running main.py with provided arguments..."
python3 /home/dnc/master/paper2024/code/main.py "${paper_args[@]}"
sleep 30


for ((i=1; i<=repetitions; i++)); do
    result_dir="/home/dnc/master/paper2024/result/bookinfo/proposed/${paper_arg3}_${i}"
    mkdir -p "$result_dir"

    for QPS in "${qps_values[@]}"; do
        echo "Running second wrk2 load test with QPS=$QPS..."
        sleep 10         
        wrk2 -t4 -c10 -d180s -R$QPS --latency http://10.108.73.23:9080/productpage  | tee -a "$result_dir/result${QPS}.txt"
    done
done

kubectl delete -Rf $path

echo "Script execution completed."
