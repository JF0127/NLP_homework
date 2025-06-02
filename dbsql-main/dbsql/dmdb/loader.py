import os
from urllib.parse import quote_plus as urlquote

from dotenv import load_dotenv
from .dm_database import DMDatabase


def load_db() -> DMDatabase:
    """使用环境变量加载数据库"""
    load_dotenv()
    host = os.environ.get("DB_HOST", "127.0.0.1")
    port = os.environ.get("DB_PORT", "5236")
    user = os.environ.get("DB_USER", "XYCS")
    passwd = os.environ.get("DB_PASSWD", "123456789")
    name = os.environ.get("DB_NAME", "XYCS")
    passwd = urlquote(passwd)
    db_uri = f'jdbc:dm://{user}:{passwd}@{host}:{port}/{name}'
    return DMDatabase.from_uri(db_uri)


# 加载数据库实例
db: DMDatabase = load_db()


def get_schema() -> str:
    return db.get_table_info()


def run_query(query):
    return db.run(query)


if __name__ == "__main__":
    print(db.get_table_info())
    # print(run_query("SELECT * FROM users;"))
