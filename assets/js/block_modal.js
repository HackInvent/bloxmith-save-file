import { withProperties } from "./properties.js";

/**
 * Role: Mounts the save file block modal frontend.
 * File Name: block_modal.js
 * Author: Alexandre EL
 * Email: alex@hackinvent.com
 * Created Date: 2026-06-10
 */

import { mountSaveFileEditor } from "./common.js";

/**
 * Mount the Save File modal bindings using the modal update action.
 *
 * @param {HTMLElement} root - Mounted Save File modal root.
 * @param {object} api - Generic block UI API exposing block actions.
 * @returns {void}
 */
function mountOwned(root, api) {
  mountSaveFileEditor(root, api, { actionName: "modal_update_save_file" });
}

/** Keep the block behavior and add properties-only accessibility. */
export function mount(root, ...args) {
  return withProperties(mountOwned).call(this, root, ...args);
}
