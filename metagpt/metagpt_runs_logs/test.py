import re
import os
from datetime import datetime
from statistics import mean

def calculate_token_usage_and_duration(log_content):
    # Regular expressions to extract information
    timestamp_pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})'
    token_pattern = r'prompt_tokens: (\d+), completion_tokens: (\d+)'
    stats_marker = r'==== TOKEN USAGE STATISTICS ===='
    
    # Find position of statistics section
    stats_position = log_content.find(stats_marker)
    if stats_position == -1:
        relevant_content = log_content
    else:
        relevant_content = log_content[:stats_position]
    
    # Extract all timestamps
    timestamps = re.findall(timestamp_pattern, relevant_content)
    
    # Extract all token usages
    token_matches = re.findall(token_pattern, relevant_content)
    
    # Calculate total tokens
    total_prompt_tokens = sum(int(match[0]) for match in token_matches)
    total_completion_tokens = sum(int(match[1]) for match in token_matches)
    total_tokens = total_prompt_tokens + total_completion_tokens
    
    # Calculate duration if timestamps are available
    duration_seconds = None
    if timestamps:
        first_timestamp = datetime.strptime(timestamps[0], '%Y-%m-%d %H:%M:%S.%f')
        last_timestamp = datetime.strptime(timestamps[-1], '%Y-%m-%d %H:%M:%S.%f')
        duration = last_timestamp - first_timestamp
        duration_seconds = duration.total_seconds()
    
    return {
        'prompt_tokens': total_prompt_tokens,
        'completion_tokens': total_completion_tokens,
        'total_tokens': total_tokens,
        'duration_seconds': duration_seconds,
        'duration_formatted': format_duration(duration_seconds) if duration_seconds is not None else "Unknown"
    }

def calculate_average_from_multiple_files(file_pattern, num_files):
    """
    Calculate average token usage and duration from multiple files
    
    Args:
        file_pattern (str): Pattern for the file names (e.g., 'calculator_{}.txt')
        num_files (int): Number of files to process
        
    Returns:
        dict: Average statistics
    """
    all_results = []
    
    for i in range(1, num_files + 1):
        filename = file_pattern.format(i)
        
        # Skip if file doesn't exist
        if not os.path.exists(filename):
            print(f"Warning: File {filename} not found, skipping.")
            continue
            
        try:
            with open(filename, 'r') as f:
                log_content = f.read()
                
            # Calculate token usage and duration for this file
            results = calculate_token_usage_and_duration(log_content)
            all_results.append(results)
            
            print(f"Processed {filename}:")
            print(f"  - Total tokens: {results['total_tokens']}")
            print(f"  - Duration: {results['duration_formatted']}")
            print()
            
        except Exception as e:
            print(f"Error processing {filename}: {str(e)}")
    
    if all_results:
        avg_prompt_tokens = round(mean([r['prompt_tokens'] for r in all_results]))
        avg_completion_tokens = round(mean([r['completion_tokens'] for r in all_results]))
        avg_total_tokens = round(mean([r['total_tokens'] for r in all_results]))
        
        durations = [r['duration_seconds'] for r in all_results if r['duration_seconds'] is not None]
        avg_duration_seconds = mean(durations) if durations else None
        
        return {
            'avg_prompt_tokens': avg_prompt_tokens,
            'avg_completion_tokens': avg_completion_tokens,
            'avg_total_tokens': avg_total_tokens,
            'avg_duration_seconds': avg_duration_seconds,
            'avg_duration_formatted': format_duration(avg_duration_seconds) if avg_duration_seconds is not None else "Unknown",
            'num_files_processed': len(all_results)
        }
    else:
        return {
            'avg_prompt_tokens': 0,
            'avg_completion_tokens': 0,
            'avg_total_tokens': 0,
            'avg_duration_seconds': None,
            'avg_duration_formatted': "Unknown",
            'num_files_processed': 0
        }

def format_duration(seconds):
    """Format duration in seconds to decimal minutes"""
    if seconds is None:
        return "Unknown"
    
    # Convert seconds to minutes with 2 decimal places
    minutes = seconds / 60
    return f"{minutes:.2f} minutes"

# Example usage:
if __name__ == "__main__":
    # Process single file
    if False:  # Set to True to process single file
        with open('log_file.txt', 'r') as f:
            log_content = f.read()
        
        # Calculate token usage and duration
        results = calculate_token_usage_and_duration(log_content)
        
        # Print results
        print(f"Total prompt tokens: {results['prompt_tokens']}")
        print(f"Total completion tokens: {results['completion_tokens']}")
        print(f"Total tokens: {results['total_tokens']}")
        print(f"Total duration: {results['duration_formatted']}")
    
    # Process multiple files
    print("Processing multiple calculator files...")
    file_pattern = "calculator_t_{}_log.txt"  # Format for file names
    num_files = 10  # Number of files to process
    
   
    
    avg_results = calculate_average_from_multiple_files(file_pattern, num_files)
    
    print("\nSummary:")
    print(f"{file_pattern}")
    print(f"Files processed: {avg_results['num_files_processed']} out of {num_files}")
    print(f"Average prompt tokens: {avg_results['avg_prompt_tokens']}")
    print(f"Average completion tokens: {avg_results['avg_completion_tokens']}")
    print(f"Average total tokens: {avg_results['avg_total_tokens']}")
    print(f"Average duration: {avg_results['avg_duration_formatted']}")
    
    # Optionally save the summary to a file
    with open("token_usage_summary.txt", "w") as f:
        f.write(f"Files processed: {avg_results['num_files_processed']} out of {num_files}\n")
        f.write(f"Average prompt tokens: {avg_results['avg_prompt_tokens']}\n")
        f.write(f"Average completion tokens: {avg_results['avg_completion_tokens']}\n")
        f.write(f"Average total tokens: {avg_results['avg_total_tokens']}\n")
        f.write(f"Average duration: {avg_results['avg_duration_formatted']}\n")