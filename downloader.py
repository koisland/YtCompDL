import os
import pprint
import pytube
from pytube.helpers import safe_filename
import logging
from tqdm import tqdm

from ffmpeg_utils import merge_codecs, convert_audio
from utils import timer
from errors import PyTubeError
from config import Config

# Prevent verbose logging for pytube.
pytube_logger = logging.getLogger('pytube')
pytube_logger.setLevel(logging.ERROR)

logging.basicConfig(filename='yt_data.log', filemode='w', level=logging.DEBUG,
                    format="%(asctime)s - %(levelname)s - %(message)s")


class Pytube_Dl(Config):

    def __init__(self, url, output, res="720p"):
        self.url = url
        self.output = output
        self.res = res

        self.dl_prog_bar = None
        self.adap_streams = False
        self.output_files = []

        self.pt = pytube.YouTube(url=self.url, on_progress_callback=self._show_progress)
        self.streams = self._get_streams()
        self.fname = f"{safe_filename(self.pt.title)}.{self.DEF_DL_FILE_EXT}"

    def pytube_dl(self, output=None):
        if output is None:
            output = self.OUTPUT_PATH
        if not os.path.exists(output):
            raise PyTubeError(f"Path ({output}) doesn't exist.")
        elif os.path.exists(os.path.join(output, self.fname)):
            raise PyTubeError(f"File ({os.path.join(output, self.fname)}) already exists.")
        elif not self.streams:
            raise PyTubeError("No streams to download.")

        # Setup prog bar and have contain filesize of all desired streams.
        print(f'Downloading "{self.url}" as "{self.fname}".')
        self.dl_prog_bar = tqdm(total=sum(stream.filesize for stream in self.streams))

        for stream in self.streams:
            # prepend output type to prevent overwriting files when downloading video
            if self.output == "video" and self.adap_streams:
                if stream.includes_video_track:
                    categ = "video_"
                else:
                    categ = "audio_"
                logging.info(f"Downloading {categ.strip('_')} stream of {stream.title} "
                             f"as {categ + stream.default_filename}.")
                self.output_files.append(stream.download(output_path=output, filename_prefix=categ))
            else:
                logging.info(f"Downloading {stream.title} as {stream.default_filename}.")
                self.output_files.append(stream.download(output_path=output))

        # video: merge codecs if source streams were adaptive
        # audio: convert to mp3
        if self.output == "video" and self.adap_streams:
            print("Merging audio and video.")
            logging.debug("Merging audio and video codecs")
            merge_codecs(*self.output_files, os.path.join(self.OUTPUT_PATH, self.fname))
        else:
            mp3_fname = self.fname.strip(".mp4") + ".mp3"
            print(f'Converting "{self.fname}" to "{mp3_fname}"')
            convert_audio(*self.output_files, os.path.join(self.OUTPUT_PATH, mp3_fname))

    def list_available_resolutions(self):
        resolutions = {stream.resolution for stream in self.pt.streams.filter(type="video")}
        sorted_res = sorted(resolutions, key=lambda x: int(x.strip("p")))
        print(sorted_res)
        return sorted_res

    def _get_streams(self):
        streams = []
        # both outputs will need the audio stream. audio stream output is mp4a
        # [print(stream) for stream in self.pt.streams.filter(only_audio=True)]
        audio_stream = self.pt.streams.get_audio_only()

        if self.output == "audio":
            streams.append(audio_stream)
        elif self.output == "video":
            if self.res in self.DEF_RESOLUTIONS:
                if video_stream := self.pt.streams.filter(res=self.res).first():
                    # Will need to know to merge adaptive streams later.
                    self.adap_streams = True
                    streams.append(video_stream)
                    streams.append(audio_stream)
                else:
                    logging.info(f"No video stream found with desired resolution: {self.res}")
                    prog_stream = self.pt.streams.get_highest_resolution()
                    logging.info(f"Defaulting to progressive stream with highest resolution ({prog_stream.resolution}).")
                    streams.append(prog_stream)
            else:
                raise PyTubeError(f"Invalid resolution ({self.res}).")
        else:
            raise PyTubeError(f"Invalid format ({self.output}).")

        return streams

    def _show_progress(self, *args):
        (_, data_chunk, _) = args
        self.dl_prog_bar.update(len(data_chunk))


if __name__ == "__main__":
    # dl = Pytube_Dl(url="https://www.youtube.com/watch?v=80EUn_6OJ-Q&list=LL&index=4",
    #                output="video", res="2160p")
    dl = Pytube_Dl(url="https://www.youtube.com/watch?v=g5ShI1dTeUI",
                   output="audio")
    dl.pytube_dl()
    # dl.list_available_resolutions()
