FROM python:3.9.20-slim-bullseye

RUN git clone git@github.com:gahoo/Summarizer.git && \
    cd Summarizer && \
    pip install https://github.com/opendatalab/magic-html/releases/download/magic_html-0.1.2-released/magic_html-0.1.2-py3-none-any.whl -r requirements.txt

RUN pip install pyuwsgi
