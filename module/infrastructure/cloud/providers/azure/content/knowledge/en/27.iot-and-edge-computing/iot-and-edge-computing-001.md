# IoT Telemetry Ingestion Architecture on Azure

Imagine a factory with 15,000 sensors measuring temperature, vibration, and electrical power. Devices send data over cellular networks, Wi-Fi, or edge gateways. Some devices only have connectivity for a few minutes each hour; others emit multiple samples per second. The operations center wants to detect overheating quickly, while the analytics team wants to store months of data for predictive maintenance.

The problem is not just opening an HTTP endpoint to receive JSON. A reliable IoT platform must **authenticate each device's identity, ingest data at scale, handle duplicates/errors/disconnections, route as needed, store securely, provide observability, and control costs**.

On Microsoft Azure, a common approach uses **Azure IoT Hub** to connect and manage devices, **Azure IoT Hub Device Provisioning Service (DPS)** for initial provisioning, **Azure IoT Edge or appropriate edge processing solutions** to buffer and process near devices, combined with **Azure Functions, Azure Stream Analytics, Azure Event Hubs, Azure Data Explorer, Azure Blob Storage/ADLS Gen2, and Databricks** for different processing paths.

This lesson belongs to the **IoT and Edge Computing** chapter in the **CLOUD_PROVIDERS_AZURE** module. It connects knowledge of Azure subscriptions, resource groups, Microsoft Entra ID, virtual networks, storage, monitoring, security, and cost into a deployable and operable IoT application architecture.

**Scope:** architecture and hands-on practice with Azure IoT Hub for device-to-cloud (D2C) telemetry. Service plans, limits, and IoT features may change over time; check actual SKUs, APIs/SDKs, regions, and quotas before deployment. Examples only illustrate on an authorized lab environment, not executed directly on a real subscription.

## 1. Learning Objectives

After this lesson, you can:

1. Distinguish telemetry, device state, command, device twin, event, and business alert.
2. Draw an end-to-end architecture from sensor, gateway, and IoT Hub to the hot path and cold path.
3. Choose the right role for IoT Hub, Event Hubs, DPS, IoT Central, and edge processing.
4. Explain the provisioning process, device identity, SAS/X.509, and credential lifecycle.
5. Compare MQTT, AMQP, HTTPS, and approaches for constrained networks.
6. Design a telemetry envelope with device ID, event ID, sequence, timestamp, schema version, measurement units, and quality flags.
7. Understand the IoT Hub built-in Event Hubs-compatible endpoint, message routes, custom endpoints, enrichments, and fallback.
8. Design near-real-time processing with Azure Functions/Stream Analytics and long-term storage with ADLS Gen2/Blob.
9. Recognize at-least-once delivery, partition-scoped ordering, idempotency, retry, backpressure, and poison messages.
10. Design edge buffering/store-and-forward when devices lose connectivity.
11. Estimate message volume, throughput, IoT Hub units, quotas, and costs.
12. Configure security with device-level credentials, least privilege, private access, encryption, and data lifecycle.
13. Practice using Azure CLI/Python SDK to send simulated messages and verify the receiving path.
14. Design monitoring, incident runbooks, load testing, rollback, and recovery.
15. Apply a production checklist for a multi-device/multi-site IoT system.

## 2. What Is Telemetry and What Is It Not?

### 2.1. Continuous Measurement Data

**Telemetry** is observational data sent by a device, typically including:

- Temperature, humidity, pressure, voltage, current.
- GPS/speed/location when authorized and for a legitimate purpose.
- Heartbeat, firmware version, battery percentage.
- Motor status, vibration metrics, uptime.
- Environmental or energy measurements over time.

Document example:

~~~json
{
  "schemaVersion": "1.0",
  "eventId": "evt-3f9a",
  "deviceId": "motor-042",
  "bootId": "boot-19",
  "sequence": 1835,
  "eventTimeUtc": "2026-11-20T08:30:00.000Z",
  "measurements": {
    "temperatureC": 78.4,
    "vibrationMmS": 4.8,
    "currentA": 3.2
  },
  "quality": "ok"
}
~~~

This is a sample payload. In a proper pipeline, `deviceId` in the **message body should not be treated as proof of device authentication**; the application must cross-check against the identity verified by IoT Hub through system metadata and registry policies. A compromised device can send any JSON content.

### 2.2. Distinguishing Four Streams

| Type | Direction | Purpose | Example |
|---|---|---|---|
| Device-to-cloud telemetry | Device → cloud | Send measurements/events | Temperature every minute |
| Device state/reported properties | Device → cloud registry/twin | Configuration/capability state | Firmware version, connectivity state |
| Cloud-to-device command | Cloud → device | Request an action | Start measuring immediately, controlled reboot |
| Desired configuration | Cloud → device twin | Declare desired state | Sampling interval = 60 seconds |

You should not put all long-lived state into the telemetry stream if you need to query the current configuration via device twin. Conversely, **device twin is not a time-series store containing billions of samples**. Commands and telemetry also differ in confirmation, timeout, retry, and physical impact.

### 2.3. Telemetry Event vs. Business Alert

A temperature event of 78.4°C is an **observation**. An alert "Motor 42 overheating for 5 consecutive minutes" is a **processing conclusion** based on rules/time windows.

If a sensor sends the same sample three times, the pipeline must avoid firing three alerts or counting it three times in the average. If a device sends data late, the business logic must decide whether to use measurement time or cloud arrival time.

## 3. End-to-End Reference Architecture

~~~mermaid
flowchart LR
    S["Sensors / devices"] --> G["Edge gateway / IoT Edge when needed"]
    S --> I["Azure IoT Hub"]
    G --> I
    DPS["IoT Hub DPS"] -. "Provision identity/assignment" .-> S
    DPS -. "Assign hub" .-> I
    I --> R["Message routing / built-in endpoint"]
    R --> H["Hot path: Stream Analytics / Functions"]
    R --> C["Cold path: Blob / ADLS Gen2"]
    H --> A["Alerts / operational store / dashboards"]
    C --> T["Databricks / Data Explorer / analytics"]
    H --> M["Azure Monitor / runbook"]
    T --> M
~~~

Each layer has distinct responsibilities:

1. **Device/gateway:** capture measurements, ensure formatting, timestamps, buffering, and retries.
2. **Provisioning and identity:** register identity, issue credentials, assign device to a hub.
3. **IoT ingestion:** authenticate devices, accept D2C messages within quota, route messages.
4. **Hot path:** detect anomalies, enrich/aggregate, generate alerts/operational views.
5. **Cold path:** store raw/standardized data for reconciliation and long-term analytics.
6. **Governance:** access permissions, encryption, retention, auditing.
7. **Operations:** metrics, logs, alerting, incident handling, and cost management.

**A message accepted by IoT Hub does not mean all downstream systems have processed it successfully.** Each stage needs mechanisms to track progress, handle retries, observe consumer lag, and test recovery.

### 3.1. Event-Level Data Flow

~~~mermaid
sequenceDiagram
    participant D as Device
    participant H as IoT Hub
    participant R as Route / Event endpoint
    participant P as Processor
    participant L as ADLS / Data store
    participant O as Operator

    D->>H: Authenticate + send telemetry
    H-->>D: Protocol-level acknowledgement
    H->>R: Route accepted message
    R->>P: Consume event
    P->>P: Validate, deduplicate, process
    P->>L: Persist raw/processed records
    P->>O: Alert only when business rule matches
~~~

An ACK from IoT Hub to the device only confirms within the scope of the supported protocol/service interaction; **it is not a guarantee of final record persistence, nor confirmation that an alert reached the on-call operator**. To provide end-to-end guarantees, you must design downstream checkpoints, idempotency, and separate business acknowledgements.

## 4. Choosing the Right Service for the Role

### 4.1. Azure IoT Hub

**Azure IoT Hub** is designed for communication between IoT devices and the cloud:

- Device registry and individual identity for each device.
- Device-to-cloud telemetry ingestion.
- Cloud-to-device communication according to supported SKU/features.
- Device twins, jobs, or direct methods depending on tier and capability.
- Message routing to supported endpoints.
- Device authentication using mechanisms such as SAS or X.509.
- Monitoring of device connectivity, ingress, routing, and quotas.

Use IoT Hub when you require **device identity, connection lifecycle, and device management**, not just receiving an anonymous stream of events.

### 4.2. Azure Event Hubs

**Azure Event Hubs** is a general-purpose streaming event ingestion service with partitions, consumer groups, and stream processing tools.

| Question | IoT Hub | Event Hubs |
|---|---|---|
| Has a dedicated device registry? | Yes | No equivalent |
| Has Device Provisioning Service to assign devices? | Can integrate DPS | Not a standard Event Hubs mechanism |
| Has device twins/methods? | Depends on tier/features | Not a core feature |
| Distributes partitioned event streams? | Yes via event endpoints | Yes |
| Suitable for generic logs/events/telemetry from backend? | Possible, but often excessive abstraction | Very suitable |
| Device-level identity/management is the focus? | Yes | No |

If 100,000 real sensors need enrollment, certificate rotation, and online/offline management, IoT Hub is usually the primary candidate. If an already-authenticated application backend sends a large volume of pure application events, Event Hubs may suffice.

### 4.3. IoT Hub Built-in Endpoint Is Not a Standalone Event Hubs Namespace

IoT Hub has a **built-in Event Hubs-compatible endpoint** so Event Hubs-compatible stream consumers can read device-to-cloud messages. However:

- This endpoint belongs to IoT Hub, not an Event Hubs namespace you created.
- It has its own configuration/partitions/retention/authorization scoped to IoT Hub.
- Not all Event Hubs management features and pricing options apply as-is.
- If you want an independent stream for multiple consumer groups, you can **route IoT Hub to an Event Hubs custom endpoint** and then use that namespace as needed.

Do not confuse IoT Hub's **Event Hubs-compatible endpoint** with a separately provisioned Event Hub.

### 4.4. Azure IoT Hub Device Provisioning Service (DPS)

**DPS** enables zero-touch provisioning: a new device uses enrollment/attestation information to be assigned to the appropriate IoT Hub, instead of hard-coding all hub hostnames and credentials in firmware.

DPS can use supported attestation methods such as X.509 and symmetric keys, along with hardware-based security options like TPM depending on device/platform and service support.

DPS does not turn an untrusted device into a secure device: root keys/certificates must still be generated, stored, provisioned, and revoked according to security processes.

### 4.5. Azure IoT Central

**IoT Central** targets building operational/application IoT solutions under a more highly managed model, with device templates, dashboards, and workflows according to current capabilities.

- Use when you want a fast, business-oriented IoT application that fits the provided capabilities.
- Use a self-built IoT Hub + data services architecture when you need fine-grained control over ingestion, routing, data contracts, or multiple dedicated pipelines.

Do not decide based on product name alone; verify roadmap, pricing, region, feature availability, and data ownership at selection time.

### 4.6. Azure IoT Edge and Processing at the Edge

IoT Edge and appropriate Azure edge solutions can help run workloads close to devices, reduce bandwidth, process locally, and buffer data when networks are intermittent. Newer models like Azure IoT Operations have different deployment prerequisites and management approaches than traditional IoT Edge; **do not apply one set of edge commands/features across every product**.

Choose edge when you have:
- Latency requiring local response.
- Intermittent networks or high transmission costs.
- Needs to filter/deduplicate/aggregate before sending to the cloud.
- Sensitive data requiring processing before leaving the factory.
- Industrial device protocols that cannot connect directly to IoT Hub.

