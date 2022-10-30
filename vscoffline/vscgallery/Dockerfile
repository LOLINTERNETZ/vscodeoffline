FROM python:3.7-alpine

# For gunicorn > 20.0.0
RUN apk --no-cache add libc-dev binutils

COPY ./vscoffline/ /opt/vscoffline

RUN mkdir /artifacts/

RUN pip install --no-cache-dir -r /opt/vscoffline/vscgallery/requirements.txt

ENV ARTIFACTS=/artifacts
ENV BIND=0.0.0.0:443
ENV TIMEOUT=180
ENV THREADS=4
ENV SSLARGS="--certfile=/opt/vscoffline/vscgallery/ssl/vscoffline.crt --keyfile=/opt/vscoffline/vscgallery/ssl/vscoffline.key"

CMD gunicorn  --bind $BIND --chdir /opt/vscoffline/ $SSLARGS \
    --access-logfile - --reload --timeout $TIMEOUT --threads $THREADS \
    server:application
