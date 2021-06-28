FROM python:3.9-slim AS compile-image

# Enable venv
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Runtime image
FROM python:3.9-slim AS build-image
COPY --from=compile-image /opt/venv /opt/venv

RUN mkdir -p /usr/predictions-bot
WORKDIR /usr/predictions-bot

# Enable venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application
COPY ./src ./src
COPY ./main.py ./main.py
COPY ./db_init.py ./db_init.py
COPY ./config.py ./config.py

# Run application
CMD ["/bin/bash", "-c", "aerich upgrade && python3 main.py"]
