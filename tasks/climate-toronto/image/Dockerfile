FROM ghcr.io/agentslastexam/container-ubuntu22-base:latest
USER root
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright
RUN python3 -m pip install --no-cache-dir playwright==1.63.0 \
    && python3 -m playwright install --with-deps chromium \
    && chmod -R a+rX /opt/playwright \
    && install -d -o user -g user /home/user/output
