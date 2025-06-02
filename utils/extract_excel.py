import json
from pathlib import Path
import re
import requests
import time
import pandas as pd
import logging

# --- 配置常量 ---
# 建议将这些配置移到单独的配置文件或环境变量中
OLLAMA_API_BASE_URL = "https://u354342-baf8-f3ff1b79.bjc1.seetacloud.com:8443" # 你的API地址
DEFAULT_MODEL_NAME = "deepseek-r1:7b" # 确认这是你在Ollama中使用的模型确切名称
DEFAULT_MAX_RETRIES = 3
DEFAULT_REQUEST_TIMEOUT = 60  # 秒
REQUEST_INTERVAL_SECONDS = 1 # 每次API调用后的等待时间

# --- 设置日志 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
    handlers=[
        logging.StreamHandler() # 输出到控制台
        # logging.FileHandler("processing_log.txt") # 同时输出到文件
    ]
)

# --- Excel数据提取函数 (需要你自己实现或确认) ---
def extract_excel_data(file_path: str, column: str, start_row: int, end_row: int) -> pd.Series:
    """
    从Excel文件提取指定列和行范围的数据。
    你需要确保这个函数能够正确处理各种边界情况。
    返回一个包含文本内容的pandas Series。
    """
    logging.info(f"尝试从 '{file_path}' 的列 '{column}' (行 {start_row}-{end_row}) 提取数据")
    try:
        # 示例实现：
        # pandas的read_excel中skiprows参数是从0开始计数的，所以start_row为1时表示跳过0行。
        # header=None表示第一行不是表头。
        # usecols可以按列名（如'B'）或索引（如1）读取。
        
        # 将Excel列字母转换为0-based索引
        col_index = ord(column.upper()) - ord('A') if isinstance(column, str) and column.isalpha() else int(column)

        df = pd.read_excel(
            file_path,
            header=None, # 假设没有表头行，或者表头在start_row之前
            usecols=[col_index], # 指定读取的列
            skiprows=range(1, start_row -1) # 跳过start_row之前的行 (Excel行号通常从1开始)
        )
        # nrows 参数用于限制读取的行数
        num_rows_to_extract = end_row - start_row + 1
        data_series = df.iloc[:num_rows_to_extract, 0] # 读取指定行数，并选择第一列（因为我们只usecols了一列）
        
        logging.info(f"成功提取 {len(data_series)} 条数据")
        return data_series
    except FileNotFoundError:
        logging.error(f"Excel文件未找到: {file_path}")
        raise
    except ValueError as e: # 例如列名无效
        logging.error(f"读取Excel时发生值错误 (可能是列指定问题): {file_path}, column {column}. Error: {e}")
        raise
    except Exception as e:
        logging.error(f"读取Excel文件 '{file_path}' 时发生未知错误: {e}")
        raise


