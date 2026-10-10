# Instagram Follower Analyzer

A Python data parsing utility using `BeautifulSoup` to parse HTML follower and following exports, identifying unreciprocated following relationships and connection overlaps.

## Usage

1. Export your Instagram account data as HTML files (`followers.html` and `following.html`).
2. Place the HTML files in the project root directory.
3. Run `compare.py`:

```bash
python compare.py
```

## Dependencies

- Python 3.x
- `beautifulsoup4`

```bash
pip install beautifulsoup4
```
