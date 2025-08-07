import stealth_requests as requests
from stealth_requests import StealthSession
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time
import json
import re
import random

class ImageChecker:
    def __init__(self, identity_id=0):
        # Configuration avancée de StealthSession pour être indétectable
        self.session = StealthSession(
            timeout=30,
            headers={
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Cache-Control': 'max-age=0'
            }
        )
        
        # Liste de User-Agents pour rotation
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:120.0) Gecko/20100101 Firefox/120.0'
        ]
        
        # Référents français courants pour paraître naturel
        self.referrers = [
            'https://www.google.fr/',
            'https://www.google.com/',
            'https://www.bing.com/',
            'https://duckduckgo.com/',
            'https://www.qwant.com/',
            'https://search.yahoo.com/'
        ]
        self.request_count = 0
        
    def _make_stealth_request(self, url, method='GET', **kwargs):
        """Effectue une requête indétectable avec rotation d'User-Agent et délais"""
        # Simuler un comportement humain
        behavior = self._simulate_human_behavior()
        
        # Délai aléatoire adaptatif selon le comportement
        if behavior == 'burst':
            delay = random.uniform(0.2, 0.8)  # Plus rapide en mode burst
        else:
            delay = random.uniform(0.8, 2.5)  # Délai normal plus variable
        time.sleep(delay)
        
        # Rotation du User-Agent tous les 10-15 requêtes
        if self.request_count % random.randint(10, 15) == 0:
            user_agent = random.choice(self.user_agents)
            self.session.headers.update({'User-Agent': user_agent})
            # Profiter du changement d'UA pour mettre à jour les headers anti-fingerprint
            self._add_anti_fingerprint_headers()
        
        # Ajouter un référent aléatoire parfois
        if random.random() < 0.3:  # 30% de chance
            referrer = random.choice(self.referrers)
            self.session.headers.update({'Referer': referrer})
        elif 'Referer' in self.session.headers:
            del self.session.headers['Referer']
        
        # Varier les timeouts
        timeout = kwargs.get('timeout', random.uniform(8, 15))
        kwargs['timeout'] = timeout
        
        self.request_count += 1
        
        # Retry avec backoff exponentiel en cas d'échec
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if method.upper() == 'GET':
                    response = self.session.get(url, **kwargs)
                elif method.upper() == 'HEAD':
                    response = self.session.head(url, **kwargs)
                else:
                    response = self.session.request(method, url, **kwargs)
                
                # Si on obtient un 429 (rate limit), attendre plus longtemps
                if response.status_code == 429:
                    wait_time = random.uniform(5, 10) * (attempt + 1)
                    print(f"⚠️  Rate limit détecté, attente {wait_time:.1f}s...")
                    time.sleep(wait_time)
                    continue
                
                return response
                
            except Exception as e:
                if attempt == max_retries - 1:
                    raise e
                # Délai exponentiel entre tentatives
                wait_time = random.uniform(1, 3) * (2 ** attempt)
                time.sleep(wait_time)
        
        return None
    
    def _simulate_human_behavior(self):
        """Simule un comportement humain aléatoire"""
        # Parfois faire une pause plus longue (comme si l'utilisateur lisait)
        if random.random() < 0.05:  # 5% de chance
            reading_time = random.uniform(3, 8)
            print(f"🤔 Pause lecture simulée: {reading_time:.1f}s")
            time.sleep(reading_time)
        
        # Simuler des pics d'activité et des pauses (comme un humain)
        if random.random() < 0.1:  # 10% de chance
            activity_burst = random.randint(3, 6)
            print(f"🔥 Pic d'activité simulé: {activity_burst} requêtes rapides")
            return 'burst'
        
        return 'normal'
    
    def _add_anti_fingerprint_headers(self):
        """Ajoute des headers pour éviter le fingerprinting"""
        # Headers variables pour éviter la détection
        viewport_widths = ['1920', '1366', '1440', '1536', '1280']
        viewport_heights = ['1080', '768', '900', '864', '720']
        
        # Simuler différentes résolutions d'écran
        if random.random() < 0.2:  # 20% de chance
            width = random.choice(viewport_widths)
            height = random.choice(viewport_heights)
            self.session.headers.update({
                'Viewport-Width': width,
                'Device-Memory': str(random.choice([4, 8, 16])),
                'Downlink': str(random.uniform(1.5, 10.0))
            })
        
        # Varier Accept-Language parfois
        if random.random() < 0.1:  # 10% de chance
            languages = [
                'fr-FR,fr;q=0.9,en;q=0.8',
                'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
                'fr,fr-FR;q=0.9,en;q=0.8'
            ]
            self.session.headers.update({'Accept-Language': random.choice(languages)})
        
        self.placeholder_patterns = [
            'placeholder',
            'no-image',
            'default-image',
            'image-missing',
            'coming-soon',
            'awaiting-image',
            'blank.jpg',
            'blank.png',
            'empty.jpg',
            'empty.png',
            '/assets/images/default/',
            'default/1140x380',
            'default/1368x456'
        ]
    
    def check_images(self, url):
        result = {
            'url': url,
            'status': 'success',
            'images_found': 0,
            'images': [],
            'has_placeholder': False,
            'placeholder_count': 0,
            'error': None,
            'title': ''
        }
        
        try:
            response = self._make_stealth_request(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'lxml')
            
            title_tag = soup.find('title')
            if title_tag:
                result['title'] = title_tag.text.strip()
            
            # Rechercher d'abord les images dans la headband galerie
            headband_images = []
            headband_grid = soup.find('div', class_='headbandRanking-grid')
            if headband_grid:
                headband_images = headband_grid.find_all('img', class_='headbandRanking-img')
            
            # Si pas d'images headband, utiliser la méthode standard
            if headband_images:
                main_images = headband_images
            else:
                images = soup.find_all('img')
                main_images = []
                for img in images:
                    if self._is_main_image(img):
                        main_images.append(img)
                
                if not main_images:
                    main_images = images
            
            for img in main_images:
                img_src = img.get('src', '')
                img_data_src = img.get('data-src', '')
                img_lazy_src = img.get('data-lazy-src', '')
                
                src_to_check = img_src or img_data_src or img_lazy_src
                
                if src_to_check:
                    absolute_url = urljoin(url, src_to_check)
                    is_placeholder = self._is_placeholder(absolute_url, img)
                    
                    img_data = {
                        'src': absolute_url,
                        'alt': img.get('alt', ''),
                        'is_valid': self._check_image_validity(absolute_url),
                        'is_placeholder': is_placeholder,
                        'class': img.get('class', [])
                    }
                    result['images'].append(img_data)
                    
                    if is_placeholder:
                        result['has_placeholder'] = True
                        result['placeholder_count'] += 1
            
            result['images_found'] = len(result['images'])
            
            if result['images_found'] == 0:
                result['status'] = 'warning'
                result['error'] = 'Aucune image trouvée sur cette page'
            elif result['has_placeholder']:
                result['status'] = 'warning'
            
        except Exception as e:
            print(f"❌ Erreur vérification {url}: {str(e)}")
            result['status'] = 'error'
            result['error'] = f'Erreur inattendue: {str(e)}'
        
        # Délai géré automatiquement par _make_stealth_request()
        
        return result
    
    def _is_main_image(self, img):
        classes = ' '.join(img.get('class', []))
        parent_classes = ''
        if img.parent:
            parent_classes = ' '.join(img.parent.get('class', []))
        
        main_indicators = [
            'hero', 'main', 'featured', 'property', 'residence',
            'carousel', 'gallery', 'accommodation', 'header',
            'headband-img', 'headband', 'headbandranking'
        ]
        
        for indicator in main_indicators:
            if indicator in classes.lower() or indicator in parent_classes.lower():
                return True
        
        return False
    
    def _is_placeholder(self, img_url, img_tag):
        url_lower = img_url.lower()
        for pattern in self.placeholder_patterns:
            if pattern in url_lower:
                return True
        
        alt_text = img_tag.get('alt', '').lower()
        for pattern in self.placeholder_patterns:
            if pattern in alt_text:
                return True
        
        classes = ' '.join(img_tag.get('class', [])).lower()
        if 'placeholder' in classes or 'default' in classes:
            return True
        
        return False
    
    def _check_image_validity(self, img_url):
        try:
            if img_url.startswith('data:'):
                return True
            
            response = self._make_stealth_request(img_url, method='HEAD', timeout=5, allow_redirects=True)
            return response.status_code == 200
        except:
            return False
    
    def crawl_catalog_destinations(self, catalog_url='https://www.pierreetvacances.com/fr-fr/catalog', max_links=500):
        destinations = []
        
        try:
            print(f"Récupération du catalogue depuis : {catalog_url}")
            response = self._make_stealth_request(catalog_url, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'lxml')
            
            destination_links = soup.find_all('a', href=True)
            
            for link in destination_links:
                href = link.get('href', '')
                
                if self._is_destination_url(href):
                    absolute_url = urljoin(catalog_url, href)
                    
                    destination_name = link.text.strip()
                    if not destination_name:
                        destination_name = link.get('title', '').strip()
                    
                    if absolute_url not in [d['url'] for d in destinations]:
                        destinations.append({
                            'url': absolute_url,
                            'name': destination_name
                        })
                        
                        if len(destinations) >= max_links:
                            break
            
            print(f"Trouvé {len(destinations)} destinations")
            
        except Exception as e:
            print(f"Erreur lors de la récupération du catalogue: {e}")
        
        return destinations
    
    def _is_destination_url(self, url):
        destination_patterns = [
            '/fp_',
            '/residence-',
            '/residences/',
            '/location-vacances/',
            '/sejour/',
            '/destination/',
            '/france/',
            '/espagne/',
            '/italie/',
            '/belgique/',
            '/pays-bas/',
            '/allemagne/'
        ]
        
        url_lower = url.lower()
        
        if not url_lower.startswith(('http', '/')):
            return False
        
        return any(pattern in url_lower for pattern in destination_patterns)
    
    def get_all_destinations_from_sitemap(self):
        sitemap_urls = [
            'https://www.pierreetvacances.com/sitemap.xml',
            'https://www.pierreetvacances.com/fr-fr/sitemap.xml'
        ]
        
        destinations = []
        
        for sitemap_url in sitemap_urls:
            try:
                response = self._make_stealth_request(sitemap_url, timeout=10)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'xml')
                    
                    for loc in soup.find_all('loc'):
                        url = loc.text
                        if self._is_destination_url(url):
                            destinations.append({
                                'url': url,
                                'name': self._extract_name_from_url(url)
                            })
            except:
                pass
        
        return destinations
    
    def _extract_name_from_url(self, url):
        parts = url.split('/')
        name = parts[-1] if parts[-1] else parts[-2]
        
        name = name.replace('-', ' ').replace('_', ' ')
        
        if name.startswith('fp '):
            name = name[3:]
        
        return name.title()
    
    def extract_emails(self, url):
        """Extract email addresses from a webpage"""
        try:
            response = self._make_stealth_request(url, timeout=10)
            response.raise_for_status()
            
            # Email regex pattern
            email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
            
            # Extract from HTML content
            emails = set(re.findall(email_pattern, response.text))
            
            # Also check for emails in links (mailto:)
            soup = BeautifulSoup(response.content, 'lxml')
            mailto_links = soup.find_all('a', href=lambda x: x and x.startswith('mailto:'))
            for link in mailto_links:
                email = link.get('href').replace('mailto:', '').split('?')[0]
                if re.match(email_pattern, email):
                    emails.add(email)
            
            return {
                'url': url,
                'emails': list(emails),
                'count': len(emails)
            }
            
        except Exception as e:
            return {
                'url': url,
                'emails': [],
                'count': 0,
                'error': str(e)
            }
    
    def extract_phone_numbers(self, url):
        """Extract phone numbers from a webpage"""
        try:
            response = self._make_stealth_request(url, timeout=10)
            response.raise_for_status()
            
            # Phone number regex patterns (French and international formats)
            phone_patterns = [
                r'\b(?:\+33|0)[1-9](?:[0-9]{8})\b',  # French format
                r'\b\+?1?[-.\s]?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b',  # US format
                r'\b\+[1-9]\d{1,14}\b',  # International format
                r'\b0[1-9](?:[-.\s]?[0-9]{2}){4}\b',  # French with separators
                r'\b(?:\+33\s?|0)[1-9](?:[-.\s]?[0-9]{2}){4}\b'  # French variations
            ]
            
            phones = set()
            for pattern in phone_patterns:
                matches = re.findall(pattern, response.text)
                phones.update(matches)
            
            # Also check for tel: links
            soup = BeautifulSoup(response.content, 'lxml')
            tel_links = soup.find_all('a', href=lambda x: x and x.startswith('tel:'))
            for link in tel_links:
                phone = link.get('href').replace('tel:', '').strip()
                phones.add(phone)
            
            return {
                'url': url,
                'phones': list(phones),
                'count': len(phones)
            }
            
        except Exception as e:
            return {
                'url': url,
                'phones': [],
                'count': 0,
                'error': str(e)
            }
    
    def extract_images(self, url):
        """Extract all images from a webpage with detailed information"""
        try:
            response = self._make_stealth_request(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'lxml')
            images = []
            
            for img in soup.find_all('img'):
                src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                if src:
                    absolute_url = urljoin(url, src)
                    
                    image_data = {
                        'src': absolute_url,
                        'alt': img.get('alt', ''),
                        'title': img.get('title', ''),
                        'width': img.get('width'),
                        'height': img.get('height'),
                        'class': img.get('class', []),
                        'is_placeholder': self._is_placeholder(absolute_url, img)
                    }
                    images.append(image_data)
            
            return {
                'url': url,
                'images': images,
                'count': len(images)
            }
            
        except Exception as e:
            return {
                'url': url,
                'images': [],
                'count': 0,
                'error': str(e)
            }
    
    def extract_links(self, url):
        """Extract all links from a webpage"""
        try:
            response = self._make_stealth_request(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'lxml')
            links = []
            
            for link in soup.find_all('a', href=True):
                href = link.get('href')
                absolute_url = urljoin(url, href)
                
                # Parse URL to get domain
                parsed_url = urlparse(absolute_url)
                is_external = parsed_url.netloc != urlparse(url).netloc
                
                link_data = {
                    'url': absolute_url,
                    'text': link.get_text().strip(),
                    'title': link.get('title', ''),
                    'is_external': is_external,
                    'domain': parsed_url.netloc,
                    'scheme': parsed_url.scheme
                }
                links.append(link_data)
            
            # Count internal vs external links
            internal_links = [l for l in links if not l['is_external']]
            external_links = [l for l in links if l['is_external']]
            
            return {
                'url': url,
                'links': links,
                'total_count': len(links),
                'internal_count': len(internal_links),
                'external_count': len(external_links),
                'internal_links': internal_links,
                'external_links': external_links
            }
            
        except Exception as e:
            return {
                'url': url,
                'links': [],
                'total_count': 0,
                'internal_count': 0,
                'external_count': 0,
                'internal_links': [],
                'external_links': [],
                'error': str(e)
            }
    
    def extract_all_data(self, url):
        """Extract emails, phone numbers, images, and links from a webpage"""
        return {
            'url': url,
            'emails': self.extract_emails(url),
            'phones': self.extract_phone_numbers(url),
            'images': self.extract_images(url),
            'links': self.extract_links(url)
        }