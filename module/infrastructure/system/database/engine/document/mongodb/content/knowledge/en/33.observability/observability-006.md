# Database Profiler and Query Collection Overhead in MongoDB

> **Module:** MongoDB Document Database Engine  
> **Chapter:** Observability  
> **Lesson:** Database Profiler and Query Collection Overhead

## 1. Problem: Does Collecting More Data Always Mean Better Observability?

An e-commerce API backed by MongoDB sees a sharp spike in p95 latency. The operations team wants to determine:

- Which queries are slow, and in which database and collection?
- How many documents and index keys did the query scan?
- Did it use `COLLSCAN` or `IXSCAN`?
- Which queries share the same shape and repeat frequently?
- When the application calls `find()` and `getMore`, where is execution time spent?
- How can we capture timely evidence without making MongoDB even slower?
- Should we enable profiler level 2 to record all operations?
- Why is `system.profile` sometimes empty even when the server log contains `Slow query`?
- Can filter or update data show up inside the profiler?
- After the investigation, which settings must be reverted to their original state?

The MongoDB **database profiler** is a valuable tool for analyzing query workloads. However, the profiler is not free: generating and storing operation profiles consumes CPU, memory, I/O, and storage capacity.

An uncontrolled investigation can create a vicious feedback loop:

```text
Application slows down
     │
     ▼
Enable profiling for all operations (level 2)
     │
     ▼
system.profile record rate surges
     │
     ▼
CPU + writes + storage pressure increase
     │
     ▼
Application slows down further
     │
     ▼
Measurements no longer reflect the original workload
```

**Core message:** The database profiler is an **observation tool with a cost**, not a debug switch to crank to maximum. Choose the right level, threshold, filter, duration, and scope; combine it with diagnostic logs, metrics, Java Driver tracing, and `explain()`.

### 1.1. Learning Objectives

After this lesson, you will be able to:

1. Explain what the database profiler is and where its data is stored.
2. Distinguish profiling levels `0`, `1`, and `2`.
3. Understand `slowms`, `sampleRate`, and `filter`, including effects that extend beyond the configured database.
4. Read key fields in `system.profile`.
5. Estimate write, storage, CPU, and privacy costs when increasing profiling levels.
6. Practice `db.getProfilingStatus()` and `db.setProfilingLevel()`.
7. Use targeted filters/profilers at the right moment instead of capturing all queries.
8. Use `explain("executionStats")` to pinpoint performance causes.
9. Distinguish profiler records from diagnostic slow-operation logs.
10. Design a runbook to enable, monitor, disable, and revert the profiler in authorized environments.

---

## 2. What Is the Database Profiler?

The **database profiler** is a MongoDB Server mechanism that collects detailed information about database operations matching profiling criteria.

On `mongod`, profile records are stored in a special collection:

```text
<database>.system.profile
```

For example:

```text
commerce.system.profile
analytics.system.profile
profile_lab.system.profile
```

A record can contain:

- Timestamp of the operation.
- Operation type: `query`, `command`, `getmore`, `update`, etc.
- Namespace.
- Part or all of the command document depending on capture rules and size limits.
- Total operation time in milliseconds.
- Query plan summary.
- Index keys and documents examined.
- Number of documents returned.
- Lock, yield, storage, or execution details when supported.
- Cursor and query shape/plan identifiers depending on server version.

### 2.1. The Profiler Is Not a Database Log File

Comparison:

```text
MongoDB server process
     │
     ├── Diagnostic log
     │     stdout / mongod.log / container collector
     │     INFO, WARNING, ERROR, DEBUG, Slow query
     │
     └── Database profiler
           <database>.system.profile
           selected operation records
```

The diagnostic log records broad server state. The profiler focuses on per-database operation profiling, storing records as documents inside MongoDB.

### 2.2. The Profiler Is Not Full-Application APM

The profiler sees operations **that reached the MongoDB server**. It does not capture all of:

- HTTP request time.
- Business logic in Java.
- Connection pool wait time.
- Network transit between application and MongoDB.
- Driver-side retries.
- Calls to external APIs.
- Response rendering/serialization.
- Frontend UI latency.

An API with a 1,000 ms p95 and a profile record showing `millis: 80` does not mean MongoDB caused all 1,000 ms.

### 2.3. The Profiler Does Not Replace Backups or Auditing

The `system.profile` collection holds bounded observational data; it is not:

- A database backup.
- A complete security/compliance audit trail.
- A list of every query ever executed.
- A replayable transaction log.
- A guarantee that every request was captured.

If you need access auditing, use database auditing features properly deployed per your edition/plan and security policy.

---

## 3. Situating the Profiler in an Observability Stack

A production system typically needs multiple signal sources:

| Source | Provides | Best suited for |
|---|---|---|
| Database profiler | Details on selected operations on `mongod` | Investigating query shapes, plans, scan counts |
| Diagnostic slow-operation log | Slow operation entries in server logs | Broad monitoring, centralized log aggregation |
| `explain("executionStats")` | Plan and counters from an analyzed query | Verifying scans, indexes, and sorts |
| `serverStatus` / metrics | Connection, cache, operation, and lock stats | Trend and load monitoring |
| `currentOp` | Operations running at call time | Investigating currently active work |
| Java Driver command monitoring | Client-side command latency and success/failure | Isolating server, network, and driver time |
| Distributed tracing | Request spans across services | End-to-end correlation |
| Atlas / managed monitoring | Tier-based metrics, profiler, and logs | Managed cluster observability |

No single source replaces all the others.

### 3.1. Example of Correlating Data

Suppose:

```text
HTTP p95 rises from 100 ms to 900 ms
Driver command duration p95 ~700 ms
system.profile shows:
  ns: shop.orders
  planSummary: COLLSCAN
  docsExamined: 450000
  nreturned: 10
  millis: 650
explain shows the tenantId/status index is missing or unsuitable
```

A solid hypothesis is that MongoDB is scanning too many documents for this query. Still, verify actual workload, index changes, resource contention, and post-fix impact.

### 3.2. You Do Not Always Need the Profiler

If the database is slow because disk is full, the replica set lost its primary, or the network is down, enabling profiling level 2 will not help and adds extra load.

Start from the investigation question and choose the lowest-cost source able to answer it.

---

## 4. Three Profiling Levels: 0, 1, and 2

MongoDB provides three classic profiling levels:

| Level | Behavior | When appropriate |
|---|---|---|
| `0` | Disables writing profiler records to `system.profile` | Normal baseline operation when profiling is not needed |
| `1` | Records operations matching slow-operation criteria or filter | Selective investigation |
| `2` | Records all profiler-supported operations per active config | Labs or brief targeted investigations |

### 4.1. Level 0 — Profiler Disabled

```javascript
db.setProfilingLevel(0);
```

Stops writing new operation profiles into `system.profile` under normal profiler rules.

**However, MongoDB's diagnostic log can still record slow operations.** Disabling the profiler does not turn off slow query logging.

### 4.2. Level 1 — Collecting Qualifying Operations

```javascript
db.setProfilingLevel(1, {
  slowms: 100,
  sampleRate: 1.0
});
```

Illustration:

- Profiling level 1.
- Slow threshold 100 ms.
- Sampling rate 1.0 (all qualifying operations per threshold/sampling logic—not every database operation).

On an appropriate deployment, this is usually the right place to begin investigating.

### 4.3. Level 2 — Broad Collection

```javascript
db.setProfilingLevel(2);
```

At level 2, the profiler captures nearly all profilable operations rather than only those exceeding the slow threshold.

Risks:

- Generates massive numbers of profile documents.
- Adds extra write load.
- Increases CPU and I/O.
- Triggers additional resource contention.
- Wraps the capped collection buffer rapidly.
- Increases exposure of sensitive values.
- Skews benchmarks and p99 latency.

**Never leave level 2 enabled long-term in production.** If you need full capture in an isolated lab, keep the window short and watch overhead.

### 4.4. Workload Comparison

Suppose a workload runs 10,000 operations/sec and 5% exceed 100 ms:

- Level 0: writes no profiles to `system.profile`, though slow-operation diagnostic logs may still be emitted.
- Level 1, `slowms` 100 ms, `sampleRate` 1: roughly 500 candidate operations/sec under a simple distribution model.
- Level 1, `sampleRate` 0.1: roughly 50 records/sec in an idealized example.
- Level 2: can approach 10,000 profile records/sec if all operations are profilable—orders of magnitude higher.

These numbers are illustrative, **not exact record guarantees**; operation types, filters, and internal exclusions affect real counts.

---

## 5. How Does the `system.profile` Collection Work?

MongoDB stores profiler records in:

```javascript
db.getSiblingDB("profile_lab").system.profile
```

This is a **capped collection** managed by MongoDB for profiling.

### 5.1. What Does Capped Collection Mean?

A capped collection has a fixed maximum size; once full, older documents are overwritten by new records under capped storage semantics.

Implications:

- `system.profile` is not an infinite historical archive.
- Level 2 or high-throughput level 1 can overwrite old data very quickly.
- Rare events may roll off before operators inspect them.
- Export or summarize into a proper observability backend if long-term retention is needed.
- Do not enlarge the profiler cap recklessly just to retain records longer; doing so raises disk and operational overhead.

### 5.2. Which Database Owns `system.profile`?

If profiling is enabled on `profile_lab`, its records live in:

```text
profile_lab.system.profile
```

Do not expect profile records for `commerce` to appear inside `admin.system.profile`.

### 5.3. Are Literally All Operations Recorded?

