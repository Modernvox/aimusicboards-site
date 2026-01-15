import json
import os
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QKeySequence, QAction, QColor, QBrush
from PyQt6.QtWidgets import (
    QApplication, QWidget, QMainWindow, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QLabel, QPushButton, QLineEdit, QTextEdit,
    QSpinBox, QFormLayout, QMessageBox, QListWidget, QListWidgetItem,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QFrame, QSplitter
)

# ============================
# CONFIG
# ============================
QUALIFYING_SCORE_MIN = 30
LEADERBOARD_LIMIT = 50
EXPORT_JSON_PATH = r"C:\Users\lovei\OneDrive\Documents\Ai_Music_Board\leaderboard.json"
APP_NAME = "ai_music_review_board"

# ============================
# DATA MODELS
# ============================

@dataclass
class Submission:
    artist: str
    track: str
    genre: str = ""
    link: str = ""
    notes: str = ""
    submitted_at: str = ""
    status: str = "Queued"  # Queued | Reviewing | Reviewed


@dataclass
class Entry:
    artist: str
    track: str
    genre: str
    lyrics: int
    vocals: int
    production: int
    originality: int
    link: str = ""
    reviewed_at: str = ""

    @property
    def total(self) -> int:
        return self.lyrics + self.vocals + self.production + self.originality


# ============================
# HELPERS
# ============================

def app_data_dir(app_name: str = APP_NAME) -> str:
    home = os.path.expanduser("~")
    base = os.path.join(home, ".config") if sys.platform != "win32" else os.getenv("APPDATA", home)
    path = os.path.join(base, app_name)
    os.makedirs(path, exist_ok=True)
    return path


def session_path() -> str:
    return os.path.join(app_data_dir(), "session.json")


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def place_colors(place: int) -> Optional[QColor]:
    if place == 1:
        return QColor(212, 175, 55)   # gold
    if place == 2:
        return QColor(46, 204, 113)   # green
    if place == 3:
        return QColor(52, 152, 219)   # blue
    return None


# ============================
# UI WIDGETS
# ============================

