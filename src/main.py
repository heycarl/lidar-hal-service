import argparse
import asyncio
import uvicorn
import logging
import sys
from src.core.manager import LidarManager
from src.transports.rest_api import create_app
from src.utils.config_loader import load_app_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)

logger = logging.getLogger("Main")


async def main():
    parser = argparse.ArgumentParser(description="Lidar WEB Service")
    parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="Path to the YAML configuration file",
    )
    args = parser.parse_args()

    app_cfg = load_app_config(args.config)

    if not app_cfg.lidar:
        logger.error("No LiDAR configurations found in YAML")
        return

    lidar_manager = LidarManager(app_cfg.lidar[0])

    app = create_app(lidar_manager)

    uvicorn_config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=app_cfg.network.rest_port,
    )
    server = uvicorn.Server(uvicorn_config)

    logger.info("Service initialized. Starting API server...")

    try:
        # Run the FastAPI server
        await server.serve()
    finally:
        # 5. Graceful Shutdown logic
        logger.info("Service shutting down. Stopping hardware...")
        await lidar_manager.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


def run_app():
    """Entry point for the console script."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
