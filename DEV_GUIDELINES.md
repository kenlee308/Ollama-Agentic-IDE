# Ollama IDE Development Guidelines
**Source of Truth for AI Agent Decision-Making**

This document defines the exact goals, requirements, and protocols for the Ollama IDE ecosystem. Every programming decision by an AI Agent must align with these specifications.

---

## 0. Executive Summary: System Goals

### A. Ollama Agentic IDE (`Ollama_Agentic_IDE_v1_1.py`)
**Primary Goal**: Provide a transparent, local-first agentic coding assistant that executes AI-generated file operations and shell commands through native tool calling.

**Core Functions**:
- **AI Chat Interface**: Multi-turn conversations with local Ollama models
- **Native Tool Execution**: Create files, delete files, run shell commands, list directories
- **File Editing**: Built-in code editor with syntax awareness
- **Attachment System**: Context injection via file uploads and vision API
- **State Persistence**: Automatic save/restore of all UI state via `app_state.json`
- **Model Capability Detection**: Auto-detect and display tool/vision support per model
- **Auto-Approve Mode**: Optional bypass of confirmation dialogs for trusted workflows
- **Agentic Loop**: Automatic tool result feedback to enable multi-step reasoning

### B. Integrated Tester (`Integrated_Tester_v1_1.py`)
**Primary Goal**: Serve as an independent, headless-capable auditor that verifies IDE functionality, Ollama connectivity, and AI tool compliance.

**Core Functions**:
- **12+ Component Tests**: Connectivity, Persistence, Parsing, Tool Compat, OS Permissions, Engine Logic, Static Reference, Shell Sanitizer, Capability Logic, Feedback Loop, Visual Audit, AI Compliance.
- **Deep Functional Verification**: Performs multi-instance state round-trips and live tool-calling probes.
- **Global Model Reporting**: Iteratively audits all local models to generate a `model_capabilities_report.txt` covering native tool support and vision.
- **Headless CLI Mode**: Run full audit via `--full` flag without GUI.
- **Task-Based Orchestration**: Uses `pending_tasks` for reliable async synchronization.

---

## 1. The Logical Update Order

To maintain stability and testability, changes **MUST** strictly follow this sequence:

1.  **Core Application** (`Ollama_Agentic_IDE_v1_1.py`)
    *   Implement the feature, bug fix, or refactor.
    *   Ensure no syntax errors before proceeding.

2.  **Test Infrastructure** (`Integrated_Tester_v1_1.py`)
    *   **Stub Updates**: If you added/changed UI methods (e.g., `open_file`, `messagebox`), you **MUST** update the test stubs in `Integrated_Tester` immediately. Failure to do this will break the automated suite.
    *   **New Tests**: Add specific logic tests for your new feature in `test_app_logic`.
    *   **Run Audit**: Execute `python Integrated_Tester_v1_1.py --full` to verify.

3.  **Documentation** (`README.md`, `TECHNICAL_SPECS.md`, etc.)
    *   Update user-facing docs to reflect new capabilities.
    *   Update this file (`DEV_GUIDELINES.md`) if protocols change.

---

## 2. Dependency Map

Be aware of these critical relationships to avoid regression:

| Component | Responsibility | Relationships |
| :--- | :--- | :--- |
| **`Ollama_Agentic_IDE_v1_1.py`** | **The Core**. UI, Logic, AI Client. | Reads/Writes `app_state.json`. |
| **`Integrated_Tester_v1_1.py`** | **The Verifier**. Runs Logic, Visual, Unit, and **Multi-OS AI Compliance** tests. | Imports `Ollama_Agentic_IDE_v1_1`. Mocks UI classes. |
| **`app_state.json`** | **Single Source of Truth**. Persists all data. | Shared by App and Tester to verify persistence. |
| **`tests/`** | **Code Unit Tests**. Low-level checks. | Executed as subprocesses by the Tester. |

---

## 3. Backup Protocol

### 3.1 Regular Backup
Before any "Destructive" or "Complex" refactor (e.g., changing the threading model, rewriting the AI loop), follow this backup process:

1.  **Locate**: Go to the `backup/` directory.
2.  **Snapshot**: Copy the *working* file (`Ollama_Agentic_IDE_v1_1.py` or `Integrated_Tester_v1_1.py`).
3.  **Name**: Save it as `[FILENAME]_backup_[DATE]_[REASON].py`.
    *   *Example*: `Ollama_Agentic_IDE_v1_1_backup_20260128_pre_async_refactor.py`

