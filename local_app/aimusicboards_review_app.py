import os
import sys
import webbrowser
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QGroupBox, QFormLayout, QLineEdit,
    QTextEdit, QSpinBox, QMessageBox
)

API_BASE = os.environ.get("AIMB_API_BASE", "https://aimusicboards.com")
ADMIN_TOKEN = os.environ.get("AIMB_ADMIN_TOKEN", "")  # set this in your environment
CLAIMED_BY = os.environ.get("AIMB_CLAIMED_BY", "mike-desktop")

POLL_MS = 2500


@dataclass
class Submission:
    id: str
    created_at: str
    artist_name: str
    track_title: str
    genre: str
    track_url: str
    notes: str
    priority: int
    paid: int
    status: str
    claimed_by: Optional[str]
    claimed_at: Optional[str]

    # NEW (Stripe paid skips)
    payment_status: str = "NONE"      # NONE | PENDING | PAID
    paid_type: Optional[str] = None   # SKIP | UPNEXT
    stripe_session_id: Optional[str] = None


def auth_headers() -> Dict[str, str]:
    return {"Authorization": f"Bearer {ADMIN_TOKEN}"}


def api_get(path: str) -> Any:
    r = requests.get(f"{API_BASE}{path}", headers=auth_headers(), timeout=10)
    r.raise_for_status()
    return r.json()


def api_post(path: str, payload: Dict[str, Any]) -> Any:
    r = requests.post(f"{API_BASE}{path}", json=payload, headers=auth_headers(), timeout=10)
    if r.status_code >= 400:
        try:
            j = r.json()
            raise RuntimeError(j.get("error") or f"HTTP {r.status_code}")
        except Exception:
            raise RuntimeError(f"HTTP {r.status_code}")
    return r.json()


def paid_badge(s: Submission) -> str:
    """
    Queue badge rules:
      - PAID + UPNEXT => "⭐ UP NEXT"
      - PAID + SKIP   => "💸 SKIP"
      - PENDING       => "⏳ PENDING"
      - NONE          => ""
    """
    ps = (s.payment_status or "NONE").upper().strip()
    pt = (s.paid_type or "").upper().strip()

    if ps == "PAID":
        if pt == "UPNEXT":
            return "⭐ UP NEXT"
        if pt == "SKIP":
            return "💸 SKIP"
        return "💸 PAID"

    if ps == "PENDING":
        # show which type they tried to buy, if we have it
        if pt == "UPNEXT":
            return "⏳ PENDING (UP NEXT)"
        if pt == "SKIP":
            return "⏳ PENDING (SKIP)"
        return "⏳ PENDING"

    return ""


