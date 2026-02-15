import os
import sys
import subprocess
import threading
import platform
import time
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import queue
import json

# Try to import ollama and schedule
try:
    import ollama
except ImportError:
    ollama = None

try:
    import schedule
except ImportError:
    schedule = None

def get_python_exe():
    """Returns the path to the python executable, even if running as a frozen bundle."""
    if getattr(sys, 'frozen', False):
        # In a bundle, sys.executable is the .exe of the IDE.
        # We need to find the user's system python to run scripts.
        return "python" # Fallback to path
    return sys.executable

def get_base_path():
    """Returns the base path of the executable or script."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


class ShellExecutor:
    """Handles threaded, safe, and controllable shell command execution."""
    def __init__(self, output_callback, end_callback):
        self.output_callback = output_callback # Function(str) to print to console
        self.end_callback = end_callback       # Function() to call when done
        self.process = None
        self.running = False
        self.lock = threading.Lock()

    def sanitize_command(self, cmd):
        """Injects flags to prevent interactive hangs."""
        if platform.system() == "Windows":
            # Fix RMDIR: /s usually prompts, add /q
            if "rmdir" in cmd.lower() and "/s" in cmd.lower() and "/q" not in cmd.lower():
                cmd += " /q"
                self.output_callback("[AUTO-FIX] Appended /q to rmdir for non-interactive deletion.\n")
            
            # Fix DEL: prompts on wildcards, add /q
            if "del" in cmd.lower() and "/q" not in cmd.lower():
                cmd += " /q" 
                self.output_callback("[AUTO-FIX] Appended /q to del for non-interactive deletion.\n")
                
            # Translations
            if cmd.startswith("mv "):
                cmd = "move " + cmd[3:]
                self.output_callback("[AI-SHELL-AUTOFIX]: Translated 'mv' to 'move'.\n")
            elif cmd.startswith("cp "):
                cmd = "copy " + cmd[3:]
                self.output_callback("[AI-SHELL-AUTOFIX]: Translated 'cp' to 'copy'.\n")
            elif cmd.startswith("ls"):
                 if not cmd.strip().startswith("ls -"): # simple ls
                     cmd = "dir"
                     self.output_callback("[AI-SHELL-AUTOFIX]: Translated 'ls' to 'dir'.\n")
        return cmd

    def run(self, cmd):
        with self.lock:
            if self.running:
                self.output_callback("[ERROR] A command is already running. Please stop it or wait.\n")
                return

            cmd = self.sanitize_command(cmd)
            self.running = True
        
        def _thread_target():
            try:
                self.process = subprocess.Popen(cmd, shell=True, 
                                                stdout=subprocess.PIPE, 
                                                stderr=subprocess.STDOUT, 
                                                text=True, 
                                                bufsize=1)
                for line in self.process.stdout:
                    self.output_callback(f"[AI-SHELL]: {line}")
                self.process.wait()
                exit_code = self.process.returncode
                self.output_callback(f"[AI-SHELL]: Finished with exit code {exit_code}\n")
                if exit_code != 0 and platform.system() == "Windows":
                     self.output_callback(f"[HINT]: Windows commands: 'mv'->'move', 'cp'->'copy', 'ls'->'dir'.\n")
            except Exception as e:
                self.output_callback(f"[EXEC ERROR] {e}\n")
            finally:
                with self.lock:
                    self.running = False
                    self.process = None
                self.end_callback()

        t = threading.Thread(target=_thread_target, daemon=True)
        t.start()

    def stop(self):
        with self.lock:
            if self.process and self.running:
                self.output_callback("[STOP] Terminating process...\n")
                try:
                    subprocess.call(['taskkill', '/F', '/T', '/PID', str(self.process.pid)]) if platform.system() == "Windows" else self.process.terminate()
                except Exception as e:
                    self.output_callback(f"[STOP ERROR]: {e}\n")

class OllamaToolManager:
    """Manages Ollama native tool definitions and parsing."""
    def get_tools(self):
        return [
            {
                'type': 'function',
                'function': {
                    'name': 'create_file',
                    'description': 'Create or overwrite a file with specific content.',
                    'parameters': {
                        'type': 'object',
                        'properties': {
                            'path': {'type': 'string', 'description': 'Destination file path.'},
                            'content': {'type': 'string', 'description': 'Full file content.'},
                        },
                        'required': ['path', 'content'],
                    },
                },
            },
            {
                'type': 'function',
                'function': {
                    'name': 'run_shell_cmd',
                    'description': 'Execute a terminal command.',
                    'parameters': {
                        'type': 'object',
                        'properties': {
                            'command': {'type': 'string', 'description': 'Shell command string.'},
                        },
                        'required': ['command'],
                    },
                },
            },
            {
                'type': 'function',
                'function': {
                    'name': 'delete_file',
                    'description': 'Delete a file from the system.',
                    'parameters': {
                        'type': 'object',
                        'properties': {
                            'path': {'type': 'string', 'description': 'Target file path.'},
                        },
                        'required': ['path'],
                    },
                },
            },
            {
                'type': 'function',
                'function': {
                    'name': 'list_files',
                    'description': 'List all files in the current working directory.',
                    'parameters': {
                        'type': 'object',
                        'properties': {
                            'path': {'type': 'string', 'description': 'Directory path to list (default is current).'},
                        },
                    },
                },
            }
        ]

    def parse_tool_call(self, name, args):
        """Converts Ollama tool call to IDE internal command."""
        # Safe argument retrieval with defaults
        p = args.get('path', '')
        c = args.get('content', '') or args.get('command', '')
        
        if name == 'create_file': return ("Create File", p, c)
        if name == 'run_shell_cmd': return ("Run Command", "", c)
        if name == 'delete_file': return ("Delete File", p, "")
        if name == 'list_files': return ("List Files", p or ".", "")
        return None

class ModelCapabilityChecker:
    """Static utility to detect model capabilities based on internal heuristics."""
    @staticmethod
    def check(model_name):
        model_name = model_name.lower()
        # Heuristic detection
        has_tools = any(x in model_name for x in ["llama3", "qwen2.5", "qwen3", "mistral", "nemo", "command-r", "deepseek-v3", "deepseek-r1", "firefunction", "gemma"])
        has_vision = any(x in model_name for x in ["vision", "llava", "moondream", "bakllava", "vl"])
        return {"tools": has_tools, "vision": has_vision}

class OllamaIDE:
    def __init__(self, root):
        self.root = root
        self.root.title("Ollama Mini-IDE v1.1")
        # Enforce a minimum size to prevent UI collapse on small screens
        self.root.minsize(1500, 800)
        # Set robust initial geometry (Wide enough for all 4 panels)
        self.root.geometry("1850x950")

        self.current_filepath = None
        self.models = []
        self.chat_queue = queue.Queue()
        self.output_queue = queue.Queue()
        self.is_streaming = False
        self.auto_approve = tk.BooleanVar(value=False)
        self.help_visible = tk.BooleanVar(value=True)
        self.os_var = tk.StringVar(value=platform.system())
        self.client = None
        self.chat_history = []
        self.state_loaded = False # Startup Guard: Prevents saving until state is restored
        self.tool_manager = OllamaToolManager()
        self.latest_tool_commands = [] # Buffers tool calls for the prompt checker
        self.base_path = get_base_path()
        # Single source of truth for all state
        self.state_file = os.path.join(self.base_path, "app_state.json")

        self.shell_runner = ShellExecutor(self.append_to_console, self._on_shell_finished)
        
        self.system_prompt = (
            "You are an AI Coding Assistant in 'Ollama Mini-IDE'. "
            "You have access to a REAL FILE SYSTEM. "
            "CRITICAL INSTRUCTION: To generate files or run commands, you MUST use these specific XML tags. "
            "Markdown code blocks (```) DO NOT EXECUTE. Only these tags execute:\n\n"
            "1. CREATE FILE: <CREATE_FILE path=\"path/to/file\">content</CREATE_FILE>\n"
            "2. EXECUTE SHELL: <SHELL_CMD>command</SHELL_CMD>\n"
            "3. DELETE FILE: <DELETE_FILE>path</DELETE_FILE>\n"
            "4. LIST FILES: <LIST_FILES />\n\n"
            "Example Request: 'Create hello.py'\n"
            "Your Response: <CREATE_FILE path=\"hello.py\">print('hello')</CREATE_FILE>\n\n"
            "Always use these tags when the user asks for code changes or actions."
        )

        self.setup_ui()
        # Check if running in a headless test environment
        is_test = False
        try:
             # If root is withdrawn, we assume it's a test
            if self.root.state() == 'withdrawn':
                is_test = True
        except:
            pass

        if not is_test:
            self.start_queue_checker()
            self.start_console_checker()
            self.start_scheduler_thread()
            self.load_models()
        
        self.append_to_console("--- App Started (v1.2) ---\n")
        self.refresh_file_list()
        
        # Only load state if not in test mode
        if not is_test:
            self.load_state()   # Restore EVERYTHING
        
        # If no state was loaded (e.g. first run), force the geometry again 
        # after the widgets have had a chance to initialize.
        if not os.path.exists(self.state_file):
            self.root.update_idletasks()
            self.root.geometry("1850x950")
            
        # Defer a layout enforcement to ensure panes don't collapse on startup
        if not is_test:
            self.root.after(300, self._force_layout_refresh)
        
        # Handle cleanup on close
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_ui(self):
        # Define Colors
        self.bg_color = "#1e1e1e"
        self.fg_color = "#d4d4d4"
        self.accent_color = "#007acc"
        self.sidebar_bg = "#252526"
        self.input_bg = "#3c3c3c"

        self.root.configure(bg=self.bg_color)
        
        # --- Menu Bar ---
        self.menubar = tk.Menu(self.root)
        self.root.config(menu=self.menubar)

        # File Menu
        self.file_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="File", menu=self.file_menu)
        self.file_menu.add_command(label="New", command=self.new_file, accelerator="Ctrl+N")
        self.file_menu.add_command(label="Open", command=self.open_file, accelerator="Ctrl+O")
        self.file_menu.add_command(label="Save", command=self.save_file, accelerator="Ctrl+S")
        self.file_menu.add_command(label="Save As...", command=self.save_as_file)
        self.file_menu.add_command(label="Duplicate (Copy)", command=self.duplicate_file)
        self.file_menu.add_separator()
        self.file_menu.add_command(label="Exit", command=self.on_closing)

        # Run Menu
        self.run_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="Run", menu=self.run_menu)
        self.run_menu.add_command(label="Run Current File", command=self.run_current_file, accelerator="Ctrl+R")

        # AI Menu
        self.ai_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="AI", menu=self.ai_menu)
        self.ai_menu.add_command(label="Refresh Model List", command=self.load_models)
        self.ai_menu.add_command(label="Pull Model (llama3.2)", command=lambda: self.pull_model("llama3.2"))
        self.ai_menu.add_command(label="Pull Model (deepseek-coder:6.7b)", command=lambda: self.pull_model("deepseek-coder:6.7b"))
        self.ai_menu.add_command(label="Clear Chat History", command=self.clear_chat)

        # Tools Menu
        self.tools_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="Tools", menu=self.tools_menu)
        self.tools_menu.add_command(label="Create Virtual Env", command=self.create_venv)
        self.tools_menu.add_command(label="Schedule Current File", command=self.schedule_current_file)
        self.tools_menu.add_command(label="Clear Console", command=self.clear_console)
        self.tools_menu.add_command(label="List Project Files", command=self.list_project_files)
        self.tools_menu.add_command(label="Manual Reconnect", command=self.load_models)
        self.tools_menu.add_command(label="System Check", command=self.load_models)

        # --- Main Layout ---
        self.main_paned = tk.PanedWindow(self.root, orient=tk.VERTICAL, sashrelief=tk.RAISED, sashwidth=4, bg=self.bg_color)
        self.main_paned.pack(fill=tk.BOTH, expand=True)

        self.top_paned = tk.PanedWindow(self.main_paned, orient=tk.HORIZONTAL, sashrelief=tk.RAISED, sashwidth=4, bg=self.bg_color)
        self.main_paned.add(self.top_paned, height=700)

        # Left: File Explorer Sidebar
        self.sidebar_frame = tk.Frame(self.top_paned, bg=self.sidebar_bg, width=250)
        self.top_paned.add(self.sidebar_frame, width=250, minsize=250)
        
        tk.Label(self.sidebar_frame, text="PROJECT FILES", bg=self.sidebar_bg, fg="#858585", font=("Segoe UI", 8, "bold")).pack(fill=tk.X, pady=5)
        
        self.file_listbox = tk.Listbox(self.sidebar_frame, bg=self.sidebar_bg, fg=self.fg_color, 
                                      borderwidth=0, highlightthickness=0, font=("Segoe UI", 9))
        self.file_listbox.pack(fill=tk.BOTH, expand=True)
        self.file_listbox.bind("<Double-1>", self._on_listbox_double_click)
        
        tk.Button(self.sidebar_frame, text="Refresh", command=self.refresh_file_list, 
                  bg=self.input_bg, fg="white", font=("Segoe UI", 8)).pack(fill=tk.X)

        # Middle: Editor Frame
        self.editor_frame = tk.Frame(self.top_paned, bg=self.bg_color)
        self.top_paned.add(self.editor_frame, width=800, minsize=400)

        # Line Numbers
        self.line_numbers = tk.Text(self.editor_frame, width=4, padx=5, pady=5, 
                                   bg=self.sidebar_bg, fg="#858585", state=tk.DISABLED,
                                   font=("Consolas", 12), borderwidth=0)
        self.line_numbers.pack(side=tk.LEFT, fill=tk.Y)

        self.editor_text = tk.Text(self.editor_frame, wrap=tk.NONE, font=("Consolas", 12), undo=True,
                                  bg=self.bg_color, fg=self.fg_color, insertbackground="white",
                                  selectbackground=self.accent_color, padx=5, pady=5, borderwidth=0)
        self.editor_scroll_y = tk.Scrollbar(self.editor_frame, command=self._scroll_both)
        self.editor_scroll_x = tk.Scrollbar(self.editor_frame, orient=tk.HORIZONTAL, command=self.editor_text.xview)
        
        self.editor_text.configure(yscrollcommand=self._update_scroll)
        self.editor_text.configure(xscrollcommand=self.editor_scroll_x.set)

        self.editor_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.editor_scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.editor_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.editor_text.bind("<KeyRelease>", lambda e: self.update_line_numbers())
        self.editor_text.bind("<MouseWheel>", lambda e: self.update_line_numbers())
        self.editor_text.bind("<<Modified>>", lambda e: self._on_modified())

        # Right: Chat Frame
        self.chat_frame = tk.Frame(self.top_paned, bg=self.sidebar_bg)
        self.top_paned.add(self.chat_frame, width=450, minsize=350)

        # Model Selector
        self.model_frame = tk.Frame(self.chat_frame, bg=self.sidebar_bg)
        self.model_frame.pack(fill=tk.X, padx=5, pady=5)
        tk.Label(self.model_frame, text="Model:", bg=self.sidebar_bg, fg=self.fg_color).pack(side=tk.LEFT)
        self.model_var = tk.StringVar()
        self.model_combo = ttk.Combobox(self.model_frame, textvariable=self.model_var, state="readonly")
        self.model_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.model_combo.bind("<<ComboboxSelected>>", lambda e: self.save_state())

        # Auto-approve Toggle
        self.auto_btn = tk.Checkbutton(self.chat_frame, text="Auto-Approve AI Actions", 
                                      variable=self.auto_approve, bg=self.sidebar_bg, fg="#888", 
                                      selectcolor=self.bg_color, activebackground=self.sidebar_bg, 
                                      activeforeground="white", font=("Segoe UI", 8))
        self.auto_btn.pack(fill=tk.X, padx=10)

        # Chat Output
        self.chat_output = tk.Text(self.chat_frame, wrap=tk.WORD, font=("Segoe UI", 10), state=tk.DISABLED,
                                  bg=self.bg_color, fg=self.fg_color, padx=5, pady=5)
        self.chat_output.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.chat_output.tag_configure("user", foreground="#4ec9b0", font=("Segoe UI", 10, "bold"))
        self.chat_output.tag_configure("ai_header", foreground="#ce9178", font=("Segoe UI", 10, "bold"))
        self.chat_output.tag_configure("ai_body", foreground=self.fg_color)

        # Chat Input
        self.input_frame = tk.Frame(self.chat_frame, bg=self.sidebar_bg)
        self.input_frame.pack(fill=tk.X, padx=5, pady=5)
        self.chat_input = tk.Entry(self.input_frame, font=("Segoe UI", 10), bg=self.input_bg, fg="white", insertbackground="white")
        self.chat_input.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.chat_input.bind("<Return>", lambda e: self.send_chat())
        self.send_btn = tk.Button(self.input_frame, text="Send", command=self.send_chat, bg=self.accent_color, fg="white")
        self.send_btn.pack(side=tk.RIGHT, padx=5)

        # Help Toggle Button
        self.help_btn = tk.Button(self.chat_frame, text="Command Reference", command=self.toggle_help, 
                                  bg=self.sidebar_bg, fg="#bbb", font=("Segoe UI", 8), borderwidth=1)
        self.help_btn.pack(fill=tk.X, padx=10, pady=5)

        # --- Right: Help/Reference Frame (Visible by default) ---
        self.help_frame = tk.Frame(self.top_paned, bg=self.sidebar_bg, width=350)
        self.top_paned.add(self.help_frame, width=350, minsize=350)
        self.help_btn.config(relief=tk.SUNKEN, bg=self.accent_color)

        self.console_frame = tk.Frame(self.main_paned, bg="#000000")
        self.main_paned.add(self.console_frame, height=250)
        
        # Console Toolbar
        self.console_toolbar = tk.Frame(self.console_frame, bg="#333333", height=25)
        self.console_toolbar.pack(fill=tk.X)
        
        tk.Label(self.console_toolbar, text=" Console Output", bg="#333333", fg="white", font=("Segoe UI", 8, "bold")).pack(side=tk.LEFT)
        
        self.stop_btn = tk.Button(self.console_toolbar, text="⬛ STOP", command=self.stop_current_command, 
                                  bg="#8a0000", fg="white", font=("Segoe UI", 8, "bold"), 
                                  state=tk.DISABLED, relief=tk.FLAT, padx=5)
        self.stop_btn.pack(side=tk.RIGHT, padx=2, pady=0)

        self.export_btn = tk.Button(self.console_toolbar, text="💾 EXPORT", command=self.export_console, 
                                    bg=self.input_bg, fg="white", font=("Segoe UI", 8), 
                                    relief=tk.FLAT, padx=5)
        self.export_btn.pack(side=tk.RIGHT, padx=2, pady=0)

        self.clear_con_btn = tk.Button(self.console_toolbar, text="🗑️ CLEAR", command=self.clear_console, 
                                      bg=self.input_bg, fg="white", font=("Segoe UI", 8), 
                                      relief=tk.FLAT, padx=5)
        self.clear_con_btn.pack(side=tk.RIGHT, padx=2, pady=0)

        self.console_text = tk.Text(self.console_frame, wrap=tk.NONE, font=("Consolas", 10), state=tk.DISABLED,
                                   bg="black", fg="#00ff00")
        self.console_scroll = tk.Scrollbar(self.console_frame, command=self.console_text.yview)
        self.console_text.configure(yscrollcommand=self.console_scroll.set)
        
        self.console_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.console_text.pack(fill=tk.BOTH, expand=True)

        # Status Bar
        self.status_frame = tk.Frame(self.root, bg=self.sidebar_bg)
        self.status_frame.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.status_bar = tk.Label(self.status_frame, text="Ready", bd=1, relief=tk.SUNKEN, anchor=tk.W, bg=self.sidebar_bg, fg=self.fg_color)
        self.status_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        self.version_label = tk.Label(self.status_frame, text="v1.1 Build", bd=1, relief=tk.SUNKEN, bg=self.sidebar_bg, fg="#858585")
        self.version_label.pack(side=tk.RIGHT)

        self._setup_help_content()

        # Key Bindings
        self.root.bind("<Control-n>", lambda e: self.new_file())
        self.root.bind("<Control-o>", lambda e: self.open_file())
        self.root.bind("<Control-s>", lambda e: self.save_file())
        self.root.bind("<Control-r>", lambda e: self.run_current_file())
        self.root.bind("<Control-Return>", lambda e: self.send_chat())
        self.root.bind("<Control-h>", lambda e: self.toggle_help())

    def _setup_help_content(self):
        """Populates the help frame with command documentation."""
        tk.Label(self.help_frame, text="OS PROFILE", bg=self.sidebar_bg, fg="#858585", 
                 font=("Segoe UI", 8, "bold")).pack(fill=tk.X, pady=(10, 2))
        
        self.os_combo = ttk.Combobox(self.help_frame, textvariable=self.os_var, state="readonly", 
                                     values=["Windows", "Linux", "Darwin"])
        self.os_combo.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(self.help_frame, text="COMMAND REFERENCE", bg=self.sidebar_bg, fg="#858585", 
                 font=("Segoe UI", 8, "bold")).pack(fill=tk.X, pady=(15, 2))
        
        self.help_text = tk.Text(self.help_frame, bg=self.sidebar_bg, fg=self.fg_color, font=("Consolas", 9),
                            borderwidth=0, highlightthickness=0, padx=10, pady=10)
        self.help_text.pack(fill=tk.BOTH, expand=True)
        
        self.update_help_content()

        # Bind this later to distinguish between startup and user interaction
        self.os_combo.bind("<<ComboboxSelected>>", lambda e: self.update_help_content(save=True))

    def update_help_content(self, save=False):
        """Updates the help panel text based on the current OS selection."""
        os_sys = self.os_var.get()
        self.help_text.config(state=tk.NORMAL)
        self.help_text.delete(1.0, tk.END)
        
        # OS specific snippets
        ls_cmd = "dir" if os_sys == "Windows" else "ls -la"
        pip_cmd = "pip install" if os_sys == "Windows" else "python3 -m pip install"
        path_example = "docs\\notes.txt" if os_sys == "Windows" else "docs/notes.txt"

        ref_content = (
            f"Mode: {os_sys}\n"
            "AI will use this syntax:\n\n"
            "--- CREATE FILE ---\n"
            f"<CREATE_FILE path=\"{path_example}\">\n"
            "content here\n"
            "</CREATE_FILE>\n\n"
            "--- RUN COMMAND ---\n"
            "<SHELL_CMD>\n"
            f"{ls_cmd}\n"
            f"{pip_cmd} requests\n"
            "</SHELL_CMD>\n\n"
            "--- DELETE FILE ---\n"
            f"<DELETE_FILE>{path_example}</DELETE_FILE>\n\n"
            "--- LIST FILES ---\n"
            "<LIST_FILES />\n\n"
            "Note: Markdown code blocks\n(```) do NOT execute."
        )
        self.help_text.insert(tk.END, ref_content)
        self.help_text.config(state=tk.DISABLED)
        if save:
            self.save_state()

    def toggle_help(self):
        """Toggles the visibility of the command reference panel."""
        if self.help_visible.get():
            self.top_paned.forget(self.help_frame)
            self.help_visible.set(False)
            self.help_btn.config(relief=tk.RAISED, bg=self.sidebar_bg)
        else:
            self.top_paned.add(self.help_frame, width=350, minsize=350)
            self.help_visible.set(True)
            self.help_btn.config(relief=tk.SUNKEN, bg=self.accent_color)
        self.save_state()
        
    def _force_layout_refresh(self):
        """Forces a layout update to ensure panes aren't squashed on startup."""
        self.root.update_idletasks()
        pass

    def stop_current_command(self):
        self.shell_runner.stop()
        
    def _on_shell_finished(self):
        """Called by thread when shell command ends."""
        self.root.after(0, lambda: self.stop_btn.config(state=tk.DISABLED, bg="#500000"))
        self.root.after(0, self.refresh_file_list)

    def export_console(self):
        """Exports the console content to a text file."""
        content = self.console_text.get(1.0, tk.END)
        filepath = filedialog.asksaveasfilename(defaultextension=".txt", 
                                                filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")],
                                                title="Export Console Log")
        if filepath:
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                messagebox.showinfo("Export Success", f"Console log saved to {filepath}")
            except Exception as e:
                messagebox.showerror("Export Error", f"Could not export console: {e}")

    # --- File Operations ---
    def new_file(self):
        self.editor_text.delete(1.0, tk.END)
        self.current_filepath = None
        self.update_status("New File")

    def open_file(self):
        filepath = filedialog.askopenfilename(filetypes=[("Python Files", "*.py"), ("All Files", "*.*")])
        if filepath:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                self.editor_text.delete(1.0, tk.END)
                self.editor_text.insert(tk.END, content)
                self.current_filepath = filepath
                self.update_status(f"Opened: {filepath}")
            except Exception as e:
                messagebox.showerror("Error", f"Could not open file: {e}")

    def save_file(self):
        if self.current_filepath:
            self._write_file(self.current_filepath)
        else:
            self.save_as_file()

    def save_as_file(self):
        filepath = filedialog.asksaveasfilename(defaultextension=".py", filetypes=[("Python Files", "*.py"), ("All Files", "*.*")])
        if filepath:
            self._write_file(filepath)
            self.current_filepath = filepath
            self.update_status(f"Saved: {filepath}")

    def duplicate_file(self):
        filepath = filedialog.asksaveasfilename(defaultextension=".py", title="Duplicate to...", filetypes=[("Python Files", "*.py"), ("All Files", "*.*")])
        if filepath:
            self._write_file(filepath)
            messagebox.showinfo("Duplicate", f"File duplicated to: {filepath}")

    def _write_file(self, path):
        try:
            content = self.editor_text.get(1.0, tk.END)
            # Remove trailing newline added by tk.Text
            if content.endswith("\n"):
                content = content[:-1]
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            self.refresh_file_list() # Auto-refresh on save
        except Exception as e:
            messagebox.showerror("Error", f"Could not save file: {e}")

    # --- AI Operations ---
    def load_models(self):
        if not ollama:
            self.append_to_console("Error: 'ollama' package missing.\n")
            return

        self.update_status("Ollama: Connecting...")
        self.append_to_console("\n[v1.1] Fetching models list...\n")

        def _fetch():
            print("[DEBUG] Worker thread started.")
            try:
                self.output_queue.put("Worker: Thread background process started.\n")
                
                print("[DEBUG] Initializing Client...")
                if not self.client:
                    # Explicit timeout in the client if supported (using httpx kwargs)
                    # For ollama-python: it doesn't have a direct timeout arg in __init__ for older versions,
                    # but we can try to wrap the call.
                    self.client = ollama.Client(host='http://127.0.0.1:11434')
                
                print("[DEBUG] Calling client.list()...")
                self.output_queue.put("Worker: Contacting Ollama service...\n")
                
                # We wrap list call in a try to catch specific network errors
                response = self.client.list()
                
                print(f"[DEBUG] Response status: {'Success' if response else 'Empty'}")
                self.output_queue.put("Worker: List data received.\n")
                
                models = []
                if isinstance(response, dict) and 'models' in response:
                    models = [m['name'] for m in response['models']]
                elif hasattr(response, 'models'):
                    for m in response.models:
                        if hasattr(m, 'model'): models.append(m.model)
                        elif hasattr(m, 'name'): models.append(m.name)
                        elif isinstance(m, dict): models.append(m.get('name', str(m)))
                        else: models.append(str(m))
                
                if not models:
                    self.output_queue.put("Worker: No models found on this instance.\n")
                else:
                    self.output_queue.put(f"Worker: Found {len(models)} models.\n")

                self.root.after(0, lambda: self.update_model_list(models))
            except Exception as e:
                self.output_queue.put(f"Worker CRITICAL ERROR: {str(e)}\n")
                self.root.after(0, lambda: self.update_status("Ollama: Offline"))

        # Explicitly start the thread
        t = threading.Thread(target=_fetch, daemon=True)
        t.start()
        self.append_to_console(f"Main: Thread {t.name} dispatched.\n")

    def pull_model(self, model_name):
        self.append_to_console(f"--- Pulling model: {model_name} ---\n")
        self.update_status(f"Pulling {model_name}...")
        
        def _pull():
            try:
                if not self.client: return
                # This blocks but we are in a thread
                for progress in self.client.pull(model=model_name, stream=True):
                    status = progress.get('status', '')
                    if status:
                        self.output_queue.put(f" {status}\n")
                self.output_queue.put(f"Successfully pulled {model_name}.\n")
                self.root.after(0, self.load_models)
            except Exception as e:
                self.output_queue.put(f"Error pulling model: {e}\n")
        
        threading.Thread(target=_pull, daemon=True).start()

    # --- Unified AI Worker Logic ---

    def send_agent_feedback(self, result_text, tool_call_id=None):
        """Feed tool execution results back to the agentic model."""
        self.chat_history.append({
            'role': 'tool',
            'content': result_text,
            'tool_call_id': tool_call_id
        })
        self.append_to_console(f"[AGENT-FEEDBACK]: Returning result to model...\n")
        self._on_chat_worker_trigger()

    def _on_chat_worker_trigger(self):
        """Dispatches the worker thread."""
        model = self.model_var.get()
        t = threading.Thread(target=self._ollama_worker, args=(model,), daemon=True)
        t.start()

    def update_model_list(self, models):
        self.models = models
        
        # Decorate names with capabilities
        decorated_names = []
        for m in models:
            caps = ModelCapabilityChecker.check(m)
            tags = []
            if caps['tools']: tags.append("[Tools]")
            if caps['vision']: tags.append("[Vision]")
            decorated_names.append(f"{m} {' '.join(tags)}".strip())

        self.model_combo['values'] = decorated_names
        if models:
            # Priority: 1. Restored state model, 2. 'qwen2.5-coder', 3. First available
            state_model = getattr(self, '_restored_model', None)
            if state_model in models:
                self.model_var.set(state_model)
                self.model_combo.set(state_model) # Force UI sync
            elif "qwen3:4b" in models:
                self.model_var.set("qwen3:4b")
            else:
                self.model_combo.current(0)
            
            # self.save_state() <-- REMOVED: Managed by startup guard/user interaction
            self.update_status(f"Models loaded: {len(models)}")
        else:
            self.update_status("No Ollama models found.")

    def send_chat(self):
        if not ollama:
            messagebox.showerror("Error", "Ollama library not installed.")
            return
        
        prompt = self.chat_input.get().strip()
        model = self.model_var.get()

        if not prompt:
            return
        if not model:
            messagebox.showwarning("Warning", "Please select a model first.")
            return
        if self.is_streaming:
            return

        # Prepare context
        editor_content = self.editor_text.get(1.0, tk.END).strip()
        
        # Build message history
        if not self.chat_history:
            self.chat_history.append({'role': 'system', 'content': self.system_prompt})
        
        # Prepare the context + prompt + SYSTEM REMINDER (Context Injection)
        # This forces the model to obey tags even if context is long.
        system_reminder = f"\n[SYSTEM REMINDER: You are on {self.os_var.get()}. To perform actions, you MUST use <CREATE_FILE>, <SHELL_CMD>, etc. Do not write markdown blocks.]"
        
        user_content = f"CONTEXT (Current Editor):\n```python\n{editor_content}\n```\n\nUSER QUESTION: {prompt}{system_reminder}"
        self.chat_history.append({'role': 'user', 'content': user_content})
        
        self.chat_input.delete(0, tk.END)
        self.append_to_chat(f"\n[You]: {prompt}\n", "user")
        self.append_to_chat(f"[AI ({model})]: ", "ai_header")
        
        self.is_streaming = True
        self.current_ai_response = ""
        self.send_btn.config(state=tk.DISABLED)
        
        self.save_state() # Auto-save state on new message

        threading.Thread(target=self._ollama_worker, args=(model,), daemon=True).start()

    def _ollama_worker(self, model):
        """Unified thread worker for Ollama API with streaming and native tool support."""
        try:
            if not self.client:
                self.chat_queue.put("\n[Error]: Ollama client not initialized.")
                return

            full_model_name = model.split(' [')[0].strip()
            
            # 1. Detect capabilities and prepare tools
            caps = ModelCapabilityChecker.check(full_model_name)
            tools = self.tool_manager.get_tools() if caps['tools'] else None
            
            # 2. Inject system prompt if tools are supported but history is empty/missing system message
            if tools and not any(m['role'] == 'system' for m in self.chat_history):
                 self.chat_history.insert(0, {'role': 'system', 'content': 'You are a coder helper with Native Tools. Use them correctly.'})

            # Check if vision-capable model is selected
            if caps['vision']:
                self.append_to_console(f"[STATUS] Vision capability detected for {full_model_name}\n")
            
            response = self.client.chat(
                model=full_model_name,
                messages=self.chat_history,
                tools=tools,
                stream=True
            )
            
            full_response = ""
            native_tool_calls_detected = []
            
            for chunk in response:
                msg = chunk.get('message', {})
                content = msg.get('content', '')
                tool_calls = msg.get('tool_calls', [])
                
                if content:
                    full_response += content
                    self.chat_queue.put(content)
                
                if tool_calls:
                    for t in tool_calls:
                        native_tool_calls_detected.append(t)
            
            # If native tools were used, convert them to XML strings so parse_ai_commands can see them
            # and append them to self.current_ai_response for the console/debug_dump logs.
            xml_conversion = ""
            for tool in native_tool_calls_detected:
                fn = tool.get('function', {})
                name = fn.get('name')
                args = fn.get('arguments', {})
                
                # Convert to XML equivalent based on OllamaToolManager mappings
                if name == 'create_file':
                    xml_conversion += f'\n<CREATE_FILE path="{args.get("path")}">\n{args.get("content")}\n</CREATE_FILE>'
                elif name == 'run_shell_cmd':
                    xml_conversion += f'\n<SHELL_CMD>\n{args.get("command")}\n</SHELL_CMD>'
                elif name == 'delete_file':
                    xml_conversion += f'\n<DELETE_FILE>{args.get("path")}</DELETE_FILE>'
                elif name == 'list_files':
                    xml_conversion += f'\n<LIST_FILES />'
            
            if xml_conversion:
                self.chat_queue.put("\n[AI Native Tool Call Detected]\n")
                full_response += xml_conversion
            
            if not full_response:
                self.chat_queue.put("\n[Empty Response]: The model generated no text or tool calls.")

            # Save response to history
            self.chat_history.append({'role': 'assistant', 'content': full_response})
            self.current_ai_response = full_response
            self.root.after(0, self.save_state) # Save state after response
            
        except Exception as e:
            self.chat_queue.put(f"\n[Error]: {e}")
            import traceback
            print(f"[ERROR] Ollama Worker: {e}")
            traceback.print_exc()
        finally:
            self.chat_queue.put(None) # Sentinel for end

    def start_queue_checker(self):
        try:
            # OPTIMIZATION: Check if there's anything to do first
            if not self.chat_queue.empty():
                self.chat_output.config(state=tk.NORMAL)
                while True:
                    try:
                        chunk = self.chat_queue.get_nowait()
                        if chunk is None:
                            self.is_streaming = False
                            self.send_btn.config(state=tk.NORMAL)
                            print("[DEBUG] Streaming finished. Triggering command check.")
                            self.append_to_console("[DEBUG] Streaming finished. Checking for commands...\n")
                            self.check_for_ai_commands()
                        else:
                            self.chat_output.insert(tk.END, chunk, "ai_body")
                            self.chat_output.see(tk.END)
                    except queue.Empty:
                        break
                self.chat_output.config(state=tk.DISABLED)
                
        except Exception as e:
            pass
        self.root.after(50, self.start_queue_checker) # Faster poll

    def check_for_ai_commands(self):
        """Orchestrates the detection and execution of AI commands."""
        print(f"[DEBUG] Checking text length: {len(self.current_ai_response)}")
        
        # DUMP FOR AGENT VISIBILITY
        try:
            with open("debug_dump.txt", "w", encoding="utf-8") as f:
                f.write(f"--- TIMESTAMP: {datetime.now()} ---\n")
                f.write(f"RAW BUFFER LEN: {len(self.current_ai_response)}\n")
                f.write("--- START RAW CONTENT ---\n")
                f.write(self.current_ai_response)
                f.write("\n--- END RAW CONTENT ---\n")
        except Exception as e:
            print(f"Failed to write dump: {e}")
            
        commands = self.parse_ai_commands(self.current_ai_response)
        
        print(f"[DEBUG] Commands found: {len(commands)}")
        
        if commands:
            self.append_to_chat("\n[Action Suggested]: The AI wants to perform operations. Check Tools > Pending AI Commands.\n", "ai_header")
            self.show_ai_command_dialog(commands)

    def parse_ai_commands(self, text):
        """Extracts command tuples from the provided text."""
        import re
        
        # Patterns
        # 1. Strict XML Pattern (Preferred)
        create_strict = r'<CREATE_FILE path="([^"]+)">([\s\S]*?)<\/CREATE_FILE>'
        
        # 2. Lazy/Hallucinated Pattern (Observed: <CREATE_FILE>filename:content)
        # We capture up to the first colon or newline as filename
        create_lazy = r'<CREATE_FILE>\s*([^:\n]+)[:\n]([\s\S]*)'
        
        # 3. Shell Patterns
        shell_strict = r'<SHELL_CMD>([\s\S]*?)<\/SHELL_CMD>'
        shell_lazy = r'<SHELL_CMD>([\s\S]*)' # Dangerous, but captures remainder if tag is open
        
        # 4. Delete Pattern
        delete_pattern = r'<DELETE_FILE>([^<]+)<\/DELETE_FILE>'

        commands = []
        
        # --- Create File Parsing ---
        # Try strict first
        for p, c in re.findall(create_strict, text):
            commands.append(("Create File", p, c))
            
        # If strict failed, try lazy only if we have no commands yet or if the lazy pattern finds something new
        # (Simplified: just check lazy if we found the tag but not the strict match)
        if not commands and "<CREATE_FILE>" in text:
             # This regex is greedy for content, assumes end of string or next tag? 
             # Let's be careful. If the user output is single line, the lazy regex works.
             matches = re.findall(create_lazy, text)
             for p, c in matches:
                 # Cleanup trailing closing tags if the model halfway tried
                 c = c.replace("</CREATE_FILE>", "").strip()
                 commands.append(("Create File", p.strip(), c))

        # --- Shell Parsing ---
        # Try strict first
        for c in re.findall(shell_strict, text):
            commands.append(("Run Command", "", c))

        # Fallback: Lazy Shell (if no strict match found but tag exists)
        # matches <SHELL_CMD>command (until end of line or string)
        if not any(cmd[0] == "Run Command" for cmd in commands) and "<SHELL_CMD>" in text:
             # Match until end of string, taking care to strip if multiple lines
             # regex: <SHELL_CMD> followed by anything
             matches = re.findall(shell_lazy, text)
             for c in matches:
                 # Clean up potential mess
                 c = c.replace("</SHELL_CMD>", "").strip()
                 # If it looks like multiple lines, maybe take just the first? 
                 # For now, trust the capture.
                 commands.append(("Run Command", "", c))

        for p in re.findall(delete_pattern, text):
            commands.append(("Delete File", p, ""))
            
        return commands

    def show_ai_command_dialog(self, commands):
        msg = "The AI wants to perform these actions:\n\n"
        for type, path, data in commands:
            msg += f"- {type}: {path if path else data[:30] + '...'}\n"
        
        # Check Auto-approve toggle
        if self.auto_approve.get():
            self.append_to_console("[AUTO-APPROVE]: Executing recognized commands...\n")
            for type, path, data in commands:
                self.execute_one_command(type, path, data)
            return

        if messagebox.askyesno("AI Action Request", msg + "\nAllow execution?"):
            for type, path, data in commands:
                self.execute_one_command(type, path, data)

    def execute_one_command(self, type, path, data):
        try:
            abs_path = os.path.abspath(path) if path else ""
            if type == "Create File":
                # Ensure directory exists
                dir_name = os.path.dirname(abs_path)
                if dir_name:
                    os.makedirs(dir_name, exist_ok=True)
                
                with open(abs_path, "w", encoding="utf-8") as f:
                    f.write(data)
                
                self.append_to_console(f"AI Action SUCCESS: Created file at {abs_path}\n")
                self.refresh_file_list() # Update sidebar
                
                # Automatically open the file in the editor so the user can see it!
                if messagebox.askyesno("Open File?", f"AI created {path}. Would you like to open it in the editor now?"):
                    self._load_file_into_editor(abs_path)
                    
            elif type == "Delete File":
                if os.path.exists(abs_path):
                    os.remove(abs_path)
                    self.append_to_console(f"AI Action SUCCESS: Deleted file {abs_path}\n")
                    self.refresh_file_list()
                else:
                    self.append_to_console(f"AI Action FAILED: File {abs_path} not found.\n")
            elif type == "Run Command":
                self.append_to_console(f"AI Action: Running shell command '{data}'...\n")
                self.stop_btn.config(state=tk.NORMAL, bg="#ff0000")
                self.shell_runner.run(data)
            elif type == "List Files":
                self.list_project_files()

        except Exception as e:
            messagebox.showerror("Action Error", f"Failed to execute {type}: {e}")

    def refresh_file_list(self):
        """Updates the sidebar listbox with files in the current directory."""
        self.file_listbox.delete(0, tk.END)
        try:
            files = sorted(os.listdir(os.getcwd()))
            for f in files:
                if os.path.isfile(f):
                    self.file_listbox.insert(tk.END, f"  📄 {f}")
                else:
                    self.file_listbox.insert(tk.END, f"  📁 {f}")
        except Exception as e:
            self.file_listbox.insert(tk.END, "Error loading files")

    def _on_listbox_double_click(self, event):
        selection = self.file_listbox.curselection()
        if selection:
            item = self.file_listbox.get(selection[0])
            filename = item.split(" ", 2)[-1]
            if os.path.isfile(filename):
                self._load_file_into_editor(os.path.abspath(filename))

    def list_project_files(self):
        """Lists files in the current working directory."""
        self.append_to_console("\n--- Project File List ---\n")
        try:
            cwd = os.getcwd()
            self.append_to_console(f"Directory: {cwd}\n")
            files = os.listdir(cwd)
            for f in files:
                mtime = os.path.getmtime(f)
                dt = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
                size = os.path.getsize(f) if os.path.isfile(f) else "DIR"
                self.append_to_console(f" [{dt}]  {str(size).rjust(8)}  {f}\n")
        except Exception as e:
            self.append_to_console(f"Error listing files: {e}\n")

    def _load_file_into_editor(self, filepath):
        """Helper to load a file into the editor UI."""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            self.editor_text.delete(1.0, tk.END)
            self.editor_text.insert(tk.END, content)
            self.current_filepath = filepath
            self.update_status(f"Project File: {filepath}")
            self.update_line_numbers()
        except Exception as e:
            self.append_to_console(f"Error opening file: {e}\n")

    def append_to_chat(self, text, tag=None):
        self.chat_output.config(state=tk.NORMAL)
        self.chat_output.insert(tk.END, text, tag)
        self.chat_output.see(tk.END)
        self.chat_output.config(state=tk.DISABLED)

    def clear_chat(self):
        self.chat_output.config(state=tk.NORMAL)
        self.chat_output.delete(1.0, tk.END)
        self.chat_output.config(state=tk.DISABLED)
        self.chat_history = [] # Reset AI memory
        self.save_state() # Update state immediately
        self.append_to_console("AI Chat History Cleared.\n")



    def save_state(self):
        """Saves ENTIRE application state to a single JSON file."""
        if not self.state_loaded:
            # Startup Guard active
            return

        try:
            state = {
                "filepath": self.current_filepath,
                "content": self.editor_text.get(1.0, tk.END),
                "model": self.model_var.get(),
                "auto_approve": self.auto_approve.get(),
                "help_visible": self.help_visible.get(),
                "os_profile": self.os_var.get(),
                "geometry": self.root.geometry(),
                "console": self.console_text.get(1.0, tk.END),
                "chat_history": self.chat_history
            }
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            print(f"Failed to save app state: {e}")

    def load_state(self):
        """Restores the ENTIRE IDE state from the JSON file."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    state = json.load(f)
                
                # 1. Restore Layout
                try:
                    if state.get("geometry"):
                        self.root.geometry(state["geometry"])
                except Exception as e:
                    print(f"[WARN] Failed to restore geometry: {e}")
                
                # 2. Restore Filepath
                self.current_filepath = state.get("filepath")
                
                # 3. Restore Editor Content
                try:
                    content = state.get("content", "")
                    if content:
                        self.editor_text.delete(1.0, tk.END)
                        self.editor_text.insert(tk.END, content)
                        self.update_line_numbers()
                except Exception as e:
                    print(f"[WARN] Failed to restore content: {e}")

                # 4. Restore Console Logs
                try:
                    console_logs = state.get("console", "")
                    if console_logs:
                        self.console_text.config(state=tk.NORMAL)
                        self.console_text.delete(1.0, tk.END)
                        self.console_text.insert(tk.END, console_logs)
                        self.console_text.see(tk.END)
                        self.console_text.config(state=tk.DISABLED)
                except Exception as e:
                    print(f"[WARN] Failed to restore console: {e}")
                
                # 5. Restore Chat History
                try:
                    self.chat_history = state.get("chat_history", [])
                    if self.chat_history:
                        self.console_text.config(state=tk.NORMAL)
                        self.console_text.insert(tk.END, f"[SYSTEM] Restoring {len(self.chat_history)} chat messages...\n")
                        self.console_text.config(state=tk.DISABLED)

                    self.chat_output.config(state=tk.NORMAL)
                    self.chat_output.delete(1.0, tk.END)
                    
                    for msg in self.chat_history:
                        role = msg.get('role', '')
                        content = msg.get('content', '')
                        
                        if role == 'user':
                            if "USER QUESTION:" in content:
                                display_text = content.split("USER QUESTION:")[-1]
                                if "[SYSTEM REMINDER" in display_text:
                                    display_text = display_text.split("[SYSTEM REMINDER")[0]
                                display_text = display_text.strip()
                            else:
                                display_text = content
                                
                            self.append_to_chat(f"\n[You]: {display_text}\n", "user")
                            
                        elif role == 'assistant':
                            self.append_to_chat(f"[AI]: ", "ai_header")
                            self.append_to_chat(content, "ai_body")
                        elif role == 'tool':
                            self.append_to_chat(f"\n[Tool Result]: {content[:50]}...\n", "code")

                    self.chat_output.see(tk.END)
                    self.chat_output.config(state=tk.DISABLED)
                except Exception as e:
                    print(f"[WARN] Failed to restore chat history: {e}")

                # 6. Restore Model, Auto-approve & OS Selection & Help Visibility
                self._restored_model = state.get("model")
                self.auto_approve.set(state.get("auto_approve", False))
                self.help_visible.set(state.get("help_visible", True))
                self.os_var.set(state.get("os_profile", platform.system()))
                
                # Restore Help Visibility
                saved_help = state.get("help_visible", True)
                if saved_help != self.help_visible.get():
                    if saved_help:
                        self.top_paned.add(self.help_frame, width=350)
                        self.help_btn.config(relief=tk.SUNKEN, bg=self.accent_color)
                    else:
                        self.top_paned.forget(self.help_frame)
                        self.help_btn.config(relief=tk.RAISED, bg=self.sidebar_bg)
                    self.help_visible.set(saved_help)

                self.update_help_content()
                
                if self.current_filepath:
                    self.update_status(f"Restored file: {self.current_filepath}")
                else:
                    self.update_status("Restored unsaved session")
                    
                self.append_to_console("Total session state restored.\n")
            except Exception as e:
                self.append_to_console(f"Could not restore app state: {e}\n")
        
        # Startup Guard Lifted: Safe to save now
        self.state_loaded = True

    def on_closing(self):
        """Handles cleanup and state saving before exit."""
        self.save_state()
        self.root.destroy()

    # --- Console Output ---
    def start_console_checker(self):
        try:
            while True:
                line = self.output_queue.get_nowait()
                self.append_to_console(line)
        except queue.Empty:
            pass
        self.root.after(100, self.start_console_checker)

    def append_to_console(self, text: str):
        self.console_text.config(state=tk.NORMAL)
        
        # Add timestamp to each newline chunk
        # If the text is just a newline, don't double-timestamp
        if text.strip():
            timestamp = datetime.now().strftime("[%H:%M:%S] ")
            # If the last line doesn't end in newline, we might be appending to same line
            last_line = self.console_text.get("end-2c linestart", "end-1c")
            if not last_line or self.console_text.index("end-1c") == "1.0":
                self.console_text.insert(tk.END, timestamp)
            elif "\n" in text:
                # Handle multi-line blocks
                text = text.replace("\n", f"\n{timestamp}")
        
        self.console_text.insert(tk.END, text)
        self.console_text.see(tk.END)
        self.console_text.config(state=tk.DISABLED)
        # Ensure console output is persisted by saving state periodically
        if "\n" in text:
            self.save_state()

    def clear_console(self):
        self.console_text.config(state=tk.NORMAL)
        self.console_text.delete(1.0, tk.END)
        self.console_text.config(state=tk.DISABLED)

    # --- Execution ---
    def run_current_file(self):
        if not self.current_filepath:
            self.save_as_file()
            if not self.current_filepath: return
        else:
            self.save_file()

        filepath = self.current_filepath
        self.append_to_console(f"\n--- Running: {filepath} ---\n")

        # Start a thread to run and capture output
        def _run_and_capture():
            try:
                python_exe = get_python_exe()
                process = subprocess.Popen([python_exe, "-u", filepath], 
                                         stdout=subprocess.PIPE, 
                                         stderr=subprocess.STDOUT, 
                                         text=True)
                for line in process.stdout:
                    self.output_queue.put(line)
                process.wait()
                self.output_queue.put(f"\n--- Finished (Exit Code: {process.returncode}) ---\n")
            except Exception as e:
                self.output_queue.put(f"\n--- Error: {e} ---\n")

        threading.Thread(target=_run_and_capture, daemon=True).start()

        # Also launch external terminal as requested
        try:
            python_exe = get_python_exe()
            if platform.system() == "Windows":
                subprocess.Popen(["cmd", "/c", "start", "cmd", "/k", python_exe, filepath])
            elif platform.system() == "Darwin": # macOS
                subprocess.Popen(["open", "-a", "Terminal", python_exe, filepath])
            else: # Linux
                terminals = ["x-terminal-emulator", "gnome-terminal", "konsole", "xterm"]
                for term in terminals:
                    try:
                        subprocess.Popen([term, "-e", f"{python_exe} {filepath}"])
                        break
                    except FileNotFoundError:
                        continue
        except Exception as e:
            print(f"Failed to launch external terminal: {e}")

    # --- Tools ---
    def create_venv(self):
        venv_dir = filedialog.askdirectory(title="Select Folder for Virtual Environment")
        if not venv_dir:
            return
        
        target = os.path.join(venv_dir, "venv")
        self.update_status(f"Creating venv at {target}...")
        
        def _run():
            try:
                python_exe = get_python_exe()
                subprocess.run([python_exe, "-m", "venv", target], check=True)
                self.root.after(0, lambda: messagebox.showinfo("Success", f"Venv created at {target}"))
                self.root.after(0, lambda: self.update_status(f"Venv created: {target}"))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", f"Failed to create venv: {e}"))

        threading.Thread(target=_run, daemon=True).start()

    def schedule_current_file(self):
        if not schedule:
            messagebox.showerror("Error", "Schedule library not installed.")
            return
        if not self.current_filepath:
            messagebox.showwarning("Warning", "Save your file first!")
            return

        # Simple Interval Dialog
        dialog = tk.Toplevel(self.root)
        dialog.title("Schedule Task")
        dialog.geometry("300x150")
        
        tk.Label(dialog, text="Run Every (minutes):").pack(pady=10)
        minutes_var = tk.StringVar(value="60")
        tk.Entry(dialog, textvariable=minutes_var).pack()
        
        def set_schedule():
            try:
                mins = int(minutes_var.get())
                filepath = self.current_filepath
                schedule.every(mins).minutes.do(self._scheduled_task, filepath)
                messagebox.showinfo("Scheduled", f"Task scheduled every {mins} minutes for {filepath}")
                dialog.destroy()
            except ValueError:
                messagebox.showerror("Error", "Invalid number of minutes.")

        tk.Button(dialog, text="Set Schedule", command=set_schedule).pack(pady=10)

    def _scheduled_task(self, filepath):
        print(f"[{datetime.now()}] Running scheduled task: {filepath}")
        try:
            # Run silently in background
            python_exe = get_python_exe()
            subprocess.run([python_exe, filepath], capture_output=True, text=True)
        except Exception as e:
            print(f"Scheduled task error: {e}")

    def start_scheduler_thread(self):
        if not schedule: return
        def _run():
            while True:
                schedule.run_pending()
                time.sleep(1)
        threading.Thread(target=_run, daemon=True).start()

    # --- UI Helpers ---
    def _scroll_both(self, *args):
        self.editor_text.yview(*args)
        self.line_numbers.yview(*args)

    def _update_scroll(self, *args):
        self.editor_scroll_y.set(*args)
        self.line_numbers.yview_moveto(args[0])

    def update_line_numbers(self):
        self.line_numbers.config(state=tk.NORMAL)
        self.line_numbers.delete(1.0, tk.END)
        
        line_count = self.editor_text.get(1.0, tk.END).count('\n')
        line_num_content = "\n".join(str(i) for i in range(1, line_count + 1))
        self.line_numbers.insert(1.0, line_num_content)
        self.line_numbers.config(state=tk.DISABLED)
        # Sync scroll
        self.line_numbers.yview_moveto(self.editor_text.yview()[0])

    def _on_modified(self):
        if self.editor_text.edit_modified():
            self.update_line_numbers()
            self.editor_text.edit_modified(False)

    def update_status(self, text):
        now = datetime.now().strftime("%H:%M:%S")
        self.status_bar.config(text=f"[{now}] {text}")

if __name__ == "__main__":
    # CLI Testing Mode
    if "--test" in sys.argv:
        print("Starting Ollama Mini-IDE Test Mode...")
        try:
            import ollama
            client = ollama.Client(host='http://127.0.0.1:11434')
            models = client.list()
            print(f"Success: Connected to Ollama. Found {len(models.models if hasattr(models, 'models') else models.get('models', []))} models.")
            sys.exit(0)
        except Exception as e:
            print(f"Failure: Could not connect to Ollama: {e}")
            sys.exit(1)

    root = tk.Tk()
    
    # Simple styling
    style = ttk.Style()
    style.theme_use('clam')

    app = OllamaIDE(root)
    root.mainloop()
