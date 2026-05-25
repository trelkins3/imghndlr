# imghndlr

`imghndlr` is a lightweight concurrent image downloader and interactive desktop gallery viewer. Originally built to replace the **GalleryMaker** web app, the long term goal is to turn `imghndlr` into a generalized image management and modification toolkit.

The initial core module fetches high-resolution image assets directly from public 4chan boards using the 4chan API and provides an elegant Tkinter GUI to preview, scale, and permanently organize wallpapers.

---

## Features

* **Multiple Image Sources:** 

  * Browse **local image directories** with built-in filtering
  * Fetch from **Reddit subreddits** (using public JSON endpoints, not praw)
  * Download from **4chan threads** using the 4chan JSON API
* **Multi-Threaded Downloader Core:** Uses Python's `ThreadPoolExecutor` to pull down entire remote image catalogs concurrently.
* **Isolated Sandbox Storage:** Remote sources (Reddit, 4chan) cache images in temporary directories, ensuring no local disk clutter unless you explicitly choose to save an asset.
* **Responsive Layout Canvas:** A Tkinter-based gallery UI that scales images proportionally using high-fidelity `LANCZOS` downsampling during window resizing.
* **Power-User Hotkeys:** Fluid navigation and storage controls designed for speed:
  * `◀ Left Arrow` / `Right Arrow ▶`: Navigate back and forth through the image stack.
  * `Spacebar`: Instantly commit and copy the current image to your permanent local directory.
  * `Delete`: Remove saved copies from your destination directory.
* **Extensible & Maintainable Architecture:** Written with explicit keyword argument mappings and strict Python type hints, making it straightforward to add new `ImageSource` implementations.
* **Config Persistence:** Optional `--conf` flag saves your preferred save directory across sessions.

---

## Dependencies

* **Python 3.8+**
* **Tkinter** (usually bundled with Python, but some Linux configurations may require running `sudo apt-get install python3-tk`)

---

## Usage

`imghndlr` requires a `--source` argument to specify the image source type and a source-specific input:

### From a Local Directory
```bash
python imghndlr.py --source dir "/path/to/images"
# Windows example:
python imghndlr.py --source dir "C:\Users\YourName\Pictures"
```

### From a Reddit Subreddit
```bash
python imghndlr.py --source reddit earthporn
# No setup required! Uses Reddit's public JSON API.
```

### From a 4chan Thread
```bash
python imghndlr.py --source 4chan "https://boards.4channel.org/wg/thread/123456789"
```

### With Config Persistence
Add `--conf` to save your image destination directory across sessions:
```bash
python imghndlr.py --source reddit CatsStandingUp --conf
```

For additional details, run:
```bash
python imghndlr.py --help
```

---

## Workflow

1. **Choose your source** and provide it on the command line:
   - 4chan thread URL for `--source 4chan`
   - Directory path for `--source dir`
   - Subreddit name (without 'r/') for `--source reddit`

2. **Wait for images to download** (displayed in terminal with progress)

3. **Browse the gallery** using arrow keys or buttons

4. **Save images** you want to keep:
   - Enter your destination directory in the text box
   - Press Spacebar or click "Save Image" to copy the current image
   - Status bar shows whether each image is already saved

5. **Cleanup** is automatic:
   - Remote sources (4chan, Reddit) clean up their temporary directories when you close the app
   - Local directory source keeps originals untouched
   - Your saved images remain in your destination directory

---

## AI Policy
This application DOES use artificial intelligence. Gemini and Copilot were used extensively for development.

## License
This program is free software; you can redistribute it and/or modify it under the terms of the GNU General Public License v2.0 as published by the Free Software Foundation. See the accompanying LICENSE file for full compliance details.
