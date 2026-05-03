"""
HUGR — ITC Spirit Communication Tool  v3
For Viggeir / Daniel Van Nattan

Dual-mode microphone:
  SPEAKING  → speech transcribed, displayed as your question
  SILENT    → full FFT spectrum of ambient audio maps to words

Full spectrum mapping:
  The FFT of the ambient room is computed.
  The dominant frequency bin index is used to select a word
  deterministically from the vocabulary. Different rooms,
  different atmospheric conditions, different moments in time
  produce different words. Your voice does not drive this.

Speech transcription via Windows SAPI (requires pywin32).
Without pywin32, transcription is disabled but everything else works.
"""

import sys
import random
import math
import threading
import collections
import time

import numpy as np
import sounddevice as sd

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSlider, QFrame, QSizePolicy, QScrollArea
)
from PySide6.QtCore import Qt, QTimer, QObject, Signal, QRect
from PySide6.QtGui import (
    QPainter, QColor, QPen, QFont, QLinearGradient, QBrush, QRadialGradient
)

# ─────────────────────────────────────────────
# COLOURS
# ─────────────────────────────────────────────

BG         = QColor(8, 6, 4)
BG_PANEL   = QColor(14, 11, 8)
BG_MSG     = QColor(18, 14, 10)
EMBER      = QColor(196, 112, 28)
EMBER_DIM  = QColor(100, 58, 14)
EMBER_GLOW = QColor(220, 140, 40)
ASH        = QColor(60, 55, 50)
TEXT_DIM   = QColor(80, 72, 60)
TEXT_MID   = QColor(140, 125, 100)
TEXT_FULL  = QColor(200, 185, 155)
SPECTR_LOW = QColor(20, 14, 8)
SPECTR_MID = QColor(100, 50, 10)
SPECTR_HI  = QColor(220, 140, 40)

# ─────────────────────────────────────────────
# VOCABULARY — ordered list
# Position in this list is what the spectrum maps to.
# The full FFT dominant bin selects an index into this list.
# Order is intentional — adjacent words have cosmological
# relationship so nearby frequency bins produce related words.
# ─────────────────────────────────────────────

