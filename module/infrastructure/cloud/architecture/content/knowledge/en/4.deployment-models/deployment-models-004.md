# Edge Architecture and Workload Split Between Edge and Cloud

In **Cloud Architecture** design, not all data needs to travel to a distant data center before creating value. A warehouse scanner needs instant feedback; factory surveillance cameras can generate massive video streams; devices in poorly connected areas must keep running when the Internet link drops. **Edge architecture** moves part of the processing closer to where data is generated or actions occur, while using the cloud for aggregation, coordination, long-term storage, analytics, and centralized governance.

Within the **Deployment Models** chapter, this lesson explains how to partition functionality across **devices, edge nodes, local network zones, and the cloud**. This decision must be grounded in business requirements, latency budgets, bandwidth, offline capability, data characteristics, and risk levels. The output should be a data-flow diagram and a verifiable set of architecture decisions with explicit trade-offs across **reliability, security, scalability, cost, and operations** aligned with Well-Architected thinking.

After this lesson, you will be able to:

- Distinguish processing on-device, at the local edge, at the network edge, and in the cloud.
- Choose execution placement for each task based on latency, resource, data, and connectivity needs.
- Design data and control flows between edge and cloud, including when network connectivity drops.
- Address queuing, synchronization, conflicts, consistency, and safe actuation.
- Build a security, version rollout, observability, and distributed fleet management strategy.
- Evaluate an edge–cloud design with concrete metrics instead of relying on the slogan "move processing closer to users."

## 1. What Is Edge Computing and Where Does It Live?

**Edge computing** means placing compute, storage, or data processing capabilities near the data source or where a response is needed. "Near" can mean physical proximity, fewer network hops, or a low-latency operational domain. The edge is not necessarily a server inside a factory; it can also be a smartphone, a retail store gateway, a cluster at a telecom tower, or compute at a provider's point of presence.

| Tier | Typical Location | Capabilities and Constraints | Common Roles |
| --- | --- | --- | --- |
| **Device (on-device)** | Sensors, cameras, phones, industrial machines | Limited CPU/RAM/power; hardware-bound | Signal capture, simple checks, ultra-fast feedback |
| **Local edge** | Gateways, servers in stores, factories, stations | More resources than devices; can run on LAN | Data filtering, AI inference, offline queues, on-site coordination |
| **Network edge** | Network points of presence, near-user clusters, MEC | Low network latency possible; management depends on provider | Caching, subscriber-adjacent processing, low-latency APIs |
| **Cloud region** | Cloud provider data centers | Elastic scale, rich managed services | Central data store, heavy analytics, model training, fleet orchestration |
| **Backup/DR region** | Approved secondary region or facility | Additional cost and sync requirements | Disaster recovery, redundancy for centralized systems |

Edge and cloud **are not mutually exclusive**. The most common pattern is distributing tasks by fit: parts needing local responsiveness run at the edge; parts needing a global system view, heavy resources, or durable long-term storage run in the cloud.

### 1.1. Commonly Confused Concepts

- **Edge computing:** placing and executing processing close to data sources.
- **IoT:** connected devices, protocols, and applications; IoT may use edge computing, though it is not mandatory.
- **Fog computing:** intermediate distributed processing layers between devices and the cloud; overlaps partially with edge.
- **Content Delivery Network (CDN):** points of presence specialized in caching/delivering content; some platforms run compute at the edge, yet a CDN is not synonymous with an entire edge architecture.
- **Multi-access Edge Computing (MEC):** compute resources near access networks, often tied to telecom infrastructure.
- **Hybrid cloud:** combining on-premises infrastructure and cloud under an operating model; a hybrid system can include edge nodes, but not every hybrid system serves real-time edge processing.

A gateway that merely forwards raw packets does not necessarily solve an edge computing problem. Architectural value appears when that node holds clear processing responsibilities and operates reliably within business SLAs/SLOs.

## 2. When Should Processing Be Placed at the Edge?

Start from **measurable requirements**, not from a list of products or technologies. Six primary question areas:

1. **Latency:** what is the maximum end-to-end time from sensing an event to acting on it? Is the target average, p95, p99, or a hard bound? Must it respond even when the WAN is down?
2. **Traffic volume:** how much data is generated over time, including peak hours? Which parts require raw data versus filtering, compression, or aggregation?
3. **Availability:** when the Internet fluctuates or the cloud is unreachable, how must devices keep operating and for how long?
4. **Data residency and security:** is there personal data, manufacturing secrets, sensitive imagery, or regulatory limits on where data may travel or reside?
5. **Resources:** do devices/edge nodes have sufficient CPU, RAM, GPU/NPU, disk, power, cooling, and maintainability?
6. **Coordination scope:** does a decision need data from a single device, a single site, or the entire network?

