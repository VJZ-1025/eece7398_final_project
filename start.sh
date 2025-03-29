#!/bin/bash
set -e

echo "Waiting for Elasticsearch to be available at http://es:9200..."

until curl -s http://es:9200 >/dev/null; do
  sleep 1
done

echo "Elasticsearch is up!"

# 启动 uvicorn
exec uvicorn app:app --host 0.0.0.0 --port 8000 --reload