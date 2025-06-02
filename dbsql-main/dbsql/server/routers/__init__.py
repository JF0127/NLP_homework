"""服务接口路由的汇集目录"""
from fastapi import APIRouter

from nlidb.server.routers import health, run_sql


# 主路由
main_router = APIRouter()
main_router.include_router(health.router)
main_router.include_router(run_sql.router)
