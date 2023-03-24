import os
import shlex
import shutil
import subprocess
import logging
import functools
import tqdm
from ffmpeg import probe
from typing import List, Dict, Tuple, Union, Callable

from .errors import PostProcessError

logger = logging.getLogger(__name__)


# from better_ffmpeg_progress https://github.com/CrypticSignal/better-ffmpeg-progress
def run_ffmpeg_w_progress(ffmpeg_cmd: List[str], desc: str) -> None:
    """
    Run ffmpeg commands with progress bar.
    :param ffmpeg_cmd: ffmpeg cmd as list of str.
    :param desc: Description to print before progress bar.

    :return: None
    """
    index_of_filepath = ffmpeg_cmd.index("-i") + 1
    filepath = ffmpeg_cmd[index_of_filepath]

    # Find duration of file to set progress bar denom.
    file_duration = float(probe(filepath)["format"]["duration"])
    file_duration = int(file_duration)

    process = subprocess.Popen(
        ffmpeg_cmd + ["-progress", "-", "-nostats"],
        stdout=subprocess.PIPE,
    )

    # Match pytube max width of progressbar
    # https://github.com/pytube/pytube/blob/master/pytube/cli.py#L230
    prog_bar_len = shutil.get_terminal_size().columns
    max_width = int(prog_bar_len * 0.55)

    s_elapsed = 0
    print(f"\n{desc}")
    with tqdm.tqdm(
        total=file_duration,
        bar_format=f" ↳ |{{bar:{max_width}}}| {{percentage:3.0f}}.0%",
        leave=True,
        position=0,
    ) as pb:
        # Check if process is still running.
        while process.poll() is None:
            if process.stdout:
                output = process.stdout.readline().decode("utf-8").strip()
                if "out_time_ms" in output:
                    microseconds = int(output[12:])
                    secs = int(microseconds / 1_000_000)
                    # subtract seconds added by previous s_elapsed to get number of seconds added to add to prog bar.
                    pb.update(secs - s_elapsed)
                    s_elapsed = secs


def check_ffmpeg(func: Callable) -> Callable:
    """
    Wrapper function to check if ffmpeg exists as an excutable on os.
    :param func: function to wrap

    :return: Wrapped function.
    """

    @functools.wraps(func)
    def inner_func(*args, **kwargs):
        if shutil.which("ffmpeg") is None:
            raise PostProcessError("ffmpeg not an available executable.")
        ret = func(*args, **kwargs)
        return ret

    return inner_func


@check_ffmpeg
def slice_source(input_fname: str, output_fname: str, duration: Tuple[int, int]) -> str:
    """
    Slice source by single duration given.
    :param input_fname: input source file
    :param output_fname: output file
    :param duration: durations start and end timestamp
    :return: escaped output file path
    """
    if not isinstance(duration, tuple) and all(
        isinstance(time, int) for time in duration
    ):
        raise PostProcessError("Invalid duration times.")

    input_fname_qt = shlex.quote(input_fname)
    output_fname_qt = shlex.quote(output_fname)

    # ss arg for position, c for codec/copy
    # -map_metadata 0 copy metadata from source to output
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        *shlex.split(input_fname_qt),
        "-map_metadata",
        "0",
        "-ss",
        f"{duration[0]}",
        "-to",
        f"{duration[1]}",
        "-c",
        "copy",
        *shlex.split(output_fname_qt),
    ]
    try:
        logger.info(f"Running slice command: {' '.join(cmd)}")
    except (UnicodeEncodeError, UnicodeError):
        # if contains characters that can't be encoded.
        logger.info(f"Sliced source from {duration[0]}-{duration[1]}")

    subprocess.run(cmd, shell=False)

    return shlex.split(output_fname_qt)[0]


