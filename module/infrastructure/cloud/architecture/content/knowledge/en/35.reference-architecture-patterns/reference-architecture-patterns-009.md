# IoT Data Ingestion Combined with Edge Processing

A factory operates thousands of sensors measuring temperature, vibration, and power consumption. If every sample is streamed directly to the cloud, data transfer and storage costs can grow large, alerting depends on Internet connectivity, and the factory loses visibility when the link drops. Conversely, keeping data strictly on-site makes it hard to benchmark multiple facilities, train models on long-term history, and manage the device fleet centrally.

An **edge–cloud IoT architecture** places part of ingestion, normalization, analytics, and buffering close to devices while using the cloud for large-scale intake, long-term storage, cross-site analytics, and fleet management. This is a **reference architecture pattern**, not a rigid blueprint: designs must stem from business goals, disruption tolerance, trust zones, data characteristics, and operational constraints.

Within cloud application architecture design, this lesson progresses from requirements to networking, compute, data, and deployment choices, then evaluates them across the Well-Architected dimensions: operations, reliability, security, performance, cost, and sustainability.

## 1. Understanding Components and Responsibilities

| Component | Typical role | Things to clarify |
|---|---|---|
| **Devices/sensors** | Measure physical telemetry, report status, or receive config | Protocols, sampling rates, accuracy, power, identity |
| **Local controllers (PLC/RTU)** | Control machinery under validated safety workflows | Safety limits, real-time determinism, OT system ownership |
| **Edge gateway** | Connect devices, bridge protocols, aggregate data, authenticate, and buffer | CPU/RAM/disk capacity, connection counts, upgradability |
| **Edge processing** | Noise filtering, feature extraction, aggregation, model inference, local alerts | Target latency, correctness, resources, and offline behavior |
| **Cloud ingestion** | Ingest telemetry from many gateways over controlled channels | Identity, quotas, load handling, duplicate handling |
| **Stream processing** | Route, validate schemas, enrich, compute near-real-time metrics | Event lateness, ordering, errors, replay, and versioning |
| **Data stores** | Store time series, raw history, analytics, and reports | Retention, query patterns, hot/cold tiering, access controls |
| **Device/fleet management** | Enroll, authorize, configure, patch software, monitor health | Certificates, versions, rollouts, rollbacks, auditing |
| **Business applications** | Dashboards, alerting, predictive maintenance, capacity analytics | Users, actionable responses, success metrics |

**Edge** may be a microcontroller, industrial gateway, line-side server, or on-site cluster. Compute placement depends on continuous-operation needs and hardware constraints. **Cloud** does not imply a single vendor product: define logical functions before selecting deployment services.

### 1.1. Distinguishing Telemetry and Control

- **Telemetry (upstream data path):** sensors/gateways send measurements, status, and events for analysis.
- **Control/command (downstream control path):** management systems send configuration, diagnostics, or authorized commands down to devices.
- **Local safety control:** machine interlocks, emergency stops, and deterministic real-time loops belong strictly in safety-certified local control layers.

Never make safety control loops depend on the cloud or a remote AI model when network links and processing paths cannot satisfy safety determinism. Commands from the cloud must pass permission checks, device state validation, operating bounds, and authorized on-site governance.

## 2. Defining Requirements Before Drawing the Architecture

Designs should establish **quality attribute scenarios**: under what context, what stimulus occurs, how the system must respond, and which metrics verify it.

| Requirement area | Architectural questions | Example criteria to confirm |
|---|---|---|
| **Latency** | Where must alerts surface and how fast after sensor sampling? | Edge alerts fire within a business-defined threshold |
| **Disconnection** | How many hours/days must the site run without WAN? | Continue priority collection and backfill upon reconnection |
| **Scale** | How many devices, samples/sec, sample sizes, sites, and growth rate? | Ingestion and buffers maintain headroom |
| **Data correctness** | Are missing, duplicate, or out-of-order samples tolerable? | Critical events reconciled by ID and source sequence |
| **Security** | Which network holds devices, where live keys, who can issue commands? | Per-device identities, least privilege, full auditability |
| **Privacy** | Which data is permitted to leave the factory? | Filter or anonymize identifiers at the edge per approved policy |
| **Availability** | What happens if a gateway, power feed, or cloud region fails? | Tested RTO/RPO and graceful degradation modes |
| **Operations** | Who updates gateways across multiple sites? | Inventory, canary rollouts, observability, and rollbacks |
| **Cost** | What are bandwidth, messaging, storage, compute, and staffing costs? | TCO over time, including gateway hardware and maintenance |

SLOs/SLAs, RTO/RPO, retention windows, and safety targets must be approved by **business, OT, security, and operations owners**. Never assume "near-real-time" always means one second, or that all telemetry needs financial-transaction durability.

