# Structured Logs, Slow Query Logs, and Appropriate Verbosity Levels in MongoDB

> **Module:** MongoDB Document Database Engine  
> **Chapter:** Observability  
> **Lesson:** Structured Logs, Slow Query Logs, and Appropriate Verbosity Levels

## 1. Problem: The Application Is Slow—What Is MongoDB Saying?

An ordering service backed by MongoDB reports rising latency: the order-listing API jumps from 50 ms to 2 seconds, yet application CPU does not rise correspondingly. The operations team needs to answer:

- Is MongoDB generating slow queries?
- Which commands are slow, and on which collections?
- How many documents and index keys did MongoDB scan?
- Are `COLLSCAN`s, large sorts, lock waits, or replication lag occurring?
- When did slow queries start, on which instance, and for which request?
- Can we increase log detail to investigate without filling the disk or exposing customer data?
- Should we enable the database profiler, or is the server diagnostic log sufficient?
- When the incident ends, how do we lower log levels and restore sampling?

The answer is not "turn everything up to verbosity 5." MongoDB provides observability sources with **different levels of detail, scope, and cost**.

```text
Application / Java Driver
    │
    │ request, command, latency, opaque traceId
    ▼
MongoDB mongos / mongod
    │
    ├─ JSON diagnostic log:
    │    INFO / WARNING / ERROR / DEBUG
    │    component, message id, context, attributes
    │
    ├─ Slow-operation log:
    │    command + namespace + duration + plan summary
    │    keysExamined, docsExamined, nreturned ...
    │
    ├─ Database profiler (mongod):
    │    system.profile capped collection per database
    │
    └─ Other metrics / diagnostics:
         serverStatus, explain, currentOp,
         FTDC, managed monitoring
    │
    ▼
Log collector / Monitoring / Alerting
    │
    └─ Analysis: timestamp, host, namespace,
       query shape, component, latency, error
```

**Core message:** Use **structured diagnostic logs** for broad visibility, **slow-operation logging** to catch slow commands, the **profiler** when controlled detail is needed, and **`explain`/metrics** to verify root causes. Choose verbosity, thresholds, and sampling deliberately, and revert debug settings once the investigation concludes.

### 1.1. Learning Outcomes

After this lesson, you will be able to:

1. Recognize MongoDB's JSON logging structure: `t`, `s`, `c`, `id`, `ctx`, `msg`, `attr`.
2. Distinguish warning/error logs from slow-operation logs and the profiler.
3. Read a slow query entry: namespace, command, duration, plan, keys/documents examined.
4. Understand `slowOpThresholdMs`, `slowOpSampleRate`, and profiler levels 0/1/2.
5. Choose targeted component verbosity rather than enabling server-wide debug logging.
6. Use `getProfilingStatus()`, `setProfilingLevel()`, `system.profile`, and `explain("executionStats")` in a lab.
7. Correlate Java Driver command monitoring with server-side logs without logging passwords or sensitive data.
8. Distinguish logs across `mongod`, `mongos`, replica sets, and sharded clusters.
9. Design retention, rotation, parsing, sampling, access controls, and alerting.
10. Write a latency-spike runbook and know when to dial verbosity back down.

---

## 2. Three Information Sources Often Lumped Together as "MongoDB Logs"

| Source | Purpose | Where it lives | Scope | Cost to watch |
|---|---|---|---|---|
| **Diagnostic log** | Server state, warnings, errors, debug, slow operations | stdout/stderr or file, per config | Per `mongod`/`mongos` process | Disk space, I/O, data sensitivity |
| **Slow-operation log** | Flags operations deemed slow | Usually a message type inside the diagnostic log | Per server process/threshold/filter | High volume when threshold is low |
| **Database profiler** | Records detailed profiles for selected operations | `system.profile` collection in a database | Per database on `mongod` | CPU, disk writes, capped storage |
| **Metrics/FTDC** | Trends in CPU, memory, cache, opcounters, locks, queues | Monitoring or diagnostic capture data | Process/host/cluster | Sampling, collection, retention |
| **Driver/application log** | Requests/traces, network + driver latency, retries | Service logs/tracing | Client/service | Sensitive data, cardinality, volume |

**The slow query log is not a separate file by default.** MongoDB typically writes slow-operation messages into the **server diagnostic log**. Depending on log destination, operators see them in `mongod.log`, container logs, or a provider-managed observability UI.

### 2.1. Diagnostic Log

Messages covering:

- Startup and shutdown.
- Network/TLS connections.
- Authentication and authorization.
- Replication, elections, and sharding.
- Storage and checkpoints.
- Query and command execution.
- Warnings when resources near limits.
- Errors and troubleshooting info.

Not every message is a query; many are critical for explaining slow queries caused by infrastructure or cluster state.

### 2.2. Slow-Operation Log

A message about a command whose latency exceeded the configured threshold or matched the configured filter/sampling.

For example, it may report:

- `ns`: `shop.orders`.
- `command`: `find`.
- `planSummary`: `COLLSCAN`.
- `docsExamined`: 250,000.
- `nreturned`: 20.
- `durationMillis`: 863.

It provides a strong lead for running `explain` and checking indexes/query shapes, but **does not by itself prove every cause** of latency.

### 2.3. Database Profiler

The MongoDB profiler writes records into `system.profile`. It is **data stored inside MongoDB**, not the plain-text `mongod.log` file. This collection is capped and records version-specific details.

The profiler is useful for targeted investigation, but level 2 must not be left enabled unbounded on heavy workloads.

### 2.4. Does Disabling the Profiler Still Emit Slow Query Logs?

**Yes, it can.** Profiling level `0` means **do not write operation profiles into `system.profile`**, yet slow operations can still be logged to the diagnostic log according to threshold, sample rate, and filter settings.

Remember this distinction:

```text
Profiling level = 0
    ├─ system.profile: no operation profile records written
    └─ diagnostic log: slow-operation messages can still be written
```

---

## 3. Structured Logging: How MongoDB Writes JSON Logs

Modern MongoDB versions support **structured logging** as line-delimited JSON. MongoDB 4.4 introduced structured JSON diagnostic logging to the server.

**Abbreviated illustrative example** (fields vary by version, command type, and execution engine):

```json
{
  "t": {
    "$date": "2026-11-14T08:20:12.483+00:00"
  },
  "s": "I",
  "c": "COMMAND",
  "id": 51803,
  "ctx": "conn241",
  "msg": "Slow query",
  "attr": {
    "type": "command",
    "ns": "shop.orders",
    "command": {
      "find": "orders",
      "filter": {
        "status": "PENDING"
      },
      "$db": "shop"
    },
    "planSummary": "COLLSCAN",
    "keysExamined": 0,
    "docsExamined": 250000,
    "nreturned": 20,
    "durationMillis": 863
  }
}
```

**Do not assume every MongoDB release returns these exact fields.** This sample illustrates structural meaning, not a mandatory schema for every log event.

### 3.1. Top-Level Fields

| Field | Meaning | Example |
|---|---|---|
| `t` | Log event timestamp, usually Extended JSON Date | `{"$date":"..."}` |
| `s` | Severity | `I`, `W`, `E`, `D1` |
| `c` | Component/subsystem | `COMMAND`, `NETWORK`, `REPL` |
| `id` | Numeric message identifier for the message type | `51803` |
| `ctx` | Execution context/connection/thread | `conn241` |
| `msg` | Human-readable message text | `Slow query` |
| `attr` | Structured attributes, event-specific | `ns`, `durationMillis`, etc. |
| `tags` | Optional classification tags; not on every event | List of classification tags |

### 3.2. `t`: Timestamp

Timestamps are used to:

- Compare error occurrence times.
- Align with CPU, I/O, and replication metrics.
- Identify before/after deployment boundaries.
- Build an incident timeline.

Normalize timezones in the log pipeline—typically UTC in centralized logging. Never mix server, client, and dashboard timestamps without timezone conversion.

### 3.3. `s`: Severity

Common symbols:

| Severity | Meaning |
|---|---|
| `F` | Fatal |
| `E` | Error |
| `W` | Warning |
| `I` | Informational |
| `D1` to `D5` | Debug levels depending on verbosity |

An `I` message named `Slow query` can still represent a critical performance problem. Never filter solely for `E`/`W` and conclude there are no slow queries.

### 3.4. `c`: Component

The log component identifies the subsystem emitting the message. Examples:

- `COMMAND`: command execution and slow-operation entries.
- `NETWORK`: connections, sockets, TLS.
- `ACCESS` (or access-control categories depending on version): authentication/authorization.
- `REPL`: replication.
- `STORAGE`: storage engine.
- `SHARDING`: sharded cluster.
- `QUERY`: query execution/planning in specific contexts.
- `INDEX`: index builds and operations.

Exact component lists vary by MongoDB version. Consult docs for your running version instead of hardcoding all components.

### 3.5. `id` Is a Message Type Identifier, Not a Request ID

For example, `id: 51803` can appear on **many** slow query entries.

It identifies the **message type**, not a unique request like an application trace ID.

To distinguish individual events, use timestamp, host/process, context, namespace, and available correlation fields.

### 3.6. `ctx` Is the Execution Context

`ctx` represents the connection or thread context, such as `conn241`. It helps correlate messages on the same connection over a period.

However:

- Connection pools reuse the same connection across many requests.
- One application request can issue multiple MongoDB commands.
- Retries and `getMore` complicate the sequence.
- `ctx` is not a system-wide end-to-end trace ID.

