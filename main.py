import os
import re
import datetime
import pprint
import logging
from functools import reduce

from tqdm import tqdm
from googleapiclient.discovery import build
from pytube.helpers import safe_filename

# local imports
from downloader import Pytube_Dl
from ffmpeg_utils import slice_audio, apply_afade, apply_metadata
from config import Config
from ytcompdl.utils import timer
from ytcompdl.errors import YTAPIError, PostProcessError, PyTubeError

logger = logging.getLogger('googleapiclient.discovery')
logger.setLevel(logging.ERROR)
logging.basicConfig(filename='yt_data.log', filemode='w', level=logging.DEBUG,
                    format="%(asctime)s - %(levelname)s - %(message)s")


class YTCompDL(Pytube_Dl, Config):
    # Setup build func to allow access to Youtube API.
    YT = build(serviceName="youtube", version="v3", developerKey=os.environ.get("YT_API_KEY"))

    def __init__(self, video_url, video_output,
                 res="720p", opt_metadata=None, choose_comment=False, save_timestamps=True):
        """
        :param video_url: Youtube video url. (string)
        :param video_output: Desired output from video. (string - "audio", "video")
        :param res: Desired resolution (if video_ouput="video"). (string - See config.py)
        :param opt_metadata: Optional album metadata (dict)
        Titles and track numbers applied by default.
        """
        super().__init__(video_url, video_output, res)
        self.video_url = video_url
        self.video_path = None
        self.video_output = video_output
        self.opt_metadata = opt_metadata

        self.snippets, self.content_details = list(self.get_video_info(*self.YT_VIDEO_PARTS))
        self.title = safe_filename(self.snippets['title'])
        self.desc = self.snippets['description']
        self.channel = self.snippets['channelTitle']
        self.upload_time = self.snippets['publishedAt']
        self.year_uploaded = self.upload_time.split('-')[0]

        self.choose_comment = choose_comment
        self.save_timestamps = save_timestamps
        self.comment = None
        self.timestamp_style = None
        self.titles, self.times = self.format_timestamps()

        self.process_prog_bar = None

    @property
    def video_id(self):
        """
        Video id from url.
        :return: id_search (string)
        """
        if id_search := re.search(self.YT_ID_REGEX, self.video_url):
            return id_search.group(1)
        else:
            raise YTAPIError(f"Unable to parse video id from provided url. ({self.video_url})")

    @property
    def duration(self):
        """
        Converts iso8601 duration string into duration as datetime timedelta .
        :return: duration (datetime timedelta)
        """
        if hms := re.search(self.ISO_DUR_REGEX, self.content_details['duration']):
            dt_strptime_fmt = "PT" + ''.join("%" + (match[-1] * 2) for match in hms.groups() if match)
            duration = datetime.datetime.strptime(self.content_details['duration'], dt_strptime_fmt) - self.BASE_TIME
            return duration
        else:
            raise YTAPIError("Unable to parse ISO8601 duration string.")

    @property
    def metadata(self):
        """
        Metadata from video information to add to media.
        If opt_metadata included and validated, use instead.
        :return: metadata or self.opt_metadata (dict)
        """
        if self.opt_metadata is None:
            metadata = {'album': self.snippets['title'],
                        'album_artist': self.channel,
                        'year': self.year_uploaded}
            logging.info(f"No optional album metadata provided. Applying defaults.\n"
                         f"{metadata.items()}")
            return metadata
        else:
            if self.opt_metadata and \
                    isinstance(self.opt_metadata, dict) and \
                    all(tag in self.ACCEPTED_TAGS for tag, _ in self.opt_metadata.items()):
                logging.info("Valid album metadata provided.")
                return self.opt_metadata
            else:
                raise YTAPIError("Invalid album metadata provided.")

    @timer
    def download(self, slice_output=True, apply_fade="both", fade_time=0.5):
        """
        Download YT video provided by url and slice into individual videos using timestamps.
        :param slice_output: slice output using timestamps? (boolean)
        :param apply_fade:
        :param fade_time:
        :return: None
        """

        if self.video_output.lower() in self.OUTPUT_FILE_EXT.keys():
            self.video_path = os.path.join(self.OUTPUT_PATH, f"{self.title}.{self.OUTPUT_FILE_EXT[self.output]}")
        else:
            raise PyTubeError(f"Invalid output category ({self.video_output}).")

        if not os.path.exists(self.video_path):
            logging.info(f"Downloading {self.video_output.lower()} for {self.snippets['title']}.")
            self.pytube_dl()
        else:
            logging.info("Pre-existing file found.")

        self._postprocess(slice_output, apply_fade, fade_time)

    def _postprocess(self, slice_output, apply_fade, fade_time):
        if slice_output and isinstance(slice_output, bool):
            # Move to downloader section.
            if self.titles and self.times:
                folder_path = os.path.join(self.OUTPUT_PATH, self.title)
                if not os.path.exists(folder_path):
                    os.makedirs(folder_path)

                logging.info(f"Slicing {self.title}.")
                logging.info(f"Applying fade ({apply_fade}).\n")

                # tqdm progbar for iterating thru titles/times.
                print(f"\nProcessing file: {self.video_path}"
                      f"\nSlicing: {slice_output}, Applying fade ({fade_time}): {apply_fade}")
                self.process_prog_bar = tqdm(total=len(self.titles), position=0, leave=True,
                                             bar_format=" ↳ |{bar:44}|{percentage:3.0f}%")

                for num, (title, times) in enumerate(zip(self.titles, self.times), 1):
                    # ffmpeg can't apply inplace so need different files
                    slice_path = os.path.join(folder_path, f"x{title}.{self.OUTPUT_FILE_EXT[self.output]}")
                    fade_path = os.path.join(folder_path, f"xx{title}.{self.OUTPUT_FILE_EXT[self.output]}")
                    final_output = os.path.join(folder_path, f"{title}.{self.OUTPUT_FILE_EXT[self.output]}")

                    # convert timedelta times to seconds (int).
                    duration = [time.seconds for time in times]

                    # if empty title or unknown, give generic name.
                    # else clean and format.
                    if title in ("", "?"):
                        title = f"track_{num}"
                    else:
                        title = safe_filename(title)

                    slice_audio(source=self.video_path, output=slice_path, duration=duration)

                    if apply_fade:
                        apply_afade(source=slice_path, output=fade_path, in_out=apply_fade, duration=times,
                                    seconds=fade_time)
                    else:
                        fade_path = slice_path

                    # can't add metadata inplace
                    apply_metadata(source=fade_path,
                                   output=final_output,
                                   title=title,
                                   track=num,
                                   album_tags=self.metadata)

                    self.process_prog_bar.update(1)
                    logging.info(f"{title.encode('utf-8')} sliced from {duration[0]} to {duration[1]} seconds.\n")
            else:
                raise PostProcessError("No timestamps to use to slice.")
        else:
            logging.info(f"Unsliced {self.title} saved to {self.OUTPUT_PATH}")

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
                if timestamp.index('') == 0:
                    titles.append(timestamp[-1])
                # if empty group of regex at end. Timestamp title at start.
                elif timestamp.index('') == len(timestamp) - 1:
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
        return [[re.sub("|\[|]|—|-|~", "", item.strip()).strip() for item in timestamp] for timestamp in timestamps]

    def convert_str_time(self, str_times, rtn_fmt="datetime"):
        """
        Convert string time to datetime
        :param str_times: time-like strings (iterable)
        :param rtn_fmt: return datetime or timedelta? (string)
        :return: datetime objects (list)
        """
        # Check if str_times iterable has any invalid dtypes (not a str).
        if any(not isinstance(str_time, str) for str_time in str_times):
            raise YTAPIError(f"Unable to convert invalid string timestamp.\n"
                             f"{str_times}")
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
                converted_times.append((datetime.datetime.strptime(str_time, "%H:%M:%S") - self.BASE_TIME))
        return converted_times

    def validate_timestamps(self, timestamps, min_num_timestamps=5, percent_threshold=0.5):
        # If total number of timestamps below minimum, reject timestamps
        # If total length not within 5% of actual video length, reject timestamps.

        if len(timestamps) < min_num_timestamps:
            return

        # Currently prefixed sum. Convert to individual lengths first.
        # Iterate through each timestamp ignoring last item, the track title.
        dt_timestamps = [self.convert_str_time(timestamp[1:-1]) for timestamp in timestamps]
        if self.timestamp_style == "Start":
            # convert_str_time returns a list of datetimes. only one datetime with start timestamp style so take
            # first item.
            dt_timestamps = [dt[0] for dt in dt_timestamps]
            # subtract next timestamp by current current timestamp
            dt_lengths = [dt_timestamps[ind + 1] - dt_timestamps[ind] for ind in range(len(dt_timestamps) - 1)]
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

    @timer
    def get_video_info(self, *parts):
        if self.video_id:
            # query desired parts from video with matching video id.
            info_request = self.YT.videos().list(part=f"{','.join(parts)}", id=self.video_id)
            info_response = info_request.execute()

            for part in parts:
                requested_part = info_response['items'][0][part]
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
        timestamp_string = timestamp_string.replace('"', '').split('\n')
        dur_timestamps = [re.findall(self.YT_DUR_TIMESTAMPS_REGEX, line) for line in timestamp_string
                          if re.findall(self.YT_DUR_TIMESTAMPS_REGEX, line)]
        start_timestamps = [re.findall(self.YT_START_TIMESTAMPS_REGEX, line) for line in timestamp_string
                            if re.findall(self.YT_START_TIMESTAMPS_REGEX, line)]
        return dur_timestamps, start_timestamps

    @timer
    @property
    def timestamps(self):
        """
        Found timestamps will always be in this form: (str_title_front, *timestamp, str_title_back)
        * timestamp can be one - two strings
        :return:
        """
        valid_timestamps = []
        parsed_timestamps = []

        (desc_dur_timestamps, desc_start_timestamps) = self.find_timestamps(self.desc)

        if desc_timestamps := desc_dur_timestamps or desc_start_timestamps:
            logging.info("Timestamps found in description.")
            chosen_comment = self.desc.split('\n')
            # remove extra list from list comprehension
            desc_timestamps = reduce(lambda x, y: x + y, desc_timestamps)
            # Set timestamp style.
            self.set_timestamp_style(desc_timestamps)
            chosen_timestamps = self.clean_timestamps(desc_timestamps)
        else:
            # If cannot find timestamps in description, check comments
            logging.info("Timestamps not found in description. Checking comment section.")
            for comment in self.extract_comments(max_comments=self.MAX_COMMENTS):

                (comm_dur_timestamps, comm_start_timestamps) = self.find_timestamps(comment)

                # Whichever one isn't an empty list (Not found).
                if comm_timestamps := comm_dur_timestamps or comm_start_timestamps:
                    comm_timestamps = reduce(lambda x, y: x + y, comm_timestamps)
                    # Set timestamp style.

                    self.set_timestamp_style(comm_timestamps)
                    if time_perc_identity := self.validate_timestamps(comm_timestamps):
                        valid_timestamps.append([time_perc_identity, *comment])
                        parsed_timestamps.append(comm_timestamps)
                        logging.info(f"Valid comment timestamps found ({time_perc_identity}).")

            # If choose_comment=True, allow to choose which timestamps to select when multiple are valid.
            # Else, return comment timestamps with highest percentage identity.
            if self.choose_comment:
                if len(valid_timestamps) < 0:
                    logging.info(f"No valid timestamps found in comments.")
                    return
                comment_num = self.select_comment(valid_timestamps)
                chosen_comment = valid_timestamps[int(comment_num) - 1]
                chosen_timestamps = parsed_timestamps[int(comment_num) - 1]
            else:
                sorted_comments = list(sorted(valid_timestamps, key=lambda x: x[0], reverse=True))
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

        logging.info(f"Comment {int(question)} chosen for timestamps.")
        return question

    def save_comment(self, chosen_comment):
        output_path = os.path.join(os.getcwd(), 'output')
        try:
            timestamp_fname = os.path.join(output_path, f'{self.title}_timestamps.txt')
        except FileNotFoundError:
            # If invalid characters in title.
            timestamp_fname = os.path.join(output_path, f'video_timestamp_{datetime.datetime.now()}.txt')
        with open(timestamp_fname, 'w', encoding='utf-8') as fobj:
            fobj.write('\n'.join(chosen_comment))
        logging.info(f"Timestamps saved to {os.path.join(os.getcwd(), timestamp_fname)}.")

    @timer
    def extract_comments(self, max_comments):
        # Comment counter
        comments_checked = 0
        # Must be a multiple of 100.
        if max_comments % 100 != 0:
            raise YTAPIError("Invalid number of comments to check. Must be a multiple of 100.")

        comment_request = self.YT.commentThreads().list(part="snippet, replies", videoId=self.video_id,
                                                        maxResults=100, order="relevance")
        # Increment for first request.
        comments_checked += 100
        while comment_request:
            comment_response = comment_request.execute()
            if comment_threads := comment_response.get('items'):
                for thread in comment_threads:
                    top_level_comment = thread['snippet']['topLevelComment']
                    yield top_level_comment['snippet']['textOriginal']
                # list next returns None if no items remaining.
                comment_request = self.YT.commentThreads().list_next(comment_request, comment_response)
                comments_checked += 100
            else:
                logging.info("No comments found.")
            if comments_checked == max_comments:
                comment_request = None


