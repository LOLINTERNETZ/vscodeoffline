FROM python:3.12-alpine
ARG USER=vscsync
ARG ARTIFACTS=/artifacts

WORKDIR /opt/vscoffline
COPY ./vscoffline/ ./

RUN adduser -Dh /opt/vscoffline ${USER} &&\
    mkdir ${ARTIFACTS} &&\
    ln -s ${ARTIFACTS} ${ARTIFACTS/\//} &&\
    chown -R ${USER}:${USER} ${ARTIFACTS} ../
USER vscsync

RUN ls -al * &&\
    pip install --no-cache-dir -r vscsync/requirements.txt

ENV ARTIFACTS=${ARTIFACTS}
ENV SYNCARGS=--sync

ENTRYPOINT [ "python3", "sync.py" ]
CMD [ "--artifacts", "$ARTIFACTS", "$SYNCARGS" ]
