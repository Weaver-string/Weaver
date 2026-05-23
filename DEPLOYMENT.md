# Weaver Internet Deployment

Weaver can be exposed as a public website, but Matter control still needs a controller process with access to the Matter fabric. The intended real-appliance controller is a Raspberry Pi running Matter Server on the home network.

## Realistic Architecture

```mermaid
flowchart LR
  Browser["Public browser"] --> Frontend["Public Weaver frontend"]
  Frontend --> Api["Public Weaver API"]
  Api --> MatterServer["Raspberry Pi Matter Server"]
  MatterServer --> MatterFabric["Matter fabric over IPv6"]
  MatterFabric --> Wifi["Wi-Fi / Ethernet appliances"]
  MatterFabric --> Thread["Thread appliances via Border Router"]
```

Matter appliance commands are not sent directly from the browser. The browser calls Weaver's API over HTTPS. Weaver then asks the configured Raspberry Pi Matter Server to control commissioned Matter nodes using Matter operational traffic over IPv6.

## Deployment Modes

### 1. Public UI and Public API on the Matter Network

Run the frontend and backend on a host that can also reach the Raspberry Pi Matter Server and the Matter appliances. Expose the frontend/API through HTTPS using a reverse proxy or tunnel.

This is the simplest realistic test if the Matter Server and Weaver backend share the same IPv6-capable home network.

### 2. Public UI with Raspberry Pi Controller

Host the frontend publicly, but keep Weaver API or a small controller service inside the home network with access to the Raspberry Pi Matter Server.

The public frontend must call the reachable API URL:

```text
NEXT_PUBLIC_API_URL=https://api.your-weaver-domain.example
```

### 3. Cloud Backend with Local Agent

If the backend is hosted in the cloud, it usually cannot discover or control local Matter devices directly because Matter uses local IPv6 operational discovery and fabric credentials. In that case, run a local agent/controller near the Matter fabric, preferably beside the Raspberry Pi Matter Server, and connect it to the cloud backend over a secure outbound channel.

## Required Environment

Frontend:

```text
NEXT_PUBLIC_API_URL=https://api.your-weaver-domain.example
```

Backend:

```text
FRONTEND_ORIGINS=https://your-weaver-domain.example
MATTER_SERVER_WS_URL=ws://RASPBERRY_PI_IP:5580/ws
API_HOST=0.0.0.0
API_PORT=8000
```

Use `FRONTEND_ORIGINS=*` only for local testing.

## Realism Checklist

- Commission appliances with Matter QR/manual setup payloads through the Raspberry Pi Matter Server.
- Do not register fake localhost appliances from the UI.
- Ensure Weaver and the Matter Server share an IPv6-capable network path.
- Ensure mDNS/DNS-SD works for Matter discovery, or use the Matter server's supported discovery path.
- For Thread realism, use an OTBR/Thread Border Router topology rather than plain localhost containers.
- Expose web traffic through HTTPS before inviting remote users.
