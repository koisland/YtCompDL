# ffmpeg
# https://ffmpeg.org/ffmpeg.html#toc-Main-options

# Trimming
# https://unix.stackexchange.com/questions/182602/trim-audio-file-using-start-and-stop-times

# Add tags/metdata
# https://superuser.com/questions/1331752/ffmpeg-adding-metadata-to-an-mp3-from-mp3-input
# https://wiki.multimedia.cx/index.php/FFmpeg_Metadata
# https://stackoverflow.com/questions/18710992/how-to-add-album-art-with-ffmpeg


import os
import subprocess


def slice_audio(path):
    start = 0
    stop = 60
    output = "Suruga Kanbaru's Life.mp3"
    cmd = ['ffmpeg', '-i', f'{path}', '-ss', f'{start}', '-to', f'{stop}', '-c', f'"{output}"']
    print(' '.join(cmd))


if __name__ == "__main__":
    mp3_path = os.path.join(os.getcwd(), "output", "Monogatari.mp3")
    print(mp3_path)
    slice_audio(mp3_path)
