# Gathering Evidence, Isolating Root Causes, and Verifying Fixes in MongoDB

A MongoDB incident usually starts with symptoms in the application: slow APIs, timeouts, rising 5xx errors, missing returned data, rejected writes, or an inability to elect a primary. These symptoms **do not by themselves identify the root cause**. A timeout can stem from a query scanning too many documents, an exhausted connection pool, network packet loss, an election, overloaded disk I/O, or a client using an inappropriate read/write concern.

If the operations team rushes to restart processes, drop indexes, raise timeouts, or alter replica set configuration before collecting evidence, they can erase diagnostic trails, trigger new errors, and make the next incident harder to resolve. A reliable methodology is **gather evidence → build and falsify hypotheses → make controlled changes → verify recovery → record preventive lessons**.

This lesson belongs to the **Troubleshooting** chapter of the **Database Engine Document MongoDB** module and guides multi-layer MongoDB diagnostics across the Java application, driver/connection pool, network, `mongod`/`mongos`, query planner/indexes, replica set, sharding, storage, security, and data correctness.

**Safety principle:** Information-gathering commands in this lesson are primarily read-only. Some commands or profiling options impact performance or can expose sensitive data. Never run restarts, `killOp`, `stepDown`, force reconfig, repair, drop/delete operations, index changes, or production configuration edits without impact assessment and an approved change process. During an incident, prioritize controlled service restoration and data preservation.

## 1. Lesson Objectives

After this lesson, you will be able to:

1. Distinguish **symptoms**, **observed events**, **hypotheses**, and **root causes**.
2. Open an incident timeline with unified timestamps and confidence levels for each piece of evidence.
3. Collect metrics, logs, traces, and configurations in least-invasive order.
4. Use MongoDB commands such as `hello`, `serverStatus`, `rs.status`, `currentOp`, and `explain` in the proper context.
5. Isolate issues across application/driver, network, query/index, replication, sharding, or storage layers.
6. Understand why a server selection timeout does not automatically mean a MongoDB server has crashed.
7. Read query plans and distinguish causes of `COLLSCAN`, blocking `SORT`, and high `docsExamined`.
8. Handle evidence around replica set elections, replication lag, write concern, and stale reads.
9. Design reversible, low-impact experiments to verify hypotheses.
10. Confirm post-fix recovery across system health, workload, SLOs, and business/data invariants.
11. Build an incident runbook, evidence ledger, rollback gates, and reproducible postmortem.

## 2. Four Concepts You Must Not Mix Up

| Concept | Example | Level of certainty |
| --- | --- | --- |
| Symptom | Order listing API p95 jumps from 120 ms to 3 s | Observed by users |
| Observation | `totalDocsExamined` is huge; plan shows `COLLSCAN` | Measured |
| Hypothesis | A filter change prevents the query from using its index | Needs verification |
| Root cause | A release changed the predicate and dropped the leading equality field of a compound index, triggering massive scans as traffic rose | Proven by a chain of evidence |

An observation like "CPU 95%" can be a **consequence** of a scanning query rather than the root cause. A restart lowering CPU does not prove restarting fixed the root cause.

### 2.1. Correlation Is Not Causation

Two graphs spiking together at 10:05 do not prove event A caused B. You must compare exact timing, causal pathways, independent corroborating evidence, and results after a controlled change.

### 2.2. Focus on Falsifiable Claims

A useful hypothesis predicts testable observations:

- If a missing index is the cause, the query plan will fail to use an appropriate index and `docsExamined` will be high.
- If the pool is exhausted, client-side connection wait times rise even without a corresponding rise in server execution latency.
- If the replica set is undergoing an election, logs/topology events and the window with no writable primary will match the timing of write errors.

If evidence refutes a prediction, update the hypothesis rather than clinging to the initial guess.

## 3. Layered Incident Model

~~~text
User / Client
      |
      v
API / Business service
      |
      v
MongoDB Java Driver
  - connection pool
  - server selection
  - retry/read preference
      |
      v
Network / TLS / DNS / Proxy
      |
      v
mongos (if sharded)
      |
      v
mongod / Replica set
  - elections
  - read/write execution
  - locks/tickets
  - query planner/index
      |
      v
WiredTiger / Memory / CPU / Disk
      |
      v
Data / Durability / Consistency
~~~

Do not jump straight to `mongod` merely because an error contains the word "MongoDB." Lost API connectivity can equally stem from DNS, firewalls, secret rotation, or the client pool.

### 3.1. Identify the Blast Radius

Ask what the error affects:

- One endpoint or every endpoint?
- One tenant, one collection, or the whole cluster?
- Reads, writes, or both?
- One app version/pod or every version?
- One AZ/region or all of them?
- One shard/replica set member or the entire deployment?
- Peak traffic only or off-peak too?
- Only after a deploy/migration, or unrelated to recent changes?

Scope and timing are two powerful narrowing clues.

## 4. Set the Right Goal from the Start

Before making any change, clarify:

1. **Impact level:** failing request volume, affected tenants/users, and whether data is at risk of loss or corruption.
2. **Urgency:** are SLOs breached? Is there active write interruption or data corruption risk?
3. **Priority objective:** reduce user impact, safeguard data, restore the write path, or restore reporting reads.
4. **Action boundaries:** who is authorized to approve failover, config, or index changes?
5. **Roles:** incident commander, database operator, application owner, communications owner.
6. **Time markers:** start time, latest changes, and recovery measurement checkpoints.

### 4.1. Mitigation Differs from a Root-Cause Fix

Throttling request rates, rolling back a release, or shifting traffic can quickly mitigate user impact while the root cause is still analyzed. Distinguish **temporary mitigation** from **permanent root-cause fix**.

### 4.2. Never Sacrifice Data for a Green Dashboard

Cutting traffic or errors by disabling validation or stripping write concern without assessing durability can turn dashboards green while putting data in far greater danger.

## 5. The First-15-Minutes Process

| Window | Key tasks | Expected output |
| --- | --- | --- |
| 0–2 min | Confirm incident, classify impact, assign owners | Incident ID, severity, scope |
| 2–5 min | Lock down UTC timeline, app versions, recent changes | T0 marker and suspected changes |
| 5–10 min | Gather app error rates, p95, driver errors, MongoDB topology/host metrics | Initial evidence |
| 10–15 min | Compare against baseline, branch hypotheses, pick lowest-impact next checks | Prioritized hypothesis list |

This sequence is an example workflow, not a guarantee of diagnostic duration. Severe data-loss or security incidents may require immediately activating specialized escalation tracks.

### 5.1. Questions to Answer Before Fixing

- Since when?
- Where?
- What changed?
- What evidence confirms or refutes it?
- Could the planned change disrupt users or lose data?
- What is the rollback path?

### 5.2. Never Change Multiple Variables at Once

If you enlarge the pool size, add an index, and restart the replica set simultaneously and p95 then drops, it becomes nearly impossible to tell which change helped and which introduced side effects.

## 6. Evidence Ledger

Every piece of evidence needs a **source, timestamp, scope, value, and confidence level**.

| ID | UTC Time | Source | Observation | Related direction |
| --- | --- | --- | --- | --- |
| E01 | 10:03:10 | API metrics | `/bookings` endpoint p95 rises | Client symptom |
| E02 | 10:03:13 | Driver logs | Server selection errors spike | Topology/network |
| E03 | 10:03:15 | Replica status | No primary during an interval | Election |
| E04 | 10:03:16 | `mongod` logs | Member election events | Supports hypothesis |
| E05 | 10:06:00 | App metrics | Writes recover after primary elected | Observed recovery |

Never record "E03 proves a network fault" if all you observed is a primary change. Evidence must state strictly what was observed.

### 6.1. Separate Facts from Interpretations

