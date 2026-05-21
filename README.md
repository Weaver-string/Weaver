# Weaver

Weaver is a local-first smart energy scheduler for Matter appliances.

It runs inside the user's home network, commissions Matter devices through a local Matter controller, and schedules flexible appliances around grid prices and optional solar production.

## What Weaver Does Now

- Connects Matter appliances with a manual setup code or `MT:` QR payload.
- Runs connected On/Off Matter appliances immediately.
- Schedules flexible appliance loads against a grid price signal.
- Supports two home modes:
  - Grid only
  - Solar + grid
- Uses a local FastAPI backend and a Next.js frontend.

## Repository Layout

```text
frontend/                         Next.js app
Models/MatterEnergyScheduler/      FastAPI backend
install.ps1                        Windows dependency install script
start-matter-server.ps1            Starts the local Home Assistant Matter Server from Python
start-weaver.ps1                   Windows local startup script
stop-weaver.ps1                    Windows local stop script
uninstall.ps1                      Removes installed local dependencies
Start Weaver.vbs                   Double-click local launcher
Stop Weaver.vbs                    Double-click local stop helper
```

## Requirements

- Windows 10/11
- Node.js 20+
- Python 3.13 recommended
- A Matter appliance that can be put into pairing mode
- The Windows computer running Weaver and the Matter appliance on the same home network

## Before You Try It

Weaver is an early local app for testing Matter appliance scheduling. It is best suited for people who are comfortable running PowerShell commands and trying software that may need troubleshooting.

Useful feedback includes:

- Whether install and startup worked on your machine.
- Whether Weaver could commission your Matter appliance.
- What appliance type, brand, and model you tested.
- Any error messages from the PowerShell windows or the app.
- Places where the setup instructions were confusing.

## Quick Start on Windows

Open PowerShell in the repo root:

```powershell
.\install.ps1
.\start-weaver.ps1
```

`start-weaver.ps1` starts the local Matter Server, Weaver backend, and Weaver frontend.

Then open:

```text
http://127.0.0.1:3000
```

Put the Matter appliance into pairing mode, click Connect Device in Weaver, and enter the device's Matter setup code or `MT:` payload.

You can also start Weaver from File Explorer by opening the repo folder and double-clicking `Start Weaver.vbs`. To stop Weaver, double-click `Stop Weaver.vbs`.

## Uninstall

To remove Weaver's installed dependencies from this folder:

```powershell
.\uninstall.ps1
```

This removes the Python virtual environment, frontend dependencies, and build caches. It keeps local Weaver app data by default.

To also remove local Weaver app data, including Matter Server state:

```powershell
.\uninstall.ps1 -RemoveData
```

## Matter Notes

Matter commissioning and control are local-network operations. The machine running Weaver should be on the same home network as the Matter appliance.

Weaver uses the same open-source Matter Server used by Home Assistant:

```text
python-matter-server
```

The local architecture is:

```text
Weaver UI
  -> Weaver FastAPI backend
    -> Home Assistant Matter Server
      -> Matter appliance
```

The Matter Server handles the low-level Matter protocol work: discovery, secure commissioning, fabric credentials, node storage, secure sessions, and Matter cluster commands. Weaver handles the user experience, scheduling, and optimization decisions.

By default, Weaver connects to the Matter Server at:

```text
ws://127.0.0.1:5580/ws
```

The Matter Server stores its local state under:

```text
.weaver/matter-server
```

This local state is not committed to Git.

## Pairing a Matter Appliance

1. Make sure the computer running Weaver and the Matter appliance are on the same home network.
2. Put the appliance into pairing mode.
3. Open Weaver.
4. Click Connect Device.
5. Enter the device's Matter setup code.
6. Weaver commissions the appliance through the local Matter Server.

## Development Checks

Frontend:

```powershell
cd .\frontend
npm.cmd run lint
npm.cmd exec tsc -- --noEmit
```

Backend:

```powershell
cd .\Models\MatterEnergyScheduler
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check main.py src tests
```

## Local Files Not Committed

The repo ignores local generated files such as:

- `node_modules/`
- `.next/`
- `.venv/`
- `.env`
- logs
- local SQLite databases
- Matter runtime state
- Python bytecode caches

## Advanced Manual Starts

`start-weaver.ps1` is the normal way to run Weaver. These commands are only for starting individual services while developing or troubleshooting.

Start only the Matter Server:

```powershell
.\start-matter-server.ps1
```

Start only the backend:

```powershell
cd .\Models\MatterEnergyScheduler

$env:MATTER_SERVER_WS_URL="ws://127.0.0.1:5580/ws"
$env:FRONTEND_ORIGINS="http://localhost:3000,http://127.0.0.1:3000"
$env:WEAVER_LIVE_PRICES="0"

.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Start only the frontend:

```powershell
cd .\frontend

$env:NEXT_PUBLIC_API_URL="http://127.0.0.1:8000"

npm.cmd run dev -- --hostname 127.0.0.1
```

## License

MIT
