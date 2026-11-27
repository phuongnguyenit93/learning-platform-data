# Operating during disconnection and resynchronizing state

Hybrid and edge systems often must continue serving branch offices, factories, retail stores, vehicles, or remote locations even when connectivity back to the cloud is disrupted. If an application only works when it can reach central services, a single WAN outage can halt all edge operations. Conversely, allowing offline data writes without synchronization rules can cause duplicate records, overwrite newer data, or corrupt business state once connectivity returns.

The design must answer two questions: **what the edge is allowed to continue doing while disconnected**, and **how local changes merge back with central state upon reconnection**. Not all data needs immediate synchronization, and not every operation is safe to run independently. You must classify operations, define authoritative data sources, persist changes durably, transmit data in a controlled manner, and resolve conflicts according to business semantics.

This lesson covers offline operating modes, store-and-forward models, synchronization protocols, handling duplicate and out-of-order events, conflict resolution strategies, security, operational observability, and post-outage recovery procedures.

## 1. Goals and scope of disconnected operation

Disconnected operation is the ability of a system to continue executing a defined set of functions when unable to reach one or more external services. Causes may include:
- Internet or WAN connectivity loss.
- VPN/private link failure.
- Unreachable cloud region or control plane.
- DNS, routing, firewall, or gateway failures.
- Intermittent links, high latency, or packet loss.
- Edge nodes isolated by design for network protection.
- Mobile devices or vehicles moving through dead zones.

The goal is not to maintain every feature identically to online mode. The goal is to sustain approved operations, protect data, and recover consistently once connectivity returns.

### Design questions

1. Which functions must operate offline?
2. Which actions are permitted only with confirmation from the cloud?
3. What data is stored locally and for how long?
4. What types of data is the edge allowed to create or modify?
5. When two locations edit the same object, who decides?
6. What is the maximum outage duration the edge must have storage capacity for?
7. Upon reconnect, which data needs to sync first?
8. How do we know sync is complete and the new state can be trusted?
9. What happens if the edge loses power or suffers disk failure while offline?
10. How do we revoke access for a device that has been disconnected for a long time?

### Distinguishing offline from degraded mode

- **Offline:** no usable communication path to a dependency or central system.
- **Degraded mode:** partial connectivity or services remain, but capabilities are constrained—for instance, read-only cache access or high-priority-only transmission.
- **Partitioned mode:** a subset of nodes still communicate internally while isolated from the rest of the system.
- **Recovery/synchronizing:** connectivity has returned, yet the backlog has not fully drained.

Never flip status from offline to healthy just because a ping succeeds. The system may reach the endpoint while still failing authentication, failing to ship payloads, or holding an unprocessed backlog.

## 2. Defining edge autonomy levels

Each workload requires a predefined autonomy level.

| Level | Behavior during disconnection | Examples |
|---|---|---|
| Read-only cache | Reads cached data, accepts no writes | Catalog or reference lookup |
| Local write queue | Writes requests to a durable queue for later processing | Telemetry shipping, orders awaiting confirmation |
| Local processing | Processes business logic locally within permitted bounds | Local calculation, classification, local control |
| Autonomous operation | Sustains stateful workflows with local policies | Production line requiring on-site control |
| Fail-closed | Rejects operations when conditions cannot be verified | Transactions exceeding limits or sensitive actions |

Avoid choosing a single level for the entire application. An edge site might continue displaying dashboards, accepting local commands, and collecting telemetry while pausing permission changes, high-risk payments, or security policy updates while disconnected from the control plane.

### Classification by risk level

- **Offline-capable:** local operations verifiable against synced data with deterministic merge rules.
- **Conditionally permitted:** actions executable only within pre-allocated quotas, time windows, or pre-granted permissions.
- **Online-required:** actions needing unique confirmation from the central system.
- **Fail-safe required:** if state cannot be verified, transition to a pre-engineered safe state.

For physical control systems, fail-safe behavior must be specified by domain/safety engineers for the equipment. Never assume "keep running" is always safer than "stop."

## 3. Local-first data models and authoritative sources

Local-first lets the edge record changes locally first and sync centrally later. This improves offline capability but requires unambiguous data ownership.

### Ownership models

- **Central-authoritative:** the cloud is the source of authority. The edge may cache and submit change proposals, while the cloud decides the final outcome.
- **Edge-authoritative:** the edge owns a specific data domain, such as device state at a site. The cloud receives copies or aggregates.
- **Partitioned ownership:** each edge owns a distinct set of objects or keys, reducing concurrent edits to the same item.
- **Shared ownership:** multiple nodes may edit the same data; requires explicit versioning and conflict resolution.

### Data classification

| Data type | Suggested authority | Offline behavior |
|---|---|---|
| Platform configuration | Cloud/control plane | Use verified version; do not self-modify root policies |
| Catalog cache | Published by cloud, read by edge | Allow cache reads per TTL |
| Telemetry | Generated by edge, aggregated by cloud | Buffer locally and forward later |
| Site transaction events | Edge or domain service per ownership | Persist locally, sync later |
| Shared inventory state | Central inventory domain or partitioned ownership | Cap transactions by quota/reservation |
| Sensitive control commands | Designated authority | Fail-closed without valid authorization |
| Operational logs | Generated by edge, stored centrally | Buffer, prioritize critical events |

