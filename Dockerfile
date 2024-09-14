FROM python:3.9.20-slim-bookworm

RUN apt update && \
    apt install -y libmagic-dev unzip wget && \
    wget https://github.com/gahoo/Summarizer/archive/refs/heads/master.zip && \
    unzip master && \
    rm master.zip && \
    mv Summarizer-master Summarizer && \
    cd Summarizer && \
    pip install https://github.com/opendatalab/magic-html/releases/download/magic_html-0.1.2-released/magic_html-0.1.2-py3-none-any.whl -r requirements.txt

RUN pip install pyuwsgi
RUN useradd summarizer

USER summarizer

WORKDIR /Summarizer

ENV PORT 8000
ENV HOST 0.0.0.0

CMD uwsgi --http ${HOST}:${PORT} --master -p 4 -w app