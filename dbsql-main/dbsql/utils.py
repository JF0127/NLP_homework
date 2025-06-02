import re
from typing import Dict, List, Optional

from langchain_core.messages import AIMessage

from .dmdb.dm_database import DMDatabase


def sql_extract(sentence: str) -> List[str]:
    pattern = r"```sql\s*(.*?)\s*```"
    matches = re.findall(pattern, sentence, re.DOTALL)
    return matches


def table_extract(message: AIMessage) -> Optional[List[str]]:
    content = message.content
    if content == "":
        return None
    print("content:", content)
    content = content.split("Answer:")[-1]
    tables = [table.strip() for table in content.split(",")]
    if "NLP_DB_BY_TYPE" not in tables[0]:
        return tables
    else:
        result = []
        for table in tables:
            if "NLP_DB_BY_TYPE" in table:
                table = table.replace("NLP_DB_BY_TYPE", "")
            if "\\" in table:
                table = table.replace("\\", "")
            if table.startswith("_"):
                table = table.strip("_")
            if table.startswith("."):
                table = table.replace(".", "")
            result.append(table)
        return result

def table_info_generate(db: DMDatabase, table_names: List[str], extra_data: Dict[str, Dict]) -> str:
    print("call")
    if table_names is None or len(table_names) == 0:
        table_names = db.get_usable_table_names()
    table_info = ""
    for table_name in table_names:
        table_info += f"######### {table_name} #########\n"
        table_info += f"1. SQL描述与示例数据\n"
        table_info += db.get_table_info([table_name]).strip()
        table_info += "\n\n2. 表用途\n"
        table_info += extra_data[table_name]["表用途"]
        table_info += "\n\n3. 表结构\n"
        for id, state in extra_data[table_name]["表结构"].items():
            table_info += f"- {id}: {state}\n"
    return table_info
