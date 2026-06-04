FROM python:3.13-slim-bullseye

ENV DEBIAN_FRONTEND=noninteractive

# System dependencies for audio conversion and PDF rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
RUN pip install --no-cache-dir \
    "markitdown[all]" \
    pypdfium2 \
    pypdf \
    dashscope \
    openai \
    requests \
    Pillow

# Copy v3 script + config
COPY scripts/read_everything_v3.py /app/read_everything_v3.py
COPY scripts/read_everything_config.example.json /app/scripts/read_everything_config.example.json
COPY references/ /app/references/

# Mount real config at runtime:
# docker run -v ./scripts/read_everything_config.json:/app/scripts/read_everything_config.json ...

VOLUME ["/data"]
WORKDIR /data

ENTRYPOINT ["python3", "/app/read_everything_v3.py"]
