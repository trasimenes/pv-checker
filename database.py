import sqlite3
import json
from datetime import datetime
import csv
import io

class DestinationDB:
    def __init__(self, db_path='destinations.db'):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS destinations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    url TEXT NOT NULL UNIQUE,
                    country TEXT NOT NULL,
                    region TEXT,
                    city TEXT,
                    type TEXT,
                    category TEXT DEFAULT 'destination',
                    status TEXT DEFAULT 'active',
                    last_checked DATETIME,
                    has_placeholder BOOLEAN DEFAULT 0,
                    images_count INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    notes TEXT
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS countries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    flag_icon TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS scraping_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                    urls_found INTEGER DEFAULT 0,
                    new_destinations INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'running',
                    notes TEXT
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS catalog_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    version_name TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    description TEXT,
                    total_destinations INTEGER DEFAULT 0,
                    destinations_by_country TEXT,
                    snapshot_data TEXT,
                    created_by TEXT DEFAULT 'system'
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS category_mappings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    keyword TEXT NOT NULL,
                    category TEXT NOT NULL,
                    language TEXT DEFAULT 'all',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS reclassification_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_type TEXT NOT NULL DEFAULT 'reclassification',
                    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    completed_at DATETIME,
                    duration_minutes INTEGER,
                    total_processed INTEGER DEFAULT 0,
                    total_updated INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'running',
                    threading_mode TEXT,
                    error_message TEXT,
                    notes TEXT
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS verification_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    title TEXT,
                    name TEXT,
                    country TEXT,
                    detected_category TEXT,
                    status TEXT NOT NULL,
                    has_placeholder BOOLEAN DEFAULT 0,
                    placeholder_count INTEGER DEFAULT 0,  
                    images_found INTEGER DEFAULT 0,
                    images_data TEXT,  -- JSON des images
                    scan_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                    optimization_tag TEXT,
                    similar_urls_count INTEGER DEFAULT 0,
                    is_optimized_sample BOOLEAN DEFAULT 0,
                    error_message TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(url, scan_date) -- Permet plusieurs scans pour la même URL
                )
            ''')
            
            # Ajouter la colonne category si elle n'existe pas (migration)
            cursor.execute("PRAGMA table_info(destinations)")
            columns = [column[1] for column in cursor.fetchall()]
            if 'category' not in columns:
                cursor.execute('ALTER TABLE destinations ADD COLUMN category TEXT DEFAULT "destination"')
                print("✅ Colonne 'category' ajoutée à la table destinations")
            
            # Insert default countries
            countries = [
                ('FR', 'France', 'fi-fr'),
                ('ES', 'Espagne', 'fi-es'),
                ('IT', 'Italie', 'fi-it'),
                ('GR', 'Grèce', 'fi-gr'),
                ('PT', 'Portugal', 'fi-pt'),
                ('MT', 'Malte', 'fi-mt'),
                ('MU', 'Maurice', 'fi-mu'),
                ('RE', 'Réunion', 'fi-re'),
                ('AD', 'Andorre', 'fi-ad'),
                ('GP', 'Guadeloupe', 'fi-gp'),
                ('MQ', 'Martinique', 'fi-mq'),
                ('BE', 'Belgique', 'fi-be'),
                ('NL', 'Pays-Bas', 'fi-nl'),
                ('DE', 'Allemagne', 'fi-de'),
                ('AT', 'Autriche', 'fi-at'),
                ('CH', 'Suisse', 'fi-ch')
            ]
            
            for code, name, flag in countries:
                cursor.execute('''
                    INSERT OR IGNORE INTO countries (code, name, flag_icon) 
                    VALUES (?, ?, ?)
                ''', (code, name, flag))
            
            # Insert default category mappings
            default_mappings = [
                # Offres (français)
                ('last-minute', 'offre', 'fr'),
                ('minute', 'offre', 'fr'),
                ('promo', 'offre', 'fr'),
                ('offre', 'offre', 'fr'),
                ('voyage', 'offre', 'fr'),
                ('special', 'offre', 'fr'),
                
                # Editorial (français)
                ('a-voir-a-faire', 'editorial', 'fr'),
                ('voir-faire', 'editorial', 'fr'),
                ('guide', 'editorial', 'fr'),
                ('activite', 'editorial', 'fr'),
                ('culture', 'editorial', 'fr'),
                ('sortie', 'editorial', 'fr'),
                
                # Séjours (français)
                ('sejour', 'sejour', 'fr'),
                ('weekend', 'sejour', 'fr'),
                ('package', 'sejour', 'fr'),
                ('formule', 'sejour', 'fr'),
                
                # Offres (autres langues)
                ('last-minute', 'offre', 'en'),
                ('offer', 'offre', 'en'),
                ('special', 'offre', 'en'),
                ('aanbieding', 'offre', 'nl'),
                ('angebot', 'offre', 'de'),
                ('oferta', 'offre', 'es'),
                ('offerta', 'offre', 'it'),
                
                # Editorial (autres langues)
                ('things-to-do', 'editorial', 'en'),
                ('activities', 'editorial', 'en'),
                ('te-doen', 'editorial', 'nl'),
                ('activiteiten', 'editorial', 'nl'),
                ('aktivitaten', 'editorial', 'de'),
                ('actividades', 'editorial', 'es'),
                ('attivita', 'editorial', 'it')
            ]
            
            for keyword, category, language in default_mappings:
                cursor.execute('''
                    INSERT OR IGNORE INTO category_mappings (keyword, category, language)
                    VALUES (?, ?, ?)
                ''', (keyword, category, language))
            
            conn.commit()
    
    def add_destination(self, name, url, country, region=None, city=None, destination_type=None, category=None, notes=None):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT INTO destinations (name, url, country, region, city, type, category, notes, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (name, url, country, region, city, destination_type, category or 'destination', notes))
                conn.commit()
                return cursor.lastrowid
            except sqlite3.IntegrityError:
                # URL already exists, update instead
                cursor.execute('''
                    UPDATE destinations 
                    SET name=?, country=?, region=?, city=?, type=?, category=?, notes=?, updated_at=CURRENT_TIMESTAMP
                    WHERE url=?
                ''', (name, country, region, city, destination_type, category or 'destination', notes, url))
                conn.commit()
                return None
    
    def get_destinations_by_country(self, country=None):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            if country:
                cursor.execute('''
                    SELECT d.*, c.name as country_name, c.flag_icon
                    FROM destinations d
                    LEFT JOIN countries c ON d.country = c.code
                    WHERE d.country = ?
                    ORDER BY d.name
                ''', (country,))
            else:
                cursor.execute('''
                    SELECT d.*, c.name as country_name, c.flag_icon
                    FROM destinations d
                    LEFT JOIN countries c ON d.country = c.code
                    ORDER BY d.country, d.name
                ''')
            
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def save_verification_result(self, result):
        """Sauvegarde un résultat de vérification en base"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Extraire les données images en JSON
            images_json = json.dumps(result.get('images', [])) if result.get('images') else None
            
            cursor.execute('''
                INSERT OR REPLACE INTO verification_results (
                    url, title, name, country, detected_category, status,
                    has_placeholder, placeholder_count, images_found, images_data,
                    scan_date, optimization_tag, similar_urls_count, 
                    is_optimized_sample, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                result.get('url'),
                result.get('title'),
                result.get('name'),
                result.get('country'),
                result.get('detected_category'),
                result.get('status'),
                result.get('has_placeholder', False),
                result.get('placeholder_count', 0),
                result.get('images_found', 0),
                images_json,
                result.get('scan_date'),
                result.get('optimization_tag'),
                result.get('similar_urls_count', 0),
                result.get('is_optimized_sample', False),
                result.get('error')
            ))
            
            return cursor.lastrowid
    
    def get_all_verification_results(self):
        """Récupère tous les résultats de vérification avec le dernier scan par URL"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT vr.* FROM verification_results vr
                INNER JOIN (
                    SELECT url, MAX(scan_date) as latest_scan
                    FROM verification_results
                    GROUP BY url
                ) latest ON vr.url = latest.url AND vr.scan_date = latest.latest_scan
                ORDER BY vr.scan_date DESC
            ''')
            
            columns = [desc[0] for desc in cursor.description]
            results = []
            
            for row in cursor.fetchall():
                result = dict(zip(columns, row))
                
                # Reconstituer les images depuis JSON
                if result.get('images_data'):
                    try:
                        result['images'] = json.loads(result['images_data'])
                    except:
                        result['images'] = []
                
                results.append(result)
            
            return results
    
    def get_verification_history_for_url(self, url):
        """Récupère l'historique complet des vérifications pour une URL"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM verification_results 
                WHERE url = ? 
                ORDER BY scan_date DESC
            ''', (url,))
            
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def get_unverified_destinations(self):
        """Récupère toutes les destinations qui n'ont jamais été vérifiées"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT d.* FROM destinations d
                LEFT JOIN verification_results vr ON d.url = vr.url
                WHERE vr.url IS NULL
                ORDER BY d.country, d.name
            ''')
            
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def populate_missing_verification_urls(self):
        """Peuple la table verification_results avec toutes les URLs manquantes depuis destinations"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Récupérer toutes les destinations non vérifiées
            unverified = self.get_unverified_destinations()
            
            populated_count = 0
            for dest in unverified:
                # Créer un résultat de vérification "en attente" pour chaque URL manquante
                cursor.execute('''
                    INSERT OR IGNORE INTO verification_results (
                        url, title, name, country, detected_category, status,
                        has_placeholder, placeholder_count, images_found,
                        scan_date, optimization_tag, is_optimized_sample
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    dest['url'],
                    dest['name'],  # Utiliser le nom comme titre temporaire
                    dest['name'],
                    dest['country'],
                    dest.get('category', 'destination'),
                    'pending',  # Statut en attente de vérification
                    False,      # has_placeholder
                    0,          # placeholder_count
                    0,          # images_found
                    datetime.now().isoformat(),
                    'auto_populated',  # Tag pour identifier les URLs auto-peuplées
                    False       # is_optimized_sample
                ))
                populated_count += 1
            
            conn.commit()
            return populated_count
    
    def get_verification_stats(self):
        """Statistiques détaillées sur les vérifications"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Stats générales
            cursor.execute('SELECT COUNT(*) FROM verification_results')
            total_verifications = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(DISTINCT url) FROM verification_results')
            unique_urls = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM verification_results WHERE status = "pending"')
            pending = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM verification_results WHERE status = "success"')
            success = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM verification_results WHERE status = "warning"')
            warning = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM verification_results WHERE status = "error"')
            error = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM verification_results WHERE has_placeholder = 1')
            with_placeholders = cursor.fetchone()[0]
            
            # Stats par catégorie
            cursor.execute('''
                SELECT detected_category, COUNT(*) as count
                FROM verification_results
                GROUP BY detected_category
                ORDER BY count DESC
            ''')
            by_category = dict(cursor.fetchall())
            
            # Stats par pays
            cursor.execute('''
                SELECT country, COUNT(*) as count
                FROM verification_results
                WHERE country IS NOT NULL AND country != ''
                GROUP BY country
                ORDER BY count DESC
            ''')
            by_country = dict(cursor.fetchall())
            
            return {
                'total_verifications': total_verifications,
                'unique_urls': unique_urls,
                'pending': pending,
                'success': success,
                'warning': warning,
                'error': error,
                'with_placeholders': with_placeholders,
                'success_rate': round((success / unique_urls * 100) if unique_urls > 0 else 0, 1),
                'by_category': by_category,
                'by_country': by_country
            }
    
    def get_all_countries(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT c.*, COUNT(d.id) as destination_count
                FROM countries c
                LEFT JOIN destinations d ON c.code = d.country
                GROUP BY c.code, c.name, c.flag_icon
                ORDER BY c.name
            ''')
            
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def update_destination_check_status(self, url, has_placeholder, images_count):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE destinations 
                SET has_placeholder=?, images_count=?, last_checked=CURRENT_TIMESTAMP
                WHERE url=?
            ''', (has_placeholder, images_count, url))
            conn.commit()
    
    def delete_destination(self, destination_id):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM destinations WHERE id=?', (destination_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    def delete_destinations_by_url_pattern(self, url_pattern):
        """Supprime toutes les destinations dont l'URL contient le pattern donné"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM destinations WHERE url LIKE ?', (f'%{url_pattern}%',))
            conn.commit()
            return cursor.rowcount
    
    def update_destination_country(self, destination_id, new_country):
        """Met à jour le pays d'une destination"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE destinations SET country=? WHERE id=?', (new_country, destination_id))
            conn.commit()
            return cursor.rowcount > 0
    
    def export_csv(self, country=None):
        destinations = self.get_destinations_by_country(country)
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Headers
        writer.writerow([
            'ID', 'Nom', 'URL', 'Pays', 'Région', 'Ville', 'Type', 
            'Statut', 'Dernière vérification', 'A des placeholders', 
            'Nombre d\'images', 'Créé le', 'Modifié le', 'Notes'
        ])
        
        # Data
        for dest in destinations:
            writer.writerow([
                dest['id'], dest['name'], dest['url'], dest['country_name'], 
                dest['region'], dest['city'], dest['type'], dest['status'],
                dest['last_checked'], dest['has_placeholder'], dest['images_count'],
                dest['created_at'], dest['updated_at'], dest['notes']
            ])
        
        return output.getvalue()
    
    def import_csv(self, csv_content):
        reader = csv.DictReader(io.StringIO(csv_content))
        imported_count = 0
        errors = []
        
        for row in reader:
            try:
                result = self.add_destination(
                    name=row.get('Nom', ''),
                    url=row.get('URL', ''),
                    country=row.get('Pays', ''),
                    region=row.get('Région', ''),
                    city=row.get('Ville', ''),
                    destination_type=row.get('Type', ''),
                    notes=row.get('Notes', '')
                )
                if result:
                    imported_count += 1
            except Exception as e:
                errors.append(f"Ligne {reader.line_num}: {str(e)}")
        
        return imported_count, errors
    
    def get_stats(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute('SELECT COUNT(*) FROM destinations')
            total_destinations = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM destinations WHERE last_checked IS NOT NULL')
            checked_destinations = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM destinations WHERE has_placeholder = 1')
            with_placeholders = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM destinations WHERE status = "active"')
            active_destinations = cursor.fetchone()[0]
            
            cursor.execute('''
                SELECT c.name, COUNT(d.id) as count
                FROM countries c
                LEFT JOIN destinations d ON c.code = d.country
                GROUP BY c.code, c.name
                ORDER BY count DESC
            ''')
            by_country = dict(cursor.fetchall())
            
            return {
                'total': total_destinations,
                'checked': checked_destinations,
                'with_placeholders': with_placeholders,
                'active': active_destinations,
                'by_country': by_country
            }
    
    def create_snapshot(self, version_name, description=None, created_by='system'):
        """Crée un snapshot du catalogue actuel"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Get current stats
            stats = self.get_stats()
            
            # Get all destinations
            destinations = self.get_destinations_by_country()
            
            # Create snapshot data
            snapshot_data = {
                'destinations': destinations,
                'stats': stats,
                'created_at': datetime.now().isoformat()
            }
            
            cursor.execute('''
                INSERT INTO catalog_snapshots 
                (version_name, description, total_destinations, destinations_by_country, 
                 snapshot_data, created_by)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                version_name,
                description,
                stats['total'],
                json.dumps(stats['by_country']),
                json.dumps(snapshot_data),
                created_by
            ))
            
            conn.commit()
            return cursor.lastrowid
    
    def get_snapshots(self):
        """Récupère tous les snapshots"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, version_name, created_at, description, total_destinations,
                       destinations_by_country, created_by
                FROM catalog_snapshots
                ORDER BY created_at DESC
            ''')
            
            columns = [desc[0] for desc in cursor.description]
            snapshots = []
            
            for row in cursor.fetchall():
                snapshot = dict(zip(columns, row))
                if snapshot['destinations_by_country']:
                    snapshot['destinations_by_country'] = json.loads(snapshot['destinations_by_country'])
                snapshots.append(snapshot)
            
            return snapshots
    
    def get_snapshot_data(self, snapshot_id):
        """Récupère les données complètes d'un snapshot"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT snapshot_data FROM catalog_snapshots WHERE id = ?
            ''', (snapshot_id,))
            
            result = cursor.fetchone()
            if result and result[0]:
                return json.loads(result[0])
            return None
    
    def delete_snapshot(self, snapshot_id):
        """Supprime un snapshot"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM catalog_snapshots WHERE id = ?', (snapshot_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    def export_snapshot_csv(self, snapshot_id):
        """Exporte un snapshot en CSV"""
        snapshot_data = self.get_snapshot_data(snapshot_id)
        if not snapshot_data:
            return None
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Headers
        writer.writerow([
            'ID', 'Nom', 'URL', 'Pays', 'Région', 'Ville', 'Type', 
            'Statut', 'Dernière vérification', 'A des placeholders', 
            'Nombre d\'images', 'Créé le', 'Modifié le', 'Notes'
        ])
        
        # Data from snapshot
        for dest in snapshot_data['destinations']:
            writer.writerow([
                dest['id'], dest['name'], dest['url'], dest['country_name'], 
                dest['region'], dest['city'], dest['type'], dest['status'],
                dest['last_checked'], dest['has_placeholder'], dest['images_count'],
                dest['created_at'], dest['updated_at'], dest['notes']
            ])
        
        return output.getvalue()
    
    # Category mappings methods
    def get_category_mappings(self):
        """Récupère toutes les correspondances de catégories"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, keyword, category, language, created_at, updated_at
                FROM category_mappings
                ORDER BY category, language, keyword
            ''')
            
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def add_category_mapping(self, keyword, category, language='all'):
        """Ajoute une correspondance de catégorie"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO category_mappings (keyword, category, language, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ''', (keyword, category, language))
            conn.commit()
            return cursor.lastrowid
    
    def update_category_mapping(self, mapping_id, keyword, category, language='all'):
        """Met à jour une correspondance de catégorie"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE category_mappings 
                SET keyword=?, category=?, language=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
            ''', (keyword, category, language, mapping_id))
            conn.commit()
            return cursor.rowcount > 0
    
    def delete_category_mapping(self, mapping_id):
        """Supprime une correspondance de catégorie"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM category_mappings WHERE id=?', (mapping_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    def get_category_patterns(self):
        """Récupère les patterns de catégories depuis la base"""
        mappings = self.get_category_mappings()
        patterns = {
            'offre': [],
            'editorial': [],
            'sejour': [],
            'destination': []
        }
        
        for mapping in mappings:
            category = mapping['category']
            if category in patterns:
                patterns[category].append(mapping['keyword'])
        
        return patterns
    
    # Reclassification sessions methods
    def create_reclassification_session(self, session_type='reclassification', threading_mode=None, notes=None):
        """Crée une nouvelle session de reclassification"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO reclassification_sessions 
                (session_type, threading_mode, notes)
                VALUES (?, ?, ?)
            ''', (session_type, threading_mode, notes))
            conn.commit()
            return cursor.lastrowid
    
    def update_reclassification_session(self, session_id, **kwargs):
        """Met à jour une session de reclassification"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Construire la requête dynamiquement
            updates = []
            values = []
            
            for key, value in kwargs.items():
                if key in ['completed_at', 'duration_minutes', 'total_processed', 'total_updated', 'status', 'error_message', 'notes']:
                    updates.append(f"{key}=?")
                    values.append(value)
            
            if updates:
                query = f"UPDATE reclassification_sessions SET {', '.join(updates)} WHERE id=?"
                values.append(session_id)
                cursor.execute(query, values)
                conn.commit()
                return cursor.rowcount > 0
            return False
    
    def get_reclassification_sessions(self, limit=20):
        """Récupère l'historique des sessions de reclassification"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, session_type, started_at, completed_at, duration_minutes,
                       total_processed, total_updated, status, threading_mode, notes
                FROM reclassification_sessions
                ORDER BY started_at DESC
                LIMIT ?
            ''', (limit,))
            
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def export_all_destinations_json(self, filename='destinations_export.json'):
        """Exporte toutes les destinations en JSON pour traitement offline"""
        import json
        from datetime import datetime
        
        destinations = self.get_destinations_by_country()
        
        export_data = {
            'export_date': datetime.now().isoformat(),
            'total_destinations': len(destinations),
            'destinations': destinations,
            'metadata': {
                'categories': list(set(d.get('category', 'destination') for d in destinations)),
                'countries': list(set(d.get('country', 'Unknown') for d in destinations)),
                'languages': list(set(d['url'].split('/')[3] for d in destinations if len(d['url'].split('/')) > 3))
            }
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        
        return filename, len(destinations)