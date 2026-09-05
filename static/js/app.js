/**
 * RetailIQ — Core Client Application Script
 * Track ID: PS03 (NexusTiQ24)
 * Manages drawer navigation, modal dialogues, and global state.
 */

// Global Data Mode State (demo vs user vs all)
window.currentDataMode = localStorage.getItem('retailiq_data_mode') || 'demo';

function changeDataMode(mode) {
  window.currentDataMode = mode;
  localStorage.setItem('retailiq_data_mode', mode);
  
  // Reload current page with data_mode param
  const url = new URL(window.location.href);
  url.searchParams.set('data_mode', mode);
  window.location.href = url.toString();
}

// Modal Management
function openModal(id) {
  const modal = document.getElementById(id);
  if (modal) {
    modal.classList.add('active');
    document.body.style.overflow = 'hidden';
  }
}

function closeModal(id) {
  const modal = document.getElementById(id);
  if (modal) {
    modal.classList.remove('active');
    document.body.style.overflow = '';
  }
}

// Close modal when clicking on backdrop
document.addEventListener('click', (e) => {
  if (e.target && e.target.classList.contains('modal-backdrop')) {
    e.target.classList.remove('active');
    document.body.style.overflow = '';
  }
});

// Close modal on Escape key
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    document.querySelectorAll('.modal-backdrop.active').forEach(m => {
      m.classList.remove('active');
    });
    document.body.style.overflow = '';
  }
});

// Mobile Sidebar Drawer Management
document.addEventListener('DOMContentLoaded', () => {
  const sidebar = document.getElementById('appSidebar');
  const toggleBtn = document.getElementById('sidebarToggleBtn');
  const closeBtn = document.getElementById('sidebarCloseBtn');
  const backdrop = document.getElementById('sidebarBackdrop');

  if (toggleBtn && sidebar && backdrop) {
    toggleBtn.addEventListener('click', () => {
      sidebar.classList.add('open');
      backdrop.classList.add('active');
    });
  }

  if (closeBtn && sidebar && backdrop) {
    closeBtn.addEventListener('click', () => {
      sidebar.classList.remove('open');
      backdrop.classList.remove('active');
    });
  }

  if (backdrop && sidebar) {
    backdrop.addEventListener('click', () => {
      sidebar.classList.remove('open');
      backdrop.classList.remove('active');
    });
  }

  // Synchronize data mode selector if present
  const modeSelect = document.getElementById('globalDataMode');
  if (modeSelect) {
    const urlParams = new URLSearchParams(window.location.search);
    const paramMode = urlParams.get('data_mode');
    if (paramMode) {
      modeSelect.value = paramMode;
      window.currentDataMode = paramMode;
    } else {
      modeSelect.value = window.currentDataMode;
    }
  }

  // Update sidebar alert badge if endpoint accessible
  const alertBadge = document.getElementById('nav-alert-count');
  if (alertBadge) {
    fetch('/api/alerts?data_mode=' + window.currentDataMode)
      .then(res => res.json())
      .then(data => {
        const count = (data.alerts && data.alerts.length) || 0;
        alertBadge.textContent = count > 0 ? `${count}` : '0';
        if (count > 0) {
          alertBadge.style.backgroundColor = 'rgba(239, 68, 68, 0.2)';
          alertBadge.style.color = '#fca5a5';
        }
      })
      .catch(() => {});
  }
});
