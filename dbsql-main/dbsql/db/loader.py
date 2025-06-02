import os
from urllib.parse import quote_plus as urlquote

from dotenv import load_dotenv
from langchain_community.utilities import SQLDatabase


def load_db() -> SQLDatabase:
    """使用环境变量加载数据库"""
    load_dotenv()
    host = os.environ.get("DB_HOST", "localhost")
    port = os.environ.get("DB_PORT", "3306")
    user = os.environ.get("DB_USER", "root")
    passwd = os.environ.get("DB_PASSWD", "jhl12735800")
    name = os.environ.get("DB_NAME", "NLP_DB_BY_TYPE")
    passwd = urlquote(passwd)
    db_uri = f'mysql+pymysql://{user}:{passwd}@{host}:{port}/{name}'
    return SQLDatabase.from_uri(db_uri)


# 加载数据库实例
db: SQLDatabase = load_db()


def get_schema() -> str:
    return db.get_table_info()


def run_query(query):
    return db.run(query)


if __name__ == "__main__":
    print(db.get_table_info())
    # print(run_query("SELECT * FROM users;"))
