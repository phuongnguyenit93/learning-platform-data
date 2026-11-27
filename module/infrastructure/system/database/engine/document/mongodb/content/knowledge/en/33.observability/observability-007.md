# `currentOp`, Identifying Long-Running Operations, and Conditions for Using `killOp` in MongoDB

An application experiences API latency jumping from tens of milliseconds to several seconds. Someone suggests "running **`killOp`** to kill the longest-running query," yet doing so can interrupt transactions, trigger client retries, cause cascading errors, or fail to fix the real underlying cause. Before terminating any operation, an operator must answer: **what operation is running, who started it, is it executing or waiting, why is it taking so long, and is killing it safe?**

MongoDB lets you observe active operations via the **`$currentOp` aggregation stage** and the **`db.currentOp()`** helper. Once a client-initiated operation is confirmed to be no longer needed or posing severe impact, authorized personnel may consider **`db.killOp(opid)`**. However, this is a **conditional intervention**, not a routine query tuning tool.

This lesson belongs to the **Observability** chapter and focuses on:

1. Observation sources: **`$currentOp`**, **`db.currentOp()`**, profiler, slow query logs, `explain`, and metrics.
2. Fields to read: **`opid`, `active`, `secs_running`, `ns`, `op`, `command`, `appName`, `client`, `planSummary`, `waitingForLock`, `numYields`, `progress`, `lsid`, `transaction`**.
3. Filtering, grouping, and classifying long-running queries by database, namespace, application, host, operation, and wait state.
4. Distinguishing **slow due to resource-heavy queries** from **slow due to locks, queues, slow clients, tailable cursors, index builds, or transactions**.
5. Distinguishing "running long" from "should be killed."
6. When **`killOp`** may be used, when it must not be used, and what to verify before and after.
7. Differences among **`mongod`, replica sets, `mongos`, and sharded clusters**.
8. Proactive prevention using **`maxTimeMS`**, batch limits, proper indexes, `applicationName`, and query comments.
9. Operational runbooks, `mongosh`/Node.js/Java examples, failure scenarios, and exercises.

**Overarching safety principle:** only use **`killOp` on client-initiated operations** after verifying the exact `opid`, host, owner, impact, and authorization. **Never kill internal MongoDB operations** such as replication, checkpoints, balancer tasks, or system jobs simply because they appear in `currentOp`.

## 1. What Does "Long-Running Query" Mean?

A query is considered **long-running** when its execution time exceeds a threshold defined by the **workload's SLA** and warrants investigation. No single universal threshold applies to every system.

Examples:

| Workload | Illustrative target | When to investigate |
|---|---|---|
| API reading a single order by ID | p95 under 100 ms | A 3-second query may be anomalous |
| Daily reporting aggregation API | p95 under 2 seconds | 15 seconds may be an incident |
| Bounded background data export | Completes in a few minutes | 30 seconds may be completely normal |
| Planned index build | Can run for many minutes | Must not be killed just for taking long |
| Change stream awaiting events | Intentionally waits for events | Long wait duration is not an error |

These numbers are **illustrative SLO examples only**; choose thresholds tailored to your real application.

### 1.1. Query Duration Differs from Request Duration

A request passes through:

~~~text
HTTP request
    |
    v
Application queue / authentication
    |
    v
Connection pool checkout
    |
    v
Send MongoDB command
    |
    v
MongoDB operation observed in currentOp
    |
    v
Read result batches / deserialize
    |
    v
Application processing / response
~~~

**`$currentOp`** observes the current MongoDB operation; **it does not measure total application request duration**. If an application stalls for 10 seconds waiting on its connection pool and then runs a 5 ms query, `currentOp` will not report a 10-second query.

### 1.2. Long Does Not Equal Harmful

A scheduled export running during its approved window with an appropriate read preference and no SLA impact may **need no intervention**.

Conversely, a query running for only 1 second that **holds a critical lock or pushes the system into severe contention** can be higher priority than a 30-second reporting query impacting nobody.

Decisions must rest on **cause + impact + urgency**, not a blind threshold comparison.

## 2. What Is `currentOp` and Which API Should You Use?

MongoDB exposes several related interfaces:

| Interface | Role | Recommendation |
|---|---|---|
| **`$currentOp`** aggregation stage | Returns a stream of operation/session documents; supports `$match`/`$project`/`$sort` | **Preferred** for live observation |
| **`db.currentOp()`** | `mongosh` helper for quick viewing and filtering of current ops | Useful for rapid ad-hoc triage |
| **`currentOp` database command** | Legacy backend command | Not preferred; deprecated since MongoDB 6.2 |
| **`system.profile` / profiler** | Stores past operation records per profiling configuration | Suited for slow query history |
| **Slow query logs / Atlas Query Profiler** | Observes slow queries over a time window | Suited for investigating completed events |
| **`explain()`** | Analyzes execution plan of a reproducible query | Useful for index/plan issues |

Per current MongoDB documentation, **`$currentOp` is recommended over the `currentOp` command**. **`db.currentOp()` remains a useful helper**, though due to implementation and `mongosh`/version differences, core examples use **`$currentOp`**.

### 2.1. `currentOp` Is a Point-in-Time Snapshot

~~~text
10:00:00.000   Query A starts
10:00:00.020   Query B starts
10:00:00.060   Query A finishes
10:00:00.100   Operator runs $currentOp
10:00:00.200   Query B finishes
~~~

At 10:00:00.100, `currentOp` sees Query B but **no longer sees Query A**. Therefore:

- A query absent from `currentOp` **does not prove it was never slow**.
- To inspect history, use the profiler, slow-query logs, or APM.
- For continuous visibility, use bounded collection and time-series metrics.

### 2.2. `$currentOp` Is Not a Business Collection

Do not write:

~~~javascript
db.orders.find({ "$currentOp": {} });
~~~

The correct form is running an **aggregation pipeline on the `admin` database** with **`$currentOp` as the first stage**:

~~~javascript
db.getSiblingDB("admin").aggregate([
  {
    $currentOp: {
      allUsers: true,
      idleConnections: false
    }
  }
]);
~~~

This is an **observation command** and does not mutate application data. However, the response can contain commands/filters, client addresses, namespaces, and sensitive metadata; protect access accordingly.

### 2.3. Execution Requirements and Privileges

On deployments with authorization enabled:

- To observe operations across **all users**, the appropriate **`inprog`** privilege is required.
- On standalone/replica sets, observing only your own operations may not require broad `inprog` privileges.
- On sharded clusters, using `$currentOp` requires **`inprog`** privileges per documentation.
- Certain Atlas tiers such as **M0/Flex** do not support `currentOp` commands/helpers the same way dedicated clusters do; verify tier capabilities.

A regular business application **should never receive `inprog`/`killop` just to serve API traffic**. Separate monitoring/on-call identities from application runtime identities.

## 3. Basic `$currentOp` Syntax

### 3.1. Viewing Only the Current User's Operations

~~~javascript
db.getSiblingDB("admin").aggregate([
  {
    $currentOp: {
      allUsers: false,
      idleConnections: false
    }
  }
]);
~~~

**`allUsers: false`** limits scope to the user running the command. Privilege rules and topology still affect visibility.

### 3.2. Viewing All Active Operations Across All Users

~~~javascript
db.getSiblingDB("admin").aggregate([
  {
    $currentOp: {
      allUsers: true,
      idleConnections: false
    }
  },
  {
    $match: {
      active: true
    }
  }
]);
~~~

**`allUsers: true`** requires appropriate privileges; do not grant this to application accounts.

### 3.3. Operations Running Longer Than 5 Seconds

~~~javascript
db.getSiblingDB("admin").aggregate([
  {
    $currentOp: {
      allUsers: true,
      idleConnections: false
    }
  },
  {
    $match: {
      active: true,
      secs_running: { $gte: 5 }
    }
  },
  {
    $sort: {
      secs_running: -1
    }
  }
]);
~~~

**`secs_running`** appears only while an operation is active. It measures elapsed time since the operation started, **not CPU time**, and does not prove the query spent all that time burning CPU.

### 3.4. Compact Projection to Avoid Printing Sensitive Command Bodies

~~~javascript
db.getSiblingDB("admin").aggregate([
  {
    $currentOp: {
      allUsers: true,
      idleConnections: false
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
      _id: 0,
      host: 1,
      shard: 1,
      opid: 1,
      op: 1,
      ns: 1,
      appName: 1,
      active: 1,
      secs_running: 1,
      waitingForLock: 1,
      planSummary: 1,
      numYields: 1,
      msg: 1,
      "command.comment": 1
    }
  },
  {
    $sort: {
      secs_running: -1
    }
  }
]);
~~~

Projecting only **`command.comment`** lowers the risk of exposing sensitive filter literals. Still, **`comment` itself can leak sensitive data if the app populates it improperly**, so use only PII-free IDs or tags.

### 3.5. `$currentOp` Must Be First

Do not write:

~~~javascript
// Invalid structure:
db.getSiblingDB("admin").aggregate([
  { $match: { active: true } },
  { $currentOp: {} }
]);
~~~

Correct:

~~~javascript
db.getSiblingDB("admin").aggregate([
  { $currentOp: {} },
  { $match: { active: true } }
]);
~~~

The **`$currentOp` stage must be the first stage**, and pipelines beginning with `$currentOp` must run against the **`admin` database**. It is not permitted inside a transaction.

## 4. `db.currentOp()` for Quick Checks

The `mongosh` helper accepts filters:

~~~javascript
db.currentOp();
~~~

Or:

~~~javascript
db.currentOp({
  active: true,
  secs_running: { $gt: 3 }
});
~~~

Filter by namespace:

~~~javascript
db.currentOp({
  active: true,
  ns: /^sales\./
});
~~~

Inspect operations waiting for locks:

~~~javascript
db.currentOp({
  waitingForLock: true
});
~~~

Inspect the current user's operations on `mongod`:

~~~javascript
db.currentOp({
  "$ownOps": true
});
~~~

Passing **`true`** in `db.currentOp(true)` includes operations on idle connections and system operations; **do not use `true` as a filter for "only running queries."**

**Version note:** The `currentOp` command was deprecated in MongoDB 6.2; in newer `mongosh` versions, the helper may use `$currentOp` underneath. For large result sets and clean filtering/projection, prefer the `$currentOp` aggregation stage.

## 5. How to Read `currentOp` Output

An illustrative typical document is shown below. Depending on **version, topology, operation type, and permissions**, not every field is always present.

~~~javascript
{
  type: "op",
  host: "db-primary.example.net:27017",
  desc: "conn128",
  client: "198.51.100.25:53124",
  appName: "orders-api",
  active: true,
  opid: 81042,
  secs_running: Long("18"),
  microsecs_running: 18233000,
  op: "command",
  ns: "shop.orders",
  command: {
    find: "orders",
    filter: { status: "PENDING" },
    comment: "orders-api:pending-dashboard",
    "$db": "shop"
  },
  planSummary: "COLLSCAN",
  waitingForLock: false,
  numYields: 25,
  killPending: false
}
~~~

This is **simulated output** to explain fields, not output captured from a real database query.

### 5.1. `type` and `op`

**`type`** distinguishes observed document categories:

- **`op`**: active or tracked operation.
- **`idleSession`**: session with no active operation, potentially holding an open transaction.
- **`idleCursor`**: idle cursor when cursor reporting is enabled.

**`op`** typically takes values such as:

~~~text
command
query
update
insert
remove
getmore
killcursors
none
~~~

Many modern queries report **`op: "command"`**, so filtering solely on **`op: "query"`** misses `find`, `aggregate`, and other commands.

### 5.2. `opid`

**`opid`** identifies an operation during diagnosis and may be passed to **`db.killOp(opid)`**.

Do not confuse:

| Field | Meaning |
|---|---|
| `opid` | Current operation identifier, used when considering `killOp` |
| `connectionId` | Connection identifier handling the operation |
| `lsid` | Logical session identifier |
| `cursorId` | Cursor identifier |
| `requestId` / `comment` | Application-provided correlation values |
| `txnNumber` | Transaction sequence within a session, not `opid` |

