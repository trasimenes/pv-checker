from flask import Flask, render_template, jsonify, request, send_file, Response, redirect, url_for, session, flash
from crawler import ImageChecker
from database import DestinationDB
from catalog_scraper import PVCatalogScraper
import threading
import json
import os
import io
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from datetime import datetime
import requests
from PIL import Image
import hashlib
from urllib.parse import urlparse
import uuid
from datetime import datetime
import glob

app = Flask(__name__)

# Configuration d'authentification (à adapter selon vos besoins de sécurité)
try:
    from auth_config import LOGIN_USERNAME, LOGIN_PASSWORD, SECRET_KEY
    app.secret_key = SECRET_KEY
except ImportError:
    # Valeurs par défaut pour le développement (à changer en production)
    LOGIN_USERNAME = 'admin'
    LOGIN_PASSWORD = 'admin'
    app.secret_key = 'dev-secret-key-change-in-production'

image_checker = ImageChecker()
db = DestinationDB()
scraper = PVCatalogScraper()

# Gestionnaire de tâches global
class TaskManager:
    def __init__(self):
        self.tasks = {}
    
    def create_task(self, task_type, description, total_items=0):
        task_id = str(uuid.uuid4())
        task = {
            'id': task_id,
            'type': task_type,
            'description': description,
            'status': 'running',
            'progress': 0,
            'total': total_items,
            'current_item': None,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'error': None,
            'results': [],
            'can_stop': True
        }
        self.tasks[task_id] = task
        print(f"🚀 Tâche créée: {task_type} - {description} (ID: {task_id})")
        return task_id
    
    def update_task(self, task_id, **kwargs):
        if task_id in self.tasks:
            self.tasks[task_id].update(kwargs)
            self.tasks[task_id]['updated_at'] = datetime.now().isoformat()
    
    def complete_task(self, task_id, success=True, error=None):
        if task_id in self.tasks:
            self.tasks[task_id]['status'] = 'completed' if success else 'error'
            self.tasks[task_id]['updated_at'] = datetime.now().isoformat()
            if error:
                self.tasks[task_id]['error'] = str(error)
            print(f"✅ Tâche terminée: {task_id} - {self.tasks[task_id]['description']}")
    
    def stop_task(self, task_id):
        if task_id in self.tasks and self.tasks[task_id]['can_stop']:
            self.tasks[task_id]['status'] = 'stopped'
            self.tasks[task_id]['updated_at'] = datetime.now().isoformat()
            print(f"⏹️ Tâche arrêtée: {task_id}")
            return True
        return False
    
    def get_all_tasks(self):
        return list(self.tasks.values())
    
    def get_task(self, task_id):
        return self.tasks.get(task_id)
    
    def is_task_running(self, task_id):
        task = self.tasks.get(task_id)
        return task and task['status'] == 'running'
    
    def cleanup_old_tasks(self, max_age_hours=24):
        """Nettoie les tâches anciennes"""
        cutoff = datetime.now().timestamp() - (max_age_hours * 3600)
        to_remove = []
        
        for task_id, task in self.tasks.items():
            task_time = datetime.fromisoformat(task['created_at']).timestamp()
            if task_time < cutoff and task['status'] in ['completed', 'error', 'stopped']:
                to_remove.append(task_id)
        
        for task_id in to_remove:
            del self.tasks[task_id]
            
        if to_remove:
            print(f"🧹 {len(to_remove)} tâches anciennes nettoyées")

# Instance globale du gestionnaire de tâches
task_manager = TaskManager()

check_status = {
    'is_running': False,
    'progress': 0,
    'total': 0,
    'results': [],
    'current_url': None
}

