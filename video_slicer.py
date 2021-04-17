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
import logging
from datetime import timedelta
from collections.abc import Collection

logging.basicConfig(filename='yt_data.log', filemode='w', level=logging.DEBUG,
                    format="%(asctime)s - %(levelname)s - %(message)s")


def slice_audio(source, output, duration):
    if not os.path.exists(source) or os.path.exists(output):
        raise Exception("Invalid file.")
    if not isinstance(duration, Collection) and all(isinstance(time, timedelta) for time in duration):
        raise Exception("Not an iterable")

    source = source.replace("\\", "/")
    output = output.replace("\\", "/")

    cmd = ['ffmpeg', '-i', source, '-ss', f'{duration[0]}', '-to', f'{duration[1]}', '-c', 'copy', output]
    logging.info(f"Running following command: {' '.join(cmd)}")
    subprocess.call(cmd)


if __name__ == "__main__":
    base_dir = os.path.join(os.getcwd(), "output")
    source_file = os.path.join(base_dir, "The_Lord_of_the_Rings_-_Symphony_Soundtrack_HQ_-_Complete_Album_HQ.mp3")
    output_file = os.path.join(base_dir, "opening.mp3")
    slice_audio(source_file, output_file, [0, 275])
