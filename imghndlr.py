import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import tkinter as tk
import json
from abc import ABC, abstractmethod
from enum import Enum
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple, Dict, Any, Optional
from contextlib import ExitStack
import requests
from PIL import Image, ImageTk


class ImageSource(ABC):
    """
    Abstract base class representing a source of images.

    Concrete subclasses implement get_images() to provide a list of local image
    paths ready for display in the UI.
    """

    @abstractmethod
    def get_images(self) -> List[str]:
        """Return a list of image file paths from the source."""


class FourChanImageSource(ImageSource):
    """
    Handles 4chan API interactions and concurrent image downloading.

    Usage: --source 4chan "<thread_url>"
    Example: --source 4chan "https://boards.4channel.org/b/thread/123456789"

    * Takes a standard 4chan thread URL and identifies relevant board and thread identifiers
    * Fetches JSON payload from 4chan data API
    * Uses threads to concurrently download media assets into a target directory
    """
    
    def __init__(self, thread_url: str, target_dir: str) -> None:
        """
        Initializes the image source with a thread URL and a local target directory.

        :param thread_url: Full web address of the target 4chan thread.
        :param target_dir: Local filesystem path where images should be saved.
        """
        self.thread_url: str = thread_url
        self.target_dir: str = target_dir
        self.board: str
        self.thread_id: str
        self.board, self.thread_id = self._parse_thread_url(url=thread_url)

    def _parse_thread_url(self, url: str) -> Tuple[str, str]:
        """
        Extracts the board name and thread ID from a standard 4chan URL structure.

        :param url: Str, the raw URL string inputted by the user.
        :return: A tuple containing (board_name, thread_id) as strings.
        :raises ValueError: If the URL layout does not match expected 4chan routing patterns.
        """
        parsed = urlparse(url=url)
        path_parts: List[str] = parsed.path.strip("/").split("/")
        if len(path_parts) >= 3 and path_parts[1] == "thread":
            return path_parts[0], path_parts[2]
        raise ValueError("Invalid 4chan thread URL structure.")

    def _download_single_image(self, post: Dict[str, Any]) -> Tuple[str, str]:
        """
        Worker function intended for execution within a thread pool to download an individual file.

        :param post: Dict, a single post object extracted from the 4chan thread JSON API.
        :return: A tuple containing (local_path, img_filename) indicating the saved file state.
        """
        # THIS IS SPECIAL SAUCE!!!
        img_filename: str = f"{post['tim']}{post['ext']}"
        img_url: str = f"https://i.4cdn.org/{self.board}/{img_filename}"
        local_path: str = os.path.join(self.target_dir, img_filename)
        
        img_data: bytes = requests.get(url=img_url).content
        with open(local_path, "wb") as f:
            f.write(img_data)
        return local_path, img_filename

    def get_images(self) -> List[str]:
        """
        Orchestrates the multi-threaded download process for the parsed thread target.

        Fetches thread metadata via the 4chan JSON API, filters out posts containing 
        invalid media attachments, and processes downloads concurrently using a ThreadPoolExecutor.

        :return: List of strings representing sorted local file paths to the downloaded images.
        :raises HTTPError: If the remote API endpoint fails to respond successfully.
        """
        api_url: str = f"https://a.4cdn.org/{self.board}/thread/{self.thread_id}.json"
        
        print("Fetching thread data from 4chan API...")
        response = requests.get(url=api_url)
        response.raise_for_status()
        
        posts: List[Dict[str, Any]] = response.json().get("posts", [])
        image_posts: List[Dict[str, Any]] = [p for p in posts if "tim" in p and "ext" in p]
        total_images: int = len(image_posts)
        
        if total_images == 0:
            return []
            
        print(f"Found {total_images} images. Starting concurrent downloads...\n")
        image_paths: List[str] = []
        completed_count: int = 0
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_post = {
                executor.submit(self._download_single_image, post): post 
                for post in image_posts
            }
            
            for future in as_completed(future_to_post):
                completed_count += 1
                post = future_to_post[future]
                try:
                    local_path, img_filename = future.result()
                    image_paths.append(local_path)
                    print(f"[{completed_count}/{total_images}] Downloaded: {img_filename}")
                except Exception as e:
                    img_filename = f"{post.get('tim', 'unknown')}{post.get('ext', '')}"
                    print(f"[{completed_count}/{total_images}] Failed to download {img_filename}: {e}")
                    
        print(f"\nSuccessfully downloaded {len(image_paths)}/{total_images} images.")
        image_paths.sort()
        return image_paths


