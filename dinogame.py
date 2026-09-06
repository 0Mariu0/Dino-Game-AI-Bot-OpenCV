import time
import ctypes       # Used to interact directly with the Windows API (hardware keyboard, window styles)
import threading    # Allows the bot logic to run in the background without freezing the UI
import cv2          # OpenCV: The core computer vision library used for image processing
import mss          # Extremely fast screen capturing library (better than pyautogui/ImageGrab)
import numpy as np  # Used for high-speed matrix/array calculations on the screen pixels
import tkinter as tk # Built-in Python library for creating the graphical user interface (GUI)

# ============================================================
# DEBUG SETTINGS & SPEED OPTIMIZATION
# ============================================================
DEBUG_MODE = True # If True, opens a secondary window showing the bot's computer vision output

# Hardware Keyboard Functions (0 latency to bypass standard pyautogui lag)
VK_SPACE = 0x20 # Virtual-Key code for the SPACE bar in Windows

def press_space():
    # Simulates a direct hardware-level key press for SPACE down (0 latency)
    ctypes.windll.user32.keybd_event(VK_SPACE, 0, 0, 0)

def release_space():
    # Simulates a direct hardware-level key release for SPACE up. 
    # '2' represents the KEYEVENTF_KEYUP flag in Windows API.
    ctypes.windll.user32.keybd_event(VK_SPACE, 0, 2, 0)

def press_space_once():
    # Used only for the initial game start to trigger the first jump
    press_space()
    time.sleep(0.05)
    release_space()

# ============================================================
# MAIN VISION FRAME SETTINGS
# ============================================================
# Initial coordinates (X, Y) and dimensions (Width, Height) of the main green overlay window
INITIAL_X = 450
INITIAL_Y = 220
INITIAL_W = 900
INITIAL_H = 120

# Limits to prevent the user from making the green window too small to function
MIN_FRAME_W = 300
MIN_FRAME_H = 70
# Size of the interactive corner handles used for resizing the windows
HANDLE_SIZE = 16 

# ============================================================
# DETECTION WINDOW (The Yellow Radar Box)
# ============================================================
# Initial coordinates (relative to the green box) and size for the yellow detection area
DETECT_X = 180
DETECT_Y = 40
DETECT_W = 300 
DETECT_H = 50

# Limits to prevent the yellow radar from becoming too small
MIN_DETECT_W = 50
MIN_DETECT_H = 30

# ============================================================
# DETECTION SETTINGS & BOT BEHAVIOR
# ============================================================
# Minimum dimensions (in pixels) for an object to be considered an obstacle (filters out tiny dust/noise)
MIN_OBJECT_WIDTH = 10  
MIN_OBJECT_HEIGHT = 8 
# Main loop delay - bot takes a new screenshot and calculates math every 5 milliseconds (200 FPS)
SCAN_DELAY = 0.005      

# ============================================================
# GLOBAL STATE VARIABLES
# ============================================================
running = True             # Keeps the entire Python application alive
bot_running = False        # Toggles the actual jumping logic on/off
debug_window_created = False # Tracks if the OpenCV debug window has been initialized

