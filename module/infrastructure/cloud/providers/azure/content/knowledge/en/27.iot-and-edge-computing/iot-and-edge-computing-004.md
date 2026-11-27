# Device Twin, Direct Method, and Cloud-to-Device Message

In the **CLOUD_PROVIDERS_AZURE** module, we explore the Microsoft Azure ecosystem from subscriptions, resource groups, and Microsoft Entra ID through virtual networks, compute, storage, and data; the goal is to deploy, monitor, secure, and control the cost of application architectures on Azure. In the **IoT and Edge Computing** chapter, this lesson focuses on **Azure IoT Hub** and three mechanisms for controlling and synchronizing state from the cloud to devices: **device twin**, **direct method**, and **cloud-to-device (C2D) message**.

Imagine an enterprise managing 50,000 temperature sensors and smart refrigerators. The cloud wants to change the telemetry collection interval, ask an online device to capture a diagnostic snapshot, and send an operational notice to a device that may currently be offline. All three actions go cloud → device, yet **they should not share one mechanism**: long-lived configuration state differs from a call needing an immediate response, and both differ from a message waiting for a device to connect.

After this lesson, you can:

- Distinguish **desired properties, reported properties, and tags** in a device twin; understand eventual synchronization, versions, ETags, and optimistic concurrency.
- Choose **direct method** when request–response is needed for an online device; handle timeouts and unknown execution outcomes.
- Choose **C2D message** for one-way messages queued temporarily while a device is offline, within TTL/quota limits.
- Understand the difference between **transport acknowledgement**, **business acknowledgement**, and **actual state applied by the device**.
- Design device handlers with the **Java IoT SDK**, separate service-side from device-side responsibilities, and combine IoT Hub with Azure Functions/Service Bus/Storage when needed.
- Secure IoT flows with **device identity, service-side Microsoft Entra ID/RBAC, SAS/X.509, TLS**, authorization, and idempotency.
- Build telemetry/tracing, alerting, offline/failover runbooks, and testing for thousands of devices without triggering command storms.

## 1. Role of Azure IoT Hub in Device Control

**Azure IoT Hub** provides a managed communication layer between cloud applications and authenticated devices. Devices typically establish outbound connections to IoT Hub; the cloud does not need to know a device's IP or open an inbound port on the device.

```text
                      Cloud control plane
               Java service / Azure Functions
                          |
                 Azure IoT Hub APIs
                   /      |      \
                  /       |       \
           Device twin  Direct   Cloud-to-device
           properties   method       message
                  \       |       /
                   \      |      /
                 IoT Hub device identities
                          |
                MQTT / AMQP / HTTPS*
                          |
                     Edge devices
                  /        |        \
                sensor    gateway   controller

* Capabilities of each mechanism depend on transport/SDK; do
  not assume HTTPS polling has all features like MQTT/AMQP.
```

Devices can simultaneously send **device-to-cloud telemetry (D2C)** reporting readings, state, and long-running execution outcomes. However, D2C telemetry is a separate stream; IoT Hub accepting a message from a device does **not** automatically prove a cloud command succeeded or that data was durably committed to a business database.

### 1.1. Cloud Control Is Not Direct RPC Over the Internet

A direct method follows a request–response model, yet travels **through IoT Hub** and depends on the device being connected, having a registered handler ready, and responding before timeout. A device twin carries **desired state and reported state**, not RPC. A C2D message is **one-way asynchronous communication** buffered temporarily per hub/TTL rules, without guaranteeing the device completed business execution.

### 1.2. Three Questions to Choose a Mechanism

Before sending an operation down to a device, ask:

1. Is this **configuration/state that needs convergence** or an action that occurs once?
2. Does the cloud need the result **immediately within the current request**?
3. Might the device be **offline for hours** and need to receive the message after returning?

From those answers, pick the mechanism, acknowledgement requirement, and recovery strategy.

## 2. Decision Table: Twin, Direct Method, or C2D?

| Criterion | **Device twin** | **Direct method** | **C2D message** |
|---|---|---|---|
| Primary purpose | Synchronize desired configuration/state and reported state | Invoke an action and receive a response within a time limit | Send a one-way message for asynchronous processing |
| Device offline | Desired state remains stored; device syncs upon connecting | Fails if device is unreachable or lacks a handler | Message can wait in per-device queue, **within TTL/quota** |
| Cloud receives sync result | No; check reported properties/other evidence | Yes, receives status/payload from handler if timely | No synchronous business response |
| Data semantics | **Latest state** matters; does not retain every intermediate change | Invocation has a deadline, no offline queue | Message stored and delivered per capabilities/TTL |
| Retry/duplicate | Desired applies must be idempotent; versions prevent stale overwrites | Timeouts can leave an **unknown outcome**; retries must be idempotent | May be delivered/reprocessed multiple times; use message ID |
| Capacity | Twin JSON has size/quotas; not for large data streams | Request/response payloads are size-limited | Message payload/properties have size limits and TTL |
| Example | `telemetryIntervalSec=60` | `captureDiagnostics()` | `maintenanceNotice` notification |
| Completion tracking | Reported + job/telemetry | Method response; long-running still needs telemetry/twin | Application-level D2C/twin ACK, not just transport feedback |

### 2.1. What Goes Wrong When Choosing Poorly?

- Using twin for `reboot` as a boolean `true`: on reconnect, desired is still `true` and the device can **reboot repeatedly**.
- Calling direct method `installFirmware` that takes 30 minutes: the method times out, leaving the cloud blind to whether the device is still updating.
- Sending a C2D message and treating "accepted by hub" as "device completed it": **wrong acknowledgement layer**.
- Using the C2D queue for long-lived config while devices stay offline past TTL: devices may **never receive** the config.

### 2.2. One Workflow Can Combine Multiple Mechanisms

A firmware v2 rollout might:

1. Cloud writes **desired** target version and rollout ID.
2. Device syncs, validates, and updates **reported** `downloading` → `installed`.
3. Cloud invokes **direct method** `startUpdate` for online devices when immediate trigger is needed.
4. **C2D message** sends a short notification to devices that might be offline, without serving as the sole source of truth.
5. Service records audit/rollout history in a database, using telemetry and reported state to confirm completion.

Critical commands often need a dedicated **business command store** outside IoT Hub for auditing, deduplication, and orchestration.

## 3. What Is a Device Twin?

Every IoT Hub device identity has a **device twin**, a JSON state document managed by IoT Hub. It typically includes:

- **`tags`:** service-side metadata for grouping/querying; devices do not read tags directly via the device twin API.
- **`properties.desired`:** cloud-desired state updated by cloud/service; devices read it and receive change notifications where supported.
- **`properties.reported`:** device-reported state updated by the device; cloud/service reads it to observe actual device state.
- **Metadata/version:** IoT Hub manages `$version`, update timestamps, and ETags/metadata across sections.

### 3.1. Device Twin Example

```json
{
  "deviceId": "fridge-042",
  "tags": {
    "site": "hcm-warehouse-02",
    "model": "coldstore-v3",
    "environment": "production"
  },
  "properties": {
    "desired": {
      "telemetryIntervalSec": 60,
      "temperatureTargetC": 4.0,
      "firmware": {
        "targetVersion": "2.4.0",
        "rolloutId": "rollout-20261120-b"
      },
      "$version": 27
    },
    "reported": {
      "telemetryIntervalSec": 30,
      "temperatureTargetC": 4.0,
      "firmware": {
        "currentVersion": "2.3.1",
        "status": "downloading",
        "appliedRolloutId": "rollout-20261120-a"
      },
      "lastAppliedDesiredVersion": 26,
      "$version": 48
    }
  }
}
```

**This is a simplified illustrative JSON**, not the full twin returned by the API. Fields like `deviceId`, `$version`, and system metadata are managed by IoT Hub; applications **do not send `$version` manually inside a desired patch**. Values in the example show the cloud wants a 60-second interval while the device still reports 30 seconds: **desired does not mean applied**.

### 3.2. Who Can Read/Write Which Section?

| Section | Cloud service | Device client |
|---|---|---|
| `tags` | Read/write via service-side APIs per permissions | Cannot access tags via device twin interface |
| `desired` | Read/write | Read and receive desired updates; cannot write desired |
| `reported` | Read | Write reported properties |
| Identity / security | Service registry/data-plane permissions | Sign in with the device's own identity |

A device must never be able to set a tag `role=admin` and use it to escalate backend permissions. Tags are for **management/querying**, not IAM authorization.

### 3.3. Desired State and Reported State Are Not Copies

Proper pattern:

```text
Cloud desired:
  telemetryIntervalSec = 60
       |
       v
IoT Hub stores desired state
       |
       v
Device receives delta / GETs twin on reconnect
       |
       v
Validate -> save local config -> apply safely
       |
       v
Device reported:
  telemetryIntervalSec = 60
  lastAppliedDesiredVersion = 27
  applyStatus = "succeeded"
```

Devices should report "succeeded" **only after actually applying**, not immediately upon receiving desired. If application fails, report error codes/status rather than faking convergence.

## 4. Desired Properties: Eventual-State Configuration Updates

Example when the service wants to change interval and target temperature:

```json
{
  "properties": {
    "desired": {
      "telemetryIntervalSec": 60,
      "temperatureTargetC": 4.0
    }
  }
}
```

IoT Hub stores the desired patch. When the device is online with an active subscription/handler, it can receive delta notifications. When offline, desired state stays stored so the device can **GET full twin** or sync on reconnect. Do not rely on receiving *every historical delta* as an event log.

### 4.1. Patch vs. Replace

**Patch** updates specified fields without unintentionally overwriting sibling fields. **Replace** on the full twin/section (where APIs allow) can wipe out another writer's updates if operating on a stale copy. In multi-controller systems, prefer conditional/versioned updates and partition field ownership by namespace.

For example, cloud team A manages `telemetryIntervalSec`, while team B manages `firmware.targetVersion`. One updater must not send an hours-old full desired block and accidentally erase the other team's changes.

### 4.2. Deleting a Property with Null

In IoT Hub twin patch semantics, setting a property to `null` can **remove** that property; do not confuse that with "setting null as a literal config value to apply." Example:

```json
{
  "properties": {
    "desired": {
      "deprecatedSamplingMode": null
    }
  }
}
```

Devices must have clear **default/fallback** logic when a field disappears. Config additions and removals must be tested against older firmware to avoid crashes after reconnect.

### 4.3. Version and Out-of-Assumption Patch Arrival

Desired includes `$version` so the device knows which update level it sees. In every handler:

1. Read version from the desired patch or full twin.
2. Compare against durably persisted `lastAppliedDesiredVersion` if needed.
3. Never apply a patch **older** than already-completed state.
4. Parse/validate all interdependent config fields rather than applying an isolated delta without context.
5. Report outcome with version/rollout ID.

Do not assume desired patches arrive exactly once, or without version gaps while a device was offline. **After reconnect**, syncing the full twin per SDK/device strategy is safest.

## 5. Reported Properties: Confirming Actual State

The device updates reported after attempting to apply configuration:

```json
{
  "telemetryIntervalSec": 60,
  "temperatureTargetC": 4.0,
  "lastAppliedDesiredVersion": 27,
  "applyStatus": "succeeded",
  "firmware": {
    "currentVersion": "2.4.0",
    "status": "installed",
    "appliedRolloutId": "rollout-20261120-b"
  }
}
```

This is a **reported-properties patch sent by the device**, not a full twin response. You can add `lastApplyErrorCode` and `lastApplyTimeUtc` per contract. Never send raw access tokens, secrets, or sensitive logs in reported properties.

### 5.1. Status Should Be a State Machine

A firmware rollout can have:

```text
PENDING -> VALIDATING -> DOWNLOADING -> VERIFYING
     -> INSTALLING -> REBOOTING -> SUCCEEDED
                         |
                         +----------> FAILED
```

