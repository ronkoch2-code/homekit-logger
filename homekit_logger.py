#!/usr/bin/env python3
"""
HomeKit Data Logger - SQLite Edition
=====================================

A simple Flask server that receives HomeKit sensor data via POST requests
and stores it in a local SQLite database.

This replaces the Google Sheets approach from:
https://blog.claude.nl/posts/logging-homekit-data-to-google-sheets-for-free--walkthrough/

Usage:
    1. Install dependencies: pip install flask flask-limiter
    2. Edit the SENSORS list below to match your HomeKit sensors
    3. Optionally set HOMEKIT_API_KEY environment variable for authentication
    4. Run: python homekit_logger.py
    5. Update your iOS Shortcut to POST to http://<your-mac-ip>:5000/log

For HTTPS (required by HomeKit hubs in some cases):
    pip install pyopenssl
    Run with: python homekit_logger.py --https
"""

import argparse
import logging
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Generator, Optional

from flask import Flask, Response, jsonify, render_template_string, request

# =============================================================================
# CONFIGURATION - Edit these to match your HomeKit sensors
# =============================================================================

# Define your sensors here. The 'field' is what you'll use in the iOS Shortcut
# as the form field name (like Google's entry.XXXXX but simpler)
SENSORS = [
    # Outside
    {"field": "outside_temp", "name": "Outside Temperature", "unit": "°C"},
    {"field": "outside_humidity", "name": "Outside Humidity", "unit": "%"},
    # Master Bedroom
    {
        "field": "master_bedroom_temp",
        "name": "Master Bedroom Temperature",
        "unit": "°C",
    },
    {
        "field": "master_bedroom_humidity",
        "name": "Master Bedroom Humidity",
        "unit": "%",
    },
    # Library
    {"field": "library_temp", "name": "Library Temperature", "unit": "°C"},
    {"field": "library_humidity", "name": "Library Humidity", "unit": "%"},
    # Kitchen
    {"field": "kitchen_temp", "name": "Kitchen Temperature", "unit": "°C"},
    {"field": "kitchen_humidity", "name": "Kitchen Humidity", "unit": "%"},
    # Living Room
    {"field": "living_room_temp", "name": "Living Room Temperature", "unit": "°C"},
    {"field": "living_room_humidity", "name": "Living Room Humidity", "unit": "%"},
    # Other
    {"field": "co2_level", "name": "CO2 Level", "unit": "ppm"},
]

# Configuration from environment variables with defaults
DATABASE_PATH = os.getenv("HOMEKIT_DB_PATH", "homekit_data.db")
HOST = os.getenv("HOMEKIT_HOST", "0.0.0.0")  # nosec B104 - intentional for LAN access
PORT = int(os.getenv("HOMEKIT_PORT", "5000"))
API_KEY = os.getenv("HOMEKIT_API_KEY")  # Optional: set for authentication

# Limits
MAX_READINGS_LIMIT = 10000
MAX_REQUEST_SIZE = 1024 * 10  # 10KB max request body

# Regex pattern for valid sensor field names (compiled once at module level)
VALID_FIELD_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
MEASUREMENT_PATTERN = re.compile(r"^([-+]?\d*\.?\d+)")

# =============================================================================
# Logging Setup
# =============================================================================

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# =============================================================================
# Application Code
# =============================================================================

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_REQUEST_SIZE

# Rate limiting (optional - only if flask-limiter is installed)
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address

    limiter = Limiter(
        key_func=get_remote_address,
        app=app,
        default_limits=["200 per minute"],
        storage_uri="memory://",
    )
    RATE_LIMITING_ENABLED = True
    logger.info("Rate limiting enabled")
except ImportError:
    RATE_LIMITING_ENABLED = False
    logger.warning(
        "flask-limiter not installed, rate limiting disabled. Install with: pip install flask-limiter"
    )

    # Create a no-op decorator
    class NoOpLimiter:
        def limit(self, *args, **kwargs):
            def decorator(f):
                return f

            return decorator

    limiter = NoOpLimiter()


