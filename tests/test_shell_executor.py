import os
import sys
import threading
import time
import platform
import subprocess

# Add parent path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import ShellExecutor from the main app (by importing the module)
# Note: Since the class is inside the script, we can import it if it's top level.
# If this fails, we might need to mock it or extract it.
from Ollama_Agentic_IDE_v1_1 import ShellExecutor

def test_shell_executor():
    print("Testing ShellExecutor...")
    
    logs = []
    done_event = threading.Event()
    
    def log_cb(msg):
        logs.append(msg)
        print(f"[CB] {msg.strip()}")
        
    def end_cb():
        done_event.set()
        print("[CB] Process Finished")

    executor = ShellExecutor(log_cb, end_cb)
    
    # Test 1: Sanitization (Windows)
    if platform.system() == "Windows":
        print("\n--- Test 1: Sanitization (Windows) ---")
        cmd = "rmdir /S testing_dir"
        fixed = executor.sanitize_command(cmd)
        if "/q" in fixed.lower():
            print("SUCCESS: rmdir auto-fixed.")
        else:
            print(f"FAIL: rmdir not fixed: {fixed}")
            return 1
            
        cmd_del = "del *.txt"
        fixed_del = executor.sanitize_command(cmd_del)
        if "/q" in fixed_del.lower():
             print("SUCCESS: del auto-fixed.")
        else:
             print(f"FAIL: del not fixed: {fixed_del}")
             return 1

    # Test 2: Stop Functionality (Mock long process)
    print("\n--- Test 2: Stop Functionality ---")
    long_cmd = "ping 127.0.0.1 -n 10" if platform.system() == "Windows" else "sleep 10"
    executor.run(long_cmd)
    
    time.sleep(2) # Let it start
    if executor.running:
        print("Confirmed process running.")
        executor.stop()
        done_event.wait(timeout=2)
        
        if not executor.running:
            print("SUCCESS: Process stopped.")
        else:
            print("FAIL: Process still running after stop.")
            return 1
    else:
        print("FAIL: Process finished too fast?")
        return 1

    return 0

if __name__ == "__main__":
    try:
        sys.exit(test_shell_executor())
    except Exception as e:
        print(f"CRASH: {e}")
        sys.exit(1)
