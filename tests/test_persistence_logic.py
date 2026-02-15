import os
import json
import tkinter as tk
from unittest.mock import MagicMock
import sys

# Add parent dir to path to import app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from Ollama_Agentic_IDE_v1_1 import OllamaIDE

def test_persistence():
    print("Testing App State Persistence Logic...")
    
    # Mock Root
    root = tk.Tk()
    root.withdraw() # Hide
    
    # Initialize App (creates state file if missing)
    app = OllamaIDE(root)
    
    # Manipulate State
    test_history = [{"role": "user", "content": "Test Persistence Message"}]
    app.chat_history = test_history
    app.os_var.set("TestOS")
    
    # Save
    print("Saving state...")
    app.save_state()
    
    # Verify File Content
    if not os.path.exists(app.state_file):
        print("FAIL: State file not created.")
        return 1
        
    with open(app.state_file, "r") as f:
        data = json.load(f)
        
    if data.get("chat_history") == test_history:
        print("SUCCESS: Chat history persisted correctly.")
    else:
        print(f"FAIL: History mismatch. Got: {data.get('chat_history')}")
        return 1

    if data.get("os_profile") == "TestOS":
         print("SUCCESS: OS Profile persisted correctly.")
    else:
         print(f"FAIL: OS Profile mismatch. Got: {data.get('os_profile')}")
         return 1
         
    return 0

if __name__ == "__main__":
    try:
        sys.exit(test_persistence())
    except Exception as e:
        print(f"CRASH: {e}")
        sys.exit(1)
