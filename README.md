# ⚡ Follower Vault: Instagram Follower Analyzer & Swipe Deck

[![CI](https://github.com/Lwhels/instagram-followers/actions/workflows/ci.yml/badge.svg)](https://github.com/Lwhels/instagram-followers/actions/workflows/ci.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Privacy: 100% Local](https://img.shields.io/badge/Privacy-100%25%20Local%20First-success.svg)](https://github.com/Lwhels/instagram-followers)

> **Zero-Risk, 100% Client-Side Follower Auditor with Tinder-Style Swipe Triage & Instant Recomputation.**
> Triage hundreds of unreciprocated following relationships in minutes. Whitelist celebrities and brands to eliminate false positives, mutate a persistent SQLite vault, and track historical unfollows over time. Available in **Modern Web UI**, **Native macOS Desktop Window**, and **CLI**.

---

## 💡 Why This Exists

Most Instagram follower apps demand your username and password or cookies. Handing over login credentials triggers Instagram bot detection, 2FA locks, shadowbans, and permanent account suspensions.

**Follower Vault operates 100% offline and locally.** It processes official Meta Data Exports (`.zip`, `.html`, or `.json`). No credentials, no scraping, no API rate limits, and zero risk to your account.

### The Problem With Raw Diffs
A standard diff between followers and following will list hundreds of accounts who don't follow you back—including **celebrities, news outlets, meme pages, universities, brands, and mentors** that you *deliberately* follow! 

Raw lists are cluttered with false positives.

### The Solution: Tinder-Style Swipe Deck & Recompute
1. **Swipe Right (`→` / `D`)**: **Whitelist / Keep** (Celebrity, Brand, Influencer, School Club).
2. **Swipe Left (`←` / `A`)**: **Flag for Unfollow** (Inactive acquaintance, ghost account).
3. **Swipe Up (`↑` / `W`)**: **VIP / Close Friend**.
4. **Instant Database Mutation & Recomputation**: As you swipe, the local SQLite database mutates immediately. True unreciprocated metrics, reciprocity percentages, and actionable audit lists recompute dynamically in real-time.
5. **Timeline & Diff Engine**: Upload subsequent snapshots to see exactly who unfollowed you since your last export.

---

## ✨ Features

- 🎴 **Interactive Tinder-Style Swipe Deck**: Smooth 3D card physics, touch/pointer gestures, visual stamps, and tactile Web Audio sound effects.
- ⌨️ **Keyboard Supercharged**: Triage at lightning speed with `←` / `→` / `↑` / `Space` and instant `Cmd+Z` / `U` undo.
- 🔄 **Live Recompute Engine**: Real-time Reciprocity Rate health meter and dynamic metric cards.
- 💾 **Persistent SQLite Vault**: Automatically indexes accounts, relationship histories, custom tags (`#brand`, `#tech`, `#creator`), and notes.
- ⏱️ **Historical Snapshot Diff**: Compare two snapshots (e.g. April 2025 vs October 2026) to see **Lost Followers**, **New Followers**, and **Removed Accounts**.
- 📋 **Master Audit Explorer Table**: Search, filter, and batch-whitelist or batch-flag accounts with 1-click links to Instagram profiles.
- 📤 **Multi-Format Export**: Export clean actionable checklists to CSV, Markdown, or JSON.
- 🎲 **Interactive Demo Mode**: Zero-setup 1-click demo dataset with realistic accounts, timestamps, and relationship distributions.
- 🖥️ **Cross-Platform**: Run in any browser, as a native **macOS Desktop Window** (via PyObjC Cocoa & WebKit), or via the command line.

---

## 🚀 Quick Start

### 1. Clone & Setup

```bash
git clone https://github.com/Lwhels/instagram-followers.git
cd instagram-followers

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -e .
```

---

### 2. Launch the Web & Desktop Experience

#### Option A: Web App (Browser)
```bash
python -m instagram_analyzer serve --port 8000
```
Open **[http://localhost:8000](http://localhost:8000)** in your browser. Click **"🎲 Load Demo"** to immediately try the interactive swipe deck!

#### Option B: Native macOS Desktop App
Run the native macOS launcher:
```bash
./macos/run_macos_app.sh
```
This opens a dedicated macOS Cocoa desktop window with native title bar, window controls, and keyboard shortcuts without browser URL bars.

---

### 3. Command Line Interface (CLI)

#### Direct File Comparison (Backwards Compatible)
```bash
python compare.py followers_1.html following.html
```

#### CLI Analyzer With Database Persistence
```bash
python -m instagram_analyzer compare followers.html following.html --save-db --name "October 2026"
```

#### Seed Demo Data via CLI
```bash
python -m instagram_analyzer demo
```

---

## ⌨️ Swipe Deck Keyboard Shortcuts

| Shortcut | Action | Description |
|---|---|---|
| <kbd>←</kbd> or <kbd>A</kbd> | **Swipe Left** | Flag as Unfollow Candidate |
| <kbd>→</kbd> or <kbd>D</kbd> | **Swipe Right** | Whitelist / Keep (Brand, Celebrity, Mentor) |
| <kbd>↑</kbd> or <kbd>W</kbd> | **Swipe Up** | Mark as VIP / Close Friend |
| <kbd>Space</kbd> or <kbd>↓</kbd> | **Skip** | Skip account for later review |
| <kbd>Cmd</kbd> + <kbd>Z</kbd> or <kbd>U</kbd> | **Undo** | Revert last swipe decision |

---

## 📥 How to Export Your Instagram Data

1. Open Instagram on your phone or web browser.
2. Go to **Settings & Privacy** > **Accounts Center** > **Your Information and Permissions** > **Download Your Information**.
3. Select your Instagram profile and choose **Some of your information**.
4. Check **Followers and Following**.
5. Select **Download to device**:
   - Format: **HTML** or **JSON**
   - Date range: **All time**
6. Once Meta emails you the download link, download the ZIP archive.
7. Open Follower Vault, click **"📁 Import Export"**, and drag & drop the downloaded `.zip` file (or individual `followers_1.html` and `following.html` files).

---

## 🐳 Docker Deployment

Run Follower Vault inside a production Docker container:

```bash
docker-compose up -d
```

Access the UI at `http://localhost:8000`. Database snapshots are persisted to `./data`.

---

## 🧪 Testing & Code Quality

Follower Vault includes a comprehensive test suite with high test coverage (>90% on core components).

```bash
# Run pytest with test coverage report
pytest --cov=instagram_analyzer --cov-report=term-missing tests/
```

All pull requests and commits are automatically verified via GitHub Actions CI across Python 3.10 and 3.11.

---

## 📂 Project Architecture

```
instagram-followers/
├── instagram_analyzer/       # Core Python Package
│   ├── __init__.py           # Package exports & version
│   ├── api.py                # FastAPI REST API & static file serving
│   ├── cli.py                # Command-line interface
│   ├── database.py           # SQLite storage engine (WAL mode, migrations)
│   ├── engine.py             # Business logic, heuristics & recomputation
│   ├── models.py             # Pydantic v2 data models
│   ├── parser.py             # Resilient HTML, JSON & ZIP parser
│   └── sample_data.py        # Realistic mock dataset generator
├── macos/                    # macOS Desktop App Integration
│   ├── app.py                # Cocoa & WebKit desktop window runner
│   └── run_macos_app.sh      # Executable launcher script
├── static/                   # Frontend UI
│   ├── app.js                # Web Audio FX, gesture drag, keyboard navigation
│   ├── index.html            # Responsive UI layout & SVG meters
│   └── style.css             # Glassmorphic dark styling & card physics
├── tests/                    # Test Suite (>90% core coverage)
│   ├── test_api.py           # REST endpoints tests
│   ├── test_api_uploads.py   # ZIP and multipart upload tests
│   ├── test_cli.py           # CLI commands tests
│   ├── test_database.py      # SQLite persistence & diff tests
│   ├── test_engine.py        # Business logic & tagging tests
│   └── test_parser.py        # HTML, JSON & text parsing tests
├── .github/workflows/ci.yml  # GitHub Actions CI workflow
├── compare.py                # Standalone backwards-compatible runner
├── requirements.txt          # Python dependencies
├── pyproject.toml            # Package build configuration
├── Dockerfile                # Production container specification
└── docker-compose.yml        # Docker service orchestration
```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