Do not make both cloud and edge masters of the same field without arbitration rules. The simplest way to prevent conflicts is partitioning write authority by domain, tenant, site, or key.

### Replicas are not the source of truth

A cached copy may be stale yet remain useful for reads. UIs and APIs should indicate stale mode, last update timestamp, and whether writes are allowed.

## 4. Store-and-forward architecture

Store-and-forward is a standard pattern: the edge writes events or commands to durable storage, then a sync process sends them to the cloud when connected.

~~~mermaid
flowchart LR
    APP["Edge application"] --> LOCAL["Local database / durable outbox"]
    LOCAL --> SENDER["Sync agent"]
    SENDER --> LINK["WAN / private connection"]
    LINK --> INGEST["Cloud ingestion API"]
    INGEST --> INBOX["Inbox / deduplication"]
    INBOX --> DOMAIN["Domain processing"]
    DOMAIN --> ACK["Commit result / acknowledgement"]
    ACK --> SENDER
    SENDER --> LOCALACK["Mark event as synchronized"]
~~~

### Key components

- **Local database:** persists business state and metadata needed while offline.
- **Outbox/spool:** holds unsent events with sequence numbers and delivery state.
- **Sync agent:** manages connectivity, batching, retries, compression, and checkpoints.
- **Cloud ingestion endpoint:** authenticates edge identity, validates schemas, and ingests events.
- **Inbox/deduplication store:** detects already-processed events.
- **Domain processor:** applies changes to the authoritative system.
- **Acknowledgement:** confirms commit outcomes so the edge can mark events complete.

### Writing state and outbox in the same transaction

If an application writes a change to the local database and publishes an event separately, failures can occur:
- Database commits, then the process crashes before publishing.
- Event is sent, then the database transaction rolls back.
- Edge reboots and does not know which events still need sending.

The outbox pattern solves this by writing business state and the outbox record in the same local transaction. The sync agent reads the outbox and ships events asynchronously. This minimizes the risk of losing events between two separate writes.

### Outbox alone does not guarantee exactly-once

Events can be delivered multiple times if the edge misses an acknowledgement after the cloud already committed. The cloud needs idempotency/deduplication so each event applies business effects at most once. In practice, systems combine at-least-once delivery with idempotent processing.

## 5. Persisting offline data durably

An in-memory queue is insufficient for extended outages or power loss. Data must be written to durable storage with recovery support.

### What to persist

- Event ID and sequence.
- Job/task ID if the event belongs to a job.
- Entity ID or partition key.
- Schema version.
- Event type.
- Event time and local ingest time.
- Payload or payload reference.
- Retry count and next retry time.
- Delivery state.
- Checksum/hash if integrity checks are required.
- Correlation ID.
- Data classification and retention metadata.

### Write-ahead logs and transactions

Databases can use a write-ahead log (WAL) to protect changes before data pages flush. Durability settings must match power-loss risks and storage hardware. If a workload must confirm persistence before returning success, do not leave data solely in the OS page cache or unflushed buffers violating durability policy.

### Capacity planning for offline buffers

Estimate minimum capacity:

\[
BufferSize \approx EventRate \times AverageEventSize \times OfflineDuration
\]

Add overhead for:
- Metadata and index overhead.
- Retry copies or temporary payloads.
- Logs and checkpoints.
- Growth margin.
- Filesystem reserved space.
- Space needed for compaction/backups.

For example, an edge generating 30 events/second at 2 KiB average size needing 12 hours of offline buffering:

\[
30 \times 2KiB \times 43{,}200 \approx 2.47GiB
\]

This covers raw payloads only. Actual storage must be larger for indexes, WAL, replication, or overhead. If event sizes have a heavy tail, size using p95/p99 and enforce payload limits.

### Handling disk exhaustion

Set thresholds:
- Warning when buffer reaches a target utilization.
- Critical when headroom runs out.
- Admission control to drop or reject low-priority event classes.
- Retention/compaction for already-acknowledged data.
- Alerts when the oldest pending event exceeds SLA.

Never delete unacknowledged business events solely to free space. If low-priority telemetry must be evicted, policy must specify which data types, drop counts, and audit records.

## 6. Prioritizing data for synchronization

Upon reconnection, sending everything at once can saturate the WAN and cloud ingestion. Prioritize by business value and urgency.

Example priority tiers:
1. Security/audit events and critical command results.
2. Business transactions requiring completion.
3. Device status and inventory.
4. Operational telemetry.
5. Debug logs or reconstructible data.
6. Large artifacts transferable out-of-band.

### Priority policies

Each event class should define:
- Priority class.
- Maximum queue age.
- Retention when undeliverable.
- Retry policy.
- Data size limit.
- Ordering requirement.
- Whether lossy delivery is permitted.
- Deadline or expiration.

Never let debug logs fill the buffer and block critical transactions from syncing. Use per-class quotas or separate queues.

### Backpressure

When creation rate exceeds transmission rate:
- Backlog grows.
- Queue age increases.
- Local storage can fill up.
- High-priority events can be delayed.

