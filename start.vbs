Set objShell = CreateObject("WScript.Shell")
objShell.CurrentDirectory = "C:\Users\ABDO\Documents\alkhayar_hr_v4"
objShell.Run "cmd /c git pull", 1, True
objShell.Run "py -m streamlit run app.py --server.headless true", 0, False
WScript.Sleep 4000
objShell.Run "http://localhost:8501"