# Azure IoT Edge and Deploying Modules at the Device

A factory operates hundreds of controllers, temperature sensors, and cameras. Internet connectivity occasionally drops for several hours, yet high-temperature alerts must appear immediately on the shop floor without waiting for a round trip to the cloud. The business wants local telemetry processing, forwarding only filtered data to **Azure IoT Hub**, monitoring software versions on each gateway, and updating analytics logic without manual per-machine installation.

**Azure IoT Edge** addresses these requirements by running **container modules** on edge devices orchestrated by a runtime. IoT Hub holds desired configurations and ingests data; devices pull images, start modules, route messages through `edgeHub`, and report deployment status. When connectivity drops, devices can continue processing locally; cloud-bound data can be **stored and forwarded** per policy within storage capacity, retention limits, and connectivity bounds.

This lesson sits in the **IoT and Edge Computing** chapter of the **CLOUD_PROVIDERS_AZURE** module: exploring Microsoft Azure from subscriptions/resource groups, Microsoft Entra ID, networking, compute, storage, and data through deployment, monitoring, security, and application cost control. The focus is **Azure IoT Edge and module deployment at the device**, distinct from Azure IoT Operations (a service for Azure Arc-enabled Kubernetes architectures), Azure Functions, or general Kubernetes.

After this lesson, you can:

- Explain **IoT device, IoT Edge device, IoT Hub, Device Provisioning Service (DPS), edgeAgent, edgeHub, modules, and module twins**.
- Decide when to push processing down to the edge instead of sending all raw data to the cloud.
- Prepare prerequisites: **Linux/CPU architecture, container runtime, disk, DNS, ports, device identity, and IoT Hub**.
- Build a Python/container module that filters telemetry and emits new outputs.
- Read/write a **deployment manifest** with `$edgeAgent`, `$edgeHub`, image references, create options, environment variables, and routes.
- Distinguish **single-device deployments** from **automatic deployments/layered deployments** targeting device twins/tags.
- Design **edgeHub store-and-forward**, offline operation, retries/idempotency, and local routing.
- Verify behavior in practice via **IoT Edge CLI, IoT Hub twins, module logs, and metrics**, and troubleshoot image pull, networking, route, and identity failures.
- Apply **TLS/X.509, registry credential protection, least privilege, pinning/digests, updates/rollbacks**, HA/DR, and cost governance.

## 1. When Is Edge Computing Needed?

In a pure-cloud IoT system, sensors send every record to an analytics platform in Azure. This model is simple when networking is reliable and transmission speed and cost are acceptable. However, the following conditions make **edge computing** valuable:

| Need | Cloud Only | With IoT Edge |
|---|---|---|
| Fast shop-floor response | Depends on cloud round-trip and network | Local filtering/analytics/alerting |
| Unstable Internet | Raw messages may drop/wait on device | `edgeHub` can store-and-forward |
| High-volume cameras/sensors | Large uplink, high bandwidth cost | Pre-process, aggregate, or emit events only |
| Controlling sensitive data | Raw data leaves the factory | Keep raw data local, send approved results only |
| Updating apps across many gateways | Hard-to-control manual installs | Module deployment from IoT Hub |
| Remote device operations | Needs custom tooling | Device/module twins, telemetry, and health logs |

For example, a camera produces 30 frames per second, yet the goal is merely detecting "person in danger zone" and counting events per minute. An edge AI/vision module can send **controlled metadata** to the cloud instead of shipping raw video. That does not remove data protection duties: metadata or cropped images can still hold sensitive information.

### 1.1. IoT Edge Does Not Turn a Gateway into a Mini Cloud

IoT Edge does not automatically provide every Azure capability: it does not replace transactional databases, backup models, or cloud monitoring systems. Modules must be designed to run **on finite CPU/RAM/disk**, survive sudden power loss, handle network drops, and undergo controlled upgrades.

For industrial safety tasks, critical **fail-safe/control loops** must be handled by certified hardware/PLCs and safety mechanisms. Never rely on a container or an IoT Hub command over the Internet as the sole controller where human safety or property is at risk.

### 1.2. Selection Criteria

Before choosing Azure IoT Edge, measure:

1. **Latency** required for response: milliseconds, seconds, or minutes?
2. **Offline duration** and uplink profile: continuous connectivity or multi-hour outages?
3. **Volume**: bytes/message, messages/second, device count, compression.
4. **Hardware**: CPU architecture, RAM, storage, GPU/accelerator, operating temperature.
5. **Data characteristics**: tolerance for loss/duplicates/delays, presence of PII or confidential data?
6. **Distribution**: one gateway or thousands of sites; ring-based rollout/rollback needed?
7. **Security/operability**: identities, certificates, physical access, update workflows, logging.
8. **Lifecycle cost**: hardware, IoT Hub messages, container registry, bandwidth, monitoring, on-site staff.

Only use IoT Edge when container modules/gateways fit. For embedded MCUs unable to run a Linux container runtime, connect them as **downstream leaf** devices behind an IoT Edge gateway or directly to IoT Hub; never try forcing a container runtime onto unsupported hardware.

## 2. Overall Architecture: IoT Hub, Devices, and Local Processing

~~~mermaid
flowchart LR
    S1[Sensor / PLC A] -->|MQTT/industrial adapter| G[IoT Edge gateway]
    S2[Sensor / PLC B] --> G
    subgraph EDGE[Linux Edge Device]
      A[edgeAgent]
      H[edgeHub]
      M1[sensorSimulator / protocol adapter]
      M2[telemetryFilter / local analytics]
      M1 -->|module output| H
      H -->|module input route| M2
      M2 -->|filtered output| H
      A -. run/restart containers .-> M1
      A -. run/restart containers .-> M2
    end
    G --- EDGE
    H -->|TLS, store-and-forward| HUB[Azure IoT Hub]
    HUB -->|routing/export| BUS[Event Hubs / Functions / Storage]
    BUS --> ADX[Analytics / Azure Data Explorer]
    DPS[Device Provisioning Service] -. initial identity / assignment .-> A
    REG[Azure Container Registry] -. pull signed/approved images .-> A
    OPS[Platform/SRE] -. desired deployment / twins .-> HUB
    HUB -. desired properties/status .-> A
~~~

**The diagram is a logical model:** many sensors/PLCs use appropriate adapters rather than speaking MQTT directly to a container. Device → cloud and cloud → device use separate IoT Hub channels/features with distinct quotas, permissions, and connectivity requirements.

### 2.1. Role of Each Component

| Component | Role | What It Does Not Do Automatically |
|---|---|---|
| **IoT Hub** | Identity registry, device/module comms, twins, routing, and deployment management | Does not run application containers on the device itself |
| **DPS** | Bootstraps/provisions fleets into IoT Hubs per enrollments | Does not replace `edgeAgent` running modules |
| **IoT Edge runtime** | Host system services managing identity and containers | Does not contain telemetry business logic |
| **edgeAgent** | Watches desired deployment, pulls/starts/stops/restarts modules, reports status | Not a temperature-filtering module |
| **edgeHub** | Local message broker/router, bridges modules/devices with IoT Hub, store-and-forward | Not a durable broker with exactly-once guarantees |
| **Custom modules** | Docker/OCI containers running business logic, protocol adapters, AI inference | Not automatically granted access to all Azure resources |
| **Device twin** | Desired/reported properties and tags at device scope | Does not replace a local database or sensor history |
| **Module twin** | Desired/reported properties per module | Does not make an app resilient if code ignores updates |
| **Azure Container Registry** | Stores images by tag/digest with access policies | Does not implicitly grant Edge devices permission to pull private images |

### 2.2. Data Plane and Control Plane

- **Control/management flow:** the platform sets a deployment in IoT Hub; `edgeAgent` syncs desired state and reports status. Editing the manifest can make the device swap images/containers.
- **Data plane:** sensors/modules emit telemetry to `edgeHub`, which routes locally or upstream to IoT Hub. Depending on routes, data can stay local or be forwarded.
- **Identity plane:** Edge runtime, `edgeAgent`, `edgeHub`, modules, and IoT Hub use separate identities/credentials per the IoT Edge model; admin Azure RBAC differs from device identities.

A `running` container does not prove it received sensor data; a device marked `Connected` in the Portal does not prove module business logic works. Inspect **desired/reported state, routing, and end-to-end message flow**.

## 3. How Do edgeAgent, edgeHub, and the Runtime Actually Work?

### 3.1. edgeAgent: Desired State Reconciliation

When IoT Hub sends a deployment:

~~~text
IoT Hub stores desired module configuration
     ↓
Device syncs its Edge Agent twin
     ↓
edgeAgent reads target images, env, createOptions, restart policy
     ↓
Container engine pulls images / starts or stops modules
     ↓
edgeAgent reports running state and errors
~~~

If the desired manifest specifies `telemetryFilter:2.0` yet the device cannot pull the image, **desired state changed** while the runtime may still run the old version or leave the module stopped. To evaluate a rollout, inspect **reported state** and verify business outputs—not merely deployment acceptance.

`edgeAgent` needs container runtime access and valid registry credentials. Module images should be pinned by **immutable digest** or controlled immutable tags; mutable `latest` tags easily leave two devices running different binaries under identical manifests.

### 3.2. edgeHub: Local Broker and Upstream

`edgeHub` provides **local routing** between modules/connected downstream devices and upstream IoT Hub. With `storeAndForwardConfiguration.timeToLiveSecs` configured, eligible messages can be **stored on local disk** during outages and forwarded once uplink returns.

Limits you must understand:

- Store-and-forward has a **TTL**; it does not retain forever.
- Disk needs adequate capacity and properly secured filesystem permissions.
- If the device suffers total hardware failure, local store can be lost; this is **not a backup**.
- On reconnect/retry, duplicates can occur; backends must be idempotent when needed.
- No global ordering guarantee when multiple modules/devices emit concurrently.
- If backlog exceeds disk or TTL, messages can be evicted/dropped and require alerts.

### 3.3. Runtime Host Services and Versions

On modern IoT Edge releases, the host runs identity/management services (such as **Azure IoT Identity Service**) and CLI tools `aziotctl`/`iotedge` depending on version. Components, config directories, and package names changed between IoT Edge 1.4, 1.5, and updates. **Never follow an old 1.0/1.1 tutorial assuming commands/configs apply unmodified to new devices.**

For production, pick a **Microsoft-supported release** matching your device OS/architecture, and verify release/support lifecycles and patching policies. Image tags like `:1.5` in this lesson illustrate a runtime stream; verify current image/version tags before deploying.

### 3.4. States to Distinguish

| Indicator | Meaning | What Else Must Be Verified |
|---|---|---|
| IoT Hub device identity exists | Device ID is registered | Are provisioning/keys/certs valid? |
| IoT Hub shows device connected | Device/cloud connection exists | Are `edgeAgent` and app modules healthy? |
| `edgeAgent` running | Agent container is up | Is it reconciling desired config? |
| `edgeHub` running | Local broker is up | Are routes, upstream, and local store healthy? |
| Custom module running | Container process is alive | Is it reading/emitting valid messages and ACKs/errors? |
| Deployment assigned | Desired config is saved | Do reported runtime images/digests match? |
| `edgeHub` upstream connected | Cloud channel is active | Are messages reaching the right consumer/route? |

## 4. Preparing the Device: OS, CPU, Disk, and Network

IoT Edge typically runs on a **Linux-compatible host** with a supported container runtime and release. Virtualization or Windows hosting options exist per documentation for specific scenarios, though labs here assume **Linux x86_64** or ARM64 supported by the IoT Edge runtime and images.

### 4.1. Hardware and OS Preflight

| Item | What to Check |
|---|---|
| **CPU architecture** | `amd64` vs. `arm64`; module image manifests match architecture |
| **Operating system** | Distro/kernel/container runtime supported by the chosen IoT Edge release |
| **RAM/CPU** | Enough for `edgeAgent`, `edgeHub`, 2+ app modules, peak inference/decoding |
| **Disk** | Root image layers, local store-and-forward, logs, model files, update rollbacks |
| **Clock/NTP** | Accurate UTC time for TLS certificates, SAS/token expiry, telemetry |
| **Networking** | DNS, outbound TLS to IoT Hub/DPS/ACR, proxy/firewall; local ports |
| **Identity** | Device ID and authorized enrollment/credentials |
| **Storage protection** | Filesystem permissions, disk encryption if device theft is a risk |
| **Physical security** | Tamper protection, secure boot/TPM where available, unused services disabled |
| **Observability** | Remote health/log metrics, disk space, offline queue depth |

**Do not size RAM around `edgeHub` alone:** camera/AI modules may need GPUs, driver/device passthrough, and many times the memory of JSON-filtering apps. Benchmark on actual production gateway hardware.

### 4.2. Network Paths

~~~text
Edge device outbound:
  -> IoT Hub (MQTT over TLS / AMQP over TLS / HTTPS as configured)
  -> DPS global endpoint if using DPS
  -> Container Registry over HTTPS for image pulls
  -> Optional Azure Monitor/Key Vault/backend endpoints as authorized

