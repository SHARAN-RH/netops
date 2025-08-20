"""Logging configuration"""

import logging
import sys
from rich.logging import RichHandler
from .config import config

def setup_logging():
    """Setup application logging with Rich handler"""
    
    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, config.app.log_level.upper()),
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)]
    )
    
    # Configure specific loggers
    logger = logging.getLogger("mcp_network_upgrader")
    logger.setLevel(getattr(logging, config.app.log_level.upper()))
    
    return logger

# Initialize logging
logger = setup_logging()