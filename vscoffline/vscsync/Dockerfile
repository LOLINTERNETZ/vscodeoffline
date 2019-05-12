FROM python:3.7-alpine

COPY ./vscoffline/ /opt/vscoffline

RUN mkdir /artifacts/

RUN pip install --no-cache-dir -r /opt/vscoffline/vscsync/requirements.txt

ENV ARTIFACTS=/artifacts
ENV SYNCARGS=--sync

CMD python3 /opt/vscoffline/sync.py --artifacts $ARTIFACTS $SYNCARGS