## 5. Devices, Identity, and Provisioning

### 5.1. Device Lifecycle

~~~mermaid
flowchart LR
    M["Manufacture / enroll"] --> P["Provision via DPS"]
    P --> R["Register identity in IoT Hub"]
    R --> C["Connect and authenticate"]
    C --> O["Send telemetry / receive config"]
    O --> K["Rotate key / update certificate"]
    K --> O
    O --> D["Disable / retire / delete identity"]
~~~

Each stage needs an owner and audit logs. Do not share a single system-wide symmetric key if individual identities can be issued; when one device's key is compromised, it should not cause an incident across the entire fleet.

### 5.2. Symmetric Key and SAS Token

In a lab scenario, a device identity can use a symmetric key and the SDK generates a **Shared Access Signature (SAS) token** to authenticate with IoT Hub.

Risks:
- A stolen device can expose the key.
- Shared keys stored in plaintext firmware are easy to copy.
- Expired tokens/credentials cause devices to disconnect.
- Credentials leaked in logs or source repos.
- Using a hub-level connection string on a device grants overly broad permissions.

In production, prefer storing secrets in a secure element/TPM where appropriate, implementing rotation/revocation, and never placing service keys on devices.

### 5.3. X.509 Certificates

X.509 allows each device to have its own private key and prove identity with properly designed certificates/chains. You need:

1. Supported trust chain/CA and enrollment types.
2. Protection of the private key in hardware/secure store.
3. Management of certificate expiration and rotation.
4. Revocation/disabling of compromised devices.
5. Coordinating certificate changes without fleet-wide downtime.
6. Testing the system when certificates expire or clocks drift.

**X.509 does not guarantee security if private keys can still be freely copied or the provisioning server trusts an unverified certificate.**

### 5.4. DPS Enrollment and Assignment

A typical flow:

~~~mermaid
sequenceDiagram
    participant D as New device
    participant P as DPS
    participant H as Assigned IoT Hub
    D->>P: Enrollment/attestation request
    P->>P: Verify enrollment and choose hub
    P-->>D: Assignment / hub info
    D->>H: Authenticate with provisioned identity
    H-->>D: Connection established
    D->>H: Device-to-cloud telemetry
~~~

You can use **individual enrollments** or **enrollment groups** depending on devices and attestation methods. Assignment policies can target balancing across fleet/region/hub under supported conditions.

DPS handles provisioning; **it does not replace the continuous telemetry processing path**. After provisioning, devices send measurements to the assigned IoT Hub.

### 5.5. Device Twin and Reported/Desired Properties

A device twin represents device metadata/configuration in a JSON model:

~~~json
{
  "properties": {
    "desired": {
      "samplingIntervalSeconds": 60
    },
    "reported": {
      "firmwareVersion": "2.3.1",
      "samplingIntervalSeconds": 60,
      "sensorHealth": "ok"
    }
  }
}
~~~

The JSON above is illustrative, not the full twin response. Distinguish between:

- **Desired:** state the cloud wants the device to apply.
- **Reported:** state the device reports it is currently applying.
- **Tags:** cloud-side metadata according to granted permissions.

Do not create a new reported property for every temperature reading. Twins are meant for state and configuration, not a time-series table of billions of samples.

## 6. Device → Azure Protocols

### 6.1. Comparing MQTT, AMQP, and HTTPS

| Protocol | When Suitable | Key Considerations |
|---|---|---|
| MQTT over TLS | Resource-constrained devices, long-lived connections | Session/reconnect/QoS per IoT Hub support; not a generic MQTT broker |
| MQTT over WebSockets | Networks allowing only HTTPS/WebSockets | TLS/443, overhead, and proxy compatibility |
| AMQP over TLS | Capable SDKs/gateways, multiplexing/messaging | Requires understanding connection/session and network policy |
| AMQP over WebSockets | Port-restricted proxies | TLS/443, long-lived connections |
| HTTPS | Simple cases, infrequent sends | Request/response overhead; receive/feedback behavior differs from persistent protocols |

Common ports for direct TLS connections include MQTT 8883 and AMQP 5671; WebSockets/HTTPS typically use 443. **Verify exact ports/protocols against the Azure IoT SDK/version and network policy in use**; do not open every port just because of an example.

### 6.2. IoT Hub MQTT Is Not a General-Purpose MQTT Broker

IoT Hub supports MQTT connection methods and topic conventions specific to IoT Hub. Do not assume devices can freely publish/subscribe to arbitrary topics like a standard MQTT broker, or use every feature of all MQTT versions.

For new devices, prefer the **Azure IoT Device SDK** suited to the language/device so the SDK manages protocol, authentication, TLS, and reconnects. If a raw MQTT client must be used, read protocol-level documentation and test thoroughly.

### 6.3. Unstable Networks

An LTE sensor may lose connectivity mid-send:

- The device needs a buffer and a local capacity limit policy.
- Retry with exponential backoff and jitter.
- Do not regenerate `eventId` on each retry of the same sample.
- Include `sequence`/boot ID to detect missing or duplicate samples.
- Distinguish send accepted from end-to-end processed.
- Monitor backlog age and drop rates.
- Have a sampling/throttling policy during overload.

Do not retry infinitely at maximum speed: that can drain batteries, saturate the hub, and increase costs.

## 7. Designing the Telemetry Contract

### 7.1. Recommended Envelope

~~~json
{
  "schemaVersion": "1.0",
  "eventId": "evt-20261120-00183",
  "deviceId": "motor-042",
  "siteId": "factory-hcm",
  "bootId": "boot-19",
  "sequence": 1835,
  "eventTimeUtc": "2026-11-20T08:30:00.000Z",
  "firmwareVersion": "2.3.1",
  "measurements": {
    "temperatureC": 78.4,
    "vibrationMmS": 4.8,
    "currentA": 3.2
  },
  "quality": {
    "sensorStatus": "ok",
    "batteryPct": 92
  }
}
~~~

Not every field needs to be resent redundantly in the payload if a trusted metadata source already exists; prioritize balancing **message size, traceability, and data governance**.

### 7.2. Field-by-Field Breakdown

| Field | Purpose | Principle |
|---|---|---|
| schemaVersion | Control contract changes | Documented version, backward compatibility |
| eventId | Idempotency/dedup | Keep stable across retries |
| deviceId | Business association with device | Cross-check against system identity from IoT Hub |
| siteId | Facility/location partitioning | Do not arbitrarily trust client value for authorization |
| bootId | Distinguish boot cycles | Combine with sequence to detect duplicates |
| sequence | Device-generated sequence number | May reset on boot; combine with bootId |
| eventTimeUtc | Sensor measurement time | Account for clock skew and clock quality |
| firmwareVersion | Analyze issues by version | Do not treat as attested proof |
| measurements | Technical readings | Include unit, range, calibration |
| quality | Quality/health/flags | Distinguish unknown, invalid, and 0 |

### 7.3. Units, Timezone, and Precision

A bare value `78.4` without units is insufficient. Use field names with units or a schema with explicit units.

- Temperature: °C or °F?
- Vibration: mm/s RMS or acceleration g?
- Energy: Wh or kWh?
- Time: UTC ISO 8601 and offset?
- Location: which coordinate system and what precision?
- Precision: decimal/double type and rounding policy?

In analytics, never double revenue/energy simply because two measurement units were interpreted differently; use schema evolution and contract tests.

### 7.4. System Metadata and Identity Source

IoT Hub has service-processed/attached metadata, such as device identity and receipt time depending on endpoint/protocol. Consumers should:

1. Read device identity from system properties when provided by the API.
2. Compare with `deviceId` in the payload if needed; do not trust the payload alone.
3. Record cloud receipt/enqueue time separately from `eventTimeUtc`.
4. Record application message ID/correlation ID for dedup/tracing.
5. Never put account keys or raw SAS tokens into payloads.
6. Be careful when using hub/protocol metadata in route queries.

### 7.5. Schema Evolution

If firmware v2 adds `vibrationMmS` while firmware v1 does not have it:

- Keep the version field explicit.
- Define default/missing values.
- Distinguish an absent field from the value 0.
- Downstream parsers must handle multiple versions during rollout.
- Send unknown schemas to quarantine instead of silently dropping them.
- Have an owner approve breaking changes.
- Have a data backfill/replay plan if transformations change.

**The telemetry contract is an agreement between firmware, ingestion, and analytics.** It must be tested as part of application releases, not only in cloud-only tests.


## 8. Azure IoT Hub: Ingestion and Load Throttling Layer

### 8.1. Device D2C Send Flow

~~~mermaid
flowchart LR
    D["Device SDK"] --> A["TLS + device auth"]
    A --> H["IoT Hub ingress"]
    H --> V["Validate protocol / quota"]
    V --> R["Message routing"]
    R --> E["Built-in Event Hubs-compatible endpoint"]
    R --> C["Custom endpoint(s)"]
    E --> P["Stream consumer"]
    C --> S["Storage / downstream services"]
~~~

A message going through IoT Hub typically passes through connection, authentication, service acceptance, routing, and downstream consumer. A device sending successfully does not mean the message has appeared in reports.

### 8.2. IoT Hub Units, Tiers, and Quotas

Azure IoT Hub has service tiers and capacity units with different quotas/throttling limits. When designing, check:

- Number of registerable devices and concurrent connections.
- Daily device-to-cloud message volume per tier/unit.
- Throughput/burst limits for D2C operations.
- Message size limit, metering granularity, and billing rules.
- Routing throughput/custom endpoint availability.
- Consumer partitions and retention of the built-in endpoint.
- Limits on service operations other than telemetry.
- Region, availability, and quota request process.

Do not assume quota numbers from one SKU apply to all. A lab SKU may lack features required by a production deployment.

### 8.3. Handling Throttling

If devices simultaneously send a large burst:

1. IoT Hub may return throttling error codes/messages per SDK/protocol.
2. Devices must retry with exponential backoff and jitter.
3. Edge buffers must retain data according to storage policy.
4. The fleet may need staggered send schedules to avoid aligning on the same minute.
5. Operations reviews IoT Hub units/quotas and downstream capacity.
6. If exceeding limits of one hub or region, plan a multi-hub strategy with managed provisioning.

**Scaling out the stream processor does not increase IoT Hub ingress quota.** Conversely, adding IoT Hub units does not automatically fix a slow-reading consumer.

### 8.4. Decoupling Ingress from Processing

Firmware should not call databases or complex business APIs directly for each sample, because:

- Devices would have to hold many credentials and dependencies.
- Upstream becomes coupled to downstream schemas/latency.
- Database outages affect all device connections.
- Changing pipelines becomes hard without firmware updates.
- Controlling backpressure and retries becomes difficult.

IoT Hub acts as the ingestion layer, then routes to processing streams with separate responsibilities.

## 9. Message Routing: Delivering Telemetry to the Right Destination

### 9.1. Why Is Routing Needed?

For example, a factory wants to:

- Send **all telemetry** to ADLS Gen2/Blob for archiving.
- Send high-temperature events to a stream processor.
- Send poor-quality messages to a monitoring channel.
- Separate data by event type or factory when policy allows.

IoT Hub message routing sends messages matching conditions to supported endpoints, rather than having firmware send multiple copies to multiple systems.

### 9.2. Typical Endpoints and Destinations

