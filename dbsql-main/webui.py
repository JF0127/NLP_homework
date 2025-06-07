import gradio as gr
import pandas as pd
import datetime
import time
import schedule # 用于定时任务
import requests # 用于直接调用Ollama HTTP API
import json     # 用于构造和解析JSON
from collections import defaultdict # 用于聚合数据
import mysql.connector
from mysql.connector import Error as MySQLError # 为清晰起见，重命名Error

# --- 1. 从你的项目中导入DBSQLAnswer ---
try:
    from dbsql.llm.chains.dbsql_answer import DBSQLAnswer
    DBSQLAnswer_available = True
except ImportError:
    print("警告：无法导入 DBSQLAnswer 类。Text2SQL页面将使用模拟功能。")
    print("请确保 dbsql.llm.chains.dbsql_answer 路径正确且在PYTHONPATH中。")
    DBSQLAnswer_available = False
    class DBSQLAnswer: # 模拟类，如果导入失败
        def __init__(self, model, db_type, db_host, db_port, db_user, db_password, db_name):
            self.db_name = db_name
            print(f"警告：使用了模拟的DBSQLAnswer (数据库: {db_name})")
        def step_run(self, question: str):
            time.sleep(0.5) # 模拟处理
            if "多少" in question:
                 return f"SELECT COUNT(*) FROM DUMMY_TABLE WHERE q='{question}'", f"模拟结果：关于 '{question}' 有100条记录。"
            return f"-- 模拟SQL for: {question} --", f"模拟的自然语言回答: {question}"

# --- 2. 全局配置 ---
DB_CONNECTION_CONFIG = {
    'user': 'root',
    'password': 'jhl12735800', # !!! 请务必使用你的真实密码 !!!
    'host': '127.0.0.1',
    'charset': 'utf8mb4',
}
MAIN_DB_NAME = 'NLP_DB_BY_TYPE'
TABLE_NAME_PREFIX = ''

EXPLICIT_COLUMN_SCHEMAS = {
    "id": {"type": "INT AUTO_INCREMENT PRIMARY KEY", "comment": '自动递增主键'},
    "time": {"type": "DATE", "comment": '投诉发生的日期, 格式YYYY-MM-DD'},
    "amount": {"type": "DECIMAL(10,2)", "comment": '涉及金额'},
    "subject": {"type": "VARCHAR(255)", "comment": '投诉方'},
    "object": {"type": "VARCHAR(255)", "comment": '被投诉方'},
    "description": {"type": "TEXT", "comment": '投诉的具体内容描述'},
    "platform": {"type": "VARCHAR(255)", "comment": '投诉发生的平台'},
    "complaint_type": {"type": "VARCHAR(255)", "comment": '投诉的实际分类值'}
}
TIME_COLUMN_NAME = 'time'

# Ollama模型配置 (用于页面一的趋势预警)
# 这些值来自你之前提供的 final_trend_analysis_script.py
OLLAMA_MODEL_FOR_TREND_ANALYSIS = "deepseek-r1:14b" 
OLLAMA_BASE_URL_FOR_TRENDS = "https://u354342-baf8-f3ff1b79.bjc1.seetacloud.com:8443" # 你脚本中提供的URL

# Text2SQL 使用的 DBSQLAnswer 实例
if DBSQLAnswer_available:
    try:
        db_answer_instance_for_text2sql = DBSQLAnswer(
            model="local", db_type="MySQL", db_host=DB_CONNECTION_CONFIG['host'],
            db_port=3306, db_user=DB_CONNECTION_CONFIG['user'],
            db_password=DB_CONNECTION_CONFIG['password'], db_name=MAIN_DB_NAME,
        )
        print("DBSQLAnswer 实例 (用于Text2SQL) 已成功初始化。")
    except Exception as e:
        print(f"错误：初始化真实 DBSQLAnswer 失败: {e}。Text2SQL将使用模拟功能。")
        db_answer_instance_for_text2sql = DBSQLAnswer("simulated", "MySQL", "localhost", 3306, "user", "pass", "db")
else:
    db_answer_instance_for_text2sql = DBSQLAnswer("simulated", "MySQL", "localhost", 3306, "user", "pass", "db")

SCHEDULED_ANALYSIS_TIME = "02:00"

