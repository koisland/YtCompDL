import os
import timeit
import mimetypes
import logging
from PIL import Image

logging.basicConfig(filename='yt_data.log', filemode='w', level=logging.DEBUG,
                    format="%(asctime)s - %(levelname)s - %(message)s")


def timer(func):
    def timed_func(*args, **kwargs):
        start_time = timeit.default_timer()
        result = func(*args, **kwargs)
        end_time = timeit.default_timer()
        elapsed_time = end_time - start_time
        logging.debug(f"Total time elapsed for {func.__name__} is {round(elapsed_time, 3)} seconds.")
        return result

    return timed_func

#
# def format_picture(source, img_ext):
#     print(source, img_ext)
#     directory, file = os.path.split(source)
#     fname, _ = os.path.splitext(file)
#     dest = os.path.join(directory, f"{fname}.{img_ext.strip('.')}")
#
#     # Check mimetype category.
#     src_mtype = mimetypes.guess_type(source)[0].split("/")[0]
#     dest_mtype = mimetypes.guess_type(dest)[0].split("/")[0]
#     print(src_mtype, dest_mtype)
#
#     if src_mtype == "image" and dest_mtype == "image":
#         im = Image.open(source)
#         converted_im = im.convert('RGB')
#         converted_im.save(dest)
#
#         # remove original file
#         os.remove(source)
#     else:
#         raise Exception("Invalid source or extension.")