### 2.1. Three Questions Governing Compute Placement

1. **Must the decision still execute when the Internet is down?** If yes, the minimal decision logic and required state belong on the edge/local controller.
2. **How much data must be processed before transmission?** If raw streams are huge, use the edge to filter, aggregate, compress, or extract features while retaining conditional raw-upload capability when needed.
3. **Does the decision require cross-site coordination or long-term history?** If yes, the cloud fits fleet-wide analytics, model training, and global governance.

## 3. Reference Architecture: Data Plane and Control Plane

~~~mermaid
flowchart TB
  subgraph Site["Factory / OT network"]
    Sensors["Sensors / machinery"]
    PLC["PLC / local safety control"]
    Adapter["Gateway: protocol adapters + auth"]
    Edge["Edge: filtering, aggregation, rules / ML inference"]
    Buffer[("Durable queue / store-and-forward")]
    Local["Local dashboard / alerting"]
    Sensors --> Adapter
    Sensors --> PLC
    Adapter --> Edge
    Edge --> Local
    Edge --> Buffer
  end
  subgraph Cloud["Cloud / application network"]
    Ingest["IoT broker / ingestion endpoint"]
    Stream["Stream processing + schema validation"]
    TSDB[("Time-series / operational store")]
    Lake[("Object storage / data lake")]
    Analytics["Dashboards, reports, analytics, ML training"]
    Fleet["Registry, IAM, config, OTA orchestration"]
    Ingest --> Stream
    Stream --> TSDB
    Stream --> Lake
    TSDB --> Analytics
    Lake --> Analytics
  end
  Buffer -->|"MQTT/HTTPS over TLS, retries"| Ingest
  Fleet -.->|"Authenticated management channel, signed updates"| Adapter
  Fleet -.->|"Configuration and model versions"| Edge
~~~

This is a **logical reference architecture**. In practice, enforce explicit trust boundaries: OT network, industrial DMZ/gateway zone, Internet or private WAN, cloud ingestion tier, processing tier, and storage tier. Never connect a PLC directly to an Internet endpoint merely because a diagram draws a telemetry arrow.

### 3.1. Data Plane: Path of Data

**Step 1 — Collection:** gateways poll or subscribe to devices via suitable adapters. For OT gear, adapters read only whitelisted tags and apply rate limits so PLCs are never overloaded. Sensitive data may need filtering right at collection.

**Step 2 — Normalization:** standardize units, attach device identity, measurement timestamps, schema version, and quality flags. Preserve critical raw readings or store references to originals when audits require them.

**Step 3 — Edge compute:** evaluate thresholds, denoise, compute windowed aggregates, detect anomalies, run inference models, or trigger local alerts. Isolate high-priority alerts from background statistics streams.

**Step 4 — Durable buffering:** persist outbound events to a bounded local queue/log before confirming receipt at the gateway. Evict records only once delivery policies and downstream acknowledgments permit.

**Step 5 — Secure transport:** gateways initiate outbound TLS/mTLS connections to the cloud broker or HTTPS endpoint. Upon WAN recovery, pace backfill uploads so the cloud tier is not flooded.

**Step 6 — Cloud processing:** authenticate tenant/site/device, validate schemas, deduplicate, enrich with asset metadata, process events, and route to appropriate stores.

**Step 7 — Business serving:** operational dashboards read near-real-time metrics; long-term stores power failure prediction and multi-plant benchmarking; alerts integrate with acknowledgment and incident workflows.

### 3.2. Control Plane: Fleet Management

Separate management traffic from telemetry traffic to simplify permission boundaries and avoid choking business data. The control plane governs **onboarding, identities, certificates, configs, policies, app/model versions, firmware updates, staged rollouts, device revocation, and auditing**.

Safe update pipelines should include: signed releases; origin and version checks; canary rings on small cohorts; health verification; phased expansion; and tested rollback capability. For safety-related equipment, every change must follow OT governance rather than modifying control logic outside approved scopes.

## 4. Dividing Responsibilities Between Edge and Cloud

| Task | Place at the edge when… | Place in the cloud when… |
|---|---|---|
| OT protocol ingestion | Devices speak only over LAN/serial or isolated networks | Devices have secure Internet access and modern protocols |
| Filtering, aggregation | Cutting bandwidth or stripping sensitive fields before leaving site | Combining many sources uniformly or retaining raw inputs |
| Operational alerting | Must work offline with tight local latency | Requires deep history or multi-site correlation |
| ML inference | Low latency, tight bandwidth, or on-site data confidentiality needed | Models exceed edge hardware or need centralized context |
| ML training | Dedicated edge servers exist and data cannot leave site | Large datasets, elastic compute, and model governance pipelines needed |
| Short-term storage | Store-and-forward and local analytics during WAN loss | Multi-site synchronization with extended retention |
| Long-term storage, cross-site reporting | Strict rules forbid data leaving premises | Unified queries and cross-facility historical analytics |
| Safety control | Local determinism and safety certification required | Never suitable as a direct real-time safety loop |