**An operation ID is not a "permanent global query ID."** Operations finish and IDs disappear or get reused. Always re-verify immediately before terminating, including **host/shard and command details**.

### 5.3. `active` and `secs_running`

~~~javascript
{
  active: true,
  secs_running: 22
}
~~~

This means MongoDB considers the operation active and roughly 22 seconds have elapsed since it started. It could be:

- Executing a collection or index scan.
- Sorting or aggregating.
- Waiting on a lock or admission queue.
- Holding an operation waiting on a client/server/event in an active-marked state.

**`active: true` does not mean 100% CPU usage.** Inspect wait states and system metrics as well.

### 5.4. `ns`

**`ns`** is the **`database.collection`** namespace:

~~~text
shop.orders
analytics.events
admin.$cmd
~~~

For some commands, `ns` is a command namespace or differs from the target business collection. Thus, if filtering by `ns` misses an operation, check **`command.find`**, **`command.aggregate`**, **`command.update`**, or **`originatingCommand`** depending on the operation.

### 5.5. `command`

**`command`** usually describes the executing command:

~~~javascript
{
  find: "orders",
  filter: {
    status: "PENDING"
  },
  sort: {
    createdAt: -1
  },
  comment: "orders-api:pending-dashboard"
}
~~~

This reveals query patterns and application paths, but may contain **sensitive literals**. Use projections and log access controls to avoid exposing tax IDs, emails, tokens, or customer records.

With **Queryable Encryption**, MongoDB applies **redaction**, omitting portions of `command` in `currentOp`. Never interpret a redacted command as proof that no query exists.

### 5.6. `client`, `appName`, and `clientMetadata`

~~~javascript
{
  appName: "payment-worker",
  client: "198.51.100.45:49300",
  clientMetadata: {
    driver: { name: "mongo-java-driver", version: "..." }
  }
}
~~~

- **`appName`** distinguishes backend services, batch jobs, and reporting tools.
- **`client`** identifies the source IP and port.
- **`clientMetadata`** shows driver/platform details when available.

Good design sets **`applicationName`** in connection settings and attaches **`comment`** on key queries for accurate endpoint/job attribution.

### 5.7. `planSummary`

Common values:

| `planSummary` | General interpretation |
|---|---|
| `COLLSCAN` | Collection scan; can be very expensive with non-selective filters |
| `IXSCAN` | Index scan; does not guarantee the index is ideal or the whole query is optimal |
| `IXSCAN` plus other stages | Check `explain` to inspect fetch, sort, and residual filtering |
| Field absent | Do not infer whether the query used or skipped an index |

**`COLLSCAN` is not always a bug.** On tiny collections or queries reading most documents, a scan can be optimal. Conversely, **`IXSCAN`** can still be slow if it scans huge index ranges and fetches many documents.

### 5.8. `waitingForLock`

~~~javascript
{
  waitingForLock: true
}
~~~

Indicates the operation is waiting on a lock. Never conclude a query lacks an index before checking the **lock holder/blocker** and active transactions.

A long lock wait may stem from a long-open transaction, schema DDL, or another workload. **Killing a waiter** clears a hung request briefly but fails to solve the root cause if the holder keeps the lock.

### 5.9. `numYields`

**`numYields`** counts how many times MongoDB yielded the operation:

~~~javascript
{
  numYields: 250
}
~~~

Large counts can appear on long queries, but it is **not CPU preemptions** and does not by itself prove an error. Evaluate alongside operation type, plan, locks, index usage, and workload.

### 5.10. `locks` and `lockStats`

Some outputs include:

~~~javascript
{
  locks: {
    Global: "r",
    Database: "r",
    Collection: "r"
  },
  lockStats: {
    Collection: {
      acquireCount: { r: Long("12") },
      acquireWaitCount: { r: Long("2") },
      timeAcquiringMicros: { r: Long("85000") }
    }
  }
}
~~~

These details help assess lock wait behavior. **Lock mode notations and `lockStats` structure vary by operation type and version**, so never assume `"r = read-only so zero impact"`.

### 5.11. `msg` and `progress`

Operations such as index builds can report:

~~~javascript
{
  msg: "Index Build: ...",
  progress: {
    done: 820000,
    total: 1000000
  }
}
~~~

If **`progress` is advancing**, the operation may be proceeding on schedule. Never kill blindly just because `secs_running` is large. Confirm whether the task is an **approved migration or index build** and whether change control permits interruption.

### 5.12. `killPending`

~~~javascript
{
  killPending: true
}
~~~

Indicates an interrupt was requested, yet the operation **has not necessarily stopped yet**. `killOp` takes effect at the next **interrupt point**, not as an instant process termination.

### 5.13. `lsid` and `transaction`

Operations inside a multi-document transaction may expose:

~~~javascript
{
  lsid: { id: UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa") },
  transaction: {
    timeOpenMicros: Long("60000000"),
    timeActiveMicros: Long("2000000"),
    timeInactiveMicros: Long("58000000")
  }
}
~~~

This is an abbreviated example. A transaction **open for 60 seconds** but active for only 2 seconds can pressure snapshots, history, or locks even without a continuously active query. To inspect idle transactions, pass **`idleSessions: true`** to `$currentOp`.

### 5.14. `cursor` and `getMore`

An initial query may finish while its cursor stays open and the client issues **`getMore`** calls for subsequent batches.

~~~javascript
{
  op: "getmore",
  command: {
    getMore: Long("1234567890"),
    collection: "events",
    batchSize: 500
  },
  cursor: {
    cursorId: Long("1234567890"),
    tailable: false,
    awaitData: false
  }
}
~~~

A **change stream or tailable cursor with `awaitData`** intentionally waits for events. Never assume a long `getMore` is a bad scan, and never kill a production change stream solely on `secs_running`.

## 6. Version-Dependent Fields

MongoDB expands `currentOp` output across releases. For example:

- MongoDB 8.0 adds details on **admission queues / `currentQueue`**.
- MongoDB 8.2 introduces fields such as **`versionContext`** for FCV operations.
- Per-operation memory metrics appear in newer versions.
- Sharded clusters add **`shard`**, **`client_s`**, and routing metadata.

Therefore, never write alerts like:

~~~javascript
// Fragile: assumes every operation in every version has planSummary.
{ $match: { planSummary: "COLLSCAN" } }
~~~

and conclude everything else is optimal. Use fields when present and build **fallbacks or version-aware branches**.

## 7. `currentOp` Filtering Patterns by Goal

Dumping every operation unfiltered can return huge payloads. Start with a filter tailored to your operational question.

### 7.1. Longest-Running Operations

~~~javascript
db.getSiblingDB("admin").aggregate([
  { $currentOp: { allUsers: true, idleConnections: false } },
  {
    $match: {
      type: "op",
      active: true,
      secs_running: { $gte: 5 }
    }
  },
  { $sort: { secs_running: -1 } },
  { $limit: 20 },
  {
    $project: {
      _id: 0,
      opid: 1,
      host: 1,
      shard: 1,
      secs_running: 1,
      ns: 1,
      op: 1,
      appName: 1,
      waitingForLock: 1,
      planSummary: 1,
      "command.comment": 1
    }
  }
]);
~~~

This retrieves the **top 20 by elapsed time**, not necessarily the 20 most CPU-intensive operations.

### 7.2. Filtering by Database or Collection

~~~javascript
db.getSiblingDB("admin").aggregate([
  { $currentOp: { allUsers: true } },
  {
    $match: {
      active: true,
      ns: "shop.orders"
    }
  }
]);
~~~

If an operation is a **command whose `ns` does not match the business collection**, also filter on **`command.find`**, **`command.aggregate`**, or correlate via **`comment`**. Do not prematurely conclude no queries are running against that collection.

### 7.3. Filtering by Application Name

~~~javascript
db.getSiblingDB("admin").aggregate([
  { $currentOp: { allUsers: true } },
  {
    $match: {
      active: true,
      appName: "billing-service"
    }
  },
  {
    $project: {
      opid: 1,
      host: 1,
      ns: 1,
      secs_running: 1,
      appName: 1,
      "command.comment": 1
    }
  }
]);
~~~

For this filter to be useful, services must configure **`applicationName`** consistently. If every connection has an empty or generic `appName`, attributing load per service becomes difficult.

### 7.4. Filtering Operations Waiting on Locks

~~~javascript
db.getSiblingDB("admin").aggregate([
  { $currentOp: { allUsers: true } },
  {
    $match: {
      active: true,
      waitingForLock: true
    }
  },
  {
    $project: {
      host: 1,
      opid: 1,
      ns: 1,
      secs_running: 1,
      appName: 1,
      lockStats: 1,
      waitingForLock: 1
    }
  }
]);
~~~

A long list of waiters should prompt you to **find the blocker and lock holder** before considering killing any waiter.

### 7.5. Filtering Long-Running `COLLSCAN`s

~~~javascript
db.getSiblingDB("admin").aggregate([
  { $currentOp: { allUsers: true } },
  {
    $match: {
      active: true,
      secs_running: { $gte: 10 },
      planSummary: /COLLSCAN/
    }
  },
  {
    $project: {
      host: 1,
      opid: 1,
      ns: 1,
      secs_running: 1,
      planSummary: 1,
      "command.comment": 1
    }
  }
]);
~~~

This is strictly an **investigative signal**. Collection scans can be valid on small datasets or broad batch reads; verify with **`explain`** and real metrics before creating indexes.

### 7.6. Filtering by Safe Comment

Applications should attach **non-sensitive comments**:

~~~text
orders-api:list-pending:v2
billing-worker:reconcile-hourly
analytics:export-daily
~~~

When `currentOp` includes `command.comment`:

~~~javascript
db.getSiblingDB("admin").aggregate([
  { $currentOp: { allUsers: true } },
  {
    $match: {
      "command.comment": "orders-api:list-pending:v2"
    }
  }
]);
~~~

**Comments may not appear in this exact field for every command/`getMore`, or may be redacted.** For `getMore`, also check **`cursor.originatingCommand.comment`** where available.

### 7.7. Filtering Write Operations

~~~javascript
db.getSiblingDB("admin").aggregate([
  { $currentOp: { allUsers: true } },
  {
    $match: {
      active: true,
      $or: [
        { op: { $in: ["insert", "update", "remove"] } },
        { "command.update": { $exists: true } },
        { "command.delete": { $exists: true } },
        { "command.findAndModify": { $exists: true } }
      ]
    }
  }
]);
~~~

Command representations vary by driver and version, so treat this as a **filtering pattern**, not an exhaustive filter covering 100% of write activity.

### 7.8. Grouping Active Operations by `appName`

~~~javascript
db.getSiblingDB("admin").aggregate([
  { $currentOp: { allUsers: true } },
  { $match: { active: true, type: "op" } },
  {
    $group: {
      _id: "$appName",
      activeCount: { $sum: 1 },
      maxSecs: { $max: "$secs_running" }
    }
  },
  { $sort: { activeCount: -1 } }
]);
~~~

The result is a **snapshot count of active operations**, not throughput in operations/second. To measure QPS, use time-windowed metrics or driver command monitoring.

### 7.9. Observing Inactive Transactions

~~~javascript
db.getSiblingDB("admin").aggregate([
  {
    $currentOp: {
      allUsers: true,
      idleSessions: true
    }
  },
  {
    $match: {
      type: "idleSession",
      transaction: { $exists: true }
    }
  },
  {
    $project: {
      host: 1,
      lsid: 1,
      appName: 1,
      active: 1,
      "transaction.timeOpenMicros": 1,
      "transaction.timeActiveMicros": 1,
      "transaction.timeInactiveMicros": 1
    }
  }
]);
~~~

This uncovers **open transactions with no currently active query**. Idle transactions can still hold snapshots or locks. There is no active `opid` to pass to `killOp` like an ordinary query; manage session/transaction lifecycles using appropriate session controls.

### 7.10. Observing Idle Cursors

~~~javascript
db.getSiblingDB("admin").aggregate([
  {
    $currentOp: {
      allUsers: true,
      idleCursors: true
    }
  },
  {
    $match: {
      type: "idleCursor"
    }
  },
  {
    $project: {
      host: 1,
      appName: 1,
      ns: 1,
      "cursor.cursorId": 1,
      "cursor.createdDate": 1,
      "cursor.lastAccessDate": 1,
      "cursor.noCursorTimeout": 1,
      "cursor.tailable": 1
    }
  }
]);
~~~

An idle cursor is not an actively computing query. For long-lived idle cursors, check **whether the driver closed the cursor**, whether streaming is intentional, and idle timeout policies.

### 7.11. Observing Index Builds—Do Not Kill Blindly

~~~javascript
db.getSiblingDB("admin").aggregate([
  {
    $currentOp: {
      allUsers: true,
      idleConnections: true
    }
  },
  {
    $match: {
      $or: [
        { "command.createIndexes": { $exists: true } },
        { op: "none", msg: /^Index Build/ }
      ]
    }
  },
  {
    $project: {
      host: 1,
      opid: 1,
      msg: 1,
      progress: 1,
      secs_running: 1,
      ns: 1
    }
  }
]);
~~~

This pattern comes from MongoDB docs for inspecting index builds, **though not every rolling index build type matches identically**. Index builds consume resources and run long; if running inside a change window, coordinate with DBAs/on-call before any intervention.

## 8. Categorizing Root Causes of Long-Running Operations

A helpful investigative breakdown:

| Category | Common signals | Next step |
|---|---|---|
| Poor query plan / index | `COLLSCAN`, high keys/docs examined, costly filter/sort | `explain`, review indexes and query shape |
| Waiting for lock | `waitingForLock=true`, `lockStats` | Find blocker, transaction, or schema op |
| Admission / resource queue | `currentQueue`/`queues`, saturated CPU/I/O | Check pool, admission, and resources |
| Large sort / aggregation | Heavy sort/group, disk spills, temp files | `explain`, query rewrite, index, or memory |
| `getMore` / streaming | `op=getmore`, `cursor.awaitData` | Check client, batch size, or change stream |
| Index build / migration | `msg`/`progress`, `createIndexes` | Check change plan and progress |
| Long transaction | High `transaction.timeOpenMicros` | Check snapshot/locks/owner and abort policy |
| Sharded routing | `mongos`/shards, scatter-gather | Check shard targeting and routing |
| Network / client | Server op fast, API slow | Check connection pool, network, downstream |
| Replication / flow control | `waitingForFlowControl`, lag, write concern | Check topology and replication metrics |

One symptom can span **multiple categories**. For instance, an unindexed query drives up I/O, backing up queues and stalling other queries. Killing one query treats only **the immediate symptom**, leaving the missing index or workload issue intact.

## 9. Slowness Due to Suboptimal Query Plans or Indexes

Example:

~~~javascript
db.orders.find({
  tenantId: "T-001",
  status: "PENDING"
}).sort({ createdAt: -1 }).limit(50);
~~~

If the collection holds millions of documents without an index covering the filter and sort, the query may scan heavily or execute a blocking sort.

### 9.1. Gathering Clues with `currentOp`

~~~javascript
db.getSiblingDB("admin").aggregate([
  { $currentOp: { allUsers: true } },
  {
    $match: {
      active: true,
      secs_running: { $gte: 5 },
      ns: "shop.orders"
    }
  },
  {
    $project: {
      opid: 1,
      secs_running: 1,
      planSummary: 1,
      waitingForLock: 1,
      "command.comment": 1
    }
  }
]);
~~~

Seeing **`COLLSCAN`** with **`waitingForLock=false`** points toward the query plan. However, `currentOp` is only a **snapshot** and does not always expose full examined document counts.

### 9.2. Analyzing Safely with `explain`

~~~javascript
db.getSiblingDB("shop").orders
  .find({
    tenantId: "T-001",
    status: "PENDING"
  })
  .sort({ createdAt: -1 })
  .limit(50)
  .explain("executionStats");
~~~

**Important note:** `explain` can make the server perform substantial work. On an overloaded production cluster, do not run `explain("executionStats")` on a heavy query without controlling cost. Start with **`queryPlanner`** or a representative staging environment, then measure cautiously.

### 9.3. Useful `explain` Metrics

- **`winningPlan`**: chosen execution strategy.
- **`COLLSCAN`/`IXSCAN`**: collection vs. index scan.
- **`totalKeysExamined`**: index entries scanned.
- **`totalDocsExamined`**: documents read/checked.
- **`nReturned`**: returned documents.
- **`SORT` stage**: sort not satisfied by the index.
- `executionStats` timing: helpful, though never a replacement for end-to-end p95 metrics.

Example:

~~~text
nReturned          = 50
totalDocsExamined  = 900000
totalKeysExamined  = 0
planSummary        = COLLSCAN
~~~

In most OLTP workloads, this strongly warrants reviewing indexes or query patterns.

### 9.4. Index Design Direction

For equality filters on `tenantId`/`status` and descending sort on `createdAt`:

~~~javascript
db.getSiblingDB("shop").orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
});
~~~

