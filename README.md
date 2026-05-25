# Weaver

Weaver is a local-first smart energy scheduler for Matter appliances, designed to pair with a Matter Server running on a Raspberry Pi.

It runs inside the user's home network, connects to a Matter controller over WebSocket, and schedules flexible appliances around grid prices and optional solar production.

## What Weaver Does Now

- Connects Matter appliances through a configured Matter Server.
- Runs connected On/Off Matter appliances immediately when Matter Server access is available.
- Schedules flexible appliance loads against a grid price signal.
- Supports two home modes:
  - Grid only
  - Solar + grid
- Uses a local FastAPI backend and a Next.js frontend.

## How Price Scheduling Works

Weaver is built for flexible appliances: devices that do not need to start immediately, but do need to finish before a deadline. Examples include a dishwasher, washing machine, dryer, water heater, or EV charger.

When you choose a city, Weaver uses that location to fetch local electricity price data and plan the run. The scheduler works in 30-minute blocks and looks for a start time that finishes before the appliance deadline.

The price data is wholesale electricity market pricing. It does not represent a fixed household tariff or a utility plan where you pay the same rate all day. Weaver's price scheduling is meant to reflect dynamic electricity plans, where the price changes by time period and the utility or supplier passes some version of that signal to the customer.

Live day-ahead prices require an ENTSO-E Transparency Platform API token. After starting Weaver, open the info tab and paste the key into the `Live prices` setup box. Weaver saves it locally in `Models/MatterEnergyScheduler/.env`, which is ignored by Git. If no token is configured, Weaver uses fallback estimates so the app can still schedule devices.

When a schedule reaches into hours where live day-ahead prices are not published yet, Weaver keeps every real price it already has and fills only the missing price windows with fallback estimates. This lets scheduling still work across a deadline while giving priority to actual market prices whenever they are available. Fallback estimates are not treated as permanent: when actual prices arrive later, they replace the synthetic prices for the same time windows.

In grid-only mode, Weaver uses a cheapest-window algorithm. It sorts through the available price periods, estimates the cost of running the appliance in each possible window, skips windows that would miss the deadline or exceed the configured home load limit, and chooses the lowest-cost valid window.

In solar + grid mode, Weaver gives priority to using your own solar power first. This matters because self-consuming rooftop solar is often worth more than exporting it, especially when export rates are lower than import prices. The scheduler scores each possible run window by estimating how much of the appliance load can be covered by forecast solar production, then uses grid price optimization for the remaining energy. In practical terms: run when your panels are expected to produce, and use cheaper grid periods as the backup.

Grid + solar + BESS mode is planned, but not completed yet. BESS means battery energy storage system, such as a home battery. The goal is to support homes where Weaver can coordinate appliance demand with rooftop solar, stored battery energy, and grid prices together.

The intended BESS algorithm would use available solar first, then battery energy above a reserve buffer, and then grid power for any remaining demand. It would also account for charging the battery from excess solar. This mode depends on home batteries becoming more broadly controllable through Matter, so Weaver currently focuses on grid-only and solar + grid scheduling.

## Repository Layout

```text
frontend/                         Next.js app
Models/MatterEnergyScheduler/      FastAPI backend
install.ps1                        Windows dependency install script for Weaver
start-matter-server.ps1            Advanced helper; native Windows Matter Server is not supported
start-weaver.ps1                   Windows local startup script for Weaver UI/backend
stop-weaver.ps1                    Windows local stop script
uninstall.ps1                      Removes installed local dependencies
Start Weaver.vbs                   Double-click local launcher
Stop Weaver.vbs                    Double-click local stop helper
```

## Requirements

- Windows 10/11 for the Weaver UI/backend
- Node.js 20+
- Python 3.12 or 3.13, installed from python.org with `Add python.exe to PATH` enabled
- Raspberry Pi running Matter Server for real appliance commissioning/control
- A Matter appliance that can be put into pairing mode
- The Weaver machine, Matter Server host, and Matter appliance on the same home network

## Before You Try It

Weaver is an early local app for testing Matter appliance scheduling. It is best suited for people who can run a Raspberry Pi at home and are comfortable trying software that may need troubleshooting.

Useful feedback includes:

- Whether install and startup worked on your machine.
- Whether Weaver could connect through your Raspberry Pi Matter Server.
- What appliance type, brand, and model you tested.
- Any error messages from the PowerShell windows or the app.
- Places where the setup instructions were confusing.

## Quick Start on Windows

Open PowerShell, then go to the Weaver folder:

```powershell
cd C:\Users\YOUR_NAME\Desktop\Weaver
```

If PowerShell says scripts are disabled, allow scripts for this PowerShell window only:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Install Weaver once:

```powershell
.\install.ps1
```

Start Weaver for UI testing:

```powershell
.\start-weaver.ps1
```

The start script opens separate windows for the Weaver backend and Weaver frontend. Leave those windows open while using Weaver.

Weaver should open automatically. If it does not, open this address in your browser:

```text
http://127.0.0.1:3000
```

## Live Price Setup

Weaver can schedule with fallback price estimates, but live day-ahead prices need an ENTSO-E API key.

1. Create an account on the ENTSO-E Transparency Platform.
2. Create or copy your API token from the platform.
3. Start Weaver.
4. Open the info tab.
5. Paste the token into the `Live prices` setup box.

After the token is saved, that setup box disappears and Weaver starts attempting live wholesale prices. The token stays on your computer in:

```text
Models/MatterEnergyScheduler/.env
```

You can also configure it manually before starting Weaver:

```text
ENTSOE_API_KEY=your_token_here
```

## Raspberry Pi Matter Server Setup

For real appliances, set Weaver's Matter Server URL before starting it:

```powershell
$env:MATTER_SERVER_WS_URL="ws://RASPBERRY_PI_IP:5580/ws"
.\start-weaver.ps1
```

`RASPBERRY_PI_IP` is the IP address of the Raspberry Pi running Matter Server. The Pi, the Weaver machine, and the Matter appliance should be on the same home network with IPv6 enabled.

Then put the Matter appliance into pairing mode, click Connect Device in Weaver, and enter the device's Matter setup code or `MT:` payload.

For the full Raspberry Pi setup, see [RASPBERRY_PI_MATTER_SERVER.md](RASPBERRY_PI_MATTER_SERVER.md).

After the first install, normal startup is just:

```powershell
cd C:\Users\YOUR_NAME\Desktop\Weaver
.\start-weaver.ps1
```

To stop Weaver, close the Weaver PowerShell windows or run:

```powershell
.\stop-weaver.ps1
```

You can also start Weaver from File Explorer by opening the repo folder and opening `Start Weaver.vbs`. To stop Weaver from File Explorer, open `Stop Weaver.vbs`.

## Uninstall

To remove Weaver's installed dependencies from this folder:

```powershell
.\uninstall.ps1
```

This removes the Python virtual environment, frontend dependencies, and build caches. It keeps local Weaver app data by default.

To also remove local Weaver app data:

```powershell
.\uninstall.ps1 -RemoveData
```

## Matter Notes

Matter commissioning and control are local-network operations. The machine running Weaver should be on the same home network as the Matter appliance.

For Raspberry Pi setup, see [RASPBERRY_PI_MATTER_SERVER.md](RASPBERRY_PI_MATTER_SERVER.md).

Weaver talks to a Matter Server over WebSocket. The intended real-appliance setup is a Matter Server running on a Raspberry Pi, with Weaver connecting to it from the same home network.

The backend includes the open-source Python Matter Server client package:

```text
python-matter-server
```

Native Windows startup of the Python Matter Server is not currently available because the upstream CHIP core package does not publish Windows builds. Weaver therefore focuses on Raspberry Pi Matter Server hosts for real appliance commissioning and control.

The local architecture is:

```text
Weaver UI
  -> Weaver FastAPI backend
    -> Raspberry Pi Matter Server
      -> Matter appliance
```

The Matter Server handles the low-level Matter protocol work: discovery, secure commissioning, fabric credentials, node storage, secure sessions, and Matter cluster commands. Weaver handles the user experience, scheduling, and optimization decisions.

Set `MATTER_SERVER_WS_URL` to your Raspberry Pi Matter Server:

```text
ws://RASPBERRY_PI_IP:5580/ws
```

If `MATTER_SERVER_WS_URL` is not set, Weaver falls back to this local development address:

```text
ws://127.0.0.1:5580/ws
```

Your Matter Server manages its own Matter state. The ignored Weaver data folder is:

```text
.weaver/matter-server
```

This local state is not committed to Git.

## Pairing a Matter Appliance

1. Make sure the Raspberry Pi Matter Server is running.
2. Make sure the Weaver machine, Matter Server host, and Matter appliance are on the same home network.
3. Set `MATTER_SERVER_WS_URL` to the Matter Server WebSocket URL before starting Weaver.
4. Put the appliance into pairing mode.
5. Open Weaver.
6. Click Connect Device.
7. Enter the device's Matter setup code.
8. Weaver commissions the appliance through the configured Matter Server.

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

Start only the Matter Server helper:

```powershell
.\start-matter-server.ps1
```

This helper is kept for advanced development on supported hosts. Native Windows Matter Server startup is not supported by the current upstream CHIP dependency.

Start only the backend:

```powershell
cd .\Models\MatterEnergyScheduler

$env:MATTER_SERVER_WS_URL="ws://127.0.0.1:5580/ws"
$env:FRONTEND_ORIGINS="http://localhost:3000,http://127.0.0.1:3000"

.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

To force fallback prices while troubleshooting, set:

```powershell
$env:WEAVER_LIVE_PRICES="0"
```

Start only the frontend:

```powershell
cd .\frontend

$env:NEXT_PUBLIC_API_URL="http://127.0.0.1:8000"

npm.cmd run dev -- --hostname 127.0.0.1
```

## License

MIT