**Example:** vibration sensors emit high-frequency samples every second. The edge computes RMS and spectral features over short windows, fires local factory alerts, streams periodic summaries to the cloud, and buffers/uploads raw waveforms only when anomalies occur for specialist diagnosis. Not all filters/aggregates preserve full fidelity: explicitly document discarded detail and re-analysis limits.

## 5. Protocols and Connectivity Layers

No single protocol is optimal across every layer:

| Protocol / connectivity | Appropriate placement | Aspects to evaluate |
|---|---|---|
| **Modbus RTU/TCP** | Gateway polling legacy industrial gear inside OT network | Native protocol lacks end-to-end auth/encryption; isolate networks and lock down adapters |
| **OPC UA** | Structured industrial machine/device integration | Information models, endpoint security, certificates, server capacity |
| **MQTT** | Gateways/devices streaming telemetry over persistent links | QoS levels, sessions, keepalives, topic/payload caps, backpressure, retain policies |
| **CoAP** | Constrained devices in suitable environments | Unstable links, DTLS/OSCORE protection, proxies/gateways |
| **HTTPS** | Batch uploads, management APIs, or request/response ingestion | Connection setup cost, retries, idempotency, payload limits |
| **Private WAN / VPN / dedicated link** | Site-to-cloud links needing strict isolation or stability | Bandwidth, latency, routing, failover, and cost |

For OT-network devices, **outbound gateway-initiated connections** through a controlled DMZ are generally safer than allowing the cloud to open arbitrary inbound connections to devices.

### 5.1. MQTT QoS Does Not Replace End-to-End Data Controls

- **QoS 0:** best-effort delivery; messages may be lost.
- **QoS 1:** at-least-once delivery within the MQTT link scope; redelivery can create duplicates.
- **QoS 2:** exactly-once exchange across the specific MQTT protocol hop; does **not** automatically guarantee "exactly-once processing" through adapters, queues, stream processors, and databases.

Therefore, even with MQTT QoS 1 or 2, downstream logic still requires **idempotency** and duplicate handling. A broker ACK does not mean data has been durably committed to all downstream stores. Base edge deletion policies on required durability and actual platform guarantees.

### 5.2. Network Segmentation and Permissions

Design at least three zones: **OT/devices**, **DMZ/gateways**, and **IT/cloud**. Permit only strictly necessary flows under least privilege, log denied traffic, and test backup paths. If a gateway speaks multiple protocols, allow access only to approved subnets, ports, and devices—never grant flat access across the entire plant network.

## 6. Designing IoT Data Contracts

A telemetry message should carry enough context for interpretation and reprocessing, even if it reaches the cloud late. Minimal example:

~~~json
{
  "schemaVersion": "1.0",
  "eventId": "site-a/pump-17/boot-42/seq-109813",
  "tenantId": "factory-group",
  "siteId": "site-a",
  "deviceId": "pump-17",
  "bootId": "boot-42",
  "sequence": 109813,
  "observedAt": "2026-11-18T08:15:12.340Z",
  "gatewayReceivedAt": "2026-11-18T08:15:12.370Z",
  "metric": "vibration.rms",
  "value": 2.74,
  "unit": "mm/s",
  "quality": "good",
  "processing": {
    "type": "window_aggregate",
    "windowSeconds": 10,
    "edgeAppVersion": "3.2.1"
  }
}
~~~

This is an **illustrative payload**, not a mandatory schema. Real payloads may use JSON, Protobuf, Avro, or binary encodings depending on devices and pipelines. Sensitive fields must be evaluated before transmission or storage.

Decisions to specify in the data contract:

- **Identity:** over what scope is `tenant/site/device` unique; how are devices enrolled and revoked?
- **Event time vs. processing time:** device measurement time differs from gateway receipt and cloud processing; which timestamp drives windowing?
- **Event identification:** unique `eventId`, per-device `sequence`, and `bootId` help detect duplicates and gaps. Avoid ID collisions if counters reset.
- **Units and quality:** Celsius or Fahrenheit; how are faulty, out-of-range, or uncalibrated readings represented?
- **Schema evolution:** are field additions/changes compatible with un-updated gateways and older consumers?
- **Retention/lineage:** how long are raw, aggregate, and alert records kept; can analytical metrics trace back to raw sources?

### 6.1. Duplicates, Out-of-Order Delivery, and Late Records

