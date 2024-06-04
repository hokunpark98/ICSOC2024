import requests
import time

# Endpoint and data
url = "http://10.101.244.15:11000/a?value=1"
headers = {"Content-Type": "application/json"}
data = '{"value":1}'
count = 0
# Open the file in write mode
with open('stress.txt', 'w') as file:
    # List to store response times
    response_times = []

    # Make 1000 requests and measure response times
    for _ in range(30000):
        start_time = time.time_ns()
        response = requests.get(url=url)
        end_time = time.time_ns()
        response_time_ns = end_time - start_time
        response_times.append(response_time_ns)
        response = response.json()
        response = response['result']
        
        if response == 5:
            file.write(f"{response_time_ns}\n")
            count = count + 1
                    
        # Write each response time to the file
        
        

    # Calculate average, maximum, and minimum response times
    avg_response_time = sum(response_times) / len(response_times)
    max_response_time = max(response_times)
    min_response_time = min(response_times)

    # Write the summary statistics to the file
    file.write("\n\n")  # Add a newline for separation
    file.write(f"Average Response Time: {avg_response_time} ns\n")
    file.write(f"Maximum Response Time: {max_response_time} ns\n")
    file.write(f"Minimum Response Time: {min_response_time} ns\n")

print("Full results and summary saved to response_times_full_results.txt")
print(count)