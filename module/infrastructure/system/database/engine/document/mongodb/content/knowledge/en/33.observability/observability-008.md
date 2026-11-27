# `mongostat`, `mongotop`, Compass, and Atlas Monitoring Tools in MongoDB

## 1. Objectives and the Observability Big Picture

A MongoDB system can still accept connections normally while the application responds very slowly. Causes may include collection-scanning queries, excessive connections, disk saturation, cache pressure, a write-heavy collection, secondary replication lag, or a shard key producing uneven load distribution.

The first question during an investigation is not just "Is MongoDB alive?" but also:

- **On which node**, at what time, and for how long did load spike?
- How did insert/query/update/delete rates and network traffic change?
- **Which collection** is consuming the most read/write time?
- **Which query shape** is slow or scanning many documents?
- Is the bottleneck CPU, memory, disk, network, queues, or the connection pool?
- Does the replica set have secondary lag, elections, or loss of majority?
- Did a recently deployed change trigger the incident?
- Did monitoring alert before users were impacted?

MongoDB offers four tools commonly used together:

1. **`mongostat`:** quick periodic view of a `mongod` or `mongos` process across sampling intervals.
2. **`mongotop`:** measures cumulative read/write time per collection/namespace on a `mongod`.
3. **MongoDB Compass:** graphical interface featuring Performance and Explain Plan views for inspecting stats and queries.
4. **MongoDB Atlas Monitoring:** historical charts, Real-Time Performance Panel, Query Insights/Profiler, Performance Advisor, Sharding Insights, logs, and alerts depending on cluster tier.

This lesson focuses on **picking the right tool, interpreting numbers accurately, and structuring a diagnostic workflow**. A single metric rarely identifies the root cause on its own.

### Learning Outcomes

After this lesson, you will be able to:

- Run `mongostat` and `mongotop` from a terminal with interval and row count options.
- Read throughput, WiredTiger cache, memory, active/queued clients, network, and connections.
- Avoid confusing **cumulative read/write time** in `mongotop` with single-query latency.
- Use Compass Performance and Explain Plan to locate query bottlenecks.
- Distinguish Atlas Metrics, RTPP, Query Profiler, Query Insights, and Performance Advisor.
- Configure alerts with conditions, owners, notifications, and runbooks.
- Combine `serverStatus`, `$currentOp`, `rs.status()`, and `explain("executionStats")`.
- Investigate slowness incidents by timestamp, node, collection, query shape, and before/after metrics.

---

## 2. Which Tool Should You Open First?

| Question | Tool to open first | Keep in mind |
| --- | --- | --- |
| Unusual spike in database activity? | `mongostat`, Atlas Metrics | Verify units and sampling interval |
| Connections or queues climbing? | `mongostat`, Atlas Metrics | Compare against traffic and app connection pools |
| Which collection is hot? | `mongotop`, Compass Performance, Atlas RTPP | Cumulative time differs from latency |
| Is the query using an index? | Compass Explain, `explain()` | Check both keys and docs examined |
| Which query is running long right now? | `$currentOp`, Compass Slowest Operations, RTPP | Reflects currently active operations |
| Which query shapes were slow over recent days? | Atlas Query Insights/Profiler | Subject to sampling and retention |
| Should we add an index? | Performance Advisor + Explain + benchmark | Indexes also add write and storage overhead |
| Replica set issues? | Atlas per-node metrics, `rs.status()` | Check secondaries and oplog |
| How is load distributed across shards? | Sharding Insights and per-shard metrics | Depends on Atlas tier and server version |
| Want to be paged when disk nears full? | Atlas Alerts | Requires thresholds, owner, and runbook |
| API p99 rises while MongoDB metrics look normal? | App APM/tracing + DB metrics | DB is only one leg of the request |

### 2.1. Metrics, Logs, Traces, and Explain Are Distinct

- **Metrics:** time-series measurements such as ops/s, CPU, connections, replication lag; suited for dashboards and alerts.
- **Logs:** event records such as failovers, authentication failures, slow operations; suited for timelines and investigation.
- **Traces:** an HTTP request's path across app, driver, MongoDB, and downstream services; suited for attributing latency.
- **Profiler:** sampled operations/queries helping identify slow query shapes.
- **Explain:** query plan and execution statistics from running a test query.

A high CPU chart does not prove a missing index. A query using `IXSCAN` does not prove it is optimal.

---

## 3. Preparing MongoDB Database Tools

`mongostat` and `mongotop` belong to **MongoDB Database Tools**. They are OS command-line programs, not JavaScript expressions inside `mongosh`.

Verify installation:

```bash
mongostat --version
mongotop --version
mongosh --version
```

MongoDB Database Tools follow their own release numbering, typically `100.x`. The Database Tools version need not match MongoDB Server identically, but must be compatible with your deployment.

### 3.1. Where to Run Them?

- On an authorized admin host or bastion permitted to reach `mongod`/`mongos`.
- In a self-managed lab environment to practice syntax.
- With Atlas, tools can run over authorized endpoints with TLS/credentials where features and privileges permit.
- Compass is a standalone GUI desktop app; Atlas Monitoring is built into the Atlas UI per project.

**Never** open public network access to MongoDB solely for monitoring. Network segmentation, TLS, and database roles must always remain enforced.

### 3.2. Least-Privilege Permissions

`mongostat` reads information such as `serverStatus`; `mongotop` requires privileges tied to `serverStatus` and `top`. The built-in **`clusterMonitor`** role generally suits self-managed monitoring, subject to deployment policy.

Viewing other users' operations via `$currentOp` may require `inprog`; terminating operations requires separate privileges like `killop`. Never grant those to people who only view dashboards.

**Atlas Project roles** and **MongoDB database roles** are two separate layers. A Project Viewer can view charts without automatically having permission to create indexes or run every admin command.

### 3.3. Connecting Without Exposing Credentials

Unauthenticated lab environment:

```bash
mongostat --host=127.0.0.1:27017 --rowcount=5 1
mongotop --host=127.0.0.1:27017 --rowcount=5 1
```

Authenticated deployment, prompting for password:

```bash
mongostat \
  --host=mongo1.example.net:27017 \
  --username=monitorUser \
  --authenticationDatabase=admin \
  --rowcount=10 2
```

Database Tools support TLS/CA options and `--config` depending on version. **Never put plaintext passwords in URIs inside logs, repositories, or shell history**, and never disable TLS verification as a "quick fix."

---

## 4. `mongostat`: Quick Per-Node View

`mongostat` periodically monitors `mongod`/`mongos`, similar in spirit to Linux `vmstat`.

Syntax:

```bash
mongostat [options] [polling-interval-seconds]
```

Examples:

```bash
# Local MongoDB, one sample per second, runs until Ctrl+C.
mongostat

# Collect 12 samples at a two-second interval.
mongostat --host=127.0.0.1:27017 --rowcount=12 2

# Collect 10 samples, every five seconds.
mongostat --rowcount=10 5
```

`--rowcount` sets the number of displayed rows; the trailing number is the **polling interval in seconds**. Omitting row count lets the tool run continuously until stopped.

