from PIL import Image, ImageDraw

# Create a new image with a blue background (32x32 is standard favicon size)
img = Image.new('RGB', (32, 32), color='#0d6efd')
draw = ImageDraw.Draw(img)

# Save as ICO file
img.save('static/favicon.ico')
