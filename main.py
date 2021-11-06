import asyncio
import argparse
from ytcompdl.yt_comp_dl import YTCompDL

"""
command-line version
"""

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Command-line program to download and segment Youtube videos.")

    # Required arguments.
    ap.add_argument("-u", "--url", required=True, help="Youtube URL")
    ap.add_argument("-o", "--output", required=True, help="Desired output (audio/video)")

    # Optional arguments.
    ap.add_argument("-r", "--resolution", help="Desired resolution (video only)", default="720p")
    ap.add_argument("-m", "--metadata", help="Path to optional metadata (.json)", default=None)
    ap.add_argument("-c", "--comment", help="Select comment.", default=False, action="store_true")
    ap.add_argument("-t", "--timestamps", help="Save timestamps as .txt file.", default=False, action="store_true")
    ap.add_argument("-s", "--slice", help="Slice output.", default=True, action="store_false")
    ap.add_argument("-f", "--fade", help="Fade (in/out/both/none)", default="both")
    ap.add_argument("-ft", "--fade_time", help="Fade time in seconds.", default=0.5)

    # dl arguments.
    args = vars(ap.parse_args())
    dl = YTCompDL(*args.values())
    # print(dl.timestamps)
    asyncio.run(dl.download())
