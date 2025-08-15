# Start with a base Python image. Using 'slim' keeps the image size small.
FROM python:3.13-slim

# Install system dependencies.
# 'apt-get update' refreshes the package list.
# 'apt-get install -y ffmpeg' installs the FFmpeg suite, which includes ffprobe.
# The '-y' flag automatically confirms the installation.
RUN apt-get update && apt-get install -y ffmpeg

# Set the working directory inside the container.
# All subsequent commands will be run from this directory.
WORKDIR /usr/src/app

# Copy the Python dependency file first to leverage Docker's layer caching.
# This makes subsequent builds faster if only the code changes.
COPY requirements.txt ./

# Install the Python dependencies.
# The '--no-cache-dir' flag and '--upgrade pip' are good practices.
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application source code into the container.
COPY . .

# Expose the port on which your web application listens.
# This should match the port your application is configured to use.
# Common ports are 8000 or 5000. Assuming it runs on 8080.
EXPOSE 8080

# Define the command to run the application when the container starts.
# This is the same command from your Procfile.
CMD ["python", "-m", "WebStreamer"]