IoT systems lean toward **at-least-once delivery** across flaky links; plan for:

1. Gateway retransmitting after missing an ACK, causing duplicate arrivals.
2. Sequence 102 reaching the cloud before sequence 101.
3. Device clock drift producing skewed timestamps.
4. WAN recovery flushing hours of buffered telemetry in a burst.
5. Staged schema rollouts leaving two payload versions active simultaneously.

Mitigations include deduplication keys on `tenantId/deviceId/eventId`; idempotent sink writes; **event-time windows** with deliberate lateness/watermark bounds; persisting quality flags; clock sync via NTP/PTP as required; and correction/backfill paths for late records. Critical alarms need dedicated rules and must never be silently dropped just because a statistical window closed.

One way to express target sink writes:

~~~text
onTelemetry(message):
    validateIdentityAndSchema(message)
    if alreadyProcessed(message.eventId):
        acknowledgeWithoutApplyingAgain()
        return
    applyIdempotently(message)        # upsert/transaction or equivalent
    markProcessed(message.eventId)    # consistency-aligned with apply step
    acknowledgeAccordingToDurabilityPolicy()
~~~

If `applyIdempotently` and `markProcessed` run separately without transactional binding or recovery logic, a gap remains for duplicate or lost effects. Never mistake this pseudocode for an automatic exactly-once guarantee.

## 7. Designing Store-and-Forward for Disconnections

**Store-and-forward** retains critical events at the edge when the cloud is unreachable and backfills once connectivity returns. To work reliably, include at least:

- Durable local queues/logs on suitable storage media with per-data-class size caps.
- Priority tiers: safety/fault alerts, incident states, periodic telemetry, raw samples; define which classes may downsample or drop.
- Self-throttling: bounded queues, backpressure to producers where feasible, compression/batching, and overflow eviction policies.
- Retries with exponential backoff and jitter to avoid post-outage reconnect storms.
- Checkpoints/offsets and ACK tracking to resume cleanly from unconfirmed data.
- Backlog monitoring by **record count, bytes, and oldest record age**, not connection status alone.

### 7.1. Buffer Sizing Problem

Suppose a gateway ingests **100 sensors × 1 sample/sec × 300 bytes/sample**. Payload alone:

\[
D_{\text{day}} = 100 \times 1 \times 300 \times 86\,400
= 2\,592\,000\,000\ \text{bytes} \approx 2.59\ \text{GB/day}.
\]

To buffer **72 hours** without WAN, raw payloads require roughly **7.78 GB**. Actual storage must add metadata, queue indexes, write amplification, retransmission overhead, filesystem overhead, headroom, drain throughput, and flash wear budgets. The illustrative figure is not a recommendation to buy an 8 GB drive.

If the gateway buffers 72 hours and connectivity returns, link bandwidth merely matching live ingestion means **the backlog will never drain**. Available catch-up bandwidth must exceed new arrival rates; for example, sending useful payloads at double the ingestion rate still takes roughly 72 additional hours to drain 72 hours of backlog, excluding protocol overhead and cloud throttling.

When storage fills up, policy must be explicit: retain safety/alert events longest; downsample raw streams; shed non-essential feeds; and surface a **data loss/degraded** status rather than silently reporting healthy.

### 7.2. Edge Resilience

Disruptions extend beyond WAN loss: gateways lose power, disks fail, apps crash, or sensors emit garbage. For every failure mode, define: whether local safety controls stay intact; which data is lost; whether reboots resume cleanly and backfill; whether standby hardware exists; and how to tell a silent gateway apart from an idle machine.

For high-availability sites, evaluate redundant gateways and leader/fencing mechanisms so two gateways do not simultaneously issue commands or emit uncontrolled duplicate streams. **Edge HA** is not automatically solved by running two containers.

## 8. Bandwidth Sizing and Selecting What Goes to the Cloud

Suppose a factory has **2,000 sensors**, each emitting **1 record/sec** with a **250-byte payload**:

\[
2\,000 \times 1 \times 250 \times 86\,400
= 43.2\ \text{GB/day}
\]

Sending only **one per-minute summary per sensor**, assuming the summary stays 250 bytes, drops periodic statistical traffic to:

\[
2\,000 \times \frac{1}{60} \times 250 \times 86\,400
= 0.72\ \text{GB/day}.
\]

This trims periodic telemetry payload by roughly **98.3%** in this hypothetical setup. That is **not** a 98.3% total cloud cost reduction: packet/protocol overhead, extra event/alert traffic, anomaly-triggered raw uploads, analytics storage, compute, fleet management, and gateway hardware/maintenance still apply.

Information quality considerations:

