"""
autobot - 移动端自动化机器人
主入口
"""

import sys
import os
import threading

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uvicorn
from loguru import logger

from backend.config import config
from backend.device_manager import device_manager
from backend.tasks.scheduler import task_scheduler
from backend.vision.ocr import ocr_engine


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
    """初始化系统各组件"""
    logger.info("=" * 50)
    logger.info("autobot 移动端自动化机器人 启动中...")
    logger.info("=" * 50)

    # 确保目录存在
    config.ensure_dirs()

    # 初始化 OCR 引擎（异步加载以避免阻塞启动）
    def _init_ocr():
        try:
            ocr_engine.initialize()
            logger.info("OCR 引擎就绪")
        except Exception as e:
            logger.warning(f"OCR 引擎初始化失败（文字识别功能不可用）: {e}")

    threading.Thread(target=_init_ocr, daemon=True).start()

    # 扫描设备
    device_manager.refresh()
    logger.info(f"发现 {device_manager.get_device_count()} 台设备")

    # 启动设备扫描
    device_manager.start_scan()

    # 启动任务调度器
    task_scheduler.start()

    # 设备连接/断开回调（可选）
    device_manager.on_connected(
        lambda serial: logger.info(f"设备连接回调: {serial}")
    )
    device_manager.on_disconnected(
        lambda serial: logger.warning(f"设备断开回调: {serial}")
    )

    logger.info(f"Web 管理面板: http://localhost:{config.WEB_PORT}")
    logger.info("autobot 启动完成！")


def main():
    """主函数"""
    setup_logging()
    initialize()

    # 启动 FastAPI Web 服务
    from backend.api.routes import app

    uvicorn.run(
        app,
        host=config.WEB_HOST,
        port=config.WEB_PORT,
        log_level="info",
        access_log=False,
    )


if __name__ == "__main__":
    main()