Never claim "every command" is recorded unconditionally. The profiler has supported scopes, level/filter rules, permissions, server-version behaviors, and internal operations that are not profiled like ordinary client queries.

In particular, reading `system.profile` itself should not create an endless self-profiling loop.

### 5.4. Access Privileges

Reading the profiler requires appropriate privileges on `system.profile`. A user who can merely connect to a database cannot automatically administer profiling.

Enabling/disabling the profiler or changing global slow thresholds or log settings requires elevated administrative privileges.

In production:

- Separate the principal reading telemetry from the principal modifying profiling.
- Never grant `root` to an application just to read the profiler.
- Restrict access to records that may contain query values or PII.

### 5.5. Collection Size and Retention Window

You cannot calculate retention time from the size limit alone, because record size and arrival rate vary with workload.

Example:

```text
system.profile capped capacity: 100 MiB (example)
Average record:                 2 KiB
Theoretical capacity:           ~51,200 records
Profile rate:                   500 records/sec
Theoretical retention:          ~102 seconds
```

This is a model calculation. Reality depends on storage overhead, uneven document sizes, and capped collection mechanics.

**Lesson:** A 100 MiB profiler buffer may hold only a couple of minutes under high write rates.

---

## 6. Configuring the Profiler with `mongosh`

### 6.1. Inspecting Current Configuration

Before changing any setting:

```javascript
const lab = db.getSiblingDB("profile_lab");

printjson(lab.getProfilingStatus());
print("Current level:", lab.getProfilingLevel());
```

Example result:

```json
{
  "was": 0,
  "slowms": 100,
  "sampleRate": 1,
  "ok": 1
}
```

Meaning:

- `was`: profiling level at query time.
- `slowms`: active slow threshold.
- `sampleRate`: sampling rate.
- Additional fields may appear depending on version and configuration.

### 6.2. Saving Initial State

In a `mongosh` lab session:

```javascript
const profileDb = db.getSiblingDB("profile_lab");
const originalProfiling = profileDb.getProfilingStatus();

printjson(originalProfiling);
```

When planning a change on a live system, log the status in an **access-controlled** change record along with timestamp, owner, and server version.

### 6.3. Enabling Level 1

```javascript
profileDb.setProfilingLevel(1, {
  slowms: 100,
  sampleRate: 1.0
});

printjson(profileDb.getProfilingStatus());
```

You must hold appropriate administrative privileges first. Some managed deployments restrict calling this API directly.

### 6.4. Adjusting Sampling

```javascript
profileDb.setProfilingLevel(1, {
  slowms: 100,
  sampleRate: 0.25
});
```

A rate of `0.25` samples roughly one quarter of qualifying operations per version semantics; it does not guarantee exactly one record out of every four operations.

### 6.5. Disabling the Profiler

```javascript
profileDb.setProfilingLevel(0);
```

**Running only this does not guarantee a full rollback.** If you changed `slowms` or `sampleRate`, those values may still differ from their initial state. Restore from your saved configuration and check any `filter`.

### 6.6. Restoring Exact Initial State

A runbook should:

1. Save initial `was`/level.
2. Save `slowms`.
3. Save `sampleRate`.
4. Save `filter` if present.
5. Note explicit vs. inherited settings if the API/deployment distinguishes them.
6. Account for global impact.
7. Restore using commands compatible with your server version.
8. Re-read status and verify.

Example *only when the original state was literally level 0, `slowms` 100, `sampleRate` 1, and no filter*:

```javascript
profileDb.setProfilingLevel(0, {
  slowms: 100,
  sampleRate: 1.0
});

printjson(profileDb.getProfilingStatus());
```

Never use example defaults to overwrite an unknown production configuration.

---

## 7. Critical Point: `slowms` and `sampleRate` Can Have Broad Scope

A common misconception is thinking:

> "If I run `db.getSiblingDB("profile_lab").setProfilingLevel(1, {slowms: 10})`, only commands on this database use the 10 ms threshold."

On MongoDB `mongod`, **the profiling level is configured per database**, whereas parameters such as `slowms` and `sampleRate` operate at the process/global level as documented by MongoDB.

Consequently, setting a low threshold from one database can affect **slow-operation diagnostic logging for all other databases** on the same `mongod` process.

### 7.1. Distinguishing the Two Scopes

```text
mongod process
│
├── Database A
│     profiler level: 0/1/2
│
├── Database B
│     profiler level: 0/1/2
│
└── Slow-operation threshold / sampling settings
      have broad process-wide impact per server configuration
```

Never assume calling the helper on `profile_lab` guarantees "zero impact on other workloads."

### 7.2. How Does This Cause Incidents?

Suppose 10 applications share one `mongod` process:

- A developer enables profiling level 1 on a test database.
- At the same time, they pass `slowms: 1`.
- Production traffic on other databases now triggers massive diagnostic slow logs due to the shared threshold.
- Log collectors and disks overload even though profiling was only enabled on the test database.

### 7.3. Runbooks Must Document Blast Radius

Before making changes:

- Verify the MongoDB version.
- Inspect the process's effective configuration.
- Identify all databases and workloads sharing the process.
- Estimate log volume from peak operations/sec.
- Define a short window.
- Assign an owner responsible for rollback.
- Monitor bytes/sec and free disk space.

---

## 8. Understanding `slowms`: The "Slow" Threshold Is Not the Application SLA

The `slowms` parameter (typically matching `slowOpThresholdMs`) is the threshold MongoDB uses to classify operations as slow in supported profiling and diagnostic logging mechanisms.

### 8.1. Common Default

In many MongoDB Server releases, the default threshold is 100 ms. However, **never assume production still uses the default**; always inspect `getProfilingStatus()` or configuration files.

### 8.2. Server Timing Differs from Client Timing

Suppose:

```text
HTTP request latency:         950 ms
Driver command latency:       650 ms
MongoDB profiler millis:      480 ms
Network / scheduling / other: remainder
```

These illustrative numbers show that the profiler does not measure the entire request.

### 8.3. SLOs Differ by Workload

| Workload | Example target | Profiler threshold to consider |
|---|---|---|
| Online checkout | p95 under 150 ms | May need visibility on commands under 100 ms |
| Batch analytics | Runtime under 60 s | 100 ms may capture far too much data |
| Backoffice report | p95 under 3 s | Choose threshold by query/operation type |
| Streaming consumer | Lag and throughput | Watch `getMore`, writes, batches |
| Multi-tenant API | SLOs vary by tenant tier | Focus on shape, rate, and tenant skew |

The goal is not picking one universal threshold for every workload. Pick a threshold that captures **enough signal** without triggering a log storm.

### 8.4. A High Threshold Can Miss Frequent Moderate Queries

Suppose a query takes 80 ms each time and runs 1,000 times/sec. It stays below 100 ms yet burns significant CPU and drives up total load.

Do not inspect only slow queries above 100 ms; CPU/ops metrics, command latency histograms, and application traces remain essential.

### 8.5. Ultra-Low Thresholds

```javascript
profileDb.setProfilingLevel(1, {
  slowms: 0,
  sampleRate: 1.0
});
```

This can generate huge profile and slow-log volumes under supported rules. Use it only in an isolated lab or a tightly controlled investigation window.

Never treat it as a safe long-term configuration.

---

## 9. Understanding `sampleRate`: Collecting Fewer Records Does Not Reduce Query Load

`sampleRate` typically ranges from `0.0` to `1.0`.

Example:

```javascript
profileDb.setProfilingLevel(1, {
  slowms: 100,
  sampleRate: 0.10
});
```

Practical meaning: capture a fraction of qualifying operations according to the sampling mechanism.

### 9.1. Why Sample?

If a workload generates 5,000 slow operations per minute, recording all of them causes:

- Huge profile record volume.
- Rapid capped collection wrap-around.
- Read/write overhead.
- Heavy export/ingestion traffic.
- Greater exposure of sensitive query values.

Sampling lightens the investigation while still surfacing common patterns.

### 9.2. Sampling Does Not Guarantee Exact Ratios in Small Groups

For a query shape occurring three times, `sampleRate: 0.1` can easily capture zero records. Therefore:

- Never interpret "no profile records" as proof that no slow queries occurred.
- Never use a sampled profiler as an exact audit trail.
- For rare incidents, use a different filter or scope.
- When extrapolating total counts from sampled data, explicitly state uncertainty.

### 9.3. Never Compare Raw Log Counts Across `sampleRate` Changes

Suppose:

```text
Before change:
sampleRate = 1.0
profile records = 1,000/min

After change:
sampleRate = 0.1
profile records = 100/min
```

You cannot conclude the workload improved 10x. You may simply be collecting 10x fewer records.

### 9.4. Sampling Still Has Overhead

Sampling does not mean "zero overhead." The server must still:

- Evaluate whether each operation qualifies.
- Decide whether to sample the record.
- Construct the document for selected operations.
- Write to `system.profile`.
- Serialize detailed fields when selected.

Sampling lowers cost, but never eliminates overhead completely.

### 9.5. When Is a Small `sampleRate` Useful?

- Workloads with millions of operations.
- Goal is identifying **frequent query shapes**.
- Incident lasts long enough to gather sufficient samples.
- Continuous latency metrics exist alongside it for correlation.
- Exact capture of every slow operation is not required.

---

## 10. Profiling Filter: Selecting Signals Conditionally

Some MongoDB Server releases support a **profiling filter** to collect only operations matching specific conditions.

Design intent example:

> "I only want operations targeting the `orders` collection, without profiling every collection in the database."

### 10.1. Example Namespace Filter

