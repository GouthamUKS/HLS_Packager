#!/usr/bin/env python3
"""
HLS Adaptive Bitrate Video Packager

Transcodes video into adaptive bitrate variants using FFmpeg,
segments them into 6-second chunks, and generates HLS manifests.

Author: Goutham Soratoor
GitHub: https://github.com/GouthamUKS
"""

import argparse
import logging
import subprocess
import os
import sys
from pathlib import Path
from typing import List, Tuple, Optional


logger = logging.getLogger(__name__)


class ABRVariant:
    """Defines an adaptive bitrate variant configuration."""

    def __init__(
        self, name: str, resolution: Tuple[int, int], bitrate: int, profile: str
    ):
        self.name = name
        self.resolution = resolution
        self.bitrate = bitrate
        self.profile = profile

    @property
    def scale_filter(self) -> str:
        """Return FFmpeg scale filter string."""
        width, height = self.resolution
        return f"scale={width}:{height}"

    @property
    def codec_params(self) -> str:
        """Return FFmpeg codec parameters."""
        return f"-c:v libx264 -profile:v {self.profile} -b:v {self.bitrate}k"


def setup_logging(level: int = logging.INFO) -> None:
    """Configure logging for the packager."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def check_ffmpeg_available() -> bool:
    """Verify FFmpeg is available in system PATH."""
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            check=True,
            timeout=5,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def validate_input_file(input_path: str) -> Path:
    """Validate that input file exists and is readable."""
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    if not path.is_file():
        raise ValueError(f"Input path is not a file: {input_path}")
    return path


def get_video_duration(input_file: str) -> float:
    """Get video duration in seconds using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1:novalue=1",
                input_file,
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        return float(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError, subprocess.TimeoutExpired):
        logger.warning(f"Could not determine duration for {input_file}")
        return 0.0


def transcode_variant(
    input_file: str,
    output_dir: str,
    variant: ABRVariant,
    segment_duration: int = 6,
) -> bool:
    """Transcode video to a single ABR variant with HLS segmentation."""
    variant_dir = Path(output_dir) / variant.name
    variant_dir.mkdir(parents=True, exist_ok=True)

    playlist_path = variant_dir / f"{variant.name}.m3u8"
    segment_pattern = str(variant_dir / "segment_%03d.ts")

    cmd = [
        "ffmpeg",
        "-i",
        input_file,
        "-vf",
        variant.scale_filter,
        "-c:a",
        "aac",
        "-b:a",
        "128k",
    ]

    cmd.extend(variant.codec_params.split())
    cmd.extend(
        [
            "-force_key_frames",
            f"expr:gte(t,n_forced*{segment_duration})",
            "-hls_time",
            str(segment_duration),
            "-hls_list_size",
            "0",
            "-hls_segment_type",
            "mpegts",
            str(playlist_path),
        ]
    )

    try:
        logger.info(f"Transcoding {variant.name} variant...")
        subprocess.run(cmd, check=True, capture_output=True, timeout=3600)
        logger.info(f"Successfully transcoded {variant.name}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Transcoding failed for {variant.name}: {e.stderr.decode()}")
        return False
    except subprocess.TimeoutExpired:
        logger.error(f"Transcode timeout for {variant.name}")
        return False


def generate_master_playlist(
    output_dir: str, variants: List[ABRVariant]
) -> bool:
    """Generate master HLS playlist with variant information."""
    master_path = Path(output_dir) / "master.m3u8"

    lines = ["#EXTM3U", "#EXT-X-VERSION:3"]

    for variant in variants:
        width, height = variant.resolution
        lines.append(
            f'#EXT-X-STREAM-INF:BANDWIDTH={variant.bitrate * 1000},'
            f'RESOLUTION={width}x{height},CODECS="avc1.640028,mp4a.40.2"'
        )
        lines.append(f"{variant.name}/{variant.name}.m3u8")

    try:
        with open(master_path, "w") as f:
            f.write("\n".join(lines) + "\n")
        logger.info(f"Master playlist written to {master_path}")
        return True
    except IOError as e:
        logger.error(f"Failed to write master playlist: {e}")
        return False


def package_video(input_file: str, output_dir: str) -> bool:
    """Main packaging workflow."""
    logger.info(f"Starting HLS packaging: {input_file} -> {output_dir}")

    input_path = validate_input_file(input_file)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    variants = [
        ABRVariant("720p", (1280, 720), 2500, "high"),
        ABRVariant("480p", (854, 480), 1200, "main"),
        ABRVariant("360p", (640, 360), 600, "baseline"),
    ]

    logger.info(f"Video duration: {get_video_duration(str(input_path))} seconds")

    success = True
    for variant in variants:
        if not transcode_variant(str(input_path), str(output_path), variant):
            success = False

    if not generate_master_playlist(str(output_path), variants):
        success = False

    if success:
        logger.info(f"HLS packaging complete: {output_path}")
    else:
        logger.error("HLS packaging completed with errors")

    return success


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Transcode video to adaptive bitrate HLS with keyframe-aligned segmentation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --input video.mp4 --output ./output
  %(prog)s -i movie.mov -o ./hls_output
        """,
    )

    parser.add_argument(
        "--input",
        "-i",
        required=True,
        help="Input video file path (MP4, MOV, MKV, etc.)",
    )
    parser.add_argument(
        "--output",
        "-o",
        required=True,
        help="Output directory for HLS files",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    setup_logging(level=logging.DEBUG if args.verbose else logging.INFO)

    if not check_ffmpeg_available():
        logger.error("FFmpeg not found. Please install FFmpeg and add to PATH.")
        return 1

    try:
        success = package_video(args.input, args.output)
        return 0 if success else 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
