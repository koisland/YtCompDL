import os
import re
import datetime
import pprint
import logging
from functools import reduce
from googleapiclient.discovery import build
from downloader import ydl_downloader

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

    # regexp to parse strings (id, timestamps, etc.)
    YT_ID_REGEX = re.compile(r"(?<=v=)(.*?)(?=(?:&|$))")
    # start time and chapter title
    YT_START_TIMESTAMPS_REGEX = re.compile(r"(\d{1,2}:?\d*:\d{2})[\s-]*?(.*)")
    # duration and chapter title
    YT_DUR_TIMESTAMPS_REGEX = re.compile(r"(\d{1,2}:?\d*:\d{2})[\s-]*?(\d{1,2}:?\d*:\d{2})(.*)")

    BASE_TIME = datetime.datetime.strptime("1900-01-01 00:00:00", "%Y-%m-%d %H:%M:%S")

    def __init__(self, video_url, output="audio"):
        self.output = output
        self.video_url = video_url
        self.video_id = self.extract_id()

        self.snippets, self.content_details = list(self.get_video_info('snippet', 'contentDetails'))
        self.title = self.snippets['title']
        self.desc = self.snippets['description']
        self.channel = self.snippets['channelTitle']
        self.upload_time = self.snippets['publishedAt']
        
        # datetime.timedelta
        time_pattern = f"PT{self.set_dtime_format('H')}{self.set_dtime_format('M')}{self.set_dtime_format('S')}"
        self.duration = datetime.datetime.strptime(self.content_details['duration'], time_pattern) - self.BASE_TIME

        self.timestamp_style = None
        self.timestamps = self.find_timestamps()
        ydl_downloader(self.video_url, "audio")

    def set_dtime_format(self, char):
        # Sets pattern for converting duration string into datetime.datetime
        if char in self.content_details['duration']:
            return f"%{char}{char}"
        else:
            return ""

    @staticmethod
    def clean_timestamps(timestamps):
        # Remove characters used to separate timestamp and title.
        return [[re.sub("|\[|]|—|-|~", "", item.strip()).strip() for item in timestamp] for timestamp in timestamps]

    @staticmethod
    def convert_time(str_times):
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
            converted_times.append(datetime.datetime.strptime(str_time, "%H:%M:%S"))
        return converted_times

    def validate_timestamps(self, timestamps, min_num_timestamps=5, percent_threshold=0.90):
        # If total number of timestamps below minimum, reject timestamps
        # If total length not within 5% of actual video length, reject timestamps.

        if len(timestamps) < min_num_timestamps:
            return

        # Currently prefixed sum. Convert to individual lengths first.
        # Iterate through each timestamp ignoring last item, the track title.
        dt_timestamps = [self.convert_time(timestamp[0:-1]) for timestamp in timestamps]
        if self.timestamp_style == "Start":
            # convert_time returns a list of datetimes. only one datetime with start timestamp style so take first item.
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
            return f"Percent similarity: {round(percent_identity * float(100), 2) }%"

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

    def find_timestamps(self, select_comment=False, save_timestamps=True):
        valid_timestamps = []
        parsed_timestamps = []

        if desc_timestamps := re.findall(self.YT_START_TIMESTAMPS_REGEX, self.desc):
            # pprint.pprint(chapters)
            logging.info("Timestamps found in description.")
            chosen_comment = self.desc.split('\n')
            chosen_timestamps = self.clean_timestamps(desc_timestamps)
        else:
            # If cannot find timestamps in description, check comments
            logging.info("Timestamps not found in description. Checking comment section.")
            for comment in self.extract_comments():
                if comm_timestamps := re.findall(self.YT_DUR_TIMESTAMPS_REGEX, comment) \
                                      or re.findall(self.YT_START_TIMESTAMPS_REGEX, comment):

                    # if length of all timestamps is 2, timestamp is based on start of chapter.
                    # if length of all timestamps is 3, timestamp is based on duration of chapter.
                    if all(len(timestamp) == 2 for timestamp in comm_timestamps):
                        self.timestamp_style = "Start"
                    elif all(len(timestamp) == 3 for timestamp in comm_timestamps):
                        self.timestamp_style = "Duration"
                    else:
                        logging.error("Invalid format in retrieved timestamps.")

                    if time_perc_identity := self.validate_timestamps(comm_timestamps):
                        valid_timestamps.append([time_perc_identity, comment])
                        parsed_timestamps.append(comm_timestamps)
                        logging.info(f"Valid comment timestamps found ({time_perc_identity}).")

            # If select_comment=True, allow to choose which timestamps to select when multiple are valid.
            # Else, return comment timestamps with highest percentage identity.
            if select_comment:
                total_comments = len(valid_timestamps)
                for num, v_comment in enumerate(valid_timestamps):
                    print(f"[{num+1}]")
                    pprint.pprint(v_comment)

                question = input(f"Select comment. (1-{total_comments})\n")
                while int(question) not in range(1, total_comments+1):
                    print(f"Invalid comment ({question}). Please try again.\n")
                    question = input(f"Select comment. (1-{total_comments})\n")

                logging.info(f"Comment {int(question)} chosen for timestamps.")
                chosen_comment = valid_timestamps[int(question)-1]
                chosen_timestamps = parsed_timestamps[int(question)-1]
            else:
                sorted_comments = list(sorted(valid_timestamps, key=lambda x: x[0], reverse=True))
                chosen_comment = sorted_comments[0]
                # Need original index before sort to get parsed timestamps.
                original_index = valid_timestamps.index(chosen_comment)
                chosen_timestamps = parsed_timestamps[original_index]

        # Save timestamps to file named f"{title}_timestamps.txt"
        if save_timestamps:
            # TODO: Replace title characters not allowed as file.
            try:
                timestamp_fname = f'{self.title.replace("/", "")}_timestamps.txt'
            except FileNotFoundError:
                # If invalid characters in title.
                timestamp_fname = 'video_timestamp.txt'
            with open(timestamp_fname, 'w', encoding='utf-8') as fobj:
                fobj.write('\n'.join(chosen_comment))
            logging.info(f"Timestamps saved to {os.path.join(os.getcwd(), timestamp_fname)}.")

        return self.clean_timestamps(chosen_timestamps)

    def extract_comments(self, num=100):
        comment_request = self.YT.commentThreads().list(part="snippet, replies", videoId=self.video_id,
                                                        maxResults=num, order="relevance")
        comment_response = comment_request.execute()
        if comment_threads := comment_response.get('items'):
            logging.info('Comments found.')
            for thread in comment_threads:
                top_level_comment = thread['snippet']['topLevelComment']
                yield top_level_comment['snippet']['textOriginal']
        else:
            logging.info("No comments found.")

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
    test = YTSingleVideoBreakdown(
        video_url="https://www.youtube.com/watch?v=OJk_1C7oRZg&list=PLJzDTt583BOY28Y996pdRqepIHdysjfiz&index=3")

    """
    Animalcule video - No comments.
    """
    # test = YTSingleVideoBreakdown(video_url="https://www.youtube.com/watch?v=wXy2T3zXkAs")

    """
    BFV Soundtrack - Timestamp (start) in comment section. Some untitled chapters just have new line char.
    """
    # test = https://www.youtube.com/watch?v=KBujC9Sbhas&list=PLJzDTt583BOY28Y996pdRqepIHdysjfiz&index=3

    """
    Hollow Knight Soundtrack - Timestamp in pinned comment. Surrounded in brackets.
    """
    # test = YTSingleVideoBreakdown(video_url="https://www.youtube.com/watch?v=0HbnqjGirFg&list=PLJzDTt583BOY28Y996pdRqepIHdysjfiz&index=6")
