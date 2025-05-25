# Simplz.Photoframe

A simple Flask-based image upload and management web app.

## Features
- Drag-and-drop image upload
- Image gallery with delete option

## Running as a Service on Linux

1. **Clone the repository and install dependencies:**
   ```sh
   git clone <your-repo-url>
   cd Simplz.Photoframe
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Create a systemd service file:**
   Create `/etc/systemd/system/photoframe.service` with the following content (edit paths and user as needed):
   ```ini
   [Unit]
   Description=Simplz Photoframe Flask App
   After=network.target

   [Service]
   User=www-data
   WorkingDirectory=/path/to/Simplz.Photoframe
   Environment="FLASK_APP=app.py"
   Environment="FLASK_ENV=production"
   ExecStart=/path/to/Simplz.Photoframe/venv/bin/flask run --host=0.0.0.0 --port=5052
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```

3. **Reload systemd and start the service:**
   ```sh
   sudo systemctl daemon-reload
   sudo systemctl start photoframe
   sudo systemctl enable photoframe
   ```

4. **Check status:**
   ```sh
   sudo systemctl status photoframe
   ```

The app will now run as a service and restart automatically on failure or reboot.