Each transition should carry consistent **rollout ID, desired version, timestamp, and error code**. Cloud services must not mark a whole rollout successful merely because IoT Hub accepted the desired update.

### 5.2. Reporting Errors Without Overwriting Reality

If a device has a faulty sensor and cannot apply `telemetryIntervalSec=60`, reported should reflect the **currently running value** plus the error state:

```json
{
  "telemetryIntervalSec": 30,
  "lastAppliedDesiredVersion": 26,
  "applyStatus": "failed",
  "lastFailedDesiredVersion": 27,
  "lastApplyErrorCode": "SENSOR_BUSY"
}
```

Keeping these fields lets the cloud distinguish **offline**, **not yet applied**, and **failed**.

### 5.3. Twins Are Not a Telemetry Store

Do not update reported every 100 ms for continuous temperature readings. Twins have quotas/throttling and suit **relatively stable state**, not time-series storage. Periodic measurements belong in **device-to-cloud telemetry** routed to targets like Azure Data Explorer/Storage/stream processors per architecture. Use reported properties to summarize managed state such as firmware version, mode, or aggregate health.

## 6. Tags, Fleet Queries, and Large-Scale Jobs

Tags can group devices:

```json
{
  "site": "hcm-warehouse-02",
  "region": "south",
  "model": "coldstore-v3",
  "maintenanceGroup": "wave-b"
}
```

Service-side code can query identities/twins by tags/reported properties using the **IoT Hub query language**; syntax typically follows `SELECT * FROM devices WHERE ...`. Query indexing has update latency; do not treat query results as an instantaneously consistent snapshot right after changing a tag.

### 6.1. Fleet Query Example

```sql
SELECT *
FROM devices
WHERE tags.model = 'coldstore-v3'
  AND tags.maintenanceGroup = 'wave-b'
```

This is **IoT Hub twin query syntax**, not Azure SQL Database T-SQL. Supported projections, predicates, and indexing have specific limits; verify against current Hub tier/SDK and permissions.

### 6.2. Updating Thousands of Devices

Avoid writing a naive `for` loop firing 50,000 patches simultaneously. At large scale, consider **IoT Hub jobs** to update twins or invoke direct methods across a cohort when supported by feature/tier. Design:

- Split rollouts into waves/canaries by tags/model/site.
- Rate-limit according to **IoT Hub quotas/throttling** and online device counts.
- Track job state, timeouts, and succeeded/failed counts.
- Verify **reported business outcomes** after the job, not just job API status.
- Support pausing/rolling back/quarantining failing cohorts.

Tags can change while a job is running; define clear **cohort snapshot/selection semantics** rather than assuming every query and job always selects identical devices.

## 7. Concurrency When Multiple Cloud Services Update a Twin

IoT Hub maintains an **ETag** on twins to support optimistic concurrency when using compatible update operations. With multiple writers, a classic problem occurs:

```text
Service A GET twin at ETag E1
Service B GET twin at ETag E1
Service B UPDATE desired.firmware -> ETag E2
Service A REPLACE twin based on E1
    -> risk losing newer changes or hitting 412 conflict
```

### 7.1. Optimistic Concurrency

When the API supports conditional **If-Match/ETag**, follow this strategy:

1. Read twin + ETag.
2. Compute patch/update respecting ownership and contract.
3. Send conditional update with the ETag read earlier.
4. On **precondition failed / conflict**, fetch the latest twin and **merge logic properly** instead of blindly overwriting.
5. Cap retries and raise an incident on persistent conflicts.

Exact API/SDK details for ETags, patches/updates, and conflicts may vary; **verify method signatures for your SDK version**. Do not pass wildcard ETags unconditionally on operations that could overwrite another controller's data.

### 7.2. Desired Version Does Not Replace Business Revision

IoT Hub-managed `$version` orders twin updates; however, services often need their own **configurationRevision** or `rolloutId` to identify a business decision and reconcile across services.

```json
{
  "configurationRevision": "config-rev-0048",
  "telemetryIntervalSec": 60,
  "requestedBy": "fleet-config-service",
  "effectiveAfterUtc": "2026-11-21T00:00:00Z"
}
```

A config revision still requires device-side validation; never allow the cloud to alter **safety-critical actuator parameters** via an unchecked JSON patch without device-side bounds checks.

### 7.3. Never Put Secrets in a Twin

Twin JSON can often be read by many principals holding device management permissions and may appear in logs/audits. Never store database passwords, SAS keys, device certificates, personal data, or API access tokens in desired/reported/tags. For sensitive configurations, send an **opaque reference or configuration version** and fetch secrets via a more secure mechanism matching your threat model.

## 8. Direct Method: Calls Requiring a Synchronous Response

A **direct method** is a call from a service/cloud to a handler on a **currently reachable** device via IoT Hub. The cloud sends **method name + JSON payload**, the device executes the handler and returns **status + response payload** before timeout. It fits short actions where the cloud needs a response within the same request.

Example:

```text
Java operations service
     |
     | invokeDeviceMethod(deviceId="fridge-042",
     |                    method="captureDiagnostics",
     |                    payload={"requestId":"cmd-117"})
     v
   Azure IoT Hub
     |
     | route to connected device
     v
Device direct method handler
     |
     | validate -> capture quick diagnostics -> return
     v
Response: {"status": 200, "payload": {"diagnosticId":"diag-719"}}
     |
     v
Cloud records result
```

Status `200` in the example is an **application response code returned by the device handler per contract**, not a guarantee the result was persisted to Storage/SQL or audited elsewhere.

### 8.1. When to Use?

- Asking an online device to read current values and return quickly.
- Testing a short-lived action with a deterministic response.
- Enabling/disabling diagnostic mode **under a safe contract** with device authorization.
- Application-level `ping` (verifying handler health) rather than relying solely on transport status.
- Triggering a **long-running job**, returning `accepted` with a job ID and tracking progress via reported/D2C.

### 8.2. Offline Devices: No Durable Offline Queue

A direct method is **not** a durable command queue for offline devices. If the device is disconnected or lacks a subscribed handler, the invocation fails on timeout/API error. Do not expect IoT Hub to automatically invoke that method once the device reconnects.

If offline devices must **eventually converge to a configuration**, prefer **desired properties**. If an asynchronous time-limited message is needed, consider **C2D**. If commands must survive extended offline periods, use a **durable command store/workflow** outside direct methods.

### 8.3. Two Timeout Stages

Method invocation APIs typically have parameters such as:

- **Connection timeout:** how long IoT Hub waits for the device to be reachable/have a registered handler within supported limits.
- **Response timeout:** how long to wait for the handler to return once the invocation reaches the device.

Distinguish both stages and choose a **total deadline** aligned with the cloud API. Default/maximum timeout limits depend on service/SDK and may change; never hardcode an assumption of "60 seconds everywhere."

### 8.4. What Does Returning 202 Accepted Mean?

For a 10-minute firmware update, a handler can:

1. Validate `requestId` and model/firmware version.
2. Persist durable local job state.
3. Return `status=202` with `jobId` within a few seconds.
4. Run download/verify/install in the background.
5. Update reported properties or send a D2C completion event when finished.

Here `202` is an **application status convention**: it only confirms the device accepted/scheduled the job, not that firmware is installed. The cloud must still track the job ID and final status.

## 9. Direct Method and "Unknown Outcome" on Timeout

This is the most common failure mode when devices control physical hardware.

```text
Cloud                     IoT Hub                      Device
  |                         |                           |
  | invoke openValve(id=7)  |                           |
  |------------------------>|-------- invoke ---------->|
  |                         |            handler opens valve|
  |                         |<------ status 200 ---------|
  |      X lost response / timeout                        |
  |                                                      |
  | cloud receives timeout                               |
  | Should it retry? **Unknown if prior command ran**    |
```

**A timeout does not prove the device did not execute the operation.** Like a lost database COMMIT ACK, a blind retry can execute the side effect twice.

### 9.1. Idempotency with commandId

Example sent by cloud:

```json
{
  "commandId": "cmd-20261120-117",
  "action": "setTargetTemperature",
  "targetC": 4.0,
  "expectedConfigRevision": "config-rev-0048"
}
```

The device should:

1. Verify invocation origin via the authorized IoT Hub connection and validate contract/payload.
2. Check if `commandId` was already processed.
3. If already processed, return the **prior result** or current state without re-executing.
4. If new, write a **durable in-progress record** (when required) and verify safety preconditions.
5. Execute the action, persist the result, and return the response.
6. Report completion state via twin/D2C when auditing is required.

**In-memory RAM deduplication is insufficient** if the device reboots mid-command. For safety-critical side effects, use a local durable journal, operation reconciliation, and bounded command validity.

### 9.2. "Set State" Commands Are Safer Than "Toggle"

Compare:

```text
setFanSpeed(3)   -> repeating with the same revision is usually idempotent
toggleFan()      -> calling twice can revert back to the original state
incrementDose()  -> calling twice can overdose
```

For actuators with physical effects, prefer **desired target state + local safety bounds** over non-idempotent commands. Never control safety-critical equipment via the cloud without **local interlocks, watchdogs, emergency stops, and proper certification**.

### 9.3. Command Expiration and Anti-Replay

A command can include:

```json
{
  "commandId": "cmd-117",
  "issuedAtUtc": "2026-11-20T10:00:00Z",
  "expiresAtUtc": "2026-11-20T10:02:00Z",
  "requestedTargetC": 4.0
}
```

Devices must account for clock skew and untrusted clocks (offline), rejecting stale commands for dangerous actions. **Idempotency key + expiry + revision** may all be needed together; random IDs alone cannot prevent replay forever if dedup state gets pruned.

### 9.4. Application Status Codes in Direct Methods

Contract example:

| App Status | Interpretation | Cloud Action |
|---|---|---|
| `200` | Fast action completed | Record result, verify if needed |
| `202` | Accepted for background processing | Track job ID/telemetry |
| `400` | Invalid payload | Fix caller; do not retry identically |
| `403` | Device policy forbids | Check permissions/safety; do not bypass |
| `409` | State/revision conflict | Refresh state and decide anew |
| `429` | Device busy/throttled per contract | Retry with backoff if idempotent |
| `500` | Handler internal error | Classify retryability, inspect device logs |

These status codes are **illustrative conventions**, not all codes generated by IoT Hub itself. Distinguish **hub/network invocation errors** from **handler-returned statuses**.

## 10. Cloud-to-Device Message: Asynchronous Messaging

A **cloud-to-device message (C2D)** lets a cloud application send a message to a device identity through IoT Hub. The hub can **temporarily queue** messages for offline devices within TTL and service quotas. The device receives messages upon connecting and processes them per API/protocol.

```text
Cloud service
     |
     | send C2D message(deviceId, payload, messageId, TTL)
     v
Azure IoT Hub per-device queue
     |
     +-- Device offline -> buffer temporarily until expiry/quota
     |
     +-- Device online -> deliver per transport
     |
     v
Device message callback
     |
     +-- parse/validate/dedup
     +-- execute or persist local work
     +-- settle/ack per transport/SDK if supported
     |
     +--> optional business ACK via device-to-cloud telemetry
```

### 10.1. C2D Payload Example

```json
{
  "messageId": "notice-20261120-042",
  "type": "maintenanceNotice",
  "createdAtUtc": "2026-11-20T09:30:00Z",
  "expiresAtUtc": "2026-11-21T09:30:00Z",
  "notice": "Technician scheduled for inspection",
  "requiresAcknowledgement": true
}
```

In practice, `messageId`, TTL, correlation ID, and delivery acknowledgement can reside in **IoT Hub message system/application properties**, not only in the JSON body. Putting `messageId` in the body as well makes device-handler idempotency easier to demonstrate; keep body and headers synchronized if using both.

### 10.2. TTL Is Not Infinite Storage