def save_scan_with_timestamp(results):
    """Sauvegarde les résultats avec un timestamp"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'historique_scans/scan_{timestamp}.json'
    
    scan_data = {
        'timestamp': datetime.now().isoformat(),
        'date': datetime.now().strftime('%Y-%m-%d'),
        'time': datetime.now().strftime('%H:%M:%S'),
        'total_destinations': len(results),
        'results': results
    }
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(scan_data, f, indent=2, ensure_ascii=False)
    
    print(f"📁 Scan sauvegardé: {filename}")

scraping_status = {
    'is_running': False,
    'progress': 0,
    'total': 0,
    'destinations_found': 0,
    'progress_percent': 0
}

reclassify_status = {
    'is_running': False,
    'progress': 0,
    'total': 0,
    'updated_count': 0,
    'progress_percent': 0,
    'current_status': 'Initialisation...',
    'current_url': None
}

def login_required(f):
    """Décorateur pour protéger les routes avec authentification"""
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if username == LOGIN_USERNAME and password == LOGIN_PASSWORD:
            session['logged_in'] = True
            session['username'] = username
            return redirect(url_for('index'))
        else:
            flash('Nom d\'utilisateur ou mot de passe incorrect')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/consolidator')
@login_required
def consolidator():
    return render_template('consolidator.html')


@app.route('/settings')
@login_required
def settings():
    return render_template('settings.html')

@app.route('/tasks')
@login_required
def tasks():
    return render_template('tasks.html')

@app.route('/historique')
@login_required
def historique():
    return render_template('historique.html')

# API Routes pour la gestion des tâches
@app.route('/api/tasks')
@login_required
def get_all_tasks():
    """Récupère toutes les tâches"""
    task_manager.cleanup_old_tasks()  # Nettoyage automatique
    return jsonify(task_manager.get_all_tasks())

@app.route('/api/tasks/<task_id>')
@login_required
def get_task(task_id):
    """Récupère une tâche spécifique"""
    task = task_manager.get_task(task_id)
    if task:
        return jsonify(task)
    return jsonify({'error': 'Tâche non trouvée'}), 404

@app.route('/api/tasks/<task_id>/stop', methods=['POST'])
@login_required
def stop_task(task_id):
    """Arrête une tâche"""
    success = task_manager.stop_task(task_id)
    if success:
        return jsonify({'success': True, 'message': 'Tâche arrêtée'})
    return jsonify({'success': False, 'error': 'Impossible d\'arrêter cette tâche'}), 400

@app.route('/api/check-from-database', methods=['POST'])
@login_required
def start_check_from_database():
    global check_status
    
    if check_status['is_running']:
        return jsonify({'error': 'Une vérification est déjà en cours'}), 400
    
    data = request.get_json()
    scope = data.get('scope', 'all')
    country = data.get('country')
    category = data.get('category')
    max_destinations = data.get('max_destinations')
    optimize_verification = data.get('optimize_verification', False)
    
    # Créer une tâche
    task_description = f"Vérification d'images - {scope}"
    if country:
        task_description += f" ({country})"
    if category:
        task_description += f" ({category})"
    if optimize_verification:
        task_description += " [Optimisé]"
    if max_destinations:
        task_description += f" - max {max_destinations}"
    
    task_id = task_manager.create_task('image_check', task_description)
    
    def process_image_check_batch(destinations_batch, batch_num):
        """Process a batch of image checks in parallel"""
        batch_results = []
        
        for dest in destinations_batch:
            if not check_status['is_running'] or not task_manager.is_task_running(task_id):
                break
                
            try:
                result = image_checker.check_images(dest['url'])
                result['name'] = dest['name']
                result['country'] = dest['country']
                
                # Ajouter la catégorie détectée automatiquement
                result['detected_category'] = detect_url_category(dest['url'])
                result['scan_date'] = datetime.now().isoformat()
                
                # Ajouter les informations d'optimisation si présentes
                if dest.get('is_optimized_sample'):
                    result['optimization_tag'] = dest.get('optimization_tag')
                    result['similar_urls_count'] = dest.get('similar_urls_count', 0)
                    result['is_optimized_sample'] = True
                
                # Sauvegarder DIRECTEMENT en base - fini les fichiers JSON !
                db.save_verification_result(result)
                
                # Update database with check results (garde la compatibilité)
                db.update_destination_check_status(
                    dest['url'], 
                    result.get('has_placeholder', False),
                    result.get('images_found', 0)
                )
                
                batch_results.append(result)
                
            except Exception as e:
                print(f"❌ Erreur vérification {dest['url']}: {e}")
                result = {
                    'url': dest['url'],
                    'name': dest['name'],
                    'country': dest['country'],
                    'status': 'error',
                    'error': str(e),
                    'has_placeholder': False,
                    'images_found': 0
                }
                batch_results.append(result)
        
        return batch_results
    
    def run_check_from_db():
        global check_status
        check_status['is_running'] = True
        check_status['progress'] = 0
        check_status['results'] = []
        
        print(f"🚀 Démarrage vérification images - Mode: {scope}")
        
        # Get destinations from database based on scope
        if scope == 'country':
            destinations = db.get_destinations_by_country(country)
        elif scope == 'category':
            # Get destinations by category (same logic as consolidator)
            all_destinations = db.get_destinations_by_country(None)
            destinations = []
            for dest in all_destinations:
                if is_destination_from_category(dest['url'], category):
                    destinations.append(dest)
        elif scope == 'unverified':
            # Get destinations that haven't been checked
            destinations = [d for d in db.get_destinations_by_country() if not d['last_checked']]
        elif scope == 'placeholder':
            # Get destinations with placeholders
            destinations = [d for d in db.get_destinations_by_country() if d['has_placeholder']]
        else:  # all
            destinations = db.get_destinations_by_country()
        
        # Apply smart optimization if requested
        original_count = len(destinations)
        if optimize_verification:
            destinations = optimize_destinations_by_location(destinations)
            print(f"🧠 Optimisation: {original_count} URLs → {len(destinations)} URLs représentatives")
        
        # Limit destinations if specified
        if max_destinations:
            destinations = destinations[:max_destinations]
        
        check_status['total'] = len(destinations)
        check_status['original_total'] = original_count
        
        # Mettre à jour la tâche avec le total
        task_manager.update_task(task_id, total=len(destinations))
        
        print(f"📊 {len(destinations)} destinations à vérifier")
        
        # Rate limiting adaptatif - Commence avec des paramètres conservateurs
        adaptive_config = {
            'batch_size': 20,        # Commence petit
            'max_workers': 5,        # Commence conservateur
            'success_streak': 0,     # Compteur de succès consécutifs
            'failure_count': 0,      # Compteur d'échecs
            'max_batch_size': 100,   # Limite haute
            'max_workers_limit': 50, # Limite haute workers
            'retry_queue': []        # Queue des batchs à retry
        }
        
        batches = [destinations[i:i + adaptive_config['batch_size']] 
                  for i in range(0, len(destinations), adaptive_config['batch_size'])]
        processed_count = 0
        
        print(f"🧠 Threading adaptatif: {len(batches)} batches initiaux de {adaptive_config['batch_size']} destinations")
        
        # Démarrer avec le nombre de workers adaptatif
        with ThreadPoolExecutor(max_workers=adaptive_config['max_workers']) as executor:
            for batch_num, batch in enumerate(batches):
                if not check_status['is_running'] or not task_manager.is_task_running(task_id):
                    break
                
                check_status['current_url'] = f'Batch {batch_num + 1}/{len(batches)} - {len(batch)} URLs (Workers: {adaptive_config["max_workers"]})'
                task_manager.update_task(task_id, current_item=check_status['current_url'])
                
                # Soumettre le batch en parallèle
                future_to_dest = {
                    executor.submit(process_image_check_batch, [dest], batch_num): dest 
                    for dest in batch
                }
                
                # Traiter les résultats au fur et à mesure avec monitoring
                batch_errors = 0
                batch_start_time = time.time()
                
                for future in as_completed(future_to_dest):
                    dest = future_to_dest[future]
                    processed_count += 1
                    
                    if not check_status['is_running'] or not task_manager.is_task_running(task_id):
                        break
                    
                    current_item_text = f'Batch {batch_num + 1}/{len(batches)} - {dest["name"]} ({processed_count}/{len(destinations)})'
                    check_status['current_url'] = current_item_text
                    task_manager.update_task(task_id, 
                                           progress=processed_count, 
                                           current_item=current_item_text)
                    
                    try:
                        batch_results = future.result()
                        check_status['results'].extend(batch_results)
                        adaptive_config['success_streak'] += 1
                        
                    except Exception as e:
                        print(f"❌ Erreur future {dest['url']}: {e}")
                        batch_errors += 1
                        adaptive_config['failure_count'] += 1
                    
                    check_status['progress'] = processed_count
                
                # Adaptive rate monitoring
                batch_duration = time.time() - batch_start_time
                error_rate = batch_errors / len(batch) if len(batch) > 0 else 0
                
                # Ajuster la pause selon les performances
                if error_rate > 0.2:  # > 20% d'erreurs
                    pause_time = 2.0
                    print(f"⚠️ Erreurs détectées ({error_rate:.1%}) - Pause augmentée à {pause_time}s")
                elif adaptive_config['success_streak'] > 50:  # Beaucoup de succès
                    pause_time = 0.2
                    print(f"🚀 Performance excellente - Pause réduite à {pause_time}s")
                else:
                    pause_time = 0.5
                
                time.sleep(pause_time)
        
        check_status['is_running'] = False
        check_status['current_url'] = None
        
        # Finaliser la tâche
        task_manager.update_task(task_id, results=check_status['results'])
        task_manager.complete_task(task_id, success=True)
        
        # Statistiques finales
        total_success = adaptive_config['success_streak']
        total_failures = adaptive_config['failure_count']
        success_rate = total_success / (total_success + total_failures) * 100 if (total_success + total_failures) > 0 else 0
        
        print(f"✅ Vérification terminée: {len(check_status['results'])} destinations vérifiées")
        print(f"📊 Performance adaptative - Succès: {total_success}, Échecs: {total_failures} (Taux: {success_rate:.1f}%)")
        print(f"⚙️ Configuration finale - Workers: {adaptive_config['max_workers']}, Batch: {adaptive_config['batch_size']}")
        
        # 🗃️ TOUT EST DÉJÀ EN BASE ! Plus besoin de fichiers JSON compliqués
        print(f"🗃️ Tous les résultats sauvegardés en base SQLite - {len(check_status['results'])} nouveaux scans")
        
        # Sauvegarder avec timestamp dans historique
        save_scan_with_timestamp(check_status['results'])
    
    thread = threading.Thread(target=run_check_from_db)
    thread.start()
    
    return jsonify({
        'message': 'Vérification démarrée (Threading 30x30)', 
        'scope': scope,
        'task_id': task_id
    })

@app.route('/api/verification-simulation', methods=['POST'])
@login_required
def simulate_verification():
    """Simule une vérification pour calculer le nombre d'URLs et l'optimisation"""
    try:
        data = request.get_json()
        scope = data.get('scope', 'all')
        country = data.get('country')
        category = data.get('category')
        max_destinations = data.get('max_destinations')
        
        # Get destinations using same logic as verification
        if scope == 'country':
            destinations = db.get_destinations_by_country(country)
        elif scope == 'category':
            all_destinations = db.get_destinations_by_country(None)
            destinations = []
            for dest in all_destinations:
                if is_destination_from_category(dest['url'], category):
                    destinations.append(dest)
        elif scope == 'unverified':
            destinations = [d for d in db.get_destinations_by_country() if not d['last_checked']]
        elif scope == 'placeholder':
            destinations = [d for d in db.get_destinations_by_country() if d['has_placeholder']]
        else:  # all
            destinations = db.get_destinations_by_country()
        
        base_count = len(destinations)
        
        # Apply optimization simulation
        optimized_destinations = optimize_destinations_by_location(destinations)
        optimized_count = len(optimized_destinations)
        
        # Apply max limit if specified
        if max_destinations:
            final_count = min(optimized_count, max_destinations)
        else:
            final_count = optimized_count
        
        # Calculate savings
        savings_percent = int((base_count - optimized_count) / base_count * 100) if base_count > 0 else 0
        
        # Estimate time (assuming ~3 seconds per verification)
        estimated_time_minutes = max(1, int(final_count * 3 / 60))
        
        return jsonify({
            'success': True,
            'base_count': base_count,
            'optimized_count': optimized_count,
            'final_count': final_count,
            'savings_percent': savings_percent,
            'estimated_time_minutes': estimated_time_minutes
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/crawl-and-check', methods=['POST'])
@login_required
def start_crawl_and_check():
    """Legacy endpoint for backwards compatibility"""
    global check_status
    
    if check_status['is_running']:
        return jsonify({'error': 'Une vérification est déjà en cours'}), 400
    
    data = request.get_json()
    max_destinations = data.get('max_destinations', 500)
    catalog_url = data.get('catalog_url', 'https://www.pierreetvacances.com/fr-fr/catalog')
    
    def run_crawl_and_check():
        global check_status
        check_status['is_running'] = True
        check_status['progress'] = 0
        check_status['results'] = []
        
        destinations = image_checker.crawl_catalog_destinations(catalog_url, max_destinations)
        
        check_status['total'] = len(destinations)
        
        for i, destination in enumerate(destinations):
            if not check_status['is_running']:
                break
                
            check_status['current_url'] = destination['url']
            result = image_checker.check_images(destination['url'])
            result['name'] = destination['name']
            check_status['results'].append(result)
            check_status['progress'] = i + 1
        
        check_status['is_running'] = False
        check_status['current_url'] = None
        
        # Sauvegarder dans results_cache.json pour compatibilité
        with open('results_cache.json', 'w') as f:
            json.dump(check_status['results'], f, indent=2)
        
        # Sauvegarder avec timestamp dans historique
        save_scan_with_timestamp(check_status['results'])
    
    thread = threading.Thread(target=run_crawl_and_check)
    thread.start()
    
    return jsonify({'message': 'Crawl et vérification démarrés', 'total': max_destinations})

@app.route('/api/status')
@login_required
def get_status():
    return jsonify(check_status)

@app.route('/api/results')
@login_required
def get_results():
    """Récupère tous les résultats de vérification depuis la base de données"""
    # Compter le total de destinations disponibles dans la base
    total_destinations_available = len(db.get_destinations_by_country(None))
    
    # Récupérer tous les résultats depuis la base de données
    db_results = db.get_all_verification_results()
    
    # Migration une seule fois: importer les anciens résultats JSON en base s'ils existent
    if os.path.exists('results_cache.json') and len(db_results) == 0:
        try:
            with open('results_cache.json', 'r') as f:
                legacy_results = json.load(f)
            
            print(f"🔄 Migration des {len(legacy_results)} résultats JSON vers la base de données...")
            
            for result in legacy_results:
                # Ajouter des informations manquantes pour la compatibilité
                if 'detected_category' not in result and 'url' in result:
                    result['detected_category'] = detect_url_category(result['url'])
                
                # Marquer comme scan historique
                if 'scan_date' not in result:
                    result['scan_date'] = datetime.now().isoformat()
                    result['is_legacy_scan'] = True
                
                # Sauvegarder en base
                db.save_verification_result(result)
            
            # Renommer le fichier JSON pour éviter la re-migration
            os.rename('results_cache.json', 'results_cache_migrated.json')
            print(f"✅ Migration terminée, fichier renommé en results_cache_migrated.json")
            
            # Récupérer les résultats maintenant en base
            db_results = db.get_all_verification_results()
            
        except Exception as e:
            print(f"❌ Erreur lors de la migration: {e}")
    
    return jsonify({
        'results': db_results,
        'total_available': total_destinations_available,
        'total_checked': len(db_results)
    })

@app.route('/api/historique/data')
@login_required
def get_historique_data():
    """Retourne les données historiques depuis la base de données avec statistiques"""
    # Récupérer tous les résultats depuis la base de données
    results = db.get_all_verification_results()
    
    # Calculer les statistiques
    total = len(results)
    success = len([r for r in results if r.get('status') == 'success'])
    warning = len([r for r in results if r.get('status') == 'warning'])
    error = len([r for r in results if r.get('status') == 'error'])
    with_images = len([r for r in results if r.get('images_found', 0) > 0])
    placeholders = len([r for r in results if r.get('has_placeholder', False)])
    
    # Grouper par pays/domaine depuis les données en base
    countries = {}
    for result in results:
        # Utiliser le pays détecté ou extraire du domaine
        country_key = result.get('country', 'unknown')
        if not country_key or country_key == 'unknown':
            domain = result.get('url', '').split('/')[2] if '/' in result.get('url', '') else 'unknown'
            country_key = domain.split('.')[-2] if '.' in domain else domain
        
        if country_key not in countries:
            countries[country_key] = {
                'name': country_key,
                'total': 0,
                'success': 0,
                'warning': 0,
                'error': 0,
                'images_total': 0
            }
        
        countries[country_key]['total'] += 1
        status = result.get('status', 'unknown')
        if status in countries[country_key]:
            countries[country_key][status] += 1
        countries[country_key]['images_total'] += result.get('images_found', 0)
    
    return jsonify({
        'results': results,
        'statistics': {
            'total': total,
            'success': success,
            'warning': warning,
            'error': error,
            'with_images': with_images,
            'placeholders': placeholders,
            'success_rate': round((success / total * 100) if total > 0 else 0, 1)
        },
        'countries': list(countries.values())
    })

@app.route('/api/historique/scans')
@login_required
def get_historique_scans():
    """Retourne la liste des scans disponibles par date"""
    scans = []
    scan_files = glob.glob('historique_scans/scan_*.json')
    
    for scan_file in sorted(scan_files, reverse=True):
        try:
            with open(scan_file, 'r', encoding='utf-8') as f:
                scan_data = json.load(f)
                scans.append({
                    'filename': os.path.basename(scan_file),
                    'timestamp': scan_data.get('timestamp'),
                    'date': scan_data.get('date'),
                    'time': scan_data.get('time'),
                    'total_destinations': scan_data.get('total_destinations', 0)
                })
        except:
            continue
    
    return jsonify({'scans': scans})

@app.route('/api/historique/scan/<filename>')
@login_required
def get_scan_details(filename):
    """Retourne les détails d'un scan spécifique"""
    try:
        filepath = f'historique_scans/{filename}'
        with open(filepath, 'r', encoding='utf-8') as f:
            scan_data = json.load(f)
        
        results = scan_data.get('results', [])
        
        # Calculer les statistiques
        total = len(results)
        success = len([r for r in results if r['status'] == 'success'])
        warning = len([r for r in results if r['status'] == 'warning'])
        error = len([r for r in results if r['status'] == 'error'])
        with_images = len([r for r in results if r['images_found'] > 0])
        placeholders = len([r for r in results if r['has_placeholder']])
        
        # Grouper par domaine et région
        domains = {}
        regions = {}
        
        for result in results:
            # Extraction du domaine
            domain = result['url'].split('/')[2] if '/' in result['url'] else 'unknown'
            country_key = domain.split('.')[-2] if '.' in domain else domain
            
            if country_key not in domains:
                domains[country_key] = {
                    'name': country_key,
                    'total': 0,
                    'success': 0,
                    'warning': 0,
                    'error': 0,
                    'images_total': 0,
                    'placeholders': 0
                }
            
            domains[country_key]['total'] += 1
            domains[country_key][result['status']] += 1
            domains[country_key]['images_total'] += result['images_found']
            if result['has_placeholder']:
                domains[country_key]['placeholders'] += 1
            
            # Extraction de la région depuis l'URL
            url_parts = result['url'].split('/')
            if len(url_parts) > 4:
                region_code = url_parts[4].split('_')[0] if '_' in url_parts[4] else 'other'
                
                if region_code not in regions:
                    regions[region_code] = {
                        'name': region_code,
                        'total': 0,
                        'success': 0,
                        'warning': 0,
                        'error': 0,
                        'images_total': 0,
                        'placeholders': 0
                    }
                
                regions[region_code]['total'] += 1
                regions[region_code][result['status']] += 1
                regions[region_code]['images_total'] += result['images_found']
                if result['has_placeholder']:
                    regions[region_code]['placeholders'] += 1
        
        return jsonify({
            'scan_info': {
                'filename': filename,
                'timestamp': scan_data.get('timestamp'),
                'date': scan_data.get('date'),
                'time': scan_data.get('time')
            },
            'results': results,
            'statistics': {
                'total': total,
                'success': success,
                'warning': warning,
                'error': error,
                'with_images': with_images,
                'placeholders': placeholders,
                'success_rate': round((success / total * 100) if total > 0 else 0, 1)
            },
            'domains': list(domains.values()),
            'regions': list(regions.values())
        })
    except FileNotFoundError:
        return jsonify({'error': 'Scan not found'}), 404

