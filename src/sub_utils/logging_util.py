# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adi Hezral <hezral@gmail.com>

import logging
import logging.handlers
import functools
import sys
import os
from typing import Callable, Any
from gi.repository import GLib

# Define a custom level for Verbose logging
VERBOSE_LEVEL = 5
logging.addLevelName(VERBOSE_LEVEL, "VERBOSE")

def verbose(self, message, *args, **kws):
    if self.isEnabledFor(VERBOSE_LEVEL):
        self._log(VERBOSE_LEVEL, message, args, **kws)

logging.Logger.verbose = verbose

def init_logging(debug: bool = False, verbose_flag: bool = False):
    """
    Initialize the logging system.
    
    :param debug: If True, set level to DEBUG.
    :param verbose_flag: If True, set level to VERBOSE (even lower than DEBUG).
    """
    level = logging.INFO
    if debug:
        level = logging.DEBUG
    if verbose_flag:
        level = VERBOSE_LEVEL
        
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    handlers = [logging.StreamHandler(sys.stdout)]
    
    # Setup log file in user's data directory
    try:
        data_dir = GLib.get_user_data_dir()
        app_log_dir = os.path.join(data_dir, "quickey", "logs")
        os.makedirs(app_log_dir, exist_ok=True)
        log_file = os.path.join(app_log_dir, "quickey.log")
        
        # Rotating file handler (5 MB per file, keep 3 backups)
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=5*1024*1024, backupCount=3
        )
        file_handler.setFormatter(logging.Formatter(log_format))
        handlers.append(file_handler)
    except Exception as e:
        print(f"Failed to initialize file logging: {e}", file=sys.stderr)

    logging.basicConfig(
        level=level,
        format=log_format,
        handlers=handlers
    )
    
    logger = logging.getLogger("quickey")
    logger.info(f"Logging initialized. Level: {logging.getLevelName(level)}")
    if 'log_file' in locals():
        logger.info(f"Log file: {log_file}")

def get_logger(name: str):
    """Get a logger instance with the project prefix."""
    return logging.getLogger(f"quickey.{name}")

def log_function_calls(func: Callable) -> Callable:
    """Decorator to log function entry and exit at VERBOSE level."""
    logger = logging.getLogger("quickey.verbose")
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # Extract class name if it's a method
        cls_name = ""
        if args and hasattr(args[0], '__class__'):
            cls_name = f"{args[0].__class__.__name__}."
            
        func_name = f"{cls_name}{func.__name__}"
        
        if logger.isEnabledFor(VERBOSE_LEVEL):
            logger.verbose(f"Entering: {func_name}")
            
        try:
            result = func(*args, **kwargs)
            if logger.isEnabledFor(VERBOSE_LEVEL):
                logger.verbose(f"Exiting: {func_name} (Success)")
            return result
        except Exception as e:
            if logger.isEnabledFor(VERBOSE_LEVEL):
                logger.verbose(f"Exiting: {func_name} (Failed: {e})")
            raise
            
    return wrapper
