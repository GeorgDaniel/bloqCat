# Use the official Python image as the base image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Copy the pyproject.toml and poetry.lock files to the container
COPY pyproject.toml poetry.lock README.md /app/
COPY bloqcat /app/bloqcat

ENV PATH="/root/.local/bin:${PATH}"

# Install poetry and project dependencies
RUN python3 -m pip install --user pipx && \
    python3 -m pipx ensurepath && \
    pipx install poetry && \
    poetry config virtualenvs.create false && \
    poetry install --no-interaction --no-ansi

# Copy the rest of the application code to the container
COPY . /app/

# Expose the port that the Flask app will run on
EXPOSE 5000

# Set environment variables for Flask
ENV FLASK_APP=bloqcat
ENV FLASK_RUN_HOST=0.0.0.0

# Specify the command to run when the container starts
CMD ["poetry", "run", "flask", "run"]
