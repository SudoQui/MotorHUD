
import os
os.environ.setdefault("ORT_LOG_SEVERITY_LEVEL", "3")

import time, threading, subprocess, cv2, numpy as np
from collections import deque, defaultdict
from ultralytics import YOLO

# SER CONFIG
DETECT_WEIGHTS = "/home/sudospeed/models/detect_best.onnx"   # detect (320x320)
REC_WEIGHTS    = "/home/sudospeed/models/rec_best.onnx"      # classify (64x64)
DETECT_IMGSZ   = 320
IMG_SIZE_CLS   = 64

USE_CAMERA  = True
CAM_SIZE    = (960, 544) 
VIDEO_PATH  = "" 


OLED_ENABLED = True
SPI_PORT    = 0
SPI_DEVICE  = 0 
OLED_DC     = 25
OLED_RST    = 24
OLED_WIDTH  = 128
OLED_HEIGHT = 64

# Button
BTN_ENABLED  = True
BTN_PIN      = 17
DEBOUNCE_S   = 0.05
LONG_PRESS_S = 1.2

# ESP32 Bluetooth SPP
ESP32_MAC       = "FC:E8:C0:D6:2B:42"   # <-- your ESP32 MAC
RFCOMM_CHANNEL  = 1
SERIAL_PORT     = "/dev/rfcomm0"
SERIAL_BAUD     = 115200
SERIAL_RETRY_S  = 3.0
SERIAL_PREFIX   = "Z:"
HANDSHAKE_LINE  = "HELLO:CONNECTION_SECURED"


# I honestly dont even know how to tweak this to be optimal for each machine



# Detector
PROCESS_EVERY_N     = 2 
MAX_CROPS_PER_FRAME = 3
CONF_DET_THRESH     = 0.28
MIN_BOX_H_FRAC      = 0.025
RIGHT_SIDE_FRAC     = 0.20
ASPECT_MIN, ASPECT_MAX = 0.55, 1.5

# If this doesnt kill the latency issue, that it has killed me

CONF_THR                   = 0.65
TARGET_WINDOW_SEC_AT_30FPS = 0.8
CONFIRM_HITS               = 2   
EXTRA_HITS_TO_CHANGE       = 1 
COOLDOWN_S                 = 2.0
MAX_GAP_ANY_SIGN_S         = 60.0
DEFAULT_ZONE               = None

# Optional strong-confidence shortcut
ALLOW_STRONG_PROMOTE = True
STRONG_CONF_THR      = 0.93
STRONG_MIN_H_FRAC    = 0.04

#JUST KILL ME

DRAW_EVERY = 2  
PRINT_FPS_EVERY = 60  

#GLOBAL STATE
running = False
tx_enabled = False
current_zone, zone_set_ts = None, -1e18
pending_votes = defaultdict(lambda: deque(maxlen=64))
last_seen = {}
stop_event = threading.Event()

#Display
class OledHUD:
    def __init__(self, enable=True):
        self.device = None
        self.enable = enable
        if not enable:
            return
        try:
            from luma.core.interface.serial import spi
            from luma.oled.device import sh1106, ssd1306
            self.serial = spi(port=SPI_PORT, device=SPI_DEVICE, gpio_DC=OLED_DC, gpio_RST=OLED_RST, bus_speed_hz=8000000)
            try:
                self.device = sh1106(self.serial, width=OLED_WIDTH, height=OLED_HEIGHT)
                print("[OLED] SH1106")
            except Exception:
                self.device = ssd1306(self.serial, width=OLED_WIDTH, height=OLED_HEIGHT)
                print("[OLED] SSD1306")
        except Exception as e:
            print(f"[OLED] init failed: {e}")
            self.enable = False
            self.device = None

    def draw_lines(self, lines):
        if not (self.enable and self.device): return
        from PIL import Image, ImageDraw, ImageFont
        try:
            f = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
        except Exception:
            from PIL import ImageFont
            f = ImageFont.load_default()
        W,H = self.device.width, self.device.height
        img = Image.new("1",(W,H),0); d = ImageDraw.Draw(img)
        y = 0
        for line in lines[:5]:
            d.text((0,y), line, fill=255, font=f); y += 12
        self.device.display(img)

    def draw_status(self, zone, cand, hits, cooldown, fps):
        if not (self.enable and self.device): return
        from PIL import Image, ImageDraw, ImageFont
        try:
            font_s = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 11)
            font_b = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
        except Exception:
            from PIL import ImageFont
            font_s = ImageFont.load_default(); font_b = ImageFont.load_default()
        W,H = self.device.width, self.device.height
        img = Image.new("1",(W,H),0); d = ImageDraw.Draw(img)
        d.text((0,0),  f"FPS  : {fps:>4.1f}",                255, font=font_s)
        d.text((0,12), f"CAND : {cand if cand else '—'}",    255, font=font_s)
        d.text((0,24), f"HITS : {hits:>2}",                  255, font=font_s)
        d.text((0,36), f"COOL : {'Y' if cooldown else 'N'}", 255, font=font_s)
        z = str(zone) if zone is not None else "—"
        tz = f"Z:{z}"
        bx0,by0,bx1,by1 = d.textbbox((0,0), tz, font=font_b)
        tw,th = bx1-bx0, by1-by0
        x = max(0, W-tw-2); y = H-th-2
        d.rectangle((x-2,y-2,W,H), outline=255, fill=0)
        d.text((x,y), tz, 255, font=font_b)
        self.device.display(img)

