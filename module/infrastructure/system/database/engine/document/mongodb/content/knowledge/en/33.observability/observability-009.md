# Setting Alert Thresholds, Baselines, and Incident Investigation Workflows in MongoDB

## 1. Why MongoDB Monitoring Requires More Than a CPU Chart

Suppose MongoDB still responds to `ping`, yet users repeatedly hit timeouts when opening their order list. The root cause could be a new query skipping indexes, the Java driver exhausting its connection pool, replication lag slowing down majority writes, or one shard running much hotter than the rest.

A brief CPU spike can be harmless; conversely, low CPU does not prove the database is serving the application well. Effective monitoring must rely on **user impact**, **normal baselines**, **actionable thresholds**, and **evidence-based incident investigation workflows**.

This lesson belongs to the **Observability** chapter of the **MongoDB Document Database Engine** module, titled **Setting Alert Thresholds, Baselines, and Incident Investigation Workflows**.

After this lesson, you will be able to:

1. Distinguish monitoring, observability, alerting, and incident management.
2. Select key signal groups: latency, traffic, errors, saturation, replication, and backup readiness.
3. Build baselines by day/hour, release, workload, and individual MongoDB member/shard.
4. Design static, dynamic, relative, forecast, SLO/error-budget, and no-data thresholds.
5. Configure duration, hysteresis, deduplication, and routing to the right on-call responder.
6. Use Atlas Alerts, metrics, Query Profiler, Performance Advisor, and Real-Time Performance Panel appropriately.
7. Read `serverStatus`, `rs.status`, `rs.printSecondaryReplicationInfo`, `$currentOp`, profiler, and `explain`.
8. Diagnose query regressions, connection storms, replication lag, disk pressure, elections, and authentication failures.
9. Build incident timelines, test hypotheses, mitigate safely, verify recovery, and write postmortems.
10. Design Java driver metrics, protect sensitive data in logs/traces, and run drills.

**Core principle:** A good alert tells you what needs attention, its priority, who owns it, and links directly to a runbook. It is never merely comparing a metric to an arbitrary number.

## 2. Four Layers of an Observability System

~~~text
Application / user experience
       |
       v
Application metrics + traces + driver metrics
       |
       v
MongoDB node / replica set / shard metrics + logs
       |
       v
Baselines + SLOs + Alert rules
       |
       v
On-call / Incident response
       |
       v
Root cause + Action items + Threshold review
~~~

- **Monitoring:** tracking defined signals and current system state.
- **Observability:** the ability to explain what is happening using metrics, logs, traces, and query plans.
- **Alerting:** deciding when a condition requires human attention.
- **Incident response:** reducing impact, preserving evidence, verifying recovery, and improving the system.

No tool fully replaces another. Atlas metrics can show high disk I/O without naming the impacted API endpoint; Java tracing can pinpoint the endpoint without revealing a node lost primary status.

### 2.1. Symptoms Differ from Causes

~~~text
Users experience slow API
   |
   +--> High Java pool checkout wait
   |        |
   |        +--> Connections climbing
   |                 |
   |                 +--> Retry storm or app scale-out
   |
   +--> Query plan shifted to COLLSCAN
   |
   +--> Secondary lag, slow majority writes
   |
   +--> High disk latency
~~~

A CPU curve and a latency curve rising together show correlation only. You still need a timeline, technical mechanism, and falsifiable checks.

## 3. Golden Signals and MongoDB-Specific Dimensions

The four golden signals:

| Group | Suggested metrics | Investigative question |
|---|---|---|
| Latency | p50/p95/p99 query and API response | Are requests slower than acceptable? |
| Traffic | Requests/s, database operations/s | Is workload surging or dropping abnormally? |
| Errors | Command failures, timeouts, 5xx, auth errors | Which requests are failing? |
| Saturation | CPU, RAM/cache, IOPS, queues, tickets, connections | Which component is nearing exhaustion? |

MongoDB also requires monitoring:

- Primary availability and elections.
- Replication lag across members.
- Oplog window and secondary catch-up margin.
- WiredTiger cache, eviction, and checkpoints.
- Free disk bytes and disk latency/throughput.
- Query plans, scan ratios, and index usage.
- Imbalanced shards.
- Backup freshness and PIT restore windows.
- TLS and authentication failures.
- Change stream consumer lag if applicable.

### 3.1. Multi-Level Observation

~~~text
Business SLO
    |
    v
Service/Endpoint SLI
    |
    v
MongoClient / connection pools
    |
    v
Cluster / Replica Set
    |
    +--> Member A - PRIMARY
    +--> Member B - SECONDARY
    +--> Member C - SECONDARY
    |
    v
Per-namespace / query shape
~~~

Never rely solely on cluster-wide averages; one unhealthy secondary or hot shard can be hidden by healthy peers.

### 3.2. Client and Server Metrics Do Not Always Match

API-observed latency includes networking, DNS/TLS, server selection, queue/pool checkout, retries, BSON serialization, and business logic. Server execution time is only one slice. A healthy MongoDB server does not rule out bugs in the Java driver or network.

## 4. Reading Metric Types Properly

| Metric type | Examples | Usage |
|---|---|---|
| Gauge | `connections.current`, free disk, CPU % | Point-in-time value |
| Counter | `connections.totalCreated`, `opcounters` | Convert into rate/increase over time |
| Histogram | Duration buckets | Compute p95/p99 |
| State/Event | Primary election, node down | Detect transitions and durations |
| Derived ratio | Docs examined/returned, error rate | Guard denominators and minimum volume |

### 4.1. Counter Resets

Counters typically accumulate from process start; on restart, they reset toward 0. Never turn a negative delta into negative throughput. Telemetry backends must handle counter resets—for example, `rate()` or `increase()` in Prometheus.

### 4.2. `connections.totalCreated` Is Not Current Open Connections

- `current`: currently open incoming connections.
- `available`: remaining incoming connections the server can accept.
- `totalCreated`: cumulative connections created since process start.

A large `totalCreated` may simply reflect long uptime. A rising `rate(totalCreated)` points to connection churn.

### 4.3. p95/p99 Matter More Than Mean

Mean latency can look fine while a subset of users waits far too long. For key endpoints, track p50, p95, p99, error rate, request count, and concurrency.

### 4.4. Percentiles Need Sufficient Samples

One slow request out of three does not prove a sustained p99 degradation. Alerts need a minimum sample count or longer evaluation window.

### 4.5. Ratios When the Denominator Is Zero

`docsExamined / nReturned` is undefined if zero documents are returned. In monitoring, use conditional ratios or pair absolute examined counts with returned counts. Never turn division by zero into infinity and page on-call constantly.

## 5. What Is a Baseline?

A **baseline** captures normal workload behavior under defined conditions as a reference for comparison.

Example:

~~~text
Monday, 09:00: 1,200 queries/min
Monday, 02:00:    50 queries/min
Sunday, 09:00:   150 queries/min
~~~

Setting a single static threshold of 500 queries/min misclassifies normal daytime traffic as anomalous while missing a "traffic dropped to 0" outage at night.

