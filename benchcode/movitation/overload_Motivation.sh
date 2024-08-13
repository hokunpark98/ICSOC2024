#!/bin/bash
  

# QPS 값 목록
qps_values=(10 30 50 100 150 200 250 300)
paper_arg1="paper2"
paper_arg3="motivationOverload"

# Number of repetitions
repetitions=3

for ((i=1; i<=repetitions; i++)); do
    result_dir="/home/dnc/master/paper2024/result/motivation_result/${paper_arg3}_${i}"

    # Create the directory if it doesn't exist
    mkdir -p "$result_dir"

    for QPS in "${qps_values[@]}"; do
        # 기존의 Deployment 삭제 및 재생성
        echo "Deleting existing deployments..."

        # 기존에 있던 Destination Rules와 Virtual Services 삭제
        echo "Deleting existing virtual services..."
        kubectl delete vs -n $paper_arg1 --all
        kubectl delete dr -n $paper_arg1 --all
        sleep 10
        
        # 첫 번째 wrk2 명령어 실행 및 결과 추가 저장
        echo "Running first wrk2 load test with QPS=$QPS..."
        # 캐싱으로 인한 성능 향상 제거
        wrk2 -t4 -c10 -d60s -R$QPS --latency  "http://10.105.92.109:11003/d?value=1"
        sleep 60
        wrk2 -t4 -c10 -d120s -R$QPS --latency "http://10.105.92.109:11003/d?value=1" | tee -a "$result_dir/result${QPS}_1.txt"
    done
done

kubectl delete -Rf $path

echo "Script execution completed."
