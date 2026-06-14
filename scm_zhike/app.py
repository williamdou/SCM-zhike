# -*- coding: utf-8 -*-
"""
SCM智课 - 供应链管理研究互动式课堂智能教学系统
基于 Flask + SQLite + DeepSeek API
"""

import os
import json
import sqlite3
import hashlib
import random
import math
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash

app = Flask(__name__)
app.secret_key = 'scm_zhike_secret_key_2026'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=4)

DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scm_zhike.db')

# ============================================================
# Database helpers
# ============================================================
def get_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    return db

def init_db():
    db = get_db()
    cur = db.cursor()
    cur.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('teacher','student')),
            realname TEXT NOT NULL,
            student_id TEXT,
            grade TEXT,
            class_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            chapter TEXT NOT NULL,
            action TEXT NOT NULL,
            detail TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS practice_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            chapter TEXT NOT NULL,
            task_name TEXT NOT NULL,
            score REAL,
            detail TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            chapter TEXT,
            rating INTEGER,
            comment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
    ''')
    db.commit()

    # Ensure a default admin teacher exists
    admin = cur.execute("SELECT id FROM users WHERE username=?", ('admin',)).fetchone()
    if not admin:
        pw = hashlib.sha256('admin123'.encode()).hexdigest()
        cur.execute(
            "INSERT INTO users (username, password_hash, role, realname) VALUES (?,?,?,?)",
            ('admin', pw, 'teacher', '管理员教师')
        )
        db.commit()
    db.close()

# Initialize DB at startup
init_db()

# Re-register BI module with actual get_db function
from bi_module import register_bi_routes
register_bi_routes(app, get_db)

# ============================================================
# Auth decorators
# ============================================================
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated

def teacher_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login_page'))
        if session.get('role') != 'teacher':
            flash('需要教师权限', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated

def log_activity(user_id, username, chapter, action, detail=''):
    try:
        db = get_db()
        db.execute(
            "INSERT INTO activity_log (user_id, username, chapter, action, detail) VALUES (?,?,?,?,?)",
            (user_id, username, chapter, action, detail)
        )
        db.commit()
        db.close()
    except:
        pass

# ============================================================
# Auth routes
# ============================================================
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login_page'))

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        if not username or not password:
            flash('请输入用户名和密码', 'error')
            return render_template('login.html')

        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        db.close()

        pw_hash = hashlib.sha256(password.encode()).hexdigest()
        if user and user['password_hash'] == pw_hash:
            session.permanent = True
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            session['realname'] = user['realname']
            flash(f'欢迎回来，{user["realname"]}！', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('用户名或密码错误', 'error')

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register_page():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        password2 = request.form.get('password2', '').strip()
        role = request.form.get('role', 'student')
        realname = request.form.get('realname', '').strip()
        student_id = request.form.get('student_id', '').strip()
        grade = request.form.get('grade', '').strip()
        class_name = request.form.get('class_name', '').strip()

        if not username or not password or not realname:
            flash('请填写必填字段', 'error')
            return render_template('register.html')

        if role == 'student' and not grade:
            flash('学生请选择年级', 'error')
            return render_template('register.html')

        if password != password2:
            flash('两次密码不一致', 'error')
            return render_template('register.html')

        if len(password) < 6:
            flash('密码长度至少6位', 'error')
            return render_template('register.html')

        if role not in ('teacher', 'student'):
            role = 'student'

        db = get_db()
        exists = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        if exists:
            db.close()
            flash('用户名已存在', 'error')
            return render_template('register.html')

        pw_hash = hashlib.sha256(password.encode()).hexdigest()
        db.execute(
            "INSERT INTO users (username, password_hash, role, realname, student_id, grade, class_name) VALUES (?,?,?,?,?,?,?)",
            (username, pw_hash, role, realname, student_id, grade, class_name)
        )
        db.commit()
        db.close()
        flash('注册成功，请登录', 'success')
        return redirect(url_for('login_page'))

    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))

# ============================================================
# Dashboard
# ============================================================
@app.route('/dashboard')
@login_required
def dashboard():
    if session.get('role') == 'teacher':
        return redirect(url_for('teacher_dashboard'))
    return redirect(url_for('student_dashboard'))

# ============================================================
# Teacher routes
# ============================================================
@app.route('/teacher')
@teacher_required
def teacher_dashboard():
    db = get_db()

    # Stats
    total_students = db.execute("SELECT COUNT(*) as c FROM users WHERE role='student'").fetchone()['c']
    total_activities = db.execute("SELECT COUNT(*) as c FROM activity_log").fetchone()['c']
    total_practices = db.execute("SELECT COUNT(*) as c FROM practice_results").fetchone()['c']

    # Recent activities
    recent = db.execute("""
        SELECT al.*, u.realname FROM activity_log al
        JOIN users u ON al.user_id = u.id
        ORDER BY al.created_at DESC LIMIT 20
    """).fetchall()

    # Chapter stats (exclude test entries)
    chapter_stats = db.execute("""
        SELECT chapter, COUNT(*) as cnt FROM activity_log
        WHERE chapter != 'Test' AND chapter NOT LIKE '%test%'
        GROUP BY chapter ORDER BY cnt DESC
    """).fetchall()

    # Student practice scores
    student_scores = db.execute("""
        SELECT u.realname, u.username, pr.chapter, pr.task_name,
               ROUND(AVG(pr.score), 1) as avg_score, COUNT(*) as cnt
        FROM practice_results pr
        JOIN users u ON pr.user_id = u.id
        WHERE u.role = 'student'
        GROUP BY u.id, pr.chapter, pr.task_name
        ORDER BY u.realname, pr.chapter
    """).fetchall()

    # Student list
    students = db.execute("SELECT * FROM users WHERE role='student' ORDER BY created_at DESC").fetchall()

    # Feedback
    feedbacks = db.execute("""
        SELECT f.*, u.realname FROM feedback f
        JOIN users u ON f.user_id = u.id
        ORDER BY f.created_at DESC LIMIT 20
    """).fetchall()

    db.close()

    return render_template('teacher_dashboard.html',
        total_students=total_students,
        total_activities=total_activities,
        total_practices=total_practices,
        recent=recent,
        chapter_stats=chapter_stats,
        student_scores=student_scores,
        students=students,
        feedbacks=feedbacks)

@app.route('/teacher/student/<int:student_id>')
@teacher_required
def student_detail(student_id):
    db = get_db()
    student = db.execute("SELECT * FROM users WHERE id=? AND role='student'", (student_id,)).fetchone()
    if not student:
        db.close()
        flash('学生不存在', 'error')
        return redirect(url_for('teacher_dashboard'))

    activities = db.execute(
        "SELECT * FROM activity_log WHERE user_id=? ORDER BY created_at DESC LIMIT 50",
        (student_id,)
    ).fetchall()

    practices = db.execute(
        "SELECT * FROM practice_results WHERE user_id=? ORDER BY created_at DESC",
        (student_id,)
    ).fetchall()

    db.close()
    return render_template('student_detail.html', student=student, activities=activities, practices=practices)

# ============================================================
# Student routes
# ============================================================
@app.route('/student')
@login_required
def student_dashboard():
    return redirect(url_for('chapter_select'))

@app.route('/chapters')
@login_required
def chapter_select():
    from knowledge_data import CHAPTERS, CHAPTER_ORDER
    user_id = session['user_id']
    db = get_db()
    progress = {}
    rows = db.execute(
        "SELECT chapter, COUNT(DISTINCT task_name) as cnt FROM practice_results WHERE user_id=? GROUP BY chapter",
        (user_id,)
    ).fetchall()
    for r in rows:
        progress[r['chapter']] = r['cnt']
    db.close()

    chapters = []
    for key in CHAPTER_ORDER:
        ch = CHAPTERS.get(key)
        if ch:
            chapters.append({
                'key': key,
                'name': ch['name'],
                'icon': ch['icon'],
                'overview': ch['overview'],
                'enterprise_cases': len(ch['enterprise']['cases']),
                'practice_tasks': len(ch.get('practice_tasks', [])),
                'completed': progress.get(ch['name'], 0),
            })
    return render_template('chapter_select.html', chapters=chapters)

@app.route('/chapter/<chapter_key>')
@login_required
def chapter_view(chapter_key):
    from knowledge_data import CHAPTERS
    chapter = CHAPTERS.get(chapter_key)
    if not chapter:
        flash('章节不存在', 'error')
        return redirect(url_for('chapter_select'))

    log_activity(session['user_id'], session['username'], chapter['name'], 'view_chapter', f'查看章节：{chapter["name"]}')
    return render_template('chapter_content.html', chapter=chapter, chapter_key=chapter_key)

@app.route('/practice/<chapter_key>/<task_key>')
@login_required
def practice_view(chapter_key, task_key):
    from knowledge_data import CHAPTERS
    chapter = CHAPTERS.get(chapter_key)
    if not chapter:
        return jsonify({'error': '章节不存在'}), 404

    tasks = chapter.get('practice_tasks', [])
    task = None
    for t in tasks:
        if t['key'] == task_key:
            task = t
            break
    if not task:
        return jsonify({'error': '任务不存在'}), 404

    log_activity(session['user_id'], session['username'], chapter['name'], 'start_practice', f'开始实践：{task["name"]}')
    return render_template('practice.html', chapter=chapter, chapter_key=chapter_key, task=task, task_key=task_key)

# ============================================================
# Practice API endpoints
# ============================================================
@app.route('/api/practice/beer_game/init', methods=['POST'])
@login_required
def beer_game_init():
    """Initialize beer game session"""
    data = {
        'round': 0,
        'max_rounds': 6,
        'inventory': 80,
        'demand_history': [100, 100, 100, 100, 100],
        'current_demand': 150,
        'orders': [],
        'inventory_history': [],
        'holding_cost_rate': 5,
        'stockout_cost_rate': 20,
        'lead_time': 2,
        'pending_orders': [0, 0],  # orders arriving in 1 and 2 weeks
        'total_cost': 0,
        'cost_history': []
    }
    return jsonify(data)

@app.route('/api/practice/beer_game/play', methods=['POST'])
@login_required
def beer_game_play():
    """Play one round of beer game"""
    state = request.json
    order_qty = int(state.get('order_qty', 100))
    inv = state.get('inventory', 80)
    demand = state.get('current_demand', 150)
    pending = state.get('pending_orders', [0, 0])
    total_cost = state.get('total_cost', 0)
    rnd = state.get('round', 0) + 1

    # Receive pending order from 2 weeks ago
    arrival = pending[0]
    new_inv = inv + arrival

    # Fulfill demand
    if new_inv >= demand:
        fulfilled = demand
        stockout = 0
        new_inv -= demand
    else:
        fulfilled = new_inv
        stockout = demand - new_inv
        new_inv = 0

    holding_cost = new_inv * state.get('holding_cost_rate', 5)
    stockout_cost = stockout * state.get('stockout_cost_rate', 20)
    round_cost = holding_cost + stockout_cost
    total_cost += round_cost

    # Update pending orders
    pending = [pending[1], order_qty]

    # Generate next demand (with some randomness + trend)
    base_demand = state.get('demand_history', [100]*5)[-1]
    if rnd < 5:
        next_demand = base_demand + random.randint(-30, 40)
        next_demand = max(50, min(250, next_demand))
    else:
        next_demand = 0  # game ends

    result = {
        'round': rnd,
        'max_rounds': state.get('max_rounds', 6),
        'order_qty': order_qty,
        'arrival': arrival,
        'demand': demand,
        'fulfilled': fulfilled,
        'stockout': stockout,
        'ending_inventory': new_inv,
        'holding_cost': holding_cost,
        'stockout_cost': stockout_cost,
        'round_cost': round_cost,
        'total_cost': total_cost,
        'pending_orders': pending,
        'next_demand': next_demand,
        'game_over': rnd >= state.get('max_rounds', 6)
    }
    return jsonify(result)

@app.route('/api/practice/supplier_eval/evaluate', methods=['POST'])
@login_required
def supplier_eval():
    """Evaluate supplier selection based on student weights"""
    data = request.json
    weights = data.get('weights', {})  # {price: 0.3, quality: 0.25, ...}

    # Normalize weights
    total_w = sum(weights.values())
    if total_w == 0:
        return jsonify({'error': '权重不能全为0'}), 400
    weights = {k: v/total_w for k, v in weights.items()}

    # Supplier data (normalized scores 0-100)
    suppliers = [
        {'name': '供应商A', 'price': 85, 'quality': 90, 'delivery': 78, 'tech': 82, 'service': 88},
        {'name': '供应商B', 'price': 92, 'quality': 75, 'delivery': 88, 'tech': 70, 'service': 80},
        {'name': '供应商C', 'price': 70, 'quality': 95, 'delivery': 90, 'tech': 95, 'service': 92},
        {'name': '供应商D', 'price': 80, 'quality': 80, 'delivery': 95, 'tech': 75, 'service': 75},
        {'name': '供应商E', 'price': 95, 'quality': 70, 'delivery': 72, 'tech': 88, 'service': 70},
    ]

    # Expert weights
    expert_weights = {'price': 0.20, 'quality': 0.30, 'delivery': 0.20, 'tech': 0.15, 'service': 0.15}

    def calc_score(s, w):
        return (s['price']*w.get('price',0) + s['quality']*w.get('quality',0) +
                s['delivery']*w.get('delivery',0) + s['tech']*w.get('tech',0) +
                s['service']*w.get('service',0))

    student_ranking = sorted(suppliers, key=lambda s: calc_score(s, weights), reverse=True)
    expert_ranking = sorted(suppliers, key=lambda s: calc_score(s, expert_weights), reverse=True)

    # Calculate match score
    student_top3 = set(s['name'] for s in student_ranking[:3])
    expert_top3 = set(s['name'] for s in expert_ranking[:3])
    match_count = len(student_top3 & expert_top3)
    match_score = match_count / 3 * 100

    result = {
        'student_ranking': [{'name': s['name'], 'score': round(calc_score(s, weights), 1)} for s in student_ranking],
        'expert_ranking': [{'name': s['name'], 'score': round(calc_score(s, expert_weights), 1)} for s in expert_ranking],
        'match_score': round(match_score, 1),
        'match_count': match_count,
        'analysis': '权重设置与专家基准高度一致，选择结果很合理' if match_count >= 3 else
                    '权重设置结果与专家基准较为接近' if match_count >= 2 else
                    '权重设置与专家基准差异较大。提示：质量和技术能力通常比价格更重要'
    }
    return jsonify(result)

@app.route('/api/practice/facility_location/evaluate', methods=['POST'])
@login_required
def facility_location():
    """Evaluate facility location decision"""
    data = request.json
    selected = data.get('selected', '').strip()

    # 3 candidate locations with data
    candidates = {
        'A': {'name': '武汉', 'transport_cost': 85000, 'construction_cost': 2000000, 'labor_quality': 75, 'market_access': 90, 'total': 2085000},
        'B': {'name': '郑州', 'transport_cost': 92000, 'construction_cost': 1800000, 'labor_quality': 70, 'market_access': 85, 'total': 1892000},
        'C': {'name': '长沙', 'transport_cost': 88000, 'construction_cost': 1900000, 'labor_quality': 80, 'market_access': 82, 'total': 1988000},
    }

    if selected not in candidates:
        return jsonify({'error': '请选择A/B/C'}), 400

    # The "optimal" depends on the decision criteria. For a balanced approach, B is optimal (lowest total cost)
    chosen = candidates[selected]

    # Compare: A best for market access, B best for cost, C best for labor quality
    comparison = []
    for k, v in candidates.items():
        comparison.append({
            'name': v['name'],
            'key': k,
            'transport_cost': v['transport_cost'],
            'construction_cost': v['construction_cost'],
            'total_cost': v['total'],
            'labor_quality': v['labor_quality'],
            'market_access': v['market_access'],
            'is_selected': k == selected
        })

    # Score the decision
    if selected == 'B':
        feedback = '优秀！郑州方案综合成本最低，且市场通达性好，是最优选址。'
        score = 95
    elif selected == 'A':
        feedback = '武汉方案市场通达性最好，但建设成本较高。如果市场覆盖是首要目标，这是一个合理的选择。但从综合成本来看，郑州更优。'
        score = 75
    else:
        feedback = '长沙方案劳动力素质最高，但综合竞争力不如郑州。除非对人才有特殊需求，否则郑州方案更经济。'
        score = 70

    return jsonify({
        'selected': chosen['name'],
        'comparison': comparison,
        'feedback': feedback,
        'score': score
    })

@app.route('/api/practice/pricing/simulate', methods=['POST'])
@login_required
def pricing_simulate():
    """Simulate price-demand elasticity"""
    data = request.json
    price = float(data.get('price', 100))
    base_price = 80
    base_demand = 1000
    unit_cost = 50

    # Demand function with price elasticity
    # demand = base_demand * (base_price / price) ^ 1.5
    if price <= 0:
        price = 1
    demand = int(base_demand * ((base_price / price) ** 1.5))

    revenue = price * demand
    cost = unit_cost * demand
    profit = revenue - cost

    # Optimal price analytically: p* = unit_cost * (elasticity/(elasticity-1))
    # elasticity = 1.5, so p* = 50 * (1.5/0.5) = 150
    optimal_price = 150
    optimal_demand = int(base_demand * ((base_price / optimal_price) ** 1.5))
    optimal_profit = optimal_price * optimal_demand - unit_cost * optimal_demand

    return jsonify({
        'price': price,
        'demand': demand,
        'revenue': round(revenue, 2),
        'cost': round(cost, 2),
        'profit': round(profit, 2),
        'optimal_price': optimal_price,
        'optimal_profit': round(optimal_profit, 2),
        'efficiency': round(profit / optimal_profit * 100, 1) if optimal_profit > 0 else 0
    })

@app.route('/api/practice/make_or_buy/check', methods=['POST'])
@login_required
def make_or_buy():
    """Check make vs buy breakeven calculation"""
    data = request.json
    student_be = float(data.get('breakeven', 0))
    fixed_cost = 500000  # annual fixed cost of making
    unit_vc_make = 35    # variable cost per unit (make)
    unit_price_buy = 65  # purchase price per unit (buy)

    # Correct breakeven: fixed_cost / (unit_price_buy - unit_vc_make)
    correct_be = fixed_cost / (unit_price_buy - unit_vc_make)
    correct_be = round(correct_be, 0)

    diff_pct = abs(student_be - correct_be) / correct_be * 100

    if diff_pct < 5:
        feedback = f'计算正确！盈亏平衡点为{int(correct_be)}件。当年需求量超过此值时自制更优。'
        score = 95
    elif diff_pct < 15:
        feedback = f'接近正确答案。盈亏平衡点应为{int(correct_be)}件，你的结果为{int(student_be)}件。检查公式：盈亏平衡点 = 固定成本/(外购单价-自制单位变动成本)。'
        score = 75
    else:
        feedback = f'偏差较大。盈亏平衡点应为{int(correct_be)}件。公式：盈亏平衡点 = 固定成本÷(外购单价-自制单位变动成本) = {fixed_cost}÷({unit_price_buy}-{unit_vc_make})。'
        score = 50

    return jsonify({
        'correct_breakeven': int(correct_be),
        'student_breakeven': student_be,
        'feedback': feedback,
        'score': score,
        'formula': f'{fixed_cost} ÷ ({unit_price_buy} - {unit_vc_make}) = {int(correct_be)} 件'
    })

@app.route('/api/practice/delivery_route/evaluate', methods=['POST'])
@login_required
def delivery_route():
    """Evaluate delivery route optimization"""
    data = request.json
    student_route = data.get('route', [])

    # Distance matrix (5 delivery points)
    distances = {
        ('A','B'): 45, ('A','C'): 30, ('A','D'): 55, ('A','E'): 40, ('A','DC'): 25,
        ('B','C'): 35, ('B','D'): 25, ('B','E'): 50, ('B','DC'): 30,
        ('C','D'): 40, ('C','E'): 35, ('C','DC'): 20,
        ('D','E'): 30, ('D','DC'): 35,
        ('E','DC'): 40,
    }
    # Make symmetric
    for (a,b), d in list(distances.items()):
        distances[(b,a)] = d

    # Optimal route: DC -> C -> E -> D -> B -> A -> DC
    optimal_route = ['DC', 'C', 'E', 'D', 'B', 'A', 'DC']
    optimal_dist = 30 + 35 + 30 + 25 + 45 + 25  # = 190 (DC->C->E->D->B->A->DC)

    # Calculate student route distance
    student_dist = 0
    valid = True
    if len(student_route) < 3:
        valid = False

    if valid:
        try:
            for i in range(len(student_route)-1):
                a, b = student_route[i], student_route[i+1]
                if (a,b) in distances:
                    student_dist += distances[(a,b)]
                else:
                    valid = False
                    break
        except:
            valid = False

    if not valid:
        return jsonify({'error': '路线格式不正确，请输入类似 DC-C-E-D-B-A-DC 的路线'}), 400

    efficiency = optimal_dist / max(student_dist, 1) * 100

    if efficiency > 95:
        feedback = f'优秀！你的路线距离{student_dist}km，接近最优解{optimal_dist}km。'
        score = 95
    elif efficiency > 80:
        feedback = f'不错！你的路线距离{student_dist}km，最优解为{optimal_dist}km（DC→C→E→D→B→A→DC）。还有优化空间。'
        score = 75
    else:
        feedback = f'你的路线距离{student_dist}km，最优解为{optimal_dist}km（DC→C→E→D→B→A→DC）。可以尝试"最近邻启发式"策略：每次选择距离当前点最近的未访问点。'
        score = 50

    return jsonify({
        'student_distance': student_dist,
        'optimal_distance': optimal_dist,
        'optimal_route': 'DC → C → E → D → B → A → DC',
        'efficiency': round(efficiency, 1),
        'feedback': feedback,
        'score': score
    })

@app.route('/api/practice/risk_scenario/evaluate', methods=['POST'])
@login_required
def risk_scenario():
    """Evaluate supply chain risk response"""
    data = request.json
    choice = data.get('choice', '')

    scenarios = {
        'scenario': '你的核心芯片供应商因自然灾害停产，库存仅能维持3周。新供应商认证需要8周。现有客户订单必须按时交付。',
        'options': {
            'A': {
                'name': '紧急现货采购',
                'cost': '溢价200%，可立即获得芯片',
                'recovery': '1周内恢复',
                'risk': '成本飙升，利润严重受损',
                'score': 70,
                'analysis': '短期有效但成本高昂。适合利润空间大、客户关系至关重要的场景。'
            },
            'B': {
                'name': '与现有客户协商延迟交付',
                'cost': '可能损失部分客户信任，潜在赔偿',
                'recovery': '8周（等待新供应商认证）',
                'risk': '客户流失风险高',
                'score': 40,
                'analysis': '风险最高，客户信任一旦失去难以挽回。不建议作为首选方案。'
            },
            'C': {
                'name': '混合策略：现货采购满足关键客户+协商非关键客户延迟',
                'cost': '溢价100%（部分现货采购）',
                'recovery': '1周内恢复关键客户，8周全面恢复',
                'risk': '综合风险可控',
                'score': 95,
                'analysis': '最佳策略！兼顾客户分级管理和成本控制，是供应链韧性的典型实践。'
            },
        }
    }

    if choice not in scenarios['options']:
        return jsonify({'error': '请选择A/B/C'}), 400

    option = scenarios['options'][choice]
    result = {
        'choice': choice,
        'name': option['name'],
        'score': option['score'],
        'analysis': option['analysis'],
        'all_options': {k: {'name': v['name'], 'cost': v['cost'], 'recovery': v['recovery'], 'risk': v['risk']} for k, v in scenarios['options'].items()}
    }
    return jsonify(result)

@app.route('/api/practice/save_result', methods=['POST'])
@login_required
def save_practice_result():
    """Save practice result to DB"""
    data = request.json
    db = get_db()
    db.execute(
        "INSERT INTO practice_results (user_id, username, chapter, task_name, score, detail) VALUES (?,?,?,?,?,?)",
        (session['user_id'], session['username'], data.get('chapter',''), data.get('task_name',''), data.get('score',0), json.dumps(data.get('detail',{}), ensure_ascii=False))
    )
    db.commit()
    db.close()
    log_activity(session['user_id'], session['username'], data.get('chapter',''), 'complete_practice', f'完成：{data.get("task_name","")}，得分：{data.get("score",0)}')
    return jsonify({'status': 'ok'})

# ============================================================
# Chapter 1: Supply Chain Map game
# ============================================================
@app.route('/api/practice/scm_map/check', methods=['POST'])
@login_required
def scm_map_check():
    """Evaluate student's SCM map components"""
    data = request.json
    components = data.get('components', {})
    product = data.get('product', '')

    # Expected components for a complete SCM map
    expected = {
        'suppliers': {'weight': 20, 'label': '原材料供应商', 'hint': '如矿产、农场、化工厂等'},
        'manufacturers': {'weight': 20, 'label': '制造商/加工厂', 'hint': '将原材料转化为零部件或成品'},
        'distributors': {'weight': 15, 'label': '分销商/批发商', 'hint': '区域仓储与分销'},
        'retailers': {'weight': 15, 'label': '零售商/电商平台', 'hint': '直接面向消费者的销售渠道'},
        'logistics': {'weight': 15, 'label': '物流服务商', 'hint': '运输、仓储、配送'},
        'info_flow': {'weight': 10, 'label': '信息流', 'hint': '订单、需求预测、库存信息的传递方向'},
        'cash_flow': {'weight': 5, 'label': '资金流', 'hint': '付款、货款的流动方向'},
    }

    score = 0
    feedback_parts = []
    for key, exp in expected.items():
        if key in components and components[key] and components[key].strip():
            score += exp['weight']
            feedback_parts.append(f'✅ {exp["label"]}: 已识别')
        else:
            feedback_parts.append(f'⚠️ {exp["label"]}: 缺失——{exp["hint"]}')

    bonus = int(product.strip() != '')
    score = min(100, score + bonus * 5)
    feedback_parts.append(f'\n📊 总分: {score}/100')
    if score >= 85:
        feedback_parts.append('优秀！你对供应链结构有完整的理解。')
    elif score >= 60:
        feedback_parts.append('不错！注意补充缺失的环节。')

    return jsonify({
        'score': score,
        'feedback': '\n'.join(feedback_parts),
        'components_found': sum(1 for k in expected if k in components and components[k] and components[k].strip()),
        'total_components': len(expected),
    })


# ============================================================
# Chapter 2: Vertical vs Outsource decision
# ============================================================
@app.route('/api/practice/vertical_vs_outsource/check', methods=['POST'])
@login_required
def vertical_vs_outsource():
    data = request.json
    choice = data.get('choice', '')
    reasons = data.get('reasons', '')

    options = {
        'A': {
            'name': '自建芯片产线（垂直整合）',
            'pros': '供应安全完全自主可控、长期单位成本可能更低、技术know-how内生',
            'cons': '初始投资5亿元，资金压力大、3年建设期，远水不解近渴、芯片行业技术迭代快，有产能过时风险',
            'score': 70,
            'analysis': '选择垂直整合意味着你对供应安全给予最高权重。这是华为被制裁后许多中国企业的思考方向。但需要清醒认识到3年的建设周期和巨大的资金压力。',
        },
        'B': {
            'name': '与供应商签长约（市场交易）',
            'pros': '即期锁定供应，无建设期风险、无需巨额资本投入、保持战略灵活性',
            'cons': '供应商仍可能违约、价格锁定后无法享受技术降价红利、议价筹码随时间减弱',
            'score': 75,
            'analysis': '选择长约是务实的短期策略。但需要注意合约中的不可抗力条款和违约责任设计，确保合约真的有约束力。',
        },
        'C': {
            'name': '混合策略：部分自研+部分长约+培育第二供应商',
            'pros': '短期保供应（长约）、中期增选择（培育第二源）、长期建能力（自研）',
            'cons': '资源分散，管理复杂度高',
            'score': 95,
            'analysis': '最佳策略！这是许多领先企业实际采用的方法。"不把鸡蛋放在一个篮子里"——同时推进三个时间维度的供应链安全策略。',
        },
    }

    if choice not in options:
        return jsonify({'error': '请选择A/B/C'}), 400

    opt = options[choice]
    return jsonify({
        'choice': choice,
        'name': opt['name'],
        'pros': opt['pros'],
        'cons': opt['cons'],
        'score': opt['score'],
        'analysis': opt['analysis'],
        'all_options': {k: {'name': v['name'], 'score': v['score']} for k, v in options.items()},
    })


# ============================================================
# Chapter 3: Technology assessment ranking
# ============================================================
@app.route('/api/practice/tech_assessment/check', methods=['POST'])
@login_required
def tech_assessment():
    data = request.json
    ranking = data.get('ranking', [])  # ordered list of tech keys

    techs = [
        {'key': 'ai_forecast', 'name': 'AI需求预测', 'expert_rank': 1,
         'reason': '直接影响库存成本和缺货率，食品行业SKU多、保质期短，AI预测的ROI最高'},
        {'key': 'rfid', 'name': 'RFID全链追踪', 'expert_rank': 2,
         'reason': '食品安全溯源刚需+库存精准度提升+自动盘点减少人工，连锁零售的标配'},
        {'key': 'digital_twin', 'name': '数字孪生', 'expert_rank': 3,
         'reason': '适合复杂网络模拟优化，但食品零售网络相对简单，投入产出比较前两项低'},
        {'key': 'blockchain', 'name': '区块链溯源', 'expert_rank': 4,
         'reason': '食品安全溯源有价值，但技术成熟度不够、成本高，可用RFID替代大部分功能'},
        {'key': 'drone', 'name': '无人机配送', 'expert_rank': 6,
         'reason': '食品零售以门店为主，无人机配送目前更多是营销噱头而非核心ROI来源'},
        {'key': 'd_printing', 'name': '3D打印备件', 'expert_rank': 5,
         'reason': '食品零售行业设备备件场景有限，该技术更适合制造业'},
    ]

    tech_map = {t['key']: t for t in techs}
    expert_order = [t['key'] for t in sorted(techs, key=lambda x: x['expert_rank'])]

    # Score: Spearman rank correlation
    student_ranks = {k: i + 1 for i, k in enumerate(ranking) if k in tech_map}
    expert_ranks = {t['key']: t['expert_rank'] for t in techs}

    total_diff = 0
    for t in techs:
        sr = student_ranks.get(t['key'], 7)
        er = expert_ranks[t['key']]
        total_diff += (sr - er) ** 2

    n = len(techs)
    max_diff = n * (n**2 - 1) * 2  # theoretical max for Spearman
    spearman = 1 - (6 * total_diff) / (n * (n**2 - 1))
    score = round(max(0, spearman) * 100)

    analysis = '你的排序与专家建议高度一致，对SCM技术趋势有很好的判断力！' if score >= 85 else \
               '排序与专家建议较为接近，注意AI预测和RFID的投资优先级。' if score >= 65 else \
               '建议重新思考：食品零售行业最核心的痛点是需求波动大和食品安全，前两项技术的ROI远高于其他。'

    return jsonify({
        'score': score,
        'analysis': analysis,
        'correlation': round(spearman, 3),
        'expert_ranking': [{'rank': t['expert_rank'], 'name': t['name'], 'reason': t['reason']} for t in sorted(techs, key=lambda x: x['expert_rank'])],
        'student_ranking': ranking,
    })


# ============================================================
# Chapter 4: Fisher matrix matching
# ============================================================
@app.route('/api/practice/fisher_match/check', methods=['POST'])
@login_required
def fisher_match():
    data = request.json
    matches = data.get('matches', {})  # {product: 'efficient'|'responsive'}

    products = [
        {'key': 'furniture', 'name': '高端定制家具', 'demand_uncertainty': '高', 'profit_margin': '高',
         'lifecycle': '长', 'correct': 'responsive',
         'reason': '需求高度不确定（定制化）+利润率高→匹配响应型供应链。核心目标：快速响应客户个性化需求，而非成本最低。'},
        {'key': 'water', 'name': '品牌瓶装水', 'demand_uncertainty': '低', 'profit_margin': '低',
         'lifecycle': '长', 'correct': 'efficient',
         'reason': '需求稳定可预测+利润率低→匹配效率型供应链。核心目标：最大化产能利用率、最小化物流成本。'},
        {'key': 'phone', 'name': '新款智能手机', 'demand_uncertainty': '高', 'profit_margin': '高',
         'lifecycle': '短', 'correct': 'responsive',
         'reason': '需求高度不确定+产品生命周期短（约1年）+利润率高→必须匹配响应型供应链，快速上市+弹性产能。'},
        {'key': 'screw', 'name': '标准工业螺丝', 'demand_uncertainty': '低', 'profit_margin': '极低',
         'lifecycle': '极长', 'correct': 'efficient',
         'reason': '需求极稳定（标准化产品）+利润率极低→经典效率型供应链。以规模效应和精益生产取胜。'},
    ]

    correct_count = 0
    details = []
    for p in products:
        student_choice = matches.get(p['key'], '')
        is_correct = student_choice == p['correct']
        if is_correct:
            correct_count += 1
        details.append({
            'name': p['name'],
            'student': student_choice,
            'correct': p['correct'],
            'is_correct': is_correct,
            'reason': p['reason'],
        })

    score = correct_count / len(products) * 100

    feedback_map = {
        4: '完美！你对Fisher模型的理解非常到位。',
        3: '基本掌握，有1个产品的匹配需要重新思考。',
        2: '还需要加强理解。建议回顾：核心原则是"产品特征决定供应链类型"。创新产品（需求不确定、利润率高）→响应型；功能产品（需求稳定、利润率低）→效率型。',
        1: 'Fisher模型掌握不足，建议重新阅读Fisher(1997)原文。',
        0: '请仔细学习Fisher模型的基本原理后重试。',
    }
    feedback = feedback_map[correct_count]

    return jsonify({
        'score': score,
        'correct_count': correct_count,
        'total': len(products),
        'feedback': feedback,
        'details': details,
    })


# ============================================================
# Chapter 5: Information sharing experiment
# ============================================================
@app.route('/api/practice/info_sharing/run', methods=['POST'])
@login_required
def info_sharing():
    """Two-phase experiment comparing no-sharing vs sharing"""
    data = request.json
    phase = data.get('phase', 1)  # 1=no sharing, 2=with sharing
    order_qty = int(data.get('order_qty', 100))
    round_num = int(data.get('round', 0)) + 1

    # True demand (same for both phases)
    true_demands = [100, 105, 95, 110, 90]
    demand = true_demands[(round_num - 1) % len(true_demands)]

    if phase == 1:
        # No sharing: retailer sees only his own demand, wholesaler sees retailer's order
        # Simulate upstream decisions blindly
        upstream_order_amplification = order_qty * (1.2 if order_qty > 110 else 1.0)
    else:
        # With sharing: wholesaler sees true demand, so amplification is reduced
        upstream_order_amplification = demand * 1.1

    amplification = round(upstream_order_amplification / max(demand, 1), 2)

    result = {
        'round': round_num,
        'max_rounds': 5,
        'demand': demand,
        'your_order': order_qty,
        'upstream_order': round(upstream_order_amplification),
        'amplification': amplification,
        'phase': phase,
        'phase_label': '无信息共享' if phase == 1 else '有信息共享',
        'analysis': '上游订单波动放大，牛鞭效应明显' if amplification > 1.3 else
                    '上游订单波动较小，信息共享缓解了牛鞭效应' if amplification < 1.2 else
                    '上游订单波动中等',
        'game_over': round_num >= 5,
    }
    return jsonify(result)


# ============================================================
# Chapter 8: Postponement design
# ============================================================
@app.route('/api/practice/postponement/check', methods=['POST'])
@login_required
def postponement_check():
    data = request.json
    push_pull_boundary = data.get('boundary', '')  # 'factory' | 'dc' | 'store'
    reasoning = data.get('reasoning', '')

    options = {
        'factory': {
            'name': '在工厂完成差异化（纯Push）',
            'score': 40,
            'analysis': '这意味着所有差异化（尺码标签、包装）在工厂完成。各市场库存无法共享调拨，牛鞭效应最严重。这是效率最低的方案。',
        },
        'dc': {
            'name': '在区域DC完成差异化（Postponement）',
            'score': 95,
            'analysis': '这正是经典的延迟策略！"通用白牌服装"推至区域DC，在DC根据当地需求进行最终差异化。全欧库存共享，大幅降低安全库存需求。',
        },
        'store': {
            'name': '在门店完成差异化（纯Pull）',
            'score': 65,
            'analysis': '虽然库存风险最低（完全按需生产），但门店员工需要进行标签打印等操作，品质一致性和效率都成问题。对于服装行业过度了。',
        },
    }

    if push_pull_boundary not in options:
        return jsonify({'error': '请选择 factory/dc/store'}), 400

    opt = options[push_pull_boundary]
    bonus = min(10, len(reasoning.strip()) / 20)
    score = min(100, opt['score'] + bonus)

    return jsonify({
        'score': round(score),
        'name': opt['name'],
        'analysis': opt['analysis'],
        'push_pull_boundary': push_pull_boundary,
    })


# ============================================================
# Chapter 13: Information value experiment (IT specific)
# ============================================================
@app.route('/api/practice/info_value/run', methods=['POST'])
@login_required
def info_value():
    """Compare 2 scenarios: decentralized vs centralized information"""
    data = request.json
    scenario = data.get('scenario', 'decentralized')  # decentralized | centralized
    demand = int(data.get('demand', 100))
    lead_time = int(data.get('lead_time', 2))

    if scenario == 'decentralized':
        # Each echelon uses only local information
        # Retailer's order based on demand + safety
        retailer_order = int(demand * 1.15)
        # Wholesaler sees retailer's order (already amplified) -> further amplify
        wholesaler_order = int(retailer_order * 1.20)
        manufacturer_order = int(wholesaler_order * 1.25)
        total_cost = demand * 20 + (retailer_order - demand) * 5 + (wholesaler_order - retailer_order) * 5 + (manufacturer_order - wholesaler_order) * 5
    else:
        # Centralized: all echelons see true demand
        retailer_order = int(demand * 1.05)
        wholesaler_order = int(demand * 1.08)
        manufacturer_order = int(demand * 1.10)
        total_cost = demand * 15 + (retailer_order - demand) * 3 + (wholesaler_order - demand) * 3 + (manufacturer_order - demand) * 3

    amplification = {'retailer': round(retailer_order / max(demand, 1), 2),
                     'wholesaler': round(wholesaler_order / max(demand, 1), 2),
                     'manufacturer': round(manufacturer_order / max(demand, 1), 2)}

    return jsonify({
        'scenario': scenario,
        'scenario_label': '分散信息（传统）' if scenario == 'decentralized' else '集中信息（信息共享）',
        'demand': demand,
        'retailer_order': retailer_order,
        'wholesaler_order': wholesaler_order,
        'manufacturer_order': manufacturer_order,
        'amplification': amplification,
        'total_cost': total_cost,
        'bullwhip_index': round(max(amplification.values()) - 1, 2),
    })


# ============================================================
# Chapter 14: Production schedule puzzle
# ============================================================
@app.route('/api/practice/production_schedule/check', methods=['POST'])
@login_required
def production_schedule():
    data = request.json
    schedule = data.get('schedule', [])  # list of {product, hours}

    products = {
        'A': {'name': '产品A', 'demand': 300, 'setup_hours': 2, 'unit_profit': 50, 'hourly_rate': 30},
        'B': {'name': '产品B', 'demand': 200, 'setup_hours': 1.5, 'unit_profit': 80, 'hourly_rate': 25},
        'C': {'name': '产品C', 'demand': 500, 'setup_hours': 0.5, 'unit_profit': 30, 'hourly_rate': 40},
    }

    total_hours = 40
    total_profit = 0
    total_produced = {}
    total_setup_time = 0
    details = []

    prev_product = None
    for step in schedule:
        p_key = step.get('product', '')
        hours = float(step.get('hours', 0))
        if p_key not in products:
            continue
        p = products[p_key]
        setup = p['setup_hours'] if p_key != prev_product else 0
        total_setup_time += setup
        available_hours = max(0, hours - setup)
        qty = int(available_hours * p['hourly_rate'])
        total_produced[p_key] = total_produced.get(p_key, 0) + qty
        total_profit += qty * p['unit_profit']
        details.append({'product': p['name'], 'hours': hours, 'setup': setup,
                        'produced': qty, 'profit': qty * p['unit_profit']})
        prev_product = p_key

    # Check feasibility
    if total_setup_time + sum(s.get('hours', 0) for s in schedule) > total_hours * 1.5:
        feasible = False
        score = 0
    else:
        feasible = True
        # Optimal: B then C (group by product to minimize setups)
        # B: setup 1.5h + produce 200/25=8h = 9.5h, C: setup 0.5h + produce 500/40=12.5h = 13h,
        # A: setup 2h + produce remaining...
        # Rough optimum: B first (high profit), then C (high volume), remaining time to A
        opt_profit = 200 * 80 + 500 * 30  # B all + C all = 16000 + 15000 = 31000
        # Then A: 40 - 1.5 - 200/25 - 0.5 - 500/40 = 40 - 1.5 - 8 - 0.5 - 12.5 = 17.5h for A
        opt_profit += int(17.5 * 30) * 50  # = 525 * 50 = 26250
        opt_profit = 31000 + 26250

        efficiency = min(100, total_profit / max(opt_profit, 1) * 100)
        score = round(efficiency)

    return jsonify({
        'score': score,
        'total_profit': total_profit,
        'optimal_profit': 57250,
        'efficiency': round(min(100, total_profit / 57250 * 100), 1),
        'feasible': feasible,
        'details': details,
        'advice': '策略：利润率高优先(B)→量大优先(C)→剩余时间产A。减少换产次数是关键！' if score < 80 else '出色的排产方案！',
    })


# ============================================================
# Chapter 16: SCOR KPI design
# ============================================================
@app.route('/api/practice/scor_kpi/check', methods=['POST'])
@login_required
def scor_kpi():
    data = request.json
    kpis = data.get('kpis', {})  # {plan: [kpi1, kpi2], source: [...], ...}

    scor_dims = {
        'plan': {
            'label': '计划(Plan)',
            'recommended': ['需求预测准确率(Forecast Accuracy)', '计划达成率(Plan Attainment)'],
            'formulas': ['|实际-预测|/实际×100%', '实际产量/计划产量×100%'],
        },
        'source': {
            'label': '采购(Source)',
            'recommended': ['OTIF(准时足量交付率)', '供应商质量PPM(百万分之不良)'],
            'formulas': ['准时足量订单数/总订单数×100%', '不良件数/总收货件数×1,000,000'],
        },
        'make': {
            'label': '制造(Make)',
            'recommended': ['OEE(设备综合效率)', '一次良品率(FPY)'],
            'formulas': ['可用率×性能率×质量率', '一次合格品数/总产量×100%'],
        },
        'deliver': {
            'label': '交付(Deliver)',
            'recommended': ['完美订单率(Perfect Order Rate)', '物流成本占销售额%'],
            'formulas': ['(准时×足量×无破损订单数)/总订单数×100%', '物流总成本/销售额×100%'],
        },
        'return': {
            'label': '退货(Return)',
            'recommended': ['退货处理周期(天)', '退货率'],
            'formulas': ['退货收到→处理完成的平均天数', '退货件数/发货件数×100%'],
        },
    }

    score = 0
    feedback_parts = []
    for dim_key, dim in scor_dims.items():
        student_kpis = kpis.get(dim_key, [])
        rec = dim['recommended']
        match_count = 0
        for sk in student_kpis:
            for rk in rec:
                if sk.strip()[:4] == rk[:4] or any(kw in sk for kw in rk.split('(')[0].strip()[:4].split('/')):
                    match_count += 1
                    break
        dim_score = min(20, match_count * 10)
        score += dim_score
        feedback_parts.append(f'{dim["label"]}: {match_count}/{len(rec)}个关键KPI匹配 (+{dim_score}分)')

    score = min(100, score)
    feedback_parts.append(f'\n📊 总分: {score}/100')
    if score >= 80:
        feedback_parts.append('优秀！你对SCOR模型的KPI设计有深入理解。')
    elif score >= 50:
        feedback_parts.append('基础不错，建议进一步学习SCOR模型各维度的标准指标。')
    else:
        feedback_parts.append('建议系统学习SCOR 11.0模型的标准指标定义。')

    return jsonify({
        'score': score,
        'feedback': '\n'.join(feedback_parts),
        'reference': {k: {'label': v['label'], 'recommended': v['recommended'], 'formulas': v['formulas']}
                      for k, v in scor_dims.items()},
    })


# ============================================================
# Knowledge search API (simulates DeepSeek integration)
# ============================================================
@app.route('/api/knowledge/<chapter_key>')
@login_required
def knowledge_api(chapter_key):
    from knowledge_data import CHAPTERS
    chapter = CHAPTERS.get(chapter_key)
    if not chapter:
        return jsonify({'error': '章节不存在'}), 404

    log_activity(session['user_id'], session['username'], chapter['name'], 'api_knowledge', f'API查询：{chapter["name"]}')
    return jsonify(chapter)

# ============================================================
# DeepSeek AI assistant proxy
# ============================================================
@app.route('/api/ai/ask', methods=['POST'])
@login_required
def ai_ask():
    """Proxy to DeepSeek API for additional Q&A"""
    data = request.json
    question = data.get('question', '')
    chapter_name = data.get('chapter', '')

    if not question:
        return jsonify({'error': '请输入问题'}), 400

    # Try DeepSeek API
    api_key = os.environ.get('DEEPSEEK_API_KEY', '')
    if api_key:
        try:
            import requests as req
            resp = req.post(
                'https://api.deepseek.com/chat/completions',
                headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
                json={
                    'model': 'deepseek-chat',
                    'messages': [
                        {'role': 'system', 'content': f'你是供应链管理课程的AI助教，当前章节是"{chapter_name}"。请用中文简洁回答学生的问题，控制在200字以内。'},
                        {'role': 'user', 'content': question}
                    ],
                    'max_tokens': 500,
                    'temperature': 0.7,
                },
                timeout=30
            )
            if resp.status_code == 200:
                answer = resp.json()['choices'][0]['message']['content']
            else:
                answer = f'AI服务暂时不可用（状态码：{resp.status_code}）'
        except Exception as e:
            answer = f'AI服务连接失败: {str(e)}'
    else:
        # Fallback: rule-based answers from knowledge data
        answer = get_fallback_answer(question, chapter_name)

    log_activity(session['user_id'], session['username'], chapter_name, 'ai_ask', f'提问：{question}')
    return jsonify({'answer': answer, 'question': question})

def get_fallback_answer(question, chapter_name):
    """Fallback answers when DeepSeek API is not available"""
    from knowledge_data import CHAPTERS
    # Simple keyword matching
    keywords_map = {
        '牛鞭效应': '牛鞭效应（Bullwhip Effect）是指供应链中需求信息从下游向上游传递时，波动逐级放大的现象。主要成因包括：需求预测更新、批量订货、价格波动、短缺博弈。缓解策略：信息共享、缩短提前期、减小订货批量、稳定价格。经典文献：Lee, Padmanabhan & Whang (1997)。',
        '供应链': '供应链是指围绕核心企业，通过对信息流、物流、资金流的控制，从原材料采购开始，到制成中间产品及最终产品，最后由销售网络把产品送到消费者手中的，将供应商、制造商、分销商、零售商直到最终用户连成一个整体的功能网链结构。',
        '库存': '库存管理是供应链管理的核心环节之一。关键概念包括：经济订货批量（EOQ）、安全库存、再订货点、ABC分类法。现代趋势：VMI（供应商管理库存）、JIT（准时制）、CPFR（协同规划预测补货）。',
        '风险': '供应链风险管理包括风险识别、评估、缓解和监控四个阶段。主要策略：多源采购、安全库存、柔性产能、供应契约设计。韧性供应链强调快速恢复能力而非仅防范风险。',
    }
    for kw, ans in keywords_map.items():
        if kw in question:
            return ans
    return f'关于"{question}"，这是一个很好的问题。请尝试以下方式获取更详细的解答：\n1. 在章节内容中查找相关知识点\n2. 查看学术研究维度的经典文献推荐\n3. 如果配置了DeepSeek API密钥（设置环境变量DEEPSEEK_API_KEY），AI助手将提供更精准的回答'

# ============================================================
# Feedback API
# ============================================================
@app.route('/api/feedback', methods=['POST'])
@login_required
def submit_feedback():
    data = request.json
    db = get_db()
    db.execute(
        "INSERT INTO feedback (user_id, username, chapter, rating, comment) VALUES (?,?,?,?,?)",
        (session['user_id'], session['username'], data.get('chapter',''), data.get('rating', 5), data.get('comment',''))
    )
    db.commit()
    db.close()
    return jsonify({'status': 'ok', 'message': '感谢你的反馈！'})

# ============================================================
# Main
# ============================================================
if __name__ == '__main__':
    init_db()
    print('='*60)
    print('  SCM - Supply Chain Management Interactive Teaching System')
    print('  Default admin: admin / admin123')
    print(f'  Local URL: http://localhost:5000')
    print('='*60)
    print('  For public access, run ngrok separately:')
    print('    ngrok http 5000')
    print('='*60)
    app.run(host='0.0.0.0', port=5000, debug=True)