# --- 3. 数据库辅助函数 ---
def connect_db(database_name=None):
    conn = None; config = DB_CONNECTION_CONFIG.copy()
    if database_name: config['database'] = database_name
    try: conn = mysql.connector.connect(**config)
    except MySQLError as e: print(f"错误：连接MySQL数据库 '{database_name if database_name else '服务器'}' 失败: {e}")
    return conn

def get_all_complaint_table_names(db_conn, prefix):
    if not db_conn or not db_conn.is_connected(): return []
    names = []; cursor = None
    try:
        cursor = db_conn.cursor()
        cursor.execute("SHOW TABLES;")
        for row in cursor.fetchall():
            if row[0].startswith(prefix): names.append(row[0])
    except MySQLError as e: print(f"错误：获取表名列表时出错: {e}")
    finally: 
        if cursor: cursor.close()
    return names

# --- 4. 数据获取函数 (真实数据 for Page 1 & Alerts) ---
def fetch_complaint_volume_data_from_db():
    print(f"数据库操作：正在获取2023-2024年度月度投诉总量...")
    conn = connect_db(MAIN_DB_NAME)
    if not conn: return pd.DataFrame({'月份': [], '每月投诉量': []})

    all_table_names = get_all_complaint_table_names(conn, TABLE_NAME_PREFIX)
    daily_counts_aggregated = defaultdict(int)

    start_dt = pd.to_datetime("2023-01-01", utc=False)
    end_dt = pd.to_datetime("2024-12-31", utc=False) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)

    if all_table_names:
        for table_name in all_table_names:
            cursor = None
            try:
                cursor = conn.cursor(dictionary=True)
                query = f"SELECT `{TIME_COLUMN_NAME}`, COUNT(*) as count FROM `{table_name}` GROUP BY `{TIME_COLUMN_NAME}`"
                cursor.execute(query)
                for row in cursor.fetchall():
                    event_date_obj = row[TIME_COLUMN_NAME]
                    if event_date_obj is not None:
                        event_date = pd.to_datetime(event_date_obj, utc=False)
                        if event_date < start_dt or event_date > end_dt:
                            continue
                        daily_counts_aggregated[event_date] += row['count']
            except MySQLError as e: print(f"错误：从表 '{table_name}' 查询每日投诉量时出错: {e}")
            finally:
                if cursor: cursor.close()
    if conn.is_connected(): conn.close()

    if not daily_counts_aggregated: return pd.DataFrame({'月份': [], '每月投诉量': []})

    df = pd.DataFrame(list(daily_counts_aggregated.items()), columns=['日期', '每日投诉量'])
    if df.empty: return pd.DataFrame({'月份': [], '每月投诉量': []})

    df['日期'] = pd.to_datetime(df['日期'])
    df = df.sort_values(by='日期')
    df.set_index('日期', inplace=True)

    monthly_df = df['每日投诉量'].resample('MS').sum().reset_index()
    monthly_df.rename(columns={'日期': '月份', '每日投诉量': '每月投诉量'}, inplace=True)
    
    # --- 修改：确保月份列是 'YYYY-MM' 格式的字符串 ---
    if not monthly_df.empty:
        monthly_df['月份'] = pd.to_datetime(monthly_df['月份']).dt.strftime('%Y-%m')
    # --- 修改结束 ---

    print(f"数据库操作：成功获取并聚合了2023-2024年度 {len(monthly_df)} 个月的投诉总量数据。")
    return monthly_df

