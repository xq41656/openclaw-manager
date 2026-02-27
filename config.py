from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    # 服务配置
    APP_NAME: str = "OpenClaw Manager"
    APP_VERSION: str = "1.0.0"
    
    # 端口池配置 (OpenClaw Gateway 默认 18789，映射到宿主机端口池)
    PORT_POOL_START: int = 18800
    PORT_POOL_END: int = 18900
    GATEWAY_INTERNAL_PORT: int = 18789
    
    # 数据库
    DATABASE_URL: str = "sqlite:///./openclaw_manager.db"
    
    # OpenClaw 镜像
    DEFAULT_OPENCLAW_IMAGE: str = "openclaw/openclaw:latest"
    
    # 存储路径
    DATA_DIR: str = "./data"
    BACKUP_DIR: str = "./backups"
    
    class Config:
        env_file = ".env"

settings = Settings()
