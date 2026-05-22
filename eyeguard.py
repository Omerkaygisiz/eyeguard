"""
👁️  EyeGuard / Göz Koruyucu  v5.1
20-20-20 Rule — MediaPipe ile göz takibi

Kurulum:
    pip install mediapipe opencv-python pystray pillow

v5.0'dan farklar (bug fix):
  - GazeWrapper.close() sorunu giderildi: reopen() metodu eklendi,
    her molada face_mesh yeniden başlatılıyor
  - _break_done race condition düzeltildi: clear() timer thread'e taşındı
  - _stop_cam Event'i artık _close_break() içinde set ediliyor
  - show_break_done() / _close_break() çift çağrı önlendi (_closing_break bayrağı)
  - Tray thread'inden yapılan Tkinter çağrıları safe_after ile sarıldı
  - SettingsWindow dil değişince otomatik kapanıyor
"""

import cv2
import time
import math
import tkinter as tk
from tkinter import font as tkfont
from threading import Thread, Event, Lock
import sys

# ── MediaPipe ────────────────────────────────────────────────────
try:
    import mediapipe as mp
    if hasattr(mp, 'solutions') and hasattr(mp.solutions, 'face_mesh'):
        _mp_face = mp.solutions.face_mesh
        _MP_MODE = "solutions"
        GAZE_AVAILABLE = True
        print(f"✅ MediaPipe {mp.__version__} — solutions API")
    elif hasattr(mp, 'tasks'):
        # 0.10.20+ tasks API
        from mediapipe.tasks import python as mp_tasks
        from mediapipe.tasks.python import vision as mp_vision
        import urllib.request, os
        _MODEL_PATH = os.path.join(os.path.dirname(__file__), "face_landmarker.task")
        if not os.path.exists(_MODEL_PATH):
            print("📥 Face landmarker modeli indiriliyor...")
            urllib.request.urlretrieve(
                "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
                _MODEL_PATH)
            print("✅ Model indirildi.")
        _mp_tasks   = mp_tasks
        _mp_vision  = mp_vision
        _MP_MODE    = "tasks"
        GAZE_AVAILABLE = True
        print(f"✅ MediaPipe {mp.__version__} — tasks API")
    else:
        print(f"⚠️  MediaPipe {mp.__version__} — uyumlu API bulunamadı")
        GAZE_AVAILABLE = False
        _MP_MODE = "none"
except ImportError:
    print("⚠️  mediapipe bulunamadı.  pip install mediapipe")
    GAZE_AVAILABLE = False
    _MP_MODE = "none"
except Exception as e:
    print(f"⚠️  mediapipe yüklenemedi: {e}")
    GAZE_AVAILABLE = False
    _MP_MODE = "none"

# ── pystray ──────────────────────────────────────────────────────
try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_AVAILABLE = True
except ImportError:
    print("⚠️  pystray/Pillow yok.  pip install pystray pillow")
    TRAY_AVAILABLE = False

# ════════════════════════════════════════════════════════════════
#  LANGUAGE
# ════════════════════════════════════════════════════════════════
STRINGS = {
    "tr": {
        "app_name":             "Göz Koruyucu",
        "tray_open":            "Uygulamayı Aç",
        "tray_settings":        "Ayarlar",
        "tray_lang":            "Dil: TR → EN",
        "tray_quit":            "Çıkış",
        "tray_game_on":         "🎮  Oyun Modunu Kapat",
        "tray_game_off":        "🎮  Oyun Modu (2 saat)",
        "next_break_in":        "Sonraki mola",
        "min":                  "dk",
        "sec":                  "sn",
        "panel_title":          "GÖZ KORUYUCU",
        "panel_subtitle":       "20 • 20 • 20 Kuralı",
        "panel_next":           "SONRAKİ MOLAYA",
        "panel_working":        "● Çalışıyor",
        "panel_paused":         "⏸  Duraklatıldı",
        "panel_schedule_off":   "⏸  Bugün devre dışı",
        "panel_schedule_range": "⏸  {start}–{end} devre dışı",
        "panel_minimize":       "Küçült",
        "panel_lang_btn":       "EN",
        "panel_settings":       "⚙  Ayarlar",
        "panel_stats_btn":      "📊  İstatistik",
        "panel_game_btn":       "🎮  Oyun Modu",
        "panel_game_stop":      "🎮  Oyun Modu — Kapat",
        "panel_schedule_btn":   "🕐  Zamanlama",
        "panel_today":          "BUGÜN",
        "panel_week":           "BU HAFTA",
        "panel_away":           "UZAKTA",
        "panel_mola":           "mola",
        "panel_bugun":          "bugün",
        "panel_dk":             "dk",
        "game_title":           "🎮  OYUN MODU",
        "game_subtitle":        "Molalar ve sayaç duraklatılır",
        "game_duration":        "Ne kadar süre aktif kalsın?",
        "game_hour":            "Saat",
        "game_minute":          "Dakika",
        "game_start":           "Başlat",
        "game_unlimited":       "Süresiz",
        "game_cancel":          "İptal",
        "game_remaining_h":     "⏱  {h}s {m:02d}dk kaldı",
        "game_remaining_m":     "⏱  {m}dk kaldı",
        "game_unlimited_lbl":   "⏱  Süresiz aktif",
        "game_error":           "Geçerli bir saat/dakika girin (0-23 saat, 0-59 dk)",
        "stats_title":          "İSTATİSTİKLER",
        "stats_subtitle":       "Son 30 günlük mola geçmişin",
        "stats_week":           "SON 7 GÜN",
        "stats_month":          "SON 30 GÜN",
        "stats_close":          "Kapat",
        "stats_days":           ["Pzt","Sal","Çar","Per","Cum","Cmt","Paz"],
        "schedule_title":       "🕐  ZAMANLAMA",
        "schedule_subtitle":    "Belirli saat aralıklarında veya günlerde programı duraklat",
        "schedule_active":      "  ✓ Aktif  ",
        "schedule_inactive":    "  ✗ Kapalı  ",
        "schedule_add":         "＋  Devre dışı aralık ekle",
        "schedule_disabled":    "Devre dışı:",
        "schedule_start":       "Başlangıç",
        "schedule_end":         "Bitiş",
        "schedule_save":        "💾  Kaydet ve Kapat",
        "schedule_days":        ["Pazartesi","Salı","Çarşamba","Perşembe","Cuma","Cumartesi","Pazar"],
        "settings_title":       "Ayarlar",
        "settings_work":        "Çalışma Süresi (dakika)",
        "settings_break":       "Mola Süresi (saniye)",
        "settings_sens":        "Hassasiyet  (ne kadar saptığında 'uzakta' sayılır)",
        "sens_low":             "Geniş",
        "sens_med":             "Orta",
        "sens_high":            "Dar",
        "settings_autostart":   "Windows başlangıcında otomatik çalıştır",
        "autostart_on":         "✓ Aktif",
        "autostart_off":        "✗ Pasif",
        "settings_save":        "Kaydet",
        "settings_cancel":      "İptal",
        "break_title":          "MOLA ZAMANI!",
        "break_subtitle":       "Uzak bir noktaya bak",
        "break_rule":           "20 dakikada bir  •  20 saniye  •  20 feet uzak",
        "break_watching":       "Kamera seni izliyor  •  Ekrana bakarsan süre sıfırlanır",
        "break_done":           "HARİKA!  Gözlerin teşekkür eder 👁",
        "status_away":          "✅  Uzağa bakıyor",
        "status_screen":        "⚠   Ekrana bakıyor — süre sıfırlandı",
        "status_noface":        "🔍  Yüz / göz algılanamıyor",
        "status_blink":         "😑  Göz kırpılıyor...",
        "status_complete":      "✅  Süre doldu! Devam edebilirsin",
        "console_start":        "🌿 Göz Koruyucu Başladı!",
        "console_info":         "Her {w} dakikada bir mola — {b} saniye mola.",
        "console_break":        "🟢 MOLA ZAMANI!",
        "console_done":         "🎉 Mola tamamlandı!",
        "console_reset":        "⚠️  Ekrana bakıldı — süre sıfırlanıyor",
        "console_away":         "👀 Uzağa bakılıyor...",
        "no_gaze_lib":          "❌ mediapipe kütüphanesi yüklü değil!",
        "warn_60s":             "🔔 Molaya 60 saniye kaldı!",
    },
    "en": {
        "app_name":             "EyeGuard",
        "tray_open":            "Open App",
        "tray_settings":        "Settings",
        "tray_lang":            "Lang: EN → TR",
        "tray_quit":            "Quit",
        "tray_game_on":         "🎮  Disable Game Mode",
        "tray_game_off":        "🎮  Game Mode (2 hours)",
        "next_break_in":        "Next break in",
        "min":                  "min",
        "sec":                  "sec",
        "panel_title":          "EYE GUARD",
        "panel_subtitle":       "20 • 20 • 20 Rule",
        "panel_next":           "NEXT BREAK IN",
        "panel_working":        "● Working",
        "panel_paused":         "⏸  Paused",
        "panel_schedule_off":   "⏸  Disabled today",
        "panel_schedule_range": "⏸  Disabled {start}–{end}",
        "panel_minimize":       "Minimize",
        "panel_lang_btn":       "TR",
        "panel_settings":       "⚙  Settings",
        "panel_stats_btn":      "📊  Statistics",
        "panel_game_btn":       "🎮  Game Mode",
        "panel_game_stop":      "🎮  Game Mode — Stop",
        "panel_schedule_btn":   "🕐  Schedule",
        "panel_today":          "TODAY",
        "panel_week":           "THIS WEEK",
        "panel_away":           "AWAY",
        "panel_mola":           "breaks",
        "panel_bugun":          "today",
        "panel_dk":             "min",
        "game_title":           "🎮  GAME MODE",
        "game_subtitle":        "Breaks and timer are paused",
        "game_duration":        "How long should it stay active?",
        "game_hour":            "Hours",
        "game_minute":          "Minutes",
        "game_start":           "Start",
        "game_unlimited":       "Unlimited",
        "game_cancel":          "Cancel",
        "game_remaining_h":     "⏱  {h}h {m:02d}min left",
        "game_remaining_m":     "⏱  {m}min left",
        "game_unlimited_lbl":   "⏱  Active indefinitely",
        "game_error":           "Enter valid hours/minutes (0-23h, 0-59min)",
        "stats_title":          "STATISTICS",
        "stats_subtitle":       "Your break history for the last 30 days",
        "stats_week":           "LAST 7 DAYS",
        "stats_month":          "LAST 30 DAYS",
        "stats_close":          "Close",
        "stats_days":           ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"],
        "schedule_title":       "🕐  SCHEDULE",
        "schedule_subtitle":    "Pause the app during specific hours or days",
        "schedule_active":      "  ✓ Active  ",
        "schedule_inactive":    "  ✗ Off  ",
        "schedule_add":         "＋  Add disabled range",
        "schedule_disabled":    "Disabled:",
        "schedule_start":       "Start",
        "schedule_end":         "End",
        "schedule_save":        "💾  Save & Close",
        "schedule_days":        ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"],
        "settings_title":       "Settings",
        "settings_work":        "Work Duration (minutes)",
        "settings_break":       "Break Duration (seconds)",
        "settings_sens":        "Sensitivity  (how far to look away)",
        "sens_low":             "Wide",
        "sens_med":             "Medium",
        "sens_high":            "Narrow",
        "settings_autostart":   "Launch at Windows startup",
        "autostart_on":         "✓ Active",
        "autostart_off":        "✗ Inactive",
        "settings_save":        "Save",
        "settings_cancel":      "Cancel",
        "break_title":          "BREAK TIME!",
        "break_subtitle":       "Look at something far away",
        "break_rule":           "Every 20 min  •  20 seconds  •  20 feet away",
        "break_watching":       "Camera is watching  •  Looking at screen resets the timer",
        "break_done":           "GREAT!  Your eyes thank you 👁",
        "status_away":          "✅  Looking away",
        "status_screen":        "⚠   Looking at screen — timer reset",
        "status_noface":        "🔍  Face / eyes not detected",
        "status_blink":         "😑  Blinking...",
        "status_complete":      "✅  Done! You can continue",
        "console_start":        "🌿 EyeGuard Started!",
        "console_info":         "Break every {w} min — {b} sec break.",
        "console_break":        "🟢 BREAK TIME!",
        "console_done":         "🎉 Break complete!",
        "console_reset":        "⚠️  Looking at screen — resetting timer",
        "console_away":         "👀 Looking away...",
        "no_gaze_lib":          "❌ mediapipe library not installed!",
        "warn_60s":             "🔔 60 seconds until break!",
    }
}

