---
description: Test the Ollama Mini-IDE and Ollama connectivity
---

This workflow allows the AI (Antigravity) to verify that the Mini-IDE can communicate with the local Ollama service.

1. Run the headless system check for the app
// turbo
```powershell
python app.py --test
```

2. If the check fails, verify if Ollama is running on port 11434
// turbo
```powershell
curl http://127.0.0.1:11434
```

3. (Optional) Start the full GUI app for the user to see
```powershell
python app.py
```