class RedditImageSourcePRAW(ImageSource):
    """
    Handles Reddit API interactions via PRAW (Python Reddit API Wrapper).

    NOTE: This is a reference implementation for using the official Reddit API.
    Reddit's official recommendation is to use PRAW for production Reddit API access.

    For authentication and higher rate limits, users can implement this using:
    - PRAW library: https://praw.readthedocs.io/
    - Setup: Requires API credentials from https://www.reddit.com/prefs/apps
    - Environment variables: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT

    Currently, imghndlr uses RedditImageSource instead, which fetches from
    Reddit's public JSON endpoints without authentication. This is simpler for
    end users but subject to Reddit's unauthenticated rate limits.

    To implement this class:
    1. Install PRAW: pip install praw
    2. Create a Reddit app: https://www.reddit.com/prefs/apps
    3. Set environment variables with your credentials
    4. Implement the methods below following the RedditImageSource pattern
    """

    def get_images(self) -> List[str]:
        raise NotImplementedError(
            "RedditImageSourcePRAW is not implemented. "
            "Use --source reddit with RedditImageSource instead (no setup required), "
            "or implement this class using PRAW for authenticated access. "
            "See class docstring for details."
        )


class RedditImageSource(ImageSource):
    """
    Handles Reddit API interactions using public JSON endpoints and concurrent image downloading.

    Usage: --source reddit "<subreddit_name>"
    Example: --source reddit cats
    Note: Use only the subreddit name (without 'r/' prefix). No API credentials required.

    * Fetches top posts from the past week
    * No credentials required; uses Reddit's public JSON endpoints
    * Extracts image URLs from various post types (direct images, galleries, external links)
    * Uses threads to concurrently download images into a target directory
    """

    REDDIT_BASE_URL = "https://www.reddit.com"
    SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

    def __init__(self, subreddit_name: str, target_dir: str) -> None:
        """
        Initializes the image source with a subreddit name and target directory.

        :param subreddit_name: Name of the subreddit to fetch images from (just the name, e.g. 'cats', not 'r/cats')
        :param target_dir: Local filesystem path where images should be saved
        """
        self.subreddit_name: str = subreddit_name
        self.target_dir: str = target_dir

    def _download_single_image(self, url: str, filename: str) -> Tuple[str, str]:
        """
        Downloads a single image from a URL.

        :param url: The URL of the image to download
        :param filename: The filename to save as
        :return: A tuple containing (local_path, filename)
        :raises Exception: If the download fails
        """
        local_path: str = os.path.join(self.target_dir, filename)

        try:
            img_data: bytes = requests.get(url=url, timeout=10).content
            with open(local_path, "wb") as f:
                f.write(img_data)
            return local_path, filename
        except Exception as e:
            raise Exception(f"Failed to download {url}: {e}")

    def _extract_image_urls(self, post_data: Dict[str, Any]) -> List[Tuple[str, str]]:
        """
        Extracts image URLs from a Reddit post JSON object.

        Handles various content types:
        - Direct image posts (i.redd.it, imgur, etc.)
        - Reddit galleries (multi-image posts)
        - External image links

        :param post_data: A post data dictionary from Reddit JSON API
        :return: List of (url, filename) tuples
        """
        urls: List[Tuple[str, str]] = []
        post_id: str = post_data.get("id", "unknown")
        post_url: str = post_data.get("url", "")

        # Handle direct image posts
        if post_url.endswith(tuple(self.SUPPORTED_IMAGE_EXTENSIONS)):
            filename = os.path.basename(post_url).split("?")[0] or f"{post_id}.jpg"
            urls.append((post_url, filename))
        # Handle Reddit galleries (multi-image posts)
        elif post_data.get("gallery_data"):
            gallery_data = post_data["gallery_data"]
            if isinstance(gallery_data, dict) and "items" in gallery_data:
                for idx, item in enumerate(gallery_data["items"]):
                    media_id = item.get("media_id")
                    if media_id:
                        url = f"https://i.redd.it/{media_id}.jpg"
                        urls.append((url, f"{post_id}_{idx}.jpg"))
        # Handle i.redd.it and other direct image hosting
        elif "i.redd.it" in post_url or "imgur.com" in post_url:
            # Remove tracking parameters
            clean_url = post_url.split("?")[0]
            if clean_url.endswith(tuple(self.SUPPORTED_IMAGE_EXTENSIONS)):
                filename = os.path.basename(clean_url) or f"{post_id}.jpg"
                urls.append((clean_url, filename))

        return urls

    def get_images(self) -> List[str]:
        """
        Orchestrates fetching and downloading images from a subreddit.

        Fetches top posts from the past week via Reddit's public JSON API,
        extracts image URLs, and downloads them concurrently.

        :return: List of local file paths to downloaded images
        :raises Exception: If API calls or downloads fail
        """
        try:
            api_url = f"{self.REDDIT_BASE_URL}/r/{self.subreddit_name}/top.json?t=week&limit=100"
            print(f"Fetching posts from r/{self.subreddit_name}...")

            # Set a proper User-Agent to avoid being blocked
            headers = {"User-Agent": "imghndlr/1.0"}
            response = requests.get(url=api_url, headers=headers, timeout=10)
            response.raise_for_status()

            data = response.json()
            posts = data.get("data", {}).get("children", [])

            image_urls: List[Tuple[str, str]] = []
            for post in posts:
                post_data = post.get("data", {})
                urls = self._extract_image_urls(post_data)
                image_urls.extend(urls)

            total_images: int = len(image_urls)
            if total_images == 0:
                return []

            print(f"Found {total_images} images. Starting concurrent downloads...\n")

            image_paths: List[str] = []
            completed_count: int = 0

            with ThreadPoolExecutor(max_workers=10) as executor:
                future_to_url = {
                    executor.submit(self._download_single_image, url, filename): (url, filename)
                    for url, filename in image_urls
                }

                for future in as_completed(future_to_url):
                    completed_count += 1
                    url, filename = future_to_url[future]
                    try:
                        local_path, _ = future.result()
                        image_paths.append(local_path)
                        print(f"[{completed_count}/{total_images}] Downloaded: {filename}")
                    except Exception as e:
                        print(f"[{completed_count}/{total_images}] Failed to download {filename}: {e}")

            print(f"\nSuccessfully downloaded {len(image_paths)}/{total_images} images.")
            image_paths.sort()
            return image_paths

        except Exception as e:
            raise Exception(f"Error fetching from Reddit: {e}")


