# set base image (host OS)
FROM python:3.10.10

# set the working directory in the container
WORKDIR /app

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

