import logging
import sys


class DefaultFormatter(logging.Formatter):
    COLORS = {
        logging.DEBUG: '\033[97m',  # Blue
        logging.INFO: '\033[97m',  # Blue
        logging.WARNING: '\033[93m',  # Yellow
        logging.ERROR: '\033[91m',  # Red
        logging.CRITICAL: '\033[91m',  # Red
    }

    RESET_SEQ = '\033[0m'

    def format(self, record):
        log_color = self.COLORS.get(record.levelno)
        logger_name = record.name
        logger_datetime = self.formatTime(record, self.datefmt)
        log_level = record.levelname
        log_message = record.getMessage()
        log_format = '{}{} - [{}] - {} - {}{}'.format(log_color, logger_datetime, logger_name, log_level, log_message,
                                                  self.RESET_SEQ)
        return log_format


class OpenRailsLogFormatter(DefaultFormatter):
    COLORS = {
        logging.DEBUG: '\033[94m',  # Blue
        logging.INFO: '\033[94m',  # Blue
        logging.WARNING: '\033[93m',  # Yellow
        logging.ERROR: '\033[91m',  # Red
        logging.CRITICAL: '\033[91m',  # Red
    }

    RESET_SEQ = '\033[0m'

SERVER_CONNECT_LOG = "Server Connector"
OPENRAILS_LOGGER = "OpenRails Application"

def get_server_connector_log():
    log = logging.getLogger(SERVER_CONNECT_LOG)
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(DefaultFormatter())
    # # avoid adding multiple handlers:
    # if not log.hasHandlers():
    log.addHandler(handler)
    log.propagate = False
    return log

def get_openrails_log():
    log = logging.getLogger(OPENRAILS_LOGGER)
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(OpenRailsLogFormatter())
    # # avoid adding multiple handlers:
    # if not log.hasHandlers():
    log.addHandler(handler)
    log.propagate = False
    return log
