FROM python:3.11-slim-buster

RUN apt update && apt install -y ffmpeg

# https://pythonspeed.com/articles/activate-virtualenv-dockerfile/
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

WORKDIR /ytcompdl

# Install dependencies:
COPY envs/requirements.txt .
RUN pip install -r requirements.txt

# Set entrypoint.
ENTRYPOINT [ "ytcompdl" ]