if __name__ == "__main__":
    """
    Monogatari Soundtrack - Timestamps (start) in desc.
    """
    # test = YTSingleVideoBreakdown(video_url="https://www.youtube.com/watch?v=aeB9qIZPvK8&t=1015s",
    #                               video_output="audio")
    # test = YTSingleVideoBreakdown(video_url="https://www.youtube.com/watch?v=80EUn_6OJ-Q&list=LL&index=4",
    #                               video_output="audio")

    """
    LOTR Soundtrack - Timestamps (duration) in comment section. 
    """
    # test = YTCompDL(
    #     video_url="https://www.youtube.com/watch?v=OJk_1C7oRZg&list=PLJzDTt583BOY28Y996pdRqepIHdysjfiz&index=3",
    #     video_output="audio")

    """
    Animalcule video - No comments.
    """
    # test = YTCompDL(video_url="https://www.youtube.com/watch?v=wXy2T3zXkAs", video_output="video")

    """
    BFV Soundtrack - Timestamp (start) in comment section. Some untitled chapters just have new line char.
    """
    # test = YTCompDL(video_url="https://www.youtube.com/watch?v=KBujC9Sbhas&list=PLJzDTt583BOY28Y996pdRqepIHdysjfiz
    # &index=3")

    """
    Hollow Knight Soundtrack - Timestamp in pinned comment. Surrounded in brackets.
    """
    # test = YTCompDL(video_url="https://www.youtube.com/watch?v=0HbnqjGirFg&list=PLJzDTt583BOY28Y996pdRqepIHdysjfiz
    # &index=6", video_output="audio")

    """
    Chrono Trigger Soundtrack
    Title is first, timestamps are second.
    """
    test = YTCompDL(video_url="https://www.youtube.com/watch?v=waxQzdbixLk",
                    video_output="audio")

    """
    Contradiction Soundtrack
    """
    # test = YTCompDL(video_url="https://www.youtube.com/watch?v=Bs9hJtlFqd4")

    # Start download
    # test.download(slice_output=True, apply_fade="both", fade_time=0.5)