~~~text
FACT:
  From 10:03:11 to 10:03:27 multiple server selection timeouts occurred.
  Primary changed between status samples.

HYPOTHESIS:
  Election window caused part of the write errors.

NOT YET KNOWN:
  Why the original primary became unavailable.
~~~

### 6.2. Retain Originals Per Policy

Raw logs and metrics may need retention under the incident ID, subject to access controls and redacting secrets/PII. Never post raw telemetry containing credentials in public channels.

## 7. Synchronizing Time and Identifiers

An incident spans Java JVMs, Docker/Kubernetes, Linux hosts, `mongod`, and monitoring platforms across multiple timezones.

### 7.1. Use a Unified UTC Reference

Example:

~~~text
2026-11-14T10:03:14.320Z
~~~

Record the original timezone if source logs use local time. Distinguish wall-clock timestamps from monotonic durations; clock skew can make event ordering appear inverted.

### 7.2. Identifiers to Capture

- Incident ID.
- Environment, cluster/deployment, region/AZ.
- Replica set, member, shard, or `mongos` if applicable.
- App service, pod/host, version/commit/release.
- Trace ID/request ID and masked/hashed tenant ID where needed.
- Collection/operation category.
- Time window, query shape, and workload size.

### 7.3. Never Rely Entirely on One Machine's Clock

If a host suffers clock skew, cross-check the timeline against independent sources such as platform events, cluster topology logs, and distributed traces.

## 8. Incident Record Template

~~~yaml
incidentId: "INC-2026-001"
title: "Booking read latency spike"
environment: "production"
severity: "SEV2"
status: "investigating"
startUtc: "2026-11-14T10:03:00Z"
scope:
  services: ["booking-api"]
  operations: ["find"]
  regions: ["region-a"]
  tenants: "multiple"
impact:
  errorRate: "observed in dashboard"
  p95: "observed above SLO"
changeWindow:
  - "booking-api release"
  - "index migration"
hypotheses:
  - id: H1
    statement: "query shape no longer matches index"
    evidenceFor: ["E01"]
    evidenceAgainst: []
    nextCheck: "capture query shape and explain"
owner: "incident commander"
mitigation: "not applied"
verificationGates:
  - "application p95 below SLO"
  - "business result counts correct"
  - "no new MongoDB errors"
~~~

Populate metrics with genuine observed numbers—never invent figures for reporting. Use your organization's incident tracker/ticket system instead of YAML if one already exists.

## 9. Evidence Source Priority Order

A low-risk sequence:

1. Existing dashboards: traffic, errors, latency, CPU, disk, connections, replica lag.
2. App/driver logs, deployment events, tracing spans.
3. MongoDB logs scoped by time window.
4. State-reading commands: `hello`, `rs.status`, `serverStatus`, and configs.
5. Bounded query/index inspection with `explain`.
6. Scoped, time-boxed profiler/`currentOp` when genuinely required.
7. Canary tests or approved configuration changes.
8. Remediation, failover, or rollback with approved runbook, authority, and impact review.

### 9.1. Do Not Enable Cluster-Wide Profiling Reflexively

The profiler writes extra records and adds performance overhead; profiling levels, `slowms`, and sample rates must suit current load and security policies.

### 9.2. Never Pull "All Logs Forever"

Constrain the time range and relevant members; focus on logs around T0 ± an appropriate window. Huge log dumps slow analysis and raise PII exposure risk.

## 10. Gathering Evidence in the Application

Key signals:

- Request rate and endpoint mix.
- Error rate by exception class/status code.
- p50/p95/p99 latency, queue times, and timeout counts.
- Concurrent request count and thread pool saturation.
- Database operation durations from APM spans.
- Driver connection acquisition wait time.
- Server selection failures, network resets, auth/TLS errors.
- Retry counts and timeout budgets.
- Timestamps of deployments, config changes, and secret rotations.

### 10.1. Separate Application Time from MongoDB Time

API p95 = 3s does not prove `mongod` spent 3s running queries. 2.8s may have been spent waiting for a connection or an upstream dependency.

### 10.2. Never Log Full Queries Containing Personal Data

Log **query shape**, collection, operation type, duration, and trace ID; mask sensitive values. Avoid logging raw auth tokens or payment details.

### 10.3. Trace Both a Healthy Request and a Failing Request

Compare pre- and post-deploy app behavior, individual phases, and downstream calls. Never generalize from a single outlier trace to the entire fleet.

## 11. Java Driver: Error Taxonomy

Distinct error categories carry distinct meanings:

| Group | Likelihood | What to inspect |
| --- | --- | --- |
| Server selection timeout | Cannot find a server matching read/write preference | Topology, DNS, elections, network |
| `MongoSocketException` | Connection/network failure | Network, TLS, server resets |
| `MongoSecurityException` or auth failure | Credentials/roles/auth config issue | Secret rotation, `authSource` |
| `MongoWriteConcernException` | Write acknowledgment did not meet requirements | Replication/majority, disk |
| Duplicate key error | Unique index violated | Business keys, concurrency |
| `MongoCommandException` | Server returned a command error code | Error code, privileges, semantics |
| Connection acquisition timeout | Pool could not dispense a connection in time | Pool usage/queue, slow ops |

Exact exception names/capabilities depend on driver version. Always preserve **error class/code** and context, not merely truncated messages.

### 11.1. A Timeout Does Not Prove a Write Never Executed

A network timeout can occur after the server applied a write while the response was lost. Business-layer retries require idempotency and reconciliation to avoid double writes.

### 11.2. Retryable Writes Have Limits

The driver supports automatic retries for qualifying operations and topologies, yet it does not make multi-collection workflows or external side effects automatically exactly-once.

## 12. Quickly Gathering Topology via `mongosh`

Connect using an appropriate **read-only/monitoring** account. Commands:

~~~javascript
// Server currently contacted:
db.adminCommand({ hello: 1 });

// Version and selected server details:
db.version();

// Monitoring status, requires suitable privilege:
db.adminCommand({ serverStatus: 1 });
~~~

### 12.1. `hello` Reflects One Node or Router

`hello` returns role/`isWritablePrimary`/secondary status, hosts, `setName`, and topology metadata. Output via `mongos` differs from connecting directly to `mongod`.

### 12.2. Never Assume One Node Represents the Cluster

One healthy node does not prove the rest of the replica set or shards are healthy. Sample across the right scope.

### 12.3. Prefer Telemetry Platforms

Atlas, Cloud Manager, Ops Manager, or existing observability stacks retain history **before T0**; a `mongosh` command at the current moment only gives a point-in-time snapshot.

## 13. Reading `serverStatus` in Context

Example projecting selected fields when authorized:

~~~javascript
const s = db.adminCommand({ serverStatus: 1 });

printjson({
  host: s.host,
  process: s.process,
  uptime: s.uptime,
  connections: s.connections,
  opcounters: s.opcounters,
  network: s.network,
  mem: s.mem
});
~~~

### 13.1. Counters Are Typically Cumulative

Many `serverStatus` metrics are cumulative counters since process startup rather than instantaneous QPS/rates. Take two samples separated by an interval and compute delta/time.

### 13.2. Uptime and Restarts

If counters reset abruptly, check `uptime` and process restarts before concluding traffic dropped. A restart also wipes in-memory counter history.

### 13.3. Connections Do Not Equal Active Requests

Many open connections do not imply high active operations; pools hold idle connections. Compare current/available/active counts and driver pool telemetry for your version.

### 13.4. WiredTiger Fields Vary by Version

Never hardcode automation against every internal field across releases. Keep raw samples and version-aware mappings.

## 14. Collecting `mongod`/`mongos` Logs

Depending on deployment:

