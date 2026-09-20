/**
 * Role: Mounts the save file block inspector panel frontend.
 * File Name: inspector_panel.js
 * Author: Alexandre EL
 * Email: alex@hackinvent.com
 * Created Date: 2024-12-23
 */

import { mountSaveFileEditor } from "./common.js";

/**
 * Mount the Save File inspector panel bindings.
 *
 * @param {HTMLElement} root - Mounted Save File inspector root.
 * @param {object} api - Generic block UI API exposing block actions.
 * @returns {void}
 */
export function mount(root, api) {
  mountSaveFileEditor(root, api, { actionName: "inspector_update_save_file" });
}
