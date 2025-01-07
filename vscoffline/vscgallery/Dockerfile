FROM python:3.12-alpine
ARG USER=vscgallery
ARG ARTIFACTS=/artifacts

# For gunicorn > 20.0.0
RUN apk --no-cache add libc-dev binutils

WORKDIR /opt/vscoffline
COPY ./vscoffline/ ./

RUN adduser -Dh /opt/vscoffline ${USER} &&\
    mkdir ${ARTIFACTS} &&\
    ln -s ${ARTIFACTS} ${ARTIFACTS/\//} &&\
    chown -R ${USER}:${USER} ${ARTIFACTS} ../
USER ${USER}

RUN PATH=/opt/vscoffline/.local/bin:$PATH \
    pip install --no-cache-dir -r vscgallery/requirements.txt

ENV ARTIFACTS=${ARTIFACTS}
ENV BIND=0.0.0.0:9443
ENV TIMEOUT=180
ENV THREADS=4
ENV SSLARGS="--certfile=/opt/vscoffline/vscgallery/ssl/vscoffline.crt --keyfile=/opt/vscoffline/vscgallery/ssl/vscoffline.key"
ENV PATH=/opt/vscoffline/.local/bin:$PATH

CMD gunicorn  \
    $SSLARGS \
    --reload \
    --bind $BIND \
    --access-logfile - \
    --timeout $TIMEOUT \
    --threads $THREADS \
    server:application
