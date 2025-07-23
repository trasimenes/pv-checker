import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time
import json
import re
import gzip
from database import DestinationDB

class PVCatalogScraper:
    def __init__(self, progress_callback=None):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        self.db = DestinationDB()
        self.base_url = 'https://www.pierreetvacances.com'
        self.progress_callback = progress_callback
        
        # Country mapping from URL patterns and content
        self.country_mapping = {
            '/fr-fr/': 'FR',
            '/fr-be/': 'BE', 
            '/fr-ch/': 'CH',
            '/es-es/': 'ES',
            '/it-it/': 'IT',
            '/de-de/': 'DE',
            '/nl-nl/': 'NL',
            '/pt-pt/': 'PT'
        }
        
        # Country mapping by destination names and regions
        self.region_country_mapping = {
            # France et régions
            'alsace': 'FR', 'alsace-lorraine': 'FR', 'lorraine': 'FR', 
            'centre': 'FR', 'bretagne': 'FR', 'corse': 'FR', 
            'mediterranee': 'FR', 'cote-azur': 'FR', 'cote-d-azur': 'FR',
            'nord': 'FR', 'nord-picardie': 'FR', 'picardie': 'FR', 
            'normandie': 'FR', 'pays-de-la-loire': 'FR', 'loire': 'FR',
            'poitou': 'FR', 'poitou-charentes': 'FR', 'charentes': 'FR',
            'sud-ouest': 'FR', 'alpes': 'FR', 'pyrenees': 'FR', 
            'pyrenees-andorre': 'FR', 'rhone-alpes': 'FR', 'france': 'FR',
            
            # Espagne et régions
            'andalousie': 'ES', 'baleares': 'ES', 'catalogne': 'ES', 
            'communaute-valencienne': 'ES', 'valencienne': 'ES',
            'iles-canaries': 'ES', 'canaries': 'ES', 
            'communaute-de-madrid': 'ES', 'madrid': 'ES', 'espagne': 'ES',
            
            # Grèce et régions
            'crete': 'GR', 'santorin': 'GR', 'grece': 'GR',
            
            # Italie et régions
            'ligurie': 'IT', 'piemont': 'IT', 'pouilles': 'IT', 'sardaigne': 'IT',
            'sicile': 'IT', 'toscane': 'IT', 'venetie': 'IT', 'campanie': 'IT',
            'lombardie': 'IT', 'italie': 'IT',
            
            # Malte
            'malte': 'MT', 'ile-de-malte': 'MT',
            
            # Maurice
            'maurice': 'MU', 'ile-maurice': 'MU',
            
            # Portugal et régions
            'algarve': 'PT', 'madere': 'PT', 'lisbonne': 'PT', 
            'region-de-lisbonne': 'PT', 'region-du-nord': 'PT', 
            'obidos': 'PT', 'portugal': 'PT',
            
            # Réunion
            'saint-paul': 'RE', 'saint-pierre': 'RE', 'reunion': 'RE',
            
            # Andorre
            'andorre': 'AD', 'principaute-andorre': 'AD', 'principaute-d-andorre': 'AD',
            
            # Antilles
            'antilles': 'GP', 'guadeloupe': 'GP', 'martinique': 'MQ',
            
            # Lieux touristiques et zones côtières Espagne
            'costa-de-almeria': 'ES', 'almeria': 'ES',
            'costa-del-sol': 'ES', 'sol': 'ES',
            'majorque': 'ES', 'mallorca': 'ES',
            'costa-brava': 'ES', 'brava': 'ES',
            'costa-dorada': 'ES', 'dorada': 'ES',
            'costa-del-azahar': 'ES', 'azahar': 'ES',
            'costa-blanca': 'ES', 'blanca': 'ES',
            
            # Lieux touristiques France côtiers
            'finistere': 'FR', 'languedoc-roussillon': 'FR', 'languedoc': 'FR', 'roussillon': 'FR',
            'var': 'FR', 'ardeche': 'FR',
            'baie-de-somme': 'FR', 'somme': 'FR', 'cote-opale': 'FR', 'opale': 'FR',
            'cote-normande': 'FR', 'normande': 'FR',
            'vendee': 'FR', 'loire-atlantique': 'FR', 'atlantique': 'FR',
            'pays-basque': 'FR', 'basque': 'FR',
            'landes': 'FR', 'bordeaux': 'FR', 'arcachon': 'FR', 'bordeaux-arcachon': 'FR',
            'provence': 'FR', 'morbihan': 'FR',
            
            # Lieux touristiques Portugal
            'faro': 'PT',
            
            # Domaines skiables France
            'grandvalira': 'AD', 'paradiski': 'FR', 'avoriaz': 'FR', 'portes-du-soleil': 'FR',
            'chamonix': 'FR', 'mont-blanc': 'FR', 'chamonix-mont-blanc': 'FR',
            'grand-massif': 'FR', 'massif': 'FR',
            'domaine-blanc': 'FR', 'grand-domaine-ski': 'FR',
            'trois-vallees': 'FR', 'vallees': 'FR',
            'praz-de-lys': 'FR', 'sommand': 'FR', 'praz-de-lys-sommand': 'FR',
            'serre-chevalier': 'FR', 'serre-chevalier-vallee': 'FR',
            'val-isere': 'FR', 'tignes': 'FR', 'val-isere-tignes': 'FR',
            'galibier': 'FR', 'thabor': 'FR', 'galibier-thabor': 'FR',
            'foret-blanche': 'FR', 'la-foret-blanche': 'FR',
            'ax-trois-domaines': 'FR', 'ax': 'FR',
            'font-romeu': 'FR', 'pyrenees-2000': 'FR', 'font-romeu-pyrenees-2000': 'FR',
            'tourmalet': 'FR', 'bareges': 'FR', 'la-mongie': 'FR', 'tourmalet-bareges-la-mongie': 'FR',
            'saint-lary': 'FR', 'soulan': 'FR', 'saint-lary-soulan': 'FR',
            'le-grand-domaine': 'FR', 'grand-domaine': 'FR'
        }
        
        # Destination type patterns
        self.type_patterns = {
            'residence': ['residence', 'residences'],
            'hotel': ['hotel', 'hotels'],
            'villa': ['villa', 'villas', 'maison'],
            'appartement': ['appartement', 'appartements', 'appart'],
            'camping': ['camping', 'campings'],
            'resort': ['resort', 'resorts']
        }
        
        # Category patterns for content classification (will be loaded from database)
        self.category_patterns = self._load_category_patterns()
        
        # Progress tracking
        self.current_progress = 0
        self.current_status = "Initialisation"
    
    def _load_category_patterns(self):
        """Charge les patterns de catégories depuis la base de données"""
        try:
            patterns = self.db.get_category_patterns()
            print(f"📋 Patterns de catégories chargés: {sum(len(p) for p in patterns.values())} mots-clés")
            return patterns
        except Exception as e:
            print(f"⚠️ Erreur chargement patterns, utilisation des patterns par défaut: {e}")
            # Fallback sur les patterns par défaut
            return {
                'offre': ['last-minute', 'minute', 'promo', 'offre', 'voyage', 'special'],
                'editorial': ['a-voir-a-faire', 'voir-faire', 'guide', 'activite', 'culture', 'sortie'],
                'sejour': ['sejour', 'weekend', 'package', 'formule'],
                'destination': []  # default category
            }
    
    def scrape_full_catalog(self, max_pages=50):
        """Scrape complet du catalogue P&V avec progress callback"""
        print("🚀 Démarrage du scraping complet du catalogue Pierre & Vacances...")
        
        destinations = []
        session_id = self._start_scraping_session()
        
        try:
            total_steps = 7
            current_step = 0
            
            def update_progress(step_name, step_progress=0):
                nonlocal current_step
                if step_progress == 0:
                    current_step += 1
                
                overall_progress = ((current_step - 1) / total_steps) * 100 + (step_progress / total_steps)
                self.current_progress = int(overall_progress)
                self.current_status = step_name
                
                if self.progress_callback:
                    self.progress_callback(self.current_progress, step_name)
                print(f"📊 {self.current_progress}% - {step_name}")
            
            # Étape 1: Pages principales du catalogue
            update_progress("Scraping des pages principales du catalogue")
            catalog_urls = [
                'https://www.pierreetvacances.com/fr-fr/catalog',
                'https://www.pierreetvacances.com/fr-fr/sejours',
                'https://www.pierreetvacances.com/fr-fr/residences',
                'https://www.pierreetvacances.com/fr-fr/location-vacances'
            ]
            
            for i, catalog_url in enumerate(catalog_urls):
                print(f"📋 Scraping: {catalog_url}")
                destinations.extend(self._scrape_catalog_page(catalog_url))
                update_progress(f"Catalogue {i+1}/{len(catalog_urls)}", (i+1)/len(catalog_urls) * 100)
                time.sleep(1)
            
            # Étape 2: Sitemaps XML GZ (principal)
            update_progress("Scraping des sitemaps XML.gz")
            sitemap_destinations = self._scrape_sitemaps()
            destinations.extend(sitemap_destinations)
            
            # Étape 3: Pages de pays spécifiques (complément)
            update_progress("Scraping des pages par pays (complément)")
            country_pages = self._get_country_pages()
            for i, country_page in enumerate(country_pages):
                print(f"🌍 Scraping page pays: {country_page}")
                destinations.extend(self._scrape_country_page(country_page))
                update_progress(f"Pays {i+1}/{len(country_pages)}", (i+1)/len(country_pages) * 100)
                time.sleep(1)
            
            # Étape 4: Dédoublonnage
            update_progress("Dédoublonnage des destinations")
            unique_destinations = self._deduplicate_destinations(destinations)
            print(f"📊 {len(destinations)} -> {len(unique_destinations)} après dédoublonnage")
            
            # Étape 5: Sauvegarde en base
            update_progress("Sauvegarde des destinations en base de données")
            saved_count = self._save_destinations_to_db(unique_destinations)
            
            # Étape 6: Finalisation
            update_progress("Finalisation du scraping")
            self._end_scraping_session(session_id, len(unique_destinations), saved_count)
            
            # Étape 7: Terminé
            final_message = f"Scraping terminé: {len(unique_destinations)} destinations trouvées, {saved_count} sauvegardées"
            update_progress(final_message)
            print(f"✅ {final_message}")
            
            return unique_destinations
            
        except Exception as e:
            error_msg = f"Erreur: {str(e)}"
            self._end_scraping_session(session_id, 0, 0, error_msg)
            if self.progress_callback:
                self.progress_callback(100, error_msg)
            print(f"❌ {error_msg}")
            raise e
    
    def _scrape_catalog_page(self, url):
        """Scrape une page de catalogue"""
        destinations = []
        
        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'lxml')
            
            # Chercher tous les liens vers des destinations
            destination_links = soup.find_all('a', href=True)
            print(f"📊 Page {url}: {len(destination_links)} liens trouvés au total")
            
            valid_destinations = 0
            for link in destination_links:
                href = link.get('href', '')
                if self._is_destination_link(href):
                    destination = self._extract_destination_info(link, href, url)
                    if destination:
                        destinations.append(destination)
                        valid_destinations += 1
            
            print(f"✅ Page {url}: {valid_destinations} destinations valides extraites sur {len(destination_links)} liens")
            
            # Chercher la pagination
            next_pages = self._find_pagination_links(soup, url)
            for next_page in next_pages[:5]:  # Limiter à 5 pages par section
                print(f"  📄 Page suivante: {next_page}")
                destinations.extend(self._scrape_catalog_page(next_page))
                time.sleep(0.5)
                
        except Exception as e:
            print(f"❌ Erreur lors du scraping de {url}: {e}")
        
        return destinations
    
    def _scrape_country_page(self, url):
        """Scrape une page spécifique d'un pays"""
        destinations = []
        
        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'lxml')
            
            # Chercher les destinations dans différentes structures
            selectors = [
                'a[href*="/fp_"]',
                'a[href*="/residence"]',
                'a[href*="/location-"]',
                'a[href*="/sejour"]',
                '.destination-card a',
                '.property-card a',
                '.accommodation-item a'
            ]
            
            for selector in selectors:
                links = soup.select(selector)
                for link in links:
                    href = link.get('href', '')
                    if self._is_destination_link(href):
                        destination = self._extract_destination_info(link, href, url)
                        if destination:
                            destinations.append(destination)
                            
        except Exception as e:
            print(f"❌ Erreur lors du scraping de {url}: {e}")
        
        return destinations
    
    def _scrape_sitemaps(self):
        """Scrape les sitemaps XML GZ pour plus de couverture"""
        destinations = []
        
        # URL du sitemap des destinations uniquement
        sitemap_gz_urls = [
            'https://www.pierreetvacances.com/sitemap.destination.xml.gz'
        ]
        
        for sitemap_url in sitemap_gz_urls:
            try:
                print(f"🗺️ Scraping sitemap GZ: {sitemap_url}")
                response = self.session.get(sitemap_url, timeout=15)
                
                if response.status_code == 200:
                    # Décompresser le contenu GZ
                    decompressed_content = gzip.decompress(response.content)
                    
                    # Parser le XML décompressé
                    soup = BeautifulSoup(decompressed_content, 'xml')
                    
                    url_count = 0
                    for loc in soup.find_all('loc'):
                        url = loc.text.strip()
                        if self._is_destination_link(url):
                            destination = self._create_destination_from_url(url)
                            if destination:
                                destinations.append(destination)
                                url_count += 1
                    
                    print(f"✅ Sitemap {sitemap_url}: {url_count} destinations valides extraites")
                                
            except Exception as e:
                print(f"❌ Erreur sitemap {sitemap_url}: {e}")
        
        print(f"📊 Total sitemaps: {len(destinations)} destinations trouvées")
        return destinations
    
    def _is_destination_link(self, url):
        """Vérifie si l'URL est une destination valide P&V"""
        if not url:
            return False
        
        # Patterns d'URLs de destinations Pierre & Vacances
        destination_patterns = [
            r'/fp_[A-Z0-9]+_[a-zA-Z0-9\-_]+',  # Destinations individuelles ex: fp_CWL_location-residence-la-petite-venise
            r'/de_[a-zA-Z0-9\-_]+',  # Destinations par ville/région ex: de_location-houlgate
            r'/ge_[a-zA-Z0-9\-_]+',  # Pages géographiques ex: ge_location-saint-paul
            r'/zt_[a-zA-Z0-9\-_]+',  # Zones/territoires ex: zt_location-majorque
            r'/co_[a-zA-Z0-9\-_]+',  # Pages de pays
            r'/residence-[a-zA-Z0-9\-_]+',
            r'/location-[a-zA-Z0-9\-_]+',
            r'/sejour-[a-zA-Z0-9\-_]+',
            r'/appartement-[a-zA-Z0-9\-_]+',
            r'/villa-[a-zA-Z0-9\-_]+',
            r'/hotel-[a-zA-Z0-9\-_]+'
        ]
        
        # Exclusions
        exclude_patterns = [
            'javascript:', '#', 'mailto:', 'tel:',
            '/search', '/filter', '/api/', '/admin',
            '.pdf', '.jpg', '.png', '.gif',
            '/avis',  # Pages d'avis à exclure
            '/reviews',  # Pages d'avis en anglais
            '/contact',  # Pages de contact
            '/info',  # Pages d'information
            '/booking',  # Pages de réservation
            '/reservation'  # Pages de réservation
        ]
        
        url_lower = url.lower()
        
        # Vérifier les exclusions
        if any(exclude in url_lower for exclude in exclude_patterns):
            return False
        
        # Vérifier les patterns de destinations
        return any(re.search(pattern, url_lower) for pattern in destination_patterns)
    
    def _extract_destination_info(self, link_element, url, source_url):
        """Extrait les informations d'une destination depuis un élément HTML"""
        try:
            # Construire l'URL absolue
            absolute_url = urljoin(self.base_url, url)
            
            # Extraire le nom
            name = self._extract_name_from_element(link_element)
            if not name:
                name = self._extract_name_from_url(absolute_url)
            
            # Déterminer le pays
            # Pour le scraping initial, utiliser la méthode rapide basée sur l'URL
            # L'extraction depuis la page sera faite pendant la re-classification
            country = self._determine_country(absolute_url, source_url)
            
            # Déterminer le type
            destination_type = self._determine_type(absolute_url, name)
            
            # Déterminer la catégorie
            category = self._determine_category(absolute_url, name)
            
            # Extraire région/ville si possible
            region, city = self._extract_location_info(link_element)
            
            return {
                'name': name,
                'url': absolute_url,
                'country': country,
                'region': region,
                'city': city,
                'type': destination_type,
                'category': category
            }
            
        except Exception as e:
            print(f"❌ Erreur extraction {url}: {e}")
            return None
    
    def _create_destination_from_url(self, url):
        """Crée une destination depuis une URL seule"""
        try:
            name = self._extract_name_from_url(url)
            country = self._determine_country(url)
            destination_type = self._determine_type(url, name)
            category = self._determine_category(url, name)
            
            return {
                'name': name,
                'url': url,
                'country': country,
                'region': None,
                'city': None,
                'type': destination_type,
                'category': category
            }
        except:
            return None
    
    def _extract_name_from_element(self, element):
        """Extrait le nom depuis un élément HTML"""
        # Essayer différents attributs et contenus
        for attr in ['title', 'alt', 'data-title']:
            if element.get(attr):
                return element.get(attr).strip()
        
        # Essayer le texte de l'élément
        text = element.get_text(strip=True)
        if text and len(text) > 2:
            return text
        
        # Essayer les éléments enfants
        for child in element.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'span', 'div']):
            child_text = child.get_text(strip=True)
            if child_text and len(child_text) > 2:
                return child_text
        
        return None
    
    def _extract_name_from_url(self, url):
        """Extrait le nom depuis l'URL"""
        try:
            parts = url.split('/')
            name_part = parts[-1] if parts[-1] else parts[-2]
            
            # Nettoyer le nom
            name = name_part.replace('-', ' ').replace('_', ' ')
            
            # Supprimer les préfixes
            prefixes = ['fp ', 'de ', 'co ', 'residence ', 'location ', 'sejour ', 'appartement ', 'villa ', 'hotel ']
            for prefix in prefixes:
                if name.lower().startswith(prefix):
                    name = name[len(prefix):]
            
            return name.title().strip()
            
        except:
            return "Destination inconnue"
    
    def _determine_country(self, url, source_url=None):
        """Détermine le pays depuis l'URL"""
        url_lower = url.lower()
        
        # D'abord chercher par région/nom dans l'URL (priorité)
        for region, country in self.region_country_mapping.items():
            if region in url_lower:
                return country
        
        # Ensuite chercher dans l'URL de destination (patterns de langue)
        for pattern, country in self.country_mapping.items():
            if pattern in url:
                return country
        
        # Chercher dans l'URL source
        if source_url:
            source_lower = source_url.lower()
            # D'abord par région dans l'URL source
            for region, country in self.region_country_mapping.items():
                if region in source_lower:
                    return country
            # Puis par pattern de langue
            for pattern, country in self.country_mapping.items():
                if pattern in source_url:
                    return country
        
        # Pays par défaut seulement si rien trouvé
        return 'FR'
    
    def _extract_country_from_page(self, url):
        """Extrait le pays directement depuis la page de destination"""
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'lxml')
            
            # Chercher dans le headband
            headband = soup.find('div', class_='headband-destination')
            if headband:
                country_link = headband.find('a')
                if country_link:
                    # Essayer d'abord le title
                    country_name = country_link.get('title')
                    # Si pas de title, prendre le texte
                    if not country_name:
                        country_name = country_link.get_text(strip=True)
                    
                    if country_name:
                        country_name = country_name.strip()
                        print(f"🌍 Pays extrait du headband pour {url}: '{country_name}'")
                        
                        # Mapper le nom du pays vers le code
                        country_mapping = {
                            'France': 'FR', 'Espagne': 'ES', 'Italie': 'IT', 
                            'Grèce': 'GR', 'Portugal': 'PT', 'Malte': 'MT',
                            'Maurice': 'MU', 'Réunion': 'RE', 'Andorre': 'AD',
                            'Guadeloupe': 'GP', 'Martinique': 'MQ',
                            'Belgique': 'BE', 'Pays-Bas': 'NL', 'Allemagne': 'DE',
                            'Autriche': 'AT', 'Suisse': 'CH'
                        }
                        return country_mapping.get(country_name, 'FR')
            
            # Fallback 1: chercher dans residenceHeader pour les résidences fp_*
            residence_header = soup.find('div', class_='residenceHeader')
            if residence_header:
                # Chercher dans l'adresse
                address_tag = residence_header.find('address')
                if address_tag:
                    address_text = address_tag.get_text(strip=True)
                    print(f"🏠 Adresse trouvée dans residenceHeader pour {url}: '{address_text}'")
                    
                    # Chercher le pays dans l'adresse
                    address_lower = address_text.lower()
                    if 'espagne' in address_lower or 'españa' in address_lower:
                        print(f"🇪🇸 Pays détecté depuis l'adresse: Espagne")
                        return 'ES'
                    elif 'france' in address_lower:
                        print(f"🇫🇷 Pays détecté depuis l'adresse: France")
                        return 'FR'
                    elif 'italie' in address_lower or 'italia' in address_lower:
                        print(f"🇮🇹 Pays détecté depuis l'adresse: Italie")
                        return 'IT'
                    elif 'grèce' in address_lower or 'greece' in address_lower:
                        print(f"🇬🇷 Pays détecté depuis l'adresse: Grèce")
                        return 'GR'
                    elif 'portugal' in address_lower:
                        print(f"🇵🇹 Pays détecté depuis l'adresse: Portugal")
                        return 'PT'
                    elif 'malte' in address_lower or 'malta' in address_lower:
                        print(f"🇲🇹 Pays détecté depuis l'adresse: Malte")
                        return 'MT'
                    elif 'maurice' in address_lower or 'mauritius' in address_lower:
                        print(f"🇲🇺 Pays détecté depuis l'adresse: Maurice")
                        return 'MU'
                    elif 'réunion' in address_lower or 'reunion' in address_lower:
                        print(f"🇷🇪 Pays détecté depuis l'adresse: Réunion")
                        return 'RE'
                    elif 'andorre' in address_lower or 'andorra' in address_lower:
                        print(f"🇦🇩 Pays détecté depuis l'adresse: Andorre")
                        return 'AD'
                    elif 'guadeloupe' in address_lower:
                        print(f"🇬🇵 Pays détecté depuis l'adresse: Guadeloupe")
                        return 'GP'
                    elif 'martinique' in address_lower:
                        print(f"🇲🇶 Pays détecté depuis l'adresse: Martinique")
                        return 'MQ'

            # Fallback 2: chercher dans breadcrumb
            breadcrumb = soup.find('nav', class_='breadcrumb')
            if breadcrumb:
                for link in breadcrumb.find_all('a'):
                    if link.get('href') and '/co_location-' in link.get('href', ''):
                        country_name = link.get_text(strip=True)
                        country_mapping = {
                            'France': 'FR', 'Espagne': 'ES', 'Italie': 'IT', 
                            'Grèce': 'GR', 'Portugal': 'PT', 'Malte': 'MT',
                            'Maurice': 'MU', 'Réunion': 'RE', 'Andorre': 'AD',
                            'Guadeloupe': 'GP', 'Martinique': 'MQ'
                        }
                        return country_mapping.get(country_name, 'FR')
                        
        except Exception as e:
            print(f"❌ Erreur extraction pays depuis {url}: {e}")
        
        # Fallback vers la méthode URL si la page n'est pas accessible
        return self._determine_country(url)
    
    def _determine_type(self, url, name):
        """Détermine le type de destination"""
        url_lower = url.lower()
        name_lower = (name or '').lower()
        
        for dest_type, patterns in self.type_patterns.items():
            if any(pattern in url_lower or pattern in name_lower for pattern in patterns):
                return dest_type
        
        return 'residence'
    
    def _determine_category(self, url, name):
        """Détermine la catégorie de contenu"""
        url_lower = url.lower()
        name_lower = (name or '').lower()
        
        # D'abord, vérifier l'URL (plus fiable)
        for category, patterns in self.category_patterns.items():
            if patterns:  # Skip empty patterns (default category)
                if any(pattern in url_lower for pattern in patterns):
                    return category
        
        # Si URL ne match pas, vérifier le nom SEULEMENT pour certains patterns fiables
        reliable_name_patterns = {
            'offre': ['last-minute', 'promo', 'special', 'voyage'],
            'sejour': ['sejour', 'weekend', 'package', 'formule']
        }
        
        for category, patterns in reliable_name_patterns.items():
            if any(pattern in name_lower for pattern in patterns):
                return category
        
        # Si l'URL contient les patterns destination classiques, c'est une destination
        destination_patterns = ['/fp_', '/residence', '/location-', '/appartement', '/villa', '/hotel']
        if any(pattern in url_lower for pattern in destination_patterns):
            return 'destination'
        
        return 'destination'  # default category
    
    def _extract_location_info(self, element):
        """Extrait les informations de localisation"""
        # Essayer de trouver région/ville dans les éléments parents/enfants
        region = None
        city = None
        
        # Chercher dans les classes CSS ou attributs data
        parent = element.parent
        if parent:
            for attr in ['data-region', 'data-city', 'data-location']:
                if parent.get(attr):
                    if attr == 'data-region':
                        region = parent.get(attr)
                    elif attr == 'data-city':
                        city = parent.get(attr)
        
        return region, city
    
    def _get_country_pages(self):
        """Récupère les URLs des pages par pays - LISTE RÉDUITE"""
        country_pages = [
            # SEULEMENT les pages principales pays (12 pages max)
            'https://www.pierreetvacances.com/fr-fr/co_location-france',
            'https://www.pierreetvacances.com/fr-fr/co_location-espagne', 
            'https://www.pierreetvacances.com/fr-fr/co_location-italie',
            'https://www.pierreetvacances.com/fr-fr/co_location-grece',
            'https://www.pierreetvacances.com/fr-fr/co_location-portugal',
            'https://www.pierreetvacances.com/fr-fr/co_location-malte',
            'https://www.pierreetvacances.com/fr-fr/co_location-maurice',
            'https://www.pierreetvacances.com/fr-fr/co_location-reunion',
            'https://www.pierreetvacances.com/fr-fr/co_location-andorre',
            'https://www.pierreetvacances.com/fr-fr/co_location-antilles',
            'https://www.pierreetvacances.com/fr-fr/co_location-guadeloupe',
            'https://www.pierreetvacances.com/fr-fr/co_location-martinique'
        ]
        return country_pages
    
    def _find_pagination_links(self, soup, current_url):
        """Trouve les liens de pagination"""
        pagination_links = []
        
        # Sélecteurs pour la pagination
        selectors = [
            'a[href*="page="]',
            '.pagination a',
            '.pager a',
            'a[rel="next"]'
        ]
        
        for selector in selectors:
            links = soup.select(selector)
            for link in links:
                href = link.get('href')
                if href and href not in pagination_links:
                    absolute_url = urljoin(current_url, href)
                    pagination_links.append(absolute_url)
        
        return pagination_links[:5]  # Limiter
    
    def _deduplicate_destinations(self, destinations):
        """Supprime les doublons basés sur l'URL"""
        seen_urls = set()
        unique_destinations = []
        
        for dest in destinations:
            if dest['url'] not in seen_urls:
                seen_urls.add(dest['url'])
                unique_destinations.append(dest)
        
        return unique_destinations
    
    def _save_destinations_to_db(self, destinations):
        """Sauvegarde les destinations en base"""
        saved_count = 0
        
        for dest in destinations:
            try:
                result = self.db.add_destination(
                    name=dest['name'],
                    url=dest['url'],
                    country=dest['country'],
                    region=dest.get('region'),
                    city=dest.get('city'),
                    destination_type=dest.get('type'),
                    category=dest.get('category'),
                    notes='Importé par scraping automatique'
                )
                if result:
                    saved_count += 1
            except Exception as e:
                print(f"❌ Erreur sauvegarde {dest['url']}: {e}")
        
        return saved_count
    
    def _start_scraping_session(self):
        """Démarre une session de scraping"""
        import sqlite3
        with sqlite3.connect(self.db.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO scraping_sessions (session_date, status)
                VALUES (CURRENT_TIMESTAMP, 'running')
            ''')
            conn.commit()
            return cursor.lastrowid
    
    def _end_scraping_session(self, session_id, urls_found, new_destinations, notes=None):
        """Termine une session de scraping"""
        import sqlite3
        with sqlite3.connect(self.db.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE scraping_sessions 
                SET urls_found=?, new_destinations=?, status='completed', notes=?
                WHERE id=?
            ''', (urls_found, new_destinations, notes, session_id))
            conn.commit()