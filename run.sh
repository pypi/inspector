docker build . -t inspector
docker run -e PORT=8080 -p 80:8080 -it inspector
