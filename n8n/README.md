# n8n Workflow for AiSList Integration

This directory contains the n8n workflow that automates AI video detection for the AiSList GitHub repository.

## Overview

The workflow receives GitHub webhook events when new issues are created, analyzes the submitted video using our D3 detector, and automatically creates pull requests to add channels to the blocklist or warnlist.

## Architecture

```
GitHub Issue Created
       ↓
GitHub Webhook
       ↓
n8n Webhook Node (receives payload)
       ↓
n8n Filter Node (only process AI channel reports)
       ↓
n8n Code Node (parse issue data)
       ↓
n8n HTTP Request → Local AI Detection API (localhost:8000)
       ↓
n8n receives analysis results
       ↓
n8n GitHub Node: Post analysis comment
       ↓
n8n Code Node: Generate file changes
       ↓
n8n GitHub Node: Create PR with blocklist update
```

## Prerequisites

1. **n8n installed and running locally**
   ```bash
   npm install -g n8n
   n8n start
   ```

2. **AI Detection API running**
   ```bash
   cd /path/to/AiNoiser
   python api/detection_api.py
   ```

3. **GitHub OAuth credentials** (for posting comments and creating PRs)

4. **Maintainer access** to the Override92/AiSList repository

## Setup Instructions

### Step 1: Install n8n (if not already installed)

```bash
npm install -g n8n

# Start n8n
n8n start

# n8n will run on http://localhost:5678
```

### Step 2: Import the Workflow

1. Open n8n: http://localhost:5678
2. Click "Workflows" → "Add Workflow"
3. Click "..." menu → "Import from File"
4. Select `n8n/aislist_workflow.json`
5. Save the workflow

### Step 3: Configure GitHub Credentials

#### Create GitHub OAuth App

1. Go to: https://github.com/settings/developers
2. Click "New OAuth App"
3. Fill in:
   - **Application name:** n8n AiSList Integration
   - **Homepage URL:** http://localhost:5678
   - **Authorization callback URL:** http://localhost:5678/rest/oauth2-credential/callback
4. Click "Register application"
5. Copy the **Client ID** and **Client Secret**

#### Add Credentials to n8n

1. In n8n, go to **Credentials** → **Add Credential**
2. Search for "GitHub OAuth2 API"
3. Enter:
   - **Client ID:** (from OAuth app)
   - **Client Secret:** (from OAuth app)
4. Click "Connect my account"
5. Authorize the OAuth app
6. Save the credential

### Step 4: Configure Webhook Secret

1. Generate a webhook secret:
   ```bash
   openssl rand -hex 32
   ```

2. In n8n workflow, edit the **Webhook** node:
   - Path: `/webhook/github-issues`
   - Authentication: `Header Auth`
   - Header Name: `X-Hub-Signature-256`
   - Header Value: `{{ $value }}` (leave as default)
   - Enable **HMAC Authentication**
   - Secret: (paste your generated secret)

3. Save the secret - you'll need it for GitHub webhook configuration

### Step 5: Get n8n Webhook URL

1. In n8n, open the workflow
2. Click on the **Webhook** node
3. Copy the **Production URL** (will look like: `http://localhost:5678/webhook/XXXXX`)
4. If running locally, you'll need to expose this via tunneling (see below)

### Step 6: Expose n8n Locally (if needed)

Since n8n is running locally, GitHub can't reach it. Options:

#### Option A: ngrok (Recommended for testing)

```bash
# Install ngrok
# https://ngrok.com/download

# Expose n8n
ngrok http 5678

# Copy the HTTPS URL (e.g., https://abc123.ngrok.io)
# Your webhook URL will be: https://abc123.ngrok.io/webhook/github-issues
```

#### Option B: n8n Cloud

```bash
# Use n8n cloud hosting (free tier available)
# https://n8n.io/cloud
```

#### Option C: Cloudflare Tunnel

```bash
cloudflared tunnel --url http://localhost:5678
```

### Step 7: Configure GitHub Webhook