### 2.1. Classifying Tasks by Characteristics

| Task Characteristic | Favor Edge When… | Favor Cloud When… |
| --- | --- | --- |
| Response latency | Must respond in milliseconds to tens of milliseconds; WAN varies widely | Higher response latency is acceptable; async processing works |
| Raw data volume | Large volumes where most raw data adds little value if shipped intact | Small data volumes or centralized raw data is truly required |
| Connectivity | Local operations must complete when WAN drops | Task depends on central data stores, services, or identity |
| Decision scope | Relies primarily on signals at a single site | Requires global optimization and cross-site reconciliation |
| Compute scale | Small models, near-sensor processing, viable hardware budget | Large model training, batch jobs, elastic compute needs |
| Sensitive data | Can transmit only reduced features/events | Must centralize data for approved purposes under proper controls |
| Version governance | Can package, verify, and update by device cohorts | Rapid, frequent deployments on centralized infrastructure |

These are initial heuristics, not absolute rules. A small AI model may still belong in the cloud if the device lacks memory; a global aggregation job may still pre-compute partially at the edge to shrink transfer volume.

### 2.2. Latency Must Be Measured End-to-End

A typical task passes through this chain:

~~~text
Signal capture
  -> Preprocessing
  -> Transport to processing node
  -> Queuing
  -> Business execution / inference
  -> Return result
  -> Execute action
~~~

Approximate total time:

**Total latency = capture + preprocessing + network transit + queue wait + processing + response transit + actuation.**

As an illustrative example, a production line needs a response within **50 ms**. If local steps take 8 ms capture, 4 ms LAN transit, 6 ms preprocessing, 12 ms inference, 5 ms policy check, and 10 ms actuator trigger, the sum is **45 ms** before accounting for jitter and headroom. If a cloud round trip alone exceeds this budget, placing the real-time decision step in the cloud cannot meet the requirement. Validate using p95/p99 distributions in a real environment, since averages often mask tail latency spikes.

Never assume every cloud round trip is slow or every edge node is fast. An underpowered edge box with CPU saturation or slow flash storage can perform worse than a well-tuned cloud system. Measure **end-to-end latency under normal load, peak load, and failure conditions**.

## 3. Rules for Splitting Processing Between Edge and Cloud

You can decide across three patterns: **process at the edge, process in the cloud, or split a workflow into steps across both**. For each step, define who owns authoritative state, whether data is replicated or only events are emitted, and what behavior is permitted during disconnection.

### 3.1. Reference Split Matrix

| Task | Suggested Placement | Rationale |
| --- | --- | --- |
| Sensor reading, simple noise filtering | Device/edge | High frequency, close to source |
| Emergency machine stop or safety-critical control | Dedicated local safety controller | Must be independent of WAN and non-real-time applications |
| Line-side visual inference | Edge with GPU/NPU if suitable | Cuts latency and video bandwidth |
| Filtering, deduplication, event aggregation | Edge | Avoids shipping redundant raw data |
| Reference data caching at point of sale | Edge | Reduces WAN dependency |
| Authorizing pre-approved offline actions | Edge with explicit policies and TTLs | Sustains bounded operations during outages |
| Large model training | Cloud or dedicated compute cluster | Needs aggregated data and heavy compute |
| Centralized identity management | Cloud/central | Consistent identities and policies, distributing needed copies |
| Multi-branch revenue aggregation | Cloud | Requires multi-site data |
| Long-term retention, reporting, BI | Cloud or approved data platform | Elastic storage, querying, and governance |
| Config and model version distribution | Cloud orchestrates, edge executes | Unified governance with local execution |
| Fleet-wide auditing and trend analytics | Cloud | Needs global view; edge can buffer events |

**Critical exception:** if an action impacts machine or human safety, the control loop must be engineered, certified, and deployed on appropriate safety-rated systems. Standard edge software does not automatically qualify to replace PLCs, safety controllers, or hardware safety interlocks.

### 3.2. Two Common Architectural Patterns

**Cloud governs, edge executes:** the cloud defines configurations, distributes versions, and aggregates state; the edge handles local requests. This suits thousands of stores, stations, or gateways needing uniform governance.

**Edge pre-processes, cloud analyzes deeply:** the edge extracts features, detects events, and filters data; the cloud combines multiple sources for long-term analytics. This suits high-volume video, industrial telemetry, and sensor networks.

Both patterns are frequently combined in one architecture. To avoid conflicts, explicitly separate the **data plane** and the **control/management plane**.

## 4. Reference Architecture: Data Plane and Control Plane

The diagram assumes a manufacturing site with multiple sensors/cameras, an edge cluster, and cloud services:

~~~mermaid
flowchart TB
    subgraph SITE["On-Site: Local Operational Domain"]
        S["Sensors / Cameras"] --> GW["Ingestion Gateway"]
        GW --> P["Preprocess, Filter, and Inference"]
        P --> A["Local Decision"]
        A --> ACT["Actuator / Business System"]
        P --> Q[("Durable Queue and Buffer")]
        P --> EDB[("Essential Local Data")]
        CM["Device Management Agent"] --> P
    end

    subgraph CLOUD["Cloud / Centralized Platform"]
        MQ["Event Ingestion Service"]
        STORE[("Data Lake / Event Store")]
        ANALYTICS["Analytics and Reporting"]
        REG["Config, App / Model Version Registry"]
        FLEET["Fleet Management, Observability, Audit"]
    end

    Q -- "Sync events when connected" --> MQ
    MQ --> STORE
    STORE --> ANALYTICS
    FLEET --> REG
    REG -- "Signed updates" --> CM
    CM -- "Status, versions, health" --> FLEET
~~~

In the diagram:

- **Local operational flow:** sensors → preprocessing → decision → actuation. Steps requiring offline operation must not depend on the cloud along their critical path.
- **Data flow to cloud:** selected events or data → durable buffer → ingestion platform → storage and analytics. Losing the WAN delays synchronization without necessarily halting local work.
- **Control flow from cloud:** configs, models, or app versions → authenticated distribution → edge agent → controlled application. The edge must retain a stable version if it cannot fetch new configs.

This diagram is a discussion template, not a claim that a single product provides every capability out of the box. Every arrow still requires defined protocols, schemas, permissions, retry logic, and observability.

### 4.1. Choosing Protocols Based on Semantics

| Mechanism | Best Suited For | Notes |
| --- | --- | --- |
| HTTP/HTTPS API | Request–response, device registration, config download | Avoid forcing offline-capable ops onto synchronous requests |
| MQTT or similar pub/sub | Telemetry, events, intermittently connected devices | Design QoS, sessions, auth, topics, and buffer bounds |
| AMQP, queues, or event streaming | Event streams needing ack control, retention, replay | Choose retention, partition ordering, and idempotency |
| gRPC or binary RPC | Service-to-service calls with strict contracts and compact payloads | Manage deadlines, retries, and versioning |
| OPC UA / industrial protocols | Integrating industrial equipment | Requires secure gateways, OT/IT segmentation, and legacy awareness |

Protocol is only half the story. For example, "publishing with MQTT QoS 1" does not prove the business logic processes the event exactly once. Define **completion semantics**: whether the event reached the broker, was durably persisted, was processed, or updated the business system of record.

## 5. Data Design Patterns Between Edge and Cloud

### 5.1. Filtering, Aggregation, and Inference at the Source

For example, line-monitoring cameras generate continuous streams, while operations only need **when a defect occurred, its location, confidence score, and an approved evidence clip**. The edge can:

1. Receive video streams over the LAN.
2. Preprocess frames and run the defect-detection model.
3. Emit a compact event with timestamp, device ID, defect class, and model version.
4. Retain raw footage briefly if needed for reprocessing or investigation, with strict access controls.
5. Upload selected events or clips to the cloud per retention and security policies.

The benefit is reduced bandwidth and raw data exposure. The trade-off is managing models across many nodes, detecting drift, and preserving enough audit trails to validate outputs.

### 5.2. Store-and-Forward During Network Outages

**Store-and-forward** keeps events locally until they can be shipped to the cloud. Operational sequence:

~~~mermaid
sequenceDiagram
    participant D as Device
    participant E as Edge
    participant Q as Durable Buffer
    participant C as Cloud

    D->>E: New event
    E->>Q: Durable write (eventId, sequence, payload)
    Q-->>E: Persisted
    Note over E,C: WAN disrupted
    D->>E: Subsequent events
    E->>Q: Continue writing within capacity limits
    Note over E,C: WAN restored
    loop Send unacknowledged events
        E->>C: Send rate-limited batch
        C->>C: Check idempotency, record processing
        C-->>E: Acknowledge committed processing level
        E->>Q: Mark as synchronized
    end
~~~

To implement this reliably, design **buffer durability, capacity limits, write quotas, catch-up sync rates, retries, acknowledgments, and disk-full behavior**.

- Use **eventId** or a business key so the cloud deduplicates re-sent events.
- Use a per-device or per-stream **sequence number** to detect missing, duplicate, or out-of-order events.
- Record **event time** and **ingestion time** separately; synchronize device clocks and handle clock skew.
- Persist checkpoints durably if the app must resume cleanly after an edge reboot.
- Use **exponential backoff with jitter**, rate limiting, and backlog alerts to avoid thundering herds when thousands of devices reconnect simultaneously.
- Define disk-full behavior explicitly: prioritize critical events, shed droppable telemetry, expand valid buffer storage, or raise errors. Never silently drop data committed for retention.