### 5.1. How Long Should You Collect a Baseline?

Start with 7–28 days of normal operating history, extending further if workloads have month-end or quarter-end cycles. No single window fits all systems—it must cover full business cycles.

### 5.2. Baselines Should Be Segmented

- Hour of day and day of week.
- Peak vs. off-peak.
- Region and cluster tier.
- Application and endpoint.
- Query shape.
- Primary vs. secondary.
- Before vs. after deployments.
- Scheduled batch or backfill windows.
- Tenant tier or workload class, avoiding high cardinality.

### 5.3. Incident Data Must Never Become the New Normal

A week containing a 10x slow-query incident must not automatically pull a dynamic baseline upward and mask future incidents. Label incident windows and protect baselines from drift during investigations.

### 5.4. Events That Invalidate Baselines

Review baselines after:

- Major MongoDB version upgrades.
- Adding/dropping indexes or changing schemas.
- Tier, hardware, or storage upgrades.
- Sharding or resharding.
- Application or query shape changes.
- Multi-fold traffic or data growth.
- Region or network migrations.
- New batch workloads.

## 6. Sample Baseline Table

All values below are **fictional exercise data**, not MongoDB defaults.

| Metric | Segment | p50 | p95 | p99 | Window |
|---|---|---:|---:|---:|---|
| API read latency | Orders peak | 30 ms | 90 ms | 160 ms | 4 weeks |
| API read latency | Orders off-peak | 20 ms | 60 ms | 110 ms | 4 weeks |
| Pool checkout wait | Orders API | 3 ms | 20 ms | 45 ms | 4 weeks |
| Secondary lag | rs0 node B | 0.2 s | 1.1 s | 2.5 s | 4 weeks |
| Query duration | get-open-orders | 8 ms | 30 ms | 60 ms | 4 weeks |

Example baseline metadata:

~~~yaml
baselineId: mongo-orders-prod-2026w46
windowStartUtc: 2026-10-17T00:00:00Z
windowEndUtc: 2026-11-14T00:00:00Z
cluster: orders-prod
releaseRange: orders-2026.10
excludedIncidents:
  - INC-2026-041
owner: platform
~~~

This is custom governance YAML, **not** direct MongoDB configuration.

### 6.1. Never Store Only Averages

Store quantiles, distributions, QPS, error rates, timestamps, and system versions. Keeping only "average CPU 55%" makes it hard to tell if 90% CPU at peak is normal.

## 7. Static Thresholds

Static thresholds fit clear technical or business boundaries:

~~~text
Warning: disk used > 80% for 10 minutes
Critical: disk used > 92% for 5 minutes
~~~

Pros: simple to understand and audit.

Cons: prone to false positives across shifting workloads; a steady 82% disk is less urgent than a 76% disk growing 5% per hour.

### 7.1. Pair with Time-to-Exhaustion Forecasts

~~~text
Estimated time to full =
    disk_free_bytes / estimated_growth_bytes_per_second
~~~

This is a simple forecast formula; guard against zero or negative growth rates instead of dividing blindly. Forecasts should account for confidence, seasonality, and minimum bounds.

### 7.2. Never Apply One CPU Threshold to Every Node

An analytics node may run high CPU by design, while a transactional primary can degrade even at low CPU due to I/O, locks, or tickets. Base severity on business impact.

## 8. Dynamic / Baseline-Relative Thresholds

Example rule:

~~~text
observed_p95_ms > max(200, 2 * baseline_p95_ms)
for 10 minutes
AND request_count_5m >= 100
~~~

If baseline is 80 ms, the threshold becomes 200 ms; if baseline is 300 ms, the threshold becomes 600 ms.

This is **illustrative logic only**. Validate 200 ms, 2x, and 10 minutes against actual SLOs and data.

### 8.1. Combine Absolute Floors with Relative Multipliers

If baseline p95 is 2 ms, doubling to 4 ms rarely warrants a page—an absolute floor prevents noise. If baseline is 500 ms, a 200 ms floor would fire constantly—a relative multiplier keeps the rule sensible.

### 8.2. Time-of-Week Baselines

Compare Monday 09:00 query latency against prior Mondays at 09:00 rather than against quiet midnight hours with completely different QPS.

### 8.3. Never Let Baselines Learn Ongoing Incidents

If a dynamic baseline keeps adapting to the last 30 minutes while an incident remains unresolved, it raises "normal" until the alert resolves itself. Freeze or exclude incident samples.

## 9. Duration, Hysteresis, and Anti-Flapping

An alert flapping on and off destroys on-call trust.

### 9.1. Minimum Duration

~~~text
Alert ON:
  CPU > 85% continuously for 10 minutes

Do not page for a 5-second spike.
~~~

However, events like losing the primary or data corruption require near-instant notification; tune duration by impact type.

### 9.2. Hysteresis

~~~text
Alert ON:
  disk used > 90% for 5 minutes

Alert OFF:
  disk used < 82% for 15 minutes
~~~

Using separate trigger and resolution thresholds prevents flapping.

### 9.3. Deduplication and Alert Grouping

A single primary election can trip multiple signals: no primary, driver timeouts, replication errors, API 5xx. Group alerts by incident or cluster instead of paging on-call 20 times.

### 9.4. Maintenance Windows

Tag planned maintenance to suppress expected noise, while still detecting severe issues such as data loss, prolonged unavailability, or broken backups.

### 9.5. No-Data Is a State to Monitor

If an exporter or Atlas integration stops sending metrics, a silent dashboard does **not** mean healthy services. Alert on last-sample age, exporter health, and alert delivery failures.

## 10. SLOs, SLIs, and Error Budgets

Resource metrics do not directly measure customer experience. Example SLO:

~~~text
Over 30 days, at least 99.9% of order-listing requests:
- succeed
- and complete within 200 ms
~~~

- **SLI:** proportion of requests meeting the criteria.
- **SLO:** target for the SLI.
- **Error budget:** allowable fraction of failing/slow requests.
- **Burn rate:** rate of budget consumption relative to the allowed pace.

### 10.1. Burn Rate Example

If an SLO permits 0.1% bad requests, yet the last 5 minutes saw 1% bad requests, the burn rate is roughly 10x.

Paging purely on 1-minute windows is noisy; paging purely on 24-hour windows is too slow. **Multi-window burn rates** pair short and long windows to determine severity.

### 10.2. Linking DB Metrics to SLOs

Example:

~~~text
API p99 breaches SLO
    |
    +--> MongoDB query duration rises
    +--> Docs examined per returned rises
    +--> Disk/CPU also rise
~~~

This evidence chain is far stronger than "CPU > 80%." Still check traces and deployment events to confirm causality.

## 11. MongoDB Metric Groups to Collect