On MongoDB versions supporting `filter`:

```javascript
const profileDb = db.getSiblingDB("profile_lab");

profileDb.setProfilingLevel(1, {
  filter: {
    ns: "profile_lab.orders"
  }
});
```

Then verify:

```javascript
printjson(profileDb.getProfilingStatus());
```

Note: Filters evaluate fields supported by MongoDB in the operation/profiling structure, and semantics can vary by version. Consult docs for your running server before applying in production.

### 10.2. Filters Can Alter the Role of `slowms` and `sampleRate`

**Especially important:** When a profiling filter is configured, MongoDB documentation states that `slowms` and `sampleRate` may **no longer apply to profiling and slow-operation diagnostic logging in the usual threshold manner**; the filter directly governs which operations are logged.

Therefore, do not write:

```javascript
profileDb.setProfilingLevel(1, {
  slowms: 100,
  sampleRate: 0.01,
  filter: { ns: "profile_lab.orders" }
});
```

and assume the filter selects `orders` **and** `sampleRate` still caps it to 1% of operations over 100 ms. Verify option interactions in version-specific docs and inspect effective status.

### 10.3. Filter Scope and Cost

A careless filter can select far too many events. Filtering solely by a high-throughput namespace still imposes heavy overhead.

Better approach:

1. Estimate operations/sec for the namespace.
2. Make the filter as narrow as supported.
3. Bound the investigation window.
4. Watch the actual rate of profile records.
5. Revert the filter once finished.

### 10.4. Filters Do Not Replace the Profiler Level

The filter controls selection; the level controls profiling mode per server rules. Never assume setting a filter at level 0 will populate `system.profile`.

### 10.5. Removing Filters Properly

When reverting, clean up the prior filter as well. Some APIs and versions support `filter: "unset"` per documentation.

Never blindly delete a production filter if it was intentionally configured for another monitoring workflow. Save and restore full state.

### 10.6. Use a Filter or Lower the Threshold?

| Goal | Preferred approach |
|---|---|
| Find all slow operations on `mongod` | Threshold + sampling/logs |
| Focus on one specific collection | Filter where supported by version |
| Investigate one query shape | Filter/query telemetry + `explain` |
| Analyze end-to-end application p99 latency | APM/metrics; profiler as supporting evidence |
| Record every security-sensitive action | Supported database auditing, not profiler |

---

## 11. Configuration in `mongod.conf`

On self-managed deployments, MongoDB exposes the `operationProfiling` section:

```yaml
operationProfiling:
  mode: off
  slowOpThresholdMs: 100
  slowOpSampleRate: 1.0
```

### 11.1. Meaning of Configuration Fields

| Config | Meaning |
|---|---|
| `mode: off` | Disables database profiling |
| `mode: slowOp` | Profiles slow operations per config |
| `mode: all` | Broadly profiles operations within scope |
| `slowOpThresholdMs` | Duration threshold in ms |
| `slowOpSampleRate` | Sampling rate |

Some versions support `filter` in config/control commands; use exact syntax for your version.

### 11.2. Startup Config vs. Runtime Changes

- `mongod.conf` is read when the service starts.
- `db.setProfilingLevel()` changes runtime state at the database/server level per supported semantics.
- Runtime changes are not automatically persisted back into the config file.
- A restart can revert settings back to startup values unless configuration management syncs them.

When troubleshooting after a restart, verify effective settings instead of assuming last week's runtime change survived.

### 11.3. Diagnostic Logging Is a Separate Stream

You may configure:

```yaml
systemLog:
  destination: file
  path: /var/log/mongodb/mongod.log
  logAppend: true
  verbosity: 0
```

Here `verbosity: 0` does not silence all messages and **does not mean slow-operation logs are disabled**.

Do not confuse:

```text
operationProfiling.mode
    ↔ profile documents in system.profile

systemLog.verbosity
    ↔ detail level of diagnostic messages
```

### 11.4. Managed Deployments

Atlas and other managed MongoDB providers may restrict profiler/config edits or provide their own Query Profiler, Performance Advisor, and metrics UIs.

Never assume database connection privileges allow editing `mongod.conf` or setting level 2 on Atlas.

---

## 12. Hands-On Lab: Creating the Database and Data

In `mongosh` connected to a **lab MongoDB `mongod`** where profiling changes are permitted:

### 12.1. Preparing the Collection

```javascript
const lab = db.getSiblingDB("profile_lab");
const orders = lab.getCollection("orders");

orders.insertMany([
  {
    _id: 1, tenantId: "t1", customerId: "C01",
    status: "PENDING", total: NumberDecimal("120.00"),
    createdAt: ISODate("2026-11-01T08:00:00Z")
  },
  {
    _id: 2, tenantId: "t1", customerId: "C02",
    status: "PAID", total: NumberDecimal("550.00"),
    createdAt: ISODate("2026-11-01T09:00:00Z")
  },
  {
    _id: 3, tenantId: "t1", customerId: "C01",
    status: "PENDING", total: NumberDecimal("89.00"),
    createdAt: ISODate("2026-11-02T08:00:00Z")
  },
  {
    _id: 4, tenantId: "t1", customerId: "C03",
    status: "PAID", total: NumberDecimal("220.00"),
    createdAt: ISODate("2026-11-02T09:00:00Z")
  },
  {
    _id: 5, tenantId: "t1", customerId: "C04",
    status: "CANCELLED", total: NumberDecimal("90.00"),
    createdAt: ISODate("2026-11-03T08:00:00Z")
  },
  {
    _id: 6, tenantId: "t2", customerId: "C10",
    status: "PENDING", total: NumberDecimal("75.00"),
    createdAt: ISODate("2026-11-03T09:00:00Z")
  },
  {
    _id: 7, tenantId: "t2", customerId: "C10",
    status: "PAID", total: NumberDecimal("425.00"),
    createdAt: ISODate("2026-11-04T08:00:00Z")
  },
  {
    _id: 8, tenantId: "t1", customerId: "C02",
    status: "PENDING", total: NumberDecimal("150.00"),
    createdAt: ISODate("2026-11-04T09:00:00Z")
  },
  {
    _id: 9, tenantId: "t2", customerId: "C11",
    status: "PAID", total: NumberDecimal("199.00"),
    createdAt: ISODate("2026-11-05T08:00:00Z")
  },
  {
    _id: 10, tenantId: "t1", customerId: "C01",
    status: "PAID", total: NumberDecimal("330.00"),
    createdAt: ISODate("2026-11-05T09:00:00Z")
  },
  {
    _id: 11, tenantId: "t2", customerId: "C12",
    status: "PENDING", total: NumberDecimal("610.00"),
    createdAt: ISODate("2026-11-06T08:00:00Z")
  },
  {
    _id: 12, tenantId: "t1", customerId: "C05",
    status: "PENDING", total: NumberDecimal("410.00"),
    createdAt: ISODate("2026-11-06T09:00:00Z")
  }
]);

print("Count:", orders.countDocuments({}));
```

This contains **12 documents** in an empty lab database. Running it twice causes duplicate key errors on `_id`.

### 12.2. Common Queries

```javascript
printjson(orders.find({
  tenantId: "t1",
  status: "PENDING"
}).toArray());

printjson(orders.find({
  customerId: "C01"
}).sort({ createdAt: -1 }).toArray());

printjson(orders.aggregate([
  { $match: { status: "PAID" } },
  {
    $group: {
      _id: "$tenantId",
      revenue: { $sum: "$total" },
      count: { $sum: 1 }
    }
  }
]).toArray());
```

### 12.3. Creating Comparison Indexes

```javascript
orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "idx_tenant_status_time" }
);

orders.createIndex(
  { customerId: 1, createdAt: -1 },
  { name: "idx_customer_time" }
);

printjson(orders.getIndexes());
```

This small lab lacks enough data to benchmark latency or force the planner to choose `IXSCAN`.

---

## 13. Enabling the Profiler in the Lab and Reading Records

### 13.1. Snapshot Initial State

```javascript
const profileDb = db.getSiblingDB("profile_lab");
const before = profileDb.getProfilingStatus();

printjson(before);
```

On a fresh lab database, you will typically see level 0.

### 13.2. Enable Profiling with a Threshold

```javascript
profileDb.setProfilingLevel(1, {
  slowms: 50,
  sampleRate: 1.0
});
```

Re-run the queries from the previous section.

### 13.3. Reading `system.profile`

```javascript
profileDb.system.profile
  .find({
    ns: "profile_lab.orders"
  })
  .sort({ ts: -1 })
  .limit(10)
  .pretty();
```

With 12 documents, queries normally finish well under 50 ms, so there may be **zero records**.

Do not treat that as a MongoDB failure; the threshold or sampling simply did not select those queries.

### 13.4. Lab Option: Brief Level 2

If your lab is isolated, low-traffic, and profiling is authorized:

```javascript
profileDb.setProfilingLevel(2);
```

Run 1–2 small queries, then inspect:

```javascript
profileDb.system.profile
  .find({
    ns: "profile_lab.orders"
  })
  .sort({ ts: -1 })
  .limit(5)
  .pretty();
```

Immediately **restore** the initial level and parameters afterward.

### 13.5. Abbreviated Record Example

An **illustrative** profiler record (not a fixed schema):

```javascript
{
  op: "query",
  ns: "profile_lab.orders",
  command: {
    find: "orders",
    filter: {
      tenantId: "t1",
      status: "PENDING"
    },
    "$db": "profile_lab"
  },
  keysExamined: 5,
  docsExamined: 5,
  nreturned: 4,
  millis: 2,
  planSummary: "IXSCAN { tenantId: 1, status: 1, createdAt: -1 }",
  ts: ISODate("2026-11-14T08:30:00Z")
}
```

