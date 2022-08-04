import os
import re
import sys
import yaml
import pathlib
import datetime
import pprint
import logging
import json
import dotenv
import traceback
import multiprocessing as mp

from typing import List, Iterator
from functools import reduce
from googleapiclient.discovery import build
from pytube.helpers import safe_filename

from ytcompdl.pytube_dl import Pytube_Dl
from ytcompdl.ffmpeg_utils import slice_source, apply_fade, apply_metadata
from ytcompdl.errors import YTAPIError, PostProcessError, PyTubeError

logger = logging.getLogger(__name__)
dotenv.load_dotenv()


class YTCompDL(Pytube_Dl):
    # YT Data API parts of video to get. Fed to get_video_info
    YT_VIDEO_PARTS = ("snippet", "contentDetails")
    # Subtract by one base time to be consistent with timedeltas.
    BASE_TIME = datetime.datetime.strptime("1900-01-01 00:00:00", "%Y-%m-%d %H:%M:%S")
    YT_ISO_DUR_REGEX = re.compile(r"(\d{1,2}H)?(\d{1,2}M)?(\d{1,2}S)")
    # Regexp to parse strings (id, timestamps, etc.)
    # Works only if text is split line-by-line.
    YT_ID_REGEX = re.compile(r"(?<=v=)(.*?)(?=(?:&|$))")

    # Max comments to query from.
    MAX_COMMENTS = 1000
    # Minimum number of timestamps a comment has to have to be considered.
    MIN_NUM_TIMESTAMPS = 5
    # Percent similarity (0-1) to original duration of video. NOTE: Last timestamp cannot be considered in
    # calculation! This means that comments with longer tracks at end will have reduced overall similarity
    LENGTH_THRESHOLD = 0.5

    # Download configs
    ALLOWED_TAGS = ("album", "composer", "genre", "artist", "album_artist", "date")
    OUTPUT_FILE_EXT = {"audio": "mp3", "video": "mp4"}

    # remove original source file
    RM_SOURCE = True

    def __init__(
        self,
        video_url: str,
        output_type: str,
        regex_config: str,
        output_dir: pathlib.Path,
        n_processes: int = 4,
        res: str = "720p",
        opt_metadata: str = None,
        choose_comment: bool = False,
        save_timestamps: bool = True,
        slice_output: bool = True,
        fade_end: str = "both",
        fade_time: float = 0.5,
    ):
        """
        :param video_url: Youtube video url. (string)
        :param output_type: Desired output from video. (string - "audio", "video")
        :param res: Desired resolution (if video_ouput="video"). (string)
        :param opt_metadata: Optional album metadata (dict)
        :param choose_comment: (bool)
        :param save_timestamps: (bool)
        :param slice_output: Slice output by timestamps. (bool)
        :param fade_end: Fade an end of the output. (string)
        :param fade_time: Time to fade audio or video. (float)
        Titles and track numbers applied by default.
        """
        self.video_url = video_url
        self.output_type = output_type
        self.output_dir = output_dir

        # Check available cores
        if available_cores := os.cpu_count():
            self.n_processes = (
                available_cores if available_cores < n_processes else n_processes
            )
        else:
            raise Exception("No cores available.")

        # Load regex patterns
        self.regex_config = regex_config
        self.load_config_regex()

        self.opt_metadata = opt_metadata
        self.choose_comment = choose_comment
        self.save_timestamps = save_timestamps
        self.slice_output = slice_output
        self.fade_end = fade_end
        self.fade_time = fade_time

        if not os.environ.get("YT_API_KEY"):
            raise YTAPIError(
                "No YouTube Data API key detected in environment variables."
            )
        try:
            # Setup build func to allow access to Youtube API.
            self.YT = build(
                serviceName="youtube",
                version="v3",
                developerKey=os.environ.get("YT_API_KEY"),
            )
        except Exception:
            traceback.print_exc(limit=2, file=sys.stdout)
            sys.exit(1)

        # Get video info.
        self.snippets, self.content_details = list(
            self.get_video_info(*self.YT_VIDEO_PARTS)
        )
        # comment instance vars
        self.comment = None
        self.timestamp_style = None
        # timestamps
        self.titles, self.times = self.format_timestamps()

        # download instance vars
        self.video_path = None

        # Place at the end to allow custom errors if invalid args.
        super().__init__(video_url, output_type, output_dir, res)

    def load_config_regex(self):
        """
        Load regex patterns from config file by setting instance vars.
        """
        with open(self.regex_config, "r") as yaml_file:
            try:
                regex_patterns = yaml.safe_load(yaml_file)
            except yaml.YAMLError:
                raise Exception(f"Invalid yaml file. {self.regex_config}")

        # Check that all patterns exist.
        expected_patterns = [
            "ignored_spacers",
            "time",
            "start_timestamp",
            "duration_timestamp",
        ]
        if any(pattern not in expected_patterns for pattern in regex_patterns.keys()):
            raise ValueError(
                f"Missing one or more expected patterns. {expected_patterns}"
            )

        # Check that types are correct.
        for regex_name, pattern in regex_patterns.items():
            if regex_name == "ignored_spacers" and isinstance(pattern, list):
                if any(isinstance(ign_char, str) is False for ign_char in pattern):
                    raise ValueError("Invalid character in ignored_spacers.")
            elif not isinstance(pattern, str):
                raise ValueError(
                    f"Regular expression pattern for {regex_name} is invalid. {pattern}"
                )

        self.YT_TIME_REGEX = regex_patterns["time"]
        try:
            self.YT_IGN_REGEX = "|".join(
                f"\\{char}" for char in regex_patterns["ignored_spacers"]
            )
        except TypeError:
            logging.debug(
                'No ignored characters provided for spacer. Using "" as default.'
            )
            self.YT_IGN_REGEX = ""

        self.YT_START_TIMESTAMPS_REGEX = re.compile(
            regex_patterns["start_timestamp"].format(
                ignored_spacers=self.YT_IGN_REGEX, time=self.YT_TIME_REGEX
            )
        )
        self.YT_DUR_TIMESTAMPS_REGEX = re.compile(
            regex_patterns["duration_timestamp"].format(
                ignored_spacers=self.YT_IGN_REGEX, time=self.YT_TIME_REGEX
            )
        )

    @property
    def title(self) -> str:
        """
        Safe filename for title of video
        :return: Safe title filename.
        """
        return safe_filename(self.snippets["title"])

    @property
    def desc(self) -> str:
        """
        Video description
        :return: Safe title filename.
        """
        return self.snippets["description"]

    @property
    def channel(self) -> str:
        """
        Channel name
        :return: channel name.
        """
        return self.snippets["channelTitle"]

    @property
    def year_uploaded(self) -> str:
        try:
            year_uploaded = self.snippets["publishedAt"].split("-")[0]
        except (ValueError, KeyError):
            logger.warning("Unable to parse year uploaded. Defaulting to current year.")
            year_uploaded = str(datetime.datetime.now().year)
        return year_uploaded

    @property
    def video_id(self):
        """
        Video id from url.
        :return: id_search (string)
        """
        if id_search := re.search(self.YT_ID_REGEX, self.video_url):
            return id_search.group(1)
        else:
            raise YTAPIError(
                f"Unable to parse video id from provided url. ({self.video_url})"
            )

    @property
    def duration(self):
        """
        Converts iso8601 duration string into duration as datetime timedelta .
        :return: duration (datetime timedelta)
        """
        if hms := re.search(self.YT_ISO_DUR_REGEX, self.content_details["duration"]):
            dt_strptime_fmt = "PT" + "".join(
                "%" + (match[-1] * 2) for match in hms.groups() if match
            )
            datetime_duration = datetime.datetime.strptime(
                self.content_details["duration"], dt_strptime_fmt
            )
            duration_total = datetime_duration - self.BASE_TIME
            return duration_total
        else:
            raise YTAPIError("Unable to parse ISO8601 duration string.")

    @property
    def metadata(self):
        """
        Metadata from video information to add to media.
        If opt_metadata included and validated, use instead.
        :return: metadata or data (dict)
        """
        if self.opt_metadata is None:
            metadata = {
                "album": self.snippets["title"],
                "author": self.channel,
                "year": self.year_uploaded,
            }
            logger.info(
                f"No optional album metadata provided. Applying defaults. {metadata.items()}"
            )
            return metadata
        else:
            if os.path.exists(self.opt_metadata) and ".json" in self.opt_metadata:
                with open(self.opt_metadata, "r") as jfile:
                    data = json.load(jfile)
            else:
                raise YTAPIError("Invalid path to json metadata file.")
            # check if tags in deserialized json are valid.
            if all(tag in self.ALLOWED_TAGS for tag, _ in data.items()):
                logger.info("Valid album metadata provided.")
                return data
            else:
                raise YTAPIError("Invalid album metadata provided.")

    def download(self):
        """
        Download YT video provided by url and process using timestamps.
        :return: Output path.
        """

        if self.output_type.lower() in self.OUTPUT_FILE_EXT.keys():
            self.video_path = os.path.join(
                self.output_dir, f"{self.title}.{self.OUTPUT_FILE_EXT[self.output]}"
            )
        else:
            raise PyTubeError(f"Invalid output category ({self.output_type}).")

        if not os.path.exists(self.video_path):
            logger.info(
                f"Downloading {self.output_type.lower()} for {self.snippets['title']}."
            )
            self.pytube_dl()
        else:
            logger.info("Pre-existing file found.")

        self._postprocess()

        # remove original source file.
        if self.RM_SOURCE and self.slice_output:
            os.remove(self.video_path)

        return self.output_dir

    @staticmethod
    def _postprocess_track(
        video_path: pathlib.Path,
        num: int,
        title: str,
        times: List[datetime.timedelta],
        output_dir: pathlib.Path,
        output_type: str,
        fade_end: str,
        fade_time: int,
        metadata: dict,
    ) -> str:
        """
        Process a single track.
        instance var needs to be picklable so instead pass vars
        """
        # If empty title or unknown, give generic name.
        # else clean and format.
        if title in ("", "?"):
            safe_title = f"track_{num}"
        else:
            safe_title = safe_filename(title)

        ext = "mp3" if output_type == "audio" else "mp4"

        # ffmpeg can't apply inplace so need intermediate files
        slice_path = output_dir.joinpath(f"{safe_title}.{ext}")
        fade_path = output_dir.joinpath(f"xx{safe_title}.{ext}")
        final_output = output_dir.joinpath(f"{safe_title}.{ext}")

        if final_output.exists():
            return str(final_output)

        # convert timedelta times to seconds (int).
        duration = [time.seconds for time in times]

        if not slice_path.exists():
            slice_path = slice_source(
                source=video_path, output=str(slice_path), duration=duration
            )

        if fade_end and not fade_path.exists():
            fade_path = apply_fade(
                source=str(slice_path),
                output=str(fade_path),
                output_type=output_type,
                fade_end=fade_end,
                duration=times,
                seconds=float(fade_time),
            )
        else:
            fade_path = slice_path

        # can't add metadata inplace
        final_output = apply_metadata(
            source=str(fade_path),
            output=str(final_output),
            title=title,
            track=num,
            album_tags=metadata,
        )

        return str(final_output)

    def _postprocess(self):
        if not self.slice_output:
            logger.info(f"Unsliced {self.title} saved to {self.output_dir}")
            return
        if not self.titles and not self.times:
            raise PostProcessError("No timestamps to use to slice.")

        # make subfolder for video segments
        title_folder = self.output_dir.joinpath(self.title)
        if not title_folder.exists():
            title_folder.mkdir(parents=True, exist_ok=True)

        logger.info(f"Processing file: {self.video_path}")
        logger.info(f"Running post-processing in {self.n_processes} processes.")
        logger.info(f"Slicing: {self.slice_output}")
        logger.info(f"Applying fade ({self.fade_time}): {self.fade_end}")

        with mp.Pool(processes=self.n_processes) as pool:
            args = [
                (
                    self.video_path,
                    num,
                    title,
                    times,
                    title_folder,
                    self.output,
                    self.fade_end,
                    self.fade_time,
                    self.metadata,
                )
                for num, (title, times) in enumerate(zip(self.titles, self.times), 1)
            ]
            res = pool.starmap(self._postprocess_track, args)
            logger.info(f"Completed processing. {len(res)} files produced.")
            return res

    def format_timestamps(self):
        """
        Format timestamps by splitting into times and titles
        Convert times into durations that can be fed into ffmpeg. Also add ending times.
        :return: titles, times (list)
        """
        titles = []
        times = []

        for timestamp in self.timestamps:
            times.append(self.convert_str_time(timestamp[1:-1], rtn_fmt="timedelta"))
            try:
                # If empty group is at start. Timestamp title at end.
                if timestamp.index("") == 0:
                    titles.append(timestamp[-1])
                # if empty group of regex at end. Timestamp title at start.
                elif timestamp.index("") == len(timestamp) - 1:
                    titles.append(timestamp[0])
            except ValueError:
                # if text on both sides of timestamps, take the group on the right by default.
                titles.append(timestamp[-1])

        # Condense nested lists to single list and convert to duration.
        if self.timestamp_style == "Start":
            times = reduce(lambda x, y: x + y, times)
            dur_times = []
            for i in range(len(times) - 1):
                if i == 0:
                    add_time = datetime.timedelta(seconds=0)
                else:
                    add_time = datetime.timedelta(seconds=1)
                dur_times.append([times[i] + add_time, times[i + 1]])
            # Add final timestamp
            dur_times.append([times[-1] + datetime.timedelta(seconds=1), self.duration])
            times = dur_times
        else:
            # Take last duration timestamp's ending time and add 1 second.
            times.append([times[-1][1] + datetime.timedelta(seconds=1), self.duration])
        return titles, times

    @staticmethod
    def clean_timestamps(timestamps):
        """
        Remove characters used to separate timestamp and title.
        :param timestamps:  timestamp/title strings (list of lists)
        :return: modified timestamp/title strings (list of lists)
        """
        # pprint.pprint(timestamps)
        return [
            [re.sub(r"\[|\]|—|-|~", "", item.strip()).strip() for item in timestamp]
            for timestamp in timestamps
        ]

    def convert_str_time(self, str_times, rtn_fmt="datetime"):
        """
        Convert string time to datetime
        :param str_times: time-like strings (iterable)
        :param rtn_fmt: return datetime or timedelta? (string)
        :return: datetime objects (list)
        """
        # Check if str_times iterable has any invalid dtypes (not a str).
        if any(not isinstance(str_time, str) for str_time in str_times):
            raise YTAPIError(
                f"Unable to convert invalid string timestamp.\n" f"{str_times}"
            )
        time_length = 8
        # First pad time to standardize.
        converted_times = []
        for str_time in str_times:
            while len(str_time) < time_length:
                # if str_time close to next time unit (hour, minute, etc.)
                if (len(str_time) + 1) % 3 == 0:
                    # Append colon.
                    str_time = ":" + str_time
                else:
                    # Pad with 0's.
                    str_time = "0" + str_time
            if rtn_fmt == "datetime":
                converted_times.append(datetime.datetime.strptime(str_time, "%H:%M:%S"))
            elif rtn_fmt == "timedelta":
                converted_times.append(
                    (datetime.datetime.strptime(str_time, "%H:%M:%S") - self.BASE_TIME)
                )
        return converted_times

    def validate_timestamps(
        self, timestamps, min_num_timestamps=5, percent_threshold=0.5
    ):
        # If total number of timestamps below minimum, reject timestamps
        # If total length not within 50% of actual video length, reject timestamps.

        if len(timestamps) < min_num_timestamps:
            return

        # Currently prefixed sum. Convert to individual lengths first.
        # Iterate through each timestamp ignoring last item, the track title.
        dt_timestamps = [
            self.convert_str_time(timestamp[1:-1]) for timestamp in timestamps
        ]
        if self.timestamp_style == "Start":
            # convert_str_time returns a list of datetimes. only one datetime with start timestamp style so take
            # first item.
            dt_timestamps = [dt[0] for dt in dt_timestamps]
            # subtract next timestamp by current current timestamp
            dt_lengths = [
                dt_timestamps[ind + 1] - dt_timestamps[ind]
                for ind in range(len(dt_timestamps) - 1)
            ]
        else:
            # end of timestamp - start of timestamp
            dt_lengths = [dur[1] - dur[0] for dur in dt_timestamps]

        total_length = reduce(lambda x, y: x + y, dt_lengths)

        # If estimated length is under percent threshold, reject timestamp.
        # Main issue is that with start timestamps, last item will not be counted and less accurate in general.
        # If it covers a long segment of the video, could throw off calculation.
        # For duration timestamps, regex pattern won't count anything other than a time-like pattern.
        # So no "END" or "FIN". Not worth risk of matching track title.

        # As a result, default percent threshold high but not insanely high. Adjust accordingly.
        percent_identity = total_length / self.duration
        if percent_threshold <= percent_identity:
            return f"Percent similarity: {round(percent_identity * float(100), 2)}%"

    def get_video_info(self, *parts: str) -> Iterator[dict]:
        """
        Extract video information parts from YouTube video ID.
        """
        if self.video_id:
            # query desired parts from video with matching video id.
            info_request = self.YT.videos().list(
                part=f"{','.join(parts)}", id=self.video_id
            )
            info_response = info_request.execute()
            if len(info_response["items"]) == 0:
                raise YTAPIError("No video information available.")
            for part in parts:
                requested_part = info_response["items"][0][part]
                yield requested_part

    def set_timestamp_style(self, timestamps):
        # if length of all timestamps is 3, timestamp is based on start of chapter.
        # if length of all timestamps is 4, timestamp is based on duration of chapter.
        if all(len(timestamp) == 3 for timestamp in timestamps):
            self.timestamp_style = "Start"
        elif all(len(timestamp) == 4 for timestamp in timestamps):
            self.timestamp_style = "Duration"
        else:
            raise YTAPIError("Invalid format in retrieved timestamps.")

    def find_timestamps(self, timestamp_string):
        # Replace '"' with '' to help extract titles
        # Split comment into lines to avoid bad regex matches at end.
        timestamp_string = timestamp_string.replace('"', "").split("\n")

        for line in timestamp_string:
            if timestamps := re.findall(self.YT_TIME_REGEX, line):
                if len(timestamps) == 1:
                    yield re.findall(self.YT_START_TIMESTAMPS_REGEX, line)
                elif len(timestamps) == 2:
                    yield re.findall(self.YT_DUR_TIMESTAMPS_REGEX, line)

    @property
    def timestamps(self):
        """
        Found timestamps will always be in this form: (str_title_front, *timestamp, str_title_back)
        * timestamp can be one - two strings
        :return:
        """
        valid_timestamps = []
        parsed_timestamps = []

        if desc_timestamps := list(self.find_timestamps(self.desc)):
            logger.info("Timestamps found in description.")
            chosen_comment = self.desc.split("\n")
            # remove extra list from list comprehension
            desc_timestamps = reduce(lambda x, y: x + y, desc_timestamps)
            # Set timestamp style.
            self.set_timestamp_style(desc_timestamps)
            chosen_timestamps = self.clean_timestamps(desc_timestamps)
        else:
            # If cannot find timestamps in description, check comments
            logger.info(
                "Timestamps not found in description. Checking comment section."
            )

            for comment in self.extract_comments(max_comments=self.MAX_COMMENTS):
                if comm_timestamps := list(self.find_timestamps(comment)):
                    comm_timestamps = reduce(lambda x, y: x + y, comm_timestamps)
                    # Set timestamp style.

                    self.set_timestamp_style(comm_timestamps)
                    if time_perc_identity := self.validate_timestamps(
                        comm_timestamps,
                        min_num_timestamps=self.MIN_NUM_TIMESTAMPS,
                        percent_threshold=self.LENGTH_THRESHOLD,
                    ):
                        valid_timestamps.append(
                            [time_perc_identity, *comment.split("\n")]
                        )
                        parsed_timestamps.append(comm_timestamps)
                        logger.info(
                            f"Valid comment timestamps found ({time_perc_identity})."
                        )

            # If choose_comment=True, allow to choose which timestamps to select when multiple are valid.
            # Else, return comment timestamps with highest percentage identity.
            if len(valid_timestamps) == 0:
                raise YTAPIError("No valid timestamps found in comments.")
            if self.choose_comment:
                comment_num = self.select_comment(valid_timestamps)
                chosen_comment = valid_timestamps[int(comment_num) - 1]
                chosen_timestamps = parsed_timestamps[int(comment_num) - 1]
            else:
                sorted_comments = list(
                    sorted(valid_timestamps, key=lambda x: x[0], reverse=True)
                )
                chosen_comment = sorted_comments[0]
                # Need original index before sort to get parsed timestamps.
                original_index = valid_timestamps.index(chosen_comment)
                chosen_timestamps = parsed_timestamps[original_index]

            self.set_timestamp_style(chosen_timestamps)

        # Save timestamps to file named f"{title}_timestamps.txt"
        if self.save_timestamps:
            self.save_comment(chosen_comment)

        return self.clean_timestamps(chosen_timestamps)

    @staticmethod
    def select_comment(valid_timestamps):
        for num, v_comment in enumerate(valid_timestamps):
            print(f"[{num + 1}]")
            pprint.pprint(v_comment)

        question = input(f"Select comment. (1-{len(valid_timestamps)})\n")
        while int(question) not in range(1, len(valid_timestamps) + 1):
            print(f"Invalid comment ({question}). Please try again.\n")
            question = input(f"Select comment. (1-{len(valid_timestamps)})\n")

        logger.info(f"Comment {int(question)} chosen for timestamps.")
        return question

    def save_comment(self, chosen_comment):
        timestamp_fname = os.path.join(self.output_dir, f"{self.title}_timestamps.txt")
        with open(timestamp_fname, "w", encoding="utf-8") as fobj:
            fobj.write("\n".join(chosen_comment))
        logger.info(
            f"Timestamps saved to {os.path.join(os.getcwd(), timestamp_fname)}."
        )

    def extract_comments(self, max_comments: int) -> Iterator[str]:
        """
        Extract comments with YT Api given a maximum number of comments to check.
        :param max_comments: maximum number of comments to check. Must be multiple of 100.
        :
        """
        # Comment counter
        comments_checked = 0
        # Must be a multiple of 100.
        if max_comments % 100 != 0:
            raise YTAPIError(
                "Invalid number of comments to check. Must be a multiple of 100."
            )

        comment_request = self.YT.commentThreads().list(
            part="snippet, replies",
            videoId=self.video_id,
            maxResults=100,
            order="relevance",
        )
        # Increment for first request.
        comments_checked += 100
        while comment_request:
            comment_response = comment_request.execute()
            if comment_threads := comment_response.get("items"):
                for thread in comment_threads:
                    top_level_comment = thread["snippet"]["topLevelComment"]
                    yield top_level_comment["snippet"]["textOriginal"]
                # list next returns None if no items remaining.
                comment_request = self.YT.commentThreads().list_next(
                    comment_request, comment_response
                )
                comments_checked += 100
            else:
                logger.info("No comments found.")
            if comments_checked == max_comments:
                comment_request = None