1. Go to: https://github.com/Override92/AiSList/settings/hooks
2. Click "Add webhook"
3. Fill in:
   - **Payload URL:** Your n8n webhook URL (e.g., `https://abc123.ngrok.io/webhook/github-issues`)
   - **Content type:** `application/json`
   - **Secret:** (paste the secret you generated in Step 4)
   - **Events:** Select "Let me select individual events"
     - ✓ Issues
     - ✓ Issue comments (optional)
   - **Active:** ✓ Checked
4. Click "Add webhook"
5. Test by clicking "Recent Deliveries" → "Redeliver"

## Workflow Nodes

### Node 1: Webhook Trigger
- **Type:** Webhook
- **Path:** `/webhook/github-issues`
- **Method:** POST
- **Authentication:** HMAC (GitHub signature verification)

### Node 2: Filter Issues
- **Type:** IF
- **Condition 1:** `{{ $json.action }}` equals `opened`
- **Condition 2:** `{{ $json.issue.title }}` contains `Blocklist` OR `Warnlist`

### Node 3: Parse Issue Data
- **Type:** Code (JavaScript)
```javascript
const body = $json.issue.body;
const channelMatch = body.match(/@[\w-]+/);
const videoMatch = body.match(/youtube\.com\/watch\?v=([\w-]+)/);

return {
  issue_number: $json.issue.number,
  issue_url: $json.issue.html_url,
  channel_handle: channelMatch ? channelMatch[0] : null,
  video_url: videoMatch ? `https://youtube.com/watch?v=${videoMatch[1]}` : null,
  confidence: body.toLowerCase().includes('high') ? 'high' : 'medium'
};
```

### Node 4: Call AI Detection API
- **Type:** HTTP Request
- **Method:** POST
- **URL:** `http://localhost:8000/analyze`
- **Body:**
```json
{
  "video_url": "{{ $('Parse Issue Data').item.json.video_url }}"
}
```

### Node 5: Post Analysis Comment
- **Type:** GitHub
- **Resource:** Issue
- **Operation:** Create Comment
- **Owner:** Override92
- **Repository:** AiSList
- **Issue Number:** `{{ $('Parse Issue Data').item.json.issue_number }}`
- **Body:** (See template in workflow JSON)

### Node 6: Generate File Content
- **Type:** Code (JavaScript)
```javascript
const channelHandle = $('Parse Issue Data').item.json.channel_handle;
const aiProb = $json.ai_probability;

if (aiProb > 0.7) {
  return {
    target_file: 'AiSList/aislist_blocklist.txt',
    list_type: 'blocklist',
    channel_handle: channelHandle,
    branch_name: `ai-detection/add-${channelHandle.replace('@', '')}`,
    pr_title: `Add ${channelHandle} to blocklist`,
    pr_body: `## Automated Addition\n\n**Channel:** ${channelHandle}\n**AI Probability:** ${Math.round(aiProb * 100)}%`
  };
} else if (aiProb > 0.5) {
  return {
    target_file: 'AiSList/aislist_warnlist.txt',
    list_type: 'warnlist',
    channel_handle: channelHandle,
    branch_name: `ai-detection/add-${channelHandle.replace('@', '')}`,
    pr_title: `Add ${channelHandle} to warnlist`,
    pr_body: `## Automated Addition\n\n**Channel:** ${channelHandle}\n**AI Probability:** ${Math.round(aiProb * 100)}%`
  };
} else {
  return { skip: true };
}
```

### Node 7: Create Pull Request
- **Type:** GitHub
- **Resource:** Pull Request
- **Operation:** Create
- **Owner:** Override92
- **Repository:** AiSList
- **Base:** main
- **Head:** `{{ $json.branch_name }}`
- **Title:** `{{ $json.pr_title }}`
- **Body:** `{{ $json.pr_body }}`

## Testing the Workflow

### 1. Test Webhook Reception

```bash
# Simulate GitHub webhook
curl -X POST http://localhost:5678/webhook/github-issues \
  -H "Content-Type: application/json" \
  -H "X-Hub-Signature-256: sha256=test" \
  -d '{
    "action": "opened",
    "issue": {
      "number": 999,
      "html_url": "https://github.com/Override92/AiSList/issues/999",
      "title": "Add @TestChannel to Blocklist",
      "body": "Channel: @TestChannel\nReason: AI voice\nEvidence: https://youtube.com/watch?v=dQw4w9WgXcQ\nConfidence: High"
    }
  }'