Fields such as `keysExamined`, `docsExamined`, and `planSummary` depend on operation type and server version, and the planner may choose `COLLSCAN` on tiny datasets.

---

## 14. Querying `system.profile` Properly

### 14.1. Most Recent Records

```javascript
const p = db.getSiblingDB("profile_lab");

p.system.profile.find(
  {},
  {
    ts: 1,
    op: 1,
    ns: 1,
    millis: 1,
    planSummary: 1
  }
).sort({ ts: -1 }).limit(20);
```

Using a projection prevents accidentally printing entire command payloads containing customer details.

### 14.2. Filtering by Duration

```javascript
p.system.profile.find(
  {
    ns: "profile_lab.orders",
    millis: { $gte: 50 }
  },
  {
    ts: 1,
    op: 1,
    ns: 1,
    millis: 1,
    keysExamined: 1,
    docsExamined: 1,
    nreturned: 1,
    planSummary: 1
  }
).sort({ ts: -1 }).limit(20);
```

If profiling was enabled with a lower threshold or level 2, filtering `millis >= 50` isolates the records of interest.

### 14.3. Grouping by Namespace

```javascript
p.system.profile.aggregate([
  {
    $match: {
      ns: /^profile_lab[.]/
    }
  },
  {
    $group: {
      _id: "$ns",
      records: { $sum: 1 },
      maxMillis: { $max: "$millis" },
      avgMillis: { $avg: "$millis" }
    }
  },
  {
    $sort: {
      maxMillis: -1
    }
  },
  { $limit: 10 }
]);
```

These statistics apply **only to retained records selected by the profiler**. Never report `avgMillis` from a sampled/thresholded subset as the true average latency across all queries.

### 14.4. Top Records by Duration

```javascript
p.system.profile
  .find(
    { millis: { $exists: true } },
    {
      ts: 1,
      ns: 1,
      op: 1,
      millis: 1,
      planSummary: 1,
      keysExamined: 1,
      docsExamined: 1,
      nreturned: 1
    }
  )
  .sort({ millis: -1 })
  .limit(10);
```

This shows the "slowest among captured records," not necessarily the slowest in cluster history.

### 14.5. Does Querying `system.profile` Have Overhead?

Yes. Querying and aggregating `system.profile` still consumes MongoDB resources, even though it is a capped collection.

Never run a dashboard scanning and aggregating `system.profile` every second on an already stressed instance.

For continuous analysis, export or ingest into a log/metrics system designed for time-series queries with proper RBAC and redaction.

---

## 15. Important Fields in a Profiler Record

| Field | Meaning | Usage |
|---|---|---|
| `ts` | Timestamp | Timeline and correlation |
| `op` | Operation type | Distinguish query, getmore, update, command |
| `ns` | Namespace | Identify affected collection |
| `command` | Command document | Query shape/filter/sort (sensitive) |
| `millis` | Server operation duration | Rank and compare against threshold |
| `planSummary` | Plan summary | Spot `COLLSCAN`/`IXSCAN` |
| `keysExamined` | Index keys examined | Assess scan breadth |
| `docsExamined` | Documents examined | Assess filter selectivity |
| `nreturned` | Documents returned | Compare scan ratio |
| `numYield` | Yield count (when present) | Concurrency indicator |
| `locks` | Lock info (when present) | Contention diagnosis |
| `responseLength` | Response size (when present) | Track large payloads |
| `cursorid` | Cursor identifier (when present) | Analyze `getMore` |
| `usedDisk` | Disk spill indicator | Investigate sort/group spills |
| `errCode`/`errMsg` | Error info (when present) | Classify failures |
| Query/plan identifiers | Group executions by shape/plan | Track version-specific fields |

Do not treat this table as a guaranteed schema for every record. For instance, `nreturned` does not behave identically across write commands, and several fields depend on engine and version.

### 15.1. Duration Differs from End-to-End Latency

`millis` is server-side execution time recorded in the profile. User-facing response time also includes:

- Connection pool checkout.
- Driver server selection.
- Network/TLS.
- BSON serialization/deserialization.
- Multiple cursor batches.
- Retries.
- Application logic.

### 15.2. High `keysExamined`

A query using `IXSCAN` with `keysExamined=400000` can still be expensive, especially if `nreturned=10`.

**`IXSCAN` means an index was used—not that index bounds were tight.**

### 15.3. High `docsExamined`

Example:

```text
docsExamined = 300000
nreturned    = 12
planSummary  = COLLSCAN
```

This is a strong clue to check indexes and filters, though not automatic proof that "a missing index is the sole cause." Analytical queries intentionally scanning whole collections can be valid.

### 15.4. `usedDisk`

Certain aggregation/sort pipelines can spill intermediate data to disk depending on operators, version, and settings. When `usedDisk` appears, review:

- Pipeline stages.
- Indexes for sort/group.
- Cardinality.
- Memory and disk pressure.
- MongoDB Server version and `allowDiskUse` semantics.

Never blindly add `allowDiskUse: true` and treat it as a permanent optimization.

### 15.5. Query Identifiers Change Across Versions

MongoDB versions expose `queryHash`, `planCacheKey`, and newer identifiers such as `planCacheShapeHash` or `queryShapeHash` in certain contexts.

Never hardcode a dashboard to a single legacy field name without checking your MongoDB Server version. Canonicalize per release.

---

## 16. Scan Ratio: Read Properly, Avoid Mechanical Conclusions

A reference indicator:

\[
\text{scan ratio} = \frac{\text{docsExamined}}{\max(\text{nreturned},1)}
\]

Example:

```text
docsExamined = 100000
nreturned    = 10

scan ratio   = 10000
```

This suggests the server examined vastly more documents than it returned.

### 16.1. When a High Scan Ratio Is Worth Investigating

- Selective operational API reads.
- Queries filtering by tenant, customer, or status.
- Queries returning a handful of documents after scanning hundreds of thousands.
- Paginated APIs using huge `skip` offsets.
- Indexes misaligned with filter and sort order.

### 16.2. When a High Scan Ratio Is Expected

- Full-dataset `$group` aggregations.
- `countDocuments({})` over large datasets depending on plan.
- Intentional analytics/reporting scans.
- Summary queries aggregating many docs into one output document.

Never enforce a single cluster-wide scan-ratio threshold across every operation type.

### 16.3. `keysExamined` / `docsExamined` / `nreturned`

Common patterns:

| Pattern | Hint |
|---|---|
| Keys 0, docs very high, returned low | Collection scan worth investigating |
| Keys very high, docs high, returned low | Low-selectivity index or wide range |
| Keys very high, docs 0, returned low | Likely covered index scan over a wide range |
| Docs low, returned low, `millis` high | Resource/lock/network waits or concurrent load |
| Returned very high | Missing `limit`/projection or large business payload |

Final conclusions require query shape, `explain`, metrics, and application context.

---

## 17. Profiler and `explain`: Combining Both to Find Root Causes

The profiler captures **an operation that actually ran** under live traffic. `explain("executionStats")` inspects the plan and execution counters at diagnostic time.

Example:

```javascript
const lab = db.getSiblingDB("profile_lab");

const plan = lab.orders.find({
  tenantId: "t1",
  status: "PENDING"
}).sort({
  createdAt: -1
}).explain("executionStats");

printjson(plan.queryPlanner);
printjson(plan.executionStats);
```

### 17.1. Comparison

| Profiler | Explain | Note |
|---|---|---|
| `planSummary` | `winningPlan` | `explain` provides greater detail |
| `docsExamined` | `totalDocsExamined` | Two runs can differ |
| `keysExamined` | `totalKeysExamined` | Sensitive to parameter selectivity |
| `nreturned` | `nReturned` | Must match filter, sort, and limit |
| `millis` | `executionTimeMillis` | Not identical absolute measurements |
| `command` | Query input | Profiler command may be redacted/truncated |

### 17.2. Why Might Results Differ?

- Indexes changed between runs.
- Data volume grew or shrank.
- Query parameters had different selectivity.
- Plan cache state changed.
- Different replica set target node.
- Different CPU, cache, and concurrency load.
- Profiler recorded a `getMore` while `explain` inspects `find`.
- Production query used a different collation, hint, or limit.
- Different server engine or version.

**Never claim that a post-incident `explain` is guaranteed to match the exact plan executed during the incident.**

### 17.3. Write Queries: Never Replay to Analyze

If the profiler logged:

```javascript
db.orders.deleteMany({ status: "EXPIRED" });
```

never copy and re-run that operation on production just to check performance—it modifies or deletes data.

Use non-executing plan inspection methods appropriate to your version, staging/snapshots, or safe diagnostic tooling.

---

## 18. Profiler and Slow-Operation Diagnostic Log: The Real Relationship

This is a frequent operational trap.

### 18.1. Diagnostic Slow Logs Can Exist at Profiler Level 0

```text
Database profiler:
  level = 0
  system.profile: no new records written

MongoDB diagnostic log:
  can still emit "Slow query" events
  based on slow-operation settings
```

Thus a DBA can see `Slow query` in server logs while `system.profile` is empty. That is not necessarily a misconfiguration.

### 18.2. Profiler Level 1 Is Not a Separate Log File

When level 1 is enabled, records go into `<database>.system.profile` on `mongod`. Meanwhile, the server diagnostic log may also emit slow entries.

Do not count both sources as two separate operations when totaling workload volume.

