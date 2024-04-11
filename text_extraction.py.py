import cv2
import pytesseract
from picamera2 import MappedArray, Picamera2, Preview
import time
import threading
from datetime import datetime
import sqlite3
import os

# Connect to SQLite database
conn = sqlite3.connect('captured_data.db')
c = conn.cursor()

# Create table if not exists
c.execute('''CREATE TABLE IF NOT EXISTS capture_data
             (timestamp TEXT, Box1 TEXT, Box2 TEXT, Box3 TEXT)''')


# Initialize Picamera2
picam2 = Picamera2()
picam2.configure(picam2.create_preview_configuration({"size": (800, 768)}))
picam2.start_preview(Preview.QTGL)
picam2.start()


# Function to read coordinates from a text file
def read_coordinates(file_path):
    coordinates = []
    with open(file_path, 'r') as file:
        for line in file:
            parts = line.strip().split(',')
            if len(parts) == 5:  # Added an extra part for box name
                name, x, y, w, h = parts
                coordinates.append((name, int(x), int(y), int(w), int(h)))
    return coordinates


# Function to write coordinates to a text file
def write_coordinates(file_path, coordinates):
    with open(file_path, 'a') as file:
        for coord in coordinates:
            file.write(','.join(map(str, coord)) + '\n')

# Read coordinates from the text file
coordinates = read_coordinates('coordinates.txt')

# Mouse event handling functions
drawing = False  # True if mouse is pressed
ix, iy = -1, -1
box_count = len(coordinates) + 1  # Start counting boxes from the existing count


def draw_rectangle(event, x, y, flags, param):
    global ix, iy, drawing, box_count, image

    if event == cv2.EVENT_LBUTTONDOWN:
        drawing = True
        ix, iy = x, y

    elif event == cv2.EVENT_MOUSEMOVE:
        if drawing:
            # Make a copy of the original image
            image = array.copy()
            # Draw all previously defined boxes
            for (name, x1, y1, w1, h1) in coordinates:
                cv2.rectangle(image, (x1, y1), (x1 + w1, y1 + h1), (0, 255, 0), 2)
                cv2.putText(image, name, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
            # Draw rectangle from initial (ix,iy) to current (x,y) position
            cv2.rectangle(image, (ix, iy), (x, y), (0, 255, 0), 2)
            # Show the image with the updated rectangles
            cv2.imshow('image', image)


    elif event == cv2.EVENT_LBUTTONUP:
        if drawing:
            drawing = False
            w, h = x - ix, y - iy
            if w != 0 and h != 0:  # Check if width and height are not zero
                name = 'box{}'.format(box_count)
                coordinates.append((name, ix, iy, w, h))
                write_coordinates('coordinates.txt', [(name, ix, iy, w, h)])
                box_count += 1

cv2.namedWindow('image')
cv2.setMouseCallback('image', draw_rectangle)


# Function to extract text from ROI and print it
def extract_and_print_text(name, x, y, w, h, array, data_list):
    roi = array[y:y+h, x:x+w]
    text = pytesseract.image_to_string(roi)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if text.strip() and text.strip().isprintable():  # Check if text is printable and non-empty
        data_list.append((name, text.strip(), timestamp))  # Append data with timestamp to the list


# Ensure the output directory exists
output_dir = '/home/sandip/Documents/Anand/image_processing1/whole image'
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# Main loop
while True:
    array = picam2.capture_array()
    image = array.copy()

    # Convert the RGB image to BGR
    bgr_image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

    # Resize the whole image
    resized_image = cv2.resize(bgr_image, (180, 140))  # Resize to desired dimensions

    # Save the resized image without rectangles
    image_filename = f'processed_image_{datetime.now().strftime("%Y%m%d%H%M%S")}.jpg'
    image_path = os.path.join(output_dir, image_filename)
    cv2.imwrite(image_path, resized_image)


    # Draw rectangles on the captured image based on coordinates
    for (name, x, y, w, h) in coordinates:
        cv2.rectangle(bgr_image, (x, y), (x + w, y + h), (0, 255, 0), 2)
        cv2.putText(bgr_image, name, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)

    # Display the image with rectangles
    cv2.imshow('image', bgr_image)

    # Use threading to extract text from each box simultaneously
    threads = []
    data_list = []  # List to store received data from threads
    for (name, x, y, w, h) in coordinates:
        t = threading.Thread(target=extract_and_print_text, args=(name, x, y, w, h, array, data_list))
        threads.append(t)
        t.start()


    # Join all threads to wait for them to complete
    for t in threads:
        t.join()

    # Sort data list based on box names
    data_list.sort(key=lambda x: int(x[0][3:]))


    # Insert data into SQLite database
    if data_list:
        captured_values = {}
        for item in data_list:
            captured_values[item[0]] = item[1]
        c.execute("INSERT INTO capture_data (timestamp, Box1, Box2, Box3) VALUES (?, ?, ?, ?)",
                  (data_list[0][2], captured_values.get('box1', ''), captured_values.get('box2', ''), captured_values.get('box3', '')))
        conn.commit()


    # Print all received data
    print_empty_line = False
    for item in data_list:
        if item[1].strip() and item[1].strip().isprintable():
            print("Text in {} at {}: {}".format(item[0], item[2], item[1]))
            print_empty_line = True


    # Write received data with timestamp to a text file
    with open('data.txt', 'a') as file:
        for item in data_list:
            if item[1].strip() and item[1].strip().isprintable():
                file.write("Text in {} at {}: {}\n".format(item[0], item[2], item[1]))
        if print_empty_line:
            file.write('\n')  # Add an empty line between each data entry


    # Print an empty line in terminal if valid data was received
    if print_empty_line:
        print()

    # Break the loop if ESC key is pressed
    if cv2.waitKey(1) == 25:
        break

    # Add a delay of 2 seconds
    time.sleep(30)

# Close all OpenCV windows
cv2.destroyAllWindows()

# Close SQLite connection
conn.close()
