import cv2, easyocr, re
import matplotlib.pyplot as plt
from ultralytics import YOLO

#---------- load models ----------

#Detect license plates and cars
#https://huggingface.co/orionwambert/yolov8-license-plate-detection?utm_source=chatgpt.com
license_plate_detector = YOLO('best.pt')



#---------- (camera/video/photo) feed ----------

#cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
#cap = cv2.VideoCapture('video.mp4')
img = cv2.imread("georgia.jpg")



#---------- EasyOCR Setup ----------

#Initialize the OCR reader
reader = easyocr.Reader(['en'], gpu=True)

#States filter
states_set = {
    "ALABAMA", "ALASKA", "ARIZONA", "ARKANSAS", "CALIFORNIA",
    "COLORADO", "CONNECTICUT", "DELAWARE", "FLORIDA", "GEORGIA",
    "HAWAII", "IDAHO", "ILLINOIS", "INDIANA", "IOWA",
    "KANSAS", "KENTUCKY", "LOUISIANA", "MAINE", "MARYLAND",
    "MASSACHUSETTS", "MICHIGAN", "MINNESOTA", "MISSISSIPPI", "MISSOURI",
    "MONTANA", "NEBRASKA", "NEVADA", "NEW HAMPSHIRE", "NEW JERSEY",
    "NEW MEXICO", "NEW YORK", "NORTH CAROLINA", "NORTH DAKOTA", "OHIO",
    "OKLAHOMA", "OREGON", "PENNSYLVANIA", "RHODE ISLAND", "SOUTH CAROLINA",
    "SOUTH DAKOTA", "TENNESSEE", "TEXAS", "UTAH", "VERMONT",
    "VIRGINIA", "WASHINGTON", "WEST VIRGINIA", "WISCONSIN", "WYOMING"
}



#---------- Locate Plate Functions ----------

final_results = {}

# Gives coordinates and index of license plate
def plate_location(results):
    best_box = None
    best_conf = -1
    index = 0

    # Extract detection information
    for i, result in enumerate(results):
        for box in result.boxes:

            # Get class name
            class_name = result.names[int(box.cls[0].item())]

            # Get bounding boxes coordinates
            if class_name == "license-plate":  # only consider license plates
                conf = box.conf[0].item()
                if conf > best_conf:  # keep the most confident
                    best_conf = conf
                    best_box = box.xyxy[0].tolist()  # store coordinates
                    index = i
    return best_box, index

# Crops License plate with coordinates
def crop_plate(coord, image, zoom=2):

    #Extarct coordinates
    x1, y1, x2, y2 = map(int, coord)

    # Crop the license plate from original image
    plate_img = image[y1:y2, x1:x2]

    # Enlarge plate image
    height, width = plate_img.shape[:2]
    plate_img_zoomed = cv2.resize(plate_img,
                                  (width * zoom, height * zoom),
                                  interpolation=cv2.INTER_CUBIC)
    return plate_img_zoomed, [x1, y1, x2, y2]

def read_license_plate(license_plate):
    best_text = None
    best_score = -1

    #Extract texts from license plate
    detections = reader.readtext(license_plate)

    #Look at all text detected
    for detection in detections:
        bbox, text, score = detection

        # Clean up text
        text = re.sub(r'[^A-Z0-9]', '', text.upper())

        #Ensure text is license plate numbers
        if score > best_score and 4 <= len(text) <= 10 and text not in states_set:  # keep the most confident
            best_score = score
            best_text = text

    #Returns plate number that was found
    if best_text is not None:
        return best_text, best_score
    else:
        return None, None

# Start license plate extraction
def extract_plate_text():

    #Read frames from video input
    frame_number = -1
    ret = True
    while ret:
        frame_number += 1
        #ret, frame = cap.read()
        frame = img
        if ret:
            # Array of frames with detected plates
            final_results[frame_number] = {}

            # Detect vehicles and license plates
            detections = license_plate_detector(frame)

            # Retrieve coordinates of license plate
            plate_position, index = plate_location(detections)

            # If a plate was located
            if plate_position is not None:

                # Crop License Plate
                license_plate_crop, plates_xy = crop_plate(plate_position, frame)

                # Process license plate
                license_plate_gray = cv2.cvtColor(license_plate_crop, cv2.COLOR_BGR2GRAY)
                _, plate_thresh = cv2.threshold(license_plate_gray, 100, 255, cv2.THRESH_BINARY_INV)

                # Read license plate number
                license_plate_text, text_conf_score = read_license_plate(plate_thresh)

                # Save information in dictionary
                if license_plate_text is not None:
                    final_results[frame_number] = {'license_plate': {'position': plates_xy,
                                                                     'text': license_plate_text,
                                                                     'txt_score': text_conf_score}}


                #TEST FOR IMAGES
                plt.figure(figsize=(15, 5))  # Set the figure size
                plt.subplot(1, 2, 1)  # 1 row, 2 columns, first subplot
                plt.imshow(license_plate_gray, cmap='gray')
                plt.title('Original')
                plt.axis('off')

                plt.subplot(1, 2, 2)  # 1 row, 2 columns, second subplot
                plt.imshow(plate_thresh, cmap='gray')
                plt.title('Threshold')
                plt.axis('off')
                plt.show()

            ret = False

    print(final_results)

    # Display Plate Detected
    detections[index][index].show()

    # Save results
    #detections[index].save('output.jpg')

    #print(detections[index].names)





#----- MAIN FOR TESTING -------
def main():

    # Extract detection information
    extract_plate_text()

if __name__ == "__main__":
    main()
