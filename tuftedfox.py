import subprocess, json, os, requests, random
from flask import Flask, render_template, request, jsonify, abort, Response, g
from datetime import datetime
from dotenv import load_dotenv

app = Flask(__name__)

#-------------------------------------------------------------------
# app variables 
#-------------------------------------------------------------------

load_dotenv()
secret_password = os.getenv('SECRET_PASSWORD')
app_start_time = int(datetime.utcnow().timestamp())
images = {}
images_404 = {}
page_hits = {}

#-------------------------------------------------------------------
# functions 
#-------------------------------------------------------------------

def save_page_hits():
    with open('data/page_hits.json', 'w') as f:
        json.dump(page_hits, f)

def load_page_hits():
    try:
        with open('data/page_hits.json', 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

page_hits = load_page_hits()

def load_images_to_memory():
    image_folder = 'img/'
    image_entries = os.listdir(image_folder)
    images = {}

    for entry in image_entries:
        entry_path = os.path.join(image_folder, entry)
        # Check if the entry is a file
        if os.path.isfile(entry_path):
            with open(entry_path, 'rb') as f:
                images[entry] = f.read()

    return images

images = load_images_to_memory()

def load_404_images_to_memory():
    image_folder = 'img/404/'
    image_entries = os.listdir(image_folder)
    images = {}

    for entry in image_entries:
        entry_path = os.path.join(image_folder, entry)
        # Check if the entry is a file
        if os.path.isfile(entry_path):
            with app.open_resource(entry_path, 'rb') as f:
                images[entry] = f.read()
    return images

images_404 = load_404_images_to_memory()

#-------------------------------------------------------------------
# page count injection
#-------------------------------------------------------------------

@app.before_request
def before_request():
    global page_hits
    page = request.path

    # Track hits per page
    page_hits[page] = page_hits.get(page, 0) + 1
    save_page_hits()  # Save page hits as needed, this is not a permanent spot to do it

#-------------------------------------------------------------------
# page routes
#-------------------------------------------------------------------

@app.route('/')
def index():
    #ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    return render_template('index.html')

@app.route('/update', methods=['GET', 'POST'])
def update_server():
    if request.method == 'POST':
        if request.form.get('secret_word') == secret_password:
            subprocess.run('python3 updater.py', shell=True)

    with open('data/update.log', 'r') as logfile:
        log_content = logfile.read()

    return render_template('update.html', log_content=log_content, app_start_time=app_start_time)

@app.route('/count')
def count_page():
    return render_template('count.html', page_hits=page_hits)

@app.route('/order')
def order_page():
    return render_template('order.html')

@app.route('/gallery')
def gallery_page():
    return render_template('gallery.html')

@app.route('/about')
def about_tuftedfox():
    return render_template('about.html')

#-------------------------------------------------------------------
# api routes
#-------------------------------------------------------------------

@app.route('/404.png')
def serve_random_404_image():
    #serve a random image as the 404.png   ill remove this later so the front end will choose the image
    random_filename = random.choice(list(images_404.keys()))
    return Response(images_404[random_filename], mimetype='image/png')

@app.route('/<path:image_name>')
def serve_image(image_name):
    name, extension = os.path.splitext(image_name)
    mime_map = {
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.ico': 'image/x-icon',
        '.gif': 'image/gif',
    }  
    mime_type = mime_map.get(extension.lower())
    image_file = images.get(f'{name}{extension}')
    
    if image_file and mime_type:
        return Response(image_file, content_type=mime_type)
    else:
        abort(404)  # Return a 404 error if the image or MIME type is not found

#-------------------------------------------------------------------

@app.errorhandler(404)
def page_not_found(e):
    # note that we set the 404 status explicitly
    return render_template('404.html'), 404

#-------------------------------------------------------------------

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8081)