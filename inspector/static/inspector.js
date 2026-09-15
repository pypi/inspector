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

// Installer choices and cookie follow pypi/warehouse#19984 (Apache-2.0).
document.querySelectorAll("[data-installer-command]").forEach((control) => {
  const commands = { pip: "install", uv: "add", poetry: "add", pdm: "add", pipenv: "install" };
  const select = control.querySelector("select");
  const suffix = control.querySelector("[data-installer-suffix]");
  const full = control.querySelector("#pip-install-cmd");
  const copy = control.querySelector("[data-copy-target]");
  const releaseCopies = document.querySelectorAll("[data-copy-project]");
  const saved = document.cookie.match(/(?:^|;\s*)pypi-installer=(pip|uv|poetry|pdm|pipenv|name)(?:;|$)/);
  if (saved) select.value = saved[1];

  const commandFor = (name, spec, installer) => {
    if (installer === "name") return name;
    const target = name + spec;
    return `${installer} ${commands[installer]} ${spec.includes("!") ? "'" + target + "'" : target}`;
  };

  const render = () => {
    const installer = select.value;
    const nameOnly = installer === "name";
    const command = commandFor(control.dataset.project, control.dataset.spec, installer);
    suffix.textContent = nameOnly ? command : command.slice(installer.length + 1);
    full.textContent = command;
    copy.setAttribute("aria-label", nameOnly ? "Copy project name" : "Copy command");
    releaseCopies.forEach((button) => {
      button.dataset.copyText = commandFor(button.dataset.copyProject, button.dataset.copySpec, installer);
      button.setAttribute("aria-label", nameOnly
        ? `Copy project name for ${button.dataset.copySpec.slice(2)}`
        : `Copy ${installer} command for ${button.dataset.copySpec.slice(2)}`);
    });
  };

  select.addEventListener("change", () => {
    document.cookie = `pypi-installer=${select.value}; max-age=31536000; path=/; SameSite=Lax`;
    render();
  });
  render();
  select.disabled = false;
});