C2D messages have a **time-to-live (TTL)** governed by IoT Hub message semantics and service limits; devices offline longer than the TTL may miss the message. Queues also have depth/capacity limits and quotas. "Offline queuing" is **not** equivalent to an infinite durable queue like a command database.

For configuration that must survive weeks offline, use **twin desired state**, not C2D alone. For workflows auditing every critical command, store commands in an application **database/Service Bus** and manage retries, expiry, and device delivery explicitly.

### 10.3. C2D Is One-Way with No Synchronous Response

The hub accepting and queuing a message **does not mean** the device displayed the notice, updated configuration, or started the action. If the cloud must know processing completed, the device must send an **application-level acknowledgement** (typically a D2C event/telemetry or reported state) referencing `messageId`.

### 10.4. Distinguishing Three Acknowledgement Layers

| Level | Proves | Does Not Prove |
|---|---|---|
| **Hub accepted** | IoT Hub accepted the message within protocol/quota | Device received or processed it |
| **Transport delivery/settlement** | Message was delivered/settled per protocol/client semantics | Business execution succeeded |
| **Business ACK** | Device reported processing evidence per contract | Downstream side effects persisted unless separately verified |

Specifically, **complete/reject/abandon/feedback** behaviors depend on MQTT/AMQP/HTTPS and the SDK. Never claim an MQTT callback automatically guarantees "exactly-once" business transactions.

## 11. C2D Delivery, Feedback, Ordering, and Duplicates

### 11.1. C2D Feedback

IoT Hub supports **delivery feedback** per options/system properties and service features, informing the service of delivery/expiry/rejection at the supported layer. However, **feedback is not business execution outcome**; for instance, a device might receive `scheduleMaintenance` yet fail to run it due to low battery.

Depending on SDK/API/transport, feedback formats and availability vary; verify feedback queue/endpoint access, retention, and service quotas before building dependencies on it.

### 11.2. At-Least-Once, Duplicates, and Ordering

Design handlers to **tolerate duplicate messages and unexpected arrival orders**; never assume global ordering or exactly-once business execution. Retransmissions can occur after reconnects, timeouts, or failures between processing and settlement.

Example:

```text
messageId=msg-117, commandRevision=5
messageId=msg-118, commandRevision=6

Device receives msg-118 first,
must not apply stale msg-117 afterward to revert to old config.
```

Devices need version/revision preconditions; non-idempotent commands need a local journal and business reconciliation.

### 11.3. Do Not Use C2D as a Permanent Business Command Store

If the business must guarantee "every firmware rollout is audited and completed within 14 days," store **business command records** in a database with a state machine, retry deadlines, device acknowledgements, and dashboards. C2D is **a transport channel for one part of the lifecycle**, not an infinite-history workflow engine.

### 11.4. Do Not Mix Up D2C and C2D

```text
Device-to-cloud:  sensor telemetry, state, business ACK
Cloud-to-device:  notification/work item down to device
Direct method:    invoke online handler, immediate response
Device twin:      desired/reported state document
```

IoT Hub routing, consumer groups, and the Event Hubs-compatible endpoint primarily serve **D2C ingestion**, not receiving C2D messages on devices. Choose the API/client matching the direction of travel.

## 12. Comparing Behavior When a Device Is Offline

| Device State | Twin Desired | Direct Method | C2D |
|---|---|---|---|
| Online, healthy handler | Receives patch/reads twin and applies | Receives and responds within deadline | Receives message per protocol |
| Offline 5 minutes | Latest desired stays stored | Invocation typically fails/times out | Can wait if TTL and quota permit |
| Offline beyond C2D TTL | Latest desired stays stored | No offline replay | Message may expire/be dropped |
| Reconnect after multiple desired updates | GETs full desired/latest state | Does not replay old invocations | Receives non-expired messages |
| Reconnect after firmware reset | Syncs desired and reports state | Runs only new methods | Dedup via local message journal |
| Hub throttled or queue full | Updates may throttle/fail | Invocations may throttle/fail | Sends may fail; cloud retries carefully |

### 12.1. "Online" Is Not an Absolute State

In real environments, connection state and telemetry do not always update instantaneously; a device might hold an open TCP socket while its handler thread is hung, or connect through an intermittent gateway. Never make safety-critical decisions solely from an online/offline flag. Use **fresh heartbeats, timeouts, ACK states, and local safety constraints**.

## 13. Standardizing a Command Envelope for IoT Devices

To handle retries, auditing, and tracing, services should use a consistent **command envelope** across direct methods or C2D:

```json
{
  "schemaVersion": 2,
  "commandId": "cmd-20261120-117",
  "targetDeviceId": "fridge-042",
  "type": "captureDiagnostics",
  "requestedByService": "fleet-operations",
  "requestedAtUtc": "2026-11-20T10:00:00Z",
  "expiresAtUtc": "2026-11-20T10:05:00Z",
  "expectedConfigRevision": "config-rev-0048",
  "payload": {
    "includeSensors": true,
    "maxDurationSeconds": 10
  }
}
```

This is an **illustrative application protocol**, not a mandatory IoT Hub JSON schema. For direct methods, `type` often maps to the method name while the envelope sits in the method payload; for C2D, some metadata belongs in message properties.

### 13.1. Key Fields

| Field | Role | Check |
|---|---|---|
| `schemaVersion` | Firmware/service compatibility | Accept supported versions only |
| `commandId` | Dedup/correlation | Unique per namespace/tenant/device |
| `targetDeviceId` | Prevent logical misrouting | Compare with actual device identity and contract |
| `type` | Supported action | Allowlist; never execute arbitrary code |
| `requestedAtUtc` / `expiresAtUtc` | Block stale commands | Clock/TTL/clock-skew policy |
| `expectedConfigRevision` | Prevent acting on changed state | Compare version/revision |
| `payload` | Business data | Validate schema/ranges and permissions |

### 13.2. Command State Machine

```text
CREATED
   |
   v
DISPATCHING ----(hub error)------> DISPATCH_RETRY
   |
   v
HUB_ACCEPTED / INVOKED
   |
   +------> DEVICE_ACCEPTED ---> RUNNING ---> SUCCEEDED
   |                                   |
   |                                   +----------> FAILED
   |
   +------> EXPIRED / NOT_DELIVERED
   |
   +------> UNKNOWN_OUTCOME ---> RECONCILE
```

This is an application **business command store** state machine, not a single built-in state enum provided by Azure IoT Hub. For desired twins, tracking **applied configuration revisions** makes more sense than modeling every update as a multi-step job.

### 13.3. Why Is a Separate Audit Store Needed?

Twins represent latest state; direct method responses have deadlines; C2D queues have TTLs. If the business must retain command history, requester, timestamps, acknowledgements, and retries across weeks, use a transactional database (such as Azure SQL/Cosmos DB per needs) with **unique commandIds**, retry state, and retention policies. IoT Hub is a **communication boundary**, not a replacement for an application workflow database.

## 14. Azure CLI Practice: Setup and Reading Twins