VOCABULARY = [
    # Soul anatomy cluster (0-9)
    ("hugr",         "mind"),
    ("hamr",         "shape"),
    ("fylgja",       "follower"),
    ("önd",          "breath"),
    ("óðr",          "frenzy"),
    ("líkamr",       "body"),
    ("hamingja",     "luck-force"),
    ("hugprúðr",     "courage"),
    ("sjálfsvirðing","self-worth"),
    ("ótti",         "fear"),

    # Underworld cluster (10-19)
    ("niflhel",      "deep dark"),
    ("niflhelsbúar", "dark friends"),
    ("helvegr",      "hel road"),
    ("náströnd",     "corpse shore"),
    ("þögn",         "silence"),
    ("myrkr",        "darkness"),
    ("ginnungagap",  "void"),
    ("inbetween",    "between"),
    ("hamlausir",    "formless"),
    ("hugr-sending", "projection"),

    # Fate cluster (20-29)
    ("ørlög",        "primal law"),
    ("wyrd",         "woven fate"),
    ("nornir",       "the fates"),
    ("urðr",         "what was"),
    ("verðandi",     "what is"),
    ("skuld",        "what shall be"),
    ("þráðr",        "thread"),
    ("lag",          "layer"),
    ("dauðadagr",    "death day"),
    ("perthro",      "hidden fate"),

    # Warrior / bond cluster (30-39)
    ("viggeir",      "warrior"),
    ("skjaldmær",    "shield maiden"),
    ("bróðir",       "brother"),
    ("eiðr",         "oath"),
    ("blóð",         "blood"),
    ("járn",         "iron"),
    ("drengskapr",   "honour"),
    ("tryggð",       "fidelity"),
    ("frœkn",        "bold"),
    ("fóstbróðralag","sworn brotherhood"),

    # Ancestral cluster (40-49)
    ("forfeðr",      "ancestor"),
    ("ætt",          "lineage"),
    ("minni",        "memory"),
    ("arfr",         "inheritance"),
    ("othala",       "ancestral land"),
    ("hamingja",     "luck-force"),
    ("blóð",         "blood"),
    ("draugr",       "revenant"),
    ("maðr forni",   "ancient man"),
    ("sjónhverfing", "sight-turning"),

    # Magic / craft cluster (50-59)
    ("seiðr",        "magic"),
    ("galdr",        "charm"),
    ("útiseta",      "sitting out"),
    ("varðlokkur",   "warding song"),
    ("rún",          "rune"),
    ("hamfarir",     "spirit journey"),
    ("völva",        "seeress"),
    ("nákváma",      "corpse-waking"),
    ("seiðr-dvali",  "trance"),
    ("útangarðs",    "beyond the boundary"),

    # Runes cluster (60-77)
    ("fehu",         "abundance"),
    ("uruz",         "vitality"),
    ("thurisaz",     "thorn"),
    ("ansuz",        "divine voice"),
    ("raidho",       "journey"),
    ("kenaz",        "torch"),
    ("gebo",         "gift"),
    ("wunjo",        "joy"),
    ("hagalaz",      "disruption"),
    ("nauthiz",      "need"),
    ("isa",          "stillness"),
    ("jera",         "harvest"),
    ("eihwaz",       "world axis"),
    ("algiz",        "protection"),
    ("sowilo",       "victory"),
    ("tiwaz",        "justice"),
    ("berkano",      "birth"),
    ("ehwaz",        "trust"),
    ("mannaz",       "self"),
    ("laguz",        "depth"),
    ("ingwaz",       "potential"),
    ("dagaz",        "dawn"),

    # Emotional / state cluster (82-94)
    ("heim",         "home"),
    ("einvera",      "solitude"),
    ("sorg",         "grief"),
    ("gleði",        "joy"),
    ("þrá",          "longing"),
    ("ást",          "love"),
    ("reiði",        "anger"),
    ("friðr",        "peace"),
    ("traust",       "trust"),
    ("þekkja",       "knowing"),
    ("finna",        "find"),
    ("leita",        "seek"),
    ("vakna",        "wake"),

    # Elemental / action cluster (95-109)
    ("eldr",         "fire"),
    ("vatn",         "water"),
    ("stormr",       "storm"),
    ("vindr",        "wind"),
    ("jörð",         "earth"),
    ("ís",           "ice"),
    ("ljós",         "light"),
    ("rísa",         "rise"),
    ("falla",        "fall"),
    ("standa",       "stand"),
    ("halda",        "hold"),
    ("hlusta",       "listen"),
    ("sjá",          "see"),
    ("heyra",        "hear"),
    ("muna",         "remember"),

    # Cosmos cluster (110-119)
    ("yggdrasil",    "world tree"),
    ("ásgarðr",      "god realm"),
    ("miðgarðr",     "middle world"),
    ("jötunheimr",   "giant world"),
    ("valhöll",      "hall of slain"),
    ("bifröst",      "rainbow bridge"),
    ("urðarbrunnr",  "well of fate"),
    ("hvergelmir",   "bubbling spring"),
    ("ragnarök",     "doom of gods"),
    ("ginnungagap",  "primal void"),
]

VOCAB_SIZE = len(VOCABULARY)