def fetch_complaint_types_trend_from_db():
    # ... (前面的数据库连接和数据获取逻辑不变) ...
    print(f"数据库操作：正在获取2023-2024年度各投诉类型月度趋势...")
    conn = connect_db(MAIN_DB_NAME)
    if not conn: return pd.DataFrame({'月份': [], '投诉类型': [], '数量': []})

    all_table_names = get_all_complaint_table_names(conn, TABLE_NAME_PREFIX)
    all_type_trends_daily = []

    start_dt = pd.to_datetime("2023-01-01", utc=False)
    end_dt = pd.to_datetime("2024-12-31", utc=False) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)

    if all_table_names:
        for table_name in all_table_names:
            cursor = None
            try:
                cursor = conn.cursor(dictionary=True)
                type_name = table_name.replace(TABLE_NAME_PREFIX, "")
                query = f"SELECT `{TIME_COLUMN_NAME}`, COUNT(*) as count FROM `{table_name}` GROUP BY `{TIME_COLUMN_NAME}`"
                cursor.execute(query)
                for row in cursor.fetchall():
                    event_date_obj = row[TIME_COLUMN_NAME]
                    if event_date_obj is not None:
                        event_date = pd.to_datetime(event_date_obj, utc=False)
                        if event_date < start_dt or event_date > end_dt:
                            continue
                        all_type_trends_daily.append({'日期': event_date, '投诉类型': type_name, '数量': row['count']})
            except MySQLError as e: print(f"错误：从表 '{table_name}' 查询类型趋势时出错: {e}")
            finally:
                if cursor: cursor.close()
    if conn.is_connected(): conn.close()

    if not all_type_trends_daily: return pd.DataFrame({'月份': [], '投诉类型': [], '数量': []})

    df = pd.DataFrame(all_type_trends_daily)
    if df.empty: return pd.DataFrame({'月份': [], '投诉类型': [], '数量': []})

    df['日期'] = pd.to_datetime(df['日期'])
    df = df.sort_values(by=['投诉类型', '日期'])

    monthly_dfs = []
    for type_name_group, group in df.groupby('投诉类型'):
        group = group.set_index('日期')
        monthly_group = group['数量'].resample('MS').sum().reset_index()
        monthly_group['投诉类型'] = type_name_group
        monthly_dfs.append(monthly_group)

    if not monthly_dfs: return pd.DataFrame({'月份': [], '投诉类型': [], '数量': []})
    
    final_df = pd.concat(monthly_dfs)
    final_df.rename(columns={'日期': '月份'}, inplace=True)
    
    # --- 修改：确保月份列是 'YYYY-MM' 格式的字符串 ---
    if not final_df.empty:
        final_df['月份'] = pd.to_datetime(final_df['月份']).dt.strftime('%Y-%m')
    # --- 修改结束 ---

    final_df = final_df[['月份', '投诉类型', '数量']]
    print(f"数据库操作：成功获取并聚合了2023-2024年度 {len(final_df)} 条各投诉类型的月度时间趋势数据。")
    return final_df


def get_overall_n_newest_complaints(n_records=50):
    """从所有相关投诉表中获取按时间排序最新的 N 条详细记录。"""
    print(f"数据库操作：正在获取全局最新的 {n_records} 条投诉记录...")
    db_main_conn = connect_db(database_name=MAIN_DB_NAME)
    if not db_main_conn: return []
    all_complaints_ever_list = []
    complaint_table_names = get_all_complaint_table_names(db_main_conn, TABLE_NAME_PREFIX)
    if not complaint_table_names:
        print(f"信息：在数据库 '{MAIN_DB_NAME}' 中没有找到以 '{TABLE_NAME_PREFIX}' 开头的表 (获取最新N条)。")
    else:
        columns_to_fetch = list(EXPLICIT_COLUMN_SCHEMAS.keys())
        for table_name in complaint_table_names:
            cursor = None
            try:
                cursor = db_main_conn.cursor(dictionary=True)
                select_cols_str = ", ".join([f"`{col}`" for col in columns_to_fetch])
                # 为了获取最新的N条，我们仍然需要先获取较多数据或所有数据进行全局排序
                # 如果表非常大，这里应该优化为每个表取最新的N条（或稍多于N/num_tables条）然后合并排序
                # 当前实现是获取所有，然后在Python中排序，与你之前的脚本一致
                query = f"SELECT {select_cols_str} FROM `{table_name}`" 
                cursor.execute(query)
                records_from_this_table = cursor.fetchall()
                category_name = table_name.replace(TABLE_NAME_PREFIX, "")
                for record_dict in records_from_this_table:
                    if record_dict.get(TIME_COLUMN_NAME) is not None:
                        record_dict['source_table_category'] = category_name
                        all_complaints_ever_list.append(record_dict)
            except MySQLError as e: print(f"错误：从表 '{table_name}' 获取所有数据时出错: {e}")
            finally: 
                if cursor: cursor.close()
    if db_main_conn.is_connected(): db_main_conn.close()
    if not all_complaints_ever_list:
        print("信息：未能从任何表中获取到用于全局排序的数据。")
        return []
    try:
        all_complaints_ever_list.sort(key=lambda x: x[TIME_COLUMN_NAME], reverse=True)
    except (TypeError, KeyError) as e: # KeyError if TIME_COLUMN_NAME is missing in some dict
        print(f"错误：排序时发生错误 (可能是因为 '{TIME_COLUMN_NAME}' 字段问题): {e}")
        return [] 
    top_n_complaints = all_complaints_ever_list[:n_records]
    print(f"信息：总共从所有表中获取并排序了 {len(all_complaints_ever_list)} 条记录，返回最新的 {len(top_n_complaints)} 条。")
    return top_n_complaints

