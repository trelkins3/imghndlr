import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from PIL import Image
from PIL.ExifTags import GPSTAGS, TAGS


class Dataset(ABC):
    """
    Abstract base class for datasets returned by handler plugins.

    Represents processed image data ready to be loaded into the UI.
    Subclasses should implement the appropriate data structure for their
    specific handler's output format.

    The dataset maintains a correlation between image paths and their
    associated metadata, allowing the UI to look up metadata for any
    displayed image.
    """

    @abstractmethod
    def get_image_paths(self) -> List[str]:
        """Return the list of image paths that can be displayed."""

    @abstractmethod
    def get_metadata(self) -> Dict[str, Any]:
        """Return metadata associated with the processed images."""

    @abstractmethod
    def get_metadata_for_image(self, image_path: str) -> Dict[str, Any]:
        """
        Retrieve metadata for a specific image.

        :param image_path: The path (or name) of the image.
        :return: Dictionary of metadata for that image, or empty dict if not found.
        """

    @abstractmethod
    def get_metadata_by_index(self, index: int) -> Dict[str, Any]:
        """
        Retrieve metadata for an image by its index in the image paths list.

        :param index: Index in the image paths list.
        :return: Dictionary of metadata for that image, or empty dict if index is invalid.
        """


class SimpleDataset(Dataset):
    """
    Basic dataset implementation for handlers that correlate images with metadata.

    Maintains a mapping between image paths and their associated metadata,
    enabling quick lookups by path or index.
    """

    def __init__(
        self,
        image_paths: List[str],
        metadata_by_path: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> None:
        """
        Initialize a simple dataset with image paths and correlated metadata.

        :param image_paths: Ordered list of image file paths or names.
        :param metadata_by_path: Dictionary mapping image path to metadata dict.
                                 If None, each image gets an empty metadata dict.
        """
        self.image_paths: List[str] = image_paths
        self.metadata_by_path: Dict[str, Dict[str, Any]] = metadata_by_path or {}

        # Ensure all image paths have a metadata entry (even if empty)
        for path in self.image_paths:
            if path not in self.metadata_by_path:
                self.metadata_by_path[path] = {}

    def get_image_paths(self) -> List[str]:
        return self.image_paths

    def get_metadata(self) -> Dict[str, Any]:
        """Return the entire metadata mapping keyed by image path."""
        return self.metadata_by_path

    def get_metadata_for_image(self, image_path: str) -> Dict[str, Any]:
        """
        Retrieve metadata for a specific image by its path.

        :param image_path: The image path or name to look up.
        :return: Dictionary of metadata for that image, or empty dict if not found.
        """
        return self.metadata_by_path.get(image_path, {})

    def get_metadata_by_index(self, index: int) -> Dict[str, Any]:
        """
        Retrieve metadata for an image by its index in the image paths list.

        :param index: Index in the image paths list (0-based).
        :return: Dictionary of metadata for that image, or empty dict if index is invalid.
        """
        if 0 <= index < len(self.image_paths):
            image_path = self.image_paths[index]
            return self.metadata_by_path.get(image_path, {})
        return {}

    def add_metadata(self, image_path: str, metadata: Dict[str, Any]) -> None:
        """
        Add or update metadata for a specific image.

        Useful for incrementally building the dataset as images are processed.

        :param image_path: The image path to associate metadata with.
        :param metadata: Dictionary of metadata to add/merge.
        """
        if image_path not in self.metadata_by_path:
            self.metadata_by_path[image_path] = {}
        self.metadata_by_path[image_path].update(metadata)

    def update_metadata_entry(self, image_path: str, **kwargs) -> None:
        """
        Update metadata for a specific image using keyword arguments.

        Convenient shorthand for adding individual metadata fields.

        :param image_path: The image path to update.
        :param kwargs: Key-value pairs to add/update in the metadata.
        """
        if image_path not in self.metadata_by_path:
            self.metadata_by_path[image_path] = {}
        self.metadata_by_path[image_path].update(kwargs)


class HandlerPlugin(ABC):
    """
    Abstract base class for image handler plugins.

    Handlers process a set of images and return a dataset that can be
    loaded and displayed in the UI. This allows for flexible, composable
    image processing workflows (e.g., filtering, sorting, augmentation, analysis).

    Subclasses must implement the handle() method to define their specific
    image processing logic.
    """

    def __init__(self, name: str, description: str = "") -> None:
        """
        Initialize the handler plugin.

        :param name: Unique identifier for this handler.
        :param description: Human-readable description of what this handler does.
        """
        self.name: str = name
        self.description: str = description

    @abstractmethod
    def handle(self, image_paths: List[str]) -> Dataset:
        """
        Process a collection of images and return a dataset.

        This is the core method that subclasses must implement. It should:
        1. Take the provided image paths
        2. Apply the handler's specific processing logic
        3. Return a Dataset containing the results

        :param image_paths: List of file paths to images to process.
        :return: A Dataset containing the processed images and associated metadata.
        """

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r}, description={self.description!r})"


