# YTCompDL, a Youtube Video Segmenter

---
Command-line program to download and segment Youtube videos automatically.

![](docs/vid_chapters.png)

### Usage

---
``` shell
# Check that ffmpeg is installed.
ffmpeg --version

# install requirements.
pip install -r requirements.txt

# Run script
python main.py -u url -o output 
```

### Options

---
* Required:
  * url (-u)
  * output (-o)
    * "audio" or "video". 
* Optional:
    * resolution (-r)
      * Desired output resolution for video output. Check [config.py](ytcompdl/config.py)
    * metadata (-m)
      * Path to json file with file metadata. Check [config.py](ytcompdl/config.py)
      * ``` python
        # Default
        {'album': self.snippets['title'], 
        'artist': self.channel,
        'year': self.year_uploaded}
        ```
    * comment (-c)
      * Allow comment selection.
    * timestamps (-t)
      * Save timestamps as text file.
    * slice (-s)
      * Slice output by timestamps.
    * fade (-f)
      * Fade "in", "out", "both", or "none".
    * fade_time (-ft) 
      * Time to fade in seconds.

### Workflow

---
* Find timestamps in video description or comments.
* Download video and/or audio streams from Youtube.
* Process streams. 
    * Merge or convert streams.
    * Slice by timestamps found.
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
* [ ] **File Extension**
  * Pretty unlikely since time-consuming.