def fetch_complaint_types_distribution_from_db():
    print("数据库操作：正在获取各投诉类型分布...")
    conn = connect_db(MAIN_DB_NAME)
    if not conn: return pd.DataFrame({'投诉类型': [], '数量': []})
    all_table_names = get_all_complaint_table_names(conn, TABLE_NAME_PREFIX)
    type_counts = []
    if all_table_names:
        for table_name in all_table_names:
            cursor = None
            try:
                cursor = conn.cursor() # New cursor for each query
                query = f"SELECT COUNT(*) FROM `{table_name}`"
                cursor.execute(query)
                count_result = cursor.fetchone()
                count = count_result[0] if count_result else 0
                type_name = table_name.replace(TABLE_NAME_PREFIX, "")
                type_counts.append({'投诉类型': type_name, '数量': count})
            except MySQLError as e: print(f"错误：从表 '{table_name}' 查询总数时出错: {e}")
            finally: 
                if cursor: cursor.close()
    if conn.is_connected(): conn.close()
    df = pd.DataFrame(type_counts)
    print(f"数据库操作：成功获取了 {len(df)} 个投诉类型的分布数据。")
    return df

# --- 5. Ollama LLM 交互函数 (使用requests.post) ---
def analyze_complaint_trends_with_ollama_via_requests(
        complaints_data_list, ollama_model_name, base_url, analysis_type_description=""):
    if not complaints_data_list: return "分析中止：输入数据为空。"
    if base_url == "YOUR_OLLAMA_BASE_URL_HERE" or not base_url or "seetacloud.com" not in base_url : # Added check for placeholder or unconfigured SeetaCloud URL
        print(f"错误：Ollama基础URL ({base_url}) 未正确配置或仍为占位符。")
        return f"配置错误：Ollama基础URL ({base_url}) 未正确设置。"
    # (The rest of this function with the detailed prompt is the same as provided in the previous response)
    # For brevity, I'll just include the key call part. Ensure you have the full prompt logic here.
    print(f"\n--- Ollama(requests)趋势分析：模型 '{ollama_model_name}' URL '{base_url}' 分析 {analysis_type_description} ---")
    system_prompt_content = (
        "你是一位专为政府部门提供决策支持的资深公共政策与消费者行为分析顾问。你的核心专长是从大规模、高时效性的消费者投诉数据（例如12315系统数据）中敏锐洞察社会经济运行中的关键信号，"
        "识别亟待关注的消费领域热点问题，并精准研判其动态演化趋势。\n"
        "你的分析报告将作为政府相关部门进行市场监管、政策制定和风险预警的重要参考。\n\n"
        "基于接下来提供的消费者投诉数据摘要，请务必完成以下核心分析任务：\n"
        "1.  **当前消费热点问题识别**：\n"
        "    - 明确指出当前数据中反映出的、在社会经济生活中最为突出或亟待关注的消费热点问题（例如：特定商品/服务投诉激增、新型消费陷阱、涉及领域广泛的共性问题等）。\n"
        "    - 对每个热点问题进行简要描述，说明其主要表现形式和涉及的消费领域。\n"
        "2.  **投诉动态趋势分析**：\n"
        "    - 结合所提供数据的时间信息，分析各类主要投诉（或你识别出的热点问题）随时间演变的动态特征（例如：是快速增长、持续平稳、季节性波动，还是偶发性爆发？）。\n"
        "    - 如果数据支持，尝试指出趋势背后的可能驱动因素。\n"
        "3.  **潜在影响与风险研判**：\n"
        "    - 评估已识别的消费热点和负面趋势可能对消费者合法权益、市场经济秩序以及社会和谐稳定造成的潜在影响和风险级别。\n"
        "4.  **政策关注与建议方向**（此部分需审慎，基于数据客观提出）：\n"
        "    - 根据分析结果，凝练出需要政府监管部门或相关政策制定者重点关注的领域或具体问题点。\n"
        "    - （如果数据和你的分析能支持）可以初步提出需要进一步调研或考虑的政策调整方向。\n\n"
        "分析报告的总体要求：\n"
        "-   **高度客观**：严格基于数据进行分析，避免无依据的推测。\n"
        "-   **重点突出**：优先呈现对政府决策最具价值的核心发现。\n"
        "-   **结构化呈现**：报告主体可考虑采用如“一、当前主要消费热点问题”、“二、投诉动态趋势观察”、“三、潜在影响与风险评估”、“四、政策关注建议”等逻辑清晰的章节进行组织。\n"
        "-   **语言专业**：使用专业、严谨、精炼的语言，避免口语化和模糊表达，确保报告的权威性。"
    )
    user_prompt_lines = [
        f"背景信息：以下数据抽样自12315消费者投诉举报系统，反映了在“{analysis_type_description}”时间窗口内的部分消费者核心诉求。",
        "核心分析任务：请您作为资深政府分析顾问，严格遵照系统提示中定义的角色职责、分析框架和报告要求，对下述数据进行深入分析，旨在：",
        "  (A) 有效识别当前社会经济生活中亟待关注的消费热点问题；",
        "  (B) 精准分析各类投诉随时间演变的动态趋势及其潜在影响。",
        "请确保您的分析具有前瞻性和决策参考价值。\n",
        "具体的投诉数据条目如下：", "--- 数据开始 ---"
    ]
    for i, complaint in enumerate(complaints_data_list):
        details = [];
        for key, value in complaint.items():
            if value is not None: 
                if key == TIME_COLUMN_NAME and isinstance(value, datetime.date): details.append(f"{key}: {value.strftime('%m-%d')}")
                else: details.append(f"{key}: {str(value)}")
        user_prompt_lines.append(f"投诉 {i+1}: {' | '.join(details)}")
    user_prompt_lines.append("--- 数据结束 ---\n请严格按照系统提示中的要求，生成你的专业分析报告。")
    full_user_prompt = "\n".join(user_prompt_lines)
    payload = {"model": ollama_model_name, "messages": [{"role": "system", "content": system_prompt_content}, {"role": "user", "content": full_user_prompt}], "stream": False}
    api_endpoint = f"{base_url.rstrip('/')}/api/chat"
    analysis_report = f"未能连接到Ollama服务或API调用失败: {api_endpoint}"
    try:
        headers = {"Content-Type": "application/json"}
        response = requests.post(api_endpoint, data=json.dumps(payload), headers=headers, timeout=300)
        response.raise_for_status()
        response_data = response.json()
        if response_data and 'message' in response_data and 'content' in response_data['message']:
            analysis_report = response_data['message']['content'].strip()
        else: print(f"Ollama响应结构异常: {response_data}")
    except requests.exceptions.Timeout: analysis_report = f"LLM分析请求超时(URL:{api_endpoint})"; print(analysis_report)
    except requests.exceptions.HTTPError as e: analysis_report = f"Ollama API HTTP错误(状态码 {e.response.status_code}): {e.response.text[:200]}"; print(analysis_report + e.response.text)
    except requests.exceptions.RequestException as e: analysis_report = f"无法连接到Ollama: {e}"; print(analysis_report)
    except Exception as e: analysis_report = f"处理LLM交互时未知错误: {e}"; print(analysis_report)
    return analysis_report


