import os
import threading
import json
from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.utils import secure_filename
from functools import wraps

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
SEQUENCE_FILE = os.path.join('static', 'sequence.json')

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = os.environ.get('PHOTOFRAME_SECRET_KEY', 'change_this_secret')

PHOTOFRAME_PASSWORD = os.environ.get('PHOTOFRAME_PASSWORD', 'changeme')
PRINT_INTERVAL = int(os.environ.get('PHOTOFRAME_PRINT_INTERVAL', 60))

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Shared index for image navigation
image_index = {"idx": 0}
image_lock = threading.Lock()
image_update_event = threading.Event()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Sequence loading/saving helpers

def load_sequence():
    if os.path.exists(SEQUENCE_FILE):
        with open(SEQUENCE_FILE, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except Exception:
                return []
    return []

def save_sequence(seq):
    with open(SEQUENCE_FILE, 'w', encoding='utf-8') as f:
        json.dump(seq, f, indent=2)

def get_image_sequence():
    all_images = [img for img in os.listdir(UPLOAD_FOLDER) if allowed_file(img)]
    all_images_set = set(all_images)
    sequence = []
    json_seq = load_sequence()
    for img in json_seq:
        if img in all_images_set:
            sequence.append(img)
            all_images_set.remove(img)
    sequence.extend(sorted(all_images_set))
    return sequence

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
        files = request.files.getlist('file')
        for file in files:
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

@app.route('/api/sequence', methods=['GET'])
@login_required
def api_get_sequence():
    return {"sequence": get_image_sequence()}

@app.route('/api/sequence', methods=['POST'])
@login_required
def api_save_sequence():
    data = request.get_json()
    seq = data.get('sequence', [])
    save_sequence(seq)
    return {"ok": True}

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
if not app.debug:
    import gpiod
    import gpiodevice
    from gpiod.line import Bias, Direction, Edge, Value
    import time
    # Button GPIOs (BCM numbering)
    SW_A = 5
    SW_B = 6
    SW_C = 25
    SW_D = 24
    LED_PIN = 13
    BUTTONS = [SW_A, SW_B, SW_C, SW_D]
    LABELS = ["A", "B", "C", "D"]
    INPUT = gpiod.LineSettings(direction=Direction.INPUT, bias=Bias.PULL_UP, edge_detection=Edge.BOTH)
    chip = gpiodevice.find_chip_by_platform()
    led = chip.line_offset_from_id(LED_PIN)
    gpio = chip.request_lines(consumer="inky", config={led: gpiod.LineSettings(direction=Direction.OUTPUT, bias=Bias.DISABLED)})
    OFFSETS = [chip.line_offset_from_id(id) for id in BUTTONS]
    line_config = dict.fromkeys(OFFSETS, INPUT)
    button_request = chip.request_lines(consumer="photoframe-buttons", config=line_config)

    def handle_button(event):
        index = OFFSETS.index(event.line_offset)
        label = LABELS[index]
        print(f"Button press detected: {label}")
        if label == "A":
            # Check for long press (5 seconds)
            if event.event_type == Edge.FALLING:
                press_time = time.monotonic()
                # Wait for rising edge or timeout
                while True:
                    evs = button_request.read_edge_events(timeout=0.1)
                    for ev in evs:
                        if ev.line_offset == event.line_offset and ev.event_type == Edge.RISING:
                            duration = time.monotonic() - press_time
                            if duration >= 5.0:
                                print("A held for 5s, shutting down Pi...")
                                os.system("sudo shutdown now")
                                return
                            else:
                                print(f"A pressed for {duration:.2f}s (not long enough for shutdown)")
                                return
                    if time.monotonic() - press_time >= 5.0:
                        print("A held for 5s, shutting down Pi...")
                        os.system("sudo shutdown now")
                        return
            else:
                print("Disabling WiFi (wlan0 down)...")
                os.system("sudo ifconfig wlan0 down")
                gpio.set_value(led, Value.INACTIVE)
        elif label == "B":
            print("Enabling WiFi (wlan0 up)...")
            os.system("sudo ifconfig wlan0 up")
            gpio.set_value(led, Value.ACTIVE)
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
            for event in button_request.read_edge_events():
                handle_button(event)
    threading.Thread(target=button_event_thread, daemon=True).start()

def background_image_printer():
    if app.debug:
        displayer = PrintImageDisplayer()
    else:
        displayer = InkyImageDisplayer()
    while True:
        try:
            images = get_image_sequence()
            with image_lock:
                if images:
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