In distributed systems, retries typically yield **at-least-once delivery**; downstream consumers must therefore be **idempotent**. Never assume end-to-end exactly-once semantics solely because a broker advertises a delivery feature.

### 5.3. State Synchronization and Consistency

Harder than shipping telemetry is syncing data **modifiable on both sides**, such as store-level item prices versus central pricing, or order status while a store is offline.

| Data Type | Suggested Authoritative Source | Sync Strategy |
| --- | --- | --- |
| Sensor telemetry | Device/edge emitting events | Append-only, catch-up upload, deduplication |
| Rules, configs, model versions | Centralized management system | Explicit versioning; edge applies with ack |
| Balances, access rights, or strongly consistent transactions | Designated business service | Restrict offline edits; use purpose-built transaction protocols |
| On-site task outcomes | Edge execution system | Immutable events synced to cloud; business conflict resolution |
| Slowly changing reference data | Cloud publisher | Versioned caching, TTL, and invalidation mechanism |

**Key principle:** assign **one authoritative source per field or command type** whenever possible. If both edge and cloud can modify the same record, define deterministic conflict policies upfront: monotonic versions, field ownership, field-level merge, or business reconciliation workflows. Picking the latest timestamp can fail under clock skew, especially in financial transactions.

During a network partition, both sides cannot simultaneously have instant global updates while operating independently. The architecture must explicitly specify which operations allow **eventual consistency**, which must wait for authoritative confirmation, and which are locked out to prevent business errors.

### 5.4. Offline Mode Does Not Mean "Everything Keeps Running"

Classify functions by acceptable behavior during WAN loss:

| Operation Category | During WAN Loss | Examples |
| --- | --- | --- |
| **Continue fully locally** | Complete locally, sync later | Image classification, sensor readings, local device alerts |
| **Continue conditionally** | Use pre-issued rights/configs with TTL or quotas | Scanning pre-authorized goods, local maintenance checks |
| **Accept as pending only** | Queue request without declaring business completion | Config change requests needing central approval |
| **Fail safe / pause** | Reject or switch to manual fallback | Online payments needing verification, actions exceeding local authority |

Do not display "success" if the system merely queued a request for sync when the business requires cloud confirmation. UIs and APIs must surface clear states such as **processed locally, pending sync, centrally accepted, rejected**.

## 6. Capacity Planning: Bandwidth, Compute, and Storage

An edge solution pays off only when edge resources handle peak load and total lifecycle cost is acceptable.

### 6.1. Bandwidth Estimation

Illustrative example: a warehouse has **40 cameras**, each generating an average **2 Mbps** compressed stream.

- Aggregate raw bitrate: **40 × 2 = 80 Mbps**, or roughly **10 MB/sec**.
- Streamed continuously for 24 hours, volume is approximately **864 GB/day** (decimal units), before protocol overhead and bitrate bursts.
- If the edge sends only **5%** of input volume, transmitted traffic drops to roughly **43.2 GB/day**—a 95% reduction under these assumptions.

These figures are an illustrative calculation, **not a guarantee** that every analytics model achieves 95% reduction. If investigations require raw video, account for video retention policies, event clip counts, and on-demand retrieval bandwidth.

For offline buffers, basic sizing:

**Minimum capacity ≈ data rate to retain × designed outage duration.**

If forced to buffer raw video at **10 MB/sec** during a **2-hour** WAN outage, raw input alone needs roughly **72 GB**. In practice, add headroom for bitrate spikes, metadata, disk write amplification, sync backlog catch-up, and incident detection time. If retaining only filtered events, storage needs shrink dramatically. Define explicitly which data **must** be preserved.

### 6.2. Compute Capacity Estimation

When running inference at the edge, do not pick CPU/GPU specs purely from vendor peak ratings. Measure:

- Throughput, FPS, or events/sec with all cameras running concurrently.
- p95/p99 latency across the full pipeline, including preprocessing and I/O.
- RAM limits, cache footprint, disk write throughput, and LAN bandwidth.
- Thermal behavior, power draw, and clock throttling under sustained continuous operation.
- Ability to run old and new versions side by side during model updates.
- Failover headroom when one node in an edge cluster fails or during backlog catch-up.

A throughput test running a single camera does not prove a cluster handles 40 cameras concurrently. Test **peak load, bursts, and long-duration soak runs**.

### 6.3. Full Lifecycle Cost

