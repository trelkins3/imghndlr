import argparse
import os
import tempfile
import tkinter as tk
from contextlib import ExitStack
from typing import List, Optional

from imghndlr_plugin import BasicAnalyzerPlugin
from imghndlr_img_source import ImageSource, SourceType
from imghndlr_ui import ImgGalleryUI


class ImgHndlrOrchestrator:
    """
    Central manager for primary execution:
        * Handles terminal prompts
        * Manages temporary directories (if necessary)
        * Fetches image paths from source
        * Invokes analysis plugins
        * Launches the GUI
    """

    CONFIG_FILE: Optional[str] = None
    """ Path to the .conf file, if desired """

    # REVISIT: This seems like an anti-pattern...
    def __init__(self) -> None:
        pass

    def run(
        self,
        source_type: SourceType,
        source_input: str,
        use_config: bool = False,
        duplicates_only: bool = False,
        dedupe: bool = False,
        allow_webm: bool = False,
    ) -> None:
        """
        Perform setup, fetch image paths, invoke plugins, then spin up the UI.

        :param source_type: The resolved source type enum.
        :param source_input: The source-specific input string (ex. 4chan URL, subreddit name, etc.)
        :param use_config: Whether to enable persistent config file
        :param duplicates_only: Whether to display only images with similar matches.
        :param dedupe: Whether to calculate perceptual hashes and similarity counts.
        :param allow_webm: Whether to include WebM files in source results.
        """
        from imghndlr_img_source import DirectoryImageSource, FourChanImageSource

        # User wants the persistent .conf file, spin it up
        if use_config:
            ImgHndlrOrchestrator.CONFIG_FILE = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "imghndlr.conf"
            )

        tmpdir = None
        with ExitStack() as stack:
            if source_type == SourceType.FOURCHAN:
                tmpdir = stack.enter_context(tempfile.TemporaryDirectory())
                print(f"Created temporary directory at: {tmpdir}")
                stack.callback(
                    lambda: print("Temporary directory is now being cleaned up...")
                )

            if source_type not in SourceType.supported_types():
                raise ValueError("The requested source type is not currently supported.")

            source: ImageSource
            match source_type:
                case SourceType.DIRECTORY:
                    source = DirectoryImageSource(
                        directory_path=source_input,
                        allow_webm=allow_webm,
                    )
                case SourceType.FOURCHAN:
                    # thanks mypy
                    assert tmpdir is not None
                    # REVISIT: Don't like how this is getting broken up, figure out why it's happening + fix it
                    source = FourChanImageSource(
                        thread_url=source_input,
                        target_dir=tmpdir,
                        allow_webm=allow_webm,
                    )
                case _:
                    raise AssertionError(
                        "Unsupported SourceType. If you got here, argparse screwed up!"
                    )

            try:
                # Fetch image paths from the source object; we'll propagate this to the plugins and the UI
                image_paths: List[str] = source.get_images()
            except Exception as e:
                print(f"Error handling image source operations: {e}")
                raise

            if not image_paths:
                print("No images were found or downloaded.")
                raise

            # REVISIT: What is this directory for...? Only used w/ SourceType.DIRECTORY
            source_directory: Optional[str] = None
            if isinstance(source, DirectoryImageSource):
                source_directory = source.directory_path

            # REVISIT: This code needs to be more robust and dynamically invoke the desired plugins
            # Run basic analysis only for now. EXIF extraction plugin is disabled pending debug.
            print("Analyzing images...")
            analyzer = BasicAnalyzerPlugin()
            dataset = analyzer.handle(image_paths, dedupe=dedupe)
            print("Image analysis complete.")

            if duplicates_only:
                image_paths = [
                    image_path
                    for image_path in image_paths
                    if dataset.get_metadata_for_image(image_path).get(
                        "similar_image_count", 0
                    )
                    > 0
                ]
                print(f"Showing {len(image_paths)} images with similar matches.")

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
            print("Temporary directory cleanup complete. Goodbye!")

    @classmethod
    def main(cls) -> None:
        """
        Parses CLI arguments and starts the orchestrator (main program execution).
        """
        parser = argparse.ArgumentParser(
            description="Fetch and browse images from various sources.",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            # REVISIT: If we add Reddit support back, this needs an example string
            epilog="""Examples:
  python imghndlr.py --source 4chan "https://boards.4channel.org/wg/thread/<id>"
  python imghndlr.py --source dir "/path/to/images"
            """,
        )
        parser.add_argument(
            "--conf",
            action="store_true",
            help="Enable saving/loading target directory path",
        )
        parser.add_argument(
            "--dedupe",
            action="store_true",
            help="Calculate perceptual hashes and find similar images",
        )
        parser.add_argument(
            "--allow_webm",
            action="store_true",
            help="Include WebM files even if the UI cannot display them",
        )
        parser.add_argument(
            "--duplicates_only",
            action="store_true",
            help="Show only similar images; requires --dedupe",
        )
        parser.add_argument(
            "--source",
            choices=[s.value for s in SourceType.supported_types()],
            required=True,
            # REVISIT: If we add Reddit support back, this needs to mention it
            help="Image source type: '4chan' (4chan thread) or 'dir' (local directory).",
        )
        parser.add_argument(
            "source_input",
            # REVISIT: If we add Reddit support back, this needs to mention it
            help="Source-specific input: Full 4chan thread URL or local directory path.",
        )
        parsed_args = parser.parse_args()
        if parsed_args.duplicates_only and not parsed_args.dedupe:
            parser.error("--duplicates_only requires --dedupe")
        source_type = SourceType(parsed_args.source)

        cls().run(
            source_type=source_type,
            source_input=parsed_args.source_input,
            use_config=parsed_args.conf,
            duplicates_only=parsed_args.duplicates_only,
            dedupe=parsed_args.dedupe,
            allow_webm=parsed_args.allow_webm,
        )


if __name__ == "__main__":
    ImgHndlrOrchestrator.main()