def extract_and_parse_json(llm_output_text: str) -> dict | None:
    """
    从LLM的文本输出中提取并解析JSON对象。
    优先寻找被```json ... ```包裹的内容。
    如果找不到，则尝试解析整个文本或其中最大的JSON结构。
    """
    if not llm_output_text:
        return None

    processed_text = llm_output_text # 默认使用原始文本

    # 1. 尝试从Markdown代码块提取
    #    更宽松地匹配```json与```之间的内容，允许可选的语言标识符后的换行
    match = re.search(r'```(?:json)?\s*(.*?)\s*```', llm_output_text, re.DOTALL | re.IGNORECASE)
    if match:
        logging.debug("在LLM输出中找到Markdown JSON块。")
        processed_text = match.group(1)
    else:
        logging.debug("未在LLM输出中找到Markdown JSON块，尝试寻找原始JSON结构。")
        # 2. 如果没有Markdown块，尝试寻找文本中第一个 '{' 到最后一个 '}'
        #    或者第一个 '[' 到最后一个 ']' 的内容作为潜在JSON。
        #    这是一种启发式方法，可能不完美。
        start_brace = processed_text.find('{')
        end_brace = processed_text.rfind('}')
        start_bracket = processed_text.find('[')
        end_bracket = processed_text.rfind(']')

        # 选择看起来更像完整JSON对象的那个
        json_like_str = ""
        if start_brace != -1 and end_brace != -1 and start_brace < end_brace:
            json_like_str = processed_text[start_brace : end_brace+1]
        
        # 如果数组看起来更完整或只有数组
        if start_bracket != -1 and end_bracket != -1 and start_bracket < end_bracket:
            array_like_str = processed_text[start_bracket : end_bracket+1]
            if len(array_like_str) > len(json_like_str): # 倾向于更长的，可能更完整的
                json_like_str = array_like_str
        
        if json_like_str:
            processed_text = json_like_str
        else:
            logging.warning("在LLM输出中未能定位到明显的JSON结构。")
            # return None # 如果严格要求json结构，找不到就返回

    # 3. 清洗和解析 (应用在你上面代码中的逻辑)
    try:
        # 去除C风格注释 /* ... */
        cleaned_str = re.sub(r'/\*.*?\*/', '', processed_text, flags=re.DOTALL)
        # 去除行注释 // ...
        cleaned_str = re.sub(r'//.*?\n', '\n', cleaned_str) # 保留换行符
        cleaned_str = re.sub(r'//.*', '', cleaned_str) # 处理行尾注释

        # 谨慎替换单引号为双引号：仅当LLM确实会错误地用单引号包裹键或字符串时使用。
        # 如果你的LLM输出的JSON字符串值中可能包含合法的单引号，这个替换会出问题。
        # cleaned_str = cleaned_str.replace("'", '"')

        # 移除尾随逗号 (在对象和数组中)
        cleaned_str = re.sub(r',\s*([\}\]])', r'\1', cleaned_str)
        
        # 移除开头和结尾可能存在的非JSON字符（例如，如果LLM在JSON前后添加了“好的，这是JSON：”）
        cleaned_str = cleaned_str.strip()
        if not (cleaned_str.startswith('{') and cleaned_str.endswith('}')) and \
           not (cleaned_str.startswith('[') and cleaned_str.endswith(']')):
            logging.warning(f"清洗后的字符串不像一个JSON对象或数组: '{cleaned_str[:100]}...'")
            # 在这种情况下，可以尝试更积极地寻找JSON的起始和结束
            # 但简单起见，我们先依赖上面的提取逻辑

        return json.loads(cleaned_str)
    except json.JSONDecodeError as e:
        logging.warning(f"JSON解析失败: {e}. 清洗后的文本片段: '{cleaned_str[:200]}...'")
        return None
    except Exception as e: # 捕获其他潜在的清洗错误
        logging.error(f"解析JSON时发生意外错误: {e}. 文本片段: '{cleaned_str[:200]}...'")
        return None