# --- 6. Gradio 回调函数定义 ---

def update_volume_plot_gradio_monthly(): # 移除了日期参数
    df = fetch_complaint_volume_data_from_db() # 直接调用，不传日期
    if df.empty or '月份' not in df.columns or '每月投诉量' not in df.columns:
        return gr.LinePlot(value=None, title="2023-2024年度月度投诉数据量趋势 - 无有效数据", x_title="月份", y_title="每月投诉量")
    return gr.LinePlot(
        df, x='月份', y='每月投诉量',
        title="2023-2024年度月度投诉数据量趋势", # 更新标题
        x_title="月份", y_title="每月投诉量",
        shape="circle", tooltip=['月份', '每月投诉量'],
        height=350, width="auto"
    )

# 直方图函数保持不变，它原本就不依赖日期选择器
def update_type_histogram_gradio():
    df = fetch_complaint_types_distribution_from_db() # 这个函数可能也需要调整以反映特定时期或全部数据
    # 如果希望直方图也仅显示2023-2024的数据，fetch_complaint_types_distribution_from_db 也需要类似地过滤
    if df.empty or '投诉类型' not in df.columns or '数量' not in df.columns:
        return gr.BarPlot(value=None, title="各类投诉数量分布 - 无有效数据", x_title="投诉类型", y_title="数量")
    return gr.BarPlot(
        df, x='投诉类型', y='数量',
        title="各类投诉数量分布 (直方图)", # 可考虑添加年份范围到标题
        x_title="投诉类型", y_title="数量",
        vertical_x_text=True, height=350,
        color='投诉类型', width="auto"
    )

