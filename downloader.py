import os
import youtube_dl

"""
https://github.com/ytdl-org/youtube-dl/blob/master/README.md#embedding-youtube-dl
Embedding ytdl in python
"""

import logging

logging.basicConfig(filename='yt_data.log', filemode='w', level=logging.DEBUG,
                    format="%(asctime)s - %(levelname)s - %(message)s")


class Ydl_Logger(object):

    def error(self, msg):
        logging.error(msg)

    def debug(self, msg):
        print(msg)
        pass
        # logging.debug(msg)


def ydl_downloader(url, output):
    dest = os.path.join(os.getcwd(), 'output', '%(title)s.%(ext)s')
    if output == "audio":
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192'}],
            # Output processed file to output folder
            'outtmpl': dest,
            'restrictfilenames': True,
            'logger': Ydl_Logger(),
            # Ignore playlist and just download single video.
            'noplaylist': True,
            # Save thumbnail and use.
            'writethumbnail': True,
            }
    else:
        ydl_opts = {
            'format': 'bestvideo/best',
            'outtmpl': dest,
            'logger': Ydl_Logger(),
            }

    # TODO: Just add hook saying that conversion with ffmpeg occuring.
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
        logging.info("Download/conversion finished.")
