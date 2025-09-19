from flask import Flask, render_template, request, jsonify, redirect, url_for
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import requests
import time
import threading
import uuid
import json
import os

DATA_FILE = 'targets.json'

app = Flask(__name__)
scheduler = BackgroundScheduler()
scheduler.start()
lock = threading.Lock()

# Khởi tạo file data nếu chưa có
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, 'w') as f:
        json.dump({'targets': [], 'logs': {}}, f)


def load_data():
    with lock:
        with open(DATA_FILE, 'r') as f:
            return json.load(f)


def save_data(data):
    with lock:
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=2)


def ping_target(target_id):
    data = load_data()
    targets = data.get('targets', [])
    target = next((t for t in targets if t['id'] == target_id), None)
    if not target:
        return
    url = target['url']
    now = time.time()
    entry = {'ts': now}
    try:
        start = time.time()
        r = requests.get(url, timeout=10)
        elapsed = time.time() - start
        entry.update({'status': 'ok', 'code': r.status_code, 'time': round(elapsed, 3)})
    except Exception as e:
        entry.update({'status': 'error', 'error': str(e)})

    # lưu log
    data = load_data()
    logs = data.setdefault('logs', {})
    logs.setdefault(target_id, []).insert(0, entry)
    if len(logs[target_id]) > 200:
        logs[target_id] = logs[target_id][:200]
    save_data(data)


@app.route('/')
def index():
    data = load_data()
    return render_template('index.html', targets=data.get('targets', []))


@app.route('/add', methods=['POST'])
def add():
    url = request.form.get('url', '').strip()
    label = request.form.get('label', '').strip() or url
    interval = int(request.form.get('interval', '5'))
    if not url:
        return redirect(url_for('index'))
    data = load_data()
    tid = str(uuid.uuid4())
    target = {'id': tid, 'url': url, 'label': label, 'interval': interval, 'running': False}
    data.setdefault('targets', []).append(target)
    save_data(data)
    return redirect(url_for('index'))


@app.route('/start/<tid>', methods=['POST'])
def start(tid):
    data = load_data()
    target = next((t for t in data.get('targets', []) if t['id'] == tid), None)
    if not target:
        return jsonify({'ok': False, 'error': 'not found'}), 404
    if target.get('running'):
        return jsonify({'ok': True})
    trigger = IntervalTrigger(seconds=target.get('interval', 5))
    scheduler.add_job(lambda: ping_target(tid), trigger, id=tid, replace_existing=True)
    target['running'] = True
    save_data(data)
    return jsonify({'ok': True})


@app.route('/stop/<tid>', methods=['POST'])
def stop(tid):
    try:
        scheduler.remove_job(tid)
    except Exception:
        pass
    data = load_data()
    target = next((t for t in data.get('targets', []) if t['id'] == tid), None)
    if target:
        target['running'] = False
        save_data(data)
    return jsonify({'ok': True})


@app.route('/delete/<tid>', methods=['POST'])
def delete(tid):
    data = load_data()
    data['targets'] = [t for t in data.get('targets', []) if t['id'] != tid]
    if tid in data.get('logs', {}):
        data['logs'].pop(tid)
    try:
        scheduler.remove_job(tid)
    except Exception:
        pass
    save_data(data)
    return jsonify({'ok': True})


@app.route('/ping_now/<tid>', methods=['POST'])
def ping_now(tid):
    threading.Thread(target=ping_target, args=(tid,), daemon=True).start()
    return jsonify({'ok': True})


@app.route('/logs/<tid>')
def get_logs(tid):
    data = load_data()
    logs = data.get('logs', {}).get(tid, [])
    return jsonify({'ok': True, 'logs': logs[:50]})


@app.route('/list')
def get_list():
    data = load_data()
    return jsonify({'targets': data.get('targets', [])})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
