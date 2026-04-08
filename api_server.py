"""
Flask API Server for Vigilant AI Backend
Exposes REST endpoints without modifying core backend logic
"""

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import sqlite3
import json
import os
import subprocess
import threading
from datetime import datetime
from pathlib import Path
import utils.constants
from actions.agent_actions import actions, scenarios

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend integration

# Configuration
DB_NAME = "logs.db"
WORKING_FOLDER = utils.constants.LLM_WORKING_FOLDER
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Active scenario tracking
active_scenarios = {}
scenario_lock = threading.Lock()


# ============================================
# DATABASE UTILITIES
# ============================================

def get_db_connection():
    """Get SQLite database connection"""
    db_path = os.path.join(SCRIPT_DIR, DB_NAME)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def dict_from_row(row):
    """Convert SQLite row to dictionary"""
    return {key: row[key] for key in row.keys()}


# ============================================
# AGENT ENDPOINTS
# ============================================

@app.route('/api/agents', methods=['GET'])
def get_agents():
    """Get list of all available agents"""
    agents = [
        {
            "id": "caldera_agent",
            "name": "Caldera Agent",
            "role": "Adversary Emulation",
            "status": "idle",
            "description": "Executes commands on Caldera agents for red team operations",
            "lastUpdated": datetime.now().isoformat()
        },
        {
            "id": "internet_agent",
            "name": "Internet Agent",
            "role": "Intelligence Gathering",
            "status": "idle",
            "description": "Downloads and analyzes external threat intelligence",
            "lastUpdated": datetime.now().isoformat()
        },
        {
            "id": "text_analyst_agent",
            "name": "Text Analyst",
            "role": "Analysis",
            "status": "idle",
            "description": "Analyzes and summarizes security data",
            "lastUpdated": datetime.now().isoformat()
        },
        {
            "id": "cmd_exec_agent",
            "name": "Command Executor",
            "role": "Code Execution",
            "status": "idle",
            "description": "Executes shell commands and scripts",
            "lastUpdated": datetime.now().isoformat()
        }
    ]
    
    # Update status based on active scenarios
    with scenario_lock:
        for agent in agents:
            for scenario_id, scenario_data in active_scenarios.items():
                if scenario_data['status'] == 'running':
                    agents_in_scenario = scenario_data.get('agents', [])
                    if agent['id'] in agents_in_scenario:
                        agent['status'] = 'active'
                        break
    
    return jsonify(agents)


@app.route('/api/agents/<agent_id>', methods=['GET'])
def get_agent(agent_id):
    """Get specific agent details"""
    agents = {
        "caldera_agent": {
            "id": "caldera_agent",
            "name": "Caldera Agent",
            "role": "Adversary Emulation",
            "status": "idle",
            "description": "Executes commands on Caldera agents for red team operations",
            "capabilities": ["command_execution", "caldera_api", "adversary_simulation"],
            "lastUpdated": datetime.now().isoformat()
        },
        "internet_agent": {
            "id": "internet_agent",
            "name": "Internet Agent",
            "role": "Intelligence Gathering",
            "status": "idle",
            "description": "Downloads and analyzes external threat intelligence",
            "capabilities": ["web_scraping", "threat_intel", "data_collection"],
            "lastUpdated": datetime.now().isoformat()
        },
        "text_analyst_agent": {
            "id": "text_analyst_agent",
            "name": "Text Analyst",
            "role": "Analysis",
            "status": "idle",
            "description": "Analyzes and summarizes security data",
            "capabilities": ["text_analysis", "summarization", "reporting"],
            "lastUpdated": datetime.now().isoformat()
        },
        "cmd_exec_agent": {
            "id": "cmd_exec_agent",
            "name": "Command Executor",
            "role": "Code Execution",
            "status": "idle",
            "description": "Executes shell commands and scripts",
            "capabilities": ["shell_execution", "script_running", "system_commands"],
            "lastUpdated": datetime.now().isoformat()
        }
    }
    
    agent = agents.get(agent_id)
    if not agent:
        return jsonify({"error": "Agent not found"}), 404
    
    return jsonify(agent)


# ============================================
# LOGS ENDPOINTS
# ============================================

@app.route('/api/logs', methods=['GET'])
def get_logs():
    """Get logs from SQLite database"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get query parameters
        limit = request.args.get('limit', 100, type=int)
        level = request.args.get('level', None)
        agent = request.args.get('agent', None)
        
        query = "SELECT * FROM chat_completions ORDER BY start_time DESC LIMIT ?"
        cursor.execute(query, (limit,))
        
        rows = cursor.fetchall()
        logs = []
        
        for row in rows:
            log_entry = dict_from_row(row)
            
            # Parse request and response JSON
            if log_entry.get('request'):
                try:
                    log_entry['request'] = json.loads(log_entry['request'])
                except:
                    pass
            
            if log_entry.get('response'):
                try:
                    log_entry['response'] = json.loads(log_entry['response'])
                except:
                    pass
            
            logs.append(log_entry)
        
        conn.close()
        
        return jsonify({
            "logs": logs,
            "total": len(logs)
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/logs/stats', methods=['GET'])
def get_log_stats():
    """Get aggregated log statistics"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Total tokens and cost
        cursor.execute("""
            SELECT 
                COUNT(*) as total_logs,
                SUM(cost) as total_cost
            FROM chat_completions
        """)
        
        stats = dict_from_row(cursor.fetchone())
        
        # Get session count
        cursor.execute("SELECT COUNT(DISTINCT session_id) as session_count FROM chat_completions")
        session_data = dict_from_row(cursor.fetchone())
        stats['total_sessions'] = session_data['session_count']
        
        conn.close()
        
        return jsonify(stats)
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================
# SCENARIOS ENDPOINTS
# ============================================

