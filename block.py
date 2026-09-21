# -----------------------------------------------------------------------------
# Role: Implements the save file block runtime and UI contract.
# File Name: block.py
# Author: Alexandre EL
# Email: alex@hackinvent.com
# Created Date: 2024-01-29
# -----------------------------------------------------------------------------

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
import json
import threading

from bloxsmith_app.block_api import (
    BlockDefinition,
    BlockRuntimeContext,
    BlockRuntimeOutput,
    BlockRuntimeResult,
    CONTROL_TRIGGER,
    render_inspector_template,
    render_node_card_template,
    render_path_browser_control,
)


# Functional behavior:
# FB1 - Write incoming content to a configured or input-provided workspace file during runtime execution.
# FB2 - Support overwrite and append modes, including append headers.
# FB3 - Serialize concurrent writes to the same target path.
# FB4 - Emit optional Done operational output only after a successful write.
# FB5 - Convert path, permission, and write failures into explicit SaveFileBlockError errors.
class SaveFileBlockError(ValueError):
    """Raised when a save_file block cannot write safely."""


class _FileWriteQueue:
    """Structured data used by this block implementation."""
    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._next_ticket = 0
        self._serving_ticket = 0

    def reserve(self) -> tuple[int, int]:
        """Provide internal _FileWriteQueue behavior for `reserve`."""
        with self._condition:
            ticket = self._next_ticket
            self._next_ticket += 1
            queued_before = ticket - self._serving_ticket
            return ticket, queued_before

    def wait_for_turn(self, ticket: int) -> None:
        """Provide internal _FileWriteQueue behavior for `wait_for_turn`.

        Args:
            ticket: Ticket value used by this block helper.
        """
        with self._condition:
            while ticket != self._serving_ticket:
                self._condition.wait()

    def leave(self) -> None:
        """Provide internal _FileWriteQueue behavior for `leave`."""
        with self._condition:
            self._serving_ticket += 1
            self._condition.notify_all()

    def is_idle(self) -> bool:
        """Provide internal _FileWriteQueue behavior for `is_idle`."""
        with self._condition:
            return self._serving_ticket == self._next_ticket


_WRITE_QUEUES_LOCK = threading.Lock()
_WRITE_QUEUES: dict[Path, _FileWriteQueue] = {}


def _reserve_file_write_queue(target_path: Path) -> tuple[_FileWriteQueue, int, int]:
    """Provide internal block behavior for `_reserve_file_write_queue`.

    Args:
        target_path: Filesystem path handled by the block.
    """
    with _WRITE_QUEUES_LOCK:
        queue = _WRITE_QUEUES.get(target_path)
        if queue is None:
            queue = _FileWriteQueue()
            _WRITE_QUEUES[target_path] = queue
        ticket, queued_before = queue.reserve()
        return queue, ticket, queued_before


def _discard_file_write_queue_if_idle(target_path: Path, queue: _FileWriteQueue) -> None:
    """Provide internal block behavior for `_discard_file_write_queue_if_idle`.

    Args:
        target_path: Filesystem path handled by the block.
        queue: Queue value used by this block helper.
    """
    with _WRITE_QUEUES_LOCK:
        if _WRITE_QUEUES.get(target_path) is queue and queue.is_idle():
            del _WRITE_QUEUES[target_path]