| Destination | Purpose | Key Considerations |
|---|---|---|
| Built-in Event Hubs-compatible endpoint | Consumer reads telemetry stream from hub | Retention/partitions/consumer groups per IoT Hub config |
| Custom Azure Event Hubs endpoint | Separate stream for multiple consumers | Has separate namespace, quota, RBAC, retention, and cost |
| Azure Blob Storage endpoint | Store D2C data for cold path | File format/batching, naming, latency, and retention |
| Service Bus queue | Supported downstream work queue | Not optimal as an infinite time-series store replacement |
| Service Bus topic | Fan-out workload events via subscription filters | Handle duplicates/TTL/dead-letter per downstream design |

Endpoint support, authentication, and route sources have different limits depending on IoT Hub tier. **ADLS Gen2 often builds on Azure Blob Storage capabilities**, but filesystem/hierarchical namespace requirements, paths, file formats, and pipelines must be verified when connecting to storage routes.

### 9.3. Route Source, Condition, and Priority

A route has these elements:

- **Source:** event type such as device telemetry per configurable capabilities.
- **Condition/query:** expression using system properties, application properties, or payload body when body-based routing is supported.
- **Endpoint:** destination where data is sent when the condition matches.
- **Enabled status:** whether the route is active.

Conceptual example:

~~~text
Route raw-all:
  Source: Device Telemetry Messages
  Condition: true
  Endpoint: Storage archive

Route operational-hot:
  Source: Device Telemetry Messages
  Condition: messageType = "telemetry"
  Endpoint: Event Hubs analytics

Route urgent:
  Source: Device Telemetry Messages
  Condition: priority = "high"
  Endpoint: Event Hubs alerting
~~~

This is an architectural description, **not complete Azure CLI syntax or route query DSL**. Actual conditions must use supported syntax and exact property names. Do not assume any arbitrary JSON payload string is automatically a route property.

### 9.4. Body-Based Route Queries Require Proper Metadata

When IoT Hub needs to parse the **JSON body** for a route condition, the message typically must declare content type and encoding such as:

~~~text
contentType: application/json
contentEncoding: utf-8
~~~

When using an SDK, these are SDK message properties/metadata, not necessarily two fields inside the JSON body.

If firmware forgets to set content type/encoding, body-based routes may not match as intended even though the message is received by the hub. If the goal is only to classify message types, use a controlled application property like `messageType` or `priority` to avoid complex body parsing at the routing layer.

### 9.5. Routing Fallback and Built-in Endpoint

A common mistake: "IoT Hub always sends a copy to the built-in endpoint even when custom routes are enabled."

In practice, you must **verify the routing configuration to the built-in endpoint and fallback**. Once message routes exist, default routing behavior can change; messages not matching any route may be handled according to fallback settings. The design must clearly define:

- Which route sends all telemetry to the cold path?
- Does the built-in endpoint still receive messages?
- Which route targets the built-in events endpoint when needed?
- Is fallback enabled as intended?
- Are any unmatched messages dropped from downstream?

Test every scenario with a test device and endpoint consumer; do not infer from "route configured successfully" that data is definitely arriving at the destination.

### 9.6. Message Enrichment

Message enrichments can add IoT Hub metadata to routed messages per service capabilities, such as tenant/site information sourced from device twin tags or hub info.

Benefits:
- Downstream does not need to fully trust `tenantId` in the payload.
- Can reduce registry/twin lookups in consumers.
- Easy to attach ownership/schema/route metadata.

Risks:
- Source metadata becomes stale.
- Routes or consumers depend on a property name that gets changed.
- Sending tenant tags/PII to unauthorized destinations.
- Larger messages, increasing metering units and storage.

Only enrich necessary properties, with data classification and tests.

## 10. Hot Path: Near-Real-Time Processing

### 10.1. Architecture

~~~mermaid
flowchart LR
    H["IoT Hub"] --> E["Built-in endpoint / Event Hubs"]
    E --> F["Azure Functions / Stream Analytics"]
    F --> C["Operational DB / Azure Data Explorer"]
    F --> A["Alerts / Logic Apps / Incident workflow"]
    F --> M["Monitor / metric / logs"]
~~~

The **hot path** is the fast processing branch serving alerts, near-current state, dashboards, or operational controls. End-to-end latency depends on ingestion, endpoint, consumer scheduling, query windows, and downstream.

### 10.2. Azure Stream Analytics

**Azure Stream Analytics** fits many SQL-like streaming problems:

- Filter messages exceeding thresholds.
- Group by time window.
- Count event occurrences within an interval.
- Compute averages/medians using supported functions.
- Join with reference data per capability.
- Write results to appropriate sinks.

Logic example:

~~~text
Input: IoT Hub / Event Hubs-compatible endpoint
Filter: messageType = telemetry
Group: deviceId + 5-minute event-time window
Metric: average temperatureC
Rule: average > 80 and >= minimum sample count
Output: operational alerts
~~~

Stream Analytics has its own query language and window semantics; do not copy pseudo-SQL as a live query without verifying event time mapping, `TIMESTAMP BY`, late arrival/out-of-order policies, and output schema.

### 10.3. Azure Functions Event Processing

Azure Functions can use an **Event Hubs trigger** to process messages from IoT Hub's built-in Event Hubs-compatible endpoint or a custom Event Hubs endpoint under supported configurations.

Suitable when:
- You need Python/C#/JavaScript/Java code per hosting plan.
- You need complex validation/enrichment.
- You need to call APIs or write to an operational store.
- You want Azure ecosystem bindings/integrations.

Must consider:
- Batch size, concurrency, scale-out, and checkpoints.
- Timeouts, retries, and poison messages.
- End-to-end idempotency.
- Networking to databases/Key Vault/Storage.
- Service identity and least privilege.
- Costs during sudden event volume spikes.

### 10.4. A Stateful Alert Processing Pattern

A naive threshold:

~~~text
if temperatureC > 90:
    send_alert()
~~~

can generate 60 alerts/minute if a device sends every second. A better design:

~~~text
Per device:
  Aggregate over 5-minute event-time window
  Alert if average temperature > 90 AND 20 valid samples
  Suppress repeated alerts for agreed cooldown
  Include severity, device, site, window, source events
  Persist alert state with idempotency key
  Track acknowledgement and incident closure
~~~

**Alerts are business actions with side effects.** When a stream processor retries, avoid sending redundant alerts; controlled retries, alert IDs, and deduplication at the sink are essential.

### 10.5. Azure Data Explorer and Time-Series Analysis

**Azure Data Explorer (ADX)** is suitable when querying large volumes of telemetry events, time ranges, aggregations, anomalies, and interactive dashboards per supported capabilities.

An architecture can ingest from IoT Hub or Event Hubs via a supported data connection/ingestion pipeline, then use KQL for time-based queries.

This is an **operational analytics/time-series store**; it does not replace cold backups by default and is not necessarily an OLTP database for all transactional requirements.

## 11. Cold Path: Historical Storage and Analytics

### 11.1. Raw Archive on Blob Storage / ADLS Gen2

The **cold path** stores raw or near-raw telemetry for:

- Reconciliation and replay when transformations change.
- Historical data for machine learning.
- Operational audits and incident investigation.
- Weekly/monthly/annual aggregations.
- Retrieval by site/device/date.
- Data science and predictive maintenance.

~~~mermaid
flowchart LR
    H["IoT Hub storage route"] --> B["Blob / ADLS Gen2 raw"]
    B --> L["Bronze"]
    L --> S["Silver clean & dedup"]
    S --> G["Gold features / aggregates"]
    G --> D["Databricks / BI / ML"]
~~~

When routing IoT Hub to Blob Storage, inspect output format, batching, file naming, authentication, retention, and how downstream reads it. **Do not assume every message becomes a single JSON file named `eventId`**, because the service can batch messages into files per routing/capture rules.

### 11.2. Partitioning Data by Time and Source

An example pipeline-managed layout:

~~~text
raw/
  source=iothub/
    site=factory-hcm/
      year=2026/
        month=11/
          day=20/
            hour=08/
              batch-0001.json
~~~

If IoT Hub routing outputs files in a specific layout/format, an ETL job can convert them into the desired analytics layout. Do not assume storage routing supports arbitrary custom path templates identical to the illustrative structure above.

When designing the layout, consider:
- Number of files/objects.
- Data residency and PII.
- Retention/lifecycle management.
- Compression and Parquet/Delta conversion.
- Late data/backfill and overwrite policy.
- Permissions across tenants/sites.
- Storage transaction costs.

### 11.3. Medallion for IoT

| Layer | Data | Function |
|---|---|---|
| Bronze | Raw telemetry, auth metadata, and ingestion time | Preserve source, support replay |
| Silver | Typed, standardized units, deduplicated, quality flags | Clean, flexible data |
| Gold | 5-minute averages, energy KPIs, failure indicators | Reporting/ML/business actions |

For example, Silver detects a temperature of 1000°C exceeding physical limits and marks it invalid rather than including it in averages; Gold built on accurate Silver has far less noise.

### 11.4. Do Not Rely Solely on the Hot Consumer for Archiving

If you only save to ADLS after an Azure Function processes events and the function fails, you may lose raw telemetry once the endpoint retention expires.

A better design usually:

- Routes raw directly to storage/cold path, or uses an independent durable capture pipeline.
- Lets the hot consumer handle alerts.
- Performs reconciliation: accepted/routed message count vs. ingested output count.
- Monitors endpoint health and consumer lag.
- Supports replay from the raw archive.

Still, if the archive route fails while devices continue sending successfully, alerts/recovery procedures are needed. Do not treat "a route exists" as proof that data is safely stored.

### 11.5. Retention by Data Classification

- Environmental/device data: based on analytics needs and cost.
- Worker location data: carries privacy risk; restrict access and retention.
- Audit data: may have mandatory retention requirements.
- Logs/alerts: sometimes require different retention periods than telemetry.
- Raw data: should have a lifecycle policy to move storage tiers or delete upon policy expiration.

Storage lifecycle and data governance are not defined solely by IoT Hub endpoint retention settings.

## 12. Edge Processing During Disconnection

### 12.1. Why Does Edge Matter?

A remote site only has connectivity for 20 minutes each hour. If firmware simply sends and discards on connection failure, losing 2/3 of telemetry can skew reports and miss incidents.

Edge/store-and-forward solution:

~~~mermaid
flowchart LR
    S["Sensors"] --> G["Edge gateway"]
    G --> F["Local durable buffer"]
    G --> A["Local rule / alert if required"]
    F --> R["Retry with backoff"]
    R --> H["Azure IoT Hub"]
    H --> P["Cloud processing"]
~~~

The design must clarify whether, on gateway power loss, the buffer resides in RAM or durable storage, and whether it has checksums, flush/fsync, and capacity limits.

### 12.2. What Is an Edge Gateway?

A gateway can:
- Translate OPC UA/Modbus/serial or other industrial protocols into the target message contract.
- Batch multiple sensors together.
- Filter noise, compute local averages, reduce bandwidth.
- Cache data prior to upload.
- Distribute configuration and monitor sensor health.
- Synchronize time or record clock quality.
- Run local AI inference/rules on site.

One gateway may represent many downstream devices. If per-sensor identity traceability is important, do not drop `deviceId`/`sourceId` during batching; design secure **device identity/child-device mapping**.

### 12.3. Store-and-Forward and Ordering

A buffered record might store:

~~~json
{
  "eventId": "evt-3f9a",
  "deviceId": "motor-042",
  "bootId": "boot-19",
  "sequence": 1835,
  "eventTimeUtc": "2026-11-20T08:30:00Z",
  "localStoredAtUtc": "2026-11-20T08:30:02Z",
  "retryCount": 0,
  "payload": {
    "temperatureC": 78.4
  }
}
~~~