- Per-minute mean/median hides vibration spikes or brief safety breaches; retain **min/max, count, percentiles, quality, anomaly flags**, or conditional raw bursts.
- For post-incident root-cause analysis, maintain pre/post-event ring buffers and selective upload policies.
- If audits or regulations mandate full raw retention, never unilaterally drop samples to save fees.
- Heavily compressed/aggregated data may be less useful for model retraining; align retention policies with each tier's value.

### 8.1. Separating Data Paths by Urgency

| Stream | Characteristics | Processing priority |
|---|---|---|
| Safety/equipment alerts | Low volume, low latency, zero-loss within agreed targets | Highest; local response independent of cloud |
| Operational status | Periodic, powers dashboards | Medium; late arrivals allowed if tagged |
| Per-minute aggregates | Moderate volume, key for reporting | Batchable and backfillable |
| Raw waveforms / images / video | High volume, uploaded on demand or trigger | Rate limits, compression, dedicated retention/policies |
| Diagnostic logs | Maintenance use, may hold sensitive context | Sampling, redaction, access control |

This allows deliberate **cost–granularity–latency trade-offs**, avoiding one-size-fits-all QoS, retention, and priority across all data.

## 9. Choosing Cloud Storage and Processing

No single database serves every query pattern well:

| Need | Common architectural choice | Notes |
|---|---|---|
| Latest device state | Key-value/state store or device shadow/twin | Distinguish desired state, reported state, and update timestamps |
| Time-based monitoring dashboards | Time-series store/OLAP built for time-indexed writes and queries | Watch label cardinality, TTLs, downsampling, indexing, and cost |
| Long-term raw archival | Object storage partitioned by tenant/site/day | Columnar formats, schema evolution, lifecycle rules, access controls |
| Streaming alerts | Stream processor + rule engine | Event time, dedup, windows, lateness, and ordering |
| Cross-plant analytics / ML | Warehouse/lakehouse, batch training | Data quality, lineage, training-set governance |
| Device & config orchestration | Audited registry/metadata store | Avoid coupling live device state paths to analytics databases |

Typically telemetry flows through **ingestion/broker → stream processing → sinks**, each with tailored retention and permissions. If brokers or stream processors bottleneck, partition by `tenant/site/device` to preserve per-key ordering while balancing load. A single chatty device can create a hot partition: design partition keys and outlier throttling before scaling.

### 9.1. Multi-Tenant Boundaries and Data Lifecycle Management

When serving multiple factories/customers, enforce **tenant isolation** across identities, topics, read/write grants, encryption keys, partitions, queries, and dashboards. Never grant access solely from a client-supplied `tenantId`: authenticated credentials must determine allowed tenant scope.

Define lifecycles: raw data gets its own expiry; reporting aggregates live longer; alerts and audit logs follow dedicated rules; unneeded data purges per compliance. For sensitive data, govern backups, exports, logs, and training datasets too.

## 10. Security from Device to Cloud

IoT carries a unique attack surface: devices sit in dispersed physical sites with long lifespans, aging firmware, and limited patching paths. A sound design covers **identity, transport, software supply chain, networking, and physical access**.

### 10.1. Identity and Trusted Provisioning

Minimum workflow:

1. Register each device/gateway in inventory with serial, owner, site, device type, and status.
2. Issue unique per-device identities and keys/certificates; prefer hardware-backed storage like TPM/secure elements where available.
3. Enforce mutual authentication (e.g., **mTLS**) where appropriate; never share one static secret across the entire fleet.
4. Apply least privilege across topics, APIs, commands, data, and site scopes, plus rate limits.
5. Support certificate rotation/revocation, ownership transfers, and audited device decommissioning.

**Bootstrapping** is delicate: a new device must verify it is talking to the genuine service before accepting sensitive configs or software updates. Never bake long-lived credentials into public firmware images.

### 10.2. Protecting Devices and the Update Supply Chain

Where supported, use secure boot, signed firmware/apps, integrity checks, encrypted local sensitive storage, and A/B partitions or safe rollbacks. Establish patch policies, version lifecycles, vulnerability tracking, EOL asset handling, and rules for devices offline for months.

Separate privileges among **viewing telemetry**, **changing configs**, **pushing firmware**, and **issuing control commands**. Physically impactful commands must be gated by device state, expiration windows, human approvals, and safety procedures.

### 10.3. Privacy and Integrity

Camera feeds, audio, location, operator IDs, or sensitive production metrics may require edge processing or redaction prior to upload. Govern transport and storage per applicable laws, maintaining audit trails for data exports. TLS stops eavesdropping in transit yet **does not prove a sensor measures truthfully**: data quality checks, calibration tracking, and anomaly/tamper detection remain necessary.

## 11. Bidirectional Commands and Device State

Some systems need telemetry only. When remote control is required, never lump commands into the same "best-effort" channel as sensor measurements.