class ImageAnalyzerHandler(HandlerPlugin):
    """
    Analyzes images and extracts visual metadata.

    For each image, extracts:
    - Dimensions (width, height)
    - Aspect ratio
    - File size (in KB)
    - Color mode (RGB, RGBA, L, etc.)

    If an image fails to analyze, stores the error message in metadata.
    """

    def __init__(self) -> None:
        super().__init__(
            name="image_analyzer",
            description="Extracts visual metadata from images (dimensions, size, color mode, etc.)"
        )

    def handle(self, image_paths: List[str]) -> SimpleDataset:
        """
        Process images and extract visual metadata.

        :param image_paths: List of image file paths to analyze.
        :return: Dataset with images and their extracted metadata.
        """
        dataset = SimpleDataset(image_paths)

        for image_path in image_paths:
            try:
                # Open and analyze image
                img = Image.open(image_path)
                width, height = img.size
                aspect_ratio = width / height if height > 0 else 0
                disk_size_bytes = os.path.getsize(image_path)
                disk_size_kb = round(disk_size_bytes / 1024, 2)
                extension = os.path.splitext(image_path)[1].lower().lstrip('.')

                # Add metadata for this image
                dataset.add_metadata(image_path, {
                    "width": width,
                    "height": height,
                    "aspect_ratio": round(aspect_ratio, 2),
                    "disk_size_kb": disk_size_kb,
                    "color_mode": img.mode,
                    "extension": extension,
                })
            except Exception as e:
                # Handle errors gracefully, store error info
                dataset.update_metadata_entry(
                    image_path,
                    error=str(e),
                    error_type=type(e).__name__
                )

        return dataset


