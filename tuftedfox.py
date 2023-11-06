import subprocess, json, os, requests, random
from flask import Flask, render_template, request, jsonify, abort, Response, g, send_from_directory
from werkzeug.utils import safe_join
from werkzeug.exceptions import NotFound
from werkzeug.routing import RequestRedirect
from datetime import datetime
from dotenv import load_dotenv

app = Flask(__name__)

#-------------------------------------------------------------------
# app variables 
#-------------------------------------------------------------------

load_dotenv()
secret_password = os.getenv('SECRET_PASSWORD')
app_start_time = int(datetime.utcnow().timestamp())
page_hits = {}
page_hits_invalid = {}

#-------------------------------------------------------------------
# functions 
#-------------------------------------------------------------------

def save_page_hits():
    try:
        with open('data/page_hits.json', 'w') as f:
            json.dump(page_hits, f)
    except IOError as e:
        print(f"An error occurred while saving valid page hits: {e}")

    try:
        with open('data/page_hits_invalid.json', 'w') as f:
            json.dump(page_hits_invalid, f)
    except IOError as e:
        print(f"An error occurred while saving invalid page hits: {e}")

def load_page_hits():
    tmp_hits = {}
    tmp_invalid = {}
    try:
        with open('data/page_hits.json', 'r') as f:
            tmp_hits = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        tmp_hits = {}
    try:
        with open('data/page_hits_invalid.json', 'r') as f:
            tmp_invalid = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        tmp_invalid = {}
        
    return tmp_hits, tmp_invalid

page_hits, page_hits_invalid = load_page_hits()

#-------------------------------------------------------------------
# page count injection
#-------------------------------------------------------------------

@app.before_request
def before_request():
    global page_hits, page_hits_invalid
    page = request.path
    try:
        # Try to match the request path to the URL map
        app.url_map.bind('').match(page)
        # If the above line doesn't raise an exception, the route is valid
        page_hits[page] = page_hits.get(page, 0) + 1
    except (NotFound, RequestRedirect):
        # If the route is not found or a redirect, consider it invalid
        page_hits_invalid[page] = page_hits_invalid.get(page, 0) + 1
    finally:
        save_page_hits()

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
    # Sort the valid page hits
    sorted_page_hits = sorted(page_hits.items(), key=lambda item: item[1], reverse=True)
    sorted_page_hits_dict = dict(sorted_page_hits)

    # Sort the invalid page hits
    sorted_page_hits_invalid = sorted(page_hits_invalid.items(), key=lambda item: item[1], reverse=True)
    sorted_page_hits_invalid_dict = dict(sorted_page_hits_invalid)

    # Pass both dictionaries to the template
    return render_template('count.html',
                           page_hits=sorted_page_hits_dict,
                           page_hits_invalid=sorted_page_hits_invalid_dict)

@app.route('/order')
def order_page():
    return render_template('order.html')

@app.route('/gallery')
def gallery_page():
    rugs_folder = 'img/rugs'
    thumbnails_folder = 'img/rugs/thumbnails'
    image_data = []
    image_names = sorted(os.listdir(rugs_folder))

    for image_name in image_names:
        if os.path.isfile(os.path.join(rugs_folder, image_name)):
            image_url = f'{rugs_folder}/{image_name}'
            thumbnail_url = f'{thumbnails_folder}/{image_name}'
            image_data.append((thumbnail_url, image_url))

    return render_template('gallery.html', image_data=image_data)


@app.route('/about')
def about_tuftedfox():
    return render_template('about.html')

#-------------------------------------------------------------------
# api routes
#-------------------------------------------------------------------

@app.route('/favicon.ico')
def favicon():
    favicon_path = safe_join(app.root_path, 'img/icons/favicon.ico')
    if not os.path.isfile(favicon_path):
        abort(404)
    return send_from_directory(os.path.join(app.root_path, 'img/icons'), 'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route('/img/<folder>/<path:image_name>')
def serve_image(folder, image_name):
    valid_folders = ['404', 'rugs', 'icons']
    
    if folder not in valid_folders:
        abort(404)

    image_folder = safe_join('img', folder)
    safe_image_path = safe_join(image_folder, image_name)
    
    if not os.path.isfile(safe_image_path):  
        abort(404)

    return send_from_directory(image_folder, image_name)

#-------------------------------------------------------------------
# Error handlers
#-------------------------------------------------------------------

@app.errorhandler(404)
def page_not_found(e):
    error_folder_path = os.path.join('img', '404')
    error_images = os.listdir(error_folder_path)
    random_image_name = random.choice(error_images)
    image_path = f'/img/404/{random_image_name}'
    return render_template('404.html', image_path=image_path), 404

#-------------------------------------------------------------------

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8081)