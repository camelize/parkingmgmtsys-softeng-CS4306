#Jessy Henry Quevedo

import cv2

# Which (camera or video, function helps video feed)
'''cap = cv2.VideoCapture("https://192.168.7.253:8080/video")'''
cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)

# Checks function will return a bool
print(cap.isOpened())

# Set frame width(3) and height(4)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

count = 0

while cap.isOpened():

    # Capture frames from capture device saves it in variable "frame"
    ret, frame = cap.read()

    # Frame limit
    if not ret:
        break

    # Changes color of frame
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # Remove noise in frame
    blur = cv2.GaussianBlur(gray, (5, 5), 0)

    # Highlight plate edges in frame
    edges = cv2.Canny(blur, 100, 200)

    # Flips camera (frame, position)
    '''mirror = cv2.flip(gray, -1)'''

    # Display frame in a window ('window name', variable)
    cv2.imshow('frame', gray)

    # Wait for user input if q
    if cv2.waitKey(1) == ord('q'):
        break

    #path set to local folder
    path = 'frames/frame' + str(count) + '.jpg'

    # Save image in fram.jpg (file name, frame)
    cv2.imwrite(path, edges)
    count += 1

# Release camera
cap.release()

# Close all windows opened
cv2.destroyAllWindows()