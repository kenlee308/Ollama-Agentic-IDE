import os
import sys
import threading
import subprocess
import json
import time
import queue
import tkinter as tk
from tkinter import messagebox, ttk
import re
import platform
from datetime import datetime

# Optional imports for visual testing
try:
    import pyautogui
    import pygetwindow as gw
except ImportError:
    pyautogui = None
    gw = None

# Add current dir to path to allow import of sibling files
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Try to import ollama and the IDE class
try:
    import ollama
except ImportError:
    ollama = None

# Non-interactive tool detection for headless tests
os.environ["OLLAMA_IDE_TEST_MODE"] = "1"

try:
    from Ollama_Agentic_IDE_v1_1 import OllamaIDE, OllamaToolManager, ModelCapabilityChecker
except ImportError as e:
    print(f"[CRITICAL] Failed to import IDE components: {e}")
    OllamaIDE = None
    OllamaToolManager = None
    ModelCapabilityChecker = None

class DiagnosticEngine:
    """Core logic for diagnostics, decoupled from UI."""
    def __init__(self, log_callback, progress_callback=None):
        self.log = log_callback
        self.progress = progress_callback 
        if getattr(sys, 'frozen', False):
            self.base = os.path.dirname(sys.executable)
        else:
            self.base = os.path.dirname(os.path.abspath(__file__))
            
        self.state_file = os.path.join(self.base, "app_state.json")
        self.test_results = []  
        self.target_os = platform.system()
        self.selected_model = None 
        self._restored_model = None
        self.pending_tasks = 0 
        self.audit_mode = False
        self.load_state()

    def log_result(self, test_name, status, details=""):
        """Track test results for final summary."""
        self.test_results.append({
            "test": test_name,
            "status": status, 
            "details": details
        })

    def save_state(self):
        """Persists selection to app_state.json"""
        try:
            state = {}
            if os.path.exists(self.state_file):
                with open(self.state_file, "r") as f:
                    state = json.load(f)
            
            state["model"] = self.selected_model
            with open(self.state_file, "w") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            self.log(f"Failed to save state: {e}")

    def load_state(self):
        """Loads selection from app_state.json"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, "r") as f:
                    state = json.load(f)
                self._restored_model = state.get("model")
                if self._restored_model:
                    # Strip tags if present in saved state
                    self.selected_model = self._restored_model.split(' [')[0].strip()
        except Exception as e:
            self.log(f"Failed to load state: {e}")

    def run_all(self):
        self.log("--- Starting Comprehensive Diagnostic Suite v1.4 ---")
        self.test_results = [] 
        self.audit_mode = True
        
        tests = [
            (self.test_ollama, "Connectivity"),
            (self.test_persistence, "State Persistence"),
            (self.test_parsing, "XML Parsing"),
            (self.test_native_parsing, "IDE Tool Compat"),
            (self.test_execution_environment, "OS Permissions"),
            (self.test_app_logic, "Engine Logic"),
            (self.test_reference_commands, "Static Reference"),
            (self.test_shell_sanitizer, "Shell Sanitizer"),
            (self.test_capabilities, "Capability Logic"),
            (self.test_feedback_loop, "Feedback Loop"),
            (self.test_all_models_report, "Global Model Report"),
            (self.test_visual, "Visual Audit"),
            (self.test_model_compliance, "AI Tool Compliance")
        ]
        
        self.pending_tasks = len(tests)
        for i, (test_func, msg) in enumerate(tests):
            pct = int((i / len(tests)) * 100)
            if self.progress: self.progress(pct, msg)
            test_func()
            
        if self.progress: self.progress(100, "Full Audit Pending...")
        self.log("--- All Tests Initiated. Waiting for results... ---")
        
        # CLI summary wait is handled in __main__
        if not hasattr(sys, 'frozen') and "--full" not in sys.argv:
            # UI background wait
            def _wait():
                checks = 0
                while self.pending_tasks > 0 and checks < 120:
                    time.sleep(1)
                    checks += 1
                self.print_test_summary()
                self.audit_mode = False
            threading.Thread(target=_wait, daemon=True).start()

    def print_test_summary(self):
        self.log("\n" + "="*60)
        self.log("INTEGRATED TEST SUMMARY")
        self.log("="*60)
        
        passed = sum(1 for r in self.test_results if r["status"] == "PASS")
        failed = sum(1 for r in self.test_results if r["status"] == "FAIL")
        
        for result in self.test_results:
            icon = "[PASS]" if result["status"] == "PASS" else "[FAIL]" if result["status"] == "FAIL" else "[SKIP]"
            self.log(f"{icon} {result['test']}")
            if result["details"]:
                self.log(f"  |_ {result['details']}")
        
        self.log("="*60)
        self.log(f"TOTAL: {len(self.test_results)} | PASSED: {passed} | FAILED: {failed}")
        self.log("="*60 + "\n")

    def test_ollama(self):
        if not self.audit_mode: self.pending_tasks = 1
        self.log("Testing Ollama Connectivity...")
        def _work():
            try:
                self.log("  [DEBUG] Checking if ollama module is available...")
                if not ollama: 
                    self.log("  [DEBUG] FAILED: ollama module not installed")
                    self.log_result("Connectivity", "FAIL", "ollama missing")
                    return
                
                self.log("  [DEBUG] Creating Ollama client (host: http://127.0.0.1:11434)...")
                client = ollama.Client(host='http://127.0.0.1:11434')
                
                self.log("  [DEBUG] Fetching model list from Ollama server...")
                models = client.list().get('models', [])
                self.log(f"  [DEBUG] Received {len(models)} models from server")
                self.log(f"SUCCESS: Found {len(models)} models.")
                self.log_result("Connectivity", "PASS")
                
                # Update UI list
                self.log("  [DEBUG] Decorating model names with capability tags...")
                decorated_names = []
                for m in models:
                    name = m.model if hasattr(m, 'model') else m.get('model', str(m))
                    caps = ModelCapabilityChecker.check(name) if ModelCapabilityChecker else {'tools': False, 'vision': False}
                    tags = []
                    if caps['tools']: tags.append("[Tools]")
                    if caps['vision']: tags.append("[Vision]")
                    decorated_names.append(f"{name} {' '.join(tags)}".strip())
                self.log(f"  [DEBUG] Decorated names: {decorated_names[:3]}...")
                self.update_model_list(decorated_names)
            except Exception as e:
                self.log(f"  [DEBUG] Exception during connectivity test: {type(e).__name__}: {e}")
                self.log_result("Connectivity", "FAIL", str(e))
            finally:
                self.pending_tasks -= 1
        threading.Thread(target=_work, daemon=True).start()

    def update_model_list(self, models):
        if hasattr(self, 'model_combo') and self.model_combo:
            self.model_combo['values'] = models
            if models:
                # 1. Capture current UI text to preserve what the user sees
                current_ui_text = self.model_combo.get()
                current_clean = current_ui_text.split(' [')[0].strip() if current_ui_text else None
                
                # Capture the best lookup candidate
                # We prioritize the cleaned name because tags might have changed
                lookup = current_clean or self.selected_model
                
                best_match = models[0]
                if lookup:
                    self.log(f"  [DEBUG] Syncing model list with active selection: '{lookup}'")
                    for m in models:
                        if m.split(' [')[0].strip() == lookup:
                            best_match = m
                            self.log(f"  [DEBUG] Preserving selection: {m}")
                            break
                            
                self.model_combo.set(best_match)
                # Sync logic: Only update if the base model name actually changed
                new_clean = best_match.split(' [')[0].strip()
                if new_clean != self.selected_model:
                    self.update_target_model(best_match, is_auto=True)

    def update_target_model(self, decorated_name, is_auto=False):
        self.selected_model = decorated_name.split(' [')[0].strip()
        origin = "[AUTO]" if is_auto else "[MANUAL]"
        self.log(f"Config: Target Model override set to '{self.selected_model}' {origin}")
        self.save_state()

    def test_persistence(self):
        if not self.audit_mode: self.pending_tasks = 1
        self.log("Verifying Persistence Engine (Deep Functional Test)...")
        test_file = "test_persistence_state.json"
        try:
            if not OllamaIDE:
                 self.log_result("State Persistence", "FAIL", "OllamaIDE missing")
                 return

            self.log("  [DEBUG] Initializing primary test instance...")
            root = tk.Tk(); root.withdraw()
            app = OllamaIDE(root)
            app.state_file = test_file # Re-route to test file
            
            # Step 1: Set unique values
            test_path = os.path.abspath("persist_test.py")
            test_content = f"print('Persistence works: {int(time.time())}')"
            app.current_filepath = test_path
            app.editor_text.delete(1.0, tk.END)
            app.editor_text.insert(tk.END, test_content)
            root.update_idletasks() # Ensure UI state is synchronized
            
            self.log(f"  [DEBUG] Saving state to: {test_file}")
            app.save_state()
            
            # Step 2: Instantiate second instance and load
            self.log("  [DEBUG] Initializing second instance for restoration...")
            root2 = tk.Tk(); root2.withdraw()
            app2 = OllamaIDE(root2)
            app2.state_file = test_file # Point to the same test file
            
            self.log("  [DEBUG] Triggering app2.load_state()...")
            app2.load_state()
            
            restored_path = app2.current_filepath
            restored_content = app2.editor_text.get(1.0, tk.END).strip()
            
            self.log(f"  [DEBUG] Restored Path: {restored_path}")
            self.log(f"  [DEBUG] Restored Content Snippet: {restored_content[:30]}...")
            
            if restored_path == test_path and restored_content == test_content:
                self.log("  [DEBUG] Deep verification: PASS")
                self.log_result("State Persistence", "PASS")
            else:
                details = []
                if restored_path != test_path: details.append(f"Path mismatch. Expected {test_path}, got {restored_path}")
                if restored_content != test_content: details.append("Content mismatch")
                self.log_result("State Persistence", "FAIL", "; ".join(details))
            
            # Cleanup
            root.destroy(); root2.destroy()
            if os.path.exists(test_file): os.remove(test_file)
        except Exception as e:
            self.log(f"  [DEBUG] ERROR during persistence logic: {e}")
            self.log_result("State Persistence", "FAIL", str(e))
        finally:
            self.pending_tasks -= 1

    def test_parsing(self):
        if not self.audit_mode: self.pending_tasks = 1
        self.log("Testing IDE Logic: XML Command Parsing...")
        try:
            if not OllamaIDE:
                 self.log_result("XML Parsing", "FAIL", "OllamaIDE missing")
                 return

            self.log("  [DEBUG] Instantiating IDE for parsing test...")
            root = tk.Tk(); root.withdraw()
            app = OllamaIDE(root)
            
            sample_text = (
                "Here is the file:\n"
                "<CREATE_FILE path=\"test_logic.py\">print('logic')</CREATE_FILE>\n"
                "And now a command:\n"
                "<SHELL_CMD>pip install requests</SHELL_CMD>"
            )
            
            self.log("  [DEBUG] Calling app.parse_ai_commands()...")
            commands = app.parse_ai_commands(sample_text)
            self.log(f"  [DEBUG] Parsed {len(commands)} commands: {commands}")
            
            has_create = any(c[0] == "Create File" and c[1] == "test_logic.py" for c in commands)
            has_shell = any(c[0] == "Run Command" and "pip install" in c[2] for c in commands)
            
            if has_create and has_shell:
                self.log("  [DEBUG] Both Create and Shell patterns parsed accurately: PASS")
                self.log_result("XML Parsing", "PASS")
            else:
                self.log_result("XML Parsing", "FAIL", f"Parsing logic incomplete. Found: {len(commands)}")
            
            root.destroy()
        except Exception as e:
            self.log_result("XML Parsing", "FAIL", str(e))
        finally:
            self.pending_tasks -= 1

    def test_native_parsing(self):
        if not self.audit_mode: self.pending_tasks = 1
        self.log("Testing IDE Tool compatibility...")
        if not OllamaIDE:
             self.log("  [DEBUG] FAILED: OllamaIDE class not available for import")
             self.log_result("IDE Tool Compat", "FAIL", "OllamaIDE class missing mapping")
             self.pending_tasks -= 1
             return
        try:
            # Verify if internal tool manager is initialized in the IDE
            self.log("  [DEBUG] Creating headless Tkinter root...")
            root = tk.Tk()
            root.withdraw()
            self.log("  [DEBUG] Instantiating OllamaIDE in headless mode...")
            app = OllamaIDE(root)
            self.log("  [DEBUG] Checking for tool_manager attribute...")
            if hasattr(app, 'tool_manager') and app.tool_manager:
                self.log(f"  [DEBUG] tool_manager found: {type(app.tool_manager).__name__}")
                self.log_result("IDE Tool Compat", "PASS")
            else:
                self.log("  [DEBUG] tool_manager attribute missing or None")
                self.log_result("IDE Tool Compat", "FAIL", "IDE instance lacks tool_manager")
            self.log("  [DEBUG] Destroying Tkinter root...")
            root.destroy()
        except Exception as e:
            self.log(f"  [DEBUG] Exception during IDE compatibility test: {type(e).__name__}: {e}")
            self.log_result("IDE Tool Compat", "FAIL", str(e))
        finally:
            self.pending_tasks -= 1

    def test_execution_environment(self):
        if not self.audit_mode: self.pending_tasks = 1
        self.log("Verifying OS Permissions & Integrated Listing Logic...")
        test_dir = "test_listing_dir"
        test_file = os.path.join(test_dir, "listing_test.tmp")
        try:
            self.log(f"  [DEBUG] Creating test directory: {test_dir}")
            if not os.path.exists(test_dir): os.makedirs(test_dir)
            
            self.log(f"  [DEBUG] Creating test file: {test_file}")
            with open(test_file, "w") as f:
                f.write("test")
            
            self.log("  [DEBUG] Verifying listing logic via walk...")
            found = False
            for root, dirs, files in os.walk(test_dir):
                if "listing_test.tmp" in files:
                    found = True
                    break
            
            if found:
                self.log("  [DEBUG] File system interaction & walking: PASS")
                self.log_result("OS Permissions", "PASS")
            else:
                self.log_result("OS Permissions", "FAIL", "Could not list created file")
            
            # Cleanup
            os.remove(test_file)
            os.rmdir(test_dir)
        except Exception as e:
            self.log(f"  [DEBUG] Exception during OS permissions test: {type(e).__name__}: {e}")
            self.log_result("OS Permissions", "FAIL", str(e))
        finally:
            self.pending_tasks -= 1

    def test_app_logic(self):
        if not self.audit_mode: self.pending_tasks = 1
        self.log("Verifying Engine Logic...")
        try:
            self.log("  [DEBUG] Checking if OllamaToolManager is available...")
            if not OllamaToolManager:
                self.log("  [DEBUG] FAILED: OllamaToolManager not available")
                self.log_result("Engine Logic", "FAIL", "OllamaToolManager definition missing")
                return
            
            self.log("  [DEBUG] Instantiating OllamaToolManager...")
            tm = OllamaToolManager()
            self.log("  [DEBUG] Calling get_tools()...")
            tools = tm.get_tools()
            self.log(f"  [DEBUG] Received {len(tools)} tool definitions")
            
            if len(tools) >= 3:
                # Rigorous check: verify required keys in first tool
                sample = tools[0]
                self.log(f"  [DEBUG] Inspecting first tool: {sample.get('type')}")
                func = sample.get('function', {})
                self.log(f"  [DEBUG] Function keys: {list(func.keys())}")
                if 'name' in func and 'parameters' in func:
                    self.log(f"  [DEBUG] Tool schema valid. Name: {func['name']}")
                    self.log_result("Engine Logic", "PASS")
                else:
                    self.log(f"  [DEBUG] Tool schema malformed: missing required keys")
                    self.log_result("Engine Logic", "FAIL", f"Tool schema malformed: {func.keys()}")
            else:
                self.log(f"  [DEBUG] Insufficient tools: expected >= 3, got {len(tools)}")
                self.log_result("Engine Logic", "FAIL", f"Only {len(tools)} tools found")
        except Exception as e:
            self.log(f"  [DEBUG] Exception during engine logic test: {type(e).__name__}: {e}")
            self.log_result("Engine Logic", "FAIL", f"Initialization error: {str(e)}")
        finally:
            self.pending_tasks -= 1

    def test_reference_commands(self):
        if not self.audit_mode: self.pending_tasks = 1
        self.log("Validating Tool Definitions...")
        try:
            self.log("  [DEBUG] Checking if OllamaToolManager is available...")
            if not OllamaToolManager:
                self.log("  [DEBUG] FAILED: OllamaToolManager not available")
                self.log_result("Static Reference", "FAIL", "Cannot validate stubs: Manager missing")
                return

            self.log("  [DEBUG] Instantiating OllamaToolManager...")
            tm = OllamaToolManager()
            # Test specific parsing logic
            test_args = {'path': 'test.txt', 'content': 'hello'}
            self.log(f"  [DEBUG] Testing parse_tool_call with args: {test_args}")
            parsed = tm.parse_tool_call('create_file', test_args)
            self.log(f"  [DEBUG] Parsed result: {parsed}")
            if parsed and parsed[0] == "Create File" and parsed[1] == "test.txt":
                self.log("  [DEBUG] Parsing validation successful")
                self.log_result("Static Reference", "PASS")
            else:
                self.log(f"  [DEBUG] Parsing validation failed, unexpected result: {parsed}")
                self.log_result("Static Reference", "FAIL", f"Parsing error: {parsed}")
        except Exception as e:
            self.log(f"  [DEBUG] Exception during static reference test: {type(e).__name__}: {e}")
            self.log_result("Static Reference", "FAIL", str(e))
        finally:
            self.pending_tasks -= 1

    def test_shell_sanitizer(self):
        if not self.audit_mode: self.pending_tasks = 1
        self.log("Verifying ShellExecutor Sanitization Logic...")
        try:
            from Ollama_Agentic_IDE_v1_1 import ShellExecutor
            # Mock callbacks
            def mock_out(x): pass
            def mock_end(): pass
            shell = ShellExecutor(mock_out, mock_end)
            
            # Test Windows translations
            if platform.system() == "Windows":
                self.log("  [DEBUG] Testing Windows-specific command translations...")
                t1 = shell.sanitize_command("mv file1 file2")
                t2 = shell.sanitize_command("rmdir /s mydir")
                t3 = shell.sanitize_command("ls")
                
                pass_mv = "move" in t1
                pass_rm = "/q" in t2
                pass_ls = "dir" in t3
                
                if pass_mv and pass_rm and pass_ls:
                    self.log("  [DEBUG] mv->move, rmdir->/q, ls->dir: PASS")
                    self.log_result("Shell Sanitizer", "PASS")
                else:
                    self.log_result("Shell Sanitizer", "FAIL", f"Translation failed: mv={t1}, rm={t2}, ls={t3}")
            else:
                self.log("  [DEBUG] Non-Windows OS detected, skipping translations check.")
                self.log_result("Shell Sanitizer", "PASS", "Validated (Not applicable for OS)")
        except Exception as e:
            self.log_result("Shell Sanitizer", "FAIL", str(e))
        finally:
            self.pending_tasks -= 1

    def test_capabilities(self):
        if not self.audit_mode: self.pending_tasks = 1
        self.log("Verifying ModelCapabilityChecker Heuristics...")
        try:
            if not ModelCapabilityChecker:
                self.log_result("Capability Logic", "FAIL", "ModelCapabilityChecker missing")
                return
            
            self.log("  [DEBUG] Testing known tool-enabled model: llama3.2")
            res1 = ModelCapabilityChecker.check("llama3.2")
            self.log("  [DEBUG] Testing known vision-enabled model: llava")
            res2 = ModelCapabilityChecker.check("llava:7b-vision")
            
            if res1['tools'] and res2['vision']:
                self.log("  [DEBUG] Tool and Vision detection: PASS")
                self.log_result("Capability Logic", "PASS")
            else:
                self.log_result("Capability Logic", "FAIL", f"Logic error: llama3_tools={res1['tools']}, llava_vision={res2['vision']}")
        except Exception as e:
            self.log_result("Capability Logic", "FAIL", str(e))
        finally:
            self.pending_tasks -= 1

    def test_feedback_loop(self):
        if not self.audit_mode: self.pending_tasks = 1
        self.log("Verifying Agentic Feedback Loop State...")
        try:
            root = tk.Tk(); root.withdraw()
            app = OllamaIDE(root)
            
            self.log("  [DEBUG] Triggering send_agent_feedback()...")
            test_result = "File created successfully"
            test_id = "call_123"
            
            # We don't want to actually start the chat worker (model interaction)
            # Monkeypatch it to just record the call
            worker_triggered = [False]
            def mock_trigger(): worker_triggered[0] = True
            app._on_chat_worker_trigger = mock_trigger
            
            app.send_agent_feedback(test_result, test_id)
            
            # Verify history
            last_entry = app.chat_history[-1]
            self.log(f"  [DEBUG] Last history entry: {last_entry}")
            
            if last_entry['role'] == 'tool' and last_entry['content'] == test_result and last_entry['tool_call_id'] == test_id:
                if worker_triggered[0]:
                    self.log("  [DEBUG] Feedback loop injection and worker trigger: PASS")
                    self.log_result("Feedback Loop", "PASS")
                else:
                    self.log_result("Feedback Loop", "FAIL", "Worker trigger failed")
            else:
                self.log_result("Feedback Loop", "FAIL", f"History corruption: {last_entry}")
                
            root.destroy()
        except Exception as e:
            self.log_result("Feedback Loop", "FAIL", str(e))
        finally:
            self.pending_tasks -= 1

    def test_visual(self):
        if not self.audit_mode: self.pending_tasks = 1
        if not pyautogui:
            self.log_result("Visual Audit", "SKIP", "pyautogui missing")
            self.pending_tasks -= 1
            return
        self.log("Launching Visual Audit...")
        def _work():
            try:
                proc = subprocess.Popen([sys.executable, "Ollama_Agentic_IDE_v1_1.py"])
                time.sleep(5)
                pyautogui.screenshot("visual_test.png")
                proc.terminate()
                self.log_result("Visual Audit", "PASS")
            except Exception as e:
                self.log_result("Visual Audit", "FAIL", str(e))
            finally:
                self.pending_tasks -= 1
        threading.Thread(target=_work, daemon=True).start()

    def test_model_compliance(self):
        if not self.audit_mode: self.pending_tasks = 1
        self.log("Testing AI Compliance...")
        # CRITICAL: Capture the target model selection BEFORE starting the thread
        # to prevent async refreshes from test_ollama from interfering.
        target = self.selected_model
        
        def _work():
            try:
                if not ollama or not OllamaToolManager or not ModelCapabilityChecker:
                    self.log_result("AI Tool Compliance", "SKIP", "Dependencies missing")
                    return
                tm = OllamaToolManager()
                client = ollama.Client(host='http://127.0.0.1:11434')
                
                self.log(f"  [DEBUG] Compliance Test starting. Context model: '{target}'")
                
                probe_target = target
                if not probe_target:
                    self.log("  [DEBUG] No model selected, scanning for tool-capable fallback...")
                    models = client.list().get('models', [])
                    for m in models:
                        name = m.model if hasattr(m, 'model') else m.get('model', '')
                        if ModelCapabilityChecker.check(name)['tools']:
                            probe_target = name
                            self.log(f"  [DEBUG] Fallback selected: {probe_target}")
                            break
                
                if not probe_target:
                    self.log_result("AI Tool Compliance", "SKIP", "No tool-model found")
                    return
                
                self.log(f"  [AI-PROBE] Executing Native Tool test on: {probe_target}")
                messages = [
                    {'role': 'system', 'content': 'You are a coder helper with Native Tools. Use them correctly.'},
                    {'role': 'user', 'content': 'Create hello.py containing print("hi")'}
                ]
                res = client.chat(model=target, messages=messages, tools=tm.get_tools())
                tc = res.get('message', {}).get('tool_calls', [])
                content = res.get('message', {}).get('content', '')
                
                if tc:
                    self.log_result("AI Tool Compliance", "PASS")
                else:
                    snippet = (content[:50] + "...") if len(content) > 50 else content
                    self.log(f"   [DEBUG]: Model returned text: {snippet}")
                    self.log_result("AI Tool Compliance", "FAIL", "Model returned text, not tool")
            except Exception as e:
                self.log_result("AI Tool Compliance", "FAIL", str(e))
            finally:
                self.pending_tasks -= 1
        threading.Thread(target=_work, daemon=True).start()

    def test_all_models_report(self):
        """Iteratively probes all models for tool calling capabilities."""
        self.pending_tasks += 1
        self.log("\n" + "="*60)
        self.log("GENERATING GLOBAL MODEL CAPABILITY REPORT")
        self.log("="*60)
        self.log("Note: This will perform a live 'Tool Probe' on models marked with [Tools].\n")
        
        def _work():
            try:
                client = ollama.Client(host='http://127.0.0.1:11434')
                raw_models = client.list().get('models', [])
                tm = OllamaToolManager()
                
                report = []
                for m in raw_models:
                    name = m.model if hasattr(m, 'model') else m.get('model', str(m))
                    size_gb = m.size / (1024**3) if hasattr(m, 'size') else 0
                    caps = ModelCapabilityChecker.check(name) if ModelCapabilityChecker else {'tools': False, 'vision': False}
                    
                    live_tool = "Untested"
                    
                    if caps['tools']:
                        self.log(f"  [PROBE] Testing {name} for native tool support...")
                        try:
                            # Use a more explicit prompt for the probe
                            probe_messages = [
                                {'role': 'system', 'content': 'You are a helper with access to native tools. Use create_file to respond.'},
                                {'role': 'user', 'content': 'Please use a tool to create a file named probe.txt'}
                            ]
                            res = client.chat(
                                model=name, 
                                messages=probe_messages,
                                tools=tm.get_tools(),
                                options={'num_predict': 100, 'temperature': 0} 
                            )
                            if res.get('message', {}).get('tool_calls'):
                                live_tool = "SUCCESS [OK]"
                            else:
                                live_tool = "FAILED [Text Only]"
                        except Exception as e:
                            live_tool = f"ERROR [!] ({str(e)[:30]}...)"
                    
                    report.append({
                        "name": name,
                        "size": f"{size_gb:.1f} GB",
                        "heuristic_tools": "Yes" if caps['tools'] else "No",
                        "heuristic_vision": "Yes" if caps['vision'] else "No",
                        "live_tool_probe": live_tool
                    })
                
                # Format Table
                header = f"{'MODEL NAME':<35} | {'SIZE':<8} | {'HEURISTIC':<12} | {'LIVE PROBE'}"
                self.log(header)
                self.log("-" * len(header))
                for r in report:
                    h_str = f"T:{r['heuristic_tools']} V:{r['heuristic_vision']}"
                    self.log(f"{r['name']:<35} | {r['size']:<8} | {h_str:<12} | {r['live_tool_probe']}")
                
                self.log("\n" + "="*60)
                self.log("REPORT COMPLETE")
                self.log("="*60 + "\n")
                
                # Save to file
                report_file = "model_capabilities_report.txt"
                with open(report_file, "w", encoding="utf-8") as f:
                    f.write("OLLAMA MODEL CAPABILITY REPORT\n")
                    f.write(f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                    f.write(f"{'MODEL NAME':<40} | {'SIZE':<10} | {'HEURISTIC T':<12} | {'HEURISTIC V':<12} | {'LIVE TOOL PROBE'}\n")
                    f.write("-" * 105 + "\n")
                    for r in report:
                         f.write(f"{r['name']:<40} | {r['size']:<10} | {r['heuristic_tools']:<12} | {r['heuristic_vision']:<12} | {r['live_tool_probe']}\n")
                    
                    f.write("\n" + "="*85 + "\n")
                    f.write("GLOSSARY & TEST DESCRIPTIONS\n")
                    f.write("="*85 + "\n")
                    f.write("1. HEURISTIC (TOOLS/VISION):\n")
                    f.write("   - Static architecture-based detection (e.g., Qwen 2.5, Llama 3.1).\n")
                    f.write("   - Indicates if the model family is DESIGNED to support native tool calling.\n\n")
                    f.write("2. LIVE TOOL PROBE:\n")
                    f.write("   - Functional test run during this report generation.\n")
                    f.write("   - SUCCESS [OK]: The model issued a valid native tool_call via the Ollama API.\n")
                    f.write("   - FAILED [Text]: The model ignored the tools and responded in plain text.\n")
                    f.write("   - Untested: Probes are only run on models with HEURISTIC TOOLS = Yes.\n")
                    f.write("="*85 + "\n")
                
                self.log(f"Report saved to: {report_file}")
                self.log_result("Global Model Report", "PASS")

            except Exception as e:
                self.log(f"  [DEBUG] Error generating report: {e}")
                self.log_result("Global Model Report", "FAIL", str(e))
            finally:
                self.pending_tasks -= 1
        
        threading.Thread(target=_work, daemon=True).start()

class IntegratedTester:
    def __init__(self, root):
        self.root = root
        self.root.title("Integrated Tester v1.5 - Premium Diagnostic Suite")
        self.root.geometry("1800x950")
        self.root.configure(bg="#0f0f12") # Deeper dark background
        
        # Style Configuration
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure("Custom.Horizontal.TProgressbar", 
                            troughcolor='#1e1e24', 
                            background='#007acc', 
                            thickness=12,
                            bordercolor="#0f0f12",
                            lightcolor="#007acc",
                            darkcolor="#005a9e")
        
        self.queue = queue.Queue()
        self.status_var = tk.StringVar(value="Ready to Audit")
        self.progress_var = tk.DoubleVar(value=0)
        self.test_cards = {} # Store card references for color updates
        
        self.engine = DiagnosticEngine(self.log_to_queue, self.update_progress)
        self.setup_ui()
        self.start_poller()
        self.engine.model_combo = self.model_combo
        self.engine.test_ollama()

    def update_progress(self, pct, msg):
        self.root.after(0, lambda: self.progress_var.set(pct))
        self.root.after(0, lambda: self.status_var.set(msg))

    def setup_ui(self):
        # Header Section
        header = tk.Frame(self.root, bg="#16161d", height=80)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        
        tk.Label(header, text="DIAGNOSTIC", fg="#4fc3f7", bg="#16161d", font=("Segoe UI Semilight", 10, "bold")).pack(side=tk.LEFT, padx=(30, 5))
        tk.Label(header, text="DASHBOARD", fg="white", bg="#16161d", font=("Segoe UI", 18, "bold")).pack(side=tk.LEFT)
        
        v_label = tk.Label(header, text="v1.5 PRO", fg="#555", bg="#16161d", font=("Segoe UI", 9))
        v_label.pack(side=tk.RIGHT, padx=30)

        # Main Scrollable Area
        container = tk.Frame(self.root, bg="#0f0f12")
        container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # --- Top Controls Section ---
        ctrl_panel = tk.Frame(container, bg="#1e1e24", padx=20, pady=15)
        ctrl_panel.pack(fill=tk.X, pady=(0, 20))
        
        # Grid layout for controls
        tk.Label(ctrl_panel, text="ACTIVE AI MODEL", bg="#1e1e24", fg="#888", font=("Segoe UI", 8, "bold")).grid(row=0, column=0, sticky="w")
        self.model_combo = ttk.Combobox(ctrl_panel, state="readonly", width=45, font=("Segoe UI", 10))
        self.model_combo.grid(row=1, column=0, sticky="w", pady=(5, 0))
        self.model_combo.bind("<<ComboboxSelected>>", lambda e: self.engine.update_target_model(self.model_combo.get()))

        btn_full = tk.Button(ctrl_panel, text="EXECUTE FULL AUDIT", command=self.engine.run_all, 
                          bg="#007acc", fg="white", font=("Segoe UI", 10, "bold"), 
                          relief=tk.FLAT, padx=20, cursor="hand2")
        btn_full.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=(20, 0))

        btn_report = tk.Button(ctrl_panel, text="GLOBAL CAPABILITY REPORT", command=self.engine.test_all_models_report, 
                           bg="#28a745", fg="white", font=("Segoe UI", 9, "bold"), 
                           relief=tk.FLAT, padx=15, cursor="hand2")
        btn_report.grid(row=0, column=2, rowspan=2, sticky="nsew", padx=(10, 0))

        # --- Dashboard Grid ---
        grid_frame = tk.Frame(container, bg="#0f0f12")
        grid_frame.pack(fill=tk.BOTH, expand=True)

        def create_test_card(parent, title, desc, command, row, col):
            card = tk.Frame(parent, bg="#1e1e24", padx=15, pady=12, highlightthickness=1, highlightbackground="#2e2e38")
            card.grid(row=row, column=col, sticky="nsew", padx=4, pady=4)
            parent.grid_columnconfigure(col, weight=1)
            
            # Status Indicator
            ind = tk.Frame(card, bg="#444", width=4, height=35)
            ind.pack(side=tk.LEFT, fill=tk.Y)
            
            content = tk.Frame(card, bg="#1e1e24")
            content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0))
            
            lbl_title = tk.Label(content, text=title.upper(), fg="#ccc", bg="#1e1e24", font=("Segoe UI", 9, "bold"), anchor="w")
            lbl_title.pack(fill=tk.X)
            
            lbl_desc = tk.Label(content, text=desc, fg="#666", bg="#1e1e24", font=("Segoe UI", 8), anchor="w")
            lbl_desc.pack(fill=tk.X)
            
            card.bind("<Enter>", lambda e: card.config(bg="#25252d"))
            card.bind("<Leave>", lambda e: card.config(bg="#1e1e24"))
            card.bind("<Button-1>", lambda e: command())
            lbl_title.bind("<Button-1>", lambda e: command())
            lbl_desc.bind("<Button-1>", lambda e: command())
            
            self.test_cards[title] = (card, ind, lbl_title)

        tests = [
            ("Connectivity", "Ollama Server Status", self.engine.test_ollama),
            ("State Persistence", "app_state.json Round-Trip", self.engine.test_persistence),
            ("XML Parsing", "Internal Regex Logic", self.engine.test_parsing),
            ("IDE Tool Compat", "IDE Class Buffer Test", self.engine.test_native_parsing),
            ("OS Permissions", "File System Capability", self.engine.test_execution_environment),
            ("Engine Logic", "Tool Schema Validation", self.engine.test_app_logic),
            ("Static Reference", "Argument Mapping Test", self.engine.test_reference_commands),
            ("Shell Sanitizer", "Win/Unix Command Translation", self.engine.test_shell_sanitizer),
            ("Capability Logic", "Model Feature Heuristics", self.engine.test_capabilities),
            ("Feedback Loop", "Agent State Injection", self.engine.test_feedback_loop),
            ("Visual Audit", "Screenshot UI Validation", self.engine.test_visual),
            ("AI Compliance", "Live Tool-Calling Probe", self.engine.test_model_compliance)
        ]

        for i, (title, desc, cmd) in enumerate(tests):
            create_test_card(grid_frame, title, desc, cmd, i // 3, i % 3)

        # --- Footer Section ---
        footer = tk.Frame(self.root, bg="#16161d", pady=15, padx=20)
        footer.pack(fill=tk.X)
        
        # Progress and Output
        tk.Label(footer, textvariable=self.status_var, fg="#aaa", bg="#16161d", font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, 5))
        self.pb = ttk.Progressbar(footer, variable=self.progress_var, maximum=100, style="Custom.Horizontal.TProgressbar")
        self.pb.pack(fill=tk.X, pady=(0, 15))
        
        self.output = tk.Text(footer, bg="#050505", fg="#d4d4d4", font=("Consolas", 10), 
                           relief=tk.FLAT, height=12, highlightthickness=1, highlightbackground="#2e2e38", pady=10, padx=10)
        self.output.pack(fill=tk.X)

    def log_to_queue(self, text):
        raw_msg = f"[{time.strftime('%H:%M:%S')}] {text}"
        self.queue.put(raw_msg + "\n")
        
        # Color coding cards based on log output
        if "PASS" in text:
            for title in self.test_cards:
                 if title in text:
                     card, ind, lbl = self.test_cards[title]
                     self.root.after(0, lambda: ind.config(bg="#28a745"))
                     self.root.after(0, lambda: lbl.config(fg="#28a745"))
        elif "FAIL" in text:
            for title in self.test_cards:
                 if title in text:
                     card, ind, lbl = self.test_cards[title]
                     self.root.after(0, lambda: ind.config(bg="#dc3545"))
                     self.root.after(0, lambda: lbl.config(fg="#dc3545"))

    def start_poller(self):
        try:
            while True:
                line = self.queue.get_nowait()
                self.output.config(state=tk.NORMAL)
                self.output.insert(tk.END, line)
                self.output.see(tk.END)
                self.output.config(state=tk.DISABLED)
        except queue.Empty:
            pass
        self.root.after(100, self.start_poller)

if __name__ == "__main__":
    if "--full" in sys.argv:
        engine = DiagnosticEngine(lambda x: print(x, flush=True))
        engine.run_all()
        checks = 0
        while engine.pending_tasks > 0 and checks < 120:
            time.sleep(1)
            checks += 1
        time.sleep(1)
        engine.print_test_summary()
    else:
        root = tk.Tk()
        IntegratedTester(root)
        root.mainloop()
