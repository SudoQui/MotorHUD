#include <algorithm>            // for std::min
#include "BluetoothSerial.h"
#include <U8g2lib.h>
#include <SPI.h>

// Bluetooth & Display setup
BluetoothSerial SerialBT;
U8G2_SH1106_128X64_NONAME_F_4W_HW_SPI u8g2(
  U8G2_MIRROR,   // <‑‑ horizontal mirror for helmet reflection
  /* cs=*/ 5,
  /* dc=*/ 17,
  /* reset=*/ 16
);

void setup() {
  Serial.begin(115200);
  u8g2.begin();
  u8g2.setFont(u8g2_font_ncenB08_tr);
  SerialBT.begin("ESP32_HUD");
  Serial.println("Connection established");
}

void loop() {
  // 1) Read from Bluetooth if available
  if (SerialBT.available()) {
    String msg = SerialBT.readStringUntil('\n');
    msg.trim();  // remove trailing \r or spaces

    // 2) Split into up to 3 lines of max 18 chars each
    const int maxChars = 18;
    String line1 = msg.substring(0, std::min<int>(maxChars, msg.length()));
    String line2 = "";
    String line3 = "";

    if (msg.length() > maxChars) {
      int end2 = std::min<int>(2 * maxChars, msg.length());
      line2 = msg.substring(maxChars, end2);
      if (msg.length() > 2 * maxChars) {
        line3 = msg.substring(2 * maxChars);
      }
    }

    // 3) Draw all three lines
    u8g2.clearBuffer();
    u8g2.drawStr(0, 16, line1.c_str());
    u8g2.drawStr(0, 32, line2.c_str());
    u8g2.drawStr(0, 48, line3.c_str());
    u8g2.sendBuffer();
  }

  // 4) (Optional) Mirror PC serial to Bluetooth
  if (Serial.available()) {
    String PC_message = Serial.readStringUntil('\n');
    Serial.println("PC: " + PC_message);
    SerialBT.println(PC_message);
  }
}
