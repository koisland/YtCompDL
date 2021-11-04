import logging


logger = logging.getLogger(__name__)


class YTAPIError(Exception):
    def __init__(self, message):
        logger.error(message)
        super().__init__(message)


class PostProcessError(Exception):
    def __init__(self, message):
        logger.error(message)
        super().__init__(message)


class PyTubeError(Exception):
    def __init__(self, message):
        logger.error(message)
        super().__init__(message)