| Group | Metrics | Risk |
|---|---|---|
| Availability | Node state, primary availability, elections | Read/write unavailability |
| Replication | Secondary lag, applied optime, oplog window | Stale reads, resync |
| Throughput | Opcounter rates, operation rates | Traffic surge or drop |
| Query | Duration p95/p99, docs/keys examined, `nReturned` | Query regression |
| Connections | Current, available, `totalCreated` rate, rejected | Connection exhaustion |
| Memory | WiredTiger cache, eviction, OS swap | Cache pressure |
| CPU | Process CPU, host CPU | Saturation |
| Disk | Capacity, IOPS, latency, disk queue | Full disk, slow I/O |
| Tickets/queues | Available tickets, queued operations | Backpressure |
| Sharding | Per-shard load, chunk distribution | Hot shard |
| Reliability | Backup freshness, PIT window, restore drills | Recovery risk |
| Security | Authentication failures, TLS errors | Credential or network issues |

Exact field names and availability vary by MongoDB version, Atlas tier, exporter, and storage engine. Never assume every metric exists identically across all deployments.

### 11.1. Per-Node Visibility Is Essential

A cluster averaging 50% CPU can hide Shard A at 95% and Shard B at 5%. A severely lagging secondary can be masked by average replication lag. Inspect every host, member, and shard.

## 12. Sample Threshold Matrix

**All figures are illustrative starting points, not mandatory MongoDB thresholds.**

| Event | Example Warning | Example Critical |
|---|---|---|
| Primary unavailable | Unscheduled state transition | Write availability lost beyond SLO |
| Secondary lag | >5s for 5 minutes | >30s for 3 minutes |
| Oplog window | <24h | Below expected recovery downtime |
| Disk used | >80% and rising quickly | >90% or very short time-to-full |
| CPU | >85% for 10 minutes | >95% for 5 minutes with latency impact |
| Query p95 | >2x baseline and above floor | Sustained SLO violation |
| Connections | Available drops sharply | Rejected / checkout timeouts rising |
| Queues | Sustained above baseline | Rising queues paired with degraded p99 |
| Errors | Rising above baseline | Burn rate exceeds P1/P2 limit |
| Backup | Past verified backup schedule | No recovery point meeting RPO |

### 12.1. Base Severity on Impact

P1 covers write outages, potential data loss, or broad user impact. P2 covers significant degradation with workarounds. P3 covers capacity warnings addressable during business hours. Formalize exact definitions within your organization.

### 12.2. Combine Cause and Symptom

92% disk need not page urgently if stable with planned headroom; 78% disk climbing rapidly may warrant urgent action. SLOs, growth rate, runbooks, and remediation paths determine severity.

## 13. Atlas Alerts and Notifications

MongoDB Atlas supports alert conditions, thresholds, notification channels, and default project-level alerts. Operators configure alerts per project or organization according to assigned roles.

Workflow:

1. Select project and cluster.
2. Inspect baselines under Metrics/Monitoring.
3. Open Alerts / Alert Settings.
4. Pick conditions/metrics matching the cluster type.
5. Set thresholds, durations, and routing.
6. Attach owners and runbooks per internal incident processes.
7. Verify notification delivery.
8. Review false positives and missed incidents periodically.

### 13.1. Free/Flex vs. Dedicated Observability

Atlas Free/Flex supports only tier-appropriate metrics and alert conditions. Real-Time Performance Panel requires M10+. Query Profiler and Performance Advisor also depend on deployment tier and configuration.

Never assume screenshots or menus from one tier match every other tier.

### 13.2. Tickets/Queues Alerts from Atlas Docs

Atlas Alert Basics recommends alerting when **available tickets drop** or **queues climb** for several minutes to filter out transient spikes. Tune Atlas example numbers to your workload, server version, and metric definitions.

### 13.3. Notifications Are Only the Delivery Layer

Alerts route via email, webhooks, and supported Atlas integrations. Incidents still require acknowledgment, escalation, ownership, status updates, and runbooks.

## 14. Atlas Query Profiler, RTPP, and Performance Advisor

Atlas tools complement one another:

- **Query Profiler:** finds slow queries by time, namespace, duration, docs examined/returned, and index efficiency.
- **Real-Time Performance Panel:** near real-time operations, network, and hardware view (requires M10+).
- **Performance Advisor:** analyzes slow queries and recommends indexes and query improvements.
- **Sharding Insights:** inspects workload and chunk distribution on supported sharded clusters.

### 14.1. Performance Advisor Does Not Replace Index Reviews

A new index increases storage and write amplification, may overlap existing indexes, or alter query plans. Check workload mix, cardinality, and rollout impact before applying to production.

### 14.2. Query Profiler Can Expose Sensitive Information

Profilers and logs hold query shapes and metadata that can expose business details. Enforce access controls, retention limits, and redaction before sharing outside the team.

### 14.3. Correlate with Change Events

Plot p99 and query shapes alongside releases, index builds, scaling, and backups. Preceding events provide strong clues, though not standalone proof of causality.

## 15. Self-Managed MongoDB: `serverStatus`

With an appropriately privileged monitoring account:

~~~javascript
const s = db.adminCommand({ serverStatus: 1 });

printjson({
  host: s.host,
  uptime: s.uptime,
  connections: s.connections,
  opcounters: s.opcounters,
  network: s.network
});
~~~

Output and fields vary across MongoDB versions, node roles, and storage engines.

### 15.1. Connections

~~~javascript
s.connections.current;
s.connections.available;
s.connections.totalCreated;
~~~

MongoDB 6.3 adds `connections.rejected`. Newer versions may add queue and connection-establishment metrics. When building collectors, check field existence and server version.

### 15.2. Network and `opcounters`

~~~javascript
s.network.bytesIn;
s.network.bytesOut;
s.network.numRequests;

s.opcounters;
~~~

These are typically cumulative counters. Convert to rates and compare against application throughput; never treat cumulative `bytesIn` as bytes/s.

### 15.3. Uptime Resets Are Key Signals

If `uptime` drops low, the node likely restarted. When multiple counters reset together, inspect restart, election, and host logs before concluding traffic dropped.

## 16. WiredTiger Cache, Eviction, and Disk I/O

WiredTiger intentionally uses RAM for caching. High cache occupancy **does not by itself prove memory starvation**.

Example reading version-dependent fields:

~~~javascript
const s = db.adminCommand({ serverStatus: 1 });
const cache = s.wiredTiger && s.wiredTiger.cache;

if (cache) {
  printjson({
    bytesInCache: cache["bytes currently in the cache"],
    maximumBytes: cache["maximum bytes configured"],
    dirtyBytes: cache["tracked dirty bytes in the cache"]
  });
}
~~~

Verify exact field names against `serverStatus` on your running MongoDB/WiredTiger version.

### 16.1. Signals More Useful Than "90% Cache Used"

- Eviction activity and application threads performing eviction.
- Dirty pages and checkpoints.
- Disk read/write latency.
- OS swap and memory pressure.
- Query p95/p99.
- Working set shifts.
- Read/write ticket availability.

### 16.2. Full Disk vs. Slow Disk

Disk used measures **capacity**; disk latency and IOPS measure **performance**. High disk latency can occur even with plenty of free space.

### 16.3. Never Delete WiredTiger Files to Free Space

Manage MongoDB data and journal files strictly through MongoDB commands and runbooks. Deleting files directly on the filesystem causes data loss and corruption.

## 17. Tickets, Queues, and Flow Control