oled = OledHUD(OLED_ENABLED)

# SERIAL Connection
class SerialTX:
    def __init__(self, port, baud, retry_s=3.0):
        self.port, self.baud, self.retry_s = port, baud, retry_s
        self.ser = None
        self.lock = threading.Lock()
        self._stop = False
        threading.Thread(target=self._open_loop, daemon=True).start()

    def _open_loop(self):
        while not self._stop:
            if self.ser is None:
                try:
                    import serial
                    self.ser = serial.Serial(self.port, self.baud, timeout=0.2)
                    print(f"[SERIAL] Connected -> {self.port} @ {self.baud}")
                except Exception:
                    time.sleep(self.retry_s); continue
            time.sleep(self.retry_s)

    def send(self, line):
        with self.lock:
            if self.ser is None: return False
            try:
                self.ser.write((line+"\n").encode("utf-8"))
                return True
            except Exception:
                try: self.ser.close()
                except Exception: pass
                self.ser = None
                return False

    def force_reopen(self):
        with self.lock:
            if self.ser:
                try: self.ser.close()
                except Exception: pass
                self.ser = None

    def close(self):
        self._stop = True
        with self.lock:
            if self.ser:
                try: self.ser.close()
                except Exception: pass
                self.ser = None

serial_tx = SerialTX(SERIAL_PORT, SERIAL_BAUD, SERIAL_RETRY_S)

def ensure_rfcomm_bound(mac, ch):
    try:
        subprocess.run(["sudo","rfcomm","release","0"], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["sudo","rfcomm","bind","0", mac, str(ch)], check=True)
        print(f"[RFCOMM] /dev/rfcomm0 bound -> {mac} ch {ch}")
        return True
    except Exception as e:
        print(f"[RFCOMM] bind failed: {e}")
        return False


def prep_for_recogniser(bgr_img, size, use_edges=False, grayscale=True):
    img = bgr_img
    if grayscale:
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
        g = clahe.apply(g)
        if use_edges:
            e = cv2.Canny(g, 80, 160)
            g = cv2.addWeighted(g, 0.85, e, 0.15, 0)
        img = cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)
    if img.ndim == 2: img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if img.shape[2] == 4: img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    img = cv2.resize(img, (size, size), interpolation=cv2.INTER_LINEAR)
    return np.ascontiguousarray(img, dtype=np.uint8)

def plausible_geometry(box_xyxy, W, H):
    x1,y1,x2,y2 = box_xyxy
    w,h = max(1, x2-x1), max(1, y2-y1)
    if (h / float(H)) < MIN_BOX_H_FRAC: return False
    xc = (x1+x2)/2.0
    if xc < RIGHT_SIDE_FRAC * W: return False
    a = w / float(h)
    return ASPECT_MIN <= a <= ASPECT_MAX

def window_secs(est_fps):
    return TARGET_WINDOW_SEC_AT_30FPS if est_fps <= 1e-3 else TARGET_WINDOW_SEC_AT_30FPS * (30.0 / max(1e-6, est_fps))

def cull_old_votes(now_s, win_s, votes):
    for v in list(votes.keys()):
        dq = votes[v]
        while dq and (now_s - dq[0] > win_s):
            dq.popleft()
        if not dq: votes.pop(v, None)

def too_long_since_any_sign(now_s, last_seen):
    return bool(last_seen) and (now_s - max(last_seen.values()) > MAX_GAP_ANY_SIGN_S)

#ZONE LOGIC
def set_zone(v, now_s):
    global current_zone, zone_set_ts
    current_zone, zone_set_ts = v, now_s
    print(f"[ZONE] {v} @ {time.strftime('%H:%M:%S')}")
    if tx_enabled:
        line = f"{SERIAL_PREFIX}{v}"
        ok = serial_tx.send(line)
        print("  -> TX:", line if ok else "  -> TX failed")