### 4.1. Illustrative Sample Output

```text
insert query update delete getmore command dirty used flushes vsize res qrw arw net_in net_out conn time
    15    46     12      1       4     3|0  1.2%  36%      0   2.7G 400M 0|0 4|1  100k   250k   40 10:00:00
    80   210     75      4       7     5|0  3.8%  59%      0   2.8G 445M 2|5 9|8  950k   1.2m   90 10:00:01
```

**These numbers are fictional examples**, not benchmark results. Column names and formats vary by Database Tools and server version.

### 4.2. Operation Counters

| Field | Meaning | Interpretation |
| --- | --- | --- |
| `insert` | Objects/documents inserted per second | Ingest burst or batch import |
| `query` | Query operations per second | Does not necessarily equal HTTP GET count |
| `update` | Update operations per second | Batch updates or app writes |
| `delete` | Delete operations per second | Cleanups, purges, TTL activity |
| `getmore` | Cursor `getMore` operations per second | Additional batch fetches |
| `command` | Command operations per second | On secondaries may show `local|replicated` |
| `set` | Replica set name if applicable | Group identifier |
| `repl` | Member role | `PRI`, `SEC`, `REC`, `RTR`, etc. |

On some values, an asterisk `*` denotes a **replicated operation**. For example, `*0` on a secondary is neither an error nor a wildcard.

One HTTP request can trigger multiple database commands, and one query may retry. Hence **ops/s does not equal application requests/s**.

### 4.3. Cache and Memory

| Field | What it actually is | What it is NOT |
| --- | --- | --- |
| `dirty` | % of WiredTiger cache max holding dirty bytes | % of total host RAM |
| `used` | % of WiredTiger cache max currently in use | % of total disk or OS RAM |
| `vsize` | Process virtual memory size | Actual resident RAM |
| `res` | Process resident memory | Total host or Search Node memory |
| `flushes` | WiredTiger checkpoint events per interval | Number of document writes to disk |

For example, `used=94%` is **insufficient** to prove a memory leak. WiredTiger cache is designed to fill; correlate eviction behavior, disk I/O, query latency, and OS free memory.

Sustained rising `dirty` paired with rising write latency and disk utilization can suggest checkpoint/disk pressure, though still verify with companion metrics before concluding.

### 4.4. Queues and Active Requests

Some outputs display:

- `qr` / `qw`: read/write clients currently **queued**.
- `ar` / `aw`: read/write clients currently **active**.
- `qrw` / `arw`: combined `read|write` format.

Example:

```text
qrw  arw
0|6  8|12
```

This shows 0 queued readers, 6 queued writers, 8 active readers, and 12 active writers in this example format. Growing queues can stem from saturation, contention, or load bursts. Compare CPU, disk, and latency to isolate the true bottleneck.

### 4.5. Network and Connections

| Field | Meaning |
| --- | --- |
| `net_in` / `netIn` | Bytes received, formatted per utility interval |
| `net_out` / `netOut` | Bytes sent |
| `conn` | Open connections |

If `conn` jumps from 200 to 3,000 after a deploy, hypotheses include: the app creating unpooled clients per request, pod scale-out, connection pool misconfiguration, retry storms, or connection leaks.

Do not upgrade cluster tiers before checking driver pool telemetry, connection limits, and traffic.

### 4.6. How Polling Interval Shapes Interpretation

Throughput numbers in `mongostat` are normalized to **per-second** rates even when the interval exceeds 1 second. With a 5-second interval, a 0.2-second burst gets smoothed into an interval average.

- 1s interval: suited for brief live incidents, verbose output.
- 5–10s interval: suited for watching trends in a terminal.
- Atlas Metrics: better for historical data, with its own granularity and retention.

---

## 5. Advanced `mongostat`

### 5.1. Monitoring Multiple Replica Set Members

```bash
mongostat \
  --host=mongo1.example.net:27017,mongo2.example.net:27017,mongo3.example.net:27017 \
  --rowcount=15 2
```

Read node data in context of `PRI`/`SEC` role, network path, and sampling timestamp.

### 5.2. Discovering Topology with `--discover`

```bash
mongostat \
  --host=mongo1.example.net:27017 \
  --discover \
  --rowcount=15 2
```

`--discover` discovers **non-hidden replica set members**. When connected to `mongos`, it can gather stats across eligible shards and members.

**Do not** assume discovery covers hidden members or hosts unreachable due to network or permission constraints.

### 5.3. JSON Output

```bash
mongostat --host=127.0.0.1:27017 --json --rowcount=5 1
```

JSON is handy for saving a lab monitoring trace, though do not treat field names as an immutable API across all Database Tools versions.

### 5.4. Selecting Additional `serverStatus` Fields

`-O` appends fields to default output:

```bash
mongostat \
  --host=127.0.0.1:27017 \
  -O='host,version,network.numRequests=Requests' \
  --rowcount=5 2
```

`-o` outputs only the explicitly selected fields:

```bash
mongostat \
  --host=127.0.0.1:27017 \
  -o='host=Node,time=Time,network.numRequests=Requests' \
  --rowcount=5 2
```

Per documentation, `-o` also supports `.rate()` and `.diff()` on compatible `serverStatus` fields. **Never use `-o` and `-O` together.**

```bash
mongostat --all --rowcount=5 2
mongostat --interactive
```

`--interactive` cannot be combined with `--json`.

### 5.5. What `mongostat` Cannot Answer

- Which query drove up the counter?
- Which collection is hot?
- How long did one specific query run?
- What is the app's p95/p99 latency?
- What was yesterday's historical trend?

To answer those, move to `mongotop`, Compass/Atlas Profiler, or application observability.

---

## 6. `mongotop`: Which Collection Consumes Read/Write Time?

`mongotop` reports **read/write execution time per namespace**, giving a collection-level view on a `mongod`.

```bash
mongotop

mongotop --host=127.0.0.1:27017 --rowcount=10 2
```

By default it polls every second. Required privileges include `serverStatus` and `top` per Database Tools documentation.

### 6.1. Sample Output

```text
ns                       total    read    write    timestamp
shop.orders              850ms   700ms   150ms    10:10:00
shop.sessions            430ms    30ms   400ms    10:10:00
shop.products             70ms    70ms     0ms    10:10:00
```

Values are **hypothetical**.

| Column | Meaning |
| --- | --- |
| `ns` | Namespace `database.collection` |
| `total` | Total operation time recorded for the namespace |
| `read` | Total read operation time |
| `write` | Total write operation time |
| Timestamp | Reporting timestamp |

### 6.2. Do Not Confuse Cumulative Time with Latency

Suppose a collection serves 100 concurrent reads, each taking 10 ms:

```text
100 × 10 ms = 1,000 ms total operation time
```

Because operations overlap concurrently, `mongotop.total` **can exceed 1,000 ms within a 1-second interval**. That does not mean a single query took over a second, nor does it mean % CPU.

To see operation counts or per-query latency, use JSON mode, Query Profiler, and APM.

### 6.3. Missing Namespaces

`mongotop` generally lists only namespaces active during the sample. If a collection does not appear:

- It may have had no activity during that window.
- Traffic may have hit another node.
- Queries may have completed between samples.
- Feature/permission limits in a GUI tool may hide it.

Never conclude the collection went unused all day.

### 6.4. JSON and Legacy `--locks`

```bash
mongotop --host=127.0.0.1:27017 --json --rowcount=5 1
```

MongoDB docs note that JSON output also includes **operation counts in the polling interval** alongside read/write timings.

`mongotop --locks` is a **legacy** flag for pre-MongoDB 3.0 per-database lock usage; on newer servers it may fail. **Never use `--locks` to infer lock contention on MongoDB 8.x/9.x.**

### 6.5. `mongotop` in a Sharded Cluster

`mongotop` targets statistics of **a single `mongod`**. In sharded clusters, inspect **multiple shard members** or Atlas per-shard charts / Sharding Insights. A single `mongos` connection does not reflect physical shard-node timings.

---

## 7. Lab: Creating Data and an Unindexed Query

Open `mongosh` on a **test database**—never run `drop()` or generate synthetic load on production.

```javascript
const lab = db.getSiblingDB("observability_lab");
lab.events.drop();

const records = Array.from({ length: 2000 }, (_, i) => ({
  tenantId: i % 2 === 0 ? "A" : "B",
  eventId: "event-" + i,
  status: i % 10 === 0 ? "FAILED" : "OK",
  category: ["auth", "order", "payment", "search"][i % 4],
  createdAt: new Date(Date.UTC(2026, 10, 14, 0, 0, i % 3600)),
  durationMs: (i * 7) % 300,
  payload: { source: "demo", id: i }
}));

lab.events.insertMany(records);

lab.events.createIndex(
  { tenantId: 1, createdAt: -1 },
  { name: "ix_tenant_createdAt" }
);

lab.events.countDocuments({});
// 2000
```

### 7.1. Well-Indexed Query

```javascript
lab.events.find({
  tenantId: "A",
  createdAt: {
    $gte: ISODate("2026-11-14T00:10:00Z")
  }
})
.sort({ createdAt: -1 })
.limit(20)
.explain("executionStats");
```

The `(tenantId, createdAt)` index satisfies the tenant equality, range filter, and time sort. Still, with 2,000 docs, the optimizer may pick another plan; **always inspect actual `explain`**.

### 7.2. Query Missing an Index on `status`

```javascript
lab.events.find({ status: "FAILED" })
  .sort({ createdAt: -1 })
  .limit(20)
  .explain("executionStats");
```

Currently no index supports `status + sort(createdAt)` well, potentially causing a `COLLSCAN` and costly sort.

### 7.3. Generating a Tiny Workload to Observe

Open two terminals:

```bash
# Terminal A
mongostat --rowcount=30 1

# Terminal B
mongotop --rowcount=30 1
```

Then run in the **lab** `mongosh`:

```javascript
for (let i = 0; i < 100; i++) {
  lab.events.find({ status: "FAILED" })
    .sort({ createdAt: -1 })
    .limit(10)
    .toArray();
}

for (let i = 0; i < 50; i++) {
  lab.events.updateOne(
    { eventId: "event-" + i },
    { $inc: { durationMs: 1 } }
  );
}
```

`mongostat` should reflect rising query/update ops; `mongotop` should show read/write time on `observability_lab.events`.

**Note:** With tiny data, the entire loop finishes rapidly and may fall between polls. Seeing no spike does not mean the tool is broken. Never inflate workload to millions of queries in production just to "populate charts."

### 7.4. Adding a Test Index and Re-Comparing `explain`

```javascript
lab.events.createIndex(
  { status: 1, createdAt: -1 },
  { name: "ix_status_createdAt" }
);

lab.events.find({ status: "FAILED" })
  .sort({ createdAt: -1 })
  .limit(20)
  .explain("executionStats");
```

Compare:

- `winningPlan`.
- `totalKeysExamined`.
- `totalDocsExamined`.
- `nReturned`.
- Sort stage.
- `executionTimeMillis`.
- Write-workload impact if tested at larger scale.

New indexes add storage usage and write amplification. Never create indexes directly in production without evaluating other query patterns.

---

## 8. Additional Commands in `mongosh`

### 8.1. `serverStatus`: Per-Node Counters

```javascript
const admin = db.getSiblingDB("admin");
const s = admin.serverStatus();

printjson({
  uptime: s.uptime,
  connections: s.connections,
  opcounters: s.opcounters,
  network: s.network,
  opLatencies: s.opLatencies
});
```

Many fields in `serverStatus` are **cumulative counters since process startup**, not per-second rates.

To compute a rate:

\[
\mathrm{rate}=\frac{\mathrm{counter}_2-\mathrm{counter}_1}{t_2-t_1}
\]

If a counter rises by 600 over 10 seconds, the average rate is 60/s. Never compute deltas across restarts or between two different nodes without noting it.

`opLatencies` reports count/latency totals per operation class; never treat an average as HTTP p95/p99.

### 8.2. `top`: Operation Time by Namespace

```javascript
db.getSiblingDB("admin").runCommand({ top: 1 });
```

`top` output backs `mongotop`. On `mongod`, it reports timings per namespace. Never query a single node and treat it as a sharded cluster aggregate.

### 8.3. `currentOp`: Currently Running Operations

```javascript
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
      secs_running: { $gte: 2 }
    }
  },
  {
    $project: {
      opid: 1,
      ns: 1,
      op: 1,
      secs_running: 1,
      client: 1,
      waitingForLock: 1
    }
  }
]).toArray();
```

Requires appropriate privileges and supported deployment/role. Options and field names vary by MongoDB version and process role.

**Never automatically kill an operation** solely because `secs_running` is high: it could be a legitimate reporting job, backup, index build, or transaction.

### 8.4. `rs.status` and `db.hello`

```javascript
db.hello();

// Only on a replica set with appropriate privileges:
rs.status();
```

Use these to check primary/secondary roles, member health, replication state, and optimes. A secondary serving heavy reads has a different load profile from the primary.

### 8.5. `explain`

```javascript
lab.events.find({ status: "FAILED" })
  .sort({ createdAt: -1 })
  .limit(20)
  .explain("executionStats");
```

Never confuse `executionTimeMillis` from **one `explain` run** with historical application p99.

---

## 9. MongoDB Compass: Performance via GUI

MongoDB Compass is the official desktop GUI for browsing documents, indexes, schemas, aggregations, and query explains.

### 9.1. Opening Performance

Per current Compass documentation:

1. Open Compass and connect to a deployment with appropriate credentials.
2. In the **Connections Sidebar**, open the menu next to the connection name.
3. Select **Performance**.
4. Inspect charts and tables, recording timestamps and nodes.
5. Inspect Hottest Collections and Slowest Operations to guide deeper analysis.

Menu names and placement can shift across Compass versions; follow guidance for your installed version.

### 9.2. Areas of the Performance View