Do not treat `conn241` as a transaction ID or business request ID.

### 3.7. `msg` and `attr`

`msg` is a standardized summary string; `attr` holds structured details for machine parsing.

Example:

```json
{
  "msg": "Slow query",
  "attr": {
    "ns": "shop.orders",
    "planSummary": "IXSCAN { customerId: 1, createdAt: -1 }",
    "keysExamined": 84500,
    "docsExamined": 84500,
    "nreturned": 10,
    "durationMillis": 377
  }
}
```

Do not rely on fragile substring matching across whole log lines when a parser can extract structured JSON fields.

---

## 4. Why Structured Logs Benefit Observability

Before structured logs, extracting data depended on regexes over long text lines that broke whenever formats changed.

With JSON logs, you can query:

- `s="E"` over the past 5 minutes.
- `c="REPL"` and specific message IDs.
- `msg="Slow query"` with `attr.ns="shop.orders"`.
- Histograms of `attr.durationMillis`.
- Top namespaces with high `docsExamined / max(nreturned, 1)`.
- Error counts by component, host, or replica set member.

### 4.1. A Log Event May Lack `attr`

Not every message contains `attr` or every nested field. Log pipelines must handle optional fields gracefully.

### 4.2. Truncated Log Indicators

Large values—especially command/query documents—can be **truncated** due to log message size limits and redaction. Never assume `attr.command` is a complete, verbatim copy of the query.

Never replay a query blindly from slow logs when:

- The command was truncated.
- Fields contain sensitive data.
- Context such as read concern or transaction state is incomplete.
- Logged parameters were redacted.
- The query mutates or deletes data.

### 4.3. Log Schemas Are Not Immutable Contracts

Across MongoDB versions, the server may:

- Add or remove fields.
- Change how query identifiers are represented.
- Emit different fields between the classic engine and Slot-Based Execution.
- Change message text or IDs.
- Adjust details for reads, writes, or `getMore`.

Build resilient parsers: treat fields as optional, retain raw messages per policy, and test parsers during MongoDB upgrades.

### 4.4. Message IDs Are More Stable Than Text, Yet Still Versioned

Numeric log IDs help categorize events, but never assume every version shares the exact same event structure. Combine `id` with `msg`, `c`, and server version for classification.

---

## 5. What Is the Slow Query Log?

Although commonly called the **slow query log**, MongoDB actually logs **slow operations**—not only `find`.

Logged operations can include:

- `find`.
- `aggregate`.
- `update`.
- `delete`.
- `findAndModify`.
- `getMore` for cursors.
- Other commands and operations depending on version.

An operation exceeding the configured logging/profiling threshold emits an entry in the diagnostic log.

### 5.1. Slow Does Not Necessarily Mean Broken

For example, an analytical report query is expected to take 5 seconds, whereas a transactional API has a 100 ms SLO.

The same 100 ms threshold can be:

- Too sensitive for analytical batches.
- Too loose for latency-sensitive APIs.
- Too noisy on high-volume workloads.
- Blind to multiple 80 ms queries adding up to a 300 ms request.

Thresholds must align with **each workload's SLO**, not just server defaults.

### 5.2. Common Threshold

MongoDB provides:

```yaml
operationProfiling:
  slowOpThresholdMs: 100
```

100 ms is a common default slow-operation threshold in many versions, but **always verify the actual configuration** on your server or managed provider.

### 5.3. Sampling

A system with 100,000 slow operations/hour generates massive log volume.

```yaml
operationProfiling:
  slowOpSampleRate: 0.1
```

A value of `0.1` samples roughly 10% under the supported version's sampling mechanism—**not an exact guarantee of 10 out of every 100 operations per collection**.

Sampling cuts volume and overhead, yet:

- It can miss rare events.
- It cannot prove "no slow queries occurred."
- It is unsuitable if exact per-operation auditing is required.
- Alerting must factor in the sampling rate.
- Percentiles computed from sampled logs can skew if the sample is unrepresentative.

### 5.4. Thresholds and Sampling Are Not a Free Debugger

Lowering the threshold from 100 ms to 0 ms on a system handling 100,000 ops/s turns the server log into a massive flood.

Never run ultra-low thresholds in production for long periods without accounting for log volume, collector throughput, and disk capacity.

---

## 6. Profiler Levels: 0, 1, and 2

MongoDB's **database profiler** has three standard levels:

| Level | Meaning | When to use |
|---|---|---|
| `0` | Disables writing profile records to `system.profile` | Default / normal operation; slow-operation logs still apply |
| `1` | Profiles slow operations matching threshold/sample or filter | Controlled investigation |
| `2` | Profiles all operations tracked by the profiler | Lab or very brief investigation; watch overhead |

**Critical point:** Level `0` does not stop the diagnostic log from recording slow operations.

### 6.1. Profiling Mode in Config Files

Self-managed `mongod.conf` example:

```yaml
operationProfiling:
  mode: off
  slowOpThresholdMs: 100
  slowOpSampleRate: 1.0
```

Config mode values typically include:

- `off`: profiler does not write to `system.profile`.
- `slowOp`: profile slow operations.
- `all`: profile all operations.

The CLI/`mongosh` equivalents are numeric levels `0`, `1`, and `2`.

### 6.2. Changing Profiling Level in `mongosh`

Assuming an authorized lab environment:

```javascript
const lab = db.getSiblingDB("observability_lab");

// Check current status first.
printjson(lab.getProfilingStatus());

// Enable profiler for slow operations in the lab.
lab.setProfilingLevel(1, {
  slowms: 100,
  sampleRate: 1.0
});
```

To disable the profiler after testing:

```javascript
lab.setProfilingLevel(0);
```

**Do not simply assume it started at level 0.** Record the prior configuration before changing anything and restore the exact threshold, sample rate, and filter values per your runbook.

### 6.3. Level 2 Is Resource-Intensive

```javascript
// Only in a small, authorized lab environment.
lab.setProfilingLevel(2);
```

Profiling level 2 generates heavy profile writes and extra write load. Never enable it production-wide for extended periods just to "collect extra just in case."

### 6.4. Filter Mechanism

Some MongoDB versions support configuring a profiler filter to select operations matching specific criteria.

When `filter` is set, its interaction with `slowms`/`sampleRate` can **differ from normal threshold logic**; documentation notes that `filter` can take precedence over those thresholds in certain configurations.

Therefore, do not assume `slowms`/`sampleRate` still cap profile/slow-log volume as usual when a `filter` is active. Read version-specific docs and test in a lab.

### 6.5. Profiler on `mongos`?

The database profiler runs on `mongod` using `system.profile`. **You cannot enable database profiling on `mongos` the way you do on `mongod`**: `mongos` has no per-database `system.profile` collection.

In a sharded cluster, collect diagnostic logs and diagnostics across `mongos` and shards per topology.

---

## 7. Creating an Observability Lab Without Dangerous Load

The following exercise uses a tiny collection. Never intentionally craft malicious queries to force MongoDB to stall.

### 7.1. Lab Data

In `mongosh` connected to a lab MongoDB instance:

```javascript
const lab = db.getSiblingDB("observability_lab");
const orders = lab.getCollection("orders");

orders.insertMany([
  {
    _id: 1, tenantId: "t1", customerId: "C001",
    status: "PENDING", amount: 120000,
    createdAt: ISODate("2026-11-01T08:00:00Z")
  },
  {
    _id: 2, tenantId: "t1", customerId: "C002",
    status: "PAID", amount: 560000,
    createdAt: ISODate("2026-11-01T09:00:00Z")
  },
  {
    _id: 3, tenantId: "t1", customerId: "C001",
    status: "PENDING", amount: 80000,
    createdAt: ISODate("2026-11-02T08:00:00Z")
  },
  {
    _id: 4, tenantId: "t1", customerId: "C003",
    status: "CANCELLED", amount: 140000,
    createdAt: ISODate("2026-11-02T09:00:00Z")
  },
  {
    _id: 5, tenantId: "t2", customerId: "C090",
    status: "PAID", amount: 250000,
    createdAt: ISODate("2026-11-03T08:00:00Z")
  },
  {
    _id: 6, tenantId: "t2", customerId: "C091",
    status: "PENDING", amount: 175000,
    createdAt: ISODate("2026-11-03T09:00:00Z")
  },
  {
    _id: 7, tenantId: "t1", customerId: "C001",
    status: "PAID", amount: 310000,
    createdAt: ISODate("2026-11-04T08:00:00Z")
  },
  {
    _id: 8, tenantId: "t1", customerId: "C002",
    status: "PENDING", amount: 220000,
    createdAt: ISODate("2026-11-04T09:00:00Z")
  },
  {
    _id: 9, tenantId: "t2", customerId: "C090",
    status: "PAID", amount: 199000,
    createdAt: ISODate("2026-11-05T08:00:00Z")
  },
  {
    _id: 10, tenantId: "t1", customerId: "C004",
    status: "PENDING", amount: 275000,
    createdAt: ISODate("2026-11-05T09:00:00Z")
  }
]);

print("Orders:", orders.countDocuments({}));
```

This sample dataset has **10 documents**. Run `insertMany` once on an empty lab database; re-running will trigger duplicate `_id` errors. Never run `dropDatabase()` on a database holding data that must be kept.

### 7.2. Testing Queries

