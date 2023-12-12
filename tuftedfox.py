import subprocess, json, os, random, re
from flask import Flask, render_template, request, jsonify, abort, Response, g, send_from_directory, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from functools import wraps
from werkzeug.utils import safe_join
from werkzeug.exceptions import NotFound
from werkzeug.routing import RequestRedirect
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime, timedelta
from dotenv import load_dotenv
from PIL import Image
import random
from werkzeug.utils import secure_filename
from sqlalchemy import text

app = Flask(__name__)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('logged_in'):
            return f(*args, **kwargs)
        else:
            flash('You need to be logged in to view this page.')
            return redirect(url_for('admin_login'))
    return decorated_function

#-------------------------------------------------------------------
# app variables 
#-------------------------------------------------------------------

ORDER_FOLDER = 'orders/'
UPLOAD_FOLDER = 'orders/'

load_dotenv()
app.secret_key = os.getenv('SECRET_KEY')
admin_username = os.getenv('ADMIN_NAME')
admin_password = os.getenv('ADMIN_PASSWORD')
admin_password_hash = generate_password_hash(admin_password)  

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tuftedfox.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app_start_time = int(datetime.utcnow().timestamp())

db = SQLAlchemy(app)

class PageHit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    page_url = db.Column(db.String(500))
    hit_type = db.Column(db.String(50)) # 'image', 'valid', 'invalid'
    visit_datetime = db.Column(db.DateTime, default=datetime.utcnow)
    visitor_id = db.Column(db.String(100)) # IP or session ID

#-------------------------------------------------------------------
# functions 
#-------------------------------------------------------------------

def generate_thumbnail(image_path, thumbnail_path, size):
    with Image.open(image_path) as img:
        img.thumbnail(size)
        img.save(thumbnail_path)

def check_all_thumbnails(dir_path, size=(256, 256)):
    ignore_dir = ['thumbnails', 'icons', '404']
    safe_extensions={'png', 'jpg', 'jpeg'}

    for root, dirs, files in os.walk(dir_path):
        dirs[:] = [d for d in dirs if d not in ignore_dir]

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

            #i disabled this line so it always overwrites every thumbnail, enable to only create new ones
            #if not os.path.exists(thumbnail_path):
            generate_thumbnail(image_path, thumbnail_path, size)

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

    rug_groups = {}
    for image in images:
        image_name = os.path.basename(image[1])
        match = re.match(r"(.*?)_\d+\.\w+$", image_name)
        if match:
            # If the filename matches the pattern, use the extracted name
            rug_name = match.group(1)
        else:
            # If not, use the whole filename (without extension)
            rug_name = os.path.splitext(image_name)[0]

        if rug_name not in rug_groups:
            rug_groups[rug_name] = []
        rug_groups[rug_name].append(image)

    grouped_images = []
    for rug_name, imgs in rug_groups.items():
        grouped_images.append({
            'name': rug_name,
            'images': imgs,
            'comment': comments.get(imgs[0][1], "")  # Comment of the first image
        })

    return grouped_images

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

def generate_filename(filepath):
    directory, filename = os.path.split(filepath)
    base, extension = os.path.splitext(filename)
    if not base.endswith("_"):
        base += "_"
    i = 1
    while os.path.exists(os.path.join(directory, f"{base}{i:02d}{extension}")):
        i += 1
    return os.path.join(directory, f"{base}{i:02d}{extension}")

#-------------------------------------------------------------------
# page count
#-------------------------------------------------------------------

@app.before_request
def before_request():
    page = request.path
    hit_type = 'none'
    visitor_id = request.headers.get('X-Forwarded-For', request.remote_addr)
    ignore_list = ['thumbnail', 'icons']

    for item in ignore_list:
        if item in page:
            return
    try:
        app.url_map.bind('').match(page)
        if page.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
            hit_type = 'image'
        else:
            hit_type = 'valid'
    except (NotFound, RequestRedirect):
        hit_type = 'invalid'
    finally:
        new_hit = PageHit(page_url=page, hit_type=hit_type, visitor_id=visitor_id)
        db.session.add(new_hit)
        db.session.commit()

