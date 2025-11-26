"""
AI Video Detection API
Lightweight Flask API that wraps the D3 detector for HTTP access.
Used by n8n workflow to analyze videos from GitHub issue submissions.
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import sys
import os
import tempfile
import traceback

# Add parent directory to path to import from root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_video_detector import AIVideoDetector
from youtube_downloader import download_youtube_video

app = Flask(__name__)
CORS(app)  # Allow n8n to call this API

# Initialize detector once at startup
print("Initializing D3 detector...")
detector = AIVideoDetector(encoder='CLIP-16', loss_type='cos')
print("Detector ready!")


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "detector": "D3-CLIP-16-cosine",
        "version": "1.0.0"
    })


@app.route('/analyze', methods=['POST'])
def analyze_video():
    """
    Analyze video for AI generation

    Request body:
    {
        "video_url": "https://youtube.com/watch?v=...",
        "max_frames": 100  (optional, default: 100)
    }

    Response:
    {
        "verdict": "LIKELY AI-GENERATED" | "POSSIBLY AI-GENERATED" | "UNCERTAIN" | "LIKELY REAL",
        "confidence": "HIGH" | "MEDIUM" | "LOW",
        "ai_probability": 0.87,
        "frame_count": 100,
        "detailed_analysis": {...},
        "error": "..." (only if error occurred)
    }
    """
    try:
        # Parse request
        data = request.json
        if not data:
            return jsonify({"error": "Request body must be JSON"}), 400

        video_url = data.get('video_url')
        if not video_url:
            return jsonify({"error": "video_url is required"}), 400

        # Convert max_frames to int (n8n might send it as string)
        max_frames = int(data.get('max_frames', 100))

        print(f"Analyzing video: {video_url}")
        print(f"Max frames: {max_frames}")

        # Create temporary directory for video download
        temp_dir = tempfile.mkdtemp()
        video_path = None

        try:
            print(f"Downloading video to {temp_dir}...")

            try:
                # Download video (automatically downloads 10s snippet for long videos)
                # Note: max_duration=120 is DEPRECATED but kept for backward compatibility
                video_path = download_youtube_video(
                    video_url,
                    output_path=temp_dir,
                    max_duration=120  # DEPRECATED: Kept for backward compatibility
                )

                if not video_path or not os.path.isfile(video_path):
                    return jsonify({
                        "error": "Failed to download video. It may be private, deleted, or geo-restricted.",
                        "ai_probability": 0.5
                    }), 400

                print(f"Video downloaded: {video_path}")

            except Exception as e:
                print(f"Download error: {str(e)}")
                return jsonify({
                    "error": f"Video download failed: {str(e)}",
                    "ai_probability": 0.5
                }), 400

            # Run D3 detection
            print("Running D3 detection...")
            results = detector.detect(
                video_path,
                max_frames=max_frames,
                visualize=False  # No visualization for API
            )

            print(f"Analysis complete: {results['verdict']} ({results['ai_probability']:.2%})")

            return jsonify(results), 200

        finally:
            # Manual cleanup with Windows-friendly error handling
            if video_path and os.path.isfile(video_path):
                try:
                    os.remove(video_path)
                except (PermissionError, OSError) as e:
                    print(f"Warning: Could not delete {video_path}: {e}")

            # Try to remove temp directory
            try:
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception as e:
                print(f"Warning: Could not delete temp directory {temp_dir}: {e}")

    except Exception as e:
        print(f"ERROR: {str(e)}")
        traceback.print_exc()
        return jsonify({
            "error": f"Analysis failed: {str(e)}",
            "ai_probability": 0.5
        }), 500


@app.route('/analyze/batch', methods=['POST'])
def analyze_batch():
    """
    Analyze multiple videos in batch

    Request body:
    {
        "videos": [
            {"url": "https://...", "id": "video1"},
            {"url": "https://...", "id": "video2"}
        ],
        "max_frames": 100
    }

    Response:
    {
        "results": [
            {"id": "video1", "verdict": "...", ...},
            {"id": "video2", "verdict": "...", ...}
        ]
    }
    """
    try:
        data = request.json
        videos = data.get('videos', [])
        # Convert max_frames to int (n8n might send it as string)
        max_frames = int(data.get('max_frames', 100))

        if not videos:
            return jsonify({"error": "videos array is required"}), 400

        results = []
        for video_data in videos:
            video_url = video_data.get('url')
            video_id = video_data.get('id', video_url)

            # Analyze single video
            response = analyze_single_video_internal(video_url, max_frames)
            response['id'] = video_id
            results.append(response)

        return jsonify({"results": results}), 200

    except Exception as e:
        print(f"ERROR: {str(e)}")
        traceback.print_exc()
        return jsonify({"error": f"Batch analysis failed: {str(e)}"}), 500


def analyze_single_video_internal(video_url: str, max_frames: int) -> dict:
    """Internal helper for batch processing"""
    temp_dir = tempfile.mkdtemp()
    video_path = None

    try:
        # Download video (automatically downloads 10s snippet for long videos)
        video_path = download_youtube_video(
            video_url,
            output_path=temp_dir,
            max_duration=120  # DEPRECATED: Kept for backward compatibility
        )

        if not video_path or not os.path.isfile(video_path):
            return {
                "error": "Failed to download video",
                "ai_probability": 0.5
            }

        results = detector.detect(video_path, max_frames=max_frames, visualize=False)
        return results

    except Exception as e:
        return {
            "error": str(e),
            "ai_probability": 0.5
        }

    finally:
        # Manual cleanup with Windows-friendly error handling
        if video_path and os.path.isfile(video_path):
            try:
                os.remove(video_path)
            except (PermissionError, OSError):
                pass  # Ignore cleanup errors in batch mode

        try:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass  # Ignore cleanup errors in batch mode


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='AI Video Detection API')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--port', type=int, default=8000, help='Port to bind to')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')

    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"AI Video Detection API")
    print(f"{'='*60}")
    print(f"Listening on: http://{args.host}:{args.port}")
    print(f"Health check: http://{args.host}:{args.port}/health")
    print(f"Analyze endpoint: POST http://{args.host}:{args.port}/analyze")
    print(f"{'='*60}\n")

    app.run(
        host=args.host,
        port=args.port,
        debug=args.debug
    )
