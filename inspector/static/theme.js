// SPDX-License-Identifier: Apache-2.0
(() => {
  "use strict";
  const storageKey = "inspector-theme";
  const systemTheme = window.matchMedia("(prefers-color-scheme: dark)");
  const isValidPreference = (value) => value === "light" || value === "dark";

  function readPreference() {
    try {
      const stored = window.localStorage.getItem(storageKey);
      return isValidPreference(stored) ? stored : null;
    } catch {
      // Storage unavailable (e.g. disabled, private mode): fall back to system.
      return null;
    }
  }

  function writePreference(value) {
    try {
      if (value) window.localStorage.setItem(storageKey, value);
      else window.localStorage.removeItem(storageKey);
    } catch {
      // Keep this tab's explicit choice in memory even if it cannot be persisted.
    }
  }

  let preference = readPreference();

  function effectiveTheme() {
    return preference || (systemTheme.matches ? "dark" : "light");
  }

  function updateControls(theme) {
    const current = preference || "system";
    const next = preference === "light" ? "dark" : preference === "dark" ? "system" : "light";
    const description = current === "system" ? `system (${theme})` : current;
    document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
      button.querySelectorAll("[data-theme-icon]").forEach((icon) => {
        icon.toggleAttribute("hidden", icon.dataset.themeIcon !== current);
      });
      button.setAttribute("aria-label", `Theme: ${description}. Switch to ${next} mode`);
      button.title = button.getAttribute("aria-label");
    });
  }

  function applyTheme() {
    const theme = effectiveTheme();
    document.documentElement.dataset.theme = theme;
    document.documentElement.dataset.themePreference = preference || "system";
    updateControls(theme);
  }

  applyTheme();

  document.addEventListener(
    "DOMContentLoaded",
    () => {
      document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
        button.hidden = false;
      });
      updateControls(effectiveTheme());
    },
    { once: true },
  );

  document.addEventListener("click", (event) => {
    const button = event.target instanceof Element ? event.target.closest("[data-theme-toggle]") : null;
    if (!button || button.disabled) return;
    preference = preference === "light" ? "dark" : preference === "dark" ? null : "light";
    writePreference(preference);
    applyTheme();
  });

  systemTheme.addEventListener("change", () => {
    if (!preference) applyTheme();
  });

  window.addEventListener("storage", (event) => {
    if (event.key !== storageKey && event.key !== null) return;
    try {
      if (event.storageArea !== window.localStorage) return;
    } catch {
      return;
    }
    preference = isValidPreference(event.newValue) ? event.newValue : null;
    applyTheme();
  });
})();
