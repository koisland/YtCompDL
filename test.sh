#!/usr/bin/env bash

source venv/Scripts/activate

url="https://www.youtube.com/watch?v=80OvNaEgmmw"

python main.py -u "${url}" -o "video"
