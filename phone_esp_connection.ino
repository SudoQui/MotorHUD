#include "BluetoothSerial.h"
#include <U8g2lib.h>
#include <SPI.h>

// Creating bluetooth objects
BluetoothSerial SerialBT;

// SH1106, 128x64, SPI mode with full buffer (hardware SPI)
U8G2_SH1106_128X64_NONAME_F_4W_HW_SPI u8g2(U8G2_R0, /* cs=*/ 5, /* dc=*/ 17, /* reset=*/ 16);


void setup(){
  // Starts connection with USB
  Serial.begin(115200);
  u8g2.begin();
  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_ncenB08_tr);
  // Starts Bluetooth connection
  SerialBT.begin("ESP32_HUD");
  Serial.println("Connection established");



}

void loop(){
  if (SerialBT.available()){
    String phone_message = SerialBT.readString();
    Serial.println(phone_message);
    u8g2.clearBuffer();
    int maxPerLine = 18;

    String line1 = phone_message.substring(0, min(maxPerLine, (int)phone_message.length()));
    String line2 = (phone_message.length() > maxPerLine) ? phone_message.substring(maxPerLine) : "";

    u8g2.drawStr(0, 16, line1.c_str());  // First line
    if (line2.length() > 0) {
      u8g2.drawStr(0, 32, line2.c_str());  // Second line
    }
    u8g2.sendBuffer();
  }

  if (Serial.available()){
    String PC_message = Serial.readStringUntil('\n');
    Serial.println("PC: " + PC_message);
    SerialBT.println(PC_message);
  }

}