~~~text
Linux + systemd:
  journalctl -u mongod --since "2026-11-14 10:00:00 UTC"
  journalctl -u mongod --until "2026-11-14 10:10:00 UTC"

Kubernetes:
  kubectl logs <pod-name> --since=30m --timestamps
  kubectl logs <pod-name> --previous --timestamps

Managed MongoDB:
  Atlas / Ops Manager log and metrics download
~~~

These are examples only: service units, pod names, and containers depend on your environment. In Kubernetes, retrieving logs may require specifying the container and namespace and verifying RBAC.

### 14.1. Search Signals Matching Symptoms

- Elections, stepdowns, and topology transitions.
- Slow operations and query shapes.
- Authentication or TLS failures.
- Spikes in connection creation/closure.
- Checkpoint, storage, or I/O errors.
- Too many open files or disk errors.
- Transaction and write concern errors.
- Sharding migration or router errors.

### 14.2. Never Filter Logs by a Single Keyword Alone

Pre- and post-T0 faults may log different wording. Filter by incident window, component IDs, and request/correlation IDs.

### 14.3. Retention and Privacy

Logs can contain namespaces, query parameters, hostnames, sensitive data, or payloads. Store and share strictly according to access controls.

## 15. Fetching In-Memory Logs When Appropriate

MongoDB provides a command to read part of its in-memory log buffer (depending on version, privileges, and deployment):

~~~javascript
db.adminCommand({ getLog: "global" });
~~~

### 15.1. The Buffer Is Not Full History

It retains only a bounded slice of recent logs and overwrites older entries. For historical analysis, rely on log files and observability archives.

### 15.2. Never Rely on a Single Log Source

Correlate host/system logs and application traces to see how faults propagate from storage or replication up to APIs.

## 16. Inspecting Running Operations with `currentOp`

Snapshot currently executing operations when authorized:

~~~javascript
db.currentOp();
~~~

Or via the `$currentOp` aggregation stage where topology and permissions allow:

~~~javascript
db.getSiblingDB("admin").aggregate([
  {
    $currentOp: {
      allUsers: true,
      localOps: true
    }
  },
  {
    $project: {
      opid: 1,
      ns: 1,
      secs_running: 1,
      op: 1,
      waitingForLock: 1
    }
  },
  { $limit: 50 }
]);
~~~

### 16.1. `currentOp` Is a Point-in-Time Snapshot

An operation can finish right before you run the command. Seeing zero slow queries in `currentOp` does not prove no slow queries occur.

### 16.2. Never Expose Raw Commands

Running operations can contain query values. Sanitize sensitive fields before pasting into incident tickets.

### 16.3. Never Kill Operations Arbitrarily

`killOp` can disrupt transactions, trigger application retries, and compromise business correctness. Require authorization, owner/impact alignment, and a dedicated runbook.

## 17. Database Profiler: Use with Caution

The profiler writes operation records to `system.profile` when enabled at the configured level.

Check the current profiling level:

~~~javascript
db.getProfilingStatus();
~~~

Read existing entries:

~~~javascript
db.system.profile.find(
  {},
  {
    ts: 1,
    millis: 1,
    ns: 1,
    planSummary: 1
  }
).sort({ ts: -1 }).limit(20);
~~~

### 17.1. Never Enable Profiling Level 2 in Production Out of Habit

Logging every operation adds overhead and captures sensitive data. When profiling is necessary, bound scope, duration, sampling, and approval.

### 17.2. Slow Query Logging Also Carries Overhead

MongoDB configures slow operation log thresholds differently across environments and versions. Assess load overhead before lowering thresholds.

### 17.3. The Profiler Does Not Replace Application Tracing

Slow server execution alone does not account for time spent across network hops, driver pools, or application queues.

## 18. Slow Queries: Measure with `explain`

Example query with `tenantId` + `status` + `createdAt`:

