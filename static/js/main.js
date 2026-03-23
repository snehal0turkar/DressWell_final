// ─── GLOBAL UTILS ────────────────────────────────────────────────────────────

function showToast(message, type = 'success') {
    let container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast toast--${type}`;
    toast.innerHTML = `
        <span class="toast-icon">${type === 'success' ? '✓' : '✕'}</span>
        <span>${message}</span>
    `;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(20px)';
        toast.style.transition = 'all 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// ─── NAV TOGGLE (mobile) ─────────────────────────────────────────────────────

const navToggle = document.getElementById('navToggle');
const sidenav   = document.getElementById('sidenav');

// Create mobile overlay backdrop
let navOverlay = null;
function getOverlay() {
    if (!navOverlay) {
        navOverlay = document.createElement('div');
        navOverlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:99;display:none';
        navOverlay.addEventListener('click', closeNav);
        document.body.appendChild(navOverlay);
    }
    return navOverlay;
}
function openNav() {
    sidenav.classList.add('sidenav--open');
    navToggle.classList.add('nav-toggle--open');
    const ov = getOverlay();
    ov.style.display = 'block';
    document.body.style.overflow = 'hidden';
}
function closeNav() {
    sidenav.classList.remove('sidenav--open');
    navToggle.classList.remove('nav-toggle--open');
    if (navOverlay) navOverlay.style.display = 'none';
    document.body.style.overflow = '';
}

if (navToggle && sidenav) {
    navToggle.addEventListener('click', () => {
        sidenav.classList.contains('sidenav--open') ? closeNav() : openNav();
    });
    // Close when a nav link is clicked on mobile
    sidenav.querySelectorAll('.nav-link').forEach(link => {
        link.addEventListener('click', () => {
            if (window.innerWidth <= 768) closeNav();
        });
    });
}

// ─── INTERSECTION OBSERVER for [data-anim] ────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    const observer = new IntersectionObserver(entries => {
        entries.forEach(e => {
            if (e.isIntersecting) {
                e.target.classList.add('in-view');
                observer.unobserve(e.target);
            }
        });
    }, { threshold: 0.08 });

    document.querySelectorAll('[data-anim]').forEach(el => observer.observe(el));
});

// ─── SMOOTH HOVER on cards ───────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.outfit-card, .stat-card, .clothes-card').forEach(card => {
        card.addEventListener('mousemove', e => {
            const rect = card.getBoundingClientRect();
            const x = ((e.clientX - rect.left) / rect.width - 0.5) * 6;
            const y = ((e.clientY - rect.top) / rect.height - 0.5) * 6;
            card.style.transform = `perspective(800px) rotateX(${-y}deg) rotateY(${x}deg) translateY(-2px)`;
        });
        card.addEventListener('mouseleave', () => {
            card.style.transform = '';
        });
    });
});

// ─── KEYBOARD SHORTCUTS ──────────────────────────────────────────────────────

document.addEventListener('keydown', e => {
    // Escape closes modals
    if (e.key === 'Escape') {
        document.querySelectorAll('.modal-overlay--active').forEach(m => {
            m.classList.remove('modal-overlay--active');
        });
    }
});