def spectrum_to_words(fft_bins, count):
    """
    Map the full FFT spectrum to 'count' words deterministically.

    Method:
    - Find the top 'count' dominant frequency bins
    - Each dominant bin index, scaled to VOCAB_SIZE, selects a word
    - This means the actual frequency content of the ambient audio
      determines which words surface. Different audio = different words.
    """
    if fft_bins is None or len(fft_bins) == 0:
        return [random.choice(VOCABULARY)]

    n = len(fft_bins)
    # Get top 'count' peak bin indices (not adjacent to each other)
    # to avoid selecting the same harmonic multiple times
    peaks = []
    bins_copy = fft_bins.copy()

    for _ in range(count):
        idx = int(np.argmax(bins_copy))
        peaks.append(idx)
        # Null out surrounding bins (window of 5% of spectrum)
        window = max(3, n // 20)
        lo = max(0, idx - window)
        hi = min(n, idx + window)
        bins_copy[lo:hi] = 0.0

    words = []
    for peak in peaks:
        # Map bin index to vocabulary index
        vocab_idx = int((peak / n) * VOCAB_SIZE) % VOCAB_SIZE
        words.append(VOCABULARY[vocab_idx])

    return words


# ─────────────────────────────────────────────
# AUDIO ENGINE
# Dual mode: speech detection vs ambient capture
# ─────────────────────────────────────────────

SAMPLE_RATE    = 44100
BLOCK_SIZE     = 1024
FFT_SIZE       = 4096   # larger FFT = better frequency resolution
NUM_BINS       = 120
SPEECH_THRESH  = 0.08   # RMS above this = speaking (higher = less sensitive)
SILENCE_HOLD   = 1.8    # seconds of silence before switching to ambient mode
AMBIENT_WINDOW = 3.0    # seconds of ambient audio to accumulate for analysis


class AudioEngine(QObject):
    fft_ready      = Signal(np.ndarray)   # for spectrogram display
    speech_start   = Signal()             # user started speaking
    speech_end     = Signal()             # user stopped speaking
    ambient_ready  = Signal(np.ndarray)   # accumulated ambient FFT ready

    def __init__(self):
        super().__init__()
        self.noise_volume  = 0.12
        self.mic_volume    = 0.90
        self.running       = False
        self._stream       = None
        self._lock         = threading.Lock()

        # FFT buffer for spectrogram
        self._fft_buffer   = collections.deque(maxlen=FFT_SIZE)

        # Ambient accumulation buffer
        self._ambient_buf  = collections.deque(
            maxlen=int(SAMPLE_RATE * AMBIENT_WINDOW)
        )

        # Speech state tracking
        self._is_speaking     = False
        self._silence_since   = None
        self._last_rms        = 0.0
        self._speech_thresh   = SPEECH_THRESH  # adjustable live

        # Ambient emission timer (emit ambient FFT every N seconds when silent)
        self._ambient_counter = 0
        self._ambient_emit_every = int(SAMPLE_RATE * AMBIENT_WINDOW / BLOCK_SIZE)

    def set_noise_volume(self, v):
        with self._lock:
            self.noise_volume = v

    def set_mic_volume(self, v):
        with self._lock:
            self.mic_volume = v

    def start(self):
        self.running = True
        try:
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                blocksize=BLOCK_SIZE,
                channels=1,
                dtype='float32',
                callback=self._callback
            )
            self._stream.start()
            return True
        except Exception:
            self.running = False
            return False

    def stop(self):
        self.running = False
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def _callback(self, indata, frames, time_info, status):
        if not self.running:
            return

        with self._lock:
            nv = self.noise_volume
            mv = self.mic_volume

        mic_raw = indata[:, 0]
        rms     = float(np.sqrt(np.mean(mic_raw ** 2)))
        self._last_rms = rms

        # ── Speech detection ──
        currently_speaking = rms > self._speech_thresh

        if currently_speaking and not self._is_speaking:
            self._is_speaking   = True
            self._silence_since = None
            self.speech_start.emit()

        elif not currently_speaking and self._is_speaking:
            if self._silence_since is None:
                self._silence_since = time.time()
            elif time.time() - self._silence_since > SILENCE_HOLD:
                self._is_speaking   = False
                self._silence_since = None
                self.speech_end.emit()

        elif not currently_speaking and not self._is_speaking:
            self._silence_since = None

        # ── Ambient buffer (only when not speaking) ──
        if not self._is_speaking:
            self._ambient_buf.extend(mic_raw.tolist())
            self._ambient_counter += 1

            if self._ambient_counter >= self._ambient_emit_every:
                self._ambient_counter = 0
                self._emit_ambient_fft()

        # ── Display FFT (always, mixed with noise) ──
        noise  = np.random.uniform(-1, 1, frames).astype(np.float32) * nv
        mixed  = mic_raw * mv + noise
        self._fft_buffer.extend(mixed.tolist())

        if len(self._fft_buffer) >= FFT_SIZE:
            arr      = np.array(list(self._fft_buffer)[-FFT_SIZE:])
            window   = np.hanning(FFT_SIZE)
            spectrum = np.abs(np.fft.rfft(arr * window))
            half     = len(spectrum)
            indices  = np.linspace(0, half - 1, NUM_BINS, dtype=int)
            bins     = spectrum[indices]
            bins     = np.log1p(bins)
            peak     = bins.max()
            if peak > 0:
                bins = bins / peak
            self.fft_ready.emit(bins)

    def _emit_ambient_fft(self):
        if len(self._ambient_buf) < FFT_SIZE:
            return
        arr      = np.array(list(self._ambient_buf)[-FFT_SIZE:])
        window   = np.hanning(FFT_SIZE)
        spectrum = np.abs(np.fft.rfft(arr * window))
        # Return full half-spectrum normalised
        spectrum = np.log1p(spectrum)
        peak     = spectrum.max()
        if peak > 0:
            spectrum = spectrum / peak
        self.ambient_ready.emit(spectrum)


