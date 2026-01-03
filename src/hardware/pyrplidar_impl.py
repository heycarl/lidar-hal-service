import logging
import threading
import time
from typing import Callable, List, Optional, Any

from pyrplidar import PyRPlidar, PyRPlidarProtocolError, PyRPlidarConnectionError
from .base import BaseLidar, LidarStatus
from ..core.models import LidarConfig

logger = logging.getLogger(__name__)


class PyRPlidarImpl(BaseLidar):
    """
    Hardware Abstraction Layer for RPLIDAR C1.
    Handles low-level serial communication, motor control, and data batching.
    """

    # Hardware constraints for RPLIDAR C1 (Model 65)
    MIN_PWM = 0
    MAX_PWM = 1023
    DEFAULT_PWM = 600

    def __init__(self, config: LidarConfig):
        self._port = config.port
        self._baudrate = config.baudrate
        self._timeout = config.timeout
        self._motor_pwm = config.motor_pwm
        self._warmup_seconds = 3.0

        self._lidar = PyRPlidar()
        self._status = LidarStatus.DISCONNECTED

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._callback: Optional[Callable[[List[Any]], None]] = None

    def get_status(self) -> LidarStatus:
        return self._status

    def connect(self):
        """Establish connection and initialize the motor with parameters."""
        logger.info(f"Connecting to LiDAR on {self._port} (Baud: {self._baudrate})...")
        self._status = LidarStatus.CONNECTING
        try:
            self._lidar.connect(
                port=self._port, baudrate=self._baudrate, timeout=self._timeout
            )

            # Get device information for logging purposes
            info = self._lidar.get_info()
            health = self._lidar.get_health()
            logger.info(f"Connected. Model: {info.model}, S/N: {info.serialnumber}")
            logger.info(f"LiDAR Health: {health.status}")

            # Set PWM (motor speed intensity)
            logger.info(f"Starting motor with PWM: {self._motor_pwm}...")
            self._lidar.set_motor_pwm(self._motor_pwm)

            # Warm up the motor to stabilize the speed
            if self._warmup_seconds > 0:
                logger.info(f"Warming up motor ({self._warmup_seconds}s)...")
                time.sleep(self._warmup_seconds)

            self._status = LidarStatus.READY
            logger.info("LiDAR HAL is ready.")

        except PyRPlidarConnectionError as e:
            self._status = LidarStatus.ERROR
            logger.error(f"Physical connection error to port {self._port}: {e}")
            raise
        except Exception as e:
            self._status = LidarStatus.ERROR
            logger.error(f"Unexpected error during LiDAR initialization: {e}")
            raise

    def _run_scan_loop(self):
        """Internal loop for reading data with batching by rotations."""
        batch = []
        try:
            # Start scanning (optional parameters for scan mode can be added here)
            scan_generator = self._lidar.start_scan()
            logger.info("Scan generator started.")

            for measurement in scan_generator():
                if self._stop_event.is_set():
                    break

                # Check for new rotation (use corrected start_flag)
                if measurement.start_flag and batch:
                    if self._callback:
                        self._callback(batch)
                    batch = []

                # Filter by quality (valid points)
                if measurement.quality > 0:
                    batch.append(measurement)

        except PyRPlidarProtocolError as e:
            logger.error(f"LiDAR Protocol error: {e}")
            self._status = LidarStatus.ERROR
        except Exception as e:
            logger.error(f"Critical failure in LiDAR thread: {e}", exc_info=True)
            self._status = LidarStatus.ERROR
        finally:
            self._cleanup()

    def _cleanup(self):
        """Safely stop the motor and de-initialize the device."""
        try:
            self._lidar.stop()
            self._lidar.set_motor_pwm(0)
            logger.info("Motor and scan stopped.")
        except Exception as e:
            logger.warning(f"Cleanup error (possible disconnect): {e}")

        if self._status != LidarStatus.ERROR:
            self._status = LidarStatus.READY

    def start_scan(self, callback: Callable[[List[Any]], None]):
        """Start background scanning thread."""
        if self._status not in [LidarStatus.READY, LidarStatus.ERROR]:
            logger.error(f"Cannot start scan: Device in state {self._status}")
            return

        self._callback = callback
        self._stop_event.clear()

        self._thread = threading.Thread(
            target=self._run_scan_loop, name=f"Lidar-{self._port[-4:]}", daemon=True
        )
        self._thread.start()
        self._status = LidarStatus.SCANNING

    def stop_scan(self):
        """Stop the scanning thread."""
        if self._thread and self._thread.is_alive():
            self._stop_event.set()
            self._thread.join(timeout=self._timeout + 1.0)
            logger.info("Scan thread joined.")

    def disconnect(self):
        """Release the port and disconnect the device."""
        self.stop_scan()
        try:
            self._lidar.disconnect()
            self._status = LidarStatus.DISCONNECTED
            logger.info("Disconnected.")
        except Exception as e:
            logger.error(f"Disconnect error: {e}")

    def _validate_pwm(self, pwm: int) -> int:
        """Verify PWM is within RPLIDAR C1 physical limits."""
        if not (self.MIN_PWM <= pwm <= self.MAX_PWM):
            logger.warning(
                f"PWM {pwm} is out of hardware bounds. Clipping to [{self.MIN_PWM}, {self.MAX_PWM}]"
            )
            return max(self.MIN_PWM, min(pwm, self.MAX_PWM))
        return pwm

    def update_parameters(self, motor_pwm: Optional[int] = None):
        """
        Safety sequence to update hardware parameters:
        Stop Scan -> Stop Motor -> Apply New PWM -> Start Motor -> Resume Scan.
        """
        if motor_pwm is None:
            return

        new_pwm = self._validate_pwm(motor_pwm)
        if new_pwm == self._motor_pwm:
            return

        logger.info(f"Reconfiguring motor: {self._motor_pwm} -> {new_pwm}")

        # 1. Store state and stop active processes
        is_scanning = self._status == LidarStatus.SCANNING
        callback_ref = self._callback

        if is_scanning:
            self.stop_scan()

        # 2. Complete hardware reset for PWM change
        try:
            self._lidar.stop()
            time.sleep(self._warmup_seconds)  # Allow rotor to slow down

            self._motor_pwm = new_pwm
            self._lidar.set_motor_pwm(self._motor_pwm)

            # 3. Restore previous state if it was scanning
            if is_scanning and callback_ref:
                self.start_scan(callback_ref)

        except Exception as e:
            logger.error(f"Failed to update hardware parameters: {e}")
            self._status = LidarStatus.ERROR
