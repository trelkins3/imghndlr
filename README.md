# imghndlr

`imghndlr` is a lightweight concurrent image downloader and interactive desktop gallery viewer. Originally built to replace the **GalleryMaker** web app, the long term goal is to turn `imghndlr` into a generalized image management and modification toolkit.

The initial core module fetches high-resolution image assets directly from public 4chan boards using the 4chan API and provides an elegant Tkinter GUI to preview, scale, and permanently organize wallpapers.

---

## Features

* **Multi-Threaded Downloader Core:** Uses Python's `ThreadPoolExecutor` to pull down entire remote image catalogs concurrently.
* **Isolated Sandbox Storage:** Caches active images inside an OS-level temporary directory, ensuring no local disk clutter unless you explicitly choose to save an asset.
* **Responsive Layout Canvas:** A Tkinter-based gallery UI that scales images proportionally using high-fidelity `LANCZOS` downsampling rules during window resizing.
* **Power-User Hotkeys:** Fluid navigation and storage controls designed for speed:
  * `◀ Left Arrow` / `Right Arrow ▶`: Navigate back and forth through the image stack.
  * `Spacebar`: Instantly commit and copy the current image to your permanent local directory.
* **Extensible & Maintainable Architecture:** Written with explicit keyword argument mappings and strict Python type hints, making it straightforward to add new input sources or image manipulation modules.

---

## Dependencies

* **Python 3.8+**
* **Tkinter** (usually bundled with Python, but some Linux configurations may require running `sudo apt-get install python3-tk`)

---

## Usage

Launch `imghndlr` directly from your terminal:

```
python imghndlr.py
```

`--conf` can be specified to generate a (non-temporary) config file that will retain your target image destination across tool instances.

---

## Workflow
1. Provide input URI (ex: https://boards.4chan.org/wg/thread/XXXXXX) when prompted by the terminal
2. Choose a destination for assets by typing a file path into the text box
3. Navigate the gallery with the buttons or left and right arrow keys; spacebar or 'save image' can be used to save
4. Cleanup! Closing imghndlr will flush and purge the isolated temporary storage

---

## AI Policy
This application DOES use artificial intelligence. Gemini was used extensively for development purposes.

## License
This program is free software; you can redistribute it and/or modify it under the terms of the GNU General Public License v2.0 as published by the Free Software Foundation. See the accompanying LICENSE file for full compliance details.