~~~javascript
db.bookings.find({
  tenantId: "tenant-a",
  status: "PAID"
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20).explain("executionStats");
~~~

Focus on:

- `winningPlan`.
- `COLLSCAN`, `IXSCAN`, `FETCH`.
- Blocking `SORT` if present.
- `nReturned`.
- `totalKeysExamined`.
- `totalDocsExamined`.
- `executionTimeMillis`.
- Filter, sort, projection, and index definitions.

### 18.1. Quick Ratio Heuristic

If `totalDocsExamined` is vastly higher than `nReturned`, the query may be scanning far more documents than necessary. However, certain aggregations or selective predicates require evaluating exact query semantics.

### 18.2. Explain Is Not End-User Latency

Explain can influence planning/measurement and excludes network latency, app queues, serialization, and live production concurrency. Always pair it with real metrics.

### 18.3. Never Run Unbounded Explain on Heavy Queries

Keep filters, time ranges, and limits tightly scoped in production, and use representative staging environments for heavier tests.

## 19. Gathering Index Evidence

Read-only commands:

~~~javascript
db.bookings.getIndexes();

db.bookings.aggregate([
  { $indexStats: {} }
]);
~~~

### 19.1. `$indexStats` Is a Signal, Not Absolute Proof

Counters reset on restart or reflect unrepresentative windows. An index lightly used over a few hours is not automatically safe to drop.

### 19.2. Candidate Index from Access Patterns

For equality on `tenantId`/`status` and sorting on `createdAt` desc, `_id` desc:

~~~javascript
// Candidate index; do not create on production
// without approved change and impact assessment.
{
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
}
~~~

### 19.3. Index Creation Is a Write/DDL Change

An index build consumes CPU, memory, storage, and I/O and can impact live workloads. Execute strictly under change management.

### 19.4. Query Plan Regressions

A release altering a field, collation, data type, or sort order can render an existing compound index unusable even though the index remains intact.

## 20. Queries Slow Down Because Data Shapes Changed

Common causes:

- `createdAt` written as a string instead of BSON Date.
- `price` mixing String, NumberInt, and Decimal128 inconsistently.
- Queries targeting a nested field path different from actual documents.
- Unanchored regexes unable to leverage indexes cleanly.
- `$in` passed an oversized array.
- `$lookup` lacking indexes on foreign keys.
- Deep pagination using large `$skip` offsets.
- Large arrays inflating multikey index entries.
- Aggregations grouping/sorting over overly broad datasets.

### 20.1. Check Schema Drift Before Adding Indexes

If a field is missing or mistyped, adding an index sometimes merely papers over the symptom. Find out why the writer produced malformed data.

### 20.2. Correlate with Application Releases

A DTO or codec mapping change can alter queried BSON types, causing plan mismatches even when stored documents haven't changed.

## 21. Connection Pool Exhaustion

Typical symptoms:

- Requests time out waiting for a MongoDB connection.
- Pool wait queue depth grows.
- Active connections hover near the pool cap.
- Slow operations hold checked-out connections longer.
- Surging concurrency or leaked cursors/sessions.

### 21.1. Never Just Raise `maxPoolSize`

If slow queries hold connections longer, enlarging the pool piles more load onto `mongod` and worsens contention.

### 21.2. Separate Client Pool from Server Connections

`serverStatus.connections` gives the server perspective; acquisition wait times normally require driver instrumentation or APM telemetry.

### 21.3. Hypotheses

- Pool is undersized for sustained concurrency.
- Higher query latency holds connections longer.
- Application constructs a fresh `MongoClient` per request.
- Connections fail to return due to lifecycle, cursor, or session leaks.
- Network/TLS handshakes slow down connection establishment.

### 21.4. Verification

After remediation, pool wait p95 drops, error rates fall, server CPU/IO stay healthy, and end-to-end SLOs recover.

## 22. Server Selection Timeout: Never Assume `mongod` Is Down

The Java driver selects servers based on topology, read preference, write requirements, and server discovery.

Possible causes:

- No primary available when a write is required.
- Incorrect or stale DNS SRV/hostnames.
- TLS certificate or hostname verification failures.
- Firewall rules or network packet loss.
- Driver cannot reach advertised member hostnames.
- Replica set name or config mismatch.
- Read preference requires a secondary, yet none qualifies.
- Server selection timeout set shorter than normal failover duration.

### 22.1. Capture Driver Topology Events

Server description changes, heartbeat failures, and selection errors separate network reachability faults from elections.

### 22.2. Test Connectivity from the Application Environment

Connecting smoothly via `mongosh` from a developer laptop does not prove pods inside a private subnet can reach replica set members.

### 22.3. Never "Fix" by Disabling TLS

Disabling TLS or hostname validation just to restore connectivity introduces severe security risks and hides misconfigured networks or certificates.

## 23. Replica Set: Information to Gather

When connected appropriately with proper permissions:

~~~javascript
rs.status();
rs.conf();
db.adminCommand({ hello: 1 });
rs.printSecondaryReplicationInfo();
~~~

Some helpers do not apply on `mongos` or managed deployments; use the corresponding official monitoring interfaces.

### 23.1. Observe Member State

- `PRIMARY`.
- `SECONDARY`.
- `STARTUP`/`STARTUP2`/`RECOVERING`/`ROLLBACK` and related states.
- Health and heartbeat timestamps/messages.
- Election term and primary transitions.
- `optime` / last applied / durable op times.
- Replication lag and sync source.

### 23.2. Cross-Check Multiple Members

A single status snapshot from one member may be incomplete. Correlate logs/metrics across members alongside network events at the same timestamp.

### 23.3. Never Use `rs.reconfig(force)` to "Experiment"

Forced reconfiguration risks data loss or serious consistency divergence. Only run official recovery procedures led by qualified owners.

## 24. Elections and Majority Quorum

A replica set needs a **voting majority** under its active configuration to maintain or elect a primary.

~~~text
Voters = 3
Majority = floor(3/2) + 1 = 2

One voter lost:
  Remaining 2 can still form a majority,
  assuming network connectivity and eligible primary.

Two voters lost:
  Remaining 1 lacks majority.
~~~

### 24.1. Primary Transitions Briefly Interrupt Writes

Client retries, topology rediscovery, and election timing govern recovery duration. Never assume "having secondaries" means zero write interruption.

### 24.2. Election Ability Differs from Write Durability

Election majority and `"majority"` write concern are related, yet do not guarantee every acknowledged write is safe if special topology constraints go unrecognized.

### 24.3. Arbiters Store No Data

A PSA topology with an arbiter carries trade-offs for majority write availability and durability. Never mistake an arbiter for a data copy.

## 25. Replication Lag and Write Concern

Symptoms:

- Secondary reads return stale data.
- `w:"majority"` writes slow down or time out.
- Secondaries cannot keep up with write throughput.
- Lag spikes after batch jobs, migrations, or network issues.

### 25.1. Collect Evidence Over Time

Record primary/secondary optimes, write rates, I/O/CPU, network metrics, oplog window, and backlog. One lag spike alone is not enough to identify the cause.

### 25.2. A Write Concern Error Does Not Prove the Write Failed

The write may have already applied without accumulating enough acknowledgments in time; client outcomes require idempotent verification by business operation ID.

### 25.3. Read Preference and Read Concern

Queries reading from `SECONDARY` can see stale state without an appropriate consistency contract. Verifying read-your-writes requires examining read preference, read concern, and causal/session semantics.

### 25.4. Never Lower Write Concern Just to Silence Alerts

Switching `majority` to `w:1` alters durability guarantees. Any change requires data-risk evaluation, RPO review, and formal approval.

## 26. Oplog Window and Secondary Recovery

If a secondary falls too far behind or stays offline too long, it can outrun the available oplog history.

### 26.1. Observations to Collect

- Oplog window size and trend.
- Secondary applied and durable optimes.
- Write rates and workload bursts.
- Storage and network health.
- Initial sync and recovery logs.

### 26.2. Do Not Look at a Single Lag Number Alone

Large lag can stem from node downtime, network issues, or I/O bottlenecks. Evaluate it alongside the oplog window and member position.

### 26.3. Rebuilds/Resyncs Carry Operational Risk

Never blindly wipe data files or restart nodes to trigger initial sync. Evaluate quorum, capacity, disk headroom, and backups/DR first.

## 27. Sharded Clusters: `mongos`, Shards, and Config Servers

In a sharded cluster, requests flow through `mongos` to shards. A hotspot on one shard can slow only specific tenants or query shapes.

Appropriate observation commands when authorized:

~~~javascript
sh.status();
db.adminCommand({ listShards: 1 });
~~~

Connect to `mongos` for sharding helpers and metadata; Atlas and managed deployments also expose dedicated telemetry dashboards.

### 27.1. Key Questions

- Is one shard slow or all shards slow?
- Do queries include shard-key equality to target the right shard?
- Is one large tenant creating a hotspot?
- Were chunk migrations or balancer runs active at T0?
- Is the config server replica set healthy?
- Are `mongos` routers facing CPU, network, or connection saturation?

### 27.2. Scatter-Gather

Queries lacking shard-key targeting fan out across multiple shards. Never assume adding more shards automatically speeds up scatter-gather queries.

### 27.3. Balancer and Resharding

Never disable the balancer or move chunks manually as a first reflex. Gather metrics, assess impact, and follow version-appropriate runbooks.

## 28. Storage: WiredTiger, Cache, and Disk I/O

Slow APIs often point to storage rather than the query planner.

Observe:

- Host CPU, load average, and CPU throttling.
- Memory pressure, swap usage, and OOM kills.
- Free disk space, latency, IOPS, and queue depth.
- WiredTiger cache utilization and eviction pressure.
- Checkpoint activity and write throughput.
- Storage errors in logs.
- Container storage caps and volume health.

### 28.1. Disk Full Is a Data Incident, Not Just Latency

When disk fills up, MongoDB writes and checkpoints fail. Never manually delete storage files or the journal to "free space."

### 28.2. Filesystem and Volume

Check host and persistent volume free space at the exact data and log mount points, rather than checking an unrelated filesystem on the same machine.

### 28.3. Swap and OOM

Restarting after an OOM kill may temporarily restore service without resolving the underlying memory leak or misconfiguration.

### 28.4. Metrics Need a Baseline

80% cache utilization does not automatically mean "bad cache." Compare eviction activity, I/O latency, page faults, workload patterns, and version-specific guidance.

## 29. Reading Host/Container Metrics

Non-destructive observation commands:

~~~text
Linux:
  df -h
  free -m
  uptime
  iostat -x (if available)
  vmstat 1 (bounded observation)

Kubernetes:
  kubectl top pod ...
  kubectl describe pod ...
  kubectl get events ...
~~~

### 29.1. Right Host and Right Time Window

Low CPU at T+20 minutes does not disprove CPU saturation at T0. Check historical telemetry whenever available.

### 29.2. Care in Container Environments

Container cgroup limits can trigger CPU throttling or OOM kills even when the underlying host still shows free resources.

### 29.3. Avoid Excessive Diagnostic Load

Routine metric reads are low-risk, yet aggressive sampling or massive log dumps can worsen an already overloaded cluster.

## 30. Locking, Tickets, and Contention

MongoDB and WiredTiger manage sophisticated concurrency controls. When operations stall:

- Inspect operation queues and latencies.
- Identify long-running transactions or reads.
- Check hot-write documents alongside lock/ticket metrics.
- Inspect ticket/wait counters for your version.
- Check concurrent batch, DDL, or index build jobs.

### 30.1. One Hot Document

If thousands of requests update a single counter document concurrently, lock/ticket contention rises even though each update is atomic.

### 30.2. Long-Running Transactions

Long transactions hold resources open, elevating memory, replication, and storage pressure. Never kill a transaction blindly without knowing its business side effects and retry handling.

### 30.3. Do Not Call Every Delay a Lock

Pool wait, network latency, storage queues, and server scheduling can look identical at the API boundary. Break duration down layer by layer.

## 31. Transactions and Write Failures

Multi-document transactions can report transient transaction errors or unknown commit outcomes.

### 31.1. Preserve Error Labels and Codes

Log exception class, error labels, command category, sanitized transaction/session context, and exact timestamps.

### 31.2. Never Blindly Retry Whole Business Workflows

A payment capture or booking confirmation must never execute twice simply because a MongoDB response timed out. Use idempotency keys, stable business IDs, and reconciliation.

### 31.3. Long Transactions Are the Wrong Model

If a workflow waits on end users or external payment providers, never hold a MongoDB transaction open across the external wait.

## 32. Wrong Data: Isolating Correctness Issues

Some incidents never show up on CPU or latency charts:

- Documents linked to the wrong tenant.
- Negative inventory after concurrent decrements.
- Overlapping double bookings.
- Payment totals summed twice.
- Missing records after a migration.
- APIs reading from stale secondaries.
- An older/newer schema reader misinterpreting fields.
- Backfills overwriting fresher CDC events.

### 32.1. Identify the Source of Truth

Ask which store is canonical: application state, booking ledger, payment provider, legacy SQL, or a specific MongoDB collection?

### 32.2. Evidence Must Include Invariants

Counts by tenant/status, sums by currency, uniqueness constraints, version progression, event ID deduplication, foreign references, and availability overlap checks.

### 32.3. Never Run Mass Corrective Updates Before Isolating the Cause

Bulk-modifying production records before proving root cause can erase forensic evidence and compound data drift.

## 33. Example of Wrong Data Caused by Read Preference

Workflow:

~~~text
T0: write status=PAID to primary
T1: immediate read from secondary
T2: secondary replication catches up
~~~

The read at T1 can still observe `PENDING` if read preference and read concern allow stale reads.

### 33.1. Do Not Jump to "The Write Was Lost"

Inspect write acknowledgments, read preference, read concern, causal sessions, and primary/secondary optimes.

### 33.2. Business SLOs Dictate Consistency Choices

When read-your-writes is required, the application must use proper session/read strategies rather than crudely sleeping on the client.

### 33.3. Stale Caches Can Produce Identical Symptoms

If the MongoDB primary already holds `PAID` yet the API still serves `PENDING`, check Redis, CDN, application caches, and event projection lag.

## 34. Authentication, Authorization, and TLS

Connection failures right after secret rotation often trace to:

- Out-of-sync passwords/credentials across pods.
- Wrong `authSource` or username.
- Expired client certificates or untrusted CA chains.
- TLS hostname mismatches.
- Changed IP allowlists or firewall rules.
- Roles lacking privileges on new collections or commands.

### 34.1. Collect Security Logs Safely

Record error codes/classes, certificate expiry metadata, service versions, and secret version labels; **never** paste passwords or private keys into incident notes.

### 34.2. Never Switch to an Admin Account to Test Directly

Confirming admin credentials work does not prove the application's least-privilege role works. Test with a principal matching production permissions.

### 34.3. Never Disable Security Just to Read Errors Easier

Turning off TLS or auth in production to "isolate causes" introduces critical risk. Use controlled certificate and network checks instead.

## 35. Symptom → Measurement Routing Table

| Symptom | Primary hypothesis | Discriminating evidence |
| --- | --- | --- |
| API p95 up, MongoDB execution time up | Query/index/storage | Explain, slow logs, CPU/IO |
| API p95 up, MongoDB looks fine | Pool/queue/network/app | Traces, pool waits, thread pools |
| Intermittent write timeouts | Elections/network/write concern | `rs.status`, logs, acknowledgments |
| Stale secondary reads | Replication lag/read preference | Optimes, read concern, app config |
| One collection slow | Missing index/data skew | Query plan, cardinality |
| One shard overloaded | Shard-key hotspot/fan-out | Per-shard metrics, targeted queries |
| All ops slow, disk latency high | Storage pressure | Host I/O/WiredTiger metrics |
| Only new app release fails | Driver/codec/config regression | Version split, logs, request shapes |
| Spike in duplicate key errors | Retries/upserts/identity bugs | Unique indexes, request IDs |
| Mismatched totals post-migration | Transform/CDC ordering | Watermarks, grouped counts, hashes |
| Rising 401/auth errors | Secret/TLS/auth changes | Auth logs, cert and role metadata |
| High connections, pool waits | Pool pressure or leaks | Driver metrics, query durations |
| Repeated DB restarts | OOM/disk/system events | Host logs, uptime, container events |

This table only helps **prioritize hypotheses**. One incident may involve multiple concurrent causes or cascading effects.

## 36. Ranking Hypotheses

Evaluate each hypothesis against:

1. Does it fit the time window?
2. Does it explain the exact blast radius?
3. Does it align with the architecture?
4. Is there independent supporting evidence?
5. Is there contradicting evidence?
6. Is the next verification step low-risk?
7. If confirmed, is remediation reversible?

Template:

~~~yaml
hypothesisId: H2
statement: "Pool wait drives API latency"
predictions:
  - "driver acquisition wait increased"
  - "MongoDB server op time did not increase similarly"
evidenceFor:
  - E10
evidenceAgainst:
  - E12
nextCheck: "compare pool metrics by app pod/version"
confidence: "medium"
status: "open"
~~~

### 36.1. Never Inflate Confidence from Repeated Log Lines

One fault emitting 1,000 identical log lines does not equal 1,000 independent pieces of evidence.

### 36.2. Disconfirming Evidence Is Highly Valuable

If all app pods execute the same query yet failures hit only one AZ, a cluster-wide missing index becomes far less likely; check AZ networking/routing instead.

## 37. Low-Impact Verification Experiments

Priority order:

1. Compare the failing release against the healthy release.
2. Compare affected tenants/endpoints against unaffected ones.
3. Run tightly scoped read-only query `explain` checks.
4. Replay sanitized queries in staging with representative data.
5. Route canary traffic or isolate one service instance if supported.
6. Apply one approved config/index/app change and measure before/after.
7. Consider high-impact/destructive measures only with complete evidence.

### 37.1. Design Falsifiable Tests

For example, "an index will fix latency" predicts `totalDocsExamined` and p95 will drop once the plan shifts to the right `IXSCAN`; if latency stays high, investigate network or serialization next.

### 37.2. One Variable at a Time

When external traffic shifts make freezing every variable impossible, record exact timestamps of every action and external event to avoid misattribution.

### 37.3. Never Load-Test Directly Against an Overloaded DB

Even read-only replays burn CPU and I/O. Use staging or tightly rate-limited canaries.

## 38. Controlled Remediation Decisions

Before changing anything, document:

~~~text
CHANGE:
  What exactly changes?

EVIDENCE:
  Which hypothesis supports the change?

BLAST RADIUS:
  Which services/members/tenants could be affected?

DURABILITY:
  Could this change alter writes, read concern or RPO?

ROLLBACK:
  How to revert without losing committed data?

OBSERVABILITY:
  Which metrics must improve?

OWNER:
  Who approves and executes?

STOP CONDITION:
  When to abort the change?
~~~

### 38.1. Reversible Before Irreversible

Rolling back an application release is usually less invasive than forcing a replica set reconfiguration. Still verify code rollbacks stay compatible with schema changes or newer writes.

### 38.2. Preserve Evidence

Capture needed configs, metrics, and logs before restarting whenever feasible, without unreasonably delaying urgent restoration just to gather extra logs.

### 38.3. Never Trade Durability for Green Metrics

Lowering write concern, disabling auth, or reading from stale secondaries is a reliability/behavior change—never an "innocent timeout tweak."

## 39. Post-Fix Verification: Four Layers

A command returning success **does not** mean the incident is over.

| Layer | What to verify | Examples |
| --- | --- | --- |
| Infrastructure | Nodes/pods/disk/network stable | No restart loops, disk headroom |
| MongoDB | Topology/ops/lag/queries healthy | Primary intact, secondaries caught up, low errors |
| Application | SLOs/errors/connection pool recovered | p95, 5xx, pool waits, retries |
| Business/data | Invariants, records, side effects valid | No double bookings, accurate totals |

### 39.1. Maintain an Observation Window

Monitor continuously after the change across relevant traffic peaks and cycles rather than declaring victory off one clean request. Duration follows SLO and incident owner sign-off.

### 39.2. Match Baseline Conditions

If post-fix traffic dropped 90%, lower latency proves nothing about the root cause. Compare at equivalent traffic or run controlled replays.

### 39.3. Check Originally Unaffected Workloads

Adding an index or tweaking configs can speed up one endpoint while slowing writes or backups. Check adjacent workloads for regressions.

## 40. Setting Measurable Acceptance Criteria

Example gates—**draw real numeric thresholds from your SLOs** rather than treating placeholders as universal rules:

~~~yaml
verification:
  application:
    - "error rate below agreed threshold"
    - "p95 latency within SLO for representative load"
    - "pool acquisition waits normalized"
  mongodb:
    - "healthy primary and intended secondaries"
    - "replication lag within team threshold"
    - "no new storage/auth/network errors"
    - "query plan matches expected access pattern"
  data:
    - "business counts and totals reconcile"
    - "no duplicate booking or stock invariant violation"
    - "committed operations not silently lost"
  operations:
    - "alerts stable through observation window"
    - "rollback procedure still available"
~~~

### 40.1. Every Gate Needs an Owner and Timestamp

Never write just "looks stable." Record who verified, when, and which metric source/evidence IDs support it.

### 40.2. SLO Recovery Often Precedes Root-Cause Closure

Mitigation stops user pain quickly, yet postmortem and permanent root-cause action items must still be tracked to completion.

## 41. Example 1: Booking Feed Suddenly Slows Down

**Context:** `GET /bookings?status=PAID` p95 spikes right after a release.

### 41.1. Symptoms

- Only the list endpoint is slow.
- `_id` booking lookups stay fast.
- Query rate and `documentsExamined` jump.
- Recent deploy altered sort/ordering logic.

### 41.2. Gather Evidence

~~~javascript
db.bookings.getIndexes();

db.bookings.find({
  tenantId: "tenant-a",
  status: "PAID"
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20).explain("executionStats");
~~~

### 41.3. Hypothesis

The query no longer aligns with an index supporting both equality filters and the sort clause, causing heavy scans/sorts as the collection grows.

### 41.4. Verify and Remediate

Compare pre- and post-release query shapes and indexes. Once confirmed, either roll back the query change or add an approved **candidate** compound index. Example:

~~~javascript
// DDL proposal only — requires approved change:
db.bookings.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
});
~~~