@app.route('/api/historique/compare', methods=['POST'])
@login_required
def compare_scans():
    """Compare deux scans pour voir l'évolution"""
    data = request.json
    scan1_file = data.get('scan1')
    scan2_file = data.get('scan2')
    
    try:
        # Charger les deux scans
        with open(f'historique_scans/{scan1_file}', 'r', encoding='utf-8') as f:
            scan1_data = json.load(f)
        
        with open(f'historique_scans/{scan2_file}', 'r', encoding='utf-8') as f:
            scan2_data = json.load(f)
        
        results1 = {r['url']: r for r in scan1_data.get('results', [])}
        results2 = {r['url']: r for r in scan2_data.get('results', [])}
        
        # Analyser les changements
        changes = {
            'fixed': [],  # Erreurs corrigées
            'broken': [],  # Nouvelles erreurs
            'improved': [],  # Améliorations (ex: placeholders remplacés)
            'degraded': [],  # Dégradations
            'unchanged': [],  # Sans changement
            'new': [],  # Nouvelles destinations
            'removed': []  # Destinations supprimées
        }
        
        # Comparer les URLs communes
        for url in results1:
            if url in results2:
                r1 = results1[url]
                r2 = results2[url]
                
                if r1['status'] == 'error' and r2['status'] != 'error':
                    changes['fixed'].append({'url': url, 'before': r1, 'after': r2})
                elif r1['status'] != 'error' and r2['status'] == 'error':
                    changes['broken'].append({'url': url, 'before': r1, 'after': r2})
                elif r1['has_placeholder'] and not r2['has_placeholder']:
                    changes['improved'].append({'url': url, 'before': r1, 'after': r2})
                elif not r1['has_placeholder'] and r2['has_placeholder']:
                    changes['degraded'].append({'url': url, 'before': r1, 'after': r2})
                elif r1['status'] == r2['status'] and r1['has_placeholder'] == r2['has_placeholder']:
                    changes['unchanged'].append({'url': url, 'before': r1, 'after': r2})
            else:
                changes['removed'].append(results1[url])
        
        # Nouvelles destinations
        for url in results2:
            if url not in results1:
                changes['new'].append(results2[url])
        
        return jsonify({
            'scan1': {
                'filename': scan1_file,
                'date': scan1_data.get('date'),
                'time': scan1_data.get('time')
            },
            'scan2': {
                'filename': scan2_file,
                'date': scan2_data.get('date'),
                'time': scan2_data.get('time')
            },
            'changes': changes,
            'summary': {
                'fixed': len(changes['fixed']),
                'broken': len(changes['broken']),
                'improved': len(changes['improved']),
                'degraded': len(changes['degraded']),
                'unchanged': len(changes['unchanged']),
                'new': len(changes['new']),
                'removed': len(changes['removed'])
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/historique/import', methods=['POST'])
@login_required
def import_json_scan():
    """Importe un fichier JSON comme nouveau scan avec référence temporelle"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'Aucun fichier fourni'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'Aucun fichier sélectionné'}), 400
        
        if not file.filename.endswith('.json'):
            return jsonify({'error': 'Le fichier doit être au format JSON'}), 400
        
        # Lire le contenu du fichier
        content = file.read().decode('utf-8')
        imported_data = json.loads(content)
        
        # Valider la structure du JSON
        if isinstance(imported_data, list):
            # Format simple : liste de résultats
            results = imported_data
        elif isinstance(imported_data, dict) and 'results' in imported_data:
            # Format avec métadonnées
            results = imported_data['results']
        else:
            return jsonify({'error': 'Format JSON non reconnu. Attendu: liste de résultats ou objet avec propriété "results"'}), 400
        
        # Récupérer les paramètres personnalisés
        custom_date = request.form.get('custom_date')
        custom_time = request.form.get('custom_time', '12:00:00')
        description = request.form.get('description', 'Import manuel')
        
        # Créer le timestamp
        if custom_date:
            try:
                # Nettoyer la date (supprimer espaces)
                custom_date = custom_date.strip()
                print(f"DEBUG: Date reçue: '{custom_date}' (longueur: {len(custom_date)})")
                
                # Essayer d'abord le format français DD/MM/YYYY
                try:
                    date_obj = datetime.strptime(custom_date, '%d/%m/%Y')
                    print(f"DEBUG: Date parsée avec format français: {date_obj}")
                except ValueError as e1:
                    print(f"DEBUG: Échec format français: {e1}")
                    # Si ça échoue, essayer le format ISO YYYY-MM-DD
                    try:
                        date_obj = datetime.strptime(custom_date, '%Y-%m-%d')
                        print(f"DEBUG: Date parsée avec format ISO: {date_obj}")
                    except ValueError as e2:
                        print(f"DEBUG: Échec format ISO: {e2}")
                        raise ValueError(f"Aucun format reconnu: français={e1}, ISO={e2}")
                
                # Parser l'heure avec ou sans secondes
                try:
                    time_obj = datetime.strptime(custom_time, '%H:%M:%S').time()
                except ValueError:
                    # Si pas de secondes, ajouter :00
                    time_obj = datetime.strptime(custom_time + ':00', '%H:%M:%S').time()
                timestamp_dt = datetime.combine(date_obj.date(), time_obj)
            except ValueError as e:
                print(f"DEBUG: Erreur finale: {e}")
                return jsonify({'error': f'Format de date/heure invalide. Date reçue: "{custom_date}", Heure reçue: "{custom_time}". Utilisez DD/MM/YYYY ou YYYY-MM-DD pour la date et HH:MM ou HH:MM:SS pour l\'heure'}), 400
        else:
            timestamp_dt = datetime.now()
        
        # Générer le nom de fichier
        timestamp_str = timestamp_dt.strftime('%Y%m%d_%H%M%S')
        filename = f'historique_scans/scan_{timestamp_str}_imported.json'
        
        # Préparer les données du scan
        scan_data = {
            'timestamp': timestamp_dt.isoformat(),
            'date': timestamp_dt.strftime('%Y-%m-%d'),
            'time': timestamp_dt.strftime('%H:%M:%S'),
            'total_destinations': len(results),
            'description': description,
            'imported': True,
            'original_filename': file.filename,
            'results': results
        }
        
        # Valider les résultats
        validated_results = []
        for i, result in enumerate(results):
            # Structure minimale requise
            validated_result = {
                'url': result.get('url', f'unknown_url_{i}'),
                'status': result.get('status', 'unknown'),
                'images_found': result.get('images_found', 0),
                'images': result.get('images', []),
                'has_placeholder': result.get('has_placeholder', False),
                'placeholder_count': result.get('placeholder_count', 0),
                'error': result.get('error', None),
                'title': result.get('title', '')
            }
            validated_results.append(validated_result)
        
        scan_data['results'] = validated_results
        
        # Sauvegarder le fichier
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(scan_data, f, indent=2, ensure_ascii=False)
        
        print(f"📁 JSON importé et sauvegardé: {filename}")
        
        return jsonify({
            'success': True,
            'message': f'JSON importé avec succès ({len(validated_results)} destinations)',
            'filename': os.path.basename(filename),
            'scan_info': {
                'date': scan_data['date'],
                'time': scan_data['time'],
                'total_destinations': scan_data['total_destinations'],
                'description': scan_data['description']
            }
        })
        
    except json.JSONDecodeError as e:
        return jsonify({'error': f'Erreur de format JSON: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'error': f'Erreur lors de l\'import: {str(e)}'}), 500

# Consolidator API Routes
@app.route('/api/consolidator/countries')
@login_required
def get_countries():
    countries = db.get_all_countries()
    return jsonify(countries)

@app.route('/api/consolidator/destinations')
@login_required
def get_all_destinations():
    # Récupérer toutes les entrées (maintenant ce sont des typologies GZ, pas des destinations classiques)
    destinations = db.get_destinations_by_country(None)
    print(f"API: Returning {len(destinations)} entries (all)")
    if len(destinations) > 0:
        print(f"First entry sample: {destinations[0]}")
    return jsonify({
        'success': True,
        'destinations': destinations,
        'count': len(destinations)
    })

@app.route('/api/consolidator/destinations/<country>')
@login_required
def get_destinations_by_country(country):
    destinations = db.get_destinations_by_country(country)
    print(f"API: Returning {len(destinations)} destinations for country: {country}")
    if len(destinations) > 0:
        print(f"First destination sample: {destinations[0]}")
    return jsonify({
        'success': True,
        'destinations': destinations,
        'count': len(destinations)
    })

@app.route('/api/consolidator/destinations', methods=['POST'])
@login_required
def add_destination():
    data = request.get_json()
    try:
        result = db.add_destination(
            name=data['name'],
            url=data['url'],
            country=data['country'],
            region=data.get('region'),
            city=data.get('city'),
            destination_type=data.get('type'),
            notes=data.get('notes')
        )
        return jsonify({'success': True, 'id': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/consolidator/destinations', methods=['PUT'])
@login_required
def update_destination():
    data = request.get_json()
    try:
        # For updates, we use the same add_destination method which handles updates
        db.add_destination(
            name=data['name'],
            url=data['url'],
            country=data['country'],
            region=data.get('region'),
            city=data.get('city'),
            destination_type=data.get('type'),
            notes=data.get('notes')
        )
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/consolidator/destinations/<int:destination_id>', methods=['DELETE'])
@login_required
def delete_destination(destination_id):
    try:
        result = db.delete_destination(destination_id)
        return jsonify({'success': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/consolidator/scrape-full', methods=['POST'])
@login_required
def start_full_scraping():
    global scraping_status
    
    if scraping_status['is_running']:
        return jsonify({'success': False, 'error': 'Un scraping est déjà en cours'})
    
    # Get selected categories from request
    data = request.get_json() or {}
    selected_categories = data.get('categories', None)
    
    def progress_callback(percent, status):
        global scraping_status
        scraping_status['progress_percent'] = percent
        scraping_status['current_status'] = status
        print(f"📊 {percent}% - {status}")
    
    def run_scraping():
        global scraping_status
        scraping_status['is_running'] = True
        scraping_status['progress'] = 0
        scraping_status['destinations_found'] = 0
        scraping_status['progress_percent'] = 0
        scraping_status['current_status'] = 'Initialisation...'
        
        try:
            # Créer un scraper avec callback
            progress_scraper = PVCatalogScraper(progress_callback=progress_callback)
            
            # Use the new method with selected categories if provided
            if selected_categories:
                destinations = progress_scraper.scrape_full_catalog_selective(selected_categories)
            else:
                destinations = progress_scraper.scrape_full_catalog()
            
            scraping_status['destinations_found'] = len(destinations)
            scraping_status['progress_percent'] = 100
            scraping_status['current_status'] = f'Terminé - {len(destinations)} destinations trouvées'
            
            print(f"✅ Scraping terminé: {len(destinations)} destinations trouvées")
            
        except Exception as e:
            print(f"❌ Erreur scraping: {e}")
            scraping_status['progress_percent'] = 100
            scraping_status['current_status'] = f'Erreur: {str(e)}'
        finally:
            scraping_status['is_running'] = False
    
    thread = threading.Thread(target=run_scraping)
    thread.start()
    
    return jsonify({'success': True})

@app.route('/api/consolidator/sitemap-counts')
@login_required
def get_sitemap_counts():
    """Récupère le nombre d'entrées dans chaque fichier sitemap"""
    try:
        scraper = PVCatalogScraper()
        counts = scraper.get_sitemap_entry_counts()
        return jsonify({'success': True, 'counts': counts})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/consolidator/destinations/category/<category>')
@login_required
def get_destinations_by_category(category):
    """Récupère les destinations par catégorie GZ"""
    try:
        db = DestinationDB()
        # Récupérer toutes les entrées de la table (ce sont maintenant des typologies GZ)
        destinations = db.get_destinations_by_country(None)
        
        # Filtrer par catégorie basé sur l'URL ou les patterns
        if category != 'all':
            filtered_destinations = []
            for dest in destinations:
                if is_destination_from_category(dest['url'], category):
                    filtered_destinations.append(dest)
            destinations = filtered_destinations
        
        return jsonify({
            'success': True, 
            'destinations': destinations,
            'count': len(destinations)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

def optimize_destinations_by_location(destinations):
    """Optimise la liste en ne gardant qu'une URL représentative par destination géographique"""
    import re
    from collections import defaultdict
    
    # Grouper les destinations par nom géographique
    location_groups = defaultdict(list)
    
    for dest in destinations:
        # Extraire le nom de la destination depuis l'URL
        location_name = extract_location_from_url(dest['url'])
        location_groups[location_name].append(dest)
    
    optimized_destinations = []
    skipped_groups = []
    
    for location, group in location_groups.items():
        if len(group) == 1:
            # Une seule URL pour cette destination, on la garde
            optimized_destinations.extend(group)
        else:
            # Plusieurs URLs pour cette destination, on ne garde que la première (française de préférence)
            # Priorité: fr-fr > autres langues
            group_sorted = sorted(group, key=lambda x: (
                0 if '/fr-fr/' in x['url'] else 1,  # Français en premier
                len(x['url'])  # URL la plus courte ensuite
            ))
            
            representative = group_sorted[0]
            # Marquer comme groupe optimisé avec tag spécial
            representative['optimization_tag'] = f"🔍 Groupe '{location}' ({len(group)} URLs similaires)"
            representative['similar_urls_count'] = len(group) - 1
            representative['is_optimized_sample'] = True
            
            optimized_destinations.append(representative)
            skipped_groups.append({
                'location': location,
                'count': len(group),
                'representative_url': representative['url']
            })
    
    print(f"📍 {len(location_groups)} destinations uniques détectées")
    print(f"⚡ {len(skipped_groups)} groupes optimisés (1 URL testée par groupe)")
    
    return optimized_destinations

def detect_url_category(url):
    """Détecte la catégorie d'une URL pour l'affichage des tags colorés"""
    url_lower = url.lower()
    
    # Mapping des patterns vers les catégories d'affichage
    if '/co_' in url_lower:
        return 'Pays'
    elif '/zt_' in url_lower:
        return 'Zone Touristique'
    elif '/ge_' in url_lower:
        return 'Région'
    elif '/de_' in url_lower:
        return 'Destination'
    elif '/fp_' in url_lower:
        return 'Fiche Produit'
    elif '/avis' in url_lower or '/review' in url_lower:
        return 'Avis'
    elif '/blog' in url_lower or '/article' in url_lower:
        return 'Blog'
    else:
        return 'Autre'

def extract_location_from_url(url):
    """Extrait le nom de la destination depuis une URL Pierre & Vacances"""
    import re
    
    # Patterns pour différents types d'URLs
    patterns = [
        r'/de_[^/]*?-([^/]+?)(?:-[^/]*)?/?(?:\?|$)',  # /de_location-sainte-anne
        r'/fp_[A-Z0-9]+_[^/]*?-([^/]+?)(?:-[^/]*)?/?(?:\?|$)',  # /fp_XXX_location-sainte-anne
        r'/co_[^/]*?-([^/]+?)/?(?:\?|$)',  # /co_location-france
        r'/zt_[^/]*?-([^/]+?)/?(?:\?|$)',  # /zt_costa-brava
        r'/ge_[^/]*?-([^/]+?)/?(?:\?|$)',  # /ge_region-alsace
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            location = match.group(1)
            # Nettoyer le nom (enlever les suffixes techniques)
            location = re.sub(r'-(last-minute|vacances|location|sejour|weekend)$', '', location)
            return location.lower()
    
    # Si aucun pattern ne matche, utiliser le dernier segment de l'URL
    segments = url.rstrip('/').split('/')
    if segments:
        return segments[-1].lower()
    
    return 'unknown'

def is_destination_from_category(url, category):
    """Détermine si une URL appartient à une catégorie spécifique"""
    url_lower = url.lower()
    
    # Patterns basés sur la structure réelle des URLs Pierre & Vacances
    category_patterns = {
        'country': ['/co_'],  # Pages pays: /co_location-france
        'region': ['/ge_', '/zt_'],  # Géographique + Zone touristique  
        'destination': ['/de_'],  # Pages destinations: /de_location-houlgate
        'zone-touristique': ['/zt_'],  # Zone touristique uniquement
        'fiche-produit': ['/fp_'],  # Fiches produit: /fp_CWL_location-residence
        'avis-fiche-produit': ['/avis'],  # Pages d'avis
        'blog': ['/blog', '/article'],  # Articles de blog
        'autre-page': []  # Catch-all pour les autres pages
    }
    
    if category in category_patterns:
        patterns = category_patterns[category]
        if patterns:  # Si il y a des patterns à chercher
            return any(pattern in url_lower for pattern in patterns)
        else:  # Pour 'autre-page', prendre ceux qui ne matchent aucun pattern
            all_patterns = []
            for cat_patterns in category_patterns.values():
                all_patterns.extend(cat_patterns)
            return not any(pattern in url_lower for pattern in all_patterns if pattern)
    
    return False

@app.route('/api/consolidator/scraping-status')
@login_required
def get_scraping_status():
    return jsonify(scraping_status)

@app.route('/api/consolidator/stop-scraping', methods=['POST'])
@login_required
def stop_scraping():
    global scraping_status
    scraping_status['is_running'] = False
    scraping_status['current_status'] = 'Arrêté par l\'utilisateur'
    return jsonify({'success': True, 'message': 'Scraping arrêté'})

@app.route('/api/consolidator/stats')
@login_required
def get_consolidator_stats():
    stats = db.get_stats()
    return jsonify(stats)

@app.route('/api/consolidator/export/json')
@login_required
def export_destinations_json():
    """Exporte toutes les destinations en JSON pour traitement offline"""
    try:
        filename, count = db.export_all_destinations_json()
        return jsonify({
            'success': True,
            'filename': filename,
            'count': count,
            'message': f'{count} destinations exportées dans {filename}'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/consolidator/export/<format>')
@app.route('/api/consolidator/export/<format>/<country>')
@login_required
def export_destinations(format, country=None):
    if format == 'csv':
        csv_data = db.export_csv(country)
        filename = f'destinations_{country or "all"}.csv'
        
        return Response(
            csv_data,
            mimetype='text/csv',
            headers={"Content-disposition": f"attachment; filename={filename}"}
        )
    else:
        return jsonify({'error': 'Format non supporté'}), 400

@app.route('/api/consolidator/import/csv', methods=['POST'])
@login_required
def import_destinations_csv():
    if 'csv_file' not in request.files:
        return jsonify({'success': False, 'error': 'Aucun fichier fourni'})
    
    file = request.files['csv_file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'Aucun fichier sélectionné'})
    
    try:
        csv_content = file.read().decode('utf-8')
        imported_count, errors = db.import_csv(csv_content)
        
        if errors:
            return jsonify({
                'success': False, 
                'error': f'{len(errors)} erreurs lors de l\'import',
                'details': errors[:5]  # Show first 5 errors
            })
        
        return jsonify({
            'success': True, 
            'imported_count': imported_count
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# Snapshots API Routes
@app.route('/api/consolidator/snapshots')
@login_required
def get_snapshots():
    snapshots = db.get_snapshots()
    return jsonify(snapshots)

@app.route('/api/consolidator/snapshots', methods=['POST'])
@login_required
def create_snapshot():
    data = request.get_json()
    try:
        snapshot_id = db.create_snapshot(
            version_name=data['version_name'],
            description=data.get('description'),
            created_by=data.get('created_by', 'system')
        )
        return jsonify({'success': True, 'id': snapshot_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/consolidator/snapshots/<int:snapshot_id>')
@login_required
def get_snapshot_details(snapshot_id):
    snapshot_data = db.get_snapshot_data(snapshot_id)
    if snapshot_data:
        return jsonify(snapshot_data)
    else:
        return jsonify({'error': 'Snapshot non trouvé'}), 404

@app.route('/api/consolidator/snapshots/<int:snapshot_id>/export')
@login_required
def export_snapshot(snapshot_id):
    csv_data = db.export_snapshot_csv(snapshot_id)
    if csv_data:
        # Get snapshot info for filename
        snapshots = db.get_snapshots()
        snapshot = next((s for s in snapshots if s['id'] == snapshot_id), None)
        filename = f'snapshot_{snapshot["version_name"] if snapshot else snapshot_id}.csv'
        
        return Response(
            csv_data,
            mimetype='text/csv',
            headers={"Content-disposition": f"attachment; filename={filename}"}
        )
    else:
        return jsonify({'error': 'Snapshot non trouvé'}), 404

@app.route('/api/consolidator/snapshots/<int:snapshot_id>', methods=['DELETE'])
@login_required
def delete_snapshot(snapshot_id):
    try:
        result = db.delete_snapshot(snapshot_id)
        return jsonify({'success': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/consolidator/cleanup/avis', methods=['POST'])
@login_required
def cleanup_avis_urls():
    """Supprime toutes les URLs contenant '/avis' de la base de données"""
    try:
        deleted_count = db.delete_destinations_by_url_pattern('/avis')
        return jsonify({
            'success': True, 
            'deleted_count': deleted_count,
            'message': f'{deleted_count} URLs d\'avis supprimées'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/consolidator/reclassify-offline', methods=['POST'])
@login_required
def reclassify_offline():
    """Re-classifie les destinations en mode OFFLINE (sans requêtes HTTP)"""
    global reclassify_status
    
    if reclassify_status['is_running']:
        return jsonify({'success': False, 'error': 'Une re-classification est déjà en cours'})
    
    def run_offline_reclassification():
        global reclassify_status
        try:
            from catalog_scraper import PVCatalogScraper
            temp_scraper = PVCatalogScraper()
            
            reclassify_status['is_running'] = True
            reclassify_status['progress'] = 0
            reclassify_status['updated_count'] = 0
            reclassify_status['progress_percent'] = 0
            reclassify_status['current_status'] = 'Mode OFFLINE - Chargement des destinations...'
            
            # Créer une session de reclassification
            session_id = db.create_reclassification_session(
                session_type='reclassification_offline',
                threading_mode='batch_50',
                notes='Reclassification offline sans requêtes HTTP'
            )
            start_time = time.time()
            
            # Récupérer toutes les destinations
            destinations = db.get_destinations_by_country()
            reclassify_status['total'] = len(destinations)
            reclassify_status['current_status'] = f'Mode OFFLINE - {len(destinations)} destinations à analyser'
            
            # Traiter par batch de 50
            batch_size = 50
            updated_count = 0
            
            for i in range(0, len(destinations), batch_size):
                if not reclassify_status['is_running']:
                    break
                    
                batch = destinations[i:i + batch_size]
                batch_num = i // batch_size + 1
                total_batches = (len(destinations) + batch_size - 1) // batch_size
                
                reclassify_status['current_status'] = f'Mode OFFLINE - Batch {batch_num}/{total_batches}'
                
                for dest in batch:
                    if not reclassify_status['is_running']:
                        break
                    
                    # Déterminer la catégorie à partir de l'URL et du nom UNIQUEMENT
                    new_category = temp_scraper._determine_category(dest['url'], dest['name'])
                    
                    # Extraire le pays de l'URL (pattern simple sans requête HTTP)
                    url_parts = dest['url'].split('/')
                    if len(url_parts) > 4:
                        # Pattern: /fr-fr/ge_FR ou /fr-fr/fp_ABC
                        location_part = url_parts[4]
                        if '_' in location_part:
                            country_code = location_part.split('_')[1][:2].upper()
                            # Mapping simple des codes pays
                            country_map = {
                                'FR': 'FR', 'ES': 'ES', 'IT': 'IT', 'GR': 'GR',
                                'PT': 'PT', 'AD': 'AD', 'MT': 'MT', 'MU': 'MU',
                                'RE': 'RE', 'GP': 'GP', 'MQ': 'MQ', 'NL': 'NL',
                                'BE': 'BE', 'DE': 'DE', 'AT': 'AT', 'CH': 'CH'
                            }
                            new_country = country_map.get(country_code, dest['country'])
                        else:
                            new_country = dest['country']
                    else:
                        new_country = dest['country']
                    
                    # Mettre à jour si changement
                    if new_category != dest.get('category', 'destination') or new_country != dest['country']:
                        import sqlite3
                        with sqlite3.connect(db.db_path) as conn:
                            cursor = conn.cursor()
                            cursor.execute('''
                                UPDATE destinations 
                                SET country=?, category=?, updated_at=CURRENT_TIMESTAMP
                                WHERE id=?
                            ''', (new_country, new_category, dest['id']))
                            conn.commit()
                        updated_count += 1
                
                reclassify_status['progress'] = i + len(batch)
                reclassify_status['updated_count'] = updated_count
                reclassify_status['progress_percent'] = int((i + len(batch)) / len(destinations) * 100)
            
            # Terminer la session
            duration = int((time.time() - start_time) / 60)
            db.update_reclassification_session(
                session_id,
                completed_at=datetime.now(),
                duration_minutes=duration,
                total_processed=len(destinations),
                total_updated=updated_count,
                status='completed'
            )
            
            reclassify_status['current_status'] = f'Mode OFFLINE terminé - {updated_count} destinations mises à jour en {duration} minutes'
            print(f"✅ Reclassification OFFLINE terminée: {updated_count}/{len(destinations)} mises à jour")
            
        except Exception as e:
            print(f"❌ Erreur reclassification offline: {e}")
            reclassify_status['current_status'] = f'Erreur: {str(e)}'
            if 'session_id' in locals():
                db.update_reclassification_session(
                    session_id,
                    completed_at=datetime.now(),
                    status='error',
                    error_message=str(e)
                )
        finally:
            reclassify_status['is_running'] = False
    
    thread = threading.Thread(target=run_offline_reclassification)
    thread.start()
    
    return jsonify({'success': True, 'message': 'Re-classification OFFLINE démarrée (sans requêtes HTTP)'})

@app.route('/api/consolidator/reclassify-countries', methods=['POST'])
@login_required
def reclassify_countries():
    """Re-classifie toutes les destinations avec la nouvelle logique de pays"""
    global reclassify_status
    
    if reclassify_status['is_running']:
        return jsonify({'success': False, 'error': 'Une re-classification est déjà en cours'})
    
    def process_destination_batch(destinations_batch, temp_scraper, batch_num):
        """Process a batch of destinations in parallel"""
        batch_results = []
        
        for dest in destinations_batch:
            if not reclassify_status['is_running']:
                break
                
            try:
                # Utiliser la nouvelle logique pour déterminer le pays
                new_country = temp_scraper._extract_country_from_page(dest['url'])
                
                # Utiliser la nouvelle logique pour déterminer la catégorie (avec les correspondances configurables)
                new_category = temp_scraper._determine_category(dest['url'], dest['name'])
                
                # Vérifier les changements
                country_changed = new_country != dest['country']
                category_changed = new_category != dest.get('category', 'destination')
                
                if country_changed or category_changed:
                    batch_results.append({
                        'dest': dest,
                        'new_country': new_country,
                        'new_category': new_category,
                        'country_changed': country_changed,
                        'category_changed': category_changed
                    })
                    
            except Exception as e:
                print(f"❌ Erreur traitement {dest['url']}: {e}")
                continue
        
        return batch_results

    def run_reclassification():
        global reclassify_status
        try:
            from catalog_scraper import PVCatalogScraper
            temp_scraper = PVCatalogScraper()
            
            reclassify_status['is_running'] = True
            reclassify_status['progress'] = 0
            reclassify_status['updated_count'] = 0
            reclassify_status['progress_percent'] = 0
            reclassify_status['current_status'] = 'Chargement des destinations...'
            reclassify_status['current_url'] = None
            
            # Récupérer toutes les destinations
            destinations = db.get_destinations_by_country()
            reclassify_status['total'] = len(destinations)
            reclassify_status['current_status'] = f'Re-classification de {len(destinations)} destinations (pays + catégories) - Threading 30x30...'
            
            # Diviser en batches de 30
            batch_size = 30
            batches = [destinations[i:i + batch_size] for i in range(0, len(destinations), batch_size)]
            processed_count = 0
            
            print(f"🚀 Threading: {len(batches)} batches de {batch_size} destinations")
            
            with ThreadPoolExecutor(max_workers=8) as executor:
                for batch_num, batch in enumerate(batches):
                    if not reclassify_status['is_running']:
                        break
                    
                    reclassify_status['current_status'] = f'Batch {batch_num + 1}/{len(batches)} - Threading 30 URLs...'
                    
                    # Soumettre le batch en parallèle
                    future_to_dest = {
                        executor.submit(process_destination_batch, [dest], temp_scraper, batch_num): dest 
                        for dest in batch
                    }
                    
                    # Traiter les résultats au fur et à mesure
                    for future in as_completed(future_to_dest):
                        dest = future_to_dest[future]
                        processed_count += 1
                        
                        if not reclassify_status['is_running']:
                            break
                            
                        reclassify_status['current_url'] = dest['url']
                        reclassify_status['current_status'] = f'Batch {batch_num + 1}/{len(batches)} - {dest["name"]} ({processed_count}/{len(destinations)})'
                        
                        try:
                            batch_results = future.result()
                            
                            # Appliquer les mises à jour
                            for result in batch_results:
                                try:
                                    import sqlite3
                                    with sqlite3.connect(db.db_path) as conn:
                                        cursor = conn.cursor()
                                        cursor.execute('''
                                            UPDATE destinations 
                                            SET country=?, category=?, updated_at=CURRENT_TIMESTAMP
                                            WHERE id=?
                                        ''', (result['new_country'], result['new_category'], result['dest']['id']))
                                        conn.commit()
                                    
                                    reclassify_status['updated_count'] += 1
                                    changes = []
                                    if result['country_changed']:
                                        changes.append(f"pays: {result['dest']['country']} -> {result['new_country']}")
                                    if result['category_changed']:
                                        changes.append(f"catégorie: {result['dest'].get('category', 'destination')} -> {result['new_category']}")
                                    print(f"🔄 Updated {result['dest']['url']}: {', '.join(changes)}")
                                    
                                except Exception as update_error:
                                    print(f"❌ Erreur update {result['dest']['url']}: {update_error}")
                                    continue
                                    
                        except Exception as e:
                            print(f"❌ Erreur future {dest['url']}: {e}")
                        
                        reclassify_status['progress'] = processed_count
                        reclassify_status['progress_percent'] = int(processed_count / len(destinations) * 100)
                    
                    # Petite pause entre les batches
                    time.sleep(0.1)
            
            reclassify_status['current_status'] = f'Terminé - {reclassify_status["updated_count"]} destinations re-classifiées (pays + catégories) avec threading 30x30'
            reclassify_status['current_url'] = None
            print(f"✅ Re-classification threading terminée: {reclassify_status['updated_count']} destinations mises à jour")
            
        except Exception as e:
            print(f"❌ Erreur re-classification threading: {e}")
            reclassify_status['current_status'] = f'Erreur: {str(e)}'
        finally:
            reclassify_status['is_running'] = False
    
    thread = threading.Thread(target=run_reclassification)
    thread.start()
    
    return jsonify({'success': True, 'message': 'Re-classification démarrée'})

@app.route('/api/consolidator/reclassify-status')
@login_required
def get_reclassify_status():
    return jsonify(reclassify_status)

@app.route('/api/consolidator/stop-reclassification', methods=['POST'])
@login_required
def stop_reclassification():
    global reclassify_status
    reclassify_status['is_running'] = False
    reclassify_status['current_status'] = 'Arrêté par l\'utilisateur'
    return jsonify({'success': True, 'message': 'Re-classification arrêtée'})

# Settings API Routes
@app.route('/api/settings/mappings')
@login_required
def get_category_mappings():
    mappings = db.get_category_mappings()
    return jsonify(mappings)

@app.route('/api/settings/mappings', methods=['POST'])
@login_required
def add_category_mapping():
    data = request.get_json()
    try:
        result = db.add_category_mapping(
            keyword=data['keyword'],
            category=data['category'],
            language=data.get('language', 'all')
        )
        return jsonify({'success': True, 'id': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/settings/mappings', methods=['PUT'])
@login_required
def update_category_mapping():
    data = request.get_json()
    try:
        result = db.update_category_mapping(
            mapping_id=data['id'],
            keyword=data['keyword'],
            category=data['category'],
            language=data.get('language', 'all')
        )
        return jsonify({'success': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/settings/mappings/<int:mapping_id>', methods=['DELETE'])
@login_required
def delete_category_mapping(mapping_id):
    try:
        result = db.delete_category_mapping(mapping_id)
        return jsonify({'success': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# Fonctions pour les thumbnails
def generate_thumbnail(image_url, size=(60, 60)):
    """Génère une thumbnail depuis une URL d'image"""
    try:
        # Créer le dossier thumbnails s'il n'existe pas
        os.makedirs('static/thumbnails', exist_ok=True)
        
        # Générer un nom de fichier basé sur l'URL
        url_hash = hashlib.md5(image_url.encode()).hexdigest()
        thumbnail_path = f'static/thumbnails/{url_hash}_{size[0]}x{size[1]}.jpg'
        
        # Si le thumbnail existe déjà, le retourner
        if os.path.exists(thumbnail_path):
            return f'/static/thumbnails/{url_hash}_{size[0]}x{size[1]}.jpg'
        
        print(f"📸 Génération thumbnail pour: {image_url}")
        
        # Télécharger l'image
        response = requests.get(image_url, timeout=10, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        response.raise_for_status()
        
        print(f"✅ Image téléchargée, taille: {len(response.content)} bytes")
        
        # Ouvrir l'image avec PIL
        img = Image.open(io.BytesIO(response.content))
        
        # Convertir en RGB si nécessaire
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Créer la thumbnail en gardant les proportions
        img.thumbnail(size, Image.Resampling.LANCZOS)
        
        # Créer une image carrée avec fond blanc
        thumb = Image.new('RGB', size, (255, 255, 255))
        
        # Centrer l'image redimensionnée
        offset = ((size[0] - img.size[0]) // 2, (size[1] - img.size[1]) // 2)
        thumb.paste(img, offset)
        
        # Sauvegarder
        thumb.save(thumbnail_path, 'JPEG', quality=85, optimize=True)
        
        print(f"✅ Thumbnail sauvegardée: {thumbnail_path}")
        return f'/static/thumbnails/{url_hash}_{size[0]}x{size[1]}.jpg'
        
    except Exception as e:
        print(f"❌ Erreur génération thumbnail pour {image_url}: {e}")
        return None

@app.route('/api/thumbnail')
@login_required
def get_thumbnail():
    """Endpoint pour générer et servir les thumbnails"""
    image_url = request.args.get('url')
    size = int(request.args.get('size', 60))
    
    if not image_url:
        # Retourner une SVG d'erreur
        error_svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}">
            <rect width="{size}" height="{size}" fill="#f5f5f5"/>
            <line x1="10" y1="10" x2="{size-10}" y2="{size-10}" stroke="#dc3545" stroke-width="3"/>
            <line x1="{size-10}" y1="10" x2="10" y2="{size-10}" stroke="#dc3545" stroke-width="3"/>
        </svg>'''
        return Response(error_svg, mimetype='image/svg+xml')
    
    thumbnail_url = generate_thumbnail(image_url, (size, size))
    
    if thumbnail_url:
        # Servir directement le fichier thumbnail
        thumbnail_path = thumbnail_url.replace('/static/', 'static/')
        if os.path.exists(thumbnail_path):
            return send_file(thumbnail_path, mimetype='image/jpeg')
        else:
            # Fichier introuvable, retourner SVG d'erreur
            error_svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}">
                <rect width="{size}" height="{size}" fill="#f5f5f5"/>
                <text x="50%" y="50%" text-anchor="middle" dy=".3em" fill="#999" font-size="8">404</text>
            </svg>'''
            return Response(error_svg, mimetype='image/svg+xml')
    else:
        # Retourner une SVG d'erreur
        error_svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}">
            <rect width="{size}" height="{size}" fill="#f5f5f5"/>
            <line x1="10" y1="10" x2="{size-10}" y2="{size-10}" stroke="#dc3545" stroke-width="3"/>
            <line x1="{size-10}" y1="10" x2="10" y2="{size-10}" stroke="#dc3545" stroke-width="3"/>
        </svg>'''
        return Response(error_svg, mimetype='image/svg+xml')

# Data Extraction API Routes (Stealth-Requests functionality)
@app.route('/api/extract/emails', methods=['POST'])
@login_required
def extract_emails():
    """Extract email addresses from a URL"""
    data = request.get_json()
    url = data.get('url')
    
    if not url:
        return jsonify({'error': 'URL is required'}), 400
    
    try:
        result = image_checker.extract_emails(url)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/extract/phones', methods=['POST'])
@login_required
def extract_phones():
    """Extract phone numbers from a URL"""
    data = request.get_json()
    url = data.get('url')
    
    if not url:
        return jsonify({'error': 'URL is required'}), 400
    
    try:
        result = image_checker.extract_phone_numbers(url)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/extract/images', methods=['POST'])
@login_required
def extract_images():
    """Extract images from a URL"""
    data = request.get_json()
    url = data.get('url')
    
    if not url:
        return jsonify({'error': 'URL is required'}), 400
    
    try:
        result = image_checker.extract_images(url)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/extract/links', methods=['POST'])
@login_required
def extract_links():
    """Extract links from a URL"""
    data = request.get_json()
    url = data.get('url')
    
    if not url:
        return jsonify({'error': 'URL is required'}), 400
    
    try:
        result = image_checker.extract_links(url)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/extract/all', methods=['POST'])
@login_required
def extract_all():
    """Extract emails, phone numbers, images, and links from a URL"""
    data = request.get_json()
    url = data.get('url')
    
    if not url:
        return jsonify({'error': 'URL is required'}), 400
    
    try:
        result = image_checker.extract_all_data(url)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/extract/batch', methods=['POST'])
@login_required
def extract_batch():
    """Extract data from multiple URLs"""
    data = request.get_json()
    urls = data.get('urls', [])
    extraction_types = data.get('types', ['all'])  # emails, phones, images, links, all
    
    if not urls:
        return jsonify({'error': 'URLs list is required'}), 400
    
    # Create a task for batch extraction
    task_description = f"Extraction batch - {len(urls)} URLs"
    task_id = task_manager.create_task('batch_extraction', task_description, len(urls))
    
    def run_batch_extraction():
        results = []
        
        for i, url in enumerate(urls):
            if not task_manager.is_task_running(task_id):
                break
            
            try:
                # Update task progress
                task_manager.update_task(task_id, 
                                       progress=i+1, 
                                       current_item=f'Extracting from {url}')
                
                # Extract data based on requested types
                url_results = {'url': url}
                
                if 'all' in extraction_types:
                    url_results.update(image_checker.extract_all_data(url))
                else:
                    if 'emails' in extraction_types:
                        url_results['emails'] = image_checker.extract_emails(url)
                    if 'phones' in extraction_types:
                        url_results['phones'] = image_checker.extract_phone_numbers(url)
                    if 'images' in extraction_types:
                        url_results['images'] = image_checker.extract_images(url)
                    if 'links' in extraction_types:
                        url_results['links'] = image_checker.extract_links(url)
                
                results.append(url_results)
                
            except Exception as e:
                print(f"❌ Error extracting data from {url}: {e}")
                results.append({
                    'url': url,
                    'error': str(e)
                })
        
        # Complete the task
        task_manager.update_task(task_id, results=results)
        task_manager.complete_task(task_id, success=True)
    
    thread = threading.Thread(target=run_batch_extraction)
    thread.start()
    
    return jsonify({
        'message': 'Batch extraction started',
        'task_id': task_id,
        'urls_count': len(urls),
        'extraction_types': extraction_types
    })

# Endpoints pour la gestion des URLs manquantes et statistiques historiques
@app.route('/api/verification/populate-missing', methods=['POST'])
@login_required
def populate_missing_urls():
    """Peuple la table verification_results avec toutes les URLs manquantes"""
    try:
        populated_count = db.populate_missing_verification_urls()
        return jsonify({
            'success': True,
            'populated_count': populated_count,
            'message': f'{populated_count} URLs manquantes ajoutées en base avec statut "pending"'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/verification/stats')
@login_required
def get_verification_stats():
    """Récupère les statistiques détaillées sur les vérifications"""
    try:
        stats = db.get_verification_stats()
        return jsonify({
            'success': True,
            'stats': stats
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/verification/unverified')
@login_required
def get_unverified_destinations():
    """Récupère toutes les destinations jamais vérifiées"""
    try:
        unverified = db.get_unverified_destinations()
        return jsonify({
            'success': True,
            'unverified': unverified,
            'count': len(unverified)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/verification/history/<path:url>')
@login_required
def get_url_verification_history(url):
    """Récupère l'historique complet des vérifications pour une URL"""
    try:
        history = db.get_verification_history_for_url(url)
        return jsonify({
            'success': True,
            'url': url,
            'history': history,
            'count': len(history)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    app.run(debug=True)