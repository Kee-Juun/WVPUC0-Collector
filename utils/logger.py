# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'logger.py'
# Bytecode version: 3.13.0rc3 (3571)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

"""\nLogging functionality for WVPUC0 Document Collector\n"""
import logging
from pathlib import Path
from datetime import datetime
class Logger:
    # ***<module>.Logger: Failure detected at line number 20 and instruction offset 88: Different bytecode
    """Handles logging functionality"""
    def __init__(self, log_dir: str='Downloads/WVPUC0 Collections/Logs'):
        # ***<module>.Logger.__init__: Failure: Compilation Error
        path = Path(log_dir)
        self.log_dir = path if path.is_absolute() else Path.home() / path
        self.log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.log_file = self.log_dir / f'Log_{timestamp}.txt'
        formatter = logging.Formatter(fmt='%(asctime)s - %(levelname)s - %(message)s', datefmt='%I:%M:%S %p')
        file_handler = logging.FileHandler(self.log_file)
        file_handler.setFormatter(formatter)
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        self.logger = logging.getLogger('WVPUC0')
        self.logger.setLevel(logging.INFO)
        if self.logger.handlers:
            self.logger.handlers.clear()
        self.logger.addHandler(file_handler)
        self.logger.addHandler(stream_handler)
        self.logger.propagate = False
    def info(self, message: str) -> None:
        """Log info message"""
        self.logger.info(message)
    def error(self, message: str) -> None:
        """Log error message"""
        self.logger.error(message)
    def warning(self, message: str) -> None:
        """Log warning message"""
        self.logger.warning(message)