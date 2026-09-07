# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'logger.py'
# Bytecode version: 3.13.0rc3 (3571)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

"""\nLogging functionality for WVPUC0 Document Collector\n"""
import logging
import sys
from pathlib import Path
from datetime import datetime


class ConsoleSafeFormatter(logging.Formatter):
    """Replace characters unsupported by the active Windows console encoding."""

    def __init__(self, *args, console_encoding: str | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.console_encoding = console_encoding or 'utf-8'

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        return message.encode(self.console_encoding, errors='replace').decode(
            self.console_encoding,
            errors='replace',
        )


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
        log_format = '%(asctime)s - %(levelname)s - %(message)s'
        date_format = '%I:%M:%S %p'
        formatter = logging.Formatter(fmt=log_format, datefmt=date_format)
        file_handler = logging.FileHandler(self.log_file, encoding='utf-8', errors='replace')
        file_handler.setFormatter(formatter)
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(ConsoleSafeFormatter(
            fmt=log_format,
            datefmt=date_format,
            console_encoding=getattr(sys.stderr, 'encoding', None),
        ))
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