When connectivity returns, the gateway uploads the backlog but must:
- Preserve `eventId`, original timestamp, and `sequence`.
- Distinguish measurement time from cloud receipt time.
- Apply backoff/jitter; do not flush the entire backlog at once and cause throttling.
- Maintain checksums and data integrity.
- Delete local items only after ACK status per policy; ACK is not end-to-end processing.
- Enforce storage quotas and an oldest-first/priority-based eviction policy.

### 12.4. Edge Filtering and Information Loss

Filtering data at the edge reduces costs and latency, but can lose detail needed for investigation.

For example:
- Sending 1-minute temperature averages reduces messages.
- But a 2-second spike to 120°C could be smoothed out by the average.

A good strategy:
- Send periodic aggregates.
- Send exception/anomaly events when thresholds trigger.
- Store raw locally for a short window if needed.
- Support on-demand raw upload after an incident.
- Validate false positives/false negatives.

## 13. Delivery Semantics, Duplicates, and Idempotency

### 13.1. Do Not Assume End-to-End Exactly-Once

A device may send an event, IoT Hub accepts it, but the device misses the ACK due to a network drop at that moment. The device retries the same event. The consumer may see **two copies**.

This creates the scenario:

~~~text
Device sends event-123
  → Hub accepts
  → ACK lost
Device retries event-123
  → Hub accepts again
Consumer receives two records
~~~

A proper pipeline must anticipate **at-least-once delivery or replays** across stages, depending on protocol/endpoint/SDK. Idempotency must be designed in the consumer and sink.

### 13.2. Constructing an Idempotency Key

Example:

~~~text
idempotencyKey =
  deviceId + bootId + sequence
~~~

Or a stable firmware-generated `eventId` ensuring uniqueness within a defined scope. It is insufficient if `sequence` resets to 0 after reboot without a `bootId`; you must also handle misprovisioned device IDs or `eventId` reuse caused by firmware bugs.

### 13.3. Deduplication in the Stream Processor

A consumer can:

1. Parse the message and validate schema.
2. Obtain system identity; do not trust the body alone.
3. Compute `idempotencyKey`.
4. Check/record the key using **atomic uniqueness or conditional operations** in an appropriate store.
5. Emit the business side effect only once per key.
6. Commit the checkpoint after processing according to supported transaction semantics.
7. Retry safely on timeout.
8. Route poison events to quarantine and notify the owner.

Doing "SELECT to see if key exists" and then INSERT **is unsafe when two consumers process concurrently** if the store lacks a constraint/compare-and-set.

### 13.4. Ordering by Partition and Device

Event streams typically provide ordering guarantees **within a single partition/source sequence**, not a global order across thousands of devices. When using the IoT Hub Event Hubs-compatible endpoint or custom Event Hubs:

- Determine which partition device messages are distributed to.
- Do not assume two devices in different partitions have a global order.
- Use `sequence`/`eventTime` to handle late/out-of-order events.
- Do not share a single consumer group across systems needing independent progress.

If business logic requires strict per-device ordering, verify partition mapping, keys, and concurrency characteristics of the source/consumer. Stateful processing keyed by `deviceId` may be required.

### 13.5. Poison Messages and Dead-Letter Workflows

A malformed JSON message can cause a consumer to fail repeatedly. Do not let an entire partition stall indefinitely over one record:

- Validate schema/types/content size.
- Save bad records to a secure **quarantine** if policy allows.
- Log source metadata, reason, offset/time, and correlation ID.
- Commit checkpoints according to an explicit strategy.
- Have an operator/worker reprocess data after fixes.
- Do not write raw PII/secrets into exception logs.

**IoT Hub's built-in endpoint does not automatically provide all dead-letter semantics like a Service Bus queue.** If a DLQ is needed, design it in the processor/sink or use a service that supports it.

### 13.6. Data Loss and Reconciliation

One verification approach:

~~~text
Device-generated events
    ↓
IoT Hub accepted/routed telemetry metrics
    ↓
Endpoint consumer received/processed count
    ↓
Raw storage persisted count
    ↓
Silver validated count + quarantined count
    ↓
Gold aggregation count
~~~

These counts do not always match minute-for-minute due to retention, delays, duplicates, batching, and filtering. Reconcile by **eventId, window, route, schema, and latency budget**, not merely raw totals.

## 14. Event Time, Arrival Time, and Late Data

### 14.1. Three Timestamps

| Timestamp | Meaning | Provided By |
|---|---|---|
| eventTimeUtc | Time the sensor actually measured | Device or gateway |
| ingestion/arrival time | Time IoT Hub/endpoint received it | Cloud service metadata |
| processingTimeUtc | Time the consumer processed it | Hot/cold processor |

An event measured at 08:00 might be sent at 09:00 if the gateway was offline. If analytics uses only cloud arrival time, overheating may appear to have occurred at 09:00 even though the real incident happened at 08:00.

### 14.2. Clock Skew

Many IoT devices:
- Lack stable NTP synchronization.
- Boot with a default date/time.
- Lack a reliable RTC.
- Drift after power outages.
- Use local timezone without sending an offset.

Solutions:
- Authenticated time sync when feasible.
- Send UTC ISO 8601 and `deviceClockStatus`.
- Record cloud arrival time independently.
- Validate `eventTime` falls within an acceptable range.
- Handle clock drift with quality flags/quarantine.
- Do not trust an `eventTime` far in the future to bypass monitoring.

### 14.3. Late-Arrival Policy

For hot processing:

~~~text
Window size: 5 minutes
Allowed lateness: 15 minutes
Operational alert: target a few minutes
Late events > 15 minutes: can go to replay/reconciliation
~~~

This is an example. Do not use a 15-minute watermark if edge buffers can hold 8 hours of data and the business expects complete historical reports.

One approach:
- Hot alerts use timely data with explicit late-event handling.
- Cold path preserves `eventTime` and re-analyzes when backlogs arrive.
- Gold reports have a reprocessing/backfill policy.
- Track late-data ratio and delay distribution metrics.

### 14.4. Alerts and Stale Data

If an overheating event from 08:00 arrives at 11:00, firing an urgent "currently overheating" alert at 11:00 may make no sense. Yet the event remains important for incident reporting.

Distinguish between:
- **Current safety alert:** based on fresh data, with TTL freshness.
- **Historical incident event:** still stored for investigation.
- **Maintenance alert:** can aggregate late-arriving data.
- **Business notification:** has cooldown, idempotency, and suppression rules.

Do not let a long backlog automatically trigger thousands of late alerts that overwhelm operations.


## 15. End-to-End Security for IoT Architecture

### 15.1. Threat Model

IoT often faces risks distinct from typical web applications:

- Physical theft of devices exposing credentials.
- Modified or vulnerable firmware.
- Compromised gateway injecting fake data.
- Attackers replaying the same message multiple times.
- Measurements tampered with or lost in transit.
- IoT Hub policy keys leaked in repositories.
- Overly broad network routes, unnecessary open inbound ports.
- Users with archive access viewing location/PII data.
- Cloud operators misconfiguring routes, leaking or dropping data.
- Floods/bursts throttling the hub or consumers.

Security must be layered across: **identity, device, connectivity, routing, processing, storage, monitoring, and human access**.

### 15.2. Device Identity vs. Cloud Service Identity

| Role | Typical Mechanism | Scope |
|---|---|---|
| Physical device | Per-device SAS or X.509 per IoT Hub support | D2C/device-scoped connection |
| DPS enrollment | Supported X.509, symmetric key, or hardware attestation | Provisioning and hub assignment |
| Backend/cloud operator | Microsoft Entra ID, Azure RBAC, and IoT Hub data-plane roles | Registry/service operations management |
| Stream processor | Managed identity or controlled secret per endpoint | Read events, write downstream |
| Storage archive writer | Appropriate managed identity/RBAC if integration supports | Write Blob/ADLS |
| BI/analyst | Entra identity and data store permissions | Query authorized data |

**Never place an IoT Hub owner/service policy connection string on a device.** Device credentials should be scoped strictly to that device. Management-plane Azure RBAC, IoT Hub data-plane permissions, and storage RBAC have different scopes; test each identity.

### 15.3. TLS and Certificate Validation

Connections require:
- TLS supported by the SDK/protocol.
- Server hostname/certificate chain validation.
- Never disabling certificate validation to work around clock/DNS issues.
- Firmware holding a trust store and a CA update mechanism when needed.
- Clocks accurate enough for token/certificate validity.
- Policies deprecating weak/legacy ciphers and protocols.
- Testing rotation of device, hub, and CA certificates.

A device with a wrong clock year may fail TLS or SAS token validation even while the Hub is healthy. Check time and the CA bundle before deleting a device identity.

### 15.4. Public, Private, and Hybrid Networking

A solution may require Azure Private Link/Private Endpoint for IoT Hub or supported data services. However, this comes with conditions:

- Devices outside the VNet **cannot connect** if public access is blocked without a private route.
- Factories may need VPN/ExpressRoute, gateways, or network routing to the Private Endpoint.
- Device Provisioning Service and identity/attestation services have separate connectivity requirements.
- Private DNS and firewalls must be tested from where devices/gateways actually run.
- Stream processors/Functions may have different VNet integration models depending on hosting plan.
- IoT Hub, Event Hubs, Storage, and ADX/Databricks have distinct networking configurations.

Do not copy an Azure SQL Database Private Endpoint configuration to IoT Hub and assume every hostname, port, and security behavior works identically.

### 15.5. Least Privilege and Key Rotation

Process:
1. Issue an individual identity per device or designed device group.
2. Never grant hub-level owner keys to firmware.
3. Store private keys in secure hardware/stores when possible.
4. Plan rotation before credentials expire.
5. Maintain capability to disable/revoke a compromised device.
6. Restrict backend/service permissions by function.
7. Audit changes to registry, policies, routing, and networking.
8. Manage secrets in Key Vault when identity federation cannot be used.
9. Test device recovery procedures when rotation fails.

Replacing a device key can immediately disconnect the device if firmware has not received the new key yet. Use staged rotation and test reconnection.

### 15.6. Data Privacy and Data Residency

A GPS coordinate may be technical telemetry, yet when linked to an individual, it becomes sensitive personal location data. You must:

- Collect for a specific purpose with legal basis/consent under applicable law.
- Reduce granularity when exact location is unnecessary.
- Bring PII into the hot path only when necessary.
- Separate tenant/site access.
- Define retention across IoT Hub endpoints, Storage, ADX, logs, and backups.
- Enforce permissions on Blob/ADLS/ADX/BI and audit queries.
- Verify cross-region replication and storage regions.
- Design deletion workflows for data erasure requests.

**Deleting an event from an analytics table does not automatically delete every copy in raw archives, checkpoints, backups, and logs.**

## 16. Capacity Planning and Data Estimation

### 16.1. Starting from Four Numbers

To size IoT ingestion, gather:

1. **N:** expected number of devices at each stage.
2. **F:** messages per device per second/minute/hour.
3. **S:** average and p95/p99 payload size.
4. **B:** burst factor and backlog upload when edge reconnects.

Then add retention, replication, consumer count, routes, compute, HA/DR, and growth.

### 16.2. Basic Volume Formulas

~~~text
Messages per day =
    numberOfDevices × messagesPerDevicePerDay

Approx raw data per day =
    messagesPerDay × payloadBytes

Average messages per second =
    messagesPerDay ÷ 86,400