# ════════════════════════════════════════════════════════════════
#  GLOBAL STATE
# ════════════════════════════════════════════════════════════════
class AppState:
    def __init__(self):
        self._lock           = Lock()
        self.lang            = "tr"
        self.work_minutes    = 20
        self.break_seconds   = 20
        self.sensitivity     = "med"
        self.running         = True
        self.on_break        = False
        self.next_break_time = 0.0
        self.tray_icon       = None
        self.app             = None
        self._listeners      = []
        # Oyun modu
        self.game_mode       = False
        self.game_mode_until = None
        self.schedule_active = True   # zamanlama aktif mi
        self.panel_visible   = True   # ana panel görünür mü   # None = süresiz, float = bitiş zamanı

    def enable_game_mode(self, hours=None):
        self.game_mode = True
        self.game_mode_until = time.time() + hours * 3600 if hours else None
        print(f"🎮 Oyun modu aktif {'(süresiz)' if not hours else f'({hours} saat)'}")
        self._notify()

    def disable_game_mode(self):
        self.game_mode       = False
        self.game_mode_until = None
        print("✅ Oyun modu kapatıldı, molalar devam ediyor.")
        self._notify()

    def sensitivity_threshold(self):
        return {"low": 0.20, "med": 0.14, "high": 0.08}[self.sensitivity]

    def add_listener(self, cb):
        with self._lock:
            if cb not in self._listeners:
                self._listeners.append(cb)

    def remove_listener(self, cb):
        with self._lock:
            try: self._listeners.remove(cb)
            except ValueError: pass

    def _notify(self):
        with self._lock:
            cbs = list(self._listeners)
        for cb in cbs:
            try: cb()
            except Exception:
                pass  # listener hataları sessizce geç

    def set_lang(self, lang):
        self.lang = lang
        # FIX: Close settings window on language change,
        # so it reopens with the correct language.
        if self.app and hasattr(self.app, '_settings_win'):
            sw = self.app._settings_win
            if sw._win and sw._win.winfo_exists():
                try:
                    sw._win.destroy()
                except Exception:
                    pass
        self._notify()

    def update_settings(self, work, brk, sens):
        with self._lock:
            self.work_minutes  = work
            self.break_seconds = brk
            self.sensitivity   = sens
        self._notify()

state = AppState()

def s(key, **kw):
    t = STRINGS[state.lang].get(key, key)
    return t.format(**kw) if kw else t

# ════════════════════════════════════════════════════════════════
#  STATISTICS MODULE
# ════════════════════════════════════════════════════════════════
import json, os
from datetime import datetime, date, timedelta

STATS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "eyeguard_stats.json")

class Stats:
    """
    JSON dosyasına günlük istatistik kaydeder.
    Format:
    {
      "2025-01-20": {"breaks": 5, "away_seconds": 120},
      ...
    }
    """
    def __init__(self):
        self._lock = Lock()
        self._data = self._load()

    def _load(self):
        try:
            if os.path.exists(STATS_FILE):
                with open(STATS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save(self):
        try:
            with open(STATS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Stats kayıt hatası: {e}")

    def _today(self):
        return date.today().isoformat()

    def record_break(self, away_seconds: float):
        """Mola tamamlandığında çağır."""
        with self._lock:
            key = self._today()
            if key not in self._data:
                self._data[key] = {"breaks": 0, "away_seconds": 0}
            self._data[key]["breaks"]       += 1
            self._data[key]["away_seconds"] += away_seconds
            self._save()

    def today_breaks(self) -> int:
        with self._lock:
            return self._data.get(self._today(), {}).get("breaks", 0)

    def today_away_seconds(self) -> float:
        with self._lock:
            return self._data.get(self._today(), {}).get("away_seconds", 0)

    def week_breaks(self) -> int:
        """Son 7 günün toplam mola sayısı."""
        with self._lock:
            total = 0
            for i in range(7):
                d = (date.today() - timedelta(days=i)).isoformat()
                total += self._data.get(d, {}).get("breaks", 0)
            return total

    def last_n_days(self, n=30) -> list:
        """
        Son n günün listesi: [{"date": "2025-01-20", "breaks": 3, "away_seconds": 80}, ...]
        En eskiden en yeniye sıralı.
        """
        with self._lock:
            result = []
            for i in range(n-1, -1, -1):
                d = (date.today() - timedelta(days=i)).isoformat()
                entry = self._data.get(d, {"breaks": 0, "away_seconds": 0})
                result.append({"date": d, **entry})
            return result

stats = Stats()

# ════════════════════════════════════════════════════════════════
#  SCHEDULE MODULE
# ════════════════════════════════════════════════════════════════
SCHEDULE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "eyeguard_schedule.json")

# Default schedule: every day active, no disabled ranges
_DEFAULT_SCHEDULE = {
    str(i): {"active": True, "disabled_ranges": []}
    for i in range(7)   # 0=Pazartesi, 6=Pazar
}

DAY_NAMES_TR = ["Pazartesi","Salı","Çarşamba","Perşembe","Cuma","Cumartesi","Pazar"]
DAY_NAMES_EN = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]