This example follows **Equality -> Sort** for that query pattern. Still, never create a production index solely from one `currentOp` sighting: evaluate existing indexes, write overhead, cardinality, frequency, other query patterns, and rollout safety.

### 9.5. An Index Cannot Cure Every Slow Operation

If a query is waiting on a lock, building a new index can worsen contention. If the API is stalled on a connection pool or external service, a database index fixes nothing. Confirm the root cause first.

## 10. Slowness Due to Locks, Transactions, and Wait Conditions

### 10.1. `waitingForLock`: Find Waiter and Blocker

Suppose:

~~~text
Operation A: schema change/transaction holds resource
              |
              v
Operation B: update waiting for lock
              |
              v
Operation C: another update waiting
~~~

`currentOp` shows B and C with **`waitingForLock=true`**, though it does not always provide a full wait-for graph pointing directly to the blocker.

Do not run:

~~~javascript
// Usually NOT a sensible default action:
db.killOp(opidOfWaiter);
~~~

simply because a waiter is blocked. While the blocker remains, incoming requests will pile right back up.

### 10.2. Long-Open Yet Inactive Transactions

A transaction can behave like:

~~~text
BEGIN TRANSACTION
      |
      v
UPDATE document
      |
      v
Application waits on an external API
      |
      v
Transaction remains open
~~~

Depending on the operation and storage engine, it can hold snapshots, history, or locks even when no active query appears in `currentOp`.

Inspect:

~~~javascript
db.getSiblingDB("admin").aggregate([
  {
    $currentOp: {
      allUsers: true,
      idleSessions: true
    }
  },
  {
    $match: {
      type: "idleSession",
      transaction: { $exists: true }
    }
  },
  {
    $project: {
      lsid: 1,
      appName: 1,
      "transaction.timeOpenMicros": 1,
      "transaction.timeInactiveMicros": 1
    }
  }
]);
~~~

Work with the **session/transaction owner** here. Never mistake `lsid` for `opid` and pass it to `db.killOp()`.

### 10.3. Lock Waits Differ from `writeConflict`

MongoDB uses optimistic concurrency and **write conflicts**. An operation experiencing high write conflicts is not necessarily **`waitingForLock`**:

- A lock wait involves waiting to acquire a lock mode.
- A write conflict happens when two operations race to update the same record, triggering retries or errors depending on context.
- Transactions can abort on write conflicts and require client-side retries.

Distinguish them using `currentOp` (where fields exist), logs, profiler, and app error metrics. Never use `killOp` as a long-term concurrency control mechanism.

### 10.4. Admission Queues and Resources

Modern MongoDB exposes **`currentQueue`/`queues`** in supported versions. An operation can wait in admission queues before consuming execution CPU.

If many operations queue on CPU/I/O, you may need to:

- Lower inbound concurrency.
- Throttle batch workloads or background jobs.
- Optimize queries and plans.
- Review cluster capacity and scaling.
- Check connection pools and retry storms.

**Killing operations** can clear a few queued requests, yet if traffic stays flat, the queue immediately refills.

### 10.5. Flow Control and Replication

In a replica set, writes can encounter **flow control** or wait on write concern/replication. Signals such as **`waitingForFlowControl`**, replication lag, and related metrics aid diagnosis.

If writes stall due to replication lag, killing a writer will not fix inter-node networking or secondary apply throughput. Inspect replica set health and write concern alignment.

## 11. `getMore`, Cursors, and Change Streams

### 11.1. Cursor Lifecycle

~~~text
find / aggregate
      |
      v
Initial batch
      |
      v
Cursor remains open
      |
      +--> getMore batch 2
      |
      +--> getMore batch 3
      |
      +--> Cursor exhausted / closed / timed out
~~~

Never inspect only the initial `find` and ignore **`getMore`** calls that may consume most of the read time.

### 11.2. `getMore` Can Wait on Clients or New Data

For tailable cursors and change streams:

~~~text
getMore
   |
   v
Await next event (by design)
   |
   +--> Event arrives
   |
   +--> Await time limit
~~~

A long `getMore` can be completely normal, especially when **`awaitData=true`**. Check **`cursor.tailable`**, **`cursor.awaitData`**, **`originatingCommand`**, `appName`, and intended purpose.

### 11.3. Idle Cursors and Leaks

Applications forgetting to close cursors leave them idle—especially with `noCursorTimeout`. Investigate:

- Which endpoint or job created the cursor?
- Is intentional streaming happening?
- Is `lastAccessDate` advancing?
- Does the driver close cursors inside exception paths?
- Are concurrent cursors bounded?

In Java, use `try-with-resources` with cursors:

~~~java
try (MongoCursor<Document> cursor =
        collection.find(filter).iterator()) {
    while (cursor.hasNext()) {
        Document item = cursor.next();
        process(item);
    }
}
~~~

**`killOp`** is not the default fix for idle cursors; the owning driver should close cursors or use proper cursor/session management APIs.

### 11.4. Killed Queries Retried by Clients

If the client automatically retries reads, right after `killOp` you may see **a brand-new operation with a new `opid`**. Thus, if an endpoint keeps firing repeated heavy queries:

1. Throttle or block traffic at the endpoint or job.
2. Confirm which query or transaction must stop.
3. If still needed, kill the operation in a controlled manner.
4. Watch retry/error rates and incoming operations.

Blindly looping `killOp` on each new `opid` creates a **kill-retry storm**, destabilizing the system further.

## 12. Comparing `currentOp` with Profiler, Logs, and `explain`

| Tool | What it shows | What it cannot replace |
|---|---|---|
| `$currentOp` | Snapshot of active/idle operations and sessions | Does not provide complete history |
| `db.currentOp()` | Quick filtered snapshot | Not the preferred API for large pipelines |
| Profiler / `system.profile` | Completed operations per profiling settings | Has overhead; not a live snapshot |
| Slow query logs | Logged slow events | Incomplete if thresholds/sampling omit events |
| `explain` | Query plan, stages, and stats | Cannot reconstruct every incident from one run |
| Atlas metrics | CPU, connections, I/O, replication, cache, ops | Cannot isolate a single query without correlation |
| Application traces | Endpoint latency, query comments/correlation | Cannot inspect MongoDB internals |

### 12.1. Use the Profiler When the Operation Already Finished

If a query ran for 12 seconds and finished before on-call opened `mongosh`, **`$currentOp` will no longer show it**.

Instead, inspect:

- Database profiler if enabled per policy.
- Slow-operations log.
- Atlas Query Profiler / Query Insights if supported.
- Application APM traces and command monitoring.

**The profiler carries overhead and can store sensitive query metadata.** Never enable high-level profiling in production without evaluating storage and performance impact.

### 12.2. View Slowness Across Distributions

