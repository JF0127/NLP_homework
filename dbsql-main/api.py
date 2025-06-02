from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dbsql.llm.chains.dbsql_answer import DBSQLAnswer
import uvicorn
# 新增 CORS 中间件
from fastapi.middleware.cors import CORSMiddleware  # <-- 添加这一行

app = FastAPI(title="Database Chat API")

# 添加 CORS 配置（必须放在所有路由定义之前）  <-- 新增部分
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源（生产环境建议指定具体域名）
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有方法（包括 OPTIONS）
    allow_headers=["*"],  # 允许所有请求头
)

# 初始化数据库处理器
db_handler = DBSQLAnswer(
    model="local",
    db_type="MySQL",
    db_host="localhost",
    db_port=3006,
    db_user="DB_MASTER",
    db_password="DB_CODE",
    db_name="DB_COMPANY",
)

class QuestionRequest(BaseModel):
    question: str

@app.post("/ask", response_model=str)
async def simple_chat(request: QuestionRequest):
    """
    简化版问答接口
    输入: 问题字符串
    输出: 答案字符串
    """
    try:
        # 调用核心处理逻辑
        _, response = db_handler.step_run(question=request.question)
        
        # 返回最终答案字符串
        return response
        
    except Exception as e:
        # 返回纯文本错误信息
        raise HTTPException(
            status_code=400,
            detail=f"处理失败: {str(e)}"
        )

if __name__ == "__main__":
    uvicorn.run(app, host="localhost", port=12256)