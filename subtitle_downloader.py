import yt_dlp
import os
import argparse
import pdb
from dotenv import load_dotenv
from groq import Groq

def get_best_subtitle_language(subtitles, auto_captions):
    all_subs = {**subtitles, **auto_captions}
    preferred_languages = ['en', 'es', 'fr', 'de', 'it', 'pt', 'zh']  # 添加更多语言代码
    
    # 首先检查是否有首选语言的字幕
    for lang in preferred_languages:
        if lang in all_subs:
            return lang
    
    # 如果没有首选语言，返回第一个可用的语言
    return next(iter(all_subs)) if all_subs else None

def download_subtitle_or_audio(url, cookies_file=None, groq_api_key=None, language=None):
    ydl_opts = {
        'skip_download': True,
        'writesubtitles': True,
        'writeautomaticsub': True,
        'outtmpl': '%(title)s.%(ext)s',
    }
    
    if cookies_file:
        ydl_opts['cookiefile'] = cookies_file

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        title = info['title']
        safe_title = "".join([c for c in title if c.isalpha() or c.isdigit() or c==' ']).rstrip()
        
        if not language:
            language = get_best_subtitle_language(info.get('subtitles', {}), info.get('automatic_captions', {}))

                # 检查是否有字幕
        if info.get('subtitles'):
            # 下载字幕
            ydl_opts = {
                'skip_download': True,
                'writesubtitles': True,
                'outtmpl': f'{safe_title}.%(ext)s',
                'postprocessors': [{'format': 'srt',
                     'key': 'FFmpegSubtitlesConvertor',
                     'when': 'before_dl'}],
            }
            if cookies_file:
                ydl_opts['cookiefile'] = cookies_file
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            print(f"已下载字幕: {safe_title}.srt")
            return f'{safe_title}.{language}.srt'
        
        elif info.get('automatic_captions'):
            # 下载自动生成的字幕
            ydl_opts = {
                'skip_download': True,
                'writeautomaticsub': True,
                'postprocessors': [{'format': 'srt',
                     'key': 'FFmpegSubtitlesConvertor',
                     'when': 'before_dl'}],
                'outtmpl': f'{safe_title}.%(ext)s',
            }
            if cookies_file:
                ydl_opts['cookiefile'] = cookies_file
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            print(f"已下载自动生成的字幕: {safe_title}.srt")
            return f'{safe_title}.{language}.srt'
        
        else:
            # 如果没有字幕，下载音频并使用Whisper API
            ydl_opts = {
                'format': '139',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'm4a',
                    'preferredquality': '16',
                }],
                'outtmpl': f'{safe_title}.%(ext)s',
            }
            if cookies_file:
                ydl_opts['cookiefile'] = cookies_file

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        
            audio_file = f"{safe_title}.m4a"
            if os.path.exists(audio_file) and groq_api_key:
                client = Groq(api_key=groq_api_key)
                with open(audio_file, "rb") as file:
                    transcription = client.audio.transcriptions.create(
                        file=(audio_file, file.read()),
                        model="whisper-large-v3",
                        response_format="verbose_json",
                        language=language,
                        temperature=0.0
                    )
                
                txt_file = f"{safe_title}.txt"
                text = "\n".join([segment['text'] for segment in transcription.segments])
                with open(txt_file, "w", encoding="utf-8") as f:
                    f.write(text)
                
                print(f"已生成{language}字幕: {txt_file}")
            return txt_file

def main():
    parser = argparse.ArgumentParser(description="下载YouTube视频的字幕或音频")
    parser.add_argument("url", help="YouTube视频的URL")
    parser.add_argument("--cookies", help="cookies文件的路径")
    parser.add_argument("--language", help="指定字幕语言（例如：en, es, fr）")
    args = parser.parse_args()

    load_dotenv()
    GROQ_API_KEY=os.getenv('GROQ_API_KEY')
    download_subtitle_or_audio(args.url, args.cookies, GROQ_API_KEY, args.language)

if __name__ == "__main__":
    main()