Azure CLI with the **Azure IoT extension** (where commands aren't built in) provides IoT Hub management commands. Commands below are **lab examples** requiring proper IoT Hub permissions; exact syntax/flags can vary across CLI/extension versions. Check `az ... --help` on your deployment machine before production use.

### 14.1. Setting Environment Variables

```bash
az login
az account set --subscription "<subscription-id>"

HUB_NAME="<your-iot-hub-name>"
DEVICE_ID="fridge-042"

# If CLI reports missing IoT command group:
# az extension add --name azure-iot

az iot hub device-twin show \
  --hub-name "$HUB_NAME" \
  --device-id "$DEVICE_ID" \
  --output json
```

**Never create or modify production devices outside your ownership.** With multiple subscriptions, check `az account show` to avoid updating the wrong hub.

### 14.2. Updating Desired Properties

With an IoT CLI extension supporting `--set`:

```bash
az iot hub device-twin update \
  --hub-name "$HUB_NAME" \
  --device-id "$DEVICE_ID" \
  --set properties.desired.telemetryIntervalSec=60 \
  --output json
```

This command illustrates **cloud updating desired**; it does not make the device immediately report 60 seconds. Check later with `device-twin show` and inspect `properties.reported.telemetryIntervalSec` or `lastAppliedDesiredVersion`.

**Concurrency note:** specific CLI update commands may use ETags or default merge semantics depending on extension version. For multiple writers or strict protection, use SDK/REST with explicit conditional updates and test 412 conflicts.

### 14.3. Querying Fleet by Tag

When the CLI supports IoT Hub twin queries:

```bash
az iot hub query \
  --hub-name "$HUB_NAME" \
  --query-command \
    "SELECT * FROM devices WHERE tags.maintenanceGroup = 'wave-b'" \
  --output json
```

Service-side query permissions may differ from twin update permissions. Do not treat query results as a transactionally consistent list against concurrent tag changes.

### 14.4. Sensitive Data in Outputs

Full twins can hold tags, desired/reported properties, and operationally sensitive metadata. Never paste raw production twin JSON into public pastes or CI console logs; project only needed fields and enforce RBAC and log retention.

## 15. Azure CLI: Invoking a Direct Method

In the lab, the device must be online and the device-side SDK must have registered the `captureDiagnostics` handler.

```bash
az iot hub invoke-device-method \
  --hub-name "$HUB_NAME" \
  --device-id "$DEVICE_ID" \
  --method-name "captureDiagnostics" \
  --method-payload '{"commandId":"cmd-lab-117","includeSensors":true}' \
  --output json
```

Timeout parameters, method payload formatting, and service errors depend on the installed CLI/extension version. Check `az iot hub invoke-device-method --help` when configuring timeouts. The returned JSON may include the status/payload returned by the handler.

### 15.1. What Happens If the Device Is Offline?

Direct methods are not queued. The cloud sees an error/timeout if the device is unreachable before the deadline; log **method invocation unsuccessful** rather than marking the device as "rejected," since the handler may never have received anything.

### 15.2. Never Call "Reboot" to Test Connectivity in Production

Many IoT samples use `reboot` because it is easy to see. However, rebooting real devices or physical actuators can interrupt live services. In labs, prefer non-destructive methods like **`getStatus`** or **`captureDiagnostics`** using simulated devices.

### 15.3. Distinguishing Response Status from CLI Exit Code

`az` can exit 0 because the invocation API returned a **method response** from the device, even though the application payload status is `400` or `500`. Pipelines must inspect **both command execution/transport outcome and business status**, never just the process exit code.

## 16. Azure CLI: Sending Cloud-to-Device Messages

With an IoT CLI extension providing `az iot device c2d-message`:

```bash
az iot device c2d-message send \
  --hub-name "$HUB_NAME" \
  --device-id "$DEVICE_ID" \
  --data '{"messageId":"notice-lab-042","type":"maintenanceNotice"}'
```

**Syntax is illustrative; verify with `az iot device c2d-message send --help` in your installed version.** Setting TTL, acknowledgement, and message properties must also follow current flags/SDK.

### 16.1. Testing While the Device Is Offline

In the **lab**:

1. Ensure the device identity and hub tier support C2D.
2. Disconnect the device simulator cleanly.
3. Send a message with a supported TTL long enough to cover the lab reconnect window.
4. Reconnect the device before TTL expires.
5. Inspect device logs to confirm message receipt/settlement.
6. If business confirmation is needed, check **D2C acknowledgement** with matching message ID.
7. Repeat with an offline window longer than TTL to observe expiration/non-delivery.

Never run this test against live operational hardware without approval; disconnecting can disrupt alerts and safety.

### 16.2. Persisting Message State for High-Reliability Cloud Workflows

Suppose a C2D notice must be displayed before tomorrow: IoT Hub queue TTL is only one piece. The application workflow should store `noticeId`, `deviceId`, `deadline`, `deliveryAttempt`, `businessAckAt`, and failure reason in a database. On expiration, mark `expired` for operator follow-up instead of looping infinitely.

## 17. Device-Side Java: Choosing an SDK and Managing Lifecycle

In Java, IoT Hub SDKs are typically split into:

- **Device SDK:** runs on the device/gateway; manages connections, device twin callbacks, direct method handlers, and C2D message handlers.
- **Service SDK:** runs in the backend/cloud; updates twins, invokes direct methods, sends C2Ds, and runs registry/twin queries.

Many systems use Java packages/libraries from the **Azure IoT SDK for Java** such as `com.microsoft.azure.sdk.iot: iot-device-client` and `iot-service-client` (exact coordinates/artifacts depend on release). API names, dependencies, permissions, support lifecycles, and transport behaviors must be **checked against release notes/docs for the chosen version**. The following examples focus on **application lifecycle and contracts** rather than pretending every SDK version shares identical signatures.

### 17.1. Lifecycle of a Device Process

```text
Device boot
   |
   v
Load device identity, TLS trust, secure local config
   |
   v
Open IoT Hub connection (MQTT/AMQP per SDK)
   |
   +--> Subscribe desired property updates
   +--> Register direct method handlers
   +--> Register C2D message handler
   |
   v
GET full device twin / reconcile desired
   |
   v
Run telemetry + command processing loop
   |
   +--> Persist local command journal
   +--> Apply safety checks
   +--> Update reported state / send D2C business ACK
   |
   v
On disconnect: backoff/reconnect; sync full twin
   |
   v
Graceful shutdown / persist checkpoints
```

### 17.2. Do Not Create a DeviceClient Per Command

The device-side SDK manages TLS connections and subscriptions. An application should maintain a stable **connection lifecycle** per SDK guidance rather than opening a new IoT Hub client on every sensor reading or method call, which wastes auth/network overhead, pressures quotas, and loses callback state.

### 17.3. Handlers Must Not Block Too Long

Method callbacks often run on the client's callback executor thread. If a handler downloads a 200 MB firmware image and blocks for 20 minutes, the device will time out direct methods and starve other callbacks. **Acknowledge quickly**, persist a local job, and hand work to a background worker—while bounding queue size, CPU/memory, disk, and watchdogs.

### 17.4. Lifecycle Across Restarts

After a device reboot:

1. Restore identity and the local command journal.
2. Reconnect to the hub securely.
3. Register handlers/subscriptions per SDK.
4. **GET full twin** and process the current desired version.
5. Write reported state if state changed across reboot.
6. Deduplicate messages and reconcile long-running commands from durable local state.

Never assume callbacks fire in the exact pre-reboot order. Avoid re-running a "once-only" command merely because it still sits as a desired key.

## 18. Java: Building an Idempotent Handler Decoupled from the IoT SDK

The example below is **pure Java business logic** invoked inside an SDK device-side callback. The goal is separating safety logic from specific SDK APIs. Illustrative interfaces must be backed by real persistence and hardware implementations per device type.

```java
import java.time.Instant;
import java.util.Map;
import java.util.Objects;

record Command(
    String commandId,
    String action,
    int targetC,
    Instant expiresAtUtc,
    String configRevision
) {}

record Result(int status, String code, String commandId) {}

interface CommandJournal {
    Result findCompleted(String deviceId, String commandId);
    void markStarted(String deviceId, String commandId);
    void markCompleted(String deviceId, Result result);
}

interface TemperatureController {
    void setTargetTemperature(int targetC) throws Exception;
}

public final class DeviceCommandHandler {
    private final String localDeviceId;
    private final CommandJournal journal;
    private final TemperatureController controller;

    public DeviceCommandHandler(String localDeviceId,
                                CommandJournal journal,
                                TemperatureController controller) {
        this.localDeviceId = Objects.requireNonNull(localDeviceId);
        this.journal = Objects.requireNonNull(journal);
        this.controller = Objects.requireNonNull(controller);
    }

    public Result handle(Command command) {
        if (command == null || command.commandId() == null) {
            return new Result(400, "BAD_COMMAND", null);
        }
        if (command.expiresAtUtc() == null
                || Instant.now().isAfter(command.expiresAtUtc())) {
            return new Result(410, "EXPIRED", command.commandId());
        }
        Result prior = journal.findCompleted(
                localDeviceId, command.commandId());
        if (prior != null) return prior; // Dedup already-completed request.

        if (!"setTargetTemperature".equals(command.action())
                || command.targetC() < 2
                || command.targetC() > 8) {
            return new Result(400, "INVALID_OR_UNSAFE", command.commandId());
        }

        try {
            journal.markStarted(localDeviceId, command.commandId());
            controller.setTargetTemperature(command.targetC());
            Result result = new Result(200, "APPLIED", command.commandId());
            journal.markCompleted(localDeviceId, result);
            return result;
        } catch (Exception ex) {
            // Do not assume hardware action did not run if the process fails.
            return new Result(500, "REQUIRES_RECONCILIATION",
                    command.commandId());
        }
    }
}
```

This is an **illustrative example**, **not production-ready**:

- `CommandJournal` needs an **atomic claim** so two concurrent invocations with the same `commandId` cannot execute in parallel; separate `findCompleted` then `markStarted` has a race condition.
- State **STARTED yet not COMPLETED** after a crash must be reconciled with hardware rather than blindly re-run.
- `TemperatureController` needs hardware interlocks, permissions, and state revision checks.
- `Instant.now()` clocks can drift if offline long; enforce time-sync/expiry-tolerance policies.
- Callbacks must verify identity/authorization per IoT Hub/device app and never accept commands from an untrusted local channel.
- The example uses `int` degrees for brevity; real hardware has distinct calibration/limits/units.

### 18.1. Mapping to the IoT SDK

A device SDK adapter can bridge:

```text
Direct method callback:
  methodName + JSON payload
    -> parse & validate Command
    -> DeviceCommandHandler.handle(...)
    -> serialize {status, code, commandId} as method response

C2D message callback:
  system properties + JSON body
    -> parse & validate Command/Notice
    -> local durable enqueue / dedup
    -> settle transport message per SDK capabilities
    -> worker executes
    -> send D2C business ACK on completion
```

Note: **settling transport before persisting local work** risks losing work on crash; settling after side effects with retries risks duplicates. Choose the boundary deliberately and use a durable local journal for critical workloads.

### 18.2. Why Not Copy-Paste Callbacks Between Direct Method and C2D?

Direct methods must **return a response immediately** and generally run short tasks; C2D receives asynchronously and writes to a local queue. The underlying business handler can be shared, while **transport wrappers, timeouts, settlement, acks, and retries differ**.

## 19. Service-Side Java: Decoupling Business Logic from the IoT Hub SDK

Cloud backends should also avoid scattering raw REST/SDK calls throughout controllers. An internal port/interface hides differences across SDK versions, REST, and authentication while keeping a **business command store** and clean tests.

### 19.1. Designing a Port for All Three Mechanisms

```java
import java.time.Duration;
import java.util.Map;

record DesiredPatch(Map<String, Object> properties,
                    String configRevision) {}

record TwinView(String deviceId,
                String etag,
                long desiredVersion,
                Map<String, Object> desired,
                Map<String, Object> reported) {}

record InvocationResponse(int deviceStatus, String payloadJson) {}

record QueuedReceipt(String serviceMessageId, String trackingId) {}

interface IoTHubControlPort {
    TwinView readTwin(String deviceId) throws Exception;

    TwinView updateDesired(
            String deviceId, DesiredPatch patch, String expectedEtag)
            throws Exception;

    InvocationResponse invokeMethod(
            String deviceId, String methodName, String requestJson,
            Duration connectionTimeout, Duration responseTimeout)
            throws Exception;

    QueuedReceipt sendC2D(
            String deviceId, String messageId, String messageJson,
            Duration timeToLive)
            throws Exception;
}
```

**This is an application-defined interface**, not a built-in Azure IoT Java SDK API. Real implementations must use supported IoT Hub SDK/REST calls for the chosen version and handle ETag conflicts, quotas, authentication, payload sizes, and TTLs.

### 19.2. Java Service Choosing the Right Mechanism

```java
import java.time.Duration;
import java.util.Map;

public final class FleetCommandService {
    private final IoTHubControlPort hub;

    public FleetCommandService(IoTHubControlPort hub) {
        this.hub = hub;
    }

    public TwinView setSamplingInterval(
            String deviceId, int intervalSeconds) throws Exception {
        if (intervalSeconds < 10 || intervalSeconds > 3600) {
            throw new IllegalArgumentException("Interval out of range");
        }
        TwinView current = hub.readTwin(deviceId);
        return hub.updateDesired(deviceId,
                new DesiredPatch(
                        Map.of("telemetryIntervalSec", intervalSeconds),
                        "config-rev-0049"),
                current.etag());
    }

    public InvocationResponse captureDiagnostics(
            String deviceId, String commandJson) throws Exception {
        return hub.invokeMethod(deviceId, "captureDiagnostics",
                commandJson, Duration.ofSeconds(5),
                Duration.ofSeconds(20));
    }

    public QueuedReceipt sendNotice(
            String deviceId, String messageId, String json) throws Exception {
        return hub.sendC2D(deviceId, messageId, json,
                Duration.ofHours(6));
    }
}
```

Values `5s`, `20s`, and `6h` are **lab assumptions**, not mandatory IoT Hub defaults or limits. Check SDK and hub tier capabilities/valid ranges before deployment. This class also lacks authorization, persistent auditing, rate limiting, and retries; never expose it directly to the Internet as a production API.

### 19.3. Do Not Return HTTP 200 Just Because the Hub Accepted

If a backend REST API receives `POST /devices/fridge-042/commands` and dispatches a C2D message, the application response can look like:

```json
{
  "commandId": "cmd-117",
  "state": "QUEUED",
  "deviceExecutionComplete": false
}
```

The HTTP status returned to the client can be `202 Accepted` **by API design**, rather than pretending device execution completed. Clients poll `GET /commands/cmd-117` or subscribe for updates. The command store must distinguish **queued, dispatched, acknowledged, succeeded, failed, and expired**.

### 19.4. Sending Commands Durably

```text
Operator requests command
           |
           v
Authorize operator and device scope
           |
           v
Insert durable command record (unique commandId)
           |
           v
Dispatch via IoT Hub direct method / C2D / desired patch
           |
           v
Update dispatch attempt / IoT Hub result
           |
           v
Wait for device business ACK or reported convergence
           |
           v
Reconcile, timeout, escalate and audit
```

Writing to a database and calling IoT Hub **do not form a single ACID transaction**. If a crash happens after sending yet before recording the result, the next dispatch attempt may duplicate: therefore, stable command IDs, device-side deduplication, and reconciliation are mandatory. A **transactional outbox** can decouple command creation from dispatching, though an outbox alone does not create exactly-once execution on devices.

## 20. Device Twin Convergence: Knowing Configuration Was Applied

Avoid naive "desired value equals reported value" comparisons when updates happen frequently. Use **configuration revision + version + last applied status**.

### 20.1. State Model

```text
Cloud config-rev-0049
  desired.version = 29
          |
          v
Device sees desired 29
          |
          v
Device validates and writes local config
          |
          v
Device applies config to actual sensor
          |
          v
Device reported:
  lastAppliedDesiredVersion = 29
  configRevision = "config-rev-0049"
  applyStatus = "succeeded"
          |
          v
Cloud checks actualReportedValue + revision + status
          |
          v
Mark configuration converged
```

**Mistake:** cloud updates desired successfully and immediately writes `rollout_status=SUCCEEDED`. Better: `DESIRED_UPDATED`, then **wait for verified reported state**.

### 20.2. Do Not Mistake Stale Reported State for the Current Outcome

A device may still report `applyStatus=succeeded` from an older revision while desired has moved to a new revision. Compare **`lastAppliedDesiredVersion` or `configRevision`** against the current revision, alongside the actual state reported by the device. Never check only the string `"succeeded"`.

### 20.3. Firmware Rollback

If firmware `2.4.0` fails on 5% of devices:

1. Halt subsequent rollout waves.
2. Identify devices in `DOWNLOADING`/`INSTALLING`/`FAILED`/`SUCCEEDED`.
3. Update target version/revision or trigger a rollback action compatible with firmware capabilities.
4. Device verifies package signature, hardware compatibility, power level, and safe rollback.
5. Monitor actual reported versions and device heartbeats.

Do not assume editing desired `targetVersion=2.3.1` instantly rolls back firmware; devices may be offline or lack safe downgrade support.

## 21. Device Identity, Authentication, and Authorization

IoT flows cross **two distinct trust boundaries**:

- **Device → IoT Hub:** devices authenticate with individual identities using mechanisms such as **per-device symmetric keys/SAS tokens or X.509 certificates** where supported; never share hub-wide backend credentials across all devices.
- **Cloud service → IoT Hub:** operational services receive data-plane permissions via **Microsoft Entra ID/RBAC** or approved service credentials with least privilege.

### 21.1. Trust Diagram

```text
Administrator / API client
       |
       | Entra ID + API authorization
       v
Fleet Operations Service (managed identity)
       |
       | IoT Hub data-plane permission
       v
Azure IoT Hub
       |
       | device identity authentication via TLS
       v
Device with individual key or certificate
       |
       | local policy + interlocks
       v
Physical actuator / sensor
```

A cloud service holding permission to **update desired** should not automatically be allowed to change firmware on every device unless business policy permits it. Enforce **business API authorization** by tenant/site/role/operation rather than relying solely on IoT Hub RBAC.

### 21.2. Never Embed a Hub-Owner Key in Firmware

Using a full-privilege hub-level shared access policy across all devices is a severe anti-pattern: one compromised device threatens the entire fleet. Each device needs its own identity/certificate/secret, easily rotated/revoked, provisioned via **Device Provisioning Service (DPS)** where appropriate.

### 21.3. Cloud-Side RBAC

Azure IoT Hub offers data-plane RBAC roles/permissions to read registries/twins, manage devices, and invoke authorized operations per feature. A managed identity should hold only **the IoT Hub permissions required for its workload** at the narrowest scope; never grant Subscription Owner just to invoke a method or read a twin.

**Control-plane IAM** for managing the IoT Hub resource and **data-plane authorization** for sending commands/reading twins are not automatically interchangeable. Verify exact supported roles/actions for `update twin`, `invoke direct method`, and `send C2D` per SDK and tenant policy.

### 21.4. TLS, CA, and Credential Rotation

- Devices use TLS and verify hostname/server CA chains; never disable certificate verification.
- SAS tokens expire and must refresh; clock skew breaks token validity.
- X.509 certificates require provisioning/revocation/rotation policies and private key protection.
- When a device is stolen, disable/revoke its identity and block new commands.
- Firmware should update trust stores/CAs securely rather than pinning a leaf certificate for a multi-year lifespan without a rollover plan.

### 21.5. Commands Must Have Device-Side Safety Boundaries

Even when an operator is authorized by the cloud, the device must enforce **local safety checks**:

- Target temperature lies within certified bounds.
- Never open a valve when sensors indicate hazard.
- Never reboot during a critical cycle.
- Reject firmware commands lacking signature verification or matching model checks.
- Enforce command expiry/revisions so stale commands cannot overwrite newer state.

**IoT Hub provides a more trustworthy identity channel, not a replacement for device-side safety controllers.**

## 22. Networking and Protocol Support

IoT devices can use MQTT/AMQP and certain IoT Hub-supported HTTPS mechanisms for specific scenarios. **Twin, direct method, and C2D capabilities do not have identical support across every transport.**

### 22.1. MQTT vs. AMQP/HTTPS

| Criterion | MQTT | AMQP | HTTPS |
|---|---|---|---|
| IoT device connection | Often fits constrained devices keeping long-lived connections | Fits capable SDKs/gateways/transports | Request/polling, limited real-time features |
| Twin desired subscriptions | Supported via MQTT semantics/SDK | Supported via AMQP semantics/SDK | Do not assume identical push callbacks |
| Direct methods | Supported per client/tier/SDK | Supported per client/tier/SDK | Do not assume HTTP-only devices have equivalent handlers |
| C2D messages | Dedicated delivery/ack semantics | Dedicated settlement semantics | Polling/ack behavior where API supports |
| Network | Check firewall, proxy, TLS, port | Check firewall, proxy, TLS, port | Fits HTTPS-only networks with different capabilities |

**Do not switch from MQTT to HTTPS just because a proxy blocks a port and assume direct methods still work.** Check protocol feature matrices for IoT Hub and the device SDK, latency/connection behavior, message settlement, and gateway topology.

### 22.2. Outbound Connections and Firewalls

Devices typically require **outbound** connectivity to IoT Hub and supporting endpoints (identity/DPS/time sync/update storage) per workflow. Enterprise firewalls should permit exact architecture-defined endpoints/ports; never open inbound Internet ports directly to hardware bypassing IoT Hub.

### 22.3. IoT Edge Gateways

When devices connect through **Azure IoT Edge** or a gateway, distinguish device twins from **module twins**, nested/gateway identities, and store-and-forward. Edge hub offline behavior, local routing, and cache/twin sync depend on runtime/architecture; **do not assume C2D/direct methods queue infinitely or behave identically to direct IoT Hub connections**.

### 22.4. Device Clocks

Command expiration, SAS tokens, TLS certificates, and event timestamps can all rely on clocks. Devices offline for long periods, with dead RTC batteries, or broken time sync may reject valid tokens or accept expired commands. Implement secure time sync, monotonic timers for short deadlines, clock-skew policies, and drift alerts.

## 23. IoT Hub Quotas, Throttling, and Fleet Rollouts

IoT Hub enforces **quotas and rate limits** by hub tier, units, and operation types. Twin updates, method invocations, C2D sends, registry queries, and telemetry ingestion can have **distinct limits**. Do not assume 50,000 devices means 50,000 concurrent method invocations without limits.

### 23.1. Rollout in Waves

Example fleet split:

```text
Wave A: 1% canary (500 devices)
  -> wait for reported convergence + failure thresholds
Wave B: 9% (4,500 devices)
  -> validate DQ/health/error rate
Wave C: 30% (15,000 devices)
  -> monitor hub throttles and device availability
Wave D: remaining 60% (30,000 devices)
  -> continue only if SLO and safety gate PASS
```

Percentages are illustrative; real plans should stratify by site, time zone, model, network carrier, release channel, and business risk.

### 23.2. Exponential Backoff + Jitter

For 429 throttling or transient network errors, retry in a bounded manner:

```text
Attempt 1: send once
Attempt 2: delay ~200–400 ms
Attempt 3: delay ~500–1000 ms
Attempt 4: delay ~1–2 s
Then: park command / escalate, do not loop forever
```

This is an **illustrative diagram**, not a mandatory IoT Hub retry policy. Respect retry-after/backoff hints when present, and avoid multiplying retries across SDK + backend + scheduler into a command storm. **C2D/direct method retries must never re-execute dangerous commands when outcome is unknown.**

### 23.3. Never Increase Hub Units to Mask a Handler Bug

If 20,000 devices update reported properties every 100 ms due to a firmware bug, throttling and costs will spike. Fix the frequency/nature of the data, route telemetry over D2C, and only report meaningful state changes; scaling tiers does not fix using twins as a streaming bus.

### 23.4. Cost-Aware Command Cadence

Every operation through IoT Hub can consume metered message units and quotas depending on payload, tier, and operation type. Command volume, retries, twin patches, telemetry, and downstream storage/processing all contribute to cost. **Never lock in a fixed unit price/limit** without checking current pricing/quotas for the target hub SKU and region.

## 24. Monitoring: Tracking a Command Across Cloud → Device

A dashboard showing only "IoT Hub request succeeded" misses offline devices, queued commands, failing device handlers, and actuators not reaching target state. Full observability attaches a **correlation ID/command ID** end-to-end:

```text
Operator / API request
   |
   +-- API authorization / request ID
   |
   v
Command store
   |
   +-- desired update / method invocation / C2D send
   |
   v
IoT Hub resource metrics + diagnostics
   |
   +-- throttling / failures / hub health
   |
   v
Device SDK callback
   |
   +-- receive latency / dedup / local queue
   |
   v
Physical/sensor workflow
   |
   +-- applied state / error / execution duration
   |
   v
Reported property or D2C business ACK
   |
   v
Cloud reconciliation / command status / alert
```

### 24.1. Metrics by Layer

| Layer | Key Metrics | Detects |
|---|---|---|
| **Fleet API** | Command requests, unauthorized, dispatch failures | Cloud API errors/permissions |
| **IoT Hub** | Data-plane operation success/error, throttling, supported queue/telemetry metrics | Hub capacity/quotas |
| **Connectivity** | Connected/disconnected devices per telemetry/events, reconnect rate | Carrier, gateway, or certificate issues |
| **Twin** | Desired update rate, reported lag, convergence percent | Stalled config rollouts |
| **Direct method** | Invoke latency, device handler response, timeout rate | Offline/busy handlers |
| **C2D** | Accepted, expired, delivery feedback, outstanding business ACKs | Offline queues/TTL |
| **Device** | Local command queue depth, last applied revision, handler duration, failure codes | Device CPU/storage/hardware |
| **Business** | % devices at target config, command completion SLA | Business impact |

IoT Hub does not automatically expose **all** of these metrics natively. Metrics like **convergence percent** and **business ACK latency** typically must be computed from twin snapshots, device events, and the command store.

### 24.2. Distinguishing Push Events from Status Snapshots

Device twin `reported` is a latest-state snapshot; if a device transitions `RUNNING` → `FAILED` → `RUNNING` in 2 seconds, a later query may see only the **final state**. To audit transitions, devices should send **D2C events** carrying `commandId`, `transition`, and `timestamp`, persisted by the backend per security/retention rules.

### 24.3. A D2C Acknowledgement Event

```json
{
  "eventType": "commandResult",
  "deviceId": "fridge-042",
  "commandId": "cmd-20261120-117",
  "result": "SUCCEEDED",
  "configRevision": "config-rev-0049",
  "deviceEventTimeUtc": "2026-11-20T10:00:42Z",
  "actualTargetC": 4.0
}
```

The backend must verify the **device identity attached to a trusted ingestion source** and match it against the pending command. The `deviceId` field inside the payload is **not authentication proof by itself**; never let device A claim in JSON that it is device B. D2C events can duplicate or arrive late, so ACK processors must be idempotent and check revisions/order.

### 24.4. Freshness of Reported State

A device reporting `temperatureTargetC=4.0` two weeks ago that is currently offline must not be treated as "operating normally." Status services should combine:

- Last successful reported revision.
- Last verified business ACK/telemetry timestamp.
- Transport connection health/freshness.
- Device heartbeats and error signals.
- Acceptable offline window for that device class.

Avoid treating an `isConnected` flag as proof that physical hardware is safe.

## 25. Azure Monitor, Metrics, and Diagnostic Settings

**Azure Monitor** tracks IoT Hub resources via platform metrics, alert rules, and diagnostic settings routing to Log Analytics/Storage/Event Hubs per supported capabilities. **Metric names, categories, dimensions, retention, and pricing vary by SKU/features**, so discover them from the resource rather than guessing names.

### 25.1. Azure Portal

1. Open the **exact IoT Hub** in the Azure Portal and verify subscription/resource group/tier.
2. Select **Monitoring → Metrics** and review available metric definitions.
3. Choose appropriate time ranges and aggregations (Sum/Count/Max/Average per metric).
4. Monitor errors/auth/throttling and D2C/C2D/twin/method operations via available signals.
5. Enable needed **Diagnostic settings** and verify logs actually land in the workspace/Storage/Event Hubs.
6. Create alerts with owners/action groups and runbooks.
7. Correlate platform metrics with **device application telemetry** and the command store.

**There is no built-in IoT Hub platform metric for "valve opened successfully" unless the application emits a trusted confirmation.**

### 25.2. Azure CLI: Discovering Metric Definitions

```bash
az login
az account show --output table
az account set --subscription "<subscription-id>"

IOTHUB_RESOURCE_ID="<full-IoT-Hub-Azure-resource-id>"

az monitor metrics list-definitions \
  --resource "$IOTHUB_RESOURCE_ID" \
  --output table
```

After selecting a metric name that **actually appears**:

```bash
METRIC_NAME="<metric-name-from-definition>"

az monitor metrics list \
  --resource "$IOTHUB_RESOURCE_ID" \
  --metric "$METRIC_NAME" \
  --output json
```

When specifying time grains or metric namespaces, verify values allowed by the resource/CLI; never assume every metric supports 1-minute granularity or identical dimensions.

### 25.3. Diagnostic Settings

```bash
az monitor diagnostic-settings list \
  --resource "$IOTHUB_RESOURCE_ID" \
  --output json
```

The returned list may be empty if unconfigured; that does not mean the hub lacks platform metrics. To inspect supported diagnostic categories, use Azure Portal/CLI for that resource. When configuring exports:

- Select a Log Analytics workspace/Storage/Event Hubs in the right region with proper permissions.
- Limit to necessary categories to avoid excessive log volume.
- Control PII in payloads/diagnostics and retention.
- Trigger a lab action with a correlation ID and verify ingestion.

### 25.4. Illustrative KQL for Command Audit Logs

Assuming the organization created custom table **`IoTCommandAudit_CL`** and ingests matching records (column names are **examples only**):

```kusto
IoTCommandAudit_CL
| where TimeGenerated > ago(24h)
| summarize
    Requested=count(),
    Succeeded=countif(Result_s == "SUCCEEDED"),
    Failed=countif(Result_s == "FAILED"),
    Unknown=countif(Result_s == "UNKNOWN_OUTCOME")
    by Mechanism_s
| order by Failed desc
```

**The table `IoTCommandAudit_CL` is not pre-created by IoT Hub.** If KQL reports a missing table/column, inspect data collection rules/ingestion pipelines, schemas, and workspaces instead of guessing column renames.

### 25.5. KQL Analyzing Non-Converged Devices

Against a custom table storing **reconciliation snapshots**:

```kusto
IoTFleetConvergence_CL
| where TimeGenerated > ago(2h)
| where DesiredRevision_s != ReportedRevision_s
| summarize NotConverged=dcount(DeviceId_s)
    by Site_s, Model_s
| order by NotConverged desc
```

This example illustrates **a pipeline that generates snapshots and columns first**; KQL does not directly query the IoT Hub twin registry. For millions of devices, throttle snapshot frequency/rate limits so dashboard builds do not hammer IoT Hub.

### 25.6. Useful Alerts

Examples of actionable signals:

- Direct method timeout rate spiking after a firmware release.
- % reported convergence below threshold during a rollout wave.
- Expiring C2D messages or delayed **business acknowledgements**.
- Rising hub throttling or 401/403 auth failures after key rotation.
- Rising heartbeat loss rate by model/site/carrier.
- High device local command queue depth, low battery, or full disk.
- Handler/firmware install failures exceeding canary thresholds.

Set thresholds using **traffic, cohort size, expected offline windows, and SLOs**—never set `offline devices > 0` for fleets with scheduled offline maintenance.

## 26. Security Observability and Preventing Spoofed ACKs

Avoid logging raw twins, C2D payloads, or method parameters containing PII/secrets everywhere. A structured audit record might include:

```json
{
  "commandId": "cmd-20261120-117",
  "deviceId": "fridge-042",
  "site": "hcm-warehouse-02",
  "operation": "setTargetTemperature",
  "mechanism": "directMethod",
  "dispatchAttempt": 1,
  "dispatchResult": "METHOD_RESPONSE_202",
  "businessStatus": "RUNNING",
  "desiredRevision": "config-rev-0049",
  "traceId": "trace-d3a1",
  "observedAtUtc": "2026-11-20T10:00:04Z"
}
```

### 26.1. Permissions for Viewing Audit Data

An operator at site A may need to view outcomes for refrigerators at site A, without permission to view certificates, registry keys, or site B data. Data lakes/log workspaces must enforce **authorization and data classification**; production APIs are not the only tier needing security.

### 26.2. Correlation ID Is Not a Credential

`commandId` and `traceId` join logs together, yet they do **not** authenticate the sender. When the cloud receives a D2C ACK, verify connection identity, trusted IoT Hub metadata/ingestion context, and device authorization. Never allow an unauthenticated actor calling `POST /commands/cmd-117/ack` to mark `SUCCEEDED`.

### 26.3. Logs on Authentication Failure

Log **error codes, sanitized device IDs, non-secret identity/certificate references, and timestamps**; never log full SAS tokens, hub connection strings, X.509 private keys, or TLS secrets. After rotation, inspect the specific affected devices rather than disabling hub-wide authentication.

## 27. Runbook 1: Desired State Not Applied

**Scenario:** the cloud set desired `telemetryIntervalSec=60` across 500 devices, yet after 30 minutes 120 devices still report `30`.

### 27.1. Step-by-Step Investigation

1. Confirm cloud desired updates succeeded on the exact **IoT Hub/device IDs**.
2. Compare `desired.$version` with `lastAppliedDesiredVersion`/`configRevision` in reported.
3. Segment the 120 devices by **offline status, firmware version, site, carrier, and model**.
4. Verify device handlers subscribe to desired updates and **GET full twin on reconnect**.
5. Inspect device logs: parse errors, range validation failures, local storage errors, sensor busy.
6. Check IoT Hub throttles and network/TLS/DPS/auth errors.
7. Cross-check update timestamps and stale reported states.
8. For online devices, invoke a **safe non-destructive** diagnostic method if needed.
9. Fix firmware/config, canary on a small cohort, and monitor convergence.
10. Mark success only when reported matches both desired revision and actual state.

### 27.2. Do Not Do These

- Do not blast 500 desired patches every 2 seconds.
- Do not force devices to report `60` before actually applying the configuration.
- Do not reset the whole IoT Hub or rotate keys because one model group has a parse bug.
- Do not apply commands exceeding hardware safety limits.

### 27.3. Possible Root Causes

| Symptom | Likely Cause |
|---|---|
| Newer desired version, older reported, device offline | Has not reconnected/synced yet |
| Device online yet reports error | Validation/hardware/firmware error |
| Only older firmware fails | Does not understand new desired schema |
| Reported shows same value but older revision | Stale success, hasn't applied new rollout |
| Update denied | Cloud RBAC/identity or hub/quota error |

## 28. Runbook 2: Mass Direct Method Timeouts

**Scenario:** operations dashboard shows 35% of `captureDiagnostics` invocations timing out.

### 28.1. Four Failure Categories

1. **Device offline/unreachable:** no reachable connection/handler.
2. **Device busy:** handler callback thread blocked, low CPU/storage/battery.
3. **Network instability:** carrier/gateway/IoT Hub connection resets, packet loss.
4. **Cloud throttling/config:** hub tier/quota, credentials, wrong method name, or overly short deadline.

### 28.2. Investigation

1. Slice timeouts by **device model/site/firmware/time window**.
2. Inspect error codes from IoT Hub invocation, not just cloud API HTTP status.
3. Check connectivity freshness/heartbeats and connection errors.
4. Evaluate timeout budgets: connection wait vs. handler response.
5. Inspect device CPU, disk, and callback executor/thread starvation.
6. Verify method contract, payload schema, and response-returning code paths.
7. Reduce fleet fan-out; retry with jitter for idempotent operations.
8. On unknown outcome, **reconcile command ID** before retrying.
9. Canary after fix; resume controlled rollout.

### 28.3. Do Not Raise Every Timeout to Huge Values

If 10,000 invocation threads block waiting for 2 minutes, the backend can exhaust threads/connections and trigger an outage even while IoT Hub stays healthy. Use **bounded concurrency** and return accepted + job tracking for long tasks.

## 29. Runbook 3: C2D Accepted Without ACK

**Scenario:** the service sent maintenance notices to 800 devices. IoT Hub accepted the messages, yet 200 devices have no business acknowledgement after 4 hours.

### 29.1. Procedure

1. Query command/message store: `deviceId`, `messageId`, TTL, queued/feedback/result.
2. Separate offline vs. online devices; compare against **last heartbeat**.
3. Check C2D queue/feedback if supported and enabled.
4. Check whether device callbacks received/settled the messages.
5. If messages expired, transition business state to `EXPIRED`; never claim processed.
6. If devices received them without ACKing, inspect local queues/handlers and D2C route/ingestion lag.
7. Deduplicate on `messageId` before resending; confirm the command is still valid.
8. For critical actions, cross-check **actual device state** or reported properties.
9. Add alerts by cohort/site/offline age and consider alternate channels if business-approved.

### 29.2. Do Not Equate Feedback with Business Success

Even positive hub delivery feedback does not prove a maintenance notice rendered or an actuator changed state. Build explicit ACKs with `messageId`, timestamp, status, and trusted device identity.

### 29.3. Avoid Unbounded Resends

If a device stays offline for over a week, resending 1,000 times does not improve delivery while offline—it just burns quotas and money. A sound workflow tracks **deadline, maxAttempts, and nextRetryAt**, raises alerts, and lets operators intervene. When the device comes online much later, check **command expiration** before executing.

## 30. Availability, Offline-First, and Edge Processing

**IoT devices** routinely operate over intermittent networks. Systems must therefore separate:

- **Local control plane:** state, interlocks, and safety logic must operate while cloud connectivity is lost.
- **Cloud desired configuration:** cloud proposes targets; devices converge when connected.
- **Short-lived command delivery:** direct methods or C2D within deadlines.
- **Durable business workflow:** server/database maintains command history and reconciliation.

### 30.1. Device Offline State Machine

```text
BOOT
  |
  v
LOAD_LOCAL_CONFIG
  |
  v
CONNECTING ----(timeout)----> OFFLINE_MODE
  |                               |
  | connected                     | run local safe operation
  v                               | queue essential local events
REGISTER_CALLBACKS                |
  |                               |
  v                               |
FETCH_FULL_TWIN <------ reconnect-+
  |
  v
RECONCILE_DESIRED + LOCAL_COMMAND_JOURNAL
  |
  v
ONLINE_OPERATION
  |
  +----(network lost)----> OFFLINE_MODE
```

In `OFFLINE_MODE`, devices must never drop safety controls simply because the cloud is gone. **Local limits and fallback setpoints** must be engineered and certified for the hardware. On reconnect, avoid "replaying every command once" without idempotency.

### 30.2. Latest Desired Config vs. Command History

Suppose the service changes interval 10 → 20 → 60 while a device is offline. The device only needs to **apply 60**, not step through 10 and 20. Here **device twin fits**.

Conversely, "count 3 door openings" is event history—you cannot replace it with desired `openCount=3` hoping the device executes three times. Independent events require **durable event/command processing**, idempotency, and auditing.

### 30.3. Edge Gateways and Local Persistence

With gateways/IoT Edge, local work queues or telemetry buffers may be needed when upstream is unavailable, yet:

- Gateway storage can fill up or corrupt.
- Local caches may not mirror IoT Hub C2D queue/twin semantics identically.
- Re-syncing upon coming online can cause bursts.
- Module identities, module twins, and device twins have different scopes.
- Gateway software updates can restart callbacks and local processes.

Test **power loss, full storage, corrupted checkpoints, certificate expiration, and clock drift** as normal edge failure modes.

## 31. Optimizing Latency, Scalability, and Cost

### 31.1. Which Workflows Need Real-Time?

| Requirement | Preferred Mechanism | Operational Cost Considerations |
|---|---|---|
| Update interval across 50k devices | Twin desired/jobs in waves | Twin updates, reports, quotas |
| Instant diagnostics on 100 online devices | Direct method | Connection/response latency, timeouts |
| Non-urgent notice, offline-tolerant for hours | C2D with TTL | Message units, queue/feedback, eventual ACK |
| Safety-critical actuator | Local controller + validated command | Hardware safety, audit, manual approval |
| 1 Hz telemetry from thousands of sensors | D2C telemetry/batching per SLA | IoT Hub throughput, routing, storage/analytics |
| Commands retained for weeks | Durable command store + IoT delivery | Database/Service Bus, worker compute, alerts |

### 31.2. Avoid Over-Frequent Twin Updates

If 50,000 devices send reported temperature every 5 seconds:

```text
50,000 / 5 = 10,000 reported updates/second
```

This is a poor design for both quotas and cost. Reported properties should capture **relatively stable managed state**; frequent measurements belong on D2C telemetry and downstream time-series/analytics systems.

### 31.3. Selective Batching and Compression

IoT Hub messages/payloads have size limits; packing hundreds of readings into one D2C event lowers per-message overhead yet increases latency and loses more samples if a message fails. Size batches to network bandwidth, device RAM, power, downstream retention, and SLOs. Never send raw firmware images inside direct method/C2D payloads.

### 31.4. Where Should Firmware Binaries Go?

A common pattern:

```text
IoT Hub desired:
  targetFirmwareVersion
  rolloutId
  opaque download reference / package manifest ID
          |
          v
Device obtains authorized download URL/token via secure workflow
          |
          v
Azure Blob Storage/CDN (firmware binary)
          |
          v
Device verifies signature/hash/model
          |
          v
Install + rollback strategy
          |
          v
Reported firmware state / D2C result
```

Never push tens of megabytes of binary through device twins or direct method payloads. For signed URLs/SAS, restrict permissions/path/expiry and avoid leaving sensitive URLs in logs/twins beyond policy. **A hash alone does not prove firmware came from a trusted publisher**; trusted signatures and a secure boot/update chain are needed where appropriate.

### 31.5. Billing by Workload

Costs can include IoT Hub tier/units/message operations, Device Provisioning Service, Azure Functions/Service Bus, Azure SQL/Cosmos DB command stores, Event Hubs/stream processing, Blob firmware storage, Log Analytics, networking/egress, certificates, and operations staff. Each service uses its own pricing model. Use the **Azure Pricing Calculator and Cost Management** for exact SKUs/regions/dates rather than assuming one flat unit price across all message types.

## 32. Testing the Exact Semantics of Each Mechanism

An online happy-path demo is insufficient. Run **positive/negative/failure tests** in lab or staging using simulators and authorized real hardware.

### 32.1. Test Matrix

| Test | Desired Twin | Direct Method | C2D Message |
|---|---|---|---|
| Device online | Reported state converges | Handler responds accurately | Receives/ACKs per protocol |
| Device offline minutes | Desired stays stored | Invoke fails/times out per design | Message waits within TTL |
| Reconnect after multiple updates | Applies latest desired | Does not replay old invocations | Receives non-expired messages |
| Malformed payload/schema | Device reports apply failed | Device returns validation error | Device rejects/quarantines/D2C failure per contract |
| Duplicate send/update | Idempotent apply by revision | Dedup by commandId | Dedup by messageId |
| Crash mid-execution | Reconcile actual state after reboot | Unknown outcome + journal | Local journal/settlement plan |
| Throttle/quota | Backoff service updates | Bounded retries | Backoff send, expiry budget |
| Expired credentials | Reconnect/resync | Invocation errors/repair | Delivery delayed/repaired |
| Hub/network outage | Cached desired local rules | Cannot invoke online | Queue behavior only within TTL/quota |
| Old model rejects new config | Report incompatible/failed | Method error | Validation/quarantine/compat fallback |

### 32.2. Testing Direct Method Unknown Outcome

Scenario:

1. Send `setTargetTemperature(commandId=cmd-117, target=4)`.
2. Device applies successfully and writes local journal.
3. Simulate connection loss before the cloud receives the response.
4. Cloud hits timeout and records `UNKNOWN_OUTCOME`.
5. Reconcile device state; if retried with the same command ID, the handler returns the stored result.
6. Confirm the actuator **did not re-execute a non-idempotent side effect**.

This logic test matters far more than simply raising timeouts.

### 32.3. Testing C2D Expiry

1. Keep the lab device offline.
2. Send a message with a valid TTL and record `messageId`.
3. Wait past TTL, then reconnect.
4. Confirm the handler does not process expired messages per IoT Hub/SDK semantics.
5. Command store transitions to `EXPIRED` per deadline; operators can issue a new command if business permits.

Never assume a message still exists just because cloud logs recorded `send accepted`.

### 32.4. Testing Twin Overwrite/Conflict

1. Two services read the same twin/ETag.
2. Service A updates firmware desired.
3. Service B updates sampling desired using the stale copy.
4. Apply conditional updates/merge logic properly.
5. Confirm Service A's property from step 2 is not lost.

If B hits 412, code must refresh/merge/retry within limits—never bypass with arbitrary wildcard ETags.

### 32.5. Testing Reboot/Reconnect

After a device receives desired yet before it reports back:

- Power off safely in the lab.
- Restart from local state.
- Register handlers, GET full twin.
- Check desired version/rollout ID.
- Apply config/resume jobs exactly once.
- Send accurate reported state/ACK.

Never run power-cycle tests on live medical/industrial equipment without approved safety procedures.

### 32.6. Fleet Load Testing

Ramp up in waves:

```text
100 devices -> 1,000 -> 5,000 -> 20,000 simulated devices

Measure per wave:
  twin update/invoke/C2D operations per minute
  throttling/401/5xx
  method p95 latency and timeout
  C2D delivery/business ACK lag
  desired-to-reported convergence p95
  reconnect rate and connection failures
  cloud worker queue depth and cost
```

Simulators may fail to reproduce **carrier latency, weak batteries, drifting RTCs, and constrained CPUs** of real devices. Run a hardware canary phase before full production rollout.

## 33. Architecture Scenario: Smart Cold-Storage Fleet

### 33.1. System Overview

An enterprise operates:

- 8,000 refrigerators across stores connected via LTE/Wi-Fi, some offline for hours.
- Cloud Java service on App Service/AKS.
- Azure IoT Hub for control and telemetry.
- Azure SQL Database/Cosmos DB for command history and device metadata.
- Azure Blob Storage for firmware and diagnostic bundles.
- Azure Functions/stream processors for business ACKs and telemetry.
- Azure Monitor/Log Analytics for metrics and alerts.

### 33.2. Requirement 1: Changing Sampling Interval

Goal: move new-model devices from 30s to 60s after one day, including offline devices.

**Solution:** update **twin desired** in rollout waves with `configRevision` and `effectiveAfterUtc`. Devices GET full twin upon reconnect, validate firmware compatibility, apply, and update reported revision + actual interval. Never fire 8,000 continuous direct methods when part of the fleet is offline.

### 33.3. Requirement 2: Device Diagnostics

Goal: operators must inspect sensor status immediately on a dashboard for **online devices**.

**Solution:** direct method `captureDiagnostics` with bounded connection/response timeouts. Devices return safe details inline; for large log bundles, return `202` + `diagnosticId`, upload securely, and emit a reported/D2C completion event.

### 33.4. Requirement 3: Maintenance Notice

Goal: a short notice for devices that may be offline for 2 hours, with no immediate reply needed.

**Solution:** C2D message with appropriate TTL and `noticeId`. Devices implement a handler that stores and displays the notice per state machine. Cloud tracks business ACK via D2C events, not send accepted alone.

### 33.5. Requirement 4: Unauthorized Cold-Room Door Open

Goal: on abnormal door opening, alert and maintain safe operation even if networking is down.

**Solution:** **local detection/actuation** on the device plus D2C alerts. Never rely on a cloud direct method arriving in time before the device closes a safety relay. Cloud can update thresholds via desired, while local firmware enforces valid bounds.

### 33.6. Classifying State and Outcomes

| Operation | What Cloud Knows Initially | When to Mark Complete |
|---|---|---|
| Desired update | Hub accepted target state | Reported revision + actual value match |
| Direct method diagnostics | Handler returned status/payload within deadline | Short jobs: response; long jobs: final ACK |
| C2D notice | Hub accepted/queued | Device D2C business ACK or reported state |
| Firmware rollout | Desired target written | Signed package installed, reported target/version, health checks |
| Safety alarm | Device sent telemetry | Backend saved/displayed alert while local controls remain active |

### 33.7. When 30% of Devices Lose LTE

Do not retry direct methods thousands of times. **Desired waits for convergence**; C2D survives only within TTL; longer-SLA business commands stay in the command store. As connectivity returns, use bounded reconnects, twin sync, command reconciliation, and rollout waves to avoid message storms.

### 33.8. Acceptance Criteria

- Desired config converges by revision and is device-verified.
- Direct methods are not misused for long-running tasks or offline devices.
- C2D expiry/duplicates/reconnects are tested.
- Commands carry stable IDs, auditing, and reliable business ACKs.
- Transport errors do not cause hazardous side effects or duplicate execution.
- Devices enforce local offline safety.
- Separate security principals/keys/certs and proper RBAC permissions.
- Dashboards distinguish offline, pending, failed, expired, and succeeded.
- Fleet rollouts have canaries, quota headroom, and rollbacks.

## 34. Practice Exercises

### Exercise A – Choosing the Right Mechanism

For each requirement below, choose **device twin / direct method / C2D / combination** and explain:

1. Change interval 15 → 60 seconds across 10,000 devices, many offline for days.
2. Quickly fetch battery level from an online device, needing a response within 10 seconds.
3. Send a maintenance notice valid for 6 hours; device might be temporarily offline.
4. Request a 30-minute firmware upgrade requiring full step-by-step auditing.
5. Trigger emergency shutdown when Internet connectivity is lost.

**Solution guide:** (1) twin desired/reported, (2) direct method, (3) C2D + business ACK, (4) desired/short method + durable command store/reported/D2C progress, (5) local hardware safety logic—**never** rely solely on the cloud.

### Exercise B – Desired/Reported Divergence

Twin shows:

```json
{
  "desired": {
    "telemetryIntervalSec": 60,
    "$version": 19
  },
  "reported": {
    "telemetryIntervalSec": 30,
    "lastAppliedDesiredVersion": 18,
    "applyStatus": "succeeded"
  }
}
```

**Task:** why must this rollout not be marked successful? Write the minimum convergence condition and identify at least three reasons the device hasn't reached revision 19.

**Solution guide:** reported "succeeded" belongs to version 18; require `reported.lastAppliedDesiredVersion=19`, actual value 60, and status succeeded. Possible causes: offline, callback didn't fire, firmware parse error/hardware busy.

### Exercise C – Direct Method Timed Out

Cloud sent `togglePump(commandId=cmd-8)`; the device executed it, yet the response was lost. Cloud timed out.

**Task:** prove why immediate retry is dangerous; design command ID, local journal, state reconciliation, and propose a safer idempotent operation.

**Solution guide:** calling `toggle` twice flips the state back; replace with `setPumpState(target=OFF, revision=N)` featuring local safety bounds, deduplication, and state queries.

### Exercise D – C2D Expired

A device stays offline for 3 days; the service sent a message with a 12-hour TTL and the API returned send accepted.

**Task:** explain why the device did not receive it on return, what must be recorded in the command store, and when to use twin instead of C2D.

**Solution guide:** C2D is retained only within TTL/quota; transition state to `EXPIRED` with business follow-up. Persistent configurations belong in desired state.

### Exercise E – ETag Conflict

Services A and B read the same twin at ETag E11. A patches `desired.firmware.targetVersion`; B replaces the full twin using stale E11.

**Task:** apply conditional updates, handle 412, merge with ownership, and avoid wildcard ETags.

**Solution guide:** B refreshes the twin and patches only fields B owns, respecting ETag/contract and bounded retries without overwriting A's firmware target.

### Exercise F – SDK Adapter in Java

Create interface `IoTHubControlPort` as in Section 19 along with a fake test implementation. Write unit tests:

- `setSamplingInterval` rejects intervals 0 and 9,999.
- `setSamplingInterval` sends the right patch.
- `captureDiagnostics` passes the right method name and bounded timeouts.
- `sendNotice` preserves message ID and TTL.
- When the hub throws throttling, business command state moves into a backoff retry queue.

**Solution guide:** mock the adapter to unit-test business semantics; keep live integration tests separate per SDK/tier and lab credentials.

### Exercise G – Fleet Canary

An enterprise needs to roll out firmware v2 to 20,000 devices. 0.5% of model A devices hit a battery bug during update.

**Task:** design canaries/waves, reported statuses, success thresholds, pause/rollback, and retry-storm prevention.

**Solution guide:** roll out by model/site, halt when critical safety thresholds trip, never mark success from desired updates alone, and use signed firmware manifests with local rollback.

### Exercise H – Monitoring and KQL

Design a dashboard tracking:

- `device connectivity freshness`.
- `desired-to-reported convergence`.
- `direct-method timeout rate`.
- `C2D business ack latency/expiry`.
- `IoT Hub throttling/auth failures`.

**Task:** state which signals come out of the box from Azure Monitor per resource and which **must be instrumented explicitly**. Draft alerts with owners/windows/runbooks.

**Solution guide:** discover metric definitions/diagnostic categories on the hub; business ACKs/convergence usually come from the application command store and device events.

### Exercise I – Device Reset Mid-Command

A device receives direct method `setTargetTemperature`, writes journal STARTED, applies hardware change, and reboots before writing COMPLETED.

**Task:** after reboot, how do you know whether to rerun? Why is deduplicating on `findCompleted` alone insufficient? Design hardware state reading and reconciliation.

**Solution guide:** STARTED is an uncertain state; inspect actual setpoint, command revision, durable journal, and safety bounds, marking success or retrying only with solid evidence.

### Exercise J – Security Threat Modeling

A developer embeds a connection string containing a hub-level owner key in firmware to send device-to-cloud telemetry.

**Task:** describe the blast radius; propose per-device identities, DPS, X.509/SAS rotation, server RBAC, and keeping keys out of logs.

**Solution guide:** hub owner credentials grant overly broad access; replace with per-device identities/credentials and scoped cloud service principals/managed identities.

### Exercise K – Offline Gateway

An IoT Edge gateway loses Internet for 36 hours while still receiving local sensor events; on reconnect it must sync to Azure.

**Task:** distinguish local telemetry store-and-forward from C2D queues and twin desired sync; identify quota/disk/ordering/dedup/failure tests.

**Solution guide:** verify exact IoT Edge runtime/store capabilities rather than assuming cloud-to-device messages buffer through gateways indefinitely; set local disk retention and replay safeguards.

### Exercise L – Sizing and Cost

50,000 devices must report temperature at 1 Hz, report firmware version daily, and receive config changes a few times a month.

**Task:** pick D2C telemetry for readings, reported properties for firmware/state, desired for config; estimate operations and impact on IoT Hub tier/units, downstream Storage, and Log Analytics.

**Solution guide:** 50,000 messages/second is a massive workload requiring batching, capacity planning, and official pricing lookup—never update twins every second.

## 35. Self-Check Questions

**1. What is a device twin used for?** Storing device metadata/tags and desired/reported state, supporting configuration synchronization.

**2. Who can write desired properties?** Cloud/service principals with appropriate IoT Hub permissions—not the device client modifying desired arbitrarily.

**3. Who writes reported properties?** The authenticated device client; the cloud reads them to track device state.

**4. Can devices read tags directly via the device twin API?** No. Tags are service-side metadata.

**5. Does an accepted desired update mean the device applied it?** No. Wait for reported revision/actual state confirmation.

**6. When offline across multiple desired changes, must a device replay every delta?** No; typically it syncs **latest desired/full twin** and converges state.

**7. What does `$version` do?** Identifies system-managed change ordering on desired/reported for reconciliation.

**8. What is ETag used for?** Optimistic concurrency on twin updates, preventing stale writers from overwriting newer changes per API semantics.

**9. Should passwords be placed in twins?** No. Twins are managed state/metadata readable by multiple principals.

**10. Are direct methods queued when a device is offline and invoked upon reconnect?** Direct methods have no durable offline queue.

**11. When a direct method times out, is it certain the device didn't run it?** No; outcome may be uncertain if the response was lost.

**12. Why can a direct method returning 202 make sense?** The device accepted a background job; the cloud expects a final ACK via another channel.

**13. Which direct methods are dangerous to retry?** Non-idempotent actions like `toggle`, `increment`, or `openOnce` without journals/reconciliation.

**14. What is the main difference between C2D and direct methods?** C2D is asynchronous messaging with queue TTL; direct methods are online request–response.

**15. Does C2D accepted prove the device displayed the notice?** No. Business acknowledgement from the device is required.

**16. Does C2D store messages indefinitely while a device is offline?** No; finite TTL and quotas apply.

**17. Does MQTT ACK/settlement prove business completion?** No; it only reflects transport/client semantics.

**18. How should C2D duplicates be handled?** Stable message/command IDs, dedup journals, idempotent handlers, and revision checks.

**19. Does the IoT Hub service replace a command audit database?** Not when the business needs long-term history and reconciliation.

**20. Does cloud Entra RBAC mean the device already authorized the firmware?** No; devices still validate payloads, revisions, and safety policies.

**21. Why avoid embedding a hub owner shared key in all firmware?** Compromising one device exposes hub-wide access, creating a huge blast radius.

**22. Is device twin suited for storing temperature every 100 ms?** No; D2C telemetry fits better due to twin/throttling semantics.

**23. When a firmware rollout fails on 5% of devices, what is the first action?** Pause waves, analyze affected cohorts and reported states, then safely roll back/fix.

**24. Does a connected flag prove an actuator is healthy?** No. Heartbeats, actual state, error codes, and fresh telemetry are needed.

**25. Why maintain a per-device idempotency journal?** Prevents re-execution after timeouts, reconnects, or reboots, protecting side effects.

**26. Does offline IoT Edge mean every C2D automatically buffers on the gateway?** No; inspect specific runtime/module capabilities and retention settings.

**27. Does a direct method returning success guarantee firmware download finished?** Not if the method only started a background job; check final state.

**28. Why enforce site/tenant operator authorization outside IoT Hub IAM?** Hub data-plane permissions do not automatically express all business authorization rules.

**29. Is KQL table `IoTCommandAudit_CL` pre-created by IoT Hub?** No; it is an illustrative custom table ingested by the application.

**30. What is the most important rollout success criterion?** Devices safely applied the state/job at the target revision, evidenced by reported/business ACKs.

## 36. Production Readiness Checklist for Cloud-to-Device Flows

### 36.1. Mechanisms and Contracts

- [ ] Verified **IoT Hub tier/SKU** supports required device twin, direct method, and C2D features; never assume Basic/Standard share identical capabilities.
- [ ] Separated device twin state, direct method request–response, and C2D asynchronous delivery.
- [ ] Desired properties include schema/revision, validation, and TTL/expiry policies if required by business logic.
- [ ] Reported reflects **actual applied state** and last applied desired revision.
- [ ] Devices GET full twin after reconnect/reboot rather than relying solely on delta subscriptions.
- [ ] Tags used for grouping/querying, never as IAM authorization.
- [ ] ETag/optimistic concurrency or field ownership enforced to prevent lost updates.
- [ ] Direct methods used only for quick online actions or returning accepted for background jobs.
- [ ] Direct method timeouts/unknown outcomes backed by idempotency/reconciliation.
- [ ] C2D payloads carry message ID, TTL, contract version, and proper handlers.
- [ ] Distinguished hub accepted, transport settlement/feedback, and business ACK.
- [ ] No assumptions that C2D stores commands indefinitely while offline.
- [ ] Business command store maintains unique IDs, auditing, deadlines, retries, statuses, and retention where needed.

### 36.2. Java Device and Safety

- [ ] Device SDK/transport versions support callbacks/twin/method/C2D per hub tier.
- [ ] Individual device identities; no hub-level owner keys in firmware.
- [ ] TLS certificate/CA hostname validation and credential refresh operational.
- [ ] Callbacks do not block long; local queues are bounded.
- [ ] Handlers enforce schema validation, allowlisted actions, and range/safety checks.
- [ ] Non-idempotent commands use durable journals and post-reboot reconciliation.
- [ ] Command expiry and clock skew handled; stale commands rejected.
- [ ] Local device safety operates when cloud/network drops.
- [ ] Firmware signatures/models verified with safe rollback where appropriate.
- [ ] C2D transport settlement matches SDK/transport, with separate business ACKs.
- [ ] Reported/telemetry omit credentials, secrets, and sensitive data.

### 36.3. Backend, Fleet, and Security

- [ ] Backend uses Entra managed identity/RBAC or securely managed service credentials.
- [ ] Azure control-plane permissions separated from IoT Hub data-plane permissions.
- [ ] Operator API checks tenant/site/role/operation before dispatching.
- [ ] Commands stay within hub quotas/throttling and avoid retry storms.
- [ ] Fleet rollouts have waves/canaries, pause/rollback, and convergence checks.
- [ ] Offline cohorts have deadlines/recovery plans rather than fake success.
- [ ] Service-side updates handle 412 conflicts per business logic.
- [ ] Command store, dispatch workers, and ACK processors are idempotent.
- [ ] IoT Hub has appropriate network/egress/ports/protocols and secret rotation plans.
- [ ] DPS/provisioning, device decommissioning, and revocation have clear lifecycles.
- [ ] No logs contain SAS tokens, hub keys, private certificates, or raw sensitive payloads.

### 36.4. Monitoring, Testing, and Cost

- [ ] Azure Monitor metrics discovered from the exact IoT Hub resource/tier.
- [ ] Diagnostics, workspace ingestion, and log schemas tested in practice.
- [ ] Dashboards show twin convergence, method timeouts, C2D business ACK/expiry, reconnects, and hub throttling.
- [ ] Alerts include owners, thresholds, evaluation windows, action groups, and runbooks.
- [ ] Tested device online/offline/reconnect, TTL expiry, method timeouts, and duplicate messages.
- [ ] Tested crashes between side effect and ACK, full twin resync, and ETag conflicts.
- [ ] Tested credential expiry/rotation, clock drift, and firmware schema incompatibility.
- [ ] Load-tested wave rollouts before updating the full fleet.
- [ ] Estimated costs for IoT Hub tier, operations, downstream processing, Storage, and monitoring.
- [ ] Never run hazardous hardware control actions in lab/staging without safety approval.

## 37. Conclusion

**Device twin, direct method, and cloud-to-device message** address three distinct needs in Azure IoT Hub. **Device twin** captures desired and reported state, ideal for synchronizing configuration even across offline periods; **direct method** fits short actions needing a synchronous response while devices are reachable; **C2D message** provides an asynchronous queued channel with TTL for suitably designed notices/commands. None of these mechanisms automatically guarantees every side effect runs exactly once, without data loss, and with complete auditing.

When building production Java IoT systems on Azure, design **schemas/revisions/command IDs, ETag concurrency, idempotency journals, business acknowledgements, deadlines, and local safety controls**. Keep cloud service and device identities separate, enforce TLS, managed identity/RBAC, and secret protection. Combine **Azure Monitor, diagnostics, device reported state, and D2C telemetry**, staged wave rollouts, and offline/failover runbooks so you know not just that IoT Hub accepted an operation, but that **devices actually converged to a safe state**. That is the foundation for a scalable, auditable, and resilient IoT system on Microsoft Azure.
