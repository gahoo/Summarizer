FROM python:3.9.20-slim-bookworm

RUN apt update && \
    apt install -y libmagic-dev unzip wget && \
    wget https://github.com/gahoo/Summarizer/archive/refs/heads/master.zip && \
    unzip master && \
    rm master.zip && \
    mv Summarizer-master Summarizer && \
    cd Summarizer && \
    mv tokens.py.example tokens.py && \
    pip install https://github.com/opendatalab/magic-html/releases/download/magic_html-0.1.2-released/magic_html-0.1.2-py3-none-any.whl -r requirements.txt && \
    sed '278s#www.youtube.com#siteproxy.42bio.info/fxxkgfw/https/www.youtube.com#g' /usr/local/lib/python3.9/site-packages/yt_dlp/extractor/youtube.py -i

RUN pip install pyuwsgi
RUN useradd summarizer

USER summarizer

WORKDIR /Summarizer

ENV PORT 5000
ENV WORKERS 4

CMD uwsgi --http :${PORT} --master -p ${WORKERS} -w app:app