| Area | Content | Comparison tool |
| --- | --- | --- |
| Operations | Database operation rates | `mongostat` |
| Read & Write | Active and queued reads/writes | `mongostat` |
| Network | Network and connections | `mongostat` |
| Memory | Cache and process memory metrics | `mongostat` |
| Hottest Collections | Collections with the most activity | `mongotop` |
| Slowest Operations | Currently slow-running operations | `db.currentOp()` / `$currentOp` |

Compass includes a **Pause** button that freezes UI updates; it **does not pause the MongoDB database**. Never treat GUI Pause as freezing data or taking a backup.

### 9.3. Limitations

- Compass provides **limited Performance info** when connected to `mongos`.
- Compass cannot collect performance data for collections using **Queryable Encryption** per current documentation.
- Real-time Performance does not store full history from last month.
- Viewing or killing operations requires matching database privileges; `killop` must not be granted broadly.

---

## 10. Compass Explain Plan: Inspecting Specific Query Plans

`mongostat` shows which node is loaded; `mongotop` shows which collection is hot; **Explain** identifies the specific query bottleneck.

### 10.1. Walkthrough

1. Open collection `observability_lab.events` in Compass.
2. In the query bar, enter Filter:

```javascript
{ status: "FAILED" }
```

3. Enter Sort:

```javascript
{ createdAt: -1 }
```

4. Click **Explain**.
5. Inspect the **Visual Tree**.
6. Switch to **Raw Output** to inspect full execution details.
7. Compare before and after adding index `ix_status_createdAt`.

### 10.2. Reading Key Metrics

| Field/Stage | Meaning |
| --- | --- |
| `COLLSCAN` | Collection scan |
| `IXSCAN` | B-tree index scan |
| `FETCH` | Document fetch following index lookup |
| `SORT` | In-memory/blocking sort stage; can consume memory |
| `totalDocsExamined` | Documents inspected |
| `totalKeysExamined` | Index keys inspected |
| `nReturned` | Documents returned |
| `executionTimeMillis` | Duration of this explain run, not p95 |
| `winningPlan` | Selected query execution plan |

### 10.3. Query Targeting Ratio

\[
\mathrm{DocsExaminedPerReturned} =
\frac{\mathrm{docsExamined}}{\mathrm{docsReturned}}
\]

Scanning 100,000 docs to return 100 docs gives a ratio of **1,000 docs/result**.

If `docsReturned=0`, standard division fails; never blindly report infinity or zero.

**A high ratio is not always a bug:** analytical full scans can be intentional. Consider request semantics and traffic.

### 10.4. `IXSCAN` Alone Proves Nothing

```text
IXSCAN keysExamined=400,000
FETCH docsExamined=250,000
nReturned=5
```

An index was used, yet huge numbers of keys and docs were scanned. Check compound index prefix order, filter selectivity, collation, sort order, and data skew.

### 10.5. Visual Tree Limitations

MongoDB Compass currently **does not render vector search queries as a Visual Tree** in Explain. For `$vectorSearch`, use version-supported explain outputs/methods and dedicated Search metrics.

---

## 11. Atlas Monitoring: Observing the System Over Time

Atlas provides monitoring scoped by cluster, node, project, and supported features.

Core tools:

- **Deployment Metrics:** historical charts for throughput, CPU, disk, memory, network, connections, etc.
- **Real-Time Performance Panel (RTPP):** near real-time activity, slowest operations, and hottest collections.
- **Query Insights:** query shapes and namespaces with slow-running queries.
- **Query Profiler:** details on sampled slow operations.
- **Performance Advisor:** index recommendations derived from workload.
- **Sharding Insights:** workload distribution visibility across sharded clusters where eligible.
- **Alerts:** conditions/thresholds and notifications.
- **Logs, Administration API, Integrations:** deep troubleshooting and external observability pipelines.

### 11.1. Check Tier and Permissions First

Not every feature exists on every cluster:

- **RTPP**: Atlas docs specify **M10+**.
- **Performance Advisor**: available on **M10+**.
- **Query Profiler/Query Insights**: depends on tier, role, feature/threshold settings, and captured data.
- **Sharding Insights**: current docs note **M10+ sharded clusters, MongoDB 8.0+**.
- **Free/Flex**: carry specific limits on metrics, retention, and alerts.

If a menu is missing, check Atlas tier, project roles, server version, and feature settings.

---

## 12. Atlas Deployment Metrics

In Atlas, select your organization/project, open the cluster/deployment, and go to **Metrics** in the UI. Select the time window covering the incident.

### 12.1. Metric Groups to Inspect

| Group | Notable signals |
| --- | --- |
| Operations/s | Load surging right after a deploy or batch job |
| CPU | Sustained saturation |
| Disk IOPS/latency | Read/write bottlenecks |
| Cache & resident memory | Cache pressure and evictions |
| Connections | Connection storms or pool growth |
| Network In/Out | Large payloads, read traffic, replication |
| Query Targeting | Scanning far more docs than returned |
| Replication Lag | Secondary trailing the primary |
| Oplog Window | Secondary recovery risk |
| Data/Index Size | Capacity and write amplification |
| Search Nodes (if used) | Search index RAM, disk, and latency |

Exact metric availability varies by cluster tier and MongoDB version.

### 12.2. Baselines Matter More Than Any Single Value

Suppose CPU = 75%:

- Cluster A normally runs at 15–25% and jumped to 75% after a deployment: investigate immediately.
- Cluster B normally runs at 60–80% during peak hours with no latency/error increase: not necessarily an incident.

Compare against the same hour yesterday, the same weekday last week, and recent deployment events.

### 12.3. Sampling and Granularity

A 20-second burst can vanish on an hourly-averaged chart. When investigating:

- Narrow the time range.
- Select the finest granularity supported by the environment.
- Correlate with timestamped logs and profiler entries.
- Use explicit timezones (prefer UTC).
- Never compare 1-second data directly against 5-minute averages without noting the difference.

---

## 13. Atlas Real-Time Performance Panel

RTPP shows near real-time performance on eligible Atlas deployments.

Displayed telemetry can include:

- Connections, Network In/Out.
- CPU, Disk IOPS, System Memory.
- Operations.
- Query Execution Times.
- Query Targeting.
- Hottest Collections.
- Slowest Operations.
- Active/queued readers and writers.
- Replication lag depending on member/role.

### 13.1. Using RTPP When the Application Slows Down

1. Open the cluster's RTPP in Atlas.
2. Select the target node/shard or scope.
3. Review operations, CPU, IOPS, and Network trends.
4. Open **Hottest Collections** to spot busy namespaces.
5. Open **Slowest Operations** to inspect long-running ops.
6. Check Query Targeting.
7. Note query shape, host, and timestamp, then move to Profiler/Explain for deep analysis.

### 13.2. Scope Limitations

