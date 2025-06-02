import json
import mysql.connector
import re # 用于正则表达式
import os

# --- START: 配置部分 ---
# MySQL 连接配置
db_connection_config = {
    'user': 'root',         # 替换为你的 MySQL 用户名
    'password': 'jhl12735800', # 替换为你的 MySQL 密码
    'host': '127.0.0.1',    # 通常是本地主机
    # 'database' 键将在连接到特定数据库时添加
    'charset': 'utf8mb4',   # 确保连接使用 utf8mb4
}
MAIN_DB_NAME = 'NLP_DB_BY_TYPE'  # 新的数据库名，或者你可以用旧的，表名会不同
TABLE_NAME_PREFIX = "" # 例如: complaints_type_产品质量

# 明确的列模式定义 (与你之前的脚本一致)
explicit_column_schemas = {
    "time": {"type": "DATE", "comment": '投诉发生的日期, 格式YYYY-MM-DD, 可能为 NULL'},
    "amount": {"type": "DECIMAL(10,2)", "comment": '涉及金额, 可能为 0 或 NULL'},
    "subject": {"type": "VARCHAR(255)", "comment": '投诉方, 可能为 NULL 或具体名称/代称如 "用户", "我"'},
    "object": {"type": "VARCHAR(255)", "comment": '被投诉方'},
    "description": {"type": "TEXT", "comment": '投诉的具体内容描述'},
    "platform": {"type": "VARCHAR(255)", "comment": '投诉发生的平台, 如 淘宝, 微信, 可能为 NULL 或 "未知"'},
    "complaint_type": {"type": "VARCHAR(255)", "comment": '投诉的分类, 如 产品质量, 虚假宣传'} # 在按类型分表后，此列值在该表中应基本一致
}

# 类型推断函数 (与你之前的脚本一致)
def infer_sql_type(key_name, value):
    key_name_lower = key_name.lower()
    if key_name_lower == "time":
        if isinstance(value, str):
            if re.match(r"^\d{4}-\d{2}-\d{2}$", value): return "DATE"
            if re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+Z?)?$", value): return "DATETIME" # 虽然我们主要处理 DATE
    if key_name_lower == "amount":
        if value is None or isinstance(value, (int, float)) or (isinstance(value, str) and value == ""): # 允许空字符串转为NULL
            return "DECIMAL(10, 2) DEFAULT NULL"
    if isinstance(value, bool): return "BOOLEAN"
    elif isinstance(value, int): return "INT"
    elif isinstance(value, float): return "FLOAT"
    elif isinstance(value, str):
        # "complaint_type" 字段已在 explicit_column_schemas 中定义为 VARCHAR(255)
        if key_name_lower in explicit_column_schemas and explicit_column_schemas[key_name_lower]["type"] != "TEXT":
             # 如果已显式定义且不是TEXT，遵循显式定义（这里主要防止它被推断为TEXT）
             pass # 类型由 explicit_column_schemas 控制
        elif key_name_lower in ["description", "content", "text", "details"] or len(value) > 250:
            return "TEXT"
        return "VARCHAR(255)"
    elif value is None: return "VARCHAR(255) DEFAULT NULL" # 对于未在 explicit_schemas 定义的 None 值
    else: return "TEXT DEFAULT NULL" # 其他未知类型默认为 TEXT

def sanitize_tablename_utf8(name_str, max_len=50):
    """
    为MySQL表名净化字符串 (允许UTF-8字符, 用于带反引号的表名)。
    总表名长度限制为64，前缀占一部分，所以 name_str 部分长度需相应限制。
    """
    s = str(name_str)
    # 替换控制字符, 路径分隔符, MySQL非法字符以及我们想标准化的字符 (如空格, 点号) 为下划线
    s = re.sub(r'[\x00-\x1f\\/:*?"<>|\s\.]+', '_', s)
    
    # 截断到最大长度 (为表名的实际部分)
    s = s[:max_len]

    # 移除可能因替换产生的首尾下划线
    s = s.strip('_')
    
    if not s: # 如果净化后为空
        s = 'default_type_name' # 提供一个默认名称
    
    return s
