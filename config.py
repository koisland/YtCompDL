import os
import re
import datetime


class Config:
    # Regexp to parse strings (id, timestamps, etc.)
    YT_ID_REGEX = re.compile(r"(?<=v=)(.*?)(?=(?:&|$))")
    TIME_PATTERN = r"\d{1,2}:?\d*:\d{2}"
    IGNORE_CHRS = r"—|-|\s|\[|\]"  # Spacer characters between time or titles to ignore.
    # Works only if text is split line-by-line.
    YT_START_TIMESTAMPS_REGEX = \
        re.compile(f"(.*?)(?:{IGNORE_CHRS})*({TIME_PATTERN})(?:{IGNORE_CHRS})*(.*)")
    YT_DUR_TIMESTAMPS_REGEX = \
        re.compile(f"(.*?)(?:{IGNORE_CHRS})*({TIME_PATTERN})(?:{IGNORE_CHRS})*({TIME_PATTERN})(?:{IGNORE_CHRS})*(.*)")

    MAX_COMMENTS = 1000
    BASE_TIME = datetime.datetime.strptime("1900-01-01 00:00:00", "%Y-%m-%d %H:%M:%S")

    ACCEPTED_TAGS = ("album", "composer", "genre", "artist", "album_artist", "date")
    OUTPUT_FILE_EXT = {"audio": "mp3", "video": "mp4"}

    OUTPUT_PATH = os.path.join(os.getcwd(), 'output')
    DEF_DL_FILE_EXT = "mp4"
    DEF_RESOLUTIONS = ("2160p", "1440p", "1080p", "720p", "480p", "360p", "240p", "144p")
