import json, os, random, re, io
from flask import Flask, render_template, request, jsonify, abort, send_from_directory, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from werkzeug.utils import safe_join
from werkzeug.exceptions import NotFound
from werkzeug.routing import RequestRedirect
from datetime import datetime
from dotenv import load_dotenv
from PIL import Image
from collections import defaultdict
import random
from werkzeug.utils import secure_filename
from sqlalchemy import text
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

app = Flask(__name__)

limiter = Limiter(
    get_remote_address,  # Use the client's IP address to track the rate limit
    app=app,
    default_limits=["200 per day", "10 per minute"]  # Default rate limits
)

#-------------------------------------------------------------------
# app variables 
#-------------------------------------------------------------------

ORDER_FOLDER = 'orders/'
UPLOAD_FOLDER = 'orders/'

load_dotenv()

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

def analyze_image_colors(img, colors_used):
    if img.mode == 'P':
        img = img.convert('RGBA')
    pixels = img.getdata()
    color_count = defaultdict(int)
    TRANSPARENT_COLOR = (-1, -1, -1)  # Unique identifier for fully transparent pixels

    for pixel in pixels:
        if len(pixel) == 4:  # RGBA format
            r, g, b, a = pixel
            if a < 16:  # Treat as fully transparent
                color_count[TRANSPARENT_COLOR] += 1
            else:  # Treat as regular color
                color_count[(r, g, b)] += 1
        else:  # RGB format
            color_count[pixel] += 1

    total_pixels = img.width * img.height
    color_percentage = {color: (count / total_pixels) * 100 for color, count in color_count.items()}

    # Sort the colors by frequency in descending order
    sorted_color_data = sorted(color_count.items(), key=lambda item: item[1], reverse=True)

    # Create a list of colors with count and percentage
    color_data_list = [{'color': color, 'count': count, 'percentage': color_percentage[color]} 
                        for color, count in sorted_color_data]

    # Slice the list if colors_used is greater than 0
    if colors_used > 0:
        color_data_list = color_data_list[:colors_used]

    ###save the images###
    os.makedirs('saved', exist_ok=True)
    # Format the datetime as a string for the filename
    datetime_string = datetime.now().strftime('%Y%m%d_%H%M%S')
    # Construct the filename with directory
    filename = generate_filename(f'saved/{datetime_string}.png')
    # Save the image
    img.save(filename, 'PNG')

    return color_data_list

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
    return render_template('analysis.html')

#-------------------------------------------------------------------
# api routes
#-------------------------------------------------------------------

@app.route('/rugcolor/analyze', methods=['GET','POST'])
def analyze():
    try:
        image_file = request.files['image']
        colors_used = int(request.form.get('colorsUsed', 0))

        if image_file:
            image_stream = io.BytesIO(image_file.read())
            with Image.open(image_stream) as image:
                color_data = analyze_image_colors(image, colors_used)
                return jsonify(color_data)
        else:
            return jsonify({"error": "No image provided"}), 400

    except Exception as e:
        app.logger.error('Error during image analysis: %s', e, exc_info=True)
        return jsonify({"error": "Server error during image analysis"}), 500

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

@app.errorhandler(429)
def ratelimit_handler(e):
    message_title = '429 Rate Limit'
    message_content = '<p>You have exceeded the request rate limit. </p><P>redirecting in 3 seconds...</p>'
    return render_template('redirect.html', message_title=message_title, message_content=message_content), 429

#-------------------------------------------------------------------

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    host = os.environ.get('HOST')
    port = int(os.environ.get('PORT'))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    app.debug = debug
    app.run(host=host, port=port)