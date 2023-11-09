import os
from PIL import Image

def generate_thumbnail(image_path, thumbnail_path, size=(128, 128)):
    with Image.open(image_path) as img:
        img.thumbnail(size)
        img.save(thumbnail_path)

def check_all_thumbnails(dir_path, safe_extensions={'png', 'jpg', 'jpeg', 'bmp'}):
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

            if not os.path.exists(thumbnail_path):
                generate_thumbnail(image_path, thumbnail_path)

        # Remove thumbnails without a parent image
        for thumbnail in existing_thumbnails:
            if thumbnail not in parent_images:
                os.remove(os.path.join(thumbnail_directory, thumbnail))

        # Delete the thumbnail directory if empty
        if os.path.exists(thumbnail_directory) and not parent_images:
            os.rmdir(thumbnail_directory)

# Usage
check_all_thumbnails('img/')
