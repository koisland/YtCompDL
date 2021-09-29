import asyncio
import argparse
from ytcompdl.yt_comp_dl import YTCompDL

"""
command-line version
"""

if __name__ == "__main__":
    ap = argparse.ArgumentParser()

    # Required arguments.
    ap.add_argument("-u", "--url", required=True, help="Youtube URL")
    ap.add_argument("-o", "--output", required=True, help="Desired output (audio/video)")

    # Optional arguments.
    ap.add_argument("-r", "--res", help="Desired resolution (video only)")
    ap.add_argument("-om", "--opt_metadata", help="Path to optional metadata (.json)")
    ap.add_argument("-cc", "--choose_comment", help="Select comment.")
    ap.add_argument("-st", "--save_timestamps", help="Save timestamps as .txt file.")

    args = vars(ap.parse_args())
    dl = YTCompDL(*args.values())
    # print(dl.timestamps)
    asyncio.run(dl.download())