# ─────────────────────────────────────────────
# SPEECH RECOGNISER
# ─────────────────────────────────────────────

class SpeechWorker(QObject):
    text_ready = Signal(str)
    available  = Signal(bool)

    def __init__(self):
        super().__init__()
        self._running  = False
        self._backend  = self._detect_backend()

    def _detect_backend(self):
        """
        Try backends in order:
        1. SpeechRecognition library (pip install SpeechRecognition) — most reliable
        2. win32com SAPI event sink — Windows built-in
        3. None — transcription disabled
        """
        try:
            import speech_recognition
            return "sr"
        except ImportError:
            pass
        try:
            import win32com.client
            return "sapi"
        except ImportError:
            pass
        return None

    def is_available(self):
        return self._backend is not None

    def backend_name(self):
        return self._backend or "none"

    def start(self):
        if not self._backend:
            self.available.emit(False)
            return
        self._running = True
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()
        self.available.emit(True)

    def stop(self):
        self._running = False

    def _loop(self):
        if self._backend == "sr":
            self._loop_sr()
        elif self._backend == "sapi":
            self._loop_sapi()

    def _loop_sr(self):
        """
        Uses the SpeechRecognition library with Windows built-in recogniser.
        Listens in a continuous loop, emits text when recognised.
        """
        try:
            import speech_recognition as sr
            recogniser = sr.Recognizer()
            recogniser.energy_threshold     = 400
            recogniser.dynamic_energy_threshold = True
            recogniser.pause_threshold      = 0.8

            mic = sr.Microphone()
            with mic as source:
                recogniser.adjust_for_ambient_noise(source, duration=1)

            while self._running:
                try:
                    with mic as source:
                        audio = recogniser.listen(
                            source,
                            timeout=3,
                            phrase_time_limit=8
                        )
                    # Use Windows Speech Recognition (sphinx offline fallback)
                    try:
                        text = recogniser.recognize_google(audio)
                    except Exception:
                        try:
                            text = recogniser.recognize_sphinx(audio)
                        except Exception:
                            continue
                    if text and text.strip():
                        self.text_ready.emit(text.strip())
                except sr.WaitTimeoutError:
                    pass
                except Exception:
                    time.sleep(0.5)

        except Exception:
            self.available.emit(False)

    def _loop_sapi(self):
        """
        Windows SAPI via win32com.
        Uses event-driven recognition rather than polling.
        """
        try:
            import win32com.client
            import pythoncom
            pythoncom.CoInitialize()

            # Use in-process recogniser for better control
            recogniser = win32com.client.Dispatch("SAPI.SpInProcRecognizer")
            audio_in   = win32com.client.Dispatch("SAPI.SpMMAudioIn")
            recogniser.AudioInput = audio_in

            context = recogniser.CreateRecoContext()
            grammar = context.CreateGrammar(0)
            grammar.DictationSetState(1)

            # Wire up event handler
            speech_signal = self.text_ready

            class RecoHandler:
                def OnRecognition(self, stream_num, stream_pos, rec_type, result_obj):
                    try:
                        phrase = result_obj.PhraseInfo.GetText()
                        if phrase and phrase.strip():
                            speech_signal.emit(phrase.strip())
                    except Exception:
                        pass

            context_events = win32com.client.WithEvents(context, RecoHandler)

            while self._running:
                pythoncom.PumpWaitingMessages()
                time.sleep(0.05)

        except Exception:
            # Fall back gracefully
            self.available.emit(False)


# ─────────────────────────────────────────────
# SPECTROGRAM
# ─────────────────────────────────────────────

class SpectrogramWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(72)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._history = collections.deque(maxlen=300)
        self._active  = False
        self._speaking = False

    def set_active(self, v):
        self._active = v
        if not v:
            self._history.clear()
        self.update()

    def set_speaking(self, v):
        self._speaking = v
        self.update()

    def update_fft(self, bins):
        self._history.append(bins.copy())
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        w, h = self.width(), self.height()
        painter.fillRect(0, 0, w, h, BG_PANEL)

        if not self._active or not self._history:
            painter.setPen(QPen(ASH, 1))
            painter.drawLine(0, h // 2, w, h // 2)
            return

        history = list(self._history)
        n       = len(history)
        col_w   = max(1.0, w / max(n, 1))

        for i, frame in enumerate(history):
            x = int(i * col_w)
            for j, val in enumerate(frame):
                if val < 0.3:
                    c = SPECTR_LOW
                elif val < 0.65:
                    t = (val - 0.3) / 0.35
                    r = int(SPECTR_LOW.red()   + t * (SPECTR_MID.red()   - SPECTR_LOW.red()))
                    g = int(SPECTR_LOW.green() + t * (SPECTR_MID.green() - SPECTR_LOW.green()))
                    b = int(SPECTR_LOW.blue()  + t * (SPECTR_MID.blue()  - SPECTR_LOW.blue()))
                    c = QColor(r, g, b)
                else:
                    t = (val - 0.65) / 0.35
                    r = int(SPECTR_MID.red()   + t * (SPECTR_HI.red()   - SPECTR_MID.red()))
                    g = int(SPECTR_MID.green() + t * (SPECTR_HI.green() - SPECTR_MID.green()))
                    b = int(SPECTR_MID.blue()  + t * (SPECTR_HI.blue()  - SPECTR_MID.blue()))
                    c = QColor(r, g, b)

                painter.fillRect(
                    x, int(j * h / NUM_BINS),
                    max(1, int(col_w) + 1),
                    max(1, int(h / NUM_BINS) + 1),
                    c
                )

        # Mode indicator bar
        if self._speaking:
            painter.fillRect(0, h - 3, w, 3, QColor(TEXT_MID.red(), TEXT_MID.green(), TEXT_MID.blue(), 120))
        else:
            painter.fillRect(0, h - 3, w, 3, QColor(EMBER_DIM.red(), EMBER_DIM.green(), EMBER_DIM.blue(), 120))


# ─────────────────────────────────────────────
# CONVERSATION BUBBLE
# ─────────────────────────────────────────────

class BubbleWidget(QWidget):
    def __init__(self, main, sub="", is_response=True, parent=None):
        super().__init__(parent)
        self.is_response = is_response
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        lbl_main = QLabel(main)
        lbl_main.setWordWrap(True)
        lbl_main.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        if is_response:
            lbl_main.setFont(QFont("Georgia", 15, QFont.Weight.Light))
            lbl_main.setStyleSheet(
                f"color: {EMBER_GLOW.name()}; letter-spacing: 3px; background: transparent;"
            )
        else:
            lbl_main.setFont(QFont("Georgia", 10))
            lbl_main.setStyleSheet(
                f"color: {TEXT_MID.name()}; background: transparent;"
            )
        layout.addWidget(lbl_main)

        if sub:
            lbl_sub = QLabel(sub)
            lbl_sub.setWordWrap(True)
            lbl_sub.setFont(QFont("Georgia", 8))
            lbl_sub.setStyleSheet(
                f"color: {TEXT_DIM.name()}; font-style: italic; "
                f"letter-spacing: 2px; background: transparent;"
            )
            layout.addWidget(lbl_sub)

    def paintEvent(self, event):
        painter = QPainter(self)
        w, h = self.width(), self.height()
        if self.is_response:
            painter.fillRect(0, 0, w, h, BG_MSG)
            painter.fillRect(0, 6, 2, h - 12, EMBER_DIM)
        else:
            painter.fillRect(0, 0, w, h, BG)
            painter.fillRect(w - 2, 6, 2, h - 12, ASH)


# ─────────────────────────────────────────────
# EMBER PULSE
# ─────────────────────────────────────────────

class EmberPulse(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(10, 10)
        self._active  = False
        self._phase   = 0.0
        self._timer   = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.setInterval(40)

    def set_active(self, v):
        self._active = v
        if v:
            self._timer.start()
        else:
            self._timer.stop()
            self._phase = 0.0
        self.update()

    def _tick(self):
        self._phase = (self._phase + 0.06) % (2 * math.pi)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(0, 0, 10, 10, BG)
        if self._active:
            pulse = (math.sin(self._phase) + 1) / 2
            a = int(130 + pulse * 125)
            c = QColor(EMBER_GLOW.red(), EMBER_GLOW.green(), EMBER_GLOW.blue(), a)
        else:
            c = ASH
        painter.setBrush(QBrush(c))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(1, 1, 8, 8)


class EmberLine(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(1)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def paintEvent(self, event):
        painter = QPainter(self)
        grad = QLinearGradient(0, 0, self.width(), 0)
        grad.setColorAt(0,   QColor(0, 0, 0, 0))
        grad.setColorAt(0.3, EMBER_DIM)
        grad.setColorAt(0.7, EMBER_DIM)
        grad.setColorAt(1,   QColor(0, 0, 0, 0))
        painter.fillRect(0, 0, self.width(), 1, QBrush(grad))


def make_slider(mn, mx, init):
    s = QSlider(Qt.Orientation.Horizontal)
    s.setRange(mn, mx)
    s.setValue(init)
    s.setStyleSheet("""
        QSlider::groove:horizontal { height: 2px; background: #3C3730; }
        QSlider::handle:horizontal {
            background: #C4701C; width: 12px; height: 12px;
            margin: -5px 0; border-radius: 6px;
        }
        QSlider::sub-page:horizontal { background: #6E3C0E; }
    """)
    return s


# ─────────────────────────────────────────────
# MODE INDICATOR LABEL
# ─────────────────────────────────────────────

class ModeLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFont(QFont("Georgia", 8))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._set_ambient()

    def set_speaking(self):
        self.setText("● transcribing voice")
        self.setStyleSheet(f"color: {TEXT_MID.name()}; font-style: italic; letter-spacing: 2px;")

    def set_ambient(self):
        self._set_ambient()

    def _set_ambient(self):
        self.setText("◆ reading ambient spectrum")
        self.setStyleSheet(f"color: {EMBER_DIM.name()}; font-style: italic; letter-spacing: 2px;")

    def set_dormant(self):
        self.setText("")


# ─────────────────────────────────────────────
# MAIN WINDOW
# ─────────────────────────────────────────────

class HugrWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("HUGR")
        self.setMinimumSize(640, 720)
        self.resize(700, 800)

        self._session_active  = False
        self._pending_ambient = None   # last ambient FFT waiting for word count
        self._word_count_pool = []     # rotating word counts [2,3,2,4,3,...]

        self._audio   = AudioEngine()
        self._audio.fft_ready.connect(self._on_fft)
        self._audio.speech_start.connect(self._on_speech_start)
        self._audio.speech_end.connect(self._on_speech_end)
        self._audio.ambient_ready.connect(self._on_ambient)

        self._speech  = SpeechWorker()
        self._speech.text_ready.connect(self._on_transcription)
        self._speech.available.connect(self._on_speech_available)

        self._build_ui()
        self._apply_style()

    # ── Build UI ─────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(0)

        # Header
        hdr = QHBoxLayout()
        hdr.setSpacing(8)
        self._pulse = EmberPulse()
        hdr.addWidget(self._pulse)

        title = QLabel("HUGR")
        title.setFont(QFont("Georgia", 20, QFont.Weight.Light))
        title.setStyleSheet(f"color: {EMBER.name()}; letter-spacing: 10px;")
        hdr.addWidget(title)
        hdr.addStretch()

        self._status_lbl = QLabel("dormant")
        self._status_lbl.setFont(QFont("Georgia", 9))
        self._status_lbl.setStyleSheet(f"color: {TEXT_DIM.name()}; font-style: italic;")
        hdr.addWidget(self._status_lbl)

        root.addLayout(hdr)
        root.addSpacing(8)
        root.addWidget(EmberLine())
        root.addSpacing(4)

        sub = QLabel("Instrumental Trans-Communication  ·  Norse Framework")
        sub.setFont(QFont("Georgia", 7))
        sub.setStyleSheet(f"color: {TEXT_DIM.name()}; letter-spacing: 2px;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(sub)
        root.addSpacing(10)

        # Spectrogram
        spec_lbl = QLabel("SIGNAL")
        spec_lbl.setFont(QFont("Georgia", 7))
        spec_lbl.setStyleSheet(f"color: {TEXT_DIM.name()}; letter-spacing: 3px;")
        root.addWidget(spec_lbl)
        root.addSpacing(3)

        self._spectrogram = SpectrogramWidget()
        root.addWidget(self._spectrogram)
        root.addSpacing(6)

        # Mode label
        self._mode_lbl = ModeLabel()
        self._mode_lbl.set_dormant()
        root.addWidget(self._mode_lbl)
        root.addSpacing(8)
        root.addWidget(EmberLine())
        root.addSpacing(8)

        # Conversation
        conv_lbl = QLabel("SESSION")
        conv_lbl.setFont(QFont("Georgia", 7))
        conv_lbl.setStyleSheet(f"color: {TEXT_DIM.name()}; letter-spacing: 3px;")
        root.addWidget(conv_lbl)
        root.addSpacing(4)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{ background: {BG.name()}; border: none; }}
            QScrollBar:vertical {{ background: {BG.name()}; width: 4px; }}
            QScrollBar::handle:vertical {{ background: {EMBER_DIM.name()}; border-radius: 2px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        """)

        self._conv_widget = QWidget()
        self._conv_widget.setStyleSheet(f"background: {BG.name()};")
        self._conv_layout = QVBoxLayout(self._conv_widget)
        self._conv_layout.setContentsMargins(0, 0, 0, 0)
        self._conv_layout.setSpacing(4)
        self._conv_layout.addStretch()

        self._scroll.setWidget(self._conv_widget)
        self._scroll.setMinimumHeight(260)
        root.addWidget(self._scroll)

        root.addSpacing(8)
        root.addWidget(EmberLine())
        root.addSpacing(10)

        # Sliders
        ctrl = QVBoxLayout()
        ctrl.setSpacing(8)

        noise_row = QHBoxLayout()
        nl = QLabel("noise mix")
        nl.setFixedWidth(70)
        nl.setStyleSheet(f"color: {TEXT_DIM.name()}; font-size: 8px; letter-spacing: 1px;")
        self._noise_sl = make_slider(0, 100, 12)
        self._noise_sl.valueChanged.connect(lambda v: self._audio.set_noise_volume(v / 100.0))
        noise_row.addWidget(nl)
        noise_row.addWidget(self._noise_sl)
        ctrl.addLayout(noise_row)

        mic_row = QHBoxLayout()
        ml = QLabel("mic gain")
        ml.setFixedWidth(70)
        ml.setStyleSheet(f"color: {TEXT_DIM.name()}; font-size: 8px; letter-spacing: 1px;")
        self._mic_sl = make_slider(0, 100, 90)
        self._mic_sl.valueChanged.connect(lambda v: self._audio.set_mic_volume(v / 100.0))
        mic_row.addWidget(ml)
        mic_row.addWidget(self._mic_sl)
        ctrl.addLayout(mic_row)

        # Voice sensitivity — controls SPEECH_THRESH live
        # Low = triggers on breathing/taps. High = only loud clear speech.
        sens_row = QHBoxLayout()
        sl = QLabel("voice sens")
        sl.setFixedWidth(70)
        sl.setStyleSheet(f"color: {TEXT_DIM.name()}; font-size: 8px; letter-spacing: 1px;")
        self._sens_sl = make_slider(1, 30, 8)  # maps to 0.01–0.30 RMS
        self._sens_sl.valueChanged.connect(
            lambda v: setattr(self._audio, '_speech_thresh', v / 100.0)
        )
        sens_row.addWidget(sl)
        sens_row.addWidget(self._sens_sl)
        ctrl.addLayout(sens_row)

        root.addLayout(ctrl)
        root.addSpacing(12)

        # Begin/End button
        self._toggle_btn = QPushButton("BEGIN SESSION")
        self._toggle_btn.setFixedHeight(42)
        self._toggle_btn.setFont(QFont("Georgia", 10, QFont.Weight.Light))
        self._toggle_btn.clicked.connect(self._toggle_session)
        self._style_dormant_btn()
        root.addWidget(self._toggle_btn)

        root.addSpacing(6)

        self._speech_lbl = QLabel("")
        self._speech_lbl.setFont(QFont("Georgia", 7))
        self._speech_lbl.setStyleSheet(f"color: {TEXT_DIM.name()}; font-style: italic;")
        self._speech_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._speech_lbl)

        if not self._speech.is_available():
            self._speech_lbl.setText(
                "voice transcription unavailable  ·  pip install SpeechRecognition  ·  restart"
            )

        root.addSpacing(4)
        footer = QLabel("ephemeral  ·  nothing is saved  ·  all passes")
        footer.setFont(QFont("Georgia", 7))
        footer.setStyleSheet(f"color: {TEXT_DIM.name()}; letter-spacing: 2px;")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(footer)

    # ── Style ────────────────────────────────

    def _apply_style(self):
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{ background: {BG.name()}; color: {TEXT_FULL.name()}; }}
            QLabel {{ background: transparent; }}
        """)

    def _style_dormant_btn(self):
        self._toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: {BG_PANEL.name()}; color: {EMBER.name()};
                border: 1px solid {EMBER_DIM.name()}; border-radius: 2px;
                letter-spacing: 5px;
            }}
            QPushButton:hover {{
                background: {EMBER_DIM.name()}; color: {EMBER_GLOW.name()};
            }}
        """)

    def _style_active_btn(self):
        self._toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: #120A04; color: {TEXT_DIM.name()};
                border: 1px solid #1E1006; border-radius: 2px;
                letter-spacing: 5px;
            }}
            QPushButton:hover {{
                background: #1A0E06; color: {TEXT_MID.name()};
            }}
        """)

    # ── Session ──────────────────────────────

    def _toggle_session(self):
        if not self._session_active:
            self._start_session()
        else:
            self._end_session()

    def _start_session(self):
        self._session_active = True
        ok = self._audio.start()
        self._spectrogram.set_active(True)
        self._pulse.set_active(True)
        self._toggle_btn.setText("END SESSION")
        self._style_active_btn()
        self._mode_lbl.set_ambient()

        status = "active" if ok else "active · no mic"
        self._status_lbl.setText(status)
        self._status_lbl.setStyleSheet(
            f"color: {EMBER_DIM.name()}; font-style: italic; font-size: 9px;"
        )

        if self._speech.is_available():
            self._speech.start()
            backend = self._speech.backend_name()
            self._speech_lbl.setText(
                f"voice transcription active  ·  {backend}  ·  adjust voice sens if needed"
            )
            self._speech_lbl.setStyleSheet(
                f"color: {TEXT_DIM.name()}; font-style: italic; font-size: 7px;"
            )

    def _end_session(self):
        self._session_active = False
        self._audio.stop()
        self._spectrogram.set_active(False)
        self._pulse.set_active(False)
        self._toggle_btn.setText("BEGIN SESSION")
        self._style_dormant_btn()
        self._status_lbl.setText("dormant")
        self._status_lbl.setStyleSheet(
            f"color: {TEXT_DIM.name()}; font-style: italic; font-size: 9px;"
        )
        self._mode_lbl.set_dormant()
        if self._speech.is_available():
            self._speech.stop()

    # ── Audio callbacks ───────────────────────

    def _on_fft(self, bins):
        self._spectrogram.update_fft(bins)

    def _on_speech_start(self):
        self._spectrogram.set_speaking(True)
        self._mode_lbl.set_speaking()

    def _on_speech_end(self):
        self._spectrogram.set_speaking(False)
        self._mode_lbl.set_ambient()

        # Emit a response based on the ambient FFT accumulated before speech
        if self._pending_ambient is not None:
            count = self._next_word_count()
            words = spectrum_to_words(self._pending_ambient, count)
            self._add_response(words)

    def _on_ambient(self, spectrum):
        # Store the latest ambient spectrum — used when speech ends
        self._pending_ambient = spectrum

        # Also emit spontaneous ambient responses (every ~3 accumulations)
        # so the tool isn't completely silent if you don't speak
        if not hasattr(self, '_ambient_tick'):
            self._ambient_tick = 0
        self._ambient_tick += 1

        if self._ambient_tick >= 3:
            self._ambient_tick = 0
            count = self._next_word_count()
            words = spectrum_to_words(spectrum, count)
            self._add_response(words)

    def _next_word_count(self):
        # Rotate through counts 2,3,2,4,3,2,3 — varied but not random
        if not self._word_count_pool:
            self._word_count_pool = [2, 3, 2, 4, 3, 2, 3, 4, 2, 3]
        return self._word_count_pool.pop(0)

    # ── Transcription callback ────────────────

    def _on_transcription(self, text):
        if not self._session_active:
            return
        self._add_bubble(text, "", is_response=False)

    def _on_speech_available(self, ok):
        if not ok:
            self._speech_lbl.setText(
                "speech recognition failed  ·  pip install pywin32  ·  restart"
            )

    # ── Conversation ──────────────────────────

    def _add_response(self, words):
        if not self._session_active:
            return
        norse_text   = "  ·  ".join(w[0].upper() for w in words)
        english_text = "  ·  ".join(w[1] for w in words)
        self._add_bubble(norse_text, english_text, is_response=True)

    def _add_bubble(self, main, sub, is_response):
        bubble = BubbleWidget(main, sub, is_response)
        count  = self._conv_layout.count()
        self._conv_layout.insertWidget(count - 1, bubble)
        QTimer.singleShot(50, self._scroll_bottom)

    def _scroll_bottom(self):
        sb = self._scroll.verticalScrollBar()
        sb.setValue(sb.maximum())


    # ── Cleanup ───────────────────────────────

    def closeEvent(self, event):
        self._audio.stop()
        if self._speech.is_available():
            self._speech.stop()
        super().closeEvent(event)


# ─────────────────────────────────────────────
# ENTRY
# ─────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("HUGR")
    win = HugrWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
