# Raspberry Pi Matter Server Setup

This is the preferred real-appliance setup for Weaver while native Windows Matter Server support is blocked by upstream CHIP package availability.

The Raspberry Pi runs Matter Server. Weaver runs on the Windows machine and connects to the Pi over WebSocket.

```text
Matter appliance
  <-> Raspberry Pi Matter Server
  <-> Weaver backend on Windows
  <-> Weaver UI
```

## Recommended Pi Setup

Use:

- Raspberry Pi 4 or 5
- 64-bit Raspberry Pi OS or Home Assistant OS
- A flat home network where the Pi, Weaver machine, phone, border routers, and Matter appliances are on the same LAN/VLAN
- IPv6 enabled on the Pi network interface

Matter relies on local IPv6 multicast, mDNS/DNS-SD, and route discovery. Avoid guest networks, isolated IoT VLANs, multicast filtering, and mDNS forwarding while testing.

## Option A: Raspberry Pi OS + Docker Matter Server

This is the most direct path for Weaver because the Matter Server WebSocket is exposed from the Pi.

On the Pi:

```sh
mkdir -p ~/weaver-matter-server/data
cd ~/weaver-matter-server

docker run -d \
  --name matter-server \
  --restart=unless-stopped \
  --security-opt apparmor=unconfined \
  -v "$(pwd)/data:/data" \
  --network=host \
  ghcr.io/matter-js/python-matter-server:stable
```

Then point Weaver at the Pi:

```powershell
$env:MATTER_SERVER_WS_URL="ws://RASPBERRY_PI_IP:5580/ws"
.\start-weaver.ps1
```

If you want local Bluetooth commissioning through the Pi, run the container with D-Bus access:

```sh
docker run -d \
  --name matter-server \
  --restart=unless-stopped \
  --security-opt apparmor=unconfined \
  -v "$(pwd)/data:/data" \
  -v /run/dbus:/run/dbus:ro \
  --network=host \
  ghcr.io/matter-js/python-matter-server:stable \
  --storage-path /data \
  --paa-root-cert-dir /data/credentials \
  --bluetooth-adapter 0
```

Use the first command for Wi-Fi/LAN Matter testing. Use the Bluetooth command only if the Pi is handling local commissioning.

## Option B: Home Assistant OS on Raspberry Pi

This is the most supported Home Assistant route.

In Home Assistant:

1. Install Home Assistant OS on the Raspberry Pi.
2. Go to Settings -> Devices & services.
3. Add the Matter integration.
4. In a normal Home Assistant OS setup, Home Assistant installs the official Matter Server app.
5. Pair devices through the Home Assistant Companion app.

This path is best for Home Assistant users, but the Matter Server add-on may not expose its WebSocket port to other machines by default. For Weaver, either expose the Matter Server WebSocket deliberately, or use a standalone Pi Matter Server container as in Option A.

## Network Checklist

- Pi is 64-bit Linux.
- Pi and Matter appliances are on the same LAN/VLAN.
- IPv6 is enabled on the Pi.
- Multicast filtering/optimization is disabled on the router/AP.
- Weaver can reach the Pi:

```powershell
Test-NetConnection RASPBERRY_PI_IP -Port 5580
```

- Weaver starts with:

```powershell
$env:MATTER_SERVER_WS_URL="ws://RASPBERRY_PI_IP:5580/ws"
.\start-weaver.ps1
```

## Notes

- Do not expose port `5580` to the public internet.
- Keep Matter Server state in the Pi data folder; it contains the Matter fabric state.
- Thread devices also need a working Thread Border Router and correct IPv6 routing.
- Wi-Fi Matter devices are simpler first test targets than Thread devices.
