import json
import os
import shutil
import subprocess
import sys
import tkinter as tk
from PIL import Image, ImageTk
from typing import List, Optional

__all__ = ["ImgGalleryUI"]

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

    def __init__(
        self,
        root: tk.Tk,
        image_paths: List[str],
        source_directory: Optional[str] = None,
        config_file: Optional[str] = None,
    ) -> None:
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
        self.config_file: Optional[str] = config_file
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
        if self.config_file and os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f:
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
        if not self.config_file:
            return  # Skip silently if --conf wasn't provided

        try:
            config = {"save_directory": path}
            with open(self.config_file, "w") as f:
                json.dump(config, f, indent=4)
        except Exception as e:
            print(f"Warning: Failed to save directory configuration: {e}")

    def _build_ui(self) -> None:
        """
        Constructs and packs the visual widget layout tree inside the host application window.
        """
        # 1. Save Status Bar (Absolute Bottom)
        self.status_bar = tk.Label(
            master=self.root,
            text="",
            font=("Arial", 11, "bold"),
            bd=1,
            relief="sunken",
            anchor="w",
            padx=10,
            pady=5,
        )
        self.status_bar.pack(side="bottom", fill="x")

        # 2. Save Input Frame (Above Status Bar)
        save_frame = tk.Frame(master=self.root)
        save_frame.pack(side="bottom", fill="x", pady=5, padx=20)

        save_label = tk.Label(
            master=save_frame, text="Save Directory:", font=("Arial", 10)
        )
        save_label.pack(side="left", padx=5)

        self.dir_entry = tk.Entry(master=save_frame, font=("Arial", 10))
        self.dir_entry.pack(side="left", expand=True, fill="x", padx=5)

        initial_dir = self._load_saved_directory()
        self.dir_entry.insert(index=0, string=initial_dir)

        self.save_btn = tk.Button(
            master=save_frame,
            text="Save Image (Space)",
            command=self.save_current_image,
            bg="#4CAF50",
            fg="white",
        )
        self.save_btn.pack(side="left", padx=5)

        self.delete_btn = tk.Button(
            master=save_frame,
            text="Delete (Del)",
            command=self.delete_current_image,
            bg="#f44336",
            fg="white",
        )
        self.delete_btn.pack(side="left", padx=5)

        self.reveal_btn = tk.Button(
            master=save_frame,
            text="Reveal (R)",
            command=self.reveal_current_image,
            bg="#2196F3",
            fg="white",
        )
        self.reveal_btn.pack(side="left", padx=5)

        # 3. Navigation Controls Frame (Above Save Frame)
        nav_frame = tk.Frame(master=self.root)
        nav_frame.pack(side="bottom", fill="x", pady=5)

        self.prev_btn = tk.Button(
            master=nav_frame, text="◀ Left", command=self.show_prev, width=10
        )
        self.prev_btn.pack(side="left", padx=20)

        self.status_label = tk.Label(master=nav_frame, text="", font=("Arial", 12))
        self.status_label.pack(side="left", expand=True)

        self.file_info_label = tk.Label(
            master=nav_frame, text="", font=("Arial", 10), fg="#555555"
        )
        self.file_info_label.pack(side="left", padx=10)

        self.next_btn = tk.Button(
            master=nav_frame, text="Right ▶", command=self.show_next, width=10
        )
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
        lbl = tk.Label(
            master=self.root, text="No images found or downloaded.", font=("Arial", 14)
        )
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

        self.status_label.config(
            text=f"Image {self.current_index + 1} of {len(self.image_paths)}"
        )
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
        img_copy.thumbnail(
            size=(display_width, display_height), resample=Image.Resampling.LANCZOS
        )

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
            self.status_bar.config(
                text="⚠ Error: Please specify a target directory first.", fg="#d84315"
            )
            return

        # Prevent saving back to the source directory (for local directory browsing)
        if self.source_directory and os.path.abspath(target_dir) == os.path.abspath(
            self.source_directory
        ):
            self.status_bar.config(
                text="⚠ Error: Target directory cannot be the source directory.",
                fg="#d84315",
            )
            return

        self._save_directory_to_config(target_dir)

        if not os.path.exists(target_dir):
            try:
                os.makedirs(name=target_dir, exist_ok=True)
            except Exception:
                self.status_bar.config(
                    text="⚠ Error: Could not create directory.", fg="#d84315"
                )
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
            self.status_bar.config(
                text="⚠ Error: Please specify a target directory first.", fg="#d84315"
            )
            return

        # Prevent deleting from the source directory (for local directory browsing)
        if self.source_directory and os.path.abspath(target_dir) == os.path.abspath(
            self.source_directory
        ):
            self.status_bar.config(
                text="⚠ Error: Cannot delete from the source directory.", fg="#d84315"
            )
            return

        src_path: str = self.image_paths[self.current_index]
        filename: str = os.path.basename(src_path)
        dest_path: str = os.path.join(target_dir, filename)

        if not os.path.exists(dest_path):
            self.status_bar.config(
                text="✓ File not in destination (nothing to delete).", fg="#ff9800"
            )
            return

        try:
            os.remove(dest_path)
            print(f"Deleted: {dest_path}")
            self.status_bar.config(
                text="✓ Image deleted from destination.", fg="#2e7d32"
            )
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