class Top5Card(QFrame):
    """TV-style card for Top 5 — ultra readable on live stream."""
    def __init__(self, rank: int, parent=None):
        super().__init__(parent)
        self.rank = rank
        self.setObjectName("Top5Card")
        self.setFrameShape(QFrame.Shape.StyledPanel)

        self.setStyleSheet("""
            QFrame#Top5Card {
                border-radius: 16px;
                border: 1px solid rgba(255,255,255,0.15);
                background: rgba(255,255,255,0.05);
            }
            QLabel#Rank {
                font-size: 26px;
                font-weight: 900;
                padding: 8px 16px;
                border-radius: 14px;
                background: rgba(255,255,255,0.10);
            }
            QLabel#ArtistTrack {
                font-size: 22px;
                font-weight: 900;
            }
            QLabel#Meta {
                font-size: 14px;
                font-weight: 700;
                opacity: 0.85;
            }
            QLabel#Score {
                font-size: 28px;
                font-weight: 950;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(18)

        self.rank_lbl = QLabel(f"#{rank}")
        self.rank_lbl.setObjectName("Rank")
        self.rank_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.rank_lbl.setFixedWidth(96)

        mid = QVBoxLayout()
        mid.setSpacing(4)

        self.artist_track_lbl = QLabel("—")
        self.artist_track_lbl.setObjectName("ArtistTrack")

        self.meta_lbl = QLabel("—")
        self.meta_lbl.setObjectName("Meta")

        mid.addWidget(self.artist_track_lbl)
        mid.addWidget(self.meta_lbl)

        self.score_lbl = QLabel("—")
        self.score_lbl.setObjectName("Score")
        self.score_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.score_lbl.setFixedWidth(140)

        layout.addWidget(self.rank_lbl)
        layout.addLayout(mid, 1)
        layout.addWidget(self.score_lbl)

    def _elide(self, text: str, max_chars: int) -> str:
        t = (text or "").strip()
        return t if len(t) <= max_chars else t[: max_chars - 1] + "…"

    def set_data(self, artist: str, track: str, total: int, meta: str, place: int):
        main = f"{artist} — {track}"
        self.artist_track_lbl.setText(self._elide(main, 44))
        self.meta_lbl.setText(self._elide(meta, 60))
        self.score_lbl.setText(f"{total}/40")
        self.apply_place_highlight(place)

    def clear_data(self):
        self.artist_track_lbl.setText("—")
        self.meta_lbl.setText("—")
        self.score_lbl.setText("—")
        self.apply_place_highlight(0)

    def apply_place_highlight(self, place: int):
        c = place_colors(place)
        if not c:
            self.rank_lbl.setStyleSheet("background: rgba(255,255,255,0.10);")
            return
        self.rank_lbl.setStyleSheet(
            f"background: rgba({c.red()},{c.green()},{c.blue()},0.22);"
            f"border: 1px solid rgba({c.red()},{c.green()},{c.blue()},0.55);"
        )


class DisplayModeWindow(QWidget):
    """Borderless, ultra-clean window for TikTok LIVE capture."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Music Review Board — DISPLAY")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 28, 28, 28)
        root.setSpacing(18)

        banner = QFrame()
        banner.setObjectName("DisplayBanner")
        banner_layout = QVBoxLayout(banner)
        banner_layout.setContentsMargins(24, 18, 24, 18)
        banner_layout.setSpacing(8)

        self.lbl_np_title = QLabel("NOW PLAYING")
        self.lbl_np_title.setObjectName("NPTitle")

        self.lbl_np_main = QLabel("Nothing selected")
        self.lbl_np_main.setObjectName("NPMain")

        self.lbl_np_sub = QLabel("")
        self.lbl_np_sub.setObjectName("NPSub")

        banner_layout.addWidget(self.lbl_np_title)
        banner_layout.addWidget(self.lbl_np_main)
        banner_layout.addWidget(self.lbl_np_sub)
        root.addWidget(banner)

        header_row = QHBoxLayout()
        lbl_top = QLabel(f"TOP 5 (≥ {QUALIFYING_SCORE_MIN})")
        lbl_top.setObjectName("TopHeader")
        header_row.addWidget(lbl_top)
        header_row.addStretch()
        root.addLayout(header_row)

        self.cards: List[Top5Card] = []
        for i in range(1, 6):
            card = Top5Card(i)
            self.cards.append(card)
            root.addWidget(card)

        self.setStyleSheet("""
            QWidget { background: #0b0b0f; color: #ffffff; }
            QFrame#DisplayBanner {
                border-radius: 20px;
                background: rgba(255,255,255,0.08);
                border: 1px solid rgba(255,255,255,0.14);
            }
            QLabel#NPTitle { font-size: 14px; font-weight: 900; letter-spacing: 2px; opacity: 0.9; }
            QLabel#NPMain  { font-size: 40px; font-weight: 950; }
            QLabel#NPSub   { font-size: 18px; font-weight: 700; opacity: 0.85; }
            QLabel#TopHeader { font-size: 18px; font-weight: 950; opacity: 0.95; }
        """)

    def update_now_playing(self, text_main: str, text_sub: str):
        self.lbl_np_main.setText(text_main if text_main else "Nothing selected")
        self.lbl_np_sub.setText(text_sub if text_sub else "")

    def update_top5(self, qualifying_entries: List[Entry]):
        top5 = qualifying_entries[:5]
        for i in range(5):
            if i < len(top5):
                e = top5[i]
                g = e.genre or "—"
                meta = f"{g} • L{e.lyrics} V{e.vocals} P{e.production} O{e.originality}"
                self.cards[i].set_data(e.artist, e.track, e.total, meta, place=i + 1)
            else:
                self.cards[i].clear_data()


