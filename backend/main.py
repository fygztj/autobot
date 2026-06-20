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
from backend.task_manager import scheduler


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


# 启动/关闭时自动管理调度器
@app.on_event("startup")
async def on_startup():
    # 设置调度器的命令发送回调（复用 app_device_manager）
    from backend.app_client import app_device_manager

    async def _send_command(device_id: str, action: str, platform: str, params: dict):
        return await app_device_manager.send_command(
            device_id=device_id,
            action=action,
            platform=platform,
            params=params,
            timeout=300,  # 定时任务给更长的超时
        )

    scheduler.command_sender = _send_command
    await scheduler.start()


@app.on_event("shutdown")
async def on_shutdown():
    await scheduler.stop()


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
