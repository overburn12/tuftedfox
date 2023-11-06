from PIL import Image
import os

def generate_thumbnails(directory, thumbnail_directory, size=(512, 512)):
    if not os.path.exists(thumbnail_directory):
        os.makedirs(thumbnail_directory)

    for image_name in os.listdir(directory):
        image_path = os.path.join(directory, image_name)
        if os.path.isfile(image_path):
            with Image.open(image_path) as img:
                img.thumbnail(size)
                # Construct the path for the thumbnail
                thumbnail_path = os.path.join(thumbnail_directory, image_name)
                img.save(thumbnail_path)

# Call the function with the path to your images
rugs_folder = 'img/rugs'
thumbnails_folder = 'img/rugs/thumbnails'  # Make sure this directory exists or is created by the script
generate_thumbnails(rugs_folder, thumbnails_folder)