# ============================================================
# OVERLAY CLASS (Handles UI, drawing, dragging, and resizing)
# ============================================================
class Overlay:
    def __init__(self):
        self.root = tk.Tk()
        # Removes standard Windows borders, title bar, and close buttons
        self.root.overrideredirect(True)
        # Forces the window to always stay on top of the browser
        self.root.attributes("-topmost", True)
        self.root.configure(bg="black")

        # Magic trick: Tells Windows to make all "black" pixels in this window fully transparent
        try:
            self.root.wm_attributes("-transparentcolor", "black")
        except tk.TclError:
            pass # Failsafe just in case the OS doesn't support transparency

        # Store current positions and dimensions
        self.x = INITIAL_X
        self.y = INITIAL_Y
        self.w = INITIAL_W
        self.h = INITIAL_H

        self.detect_x = DETECT_X
        self.detect_y = DETECT_Y
        self.detect_w = DETECT_W
        self.detect_h = DETECT_H

        self.edit_mode = True # Starts in Edit Mode so you can position the windows
        self.flash_until = 0  # Timer used to make the screen flash red when an obstacle is seen
        
        # Initial position of the red line (35% down from the top of the yellow box)
        self.red_line_percent = 0.35 

        # Variables to track mouse states for dragging and resizing the UI
        self.dragging_frame = False
        self.dragging_detection = False
        self.resizing_frame = False
        self.resizing_detection = False
        self.resize_target = None
        self.resize_corner = None

        self.start_mouse_x = 0
        self.start_mouse_y = 0
        self.start_x = 0
        self.start_y = 0

        # Create the canvas where all lines, text, and boxes will be drawn
        self.canvas = tk.Canvas(self.root, width=self.w, height=self.h, bg="black", highlightthickness=0)
        self.canvas.pack()

        self.update_geometry()

        # Mouse event bindings (click, drag, release) for interacting with the UI
        self.canvas.bind("<ButtonPress-1>", self.mouse_down)
        self.canvas.bind("<B1-Motion>", self.mouse_move)
        self.canvas.bind("<ButtonRelease-1>", self.mouse_up)

        # Global Keyboard bindings for controlling the application states
        self.root.bind("<Return>", self.toggle_play)  # ENTER starts the bot
        self.root.bind("e", self.toggle_edit)         # E stops the bot and allows editing
        self.root.bind("E", self.toggle_edit)
        self.root.bind("<Escape>", self.close)        # ESC kills the entire script
        
        # Key binds to manually adjust the red bird-filtering line up and down
        self.root.bind("<Up>", self.move_line_up)
        self.root.bind("<Down>", self.move_line_down)

        # Start the continuous UI rendering loop
        self.draw()

    def update_geometry(self):
        # Applies the calculated Width, Height, X, and Y to the actual Windows window
        self.root.geometry(f"{int(self.w)}x{int(self.h)}+{int(self.x)}+{int(self.y)}")
        self.canvas.config(width=int(self.w), height=int(self.h))

    def move_line_up(self, event=None):
        # Moves the red line up by decreasing the percentage (max 10% from the top)
        if self.edit_mode:
            self.red_line_percent = max(0.1, self.red_line_percent - 0.05)
            
    def move_line_down(self, event=None):
        # Moves the red line down by increasing the percentage (max 90% to the bottom)
        if self.edit_mode:
            self.red_line_percent = min(0.9, self.red_line_percent + 0.05)

    def get_frame_corner(self, mx, my):
        # Mathematical check to see if the mouse click (mx, my) is on one of the 4 green corners
        hit = HANDLE_SIZE * 1.5 
        if mx <= hit and my <= hit: return "NW"
        if mx >= self.w - hit and my <= hit: return "NE"
        if mx <= hit and my >= self.h - hit: return "SW"
        if mx >= self.w - hit and my >= self.h - hit: return "SE"
        return None

    def get_detection_corner(self, mx, my):
        # Mathematical check to see if the mouse click is on one of the 4 yellow corners
        hit = HANDLE_SIZE * 1.5
        x1 = self.detect_x
        y1 = self.detect_y
        x2 = self.detect_x + self.detect_w
        y2 = self.detect_y + self.detect_h

        if abs(mx - x1) <= hit and abs(my - y1) <= hit: return "NW"
        if abs(mx - x2) <= hit and abs(my - y1) <= hit: return "NE"
        if abs(mx - x1) <= hit and abs(my - y2) <= hit: return "SW"
        if abs(mx - x2) <= hit and abs(my - y2) <= hit: return "SE"
        return None

    def mouse_down(self, event):
        # Triggered when left mouse button is pressed. Records starting coordinates for dragging logic.
        if not self.edit_mode: return
        mx, my = event.x, event.y
        self.start_mouse_x, self.start_mouse_y = event.x_root, event.y_root
        
        self.start_x, self.start_y = self.x, self.y
        self.start_w, self.start_h = self.w, self.h
        self.start_detect_x, self.start_detect_y = self.detect_x, self.detect_y
        self.start_detect_w, self.start_detect_h = self.detect_w, self.detect_h

        # Determine if we are clicking a radar corner, dragging the radar, or resizing the main frame
        corner = self.get_detection_corner(mx, my)
        if corner == "NW": 
            self.dragging_detection = True
            return
        elif corner: 
            self.resizing_detection = True
            self.resize_target, self.resize_corner = "detection", corner
            return

        corner = self.get_frame_corner(mx, my)
        if corner == "NW": 
            self.dragging_frame = True
            return
        elif corner: 
            self.resizing_frame = True
            self.resize_target, self.resize_corner = "frame", corner
            return

    def mouse_move(self, event):
        # Triggered while holding left click and moving the mouse. Updates dimensions/positions dynamically.
        if not self.edit_mode: return
        # Calculate how far the mouse has moved since the click started
        dx = event.x_root - self.start_mouse_x
        dy = event.y_root - self.start_mouse_y

        if self.dragging_frame:
            self.x, self.y = self.start_x + dx, self.start_y + dy
            self.update_geometry()
            return

        if self.dragging_detection:
            # Prevents the yellow box from being dragged outside the green box
            new_x = max(0, min(self.start_detect_x + dx, self.w - self.detect_w))
            new_y = max(0, min(self.start_detect_y + dy, self.h - self.detect_h))
            self.detect_x, self.detect_y = new_x, new_y
            return

        # Complex math to handle resizing from different corners (NE, SW, SE)
        if self.resizing_frame:
            corner = self.resize_corner
            if corner == "NE":
                new_w, new_h = self.start_w + dx, self.start_h - dy
                if new_w >= MIN_FRAME_W: self.w = new_w
                if new_h >= MIN_FRAME_H: self.y, self.h = self.start_y + dy, new_h
            elif corner == "SW":
                new_w, new_h = self.start_w - dx, self.start_h + dy
                if new_w >= MIN_FRAME_W: self.x, self.w = self.start_x + dx, new_w
                if new_h >= MIN_FRAME_H: self.h = new_h
            elif corner == "SE":
                new_w, new_h = self.start_w + dx, self.start_h + dy
                if new_w >= MIN_FRAME_W: self.w = new_w
                if new_h >= MIN_FRAME_H: self.h = new_h

            # Ensures the yellow box stays inside the green box if the green box shrinks
            self.detect_x = max(0, min(self.detect_x, self.w - self.detect_w))
            self.detect_y = max(0, min(self.detect_y, self.h - self.detect_h))
            self.update_geometry()
            return

        if self.resizing_detection:
            corner = self.resize_corner
            if corner == "NE":
                new_w, new_h = self.start_detect_w + dx, self.start_detect_h - dy
                if new_w >= MIN_DETECT_W: self.detect_w = min(new_w, self.w - self.detect_x)
                if new_h >= MIN_DETECT_H: self.detect_y, self.detect_h = max(0, self.start_detect_y + dy), new_h
            elif corner == "SW":
                new_w, new_h = self.start_detect_w - dx, self.start_detect_h + dy
                if new_w >= MIN_DETECT_W: self.detect_x, self.detect_w = max(0, self.start_detect_x + dx), new_w
                if new_h >= MIN_DETECT_H: self.detect_h = min(new_h, self.h - self.detect_y)
            elif corner == "SE":
                new_w, new_h = self.start_detect_w + dx, self.start_detect_h + dy
                if new_w >= MIN_DETECT_W: self.detect_w = min(new_w, self.w - self.detect_x)
                if new_h >= MIN_DETECT_H: self.detect_h = min(new_h, self.h - self.detect_y)

    def mouse_up(self, event):
        # Resets all tracking variables when the left mouse button is released
        self.dragging_frame = self.dragging_detection = False
        self.resizing_frame = self.resizing_detection = False
        self.resize_target = None
        self.resize_corner = None

    def draw(self):
        # Clears the entire canvas to redraw it for the next frame (Animation loop)
        self.canvas.delete("all")
        
        # Calculate exact Y pixel coordinate of the red line based on its percentage
        red_line_y_pos = self.detect_y + int(self.detect_h * self.red_line_percent)

        if self.edit_mode:
            # Draw Main Frame (Green) and instructional text
            self.canvas.create_rectangle(2, 2, self.w - 2, self.h - 2, outline="#00ff66", width=3)
            self.canvas.create_text(10, 8, text="VISION - EDIT MODE", anchor="nw", fill="#00ff66", font=("Consolas", 11, "bold"))
            self.canvas.create_text(10, 25, text="Press UP/DOWN ARROWS to move the red line", anchor="nw", fill="#00ff66", font=("Consolas", 9))
            self.canvas.create_text(self.w - 10, 8, text="ENTER = PLAY", anchor="ne", fill="#00ff66", font=("Consolas", 11, "bold"))
            
            # Draw Detection Radar (Yellow)
            self.canvas.create_rectangle(self.detect_x, self.detect_y, self.detect_x + self.detect_w, self.detect_y + self.detect_h, outline="#ffff00", width=3)
            
            # Draw Red Line (Bird Filter) - uses 'dash' to make it dotted
            self.canvas.create_line(self.detect_x, red_line_y_pos, self.detect_x + self.detect_w, red_line_y_pos, fill="red", dash=(4, 4), width=2)

            # Draw the little interactive squares on the corners for resizing
            s = HANDLE_SIZE
            corners = [
                (self.detect_x - s//2, self.detect_y - s//2), 
                (self.detect_x + self.detect_w - s//2, self.detect_y - s//2),
                (self.detect_x - s//2, self.detect_y + self.detect_h - s//2), 
                (self.detect_x + self.detect_w - s//2, self.detect_y + self.detect_h - s//2)
            ]
            for hx, hy in corners:
                self.canvas.create_rectangle(hx, hy, hx + s, hy + s, fill="#ffff00", outline="#ffff00")

            frame_corners = [(2, 2), (self.w - s - 2, 2), (2, self.h - s - 2), (self.w - s - 2, self.h - s - 2)]
            for hx, hy in frame_corners:
                self.canvas.create_rectangle(hx, hy, hx + s, hy + s, fill="#00ff66", outline="#00ff66")

        else:
            # PLAY MODE UI
            self.canvas.create_rectangle(2, 2, self.w - 2, self.h - 2, outline="#00ff66", width=3)
            
            # Dynamic color change: If flash_until timer is active, turn the yellow box red
            detection_color = "#ff2020" if time.time() < self.flash_until else "#ffff00"
            
            # Flash UI red when obstacle is detected (draws a thicker red outline outside the normal box)
            if time.time() < self.flash_until:
                self.canvas.create_rectangle(self.detect_x - 5, self.detect_y - 5, self.detect_x + self.detect_w + 5, self.detect_y + self.detect_h + 5, outline="#ff2020", width=5)
            self.canvas.create_rectangle(self.detect_x, self.detect_y, self.detect_x + self.detect_w, self.detect_y + self.detect_h, outline=detection_color, width=2)
            
            self.canvas.create_line(self.detect_x, red_line_y_pos, self.detect_x + self.detect_w, red_line_y_pos, fill="red", dash=(4, 4), width=2)

            if time.time() < self.flash_until:
                self.canvas.create_text(self.w // 2, 12, text="OBSTACLE DETECTED", fill="#ff3030", font=("Consolas", 14, "bold"))
            else:
                self.canvas.create_text(10, 8, text="VISION - PLAY MODE\nPress 'E' for Edit / 'ESC' to Exit", anchor="nw", fill="#00ff66", font=("Consolas", 10, "bold"))
        
        # Schedule this draw function to run again in 30 milliseconds (creates a ~33 FPS animation loop for UI)
        self.root.after(30, self.draw)

    def obstacle(self):
        # Triggers the visual flash logic by setting a future timestamp (current time + 0.18 seconds)
        self.flash_until = time.time() + 0.18

    def toggle_play(self, event=None):
        global bot_running
        if self.edit_mode:
            self.edit_mode = False
            make_click_through(self.root) # Locks the window so you can click the browser through it
            bot_running = True
            # Starts the actual bot logic in a separate CPU thread so it doesn't freeze the UI
            threading.Thread(target=bot, daemon=True).start()

    def toggle_edit(self, event=None):
        global bot_running
        if not self.edit_mode:
            bot_running = False
            restore_clickable(self.root) # Unlocks the window so you can drag it again
            self.edit_mode = True

    def close(self, event=None):
        global running, bot_running
        running = bot_running = False # Flags all loops to terminate
        self.root.destroy() # Kills the Tkinter window

# ============================================================
# WINDOWS CLICK-THROUGH API INTEGRATION (Ghost Window Logic)
# ============================================================
def make_click_through(window):
    # Gets the low-level Windows Handle (HWND) for our python GUI window
    hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
    # Reads the current Extended Window Styles (GWL_EXSTYLE is -20)
    style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
    # Applies WS_EX_LAYERED (0x00080000) and WS_EX_TRANSPARENT (0x00000020) via bitwise OR.
    # This combination forces Windows OS to completely ignore mouse events on this window.
    ctypes.windll.user32.SetWindowLongW(hwnd, -20, style | 0x00080000 | 0x00000020)

def restore_clickable(window):
    hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
    style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
    # Removes the WS_EX_TRANSPARENT flag using bitwise AND NOT (~), making the window clickable again
    ctypes.windll.user32.SetWindowLongW(hwnd, -20, style & ~0x00000020)

# Initialize the blazing fast MSS screen capturer
sct = mss.MSS() 

# ============================================================
# COMPUTER VISION & DETECTION LOGIC
# ============================================================
def detect_obstacles():
    global debug_window_created
    # Define exact screen region to capture based on the yellow box's absolute screen coordinates
    monitor = {
        "left": int(overlay.x + overlay.detect_x),
        "top": int(overlay.y + overlay.detect_y),
        "width": int(overlay.detect_w),
        "height": int(overlay.detect_h)
    }

    # Grab screen raw data and convert it into a NumPy array, then to Grayscale for faster processing
    screenshot = np.array(sct.grab(monitor))
    gray = cv2.cvtColor(screenshot, cv2.COLOR_BGRA2GRAY)

    # Bulletproof Day/Night processing (Median subtraction)
    # 1. Calculates the MEDIAN pixel brightness. Because the background takes up most of the space, 
    #    the median value will perfectly represent the background color, whether it's white (day) or black (night).
    bg_color = int(np.median(gray))
    # 2. Creates a fake "empty sky" image entirely filled with that background color
    bg_matrix = np.full_like(gray, bg_color)
    # 3. Mathematically subtracts the current frame from the empty sky frame.
    #    This isolates ONLY the things that are different from the background (cacti, birds, stars).
    diff = cv2.absdiff(gray, bg_matrix)
    
    # Threshold creates a high-contrast binary (black/white) image.
    # Any difference > 30 becomes pure white (255), everything else becomes pure black (0).
    _, threshold = cv2.threshold(diff, 30, 255, cv2.THRESH_BINARY)

    # Morphological OPEN (Erosion followed by Dilation):
    # Melts away tiny white pixels (like 3x3 pixel stars or dust) that passed the threshold.
    kernel_clean = np.ones((3, 3), np.uint8)
    threshold = cv2.morphologyEx(threshold, cv2.MORPH_OPEN, kernel_clean)

    # Morphological CLOSE (Dilation followed by Erosion):
    # Smudges white objects horizontally. If two cacti are very close, this bridges the 15-pixel gap 
    # between them so the computer sees them as one solid object.
    kernel_bridge = np.ones((3, 15), np.uint8) 
    threshold = cv2.morphologyEx(threshold, cv2.MORPH_CLOSE, kernel_bridge)

    if DEBUG_MODE:
        # Handles the rendering of the secondary OpenCV visualizer window
        if not debug_window_created:
            cv2.namedWindow("Debug - Vision", cv2.WINDOW_NORMAL)
            cv2.resizeWindow("Debug - Vision", 400, 200)
            cv2.setWindowProperty("Debug - Vision", cv2.WND_PROP_TOPMOST, 1)
            debug_window_created = True
        cv2.imshow("Debug - Vision", threshold)
        cv2.waitKey(1)

    # Find the outlines (contours) of all the remaining white shapes in the threshold image
    contours, _ = cv2.findContours(threshold, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Calculate absolute Y pixel position of the red line
    red_line_y = int(monitor["height"] * overlay.red_line_percent)
    
    valid_obstacles = []

    for contour in contours:
        # Get bounding box (x, y, width, height) for each found shape
        x, y, w, h = cv2.boundingRect(contour)
        
        # GHOST FILTER: Ignore shapes that are too small, or MASSIVELY wide (like a cloudy sky transition error > 140px)
        if w < MIN_OBJECT_WIDTH or h < MIN_OBJECT_HEIGHT or w > 140:
            continue

        center_y = y + (h // 2)
        bottom_y = y + h

        # PIXEL DENSITY FILTER: Checks inside the bounding box. If less than 20% of it is solid white,
        # it's just random scattered noise, not a real cactus.
        roi = threshold[y:y+h, x:x+w]
        if cv2.countNonZero(roi) / (w * h) < 0.20:
            continue

        # HIGH BIRD FILTER: If the physical center of the object is ABOVE the red line, it's a high bird. Ignore it.
        if center_y < red_line_y:
            continue
            
        # MEDIUM/LOW BIRD DETECTOR: Checks if the bottom of the object is floating more than 12 pixels above the ground
        is_bird = bottom_y < (monitor["height"] - 12)
        valid_obstacles.append((x, w, is_bird))

    # Sort obstacles from left to right so the bot always reacts to the closest one first
    valid_obstacles.sort(key=lambda item: item[0])
    return valid_obstacles

# ============================================================
# BOT LOGIC & JUMP PHYSICS
# ============================================================
def bot():
    global last_jump, debug_window_created
    print("Bot starting in 1 second...")
    time.sleep(1)
    
    press_space_once() # Trigger the game to start
    time.sleep(0.5)

    smooth_speed = 350.0 # Initial guess of game speed (pixels per second)
    last_obs_x = None    # Tracks previous position of obstacle to calculate speed
    last_time = time.time()
    last_jump = 0        # Timestamp of the last time we jumped
    
    is_space_pressed = False
    release_time = 0

    while running and bot_running:
        current_time = time.time()
        
        # Hardware keybind checks for Exit(ESC) / Edit(E) during gameplay
        # GetAsyncKeyState reads the physical keyboard state directly from the motherboard. 
        # 0x8000 is the bitmask verifying the key is currently held down.
        if ctypes.windll.user32.GetAsyncKeyState(0x1B) & 0x8000:
            overlay.root.after(0, overlay.close)
            break
        if ctypes.windll.user32.GetAsyncKeyState(0x45) & 0x8000:
            overlay.root.after(0, overlay.toggle_edit)
            time.sleep(0.3) # Debounce to prevent multiple toggles
            break
        
        # Asynchronously release SPACE key if jump duration is over
        if is_space_pressed and current_time >= release_time:
            release_space()
            is_space_pressed = False

        obstacles = detect_obstacles()
        
        if len(obstacles) > 0:
            obs_x, obs_w, is_bird = obstacles[0]
            
            # CLUSTER CALCULATION: Groups close obstacles into one massive "effective width"
            effective_w = obs_w
            cluster_has_bird = is_bird
            for i in range(1, len(obstacles)):
                next_x, next_w, next_is_bird = obstacles[i]
                # If the gap between obstacles is < 70 pixels, merge them mathmetically
                # MODIFIABLE: Change '70' to adjust cluster grouping tolerance
                if next_x - (obs_x + effective_w) < 70: 
                    effective_w = (next_x + next_w) - obs_x
                    if next_is_bird: cluster_has_bird = True
                else:
                    break

            # SPEED CALCULATION: Extremely filtered to ignore system lag/stutters
            if last_obs_x is not None and obs_x < last_obs_x:
                dx = last_obs_x - obs_x
                dt = current_time - last_time
                # Only trust the time delta if it's within a normal frame range (0.01s to 0.1s).
                # If the OS stutters for 0.5s, the speed calculation is ignored to prevent panic jumps.
                if 0.01 < dt < 0.1: 
                    inst_speed = dx / dt
                    # Only accept realistic speeds (between 200 and 2000 pixels/sec)
                    if 200 < inst_speed < 2000: 
                        # EXPONENTIAL MOVING AVERAGE: Takes 95% of the historic speed and only 5% of the new speed.
                        # This creates an incredibly smooth and stable speed value that doesn't spike.
                        smooth_speed = (smooth_speed * 0.95) + (inst_speed * 0.05)
            
            last_obs_x = obs_x
            last_time = current_time
            
            # ==========================================================
            # JUMP SETTINGS: MODIFY THESE VALUES TO TWEAK BOT'S REFLEXES
            # ==========================================================
            # base_dist = Distance in pixels from the left where panic triggers (Higher = Jumps earlier)
            # jump_duration = Seconds to hold SPACE down (Higher = Longer float in the air)
            
            if cluster_has_bird:
                # Target includes a medium bird
                base_dist = 70        
                jump_duration = 0.25  
            elif effective_w > 65:
                # Large groups (3-4 cacti)
                base_dist = 60      
                jump_duration = 0.25  
            elif effective_w > 50:
                # Medium groups (2-3 cacti)
                base_dist = 50
                jump_duration = 0.18  
            elif effective_w > 20:
                # One wide cactus or small group
                base_dist = 40
                jump_duration = 0.02  # Short tap to land fast
            else:
                # Single small cactus
                base_dist = 30      
                jump_duration = 0.02  # Instant tap, immediate landing
                
            # Internal cooldown to prevent spamming jumps mid-air (duration + 20ms buffer)
            current_cooldown = jump_duration + 0.02 

            # SPEED MULTIPLIER: Increases panic_dist dynamically as the game gets faster.
            # Normalizes speed between 300 and 1200 into a 0.0 to 1.0 factor.
            # MODIFIABLE: Increase the '115' if bot hits objects at very high speeds.
            speed_factor = max(0.0, min((smooth_speed - 300) / 900.0, 1.0)) 
            panic_dist = base_dist + (speed_factor * 115) 
            
            # TRIGGER THE JUMP if the object crosses the panic threshold
            if obs_x <= panic_dist:
                # Verify we aren't already jumping
                if current_time - last_jump >= current_cooldown:
                    overlay.obstacle()
                    
                    if not is_space_pressed:
                        press_space() # Hardware key down
                        is_space_pressed = True
                        
                    release_time = current_time + jump_duration
                    last_jump = current_time
                    last_obs_x = None 
        else:
            # Memory wipe delay if the screen is empty (prevents negative speed bugs when a new cactus spawns)
            if current_time - last_time > 0.15:
                last_obs_x = None
                
        time.sleep(SCAN_DELAY) # Rest CPU

    # Failsafe release in case the bot is stopped while mid-air
    if is_space_pressed:
        release_space()
        
    if DEBUG_MODE:
        try:
            cv2.destroyAllWindows()
        except:
            pass
        debug_window_created = False

# ============================================================
# APPLICATION START
# ============================================================
if __name__ == "__main__":
    overlay = Overlay()
    overlay.root.mainloop()
