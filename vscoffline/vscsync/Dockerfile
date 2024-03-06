FROM python:3.12.2-alpine
WORKDIR /opt/vscoffline

COPY ./vscoffline/ ./

RUN mkdir /artifacts/

RUN pip install --no-cache-dir -r vscsync/requirements.txt

ENV ARTIFACTS=/artifacts
ENV SYNCARGS=--sync

CMD python3 sync.py --artifacts $ARTIFACTS $SYNCARGS