Backpressure measures include throttling producers, telemetry sampling, batching events, limiting concurrency, and pausing deferrable workloads. Never apply a drop policy to business transactions without explicit business rules.

## 7. Detecting disconnection and recovery

Do not rely on a single Internet ping to declare the system online. Internet routing may work while ingestion APIs, internal DNS, or identity endpoints remain unreachable.

### Dependency-level health checks

Check separately:
- DNS resolution.
- TCP/TLS connectivity.
- Authentication/token validity.
- API readiness.
- Publish permissions.
- Ability to receive acknowledgements.
- Latency and packet loss.
- Clock synchronization if protocols depend on timestamps.

Use lightweight health probes with bounded timeouts and reasonable intervals. Avoid aggressive probing that adds load over degraded links.

### Connectivity state machine

~~~mermaid
stateDiagram-v2
    [*] --> ONLINE
    ONLINE --> DEGRADED: high latency or partial errors
    ONLINE --> OFFLINE: dependencies unreachable
    DEGRADED --> OFFLINE: sustained errors
    OFFLINE --> RECONNECTING: endpoint recovered
    RECONNECTING --> SYNCHRONIZING: auth and handshake succeeded
    SYNCHRONIZING --> ONLINE: backlog and consistency criteria met
    SYNCHRONIZING --> DEGRADED: large backlog or partial errors
    RECONNECTING --> OFFLINE: handshake failed
    SYNCHRONIZING --> OFFLINE: connection lost again
~~~

Applications should surface clear states:
- Online.
- Degraded.
- Offline; local operations only.
- Reconnecting.
- Synchronizing; pending changes.
- Sync blocked; action required.

### Hysteresis

To prevent state flapping:
- Require multiple consecutive probe failures before transitioning offline.
- Require multiple successful probes or a full handshake before transitioning to reconnecting.
- Apply cooldowns between attempts.
- Distinguish network failures from authentication failures.

If a TLS certificate expires, endless network retries will not fix it; surface a "sync blocked" state with credential remediation guidance.

## 8. Reconnection synchronization protocol

A sync protocol should follow clear steps:

1. **Authenticate:** edge proves identity via certificate, workload identity, or appropriate credential.
2. **Negotiate:** exchange protocol version, schema support, capabilities, and data scope.
3. **Identify state:** send edge ID, epoch/generation, last acknowledged sequence, and local checkpoint.
4. **Reconcile metadata:** cloud returns cursor, snapshot version, or received state.
5. **Upload pending changes:** ship events in batches and required order.
6. **Apply inbound changes:** receive deltas or snapshots from cloud.
7. **Resolve conflicts:** apply ownership and conflict policies.
8. **Commit checkpoint:** persist watermark/cursor only after data is durably applied.
9. **Verify:** cross-check event counts, hashes, or aggregates.
10. **Resume:** gradually return workloads to normal online mode.

### Handshake

The handshake lets both sides confirm:
- Edge identity and site.
- Protocol/schema version.
- Last cloud cursor.
- Last locally committed sequence.
- Pending event count/bytes.
- Snapshot generation.
- Supported conflict policy.
- Device certificate status.
- Clock offset if needed.

Never start streaming bulk data before both sides agree on which checkpoint to resume from.

### Acknowledgement

The cloud should acknowledge an event or batch only after committing per defined semantics. If it acks before committing, the edge may delete the event and a cloud crash would lose data.

Acknowledgements should include:
- Event ID or sequence range.
- Commit status.
- Cloud cursor/watermark.
- Rejection/conflict code.
- Retryability.
- Result reference.

The edge deletes or compacts outbox records only after receiving a valid ack and safely persisting its checkpoint.

## 9. Incremental sync vs. full resynchronization

### Delta sync

Delta sync transmits only changes since the last confirmed cursor/checkpoint:
- Low bandwidth consumption.
- Short recovery time.
- Reduced cloud load.
- Easy prioritization of critical events.

However, deltas depend on intact event history and valid checkpoints on both sides.

### Full snapshot

Full resync transfers a fresh snapshot or current state:
- Suitable when the edge loses its checkpoint.
- Suitable when schema/state migrations break delta compatibility.
- Recovers after event history passes retention.
- Consumes significant time, storage, and bandwidth.

### Choosing delta vs. snapshot

Use delta when:
- Cursor remains valid.
- Event history is contiguous.
- Schemas are compatible.
- No corruption occurred.
- Outage duration stayed within the retention window.

Use snapshot when:
- Edge is newly provisioned or lost local state.
- Unrecoverable sequence gaps exist.
- Checkpoint is corrupted.
- Delta history has expired.
- Sides no longer share a schema generation.
- Integrity verification fails.

### Safe snapshots

Snapshots should carry:
- Snapshot ID and generation.
- Schema version.
- Created-at timestamp.
- Data scope.
- Content hash/manifest.
- Pagination/chunk manifest.
- Consistent watermark.
- Signature or authentication metadata.

Never overwrite a live database piece-by-piece while downloading a snapshot. Download into a staging area, verify checksums, validate schema compatibility, and perform an atomic switch or rollback-capable migration.

## 10. Ordering, sequencing, and versioning