#-------------------------------------------------------------------
# page routes
#-------------------------------------------------------------------

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/custom', methods=['GET', 'POST'])
def custom_page():
    return render_template('custom.html')

@app.route('/gallery', methods=['GET', 'POST'])
def gallery_page():
    galleries_data = load_gallery_data('img/rugs')
    return render_template('gallery.html', galleries_data=galleries_data, gallery_size='large')

@app.route('/render', methods=['GET', 'POST'])
def render_page():
    galleries_data = load_gallery_data('img/ai')
    return render_template('gallery.html', galleries_data=galleries_data, gallery_size='small')

@app.route('/order', methods=['GET', 'POST'])
def order_page():
    return render_template('order.html')

@app.route('/order_sent', methods=['GET', 'POST'])
def order_sent():
    message_title = 'Order Recieved!'
    message_content = '<p>Thank you for your order! we will contact you soon. </p><P>redirecting in 3 seconds...</p>'
    return render_template('redirect.html', message_title=message_title, message_content=message_content)

@app.route('/message', methods=['GET', 'POST'])
def message_page():
    if request.method == 'POST':
        message = request.form['message']
        filename = generate_filename('messages/m.txt')
        with open(filename, 'w') as file:
            file.write(message)
        return redirect('/message_sent')
    return render_template('message.html')

@app.route('/message_sent', methods=['GET', 'POST'])
def message_sent():
    message_title = 'Sent!'
    message_content = '<p>Thank you for reaching out. Your message has been successfully sent. </p><P>redirecting in 3 seconds...</p>'
    return render_template('redirect.html', message_title=message_title, message_content=message_content)

@app.route('/count', methods=['GET', 'POST'])
def count_page():

    # Query and tally the valid page hits
    exclude_words = ['admin', '404', 'thumbnail', 'icon', 'logout', 'api', 'upload_image','order_sent','submit_order', 'message_sent']
    valid_hits = db.session.query(
        PageHit.page_url,
        func.count(PageHit.id)
    ).filter(
        PageHit.hit_type == 'valid',
        ~PageHit.page_url.ilike(f'%{exclude_words[0]}%') if exclude_words else False,
        *[
            ~PageHit.page_url.ilike(f'%{word}%') for word in exclude_words[1:]
        ]
    ).group_by(PageHit.page_url).all()

    # Calculate the total count of image hits
    total_image_hits = db.session.query(
        func.count(PageHit.id)
    ).filter(
        PageHit.hit_type == 'image',
        ~PageHit.page_url.ilike(f'%{exclude_words[0]}%') if exclude_words else False,
        *[
            ~PageHit.page_url.ilike(f'%{word}%') for word in exclude_words[1:]
        ]
    ).scalar()

    # List of words to filter out for invalid hits
    exclude_invalid = ['robots.txt', 'this_page_does_not_exist']

    # Calculate the total count of invalid hits excluding certain pages
    total_invalid_hits = db.session.query(
        func.count(PageHit.id)
    ).filter(
        PageHit.hit_type == 'invalid',
        *[
            ~PageHit.page_url.ilike(f'%{word}%') for word in exclude_invalid
        ]
    ).scalar()

    # List of words to filter out for valid hits
    exclude_valid = ['styles.css']

    # Calculate the total count of valid hits excluding certain pages
    total_valid_hits = db.session.query(
        func.count(PageHit.id)
    ).filter(
        PageHit.hit_type == 'valid',
        *[
            ~PageHit.page_url.ilike(f'%{word}%') for word in exclude_valid
        ]
    ).scalar()

    total_unique = db.session.query(func.count(PageHit.visitor_id.distinct()))\
                        .filter(PageHit.hit_type.in_(['valid', 'image']))\
                        .scalar()
    
    return render_template('count.html',
                           page_hits=valid_hits,
                           total_image_hits=total_image_hits,
                           total_invalid_hits=total_invalid_hits,
                           total_unique=total_unique,
                           total_valid_hits=total_valid_hits)

@app.route('/analysis', methods=['GET','POST'])
def image_analysis_page():
    return render_template('rug_colors.html')
#--------------------------------------------

