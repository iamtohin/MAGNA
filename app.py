from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
import sqlite3
from datetime import datetime
import uuid
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Database setup
def init_db():
    conn = sqlite3.connect('magna_kanban.db')
    cursor = conn.cursor()
    
    # Create tables if they don't exist
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS inventory (
        item_id TEXT PRIMARY KEY,
        item_name TEXT NOT NULL,
        part_number TEXT NOT NULL,
        location TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        min_threshold INTEGER NOT NULL,
        supplier TEXT NOT NULL,
        production_line TEXT NOT NULL
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS empty_signals (
        signal_id TEXT PRIMARY KEY,
        item_id TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        status TEXT NOT NULL,
        priority TEXT NOT NULL,
        production_line TEXT NOT NULL,
        FOREIGN KEY (item_id) REFERENCES inventory (item_id)
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS delivery_requests (
        request_id TEXT PRIMARY KEY,
        signal_id TEXT NOT NULL,
        item_id TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        destination TEXT NOT NULL,
        status TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        estimated_delivery TEXT,
        delivery_time TEXT,
        FOREIGN KEY (signal_id) REFERENCES empty_signals (signal_id),
        FOREIGN KEY (item_id) REFERENCES inventory (item_id)
    )
    ''')
    
    # Insert some sample data if inventory is empty
    cursor.execute("SELECT COUNT(*) FROM inventory")
    if cursor.fetchone()[0] == 0:
        sample_items = [
            ('MGP001', 'Door Panel Assemblies', 'DP-23456-A', 'Storage Area C5', 24, 5, 'Magna Exteriors', 'Door Assembly Line 1'),
            ('MGP002', 'Headlight Housings', 'HL-78901-B', 'Storage Area B2', 50, 10, 'Magna Lighting', 'Front End Assembly'),
            ('MGP003', 'Seat Frame Components', 'SF-34567-C', 'Storage Area D3', 36, 8, 'Magna Seating', 'Interior Assembly Line 2'),
            ('MGP004', 'Hood Latch Mechanisms', 'HLM-45678-D', 'Storage Area A1', 60, 12, 'Magna Closures', 'Body Shop Line 1'),
            ('MGP005', 'Side Mirror Assemblies', 'SM-56789-E', 'Storage Area B4', 40, 8, 'Magna Mirrors', 'Door Assembly Line 2'),
            ('MGP006', 'HVAC Control Modules', 'HCM-67890-F', 'Storage Area E2', 30, 6, 'Magna Electronics', 'Dashboard Assembly'),
            ('MGP007', 'Bumper Reinforcements', 'BR-78901-G', 'Storage Area C1', 20, 4, 'Magna Exteriors', 'Front End Assembly'),
            ('MGP008', 'Power Window Motors', 'PWM-89012-H', 'Storage Area D4', 48, 10, 'Magna Closures', 'Door Assembly Line 1')
        ]
        cursor.executemany('INSERT INTO inventory VALUES (?, ?, ?, ?, ?, ?, ?, ?)', sample_items)
    
    conn.commit()
    conn.close()

# Initialize database
init_db()

# Helper functions
def get_db_connection():
    conn = sqlite3.connect('magna_kanban.db')
    conn.row_factory = sqlite3.Row
    return conn

def get_inventory():
    conn = get_db_connection()
    rows = conn.execute('SELECT * FROM inventory ORDER BY production_line, item_name').fetchall()
    conn.close()

    inventory = []
    for row in rows:
        row = dict(row)
        try:
            row['quantity'] = int(row['quantity'])
            row['min_threshold'] = int(row['min_threshold'])
        except ValueError:
            row['quantity'] = 0
            row['min_threshold'] = 0

        # Compute low stock flag
        row['is_low_stock'] = row['quantity'] <= row['min_threshold']
        inventory.append(row)

    return inventory




def get_empty_signals():
    conn = get_db_connection()
    rows = conn.execute('''
        SELECT es.*, i.item_name, i.part_number, i.production_line 
        FROM empty_signals es 
        JOIN inventory i ON es.item_id = i.item_id 
        ORDER BY 
            CASE es.priority
                WHEN 'HIGH' THEN 1
                WHEN 'MEDIUM' THEN 2
                WHEN 'LOW' THEN 3
            END,
            es.timestamp DESC
    ''').fetchall()
    conn.close()

    signals = []
    for row in rows:
        signals.append(dict(row))
    return signals


def get_delivery_requests():
    conn = get_db_connection()
    rows = conn.execute('''
        SELECT dr.*, i.item_name, i.part_number, i.production_line
        FROM delivery_requests dr 
        JOIN inventory i ON dr.item_id = i.item_id 
        ORDER BY dr.timestamp DESC
    ''').fetchall()
    conn.close()

    requests = []
    for row in rows:
        row = dict(row)
        try:
            row['quantity'] = int(row['quantity'])
        except ValueError:
            row['quantity'] = 0
        requests.append(row)
    return requests


def get_production_lines():
    conn = get_db_connection()
    lines = conn.execute('SELECT DISTINCT production_line FROM inventory ORDER BY production_line').fetchall()
    conn.close()
    return [line['production_line'] for line in lines]

# Routes
@app.route('/')
def index():
    inventory = get_inventory()
    empty_signals = get_empty_signals()
    delivery_requests = get_delivery_requests()
    production_lines = get_production_lines()
    
    return render_template('index.html', 
                           inventory=inventory, 
                           empty_signals=empty_signals, 
                           delivery_requests=delivery_requests,
                           production_lines=production_lines)

@app.route('/create_empty_signal', methods=['POST'])
def create_empty_signal():
    item_id = request.form['item_id']
    priority = request.form.get('priority', 'MEDIUM')
    
    conn = get_db_connection()
    # Check if the item exists
    item = conn.execute('SELECT * FROM inventory WHERE item_id = ?', (item_id,)).fetchone()
    
    if not item:
        conn.close()
        flash('Component not found!')
        return redirect(url_for('index'))
    
    # Create empty signal
    signal_id = str(uuid.uuid4())
    timestamp = datetime.now().isoformat()
    
    conn.execute('INSERT INTO empty_signals VALUES (?, ?, ?, ?, ?, ?)', 
                 (signal_id, item_id, timestamp, 'PENDING', priority, item['production_line']))
    conn.commit()
    conn.close()
    
    flash('Empty kanban signal created successfully!')
    return redirect(url_for('index'))

@app.route('/avg_interface')
def avg_interface():
    empty_signals = get_empty_signals()
    inventory = get_inventory()
    production_lines = get_production_lines()
    
    # Filter only pending signals
    pending_signals = [signal for signal in empty_signals if signal['status'] == 'PENDING']
    
    return render_template('avg_interface.html', 
                           empty_signals=pending_signals,
                           inventory=inventory,
                           production_lines=production_lines)

@app.route('/process_empty_signal', methods=['POST'])
def process_empty_signal():
    signal_id = request.form['signal_id']
    item_id = request.form['item_id']
    quantity = int(request.form['quantity'])
    destination = request.form['destination']
    
    conn = get_db_connection()
    
    # Update signal status
    conn.execute('UPDATE empty_signals SET status = ? WHERE signal_id = ?', 
                 ('PROCESSING', signal_id))
    
    # Create delivery request
    request_id = str(uuid.uuid4())
    timestamp = datetime.now().isoformat()
    estimated_delivery = (datetime.now().replace(second=0, microsecond=0).timestamp() + 1800)  # 30 min from now
    estimated_delivery = datetime.fromtimestamp(estimated_delivery).isoformat()
    
    conn.execute('''
        INSERT INTO delivery_requests 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (request_id, signal_id, item_id, quantity, destination, 'PICKING', timestamp, estimated_delivery, None))
    
    conn.commit()
    conn.close()
    
    flash('Empty kanban signal processed and delivery request created!')
    return redirect(url_for('avg_interface'))

@app.route('/update_delivery_status/<request_id>/<status>')
def update_delivery_status(request_id, status):
    conn = get_db_connection()
    
    delivery_time = None
    if status == 'COMPLETED':
        delivery_time = datetime.now().isoformat()
    
    conn.execute('UPDATE delivery_requests SET status = ?, delivery_time = ? WHERE request_id = ?', 
                 (status, delivery_time, request_id))
    
    # If completed, update inventory and signal status
    if status == 'COMPLETED':
        delivery = conn.execute('SELECT * FROM delivery_requests WHERE request_id = ?', 
                                (request_id,)).fetchone()
        
        signal_id = delivery['signal_id']
        item_id = delivery['item_id']
        
        # Update signal status
        conn.execute('UPDATE empty_signals SET status = ? WHERE signal_id = ?', 
                     ('COMPLETED', signal_id))
        
        # Update inventory quantity
        conn.execute('''
            UPDATE inventory 
            SET quantity = quantity + ? 
            WHERE item_id = ?
        ''', (delivery['quantity'], item_id))
    
    conn.commit()
    conn.close()
    
    flash(f'Delivery status updated to {status}!')
    return redirect(url_for('index'))

@app.route('/filter_by_line/<line>')
def filter_by_line(line):
    if line == 'all':
        inventory = get_inventory()
    else:
        conn = get_db_connection()
        rows = conn.execute('SELECT * FROM inventory WHERE production_line = ? ORDER BY item_name', (line,)).fetchall()
        conn.close()

        inventory = []
        for row in rows:
            row = dict(row)
            try:
                row['quantity'] = int(row['quantity'])
                row['min_threshold'] = int(row['min_threshold'])
            except ValueError:
                row['quantity'] = 0
                row['min_threshold'] = 0
            inventory.append(row)

    return render_template('inventory_partial.html', inventory=inventory)



@app.route('/api/inventory')
def api_inventory():
    inventory = get_inventory()
    result = [dict(item) for item in inventory]
    return jsonify(result)

@app.route('/api/empty_signals')
def api_empty_signals():
    signals = get_empty_signals()
    result = [dict(signal) for signal in signals]
    return jsonify(result)

@app.route('/api/delivery_requests')
def api_delivery_requests():
    requests = get_delivery_requests()
    result = [dict(req) for req in requests]
    return jsonify(result)

@app.route('/api/production_status')
def api_production_status():
    # Get counts of components by production line
    conn = get_db_connection()
    lines = conn.execute('''
        SELECT production_line, 
               COUNT(*) as total_items,
               SUM(CASE WHEN quantity <= min_threshold THEN 1 ELSE 0 END) as low_stock
        FROM inventory
        GROUP BY production_line
    ''').fetchall()
    conn.close()
    
    result = [dict(line) for line in lines]
    return jsonify(result)

@app.route('/inventory_partial.html')
def inventory_partial():
    inventory = get_inventory()
    return render_template('inventory_partial.html', inventory=inventory)

if __name__ == '__main__':
    app.run(debug=True)