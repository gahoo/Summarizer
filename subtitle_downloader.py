import yt_dlp
import os
import argparse
import pdb
import re
import requests
import functools
from dotenv import load_dotenv
from groq import Groq
from scraper import download_path

load_dotenv()
GROQ_API_KEY=os.getenv('GROQ_API_KEY')
WHISPER_ASR_API_URL = os.getenv('WHISPER_ASR_API_URL')

def undo_proxy(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        http_proxy = os.environ.pop('http_proxy', None)
        https_proxy = os.environ.pop('https_proxy', None)

        result = func(*args, **kwargs)

        os.environ['http_proxy'] = http_proxy
        os.environ['https_proxy'] = https_proxy
        return result
    return wrapper

def get_best_subtitle_language(subtitles):
    preferred_languages = ['en', 'zh', 'zh-Hans', 'zh-Hant', 'zh-TW', 'en-US', 'en-GB']  # 添加更多语言代码
    
    # 首先检查是否有首选语言的字幕
    for lang in preferred_languages:
        if lang in subtitles:
            return lang
    
    # 如果没有首选语言，返回第一个可用的语言
    return next(iter(subtitles)) if subtitles else None

def srt_to_txt(srt_file_path, txt_file_path):
    """
    将SRT格式的字幕文件转换为纯文本TXT文件。
    
    :param srt_file_path: SRT文件的路径
    :param txt_file_path: 输出TXT文件的路径
    """
    # 用于匹配SRT文件中的时间戳行的正则表达式
    timestamp_pattern = re.compile(r'\d+:\d+:\d+,\d+ --> \d+:\d+:\d+,\d+')

    with open(srt_file_path, 'r', encoding='utf-8') as srt_file, \
         open(txt_file_path, 'w', encoding='utf-8') as txt_file:
        
        skip_next = False
        for line in srt_file:
            line = line.strip()
            
            # 跳过空行和序号行
            if not line or line.isdigit():
                continue
            
            # 跳过时间戳行
            if timestamp_pattern.match(line) or skip_next:
                skip_next = False
                continue
            
            # 写入字幕文本
            txt_file.write(line + ' ')
            
            # 如果这行以 '>' 结尾，下一行可能是时间戳的一部分，需要跳过
            if line.endswith('>'):
                skip_next = True

    print(f"转换完成。文本已保存到 {txt_file_path}")

def download_captions(url, cookies_file=None, language=None, convert_to_txt=False, transcribe=True):
    ydl_opts = {
        'skip_download': True,
        'postprocessors': [{
            'format': 'srt',
            'key': 'FFmpegSubtitlesConvertor',
            'when': 'before_dl'
        }]
    }
    
    if cookies_file:
        ydl_opts['cookiefile'] = cookies_file

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        safe_title = download_path("".join([c for c in info['title'] if c.isalpha() or c.isdigit() or c==' ']).rstrip())
        ydl.params['outtmpl']['default'] = f'{safe_title}.%(ext)s'
        if info.get('subtitles') and 'live_chat' not in info.get('subtitles'):
            if not language:
                language = get_best_subtitle_language(info['subtitles'])
            caption_file = download_youtube_captions(url, ydl, safe_title, language, automatic_captions=False, convert_to_txt=convert_to_txt)
        elif info.get('automatic_captions'):
            if not language:
                language = get_best_subtitle_language(info['automatic_captions'])
            caption_file = download_youtube_captions(url, ydl, safe_title, language, automatic_captions=True, convert_to_txt=convert_to_txt)
        else:
            audio_file = download_youtube_audio(url, ydl, safe_title)
            if not transcribe:
                return audio_file
            elif info.get('duration') <= 7200 and is_file_size_within_limit(audio_file, 25 * 1024 * 1024):
                caption_file = groq_transcribe(audio_file, language)
            else:
                caption_file = whisper_asr_transcribe(audio_file, language=language)
    return caption_file

def is_file_size_within_limit(filename, max_size):
    return os.path.getsize(filename) < max_size

def download_youtube_captions(url, ydl, safe_title, language, automatic_captions=False, convert_to_txt=False):
    if automatic_captions:
        ydl.params['writeautomaticsub'] = True
    else:
        ydl.params['writesubtitles'] = True

    ydl.params['subtitleslangs'] = [language]
    ydl.download([url])
    print(f"已下载字幕: {safe_title}.{language}.srt")
    if convert_to_txt:
        srt_to_txt(f'{safe_title}.{language}.srt', f'{safe_title}.{language}.txt')
        return f'{safe_title}.{language}.txt'
    else:
        return f'{safe_title}.{language}.srt'

def download_youtube_audio(url, ydl, safe_title):
    if 'youtube.com' in url or 'youtu.be' in url:
        ydl.format_selector = ydl.build_format_selector('139')
        ext = 'm4a'
    elif 'x.com' in url or 'twitter.com' in url:
        ydl.format_selector = ydl.build_format_selector('hls-audio-32000-Audio')
        ext = 'mp4'
    ydl.params['skip_download'] = False
    ydl.download([url])
    audio_file = f"{safe_title}.{ext}"
    return audio_file

def groq_transcribe(audio_file, language):
    client = Groq(api_key=GROQ_API_KEY)
    print(f"使用Groq进行语音识别: {audio_file}")
    with open(audio_file, "rb") as file:
        transcription = client.audio.transcriptions.create(
            file=(audio_file, file.read()),
            model="whisper-large-v3",
            response_format="verbose_json",
            language=language,
            temperature=0.0
        )
    
    safe_title = os.path.splitext(audio_file)[0]
    txt_file = f"{safe_title}.txt"
    text = "\n".join([segment['text'] for segment in transcription.segments])
    with open(txt_file, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"已识别字幕: {safe_title}.txt")
    return txt_file

@undo_proxy
def whisper_asr_transcribe(audio_file, **kwargs):
    files = {'audio_file': (audio_file, open(audio_file, "rb"), 'audio/x-m4a')}
    valid_params = ['encode', 'task', 'vad_filter', 'language', 'word_timestamps', 'output', 'initial_prompt']
    params = {k: str(v).lower() for k, v in kwargs.items() if v is not None and k in valid_params}
    headers = {'accept': 'application/json'}
    print(f"使用Whisper ASR进行语音识别: {audio_file}")
    response = requests.post(WHISPER_ASR_API_URL, files=files, params=params, headers=headers)
    response.raise_for_status()
    safe_title = os.path.splitext(audio_file)[0]
    output_format = kwargs.get('output', 'txt')
    out_file = f"{safe_title}.{output_format}"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(response.text)
    print(f"已识别字幕: {safe_title}.{output_format}")
    return out_file

def main():
    parser = argparse.ArgumentParser(description="下载YouTube视频的字幕或音频")
    parser.add_argument("url", help="YouTube视频的URL")
    parser.add_argument("--cookies", help="cookies文件的路径")
    parser.add_argument("--language", help="指定字幕语言（例如：en, es, fr）")
    args = parser.parse_args()

    download_captions(args.url, args.cookies, args.language)

if __name__ == "__main__":
    main()