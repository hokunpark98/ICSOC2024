import matplotlib.pyplot as plt
import numpy as np
import os

# 데이터 입력
data = {
    "local": {
        100: (183, 243),
        200: (206, 328),
        300: (9000, 13000),
        400: (33000, 38000),
        500: (45000, 54000)
    },
    "k8s": {
        100: (71, 109),
        200: (54, 74),
        300: (7000, 10000),
        400: (5000, 32000),
        500: (45000, 54000)
    },
    "proposed": {
        100: (123, 158),
        200: (118, 134),
        300: (4000, 7000),
        400: (12000, 14300),
        500: (35000, 54000)
    }
}
# QPS 리스트
qps = [100, 200, 300, 400, 500]

# 데이터 준비
local_90 = [data["local"][q][0] for q in qps]
local_99 = [data["local"][q][1] for q in qps]
k8s_90 = [data["k8s"][q][0] for q in qps]
k8s_99 = [data["k8s"][q][1] for q in qps]
proposed_90 = [data["proposed"][q][0] for q in qps]
proposed_99 = [data["proposed"][q][1] for q in qps]

# 결과 저장 경로
output_dir = '/home/dnc/master/paper2024/result'
os.makedirs(output_dir, exist_ok=True)

# 그래프 그리기 - 90% Latency
plt.figure(figsize=(14, 7))
bar_width = 0.25
index = np.arange(len(qps))

plt.bar(index, local_90, bar_width, label='Local 90%')
plt.bar(index + bar_width, k8s_90, bar_width, label='K8s 90%')
plt.bar(index + bar_width * 2, proposed_90, bar_width, label='Proposed 90%')

plt.xlabel('QPS')
plt.ylabel('Latency (ms)')
plt.title('90% Latency Comparison')
plt.xticks(index + bar_width, qps)
plt.legend()
plt.grid(True)

plt.tight_layout()
plt.savefig(os.path.join(output_dir, 'latency_comparison_90.png'))  # Save the plot as a PNG file

# 그래프 그리기 - 99% Latency
plt.figure(figsize=(14, 7))
bar_width = 0.25
index = np.arange(len(qps))

plt.bar(index, local_99, bar_width, label='Local 99%')
plt.bar(index + bar_width, k8s_99, bar_width, label='K8s 99%')
plt.bar(index + bar_width * 2, proposed_99, bar_width, label='Proposed 99%')

plt.xlabel('QPS')
plt.ylabel('Latency (ms)')
plt.title('99% Latency Comparison')
plt.xticks(index + bar_width, qps)
plt.legend()
plt.grid(True)

plt.tight_layout()
plt.savefig(os.path.join(output_dir, 'latency_comparison_99.png'))  # Save the plot as a PNG file
