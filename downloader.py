import youtube_dl

"""
https://github.com/ytdl-org/youtube-dl/blob/master/README.md#embedding-youtube-dl
Embedding ytdl in python
"""


class Ydl_Logger(object):
    # TODO: Work on outputting to yt_data.log
    def debug(self, msg):
        print(msg)


def ydl_downloader(url, output):
    if output == "audio":
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192'}],
            'logger': Ydl_Logger(),
            'noplaylist': True}
    else:
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192'
            }]}

    # TODO: Track progress of video conversion to audio with ffmpeg.
    #  Might need to use pexpect to spawn child process.
    #  https://stackoverflow.com/questions/7632589/getting-realtime-output-from-ffmpeg-to-be-used-in-progress-bar-pyqt4-stdout#answer-7641175
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
