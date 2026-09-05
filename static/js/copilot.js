/**
 * RetailIQ AI Copilot Interactive Client
 * Powers the conversational decision assistant with grounded evidence rendering.
 */

window.Copilot = {
  chatHistory: [],
  isWaiting: false,

  init() {
    const input = document.getElementById("copilot-input");
    const sendBtn = document.getElementById("btn-send-query");
    const clearBtn = document.getElementById("btn-clear-chat");
    const exportBtn = document.getElementById("btn-export-chat");

    if (sendBtn) {
      sendBtn.addEventListener("click", () => this.handleSend());
    }
    if (input) {
      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          this.handleSend();
        }
      });
    }
    if (clearBtn) {
      clearBtn.addEventListener("click", () => this.clearChat());
    }
    if (exportBtn) {
      exportBtn.addEventListener("click", () => this.exportChat());
    }

    // Bind suggested chips
    document.querySelectorAll(".chip").forEach(chip => {
      chip.addEventListener("click", () => {
        const queryText = chip.getAttribute("data-query");
        if (queryText) {
          this.ask(queryText);
        }
      });
    });

    // Add initial greeting if history is empty
    if (this.chatHistory.length === 0) {
      this.renderGreeting();
    }
  },

  renderGreeting() {
    const container = document.getElementById("chat-messages-container");
    if (!container) return;

    container.innerHTML = `
      <div class="message-row assistant">
        <div class="message-avatar">🤖</div>
        <div class="message-bubble">
          <div class="copilot-response-title">👋 Welcome to RetailIQ Copilot</div>
          <div class="copilot-summary">
            I am your AI-Powered Sales & Inventory Copilot. Every figure and recommendation I provide is backed by 
            <strong>deterministic calculations</strong> from your store's verified database records.
          </div>
          <div class="grounded-evidence-box">
            <div class="evidence-box-title">🛡️ Strict Grounding & No-Hallucination Policy</div>
            <div class="evidence-item">Calculates exact stock runways, sales velocities, spikes, and drops.</div>
            <div class="evidence-item">Provides mathematical replenishment amounts and transparent assumptions.</div>
            <div class="evidence-item">Explicitly alerts you when available data cannot answer external questions.</div>
          </div>
          <div style="font-size: 0.85rem; color: #94a3b8; margin-top: 8px;">
            Try asking one of the suggested questions below, or choose a pre-configured demo scenario!
          </div>
        </div>
      </div>
    `;
  },

  ask(queryText) {
    const input = document.getElementById("copilot-input");
    if (input) input.value = queryText;
    this.handleSend();
  },

  async handleSend() {
    const input = document.getElementById("copilot-input");
    if (!input || this.isWaiting) return;

    const query = input.value.trim();
    if (!query) return;

    // Clear input
    input.value = "";

    // Append user message
    this.appendUserMessage(query);

    // Show loading state
    this.isWaiting = true;
    const loadingId = this.appendLoadingMessage();

    // Get active store filter
    const storeSelector = document.getElementById("global-store-selector");
    const storeId = storeSelector && storeSelector.value ? parseInt(storeSelector.value) : null;
    const modeSelector = document.getElementById("global-data-mode-selector");
    const dataMode = (modeSelector && modeSelector.value) || (window.RetailApp && RetailApp.dataMode) || "demo";

    try {
      const response = await fetch("/api/copilot/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: query, store_id: storeId, data_mode: dataMode })
      });

      const data = await response.json();
      this.removeLoadingMessage(loadingId);

      if (response.ok) {
        this.appendAssistantResponse(data);
        this.chatHistory.push({ query: query, response: data, timestamp: new Date().toISOString() });
      } else {
        this.appendErrorMessage(data.message || data.error || "Error processing analytics query.");
      }
    } catch (err) {
      this.removeLoadingMessage(loadingId);
      this.appendErrorMessage(`Network or server failure: ${err.message}`);
    } finally {
      this.isWaiting = false;
      this.scrollToBottom();
    }
  },

  appendUserMessage(text) {
    const container = document.getElementById("chat-messages-container");
    if (!container) return;

    const row = document.createElement("div");
    row.className = "message-row user";
    row.innerHTML = `
      <div class="message-avatar">👤</div>
      <div class="message-bubble">${this.escapeHtml(text)}</div>
    `;
    container.appendChild(row);
    this.scrollToBottom();
  },

  appendLoadingMessage() {
    const container = document.getElementById("chat-messages-container");
    if (!container) return "";

    const id = "loading-" + Date.now();
    const row = document.createElement("div");
    row.id = id;
    row.className = "message-row assistant";
    row.innerHTML = `
      <div class="message-avatar">🤖</div>
      <div class="message-bubble" style="display: flex; align-items: center; gap: 12px;">
        <span class="spinner"></span>
        <span style="font-size: 0.88rem; color: #94a3b8;">Analyzing verified store data & calculating evidence...</span>
      </div>
    `;
    container.appendChild(row);
    this.scrollToBottom();
    return id;
  },

  removeLoadingMessage(id) {
    const elem = document.getElementById(id);
    if (elem) elem.remove();
  },

  appendAssistantResponse(data) {
    const container = document.getElementById("chat-messages-container");
    if (!container) return;

    const row = document.createElement("div");
    row.className = "message-row assistant";

    let evidenceHtml = "";
    if (data.evidence && data.evidence.length > 0) {
      evidenceHtml = `
        <div class="grounded-evidence-box">
          <div class="evidence-box-title">📊 Verified Evidence & Lineage (${data.evidence.length} metrics)</div>
          ${data.evidence.map(e => `
            <div class="evidence-item">
              <strong>${this.escapeHtml(e.metric)}:</strong> <code>${this.escapeHtml(String(e.value))}</code><br>
              <span style="font-size: 0.75rem; color: #64748b;">
                Source: <code>${this.escapeHtml(e.source_table)}</code> | Window: ${this.escapeHtml(e.date_range)}
              </span>
            </div>
          `).join("")}
        </div>
      `;
    }

    let recsHtml = "";
    if (data.recommendations && data.recommendations.length > 0) {
      recsHtml = `
        <div class="recommendations-box">
          <div class="recommendations-title">⚡ Recommended Operational Actions</div>
          <ul style="padding-left: 18px; font-size: 0.85rem; color: #d1fae5;">
            ${data.recommendations.map(r => `<li>${this.escapeHtml(r)}</li>`).join("")}
          </ul>
        </div>
      `;
    }

    let assumptionsHtml = "";
    if (data.assumptions && data.assumptions.length > 0) {
      assumptionsHtml = `
        <div class="assumptions-box">
          <strong>Assumptions & Rules:</strong> ${data.assumptions.map(a => this.escapeHtml(a)).join(" • ")}
        </div>
      `;
    }

    let limitationsHtml = "";
    if (data.data_limitations) {
      limitationsHtml = `
        <div class="data-limitations-box">
          <div class="limitations-title">🛡️ Data Boundary / What The Data Can't Answer</div>
          <div style="font-size: 0.82rem; color: #fca5a5;">${this.escapeHtml(data.data_limitations)}</div>
        </div>
      `;
    }

    // Model used tag
    const modelBadge = data.model_used.includes("gemini")
      ? `<span class="badge badge-purple" style="margin-left: auto;">Gemini Powered</span>`
      : `<span class="badge badge-info" style="margin-left: auto;">Deterministic Verified</span>`;

    row.innerHTML = `
      <div class="message-avatar">🤖</div>
      <div class="message-bubble" style="width: 100%;">
        <div class="copilot-response-title">
          <span>${this.escapeHtml(data.title || "Decision Intelligence")}</span>
          ${modelBadge}
        </div>
        <div class="copilot-summary">${this.formatMarkdown(data.summary)}</div>
        ${evidenceHtml}
        ${recsHtml}
        ${assumptionsHtml}
        ${limitationsHtml}
      </div>
    `;

    container.appendChild(row);
    this.scrollToBottom();
  },

  appendErrorMessage(errorText) {
    const container = document.getElementById("chat-messages-container");
    if (!container) return;

    const row = document.createElement("div");
    row.className = "message-row assistant";
    row.innerHTML = `
      <div class="message-avatar" style="background: #ef4444;">⚠️</div>
      <div class="message-bubble" style="border-color: rgba(239, 68, 68, 0.4); background: rgba(239, 68, 68, 0.1);">
        <div style="font-weight: 700; color: #f87171; margin-bottom: 4px;">Analytics Processing Notice</div>
        <div style="font-size: 0.88rem; color: #fca5a5;">${this.escapeHtml(errorText)}</div>
      </div>
    `;
    container.appendChild(row);
    this.scrollToBottom();
  },

  clearChat() {
    this.chatHistory = [];
    this.renderGreeting();
    RetailApp.showToast("Chat session cleared.");
  },

  exportChat() {
    if (this.chatHistory.length === 0) {
      RetailApp.showToast("No chat messages to export.", "error");
      return;
    }
    const jsonStr = JSON.stringify(this.chatHistory, null, 2);
    const blob = new Blob([jsonStr], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `retailiq-copilot-session-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
    RetailApp.showToast("Copilot session exported successfully!");
  },

  scrollToBottom() {
    const container = document.getElementById("chat-messages-container");
    if (container) {
      container.scrollTop = container.scrollHeight;
    }
  },

  escapeHtml(text) {
    if (typeof text !== "string") return String(text);
    return text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  },

  formatMarkdown(text) {
    if (!text) return "";
    let formatted = this.escapeHtml(text);
    // Bold **text**
    formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    // Inline code `text`
    formatted = formatted.replace(/`(.*?)`/g, '<code style="background: rgba(255,255,255,0.08); padding: 2px 4px; border-radius: 4px;">$1</code>');
    // Bullet points
    formatted = formatted.replace(/^\s*[-•]\s+(.*)$/gm, '<li style="margin-left: 18px;">$1</li>');
    // Paragraph newlines
    formatted = formatted.replace(/\n\n/g, '<br><br>');
    return formatted;
  }
};
