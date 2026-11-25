/* Shared UI utilities — no browser alert()/confirm()/prompt() popups */
(function () {
    'use strict';

    const ICON_MAP = {
        success: 'fa-circle-check',
        error: 'fa-circle-exclamation',
        warning: 'fa-triangle-exclamation',
        info: 'fa-circle-info',
    };

    function getCookie(name) {
        if (!document.cookie) return null;
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.startsWith(name + '=')) {
                return decodeURIComponent(cookie.substring(name.length + 1));
            }
        }
        return null;
    }

    function showToast(message, type = 'info', duration = 4000) {
        let container = document.getElementById('toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toast-container';
            container.className = 'toast-container';
            document.body.appendChild(container);
        }

        const safeType = ICON_MAP[type] ? type : 'info';
        const toast = document.createElement('div');
        toast.className = `glass-toast glass-toast--${safeType}`;
        toast.setAttribute('role', 'status');

        const icon = document.createElement('i');
        icon.className = `fa-solid ${ICON_MAP[safeType]}`;

        const text = document.createElement('span');
        text.className = 'glass-toast__text';
        text.textContent = message;

        const closeBtn = document.createElement('button');
        closeBtn.type = 'button';
        closeBtn.className = 'glass-toast__close';
        closeBtn.setAttribute('aria-label', 'Dismiss notification');
        closeBtn.innerHTML = '<i class="fa-solid fa-xmark"></i>';
        closeBtn.addEventListener('click', () => dismissToast(toast));

        toast.append(icon, text, closeBtn);
        container.appendChild(toast);

        if (duration > 0) {
            setTimeout(() => dismissToast(toast), duration);
        }
    }

    function dismissToast(toast) {
        if (!toast || toast.dataset.dismissed) return;
        toast.dataset.dismissed = '1';
        toast.classList.add('glass-toast--leaving');
        setTimeout(() => toast.remove(), 220);
    }

    function updateCartBadge(count, animate = false) {
        const badge = document.querySelector('.cart-badge');
        if (!badge) return;
        const parsed = parseInt(count, 10) || 0;
        badge.textContent = parsed;
        badge.classList.toggle('hidden', parsed <= 0);
        badge.style.display = parsed > 0 ? 'inline-flex' : 'none';
        if (animate && parsed > 0) {
            badge.classList.remove('cart-badge--pop');
            void badge.offsetWidth;
            badge.classList.add('cart-badge--pop');
        }
    }

    async function parseJsonSafe(response) {
        const text = await response.text();
        if (!text) return {};
        try {
            return JSON.parse(text);
        } catch {
            return { message: 'Unexpected server response.' };
        }
    }

    function bindAddToCartForms() {
        const forms = document.querySelectorAll('.add-to-cart-form, #addToCartDetailForm');
        forms.forEach(form => {
            form.addEventListener('submit', async function (event) {
                event.preventDefault();
                const submitBtn = form.querySelector('button[type="submit"]');
                const originalHtml = submitBtn ? submitBtn.innerHTML : '';
                if (submitBtn) {
                    submitBtn.disabled = true;
                    submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Adding...';
                }

                try {
                    const formData = new FormData(form);
                    const csrfToken = formData.get('csrfmiddlewaretoken') || getCookie('csrftoken');
                    const response = await fetch(form.action, {
                        method: 'POST',
                        body: formData,
                        headers: {
                            'X-CSRFToken': csrfToken,
                            'X-Requested-With': 'XMLHttpRequest',
                        },
                    });

                    const data = await parseJsonSafe(response);
                    if (response.status === 401 && data.login_url) {
                        showToast(data.message || 'Please log in to continue.', 'warning', 2000);
                        setTimeout(() => { window.location.href = data.login_url; }, 650);
                        return;
                    }

                    if (response.ok && data.success) {
                        updateCartBadge(data.cart_item_count, true);
                        if (submitBtn) {
                            submitBtn.classList.add('add-to-cart-btn--added');
                            submitBtn.innerHTML = '<i class="fa-solid fa-check"></i> Added';
                            setTimeout(() => {
                                submitBtn.classList.remove('add-to-cart-btn--added');
                                submitBtn.innerHTML = originalHtml;
                                submitBtn.disabled = false;
                            }, 1100);
                        }
                        showToast(data.message || 'Added to cart.', 'success');
                    } else {
                        if (submitBtn) {
                            submitBtn.disabled = false;
                            submitBtn.innerHTML = originalHtml;
                        }
                        showToast(data.message || 'Could not add item to cart.', 'error');
                    }
                } catch {
                    if (submitBtn) {
                        submitBtn.disabled = false;
                        submitBtn.innerHTML = originalHtml;
                    }
                    showToast('Network error while adding to cart.', 'error');
                }
            });
        });
    }

    document.addEventListener('DOMContentLoaded', () => {
        bindAddToCartForms();
    });

    window.FurnitureUI = {
        getCookie,
        showToast,
        updateCartBadge,
        parseJsonSafe,
    };
})();