In distributed systems, events can arrive late, duplicated, or out of order. Timestamps alone are not always sufficient to determine order.

### Per-aggregate sequences

Assign monotonically increasing sequences per entity or aggregate:
- Device 17: 101, 102, 103.
- Order 42: 8, 9, 10.
- Site inventory partition: dedicated offset.

Sequences detect:
- Duplicates.
- Missing events.
- Out-of-order delivery.
- Replays.
- Stale updates.

A single global sequence across the entire system is rarely necessary. Global sequences create bottlenecks when ordering only matters within an aggregate.

### Event time vs. ingest time

- **Event time:** when the business event occurred at the edge.
- **Ingest time:** when the cloud received the event.
- **Commit time:** when the cloud applied the change.
- **Observed time:** when telemetry recorded the measurement.

Edge clocks can drift or desync while offline. Use sequences and causal metadata for ordering; use timestamps for temporal analytics with documented error bounds.

### Versions and optimistic concurrency

Records can carry a version incremented on each update. When the cloud receives an update referencing an older version, it can:
- Accept if no competing change exists.
- Reject as a conflict for resolution.
- Merge using field/domain rules.
- Store as a proposal for authorized review.

For example, an API updates a record with `expected_version = 12`. If the server is already at 13, an update based on version 12 must not overwrite blindly.

### Epochs and fencing tokens

When an edge reconnects after a long absence, the cloud may have granted ownership or a new lease to another node. Epochs/generations and fencing tokens let storage/services reject writes from stale workers. Never rely solely on timestamps to protect write authority during split-brain scenarios.

## 11. Duplicate handling and idempotency

Disconnection can happen after the cloud commits but before the edge receives the ack. The edge will resend the event. Duplicates are therefore a normal scenario to design for upfront.

### Stable event IDs

Each event needs a unique ID generated before the first send attempt and preserved across all retries. Never generate a new event ID when retrying the same change.

The cloud can store inbox/deduplication keys:
- Edge ID.
- Event ID.
- Event type or operation scope.
- Commit result.
- Received/committed timestamp.

### Idempotent application

An idempotent operation can be reapplied without producing additional business side effects. Examples:
- Setting device status to a specific value guarded by version.
- Inserting a record with a unique business key.
- Upserting by event ID.
- Incrementing a counter via a deduplicated event ledger.

An operation like "add 5 to inventory" is not naturally idempotent. Retrying it adds 5 twice. Record operation IDs or execute within a transaction backed by an inbox table.

### Transactional inbox

One pattern:
1. Receive event.
2. Start transaction.
3. Check if event ID already exists.
4. If already committed, return the stored ack.
5. Otherwise, insert inbox record and update domain state.
6. Commit.
7. Return acknowledgement.

When the domain update and inbox record share one transaction, duplicates are identified safely.

### Do not promise end-to-end exactly-once

Networks, queues, and processes can all retry. In practice, systems pair at-least-once transport with idempotent consumers, deduplication, and transactional state. Claim exactly-once only within a specifically proven transactional boundary—never broadly across the entire pipeline.

## 12. Conflict resolution strategies

Conflicts occur when both sides modify the same data before synchronizing. No single policy fits every data type.

### Last-write-wins

Selects the change with the latest timestamp or version. Simple, but risks losing updates if clocks drift or two changes are independent. Use only when full replacement semantics are acceptable.

### Field-level merge

If the two sides edited disjoint fields, merge field by field. Define which fields are independent and which share invariants.

For example, edge updates device notes while cloud updates admin tags; those two fields can merge. However, edge modifying stock quantity while cloud modifies reservations cannot merge independently because they share a total inventory invariant.

### Domain-specific merge

Apply business logic:
- Inventory: apply a movement ledger rather than overwriting totals.
- Orders: allow only valid state-machine transitions.
- Telemetry: append events rather than overwriting.
- Configuration: cloud policy acts as authority; edge submits desired-state proposals.
- Counters: use operation IDs or CRDT counters where semantics fit.

### Manual resolution

For conflicts impacting finances, access control, safety, or irrecoverable data, route to a manual resolution queue. The UI should surface:
- Both versions.
- Source and timestamp of each change.
- Who made each change.
- Conflict reason.
- Permitted resolution actions.
- Audit record upon resolution.

### Selection table

| Data type | Typically suitable policy | Reason |
|---|---|---|
| Append-only telemetry | Append + dedupe | Never overwrites measurements |
| Central configuration | Cloud-authoritative | Prevents edge from overriding policy |
| Local notes | Field merge or LWW | Low risk when fields are independent |
| Inventory | Movement ledger / domain merge | Must preserve invariants |
| Command state | Sequence + state machine | Order and execution authority matter |
| Financial transactions | Idempotency + central reconciliation | Cannot merge arbitrarily |
| Distributed counters | CRDT or operation ledger | Independent increments can add cleanly if semantics match |

### Conflicts are not transport errors

An event that reaches the cloud and gets rejected for a version conflict is a business outcome to handle—do not retry the exact same payload infinitely. Distinguish transport retries, transient server errors, and semantic conflicts.

## 13. Preventing split-brain and unsafe concurrent writes

Split-brain occurs when two nodes both believe they hold authoritative write rights and update the same state concurrently. Disconnection increases this risk.

