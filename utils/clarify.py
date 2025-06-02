import json
import os

def classify_complaints(input_file_path, output_directory):
    """
    Classifies complaints from a JSONL file based on 'complaint_type'
    and saves the 'extracted_data' into separate JSONL files.

    Args:
        input_file_path (str): The path to the input JSONL file.
        output_directory (str): The directory where classified JSONL files will be saved.
    """
    if not os.path.exists(output_directory):
        os.makedirs(output_directory)

    classified_data = {}

    try:
        with open(input_file_path, 'r', encoding='utf-8') as infile:
            for line in infile:
                try:
                    record = json.loads(line.strip())
                    if record.get("status") == "success" and "extracted_data" in record:
                        extracted_data = record["extracted_data"]
                        complaint_type = extracted_data.get("complaint_type")

                        if complaint_type:
                            if complaint_type not in classified_data:
                                classified_data[complaint_type] = []
                            classified_data[complaint_type].append(extracted_data)
                        else:
                            print(f"Warning: Record at source_row {record.get('source_row')} has no 'complaint_type' in 'extracted_data'. Skipping.")
                    else:
                        print(f"Warning: Record {record.get('id', 'Unknown ID')} is not status 'success' or missing 'extracted_data'. Skipping.")
                except json.JSONDecodeError:
                    print(f"Warning: Could not decode JSON from line: {line.strip()}. Skipping.")
                except Exception as e:
                    print(f"An unexpected error occurred while processing a line: {e}. Line: {line.strip()}. Skipping.")


        for complaint_type, data_list in classified_data.items():
            output_file_path = os.path.join(output_directory, f"{complaint_type}.jsonl")
            with open(output_file_path, 'w', encoding='utf-8') as outfile:
                for item in data_list:
                    outfile.write(json.dumps(item, ensure_ascii=False) + '\n')
            print(f"Successfully saved {len(data_list)} records to {output_file_path}")

    except FileNotFoundError:
        print(f"Error: Input file not found at {input_file_path}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    input_filename = "data/output.jsonl"

    # --- Configuration ---
    input_jsonl_file = input_filename # Replace with your input file name
    output_dir = "classified_complaints" # Replace with your desired output directory name
    # --- End Configuration ---

    classify_complaints(input_jsonl_file, output_dir)

    print(f"\n--- Content of {output_dir}/其他.jsonl (if created) ---")
    try:
        with open(os.path.join(output_dir, "其他.jsonl"), 'r', encoding='utf-8') as f:
            for line in f:
                print(line.strip())
    except FileNotFoundError:
        print("其他.jsonl not found.")

    print(f"\n--- Content of {output_dir}/虚假宣传.jsonl (if created) ---")
    try:
        with open(os.path.join(output_dir, "虚假宣传.jsonl"), 'r', encoding='utf-8') as f:
            for line in f:
                print(line.strip())
    except FileNotFoundError:
        print("虚假宣传.jsonl not found.")

    print(f"\n--- Content of {output_dir}/产品质量.jsonl (if created) ---")
    try:
        with open(os.path.join(output_dir, "产品质量.jsonl"), 'r', encoding='utf-8') as f:
            for line in f:
                print(line.strip())
    except FileNotFoundError:
        print("产品质量.jsonl not found.")

    print(f"\n--- Content of {output_dir}/物流问题.jsonl (if created) ---")
    try:
        with open(os.path.join(output_dir, "物流问题.jsonl"), 'r', encoding='utf-8') as f:
            for line in f:
                print(line.strip())
    except FileNotFoundError:
        print("物流问题.jsonl not found.")