class Schedule:
    """
    Zamanlı etkinleştirme.
    Format:
    {
      "0": {"active": true, "disabled_ranges": [["12:00","13:00"], ["15:00","16:00"]]},
      "6": {"active": false, "disabled_ranges": []}
    }
    """
    def __init__(self):
        self._lock = Lock()
        self._data = self._load()

    def _load(self):
        try:
            if os.path.exists(SCHEDULE_FILE):
                with open(SCHEDULE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for i in range(7):
                        if str(i) not in data:
                            data[str(i)] = {"active": True, "disabled_ranges": []}
                    return data
        except Exception as e:
            print(f"Schedule yükleme hatası: {e}")
        return {k: dict(v) for k, v in _DEFAULT_SCHEDULE.items()}

    def save(self):
        try:
            with open(SCHEDULE_FILE, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Schedule kayıt hatası: {e}")

    def get_day(self, weekday: int) -> dict:
        with self._lock:
            return dict(self._data.get(str(weekday), {"active": True, "disabled_ranges": []}))

    def set_day(self, weekday: int, active: bool, disabled_ranges: list):
        with self._lock:
            self._data[str(weekday)] = {
                "active": active,
                "disabled_ranges": disabled_ranges
            }
        self.save()

    def should_be_active(self) -> bool:
        now      = datetime.now()
        weekday  = now.weekday()
        day_cfg  = self.get_day(weekday)

        if not day_cfg["active"]:
            return False

        now_str = now.strftime("%H:%M")
        for start, end in day_cfg["disabled_ranges"]:
            if start <= now_str < end:
                return False

        return True

schedule = Schedule()


# Landmark indices used:
#   1   = burun ucu
#   152 = chin tip
#   33  = left eye inner corner
#   263 = right eye inner corner
#   10  = forehead center

class GazeWrapper:
    """
    Kafa yönünü 2D landmark geometrisiyle hesaplar — solvePnP yok.

    Yatay simetri (sol/sağ göz mesafesi farkı) → yaw proxy
    Dikey oran (burun-çene / göz-çene)          → pitch proxy

    Ekrana düz bakılınca her iki değer ~0.
    Başı çevirince veya eğince değerler artar.

    Hassasiyet eşikleri ayardan gelir:
        low  → geniş  (çok döndürünce tetiklenir)
        med  → orta
        high → dar    (az döndürünce tetiklenir)
    """

    THRESHOLDS = {
        "low":  (0.25, 0.22),
        "med":  (0.15, 0.16),
        "high": (0.10, 0.11),
    }
    BUF_SIZE = 5

    def __init__(self):
        self._face_mesh = None
        self._buf       = []
        self._lock      = Lock()
        self._reopen()

    def _reopen(self):
        if not GAZE_AVAILABLE:
            return
        if self._face_mesh is not None:
            try:
                self._face_mesh.close()
            except Exception:
                pass
            self._face_mesh = None

        if _MP_MODE == "solutions":
            self._face_mesh = _mp_face.FaceMesh(
                max_num_faces=1,
                refine_landmarks=False,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
        else:
            import os
            _MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "face_landmarker.task")
            base_opts = _mp_tasks.BaseOptions(model_asset_path=_MODEL_PATH)
            opts = _mp_vision.FaceLandmarkerOptions(
                base_options=base_opts,
                num_faces=1,
                running_mode=_mp_vision.RunningMode.IMAGE,
            )
            self._face_mesh = _mp_vision.FaceLandmarker.create_from_options(opts)

    def reopen(self):
        with self._lock:
            self._buf.clear()
        self._reopen()

    def analyze(self, frame) -> str:
        """'away' | 'screen' | 'noface'"""
        if self._face_mesh is None:
            return "noface"

        h, w = frame.shape[:2]
        rgb  = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        if _MP_MODE == "solutions":
            rgb.flags.writeable = False
            results = self._face_mesh.process(rgb)
            if not results.multi_face_landmarks:
                return "noface"
            lm = results.multi_face_landmarks[0].landmark
        else:
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            results  = self._face_mesh.detect(mp_image)
            if not results.face_landmarks:
                return "noface"
            lm = results.face_landmarks[0]

        # Normalized coordinates (0-1 range)
        nose    = lm[1]    # burun ucu
        chin    = lm[152]  # çene
        l_eye   = lm[33]   # sol göz iç köşe
        r_eye   = lm[263]  # sağ göz iç köşe
        forehead= lm[10]   # alın

        # ── Yatay asimetri (yaw proxy) ──
        # Face center x = midpoint between eye corners
        # Nose deviation from center gives yaw proxy
        eye_center_x = (l_eye.x + r_eye.x) / 2
        eye_span     = abs(r_eye.x - l_eye.x)   # göz açıklığı (normalize)
        if eye_span < 0.01:
            return "noface"

        # Nose horizontal deviation / eye span
        yaw_proxy = abs(nose.x - eye_center_x) / eye_span

        # ── Vertical tilt (pitch proxy) ──
        # Nose position within forehead-chin vertical span
        # When looking straight, nose is roughly in the middle
        face_height = abs(chin.y - forehead.y)
        if face_height < 0.01:
            return "noface"

        nose_rel    = (nose.y - forehead.y) / face_height  # 0=alın, 1=çene
        # ~0.55-0.60 when looking straight; take deviation
        pitch_proxy = abs(nose_rel - 0.57)

        yaw_th, pitch_th = self.THRESHOLDS[state.sensitivity]
        raw_away = (yaw_proxy > yaw_th) or (pitch_proxy > pitch_th)

        with self._lock:
            self._buf.append(raw_away)
            if len(self._buf) > self.BUF_SIZE:
                self._buf.pop(0)
            is_away = (len(self._buf) == self.BUF_SIZE) and all(self._buf)

        return "away" if is_away else "screen"

    def clear_buffer(self):
        with self._lock:
            self._buf.clear()

    def shutdown(self):
        if self._face_mesh:
            try:
                self._face_mesh.close()
            except Exception:
                pass
            self._face_mesh = None


# ════════════════════════════════════════════════════════════════
#  YARDIMCI
# ════════════════════════════════════════════════════════════════
FONT_PREF = ["Segoe UI", "Helvetica Neue", "Arial"]

def font(size, weight="normal"):
    for fam in FONT_PREF:
        try:
            f = tkfont.Font(family=fam, size=size, weight=weight)
            if fam.lower() in f.actual("family").lower():
                return f
        except Exception:
            pass
    return tkfont.Font(size=size, weight=weight)

# ════════════════════════════════════════════════════════════════
#  AUTO-START  (Windows Registry)
# ════════════════════════════════════════════════════════════════
_REG_KEY  = r"Software\Microsoft\Windows\CurrentVersion\Run"
_APP_NAME = "EyeGuard"

def _get_exe_path() -> str:
    """Çalışan scriptin/exe'nin tam yolunu döndürür."""
    import sys
    if getattr(sys, 'frozen', False):
        # PyInstaller ile paketlendiyse
        return sys.executable
    # Normal Python scripti
    return f'"{sys.executable}" "{os.path.abspath(__file__)}"'

def autostart_is_enabled() -> bool:
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_KEY, 0, winreg.KEY_READ)
        val, _ = winreg.QueryValueEx(key, _APP_NAME)
        winreg.CloseKey(key)
        return bool(val)
    except Exception:
        return False

def autostart_enable():
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_KEY, 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, _APP_NAME, 0, winreg.REG_SZ, _get_exe_path())
        winreg.CloseKey(key)
        print("✅ Otomatik başlatma aktifleştirildi.")
    except Exception as e:
        print(f"❌ Otomatik başlatma hatası: {e}")

def autostart_disable():
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_KEY, 0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(key, _APP_NAME)
        winreg.CloseKey(key)
        print("🔕 Otomatik başlatma devre dışı.")
    except FileNotFoundError:
        pass  # zaten yoktu
    except Exception as e:
        print(f"❌ Otomatik başlatma kaldırma hatası: {e}")


def safe_after(root, fn, delay=0):
    try:
        if root and root.winfo_exists():
            root.after(delay, fn)
    except Exception:
        pass

def play_sound(kind="break"):
    """
    kind: 'warning' | 'break' | 'done'
    Plays the relevant file from the notifications/ folder.
    """
    # Correct base path for both PyInstaller EXE and normal script
    if getattr(sys, 'frozen', False):
        _BASE = os.path.dirname(sys.executable)
    else:
        _BASE = os.path.dirname(os.path.abspath(__file__))

    FILES = {
        "warning": os.path.join(_BASE, "notifications", "warning.wav"),
        "break":   os.path.join(_BASE, "notifications", "break.wav"),
        "done":    os.path.join(_BASE, "notifications", "done.mp3"),
    }
    def _play():
        try:
            import pygame
            path = FILES.get(kind, "")
            if not path:
                return
            import os
            if not os.path.exists(path):
                print(f"⚠️  Ses dosyası bulunamadı: {path}")
                return
            pygame.mixer.init()
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
            # Ses bitene kadar bekle (max 10 sn)
            import time as _time
            waited = 0
            while pygame.mixer.music.get_busy() and waited < 10:
                _time.sleep(0.1)
                waited += 0.1
        except Exception as e:
            print(f"⚠️  Ses çalınamadı: {e}")
    Thread(target=_play, daemon=True).start()

