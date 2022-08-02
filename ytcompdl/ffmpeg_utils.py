import os
import shlex
import subprocess
import logging
import tqdm
from datetime import timedelta
from collections.abc import Collection
from ffmpeg import probe
from typing import List
from ytcompdl.errors import PostProcessError

logger = logging.getLogger(__name__)


# from better_ffmpeg_progress https://github.com/CrypticSignal/better-ffmpeg-progress
def run_ffmpeg_w_progress(ffmpeg_cmd: List[str], desc: str):
    index_of_filepath = ffmpeg_cmd.index("-i") + 1
    filepath = ffmpeg_cmd[index_of_filepath]

    file_duration = float(probe(filepath)["format"]["duration"])
    file_duration = int(file_duration)

    process = subprocess.Popen(
        ffmpeg_cmd + ["-progress", "-", "-nostats"],
        stdout=subprocess.PIPE,
    )

    s_elapsed = 0
    print(f"\n{desc}")
    with tqdm.tqdm(
        total=file_duration,
        bar_format=" ↳ |{bar:114}| {percentage:3.0f}%",
        leave=True,
        position=0,
    ) as pb:
        while process.poll() is None:
            output = process.stdout.readline().decode("utf-8").strip()
            if "out_time_ms" in output:
                microseconds = int(output[12:])
                secs = int(microseconds / 1_000_000)
                # subtract seconds added by previous s_elapsed to get number of seconds added to add to prog bar.
                pb.update(secs - s_elapsed)
                s_elapsed = secs


def check_file_paths(source, output):
    if not os.path.exists(source):
        raise PostProcessError("Invalid file source.")
    if os.path.exists(output):
        # remove incomplete intermediate file if output exists.
        os.remove(source)
        raise PostProcessError("Invalid file output path. Already exists.")


def slice_source(source: str, output: str, duration: Collection[timedelta]) -> str:
    """
    Slice source by single duration given.
    :param source: input source file
    :param output: output file
    :param duration: durations start and end timestamp
    :return: escaped output file path
    """
    check_file_paths(source, output)

    if not isinstance(duration, Collection) and all(
        isinstance(time, timedelta) for time in duration
    ):
        raise PostProcessError("Invalid duration times.")

    esc_source = shlex.quote(source)
    esc_output = shlex.quote(output)

    # ss arg for position, c for codec/copy
    # -map_metadata 0 copy metadata from source to output
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        *shlex.split(esc_source),
        "-map_metadata",
        "0",
        "-ss",
        f"{duration[0]}",
        "-to",
        f"{duration[1]}",
        "-c",
        "copy",
        *shlex.split(esc_output),
    ]
    try:
        logger.info(f"Running slice command: {' '.join(cmd)}".encode("utf-8"))
    except (UnicodeEncodeError, UnicodeError):
        # if contains characters that can't be encoded.
        logger.info(f"Sliced source from {duration[0]}-{duration[1]}")

    subprocess.call(cmd, shell=False)

    return shlex.split(esc_output)[0]


def apply_fade(source, output, output_type, fade_end="both", duration=None, seconds=1):
    """
    Apply audio fade to one or both ends of source audio for some number of seconds.
    :param source:
    :param output:
    :param output_type:
    :param fade_end:
    :param duration:
    :param seconds:
    :return:
    """

    check_file_paths(source, output)

    esc_source = shlex.quote(source)
    esc_output = shlex.quote(output)

    if duration is None:
        raise PostProcessError("No track duration given.")
    else:
        track_time = duration[1] - duration[0]
        if seconds > track_time.seconds:
            raise PostProcessError(
                f"Invalid fade time. Longer than track length. ({seconds} > {track_time.seconds})"
            )
    if not (isinstance(seconds, int) or isinstance(seconds, float)):
        raise PostProcessError(
            f"Invalid fade time. Not a number. ({seconds}: {type(seconds)})"
        )
    if fade_end.lower() not in ("in", "out", "both", "none"):
        raise PostProcessError(f"Invalid fade option. ({fade_end})")

    if fade_end.lower() == "none":
        # if no fade, return source file path.
        return shlex.split(source)[0]

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
                f"fade=in:st=0:d={seconds}, fade=out:st={track_time.seconds - seconds}:d={seconds}",
                "-filter_complex",
                f"afade=in:st=0:d={seconds}, afade=out:st={track_time.seconds - seconds}:d={seconds}",
            ],
        },
        "audio": {
            "in": ["-filter_complex", f"afade=in:st=0:d={seconds}"],
            "out": ["-filter_complex", f"afade=out:st=0:d={seconds}"],
            "both": [
                "-filter_complex",
                f"afade=in:st=0:d={seconds}, afade=out:st={track_time.seconds - seconds}:d={seconds}",
            ],
        },
    }

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        *shlex.split(esc_source),
        "-map_metadata",
        "0",
        "-max_muxing_queue_size",
        "1024",
        *fade_cmds[output_type.lower()][fade_end.lower()],
        *shlex.split(esc_output),
    ]

    subprocess.call(cmd, shell=False)

    try:
        os.remove(source)
        logger.info(f"Removed {source.encode('utf-8')}")
        logger.info(f"Completed fade command: {' '.join(cmd)}".encode("utf-8"))
    except OSError as e:
        logger.error(e)
    except (UnicodeEncodeError, UnicodeError):
        logger.info(f"Applied afade: {fade_end} for {seconds} seconds.")

    return shlex.split(esc_output)[0]