# ============================
# MAIN WINDOW
# ============================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Music Review Board — LIVE Control Panel")
        self.resize(1280, 760)

        self.submissions: List[Submission] = []
        self.entries: List[Entry] = []
        self.now_playing: Optional[Submission] = None

        self.display_mode: Optional[DisplayModeWindow] = None

        # Board session (for website metadata)
        self.board_session_num: int = 1

        # Auto-export throttle
        self._export_timer = QTimer(self)
        self._export_timer.setSingleShot(True)
        self._export_timer.timeout.connect(self._flush_auto_export)
        self._export_dirty = False

        self._build_ui()
        self._wire_shortcuts()
        self.load_session()
        self.refresh_all()

    # ============================
    # UI BUILD
    # ============================

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        # Banner
        self.banner = QFrame()
        self.banner.setObjectName("Banner")
        self.banner.setStyleSheet("""
            QFrame#Banner {
                border-radius: 16px;
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.12);
            }
            QLabel#BannerTitle { font-size: 12px; opacity: 0.85; }
            QLabel#BannerNow { font-size: 20px; font-weight: 900; }
            QLabel#BannerSub { font-size: 12px; opacity: 0.85; }
        """)
        b = QHBoxLayout(self.banner)
        b.setContentsMargins(16, 12, 16, 12)

        left = QVBoxLayout()
        self.banner_title = QLabel("NOW PLAYING")
        self.banner_title.setObjectName("BannerTitle")
        self.banner_now = QLabel("Nothing selected")
        self.banner_now.setObjectName("BannerNow")
        self.banner_sub = QLabel("Select a submission to update this banner")
        self.banner_sub.setObjectName("BannerSub")
        left.addWidget(self.banner_title)
        left.addWidget(self.banner_now)
        left.addWidget(self.banner_sub)

        self.btn_clear_now = QPushButton("Clear")
        self.btn_clear_now.clicked.connect(self.clear_now_playing)

        self.btn_fullscreen = QPushButton("Fullscreen")
        self.btn_fullscreen.clicked.connect(self.toggle_fullscreen)

        self.btn_display = QPushButton("Display Mode (D)")
        self.btn_display.clicked.connect(self.toggle_display_mode)

        right = QVBoxLayout()
        right.addWidget(self.btn_fullscreen)
        right.addWidget(self.btn_display)
        right.addWidget(self.btn_clear_now)
        right.addStretch()

        b.addLayout(left, 1)
        b.addLayout(right)
        root.addWidget(self.banner)

        self.pages = QStackedWidget()
        root.addWidget(self.pages, 1)

        self.page_host = self._build_host_page()
        self.page_review = self._build_review_page()
        self.page_board = self._build_board_page()

        self.pages.addWidget(self.page_host)
        self.pages.addWidget(self.page_review)
        self.pages.addWidget(self.page_board)

        self.hint = QLabel("Shortcuts: 1 = Host | 2 = Review | 3 = Board | D = Display")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint.setStyleSheet("opacity: 0.7;")
        root.addWidget(self.hint)

        self.setStyleSheet("""
            QWidget { font-size: 13px; }
            QMainWindow { background: #0b0b0f; color: #ffffff; }
            QWidget { background: transparent; color: #ffffff; }
            QLineEdit, QTextEdit, QListWidget, QTableWidget {
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 10px;
                padding: 8px;
            }
            QPushButton {
                background: rgba(255,255,255,0.08);
                border: 1px solid rgba(255,255,255,0.16);
                border-radius: 10px;
                padding: 10px 12px;
                font-weight: 700;
            }
            QPushButton:hover { background: rgba(255,255,255,0.12); }
        """)

    def _build_host_page(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        title = QLabel("HOST")
        title.setFont(self._big_font(18, True))
        layout.addWidget(title)

        self.host_script = QTextEdit()
        self.host_script.setPlaceholderText("Opening script for your live show…")
        layout.addWidget(self.host_script, 1)
        return w

    def _build_review_page(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        title = QLabel("REVIEW")
        title.setFont(self._big_font(18, True))
        layout.addWidget(title)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)

        # Left
        left = QWidget()
        l = QVBoxLayout(left)
        self.queue_list = QListWidget()
        self.queue_list.itemSelectionChanged.connect(self.on_queue_selection_changed)
        l.addWidget(QLabel("Queue"))
        l.addWidget(self.queue_list, 1)

        self.in_artist = QLineEdit(); self.in_artist.setPlaceholderText("Artist")
        self.in_track = QLineEdit(); self.in_track.setPlaceholderText("Track")
        self.in_genre = QLineEdit(); self.in_genre.setPlaceholderText("Genre")
        self.in_link = QLineEdit(); self.in_link.setPlaceholderText("Link")
        form = QFormLayout()
        form.addRow("Artist", self.in_artist)
        form.addRow("Track", self.in_track)
        form.addRow("Genre", self.in_genre)
        form.addRow("Link", self.in_link)
        l.addLayout(form)

        btns = QHBoxLayout()
        add = QPushButton("Add")
        add.clicked.connect(self.add_submission)
        rem = QPushButton("Remove")
        rem.clicked.connect(self.remove_submission)
        btns.addWidget(add); btns.addWidget(rem)
        l.addLayout(btns)
        splitter.addWidget(left)

        # Right
        right = QWidget()
        r = QVBoxLayout(right)
        self.review_notes = QTextEdit()
        self.review_notes.setPlaceholderText("Notes…")
        r.addWidget(self.review_notes)

        self.s_lyrics = QSpinBox(); self.s_lyrics.setRange(0, 10)
        self.s_vocals = QSpinBox(); self.s_vocals.setRange(0, 10)
        self.s_prod = QSpinBox(); self.s_prod.setRange(0, 10)
        self.s_orig = QSpinBox(); self.s_orig.setRange(0, 10)
        sf = QFormLayout()
        sf.addRow("Lyrics", self.s_lyrics)
        sf.addRow("Vocals", self.s_vocals)
        sf.addRow("Production", self.s_prod)
        sf.addRow("Originality", self.s_orig)
        r.addLayout(sf)

        add_board = QPushButton("Add to Leaderboard")
        add_board.clicked.connect(self.add_score_to_leaderboard)
        r.addWidget(add_board)
        splitter.addWidget(right)
        return w

    def _build_board_page(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        title = QLabel("LEADERBOARD")
        title.setFont(self._big_font(18, True))
        layout.addWidget(title)

        self.top5_cards = []
        for i in range(1, 6):
            card = Top5Card(i)
            self.top5_cards.append(card)
            layout.addWidget(card)

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(["Rank", "Artist", "Track", "Genre", "Lyrics", "Vocals", "Production", "Originality", "Total"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self.on_table_selection_changed)
        layout.addWidget(self.table, 1)

        export_btn = QPushButton("Export JSON to Website")
        export_btn.clicked.connect(self.export_to_website_clicked)
        layout.addWidget(export_btn)
        return w

    def _big_font(self, size: int, bold: bool = False) -> QFont:
        f = QFont()
        f.setPointSize(size)
        f.setBold(bold)
        return f

    # ============================
    # SHORTCUTS
    # ============================

    def _wire_shortcuts(self):
        for key, idx in [("1", 0), ("2", 1), ("3", 2)]:
            act = QAction(self)
            act.setShortcut(QKeySequence(key))
            act.triggered.connect(lambda _, i=idx: self.pages.setCurrentIndex(i))
            self.addAction(act)

        d = QAction(self); d.setShortcut(QKeySequence("D")); d.triggered.connect(self.toggle_display_mode); self.addAction(d)
        f = QAction(self); f.setShortcut(QKeySequence("F")); f.triggered.connect(self.toggle_fullscreen); self.addAction(f)

    # ============================
    # DISPLAY MODE
    # ============================

    def toggle_display_mode(self):
        if self.display_mode and self.display_mode.isVisible():
            self.display_mode.close()
            self.display_mode = None
            return
        self.display_mode = DisplayModeWindow()
        self.display_mode.resize(1920, 1080)
        self._sync_display_mode()
        self.display_mode.show()

    def qualifying_entries(self) -> List[Entry]:
        return [e for e in self.entries if e.total >= QUALIFYING_SCORE_MIN]

    def _sync_display_mode(self):
        if not self.display_mode:
            return
        if not self.now_playing:
            self.display_mode.update_now_playing("Nothing selected", "")
        else:
            main = f"{self.now_playing.artist} — {self.now_playing.track}"
            sub = " • ".join(filter(None, [self.now_playing.genre, self.now_playing.status]))
            self.display_mode.update_now_playing(main, sub)
        self.display_mode.update_top5(self.qualifying_entries())

    # ============================
    # CORE LOGIC
    # ============================

    def add_submission(self):
        if not self.in_artist.text().strip() or not self.in_track.text().strip():
            QMessageBox.warning(self, "Missing info", "Artist and Track are required.")
            return
        sub = Submission(
            artist=self.in_artist.text().strip(),
            track=self.in_track.text().strip(),
            genre=self.in_genre.text().strip(),
            link=self.in_link.text().strip(),
            submitted_at=now_iso()
        )
        self.submissions.append(sub)
        self.in_artist.clear(); self.in_track.clear(); self.in_genre.clear(); self.in_link.clear()
        self.refresh_queue()
        self.save_session()

    def remove_submission(self):
        idx = self.queue_list.currentRow()
        if idx >= 0:
            self.submissions.pop(idx)
            self.refresh_queue()
            self.save_session()

    def on_queue_selection_changed(self):
        idx = self.queue_list.currentRow()
        if 0 <= idx < len(self.submissions):
            sub = self.submissions[idx]
            self.review_notes.setPlainText(sub.notes)

    def add_score_to_leaderboard(self):
        idx = self.queue_list.currentRow()
        if idx < 0:
            return
        sub = self.submissions[idx]
        entry = Entry(
            artist=sub.artist,
            track=sub.track,
            genre=sub.genre,
            lyrics=self.s_lyrics.value(),
            vocals=self.s_vocals.value(),
            production=self.s_prod.value(),
            originality=self.s_orig.value(),
            link=sub.link,
            reviewed_at=now_iso()
        )
        self.entries.append(entry)
        sub.status = "Reviewed"
        self.sort_entries()
        self.refresh_all()
        self.save_session()
        self.request_auto_export()

    def sort_entries(self):
        self.entries.sort(key=lambda e: (e.total, e.originality, e.artist.lower()), reverse=True)

    def refresh_all(self):
        self.refresh_queue()
        self.refresh_board()
        self._sync_display_mode()

    def refresh_queue(self):
        self.queue_list.clear()
        for s in self.submissions:
            self.queue_list.addItem(QListWidgetItem(f"[{s.status}] {s.artist} — {s.track}"))

    def refresh_board(self):
        self.sort_entries()
        quals = self.qualifying_entries()
        for i in range(5):
            if i < len(quals):
                e = quals[i]
                meta = f"{e.genre} • L{e.lyrics} V{e.vocals} P{e.production} O{e.originality}"
                self.top5_cards[i].set_data(e.artist, e.track, e.total, meta, i + 1)
            else:
                self.top5_cards[i].clear_data()

        self.table.setRowCount(len(quals))
        for r, e in enumerate(quals):
            for c, v in enumerate([r + 1, e.artist, e.track, e.genre, e.lyrics, e.vocals, e.production, e.originality, e.total]):
                self.table.setItem(r, c, QTableWidgetItem(str(v)))

    # ============================
    # EXPORT + SESSION
    # ============================

    def request_auto_export(self, delay_ms: int = 1500):
        self._export_dirty = True
        self._export_timer.start(delay_ms)

    def _flush_auto_export(self):
        if not self._export_dirty:
            return
        self._export_dirty = False
        self.export_leaderboard_json(EXPORT_JSON_PATH)

    def export_to_website_clicked(self):
        self.export_leaderboard_json(EXPORT_JSON_PATH)
        QMessageBox.information(self, "Exported", f"leaderboard.json saved to:\n{EXPORT_JSON_PATH}")

    def export_leaderboard_json(self, output_path="leaderboard.json"):
        date_str = datetime.utcnow().strftime("%b %d, %Y")
        data = {
            "updated_at": now_iso(),
            "board_session": f"Board Session {self.board_session_num:03d} • {date_str}",
            "now_playing": None,
            "leaderboard": []
        }

        if self.now_playing:
            data["now_playing"] = asdict(self.now_playing)

        for i, e in enumerate(self.qualifying_entries()[:LEADERBOARD_LIMIT], start=1):
            data["leaderboard"].append({
                "rank": i,
                "artist": e.artist,
                "track": e.track,
                "genre": e.genre,
                "total": e.total,
                "lyrics": e.lyrics,
                "vocals": e.vocals,
                "production": e.production,
                "originality": e.originality,
                "reviewed_at": e.reviewed_at
            })

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def save_session(self):
        payload = {
            "version": 4,
            "saved_at": now_iso(),
            "board_session_num": self.board_session_num,
            "now_playing": asdict(self.now_playing) if self.now_playing else None,
            "submissions": [asdict(s) for s in self.submissions],
            "entries": [asdict(e) for e in self.entries],
            "host_script": self.host_script.toPlainText()
        }
        with open(session_path(), "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    def load_session(self):
        p = session_path()
        if not os.path.exists(p):
            return
        with open(p, "r", encoding="utf-8") as f:
            payload = json.load(f)
        self.submissions = [Submission(**s) for s in payload.get("submissions", [])]
        self.entries = [Entry(**e) for e in payload.get("entries", [])]
        self.board_session_num = payload.get("board_session_num", 1)
        np = payload.get("now_playing")
        self.now_playing = Submission(**np) if np else None

    # ============================
    # WINDOW
    # ============================

    def toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def closeEvent(self, event):
        self.save_session()
        if self.display_mode:
            self.display_mode.close()
        super().closeEvent(event)


# ============================
# ENTRY POINT
# ============================

def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
