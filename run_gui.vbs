' Runner tanpa jendela CMD (Silent Launcher)
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strCurrentDir = fso.GetParentFolderName(WScript.ScriptFullName)
strPythonW = strCurrentDir & "\.venv\Scripts\pythonw.exe"
strMainPy = strCurrentDir & "\main.py"

If Not fso.FileExists(strPythonW) Then
    MsgBox "Virtual environment belum tersedia. Silakan jalankan setup.bat terlebih dahulu.", vbCritical, "Cloudflare Tunnel Manager"
    WScript.Quit 1
End If

' 0 = Sembunyikan window sepenuhnya, False = Tidak menunggu proses selesai
WshShell.Run """" & strPythonW & """ """ & strMainPy & """", 0, False
Set WshShell = Nothing
Set fso = Nothing