def validate_sensors_config() -> None:
    """Validate that all sensor field names are safe SQL identifiers."""
    seen_fields = set()
    for sensor in SENSORS:
        field = sensor.get("field", "")
        if not VALID_FIELD_PATTERN.match(field):
            raise ValueError(
                f"Invalid sensor field name: '{field}'. "
                "Field names must start with a letter and contain only lowercase letters, numbers, and underscores."
            )
        if field in seen_fields:
            raise ValueError(f"Duplicate sensor field name: '{field}'")
        seen_fields.add(field)
    logger.info("Sensor configuration validated", extra={"sensors": list(seen_fields)})


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """Get database connection with row factory for dict-like access."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    """Initialize the database with the readings table and migrate schema if needed."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()

            # Check if table exists
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='readings'"
            )
            table_exists = cursor.fetchone() is not None

            if not table_exists:
                # Create new table with all sensor columns
                columns = ", ".join([f'"{s["field"]}" REAL' for s in SENSORS])
                cursor.execute(
                    f"""
                    CREATE TABLE readings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        {columns}
                    )
                """
                )
                logger.info("Created new readings table")
            else:
                # Migrate: add any missing columns for new sensors
                cursor.execute("PRAGMA table_info(readings)")
                existing_columns = {row[1] for row in cursor.fetchall()}

                for sensor in SENSORS:
                    field = sensor["field"]
                    if field not in existing_columns:
                        cursor.execute(
                            f'ALTER TABLE readings ADD COLUMN "{field}" REAL'
                        )
                        logger.info(f"Added new column: {field}")

            # Create an index on timestamp for faster queries
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_timestamp ON readings(timestamp)
            """
            )

            conn.commit()

        logger.info(
            "Database initialized",
            extra={
                "database_path": DATABASE_PATH,
                "sensors": [s["field"] for s in SENSORS],
            },
        )
    except sqlite3.Error as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


def parse_measurement(value: Any) -> Optional[float]:
    """
    Parse a measurement value, stripping units if present.

    Args:
        value: The measurement value to parse (can be string or number)

    Returns:
        The numeric value as a float, or None if parsing fails

    Examples:
        >>> parse_measurement("18.4 °C")
        18.4
        >>> parse_measurement("65 %")
        65.0
    """
    if value is None:
        return None

    # Convert to string and strip whitespace
    value_str = str(value).strip()

    if not value_str:
        return None

    # Try to extract just the numeric part
    match = MEASUREMENT_PATTERN.match(value_str)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass

    return None


def check_api_key() -> Optional[tuple]:
    """Check API key if authentication is enabled. Returns error response or None."""
    if API_KEY is None:
        return None

    provided_key = request.headers.get("X-API-Key") or request.args.get("api_key")
    if provided_key != API_KEY:
        logger.warning(
            "Unauthorized access attempt", extra={"remote_addr": request.remote_addr}
        )
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    return None


@app.route("/log", methods=["POST"])
@limiter.limit("30 per minute")
def log_reading():
    """
    Endpoint to receive HomeKit sensor data.
    Accepts form data or JSON with sensor field names as keys.

    Returns:
        JSON response with status, id, and data on success
        JSON error response on failure
    """
    # Check authentication
    auth_error = check_api_key()
    if auth_error:
        return auth_error

    try:
        # Get data from form or JSON
        if request.is_json:
            data = request.json or {}
        else:
            data = request.form.to_dict()

        if not data:
            return jsonify({"status": "error", "message": "No data received"}), 400

        # Parse and validate the data - only accept known sensor fields
        parsed_data = {}
        for sensor in SENSORS:
            field = sensor["field"]
            if field in data:
                parsed_data[field] = parse_measurement(data[field])

        if not parsed_data:
            return (
                jsonify({"status": "error", "message": "No valid sensor data found"}),
                400,
            )

        # Insert into database
        with get_db() as conn:
            cursor = conn.cursor()

            # Fields come from validated SENSORS config, so this is safe
            columns = ", ".join([f'"{k}"' for k in parsed_data.keys()])
            placeholders = ", ".join(["?" for _ in parsed_data])
            values = list(parsed_data.values())

            query = f"INSERT INTO readings ({columns}) VALUES ({placeholders})"  # nosec B608
            cursor.execute(query, values)
            conn.commit()
            reading_id = cursor.lastrowid

        logger.info(
            f"Logged reading #{reading_id}",
            extra={"reading_id": reading_id, "data": parsed_data},
        )

        return jsonify({"status": "success", "id": reading_id, "data": parsed_data})

    except sqlite3.Error as e:
        logger.error(f"Database error in log_reading: {e}")
        return jsonify({"status": "error", "message": "Database error"}), 500
    except Exception as e:
        logger.exception(f"Unexpected error in log_reading: {e}")
        return jsonify({"status": "error", "message": "Internal server error"}), 500


@app.route("/readings", methods=["GET"])
@limiter.limit("100 per minute")
def get_readings():
    """Get recent readings as JSON. Use ?limit=N to control count (max 10000)."""
    auth_error = check_api_key()
    if auth_error:
        return auth_error

    try:
        limit = min(request.args.get("limit", 100, type=int), MAX_READINGS_LIMIT)
        limit = max(1, limit)  # Ensure at least 1

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM readings ORDER BY timestamp DESC LIMIT ?", (limit,)
            )
            rows = cursor.fetchall()

        readings = [dict(row) for row in rows]
        return jsonify(readings)

    except sqlite3.Error as e:
        logger.error(f"Database error in get_readings: {e}")
        return jsonify({"status": "error", "message": "Database error"}), 500


@app.route("/readings/csv", methods=["GET"])
@limiter.limit("10 per minute")
def export_csv():
    """Export all readings as CSV (streamed to prevent memory issues)."""
    auth_error = check_api_key()
    if auth_error:
        return auth_error

    def generate_csv() -> Generator[str, None, None]:
        """Stream CSV data row by row."""
        try:
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM readings ORDER BY timestamp ASC")

                # Get column names from cursor description
                headers = [desc[0] for desc in cursor.description]
                yield ",".join(headers) + "\n"

                # Stream rows in batches
                while True:
                    rows = cursor.fetchmany(1000)
                    if not rows:
                        break
                    for row in rows:
                        yield ",".join(
                            str(val) if val is not None else "" for val in row
                        ) + "\n"
        except sqlite3.Error as e:
            logger.error(f"Database error in export_csv: {e}")
            yield f"Error: {e}\n"

    return Response(
        generate_csv(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=homekit_readings.csv"},
    )


# Simple HTML dashboard
DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>HomeKit Logger Dashboard</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background: #f5f5f7; }
        h1 { color: #1d1d1f; }
        .card { background: white; border-radius: 12px; padding: 20px; margin: 20px 0; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #e0e0e0; }
        th { background: #f5f5f7; font-weight: 600; }
        tr:hover { background: #f9f9f9; }
        .endpoint { background: #e8f5e9; padding: 10px; border-radius: 6px; font-family: monospace; margin: 10px 0; }
        .sensor-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; }
        .sensor-card { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 12px; }
        .sensor-value { font-size: 2em; font-weight: bold; }
        .sensor-name { opacity: 0.9; font-size: 0.9em; }
        .refresh-btn { background: #007aff; color: white; border: none; padding: 10px 20px; border-radius: 8px; cursor: pointer; }
        .refresh-btn:hover { background: #0056b3; }
    </style>
</head>
<body>
    <h1>HomeKit Logger Dashboard</h1>

    <div class="card">
        <h2>Current Readings</h2>
        <button class="refresh-btn" onclick="location.reload()">Refresh</button>
        <div class="sensor-grid" id="current-readings">
            Loading...
        </div>
    </div>

    <div class="card">
        <h2>API Endpoints</h2>
        <div class="endpoint">POST /log - Submit new readings</div>
        <div class="endpoint">GET /readings - Get recent readings (JSON)</div>
        <div class="endpoint">GET /readings/csv - Export all data as CSV</div>
    </div>

    <div class="card">
        <h2>Recent Readings</h2>
        <table id="readings-table">
            <thead><tr><th>Loading...</th></tr></thead>
            <tbody></tbody>
        </table>
    </div>

    <script>
        fetch('/readings?limit=50')
            .then(r => r.json())
            .then(data => {
                // Update current readings
                if (data.length > 0) {
                    const latest = data[0];
                    const sensors = Object.keys(latest).filter(k => k !== 'id' && k !== 'timestamp');
                    document.getElementById('current-readings').innerHTML = sensors.map(s => {
                        const val = latest[s];
                        return `<div class="sensor-card">
                            <div class="sensor-name">${s.replace(/_/g, ' ')}</div>
                            <div class="sensor-value">${val !== null ? val : '—'}</div>
                        </div>`;
                    }).join('');
                }

                // Update table
                const table = document.getElementById('readings-table');
                if (data.length > 0) {
                    const headers = Object.keys(data[0]);
                    table.innerHTML = `
                        <thead><tr>${headers.map(h => `<th>${h}</th>`).join('')}</tr></thead>
                        <tbody>${data.map(row =>
                            `<tr>${headers.map(h => `<td>${row[h] !== null ? row[h] : ''}</td>`).join('')}</tr>`
                        ).join('')}</tbody>
                    `;
                }
            });
    </script>
</body>
</html>
"""


