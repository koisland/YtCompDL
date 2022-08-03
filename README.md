# YTCompDL, a Youtube Video Segmenter
Command-line program to download and segment Youtube videos automatically.

<img src="docs/vid_chapters.png" width="60%">

---
## Getting Started
---

### Getting a YouTube Data API Key
Follow these [instructions](https://developers.google.com/youtube/v3/getting-started).

Store your API key in a `.env` file in the main working directory.

### Conda
``` shell
conda env create -f env.yaml

conda activate YTCompDL

python main.py -u "https://www.youtube.com/watch?v=gIsHl7swEgk" -o "audio" -x "config_regex.yaml"
```

### Docker
```shell
```
---

## Options
---

```
usage: main.py [-h] -u URL -o OUTPUT_TYPE -x REGEX_CFG [-d DIRECTORY] [-n N_CORES] [-r RESOLUTION] [-m METADATA] [-c] [-t] [-s] [-f FADE] [-ft FADE_TIME]

Command-line program to download and segment Youtube videos.

options:
  -h, --help            show this help message and exit
  -u URL, --url URL     Youtube URL
  -o OUTPUT_TYPE, --output_type OUTPUT_TYPE
                        Desired output (audio/video)
  -x REGEX_CFG, --regex_cfg REGEX_CFG
                        Path to regex config file (.yaml)
  -d DIRECTORY, --directory DIRECTORY
                        Output directory.
  -n N_CORES, --n_cores N_CORES
                        Use n cores to process tracks in parallel.
  -r RESOLUTION, --resolution RESOLUTION
                        Desired resolution (video only)
  -m METADATA, --metadata METADATA
                        Path to optional metadata (.json)
  -c, --comment         Select comment.
  -t, --timestamps      Save timestamps as .txt file.
  -s, --slice           Slice output.
  -f FADE, --fade FADE  Fade (in/out/both/none)
  -ft FADE_TIME, --fade_time FADE_TIME
                        Fade time in seconds.
```

### Regular Expressions

To set your own regular expressions to search for in video comments/descriptions, modify `config/config_regex.yaml`.

*config/config_regex.yaml*
```yaml
ignored_spacers: # Optional
  - "―"
  - "―"
  - "-"
  - "\\s"
  - "["
  - "]"

time: "\\d{1,2}:?\\d*:\\d{2}" # Optional

# Required
start_timestamp: "(.*?)(?:{ignored_spacers})*({time})(?:{ignored_spacers})*(.*)"
duration_timestamp: "(.*?)(?:{ignored_spacers})*({time})(?:{ignored_spacers})*({time})(?:{ignored_spacers})*(.*)"
```

For some examples, check these patterns below:
* `Start` Timestamps
* `Duration` Timestamps


### Workflow
---

* Query YouTube's Data API for selected video.
* Search description and comments for timestamps ranked by similarity to video duration.
* Parse timestamps with regular expresions.
* Download video and/or audio streams from Youtube.
* Process streams.
    * Merge or convert streams.
    * Slice by found timestamps.
    * Apply file metadata.
    * Add audio and/or video fade.
* Cleanup
    * Remove intermediate outputs.

### TO-DO:
---

* [ ] **Testing**
  * Add more unittests.
* [ ] **Dockerfile**
  * Write up a dockerfile to handle installation.
