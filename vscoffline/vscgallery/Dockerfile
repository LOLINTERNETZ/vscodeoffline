FROM python:3.7-alpine

COPY ./vscoffline/ /opt/vscoffline

RUN mkdir /artifacts/

RUN pip install --no-cache-dir -r /opt/vscoffline/vscgallery/requirements.txt

ENV ARTIFACTS=/artifacts
ENV BIND=0.0.0.0:443
ENV TIMEOUT=180

CMD gunicorn  --bind $BIND --chdir /opt/vscoffline/ \
    --certfile=/opt/vscoffline/vscgallery/ssl/vscoffline.crt --keyfile=/opt//vscoffline/vscgallery/ssl/vscoffline.key \
    --access-logfile - --reload --timeout $TIMEOUT \
    server:application