```javascript
printjson(orders.find({
  tenantId: "t1",
  status: "PENDING"
}).toArray());

printjson(orders.find({
  customerId: "C001"
}).sort({ createdAt: -1 }).toArray());
```

### 7.3. Creating Candidate Indexes

```javascript
orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "idx_tenant_status_created" }
);

orders.createIndex(
  { customerId: 1, createdAt: -1 },
  { name: "idx_customer_created" }
);

printjson(orders.getIndexes());
```

These two indexes illustrate the lab query patterns—not a recommendation to add both to every production collection.

---

## 8. Reading Existing Logs Before Changing Configuration

### 8.1. Self-Managed Server on Linux

If MongoDB writes diagnostic logs to a file, such as:

```text
/var/log/mongodb/mongod.log
```

inspect logs using OS tools per permissions:

```bash
tail -n 100 /var/log/mongodb/mongod.log
```

If the service logs to stdout/stderr via systemd or containers, inspect journal or container logs accordingly.

### 8.2. `systemLog.destination`

Reference self-managed configuration:

```yaml
systemLog:
  destination: file
  path: /var/log/mongodb/mongod.log
  logAppend: true
  verbosity: 0
  timeStampFormat: iso8601-utc
```

Meaning:

- `destination: file`: server writes to a log file.
- `path`: file path.
- `logAppend`: appends on server startup per configuration.
- `verbosity: 0`: normal logging level, not full debug.
- `timeStampFormat`: timestamp format for logs among supported modes.

Depending on deployment, logs may go to stdout/container collectors instead of a file, and options may be managed by the hosting service.

### 8.3. `getLog` Does Not Replace Persistent Log Files

If the account has sufficient privileges:

```javascript
db.getSiblingDB("admin").runCommand({
  getLog: "global"
});
```

`getLog` returns entries from the server's **in-memory log buffer**, not complete persistent history.

Use it for quick inspection of recent messages, never as a substitute for persistent log storage or centralized log aggregation.

### 8.4. Atlas / Managed MongoDB

On MongoDB Atlas, log access, the Profiler UI, the Real-Time Performance Panel, and metrics depend on cluster tier and service features. Having a database user does not grant shell access to edit `mongod.conf`.

Use provider-supported log tools, metrics, and APIs. Never assume every Atlas tier allows profiler level 2 or downloading all raw log files.

---

## 9. Configuring Slow-Operation Threshold and Sampling

Example config for a **self-managed lab server**:

```yaml
systemLog:
  destination: file
  path: /var/log/mongodb/mongod.log
  logAppend: true
  verbosity: 0

operationProfiling:
  mode: off
  slowOpThresholdMs: 100
  slowOpSampleRate: 1.0
```

This is an illustrative configuration: the profiler is off, yet MongoDB still logs slow operations above the threshold to the diagnostic log.

### 9.1. When Is a 100 ms Threshold Appropriate?

Good as an observation starting point, though not universally ideal for every application:

- Ordering API with a 100 ms SLO: a 70 ms query already consumes most of the budget.
- Batch analytics with a 1-minute SLO: a 500 ms query can be normal.
- Remote client: high network latency is not captured in server operation duration.

Always correlate with metrics, traces, and service targets.

### 9.2. Reducing Sampling

```yaml
operationProfiling:
  mode: off
  slowOpThresholdMs: 100
  slowOpSampleRate: 0.25
```

Setting `0.25` reduces logged/profiled events under supported sampling. Useful under heavy traffic, though rare events may be missed.

### 9.3. Threshold Set Too Low

Example misconfiguration during peak hours:

```yaml
operationProfiling:
  slowOpThresholdMs: 0
  slowOpSampleRate: 1.0
```

This makes virtually every operation eligible for slow logging, causing:

- Huge log volume surges.
- Spikes in disk and collector bandwidth.
- Higher ingest and storage costs.
- Heavy alert noise.
- Significant CPU and logging overhead.

Use ultra-low thresholds only in isolated labs or tightly bounded debug windows.

### 9.4. Thresholds Are a Process-Level Concern

Changing threshold or sample rate can impact more than one query or database. Runtime methods and server configs have version-specific scope and semantics.

Before making changes:

1. Record the current setting.
2. Assess impact on other databases sharing the same process.
3. Announce the change window.
4. Set an automatic end time and rollback runbook.
5. Watch log volume immediately after enabling.

Never lower the production threshold just so someone can "collect a few extra query samples" without evaluating the impact on other workloads.

---

## 10. Using `mongosh` to Adjust the Profiler in the Lab

### 10.1. Viewing Configuration

```javascript
const lab = db.getSiblingDB("observability_lab");

printjson(lab.getProfilingStatus());
print("Level:", lab.getProfilingLevel());
```

Illustrative output:

```json
{
  "was": 0,
  "slowms": 100,
  "sampleRate": 1,
  "ok": 1
}
```

Field names and options may differ when a version supports `filter`.

### 10.2. Enabling Slow-Operation Profiling

```javascript
lab.setProfilingLevel(1, {
  slowms: 50,
  sampleRate: 1.0
});
```

Re-read to confirm:

```javascript
printjson(lab.getProfilingStatus());
```

### 10.3. Querying Profile Records

```javascript
lab.system.profile
  .find({
    ns: "observability_lab.orders"
  })
  .sort({ ts: -1 })
  .limit(10)
  .pretty();
```

If no records appear, **that does not mean no queries ran**. Possibilities include:

- No query was slow enough.
- Sampling skipped it.
- The profiler was not enabled.
- The query executed on a different process/node.
- The user lacks privileges to read `system.profile`.
- The capped collection overwrote older records.
- A profiling filter excluded those operations.

### 10.4. Disabling Profiling After the Lab

```javascript
lab.setProfilingLevel(0);
```

If non-default threshold, sample rate, or filter values were set previously, restore them from your recorded snapshot rather than merely lowering the level. Disabling the profiler does not completely turn off slow logging.

### 10.5. Never Use Level 2 on Busy Environments

```javascript
// Consider only in an isolated lab.
lab.setProfilingLevel(2);
```

Level 2 generates heavy writes into `system.profile`; watch CPU/storage and keep collection windows short.

### 10.6. Lab Environments Might Not Produce Slow Records

10 documents return in a few milliseconds, well under 50/100 ms. Never introduce artificial locks or ReDoS queries on shared environments just to trigger a slow query log.

Instead, you can:

- Inspect a safely saved sample log.
- Use `explain("executionStats")` to study performance counters.
- In an **isolated, authorized local lab**, temporarily lower `slowms` briefly, then revert carefully.
- Use an authorized representative dataset rather than real production data.

---

## 11. Important Fields in a Slow Query Entry

For a slow-operation event, useful attributes typically include:

| Field | Interpretation | Caveat |
|---|---|---|
| `ns` | Namespace, e.g., `shop.orders` | Identifies collection/context |
| `type` | Command/op type | Not present on every message |
| `command` | Recorded portion of command/query | May be truncated, redacted, or hold sensitive data |
| `planSummary` | Plan summary | Does not replace full `explain` |
| `keysExamined` | Index keys examined | High count is not always bad; compare to `nreturned` |
| `docsExamined` | Documents examined | High count can indicate wide scan |
| `nreturned` | Result count | Semantics differ for writes and `getMore` |
| `durationMillis` | Server-side duration | Does not equal client end-to-end latency |
| `numYields` | Number of times the operation yielded | Cannot prove lock contention from one number alone |
| `reslen` | Response length (when present) | Large payloads increase network cost |
| `locks` | Lock details for the operation | Interpret per event/version |
| `storage` | Storage statistics (when present) | Not in every log event |
| `planningTimeMicros` | Query planning time (when present) | May be absent |
| Query/plan shape identifiers | Group queries sharing a shape | Field names/types vary by version |

**Never treat `durationMillis` as the entire time a user waited.** Application latency also includes connection checkout, server selection, network, serialization, retries, pagination, and business logic.

### 11.1. High `docsExamined`, Low `nreturned`

Example:

```text
planSummary     = COLLSCAN
docsExamined    = 600000
keysExamined    = 0
nreturned       = 8
durationMillis  = 985
```

This is suspicious because MongoDB examined 600,000 documents to return only 8.

Investigation steps:

1. Inspect the query filter and sort.
2. Run `explain("executionStats")`.
3. Evaluate an index matching equality, sort, and range predicates.
4. Verify whether the real query accidentally omitted a tenant predicate.
5. Benchmark on representative data.
6. Create an index only after weighing write and storage overhead.

### 11.2. Even `IXSCAN` Can Be Slow

Example:

```text
planSummary     = IXSCAN { status: 1 }
keysExamined    = 400000
docsExamined    = 400000
nreturned       = 150000
durationMillis  = 1300
```

Here MongoDB used an index yet still read and returned massive data. Causes include a low-selectivity filter or an unpaginated API.

**Having an index does not guarantee a fast query.**

### 11.3. `docsExamined = 0` Is Not Guaranteed Fast Either

A query can read mostly index entries and scan vast numbers of keys—or wait on locks, replication, or network—so `docsExamined=0` does not guarantee low latency.

Read counters together rather than judging from one metric alone.

### 11.4. Sorting and Result Limits

A slow query may exhibit:

- A `planSummary` showing an index scan that still requires an in-memory/blocking sort.
- Large `nreturned`.
- Huge response documents.
- Pagination using large `skip` values.
- An index order misaligned with the sort order.

