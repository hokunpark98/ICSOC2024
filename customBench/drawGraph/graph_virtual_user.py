import matplotlib.pyplot as plt

# 파일 경로
file_path = '/home/dnc/master/paper2/bench/code/virtual_user_result.txt'

# 데이터를 읽고 파싱
user_counts = []
response_times = []

with open(file_path, 'r') as file:
    for line in file:
        parts = line.split()
        user_count = int(parts[0])
        response_time = int(parts[2])
        user_counts.append(user_count)
        response_times.append(response_time)
        print(user_count)
        print(response_time)

# 데이터를 그래프로 표현
plt.figure(figsize=(10, 6))
plt.plot(user_counts, response_times, marker='o', linestyle='-', color='b')
plt.title('result')
plt.xlabel('Virtual Users')
plt.ylabel('95th Percentile Response Time (ms)')
plt.grid(True)

plt.savefig('/home/dnc/master/paper2/bench/drawGraph/virtual_users.png')
