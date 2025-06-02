import os
from typing import Tuple
from dotenv import load_dotenv
from abc import ABC, abstractmethod
from urllib.parse import quote_plus as urlquote

from langchain_openai import ChatOpenAI
from langchain_community.utilities import SQLDatabase

from dbsql.dmdb.dm_database import DMDatabase
from langchain_community.chat_models import ChatOllama
load_dotenv()


class DBSQLAnswerBase(ABC):
    def __init__(self,
                 model: str = 'deepseek-ai',
                 db_type: str = "DaMeng",
                 db_host: str = "127.0.0.1",
                 db_port: int = 5236,
                 db_user: str = "XYCS",
                 db_password: str = "123456789",
                 db_name: str = "XYCS"):
        self.model = model
        self.llm = self.get_llm()
        self.db_type = db_type
        self.db = self.get_db(db_host, db_port, db_user, db_password, db_name)

    def get_llm(self):
        if 'qwen' in self.model:
            llm = ChatOpenAI(model=self.model,
                             openai_api_key=os.getenv("DASHSCOPE_API_KEY"),
                             openai_api_base=os.getenv("DASHSCOPE_API_BASE"))
            return llm
        elif 'local' in self.model:
            llm = ChatOllama(model="deepseek-r1:14b",
                             base_url="https://u354342-baf8-f3ff1b79.bjc1.seetacloud.com:8443")
            return llm
        else:
            raise NotImplementedError("Unsupported model. Supported models are: \n1). qwen* \n2). local")

    def get_db(self, host, port, user, password, db_name):
        if self.db_type == "DaMeng":
            db = DMDatabase(
                host=host,
                port=port,
                user=user,
                password=password,
                database=db_name
            )
            return db
        elif self.db_type == "MySQL":
            password = urlquote(password)
            db_uri = f'mysql+pymysql://{user}:{password}@{host}:{port}/{db_name}'
            return SQLDatabase.from_uri(db_uri)
        else:
            raise NotImplementedError("Unsupported DB Type")

    @abstractmethod
    def step_run(self, question: str, splitter_len=60) -> Tuple[str, str]:
        pass

    def chain_run(self, question: str) -> str:
        """执行 chain 调用"""
        # try:
        process, response = self.step_run(question)
        # except Exception as err:
        #     logger.error(err)
        #     return str(err)

        return process
