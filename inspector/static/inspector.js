document.addEventListener("keydown", (e) => {
  if (e.defaultPrevented || e.isComposing || e.key !== "/" || e.ctrlKey || e.metaKey || e.altKey || e.shiftKey) return;
  const t = e.target;
  if (t instanceof Element && t.closest("input, textarea, select, [role='textbox'], [role='combobox']")) return;
  if (t instanceof HTMLElement && t.isContentEditable) return;
  const input = document.getElementById("home-project-input") || document.getElementById("project-input");
  if (!input) return;
  e.preventDefault();
  input.focus();
  input.select();
});
