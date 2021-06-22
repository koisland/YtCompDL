import os
import logging
from app import app
from flask import request, jsonify
from zipfile import ZipFile

from ytcompdl.pytube_dl import Pytube_Dl
from ytcompdl.yt_comp_dl import YTCompDL

# TODO: Add choose timestamp functionality after everything else is working.

logger = logging.getLogger()
logger.setLevel(logging.INFO)


@app.route("/api/dl")
def download():
    url = request.json.get('url')
    output = request.json.get('output')
    res = request.json.get('res')

    # # Zip file and return.
    # with ZipFile("sample.zip", "w") as zip_obj:
    #     zip_obj.write("")

    return "hey"
