# ffmpeg
# https://ffmpeg.org/ffmpeg.html#toc-Main-options

# Trimming
# https://unix.stackexchange.com/questions/182602/trim-audio-file-using-start-and-stop-times

# Add tags/metdata
# https://superuser.com/questions/1331752/ffmpeg-adding-metadata-to-an-mp3-from-mp3-input
# https://wiki.multimedia.cx/index.php/FFmpeg_Metadata
# https://stackoverflow.com/questions/18710992/how-to-add-album-art-with-ffmpeg


import os
import shlex
import subprocess
import logging
from datetime import timedelta
from collections.abc import Collection

from utils import timer

logging.basicConfig(filename='yt_data.log', filemode='w', level=logging.DEBUG,
                    format="%(asctime)s - %(levelname)s - %(message)s")


# shell=True is a bad idea.
@timer
def slice_audio(source, output, duration):
    """

    :param source:
    :param output:
    :param duration:
    :return:
    """
    # if not os.path.exists(source) or os.path.exists(output):
    #     raise Exception("Invalid file.")
    if not isinstance(duration, Collection) and all(isinstance(time, timedelta) for time in duration):
        raise Exception("Not an iterable")

    source = shlex.quote(source)
    output = shlex.quote(output)

    # ss arg for position, c for codec/copy
    cmd = ['ffmpeg', '-i', *shlex.split(source),
           '-ss', f'{duration[0]}', '-to', f'{duration[1]}',
           '-c', 'copy', *shlex.split(output)]

    logging.debug(f"Running slice command: {' '.join(cmd)}")
    subprocess.call(cmd, shell=False)


@timer
def apply_afade(source, output, in_out="both", seconds=1):
    """
    Apply audio fade to one or both ends of source audio for some number of seconds.
    :param source:
    :param output:
    :param in_out:
    :param seconds:
    :return:
    """
    src_file = source
    source = shlex.quote(source)
    output = shlex.quote(output)

    if not (isinstance(seconds, int) or isinstance(seconds, float)):
        raise Exception("Invalid fade time.")
    if in_out.lower() not in ("in", "out", "both"):
        raise Exception("Invalid fade option.")

    # https://video.stackexchange.com/questions/19867/how-to-fade-in-out-a-video-audio-clip-with-unknown-duration
    # afade adds fade for d seconds at start of source
    # areverse reverses audio source
    # This way, we don't have to know how long the track is and specify specific times using ffmpeg's fade func.
    afade_cmds = {
        "in": ['-filter_complex', f'afade=d={seconds}'],
        "out": ['-filter_complex', f'areverse, afade=d={seconds}, areverse'],
        "both": ['-filter_complex', f'afade=d={seconds}, areverse, afade=d={seconds}, areverse']
    }

    cmd = ['ffmpeg', '-i', *shlex.split(source), *afade_cmds[in_out.lower()], *shlex.split(output)]
    logging.debug(f"Running fade command: {' '.join(cmd)}")
    subprocess.call(cmd, shell=False)

    try:
        os.remove(src_file)
    except OSError as e:
        logging.error(e)


@timer
def apply_metadata(source, output, title, track, album_tags, cover=None):
    # source file to remove after metadata is applied.
    src_file = source
    source = shlex.quote(source)
    output = shlex.quote(output)

    metadata_args = []

    # compile album tags
    for tag, tag_val in album_tags.items():
        tag_str = f'{tag}={tag_val}'
        metadata_args.append(f'-metadata')
        metadata_args.append(tag_str)

    cmd = [f'ffmpeg', '-i', *shlex.split(source), '-c', 'copy',
           f'-metadata', f'title={title}', f'-metadata', f'track={str(track)}',
           *metadata_args, *shlex.split(output)]

    logging.debug(f"Running metadata command: {' '.join(cmd)}")
    subprocess.call(cmd, shell=False)

    # remove source file
    try:
        os.remove(src_file)
    except OSError as e:
        logging.error(e)


if __name__ == "__main__":
    base_dir = os.path.join(os.getcwd(), "output")
    source_file = os.path.join(base_dir, "The_Lord_of_the_Rings_-_Symphony_Soundtrack_HQ_-_Complete_Album_HQ.mp3")
    output_file = os.path.join(base_dir, "opening.mp3")
    slice_audio(source_file, output_file, [0, 275])
