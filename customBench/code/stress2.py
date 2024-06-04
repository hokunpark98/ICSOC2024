import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# 요청을 보내는 함수
def send_request(_):
    url = "http://10.109.157.86:11000/a?value=1"
    headers = {"Content-Type": "application/json"}
    start_time = time.time_ns()
    response = requests.get(url=url, headers=headers)
    end_time = time.time_ns()
    response_time_ns = end_time - start_time
    
    if response.json().get('result') == 5:
        return response_time_ns
    else:
        return None

# 메인 코드
def main():
    response_times = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(send_request, _) for _ in range(10000)]
        for future in as_completed(futures):
            response_time = future.result()
            count = len(response_times)
            if response_time:
                response_times.append(response_time)

    # 결과 파일에 쓰기
    count = len(response_times)

    with open('stress2.txt', 'w') as file:
        for response_time in response_times:
            file.write(f"{response_time}\n")

        # 통계 계산
        if response_times:  # 비어 있지 않은 경우에만 계산
            avg_response_time = sum(response_times) / len(response_times)
            max_response_time = max(response_times)
            min_response_time = min(response_times)

            # 통계 요약을 파일에 쓰기
            file.write("\n\n")
            file.write(f"Average Response Time: {avg_response_time} ns\n")
            file.write(f"Maximum Response Time: {max_response_time} ns\n")
            file.write(f"Minimum Response Time: {min_response_time} ns\n")

    print("Full results and summary saved to response_times.txt")
    print(f"Total successful responses with result == 5: {count}")

# 스크립트를 실행할 때만 main() 함수를 호출
if __name__ == "__main__":
    main()
