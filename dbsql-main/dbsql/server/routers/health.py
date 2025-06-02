from fastapi import APIRouter

from dbsql.server.models.output import ApiResponse


router = APIRouter()


@router.get("/", response_model=ApiResponse, status_code=200)
def health() -> ApiResponse:
    """服务健康状况检查接口"""
    return ApiResponse(message="服务运行中...")