@check_ffmpeg
def apply_fade(
    input_fname: str,
    output_fname: str,
    fade_end: str = "both",
    duration: Tuple[int, int] = (0, 0),
    seconds: Union[int, float] = 1,
    remove_original: bool = True,
) -> str:
    """
    Apply audio fade to one or both ends of source audio for some number of seconds.
    :param input_fname: input file path
    :param output_fname: output file path
    :param fade_end: fade start, end, both start and end, or none.
    :param duration: duration start and end
    :param seconds: seconds to fade. float or int
    :param remove_original: remove original input_fname

    :return:
    """
    input_fname_qt = shlex.quote(input_fname)
    output_fname_qt = shlex.quote(output_fname)

    if duration == (0, 0):
        raise PostProcessError("No track duration given.")
    elif any(
        [
            isinstance(duration, tuple) is False,
            all(isinstance(dur, int) for dur in duration) is False,
            len(duration) != 2,
        ]
    ):
        raise PostProcessError(
            f"Invalid duration ({duration}) provided for {input_fname}."
        )
    else:
        track_time = duration[1] - duration[0]
        if seconds > track_time:
            raise PostProcessError(
                f"Invalid fade time. Longer than track length. ({seconds} > {track_time})"
            )
    if not (isinstance(seconds, int) or isinstance(seconds, float)):
        raise PostProcessError(
            f"Invalid fade time. Not a number. ({seconds}: {type(seconds)})"
        )
    if fade_end.lower() not in ("in", "out", "both", "none"):
        raise PostProcessError(f"Invalid fade option. ({fade_end})")

    if fade_end.lower() == "none":
        # if no fade, return source file path.
        return shlex.split(input_fname_qt)[0]

    # https://stackoverflow.com/questions/43818892/fade-out-video-audio-with-ffmpeg
    fade_cmds = {
        "video": {
            "in": [
                "-filter_complex",
                f"fade=in:st=0:d={seconds}",
                "-filter_complex",
                f"afade=in:st=0:d={seconds}",
            ],
            "out": [
                "-filter_complex",
                f"fade=t=out:st=0:d={seconds}",
                "-filter_complex",
                f"afade=t=out:st=0:d={seconds}",
            ],
            "both": [
                "-filter_complex",
                f"fade=in:st=0:d={seconds}, fade=out:st={track_time - seconds}:d={seconds}",
                "-filter_complex",
                f"afade=in:st=0:d={seconds}, afade=out:st={track_time - seconds}:d={seconds}",
            ],
        },
        "audio": {
            "in": ["-filter_complex", f"afade=in:st=0:d={seconds}"],
            "out": ["-filter_complex", f"afade=out:st=0:d={seconds}"],
            "both": [
                "-filter_complex",
                f"afade=in:st=0:d={seconds}, afade=out:st={track_time - seconds}:d={seconds}",
            ],
        },
    }

    output_type = "audio" if output_fname.endswith(".mp3") else "video"
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        *shlex.split(input_fname_qt),
        "-map_metadata",
        "0",
        "-max_muxing_queue_size",
        "1024",
        *fade_cmds[output_type][fade_end.lower()],
        *shlex.split(output_fname_qt),
    ]

    subprocess.run(cmd, shell=False)

    try:
        if remove_original:
            os.remove(input_fname)
            logger.info(f"Removed {input_fname}")
        logger.info(f"Completed fade command: {' '.join(cmd)}")
    except OSError as e:
        logger.error(e)
    except (UnicodeEncodeError, UnicodeError):
        logger.info(f"Applied afade: {fade_end} for {seconds} seconds.")

    return shlex.split(output_fname_qt)[0]


