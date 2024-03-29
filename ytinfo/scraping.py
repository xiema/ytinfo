import re, json
import requests
import time
from datetime import datetime
from .utils import *
from .exceptions import *

import logging
logger = logging.getLogger(__name__)


def get_info(url, session=None, retries=3, timeout=None):
    """
    Takes a video url and returns a dict of video info
    """
    return extract_info(get_data(url, session, retries, timeout))


def _extract_initial_player_response(text):
    return re.search(r"(?:window\s*\[\s*[\"']ytInitialPlayerResponse[\"']\s*\]|ytInitialPlayerResponse)\s*=\s*({.+?})\s*;", text)

def _extract_initial_data(text):
    return re.search(r"(?:window\s*\[\s*[\"']ytInitialData[\"']\s*\]|ytInitialData)\s*=\s*({.+?})\s*;", text)

def get_data(url, session=None, retries=3, timeout=None):
    """
    Takes a video url and returns a dict of the video's complete json data
    """
    if session is None:
        with requests.Session() as session:
            return get_data(url, session, retries, timeout)

    if timeout:
        end_time = time.monotonic() + timeout

    for _ in range(retries+1):
        if timeout:
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

        initial_player_response = _extract_initial_player_response(response.text)
        initial_data = _extract_initial_data(response.text)
        # check for malformed data
        if initial_player_response is None or initial_data is None:
            logger.warning(f"Errors on page for {url}")
            continue

        initial_player_response = json.loads(initial_player_response[1])
        initial_data = json.loads(initial_data[1])

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
        ret['id'] = re.search(r"https?://(www\.youtube\.com/watch\?v=|youtu\.be/)(?P<videoid>[\w-]+)",
                            data['url']).group('videoid')
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
    ret['publish_date'] = microformat['publishDate']
    ret['upload_date'] = microformat['uploadDate']

    ret['live_content'] = details['isLiveContent']
    ret['chat_available'] = get_chat_available(data)
    ret['average_rating'] = dict_tryget(details, 'averageRating')
    ret['views'] = details['viewCount']

    ret['family_safe'] = dict_tryget(microformat ,'isFamilySafe')

    # keywords
    ret['keywords'] = dict_tryget(details, 'keywords', default=[])


    # get chapters
    chapters = dict_tryget(idata, 'playerOverlays', 'playerOverlayRenderer',
        'decoratedPlayerBarRenderer','decoratedPlayerBarRenderer',
        'playerBar','chapteredPlayerBarRenderer','chapters', default=[])
    ret['chapters'] = [{'title': c['chapterRenderer']['title']['simpleText'],
        'starttime': c['chapterRenderer']['timeRangeStartMillis']} for
        c in chapters]


    # likes and dislikes
    ret['likes'], ret['dislikes'] = None, None
    content = str(dict_tryget(idata ,'contents','twoColumnWatchNextResults',
        'results','results','contents'))
    pat = "['\"]label['\"]\s*:\s*['\"]([\d,\.]+|No)\s+%s['\"]"
    m = re.search(pat % 'likes', content)
    if m:
        ret['likes'] = 0 if m[1]=='No' else int(re.sub("[,\.]", '', m[1]))
    m = re.search(pat % 'dislikes', content)
    if m:
        ret['dislikes'] = 0 if m[1]=='No' else int(re.sub("[,\.]", '', m[1]))

    ret['unlisted'] = dict_tryget(microformat, 'isUnlisted')
    ret['category'] = dict_tryget(microformat, 'category')

    # only for live streams
    ret['start_time'] = dict_tryget(microformat, 'liveBroadcastDetails','startTimestamp')
    ret['end_time'] = dict_tryget(microformat, 'liveBroadcastDetails','endTimestamp')

    return ret


def get_chat_available(data):
    if (dict_tryget(data, 'ytInitialData', 'contents', 'twoColumnWatchNextResults', 'conversationBar',
                    'liveChatRenderer') is not None and str(data).count("Live chat replay is not available") == 0):
        return True
    else:
        return False


def get_thumbnail(id, format='maxres', session=None, retries=3, timeout=None):
    """
    Takes a video id and thumbnail format (maxres or hq) and returns the video
    thumbnail as raw byte data
    """
    if session is None:
        with requests.Session() as session:
            return get_thumbnail(id, format, session, retries, timeout)

    if format == 'maxres':
        url = f"https://i.ytimg.com/vi/{id}/maxresdefault.jpg"
        # maxres is only available for premiere-released videos and live streams
    elif format == 'hq':
        url = f"https://i.ytimg.com/vi/{id}/hqdefault.jpg"
    else:
        raise Error(f"Unknown thumbnail format '{format}'")

    if timeout:
        end_time = time.monotonic() + timeout

    for _ in range(retries+1):
        if timeout is not None:
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


def get_channel_videos(url, session=None, retries=3, timeout=None):
    """
    Takes a channel url and returns a list of video ids from the main video
    catalog
    """
    if session is None:
        with requests.Session() as session:
            return get_channel_videos(url, session, retries, timeout)

    if not url.endswith("/videos"):
        url = url + "/videos"

    if timeout:
        end_time = time.monotonic() + timeout

    for _ in range(retries+1):
        if timeout is not None:
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

    data = json.loads(_extract_initial_data(response.text)[1])
    tabs = data['contents']['twoColumnBrowseResultsRenderer']['tabs']

    videos = []
    for tab in tabs:
        try:
            # get first page of videos
            items = tab['tabRenderer']['content']['sectionListRenderer']\
                ['contents'][0]['itemSectionRenderer']['contents'][0]\
                ['gridRenderer']['items']

            continuation = None
            for item in items:
                if 'continuationItemRenderer' not in item:
                    videos.append(item['gridVideoRenderer']['videoId'])
                else:
                    continuation = item

            # get succeeding pages
            while continuation is not None:
                token = continuation['continuationItemRenderer']['continuationEndpoint']\
                                    ['continuationCommand']['token']
                if timeout is not None:
                    remaining_time = end_time - time.monotonic()
                    if remaining_time <= 0:
                        raise TimeoutError(f"Timed out while loading {url}")
                else:
                    remaining_time = None

                response = session.get("https://www.youtube.com/browse_ajax",
                    headers={'x-youtube-client-name': '1',
                        'x-youtube-client-version': '2.20201112.04.01'
                    },
                    params={'ctoken': token,
                        'continuation': token,
                        #'itct': c['clickTrackingParams']
                    },
                    timeout=remaining_time)
                items = json.loads(response.text)[1]['response']\
                    ['onResponseReceivedActions'][0]['appendContinuationItemsAction']\
                    ['continuationItems']

                continuation = None
                for item in items:
                    if 'continuationItemRenderer' not in item:
                        videos.append(item['gridVideoRenderer']['videoId'])
                    else:
                        continuation = item

        except KeyError:
            pass

    return videos
