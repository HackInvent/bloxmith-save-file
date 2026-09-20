#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# Role: Verifies save file block behavior for the save file block.
# File Name: F5.06_save_file_block.py
# Author: Alexandre EL
# Email: alex@hackinvent.com
# Created Date: 2024-03-06
# -----------------------------------------------------------------------------

"""F5.06 - Bloc save_file en écriture contrôlée.

Le test lance `text -> save_file` dans un projet temporaire et vérifie que le
fichier cible relatif au projet est créé avec le contenu exact attendu. Il
vérifie aussi que l'input `path` écrase le chemin configuré.
"""

# Test cases:
# - FB1/FB4 - Run text -> save_file and verify the file is written inside the isolated project workspace with saved metadata.
# - FB1 - Run text -> save_file with a connected path input in centralized and active runtime, verify the input path overrides config.path.
# - FB4 - Materialized Done output emits true only after successful write in centralized and active runtime.
# - FB2 - Execute SaveFile in append mode and verify append headers and appended content are written.
# - FB3 - Execute concurrent writes to the same target and verify the serialized queue keeps all payloads.
# - FB1/FB5 - Verify controlled path handling and saved content match the incoming value.

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory

from ui_smoke_common import (
    create_run_api,
    data_edge,
    display_node,
    expect,
    feedback_edge,
    graph_payload,
    isolated_server,
    text_node,
    wait_for_run_terminal,
)

from blocs.save_file.block import SaveFileBlock


def save_file_node() -> dict:
    return {
        "id": "save-file-1",
        "kind": "save_file",
        "title": "Save file test",
        "position": {"x": 360, "y": 120},
        "inputs": [
            {"id": 1, "name": "contenu", "title": "In", "accepts": ["message/*"], "multiplicity": "many"},
            {
                "id": 2,
                "name": "path",
                "title": "Path",
                "accepts": ["file/path", "text/plain", "message/*", "application/json"],
                "multiplicity": "one",
            },
        ],
        "outputs": [],
        "config": {
            "path": "tmp_test_outputs/f5/save_file_result.txt",
            "mode": "overwrite",
            "append": False,
            "encoding": "utf-8",
        },
    }


def save_file_node_with_done_output() -> dict:
    node = save_file_node()
    node["outputs"] = [
        {
            "id": 1,
            "name": "done",
            "title": "Done",
            "emits": ["control/trigger", "message/*"],
            "multiplicity": "many",
        }
    ]
    return node


def output_value_by_content_type(run: dict, content_type: str) -> dict:
    """Return the first output value matching a content type after id materialization."""

    for value in (run.get("output_values") or {}).values():
        if value.get("content_type") == content_type:
            return value
    return {}


def worker_received_by_title(run: dict, title: str) -> str:
    """Return received worker text by runtime node title after id materialization."""

    for row in (run.get("worker_rows") or {}).values():
        if str(row.get("node_title") or "") == title:
            return str(row.get("received") or "")
    return ""


def list_node_for_done_feedback() -> dict:
    return {
        "id": "list-1",
        "kind": "list",
        "title": "Liste chemins",
        "position": {"x": 80, "y": 120},
        "inputs": [],
        "outputs": [
            {
                "id": 1,
                "name": "liste",
                "title": "Liste",
                "emits": ["application/json", "message/*"],
                "multiplicity": "many",
            }
        ],
        "config": {
            "items": [
                {"path": "tmp_test_outputs/f5/loop_1.txt", "content": "content-1"},
                {"path": "tmp_test_outputs/f5/loop_2.txt", "content": "content-2"},
                {"path": "tmp_test_outputs/f5/loop_3.txt", "content": "content-3"},
            ]
        },
    }


def iterator_node_for_done_feedback() -> dict:
    return {
        "id": "iterator-1",
        "kind": "iterator",
        "title": "Iterator Save Done",
        "position": {"x": 360, "y": 140},
        "inputs": [
            {"id": 1, "name": "liste", "title": "Liste", "accepts": ["application/json", "message/*"], "multiplicity": "many"},
            {"id": 2, "name": "trigger", "title": "Trigger", "accepts": ["control/trigger", "message/*"], "multiplicity": "many"},
        ],
        "outputs": [
            {"id": 1, "name": "item", "title": "Item", "emits": ["message/*"], "multiplicity": "many"},
            {"id": 2, "name": "index", "title": "Index", "emits": ["message/*"], "multiplicity": "many"},
            {"id": 3, "name": "done", "title": "Done", "emits": ["message/*"], "multiplicity": "many"},
            {"id": 4, "name": "next", "title": "Next", "emits": ["control/trigger", "message/*"], "multiplicity": "many"},
        ],
        "config": {},
    }