Compare **TCO (Total Cost of Ownership)** rather than cloud bills alone:

| Cost Factor | Cloud-Heavy Processing | Edge-Heavy Processing |
| --- | --- | --- |
| WAN/egress bandwidth | Can be high if shipping raw data up | Can be reduced via local filtering and aggregation |
| Compute | Pay-as-you-go cloud resources; elastic scaling | Distributed hardware purchase/lease; fixed per-site limits |
| Storage | Easy centralized capacity expansion | Needs on-site disks, endurance checks, and replacements |
| Operations | Fewer physical hardware locations | Requires fleet management, updates, remote support, power outage handling |
| Offline availability | Dependent on connectivity if all logic sits in cloud | Can operate more independently if properly engineered |
| Security | Centralized governance, but heavier data transit | Keeps data on-site, yet increases physical endpoints to harden |
| Upgrades | Fast centralized service deployments | Must manage hardware lifecycles, compatibility, and rollbacks |

Connectivity, power, spare parts, site visits, and field support hours can outweigh compute cost differences. Edge evaluations should include **sensitivity analysis** as site count, traffic volume, and hardware failure rates vary.

## 7. Reliability and Distributed Failure Management

Edge architectures have more failure domains than centralized systems: sensors, gateways, LAN, WAN, cloud, ingestion services, disks, and power can each fail independently. Document what remains functional as each piece fails.

### 7.1. Failure Modes and Controls

| Incident | Impact | Desired Behavior / Control |
| --- | --- | --- |
| WAN outage | Cloud unreachable, backlog grows | Continue permitted local ops, durable buffering, alert, catch-up sync |
| Edge process crash | Local processing interrupted | Supervisor auto-restart, health checks, bounded retries, checkpoint resume |
| Gateway power loss | Intermediate processing lost | UPS where needed, local fallback mechanism, defined acceptable downtime |
| Edge disk full or failed | Unable to persist events, data-loss risk | Disk monitoring, retention limits, overflow protection, priority alerts |
| Cloud ingestion slowdown | Edge queues grow | Backpressure, bounded retries, prioritize critical events |
| Cloud pushes bad config | Multiple edge sites impacted at once | Canary rollouts, signature/schema validation, version pinning, rollback |
| Edge runs stale model | Prediction quality degrades | Version tracking, expiry/staleness policies governing continued operation |
| Clock drift | Out-of-order data and skewed analytics | Time synchronization, sequence numbers, separate event time vs. ingest time |

Edge reliability cannot be measured by cloud uptime alone. Measure **percentage of site tasks completed on time** and **actual data loss across component failures**.

### 7.2. RTO/RPO and Disconnection Incidents

- **RTO (Recovery Time Objective):** target time to restore functionality after a defined incident type.
- **RPO (Recovery Point Objective):** maximum tolerable data loss, expressed in time or recovery points.
- **Sync lag:** elapsed time between an edge event occurring and becoming queryable in the cloud.

These metrics do not replace each other. An edge node may keep running smoothly during a WAN outage while **sync lag** reaches several hours; if its disk dies before uploading, actual RPO can be poor even though local processing never stopped.

If targeting "zero lost events during a 4-hour WAN outage," verify the fault tolerance of the **local buffer**, not just disk size. If surviving a simultaneous disk or node failure is required, design appropriate replication or redundant writes and test overlapping faults.

## 8. Edge-to-Cloud Security

An edge node may sit in a retail store, factory floor, utility pole, or area with far less physical security than a data center. Moving processing closer to the source reduces data transit, yet creates additional **management endpoints, key storage locations, and attack surfaces**.

### 8.1. Device Identity and Authentication

Every device/gateway needs its **own unique identity**—never share one static secret across all devices. A sound model includes:

1. Initial identity provisioning through a trusted onboarding workflow.
2. Device-appropriate certificates/keys or strong auth; consider **mTLS** for mutual authentication.
3. Scope permissions by device, tenant, site, and action type: Branch A's device must never read data or receive commands for Branch B.
4. Rotate and revoke identities when replacing devices, losing hardware, or detecting compromise.
5. Maintain an inventory of hardware, firmware, agent versions, and owners.

Explicitly design for when the edge cannot reach the authorization service: which permissions remain valid offline, for how long, and when execution must halt. Non-expiring tokens simplify offline mode at the cost of severe abuse risk.

### 8.2. Software and Data Protection

- Enable trusted/secure boot and protect keys using TPM, hardware security modules, or equivalents where supported and warranted by risk.
- Distribute **apps, firmware, container images, and AI models with verified provenance/signatures**; log applied versions.
- Encrypt data in transit and at rest at the edge where appropriate; ensure key management survives network outages.
- Segment device/OT networks from corporate office networks and the Internet, allowing only required flows.
- Restrict remote admin logins; audit privileged actions using time-bound access and revocation mechanisms.
- Scrub sensitive fields before writing logs, emitting metrics, or forwarding to third parties.
- Gate cloud-to-edge commands with authentication, authorization, version checks, and local safety rules.

