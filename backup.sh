#!/bin/sh
# Daglig backup av Postgres

BACKUP_DIR="/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/scraper_$TIMESTAMP.sql.gz"
RETENTION_DAYS=30

echo "[$(date)] Starting backup..."

PGPASSWORD=$(cat /run/secrets/postgres_password) pg_dump \
    -h postgres \
    -U scraper \
    -d scraper \
    | gzip > "$BACKUP_FILE"

if [ $? -eq 0 ]; then
    echo "[$(date)] Backup successful: $BACKUP_FILE"
    
    # Rensa gamla backups
    find "$BACKUP_DIR" -name "scraper_*.sql.gz" -mtime +$RETENTION_DAYS -delete
    echo "[$(date)] Cleaned up backups older than $RETENTION_DAYS days"
else
    echo "[$(date)] Backup failed!"
    exit 1
fi
