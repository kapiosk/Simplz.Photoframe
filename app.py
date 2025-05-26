import os
import threading
from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.utils import secure_filename
from functools import wraps
import gpiod
import gpiodevice
from gpiod.line import Bias, Direction, Edge

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = os.environ.get('PHOTOFRAME_SECRET_KEY', 'change_this_secret')

PHOTOFRAME_PASSWORD = os.environ.get('PHOTOFRAME_PASSWORD', 'changeme')
PRINT_INTERVAL = int(os.environ.get('PHOTOFRAME_PRINT_INTERVAL', 10))

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Shared index for image navigation
image_index = {"idx": 0}
image_lock = threading.Lock()
image_update_event = threading.Event()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Auth decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == PHOTOFRAME_PASSWORD:
            session['logged_in'] = True
            next_url = request.args.get('next') or url_for('index')
            return redirect(next_url)
        else:
            error = 'Invalid password.'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    if request.method == 'POST':
        if 'file' not in request.files:
            return redirect(request.url)
        file = request.files['file']
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            return redirect(url_for('index'))
    images = os.listdir(app.config['UPLOAD_FOLDER'])
    return render_template('index.html', images=images)

@app.route('/delete/<filename>', methods=['POST'])
@login_required
def delete_file(filename):
    path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if os.path.exists(path):
        os.remove(path)
    return redirect(url_for('index'))

class PrintImageDisplayer():
    def display(self, image_path, filename):
        print(f"[Photoframe] Would display image: {filename}")

class InkyImageDisplayer():
    def __init__(self):
        from inky.auto import auto
        self.inky = auto(ask_user=True, verbose=True)
        self.saturation = float(os.environ.get('PHOTOFRAME_SATURATION', 0.5))
        from PIL import Image
        self.Image = Image
    def display(self, image_path, filename):
        image = self.Image.open(image_path)
        resizedimage = image.resize(self.inky.resolution)
        try:
            self.inky.set_image(resizedimage, saturation=self.saturation)
        except TypeError:
            self.inky.set_image(resizedimage)
        self.inky.show()
        print(f"[Photoframe] Displayed image: {filename}")

# Only load GPIO/button functionality in production
# if not app.debug:

# Button GPIOs (BCM numbering)
SW_A = 5
SW_B = 6
SW_C = 25
SW_D = 24
BUTTONS = [SW_A, SW_B, SW_C, SW_D]
LABELS = ["A", "B", "C", "D"]
INPUT = gpiod.LineSettings(direction=Direction.INPUT, bias=Bias.PULL_UP, edge_detection=Edge.FALLING)
chip = gpiodevice.find_chip_by_platform()
OFFSETS = [chip.line_offset_from_id(id) for id in BUTTONS]
line_config = dict.fromkeys(OFFSETS, INPUT)
request = chip.request_lines(consumer="photoframe-buttons", config=line_config)

def handle_button(event):
    index = OFFSETS.index(event.line_offset)
    label = LABELS[index]
    print(f"Button press detected: {label}")
    if label == "A":
        print("Disabling WiFi (wlan0 down)...")
        os.system("sudo ifconfig wlan0 down")
    elif label == "B":
        print("Enabling WiFi (wlan0 up)...")
        os.system("sudo ifconfig wlan0 up")
    elif label == "C":
        with image_lock:
            image_index["idx"] -= 2
            print("Previous image requested.")
            image_update_event.set()
    elif label == "D":
        with image_lock:
            print("Next image requested.")
            image_update_event.set()

def button_event_thread():
    while True:
        for event in request.read_edge_events():
            handle_button(event)
threading.Thread(target=button_event_thread, daemon=True).start()

def background_image_printer():
    if app.debug:
        displayer = PrintImageDisplayer()
    else:
        displayer = InkyImageDisplayer()
    while True:
        try:
            images = [img for img in os.listdir(UPLOAD_FOLDER) if allowed_file(img)]
            images.sort()
            with image_lock:
                if images:
                    # Clamp index to valid range
                    image_index["idx"] = (image_index["idx"] + 1) % len(images)
                    filename = images[image_index["idx"]]
                    image_path = os.path.join(UPLOAD_FOLDER, filename)
                    displayer.display(image_path, filename)
                else:
                    print("[Photoframe] No images found in uploads folder.")
                    image_index["idx"] = 0
        except Exception as e:
            print(f"[Photoframe] Error in background worker: {e}")
        # Wait for either the interval or a button event
        image_update_event.wait(timeout=PRINT_INTERVAL)
        image_update_event.clear()

# Start background worker
threading.Thread(target=background_image_printer, daemon=True).start()

if __name__ == '__main__':
    app.run(debug=True, port=5053)