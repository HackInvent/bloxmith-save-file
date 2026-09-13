# Save File Block

<!-- block-metadata:start -->
[![Block version: unversioned](https://img.shields.io/badge/block-unversioned-lightgrey)](model.json)
[![BloxSmith compatibility: 1.0.9](https://img.shields.io/badge/BloxSmith-1.0.9-brightgreen)](compatibility.json)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

Verified BloxSmith versions: **1.0.9** (bundled-block tests; see [test evidence](compatibility.json)).
<!-- block-metadata:end -->


## Role

`save_file` writes incoming content to a configured file path, or to the path supplied by its optional `path` input when connected.

## Files

- `block.py`: target path resolution, write modes, formatting, write serialization, modal rendering, and inspector actions.
- `model.json`: content/path inputs, optional operational output metadata, and default file config.
- `block_modal.html`, `inspector_panel.html`, `assets/`: save-file modal and inspector UI.
- `node_card.html`: block-owned canvas card body.

## Ports

- Inputs:
  - `contenu` (`id: 1`): optional `message/*`.
  - `path` (`id: 2`): optional target file override. Accepts `file/path`, plain text, message payloads, or JSON wrappers containing `path`.

- Outputs:
  - none by default.
  - optional `done`: operational trigger output, hidden by absence until materialized from the inspector. It emits `true` with `control/trigger` only after the write succeeds.

## Configuration

- `path`: default target output file path, resolved from the project root when relative. The runtime `path` input overrides this value when provided.
- `mode`: write behavior, such as overwrite or append.
- `append`: boolean append flag synchronized with `mode`.
- `encoding`: text encoding used for writes.

## Runtime Behavior

`execute_runtime()` reads incoming content from the `contenu` input, resolves the target from the `path` input or configured `config.path`, serializes writes through a process-local queue, writes or appends according to mode, and returns write metadata/logs. If a `done` output port has been materialized, it publishes `true` only after the write has completed successfully.

## UI Behavior

The inspector and modal edit `config.path` and append mode through `inspector_update_save_file` or
`modal_update_save_file`. They read current canonical `node.config` values. Edits stay pending until the user clicks **Apply**. Path
selection uses the shared `CWPathBrowser` control and `/api/blocks/save_file/browse-files`. The ports
tab can materialize the optional `Done` output through `save_file_show_done_output`; the resulting
graph operation is applied immediately by the Python graph controller because it changes graph
structure.

## Editor Display

The canvas card is rendered by this block through `node_card.html`. It exposes the effective target path and write mode while the shared editor shell keeps ports, dragging, status, and graph links generic.

## Modal

`block_modal.html` is owned by this block. It keeps the generic title binding and exposes the same
target file browser, append option, ports, and runtime state as the inspector.

## Maintenance Notes

Keep write ordering and path safety inside this block. Any change to modes must update tests for overwrite/append behavior.

## UI surface migration

- The modal declares `data-block-runtime-refresh="autonomous"` so target path and append-mode drafts survive runtime polling.
- Shared Save File UI helpers live in `assets/js/common.js`.
- Modal behavior is mounted by `assets/js/block_modal.js`; inspector behavior is mounted by `assets/js/inspector_panel.js`.
- Durable target file edits and optional Done-port creation continue to go through block-owned UI actions.

## Compatibility policy

[compatibility.json](compatibility.json) records HackInvent's verified BloxSmith versions and test evidence. Only the versions listed above have been verified, using the block-owned suites in a **bundled-block test installation**. This is not a certification of managed-package installation, every browser/OS, or live provider availability. Other framework versions are unverified, not necessarily incompatible.

The block-version badge follows `model.json`, not a published Git tag. `unversioned` means that no block release version is declared; no number is inferred from the framework version. The framework still uses `model.json` for its runtime/install contract; the tester-owned JSON does not replace it. Official integration tests run in the private `bloxmith-blocs` workspace. Test helpers and the proprietary framework are not bundled in this public block repository.
