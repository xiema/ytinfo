# ytinfo

A minimalist library for extracting video metadata and info from YouTube. Currently has functions for getting video details, thumbnails, and a channel's entire video list. Also works with livestreams.

# Installation

    pip install git+https://github.com/xiema/ytinfo

# Usage

## Library

The functions can be used directly to get the desired data.

    import ytinfo

    # Get the JSON data first
    data = ytinfo.get_data(VIDEO_URL)
    # Extract the video info into a dict
    videoinfo = ytinfo.extract_info(data)

    # Get the video thumbnail as raw data
    img = ytinfo.get_thumbnail(VIDEO_ID)

    # Get list of all videos on channel
    video_ids = ytinfo.get_channel_videos(CHANNEL_URL)

When making multiple requests, using a `requests.Session` object is recommended.

    import requests

    infos = []
    with requests.Session() as session:
        for VIDEO_URL in VIDEO_URLS:
            data = ytinfo.get_data(VIDEO_URL, session=session)
            infos.append(ytinfo.extract_info(data))
    

## Command Line

Package can also be run as a script.

To get and print video info:

    python -m ytinfo getinfo <video_url>

To save video thumbnail:

    python -m ytinfo getthumbnail <video_id> <output_filename>.jpg

To get and print the id list of all videos of a channel:

    python -m ytinfo getchannelvideos <channel_id>
