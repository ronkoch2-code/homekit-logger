# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

HomeKit Logger is a Flask-based Python server that receives HomeKit sensor data via POST requests from iOS Shortcuts and stores it in a local SQLite database. It replaces a Google Sheets-based approach for logging home automation data.

## Commands

```bash
# Install dependencies
pip install flask

# Run the server (HTTP on port 5000)
python homekit_logger.py

# Run with HTTPS (requires pyopenssl)
pip install pyopenssl
python homekit_logger.py --https

# Run on custom port
python homekit_logger.py --port 8080

# Test the log endpoint
curl -X POST http://localhost:5000/log \
     -F 'outside_temp=18.5' -F 'outside_humidity=65'

# Query the database directly
sqlite3 homekit_data.db "SELECT * FROM readings ORDER BY timestamp DESC LIMIT 10;"
```

## Architecture

Single-file Flask application (`homekit_logger.py`) with:

- **SENSORS config** (lines 35-43): List of sensor definitions with `field`, `name`, and `unit`. The `field` value is used as the form field name in POST requests and as the SQLite column name.
- **SQLite storage**: Database columns are dynamically created from SENSORS config. All sensor values stored as REAL (float).
- **parse_measurement()**: Strips unit suffixes from values (e.g., "18.4 °C" → 18.4).

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Web dashboard |
| `/log` | POST | Submit sensor readings (form or JSON) |
| `/readings` | GET | Recent readings as JSON (?limit=N) |
| `/readings/csv` | GET | Export all data as CSV |
| `/health` | GET | Health check |

### macOS Background Service

`com.homekit.logger.plist` is a launchd configuration. To use:
1. Edit paths (YOUR_USERNAME placeholders)
2. Copy to `~/Library/LaunchAgents/`
3. Load: `launchctl load ~/Library/LaunchAgents/com.homekit.logger.plist`

## Adding New Sensors

Add entries to the SENSORS list in `homekit_logger.py`. The database schema updates automatically on restart (new columns added via CREATE TABLE IF NOT EXISTS).