Peak messages per second =
    averagePerSecond × burstFactor
~~~

This is initial sizing, **not the official Azure IoT Hub billing formula**. IoT Hub message metering has tier-dependent granularity/operation counting; beyond payload, there is protocol overhead, routes, storage, retries, and metadata.

### 16.3. Example: 15,000 Sensors Sending Every Minute

~~~text
Devices: 15,000
Sampling: 1 message per minute per device
Payload: 1.2 KB (decimal approximation)
Burst factor: 5×

Daily messages:
    15,000 × 60 × 24 = 21,600,000 messages/day

Average:
    21,600,000 ÷ 86,400 = 250 messages/second

Peak design estimate:
    250 × 5 = 1,250 messages/second

Approx raw payload:
    21,600,000 × 1,200 bytes
    = 25,920,000,000 bytes ≈ 25.92 GB/day

30-day raw payload:
    ≈ 777.6 GB (before storage/file/replica overhead)
~~~

**Note:** if IoT Hub meters in fixed message-size increments rather than exact payload bytes, billable messages may differ from 21.6 million. This figure also excludes retries, message headers, retention, file metadata, indexes, checkpoints, or geo-replication.

### 16.4. Peak Traffic from Reconnects

Suppose 3,000 devices go offline for 2 hours and then upload their backlog simultaneously:

~~~text
Backlog per device:
  120 samples (1/minute × 120 minutes)

Total backlog:
  3,000 × 120 = 360,000 messages

If all are sent within 60 seconds:
  6,000 extra messages/second
~~~

Even though the normal average is only 250 messages/second, a reconnect storm can exceed capacity. Therefore, you need:
- Jitter on reconnect.
- Rate limiting at the edge.
- Backpressure.
- Buffers with TTL/storage limits.
- Backlog age alerts.
- Properly sized hub units/scale and multiple hubs if needed.

### 16.5. One Hub or Multiple Hubs?

A single IoT Hub may suffice if device count, throughput, quotas, region, and features fit. Multiple hubs may be needed when:

- The fleet exceeds limits/quotas or needs horizontal scaling.
- Regions/data residency separation is required.
- Separating dev/test/prod environments.
- Factories require separate security/tenant isolation.
- Different operational policies are required.

When using multi-hub, you need:
- Clear DPS assignment policies.
- Device-to-hub mapping.
- Aggregated monitoring.
- Routing/consumer discovery.
- Ability to move hubs/regions during an incident.
- Preventing the same device from sending data to two hubs and causing duplicates.

Multiple hubs **do not automatically guarantee active-active geo-failover**; the failover plan must define identity re-provisioning, duplicate handling, and data reconciliation.

## 17. Cost: IoT Hub Is Only Part of It

### 17.1. TCO Components

~~~text
IoT system monthly cost =
    IoT Hub tier/units and billable operations
  + DPS operations/enrollments when applicable
  + Event Hubs throughput/retention if separate namespace
  + Functions/Stream Analytics/ADX compute and ingestion
  + Blob/ADLS storage, requests and data retention
  + Databricks/Synapse/Fabric analytics workloads
  + Network/Private Link/VPN/ExpressRoute/egress
  + Azure Monitor/Log Analytics ingestion and retention
  + Key Vault/security/audit services
  + Edge hardware, LTE, power, maintenance and operations
~~~

Services have different billing models. Do not use a single price-per-million-messages figure to budget the entire pipeline.

### 17.2. Optimization Levers

- Send only useful telemetry, without empty/meaningless repetitive payloads.
- Batch readings reasonably without violating message size or alert latency.
- Intentional edge filtering/sampling.
- Compact event contracts and binary compression when genuinely needed, with parser support.
- Use cold storage lifecycle policies for historical data.
- Avoid keeping every event in expensive operational DBs if not queried.
- Stop analytics compute that does not need to run continuously.
- Use stream windows/aggregates instead of saving every intermediate output to Cosmos DB.
- Minimize duplicate routes and redundant writes.
- Set budgets/cost tags and measure cost per million valid events.
- Manage log retention/sampling while preserving mandatory audits.

Reducing sampling too aggressively can miss brief temperature spikes that damage machinery. Optimization must be grounded in **detection accuracy and safety requirements**, not cost alone.

### 17.3. Cost Metrics to Track

- Cost per active device/month.
- Cost per million accepted messages.
- Cost per million **valid** messages after quarantine.
- Storage bytes per device/day.
- Egress per site.
- Hot path cost per generated alert.
- Retry/duplicate rate and associated cost.
- Growth forecast by sensor volume.
- Cost of backups, disaster recovery, and logs.

**Do not use accepted messages as the sole denominator** if 30% of messages fail schema validation or are duplicates; cost per valid event can rise even if IoT Hub pricing is unchanged.

## 18. Hands-On Lab: IoT Hub and Simulated Device

### 18.1. Objectives and Boundaries

This lab demonstrates:
- Reading subscription/IoT Hub context.
- Creating a device identity for a simulated device.
- Sending a D2C message with event ID/timestamp/schema.
- Verifying receipt at IoT Hub/event consumer.
- Distinguishing service acceptance from downstream success.

No physical hardware is needed, and nothing runs in production. Commands creating resources **may incur charges**; use only an approved subscription/resource group.

Example parameters:

~~~text
Subscription: <SUBSCRIPTION_ID>
Resource group: rg-iot-lab
IoT Hub: iothub-factory-lab-<unique-suffix>
Device identity: motor-042
Event payload: small JSON telemetry
~~~

The Azure IoT Hub name must meet service naming rules and uniqueness. Replace placeholders with real names; do not run literally.

### 18.2. Checking Azure CLI and Subscription

In Azure Cloud Shell or a Bash terminal with Azure CLI:

~~~bash
az account show --output table
az account set --subscription "<SUBSCRIPTION_ID>"

az group show \
  --name rg-iot-lab \
  --query "{name:name,location:location}" \
  --output json
~~~

If the resource group does not exist yet, create it only with approval and in the right region/policy. Do not create a different resource group just because you lack access to the assigned group.

### 18.3. Creating a Lab IoT Hub When Authorized

Example:

~~~bash
az iot hub create \
  --resource-group rg-iot-lab \
  --name "<IOT_HUB_UNIQUE_NAME>" \
  --sku S1
~~~

The example uses the S1 SKU for illustration; pricing/quota/SKU compatibility and resource creation permissions must be checked per region/subscription before running.

Inspect configuration:

~~~bash
az iot hub show \
  --resource-group rg-iot-lab \
  --name "<IOT_HUB_UNIQUE_NAME>" \
  --query "{name:name,location:location,sku:sku}" \
  --output json
~~~

Do not recreate a hub if it already has active routes, a device registry, data, or consumers.

### 18.4. Extension for IoT Device Operations

Some device identity/telemetry commands require the **Azure IoT extension** compatible with your Azure CLI version:

~~~bash
az extension add --name azure-iot
az iot hub device-identity create --help
~~~

If the extension is already installed, check version/updates per policy rather than installing ad hoc on a production build agent. Extension commands are illustrative and are not executed in this assignment.

### 18.5. Creating a Device Identity

~~~bash
az iot hub device-identity create \
  --hub-name "<IOT_HUB_UNIQUE_NAME>" \
  --device-id "motor-042"
~~~

Verify:

~~~bash
az iot hub device-identity show \
  --hub-name "<IOT_HUB_UNIQUE_NAME>" \
  --device-id "motor-042"
~~~

A device identity is a registry record, **not proof that a real physical device has connected**. In a lab, you can use a service-issued device symmetric key/connection string, but never print or commit secrets.

### 18.6. Creating Lab Credentials Without Exposing Secrets

For a lab requiring a symmetric-key connection string, retrieve it through an approved secure mechanism, store it in an environment variable or session secret store, and never paste it verbatim into chat/source control:

~~~text
IOTHUB_DEVICE_CONNECTION_STRING =
    HostName=<hub-hostname>;
    DeviceId=motor-042;
    SharedAccessKey=<DEVICE_KEY>
~~~

This is only an illustrative structure, not a real secret. When using PowerShell/Bash, avoid commands that leave credentials in terminal history, logs, or job artifacts.

**Production:** use DPS and X.509/better-managed device keys where feasible. Never use a hub-level service connection string as a device connection string.

### 18.7. Python SDK: Sending Simulated Telemetry

Example Python 3 application using a compatible **azure-iot-device** SDK. Install the package in an approved dev environment and supply the `IOTHUB_DEVICE_CONNECTION_STRING` environment variable securely:

~~~python
import json
import os
import uuid
from datetime import datetime, timezone

from azure.iot.device import IoTHubDeviceClient, Message

device_connection_string = os.environ[
    "IOTHUB_DEVICE_CONNECTION_STRING"
]

client = IoTHubDeviceClient.create_from_connection_string(
    device_connection_string
)

telemetry = {
    "schemaVersion": "1.0",
    "eventId": str(uuid.uuid4()),
    "deviceId": "motor-042",
    "bootId": "boot-lab-01",
    "sequence": 1,
    "eventTimeUtc": datetime.now(timezone.utc).isoformat(),
    "measurements": {
        "temperatureC": 78.4,
        "vibrationMmS": 4.8,
        "currentA": 3.2
    },
    "quality": {
        "sensorStatus": "ok"
    }
}

message = Message(json.dumps(telemetry))
message.content_type = "application/json"
message.content_encoding = "utf-8"
message.message_id = telemetry["eventId"]
message.custom_properties["messageType"] = "telemetry"

try:
    client.connect()
    client.send_message(message)
    print("Telemetry sent to IoT Hub successfully at the SDK level.")
finally:
    client.shutdown()
~~~

This output only shows the device client was accepted by the service upon successful connection. It **does not prove that an endpoint route, Function, ADLS archive, or dashboard was updated**.

### 18.8. An Azure CLI Option for Sending D2C in Lab

When the IoT extension supports the command and the device identity exists, you can use:

~~~bash
az iot device send-d2c-message \
  --hub-name "<IOT_HUB_UNIQUE_NAME>" \
  --device-id "motor-042" \
  --data '{"schemaVersion":"1.0","eventId":"evt-lab-01","temperatureC":78.4}'
~~~

This is a one-shot send example for smoke testing. Check help and shell quoting formats; do not use production devices or send PII in test messages. For JSON-body-based routing, ensure content type/encoding match supported SDK/CLI flags.

### 18.9. Verifying the Receiving Side

A verification test can use:
- The Azure IoT extension's monitor events tool in a lab environment when supported.
- An Event Hubs-compatible consumer pointing to the IoT Hub built-in endpoint.
- An Azure Function or Stream Analytics configured with the right endpoint/consumer group.
- A custom route to storage with proper permissions.
- Azure Monitor metrics and logs.

Example lab monitoring command:

~~~bash
az iot hub monitor-events \
  --hub-name "<IOT_HUB_UNIQUE_NAME>" \
  --device-id "motor-042"
~~~

The monitor command is typically long-running; exit using the terminal interrupt once observed sufficiently. If custom routes are configured, verify **whether the built-in endpoint actually receives messages**. Do not jump to the conclusion that the device isn't sending just because the built-in monitor is empty when a route sends data to another endpoint.

### 18.10. Controlled Cleanup

- Stop the sensor simulator/monitor.
- Review actual resources and billing.
- Verify the IoT Hub/device identity is strictly for lab use.
- Retain required logs/test evidence.
- Delete lab resources only with owner approval.
- Never run a delete command against an IoT Hub shared with real devices.

