FROM python:3.11-slim

# OCCT (via the cadquery-ocp wheel) needs a few shared libs that aren't in
# the slim base image, and trimesh's STL/GLB export path needs libgl/libgomp.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libgomp1 \
    libxrender1 \
    libxi6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY templates/ templates/
COPY static/ static/

RUN mkdir -p models

ENV PORT=5000
EXPOSE 5000

# ANTHROPIC_API_KEY must be supplied at runtime, e.g.:
#   docker run -e ANTHROPIC_API_KEY=sk-ant-... -p 5000:5000 ai3d-builder
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT} --workers 1 --threads 8 --timeout 180 app:app"]