Inspect the query shape and `explain` instead of merely indexing a single filter field.

---

## 12. `getMore`: Why Is the API Slow When the Initial `find` Was Fast?

MongoDB uses cursors for many queries. An application runs `find()`, then the driver issues `getMore` calls for subsequent batches.

```text
Application find()
   │
   ├─ find command  ──> firstBatch
   │
   ├─ getMore       ──> secondBatch
   │
   ├─ getMore       ──> thirdBatch
   │
   └─ cursor exhausted
```

A `getMore` can be slow due to:

- Large batch sizes.
- Ongoing scanning or computation.
- Network traffic.
- Cursor or aggregation workloads.
- Server load and concurrent operations.

If you only search logs for `find`, you will miss `getMore` entries driving overall latency.

### 12.1. Cursor Batch Size

Example:

```javascript
const docs = db.getSiblingDB("observability_lab")
  .orders
  .find({ tenantId: "t1" })
  .batchSize(2)
  .toArray();

print("Fetched:", docs.length);
```

Batch size affects server round trips, though not every batch creates a slow log entry. Small lab queries are usually far too fast.

### 12.2. Aggregations Also Use `getMore`

An `aggregate` cursor returns results in batches. A long-running pipeline can show up across separate command and `getMore` entries.

When analyzing total API latency, tie batches sharing the same operation context together where available rather than treating each log line as an independent API request.

---

## 13. Using `explain` to Verify Clues from Logs

Slow logs show **symptoms that occurred**. `explain` shows how the planner intends to execute—and executes—a matching query.

### 13.1. `find` Example

```javascript
const lab = db.getSiblingDB("observability_lab");

const explainResult = lab.orders
  .find({
    tenantId: "t1",
    status: "PENDING"
  })
  .sort({ createdAt: -1 })
  .explain("executionStats");

printjson(explainResult.queryPlanner);
printjson(explainResult.executionStats);
```

### 13.2. Metrics to Compare

| Slow log | Explain | Meaning |
|---|---|---|
| `planSummary` | `winningPlan` | Helps identify scan type |
| `docsExamined` | `totalDocsExamined` | Documents scanned |
| `keysExamined` | `totalKeysExamined` | Index keys scanned |
| `nreturned` | `nReturned` | Result count |
| `durationMillis` | `executionTimeMillis` | Not the exact same absolute measurement |
| Query command | Query filter/sort/projection | Must reproduce an equivalent shape |

### 13.3. Why Can Logs and `explain` Differ?

- Data changed after the log was written.
- A new index was created.
- The query plan cache changed.
- Different parameters or selectivity.
- Different host, shard, or primary/secondary.
- Client network latency is excluded from server `explain`.
- One execution involved cursor/`getMore`, while `explain` inspects the query shape.
- Runtime concurrency load shifted.
- Server version or optimizer engine changed.

Never run `explain` after an incident and assert it is **guaranteed** to be the exact plan that ran during the incident.

### 13.4. Be Careful Running `explain` on Write Commands

Never replay a `deleteMany`, `updateMany`, or migration script from slow logs directly on production.

To investigate, use `explain` methods supported by your API and environment, or test on a data copy, avoiding operations that mutate live data.

### 13.5. Query Shape Differs from Literal Parameters

Two queries:

```javascript
{ tenantId: "t1", status: "PENDING" }
{ tenantId: "t2", status: "PAID" }
```

share a query shape yet may differ dramatically in selectivity. When aggregating slow logs, distinguish:

- Stable query shapes for grouping issues.
- Distribution of input values.
- Index selectivity.
- Per-tenant workload.

If a log pipeline groups everything by shape without considering selectivity, you may overlook a single tenant with skewed data.

---

## 14. Distinguishing Server Latency from Application Latency

Suppose metrics show:

```text
HTTP request latency:       1400 ms
MongoDB command duration:    320 ms
Other application work:      900 ms
Network/queue/retry:         180 ms
```

These illustrative numbers show that `slow log durationMillis` **does not necessarily equal HTTP latency**.

Conversely:

```text
HTTP request latency:       2000 ms
MongoDB command duration:   1780 ms
Application work:            220 ms
```

shows MongoDB likely accounts for most of the latency budget.

### 14.1. What Do Server-Side Slow Logs Observe?

The server observes database-side operations using MongoDB's internal counters and timers.

### 14.2. What Does Driver Command Monitoring Observe?

The driver sees command duration from client-side measurement, including some driver/network overhead; it does not capture the entire HTTP request or server internals.

### 14.3. What Do APM Traces Observe?

Per-request Application Performance Monitoring / distributed tracing captures:

- Inbound HTTP span.
- Business logic.
- Connection pool waits.
- MongoDB command spans.
- Retries.
- External API calls.

Combining all three sources beats relying on any single number.

### 14.4. Few Slow Queries Do Not Rule Out a Performance Problem

Reasons include:

- Threshold set too high.
- Low sample rate.
- Bottleneck in connection checkout or network.
- Query timed out before being logged as expected.
- Bottleneck resides in application code.
- Inspecting logs from the wrong process, shard, or timezone.
- Managed provider limits log visibility.
- Slowdown occurred only in `getMore`, commit, or write concern waits.

---

## 15. Reading Logs on Linux and Containers

### 15.1. Diagnostic Log File

If file logging is configured and you have read permissions:

```bash
tail -n 200 /var/log/mongodb/mongod.log
```

Simple text filtering:

```bash
grep -F '"msg":"Slow query"' /var/log/mongodb/mongod.log
```

However, raw `grep` depends on JSON formatting and varies across versions/messages. Use a structured parser or log platform when analyzing across versions.

### 15.2. `jq` on JSON Lines

Illustrative command:

```bash
jq -c 'select(.msg == "Slow query") | {
  timestamp: .t["$date"],
  component: .c,
  context: .ctx,
  namespace: .attr.ns,
  durationMillis: .attr.durationMillis,
  docsExamined: .attr.docsExamined,
  keysExamined: .attr.keysExamined,
  nreturned: .attr.nreturned,
  planSummary: .attr.planSummary
}' /var/log/mongodb/mongod.log
```

This assumes every line is a valid JSON log object. For mixed-format log files, parsers must tolerate invalid lines and preserve raw logs.

### 15.3. Filtering by Threshold

```bash
jq -c 'select(.msg == "Slow query")
  | select((.attr.durationMillis // 0) >= 500)
  | {
      namespace: .attr.ns,
      durationMs: .attr.durationMillis,
      plan: .attr.planSummary
    }' /var/log/mongodb/mongod.log
```

Do not interpret an empty result as "zero slow queries" if:

- Logs are written elsewhere.
- Field names differ in your running version.
- Sampling skipped the events.
- The log file rotated.
- The initial threshold excluded those operations.

### 15.4. `systemd`

On self-managed Linux with `systemd`, depending on configuration:

```bash
journalctl -u mongod --since "2026-11-14 08:00:00"
```

Verify journal/system timezone and permissions. MongoDB may write to a dedicated file rather than the journal, so `journalctl` might not contain slow query entries.

### 15.5. Containers / Kubernetes

When containers log to stdout/stderr:

- Aggregate pod/container logs with cluster and member labels.
- Tag namespace, host, deployment, and replica set.
- Manage runtime/collector log rotation.
- Never log full query documents carrying sensitive data.
- Remember pod restarts wipe local logs unless shipped to a collector.

Common exploratory command:

```bash
kubectl logs <mongodb-pod-name> --since=15m
```

Use only with authorization and the right namespace/context. Do not assume container stdout holds every diagnostic message if the server writes to an internal log file.

### 15.6. Windows PowerShell

If the log file is JSON lines and you need to inspect a small tail in the lab:

```powershell
Get-Content -LiteralPath "C:\MongoDB\logs\mongod.log" -Tail 100 |
  ForEach-Object {
    try { $_ | ConvertFrom-Json } catch { $null }
  } |
  Where-Object { $_ -and $_.msg -eq "Slow query" } |
  Select-Object t, c, ctx, attr
```

Never run `Get-Content` across multi-gigabyte log files during peak hours; use log collectors, streaming, and bounded tails.

---

## 16. Choosing Detail Level: From Verbosity 0 to Per-Component Debug

MongoDB allows configuring log verbosity globally at the server level and per component.

### 16.1. Normal Level

Generally start with:

```yaml
systemLog:
  verbosity: 0
```

Level `0` does not mean "log nothing"; the server still emits essential informational, warning, error, and slow-operation messages.

### 16.2. Debug Verbosity

Higher debug levels (`1` to `5`) emit progressively more messages depending on component and version.

Do not assume `5` is "best." Higher verbosity brings:

- Rapid log volume growth.
- Higher CPU and I/O overhead.
- Exposure of sensitive metadata in logs.
- Steep ingestion costs.
- Signal buried in noise.
- Potential p95/p99 latency degradation from excessive logging.

### 16.3. Component-Specific Verbosity

Self-managed configuration example:

```yaml
systemLog:
  verbosity: 0
  component:
    command:
      verbosity: 0
    query:
      verbosity: 0
    network:
      verbosity: 0
```

During a query planner investigation, temporarily raise only the `query` or `command` component per version guidance instead of raising global verbosity.

### 16.4. Inheritance

Component log levels can **inherit** from the parent/global level per configuration rules. In many interfaces, `-1` means inherit the parent level.

If a component previously inherited global verbosity, setting `0` to "roll back" **is not always equivalent** to restoring inheritance.

