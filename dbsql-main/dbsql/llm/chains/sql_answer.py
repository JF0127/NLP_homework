import os
from operator import itemgetter
from typing import List, Union, Tuple

from dotenv import load_dotenv
from langchain.chains import create_sql_query_chain
from langchain_community.tools.sql_database.tool import QuerySQLDataBaseTool
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_openai import ChatOpenAI
from loguru import logger

from dbsql import logger
from dbsql.dmdb import DMdb
from dbsql.llm.prompts.sql import QUESTION_PROMPT, ANSWER_PROMPT
from dbsql.utils import sql_extract

load_dotenv()

# TODO: 开放 LLM 配置参数
llm = ChatOpenAI(model="qwen-coder-plus",
                 openai_api_key=os.getenv("DASHSCOPE_API_KEY"),
                 openai_api_base=os.getenv("DASHSCOPE_API_BASE"))

# llm = ChatOpenAI(model=os.getenv("MODEL_NAME"),
#                  openai_api_key=os.getenv("API_KEY"),
#                  openai_api_base=os.getenv("API_BASE"))

# Notice: you can add prompt here. And the prompt should be added here.
question_prompt = PromptTemplate.from_template(QUESTION_PROMPT, partial_variables={'top_k': 10})
logger.info(f"question_prompt\n{str(question_prompt)}")
write_query = create_sql_query_chain(llm, DMdb, question_prompt)
logger.info(f"write_query\n{str(write_query)}")

execute_query = QuerySQLDataBaseTool(db=DMdb)
logger.info(f"execute_query\n{str(execute_query)}")

answer_prompt = PromptTemplate.from_template(ANSWER_PROMPT)
logger.info(f"answer_prompt\n{str(answer_prompt)}")
answer = answer_prompt | llm | StrOutputParser()
logger.info(f"answer\n{str(answer)}")

chain = (
        RunnablePassthrough.assign(query=write_query).assign(
            result=(itemgetter("query") | execute_query)
        )
        | answer
)


def step_run(question: str, splitter_len=60) -> tuple[str, str]:
    """分步骤运行并记录各步骤结果"""
    response = ["LLM response".center(splitter_len, "-")]
    sql_query_raw = write_query.invoke({"question": question})  # question input
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
        response.extend([f"query {i+1}: \n{query}" for i, query in enumerate(sql_queries)])

        response.append("execution result".center(splitter_len, "-"))

        successful_query = None
        execution_result = None

        for i, sql_query in enumerate(sql_queries):
            try:
                logger.info(f"try to execute query {i+1}: {sql_query}")
                result = execute_query.invoke({"query": sql_query})
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
        final_answer = answer.invoke({
            "user_question": question,
            "sql_query": successful_query,
            "sql_result": execution_result
        })
        response.append(final_answer)
        return "\n".join(response), final_answer


def chain_run(question: str) -> str:
    """执行 chain 调用"""
    try:
        process, response = step_run(question)
    except Exception as err:
        logger.error(err)
        return str(err)

    return process


def test():
    process = chain_run("有哪些城市名字？")
    print(process)




if __name__ == "__main__":
    test()