def process_frame_logic(dets, now_s, W, H, est_fps):
    global current_zone
    win_s = window_secs(est_fps)
    in_cooldown = (now_s - zone_set_ts) < COOLDOWN_S


    if ALLOW_STRONG_PROMOTE:
        for value, conf, (x1,y1,x2,y2) in dets:
            if conf >= STRONG_CONF_THR:
                h_frac = max(1, (y2 - y1)) / float(H)
                if h_frac >= STRONG_MIN_H_FRAC and plausible_geometry((x1,y1,x2,y2), W, H):
                    if (current_zone is None) or (value != current_zone and not in_cooldown):
                        set_zone(value, now_s)
                        pending_votes[value].append(now_s)
                        last_seen[value] = now_s
                        break

   
    for value, conf, (x1,y1,x2,y2) in dets:
        value = str(value).strip()
        if conf < CONF_THR: continue
        if not plausible_geometry((x1,y1,x2,y2), W, H): continue
        pending_votes[value].append(now_s)
        last_seen[value] = now_s

    cull_old_votes(now_s, win_s, pending_votes)

    
    best_value, best_score = None, -1.0
    for v, times in pending_votes.items():
        hits = len(times)
        age = max(0.0, now_s - times[-1]) if times else 1e9
        score = hits + max(0.0, (win_s - age)) * 0.25
        if score > best_score:
            best_value, best_score = v, score

    promoted = None
    in_cooldown = (now_s - zone_set_ts) < COOLDOWN_S

    if best_value is not None:
        hits = len(pending_votes[best_value])
        if current_zone is None and hits >= CONFIRM_HITS:
            set_zone(best_value, now_s); promoted = best_value
        elif current_zone is not None and best_value != current_zone:
            need = CONFIRM_HITS + EXTRA_HITS_TO_CHANGE
            if hits >= need and not in_cooldown:
                set_zone(best_value, now_s); promoted = best_value

    if current_zone is not None and too_long_since_any_sign(now_s, last_seen):
        if DEFAULT_ZONE is not None and DEFAULT_ZONE != current_zone:
            set_zone(DEFAULT_ZONE, now_s)

    best_hits = len(pending_votes.get(best_value, [])) if best_value else 0
    return best_value, best_hits, in_cooldown, promoted

def classifier_supports_batch(path):
    try:
        import onnxruntime as ort
        s = ort.InferenceSession(path, providers=["CPUExecutionProvider"]).get_inputs()[0].shape
        bdim = s[0]
        return (bdim != 1) if isinstance(bdim,int) else True, bdim
    except Exception:
        return True, None

