import os
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

def upload_to_youtube(video_file, title, description):
    # The specific permission we need: to upload videos
    scopes = ["https://www.googleapis.com/auth/youtube.upload"]
    creds = None

    # Check if we already have a saved login token
    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)

    # If there are no valid credentials, let the user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("client_secrets.json", scopes)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open("token.pickle", "wb") as token:
            pickle.dump(creds, token)

    # Build the YouTube API client
    youtube = build("youtube", "v3", credentials=creds)

    # Prepare the video metadata
    request_body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": ["shorts", "trending", "ai", "viral"],
            "categoryId": "22" # 22 = People & Blogs
        },
        "status": {
            "privacyStatus": "public", 
            "selfDeclaredMadeForKids": False
        }
    }

    # Load the media file
    media = MediaFileUpload(video_file, chunksize=-1, resumable=True)
    
    print(f"Uploading '{video_file}' to YouTube...")
    
    # Execute the upload request
    upload_request = youtube.videos().insert(
        part="snippet,status",
        body=request_body,
        media_body=media
    )

    response = upload_request.execute()
    print(f"🚀 Post successful! Video ID: {response.get('id')}")
    print(f"Link: https://youtube.com/shorts/{response.get('id')}")