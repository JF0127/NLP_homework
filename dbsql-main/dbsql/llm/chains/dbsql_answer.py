import json
import os
from operator import itemgetter
import re
from typing import Tuple

from dotenv import load_dotenv
from langchain_community.tools.sql_database.tool import QuerySQLDataBaseTool
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnablePassthrough
from loguru import logger

from dbsql import logger
from dbsql.llm.chains.base import DBSQLAnswerBase
from dbsql.llm.chains.query import create_sql_query_chain_with_limit
from dbsql.llm.prompts.sql import (
    TABLE_QUERY,
    TABLE_PROMPT,
    QUESTION_PROMPT,
    ANSWER_PROMPT,
)
from dbsql.utils import sql_extract

load_dotenv()


class DBSQLAnswer(DBSQLAnswerBase):
    def __init__(
        self,
        model: str = "deepseek-ai",
        db_type: str = "DaMeng",  # MySQL
        db_host: str = "127.0.0.1",
        db_port: int = 3006,
        db_user: str = "DBSQL",
        db_password: str = "12345678",
        db_name: str = "DBTEST",
    ):
        super().__init__(
            model, db_type, db_host, db_port, db_user, db_password, db_name
        )
        self.table_info_path = "/home/jhl/Desktop/Course/NLP/data/table_info.json"
        self.table_info = None
        self.state_check()

        self.table_prompt = PromptTemplate.from_template(TABLE_PROMPT)
        self.sql_prompt = PromptTemplate.from_template(
            QUESTION_PROMPT, partial_variables={"top_k": 10}
        )
        self.write_query = create_sql_query_chain_with_limit(
            self.llm, self.db, self.table_prompt, self.sql_prompt, self.table_info
        )

        self.execute_query = QuerySQLDataBaseTool(db=self.db)

        self.answer_prompt = PromptTemplate.from_template(ANSWER_PROMPT)
        self.answer = self.answer_prompt | self.llm | StrOutputParser()

        self.chain = (  # Not used now
            RunnablePassthrough.assign(query=self.write_query).assign(
                result=(itemgetter("query") | self.execute_query)
            )
            | self.answer
        )

    def get_table_extra_info(self, table: str) -> str:
        message = [
            ("system", "you are a useful helper in table information analyse."),
            (
                "human",
                TABLE_QUERY.format(
                    table_name=table, table_info=self.db.get_table_info([table])
                ),
            ),
        ]
        ai_msg = self.llm.invoke(message)
        reply = ai_msg.content

        extract_pattern = re.compile(r"-*?([A-Z_]+).*?: (.+)")

        table_info = dict()
        main_con = reply.split("表用途")[-1]
        main_con, items = main_con.split("表结构")
        table_info["表用途"] = main_con.strip()
        table_info["表结构"] = dict()

        lines = items.split("\n")
        for line in lines:
            test = re.findall(extract_pattern, line)
            if test != [] : 
                id, state = re.findall(extract_pattern, line)[0]
                table_info["表结构"][id] = state.strip()

        return table_info

    def state_check(self):
        if self.table_info is not None:
            return

        table_info = None
        if os.path.exists(self.table_info_path):
            try:
                with open(self.table_info_path, "r", encoding='utf-8') as f:
                    table_info = json.load(f)
            except Exception as e:
                print(f"Raise Error:\n{str(e)}")
                table_info = None

        if table_info is None:
            table_info = dict()
            for table in self.db.get_usable_table_names():
                table_info[table] = self.get_table_extra_info(table)
        else:
            for table in self.db.get_usable_table_names():
                if table not in table_info.keys():
                    table_info[table] = self.get_table_extra_info(table)

        with open(self.table_info_path, "w", encoding='utf-8') as f:
            json.dump(table_info, f)
        self.table_info = table_info

    def step_run(self, question: str, splitter_len=60) -> Tuple[str, str]:
        response = ["llm response".center(splitter_len, "-")]
        # table_choice = self.table_prompt.invoke({})

        # response.append("llm response".center(splitter_len, "-"))
        sql_query_raw = self.write_query.invoke(
            {"question": question}
        )  # question input
        logger.info(f"llm response\n{str(sql_query_raw)}")
        response.append(sql_query_raw)

        sql_queries = sql_extract(sql_query_raw)
        if not sql_queries:
            logger.error("cannot extract valid SQL query!")
            response.append("I do not know")

            response.append("execution result".center(splitter_len, "-"))
            response.append("None")

            response.append("final response".center(splitter_len, "-"))
            response.append("I do not know")
            return "\n".join(response), "I do not know"

        else:
            sql_queries_str = "\n".join(sql_queries)
            logger.info(f"extract valid SQL queries: \n{sql_queries_str}")
            response.extend(
                [f"query {i + 1}: \n{query}" for i, query in enumerate(sql_queries)]
            )

            response.append("execution result".center(splitter_len, "-"))

            successful_query = None
            execution_result = None

            for i, sql_query in enumerate(sql_queries):
                try:
                    logger.info(f"try to execute query {i + 1}: {sql_query}")
                    result = self.execute_query.invoke({"query": sql_query})
                    if result.startswith("Error"):
                        raise RuntimeError(result)

                    successful_query = sql_query
                    execution_result = result
                    break
                except Exception as e:
                    logger.error(f"query {i + 1} execute failed: {str(e)}")
                    response.append(f"query {i + 1} execute failed")

            if not successful_query:
                logger.error("all queries execute failed!")
                response.append("all queries execute failed")

                response.append("final response".center(splitter_len, "-"))
                response.append("I do not know")
                return "\n".join(response), "I do not know"

            response.append(f"successful query: \n{successful_query}")
            response.append(f"successful execution: \n{execution_result}")

            response.append("final response".center(splitter_len, "-"))
            final_answer = self.answer.invoke(
                {
                    "user_question": question,
                    "sql_query": successful_query,
                    "sql_result": execution_result,
                }
            )
            response.append(final_answer)
            return "\n".join(response), final_answer


if __name__ == "__main__":
    dbsql_answer = DBSQLAnswer(model="glm4")
    dbsql_answer.state_check()
    question = "有哪些人员？"
    dbsql_answer.chain_run(question)
