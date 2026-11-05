# Build the React frontend in a separate stage so Node and its dependencies are
# not included in the smaller Python runtime image.
FROM node:22-alpine AS frontend-build

# Use a dedicated working directory for the frontend build.
WORKDIR /app/frontend
# Copy dependency manifests first so Docker can cache npm ci when only source changes.
COPY frontend/package.json frontend/package-lock.json ./
# Install the exact frontend dependencies recorded in the lockfile.
RUN npm ci
# Copy the frontend source and build it into static files in /app/frontend/dist.
COPY frontend/ ./
RUN npm run build

# Start the production image from a slim Python base image.
FROM python:3.12-slim AS runtime

# Avoid writing Python bytecode, flush logs promptly, and default the web port.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

# Keep application files under /app.
WORKDIR /app

# Install the runtime system library, clean package metadata, create an
# unprivileged app user, and make the data directory writable by that user.
RUN apt-get update \
    && apt-get install --no-install-recommends -y libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system app \
    && useradd --system --gid app --home-dir /app app \
    && mkdir -p /app/data \
    && chown app:app /app/data

# Copy and install Python dependencies separately to improve build caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Add the backend configuration and source code to the runtime image.
COPY config.yaml ./
COPY src/ ./src/
# Copy the already-built React static files from the frontend build stage.
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

# Run the application without root privileges.
USER app

# Document the listening port, declare the container data mount point, and
# periodically check that the API health endpoint responds. VOLUME does not
# create or attach an AWS EBS volume; storage must be mounted by the runtime.
EXPOSE 8000
VOLUME ["/app/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '8000') + '/api/health', timeout=3)"

# Start Uvicorn, serving the FastAPI backend and the built frontend on all
# container interfaces, using PORT or the default port 8000.
CMD ["sh", "-c", "uvicorn src.web_app.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
