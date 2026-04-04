/* ============================================================
   CV2CC — Statsig A/B Testing
   Experiments defined here map 1-to-1 with experiments you
   create in the Statsig console at https://console.statsig.com
   ============================================================ */

(function () {
  "use strict";

  const clientKey = (window.CV2CC_CONFIG || {}).statsigClientKey || "";

  // No key = skip silently (local dev without Statsig configured)
  if (!clientKey) {
    console.info("[CV2CC] Statsig client key not set — A/B testing disabled.");
    return;
  }

  // ------------------------------------------------------------------
  // Stable anonymous user ID — persists per browser so users always
  // land in the same variant across page loads
  // ------------------------------------------------------------------
  function getStableUserId() {
    const key = "cv2cc_uid";
    let uid = localStorage.getItem(key);
    if (!uid) {
      uid = "anon_" + Math.random().toString(36).slice(2) + Date.now().toString(36);
      localStorage.setItem(key, uid);
    }
    return uid;
  }

  // ------------------------------------------------------------------
  // Apply experiment variants to the DOM
  // ------------------------------------------------------------------

  /**
   * Experiment: hero_copy_test
   * Tests different headline + subheadline copy in the page hero.
   *
   * Statsig params:
   *   headline      (string) — h1 inner HTML
   *   subheadline   (string) — paragraph text below headline
   */
  function applyHeroCopyTest(exp) {
    const headline    = exp.get("headline",    null);
    const subheadline = exp.get("subheadline", null);

    const heroH1 = document.querySelector(".page-hero-text h1");
    const heroP  = document.querySelector(".page-hero-text p");

    if (heroH1 && headline)    heroH1.innerHTML = headline;
    if (heroP  && subheadline) heroP.textContent = subheadline;
  }

  /**
   * Experiment: cta_button_test
   * Tests different text on the top-nav CTA button.
   *
   * Statsig params:
   *   button_text   (string) — label on the "Load Demo" nav button
   */
  function applyCtaButtonTest(exp) {
    const buttonText = exp.get("button_text", null);
    const btn = document.getElementById("btn-load-demo");
    if (btn && buttonText) btn.textContent = buttonText;
  }

  /**
   * Experiment: ai_chips_test
   * Tests different suggestion chips shown in the AI assistant panel.
   *
   * Statsig params:
   *   chips   (array of strings) — up to 4 chip labels
   */
  function applyAiChipsTest(exp) {
    const chips = exp.get("chips", null);
    if (!Array.isArray(chips) || chips.length === 0) return;

    const container = document.querySelector(".ai-chips");
    if (!container) return;

    container.innerHTML = chips
      .slice(0, 4)
      .map(label => `<button class="ai-chip">${escHtmlAB(label)}</button>`)
      .join("");

    // Re-bind click handlers — mirrors form.js logic
    container.querySelectorAll(".ai-chip").forEach(btn => {
      btn.addEventListener("click", () => {
        const input = document.getElementById("ai-question");
        if (input) {
          input.value = btn.textContent;
          input.focus();
        }
      });
    });
  }

  function escHtmlAB(str) {
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  /**
   * Experiment: interface_test
   * Routes users between the classic multi-step form (control, "/")
   * and the AI chat-guided interface (treatment, "/chat").
   *
   * Statsig params:
   *   variant   (string) — "form" | "chat"
   *
   * Only runs on the root path so chat users are not redirected again.
   */
  function applyInterfaceTest(exp) {
    const variant = exp.get("variant", "form");
    const onForm  = window.location.pathname === "/";
    const onChat  = window.location.pathname === "/chat";

    if (variant === "chat" && onForm) {
      window.location.replace("/chat");
    } else if (variant === "form" && onChat) {
      window.location.replace("/");
    }
  }

  // ------------------------------------------------------------------
  // Initialise Statsig, then run all experiment checks
  // ------------------------------------------------------------------
  const user = { userID: getStableUserId() };

  statsig.initialize(clientKey, user, { environment: { tier: "production" } })
    .then(() => {
      // Interface routing runs first — may redirect before applying other tests
      applyInterfaceTest( statsig.getExperiment("interface_test") );

      applyHeroCopyTest(  statsig.getExperiment("hero_copy_test")  );
      applyCtaButtonTest( statsig.getExperiment("cta_button_test") );
      applyAiChipsTest(   statsig.getExperiment("ai_chips_test")   );

      // Log a custom exposure event so Statsig knows the page was viewed
      statsig.logEvent("page_view", window.location.pathname);
    })
    .catch(err => {
      console.warn("[CV2CC] Statsig init failed — running control variants.", err);
    });

})();
