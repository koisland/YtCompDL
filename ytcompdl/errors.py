import logging


logging.basicConfig(filename='../yt_data.log', filemode='w', level=logging.DEBUG,
                    format="%(asctime)s - %(levelname)s - %(message)s")


class YTAPIError(Exception):
    def __init__(self, message):
        logging.error(message)
        super().__init__(message)


class PostProcessError(Exception):
    def __init__(self, message):
        logging.error(message)
        super().__init__(message)


class PyTubeError(Exception):
    def __init__(self, message):
        logging.error(message)
        super().__init__(message)