### 18.3. Which Level for Continuous Monitoring?

Typical practice:

- Diagnostic logs and metrics for continuous monitoring.
- Profiler level 1 where policy, workload, and overhead allow.
- Profiler level 2 only in labs or very short incident windows.
- Structured log collectors for multi-node aggregation.
- Managed monitoring when provided by infrastructure.

No single setup fits every SLA.

### 18.4. Log Records Can Be Truncated or Redacted

The server can truncate command payloads in logs, and profile records must also be checked for sensitive fields and truncation per version.

Never rely on the profiler always preserving complete query values for replay or auditing.

---

## 19. `mongod` and `mongos`: Scope of Observation

### 19.1. The Profiler Runs on `mongod`

The database profiler writes into `system.profile` inside databases on `mongod`.

### 19.2. `mongos` Does Not Store Profiles the Same Way

`mongos` is a router in a sharded cluster and lacks per-database `system.profile` collections like `mongod`.

Therefore:

- Do not call `db.setProfilingLevel(2)` on `mongos` expecting to enable profiling across all shards.
- Collect `mongos` diagnostic logs for the router's perspective.
- Collect profiler/logs from individual shard members per topology.
- Distinguish shard execution time from router-level latency.

### 19.3. Replica Sets Have Multiple Members

Example:

```text
rs0
├── mongo-a PRIMARY
├── mongo-b SECONDARY
└── mongo-c SECONDARY
```

If the application uses `secondaryPreferred` read preference, reads run on secondaries rather than the primary.

Enabling the profiler only on the primary and concluding "there are no slow queries" can miss slow reads on secondaries.

### 19.4. Profiling Config Is Managed per Process and Database

Runtime changes on one `mongod` do not automatically propagate cluster-wide in all scenarios. Remember:

- Profiler levels are per-database on each node.
- `slowms` and `sampleRate` have process-wide effects.
- Replica set elections can switch which node serves as primary.
- Managed providers may orchestrate settings differently.

Never enable profiling across all members automatically without calculating combined overhead.

### 19.5. Sharded Clusters Multiply Overhead

If a scatter-gather query fans out to 10 shards and each shard profiles its local piece, one user request generates multiple records.

Never sum durations across 10 shards as end-to-end latency when they execute in parallel and `mongos` merges results.

---

## 20. Modeling Profiler Storage Overhead: A Simple Model

To make informed decisions, estimate:

\[
\text{records/s} \approx \text{ops/s}\times \text{selected fraction}
\]

\[
\text{bytes/s} \approx \text{records/s}\times\text{avg record bytes}
\]

\[
\text{retention seconds} \approx \frac{\text{capped capacity bytes}}{\text{bytes/s}}
\]

**These are approximations.** The selected fraction depends on thresholds, `sampleRate`, filters, operation types, and latency distributions.

### 20.1. Example of a Busy Cluster

Suppose a `mongod` handles:

```text
50,000 operations/s
10% exceed threshold
sampleRate = 0.1
Average profile record = 1.5 KiB
```

Estimate:

```text
Qualifying slow ops: 50,000 × 10% = 5,000 ops/s
Sampled:             5,000 × 0.1 = 500 records/s
Data volume:         500 × 1.5 KiB = 750 KiB/s
Per hour:            ~2.6 GiB/hour
```

This is approximate logical data volume, before accounting for storage-engine overhead and write amplification.

### 20.2. What If Level 2 Is Enabled?

Suppose the record rate approaches total operations/s:

```text
50,000 records/s × 1.5 KiB
  = 75,000 KiB/s
  ≈ 73.2 MiB/s
  ≈ 257 GiB/hour (before storage overhead)
```

Even though the capped collection stops growing once it reaches capacity, the server still executes **massive write volume** continuously overwriting old records.

### 20.3. How Long Are Records Retained?

Suppose capped profile capacity is 256 MiB:

- At 750 KiB/s -> ~350 seconds, under 6 minutes.
- At 75,000 KiB/s -> only ~3–4 seconds in this simple model.

Questions like "Why are there no profiles from 20 minutes ago?" are often explained by rapid capped-collection wrap-around.

### 20.4. Storage Space Is Not the Only Cost

Actual overhead also includes:

- CPU evaluating profiling criteria.
- CPU constructing and serializing BSON documents.
- WiredTiger cache occupancy.
- Journal and write-path overhead.
- Disk I/O.
- Lock and concurrency overhead.
- Contention with application writes.
- Query load if dashboards poll `system.profile` frequently.
- Export bandwidth if shipping records to centralized storage.
- Encryption, retention, and backup compliance for sensitive payloads.

Measure **actual system overhead**, not just the size of `system.profile`.

---

## 21. Impact of the Profiler on CPU, Cache, Locks, and Latency

### 21.1. CPU

To record a profile entry, the server gathers operation metadata and builds a BSON document. High volumes raise CPU usage.

### 21.2. Storage I/O

The profiler writes to MongoDB storage. A read-heavy workload becomes a mixed read/write workload as soon as profiling starts recording heavily.

### 21.3. WiredTiger Cache

Profile records occupy data/metadata pages in the storage engine and interact with cache eviction. Cache contention can drive up disk reads.

### 21.4. Contention

Heavy profile writes combined with queries reading the profile collection create pressure. Even if no single lock stalls every query, total overhead pushes tail latency higher.

### 21.5. Benchmark Distortion

If you compare:

```text
Benchmark A: profiler off
Benchmark B: profiler level 2
```

and see B is slower, do not conclude "MongoDB's query optimizer changed." Part of the gap is instrumentation cost.

When benchmarking production latency, document profiling settings explicitly and ensure apples-to-apples comparisons.

### 21.6. Do Not Ignore the Cost of Analyzing Profile Records

A dashboard repeatedly running:

```javascript
db.system.profile.aggregate([
  { $group: { _id: "$ns", count: { $sum: 1 } } }
]);
```

at high frequency also burns server resources. Raising profiling while simultaneously querying `system.profile` heavily compounds overhead.

---

## 22. Statistical Validity When Sampling

### 22.1. Selection Bias

If you profile only operations exceeding 100 ms, the dataset is **intentionally biased toward slow operations**.

Running:

```javascript
db.system.profile.aggregate([
  {
    $group: {
      _id: null,
      avgMillis: { $avg: "$millis" }
    }
  }
]);
```

computes the **average duration of profiled records**, not the average latency of the overall application workload.

### 22.2. Skewed Percentiles

When only slow operations are captured:

- Profiler p50 will sit at or above the slow threshold.
- It is not the p50 of all queries.
- Computing p95 from a small sample is unstable.
- Never publish it as an official production KPI.

### 22.3. Rare Slow Queries

A query shape occurring once under `sampleRate: 0.1` will likely be missed. Absence of a profile record does not prove the operation never ran.

### 22.4. When You Need Full Histograms

Use application, driver, and monitoring histograms designed to measure 100% of traffic, paired with the profiler for plan-level samples.

### 22.5. Comparing Across Time Windows

Always record for each snapshot:

- Profiler level.
- Slow threshold.
- `sampleRate`.
- Filter.
- Server version.
- Workload mix.
- Query shape distribution.
- Specific cluster nodes observed.

Comparing raw profile record counts across changed settings leads to wrong conclusions.

---

## 23. Security: What Can the Profiler Store?

A profile record can include the `command` payload, such as:

```javascript
db.customers.find({
  email: "customer@example.com",
  phone: "0900000000"
});
```

If the full command payload is recorded, `system.profile` may store:

- Email addresses.
- Phone numbers.
- Tenant/user identifiers.
- Query filter literals.
- Partial update payloads.
- Collection names.
- Sensitive business attributes.

**Never treat `system.profile` as harmless just because it lives inside MongoDB.**

### 23.1. Risks of Level 2

Level 2 captures fast routine operations as well as slow ones, multiplying the volume of sensitive data written and stored.

### 23.2. Sanitize Before Sharing

Instead of pasting a raw profile document into a ticket:

```javascript
{
  ns: "shop.customers",
  command: {
    find: "customers",
    filter: { email: "customer@example.com" }
  },
  docsExamined: 200000,
  nreturned: 1,
  millis: 180
}
```

share a sanitized version:

```json
{
  "ns": "shop.customers",
  "queryShape": {
    "filterFields": ["email"]
  },
  "planSummary": "COLLSCAN",
  "docsExamined": 200000,
  "nReturned": 1,
  "durationMillis": 180
}
```

This preserves query shape and performance counters without leaking customer emails.

### 23.3. RBAC

- Grant `system.profile` read access only to authorized investigators.
- Give operational accounts toggling the profiler least privilege.
- Never grant `root` to a Java API just to query the profiler.
- Audit access to sensitive telemetry.
- Never export raw profile documents to public dashboards.

### 23.4. Encryption and Retention

When exporting profile records:

- Encrypt in transit and at rest.
- Enforce retention limits.
- Enforce access control and auditing.
- Do not retain raw query parameters longer than necessary.
- Support deletion workflows for privacy/compliance requests.

### 23.5. Redaction

Some MongoDB editions/deployments support client log data redaction options. **Never assume log redaction automatically masks every field in `system.profile` identically**; verify profiler-specific and export-pipeline rules.

---

## 24. The MongoDB Profiler Is Not a Security Audit Trail

The profiler is designed for **performance**, not tamper-evident security auditing.

Why?

- Level 1 records only selected operations.
- Sampling drops events.
- Capped collections overwrite older entries.
- Certain operation types and internal actions are not profiled for audit compliance.
- Privileged users can alter profiler settings.
- Sensitive payloads may be truncated or redacted.

