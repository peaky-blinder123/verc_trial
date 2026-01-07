import requests
import threading
import time
import random  # <--- Ensure this is imported
import json
import base64
from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for
import logging
import re
import os

app = Flask(__name__)
# Security: Use environment variables in production
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'vercel_secret_key_default')
APP_PASSWORD = os.environ.get('APP_PASSWORD', "admin") 

# =============================================================================
# BACKEND LOGIC
# =============================================================================

def login_and_get_cookie(username, password):
    url = "https://student.bennetterp.camu.in/login/validate"
    headers = {
        "Content-Type": "application/json", "Origin": "https://student.bennetterp.camu.in",
        "Referer": "https://student.bennetterp.camu.in/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    }
    payload = {"dtype": "M", "Email": username, "pwd": password}
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=5)
        if "invalid" in r.text.lower() or "fail" in r.text.lower():
            return None
        if r.status_code == 200 and 'Set-Cookie' in r.headers:
            return r.headers['Set-Cookie'] 
    except:
        pass
    return None

def mark_with_cookie(username, attendance_id, stu_id, cookie_str, output_log):
    url = "https://student.bennetterp.camu.in/api/Attendance/record-online-attendance"
    headers = {
        "Accept": "application/json, text/plain, */*", "Content-Type": "application/json",
        "Cookie": cookie_str, 
        "Origin": "https://student.bennetterp.camu.in",
        "Referer": "https://student.bennetterp.camu.in/v2/timetable",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    }
    payload = {"attendanceId": attendance_id, "StuID": stu_id, "offQrCdEnbld": True}
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=4)
        output_log.append(f"📊 [{username}] Status: {r.status_code} | {r.text.strip()}")
    except Exception as e:
        output_log.append(f"❌ [{username}] Failed: {e}")

def process_student_stateless(student, attendance_id, output_log):
    email = student.get('email')
    cookie = student.get('cookie') 
    
    if not cookie:
        output_log.append(f"⚠️ [{email}] No cookie. Logging in...")
        cookie = login_and_get_cookie(email, student.get('password'))
    
    if cookie:
        mark_with_cookie(email, attendance_id, student.get('stu_id'), cookie, output_log)
    else:
        output_log.append(f"❌ [{email}] Login failed.")

def parse_logs(logs, students):
    results = []
    for s in students:
        email = s.get('email')
        status = "Pending"
        resp = "No response"
        
        student_logs = [l for l in logs if f"[{email}]" in l]
        for l in student_logs:
            lower_l = l.lower()
            if "status: 200" in lower_l and "suc" in lower_l:
                status = "Success"
                resp = "Marked Successfully"
            elif "already marked" in lower_l or "already submitted" in lower_l:
                status = "Success" 
                resp = "Already Marked (Done)"
            elif "attendance not valid" in lower_l:
                status = "Failed"
                resp = "Invalid QR (Expired)"
            elif "status:" in lower_l:
                status = "Failed" 
                resp = "Server Error"
            elif "login failed" in lower_l:
                status = "Auth Error"
                resp = "Login Failed"

        results.append({"email": email, "status": status, "response": resp})
    return results

# =============================================================================
# ROUTES
# =============================================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('password') == APP_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('index'))
    return render_template_string(LOGIN_TEMPLATE)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
def index():
    if not session.get('logged_in'): return redirect(url_for('login'))
    return render_template_string(HTML_TEMPLATE)

@app.route('/pre-login', methods=['POST'])
def pre_login_endpoint():
    data = request.json
    students = data.get('students', [])
    results = []
    
    def worker(s):
        c = login_and_get_cookie(s['email'], s['password'])
        status = "Ready" if c else "Failed"
        results.append({"email": s['email'], "status": status, "cookie": c})

    threads = []
    for s in students:
        t = threading.Thread(target=worker, args=(s,))
        threads.append(t)
        t.start()
        time.sleep(0.15) 

    for t in threads: t.join()
        
    return jsonify({"results": results})