**Zero Trust** here means every connection and action verifies identity, authorization, and context; never assume a device is safe simply because it sits on a factory LAN.

### 8.3. Data Residency and Compliance

A decision to "keep video at the edge and only send metadata to the cloud" reduces raw data transfer, yet metadata—device IDs, locations, timestamps, cropped frames, or user IDs—can still constitute personal data.

During design, inventory:

- Where raw data, caches, snapshots, backups, logs, and sync staging reside.
- Where the cloud ingests and processes data, including observability, analytics, and support tools.
- Who has remote access and which data may leave the site or country.
- Edge retention periods and secure erasure procedures when purpose ends or devices are lost/decommissioned.
- Contracts, regulations, and residency policies applicable to each data class.

Keeping data on-site **does not automatically ensure** compliance. Obligations must be verified with legal, infosec, and data owners per system.

## 9. Managing and Updating Thousands of Edge Nodes

In the cloud, you update a centralized service; at the edge, the system must handle heterogeneous hardware, version skew, power loss, and distributed sites. Consequently, **fleet management** is a core architectural component, not a post-launch add-on.

### 9.1. Device Lifecycle

~~~mermaid
flowchart LR
    A["Device onboarding"] --> B["Provision identity and policy"]
    B --> C["Deploy apps / models"]
    C --> D["Run and report state"]
    D --> E["Monitor, alert, patch"]
    E --> F["Staged / canary upgrades"]
    F --> D
    D --> G["Revoke, wipe data, decommission"]
~~~

An edge deployment platform should support:

- **Desired state:** approved software, config, and model versions for each device group.
- **Reported state:** actual running versions and health reported by the edge; distinguish **silent/offline** devices from **failing** ones.
- **Canary rollout:** deploy first to a small percentage of sites and monitor metrics before expanding.
- **Rollback:** revert to a known-good version if the new release raises error rates, latency, or degrades accuracy.
- **Compatibility rules:** older edge versions must communicate safely with newer cloud endpoints over a defined support window.
- **Decommissioning workflow:** revoke certs/keys, wipe data, and confirm handover or disposal.

When disconnected, the edge should retain a verified **last known good configuration** within its validity window. However, do not run expired critical configs indefinitely if doing so violates safety or authorization policies.

### 9.2. Remote Observability and Debugging

The cloud needs health signals from every site without ingesting all raw data. Useful metrics:

| Category | Suggested Metrics |
| --- | --- |
| Business tasks | Events processed, success rate, end-to-end p95/p99 latency |
| Device health | CPU/GPU, RAM, temperature, disk, power, firmware version |
| Connectivity | WAN outage duration, RTT, send error rate, link quality |
| Synchronization | Backlog size, oldest event age, catch-up rate, dropped events |
| AI models | Version, inference time, drift, confidence scores, anomaly rate |
| Security | Auth failures, signature check failures, privilege changes, non-compliant devices |

While offline, the edge still needs **bounded** local log/metric retention to sync diagnostic signals once reconnected. Budget observability disk space so logs never crowd out business event buffers.

## 10. Design Example: Factory Product Defect Detection

Suppose a production line uses cameras to inspect products. The business must detect defective items fast enough to trigger a conveyor diverter; management needs shift-level defect rates and cross-factory comparisons.

### 10.1. Hypothetical Requirements

| Requirement | Illustrative Value | Architectural Implication |
| --- | --- | --- |
| Vision processing response | p99 under 100 ms under defined load | Decision pipeline runs on-site |
| WAN outage | Continue inspecting products for 4 hours | Keep cloud off the core decision path |
| Video data | Process inside factory by default; upload approved clips only | Saves bandwidth and limits data exposure |
| Central reporting | Can lag up to 30 minutes when network is healthy | Asynchronous event synchronization |
| Model updates | Version-tracked and rollback-capable | Fleet manager and model registry |
| Reject actuation | Must pass through a certified control system | Decouple AI detection from physical safety logic |

These targets are illustrative assumptions for practice, not universal factory benchmarks. Before designing, measure total time from camera capture to physical actuation, including conveyor speed and sensor placement.

### 10.2. Functional Split

**At the line:** cameras capture frames; gateway feeds frames to the inference service; defect service outputs detections; local app aligns item position and timing to signal the controller. The controller enforces its own interlocks and safety rules. Defect events receive unique IDs and are durably persisted.

