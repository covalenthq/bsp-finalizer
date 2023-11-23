import logging
import sys
import functools


class LogFormat(logging.Formatter):
    ANSI_RESET = "\x1b[0m"
    ANSI_BOLD = "\x1b[1m"
    ANSI_RED = "\x1b[31m"
    ANSI_YELLOW = "\x1b[33m"

    FMT_TEMPLATE = "%(levelname)s %(name)s (%(filename)s:%(lineno)d) - %(message)s"

    FORMATTERS = {
        logging.DEBUG: logging.Formatter(FMT_TEMPLATE + ANSI_RESET),
        logging.INFO: logging.Formatter(FMT_TEMPLATE + ANSI_RESET),
        logging.WARNING: logging.Formatter(ANSI_YELLOW + FMT_TEMPLATE + ANSI_RESET),
        logging.ERROR: logging.Formatter(ANSI_RED + FMT_TEMPLATE + ANSI_RESET),
        logging.CRITICAL: logging.Formatter(
            ANSI_BOLD + ANSI_RED + FMT_TEMPLATE + ANSI_RESET
        ),
    }

    def format(self, record):
        formatter = self.FORMATTERS.get(record.levelno)
        return formatter.format(record)


@functools.cache
def get_logger(class_name):
    return _build_logger(class_name)


def _build_logger(class_name):
    logger = logging.getLogger(class_name)

    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(LogFormat())

    logger.addHandler(ch)

    return logger
