FROM --platform=linux/amd64 ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    software-properties-common \
    build-essential \
    libffi-dev \
    python3-dev \
    git \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y \
    python3.9 \
    python3.9-distutils \
    python3-pip \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip
COPY . /app

WORKDIR /app
RUN pip install -r requirements.txt

CMD ["python3", "llm_play.py"]