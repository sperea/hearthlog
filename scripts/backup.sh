#!/bin/bash
set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${PROJECT_DIR}/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/blog-backup-${TIMESTAMP}.tar.gz"

mkdir -p "$BACKUP_DIR"

tar -czf "$BACKUP_FILE" \
  -C "$PROJECT_DIR" \
  blog-content/content \
  blog-content/static/images \
  blog-content/config.toml

echo "Backup: $BACKUP_FILE"

# Mantener solo los últimos 30 backups
ls -t "${BACKUP_DIR}"/blog-backup-*.tar.gz | tail -n +31 | xargs -r rm --