**At the factory:** an edge cluster or industrial server stores events, manages queues, enforces local configs, and shows operator status. The system continues logging and acting within approved bounds during WAN outages.

**In the cloud:** a message broker ingests events; a data platform aggregates defect rates per factory; data teams evaluate models and retrain new versions on approved data; fleet management rolls out approved models by device cohort.

### 10.3. Sample Event Flow

Example application-layer event payload:

~~~json
{
  "eventId": "site-07-line-2-camera-3-0005412",
  "siteId": "site-07",
  "deviceId": "camera-3",
  "sequence": 5412,
  "eventTime": "2026-11-18T08:23:14.211Z",
  "eventType": "PRODUCT_DEFECT_DETECTED",
  "modelVersion": "vision-3.2.1",
  "confidence": 0.96,
  "productTraceId": "batch-17-item-982",
  "evidenceRef": "edge://site-07/evidence/0005412",
  "schemaVersion": 1
}
~~~

Values are illustrative. **evidenceRef** is an edge-local reference, not a URL accessible to the cloud or external users by default. Explicitly decide whether clips upload to the cloud, who approves them, who can view them, and retention limits.

### 10.4. Data Path During WAN Disruption

1. Edge continues running inference and signaling the local controller within designed bounds.
2. System writes ID-tagged events to the durable buffer; UI indicates data is pending sync.
3. Local monitoring alerts when buffer hits thresholds; priority policy preserves critical events.
4. When network recovers, events flush in batches; cloud acknowledges after persisting at the defined durability level.
5. Cloud processes idempotently, using **eventTime** for occurrence analytics and **ingestionTime** for lag tracking.
6. Operators verify backlog returns to 0, no sequence gaps exist, and reporting timeliness recovers to target.

### 10.5. Pre-Acceptance Verification Tests

- Run all cameras concurrently and measure p99 from frame capture to control signal.
- Cut WAN for a full 4 hours; verify local operation and peak backlog duration.
- Reboot the gateway mid-sync; verify zero lost events and zero duplicate business records.
- Inject duplicate and out-of-order events intentionally; verify deduplication and sequence handling.
- Roll out a new model to one line; intentionally deploy a faulty model and verify rollback.
- Simulate nearly full disk, slow cloud ingestion, and expired keys/certs to verify alerts and safe-state transitions.
- Audit event payloads, logs, clips, and remote access against approved security policies.

These are concrete system tests—never substitute a single GPU benchmark or a claim that "the broker supports retries."

## 11. Common Architectural Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Putting every decision in the cloud for deployment simplicity | Variable latency; WAN outages halt operations | Separate local critical paths from async cloud sync |
| Streaming all raw data to the cloud | Wastes bandwidth, raises latency and data risk | Filter/aggregate at source; store raw data only with clear purpose |
| Running edge nodes without fleet management | Version drift; blind to broken or unpatched devices | Build onboarding, desired/reported state, canary, and rollback |
| Assuming at-most-once or naive delivery suffices | Retries create duplicate records and skewed metrics | Use eventId, idempotency, checkpoints, and loss/dup tracking |
| Letting edge and cloud edit shared records without ownership | Conflicts on reconnect; loss of consistency | Define authoritative source and deterministic reconciliation rules |
| Treating offline mode as "just use the cache" | Expired data/permissions remain active | Classify functions into continue, conditional, queue-only, or pause |
| Failing to size buffers for WAN outage duration | Disk fills up and drops events right when needed | Size for peak rate, outage window, headroom, and priority retention |
| Unvalidated control commands from the cloud | Corrupt/spoofed commands cause physical harm | Enforce auth, authorization, bounds, and local safety interlocks |
| Monitoring only cloud uptime | Blind to line failures, backlogs, and dead devices | Measure end-to-end business SLOs and per-edge health |
| Assuming keeping data on-site equals compliance | Logs, support tools, and analytics may still leak data | Inventory all flows, storage locations, and authorized parties |

## 12. Edge–Cloud Architecture Design Process

For a new project, follow these steps:

1. **Gather requirements:** list on-site operations; define p95/p99 latency, expected WAN outage duration, data volume, and security/compliance obligations.
2. **Decompose workflows:** break into capture, filtering, inference, decision, actuation, buffering, sync, aggregation, and management.
3. **Decide placement:** assign each task to device, local edge, network edge, or cloud; specify step dependencies and resource bounds.
4. **Map data paths:** document events, permissions, storage locations, authoritative state, checkpoints, retention, and partner boundaries.
5. **Design offline behavior:** classify continue/queue/pause behaviors, buffer sizing, retries, catch-up sync, deduplication, and conflict rules.
6. **Design operations and security:** device identity, authorization, key lifecycles, signed updates, rollouts, rollbacks, auditing, and observability.
7. **Budget resources:** measure p99 latency, CPU/GPU, disk, power, WAN traffic, TCO, and headroom.
8. **Verify under realistic conditions:** benchmark peak load, cut links, reboot mid-backlog, simulate disk failures, failed updates, and intrusion tests; refine based on findings.
9. **Record decisions:** write Architecture Decision Records (ADRs) for major trade-offs and exception approvers.