@app.route("/")
def dashboard():
    """Simple web dashboard to view the data."""
    return render_template_string(DASHBOARD_HTML)


@app.route("/health")
def health():
    """Health check endpoint that also verifies database connectivity."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM readings")
            count = cursor.fetchone()[0]

        return jsonify(
            {
                "status": "ok",
                "timestamp": datetime.now().isoformat(),
                "readings_count": count,
                "rate_limiting": RATE_LIMITING_ENABLED,
                "authentication": API_KEY is not None,
            }
        )
    except sqlite3.Error as e:
        logger.error(f"Health check failed: {e}")
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Database connection failed",
                    "timestamp": datetime.now().isoformat(),
                }
            ),
            503,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="HomeKit Data Logger Server")
    parser.add_argument(
        "--https", action="store_true", help="Enable HTTPS with self-signed certificate"
    )
    parser.add_argument(
        "--port", type=int, default=PORT, help=f"Port to listen on (default: {PORT})"
    )
    args = parser.parse_args()

    # Validate configuration before starting
    validate_sensors_config()
    init_db()

    logger.info("=" * 60)
    logger.info("HomeKit Logger Server")
    logger.info("=" * 60)
    logger.info(f"Dashboard: http://localhost:{args.port}/")
    logger.info(f"Log endpoint: http://<your-ip>:{args.port}/log")
    logger.info(f"Configured sensors: {[s['field'] for s in SENSORS]}")
    logger.info(f"Rate limiting: {'enabled' if RATE_LIMITING_ENABLED else 'disabled'}")
    logger.info(f"Authentication: {'enabled' if API_KEY else 'disabled'}")
    logger.info("")
    logger.info("Example curl test:")
    logger.info(f"  curl -X POST http://localhost:{args.port}/log \\")
    logger.info("       -F 'outside_temp=18.5' -F 'outside_humidity=65'")
    logger.info("=" * 60)

    if args.https:
        logger.info("Starting with HTTPS (self-signed certificate)...")
        app.run(host=HOST, port=args.port, ssl_context="adhoc", debug=False)
    else:
        app.run(host=HOST, port=args.port, debug=False)


if __name__ == "__main__":
    main()
