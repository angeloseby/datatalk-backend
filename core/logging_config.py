import logging
import sys

from config.settings import settings


def setup_logging() -> None:
    """
    Configure application-wide logging.

    - Development: DEBUG level, human-readable format
    - Production:  INFO level, structured format with timestamps
    """
    level = logging.DEBUG if settings.is_development else logging.INFO

    fmt = (
        "%(asctime)s │ %(levelname)-8s │ %(name)-28s │ %(message)s"
        if settings.is_development
        else "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt, datefmt="%H:%M:%S"))

    # Configure the root logger for the project
    root_logger = logging.getLogger("datatalk")
    root_logger.setLevel(level)
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.propagate = False

    # Quiet noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("groq").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Get a namespaced logger under the 'datatalk' hierarchy.

    Usage:
        from core.logging_config import get_logger
        logger = get_logger(__name__)
        logger.info("Server started")
    """
    return logging.getLogger(f"datatalk.{name}")
