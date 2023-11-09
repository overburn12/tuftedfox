import subprocess, json, os, requests, random
from flask import Flask, render_template, request, jsonify, abort, Response, g, send_from_directory
from werkzeug.utils import safe_join
from werkzeug.exceptions import NotFound
from werkzeug.routing import RequestRedirect
from datetime import datetime
from dotenv import load_dotenv
from PIL import Image
import random

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

def generate_thumbnail(image_path, thumbnail_path, size=(256, 256)):
    with Image.open(image_path) as img:
        img.thumbnail(size)
        img.save(thumbnail_path)

def check_all_thumbnails(dir_path, safe_extensions={'png', 'jpg', 'jpeg'}):
    for root, dirs, files in os.walk(dir_path):
        # Skip any thumbnails folders
        if 'thumbnails' in dirs:
            dirs.remove('thumbnails')

        thumbnail_directory = os.path.join(root, 'thumbnails')
        image_files = [f for f in files if f.split('.')[-1].lower() in safe_extensions]

        # Create thumbnail directory only if there are image files
        if image_files and not os.path.exists(thumbnail_directory):
            os.makedirs(thumbnail_directory)

        existing_thumbnails = set(os.listdir(thumbnail_directory)) if os.path.exists(thumbnail_directory) else set()
        parent_images = set()

        for file in image_files:
            image_path = os.path.join(root, file)
            thumbnail_path = os.path.join(thumbnail_directory, file)
            parent_images.add(file)

            #if not os.path.exists(thumbnail_path):
            generate_thumbnail(image_path, thumbnail_path)

        # Remove thumbnails without a parent image
        for thumbnail in existing_thumbnails:
            if thumbnail not in parent_images:
                os.remove(os.path.join(thumbnail_directory, thumbnail))

        # Delete the thumbnail directory if empty
        if os.path.exists(thumbnail_directory) and not parent_images:
            os.rmdir(thumbnail_directory)

def load_images_for_category(category_path):
    allowed_extensions = ['jpg', 'jpeg', 'png']
    images = []

    thumbnails_folder = os.path.join(category_path, 'thumbnails')
    comments_path = os.path.join(category_path, 'comments.json')
    comments = {}

    if os.path.exists(comments_path):
        with open(comments_path) as file:
            comments_data = json.load(file)
            for item in comments_data:
                comments[item['filename']] = item['comment']

    for image_name in os.listdir(category_path):
        if image_name != 'thumbnails' and image_name.split('.')[-1].lower() in allowed_extensions:
            image_path = os.path.join(category_path, image_name)
            thumbnail_path = os.path.join(thumbnails_folder, image_name)
            
            comment = comments.get(image_name, "")  # Get comment if exists, else empty string
            images.append((thumbnail_path, image_path, comment))

    images.sort(key=lambda x: os.path.basename(x[1]))
    return images

def load_gallery_data(folder_path):
    order_file_path = os.path.join(folder_path, 'order.json')
    order_data = []

    # Check if order.json exists and load its content
    if os.path.exists(order_file_path):
        with open(order_file_path) as file:
            order_data = json.load(file)

    galleries_data = {}
    processed_categories = set()

    # Process categories as per order.json
    for entry in order_data:
        sub_directory = entry['path']
        category_name = entry['category']
        category_comment = entry.get('comment', '')
        category_path = os.path.join(folder_path, sub_directory)

        if os.path.isdir(category_path):
            processed_categories.add(sub_directory)
            galleries_data[category_name] = {
                'images': load_images_for_category(category_path),
                'comment': category_comment
            }

    # Process remaining directories not mentioned in order.json
    for sub_directory in os.listdir(folder_path):
        if sub_directory not in processed_categories and os.path.isdir(os.path.join(folder_path, sub_directory)):
            galleries_data[sub_directory] = {
                'images': load_images_for_category(os.path.join(folder_path, sub_directory)),
                'comment': ''
            }

    return galleries_data

#-------------------------------------------------------------------
# page count injection
#-------------------------------------------------------------------

@app.before_request
def before_request():
    global page_hits, page_hits_invalid
    page = request.path

    # Skip tracking for any path containing 'thumbnail'
    if 'thumbnail' in page:
        return

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

@app.route('/thumbnail_everything',  methods=['GET', 'POST'])
def do_the_thumbnails():
    if request.method == 'POST':
        if request.form.get('secret_word') == secret_password:
            check_all_thumbnails('img/')
            return '<html>the thumbnail cleaning is done!</html>'
        else:
            return '<html>wrong secret password!</html>'
    else:
        return '<html>this page should be accessed with a POST request</html>'

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
    # Sort the valid page hits alphabetically by path name
    sorted_page_hits = sorted(page_hits.items(), key=lambda item: item[0])
    sorted_page_hits_dict = dict(sorted_page_hits)

    # Sort the invalid page hits alphabetically by path name
    sorted_page_hits_invalid = sorted(page_hits_invalid.items(), key=lambda item: item[0])
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
    galleries_data = load_gallery_data('img/rugs')
    return render_template('gallery.html', galleries_data=galleries_data)

@app.route('/render')
def render_page():
    galleries_data = load_gallery_data('img/ai')
    return render_template('gallery.html', galleries_data=galleries_data)

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
    valid_folders = ['404', 'rugs', 'icons', 'ai']
    
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
    safe_extensions = {'png', 'jpg', 'jpeg', 'bmp'}
    # Filter out files that don't have a safe extension
    error_images = [img for img in os.listdir(error_folder_path) if img.split('.')[-1].lower() in safe_extensions]
    random_image_name = random.choice(error_images)
    image_path = f'/img/404/{random_image_name}'
    return render_template('404.html', image_path=image_path), 404


#-------------------------------------------------------------------

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8081)