# PIPELINE
def pipeline_worker():
    global running
    try:
        detector   = YOLO(DETECT_WEIGHTS, task="detect")
        recogniser = YOLO(REC_WEIGHTS,    task="classify")
        assert detector.task == "detect" and recogniser.task == "classify"
        for m in (detector, recogniser):
            try: m.fuse()
            except Exception: pass
        cls_batch, _ = classifier_supports_batch(REC_WEIGHTS)

        cap = None; picam2 = None
        if USE_CAMERA:
            from picamera2 import Picamera2
            picam2 = Picamera2()
            cfg = picam2.create_video_configuration(main={"size": CAM_SIZE, "format":"RGB888"})
            picam2.configure(cfg); picam2.start(); time.sleep(0.4)
        else:
            if not VIDEO_PATH: raise RuntimeError("Set VIDEO_PATH or enable USE_CAMERA=True")
            cap = cv2.VideoCapture(VIDEO_PATH)
            if not cap.isOpened(): raise RuntimeError(f"Could not open {VIDEO_PATH}")

        last_t, ema_fps, frame_idx, proc_count = time.time(), None, 0, 0
        running = True
        print(f"[HITS] first={CONFIRM_HITS}, change={CONFIRM_HITS + EXTRA_HITS_TO_CHANGE}")

        while not stop_event.is_set():
            if USE_CAMERA:
                frame = picam2.capture_array()
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            else:
                ok, frame = cap.read()
                if not ok: break

            frame_idx += 1
            H,W = frame.shape[:2]
            do_process = (frame_idx % PROCESS_EVERY_N) == 0
            detections = []

            if do_process:
                proc_count += 1
                det = detector.predict(frame, imgsz=DETECT_IMGSZ, conf=CONF_DET_THRESH, device="cpu", verbose=False)[0]

                boxes_scores = []
                for b in det.boxes:
                    x1,y1,x2,y2 = map(int, b.xyxy[0].tolist())
                    x1=max(0,x1); y1=max(0,y1); x2=min(W,x2); y2=min(H,y2)
                    if x2<=x1 or y2<=y1: continue
                    if (y2-y1)/float(H) < MIN_BOX_H_FRAC: continue
                    score = float(b.conf[0]) if hasattr(b,"conf") else 1.0
                    if score < 0.30: continue
                    area = (x2-x1)*(y2-y1)
                    boxes_scores.append(((x1,y1,x2,y2), area*score))

                boxes_scores.sort(key=lambda it: it[1], reverse=True)
                boxes_scores = boxes_scores[:MAX_CROPS_PER_FRAME]

                crops, boxes = [], []
                for (x1,y1,x2,y2), _ in boxes_scores:
                    crop = frame[y1:y2, x1:x2]
                    if crop.size == 0: continue
                    crop_in = prep_for_recogniser(crop, IMG_SIZE_CLS, use_edges=False, grayscale=True)
                    crops.append(crop_in); boxes.append((x1,y1,x2,y2))

                if crops:
                    if cls_batch:
                        cls = recogniser.predict(crops, imgsz=IMG_SIZE_CLS, device="cpu", verbose=False, batch=min(8,len(crops)))
                        for (x1,y1,x2,y2), res in zip(boxes, cls):
                            idx = int(res.probs.top1); name = res.names[idx].strip(); conf = float(res.probs.top1conf)
                            detections.append((name, conf, (x1,y1,x2,y2)))
                    else:
                        for (x1,y1,x2,y2), crop in zip(boxes, crops):
                            res = recogniser.predict(crop, imgsz=IMG_SIZE_CLS, device="cpu", verbose=False)[0]
                            idx = int(res.probs.top1); name = res.names[idx].strip(); conf = float(res.probs.top1conf)
                            detections.append((name, conf, (x1,y1,x2,y2)))

            now = time.time()
            dt = max(1e-6, now - last_t); inst_fps = 1.0/dt; last_t = now
            ema_fps = inst_fps if ema_fps is None else (0.9*ema_fps + 0.1*inst_fps)
            cand, hits, cooldown, _ = process_frame_logic(detections, now, W, H, ema_fps)

            if OLED_ENABLED and do_process and (proc_count % DRAW_EVERY == 0):
                oled.draw_status(current_zone, cand, hits, cooldown, ema_fps)

            if do_process and (proc_count % PRINT_FPS_EVERY == 0):
                print(f"[FPS] {ema_fps:5.2f} | cand={cand or '—'} hits={hits} cool={'Y' if cooldown else 'N'} | crops={len(detections)}")

        if not USE_CAMERA and cap: cap.release()
        if USE_CAMERA and 'picam2' in locals() and picam2: picam2.stop()
    except Exception as e:
        print("[PIPELINE] error:", e)
    finally:
        running = False
        print("[PIPELINE] stopped")

# BUTTON
def start_on_tap_and_test_on_longpress():
    try:
        from gpiozero import Button
    except Exception as e:
        print(f"[BTN] gpiozero not available: {e}")
        return

    btn = Button(BTN_PIN, pull_up=True, bounce_time=DEBOUNCE_S)
    pressing = {"t0":0.0, "long":False}
    worker = {"thread": None}

    def do_start():
        global tx_enabled
        oled.draw_lines(["Binding BT...", ESP32_MAC, f"ch {RFCOMM_CHANNEL}"])
        ok = ensure_rfcomm_bound(ESP32_MAC, RFCOMM_CHANNEL)
        if not ok:
            oled.draw_lines(["BT bind FAILED", "Tap to retry"])
            return
        serial_tx.force_reopen(); time.sleep(0.6)
        sent = serial_tx.send(HANDSHAKE_LINE)
        oled.draw_lines(["HELLO sent" if sent else "HELLO failed", "Starting..."])
        tx_enabled = True
        if not running and (worker["thread"] is None or not worker["thread"].is_alive()):
            stop_event.clear()
            worker["thread"] = threading.Thread(target=pipeline_worker, daemon=True)
            worker["thread"].start()

    def do_test_burst():
        for z in (10,20,30,40,50):
            serial_tx.send(f"{SERIAL_PREFIX}{z}")
            time.sleep(0.25)
        oled.draw_lines(["Test sent:", "10 20 30 40 50"])

    def on_pressed():
        pressing["t0"] = time.time()
        pressing["long"] = False
        def watch():
            while True:
                if pressing["long"] or (time.time()-pressing["t0"])>=LONG_PRESS_S or btn.is_released:
                    break
                time.sleep(0.02)
            if (time.time()-pressing["t0"])>=LONG_PRESS_S and btn.is_pressed:
                pressing["long"] = True
                do_test_burst()
        threading.Thread(target=watch, daemon=True).start()

    def on_released():
        if pressing["long"]:
            return
        do_start()

    btn.when_pressed = on_pressed
    btn.when_released = on_released
    print("[BTN] Tap = bind+HELLO+start, Long>1.2s = test burst")
    oled.draw_lines(["SudoSpeed IDLE", "Tap to Start", "Long: test burst"])

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        serial_tx.close()

if __name__ == "__main__":
    start_on_tap_and_test_on_longpress()