```

### 2. Test with Real Issue

1. Go to: https://github.com/Override92/AiSList/issues
2. Click "New issue"
3. Use the template:
   ```
   Title: Add @TestChannel to Blocklist
   Body:
   - Channel: @TestChannel
   - Reason: AI-generated voice
   - Evidence: https://youtube.com/watch?v=dQw4w9WgXcQ
   - Confidence: High
   ```
4. Submit the issue
5. Check n8n execution log to see the workflow run

### 3. Monitor Execution

1. In n8n, go to **Executions**
2. See the latest run
3. Click to view details
4. Check each node's output
5. Verify comment was posted on GitHub
6. Verify PR was created

## Troubleshooting

### Webhook not triggering

**Check:**
- Is n8n running? (`http://localhost:5678`)
- Is the webhook URL correct in GitHub?
- Is ngrok/tunnel running?
- Check GitHub webhook "Recent Deliveries" for errors

**Solution:**
```bash
# Restart n8n
n8n start

# Restart ngrok
ngrok http 5678

# Update webhook URL in GitHub with new ngrok URL
```

### AI API not responding

**Check:**
- Is the API running? (`http://localhost:8000/health`)
- Can n8n reach localhost:8000?

**Solution:**
```bash
# Start the API
cd /path/to/AiNoiser
python api/detection_api.py

# Test it
curl http://localhost:8000/health
```

### GitHub credentials not working

**Check:**
- Are the OAuth credentials correct?
- Did you authorize the app?
- Do you have the right permissions?

**Solution:**
1. Re-create GitHub OAuth app
2. Update credentials in n8n
3. Re-authorize

### PR creation fails

**Check:**
- Do you have write access to the repo?
- Is the branch name valid?
- Does the file exist?

**Solution:**
- Verify maintainer access
- Check branch naming in workflow
- Test manually creating a PR

## Monitoring

### View Execution History

1. n8n UI → Executions
2. Filter by workflow name
3. See success/failure rate
4. Click to view detailed logs

### GitHub Webhook Deliveries

1. GitHub repo → Settings → Webhooks
2. Click on the webhook
3. "Recent Deliveries" tab
4. See all webhook events sent

## Maintenance

### Update Workflow

1. Make changes in n8n UI
2. Save the workflow
3. Export: "..." → "Export"
4. Replace `aislist_workflow.json`
5. Commit to git

### Update AI Thresholds

Edit Node 6 (Generate File Content) to change:
- Blocklist threshold (currently 0.7 = 70%)
- Warnlist threshold (currently 0.5 = 50%)

### Disable Automation

1. In n8n, set workflow to "Inactive"
2. Or delete the GitHub webhook

## Production Deployment

For production use:

1. **Use n8n Cloud** or self-hosted n8n on a server
2. **Add rate limiting** to protect against spam
3. **Set up monitoring** for failed executions
4. **Add alerting** for errors (email, Slack, etc.)
5. **Backup workflow** regularly
6. **Document** any customizations

## Security

- **Webhook secret:** Keep this secure, rotate periodically
- **OAuth credentials:** Store securely, don't commit to git
- **API endpoint:** localhost only, don't expose publicly
- **PR approval:** Always review PRs before merging

## Support

For issues or questions:
1. Check n8n execution logs
2. Check API logs (`python api/detection_api.py`)
3. Test each component individually
4. Review GitHub webhook deliveries

## License

Same as parent project (see ../LICENSE)
