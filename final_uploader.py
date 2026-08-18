import os
import io
import pickle
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

# --- GOOGLE DRIVE FOLDER IDs ---
DRIVE_FOLDER_ID = "1Yxg1noKszBMwEEFTxw8NVw_dYrtpWEvo"
DONE_FOLDER_ID = "18oZV5nP7OrgComaLZ8CzZqdm6iIOHmpr"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(BASE_DIR, "Reddit Watch", "token.pickle")
TEMP_DIR = os.path.join(BASE_DIR, "temp_videos")

if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)

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
else:
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
        print(f"Successfully uploaded! Video ID: {response['id']}")

        # Move file in Drive to Uploaded_Done
        drive_service.files().update(
            fileId=file_id,
            addParents=DONE_FOLDER_ID,
            removeParents=DRIVE_FOLDER_ID,
            fields='id, parents'
        ).execute()

        # Clean up local file
        os.remove(local_path)