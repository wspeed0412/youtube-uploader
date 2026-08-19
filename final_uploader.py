import os
import io
import pickle
import requests
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

# --- DISCORD WEBHOOK CONFIG ---
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL")

def send_discord_notification(status, uploaded_videos=None, error_message=None):
    if not DISCORD_WEBHOOK:
        print("No Discord Webhook URL provided. Skipping notification.")
        return

    if status == "SUCCESS":
        title = "✅ YouTube Daily Upload - Success"
        color = 5763719  # Green
        if uploaded_videos:
            description = "**Uploaded Videos:**\n" + "\n".join(
                [f"• [{v['name']}](https://youtu.be/{v['id']})" for v in uploaded_videos]
            )
        else:
            description = "No new videos found in the Google Drive queue."
    else:
        title = "❌ YouTube Daily Upload - Failed"
        color = 15548997  # Red
        description = f"**Error Logs:**\n```\n{str(error_message)[:1000]}\n```"

    payload = {
        "embeds": [{
            "title": title,
            "description": description,
            "color": color,
            "footer": {"text": "Automated YouTube Uploader • GitHub Actions"}
        }]
    }

    try:
        requests.post(DISCORD_WEBHOOK, json=payload)
    except Exception as e:
        print(f"Failed to send Discord webhook: {e}")

# --- MAIN UPLOAD LOGIC ---
def main():
    # Folder IDs
    DRIVE_FOLDER_ID = "1Yxg1noKszBMwEEFTxw8NVw_dYrtpWEvo"
    DONE_FOLDER_ID = "18oZV5nP7OrgComaLZ8CzZqdm6iIOHmpr"

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    TOKEN_FILE = os.path.join(BASE_DIR, "Reddit Watch", "token.pickle")
    TEMP_DIR = os.path.join(BASE_DIR, "temp_videos")

    if not os.path.exists(TEMP_DIR):
        os.makedirs(TEMP_DIR)

    uploaded_videos_summary = []

    try:
        credentials = None
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, 'rb') as token:
                credentials = pickle.load(token)

        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())

        drive_service = build('drive', 'v3', credentials=credentials)
        youtube_service = build('youtube', 'v3', credentials=credentials)

        # Fetch up to 2 videos from Drive
        query = f"'{DRIVE_FOLDER_ID}' in parents and mimeType contains 'video/' and trashed = false"
        results = drive_service.files().list(q=query, pageSize=2, fields="files(id, name)").execute()
        items = results.get('files', [])

        if not items:
            print("No videos found in Google Drive queue.")
            send_discord_notification("SUCCESS", uploaded_videos=[])
            return

        for file in items:
            file_id = file['id']
            file_name = file['name']
            local_path = os.path.join(TEMP_DIR, file_name)

            print(f"\nDownloading from Drive: {file_name}")
            request = drive_service.files().get_media(fileId=file_id)
            with io.FileIO(local_path, 'wb') as fh:
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()

            clean_title = os.path.splitext(file_name)[0][:100]
            body = {
                'snippet': {
                    'title': clean_title,
                    'description': 'Automated Daily Upload',
                    'tags': ['shorts', 'viral']
                },
                'status': {'privacyStatus': 'public'}
            }

            print(f"Uploading to YouTube: {clean_title}")
            media = MediaFileUpload(local_path, chunksize=-1, resumable=True)
            response = youtube_service.videos().insert(part=','.join(body.keys()), body=body, media_body=media).execute()
            video_id = response['id']
            print(f"Successfully uploaded! Video ID: {video_id}")

            uploaded_videos_summary.append({
                'name': clean_title,
                'id': video_id
            })

            # Move file in Drive to Uploaded_Done
            drive_service.files().update(
                fileId=file_id,
                addParents=DONE_FOLDER_ID,
                removeParents=DRIVE_FOLDER_ID,
                fields='id, parents'
            ).execute()

            # Clean up local file
            if os.path.exists(local_path):
                os.remove(local_path)

        # Send success Discord notification
        send_discord_notification("SUCCESS", uploaded_videos=uploaded_videos_summary)

    except Exception as e:
        print(f"An error occurred: {e}")
        send_discord_notification("FAILURE", error_message=str(e))
        raise e

if __name__ == "__main__":
    main()
