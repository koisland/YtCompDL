import timeit
import logging

logging.basicConfig(filename='yt_data.log', filemode='w', level=logging.DEBUG,
                    format="%(asctime)s - %(levelname)s - %(message)s")


def timer(func):
    def timed_func(*args, **kwargs):
        start_time = timeit.default_timer()
        result = func(*args, **kwargs)
        end_time = timeit.default_timer()
        elapsed_time = end_time - start_time
        logging.debug(f"Total time elapsed for {func.__name__} is {elapsed_time}.")
        return result

    return timed_func