### Mitigations

- Partition ownership by site/partition.
- Use expiring leases with fencing tokens.
- Use monotonically increasing epochs/generations.
- Enforce single-writer per aggregate when invariants require it.
- Use quorum or consensus for data needing strong consistency.
- Pause operations that cannot be arbitrated offline.
- Reconcile before allowing a new writer to proceed.

### Leases are insufficient without fencing

A node can pause for a long time, its lease expires, and another node acquires a new lease. When the paused node wakes up, it might still send write requests. Monotonic fencing tokens let storage/services reject requests carrying stale tokens.

### When must offline writes be rejected?

- Two edges could simultaneously modify a shared balance or shared inventory.
- The operation requires a globally unique sequence.
- The command requires fresh authorization verification from the cloud.
- Policies or credentials were revoked while the edge remained unaware.
- Physical effects are irreversible.
- Insufficient local data exists to verify safety preconditions.

Offline designs must explicitly list prohibited operations, not only supported ones.

## 14. Large data sync and bandwidth management

Edges can produce large video files, images, model artifacts, logs, or datasets. Uploading everything at once upon reconnect can saturate links and starve transactional traffic.

### Metadata first, payloads later

One approach:
1. Synchronize event metadata and business state.
2. Send artifact manifests.
3. Transfer files in chunks.
4. Verify checksums.
5. Commit references once all chunks arrive.
6. Delete local copies per retention after confirmation.

### Chunking and resuming

Each chunk should carry:
- Artifact ID.
- Chunk index.
- Byte range.
- Hash.
- Upload session ID.
- Expiry.
- Retry state.

If connectivity drops mid-transfer, resume from unacknowledged chunks. Do not re-upload entire files when multipart/resumable uploads are supported.

### Bandwidth throttling

Techniques include:
- Priority queues.
- Token buckets/rate limits.
- Compression.
- Delta encoding.
- Content-hash deduplication.
- Scheduling bulk transfers off-peak.
- Concurrency limits.
- Local caching.
- Separate channels for control vs. bulk data.

Avoid compressing already-compressed or encrypted data if CPU cost outweighs bandwidth savings. Benchmark against edge CPU capacity and link characteristics.

## 15. Security during prolonged edge disconnection

Being offline delays policy updates, certificate revocations, and security patches. Therefore, bound autonomous lifetimes and limit locally stored data.

### Device identity

Each edge node needs a dedicated identity:
- Certificate or workload identity.
- Keys stored in a TPM/secure element if available.
- Rotation policy.
- Device enrollment and decommissioning.
- Revocation upon device loss.
- Auditing for sync sessions and sensitive actions.

Never share one credential across multiple sites. If one device is compromised, revocation scope must stay contained.

### Credential expiration and offline grace

Short-lived credentials improve security yet can expire while a site is offline. Design a bounded offline grace window:
- Cached credentials remain usable only up to a maximum duration.
- Offline permissions are restricted by operation.
- Privilege escalation is disallowed.
- Issue time and expiration are recorded.
- On reconnect, verify revocation status and refresh before unlocking sensitive actions.

Never extend credentials indefinitely just for availability.

### Local data protection

- Encrypt databases, spools, and disks at rest.
- Encrypt in transit during synchronization.
- Enforce secure boot and image signing.
- Apply least privilege to sync agents.
- Keep secrets out of logs.
- Enforce anti-rollback or tamper protection if required by the threat model.
- Perform secure deletion per policy when devices are decommissioned.

### Schema and payload validation

The cloud must not trust payloads solely because they come from a registered edge. Validate schemas, sizes, sequences, signatures where needed, and event-type permissions. Quarantine malformed events instead of letting them break pipelines.

## 16. Schema evolution and compatibility during long outages

An edge may be offline while the cloud upgrades. Upon reconnecting, the edge might send events in an older schema.

Requirements:
- Version envelopes and payloads.
- Use backward-compatible field additions whenever possible.
- Support multiple schemas in consumers during migration windows.
- Explicitly reject unsupported versions.
- Provide migration or translation adapters.
- Align retention windows with maximum offline duration.
- Test events generated by older edge releases.

### Expand-and-contract

A safe sequence:
1. Cloud adds support for reading the new schema while retaining old schema support.
2. Edges upgrade gradually.
3. Monitor event proportions by schema version.
4. Wait until offline grace windows and stale backlogs drain.
5. Only then remove old schema support.

Never alter the semantics of existing fields without versioning. An offline event can arrive after multiple cloud releases have shipped.

### Avoid blind queue migrations

If local queues hold legacy events, migrations require:
- Backups/checkpoints.
- Schema validation.
- Idempotent transformations.
- Retaining original payloads or audit references.
- Rollback paths.
- Never acknowledging old records until transformed data commits.

## 17. Time synchronization and ordered data

Edges can lose NTP or authoritative time sources for long periods, causing clock drift.

### Timestamps are not sequences

Use monotonic clocks to measure local durations; use wall clocks to record wall-clock times; use sequences/versions to determine change order. Never compare raw timestamps across different edges as a total order without knowing clock offsets.

### Time metadata

