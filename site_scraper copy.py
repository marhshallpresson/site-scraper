import os
import re
import json
import asyncio
import logging
import importlib
import sys
import time
from urllib.parse import urljoin, urlparse
from pathlib import Path
from collections import deque
from functools import partial
import http.server
import socketserver
import threading
import requests
from bs4 import BeautifulSoup
if sys.version_info >= (3, 12):
    import setuptools
    distutils_module = setuptools._distutils
    sys.modules.setdefault("distutils", distutils_module)
    sys.modules.setdefault("distutils.version", importlib.import_module("setuptools._distutils.version"))
import undetected_chromedriver as uc
from selenium.webdriver.chrome.options import Options
from tqdm import tqdm
import cssutils
import aiohttp
import platform

# Suppress cssutils warnings about modern CSS properties
cssutils.log.setLevel(logging.ERROR)

class SiteScraper:
    def __init__(
        self,
        base_url,
        output_dir="scraped_site",
        interactive=False,
        max_pages=200,
        max_depth=3,
        continuous=False,
        scan_interval=60,
        click_limit=20,
        click_wait=2,
        click_depth=1,
        live_save_interval=5,
        serve_on_complete=False,
        serve_port=8000,
        scroll_enabled=True,
        scroll_rounds=12,
        scroll_wait=1.5,
        scroll_max_seconds=30,
        manual_mode=False,
    ):
        self.base_url = base_url
        # Create a safe folder name from the URL
        safe_folder_name = re.sub(r'[^\w\-_]', '_', urlparse(base_url).netloc)
        self.output_dir = Path(output_dir) / safe_folder_name
        self.visited_urls = set()
        self.session = requests.Session()
        self.downloaded_files = set()
        self.interactive = interactive
        self.max_pages = max_pages
        self.max_depth = max_depth
        self.continuous = continuous
        self.scan_interval = scan_interval
        self.click_limit = click_limit
        self.click_wait = click_wait
        self.click_depth = click_depth
        self.live_save_interval = live_save_interval
        self.serve_on_complete = serve_on_complete
        self.serve_port = serve_port
        self.scroll_enabled = scroll_enabled
        self.scroll_rounds = scroll_rounds
        self.scroll_wait = scroll_wait
        self.scroll_max_seconds = scroll_max_seconds
        self.manual_mode = manual_mode
        self.base_domain = urlparse(base_url).netloc
        self.clicked_signatures = set()
        self._stop_flag = False
        self.setup_logging()
        self.setup_selenium()
        
    def setup_logging(self):
        os.makedirs('logs', exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(Path('logs') / 'scraper.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def setup_selenium(self):
        options = uc.ChromeOptions()
        if not self.interactive:
            options.add_argument("--headless")
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
        
        try:
            if self.interactive:
                self.driver = uc.Chrome(
                    options=options,
                    use_subprocess=True,
                    headless=False
                )
            else:
                self.driver = uc.Chrome(
                    options=options,
                    use_subprocess=False,
                    headless=True
                )
            self.logger.info("Chrome initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize Chrome: {str(e)}")
            raise

    def create_directory_structure(self, url_path):
        """Create necessary directory structure for saving files."""
        if not url_path or url_path == '/':
            return self.output_dir / 'index.html'
        
        parsed_url = urlparse(url_path)
        path = parsed_url.path.lstrip('/')
        sanitized_path = self._sanitize_path(path)
        full_path = self.output_dir / sanitized_path
        
        # Create parent directories if they don't exist
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        
        return full_path

    @staticmethod
    def _sanitize_segment(segment):
        cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1F]', '_', segment)
        cleaned = cleaned.strip(" .")
        if not cleaned:
            return "_"
        return cleaned[:120]

    def _sanitize_path(self, path):
        if not path:
            return "index.html"
        segments = [self._sanitize_segment(seg) for seg in path.split('/') if seg != '']
        if not segments:
            return "index.html"
        return "/".join(segments)

    def _build_save_path(self, url, treat_as_html=False):
        parsed = urlparse(url)
        path = parsed.path or "/"
        if treat_as_html:
            if path.endswith("/"):
                path = f"{path}index.html"
            else:
                last = path.rsplit("/", 1)[-1]
                if "." not in last:
                    path = f"{path}/index.html"
        else:
            if path.endswith("/"):
                path = f"{path}index.html"
        sanitized_path = self._sanitize_path(path.lstrip("/"))
        if parsed.query:
            query = re.sub(r'[^A-Za-z0-9._-]+', '_', parsed.query)[:60]
            if query:
                sanitized_path = f"{sanitized_path}__{query}"
        return self.output_dir / sanitized_path

    def _install_stop_overlay(self):
        if not self.interactive:
            return
        try:
            self.driver.execute_script(
                """
                (() => {
                  if (window.__SCRAPER_STOP_INSTALLED__) return;
                  window.__SCRAPER_STOP_INSTALLED__ = true;
                  window.__SCRAPER_STOP__ = false;
                  const btn = document.createElement('button');
                  btn.id = '__scraper_stop_btn__';
                  btn.textContent = 'STOP CAPTURE';
                  btn.style.position = 'fixed';
                  btn.style.top = '12px';
                  btn.style.right = '12px';
                  btn.style.zIndex = '2147483647';
                  btn.style.padding = '10px 14px';
                  btn.style.borderRadius = '10px';
                  btn.style.border = '1px solid rgba(255,255,255,0.25)';
                  btn.style.background = 'rgba(220, 38, 38, 0.92)';
                  btn.style.color = 'white';
                  btn.style.fontFamily = 'system-ui, -apple-system, Segoe UI, Roboto, Arial';
                  btn.style.fontSize = '14px';
                  btn.style.cursor = 'pointer';
                  btn.style.boxShadow = '0 10px 25px rgba(0,0,0,0.25)';
                  btn.onclick = () => { window.__SCRAPER_STOP__ = true; btn.textContent = 'STOPPING...'; };
                  document.documentElement.appendChild(btn);
                })();
                """
            )
        except Exception:
            return

    def _stop_requested(self):
        if not self.interactive:
            return False
        if self._stop_flag:
            return True
        try:
            requested = bool(self.driver.execute_script("return window.__SCRAPER_STOP__ === true;"))
            if requested:
                self._stop_flag = True
            return requested
        except Exception:
            return False

    def _auto_scroll(self):
        if not self.scroll_enabled:
            return
        start = time.time()
        last_height = None
        for _ in range(self.scroll_rounds):
            if self._stop_requested():
                return
            try:
                height = self.driver.execute_script("return document.body.scrollHeight;")
            except Exception:
                return
            if last_height is not None and height == last_height:
                break
            last_height = height
            try:
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            except Exception:
                return
            time.sleep(self.scroll_wait)
            if time.time() - start >= self.scroll_max_seconds:
                break
            try:
                buttons = self.driver.find_elements(
                    "xpath",
                    "//*[self::button or self::a][contains(translate(normalize-space(string(.)),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'load more') or contains(translate(normalize-space(string(.)),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'show more') or contains(translate(normalize-space(string(.)),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'view more')]",
                )
                for button in buttons[:3]:
                    try:
                        self.driver.execute_script("arguments[0].click();", button)
                        time.sleep(self.scroll_wait)
                    except Exception:
                        continue
            except Exception:
                pass

    def _serve_output(self):
        handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(self.output_dir))
        with socketserver.TCPServer(("", self.serve_port), handler) as httpd:
            self.logger.info(f"Serving extracted site at http://localhost:{self.serve_port}/")
            httpd.serve_forever()

    async def _capture_current_state(self):
        current_url = self.driver.current_url
        if not current_url or not self._is_http_url(current_url) or not self._same_domain(current_url):
            return
        self._install_stop_overlay()
        self._auto_scroll()
        page_source = self.driver.page_source
        soup = BeautifulSoup(page_source, "html.parser")
        save_path = self._build_save_path(current_url, treat_as_html=True)
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(page_source)
        resources = set(self.extract_resources(soup, current_url))
        try:
            loaded_resources = self.driver.execute_script("""
                const resources = new Set();
                performance.getEntriesByType('resource').forEach(entry => {
                    resources.add(entry.name);
                });
                return Array.from(resources);
            """)
        except Exception:
            loaded_resources = []
        for resource in loaded_resources:
            normalized = self._normalize_resource_url(current_url, resource)
            if normalized:
                resources.add(normalized)
        async with aiohttp.ClientSession() as session:
            tasks = [self.download_resource(res, session) for res in resources]
            if tasks:
                with tqdm(total=len(tasks), desc="Downloading resources") as pbar:
                    for task in asyncio.as_completed(tasks):
                        await task
                        pbar.update(1)
        for link in self._collect_links(soup, current_url):
            self.visited_urls.add(link)

    async def _interactive_capture(self):
        last_saved_url = None
        last_saved_time = 0.0
        self.driver.get(self.base_url)
        self._install_stop_overlay()
        while not self._stop_requested():
            current_url = self.driver.current_url
            now = time.time()
            if current_url != last_saved_url or now - last_saved_time >= self.live_save_interval:
                await self._capture_current_state()
                last_saved_url = current_url
                last_saved_time = now
            await asyncio.sleep(1)
        self.logger.info("Interactive session stopped")

    @staticmethod
    def _is_http_url(url):
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https")

    def _normalize_resource_url(self, base_url, candidate):
        if not candidate:
            return None
        candidate = candidate.strip()
        if candidate.startswith(("data:", "blob:", "javascript:", "mailto:", "tel:")):
            return None
        absolute = urljoin(base_url, candidate)
        if not self._is_http_url(absolute):
            return None
        return absolute

    def _same_domain(self, url):
        parsed = urlparse(url)
        return parsed.netloc == self.base_domain

    def _enqueue_url(self, queue, url, depth):
        if depth > self.max_depth:
            return
        if not url or not self._is_http_url(url) or not self._same_domain(url):
            return
        if url in self.visited_urls:
            return
        queue.append((url, depth))

    def _collect_links(self, soup, base_url):
        links = set()
        for tag in soup.find_all("a", href=True):
            normalized = self._normalize_resource_url(base_url, tag["href"])
            if normalized and self._same_domain(normalized):
                links.add(normalized)
        return links

    def _click_explore(self, base_url, depth, queue):
        if depth >= self.click_depth:
            return
        try:
            elements = self.driver.find_elements(
                "css selector",
                "a[href], button, [role='tab'], [data-bs-toggle], [data-toggle], [onclick]",
            )
        except Exception:
            return
        original_url = self.driver.current_url
        original_handle = self.driver.current_window_handle
        click_count = 0
        for element in elements:
            if click_count >= self.click_limit:
                break
            try:
                signature = f"{original_url}|{element.get_attribute('outerHTML')}"
            except Exception:
                continue
            if signature in self.clicked_signatures:
                continue
            self.clicked_signatures.add(signature)
            try:
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                self.driver.execute_script("arguments[0].click();", element)
                time.sleep(self.click_wait)
            except Exception:
                continue
            handles = self.driver.window_handles
            new_handles = [h for h in handles if h != original_handle]
            if new_handles:
                for handle in new_handles:
                    try:
                        self.driver.switch_to.window(handle)
                        new_url = self.driver.current_url
                        if self._same_domain(new_url):
                            self._enqueue_url(queue, new_url, depth + 1)
                        soup = BeautifulSoup(self.driver.page_source, "html.parser")
                        for link in self._collect_links(soup, new_url):
                            self._enqueue_url(queue, link, depth + 1)
                    finally:
                        self.driver.close()
                self.driver.switch_to.window(original_handle)
                self.driver.get(original_url)
            else:
                new_url = self.driver.current_url
                if self._same_domain(new_url):
                    self._enqueue_url(queue, new_url, depth + 1)
                soup = BeautifulSoup(self.driver.page_source, "html.parser")
                for link in self._collect_links(soup, new_url):
                    self._enqueue_url(queue, link, depth + 1)
                self.driver.get(original_url)
            click_count += 1

    async def download_resource(self, url, session):
        if not self._is_http_url(url):
            return None
        if url in self.downloaded_files:
            return None
            
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    content = await response.read()
                    
                    if not url.startswith(self.base_url) and not url.startswith('/'):
                        return content
                    
                    save_path = self._build_save_path(url)
                    os.makedirs(os.path.dirname(save_path), exist_ok=True)
                    
                    with open(save_path, 'wb') as f:
                        f.write(content)
                    self.downloaded_files.add(url)
                    self.logger.info(f"Downloaded: {url} -> {save_path}")
                    return content
                else:
                    self.logger.warning(f"Failed to download {url}: Status {response.status}")
        except Exception as e:
            self.logger.error(f"Error downloading {url}: {str(e)}")
        return None

    def analyze_javascript(self, js_content, base_url):
        resources = set()
        path_vars = {}
        var_assignments = re.finditer(r'(?:const|let|var)\s+(\w+)\s*=\s*[\'"]([^\'"\s]+)[\'"]', js_content)
        for match in var_assignments:
            var_name, value = match.groups()
            path_vars[var_name] = value

        dynamic_paths = re.finditer(r'(?:const|let|var)\s+(\w+)\s*=\s*\{([^}]+)\}', js_content)
        for match in dynamic_paths:
            var_name, content = match.groups()
            pairs = re.finditer(r'(\w+):\s*[\'"]([^\'"\s]+)[\'"]', content)
            for pair in pairs:
                key, value = pair.groups()
                path_vars[f"{var_name}.{key}"] = value

        patterns = [
            r'(?:src|href|url):\s*[\'"]([^\'"\s]+)[\'"]',
            r'(?:load|fetch|import)\s*\([\'"]([^\'"\s]+)[\'"]',
            r'new\s+(?:Image|Audio)\([\'"]([^\'"\s]+)[\'"]',
            r'\.load\s*\([\'"]([^\'"\s]+)[\'"]',
            r'\.loadTexture\s*\([\'"]([^\'"\s]+)[\'"]',
            r'\.setPath\s*\([\'"]([^\'"\s]+)[\'"]',
            r'`([^`]+?\.(?:mp3|wav|ogg|glb|gltf|jpg|png))`',
            r'\.join\s*\([\'"]([^\'"\s]+)[\'"]',
            r'\.resolve\s*\([\'"]([^\'"\s]+)[\'"]',
            r'[\'"](/[^\'"\s]+\.(?:js|css|png|jpg|jpeg|gif|svg|mp3|wav|json|wasm|glb|gltf|bin|basis|ktx2|drc|ico))[\'"]'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, js_content)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0]
                if match and not match.startswith(('http://', 'https://', 'data:', 'blob:', 'javascript:')):
                    match = match.strip('\'"`')
                    if match.startswith('./'):
                        match = match[2:]
                    for var_name, var_value in path_vars.items():
                        if var_name in match:
                            match = match.replace(var_name, var_value)
                    normalized = self._normalize_resource_url(base_url, match)
                    if normalized:
                        resources.add(normalized)

        imports = re.finditer(r'(?:import|require)\s*\(\s*[\'"]([^\'"\s]+)[\'"]', js_content)
        for match in imports:
            path = match.group(1)
            normalized = self._normalize_resource_url(base_url, path)
            if normalized:
                resources.add(normalized)

        return resources

    def extract_resources(self, soup, base_url):
        resources = set()
        
        for script in soup.find_all('script', src=True):
            script_url = self._normalize_resource_url(base_url, script["src"])
            if not script_url:
                continue
            resources.add(script_url)
            try:
                response = requests.get(script_url, timeout=15)
                if response.status_code == 200:
                    js_resources = self.analyze_javascript(response.text, base_url)
                    resources.update(js_resources)
            except requests.exceptions.SSLError as e:
                self.logger.warning(f"SSL error analyzing script {script_url}: {str(e)}")
            except Exception as e:
                self.logger.error(f"Error analyzing script {script_url}: {str(e)}")
        
        for script in soup.find_all('script'):
            if script.string:
                js_resources = self.analyze_javascript(script.string, base_url)
                resources.update(js_resources)
        
        for css in soup.find_all('link', rel='stylesheet'):
            if css.get('href'):
                css_url = self._normalize_resource_url(base_url, css["href"])
                if not css_url:
                    continue
                resources.add(css_url)
                try:
                    response = requests.get(css_url, timeout=15)
                    if response.status_code == 200:
                        css_content = response.text
                        url_patterns = [
                            r'url\([\'"]?([^\'"\)]+)[\'"]?\)',
                            r'@import\s+[\'"]([^\'"\s]+)[\'"]'
                        ]
                        for pattern in url_patterns:
                            matches = re.findall(pattern, css_content)
                            for match in matches:
                                normalized = self._normalize_resource_url(base_url, match)
                                if normalized:
                                    resources.add(normalized)
                except requests.exceptions.SSLError as e:
                    self.logger.warning(f"SSL error analyzing CSS {css_url}: {str(e)}")
                except Exception as e:
                    self.logger.error(f"Error analyzing CSS {css_url}: {str(e)}")
        
        for tag in soup.find_all(['img', 'video', 'audio', 'source', 'model-viewer', 'canvas']):
            for attr in ['src', 'data-src', 'srcset', 'href', 'data-model', 'data-texture']:
                if tag.get(attr):
                    if attr == 'srcset':
                        for src_str in tag[attr].split(','):
                            url = src_str.strip().split()[0]
                            normalized = self._normalize_resource_url(base_url, url)
                            if normalized:
                                resources.add(normalized)
                    else:
                        normalized = self._normalize_resource_url(base_url, tag[attr])
                        if normalized:
                            resources.add(normalized)
        
        for meta in soup.find_all('meta'):
            if meta.get('content') and meta.get('content').startswith(('/','http')):
                if any(key in str(meta) for key in ['image', 'video', 'audio', 'model']):
                    normalized = self._normalize_resource_url(base_url, meta["content"])
                    if normalized:
                        resources.add(normalized)
        
        for tag in soup.find_all(True):
            for attr in tag.attrs:
                if isinstance(tag[attr], str):
                    if any(ext in tag[attr].lower() for ext in ['.glb', '.gltf', '.bin', '.jpg', '.png', '.basis']):
                        normalized = self._normalize_resource_url(base_url, tag[attr])
                        if normalized:
                            resources.add(normalized)
        
        return resources

    async def process_page(self, url, depth, queue):
        self.logger.info(f"Processing page: {url}")
        
        try:
            self.driver.get(url)
            self._install_stop_overlay()
            self.driver.execute_script("""
                return new Promise((resolve) => {
                    if (document.readyState === 'complete') {
                        setTimeout(resolve, 2000);
                    } else {
                        window.addEventListener('load', () => setTimeout(resolve, 2000));
                    }
                });
            """)
            self._install_stop_overlay()
            self._auto_scroll()
            
            # Additional wait for dynamic content
            self.driver.execute_script("""
                return new Promise((resolve) => {
                    const start = performance.now();
                    const checkResources = () => {
                        const pending = performance.getEntriesByType('resource')
                            .filter(r => !r.responseEnd);
                        if (pending.length === 0 || performance.now() - start > 10000) {
                            resolve();
                        } else {
                            setTimeout(checkResources, 100);
                        }
                    };
                    checkResources();
                });
            """)
            
            page_source = self.driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')
            save_path = self._build_save_path(url, treat_as_html=True)
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write(page_source)
            
            page_resources = self.extract_resources(soup, url)
            resources = set(page_resources)
            
            loaded_resources = self.driver.execute_script("""
                const resources = new Set();
                performance.getEntriesByType('resource').forEach(entry => {
                    resources.add(entry.name);
                });
                
                const getElementResources = (tagName, attrs) => {
                    return Array.from(document.getElementsByTagName(tagName))
                        .map(el => attrs.map(attr => el[attr]))
                        .flat()
                        .filter(url => url && !url.startsWith('data:') && !url.startsWith('blob:'));
                };
                
                [
                    ['script', ['src']],
                    ['link', ['href']],
                    ['img', ['src', 'currentSrc']],
                    ['audio', ['src']],
                    ['video', ['src']],
                    ['source', ['src']],
                    ['object', ['data']],
                    ['embed', ['src']]
                ].forEach(([tag, attrs]) => {
                    getElementResources(tag, attrs).forEach(url => resources.add(url));
                });
                
                return Array.from(resources);
            """)
            
            for resource in loaded_resources:
                normalized = self._normalize_resource_url(url, resource)
                if normalized:
                    resources.add(normalized)
            
            self.logger.info(f"Found {len(resources)} resources to download")
            
            async with aiohttp.ClientSession() as session:
                tasks = [self.download_resource(res, session) for res in resources]
                with tqdm(total=len(tasks), desc="Downloading resources") as pbar:
                    for task in asyncio.as_completed(tasks):
                        await task
                        pbar.update(1)
            for link in self._collect_links(soup, url):
                if not link.endswith(('.pdf', '.jpg', '.png', '.gif')):
                    self._enqueue_url(queue, link, depth + 1)

            self._click_explore(url, depth, queue)
                    
        except Exception as e:
            self.logger.error(f"Error processing {url}: {str(e)}")
            raise

    async def scrape(self):
        self.logger.info(f"Starting scrape of {self.base_url}")
        os.makedirs(self.output_dir, exist_ok=True)
        completed = False
        try:
            if self.interactive and self.manual_mode:
                await self._interactive_capture()
                completed = True
            while not completed:
                queue = deque([(self.base_url, 0)])
                processed = 0
                while queue and processed < self.max_pages:
                    if self._stop_requested():
                        queue.clear()
                        break
                    url, depth = queue.popleft()
                    if url in self.visited_urls:
                        continue
                    self.visited_urls.add(url)
                    await self.process_page(url, depth, queue)
                    processed += 1
                if self.interactive or not self.continuous:
                    break
                await asyncio.sleep(self.scan_interval)
            completed = True
            self.logger.info(f"Scraping completed! Downloaded {len(self.downloaded_files)} files")
            self.logger.info(f"Files saved in: {self.output_dir}")
        finally:
            try:
                self.driver.quit()
            finally:
                self.driver = None
        if completed and self.serve_on_complete:
            self._serve_output()

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Scrape a website including all resources.')
    parser.add_argument('url', help='The base URL to scrape')
    parser.add_argument('--output', default='scraped_site', help='Output directory')
    parser.add_argument('--interactive', '-i', action='store_true', help='Open browser for interactive exploration before scraping')
    parser.add_argument('--max-pages', type=int, default=200, help='Maximum pages to scan per cycle')
    parser.add_argument('--max-depth', type=int, default=3, help='Maximum link depth from the base URL')
    parser.add_argument('--continuous', action='store_true', help='Continuously rescan the site')
    parser.add_argument('--scan-interval', type=int, default=60, help='Seconds between continuous scans')
    parser.add_argument('--click-limit', type=int, default=20, help='Maximum automated clicks per page')
    parser.add_argument('--click-wait', type=int, default=2, help='Seconds to wait after each click')
    parser.add_argument('--click-depth', type=int, default=1, help='Maximum click exploration depth')
    parser.add_argument('--live-interval', type=int, default=5, help='Seconds between live saves in interactive mode')
    parser.add_argument('--serve', action='store_true', help='Serve the extracted site locally after scraping')
    parser.add_argument('--serve-port', type=int, default=8000, help='Port for local preview server')
    parser.add_argument('--scroll', action='store_true', help='Enable infinite scroll processing')
    parser.add_argument('--scroll-rounds', type=int, default=12, help='Maximum scroll rounds per page')
    parser.add_argument('--scroll-wait', type=float, default=1.5, help='Seconds to wait per scroll step')
    parser.add_argument('--scroll-max-seconds', type=int, default=30, help='Maximum seconds spent scrolling per page')
    parser.add_argument('--manual', action='store_true', help='Manual capture mode with live saving only')
    args = parser.parse_args()
    
    if platform.system() == 'Windows':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    interactive = args.interactive
    serve_on_complete = args.serve or args.interactive
    scraper = SiteScraper(
        args.url,
        args.output,
        interactive,
        max_pages=args.max_pages,
        max_depth=args.max_depth,
        continuous=args.continuous,
        scan_interval=args.scan_interval,
        click_limit=args.click_limit,
        click_wait=args.click_wait,
        click_depth=args.click_depth,
        live_save_interval=args.live_interval,
        serve_on_complete=serve_on_complete,
        serve_port=args.serve_port,
        scroll_enabled=args.scroll or args.interactive,
        scroll_rounds=args.scroll_rounds,
        scroll_wait=args.scroll_wait,
        scroll_max_seconds=args.scroll_max_seconds,
        manual_mode=args.manual,
    )
    asyncio.run(scraper.scrape())

if __name__ == "__main__":
    main() 