def update_type_line_plot_gradio_monthly(): # 移除了日期参数
    df = fetch_complaint_types_trend_from_db() # 直接调用，不传日期
    if df.empty or '月份' not in df.columns or '投诉类型' not in df.columns or '数量' not in df.columns:
        return gr.LinePlot(value=None, title="2023-2024年度各类投诉月度数量趋势 - 无有效数据", x_title="月份", y_title="数量")
    return gr.LinePlot(
        df, x='月份', y='数量', color='投诉类型',
        title="2023-2024年度各类投诉月度数量趋势", # 更新标题
        x_title="月份", y_title="投诉数量",
        shape="circle", tooltip=['月份', '投诉类型', '数量'],
        height=350, legend='full', width="auto"
    )

def handle_text2sql_query_gradio(user_question: str, chat_history_proc: list, chat_history_resp: list):
    if not user_question.strip(): return chat_history_proc, chat_history_resp, ""
    if db_answer_instance_for_text2sql is None: 
        err_msg = "错误：DBSQLAnswer未初始化，Text2SQL功能不可用。"
        chat_history_proc.append([user_question, err_msg]); chat_history_resp.append([user_question, err_msg])
        return chat_history_proc, chat_history_resp, ""
    process_info, response_info = db_answer_instance_for_text2sql.step_run(user_question)
    response_info = process_info.split("</think>\n\n")[-1]
    chat_history_proc.append([user_question, f"```sql\n{process_info}\n```" if process_info else "-- 无SQL生成 --"])
    chat_history_resp.append([user_question, response_info])
    return chat_history_proc, chat_history_resp, ""

def clear_text2sql_chat_gradio(): return [], [], ""

def generate_and_display_alerts_gradio():
    status_update = f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始生成预警...\n"
    processed_report = "预警报告初始化内容..." # Default content
    try:
        # Using the latest 30 records for alert analysis as per your original code
        complaint_data = get_overall_n_newest_complaints(n_records=50)
        analysis_description = "最近50条投诉（用于预警）"
        status_update += f"获取到 {len(complaint_data)} 条数据用于分析 ({analysis_description}).\n"
        
        if not complaint_data:
            raw_report = "数据不足或获取失败，无法生成预警。"
            status_update += "数据不足或获取失败.\n"
        else:
            # This function is assumed to be defined elsewhere in your script
            raw_report = analyze_complaint_trends_with_ollama_via_requests(
                complaint_data, OLLAMA_MODEL_FOR_TREND_ANALYSIS, OLLAMA_BASE_URL_FOR_TRENDS, analysis_description
            )
        
        # Process the report content to remove potential prefixes
        if "</think>" in raw_report:
            processed_report = raw_report.split("</think>")[-1].strip()
        else:
            processed_report = raw_report.strip()
            
        status_update += f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 预警报告生成完毕.\n"
        return processed_report, status_update
    except Exception as e:
        error_message = f"生成预警失败: {e}"
        status_update += f"错误: {error_message}\n"; print(f"生成预警异常: {e}")
        # Ensure error messages are also processed if they could contain the prefix
        if "</think>" in error_message:
            processed_report = error_message.split("</think>")[-1].strip()
        else:
            processed_report = error_message.strip()
        return processed_report, status_update

