FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        ca-certificates \
        curl \
        openjdk-17-jdk-headless \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g tsx@4 typescript \
    && rm -rf /var/lib/apt/lists/*

ENV SANDBOX_OUTPUT_LIMIT=65536

RUN useradd -r -u 10001 -d /nonexistent -s /usr/sbin/nologin sandbox

COPY runner_entry.py /app/runner_entry.py
WORKDIR /app
RUN chown sandbox:sandbox /app/runner_entry.py

USER sandbox

ENTRYPOINT ["python3", "/app/runner_entry.py"]
