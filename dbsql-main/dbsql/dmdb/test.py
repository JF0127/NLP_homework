import re


def extract_table_info(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()

    # 定义正则表达式模式来匹配表格信息
    table_pattern = re.compile(
        r'### 表 `(.*?)` 简介\n'
        r'\n'
        r'#### \*\*表用途\*\*\n'
        r'(.*?)\n'
        r'\n'
        r'---\n'
        r'\n'
        r'#### \*\*表结构\*\*\n'
        r'(.*?)\n'
        r'\n'
        r'---',
        re.DOTALL
    )

    tables_info = {}
    matches = table_pattern.findall(content)

    for match in matches:
        table_name = match[0].strip()
        table_purpose = match[1].strip().replace('`', '')
        table_structure = match[2].strip()

        tables_info[table_name] = {
            'table_purpose': table_purpose,
            'table_structure': table_structure
        }

    return tables_info


# 使用函数提取信息
file_path = 'introduction.txt'
tables_info = extract_table_info(file_path)

# 打印结果
for table_name, info in tables_info.items():
    print(f"Table Name: {table_name}")
    print(f"Purpose: {info['table_purpose']}")
    print(f"Structure: \n{info['table_structure']}")
