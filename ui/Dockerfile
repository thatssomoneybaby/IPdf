FROM python:3.11-slim

WORKDIR /ui

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt /ui/requirements.txt
RUN pip install --no-cache-dir -r /ui/requirements.txt

COPY . /ui

EXPOSE 8501

ENV BACKEND_URL=http://api:8000

CMD ["streamlit", "run", "streamlit_app.py", "--server.address=0.0.0.0", "--server.port=8501"]