A command envelope should contain:

~~~json
{
  "commandId": "cmd-20261118-0142",
  "targetDeviceId": "pump-17",
  "type": "set_sampling_rate",
  "parameters": { "intervalSeconds": 10 },
  "issuedAt": "2026-11-18T08:30:00Z",
  "expiresAt": "2026-11-18T08:35:00Z",
  "requestedBy": "maintenance-operator",
  "expectedConfigVersion": "cfg-28"
}
~~~

The device/gateway must verify sender identity, authorization, allowlisted command types, current config version, expiration, operating conditions, and `commandId` idempotency. Report **accepted → applied → verified/failed** transitions, separating "cloud sent" from "device executed." Upon reconnect, **never execute expired commands**. For hazardous actions, consider requiring local physical confirmation independent of cloud connectivity.

For digital twin/shadow state, distinguish:

- **Desired state:** target configuration from the control plane.
- **Reported state:** actual state reported back by the device with timestamp and version.
- **Observed telemetry:** live measurements/events, which may differ from configuration state.

Never treat desired state as proof that a change took effect.

## 12. Fleet Deployment, Scaling, and Operations

### 12.1. Choosing Deployment Models

| Model | Suitable when | Trade-offs |
|---|---|---|
| **Simple MCU processing** | Sensors filter/aggregate locally under tight resource budgets | Power efficient, hard to run complex pipelines |
| **One gateway per cell/line** | Many OT devices need protocol adaptation | Easy to deploy, gateway can be a single point of failure |
| **On-site edge server cluster** | Heavy video/ML, many feeds, local HA needed | Hardware cost, cluster ops, power and cooling |
| **Hybrid edge + cloud** | Local continuity plus centralized governance/analytics | Sync, networking, observability, and version complexity |
| **Cloud-centric telemetry** | Securely connected devices, light data, no offline processing needed | Simpler, dependent on WAN and transfer fees |

If running containers at the edge, assess hardware capacity, whether orchestration is truly needed, where persistent state lives, crash-recovery behavior after power loss, and artifact distribution when offline. You do not need Kubernetes on a tiny gateway; equally, avoid fragile manual scripts across thousands of devices.

### 12.2. Mandatory Operational Metrics

Monitor end-to-end across **device → gateway → network → cloud ingestion → pipeline → storage → applications**:

- **Device:** heartbeat, firmware version, battery/power, clock skew, quality flags, sample drop rate.
- **Gateway:** CPU/RAM, temperature, backlog size/age, ingress/egress rates, adapter errors, flash wear where critical.
- **Network:** WAN status, RTT, packet loss, reconnect frequency, TLS/certificate expiry, retry counts.
- **Ingestion/stream:** accepted/rejected counts, duplicate rates, partition lag, event-time lag, schema failures, dead-letter queues.
- **Data & business:** record discrepancies, dashboard/alert latency, on-time device reporting ratio, alert acknowledgment rate.
- **Deployment:** device fleet version distribution, rollout error rates, canary health, long-offline device counts.

A silent gateway might mean **machine powered down**, **power outage**, **WAN cut**, **expired certificate**, or **collector crash**. Distinguish these via multi-layer heartbeats and correlation-tagged logs; never assume all devices are healthy merely because the cloud broker is up.

### 12.3. Scalability and Multi-Site Operations

Size ingestion for peak traffic and **hundreds of gateways reconnecting simultaneously**. Enforce per-tenant quotas, rate limiting, retry jitter, priority stream isolation, and sink scaling capacity. Maintain site onboarding/offboarding workflows, group configs, standardized device tags, on-site incident runbooks, and after-hours operator support.

When using multiple cloud regions, specify which datasets replicate, latency/access impacts, and budgets; multi-region alone does not guarantee lossless ingestion. During cloud outages, edge tiers must degrade gracefully to sustain committed local duties.

## 13. Designing Failure Modes and Test Scenarios

| Simulated failure | Desired behavior | Test to run |
|---|---|---|
| WAN lost for 24–72 hours | Edge processes locally, buffers priority data, flags backlog | Physically cut WAN and audit post-reconnect data completeness |
| Gateway reboots mid-batch upload | Zero loss of committed data; duplicates absorbed | Cut power / kill process before send and right before ACK |
| Device clock off by 10 minutes | Data carries quality flags without breaking windows or alerts | Inject clock skew, late arrivals, and out-of-order streams |
| Cloud ingestion overloaded | Backoff, bounded queues, operational alerts | Load-test reconnect storms and quota enforcement |
| Bad edge app update | Devices recover or roll back cleanly | Rehearse canary rollout and rollback |
| Device certificate expired/revoked | Rejects unauthorized data/commands; controlled recovery path | Test rotation, revocation, auditing, and long-offline recovery |
| Noisy/uncalibrated sensor | Measurements are not blindly trusted | Inject out-of-range values, gaps, and duplicate samples |
| Site or cloud region outage | Local operations stay safe; cloud meets RTO/RPO | Rehearse restore/replay and verify data reconciliation |