### 12.1. Placement Decision Template

The YAML below is an **illustrative decision record**, not a runnable platform configuration:

~~~yaml
workload: visual_defect_detection
business_owner: manufacturing_quality
classification: confidential
critical_path:
  input: camera_frame
  output: reject_recommendation
  latency_slo_p99_ms: 100
placement:
  capture: device
  preprocess: local_edge
  inference: local_edge
  local_policy_decision: local_edge
  physical_actuation: validated_local_controller
  aggregate_analytics: cloud
network:
  offline_target_hours: 4
  cloud_on_critical_path: false
data:
  cloud_payload: approved_defect_metadata
  source_of_truth_for_observations: edge_event_log
  delivery: at_least_once
  deduplication_key: eventId
  evidence_retention: approved_schedule
operations:
  update_strategy: staged_rollout
  rollback_required: true
  fleet_health_reporting: required
verification:
  - p99_under_peak_load
  - four_hour_wan_outage
  - power_restart_with_backlog
  - duplicate_event_replay
  - failed_model_rollout
~~~

Values like **approved_schedule** are placeholders. In real use, attach the approved retention schedule, measurement method, and test results; a YAML file alone does not enforce controls.

## 13. Well-Architected Evaluation

Adding edge nodes does not automatically improve a system. Evaluate each design across five common perspectives:

| Evaluation Angle | Questions to Answer |
| --- | --- |
| **Reliability** | When WAN or cloud fails, what keeps running? Can events be lost if an edge disk fails? Are sync lag, RTO/RPO measured, and recovery drilled? |
| **Security** | How are devices given identities? Who can issue cloud commands? What data leaves the site? Are updates verified and keys revocable? |
| **Performance Efficiency** | Does the pipeline meet p95/p99 under real load? Do CPU/GPU and network retain headroom? Does the split genuinely reduce response time? |
| **Cost Optimization** | What is total cost across cloud, WAN, edge hardware, replacements, power, and ops? How does it scale as site count grows? |
| **Operational Excellence** | Can you see every device's version, health, and backlog? Can you roll out/roll back safely when some sites are offline? |

### Pre-Finalization Design Checklist

- [ ] Every processing step has an assigned placement and rationale recorded as an architecture decision.
- [ ] Real-time critical paths have no unintended dependency on cloud/WAN.
- [ ] p95/p99 latency and throughput have been tested at production-equivalent load.
- [ ] Disconnected modes, resync, duplicates/reordering, and conflicts have explicit rules.
- [ ] Buffers are sized for outage duration, data rates, and real storage limits.
- [ ] Identity, authorization, encryption, signed updates, rollback, and decommissioning are designed.
- [ ] Raw data, events, logs, replicas, and partner flows have defined locations, permissions, and retention.
- [ ] SLOs exist for on-site functionality, sync lag, and fleet health.
- [ ] Critical failure scenarios have been drilled, measured, and evidenced.

## 14. Applied Exercise

A retail chain has 150 point-of-sale stores. Each store creates transactions and caches the product catalog. Internet links can drop for 30 minutes; Finance requires chain-wide revenue reporting within 15 minutes once connectivity stabilizes. Customers must clearly know which transactions are finalized and which are pending reconciliation.

Sketch a design addressing these questions:

1. Which operations continue inside the store during WAN loss, and which must wait for an authoritative data source?
2. Where should the authoritative source sit for product catalog, inventory, transaction history, and balances? Which data is cached or locally staged?
3. How do you prevent stores from submitting duplicate transactions upon reconnect? What rule applies if prices changed while a store was offline?
4. Which metrics confirm stores are healthy, no transactions are lost, and financial reporting stays within SLA?
5. Compare cost and reliability between cloud-only processing and placing a gateway in every store.

There is no single answer for every retail chain. What matters is demonstrating consistency across **business rules, data ownership, offline states, and verification criteria**.

Edge architecture delivers value when the boundary between **local processing** and **centralized processing** is cleanly engineered. The edge brings fast response, lower bandwidth consumption, and continuity during network outages; the cloud brings aggregation, governance, and elastic scale. Architectural quality lies in explaining why each task sits on its tier, how data moves and synchronizes, and whether the system proves its performance, security, cost, and operational commitments.
