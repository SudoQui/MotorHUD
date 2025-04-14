
# 🏍️ MotorHUD

**MotorHUD** is an intelligent Heads-Up Display (HUD) system for motorcycles. It features a custom Android app that retrieves real-time GPS location, calculates turn-by-turn navigation using the Google Directions API, and sends the next instruction to an ESP32 over Bluetooth. The ESP32 then displays the directions on a compact 1.3" OLED screen.

---

## 🚀 Features

- 📍 Real-time GPS tracking via Android phone
- 🗺️ Turn-by-turn navigation using Google Maps Directions API
- 🔄 Automatic direction updates every 5 seconds
- 📡 Bluetooth communication with ESP32
- 🖥️ Minimalist HUD using a 128x64 SPI OLED Display
- 📱 Custom Android frontend with live instruction feedback
- 🪛 Helmet integration design (coming soon via CAD)

---

## 📷 Project Architecture

```plaintext
Android App (GPS + Directions API)
    ↳ Bluetooth
        ↳ ESP32
            ↳ OLED HUD Display
```

---

## 📱 Android App

### Key Technologies:
- Kotlin
- Google Play Services Location API
- Google Directions API
- Bluetooth Adapter API

### Features:
- "MotorHUD" header with logo
- Editable destination input
- Displays live instruction being sent to ESP32
- Automatic re-routing on wrong turns

### Setup:
1. Enable location permissions
2. Set your Google Directions API key
3. Pair your ESP32 over Bluetooth
4. Tap start to begin navigation

---

## 🧠 ESP32 Firmware

### Key Technologies:
- Arduino (C++)
- U8g2 Library for OLED rendering
- Bluetooth Serial (BT Classic)
- SPI Communication

### Features:
- Displays up to **3 lines** of text
- Parses incoming Bluetooth instructions
- Refreshes display on every update

### Wiring:
| OLED Pin | ESP32 Pin |
|----------|-----------|
| VCC      | 3.3V      |
| GND      | GND       |
| SCL      | 18        |
| SDA      | 23        |
| RES      | 16        |
| DC       | 17        |
| CS       | 5         |

---

## 🪖 Helmet Integration (Coming Soon)

A CAD file will be added to this repository demonstrating how the MotorHUD system is integrated into a motorcycle helmet.  
It includes a **transparent lens** for clear visual feedback while riding, ensuring both safety and usability.  

Stay tuned for `.f3d` / `.step` design files and 3D-print-ready components!

---

## 🔧 Installation & Build

### Android App:
```bash
Android Studio → Open Project → Run on Device
```

### ESP32 Firmware:
1. Flash via Arduino IDE or PlatformIO
2. Select correct COM port
3. Libraries needed:
   - `U8g2`
   - `BluetoothSerial`

---

## ✅ To-Do / Roadmap

- [x] ESP32 OLED 3-line support
- [x] Live Bluetooth updates
- [x] Google Directions API integration
- [ ] Add voice feedback option
- [ ] Route history & analytics
- [ ] HUD brightness adjustment
- [ ] Upload CAD helmet design

---

## 🧪 Demo

https://user-images.githubusercontent.com/.../motorhud_demo.mp4 *(Insert your demo link here)*

---

## 🤝 Credits

Made with ❤️ by Mustafa Siddiqui  
Special thanks to the open-source communities supporting ESP32, Android Dev, and Google Maps APIs.

---

## 📜 License

MIT License – use freely, but attribution appreciated!