MongoDB/WiredTiger versions expose available read/write tickets, queue depths, and flow control metrics. Match metric names to your actual server version and Atlas tier.

A sound alert combines:

~~~text
Available tickets low
AND queue depth rising
AND p99 latency rising
for 5 minutes
~~~

Never page on a single transient ticket dip.

### 17.1. Flow Control Relates to Replication

Flow control throttles primary writes when majority commit lag grows too high so secondaries do not fall further behind. If write latency rises alongside high lag, inspect secondary disks, network, and flow control instead of blindly expanding pools.

### 17.2. Oversized Connection Pools Can Worsen Overload

Raising pool size from 100 to 500 per app instance amplifies queuing when the database is already saturated. Identify the bottleneck and enforce backpressure and concurrency limits.

## 18. Replica Sets and Replication Lag

Key signals:

- Is there a `PRIMARY`?
- Are members healthy and maintaining majority?
- How far behind are secondaries?
- Is the oplog window wide enough for expected downtime?
- Are elections repeating?
- Is majority write latency rising?

### 18.1. Checking via `mongosh`

~~~javascript
rs.status();
rs.printSecondaryReplicationInfo();
rs.printReplicationInfo();
~~~

- `rs.status()`: topology, member states, optimes, heartbeat/election context.
- `rs.printSecondaryReplicationInfo()`: secondary replication lag summary.
- `rs.printReplicationInfo()`: oplog size and retained time window.

In scripts, use `db.getReplicationInfo()` for structured output.

### 18.2. Oplog Window Is Time, Not Just Gigabytes

The oplog window depends on write rate. When writes surge, the same oplog size retains a shorter history.

~~~text
Oplog window: 8 hours
Secondary offline: 12 hours
=> Risk that secondary cannot catch up via oplog.
~~~

MongoDB documentation recommends sizing the oplog to cover expected secondary unavailability—commonly at least ~24 hours, with many production systems choosing 72 hours or longer depending on recovery needs.

### 18.3. Monitor Each Member Individually

One secondary lagging 30 seconds and another at 0.5 seconds must not be averaged into "normal cluster lag" if the application reads from the lagging node.

### 18.4. Never Change `writeConcern` Just to Mask Symptoms

If majority writes slow down due to secondary lag, arbitrarily weakening `writeConcern` alters durability guarantees. Evaluate impact and remediate per approved runbooks.

## 19. Primary Elections

Elections can stem from maintenance, node failures, network splits, resource stalls, or unexpected restarts.

Signals to check:

- Primary transition timestamps.
- Heartbeat failures.
- `rs.status()` member states.
- Node uptime and restarts.
- Driver `NotPrimary` or server selection timeouts.
- Replication health and quorum.
- DNS, TLS, and network errors.
- Atlas event and maintenance calendars.

### 19.1. Planned vs. Unplanned

A brief planned failover where clients retry cleanly is an informational event. Prolonged primary loss or repeated elections causing write failures is an incident.

### 19.2. Avoid Arbitrary Topology Changes

`rs.stepDown()`, `rs.reconfig()`, and restarting multiple members simultaneously can extend outages. Protect quorum and require approval and runbooks.

## 20. Sharded Clusters and Hot Shards

A cluster might show:

~~~text
Shard A: CPU 90%, p99=1200ms
Shard B: CPU 30%, p99=100ms
Cluster average CPU: 60%
~~~

The average hides Shard A's saturation.

Investigate:

- Load per shard and per member.
- Do queries include the shard key predicate?
- Are queries triggering scatter-gather?
- Chunk distribution and jumbo chunks.
- Balancer and migration events.
- Index consistency across shards.
- Hot tenants or partitions.
- Query `explain` via `mongos`.

Never jump into resharding during an active incident without assessing resource cost, side effects, and rollback.

## 21. Query Plans and `explain`

Sample query:

~~~javascript
db.orders.find({
  tenantId: "tenant-A",
  status: "OPEN"
}).sort({
  createdAt: -1
}).explain("executionStats");
~~~

Inspect:

- Winning plan and stages.
- `totalDocsExamined`.
- `totalKeysExamined`.
- `nReturned`.
- `executionTimeMillis`.
- `COLLSCAN` vs. `IXSCAN`.
- Any blocking sort stage.
- Index name and bounds.

### 21.1. `IXSCAN` Does Not Guarantee Optimality

An index can still scan hundreds of thousands of keys to return a handful of documents. Check the examined-to-returned ratio and latency.

### 21.2. `COLLSCAN` Is Not Always Bad

A collection with four documents scans faster without an index. On a high-traffic real-time endpoint over a large collection, `COLLSCAN` is usually problematic.

### 21.3. Lab `explain` Does Not Replace Load Testing

Execution stats depend on data size, cache state, concurrency, and query plans. Never extrapolate production p99 from a single lab `explain` run's `executionTimeMillis`.

## 22. `$currentOp` for Inspecting Running Operations

With appropriate monitoring privileges:

~~~javascript
db.getSiblingDB("admin").aggregate([
  {
    $currentOp: {
      allUsers: true,
      localOps: true
    }
  },
  {
    $match: {
      active: true,
      secs_running: { $gte: 5 }
    }
  },
  {
    $project: {
      opid: 1,
      ns: 1,
      desc: 1,
      secs_running: 1,
      waitingForLock: 1
    }
  },
  { $limit: 30 }
]);
~~~

`$currentOp` must be the first stage. `allUsers: true` requires privileges such as `inprog` when authentication is enabled. Use only properly authorized monitoring accounts.

### 22.1. `$currentOp` Is Not Full History

Completed operations disappear from current operations. Use slow logs, Query Profiler, or the database profiler for historical investigation.

### 22.2. Do Not Kill Operations Impulsively

`db.killOp()` can disrupt transactions, migrations, and admin tasks. Before terminating, confirm owner, scope, impact, and approval.

## 23. MongoDB Database Profiler

The profiler writes operation records to a per-database capped collection named `system.profile`.

| Level | Meaning |
|---|---|
| 0 | Does not write profiler entries |
| 1 | Writes slow operations or filter-matched operations |
| 2 | Writes all profilable operations |

MongoDB warns that profiling impacts performance and disk usage, especially at level 2 or with very low thresholds.

### 23.1. Testing on a Self-Managed Lab

~~~javascript
use observability_lab

db.getProfilingStatus();

db.setProfilingLevel(1, {
  slowms: 200,
  sampleRate: 0.1
});
~~~

This changes runtime state. Depending on version, `slowms` and `sampleRate` can affect the whole process and diagnostic logs, not just the current database. Record initial settings before changing anything.

### 23.2. Inspecting Sample Slow Operations

~~~javascript
db.system.profile.find(
  { millis: { $gte: 200 } },
  {
    ts: 1,
    ns: 1,
    millis: 1,
    planSummary: 1,
    keysExamined: 1,
    docsExamined: 1
  }
).sort({ ts: -1 }).limit(20);
~~~

Enforce permissions and retention on profile data; avoid exporting raw `command` payloads if they contain PII.

### 23.3. Disabling After Investigation

