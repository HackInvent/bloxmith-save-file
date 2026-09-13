/**
 * Role: Mounts the save file block modal frontend.
 * File Name: block_modal.js
 * Author: Alexandre EL
 * Email: alex@hackinvent.com
 * Created Date: 2026-06-10
 */

(function () {
  "use strict";

  const registry = (window.CWBlockUiBlocks = window.CWBlockUiBlocks || {});

  registry.save_file = {
    /**
     * Mount the Save File modal bindings using the modal update action.
     *
     * @param {HTMLElement} root - Mounted Save File modal root.
     * @param {object} api - Generic block UI API exposing block actions.
     * @returns {void}
     */
    mount(root, api) {
      window.CWSaveFileBlockUi?.mountSaveFileEditor?.(root, api, { actionName: "modal_update_save_file" });
    },
  };
})();
