build:
	pip install -r vscoffline/vscsync/requirements.txt
	pip install -r vscoffline/vscgallery/requirements.txt

docker:
	docker-compose build

podman:
	podman-compose build

run:
	docker-compose up --build -d
git 