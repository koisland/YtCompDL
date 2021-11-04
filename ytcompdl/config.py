import os
import pathlib
import re
import datetime


class Config:
    LOG_PATH = pathlib.Path(__file__).parents[1].joinpath("logs", "yt_data.log")

    # YT Data API parts of video to get. Fed to get_video_info
    YT_VIDEO_PARTS = ('snippet', 'contentDetails')
    MAX_COMMENTS = 1000
    BASE_TIME = datetime.datetime.strptime("1900-01-01 00:00:00", "%Y-%m-%d %H:%M:%S")

    # Regexp to parse strings (id, timestamps, etc.)
    # Works only if text is split line-by-line.
    YT_ID_REGEX = re.compile(r"(?<=v=)(.*?)(?=(?:&|$))")
    TIME_PATTERN = r"\d{1,2}:?\d*:\d{2}"
    IGNORE_CHRS = r"—|-|\s|\[|\]"  # Spacer characters between time or titles to ignore.
    YT_START_TIMESTAMPS_REGEX = \
        re.compile(f"(.*?)(?:{IGNORE_CHRS})*({TIME_PATTERN})(?:{IGNORE_CHRS})*(.*)")  # Can be name - time - name
    YT_DUR_TIMESTAMPS_REGEX = \
        re.compile(f"(.*?)(?:{IGNORE_CHRS})*({TIME_PATTERN})(?:{IGNORE_CHRS})*({TIME_PATTERN})(?:{IGNORE_CHRS})*(.*)")
    ISO_DUR_REGEX = re.compile("(\d{1,2}H)?(\d{1,2}M)?(\d{1,2}S)")

    # Download configs
    ACCEPTED_TAGS = ("album", "composer", "genre", "artist", "album_artist", "date")
    OUTPUT_FILE_EXT = {"audio": "mp3", "video": "mp4"}

    # TODO: AWS S3 folder here???
    OUTPUT_PATH = pathlib.Path(__file__).parents[1].joinpath("output")
    DEF_DL_FILE_EXT = "mp4"
    DEF_RESOLUTIONS = ("2160p", "1440p", "1080p", "720p", "480p", "360p", "240p", "144p")
