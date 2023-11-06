import subprocess, json, os, requests, random
from flask import Flask, render_template, request, jsonify, abort, Response, g, send_from_directory
from werkzeug.utils import safe_join
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
    # Sort page_hits by hits in descending order
    sorted_page_hits = sorted(page_hits.items(), key=lambda item: item[1], reverse=True)
    # Convert the sorted list of tuples back into a dictionary
    sorted_page_hits_dict = dict(sorted_page_hits)
    # Pass the sorted dictionary to the template
    return render_template('count.html', page_hits=sorted_page_hits_dict)

@app.route('/order')
def order_page():
    return render_template('order.html')

@app.route('/gallery')
def gallery_page():
    # Define the directories where the images and thumbnails are stored
    rugs_folder = 'img/rugs'
    thumbnails_folder = 'img/thumbnails'

    # Initialize an empty list to hold the image URLs and thumbnail URLs
    image_data = []

    # Get the list of image file names and sort them alphabetically
    image_names = sorted(os.listdir(rugs_folder))

    # Construct the URLs for each image and its thumbnail
    for image_name in image_names:
        if os.path.isfile(os.path.join(rugs_folder, image_name)):
            image_url = f'/img/rugs/{image_name}'
            thumbnail_url = f'/img/rugs/thumbnails/{image_name}'
            image_data.append((thumbnail_url, image_url))

    # Pass the image data to the template
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
    # List of valid folders
    valid_folders = ['404', 'rugs', 'icons']
    
    # Check if the provided folder is valid
    if folder not in valid_folders:
        abort(404)

    image_folder = safe_join('img', folder)
    safe_image_path = safe_join(image_folder, image_name)
    
    if not os.path.isfile(safe_image_path):  # Check if the file exists and is a file
        abort(404)

    # Send the file from the directory, ensuring that the MIME type and other
    # headers are handled correctly.
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