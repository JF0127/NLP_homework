from fastapi import FastAPI

from dbsql.server.routers import main_router


# 主服务
app = FastAPI(
    title="LLM demo",
    version="0.0.1"
)
app.include_router(main_router)
