from http import HTTPStatus

from pydantic import BaseModel


class ApiResponse(BaseModel):
    """通用的服务接口响应格式"""
    code: int = HTTPStatus.OK
    success: bool = True
    message: str = ""
    data: dict = dict()
    data_list: list = list()