# --- 7. Gradio 界面构建 ---
with gr.Blocks(title="12315消费投诉智能分析平台", theme=gr.themes.Default()) as demo:
    gr.Markdown("<h1><center>12315消费投诉智能分析与查询平台</center></h1>")
    with gr.Tabs():
        with gr.TabItem("数据洞察与预警", id="tab_visualization"):
            gr.Markdown("## 消费投诉洞察看板")
            with gr.Accordion("🚨 每日消费趋势预警", open=True): # 预警部分仍基于最新N条，与月度图表独立
                with gr.Row():
                    alert_refresh_button = gr.Button("获取/刷新最新预警报告", variant="primary", scale=1)
                    alert_status_textbox = gr.Textbox(label="预警生成状态", interactive=False, scale=3, lines=2, max_lines=5)
                daily_alert_display = gr.Markdown(label="预警报告内容", value="点击上方按钮以生成预警报告。")
            
            gr.Markdown("---"); gr.Markdown("### 投诉数据统计图表 (2023-2024年度, 月度)") # 更新标题
            
            plot_refresh_button = gr.Button("刷新所有图表数据", variant="secondary")
            
            with gr.Row():
                volume_plot_output = gr.LinePlot(show_label=False)
            with gr.Row():
                type_histogram_output = gr.BarPlot(show_label=False, scale=1)
                type_line_plot_output = gr.LinePlot(show_label=False, scale=1)
            
            alert_refresh_button.click(
                fn=generate_and_display_alerts_gradio, 
                inputs=[], 
                outputs=[daily_alert_display, alert_status_textbox]
            )
            
            # 绘图按钮的事件，不再需要日期输入
            plot_actions = plot_refresh_button.click(
                fn=update_volume_plot_gradio_monthly, 
                inputs=None, # 移除了 date_picker_inputs
                outputs=[volume_plot_output]
            )
            plot_actions.then(
                fn=update_type_histogram_gradio, 
                inputs=None, 
                outputs=[type_histogram_output]
            )
            plot_actions.then(
                fn=update_type_line_plot_gradio_monthly, 
                inputs=None, # 移除了 date_picker_inputs
                outputs=[type_line_plot_output]
            )
            
            initial_outputs = [
                volume_plot_output, 
                type_histogram_output, 
                type_line_plot_output, 
                daily_alert_display, 
                alert_status_textbox
            ]
            
            def load_all_data_on_start():
                vol_plot_val = update_volume_plot_gradio_monthly()
                hist_plot_val = update_type_histogram_gradio() 
                line_plot_val = update_type_line_plot_gradio_monthly()
                
                alert_report_val, alert_status_val = generate_and_display_alerts_gradio()
                
                return vol_plot_val, hist_plot_val, line_plot_val, alert_report_val, alert_status_val
            
            demo.load(
                load_all_data_on_start, 
                inputs=None, 
                outputs=initial_outputs
            )

        with gr.TabItem("Text-to-SQL查询", id="tab_text2sql"): # Text2SQL 部分保持不变
            gr.Markdown("## 自然语言数据库查询")
            with gr.Row(): 
                with gr.Column(scale=1): 
                    gr.Markdown("### SQL / 处理过程"); chatbot_process_p2 = gr.Chatbot(label="处理过程", height=350, show_copy_button=True, bubble_full_width=False)
                    gr.Markdown("### 自然语言回复"); chatbot_response_p2 = gr.Chatbot(label="机器人回复", height=350, show_copy_button=True, bubble_full_width=False)
                    user_question_p2 = gr.Textbox(label="请输入你的自然语言查询:", placeholder="例如：上周产品质量相关的投诉有多少？", lines=3)
                    with gr.Row(): send_button_p2 = gr.Button("发送查询", variant="primary", scale=3); clear_button_p2 = gr.Button("清空对话", scale=1)
            chat_history_proc_state_p2 = gr.State([]); chat_history_resp_state_p2 = gr.State([])
            send_button_p2.click(handle_text2sql_query_gradio, [user_question_p2, chat_history_proc_state_p2, chat_history_resp_state_p2], [chatbot_process_p2, chatbot_response_p2, user_question_p2])
            user_question_p2.submit(handle_text2sql_query_gradio, [user_question_p2, chat_history_proc_state_p2, chat_history_resp_state_p2], [chatbot_process_p2, chatbot_response_p2, user_question_p2])
            clear_button_p2.click(clear_text2sql_chat_gradio, [], [chatbot_process_p2, chatbot_response_p2, user_question_p2])
# --- 8. 主执行块 ---
if __name__ == "__main__":
    print("程序启动...")
    print("请确保所有数据库和Ollama配置已正确设置在脚本顶部。")
    if OLLAMA_BASE_URL_FOR_TRENDS == "YOUR_OLLAMA_BASE_URL_HERE":
        print("警告!!! Ollama基础URL (OLLAMA_BASE_URL_FOR_TRENDS) 仍为占位符，请修改为你的实际URL！")
    print(f"Ollama趋势分析将使用模型: {OLLAMA_MODEL_FOR_TREND_ANALYSIS} @ {OLLAMA_BASE_URL_FOR_TRENDS}")
    
    print(f"正在启动Gradio应用，请访问 http://127.0.0.1:12258 (或你指定的server_port)")
    demo.launch(server_port=12258, share=False)
    