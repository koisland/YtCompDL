import logging
from ytcompdl.config import Config

# Prevent verbose logging for pytube, google api client, and asyncio.
pytube_logger = logging.getLogger('pytube')
pytube_logger.setLevel(logging.ERROR)

gapi_logger = logging.getLogger('googleapiclient.discovery_cache')
gapi_logger.setLevel(logging.ERROR)

asyncio_logger = logging.getLogger('asyncio')
asyncio_logger.setLevel(logging.ERROR)

# Create the logger and set level to info.
loggers = logging.getLogger(__name__)
loggers.setLevel(logging.INFO)

# Create the Handler for logging data to a file
logger_handler = logging.FileHandler(filename=Config.LOG_PATH, mode="w")
logger_handler.setLevel(logging.INFO)

# Create a Formatter for formatting the log messages
logger_formatter = logging.Formatter('%(name)s - %(levelname)s - %(message)s')

# Add the Formatter to the Handler
logger_handler.setFormatter(logger_formatter)

loggers.addHandler(logger_handler)