class ImageExifHandler(HandlerPlugin):
    """
    Extracts EXIF metadata from images.

    Attempts to extract common EXIF fields including:
    - Camera make and model
    - DateTime taken
    - GPS coordinates
    - Exposure settings (f-number, ISO, shutter speed)
    - Focal length
    - Flash information

    For images without EXIF data, metadata is empty or contains only available fields.
    Errors during extraction are stored in the metadata.
    """

    def __init__(self) -> None:
        super().__init__(
            name="image_exif",
            description="Extracts EXIF metadata from images (camera, settings, GPS, date, etc.)"
        )

    def handle(self, image_paths: List[str]) -> SimpleDataset:
        """
        Process images and extract EXIF metadata.

        :param image_paths: List of image file paths to analyze.
        :return: Dataset with images and their extracted EXIF metadata.
        """
        dataset = SimpleDataset(image_paths)

        for image_path in image_paths:
            try:
                img = Image.open(image_path)
                exif_data = self._extract_exif(img)
                
                if exif_data:
                    dataset.add_metadata(image_path, exif_data)
                else:
                    # TODO: Debug why valid images may not be returning expected EXIF fields.
                    dataset.update_metadata_entry(image_path, exif_available=False)
            except Exception as e:
                # Handle errors gracefully, store error info
                dataset.update_metadata_entry(
                    image_path,
                    error=str(e),
                    error_type=type(e).__name__
                )

        return dataset

    def _extract_exif(self, img: Image.Image) -> Dict[str, Any]:
        """
        Extract human-readable EXIF data from a PIL Image.

        :param img: PIL Image object.
        :return: Dictionary of EXIF metadata, or empty dict if no EXIF data.
        """
        exif_data: Dict[str, Any] = {}

        try:
            exif = img.getexif()
            if exif is None or len(exif) == 0:
                return exif_data

            for tag_id, value in exif.items():
                tag_name = TAGS.get(tag_id, tag_id)

                if tag_name == "GPSInfo" and isinstance(value, dict):
                    gps_data = self._extract_gps_info(value)
                    exif_data.update(gps_data)
                    continue

                if isinstance(value, bytes):
                    try:
                        value = value.decode(errors="ignore")
                    except Exception:
                        value = str(value)

                # Normalize common EXIF names
                if tag_name in ("Make", "Model", "DateTime", "FNumber", "ExposureTime", "ISOSpeedRatings", "FocalLength", "Flash"):
                    pretty_name = {
                        "Make": "camera_make",
                        "Model": "camera_model",
                        "DateTime": "datetime",
                        "FNumber": "f_number",
                        "ExposureTime": "shutter_speed",
                        "ISOSpeedRatings": "iso",
                        "FocalLength": "focal_length",
                        "Flash": "flash",
                    }[tag_name]

                    if tag_name == "Flash":
                        flash_status = {0: "No flash", 1: "Flash fired"}.get(value, str(value))
                        exif_data[pretty_name] = flash_status
                    elif tag_name == "ExposureTime" and hasattr(value, "numerator") and hasattr(value, "denominator"):
                        exif_data[pretty_name] = f"1/{int(value.denominator / value.numerator)}" if value.numerator < value.denominator else str(value)
                    elif tag_name == "FNumber" and hasattr(value, "numerator") and hasattr(value, "denominator"):
                        exif_data[pretty_name] = f"f/{value.numerator / value.denominator:.1f}"
                    elif tag_name == "FocalLength" and hasattr(value, "numerator") and hasattr(value, "denominator"):
                        exif_data[pretty_name] = f"{value.numerator / value.denominator:.1f}mm"
                    else:
                        exif_data[pretty_name] = str(value)
                else:
                    # Keep other fields as readable text if useful
                    if isinstance(tag_name, str) and tag_name not in exif_data:
                        exif_data[tag_name.lower()] = str(value)

        except Exception:
            # EXIF reading can fail for various reasons, return empty
            return {}

        return exif_data

    def _extract_gps_info(self, gps_info: Dict[int, Any]) -> Dict[str, Any]:
        gps_data: Dict[str, Any] = {}

        def decode_coord(coord):
            try:
                degrees = float(coord[0])
                minutes = float(coord[1]) / 60.0
                seconds = float(coord[2]) / 3600.0
                return degrees + minutes + seconds
            except Exception:
                return None

        for key, value in gps_info.items():
            name = GPSTAGS.get(key, key)
            if name == "GPSLatitude":
                gps_data["gps_latitude"] = decode_coord(value)
            elif name == "GPSLongitude":
                gps_data["gps_longitude"] = decode_coord(value)
            elif name == "GPSLatitudeRef":
                gps_data["gps_latitude_ref"] = str(value)
            elif name == "GPSLongitudeRef":
                gps_data["gps_longitude_ref"] = str(value)
            else:
                gps_data[name.lower()] = str(value)

        return gps_data

    def _convert_gps_coord(self, gps_data: Any) -> Optional[float]:
        """
        Convert EXIF GPS coordinate (degrees, minutes, seconds) to decimal degrees.

        :param gps_data: EXIF GPS coordinate tuple.
        :return: Decimal degrees as float, or None if conversion fails.
        """
        try:
            if len(gps_data) >= 3:
                degrees = float(gps_data[0])
                minutes = float(gps_data[1]) / 60.0
                seconds = float(gps_data[2]) / 3600.0
                return degrees + minutes + seconds
        except (TypeError, ValueError, ZeroDivisionError):
            pass
        return None