def python_extract_node(node_id: str, title: str, field: str, *, delay_sec: float, x: int, y: int) -> dict:
    script = (
        "def run(inputs, outputs, params):\n"
        "    import json\n"
        "    import time\n"
        f"    time.sleep({delay_sec!r})\n"
        "    data = json.loads(str(inputs.get('in') or '{}'))\n"
        "    item = data.get('item', data)\n"
        f"    outputs['out'] = str(item.get({field!r}) or '')\n"
    )
    return {
        "id": node_id,
        "kind": "python",
        "title": title,
        "position": {"x": x, "y": y},
        "inputs": [{"id": 1, "name": "in", "title": "In", "accepts": ["message/*"], "multiplicity": "many"}],
        "outputs": [{"id": 1, "name": "out", "title": "Out", "emits": ["message/*"], "multiplicity": "many"}],
        "config": {
            "script": script,
            "timeout_sec": 10,
            "python_executable": "python3",
            "params": [],
            "dynamic_code_enabled": False,
            "code_input_port_id": None,
            "code_output_port_id": None,
        },
    }


def _verify_append_and_write_queue() -> None:
    block = SaveFileBlock()
    with TemporaryDirectory(prefix="bloxsmith-save-file-fb-") as tmp:
        root = Path(tmp)
        target = root / "exports" / "append.txt"
        first = block.execute(root_dir=root, config={"path": "exports/append.txt", "mode": "overwrite"}, content="first")
        second = block.execute(root_dir=root, config={"path": "exports/append.txt", "mode": "append", "project_title": "Proj", "block_path": "Save"}, content="second")
        text = target.read_text(encoding="utf-8")
        expect(first.get("mode") == "overwrite" and second.get("mode") == "append", "SaveFile must expose the effective mode.")
        expect("first" in text and "second" in text and "Proj Save" in text, "Append must keep the previous content and add the header.")

        queue_target = root / "exports" / "queue.txt"
        def write_payload(index: int) -> dict:
            return block.execute(
                root_dir=root,
                config={"path": "exports/queue.txt", "mode": "append", "project_title": "Queue", "block_path": f"B{index}"},
                content=f"payload-{index}",
            )

        with ThreadPoolExecutor(max_workers=3) as executor:
            results = list(executor.map(write_payload, range(3)))
        queued_text = queue_target.read_text(encoding="utf-8")
        expect(all(result.get("status") == "success" for result in results), "Every concurrent write must succeed.")
        expect(all(f"payload-{index}" in queued_text for index in range(3)), "The write queue must preserve every payload.")


def _verify_runtime_path_override(runtime_mode: str) -> None:
    with isolated_server() as server:
        configured_path = f"tmp_test_outputs/f5/configured_should_not_exist_{runtime_mode}.txt"
        override_path = f"tmp_test_outputs/f5/input_override_{runtime_mode}.txt"
        node = save_file_node()
        node["config"]["path"] = configured_path
        document = graph_payload(
            f"F5 Save File path input {runtime_mode}",
            [
                text_node("text-content", "Texte sauvegarde", f"contenu override {runtime_mode}", 80, 120),
                text_node("text-path", "Chemin dynamique", override_path, 80, 280),
                node,
            ],
            [
                data_edge("edge-content-save", "text-content", 1, "save-file-1", 1),
                data_edge("edge-path-save", "text-path", 1, "save-file-1", 2),
            ],
        )
        created = create_run_api(server, document, runtime_mode=runtime_mode)
        run = wait_for_run_terminal(server, str(created.get("run_id") or ""), timeout_sec=25)
        expect(run.get("status") == "success", f"The save_file {runtime_mode} run with a path input must succeed.")
        target = server.root_dir / override_path
        configured_target = server.root_dir / configured_path
        expect(target.is_file(), "The target file given by the path input was not created.")
        expect(
            target.read_text(encoding="utf-8") == f"contenu override {runtime_mode}",
            "The saved content must come from the content input only, not from the path input.",
        )
        expect(not configured_target.exists(), "The configured path must not be used when the path input is provided.")
        expect(
            any(result.get("saved_file") == override_path for result in (run.get("results") or {}).values()),
            "The save_file result must reference the path given by the path input.",
        )


