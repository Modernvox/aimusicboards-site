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

# ----------------------------
# Config
# ----------------------------
QUALIFYING_SCORE_MIN = 30
LEADERBOARD_LIMIT = 50
EXPORT_JSON_PATH = r"C:\Users\lovei\OneDrive\Documents\Ai_Music_Board\leaderboard.json"
APP_NAME = "ai_music_review_board"

AUTO_EXPORT_DELAY_MS = 1500  # throttle window (ms)


# ----------------------------
# Data models
# ----------------------------
@dataclass
class Submission:
    artist: str
    track: str
    genre: str = ""
    link: str = ""
    notes: str = ""
    submitted_at: str = ""  # ISO string
    status: str = "Queued"  # Queued | Reviewing | Reviewed

    # NEW: paid fields (from your server/D1)
    payment_status: str = "NONE"   # NONE | PENDING | PAID
    paid_type: str = ""            # "" | "SKIP" | "UPNEXT"


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
        return int(self.lyrics) + int(self.vocals) + int(self.production) + int(self.originality)


# ----------------------------
# Helpers
# ----------------------------
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


def pretty_utc_date() -> str:
    return datetime.utcnow().strftime("%b %d, %Y")


def safe_text(s) -> str:
    return (s or "").strip()


def place_colors(place: int) -> Optional[QColor]:
    # 1st = Gold, 2nd = Green, 3rd = Blue
    if place == 1:
        return QColor(212, 175, 55)
    if place == 2:
        return QColor(46, 204, 113)
    if place == 3:
        return QColor(52, 152, 219)
    return None


# NEW: Paid badge helper
def paid_badge(sub: Submission) -> str:
    ps = (sub.payment_status or "NONE").upper().strip()
    pt = (sub.paid_type or "").upper().strip()

    if ps == "PAID" and pt == "UPNEXT":
        return " ⭐ UP NEXT"
    if ps == "PAID" and pt == "SKIP":
        return " 💸 SKIP"
    if ps == "PENDING" and pt in ("SKIP", "UPNEXT"):
        return " ⏳ PENDING"
    return ""


# ----------------------------
# UI Widgets
# ----------------------------
class Top5Card(QFrame):
    """A single TV-style card row for the Top 5 (stream-readable)."""
    def __init__(self, rank: int, parent=None):
        super().__init__(parent)
        self.rank = rank
        self.setObjectName("Top5Card")
        self.setFrameShape(QFrame.Shape.StyledPanel)

        self._base_style = """
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
                opacity: 0.88;
            }
            QLabel#Score {
                font-size: 30px;
                font-weight: 950;
            }
        """
        self.setStyleSheet(self._base_style)

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
        self.artist_track_lbl.setWordWrap(False)

        self.meta_lbl = QLabel("—")
        self.meta_lbl.setObjectName("Meta")
        self.meta_lbl.setWordWrap(False)

        mid.addWidget(self.artist_track_lbl)
        mid.addWidget(self.meta_lbl)

        self.score_lbl = QLabel("—")
        self.score_lbl.setObjectName("Score")
        self.score_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.score_lbl.setFixedWidth(150)

        layout.addWidget(self.rank_lbl)
        layout.addLayout(mid, 1)
        layout.addWidget(self.score_lbl)

    def _elide(self, text: str, max_chars: int) -> str:
        t = safe_text(text)
        return t if len(t) <= max_chars else t[: max_chars - 1] + "…"

    def set_data(self, artist: str, track: str, total: int, meta: str, place: int):
        main = f"{artist} — {track}"
        self.artist_track_lbl.setText(self._elide(main, 44))
        self.meta_lbl.setText(self._elide(meta, 64))
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
    """
    Borderless, ultra-clean display window for LIVE capture.
    Shows: Board Session + Now Playing + Top 5 (qualifying).
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Music Review Board — DISPLAY")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 28, 28, 28)
        root.setSpacing(18)

        # Header row: brand + board session
        top_row = QHBoxLayout()
        self.lbl_brand = QLabel("AI MUSIC REVIEW BOARD")
        self.lbl_brand.setObjectName("Brand")
        top_row.addWidget(self.lbl_brand)

        top_row.addStretch()

        self.lbl_session = QLabel("Board Session —")
        self.lbl_session.setObjectName("SessionPill")
        top_row.addWidget(self.lbl_session)

        root.addLayout(top_row)

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
            QLabel#Brand { font-size: 20px; font-weight: 950; letter-spacing: 1px; }
            QLabel#SessionPill {
                padding: 8px 12px;
                border-radius: 999px;
                background: rgba(255,255,255,0.08);
                border: 1px solid rgba(255,255,255,0.14);
                font-weight: 800;
                opacity: 0.95;
            }
            QFrame#DisplayBanner {
                border-radius: 20px;
                background: rgba(255,255,255,0.08);
                border: 1px solid rgba(255,255,255,0.14);
            }
            QLabel#NPTitle { font-size: 14px; font-weight: 900; letter-spacing: 2px; opacity: 0.9; }
            QLabel#NPMain  { font-size: 40px; font-weight: 950; }
            QLabel#NPSub   { font-size: 18px; font-weight: 700; opacity: 0.86; }
            QLabel#TopHeader { font-size: 18px; font-weight: 950; opacity: 0.95; }
        """)

    def update_session(self, session_text: str):
        self.lbl_session.setText(session_text or "Board Session —")

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


