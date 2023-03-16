# set base image (host OS)
FROM python:3.10-alpine3.17

# set the working directory in the container
WORKDIR /app

RUN apk update && apk add --no-cache build-base=0.5-r3 postgresql15-dev=15.2-r0

# copy the dependencies file to the working directory
COPY requirements.txt .

# install dependencies
RUN pip install --no-cache-dir -r requirements.txt && mkdir -p src abi sql logs rewards
# copy the content of the local src directory to the working directory
COPY src/ /app/src
COPY abi/ /app/abi
COPY sql/ /app/sql

# command to run on container start
CMD [ "python", "./src/main.py"]

