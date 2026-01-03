import yaml
import logging
from src.core.models import AppConfig

logger = logging.getLogger(__name__)


def load_app_config(path: str) -> AppConfig:
    with open(path, "r") as f:
        data = yaml.safe_load(f)

    return AppConfig(**data)
