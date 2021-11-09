import os
import pytube
from pytube.cli import on_progress
from pytube.helpers import safe_filename
import logging

from ytcompdl.ffmpeg_utils import merge_codecs, convert_audio
from ytcompdl.errors import PyTubeError
from ytcompdl.config import Config

logger = logging.getLogger(__name__)


class Pytube_Dl(Config):
    def __init__(self, url, output, res="720p"):
        self.url = url
        self.output = output
        self.res = res

        self.adap_streams = False
        self.output_files = []

        self.pt = pytube.YouTube(url=self.url, on_progress_callback=on_progress)
        self.fname = f"{safe_filename(self.pt.title)}.mp4"

    @property
    def url(self):
        return self._url

    @url.setter
    def url(self, url):
        self._url = url

    @property
    def output(self):
        return self._output

    @output.setter
    def output(self, output):
        self._output = output

    async def pytube_dl(self, output=None):
        if output is None:
            output = self.OUTPUT_DIR
        if not os.path.exists(output):
            raise PyTubeError(f"Path ({output}) doesn't exist.")
        if not self.streams:
            raise PyTubeError("No streams to download.")

        # Setup prog bar and have contain filesize of all desired streams.
        print(f'Downloading "{self.url}" as "{self.fname}".')

        for stream in self.streams:
            # prepend output type to prevent overwriting files when downloading video
            if self.output == "video" and self.adap_streams:
                if stream.includes_video_track:
                    categ = "video_"
                else:
                    categ = "audio_"
                logger.info(f"Downloading {categ.strip('_')} stream of {stream.title} "
                            f"as {categ + stream.default_filename}.")
                self.output_files.append(stream.download(output_path=output, filename_prefix=categ))
            else:
                logger.info(f"Downloading {stream.title} as {stream.default_filename}.")
                self.output_files.append(stream.download(output_path=output))

        # video: merge codecs if source streams were adaptive. otherwise, do nothing.
        # audio: convert to mp3
        if self.output == "video" and self.adap_streams:
            logger.debug("Merging audio and video codecs")
            video_fname = os.path.join(self.OUTPUT_DIR, self.fname)
            await merge_codecs(*self.output_files, video_fname)
            return video_fname
        elif self.output == "audio":
            audio_fname = self.fname.strip(".mp4") + ".mp3"
            await convert_audio(*self.output_files, os.path.join(self.OUTPUT_DIR, audio_fname))
            return audio_fname

    def list_available_resolutions(self):
        resolutions = {stream.resolution for stream in self.pt.streams.filter(type="video")}
        sorted_res = sorted(resolutions, key=lambda x: int(x.strip("p")))
        return sorted_res

    @property
    def streams(self):
        # both outputs will need the audio stream. audio stream output is mp4a
        audio_stream = self.pt.streams.get_audio_only()

        if self.output == "audio":
            yield audio_stream
        elif self.output == "video":
            if self.res in self.DEF_RESOLUTIONS:
                if video_stream := self.pt.streams.filter(res=self.res).first():
                    # Will need to know to merge adaptive streams later.
                    self.adap_streams = True
                    yield video_stream
                    yield audio_stream
                else:
                    logger.info(f"No video stream found with desired resolution: {self.res}")
                    prog_stream = self.pt.streams.get_highest_resolution()
                    logger.info(
                        f"Defaulting to progressive stream with highest resolution ({prog_stream.resolution}).")
                    yield prog_stream
            else:
                raise PyTubeError(f"Invalid resolution ({self.res}).")
        else:
            raise PyTubeError(f"Invalid format ({self.output}).")

    @property
    def stream_filesize(self):
        return sum(stream.filesize for stream in self.streams)
