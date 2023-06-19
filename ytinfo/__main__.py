from .scraping import *

if __name__ == "__main__":
    from argparse import ArgumentParser
    parser = ArgumentParser()
    subparsers = parser.add_subparsers(dest='subcommand', required=True)

    _parser = subparsers.add_parser('getinfo', help="Get video info")
    _parser.add_argument('url', help="Video URL")

    _parser = subparsers.add_parser('getchannelvideos', help="Get list of channel videos")
    _parser.add_argument('channelid', help="Channel ID")

    _parser = subparsers.add_parser('getthumbnail', help="Get video thumbnail")
    _parser.add_argument('videoid', help="Video ID")
    _parser.add_argument('filename', help="Output filename")

    args = parser.parse_args()
    
    if args.subcommand == 'getinfo':
        import json
        data = get_data(args.url)
        videoinfo = extract_info(data)
        print(json.dumps(videoinfo, ensure_ascii=False, indent=4))
    elif args.subcommand == 'getchannelvideos':
        url = "https://www.youtube.com/channel/" + args.channelid
        videoids = get_channel_videos(url)
        print("\n".join(videoids))
    elif args.subcommand == 'getthumbnail':
        img = get_thumbnail(args.videoid, format='maxres')
        with open(args.filename, 'wb') as f:
            f.write(img)