### 3.2 Full Version Snapshots
When a major milestone (e.g., v1.5 PRO) is reached, a coordinated backup of all core files is required:
1.  **Identify**: Group all core files (`App`, `Tester`, `Guidelines`).
2.  **Tag**: Use a consistent version tag (e.g., `v1.5_PRO`) in the filename.
3.  **Execute**: Copy all files to `backup/` using the format: `[FILENAME]_backup_[DATE]_[VERSION_TAG].extension`.

### 3.3 Consolidated Snapshots
For portable archival, all core components can be combined into a single `.py` or `.txt` file:
1.  **Format**: Start with an index/header, followed by each file wrapped in distinct comment/string delimiters.
2.  **Naming**: `IDE_TESTER_GUIDELINES_[VERSION]_[DATE]_COMBINED.py`.
3.  **Content**: Include `Ollama_Agentic_IDE`, `Integrated_Tester`, and `DEV_GUIDELINES`.

*Note: For minor tweaks or UI text changes, regular backup steps can be skipped.*

---

## 4. IDE Functional Requirements

### 4.1 Required UI Components

#### Main Window
- **Title**: "Ollama Agentic IDE v1.1" (or current version)
- **Layout**: 3-panel design (Editor | Console | Sidebar)
- **Resizable**: User can adjust panel sizes
- **Background**: Dark theme (`#1e1e1e` for frames)

#### Top Toolbar
- **Model Selector** (`ttk.Combobox`): Displays all available models with `[Tools]` and `[Vision]` tags
- **Auto-Approve Toggle** (`tk.Checkbutton`): Enables/disables automatic tool execution
- **Attach File Button**: Opens file picker for context injection
- **Send Button**: Submits user input to AI

#### Code Editor Panel
- **Text Widget**: Multi-line editor with syntax highlighting hooks
- **File Name Label**: Displays currently loaded file path
- **Save Button**: Writes editor content to disk

#### Console Panel
- **Output Text Widget**: Displays AI responses, tool execution logs, errors
- **Auto-scroll**: Always shows most recent output
- **Color-coded**: AI responses in white, tool logs in cyan, errors in red

#### Sidebar (File Explorer)
- **Listbox**: Shows files in current working directory
- **Icons**: `📄` for files, `📁` for directories
- **Double-click**: Opens file in editor

### 4.2 Required Core Methods

#### `__init__(self, root)`
**Purpose**: Initialize IDE instance  
**Behavior**:
- Create all UI components
- Load `app_state.json` if exists
- Initialize `OllamaToolManager`
- Restore previous OS selection, model, and auto-approve state
- **Restore Chat History**: Re-populate the chat window with the full conversation log from `app_state.json`.

#### `send_chat(self)`
**Purpose**: Send user input to Ollama model  
**Inputs**: User message from input field, editor content (if "Include Editor Content" is checked), attachments  
**Outputs**: Streams AI response to console  
**Side Effects**:
- Appends user message to `chat_history`
- Calls `_ollama_worker` in background thread
- Clears input field

#### `send_agent_feedback(self, result_text, tool_call_id=None)`
**Purpose**: Feed tool execution results back to AI  
**Inputs**: Result string from tool execution, optional tool_call_id  
**Outputs**: None  
**Side Effects**:
- Appends `role: 'tool'` message to `chat_history`
- Triggers new AI call in background

#### `execute_one_command(self, type, path, data)`
**Purpose**: Execute a single AI-suggested tool call  
**Inputs**: Type ("Create File", "Delete File", "Run Command", "List Files"), path (if applicable), data (content or command)  
**Outputs**: Success/failure message string  
**Side Effects**:
- Creates/deletes files on disk
- Executes shell commands via `ShellExecutor`
- Updates file sidebar
- Returns result for agentic feedback

#### `save_state(self)`
**Purpose**: Persist UI state to disk  
**Inputs**: None  
**Outputs**: None  
**Side Effects**:
- Writes JSON to `app_state.json` with: model, os_type, auto_approve, chat_history
- **CRITICAL**: Must be called immediately whenever the Model Selector or OS Profile is changed.