~~~javascript
db.setProfilingLevel(0);
~~~

Remember to restore prior `slowms` and `sampleRate` values if changed. Never assume `setProfilingLevel(0)` resets every parameter automatically.

### 23.4. `mongos` Does Not Have a Database Profiler Like `mongod`

MongoDB does not support enabling the database profiler on `mongos`. You can tune slow-operation logging per documentation, but `mongos` has no `system.profile`.

## 24. `$queryStats`: Useful, Yet Requires Caution

On supported environments and versions:

~~~javascript
db.getSiblingDB("admin").aggregate([
  { $queryStats: {} },
  { $limit: 10 }
]);
~~~

Notes:

- `$queryStats` runs on `admin` as the first pipeline stage.
- The MongoDB Manual currently notes feature caveats (**unsupported** status in some contexts / output format not guaranteed stable across releases).
- On Atlas, documentation specifies a minimum M10 tier.
- Requires the `queryStatsRead` privilege, included in `clusterMonitor`.
- Query-shape stats reside in memory with version-dependent sampling and caps.
- Never rely on its output as the sole source of truth during incidents.

### 24.1. When to Consider It

Use it to group frequent query shapes, compare execution patterns, and find costly workloads. Always cross-check with app metrics, logs, and Query Profiler.

### 24.2. Why Not Build Alerts on Fixed Field Paths?

The `$queryStats` schema changes across MongoDB releases. If a collector hardcodes specific field paths, upgrades can break alerts silently. Prefer supported integrations and version-compatibility tests.

## 25. Java Driver Monitoring

Java applications should instrument:

- Connection checkout wait.
- Connection creation and closure.
- Server selection time.
- Command duration and failures.
- Retry counts.
- Pool utilization.
- Query shapes/operation names without logging sensitive literals.
- API latency and error rates.

### 25.1. Safe `CommandListener` Example

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.event.CommandFailedEvent;
import com.mongodb.event.CommandListener;
import com.mongodb.event.CommandStartedEvent;
import com.mongodb.event.CommandSucceededEvent;

import java.util.concurrent.TimeUnit;

class SafeMongoListener implements CommandListener {
    @Override
    public void commandStarted(CommandStartedEvent e) {
        // Log only command name; never log e.getCommand().
        System.out.println("Mongo started: " + e.getCommandName());
    }

    @Override
    public void commandSucceeded(CommandSucceededEvent e) {
        System.out.println("Mongo succeeded: "
            + e.getCommandName() + " in "
            + e.getElapsedTime(TimeUnit.MILLISECONDS) + "ms");
    }

    @Override
    public void commandFailed(CommandFailedEvent e) {
        System.out.println("Mongo failed: "
            + e.getCommandName() + " in "
            + e.getElapsedTime(TimeUnit.MILLISECONDS) + "ms");
    }
}

// Place inside initialization and supply URI via a secret manager.
MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(mongoUri))
    .addCommandListener(new SafeMongoListener())
    .build();

MongoClient client = MongoClients.create(settings);
~~~

`mongoUri` is an application variable loaded from secure configuration. Never print the URI (which may contain passwords) to logs. `System.out` is used for simplicity; production services should export sampled, cardinality-bounded metrics.

### 25.2. Fast Server, Slow Application

If server query execution p95 is 20 ms while API p95 is 800 ms, check pool checkout, network, DNS, TLS, retries, and application code before adding indexes.

## 26. Query Shapes and Telemetry Security

Logs, traces, and profiler data can contain:

- Full query literals.
- Emails, phone numbers, names, or user IDs.
- MongoDB connection URIs carrying credentials.
- Document payloads.
- Internal database and collection names.
- Network topology.

Principles:

1. Never log passwords, tokens, or private keys.
2. Redact or hash sensitive values.
3. Attach metric labels by query shape, never per user or document.
4. Use TLS for telemetry pipelines.
5. Restrict retention and access to logs/profiler data.
6. Audit access to incident evidence.
7. Avoid full collection exports just for debugging.
8. Enforce policies on data sent to third-party vendors.

Avoid alerts like:

~~~text
Slow query: email=customer@example.test, token=secret
~~~

Instead:

~~~text
Query shape: customers-by-email
Namespace: appdata.customers
p99 duration: 1.4s
Docs examined: high
Trace ID: abcd...
~~~

## 27. Representing a Rule as Pseudo-Config

~~~yaml
id: mongo-orders-p95-query
service: orders-api
cluster: orders-prod
severity: warning
window: 5m
minimumRequests: 100
condition: "p95 > max(200ms, 2 x baseline_p95)"
duration: 10m
resolutionCondition: "p95 < max(160ms, 1.5 x baseline_p95)"
resolutionDuration: 15m
notify:
  - orders-oncall
  - db-platform
runbook: "https://internal.example.test/runbooks/query-regression"
~~~

This is a custom pseudo-specification, **not** native MongoDB Atlas YAML config.

### 27.1. Illustrative PromQL Example

If your application exports a custom `app_mongodb_command_duration_seconds_bucket` histogram:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, service) (
    rate(app_mongodb_command_duration_seconds_bucket[5m])
  )
)
~~~

This metric is not automatically exported by MongoDB; your instrumentation must emit it.

## 28. Incident Investigation Flow

~~~text
DETECT / ALERT
       |
       v
ACK + ASSIGN OWNER
       |
       v
MEASURE USER IMPACT
       |
       v
PRESERVE EVIDENCE
       |
       v
BUILD HYPOTHESES
       |
       v
MITIGATE SAFELY
       |
       v
VERIFY RECOVERY
       |
       v
POSTMORTEM + ACTIONS
~~~

### 28.1. Prioritize Impact Before Root Cause

Ask:

- How many users or requests are affected?
- Which endpoints, regions, and tenants?
- Is there data loss, stale reads, or failed writes?
- When did the incident begin?
- Is there a safe workaround or rollback?
- Should severity or escalation be raised?

You do not need the complete root cause before starting safe mitigation.

### 28.2. Record UTC Timestamps

~~~text
10:02:13Z  Deploy orders-api v3
10:04:00Z  API p95 rises
10:04:20Z  Docs examined rises
10:06:00Z  Alert fired
10:07:10Z  On-call ACK
10:12:00Z  Canary rollback
10:14:00Z  p95 returns to baseline
~~~

### 28.3. Evidence Differs from Hypothesis

- **Observation:** query p95 jumped 5x.
- **Hypothesis:** the new deploy introduced an unindexed query.
- **Evidence:** new query shape appeared, `explain` showed `COLLSCAN`, canary rollback restored latency.
- **Conclusion:** strong evidence linking the query change to the regression.

Never write "MongoDB broke because of the release" from a single chart line alone.

## 29. Incident Roles and Communication

| Role | Responsibility |
|---|---|
| Incident Commander | Coordinates response and priorities |
| DB/Platform Operator | Investigates MongoDB, executes approved mitigations |
| Application Owner | Assesses user impact, adjusts releases or traffic |
| Communications | Updates stakeholders |
| Scribe | Records timeline and evidence |
| Security | Engages on suspected attacks or data exposure |

