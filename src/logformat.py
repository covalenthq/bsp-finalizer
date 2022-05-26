import logging
import os
import pathlib
from logging.handlers import TimedRotatingFileHandler

class LogFormat(logging.Formatter):

    grey = "\x1b[38;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    format = "%(asctime)s - %(levelname)s - %(name)s - (%(filename)s:%(lineno)d) %(message)s "

    FORMATS = {
        logging.DEBUG: grey + format + reset,
        logging.INFO: grey + format + reset,
        logging.WARNING: yellow + format + reset,
        logging.ERROR: red + format + reset,
        logging.CRITICAL: bold_red + format + reset
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)

    @staticmethod
    def init_logger(class_name, console_mode=False):
        logger = logging.getLogger(class_name)
        logger.setLevel(logging.DEBUG)
        logs_dir = pathlib.Path(os.getcwd()) / 'logs' / class_name
        logs_dir.mkdir(mode=0o755, parents=True, exist_ok=True)
        log_path_prefix = str(logs_dir / 'log')
        ch = TimedRotatingFileHandler(log_path_prefix, when="D", interval=1)
        ch.suffix = "%Y-%m-%d_%H-%M-%S.log"
        # ch = logging.FileHandler("logs.txt")
        ch.setLevel(logging.DEBUG)
        format = LogFormat()

        ch.setFormatter(format)

        logger.addHandler(ch)
        if console_mode:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(format)
            logger.addHandler(console_handler)
        logger.propagate = False

        return logger