If API p95 is 150 ms with a few 8-second outliers, hunt down those outliers and query shapes. If system-wide p95 jumps from 150 ms to 2 seconds, examine **concurrency, queues, CPU/I/O, replication, and resource saturation**, not just the single slowest query.

### 12.3. Correlating Application Traces and MongoDB

A request may carry:

~~~text
traceId = trace-19f2
appName = orders-api
queryComment = orders-api:list-pending:v2
MongoDB opid = 81042
~~~

Applications should log safe trace/correlation IDs at the app layer and attach controlled comments on queries. **`opid`** is assigned by MongoDB to an observed operation, not a request trace ID, and changes if the request retries.

## 13. What Is `killOp` and How Does It Work?

**`db.killOp(opid)`** is a `mongosh` helper requesting MongoDB to **terminate a running operation**. MongoDB marks the operation and stops it at the next **safe interrupt point**.

Syntax example:

~~~javascript
// Execute manually only after verifying the exact opid and obtaining approval.
db.killOp(81042);
~~~

**The command above illustrates syntax with a fictional `opid`. Never run a lesson's `opid` in production.**

### 13.1. `killOp` Is Not Killing a Process

~~~text
killOp(opid)
      |
      v
Set interrupt request for target operation
      |
      v
Operation reaches a safe interrupt point
      |
      v
Operation stops / returns error to client
~~~

It does NOT:

~~~text
kill the mongod process
force restart the server
delete the collection
roll back every already-finished write
~~~

Never use OS `kill` or server restarts as a substitute for `killOp` to fix a slow query; those severely impact availability and durability.

### 13.2. Immediate Termination Is Not Guaranteed

Operations stop only at **interrupt points**, or may sit in non-interruptible phases briefly. Thus:

- The kill request may be accepted.
- **`killPending`** may become `true`.
- The operation may remain visible in `currentOp` briefly.
- The client receives an interruption error once it terminates.

Never assume **`killOp` returning success = all impact ceased instantaneously**. Always verify afterward.

### 13.3. The `killop` Privilege

On deployments with authorization:

- Killing another user's operations requires the appropriate **`killop`** privilege action.
- On **`mongod`**, users may kill **their own** operations under documented conditions even without broad `killop` privileges.
- Rules on **`mongos`/sharded clusters** differ; check role definitions and scope.

Never grant `killop` to application accounts or read-only monitoring accounts. Separate **`inprog`** for observers from **`killop`** for authorized incident responders.

### 13.4. `killOp` Is Strictly for Client-Initiated Operations

Key warning from MongoDB documentation: **only terminate client-initiated operations; do not terminate internal database operations**.

Operations **never to kill arbitrarily**:

- Replication and oplog apply operations.
- Checkpoint and storage-engine threads.
- Internal balancer/chunk migrations.
- Internal query/execution tasks not tied to an explicit client operation.
- Background maintenance merely because it runs long.
- Approved index builds or migrations without consulting the runbook.

If you cannot confirm an operation is **client-initiated** and safe to interrupt, **do not call `killOp`**.

### 13.5. Reads Are Safer to Kill; Writes Require Extreme Caution

Stopping a read query causes a client error/retry or lost cursor—usually lower business risk, though still user-visible.

For writes and bulk commands:

- Documents modified before the interrupt point may **already be committed**.
- Never assume every update/delete/insert rolls back on `killOp`.
- Multi-document transactions have atomicity semantics, yet killing a single op inside a transaction does not replace transaction-aware abort/retry logic.
- Clients may see an **unknown outcome**, retrying and duplicating non-idempotent business effects.

Therefore, killing a write requires coordinating with the workload owner and assessing partial write states, idempotency, transactions, and reconciliation plans.

### 13.6. `killOp` Differs from `maxTimeMS`

**`maxTimeMS`** is a timeout set by the client **before the operation executes**:

~~~javascript
db.orders.find({
  status: "PENDING"
}).maxTimeMS(5000);
~~~

If execution exceeds the limit under MongoDB rules, the operation normally fails with **`MaxTimeMSExpired`** at an interrupt point.

**`killOp`** is an intervention **after an operation is already running**, used once a specific offending op is identified.

Neither acts as a strict end-to-end SLA; apps also incur connection pool wait, network, deserialization, retries, and interrupt-point delays.

## 14. When You SHOULD and SHOULD NOT Use `killOp`

Never use a blanket rule like **"if `secs_running > 30`, kill it."** Use a decision matrix:

| Situation | Preferred action | Consider `killOp`? |
|---|---|---|
| Unneeded ad-hoc analyst read scanning heavily and hurting prod | Ask analyst to cancel from client; shed load | **Maybe**, after verifying `opid` and impact |
| Hung API read query with rising traffic and retries | Shed traffic, curb retries, find root cause | **Maybe**, as emergency mitigation |
| 2-minute query that is an approved export | Verify progress and report SLA | **No, not just for duration** |
| Query waiting on a lock held by another transaction | Find blocker and transaction owner | **Do not kill waiters by default** |
| Planned index build in change window | Check change plan and progress | **No without DBA approval** |
| Replication, checkpoint, internal balancer | Follow MongoDB operational runbooks | **No** |
| Production bulk write with unclear commit state | Stop source, check idempotency, reconcile | **Extreme caution** |
| Change stream / `getMore` with `awaitData` | Check stream behavior | **No, not for duration alone** |
| Long inactive transaction | Engage session/transaction owner | **`killOp` is not the default** |
| Query already finished (`opid` gone) | Investigate via logs/profiler | **No target to kill** |

### 14.1. Positive Criteria Before Considering `killOp`

Intervention may be justified only when **all** hold:

1. The operation is clearly **client-initiated**, not an internal task.
2. **Namespace, host/shard, `opid`, `appName`/client, command, or comment** all match the target workload.
3. The operation is causing **real impact** or is confirmed no longer needed.
4. **Client cancellation, `maxTimeMS`, or traffic/concurrency limits** were evaluated first.
5. **Owner/on-call/DBA authorization** and privileges are in place.
6. Impact of interrupting **reads, writes, or transactions** has been assessed.
7. A plan exists to monitor client errors, retries, write outcomes, and recovery.

If any criterion is unmet, **continue diagnosing** rather than killing blindly.

### 14.2. Three Questions Before Acting

**Question 1 — Is it truly causing the incident?**

A 60-second query might just be waiting; another background job could be pegging CPU.

**Question 2 — Will killing it reduce impact or create new errors?**

Killing a non-idempotent write can cause unknown outcomes and duplicate business retries.

**Question 3 — Will the caller immediately re-submit it?**

If workers retry infinitely, `killOp` just heats up the retry loop. Curb traffic or disable the job before intervening.

## 15. Controlled `killOp` Runbook

This is a **decision procedure**, not an auto-kill script. Every kill must be executed by authorized personnel under an approved incident action.

### Step 1 — Capture Incident Context

Record:

~~~text
Incident ID:
UTC timestamp:
Cluster / environment:
Affected database/collection:
User-facing impact:
Error rate / p95 / p99:
CPU / I/O / connections / queue:
Replication state / lag:
Owner / approving on-call:
~~~

Never write simply "query very slow"—you need concrete baselines to compare before and after intervention.

### Step 2 — Capture Read-Only `currentOp`

~~~javascript
db.getSiblingDB("admin").aggregate([
  { $currentOp: { allUsers: true, idleConnections: false } },
  {
    $match: {
      type: "op",
      active: true,
      secs_running: { $gte: 10 }
    }
  },
  {
    $project: {
      _id: 0,
      host: 1,
      shard: 1,
      opid: 1,
      ns: 1,
      op: 1,
      appName: 1,
      client: 1,
      secs_running: 1,
      waitingForLock: 1,
      planSummary: 1,
      killPending: 1,
      "command.comment": 1
    }
  },
  { $sort: { secs_running: -1 } }
]);
~~~

Do not paste raw command/query literals into public incident channels if they carry customer data.

### Step 3 — Verify Operation Owner and Command

Cross-check independent signals:

- **`appName`** or client IP matches the expected service/worker.
- **`ns`** and command match the target collection/workload.
- **`comment`** / APM trace matches the incident.
- Exact **`host`/`shard`** and observation timestamp.
- Whether the operation is a **read** or **write**.
- Not an internal database task.

If ownership is unclear, escalate to the DBA or system owner—never kill because a name looks vaguely familiar.

### Step 4 — Consider Less Disruptive Options

- Cancel the request or stop the job from **the application**.
- Shed or block the endpoint/batch at the load balancer or queue.
- Lower concurrency or rate limits.
- Let the operation finish if nearly done and no longer harmful.
- Defer analytical workloads.
- Apply `maxTimeMS` for **future** requests (do not expect it to stop an already-running unlimited query).

### Step 5 — Approve and Re-Verify `opid`

**Immediately before acting**, re-run observation to confirm:

~~~text
same host/shard?
same appName/client?
same ns/command/comment?
opid still present?
operation still client-initiated?
still causing harm?
~~~

Never reuse an `opid` from an old screenshot taken minutes ago without verifying live state.

### Step 6 — Execute Approved `killOp` for One `opid`

Syntax example:

~~~javascript
// ASSUMING opid 81042 is approved on the exact target mongod/mongos.
// Do NOT run this code with an opid copied from this lesson.
db.killOp(81042);
~~~

In sharded clusters, know **whether `opid` belongs to `mongos` or a specific shard `mongod`** before choosing which endpoint runs the command. See the sharding section below.

Never run:

~~~javascript
// DO NOT DO THIS: auto-kill every operation running over 10 seconds.
db.getSiblingDB("admin").aggregate([
  { $currentOp: { allUsers: true } },
  { $match: { secs_running: { $gte: 10 } } }
]).forEach(op => db.killOp(op.opid));
~~~

That **anti-pattern** can kill internal tasks, legitimate reports, index builds, or in-flight writes.

### Step 7 — Post-Kill Verification on Operation and App

Observe:

- Did the operation **disappear** from `currentOp`, or is **`killPending=true`**?
- Did clients retry and spawn new operations with the same comment/shape?
- How did p95/p99 and error rates respond?
- Did any writes partially commit requiring reconciliation?
- Are replication, locks, and queues recovering?
- Did the app surface interruption/timeout errors properly?

If killing one operation fails to improve latency, keep investigating root cause—**do not escalate immediately into mass killing**.

### Step 8 — Fix Root Cause and Record Incident

Document:

~~~text
Incident cause:
Query shape / endpoint:
Index / query rewrite:
MaxTimeMS policy:
Retry/backpressure changes:
Outcome / user impact:
Follow-up owner and deadline:
~~~

`killOp` is only **conditional firefighting**. Truly closing an incident means preventing recurrence.

## 16. Sharded Clusters: `mongos` Differs from `mongod`

A sharded cluster consists of:

~~~text
Client
   |
   v
mongos router
   |
   +------------+------------+
   |            |            |
   v            v            v
Shard A       Shard B      Shard C
 mongod        mongod       mongod
~~~

A client query can be routed by `mongos` to one or many shards, creating **entries at both the router and individual shards**.

### 16.1. `$currentOp` via `mongos`: `localOps=false`

Running `$currentOp` on `mongos` with **`localOps: false`** (the default) reports operations on **shards** per stage scope:

~~~javascript
db.getSiblingDB("admin").aggregate([
  {
    $currentOp: {
      allUsers: true,
      localOps: false
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
      shard: 1,
      host: 1,
      opid: 1,
      ns: 1,
      secs_running: 1,
      "command.comment": 1
    }
  }
]);
~~~

Preserve the shard-side **`host`**, **`shard`**, and **`opid`**. Never feed a shard-side `opid` blindly to `mongos` assuming it matches a router-side operation ID.

### 16.2. `$currentOp` via `mongos`: `localOps=true`

**`localOps: true`** on `mongos` inspects operations running **on the `mongos` router itself**:

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
      active: true
    }
  },
  {
    $project: {
      host: 1,
      opid: 1,
      ns: 1,
      secs_running: 1,
      appName: 1,
      "command.comment": 1
    }
  }
]);
~~~

