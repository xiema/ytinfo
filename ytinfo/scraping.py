import re
import json
import requests
import time
from datetime import datetime
from .utils import *
from .exceptions import *

import logging
logger = logging.getLogger(__name__)


def get_info(in_str, session=None, retries=3, timeout=None):
    """
    Takes a video url or id and returns a dict of video info
    """
    return extract_info(get_data(in_str, session, retries, timeout))


def _extract_initial_player_response(text):
    m = re.search(
        r"(?:window\s*\[\s*[\"']ytInitialPlayerResponse[\"']\s*\]|ytInitialPlayerResponse)\s*=\s*({.+?})\s*;", text)
    if m is not None:
        return json.loads(m[1])


def _extract_initial_data(text):
    m = re.search(
        r"(?:window\s*\[\s*[\"']ytInitialData[\"']\s*\]|ytInitialData)\s*=\s*({.+?})\s*;", text)
    if m is not None:
        return json.loads(m[1])


def _get_videoid(url):
    m = re.search(
        r"https?://(?:www\.youtube\.com/watch\?v=|youtu\.be/)([\w-]+)", url)
    if m is not None:
        return m[1]


def get_data(in_str, session=None, retries=3, timeout=None):
    """
    Takes a video url or id and returns a dict of the video's complete json data
    """
    if session is None:
        with requests.Session() as session:
            return get_data(in_str, session, retries, timeout)

    if re.search(r"^[\w-]+$", in_str) is not None:
        url = f"https://www.youtube.com/watch?v={in_str}"
    else:
        url = in_str

    end_time = None
    if timeout:
        end_time = time.monotonic() + timeout

    for _ in range(retries+1):
        if end_time is not None:
            remaining_time = end_time - time.monotonic()
            if remaining_time <= 0:
                raise TimeoutError(f"Timed out while loading {url}")
        else:
            remaining_time = None

        response = session.get(url,
                               headers={'accept-language': "en-US,en;q=0.9"},
                               timeout=remaining_time)

        if response.status_code != 200:
            logger.warning(f"Got status code {response.status_code} for {url}")
            continue

        initial_player_response = _extract_initial_player_response(
            response.text)
        initial_data = _extract_initial_data(response.text)
        # check for malformed data
        if initial_player_response is None or initial_data is None:
            logger.warning(f"Errors on page for {url}")
            continue

        return {'url': url,
                'ytInitialPlayerResponse': initial_player_response,
                'ytInitialData': initial_data}

    raise RetryError(f"Reached maximum retries for {url}")


def get_status(data):
    playability_status = data['ytInitialPlayerResponse']['playabilityStatus']

    # Differentiate age-restricted and privated videos as both give
    # status value of LOGIN_REQUIRED
    if playability_status['status'] == 'LOGIN_REQUIRED':
        if 'reason' in playability_status:
            return 'AGE_RESTRICTED'
        elif 'messages' in playability_status:
            return 'PRIVATE'

    return playability_status['status']


def extract_info(data):
    """
    Takes a video json data dict and returns a dict of the most relevant
    video info
    """

    ret = {}

    ret['status'] = get_status(data)
    ret['timestamp'] = datetime.utcnow().isoformat()

    if ret['status'] in ['ERROR', 'PRIVATE']:
        ret['id'] = _get_videoid(data['url'])
        return ret

    ipr = data['ytInitialPlayerResponse']
    details = ipr['videoDetails']
    idata = data['ytInitialData']
    microformat = dict_tryget(ipr, 'microformat', 'playerMicroformatRenderer') or \
        dict_tryget(ipr, 'microformat', 'microformatDataRenderer')

    ret['id'] = details['videoId']
    ret['author'] = details['author']
    ret['channel_id'] = details['channelId']
    ret['title'] = details['title']
    ret['description'] = details['shortDescription']
    ret['length'] = details['lengthSeconds']

    if microformat is not None:
        ret['publish_date'] = microformat['publishDate']
        ret['upload_date'] = microformat['uploadDate']

    ret['live_content'] = details['isLiveContent']
    ret['chat_available'] = get_chat_available(data)
    ret['average_rating'] = dict_tryget(details, 'averageRating')
    ret['views'] = details['viewCount']

    ret['family_safe'] = dict_tryget(microformat, 'isFamilySafe')

    # keywords
    ret['keywords'] = dict_tryget(details, 'keywords', default=[])

    # get chapters
    chapters = dict_tryget(idata, 'playerOverlays', 'playerOverlayRenderer',
                           'decoratedPlayerBarRenderer', 'decoratedPlayerBarRenderer',
                           'playerBar', 'chapteredPlayerBarRenderer', 'chapters', default=[])
    if chapters is not None:
        ret['chapters'] = [{'title': c['chapterRenderer']['title']['simpleText'],
                            'starttime': c['chapterRenderer']['timeRangeStartMillis']} for
                           c in chapters]

    # likes and dislikes
    ret['likes'], ret['dislikes'] = None, None
    content = str(dict_tryget(idata, 'contents', 'twoColumnWatchNextResults',
                              'results', 'results', 'contents'))
    pat = "['\"]label['\"]\\s*:\\s*['\"]([\\d,\\.]+|No)\\s+%s['\"]"
    m = re.search(pat % 'likes', content)
    if m:
        ret['likes'] = 0 if m[1] == 'No' else int(re.sub("[,\\.]", '', m[1]))
    m = re.search(pat % 'dislikes', content)
    if m:
        ret['dislikes'] = 0 if m[1] == 'No' else int(
            re.sub("[,\\.]", '', m[1]))

    ret['unlisted'] = dict_tryget(microformat, 'isUnlisted')
    ret['category'] = dict_tryget(microformat, 'category')

    # only for live streams
    ret['start_time'] = dict_tryget(
        microformat, 'liveBroadcastDetails', 'startTimestamp')
    ret['end_time'] = dict_tryget(
        microformat, 'liveBroadcastDetails', 'endTimestamp')

    return ret