Local:
  sensor/protocol adapter -> module/edgeHub
  edgeHub -> local modules
  downstream leaf devices -> edgeHub gateway endpoints if enabled
~~~

Common IoT Hub ports include **8883/MQTT**, **5671/AMQP**, and **443/HTTPS/WebSocket** depending on protocol/features; pulling module images usually needs **443** to the registry. Never open **every inbound port** just because a tutorial lists protocols. Identify the exact protocol used by device/leaf hardware, certificates, firewall/proxy rules, and site security.

### 4.3. Host-Level Checks

~~~bash
# Read-only inspection; do not install/remove runtime in this example.
uname -a
uname -m
df -h
free -h
date -u

# Replace hostname with your organization's actual hub.
nslookup "<iot-hub-name>.azure-devices.net"
~~~

Successful DNS/TCP **does not prove** device authentication or TLS handshakes succeed. Running Azure CLI on an admin laptop also does not test network paths from the factory gateway.

### 4.4. Container Runtime

IoT Edge requires a compatible container engine per the support matrix (commonly **Moby** in the IoT Edge ecosystem). The runtime service needs permission to manage containers; **never** mount the Docker socket into custom modules unnecessarily. Exposing the Docker socket grants near-root control over the host.

Application containers should run as non-privileged users, enforce resource limits, use read-only filesystems where feasible, keep bind mounts minimal, and rotate logs. Never treat an edge box as a "trusted internal host" merely because it lacks a public IP.

## 5. IoT Hub and DPS: Identifying the Device Before Running Modules

IoT Hub must know **who the edge device is**. Two common provisioning paths exist:

- **Manual provisioning:** configure IoT Hub hostname, device identity, and specific auth material; fine for labs/small counts, hard to manage secrets at scale.
- **DPS provisioning:** register enrollments/attestations so devices get assigned to the right IoT Hub; ideal for fleet-scale rollouts and policy-based hub/region assignment. DPS does **not** install modules on its own; IoT Edge runtime and desired deployments are still needed.

### 5.1. Relationship Between Azure RBAC and IoT Identities

| Identity/Permission | Purpose |
|---|---|
| **Azure RBAC** (admin/automation) | Create IoT Hubs, manage identities/deployments within permitted scope |
| **Device identity** in IoT Hub | Authenticates the device to IoT Hub |
| **DPS enrollment attestation** | Proves device identity during provisioning |
| **Module identity** | Container module communicates along module/IoT Hub boundaries |
| **ACR pull identity/credentials** | Allows device/container engine to pull images |
| **Backend identity** | Consumers like Functions/Service Bus readers granted separate permissions |

**Azure RBAC Contributor never becomes a device credential.** Nor should you put an employee's Azure Portal access token into IoT Edge config files as a device key.

### 5.2. Registering an IoT Edge Device for Lab

Assuming an IoT Hub already exists in an **authorized lab subscription**:

~~~bash
az login
az extension add --name azure-iot

SUBSCRIPTION_ID="<approved-subscription-id>"
HUB_NAME="<approved-iot-hub-name>"
DEVICE_ID="edge-gateway-lab-001"

az account set --subscription "$SUBSCRIPTION_ID"
az account show --query "{name:name,id:id}" -o table

# Create only if device ID does not exist and you are authorized.
az iot hub device-identity create \
  --hub-name "$HUB_NAME" \
  --device-id "$DEVICE_ID" \
  --edge-enabled

az iot hub device-identity show \
  --hub-name "$HUB_NAME" \
  --device-id "$DEVICE_ID" \
  --output json
~~~

The commands above are **lab references**, not executed while authoring this lesson. `azure-iot` extension options vary across CLI versions; check `az iot hub device-identity create --help` when practicing. Some models using service principals require specific IoT Hub data-plane RBAC permissions beyond Azure Reader.

### 5.3. Certificates and Hardware Trust

In production, prefer **X.509 certificates with secure private-key storage/TPM/HSM** or approved attestation rather than copying one symmetric key across thousands of gateways. Each device needs a distinct identity to **revoke/rotate/investigate** without impacting the entire fleet.

If using symmetric keys in a lab, never print connection strings containing keys in shared terminals, commit them to Git, or paste them into logs/tickets. Use proper provisioning/secret injection and filesystem permissions; exact `/etc/aziot/config.toml` syntax depends on IoT Edge runtime version and auth type, so follow documentation for your chosen release.

### 5.4. Provisioning Runtime on the Device

Real-world deployment flow:

1. Ensure host OS/architecture is supported by the IoT Edge version.
2. Install **Azure IoT Identity Service, IoT Edge runtime, and container engine** at verified versions from trusted sources.
3. Configure manual/DPS provisioning on the host using secret-protecting methods.
4. Apply config; verify IoT Hub connectivity, certificates, and clock.
5. Start/inspect `edgeAgent` and `edgeHub`.
6. Push custom module deployments only after the base runtime is healthy.

Useful diagnostic commands (on a device with the runtime installed):

~~~bash
# Requires appropriate host admin privileges; these are read-only diagnostics.
sudo aziotctl check
sudo iotedge system status
sudo iotedge list
sudo iotedge logs edgeAgent --tail 100
sudo iotedge logs edgeHub --tail 100
~~~

**Never run random install scripts from the Internet** on production gateways; use device-team-approved base OS images, pinned packages, and OTA/maintenance windows. Never paste private keys/connection strings into chat.

## 6. Modules Are Containers, Yet Module Identity Differs from Container Image

An IoT Edge module comprises several parts:

~~~text
Module logical ID:    telemetryFilter
Container image:      <acr>.azurecr.io/iot/telemetry-filter:1.0.0
Image architecture:   linux/amd64 (or linux/arm64)
Desired configuration: thresholds, input/output routes, restart policy
Runtime credentials:  IoT Edge module environment / identity
Module twin:          desired and reported properties
Resource limits:      CPU, memory, storage, device mounts if needed
Logs/metrics:         stdout/stderr, app metrics, edgeAgent status
~~~

**Module ID is not the image name.** One image can run across many devices/modules, while each module keeps its own identity/twin and configuration. A container running fine on standalone Docker may fail on IoT Edge if it requires Edge-injected environment/identity variables.

### 6.1. Two Ways to Integrate with edgeHub

- **Module SDK:** the app uses the Azure IoT Device SDK to receive messages on an input and emit to a named output. The IoT Edge runtime injects module context/identity.
- **Custom adapter/process:** a container reads cameras/serial/OPC UA/local networks, converts into standard telemetry, and emits to `edgeHub` via the module SDK.

Every module should have a clear contract:

| Item | Example |
|---|---|
| Input | JSON temperature `temperatureC` from `sensorSimulator/temperatureOutput` |
| Output | Filtered alert/aggregate JSON from `telemetryFilter/filtered` |
| Failures | Bad payload → log/error counter, never crash-loop the container |
| Configuration | `TEMP_THRESHOLD_C` or module twin desired property |
| Security | Do not access camera/USB unnecessarily; no static cloud secrets |
| Recovery | Idempotent on event ID; test replay on reconnect |

### 6.2. Container Lifecycle and Restart Policy

`edgeAgent` uses desired configuration to keep modules in target state. A module with `restartPolicy: always` restarts automatically after crashes, yet **restarting endlessly does not fix misconfiguration**: wrong image architecture, missing secrets, broken routes, or immediate process exits produce crash loops.

Handle recoverable errors (malformed messages, HTTP timeouts) in business error handling; exit only when unrecoverable startup state fails and raise alerts. Never swallow exceptions and falsely acknowledge dropped data as "processed."

## 7. Hands-On Practice: Two Python Modules Generating and Filtering Telemetry

Let's build a **self-contained source-code example**:

~~~text
sensorSimulator
  └── output: temperatureOutput
            ↓ edgeHub route
telemetryFilter
  └── input: input1
       └── If temperatureC >= 35°C
             └── output: filtered
                       ↓ edgeHub route
                   Azure IoT Hub
~~~

Both modules use the **Azure IoT Device SDK for Python**, communicating through **edgeHub** rather than calling HTTP directly to IoT Hub. Temperatures and events are **synthetic**; never use this code to control machinery. The `>=35°C` rule is illustrative only, not an industrial safety threshold.

### 7.1. Illustrative Project Structure

~~~text
edge-telemetry-demo/
  sensorSimulator/
    app.py
    requirements.txt
    Dockerfile
  telemetryFilter/
    app.py
    requirements.txt
    Dockerfile
  deployment.template.json
~~~

This is an **illustrative layout for learners to create in their own repo**, not a requirement for workers to write extra files. STEP 4 only writes into the assigned Markdown.

### 7.2. Synthetic Data Emitter Module

Contents of `sensorSimulator/app.py`:

~~~python
import asyncio
import json
import os
import random
import uuid
from datetime import datetime, timezone

from azure.iot.device import Message
from azure.iot.device.aio import IoTHubModuleClient


async def main():
    interval = max(1, int(os.getenv("SENSOR_INTERVAL_SECS", "10")))
    client = IoTHubModuleClient.create_from_edge_environment()
    await client.connect()
    try:
        while True:
            payload = {
                "eventId": str(uuid.uuid4()),
                "deviceId": "simulated-sensor-01",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "temperatureC": round(31.0 + random.random() * 10.0, 2)
            }
            message = Message(json.dumps(payload))
            message.content_type = "application/json"
            message.content_encoding = "utf-8"
            await client.send_message_to_output(
                message, "temperatureOutput"
            )
            print("Emitted synthetic temperature event", flush=True)
            await asyncio.sleep(interval)
    finally:
        await client.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
~~~

**Explanation:**

- `create_from_edge_environment()` uses the module context provided by the IoT Edge runtime; this is **not** how you construct a client on a laptop lacking an Edge environment.
- `send_message_to_output(..., "temperatureOutput")` emits onto a **named output** for `edgeHub` routing.
- Each event carries `eventId` and a UTC timestamp so backends can detect duplicates/late arrivals.
- `print` avoids raw secrets/sensitive payloads; production code adds structured logs, metrics, and shutdown handling.
- The simulator is harmless; real sensors must be read over appropriate protocols/adapters (serial, Modbus, OPC UA, etc.) with unit and plausibility validation.

### 7.3. Temperature Filter Module

Contents of `telemetryFilter/app.py`:

~~~python
import asyncio
import json
import os
from datetime import datetime, timezone

from azure.iot.device import Message
from azure.iot.device.aio import IoTHubModuleClient


async def main():
    threshold_c = float(os.getenv("TEMP_THRESHOLD_C", "35.0"))
    client = IoTHubModuleClient.create_from_edge_environment()

    async def on_message_received(message):
        try:
            raw = message.data
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            payload = json.loads(raw)
            temperature_c = float(payload["temperatureC"])
            event_id = str(payload["eventId"])
        except (KeyError, TypeError, ValueError, UnicodeDecodeError) as exc:
            # Production: send safe metric / quarantine event,
            # never leak credentials or the entire untrusted payload.
            print("Invalid input telemetry:", type(exc).__name__, flush=True)
            return

        if temperature_c < threshold_c:
            return  # Local filtering; no upstream data for normal readings.

        filtered = {
            "eventId": event_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "originalTimestamp": payload.get("timestamp"),
            "deviceId": payload.get("deviceId"),
            "temperatureC": temperature_c,
            "alert": "HighTemperature"
        }
        outgoing = Message(json.dumps(filtered))
        outgoing.content_type = "application/json"
        outgoing.content_encoding = "utf-8"
        await client.send_message_to_output(outgoing, "filtered")
        print("Forwarded high-temperature alert", flush=True)

    client.on_message_received = on_message_received
    await client.connect()
    try:
        await asyncio.Event().wait()  # Receive via callback until shutdown.
    finally:
        await client.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
~~~

**Code notes:**

- `message.data` may be bytes or string depending on SDK version; the example converts explicitly.
- Callbacks in supported IoT Device SDK versions may vary by API; verify `on_message_received` and `send_message_to_output` against your pinned SDK when building.
- Below-threshold readings are dropped locally; **not every raw record goes** to IoT Hub.
- On output failure, SDKs/modules need timeout/retry policies and metrics; this simple sample lacks a **durable local transaction log**.
- If an upstream source emits the same `eventId` twice, downstream must deduplicate when business logic requires it.
- Do not treat this floating-point comparison alone as safe sensor validation; use quality flags, calibration, and plausibility checks.

### 7.4. Dockerfile per Module

Same Dockerfile template in **each module directory**, with its corresponding `app.py`:

~~~dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

# Non-root execution in the container.
RUN useradd --system --uid 10001 edgeapp
USER 10001

CMD ["python", "app.py"]
~~~

`requirements.txt` for the lab:

~~~text
azure-iot-device>=2.0,<3.0
~~~

This is an **illustrative version constraint**, not a production lockfile. In real CI/CD, pick a tested SDK version, pin exact versions/hashes, scan for CVEs, and pin base images by digest. Also verify `python:3.11-slim` hardware architecture support and security lifecycle.