# ----------------------------
# Main window
# ----------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Music Review Board — LIVE Control Panel")
        self.resize(1280, 760)

        self.submissions: List[Submission] = []
        self.entries: List[Entry] = []
        self.now_playing: Optional[Submission] = None

        self.board_session_num: int = 1  # persisted
        self.display_mode: Optional[DisplayModeWindow] = None

        # auto-export throttle
        self._export_dirty = False
        self._export_timer = QTimer(self)
        self._export_timer.setSingleShot(True)
        self._export_timer.timeout.connect(self._flush_auto_export)

        self._build_ui()
        self._wire_shortcuts()  # FIXED: correct method name
        self.load_session()
        self.refresh_all()

        # do a first export (throttled) so site has something
        self.request_auto_export()

    # ----------------------------
    # UI build
    # ----------------------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        # Top banner (Now Playing + session pill)
        self.banner = QFrame()
        self.banner.setObjectName("Banner")
        self.banner.setStyleSheet("""
            QFrame#Banner {
                border-radius: 16px;
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.12);
            }
            QLabel#BannerTitle { font-size: 12px; opacity: 0.85; letter-spacing: 1px; }
            QLabel#BannerNow { font-size: 20px; font-weight: 900; }
            QLabel#BannerSub { font-size: 12px; opacity: 0.82; }
            QLabel#SessionPill {
                padding: 8px 12px;
                border-radius: 999px;
                background: rgba(255,255,255,0.08);
                border: 1px solid rgba(255,255,255,0.14);
                font-weight: 800;
                opacity: 0.95;
            }
        """)
        b = QHBoxLayout(self.banner)
        b.setContentsMargins(16, 12, 16, 12)
        b.setSpacing(12)

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

        # Right controls
        right = QVBoxLayout()
        right.setSpacing(8)

        self.lbl_session_pill = QLabel(self._board_session_text())
        self.lbl_session_pill.setObjectName("SessionPill")
        self.lbl_session_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_new_session = QPushButton("New Session (+1)")
        self.btn_new_session.clicked.connect(self.new_session)

        self.btn_display = QPushButton("Display Mode (D)")
        self.btn_display.clicked.connect(self.toggle_display_mode)

        self.btn_fullscreen = QPushButton("Toggle Fullscreen (F)")
        self.btn_fullscreen.clicked.connect(self.toggle_fullscreen)

        self.btn_clear_now = QPushButton("Clear Now Playing")
        self.btn_clear_now.clicked.connect(self.clear_now_playing)

        right.addWidget(self.lbl_session_pill)
        right.addWidget(self.btn_new_session)
        right.addWidget(self.btn_display)
        right.addWidget(self.btn_fullscreen)
        right.addWidget(self.btn_clear_now)
        right.addStretch()

        b.addLayout(left, 1)
        b.addLayout(right)
        root.addWidget(self.banner)

        # Pages
        self.pages = QStackedWidget()
        root.addWidget(self.pages, 1)

        self.page_host = self._build_host_page()
        self.page_review = self._build_review_page()
        self.page_board = self._build_board_page()

        self.pages.addWidget(self.page_host)   # 0
        self.pages.addWidget(self.page_review) # 1
        self.pages.addWidget(self.page_board)  # 2

        self.hint = QLabel(
            f"Shortcuts: 1=Host  2=Review  3=Board  ︱  D=Display  F=Fullscreen  ︱  Qualify ≥ {QUALIFYING_SCORE_MIN}"
        )
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint.setStyleSheet("opacity: 0.7;")
        root.addWidget(self.hint)

        # App styling
        self.setStyleSheet("""
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
                font-weight: 800;
            }
            QPushButton:hover { background: rgba(255,255,255,0.12); }
        """)

    def _build_host_page(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(12)

        title = QLabel("HOST")
        title.setFont(self._big_font(18, True))
        layout.addWidget(title)

        self.host_script = QTextEdit()
        self.host_script.setPlaceholderText(
            "Host notes / opening script:\n\n"
            "• Welcome to AI Music Review Board\n"
            "• Drop your track (artist + title) in chat\n"
            "• We score L/V/P/O out of 10\n"
            "• 30+ qualifies for the board\n"
        )
        layout.addWidget(self.host_script, 1)

        row = QHBoxLayout()
        btn_to_review = QPushButton("Go to Review (2)")
        btn_to_review.clicked.connect(lambda: self.switch_page(1))
        btn_to_board = QPushButton("Go to Board (3)")
        btn_to_board.clicked.connect(lambda: self.switch_page(2))
        row.addWidget(btn_to_review)
        row.addWidget(btn_to_board)
        row.addStretch()
        layout.addLayout(row)
        return w

    def _build_review_page(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(12)

        title = QLabel("REVIEW — Submission Queue + Scoring")
        title.setFont(self._big_font(18, True))
        layout.addWidget(title)

        splitter = QSplitter()
        splitter.setOrientation(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)

        # ----------------------------
        # Left: Submission Queue + Inputs
        # ----------------------------
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setSpacing(10)

        q_title = QLabel("Submission Queue")
        q_title.setFont(self._big_font(14, True))
        left_layout.addWidget(q_title)

        self.queue_list = QListWidget()
        self.queue_list.itemSelectionChanged.connect(self.on_queue_selection_changed)
        left_layout.addWidget(self.queue_list, 1)

        add_form = QFormLayout()
        self.in_artist = QLineEdit()
        self.in_artist.setPlaceholderText("Artist (e.g., Mike Stadium)")
        self.in_track = QLineEdit()
        self.in_track.setPlaceholderText("Track (e.g., Stagnant)")
        self.in_genre = QLineEdit()
        self.in_genre.setPlaceholderText("Genre (Rock, Hip-Hop, Pop, EDM...)")
        self.in_link = QLineEdit()
        self.in_link.setPlaceholderText("Link (optional)")

        add_form.addRow("Artist", self.in_artist)
        add_form.addRow("Track", self.in_track)
        add_form.addRow("Genre", self.in_genre)
        add_form.addRow("Link", self.in_link)
        left_layout.addLayout(add_form)

        btn_row = QHBoxLayout()
        self.btn_add_queue = QPushButton("Add to Queue")
        self.btn_add_queue.clicked.connect(self.add_submission)

        self.btn_remove_queue = QPushButton("Remove")
        self.btn_remove_queue.clicked.connect(self.remove_submission)

        btn_row.addWidget(self.btn_add_queue)
        btn_row.addWidget(self.btn_remove_queue)
        left_layout.addLayout(btn_row)

        splitter.addWidget(left)

        # ----------------------------
        # Right: Scoring + Actions
        # ----------------------------
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setSpacing(10)

        r_title = QLabel("Scoring")
        r_title.setFont(self._big_font(14, True))
        right_layout.addWidget(r_title)

        self.review_notes = QTextEdit()
        self.review_notes.setPlaceholderText("Quick notes while listening (optional)")
        self.review_notes.setFixedHeight(120)
        right_layout.addWidget(self.review_notes)

        score_form = QFormLayout()
        self.s_lyrics = QSpinBox(); self.s_lyrics.setRange(0, 10)
        self.s_vocals = QSpinBox(); self.s_vocals.setRange(0, 10)
        self.s_prod   = QSpinBox(); self.s_prod.setRange(0, 10)
        self.s_orig   = QSpinBox(); self.s_orig.setRange(0, 10)

        score_form.addRow("Lyrics (0–10)", self.s_lyrics)
        score_form.addRow("Vocals (0–10)", self.s_vocals)
        score_form.addRow("Production (0–10)", self.s_prod)
        score_form.addRow("Originality (0–10)", self.s_orig)
        right_layout.addLayout(score_form)

        action_row = QHBoxLayout()

        btn_set_now = QPushButton("Set as Now Playing")
        btn_set_now.clicked.connect(self.set_selected_now_playing)

        btn_mark_reviewing = QPushButton("Mark Reviewing")
        btn_mark_reviewing.clicked.connect(lambda: self.set_selected_status("Reviewing"))

        btn_mark_reviewed = QPushButton("Mark Reviewed")
        btn_mark_reviewed.clicked.connect(lambda: self.set_selected_status("Reviewed"))

        action_row.addWidget(btn_set_now)
        action_row.addWidget(btn_mark_reviewing)
        action_row.addWidget(btn_mark_reviewed)
        right_layout.addLayout(action_row)

        self.btn_send_to_board = QPushButton(f"✅ Add Score to Leaderboard (qualify ≥ {QUALIFYING_SCORE_MIN})")
        self.btn_send_to_board.clicked.connect(self.add_score_to_leaderboard)
        right_layout.addWidget(self.btn_send_to_board)

        nav_row = QHBoxLayout()
        btn_to_host = QPushButton("Back to Host (1)")
        btn_to_host.clicked.connect(lambda: self.switch_page(0))
        btn_to_board = QPushButton("Go to Leaderboard (3)")
        btn_to_board.clicked.connect(lambda: self.switch_page(2))
        nav_row.addWidget(btn_to_host)
        nav_row.addWidget(btn_to_board)
        nav_row.addStretch()
        right_layout.addLayout(nav_row)

        right_layout.addStretch()
        splitter.addWidget(right)

        splitter.setSizes([520, 740])
        return w

    def _build_board_page(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(12)

        title = QLabel(f"LEADERBOARD — Top 5 (≥ {QUALIFYING_SCORE_MIN}) + Top {LEADERBOARD_LIMIT}")
        title.setFont(self._big_font(18, True))
        layout.addWidget(title)

        # Top 5 cards
        cards_title = QLabel("TOP 5 (TV-Style)")
        cards_title.setFont(self._big_font(14, True))
        layout.addWidget(cards_title)

        self.top5_cards: List[Top5Card] = []
        for i in range(1, 6):
            card = Top5Card(rank=i)
            self.top5_cards.append(card)
            layout.addWidget(card)

        # Table
        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels([
            "Rank", "Artist", "Track", "Genre", "Lyrics", "Vocals", "Production", "Originality", "Total"
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.itemSelectionChanged.connect(self.on_table_selection_changed)
        layout.addWidget(self.table, 1)

        # Buttons
        row = QHBoxLayout()

        self.btn_delete_entry = QPushButton("Delete Selected")
        self.btn_delete_entry.clicked.connect(self.delete_selected_entry)

        self.btn_copy_top50 = QPushButton("Copy Top 50 (TikTok)")
        self.btn_copy_top50.clicked.connect(self.copy_top50)

        self.btn_export_web = QPushButton("Export to Website (JSON)")
        self.btn_export_web.clicked.connect(self.export_to_website_clicked)

        self.btn_clear_all = QPushButton("Clear Board + Queue")
        self.btn_clear_all.clicked.connect(self.clear_everything_confirm)

        btn_to_review = QPushButton("Go to Review (2)")
        btn_to_review.clicked.connect(lambda: self.switch_page(1))

        row.addWidget(self.btn_delete_entry)
        row.addWidget(self.btn_copy_top50)
        row.addWidget(self.btn_export_web)
        row.addWidget(self.btn_clear_all)
        row.addStretch()
        row.addWidget(btn_to_review)
        layout.addLayout(row)

        return w

    def _big_font(self, size: int, bold: bool = False) -> QFont:
        f = QFont()
        f.setPointSize(size)
        f.setBold(bold)
        return f

    # ----------------------------
    # Shortcuts / page switching
    # ----------------------------
    def _wire_shortcuts(self):
        act1 = QAction("Host", self)
        act1.setShortcut(QKeySequence("1"))
        act1.triggered.connect(lambda: self.switch_page(0))

        act2 = QAction("Review", self)
        act2.setShortcut(QKeySequence("2"))
        act2.triggered.connect(lambda: self.switch_page(1))

        act3 = QAction("Board", self)
        act3.setShortcut(QKeySequence("3"))
        act3.triggered.connect(lambda: self.switch_page(2))

        actF = QAction("Fullscreen", self)
        actF.setShortcut(QKeySequence("F"))
        actF.triggered.connect(self.toggle_fullscreen)

        actD = QAction("Display Mode", self)
        actD.setShortcut(QKeySequence("D"))
        actD.triggered.connect(self.toggle_display_mode)

        self.addAction(act1)
        self.addAction(act2)
        self.addAction(act3)
        self.addAction(actF)
        self.addAction(actD)

    def switch_page(self, index: int):
        self.pages.setCurrentIndex(index)

    # ----------------------------
    # Session / Board Session
    # ----------------------------
    def _board_session_text(self) -> str:
        return f"Board Session {self.board_session_num:03d} • {pretty_utc_date()}"

    def new_session(self):
        self.board_session_num += 1
        self.lbl_session_pill.setText(self._board_session_text())
        self._sync_display_mode()
        self.save_session()
        self.request_auto_export()

    # ----------------------------
    # Display Mode
    # ----------------------------
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

        self.display_mode.update_session(self._board_session_text())

        if not self.now_playing:
            main = "Nothing selected"
            sub = ""
        else:
            badge = paid_badge(self.now_playing)
            main = f"{self.now_playing.artist} — {self.now_playing.track}{badge}"
            extra = []
            if self.now_playing.genre:
                extra.append(self.now_playing.genre)
            if self.now_playing.status:
                extra.append(self.now_playing.status)
            if self.now_playing.link:
                extra.append(self.now_playing.link)
            sub = " • ".join(extra) if extra else ""

        self.display_mode.update_now_playing(main, sub)
        self.display_mode.update_top5(self.qualifying_entries())

    # ----------------------------
    # Now Playing banner
    # ----------------------------
    def set_now_playing(self, sub: Optional[Submission]):
        self.now_playing = sub
        if not sub:
            self.banner_now.setText("Nothing selected")
            self.banner_sub.setText("Select a submission to update this banner")
        else:
            badge = paid_badge(sub)
            self.banner_now.setText(f"{sub.artist} — {sub.track}{badge}")
            extra = []
            if sub.genre:
                extra.append(f"Genre: {sub.genre}")
            if sub.status:
                extra.append(f"Status: {sub.status}")
            if sub.link:
                extra.append(sub.link)
            self.banner_sub.setText(" • ".join(extra) if extra else " ")

        self._sync_display_mode()
        self.save_session()
        self.request_auto_export()

    def clear_now_playing(self):
        self.set_now_playing(None)

    # ----------------------------
    # Queue logic
    # ----------------------------
    def add_submission(self):
        artist = safe_text(self.in_artist.text())
        track = safe_text(self.in_track.text())
        genre = safe_text(self.in_genre.text())
        link = safe_text(self.in_link.text())

        if not artist or not track:
            QMessageBox.warning(self, "Missing info", "Please enter both Artist and Track.")
            return

        sub = Submission(
            artist=artist,
            track=track,
            genre=genre,
            link=link,
            submitted_at=now_iso(),
            status="Queued",
            payment_status="NONE",
            paid_type=""
        )
        self.submissions.append(sub)

        self.in_artist.clear()
        self.in_track.clear()
        self.in_genre.clear()
        self.in_link.clear()

        self.refresh_queue()
        self.save_session()

    def remove_submission(self):
        idx = self.queue_list.currentRow()
        if idx < 0:
            return
        self.submissions.pop(idx)
        self.refresh_queue()
        self.save_session()

    def on_queue_selection_changed(self):
        idx = self.queue_list.currentRow()
        if idx < 0 or idx >= len(self.submissions):
            return
        sub = self.submissions[idx]
        if sub.notes and not self.review_notes.toPlainText().strip():
            self.review_notes.setPlainText(sub.notes)

    def set_selected_now_playing(self):
        idx = self.queue_list.currentRow()
        if idx < 0 or idx >= len(self.submissions):
            QMessageBox.information(self, "No selection", "Select a submission in the queue first.")
            return
        self.set_now_playing(self.submissions[idx])

    def set_selected_status(self, status: str):
        idx = self.queue_list.currentRow()
        if idx < 0 or idx >= len(self.submissions):
            return
        self.submissions[idx].status = status
        self.submissions[idx].notes = self.review_notes.toPlainText().strip()
        self.refresh_queue()

        # keep Now Playing synced
        if self.now_playing and self.now_playing is self.submissions[idx]:
            self.set_now_playing(self.submissions[idx])

        self.save_session()
        self.request_auto_export()

    # ----------------------------
    # Scoring -> leaderboard
    # ----------------------------
    def add_score_to_leaderboard(self):
        idx = self.queue_list.currentRow()
        if idx < 0 or idx >= len(self.submissions):
            QMessageBox.information(self, "No selection", "Select a submission in the queue first.")
            return

        sub = self.submissions[idx]
        entry = Entry(
            artist=sub.artist,
            track=sub.track,
            genre=sub.genre.strip(),
            lyrics=int(self.s_lyrics.value()),
            vocals=int(self.s_vocals.value()),
            production=int(self.s_prod.value()),
            originality=int(self.s_orig.value()),
            link=sub.link,
            reviewed_at=now_iso()
        )
        self.entries.append(entry)

        # Mark reviewed
        sub.status = "Reviewed"
        sub.notes = self.review_notes.toPlainText().strip()

        # Reset scoring UI
        self.review_notes.clear()
        self.s_lyrics.setValue(0)
        self.s_vocals.setValue(0)
        self.s_prod.setValue(0)
        self.s_orig.setValue(0)

        self.refresh_all()
        self.save_session()
        self.request_auto_export()
        self.switch_page(2)

    def sort_entries(self):
        self.entries.sort(key=lambda e: (e.total, e.originality, e.artist.lower()), reverse=True)

    # ----------------------------
    # Leaderboard UI events
    # ----------------------------
    def on_table_selection_changed(self):
        row = self.table.currentRow()
        if row < 0:
            return
        quals = self.qualifying_entries()[:LEADERBOARD_LIMIT]
        if row >= len(quals):
            return
        e = quals[row]
        self.set_now_playing(Submission(
            artist=e.artist,
            track=e.track,
            genre=e.genre,
            link=e.link,
            status="Reviewed",
            submitted_at=e.reviewed_at,
            payment_status="NONE",
            paid_type=""
        ))

    def delete_selected_entry(self):
        row = self.table.currentRow()
        if row < 0:
            return
        quals = self.qualifying_entries()[:LEADERBOARD_LIMIT]
        if row >= len(quals):
            return
        target = quals[row]

        for i, e in enumerate(self.entries):
            if (e.artist == target.artist and e.track == target.track and e.genre == target.genre
                    and e.total == target.total and e.reviewed_at == target.reviewed_at):
                self.entries.pop(i)
                break

        self.sort_entries()
        self.refresh_board()
        self._sync_display_mode()
        self.save_session()
        self.request_auto_export()

    def copy_top50(self):
        top = self.qualifying_entries()[:50]
        if not top:
            return
        lines = [
            f"AI MUSIC REVIEW BOARD — TOP 50 (≥ {QUALIFYING_SCORE_MIN})",
            self._board_session_text(),
            ""
        ]
        for i, e in enumerate(top, start=1):
            g = f" [{e.genre}]" if e.genre else ""
            lines.append(f"{i}. {e.artist} — {e.track}{g} ({e.total}/40)")
        QApplication.clipboard().setText("\n".join(lines))
        QMessageBox.information(self, "Copied", "Top 50 copied to clipboard.")

    def clear_everything_confirm(self):
        res = QMessageBox.question(
            self,
            "Clear everything?",
            "This will clear the queue, leaderboard, and now playing.\nAre you sure?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if res == QMessageBox.StandardButton.Yes:
            self.submissions.clear()
            self.entries.clear()
            self.set_now_playing(None)
            self.refresh_all()
            self.save_session()
            self.request_auto_export()

    # ----------------------------
    # Refresh UI
    # ----------------------------
    def refresh_all(self):
        self.refresh_queue()
        self.refresh_board()
        if self.now_playing:
            self.set_now_playing(self.now_playing)
        else:
            self._sync_display_mode()

    def refresh_queue(self):
        self.queue_list.blockSignals(True)
        self.queue_list.clear()
        for sub in self.submissions:
            g = f" • {sub.genre}" if sub.genre else ""
            badge = paid_badge(sub)
            label = f"[{sub.status}] {sub.artist} — {sub.track}{g}{badge}"
            if sub.link:
                label += "  🔗"
            self.queue_list.addItem(QListWidgetItem(label))
        self.queue_list.blockSignals(False)

    def refresh_board(self):
        self.sort_entries()
        quals = self.qualifying_entries()

        # Top 5 cards
        top5 = quals[:5]
        for i in range(5):
            if i < len(top5):
                e = top5[i]
                g = e.genre or "—"
                meta = f"{g} • L{e.lyrics} V{e.vocals} P{e.production} O{e.originality}"
                self.top5_cards[i].set_data(e.artist, e.track, e.total, meta, place=i + 1)
            else:
                self.top5_cards[i].clear_data()

        # Table top 50
        shown = quals[:LEADERBOARD_LIMIT]
        self.table.setRowCount(len(shown))

        for r, e in enumerate(shown):
            vals = [
                str(r + 1),
                e.artist,
                e.track,
                e.genre or "",
                str(e.lyrics),
                str(e.vocals),
                str(e.production),
                str(e.originality),
                str(e.total),
            ]

            accent = place_colors(r + 1)
            bg_brush = None
            if accent:
                bg_brush = QBrush(QColor(accent.red(), accent.green(), accent.blue(), 50))

            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c in (0, 4, 5, 6, 7, 8):
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if bg_brush:
                    it.setBackground(bg_brush)
                self.table.setItem(r, c, it)

        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(1, max(self.table.columnWidth(1), 240))  # artist
        self.table.setColumnWidth(2, max(self.table.columnWidth(2), 340))  # track
        self.table.setColumnWidth(3, max(self.table.columnWidth(3), 160))  # genre

        self.lbl_session_pill.setText(self._board_session_text())
        self._sync_display_mode()

    # ----------------------------
    # Auto-export throttle
    # ----------------------------
    def request_auto_export(self, delay_ms: int = AUTO_EXPORT_DELAY_MS):
        self._export_dirty = True
        self._export_timer.start(delay_ms)

    def _flush_auto_export(self):
        if not self._export_dirty:
            return
        self._export_dirty = False
        try:
            self.export_leaderboard_json(EXPORT_JSON_PATH)
        except Exception as ex:
            print(f"Auto-export failed: {ex}", file=sys.stderr)

    # ----------------------------
    # Save / load session
    # ----------------------------
    def save_session(self):
        payload = {
            "version": 5,
            "saved_at": now_iso(),
            "board_session_num": int(self.board_session_num),
            "now_playing": asdict(self.now_playing) if self.now_playing else None,
            "submissions": [asdict(s) for s in self.submissions],
            "entries": [asdict(e) for e in self.entries],
            "host_script": self.host_script.toPlainText()
        }
        try:
            with open(session_path(), "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception as ex:
            print(f"Save failed: {ex}", file=sys.stderr)

    def load_session(self):
        p = session_path()
        if not os.path.exists(p):
            return
        try:
            with open(p, "r", encoding="utf-8") as f:
                payload = json.load(f)

            self.board_session_num = int(payload.get("board_session_num", 1))

            # Backward-compatible submission load (older sessions won't have paid fields)
            subs = payload.get("submissions", [])
            fixed_subs: List[Submission] = []
            for s in subs:
                s = dict(s or {})
                s.setdefault("payment_status", "NONE")
                s.setdefault("paid_type", "")
                fixed_subs.append(Submission(**s))
            self.submissions = fixed_subs

            self.entries = [Entry(**e) for e in payload.get("entries", [])]

            np = payload.get("now_playing")
            if np:
                np = dict(np or {})
                np.setdefault("payment_status", "NONE")
                np.setdefault("paid_type", "")
                self.now_playing = Submission(**np)
            else:
                self.now_playing = None

            self.host_script.setPlainText(payload.get("host_script", ""))
        except Exception as ex:
            print(f"Load failed: {ex}", file=sys.stderr)

    # ----------------------------
    # Export JSON
    # ----------------------------
    def export_to_website_clicked(self):
        try:
            self.sort_entries()
            self.export_leaderboard_json(EXPORT_JSON_PATH)
            QMessageBox.information(
                self,
                "Export Complete",
                f"leaderboard.json exported successfully:\n\n{EXPORT_JSON_PATH}\n\n"
                "Next: upload/commit this file to your website repo."
            )
        except Exception as ex:
            QMessageBox.critical(self, "Export Failed", str(ex))

    def export_leaderboard_json(self, output_path="leaderboard.json"):
        data = {
            "updated_at": now_iso(),
            "board_session": self._board_session_text(),
            "scoring": {"L": "Lyrics", "V": "Vocal/Delivery", "P": "Production", "O": "Originality"},
            "submission_note": "Submissions open during live reviews.",
            "now_playing": None,
            "leaderboard": []
        }

        if self.now_playing:
            data["now_playing"] = {
                "artist": self.now_playing.artist,
                "track": self.now_playing.track,
                "genre": self.now_playing.genre,
                "status": self.now_playing.status,
                "link": self.now_playing.link
            }

        qualifying = self.qualifying_entries()[:LEADERBOARD_LIMIT]
        for idx, e in enumerate(qualifying, start=1):
            data["leaderboard"].append({
                "rank": idx,
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

        os.makedirs(os.path.dirname(output_path), exist_ok=True) if os.path.dirname(output_path) else None
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    # ----------------------------
    # Fullscreen
    # ----------------------------
    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    # ----------------------------
    # Close
    # ----------------------------
    def closeEvent(self, event):
        self.save_session()
        if self.display_mode:
            self.display_mode.close()
            self.display_mode = None
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
