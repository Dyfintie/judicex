# Simple Installers

Judicex currently ships script-based local installers. They create a Python
virtual environment, install Judicex, and create a launcher.

## Windows

Open PowerShell in the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_windows.ps1
```

Then run:

```text
%USERPROFILE%\Judicex\run_judicex.bat
```

## macOS

Open Terminal in the repository root:

```bash
bash scripts/install_macos.sh
```

Then run:

```bash
~/Judicex/run_judicex.command
```

Both launchers start Judicex on:

```text
http://127.0.0.1:5050
```

These scripts are intentionally simple. A signed/notarized desktop installer
can be added later with PyInstaller, Briefcase, or a native wrapper.