def get_chat_available(data):
    if (dict_tryget(data, 'ytInitialData', 'contents', 'twoColumnWatchNextResults', 'conversationBar',
                    'liveChatRenderer') is not None and str(data).count("Live chat replay is not available") == 0):
        return True
    else:
        return False


def get_thumbnail(in_str, format='maxres', session=None, retries=3, timeout=None):
    """
    Takes a video url or id and thumbnail format (maxres or hq) and returns the video
    thumbnail as raw byte data
    """
    if session is None:
        with requests.Session() as session:
            return get_thumbnail(in_str, format, session, retries, timeout)

    if re.search(r"^[\w-]+$", in_str):
        id = in_str
    else:
        id = _get_videoid(in_str)
        if id is None:
            raise Error(f"Invalid input string: {in_str}")

    if format == 'maxres':
        url = f"https://i.ytimg.com/vi/{id}/maxresdefault.jpg"
    elif format == 'hq':
        url = f"https://i.ytimg.com/vi/{id}/hqdefault.jpg"
    else:
        raise Error(f"Unknown thumbnail format '{format}'")

    end_time = None
    if timeout:
        end_time = time.monotonic() + timeout

    for _ in range(retries+1):
        if end_time is not None:
            remaining_time = end_time - time.monotonic()
            if remaining_time <= 0:
                raise TimeoutError(f"Timed out while loading {url}")
        else:
            remaining_time = None

        try:
            resp = session.get(url, timeout=remaining_time)
            if resp.status_code == 200:
                return resp.content

            logger.warning(f"Got status code {resp.status_code} for {url}")
        # have gotten connection errors fairly often while scraping thumbnails
        except requests.ConnectionError:
            logger.warning(f"Got ConnectionError for {url}")
            pass

    raise RetryError(f"Reached maximum retries for {url}")


def get_channel_videos(in_str, session=None, retries=3, timeout=None):
    """
    Takes a channel url and returns a list of video ids from the main video
    catalog
    """
    if session is None:
        with requests.Session() as session:
            return get_channel_videos(in_str, session, retries, timeout)

    if re.match(r"^@[\w-]+$", in_str):
        base_url = f"https://www.youtube.com/{in_str}"
    elif re.match(r"^[\w-]+$", in_str):
        base_url = f"https://www.youtube.com/channel/{in_str}"
    else:
        base_url = in_str

    videos = []

    for url in [f"{base_url}/videos", f"{base_url}/streams", f"{base_url}/shorts"]:

        end_time = None
        if timeout:
            end_time = time.monotonic() + timeout

        for _ in range(retries+1):
            if end_time is not None:
                remaining_time = end_time - time.monotonic()
                if remaining_time <= 0:
                    raise TimeoutError(f"Timed out while loading {url}")
            else:
                remaining_time = None

            response = session.get(url, timeout=remaining_time)
            if response.status_code == 200:
                break
            logger.warning(f"Got status code {response.status_code} for {url}")
        else:
            raise RetryError(f"Reached maximum retries for {url}")

        data = _extract_initial_data(response.text)
        # check for malformed data
        if data is None:
            logger.warning(f"Errors on page for {url}")
            continue

        tabs = data['contents']['twoColumnBrowseResultsRenderer']['tabs']

        for tab in tabs:
            try:
                # get first page of videos
                items = tab['tabRenderer']['content']['richGridRenderer']['contents']

                continuation = None
                for item in items:
                    if 'continuationItemRenderer' not in item:
                        video_id = dict_tryget(item, 'richItemRenderer', 'content', 'videoRenderer', 'videoId') or dict_tryget(
                            item, 'richItemRenderer', 'content', 'reelItemRenderer', 'videoId')
                        videos.append(video_id)
                    else:
                        continuation = item

                # get succeeding pages
                while continuation is not None:
                    token = continuation['continuationItemRenderer']['continuationEndpoint']['continuationCommand']['token']
                    if end_time is not None:
                        remaining_time = end_time - time.monotonic()
                        if remaining_time <= 0:
                            raise TimeoutError(
                                f"Timed out while loading {url}")
                    else:
                        remaining_time = None

                    response = session.post("https://www.youtube.com/youtubei/v1/browse",
                                            headers={
                                                'content-type': 'application/json',
                                                'x-youtube-client-name': '1',
                                                'x-youtube-client-version': '2.20230613.01.00'
                                            },
                                            params={
                                                'key': 'AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8',
                                                'prettyPrint': 'false',
                                            },
                                            json={
                                                'context': {
                                                    'client': {
                                                        'clientName': 'WEB',
                                                        'clientVersion': '2.20230613.01.00'
                                                    }
                                                },
                                                'continuation': token,
                                            },
                                            timeout=remaining_time)

                    items = json.loads(response.text)[
                        'onResponseReceivedActions'][0]['appendContinuationItemsAction']['continuationItems']

                    continuation = None
                    for item in items:
                        if 'continuationItemRenderer' not in item:
                            videos.append(
                                item['richItemRenderer']['content']['videoRenderer']['videoId'])
                        else:
                            continuation = item

            except KeyError:
                pass

    return videos
