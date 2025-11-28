# HomeKit Logger - SQLite Edition

A local alternative to the Google Sheets approach described in [this article](https://blog.claude.nl/posts/logging-homekit-data-to-google-sheets-for-free--walkthrough/).

Instead of posting HomeKit data to Google Forms → Google Sheets, this solution runs a simple Python server on your Mac (or any local machine) that stores data in SQLite.

## Benefits Over Google Sheets

| Feature | Google Sheets | SQLite (this solution) |
|---------|---------------|------------------------|
| Privacy | Data on Google servers | Data stays local |
| Internet required | Yes | No (local network only) |
| Query flexibility | Limited formulas | Full SQL power |
| Cell limit | 5 million cells | No practical limit |
| API rate limits | Yes | No |
| Cost | Free (with limits) | Free |
| Complexity | Google Forms setup | Simple Python server |

## Prerequisites

- Python 3.7+
- A Mac, Raspberry Pi, or any always-on computer on your network
- Flask: `pip install flask`

## Quick Start

### 1. Install & Configure

```bash
# Install Flask
pip install flask

# Download the script (or copy homekit_logger.py)
# Edit the SENSORS list at the top to match your HomeKit devices
```

### 2. Configure Your Sensors

Edit the `SENSORS` list in `homekit_logger.py`:

```python
SENSORS = [
    {"field": "outside_temp", "name": "Outside Temperature", "unit": "°C"},
    {"field": "outside_humidity", "name": "Outside Humidity", "unit": "%"},
    {"field": "living_room_temp", "name": "Living Room Temperature", "unit": "°C"},
    {"field": "co2_level", "name": "CO2 Level", "unit": "ppm"},
    # Add your sensors here...
]
```

### 3. Run the Server

```bash
python homekit_logger.py
```

The server starts on port 5000. Find your Mac's IP address:
```bash
ipconfig getifaddr en0  # For Wi-Fi
# or
ipconfig getifaddr en1  # For Ethernet
```

### 4. Test It

```bash
# From terminal, test the endpoint:
curl -X POST http://localhost:5000/log \
     -F 'outside_temp=18.5' \
     -F 'outside_humidity=65'

# Check the dashboard in your browser:
open http://localhost:5000/
```

## Setting Up the iOS Shortcut

Follow the original article's instructions for creating the HomeKit automation, but with these changes:

### Instead of Google Forms, Use Your Local Server

When you get to the "Get Contents of URL" step:

1. **URL**: `http://<your-mac-ip>:5000/log`
   (e.g., `http://192.168.1.100:5000/log`)

2. **Method**: POST

3. **Request Body**: Form

4. **Fields**: Use the simple field names from your config:
   - Key: `outside_temp` → Value: (your temperature variable)
   - Key: `outside_humidity` → Value: (your humidity variable)
   - etc.

### Shortcut Form Fields Comparison

| Google Forms | This Solution |
|--------------|---------------|
| `entry.760868340` | `outside_temp` |
| `entry.1004504929` | `outside_humidity` |

Much simpler field names!

## Important Notes

### HTTP vs HTTPS

The original article mentions that HomeKit hubs may require HTTPS with valid certificates. In practice:

- **HTTP works for testing** from your iOS device when editing the Shortcut
- **For automated runs on the home hub**, you might need HTTPS

If you need HTTPS:

```bash
pip install pyopenssl
python homekit_logger.py --https
```

However, self-signed certificates may not work with HomeKit hubs. Options:

1. **Use a reverse proxy** (like Caddy or nginx) with Let's Encrypt
2. **Use Tailscale** for secure networking with automatic HTTPS
3. **Try HTTP first** - many users report it works fine on local networks

### Keep the Server Running

To keep the server running in the background on macOS:

```bash
# Simple approach - run in background
nohup python homekit_logger.py > homekit.log 2>&1 &

# Or use a launchd service (more robust)
# See the included com.homekit.logger.plist file
```

### Running on a Raspberry Pi

This works great on a Raspberry Pi for always-on logging:

```bash
# On Raspberry Pi
pip install flask
python3 homekit_logger.py

# For auto-start on boot, add to /etc/rc.local or use systemd
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Web dashboard |
| `/log` | POST | Submit sensor readings |
| `/readings` | GET | Get recent readings (JSON) |
| `/readings?limit=N` | GET | Get last N readings |
| `/readings/csv` | GET | Export all data as CSV |
| `/health` | GET | Health check |

## Querying Your Data

The data is stored in `homekit_data.db`. You can query it directly:

```bash
# Open SQLite shell
sqlite3 homekit_data.db

# Example queries
sqlite> SELECT * FROM readings ORDER BY timestamp DESC LIMIT 10;
sqlite> SELECT AVG(outside_temp) FROM readings WHERE timestamp > datetime('now', '-1 day');
sqlite> SELECT strftime('%Y-%m-%d %H:00', timestamp) as hour, AVG(co2_level)
        FROM readings
        GROUP BY hour;
```

Or use any SQLite GUI like DB Browser for SQLite, TablePlus, etc.

## Visualization Options

Since you now have a SQLite database, you can:

1. **Export to CSV** via `/readings/csv` and import to Excel/Numbers
2. **Use Grafana** with the SQLite plugin for dashboards
3. **Write Python scripts** with matplotlib/plotly for custom graphs
4. **Use Datasette** for instant data exploration:
   ```bash
   pip install datasette
   datasette homekit_data.db
   ```

## Troubleshooting

### Server Not Reachable from iOS
- Ensure your Mac and iOS device are on the same network
- Check macOS firewall settings (System Preferences → Security & Privacy → Firewall)
- Try the IP address, not hostname

### Data Not Appearing
- Check the terminal output for errors
- Test with curl first
- Verify field names match exactly (case-sensitive)

### Shortcut Errors
- "Server not found": Check IP address and that server is running
- Empty data: Check field names in Shortcut match SENSORS config
- Test manually using the play button in Shortcut editor

## File Structure

```
homekit_logger.py    # Main server script
homekit_data.db      # SQLite database (created automatically)
homekit.log          # Log file (if using nohup)
```

## License

MIT - Do whatever you want with this!
