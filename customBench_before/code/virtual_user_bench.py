import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
import json

def send_request(url):
    headers = {"Content-Type": "application/json"}
    start_time = time.time_ns()
    try:
        response = requests.get(url=url, headers=headers)
        end_time = time.time_ns()
        response_time_ns = end_time - start_time

        if response.status_code == 200:
            response_data = response.json()
            if response_data.get('result') == 5:
                return response_time_ns / 1_000_000  # Convert ns to ms
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
    except json.decoder.JSONDecodeError as e:
        print(f"JSON decoding failed: {response.text} caused {e}")
    return None

def simulate_load(user_count):
    url = "http://10.102.46.37:11000/a?value=1"
    response_times = []
    with ThreadPoolExecutor(max_workers=user_count) as executor:
        futures = [executor.submit(send_request, url) for _ in range(user_count)]
        for future in as_completed(futures):
            response_time = future.result()
            if response_time:
                response_times.append(response_time)

    successful_responses = len(response_times)
    if response_times:
        percentile_95 = np.percentile(response_times, 95)  # Already in ms
    else:
        percentile_95 = None
    return successful_responses, percentile_95

def main():
    user_counts = [1, 5, 10, 20, 50]
    results = []
    with open('/home/dnc/master/paper2024/customBench/code/virtual_user_result.txt', 'w') as file:
        for user_count in user_counts:
            successful_responses, percentile_95 = simulate_load(user_count)
            results.append((user_count, successful_responses, percentile_95))
            result_str = f"{user_count} users: {percentile_95:.0f} ms\n"
            print(result_str)
            file.write(result_str)

if __name__ == "__main__":
    main()