If your organization must track:

- Who read which data?
- Who modified roles?
- Who ran administrative commands?
- When did authentication failures occur?

use supported database auditing with formal audit/retention policies—**never rely on the profiler as your sole source**.

---

## 25. Query Profiling in the Java Sync Driver

Java applications should generally not toggle the production database profiler automatically. Instead, applications should:

- Measure command latency with driver command monitoring.
- Log sanitized query shapes and operation names.
- Use distributed tracing and metrics.
- Leave profiler control to DBA/platform teams under change management.

### 25.1. Illustrative `CommandListener`

Java Sync Driver example with SLF4J:

```java
import com.mongodb.event.CommandFailedEvent;
import com.mongodb.event.CommandListener;
import com.mongodb.event.CommandStartedEvent;
import com.mongodb.event.CommandSucceededEvent;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.concurrent.TimeUnit;

public final class MongoTimingListener implements CommandListener {
    private static final Logger LOG =
            LoggerFactory.getLogger(MongoTimingListener.class);

    @Override
    public void commandStarted(CommandStartedEvent event) {
        LOG.debug(
            "mongo.start command={} db={} requestId={}",
            event.getCommandName(),
            event.getDatabaseName(),
            event.getRequestId()
        );
    }

    @Override
    public void commandSucceeded(CommandSucceededEvent event) {
        LOG.debug(
            "mongo.success command={} requestId={} elapsedMs={}",
            event.getCommandName(),
            event.getRequestId(),
            event.getElapsedTime(TimeUnit.MILLISECONDS)
        );
    }

    @Override
    public void commandFailed(CommandFailedEvent event) {
        LOG.warn(
            "mongo.failed command={} requestId={} elapsedMs={} type={}",
            event.getCommandName(),
            event.getRequestId(),
            event.getElapsedTime(TimeUnit.MILLISECONDS),
            event.getThrowable().getClass().getSimpleName()
        );
    }
}
```

Notes:

- Never log `event.getCommand()` by default in production.
- `requestId` is a driver command request ID, not an end-to-end trace ID.
- `elapsedMs` is client/driver observed time, not identical to `system.profile.millis`.
- Use metrics and sampling to avoid logging one line per command at high QPS.
- Exception messages and full stack traces must also be sanitized per policy.

### 25.2. Registering the Listener

```java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

public final class MongoClientFactory {
    public static MongoClient create() {
        String uri = System.getenv("MONGODB_URI");

        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                    "MONGODB_URI must be provided");
        }

        MongoClientSettings settings =
                MongoClientSettings.builder()
                        .applyConnectionString(
                                new ConnectionString(uri))
                        .addCommandListener(new MongoTimingListener())
                        .build();

        return MongoClients.create(settings);
    }
}
```

Never hardcode usernames or passwords in source code. Secret-bearing URIs must also be protected from logs, crash dumps, and unauthorized access.

### 25.3. Controlled Comments

To link application operations with server-side observability, MongoDB supports `comment` on many commands.

Example:

```java
import static com.mongodb.client.model.Filters.eq;

orders.find(eq("status", "PENDING"))
      .comment("service=checkout;operation=listPending")
      .limit(20)
      .into(new java.util.ArrayList<>());
```

Comments must:

- Be short.
- Never contain PII, tokens, or passwords.
- Follow a consistent convention.
- Avoid per-request unique strings where cardinality poses a risk.
- Only be used where supported by command, driver, and server version.
- Not be treated as a trace ID guaranteed in every profiler record.

### 25.4. Client Duration Differs from Profiler `millis`

Example:

```text
Java CommandSucceeded.elapsedMs = 400
MongoDB system.profile.millis    = 250
HTTP endpoint latency            = 650
```

This is not enough to conclude that exactly 150 ms was network latency. Inspect connection pools, retries, cursor batches, serialization, and tracing spans.

### 25.5. Never Allow Web Requests to Call `setProfilingLevel()` Directly

If an application ever exposed an API like:

```text
POST /admin/enable-profiler?level=2
```

it would require strict safeguards:

- Admin authentication and authorization.
- Change approval.
- Allowed-environment restrictions.
- Time-limited leases.
- Auditing.
- Bounded levels and thresholds.
- Automatic rollback.
- Quotas and rate limiting.
- Overhead monitoring.

It is far safer to manage profiling via privileged runbooks and ops tooling rather than public endpoints.

---

## 26. Handling `getMore` and Cursors

MongoDB splits multi-batch queries into commands:

```text
find → firstBatch
getMore → secondBatch
getMore → thirdBatch
...
```

A single profiler record for `find` does not necessarily reflect total cursor iteration time.

### 26.1. `batchSize` Example

```javascript
const lab = db.getSiblingDB("profile_lab");

const allOrders = lab.orders.find({
  tenantId: "t1"
}).batchSize(2).toArray();

print(allOrders.length);
```

When multiple batches are needed, the driver issues `getMore` calls to fetch remaining documents.

### 26.2. Why Inspect `getMore` Records?

If an API reads large numbers of documents:

- The first batch may return quickly.
- Subsequent `getMore` calls may stall on scans, network, or payload transfer.
- Searching only for `op: "query"` misses a substantial share of execution cost.

### 26.3. Cursor Identifiers

Some records carry `cursorid` or cursor metadata. You can correlate with them, keeping in mind:

- Not every record guarantees the same fields.
- Connection and cursor lifecycles can be complex.
- Sharded/`mongos` paths involve multiple commands.
- Never mistake `cursorid` for an HTTP request ID.

### 26.4. Inspection Procedure

1. Inspect related `find` and `getmore` profiler records.
2. Compare durations and batch sizes.
3. Cross-check driver spans and end-to-end request duration.
4. Review pagination and projections.
5. Tune `batchSize` for UX and network efficiency.
6. Question whether the service truly needs to fetch every document.

---

## 27. When Is the Profiler Still Not Enough?

### 27.1. High CPU Without Slow Records

Possible causes:

- Queries taking 30 ms each at hundreds of thousands of QPS.
- `slowms` set to 100 ms.
- Low sampling rate.
- Load from background tasks or index builds.
- CPU spent on compression or replication.
- Excessive concurrent driver requests.

Pair with throughput, `serverStatus`, and resource metrics.

### 27.2. Rising Disk I/O

The profiler reveals large scans but does not show filesystem latency or storage-layer throttling. Inspect OS/storage metrics, WiredTiger cache stats, and disk throughput.

### 27.3. Connection / TLS Errors

If clients fail to connect, operations never reach MongoDB to be profiled. Check diagnostic network/access logs, driver exceptions, and infrastructure metrics.

### 27.4. Locks / Replication Lag

Some profiler records include lock info, yet complete diagnosis also needs:

- `currentOp`.
- Replication status and lag.
- Write concern settings.
- Flow control metrics.
- Storage latency.
- Cluster topology.

### 27.5. Sharded Clusters

A slow scatter-gather query generates records across multiple shards. Combine router logs, shard targeting, and routing context.

### 27.6. Long-Running Queries That Have Not Finished Yet

The profiler writes records only after an operation finishes (or reaches a profilable boundary). To inspect **currently running** operations, use `currentOp`/monitoring where authorized.

`mongosh` example with appropriate privileges:

```javascript
db.getSiblingDB("admin").aggregate([
  { $currentOp: { allUsers: false } },
  {
    $match: {
      active: true
    }
  },
  {
    $project: {
      opid: 1,
      ns: 1,
      secs_running: 1,
      op: 1
    }
  },
  { $limit: 20 }
]);
```

Behavior and permissions vary by topology and version. Never treat a `currentOp` snapshot as a complete history of operations.

---

## 28. Profiler on Atlas and Managed MongoDB

Managed MongoDB services may provide:

- Query Profiler UI.
- Performance Advisor.
- Slow Query Logs.
- Real-Time Performance Panel.
- Metrics and alerting.
- Backup and monitoring telemetry.

Available features and permissions depend on tier, deployment type, and product version.

### 28.1. Do Not Assume You Can Edit Every `mongod` Parameter

On Atlas, MongoDB Operators, or cloud-managed services, editing `mongod.conf` directly may be impossible or unsupported.

Follow the service's official documentation and avoid out-of-band configuration edits outside the control plane.

### 28.2. The UI Profiler Is Not Always Raw `system.profile`

A Query Profiler dashboard may draw from separate log/metric pipelines with different retention and sampling than `system.profile` queried via `mongosh`.

Do not assume every UI entry corresponds to an identical document stored in the database.

### 28.3. Managed Tiers May Restrict

- Ability to set profiling levels.
- Which log files can be downloaded.
- Data retention windows.
- Administrative privileges.
- Data redaction/retention behavior.
- Exposed server counters.

Never extrapolate behavior from a shared tier to a production dedicated tier, or vice versa.

---

## 29. Measuring Before/After Overhead When Enabling the Profiler

To know how much the profiler impacts performance, measure in a controlled way.

### 29.1. Metrics to Track

Before enabling:

- Application p50/p95/p99 latency.
- MongoDB operations/s.
- CPU usage.
- Storage IOPS and latency.
- WiredTiger cache stats.
- Replication lag.
- Free disk space.
- `system.profile` write rate.
- Diagnostic log bytes/s.
- Errors and timeouts.

After enabling, track the same metrics and annotate the exact timestamp.

### 29.2. Fair Comparisons

If traffic doubles right as you turn on profiling, you cannot blame the entire CPU rise on the profiler.

Compare across:

- Equivalent traffic levels.
- Same query mix.
- Same indexes and schema.
- Similar cache, host, and topology state.
- Same MongoDB version.
- Long enough intervals to smooth noise.

### 29.3. Recommended Testing Pattern

```text
Baseline: profiler off
  │
  ├─ baseline metrics/latency
  │
Targeted profiler level 1
  │
  ├─ collect 2–5 min in lab or approved window
  ├─ monitor overhead
  │
Restore configuration
  │
  ├─ confirm metrics recover
  │
Analyze sanitized records
```

This 2–5 minute window is a **lab pattern example**, not a fixed production rule; real duration depends on traffic, risk, and approval.

### 29.4. Define Stop Criteria

Examples:

- CPU exceeds approved budget.
- MongoDB p99 climbs noticeably.
- Free disk drops to warning margin.
- Replication lag grows excessively.
- Profile record write rate exceeds cap.
- Log/collector pipeline experiences backpressure.

Stop and revert before the profiler worsens the incident.

---

## 30. Runbook: Investigating Rising Query Latency with the Profiler

### Step 1 — Identify Symptoms

Record:

- Which API or query shape?
- Incident start time?
- Host, cluster, and shard?
- Which SLO is violated?
- Any recent deployments, schema changes, or index builds?

### Step 2 — Use Low-Cost Signals First

- Application metrics and traces.
- MongoDB diagnostic slow logs.
- CPU, cache, and disk stats.
- Safe `explain` in an isolated environment.
- `currentOp` if long-running operations are active.

If you already have enough evidence, **do not enable the profiler**.

### Step 3 — Assess Risk of Enabling the Profiler

- Current workload operations/s?
- How many databases share the `mongod` process?
- Does the query payload carry user PII?
- Do you hold appropriate privileges?
- What is the write/storage rate for `system.profile`?
- Any replication or HA impact?
- Does the incident require data from secondaries or shards?

### Step 4 — Snapshot Configuration

```javascript
const target = db.getSiblingDB("commerce");
printjson(target.getProfilingStatus());
```

Record level, `slowms`, `sampleRate`, `filter`, timestamp, and target process.

### Step 5 — Enable Controlled Level 1

In an approved environment:

```javascript
target.setProfilingLevel(1, {
  slowms: 100,
  sampleRate: 0.1
});
```

These parameters are illustrative only. Pick threshold and sampling suited to the workload; if a filter exists, verify option interactions.

### Step 6 — Monitor Overhead

Watch continuously during sampling:

- p95/p99 latency.
- CPU.
- Disk I/O.
- Profile records/s.
- Free disk and capped wrap rate.
- Replication lag.
- Log pipeline ingestion latency.

If any guardrail trips, roll back immediately.

### Step 7 — Read Records Safely

```javascript
target.system.profile.find(
  { ns: "commerce.orders" },
  {
    ts: 1,
    op: 1,
    ns: 1,
    millis: 1,
    keysExamined: 1,
    docsExamined: 1,
    nreturned: 1,
    planSummary: 1
  }
).sort({ ts: -1 }).limit(30);
```

Project only required fields; avoid printing sensitive `command` payloads to terminals or public tickets.

### Step 8 — Analyze and Verify

- Group by namespace or query shape where identifiers exist.
- Flag records with high scan ratios or anomalous durations.
- Verify with `explain`.
- Evaluate indexes, queries, and traffic skew.
- Check lock, I/O, and replication factors.
- Correlate with application traces and timeouts.

### Step 9 — Controlled Remediation

Options include:

- Adding an index tailored to the query shape.
- Fixing filter predicates.
- Adding tenant or shard-key predicates.
- Reducing returned documents via pagination and projection.
- Optimizing sort or aggregation pipelines.
- Tuning batch sizes.
- Isolating analytics workloads.
- Adjusting API behavior where appropriate for the business.

Never throw hardware at the problem before understanding the root cause.

### Step 10 — Restore the Profiler

- Restore exact profiling level.
- Restore `slowms`, `sampleRate`, and `filter`.
- Verify all affected databases and processes.
- Confirm CPU, disk, and log volume return to baseline.
- Archive sanitized evidence.
- Write the incident report and refine alerts.

---

## 31. Profiler Change Record Template

Before making changes, fill out:

| Field | Content |
|---|---|
| Incident/Change ID | Ticket or change identifier |
| Owner | Responsible engineer |
| Environment | Production / Staging / Lab |
| MongoDB Server version | Exact running version |
| Cluster/Replica set | Topology name |
| Target process | Host / pod / instance |
| Database | Target database for profiler |
| Current level | 0 / 1 / 2 |
| Current `slowms` | Current value |
| Current `sampleRate` | Current value |
| Current `filter` | Current condition or none |
| Proposed level | 1 or 2 with justification |
| Proposed `slowms`/`sampleRate`/`filter` | Explicit values |
| Expected records/s | Estimate |
| Capped capacity | Actual capacity |
| Sensitive data controls | RBAC / redaction |
| Stop condition | CPU, p99, storage, lag bounds |
| Rollback owner | Engineer responsible for rollback |
| Rollback commands | Pre-reviewed revert commands |
| Validation | Post-rollback metrics and status |

Never approve production level 2 profiling on a ticket lacking an owner and rollback window.

---

## 32. Common Issues

| Symptom | Possible cause | Resolution |
|---|---|---|
| `system.profile` is empty | Level 0 | Check `getProfilingStatus` |
| `system.profile` is empty at level 1 | No query exceeded `slowms` | Compare threshold and workload |
| Some queries are missing | Sampling skipped them | Do not treat absence as certainty |
| Namespace filter shows no records | Wrong filter or namespace | Verify `ns`, schema, and version |
| Server log shows slow queries, profile is empty | Profiler and diagnostic logs are separate | Check level and slow settings |
| Older profile data vanished | Capped collection overwrote it | Estimate retention; export carefully |
| CPU spiked after level 2 | Instrumentation overhead | Disable or reduce profiling |
| Disk I/O surged | Profile writes plus normal writes | Check records/s and storage pressure |
| Log storm in another database | `slowms`/`sampleRate` have process-wide scope | Restore global settings |
| Disabled level 2, slow logs continue | Slow logging is independent of profiler | Check threshold, filter, and diagnostic log |
| Avg `millis` jumped when lowering `slowms`? | Selection bias changed | Compare full histogram metrics |
| Query values missing in record | Truncation, redaction, or optional field | Never assume full command is always present |
| Saw `COLLSCAN` and added index blindly | Small scan or valid query | Run `explain` + review workload |
| Saw `IXSCAN` and assumed optimal | Index range may be huge | Check `keysExamined`/`nreturned` |
| Profiler `millis` differs from HTTP latency | Different timing layers | Inspect driver/APM traces |
| App reads secondary, checked only primary | Wrong process | Follow read preference and topology |
| `mongos` has no `system.profile` | Profiler lives on `mongod` | Use router + shard observability |
| Enabling debug on Atlas denied | Managed tier/role limits | Use supported UI/APIs |
| Unauthorized error reading profile | Missing privileges | Apply proper RBAC; never grant `root` blindly |
| Level 1 enabled, no `getMore` seen | Small result set or excluded by filter | Check batching and event types |
| Forgot to roll back `filter` | Threshold/sampling behaves differently | Restore full profiling config |
| Customer info leaked via export | Command payload carried PII | Sanitize, enforce RBAC, set retention |
| Level 2 profiling slowed benchmark | Instrumentation altered workload | Measure baseline and compare fairly |

---

## 33. Exercise A — Distinguishing Profiler and Slow Log

Given:

```text
Profiler level: 0
slowms: 100
sampleRate: 1.0
```

Answer:

1. Does MongoDB write new records to `system.profile`?
2. Can the server diagnostic log still record slow operations?
3. Will a 200 ms query always have a profile record?
4. Which command checks the profiling level?
5. Why can an operator see `Slow query` in `mongod.log` while `system.profile` has no records?

## 34. Exercise B — Level 1 vs. Level 2

A node executes 20,000 queries/s, of which 2% exceed 100 ms.

1. Estimate qualifying operations at level 1 with `slowms` 100.
2. If `sampleRate` is 0.1, estimate records/s under a simple model.
3. What are the risks of level 2?
4. How should you monitor CPU, disk, and p99?
5. Why can't you derive exact HTTP request counts from profiler record counts?

## 35. Exercise C — Reading `system.profile`

Using `profile_lab.orders`:

1. Read `getProfilingStatus()`.
2. Enable level 1 in an isolated lab.
3. Run a few `find` and `aggregate` queries.
4. Query `system.profile` with a metadata-only projection.
5. Explain why records may be empty if the dataset is tiny.
6. If permitted, briefly enable level 2 in the lab and inspect a few records.
7. Restore the original state.

## 36. Exercise D — Analyzing a Record

Given the illustrative record:

```javascript
{
  op: "query",
  ns: "shop.orders",
  planSummary: "COLLSCAN",
  keysExamined: 0,
  docsExamined: 300000,
  nreturned: 8,
  millis: 930
}
```

Do the following:

1. Compute the scan ratio.
2. State two root-cause hypotheses.
3. Propose queries and `explain` checks to run.
4. Explain why a missing index is not guaranteed to be the sole cause yet.
5. List which companion metrics should be checked.

## 37. Exercise E — Sampling and Statistics

A dashboard shows:

```text
Day 1:
  sampleRate: 1.0
  Profile records: 10,000

Day 2:
  sampleRate: 0.1
  Profile records: 1,100
```

