import logging
import pathlib
import pytube
from typing import Dict
from pytube.cli import on_progress

from ytcompdl.ffmpeg_utils import merge_codecs, convert_audio
from ytcompdl.errors import PyTubeError

logger = logging.getLogger(__name__)


class Pytube_Dl:
    DEF_RESOLUTIONS = (
        "2160p",
        "1440p",
        "1080p",
        "720p",
        "480p",
        "360p",
        "240p",
        "144p",
    )

    def __init__(self, url: str, res: str = "720p") -> None:

        self.url = url
        self.res = res

        self.adap_streams: bool = False
        self.output_files: Dict[str, str] = {}

        self.pt = pytube.YouTube(url=self.url, on_progress_callback=on_progress)

    def pytube_dl(self, output: str):
        """
        Download video with pytube.
        :param output: output path. If none, default to output directory.
        """
        output_dir = pathlib.Path(output).parents[0]

        filename = pathlib.Path(output).name

        output_type = "audio" if output.endswith(".mp3") else "video"

        for stream in self.streams(output_type):
            if output_type == "video" and self.adap_streams:
                # Add output type to prevent overwriting files when downloading video
                categ = "video" if stream.includes_video_track else "audio"
                print(f'Downloading {categ} of "{self.url}" as "{categ}_{filename}".')

                logger.info(
                    f"Downloading {categ} stream of {stream.title} "
                    f"as {categ}_{stream.default_filename}."
                )
                self.output_files[categ] = stream.download(
                    output_path=output_dir,
                    filename=filename,
                    filename_prefix=f"{categ}_",
                )

            else:
                print(f'Downloading audio of "{self.url}" as "audio_{output}".')
                logger.info(f"Downloading {stream.title} as {stream.default_filename}.")
                self.output_files["audio"] = stream.download(
                    output_path=output_dir, filename=filename, filename_prefix="audio_"
                )

        if len(self.output_files) == 0:
            raise PyTubeError("No streams downloaded.")

        # Video: Merge codecs if source streams were adaptive. Otherwise, do nothing.
        # Audio: Convert to single audio stream mp3.
        if output_type == "video" and self.adap_streams:
            logger.debug("Merging audio and video codecs.")

            merge_codecs(self.output_files["audio"], self.output_files["video"], output)

        elif output_type == "audio":
            convert_audio(self.output_files["audio"], output)

        return output

    def list_available_resolutions(self):
        resolutions = {
            stream.resolution for stream in self.pt.streams.filter(type="video")
        }
        sorted_res = sorted(resolutions, key=lambda x: int(x.strip("p")))
        return sorted_res

    def streams(self, output_type: str):
        """
        Get available audio or video streams for a video.
        - progressive is lower quality but includes both audio and video
        - adaptive is best quality but is only video so must merge audio stream
        :param output_type: Output file type.

        :return: Generator of streams.
        """
        # both outputs will need the audio stream. audio stream output is mp4a
        audio_stream = self.pt.streams.get_audio_only()

        if output_type == "audio":
            yield audio_stream
        else:
            if self.res in self.DEF_RESOLUTIONS:
                if video_stream := self.pt.streams.filter(res=self.res).first():
                    # Will need to know to merge adaptive streams later.
                    self.adap_streams = True

                    yield video_stream
                    yield audio_stream
                else:
                    logger.info(
                        f"No video stream found with desired resolution: {self.res}"
                    )
                    prog_stream = self.pt.streams.get_highest_resolution()
                    logger.info(
                        f"Defaulting to progressive stream with highest resolution ({prog_stream.resolution})."
                    )
                    yield prog_stream
            else:
                raise PyTubeError(f"Invalid resolution ({self.res}).")

    @property
    def stream_filesize(self):
        return sum(stream.filesize for stream in self.streams)
