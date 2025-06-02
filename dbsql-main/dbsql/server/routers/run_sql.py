from loguru import logger
from fastapi import APIRouter

from dbsql.server.models.input import FastGPTRequest
from dbsql.server.models.output import ApiResponse
from dbsql.llm.chains.sql_answer import chain_run


router = APIRouter()


@router.post("/sql/run")
async def run_sql(request: FastGPTRequest):
    """执行 SQL 生成答案接口"""
    logger.debug(f"FastGPTRequest: {request}")

    question = request.data.get("q", None)
    if not question:
        return ApiResponse(
            success=False,
            message="未发现question字段，或内容为空。"
        )
    
    logger.info(f"输入问题：{question}")
    answer = chain_run(question)
    logger.info(f"最终回复：{answer}")
    response = ApiResponse(
        # 适配FastGPT引用格式
        data_list=[{"q": question, "a": answer}]
    )
    return response
