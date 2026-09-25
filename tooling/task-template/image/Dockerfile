FROM ghcr.io/agentslastexam/container-ubuntu22-base:latest
USER root
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright
COPY install_python.py wheels.json /opt/task-build/
RUN python3 /opt/task-build/install_python.py
RUN python3 -m playwright install --with-deps chromium \
    && chmod -R a+rX /opt/playwright \
    && install -d -o user -g user /home/user/output
RUN apt-get install -y --no-install-recommends openbox \
    && rm -rf /var/lib/apt/lists/*
