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
            # 基于学生数据生成教学策略建议
            chapter = data.get('chapter', '')

            # 获取该章节的实践成绩分布
            scores = db.execute("""
                SELECT ROUND(AVG(score),1) as avg, COUNT(*) as cnt,
                       MIN(score) as min_s, MAX(score) as max_s
                FROM practice_results WHERE chapter = ? AND score > 0
            """, (chapter,)).fetchone()

            # 获取该章节的活动量
            activity = db.execute("""
                SELECT COUNT(*) as cnt FROM activity_log WHERE chapter = ?
            """, (chapter,)).fetchone()

            db.close()

            avg_score = float(scores['avg']) if scores and scores['avg'] else 0.0
            activity_cnt = int(activity['cnt']) if activity and activity['cnt'] else 0

            # 基于规则的教学策略
            strategies = []
            if avg_score > 0 and avg_score < 60:
                strategies.append('⚠️ 实践成绩偏低，建议增加课堂练习时间和案例讨论。')
            elif avg_score >= 85:
                strategies.append('✅ 实践成绩优秀，可适当增加难度或引入进阶内容。')

            if activity_cnt < 5:
                strategies.append('📉 章节活跃度较低，建议增加互动环节或调整教学内容。')
            elif activity_cnt > 50:
                strategies.append('📈 章节活跃度高，当前教学方法效果良好。')

            if not strategies:
                strategies.append('数据正常，继续保持当前教学节奏。')

            return jsonify({
                'chapter': chapter,
                'avg_score': avg_score,
                'activity_count': activity_cnt,
                'strategies': strategies,
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