Always record **the exact original value**, not just "debug is currently 1."

### 16.5. Runtime Changes via `mongosh`

MongoDB provides helpers:

```javascript
const admin = db.getSiblingDB("admin");

// Read current configuration before changing anything.
printjson(admin.runCommand({
  getParameter: 1,
  logComponentVerbosity: 1
}));
```

In an authorized lab environment:

```javascript
// Test raising verbosity for the query component.
admin.setLogLevel(1, "query");
```

When finished, restore the recorded original level—for example, if it was `0`:

```javascript
admin.setLogLevel(0, "query");
```

**Do not reset to `0` blindly** if it was previously inherited (`-1`) or a custom level. Verify supported helpers, available components, and privileges against your MongoDB version.

### 16.6. Changing Global Verbosity

You can use `setParameter` or log verbosity APIs per version, but server-wide changes have broad blast radius. In production, prefer targeted components and sampling paired with a maintenance/change ticket.

### 16.7. When Is Higher Verbosity Helpful?

Common cases:

- Debugging TLS/network handshakes.
- Investigating authentication failures.
- Tracing election/replication transitions.
- Investigating index builds.
- Analyzing unusual query planner behavior.
- Following MongoDB Support instructions.

In these cases, define **component + duration + observation goal**. Never enable high global debug levels to troubleshoot a slow query when `explain` already suffices.

---

## 17. Recommended Verbosity Table by Scenario

| Scenario | Starting configuration | Additional actions | Safeguards |
|---|---|---|---|
| Normal production | Global verbosity 0; SLO-aligned slow threshold; sensible sampling | Metrics/traces, alerting | Keep log volume within budget |
| API query latency rising | Slow logs + `explain` + selective profiler | Briefly lower `slowms` in a narrow window if approved | Enforce rollback and monitor volume |
| Network/TLS issue | Global 0; targeted `network` component debug | Filter by host/endpoint/context | Avoid leaking connection details |
| Frequent replica set elections | Global 0; targeted replication logging | Compare election metrics/heartbeats | Check multiple members, sync clocks |
| Slow index build | `index`/`storage` components per docs | `serverStatus`/`currentOp`/metrics | Do not log all query commands |
| Small lab | Temporary profiler level 1 or 2 | `explain`, `system.profile` | Revert config after experiments |
| High-load benchmark | Default diagnostic logs; profile only if needed | APM and metric sampling | Level 2 profiling can skew benchmarks |
| Incident with sensitive data | Minimize command detail, enforce redaction and RBAC | Restrict access to incident responders | Never upload raw logs publicly |
| Sharded cluster | Collect `mongos` + shard logs with topology labels | Inspect slow queries on routers and shards | Never merge events into a fake single query |

**There is no single optimal verbosity number for all applications.** Start from the investigation question, collect just enough signal to answer it, and account for observation cost.

---

## 18. Why Logs Must Be Handled as Sensitive Data

Slow-operation logs can contain:

- Query filters with email addresses, phone numbers, and customer IDs.
- Fields used for authorization or tenant isolation.
- Update documents with sensitive payloads.
- Collection and database names revealing internal architecture.
- Financial queries.
- Business workflow identifiers.
- Authentication details or certificate errors.

**A single log line can contain user data**, not merely system telemetry.

### 18.1. Never Paste Raw Slow Queries into Public Tickets

Example query:

```javascript
db.customers.find({
  email: "customer@example.com"
});
```

If logs capture `command.filter.email`, sharing the raw line exposes PII.

Share a sanitized version instead:

```json
{
  "ns": "shop.customers",
  "queryShape": {
    "email": "<redacted>"
  },
  "planSummary": "COLLSCAN",
  "docsExamined": 250000,
  "nreturned": 1,
  "durationMillis": 450
}
```

Apply sanitization consistently, verify its effectiveness, and preserve the structural fields needed for diagnosis.

### 18.2. Server-Side Log Redaction

MongoDB supports **redacting client log data** in supported editions/versions, such as via `security.redactClientLogData` per official documentation.

Never assume redaction is always active in every deployment/tier, nor assume it masks all sensitive metadata or business fields. Verify capabilities, limits, and impact on debuggability.

### 18.3. Access Control Management

- Restrict log file ownership and OS permissions/ACLs.
- Give log collectors dedicated service identities.
- Grant raw log access only to authorized teams.
- Audit log access.
- Encrypt logs at rest and in transit.
- Enforce retention policies rather than keeping logs indefinitely.
- Never log credentials in Java applications.
- Never ship logs containing customer data into unauthorized environments.

### 18.4. Debugging Must Not Break Data Privacy

Raising verbosity can unexpectedly log command arguments. Therefore:

1. Identify what data could be emitted.
2. Verify redaction before enabling.
3. Set an automatic expiration timer.
4. Never commit production logs to repositories.
5. Delete or restrict temporary debug log bundles per retention policy.

---

## 19. Log Volume, Retention, and Rotation

### 19.1. Estimating Volume

Suppose:

```text
Slow operations:   5000 events/minute
Average size:      1.5 KB/event
Over 60 minutes:   5000 × 60 × 1.5 KB
                 = 450000 KB ≈ 439 MiB/hour
```

With full debug enabled, volume can be orders of magnitude higher.

Note that this is an estimate; measure on real logs because JSON event sizes vary widely.

### 19.2. Impact of a Full Disk

If `mongod.log` grows unbounded:

- The filesystem can fill up.
- Database and host services can suffer outages.
- Log collectors can experience backpressure.
- Events can be dropped due to rate/ingest caps.
- Costs rise and troubleshooting slows down.

Logging is therefore part of capacity planning.

### 19.3. Rotation

MongoDB supports server-managed log rotation. With admin privileges on a compatible deployment:

```javascript
db.getSiblingDB("admin").runCommand({
  logRotate: 1
});
```

Depending on configuration, rotation renames or reopens the file. Some systems coordinate with OS `logrotate` or container runtimes.

Never simply delete a log file while `mongod` holds it open and expect the server to immediately create a new one safely.

### 19.4. Choosing Retention

Determine:

- Operational investigation needs: how many days?
- Security/compliance obligations: how long?
- Should aggregated slow-query metrics be kept longer than raw PII logs?
- Online hot storage vs. cold object storage?
- Who has read access?
- Are sensitive-data purge/redaction policies enforced?

Many teams keep raw logs briefly and retain aggregated metrics much longer. Decide based on business needs and compliance rules.

### 19.5. Compression and Export

Compressing log files saves storage, yet:

- Compression is not encryption.
- Logs truncated before compression cannot be recovered.
- Pipelines must preserve accurate timestamps, hosts, and source metadata.
- Never upload raw logs containing PII to public storage.

---

## 20. Correlating Logs Across Multiple Nodes

### 20.1. Replica Set

A replica set has multiple `mongod` processes:

```text
rs0
├── mongo-a (PRIMARY)
├── mongo-b (SECONDARY)
└── mongo-c (SECONDARY)
```

A slow query log is recorded on the node that **executed the operation**. If the application routes reads to secondaries via read preference, do not inspect only primary logs.

### 20.2. Sharded Cluster

A sharded cluster consists of:

- `mongos` routers.
- Config server replica set.
- Shard replica sets.

Logs on `mongos` reflect the router's view; shard `mongod` logs capture shard-level execution. One request can emit events across multiple processes.

```text
App
 │
 ▼
mongos router
 ├── shardA mongod
 ├── shardB mongod
 └── shardC mongod
```

Never naively sum `durationMillis` across shards to estimate application latency; shards can execute in parallel, while the router adds merge and network overhead.

### 20.3. Essential Labels in the Log Collector

- Environment: production/staging/lab.
- Cluster ID.
- Replica set / shard ID.
- Host / pod name.
- Process type: `mongod` or `mongos`.
- Server version.
- Region / zone if applicable.
- Normalized UTC timestamp.
- Event severity, component, and message ID.

Never treat `ctx=conn123` on node A as the same connection as `ctx=conn123` on node B.

### 20.4. Time Synchronization

If node clocks drift, event-sequence reconstruction breaks down.

Ensure:

- NTP / time synchronization.
- Timezone normalization.
- Preservation of original timestamps.
- Clear distinction between log ingestion time and event time.

### 20.5. Slow Queries Due to Shard Targeting

When logs show the same query executing across multiple shards, check:

- Does the query include the shard key predicate?
- Is `mongos` broadcasting via scatter-gather?
- Do all shards have identical indexes?
- Is one shard experiencing skew or a hotspot?
- Is router-level merge sorting or aggregation expensive?

A single slow log entry on one shard is insufficient to conclude a cluster-wide cause.

---

## 21. Correlation from a Java Application Down to MongoDB

In Java applications, the driver exposes **command monitoring** via `CommandListener`.

The safe approach is logging minimal metadata:

- Command name.
- Database name.
- Driver request ID.
- Elapsed time.
- Success/failure status.
- An opaque application trace ID from context, if managed by your tracing system.

**Never log full `event.getCommand()` by default in production**: query filters carry customer data and update payloads can be sensitive.

### 21.1. Java Sync Driver `CommandListener` Example

Example using the modern Java Sync Driver and SLF4J:

