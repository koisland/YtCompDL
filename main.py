import os
import re
import datetime
import pprint
import logging
from functools import reduce
from googleapiclient.discovery import build
from youtube_dl.utils import sanitize_filename

from downloader import ydl_downloader
from ffmpeg_utils import slice_audio, apply_afade, apply_metadata
from utils import timer

"""
General documentation for py
https://github.com/googleapis/google-api-python-client
"""

"""
YT py methods page
https://googleapis.github.io/google-api-python-client/docs/dyn/youtube_v3.html
"""

"""
General yt documentation
https://developers.google.com/youtube/v3/docs
"""
logging.basicConfig(filename='yt_data.log', filemode='w', level=logging.DEBUG,
                    format="%(asctime)s - %(levelname)s - %(message)s")


class YTSingleVideoBreakdown:
    # Setup build func to allow access to Youtube API.
    YT = build(serviceName="youtube", version="v3", developerKey=os.environ.get("YT_API_KEY"))

    # Regexp to parse strings (id, timestamps, etc.)
    YT_ID_REGEX = re.compile(r"(?<=v=)(.*?)(?=(?:&|$))")
    TIME_PATTERN = r"\d{1,2}:?\d*:\d{2}"
    # Spacer characters between time or titles to ignore.
    IGNORE_CHRS = r"—|-|\s|\[|\]"
    # Works only if text is split line-by-line.
    YT_START_TIMESTAMPS_REGEX = \
        re.compile(f"(.*?)(?:{IGNORE_CHRS})*({TIME_PATTERN})(?:{IGNORE_CHRS})*(.*)")
    YT_DUR_TIMESTAMPS_REGEX = \
        re.compile(f"(.*?)(?:{IGNORE_CHRS})*({TIME_PATTERN})(?:{IGNORE_CHRS})*({TIME_PATTERN})(?:{IGNORE_CHRS})*(.*)")

    BASE_TIME = datetime.datetime.strptime("1900-01-01 00:00:00", "%Y-%m-%d %H:%M:%S")

    ACCEPTED_TAGS = ("album", "composer", "genre", "artist", "album_artist", "date")

    def __init__(self, video_url, metadata=None):
        """
        :param video_url: Youtube video url. (string)
        :param album_metadata: Optional album metadata (dict)
        Titles and track numbers applied by default.
        """
        self.video_url = video_url
        self.video_id = self.extract_id()
        self.snippets, self.content_details = list(self.get_video_info('snippet', 'contentDetails'))

        # Use youtube-dl util function "sanitize_filename".
        self.title = sanitize_filename(self.snippets['title']).replace("  ", " ").replace(" ", "_")
        self.desc = self.snippets['description']
        self.channel = self.snippets['channelTitle']
        self.upload_time = self.snippets['publishedAt']
        self.year_uploaded = self.upload_time.split('-')[0]
        self.metadata = self.set_metadata(metadata)

        # datetime.timedelta4
        time_pattern = f"PT{self.set_dtime_format('H')}{self.set_dtime_format('M')}{self.set_dtime_format('S')}"
        self.duration = datetime.datetime.strptime(self.content_details['duration'], time_pattern) - self.BASE_TIME

        self.timestamp_style = None
        self.extract_comments(max_comments=1000)
        self.timestamps = self.find_timestamps(select_comment=True, save_timestamps=True)
        pprint.pprint(self.timestamps)
        self.titles, self.times = self.format_timestamps()

    def set_metadata(self, metadata):
        if metadata is None:
            metadata = {'album': self.snippets['title'],
                        'album_artist': self.channel,
                        'year': self.year_uploaded}
            logging.info(f"No optional album metadata provided. Applying defaults.\n"
                         f"{metadata.items()}")
            return metadata
        else:
            if metadata and \
                    isinstance(metadata, dict) and \
                    all(tag in self.ACCEPTED_TAGS for tag, _ in metadata.items()):
                logging.info("Valid album metadata provided.")
                return metadata
            else:
                raise Exception("Invalid album metadata provided.")

    def download(self, output="audio", slice_output=True, apply_fade="both", fade_time=0.5):
        """
        Download YT video provided by url and slice into individual videos using timestamps.
        :param output: audio or video output (string)
        :param slice_output: slice output using timestamps? (boolean)
        :param apply_fade:
        :param fade_time:
        :return:
        """
        download_path = os.path.join(os.getcwd(), 'output')
        video_path = os.path.join(download_path, f"{self.title}.mp3")
        thumbnail_path = os.path.join(download_path, f"{self.title}.jpg")

        if not os.path.exists(video_path):
            if output.lower() not in ("audio", "video"):
                raise Exception("Invalid output format.")
            logging.info(f"Downloading {output.lower()} for {self.snippets['title']}.")
            ydl_downloader(self.video_url, output)
        else:
            logging.info("Pre-existing file found.")
        if slice_output:
            if self.titles and self.times:
                folder_path = os.path.join(download_path, self.title)
                if not os.path.exists(folder_path):
                    os.makedirs(folder_path)

                logging.info(f"Slicing {self.title}...")
                for num, (title, times) in enumerate(zip(self.titles, self.times), 1):
                    duration = [time.seconds for time in times]

                    s_path = os.path.join(folder_path, f"x{title}.mp3")
                    f_path = os.path.join(folder_path, f"xx{title}.mp3")
                    final_output = os.path.join(folder_path, f"{title}.mp3")

                    slice_audio(source=video_path, output=s_path, duration=duration)
                    if apply_fade:
                        logging.info(f"Applying fade ({apply_fade})")
                        apply_afade(source=s_path, output=f_path, in_out=apply_fade, seconds=fade_time)
                    # can't add metadata inplace
                    apply_metadata(source=f_path,
                                   output=final_output,
                                   title=title,
                                   track=num,
                                   album_tags=self.metadata,
                                   cover=thumbnail_path)

                    logging.info(f"{title.encode('utf-8')} sliced from {duration[0]} to {duration[1]} seconds.\n")
            else:
                raise Exception("No timestamps could be parsed.")
        else:
            logging.info(f"Unsliced {self.title} saved to {download_path}")

    def set_dtime_format(self, char):
        # Sets pattern for converting duration string into datetime.datetime
        if char in self.content_details['duration']:
            return f"%{char}{char}"
        else:
            return ""

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
            if timestamp.index('') == 0:
                titles.append(timestamp[-1])
            elif timestamp.index('') == -1:
                titles.append(timestamp[0])

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
            times.append([times[-1][1] + 1, self.duration])
        return titles, times

    @staticmethod
    def clean_timestamps(timestamps):
        """
        Remove characters used to separate timestamp and title.
        :param timestamps:  timestamp/title strings (list of lists)
        :return: modified timestamp/title strings (list of lists)
        """
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
            raise Exception("Unable to convert invalid string timestamp.")
        TIME_LENGTH = 8
        # First pad time to standardize.
        converted_times = []
        for str_time in str_times:
            while len(str_time) < TIME_LENGTH:
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
            # convert_str_time returns a list of datetimes. only one datetime with start timestamp style so take first item.
            dt_timestamps = [dt[0] for dt in dt_timestamps]
            # subtract next timestamp by current current timestamp
            dt_lengths = [dt_timestamps[ind + 1] - dt_timestamps[ind] for ind in range(len(dt_timestamps) - 1)]
        else:
            # end of timestamp - start of timestamp
            dt_lengths = [dur[1] - dur[0] for dur in dt_timestamps]

        total_length = reduce(lambda x, y: x + y, dt_lengths)

        # If estimated length is under percent threshold, reject timestamp.
        # Main issue is that with start timestamps, last item will not be counted.
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
        else:
            logging.error("Exception occurred", exc_info=True)
            raise Exception("Unable to parse video id from provided url.")

    def set_timestamp_style(self, timestamps):
        # if length of all timestamps is 3, timestamp is based on start of chapter.
        # if length of all timestamps is 4, timestamp is based on duration of chapter.
        if all(len(timestamp) == 3 for timestamp in timestamps):
            self.timestamp_style = "Start"
        elif all(len(timestamp) == 4 for timestamp in timestamps):
            self.timestamp_style = "Duration"
        else:
            logging.error("Invalid format in retrieved timestamps.")

    @timer
    def find_timestamps(self, select_comment=False, save_timestamps=True):
        """
        Found timestamps will always be in this form: (str_title_front, *timestamp, str_title_back)
        * timestamp can be one - two strings
        :param select_comment:
        :param save_timestamps:
        :return:
        """
        valid_timestamps = []
        parsed_timestamps = []
        desc = self.desc.split("\n")

        desc_dur_timestamps = [re.findall(self.YT_DUR_TIMESTAMPS_REGEX, desc_line) for desc_line in desc
                               if re.findall(self.YT_DUR_TIMESTAMPS_REGEX, desc_line)]
        desc_start_timestamps = [re.findall(self.YT_START_TIMESTAMPS_REGEX, desc_line) for desc_line in desc
                                 if re.findall(self.YT_START_TIMESTAMPS_REGEX, desc_line)]

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
            for comment in self.extract_comments():
                # Split comment into lines to avoid bad regex matches at end.
                comment = comment.split('\n')
                comm_dur_timestamps = [re.findall(self.YT_DUR_TIMESTAMPS_REGEX, cmt_line) for cmt_line in comment
                                       if re.findall(self.YT_DUR_TIMESTAMPS_REGEX, cmt_line)]
                comm_start_timestamps = [re.findall(self.YT_START_TIMESTAMPS_REGEX, cmt_line) for cmt_line in comment
                                         if re.findall(self.YT_START_TIMESTAMPS_REGEX, cmt_line)]
                # Whichever one isn't an empty list (Not found).
                if comm_timestamps := comm_dur_timestamps or comm_start_timestamps:
                    comm_timestamps = reduce(lambda x, y: x + y, comm_timestamps)
                    # Set timestamp style.
                    self.set_timestamp_style(comm_timestamps)
                    if time_perc_identity := self.validate_timestamps(comm_timestamps):
                        valid_timestamps.append([time_perc_identity, *comment])
                        parsed_timestamps.append(comm_timestamps)
                        logging.info(f"Valid comment timestamps found ({time_perc_identity}).")

            # If number of valid timestamps is greater than 0.
            if len(valid_timestamps) > 0:
                # If select_comment=True, allow to choose which timestamps to select when multiple are valid.
                # Else, return comment timestamps with highest percentage identity.
                if select_comment:
                    total_comments = len(valid_timestamps)
                    for num, v_comment in enumerate(valid_timestamps):
                        print(f"[{num + 1}]")
                        pprint.pprint(v_comment)

                    question = input(f"Select comment. (1-{total_comments})\n")
                    while int(question) not in range(1, total_comments + 1):
                        print(f"Invalid comment ({question}). Please try again.\n")
                        question = input(f"Select comment. (1-{total_comments})\n")

                    logging.info(f"Comment {int(question)} chosen for timestamps.")
                    chosen_comment = valid_timestamps[int(question) - 1]
                    chosen_timestamps = parsed_timestamps[int(question) - 1]
                else:
                    sorted_comments = list(sorted(valid_timestamps, key=lambda x: x[0], reverse=True))
                    chosen_comment = sorted_comments[0]
                    # Need original index before sort to get parsed timestamps.
                    original_index = valid_timestamps.index(chosen_comment)
                    chosen_timestamps = parsed_timestamps[original_index]
            else:
                logging.info(f"No valid timestamps found in comments.")
                return

        # Save timestamps to file named f"{title}_timestamps.txt"
        if save_timestamps:
            output_path = os.path.join(os.getcwd(), 'output')
            try:
                timestamp_fname = os.path.join(output_path, f'{self.title}_timestamps.txt')
            except FileNotFoundError:
                # If invalid characters in title.
                timestamp_fname = os.path.join(output_path, f'video_timestamp_{datetime.datetime.now()}.txt')
            with open(timestamp_fname, 'w', encoding='utf-8') as fobj:
                fobj.write('\n'.join(chosen_comment))
            logging.info(f"Timestamps saved to {os.path.join(os.getcwd(), timestamp_fname)}.")

        return self.clean_timestamps(chosen_timestamps)

    @timer
    def extract_comments(self, max_comments=500):
        # Comment counter
        comments_checked = 0
        # Must be a multiple of 100.
        if max_comments % 100 != 0:
            raise Exception("Invalid number of comments to check. Must be a multiple of 100.")

        comment_request = self.YT.commentThreads().list(part="snippet, replies", videoId=self.video_id,
                                                        maxResults=100, order="relevance")
        # Increment for first request.
        comments_checked += 100
        while comment_request:
            comment_response = comment_request.execute()
            if comment_threads := comment_response.get('items'):
                logging.info('Comments found.')
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

    def extract_id(self):
        if id_search := re.search(self.YT_ID_REGEX, self.video_url):
            return id_search.group(1)