**The lab is complete with evidence:** device identity exists, message sent, consumer/endpoint read the event, schema/deviceId/time verified, and results logged. A terminal printing "sent" alone is not enough.

## 19. Designing the Hot Path Processor

### 19.1. Pseudocode for Processing a Telemetry Event

~~~python
def process_telemetry(event, authenticated_device_id):
    payload = parse_json(event.body)

    validate_schema_version(payload["schemaVersion"])
    validate_measurement_units(payload["measurements"])

    if payload["deviceId"] != authenticated_device_id:
        quarantine(event, reason="device identity mismatch")
        return

    key = build_event_key(
        authenticated_device_id,
        payload["bootId"],
        payload["sequence"]
    )

    if not atomic_claim_event(key):
        return  # Duplicated/replayed event

    try:
        persist_telemetry_idempotently(payload, key)
        evaluate_business_window(payload, key)
    except Exception:
        mark_event_for_safe_retry(key)
        raise
~~~

This is **architectural pseudocode**, not directly runnable code: `parse_json`, `atomic_claim_event`, persistence, and retry semantics must be implemented. In practice, if claiming the event key succeeds but the downstream write fails, a naive retry might be treated as a duplicate and **skipped permanently**. Use a pending/committed state machine, transactional outbox, same-store atomic transaction, or reconciliation to avoid this trap.

### 19.2. End-to-End Idempotency

A pipeline has three steps:
1. Write operational data.
2. Update device state.
3. Emit an alert.

There is no atomic transaction across three independent services unless specifically designed. You can:
- Write the event and processing status to a durable store first.
- Use an outbox to emit downstream messages.
- Deduplicate alerts based on a stable `alertId`.
- Retry each step in a controlled manner.
- Track timeouts and partial successes.
- Run a reconciliation job for pending records.

**Idempotency is not just `if duplicate then return`**; it must also account for failures after the key has been claimed.

### 19.3. Handling Malicious or Malformed Payloads

Devices may send:
- Unparseable JSON.
- Oversized fields.
- Invalid timestamp formats.
- Implausibly negative temperature readings.
- Payload strings containing unauthorized personal data.
- Script/SQL injection payloads inside string fields.

Enforce limits on:
- Message size per IoT Hub tier and parser.
- Schema types and numeric ranges.
- JSON depth and max string length.
- Resource/time limits during parsing.
- Quarantine retention.
- Never logging full payloads.
- Never interpolating untrusted data into SQL or query DSLs.

### 19.4. One Consumer or Multiple Consumer Groups?

If hot alerts and historical enrichment read the same event stream, separate consumer groups on a supported endpoint allow each group to track independent progress.

However:
- Too many consumers/partitions have limits.
- Consumer groups do not infinitely scale read throughput.
- One consumer group sharing load across instances has its own checkpoint ownership semantics.
- Changing groups/checkpoints can trigger replays.
- Different consumers can differ in processing latency.

Do not share checkpoint storage/prefixes between two applications with different goals without verifying SDK/runtime requirements.



## 20. Monitoring, Observability, and SLOs

### 20.1. Observe More Than "Is the Hub Up?"

An IoT system can have a healthy IoT Hub while the consumer fails; or a Function succeeds while dropping 40% of events due to invalid schemas. Therefore, you need metric layers:

| Layer | Signal | Meaning |
|---|---|---|
| Device | Online/offline, reconnects, battery, boot count | Connection quality and device health |
| Device buffer | Queued events, oldest age, drops, disk usage | Risk of data loss before reaching cloud |
| IoT Hub | Ingress accepted/rejected, throttling, active connections | Ingestion layer capacity |
| Routes/endpoints | Routed messages, route failures, endpoint health | Are events reaching destinations |
| Stream consumers | Partition lag, offsets/checkpoints, retries | Is the hot path keeping up with send rate |
| Processing | Parse errors, invalid schema, duplicate rates | Input data quality |
| Operational sink | Write latency, 429/5xx, failure rate | Can state/alerts be persisted |
| Cold storage | Raw files persisted, age of last batch, storage failures | Is the archive complete/timely |
| Analytics | Silver quality, freshness, Gold lag | Are reports trustworthy |
| Security | Failed authentication, key changes, suspicious traffic | Potential attack indicators |
| Cost | IoT Hub usage, endpoint/compute/storage/log cost | Within budget or not |

Specific metric names and diagnostic categories vary by IoT Hub tier and service. Consult the Azure Monitor metrics catalog for actual resources rather than assuming metrics named "TTL" or "Consumer Lag" always exist on IoT Hub.

### 20.2. Example SLIs and SLOs

A system might define:

~~~text
Telemetry freshness SLI:
  Fraction of valid events processed within 2 minutes
  after arrival at IoT Hub.

Target SLO:
  >= 99.5% over a rolling 30-day window.

Archive completeness SLI:
  Fraction of accepted events recoverable in cold archive
  after allowing batching and agreed delay.

Critical device connectivity SLI:
  Fraction of priority devices connected or storing
  data safely in a verified edge buffer.
~~~

The 99.5% figure is an **illustrative target**, not an automatic Azure IoT Hub SLA. Define the denominator clearly: accepted, valid, device-generated, or archived messages. If 10% of devices stop sending due to dead batteries, measuring only on accepted messages will not reflect overall system reliability.

### 20.3. Correlation IDs and Tracing

An event should have:
- `eventId` or `deviceId` + `bootId` + `sequence`.
- Authenticated hub/device identity from metadata.
- Event time and arrival/processing timestamps.
- Route/consumer group/partition context when provided by the API.
- Ingestion batch ID.
- Processing status and error reason.
- Cold storage object/table reference.
- `AlertId` if the event contributed to generating an alert.

Not every system automatically gets distributed tracing across MQTT, IoT Hub, Event Hubs, and Storage. Dedicated **application correlation fields** and log aggregation may be required.

### 20.4. Alerts Must Have Owners

| Alert | Example Meaning | Action |
|---|---|---|
| High device offline rate | Network outage or site-wide firmware bug | Analyze by site/firmware/provider |
| Gateway buffer near full | Imminent data loss | Reduce sampling, fix network, expand storage |
| IoT Hub throttling | Ingress quota/burst exceeded | Backoff, sizing, scale units if appropriate |
| Rising routing errors | Endpoint credential/network/route failure | Inspect target and route config |
| High consumer lag | Slow or stopped processor | Scale/optimize per partitions/quota |
| Rising schema rejects | Incompatible firmware rollout | Quarantine and roll back firmware |
| Delayed archive freshness | Storage route/batch/permissions failure | Inspect raw path and endpoint health |
| Rising duplicate rate | Reconnect storm or retry bug | Check device SDK and network |
| Alert delivery failure | Downstream API/Logic Apps error | Retry/outbox, escalation |
| Unusual cost spike | Increased sampling or duplicate routes | Inspect per-device usage and cost |
| Unusual auth failures | Expired tokens or leaked credentials | Revoke/rotate and security review |

Every alert needs a priority level, owner, runbook, and escalation path, not just sending to a shared mailbox and ignoring it.

### 20.5. Illustrative KQL from Application Telemetry Logs

If an Azure Function sends custom logs to Application Insights/Log Analytics with appropriate tables and fields, errors can be summarized over time:

~~~kusto
AppTraces
| where TimeGenerated > ago(1h)
| where Message has "telemetry-validation"
| summarize Events=count() by bin(TimeGenerated, 5m), SeverityLevel
| order by TimeGenerated asc
~~~

This KQL is illustrative; actual tables/columns and log messages depend on workspace-based Application Insights, SDK, and logging pipeline. An empty query does not prove the system has no errors if logs are not being collected.

### 20.6. Data Quality SLOs

Recommended metrics to track:
- Rate of schema-valid payloads.
- Rate of missing `deviceId`/`eventTime`/`sequence`.
- Rate of clock skew exceeding threshold.
- Rate of out-of-range measurements.
- Duplicate rate.
- Late-arriving event rate.
- Rate of missing expected sample counts by device/site.
- Rate of quarantined records reprocessed.
- Ratio of archive vs. analytics outputs that reconcile.

Do not report the entire system as "healthy" simply because HTTP/MQTT connections succeed while data quality is broken.

## 21. High Availability and Disaster Recovery

### 21.1. Distinguishing HA, Buffering, and DR

| Mechanism | Solves | Does Not Automatically Solve |
|---|---|---|
| IoT Hub service availability | Platform outages within SLA/tier | Device disconnections from LTE or regional outages |
| Device/edge durable buffer | Temporary network outages | Unlimited data when disk fills or fails |
| Retry/backoff | Transient failures | Long-term broken data policies/credentials |
| Multi-hub/region design | Certain hub/region-level outages | Automatic global failover if not built |
| Raw cold archive | Replays/re-transformations | Instantaneous ingestion guarantees |
| Consumer checkpoints | Resuming stream processing | Full protection against data loss past retention |
| Data backup/replication | Data recovery per policy | Zero-lag sync across all services |

### 21.2. RPO and RTO Targets

- **RPO (Recovery Point Objective):** maximum tolerable data loss during an incident.
- **RTO (Recovery Time Objective):** target time to restore service flow.

Example:

~~~text
Critical alarms:
  Processing RTO target: < 15 minutes
  Acceptable data loss target: as low as feasible,
  with durable buffering and reconciliation.

Historical telemetry:
  RTO target: < 24 hours
  Restore/backfill from device/edge/archive logs.
~~~

These are project-defined targets, not service SLAs. For production lines with immediate physical safety requirements, **local safety control loops must operate independently of the cloud** when connectivity drops.

### 21.3. Strategy for a Region Outage

A serious plan must clarify:

1. Which devices can buffer when the cloud is unavailable?
2. Does DPS have enrollment/assignment to a secondary hub as designed?
3. How does each device know how to reconnect when the primary hub fails?
4. Are device identities/credentials and twin state available in the recovery location?
5. Are hot/cold routes deployed in the secondary?
6. How are Storage/ADX/consumer checkpoints recovered?
7. Does alerting have an edge fallback?
8. How are duplicate events avoided when sources send backlog both before and after failover?
9. Who approves failover and rollback?
10. When can failback occur without losing data?

A second IoT Hub **does not automatically replicate the entire device registry, state, and routes of the first hub** in every design. Replicating or recreating configuration requires IaC, a provisioning strategy, and real testing.

### 21.4. Protecting Data Before Endpoint Retention Expires

Event Hubs-compatible endpoints and stream subscriptions have finite data retention windows. If a consumer is stopped longer than supported retention, it cannot replay expired data from the endpoint. Therefore:
- Have an independent raw archive or edge buffer as required.
- Monitor consumer lag and oldest event age.
- Alert before lag approaches retention.
- Account for consumer recovery time.
- Have a backfill plan from storage if stream data has expired.
- Control duplicates and ordering when backfills overlap with real-time data.

Do not pick "default retention" just because the lab is small; production retention must align with RTO, RPO, and replay strategy.

### 21.5. Chaos/Recovery Tests

Before production, rehearse:

- Disconnecting internet for 10 simulated devices.
- Powering off a gateway while buffering.
- Rotating credentials and testing reconnect.
- Blocking network access to custom Event Hubs/Storage endpoints.
- Stopping a consumer longer than the sampling interval.
- Injecting a poison message.
- Simulating a backlog/reconnect storm.
- Changing schema version while the pipeline is running.
- Testing hub/region failover if supported by the design.
- Checking missing/duplicate event counts and alert states after recovery.