```java
import com.mongodb.event.CommandFailedEvent;
import com.mongodb.event.CommandListener;
import com.mongodb.event.CommandStartedEvent;
import com.mongodb.event.CommandSucceededEvent;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.concurrent.TimeUnit;

public final class SafeMongoCommandListener implements CommandListener {
    private static final Logger LOG =
            LoggerFactory.getLogger(SafeMongoCommandListener.class);

    @Override
    public void commandStarted(CommandStartedEvent event) {
        LOG.debug(
                "mongo.command.started command={} database={} requestId={}",
                event.getCommandName(),
                event.getDatabaseName(),
                event.getRequestId()
        );
    }

    @Override
    public void commandSucceeded(CommandSucceededEvent event) {
        LOG.info(
                "mongo.command.succeeded command={} requestId={} elapsedMs={}",
                event.getCommandName(),
                event.getRequestId(),
                event.getElapsedTime(TimeUnit.MILLISECONDS)
        );
    }

    @Override
    public void commandFailed(CommandFailedEvent event) {
        LOG.warn(
                "mongo.command.failed command={} requestId={} elapsedMs={} errorType={}",
                event.getCommandName(),
                event.getRequestId(),
                event.getElapsedTime(TimeUnit.MILLISECONDS),
                event.getThrowable().getClass().getSimpleName()
        );
    }
}
```

Explanation:

- Logs metadata only—no command document or passwords.
- `requestId` is scoped to the driver/connection, not a cluster-wide trace ID.
- `elapsedMs` is client-side timing, not identical to server `durationMillis`.
- High-volume `INFO` events can be massive. In production, prefer sampling/metrics over unbounded `INFO` logging per command.
- Do not log full exception stack traces for every failed command if exceptions might embed sensitive data; apply structured error sanitization.

### 21.2. Registering the Listener

```java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

public final class MongoClientFactory {
    public static MongoClient create() {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException(
                    "MONGODB_URI is missing");
        }

        MongoClientSettings settings = MongoClientSettings.builder()
                .applyConnectionString(new ConnectionString(uri))
                .addCommandListener(new SafeMongoCommandListener())
                .build();

        return MongoClients.create(settings);
    }
}
```

Never hardcode passwords in source code. `MONGODB_URI` from environment variables must still be protected from logging and unauthorized access.

### 21.3. Limitations of Command Monitoring

A single command event might:

- Be a retry attempt.
- Correspond to a single `getMore` batch.
- Have a duration differing from total HTTP request wait time.
- Return success while the subsequent business operation fails.
- Succeed at the protocol level yet violate the API SLO.

Pair command monitoring with distributed tracing and metrics to understand the whole request.

### 21.4. Adding Controlled Comments

MongoDB supports `comment` on many query commands. A short, non-sensitive comment helps identify the calling operation in profiler and diagnostic logs when recorded.

Example in `mongosh`:

```javascript
const lab = db.getSiblingDB("observability_lab");

lab.orders.find({
  status: "PENDING"
}).comment("service=checkout;operation=listPending").toArray();
```

In the Java Driver, supported iterables provide `comment(...)` per API version:

```java
import static com.mongodb.client.model.Filters.eq;

orders.find(eq("status", "PENDING"))
      .comment("service=checkout;operation=listPending")
      .limit(20)
      .into(new java.util.ArrayList<>());
```

Guidelines:

- Keep comments short and safe—never include emails, tokens, or passwords.
- Avoid extreme cardinality unless strictly necessary.
- Do not assume comments appear in **every** log event.
- Comment support and logging behavior depend on command, driver, and server version.
- Comments do not replace distributed tracing.

### 21.5. Controlling Java Log Volume

Logging `INFO` on every command can turn the application into a massive log generator. Better practices include:

- Aggregated application metrics by command, namespace, and latency.
- Sampling successful commands.
- Throttling/aggregating failure logs.
- Enabling temporary detailed logging only on a canary instance.
- Using server slow logs for operations exceeding thresholds.
- Alerting on p95/p99 rather than raw log line counts.

---

## 22. Why Do Server-Side Logs and Driver Logs Not Match Exactly?

Suppose:

```text
Driver event:
  command=find
  elapsedMs=900

Server slow log:
  command=find
  durationMillis=380
```

Possible reasons:

- Network latency.
- TLS overhead.
- Driver scheduling or runtime GC pauses.
- Server selection and connection pool timing measured differently by listeners.
- Retries.
- Batches/`getMore`.
- Differences in timer start/stop points.
- Events not actually belonging to the same command.

Verify first that both events belong to the exact same operation. Never subtract `900 - 380 = 520 ms` and declare "network latency is exactly 520 ms" without end-to-end trace correlation.

### 22.1. Using OpenTelemetry / APM

When the application uses distributed tracing:

```text
HTTP GET /orders
  ├── validate tenant
  ├── MongoDB find orders
  │   ├── server selection
  │   ├── connection checkout
  │   ├── command
  │   └── cursor batches
  ├── call payment API
  └── serialize JSON
```

Inspecting spans pinpoints where time goes, while MongoDB logs reveal query plans and server internals.

### 22.2. Never Copy Raw Query Documents into Traces

Telemetry backends can leak PII. Attach safe attributes instead:

- Sanitized namespace.
- Operation type.
- Query shape identifier when available.
- Document counts.
- Latency.
- Error category.

Never attach raw customer `filter` values to span attributes.

---

## 23. Choosing Alerting Signals Instead of Counting Every Log Line

A helpful dashboard displays:

- Slow operations count per minute.
- Slow log rate per namespace.
- p50/p95/p99 command duration.
- Query shapes with high `docsExamined / nReturned`.
- Error/warning rates by component.
- Connection counts and pool wait times.
- Replication lag and elections.
- Cache and disk utilization.
- Log ingest bytes/sec per node.
- Dropped/truncated log rate.
- Percentage of critical queries using `COLLSCAN`.

### 23.1. Counting Log Lines Can Mislead

For instance, slow event count drops from 1,000 to 100 after changing `sampleRate` from `1.0` to `0.1`. That is not proof the database got 10x faster.

Dashboards must account for sampling policy or rely on independent metrics for trend analysis.

### 23.2. When Thresholds Change, Alert Counts Shift

Lowering `slowOpThresholdMs` from 100 to 20 naturally increases slow log counts. Annotate configuration changes on dashboards to prevent false alarms.

### 23.3. High Cardinality Is Risky

Never attach raw per-request `userId`, `email`, or `traceId` values as time-series metric labels. That triggers cardinality explosion, driving up memory usage and costs.

Opaque trace IDs belong in trace/log events under privacy policy; reserve metric labels/tags for bounded-cardinality dimensions.

### 23.4. `docsExamined / nReturned` Ratio

A useful heuristic:

```text
scan_ratio = docsExamined / max(nReturned, 1)
```

A large ratio can indicate inefficient filtering.

However, a high ratio is not always an index bug:

- Aggregations computing summaries may return 1 row from thousands of docs.
- Analytics intentionally scan large datasets.
- TTL/maintenance and read workloads behave differently.
- Queries counting full collections scan broadly.

Evaluate ratios by **query shape and business intent** rather than ranking all queries by one naive ratio.

---

## 24. Analyzing Each Slow Operation Category

### 24.1. Slow Read Due to Collection Scan

Illustrative log:

```json
{
  "msg": "Slow query",
  "attr": {
    "ns": "shop.orders",
    "planSummary": "COLLSCAN",
    "keysExamined": 0,
    "docsExamined": 450000,
    "nreturned": 10,
    "durationMillis": 820
  }
}
```

Investigation steps:

1. Identify filter, sort, and projection.
2. Run `explain` in a safe environment.
3. Check for missing indexes and selectivity.
4. Check if the application dropped a `tenantId` predicate.
5. Weigh index read benefits against write/storage costs.
6. Monitor metrics after deploying the index.

### 24.2. Slow Read Despite `IXSCAN`

```json
{
  "msg": "Slow query",
  "attr": {
    "ns": "shop.orders",
    "planSummary": "IXSCAN { status: 1 }",
    "keysExamined": 180000,
    "docsExamined": 170000,
    "nreturned": 90000,
    "durationMillis": 1300
  }
}
```

An index is used, yet huge result volume is returned. Consider pagination, projection, compound indexes covering filter/sort, and business contracts.

### 24.3. Slow Writes

Slow `update` or `insert` operations can be slowed by:

- Excessive indexes.
- Write concern waits.
- Replication lag.
- Lock contention.
- Oversized documents.
- Storage I/O saturation.
- Large batches.

Never blindly add more indexes to fix slow writes; extra indexes make writes heavier.

### 24.4. Slow Aggregations

Aggregations can slow down due to:

- `$lookup` fan-out.
- High-cardinality `$group`.
- `$sort` on large datasets.
- `$unwind` expanding row counts.
- Inability to leverage an index early in the pipeline.
- Disk spills when allowed.
- Cross-shard merges.

Use aggregation `explain`, pipeline optimization, and matching metrics.

### 24.5. Locks / Yields / Storage

Some slow log entries report locks, yields, storage stats, and flow control.

Interpret counters in the context of the operation and server version. For example, high `numYields` alone does not prove a lock bottleneck; MongoDB yields normally as part of concurrency scheduling.

### 24.6. Slow `getMore`

A `find` may return its first batch quickly while a subsequent `getMore` takes 2 seconds. Watching only `find` slow logs misses the slowest step.

Group logs by cursor/connection context where feasible and cross-reference driver spans.

---

## 25. Investigation Workflow: From Symptom to Verified Conclusion

