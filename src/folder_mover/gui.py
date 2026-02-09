"""
Folder Mover Pro - Windows GUI

A Tkinter-based GUI for the folder mover application.
Runs operations in background threads to keep UI responsive.
"""

import logging
import os
import queue
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional, Set

from . import PRODUCT_NAME, PRODUCT_DESCRIPTION, __version__
from .excel import load_case_ids
from .indexer import match_caseids, scan_folders
from .mover import FolderMover
from .report import ReportWriter
from .types import FolderMatch

logger = logging.getLogger(__name__)


class QueueHandler(logging.Handler):
    """Logging handler that puts log records into a queue for GUI consumption."""

    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self.log_queue.put(msg)
        except Exception:
            self.handleError(record)


class FolderMoverGUI:
    """Main GUI application for Folder Mover Pro."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"{PRODUCT_NAME} v{__version__}")
        self.root.geometry("800x700")
        self.root.minsize(700, 600)

        # Queue for log messages from worker thread
        self.log_queue: queue.Queue = queue.Queue()

        # Worker thread reference
        self.worker_thread: Optional[threading.Thread] = None
        self.operation_cancelled = False

        # Variables for form fields
        self.excel_path = tk.StringVar()
        self.source_root = tk.StringVar()
        self.dest_root = tk.StringVar()
        self.report_path = tk.StringVar()
        self.dry_run = tk.BooleanVar(value=True)
        self.max_moves = tk.StringVar(value="0")
        self.matcher = tk.StringVar(value="bucket")
        self.on_dest_exists = tk.StringVar(value="rename")
        self.duplicates_action = tk.StringVar(value="quarantine")

        # Build UI
        self._create_widgets()
        self._setup_logging()

        # Start polling for log messages
        self._poll_log_queue()

        # Bind validation
        self.excel_path.trace_add("write", self._validate_inputs)
        self.source_root.trace_add("write", self._validate_inputs)
        self.dest_root.trace_add("write", self._validate_inputs)

    def _create_widgets(self) -> None:
        """Create all GUI widgets."""
        # Main container with padding
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        # Title
        title_label = ttk.Label(
            main_frame,
            text=f"{PRODUCT_NAME}",
            font=("Segoe UI", 16, "bold")
        )
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 5))

        subtitle_label = ttk.Label(
            main_frame,
            text=PRODUCT_DESCRIPTION,
            font=("Segoe UI", 9)
        )
        subtitle_label.grid(row=1, column=0, columnspan=3, pady=(0, 15))

        # === File Selection Section ===
        file_frame = ttk.LabelFrame(main_frame, text="File Selection", padding="10")
        file_frame.grid(row=2, column=0, columnspan=3, sticky="ew", pady=5)
        file_frame.columnconfigure(1, weight=1)

        # Excel file
        ttk.Label(file_frame, text="Excel File:").grid(row=0, column=0, sticky="w", pady=2)
        ttk.Entry(file_frame, textvariable=self.excel_path, width=60).grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Button(file_frame, text="Browse...", command=self._browse_excel).grid(row=0, column=2)

        # Source root
        ttk.Label(file_frame, text="Source Root:").grid(row=1, column=0, sticky="w", pady=2)
        ttk.Entry(file_frame, textvariable=self.source_root, width=60).grid(row=1, column=1, sticky="ew", padx=5)
        ttk.Button(file_frame, text="Browse...", command=self._browse_source).grid(row=1, column=2)

        # Destination root
        ttk.Label(file_frame, text="Dest Root:").grid(row=2, column=0, sticky="w", pady=2)
        ttk.Entry(file_frame, textvariable=self.dest_root, width=60).grid(row=2, column=1, sticky="ew", padx=5)
        ttk.Button(file_frame, text="Browse...", command=self._browse_dest).grid(row=2, column=2)

        # Report file
        ttk.Label(file_frame, text="Report CSV:").grid(row=3, column=0, sticky="w", pady=2)
        ttk.Entry(file_frame, textvariable=self.report_path, width=60).grid(row=3, column=1, sticky="ew", padx=5)
        ttk.Button(file_frame, text="Browse...", command=self._browse_report).grid(row=3, column=2)

        # === Options Section ===
        options_frame = ttk.LabelFrame(main_frame, text="Options", padding="10")
        options_frame.grid(row=3, column=0, columnspan=3, sticky="ew", pady=5)

        # Row 1: Dry run checkbox and max moves
        ttk.Checkbutton(
            options_frame,
            text="Dry Run (preview only, no actual moves)",
            variable=self.dry_run
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=2)

        ttk.Label(options_frame, text="Max Moves (0=unlimited):").grid(row=0, column=2, sticky="e", padx=(20, 5))
        max_moves_entry = ttk.Entry(options_frame, textvariable=self.max_moves, width=8)
        max_moves_entry.grid(row=0, column=3, sticky="w")

        # Row 2: Matcher and on-dest-exists
        ttk.Label(options_frame, text="Matcher:").grid(row=1, column=0, sticky="w", pady=2)
        matcher_combo = ttk.Combobox(
            options_frame,
            textvariable=self.matcher,
            values=["bucket", "aho"],
            state="readonly",
            width=12
        )
        matcher_combo.grid(row=1, column=1, sticky="w", padx=5)

        ttk.Label(options_frame, text="On Dest Exists:").grid(row=1, column=2, sticky="e", padx=(20, 5))
        dest_exists_combo = ttk.Combobox(
            options_frame,
            textvariable=self.on_dest_exists,
            values=["rename", "skip"],
            state="readonly",
            width=12
        )
        dest_exists_combo.grid(row=1, column=3, sticky="w")

        # Row 3: Duplicates action
        ttk.Label(options_frame, text="Duplicates Action:").grid(row=2, column=0, sticky="w", pady=2)
        dup_combo = ttk.Combobox(
            options_frame,
            textvariable=self.duplicates_action,
            values=["quarantine", "skip", "move-all"],
            state="readonly",
            width=12
        )
        dup_combo.grid(row=2, column=1, sticky="w", padx=5)

        # === Buttons Section ===
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=4, column=0, columnspan=3, pady=15)

        self.preview_btn = ttk.Button(
            button_frame,
            text="Preview (Dry Run)",
            command=self._run_preview,
            width=20
        )
        self.preview_btn.grid(row=0, column=0, padx=5)

        self.run_btn = ttk.Button(
            button_frame,
            text="Run",
            command=self._run_operation,
            width=20
        )
        self.run_btn.grid(row=0, column=1, padx=5)

        # === Log Section ===
        log_frame = ttk.LabelFrame(main_frame, text="Log Output", padding="5")
        log_frame.grid(row=5, column=0, columnspan=3, sticky="nsew", pady=5)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        main_frame.rowconfigure(5, weight=1)

        # Log text area with scrollbar
        self.log_text = tk.Text(log_frame, height=15, wrap="word", state="disabled")
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)

        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        # Clear log button
        ttk.Button(log_frame, text="Clear Log", command=self._clear_log).grid(row=1, column=0, pady=5)

        # === Status bar ===
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief="sunken", anchor="w")
        status_bar.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(5, 0))

        # Initial validation
        self._validate_inputs()

    def _setup_logging(self) -> None:
        """Configure logging to capture to GUI."""
        # Create queue handler
        queue_handler = QueueHandler(self.log_queue)
        queue_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))

        # Add handler to root logger
        root_logger = logging.getLogger()
        root_logger.addHandler(queue_handler)
        root_logger.setLevel(logging.INFO)

        # Also log from folder_mover modules
        for module_name in ["folder_mover", "folder_mover.excel", "folder_mover.indexer",
                           "folder_mover.mover", "folder_mover.report"]:
            logging.getLogger(module_name).setLevel(logging.INFO)

    def _poll_log_queue(self) -> None:
        """Poll the log queue and update the text widget."""
        while True:
            try:
                msg = self.log_queue.get_nowait()
                self._append_log(msg)
            except queue.Empty:
                break

        # Schedule next poll
        self.root.after(100, self._poll_log_queue)

    def _append_log(self, message: str) -> None:
        """Append a message to the log text widget."""
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _clear_log(self) -> None:
        """Clear the log text widget."""
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _browse_excel(self) -> None:
        """Browse for Excel file."""
        path = filedialog.askopenfilename(
            title="Select Excel File",
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")]
        )
        if path:
            self.excel_path.set(path)
            # Auto-set report path if not set
            if not self.report_path.get():
                excel_dir = os.path.dirname(path)
                self.report_path.set(os.path.join(excel_dir, "run_report.csv"))

    def _browse_source(self) -> None:
        """Browse for source folder."""
        path = filedialog.askdirectory(title="Select Source Root Folder")
        if path:
            self.source_root.set(path)

    def _browse_dest(self) -> None:
        """Browse for destination folder."""
        path = filedialog.askdirectory(title="Select Destination Root Folder")
        if path:
            self.dest_root.set(path)

    def _browse_report(self) -> None:
        """Browse for report file."""
        path = filedialog.asksaveasfilename(
            title="Save Report As",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if path:
            self.report_path.set(path)

    def _validate_inputs(self, *args) -> bool:
        """Validate inputs and enable/disable buttons."""
        excel_ok = os.path.isfile(self.excel_path.get()) if self.excel_path.get() else False
        source_ok = os.path.isdir(self.source_root.get()) if self.source_root.get() else False
        dest_ok = os.path.isdir(self.dest_root.get()) if self.dest_root.get() else False

        is_running = self.worker_thread is not None and self.worker_thread.is_alive()
        all_valid = excel_ok and source_ok and dest_ok and not is_running

        state = "normal" if all_valid else "disabled"
        self.preview_btn.configure(state=state)
        self.run_btn.configure(state=state)

        return all_valid

    def _get_max_moves(self) -> Optional[int]:
        """Get max moves value, returning None for 0 or invalid."""
        try:
            val = int(self.max_moves.get())
            return val if val > 0 else None
        except ValueError:
            return None

    def _run_preview(self) -> None:
        """Run in preview/dry-run mode."""
        # Force dry run
        self.dry_run.set(True)
        self._start_operation()

    def _run_operation(self) -> None:
        """Run the actual operation (with confirmation if not dry run)."""
        if not self.dry_run.get():
            # Show confirmation dialog
            dest = self.dest_root.get()
            max_moves = self._get_max_moves()
            max_str = str(max_moves) if max_moves else "unlimited"

            msg = (
                f"You are about to MOVE folders to:\n\n"
                f"  {dest}\n\n"
                f"Max operations: {max_str}\n\n"
                f"This action cannot be easily undone.\n\n"
                f"Are you sure you want to proceed?"
            )

            if not messagebox.askyesno("Confirm Operation", msg, icon="warning"):
                self._append_log("Operation cancelled by user.")
                return

        self._start_operation()

    def _start_operation(self) -> None:
        """Start the operation in a background thread."""
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showwarning("Busy", "An operation is already running.")
            return

        # Disable buttons
        self.preview_btn.configure(state="disabled")
        self.run_btn.configure(state="disabled")
        self.status_var.set("Running...")
        self.operation_cancelled = False

        # Gather parameters
        params = {
            "excel_file": Path(self.excel_path.get()),
            "source_root": Path(self.source_root.get()),
            "dest_root": Path(self.dest_root.get()),
            "report_path": Path(self.report_path.get()) if self.report_path.get() else None,
            "dry_run": self.dry_run.get(),
            "max_moves": self._get_max_moves(),
            "matcher": self.matcher.get(),
            "on_dest_exists": self.on_dest_exists.get(),
            "duplicates_action": self.duplicates_action.get(),
        }

        # Auto-generate report path if not set
        if not params["report_path"]:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            params["report_path"] = Path(os.path.dirname(self.excel_path.get())) / f"report_{timestamp}.csv"
            self.report_path.set(str(params["report_path"]))

        # Start worker thread
        self.worker_thread = threading.Thread(
            target=self._worker_run,
            args=(params,),
            daemon=True
        )
        self.worker_thread.start()

        # Start monitoring thread completion
        self._monitor_worker()

    def _monitor_worker(self) -> None:
        """Monitor worker thread and update UI when complete."""
        if self.worker_thread and self.worker_thread.is_alive():
            self.root.after(200, self._monitor_worker)
        else:
            # Thread completed
            self._validate_inputs()
            self.status_var.set("Ready")

    def _worker_run(self, params: Dict) -> None:
        """Worker function that runs in background thread."""
        try:
            result = self._execute_operation(params)
            # Schedule UI update on main thread
            self.root.after(0, lambda: self._show_completion_dialog(result, params))
        except Exception as e:
            logger.error(f"Operation failed: {e}")
            self.root.after(0, lambda: messagebox.showerror("Error", f"Operation failed:\n\n{e}"))

    def _execute_operation(self, params: Dict) -> Dict:
        """Execute the folder mover operation. Returns result dict."""
        logger.info("=" * 60)
        logger.info(f"{PRODUCT_NAME} v{__version__}")
        logger.info("=" * 60)

        mode_str = "DRY RUN" if params["dry_run"] else "LIVE"
        logger.info(f"Mode: {mode_str}")
        logger.info(f"Excel: {params['excel_file']}")
        logger.info(f"Source: {params['source_root']}")
        logger.info(f"Dest: {params['dest_root']}")
        logger.info(f"Report: {params['report_path']}")

        # Step 1: Load CaseIDs
        logger.info("Step 1: Loading CaseIDs from Excel...")
        case_ids = load_case_ids(params["excel_file"])
        logger.info(f"  Loaded {len(case_ids)} unique CaseIDs")

        # Step 2: Scan folders
        logger.info("Step 2: Scanning source folders...")
        folders = scan_folders(params["source_root"])
        logger.info(f"  Found {len(folders)} folders")

        # Step 3: Match CaseIDs to folders
        logger.info(f"Step 3: Matching CaseIDs using {params['matcher']} matcher...")
        matches_by_caseid = match_caseids(case_ids, folders, matcher=params["matcher"])

        # Count matches
        match_counts = {cid: len(matches) for cid, matches in matches_by_caseid.items()}
        total_matches = sum(match_counts.values())
        not_found = [cid for cid, count in match_counts.items() if count == 0]

        logger.info(f"  Total matches: {total_matches}")
        logger.info(f"  CaseIDs with no matches: {len(not_found)}")

        # Build match list
        all_matches: List[FolderMatch] = []
        for case_id, folder_entries in matches_by_caseid.items():
            for folder in folder_entries:
                all_matches.append(FolderMatch(
                    case_id=case_id,
                    source_path=folder.path,
                    folder_name=folder.name
                ))

        # Identify duplicates
        duplicate_case_ids: Set[str] = {cid for cid, count in match_counts.items() if count > 1}

        # Step 4: Move folders
        mode_str = "DRY RUN" if params["dry_run"] else "Moving"
        logger.info(f"Step 4: {mode_str} {len(all_matches)} folders...")

        mover = FolderMover(
            dest_root=params["dest_root"],
            dry_run=params["dry_run"],
            max_moves=params["max_moves"],
            on_dest_exists=params["on_dest_exists"],
            duplicates_action=params["duplicates_action"],
            duplicate_case_ids=duplicate_case_ids
        )

        results = mover.move_all(all_matches)
        move_stats = mover.get_stats()

        # Step 5: Write report
        logger.info(f"Step 5: Writing report to {params['report_path']}...")

        run_params = {
            "version": __version__,
            "timestamp": datetime.now().isoformat(),
            "excel_file": str(params["excel_file"]),
            "source_root": str(params["source_root"]),
            "dest_root": str(params["dest_root"]),
            "dry_run": str(params["dry_run"]),
            "matcher": params["matcher"],
            "max_moves": str(params["max_moves"]) if params["max_moves"] else "",
            "on_dest_exists": params["on_dest_exists"],
            "duplicates_action": params["duplicates_action"],
        }

        with ReportWriter(params["report_path"]) as writer:
            writer.write_parameters(run_params)
            for result in results:
                is_multiple = match_counts.get(result.case_id, 1) > 1
                writer.write_move_result(result, is_multiple)
            for case_id in not_found:
                writer.write_not_found(case_id)
            row_count = writer.get_row_count()

        logger.info(f"  Wrote {row_count} entries")

        # Calculate summary stats
        if params["dry_run"]:
            moved = move_stats.get("dry_run", 0) + move_stats.get("dry_run_renamed", 0)
            quarantined = move_stats.get("dry_run_quarantine", 0) + move_stats.get("dry_run_quarantine_renamed", 0)
        else:
            moved = move_stats.get("success", 0) + move_stats.get("success_renamed", 0)
            quarantined = move_stats.get("quarantined", 0) + move_stats.get("quarantined_renamed", 0)

        skipped = (
            move_stats.get("skipped_missing", 0) +
            move_stats.get("skipped_exists", 0) +
            move_stats.get("skipped_excluded", 0) +
            move_stats.get("skipped_resume", 0) +
            move_stats.get("skipped_duplicate", 0)
        )
        errors = move_stats.get("error", 0)

        logger.info("=" * 60)
        logger.info("COMPLETE")
        logger.info(f"  Moved/Would move: {moved}")
        logger.info(f"  Quarantined: {quarantined}")
        logger.info(f"  Skipped: {skipped}")
        logger.info(f"  Errors: {errors}")
        logger.info("=" * 60)

        return {
            "dry_run": params["dry_run"],
            "report_path": params["report_path"],
            "total_caseids": len(case_ids),
            "total_folders": len(folders),
            "total_matches": total_matches,
            "not_found": len(not_found),
            "moved": moved,
            "quarantined": quarantined,
            "skipped": skipped,
            "errors": errors,
        }

    def _show_completion_dialog(self, result: Dict, params: Dict) -> None:
        """Show completion summary dialog."""
        mode = "Preview" if result["dry_run"] else "Operation"
        action = "Would move" if result["dry_run"] else "Moved"

        msg = (
            f"{mode} Complete\n\n"
            f"CaseIDs loaded: {result['total_caseids']}\n"
            f"Folders scanned: {result['total_folders']}\n"
            f"Total matches: {result['total_matches']}\n"
            f"Not found: {result['not_found']}\n\n"
            f"{action}: {result['moved']}\n"
            f"Quarantined: {result['quarantined']}\n"
            f"Skipped: {result['skipped']}\n"
            f"Errors: {result['errors']}\n\n"
            f"Report: {result['report_path']}"
        )

        # Create custom dialog with "Open Report Folder" button
        dialog = tk.Toplevel(self.root)
        dialog.title(f"{mode} Complete")
        dialog.geometry("450x350")
        dialog.transient(self.root)
        dialog.grab_set()

        # Center on parent
        dialog.geometry(f"+{self.root.winfo_x() + 175}+{self.root.winfo_y() + 150}")

        ttk.Label(dialog, text=msg, justify="left", padding=20).pack(fill="both", expand=True)

        btn_frame = ttk.Frame(dialog, padding=10)
        btn_frame.pack(fill="x")

        def open_report_folder():
            folder = os.path.dirname(str(result["report_path"]))
            if sys.platform == "win32":
                os.startfile(folder)
            else:
                import subprocess
                subprocess.run(["xdg-open", folder])

        ttk.Button(btn_frame, text="Open Report Folder", command=open_report_folder).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Close", command=dialog.destroy).pack(side="right", padx=5)

        dialog.wait_window()


def _resource_path(relative_path: str) -> str:
    """Resolve a resource path that works in both source and PyInstaller frozen mode."""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # Running as PyInstaller bundle — resources are in the temp extract dir
        base = sys._MEIPASS
    else:
        # Running from source — project root is two levels up from this file
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, relative_path)


def main() -> None:
    """Main entry point for GUI."""
    root = tk.Tk()

    # Set titlebar / taskbar icon from logo/1.png
    try:
        icon_path = _resource_path(os.path.join("logo", "1.png"))
        if os.path.isfile(icon_path):
            _icon_image = tk.PhotoImage(file=icon_path)
            root.iconphoto(True, _icon_image)
            # Keep a reference so it isn't garbage-collected
            root._icon_image = _icon_image  # type: ignore[attr-defined]
    except Exception:
        pass  # Non-fatal — fall back to default Tk icon

    # Set theme
    try:
        root.tk.call("source", "azure.tcl")
        root.tk.call("set_theme", "light")
    except tk.TclError:
        # Azure theme not available, use default
        pass

    app = FolderMoverGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
