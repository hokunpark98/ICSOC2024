import os
import subprocess

# Define the base directories
base_dir = "/home/dnc/master/paper2024/benchcode"
bookinfo_dir = os.path.join(base_dir, "bookinfo")
custom_dir = os.path.join(base_dir, "custom")

# Define the result directories
bookinfo_result_dir = "/home/dnc/master/paper2024/result/bookinfo"
custom_result_dir = os.path.join(base_dir, "result/custom")

# Create the result directories if they do not exist
os.makedirs(bookinfo_result_dir, exist_ok=True)
os.makedirs(custom_result_dir, exist_ok=True)

def run_single_sh_file(dir_path, result_dir, sh_file):
    sh_file_path = os.path.join(dir_path, sh_file)
    result_file_path = os.path.join(result_dir, f"{os.path.splitext(sh_file)[0]}_result.txt")
    print('result_file_path', result_file_path)
    
    # Run the .sh file and save the output to the result file
    print(f"Running {sh_file_path}...")
    with open(result_file_path, "w") as result_file:
        # Write the script name to the result file
        result_file.write(f"Executing script: {sh_file_path}\n\n")
        # Run the script and capture the output
        subprocess.run(["bash", sh_file_path], stdout=result_file, stderr=subprocess.STDOUT)




bookinfo_sh_files = ["/home/dnc/master/paper2024/benchcode/bookinfo/proposed.sh",
                   "/home/dnc/master/paper2024/benchcode/bookinfo/default.sh",
                   "/home/dnc/master/paper2024/benchcode/bookinfo/localization.sh"]
custom_sh_files = ["/home/dnc/master/paper2024/benchcode/custom/proposed.sh",
                  "/home/dnc/master/paper2024/benchcode/custom/default.sh",
                  "/home/dnc/master/paper2024/benchcode/custom/localization.sh"]
# Run specified .sh files in bookinfo directory
for sh_file in bookinfo_sh_files:
    run_single_sh_file(bookinfo_dir, bookinfo_result_dir, sh_file)

# Run specified .sh files in custom directory
for sh_file in custom_sh_files:
    run_single_sh_file(custom_dir, custom_result_dir, sh_file)

print("All specified scripts executed and results saved.")