Small incidents may combine roles. What matters is clear ownership so responders do not run conflicting commands.

### 29.1. Writing Good Status Updates

State affected scope, confirmed symptoms, active mitigations, unknowns, and next-step owner. Never post passwords or PII in incident chat.

### 29.2. Production Changes During Incidents Must Be Traced

Record command/action, operator identity, approval, UTC timestamp, and result. High-risk actions like `rs.reconfig()`, `rs.stepDown()`, `killOp`, or dropping indexes require prior risk review.

## 30. Runbook A — Post-Release Query Regression

**Symptoms:** Query p95/p99 climbing, examined/returned ratio rising, API timeouts.

1. Measure impact by endpoint and tenant.
2. Check the release and change calendar.
3. Compare query shapes in Query Profiler or slow logs.
4. Run `explain("executionStats")` on an equivalent query.
5. Check for `COLLSCAN`, index name, examined/returned counts, and blocking sorts.
6. Assess whether other workloads are affected.
7. With supporting evidence, roll back the canary/release or shed batch load.
8. Evaluate new indexes under change control—avoid building heavy indexes rashly on an already overloaded cluster.
9. Verify p95/p99 and errors return to baseline.
10. Add performance regression tests and shape-level alerts.

**Never** jump to conclusions from `IXSCAN` or `COLLSCAN` alone without checking data volume and latency.

## 31. Runbook B — Connection Storm

**Symptoms:** connection checkout timeouts, `connections.current` surging, `available` dropping, `totalCreated` rate climbing.

~~~javascript
const s = db.adminCommand({ serverStatus: 1 });
printjson(s.connections);
~~~

Check:

- App instance count and pool `maxPoolSize`.
- Recent app autoscale or deploy events?
- Driver connection creation rate.
- Rejected connections (where field is supported).
- TLS handshake, DNS, or network failures.
- CPU, memory, and queues.
- Any active retry storm?

For instance, 20 pods configured with max pool 100 represent a theoretical ceiling of 2,000 pooled connections—**not** a guarantee that 2,000 sockets are constantly open.

Mitigation: stagger rollouts/autoscaling, curb connection churn, tune pool sizes, enforce retry backoff/jitter, and check DB capacity; avoid restarting all app pods simultaneously.

## 32. Runbook C — Secondary Replication Lag

~~~javascript
rs.status();
rs.printSecondaryReplicationInfo();
rs.printReplicationInfo();
~~~

Gather:

- Which member(s) are lagging?
- Did primary write rate spike?
- Are secondary CPU, disk, or network saturated?
- How much oplog window remains?
- Are index builds, backups, restarts, or initial syncs running?
- How did flow control and majority write latency change?

Mitigation: throttle non-essential bulk writes, resolve secondary/network bottlenecks, scale if needed, and confirm lagging members recover before touching other nodes.

Never weaken `writeConcern` blindly to hide lag; doing so alters durability guarantees.

## 33. Runbook D — Disk Pressure

Monitor:

- Free disk bytes and time-to-full.
- Disk latency, IOPS, and throughput.
- Growth by database and collection.
- WiredTiger cache, dirty bytes, and checkpoints.
- Active backups, index builds, and batch jobs.
- Host and OS storage errors.

Mitigation: scale storage cleanly, throttle abnormal write workloads, inspect temp files/logs, and clean up via safe tools. Never delete WiredTiger or journal files directly.

Verify disk headroom and stable query latency with no corruption or new replication lag.

## 34. Runbook E — Unexpected Primary Elections

Check:

- `rs.status()` and member states.
- Heartbeat and election logs.
- Host restarts, OOM events, or disk stalls.
- DNS, TLS, and network paths.
- Majority quorum.
- Driver retries and server selection errors.
- Maintenance and change events.

A planned election where apps retry cleanly is not a P1 incident. Repeated elections and prolonged primary loss require urgent response.

Never run `rs.stepDown()` or `rs.reconfig()` without verifying quorum and rollback plans.

## 35. Runbook F — Authentication / TLS Failures

Symptoms: MongoDB `AuthenticationFailed`, auth code 18, TLS handshake exceptions.

Investigate:

- Recent password or secret rotation.
- Have pods picked up the updated secret version?
- `authSource` and authentication mechanism.
- Special-character URI encoding.
- TLS certificate expiry, SANs, and CA chain.
- IP access lists and network endpoints.
- Signs of brute force or compromised credentials.
- Whether driver/client pools must be recycled.

TLS handshake failures happen below SCRAM; authorization failures mean authentication succeeded but privileges are missing. Never assume every connection error is a wrong password.

## 36. Mini Lab: Observing Indexes and Queries

Create a test database:

~~~javascript
use observability_lab

db.orders.insertMany([
  {
    _id: 1,
    tenantId: "tenant-A",
    status: "OPEN",
    amount: 120,
    createdAt: ISODate("2026-11-01T08:00:00Z")
  },
  {
    _id: 2,
    tenantId: "tenant-A",
    status: "CLOSED",
    amount: 400,
    createdAt: ISODate("2026-11-02T08:00:00Z")
  },
  {
    _id: 3,
    tenantId: "tenant-B",
    status: "OPEN",
    amount: 90,
    createdAt: ISODate("2026-11-03T08:00:00Z")
  },
  {
    _id: 4,
    tenantId: "tenant-A",
    status: "OPEN",
    amount: 250,
    createdAt: ISODate("2026-11-04T08:00:00Z")
  }
]);
~~~

### 36.1. `explain` Before Adding an Index

~~~javascript
db.orders.find({
  tenantId: "tenant-A",
  status: "OPEN"
}).sort({ createdAt: -1 })
  .explain("executionStats");
~~~

### 36.2. Create Index and Re-Compare

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1
  },
  {
    name: "idx_tenant_status_createdAt"
  }
);
~~~

Re-run `explain`. With just four documents, the planner may still choose `COLLSCAN` because the dataset is tiny. This is a syntax exercise, not a performance benchmark.

### 36.3. Profiler Status Before and After

~~~javascript
db.getProfilingStatus();
~~~

Enable level 1 only in an authorized lab, save initial configuration, and restore it after the exercise.

## 37. End-to-End Diagnostics with a Java Client

A lightweight health check:

~~~java
import com.mongodb.client.MongoClient;
import org.bson.Document;

public class MongoReachability {
    public static boolean canReachServer(MongoClient client) {
        try {
            Document result = client.getDatabase("admin")
                .runCommand(new Document("ping", 1));
            return ((Number) result.get("ok")).doubleValue() == 1.0;
        } catch (RuntimeException ex) {
            // Record redacted metrics/traces at the caller layer.
            return false;
        }
    }
}
~~~

**`ping` does not replace business readiness.** It does not prove queries are indexed, transactions succeed, or p99 meets SLOs. Health checks must stay lightweight rather than running heavy queries just to test status.

### 37.1. Bound Retries

Exponential backoff, jitter, deadlines, and circuit breakers prevent retry storms. Unlimited retries when MongoDB is already saturated worsen outages.

## 38. Case Study: A Release Increasing Scanned Documents

Assumed baseline:

