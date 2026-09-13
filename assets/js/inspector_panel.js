/**
 * Role: Mounts the save file block inspector panel frontend.
 * File Name: inspector_panel.js
 * Author: Alexandre EL
 * Email: alex@hackinvent.com
 * Created Date: 2024-12-23
 */

(function () {
  "use strict";

  const registry = (window.CWBlockUiBlocks = window.CWBlockUiBlocks || {});

  registry.save_fileInspectorPanel = {
    /**
     * Mount the Save File inspector panel bindings.
     *
     * @param {HTMLElement} root - Mounted Save File inspector root.
     * @param {object} api - Generic block UI API exposing block actions.
     * @returns {void}
     */
    mount(root, api) {
      window.CWSaveFileBlockUi?.mountSaveFileEditor?.(root, api, { actionName: "inspector_update_save_file" });
    },
  };
})();