Results must record evidence, UTC timestamps, message counts, and root causes—not just "test done."

## 22. Case Study: Factory Motor Monitoring System

### 22.1. Requirements

An enterprise has:
- 12 sites, each with several hundred to several thousand sensors.
- 15,000 total devices projected after one year.
- Temperature/vibration telemetry every minute; critical equipment may send faster.
- Unstable factory networks.
- Need to detect overheating within minutes.
- Predictive maintenance analytics over 12 months of data.
- Operational access control by site and organization.
- Policy prohibiting raw telemetry with PII outside authorized scope.
- Budgets/cloud costs tracked per factory.

### 22.2. Proposed Logical Design

~~~mermaid
flowchart TD
    D["15k sensors"] --> E["Site edge gateways + durable buffers"]
    E --> H["Azure IoT Hub / hubs"]
    DPS["DPS + device identities"] --> H
    H --> R["Routes"]
    R --> EV["Hot Event Hubs-compatible / custom stream"]
    R --> BL["Raw archive Blob / ADLS Gen2"]
    EV --> SA["Stream Analytics / Azure Functions"]
    SA --> OP["Operational metrics / Azure Data Explorer"]
    SA --> AL["Alert service + incident workflow"]
    BL --> DA["Databricks Silver/Gold analytics"]
    DA --> BI["Maintenance dashboards / ML"]
    H --> MO["Azure Monitor / security logs"]
    SA --> MO
    DA --> MO
~~~

**Note:** single hub vs. multiple hubs is a decision based on S1/S2/S3 units, regions, compliance, networking, and actual quotas; the diagram does not assert 15,000 devices always require multi-hub.

### 22.3. Device Identity and Fleet Lifecycle

1. Manufacturing/onsite onboarding verifies the device.
2. DPS enrollment by group/individual per attestation.
3. Assignment to the hub matching site/region.
4. Store `deviceId`, `siteId`, `assetId`, and certificate status.
5. Enable TLS MQTT/AMQP per SDK and firewall.
6. Send `schemaVersion`/`bootId`/`sequence`/`eventId`.
7. Device twins manage sampling interval/firmware state.
8. Monitor connectivity and certificate expiry.
9. Rotate/revoke identity when replacing hardware or upon key compromise.
10. Decommission cleanly across both cloud and edge.

### 22.4. Ingestion and Processing

- **IoT Hub** accepts device-to-cloud telemetry.
- **Hot route/stream** feeds alert windows, anomaly detection, and operational metrics.
- **Cold archive** retains raw data with sufficient metadata for replay.
- **Silver** standardizes units and filters duplicates/clock errors.
- **Gold** provides statistics per device/site/day.
- **Data Explorer/BI** enables near-real-time trend viewing and historical analysis.
- **Workflows/Functions** create alert tickets with idempotency and human acknowledgement.

Critical operational alerts must have **cooldown, minimum sample count, and freshness limits**. Do not treat a single anomalous spike as proof a line must halt; machine-stop procedures require dedicated safety engineering with operational specialists.

### 22.5. Phased Rollout Plan

| Phase | Scope | Expansion Gate |
|---|---|---|
| POC | 20 simulated or real devices in lab | Schema/SDK/DPS/routing working |
| Pilot | One production line, 100–300 devices | Measure network reliability, alert latency |
| Site rollout | One factory, thousands of devices | Backpressure, consumer recovery, RBAC |
| Multi-site | Multiple factories and hubs as needed | Governance, fleet assignment, cost |
| Enterprise | Full fleet, DR, and ML | SLOs, audit, incident runbooks, scaling tests |

Do not skip a pilot on real networks and hardware just because a cloud simulator sends 100% of events.

### 22.6. Acceptance Criteria

- Each device has a unique identity; credentials are never hard-coded in repos.
- On network loss, data is buffered within defined limits.
- Retrying the same event does not create duplicate alerts.
- Cloud receives authenticated metadata and independent timestamps.
- Both hot and cold routes are verified.
- 409/429/5xx or protocol errors have appropriate retry/backoff.
- Invalid-schema telemetry is quarantined and triggers an alert.
- Overly stale data does not cause mistimed urgent alerts.
- Storage archive has site-based retention/permissions.
- Consumer restarts have checkpointing/reconciliation.
- Site-level cost attribution is in place.
- Runbooks and rehearsals exist for network/region outages.


## 23. Layered Troubleshooting

### 23.1. Symptoms, Causes, and Actions Table

| Symptom | Likely Cause | How to Check |
|---|---|---|
| Device cannot connect | DNS, TLS, port, clock, SAS/X.509 | SDK logs, system time, certificate chain |
| Authentication error | Device identity disabled, expired token/key | IoT registry, credentials, and audit |
| DPS does not assign hub | Enrollment/attestation/assignment policy | DPS registration status and device logs |
| Device sends OK, monitor empty | Built-in route/fallback/consumer group | Inspect routing config and actual endpoint |
| Custom route does not match | Wrong query property/JSON content type | Message metadata and route test |
| D2C throttled | IoT Hub tier/unit limits or burst | Ingress metrics, 429/quota feedback |
| Connected but no telemetry seen | Firmware not sending or wrong message type | Device logs, packet send callbacks |
| Route to Storage fails | Credential/RBAC, path, target firewall | Endpoint health and diagnostic logs |
| Consumer lagging | CPU, slow downstream, partitions, retries | Processing latency and checkpoint ages |
| Duplicate alerts | Duplicate/replay, retry side effect | `eventId`/`alertId`, idempotency store |
| Alerts not arriving | Output side-effect fail, suppression policy | Outbox, downstream logs, and SLA |
| Wrong timestamps | Device clock skew or timezone | Compare `eventTime` vs. cloud arrival |
| Reports missing old data | Late events, retention, pipeline filtering | Raw archive and backfill policies |
| Abnormal 0 temperature | Invalid sensor, null-to-zero default | Schema/quality flags/quarantine |
| Data exceeds message size | Oversized payload, unreasonable batch | SDK errors, service limit |
| Hub healthy but Gold delayed | Analytics job failure or cold backlog | Databricks/ADX pipeline monitoring |
| Gateway disk full | Offline too long, retry too slow | Local queue oldest age, disk alarms |
| Unusually high cost | Excessive sampling, duplicates, extra routes | Per-device usage and cost breakdown |
| Devices offline after blocking public access | Missing private route/DNS to hub | Test from actual site network |
| Too many logs contain PII | Uncontrolled payload logging | Redaction, retention, role review |
| Devices lost on region switch | Unprepared identity/provisioning mapping | DPS re-provision and failover runbook |

### 23.2. Runbook: Device Cannot Connect to IoT Hub

1. Check power and physical network of device/gateway.
2. Read SDK logs with UTC timestamps; avoid logging secrets.
3. Verify DNS lookup of endpoint and network route to the right hub.
4. Check outbound TLS port/proxy/firewall.
5. Check device clock, SAS validity, or X.509 certificate chain.
6. Check device identity enabled state, hub name/deviceId.
7. If using DPS, verify enrollment and assigned hub.
8. Check IoT Hub public/private network restrictions.
9. Test connecting from another lab device on the same network to isolate.
10. Do not mass-rotate/delete identities before identifying root cause.

### 23.3. Runbook: Device Sends Successfully but Storage Has No Data

1. Identify send timestamp and device ID.
2. Check IoT Hub accepted/ingress metrics.
3. Inspect active routes, source, query, custom endpoints, and fallback.
4. Verify JSON-based routes have proper content type/encoding.
5. Check endpoint diagnostics/health and authorization.
6. Read the exact path/object layout and batching interval in Blob/ADLS.
7. Compare raw object creation time with `eventTime`.
8. Verify whether SDK/consumer connects to built-in or custom stream.
9. If messages expired past retention, check edge buffer/replay source.
10. Send a new smoke-test event with a unique `eventId` and verify end-to-end.

### 23.4. Runbook: Alert Storm After Network Recovery

1. Inspect device backlog, oldest `eventTime`, and connection recovery time.
2. Evaluate `eventTime` vs. `processingTime`.
3. Check cooldown/freshness filters.
4. Separate historical incidents from current safety alerts.
5. Use idempotency keys to prevent re-emission.
6. Throttle replay rate to avoid overloading the processor.
7. Investigate false alerts and record evidence.
8. Do not delete raw events to silence alerts; tune rules in a controlled way.

### 23.5. Runbook: Rising 429/Throttling

1. Identify the error source: IoT Hub, Event Hubs, Function, operational DB, or Storage.
2. Analyze average/peak and reconnect/backlog bursts.
3. Check tier, units, quotas, and per-operation limits.
4. Check whether devices retry with backoff/jitter.
5. Stagger fleet sends or throttle edge upload rates.
6. Scale the right infrastructure layer if SKU supports and is approved.
7. Monitor impact on dropped messages, queue age, and alerts.
8. Verify capacity after adjustment via load testing.

## 24. Controlled Deployment Process

### 24.1. Phase A: Define Requirements

Document clearly:
- Current device count and 1–3 year projection.
- Average and burst sampling rates.
- Payload size, retention, schema versions.
- Device network/protocol/hardware/OS.
- Online/offline ratio, buffer capacity.
- Alert latency targets, RPO/RTO.
- Data ownership, PII, jurisdiction.
- Hot/cold consumers and business analytics.
- Budget, monitoring, and on-call requirements.

Do not size solely by "how many devices" without messages/device/second, payload size, and backlog.

### 24.2. Phase B: Provision Resources

Via IaC/approval:
1. Resource group, region, tagging, budgets.
2. IoT Hub tier/units with verified quotas.
3. DPS and enrollment model if the fleet requires it.
4. Device registry/identity policy.
5. Storage/Event Hubs/Stream Analytics/Functions/ADX as needed.
6. Message routes and fallback with tests.
7. Managed identities/RBAC/Key Vault.
8. Private networking and site connectivity if applicable.
9. Diagnostic settings and log retention.
10. Backup, DR, and replay policies.

Do not create every resource without a clear purpose. A small problem might only need IoT Hub + Storage + one consumer.

### 24.3. Phase C: Application/Device Testing

- Firmware sends `schemaVersion`, UTC `eventTime`, stable `eventId`.
- Payload `deviceId` is cross-checked against system identity.
- Raw archive can be read/replayed.
- Hot processing meets latency SLO.
- Duplicate retries do not emit duplicate alerts.
- Invalid data lands in quarantine rather than disappearing silently.
- Network failure/recovery exercises buffer logic.
- Device credentials and rotation are tested.
- Dashboards distinguish current vs. historical data.
- Alert delivery has an owner and acknowledgement.

### 24.4. Phase D: Phased Rollout

~~~text
Lab simulator → 20 devices
              → 100 devices one site
              → 1,000 devices multiple gateways
              → Multi-site production
              → Full fleet
~~~

At each step:
- Measure p95/p99 latency.
- Check peak load and quotas.
- Review cost per valid event.
- Verify security posture.
- Exercise rollback plan.
- Document lessons learned and update firmware/SDK support.

### 24.5. Infrastructure and Configuration Drift

Manage in source control:
- IaC definitions for IoT Hub, DPS, routes, and endpoints.
- Configuration per region/environment.
- Access/RBAC policies and identity lifecycle.
- Alert rules and diagnostic settings.
- Schema contracts and SDK versions.
- Runbooks, testing evidence, and cost model.

Never let operators edit production routes manually without recording them in IaC: the next deployment could overwrite a critical setting and lose telemetry.

## 25. Production Checklist

