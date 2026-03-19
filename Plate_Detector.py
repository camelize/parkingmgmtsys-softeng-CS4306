import cv2, re
import pytesseract
import matplotlib.pyplot as plt

# Path to tesseract executable
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# import function = from Plate_Detector import detect_plate_number
# Detect and print the plate number
def detect_plate_number(image_path):

    # Load the image
    # Check if input is a file path (string)
    if isinstance(image_path, str):
        image = cv2.imread(image_path)  # Reads the image from the specified path
    else:
        image = image_path  # Already an image

    plt.imshow(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    plt.axis('off')
    plt.show()

    # Convert to grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Apply Gaussian Blur to remove noise
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # Edge detection - LOWER thresholds to catch more edges
    edges = cv2.Canny(blurred, 50, 150)

    plt.imshow(cv2.cvtColor(edges, cv2.COLOR_BGR2RGB))
    plt.axis('off')
    plt.show()

    # Find contours to locate the license plate
    contours, _ = cv2.findContours(edges.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Sort contours based on area (descending order), return top 10 contours
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[0:10]

    plate_contour = None
    for contour in contours:
        # Approximate the contour to a polygon
        epsilon = 0.02 * cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, epsilon, True)

        # Check if contour has 4 vertices OR is large enough (your plate has 4 vertices)
        if len(approx) == 4:
            x, y, w, h = cv2.boundingRect(approx)
            aspect_ratio = w / h

            # Ignore contours that are too large (likely the image border)
            img_h, img_w = image.shape[:2]
            if w > 0.9 * img_w or h > 0.9 * img_h:
                continue

            # Accept wider range of aspect ratios (your plate is 1.44)
            if 1.0 < aspect_ratio < 5.0:  # Changed from strict 4 vertices only
                plate_contour = approx
                break

    # If no 4-vertex contour found, try the largest contour
    if plate_contour is None and len(contours) > 0:
        print("No rectangle found, trying largest contour")
        plate_contour = contours[0]

    if plate_contour is not None:
        # Draw a bounding box around the detected license plate
        x, y, w, h = cv2.boundingRect(plate_contour)
        plate_image = gray[y:y + h, x:x + w]

        # Resize the plate image to make text bigger
        plate_image = cv2.resize(plate_image, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)

        # Apply thresholding to binarize the plate area
        _, thresh = cv2.threshold(plate_image, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # Perform OCR - using PSM 7 (grabs text from plate)
        plate_number = pytesseract.image_to_string(
            thresh,
            config='--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
        )

        # Clean up text
        plate_number = plate_number.strip().replace('\x0c', '')
        plate_number = re.sub(r'[^A-Z0-9]', '', plate_number)

        # Display cropped plate
        plt.imshow(plate_image, cmap='gray')
        plt.axis('off')
        plt.show()
    else:
        plate_number = "License plate not detected"

    # Detect and print the plate number
    print("Detected Plate Number:", plate_number)


# Test
image_path = r"coloradoPlate.jpg"   #image path
detect_plate_number(image_path)     #call function