These are two **distinct perspectives**, not synonymous aliases. Investigating a scatter-gather query may require both router-side and shard-side evidence.

### 16.3. `targetAllNodes`

In supported MongoDB versions (7.1+), **`targetAllNodes`** makes `$currentOp` return operations from all data-bearing nodes of each shard rather than one node per shard by default.

Do not toggle it carelessly on huge production clusters just to "see everything": consider node count, privileges, and output volume.

### 16.4. `killOp` on `mongos` for Reads

Per MongoDB documentation, **`killOp` run on `mongos` can terminate a read query spanning multiple shards**.

Scenario:

~~~text
Client starts a read through mongos
        |
        v
Read fans out to shards
        |
        v
Operator identifies router-side client operation
        |
        v
Approved killOp on correct mongos opid
        |
        v
Read cancellation can propagate to shards
~~~

This does not mean any arbitrary shard-side `opid` can be killed from any `mongos`. Always verify **exact router, `opid`, and operation**.

### 16.5. `killOp` on `mongos` for Writes

Critical distinction: **`killOp` on `mongos` does NOT propagate to shards when the target operation is a write**.

Therefore:

- Never claim "`mongos` returned kill success so all shard writes stopped."
- Never assume partial or completed writes automatically rolled back.
- Have a DBA inspect shard-side operations and execute proper procedures if a write needs intervention.
- Reconcile data if writes modified subsets of shards.

This is why **you must never use the same `killOp` script blindly for reads and writes in a sharded cluster**.

### 16.6. Multi-Shard Transactions

Sharded transactions involve participants and a coordinator. `$currentOp` exposes:

- Per-shard **`transaction`** metadata when `localOps=false`.
- **Composite transaction view** on `mongos` when `localOps=true`.
- **`lsid`/`txnNumber`** identifying the session-level transaction.

If a transaction stalls or sits idle, inspect **transaction lifecycle and abort semantics** rather than grabbing a random shard `opid` and assuming the entire transaction stopped cleanly.

### 16.7. Log Full Host + `opid` in Incidents

Instead of:

~~~text
Killed opid: 81042
~~~

log:

~~~text
Cluster: prod-sharded
Entry point: mongos-router-2
Node/host of operation: shard-A-primary:27017
Shard: shard-A
Operation ID: 81042
Read or write: read
Application: billing-report
Comment: report:daily-v1
Approval reference: INC-2026-001
~~~

This prevents mixing up `opid`s across nodes and supports auditing.

## 17. Preventing Runaway Operations with `maxTimeMS` and API Design

**`maxTimeMS`** is a preventive control: capping server execution time per operation under MongoDB rules instead of waiting for on-call to run `killOp`.

### 17.1. `maxTimeMS` for `find` in `mongosh`

~~~javascript
db.getSiblingDB("shop").orders
  .find({
    tenantId: "T-001",
    status: "PENDING"
  })
  .sort({ createdAt: -1 })
  .limit(50)
  .maxTimeMS(5000);
~~~

`5000` ms is an **illustrative API policy**, not an optimal limit for every query.

### 17.2. `maxTimeMS` for Aggregations

~~~javascript
db.getSiblingDB("shop").orders.aggregate(
  [
    { $match: { tenantId: "T-001" } },
    {
      $group: {
        _id: "$status",
        count: { $sum: 1 }
      }
    }
  ],
  {
    maxTimeMS: 10000,
    comment: "orders-report:status-count:v1"
  }
);
~~~

Drivers and `mongosh` expose different timeout APIs; what matters is that **the server receives `maxTimeMS` for the operation**.

### 17.3. `maxTimeMS` Is Not the Full Request Deadline

An HTTP request can spend:

~~~text
Connection pool checkout   1500 ms
Network to MongoDB          300 ms
MongoDB operation          4900 ms
Deserialize result          500 ms
Application logic          1000 ms
---------------------------------
Total                      8200 ms
~~~

Even with **`maxTimeMS: 5000`**, the request exceeds a 5-second HTTP deadline due to time outside the DB operation.

Coordinate across layers:

- API/gateway request deadlines.
- Appropriate driver socket, connect, server-selection, and pool-wait timeouts.
- Server-side `maxTimeMS` on queries.
- Client cancellation propagation where workflows support it.
- Bounded retry counts and total retry budgets.
- Per-hop latency metrics.

### 17.4. `maxTimeMS` Also Relies on Interrupt Points

Operations abort only when reaching a MongoDB interrupt check, not at the exact millisecond boundary. On timeout, drivers normally receive **`MaxTimeMSExpired`**.

Never use `maxTimeMS` as a substitute for **proper indexes, filters, sorts, batch sizes**, or capacity management.

### 17.5. Setting `maxTimeMS` by Workload Class

Illustrative breakdown:

| Class | Illustrative policy |
|---|---|
| Interactive read API | 1–3 seconds |
| Moderate reporting query | 10–30 seconds |
| Batch aggregation | 1–5 minutes |
| Background export | Bounded by batch/partition design |
| Change stream | Separate `maxAwaitTimeMS`/await semantics |

These values are **starting points for discussion**, not mandatory MongoDB standards. Derive limits from load testing and SLOs.

### 17.6. Use Pagination Instead of Reading Millions of Documents

Avoid:

~~~javascript
// Unsuitable for real-time APIs on large collections:
db.orders.find({ tenantId: "T-001" }).toArray();
~~~

APIs should paginate:

~~~javascript
db.orders.find({
  tenantId: "T-001",
  createdAt: { $lt: ISODate("2026-11-14T00:00:00Z") }
})
  .sort({ createdAt: -1, _id: -1 })
  .limit(50)
  .maxTimeMS(5000);
~~~

For stable pagination with `(createdAt, _id)` sorting, use **complete keyset pagination** filtering on the `(createdAt, _id)` tuple tie-breaker. The snippet above only illustrates bounding result count; it omits the full keyset tie-breaker condition.

### 17.7. Batch Jobs Must Have Checkpoints

If an export reads 10 million records:

~~~text
Export job
   |
   +--> Partition 1 -> done
   +--> Partition 2 -> done
   +--> Partition 3 -> retry
   +--> Partition 4 -> pending
~~~

Checkpointing lets you stop **the job** cleanly without killing one monolithic query and restarting from zero. Each batch carries its own bounds, timeout, and retry/idempotency logic.

## 18. Setting `appName` and Query Comments from Applications

One of the hardest problems when reading `currentOp` is **not knowing which endpoint originated a command**.

### 18.1. `appName` Identifies the Service

Examples:

~~~text
orders-api
invoice-worker
analytics-report
data-backfill
~~~

Name services by **component and environment** where helpful; never put secrets, `customerId`, or tokens in `appName`.

### 18.2. `comment` Identifies the Query Shape

Examples:

~~~text
orders:list-pending:v2
payments:reconciliation:v1
report:daily-revenue:v3
~~~

Keep comments as **query-pattern tags**, free of sensitive payloads. If including dynamic trace IDs, watch log length and cardinality.

### 18.3. Node.js MongoDB Driver Example

~~~javascript
import { MongoClient } from "mongodb";

const client = new MongoClient(
  process.env.MONGODB_URI,
  {
    appName: "orders-api"
  }
);

await client.connect();

try {
  const collection = client
    .db("shop")
    .collection("orders");

  const cursor = collection.find(
    {
      tenantId: "T-001",
      status: "PENDING"
    },
    {
      projection: {
        _id: 1,
        status: 1,
        createdAt: 1
      },
      comment: "orders:list-pending:v2",
      maxTimeMS: 5000
    }
  )
    .sort({ createdAt: -1 })
    .limit(50);

  try {
    const results = await cursor.toArray();
    console.log("Returned:", results.length);
  } finally {
    await cursor.close();
  }
} finally {
  await client.close();
}
~~~

In production services, **reuse a shared `MongoClient`** instead of creating and closing one per HTTP request. The snippet above shows a standalone script.

If MongoDB returns **`MaxTimeMSExpired`**, handle it cleanly: cap retries, return a clear error, and record metrics. Never infinitely retry an overloaded query.

### 18.4. Java MongoDB Sync Driver Example

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.FindIterable;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.Document;

import java.util.concurrent.TimeUnit;

public final class SlowQueryAwareExample {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException(
                    "MONGODB_URI is required");
        }

        MongoClientSettings settings =
                MongoClientSettings.builder()
                        .applyConnectionString(
                                new ConnectionString(uri))
                        .applicationName("orders-api")
                        .build();

        try (MongoClient client = MongoClients.create(settings)) {
            MongoCollection<Document> orders =
                    client.getDatabase("shop")
                            .getCollection("orders");

            FindIterable<Document> iterable = orders.find(
                    Filters.and(
                            Filters.eq("tenantId", "T-001"),
                            Filters.eq("status", "PENDING")
                    )
            )
                    .sort(Sorts.descending("createdAt"))
                    .limit(50)
                    .maxTime(5, TimeUnit.SECONDS);

            try (MongoCursor<Document> cursor =
                         iterable.iterator()) {
                while (cursor.hasNext()) {
                    Document row = cursor.next();
                    System.out.println(row.get("_id"));
                }
            }
        }
    }
}
~~~

This code **sets `appName`, applies a time bound, and closes the cursor cleanly**. In production apps, load URIs from secret managers, enforce retry policies, avoid logging sensitive data, and keep `MongoClient` scoped to the application lifecycle.

### 18.5. Comments and Operation Correlation Do Not Replace Tracing

`appName` and `comment` aid observability, yet do not build a distributed tracing system on their own. Applications still need:

- Request/trace IDs.
- Driver command monitoring or OpenTelemetry spans.
- Logs grouped by endpoint and query shape.
- End-to-end correlation across request, driver, and result/error.
- Policies redacting sensitive filter/command values.

Never embed full query payloads or JWTs inside comments.

## 19. `mongosh` Lab: Observing a Commented Query

The goal is **practicing observation**, not creating destructive load. Run these steps in a **sandbox/staging environment** you own—never in production without change approval.

### 19.1. Preparing Small Sample Data

In `mongosh`:

~~~javascript
use ops_observe_lab

const demoDocs = Array.from({ length: 300 }, (_, i) => ({
  _id: "EVT-" + String(i + 1).padStart(4, "0"),
  tenantId: "TENANT-TEST",
  status: i % 4 === 0 ? "PENDING" : "DONE",
  amount: (i % 50) * 100,
  createdAt: new Date(
    Date.UTC(2026, 10, 1, 0, 0, i % 60)
  )
}));

db.events.insertMany(demoDocs);
~~~

Re-running on a collection already holding those `_id`s will naturally raise **duplicate key errors**. Never drop other collections or production data to re-run a lab.

300 records is tiny—**not enough to keep a query running long enough to catch in `currentOp`**. That illustrates snapshot monitoring behavior, not a lab bug.

### 19.2. Running a Commented, Time-Bounded Query

In Terminal A:

~~~javascript
db.events.find({
  tenantId: "TENANT-TEST",
  status: "PENDING"
})
  .sort({ createdAt: -1 })
  .comment("lab:pending-events:v1")
  .maxTimeMS(3000)
  .limit(50)
  .toArray();
~~~

This finishes in under a second. Never inflate the dataset to tens of millions or inject infinite CPU loops just to catch it in `currentOp`.

### 19.3. Inspecting `currentOp` from Another Terminal

In Terminal B, using an **authorized monitoring account**:

~~~javascript
db.getSiblingDB("admin").aggregate([
  {
    $currentOp: {
      allUsers: true,
      idleConnections: false
    }
  },
  {
    $match: {
      $or: [
        { "command.comment": "lab:pending-events:v1" },
        {
          "cursor.originatingCommand.comment":
            "lab:pending-events:v1"
        }
      ]
    }
  },
  {
    $project: {
      opid: 1,
      host: 1,
      ns: 1,
      appName: 1,
      secs_running: 1,
      planSummary: 1,
      waitingForLock: 1
    }
  }
]);
~~~