if __name__ == "__main__":
    """
    Monogatari Soundtrack - Timestamps (start) in desc.
    """
    # test = YTSingleVideoBreakdown(video_url="https://www.youtube.com/watch?v=80EUn_6OJ-Q&list=LL&index=4")

    """
    LOTR Soundtrack - Timestamps (duration) in comment section. 
    """
    # test = YTSingleVideoBreakdown(
    #     video_url="https://www.youtube.com/watch?v=OJk_1C7oRZg&list=PLJzDTt583BOY28Y996pdRqepIHdysjfiz&index=3")

    """
    Animalcule video - No comments.
    """
    # test = YTSingleVideoBreakdown(video_url="https://www.youtube.com/watch?v=wXy2T3zXkAs")

    """
    BFV Soundtrack - Timestamp (start) in comment section. Some untitled chapters just have new line char.
    """
    test = YTSingleVideoBreakdown(
        video_url="https://www.youtube.com/watch?v=KBujC9Sbhas&list=PLJzDTt583BOY28Y996pdRqepIHdysjfiz&index=3")

    """
    Hollow Knight Soundtrack - Timestamp in pinned comment. Surrounded in brackets.
    """
    # test = YTSingleVideoBreakdown(video_url="https://www.youtube.com/watch?v=0HbnqjGirFg&list=PLJzDTt583BOY28Y996pdRqepIHdysjfiz&index=6")

    """
    Chrono Trigger Soundtrack
    Title is first, timestamps are second.
    """
    # test = YTSingleVideoBreakdown(video_url="https://www.youtube.com/watch?v=fvKGHjpsp-g")
    # test2 = YTSingleVideoBreakdown(video_url="https://www.youtube.com/watch?v=waxQzdbixLk")

    test.download(output="audio", slice_output=True, apply_fade="both", fade_time=0.5)
