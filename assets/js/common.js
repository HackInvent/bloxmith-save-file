/**
 * Role: Provides shared Save File block UI helpers for modal and inspector surfaces.
 * File Name: common.js
 * Author: Alexandre EL
 * Email: alex@hackinvent.com
 * Created Date: 2026-06-10
 */

(function () {
  "use strict";

  const namespace = (window.CWSaveFileBlockUi = window.CWSaveFileBlockUi || {});

  /**
   * Bind Save File path settings while CWPathBrowser owns file-system browsing.
   *
   * @param {HTMLElement} root - Mounted inspector or modal root.
   * @param {object} api - Generic block UI API exposing block actions.
   * @param {object} options - Action name used by the current UI surface.
   * @returns {void}
   */
  namespace.mountSaveFileEditor = function mountSaveFileEditor(root, api, { actionName = "inspector_update_save_file" } = {}) {
    const pathInput = root.querySelector("[data-save-file-path]");
    const appendInput = root.querySelector("[data-save-file-append]");
    const showDoneButton = root.querySelector("[data-save-file-show-done-output]");
    const applyButton = root.querySelector("[data-save-file-apply]") || root.querySelector("[data-block-apply]");
    let dirty = false;

    const markDirty = () => {
      dirty = true;
      if (applyButton) {
        applyButton.disabled = false;
      }
    };

    const apply = () => {
      if (!dirty) {
        return;
      }
      void api.applyAction(actionName, {
        path: pathInput?.value || "",
        append: Boolean(appendInput?.checked),
      }).then(() => {
        dirty = false;
        if (applyButton) {
          applyButton.disabled = true;
        }
      }).catch((error) => {
        api.log?.(`[error] Mise à jour Save File impossible: ${error.message}`);
      });
    };

    pathInput?.addEventListener("input", markDirty);
    pathInput?.addEventListener("change", markDirty);
    pathInput?.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        apply();
      }
    });
    appendInput?.addEventListener("change", markDirty);
    applyButton?.addEventListener("click", apply);
    showDoneButton?.addEventListener("click", () => {
      void api.applyAction("save_file_show_done_output", {}).catch((error) => {
        api.log?.(`[error] Ajout de la sortie Done impossible: ${error.message}`);
      });
    });
  };
})();