**RTO** and **RPO** should be defined **separately for local control, telemetry, alerting, and reporting**. A reporting dashboard may tolerate hours of delay, whereas a production-line hazard alert cannot.

## 14. Well-Architected Trade-Offs

| Pillar | Inspection questions | Common trade-offs |
|---|---|---|
| **Operational Excellence** | How are versions, observability, and fleet incidents managed? | Adding fleet management increases upfront setup while cutting manual toil |
| **Reliability** | How does the edge operate and recover when cloud/WAN fails? | Local queues and gateway HA raise cost while improving continuity |
| **Security** | How are devices and links authenticated, segmented, patched, and revoked? | Private links, mTLS, and signed updates demand key, cert, and rollout ops |
| **Performance Efficiency** | Which workloads need low latency and where does compute fit? | Edge inference lowers latency yet faces tight CPU/RAM/power bounds |
| **Cost Optimization** | What is the TCO of raw vs. aggregates, bandwidth, storage, and ops? | Edge filtering cuts cloud load while adding hardware and maintenance |
| **Sustainability** | Are wasteful transfers, storage, and idle compute minimized? | Smart sampling saves resources while requiring retention of high-value signals |

**No single choice fits every workload.** Sending everything to the cloud simplifies compute management at the cost of network reliance. Pushing too much to the edge creates update, observability, and version-skew burdens. Base decisions on site measurements and business targets.

## 15. Design Example: Predictive Maintenance for Manufacturing Lines

Suppose a manufacturer operates **3 plants**, each with **2,000 vibration/temperature sensors**. For select machines, gateways ingest high-frequency samples; maintenance crews need factory-floor anomaly alerts, while operations wants 12-month cross-plant trend comparisons. Each site occasionally loses WAN for several hours.

### 15.1. Requirements Breakdown

| Requirement | Architectural consequence |
|---|---|
| Anomaly alerts must fire on-site even during WAN loss | Rule engine or ML inference at the edge; local alert channel |
| Cross-site 12-month trend analytics | Cloud store with retention, standardized metadata, and access control |
| WAN outages must not wipe all data | Durable queues, priority rules, buffer sizing, and catch-up pacing |
| Compare pre-failure raw signals | Local raw ring buffers + event-triggered uploads with traceable metadata |
| Non-programming staff at each plant | Centralized fleet/rollout management, health dashboards, on-site runbooks |
| Cloud must not directly control PLCs | Network segmentation and policies isolating telemetry from local control |

### 15.2. Design Choices

**At the factory:** industrial gateways poll via approved adapters, normalize units, extract features, and trigger local alerts; hold raw data in rolling ring buffers; write summaries/key events to durable queues; and push over authenticated HTTPS/MQTT to the cloud. Redundant gateways can protect high-availability lines.

**In the cloud:** broker/ingestion receives streams, authenticates tenant/site, writes durable event logs, runs event-time stream processing, stores time series for dashboards, and archives raw/training history in object storage. The control plane isolates inventory, OTA, and config/model versions from ingestion.

**Analytics models:** train across multi-plant history in the cloud, then—after accuracy and data-quality validation—package signed models for edge inference. Version models, run canaries, monitor drift, and keep local safety rules independent of ML outputs.

### 15.3. Key ADRs to Record

- **ADR-01 — Alerting placement:** at the edge because alerts must work during WAN loss; cloud aggregates alert status.
- **ADR-02 — Cloud data selection:** per-minute summaries plus event-triggered raw bursts; confirm sufficient detail for failure diagnostics.
- **ADR-03 — Delivery semantics:** at-least-once with `eventId`/dedup rather than assuming exactly-once transport.
- **ADR-04 — Device management:** per-device identities, mTLS, signed OTA, canary rollouts, and rollback paths.
- **ADR-05 — Infrastructure limits:** benchmark collector/gateway and cloud load before scaling across all 3 plants.

Every ADR must capture context, alternatives, rationale, consequences, assumptions, and review triggers. For instance, if regulations later demand full raw retention, ADR-02 must revise upload and retention policies.

## 16. Common Anti-Patterns

**Exposing PLCs/sensors straight to the Internet:** exposes OT assets and couples control loops to WAN stability. Fix with gateways/DMZs, controlled polling adapters, and local safety logic.

**Skipping local buffers because "the cloud is always up":** loses data on every site outage. Design sized, bounded store-and-forward queues and run disconnect tests.

