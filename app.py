import os
from flask import Flask, render_template, request, redirect, url_for, session, abort
from werkzeug.utils import secure_filename
from functools import wraps

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = os.environ.get('PHOTOFRAME_SECRET_KEY', 'change_this_secret')

PHOTOFRAME_PASSWORD = os.environ.get('PHOTOFRAME_PASSWORD', 'changeme')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

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

if __name__ == '__main__':
    app.run(debug=True, port=5053)