Suppose an incident occurs: `GET /orders?status=PENDING` p95 jumps from 60 ms to 900 ms after a deployment.

### Step 1 — Define Window and Scope

- Exact start and end time?
- Which service/API?
- Which cluster, region, and tenant?
- Any recent deployments or index migrations?
- Which node does read preference target?
- Did data or traffic volume spike suddenly?

### Step 2 — Compare Application Metrics with Server Metrics

Check:

- HTTP p95/p99.
- MongoDB command durations.
- Connection pool waits.
- CPU/IO/cache.
- Replication lag.
- Network errors.
- MongoDB error rates.

### Step 3 — Filter Slow-Operation Logs

Filter by:

```text
Time window
Cluster / process
msg = Slow query (or equivalent type)
ns = shop.orders
command = find / aggregate / getMore
durationMillis >= investigation threshold
```

Do not ignore entries from other components tied to storage or replication.

### Step 4 — Inspect Query Shape and Plan

Compare:

- `planSummary`.
- `keysExamined`.
- `docsExamined`.
- `nreturned`.
- Sort behavior.
- Plan/cache shifts.
- Query parameters and selectivity.

### Step 5 — Run `explain` Safely

Take the query shape and test on appropriate data:

```javascript
db.getSiblingDB("observability_lab")
  .orders.find({
    tenantId: "t1",
    status: "PENDING"
  })
  .sort({ createdAt: -1 })
  .explain("executionStats");
```

Never replay write commands directly from raw logs on production.

### Step 6 — Choose Mitigation

Options include:

- Creating or tuning a compound index after evaluation.
- Restoring a missing tenant predicate.
- Refining the query or projection.
- Adding pagination or bounding batch sizes.
- Separating analytical queries from operational workloads.
- Adjusting the data model.
- Fixing shard hotspots or targeting.
- Tuning query timeouts.

### Step 7 — Verify

Compare before/after:

- API p95/p99.
- Server command durations.
- Query plans and scan counts.
- Disk/CPU/cache.
- Write overhead from any new index.
- Error rates.

### Step 8 — Restore Log Configuration

If verbosity was raised or `slowms` was lowered:

- Revert to original settings.
- Close temporary debug sinks.
- Archive sanitized evidence.
- Document the incident timeline.
- Update runbooks with lessons learned.
- Never leave elevated debug settings running indefinitely.

---

## 26. A Safe Runbook When Log Verbosity Must Be Increased

### 26.1. Before Enabling

Record:

```text
Incident ID:
Owner:
Environment/cluster:
Target process:
Component:
Current verbosity:
Proposed verbosity:
Current slowOpThresholdMs:
Proposed threshold:
Current sampleRate:
Proposed sampleRate:
Duration of diagnostic window:
Estimated log rate:
Storage/collector headroom:
Rollback owner:
Approval:
```

### 26.2. During the Collection Window

- Keep global verbosity at its normal baseline if possible.
- Raise only the required component.
- Pick reasonable `slowms` and sample rates.
- Limit target nodes/replica members where policy permits.
- Monitor log bytes/s and dropped events.
- Keep raw sensitive logs strictly within authorized storage.
- Never paste query values into public channels.

### 26.3. Upon Completion

- Restore verbosity to **its exact original values**, including inherited settings.
- Restore `slowms`, `sampleRate`, and `filter`.
- Disable the profiler if enabled solely for troubleshooting.
- Confirm log volume returns to baseline.
- Check storage/disk headroom and rotation.
- Save post-incident lessons with sanitized evidence.

### 26.4. Never Use Debug Logging to Mask Lack of Root Cause

A common mistake is raising verbosity to 5 and forgetting it. Hours later, the log disk fills up and takes down the database.

Set an explicit expiration time when opening a debug window. If logs still lack enough clues to pinpoint a slow query, gather metrics/tracing instead of endlessly cranking up logging.

---

## 27. Distinguishing Normal Query Activity from the Profiler

Suppose:

```javascript
const lab = db.getSiblingDB("observability_lab");
lab.setProfilingLevel(0, { slowms: 100, sampleRate: 1.0 });
```

Meaning:

- Level 0: do not save operation profiles into `system.profile`.
- Slow operation threshold: 100 ms under active configuration.
- Sample rate: 1.0 for qualifying operations per version.
- Diagnostic logs can still emit slow-operation events.

If changed to:

```javascript
lab.setProfilingLevel(1, { slowms: 100, sampleRate: 1.0 });
```

the profiler starts storing qualifying slow operations in `system.profile` on the target node/database.

If changed to:

```javascript
lab.setProfilingLevel(2);
```

the profiler records broadly; avoid running this in production without strong justification and strict controls.

### 27.1. What Indexing and Retention Does `system.profile` Have?

Profiler data lives in a **capped collection** with bounded size that overwrites older records.

Do not treat `system.profile` as an infinite historical query archive. For long-term retention, build an export pipeline with proper RBAC, redaction, and cost controls.

### 27.2. The Profiler Does Not Replace Audit Logs

The database profiler captures performance diagnostics, not compliance-grade security/audit trails.

When auditing is required:

- Use the database auditing feature supported by your edition/deployment.
- Configure appropriate audit events and policies.
- Protect audit logs and enforce retention.
- Never use slow logs as compliance audit evidence.

---

## 28. Structured Log Schemas and Robust Parsing

A well-engineered log pipeline should:

1. Parse JSON per event.
2. Attach source metadata.
3. Preserve original timestamps.
4. Handle optional fields gracefully.
5. Avoid storing full command payloads unless needed.
6. Tolerate log schema changes across versions.
7. Classify both warnings/errors and slow operations.
8. Enforce ingestion rate limits.
9. Provide dead-letter handling for malformed/truncated messages.
10. Re-test the pipeline after MongoDB version upgrades.

### 28.1. Suggested Normalized Schema

```json
{
  "eventTime": "2026-11-14T08:20:12.483Z",
  "environment": "production",
  "cluster": "orders-rs",
  "process": "mongo-a",
  "severity": "I",
  "component": "COMMAND",
  "messageId": 51803,
  "messageType": "slow_operation",
  "namespace": "shop.orders",
  "commandType": "find",
  "planSummary": "COLLSCAN",
  "durationMs": 863,
  "keysExamined": 0,
  "docsExamined": 250000,
  "nReturned": 20
}
```

This is a **pipeline-designed schema**, not a guaranteed raw MongoDB log schema.

### 28.2. Never Require Every Field on Every Event

A slow `getMore` or failed command may omit `nreturned` or use different attributes. Log parsers must allow `null` or missing values.

### 28.3. Never Store Sensitive Filters as Labels

A filter containing `customerEmail` is PII. To group by shape, normalize field/operator structure and redact literal values.

### 28.4. Version Differences in Query Identifiers

Fields for query hashes, query shapes, and plan caches can change between MongoDB releases. Check version docs and never build dashboards depending exclusively on one legacy field name.

---

## 29. Hands-On Exercises

### Exercise A — Reading a Structured JSON Log

Given:

```json
{
  "t": {
    "$date": "2026-11-14T08:20:12.483Z"
  },
  "s": "I",
  "c": "COMMAND",
  "id": 51803,
  "ctx": "conn42",
  "msg": "Slow query",
  "attr": {
    "ns": "shop.orders",
    "planSummary": "COLLSCAN",
    "keysExamined": 0,
    "docsExamined": 100000,
    "nreturned": 5,
    "durationMillis": 420
  }
}
```

Answer:

1. What is the severity?
2. What is the component?
3. Is `id` a request ID?
4. Which namespace is involved?
5. Why is high `docsExamined` relative to `nreturned` worth investigating?
6. Can you definitively conclude a missing index is the sole cause yet? Why or why not?

### Exercise B — Slow Logging vs. Profiler

Explain the differences between:

- Profiler level 0 with `slowms` 100.
- Profiler level 1 with `slowms` 100.
- Profiler level 2.
- Diagnostic log verbosity 0.
- Component `query` verbosity 1.

At level 0, where can MongoDB still record slow operations?

### Exercise C — Building the Lab

1. Create `observability_lab.orders`.
2. Run a query filtering by `status`.
3. Inspect `explain`.
4. Create a compound index.
5. Re-run `explain`.
6. Compare `docsExamined`/`keysExamined`.
7. Explain why 10 documents are too few to benchmark latency.

### Exercise D — Slow Queries Missing from Slow Logs

An API has a p95 of 500 ms, yet no slow messages appear.

List at least six hypotheses covering thresholds, sampling, wrong process, network/client delays, connection pools, `getMore`, and server vs. application timing.

### Exercise E — Log Sampling

Suppose 10,000 slow operations/hour occur at sample rate 1.0. After lowering sample rate to 0.1, the log dashboard shows roughly 1,000 events.

Can you conclude MongoDB became 10x faster? How must trends be normalized?

### Exercise F — Choosing Verbosity

A production cluster experiences intermittent authentication failures. You are considering setting global verbosity to 5.

Propose how to:

1. Pick the exact component.
2. Pick the lowest verbosity sufficient for diagnosis.
3. Bound the time window.
4. Protect secrets.
5. Monitor log volume.
6. Roll back to the exact initial level.

### Exercise G — Parsing with `jq`

Given a JSON-lines log file:

- Filter for `msg="Slow query"`.
- Extract `attr.ns`, `durationMillis`, and `planSummary`.
- Keep durations >= 500 ms.
- Tolerate missing fields.
- Avoid outputting raw sensitive command bodies.

