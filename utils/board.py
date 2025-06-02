import os
import json

def regroup_complaints(fine_grained_dir, broad_output_dir):
    """
    Regroups fine-grained complaint JSONL files into broader categories.

    Args:
        fine_grained_dir (str): Directory containing the fine-grained classified JSONL files.
        broad_output_dir (str): Directory where the broadly classified JSONL files will be saved.
    """
    if not os.path.exists(broad_output_dir):
        os.makedirs(broad_output_dir)

    # Define the mapping of fine-grained types to the new broad categories.
    # The keys are the new broad category names (and output filenames).
    # The values are lists of the original fine-grained complaint types.
    broad_category_definitions = {
        "1_产品质量与安全": [
            "产品质量", "食品安全", "餐饮卫生问题", "食品添加剂问题", "食品安全问题", "擅自更换"
        ],
        "2_服务体验与履约": [
            "服务未履行义务", "服务履行问题", "服务态度", "服务问题", "不合理医疗建议",
            "服务质量", "服务流程", "服务失误", "服务未按承诺", "装修问题", "服务延迟",
            "快递服务问题", "发货问题", "库存问题", "服务终止或停运"
        ],
        "3_虚假宣传与欺诈": [
            "虚假宣传", "虚假信息", "欺诈行为", "提款跑路", "医疗广告违规", "诚信问题",
            "利用不正当手段获取利益", "诱导消费", "欺诈", "价格欺诈"
        ],
        "4_价格、收费与退款": [
            "退款问题", "不合理收费", "乱收费", "退货退款问题", "电费问题", "费用问题",
            "电费收费", "服务费问题", "药品涨价", "乱扣费", "价格问题", "押金问题",
            "服务收费", "违约金"
        ]
        # All other types will go to "5_其他"
    }

    # Create a reverse map for quick lookup: original_type -> broad_category_name
    original_to_broad_map = {}
    for broad_name, original_types in broad_category_definitions.items():
        for original_type in original_types:
            original_to_broad_map[original_type] = broad_name

    output_file_handles = {}
    records_count = {}

    try:
        if not os.path.isdir(fine_grained_dir):
            print(f"错误：输入目录 '{fine_grained_dir}' 不存在或不是一个目录。")
            return

        for filename in os.listdir(fine_grained_dir):
            if filename.endswith(".jsonl"):
                original_type_name = filename[:-len(".jsonl")] # Extracts "虚假宣传" from "虚假宣传.jsonl"

                # Determine the new broad category
                target_broad_category_name = original_to_broad_map.get(original_type_name, "5_其他")

                if target_broad_category_name not in records_count:
                    records_count[target_broad_category_name] = 0

                # Get or create the file handle for the broad category
                if target_broad_category_name not in output_file_handles:
                    output_file_path = os.path.join(broad_output_dir, f"{target_broad_category_name}.jsonl")
                    output_file_handles[target_broad_category_name] = open(output_file_path, 'w', encoding='utf-8')

                fine_grained_file_path = os.path.join(fine_grained_dir, filename)
                try:
                    with open(fine_grained_file_path, 'r', encoding='utf-8') as infile:
                        for line in infile:
                            # Each line is already a JSON string of extracted_data
                            output_file_handles[target_broad_category_name].write(line)
                            records_count[target_broad_category_name] += 1
                except Exception as e:
                    print(f"处理文件 '{fine_grained_file_path}' 时发生错误: {e}")

        for broad_name, count in records_count.items():
            print(f"成功将 {count} 条记录保存到 {os.path.join(broad_output_dir, f'{broad_name}.jsonl')}")

    except Exception as e:
        print(f"处理过程中发生意外错误: {e}")
    finally:
        for handle in output_file_handles.values():
            if handle:
                handle.close()

if __name__ == "__main__":
    # --- 配置 ---
    # 这是您之前脚本生成的、包含细分类型JSONL文件的目录
    input_fine_grained_directory = "data/classified_complaints"
    # 这是新脚本输出整合后的大类JSONL文件的目录
    output_broad_directory = "data/broad_classified_complaints"
    # --- 配置结束 ---

    # (可选) 为测试创建一些虚拟的细分文件和目录
    # 如果您已经运行了上一个脚本并生成了 'classified_complaints' 目录及其文件，
    # 您可以注释掉或删除下面的虚拟文件创建部分。
    if not os.path.exists(input_fine_grained_directory):
        os.makedirs(input_fine_grained_directory)
        dummy_fine_grained_files = {
            "产品质量.jsonl": [{"data": "product_good_1"}, {"data": "product_good_2"}],
            "虚假宣传.jsonl": [{"data": "false_ad_1"}],
            "服务态度.jsonl": [{"data": "service_ok_1"}],
            "退款问题.jsonl": [{"data": "refund_1"}],
            "霸王条款.jsonl": [{"data": "unfair_clause_1"}], # Will go to 5_其他
            "其他.jsonl": [{"data": "original_other_1"}] # Original "其他" file, will go to 5_其他
        }
        for fname, data_list in dummy_fine_grained_files.items():
            with open(os.path.join(input_fine_grained_directory, fname), 'w', encoding='utf-8') as f:
                for item in data_list:
                    f.write(json.dumps(item, ensure_ascii=False) + '\n')
        print(f"创建了虚拟输入目录 '{input_fine_grained_directory}' 用于测试。")
    # --- 虚拟文件创建结束 ---

    regroup_complaints(input_fine_grained_directory, output_broad_directory)

    print("\n--- 聚合后的大类文件内容示例 ---")
    for category_file_name in ["1_产品质量与安全.jsonl", "2_服务体验与履约.jsonl", "3_虚假宣传与欺诈.jsonl", "4_价格、收费与退款.jsonl", "5_其他.jsonl"]:
        file_path = os.path.join(output_broad_directory, category_file_name)
        if os.path.exists(file_path):
            print(f"\n--- {file_path} 的内容 ---")
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    for i, line in enumerate(f):
                        if i < 3: # 打印最多3行作为示例
                            print(line.strip())
                        else:
                            break
                    if i >= 3:
                        print("...")
            except Exception as e:
                print(f"读取文件 {file_path} 示例内容时出错: {e}")
        else:
            print(f"\n文件 {file_path} 未创建 (可能该分类下没有记录)。")