Per Atlas Docs, RTPP pulls data from **primary replica set members** (or each shard's primary in sharded clusters). It does not replace monitoring secondaries when apps read with `secondaryPreferred`.

Some fields may be hidden/redacted under Queryable Encryption. Viewing privileges differ from **Kill Op** privileges.

### 13.3. Kill Op Requires a Process

If the UI permits terminating an operation, verify:

- Is it business-critical?
- Is it tied to a backup, index build, or transaction?
- Can the app safely retry?
- Who owns the incident?
- Is there a rollback/recovery plan?

**Never** kill an operation simply because duration exceeds 1 second.

---

## 14. Atlas Query Insights: Query Shapes and Namespaces

Query Insights analyzes **slow query patterns** rather than only currently active operations.

### 14.1. Query Shapes

Two commands:

```javascript
db.orders.find({ status: "NEW", tenantId: "A" });
db.orders.find({ status: "PAID", tenantId: "B" });
```

can be grouped into the same shape when filter structures match. MongoDB/Atlas defines query shapes by version and operation type; never assume every literal variation yields the same shape.

### 14.2. Query Shape Insights

Helps you:

- Identify query shapes with high latency.
- View trends by host/shard and time range.
- Compare shapes to spot regressions.
- Separate rare anomalies from frequent queries.

### 14.3. Namespace Insights

View performance by collection:

```text
shop.orders
shop.products
shop.sessions
```

If `shop.orders` shows rising latency, inspect its query shapes; one collection often serves many queries with distinct structures and index needs.

### 14.4. Sampled P95 Latency Is Not HTTP p95

Atlas can show sampled P95 latency for slow query shapes in Query Insights. That figure **does not necessarily equal** end-to-end API p95, because application latency also includes:

- Network and serialization.
- Driver pool wait.
- Application CPU.
- Retries.
- External dependencies.
- Off-DB aggregation, LLM, or reranking steps.

You still need app APM/tracing to evaluate user-facing SLOs.

---

## 15. Atlas Query Profiler

Query Profiler focuses on slow operations captured by Atlas. In the current UI, it typically sits under cluster -> **Query Insights** -> **Query Profiler**.

### 15.1. Key Fields

| Metric | Meaning |
| --- | --- |
| `millis` | Operation execution time |
| `docsExamined` | Documents read to process the query |
| `nreturned` / Docs Returned | Results returned |
| `keysExamined` | Index keys examined |
| `planSummary` | Plan summary such as `COLLSCAN` or `IXSCAN` |
| `numYields` | Number of times the operation yielded |
| Response Length | Result payload size |
| Docs/Keys Examined : Returned | Query targeting efficiency |

**Illustrative** sample log:

```javascript
{
  ns: "shop.orders",
  millis: 270,
  planSummary: "COLLSCAN",
  docsExamined: 250000,
  keysExamined: 0,
  nreturned: 12
}
```

Ratio `docsExamined`/`nreturned` ≈ **20,833**. This signals checking query filters and indexes, not blindly creating an index without further verification.

### 15.2. Sampling and Retention

The profiler stores **samples/history** depending on tier and feature; current Atlas documentation notes access to recent slow query history (e.g., up to **7 days** under current behavior).

Never treat the profiler as permanent storage for all queries. For auditing or long-term trends, use dedicated logging/metrics pipelines with appropriate retention policies.

### 15.3. Slow Thresholds Can Be Dynamic

Atlas-managed slow query thresholds can adapt dynamically to workload when enabled. Thus "slow" on cluster A vs. cluster B may use different millisecond thresholds. Never compare raw slow-query counts across clusters while ignoring thresholds and sampling.

### 15.4. Profiler Differs from Explain

- Profiler: **operations that already ran** under live traffic.
- Explain: **plan and execution stats** for a test query run.

Sound workflow: Profiler -> query shape/parameters -> Explain in an appropriate environment -> index/query rewrite -> verify against production telemetry.

---

## 16. Atlas Performance Advisor

Performance Advisor analyzes slow query workloads to suggest indexes likely to improve performance.

You may see:

- Recommended index key pattern.
- Sample query shapes.
- Execution count.
- Average execution time.
- Query targeting.
- Docs scanned/returned.
- In-memory sorts.
- Index ranking or drop suggestions depending on UI.

### 16.1. Why Not Create Every Suggested Index?

Every new index:

- Consumes disk, storage, and cache.
- Increases insert/update/delete write cost.
- Uses resources during the index build.
- May duplicate or overlap existing indexes.
- May not match collation, partial filter, or multikey rules.
- May speed up one rare query while slowing frequent writes.

**Advisor offers suggestions**—always validate with `explain`, workload mix, and impact.

### 16.2. No Suggestions Does Not Mean Zero Database Issues

Performance Advisor depends on thresholds, sampling, and query types. A Query Targeting alert can fire without an Advisor suggestion. Beyond missing indexes, bottlenecks include CPU/disk, connection pools, network, and application retries.

---

## 17. Atlas Alerts: Turning Charts into Action

Atlas Alerts let you configure metric/event conditions and route notifications to configured channels. Capabilities and conditions vary by tier.

### 17.1. Elements of an Actionable Alert

```text
Name: Production MongoDB disk capacity risk
Target: production cluster
Condition: disk threshold per supported Atlas metric
Duration: sustained for Y minutes
Severity: Warning / Critical
Owner: Platform On-call
Notifications: Email + PagerDuty
Runbook: link to instructions for checking time-to-full and scaling capacity
```

`Y`, disk levels, and severities must match your specific workload. Fields above are **design descriptions**, not literal API config to copy verbatim.

### 17.2. Critical Alert Groups

| Group | What to detect | First step |
| --- | --- | --- |
| Disk space | Short time-to-full | Check data/index growth |
| Sustained high CPU | Saturation | Compare load, query plans, background jobs |
| Connections | Pool nearing limit | Check app pools and client counts |
| Replica lag | Secondary trailing | Check disk, network, writes, oplog window |
| Node unavailable | Member down | Check quorum and failover |
| Slow query targeting | Inefficient scans | Profiler and Explain |
| Backup failure | Loss of recovery coverage | Check backup pipeline and retention |
| Network spike | Unusual payloads/traffic | Check app traffic and replication |
| Search capacity | Search index lag/pressure | Check Search metrics and version |

Not every row corresponds to a pre-built condition name across all Atlas tiers; verify actual supported conditions before configuring.

### 17.3. Reducing Alert Flapping and Fatigue

- Use duration thresholds where supported.
- Base thresholds on baselines.
- Separate Warning vs. Critical.
- Use maintenance windows.
- Assign on-call owners.
- Group alerts sharing one root cause.
- Attach escalation paths and runbooks.
- Test notification channels end-to-end.

Atlas supports "send if condition lasts at least" and resend intervals for **host alerts**, though not every event-based alert supports them.

### 17.4. Permissions and Notifications

Atlas supports integrations like email, SMS, PagerDuty, Microsoft Teams, and webhooks per configuration. Managing project alerts requires roles such as **Project Owner** or **Project Alerts Manager** where supported.

Never route raw query literals containing PII through webhooks or public chat channels.

---

## 18. Replica Sets: Observing Primary and Secondaries Separately

### 18.1. Key Metrics

- Primary and secondary health.
- Replication lag per secondary.
- Optimes and oplog window.
- Elections and role changes.
- Application read preference.
- Per-member disk IOPS and cache pressure.
- Inter-member network health.
- Hidden/delayed members if present.

**Hypothetical** example:

```text
Primary P:     query=100/s, update=600/s
Secondary S1:  query=1500/s, update=*600/s
Secondary S2:  query=0/s, update=*600/s
```

`S1` may be serving heavy reads due to secondary read preference. Looking only at the primary misses the overloaded node.

### 18.2. Replication Lag Has Many Causes

- Primary write bursts.
- Slow secondary disk.
- Network disruptions.
- Secondary serving heavy read queries.
- Cache pressure.
- Index builds or maintenance.
- Member restarts or recovery.

Do not enlarge the oplog and expect lag to disappear; longer retention buys recovery time without fixing apply throughput bottlenecks.

### 18.3. Monitoring Majority and Failover

With 3 voting members, majority is 2. Losing two members halts write availability. When node-unavailable alerts fire, inspect `rs.status()` and election logs—not just `mongostat conn`.

---

## 19. Sharded Clusters: Viewing Load per Shard

Sharding can distribute data evenly while workload stays skewed.

```text
Sharded cluster:
  Shard A: 80% operations
  Shard B: 15% operations
  Shard C:  5% operations
```

Illustrative numbers only.

Causes include hot shard keys, range hotspots, scatter-gather queries, balancer migrations, or single-tenant traffic spikes.

Per Atlas Docs, **Sharding Insights** is available on M10+ sharded clusters running MongoDB 8.0+ subject to feature requirements.

Inspect:

- Ops/s, CPU/disk, and network per shard.
- Query targeting and participating shard counts.
- Chunk distribution and migrations.
- Shard key cardinality.
- Routing and `mongos` health.
- Replication lag on each shard replica set.

`mongostat --discover` gives per-member figures, yet cannot replace full sharding metadata analysis.

---

## 20. Symptom-Driven Analysis Without Jumping to One-Step Conclusions

| Symptom | Reasonable hypotheses | Next evidence |
| --- | --- | --- |
| High CPU, high docs examined | Broad query scans | Profiler, Explain |
| High CPU, low docs examined | Aggregations, compression, index builds | Logs, stages, host metrics |
| WiredTiger dirty rising | Write/checkpoint pressure | Disk IOPS, cache metrics |
| High cache used | Large working set or normal cache behavior | Evictions, disk read latency |
| Connections rising | App scale-out, pool leak, retries | Driver pool stats |
| Network out rising | Large responses, `getMore`, replication | Response Length, app traces |
| Read queue rising | Contention or saturation | Active ops, CPU/disk |
| Secondary lag | Disk, network, or write bursts | `rs.status` / Atlas per-node |
| One shard hot | Shard-key or workload skew | Sharding Insights |
| `COLLSCAN` + poor targeting | Missing index or non-selective shape | Index inventory, Explain |
| High app p99, DB looks normal | Pool wait, network, app CPU | Distributed tracing |

These are **hypotheses**, not guaranteed causal rules.

---

## 21. Step-by-Step Investigation of a Specific Incident

Suppose after a deployment, `/api/orders?status=FAILED` jumps from 70 ms to 650 ms p95 at **14:05 UTC**. This is a fictional example.

### Step 1 — Frame the Timeline

```text
Incident: 14:05 UTC
Environment: production
Endpoint: /api/orders
Release: build-2026-11-14
Cluster: production-cluster
Symptom: p95 70ms -> 650ms
```

Record user impact, error rate, affected tenants/regions, and recent changes.

### Step 2 — Atlas Metrics

Compare CPU, disk IOPS, connections, ops/s, and query targeting before vs. after the deploy. Split by node/replica set where possible.

### Step 3 — `mongostat`

```bash
mongostat --host=mongo1.example.net:27017 --rowcount=15 1
```

Inspect read/write mix, queues, connections, and cache. If the incident already ended, live `mongostat` won't capture it; rely on Atlas historical metrics.

### Step 4 — `mongotop` or Compass Performance

```bash
mongotop --host=mongo1.example.net:27017 --rowcount=15 1
```

Check whether `shop.orders` is the hot namespace. If not, verify the right node/secondary or time window.

### Step 5 — Query Profiler

Filter namespace `shop.orders` around 14:00–14:20 UTC for query shapes filtering `status` with a sort. Inspect `millis`, `docsExamined`, `keysExamined`, and `planSummary`.

### Step 6 — Compass Explain

```javascript
db.orders.find({ status: "FAILED" })
  .sort({ createdAt: -1 })
  .limit(20)
  .explain("executionStats");
```

If `COLLSCAN`, test a candidate index **on staging**. If already `IXSCAN` with high `keysExamined`, review index prefix and selectivity.

### Step 7 — Evaluate Candidate Change

```javascript
// Staging example only; do not run blindly in production.
db.orders.createIndex(
  { status: 1, createdAt: -1 },
  { name: "ix_status_createdAt" }
);
```

Check index size, write overhead, overall query mix, index build impact, and rollback plan.

### Step 8 — Measure Before and After

- HTTP p50/p95/p99.
- Query profiler latency.
- Keys/docs examined.
- CPU/disk/memory.
- Write latency.
- Connection pool wait.
- Error/retry rates.
- Replication lag and shard skew.

### Step 9 — Incident Report

Document verified root cause, user impact, fix, rollback procedure, before/after metrics, and new alerts to add.

---

## 22. Common Scenarios

### 22.1. Connection Storm After a Release

Atlas Connections jump from 400 to 4,000. Check:

1. App instance count.
2. Whether `MongoClient` is being recreated per HTTP request.
3. Connection pool `maxPoolSize`/`minPoolSize`.
4. Retry loops.
5. Active vs. queued clients.
6. Host CPU/network and auth failures.

Never conclude you need to scale MongoDB before checking client connection lifecycles.

### 22.2. Write-Heavy Collection After a Batch Job

`mongotop` shows high write time on `analytics.events`; `mongostat` `update/s` surges.

Check batch size, update filter indexes, document growth, index count, dirty cache, disk IOPS, and replication lag. Fixes include batching/throttling, query optimization, or rescheduling the job.

### 22.3. Secondary Lag While Primary Looks Healthy

Primary RTPP looks normal, yet one secondary lags 90 seconds. Inspect per-secondary CPU/disk/network, read preference, oplog window, and logs. Never use the primary panel as proof all members are healthy.

### 22.4. Query Has an Index Yet Remains Slow

Profiler shows `IXSCAN` alongside high `keysExamined` and large payloads. You may need a different compound index, projection, sort optimization, or smaller result bounds. Never treat stage name alone as final proof.

---

## 23. Three Types of Latency to Keep Distinct

1. `mongotop.read=500ms` is **cumulative read operation time** for that namespace during the sample.
2. Query Profiler `millis=500` is the **duration of one recorded operation**.
3. HTTP p95=500ms is the **95th percentile across many requests**, spanning network, app, driver, and database.

They are never interchangeable.

### 23.1. Mean Differs from p95/p99

If 99% of queries finish under 60 ms while 1% take 2 seconds, the mean looks fine while tail latency hurts users.

Measure:

- API requests/s and errors.
- HTTP p50/p95/p99.
- Database operation latency.
- Driver connection-pool waits.
- Timeouts and retries.
- External calls and serialization.

**Never estimate p99 from five lines of `mongostat`.**

### 23.2. Dropping Throughput Does Not Mean Improved Performance

If the API fails fast before querying the DB, `mongostat query/s` drops. Never report database improvement while user-facing errors are climbing.

---

## 24. Minimum Monitoring Dashboard

### 24.1. Infrastructure

| Chart | Purpose |
| --- | --- |
| CPU per node | Saturation |
| Disk free, IOPS, latency | Capacity and I/O |
| WiredTiger cache used/dirty | Cache pressure |
| Resident memory, swap | Memory |
| Connections, queued operations | Pool/queue pressure |
| Network in/out | Traffic and replication |

### 24.2. Database

| Chart | Purpose |
| --- | --- |
| Ops/s by type | Workload mix |
| Query targeting | Scan efficiency |
| Namespace latency / slow query shapes | Pinpoint bottlenecks |
| Replication lag / elections | Availability |
| Oplog window | Recoverability |
| Data / index size | Capacity |
| Sharding / Search metrics if applicable | Skew / index health |

### 24.3. Application

| Chart | Purpose |
| --- | --- |
| Endpoint p50/p95/p99 | User SLO |
| Error / timeout rate | Failure outcomes |
| Driver pool wait | App-side queuing |
| Queries / retries | Hidden load |
| Deployment markers | Correlate changes |
| Region / tenant breakdown | Prevent averages hiding hotspots |

A good dashboard lets you trace **symptom -> node -> namespace -> query shape -> request trace**.

---

## 25. Security, Cost, and Monitoring Limits

### 25.1. Query Logs Can Expose Sensitive Data

Profiler, `currentOp`, and `explain` can reveal:

- Collection and field names.
- Query literals, user IDs, emails.
- Internal topology.
- Application metadata.
- Tenant names or business identifiers.

Redact before attaching to tickets and restrict access to authorized roles.

### 25.2. Do Not Arbitrarily Profile All Operations

Self-managed MongoDB includes the database profiler. Example:

```javascript
// Do not run in production without a runbook and approval.
db.setProfilingLevel(2);
```

High profiling levels add CPU/disk overhead and write query values into `system.profile`. Choose levels and thresholds intentionally, or use Atlas tools and sampling where appropriate.

### 25.3. Queryable Encryption

Compass Performance does not show performance data for collections using Queryable Encryption under current limits. Atlas RTPP may hide/redact encrypted query details. Never disable encryption just to inspect query plaintext.

### 25.4. Operation Termination Privileges

Kill Op can abort transactions, reports, or index builds and trigger retries. Operations teams need incident runbooks and change approval; never grant kill privileges to read-only monitoring roles.

---

## 26. Common Mistakes

| Misconception | Reality |
| --- | --- |
| "`mongostat query=100` means 100 HTTP requests/s" | One request can issue multiple DB commands |
| "`mongotop total=900ms` means a 900 ms slow query" | It is cumulative namespace operation time |
| "`mongotop` shows % CPU per collection" | It reports read/write time |
| "`dirty=80%` means disk is full" | It is WiredTiger dirty cache percentage |
| "`used=95%` means memory leak" | Caches are designed to fill capacity |
| "`vsize` is physical RAM" | Virtual memory differs from resident memory |
| "Rising connections means DB bug" | Often app pooling or deployments |
| "`IXSCAN` guarantees a good index" | Can still scan huge numbers of keys |
| "`COLLSCAN` is always wrong" | Some full scans are intentional and valid |
| "Compass Performance keeps infinite history" | Primarily real-time |
| "Compass on `mongos` shows full node metrics" | Limited visibility via `mongos` |
| "Primary RTPP represents all secondaries" | Secondaries carry distinct workloads |
| "Performance Advisor suggested it, so create it right away" | Measure write, storage, and plan impact first |
| "No Advisor suggestions means no slow queries" | Subject to thresholds and sampling |
| "Atlas Free has every M10+ feature" | Tiers enforce feature limits |
| "`mongostat --discover` always finds hidden nodes" | Discovery has limits |
| "`mongotop --locks` works on modern MongoDB" | Legacy 2.6 and earlier only |
| "Profiler has zero overhead or privacy risk" | Carries both overhead and PII exposure |
| "Pausing Compass pauses the database" | Only pauses GUI refresh |
| "Atlas P95 equals HTTP P95" | Different scope and sampling |
| "Kill Op fixes slow queries" | Only stops the op and may trigger errors/retries |
| "A 1-second snapshot proves root cause" | Need timelines and correlated signals |

---

## 27. Hands-On Exercises

### Exercise 1 — Pick the Right Tool

Match these needs—viewing ops/s, finding hot collections, explaining query plans, alerting on disk—to `mongostat`, `mongotop`, Compass Explain, and Atlas Alerts.

**Answer:** `mongostat`, `mongotop`, Compass Explain, and Atlas Alerts respectively.

### Exercise 2 — Terminal or `mongosh`?

Why is `mongostat --rowcount=10 1` a terminal command rather than JavaScript inside `mongosh`?

### Exercise 3 — Polling

How many samples does `mongostat --rowcount=12 5` collect and at what interval in seconds? Is the `query` column a per-second rate or a 5-second sum?

**Answer:** 12 samples at a 5s interval; operation rates are normalized per second.

### Exercise 4 — Cache

Do `dirty=8%` and `used=94%` prove the disk is 94% full?

**Answer:** No; both are percentages of the WiredTiger cache maximum.

### Exercise 5 — Connections

`conn` spikes suddenly after a deploy. Name three possible causes tied to application connection pools.

### Exercise 6 — Replica Markers

What can `*` on operation counts and `command=3|120` on a secondary signify?

### Exercise 7 — Discovery

Why might `mongostat --discover` omit a hidden member?

### Exercise 8 — `-o` and `-O`

Distinguish `mongostat -o` from `-O`. Can both be used together?

**Answer:** `-o` outputs only specified fields while `-O` appends to defaults; they cannot be combined.

### Exercise 9 — `mongotop` 2500 ms

A 1s interval shows `read=2500ms`. Does that prove a single query took 2.5 seconds?

**Answer:** No; multiple concurrent operations can accumulate over 1,000 ms in one second.

### Exercise 10 — `--locks`

Why is `mongotop --locks` unsuitable for MongoDB 8.x?

### Exercise 11 — Missing Namespace

`mongotop` does not show `shop.products` in one sample. Can you say that collection wasn't queried all day?

**Answer:** No.

### Exercise 12 — Lab Explain

Run the lab query on `status` before and after creating `(status, createdAt)`. Record keys examined, docs examined, `nReturned`, and sort stage.

### Exercise 13 — Ratio

`docsExamined=200000`, `nReturned=50`. What is docs examined per returned?

**Answer:** 4,000.

### Exercise 14 — Wide `IXSCAN`

`keysExamined=500000` and `nReturned=5` despite `IXSCAN`. Why must you check compound index order and selectivity?

### Exercise 15 — Compass Performance

Name six metric groups provided by Compass Performance. Which one corresponds to `mongotop`?

### Exercise 16 — Compass `mongos`

What limitations does Compass Performance have when connected to `mongos`?

### Exercise 17 — Vector Search Explain

Does Compass display all `$vectorSearch` queries as a Visual Tree?

**Answer:** No.

### Exercise 18 — RTPP and Secondaries

Which replica set member does RTPP primarily report from? What should you do if the app routes heavy reads to secondaries?

### Exercise 19 — Metrics Granularity

A 20-second spike gets smoothed away on a 30-day chart. How do you narrow the view?

### Exercise 20 — Query Shapes

How are two queries differing only in literals grouped? When is shape grouping insufficient?

### Exercise 21 — Advisor

Performance Advisor recommends three indexes. Why measure write latency and index size before creating them?

### Exercise 22 — Query Insights p95

Atlas query p95 is low yet HTTP p95 is high. Name four causes outside DB operation execution.

### Exercise 23 — Alerts

Design a disk capacity alert with threshold, duration, owner, notification channel, and runbook.

### Exercise 24 — Replica Lag

One secondary lags 90s while the primary looks healthy. How do you inspect network, disk, read load, and oplog?

### Exercise 25 — Shard Skew

Three shards show 80/15/5% load split. List possible causes and checks.

### Exercise 26 — Incident

High CPU, `mongotop` hot on `orders`, profiler shows `COLLSCAN`, API p95 climbing. Outline your investigation order and safe optimization steps.

### Exercise 27 — `serverStatus` Rate

A counter increases by 600 over 10s; what is the average rate?

**Answer:** 60 operations/s assuming the same process with no restart.

### Exercise 28 — Profiling Security

Why shouldn't you run `db.setProfilingLevel(2)` directly in production and paste raw query samples into a public ticket?

### Exercise 29 — Alert Fatigue

A team has 200 alerts with no owners or runbooks. Propose how to reduce noise and align with SLOs.

### Exercise 30 — End-to-End Runbook

Design a workflow combining app tracing, Atlas Metrics, `mongostat`, `mongotop`, Query Profiler, Performance Advisor, and Compass Explain to resolve a post-deployment latency regression. Include rollback plans and before/after metrics.

---

## 28. Production Checklist

### Permissions and Security

- [ ] Database Tools and Compass versions are compatible with the server.
- [ ] Least-privilege monitoring roles exist for `serverStatus`/`top`/`currentOp`.
- [ ] Atlas Project viewers are not granted unneeded admin privileges.
- [ ] Connections use TLS; credentials never sit in logs or public URIs.
- [ ] Query samples and PII are redacted.
- [ ] No unapproved Kill Op or high-level profiling outside runbooks.

### Metrics and Dashboards

- [ ] Per-node CPU, disk, cache, and connections are tracked.
- [ ] Ops/s, query targeting, and slow query shapes are tracked.
- [ ] Replication lag, oplog window, and election logs are tracked.
- [ ] App p95/p99 latency, errors, and driver pool waits are tracked.
- [ ] Deployment and maintenance markers are annotated.
- [ ] Consistent UTC timestamps are enforced.
- [ ] Tier-specific sampling, retention, and feature limits are understood.

### Alerts and Investigation

- [ ] Capacity, availability, backup, and replication alerts match policy.
- [ ] Every alert has an owner, severity, notification channel, and runbook.
- [ ] Alert delivery and escalation are tested.
- [ ] Query optimization workflow follows Profiler -> Explain -> benchmark.
- [ ] Index changes undergo review and have rollback plans.
- [ ] Write and index overhead are measured when fixing read bottlenecks.
- [ ] Incident postmortems record before/after data.

---

## 29. Summary

**`mongostat`**, **`mongotop`**, **Compass**, and **Atlas Monitoring** provide distinct observational lenses:

1. **`mongostat`:** quick per-node view of operations/s, cache, queues, memory, network, and connections.
2. **`mongotop`:** identifies collections consuming read/write time; **never confuse** this cumulative total with single-query latency.
3. **Compass:** Performance GUI and Explain Plan to spot `COLLSCAN`/`IXSCAN`, keys/docs examined, and index impact.
4. **Atlas:** historical metrics, RTPP, Query Insights, Query Profiler, Performance Advisor, Sharding Insights, and alerts governed by tier, role, and version.
5. **No single tool isolates root cause alone:** connect evidence from user-facing latency -> cluster -> node -> namespace -> query shape -> Explain.
6. **Sound operations require safe monitoring, actionable alerts, and before/after verification.**

Always ask: **"What unit is this metric measuring, on which node, over what interval, and what evidence is still missing?"** That is the foundation of MongoDB observability.

### Official MongoDB Documentation

- [`mongostat` — Database Tools](https://www.mongodb.com/docs/database-tools/mongostat/) — options, polling, fields, discovery, and JSON.
- [`mongostat` Examples](https://www.mongodb.com/docs/database-tools/mongostat/mongostat-examples/) — `-o`, `-O`, interval, and rowcount.
- [`mongotop` — Database Tools](https://www.mongodb.com/docs/database-tools/mongotop/) — namespace read/write times, JSON, and privileges.
- [`mongotop` Examples](https://www.mongodb.com/docs/database-tools/mongotop/mongotop-examples/) — output and frequency.
- [Compass: View Real-Time Performance](https://www.mongodb.com/docs/compass/performance/) — Operations, Hottest Collections, Slowest Operations.
- [Compass: View Query Performance](https://www.mongodb.com/docs/compass/query-plan/) — Explain Visual Tree and Raw Output.
- [Atlas: Monitor Clusters](https://www.mongodb.com/docs/atlas/monitoring-alerts/) — metrics, alerts, logs, and integrations.
- [Atlas: Real-Time Performance Panel](https://www.mongodb.com/docs/atlas/real-time-performance-panel/) — per-node real-time view.
- [Atlas: Analyze Slow Queries](https://www.mongodb.com/docs/atlas/analyze-slow-queries/) — Query Insights, Query Profiler, Advisor, Sharding Insights.
- [Atlas: Query Profiler](https://www.mongodb.com/docs/atlas/tutorial/query-profiler/) — slow operations and targeting.
- [Atlas: Performance Advisor](https://www.mongodb.com/docs/atlas/performance-advisor/) — index recommendations.
- [Atlas: Configure Alerts](https://www.mongodb.com/docs/atlas/configure-alerts/) — conditions, notifications, permissions.
- [Atlas: Alert Basics](https://www.mongodb.com/docs/atlas/alert-basics/) — alert lifecycle.
- [Analyze Query Performance](https://www.mongodb.com/docs/manual/tutorial/evaluate-operation-performance/) — methods and profiling.
- [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — execution plans and statistics.
- [`serverStatus`](https://www.mongodb.com/docs/manual/reference/command/serverStatus/) — node counters.
- [`top`](https://www.mongodb.com/docs/manual/reference/command/top/) — collection time.
- [`$currentOp` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/currentOp/) — current operations.
- [Database Profiler](https://www.mongodb.com/docs/manual/tutorial/manage-the-database-profiler/) — profiling considerations.
- [Replica Set Status](https://www.mongodb.com/docs/manual/reference/command/replSetGetStatus/) — replication health.
