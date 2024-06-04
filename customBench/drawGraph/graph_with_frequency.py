import numpy as np

# Calculate the 95th percentile of response times
percentile_95 = np.percentile(response_times_ms, 95)

# Plotting the histogram with 95th percentile line
plt.figure(figsize=(10, 6))
plt.hist(response_times_ms, bins=50, color='blue', alpha=0.7, label='Response Times')
plt.axvline(percentile_95, color='red', linestyle='dashed', linewidth=2, label=f'95th Percentile: {percentile_95:.2f} ms')
plt.title('Response Time Distribution in Milliseconds')
plt.xlabel('Response Time (ms)')
plt.ylabel('Frequency')
plt.legend()
plt.grid(True)
plt.show()

# Uncomment below line to execute the plot
# plot_histogram_with_percentile()