@app.route('/api/scenarios', methods=['GET'])
def get_scenarios():
    """Get list of available scenarios"""
    scenario_list = []
    
    for scenario_name, action_names in scenarios.items():
        scenario_agents = set()
        step_count = 0
        
        for action_name in action_names:
            if action_name in actions:
                for action in actions[action_name]:
                    scenario_agents.add(action['agent'])
                    step_count += 1
        
        scenario_list.append({
            "id": scenario_name,
            "name": scenario_name.replace('_', ' ').title(),
            "description": f"Scenario with {step_count} steps",
            "agents": list(scenario_agents),
            "stepCount": step_count,
            "status": active_scenarios.get(scenario_name, {}).get('status', 'idle')
        })
    
    return jsonify(scenario_list)


@app.route('/api/scenarios/<scenario_id>/run', methods=['POST'])
def run_scenario(scenario_id):
    """Run a specific scenario"""
    if scenario_id not in scenarios:
        return jsonify({"error": "Scenario not found"}), 404
    
    # Check if already running
    with scenario_lock:
        if scenario_id in active_scenarios and active_scenarios[scenario_id]['status'] == 'running':
            return jsonify({"error": "Scenario already running"}), 409
        
        # Mark as running
        active_scenarios[scenario_id] = {
            "status": "running",
            "started_at": datetime.now().isoformat(),
            "agents": []
        }
    
    # Run scenario in background thread
    def run_scenario_thread():
        try:
            script_path = os.path.join(SCRIPT_DIR, "run_agents.py")
            result = subprocess.run(
                ["python", script_path, scenario_id],
                capture_output=True,
                text=True,
                cwd=SCRIPT_DIR
            )
            
            with scenario_lock:
                active_scenarios[scenario_id]['status'] = 'completed' if result.returncode == 0 else 'failed'
                active_scenarios[scenario_id]['completed_at'] = datetime.now().isoformat()
                active_scenarios[scenario_id]['output'] = result.stdout
                active_scenarios[scenario_id]['error'] = result.stderr
        
        except Exception as e:
            with scenario_lock:
                active_scenarios[scenario_id]['status'] = 'failed'
                active_scenarios[scenario_id]['error'] = str(e)
    
    thread = threading.Thread(target=run_scenario_thread)
    thread.daemon = True
    thread.start()
    
    return jsonify({
        "message": "Scenario started",
        "scenario_id": scenario_id,
        "status": "running"
    })


@app.route('/api/scenarios/<scenario_id>/status', methods=['GET'])
def get_scenario_status(scenario_id):
    """Get status of a running scenario"""
    with scenario_lock:
        scenario_data = active_scenarios.get(scenario_id)
        
        if not scenario_data:
            return jsonify({"status": "not_started"})
        
        return jsonify(scenario_data)


# ============================================
# ARTIFACTS ENDPOINTS
# ============================================

@app.route('/api/artifacts', methods=['GET'])
def get_artifacts():
    """Get list of all artifacts"""
    artifacts = []
    working_dir = os.path.join(SCRIPT_DIR, WORKING_FOLDER)
    
    # Scan subfolders
    for subfolder in ['caldera', 'code', 'pdf', 'http_server', 'ftp_server']:
        folder_path = os.path.join(working_dir, subfolder)
        
        if not os.path.exists(folder_path):
            continue
        
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, working_dir)
                
                try:
                    stat = os.stat(file_path)
                    artifacts.append({
                        "id": rel_path.replace('\\', '/'),
                        "name": file,
                        "type": subfolder,
                        "path": rel_path.replace('\\', '/'),
                        "size": stat.st_size,
                        "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
                    })
                except:
                    pass
    
    return jsonify(artifacts)


@app.route('/api/artifacts/<path:artifact_path>', methods=['GET'])
def get_artifact(artifact_path):
    """Download a specific artifact"""
    working_dir = os.path.join(SCRIPT_DIR, WORKING_FOLDER)
    file_path = os.path.join(working_dir, artifact_path)
    
    # Security: ensure path is within working folder
    file_path = os.path.normpath(file_path)
    working_dir = os.path.normpath(working_dir)
    
    if not file_path.startswith(working_dir):
        return jsonify({"error": "Invalid path"}), 403
    
    if not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404
    
    return send_file(file_path)


# ============================================
# COORDINATOR ENDPOINTS
# ============================================

@app.route('/api/coordinator/status', methods=['GET'])
def get_coordinator_status():
    """Get coordinator status"""
    active_count = sum(1 for s in active_scenarios.values() if s['status'] == 'running')
    
    # Get current running scenario
    current_scenario = None
    for scenario_id, scenario_data in active_scenarios.items():
        if scenario_data['status'] == 'running':
            current_scenario = scenarios.get(scenario_id, [])
            if current_scenario:
                # Get scenario name (convert ID to readable name)
                current_scenario = scenario_id.replace('_', ' ').title()
            break
    
    return jsonify({
        "status": "active" if active_count > 0 else "idle",
        "activeScenarios": active_count,
        "totalScenarios": len(scenarios),
        "activeAgents": active_count,
        "currentScenario": current_scenario,
        "completedTasks": 0,
        "pendingTasks": 0,
        "uptime": "unknown",
        "serverStatus": {
            "http": "online",
            "ftp": "online",
            "database": "online"
        }
    })


# ============================================
# HEALTH CHECK
# ============================================

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    })


# ============================================
# MAIN
# ============================================

if __name__ == '__main__':
    port = int(os.getenv('PORT', os.getenv('API_PORT', 5000)))
    print(f"Starting Vigilant AI API Server on port {port}...")
    debug = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)