Nothing may appear because Terminal A already completed—highlighting the difference between **live snapshots** and **historical logs/profiler**.

### 19.4. Inspecting the Plan with `explain`

~~~javascript
db.events.find({
  tenantId: "TENANT-TEST",
  status: "PENDING"
})
  .sort({ createdAt: -1 })
  .limit(50)
  .explain("queryPlanner");
~~~

Then create the lab index:

~~~javascript
db.events.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
});
~~~

Re-run `explain` to inspect the updated plan. On tiny collections, the planner may pick various valid plans with virtually identical runtime. Never extrapolate benchmark speedups from 300 lab records to millions of production records.

### 19.5. Should You Run `killOp` in the Lab?

The basic lab **does not require `killOp`**. If testing in an **isolated sandbox**, target only a **client-initiated read operation** you started yourself, verify the exact `opid`, bound impact, and ensure proper privileges/approval.

Never run "auto-find and kill longest operations" scripts on any environment shared with others. Never spawn lock-holding transactions or CPU-burn queries just to have something to kill.

### 19.6. Cleaning Up Sample Data

Only after confirming you are inside **`ops_observe_lab`** and **`events`**:

~~~javascript
// Optional lab cleanup; verify database first.
db.getName();
db.events.countDocuments({ tenantId: "TENANT-TEST" });
~~~

Do not automatically drop collections in this lesson. Cleaning up test records is the environment owner's choice, not a prerequisite for learning `currentOp`.

## 20. Application Behavior When an Operation Is Interrupted

When MongoDB interrupts an operation, clients must handle errors according to workload semantics.

### 20.1. Read Queries

Example:

~~~text
User requests list
        |
        v
MongoDB query interrupted
        |
        v
Driver raises an error
        |
        v
API responds with controlled error / retry logic
~~~

Retrying a read may be appropriate when:

- The request still has remaining deadline budget.
- The query is idempotent and read-only.
- A small retry budget is enforced.
- The database is not actively overloaded.

Never immediately and infinitely retry a query that was just killed for causing overload.

### 20.2. Write Operations

An interrupted write leaves the client uncertain of the final state:

~~~text
Bulk write started
      |
      +-- Document A written
      +-- Document B written
      +-- Document C not yet written
      |
      v
Interruption
      |
      v
Client must reconcile actual state
~~~

Never write:

~~~text
If killOp returns success:
  assume all writes rolled back
~~~

That is **generally false**. Depending on write/bulk semantics, some documents may already be committed prior to interruption.

### 20.3. Retryable Writes and Idempotency

MongoDB drivers support retryable writes under specific conditions, yet not every command or business flow is safely retryable:

- Multi-document bulk commands are not always atomic as a whole.
- Applications may emit emails or external side effects outside the database.
- Requests generating fresh random IDs per retry can create duplicate business records.

Robust design relies on:

- Business idempotency keys.
- Appropriate unique constraints.
- Version/state-guarded updates.
- Transactions where genuinely needed and supported.
- Outbox/inbox patterns for external side effects.
- Reconciliation workflows for unknown outcomes.

### 20.4. Transactions

When an interrupted operation sits inside a transaction, gather:

~~~text
lsid
txnNumber
transaction start time
transaction owner
participants (if sharded)
commit/abort status
~~~

Killing a single command is inferior to **`client.abortTransaction()`** or runbook-guided session termination. Respect transaction error labels and retry semantics.

### 20.5. Never Silently Swallow Errors in APIs

Dangerous pattern:

~~~javascript
try {
  return await doDbOperation();
} catch (error) {
  return { success: true, items: [] };
}
~~~

If a query was interrupted, returning empty success misleads callers into believing no data exists. Instead, return an appropriate error, increment failure metrics, and use fallbacks only when business policy explicitly permits them.

## 21. Automated Monitoring: Alerting Differs from Auto-Killing

Scheduled monitoring can detect:

- Active operation counts exceeding thresholds.
- Long-running operation rates by `appName`/`namespace`.
- Counts of operations with `waitingForLock`.
- Abnormal queue times or connection spikes.
- Repeated `COLLSCAN` query shapes.
- Long-open transactions.

However, **firing an alert** and **auto-killing** are completely different mechanisms.

### 21.1. Never Build Duration-Only Auto-Kill Rules

Avoid:

~~~text
if secs_running > 30:
    killOp(opid)
~~~

Such rules cannot tell:

- Internal tasks from client-initiated operations.
- Planned exports from broken API queries.
- Nearly finished queries from lock-blocked queries.
- Which node/shard owns the `opid` in a sharded cluster.
- Whether writes partially committed.
- Whether apps will immediately retry into a storm.

### 21.2. Alerts Should Send Minimal Safe Evidence

Example safe alert:

~~~text
Alert: long-running client operation
Cluster: prod
Host: db-primary-1
Namespace: shop.orders
App: orders-api
Duration: 34 s
Op type: command
Waiting for lock: false
Plan summary: COLLSCAN
Query tag: orders:list-pending:v2
Suggested action: investigate / escalate
~~~

Never send raw filters containing names, account numbers, or tokens to public alert channels.

### 21.3. Alerts Can Be Noisy

A 5-second poll might catch an 8-second query right before it finishes. Alerting on every single sighting causes alert fatigue.

Combine:

- Sustained anomalous duration.
- Repeated occurrences or concurrency count.
- SLO impact.
- CPU, I/O, and queue metrics.
- Windows, hysteresis, and cooldowns.
- Workload metadata to exclude approved batch jobs.

### 21.4. Monitoring Overhead

Polling `$currentOp` too frequently with **`allUsers=true`**, **`idleConnections=true`**, or fanning out across all nodes via `mongos` creates large payloads and overhead.

Instead:

- Project only needed fields.
- Filter active operations; skip idle connections unless specifically needed.
- Enforce telemetry retention limits.
- Restrict access to collected logs.
- Use dedicated metrics and profilers for historical analysis.

Never scrape full command bodies across all queries every few milliseconds on busy multi-tenant clusters.

## 22. Common Mistakes and Misconceptions

### 22.1. "`currentOp` showed nothing, so the query wasn't slow"

**Wrong because:** `currentOp` is a point-in-time snapshot. The query may have finished before you checked, or ran on another node/shard.

**How to investigate:** Use the profiler, slow query logs, and APM aligned to the incident timestamp; verify topology and observation scope.

### 22.2. "`active: true` means burning CPU continuously"

**Wrong because:** an active operation can be waiting on locks, queues, I/O, or synchronization points.

**How to investigate:** Check `waitingForLock`, `currentQueue`, `lockStats`, CPU/I/O metrics, and flow control.

### 22.3. "`COLLSCAN` must always be killed immediately"

**Wrong because:** `COLLSCAN` is an execution plan, not a severity level. Scans on tiny collections are fast, and full scans can be intentional in batch jobs.

**How to investigate:** Measure resource usage and real impact, inspect `explain` and query shape, and add indexes only where warranted.

### 22.4. "`IXSCAN` proves the query is optimal"

**Wrong because:** an index scan can still traverse millions of keys, fetch huge numbers of documents, or execute expensive sorts.

**How to investigate:** Check `explain`, `totalKeysExamined`, `totalDocsExamined`, `nReturned`, `SORT` stages, cache, and schema.

### 22.5. "`secs_running=90` means 90 seconds of CPU time"

**Wrong because:** `secs_running` is **elapsed wall time** for the operation. CPU time, lock waits, and network waits differ.

**How to investigate:** Correlate `currentOp` with host metrics, driver traces, and the profiler.

### 22.6. "`killOp` returned, so the operation stopped immediately"

**Wrong because:** `killOp` takes effect at an interrupt point. **`killPending=true`** may persist briefly.

**How to investigate:** Re-sample the exact host/shard, confirm disappearance, and check client error logs.

### 22.7. "`killOp` automatically rolls back all writes"

**Wrong because:** writes committed prior to interruption are not automatically undone.

**How to investigate:** Reconcile by business IDs, idempotency keys, operation results, and transaction semantics.

### 22.8. "Killing one waiter unblocks everything"

**Wrong because:** waiters are normally victims, not the blocker.

**How to investigate:** Find the lock holder/transaction and stop the blocking workload or fix the root cause.

### 22.9. "Kill a long-running transaction with any `opid`"

**Wrong because:** transactions can be idle, span multiple operations/shards, and `lsid` differs from `opid`.

**How to investigate:** Inspect `idleSessions`, `transaction` fields, and owners, then use proper `abortTransaction`/session management.

### 22.10. "A long `getMore` is a bad query"

**Wrong because:** `getMore` may intentionally wait on a change stream or tailable cursor.

**How to investigate:** Check `cursor.awaitData`, `cursor.tailable`, `originatingCommand`, and client purpose.

### 22.11. "`db.currentOp(true)` returns only active operations"

**Wrong because:** passing `true` includes idle connections and system operations per helper behavior.

**How to investigate:** Use targeted filters or `$currentOp` with `idleConnections: false`.

### 22.12. "Any `opid` can be killed from `mongos`"

**Wrong because:** router-side and shard-side operations differ; `killOp` on `mongos` propagates for reads, not for writes to shards.

**How to investigate:** Record **host, shard, `opid`, and operation type**, and follow sharded runbooks to act on the right endpoint.

### 22.13. "Collection read privileges let you view all `currentOp` entries"

**Wrong because:** viewing other users' operations requires `inprog`, and killing others' operations requires `killop` in appropriate scopes.

**How to investigate:** Grant minimal admin roles needed; keep cluster management privileges away from application principals.

### 22.14. "`inprog` automatically grants `killop`"

**Wrong because:** **`inprog`** and **`killop`** are separate privilege actions.

**How to investigate:** Use read-only monitoring accounts to diagnose; hand off intervention to authorized on-call/DBA accounts.

### 22.15. "Missing `command` details in `currentOp` means a database bug"

**Wrong because:** commands can be truncated or redacted depending on version, privileges, and Queryable Encryption.

**How to investigate:** Check authorized profiler/APM layers and safe query comments—never disable encryption just to view plaintext.

### 22.16. "`killOp` permanently solved the problem"

**Wrong because:** clients retry, bad query plans remain, and traffic keeps arriving.

**How to investigate:** Fix root causes via indexes, `maxTimeMS`, circuit breakers, rate limits, or query rewrites.

### 22.17. "`maxTimeMS` is an HTTP timeout"

**Wrong because:** `maxTimeMS` bounds MongoDB server operation execution at interrupt checks, excluding pool wait, network, serialization, and HTTP overhead.

**How to investigate:** Configure coherent end-to-end deadlines and per-layer timeouts.

### 22.18. "If `opid` vanished, the kill succeeded"

**Wrong because:** the operation may have finished naturally right as kill was sent, been canceled by the client, timed out, or hit node failover.

**How to investigate:** Check operation outcomes, client errors, logs, and timestamps. `currentOp` holds no history.

### 22.19. "Maximum profiler level has zero impact"

**Wrong because:** profiling imposes write, CPU, and disk overhead and stores sensitive query metadata.

**How to investigate:** Enable with sampling, filters, time windows, access control, and overhead monitoring.

### 22.20. "All long-running operations are queries"

**Wrong because:** `currentOp` shows commands, writes, `getMore`, index builds, transactions, and internal tasks.

**How to investigate:** Inspect `type`, `op`, `command`, `appName`, and descriptions before acting.

## 23. Operational Scenarios with Remediation Flows

### 23.1. Order Lookup API Running a `COLLSCAN`

**Context:**

~~~text
GET /orders?status=PENDING
p95 latency: 8.2 s
currentOp:
  appName = orders-api
  ns = shop.orders
  secs_running = 12
  planSummary = COLLSCAN
  waitingForLock = false
~~~

**Response:**

