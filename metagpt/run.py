#!/usr/bin/env python3
import subprocess
import time
import os
from datetime import datetime

# Configuration
TOTAL_RUNS = 1
BASE_PROJECT_NAME = "tic_tac_toe_t"
IDEA = " Create a Tic-Tac-Toe game that delivers a complete gaming experience. The game should alternate turns between X and O players while accurately detecting all winning patterns (horizontal, vertical, and diagonal lines) and draw scenarios when the board fills without a winner. Implement validation to prevent players from selecting already occupied cells, and include a reset function that completely clears the board for new games. Add a score tracking system that records and displays each player's wins, losses, and draws. The user interface should provide clear visual or audio feedback indicating current player turns, game outcomes, and important events. If you choose to include an AI opponent, ensure it makes legal moves and offers adjustable difficulty levels for different player experiences. The game should handle boundary cases reliably, particularly when interacting with edge and corner cells, and demonstrate robust error handling for invalid inputs or unexpected interruptions during gameplay."
PARADIGM = "Hierarchy"
COMMAND = "python3 organisation.py"

def main():
    # Create a directory to store logs
    log_dir = "metagpt_runs_logs"
    os.makedirs(log_dir, exist_ok=True)
    
    print(f"Starting {TOTAL_RUNS} runs of {COMMAND} with project name base: {BASE_PROJECT_NAME}")
    print("-" * 80)
    
    for run_num in range(  1
                         , TOTAL_RUNS + 1):
        project_name = f"{BASE_PROJECT_NAME}_{run_num}"
        
        # Format the full command
        full_command = f'{COMMAND} "{IDEA}" "{PARADIGM}" --project-name {project_name}'
        
        # Log start time
        start_time = time.time()
        start_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        print(f"Run #{run_num}/{TOTAL_RUNS} - Starting: {start_datetime}")
        print(f"Command: {full_command}")
        
        # Create a log file for this run
        log_file_path = os.path.join(log_dir, f"{project_name}_log.txt")
        with open(log_file_path, "w") as log_file:
            # Execute the command and capture output
            try:
                process = subprocess.Popen(
                    full_command,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True
                )
                
                # Stream and log the output in real time
                for line in process.stdout:
                    print(line, end='')  # Print to console
                    log_file.write(line)  # Write to log file
                    log_file.flush()      # Ensure output is written immediately
                
                # Wait for the process to complete
                return_code = process.wait()
                
                # Calculate and log the execution time
                end_time = time.time()
                duration = end_time - start_time
                
                completion_message = f"\nRun #{run_num} completed with return code {return_code}"
                duration_message = f"Duration: {duration:.2f} seconds ({duration/60:.2f} minutes)"
                
                print(completion_message)
                print(duration_message)
                print("-" * 80)
                
                log_file.write(completion_message + "\n")
                log_file.write(duration_message + "\n")
                
            except Exception as e:
                error_message = f"\nError during run #{run_num}: {str(e)}"
                print(error_message)
                log_file.write(error_message + "\n")
        
        print(f"Log saved to: {log_file_path}")
        
        # Optional: Add a delay between runs if needed
        if run_num < TOTAL_RUNS:
            delay = 5  # seconds
            print(f"Waiting {delay} seconds before next run...")
            time.sleep(delay)
    
    print("\nAll runs completed!")
    print(f"Logs saved in directory: {os.path.abspath(log_dir)}")

if __name__ == "__main__":
    main()