Fields to capture:
- `event_time`.
- `observed_time`.
- `local_sequence`.
- `edge_epoch`.
- `cloud_received_at`.
- `cloud_committed_at`.
- `estimated_clock_offset`.
- `time_quality/status`.

If processing events by event-time, define watermarks and late-event policies. To protect transaction ordering, rely on sequences/transaction versions.

### Clock correction

Upon reconnect:
- Measure clock offset.
- Do not retroactively rewrite historical timestamps.
- Record time quality.
- Adjust future schedules/leases.
- Check certificate validity and token expiration.
- Avoid using untrusted local clocks as the sole basis for authorization.

## 18. Managing pending data lifecycles

Offline events may sit in spools for extended periods. Define clear policies:
- Maximum offline age.
- Retention.
- Expiration.
- Retry counts.
- Dead-letter/quarantine handling.
- Manual replay.
- Data deletion.
- Legal hold.
- Priority downgrade.

### Expired events

Not every old event is useless. Old telemetry may still be required for auditing; old control commands may have to expire because late execution is unsafe.

Each event type should define semantics:
- Can it execute late?
- Can it be discarded?
- Should users be notified?
- Must it route to manual review?
- Can it be rolled up into a snapshot instead of replaying every event?

### Tombstones and deletions

If the cloud requests data deletion, an offline edge may miss the command. Upon reconnect, sync versioned tombstones or deletion markers. Prevent stale snapshots from resurrecting data deleted under policy.

## 19. Example: retail store losing WAN

A store runs POS, an inventory cache, receipt printers, and cloud connectivity. When the WAN drops:
- POS continues recording local transactions.
- Each transaction gets a unique transaction ID.
- Pricing and catalogs use a versioned/TTL snapshot.
- Offline payment caps are enforced.
- Local inventory records changes as a movement ledger.
- Transactions persist in the local database and outbox.
- UI displays offline mode and feature restrictions.

When connectivity returns:
1. Edge authenticates the device.
2. Sends handshake with last sequence.
3. Cloud returns cursor and active policies.
4. Edge ships transactions in required order.
5. Cloud deduplicates by transaction ID.
6. Inventory service applies the movement ledger and validates invariants.
7. Cloud returns acks and conflict outcomes.
8. Edge updates transaction sync states.
9. Large artifacts/logs upload afterward.
10. Dashboard reports backlog at 0 and reconciliation complete.

### Inventory conflict scenario

Two offline stores sell the last units of an item while central inventory has not updated. Total system inventory cannot be strictly guaranteed if both sell without limit from the same shared pool.

Mitigations include:
- Pre-allocating stock quotas/reservations per store.
- Capping offline sale quantities.
- Allowing controlled oversell within business thresholds with follow-up fulfillment workflows.
- Blocking high-risk SKUs while offline.

The policy depends on business risk; post-hoc synchronization cannot put a physically sold item back on the shelf.

## 20. Example: edge gateway in a factory

A factory gateway collects telemetry and controls select equipment on the OT network. The cloud handles aggregation, analytics, and configuration updates.

During disconnection:
- Local control continues under verified policies.
- Telemetry buffers to disk.
- Critical safety alarms persist with high priority.
- Stale or expired cloud commands are not executed late.
- On-site operators retain local visibility.
- The sync agent never interferes with real-time control loops.

Upon reconnect:
- Authenticate the gateway and verify certificates.
- Compare configuration generations.
- Sync audits and alarms before bulk telemetry.
- Upload data in chunks with checksums.
- Download new configuration into staging.
- Verify signatures, versions, and policies.
- Activate configuration only via approved procedures.
- Cross-check event sequences and missing records.

Never let cloud sync consume CPU, network, or storage needed by control functions. Isolate resource budgets and network paths between local control planes and bulk synchronization.

## 21. Example event envelope protocol

An event can carry standardized metadata:

~~~json
{
  "event_id": "evt-01J9EDGEA7",
  "edge_id": "site-042-gateway-01",
  "edge_epoch": 18,
  "sequence": 10452,
  "aggregate_type": "device-state",
  "aggregate_id": "device-17",
  "event_type": "DeviceReadingRecorded",
  "schema_version": 3,
  "event_time": "2026-11-22T10:15:30Z",
  "local_recorded_at": "2026-11-22T10:15:31Z",
  "correlation_id": "job-2026-11-22-0042",
  "payload_ref": "local-object://telemetry/part-10452",
  "payload_sha256": "example-checksum",
  "priority": "normal"
}
~~~

This example illustrates structure only. Production systems should enforce:
- Unique, immutable event IDs.
- Unambiguous sequence scope.
- Access-controlled payload references.
- Hashes computed from actual contents.
- Timezone-aware timestamps.
- Supported schema versions.
- No secrets or sensitive payloads inside envelope metadata.

### Batch acknowledgements

The cloud can return per-event statuses:
- `committed`.
- `duplicate_already_committed`.
- `rejected_schema`.
- `conflict_requires_resolution`.
- `expired`.
- `retryable_failure`.

Do not return a single HTTP 200 for an entire batch if individual events were rejected. The edge must know exactly which events committed so it advances checkpoints accurately.

## 22. Synchronization observability and alerting

