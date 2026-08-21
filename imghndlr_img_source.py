import os
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from enum import Enum
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

import requests

from imghndlr_utils import ElapsedTimer


class SourceType(Enum):
    """Enumeration of available image source types."""

    FOURCHAN = "4chan"
    DIRECTORY = "dir"
    REDDIT = "reddit"

    @classmethod
    def supported_types(cls) -> List["SourceType"]:
        """
        Return the currently supported source types, excluding disabled options.
        """
        excluded_types = {
            cls.REDDIT
        }  # Exclude Reddit for now since the public JSON API is no longer supported >:(
        return [source_type for source_type in cls if source_type not in excluded_types]


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

    def __init__(
        self, thread_url: str, target_dir: str, allow_webm: bool = False
    ) -> None:
        """
        Initializes the image source with a thread URL and a local target directory.

        :param thread_url: Full web address of the target 4chan thread.
        :param target_dir: Local filesystem path where images should be saved.
        """
        self.thread_url: str = thread_url
        self.target_dir: str = target_dir
        self.allow_webm: bool = allow_webm
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
        image_posts: List[Dict[str, Any]] = [
            p
            for p in posts
            if "tim" in p
            and "ext" in p
            and (self.allow_webm or p["ext"].lower() != ".webm")
        ]
        total_images: int = len(image_posts)

        if total_images == 0:
            return []

        print(f"Found {total_images} images. Starting concurrent downloads...\n")
        image_paths: List[str] = []
        completed_count: int = 0
        download_timer = ElapsedTimer()

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
                    print(
                        f"[{completed_count}/{total_images}] Downloaded: {img_filename} | "
                        f"Elapsed: {download_timer.format_elapsed()}"
                    )
                except Exception as e:
                    img_filename = f"{post.get('tim', 'unknown')}{post.get('ext', '')}"
                    print(
                        f"[{completed_count}/{total_images}] Failed to download "
                        f"{img_filename}: {e} | Elapsed: {download_timer.format_elapsed()}"
                    )

        print(
            f"\nSuccessfully downloaded {len(image_paths)}/{total_images} images "
            f"in {download_timer.format_elapsed()}."
        )
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
            download_timer = ElapsedTimer()

            with ThreadPoolExecutor(max_workers=10) as executor:
                future_to_url = {
                    executor.submit(self._download_single_image, url, filename): (
                        url,
                        filename,
                    )
                    for url, filename in image_urls
                }

                for future in as_completed(future_to_url):
                    completed_count += 1
                    url, filename = future_to_url[future]
                    try:
                        local_path, _ = future.result()
                        image_paths.append(local_path)
                        print(
                            f"[{completed_count}/{total_images}] Downloaded: {filename} | "
                            f"Elapsed: {download_timer.format_elapsed()}"
                        )
                    except Exception as e:
                        print(
                            f"[{completed_count}/{total_images}] Failed to download "
                            f"{filename}: {e} | Elapsed: {download_timer.format_elapsed()}"
                        )

            print(
                f"\nSuccessfully downloaded {len(image_paths)}/{total_images} images "
                f"in {download_timer.format_elapsed()}."
            )
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

    SUPPORTED_EXTENSIONS = {
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".bmp",
        ".webp",
        ".tiff",
        ".tif",
    }

    def __init__(self, directory_path: str, allow_webm: bool = False) -> None:
        self.directory_path: str = os.path.abspath(directory_path)
        self.allow_webm: bool = allow_webm

    def get_images(self) -> List[str]:
        if not os.path.isdir(self.directory_path):
            raise ValueError("Source directory does not exist or is not a directory.")

        entries = os.listdir(self.directory_path)
        supported_extensions = self.SUPPORTED_EXTENSIONS
        if self.allow_webm:
            supported_extensions = supported_extensions | {".webm"}

        candidate_entries = [
            entry
            for entry in entries
            if os.path.isfile(os.path.join(self.directory_path, entry))
            and os.path.splitext(entry)[1].lower() in supported_extensions
        ]
        image_paths: List[str] = []
        load_timer = ElapsedTimer()
        total_images = len(candidate_entries)

        for completed_count, entry in enumerate(candidate_entries, start=1):
            path = os.path.join(self.directory_path, entry)
            image_paths.append(path)
            print(
                f"[{completed_count}/{total_images}] Loaded: {entry} | "
                f"Elapsed: {load_timer.format_elapsed()}"
            )

        image_paths.sort()
        if total_images:
            print(f"Loaded {total_images} images in {load_timer.format_elapsed()}.")
        return image_paths
