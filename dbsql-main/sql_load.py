import mysql.connector
import os
import re


DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "password",
    "port": "3006"
    # "auth_plugin": "mysql_native_password"
}

DB_NAME = "DB_TEST"
DB_USER = "DBSQL"
PASSWORD = "12345678"
DEFINITION_DIR = "/home/tmp_user/projects/SQLData/ToMySQL/definition/XYCS"
DATA_DIR = "/home/tmp_user/projects/SQLData/ToMySQL/data/XYCS"


def fix_sql_content(content, tablename):
    replacements = {
        r'XYCS': r"DB_TEST", 
        r'"(\w+)"': r"`\1`",  
        r"\bVARCHAR2\b": "VARCHAR", 
        r"\bCLOB\b": "LONGTEXT",
        r"\bNUMBER\b": "INT",
        r"\bNOT CLUSTER\b": "",
        r'ALTER INDEX\s+(`?\w+`?)\.?(`?\w+`?)\s+VISIBLE': 
            r'ALTER TABLE \1.' + tablename + r' ALTER INDEX \2 VISIBLE',
        r'COMMENT\s+ON\s+TABLE\s+([`\w\.]+)\s+IS\s+\'(.*?)\'': 
            r"ALTER TABLE \1 COMMENT='\2'",
        r'COMMENT\s+ON\s+COLUMN\s+([`\w\.]+)\.([`\w]+)\.([`\w]+)\s+IS\s+\'(.*?)\'':
            r"ALTER TABLE \1.\2 MODIFY COLUMN \3 VARCHAR(127) COMMENT '\4'",
        r'CLUSTER (PRIMARY KEY\(`\w+?`\))\s+?ENABLE': r'\1',
        r'CHARACTER\(2048\)': r'LONGTEXT',
        r'VARCHAR\(\d{4}\)': r'LONGTEXT',
        r'VARCHAR\(2048\)': r'LONGTEXT',
        r'VARCHAR\(512\)': r'TEXT',
        r'VARCHAR\(256\)': r'TEXT',
        r'IDENTITY\(1,1\)': r'AUTO_INCREMENT PRIMARY KEY',
        r'CHARACTER\(\d{4}\)': r'TEXT',
        # r'\bTIMESTAMP$6$\b': 'TIMESTAMP(6)',  # 保留精度（需MySQL 5.6.4+）
    }

    for pattern, repl in replacements.items():
        content = re.sub(pattern, repl, content, flags=re.IGNORECASE)

    return content


def split_sql_script(content):
    pattern = re.compile(r"""
        (                       # 分组1：需要忽略分号的内容
            '(?:[^'\\]|\\.)*'   # 单引号字符串（支持转义符）
          | "(?:[^"\\]|\\.)*"   # 双引号字符串（支持转义符）
          | --.*?$              # 单行注释（-- 开头）
          | #.*?$               # 单行注释（# 开头）
          | /\*.*?\*/           # 多行注释（/*...*/）
        )
        | (;+)                  # 分组2：分号（作为语句分隔符）
    """, re.VERBOSE | re.MULTILINE | re.DOTALL)

    statements = []
    current = []
    for match in pattern.finditer(content):
        string_or_comment, semicolon = match.groups()
        if string_or_comment:
            current.append(match.group(0))
        elif semicolon:
            current.append(';')
            statements.append(''.join(current).strip())
            current = []
    if current:
        statements.append(''.join(current).strip())
    return statements


def execute_sql_files(cursor, dir_path):
    for filename in os.listdir(dir_path):
        if filename.endswith(".sql"):
            filepath = os.path.join(dir_path, filename)
            print(f"Processing {filepath}...")

            tablename = os.path.basename(filepath).split(".")[0]

            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
                fixed_content = fix_sql_content(content, tablename)

                statements = [
                    stmt.strip() for stmt in fixed_content.split(";") if stmt.strip()
                ]
                # statements = split_sql_script(content)

                for stmt in statements:
                    try:
                        cursor.execute(stmt)
                    except mysql.connector.Error as err:
                        print(
                            f"Error executing statement: {err}\nStatement: {stmt}"
                        )

def main():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        cursor.execute(f"DROP USER IF EXISTS '{DB_USER}'@'%'")
        cursor.execute(f"DROP USER IF EXISTS '{DB_USER}'@'localhost'")

        cursor.execute(f"DROP DATABASE IF EXISTS {DB_NAME}")

        cursor.execute(f"CREATE USER '{DB_USER}'@'localhost' IDENTIFIED BY '{PASSWORD}'")
        cursor.execute(f"CREATE USER '{DB_USER}'@'%' IDENTIFIED BY '{PASSWORD}'")

        cursor.execute(
            f"CREATE DATABASE IF NOT EXISTS {DB_NAME} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )

        cursor.execute(f"GRANT ALL PRIVILEGES ON {DB_NAME}.* TO '{DB_USER}'@'localhost'")
        cursor.execute(f"GRANT ALL PRIVILEGES ON {DB_NAME}.* TO '{DB_USER}'@'%'")

        cursor.execute("FLUSH PRIVILEGES")

        cursor.execute(f"USE {DB_NAME}")
        conn.commit()
        print(f"Database {DB_NAME} created/connected.")

        execute_sql_files(cursor, DEFINITION_DIR)
        conn.commit()
        print("Table definitions imported.")

        execute_sql_files(cursor, DATA_DIR)
        conn.commit()
        print("Data imported successfully.")

    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()
    finally:
        if "conn" in locals() and conn.is_connected():
            cursor.close()
            conn.close()
            print("Connection closed.")


if __name__ == "__main__":
    main()