Dashboards should display connectivity status and data sync status separately.

### Connectivity metrics

- `connection_state`.
- `last_successful_handshake`.
- `probe_failure_count`.
- `reconnect_attempts`.
- `TLS/authentication failure`.
- `round-trip latency`.
- `packet loss`.
- `clock offset`.

### Sync metrics

- `pending_event_count`.
- `pending_bytes`.
- `oldest_pending_event_age`.
- `upload/download throughput`.
- `last_acked_sequence`.
- `sequence_gap_count`.
- `duplicate_event_count`.
- `conflict_count`.
- `rejected_event_count`.
- `snapshot_generation`.
- `sync_lag_seconds`.
- `full_resync_duration`.
- `checksum_failure_count`.

### Local resource metrics

- `spool disk used/free`.
- `database size`.
- `WAL growth`.
- `compaction backlog`.
- `CPU/memory usage of sync agent`.
- `dropped telemetry count`.
- `oldest unacknowledged event`.
- `local storage health`.

### Critical alerts

- Edge offline longer than offline grace period.
- Pending bytes approaching disk exhaustion.
- Oldest business event exceeding SLA deadline.
- Unrecoverable sequence gaps.
- Authentication/certificate failures.
- Sudden spike in conflict rates.
- Sync throughput lower than incoming event rate.
- Checksum or signature verification failures.
- Snapshot too old or schema unsupported.
- Cloud acks stalled with zero progress.

Do not alert only on "edge offline." Operators need to know whether the site is still functioning, how much buffer remains, and whether data loss is imminent.

## 23. Recovery runbook upon reconnection

A reconnect runbook may include:

1. **Verify link:** DNS, TLS, APIs, and authentication all work.
2. **Verify edge identity:** certificates, device status, revocation, and epoch.
3. **Inspect local health:** disk, database, WAL, outbox, and checksums.
4. **Handshake:** exchange schemas, cursors, sequences, and snapshot generations.
5. **Classify backlog:** business events, audits, telemetry, artifacts.
6. **Sync high priority first:** transactions and security events ahead of bulk data.
7. **Handle duplicates:** cloud returns previously committed results.
8. **Handle gaps/conflicts:** replay, snapshot, or manual resolution.
9. **Sync inbound deltas:** pull cloud state per ownership policy.
10. **Upload large artifacts:** resumable chunks with checksums.
11. **Commit checkpoints:** only after data is durably applied.
12. **Verify:** reconcile sequence ranges, counts, and hashes/manifests.
13. **Drain backlog gradually:** ramp throughput while monitoring downstream load.
14. **Business reconciliation:** verify transaction totals, inventory, or critical state.
15. **Return to online:** only once sync lag and consistency pass thresholds.
16. **Record audit:** outage duration, replayed data, conflicts, and operator actions.

### Do not mark online solely because the queue is empty

A queue might be empty because events were dropped or moved to a DLQ. Completion criteria should require:
- Zero pending events in required priority tiers.
- Zero unresolved sequence gaps.
- Verified snapshots/deltas.
- Resolved critical conflicts.
- Compatible checkpoints across cloud and edge.
- Passing business reconciliation.

### Partial recovery

An edge may finish syncing transactions while logs or video remain queued. You can allow business-online status while bulk uploads continue, provided policies and workloads permit. Status should clearly display `"business sync complete, bulk upload pending"`.

## 24. Testing disconnected operation

Do not merely unplug a network cable once. Test diverse failure modes:

- Total WAN loss.
- DNS failure while IP routing remains intact.
- Expired TLS certificates.
- Tokens expiring while offline.
- High packet loss and latency.
- Flapping connectivity.
- Cloud commits event but ack is lost.
- Edge crashes after local commit.
- Edge crashes after cloud commit before ack.
- Disk near full or rapid WAL growth.
- Sequence gaps or corrupted events.
- Interrupted snapshot downloads.
- Concurrent writes from two offline edges.
- Newer cloud schema vs. older edge schema.
- Clock drift.
- Device revoked while offline.

### Test criteria

- Zero loss of locally committed events per durability policy.
- Duplicates produce zero duplicate side effects.
- Event ordering holds within required scopes.
- Conflicts resolve deterministically or route to manual queues.
- Storage stays within bounded thresholds.
- Local control loops continue meeting SLAs.
- Reconnection does not overload cloud/databases.
- Checkpoints advance only after commits.
- Crash recovery works at every critical point.
- Audit trails show which events were received, committed, rejected, or replayed.

### Chaos testing and drills

Conduct periodic drills simulating outages of 15 minutes, several hours, and multiple days as required. Validate buffer capacity, credential grace windows, schema compatibility, and backlog drain rates.