### Devices and Identity

- [ ] Each device has a clear identity/trust model.
- [ ] No hub-level owner key embedded in firmware.
- [ ] Device symmetric keys/X.509 are protected and have a rotation plan.
- [ ] DPS enrollment/assignment and fallback tested if used.
- [ ] Device clocks synchronized or carry clock-quality flags.
- [ ] Firmware SDK/protocol updated with a version policy.
- [ ] Runbook exists for device disable/decommission and key revocation.
- [ ] Edge buffer has capacity limits, durable storage, and eviction policy.

### Ingestion and Routing

- [ ] IoT Hub tier/units sized for message volume and bursts.
- [ ] Quotas, throttling, and message size limits verified.
- [ ] MQTT/AMQP/HTTPS chosen per device and network.
- [ ] TLS/certificate verification works in the real environment.
- [ ] Built-in endpoint, custom routes, and fallback verified.
- [ ] JSON-based routes have content type/encoding and query tests.
- [ ] Raw storage route/capture has health monitoring.
- [ ] All endpoints use least privilege and avoid excessive public exposure.

### Message Contract and Processing

- [ ] Payload includes `eventId`, `schemaVersion`, time, units, and quality status.
- [ ] Payload `deviceId` cross-checked against trusted identity.
- [ ] Sequence and boot ID suffice to detect duplicates.
- [ ] Consumer implements proper idempotency/retry/backoff.
- [ ] End-to-end exactly-once is not assumed unless proven.
- [ ] Poison messages are quarantined per retention policy.
- [ ] Late/out-of-order events handled per business rules.
- [ ] Hot alerts have cooldown, freshness, and suppression.
- [ ] Consumer groups/checkpoints properly separated.
- [ ] Raw replay and reconciliation exist for storage/analytics.

### Security and Governance

- [ ] Azure RBAC/data-plane roles/service identities clearly separated.
- [ ] Managed identity used where integrations support it.
- [ ] Secrets stored in Key Vault/secure store, never in logs.
- [ ] Private DNS/Private Endpoint/VPN/hybrid network tested if required.
- [ ] PII/location data has clear classification, permissions, and retention.
- [ ] Logs, backups, and regional storage meet compliance.
- [ ] Threat detection/auditing and device key revocation have owners.
- [ ] Data deletion workflow covers raw archive and downstream copies.

### Operations and Cost

- [ ] Alerts exist for offline devices, gateway buffers, and hub throttling.
- [ ] Metrics exist for route health, archive freshness, and consumer lag.
- [ ] Data quality, duplicate/late ratios, and schema drift are monitored.
- [ ] Cost budgets, tags, and cost per valid event are tracked.
- [ ] Capacity/load tests conducted with reconnect storms.
- [ ] Failover/DR design and tests align with RPO/RTO.
- [ ] Incident runbooks exist for connection/auth/route/consumer issues.
- [ ] Owners, on-call rotation, and escalation paths defined.
- [ ] CI/CD/IaC and staged rollout in place.
- [ ] Evidence collected before full-fleet expansion.

## 26. Self-Check Questions

1. **What is telemetry?** Observational data sent by a device to the cloud or a gateway.
2. **What does D2C stand for?** Device-to-cloud communication.
3. **Can device twin replace time-series storage?** No, it is primarily for state/configuration.
4. **How does IoT Hub differ from Event Hubs?** IoT Hub provides device identity/management; Event Hubs is for generic event streams.
5. **Is IoT Hub's built-in Event Hubs endpoint a standalone Event Hubs namespace?** No.
6. **What does DPS help with?** Provisioning/assigning devices to an IoT Hub via attestation/enrollment.
7. **Does DPS process continuous telemetry instead of IoT Hub?** No.
8. **What are SAS and X.509 used for?** Authenticating devices using supported mechanisms.
9. **Why avoid putting an IoT Hub owner key in firmware?** Grants overly broad permissions and risks secret exposure.
10. **When is MQTT suitable?** Long-lived connections on resource-constrained devices per SDK/protocol support.
11. **Is IoT Hub an arbitrary-topic MQTT broker?** No.
12. **When a network only allows TCP/443, what should be evaluated?** HTTPS or MQTT/AMQP over WebSockets depending on SDK capabilities.
13. **What content type/encoding matter when routing JSON?** `application/json` and `utf-8`.
14. **Does `deviceId` in JSON prove device identity?** No, system identity is required.
15. **Should `eventId` change when retrying the same sample?** No, keep it stable for deduplication.
16. **When can `sequence` reset?** On firmware/device reboot or bug; pair with `bootId`.
17. **What does temperature telemetry need besides the number?** Unit, timestamp, device/source, and quality.
18. **What is the hot path for?** Near-real-time alerts and operational processing.
19. **What is the cold path for?** Long-term archiving, replay, analytics, and ML.
20. **What does message routing solve?** Delivering messages to endpoints based on conditions.
21. **Does enabling routes guarantee the built-in endpoint still gets all messages?** No; check route/fallback settings.
22. **What is Azure Stream Analytics commonly used for?** Streaming SQL-like transformations and windows.
23. **What must be watched with Azure Functions Event Hubs triggers?** Checkpoints, retries, concurrency, and idempotency.
24. **Does Data Explorer replace a Blob raw archive?** Not by default; use according to query/retention requirements.
25. **Why is an edge buffer important?** Prevents data loss during network outages.
26. **What does retrying without backoff cause?** Throttling, battery drain, and cost bursts.
27. **Does an IoT Hub ACK prove the dashboard updated?** No.
28. **Why design for at-least-once/replay?** To handle duplicate sends or re-reads safely.
29. **What is one way to construct an idempotency key?** `deviceId` + `bootId` + `sequence`.
30. **Can a consumer just query for duplicates and then insert?** Unsafe under concurrency without an atomic constraint.
31. **Is ordering global across all devices?** No.
32. **How are poison messages handled?** Validate, quarantine, checkpoint/retry per policy.
33. **How does event time differ from arrival time?** Measurement time vs. cloud receipt time.
34. **Why is a watermark/late policy important?** To handle late data and keep state bounded.
35. **How many messages/day do 15,000 devices sending once per minute produce?** 21.6 million.
36. **Why is an average of 250 msg/s insufficient for sizing?** Bursts and reconnect backlogs.
37. **Do IoT Hub scale units automatically increase consumer capacity?** No.
38. **Does Private Endpoint automatically solve internet device connectivity?** No, private network reachability is required.
39. **Does deleting telemetry from a Gold table delete the entire raw archive?** No.
40. **What must a valid SLO specify?** Denominator, latency window, scope, measurement method, and owner.
41. **How is archive completeness checked?** Compare accepted/routed vs. persisted event IDs per window, accounting for delay/duplicates.
42. **Why shouldn't late alerts fire as current incidents?** Backlog data may no longer represent an urgent live state.
43. **Must IoT system RPO/RTO be identical for hot and cold paths?** No, it depends on business requirements.
44. **Does multi-hub automatically synchronize identities/DR?** Not by default; must be designed, provisioned, and reconciled.
45. **When can IoT Central be used?** When the platform-managed application capabilities fit business needs.
46. **When is edge processing needed?** Network loss, local latency, bandwidth reduction, or protocol conversion.
47. **Why monitor schema rejects?** Devices may connect fine while sending unusable payloads.
48. **Why is cost per valid event more reliable than cost per accepted event?** It reflects duplicates/invalids and processing efficiency.
49. **When hitting 429s, what should be identified first?** Which service/layer is throttled and the traffic burst pattern.
50. **What are the conditions for a safe IoT rollout?** Identity, routing, hot/cold, quality, monitoring, load/DR tests, budgets, and runbooks all pass.

## 27. References

Official pages to verify current service feature matrices, SDKs, limits, and configurations:

- [Azure IoT Hub documentation](https://learn.microsoft.com/azure/iot-hub/) — device identity, IoT Hub, D2C, and service management.
- [What is Azure IoT Hub?](https://learn.microsoft.com/azure/iot-hub/iot-concepts-and-iot-hub) — architecture and core concepts.
- [Device-to-cloud communication](https://learn.microsoft.com/azure/iot-hub/iot-hub-devguide-d2c-guidance) — sending telemetry, routing, and semantics.
- [IoT Hub message routing](https://learn.microsoft.com/azure/iot-hub/iot-hub-devguide-messages-d2c) — built-in endpoints, routing, and application properties.
- [Azure IoT Hub routing tutorial](https://learn.microsoft.com/azure/iot-hub/tutorial-routing) — configuring message routes and Storage.
- [Azure IoT Hub Device Provisioning Service](https://learn.microsoft.com/azure/iot-dps/) — enrollment, attestation, and hub assignment.
- [IoT Hub supported protocols](https://learn.microsoft.com/azure/iot-hub/iot-hub-devguide-protocols) — MQTT, AMQP, and HTTPS behavior.
- [Azure IoT device SDKs](https://learn.microsoft.com/azure/iot-hub/iot-hub-devguide-sdks) — choosing device SDKs.
- [Azure IoT Hub quotas and throttling](https://learn.microsoft.com/azure/iot-hub/iot-hub-devguide-quotas-throttling) — tier-based limits.
- [Azure IoT Hub pricing](https://azure.microsoft.com/pricing/details/iot-hub/) — metering/units/pricing.
- [Azure IoT Edge](https://learn.microsoft.com/azure/iot-edge/) — edge modules and edge solution design.
- [Azure IoT Operations](https://learn.microsoft.com/azure/iot-operations/) — modern IoT/edge solution per prerequisites.
- [Azure Event Hubs](https://learn.microsoft.com/azure/event-hubs/) — partitions, consumer groups, event ingestion.
- [Azure Stream Analytics](https://learn.microsoft.com/azure/stream-analytics/) — time-based event processing.
- [Azure Functions Event Hubs trigger](https://learn.microsoft.com/azure/azure-functions/functions-bindings-event-hubs-trigger) — trigger, checkpoints, and scale.
- [Azure Data Explorer](https://learn.microsoft.com/azure/data-explorer/) — KQL and analytics on telemetry.
- [Azure Blob Storage / ADLS Gen2](https://learn.microsoft.com/azure/storage/blobs/data-lake-storage-introduction) — cold storage and data lake.
- [Azure Databricks](https://learn.microsoft.com/azure/databricks/) — Bronze/Silver/Gold processing and data analytics.
- [Azure IoT Hub monitoring](https://learn.microsoft.com/azure/iot-hub/monitor-iot-hub) — Azure Monitor metrics and diagnostic logs.
- [Azure IoT Hub security](https://learn.microsoft.com/azure/iot-hub/iot-hub-security-ground-up) — device and service security.
- [Azure Cost Management](https://learn.microsoft.com/azure/cost-management-billing/costs/) — tracking cost, budgets, and tags.
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) — estimating by tier, region, and workload.

**Conclusion:** IoT telemetry ingestion architecture on Azure is not just "devices sending JSON to the cloud." **Azure IoT Hub** authenticates and ingests data from devices; **DPS** supports provisioning; **edge buffering** retains data during network outages; **routing and Event Hubs-compatible/custom endpoints** distribute to hot/cold paths; **Functions/Stream Analytics, ADLS Gen2, Data Explorer, and Databricks** process, store, and analyze per requirements. A production solution needs a telemetry contract, idempotency, late-event policy, identity and network controls, end-to-end monitoring, recovery/DR, and a cost model based on real load. Finalize the architecture only after testing devices, networks, bursts, consumer replays, late data, security, and recovery.
