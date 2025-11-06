#include <SPI.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include "BluetoothSerial.h"

#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

// OLED pins
#define OLED_MOSI 23
#define OLED_CLK  18
// Left OLED
#define OLED1_DC   16
#define OLED1_CS    5
#define OLED1_RST  17
// Right OLED
#define OLED2_DC    4
#define OLED2_CS   14
#define OLED2_RST  27

Adafruit_SSD1306 dispLeft (128, 64, &SPI, OLED1_DC, OLED1_RST, OLED1_CS);
Adafruit_SSD1306 dispRight(128, 64, &SPI, OLED2_DC, OLED2_RST, OLED2_CS);


volatile int   g_zone  = -1;
volatile int   g_speed = -1;
String         g_nav1  = "";
String         g_nav2  = "";


unsigned long  tBlink   = 0;
bool           blinkOn  = false;


BluetoothSerial SPP;
String sppBuf;

// BlueDroid Connection
static BLEUUID SVC_UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E");
static BLEUUID RX_UUID ("6E400002-B5A3-F393-E0A9-E50E24DCCA9E");
static BLEUUID TX_UUID ("6E400003-B5A3-F393-E0A9-E50E24DCCA9E");

BLEServer*         pServer = nullptr;
BLECharacteristic* pChrRX  = nullptr;
BLECharacteristic* pChrTX  = nullptr;

String bleBuf;

// Forward decls
void handleLine(String line, bool fromBLE);
void setNavText(const String& txt);
void showWaitingScreen();

// Display orientation
void setDisplayOrientation(Adafruit_SSD1306& d, bool rotate180, bool mirrorX, bool mirrorY) {
  d.setRotation(rotate180 ? 2 : 0);
  d.ssd1306_command(mirrorX ? 0xA1 : 0xA0); 
  d.ssd1306_command(mirrorY ? 0xC8 : 0xC0);
}

//BLE callbacks
class RxCallbacks : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic* pChar) override {
    auto v = pChar->getValue();
    for (size_t i = 0; i < v.length(); ++i) {
      char ch = v[i];
      if (ch=='\n' || ch=='\r') {
        if (bleBuf.length()) { handleLine(bleBuf, true); bleBuf=""; }
      } else {
        bleBuf += ch;
        if (bleBuf.length()>256) bleBuf.remove(0, bleBuf.length()-256);
      }
    }
  }
};

class ServerCallbacks : public BLEServerCallbacks {
  void onConnect(BLEServer* pServer) override {
    Serial.println("[BLE] Central connected");
  }
  void onDisconnect(BLEServer* pServer) override {
    Serial.println("[BLE] Central disconnected");
    BLEDevice::getAdvertising()->start();
  }
};

void bleNotify(const String& s) {
  if (!pChrTX) return;
  pChrTX->setValue((uint8_t*)s.c_str(), s.length());
  pChrTX->notify();
}

//Text helpers
void setNavText(const String& txt) {
  String t = txt; t.trim();
  auto split = [](const String& s, int maxChars){
    String a = s; a.trim();
    if ((int)a.length() <= maxChars) return std::pair<String,String>(a,"");
    int cut = maxChars;
    for (int i=min(maxChars,(int)a.length()-1); i>=0; --i) if (a[i]==' '){ cut=i; break; }
    String l1 = a.substring(0, cut);
    String l2 = a.substring(cut); l2.trim();
    if ((int)l2.length() > maxChars) l2 = l2.substring(0, maxChars-1) + "…";
    return std::pair<String,String>(l1,l2);
  };
  auto p = split(t, 20);
  g_nav1 = p.first; g_nav2 = p.second;
}

void handleLine(String line, bool fromBLE){
  line.trim();
  if (!line.length()) return;

  // Allow "SPD:63|<nav>"
  if (line.startsWith("SPD:") && line.indexOf('|')>0) {
    int bar = line.indexOf('|');
    String sp = line.substring(4, bar);
    String nv = line.substring(bar+1);
    g_speed = sp.toInt();
    nv.replace("|"," | ");
    setNavText(nv);
    return;
  }

  if (line.startsWith("Z:")) {
    int z = line.substring(2).toInt();
    if (z>0 && z<200) g_zone = z;
  } else if (line.startsWith("SPD:")) {
    g_speed = line.substring(4).toInt();
  } else if (line.startsWith("NAV:")) {
    setNavText(line.substring(4));
  } else if (line == "PING") {
    if (fromBLE) bleNotify("PONG\n"); else SPP.println("PONG");
  }
}

