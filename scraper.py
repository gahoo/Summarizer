from firecrawl import FirecrawlApp
from dotenv import load_dotenv
from magic_html import GeneralExtractor
from readability import Document
from markdownify import markdownify
import requests
import os
import re
import pdb

load_dotenv()
FIRECRAWL_API_KEY=os.getenv('FIRECRAWL_API_KEY')
JINA_API_KEY=os.getenv('JINA_API_KEY', None)
MARKER_API_URL = os.getenv('MARKER_API_URL')
DOWNLOADER_FOLDER = os.getenv('DOWNLOADER_FOLDER', './')

def download_path(filename):
    return os.path.join(DOWNLOADER_FOLDER, filename)

def get_url_basename(url):
    return os.path.splitext(os.path.basename(url))[0][:20]

def write_flie(filename, content):
    with open(filename, 'w') as f:
        f.write(content)
    print(f"File written to {filename}")

def firecrawl(url, **kwargs):
    app = FirecrawlApp(api_key=FIRECRAWL_API_KEY)
    params = build_firecrawl_params(**kwargs)
    response = app.scrape_url(url, params)
    filename = download_path(response['metadata'].get('title', 'Untitled') + '.firecrawl.md')
    write_flie(filename, response['markdown'])
    return filename

def build_firecrawl_params(**kwargs):
    valid_params = ['onlyMainContent', 'onlyIncludeTags', 'removeTags']
    kwargs = {k:v for k, v in kwargs.items() if v and k in valid_params}
    if kwargs:
        params = {'pageOptions': {}}
        params['pageOptions'] = kwargs
        return params
    else:
        return {}
    
def jina(url, **kwargs):
    headers = build_jina_params(**kwargs)
    data = {'url': url}
    print(headers, data)

    response = requests.post('https://r.jina.ai/', headers=headers, data=data)
    json = response.json()
    filename = download_path(json['data'].get('title', 'Untitled') + '.jina.md')
    write_flie(filename, json['data']['content'])
    return filename

def build_jina_params(**kwargs):
    """
    {
        'Accept': 'application/json',
        'Authorization': 'Bearer jina_***',
        'X-Return-Format': 'markdown',
        'X-Target-Selector': '#img-content',
        'X-Timeout': '30',
        'X-Wait-For-Selector': '#content'
    }
    """
    valid_params = ['return_format', 'targe_selector', 'wait_for_selector', 'timeout']
    kwargs = {'X-' + k.capitalize().replace('_', '-'):str(v) for k, v in kwargs.items() if v and k in valid_params}
    headers = {'Accept': 'application/json'}
    if JINA_API_KEY:
        headers['Authorization'] = 'Bearer ' + JINA_API_KEY
    if kwargs:
        headers.update(kwargs)
    return headers

def magic_markdownify(url):
    response = requests.get(url)
    extractor = GeneralExtractor()
    data = extractor.extract(response.text, base_url=url)
    content = markdownify(data['html']).strip()
    markdown = '# {title}\n\n{content}'.format(title=data['title'], content=content)
    filename = download_path(data.get('title', 'Untitled') + '.magic.md')
    write_flie(filename, markdown)
    return filename
    
def readability_markdownify(url):
    response = requests.get(url)
    doc = Document(response.text)
    filename = download_path(doc.title() + '.readability.md')
    content = markdownify(doc.summary())
    markdown = '# {title}\n\n{content}'.format(title=doc.title(), content=content)
    write_flie(filename, markdown)
    return filename

def download_file(url):
    filename = download_path(os.path.basename(url))

    if os.path.exists(filename):
        local_file_size = os.path.getsize(filename)
    else:
        local_file_size = 0

    try:
        print(f"Downloading {url} to {filename}")
        response = requests.get(url, stream=True)
        response.raise_for_status()

        total_size = int(response.headers.get('content-length', 0))

        if local_file_size == total_size:
            print(f"File already downloaded completely: {filename}")
            return filename

        headers = {'Range': f'bytes={local_file_size}-'}
        response = requests.get(url, headers=headers, stream=True)
        response.raise_for_status()

        with open(filename, 'ab') as file:
            # 将响应逐块写入文件以防止内存溢出
            for chunk in response.iter_content(chunk_size=1024):
                file.write(chunk)

        print('File downloaded: ', filename)
        return filename

    except requests.exceptions.HTTPError as err:
        print("File download failed:", url)
        raise err

def extract_markdown_images(filename):
    with open(filename, 'r') as file:
        content = file.read()
    images = re.findall(r"!\[.*?\]\((.*?)\)", content, re.M)
    return images

def download_pdf(url, convert_to_markdown=False):
    filename = download_file(url)
    if convert_to_markdown:
        filename = pdf2markdown(filename)
    return filename

def pdf2markdown(pdf_file):
    """
    marker-api
    """
    print('Convert pdf to markdown using marker-api: ', pdf_file)
    files = {'pdf_file': (pdf_file, open(pdf_file, 'rb'), 'application/pdf')}
    response = requests.post(MARKER_API_URL, files=files)
    if response.status_code != 200:
        print(response.text)
        raise Exception('Failed to convert pdf or retrieve the results')

    filename = os.path.basename(pdf_file).replace('.pdf', '.md')
    json = response.json()
    markdown = json.get('markdown')
    write_flie(filename, markdown)
    print('PDF converted: ', filename)
    return filename
    