class DirectoryImageSource(ImageSource):
    """
    Reads a local directory and exposes image file paths as an image source.

    Usage: --source dir "<path>"
    Example: --source dir "/home/user/Pictures" or --source dir "C:\\Users\\user\\Pictures"

    Supports: .jpg, .jpeg, .png, .gif, .bmp, .webp, .tiff, .tif
    """

    SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif"}

    def __init__(self, directory_path: str) -> None:
        self.directory_path: str = os.path.abspath(directory_path)

    def get_images(self) -> List[str]:
        if not os.path.isdir(self.directory_path):
            raise ValueError("Source directory does not exist or is not a directory.")

        image_paths: List[str] = []
        for entry in os.listdir(self.directory_path):
            path = os.path.join(self.directory_path, entry)
            extension = os.path.splitext(entry)[1].lower()
            if os.path.isfile(path) and extension in self.SUPPORTED_EXTENSIONS:
                image_paths.append(path)

        image_paths.sort()
        return image_paths


# TODO: Some sort of zoom functionality
# TODO: Some sort of scrolling or "window in picture" for nonstandard images, ex. HUGE wallpapers, comics, etc.
class ImgGalleryUI:
    """
    Handles the graphical user interface, event bindings, and image presentation.
    
    This class wraps a tkinter Tk root instance to construct a functional image gallery desktop app.

    * Supports automatic scaling based on window size
    * Allows asynchronous entry focus stripping [What?]
    * Status persistence checking
    * End user directory mapping (for saving files)
    """
    
    def __init__(self, root: tk.Tk, image_paths: List[str], source_directory: Optional[str] = None) -> None:
        """
        Initializes UI workspace, state registers, and active graphics canvas.

        :param root: The active tk.Tk() window wrapper context.
        :param image_paths: List of strings, path mappings pointing to downloaded images.
        :param source_directory: Optional directory path where the source images are located.
                                 Used to prevent users from accidentally saving back to the source.
                                 Not set for temporary 4chan downloads (which we don't protect).
        """
        self.root: tk.Tk = root
        self.root.title(string="imghndlr Gallery")
        self.root.geometry(newGeometry="800x700")
        self.root.minsize(width=450, height=450)
        
        self.image_paths: List[str] = image_paths
        self.source_directory: Optional[str] = source_directory
        self.current_index: int = 0
        self.current_raw_img: Optional[Image.Image] = None
        self.tk_img: Optional[ImageTk.PhotoImage] = None
        
        # UI Component Declarations
        self.status_bar: tk.Label
        self.dir_entry: tk.Entry
        self.save_btn: tk.Button
        self.delete_btn: tk.Button
        self.reveal_btn: tk.Button
        self.prev_btn: tk.Button
        self.status_label: tk.Label
        self.next_btn: tk.Button
        self.image_label: tk.Label
        
        if not self.image_paths:
            self._show_empty_message()
            return

        self._build_ui()
        self._bind_events()
        self._load_image_data()

    def _load_saved_directory(self) -> str:
        """
        Loads the saved directory from imghndlr.conf if enabled.
        """
        if ImgHndlrOrchestrator.CONFIG_FILE and os.path.exists(ImgHndlrOrchestrator.CONFIG_FILE):
            try:
                with open(ImgHndlrOrchestrator.CONFIG_FILE, "r") as f:
                    config = json.load(f)
                    saved_path = config.get("save_directory", "")
                    if saved_path:
                        return saved_path
            except Exception:
                pass
        return os.getcwd()

    def _save_directory_to_config(self, path: str) -> None:
        """
        Persists the target directory path into imghndlr.conf only if enabled.
        """
        if not ImgHndlrOrchestrator.CONFIG_FILE:
            return  # Skip silently if --conf wasn't provided
            
        try:
            config = {"save_directory": path}
            with open(ImgHndlrOrchestrator.CONFIG_FILE, "w") as f:
                json.dump(config, f, indent=4)
        except Exception as e:
            print(f"Warning: Failed to save directory configuration: {e}")

    def _build_ui(self) -> None:
        """
        Constructs and packs the visual widget layout tree inside the host application window.
        """
        # 1. Save Status Bar (Absolute Bottom)
        self.status_bar = tk.Label(master=self.root, text="", font=("Arial", 11, "bold"), bd=1, relief="sunken", anchor="w", padx=10, pady=5)
        self.status_bar.pack(side="bottom", fill="x")
        
        # 2. Save Input Frame (Above Status Bar)
        save_frame = tk.Frame(master=self.root)
        save_frame.pack(side="bottom", fill="x", pady=5, padx=20)
        
        save_label = tk.Label(master=save_frame, text="Save Directory:", font=("Arial", 10))
        save_label.pack(side="left", padx=5)
        
        self.dir_entry = tk.Entry(master=save_frame, font=("Arial", 10))
        self.dir_entry.pack(side="left", expand=True, fill="x", padx=5)
        
        initial_dir = self._load_saved_directory()
        self.dir_entry.insert(index=0, string=initial_dir)
        
        self.save_btn = tk.Button(master=save_frame, text="Save Image (Space)", command=self.save_current_image, bg="#4CAF50", fg="white")
        self.save_btn.pack(side="left", padx=5)
        
        self.delete_btn = tk.Button(master=save_frame, text="Delete (Del)", command=self.delete_current_image, bg="#f44336", fg="white")
        self.delete_btn.pack(side="left", padx=5)

        self.reveal_btn = tk.Button(master=save_frame, text="Reveal (R)", command=self.reveal_current_image, bg="#2196F3", fg="white")
        self.reveal_btn.pack(side="left", padx=5)
        
        # 3. Navigation Controls Frame (Above Save Frame)
        nav_frame = tk.Frame(master=self.root)
        nav_frame.pack(side="bottom", fill="x", pady=5)
        
        self.prev_btn = tk.Button(master=nav_frame, text="◀ Left", command=self.show_prev, width=10)
        self.prev_btn.pack(side="left", padx=20)
        
        self.status_label = tk.Label(master=nav_frame, text="", font=("Arial", 12))
        self.status_label.pack(side="left", expand=True)

        self.file_info_label = tk.Label(master=nav_frame, text="", font=("Arial", 10), fg="#555555")
        self.file_info_label.pack(side="left", padx=10)
        
        self.next_btn = tk.Button(master=nav_frame, text="Right ▶", command=self.show_next, width=10)
        self.next_btn.pack(side="right", padx=20)
        
        # 4. Image Canvas Last (Fills the center completely)
        self.image_label = tk.Label(master=self.root, anchor="center")
        self.image_label.pack(side="top", expand=True, fill="both")

    def _bind_events(self) -> None:
        """
        Attaches system key hooks, widget focus managers, and container configuration listeners.
        """
        self.root.bind(sequence="<Left>", func=self._handle_left_key)
        self.root.bind(sequence="<Right>", func=self._handle_right_key)
        self.root.bind(sequence="<space>", func=self._handle_space_key)
        self.root.bind(sequence="<Delete>", func=self._handle_delete_key)
        self.root.bind(sequence="r", func=self._handle_reveal_key)
        self.root.bind(sequence="R", func=self._handle_reveal_key)
        
        # Bind Escape key to exit the UI application window context
        self.root.bind(sequence="<Escape>", func=self._handle_escape_key)
        
        # Strip focus hooks
        self.root.bind(sequence="<Button-1>", func=self._clear_entry_focus)
        self.image_label.bind(sequence="<Button-1>", func=self._clear_entry_focus)
        
        self.dir_entry.bind(sequence="<KeyRelease>", func=self._handle_dir_entry_change)
        
        # Resize hooks
        self.image_label.bind(sequence="<Configure>", func=self._on_window_resize)

    def _show_empty_message(self) -> None:
        """
        Packs a default fallback message widget if zero valid images are available to display.
        """
        lbl = tk.Label(master=self.root, text="No images found or downloaded.", font=("Arial", 14))
        lbl.pack(expand=True)

    def _clear_entry_focus(self, event: tk.Event) -> None:
        """
        Unfocuses the directory entry widget if the user clicks anywhere else on the GUI canvas.

        Ensures that keyboard shortcuts (like Spacebar navigating or saving) do not accidentally
        type characters into the directory string input field.
        """
        if event.widget != self.dir_entry:
            self.root.focus()

    def _handle_dir_entry_change(self, event: tk.Event) -> None:
        """
        Fires whenever the user alters the text entry, logging configuration updates instantly.
        """
        target_dir = self.dir_entry.get().strip()
        self._save_directory_to_config(target_dir)
        self.update_save_status()

    def _load_image_data(self) -> None:
        """
        Loads the current index target file into system memory using PIL.

        Resets text alerts, safely catches disk exceptions if files are unreadable,
        and triggers a downsampled UI refresh cycle.
        """
        if not self.image_paths:
            return
            
        self.status_label.config(text=f"Image {self.current_index + 1} of {len(self.image_paths)}")
        img_path: str = self.image_paths[self.current_index]
        filename = os.path.basename(img_path)
        self.file_info_label.config(text=filename)
        
        try:
            self.current_raw_img = Image.open(fp=img_path)
        except Exception:
            self.current_raw_img = None
            self.image_label.config(image="", text=f"Error loading image:\n{filename}")
            
        self.render_scaled_image()
        self.update_save_status()

    def render_scaled_image(self) -> None:
        """
        Calculates and applies proportional scaling to the active image asset.

        Fits the graphics seamlessly inside the parent container constraints 
        using high-fidelity LANCZOS interpolation filters.
        """
        if not self.current_raw_img:
            return
            
        display_width: int = self.image_label.winfo_width()
        display_height: int = self.image_label.winfo_height()
        
        if display_width <= 1 or display_height <= 1:
            display_width, display_height = 750, 450
            
        img_copy: Image.Image = self.current_raw_img.copy()
        img_copy.thumbnail(size=(display_width, display_height), resample=Image.Resampling.LANCZOS)
        
        self.tk_img = ImageTk.PhotoImage(image=img_copy)
        self.image_label.config(image=self.tk_img, text="")

    def _on_window_resize(self, event: tk.Event) -> None:
        """
        Event callback bound to container structural adjustments.

        :param event: The Tkinter configuration event details triggered by GUI window resizing.
        """
        self.render_scaled_image()

    def show_prev(self) -> None:
        """
        Cycles backward to the previous available image in the list index, wrapping around if needed.
        """
        if self.image_paths:
            self.current_index = (self.current_index - 1) % len(self.image_paths)
            self._load_image_data()

    def show_next(self) -> None:
        """
        Cycles forward to the next available image in the list index, wrapping around if needed.
        """
        if self.image_paths:
            self.current_index = (self.current_index + 1) % len(self.image_paths)
            self._load_image_data()

    def _handle_left_key(self, event: tk.Event) -> None:
        """
        Event binding bridge routing Left Arrow keyboard presses to show_prev execution.
        """
        self.show_prev()

    def _handle_right_key(self, event: tk.Event) -> None:
        """
        Event binding bridge routing Right Arrow keyboard presses to show_next execution.
        """
        self.show_next()

    def _handle_space_key(self, event: tk.Event) -> None:
        """
        Event binding bridge routing Spacebar keyboard presses to save operations.

        Ignores execution calls if the user is explicitly focused on editing text inside the
        target path input box.
        """
        if self.root.focus_get() != self.dir_entry:
            self.save_current_image()

    def _handle_delete_key(self, event: tk.Event) -> None:
        """
        Event binding bridge routing Delete key presses to delete operations.

        Ignores execution calls if the user is explicitly focused on editing text inside the
        target path input box.
        """
        if self.root.focus_get() != self.dir_entry:
            self.delete_current_image()

    def _handle_reveal_key(self, event: tk.Event) -> None:
        """
        Event binding bridge routing the R key to the reveal operation.

        Ignores execution calls if the user is explicitly focused on editing text inside the
        target path input box.
        """
        if self.root.focus_get() != self.dir_entry:
            self.reveal_current_image()

    def _handle_escape_key(self, event: tk.Event) -> None:
        """
        Event binding bridge routing Escape key pressures to UI close routine.
        """
        self.root.destroy()

    def update_save_status(self) -> None:
        """
        Evaluates whether the currently viewed file exists in the specified destination directory.

        Dynamically mutates the visual color accents and textual labeling of the lower status 
        bar to notify the user whether the image is saved or unsaved.
        """
        if not self.image_paths:
            return
        target_dir: str = self.dir_entry.get().strip()
        src_path: str = self.image_paths[self.current_index]
        filename: str = os.path.basename(src_path)
        dest_path: str = os.path.join(target_dir, filename)
        
        if target_dir and os.path.exists(dest_path):
            self.status_bar.config(text="  Saved to destination", fg="#2e7d32")
        else:
            self.status_bar.config(text="❌ Not Saved to destination", fg="#c62828")

    def save_current_image(self) -> None:
        """
        Copies the currently selected temporary cached image file into a permanent local directory.

        Creates structural directories on demand if they do not yet exist, and throws visual/textual
        exceptions down to the status bar container if directory access is denied.
        """
        if not self.image_paths:
            return
        target_dir: str = self.dir_entry.get().strip()
        if not target_dir:
            self.status_bar.config(text="⚠ Error: Please specify a target directory first.", fg="#d84315")
            return

        # Prevent saving back to the source directory (for local directory browsing)
        if self.source_directory and os.path.abspath(target_dir) == os.path.abspath(self.source_directory):
            self.status_bar.config(text="⚠ Error: Target directory cannot be the source directory.", fg="#d84315")
            return
            
        self._save_directory_to_config(target_dir)

        if not os.path.exists(target_dir):
            try:
                os.makedirs(name=target_dir, exist_ok=True)
            except Exception:
                self.status_bar.config(text="⚠ Error: Could not create directory.", fg="#d84315")
                return
                
        src_path: str = self.image_paths[self.current_index]
        filename: str = os.path.basename(src_path)
        dest_path: str = os.path.join(target_dir, filename)
        
        try:
            shutil.copy(src=src_path, dst=dest_path)
            print(f"Saved copy to: {dest_path}")
            self.update_save_status()
        except Exception:
            self.status_bar.config(text="⚠ Error: Failed to copy file.", fg="#d84315")

    def delete_current_image(self) -> None:
        """
        Deletes the currently selected image from the target save directory if it exists.

        Updates status bar with feedback and navigates to the next image after deletion.
        """
        if not self.image_paths:
            return
        target_dir: str = self.dir_entry.get().strip()
        if not target_dir:
            self.status_bar.config(text="⚠ Error: Please specify a target directory first.", fg="#d84315")
            return

        # Prevent deleting from the source directory (for local directory browsing)
        if self.source_directory and os.path.abspath(target_dir) == os.path.abspath(self.source_directory):
            self.status_bar.config(text="⚠ Error: Cannot delete from the source directory.", fg="#d84315")
            return

        src_path: str = self.image_paths[self.current_index]
        filename: str = os.path.basename(src_path)
        dest_path: str = os.path.join(target_dir, filename)

        if not os.path.exists(dest_path):
            self.status_bar.config(text="✓ File not in destination (nothing to delete).", fg="#ff9800")
            return

        try:
            os.remove(dest_path)
            print(f"Deleted: {dest_path}")
            self.status_bar.config(text="✓ Image deleted from destination.", fg="#2e7d32")
            self.update_save_status()
        except Exception as e:
            self.status_bar.config(text="⚠ Error: Failed to delete file.", fg="#d84315")

    def reveal_current_image(self) -> None:
        """
        Opens the current image in the system file browser if it exists in the target directory.

        If the image is not yet saved in the target directory, this method does nothing.
        """
        if not self.image_paths:
            return

        target_dir: str = self.dir_entry.get().strip()
        if not target_dir:
            return

        src_path: str = self.image_paths[self.current_index]
        filename: str = os.path.basename(src_path)
        dest_path: str = os.path.join(target_dir, filename)

        if not os.path.exists(dest_path):
            return

        try:
            if sys.platform.startswith("win"):
                os.startfile(dest_path)
            elif sys.platform == "darwin":
                subprocess.run(["open", "-R", dest_path], check=False)
            else:
                subprocess.run(["xdg-open", os.path.dirname(dest_path)], check=False)
        except Exception:
            pass