//Minimal drawing
void drawNavMinimal() {
  dispLeft.clearDisplay();
  dispLeft.setTextColor(SSD1306_WHITE);
  
  dispLeft.setTextSize(2);
  dispLeft.setCursor(0, 8);
  if (g_nav1.length()) dispLeft.println(g_nav1);
  if (g_nav2.length()) {
    dispLeft.setCursor(0, 36);
    dispLeft.println(g_nav2);
  }
  dispLeft.display();
}

void drawZoneMinimal() {
  dispRight.clearDisplay();
  dispRight.setTextColor(SSD1306_WHITE);

  String z = (g_zone>0) ? String(g_zone) : String("--");
  dispRight.setTextSize(3);
  int x = (128 - (z.length()*18)) / 2;
  if (x < 0) x = 0;
  int y = 16;
  dispRight.setCursor(x, y);
  dispRight.print(z);

  bool over = (g_zone>0 && g_speed>=0 && g_speed>g_zone);
  if (over && blinkOn) {
    dispRight.drawCircle(64, 32, 27, SSD1306_WHITE);
  }

  dispRight.display();
}

// Waiting screen
void showWaitingScreen() {
  // LEFT
  dispLeft.clearDisplay();
  dispLeft.setTextColor(SSD1306_WHITE);
  dispLeft.setTextSize(1);
  dispLeft.setCursor(0, 0);
  dispLeft.println("Navigation ready");
  dispLeft.drawLine(0, 10, 127, 10, SSD1306_WHITE);
  dispLeft.display();

  // RIGHT
  dispRight.clearDisplay();
  dispRight.setTextColor(SSD1306_WHITE);
  dispRight.setTextSize(1);
  dispRight.setCursor(0, 0);
  dispRight.println("Speed check ready");
  dispRight.drawLine(0, 10, 127, 10, SSD1306_WHITE);
  dispRight.display();
}

// Setup
void setup() {
  Serial.begin(115200);
  delay(100);

  // SPI + OLEDs
  SPI.begin(OLED_CLK, -1, OLED_MOSI, OLED1_CS);
  if (!dispLeft.begin(SSD1306_SWITCHCAPVCC))  { Serial.println("Left OLED fail"); while(1)delay(1000); }
  setDisplayOrientation(dispLeft,  /*rotate180=*/false, /*mirrorX=*/false, /*mirrorY=*/false);

  delay(200);
  if (!dispRight.begin(SSD1306_SWITCHCAPVCC)) { Serial.println("Right OLED fail"); while(1)delay(1000); }
  setDisplayOrientation(dispRight, /*rotate180=*/false, /*mirrorX=*/false, /*mirrorY=*/false);

  // Waiting screen, elevator music type thing
  showWaitingScreen();

  // Classic SPP for Pi
  if (!SPP.begin("ESP32-SUDOSPEED")) { Serial.println("SPP init fail"); while(1)delay(1000); }
  Serial.println("SPP ready for Pi");

  // BLE (Bluedroid) for phone
  BLEDevice::init("MotorHUD BLE");
  BLEDevice::setMTU(247);

  pServer = BLEDevice::createServer();
  pServer->setCallbacks(new ServerCallbacks());

  BLEService* pSvc = pServer->createService(SVC_UUID);

  pChrTX = pSvc->createCharacteristic(TX_UUID, BLECharacteristic::PROPERTY_NOTIFY);
  pChrTX->addDescriptor(new BLE2902());

  pChrRX = pSvc->createCharacteristic(RX_UUID,
              BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR);
  pChrRX->setCallbacks(new RxCallbacks());

  pSvc->start();

  BLEAdvertising* adv = BLEDevice::getAdvertising();
  adv->addServiceUUID(SVC_UUID);
  adv->setScanResponse(true);
  adv->start();
}


void loop() {

  while (SPP.available()) {
    char ch = SPP.read();
    if (ch=='\n' || ch=='\r') {
      if (sppBuf.length()) { handleLine(sppBuf, false); sppBuf=""; }
    } else {
      sppBuf += ch;
      if (sppBuf.length()>256) sppBuf.remove(0, sppBuf.length()-256);
    }
  }

  unsigned long now = millis();
  if (now - tBlink >= 450) { tBlink = now; blinkOn = !blinkOn; }

  static unsigned long tDraw = 0;
  if (now - tDraw >= 120) {
    tDraw = now;

    if (g_nav1.length() || g_nav2.length()) drawNavMinimal();

    if (g_zone > 0) drawZoneMinimal();
  }

  delay(4);
}
