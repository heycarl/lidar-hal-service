import logging
from typing import Any, Dict

from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status

from src.core.manager import LidarManager
from src.core.models import LidarConfig, LidarScan, WSMessage

logger = logging.getLogger(__name__)


def create_app(manager: LidarManager) -> FastAPI:
    """
    Creates a FastAPI application with professional OpenAPI documentation
    and WebSocket support for real-time telemetry.
    """
    app = FastAPI(
        title="LIDAR Service API",
        version="1.0.0",
        description="Service for hardware lifecycle management and real-time data streaming.",
        contact={
            "name": "Lidar Service Maintainer",
        },
    )

    # --- SYSTEM & STATUS ---

    @app.get(
        "/status",
        tags=["System"],
        summary="Get system state",
        response_description="Returns current hardware status, active configuration, "
        "and subscriber count.",
    )
    async def get_status() -> Dict[str, Any]:
        """
        Retrieves the current operational state of the LiDAR.
        - **status**: Current state (disconnected, ready, scanning, error).
        - **config**: The active hardware parameters (PWM, port, etc.).
        - **active_subscribers**: Number of clients currently connected
        via WebSocket or other transports.
        """
        return {
            "status": manager.status,
            "config": manager.config.model_dump(),
            "active_subscribers": manager.subscriber_count,
        }

    # --- HARDWARE CONTROL ---

    @app.post(
        "/start",
        tags=["Hardware Control"],
        summary="Start LiDAR scanning",
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def start_lidar():
        """
        Initiates the LiDAR rotation and data acquisition.
        1. Powers up the motor.
        2. Waits for stabilization (warmup).
        3. Spawns the background scanning thread.
        """
        try:
            await manager.start()
            return {"message": "LiDAR started successfully"}
        except Exception as e:
            logger.error(f"Failed to start LiDAR: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/stop", tags=["Hardware Control"], summary="Stop LiDAR scanning")
    async def stop_lidar():
        """
        Safely shuts down the scanning process.
        - Terminates the scanning thread.
        - Powers down the motor (PWM set to 0).
        """
        try:
            await manager.stop()
            return {"message": "LiDAR stopped successfully"}
        except Exception as e:
            logger.error(f"Failed to stop LiDAR: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # --- CONFIGURATION ---

    @app.put("/config", tags=["Configuration"], summary="Update hardware parameters")
    async def update_configuration(
        new_config: LidarConfig = Body(
            ...,
            examples=[
                {
                    "type": "rplidar-c1",
                    "port": "/dev/ttyUSB0",
                    "baudrate": 460800,
                    "timeout": 3,
                    "motor_pwm": 660,
                }
            ],
        ),
    ):
        """
        Updates the motor PWM and communication settings.

        **Important:** This triggers a hardware re-initialization sequence:
        `Stop Scan -> Stop Motor -> Apply PWM -> Start Motor -> Warmup -> Resume Scan`.
        """
        try:
            await manager.update_config(new_config)
            return {
                "message": "Configuration applied",
                "current_config": manager.config,
            }
        except Exception as e:
            logger.error(f"Config update failed: {e}")
            raise HTTPException(status_code=400, detail=f"Invalid configuration: {e}")

    # --- DATA & STREAMING ---

    @app.get(
        "/scan/latest",
        tags=["Data"],
        summary="Get the most recent LiDAR scan",
        response_model=LidarScan,
        responses={
            200: {"description": "Successfully retrieved the last completed 360° scan."},
            404: {"description": "No scan data available (device might be warming up or stopped)."},
        },
    )
    async def get_latest_scan():
        """
        Returns the last successfully completed 360-degree rotation batch.
        Use this for snapshots or low-frequency monitoring.
        """
        scan = manager.last_scan
        if scan is None:
            raise HTTPException(
                status_code=404, detail="No scan data available. Is the LiDAR scanning?"
            )
        return scan

    @app.websocket("/ws/scan")
    async def websocket_endpoint(websocket: WebSocket):
        """
        ### WebSocket: Real-time Data Stream
        Streams LiDAR points immediately as they are processed (one packet per revolution).

        **Data Format:**
        All messages follow the `WSMessage` schema:
        - `type`: "lidar_scan"
        - `data`: Full `LidarScan` object.

        **Flow Control:**
        Utilizes a 'Drop Oldest' policy. If the client falls behind,
        stale scans are discarded to ensure minimum latency.
        """
        await websocket.accept()

        # Subscribe to L2 Manager
        queue = manager.subscribe()
        logger.info(f"WebSocket client connected: {websocket.client}")

        try:
            while True:
                # Fetch next scan from the fan-out queue
                scan = await queue.get()

                message = WSMessage(type="lidar_scan", data=scan)
                await websocket.send_json(message.model_dump())

                queue.task_done()

        except WebSocketDisconnect:
            logger.info(f"WebSocket client disconnected: {websocket.client}")
        except Exception as e:
            logger.error(f"WebSocket internal error: {e}")
        finally:
            manager.unsubscribe(queue)

    return app
