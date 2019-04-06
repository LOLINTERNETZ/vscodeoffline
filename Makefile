build:
    pip install -r vscsync/requirements.txt
    pip install -r vscgallery/requirements.txt

docker:
    docker-compose build

run:
    docker-compose up --build -d