# README.md
# 🏍️ MotorHUD

MotorHUD puts the next turn and the current speed zone inside your helmet so your eyes stay on the road.  
This repo covers the helmet side. It includes the ESP32 hub firmware, a simple companion app starter, and printable case parts. The speed-sign vision stack now lives in a separate repo named **SudoSpeed**.

---

## What is new in this phase

**Transparent OLEDs**  
The display has moved to transparent OLEDs for better helmet integration and less visual bulk. Rendering is minimal and high contrast for quick glances.

**SudoSpeed integration**  
MotorHUD now listens for zone updates from SudoSpeed running on a Raspberry Pi or laptop. SudoSpeed emits lines like `Z:60` and the ESP32 shows the current zone on the right display.

**New navigation retrieval**  
The companion app now owns routing and re-routing. It pulls Directions from Google, reduces them to the single next instruction, and sends only that short line to the ESP32 over BLE. This keeps Bluetooth traffic light and updates smooth every few seconds.

---

## Repo layout

Your current structure is kept simple.

```
Companion App/            Android starter for BLE and Directions
images/                   All images go here
Case.stl                  ESP32 and powerbank case
display_cover v1.stl      Display cover and helmet mount
Lid v1.stl                Lid for the cover
Esp32_code.cpp            ESP32 main firmware file
SudoSpeed.py              Helper or bridge code when needed
ReadME.md                 This README
LICENSE                   MIT license
```

---

## How MotorHUD works

```
Phone Companion App → BLE text "NAV:<instruction>"
SudoSpeed on Pi or laptop → Classic BT SPP text "Z:<kph>"
ESP32 hub receives both → draws Navigation on left OLED and Zone on right OLED
Transparent OLEDs inside the helmet visor show the info with minimal clutter
```

Typical messages  
* From phone: `NAV:Turn left onto Hurley Street`  
* From SudoSpeed: `Z:60`

---

## Hardware overview

**Displays**  
Two 128×64 OLEDs. You can use transparent SSD1306-compatible panels on shared SPI.

**Power**  
Small USB battery bank or bike power with a 5 V regulator and inline fuse.

**Pins**  
You will update the final diagram. Use the table below as a starting point.

| Signal | ESP32 pin |
|-------:|:----------|
| SCLK   | 18        |
| MOSI   | 23        |
| MISO   | 19        |
| DC     | 16        |
| RST    | 4         |
| CS Left| 5         |
| CS Right| 17       |
| VCC    | 3V3       |
| GND    | GND       |

Upload your new diagram later as `images/pin_diagram_v2.png` and reference it here.

---

## Part A. ESP32 firmware

**File**  
`Esp32_code.cpp`

**Build steps**  
1. Arduino IDE or PlatformIO  
2. Boards Manager install ESP32  
3. Libraries  
   * Adafruit GFX  
   * Adafruit SSD1306  
   * BluetoothSerial  
   * NimBLE-Arduino for BLE UART  
4. Flash to the board and open Serial Monitor

**First run**  
The screens show waiting text. The device advertises as `ESP32-SUDOSPEED` for Classic BT and a BLE UART name for the phone. When a line arrives that starts with `NAV:` or `Z:` the display updates immediately.

---

## Part B. SudoSpeed link on Raspberry Pi

**Goal**  
Run SudoSpeed and forward zone updates to the ESP32.

**Steps**  
1. Pair the Pi with the ESP32 over Classic Bluetooth SPP  
2. Run SudoSpeed with your camera or a test clip  
3. Pipe lines that start with `Z:` to the SPP device

Example relay

```python
# relay_z_to_spp.py
import serial, sys
ser = serial.Serial("/dev/rfcomm0", 115200, timeout=1)
for line in sys.stdin:
    if line.startswith("Z:"):
        ser.write((line.strip() + "\n").encode("utf-8"))
```

Run

```bash
python3 run_speed_reader.py --source 0 --det detect.onnx --rec classify.onnx |
python3 relay_z_to_spp.py
```

You can also keep a helper in `SudoSpeed.py` if you prefer a single entry point.

---

## Part C. Companion App

**Folder**  
`Companion App/`

**What it does**  
Gets GPS from the phone, calls the Google Directions API, picks the single next instruction, and writes it over BLE as `NAV:<text>` every few seconds. If the rider takes a wrong turn the app re-routes and sends the new step.

**Setup**  
1. Open in Android Studio  
2. Add your Directions API key  
3. Grant location and Bluetooth permissions  
4. Pair with the ESP32 and press Start

---

## Printing and assembly

**STLs**  
`Case.stl`  
`display_cover v1.stl`  
`Lid v1.stl`

**Tips**  
* Print in ABS or PETG for heat and weather  
* Use small zip ties or M2 screws to secure the transparent OLED into the cover  
* Route cables through the case grooves and along the helmet edge  
* Check visibility at night and in bright daylight before riding

---

## Images

Keep everything in the single images folder. You plan to add these later.

```
images/
  helmet_inside.png
  helmet_outside.png
  pi_case_final.png
  pin_diagram_v2.png
```

Add any extra photos with clear names. Reference them in this README using the same folder.

---

## Roadmap

* Finalise transparent OLED mounts  
* Auto-start SudoSpeed on boot with a systemd service  
* BLE only transport for both NAV and Z if you decide to unify links  
* Brightness and font size controls on the ESP32  
* Optional voice prompt from the phone app

---

## Safety

MotorHUD is a research and learning project. Always follow road rules and test safely off the road first.

---

## License

MIT License

Copyright (c) 2025 Mustafa Siddiqui

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files the “Software”, to deal
in the Software without restriction, including without limitation the rights
to use copy modify merge publish distribute sublicense and or sell copies of
the Software and to permit persons to whom the Software is furnished to do so
subject to the following conditions

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software

THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM DAMAGES OR OTHER
LIABILITY WHETHER IN AN ACTION OF CONTRACT TORT OR OTHERWISE ARISING FROM
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE
