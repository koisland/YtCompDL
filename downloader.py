import os
import pprint
import pytube
import logging
from tqdm import tqdm

from ffmpeg_utils import merge_codecs
from utils import timer

logging.basicConfig(filename='yt_data.log', filemode='w', level=logging.DEBUG,
                    format="%(asctime)s - %(levelname)s - %(message)s")


class Pytube_Dl:
    OUTPUT_PATH = os.path.join(os.getcwd(), 'output')

    def __init__(self, url, output, res="480p"):
        self.url = url
        self.output = output
        self.res = res
        self.yt = pytube.YouTube(url=self.url,
                                 on_progress_callback=self.show_progress)

        self.prog_bar = None
        self.adap_streams = False
        self.streams = self.get_streams()
        self.fname = self.streams[0].default_filename
        self.output_files = []

    def download(self, output=OUTPUT_PATH):
        if not os.path.exists(output):
            raise Exception("Path doesn't exist.")
        if not self.streams:
            raise Exception("No streams to download.")

        # Setup prog bar and have contain filesize of all desired streams.
        self.prog_bar = tqdm(total=sum(stream.filesize for stream in self.streams))

        for stream in self.streams:
            # prepend output type to prevent overwriting files when downloading video
            if self.output == "video" and self.adap_streams:
                if stream.includes_video_track:
                    categ = "video_"
                else:
                    categ = "audio_"
                logging.info(f"Downloading {categ} stream of {stream.title} as {stream.default_filename}.")
                self.output_files.append(stream.download(output_path=output, filename_prefix=categ))
            else:
                logging.info(f"Downloading {stream.title} as {stream.default_filename}.")
                self.output_files.append(stream.download(output_path=output))

        if self.output == "video" and self.adap_streams:
            merge_codecs(*self.output_files, os.path.join(self.OUTPUT_PATH, self.fname))

    def get_streams(self):
        streams = []
        # both outputs will need the audio stream
        # [print(stream) for stream in self.yt.streams.filter(only_audio=True)]
        audio_stream = self.yt.streams.get_audio_only()

        if self.output == "audio":
            streams.append(audio_stream)
        elif self.output == "video":
            if self.res in ("2160p", "1440p", "1080p", "720p",
                            "480p", "360p", "240p", "144p"):
                if video_stream := self.yt.streams.filter(res=self.res).first():
                    # Will need to know to merge adaptive streams later.
                    self.adap_streams = True
                    streams.append(video_stream)
                    streams.append(audio_stream)
                else:
                    logging.info(f"No video stream found with desired resolution: {self.res}")
                    logging.info(f"Defaulting to progressive stream with highest resolution.")
                    prog_stream = self.yt.streams.get_highest_resolution()
                    streams.append(prog_stream)
            else:
                raise Exception("Invalid resolution.")
        else:
            raise Exception("Invalid format.")
        return streams

    def show_progress(self, stream, data_chunk, bytes_left):
        self.prog_bar.update(len(data_chunk))


if __name__ == "__main__":
    dl = Pytube_Dl(url="https://www.youtube.com/watch?v=80EUn_6OJ-Q&list=LL&index=4",
                   output="video",
                   res="1080p")
    # dl = Pytube_Dl(url="https://www.youtube.com/watch?v=g5ShI1dTeUI",
    #                output="audio")
    dl.download()
