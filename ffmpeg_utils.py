import os
import shlex
import subprocess
import logging
from datetime import timedelta
from collections.abc import Collection

from ytcompdl.utils import timer
from ytcompdl.errors import PostProcessError

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
    if not os.path.exists(source) or os.path.exists(output):
        raise PostProcessError("Invalid file source or output.")
    if not isinstance(duration, Collection) and all(isinstance(time, timedelta) for time in duration):
        raise PostProcessError("Invalid duration times.")

    source = shlex.quote(source)
    output = shlex.quote(output)

    # ss arg for position, c for codec/copy
    # -map_metadata 0 copy metadata from source to output
    cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'error',
           '-i', *shlex.split(source),
           '-map_metadata', '0',
           '-ss', f'{duration[0]}', '-to', f'{duration[1]}',
           '-c', 'copy',
           *shlex.split(output)]
    try:
        logging.debug(f"Running slice command: {' '.join(cmd)}")
    except UnicodeError:
        # if contains characters that can't be encoded.
        pass

    subprocess.call(cmd, shell=False)


@timer
def apply_afade(source, output, in_out="both", duration=None, seconds=1):
    """
    Apply audio fade to one or both ends of source audio for some number of seconds.
    :param source:
    :param output:
    :param in_out:
    :param duration:
    :param seconds:
    :return:
    """
    src_file = source
    source = shlex.quote(source)
    output = shlex.quote(output)

    if duration is None:
        raise PostProcessError("No track duration given.")
    else:
        track_time = duration[1] - duration[0]
        if seconds > track_time.seconds:
            raise PostProcessError(f"Invalid fade time. Longer than track length. ({seconds} > {track_time.seconds})")
    if not (isinstance(seconds, int) or isinstance(seconds, float)):
        raise PostProcessError(f"Invalid fade time. Not a number. ({seconds}:{type(seconds)})")
    if in_out.lower() not in ("in", "out", "both"):
        raise PostProcessError(f"Invalid fade option. ({in_out})")

    # https://video.stackexchange.com/questions/19867/how-to-fade-in-out-a-video-audio-clip-with-unknown-duration
    # afade adds fade for d seconds at start of source
    # areverse reverses audio source
    # This way, we don't have to know how long the track is and specify specific times using ffmpeg's fade func.

    # afade_cmds = {
    #     "in": [f'afade=d={seconds}'],
    #     "out": [f'areverse, afade=d={seconds}, areverse'],
    #     "both": [f'afade=d={seconds}, areverse, afade=d={seconds}, areverse']
    # }

    # https://stackoverflow.com/questions/43818892/fade-out-video-audio-with-ffmpeg
    vfade_cmds = {
        "in": [],
        "out": [],
        "both": []
    }
    afade_cmds = {
        "in": [f'afade=in:st=0:d={seconds}'],
        "out": [f'afade=out:st=0:d={seconds}'],
        "both": [f'afade=in:st=0:d={seconds}, afade=out:st={track_time.seconds - seconds}:d={seconds}']
    }

    # TODO: Recheck afade in.
    cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'error',
           '-i', *shlex.split(source),
           '-map_metadata', '0',
           '-filter_complex', *afade_cmds[in_out.lower()],
           *shlex.split(output)]

    subprocess.call(cmd, shell=False)

    try:
        os.remove(src_file)
        logging.debug(f"Removed {src_file}")
        logging.debug(f"Completed fade command: {' '.join(cmd)}")
    except OSError as e:
        logging.error(e)
    except UnicodeError:
        logging.debug(f"Sliced source from {duration[0]}-{duration[1]}")


@timer
def apply_metadata(source, output, title, track, album_tags):
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

    cmd = [f'ffmpeg', '-hide_banner', '-loglevel', 'error',
           '-i', *shlex.split(source),
           '-map_metadata', '0',
           '-c', 'copy',
           # if title is blank give just generic title
           f'-metadata', f'title={title}', f'-metadata', f'track={str(track)}',
           *metadata_args, *shlex.split(output)]

    subprocess.call(cmd, shell=False)

    # remove source file
    try:

        os.remove(src_file)
        logging.debug(f"Removed {src_file}")
        logging.debug(f"Completed metadata command: {' '.join(cmd)}")
    except OSError as e:
        logging.error(e)
    except UnicodeError:
        logging.debug(f"Applied following metadata: {metadata_args[0::2]}")


@timer
def convert_audio(src, output_fname):
    src_file = src

    src = shlex.quote(src)
    output_fname = shlex.quote(output_fname)

    cmd = ['ffmpeg', '-hide_banner',
           '-i', *shlex.split(src), '-vn',
           *shlex.split(output_fname)]

    subprocess.call(cmd, shell=False)

    try:
        os.remove(src_file)
        logging.debug(f"Removed {src_file}")
        logging.debug(f"Completed audio conversion command: {' '.join(cmd)}")
    except OSError as e:
        logging.error(e)
    except UnicodeError:
        logging.debug(f"Converted {src} to {output_fname}.")


@timer
def merge_codecs(audio, video, output_fname):
    audio_src = audio
    video_src = video

    audio = shlex.quote(audio)
    video = shlex.quote(video)
    output_fname = shlex.quote(output_fname)

    cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'error',
           '-i', *shlex.split(audio),
           '-i', *shlex.split(video),
           '-c:a', 'aac',
           '-c:v', 'copy',
           *shlex.split(output_fname)]

    subprocess.call(cmd, shell=False)

    try:
        os.remove(audio_src)
        os.remove(video_src)
        logging.debug(f"Removed {audio_src}")
        logging.debug(f"Removed {video_src}")
        logging.debug(f"Completed codec merge command: {' '.join(cmd)}")
    except OSError as e:
        logging.error(e)
    except UnicodeError:
        logging.debug(f"Merged {audio_src} and {video_src}.")


if __name__ == "__main__":
    base_dir = os.path.join(os.getcwd(), "output")
    source_file = os.path.join(base_dir, "The_Lord_of_the_Rings_-_Symphony_Soundtrack_HQ_-_Complete_Album_HQ.mp3")
    output_file = os.path.join(base_dir, "opening.mp3")
    slice_audio(source_file, output_file, [0, 275])
