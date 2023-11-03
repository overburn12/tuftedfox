import subprocess, json, os, requests
from flask import Flask, render_template, request, jsonify, abort, Response
from datetime import datetime
from dotenv import load_dotenv

app = Flask(__name__)

#-------------------------------------------------------------------
# app variables 
#-------------------------------------------------------------------

load_dotenv()
secret_password = os.getenv('SECRET_PASSWORD')
images = {}
app_start_time = int(datetime.utcnow().timestamp())

#-------------------------------------------------------------------
# functions 
#-------------------------------------------------------------------

def load_images_to_memory():
    image_folder = 'img/'
    image_filenames = os.listdir(image_folder)
    
    for filename in image_filenames:
        with app.open_resource(os.path.join(image_folder, filename), 'rb') as f:
            images[filename] = f.read()

load_images_to_memory()

#-------------------------------------------------------------------
# page routes
#-------------------------------------------------------------------

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/update', methods=['GET', 'POST'])
def update_server():
    if request.method == 'POST':
        if request.form.get('secret_word') == secret_password:
            print("RUNNING UPDATER!!!!!!!!!!!!!!!!!!!!!!")
            subprocess.run('python3 updater.py', shell=True)

    with open('data/update.log', 'r') as logfile:
        log_content = logfile.read()

    return render_template('update.html', log_content=log_content, app_start_time=app_start_time)

#-------------------------------------------------------------------
# api routes
#-------------------------------------------------------------------

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

@app.route('/gallery')
def image_gallery():
    html_content = '<!DOCTYPE html><html><body><center>'
    
    for filename in images.keys():
        name, extension = os.path.splitext(filename)  
        html_content += f'<figure><img src="/{name}{extension}" alt="{filename}">'
        html_content += f'<figcaption>{filename}</figcaption></figure>'

    html_content += '</center></body></html>'
    return html_content

#-------------------------------------------------------------------

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8081)