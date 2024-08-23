from firecrawl import FirecrawlApp
from dotenv import load_dotenv
from magic_html import GeneralExtractor
from readability import Document
from markdownify import markdownify
from os import getenv as osenv
import requests
import os
import pdb

load_dotenv()
FIRECRAWL_API_KEY=osenv('FIRECRAWL_API_KEY')
JINA_API_KEY=osenv('JINA_API_KEY', None)
MARKER_API_URL = os.getenv('MARKER_API_URL')

def save_markdown(filename, content):
    with open(filename, 'w') as f:
        f.write(content)

def firecrawl(url, **kwargs):
    app = FirecrawlApp(api_key=FIRECRAWL_API_KEY)
    params = build_firecrawl_params(**kwargs)
    response = app.scrape_url(url, params)
    filename = response['metadata']['title'] + '.firecrawl.md'
    save_markdown(filename, response['markdown'])
    return filename

def build_firecrawl_params(**kwargs):
    kwargs = {k:v for k, v in kwargs.items() if v}
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
    filename = json['data']['title'] + '.jina.md'
    save_markdown(filename, json['data']['content'])
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
    kwargs = {'X-' + k.capitalize().replace('_', '-'):v for k, v in kwargs.items() if v}
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
    filename = data['title'] + '.magic.md'
    save_markdown(filename, markdown)
    return filename
    
def readability_markdownify(url):
    response = requests.get(url)
    doc = Document(response.text)
    filename = doc.title() + '.readability.md'
    content = markdownify(doc.summary())
    markdown = '# {title}\n\n{content}'.format(title=doc.title(), content=content)
    save_markdown(filename, markdown)
    return filename

def download_pdf(url, convert_to_markdown=False):
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
    except requests.exceptions.HTTPError as err:
        print("PDF download failed:", url)

    filename = os.path.basename(url)
    with open(filename, 'wb') as file:
        # 将响应逐块写入文件以防止内存溢出
        for chunk in response.iter_content(chunk_size=1024):
            file.write(chunk)
    print('PDF downloaded: ', filename)
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
    save_markdown(filename, markdown)
    print('PDF converted: ', filename)
    return filename
    