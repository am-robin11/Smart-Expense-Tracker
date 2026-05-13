# Use official Python slim image
FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Copy requirements first (better Docker layer caching)
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the project
COPY . .

# Expose the port Railway will use
EXPOSE 8000

# Run with gunicorn (production server)
CMD ["gunicorn", "run:app", "--bind", "0.0.0.0:8000", "--workers", "2"]
