"""Gunicorn configuration."""
import multiprocessing

bind = "127.0.0.1:8000"
workers = min(multiprocessing.cpu_count() * 2 + 1, 8)
worker_class = "gthread"
threads = 2
timeout = 120
keepalive = 5
max_requests = 1000
max_requests_jitter = 50
accesslog = "-"
errorlog = "-"
loglevel = "info"