class SourceType(Enum):
    """Enumeration of available image source types."""
    FOURCHAN = "4chan"
    DIRECTORY = "dir"
    REDDIT = "reddit"


class ImgHndlrOrchestrator:
    """
    Central manager for primary workflow:
        * Handles terminal prompts 
        * Orchestrates image sources
        * Manages temporary directories
        * Launches the GUI
    
    Session application scope absolute lifestyle controller (try saying that 3 times fast).
    """

    CONFIG_FILE: Optional[str] = None

    def __init__(self) -> None:
        pass

    @staticmethod
    def parse_args() -> argparse.Namespace:
        parser = argparse.ArgumentParser(
            description="Fetch and browse images from various sources.",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""Examples:
  python imghndlr.py --source 4chan "https://boards.4channel.org/wg/thread/<id>"
  python imghndlr.py --source dir "/path/to/images"
  python imghndlr.py --source reddit cats
            """
        )
        parser.add_argument(
            "--conf",
            action="store_true",
            help="Enable saving the image save directory path to imghndlr.conf.",
        )
        parser.add_argument(
            "--source",
            choices=[s.value for s in SourceType],
            required=True,
            help="Image source type: '4chan' (4chan thread), 'dir' (local directory), or 'reddit' (subreddit).",
        )
        parser.add_argument(
            "source_input",
            help="Source-specific input: Full 4chan thread URL | Local directory path | Subreddit name (without 'r/').",
        )
        return parser.parse_args()

    def run(
        self,
        source_type: SourceType,
        source_input: str,
        use_config: bool = False,
    ) -> None:
        """
        Orchestrates the workflow for a given source type and input.

        :param source_type: The resolved source type enum.
        :param source_input: The source-specific input string.
        :param use_config: Whether to enable config file persistence
        """
        if use_config:
            ImgHndlrOrchestrator.CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "imghndlr.conf")

        tmpdir = None
        with ExitStack() as stack:
            if source_type in (SourceType.FOURCHAN, SourceType.REDDIT):
                tmpdir = stack.enter_context(tempfile.TemporaryDirectory())
                print(f"Created temporary directory at: {tmpdir}")
                stack.callback(lambda: print("Temporary directory is now being cleaned up..."))

            match source_type:
                case SourceType.DIRECTORY:
                    source = DirectoryImageSource(directory_path=source_input)
                case SourceType.FOURCHAN:
                    source = FourChanImageSource(thread_url=source_input, target_dir=tmpdir)
                case SourceType.REDDIT:
                    source = RedditImageSource(subreddit_name=source_input, target_dir=tmpdir)
                case _:
                    raise AssertionError("Unsupported source type. This should never happen due to argparse choices.")

            try:
                image_paths: List[str] = source.get_images()
            except Exception as e:
                print(f"Error handling image source operations: {e}")
                return

            if not image_paths:
                print("No images were found or downloaded.")
                return

            source_directory: Optional[str] = None
            if isinstance(source, DirectoryImageSource):
                source_directory = source.directory_path

            root: tk.Tk = tk.Tk()
            app = ImgGalleryUI(root=root, image_paths=image_paths, source_directory=source_directory)
            root.mainloop()
            print("GUI closed.")

        if tmpdir is not None:
            print("Cleanup complete. Goodbye!")

    @classmethod
    def main(cls) -> None:
        """
        Parses CLI arguments and delegates orchestration to run().
        """
        args = cls.parse_args()
        source_type = SourceType(args.source)
        
        orchestrator = cls()
        orchestrator.run(source_type=source_type, source_input=args.source_input, use_config=args.conf)


if __name__ == "__main__":
    ImgHndlrOrchestrator.main()