**Assuming QoS 2 equals end-to-end exactly-once:** sink duplicates and dashboard drift still happen. Use `eventId`, idempotent sinks, proper transaction boundaries, and reconciliation.

**Dumping all raw data into one database:** inflates cost, strains queries, and complicates retention. Tier data by value and access patterns.

**Sharing one config or certificate across all devices:** a single compromised credential impacts the whole fleet and hinders site isolation. Use unique identities, least privilege, rotation, and revocation.

**Skipping schema and model versioning:** one OTA rollout changes payloads and breaks cloud jobs and reports. Enforce compatibility contracts, canaries, and rollout monitoring.

**Ignoring stale commands:** reconnecting gateways execute expired commands, causing unexpected state changes. Enforce TTLs, `commandId`, state checks, and execution ACKs.

**Monitoring only the cloud broker:** ingestion appears healthy while gateway backlogs overflow or sensors go silent for days. Maintain end-to-end observability from sensors to data consumers.

## 17. Architecture Exercise

A logistics company operates **500 trucks**, each reporting GPS location, vibration, and cargo temperature every 5 seconds over cellular links. In tunnels or remote areas, connectivity drops for 30–90 minutes. Out-of-range cold-chain temperatures must sound an immediate cab alert for the driver; dispatch needs fleet tracking and 6-month incident traceability.

Complete the following:

1. Diagram separate telemetry and management command paths, marking **trust boundaries** on trucks and in the cloud.
2. Select which processing lives on the truck vs. the cloud; explain why temperature alerts must not depend on Internet access.
3. Compute daily payload for **500 trucks × 1 record/5 sec × 200 bytes** and propose a single-truck buffer size for a 90-minute outage (excluding overhead).
4. Describe handling duplicates, late arrivals, and skewed device clocks.
5. List at least three failover tests and three dashboard metrics for rollout evaluation.

**Solution hints:**

- On the truck: collector + temperature rules, local audible alert, durable queue, and cellular link; in the cloud: ingestion, time-series store, historical archive, dashboards, and fleet management. Never send hazardous vehicle-control commands over the telemetry path.
- Fleet-wide daily records: \(500 \times 86\,400 / 5 = 8\,640\,000\). Fleet-wide payload: \(8\,640\,000 \times 200 = 1.728\ \text{GB/day}\) (decimal). Over 90 minutes, one truck emits \(90 \times 60 / 5 = 1\,080\) records, or roughly **216 KB of payload**. Real storage needs extra room for overhead, headroom, replays, and other data policies.
- Use `deviceId + bootId + sequence` or `eventId` to deduplicate; separate `observedAt` from cloud receipt time; alert immediately on the truck and flag late records.
- Rehearse cellular dropouts, mid-upload reboots, and full buffers; monitor backlog age, offline truck counts, cloud lag, and alert acknowledgment rates.

Never size storage strictly to 216 KB: real records may grow larger, include logs/photos, and require crash-safe persistence against abrupt power loss.

## 18. Pre-Deployment Architecture Review Checklist

- [ ] Business scenarios are quantified: latency, WAN outage tolerance, retention, RTO/RPO, and data value.
- [ ] Local safety control, telemetry, and remote commands are cleanly separated with no uncontrolled physical actuation paths.
- [ ] Device inventory, OT/DMZ/cloud zones, network flows, and component owners are documented.
- [ ] Protocols/adapters match device constraints, security, and load; sensitive devices are never exposed straight to the Internet.
- [ ] Edge design enforces CPU/RAM/storage caps, backpressure, store-and-forward, and backlog observability.
- [ ] Normal load, peak load, and reconnect storms are sized; backfill bandwidth exceeds arrival rate after outages.
- [ ] Schema/versioning, `eventId`, clock/quality flags, deduplication, and late-data policies are implemented.
- [ ] Raw/aggregate/alert tiers define clear retention, access controls, sensitive-data rules, and purposes.
- [ ] Per-device identities, mutual auth where appropriate, key/cert lifecycle, software signing, canary OTA, and rollbacks exist.
- [ ] Dashboards trace end-to-end from sensors through ingestion to sinks, alerting on data loss or silent gateways.
- [ ] Network loss, power loss, failovers, data recovery, and bad upgrades have been rehearsed under realistic conditions.
- [ ] ADRs document why each computation sits at edge vs. cloud alongside reliability, security, performance, cost, and operational trade-offs.

**Design conclusion:** a strong edge–cloud IoT system sustains essential local capabilities even when cloud or WAN links fail, transmits semantically clear and reconcilable data, and leverages the cloud for large-scale analytics and fleet governance. Clarifying responsibilities, measuring traffic, testing failure modes, and securing the device lifecycle matter far more than picking any specific cloud product name.
