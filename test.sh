#!/usr/bin/env bash

source venv/Scripts/activate

url="https://www.youtube.com/watch?v=DyY9Wpfajqo"

python main.py -u "${url}" -o "video" -c -t -f "both"