@check_ffmpeg
def apply_metadata(
    input_fname: str,
    output_fname: str,
    title: str,
    track: int,
    album_tags: Dict[str, str],
    remove_original: bool = True,
) -> str:
    """
    Apply metadata to a video or audio file.
    :param input_fname: input file path
    :param output_fname: output file path
    :param title: title to add
    :param track: track to add
    :param album_tags: tags
    :param remove_original: remove original file

    :return: output file path
    """
    # source file to remove after metadata is applied.
    input_fname_qt = shlex.quote(input_fname)
    output_fname_qt = shlex.quote(output_fname)

    metadata_args = []

    # compile album tags
    for tag, tag_val in album_tags.items():
        tag_value_qt = shlex.split(shlex.quote(tag_val))[0]
        tag_str = f"{tag}={tag_value_qt}"
        metadata_args.append("-metadata")
        metadata_args.append(tag_str)

    # Add track if mp3
    # If title is blank give just generic title.
    # Title should already be escaped and safe at this point.
    metadata_args += [
        "-metadata",
        f"title={title}",
        "-metadata",
        f"track={str(track)}",
    ]

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        *shlex.split(input_fname_qt),
        "-c",
        "copy",
        *metadata_args,
        *shlex.split(output_fname_qt),
    ]

    subprocess.run(cmd, shell=False)

    try:
        if remove_original:
            os.remove(input_fname)
            logger.info(f"Removed {input_fname}")
        logger.info(f"Completed metadata command: {' '.join(cmd)}")
    except OSError as e:
        logger.error(f"Unable to remove file due to: {e}")
    except (UnicodeEncodeError, UnicodeError):
        logger.info(f"Applied following metadata: {metadata_args[0::2]}")

    return shlex.split(output_fname_qt)[0]


@check_ffmpeg
def convert_audio(
    input_video_fname: str, output_audio_fname: str, remove_original: bool = True
) -> str:
    """
    Convert video/multiple stream file to only audio file showing progressbar.
    :params input_video_fname: input video file
    :params output_audio_fname: output file with merged codecs.
    :param remove_original: remove original file.

    :return: path to param output_fname
    """
    input_video_fname_qt = shlex.quote(input_video_fname)
    output_video_fname_qt = shlex.quote(output_audio_fname)

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        *shlex.split(input_video_fname_qt),
        "-vn",
        *shlex.split(output_video_fname_qt),
    ]

    run_ffmpeg_w_progress(
        cmd,
        desc=f"Converting {input_video_fname_qt} to audio file, {output_video_fname_qt}.",
    )

    try:
        if remove_original:
            os.remove(input_video_fname)
            logger.info(f"Removed {input_video_fname}")
        logger.info(f"Completed audio conversion command: {' '.join(cmd)}")
    except OSError as e:
        logger.error(f"Unable to remove file due to: {e}")
    except (UnicodeEncodeError, UnicodeError):
        logger.info(f"Converted {input_video_fname} to {output_audio_fname}.")

    return shlex.split(output_video_fname_qt)[0]


@check_ffmpeg
def merge_codecs(
    input_audio_fname: str,
    input_video_fname: str,
    output_video_fname: str,
    remove_original: bool = True,
) -> str:
    """
    Merge audio and video codecs.
    :params input_audio_fname: audio_file
    :params input_video_fname: video file
    :params output_video_fname: output file with merged codecs.

    :return: path to param output_fname
    """
    input_audio_fname_qt = shlex.quote(input_audio_fname)
    input_video_fname_qt = shlex.quote(input_video_fname)
    output_video_fname_qt = shlex.quote(output_video_fname)

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        *shlex.split(input_audio_fname_qt),
        "-i",
        *shlex.split(input_video_fname_qt),
        "-c:a",
        "aac",
        "-c:v",
        "copy",
        *shlex.split(output_video_fname_qt),
    ]

    run_ffmpeg_w_progress(
        cmd, desc=f"Merging {input_audio_fname_qt} and {input_video_fname_qt}."
    )

    try:
        if remove_original:
            os.remove(input_audio_fname)
            os.remove(input_video_fname)
            logger.info(f"Removed {input_audio_fname}")
            logger.info(f"Removed {input_video_fname}")
        logger.info(f"Completed codec merge command: {' '.join(cmd)}")
    except OSError as e:
        logger.error(f"Unable to remove file due to: {e}")
    except (UnicodeEncodeError, UnicodeError):
        logger.info(f"Merged {input_audio_fname} and {input_video_fname}.")

    return shlex.split(output_video_fname_qt)[0]
