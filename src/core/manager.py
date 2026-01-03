import asyncio
import logging
from typing import Any, List, Optional, Set

from src.hardware.pyrplidar_impl import PyRPlidarImpl

from .models import LidarConfig, LidarPoint, LidarScan

logger = logging.getLogger(__name__)


class LidarManager:
    def __init__(self, config: LidarConfig):
        self.config = config
        self._hal = PyRPlidarImpl(config)
        self._loop = asyncio.get_event_loop()
        self._subscribers: Set[asyncio.Queue] = set()

        self._last_scan: Optional[LidarScan] = None

    def subscribe(self) -> asyncio.Queue:
        """Create and return a new data queue for a transport (L3)."""
        queue = asyncio.Queue(maxsize=10)
        self._subscribers.add(queue)
        logger.info(f"New subscriber added. Total: {len(self._subscribers)}")
        return queue

    def unsubscribe(self, queue: asyncio.Queue):
        """Remove a transport queue from subscribers."""
        self._subscribers.discard(queue)
        logger.info(f"Subscriber removed. Total: {len(self._subscribers)}")

    def _raw_callback(self, measurements: List[Any]):
        """
        Callback triggered by L1 (Thread).
        Converts raw data and schedules push to async queues.
        """
        points = [
            LidarPoint(angle=m.angle, distance=m.distance, intensity=m.quality)
            for m in measurements
        ]
        scan = LidarScan(points=points)

        self._loop.call_soon_threadsafe(self._publish, scan)

    def _publish(self, scan: LidarScan):
        """Push scan to all subscriber queues and update the cache."""
        self._last_scan = scan

        for q in self._subscribers:
            if q.full():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            q.put_nowait(scan)

    async def start(self):
        """Initialize HAL and start scanning."""
        await asyncio.to_thread(self._hal.connect)
        self._hal.start_scan(callback=self._raw_callback)
        logger.info("LidarManager: Scanning started")

    async def stop(self):
        """Graceful shutdown."""
        await asyncio.to_thread(self._hal.disconnect)
        logger.info("LidarManager: Stopped")

    async def update_config(self, new_config: LidarConfig):
        """Apply new hardware settings on the fly."""
        if new_config.motor_pwm != self.config.motor_pwm:
            await asyncio.to_thread(self._hal.update_parameters, new_config.motor_pwm)
        self.config = new_config

    @property
    def status(self) -> str:
        """Public access to current hardware status."""
        return self._hal.get_status().value

    @property
    def subscriber_count(self) -> int:
        """Public access to the number of active data listeners."""
        return len(self._subscribers)

    @property
    def last_scan(self) -> Optional[LidarScan]:
        """Public access to the most recent LiDAR scan."""
        return self._last_scan