### 41.5. Verification

- Representative `explain` switches to the expected index plan.
- `totalDocsExamined`/`nReturned` drops sharply if the hypothesis held.
- API p95 under equivalent traffic returns within SLO.
- Write latency and index storage impact stay acceptable.
- Result IDs and pagination stay accurate.

### 41.6. Do Not Conclude Too Early

Never declare "root cause solved" solely because the index shows up in `explain`. If p95 stays elevated, investigate connection pools, network, serialization, and data skew.

## 42. Example 2: Write Errors During an Election

**Context:** numerous writes fail with server selection errors over a brief window.

### 42.1. Gather Evidence

- App logs: exact error class, time window, affected pods.
- Driver topology and heartbeat events.
- `rs.status()` and member logs.
- Platform events: node restarts, network/AZ faults.
- Majority voter reachability.
- Retries/timeouts alongside business operation IDs.

### 42.2. Competing Hypotheses

H1: Normal primary election triggered after maintenance.

H2: Network partition prevented members from holding majority.

H3: App pods could not reach advertised hostnames after topology change.

H4: Server selection timeout configured shorter than a routine failover.

### 42.3. Discriminate

If the replica set already holds a healthy primary while app pods in only one AZ fail to connect, examine DNS/networking from that AZ rather than altering MongoDB election configs.

