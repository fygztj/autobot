"""
AutoBot - iOS App 自动化机器人
主入口（仅保留 App WebSocket 自动化系统）
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uvicorn
from loguru import logger

from backend.config import config
from backend.api.routes import app


def setup_logging():
    """配置日志"""
    logger.remove()
    logger.add(
        sys.stderr,
        level="INFO",
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
    )
    log_dir = os.path.join(config.BASE_DIR, "logs")
    os.makedirs(log_dir, exist_ok=True)
    logger.add(
        os.path.join(log_dir, "autobot_{time:YYYY-MM-DD}.log"),
        level="DEBUG",
        rotation="10 MB",
        retention="7 days",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
    )


def initialize():
    """初始化系统"""
    logger.info("=" * 50)
    logger.info("AutoBot iOS 自动化助手 启动中...")
    logger.info("=" * 50)

    logger.info(f"Web 管理面板: http://localhost:{config.WEB_PORT}")
    logger.info(f"WebSocket 端点: ws://localhost:{config.WEB_PORT}/ws/app/connect")
    logger.info("AutoBot 启动完成！")


def main():
    """主函数"""
    setup_logging()
    initialize()

    uvicorn.run(
        app,
        host=config.WEB_HOST,
        port=config.WEB_PORT,
        log_level="info",
        access_log=False,
    )


if __name__ == "__main__":
    main()