### Exercise H — Java/MongoDB Correlation

A Java Driver `commandSucceeded` event reports 800 ms while the MongoDB slow log reports 300 ms.

Explain possible reasons for the difference, and propose how to use tracing without logging `getCommand()`.

### Exercise I — Sharded Cluster

A scatter-gather query runs across three shards. The router logs 900 ms total, while individual shards log 300/400/600 ms.

Can you add `300 + 400 + 600 = 1300 ms` and call it request latency? Why or why not? What else do you need to know about merging and shard targeting?

### Exercise J — Redaction and Privacy

Logs contain the query:

```javascript
db.customers.find({
  email: "alice@example.com",
  phone: "0900000000"
});
```

Design a normalized log schema so dashboards still see namespace, query shape, scan counts, and duration without exposing email or phone numbers.

### Exercise K — Alerting

A dashboard alerts when `Slow query` messages exceed 100/minute.

After a deployment, `slowOpThresholdMs` drops from 100 to 20 and `sampleRate` changes from 1.0 to 0.5.

How do you distinguish log volume shifts caused by config changes from genuine query latency regressions? Which config annotations and companion metrics should you track?

### Exercise L — Incident Runbook

Write a response procedure for rising API latency covering:

- Scope and time window.
- Application metrics.
- Server logs.
- Controlled profiler usage.
- `explain`.
- Index, plan, locking, and sharding checks.
- Mitigation.
- Verification.
- Config rollback.
- Sanitized incident report.

---

## 30. Production Logging Checklist

### 30.1. Baseline Configuration

- [ ] Know exactly where `mongod`/`mongos` logs are written.
- [ ] Use structured JSON parsing on supported versions.
- [ ] Attach accurate host, process, and cluster labels.
- [ ] Standardize timestamps and timezones.
- [ ] Keep global verbosity at an appropriate baseline (typically 0).
- [ ] Align slow thresholds with performance SLOs.
- [ ] Track sampling rates and reflect them in metrics.

### 30.2. Investigating Slowness

- [ ] Do not confuse server slow logs with the profiler.
- [ ] Check the current profiler level.
- [ ] Confirm `system.profile` presence and read privileges on target databases.
- [ ] Inspect `ns`, `command`, `durationMillis`, and `planSummary`.
- [ ] Compare `keysExamined`/`docsExamined`/`nreturned`.
- [ ] Never assume `IXSCAN` is automatically optimal.
- [ ] Do not overlook `aggregate`, `getMore`, or write operations.
- [ ] Run `explain` with a matching query shape.
- [ ] Separate client, network, driver, and server latency.
- [ ] Check workload, tenant, and shard distributions.

### 30.3. Verbosity Control

- [ ] Raise verbosity per component when needed.
- [ ] Never leave high global debug enabled by default.
- [ ] Assign a change owner and expiration time.
- [ ] Record original settings for exact rollback.
- [ ] Monitor bytes/sec, disk space, and collector queues.
- [ ] Turn off profiling level 2 once investigation ends.
- [ ] Never leave `slowms: 0` / `sampleRate: 1.0` in production long-term.
- [ ] Check version-specific log component options.

### 30.4. Security and Retention

- [ ] Never log passwords, tokens, or raw PII.
- [ ] Redact/sanitize raw command payloads where needed.
- [ ] Enforce RBAC on log collectors.
- [ ] Encrypt logs in transit and at rest.
- [ ] Enforce rotation and retention policies.
- [ ] Prevent high-cardinality metric labels.
- [ ] Handle parser errors and truncation gracefully.
- [ ] Audit log access.
- [ ] Never treat the profiler as a security audit log.

### 30.5. Post-Incident

- [ ] Verify mitigation using performance metrics.
- [ ] Restore verbosity, thresholds, sampling, and filters.
- [ ] Confirm log volume returns to baseline.
- [ ] Produce an incident report stripped of sensitive details.
- [ ] Update runbooks and alerts.

---

## 31. Common Pitfalls to Avoid

| Misconception | Reality |
|---|---|
| Slow query log is always a separate file | Usually emitted inside the diagnostic log |
| Profiler level 0 means no slow logs | Server diagnostic log can still emit slow operations |
| Profiler level 2 is free | Carries heavy CPU, write, and storage overhead |
| Verbosity 5 is "production standard" | High debug levels generate massive log volume |
| Setting `slowms` to 0 is always better | Can trigger a log storm |
| Sampling 0.1 makes the database 10x faster | It only reduces collected events via sampling |
| Severity `I` means unimportant | Slow queries are commonly logged at informational severity |
| `id` is a unique query ID | Numeric message ID identifies the event type |
| `ctx` is an end-to-end trace ID | Context is usually a reusable connection/thread ID |
| Logged commands are always complete | They can be truncated, redacted, or omit fields |
| `COLLSCAN` is always a bug | On tiny collections or broad scans, it can be optimal |
| `IXSCAN` is always fast | Can still scan millions of index keys |
| High `docsExamined`/`nreturned` is always wrong | Analytics/aggregations intentionally scan broadly |
| `durationMillis` equals HTTP latency | Client, network, and business logic add time |
| No slow logs means no slow queries | Thresholds, sampling, tiers, processes, or timezones may hide them |
| Fast `find` means fast API reads | `getMore` / cursor batches can still be slow |
| Raising global debug fixes root causes | Logs only supply evidence |
| Logging full query documents makes debugging easy | Exposes PII and secrets |
| Using `system.profile` as an audit log | Completely different purpose |
| `mongos` logs include all shard details | Must combine router and shard logs |
| Inspecting primary logs is enough | Read preference may hit secondaries |
| Deleting an open log file rotates safely | Must use supported log rotation |
| Resetting verbosity to 0 always restores initial state | Component may have inherited another level |
| Turning on debug and leaving it is harmless | Requires an expiration window and rollback |

---

## 32. Official MongoDB Documentation

- [MongoDB Manual – Log Messages](https://www.mongodb.com/docs/manual/reference/log-messages/)
- [MongoDB Manual – Log Message Verbosity Levels](https://www.mongodb.com/docs/manual/reference/log-messages/#verbosity-levels)
- [MongoDB Manual – Log Components](https://www.mongodb.com/docs/manual/reference/log-messages/#log-components)
- [MongoDB Manual – Database Profiler](https://www.mongodb.com/docs/manual/tutorial/manage-the-database-profiler/)
- [MongoDB Manual – db.setProfilingLevel()](https://www.mongodb.com/docs/manual/reference/method/db.setProfilingLevel/)
- [MongoDB Manual – db.getProfilingStatus()](https://www.mongodb.com/docs/manual/reference/method/db.getProfilingStatus/)
- [MongoDB Manual – db.setLogLevel()](https://www.mongodb.com/docs/manual/reference/method/db.setLogLevel/)
- [MongoDB Manual – systemLog Configuration](https://www.mongodb.com/docs/manual/reference/configuration-options/#systemlog-options)
- [MongoDB Manual – operationProfiling Configuration](https://www.mongodb.com/docs/manual/reference/configuration-options/#operationprofiling-options)
- [MongoDB Manual – Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Manual – Database Commands / getLog](https://www.mongodb.com/docs/manual/reference/command/getLog/)
- [MongoDB Manual – logRotate Command](https://www.mongodb.com/docs/manual/reference/command/logRotate/)
- [MongoDB Java Sync Driver – Monitoring](https://www.mongodb.com/docs/drivers/java/sync/current/monitoring-and-logging/monitoring/)
- [MongoDB Java Sync Driver – Logging](https://www.mongodb.com/docs/drivers/java/sync/current/monitoring-and-logging/logging/)
- [MongoDB Atlas – Query Profiler](https://www.mongodb.com/docs/atlas/tutorial/profile-database/)
- [MongoDB Atlas – Monitoring](https://www.mongodb.com/docs/atlas/monitoring-alerts/)

> **Version note:** JSON log fields, component names, profiler filtering capabilities, runtime parameters, and managed deployment features evolve across releases. Before running configuration changes, verify against documentation for **your exact MongoDB Server version, MongoDB Atlas tier (if applicable), and MongoDB Java Driver version**.

## 33. Conclusion

MongoDB provides multiple observability sources, each answering a different question:

1. **Structured diagnostic logs** track system health through events carrying timestamps, severity, component, message IDs, execution context, and structured attributes.
2. **Slow-operation logs** surface `find`, `aggregate`, `getMore`, or write commands exceeding configured thresholds, sampling, or filters.
3. **Database profiler** stores profile records in `system.profile` on `mongod` when enabled; **level 0 does not stop diagnostic slow logging**.
4. **`explain` and metrics/tracing** verify root causes: `COLLSCAN`, `IXSCAN`, scan ratios, sorts, locking, sharding, network, and application overhead.
5. **Appropriate verbosity** is the lowest level capable of answering your investigation question. Favor component-scoped debugging within bounded time windows.
6. **Logs can contain sensitive data**: enforce redaction, RBAC, encryption, retention, and rotation, and avoid logging raw queries or passwords.
7. **Incident closure must include rolling back logging changes**. Never leave ultra-low `slowms`, profiler level 2, or high verbosity running in production simply because nobody remembered to revert it.

A strong observability system does not try to record **every single operation**—it captures **the right signals**, with enough detail to investigate, enough security to run sustainably, and low enough overhead that measurement itself never becomes the reason MongoDB slows down.