### 42.4. Mitigation and Verification

Once topology stabilizes, verify writes receive expected acknowledgments, app errors drop, retries caused zero duplicates, and secondaries catch up.

### 42.5. Avoid Dangerous Commands

Never run force `rs.reconfig`, wipe data directories, or issue repeated `rs.stepDown` calls to experiment. That risks extra elections or data loss.

## 43. Example 3: Slow API While `mongod` Metrics Look Normal

**Context:** API p95 jumps, yet server-side query durations show minimal change.

### 43.1. Evidence to Gather

- Did driver pool acquisition wait time jump?
- Are JVM threads blocked or pausing for GC?
- Is code instantiating a fresh `MongoClient` per request?
- What are `maxPoolSize` and concurrent request counts?
- Are DNS/TLS handshakes slow?
- Are other upstream calls timing out?

### 43.2. Test the Hypothesis

Compare end-to-end trace spans of a slow request against MongoDB server execution time. If most duration sits in pool acquisition wait, adding indexes is the wrong priority.

### 43.3. Remediation Path

Fix client lifecycle, pool sizing, or long-running operations holding connections. Any `maxPoolSize` adjustment must match server capacity rather than scaling blindly.

### 43.4. Verification

Pool wait drops, p95 returns to baseline, server load remains controlled, and peak concurrency executes cleanly.

## 44. Example 4: Replication Lag and Stale Reads

**Context:** right after payment confirmation, the booking page occasionally still shows `PENDING`.

### 44.1. Evidence

- Write result and write concern used.
- Endpoint read preference.
- Secondary optime/lag around the read timestamp.
- Cache or read-model staleness.
- Payment and booking event ordering.

### 44.2. Hypothesis

Reads hit a secondary before it applied the write, or API caches were not invalidated. Never assume the write was lost before inspecting the primary state.

### 44.3. Remediation Path

Select a read strategy or session consistency providing read-your-writes; fix cache invalidation or reduce underlying lag. Avoid `Thread.sleep(1000)` hacks as a general fix.

### 44.4. Verification

Immediately after an acknowledged write, the consistency-critical read path reflects the new state per contract without duplicate side effects from retries.

## 45. Example 5: Disk Pressure Unstabilizing Writes

**Context:** MongoDB write latency and host disk latency climb as volume free space runs low.

### 45.1. Evidence

- Free space and depletion slope.
- Host volume IOPS and latency.
- WiredTiger checkpoint metrics.
- MongoDB storage errors/logs.
- Running backups, retention, or maintenance jobs.
- Growth breakdown across collections, indexes, and logs.

### 45.2. Controlled Handling

Evaluate storage scaling and approved retention/archival policies. Never delete journal or data files manually, and never run `mongod --repair` as step one.

### 45.3. Verification

Disk headroom returns, I/O latency and checkpoint behavior normalize, writes acknowledge reliably, secondaries avoid falling behind, and backup/restore readiness holds.

## 46. Example 6: Post-Migration Data Drift

**Context:** MongoDB monetary totals disagree with legacy SQL totals after a backfill/CDC run.

### 46.1. Evidence

- Source snapshot or CDC watermark.
- Document counts by tenant, status, and date.
- Monetary sums by currency.
- Duplicate business IDs.
- Source log sequence vs. target applied versions.
- Quarantined or failed transform records.