# --- END: 配置部分 ---

def create_and_populate_type_table(db_cursor, db_connection, jsonl_filepath, complaint_type_from_filename):
    """
    为指定投诉类型创建表（如果不存在）并从JSONL文件导入数据。
    """
    sanitized_type_for_table = sanitize_tablename_utf8(complaint_type_from_filename)
    target_table_name = sanitized_type_for_table
    
    print(f"\n--- 开始处理文件: {jsonl_filepath} ---")
    print(f"投诉类型 (来自文件名): '{complaint_type_from_filename}'")
    print(f"目标表: `{MAIN_DB_NAME}`.`{target_table_name}`")

    try:
        # 1. 读取 JSONL 文件第一行以确定表结构 (如果需要推断额外列)
        first_line_content = None
        try:
            with open(jsonl_filepath, 'r', encoding='utf-8') as f:
                first_line_content = f.readline()
        except FileNotFoundError:
            print(f"错误: 文件 '{jsonl_filepath}' 未找到。跳过此文件。")
            return False
        if not first_line_content:
            print(f"错误: 文件 '{jsonl_filepath}' 为空。跳过此文件。")
            return False
        
        first_data_row = None
        try:
            first_data_row = json.loads(first_line_content.strip())
            if not isinstance(first_data_row, dict):
                print(f"错误: 文件 '{jsonl_filepath}' 的第一行不是有效的JSON对象。跳过。")
                return False
        except json.JSONDecodeError as e:
            print(f"错误: 解析文件 '{jsonl_filepath}' 第一行失败: {e}。跳过。")
            return False

        # 2. 构建 CREATE TABLE 语句
        column_definitions_sql = ["`id` INT AUTO_INCREMENT PRIMARY KEY COMMENT '自动递增ID'"]
        schema_column_names_for_insert = [] # 按顺序记录所有将用于INSERT的列名
        
        defined_keys_in_explicit = set()
        # 首先处理 explicit_column_schemas 中定义的列
        for key, schema_info in explicit_column_schemas.items():
            defined_keys_in_explicit.add(key)
            schema_column_names_for_insert.append(key)
            col_name_backticked = f"`{key}`"
            sql_type = schema_info["type"]
            comment_text = schema_info.get("comment", f"Column {key}").replace("'", "''")
            column_definitions_sql.append(f"{col_name_backticked} {sql_type} COMMENT '{comment_text}'")
        
        # 然后处理 first_data_row 中存在但未在 explicit_column_schemas 定义的列
        for key, value in first_data_row.items():
            if key not in defined_keys_in_explicit:
                schema_column_names_for_insert.append(key) # 添加到INSERT列表
                col_name_backticked = f"`{key}`"
                inferred_type = infer_sql_type(key, value)
                fallback_comment = f"自动推断列 (来自JSON: {key})".replace("'", "''")
                column_definitions_sql.append(f"{col_name_backticked} {inferred_type} COMMENT '{fallback_comment}'")
        
        # 表注释使用原始的、未经净化的投诉类型名，更易读
        current_table_comment = ""
        create_table_sql = (
            f"CREATE TABLE IF NOT EXISTS `{target_table_name}` ({', '.join(column_definitions_sql)}) "
            f"ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='{current_table_comment}'"
        )
        try:
            db_cursor.execute(create_table_sql)
        except mysql.connector.Error as e_create:
            print(f"错误: 在数据库 `{MAIN_DB_NAME}` 中创建表 `{target_table_name}` 失败: {e_create}")
            return False

        # 3. 逐行读取 JSONL 文件并插入数据
        with open(jsonl_filepath, 'r', encoding='utf-8') as f:
            lines_processed = 0
            successful_inserts = 0
            failed_lines = 0

            for line_number, line in enumerate(f, 1):
                line_content = line.strip()
                if not line_content: continue
                
                lines_processed += 1
                data = None
                try:
                    data = json.loads(line_content)
                    if not isinstance(data, dict):
                        print(f"警告: 文件 '{jsonl_filepath}' 第 {line_number} 行不是JSON对象，已跳过。")
                        failed_lines += 1; continue

                    # 预处理data中所有key的 "null" 字符串值为 Python None
                    for k, v in data.items():
                        if isinstance(v, str) and v.strip().lower() == 'null':
                            data[k] = None
                    
                    # --- 时间处理 ---
                    raw_time_from_json = data.get("time")
                    time_val_for_db = None # 将存入数据库的 "YYYY-MM-DD" 或 None

                    if isinstance(raw_time_from_json, str):
                        time_str_stripped = raw_time_from_json.strip()
                        if time_str_stripped == "":
                            time_val_for_db = None
                        elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", time_str_stripped): # YYYY-MM-DD
                            time_val_for_db = time_str_stripped
                        elif re.fullmatch(r"\d{4}-\d{2}", time_str_stripped): # YYYY-MM
                            time_val_for_db = f"{time_str_stripped}-01" # 转换为当月第一天
                            # print(f"信息: 第 {line_number} 行时间 '{time_str_stripped}' (YYYY-MM) 将作为 '{time_val_for_db}' 处理入库。")
                        else: # 其他无法识别的字符串格式
                            time_val_for_db = None # 无法转换为有效日期，作为NULL处理
                            print(f"警告: 文件 '{jsonl_filepath}' 第 {line_number} 行时间 '{time_str_stripped}' 格式无效，将作为NULL入库。")
                    elif raw_time_from_json is None: # 本身就是JSON null
                        time_val_for_db = None
                    
                    data['time'] = time_val_for_db # 更新data中的time字段为处理后的值
                    
                    # --- 金额处理: 空字符串转为 None ---
                    if "amount" in data and data["amount"] == "":
                        data["amount"] = None

                    # 准备插入的值
                    values_to_insert = []
                    for col_name in schema_column_names_for_insert:
                        values_to_insert.append(data.get(col_name)) # 使用 .get(col_name) 获取值，若key不存在则为None

                    columns_sql_part = ', '.join([f"`{col}`" for col in schema_column_names_for_insert])
                    placeholders_sql_part = ', '.join(['%s'] * len(schema_column_names_for_insert))
                    sql_insert = f"INSERT INTO `{target_table_name}` ({columns_sql_part}) VALUES ({placeholders_sql_part})"
                    
                    db_cursor.execute(sql_insert, tuple(values_to_insert))
                    successful_inserts += 1

                except json.JSONDecodeError as e_json:
                    print(f"错误: 无法解析文件 '{jsonl_filepath}' 第 {line_number} 行: {e_json}")
                    failed_lines += 1
                except mysql.connector.Error as e_sql:
                    data_preview = str(data)[:200] if data else "N/A" # 增加预览长度
                    print(f"错误: 文件 '{jsonl_filepath}' 第 {line_number} 行数据插入表 `{target_table_name}` 失败: {e_sql} - 数据预览: {data_preview}...")
                    failed_lines += 1
                except Exception as e_generic:
                    data_preview = str(data)[:200] if data else "N/A"
                    print(f"错误: 处理文件 '{jsonl_filepath}' 第 {line_number} 行时未知错误: {e_generic} (类型: {type(e_generic).__name__}) - 数据预览: {data_preview}...")
                    failed_lines += 1
            
            db_connection.commit()
            print(f"文件 '{jsonl_filepath}' 数据导入表 `{target_table_name}` 完成!")
            print(f"  总共处理行数: {lines_processed}")
            print(f"  成功插入行数: {successful_inserts}")
            print(f"  失败/跳过行数: {failed_lines}")
            return True

    except Exception as e:
        print(f"处理文件 '{jsonl_filepath}' 或表 '{target_table_name}' 时发生严重错误: {e} (类型: {type(e).__name__})")
        # 可以考虑在这里回滚，但通常逐文件提交，单个文件失败不影响其他
        return False