1. Check incident metrics: CPU/I/O, concurrency, queues.
2. Verify query shape and filter/sort via comment and APM.
3. Run safe `explain` checks; inspect existing indexes and selectivity.
4. Shed traffic / limit concurrency; apply `maxTimeMS` on incoming requests.
5. If a client-initiated op is causing severe harm and is no longer needed, consider `killOp` per runbook.
6. Design and roll out a compound index cleanly, then verify improvement.

**What NOT to do:** automatically kill every `COLLSCAN` across all services.

### 23.2. Multiple Writes Waiting on Locks

**Context:**

~~~text
40 pending updates
waitingForLock = true
One transaction open for 8 minutes
CPU utilization: moderate
~~~

**Response:**

1. Inspect `idleSessions` and `transaction` fields.
2. Identify the transaction owner and code keeping the transaction open.
3. Verify the blocker before deciding to abort the session/transaction.
4. Coordinate clean client abort/timeout and monitor blocked requests draining.
5. Fix the app so transactions are never held open across external API calls or user waits.

**What NOT to do:** kill all 40 waiters while leaving the holding transaction open.

### 23.3. Legitimate Export Report Running Three Minutes

**Context:**

~~~text
appName = analytics-export
comment = daily-archive:v1
secs_running = 180
planSummary = IXSCAN
Resource utilization: expected
Scheduled window: approved
~~~

**Response:** verify progress and report SLA. If critical workloads are unaffected, **let it finish**. If impact is high, coordinate stopping cleanly with the job owner while preserving checkpoints/restartability.

**What NOT to do:** enforce `>30 seconds` as a universal kill rule.

### 23.4. Change Stream Awaiting Events

**Context:**

~~~text
op = getmore
cursor.tailable = true
cursor.awaitData = true
secs_running = 10
Application = notifications-stream
~~~

**Response:** check change stream/await semantics, heartbeats, and client health. This is likely **legitimate waiting**, not an unindexed query.

**What NOT to do:** kill every `getMore` with high `secs_running`.

### 23.5. Bulk Update Interrupted Mid-Run

**Context:**

~~~text
Batch target: 100000 documents
Some updates possibly applied
killOp requested after 20 s
Client received Interrupted
~~~

**Response:**

1. Never assume the entire batch rolled back.
2. Identify business invariants that must hold.
3. Reconcile records using idempotency keys or checkpoints.
4. Re-run remaining incomplete portions under concurrency controls.
5. Refactor batch jobs into small, measurable, restartable chunks.

### 23.6. Shard Query Mistaken for Router Query

**Context:**

~~~text
Observed through mongos:
shard = shard-B
host = shard-B-primary:27017
opid = 82044
~~~

**Response:** distinguish `localOps=false` (shard-side) from `localOps=true` (router-side), recording exact host + `opid`. To abort a distributed read, target the router-side client operation; for writes, remember `mongos` `killOp` does not propagate to shards.

**What NOT to do:** pass `shard-B`'s `opid` to an arbitrary `mongos` without verification.

### 23.7. KMS or Encryption Redacting Profiler/Command Details

**Context:** A QE-enabled query appears in `currentOp`, yet `command` is redacted.

**Response:** rely on `appName`, safe query comments, APM traces, and authorized telemetry; never disable encryption or log plaintext just to debug.

### 23.8. Monitoring Alerts on an `opid` That Already Disappeared

**Context:** Alert reports `opid` 45012 at 12:00:05; on-call opens `mongosh` at 12:01:00 and sees nothing.

**Response:** check the profiler, slow logs, and application traces to see whether it completed, timed out, or was canceled. Never kill an ID that is no longer active.

### 23.9. Planned Long-Running Index Build

**Context:** `currentOp` shows index build at 85% progress, 15 minutes elapsed, storage I/O elevated.

**Response:** verify the change ticket, progress, and resource bounds, and consult the DBA before taking any action. Never kill an index build just because it tops `secs_running`.

### 23.10. Retry Storm After `killOp`

**Context:** On-call kills an expensive read; within seconds five new reads appear with the exact same comment.

**Response:** check circuit breakers and retry policies, shed traffic or stop the calling job, apply deadlines, and fix the underlying query. Stop repeatedly killing operations until the trigger is understood.

## 24. Hands-On Exercises: Reading `currentOp` and Choosing Actions

These exercises use simulated scenarios. You do not need live `killOp` privileges to practice; query steps use **read-only commands** in an authorized environment.

### Exercise 1. Write a Pipeline Finding Operations Over 10 Seconds

**Requirement:** Use `$currentOp` to retrieve active operations across all users running for 10 seconds or more, sorted longest first.

**Answer:**

~~~javascript
db.getSiblingDB("admin").aggregate([
  { $currentOp: { allUsers: true, idleConnections: false } },
  {
    $match: {
      type: "op",
      active: true,
      secs_running: { $gte: 10 }
    }
  },
  { $sort: { secs_running: -1 } },
  {
    $project: {
      _id: 0,
      opid: 1,
      host: 1,
      ns: 1,
      appName: 1,
      secs_running: 1,
      waitingForLock: 1,
      planSummary: 1
    }
  }
]);
~~~

**Note:** `inprog` privilege is required when inspecting all users on authenticated deployments.

### Exercise 2. Does an Empty `currentOp` Prove There Was No Slow Query?

A user reports an API just took 8 seconds, yet `$currentOp` shows zero active queries.

**Question:** Can you conclude the user's report is wrong?

**Answer:** No. The query may already have finished, or latency occurred outside MongoDB (pool, network, application). Use the profiler, logs, and tracing to tell them apart.

### Exercise 3. Distinguishing Active from CPU Usage

Document:

~~~javascript
{
  opid: 101,
  active: true,
  secs_running: 35,
  waitingForLock: true
}
~~~

**Question:** Can you conclude this operation consumed CPU for 35 seconds?

**Answer:** No. `currentOp` shows it waiting on a lock; locate the blocker and inspect host metrics to verify.

### Exercise 4. Filtering Lock Waiters

**Requirement:** Filter operations waiting for a lock.

~~~javascript
db.getSiblingDB("admin").aggregate([
  { $currentOp: { allUsers: true } },
  {
    $match: {
      active: true,
      waitingForLock: true
    }
  },
  {
    $project: {
      opid: 1,
      host: 1,
      ns: 1,
      secs_running: 1,
      lockStats: 1
    }
  }
]);
~~~

**Question:** Should you kill all returned results?

**Answer:** No. Find the blocker and its owner rather than assuming every waiter is the cause.

### Exercise 5. Operation ID vs. Connection ID

`currentOp`:

~~~text
opid = 81042
connectionId = 128
client = 198.51.100.25:53124
~~~

**Question:** Which identifier is passed to `db.killOp`?

**Answer:** **`opid`**. Never substitute `connectionId` or the client port. Re-verify the operation and host/shard right before running.

### Exercise 6. Read Operation with `planSummary: COLLSCAN`

Document:

~~~text
appName: orders-api
secs_running: 12
planSummary: COLLSCAN
waitingForLock: false
~~~

**Question:** Which steps better confirm the root cause?

**Guidance:** Check query shape, filter/sort/indexes, safe `explain` at controlled cost, `totalDocsExamined`/`nReturned`, plus CPU, I/O, and latency metrics.

### Exercise 7. `IXSCAN` Yet Still Slow

A query returns 10 records yet `totalKeysExamined = 2 million`.

**Question:** Does `planSummary: IXSCAN` mean the index is already good enough?

**Answer:** No. An index scan can still scan too many keys; inspect compound index design, field order, selectivity, covered queries, and sort behavior.

### Exercise 8. `getMore` and `awaitData`

Document:

~~~javascript
{
  op: "getmore",
  secs_running: 8,
  cursor: {
    tailable: true,
    awaitData: true
  }
}
~~~

**Question:** Is this a sign to call `killOp` immediately?

**Answer:** No. Tailable cursors wait for new data by design; check the change-stream consumer, timeouts, and application purpose.

### Exercise 9. Idle Transaction

~~~text
type: idleSession
transaction.timeOpenMicros: 180000000
transaction.timeActiveMicros: 2000000
~~~

**Question:** How long has the transaction been open, and how long has it been active?

**Answer:** Open for 180 seconds, active for roughly 2 seconds. Even without a continuously active query, it can impact resources. Engage the owner and proper abort workflow; never confuse `lsid` with `opid`.

### Exercise 10. Criteria for Using `killOp`

An analyst's ad-hoc read query has run for 2 minutes, is confirmed no longer needed, is driving high CPU/I/O, and the owner approved stopping it.

**Question:** May `killOp` be considered?

**Answer:** Yes—**after** re-verifying host, `opid`, and live operation details, confirming privileges and impact, checking client-side cancellation first, and verifying afterward. Duration alone is never the sole criterion.

### Exercise 11. Long-Running Index Build

An index build has run for 20 minutes inside a maintenance window with steadily advancing progress.

**Question:** Why shouldn't you kill it just because it tops the `secs_running` list?

**Answer:** It may be an approved, progressing maintenance operation; interrupting it disrupts change plans and performance. Coordinate with the DBA/change owner.

### Exercise 12. Interrupted Write Operation

A bulk write targeted 1,000 records; after interruption, 400 records are confirmed written.

**Question:** Should you blindly retry all 1,000 without idempotency?

**Answer:** No. Part of the write succeeded; reconcile or chunk batches using idempotency keys or conditional updates to prevent duplicate effects.

### Exercise 13. `killPending`

After `killOp` is accepted, the operation still shows:

~~~javascript
{
  opid: 81042,
  killPending: true
}
~~~

**Question:** Did MongoDB ignore the kill request?

**Answer:** Not necessarily. The operation is waiting to reach a safe interrupt point. Re-check status shortly rather than restarting the server prematurely.

### Exercise 14. `mongos` and Shard-Side `opid`

Observing via `mongos` with `localOps=false`, you see:

~~~text
shard = shard-C
host = shard-C-primary
opid = 3030
~~~

**Question:** Can you call `db.killOp(3030)` on any `mongos` and be sure you killed the right operation?

**Answer:** No. Separate router and shard operation IDs and verify where the command runs. Never assume `opid` is cluster-wide regardless of host.

### Exercise 15. Killing a Read Through `mongos`

A client read runs through `mongos` and scatters across three shards.

**Question:** Per documentation, can `killOp` on `mongos` propagate read cancellation down to shards?

**Answer:** Yes, for distributed reads under supported conditions when targeting the exact router-side operation. It is not a blanket ability to kill arbitrary shard-side ops.

### Exercise 16. Killing a Write Through `mongos`

A write through `mongos` dispatched operations to shards A and B. On-call kills the router-side operation.

**Question:** Can you assume all shard writes stopped and rolled back?

**Answer:** No. MongoDB documentation notes that `killOp` from `mongos` **does not propagate to shards for writes**. Inspect shard-side operations, commit states, and reconcile data.

### Exercise 17. When the Query Already Vanished

`currentOp` captured an operation ID at 13:00; by 13:02 it is gone.

**Question:** What should you do?

**Answer:** Never reuse the stale `opid` for `killOp`. Check the profiler, logs, and APM for the outcome and root cause; if it recurs, inspect the new live operation with its exact host and comment.

### Exercise 18. `applicationName`

All services currently connect with an empty `appName`. Operators cannot distinguish API queries from background workers.

**Question:** Where should this be fixed?

**Answer:** Configure `applicationName` in each service's `MongoClient`/connection string, standardize naming conventions, and align metadata tracing rather than guessing from raw queries in MongoDB.

### Exercise 19. `inprog` vs. `killop` Privileges

A user holds `inprog` but lacks `killop`.

**Question:** Can they inspect other users' operations? Can they kill arbitrarily?

**Answer:** `inprog` permits observation within scope; **it does not grant `killop`**. Intervention requires `killop` or documented own-operation exceptions on `mongod`.

### Exercise 20. `maxTimeMS`

A read API sets `maxTimeMS` to 3000, yet the HTTP request took 7 seconds.

**Question:** Does this prove MongoDB ignored `maxTimeMS`?