class Main(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Music Review Board • Control Room")

        if not ADMIN_TOKEN:
            QMessageBox.critical(
                self,
                "Missing Token",
                "Set AIMB_ADMIN_TOKEN env var to your ADMIN_TOKEN secret."
            )
            sys.exit(1)

        self.submissions: List[Submission] = []
        self.selected: Optional[Submission] = None

        root = QVBoxLayout(self)

        # top bar
        top = QHBoxLayout()
        self.lbl_status = QLabel("Status: …")
        self.btn_toggle = QPushButton("Toggle Live")
        self.btn_toggle.clicked.connect(self.toggle_live)
        top.addWidget(self.lbl_status, 1)
        top.addWidget(self.btn_toggle)
        root.addLayout(top)

        # main area
        main = QHBoxLayout()

        # queue list
        left_box = QGroupBox("Queue (NEW / IN_REVIEW)")
        left_layout = QVBoxLayout(left_box)
        self.list = QListWidget()
        self.list.itemSelectionChanged.connect(self.on_select)
        left_layout.addWidget(self.list)
        main.addWidget(left_box, 1)

        # details + scoring
        right_box = QGroupBox("Review + Score")
        right = QVBoxLayout(right_box)

        form = QFormLayout()
        self.artist = QLineEdit(); self.artist.setReadOnly(True)
        self.title = QLineEdit(); self.title.setReadOnly(True)
        self.genre = QLineEdit(); self.genre.setReadOnly(True)
        self.link = QLineEdit(); self.link.setReadOnly(True)
        self.notes = QTextEdit(); self.notes.setReadOnly(True); self.notes.setFixedHeight(90)

        # NEW: show paid state on the right panel too
        self.paid_info = QLineEdit()
        self.paid_info.setReadOnly(True)

        form.addRow("Artist", self.artist)
        form.addRow("Track", self.title)
        form.addRow("Genre", self.genre)
        form.addRow("Link", self.link)
        form.addRow("Notes", self.notes)
        form.addRow("Paid / Priority", self.paid_info)
        right.addLayout(form)

        btns = QHBoxLayout()
        self.btn_open = QPushButton("Open Link")
        self.btn_open.clicked.connect(self.open_link)
        self.btn_claim = QPushButton("Claim")
        self.btn_claim.clicked.connect(self.claim)
        btns.addWidget(self.btn_open)
        btns.addWidget(self.btn_claim)
        right.addLayout(btns)

        scores_box = QGroupBox("Scoring (0–10 each, Total ≥ 30 = Board)")
        scores = QFormLayout(scores_box)

        self.s_lyrics = QSpinBox(); self.s_lyrics.setRange(0, 10)
        self.s_delivery = QSpinBox(); self.s_delivery.setRange(0, 10)
        self.s_production = QSpinBox(); self.s_production.setRange(0, 10)
        self.s_originality = QSpinBox(); self.s_originality.setRange(0, 10)
        self.s_replay = QSpinBox(); self.s_replay.setRange(0, 10)
        self._loaded_id: Optional[str] = None

        for w in [self.s_lyrics, self.s_delivery, self.s_production, self.s_originality, self.s_replay]:
            w.valueChanged.connect(self.update_total)

        scores.addRow("Lyrics / Writing", self.s_lyrics)
        scores.addRow("Delivery / Flow", self.s_delivery)
        scores.addRow("Production / Mix", self.s_production)
        scores.addRow("Originality", self.s_originality)
        scores.addRow("Replay Value", self.s_replay)
        self.lbl_total = QLabel("Total: 0  (Rejected)")
        scores.addRow(self.lbl_total)
        right.addWidget(scores_box)

        self.score_notes = QTextEdit()
        self.score_notes.setPlaceholderText("Optional scoring notes (kept in records)…")
        self.score_notes.setFixedHeight(80)
        right.addWidget(self.score_notes)

        self.btn_submit_score = QPushButton("Submit Final Score")
        self.btn_submit_score.clicked.connect(self.submit_score)
        right.addWidget(self.btn_submit_score)

        main.addWidget(right_box, 1)
        root.addLayout(main)

        # polling timer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(POLL_MS)

        self.refresh_status()
        self.refresh()

    def refresh_status(self):
        try:
            j = api_get("/api/admin_toggle")
            open_ = bool(j.get("submissions_open"))
            self.lbl_status.setText(f"Status: {'LIVE (Accepting Submissions)' if open_ else 'OFFLINE (Closed)'}")
            self.btn_toggle.setText("Turn OFF" if open_ else "Turn ON")
        except Exception as e:
            self.lbl_status.setText(f"Status: error ({e})")

    def toggle_live(self):
        try:
            j = api_get("/api/admin_toggle")
            open_ = bool(j.get("submissions_open"))
            j2 = api_post("/api/admin_toggle", {"open": (not open_)})
            open2 = bool(j2.get("submissions_open"))
            self.lbl_status.setText(f"Status: {'LIVE' if open2 else 'OFFLINE'}")
            self.btn_toggle.setText("Turn OFF" if open2 else "Turn ON")
        except Exception as e:
            QMessageBox.critical(self, "Toggle failed", str(e))

    def refresh(self):
        try:
            j = api_get("/api/admin_queue")
            items = j.get("items", [])

            # Be resilient if backend didn't include new fields yet
            parsed: List[Submission] = []
            for it in items:
                # Defaults are handled by dataclass fields
                parsed.append(Submission(**it))

            self.submissions = parsed
            self.render_list()
        except Exception as e:
            # soft fail; keep app usable
            self.lbl_status.setText(f"{self.lbl_status.text()}  | Queue err: {e}")

    def render_list(self):
        current_id = self.selected.id if self.selected else None

        self.list.blockSignals(True)
        try:
            self.list.clear()

            for s in self.submissions:
                badge = paid_badge(s)
                badge_txt = f"{badge}  " if badge else ""

                claim = f" • claimed by {s.claimed_by}" if s.claimed_by else ""
                text = f"{badge_txt}[{s.status}] {s.artist_name} — {s.track_title} ({s.genre}){claim}"

                it = QListWidgetItem(text)
                it.setData(Qt.UserRole, s.id)
                self.list.addItem(it)

            # reselect WHILE signals are blocked (prevents resetting scores)
            if current_id:
                for i in range(self.list.count()):
                    if self.list.item(i).data(Qt.UserRole) == current_id:
                        self.list.setCurrentRow(i)
                        break
        finally:
            self.list.blockSignals(False)

    def on_select(self):
        items = self.list.selectedItems()
        if not items:
            self.selected = None
            return
        sid = items[0].data(Qt.UserRole)
        self.selected = next((s for s in self.submissions if s.id == sid), None)
        self.load_selected()

    def load_selected(self):
        s = self.selected
        if not s:
            return

        self.artist.setText(s.artist_name)
        self.title.setText(s.track_title)
        self.genre.setText(s.genre)
        self.link.setText(s.track_url)
        self.notes.setPlainText(s.notes or "")

        # NEW: paid info field on right panel
        badge = paid_badge(s)
        if badge:
            self.paid_info.setText(badge)
        else:
            self.paid_info.setText("—")

        # Only reset scoring when the selection changes
        if self._loaded_id != s.id:
            for w in [self.s_lyrics, self.s_delivery, self.s_production, self.s_originality, self.s_replay]:
                w.blockSignals(True)
                w.setValue(0)
                w.blockSignals(False)

            self.score_notes.setPlainText("")
            self._loaded_id = s.id

        self.update_total()

    def open_link(self):
        if self.selected:
            webbrowser.open(self.selected.track_url)

    def claim(self):
        if not self.selected:
            return
        try:
            api_post("/api/admin_claim", {"id": self.selected.id, "claimed_by": CLAIMED_BY})
            self.refresh()
        except Exception as e:
            QMessageBox.warning(self, "Claim failed", str(e))

    def update_total(self):
        total = (
            self.s_lyrics.value() + self.s_delivery.value() + self.s_production.value() +
            self.s_originality.value() + self.s_replay.value()
        )
        verdict = "✅ Approved (Board)" if total >= 30 else "❌ Rejected"
        self.lbl_total.setText(f"Total: {total}  ({verdict})")

    def submit_score(self):
        if not self.selected:
            QMessageBox.information(self, "No selection", "Select a submission first.")
            return

        payload = {
            "submission_id": self.selected.id,
            "scored_by": CLAIMED_BY,
            "lyrics": self.s_lyrics.value(),
            "delivery": self.s_delivery.value(),
            "production": self.s_production.value(),
            "originality": self.s_originality.value(),
            "replay": self.s_replay.value(),
            "notes": self.score_notes.toPlainText().strip(),
        }

        try:
            j = api_post("/api/admin_score", payload)
            total = j.get("total")
            approved = j.get("approved")

            QMessageBox.information(
                self,
                "Saved",
                f"Final score saved.\nTotal: {total}\nBoard: {'YES' if approved else 'NO'}"
            )

            # Trigger FINAL now_playing update for overlay recap (non-blocking)
            try:
                api_post("/api/now_playing", {
                    "final": True,
                    "submission_id": self.selected.id,
                    "artist_name": self.selected.artist_name,
                    "track_title": self.selected.track_title,
                    "genre": self.selected.genre,
                    "track_url": self.selected.track_url,
                    "lyrics": self.s_lyrics.value(),
                    "delivery": self.s_delivery.value(),
                    "production": self.s_production.value(),
                    "originality": self.s_originality.value(),
                    "replay": self.s_replay.value(),
                    "total": int(total) if total is not None else None,
                    "approved": bool(approved),
                })
            except Exception:
                pass

            self.refresh()

        except Exception as e:
            QMessageBox.critical(self, "Score submit failed", str(e))


def main():
    app = QApplication(sys.argv)
    w = Main()
    w.resize(1100, 650)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
