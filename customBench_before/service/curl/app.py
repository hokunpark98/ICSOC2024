import requests
import time

# 서비스 URL 설정
url = 'http://service-a:5000/a'

# 응답 시간을 저장할 리스트
response_times = []

# 1000번의 요청을 반복
for i in range(1000):
    start_time = time.time()  # 요청 시작 시간
    response = requests.post(url, json={'value': 1})  # POST 요청
    print('reposne', response)
    end_time = time.time()  # 요청 종료 시간
    response_times.append(end_time - start_time)  # 응답 시간 계산 및 저장

    # 선택적: 각 요청의 응답 시간을 콘솔에 출력
    print(f"Request {i+1}: {response_times[-1]} seconds")

# 응답 시간을 txt 파일로 저장
with open('response_times.txt', 'w') as file:
    for response_time in response_times:
        file.write(f"{response_time}\n")

print("All response times have been saved to response_times.txt")
