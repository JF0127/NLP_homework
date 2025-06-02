from pydantic import BaseModel

class FastGPTRequest(BaseModel):
    """FastGPT的HTTP插件请求格式"""
    appId: str
    variables: dict
    data: dict
