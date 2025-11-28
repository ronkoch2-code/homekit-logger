# HomeKit Logger

A Flask server that receives HomeKit sensor data via POST requests and stores it in a local SQLite database. A privacy-focused alternative to cloud-based logging solutions.

## Features

- **Local storage** - Data stays on your network, no cloud dependency
- **Rate limiting** - Protection against abuse (via flask-limiter)
- **Optional authentication** - API key support for secure access
- **Web dashboard** - View current and historical readings
- **Multiple export formats** - JSON API and CSV export
- **Automatic unit parsing** - Handles values like "18.4 °C" or "65%"

## Quick Start

```bash
# Install dependencies
pip install flask flask-limiter

# Run the server (use port 5050 on macOS to avoid AirPlay conflict)
python3 homekit_logger.py --port 5050

# Test it
curl -X POST http://localhost:5050/log \
     -F 'outside_temp=18.5' -F 'outside_humidity=65'

# View dashboard
open http://localhost:5050/
```

## Configuration

Edit the `SENSORS` list in `homekit_logger.py` to match your HomeKit devices:

```python
SENSORS = [
    {"field": "outside_temp", "name": "Outside Temperature", "unit": "°C"},
    {"field": "outside_humidity", "name": "Outside Humidity", "unit": "%"},
    {"field": "co2_level", "name": "CO2 Level", "unit": "ppm"},
]
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HOMEKIT_DB_PATH` | `homekit_data.db` | SQLite database path |
| `HOMEKIT_HOST` | `0.0.0.0` | Server bind address |
| `HOMEKIT_PORT` | `5000` | Server port |
| `HOMEKIT_API_KEY` | *(none)* | Optional API key for authentication |

### Authentication

To enable API key authentication:

```bash
export HOMEKIT_API_KEY="your-secret-key"
python3 homekit_logger.py --port 5050
```

Then include the key in requests:
```bash
curl -X POST http://localhost:5050/log \
     -H "X-API-Key: your-secret-key" \
     -F 'outside_temp=18.5'
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Web dashboard |
| `/log` | POST | Submit sensor readings (form or JSON) |
| `/readings` | GET | Recent readings as JSON (`?limit=N`, max 10000) |
| `/readings/csv` | GET | Export all data as CSV (streamed) |
| `/health` | GET | Health check with DB status |

## iOS Shortcut Setup

1. Create a HomeKit automation that runs a Shortcut
2. In the Shortcut, use "Get Contents of URL":
   - **URL**: `http://<your-server-ip>:5050/log`
   - **Method**: POST
   - **Request Body**: Form
   - **Fields**: Use your sensor field names (e.g., `outside_temp`)

See the [original article](https://blog.claude.nl/posts/logging-homekit-data-to-google-sheets-for-free--walkthrough/) for detailed iOS automation setup.

## Running as a Service

### macOS (launchd)

```bash
# Edit paths in com.homekit.logger.plist, then:
cp com.homekit.logger.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.homekit.logger.plist
```

### Linux (systemd)

```bash
# Create /etc/systemd/system/homekit-logger.service
sudo systemctl enable homekit-logger
sudo systemctl start homekit-logger
```

## Querying Data

```bash
sqlite3 homekit_data.db

# Recent readings
SELECT * FROM readings ORDER BY timestamp DESC LIMIT 10;

# Daily averages
SELECT date(timestamp), AVG(outside_temp), AVG(outside_humidity)
FROM readings GROUP BY date(timestamp);
```

## HTTPS

For HTTPS with a self-signed certificate:

```bash
pip install pyopenssl
python3 homekit_logger.py --https --port 5050
```

For production, use a reverse proxy (Caddy, nginx) with Let's Encrypt.

## License

MIT