~~~text
API p95: 80ms
MongoDB query p95: 25ms
Docs examined / returned: 4
CPU: 45%
Secondary lag: <1s
~~~

After deploy:

~~~text
API p95: 700ms
MongoDB query p95: 500ms
Docs examined / returned: 20,000
CPU: 85%
Secondary lag: ~1s
~~~

Investigation chain:

1. API SLO alert fired.
2. Query duration and examined ratio climbed.
3. Replication lag stayed flat, deprioritizing replication causes.
4. Query Profiler surfaced a new shape.
5. `explain` on the new shape revealed a suboptimal plan.
6. Release diff confirmed a changed filter/sort.
7. Controlled rollback returned p95 to baseline.
8. Added index/query review to the deployment pipeline.

This solidly establishes a **release-induced query regression**, far stronger than simply claiming "MongoDB CPU is high."

## 39. Postmortems and Root-Cause Analysis

A postmortem should cover:

| Section | Content |
|---|---|
| Impact | Affected users, endpoints, duration, data |
| Timeline | Events in UTC |
| Trigger | What initiated the chain |
| Contributing factors | Conditions that amplified impact |
| Detection | Which alert fired, and how fast/slow |
| Mitigation | Actions that reduced impact |
| Recovery verification | When SLOs stabilized |
| Prevention | Action items with owners and due dates |

### 39.1. The Trigger Is Not the Whole Root Cause

The trigger was deploying a new query; contributing factors included unrepresentative staging data, missing index review, no load tests, and CPU-only alerts.

### 39.2. Action Items Must Be Measurable

Do not write "monitor better." Write:

- Add load testing for query shape `list-open-orders` prior to release.
- Alert on p95 by endpoint and DB query shape.
- Enforce index review for new queries.
- Document a query-regression runbook.
- Run quarterly canary rollback drills.

### 39.3. Reviewing Alert Quality

- Did the alert fire before customers reported errors?
- Were there chronic false positives?
- Were any incidents missed?
- Did dashboards provide enough evidence?
- Could recipients act on the alert?
- Were metrics ever missing because an exporter went down?

## 40. Governance for Threshold Changes

Raising a CPU alert from 90% to 99% just to stop alerts firing **masks symptoms** rather than solving anything.

Threshold changes require:

1. Baseline and observed metrics.
2. Associated SLOs.
3. Recent alert/incident history.
4. Old vs. new thresholds.
5. Duration and hysteresis settings.
6. Approving owner.
7. Review date and rollback plan.

Example registry entry:

~~~yaml
alertId: mongo-orders-disk-growth
version: 3
owner: platform-oncall
signal: disk-time-to-full
window: 7d-trend
threshold: less-than-14-days
baselineRef: orders-2026w46
approvedAtUtc: 2026-11-14T00:00:00Z
~~~

This is custom alert-governance metadata, not MongoDB configuration.

## 41. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Alerting only on CPU | Misses disk, network, pool, and replication issues | Golden signals + DB metrics |
| Treating high CPU as always P1 | False positives | Check user impact |
| Assuming low CPU means healthy | Misses query/pool bottlenecks | Multi-signal monitoring |
| One threshold for all workloads | Seasonal false alarms | Segmented baselines |
| Using mean latency | Hides p99 tail | Track percentiles |
| Plotting raw counter values | Alerts caused by long uptime | Compute rates + handle resets |
| Treating no data as OK | Silent loss of observability | Add no-data alerts |
| Same trigger and resolve threshold | Alert flapping | Use hysteresis |
| Leaving profiler level 2 on in prod | Overhead and PII risk | Bounded sampling |
| Expecting `mongos` to have `system.profile` | Wrong assumption | Use router logs / Atlas tools |
| Expecting `$currentOp` to keep history | Misses finished operations | Slow logs / profiler |
| Assuming `$queryStats` schema never changes | Collector breaks on upgrade | Version-aware design |
| Treating `COLLSCAN` as always bad | Wastes effort on tiny datasets | Measure real performance |
| Treating `IXSCAN` as always optimal | Can scan huge key ranges | Check examined/returned ratio |
| Treating replica set as backup | Accidental deletes replicate | Maintain backups/PITR |
| Equating one member's lag with cluster lag | Misses failing secondary | Monitor per member |
| Assuming fixed oplog window under rising writes | Loses catch-up margin | Monitor time window |
| Enlarging pool when DB is overloaded | Worsens saturation | Backpressure and tuning |
| Blaming all auth errors on bad passwords | Misses TLS, network, `authSource` | Categorize errors |
| Putting full queries in alerts | Leaks PII/secrets | Use query shape and redaction |
| Stopping RCA at the trigger | Lacks systemic fixes | Full RCA and verification |
| Running incidents by a single email | Missed ACKs and escalations | Runbooks and on-call |
| Running `killOp` recklessly | Aborts critical tasks | Approval workflow |
| Weakening alerts to silence pages | Hides user impact | Threshold governance |

## 42. Hands-On Exercises

Run state-changing commands only inside **labs**—never arbitrarily enable profiling, create indexes, kill operations, or reconfigure production.

### Exercise 1 — Golden Signals

Classify API p99, `opcounters` rate, authentication errors, disk latency, and connection checkout wait.

### Exercise 2 — Time-of-Day Baselines

Peak traffic is 10x off-peak. Why shouldn't you use a 24-hour average QPS as a dynamic baseline?

### Exercise 3 — Gauges vs. Counters

Distinguish `connections.current` from `connections.totalCreated`; which requires `rate()`?

### Exercise 4 — Counter Resets

Why does a counter dropping after a restart not mean negative throughput?

### Exercise 5 — Tail Latency

Mean latency is 30 ms while p99 is 1500 ms. What additional signals should you check?

### Exercise 6 — Dynamic Thresholds

Baseline p95 is 80 ms; floor = 200 ms, multiplier = 2. Which threshold applies and why?

### Exercise 7 — Hysteresis

Propose trigger and resolve thresholds with durations for disk used%.

### Exercise 8 — No-Data Detection

A monitoring agent crashes and stops reporting samples. Design an alert to catch it.

### Exercise 9 — SLO Burn Rate

SLO is 99.9%, and observed bad request ratio is 1%. Roughly what is the burn rate?

### Exercise 10 — Severity

When is a primary election a normal event, and when is it a P1?

### Exercise 11 — Atlas Tiers

Why shouldn't you assume Free/Flex includes every alert and Real-Time Performance Panel feature of M10+?

### Exercise 12 — `serverStatus`

Query `connections` in a lab and explain `current`, `available`, and `totalCreated`.

### Exercise 13 — Cache

Cache usage is 90%, yet p99, eviction, and disk latency are normal. Is there enough evidence to scale up?

### Exercise 14 — Disk Forecast

Disk used is 78%, growing 4% per day. Design a time-to-full alert.

### Exercise 15 — Query `explain`

Why does `IXSCAN` not guarantee an efficient query?

### Exercise 16 — Current Operations

Filter `$currentOp` for `secs_running >= 5`. Why shouldn't you auto-run `killOp`?

### Exercise 17 — Profiler

