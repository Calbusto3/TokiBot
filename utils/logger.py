import logging
from typing import Optional

_DEFAULT_LEVEL = logging.INFO


def get_logger(name: Optional[str] = None, level: int = _DEFAULT_LEVEL) -> logging.Logger:
    """Return a configured logger with a simple, consistent format.
    Safe to call multiple times; handlers won't multiply.
    """
    logger = logging.getLogger(name if name else "tokibot")
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler()
        fmt = "[%(asctime)s] %(levelname)s %(name)s: %(message)s"
        datefmt = "%Y-%m-%d %H:%M:%S"
        handler.setFormatter(logging.Formatter(fmt=fmt, datefmt=datefmt))
        logger.addHandler(handler)

    return logger
