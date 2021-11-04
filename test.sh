#!/usr/bin/env bash

source venv/Scripts/activate

# hollow knight
url="https://www.youtube.com/watch?v=upIDgvEJrlg"

python main.py -u "${url}" -o "audio"