## 25. Common design mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Buffering only in RAM | Data lost on crash/power loss | Durable local database or spool |
| Sending event then deleting locally immediately | Data lost if ack drops or cloud fails before commit | Wait for post-commit acknowledgement |
| Generating new event IDs on retry | Deduplication fails to detect duplicates | Keep event IDs immutable across retries |
| Using timestamps for total ordering | Clock drift scrambles event order | Per-aggregate sequences/versions |
| Uncoordinated dual writes from cloud and edge | Lost updates and split-brain | Explicit ownership, versions, leases, and conflict rules |
| Flushing entire backlog at once | Saturates WAN and downstream services | Priority queuing, rate limits, and backpressure |
| Treating successful ping as online | APIs or auth may still fail | Handshakes and end-to-end probes |
| Ignoring legacy schema compatibility | Long-offline edges fail to sync | Versioning and expand-and-contract |
| Deleting queue on full disk | Loses transactions/audits | Quotas, admission control, and retention policies |
| Sync agent starving control resources | Disrupts on-site workloads | Resource isolation and bandwidth budgets |
| Using last-write-wins for all data | Silently loses meaningful updates | Domain-specific conflict resolution |
| Skipping snapshot verification | Corrupted state enters the system | Manifests, checksums, signatures, and atomic switches |
| Ignoring clock drift | Broken leases, certificates, and ordering | Time quality metrics and sequences |
| Executing stale commands late | Unsafe delayed actions | Expirations, generations, and command state machines |

## 26. Disconnected operation design workflow

1. **Inventory dependencies:** list cloud APIs, identity, DNS, databases, queues, storage, and control services.
2. **Classify operations:** online-only, offline-capable, degraded, or fail-safe.
3. **Define ownership:** cloud, edge, partitioned, or shared.
4. **Design local state:** databases, outboxes, checkpoints, and retention.
5. **Size offline capacity:** event rates, payload sizes, outage duration, and growth margin.
6. **Define event contracts:** IDs, sequences, schemas, timestamps, and priorities.
7. **Design sync protocols:** handshakes, deltas, snapshots, acks, and checkpoints.
8. **Design idempotency:** inboxes, deduplication, and transactional applies.
9. **Define conflict policies:** per domain/entity.
10. **Prevent split-brain:** epochs, leases, fencing, and write ownership.
11. **Design security:** identities, key rotation, offline grace, and local encryption.
12. **Add backpressure:** rates, queue classes, retries, and storage thresholds.
13. **Design observability:** connectivity, backlog, sync lag, conflicts, and disk.
14. **Build recovery runbooks:** priorities, reconciliation, verification, and online criteria.
15. **Test outage scenarios:** network, crashes, duplicates, schemas, clocks, and capacity.
16. **Run periodic drills:** measure RPO, RTO, backlog drain time, and data integrity.

## 27. Production checklist

### Offline capability
- [ ] Operations classified into offline, degraded, online-only, and fail-safe.
- [ ] Owners and policies assigned for each data type.
- [ ] Edge performs only permitted operations within offline grace windows.
- [ ] UI/APIs indicate offline status and stale data.
- [ ] Functions degrade/restrict when caches or credentials grow too old.

### Local durability
- [ ] Events are persisted durably before confirming success.
- [ ] Outbox/store-and-forward implemented.
- [ ] Business state and outbox commit atomically.
- [ ] Buffer capacity covers target outage duration plus growth margin.
- [ ] Disk thresholds, backpressure, and retention configured.
- [ ] Unacknowledged events are not deleted violating policy.

### Synchronization
- [ ] Handshake and edge identity verification implemented.
- [ ] Cursors/sequences and checkpoints implemented.
- [ ] Clear criteria exist for delta vs. full snapshot sync.
- [ ] Acks return only after durable commit.
- [ ] Event IDs are stable and consumers are idempotent.
- [ ] Duplicates, out-of-order events, and sequence gaps are handled.
- [ ] Checksums/manifests and atomic snapshot activation implemented.
- [ ] Rate limits, priorities, and resumable uploads configured.

### Consistency and security
- [ ] Cloud/edge ownership clearly defined.
- [ ] Conflict policies tailored per domain.
- [ ] Epochs/fencing implemented where needed against split-brain.
- [ ] Offline credential grace windows are bounded.
- [ ] Local data is encrypted and access-controlled.
- [ ] Schemas remain compatible with long-offline edges.
- [ ] Clock drift is measured and timestamps are not the sole ordering mechanism.
- [ ] Expired/revoked events are handled per policy.

### Operations
- [ ] Dashboards track connectivity, pending bytes, oldest event age, and sync lag.
- [ ] Alerts configured for disk, auth, sequence gaps, conflicts, and backlogs.
- [ ] Reconnect and manual conflict resolution runbooks exist.
- [ ] Crash tests cover commit/ack failure points.
- [ ] Outage drills measure backlog drain times.
- [ ] Business reconciliation runs before marking fully online.
- [ ] Audit trails capture replays, rejections, conflicts, and operator actions.

## Conclusion

Disconnected operation requires defining upfront which operations the edge may continue, which data may be written locally, and where authoritative truth resides. Store-and-forward with a durable local outbox preserves changes across outages; handshakes, deltas/snapshots, sequences, acknowledgements, and checkpoints make synchronization resumable after disruptions. Duplicates and out-of-order events must be handled with stable IDs, idempotency, versioning, and transactions; conflicts need domain-specific policies, while split-brain requires proper ownership, leases, or fencing. Upon reconnection, prioritize critical data, throttle backlogs, verify integrity, and reconcile business state before declaring full online recovery. Sound design preserves edge availability while safeguarding consistency, safety, and system-wide traceability.
