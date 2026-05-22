import argparse
import os
import shutil
import tempfile
import tkinter as tk
import json
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple, Dict, Any, Optional
import requests
from PIL import Image, ImageTk


class ImgDownloader:
    """
    Handles 4chan API interactions and concurrent image downloading.

    * Takes a standard 4chan thread URL and identifies relevant board and thread identifiers
    * Fetches JSON payload from 4chan data API
    * Uses threads to concurrently download media assets into a target directory
    """
    
    def __init__(self, thread_url: str, target_dir: str) -> None:
        """
        Initializes downloader with source URL and (local) target directory.

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
        Worker function intended for execution within a thread pool to fetch an individual file.

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

    def fetch_and_download(self) -> List[str]:
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
    
    def __init__(self, root: tk.Tk, image_paths: List[str]) -> None:
        """
        Initializes UI workspace, state registers, and active graphics canvas.

        :param root: The active tk.Tk() window wrapper context.
        :param image_paths: List of strings, path mappings pointing to downloaded images.
        """
        self.root: tk.Tk = root
        self.root.title(string="imghndlr - 4chan Gallery")
        self.root.geometry(newGeometry="800x700")
        self.root.minsize(width=450, height=450)
        
        self.image_paths: List[str] = image_paths
        self.current_index: int = 0
        self.current_raw_img: Optional[Image.Image] = None
        self.tk_img: Optional[ImageTk.PhotoImage] = None
        
        # UI Component Declarations
        self.status_bar: tk.Label
        self.dir_entry: tk.Entry
        self.save_btn: tk.Button
        self.delete_btn: tk.Button
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
        
        # 3. Navigation Controls Frame (Above Save Frame)
        nav_frame = tk.Frame(master=self.root)
        nav_frame.pack(side="bottom", fill="x", pady=5)
        
        self.prev_btn = tk.Button(master=nav_frame, text="◀ Left", command=self.show_prev, width=10)
        self.prev_btn.pack(side="left", padx=20)
        
        self.status_label = tk.Label(master=nav_frame, text="", font=("Arial", 12))
        self.status_label.pack(side="left", expand=True)
        
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
        
        try:
            self.current_raw_img = Image.open(fp=img_path)
        except Exception:
            self.current_raw_img = None
            self.image_label.config(image="", text=f"Error loading image:\n{os.path.basename(img_path)}")
            
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


class ImgHndlrOrchestrator:
    """
    Central manager for primary workflow:
        * Handles terminal prompts 
        * Orchestrates downloads
        * Manages temporary directories
        * Launches the GUI
    
    Session application scope absolute lifestyle controller (try saying that 3 times fast).
    """

    CONFIG_FILE: Optional[str] = None

    def __init__(self) -> None:
        pass

    @staticmethod
    def parse_args() -> argparse.Namespace:
        parser = argparse.ArgumentParser(description="Download and browse 4chan thread images.")
        parser.add_argument(
            "thread_url",
            nargs="?",
            help="4chan thread URL to download images from. If omitted, the program will prompt for it.",
        )
        parser.add_argument(
            "--conf",
            action="store_true",
            help="Enable saving the image save directory path to imghndlr.conf.",
        )
        return parser.parse_args()

    def run(self, thread_url: Optional[str] = None, use_config: bool = False) -> None:
        """
        Prompts input, constructs handlers, executes operations, and cleans up assets.

        Establishes an isolated context-managed system path, triggers network collection workers,
        initializes parent tkinter rendering routines, and flushes temporary space upon program exit.
        """
        if use_config:
            ImgHndlrOrchestrator.CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "imghndlr.conf")

        if not thread_url:
            thread_url = input("Enter 4chan Thread URL: ").strip()

        if not thread_url:
            print("URL cannot be empty.")
            return

        with tempfile.TemporaryDirectory() as tmpdir:
            print(f"Created temporary directory at: {tmpdir}")

            try:
                downloader = ImgDownloader(thread_url=thread_url, target_dir=tmpdir)
                downloaded_images: List[str] = downloader.fetch_and_download()
            except Exception as e:
                print(f"Error handling download operations: {e}")
                return

            if not downloaded_images:
                print("No images were downloaded.")
                return

            root: tk.Tk = tk.Tk()
            app = ImgGalleryUI(root=root, image_paths=downloaded_images)
            root.mainloop()

            print("GUI closed. Temporary directory is now being cleaned up...")

        print("Cleanup complete. Goodbye!")

    @classmethod
    def main(cls) -> None:
        """
        Initializes and runs the ImgHndlrOrchestrator using argparse.
        """
        args = cls.parse_args()
        orchestrator = cls()
        orchestrator.run(thread_url=args.thread_url, use_config=args.conf)


if __name__ == "__main__":
    ImgHndlrOrchestrator.main()