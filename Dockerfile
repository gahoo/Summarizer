FROM python:3.14.0-slim-bookworm as builder

RUN apt update && \
    apt install -y zlib1g-dev libxml2-dev libxslt1-dev build-essential
RUN pip install https://github.com/opendatalab/magic-html/releases/download/magic_html-0.1.6-released/magic_html-0.1.6-py3-none-any.whl
RUN pip install pyuwsgi

FROM python:3.14.0-slim-bookworm

RUN apt update && \
    apt install -y unzip wget xz-utils libxml2 zlib1g libxslt1.1 libmagic-dev curl

RUN wget https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz && \
    tar -xf ffmpeg-release-arm64-static.tar.xz && \
    cp ffmpeg-7.0.2-arm64-static/ffmpeg /usr/local/bin/ && \
    rm -r ffmpeg-release-arm64-static.tar.xz ffmpeg-7.0.2-arm64-static/

RUN curl -fsSL https://bun.com/install | bash

COPY --from=builder /usr/local/lib/python3.14/site-packages/ \
                    /usr/local/lib/python3.14/site-packages/

COPY --from=builder /usr/local/bin/ \
                    /usr/local/bin/

RUN wget https://github.com/gahoo/Summarizer/archive/refs/heads/master.zip && \
    unzip master && \
    rm master.zip && \
    mv Summarizer-master Summarizer && \
    cd Summarizer && \
    mv tokens.py.example tokens.py && \
    mkdir db && \
    pip install -r requirements.txt && \
    chown -R 1000:1000 /Summarizer

RUN useradd summarizer

USER summarizer

WORKDIR /Summarizer

ENV PORT 5000
ENV WORKERS 1
ENV THREADS 4
ENV BUFFER_SIZE 32768

CMD uwsgi --http :${PORT} --master -p ${WORKERS} --threads ${THREADS} -b ${BUFFER_SIZE} -w app:app