def main():
    # 修改为按投诉类型分类后的文件所在目录
    # classified_files_dir = "/home/jhl/NLP/classified_by_complaint_type" # Linux 示例路径
    # Windows 示例路径: classified_files_dir = "C:\\path\\to\\classified_by_complaint_type"
    # 或者，如果脚本和目录在同一级：
    script_dir = os.path.dirname(os.path.abspath(__file__)) if '__file__' in locals() else os.getcwd()
    classified_files_dir = os.path.join(script_dir, "data/broad_classified_complaints")
    print(f"将在以下目录中查找按类型分类的JSONL文件: '{classified_files_dir}'")


    # 1. 确保主数据库存在
    cnx_server = None
    cursor_server = None
    try:
        server_conn_props = db_connection_config.copy()
        # server_conn_props.pop('database', None) # 确保连接时不指定数据库
        
        cnx_server = mysql.connector.connect(
            user=server_conn_props['user'],
            password=server_conn_props['password'],
            host=server_conn_props['host'],
            charset=server_conn_props.get('charset', 'utf8mb4') # 使用配置中的charset
        )
        cursor_server = cnx_server.cursor()
        cursor_server.execute(f"CREATE DATABASE IF NOT EXISTS `{MAIN_DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        print(f"主数据库 '{MAIN_DB_NAME}' 已确保存在。")
    except mysql.connector.Error as err:
        print(f"错误: 连接MySQL服务器或创建主数据库 '{MAIN_DB_NAME}' 失败: {err}")
        return # 无法继续
    finally:
        if cursor_server: cursor_server.close()
        if cnx_server and cnx_server.is_connected(): cnx_server.close()

    # 2. 连接到主数据库并处理文件
    cnx_main_db = None
    cursor_main_db = None
    try:
        db_conn_props_main = db_connection_config.copy()
        db_conn_props_main['database'] = MAIN_DB_NAME
        
        cnx_main_db = mysql.connector.connect(**db_conn_props_main)
        cursor_main_db = cnx_main_db.cursor()
        # 确保连接使用UTF-8，尽管表和库级别已设置，连接参数也重要
        cursor_main_db.execute("SET NAMES utf8mb4")
        print(f"已成功连接到数据库 '{MAIN_DB_NAME}'。")

        if not os.path.exists(classified_files_dir):
            print(f"错误: 分类文件目录 '{classified_files_dir}' 不存在。请先运行按类型分类的脚本。")
            return
        
        dir_list = os.listdir(classified_files_dir)
        if not dir_list:
            print(f"目录 '{classified_files_dir}' 为空，没有文件可处理。")
            return

        print(f"开始批量导入按类型分类的数据到数据库 '{MAIN_DB_NAME}' 的各个表中...")
        processed_file_count = 0
        for filename in dir_list:
            if filename.endswith(".jsonl"):
                # 从文件名提取投诉类型 (文件名即 "类型名.jsonl")
                complaint_type_name_from_file = filename[:-len(".jsonl")] # 移除 ".jsonl" 后缀
                
                if not complaint_type_name_from_file: # 如果文件名是 ".jsonl" (不太可能)
                    print(f"跳过无效文件名: {filename}")
                    continue

                jsonl_full_path = os.path.join(classified_files_dir, filename)
                create_and_populate_type_table(cursor_main_db, cnx_main_db, jsonl_full_path, complaint_type_name_from_file)
                processed_file_count +=1
            else:
                print(f"跳过非 .jsonl 文件: {filename}")
        
        if processed_file_count == 0:
            print("在目录中没有找到 .jsonl 文件进行处理。")
        print("\n所有文件处理完毕。")

    except mysql.connector.Error as err:
        print(f"数据库 '{MAIN_DB_NAME}' 操作过程中发生 MySQL 错误: {err}")
    except Exception as e:
        print(f"处理过程中发生了一个预料之外的错误: {e} (类型: {type(e).__name__})")
    finally:
        if cursor_main_db: cursor_main_db.close()
        if cnx_main_db and cnx_main_db.is_connected():
            cnx_main_db.close()
            print("MySQL 主数据库连接已关闭。")

if __name__ == "__main__":
    main()