### 46.2. Hypotheses

- Backfill used wrong numeric types.
- Replayed CDC events summed totals twice.
- Stale backfill overwrote newer CDC updates.
- Baselines compared two unaligned timestamps.
- Timezone conversion shifted records across day boundaries.

### 46.3. Never Compare Total Document Counts Alone

Two collections with identical counts can still mismatch on tenant IDs, amounts, or statuses.

### 46.4. Remediation and Verification

Fix transformation logic and idempotent event ordering, replay from the authoritative source, and reconcile at a matching watermark. Validate both new and historical records before closing the incident.

## 47. Verifying Business Correctness

Example invariants:

~~~text
Booking:
  No overlapping active reservations for the same vehicle
  State transitions follow allowed paths

Inventory:
  Available quantity is never negative
  Reservations are not counted twice

Payment:
  Provider event IDs are not applied twice
  Sum of ledger entries matches authoritative records

Multi-tenant:
  No booking/customer association crosses tenant boundary

Migration:
  Counts, monetary totals and statuses reconcile
  with the same source snapshot / watermark
~~~

### 47.1. Align Snapshot/Timepoints

Never compare SQL at 10:15 against MongoDB updated up to 10:10 and label the gap corruption.

### 47.2. Verify Records After Retries/Timeouts

A request suffering a network timeout may still have committed. Reconcile via idempotency keys and business IDs to eliminate duplicate writes.

### 47.3. Never Use `countDocuments()` as Sole Proof

Equal counts miss swapped amounts or corrupted tenants. Verify business aggregates and deep record-level spot comparisons.

## 48. Fixing Root Causes vs. Masking Symptoms

| Action | When it genuinely helps | Risk if misused |
| --- | --- | --- |
| Roll back app release | Newly deployed regression | Schema compatibility or newer writes |
| Create compound index | Query plan lacks access path | Index build load and write overhead |
| Tune pool settings | Real demand/capacity mismatch | Amplified pressure on `mongod` |
| Scale resources | Proven CPU/IO saturation with baseline | Merely masks a query bug |
| Change read preference | Matches consistency/availability contract | Stale reads |
| Change write concern | Approved durability/latency trade-off | Loss of durability guarantees |
| Restart member | Hung/unrecoverable process per runbook | Election churn, cold cache, lost evidence |
| Trigger resync | Secondary outran oplog under clear plan | Heavy network/disk load, quorum risk |
| Kill long op | Harmful op with verified owner/impact | Partial business state and retries |
| Delete data/indexes | Approved retention or schema change | Data loss or query regression |

Every intervention requires evidence, approval, rollback steps, and verification gates.

## 49. Post-Fix Monitoring Window

Never close an incident right after one command succeeds.

### 49.1. Milestones to Log

~~~text
T0  Impact begins
T1  Incident acknowledged
T2  Evidence captured
T3  Hypothesis confirmed
T4  Mitigation applied
T5  Application SLO recovers
T6  Business invariants verified
T7  Observation window ends
T8  Root cause / follow-up tracked
~~~

### 49.2. Watch for Regressions

After adding indexes or scaling capacity, verify writes, disk, memory, replication lag, failover readiness, and unrelated endpoints.

### 49.3. If Metrics Do Not Recover

Never mark `RESOLVED` merely because the DBA command succeeded. Revisit the hypothesis tree and gather fresh evidence.

## 50. Blameless Postmortem

A thorough postmortem includes:

1. Summary of user and data impact.
2. Unified UTC timeline.
3. Facts backed by evidence IDs.
4. Trigger.
5. Root cause and contributing factors.
6. Why detection or mitigation took as long as it did.
7. Actions executed, with expected vs. observed effects.
8. Data requiring reconciliation.
9. Preventive action items with owners and due dates.
10. Runbook, alert, and test updates needed.

### 50.1. Contributing Factors Differ from Root Cause

A slow-query deployment often coexists with missing index reviews, undersized staging datasets, and slow alerts. Capture every systemic contributor to prevent repeats.

### 50.2. Never Fabricate Root Cause Without Evidence

State "probable cause" and leave open follow-up investigations when gaps remain. Honesty about uncertainty beats a confident wrong conclusion.

## 51. Designing Alerts to Catch Evidence Early Next Time

Valuable alert groups:

- Application 5xx rate, error budget burn, and p95 latency.
- MongoDB read/write latency and slow query trends.
- Connection pool acquisition failures.
- Primary availability and election frequency.
- Replication lag and oplog window.
- Disk free space and I/O latency.
- CPU, memory, and cache eviction pressure.
- Authentication and TLS anomalies.
- Sharded cluster hotspots and migration failures.
- Business invariant and reconciliation failures.

### 51.1. Alerts Must Be Action-Oriented

An isolated "CPU=80%" alert rarely helps. Pair resource thresholds with symptom impact and duration, linked directly to dashboards and runbooks.

### 51.2. Avoid Alert Storms

Correlate and route related signals from one fault by severity. Incident commanders need clear signal, not thousands of duplicate pages.

### 51.3. Retain Historical Metrics

If metric retention is too brief, responders lose the pre-T0 baseline needed for comparison.

## 52. Initial Evidence-Gathering Checklist

1. Assigned incident ID, severity, and owners.
2. Recorded start timestamp and timezone.
3. Scoped affected users, endpoints, and tenants.
4. Captured pre-incident baseline.
5. Identified deployment/config changes near T0.
6. Collected request rates, error rates, and latency.
7. Separated application time from DB execution time.
8. Captured driver exception classes and codes.
9. Collected driver pool and server-selection metrics if available.
10. Documented topology, replica set, and shard scope.
11. Pulled `mongod`/`mongos` logs for the window.
12. Captured `serverStatus` and host CPU/memory/disk snapshots as appropriate.
13. Collected query shapes, indexes, and `explain` output for query faults.
14. Documented active read/write concerns and read preferences.
15. Checked business invariants if data correctness is suspect.
16. Tagged every piece of evidence with source, time, and scope.
17. Sanitized all secrets and PII.
18. Preserved forensic evidence without hasty destructive edits.

## 53. Root-Cause Isolation Checklist

1. Separated symptoms, observations, and hypotheses.
2. Formulated at least one competing hypothesis alongside the leading theory.
3. Defined testable predictions for every hypothesis.
4. Checked that hypothesis scope matches blast radius.
5. Checked that hypothesis timing aligns with timeline.
6. Checked client vs. server latency split.
7. Checked network/TLS/DNS on connection errors.
8. Checked query plan/indexes/schema types on query regressions.
9. Checked primary/elections/lag on replication errors.
10. Checked per-shard metrics when a sharded cluster fails partially.
11. Checked host/disk/I/O when broad operations slow down.
12. Checked deployment, codec, and driver regressions.
13. Avoided mistaking correlation for causation.
14. Kept diagnostic experiments bounded in impact.
15. Confirmed decision ownership prior to high-impact remediation.

## 54. Post-Fix Verification Checklist

1. Documented remediation action with exact timestamp.
2. Verified rollback or forward-fix contingency remains viable.
3. Confirmed MongoDB primary and secondaries satisfy required topology.
4. Confirmed replication lag and write concern meet thresholds.
5. Verified zero new storage, network, or auth errors.
6. Verified query plans and index coverage.
7. Verified application error rates, p95/p99, and pool waits meet SLOs.
8. Confirmed comparison traffic is representative.
9. Verified critical business read/write operations succeed.
10. Confirmed zero duplicate or out-of-order effects from retries.
11. Reconciled counts, totals, and business invariants.
12. Verified zero cross-tenant data leakage.
13. Verified adjacent endpoints did not regress.
14. Confirmed alerts remain clean across the observation window.
15. Attached evidence links to each verification gate.
16. Transitioned incident status per process.
17. Assigned owners for root-cause and prevention follow-ups.