# ════════════════════════════════════════════════════════════════
#  SETTINGS WINDOW  (Toplevel)
# ════════════════════════════════════════════════════════════════
# ════════════════════════════════════════════════════════════════
#  SCHEDULE WINDOW
# ════════════════════════════════════════════════════════════════
class ScheduleWindow:
    BG   = "#0a1520"
    BG2  = "#111e2e"
    BG3  = "#162438"
    ACC  = "#00e5ff"
    ACC2 = "#00ff9d"
    FG   = "#cce8f0"
    DIM  = "#1e3448"
    RED  = "#ff6b6b"
    SUB  = "#4a8aaa"

    def show(self, parent):
        win = tk.Toplevel(parent)
        win.title("Zamanlama")
        win.configure(bg=self.BG)
        win.resizable(False, False)
        win.attributes("-topmost", True)

        W, H = 640, 680
        sw = parent.winfo_screenwidth()
        sh = parent.winfo_screenheight()
        win.geometry(f"{W}x{H}+{(sw-W)//2}+{(sh-H)//2}")

        # Header
        header_frame = tk.Frame(win, bg=self.BG)
        header_frame.pack(fill="x", padx=0, pady=0)
        tk.Canvas(header_frame, height=3, bg=self.ACC,
                  highlightthickness=0).pack(fill="x")
        tk.Label(header_frame, text=s("schedule_title"),
            font=font(17,"bold"), fg=self.ACC, bg=self.BG).pack(pady=(16,4))
        tk.Label(header_frame,
            text=s("schedule_subtitle"),
            font=font(10), fg=self.SUB, bg=self.BG).pack(pady=(0,12))
        tk.Canvas(header_frame, height=1, bg=self.DIM,
                  highlightthickness=0).pack(fill="x", padx=20)

        # Scroll area
        outer = tk.Frame(win, bg=self.BG)
        outer.pack(fill="both", expand=True, padx=16, pady=8)

        cv = tk.Canvas(outer, bg=self.BG, highlightthickness=0, bd=0)
        sb = tk.Scrollbar(outer, orient="vertical", command=cv.yview)
        inner = tk.Frame(cv, bg=self.BG)

        inner.bind("<Configure>",
            lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.create_window((0,0), window=inner, anchor="nw")
        cv.configure(yscrollcommand=sb.set)
        cv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # FIX: unbind mousewheel when window closes
        def _mw(e):
            try:
                if cv.winfo_exists():
                    cv.yview_scroll(int(-1*(e.delta/120)), "units")
            except Exception:
                pass

        win.bind("<MouseWheel>", _mw)

        # Days
        self._day_vars = {}
        for day_i in range(7):
            cfg = schedule.get_day(day_i)
            self._build_day_row(inner, day_i, cfg)

        # Alt bar
        bottom = tk.Frame(win, bg=self.BG)
        bottom.pack(fill="x", side="bottom")
        tk.Canvas(bottom, height=1, bg=self.DIM,
                  highlightthickness=0).pack(fill="x")
        tk.Button(bottom, text=s("schedule_save"),
            font=font(12,"bold"), fg=self.BG, bg=self.ACC,
            activebackground="#00b8cc", relief="flat",
            padx=28, pady=10, cursor="hand2",
            command=lambda: self._save(win)).pack(pady=12)

        return win

    def _build_day_row(self, parent, day_i, cfg):
        BG, BG2, BG3 = self.BG, self.BG2, self.BG3
        ACC, FG, DIM, SUB = self.ACC, self.FG, self.DIM, self.SUB

        card = tk.Frame(parent, bg=BG2,
            highlightthickness=1, highlightbackground=DIM)
        card.pack(fill="x", pady=4, padx=2)

        active_var = tk.BooleanVar(value=cfg["active"])
        self._day_vars[day_i] = {"active": active_var, "ranges": [],
                                  "ranges_frame": None, "add_btn": None}

        header = tk.Frame(card, bg=BG2)
        header.pack(fill="x", padx=12, pady=8)

        left = tk.Frame(header, bg=BG2)
        left.pack(side="left")

        day_names = s("schedule_days")
        is_weekend = day_i >= 5
        name_color = "#7ab8cc" if not is_weekend else "#5a8a9a"
        tk.Label(left, text=day_names[day_i],
            font=font(13,"bold"), fg=name_color, bg=BG2,
            width=11, anchor="w").pack(side="left")

        # Right — toggle button
        toggle_frame = tk.Frame(header, bg=BG2)
        toggle_frame.pack(side="right")

        toggle_btn = tk.Label(toggle_frame,
            text=s("schedule_active") if cfg["active"] else s("schedule_inactive"),
            font=font(10,"bold"),
            fg="#001a0a" if cfg["active"] else "#cce8f0",
            bg=self.ACC2 if cfg["active"] else "#2a2a3e",
            padx=4, pady=3, cursor="hand2")
        toggle_btn.pack()

        def _toggle(dv=active_var, tb=toggle_btn, di=day_i):
            new_val = not dv.get()
            dv.set(new_val)
            if new_val:
                tb.config(text=s("schedule_active"), fg="#001a0a", bg=self.ACC2)
            else:
                tb.config(text=s("schedule_inactive"), fg="#cce8f0", bg="#2a2a3e")
            self._update_ranges_visibility(di)

        toggle_btn.bind("<Button-1>", lambda e: _toggle())

        # Ranges frame
        ranges_frame = tk.Frame(card, bg=BG2)
        self._day_vars[day_i]["ranges_frame"] = ranges_frame

        if cfg["active"]:
            ranges_frame.pack(fill="x", padx=12, pady=(0,4))

        # Load existing ranges
        for start, end in cfg["disabled_ranges"]:
            self._add_range_row(day_i, ranges_frame, start, end)

        # Separator
        sep = tk.Canvas(ranges_frame, height=1, bg=DIM, highlightthickness=0)
        sep.pack(fill="x", pady=(4,6))
        self._day_vars[day_i]["sep"] = sep

        # Ekle butonu
        add_btn = tk.Button(ranges_frame,
            text=s("schedule_add"),
            font=font(10), fg=SUB, bg=BG2,
            activebackground=BG3, activeforeground=ACC,
            relief="flat", padx=8, pady=3, cursor="hand2",
            command=lambda di=day_i, rf=ranges_frame: self._add_range_row(di, rf))
        add_btn.pack(anchor="w", pady=(0,4))
        self._day_vars[day_i]["add_btn"] = add_btn

    def _add_range_row(self, day_i, ranges_frame, start="12:00", end="13:00"):
        add_btn = self._day_vars[day_i].get("add_btn")
        sep     = self._day_vars[day_i].get("sep")

        row = tk.Frame(ranges_frame, bg=self.BG3,
            highlightthickness=1, highlightbackground=self.DIM)

        # Order: before sep and add_btn
        sep = self._day_vars[day_i].get("sep")
        if sep and sep.winfo_exists():
            row.pack(fill="x", pady=2, before=sep)
        else:
            row.pack(fill="x", pady=2)

        inner = tk.Frame(row, bg=self.BG3)
        inner.pack(fill="x", padx=10, pady=6)

        range_dict = {"start": tk.StringVar(value=start),
                      "end":   tk.StringVar(value=end),
                      "row":   row}
        self._day_vars[day_i]["ranges"].append(range_dict)

        tk.Label(inner, text=s("schedule_disabled"), font=font(10),
            fg=self.SUB, bg=self.BG3).pack(side="left", padx=(0,8))

        for var, lbl in [(range_dict["start"], s("schedule_start")),
                         (range_dict["end"],   s("schedule_end"))]:
            tk.Label(inner, text=lbl, font=font(9),
                fg="#3a6a8a", bg=self.BG3).pack(side="left", padx=(0,2))
            e = tk.Entry(inner, textvariable=var, width=6,
                font=font(12,"bold"), bg="#0a1520", fg=self.ACC,
                insertbackground=self.ACC, relief="flat",
                highlightthickness=1, highlightbackground="#2a5070",
                justify="center")
            e.pack(side="left", padx=(0,12))

        # Sil
        def remove(rd=range_dict):
            self._day_vars[day_i]["ranges"].remove(rd)
            rd["row"].destroy()

        tk.Button(inner, text="✕",
            font=font(11,"bold"), fg=self.RED, bg=self.BG3,
            activebackground=self.BG3, activeforeground="#ff9999",
            relief="flat", padx=6, cursor="hand2",
            command=remove).pack(side="right")

    def _update_ranges_visibility(self, day_i):
        dv = self._day_vars[day_i]
        if dv["active"].get():
            dv["ranges_frame"].pack(fill="x", padx=12, pady=(0,4))
        else:
            dv["ranges_frame"].pack_forget()

    def _save(self, win):
        for day_i, dv in self._day_vars.items():
            active = dv["active"].get()
            ranges = []
            for rd in dv["ranges"]:
                start = rd["start"].get().strip()
                end   = rd["end"].get().strip()
                try:
                    datetime.strptime(start, "%H:%M")
                    datetime.strptime(end,   "%H:%M")
                    if start < end:
                        ranges.append([start, end])
                except ValueError:
                    pass
            schedule.set_day(day_i, active, ranges)
        print("🕐 Zamanlama kaydedildi.")
        win.destroy()


# ════════════════════════════════════════════════════════════════
#  STATISTICS WINDOW
# ════════════════════════════════════════════════════════════════
class StatsWindow:
    BG     = "#04080a"
    ACC    = "#00e5ff"
    ACC2   = "#00ff9d"
    FG     = "#cce8f0"
    DIM    = "#0d1f26"
    DIM2   = "#071318"

    def show(self, parent):
        win = tk.Toplevel(parent)
        win.title(s("stats_title"))
        win.configure(bg=self.BG)
        win.resizable(False, False)
        win.attributes("-topmost", True)

        W, H = 780, 560
        sw = parent.winfo_screenwidth()
        sh = parent.winfo_screenheight()
        win.geometry(f"{W}x{H}+{(sw-W)//2}+{(sh-H)//2}")

        tk.Label(win, text=s("stats_title"),
            font=font(18,"bold"), fg=self.ACC, bg=self.BG).pack(pady=(24,4))
        tk.Label(win, text=s("stats_subtitle"),
            font=font(11), fg="#3a7a90", bg=self.BG).pack(pady=(0,20))

        # ── Last 7 days bar chart ──
        tk.Label(win, text=s("stats_week"),
            font=font(10), fg="#3a7a90", bg=self.BG).pack(anchor="w", padx=40)

        bar_frame = tk.Frame(win, bg=self.BG)
        bar_frame.pack(fill="x", padx=40, pady=(6,20))

        days7 = stats.last_n_days(7)
        max_breaks = max((d["breaks"] for d in days7), default=1) or 1
        BAR_MAX_H = 80
        day_names_short = s("stats_days")

        for entry in days7:
            col = tk.Frame(bar_frame, bg=self.BG)
            col.pack(side="left", expand=True, fill="x", padx=3)

            bar_h = max(8, int(entry["breaks"] / max_breaks * BAR_MAX_H))
            spacer_h = BAR_MAX_H - bar_h

            tk.Frame(col, bg=self.BG, height=spacer_h).pack(fill="x")
            bar_color = self.ACC2 if entry["date"] == date.today().isoformat() else self.ACC
            if entry["breaks"] == 0:
                bar_color = "#1a3a50"
            bar = tk.Frame(col, bg=bar_color, height=bar_h, highlightthickness=0)
            bar.pack(fill="x")
            tk.Label(col, text=str(entry["breaks"]),
                font=font(11,"bold"),
                fg=self.ACC2 if entry["date"] == date.today().isoformat() else self.FG,
                bg=self.BG).pack()
            d = datetime.fromisoformat(entry["date"])
            tk.Label(col, text=day_names_short[d.weekday()],
                font=font(9), fg="#5a9ab0", bg=self.BG).pack()

        # Separator
        tk.Canvas(win, height=1, bg=self.DIM, highlightthickness=0).pack(fill="x", padx=40, pady=(0,16))

        # ── Monthly calendar ──
        tk.Label(win, text=s("stats_month"),
            font=font(10), fg="#3a7a90", bg=self.BG).pack(anchor="w", padx=40)

        cal_frame = tk.Frame(win, bg=self.BG)
        cal_frame.pack(padx=40, pady=(8,20), anchor="w")

        days30 = stats.last_n_days(30)
        max_b30 = max((d["breaks"] for d in days30), default=1) or 1

        # Color intensity — 5 levels
        def cell_color(breaks):
            if breaks == 0:   return "#112233"   # koyu mavi — görünür ama boş
            ratio = breaks / max_b30
            if ratio < 0.25:  return "#0d5c3a"   # koyu yeşil
            if ratio < 0.50:  return "#0f8f5a"   # orta yeşil
            if ratio < 0.75:  return "#00c47a"   # parlak yeşil
            return "#00ff9d"                      # tam parlak

        # 5 rows × 10 cols grid (30 days)
        COLS = 10
        for i, entry in enumerate(days30):
            row = i // COLS
            col_i = i % COLS
            color = cell_color(entry["breaks"])
            is_today = entry["date"] == date.today().isoformat()

            cell = tk.Frame(cal_frame, bg=color,
                width=48, height=48,
                highlightthickness=2 if is_today else 1,
                highlightbackground=self.ACC if is_today else "#1a4060")
            cell.grid(row=row, column=col_i, padx=3, pady=3)
            cell.pack_propagate(False)

            d = datetime.fromisoformat(entry["date"])
            tk.Label(cell, text=str(d.day),
                font=font(10,"bold"),
                fg="#ffffff" if entry["breaks"] > 0 else "#4a8aaa",
                bg=color).pack(expand=True)

            # Tooltip — show break count on hover
            def _enter(e, b=entry["breaks"], dt=entry["date"], c=cell):
                d2 = datetime.fromisoformat(dt)
                tip = f"{d2.strftime('%d %b')}  •  {b} mola"
                c.config(highlightbackground=self.ACC)
                self._show_tip(win, tip)
            def _leave(e, c=cell, is_t=is_today):
                c.config(highlightbackground=self.ACC if is_t else "#0d2a36")
                self._hide_tip()
            cell.bind("<Enter>", _enter)
            cell.bind("<Leave>", _leave)

        # Tooltip label (gizli, fare ile hareket eder)
        self._tip = tk.Label(win, text="", font=font(10),
            fg=self.FG, bg="#0d2a36", padx=10, pady=4,
            relief="flat", bd=0)

        # Kapat butonu
        tk.Button(win, text=s("stats_close"), command=win.destroy,
            font=font(11), fg=self.FG, bg=self.DIM,
            relief="flat", padx=20, pady=7, cursor="hand2").pack(pady=(0,20))

        return win

    def _show_tip(self, win, text):
        self._tip.config(text=text)
        # Position near mouse cursor
        x = win.winfo_pointerx() - win.winfo_rootx() + 14
        y = win.winfo_pointery() - win.winfo_rooty() - 32
        # Keep within window bounds
        if x + 160 > win.winfo_width():
            x -= 160
        if y < 0:
            y = win.winfo_pointery() - win.winfo_rooty() + 14
        self._tip.place(x=x, y=y)
        self._tip.lift()

    def _hide_tip(self):
        self._tip.place_forget()


class SettingsWindow:

    BG     = "#0a0f14"
    ACCENT = "#00e5ff"
    FG     = "#d0e8f4"
    DIM    = "#111c24"

    def __init__(self):
        self._win = None

    def show(self, parent: tk.Tk):
        if self._win and self._win.winfo_exists():
            self._win.lift()
            self._win.focus_force()
            return

        win = tk.Toplevel(parent)
        self._win = win
        win.title(s("settings_title"))
        win.configure(bg=self.BG)
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.grab_set()

        W, H = 500, 500   # yükseklik artırıldı
        sw = parent.winfo_screenwidth()
        sh = parent.winfo_screenheight()
        win.geometry(f"{W}x{H}+{(sw-W)//2}+{(sh-H)//2}")

        tk.Label(win, text=s("settings_title"),
                 font=font(17, "bold"),
                 bg=self.BG, fg=self.ACCENT).pack(pady=(26, 18))

        lkw = dict(bg=self.BG, fg=self.FG, anchor="w")

        # Work duration
        tk.Label(win, text=s("settings_work"), font=font(12), **lkw).pack(fill="x", padx=40)
        work_var = tk.IntVar(value=state.work_minutes)
        wf = tk.Frame(win, bg=self.BG); wf.pack(fill="x", padx=40, pady=(4, 14))
        tk.Scale(wf, from_=1, to=60, orient="horizontal", variable=work_var, length=360,
                 bg=self.BG, fg=self.FG, troughcolor=self.DIM,
                 highlightthickness=0, activebackground=self.ACCENT,
                 sliderlength=18).pack(side="left")
        tk.Label(wf, textvariable=work_var, width=3,
                 font=font(13, "bold"), bg=self.BG, fg=self.ACCENT).pack(side="left", padx=6)

        # Break duration
        tk.Label(win, text=s("settings_break"), font=font(12), **lkw).pack(fill="x", padx=40)
        break_var = tk.IntVar(value=state.break_seconds)
        bf = tk.Frame(win, bg=self.BG); bf.pack(fill="x", padx=40, pady=(4, 14))
        tk.Scale(bf, from_=5, to=120, orient="horizontal", variable=break_var, length=360,
                 bg=self.BG, fg=self.FG, troughcolor=self.DIM,
                 highlightthickness=0, activebackground=self.ACCENT,
                 sliderlength=18).pack(side="left")
        tk.Label(bf, textvariable=break_var, width=3,
                 font=font(13, "bold"), bg=self.BG, fg=self.ACCENT).pack(side="left", padx=6)

        # Hassasiyet
        tk.Label(win, text=s("settings_sens"), font=font(11),
                 bg=self.BG, fg="#7ab8cc", anchor="w",
                 wraplength=420, justify="left").pack(fill="x", padx=40)
        sens_var = tk.StringVar(value=state.sensitivity)
        sf = tk.Frame(win, bg=self.BG); sf.pack(fill="x", padx=40, pady=(6, 14))
        for val, key in [("low","sens_low"), ("med","sens_med"), ("high","sens_high")]:
            tk.Radiobutton(sf, text=s(key), variable=sens_var, value=val,
                           bg=self.BG, fg=self.FG, selectcolor=self.DIM,
                           activebackground=self.BG, activeforeground=self.ACCENT,
                           font=font(12)).pack(side="left", padx=16)

        # Separator
        tk.Canvas(win, height=1, bg="#1a3040", highlightthickness=0).pack(
            fill="x", padx=40, pady=(8, 14))

        # ── Auto-start ──
        autostart_var = tk.BooleanVar(value=autostart_is_enabled())
        af = tk.Frame(win, bg=self.BG); af.pack(fill="x", padx=40, pady=(0, 18))

        auto_lbl = tk.Label(af,
            text=s("settings_autostart"),
            font=font(12), bg=self.BG, fg=self.FG)
        auto_lbl.pack(side="left")

        def _toggle_auto():
            if autostart_var.get():
                autostart_enable()
                auto_status.config(text=s("autostart_on"), fg=self.ACCENT)
            else:
                autostart_disable()
                auto_status.config(text=s("autostart_off"), fg="#556677")

        tk.Checkbutton(af, variable=autostart_var, command=_toggle_auto,
            bg=self.BG, fg=self.FG, selectcolor=self.DIM,
            activebackground=self.BG, activeforeground=self.ACCENT,
            highlightthickness=0, bd=0).pack(side="right", padx=(8,0))

        auto_status = tk.Label(win,
            text=s("autostart_on") if autostart_var.get() else s("autostart_off"),
            font=font(10),
            fg=self.ACCENT if autostart_var.get() else "#556677",
            bg=self.BG)
        auto_status.pack()

        # Butonlar
        btnf = tk.Frame(win, bg=self.BG); btnf.pack(pady=(14,0))

        def save():
            state.update_settings(work_var.get(), break_var.get(), sens_var.get())
            print(f"⚙️  Kaydedildi: {state.work_minutes}dk / {state.break_seconds}sn / {state.sensitivity}")
            win.destroy()

        tk.Button(btnf, text=s("settings_save"), command=save,
                  font=font(12, "bold"), bg=self.ACCENT, fg=self.BG,
                  relief="flat", padx=24, pady=9, cursor="hand2").pack(side="left", padx=8)
        tk.Button(btnf, text=s("settings_cancel"), command=win.destroy,
                  font=font(12), bg=self.DIM, fg=self.FG,
                  relief="flat", padx=24, pady=9, cursor="hand2").pack(side="left", padx=8)

# ════════════════════════════════════════════════════════════════
#  ANA UYGULAMA  (tek tk.Tk() burada)
# ════════════════════════════════════════════════════════════════
class App:
    PANEL_BG   = "#0f1d2a"   # biraz daha açık lacivert
    PANEL_ACC  = "#00e5ff"
    PANEL_DIM  = "#1e3448"
    PANEL_FG   = "#dff0f8"
    PANEL_SUB  = "#7ab8cc"
    BREAK_BG   = "#0a1a0f"
    BREAK_ACC  = "#00ff9d"
    STATUS_COL = {
        "away":     "#00ff9d",
        "screen":   "#ff6b6b",
        "blink":    "#aaaaaa",
        "noface":   "#4a8866",
        "complete": "#00ff9d",
    }

    def __init__(self):
        self._settings_win  = SettingsWindow()
        self._gaze          = GazeWrapper()

        self._break_win     = None
        self._break_done    = Event()
        self._stop_cam      = Event()
        self._cam_status    = "noface"
        self._cam_remaining = 0.0
        self._cam_lock      = Lock()

        # FIX: double-close guard
        self._closing_break = False
        self._active_dialog = None   # açık olan dialog penceresi

        state.app = self

    # ── Kurulum ───────────────────────────────────────────────
    def run(self):
        r = tk.Tk()
        self.root = r
        # Add listener after root is created
        state.add_listener(self._on_state_change)
        r.title(s("app_name"))
        r.configure(bg=self.PANEL_BG)
        r.attributes("-fullscreen", True)
        r.protocol("WM_DELETE_WINDOW", self._hide_panel)

        self._build_panel()
        self._panel_tick()
        r.mainloop()

        # Mainloop bitti — temiz kapat
        self._gaze.shutdown()

    # ── Ana panel ─────────────────────────────────────────────
    def _build_panel(self):
        r = self.root
        W = r.winfo_screenwidth()
        H = r.winfo_screenheight()

        cv = tk.Canvas(r, bg=self.PANEL_BG, highlightthickness=0)
        cv.place(x=0, y=0, width=W, height=H)
        for cx, cy, rad, col in [
            (W*.08, H*.12, 280, "#162436"),
            (W*.92, H*.88, 230, "#122030"),
            (W*.50, H*.50, 160, "#162838"),
            (W*.75, H*.22, 110, "#12202e"),
        ]:
            cv.create_oval(cx-rad, cy-rad, cx+rad, cy+rad, fill=col, outline="")

        # Top-right buttons
        top = tk.Frame(r, bg=self.PANEL_BG)
        top.place(relx=1.0, rely=0.0, anchor="ne", x=-28, y=22)

        self._lang_btn = tk.Button(top, text=s("panel_lang_btn"),
            font=font(12,"bold"), fg=self.PANEL_ACC, bg=self.PANEL_DIM,
            activebackground="#0d2a36", activeforeground=self.PANEL_ACC,
            relief="flat", bd=0, padx=14, pady=6, cursor="hand2",
            command=self._toggle_lang)
        self._lang_btn.pack(side="left", padx=(0,8))

        self._set_btn = tk.Button(top, text=s("panel_settings"),
            font=font(12), fg="#8cc8dc", bg=self.PANEL_DIM,
            activebackground="#0d2a36", activeforeground=self.PANEL_FG,
            relief="flat", bd=0, padx=14, pady=6, cursor="hand2",
            command=self._open_settings)
        self._set_btn.pack(side="left", padx=(0,8))

        self._min_btn = tk.Button(top, text=f"⊟  {s('panel_minimize')}",
            font=font(12), fg="#8cc8dc", bg=self.PANEL_DIM,
            activebackground="#0d2a36", activeforeground=self.PANEL_FG,
            relief="flat", bd=0, padx=14, pady=6, cursor="hand2",
            command=self._hide_panel)
        self._min_btn.pack(side="left")

        # Merkez
        ctr = tk.Frame(r, bg=self.PANEL_BG)
        ctr.place(relx=0.5, rely=0.5, anchor="center")
        self._panel_ctr = ctr

        self._p_title = tk.Label(ctr, text=s("panel_title"),
            font=font(64,"bold"), fg=self.PANEL_ACC, bg=self.PANEL_BG)
        self._p_title.pack()

        self._p_sub = tk.Label(ctr, text=s("panel_subtitle"),
            font=font(18), fg=self.PANEL_SUB, bg=self.PANEL_BG)
        self._p_sub.pack(pady=(4,48))

        self._p_next = tk.Label(ctr, text=s("panel_next"),
            font=font(13), fg=self.PANEL_SUB, bg=self.PANEL_BG)
        self._p_next.pack()

        self._timer_var = tk.StringVar(value="--:--")
        tk.Label(ctr, textvariable=self._timer_var,
            font=font(96,"bold"), fg="#ffffff", bg=self.PANEL_BG).pack(pady=(4,0))

        # Timer underline — thick and bright
        tk.Canvas(ctr, width=420, height=3,
                  bg=self.PANEL_ACC, highlightthickness=0).pack(pady=(16,4))
        # Shadow effect — faint lines below
        tk.Canvas(ctr, width=420, height=2,
                  bg="#003a50", highlightthickness=0).pack()
        tk.Canvas(ctr, width=380, height=1,
                  bg="#001e2a", highlightthickness=0).pack(pady=(0,16))

        self._p_status = tk.Label(ctr, text=s("panel_working"),
            font=font(14), fg="#1ab880", bg=self.PANEL_BG)
        self._p_status.pack()

        # ── Stats summary card ──
        stats_card = tk.Frame(ctr,
            bg="#131f2e",
            highlightthickness=1,
            highlightbackground="#2a5070")
        stats_card.pack(pady=(28, 0), ipadx=10, ipady=10)

        # Card top border highlight
        tk.Canvas(stats_card, width=460, height=1,
                  bg="#3a6a8a", highlightthickness=0).pack(pady=(0,8))

        stats_row = tk.Frame(stats_card, bg="#131f2e")
        stats_row.pack(padx=10)

        # Today
        today_col = tk.Frame(stats_row, bg="#121f2e")
        today_col.pack(side="left", padx=24)
        self._lbl_today_hdr = tk.StringVar(value=s("panel_today"))
        self._lbl_mola1     = tk.StringVar(value=s("panel_mola"))
        tk.Label(today_col, textvariable=self._lbl_today_hdr, font=font(9), fg="#5a9ab0", bg="#121f2e").pack()
        self._stat_today_var = tk.StringVar(value="0")
        tk.Label(today_col, textvariable=self._stat_today_var,
            font=font(28,"bold"), fg=self.PANEL_ACC, bg="#121f2e").pack()
        tk.Label(today_col, textvariable=self._lbl_mola1, font=font(9), fg="#5a9ab0", bg="#121f2e").pack()

        tk.Canvas(stats_row, width=1, height=50, bg="#2a5070", highlightthickness=0).pack(side="left")

        # Bu hafta
        week_col = tk.Frame(stats_row, bg="#121f2e")
        week_col.pack(side="left", padx=24)
        self._lbl_week_hdr = tk.StringVar(value=s("panel_week"))
        self._lbl_mola2    = tk.StringVar(value=s("panel_mola"))
        tk.Label(week_col, textvariable=self._lbl_week_hdr, font=font(9), fg="#5a9ab0", bg="#121f2e").pack()
        self._stat_week_var = tk.StringVar(value="0")
        tk.Label(week_col, textvariable=self._stat_week_var,
            font=font(28,"bold"), fg=self.PANEL_ACC, bg="#121f2e").pack()
        tk.Label(week_col, textvariable=self._lbl_mola2, font=font(9), fg="#5a9ab0", bg="#121f2e").pack()

        tk.Canvas(stats_row, width=1, height=50, bg="#2a5070", highlightthickness=0).pack(side="left")

        # Today uzakta
        away_col = tk.Frame(stats_row, bg="#121f2e")
        away_col.pack(side="left", padx=24)
        self._lbl_away_hdr  = tk.StringVar(value=s("panel_away"))
        self._lbl_away_sub  = tk.StringVar(value=s("panel_bugun"))
        tk.Label(away_col, textvariable=self._lbl_away_hdr, font=font(9), fg="#5a9ab0", bg="#121f2e").pack()
        self._stat_away_var = tk.StringVar(value=f"0 {s('panel_dk')}")
        tk.Label(away_col, textvariable=self._stat_away_var,
            font=font(28,"bold"), fg=self.PANEL_ACC, bg="#121f2e").pack()
        tk.Label(away_col, textvariable=self._lbl_away_sub, font=font(9), fg="#5a9ab0", bg="#121f2e").pack()

        # Kart alt border
        tk.Canvas(stats_card, width=460, height=1,
                  bg="#1a3a50", highlightthickness=0).pack(pady=(8,0))

        # ── Action buttons ──
        btn_row = tk.Frame(ctr, bg=self.PANEL_BG)
        btn_row.pack(pady=(20, 0))

        BTN_STYLE = dict(
            font=font(11), relief="flat", bd=0,
            padx=0, pady=10, cursor="hand2",
            width=16,
            highlightthickness=1,
        )

        self._stats_btn = tk.Button(btn_row, text=s("panel_stats_btn"),
            fg="#7ab8cc", bg="#131f2e",
            activebackground="#1a3040", activeforeground=self.PANEL_ACC,
            highlightbackground="#2a5070",
            command=self._open_stats,
            **BTN_STYLE)
        self._stats_btn.grid(row=0, column=0, padx=6, pady=4)

        self._game_btn = tk.Button(btn_row,
            text=s("panel_game_btn"),
            fg="#7ab8cc", bg="#131f2e",
            activebackground="#1a3040", activeforeground="#00ff9d",
            highlightbackground="#2a5070",
            command=self._open_game_mode_dialog,
            **BTN_STYLE)
        self._game_btn.grid(row=0, column=1, padx=6, pady=4)

        self._schedule_btn = tk.Button(btn_row, text=s("panel_schedule_btn"),
            fg="#7ab8cc", bg="#131f2e",
            activebackground="#1a3040", activeforeground=self.PANEL_ACC,
            highlightbackground="#2a5070",
            command=self._open_schedule,
            **BTN_STYLE)
        self._schedule_btn.grid(row=0, column=2, padx=6, pady=4)

        self._game_status = tk.Label(ctr, text="",
            font=font(10), fg="#00ff9d", bg=self.PANEL_BG)
        self._game_status.pack(pady=(6,0))

        tk.Label(r, text="20 min  •  20 sec  •  20 ft",
            font=font(11), fg="#4a8aaa", bg=self.PANEL_BG).pack(side="bottom", pady=16)

    def _panel_tick(self):
        if state.schedule_active and not state.game_mode:
            remaining = max(0, state.next_break_time - time.time())
            m   = int(remaining // 60)
            sec = int(remaining  % 60)
            self._timer_var.set(f"{m:02d}:{sec:02d}")
        elif state.game_mode:
            # Game mode: timer frozen at full value
            self._timer_var.set(f"{state.work_minutes:02d}:00")
        else:
            # Schedule off: timer frozen
            self._timer_var.set("--:--")

        # Status text priority: schedule > game mode > normal
        if not state.schedule_active:
            now     = datetime.now()
            weekday = now.weekday()
            cfg     = schedule.get_day(weekday)
            now_str = now.strftime("%H:%M")
            if not cfg["active"]:
                status_text = s("panel_schedule_off")
            else:
                status_text = s("panel_schedule_off")
                for start, end in cfg["disabled_ranges"]:
                    if start <= now_str < end:
                        status_text = s("panel_schedule_range", start=start, end=end)
                        break
            self._p_status.config(text=status_text, fg="#888888")
        elif state.game_mode:
            self._p_status.config(text=s("panel_paused"), fg="#ffaa00")
        else:
            self._p_status.config(text=s("panel_working"), fg="#1ab880")

        self._stat_today_var.set(str(stats.today_breaks()))
        self._stat_week_var.set(str(stats.week_breaks()))
        away_min = int(stats.today_away_seconds() // 60)
        self._stat_away_var.set(f"{away_min} {s('panel_dk')}")
        # Update game mode remaining time
        if state.game_mode:
            self._refresh_game_mode_ui()
        self.root.after(1000, self._panel_tick)

    def _open_schedule(self):
        if self._is_dialog_open():
            self._active_dialog.lift()
            self._active_dialog.focus_force()
            return
        win = ScheduleWindow().show(self.root)
        if win:
            self._register_dialog(win)

    def _open_game_mode_dialog(self):
        if state.game_mode:
            state.disable_game_mode()
            self._refresh_game_mode_ui()
            return
        if self._is_dialog_open():
            self._active_dialog.lift()
            self._active_dialog.focus_force()
            return

        dlg = tk.Toplevel(self.root)
        dlg.title("Oyun Modu")
        dlg.configure(bg="#0e1a24")
        dlg.resizable(False, False)
        dlg.attributes("-topmost", True)
        dlg.grab_set()

        W, H = 360, 320
        dlg.geometry(f"{W}x{H}+{(self.root.winfo_screenwidth()-W)//2}+"
                     f"{(self.root.winfo_screenheight()-H)//2}")

        tk.Label(dlg, text=s("game_title"),
            font=font(18,"bold"), fg="#00ff9d", bg="#0e1a24").pack(pady=(24,6))
        tk.Label(dlg, text=s("game_subtitle"),
            font=font(10), fg="#5a9ab0", bg="#0e1a24").pack(pady=(0,20))
        tk.Label(dlg, text=s("game_duration"),
            font=font(11), fg="#cce8f0", bg="#0e1a24").pack()

        input_frame = tk.Frame(dlg, bg="#0e1a24")
        input_frame.pack(pady=14)

        tk.Label(input_frame, text=s("game_hour"), font=font(10), fg="#5a9ab0", bg="#0e1a24").grid(
            row=0, column=0, padx=(0,4))
        tk.Label(input_frame, text=s("game_minute"), font=font(10), fg="#5a9ab0", bg="#0e1a24").grid(
            row=0, column=2, padx=(12,0))

        hour_var = tk.StringVar(value="0")
        min_var  = tk.StringVar(value="30")

        hour_entry = tk.Entry(input_frame, textvariable=hour_var, width=4,
            font=font(16,"bold"), bg="#121f2e", fg="#00ff9d",
            insertbackground="#00ff9d", relief="flat",
            highlightthickness=1, highlightbackground="#2a5070",
            justify="center")
        hour_entry.grid(row=1, column=0)

        tk.Label(input_frame, text=":", font=font(18,"bold"),
            fg="#5a9ab0", bg="#0e1a24").grid(row=1, column=1, padx=4)

        min_entry = tk.Entry(input_frame, textvariable=min_var, width=4,
            font=font(16,"bold"), bg="#121f2e", fg="#00ff9d",
            insertbackground="#00ff9d", relief="flat",
            highlightthickness=1, highlightbackground="#2a5070",
            justify="center")
        min_entry.grid(row=1, column=2, padx=(12,0))

        err_lbl = tk.Label(dlg, text="", font=font(10), fg="#ff6b6b", bg="#0e1a24")
        err_lbl.pack()

        btn_frame = tk.Frame(dlg, bg="#0e1a24")
        btn_frame.pack(pady=10)

        def activate():
            try:
                h = int(hour_var.get() or 0)
                m = int(min_var.get()  or 0)
                if h < 0 or m < 0 or m > 59:
                    raise ValueError
                total_hours = h + m / 60
                state.enable_game_mode(hours=total_hours if total_hours > 0 else None)
                self._refresh_game_mode_ui()
                dlg.destroy()
            except ValueError:
                err_lbl.config(text=s("game_error"))

        def activate_unlimited():
            state.enable_game_mode(hours=None)
            self._refresh_game_mode_ui()
            dlg.destroy()

        tk.Button(btn_frame, text=s("game_start"),
            font=font(12,"bold"), fg="#0e1a24", bg="#00ff9d",
            activebackground="#00cc7a", relief="flat",
            padx=20, pady=8, cursor="hand2",
            command=activate).pack(side="left", padx=6)

        tk.Button(btn_frame, text=s("game_unlimited"),
            font=font(12,"bold"), fg="#00ff9d", bg="#0d2e1a",
            activebackground="#0f3d22", relief="flat",
            padx=20, pady=8, cursor="hand2",
            highlightthickness=1, highlightbackground="#00aa66",
            command=activate_unlimited).pack(side="left", padx=6)

        tk.Button(dlg, text=s("game_cancel"), command=dlg.destroy,
            font=font(10), fg="#5a9ab0", bg="#121f2e",
            relief="flat", padx=14, pady=6, cursor="hand2").pack(pady=(4,0))

        self._register_dialog(dlg)
        hour_entry.focus_set()

    def _refresh_game_mode_ui(self):
        try:
            if state.game_mode:
                self._game_btn.config(
                    text=s("panel_game_stop"),
                    fg="#00ff9d", bg="#0d2e1a",
                    highlightbackground="#00aa66")
                if state.game_mode_until:
                    rem = max(0, state.game_mode_until - time.time())
                    h   = int(rem // 3600)
                    m   = int((rem % 3600) // 60)
                    if h > 0:
                        self._game_status.config(text=s("game_remaining_h", h=h, m=m), fg="#00ff9d")
                    else:
                        self._game_status.config(text=s("game_remaining_m", m=m), fg="#00ff9d")
                else:
                    self._game_status.config(text=s("game_unlimited_lbl"), fg="#00ff9d")
            else:
                self._game_btn.config(
                    text=s("panel_game_btn"),
                    fg="#7ab8cc", bg="#121f2e",
                    highlightbackground="#2a5070")
                self._game_status.config(text="")
        except Exception:
            pass

    def _open_stats(self):
        if self._is_dialog_open():
            self._active_dialog.lift()
            self._active_dialog.focus_force()
            return
        if hasattr(self, '_stats_win_ref') and self._stats_win_ref and \
                self._stats_win_ref.winfo_exists():
            self._stats_win_ref.lift()
            self._stats_win_ref.focus_force()
            return
        win = StatsWindow().show(self.root)
        if win:
            self._stats_win_ref = win
            self._register_dialog(win)

    def _hide_panel(self):
        state.panel_visible = False
        self.root.withdraw()

    def restore_panel(self):
        state.panel_visible = True
        self.root.deiconify()
        self.root.attributes("-fullscreen", True)
        self.root.lift()
        self.root.focus_force()

    def _toggle_lang(self):
        state.set_lang("en" if state.lang == "tr" else "tr")

    def _open_settings(self):
        if self._is_dialog_open():
            self._active_dialog.lift()
            self._active_dialog.focus_force()
            return
        self._settings_win.show(self.root)

    def _on_state_change(self):
        try:
            if hasattr(self, 'root') and self.root and self.root.winfo_exists():
                self.root.after(0, self._refresh_panel_labels)
        except Exception:
            pass

    def _is_dialog_open(self) -> bool:
        """Herhangi bir dialog açıksa True döner."""
        return (self._active_dialog is not None and
                self._active_dialog.winfo_exists())

    def _register_dialog(self, win):
        """Dialog'u aktif olarak kaydet, kapanınca temizle."""
        self._active_dialog = win
        win.protocol("WM_DELETE_WINDOW", lambda: self._close_dialog(win))
        win.bind("<Destroy>", lambda e: self._clear_dialog(win))

    def _close_dialog(self, win):
        self._clear_dialog(win)
        try: win.destroy()
        except Exception: pass

    def _clear_dialog(self, win):
        if self._active_dialog is win:
            self._active_dialog = None

    def _refresh_panel_labels(self):
        try:
            self._lang_btn.config(text=s("panel_lang_btn"))
            self._set_btn.config(text=s("panel_settings"))
            self._min_btn.config(text=f"⊟  {s('panel_minimize')}")
            self._p_title.config(text=s("panel_title"))
            self._p_sub.config(text=s("panel_subtitle"))
            self._p_next.config(text=s("panel_next"))
            self._p_status.config(text=s("panel_working"))
            # Stats kart etiketleri
            self._lbl_today_hdr.set(s("panel_today"))
            self._lbl_week_hdr.set(s("panel_week"))
            self._lbl_away_hdr.set(s("panel_away"))
            self._lbl_mola1.set(s("panel_mola"))
            self._lbl_mola2.set(s("panel_mola"))
            self._lbl_away_sub.set(s("panel_bugun"))
            # Butonlar
            self._stats_btn.config(text=s("panel_stats_btn"))
            self._schedule_btn.config(text=s("panel_schedule_btn"))
            self._game_btn.config(
                text=s("panel_game_stop") if state.game_mode else s("panel_game_btn"))
        except Exception:
            pass

    # ── Break overlay ──────────────────────────────────────────
    def open_break(self):
        # FIX: reset closing flag and break_done here —
        # must be clean before _break_ui_tick starts
        self._closing_break = False
        self._break_done.clear()
        self._stop_cam.clear()

        # FIX: reinitialize GazeWrapper (reopen() instead of close())
        self._gaze.reopen()

        win = tk.Toplevel(self.root)
        self._break_win = win
        win.attributes("-fullscreen", True)
        win.attributes("-topmost", True)
        win.configure(bg=self.BREAK_BG)
        win.protocol("WM_DELETE_WINDOW", lambda: None)
        win.focus_force()
        win.grab_set()

        W = win.winfo_screenwidth()
        H = win.winfo_screenheight()

        bg_cv = tk.Canvas(win, bg=self.BREAK_BG, highlightthickness=0)
        bg_cv.place(x=0, y=0, width=W, height=H)
        for cx, cy, rad, col in [
            (W*.15, H*.20, 300, "#0d2b14"),
            (W*.85, H*.75, 250, "#0a2010"),
            (W*.50, H*.50, 180, "#0f3018"),
        ]:
            bg_cv.create_oval(cx-rad, cy-rad, cx+rad, cy+rad, fill=col, outline="")

        ctr = tk.Frame(win, bg=self.BREAK_BG)
        ctr.place(relx=0.5, rely=0.5, anchor="center")
        self._break_ctr = ctr

        self._b_title = tk.Label(ctr, text=s("break_title"),
            font=font(72,"bold"), fg=self.BREAK_ACC, bg=self.BREAK_BG)
        self._b_title.pack(pady=(0,6))

        self._b_sub = tk.Label(ctr, text=s("break_subtitle"),
            font=font(26), fg="#aaffcc", bg=self.BREAK_BG)
        self._b_sub.pack()

        self._b_rule = tk.Label(ctr, text=s("break_rule"),
            font=font(13), fg="#4a8866", bg=self.BREAK_BG)
        self._b_rule.pack(pady=(4,28))

        self._break_remaining_var = tk.StringVar(value=str(state.break_seconds))
        tk.Label(ctr, textvariable=self._break_remaining_var,
            font=font(108,"bold"), fg="#ffffff", bg=self.BREAK_BG).pack()

        bar_w = 500
        self._bar_w = bar_w
        bar = tk.Canvas(ctr, width=bar_w, height=10,
                        bg="#0f2418", highlightthickness=0, bd=0)
        bar.pack(pady=(8,28))
        bar.create_rectangle(0, 0, 0, 10, fill=self.BREAK_ACC, outline="", tags="bar")
        self._progress_cv = bar

        self._b_status_var = tk.StringVar(value=s("status_noface"))
        self._b_status_lbl = tk.Label(ctr, textvariable=self._b_status_var,
            font=font(20), fg=self.STATUS_COL["noface"], bg=self.BREAK_BG)
        self._b_status_lbl.pack()

        self._b_watching = tk.Label(win, text=s("break_watching"),
            font=font(12), fg="#2a5040", bg=self.BREAK_BG)
        self._b_watching.pack(side="bottom", pady=18)

        Thread(target=self._camera_loop, daemon=True).start()
        self._break_ui_tick()

    def _break_ui_tick(self):
        """50ms'de bir kamera verisini UI'ye yazar."""
        if not self._break_win or not self._break_win.winfo_exists():
            return

        with self._cam_lock:
            status    = self._cam_status
            remaining = self._cam_remaining

        color = self.STATUS_COL.get(status, "#556655")
        try:
            self._break_remaining_var.set(str(int(math.ceil(remaining))))
            self._b_status_var.set(s(f"status_{status}"))
            self._b_status_lbl.config(fg=color)
            pct = max(0.0, min(1.0, 1.0 - remaining / state.break_seconds))
            self._progress_cv.coords("bar", 0, 0, self._bar_w * pct, 10)
            bar_color = "#ffffff" if pct >= 1.0 else self.BREAK_ACC
            self._progress_cv.itemconfig("bar", fill=bar_color)
        except Exception:
            pass

        # FIX: double-close prevented with _closing_break flag
        if self._break_done.is_set():
            if not self._closing_break:
                self._closing_break = True
                self._close_break()
            return

        self._break_win.after(50, self._break_ui_tick)

    def _close_break(self):
        """Mola ekranını kapat, kamera thread'ini durdur, paneli geri getir."""
        self._stop_cam.set()

        if self._break_win:
            try:
                self._break_win.grab_release()
                self._break_win.destroy()
            except Exception:
                pass
            self._break_win = None

        # If panel was hidden (tray mode) before break, go back to tray
        if not state.panel_visible:
            self.root.withdraw()
        else:
            self.restore_panel()

    def show_break_done(self):
        """Mola başarıyla tamamlandı — ekrana yaz, 2 sn sonra kapat."""
        if not self._break_win or not self._break_win.winfo_exists():
            return
        # FIX: double-close guard
        if self._closing_break:
            return
        try:
            for w in self._break_ctr.winfo_children():
                w.destroy()
            tk.Label(self._break_ctr,
                text=s("break_done"),
                font=font(56,"bold"),
                fg=self.BREAK_ACC, bg=self.BREAK_BG).pack(expand=True, pady=60)
        except Exception:
            pass
        self._break_win.after(2000, self._do_close_after_done)

    def _do_close_after_done(self):
        """show_break_done'ın 2 sn gecikmeli kapama callback'i."""
        # FIX: set _closing_break flag before closing
        if not self._closing_break:
            self._closing_break = True
            self._close_break()

    # ── Camera / gaze loop (separate thread) ──────────────────────
    def _camera_loop(self):
        """
        Sadece veri üretir, UI'ye dokunmaz.
        FIX: finally'de gaze.shutdown() YOK — reopen() ile yeniden kullanılacak.
        FIX: _stop_cam.is_set() kontrolü eklendi.
        """
        if not GAZE_AVAILABLE:
            print(s("no_gaze_lib"))
            self._break_done.set()
            return

        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("❌ Kamera açılamadı!")
            self._break_done.set()
            return

        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS,          15)

        # Logic:
        # away_elapsed → accumulates total time spent looking away
        # Resets on screen gaze, freezes on blink/noface
        away_elapsed  = 0.0
        away_seg_start = None   # mevcut "uzağa bakış" segmentinin başlangıcı
        last_status   = None

        try:
            while not self._stop_cam.is_set() and not self._break_done.is_set():
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.1)
                    continue

                status = self._gaze.analyze(frame)
                now    = time.time()

                if status != last_status:
                    last_status = status

                if status == "away":
                    if away_seg_start is None:
                        away_seg_start = now

                    total     = away_elapsed + (now - away_seg_start)
                    remaining = max(0.0, state.break_seconds - total)

                    final_status = "complete" if total >= state.break_seconds else "away"
                    with self._cam_lock:
                        self._cam_status    = final_status
                        self._cam_remaining = remaining

                    if total >= state.break_seconds:
                        print(s("console_done"))
                        play_sound("done")
                        # Record to statistics
                        stats.record_break(away_seconds=total)
                        safe_after(self.root, self.show_break_done)
                        self._break_done.set()
                        break

                else:
                    # screen, blink, noface — all pause the timer, never reset
                    if away_seg_start is not None:
                        away_elapsed  += now - away_seg_start
                        away_seg_start = None

                    remaining = max(0.0, state.break_seconds - away_elapsed)
                    with self._cam_lock:
                        self._cam_status    = status
                        self._cam_remaining = remaining

                time.sleep(0.07)

        finally:
            cap.release()
            # FIX: gaze.shutdown() NOT called — object will be reused

# ════════════════════════════════════════════════════════════════
#  TRAY ICON
# ════════════════════════════════════════════════════════════════
def _make_icon(size=64):
    img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2
    draw.ellipse([4, cy-18, size-4, cy+18], fill=(0, 229, 255))
    draw.ellipse([cx-11, cy-11, cx+11, cy+11], fill=(4, 8, 10))
    draw.ellipse([cx-5,  cy-5,  cx+5,  cy+5],  fill=(0, 180, 200))
    draw.ellipse([cx+3,  cy-7,  cx+7,  cy-3],  fill=(255, 255, 255))
    return img

def _fmt_next():
    rem = max(0, state.next_break_time - time.time())
    return f"{s('next_break_in')}: {int(rem//60)}{s('min')} {int(rem%60):02d}{s('sec')}"

def _open_panel(icon=None, item=None):
    if state.app:
        safe_after(state.app.root, state.app.restore_panel)

def _tray_lang(icon, item):
    # FIX: set_lang touches UI and state, delegate to main thread via safe_after
    if state.app:
        safe_after(state.app.root, lambda: state.set_lang(
            "en" if state.lang == "tr" else "tr"
        ))
    if state.tray_icon:
        # Refresh menu — safe in pystray thread
        state.tray_icon.title = s("app_name")
        state.tray_icon.menu  = _build_tray_menu()

def _quit(icon=None, item=None):
    state.running = False
    if state.tray_icon:
        state.tray_icon.stop()
    # FIX: root.quit() called from main thread via safe_after
    if state.app:
        safe_after(state.app.root, state.app.root.quit)

def _tray_game_mode(icon, item):
    if state.game_mode:
        state.disable_game_mode()
        if state.app:
            safe_after(state.app.root, state.app._refresh_game_mode_ui)
    else:
        # Default 2 hours when triggered from tray
        state.enable_game_mode(hours=2)
        if state.app:
            safe_after(state.app.root, state.app._refresh_game_mode_ui)
    if state.tray_icon:
        state.tray_icon.menu = _build_tray_menu()

def _build_tray_menu():
    game_label = s("tray_game_on") if state.game_mode else s("tray_game_off")
    return pystray.Menu(
        pystray.MenuItem(s("tray_open"),     _open_panel, default=True),
        pystray.MenuItem(lambda item: _fmt_next(), None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(game_label,         _tray_game_mode),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(s("tray_settings"),
                         lambda i, it: safe_after(state.app.root,
                                                   lambda: state.app._open_settings())
                         if state.app else None),
        pystray.MenuItem(s("tray_lang"),     _tray_lang),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(s("tray_quit"),     _quit),
    )

def _run_tray():
    if not TRAY_AVAILABLE:
        return
    icon = pystray.Icon("eyeguard", _make_icon(), s("app_name"), _build_tray_menu())
    state.tray_icon = icon

    def _refresh():
        while state.running:
            time.sleep(5)
            try:
                icon.title = f"{s('app_name')} — {_fmt_next()}"
                icon.menu  = _build_tray_menu()
            except Exception:
                pass
    Thread(target=_refresh, daemon=True).start()
    icon.run()

# ════════════════════════════════════════════════════════════════
#  ZAMANLAYICI
# ════════════════════════════════════════════════════════════════
_settings_changed = Event()

def _on_settings_changed():
    _settings_changed.set()

state.add_listener(_on_settings_changed)

def _timer_loop():
    print(s("console_start"))
    print(s("console_info", w=state.work_minutes, b=state.break_seconds))

    while state.running:
        # ── Schedule check ──
        if not schedule.should_be_active():
            state.schedule_active = False
            # Fast check when panel visible, slow when in tray
            time.sleep(3 if state.panel_visible else 60)
            continue
        else:
            state.schedule_active = True

        # ── Game mode check ──
        if state.game_mode:
            # Has the duration expired?
            if state.game_mode_until and time.time() >= state.game_mode_until:
                state.disable_game_mode()
                if state.app:
                    safe_after(state.app.root, state.app._refresh_game_mode_ui)
            else:
                # Freeze timer — keep advancing next_break_time
                state.next_break_time = time.time() + state.work_minutes * 60
                time.sleep(1)
                continue

        work_secs = state.work_minutes * 60
        state.next_break_time = time.time() + work_secs
        _settings_changed.clear()

        elapsed      = 0
        warned       = False
        sched_check  = 0   # schedule'ı her saniye değil arada kontrol et
        while elapsed < work_secs:
            if not state.running:
                return
            if _settings_changed.is_set():
                print(f"⚙️  Ayarlar güncellendi — {state.work_minutes}dk ile yeniden başlıyor")
                break
            if state.game_mode:
                break
            # Check schedule every 3s if panel visible, every 60s if in tray
            sched_check += 1
            check_interval = 3 if state.panel_visible else 60
            if sched_check >= check_interval:
                sched_check = 0
                if not schedule.should_be_active():
                    state.schedule_active = False
                    break
            state.schedule_active = True
            if not warned and (work_secs - elapsed) <= 60:
                warned = True
                play_sound("warning")
                print("🔔 Molaya 60 saniye kaldı!")
            time.sleep(1)
            elapsed += 1

        if _settings_changed.is_set() or state.game_mode or not state.schedule_active:
            continue
        if not state.running:
            return

        # MOLA
        print(s("console_break"))
        state.on_break = True
        play_sound("break")

        if state.app:
            state.app._break_done.clear()
            # If in tray, show root first then open break
            def _start_break():
                try:
                    r = state.app.root
                    r.deiconify()
                    r.update()
                    r.attributes("-fullscreen", True)
                    r.update()
                    state.app.open_break()
                except Exception as e:
                    print(f"Break open error: {e}")
            try:
                state.app.root.after(0, _start_break)
            except Exception:
                pass

        while state.app and not state.app._break_done.is_set() and state.running:
            time.sleep(0.5)

        state.on_break = False

# ════════════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════════════
def main():
    if not GAZE_AVAILABLE:
        print("=" * 50)
        print("❌  mediapipe bulunamadı!")
        print("    pip install mediapipe opencv-python")
        print("=" * 50)

    if TRAY_AVAILABLE:
        Thread(target=_run_tray, daemon=True).start()

    Thread(target=_timer_loop, daemon=True).start()

    app = App()
    app.run()

    print("👋 Çıkış / Exited.")

if __name__ == "__main__":
    main()