Enable profiling level 1 with sampling in a lab, read `system.profile`, and revert settings.

### Exercise 18 — `$queryStats`

Why verify version/support and avoid depending on fixed output field paths?

### Exercise 19 — Replication Lag

A secondary lags 20s. Which metrics separate CPU, disk, network, and oplog bottlenecks?

### Exercise 20 — Oplog Window

A secondary goes offline for 12 hours while the oplog window is 8 hours. What is the risk?

### Exercise 21 — Election Timeline

Write a timeline from heartbeat failure through app retries to recovery.

### Exercise 22 — Hot Shard

One shard is at 90% CPU while others sit at 20%. Why is cluster-wide average insufficient?

### Exercise 23 — Connection Storm

20 app pods run with `maxPoolSize=100`. Why shouldn't you assume there are always 2,000 active connections?

### Exercise 24 — Java Metrics

Attach a `CommandListener` without logging raw commands. Which pool checkout metrics should you add?

### Exercise 25 — Query Regression

After a deployment, examined/returned jumps 100x. List four hypotheses and verification checks.

### Exercise 26 — Auth Failures

After secret rotation, 20% of pods fail. Check secret versions, `authSource`, TLS, and pools.

### Exercise 27 — Incident Evidence

Write a UTC timeline and distinguish observation, hypothesis, and test result.

### Exercise 28 — Alert Routing

Design rules for P1 primary unavailable, P2 replication lag, and P3 disk growth.

### Exercise 29 — Privacy

A profiler entry contains an email address. Which fields should be redacted before sharing?

### Exercise 30 — Postmortem

Write an RCA with impact, timeline, trigger, contributing factors, mitigation, and action owners.

### Exercise 31 — Query/Index Lab

Run `explain` before and after creating the compound index on `observability_lab.orders`. Why might MongoDB still choose `COLLSCAN` on four documents?

### Exercise 32 — End-to-End System Design

Design observability for an Atlas sharded cluster with a Java API covering:

- API SLIs/SLOs.
- Query latency/shape baselines.
- Connection and pool metrics.
- Per-shard CPU/disk/cache.
- Replication lag, elections, and oplog window.
- Atlas Alerts and Profiler.
- No-data detection and alert routing.
- P1 runbook.
- Privacy controls.
- Postmortems and threshold reviews.

## 43. Production Checklist

### Baselines and Metrics

- [ ] Application-level SLIs/SLOs defined.
- [ ] Golden signals instrumented.
- [ ] Query shape and namespace metrics collected.
- [ ] Per-node and per-shard views configured.
- [ ] Baselines segmented by workload and time-of-week.
- [ ] Incidents and maintenance windows excluded or annotated.
- [ ] Baselines refreshed after major releases or tier changes.
- [ ] Counters properly converted into rates.
- [ ] Percentiles enforce minimum sample counts.
- [ ] Metric labels contain no PII and avoid high cardinality.

### Alerting

- [ ] Static and dynamic thresholds have clear justification.
- [ ] Duration and hysteresis configured.
- [ ] No-data and exporter-health alerts active.
- [ ] User-facing SLO burn-rate alerts configured.
- [ ] Every alert has an owner, severity, and escalation path.
- [ ] Runbook and dashboard links attached.
- [ ] ACK and deduplication workflows configured.
- [ ] Notification routing tested and false positives reviewed.
- [ ] Critical alerts never suppressed indefinitely.
- [ ] Threshold changes require approval.

### MongoDB

- [ ] `PRIMARY` availability and elections monitored.
- [ ] Secondary lag and oplog window monitored.
- [ ] Connections and pool behavior monitored.
- [ ] WiredTiger cache, eviction, and disk latency monitored.
- [ ] Query plans and examined/returned ratios tracked.
- [ ] Atlas tier and feature support verified.
- [ ] Database profiler controlled strictly.
- [ ] `$queryStats` used with version caveats respected.
- [ ] Sharded imbalance insights tracked where applicable.
- [ ] Backup freshness and data-safety alerts active.

### Incident Response

- [ ] Incident command roles defined.
- [ ] Timelines recorded in UTC.
- [ ] Evidence redacted before sharing.
- [ ] Safe mitigation prioritized before waiting for full RCA.
- [ ] Production changes follow rollback and approval rules.
- [ ] No reckless automated `killOp` or `reconfig`.
- [ ] Clear recovery acceptance criteria defined.
- [ ] Blameless postmortems conducted.
- [ ] Action items carry owners and deadlines.
- [ ] Regular drills run for query, disk, replication, and network incidents.

## 44. Summary

A reliable MongoDB observability lifecycle runs three continuous loops:

1. **Know what normal looks like:** record baselines by service, query shape, time, node, and workload; measure latency, traffic, errors, saturation, replication, and recovery readiness.
2. **Alert accurately:** pair static/dynamic thresholds, SLOs/error budgets, duration/hysteresis, no-data detection, and user-impact severity; give every alert an owner and a runbook.
3. **Investigate and improve:** quantify impact, record UTC timelines, correlate Atlas metrics, `serverStatus`, `rs.status`, `$currentOp`, Query Profiler, `explain`, and driver metrics. After mitigating, verify SLO recovery and document RCAs with measurable action items.

The goal is never having the most alerts—it is **catching real incidents before major damage, eliminating false alarms, and equipping on-call engineers to act safely**.

## Official Reference Documentation

- [MongoDB Atlas — Configure and Resolve Alerts](https://www.mongodb.com/docs/atlas/alerts/)
- [MongoDB Atlas — Alert Basics](https://www.mongodb.com/docs/atlas/alert-basics/)
- [MongoDB Atlas Architecture — Monitoring and Alerts](https://www.mongodb.com/docs/atlas/architecture/current/monitoring-alerts/)
- [MongoDB Atlas — Monitor Real-Time Performance](https://www.mongodb.com/docs/atlas/real-time-performance-panel/)
- [MongoDB Atlas — Query Profiler](https://www.mongodb.com/docs/atlas/tutorial/query-profiler/)
- [MongoDB Atlas — Analyze Slow Queries](https://www.mongodb.com/docs/atlas/analyze-slow-queries/)
- [MongoDB Manual — `serverStatus`](https://www.mongodb.com/docs/manual/reference/command/serverstatus/)
- [MongoDB Manual — Monitor Slow Queries with `$currentOp`](https://www.mongodb.com/docs/manual/tutorial/monitor-slow-queries/)
- [MongoDB Manual — Database Profiler](https://www.mongodb.com/docs/manual/tutorial/manage-the-database-profiler/)
- [MongoDB Manual — `$queryStats`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/querystats/)
- [MongoDB Manual — Troubleshoot Replication Lag](https://www.mongodb.com/docs/manual/troubleshooting/replication-lag/)
- [MongoDB Manual — `rs.printReplicationInfo()`](https://www.mongodb.com/docs/manual/reference/method/rs.printreplicationinfo/)
- [MongoDB Manual — Replication Fundamentals](https://www.mongodb.com/docs/manual/replication/)
- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Java Sync Driver — Monitoring](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/monitoring/)
