import time
from typing import List, Literal, Any, Union, Dict
from pydantic import BaseModel, Field


class LidarPoint(BaseModel):
    """Normalized LiDAR point."""

    angle: float = Field(..., ge=0, le=360)
    distance: float = Field(..., ge=0)
    intensity: float = Field(..., ge=0)


class LidarScan(BaseModel):
    """Full 360-degree revolution batch."""

    timestamp: float = Field(default_factory=time.time)
    points: List[LidarPoint]


class LidarConfig(BaseModel):
    """Configuration for a single LiDAR unit."""

    type: str = Field(..., description="Device model, e.g., rplidar-c1")
    port: str
    baudrate: int = 460800
    timeout: int = 3
    motor_pwm: int = Field(600, ge=0, le=1023)


class NetworkConfig(BaseModel):
    """Global network settings for the service."""

    rest_port: int = Field(8000, ge=1024, le=65535)


class AppConfig(BaseModel):
    """Root configuration model matching your YAML structure."""

    lidar: List[LidarConfig]
    network: NetworkConfig


class WSMessage(BaseModel):
    """
    Standard envelope for all WebSocket communications.
    The 'type' field acts as a header for message routing.
    """
    type: Literal["lidar_scan", "system_status", "error"] = Field(
        ..., description="Type of the message payload"
    )
    data: Union[LidarScan, Dict[str, Any]] = Field(
        ..., description="The actual payload (Scan data or status info)"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "type": "lidar_scan",
                "data": {
                    "timestamp": 1704123456.789,
                    "points": [{"angle": 0.0, "distance": 150.5, "intensity": 45}]
                }
            }
        }
    }