def apply_metadata(source, output, title, track, album_tags):
    check_file_paths(source, output)

    # source file to remove after metadata is applied.
    esc_source = shlex.quote(source)
    esc_output = shlex.quote(output)

    metadata_args = []

    # compile album tags
    for tag, tag_val in album_tags.items():
        tag_str = f'{tag}="{tag_val}"'
        metadata_args.append("-metadata")
        metadata_args.append(tag_str)

    # add track if mp3
    # if title is blank give just generic title
    metadata_args += [
        "-metadata",
        f'title="{title}"',
        "-metadata",
        f"track={str(track)}",
    ]
    # if ".mp3" in source:
    #     metadata_args += [f'-metadata', f'title={title}', f'-metadata', f'track={str(track)}']
    # else:
    #     metadata_args += [f'-metadata', f'title={title}']

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        *shlex.split(esc_source),
        "-map_metadata",
        "0",
        "-c",
        "copy",
        *metadata_args,
        # use arbitrary metadata tags
        "-movflags",
        "use_metadata_tags",
        *shlex.split(esc_output),
    ]

    subprocess.call(cmd, shell=False)

    # remove source file
    try:
        os.remove(source)
        logger.info(f"Removed {source.encode('utf-8')}")
        logger.info(f"Completed metadata command: {' '.join(cmd)}".encode("utf-8"))
    except OSError as e:
        logger.error(e)
    except (UnicodeEncodeError, UnicodeError):
        logger.info(f"Applied following metadata: {metadata_args[0::2]}")

    return shlex.split(esc_output)[0]


def convert_audio(src, output_fname):
    src_file = src

    src = shlex.quote(src)
    output_fname = shlex.quote(output_fname)

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        *shlex.split(src),
        "-vn",
        *shlex.split(output_fname),
    ]

    run_ffmpeg_w_progress(cmd, desc=f"Converting {src} to audio file.")

    try:
        os.remove(src_file)
        logger.info(f"Removed {src_file.encode('utf-8')}")
        logger.info(
            f"Completed audio conversion command: {' '.join(cmd)}".encode("utf-8")
        )
    except OSError as e:
        logger.error(e)
    except (UnicodeEncodeError, UnicodeError):
        logger.info(f"Converted {src} to {output_fname}.")

    return shlex.split(output_fname)[0]


def merge_codecs(audio, video, output_fname):
    audio_src = audio
    video_src = video

    audio = shlex.quote(audio)
    video = shlex.quote(video)
    output_fname = shlex.quote(output_fname)

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        *shlex.split(audio),
        "-i",
        *shlex.split(video),
        "-c:a",
        "aac",
        "-c:v",
        "copy",
        *shlex.split(output_fname),
    ]

    run_ffmpeg_w_progress(cmd, desc=f"Merging {audio_src} and {video_src}.")

    try:
        os.remove(audio_src)
        os.remove(video_src)
        logger.info(f"Removed {audio_src.encode('utf-8')}")
        logger.info(f"Removed {video_src.encode('utf-8')}")
        logger.info(f"Completed codec merge command: {' '.join(cmd)}".encode("utf-8"))
    except OSError as e:
        logger.error(e)
    except (UnicodeEncodeError, UnicodeError):
        logger.info(f"Merged {audio_src} and {video_src}.")

    return shlex.split(output_fname)[0]