@app.route('/mark-attendance', methods=['POST'])
def mark_attendance_endpoint():
    data = request.json
    aid = data.get('attendance_id')
    students = data.get('students') 
    
    output_log = []
    threads = []
    
    for s in students:
        t = threading.Thread(target=process_student_stateless, args=(s, aid, output_log))
        threads.append(t)
        t.start()
        
        # --- NEW RANDOM STAGGER ---
        # Random sleep between 0.1s and 0.14s
        time.sleep(random.uniform(0.1, 0.14))

    for t in threads: t.join()
            
    return jsonify({"logs": output_log, "table_data": parse_logs(output_log, students)})

# =============================================================================
# TEMPLATES (SaaS UI + Dark Mode + Working Zoom)
# =============================================================================

LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login | Attendance</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Inter', sans-serif; background: #0f172a; color: #f1f5f9; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        form { background: #1e293b; padding: 2.5rem; border-radius: 16px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.5); width: 100%; max-width: 320px; text-align: center; border: 1px solid #334155; }
        h2 { margin-top: 0; color: white; font-weight: 600; }
        input { width: 100%; padding: 12px; margin: 15px 0; border: 1px solid #334155; background: #0f172a; color: white; border-radius: 8px; font-size: 1rem; box-sizing: border-box; outline: none; transition: 0.2s; }
        input:focus { border-color: #3b82f6; }
        button { width: 100%; padding: 12px; background: #3b82f6; color: white; border: none; border-radius: 8px; font-weight: 600; cursor: pointer; transition: 0.2s; font-size: 1rem; }
        button:hover { background: #2563eb; }
    </style>
</head>
<body>
    <form method="post">
        <h2>Attendance Bot</h2>
        <input type="password" name="password" placeholder="Enter Access Password" required autofocus>
        <button type="submit">Unlock Dashboard</button>
    </form>
</body>
</html>
"""

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Attendance Dashboard</title>
    <script src="https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        /* LIGHT THEME (Default) */
        :root {
            --bg-color: #f8fafc;
            --card-bg: #ffffff;
            --text-main: #1e293b;
            --text-muted: #64748b;
            --primary: #3b82f6;
            --primary-dark: #2563eb;
            --secondary: #10b981;
            --danger: #ef4444;
            --border: #e2e8f0;
            --input-bg: #f8fafc;
            --shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
            --switch-bg: #cbd5e1;
            --switch-knob: #ffffff;
            --row-hover: #f1f5f9;
        }

        /* DARK THEME (Class) */
        body.dark-mode {
            --bg-color: #0f172a;
            --card-bg: #1e293b;
            --text-main: #f1f5f9;
            --text-muted: #94a3b8;
            --primary: #60a5fa;
            --primary-dark: #3b82f6;
            --secondary: #34d399;
            --danger: #f87171;
            --border: #334155;
            --input-bg: #0f172a;
            --shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.5);
            --switch-bg: #475569;
            --switch-knob: #e2e8f0;
            --row-hover: #334155;
        }

        body {
            font-family: 'Inter', sans-serif;
            background: var(--bg-color);
            color: var(--text-main);
            margin: 0;
            padding: 1rem;
            -webkit-font-smoothing: antialiased;
            transition: background 0.3s ease, color 0.3s ease;
        }

        /* HEADER */
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1.5rem;
            max-width: 1000px;
            margin-left: auto;
            margin-right: auto;
        }
        .header h3 { font-size: 1.25rem; font-weight: 700; margin: 0; display: flex; align-items: center; gap: 8px; }
        .header-actions { display: flex; gap: 10px; align-items: center; }
        
        .btn-icon { background: var(--card-bg); border: 1px solid var(--border); color: var(--text-main); padding: 8px; border-radius: 8px; cursor: pointer; transition: 0.2s; display: flex; align-items: center; justify-content: center; width: 36px; height: 36px; }
        .btn-icon:hover { background: var(--border); }

        .logout { color: var(--text-muted); font-size: 0.875rem; text-decoration: none; font-weight: 500; padding: 6px 12px; background: var(--card-bg); border-radius: 6px; border: 1px solid var(--border); transition: 0.2s; }
        .logout:hover { background: var(--border); color: var(--text-main); }

        /* LAYOUT */
        .wrapper {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1.5rem;
            max-width: 1000px;
            margin: 0 auto;
        }

        .panel {
            background: var(--card-bg);
            padding: 1.5rem;
            border-radius: 16px;
            box-shadow: var(--shadow);
            border: 1px solid var(--border);
            display: flex;
            flex-direction: column;
            transition: background 0.3s ease, border-color 0.3s ease;
        }

        /* COMPONENTS */
        label { font-size: 0.85rem; font-weight: 600; color: var(--text-muted); margin-bottom: 6px; display: block; text-transform: uppercase; letter-spacing: 0.025em; }
        
        select, input[type="text"] {
            width: 100%;
            padding: 12px 14px;
            border: 1px solid var(--border);
            border-radius: 10px;
            font-size: 0.95rem;
            color: var(--text-main);
            background-color: var(--input-bg);
            outline: none;
            transition: all 0.2s;
            box-sizing: border-box;
            appearance: none;
            margin-bottom: 1rem;
        }
        select:focus, input:focus { border-color: var(--primary); box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2); }

        button {
            width: 100%;
            padding: 14px;
            border: none;
            border-radius: 10px;
            font-size: 0.95rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
        }
        button:active { transform: scale(0.98); }

        .btn-primary { background: var(--primary); color: white; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); }
        .btn-primary:hover { background: var(--primary-dark); }
        
        .btn-warn { background: #f59e0b; color: white; }
        .btn-warn:hover { background: #d97706; }
        
        .btn-ready { background: var(--secondary); color: white; }
        .btn-stop { background: var(--danger); color: white; }
        
        .btn-outline { background: var(--card-bg); border: 1px solid var(--border); color: var(--text-main); }
        .btn-outline:hover { background: var(--border); }

        /* LIST */
        #list { flex-grow: 1; overflow-y: auto; margin: 1rem 0; border-radius: 8px; max-height: 400px; }
        .status-row { display: flex; justify-content: space-between; align-items: center; padding: 12px 14px; background: var(--input-bg); border: 1px solid var(--border); margin-bottom: 8px; border-radius: 8px; transition: 0.2s; }
        .status-row:hover { transform: translateY(-1px); background: var(--row-hover); }
        .st-name { font-weight: 500; font-size: 0.9rem; }
        .st-badge { font-size: 0.75rem; font-weight: 600; padding: 4px 10px; border-radius: 99px; display: inline-flex; align-items: center; gap: 4px; }

        /* TOGGLE */
        .switch-container { display: flex; align-items: center; justify-content: space-between; background: var(--input-bg); padding: 12px 16px; border-radius: 12px; margin-bottom: 1.25rem; border: 1px solid var(--border); }
        .switch-label { font-size: 0.9rem; font-weight: 600; color: var(--text-main); display: flex; align-items: center; gap: 8px; }
        .toggle-checkbox { appearance: none; width: 48px; height: 26px; background: var(--switch-bg); border-radius: 99px; position: relative; cursor: pointer; transition: 0.3s; outline: none; }
        .toggle-checkbox::after { content: ''; position: absolute; top: 3px; left: 3px; width: 20px; height: 20px; background: var(--switch-knob); border-radius: 50%; transition: 0.3s; box-shadow: 0 2px 4px rgba(0,0,0,0.2); }
        .toggle-checkbox:checked { background: var(--secondary); }
        .toggle-checkbox:checked::after { transform: translateX(22px); }

        /* SCANNER & ZOOM */
        #reader { border-radius: 12px; overflow: hidden; margin-bottom: 1rem; background: black; border: 2px solid var(--border); }
        
        /* ZOOM SLIDER STYLE */
        #zoom-controls { display: flex; align-items: center; gap: 10px; margin-bottom: 1rem; background: var(--input-bg); padding: 10px; border-radius: 10px; border: 1px solid var(--border); }
        .zoom-label { font-size: 0.8rem; font-weight: 600; color: var(--text-muted); }
        input[type=range] { -webkit-appearance: none; width: 100%; background: transparent; padding: 0; margin: 0; border: none; }
        input[type=range]::-webkit-slider-thumb { -webkit-appearance: none; height: 16px; width: 16px; border-radius: 50%; background: var(--primary); cursor: pointer; margin-top: -6px; }
        input[type=range]::-webkit-slider-runnable-track { width: 100%; height: 4px; cursor: pointer; background: var(--switch-bg); border-radius: 2px; }

        .file-upload-wrapper { display: flex; gap: 10px; margin-top: auto; }
        .file-label { flex: 1; text-align: center; cursor: pointer; font-size: 0.9rem; font-weight: 500; padding: 12px; background: var(--input-bg); border: 1px dashed var(--text-muted); border-radius: 10px; color: var(--text-muted); transition: 0.2s; }
        .file-label:hover { border-color: var(--primary); color: var(--primary); }

        .hidden { display: none !important; }
        
        /* RESULT OVERLAY */
        #result-box { position: fixed; bottom: 0; left: 0; right: 0; top: 0; background: rgba(0,0,0,0.8); backdrop-filter: blur(5px); z-index: 100; padding: 2rem; display: flex; flex-direction: column; justify-content: center; max-width: 600px; margin: auto; }
        .result-content { background: var(--card-bg); padding: 1.5rem; border-radius: 16px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); border: 1px solid var(--border); }
        #log { background: var(--input-bg); padding: 1rem; border-radius: 12px; font-family: monospace; font-size: 0.85rem; color: var(--text-muted); border: 1px solid var(--border); margin-bottom: 1rem; max-height: 40vh; overflow-y: auto; }

        @media (max-width: 768px) {
            .wrapper { grid-template-columns: 1fr; }
            .header { margin-bottom: 1rem; }
            button { padding: 16px; font-size: 1rem; } 
        }
    </style>
</head>
<body>

    <div class="header">
        <h3>
            <span style="background:var(--primary); color:white; width:28px; height:28px; display:flex; align-items:center; justify-content:center; border-radius:8px; font-size:16px;">⚡</span>
            Attendance
        </h3>
        <div class="header-actions">
            <button class="btn-icon" id="theme-toggle" title="Toggle Theme">
                <span id="theme-icon">🌙</span>
            </button>
            <a href="/logout" class="logout">Log Out</a>
        </div>
    </div>

    <div class="wrapper">
        <div class="panel">
            <label>Select Subject</label>
            <select id="subject-filter">
                <option value="ALL">Select Subject...</option>
                <option value="c_333">C_333 (Networks)</option>
                <option value="eco_311">ECO_311 (Economics)</option>
                <option value="ains_485">AINS_485</option>
                <option value="acv_340">ACV_340 (Vision)</option>
                <option value="ladv_395">LADV_395</option>
                <option value="cskill_308">CSKILL_308</option>
                <option value="genai_419">GENAI_419</option>
                <option value="spm_324">SPM_324</option>
                <option value="orgb_309">ORGB_309</option>
            </select>

            <button class="btn-warn" id="pre-login-btn">Initialize Sessions</button>

            <div style="display:flex; justify-content:space-between; align-items:center; margin-top:1.5rem; margin-bottom:0.5rem;">
                <label style="margin:0;">Queue</label>
                <span id="queue-status" style="font-size:0.75rem; color:var(--text-muted); font-weight:600;">0 Waiting</span>
            </div>

            <div id="list">
                <div style="padding:20px; text-align:center; color:var(--text-muted);">
                    Select a subject to load students.
                </div>
            </div>

            <div class="file-upload-wrapper">
                <label class="file-label">
                    📂 Load JSON <input type="file" id="json-upload" hidden>
                </label>
                <button class="btn-outline" style="flex:1" onclick="resetQueue()">🔄 Reset</button>
            </div>
        </div>

        <div class="panel" id="scan-box">
            <div class="switch-container">
                <span class="switch-label">⚡ Auto-Send Mode</span>
                <input type="checkbox" id="auto-send-toggle" class="toggle-checkbox" checked>
            </div>

            <div id="reader" class="hidden"></div>
            
            <div id="zoom-controls" class="hidden">
                <span class="zoom-label">Zoom</span>
                <input type="range" id="zoom-slider" min="1" max="5" step="0.1" value="1">
            </div>

            <button class="btn-primary" id="start-cam" style="height: 120px; font-size: 1.1rem;">
                📷 Start Camera
            </button>
            
            <button class="btn-stop hidden" id="stop-cam">Stop Camera</button>

            <div style="margin-top:auto; padding-top:1.5rem;">
                <label>Manual Entry</label>
                <div style="display:flex; gap:10px;">
                    <input type="text" id="manual-code" placeholder="Paste QR Text" style="margin-bottom:0;">
                    <button id="use-text" class="btn-outline" style="width:auto; padding:0 20px;">Use</button>
                </div>
            </div>
        </div>
    </div>

    <div id="result-box" class="hidden">
        <div class="result-content">
            <h2 style="margin-top:0;">Processing...</h2>
            <div id="log"></div>
            <button id="next-qr-btn" class="btn-ready" style="padding: 16px; font-size:1.1rem; margin-bottom:10px;">
                📷 Scan Next QR
            </button>
            <button onclick="closeResults()" class="btn-outline">Close</button>
        </div>
    </div>

    <audio id="beep" src="data:audio/wav;base64,UklGRl9vT19XQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YU9vT19PANkPCz4/rgr5Cg8+v60K+g4QPj/9CvoODz/APww/QD8P/w8+P/8K+g4QPj+tCvoODz6/rQr5Cg8+P60K+QoPPg=="></audio>

    <script>
        const themeToggle = document.getElementById('theme-toggle');
        const themeIcon = document.getElementById('theme-icon');
        const body = document.body;

        if (localStorage.getItem('theme') === 'dark') {
            body.classList.add('dark-mode');
            themeIcon.innerText = '☀️';
        }

        themeToggle.addEventListener('click', () => {
            body.classList.toggle('dark-mode');
            const isDark = body.classList.contains('dark-mode');
            themeIcon.innerText = isDark ? '☀️' : '🌙';
            localStorage.setItem('theme', isDark ? 'dark' : 'light');
        });

        let allStudents = [];
        let filteredStudents = []; 
        let storedCookies = {}; 
        let completedEmails = new Set(); 
        let retryCounts = {}; 
        let scanner = null;
        let isCameraRunning = false; 

        const dom = {
            subject: document.getElementById('subject-filter'),
            list: document.getElementById('list'),
            preLogin: document.getElementById('pre-login-btn'),
            scanBox: document.getElementById('scan-box'),
            resBox: document.getElementById('result-box'),
            log: document.getElementById('log'),
            qStatus: document.getElementById('queue-status'),
            autoToggle: document.getElementById('auto-send-toggle'),
            zoomControls: document.getElementById('zoom-controls'),
            zoomSlider: document.getElementById('zoom-slider')
        };

        window.addEventListener('DOMContentLoaded', () => {
            if(localStorage.getItem('my_students')) allStudents = JSON.parse(localStorage.getItem('my_students'));
            if(localStorage.getItem('my_cookies')) storedCookies = JSON.parse(localStorage.getItem('my_cookies'));
            if(localStorage.getItem('my_completed')) completedEmails = new Set(JSON.parse(localStorage.getItem('my_completed')));
            if(localStorage.getItem('my_retries')) retryCounts = JSON.parse(localStorage.getItem('my_retries'));
            applyFilter();
        });

        function saveQueueState() {
            localStorage.setItem('my_completed', JSON.stringify([...completedEmails]));
            localStorage.setItem('my_retries', JSON.stringify(retryCounts));
        }

        function resetQueue() {
            if(confirm("Reset status for all students?")) {
                completedEmails.clear();
                retryCounts = {};
                saveQueueState();
                render();
            }
        }
        
        document.getElementById('json-upload').addEventListener('change', (e) => {
            const reader = new FileReader();
            reader.onload = (ev) => {
                try {
                    const data = JSON.parse(ev.target.result);
                    if(data.students) {
                        allStudents = data.students;
                        localStorage.setItem('my_students', JSON.stringify(allStudents));
                        alert(`Loaded ${allStudents.length} students`);
                        applyFilter();
                    }
                } catch(err) { alert("Invalid JSON"); }
            };
            reader.readAsText(e.target.files[0]);
        });

        dom.subject.addEventListener('change', applyFilter);
        
        function applyFilter() {
            const sub = dom.subject.value;
            filteredStudents = (sub === "ALL") ? allStudents : allStudents.filter(s => s.subjects && s.subjects.includes(sub));
            render();
        }

        function render() {
            dom.list.innerHTML = '';
            if (filteredStudents.length === 0) {
                dom.list.innerHTML = '<div style="padding:20px; text-align:center; color:var(--text-muted);">No students found for this subject.</div>';
                return;
            }

            let pendingCount = 0;
            let readyCount = 0;

            filteredStudents.forEach(s => {
                const hasCookie = !!storedCookies[s.email];
                if(hasCookie) readyCount++;

                const isDone = completedEmails.has(s.email);
                const fails = retryCounts[s.email] || 0;
                
                let badgeClass = 'color:#f59e0b; background:var(--input-bg); border:1px solid #f59e0b;'; 
                let icon = '⭕'; let text = 'Pending';
                
                if (isDone) { icon = '✅'; badgeClass = 'color:#10b981; background:var(--input-bg); border:1px solid #10b981;'; text = 'Done'; }
                else if (fails >= 2) { icon = '❌'; badgeClass = 'color:#ef4444; background:var(--input-bg); border:1px solid #ef4444;'; text = 'Stopped'; }
                else if (!hasCookie) { icon = '⚠️'; badgeClass = 'color:#f59e0b; background:var(--input-bg); border:1px solid #f59e0b;'; text = 'Login Req'; pendingCount++; }
                else { icon = '⚡'; badgeClass = 'color:#3b82f6; background:var(--input-bg); border:1px solid #3b82f6;'; text = 'Ready'; pendingCount++; }

                dom.list.innerHTML += `
                    <div class="status-row">
                        <span class="st-name">${s.email.split('@')[0]}</span>
                        <span class="st-badge" style="${badgeClass}">
                            ${icon} ${text}
                        </span>
                    </div>`;
            });

            if (readyCount === filteredStudents.length && filteredStudents.length > 0) {
                dom.preLogin.innerText = "Session Ready";
                dom.preLogin.className = "btn-ready";
            } else {
                dom.preLogin.innerText = "Initialize Sessions";
                dom.preLogin.className = "btn-warn";
            }
            dom.qStatus.innerText = `${pendingCount} Pending`;
        }

        dom.preLogin.addEventListener('click', async () => {
            if(!filteredStudents.length) return;
            dom.preLogin.innerText = "Connecting...";
            dom.preLogin.disabled = true;
            try {
                const res = await fetch('/pre-login', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ students: filteredStudents })
                });
                const data = await res.json();
                data.results.forEach(r => { if(r.cookie) storedCookies[r.email] = r.cookie; });
                localStorage.setItem('my_cookies', JSON.stringify(storedCookies));
                render();
            } catch(e) { alert("Error: " + e); }
            dom.preLogin.disabled = false;
        });

        // ZOOM LOGIC FROM YOUR ORIGINAL FILE
        function setupZoom() {
            try {
                setTimeout(() => {
                    const videoElement = document.querySelector("#reader video");
                    if (!videoElement || !videoElement.srcObject) return;
                    
                    const [track] = videoElement.srcObject.getVideoTracks();
                    if (!track) return;

                    const capabilities = track.getCapabilities();
                    if (capabilities.zoom) {
                        dom.zoomSlider.min = capabilities.zoom.min;
                        dom.zoomSlider.max = capabilities.zoom.max;
                        dom.zoomSlider.step = capabilities.zoom.step || 0.1;
                        dom.zoomSlider.value = track.getSettings().zoom || capabilities.zoom.min;
                        
                        dom.zoomControls.classList.remove('hidden');

                        dom.zoomSlider.addEventListener('input', (event) => {
                            const zoomValue = parseFloat(event.target.value);
                            track.applyConstraints({ advanced: [{ zoom: zoomValue }] })
                                .catch(e => console.error("Error applying zoom:", e));
                        });
                    }
                }, 500); // Wait for camera to fully load
            } catch (e) {
                console.error("Zoom setup failed:", e);
            }
        }

        const startCamera = async () => {
            if (isCameraRunning) return; 
            document.getElementById('reader').classList.remove('hidden');
            document.getElementById('start-cam').classList.add('hidden');
            document.getElementById('stop-cam').classList.remove('hidden');
            
            scanner = new Html5Qrcode("reader");
            try {
                await scanner.start({ facingMode: "environment" }, { fps: 10, qrbox: 250 }, (txt) => {
                    document.getElementById('beep').play();
                    stopCameraAndRun(txt);
                });
                isCameraRunning = true;
                setupZoom(); // TRIGGER ZOOM SETUP
            } catch (err) {
                alert("Camera fail: " + err);
                isCameraRunning = false;
            }
        };

        const stopCameraAndRun = async (txt) => {
            if(scanner && isCameraRunning) {
                await scanner.stop();
                isCameraRunning = false;
                dom.zoomControls.classList.add('hidden'); // Hide zoom when stopped
                if (dom.autoToggle.checked) {
                    runAttendance(txt); 
                } else {
                    document.getElementById('manual-code').value = txt;
                    alert("Scanned! Click 'Use' to mark.");
                }
            }
        };

        document.getElementById('start-cam').addEventListener('click', startCamera);
        
        document.getElementById('next-qr-btn').addEventListener('click', () => {
             closeResults(); 
             setTimeout(startCamera, 300);
        });

        document.getElementById('stop-cam').addEventListener('click', async () => {
            if(scanner && isCameraRunning) {
                await scanner.stop();
                isCameraRunning = false;
                location.reload();
            }
        });

        document.getElementById('use-text').addEventListener('click', () => {
            const txt = document.getElementById('manual-code').value;
            if(txt) runAttendance(txt);
        });

        function closeResults() {
            dom.resBox.classList.add('hidden');
            render(); 
            document.getElementById('reader').classList.add('hidden');
            document.getElementById('start-cam').classList.remove('hidden');
            document.getElementById('stop-cam').classList.add('hidden');
            dom.zoomControls.classList.add('hidden');
        }

        async function runAttendance(id) {
            dom.resBox.classList.remove('hidden');
            
            const queue = filteredStudents.filter(s => {
                const isDone = completedEmails.has(s.email);
                const fails = retryCounts[s.email] || 0;
                return !isDone && fails < 2;
            });

            if (queue.length === 0) {
                dom.log.innerHTML = "<div style='color:var(--secondary); font-weight:bold;'>✅ All active students are marked!</div>";
                return;
            }

            dom.log.innerHTML = `<div style='margin-bottom:10px;'>🚀 Processing ${queue.length} students...</div>`;
            
            const payload = queue.map(s => ({ ...s, cookie: storedCookies[s.email] || null }));

            try {
                const res = await fetch('/mark-attendance', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ attendance_id: id, students: payload })
                });
                const data = await res.json();
                
                let html = "";
                data.table_data.forEach(r => {
                    let icon = '❌';
                    let color = 'var(--danger)';
                    if (r.status === 'Success') {
                        completedEmails.add(r.email);
                        icon = '✅';
                        color = 'var(--secondary)';
                    } else {
                        retryCounts[r.email] = (retryCounts[r.email] || 0) + 1;
                        if (retryCounts[r.email] >= 2) icon = '🚫';
                    }
                    html += `<div style="padding:8px; border-bottom:1px solid var(--border); display:flex; justify-content:space-between;">
                        <span><b>${r.email.split('@')[0]}</b></span>
                        <span style="color:${color}; font-size:0.9em;">${icon} ${r.response}</span>
                    </div>`;
                });
                dom.log.innerHTML = html;
                saveQueueState();
            } catch(e) { dom.log.innerText = "Error: " + e; }
        }
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)