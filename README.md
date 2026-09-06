# Dino Vision Bot

Hey there, I'm Mariu! I'm a mechatronics engineering student, so I usually spend my time messing with ESP32s, designing PCBs in KiCad, or 3D printing hydraulic robotic arms. Pure software isn't really my main thing, but I wanted to see if I could build a bot that actually "sees" the screen and plays the hidden Chrome/Brave Dinosaur game using computer vision.

Instead of taking the easy route (like hacking the browser memory or injecting JavaScript), this bot looks at the pixels on your screen and triggers hardware-level keyboard inputs, just like a real player.

You can grab the code and try it out. I built and tested this on the Brave browser (`brave://dino/`), but it works perfectly fine on Chrome or Edge if you set up the vision window right.

## How It Works

I tried to keep the logic as practical as possible without overcomplicating the math:

* **Fast Eyes:** I used the `mss` library to take screenshots. It's incredibly fast and has almost zero lag compared to standard Python tools.
* **Surviving Day/Night:** The game randomly inverts colors. To keep the bot from going blind when the sky turns black, it constantly calculates the background color on the fly. Obstacles always stay highly visible.
* **Smart Vision:** The bot filters out the tiny dust particles the dino kicks up. Also, if two cacti spawn super close to each other, the bot groups them into one big block so it knows to hold the jump button longer.
* **Dodging High Birds:** The bot finds the center of every object. If that center is above an adjustable red line, it realizes it's a high-flying bird and just runs right under it.
* **Zero-Lag Jumps:** Normal Python keyboard libraries have a slight delay, which gets you killed at high speeds. I bypassed them to send the spacebar signal directly to the Windows hardware for instant reflexes.
* **Speed Adaptation:** The bot calculates how fast the game is moving. As the game speeds up, it automatically starts its jumps earlier to compensate.

## Requirements

Just install Python and these three libraries:

```bash
pip install opencv-python mss numpy

```

## Controls & Setup

**Hotkeys:**

* **`E`** : Toggle between Edit Mode (green setup window) and Play Mode.
* **`ENTER`** : Start the bot.
* **`ESC`** : Close the script.
* **`UP / DOWN ARROWS`** : Move the red bird-filtering line (only works in Edit Mode).

**How to Calibrate (Very Important):**
You have to align the bot's "eyes" correctly in **Edit Mode** before pressing play:

1. Drag the main **Green Box** over the game area.
2. The **LEFT edge** of the **Yellow Box** (the radar) must sit perfectly on the tip of the dinosaur's nose.
3. The **BOTTOM edge** of the yellow box needs to sit exactly on the ground line.
4. Stretch the right edge out so it can see 4-5 cacti ahead.
5. Use your UP/DOWN arrows to place the **Red Line** right below the dino's head.

## Tweaking the Jumps

If your monitor or PC has slightly different latency, you might need to adjust the reflexes. In the code, look for the `bot()` function and the **JUMP SETTINGS** block:

* `base_dist`: Controls **WHEN** to jump. Increase it to jump earlier.
* `jump_duration`: Controls **HOW LONG** to hold Space.
* `speed_factor`: Increase this if the bot starts crashing only at extreme speeds (score 2000+).

---

Special thanks to Gemini AI for helping me put the code together (again, I'm a mechatronics engineer, not a software dev!).
