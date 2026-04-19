#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

if [ ! -f ".env" ]; then
  echo "ERROR: .env no encontrado. Copia .env.example y edita los valores."
  exit 1
fi

source .env

if [ -z "$BLOG_PASSWORD" ] || [ "$BLOG_PASSWORD" = "cambia-esta-password-2026" ]; then
  echo "ERROR: Cambia BLOG_PASSWORD en .env antes de desplegar."
  exit 1
fi

if [ -z "$AI_BOT_API_TOKEN" ] || [ "$AI_BOT_API_TOKEN" = "cambia-este-token-secreto-bot" ]; then
  echo "ERROR: Cambia AI_BOT_API_TOKEN en .env antes de desplegar."
  exit 1
fi

echo "→ Generando auth.htpasswd..."
docker compose run --rm htpasswd-gen

echo "→ Construyendo imagen API..."
docker compose build api-bot

echo "→ Iniciando servicios..."
docker compose up -d blog api-bot

echo "→ Esperando que levanten..."
sleep 5

echo ""
echo "✓ Blog: http://192.168.1.139:8082 (usuario: familia)"
echo "✓ API:  http://192.168.1.139:5000/api/health"