def _verify_done_output(runtime_mode: str) -> None:
    with isolated_server() as server:
        target_path = f"tmp_test_outputs/f5/done_{runtime_mode}.txt"
        node = save_file_node_with_done_output()
        node["config"]["path"] = target_path
        document = graph_payload(
            f"F5 Save File done {runtime_mode}",
            [
                text_node("text-1", "Texte sauvegarde", f"done content {runtime_mode}", 80, 120),
                node,
                display_node("display-done", "Done display", 720, 120),
            ],
            [
                data_edge("edge-text-save", "text-1", 1, "save-file-1", 1),
                data_edge("edge-save-done-display", "save-file-1", 1, "display-done", 1),
            ],
        )
        created = create_run_api(server, document, runtime_mode=runtime_mode)
        run = wait_for_run_terminal(server, str(created.get("run_id") or ""), timeout_sec=25)
        expect(run.get("status") == "success", f"The save_file Done {runtime_mode} run must succeed.")
        expect((server.root_dir / target_path).read_text(encoding="utf-8") == f"done content {runtime_mode}", "The file must be written before Done.")
        done_output = output_value_by_content_type(run, "control/trigger")
        expect(done_output.get("value") == "true", "The Done output must emit true.")
        expect(done_output.get("content_type") == "control/trigger", "The Done output must emit control/trigger.")
        expect("true" in worker_received_by_title(run, "Done display"), "The subscriber must receive Done.")


def _verify_done_feedback_transport_loop(runtime_mode: str) -> None:
    with isolated_server() as server:
        save_node = save_file_node_with_done_output()
        save_node["position"] = {"x": 980, "y": 180}
        save_node["config"]["path"] = "tmp_test_outputs/f5/stale_default_should_not_exist.txt"
        document = graph_payload(
            f"F5 Save Done feedback transport {runtime_mode}",
            [
                list_node_for_done_feedback(),
                iterator_node_for_done_feedback(),
                python_extract_node("python-content", "Content slow", "content", delay_sec=0.35, x=620, y=80),
                python_extract_node("python-path", "Path fast", "path", delay_sec=0.0, x=620, y=280),
                save_node,
            ],
            [
                data_edge("edge-list-iterator", "list-1", 1, "iterator-1", 1),
                data_edge("edge-iterator-content", "iterator-1", 1, "python-content", 1),
                data_edge("edge-iterator-path", "iterator-1", 1, "python-path", 1),
                data_edge("edge-content-save", "python-content", 1, "save-file-1", 1),
                data_edge("edge-path-save", "python-path", 1, "save-file-1", 2),
                feedback_edge("edge-save-done-iterator", "save-file-1", 1, "iterator-1", 2),
            ],
        )
        created = create_run_api(server, document, runtime_mode=runtime_mode)
        run = wait_for_run_terminal(server, str(created.get("run_id") or ""), timeout_sec=30)
        logs = "\n".join(str(line) for line in run.get("logs", []))
        expect(run.get("status") == "success", f"Le feedback save_file -> iterator {runtime_mode} doit transporter Done et boucler proprement.\n{logs}")
        expect("feedback_iterations" not in run, "Le run ne doit plus exposer de compteur feedback.")
        expect("python-error" not in logs, "La boucle feedback ne doit pas propager d'item vide.")
        for index in range(1, 4):
            target = server.root_dir / "tmp_test_outputs" / "f5" / f"loop_{index}.txt"
            expect(target.is_file(), f"The feedback loop must create loop_{index}.txt.")
            expect(target.read_text(encoding="utf-8") == f"content-{index}", f"SaveFile must write the fresh content {index}.")
        expect(
            not (server.root_dir / "tmp_test_outputs" / "f5" / "stale_default_should_not_exist.txt").exists(),
            "The default path must not be used.",
        )


def main() -> None:
    _verify_append_and_write_queue()
    _verify_runtime_path_override("centralized")
    _verify_runtime_path_override("zeromq_active")
    _verify_done_output("centralized")
    _verify_done_output("zeromq_active")
    _verify_done_feedback_transport_loop("centralized")
    _verify_done_feedback_transport_loop("zeromq_active")
    with isolated_server() as server:
        document = graph_payload(
            "F5 Save File",
            [
                text_node("text-1", "Texte sauvegarde", "saved content F5", 80, 120),
                save_file_node(),
            ],
            [data_edge("edge-text-save", "text-1", 1, "save-file-1", 1)],
        )
        created = create_run_api(server, document)
        run = wait_for_run_terminal(server, str(created.get("run_id") or ""))
        expect(run.get("status") == "success", "The save_file run must succeed.")
        expect("success" in set((run.get("node_statuses") or {}).values()), "The save_file block is not successful.")

        target = server.root_dir / "tmp_test_outputs" / "f5" / "save_file_result.txt"
        expect(target.is_file(), "The save_file target file was not created.")
        expect(target.read_text(encoding="utf-8") == "saved content F5", "The saved file content is wrong.")
        expect(
            any(
                result.get("saved_file") == "tmp_test_outputs/f5/save_file_result.txt"
                for result in (run.get("results") or {}).values()
            ),
            "The save_file result does not reference the expected file.",
        )
    print("[ok] F5.06_save_file_block")


if __name__ == "__main__":
    main()
