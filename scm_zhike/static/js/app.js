# SCM智课 - JavaScript utilities
// Shared helper functions for the system

// ============================================================
// Feedback modal (for pages that include it)
// ============================================================
window.setRating = function(v) {
    window._feedbackRating = v;
    const el = document.getElementById('feedback-rating');
    if (el) el.value = v;
    document.querySelectorAll('.star-rating span').forEach((s, i) => {
        s.style.opacity = i < v ? '1' : '0.3';
    });
};

window.submitFeedback = function() {
    const modal = document.getElementById('feedback-modal');
    if (modal) modal.style.display = 'flex';
};

window.closeFeedback = function() {
    const modal = document.getElementById('feedback-modal');
    if (modal) modal.style.display = 'none';
};

window.doSubmitFeedback = async function() {
    const rating = document.getElementById('feedback-rating')?.value || 5;
    const comment = document.getElementById('feedback-comment')?.value || '';
    const chapter = document.querySelector('meta[name="chapter-name"]')?.content || '';
    try {
        await fetch('/api/feedback', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({chapter, rating: parseInt(rating), comment})
        });
        closeFeedback();
        alert('感谢你的反馈！');
    } catch(e) {
        alert('提交失败，请重试');
    }
};