class SaveFileBlock(BlockDefinition):
    """Autonomous block implementation for `SaveFileBlock`."""
    kind = "save_file"

    def render_node_card(self, *, node: dict[str, Any], payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Render the Save File canvas card body from the block-owned template."""

        config = self._ui_save_file_config(node)
        return render_node_card_template(
            block=self,
            node=node,
            node_classes=["save-file-node"],
            replacements={
                "title": node.get("title") or self.default_title(),
                "path": config.get("path") or "exports/resultat.txt",
                # The card states one of two modes, so the marker carries the matching key.
                "mode": self.translate(
                    "block.save_file.mode_append" if config.get("append") else "block.save_file.mode_overwrite",
                    fallback="append" if config.get("append") else "overwrite",
                ),
                "mode_key": ("block.save_file.mode_append" if config.get("append")
                             else "block.save_file.mode_overwrite"),
            },
        )

    def render_modal(self, *, node: dict[str, Any], payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Render the Save File modal with the same path browser as the inspector."""

        config = self._ui_save_file_config(node)
        has_done_output = self._has_done_output(node)
        template = (self.directory / "block_modal.html").read_text(encoding="utf-8")
        html = self._render_generic_modal_template(
            template=(
                template
                .replace("{{ path_browser_html }}", self._render_save_file_path_browser(config, input_id="save_file_modal_path_input"))
                .replace("{{ checked }}", "checked" if config.get("append") else "")
                .replace("{{ done_output_action_hidden }}", "hidden" if has_done_output else "")
                .replace("{{ config_fields_html }}", self._render_modal_technical_config_fields(node))
            ),
            node=node,
            payload=payload or {},
        )
        return {
            "html": html,
            "context": {
                "node_id": str(node.get("id") or ""),
                "node_kind": self.kind,
                **config,
            },
        }

    def render_inspector_panel(self, *, node: dict[str, Any], payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Render the block-owned inspector panel HTML for the selected node.

        Args:
            node: Serialized graph node handled by the block.
            payload: Optional UI or runtime payload provided by the framework.
        """
        config = self._ui_save_file_config(node)
        has_done_output = self._has_done_output(node)
        template = (self.directory / "inspector_panel.html").read_text(encoding="utf-8")
        html = render_inspector_template(
            template=(
                template
                .replace("{{ path_browser_html }}", self._render_save_file_path_browser(config, input_id="save_file_inspector_path_input"))
                .replace("{{ checked }}", "checked" if config.get("append") else "")
                .replace("{{ done_output_action_hidden }}", "hidden" if has_done_output else "")
            ),
            node={**node, "type": self.kind, "kind": self.kind},
            payload=payload,
            show_duplicate=False,
        )
        return {"html": html, "context": {"node_id": str(node.get("id") or ""), **config, "full_panel": True}}

    def handle_ui_action(
        self,
        *,
        node: dict[str, Any],
        action: str,
        values: dict[str, Any],
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Handle a block-owned UI action and return the updated node payload.

        Args:
            node: Serialized graph node handled by the block.
            action: Block-owned action name requested by the frontend.
            values: Values value used by this block helper.
            payload: Optional UI or runtime payload provided by the framework.
        """
        if action in {"inspector_update_save_file", "modal_update_save_file"}:
            return self._apply_save_file_ui_update(values)
        if action == "save_file_show_done_output":
            return self._show_done_output_action(node)
        return super().handle_ui_action(node=node, action=action, values=values, payload=payload)

    def _apply_save_file_ui_update(self, values: dict[str, Any]) -> dict[str, Any]:
        """Return a node patch for Save File path and append-mode UI edits."""

        append = bool(values.get("append"))
        return {
            "node_patch": {
                "config": {
                    "path": str(values.get("path") or ""),
                    "append": append,
                    "mode": "append" if append else "overwrite",
                },
            },
            "rerender_inspector": False,
        }

    def _render_save_file_path_browser(self, config: dict[str, Any], *, input_id: str) -> str:
        """Render the shared file selector configured for Save File targets."""

        return render_path_browser_control(
            input_id=input_id,
            label="File path",
            value=str(config.get("path") or ""),
            placeholder="./exports/resultat.txt ou /home/toto/resultat.txt",
            input_attrs="data-save-file-path",
            select_mode="file",
        )

    def _render_modal_technical_config_fields(self, node: dict[str, Any]) -> str:
        """Render Save File config keys not owned by the dedicated file controls."""

        config = self.default_config()
        node_config = node.get("config")
        if isinstance(node_config, dict):
            config.update(node_config)
        hidden_keys = {"path", "target_path", "file", "append", "mode"}
        fields = [
            self._render_generic_modal_config_field(key, value)
            for key, value in config.items()
            if str(key) not in hidden_keys
        ]
        return "\n".join(fields) if fields else '<div class="ports-editor-empty">No technical attribute.</div>'

    def _show_done_output_action(self, node: dict[str, Any]) -> dict[str, Any]:
        """Return the graph operation that materializes the optional Done output port."""
        node_id = str(node.get("id") or "").strip()
        if not node_id:
            return {"error": "missing_node_id"}
        if self._has_done_output(node):
            return {"message": "[save-file] Done output already present.", "rerender_inspector": False}
        port_id = self._next_output_port_id(node)
        return {
            "graph_operations": [
                {
                    "op": "create_port",
                    "node_id": node_id,
                    "direction": "output",
                    "port_id": port_id,
                    "name": "done",
                    "title": "Done",
                    "emits": [CONTROL_TRIGGER, "message/*"],
                    "multiplicity": "many",
                }
            ],
            "message": "[save-file] Done output added.",
            "rerender_inspector": True,
        }

    def _ui_save_file_config(self, node: dict[str, Any]) -> dict[str, Any]:
        """Return UI-facing save_file config from canonical ``node.config`` fields.

        Args:
            node: Serialized save_file node.

        Returns:
            Normalized path and append state for inspector and canvas rendering.
        """

        raw = node.get("config") if isinstance(node.get("config"), dict) else {}
        append = raw.get("append")
        if append is None:
            append = self._normalize_mode(raw.get("mode")) == "append"
        return {
            "path": str(raw.get("path") or "exports/resultat.txt"),
            "append": bool(append),
        }

    def build_runtime_config(self, *, node: Any, config: dict[str, Any], **runtime_services: Any) -> dict[str, Any]:
        """Build the normalized runtime configuration for this block.

        Args:
            node: Serialized graph node handled by the block.
            config: Raw or normalized block configuration.
            runtime_services: Runtime services value used by this block helper.
        """
        runtime_config = dict(config)
        runtime_config.setdefault("project_title", str(runtime_services.get("project_title") or "Workflow IA"))
        runtime_config.setdefault("block_path", self._runtime_block_path(node))
        return runtime_config

    def execute(self, *, root_dir: Path, config: dict[str, Any], content: str) -> dict[str, Any]:
        """Execute the block business logic with normalized inputs and configuration.

        Args:
            root_dir: Directory path used by the block runtime.
            config: Raw or normalized block configuration.
            content: Content value used by this block helper.
        """
        target_path = self._resolve_target_path(root_dir=root_dir, config=config)
        encoding = str(config.get("encoding") or "utf-8").strip() or "utf-8"
        mode = self._resolve_mode(config)

        target_path.parent.mkdir(parents=True, exist_ok=True)

        write_mode = {
            "overwrite": "w",
            "append": "a",
        }[mode]

        write_queue, ticket, queued_before = _reserve_file_write_queue(target_path)
        write_queue.wait_for_turn(ticket)
        try:
            output_content = self._format_output_content(
                target_path=target_path,
                mode=mode,
                config=config,
                content=content,
            )
            with target_path.open(write_mode, encoding=encoding) as file:
                file.write(output_content)
            stat = target_path.stat()
        except FileExistsError as exc:
            raise SaveFileBlockError(f"File already exists: {target_path}") from exc
        except PermissionError as exc:
            raise SaveFileBlockError(f"Permission refusee: {target_path}") from exc
        except OSError as exc:
            raise SaveFileBlockError(self.translate("block.save_file.error_write", {"error": str(exc)},
                fallback=f"Write failed: {exc}")) from exc
        finally:
            write_queue.leave()
            _discard_file_write_queue_if_idle(target_path, write_queue)

        display_path = self._display_path(target_path=target_path, root_dir=root_dir)
        return {
            "path": display_path,
            "absolute_path": str(target_path),
            "bytes": stat.st_size,
            "mode": mode,
            "encoding": encoding,
            "queue_ticket": ticket,
            "queued_before": queued_before,
            "status": "success",
        }

    def _resolve_target_path(self, *, root_dir: Path, config: dict[str, Any]) -> Path:
        """Resolve a configured value against runtime or project context.

        Args:
            root_dir: Directory path used by the block runtime.
            config: Raw or normalized block configuration.
        """
        root = root_dir.resolve()
        raw_path = str(config.get("path") or "").strip()

        if raw_path:
            path = Path(raw_path).expanduser()
        else:
            folder = str(config.get("folder") or "exports").strip() or "exports"
            filename = str(config.get("filename") or "resultat.txt").strip() or "resultat.txt"
            path = Path(folder).expanduser() / filename

        if not str(path).strip() or path.name in {"", ".", ".."}:
            raise SaveFileBlockError("The target path must designate a file.")

        if path.is_absolute():
            return path.resolve()
        return (root / path).resolve()

    def _display_path(self, *, target_path: Path, root_dir: Path) -> str:
        """Provide internal SaveFileBlock behavior for `_display_path`.

        Args:
            target_path: Filesystem path handled by the block.
            root_dir: Directory path used by the block runtime.
        """
        try:
            return str(target_path.relative_to(root_dir.resolve()))
        except ValueError:
            return str(target_path)

    def _resolve_mode(self, config: dict[str, Any]) -> str:
        """Resolve a configured value against runtime or project context.

        Args:
            config: Raw or normalized block configuration.
        """
        if "append" in config:
            return "append" if bool(config.get("append")) else "overwrite"
        return self._normalize_mode(config.get("mode"))

    def _normalize_mode(self, raw_mode: Any) -> str:
        """Normalize a raw value into the format expected by the block.

        Args:
            raw_mode: Raw value received from configuration or runtime input.
        """
        mode = str(raw_mode or "overwrite").strip().lower()
        if mode not in {"overwrite", "append"}:
            return "overwrite"
        return mode

    def _format_output_content(
        self,
        *,
        target_path: Path,
        mode: str,
        config: dict[str, Any],
        content: str,
    ) -> str:
        """Format a value for logs, UI display, or runtime output.

        Args:
            target_path: Filesystem path handled by the block.
            mode: Mode value used by this block helper.
            config: Raw or normalized block configuration.
            content: Content value used by this block helper.
        """
        content_text = str(content or "")
        if mode != "append":
            return content_text

        project = self._normalize_header_field(config.get("project_title") or config.get("project") or "Workflow IA")
        block_path = self._normalize_header_field(config.get("block_path") or config.get("node_path") or "save_file")
        timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        separator = f"-------------------- {project} {block_path} {timestamp}"
        leading_newline = "\n" if self._needs_leading_newline(target_path) else ""
        trailing_newline = "" if content_text.endswith("\n") else "\n"
        return f"{leading_newline}{separator}\n{content_text}{trailing_newline}"

    def _needs_leading_newline(self, target_path: Path) -> bool:
        """Provide internal SaveFileBlock behavior for `_needs_leading_newline`.

        Args:
            target_path: Filesystem path handled by the block.
        """
        if not target_path.exists() or target_path.stat().st_size == 0:
            return False
        try:
            with target_path.open("rb") as file:
                file.seek(-1, 2)
                return file.read(1) != b"\n"
        except OSError:
            return False

    def _normalize_header_field(self, value: Any) -> str:
        """Normalize a raw value into the format expected by the block.

        Args:
            value: Value to normalize, render, serialize, or process.
        """
        return " ".join(str(value or "").split()) or "-"

    def _runtime_block_path(self, node: Any) -> str:
        """Provide internal SaveFileBlock behavior for `_runtime_block_path`.

        Args:
            node: Serialized graph node handled by the block.
        """
        config = getattr(node, "config", {}) if isinstance(getattr(node, "config", {}), dict) else {}
        raw_path = config.get("runtime_path") or config.get("_runtime_path")
        if isinstance(raw_path, list):
            parts = [
                str(item.get("title") if isinstance(item, dict) else item or "").strip()
                for item in raw_path
            ]
            parts = [part for part in parts if part]
            if parts:
                return " > ".join(parts)

        raw_label = str(config.get("block_path") or config.get("runtime_path_label") or "").strip()
        if raw_label:
            return raw_label

        node_title = str(getattr(node, "title", "") or "").strip()
        node_id = str(getattr(node, "id", "") or "").strip()
        if "__" not in node_id:
            return node_title or node_id or "save_file"

        parts = [part for part in node_id.split("__") if part]
        if node_title:
            parts[-1:] = [node_title]
        return " > ".join(parts) or node_title or node_id or "save_file"

    def execute_runtime(self, context: BlockRuntimeContext) -> BlockRuntimeResult:
        """Execute the block through the generic runtime context and return runtime outputs.

        Args:
            context: Generic runtime context injected by the execution engine.
        """
        runtime_config = dict(context.config)
        path_override = self._runtime_path_override(context)
        if path_override:
            runtime_config["path"] = path_override
        metadata = self.execute(
            root_dir=context.root_dir,
            config=runtime_config,
            content=self._runtime_content(context),
        )
        last_message = {
            "path": metadata.get("path", ""),
            "absolute_path": metadata.get("absolute_path", ""),
            "bytes": metadata.get("bytes", 0),
            "mode": metadata.get("mode", ""),
            "encoding": metadata.get("encoding", ""),
            "status": metadata.get("status", "success"),
        }
        logs = []
        queued_before = int(metadata.get("queued_before") or 0)
        if queued_before:
            logs.append(
                f"[save-queue] {context.node_id} waited for {queued_before} write(s) on {metadata.get('path')}."
            )
        logs.append(f"[done] {context.node_id} file written: {metadata.get('path')} ({metadata.get('bytes')} bytes).")

        return BlockRuntimeResult(
            status="success",
            outputs=self._runtime_done_outputs(context),
            logs=logs,
            last_message=json.dumps(last_message, ensure_ascii=False, indent=2),
            worker_received=str(metadata.get("path") or "-"),
            metadata={"saved_file": metadata.get("path", ""), "bytes": metadata.get("bytes", 0)},
        )

    def _runtime_done_outputs(self, context: BlockRuntimeContext) -> list[BlockRuntimeOutput]:
        """Emit Done only for materialized Done/control ports after the write has completed."""
        outputs: list[BlockRuntimeOutput] = []
        for port in context.output_ports:
            if not self._is_done_output_port(port):
                continue
            outputs.append(
                BlockRuntimeOutput(
                    port_id=int(getattr(port, "id", 0) or 0),
                    port_name=str(getattr(port, "name", "") or "done"),
                    value="true",
                    content_type=CONTROL_TRIGGER,
                )
            )
        return outputs

    def _is_done_output_port(self, port: Any) -> bool:
        """Return whether the provided value matches this block condition.

        Args:
            port: Serialized or runtime port definition.
        """
        name = str(getattr(port, "name", "") if not isinstance(port, dict) else port.get("name") or "").strip().lower()
        emits = getattr(port, "emits", None) if not isinstance(port, dict) else port.get("emits")
        emits_values = [str(item or "").strip() for item in (emits or ()) if str(item or "").strip()]
        return name == "done" or CONTROL_TRIGGER in emits_values

    def _has_done_output(self, node: dict[str, Any]) -> bool:
        """Return whether the node contains the requested block element.

        Args:
            node: Serialized graph node handled by the block.
        """
        return any(self._is_done_output_port(port) for port in node.get("outputs") or [])

    def _next_output_port_id(self, node: dict[str, Any]) -> int:
        """Compute the next identifier or path used by this block.

        Args:
            node: Serialized graph node handled by the block.
        """
        ids = []
        for port in node.get("outputs") or []:
            try:
                ids.append(int(port.get("id") or 0))
            except (TypeError, ValueError):
                continue
        return max(ids or [0]) + 1

    def _runtime_content(self, context: BlockRuntimeContext) -> str:
        """Return the payload to write from the canonical content input."""

        for key in ("contenu", "content", "in", "1"):
            value = context.input_value(key)
            if value not in (None, ""):
                return str(value or "")
        return ""

    def _runtime_path_override(self, context: BlockRuntimeContext) -> str:
        """Return the optional runtime target path supplied on the dedicated path input."""
        raw_value = context.input_value("path", "2")
        return self._normalize_runtime_path_value(raw_value)

    def _normalize_runtime_path_value(self, raw_value: Any) -> str:
        """Normalize a plain or JSON-wrapped path value received from upstream blocks."""
        text = str(raw_value or "").strip()
        if not text:
            return ""
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError):
            return text
        if isinstance(parsed, str):
            return parsed.strip()
        if isinstance(parsed, dict):
            candidates: list[dict[str, Any]] = [parsed]
            item = parsed.get("item")
            if isinstance(item, dict):
                candidates.append(item)
            for candidate in candidates:
                for key in ("path", "absolute_path"):
                    value = str(candidate.get(key) or "").strip()
                    if value:
                        return value
        return text
