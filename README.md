# site scraper

a robust web scraper that downloads entire websites with all their resources, maintaining the original directory structure.

## features
- downloads all site resources (js, css, images, 3d models, audio, etc.)
- interactive mode for sites with dynamic content
- maintains original directory structure
- handles javascript-rendered content
- cross-platform (windows, macos, linux)

## installation

```bash
git clone https://github.com/getyoursnackon/site-scraper.git
cd site-scraper
pip install -r requirements.txt
```

## usage

basic scraping:
```bash
python site_scraper.py https://example.com
```

interactive mode (for sites with dynamic content):
```bash
python site_scraper.py -i https://example.com
```

custom output directory:
```bash
python site_scraper.py https://example.com --output my_sites
```

same-domain resource mode (default):
```bash
python site_scraper.py https://example.com --resource-same-domain-only
```

disable javascript url mining:
```bash
python site_scraper.py https://example.com --skip-js-url-mining
```

write a custom manifest file:
```bash
python site_scraper.py https://example.com --manifest-file crawl-manifest.json
```

parallel batch scrape from config:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_parallel_scrape.ps1
```

extract normalized content for Miss Nova site:
```bash
python .\scripts\content.py --scraped-root .\scraped_site_test2 --output-dir .\content
```

## interactive mode commands
- `done` - start scraping the current state
- `help` - show help message
- `url` - show current url
- `wait` - wait 5 more seconds for loading
- `refresh` - refresh the page

## requirements
- python 3.7+
- chrome browser
- see requirements.txt for python packages 
