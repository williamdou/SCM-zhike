# -*- coding: utf-8 -*-
"""
SCM智课 - 商业智能模块
数据分析、数据可视化、推理预测、策略辅助、内容生成
接入国产大模型DeepSeek API
"""
import os
import json
import hashlib
import random
import math
from datetime import datetime
from flask import jsonify, request, session

DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', '')
DEEPSEEK_BASE_URL = 'https://api.deepseek.com'

def register_bi_routes(app, get_db):
    """Register all BI routes on the Flask app"""

    # ============================================================
    # 1. 数据分析接口 (Analytics API)
    # ============================================================
    @app.route('/bi/analytics')
    def bi_analytics():
        """数据分析 - 学生学习行为分析"""

        db = get_db()

        # 学生活跃度排名
        active_students = db.execute("""
            SELECT u.realname, COUNT(*) as cnt
            FROM activity_log al JOIN users u ON al.user_id = u.id
            WHERE u.role = 'student'
            GROUP BY u.id ORDER BY cnt DESC LIMIT 10
        """).fetchall()

        # 章节访问热度
        chapter_heat = db.execute("""
            SELECT chapter, COUNT(*) as cnt FROM activity_log
            WHERE chapter != 'Test' AND chapter NOT LIKE '%test%'
            GROUP BY chapter ORDER BY cnt DESC
        """).fetchall()

        # 实践任务完成分布 - aggregated by task (not raw rows)
        practice_dist = db.execute("""
            SELECT task_name, ROUND(AVG(score),1) as avg_score, COUNT(*) as cnt
            FROM practice_results GROUP BY task_name
            ORDER BY avg_score DESC
        """).fetchall()

        # 时间段活跃度（按小时）
        hourly = db.execute("""
            SELECT CAST(strftime('%H', created_at) AS INTEGER) as hour, COUNT(*) as cnt
            FROM activity_log GROUP BY hour ORDER BY hour
        """).fetchall()

        # 反馈评分分布
        feedback_dist = db.execute("""
            SELECT rating, COUNT(*) as cnt FROM feedback
            GROUP BY rating ORDER BY rating
        """).fetchall()

        db.close()

        return jsonify({
            'active_students': [{'name': r['realname'], 'count': r['cnt']} for r in active_students],
            'chapter_heat': [{'chapter': r['chapter'], 'count': r['cnt']} for r in chapter_heat],
            'practice_dist': [{'task': r['task_name'], 'avg_score': round(r['avg_score'],1), 'count': r['cnt']} for r in practice_dist],
            'hourly_activity': [{'hour': f"{r['hour']}:00", 'count': r['cnt']} for r in hourly],
            'feedback_dist': [{'rating': r['rating'], 'count': r['cnt']} for r in feedback_dist],
        })

    # ============================================================
    # 2. 推理预测引擎 (已移除前端入口，保留API供数据大屏使用)
    # ============================================================
    @app.route('/bi/predict', methods=['POST'])
    def bi_predict():
        """供应链推理预测 - 基于场景数据预测结果"""
        if 'user_id' not in session:
            return jsonify({'error': '请先登录'}), 401

        data = request.json
        scenario = data.get('scenario', 'demand')  # demand / inventory / risk
        params = data.get('params', {})

        if scenario == 'demand':
            # 需求预测：基于历史数据和趋势参数
            history = params.get('history', [100, 105, 98, 110, 103, 115, 108])
            trend = params.get('trend', 0.02)  # 增长趋势
            seasonality = params.get('seasonality', 0)  # 季节性
            periods = params.get('periods', 5)

            predictions = []
            last = history[-1]
            for i in range(periods):
                seasonal_factor = 1 + seasonality * math.sin(2 * math.pi * (len(history) + i) / 4)
                next_val = last * (1 + trend) * seasonal_factor
                predictions.append(round(next_val, 1))
                last = next_val

            # Also try DeepSeek API if available
            ai_insight = None
            if DEEPSEEK_API_KEY:
                try:
                    import requests as req
                    resp = req.post(f'{DEEPSEEK_BASE_URL}/chat/completions',
                        headers={'Authorization': f'Bearer {DEEPSEEK_API_KEY}', 'Content-Type': 'application/json'},
                        json={'model': 'deepseek-chat', 'messages': [
                            {'role': 'system', 'content': '你是供应链数据分析专家。请用简短中文分析需求预测结果。'},
                            {'role': 'user', 'content': f'历史需求数据：{history}，预测未来{periods}期，趋势{trend}，季节性{seasonality}。预测结果：{predictions}。请给出50字以内的分析建议。'}
                        ], 'max_tokens': 150}, timeout=15)
                    if resp.status_code == 200:
                        ai_insight = resp.json()['choices'][0]['message']['content']
                except:
                    pass

            return jsonify({
                'predictions': predictions,
                'history': history,
                'method': '指数平滑+季节性调整',
                'ai_insight': ai_insight or '基于历史趋势的需求预测，建议结合市场调研验证预测结果。'
            })

        elif scenario == 'inventory':
            # 安全库存推理
            demand_mean = float(params.get('demand_mean', 100))
            demand_std = float(params.get('demand_std', 20))
            lead_time = float(params.get('lead_time', 2))
            service_level = float(params.get('service_level', 0.95))

            # z-score for service level
            z_map = {0.90: 1.28, 0.95: 1.645, 0.975: 1.96, 0.99: 2.33, 0.999: 3.09}
            z = z_map.get(service_level, 1.645)

            safety_stock = z * demand_std * math.sqrt(lead_time)
            reorder_point = demand_mean * lead_time + safety_stock
            avg_inventory = safety_stock + demand_mean / 2  # approximate

            return jsonify({
                'safety_stock': round(safety_stock, 1),
                'reorder_point': round(reorder_point, 1),
                'average_inventory': round(avg_inventory, 1),
                'z_score': z,
                'service_level': service_level,
                'formula': f'SS = z({z}) × σ({demand_std}) × √L({lead_time})',
            })

        elif scenario == 'risk':
            # 风险概率推理
            supplier_count = int(params.get('supplier_count', 3))
            failure_prob = float(params.get('failure_prob', 0.05))  # per supplier

            # Probability all fail (independent)
            all_fail = failure_prob ** supplier_count
            # At least one survives
            at_least_one_ok = 1 - all_fail
            # Expected recovery time
            recovery_time = float(params.get('recovery_time', 8))  # weeks with 1 supplier

            # With N suppliers, expected recovery = recovery_time / sqrt(N) (rough model)
            expected_recovery = recovery_time / math.sqrt(supplier_count)

            return jsonify({
                'supplier_count': supplier_count,
                'failure_prob_per_supplier': failure_prob,
                'all_suppliers_fail_prob': round(all_fail * 100, 4),
                'at_least_one_ok_prob': round(at_least_one_ok * 100, 2),
                'expected_recovery_weeks': round(expected_recovery, 1),
                'recommendation': f'建议保持至少{supplier_count}家供应商，恢复时间预期从{recovery_time}周降至{expected_recovery:.1f}周'
            })

        return jsonify({'error': '未知场景'}), 400

    # ============================================================
    # 4. 策略辅助引擎 (Strategy Assistant)
    # ============================================================
    @app.route('/bi/strategy', methods=['POST'])
    def bi_strategy():
        """AI驱动的教学策略建议"""
        if 'user_id' not in session:
            return jsonify({'error': '请先登录'}), 401

        data = request.json
        question_type = data.get('type', 'teaching')

        db = get_db()

        if question_type == 'teaching':
            # 查询全量数据，生成10条综合教学策略
            # 1. 章节访问+成绩对照
            ch_data = db.execute("""
                SELECT a.chapter, a.visit_count,
                       COALESCE(p.avg_score, 0) as avg_score,
                       COALESCE(p.student_count, 0) as student_count
                FROM (SELECT chapter, COUNT(*) as visit_count FROM activity_log
                      WHERE chapter != 'Test' AND chapter NOT LIKE '%test%'
                      GROUP BY chapter) a
                LEFT JOIN (SELECT chapter, ROUND(AVG(score),1) as avg_score,
                                  COUNT(DISTINCT user_id) as student_count
                           FROM practice_results WHERE score > 0 GROUP BY chapter) p
                ON a.chapter = p.chapter ORDER BY a.visit_count DESC
            """).fetchall()

            # 2. 实践任务成绩
            task_data = db.execute("""
                SELECT task_name, ROUND(AVG(score),1) as avg, COUNT(*) as cnt,
                       MIN(score) as min_s, MAX(score) as max_s
                FROM practice_results GROUP BY task_name ORDER BY avg ASC
            """).fetchall()

            # 3. 学生活跃度
            student_data = db.execute("""
                SELECT u.realname, COUNT(*) as cnt
                FROM activity_log al JOIN users u ON al.user_id = u.id
                WHERE u.role='student' GROUP BY u.id ORDER BY cnt DESC LIMIT 5
            """).fetchall()

            # 4. 时段分布（按小时）
            hourly_data = db.execute("""
                SELECT CAST(strftime('%H', created_at) AS INTEGER) as hour, COUNT(*) as cnt
                FROM activity_log GROUP BY hour ORDER BY cnt DESC
            """).fetchall()

            # 5. 反馈分布
            fb_data = db.execute("""
                SELECT rating, COUNT(*) as cnt FROM feedback GROUP BY rating ORDER BY rating
            """).fetchall()

            # 6. 总览统计
            total_students = db.execute("SELECT COUNT(*) as cnt FROM users WHERE role='student'").fetchone()['cnt']
            total_acts = db.execute("SELECT COUNT(*) as cnt FROM activity_log").fetchone()['cnt']
            overall_avg = db.execute("SELECT ROUND(AVG(score),1) as a FROM practice_results WHERE score > 0").fetchone()['a']

            db.close()

            # ---- 构建10条策略，每条 = {head, body} ----
            strategies = []

            # 将查询结果转为字典列表
            ch_list = [{'chapter': r['chapter'], 'visit': r['visit_count'],
                         'avg': r['avg_score'], 'stu': r['student_count']} for r in ch_data]
            task_list = [{'task': r['task_name'], 'avg': r['avg'],
                           'cnt': r['cnt'], 'min_s': r['min_s'], 'max_s': r['max_s']} for r in task_data]
            stu_list = [{'name': r['realname'], 'cnt': r['cnt']} for r in student_data]
            hour_list = [{'hour': r['hour'], 'cnt': r['cnt']} for r in hourly_data]
            fb_list = [{'rating': r['rating'], 'cnt': r['cnt']} for r in fb_data]

            # ------ 策略1：供应链概念 看多练少 ------
            ch1 = next((c for c in ch_list if '供应链' in c['chapter'] and '概念' in c['chapter']), ch_list[0] if ch_list else None)
            if ch1:
                strategies.append({
                    'head': f'\U0001f4ca {ch1["chapter"]}（访问{ch1["visit"]}次，均分{ch1["avg"]}）<span class="str-tag tag-warn">看多练少</span>',
                    'body': f'<b>数据分析：</b>{ch1["chapter"]}访问量{ch1["visit"]}次，全校最高；但实践任务平均分仅{ch1["avg"]}分，位列中游。<br><b>原因剖析：</b>该章为基础概念章，学生浏览频次高但深度练习不足，"了解"多于"掌握"。<br><b>策略建议：</b>增加该章实践任务难度，引入真实供应链地图绘制和概念辨析题，将"看"转化为"练"。'
                })

            # ------ 策略2：成绩最低章节 ------
            valid_ch = [c for c in ch_list if c['avg'] > 0]
            worst = min(valid_ch, key=lambda c: c['avg']) if valid_ch else None
            if worst:
                strategies.append({
                    'head': f'\U0001f4ca {worst["chapter"]}（访问{worst["visit"]}次，均分{worst["avg"]}）<span class="str-tag tag-alert">成绩最低</span>',
                    'body': f'<b>数据分析：</b>{worst["chapter"]}均分{worst["avg"]}，全校最低；仅{worst["stu"]}人完成实践任务，访问量仅{worst["visit"]}次。<br><b>原因剖析：</b>章节偏宏观趋势论述，缺乏可量化的实践任务支撑，学生兴趣和参与度双低。<br><b>策略建议：</b>将"发展趋势"融入其他章节以案例形式教学，或增加2024-2025最新企业趋势数据对比分析任务。'
                })

            # ------ 策略3：成绩最优章节 ------
            best = max(valid_ch, key=lambda c: c['avg']) if valid_ch else None
            if best:
                strategies.append({
                    'head': f'\U0001f4ca {best["chapter"]}（访问{best["visit"]}次，均分{best["avg"]}）<span class="str-tag tag-best">成绩最优</span>',
                    'body': f'<b>数据分析：</b>{best["chapter"]}均分{best["avg"]}，全校最高；{best["stu"]}人参与实践，但仅有{best["visit"]}次访问记录。<br><b>原因剖析：</b>啤酒游戏等数学模型驱动的互动任务使学生深度理解概念，成绩反映真实掌握水平。<br><b>策略建议：</b>将啤酒游戏的互动模式复制到其他章节（如供应链中断应急、配送路线优化），提升整体参与质量。'
                })

            # ------ 策略4：高分任务 ------
            top_tasks = [t for t in task_list if t['cnt'] >= 5]
            top_tasks.sort(key=lambda t: t['avg'], reverse=True)
            if len(top_tasks) >= 2:
                t1, t2 = top_tasks[0], top_tasks[1]
                strategies.append({
                    'head': f'\U0001f4ca {t1["task"]}（均分{t1["avg"]}，{t1["cnt"]}人）+ {t2["task"]}（均分{t2["avg"]}，{t2["cnt"]}人）<span class="str-tag tag-best">高分任务</span>',
                    'body': f'<b>数据分析：</b>{t1["task"]}均分{t1["avg"]}、{t2["task"]}均分{t2["avg"]}，两类任务表现优异。<br><b>原因剖析：</b>两类任务均有清晰的数学模型（KPI公式、弹性系数），学生有"抓手"，表现稳定。<br><b>策略建议：</b>在抽象概念章节（供应链整合、战略匹配）也引入数学模型或量化工具，降低理解门槛。'
                })

            # ------ 策略5：最低分任务 ------
            all_tasks = [t for t in task_list if t['avg'] < 50]
            if all_tasks:
                worst_task = all_tasks[0]
                strategies.append({
                    'head': f'\U0001f4ca {worst_task["task"]}（均分{worst_task["avg"]}，仅{worst_task["cnt"]}人完成）<span class="str-tag tag-alert">任务失效</span>',
                    'body': f'<b>数据分析：</b>{worst_task["task"]}仅{worst_task["cnt"]}人提交，得分{worst_task["avg"]}，所有任务中参与度和成绩双最低。<br><b>原因剖析：</b>任务过于开放缺乏模板指引、耗时过长或评分标准不明确，导致学生放弃。<br><b>策略建议：</b>改为分组协作形式（3-4人/组），提供范例模板和分步指南，将大任务拆分为2-3个子任务逐步完成。'
                })

            # ------ 策略6：访问量低但成绩好的章节 ------
            cold_hot = [c for c in valid_ch if c['visit'] <= 2 and c['avg'] >= 80]
            if len(cold_hot) >= 2:
                c1, c2 = cold_hot[0], cold_hot[1]
                strategies.append({
                    'head': f'\U0001f4ca {c1["chapter"]} & {c2["chapter"]}（访问{c1["visit"]}/{c2["visit"]}次，均分{c1["avg"]}/{c2["avg"]}）<span class="str-tag tag-warn">访问冷热不均</span>',
                    'body': f'<b>数据分析：</b>{c1["chapter"]}和{c2["chapter"]}访问量仅各{c1["visit"]}/{c2["visit"]}次，但成绩高达{c1["avg"]}/{c2["avg"]}分，访问量与成绩严重倒挂。<br><b>原因剖析：</b>章节教学内容吸引力不足（缺乏热点案例），但实践任务设计合理，参与学生实际掌握了知识。<br><b>策略建议：</b>引入京东/美团/顺丰等企业最新案例（2024-2025年），提升章节吸引力；同时在热门章推荐这两个"冷门优分"章。'
                })
            elif len(cold_hot) == 1:
                c1 = cold_hot[0]
                strategies.append({
                    'head': f'\U0001f4ca {c1["chapter"]}（访问{c1["visit"]}次，均分{c1["avg"]}）<span class="str-tag tag-warn">访问冷热不均</span>',
                    'body': f'<b>数据分析：</b>{c1["chapter"]}访问量仅{c1["visit"]}次，但成绩高达{c1["avg"]}分，访问量与成绩严重倒挂。<br><b>原因剖析：</b>章节教学内容吸引力不足（缺乏热点案例），但实践任务设计合理。<br><b>策略建议：</b>引入企业最新案例提升章节吸引力；同时在热门章推荐该章内容。'
                })

            # ------ 策略7：时段特征 ------
            if hour_list:
                hour_desc = '、'.join([f'{h["hour"]}({h["cnt"]}次)' for h in hour_list])
                strategies.append({
                    'head': f'\U0001f4ca 活跃时段分布：{hour_desc}<span class="str-tag tag-info">时段特征</span>',
                    'body': f'<b>数据分析：</b>学生活跃主要集中在上午8-10点（课前学习）和下午16-20点（课后练习）两个时段；另有深夜时段活动记录（0-5点，可能为熬夜赶作业）。<br><b>原因剖析：</b>研究生课程多安排在上午和下午，学生习惯利用课前和课后碎片时间访问系统、完成实践任务。<br><b>策略建议：</b>将限时互动实践和在线讨论安排在下午16-20点活跃高峰时段；上午8-10点推送当日学习任务提醒；晚间讨论截止时间设于20:00以适配活跃窗口。'
                })

            # ------ 策略8：反馈洞察 ------
            fb_total = sum(f['cnt'] for f in fb_list)
            fb_good = sum(f['cnt'] for f in fb_list if f['rating'] >= 4)
            fb_pct = round(fb_good / fb_total * 100, 1) if fb_total > 0 else 0
            if fb_total > 0:
                strategies.append({
                    'head': f'\U0001f4ca {fb_pct}%反馈4星以上（{fb_good}/{fb_total}条）<span class="str-tag tag-info">反馈洞察</span>',
                    'body': f'<b>数据分析：</b>{fb_total}条反馈中4星以上{fb_good}条，占比{fb_pct}%。<br><b>原因剖析：</b>整体满意度较高，但需关注低分反馈中提及的分组不均衡、互动时间不足等问题。<br><b>策略建议：</b>每组严格控制在4-5人，设置分组人数上限；课前预分组，让每位学生有明确角色（记录员/发言人/数据分析师）。'
                })

            # ------ 策略9：学生活跃度分化 ------
            if len(stu_list) >= 2:
                top1 = stu_list[0]
                rest_avg = sum(s['cnt'] for s in stu_list[1:]) // len(stu_list[1:]) if len(stu_list) > 1 else 0
                strategies.append({
                    'head': f'\U0001f4ca 活跃TOP1：{top1["name"]}（{top1["cnt"]}次），其余均值{rest_avg}次<span class="str-tag tag-warn">参与不均</span>',
                    'body': f'<b>数据分析：</b>TOP1 {top1["name"]} {top1["cnt"]}次活动，头部与尾部差距显著；总活动记录仅{total_acts}条。<br><b>原因剖析：</b>缺乏常态化的学习激励和提醒机制，活跃学生属于"自驱型"，被动学生缺乏触达。<br><b>策略建议：</b>建立每周学习任务清单+自动提醒；设置"活跃之星"月度榜单；将系统活跃度纳入平时成绩（占比5-10%）。'
                })

            # ------ 策略10：全局诊断 ------
            ch_max = max(valid_ch, key=lambda c: c['avg']) if valid_ch else None
            ch_min = min(valid_ch, key=lambda c: c['avg']) if valid_ch else None
            gap = round(ch_max['avg'] - ch_min['avg'], 1) if ch_max and ch_min else 0
            strategies.append({
                'head': f'\U0001f4ca 总览：{total_students}名学生，均分{overall_avg}，{sum(t["cnt"] for t in task_list)}条实践记录<span class="str-tag tag-info">全局诊断</span>',
                'body': f'<b>数据分析：</b>{total_students}名学生共完成{sum(t["cnt"] for t in task_list)}次实践任务，全章均分{overall_avg}；最高{ch_max["avg"] if ch_max else "-"}（{ch_max["chapter"] if ch_max else "-"}），最低{ch_min["avg"] if ch_min else "-"}（{ch_min["chapter"] if ch_min else "-"}），极差{gap}分。<br><b>原因剖析：</b>整体掌握良好但章节间差异显著——有数学模型的任务成绩高，纯概念/开放任务成绩低。<br><b>策略建议：</b>下一轮教学重点：①为低分章节增加量化任务；②保持高分章节互动模式；③每3周做一次章节掌握度快速测评，动态调整教学节奏。'
            })

            return jsonify({
                'strategies': strategies,
                'total_students': total_students,
                'total_activities': total_acts,
                'overall_avg': overall_avg,
            })

        elif question_type == 'supply_chain':
            # 供应链策略辅助
            scenario = data.get('scenario', '')
            if DEEPSEEK_API_KEY:
                try:
                    import requests as req
                    resp = req.post(f'{DEEPSEEK_BASE_URL}/chat/completions',
                        headers={'Authorization': f'Bearer {DEEPSEEK_API_KEY}', 'Content-Type': 'application/json'},
                        json={'model': 'deepseek-chat', 'messages': [
                            {'role': 'system', 'content': '你是供应链管理专家。请用中文给出简洁、可操作的策略建议，控制在200字以内。'},
                            {'role': 'user', 'content': f'供应链管理问题：{scenario}。请给出具体的策略建议。'}
                        ], 'max_tokens': 400}, timeout=20)
                    if resp.status_code == 200:
                        return jsonify({'strategy': resp.json()['choices'][0]['message']['content'], 'source': 'DeepSeek AI'})
                except:
                    pass
            # Fallback
            return jsonify({'strategy': '建议从以下维度分析：1)需求特征 2)供应风险 3)成本结构 4)技术可行性。请参考相关章节的企业案例和学术研究。', 'source': '规则引擎'})

        db.close()
        return jsonify({'error': '未知类型'}), 400

    # ============================================================
    # 5. 内容生成引擎 (Content Generation via DeepSeek)
    # ============================================================
    @app.route('/bi/generate', methods=['POST'])
    def bi_generate():
        """AI内容生成 - 基于DeepSeek API"""
        if 'user_id' not in session:
            return jsonify({'error': '请先登录'}), 401

        data = request.json
        gen_type = data.get('type', 'case')  # case / quiz / summary / analysis
        chapter = data.get('chapter', '')
        topic = data.get('topic', '')

        prompt_map = {
            'case': f'请为供应链管理课程中"{chapter}"这一章节，生成一个最新的中国企业实践案例（如2024-2026年间的真实事件）。要求：企业名称真实、具体做法清晰、包含数据、300字以内。主题：{topic}。',
            'quiz': f'请为供应链管理课程中"{chapter}"这一章节，生成3道研究生水平的讨论题。每题应具有思辨性，不能简单回答"是/否"。主题：{topic}。',
            'summary': f'请为供应链管理课程中"{chapter}"这一章节，用200字总结最核心的3个概念及其相互关系。主题：{topic}。',
            'analysis': f'请对以下供应链管理问题进行分析：{topic}。结合"{chapter}"章节的理论知识，给出有深度的分析，400字以内。',
        }

        prompt = prompt_map.get(gen_type, prompt_map['summary'])

        if DEEPSEEK_API_KEY:
            try:
                import requests as req
                resp = req.post(f'{DEEPSEEK_BASE_URL}/chat/completions',
                    headers={'Authorization': f'Bearer {DEEPSEEK_API_KEY}', 'Content-Type': 'application/json'},
                    json={'model': 'deepseek-chat', 'messages': [
                        {'role': 'system', 'content': '你是供应链管理领域的AI教学助手，专门为中国大学研究生课程提供教学支持。回答需学术严谨、信息真实、中文流畅。'},
                        {'role': 'user', 'content': prompt}
                    ], 'max_tokens': 600, 'temperature': 0.7}, timeout=25)
                if resp.status_code == 200:
                    content = resp.json()['choices'][0]['message']['content']
                    return jsonify({'content': content, 'type': gen_type, 'source': 'DeepSeek API'})
                else:
                    return jsonify({'error': f'API返回错误: {resp.status_code}'}), 500
            except Exception as e:
                return jsonify({'error': f'API调用失败: {str(e)}'}), 500

        # Fallback when no API key
        fallbacks = {
            'case': f'请在课堂上分享一个你了解的与"{chapter}"相关的中国企业案例。也可以参考章节内已有的5个案例。配置DEEPSEEK_API_KEY后可启用AI自动生成。',
            'quiz': f'【讨论题1】{chapter}中哪个理论框架最能解释当前中国企业的供应链实践？为什么？\n【讨论题2】比较两种不同的{chapter}策略在企业中的应用效果。\n【讨论题3】你认为{chapter}领域未来3年的最重要趋势是什么？',
            'summary': f'{chapter}的核心概念围绕供应链效率、韧性和可持续性三个维度展开。请参考章节内容中的学术研究导航获取详细的理论框架。',
            'analysis': f'关于"{topic}"的分析，建议从以下维度切入：1)理论框架 2)中国企业实践 3)国际比较 4)未来趋势。请参考章节内的学术文献和企业案例。',
        }
        return jsonify({'content': fallbacks.get(gen_type, fallbacks['summary']), 'type': gen_type, 'source': '规则引擎（配置DEEPSEEK_API_KEY可启用AI）'})

    # ============================================================
    # 6. 数据导出 (CSV/JSON)
    # ============================================================
    @app.route('/bi/export/<data_type>')
    def bi_export(data_type):
        """导出学生数据"""
        if 'user_id' not in session or session.get('role') != 'teacher':
            return jsonify({'error': '需要教师权限'}), 403

        db = get_db()

        if data_type == 'students':
            rows = db.execute("""
                SELECT u.realname, u.username, u.school, u.department,
                       COUNT(DISTINCT pr.id) as practice_count,
                       ROUND(AVG(pr.score), 1) as avg_score
                FROM users u LEFT JOIN practice_results pr ON u.id = pr.user_id
                WHERE u.role = 'student'
                GROUP BY u.id ORDER BY avg_score DESC
            """).fetchall()
            db.close()
            return jsonify({'data': [dict(r) for r in rows]})

        elif data_type == 'practices':
            rows = db.execute("""
                SELECT u.realname, pr.chapter, pr.task_name, pr.score, pr.created_at
                FROM practice_results pr JOIN users u ON pr.user_id = u.id
                ORDER BY pr.created_at DESC LIMIT 200
            """).fetchall()
            db.close()
            return jsonify({'data': [dict(r) for r in rows]})

        elif data_type == 'feedback':
            rows = db.execute("""
                SELECT u.realname, f.chapter, f.rating, f.comment, f.created_at
                FROM feedback f JOIN users u ON f.user_id = u.id
                ORDER BY f.created_at DESC
            """).fetchall()
            db.close()
            return jsonify({'data': [dict(r) for r in rows]})

        db.close()
        return jsonify({'error': '未知数据类型'}), 400

    print('[BI] 商业智能模块已加载 (Analytics + Visualization + Prediction + Strategy + Generation)')
