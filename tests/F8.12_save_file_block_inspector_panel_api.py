#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# Role: Verifies save file block inspector panel API behavior for the save file block.
# File Name: F8.12_save_file_block_inspector_panel_api.py
# Author: Alexandre EL
# Email: alex@hackinvent.com
# Created Date: 2024-04-12
# -----------------------------------------------------------------------------

"""F8.12 - UI modulaire du panneau inspecteur Save File.

Le test démarre un serveur isolé, demande le rendu du panneau inspecteur
`save_file` depuis `block.py`, vérifie les assets exposés, puis teste l'action
structurée de mise à jour du chemin et du mode append. Aucune donnée utilisateur
n'est modifiée hors du serveur de test.
"""

# Test cases:
# - SaveFile UI - Render the SaveFile inspector panel through the block API using current config values.
# - SaveFile UI - Apply structured path/mode/header updates and verify the returned config node patch.
# - SaveFile UI - Verify inspector assets are served by the SaveFile block package.

from __future__ import annotations

from urllib.parse import quote
from urllib.request import urlopen

from ui_smoke_common import expect, http_json, isolated_server

from bloxsmith_app.block_ui import block_ui_result_to_graph_operations


def main() -> None:
    with isolated_server() as server:
        node = {
            "id": "save-file-1",
            "kind": "save_file",
            "type": "save_file",
            "title": "Save File",
            "config": {"path": "exports/resultat.txt", "append": True, "mode": "append", "encoding": "utf-8"},
        }
        rendered = http_json(server.base_url, "/api/blocks/save_file/inspector-panel", method="POST", payload={"node": node})
        html = str(rendered.get("html") or "")
        expect("data-save-file-inspector-root" in html, "Le HTML inspecteur save_file doit venir du bloc.")
        expect("data-save-file-path" in html, "Le panneau save_file doit contenir le champ chemin.")
        expect("data-path-browser" in html, "Le panneau save_file doit utiliser le path browser commun.")
        expect('value="exports/resultat.txt"' in html, "Le panneau save_file doit lire node.config.path en priorité.")
        expect("data-save-file-append" in html, "Le panneau save_file doit contenir l'option append.")
        expect("data-block-apply" in html, "Le panneau save_file doit exposer le bouton Appliquer.")
        expect("data-save-file-show-done-output" in html, "Le panneau save_file doit proposer la sortie Done optionnelle.")
        assets = rendered.get("assets") or []
        expect({"kind": "css", "path": "assets/css/inspector_panel.css"} in assets, "CSS save_file manquant.")
        expect({"kind": "js", "path": "assets/js/common.js"} in assets, "JS commun save_file manquant.")
        expect({"kind": "js", "path": "assets/js/inspector_panel.js"} in assets, "JS save_file manquant.")

        for asset_path in ("assets/css/inspector_panel.css", "assets/js/common.js", "assets/js/inspector_panel.js"):
            with urlopen(f"{server.base_url}/api/blocks/save_file/assets/{asset_path}", timeout=5) as response:
                body = response.read().decode("utf-8")
            expect("save" in body.lower(), f"Asset inspecteur save_file non servi: {asset_path}")

        modal = http_json(server.base_url, "/api/blocks/save_file/modal", method="POST", payload={"node": node, "runtime": {}})
        modal_html = str(modal.get("html") or "")
        expect("data-save-file-modal-root" in modal_html, "Le modal save_file doit venir du bloc.")
        expect("data-block-runtime-refresh=\"autonomous\"" in modal_html, "Le modal save_file doit gérer son refresh runtime.")
        expect("data-save-file-path" in modal_html, "Le modal save_file doit contenir le champ chemin.")
        expect("data-path-browser" in modal_html, "Le modal save_file doit utiliser le path browser commun.")
        expect("data-save-file-apply" in modal_html, "Le modal save_file doit exposer l'action fichier.")
        expect("exports/resultat.txt" in modal_html, "Le modal save_file doit lire node.config.path.")
        modal_assets = modal.get("assets") or []
        expect({"kind": "css", "path": "assets/css/inspector_panel.css"} in modal_assets, "CSS modal save_file manquant.")
        expect({"kind": "js", "path": "assets/js/common.js"} in modal_assets, "JS commun modal save_file manquant.")
        expect({"kind": "js", "path": "assets/js/block_modal.js"} in modal_assets, "JS modal save_file manquant.")
        expect({"kind": "js", "path": "assets/js/inspector_panel.js"} not in modal_assets, "Le modal save_file ne doit pas charger le JS inspecteur.")

        target = server.root_dir / "exports" / "resultat.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("resultat", encoding="utf-8")
        browser = http_json(server.base_url, f"/api/blocks/save_file/browse-files?path={quote('exports/resultat.txt')}")
        expect(
            any(entry.get("name") == "resultat.txt" for entry in (browser.get("entries") or [])),
            "Le navigateur fichier save_file doit etre servi par /api/blocks/save_file/browse-files.",
        )

        applied = http_json(
            server.base_url,
            "/api/blocks/save_file/ui-action",
            method="POST",
            payload={
                "node": node,
                "action": "inspector_update_save_file",
                "values": {"path": "exports/updated.txt", "append": False},
            },
        )
        expect(
            applied.get("node_patch", {}).get("config")
            == {"path": "exports/updated.txt", "append": False, "mode": "overwrite"},
            "Patch save_file invalide.",
        )
        expect(applied.get("rerender_inspector") is False, "La saisie save_file ne doit pas forcer un rerender.")

        modal_applied = http_json(
            server.base_url,
            "/api/blocks/save_file/ui-action",
            method="POST",
            payload={
                "node": node,
                "action": "modal_update_save_file",
                "values": {"path": "exports/modal.txt", "append": True},
            },
        )
        expect(
            modal_applied.get("node_patch", {}).get("config")
            == {"path": "exports/modal.txt", "append": True, "mode": "append"},
            "Patch modal save_file invalide.",
        )

        done_result = http_json(
            server.base_url,
            "/api/blocks/save_file/ui-action",
            method="POST",
            payload={
                "node": node,
                "action": "save_file_show_done_output",
                "values": {},
            },
        )
        done_operations = done_result.get("graph_operations") or []
        expect(len(done_operations) == 1, "L'action Done doit retourner une operation graphe.")
        expect(done_operations[0].get("op") == "create_port", "Done doit materialiser un port via create_port.")
        expect(done_operations[0].get("name") == "done", "Le port Done doit avoir le nom done.")
        expect("control/trigger" in (done_operations[0].get("emits") or []), "Done doit emettre control/trigger.")

        converted = block_ui_result_to_graph_operations(
            node_id="save-file-1",
            node_kind="save_file",
            result=done_result,
            op_id_prefix="test_done",
        )
        expect(converted[0].get("op_id") == "test_done:1", "Les graph_operations directes doivent recevoir un op_id.")
    print("[ok] F8.12_save_file_block_inspector_panel_api")


if __name__ == "__main__":
    main()