### 4.3 Tool Execution Rules
1. **Validation First**: Check for empty `path` or `content` before OS operations
2. **User Confirmation**: Show approval dialog unless auto-approve is enabled
3. **Directory Creation**: Auto-create parent directories for new files
4. **Error Handling**: Log errors to console, do NOT crash the app
5. **Feedback Loop**: Always return execution result for agent loop

---

## 5. Tester Functional Requirements

### 5.1 Mandatory Test Suite (12+ Checks)
The tester MUST perform deep logical verification, not just presence checks:

#### Test 1: Connectivity (`test_ollama`)
- **Action**: Verifies Ollama API reachability.
- **Success**: Model list retrieved successfully.

#### Test 2: State Persistence (`test_persistence`)
- **Action**: Performs a **Deep Round-Trip**. Sets unique text/path in instance A, saves to a test file, loads in instance B.
- **Success**: Bit-perfect restoration of content and paths.

#### Test 3: XML Parsing (`test_parsing`)
- **Action**: Directly exercises `OllamaIDE.parse_ai_commands` with complex multi-tag samples.
- **Success**: Accurate extraction of all tag contents.

#### Test 4: Shell Sanitizer (`test_shell_sanitizer`)
- **Action**: Verifies `ShellExecutor` correctly translates Windows/Linux commands (e.g., `mv` to `move`, adding `/q` to `rmdir`).
- **Success**: Proper sanitization for non-interactive execution.

#### Test 5: Capability Logic (`test_capabilities`)
- **Action**: Verifies heuristic engine correctly identifies feature sets per model family.
- **Success**: `llama3` -> Tools, `llava` -> Vision, etc.

#### Test 6: Feedback Loop (`test_feedback_loop`)
- **Action**: Simulates a tool execution and verifies the state-injection into `chat_history`.
- **Success**: History contains `role: tool` message and triggers the AI worker.

#### Test 7: OS Permissions (`test_execution_environment`)
- **Action**: Performs recursive directory traversal and temp file CRUD operations.
- **Success**: Verifies OS-level IO compliance.

#### Test 8: Engine Logic (`test_app_logic`)
- **Action**: Validates generated JSON schemas against the Ollama Tool calling specification.
- **Success**: Schemas are valid and structured correctly.

#### Test 9: Static Reference (`test_reference_commands`)
- **Action**: Verifies that AI tool arguments map correctly to internal IDE command stubs.

#### Test 10: Global Model Report (`test_all_models_report`)
- **Action**: Iteratively audits all installed models for "Live Tool Calling" capabilities.
- **Success**: Generates `model_capabilities_report.txt` with SUCCESS/FAIL per model.

#### Test 11: Visual Audit (`test_visual`) [Optional]
- **Action**: Real GUI launch and screenshot verification via PyAutoGUI.

#### Test 12: AI Compliance (`test_model_compliance`)
- **Action**: Performs a live, unscripted tool-calling request through the local LLM.

### 5.2 Tester UI Requirements

#### Control Panel
- **Model Selector** (`ttk.Combobox`): Dropdown to manually override test target model. **MUST** load/save state from `app_state.json` to stay synchronized with the IDE.
- **Progress Bar** (`ttk.Progressbar`): Visual feedback during `run_all()`
- **Status Label** (`tk.StringVar`): Real-time text updates of current test

#### Test Dashboard
Each of the 9 tests must have:
- **Action Button**: 22-char width, left-aligned, dark background
- **Description Label**: Gray text explaining the test purpose

#### Output Console
- **Text Widget**: Black background, green monospace text
- **Timestamps**: Each log line prefixed with `[HH:MM:SS]`
- **Auto-scroll**: Always show latest output

---

## 6. Programming Principles

Adhere to these "Good Coding Practices" to ensure the IDE remains robust:

### A. Headless-First Testing
*   **Principle**: Tests must run without ANY human intervention.
*   **Practice**: Always stub `tkinter` dialogs (`filedialog`, `messagebox`) in the `Integrated_Tester`.
*   **Goal**: `python Integrated_Tester_v1_1.py --full` should run on a server with no monitor.

### B. Non-Blocking Execution
*   **Principle**: The UI Main Loop must never freeze.
*   **Practice**: Any AI call, Shell command, or File IO > 10ms must be handled in a `threading.Thread` or `ShellExecutor`.
*   **Feedback**: Always provide visual feedback (status bar, spinner) for background tasks.