Can you conclude query workload dropped by 89%? Explain sampling bias, thresholds, query mix, and independent metrics required.

## 38. Exercise F — Filters

In a version supporting profile filters:

1. Design a filter selecting only the `orders` collection.
2. Estimate operations/s for that collection.
3. Explain the interaction among `filter`, `slowms`, and `sampleRate`.
4. Show how to inspect effective status.
5. Design a rollback plan for the filter.

## 39. Exercise G — Storage Budget

A `mongod` has:

```text
Profiler capped capacity: 128 MiB
Average record size:      2 KiB
Profile records rate:     250/s
```

Calculate theoretical retention time before overwrite. Propose at least three ways to lower overhead without infinitely increasing capacity.

## 40. Exercise H — Java Driver Correlation

A Java API shows:

```text
HTTP duration:         1200 ms
Driver command:         850 ms
Profiler millis:        600 ms
```

Explain:

1. Where do the three measurements differ?
2. Can you conclude all 250 ms is pure network time?
3. How do `getMore` and retries affect this?
4. Why shouldn't you log `event.getCommand()`?
5. How can traces and comments be used safely?

## 41. Exercise I — Replica Sets and Sharding

A cluster has:

```text
mongos-1
  ├── shardA: rsA
  ├── shardB: rsB
  └── shardC: rsC
```

Answer:

1. Can you enable the profiler on `mongos` the same way as on `mongod`?
2. If you inspect only `shardA`'s primary, which queries do you miss?
3. How many records can one scatter-gather query generate?
4. Why shouldn't you sum per-shard durations to get request duration?
5. Which labels are needed when aggregating logs and profiles?

## 42. Exercise J — Incident Runbook

API p99 climbs after a deployment. The team plans to turn on profiler level 2 across the entire cluster for 24 hours.

Write a safer alternative plan covering:

1. Initial metrics and slow logs.
2. Query traffic and storage budget math.
3. Checking profiler status on the right `mongod`/database.
4. Choosing a smaller level, filter, or sample rate if needed.
5. Time limits and stop conditions.
6. Protecting PII.
7. Collecting records and running `explain`.
8. Rollback and verification.
9. Writing a sanitized incident report.

## 43. Exercise K — Observability Cost vs. Value

Propose policies for three environments:

- **Dev laptop:** Brief level 2 acceptable when needed; low traffic.
- **Staging:** Targeted level 1 with controlled retention.
- **Production:** Default to low-overhead monitoring; enable targeted profiling only under a runbook.

Compare detail level, volume, privacy, and incident response capability.

---

## 44. Checklist Before Enabling the Profiler

### 44.1. Investigation Goal

- [ ] Clear question that needs answering.
- [ ] Reviewed existing slow diagnostic logs and metrics.
- [ ] Safely checked query shapes and `explain`.
- [ ] Concrete justification for needing the profiler.
- [ ] Exact target database and process identified.

### 44.2. Configuration

- [ ] Recorded current profile level.
- [ ] Recorded current `slowms`.
- [ ] Recorded current `sampleRate`.
- [ ] Recorded current `filter` and its semantics.
- [ ] Understood that `slowms`/`sampleRate` affect more than one database.
- [ ] Verified exact MongoDB Server version.
- [ ] Confirmed managed deployment support.

### 44.3. Cost

- [ ] Estimated operations/s.
- [ ] Estimated qualifying fraction.
- [ ] Estimated profile record size.
- [ ] Checked capped collection capacity and retention.
- [ ] Verified CPU, disk, and cache headroom.
- [ ] Monitoring active for p95/p99 and replication lag.
- [ ] Stop conditions defined.
- [ ] No prolonged level 2 in production.

### 44.4. Security

- [ ] RBAC enforced for reading and modifying profiler settings.
- [ ] No raw customer PII pasted into tickets.
- [ ] No secrets logged.
- [ ] Uncontrolled query payload exports prevented.
- [ ] Encryption and retention policy enforced.
- [ ] Profiler not treated as an audit trail.

### 44.5. When Disabling

- [ ] Reverted profile level to original value.
- [ ] Restored `slowms` and `sampleRate`.
- [ ] Restored `filter` if present.
- [ ] Verified across all affected processes and databases.
- [ ] Monitored log/profile write rate returning to baseline.
- [ ] Saved sanitized evidence.
- [ ] Updated runbook.

---

## 45. Common Misconceptions to Remember

| Misconception | Reality |
|---|---|
| The profiler is `mongod.log` | The profiler writes to `system.profile` |
| Level 0 stops all slow query logging | Diagnostic logs can still record slow queries |
| Level 1 affects only the called database for all options | `slowms`/`sampleRate` have process/global effects |
| Level 2 is always best | CPU, write, storage, and privacy costs can be huge |
| `system.profile` keeps every query forever | It is a capped collection |
| `sampleRate: 0.1` captures exactly 10% of every small group | Sampling fluctuates on small counts |
| Fewer profile records means the app sped up | Sampling or threshold may have changed |
| `avg(millis)` from level 1 is overall system mean latency | It is a biased slow-only subset |
| Zero records means zero slow queries | Filter, sampling, threshold, or wrong target may hide them |
| Filter + `sampleRate` always stack as without a filter | Filters can override normal threshold/sampling rules |
| `IXSCAN` means optimal | It can still scan millions of keys |
| `COLLSCAN` is always wrong | Valid for small collections or broad analytics |
| `millis` equals HTTP latency | Measures only server-side operation time |
| The profiler alone diagnoses root causes | Still need `explain`, metrics, and workload context |
| Enlarging capped size fixes everything | Does not remove CPU or I/O overhead |
| `system.profile` is non-sensitive | Can contain query/update values and PII |
| The profiler replaces auditing | Lacks completeness and durability guarantees for audits |
| Java command monitoring equals the profiler | Client-side and server-side scopes differ |
| `mongos` has `system.profile` like `mongod` | No |
| Profiling one primary captures all reads | Reads may run on secondaries |
| Turning off level 2 reverts all settings | `slowms`, `sampleRate`, and `filter` remain |
| Every profile record contains every field | Schema depends on version and operation |
| Benchmarking with profiler enabled has zero impact | Instrumentation can skew benchmark results |

---

## 46. Official MongoDB Documentation

- [MongoDB Manual – Database Profiler](https://www.mongodb.com/docs/manual/tutorial/manage-the-database-profiler/)
- [MongoDB Manual – Database Profiler Output](https://www.mongodb.com/docs/manual/reference/database-profiler/)
- [MongoDB Manual – db.setProfilingLevel()](https://www.mongodb.com/docs/manual/reference/method/db.setProfilingLevel/)
- [MongoDB Manual – db.getProfilingStatus()](https://www.mongodb.com/docs/manual/reference/method/db.getProfilingStatus/)
- [MongoDB Manual – db.getProfilingLevel()](https://www.mongodb.com/docs/manual/reference/method/db.getProfilingLevel/)
- [MongoDB Manual – profile Command](https://www.mongodb.com/docs/manual/reference/command/profile/)
- [MongoDB Manual – operationProfiling Configuration](https://www.mongodb.com/docs/manual/reference/configuration-options/#operationprofiling-options)
- [MongoDB Manual – Log Messages](https://www.mongodb.com/docs/manual/reference/log-messages/)
- [MongoDB Manual – Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Manual – currentOp Aggregation](https://www.mongodb.com/docs/manual/reference/operator/aggregation/currentOp/)
- [MongoDB Manual – serverStatus Command](https://www.mongodb.com/docs/manual/reference/command/serverStatus/)
- [MongoDB Java Sync Driver – Monitoring and Logging](https://www.mongodb.com/docs/drivers/java/sync/current/monitoring-and-logging/)
- [MongoDB Atlas – Query Profiler](https://www.mongodb.com/docs/atlas/tutorial/profile-database/)
- [MongoDB Atlas – Monitoring and Alerts](https://www.mongodb.com/docs/atlas/monitoring-alerts/)

> **Version note:** Profiler records, query shape/plan identifier fields, filters, server-wide parameter scope, and managed deployment controls vary by MongoDB Server version and Atlas tier. In live environments, verify against documentation for your exact server version and infrastructure before modifying configuration. Examples here are educational guides, not scripts to copy verbatim into production.

---

## 47. Conclusion

1. The **database profiler** observes operations at the MongoDB Server layer by writing documents into `<database>.system.profile` on `mongod`.
2. **Level 0** disables profile records, **level 1** collects by threshold or filter, and **level 2** captures broadly with high overhead risk.
3. `slowms` and `sampleRate` must not be assumed isolated to a single database; changing them can affect slow logging process-wide.
4. **Profiling filters** are powerful selectors, provided you understand how they interact with thresholds and sampling.
5. `system.profile` is a **capped collection**: under high rates, old records overwrite rapidly, making it unsuitable for infinite history or auditing.
6. Collection overhead spans **CPU, storage writes, cache, disk I/O, operations, and security**, not just disk capacity for records.
7. Profiler data is a **sampled/filtered subset**, so averages and percentiles derived from it do not represent the whole workload.
8. Inspect `millis`, `ns`, `planSummary`, `keysExamined`, `docsExamined`, and `nreturned`, then verify with `explain()` and metrics.
9. **Never treat raw command/profile data as harmless**: it can expose PII and business secrets.
10. Always treat profiling as an **intentional, time-bounded change with monitoring and rollback**.

**Operational principle:** Collect **only enough data to answer your investigation question**. The best profiler setup delivers actionable evidence without becoming a new source of load or security risk for MongoDB.
