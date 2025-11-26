# AI Video Detection API

Lightweight Flask API that wraps the D3 detector for HTTP access. Designed to be called by n8n workflows for automated video analysis.

## Quick Start

### Installation

```bash
# Install dependencies (run from project root)
pip install flask flask-cors

# All other dependencies are already in ../requirements.txt
```

### Run the API

```bash
# From the api/ directory
python detection_api.py

# Or from project root
python api/detection_api.py

# Custom host/port
python api/detection_api.py --host 0.0.0.0 --port 8000

# With debug mode
python api/detection_api.py --debug
```

The API will start on `http://localhost:8000` by default.

## Endpoints

### `GET /health`

Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "detector": "D3-CLIP-16-cosine",
  "version": "1.0.0"
}
```

**Example:**
```bash
curl http://localhost:8000/health
```

### `POST /analyze`

Analyze a single video for AI generation.

**Request:**
```json
{
  "video_url": "https://youtube.com/watch?v=dQw4w9WgXcQ",
  "max_frames": 100
}
```

**Response:**
```json
{
  "verdict": "LIKELY AI-GENERATED",
  "confidence": "HIGH",
  "ai_probability": 0.87,
  "frame_count": 100,
  "detailed_analysis": {
    "method": "D3 (Detection by Difference of Differences)",
    "detection_score": 0.0245,
    "avg_temporal_change": -0.0012,
    "temporal_inconsistency": 0.0245,
    "threshold": 0.5,
    "description": "D3 analyzes second-order temporal features..."
  },
  "weights": {"D3": 1.0}
}
```

**Example:**
```bash
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"video_url":"https://youtube.com/watch?v=dQw4w9WgXcQ","max_frames":100}'
```

**Error Response:**
```json
{
  "error": "Failed to download video. It may be private, deleted, or geo-restricted.",
  "ai_probability": 0.5
}
```

### `POST /analyze/batch`

Analyze multiple videos in a single request.

**Request:**
```json
{
  "videos": [
    {"url": "https://youtube.com/watch?v=abc123", "id": "video1"},
    {"url": "https://youtube.com/watch?v=def456", "id": "video2"}
  ],
  "max_frames": 100
}
```

**Response:**
```json
{
  "results": [
    {
      "id": "video1",
      "verdict": "LIKELY AI-GENERATED",
      "ai_probability": 0.87,
      ...
    },
    {
      "id": "video2",
      "verdict": "LIKELY REAL",
      "ai_probability": 0.15,
      ...
    }
  ]
}
```

## Integration with n8n

### Step 1: Start the API

```bash
python api/detection_api.py
```

Keep this running in a terminal or as a background service.

### Step 2: Call from n8n HTTP Request Node

**Node Configuration:**
- Method: `POST`
- URL: `http://localhost:8000/analyze`
- Body:
```json
{
  "video_url": "{{ $json.video_url }}"
}
```

**Response:**
The n8n node will receive the JSON response which can be used in subsequent nodes.

## Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `verdict` | string | Classification: "LIKELY AI-GENERATED", "POSSIBLY AI-GENERATED", "UNCERTAIN", or "LIKELY REAL" |
| `confidence` | string | "HIGH", "MEDIUM", or "LOW" |
| `ai_probability` | float | 0.0 to 1.0 - probability the video is AI-generated |
| `frame_count` | int | Number of frames analyzed |
| `detailed_analysis.detection_score` | float | Raw D3 detection score (std of 2nd-order differences) |
| `detailed_analysis.method` | string | Detection method used |
| `error` | string | Error message (only present if analysis failed) |

## Probability Interpretation

- **>0.7** (70%): Likely AI-generated → Add to blocklist
- **0.5-0.7** (50-70%): Possibly AI-generated → Add to warnlist
- **<0.5** (50%): Likely real or insufficient evidence

## Performance

- **Analysis time:** ~30-60 seconds per video (depending on length and frame count)
- **Max video length:** 2 minutes (120 seconds)
- **Frame sampling:** Up to 100 frames (adjustable)
- **Temp storage:** Automatically cleaned up after each request

## Troubleshooting

### API won't start

**Error:** "ModuleNotFoundError: No module named 'ai_video_detector'"

**Solution:**
```bash
# Make sure you're running from the correct directory
cd /path/to/AiNoiser
python api/detection_api.py
```

### Video download fails

**Error:** "Failed to download video"

**Possible causes:**
- Video is private or deleted
- Video is geo-restricted
- YouTube is blocking yt-dlp
- No internet connection

**Solution:**
- Test with a known public video
- Update yt-dlp: `pip install --upgrade yt-dlp`
- Check internet connection

### Analysis is slow

**Solutions:**
- Reduce `max_frames` (default: 100, try 50)
- Videos are limited to 2 minutes automatically
- Consider running on GPU if available

### Port already in use

**Error:** "Address already in use"

**Solution:**
```bash
# Use a different port
python api/detection_api.py --port 8001

# Or find and kill the process using port 8000
# Linux/Mac:
lsof -ti:8000 | xargs kill -9

# Windows:
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

## Testing

### Test health endpoint:
```bash
curl http://localhost:8000/health
```

### Test with a real video:
```bash
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "video_url": "https://youtube.com/watch?v=dQw4w9WgXcQ",
    "max_frames": 50
  }'
```

### Test error handling:
```bash
# Invalid URL
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"video_url": "invalid"}'

# Missing video_url
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{}'
```

## Running in Production

### Using systemd (Linux)

Create `/etc/systemd/system/ai-detection-api.service`:

```ini
[Unit]
Description=AI Video Detection API
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/AiNoiser
ExecStart=/usr/bin/python3 /path/to/AiNoiser/api/detection_api.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable ai-detection-api
sudo systemctl start ai-detection-api
sudo systemctl status ai-detection-api
```

### Using Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
COPY api/requirements_api.txt api/
RUN pip install -r requirements.txt -r api/requirements_api.txt

COPY . .

EXPOSE 8000
CMD ["python", "api/detection_api.py", "--host", "0.0.0.0"]
```

```bash
docker build -t ai-detection-api .
docker run -p 8000:8000 ai-detection-api
```

## Security Considerations

- **Local use only:** Do NOT expose this API to the public internet without authentication
- **Rate limiting:** Consider adding rate limiting for production use
- **Input validation:** The API validates video URLs but additional checks may be needed
- **Temp file cleanup:** Temporary files are automatically cleaned up
- **CORS:** Currently allows all origins - restrict in production if needed

## License

Same as parent project (see ../LICENSE)