### C. Single Source of Truth
*   **Principle**: Do not duplicate state.
*   **Practice**: `app_state.json` is the authority. If the app crashes, re-opening it should restore the exact state from this file.

### D. Resilient Diagnostics & Chaos Testing
*   **Principle**: The verify tool checks *integrity*, not just code coverage.
*   **Chaos Standard**: The tester itself must be verified by intentional **Fault Injection**. If core logic is sabotaged in the IDE, the tester MUST flag a FAIL. If it passes a broken IDE, the tester is logically unsound.
*   **Practice**: Tests should verify *outcomes* (did the file appear?) rather than just *functions* (did it return True?).
*   **Scope**: Compliance tests must verify ALL commands (Create, Shell, Delete, List) using the Native Tool API.

### E. Leave No Trace
*   **Principle**: Tests and AI agents should clean up after themselves.
*   **Practice**:
    *   Delete temporary files (e.g., `debug_dump.txt`, `temp_test.py`) immediately after use.
    *   Use `try...finally` blocks to ensure cleanup happens even if tests crash.
    *   The `Integrated_Tester` should verify the *absence* of these files after a run.

---

## 7. API-First Architecture

We are transitioning from Regex Parsing to **Native Tool Calling**.

*   **Rule**: Do not use Regex to parse commands from the AI model (UNLESS as a fallback).
*   **Practice**: Define tools using JSON Schema passed to `ollama.chat(tools=[...])`.
*   **Goal**: Robust, structured interaction that supports complex arguments (filenames, content, options).
*   **Context**: Use RAG (Retrieval Augmented Generation) logic to inject file content via messages, not just system prompts.

### Adaptive Selection & Selection Locking (Testing)
*   **Principle**: Tests should be optimized for speed and capability while ensuring user-intent is preserved.
*   **Practice**: The test runner should automatically identify and prioritize the smallest, most capable model found locally for general checks, but **MUST** use the exact user-selected model for compliance probes.
*   **Locking**: To prevent async refreshes from resetting the target, the tester MUST capture the selected model synchronously before spawning any background diagnostic threads.

---

## 8. UX Transparency
*   **Principle**: The user should know what the model *can* do before they try to do it.
*   **Practice**:
    *   Expose capabilities (Tool Support, Vision Support) in the Model Selection UI **(IDE and Integrated Tester)**.
    *   **Accuracy Priority**: It is better to hide a capability tag than to show a False Positive. False Positives lead to 400 Errors and "Crashes".
    *   **Heuristic Whitelist**: Include proven architectures: `Llama3`, `Qwen2.5`, `Qwen3`, `Mistral-Nemo`, `Command-R`, `DeepSeek-V3/R1`, `Gemma`.
    *   Do not allow the user to select an incompatible model for a task without a warning.
    *   **UI Consistency**: Use explicit indicators (e.g., icons or text tags `[Tools]`) consistently in all dropdowns.

---

## 9. RAG & Attachments
*   **Context Strategy**: Append file content to the *User Message* using clear delimiters (`[CONTEXT FILE: name]...`), rather than stuffing the System Prompt.
*   **Vision**:
    *   **Rule**: Use the native `images` parameter of `client.chat()`.
    *   **Prohibition**: Do NOT embed Base64 image strings directly into the prompt text (it consumes context and is less reliable).
*   **Error Safety**: When ingesting files, always use `errors='ignore'` or fallback encoding to prevent the app from crashing on binary/weird files.

---

## 10. Tool Validation & Robustness
*   **Safe Defaults**: `OllamaToolManager.parse_tool_call` must ensure that missing JSON arguments default to empty strings rather than `None` to prevent `AttributeError` in downstream logic.
*   **Execution Checks**: Every method in `execute_one_command` must validate inputs (e.g., check if `path` or `content` is empty) before attempting OS operations.
*   **Silent Failures**: Log validation errors to the console/status bar; do not show blocking "Action Error" popups for expected AI input hallucinations.
*   **Tester Sync**: The `Integrated_Tester` must use a task counter (`pending_tasks`) to wait for asynchronous AI responses before generating a final audit summary.

---

