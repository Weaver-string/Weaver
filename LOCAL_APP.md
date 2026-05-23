# Weaver Local App

Weaver is intended to run locally for each household. The user's browser, backend, database, schedules, and Matter Server connection stay inside the user's own home network. Nothing needs to report back to the developer.

## Target User Mode

For real Matter appliance testing, Weaver is aimed at users who can run this at home:

- Raspberry Pi running Matter Server

In that setup:

1. Start the Matter Server on the Raspberry Pi.
2. Start Weaver on the Windows machine.
3. Set `MATTER_SERVER_WS_URL` to the Matter Server WebSocket URL.
4. Open Weaver at `http://127.0.0.1:3000`.
5. Pair and schedule appliances through Weaver.

Example:

```powershell
cd C:\Users\keyse\Desktop\Weaver

$env:MATTER_SERVER_WS_URL="ws://RASPBERRY_PI_IP:5580/ws"
.\start-weaver.ps1
```

The launcher starts:

- FastAPI backend on `127.0.0.1:8000`
- Next.js frontend on `127.0.0.1:3000`
- Browser UI pointed at the local frontend

The backend talks to the configured Matter Server over WebSocket.

## Windows-Only Test Mode

Windows users can still test Weaver's UI, city selection, price scheduling, run queue, and virtual-load flow without a Matter Server. Real appliance commissioning and control requires a configured Matter Server on a Raspberry Pi.

## LAN Test Mode

For a LAN test where the browser opens from another computer, start the backend/frontend manually with LAN binding:

```powershell
cd C:\Users\keyse\Desktop\Weaver\Models\MatterEnergyScheduler

$env:MATTER_SERVER_WS_URL="ws://RASPBERRY_PI_IP:5580/ws"
$env:FRONTEND_ORIGINS="http://localhost:3000,http://127.0.0.1:3000,http://YOUR_LAPTOP_IP:3000"
$env:WEAVER_LIVE_PRICES="0"

.\.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000
```

In another window:

```powershell
cd C:\Users\keyse\Desktop\Weaver\frontend

$env:NEXT_PUBLIC_API_URL="http://YOUR_LAPTOP_IP:8000"
npm.cmd run dev -- --hostname 0.0.0.0
```

Then open this from the other computer:

```text
http://YOUR_LAPTOP_IP:3000
```

## Installer Target

The launcher is a near-term developer/test convenience. The production target should be an installer or setup flow that provisions:

- The backend runtime
- The frontend build
- A local desktop/browser shell
- A clear Matter Server connection step for Raspberry Pi users

The installed app should start Weaver's backend automatically, open the UI, and ask for the Matter Server URL only when real appliance control is needed.
