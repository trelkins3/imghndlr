import argparse
import os
import tempfile
import tkinter as tk
from contextlib import ExitStack
from typing import List, Optional

from imghndlr_sources import ImageSource, SourceType
from imghndlr_ui import ImgGalleryUI
from handler_plugin import ImageAnalyzerHandler, ImageExifHandler, SimpleDataset


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
            """,
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
        from imghndlr_sources import (
            DirectoryImageSource,
            FourChanImageSource,
            RedditImageSource,
        )

        if use_config:
            ImgHndlrOrchestrator.CONFIG_FILE = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "imghndlr.conf"
            )

        tmpdir = None
        with ExitStack() as stack:
            if source_type in (SourceType.FOURCHAN, SourceType.REDDIT):
                tmpdir = stack.enter_context(tempfile.TemporaryDirectory())
                print(f"Created temporary directory at: {tmpdir}")
                stack.callback(
                    lambda: print("Temporary directory is now being cleaned up...")
                )

            source: ImageSource
            match source_type:
                case SourceType.DIRECTORY:
                    source = DirectoryImageSource(directory_path=source_input)
                case SourceType.FOURCHAN:
                    assert tmpdir is not None
                    source = FourChanImageSource(
                        thread_url=source_input, target_dir=tmpdir
                    )
                case SourceType.REDDIT:
                    assert tmpdir is not None
                    source = RedditImageSource(
                        subreddit_name=source_input, target_dir=tmpdir
                    )
                case _:
                    raise AssertionError(
                        "Unsupported source type. This should never happen due to argparse choices."
                    )

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

            # Run visual analysis only for now. EXIF handler is disabled pending debug.
            print("Analyzing images...")
            analyzer = ImageAnalyzerHandler()
            dataset = analyzer.handle(image_paths)
            print(f"Visual analysis complete.")

            root: tk.Tk = tk.Tk()
            _ = ImgGalleryUI(
                root=root,
                image_paths=image_paths,
                source_directory=source_directory,
                config_file=ImgHndlrOrchestrator.CONFIG_FILE,
                dataset=dataset,
            )
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
        orchestrator.run(
            source_type=source_type,
            source_input=args.source_input,
            use_config=args.conf,
        )


if __name__ == "__main__":
    ImgHndlrOrchestrator.main()
