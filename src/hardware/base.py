from abc import ABC, abstractmethod
from enum import Enum


class LidarStatus(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    READY = "ready"
    SCANNING = "scanning"
    ERROR = "error"


class BaseLidar(ABC):
    @abstractmethod
    def connect(self): ...

    @abstractmethod
    def start_scan(self, callback): ...

    @abstractmethod
    def stop_scan(self): ...

    @abstractmethod
    def get_status(self) -> LidarStatus: ...
