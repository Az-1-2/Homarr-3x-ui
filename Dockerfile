FROM python:alpine
WORKDIR /app
RUN pip install --no-cache-dir flask psutil requests 
COPY app.py /app/app.py
ENV PORT=3000
CMD ["python", "/app/app.py"]