@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if 'logged_in' in session and session['logged_in']:
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == admin_username and check_password_hash(admin_password_hash, password):
            session['logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid credentials')
    return render_template('admin_login.html')  # Your login page template

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    with open('data/update.log', 'r') as logfile:
        log_content = logfile.read()

    message_count = 0
    for filename in os.listdir('messages/'):
        if filename.startswith('m_') and filename.endswith('.txt'):
            message_count += 1

    order_count = 0
    for filename in os.listdir('orders/'):
        if filename.endswith(".txt"):
            order_count += 1

    return render_template('admin_dashboard.html', log_content=log_content, app_start_time=app_start_time, message_count=message_count, order_count=order_count)

@app.route('/admin/thumbnail',  methods=['GET', 'POST'])
@admin_required
def do_the_thumbnails():
    check_all_thumbnails('img/ai/', (256, 256))
    check_all_thumbnails('img/rugs/', (512, 512))
    return '<html>the thumbnail creation is done!</html>'

@app.route('/admin/update', methods=['GET', 'POST'])
@admin_required
def update_server():
    subprocess.run('python3 updater.py', shell=True)
    return '<html>Updated!</html>'

@app.route('/admin/messages', methods = ['GET','POST'])
@admin_required
def message_center():
    messages = []
    for filename in os.listdir('messages/'):
        if filename.startswith('m_') and filename.endswith('.txt'):
            with open(os.path.join('messages', filename), 'r') as file:
                message = {
                    'filename': filename,
                    'content': file.read()
                }
                messages.append(message)

    return render_template('admin_messages.html', messages=messages)

@app.route('/admin/orders', methods = ['GET','POST'])
@admin_required
def order_center():
    orders = []
    for filename in os.listdir('orders/'):
        if filename.endswith('.txt'):
            with open(os.path.join('orders', filename), 'r') as file:
                order = {
                    'filename': filename,
                    'content': file.read()
                }
                orders.append(order)
    return render_template('admin_orders.html', orders = orders)

@app.route('/admin/count')
@admin_required
def admin_count():
    return render_template('admin_count.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('admin_login'))

#------------------------------------------------------------------------
# DB Query route
#------------------------------------------------------------------------

@app.route('/api/execute-query', methods=['POST', 'GET'])
@admin_required
def execute_query():
    query_data = request.get_json()
    query = query_data['query']

    with db.engine.connect() as connection:
        result = connection.execute(text(query))
        columns = list(result.keys())  # Convert columns to a list

        rows = [dict(zip(columns, row)) for row in result.fetchall()]

    return jsonify({'columns': columns, 'rows': rows})

#-------------------------------------------------------------------
# api routes
#-------------------------------------------------------------------

@app.route('/upload_image', methods=['GET', 'POST'])
def upload_image():
    if 'image' not in request.files:
        return jsonify({'message': 'No image part'})
    image = request.files['image']
    if image.filename == '':
        return jsonify({'message': 'No selected image'})
    filename = secure_filename(image.filename)
    image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    unique_image_path = generate_filename(image_path)
    image.save(unique_image_path)
    return jsonify({'message': 'Image uploaded successfully', 'filename': filename})

@app.route('/submit_order', methods=['GET', 'POST'])
def submit_order():
    # Retrieve image name and other form data
    image_name = request.form.get('imageName')
    width = request.form.get('width')
    height = request.form.get('height')
    details = request.form.get('details')
    customer_name = request.form.get('customerName')
    customer_contact = request.form.get('customerContact')
    
    # Save order details in a text file
    order_details = (
    f"Customer Name: {customer_name}\n"
    f"Contact Info: {customer_contact}\n"
    f"Image Name: {image_name}\n"
    f"Order for rug size: {width} inches x {height} inches\n"
    f"Details: {details}\n"
)
    order_filename = secure_filename(f"{image_name}_order.txt")
    unique_filename = generate_filename(os.path.join(ORDER_FOLDER, order_filename))
    with open(unique_filename, 'w') as file:
        file.write(order_details)
    return redirect('/order_sent')

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

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    host = os.environ.get('HOST')
    port = int(os.environ.get('PORT'))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    app.debug = debug
    app.run(host=host, port=port)