class OllamaClient:
    def __init__(self, base_url: str, model: str = DEFAULT_MODEL_NAME, max_retries: int = DEFAULT_MAX_RETRIES, timeout: int = DEFAULT_REQUEST_TIMEOUT):
        self.api_url = f"{base_url}/api/generate"
        self.model = model
        self.max_retries = max_retries
        self.timeout = timeout

    def generate_structured_output(self, prompt: str, temperature: float = 0.3, max_tokens: int = 800) -> dict | None:
        """
        调用Ollama API生成文本，并尝试将其解析为JSON。
        包含了重试逻辑。
        """
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False, # 确保为False以获取完整响应
            # "format": "json", # 如果你的Ollama版本和模型支持，强烈建议开启此选项
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens # Ollama通常用num_predict
            }
        }
        
        last_exception = None
        for attempt in range(self.max_retries):
            logging.debug(f"向LLM发起请求 (尝试 {attempt + 1}/{self.max_retries})...")
            try:
                response = requests.post(self.api_url, json=payload, timeout=self.timeout)
                response.raise_for_status()  # 对4xx/5xx响应抛出HTTPError
                
                response_data = response.json()
                llm_output_text = response_data.get("response") # Ollama通常将输出放在 "response" 字段

                if not llm_output_text:
                    logging.warning(f"LLM响应中缺少'response'字段或为空。响应: {response_data}")
                    # 根据情况决定是否重试此类错误
                    # time.sleep(REQUEST_INTERVAL_SECONDS * (attempt + 1)) # 退避等待
                    # continue
                    return None # 或者直接返回None

                logging.debug(f"LLM原始输出 (部分): {llm_output_text[:300]}...")
                parsed_json = extract_and_parse_json(llm_output_text)
                return parsed_json # 无论是否为None，都返回第一次成功解析的结果

            except requests.exceptions.HTTPError as e:
                logging.warning(f"LLM API HTTP错误 (状态码 {e.response.status_code}): {e}")
                last_exception = e
                # 针对特定的状态码决定是否重试，例如 5xx 服务器错误可以重试
                if 500 <= e.response.status_code < 600:
                    logging.info("服务器端错误，稍后重试...")
                else: # 对于4xx客户端错误，重试可能无效，直接中断
                    logging.error(f"客户端错误 ({e.response.status_code})，中断重试。")
                    break
            except requests.exceptions.RequestException as e: # 其他网络问题，如超时、连接错误
                logging.warning(f"LLM API 请求失败: {e}")
                last_exception = e
            except json.JSONDecodeError as e: # requests.post本身的json=payload如果失败会是这个
                logging.error(f"构建请求体时发生JSON编码错误(不太可能发生): {e}")
                last_exception = e # 通常是客户端代码问题，无需重试
                break 
            except Exception as e: # 捕获其他意外错误
                logging.error(f"LLM API 调用期间发生未知错误: {e}")
                last_exception = e

            if attempt < self.max_retries - 1:
                wait_time = REQUEST_INTERVAL_SECONDS * (2 ** attempt) # 指数退避
                logging.info(f"等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
            
        logging.error(f"所有 ({self.max_retries}) 次尝试均失败。最后一次错误: {last_exception}")
        return None


def process_complaints_to_jsonl(datapath: str, output_jsonl_path: str, start_row: int, end_row: int):
    """
    处理投诉数据，将每条成功提取的信息作为独立的JSON对象写入JSON Lines文件。
    """
    # 确保你的Prompt中定义的键与这里的REQUIRED_KEYS一致
    REQUIRED_KEYS = {"time", "subject", "object", "description", "platform", "amount"}
    
    ollama_client = OllamaClient(
        base_url=OLLAMA_API_BASE_URL,
        model=DEFAULT_MODEL_NAME
    )
    
    try:
        complaint_texts_series = extract_excel_data(
            file_path=datapath,
            column="B", # 假设投诉内容在B列
            start_row=start_row,
            end_row=end_row
        )
    except Exception: # extract_excel_data 中已记录详细错误
        logging.error("因Excel读取失败，处理中止。")
        return

    if complaint_texts_series.empty:
        logging.info("Excel中未提取到任何数据，处理结束。")
        return

    successful_extractions = 0
    failed_extractions = 0

    # 确保输出目录存在
    Path(output_jsonl_path).parent.mkdir(parents=True, exist_ok=True)

    with open(output_jsonl_path, 'w', encoding='utf-8') as outfile:
        for idx, text_content in complaint_texts_series.items(): # .items() gives (index, value)
            excel_row_number = start_row + idx # 假设Series的索引从0开始对应start_row
            record_id = f"complaint_{Path(datapath).stem}_{excel_row_number}" # 创建一个唯一ID

            logging.info(f"--- 处理Excel行: {excel_row_number} (记录ID: {record_id}) ---")
            
            if pd.isna(text_content) or not str(text_content).strip():
                logging.warning(f"记录ID {record_id}: 内容为空，跳过。")
                output_record = {
                    "id": record_id,
                    "source_row": excel_row_number,
                    "status": "skipped_empty_content",
                    "extracted_data": None,
                    "error_message": "Original content was empty or NaN"
                }
                failed_extractions += 1
            else:
                logging.debug(f"记录ID {record_id}: 原始文本 -> '{str(text_content)[:200]}...'")
                # 构建你的Prompt，确保和LLM的预期一致
                prompt = f"""
                    请仔细阅读下面的用户投诉内容，并严格按照要求提取信息：

                    **投诉原文**：
                    {text_content}

                    **提取要求**：
                    1. 时间 (time): 精确到年月日（如无具体日期请用 'null' 或空字符串，格式："YYYY-MM-DD"）
                    2. 主体 (subject): 发起投诉的当事人（保留称谓如"张先生"） 
                    3. 客体 (object): 被投诉的对象（如商家、平台方等）
                    4. 描述 (description): 用一句话概括投诉核心问题（不超过50字）
                    5. 平台 (platform): 涉及的服务平台名称（如淘宝、拼多多等）
                    6. 金额 (amount): 涉及的经济损失（数字格式，单位统一为元。如无具体金额，请用null或0）
                    7. **投诉类型 (complaint_type): 根据投诉内容，概括投诉的核心类型。请从以下预设类型中选择最接近的一项，或根据实际情况给出简短精炼的类型描述（不超过10个字）。例如："产品质量与安全"、"价格、收费与退款"、"服务体验与履约"、"虚假宣传与欺诈"。如果无法明确判断，请使用 "其他"。**

                    **输出规则**：
                    - 必须严格生成标准JSON格式，键名固定为：time, subject, object, description, platform, amount, **complaint_type**
                    - 金额请统一转换为阿拉伯数字（例如："五百元" 转写为 500）。
                    - 如果某个字段的信息在原文中确实不存在，请使用 null 作为该字段的值。
                    - “投诉类型”字段应尽量精简，并优先考虑使用提供的示例类型。
                    - 禁止在JSON之外添加任何额外说明或注释。

                    请直接输出整理后的JSON对象：
                    """
                extracted_json = ollama_client.generate_structured_output(prompt)
                
                if extracted_json:
                    # 验证是否包含所有必需的键
                    missing_keys = REQUIRED_KEYS - set(extracted_json.keys())
                    if missing_keys:
                        logging.warning(f"记录ID {record_id}: LLM返回的JSON缺少必需字段: {missing_keys}. JSON: {extracted_json}")
                        output_record = {
                            "id": record_id,
                            "source_row": excel_row_number,
                            "status": "failed_missing_keys",
                            "extracted_data": extracted_json, # 仍然保存部分提取的数据
                            "error_message": f"Missing required keys: {missing_keys}"
                        }
                        failed_extractions += 1
                    else:
                        logging.info(f"记录ID {record_id}: 成功提取JSON: {extracted_json}")
                        output_record = {
                            "id": record_id,
                            "source_row": excel_row_number,
                            "status": "success",
                            "extracted_data": extracted_json,
                            "error_message": None
                        }
                        successful_extractions += 1
                else:
                    logging.warning(f"记录ID {record_id}: 未能从LLM输出中提取有效JSON。")
                    output_record = {
                        "id": record_id,
                        "source_row": excel_row_number,
                        "status": "failed_llm_extraction_or_parsing",
                        "extracted_data": None,
                        "error_message": "Failed to get valid JSON from LLM after retries or parsing failed."
                    }
                    failed_extractions += 1
            
            # 逐条写入JSON Lines文件
            outfile.write(json.dumps(output_record, ensure_ascii=False) + '\n')
            
            if (successful_extractions + failed_extractions) < len(complaint_texts_series): # 如果不是最后一条，则等待
                time.sleep(REQUEST_INTERVAL_SECONDS)

    logging.info(f"\n--- 处理完成 ---")
    logging.info(f"总计处理Excel行数: {len(complaint_texts_series)}")
    logging.info(f"成功提取记录数: {successful_extractions}")
    logging.info(f"失败或跳过记录数: {failed_extractions}")
    logging.info(f"结果已保存到: {output_jsonl_path}")

if __name__ == "__main__":
    process_complaints_to_jsonl(
        datapath="data/origin.xlsx",      # 你的Excel文件路径
        output_jsonl_path="data/output.jsonl", # 输出文件名更改为.jsonl
        start_row=1200,                      # Excel中的起始行号 (通常从1或2开始，取决于是否有表头)
        end_row=2000                         # Excel中的结束行号 (包含此行)
    )