### 7.5. Building Images for Target Device Architecture

On an authorized build machine with Docker/BuildKit and lab registry access:

~~~bash
ACR_LOGIN_SERVER="<approved-acr-name>.azurecr.io"
VERSION="1.0.0"

# Syntax assumes running from the edge-telemetry-demo directory.
docker build --platform linux/amd64 \
  -t "$ACR_LOGIN_SERVER/iot/sensor-simulator:$VERSION" \
  ./sensorSimulator

docker build --platform linux/amd64 \
  -t "$ACR_LOGIN_SERVER/iot/telemetry-filter:$VERSION" \
  ./telemetryFilter
~~~

For ARM64 gateways, build **`linux/arm64`** or a multi-architecture manifest per supported workflows; never deploy an amd64 image onto ARM64 and blame IoT Hub. Cross-platform builds may require Buildx/QEMU or native runners; prefer native/multi-arch CI and test on real target hardware.

### 7.6. Pushing Images to a Private Registry

~~~bash
# Only in an authorized lab; push commands mutate the registry.
az acr login --name "<approved-acr-name>"

docker push "$ACR_LOGIN_SERVER/iot/sensor-simulator:$VERSION"
docker push "$ACR_LOGIN_SERVER/iot/telemetry-filter:$VERSION"
~~~

Never put ACR admin usernames/passwords into Git or plaintext manifests. **Factory devices must have dedicated registry auth/credentials issued and rotated properly.** With private ACR, a successful push from a developer laptop does not prove the gateway has pull permissions; verify pulls from the device itself.

### 7.7. Event Contract and Handling Bad Data

| Field | Type | Meaning |
|---|---|---|
| `eventId` | string UUID | Identifies event for deduplication |
| `deviceId` | string | Logical source device |
| `timestamp` | UTC ISO 8601 | Event time |
| `temperatureC` | number | Temperature °C |
| `alert` | string | Present after filtering, e.g., `HighTemperature` |
| `originalTimestamp` | UTC ISO 8601 | Original sensor reading time |

**Never log full messages in production if payloads contain PII or PII-like sensor data.** Schemas must be versioned whenever renaming fields, switching °F/°C, or adding sensor types.

## 8. Deployment Manifest: Device-Side Module Control Contract

A **deployment manifest** declares the **desired modules and routes** `edgeAgent` and `edgeHub` must reconcile. The template below uses the common IoT Edge 1.x schema; verify against your actual CLI/runtime/IoT Hub version when applying.

### 8.1. Complete Manifest Example

Example `deployment.template.json`:

~~~json
{
  "modulesContent": {
    "$edgeAgent": {
      "properties.desired": {
        "schemaVersion": "1.1",
        "runtime": {
          "type": "docker",
          "settings": {
            "minDockerVersion": "v1.25",
            "loggingOptions": "",
            "registryCredentials": {}
          }
        },
        "systemModules": {
          "edgeAgent": {
            "type": "docker",
            "settings": {
              "image": "mcr.microsoft.com/azureiotedge-agent:1.5",
              "createOptions": "{}"
            }
          },
          "edgeHub": {
            "type": "docker",
            "status": "running",
            "restartPolicy": "always",
            "settings": {
              "image": "mcr.microsoft.com/azureiotedge-hub:1.5",
              "createOptions": "{}"
            }
          }
        },
        "modules": {
          "sensorSimulator": {
            "version": "1.0.0",
            "type": "docker",
            "status": "running",
            "restartPolicy": "always",
            "settings": {
              "image": "<approved-acr-name>.azurecr.io/iot/sensor-simulator:1.0.0",
              "createOptions": "{\"HostConfig\":{\"Memory\":268435456}}"
            },
            "env": {
              "SENSOR_INTERVAL_SECS": {
                "value": "10"
              }
            }
          },
          "telemetryFilter": {
            "version": "1.0.0",
            "type": "docker",
            "status": "running",
            "restartPolicy": "always",
            "settings": {
              "image": "<approved-acr-name>.azurecr.io/iot/telemetry-filter:1.0.0",
              "createOptions": "{\"HostConfig\":{\"Memory\":268435456}}"
            },
            "env": {
              "TEMP_THRESHOLD_C": {
                "value": "35.0"
              }
            }
          }
        }
      }
    },
    "$edgeHub": {
      "properties.desired": {
        "schemaVersion": "1.2",
        "routes": {
          "sensorToFilter": "FROM /messages/modules/sensorSimulator/outputs/temperatureOutput INTO BrokeredEndpoint(\"/modules/telemetryFilter/inputs/input1\")",
          "filteredToCloud": "FROM /messages/modules/telemetryFilter/outputs/filtered INTO $upstream"
        },
        "storeAndForwardConfiguration": {
          "timeToLiveSecs": 7200
        }
      }
    },
    "telemetryFilter": {
      "properties.desired": {
        "schemaVersion": "1.0",
        "configurationNote": "demo; threshold uses env in this lesson"
      }
    }
  }
}
~~~

**Conditions for this manifest to work:**

- Replace `<approved-acr-name>` with an authorized registry that the **real device has permission to pull from**. Empty `registryCredentials: {}` applies only to public images or **another supported registry auth mechanism**; private ACRs typically need **secure** registry auth added—never embed static passwords in docs/Git.
- IoT Edge runtime has matching supported system module images/versions; `:1.5` is an **illustrative tag**, not a guarantee of the latest patch.
- Edge host has container engine, DNS/egress, and sufficient disk.
- `createOptions` is **JSON encoded as a string** inside the outer JSON; escaping mistakes break deployments.
- Routes match **exact case-sensitive module IDs and output names** in code.
- No host ports are opened because the demo is strictly **module-to-module**; external leaf devices require dedicated `edgeHub` port/TLS setup.
- This JSON covers key structural fields, yet production deployments often require additional policy/config such as runtime registry auth, certificates, logging, volume mounts, and metadata.

### 8.2. Reading the Manifest Outside-In

| Path | Meaning |
|---|---|
| `modulesContent` | Set of desired module twin updates |
| `$edgeAgent.properties.desired` | Desired module inventory/runtime |
| `runtime.type/settings` | Container runtime, minimum engine/properties |
| `systemModules.edgeAgent/edgeHub` | System module images and lifecycles |
| `modules.sensorSimulator` | Simulator image and environment |
| `modules.telemetryFilter` | Filter image, threshold env, and restart policy |
| `$edgeHub.properties.desired.routes` | Routing rules through `edgeHub` |
| `storeAndForwardConfiguration.timeToLiveSecs` | TTL for messages waiting on uplink |
| `telemetryFilter.properties.desired` | Module twin desired data for the app if used |

**Changing an environment variable in `edgeAgent`** is not the same as **updating a module twin desired property**. Container env vars usually require container recreation/restart for the process to read new values. Module twin desired properties update dynamically, provided module code **subscribes/handles update callbacks**; this Python sample reads threshold from env at startup, so `configurationNote` in the twin does not change the threshold.

### 8.3. Why Use Explicitly Named Output Routes?

Suppose you write an overly broad route:

~~~text
FROM /messages/* INTO BrokeredEndpoint("/modules/telemetryFilter/inputs/input1")
~~~

If the filter also emits messages matching `/messages/*`, an unrestricted route can feed filtered outputs **right back into the filter's input**, creating an infinite loop and traffic spike. The demo specifies **exact module/output sources**:

~~~text
FROM /messages/modules/sensorSimulator/outputs/temperatureOutput
INTO BrokeredEndpoint("/modules/telemetryFilter/inputs/input1")
~~~

and forwards only filtered outputs:

~~~text
FROM /messages/modules/telemetryFilter/outputs/filtered
INTO $upstream
~~~

Route expressions follow `edgeHub` syntax; do not mix them up with cloud **Azure IoT Hub message routing queries**, SQL, or KQL. Module input `input1` and outputs `temperatureOutput`/`filtered` must match code and config verbatim.

### 8.4. Local Flow vs. Cloud Flow

~~~mermaid
sequenceDiagram
    participant S as sensorSimulator
    participant H as edgeHub
    participant F as telemetryFilter
    participant I as Azure IoT Hub
    S->>H: message on output temperatureOutput
    H->>F: route to input1
    F->>F: validate temperature and eventId
    alt Temperature below threshold
        F-->>F: local only; no cloud message
    else Temperature above threshold
        F->>H: message on output filtered
        alt Internet available
            H->>I: forward telemetry
        else Internet offline
            H->>H: buffer eligible message until TTL/capacity
        end
    end
~~~

**Do not assume calling `send_message_to_output` guarantees the message reached the cloud.** Depending on `edgeHub` store/disk/offline/retries/expiry, messages may arrive late or never arrive; end-to-end monitoring, correlation IDs, loss accounting, and business acknowledgements are needed.

## 9. Direct Deployment to a Single IoT Edge Device

For a single-gateway lab, you can assign a manifest via **Azure Portal** or the **Azure IoT CLI extension**. In production, use gated pipelines, image digests/approvals, and ring-based rollouts.

### 9.1. Azure Portal Workflow

1. Navigate to the right **subscription → IoT Hub → Devices**.
2. Select the device identity with **IoT Edge capability** and matching device ID.
3. Choose **Set modules / deployment** per the current UI.
4. Configure images for `sensorSimulator` and `telemetryFilter`; set registry auth using an authorized mechanism.
5. Configure **environment variables and `createOptions`/resource limits**.
6. Define routes in `$edgeHub` and store-and-forward TTL.
7. Review/validate and apply to the target device.
8. Inspect `edgeAgent` reported status, `iotedge list`, and module logs on the **real gateway**.
9. Test a high-temperature event and confirm it passes through the filter to IoT Hub upstream.

The Portal accepts desired configuration, yet **does not prove image pulls succeeded**: verify on the device runtime once connected.

### 9.2. Azure CLI: Setting Modules

Assuming a manifest file **created in the learner's own lab workspace** with valid `modulesContent` and verified registry access:

~~~bash
az login
az extension add --name azure-iot

SUBSCRIPTION_ID="<approved-subscription-id>"
HUB_NAME="<approved-iot-hub>"
DEVICE_ID="edge-gateway-lab-001"

az account set --subscription "$SUBSCRIPTION_ID"
az account show --query "{id:id,name:name}" --output table

# WRITE action: replaces desired modules for this specific lab device.
az iot edge set-modules \
  --hub-name "$HUB_NAME" \
  --device-id "$DEVICE_ID" \
  --content "./deployment.template.json"
~~~

**`set-modules` modifies remote deployment state**—it is not a read-only check. Never run it against a production gateway or a device managed by **automatic/layered deployments** without understanding precedence. Flag names or IoT Hub data-plane auth can vary by CLI extension version; check `az iot edge set-modules --help`.

### 9.3. Verifying Device and Module Twins

~~~bash
# Read-only commands to inspect state after deployment.
az iot hub device-identity show \
  --hub-name "$HUB_NAME" \
  --device-id "$DEVICE_ID" \
  --output json

az iot hub device-twin show \
  --hub-name "$HUB_NAME" \
  --device-id "$DEVICE_ID" \
  --output json

# In Bash, quote to preserve the literal $ character.
az iot hub module-twin show \
  --hub-name "$HUB_NAME" \
  --device-id "$DEVICE_ID" \
  --module-id '$edgeAgent' \
  --output json

az iot hub module-twin show \
  --hub-name "$HUB_NAME" \
  --device-id "$DEVICE_ID" \
  --module-id '$edgeHub' \
  --output json
~~~

In PowerShell, use matching single quotes so module names starting with `$` are not expanded. Never put **IoT Hub connection strings/service policy keys** into logged commands or CI output. Prefer Microsoft Entra identities/least-privilege service permissions where CLI/operations support them.

### 9.4. On-Device Verification

~~~bash
sudo iotedge system status
sudo iotedge list

sudo iotedge logs sensorSimulator --tail 100
sudo iotedge logs telemetryFilter --tail 100
sudo iotedge logs edgeHub --tail 100
sudo iotedge logs edgeAgent --tail 100
~~~

Expect `sensorSimulator` emitting steadily, `telemetryFilter` logging above-threshold events, `edgeHub` maintaining an upstream route, and IoT Hub receiving matching telemetry in the lab. **Missing telemetry** can stem from routes, input/output names, module callbacks, IoT Hub cloud routing, or offline state—even when every container shows `running`.

### 9.5. Measuring Outcomes Instead of Watching `running` Alone

| Checkpoint | Evidence to Collect |
|---|---|
| Desired config applied | Manifest/device twin shows target version |
| `edgeAgent` reconciled | Reported modules/images/statuses match |
| Image pull succeeded | No registry auth/architecture/pull errors |
| Simulator emits | Local logs/metrics show `temperatureOutput` traffic |
| Filter receives | Safe message receive counters/logs |
| Route works | Module input/output counters, `edgeHub` diagnostics |
| IoT Hub receives | Hub test consumer receives `filtered` messages |
| Offline resilience | Outage test builds backlog, reconnect flushes within TTL |
| End-to-end accuracy | Event IDs, timestamps, and payload schemas preserved accurately |

## 10. Fleet-Scale Rollouts with Automatic and Layered Deployments

With 5 lab gateways, picking one device and running `set-modules` works. With 5,000 gateways across factories, you need **fleet management** using targeted deployments, tags, priorities, device rings, and rollback workflows.

### 10.1. Targeting by Condition

IoT Hub can target devices using **device twin tags/properties**. Illustrative example:

~~~json
{
  "tags": {
    "environment": "lab",
    "site": "factory-a",
    "ring": "canary",
    "hardware": "gateway-amd64-v2"
  }
}
~~~

This is a **fragment** illustrating twin tags, not an entire IoT Hub device twin payload. Tags are typically managed by services/admins rather than self-reported by devices like reported properties; appropriate Azure/IoT Hub write permissions are required.

An automatic deployment can target:

~~~text
tags.environment='lab' AND tags.ring='canary'
~~~

Devices in the **canary ring** receive the desired module configuration. Ensure target condition syntax matches IoT Hub API/CLI rules and actual device tags; never assume naming a folder "canary" automatically groups devices in Azure.

### 10.2. Azure CLI Automatic Deployment (Lab)

~~~bash
DEPLOYMENT_ID="telemetry-filter-canary-v1"

# WRITE action targeting fleet devices matching the condition.
az iot edge deployment create \
  --hub-name "$HUB_NAME" \
  --deployment-id "$DEPLOYMENT_ID" \
  --content "./deployment.template.json" \
  --target-condition "tags.environment='lab' AND tags.ring='canary'" \
  --priority 20

# Read-only inspection of deployment metadata, targets, and metrics.
az iot edge deployment show \
  --hub-name "$HUB_NAME" \
  --deployment-id "$DEPLOYMENT_ID" \
  --output json
~~~

**Warning:** a bad target condition can hit unintended devices. Before running, list/audit matching device twins and practice with a **small lab ring**. These commands were not executed while writing this lesson; option support depends on Azure IoT extension version. Once reported successful, verify **actual device reported deployed/running states**, not just the IoT Hub API response.

### 10.3. Base and Layered Deployments

**Layered deployments** add or override parts of a configuration atop a base deployment without duplicating the whole manifest every time. Example:

~~~text
Base deployment:
  edgeAgent + edgeHub
  telemetryFilter, basic routes, logging policy

Layer for factory-a:
  extra protocolAdapter module
  related routes and settings

Layer for canary ring:
  tuned threshold / experimental module
~~~

Layers/overrides and priorities follow specific IoT Edge deployment merge/precedence rules. **Do not casually let two deployments mutate the same module twin field assuming devices pick randomly or pick the newest.** Separate responsibilities cleanly across base/layers and test the effective desired config on a test device.

### 10.4. Ring-Based Rollouts

~~~mermaid
flowchart LR
    B[Build and scan image] --> TEST[Lab gateways 1-3]
    TEST --> CANARY[Canary site: 1-5% devices]
    CANARY --> PILOT[Pilot sites: 10-20%]
    PILOT --> FLEET[Remaining fleet]
    CANARY -. Fail .-> R[Rollback approved image/manifest]
    PILOT -. Fail .-> R
    FLEET -. Fail .-> R
    R --> OBS[Verify reported state and telemetry]
~~~

Rollouts should enforce **promotion gates**:

- % of devices applying the manifest accurately.
- Rate of `running` modules, crash loops, and image pull errors.
- Telemetry lag/drops, throughput, and peak CPU/RAM/disk.
- Event/alert accuracy (false positives/false negatives).
- Number of gateways remaining offline/unverified post-deploy.
- Verified rollback on real hardware.

**Never push huge images across the entire fleet simultaneously over constrained uplinks:** it can saturate factory WANs, block `edgeHub` from flushing telemetry, and exhaust disk caches.

### 10.5. Offline Devices Receive Changes Late

Offline devices cannot see new desired configurations right away. Upon reconnecting, `edgeAgent` syncs state and reconciles per runtime strategy. Consequently:

- A `v2` deployment may run on 90% of the fleet while 10% remain on `v1`.
- Evaluate **observed/reported status** alongside device offline durations.
- Define fleet rollout deadlines and policies for chronically disconnected devices.
- Keep message schemas backward-compatible while **multiple module versions** coexist.
- Never delete old images/tags from the registry while offline devices might still need pulls/rollbacks.

### 10.6. Avoiding Conflicts Between Direct and Automatic Deployments

If an admin runs `set-modules` directly on a device while an automatic deployment also targets it, desired properties may be overridden or ordered unexpectedly. Establish **one consistent source of truth and management strategy** per fleet, recording deployment IDs and intended effective configs.

## 11. Module Twins: Desired vs. Reported and Config Updates

IoT Hub provides **device twins and module twins** to store metadata, configuration, and observed state. They are not transactional database locks guaranteeing instant application.

### 11.1. Desired and Reported Properties

~~~json
{
  "properties": {
    "desired": {
      "thresholdC": 35.0,
      "samplingIntervalSecs": 10
    },
    "reported": {
      "appliedThresholdC": 35.0,
      "configVersion": "v3",
      "lastAppliedUtc": "2026-11-20T09:10:00Z"
    }
  }
}
~~~

This illustrates **both sides of a twin**. In reality, IoT Hub also manages metadata, `$version`, and system fields; never construct twin update requests using this JSON verbatim without proper patch/version controls.

- **Desired:** cloud wants the module to enforce a 35°C threshold.
- **Reported:** module confirms whether it actually applied it (updated by module code).
- **Versioning/ack:** avoid treating a new desired value as proof the runtime applied it.

### 11.2. Module Twins Do Not Auto-Restart Processes

The manifest in Section 8 sets the threshold via `env.TEMP_THRESHOLD_C`. The filter code reads env **once at startup**. Changing `telemetryFilter.properties.desired.thresholdC` will **not change behavior** in the current code because no twin desired-change callback is registered.

To support dynamic configuration:

1. Define a desired properties schema and valid ranges.
2. On startup, read the current desired twin (via SDK) and apply valid defaults.
3. Register a callback for desired property updates.
4. Apply configs atomically without partial/half-updated states.
5. Update reported properties with version/ack/error details.
6. Fall back cleanly if config is invalid/out of range.
7. While offline, use the last known valid configuration and reconcile on reconnect.

**Never store secrets in module twin desired properties:** twins are not secret vaults. Use host-approved secret provisioning mechanisms.

### 11.3. Direct Methods vs. Cloud-to-Device Messages

| Mechanism | Suitable For | Risks |
|---|---|---|
| **Desired properties** | Target configuration state (thresholds, intervals) | Offline devices apply late |
| **Reported properties** | Health/state, applied firmware/module versions | Device must self-report; data can be stale |
| **Direct methods** | Online request-response actions on devices/modules | Timeouts/offline; not durable commands |
| **Cloud-to-device messages** | Cloud-to-device messages per IoT Hub API/limits | TTL/queue/offline semantics require design |
| **D2C telemetry** | Device-to-cloud events | Can be delayed/duplicated; not a transaction commit ACK |

Never rely on direct methods for industrial safety actuation when devices can go offline or time out; local control needs dedicated fail-safes.

### 11.4. Monitoring Desired/Reported Config Drift

A healthy fleet tracks indicators like:

~~~text
Expected image:      telemetry-filter@sha256:abc...
Reported image:      telemetry-filter@sha256:abc...
Expected threshold:  35.0 °C
Reported threshold:  35.0 °C
Last report:         within health window
Recent errors:       0
~~~

If desired says 35°C yet reported stays 37°C for hours, investigate offline status, callback handling, module version, and update errors before assuming config converged.

## 12. edgeHub Routing: Cloud Telemetry, Local Processing, and Leaf Devices

### 12.1. Data Directions

| Source | Destination | Purpose |
|---|---|---|
| Simulator module output | Filter module input | Local pre-processing |
| Filter module output | `$upstream` | Send only qualifying events to IoT Hub |
| Leaf device telemetry | Edge module input | Adapter/gateway filtering leaf data |
| Module output | Another module input | Local module chains, e.g., decode → detect → aggregate |
| Module output | Local storage | Custom durable queue/buffer when needed |

An **edgeHub route name** is just a config identifier; what decides where data flows is the `FROM ... INTO ...` expression and exact output/input paths. Name routes clearly: `rawToFilter`, `filteredToCloud`, `failedToQuarantine`.

### 12.2. Input/Output Names

~~~text
FROM /messages/modules/sensorSimulator/outputs/temperatureOutput
INTO BrokeredEndpoint("/modules/telemetryFilter/inputs/input1")

FROM /messages/modules/telemetryFilter/outputs/filtered
INTO $upstream
~~~

**Module IDs and output names are case-sensitive in routing** as declared; keep them consistent. IoT Edge routing expressions are not SQL queries; if using `WHERE` to filter on message properties, check exact syntax and verify properties are actually attached to messages.

### 12.3. Leaf Devices Behind a Gateway

Small devices incapable of running IoT Edge can connect as **downstream devices** through a gateway. In that setup:

- The gateway must support the client protocol/endpoints and certificate chain.
- Leaf devices must validate the gateway certificate properly—never disable certificate validation.
- Child/parent relationships or gateway setup in IoT Hub must be configured per the supported model.
- Inbound network access to `edgeHub` from local devices must be restricted to the site network.
- Parent gateway power loss cuts cloud connectivity for all attached leaf devices.

**Never open ports 8883/5671/443 on the gateway to the public Internet** just because downstream devices need MQTT/AMQP/HTTPS. Local segmentation, TLS, device identities, and firewalls are mandatory per threat model.

### 12.4. Route Design and Privacy

If data includes video frames or sensitive identifiers, forward only a classified subset of fields. Example:

~~~json
{
  "eventId": "evt-001",
  "site": "factory-a",
  "deviceId": "sensor-01",
  "timestamp": "2026-11-20T09:20:00Z",
  "eventType": "HighTemperature",
  "temperatureC": 39.1
}
~~~

This is a summary event with no raw video/audio. Still, `site`/`deviceId` can be sensitive operational metadata; enforce cloud-side retention and authorization.

## 13. Offline Operation and Store-and-Forward

A factory cannot rely on IoT Hub always being reachable. **Offline-first design** separates edge applications from ordinary cloud services.

### 13.1. Three Network States

| State | What Happens? | Design Requirements |
|---|---|---|
| **Online** | Modules emit; `edgeHub` forwards to IoT Hub | TLS/auth, routes, monitoring |
| **Short offline** | `edgeHub` buffers eligible messages; local modules keep running | Sufficient TTL and disk, retries, graceful degraded mode |
| **Extended offline** | Backlog grows; TTL expires, disk fills, identity/clock/cert issues may surface | Drop policies, local retention, alerts, maintenance, and manual recovery |

**Store-and-forward does not turn IoT Edge into an infinite durable message broker.** For events that must outlive TTL or never be dropped, applications need a **local durable store** (such as transactional SQLite or a durable local queue) with separately tested replay and idempotency.

### 13.2. Sizing the Backlog

Suppose a gateway emits after filtering:

~~~text
10 messages/second
1 KiB encoded payload per message
Offline window: 6 hours
~~~

Raw payload estimate:

\[
10 \times 1024 \times 6 \times 3600
=221{,}184{,}000\ \text{bytes}\approx211\ \text{MiB}.
\]

This excludes message headers/properties, MQTT/AMQP protocol overhead, `edgeHub` storage metadata, filesystem overhead, logs, and retries. Base disk sizing on **real measurements**, leaving headroom for image pulls/updates and log rotation. If three other modules also buffer backlogs, sum **total disk usage**.

### 13.3. TTL Is Not Disk Quota

In the manifest:

~~~json
{
  "storeAndForwardConfiguration": {
    "timeToLiveSecs": 7200
  }
}
~~~

A TTL of `7200` is **2 hours**. To retain up to 6 hours, raise it accordingly (e.g., 21600 seconds) and **ensure storage capacity**; increasing TTL alone creates no extra disk. Runtime/storage implementations have specific limits; during outages longer than TTL, messages expire.

**The snippet above is just a fragment** inside `$edgeHub.properties.desired`, not a full manifest. Do not assume a 2-hour TTL guarantees timely delivery on reconnect if disk fills or the backend rejects traffic.

### 13.4. Keeping Local Storage Reliable

For `edgeHub` persistence, configure storage/bind mounts/volumes strictly per your **IoT Edge runtime version** and host/container filesystem permissions:

- Choose a dedicated path/volume with adequate capacity and endurance.
- Grant read/write access to the container user without giving root across the host.
- Enable log rotation so logs never fill the buffer partition.
- Monitor free disk, inodes, I/O errors, and write latency.
- Account for SSD wear, sudden power loss, and filesystem/journal corruption.
- Encrypt local storage at rest if devices face physical theft risk.

**Never copy an IoT Edge 1.1 Docker bind-mount example** into a newer runtime without checking the storage-folder contract. A misconfigured volume mount can silently keep messages unpersisted across restarts.

### 13.5. Offline Does Not Mean Local Processing Stops

When module-to-module routes need no cloud connectivity:

~~~text
sensorSimulator -> edgeHub -> telemetryFilter
WAN / Internet disconnected
telemetryFilter can still classify temperatures and emit local alerts,
as long as runtime/containers and local dependencies stay healthy.
~~~

This is a core edge strength, yet it must be **tested on real hardware**: cloud SDKs might block during auth/init, local broker DNS could fail, or app code might depend on a cloud API. Never unplug Ethernet, see containers still `running`, and assume business logic is working.

### 13.6. Designing Event Idempotency

When uplink returns, events may be resent. Azure consumers should detect duplicates:

~~~json
{
  "eventId": "sensor-01/2026-11-20T09:20:01.123Z/42",
  "deviceId": "sensor-01",
  "originalTimestamp": "2026-11-20T09:20:01.123Z",
  "processedTimestamp": "2026-11-20T09:25:03.456Z",
  "type": "HighTemperature",
  "temperatureC": 38.7
}
~~~

Composite `eventId`s must remain **unique across reboots and clock skew**, e.g., using persisted sequences or UUIDs. Downstream uses a dedup store with sufficient TTL to avoid double-counting alerts or creating duplicate maintenance tickets. **`eventId` is an application field; `edgeHub` does not automatically enforce end-to-end exactly-once idempotency.**

### 13.7. When Events Cannot Be Lost

Audit events or legally regulated safety logs should:

1. Write to a **local durable append log/queue** with checksums.
2. Mark "sent" only after receiving an **application-level acknowledgement** per contract.
3. Persist offsets/checkpoints and retry on reconnect.
4. Deduplicate in the cloud by event ID.
5. Maintain local disk reconciliation/replay/recovery procedures.
6. Define RPO/RTO and test power loss, not just WAN disconnects.

`edgeHub` TTL alone does not satisfy these requirements. Safety controls require independent local fail-safe systems.

## 14. Multi-Layered IoT Edge Security

**Edge devices live outside datacenters:** maintenance staff, contractors, or attackers may gain physical access. Security therefore does not end at "IoT Hub uses TLS."

### 14.1. Chain of Trust

~~~mermaid
flowchart TB
    ROOT[Secure boot / hardware trust when available] --> OS[Patched host OS and container engine]
    OS --> ID[Device identity and certificate/key store]
    ID --> RUNTIME[IoT Edge runtime]
    RUNTIME --> IMAGES[Approved signed/scanned module images]
    IMAGES --> PERMS[Least-privilege container isolation]
    PERMS --> DATA[Encrypted/authenticated local and cloud data paths]
    DATA --> AUDIT[Health, audit, rotation, incident response]
~~~

**No single Azure Policy switch protects every layer.** Azure RBAC, IoT Hub identities, local OS users, ACR pull access, app secrets, and network segmentation all need clear owners.

### 14.2. Device Identity and Certificate Rotation

- Each device has its own **identity** in IoT Hub or via DPS enrollment.
- Prefer **X.509/TPM/HSM** attestation where supported and PKI exists; never share symmetric keys across sites.
- Schedule certificate expiry/rotation well ahead of deadlines.
- Maintain clock/NTP accuracy; clock drift breaks TLS/SAS signatures.
- Revoke identities of stolen, broken, or decommissioned devices.
- Rotate parent/leaf certificates if acting as a downstream gateway.

**Changing certificates or IoT Hub assignments can sever connectivity fleet-wide** if rolled out carelessly. Test on canaries and maintain secure fallback/maintenance access.

### 14.3. Registry and Module Supply Chain

| Risk | Control |
|---|---|
| Image replaced via mutable tag reuse | Pin **sha256 digest**, use immutable tags and release approvals |
| Secrets baked into images | CI secrets scanning; never `COPY .env` into Docker build context |
| Vulnerable images (CVEs) | SBOMs, vulnerability scans, scheduled base-image rebuilds |
| Leaked ACR credentials | Least-privilege pull, credential rotation, secure delivery to `edgeAgent` |
| Module escapes/abuses host privileges | Non-root, no privileged mode, minimal capabilities/mounts |
| ARM device pulls AMD64 image | Multi-arch builds/manifests and native hardware tests |
| Update breaks message schemas | Versioned messages, backward compatibility, staged rollouts |
| Oversized images | Layer optimization, bandwidth budgets, local cache sizing |

Illustrative manifests use human-readable tags. In production, lock images by **digest** as supported by container runtimes/manifests. During rollbacks, digests pinpoint exact builds rather than relying on mutable tags.

### 14.4. Environment Variables and Secrets

`env` in deployment manifests is suitable for **non-sensitive** settings like thresholds, sampling intervals, or feature flags. It is **not a secret vault**; anyone able to read desired configs or inspect containers sees the values. Never put:

- IoT Hub device connection strings;
- ACR admin passwords;
- Database connection strings with passwords;
- Azure service principal client secrets;
- Long-lived API tokens;
- Plaintext private keys/certificates.

For real secrets, use **host secret provisioning/encrypted storage, identity access, or runtime-approved/supported injection mechanisms**. Do not assume IoT Edge shares Kubernetes' Secret API or always has a direct network path to Azure Key Vault.

### 14.5. Least-Privilege Container Runtime

Best practices:

- Run apps under a **non-root UID**.
- Bind-mount only strictly necessary directories/devices.
- Set resource limits so one module cannot starve `edgeHub` of RAM/CPU.
- Restrict network egress to valid endpoints; never expose the Docker API.
- Avoid `privileged: true` and `--network host` unless explicitly reviewed and required.
- Separate camera-reading modules from cloud-egress modules when data boundaries demand it.
- Enable log rotation and never log raw credentials or PII-bearing frames.

**One compromised module can take over the entire gateway** if handed the Docker socket or privileged mounts. Treat the gateway as a multi-component environment needing isolation, not "all containers are trusted."

### 14.6. Networking and TLS

Over Internet uplinks, IoT Hub/DPS/ACR typically require TLS. Factory proxies/firewalls can break SNI, certificate chains, DNS, or long-lived connections. Never disable certificate verification or open unrestricted outbound Internet just to bypass missing routes.

For leaf devices, enable appropriate TLS/client auth, segment VLANs/subnets, and block inbound Internet access. If traffic must traverse private networks/ExpressRoute/VPN, design paths from gateways to Azure endpoints within service constraints; an Edge container does not magically turn IoT Hub traffic into Private Link.

### 14.7. Module Code Handling Untrusted Inputs

Sensor data can also be spoofed or corrupted:

~~~json
{
  "eventId": "fake-001",
  "temperatureC": 9999999,
  "timestamp": "2100-01-01T00:00:00Z"
}
~~~

Never allow unvalidated payloads to trigger dangerous actions without bounds checks, sensor identity checks, calibration, and local safety interlocks. In industrial environments, **business alarms and safety-critical shutdowns** must remain separate and certified per domain standards.

## 15. Monitoring Edge Runtime, Modules, and IoT Hub

If a module shows "running" while emitting zero data for 2 hours, a container-only dashboard falsely reports green. Monitoring must cover **fleet, runtime, messages, cloud connectivity, and business outputs**.

### 15.1. Health Layers

| Layer | Signals | Example Alerts |
|---|---|---|
| **Device host** | CPU, RAM, disk, NTP, filesystem errors, gateway temperature | Low free disk, clock drift |
| **edgeAgent** | Running modules, restart counts, desired/reported drift | Module crash loop / image pull failed |
| **edgeHub** | Local messages routed, upstream status, queue/backlog/drops | Rising offline backlog, expired messages |
| **Application modules** | Input/output counts, invalid payload rate, processing latency | Filter receiving no messages while sensor runs |
| **IoT Hub** | Connected devices, D2C messages, throttling | Fleet disconnected, quota near limit |
| **Consumer pipeline** | Event Hubs/Function/ADX ingestion lag, errors | Device emitting yet cloud not ingesting |
| **Business** | Alert timeliness, false positives/missed events | Temperature alerts slower than SLO |

### 15.2. Diagnostic Commands on the Device

~~~bash
# On lab gateway with appropriate privileges. Read-only focus.
sudo aziotctl check
sudo iotedge system status
sudo iotedge list
sudo iotedge logs edgeAgent --tail 100
sudo iotedge logs edgeHub --tail 100
sudo iotedge logs sensorSimulator --tail 100
sudo iotedge logs telemetryFilter --tail 100
~~~

Where permitted, inspect **container engine** state per policy (e.g., disk/image usage), without blindly pruning images in production. Runtime logs may expose connection details or identifiers; redact secrets before sharing.

### 15.3. Metrics Collector and Azure Monitor

Some IoT Edge versions expose **edgeAgent/edgeHub metrics endpoints** and support a metrics collector shipping metrics to Azure Monitor/Log Analytics. Configuring the collector, endpoints, authentication, and outbound ingestion cost is **not automatic**; deploy and review it per version, network, and security rules.

Target metrics to track:

~~~text
device_online
module_running
module_restart_count
edgehub_upstream_connected
edgehub_messages_sent_total
edgehub_messages_dropped_or_expired_total
edgehub_store_queue_depth
local_disk_free_bytes
module_input_messages_total
module_output_messages_total
last_telemetry_event_age_seconds
deployment_reported_version
~~~

**This is a target metric list**, not a claim that every exact name exists verbatim on IoT Edge endpoints. Several must be instrumented by app modules or derived in the backend. Verify actual Prometheus metric names/dimensions of your runtime.

### 15.4. Cloud Monitoring Goes Blind When Offline

When a gateway loses connectivity, IoT Hub/Azure Monitor sees **no new data** and lacks full local visibility. You need:

- Local log/metric retention shipped remotely after reconnect.
- Last-seen timestamps distinguishing "offline" from "broken module."
- Alerts tuned to each device's **expected reporting cadence**.
- Fleet maintenance procedures for long-disconnected units.
- Separating **clock skew** making timestamps look "in the future" from genuinely healthy devices.

**Never assume "0 alerts" means equipment isn't overheating** while uplink is down and `edgeHub` queues are overflowing. Monitor **silence** too.

### 15.5. End-to-End Correlation IDs

Example:

~~~text
EventId:    site-a/sensor-01/sequence-000042
DeviceId:   edge-gateway-lab-001
ModuleId:   telemetryFilter
Version:    1.0.0
EventTime:  2026-11-20T09:20:01Z
SentTime:   2026-11-20T09:20:02Z
IngestTime: 2026-11-20T09:27:15Z
~~~

If uplink drops for 7 minutes, analytics uses `EventTime` for when the sensor measured, while `IngestTime - EventTime` measures end-to-end lag. Never measure sensor reaction latency by cloud arrival time when the business requires **local reaction**.

### 15.6. Health Test Scenarios

1. **Disconnect cloud uplink only**, verify local sensor → filter keeps running.
2. **Reconnect** within TTL, confirm backlog flushes and duplicates are handled.
3. **Stop custom module** in test environment, confirm `edgeAgent` restarts/reports it.
4. **Block image pull** on test registry, verify deployment reported error.
5. **Send malformed JSON**, confirm module handles it without crash-looping.
6. **Simulate controlled disk pressure** on a lab gateway—never fill production disks.
7. **Upgrade module version**, verify rollout/reporting and rollback.
8. **Test invalid cert/clock skew in lab**, confirm device fails auth rather than bypassing TLS checks.

Every test needs evidence: before/after event IDs/metrics/logs, owner, blast radius, and recovery steps.

## 16. Troubleshooting: Deployment Accepted Yet Module Isn't Running

### 16.1. Common Failures Table

| Symptom | Possible Cause | What to Check |
|---|---|---|
| IoT Hub identity exists yet runtime won't connect | Bad provisioning/cert/key/DPS/clock, firewall | `aziotctl check`, host DNS, IoT Hub name, expiry |
| `edgeAgent` container not running | Moby/runtime failure, host image pull, disk | `iotedge system status`, runtime logs, disk |
| Module state `Backoff/Failed` | Container exit, bad command/permissions | `iotedge logs <module>`, `createOptions` |
| `manifest unknown`/`image not found` | Wrong tag/digest or image never pushed | ACR image references, registry endpoint |
| `unauthorized: authentication required` | Gateway lacks registry pull permission | Credentials/ACR access, rotate secret |
| `exec format error` | CPU architecture mismatch | `uname -m`, Docker manifest `linux/arm64`/`amd64` |
| Module running yet empty input | Route path/output name mismatch with code | `$edgeHub.routes`, message counters |
| Module receives input yet doesn't forward | Reading below threshold or callback/output bug | App logs, sample payload, output route |
| `edgeHub` online yet IoT Hub has no events | Missing `$upstream` route, bad cloud routing/consumer | `edgeHub` logs, IoT Hub monitor consumer |
| TLS/401/SAS expired | Bad cert chain/clock/key/identity | Host time, cert trust, provisioning |
| IoT Hub throttled | IoT Hub tier/quota, burst traffic | Hub metrics, aggregate/scale/right-size |
| Disk usage climbs while offline | TTL/backlog/host logs/images | Free space, retention, message rate |
| Data lost after long outage | TTL expired, disk full, non-persistent storage | `edgeHub` storage policies, local durable store |
| Twin config changed yet behavior unchanged | Code reads env once at startup, no twin callback | Desired vs. reported/app behavior |
| Update reached only some devices | Offline/target tags/priority/stale CLI state | Targeted deployments + reported state |
| Module crashes after rolling update | Incompatible schema, missing required env | Versioned contract, canary logs, rollback |
| KPI shows 0 messages during site outage | Cloud lacks data; doesn't prove dead sensors | Local logs, last-seen/queue health |

### 16.2. Eight-Layer Runbook

**1. Scope/ownership:** right subscription, IoT Hub, device ID, deployment ID, target condition, ring, and hardware architecture?

**2. Device identity:** device provisioned/connected to the right hub; certificates/clock/DPS assignment valid?

**3. Host/runtime:** OS/Moby/IoT Edge services, CPU/RAM/disk, `edgeAgent`/`edgeHub` running?

**4. Image:** image URI/tag/digest, ACR pull credentials, registry DNS/HTTPS, architecture compatibility?

**5. Container config:** env, mounts, `createOptions`, startup command, user permissions, logs?

**6. Local routing:** `edgeHub` routes, named module outputs/inputs, app callbacks, and payload schema?

**7. Cloud delivery:** `edgeHub` upstream connection, store queue, IoT Hub routing/consumers, quotas/ingest lag?

**8. Business verification:** sensor events arrive timely, filters don't drop real alerts, duplicates handled, dashboards don't misread stale data?

### 16.3. Scenario: Image Incompatible with ARM64

~~~text
Desired:
  telemetryFilter image: ...:2.0.0
Gateway:
  architecture: linux/arm64
Built image:
  linux/amd64 only
Observed:
  container cannot execute binary / exec format error
~~~

**Fix:** build a multi-platform image matching the target architecture, scan, push new tag/digest, and canary-rollout. Never make the registry public or enable privileged mode to mask an architecture mismatch.

### 16.4. Scenario: Off-by-One Character in Route

~~~text
App emits:  temperatureOutput
Route:      .../outputs/temperatureoutput
Result:     no messages delivered to filter input1
~~~

Both `sensorSimulator` and `telemetryFilter` show `running`. Fix the **route/output name**—do not add CPU or delete IoT Hub. Add contract tests/manifest linting in CI to catch name mismatches before production.

### 16.5. Scenario: Offline 4 Hours with Only a 2-Hour TTL

If `edgeHub` retains messages for only 2 hours during a 4-hour outage, older events expire. Raising TTL after the outage **does not recover expired messages**. Document incident data loss, inspect any local durable store/raw sensor logs, prioritize critical alerts over debug noise going forward, resize disk, and align TTL/disk with approved RPOs before the next outage.

### 16.6. Scenario: Sensor Runs Yet Cloud Stops Updating

Isolate each hop:

- Local sensor → module: are events arriving?
- Filter → `edgeHub`: are outputs emitted?
- `edgeHub` → IoT Hub: is upstream connected or backing up?
- IoT Hub → Event Hubs/Functions: are routing and consumers alive?
- Azure Data Explorer/Monitor: is data ingesting or is the dashboard querying the wrong time range?

Do not replace edge modules when the downstream cloud consumer is broken; trace every stage with `eventId`/timestamps and metrics.

## 17. CI/CD and Safe Module Change Policy

New modules must go through **source control, build, security scan, edge-environment testing, manifest review, and staged rollout**. Changing a `docker tag` on edge gateways is not as simple as updating an App Service image because edge devices can be offline, differ in CPU architecture, and sit behind slow uplinks.

### 17.1. Pipeline Overview

~~~mermaid
flowchart LR
    PR[Pull request source + deployment manifest] --> TEST[Unit tests and schema/route tests]
    TEST --> BUILD[Build multi-architecture container]
    BUILD --> SCAN[SBOM / vulnerabilities / image provenance]
    SCAN --> ACR[Push immutable image/digest to ACR]
    ACR --> LAB[Deploy lab gateway]
    LAB --> OFF[Offline/reconnect and load tests]
    OFF --> APPROVE[Security and Operations approval]
    APPROVE --> CANARY[Target small device ring]
    CANARY --> SCALE[Progressively target fleet]
    CANARY -. Unexpected errors .-> ROLLBACK[Restore last approved manifest/digest]
~~~

Pipeline inputs:

- Module code and tests.
- Dockerfile, lockfiles/requirements.
- Versioned message schemas with backward compatibility.
- Deployment templates with per-site routes/env/`createOptions`.
- Approved device target conditions/priorities or ID lists.
- Scanned and approved image digests.
- Rollback artifacts and monitoring thresholds.

### 17.2. Three-Layer Golden Tests

| Test | What It Verifies |
|---|---|
| **Unit** | Temperatures ≥35 forwarded, <35 dropped, malformed JSON handled safely |
| **Local integration** | `edgeHub` routes output → input → upstream, module identities |
| **End-to-end device** | Target-architecture gateway, offline/reconnect, disk/CPU, cloud events |

Unit-testing the threshold comparison does not replace **IoT Edge SDK and `edgeHub` integration**. If testing a Docker container on a laptop without the IoT Edge runtime, use mocks/Edge test harnesses and never treat that as proof devices hold valid production credentials.

### 17.3. Module Rollback

When `telemetryFilter:2.0` triggers false positives:

1. Pause promotion to later rings.
2. Identify affected devices and exact deployed build digests.
3. Restore desired image/config from the **last known good manifest** stored in Git.
4. Wait for offline devices to reconnect and `edgeAgent` to reconcile; never assume instant rollback while offline.
5. Verify running/reported versions and actual high-temperature event behavior.
6. Verify schema compatibility for events emitted while the faulty version ran.
7. Run data reconciliation/compensation if alert pipelines filed wrong tickets/actions.

**Rolling back a container does not "undo" already-sent events** or physical actions triggered while the bug was live. Critical workflows need event versioning, deduplication, and compensating actions.

### 17.4. Do Not Blindly Prune All Images

Gateways have limited disk. Clean up old images after rollouts, yet **never delete the last-known-good image until all sites confirm rollback readiness**. Disk pressure comes from image layers, logs, `edgeHub` store, and model weights; manage via inventory instead of running blind scheduled `docker system prune -a` across the fleet.

### 17.5. Dev, Staging, and Production Differ

- **Dev:** local Edge test harnesses/lab devices, simulators, and test registries.
- **Staging:** production-equivalent hardware, proxy/TLS/telemetry loads.
- **Production:** pinned images/digests, staged rollouts, offline recovery, change windows, and auditing.

Never share identical IoT Hub service policies or production certificates across every environment. If operational constraints require sharing a Hub, enforce strict device tagging, RBAC, quota isolation, and explicit approvals.

## 18. Gateway Availability and Resilience

A single IoT Edge gateway does not inherently have HA like an Azure zone-redundant service. If that gateway loses power, attached leaf devices lose their cloud uplink even while IoT Hub remains healthy.

### 18.1. Failure Modes

| Failure | Impact | Mitigation |
|---|---|---|
| **Internet outage** | Cloud events delayed | Local processing + store-and-forward TTL/disk |
| **Gateway power loss** | Runtime stops, local queue at risk | UPS, durable storage, safe restart |
| **Disk failure** | Cached messages/images/logs lost | Backups/clean rebuilds, durable events if required |
| **Host OS failure** | All modules down | Golden OS image, immutable config, spare gateway |
| **`edgeHub` failure** | Module routes/upstream disrupted | Monitoring, restart policy, runtime rollback |
| **ACR unavailable** | Cannot pull new images | Pin/cache good images, pre-stage updates |
| **IoT Hub quota/throttling** | Upstream slowed/rejected | Capacity planning, backoff, aggregate/filter |
| **Device identity revoked/expired** | Cloud auth fails | Identity rotation/re-provisioning plan |
| **Sensor failure** | Bad readings while edge stays `running` | Device calibration, range checks, sensor health |

### 18.2. RPO/RTO Depend on Use Case

Example:

~~~text
Temperature dashboard:
  Accept up to 5 minutes cloud lag.
  Raw normal readings may be summarized.
  Alerts require local audible signal even offline.

Industrial audit log:
  No intentional loss within 48 hours of WAN outage.
  Requires durable local log, checksums, replay, acknowledgments.
~~~

Two use cases cannot share a blanket "2-hour `edgeHub` TTL is enough." Derive RPO/RTO from data criticality, local storage limits, and safety policies.

### 18.3. Redundant Gateways

Some sites deploy **spare/hot-standby gateways**. However, two gateways reading the same sensor or emitting the same event simultaneously create duplicates, races, and ownership conflicts. You must design:

- Site-level primary/secondary management and lease/fencing.
- Clean sensor connection failover—never double-control or double-alert.
- Distinct device identities, IoT Hub routing, and deduplication.
- Synced configs, image digests/certificates, and local data recovery.
- Real failover testing across uplinks and local switches/PLCs.

**Do not assume "deploying the same module to two Edge devices" automatically gives high availability.** Azure IoT Edge does not replace dedicated industrial HA engineering.

### 18.4. Cloud Disaster Recovery

If an IoT Hub or Azure region suffers an outage:

1. Does edge local processing continue?
2. Did modules hardcode a single broken cloud endpoint?
3. Is a DPS/provisioning/multi-region strategy designed and tested?
4. Is there enough time to replay data from local stores?
5. When switching hubs, are device identities/registrations and cloud consumers ready?
6. Are cross-site duplicates prevented?

Never assume DPS automatically moves all devices to another region without an enrollment, configuration, and business recovery plan. Rehearse recovery on representative devices and regions.

## 19. Cost and Capacity Planning: Saving Bandwidth Is Not Free

The Azure IoT Edge runtime runs on the device, yet the overall solution incurs charges from **IoT Hub, DPS/identity operations, ACR, ingress/egress data, Event Hubs, Storage/ADX, monitoring, networking, and hardware**. Edge filtering cuts bandwidth and ingestion when designed well—it **does not automatically lower total cost**.

### 19.1. Components to Budget

| Cost Item | Notes |
|---|---|
| **Gateway hardware** | CPU/RAM/SSD/TPM, industrial temperature ratings, warranties, spares |
| **OS/operations** | Provisioning, patching, security, remote maintenance, on-site support |
| **IoT Hub tier/units** | Message counts, quotas, device identities/features, and throughput |
| **DPS (if used)** | Provisioning/enrollment operations per pricing model |
| **Container Registry** | Storage, pull traffic/networking, scanning, and CI builds |
| **Networking** | WAN, VPN/ExpressRoute, firewalls/proxies, egress/inter-region |
| **Streaming/processing** | Event Hubs, Functions/Container Apps, Service Bus if used |
| **Data/analytics** | Blob, Azure Data Explorer, Log Analytics, and retention |
| **Monitoring/DR** | Metrics/logs, alerts, backups/replays, test fleets, and spare hardware |

Avoid citing fixed USD/GB or USD/message numbers because **pricing and quotas vary by region, tier, date, and pricing model**. Check the Azure Pricing Calculator and quota docs when deciding.

### 19.2. Estimating Events Before and After Filtering

Suppose:

~~~text
100 gateways
5 leaf sensors / gateway
1 event / second / sensor
Payload raw average 500 bytes / event
Edge filtering retains 5% events as alerts/summary
Seconds / day: 86,400
~~~

Raw events/day:

\[
100 \times 5 \times 1 \times 86{,}400
=43{,}200{,}000 \ \text{events/day}.
\]

Total raw bytes/day:

\[
43{,}200{,}000 \times 500
=21{,}600{,}000{,}000 \ \text{bytes}
\approx21.6 \ \text{GB/day}.
\]

If only **5%** go to the cloud, event count:

\[
43{,}200{,}000 \times 0.05
=2{,}160{,}000 \ \text{events/day}.
\]

Logical raw payload drops by roughly **95%**, yet **do not assume IoT Hub bills exactly 2.16 million messages/day**: IoT Hub defines billable message size blocks and distinct operation types/tiers. Size against **actual encoded message size, rounding/quotas, routes, retries, and pricing tier**—plus system/control messages, diagnostics, and module deployments.

### 19.3. Upload Bandwidth During Reconnect Catch-Up

Suppose a site builds a 1 GiB backlog with a sustained 2 Mbps WAN upload. Theoretical transfer time ignoring overhead:

\[
\frac{1\ \text{GiB}\times8}{2\ \text{Mb/s}}
\approx 4{,}295\ \text{seconds}\approx72\ \text{minutes}.
\]

This is an **approximation** accounting for GiB vs. Mb while ignoring live traffic, ACKs/retries, IoT Hub quotas, and protocol framing. If devices keep generating 0.8 Mbps of new data, remaining bandwidth to drain the backlog shrinks sharply. **A 2-hour TTL may be too short** when WAN outages are long and catch-up is slow.

### 19.4. Hardware Performance

Simple JSON-filtering modules run on modest CPUs; video analytics/AI inference may need GPUs/NPUs and model optimization. Benchmark:

1. Local **messages/second** processed and post-filter output rate.
2. CPU/RAM per container, `edgeHub`, and host.
3. p95/p99 **local processing latency**, not only cloud ingest lag.
4. Disk write throughput and wear while offline.
5. Bandwidth/compression and post-filter Event Hubs/analytics cost.
6. Ability to pull new images over slow WANs when disk is nearly full.
7. Power/thermal throttling under real site temperatures.

Never pick a gateway sized just barely for a demo; reserve headroom for system modules, retries, log collection, certificate rotation, and side-by-side updates.

### 19.5. FinOps Guardrails

- Apply **resource tags** and owners to IoT Hub/ACR/analytics.
- Monitor real IoT Hub messages/quotas/throttling.
- Track **cost per active device/site** and cost per useful alert.
- Never ship unnecessary raw video/logs to the cloud.
- Cap debug log volume and retention.
- Shut down/delete approved **cloud lab resources** after sessions.
- Never delete modules/identities of live devices just to cut bills.
- Watch budget alerts; they are **not** hard spending caps.

**The right optimization goal:** lower total cost and operational risk **per trustworthy business event**, not merely raw bytes sent to IoT Hub.

## 20. Choosing Azure IoT Edge vs. Other Models

The Azure ecosystem offers multiple IoT processing patterns. **Not every edge workload needs the IoT Edge runtime.**

| Model | Strength | When to Consider |
|---|---|---|
| **IoT device → IoT Hub direct** | Simple setup, fewer edge hosts to manage | Devices can connect directly, low telemetry, stable network |
| **Azure IoT Edge modules** | Container modules, remote deployments, local routing/offline processing | Linux gateways needing local compute + fleet updates |
| **Azure IoT Operations on Azure Arc-enabled Kubernetes** | Kubernetes/Arc-based edge IoT architecture with a distinct management model | Organizations standardized on Arc/Kubernetes or requiring that stack |
| **Custom gateway service** | Exact hardware/protocol control | OS/runtime unsupported by IoT Edge or highly specialized requirements |
| **Cloud-only Event Hubs/Functions/ADX** | Centralized compute/analytics, easy cloud code updates | Reliable WAN, no offline processing/decisions needed |
| **PLC/RTOS local controller** | Deterministic bounded latency and hardware safety logic | Real-time/safety-critical loops unsuitable for Linux containers |

### 20.1. IoT Edge vs. Azure IoT Operations

Azure IoT Edge deploys container modules managed by **`edgeAgent`/`edgeHub`**, using IoT Hub desired deployments/twins.

Azure IoT Operations deploys on **Azure Arc-enabled Kubernetes**, managing components and protocols under a different architecture. Both serve edge processing, yet **do not share identical manifests, module twins, or runtimes**. Never copy `modulesContent/$edgeAgent` expecting to apply it to Azure IoT Operations.

### 20.2. When Are Container Modules Unnecessary?

- A simple sensor sending a few events/minute with no local processing needed.
- Always-online site connectivity where business latency tolerates cloud round-trips.
- No gateway/host capable of receiving timely security updates.
- Teams lacking capacity to operate OS/PKI/container images across thousands of sites.
- Workloads needing RTOS/PLC determinism or safety certification.

Edge computing pays off when **local latency, offline resilience, and bandwidth savings outweigh fleet operations and hardware costs**.

## 21. Case Study: Factory with 200 Gateways and Thousands of Sensors

**Hypothetical scenario:** A manufacturer runs 10 factories totaling **200 IoT Edge gateways**. Each gateway connects to 30 sensors via an industrial adapter. Factory-to-Azure WAN drops for 2–6 hours occasionally. Management wants regional temperature/vibration trends and anomaly alerts, while operations must roll out filter module updates across device rings.

Requirements:

- Local alarms fire within seconds even when Internet is down.
- Normal raw telemetry aggregates once per minute; send only threshold breaches or summaries.
- No personally identifiable info or raw camera feeds leave for the cloud.
- Every device has an individual identity revocable if lost.
- Deployments progress **lab → canary → pilot → fleet**, with rollback.
- 6-hour offline queue with disk headroom—**never treated as a permanent backup**.
- Azure cloud analytics tracks p95 ingest lag and alert rate/site.
- Every module/schema/threshold change is versioned with an owner.

### 21.1. Architecture

~~~mermaid
flowchart TB
    subgraph SITE[Factory site]
      S[30 leaf sensors] --> ADAPT[Protocol adapter module]
      ADAPT --> HUB[edgeHub]
      HUB --> FILTER[Telemetry filter / aggregation module]
      FILTER --> HUB
      ALARM[Local alarm controller] <-->|Validated local event| FILTER
      AGENT[edgeAgent] -. manages .-> FILTER
      AGENT -. manages .-> ADAPT
      DISK[(Local disk / durable log)] -. offline buffer .-> HUB
    end
    HUB -->|HTTPS/MQTT TLS when online| IOT[Azure IoT Hub]
    DPS[DPS / device identity] -. provisioning .-> AGENT
    ACR[Azure Container Registry] -. image pull .-> AGENT
    IOT --> EH[Event Hubs / Function]
    EH --> ADX[Azure Data Explorer]
    EH --> BLOB[Blob archive]
    MON[Azure Monitor / SRE] -. diagnostics .-> IOT
    MON -. diagnostics .-> ADX
~~~

The **Local alarm controller** shown is an independently engineered/certified system; the telemetry filter module can supply **information** to it per contract, never replacing certified factory safety cutoffs.

### 21.2. Device Identity and Grouping

Each gateway carries tags:

~~~json
{
  "tags": {
    "environment": "prod",
    "site": "factory-b",
    "ring": "canary",
    "hardware": "arm64-v2",
    "dataClassification": "industrial-telemetry"
  }
}
~~~

Tags are managed by cloud admins; never put secret keys into tags. Deployments target only `hardware=arm64-v2` with matching ARM64 images. Tagging `site` helps scope rollouts; still audit matching device lists before applying.

### 21.3. Module Output Schema

~~~json
{
  "schemaVersion": 2,
  "eventId": "factory-b/gateway-17/seq-90873",
  "site": "factory-b",
  "gatewayId": "gateway-17",
  "sensorId": "motor-temp-07",
  "originalTimestamp": "2026-11-20T09:20:01Z",
  "processedTimestamp": "2026-11-20T09:20:02Z",
  "eventType": "HighTemperature",
  "temperatureC": 38.7,
  "quality": "validated"
}
~~~

Cloud consumers use `schemaVersion`, `eventId`, and UTC timestamps to parse, deduplicate, and measure lag. Event schema updates must stay **compatible with older modules** while multi-day fleet rollouts run across offline units.

### 21.4. Store-and-Forward Design

Outages last up to 6 hours; `timeToLiveSecs` must cover 6 hours **plus backlog catch-up time**, not merely 21600 seconds if post-reconnect ingestion is slow. Yet raising TTL without expanding disk or reducing message rates still overflows queues. For zero-loss events, add a **local durable log and replay ACKs**.

In the cloud, IoT Hub message dashboards alone are **insufficient**: track per-gateway last-seen, offline queue/backlog/drop metrics, and per-site ingestion lag.

### 21.5. Ring Rollout

~~~text
Ring 0: 2 lab gateways (1 amd64 + 1 arm64)
Ring 1: 10 canary gateways across several sites
Ring 2: 40 pilot gateways
Ring 3: 148 remaining gateways
~~~

Numbers illustrate a 200-device fleet. At every stage, verify:

1. Image pull success and module uptime.
2. Upstream schema accuracy and drop rates.
3. CPU/RAM/disk within bounds.
4. Local alert latency and cloud ingest lag.
5. No regressions across other hardware/firmware/architectures.
6. Reconnect and **rollback** on at least one updated gateway.

### 21.6. Incident: Filter Update Leaves Cloud with 0 Alerts

Module v2 renamed its output from `filtered` to `alerts`, while the deployment still routed `.../outputs/filtered INTO $upstream`.

Symptoms:

~~~text
edgeAgent reports: module running
module logs:       "HighTemperature forwarded" 
edgeHub route:     still expects output "filtered"
IoT Hub:           0 new alerts from affected devices
~~~

**Root cause:** output contract/route mismatch—not Azure SQL or IoT Hub quotas. Mitigation is updating the route or rolling back the image/manifest **together**, then verifying event IDs reach the cloud. Add **manifest/schema contract tests** in CI before the next release.

### 21.7. Incident: WAN Outage Overfills Backlog Disk

Site A lost uplink for 8 hours while TTL was only 2 hours and flash storage was nearly full. Upon reconnecting, the cloud received only part of the events.

**You cannot fix this by raising TTL after the outage.** Log the incident data loss, inspect any surviving local durable store/raw sensor logs, prioritize critical alerts over debug traffic going forward, expand disk, and align thresholds/replay with RPOs.

### 21.8. Case Study Takeaways

A reliable IoT Edge system is **full-chain engineering**:

~~~text
Device identity
  -> trusted host/runtime
  -> approved module images
  -> local adapter/edgeHub/filter routes
  -> bounded offline storage
  -> secure IoT Hub delivery
  -> cloud ingestion and analytics
  -> SLO/incident evidence and rollback
~~~

Merely seeing a manifest accepted by IoT Hub—without proving routes, offline resilience, image architecture, and business SLOs—does not mean a site is production-ready.

## 22. Comprehensive Hands-On Lab: Deploying and Verifying a Module on a Device

**Prompt:** You are given **one lab IoT Hub, one Linux IoT Edge device, one lab ACR, and an approved subscription**. Deploy `sensorSimulator` and `telemetryFilter` from Section 7 with a 35°C threshold, forwarding only alerts via `edgeHub` to the cloud. If you lack a physical device, complete the **manifest analysis, design, and result-interpretation** portions without provisioning Azure resources or registering devices outside your permissions.

### 22.1. Tasks

1. **Architecture:** diagram sensor → adapter/module → `edgeHub` → filter → IoT Hub → Event Hubs/ADX, separating data plane and control plane.
2. **Device:** build a verification table for Linux/CPU architecture/RAM/disk/clock/ports and runtime version.
3. **Identity:** explain differences among device identity, DPS enrollment, IoT Hub RBAC, module identity, and ACR pull credentials.
4. **Source code:** have `sensorSimulator` emit JSON with `eventId`, UTC timestamp, and °C temperature; filter validates schema/bounds.
5. **Container:** write a non-root Dockerfile, build for the right architecture, and pin dependencies for production.
6. **Registry:** push both images with clear tags/digests; verify the device can pull from private ACR securely.
7. **Manifest:** author `modulesContent` containing `$edgeAgent`, `$edgeHub`, both modules, routes, and TTL.
8. **Routes:** explain input `input1` and outputs `temperatureOutput`/`filtered`; prove no routing loop exists.
9. **Deployment:** use Portal or `az iot edge set-modules` on the exact lab device and record the change ID.
10. **Readback:** inspect `edgeAgent` reported state, `iotedge list`, and per-module logs.
11. **Message validation:** at 34°C, emit no cloud alert; at 39°C, emit the expected event.
12. **Bad payload:** send JSON missing `temperatureC`; prove the module does not crash.
13. **Offline:** disconnect Internet for 15 minutes; verify local processing and cloud backlog.
14. **Reconnect:** verify in-TTL messages flush; record evidence on duplicates/late arrivals.
15. **TTL/disk:** calculate backlog for 10 msg/s × 1 KiB × 6 hours; determine disk headroom.
16. **Twin:** update desired `thresholdC` while code reads env only; explain why reported/behavior don't change.
17. **Fleet:** write a target condition for tag `ring=canary`; explain how to avoid targeting production accidentally.
18. **Rollout:** describe lab/canary/pilot/fleet stages, success metrics, and rollback criteria.
19. **Security:** list 5 secrets prohibited in manifest `env` and outline rotation procedures.
20. **Monitoring:** design a dashboard with at least 8 metrics covering host/disk, runtime, routes, upstream, last-seen, and cloud lag.
21. **Troubleshooting:** explain `exec format error`, `unauthorized` image pull, and mismatched route output names.
22. **Resilience:** if the gateway loses power, what data can be lost and why isn't `edgeHub` TTL a backup?
23. **Cost:** compute daily events for 100 gateways × 5 sensors × 1 message/s if filtering retains 5%.
24. **Cleanup:** identify which lab cloud resources may be deleted and which shared resources must stay untouched.

### 22.2. Reference Results

**Q8 — loop-free routes:**

~~~text
sensorSimulator.temperatureOutput → telemetryFilter.input1
telemetryFilter.filtered → $upstream
~~~

Using `FROM /messages/*` into the filter input risks feeding the filter's own outputs right back into its input; always specify exact module/output sources.

**Q11 — accurate filtering:** with a 35.0°C threshold, `temperatureC=34.0` is dropped locally and `temperatureC=39.0` emits to `filtered`. Never treat this logic as certified safety control.

**Q15 — buffer sizing:** 10 × 1024 × 6 × 3600 = 221,184,000 bytes ≈ **211 MiB raw payload** before overhead/replication/logs. Measure real usage and add headroom rather than provisioning a volume at exactly 211 MiB.

**Q16 — twin drift:** when code reads `os.getenv("TEMP_THRESHOLD_C")` only at startup, desired twin updates to `thresholdC` are ignored. Add a desired-properties callback/reported ACK, or roll out updated env/containers.

**Q17 — canary target:**

~~~text
tags.environment='lab' AND tags.ring='canary'
~~~

Audit matching twins and IoT Hub permissions before automating. If no devices carry ring tags yet, this matches 0 devices—never widen the condition to `true` just to "get results."

**Q19 — secrets:** IoT Hub connection string, device private key, registry password, service principal client secret, database password, access token. Those are six examples—all require dedicated protection and rotation.

**Q21 — errors:**

- `exec format error` → check image CPU architecture/entrypoint.
- `unauthorized` on ACR pull → verify registry identity/credentials/permissions; never enable admin user recklessly.
- Route output name mismatch → fix `$edgeHub.routes`/SDK output contracts; never open firewalls.

**Q23 — figures:** 100 × 5 × 86,400 = **43,200,000 raw events/day**; 5% leaves **2,160,000 filtered events/day**. IoT Hub billed messages may differ due to message chunk size, tier, and operations.

### 22.3. Recommended Test Matrix

| Case | Input/Condition | Expected | Evidence |
|---|---|---|---|
| A | Temperature 30°C | No cloud alert | Local receive counter increments; output stays flat |
| B | Temperature 39°C | One valid cloud alert | Filter output and IoT Hub consumer `eventId` |
| C | Missing temperature field | Module stays up | Invalid payload metric + process alive |
| D | WAN offline 15 minutes | Local processing continues | Local logs, queue/backlog counters |
| E | WAN reconnect within TTL | Eligible events arrive eventually | Timestamp/`eventId`/dedup evidence |
| F | Bad ACR credentials | Pull/reconcile error, no false success | `edgeAgent` logs/reported status |
| G | Wrong CPU architecture | Module fails to start | Device architecture + image manifest |
| H | Wrong route output name | Modules run yet zero upstream events | `edgeHub` route/counters |
| I | New deployment to canary | Only matching devices update image | Target twin tags and reported versions |
| J | Rollback to previous digest | App behavior recovers | Runtime image digest and business telemetry |
| K | Disk pressure in lab | Alert and controlled degradation | Disk/`edgeHub` queue metrics |
| L | Expired cert/clock skew lab | Auth failure detected | Device checks/cert audit |

**Never run power-loss, disk-full, or credential-revocation tests on production devices.** Disruptive tests belong in lab/staging with owners and recovery plans.

### 22.4. Completion Criteria

The lab passes when:

- Manifest **parses as valid JSON** and defines both modules and routes accurately.
- Module images exist for the right platform and the device pulls them securely.
- IoT Hub desired state and `edgeAgent` reported state match reality.
- Input/output routes have evidence from both local and cloud events.
- During a 15-minute outage, local processing continues and store-and-forward works within tested bounds.
- Potential data loss, duplicate/replay handling, and secret security are explicitly documented.
- Canary/rollback/metrics/FinOps and cleanup plans are in place.

## 23. Production Deployment Checklist

### 23.1. Before Registering Devices

- [ ] Confirmed use case genuinely benefits from edge computing, not just one sensor sending occasional events.
- [ ] Verified supported OS, IoT Edge runtime version, and CPU architecture.
- [ ] Benchmarked CPU/RAM/disk under peak load, store-and-forward, and image updates.
- [ ] Configured reliable UTC/NTP time, filesystem permissions, and log rotation.
- [ ] Designed IoT Hub/DPS/device IDs/attestation/certificate rotation.
- [ ] Configured network egress/DNS/proxy/TLS and local leaf-device segmentation.
- [ ] Scoped cloud/admin RBAC and secrets to least privilege.
- [ ] Assigned owner-managed device/site/hardware/ring tags.

### 23.2. Before Creating a Deployment

- [ ] Built images for exact `linux/amd64`/`linux/arm64` targets and scanned CVEs/SBOM.
- [ ] Approved immutable tags/digests; base images have a patching cadence.
- [ ] Containers run non-root with resource limits and minimal mounts.
- [ ] Zero hardcoded credentials/tokens/passwords in images/env/manifests.
- [ ] `$edgeAgent`/`$edgeHub` schema versions and images match the runtime.
- [ ] Module IDs/inputs/outputs/routes are consistent and loop-free.
- [ ] `createOptions` properly JSON-escaped with verified filesystem permissions.
- [ ] Store-and-forward TTL/disk sized to RPO, WAN outages, and backlog rates.
- [ ] Desired/reported twin behavior and dynamic config include contracts/ACKs/versions.
- [ ] Fleet target conditions/rings/priorities reviewed to avoid unintended devices.

### 23.3. Post-Deployment

- [ ] Module desired state and reported state match; image digests verified.
- [ ] `edgeAgent`, `edgeHub`, and custom modules run cleanly without crash loops.
- [ ] Sensor events follow named routes; filter outputs match schema.
- [ ] End-to-end IoT Hub consumer receives test messages with `eventId`/timestamps.
- [ ] Offline/reconnect behavior verified on a representative gateway.
- [ ] Modules reject malformed payloads without leaking PII/secrets.
- [ ] Local disk/queue/backlog/drop metrics and last-seen monitors operational.
- [ ] Alerts have owners, change tickets, and incident runbooks.
- [ ] Canary metrics pass before expanding fleet-wide.
- [ ] Previous image/digest retained and rollback tested.

### 23.4. Ongoing Operations

- [ ] Monitor host CPU/RAM/disk, certificate expiry/clocks, and `edgeAgent` restarts.
- [ ] Monitor IoT Hub quotas/throttling, upstream connectivity, and cloud ingestion lag.
- [ ] Audit unused device identities and registry permissions.
- [ ] Rotate secrets/certificates on schedule and test on canaries.
- [ ] Patch OS, container engine, and IoT Edge runtime on supported versions.
- [ ] Inspect site power, networking, spare hardware, and maintenance schedules.
- [ ] Keep message schemas backward-compatible during staggered rollouts.
- [ ] Rehearse WAN outages, reboots, rollbacks, and device re-provisioning.
- [ ] Review data retention/PII, cost per site, and high-value event sources.

### 23.5. Incident Response

- [ ] Confirm IoT Hub/device/site and exact scope of affected devices.
- [ ] Distinguish host failures, device identity failures, image pulls, module crashes, routes, upstream, and consumers.
- [ ] Never open public inbound ports or disable TLS to work around networking issues.
- [ ] Check offline TTL/backlog/disk before assuming events are lost.
- [ ] Never wipe all container images/logs before capturing evidence and rollback paths.
- [ ] On rollback, verify actual running module digests and business outputs—not desired status alone.
- [ ] When cloud sees 0 events, check local sensors and **ingestion freshness**.
- [ ] Document impact, data loss/duplicates, recovery, and preventive actions.

## 24. Safe Lab Cleanup

A lab exercise can create IoT Hub device identities, ACR images, deployment configurations, and dedicated cloud resources. However, an IoT Hub, ACR, or resource group may be **shared** across teams—never delete blindly.

### 24.1. Inventory

~~~bash
az account show --query "{id:id,name:name}" -o table

az iot hub device-identity show \
  --hub-name "$HUB_NAME" \
  --device-id "$DEVICE_ID" \
  --output json

az iot edge deployment list \
  --hub-name "$HUB_NAME" \
  --output table

az resource list \
  --resource-group "<approved-lab-resource-group>" \
  --output table
~~~

These are **read-only** commands, run once variables are verified and permissions confirmed. CLI extension versions may vary in syntax/subcommands.

### 24.2. Cleanup Procedure

1. Confirm the right subscription, IoT Hub, and that the **lab device** is stopped.
2. Check whether any device/automatic deployment targets production or uses a shared IoT Hub.
3. Archive logs/test evidence needing retention—**never** save private keys/access tokens.
4. If important data exists, handle export/backfill/retention before deleting.
5. Delete **only lab-specific deployments/device identities/images** after owner approval.
6. Never delete a shared ACR registry or IoT Hub simply because lab images were pushed there.
7. Review Private Endpoints/Log Analytics/Event Hubs/Blob if provisioned specifically for the lab.
8. Shut down/reimage/decommission demo hardware per device security procedures.
9. Check Cost Management to confirm no unexpected billable resources remain.

The following delete actions are **commented examples only**, not instructions to run:

~~~bash
# DO NOT RUN ON YOUR OWN without owner approval and dependency review:
# az iot hub device-identity delete \
#   --hub-name "$HUB_NAME" --device-id "$DEVICE_ID"

# Deleting a resource group destroys ALL resources in the group;
# appropriate only if 100% of the group is dedicated solely to the lab.
# az group delete --name "<approved-lab-resource-group>" --yes
~~~

**Never delete an Edge identity belonging to a long-offline gateway** merely because it didn't check in today; that gateway may still be running locally waiting to reconnect.

## 25. References and Key Takeaways

In real deployments, consult Microsoft documentation matching your exact **IoT Edge runtime version/OS/architecture** before picking packages, image tags, CLI extensions, or device provisioning workflows:

- [Azure IoT Edge overview](https://learn.microsoft.com/azure/iot-edge/about-iot-edge?view=iotedge-1.5) — runtime, modules, `edgeAgent`/`edgeHub`.
- [Deploy modules with Azure Portal](https://learn.microsoft.com/azure/iot-edge/how-to-deploy-modules-portal?view=iotedge-1.5) — manifests, custom images, and routes.
- [Develop and deploy modules](https://learn.microsoft.com/azure/iot-edge/module-composition?view=iotedge-1.5) — module identity, communication, and composition.
- [Operate IoT Edge offline](https://learn.microsoft.com/azure/iot-edge/how-to-configure-offline?view=iotedge-1.5) — local store, TTL, and storage.
- [Monitor and troubleshoot IoT Edge](https://learn.microsoft.com/azure/iot-edge/how-to-monitor-iot-edge?view=iotedge-1.5) — device/module metrics/diagnostics.
- [IoT Edge troubleshooting](https://learn.microsoft.com/azure/iot-edge/troubleshoot?view=iotedge-1.5) — runtime checks and deployment errors.
- [IoT Hub device twins](https://learn.microsoft.com/azure/iot-hub/iot-hub-devguide-device-twins) — tags, desired/reported properties.
- [Azure IoT Device Provisioning Service](https://learn.microsoft.com/azure/iot-dps/about-iot-dps) — enrollment/attestation/assignment.
- [Azure IoT Hub quotas and throttling](https://learn.microsoft.com/azure/iot-hub/iot-hub-devguide-quotas-throttling) — capacity planning.

**Timeliness note:** specific features, runtime releases, and command names can change; `:1.5` in examples does not imply "latest." This lesson does not claim IoT Edge replaces PLCs/RTOS or that every SDK/registry credential feature works identically to Kubernetes.

**Ten key points to remember:**

1. **IoT Edge provides local container processing** when latency, bandwidth, offline resilience, and fleet governance matter.
2. **`edgeAgent` manages desired state**, while **`edgeHub` routes and buffers messages**; both are distinct from custom business modules.
3. **Device identities, module identities, registry auth, and Azure RBAC** have separate scopes.
4. **A module is container image + deployment contract + module twin**, not just a Dockerfile.
5. **Routes must match module/output/input names** and avoid loops; zero cloud telemetry does not prove a module crashed.
6. **Store-and-forward has TTL/disk limits**; it is neither an infinite durable queue nor an exactly-once backup.
7. **Offline-first requires real design and testing**: clocks, networks, disks, retries, replays, idempotency, and local safety.
8. **Deploy in rings with verified rollbacks**; offline devices receive desired versions late.
9. **End-to-end security:** OS/certs/hardware, pinned images, non-root containers, secrets, TLS, networking, and least privilege.
10. **Measure final outcomes:** local reaction SLO, actual module version, upstream delivery, ingest freshness, data loss, and total cost per useful event.

An **Azure IoT Edge and device module deployment** is only complete when backed by evidence that **devices are properly identified, images pull and run on the target hardware, `edgeHub` routes deliver accurately, modules keep operating within design bounds during outages, data forwards and monitors cleanly after reconnect, and upgrades or rollbacks are safely controlled**.
