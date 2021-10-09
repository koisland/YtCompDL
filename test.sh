#!/usr/bin/env bash

source venv/Scripts/activate

# hollow knight
url="https://www.youtube.com/watch?v=0HbnqjGirFg&list=PLJzDTt583BOY28Y996pdRqepIHdysjfiz"

python main.py -u "${url}" -o "audio"