**Answer:** No. Total request time includes pool wait, network, serialization, application logic, and retries. `maxTimeMS` is not an end-to-end deadline.

### Exercise 21. Distinguishing QPS from `currentOp` Count

A dashboard polls `$currentOp` and sees 50 active operations.

**Question:** Can you conclude the cluster handles 50 queries/second?

**Answer:** No. That shows **50 active operations in one snapshot**, not a per-second rate. QPS requires time-windowed rate metrics.

### Exercise 22. Filtering by Namespace

You want to inspect all activity on database **`billing`**, yet some commands show a command namespace instead of `billing.invoices`.

**Question:** Why can filtering strictly on `ns: "billing.invoices"` miss operations?

**Answer:** Some commands and `getMore` entries report command namespaces or differ from the business collection. Cross-check **`command.find`**, **`command.aggregate`**, **`originatingCommand`**, `appName`/`comment`, and related namespaces.

### Exercise 23. Analyzing an Operation Waiting on Flow Control

A write shows **`waitingForFlowControl=true`**, and replication lag is also rising.

**Question:** Is a missing index definitely the root cause?

**Answer:** No. This reflects flow control throttling due to replica set lag. Inspect secondaries, write concern, resource utilization, and lag before changing indexes or killing writers.

### Exercise 24. Profiler Is Not `currentOp`

A slow query finished 5 minutes ago. A teammate suggests running `$currentOp` with `secs_running > 5`.

**Question:** Which tool is better suited?

**Answer:** The profiler, slow-query logs, Atlas Query Profiler, or application traces, because `currentOp` captures only live snapshots.

### Exercise 25. Why Avoid High Profiler Levels in Production?

**Guidance:** Profiling imposes write, CPU, and storage overhead, inflates log volume, and can store sensitive query metadata. Enable only with controlled sampling, filters, time windows, and restricted access.

### Exercise 26. Long Query Without SLA Impact

A scheduled report runs for 4 minutes with steady progress and ample CPU/I/O headroom.

**Question:** Should you `killOp` to enforce "zero operations over 30 seconds"?

**Answer:** No. Duration alone is not an incident. Judge by SLA, owner, progress, completion likelihood, and user impact.

### Exercise 27. Query with a Sensitive Comment

A service sends:

~~~text
comment = "lookup-taxid:123456789"
~~~

**Question:** What is the problem?

**Answer:** Comments appear in `currentOp`, profiler records, and logs, leaking sensitive PII. Use query-shape tags without tax IDs or secrets.

### Exercise 28. Auto-Kill Rule

A scheduled script runs:

~~~text
Every 5 seconds:
  find all operations with secs_running > 20
  kill every returned opid
~~~

**Question:** Should this be deployed?

**Answer:** No. It fails to distinguish internal operations, migrations, valid `awaitData` `getMore` cursors, writes/transactions, host/shard scopes, and approvals. Alert, classify, and intervene cleanly instead.

### Exercise 29. Comparing Before/After `killOp`

Before intervention:

~~~text
p95 API = 5.2 s
CPU = 95%
active expensive reads = 80
~~~

After intervention:

~~~text
p95 API = 4.9 s
CPU = 95%
active expensive reads = 78
~~~

**Question:** Can you declare success?

**Guidance:** Not yet. Monitor longer, compare against target SLOs, check retry/new-operation rates, and address root causes. Negligible improvement shows `killOp` alone is insufficient.

### Exercise 30. Designing an Incident Runbook

A sharded MongoDB cluster serves multiple applications. A read query running for 45 seconds is causing API timeouts.

**Requirement:** Write a runbook covering:

1. Checking impacted SLOs and resource metrics.
2. Running `$currentOp` on `mongos` with appropriate `localOps`.
3. Identifying host/shard/`opid`, `appName`, namespace, and query comment.
4. Distinguishing a genuine read operation from writes, transactions, or internal tasks.
5. Engaging the owner and obtaining approval.
6. Attempting client-side cancellation or traffic shedding first.
7. If needed, running `db.killOp` on the exact verified connection and `opid`.
8. Watching `killPending`, client errors, and retries.
9. Verifying p95, CPU, locks, queues, and replication afterward.
10. Using `explain`/profiler and fixing indexes, `maxTimeMS`, and query shapes to prevent recurrence.

**A strong answer never auto-kills every 45-second operation.** It preserves context to avoid harming valid work or confusing `mongos` with shard IDs.

## 25. Quick Investigation Decision Flow

A diagnostic workflow can be modeled as:

~~~text
Application latency / DB alert
              |
              v
Do we know the affected query and time?
        /                   \
      Yes                    No
       |                      |
       v                      v
Is it still active?     Use APM/profiler/logs
    /        \                 |
  Yes         No               |
   |           |               |
   v           +---------------+
Read $currentOp
   |
   v
Collect host + opid + appName + ns + command tag
   |
   v
Classify operation
   |
   +--> Waiting for lock? -> Find blocker/transaction
   |
   +--> Query plan?       -> Explain/index/query rewrite
   |
   +--> getMore/stream?   -> Check cursor/await behavior
   |
   +--> Index build?      -> Change plan/progress/DBA
   |
   +--> Write/transaction?-> Check commit/abort/idempotency
   |
   +--> Sharded query?    -> Correlate mongos/shards
   |
   +--> Pool/network?     -> Application tracing
   |
   v
Is it client-initiated and causing significant harm?
           /                  \
          No                  Yes
          |                    |
          v                    v
Continue diagnosis      Cancel from application if possible
                               |
                               v
                     Confirm owner and approval
                               |
                               v
                     Recheck host/opid/type
                               |
                               v
                    Consider one controlled killOp
                               |
                               v
                       Verify and follow up
~~~

This diagram underscores that **observation and classification are mandatory**; `killOp` is only **a conditional branch** in the runbook.

## 26. Operator Action Checklist

### 26.1. Before Opening `currentOp`

- [ ] Know the exact cluster and environment.
- [ ] Know your current `inprog` observation privileges.
- [ ] Have the incident timestamp and symptom description.
- [ ] Know which application, endpoint, or namespace is impacted.
- [ ] Have baseline CPU, I/O, p95/p99, queue, and replication metrics.

### 26.2. When Reading an Operation

- [ ] Confirm **host/shard/`opid`**.
- [ ] Confirm **`appName`/client**.
- [ ] Check **`active`** and **`secs_running`**.
- [ ] Check **`op`/`type`/`ns`**.
- [ ] Distinguish **`waitingForLock`** from active execution.
- [ ] Check **`planSummary`** when present.
- [ ] Inspect **`command`/`comment`** mindful of sensitive data.
- [ ] Identify `getMore`, index builds, migrations, and internal tasks.
- [ ] Check `transaction`/`lsid` where relevant.
- [ ] Correlate with profiler, APM, `explain`, and metrics.

### 26.3. Before Considering `killOp`

- [ ] Operation is **client-initiated**, never an internal MongoDB task.
- [ ] Impact on end users and data integrity has been evaluated.
- [ ] Less disruptive mitigations were tried where feasible.
- [ ] Write, transaction, and unknown-outcome risks were assessed.
- [ ] `mongos` vs. shard-side semantics were verified if sharded.
- [ ] Approved by owner, on-call, or DBA.
- [ ] Holds `killop` privilege or valid own-operation scope.
- [ ] `opid`, host, and command were **re-verified immediately before acting**.
- [ ] Post-kill verification and rollback/reconciliation plans are ready.

### 26.4. After Termination

- [ ] Monitored `killPending` and operation termination state.
- [ ] Checked client errors, timeouts, and retries.
- [ ] Verified whether resources and SLOs recovered.
- [ ] Reconciled write outcomes if applicable.
- [ ] Recorded the incident timeline.
- [ ] Assigned follow-up fixes for indexes, queries, deadlines, batching, or retries.

## 27. Official References

Documentation varies by MongoDB version and deployment. Key sources:

- [MongoDB Manual — `$currentOp` aggregation stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/currentOp/)
- [MongoDB Manual — `db.currentOp()`](https://www.mongodb.com/docs/manual/reference/method/db.currentOp/)
- [MongoDB Manual — `currentOp` command](https://www.mongodb.com/docs/manual/reference/command/currentOp/)
- [MongoDB Manual — `db.killOp()`](https://www.mongodb.com/docs/manual/reference/method/db.killOp/)
- [MongoDB Manual — Terminate Running Operations](https://www.mongodb.com/docs/manual/tutorial/terminate-running-operations/)
- [MongoDB Manual — Monitor Slow Queries](https://www.mongodb.com/docs/manual/tutorial/monitor-slow-queries/)
- [MongoDB Manual — Privilege Actions: `inprog` and `killop`](https://www.mongodb.com/docs/manual/reference/privilege-actions/)
- [MongoDB Manual — Database Profiler](https://www.mongodb.com/docs/manual/tutorial/manage-the-database-profiler/)
- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Manual — Query Optimization](https://www.mongodb.com/docs/manual/core/query-optimization/)

**Version note:** On MongoDB 6.2+, the **`currentOp` command is deprecated** in favor of the **`$currentOp` aggregation stage**. Metric displays, `targetAllNodes`, queue details, field availability, and sharded behaviors vary across releases. Always match documentation to your exact **server version, `mongosh`, driver, and Atlas tier**.

## 28. Summary

Frequently confused concepts to keep clear:

| Concept | Key meaning |
|---|---|
| `$currentOp` | Snapshot of active or idle operations/sessions depending on options |
| `db.currentOp()` | `mongosh` helper for rapid observation |
| `opid` | Operation ID scoped to the relevant host/router/shard |
| `secs_running` | Elapsed wall-clock time of the operation, not CPU time |
| `active=true` | Operation is active, though it may still be waiting |
| `waitingForLock=true` | Operation is waiting for a lock; locate the blocker |
| `planSummary=COLLSCAN` | Collection scan indicator; evaluate query, data, and indexes |
| `planSummary=IXSCAN` | Index scan; does not guarantee whole-query efficiency |
| `getMore` | Cursor batch fetch; may intentionally await events |
| `idleSession`/`transaction` | Session/transaction holding resources despite no active query |
| `killPending` | Interrupt requested; awaiting a safe interrupt point |
| `db.killOp(opid)` | Requests interrupting a **client-initiated** operation at an interrupt point |
| `maxTimeMS` | Server-side time limit set before execution |
| `inprog` | Privilege to observe operations within scope |
| `killop` | Privilege to terminate operations within scope |
| `localOps=true` via `mongos` | Observes router-local operations |
| `localOps=false` via `mongos` | Observes operations on shards |

**Ten core principles:**

1. **Long duration does not automatically equal an error.** Evaluate by SLO, workload class, progress, and impact.
2. **Prefer `$currentOp`** for live inspection, filtering and projecting only needed fields.
3. **`currentOp` is a snapshot**; it never replaces the profiler, logs, `explain`, and application tracing.
4. **Read `opid` alongside host/shard, `appName`, namespace, command, and wait state** before drawing conclusions.
5. **`COLLSCAN`/`IXSCAN` are merely plan indicators**; inspect `executionStats` and real data before indexing or rewriting queries.
6. **Lock waits, idle transactions, and `getMore` have distinct causes**; `killOp` cannot fix all of them.
7. **Consider `killOp` only for client-initiated operations** after verifying target, privileges, impact, owner, and alternatives.
8. **`killOp` does not guarantee full write rollback** or instant stoppage; client retries can spawn fresh operations.
9. **In sharded clusters, `mongos` kills reads differently from writes**; read cancellations can propagate, whereas `mongos` `killOp` does not propagate to shards for writes.
10. **Prevention beats intervention:** use `maxTimeMS`, proper indexes, pagination, batch checkpoints, `appName`/`comment`, backpressure, and bounded retry policies.

A MongoDB operator's goal is not making the `currentOp` list empty—it is **accurately identifying problematic operations and choosing the lowest-risk remedy**. When observation provides full context and `killOp` follows a strict runbook, teams resolve incidents quickly while minimizing unintended data and service disruption.