## 55. Evidence-Reading Exercises

### Exercise 1 — Symptom or Root Cause?

API p95 climbs while `mongod` CPU hits 95%. Write three distinct hypotheses and one measurement separating each.

### Exercise 2 — Timeline

Java logs are in UTC+7, `mongod` in UTC, and Kubernetes events in UTC. Normalize all timestamps onto one consistent timeline and explain clock skew hazards.

### Exercise 3 — Error Taxonomy

A request hits a server selection timeout. Name at least four possible causes beyond "MongoDB crashed."

### Exercise 4 — Driver Pool

App latency rises while server operation execution time barely moves. Design telemetry to separate pool wait time from network latency.

### Exercise 5 — Counter vs. Rate

`serverStatus` `opcounters` climbs from 10,000 to 11,200 over 60 seconds. Compute average ops/s in that window and explain why raw counters cannot be compared across restarts.

### Exercise 6 — Evidence Ledger

Draft a 6-row evidence table with timestamps, sources, facts, and hypothesis mappings for an election incident.

## 56. Query and Topology Exercises

### Exercise 7 — `COLLSCAN`

A feed returns 20 docs yet scans 500,000. Describe how to inspect filter, sort, existing indexes, and choose a candidate index.

### Exercise 8 — Blocking `SORT`

A query has a compound index `{tenantId, createdAt}`, yet filters by `status` too. Design an `explain` investigation before creating any new index.

### Exercise 9 — Query Mismatch

After a deploy, the driver begins writing `createdAt` as strings. How does that impact range queries and sorting?

### Exercise 10 — Election

Three voting members; one drops. What is the majority? What happens if a second voter drops?

### Exercise 11 — Lag

One secondary lags heavily and read preference allows reading from it. Examine read-your-writes semantics and how to prove stale reads.

### Exercise 12 — Write Concern Timeout

A write times out under `w:"majority"`. Why must you never assume the write didn't apply? Design idempotent reconciliation.

### Exercise 13 — Shard Hotspot

Only a large tenant on shard A slows down. List evidence separating a shard-key hotspot from a `mongos` connection bottleneck.

## 57. Storage, Data, and Recovery Exercises

### Exercise 14 — Disk Pressure

Free disk space drops low and checkpoint latency climbs. Write a safe runbook that never deletes journal or data files.

### Exercise 15 — OOM

A `mongod` container restarts from OOM. What telemetry must you collect before changing memory limits? Why is simply letting it restart not a root-cause fix?

### Exercise 16 — Overlapping Bookings

Two concurrent requests check for no overlap and both insert. Design a data invariant and concurrency test.

### Exercise 17 — Duplicate Payments

Webhook retries can credit a payment twice. Which event IDs, unique indexes, and totals must you verify?

### Exercise 18 — Migration Drift

Document counts match, yet monetary totals differ. Design reconciliation across tenant, date, currency, and source watermark.

### Exercise 19 — Choosing Remediation

In a query incident, compare app rollback, adding an index, enlarging the pool, and restarting `mongod` across required evidence, risks, and verification.

### Exercise 20 — Post-Fix Gates

Define explicit verification gates for APIs, database, and business data after resolving a replica election outage.

## 58. Advanced Exercises

### Exercise 21 — Causality

CPU and 5xx errors rise together after a deploy. Is that proof CPU caused the errors? Design a timeline and trace comparison.

### Exercise 22 — Read Concern

An API must read newly updated state right after writing. Identify all read preference, session, and read concern settings to check.

### Exercise 23 — `currentOp`

Checking `currentOp` shows no slow operations. Can you conclude there are no slow queries? Give three reasons why not.

### Exercise 24 — Profiler

Design a profiling plan specifying sampling, time-boxing, privileges, privacy controls, and rollback.

### Exercise 25 — Cross-Tenant Leak

A `$lookup` joins only on `customerId` and exposes another tenant's data. Design a test fixture and query fix.

### Exercise 26 — Incident Drill

Given simulated app, MongoDB, and host logs with timestamps, build an evidence ledger, rank hypotheses, and state root-cause uncertainty.

### Exercise 27 — Change Management

Write an index-addition change proposal detailing scope, expected benefit, load risk, rollback plan, and acceptance criteria.

### Exercise 28 — Postmortem

Write a blameless postmortem covering trigger, root cause, contributing factors, impact, evidence links, and action owners.

## 59. MongoDB Incident Runbook

~~~text
TRIGGER:
  Alert or user symptom

DECLARE:
  Incident ID, severity, owners, blast radius

STABILIZE:
  Protect data and service
  Use approved low-risk mitigation if urgent

CAPTURE:
  UTC timeline and recent changes
  App/driver errors, latency and traces
  mongod/mongos logs
  Topology, replica/shard status
  Host storage, CPU, memory and network
  Query shape/explain if needed

HYPOTHESIZE:
  Distinguish fact vs inference
  Rank explanations
  Define disconfirming evidence

TEST:
  Read-only diagnostics first
  Scope and timebox each check
  Avoid production load experiments

CHANGE:
  One approved remediation
  Record precise time and owner
  Maintain rollback/forward-fix option

VERIFY:
  Database health and topology
  App p95/errors/pool waits
  Business data and idempotency invariants
  Regression checks on adjacent workloads
  Stable observation window

CLOSE:
  Preserve sanitized evidence
  Record root cause and uncertainty
  Assign prevention tasks and runbook changes
~~~

## 60. Conclusion

Reliable MongoDB troubleshooting starts by **preserving evidence trails and separating interpretation from raw facts**:

- **Gather evidence** across the application, driver, network, `mongos`/`mongod`, replica set, sharding, query planner, storage, and business data with clear timestamps and sources.
- **Isolate root causes** using blast radius, unified timelines, falsifiable hypotheses, and least-invasive checks.
- **Apply controlled fixes** with clear ownership, impact review, consistency/durability protection, and rollback gates.
- **Verify recovery** across all four layers—infrastructure, MongoDB, application, and business/data correctness—never just one successful command.
- **Prevent recurrence** through historical telemetry, SLO-driven alerts, regression/concurrency testing, schema/index reviews, runbooks, and blameless postmortems.

User-facing symptoms often vanish before the root cause is confirmed. Conversely, a successful index build or process restart never guarantees business data and invariants are intact. The ultimate objective is **restoring service without compromising correctness, understanding the failure mechanism, and making the next response faster, safer, and verifiable**.

## References

- [MongoDB Manual — Monitoring](https://www.mongodb.com/docs/manual/administration/monitoring/)
- [MongoDB Manual — serverStatus](https://www.mongodb.com/docs/manual/reference/command/serverStatus/)
- [MongoDB Manual — hello](https://www.mongodb.com/docs/manual/reference/command/hello/)
- [MongoDB Manual — currentOp](https://www.mongodb.com/docs/manual/reference/command/currentOp/)
- [MongoDB Manual — Database Profiler](https://www.mongodb.com/docs/manual/tutorial/manage-the-database-profiler/)
- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Manual — Replica Set Status](https://www.mongodb.com/docs/manual/reference/method/rs.status/)
- [MongoDB Manual — Replica Set Elections](https://www.mongodb.com/docs/manual/core/replica-set-elections/)
- [MongoDB Manual — Replication Lag](https://www.mongodb.com/docs/manual/tutorial/troubleshoot-replica-sets/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Manual — Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/)
- [MongoDB Manual — Sharding](https://www.mongodb.com/docs/manual/sharding/)
- [MongoDB Manual — WiredTiger](https://www.mongodb.com/docs/manual/core/wiredtiger/)
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/)