## 11. Agentic Standards & Tool-Calling Loop
To achieve true "Agentic" behavior, we follow the conventional Ollama/OpenAI pattern:
1.  **System Prompting**: If tools are available, always include a system instruction: `"You are an assistant with tool calling capabilities..."`
2.  **Native Preference**: Always prefer the `tool_calls` API over XML parsing when the model supports it.
3.  **The Result Loop**: 
    - When a model calls a tool, execute it and capture the output.
    - Append a message with `role: "tool"` and the result content back to the history.
    - Call the model again so it can acknowledge the result.
4.  **Recurrence Limit**: Limit automated agent loops to a maximum of 5 turns to prevent infinite loops/context blowout.
5.  **Compliance Testing**: Every new tool added to `OllamaToolManager` MUST have a corresponding test case in the `Integrated_Tester`'s compliance suite.

---

## 11. Design Philosophy: Rigor & Stability

### 11.1 Tester Integrity (The "Who Tests the Tester" Rule)
- **Chaos Testing**: The suite must periodically be validated by sabotaging IDE logic (e.g., breaking the Shell Sanitizer) to ensure the tester correctly flags the failure.
- **Logic Assertions**: Tests must verify behavior (e.g., bit-perfect state restoration) rather than just presence.
- **No Skips**: Core tests MUST NOT be skipped if components are part of the baseline.
- **Headless Compatibility**: Code in `Ollama_Agentic_IDE_v1_1.py` MUST be import-safe. Side effects (like thread starts or UI loops) must be guarded so that the Tester can instantiate classes for unit testing.

### 11.2 Persistence First
- **Triggering**: Every user-initiated UI change (Model, OS, Help) must trigger an immediate `save_state()`.
- **Startup Safety**: `save_state()` must **NOT** be called during `__init__` or initial UI setup. Initialization methods must be side-effect free regarding persistence to prevent overwriting valid disk state with empty defaults.
- **Robust Restoration**: `load_state()` must use granular `try...except` blocks for each component (Geometry, Content, History). A failure to restore one element (e.g., corrupt geometry) must NOT prevent others (e.g., chat history) from loading.
- **Global Memory**: The state file `app_state.json` is the single source of truth that synchronizes the IDE and Tester.

### A. The IDE (Ollama_Agentic_IDE)
*   **Intent**: To provide a "Glass Box" agentic experience where the user sees *exactly* what the model is doing (thinking vs. tool calling).
*   **Philosophy**:
    *   **Local-First**: Zero reliance on cloud APIs; everything runs on `localhost:11434`.
    *   **Tool-Native**: The IDE is designed around *tools* (create, delete, shell) as first-class citizens, not just chat.
    *   **Non-Blocking**: The UI must remain responsive (using background threads) even while the model is "thinking" or running long shell commands.

### B. The Tester (Integrated_Tester)
*   **Intent**: To serve as an independent, unbiased auditor of the IDE's health.
*   **Philosophy**:
    *   **Fail-Fast**: Stop and report errors immediately rather than swallowing them.
    *   **Headless-Capable**: Must run via CLI (`--full`) on CI/CD systems without a monitor.
    *   **Truth-Teller**: It mocks nothing except what is absolutely necessary (like GUI dialogs) to ensure tests reflect real-world usage.

---

## 13. Refactoring Protocol (The "Do No Harm" Rule)
*   **Preservation**: When refactoring, ALL existing UI elements (buttons, dropdowns, labels, descriptions) must be preserved unless explicitly deprecated by the user.
*   **Mapping**: AI Agents must map the old UI elements to the new code structure *before* writing any code. If a feature existed before, it must exist after.
*   **Fidelity**: Do not "simplify" a rich dashboard into a single button. Users rely on granular control.
*   **Guideline Integrity**: Before editing any part of these guidelines, evaluate its importance. Critical protocols (like the Logical Update Order or the Do No Harm Rule) must never be relaxed or removed to accommodate a shortcut or a "simplified" refactor.

---

## 14. AI Agent Decision Rules

When faced with ambiguous requirements, AI Agents MUST:

1. **Consult This Document First**: If this guideline specifies exact behavior, follow it precisely.
2. **Preserve Existing Behavior**: If no specification exists, observe current implementation and maintain it.
3. **Ask Before Breaking**: If a change would remove functionality, ask the user explicitly.
4. **Default to Safety**: When in doubt, choose the option that prevents data loss or crashes.
5. **Test Before Committing**: Always run `python Integrated_Tester_v1_1.py --full` after changes.
