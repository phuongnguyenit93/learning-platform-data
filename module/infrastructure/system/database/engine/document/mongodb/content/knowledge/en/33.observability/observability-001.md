# Metrics to Monitor: Latency, Traffic, Errors, and Connections

A system using **MongoDB** can operate normally for months, then suddenly exhibit slow APIs, an increasing number of failed requests, timed-out workers, or lost connections to the primary. When that happens, the key question is not just "Is MongoDB still running?" but also:

- How long do users have to wait for a request to complete?
- How many operations per second is the database receiving and processing?
- How many operations are failing, which component is causing the errors, and is the error rate increasing or decreasing?
- Are the numbers of open connections, active connections, and connections waiting in the connection pool normal?
- Which resource or topology component is causing that fluctuation?
- Can we detect issues **before** the system is overloaded and have evidence to act on?

These are questions of **observability** — the ability to understand a system from metrics, logs, and traces — rather than just looking at CPU or running `db.collection.findOne()`.

In system monitoring models, **latency**, **traffic**, **errors**, and **saturation** are often called the *four golden signals*. For a MongoDB application, **connections** is an especially important metric because it reflects load sources, connection pooling, server reachability, and bottlenecks.

This lesson, **"Metrics to Monitor: Latency, Traffic, Errors, and Connections"** in the **Observability** chapter, explains how to define these four signal groups, collect metrics from the application, driver, and MongoDB, read counters properly, design dashboards and alerts, identify incident root causes, and practice safe measurements.

> **First principle:** A metric is only meaningful when you know **which layer it measures, its unit, the sampling interval, which node/tenant/operation it applies to, and whether it includes waiting or retries**. Do not treat a figure like "10 ms latency" as the entire time the user waits without identifying the start and end points of the measurement.

## 1. The Big Picture of a MongoDB Request

An HTTP request from a user can pass through multiple components:

```text
User
    │
    ▼
Load balancer / API Gateway
    │
    ▼
Application server
    │
    ├── AuthN/AuthZ, validation
    ├── Business logic
    │
    ▼
MongoDB Driver
    │
    ├── Server selection
    ├── Connection pool checkout
    ├── BSON serialization
    ├── Network / TLS
    │
    ▼
mongos or mongod
    │
    ├── Query planning / index access
    ├── WiredTiger cache / disk I/O
    ├── Locks / tickets / scheduling
    ├── Replication / write concern
    │
    ▼
MongoDB Driver
    │
    ▼
Application transformation
    │
    ▼
HTTP response
```

For example, an `/orders/search` API responds in **850 ms**, while MongoDB processes the corresponding query in **35 ms**. The remaining time may come from:

- Waiting for an available connection in the pool;
- Waiting for server selection after a failover;
- Multiple small queries running sequentially;
- Network round trips;
- BSON decoding;
- Mapping/authorization logic;
- Calling other services;
- Retries or timeouts;
- Saturated application thread pool.

Conversely, if the API takes 850 ms and the MongoDB operation takes 800 ms, you need to inspect the query plan, indexes, CPU, disk, locks, and concurrent operations.

**Metrics at each layer must be correlated, not substituted for one another.**

### 1.1. Three Minimum Observation Layers

| Layer | What can you see? | Tools |
|---|---|---|
| Application/API | User wait time, HTTP errors, business traffic | Metrics, APM, OpenTelemetry, structured logs |
| MongoDB Driver | Command timing, failures, pool checkout, server selection, retries | Driver listeners, tracing, pool metrics |
| MongoDB Server/Atlas | Operations, network traffic, connections, cache, replication, query activity | Atlas Monitoring, `serverStatus`, `mongostat`, profiler, logs |

A dashboard showing only server metrics cannot by itself explain every HTTP error. A dashboard showing only HTTP cannot pinpoint a root cause inside MongoDB.

## 2. Define Latency Properly Before Measuring

**Latency** is the time from a start point to an end point of an activity.

In a MongoDB application, there are several different definitions:

- **End-to-end request latency:** from when the API receives the request until the response completes.
- **Database logical operation latency:** the total time the application needs to complete a database task, which may include multiple commands and retries.
- **Driver command elapsed time:** the time the driver measures for a command sent to/interacting with the server under its monitoring mechanism.
- **Server operation latency:** the time to process an operation inside the MongoDB server according to server statistics.
- **Connection checkout wait:** the time spent waiting to acquire a connection from the pool.
- **Server-selection wait:** the time the driver takes to find a server matching the read preference/topology.
- **Replication/write concern wait:** the time needed to satisfy the write acknowledgment requirement.
- **Network latency:** data transmission time and round trips.

Do not group all of them under a single metric named `mongodb_latency_ms` if they are measured differently.

### 2.1. One Request Can Generate Multiple MongoDB Commands

For example:

```text
HTTP GET /orders
    │
    ├── Query orders           40 ms
    ├── Query customer         20 ms
    ├── Query permissions      15 ms
    └── Business processing    25 ms
```

If operations run sequentially with no other waits, the minimum latency is already around 100 ms. The server may report individual reads as much faster than the overall API.

Therefore, when tracking performance, you must distinguish between **latency per command** and **latency per business request**.

### 2.2. Units

| Quantity | Recommended display unit |
|---|---|
| HTTP latency | ms or s |
| Driver command duration | ms |
| MongoDB `opLatencies.*.latency` | Cumulative total microseconds by operation group |
| Connection checkout wait | ms |
| Replication lag | s |
| Network bytes/sec | B/s, KiB/s, MiB/s |
| Throughput | requests/s or operations/s |
| Error rate | errors/s or % |
| Connection counts | Number of connections, not requests/s |

Do not divide microseconds to convert to milliseconds and forget the factor of **1,000**. A unit conversion mistake can lead to claiming "MongoDB is a thousand times slower" even when the system is healthy.

## 3. Mean Differs from p95 and p99

An average metric can hide a bad experience for a subset of users.

For example, given 100 requests:

```text
95 requests:  50 ms
4 requests:  500 ms
1 request:   5000 ms
```

Mean:

\[
\text{mean} = \frac{95 \times 50+4 \times 500+5000}{100}=117.5\text{ ms}
\]

Meanwhile, the slowest request took **5 seconds**.

Common percentiles:

- **p50:** roughly 50% of observations do not exceed this value.
- **p95:** roughly 95% of observations do not exceed this value.
- **p99:** roughly 99% of observations do not exceed this value.
- **max:** the largest duration within the measurement window.

### 3.1. Why Look at p95/p99?

For an API serving millions of requests per day, 1% slow requests still affects thousands of users. A low mean does not prove good tail latency.

A latency dashboard should include at a minimum:

```text
api_request_latency_ms
  p50
  p95
  p99

mongodb_command_latency_ms
  p50
  p95
  p99

mongodb_pool_checkout_wait_ms
  p95
  p99
```

Do not rely on a single percentile alone. p99 is very sensitive to sample size and noise when traffic volume is low.

### 3.2. Percentiles Must Be Computed from Distributions, Not Averages

Wrong:

```text
Server A p95 = 100 ms
Server B p95 = 500 ms
Global p95 = (100+500)/2 = 300 ms
```

The global p95 is **not the average of per-server p95s**. You must aggregate histograms or sample sets using statistically valid methods weighted by request volume.

If the system exports histograms, use the proper aggregation/histogram quantile functions provided by your telemetry backend; never average per-node p95 values.

### 3.3. Histogram Buckets and Bounds

A histogram might use buckets:

```text
<= 10 ms
<= 25 ms
<= 50 ms
<= 100 ms
<= 250 ms
<= 500 ms
<= 1000 ms
> 1000 ms
```

Histograms support estimating percentiles and the percentage of requests meeting an SLO. However, overly coarse buckets introduce large estimation errors. Choose buckets aligned with your SLO rather than assuming every system needs the same boundaries.

## 4. MongoDB `opLatencies`: Understanding Server Counters Correctly

MongoDB provides operation latency statistics in `serverStatus()`.

Example of reading several fields:

```javascript
const s = db.serverStatus();

printjson({
  serverTime: s.localTime,
  uptimeSeconds: s.uptime,
  opLatencies: s.opLatencies
});
```

In supported versions, `opLatencies` contains groups such as:

```javascript
{
  reads: {
    latency: NumberLong("..."),
    ops: NumberLong("...")
  },
  writes: {
    latency: NumberLong("..."),
    ops: NumberLong("...")
  },
  commands: {
    latency: NumberLong("..."),
    ops: NumberLong("...")
  }
}
```

**This is a simplified representation**; actual output may contain additional fields/histograms depending on the version.

- `ops`: cumulative number of operations in the group.
- `latency`: cumulative total time in microseconds in the group.
- `reads`/`writes`/`commands`: operation groups as classified by MongoDB, not synonymous with three business endpoints.

### 4.1. Computing the Mean from Two Samples

Suppose at \(t_1\):

```text
reads.ops = 1.000.000
reads.latency = 40.000.000 μs
```

At \(t_2\), 60 seconds later:

```text
reads.ops = 1.006.000
reads.latency = 41.500.000 μs
```

Then:

\[
\Delta ops=6000
\]

\[
\Delta latency=1.500.000\ \mu s
\]

\[
\text{mean}=\frac{1.500.000}{6000}=250\ \mu s=0.25\text{ ms}
\]

\[
\text{read throughput}=\frac{6000}{60}=100\text{ ops/s}
\]

These numbers are only examples. What matters is **taking deltas over the same window**, rather than dividing cumulative totals since server startup and calling that the latency over the last minute.

### 4.2. `opLatencies` Is Not Application p95

Even when the read mean is 0.25 ms:

- You cannot derive the HTTP API's p95;
- You cannot derive driver pool wait;
- You cannot derive percentiles from `ops` and total `latency` alone;
- You cannot isolate operations belonging to a specific endpoint without labels/correlation;
- It does not tell you network RTT.

For percentiles, use histograms, tracing, driver instrumentation, or appropriate Atlas metrics.

### 4.3. Counter Resets on Restart

`serverStatus()` has many counters that are **cumulative since process startup**. When `mongod` restarts, counters may reset to smaller values.

If you compute:

```text
delta = counter_now - counter_previous
```

and the delta is negative, treat it as a **counter reset/series change**, do not record negative throughput.

You must also avoid merging metrics from two different nodes into a single time series. A primary stepdown can cause an exporter to switch from node A to node B with different counters.

## 5. How to Safely Sample Latency with `mongosh`

Example reading `serverStatus()` twice, ten seconds apart:

```javascript
const first = db.serverStatus();
sleep(10000);
const second = db.serverStatus();

const seconds =
  (second.localTime.getTime() - first.localTime.getTime()) / 1000;

function readRate(groupName) {
  const before = first.opLatencies[groupName];
  const after = second.opLatencies[groupName];

  const opsDelta = Number(after.ops) - Number(before.ops);
  const latencyDeltaUs =
    Number(after.latency) - Number(before.latency);

  if (seconds <= 0 || opsDelta < 0 || latencyDeltaUs < 0) {
    return { valid: false, reason: "invalid-window-or-counter-reset" };
  }

  return {
    valid: true,
    operationsPerSecond: opsDelta / seconds,
    meanLatencyMs:
      opsDelta > 0 ? latencyDeltaUs / opsDelta / 1000 : null
  };
}

printjson({
  windowSeconds: seconds,
  reads: readRate("reads"),
  writes: readRate("writes"),
  commands: readRate("commands")
});
```

**The purpose of this example is to illustrate delta counters**, not to serve as a production monitoring exporter. For very large counters, coercing BSON `Long` to JavaScript `Number` can lose precision; a real exporter should use proper numeric handling and telemetry libraries.

`db.serverStatus()` may require the `serverStatus`/`clusterMonitor` privilege. The command only reads metrics, but the full output contains infrastructure metadata; do not post raw output on a public page.

### 5.1. Do Not Sample Too Aggressively

Polling `serverStatus` every few milliseconds on every node does not guarantee better observability. It increases overhead, noise, and storage. Choose an interval suited to your SLO and monitoring system—typically a few seconds to tens of seconds—combined with event traces when detail is needed.

### 5.2. Measurement Windows Must Be Stated Explicitly

A chart should clearly label:

```text
read_ops_per_second over 60s
read_mean_latency_ms over 60s
api_p95_latency_ms over 5m
```

Without knowing the window, comparing two systems can be misleading.

## 6. Traffic: Accurately Measuring "How Much Work Is Being Handled"

**Traffic** can be described at multiple levels:

- HTTP requests/second;
- Business operations/second: checkout, search, purchase;
- MongoDB commands/second;
- Reads/writes/second on `mongod`;
- Query/document throughput;
- Network bytes in/out;
- Change stream events/second;
- Search queries/second.

These numbers are **not equivalent**.

For example:

```text
100 HTTP requests/s
   │
   ├── each request issues 3 MongoDB commands
   └── some have retries
             │
             ▼
Can be >300 MongoDB commands/s
```

Conversely, a single MongoDB command can return thousands of documents. Do not treat documents returned as QPS.

### 6.1. `opcounters`

Use:

```javascript
const s = db.serverStatus();

printjson({
  opcounters: s.opcounters
});
```

The output typically contains categories such as:

```text
insert
query
update
delete
getmore
command
```

These are counters based on how MongoDB classifies operations. Across different versions and protocols, not every logical operation called by an application maps one-to-one with the counter group a newcomer might guess from the name.

### 6.2. Distinguishing `opcounters` and `opLatencies`

`opcounters` helps track **operation types and counts**; `opLatencies` helps track total processing time and operation counts across latency categories.

Do not compare `opcounters.query` directly with `opLatencies.reads.ops` and assume they must be equal. Their definitions and classifications do not necessarily match.

### 6.3. Track Replication Traffic Separately

When viewing replica set node metrics, distinguish between:

- Client-submitted operations;
- Replication apply operations;
- Internal commands;
- Inter-member network traffic.

`serverStatus()` includes replication-related statistics depending on the version, such as `opcountersRepl` in supported outputs. Summing all counters across all nodes and treating the total as user requests easily causes **double counting**.

An application write can appear on the primary and be replicated to secondaries, but those are not multiple independent business writes.

## 7. Network Throughput: `bytesIn`, `bytesOut`, `numRequests`

A section of `serverStatus()`:

```javascript
const s = db.serverStatus();

printjson({
  network: {
    bytesIn: s.network && s.network.bytesIn,
    bytesOut: s.network && s.network.bytesOut,
    numRequests: s.network && s.network.numRequests
  }
});
```

Common fields:

- `bytesIn`: bytes received by the server according to MongoDB's accounting.
- `bytesOut`: bytes sent by the server.
- `numRequests`: number of requests recorded by the server.
- Other network fields may exist depending on the version.

These are typically **cumulative counters**, not ready-to-read bytes/s rates.

### 7.1. Computing bytes/s

Suppose:

```text
T1 bytesOut = 1.000.000.000
T2 bytesOut = 1.120.000.000
Interval = 60 seconds
```

\[
\text{outbound throughput}=
\frac{120.000.000}{60}=
2.000.000\text{ bytes/s}
\]

You can convert to MiB/s if desired on the dashboard. Be consistent between **MB (10^6 bytes)** and **MiB (2^20 bytes)**.

### 7.2. Why Does Network Throughput Increase?

Common causes:

- A search endpoint returning many documents;
- An API dropping projection and transferring large fields/arrays;
- An aggregation outputting a large dataset;
- A backup/export job;
- A change stream consumer;
- Client retries;
- Shard scatter-gather;
- Internal replication;
- Query result batching/getMore.

Do not jump to "we are under attack" just because `bytesOut` increased. Correlate timing, connection sources, app traffic, authentication, and business releases.

### 7.3. Network Traffic Is Not HTTP Request Count

Server `network.numRequests` counts requests reaching MongoDB under server semantics, not HTTP requests reaching the application. To calculate the API request error rate, you must use **HTTP counters** from the application/gateway.

## 8. Measuring Error Rate: Define "Error" Before Alerting

No single MongoDB error metric fits every business use case.

Categories to separate:

1. **Application errors:** HTTP 5xx, unexpected business errors.
2. **Driver errors:** server selection timeout, pool checkout timeout, network/socket errors.
3. **MongoDB command errors:** duplicate key, unauthorized, validation error, interrupted operation, exceeded time limit.
4. **Write concern failures:** the write executed but did not satisfy the desired acknowledgment level.
5. **Replication/topology events:** primary election, connectivity loss, replication lag.
6. **Search/index errors:** index not ready, query timeout, stale results.
7. **Business rejections:** invalid input, expected conflict, 404 "order not found".

### 8.1. Do Not Treat Every 4xx as a Broken System

A user entering an invalid coupon code is an expected business rejection. If the API returns HTTP 400 per contract, it may be an error from the user's perspective, but it is **not a database availability failure**.

Metrics should be broken down by group:

```text
http_requests_total{status_class="2xx"}
http_requests_total{status_class="4xx"}
http_requests_total{status_class="5xx"}

mongodb_command_failures_total{category="timeout"}
mongodb_command_failures_total{category="auth"}
mongodb_command_failures_total{category="duplicate_key"}
mongodb_command_failures_total{category="network"}
```

These metric names and labels are illustrative conventions. Never use raw exception text as a label, as it causes high cardinality and leaks data.

### 8.2. Error Rate Formula

If in five minutes there are 50,000 requests and 500 failed requests in the defined class:

\[
\text{error rate}=\frac{500}{50.000}=1\%
\]

Do not divide database errors by total HTTP requests if a single request can execute multiple MongoDB commands; the denominator must match **the event unit being measured**.

### 8.3. Both Error Count and Error Percentage Matter

A service with 10 requests in five minutes and 1 error has a **10%** error rate, but a tiny sample. A service with 100,000 requests and 1,000 errors has a **1%** error rate, but a large impact.

A good alert can combine:

- Error rate;
- Minimum error count;
- Sustained duration;
- Error budget burn;
- Business criticality.

### 8.4. Retries Can Mask Errors

The driver may automatically retry certain operations according to configuration and MongoDB semantics. When that happens:

```text
Command attempt #1: network error
Command attempt #2: successful
HTTP request: 200 OK
```

Users see no error, yet database command retries rise. If you only measure HTTP error rate, you may miss an early warning sign before an outage.

You should track metrics such as:

```text
mongodb_command_attempts
mongodb_command_failures
mongodb_retryable_failures
api_requests_failed
```

Do not assume "command failed" always means the final business operation failed. For write concern or network errors, final state may require reconciliation to avoid duplicate writes.

## 9. Error Codes and Categories to Distinguish

| Category | Symptom | What to check |
|---|---|---|
| Duplicate key | `E11000` / code 11000 | Unique index, retry/business conflict |
| Unauthorized | Authentication/authorization failure | Credentials, role, authSource, audit |
| Time limit exceeded | Query/operation hit time limit | Query plan, maxTimeMS, resources |
| Server selection timeout | Driver could not find a suitable server | DNS, TLS, topology, election |
| Connection checkout timeout | Could not acquire connection from pool | Pool sizing, wait queue, slow ops |
| Network/socket error | Connection reset or dropped | Network path, LB, TLS, restarts |
| WriteConcernError | Did not reach required write concern acknowledgment | Replication health, write concern |
| TransientTransactionError | Transaction eligible for retry | Retry policy, topology |
| Cache/disk pressure | Latency rises, possibly hitting resource limits | WiredTiger, disk metrics |
| Cursor timeout | Cursor idle/closed | Cursor lifecycle, getMore, sessions |

Each category has a **different retry strategy**. Never write a `catch(Exception) -> retry forever` loop; that can turn a minor glitch into a retry storm.

### 9.1. Should Duplicate Key Always Trigger an Alert?

No. If a registration endpoint reports that a username already exists, a duplicate key may be an expected business conflict. However, a sudden spike in `E11000` errors on an import batch that should be idempotent may indicate a bug.

Classify by **operation and expectation** before configuring alerts.

### 9.2. What Level of Observability for Failed Commands?

Application logs hold stack traces and correlation IDs; driver listeners capture command name, elapsed time, and failure; server logs capture server-side events. Tie them together using a trace ID when possible without forcing MongoDB to log entire request bodies containing PII.

## 10. Connections: What to Count and Why It Matters

MongoDB uses TCP connections between clients/drivers and servers. Standard MongoDB drivers maintain **connection pools** to reuse connections instead of opening a new TCP/TLS connection per request.

States that are easy to confuse:

- **Open/current connections:** sockets/connections currently held open by the server.
- **Active connections:** connections currently executing operations under the specific metric's semantics.
- **Available capacity:** number of additional connections the server can still accept up to its limit.
- **Connections created:** total connections created over an interval or since process startup.
- **Pool size:** number of connections managed by each driver pool.
- **Checked-out connections:** connections clients have borrowed from the pool for use.
- **Pool wait queue:** requests waiting for the pool to grant a connection.
- **Pool checkout wait:** time spent waiting to acquire a connection.
- **Server selection time:** time the driver spends choosing a server capable of serving the operation.

**Server connections are not the same as a single process's driver pool connections.** A MongoDB server accepts connections from many application instances, admin tools, monitoring agents, and replication-related components.

## 11. `serverStatus().connections`

Example:

```javascript
const s = db.serverStatus();

printjson({
  connections: s.connections
});
```

Common fields:

```javascript
{
  current: NumberInt(150),
  available: NumberInt(10000),
  totalCreated: NumberLong("125000"),
  active: NumberInt(85)
}
```

Output is an example only; MongoDB versions may include additional fields.

- `current`: connections currently open according to the server.
- `available`: remaining capacity to accept new connections per server limit.
- `totalCreated`: cumulative number of connections created.
- `active`: active connections per server semantics.
- Details such as `threaded` may appear in other versions.

### 11.1. Is High `current` Always Bad?

No. A system with many app pods, each maintaining its own connection pool, can legitimately hold hundreds of connections even at moderate QPS.

More concerning signs are:

- `current` growing disproportionately relative to app instance count;
- `totalCreated` rising very rapidly;
- `available` dropping close to the limit;
- Checkout wait time increasing;
- Pool timeouts increasing;
- Creating a new `MongoClient` on every HTTP request;
- Connection counts spiking after deployments/failovers;
- Connection counts failing to drop when instances are scaled down.

A raw number like `current=500` does not by itself prove a connection leak.

### 11.2. `totalCreated` Is a Counter, Not Currently Open Connections

If:

```text
totalCreated = 500.000
current = 250
```

that does not mean the server currently has 500,000 open connections. `totalCreated` is cumulative. To measure churn:

\[
\text{new connections/s}=
\frac{\Delta totalCreated}{\Delta t}
\]

During rolling deployments or autoscaling, this rate may spike temporarily. Correlate it with the pod count timeline and retries.

### 11.3. Connection Leaks and Churn Are Different

- **Leak/pool growth:** connections are held longer than expected, and the count climbs steadily.
- **Churn:** connections are continuously opened and closed; `current` may not be very high, but the `totalCreated` rate is very high.

Churn adds TLS handshake, authentication, and CPU overhead; leaks exhaust connection capacity. Their mitigations differ.

## 12. Driver Connection Pools: Where Latency Can Hide

Suppose you have:

```text
10 application instances
Each instance maintains a pool of up to 50 connections/server
```

Configuration-wise, the application can open up to hundreds of connections per server, plus monitoring and background connections. Actual numbers depend on the driver, topology, workload, and pool lifecycle; **do not multiply instance count by `maxPoolSize` and assume that many sockets are always open**.

### 12.1. `maxPoolSize` and `minPoolSize`

Common options in MongoDB drivers:

- `maxPoolSize`: maximum pool connections per server.
- `minPoolSize`: minimum connections the pool tries to keep open.
- `maxConnecting`: limit on concurrent connection establishments in the pool, if supported by the driver/version.
- `maxIdleTimeMS`: controls how long an idle pooled connection remains open.
- Pool checkout timeout or max wait time under the respective API/driver option name.
- Server selection timeout, connect timeout, and socket timeout each have distinct semantics.

There is no universal optimal `maxPoolSize=100` for every application. A pool that is too small creates queuing; a pool that is too large can cause connection storms, resource contention, or database overload.

### 12.2. Pool Checkout Wait Differs from Server Query Latency

Timeline:

```text
API begins
    │
    ├── Wait for pool connection      400 ms
    ├── MongoDB command                15 ms
    ├── Decode / business logic        25 ms
    └── Return response
```

If you only inspect `opLatencies` on the server, MongoDB looks fast while API p99 is very slow. There is no contradiction here; **pool wait occurs before the command is processed**.

### 12.3. Creating a `MongoClient` per Request Is an Anti-Pattern

Avoid:

```java
void handleRequest() {
    try (var client = MongoClients.create(System.getenv("MONGODB_URI"))) {
        // One request -> one new MongoClient/pool.
    }
}
```

In most web applications, you should create a **shared `MongoClient` scoped to the application lifecycle**, because `MongoClient` manages connection pools and background monitoring.

Continuously opening and closing clients creates network/TLS/authentication overhead and connection churn.

### 12.4. Where Should You Monitor the Pool?

Driver-specific monitoring APIs typically emit events such as:

```text
ConnectionPoolCreated
ConnectionCreated
ConnectionCheckedOut
ConnectionCheckedIn
ConnectionCheckOutFailed
ConnectionClosed
```

Exact class/event names depend on the driver. A useful set of metrics includes:

```text
pool_in_use
pool_idle
pool_waiting
pool_checkout_duration
pool_checkout_failures_total
pool_created_total
pool_closed_total
```

Do not treat `connections.current` on the server as sufficient to infer connection wait time inside an individual Java service.

## 13. Putting the Four Signal Groups Side by Side

A symptom-oriented reference table:

| Latency | Traffic | Errors | Connections | Possible clue |
|---|---|---|---|---|
| Rising | Rising | Not yet rising | Active rising | Load increasing; check queries/resources |
| Rising | Unchanged | Timeouts rising | Wait queue rising | Pool saturated or database slow |
| Sudden spike | Dropping | Server selection errors | Churn rising | Failover/network/TLS |
| Stable | Rising | Stable | Current rising proportionally | Scaling working normally |
| Stable | Stable | Auth errors rising | New connections rising | Credentials/rotation/anomaly |
| Rising | Stable | Few errors | Current stable | Query plan/I/O/cache/locks |
| Spiking periodically | Stable | Retries rising | Created rate rising | Connection storms/restarts |
| Low | Near 0 | Near 0 | 0 or idle remaining | Traffic dropped, or app lost connectivity |

This table lists **diagnostic hypotheses**, not deterministic rules for root cause. Always cross-check logs, traces, topology, and recent changes.

## 14. Saturation: Essential Context

The four groups—latency, traffic, errors, and connections—reflect symptoms. To understand causes, you must look at **saturation**—when a resource approaches or exceeds its capacity to serve.

Common saturation sources in MongoDB:

- CPU;
- WiredTiger cache;
- RAM pressure/swapping;
- Disk IOPS/throughput/latency;
- Disk space;
- Read/write concurrency and scheduling;
- Connection limits;
- Driver pool wait queues;
- Network bandwidth;
- Replication lag;
- Query planner/index inefficiency;
- Search nodes if using MongoDB Search/Vector Search.

### 14.1. High CPU Alone Is Insufficient for Diagnosis

High CPU when traffic rises can be normal. However, high CPU with unchanged QPS, rising p99, and a new query plan using `COLLSCAN` is a very different signal.

Compare:

```text
CPU utilization
QPS / reads / writes
p95/p99 latency
Docs examined / returned
Index usage
```

### 14.2. Disk I/O and Latency

If disk read latency rises, WiredTiger suffers frequent cache misses, or workloads scan large numbers of documents, MongoDB queries can slow down even before CPU reaches 100%.

Metrics to inspect:

- Disk read/write IOPS;
- Throughput;
- Queue depth/await at the OS/cloud layer;
- Available disk capacity;
- WiredTiger cache read/write activity;
- Pages read into cache;
- Replication/checkpoint/backup I/O.

Do not assume "more RAM always fixes every slow query." An unindexed query can still be prohibitively expensive.

## 15. WiredTiger Cache and Diagnostics

With the WiredTiger storage engine, the cache is a critical component affecting read/write latency.

Example of inspecting relevant metrics:

```javascript
const s = db.serverStatus();

if (s.wiredTiger && s.wiredTiger.cache) {
  printjson({
    cache: s.wiredTiger.cache
  });
}
```

The output contains many counters, with descriptive names such as:

```text
maximum bytes configured
bytes currently in the cache
bytes read into cache
bytes written from cache
tracked dirty bytes in the cache
```

Field names and contents may vary by MongoDB version. Do not hardcode every WiredTiger metric from a single version into scripts meant for all versions.

### 15.1. Cache Utilization

An intuitive calculation:

\[
\text{cache usage ratio} =
\frac{\text{bytes currently in cache}}
     {\text{maximum bytes configured}}
\]

However, **a nearly full cache does not automatically mean an error**: the cache is designed to use memory to improve efficiency. Also inspect eviction pressure, dirty bytes, disk I/O, query latency, and CPU.

### 15.2. Write Latency and Dirty Cache

If dirty data accumulates, eviction/checkpoints fall behind, or disk write latency increases, writes can slow down. Correlate:

```text
write ops/s
write latency
dirty cache metrics
disk write latency
checkpoint activity
replication lag
```

Do not blindly lower write concern or disable journaling to "fix" latency; those changes introduce data durability risks.

## 16. Poor Query Performance: Operation Count Is Not Everything

Two workloads with the same 100 reads/s:

```text
Workload A:
  100 findOne by _id

Workload B:
  100 aggregations scanning one million documents each
```

The operations/s rate is identical, yet the CPU and I/O cost is completely different.

To analyze this, check:

- Docs examined;
- Keys examined;
- Docs returned;
- Query plan (`IXSCAN`, `COLLSCAN`, or corresponding stages);
- Query shape;
- Slow query logs;
- Query Profiler/Atlas Query Insights if available;
- Number of result batches/getMore;
- Sort memory/disk spill.

### 16.1. `explain("executionStats")`

On a collection with appropriate indexes and permissions:

```javascript
db.getSiblingDB("shop").orders.find({
  tenantId: "T-01",
  status: "PAID"
})
.limit(20)
.explain("executionStats");
```

Typically important fields:

```text
winningPlan
nReturned
totalKeysExamined
totalDocsExamined
executionTimeMillis
```

Depending on the MongoDB version and query engine, stage names and structures may differ.

### 16.2. Query Targeting Ratio

A relative metric:

\[
\text{documents examined per returned} =
\frac{\text{totalDocsExamined}}{\max(1,\text{nReturned})}
\]

If a query returns 10 documents after examining 500,000, inspect the index and query shape. However, a high ratio is not always wrong: a query searching for "no matching records" may legitimately inspect multiple candidates depending on design.

Evaluate the ratio alongside latency, traffic, and use case; do not apply a rigid threshold to every query.

### 16.3. Explain Is Not Production Latency

`explain("executionStats")` analyzes the execution of one specific query. It does not fully simulate:

- Connection pool contention;
- Concurrent traffic;
- End-to-end API overhead;
- Client network RTT;
- Application retries;
- Interference from all concurrent workloads.

Do not take `executionTimeMillis` from a single `explain` run and use it as the API SLO.

## 17. Logs, Slow Operations, and the Profiler

When latency rises, metrics show *when* and *how much*, while logs and the profiler show *which queries and what happened*.

Common sources:

- MongoDB diagnostic logs;
- Slow operation messages;
- Atlas Query Profiler/Performance Advisor depending on tier;
- Database profiler (`system.profile`) when enabled;
- Application structured logs;
- Driver command monitoring;
- Distributed tracing.

### 17.1. Slow Operation Threshold

MongoDB provides `slowms` configuration and logging/profiling mechanisms. However, **changing the threshold is an operational change**, not a read-only command.

Do not enable full profiling for all operations in production without assessing overhead and retention. Profile data can contain query shapes, field values, or sensitive metadata.

### 17.2. Reading Profiler Status

In `mongosh`, if authorized:

```javascript
db.getSiblingDB("shop").getProfilingStatus();
```

If the profiler is enabled and the user has privileges, you can perform a bounded read:

```javascript
db.getSiblingDB("shop").system.profile.find(
  {},
  {
    ts: 1,
    millis: 1,
    op: 1,
    ns: 1
  }
)
.sort({ ts: -1 })
.limit(10);
```

Even metadata fields can expose collection names and activity. Do not paste raw profiler documents into public tickets.

### 17.3. Slow Queries Are Not Always Due to Missing Indexes

Other causes include:

- Indexed queries returning too much data;
- Complex sorts;
- Aggregation memory pressure;
- Long-lived transactions holding resources;
- Network throughput;
- Disk contention;
- Plan cache/shape changes;
- Data skew;
- Chunk migrations/shard balancing;
- Concurrent operations.

Always correlate performance metrics with the exact slow timestamp.

## 18. `currentOp`: Inspecting Running Operations

To see what is currently consuming time, you can run `currentOp` where permissions and version allow:

```javascript
db.adminCommand({
  currentOp: 1,
  active: true
});
```

Results may include:

```text
operation type
namespace
secs_running
waitingForLock
client metadata
command details
```

Not every field appears in every version or operation. `currentOp` is only a **point-in-time snapshot** and may miss short-lived operations.

### 18.1. Be Careful with Sensitive Information

Output can include command details or client info. Do not store raw output in public locations.

### 18.2. Do Not Arbitrarily Kill Operations During Observation

`killOp` and methods to terminate sessions/transactions are operational interventions that can impact users. They require dedicated runbooks and authorization. Observing does not authorize killing every long-running query.

### 18.3. Long-Running Queries and Index Builds

A long-running aggregation may be an incident, whereas a scheduled batch job, index build, or backup may be legitimate. Know maintenance windows and business workloads before alerting or intervening.

## 19. Replica Sets: Replication Lag and Elections

In a replica set:

- Primary accepts writes per topology;
- Secondaries replicate and apply changes;
- Elections change the primary when needed;
- Read preference can route reads to different nodes;
- Write concern affects write confirmation requirements.

Therefore, latency, traffic, errors, and connections must be evaluated in the context of replication.

### 19.1. Replication Lag

A fundamental metric:

```text
Primary oplog time:   T
Secondary applied:    T - 12 seconds
Replication lag:      ~12 seconds
```

Lag affects freshness for secondary reads and can impact majority write confirmation depending on topology and failures.

### 19.2. Checking Status

On a replica set with appropriate privileges:

```javascript
rs.status();
```

Verify:

- Members up/down;
- Current primary;
- Secondary states;
- Health;
- Optime/lag;
- Elections/restarts;
- Network problems.

Do not run `rs.status()` on a single node and conclude all network issues are resolved. Cross-check server metrics and multi-node monitoring.

### 19.3. How Elections Impact Connections and Errors

When the primary changes:

```text
Primary stepdown
     │
     ├── Server selection changes
     ├── Some commands are interrupted/retried
     ├── Connections/pools may re-establish
     └── API latency/errors rise temporarily
```

If a dashboard only shows QPS without topology events, you might misdiagnose this as a query regression.

### 19.4. Do Not "Fix Latency" by Recklessly Lowering Write Durability

Lowering write concern for faster ACKs can compromise data guarantees. Only modify it when you understand business consistency and durability requirements, have approval, and measure against the workload.

## 20. Sharded Clusters: Metrics by Router, Shard, and Namespace

In a sharded cluster:

```text
Application
    │
    ▼
  mongos
    │
    ├── Shard A replica set
    ├── Shard B replica set
    └── Shard C replica set
```

A query can:

- Target a single shard;
- Target a subset of shards;
- Scatter-gather across all shards;
- Wait for result merging;
- Be affected by chunk migrations/balancer activity.

### 20.1. Do Not Inspect One Shard and Generalize to the Whole Cluster

Example:

```text
Shard A CPU = 95%, high p99
Shard B CPU = 20%, normal p99
Shard C CPU = 15%, normal p99
```

Cluster-wide average CPU may look moderate, yet Shard A is a hotspot.

Break down metrics by:

- Shard;
- Replica set member;
- Primary/secondary;
- Namespace;
- Query shape;
- Tenant or partition key when suitable telemetry is available.

### 20.2. Scatter-Gather Can Inflate Traffic

An endpoint that omits the shard key can force `mongos` to send queries to multiple shards. HTTP QPS remains unchanged, yet total MongoDB query activity and network traffic increase.

When reviewing traffic, avoid double-counting between routers and shards as if they were independent business requests.

### 20.3. Balancing/Resharding and Latency Spikes

Chunk migrations, balancing, or resharding can affect disk, network, and CPU. Cross-reference metrics with maintenance events before blaming a traffic surge.

## 21. Atlas Monitoring: Use Built-in Dashboards While Understanding Semantics

MongoDB Atlas offers monitoring dashboards/metrics and performance analysis features depending on deployment tier and version, such as:

- Operations and throughput;
- Connections;
- Query/command latency;
- CPU, memory, disk;
- Network ingress/egress;
- Replication lag;
- Cache/utilization;
- Query targeting;
- Alerts;
- Query Profiler/Performance Advisor or equivalent features;
- Search Nodes metrics when used.

**Metric names and granularity vary by tier and version**, so check the dashboard's tooltips and definitions rather than assuming every name matches `serverStatus()`.

### 21.1. Is the Metric Node-Scoped or Cluster-Scoped?

A "Connections" chart may show a single node or the whole cluster depending on the view. When comparing:

- Select the right cluster/project;
- Select the node role;
- Check time range and timezone;
- Verify whether the chart is aggregated or per-node;
- Correlate with rolling upgrades and elections.

### 21.2. Atlas Free/Flex Tiers Have Monitoring Limits

Do not assume Atlas Free, Flex, and Dedicated tiers share the same metric resolution, retention, profiler, alert options, or export capabilities. When production SLOs require detailed p99 tracing, verify that your tier provides sufficient data.

### 21.3. Tie Alerts to On-Call Owners

Atlas alerts are insufficient if:

- Nobody receives notifications;
- Thresholds are disconnected from SLOs;
- Alert spam leads to alert fatigue;
- There is no runbook;
- There is no escalation path;
- There are no safeguards against destructive actions.

Monitoring design is part of operations, not just toggling a notification.

## 22. `mongostat` and `mongotop`: Two Different Tools

MongoDB Database Tools / diagnostic tools include observation utilities such as `mongostat` and `mongotop` in supported environments.

### 22.1. `mongostat`

Example run in an authorized shell:

```bash
mongostat --uri "$MONGODB_URI" 5
```

The example above uses Unix shell syntax; on Windows PowerShell, environment variable syntax differs. Never embed real usernames/passwords in commands or terminal logs.

`mongostat` gives a periodic sampled view of:

- Insert/query/update/delete;
- Connections;
- Cache/memory;
- Network;
- Replication metrics;
- Columns depending on server/tool version.

It is suited for quick diagnostics, **not as a replacement for long-term time-series monitoring**.

### 22.2. `mongotop`

Example:

```bash
mongotop --uri "$MONGODB_URI" 5
```

`mongotop` reports read/write time per namespace according to the tool's sampling mechanism. It helps identify collections with notable activity.

Do not mistake `mongotop`'s millisecond columns for HTTP p95 latency. They measure **MongoDB activity time** at a different scope.

### 22.3. Do Not Run Tools as Root Just to View Metrics

Use a monitoring account with least-privilege permissions, TLS, and private connectivity. Diagnostic tools are also clients whose credentials must be controlled.

## 23. Java Driver: Collecting Command Latency and Errors

With the MongoDB Java Sync Driver, you can use **CommandListener** to observe command started/succeeded/failed events.

Minimal example:

```java
import com.mongodb.event.CommandListener;
import com.mongodb.event.CommandStartedEvent;
import com.mongodb.event.CommandSucceededEvent;
import com.mongodb.event.CommandFailedEvent;

import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.LongAdder;

public final class SafeMongoCommandListener implements CommandListener {

    private final LongAdder successCount = new LongAdder();
    private final LongAdder failureCount = new LongAdder();
    private final LongAdder elapsedNanos = new LongAdder();

    @Override
    public void commandStarted(CommandStartedEvent event) {
        // Do not log event.getCommand() indiscriminately:
        // the command body may contain PII or tokens.
    }

    @Override
    public void commandSucceeded(CommandSucceededEvent event) {
        successCount.increment();
        elapsedNanos.add(
            event.getElapsedTime(TimeUnit.NANOSECONDS)
        );
    }

    @Override
    public void commandFailed(CommandFailedEvent event) {
        failureCount.increment();
        elapsedNanos.add(
            event.getElapsedTime(TimeUnit.NANOSECONDS)
        );
    }

    public long successes() {
        return successCount.sum();
    }

    public long failures() {
        return failureCount.sum();
    }

    public long totalElapsedNanos() {
        return elapsedNanos.sum();
    }
}
```

Register the listener when building `MongoClientSettings`:

```java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

String uri = System.getenv("MONGODB_URI");

SafeMongoCommandListener listener =
    new SafeMongoCommandListener();

MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .addCommandListener(listener)
    .build();

MongoClient client = MongoClients.create(settings);
```

This example demonstrates **monitoring hook points**, not a complete production metrics exporter. Counters represent totals since the listener was created. A production setup needs:

- Histograms for durations;
- Command name as a useful label;
- Low-cardinality error categories;
- Context about the application instance;
- Export to a metrics backend;
- Correlation with API spans;
- Avoiding logging command parameters;
- Closing `MongoClient` according to application lifecycle.

### 23.1. Command Elapsed Time Excludes Application Wait Overhead

The driver command listener focuses on database command lifecycles. It **does not automatically measure all** pool checkout wait, server selection, business-code serialization, or HTTP response time.

Place a timer at the application service boundary for an end-to-end view.

### 23.2. When a Command Fails but a Retry Succeeds

If monitoring increments `failureCount` on the first attempt and a retry succeeds, the application still returns 200. These are two metrics at different scopes:

```text
Driver command attempt: failed
Driver later attempt:  success
HTTP request:          success
```

Do not "fix" numbers by erasing driver failures; clearly distinguish *attempt failure* from *logical request failure*.

## 24. Java ConnectionPoolListener: Seeing the Wait Queue

The MongoDB Java Driver emits connection pool monitoring events. Production instrumentation typically needs:

- Pool created/cleared/closed;
- Connection created/ready/closed;
- Checkout started;
- Checkout succeeded;
- Checkout failed;
- Checked in;
- Checkout duration.

Skeleton configuration:

```java
import com.mongodb.MongoClientSettings;
import com.mongodb.ConnectionString;
import com.mongodb.event.ConnectionPoolListener;

MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(
        new ConnectionString(System.getenv("MONGODB_URI"))
    )
    .applyToConnectionPoolSettings(builder -> {
        builder.addConnectionPoolListener(
            new MyConnectionPoolMetricsListener()
        );
    })
    .build();
```

`MyConnectionPoolMetricsListener` is an **application class you implement yourself** from `ConnectionPoolListener` per your driver version's API. It is not a built-in class in the MongoDB Driver.

### 24.1. Events to Correlate

```text
ConnectionCheckOutStarted
        │
        ├── Succeeded → checkout duration
        │
        └── Failed    → reason / timeout
```

If checkout duration p99 rises while `mongod` operation latency looks normal, possible reasons include:

- Pool too small for concurrency;
- Connections held long by other operations;
- Pool establishing connections too slowly;
- Application has too many threads competing for the pool;
- One client instance generating excessive concurrent requests;
- Slow network/TLS establishment.

Increasing `maxPoolSize` can help in some cases, but can also push more load onto MongoDB, worsening server overload. Benchmark and enforce concurrency controls.

## 25. OpenTelemetry: Traces Stitch the Layers Together

An end-to-end trace might look like:

```text
Trace: GET /orders/search 900 ms
   │
   ├── API middleware                   10 ms
   ├── Business rule                    20 ms
   ├── DB pool / server selection      450 ms
   ├── MongoDB aggregate              120 ms
   ├── External service call          200 ms
   └── Response serialization         100 ms
```

A trace with spans reveals where time is spent. However, **breakdown accuracy** depends on instrumentation: not every library creates a dedicated span for pool wait automatically.

### 25.1. Correlation IDs

Propagate a request/trace ID across layers:

```text
HTTP traceId
    ↕
Application log
    ↕
Driver span/command event
    ↕
Operational timeline
```

Do not place raw user data, secrets, MongoDB URIs, or PII in span attributes. A trace ID is valuable even without storing command bodies.

### 25.2. Sampling

Full tracing for every request can be expensive. Options include:

- Head-based sampling;
- Tail-based sampling;
- Higher sampling rates for errors/slow requests;
- Keeping aggregate metrics for 100% of traffic;
- Enforcing retention and privacy policies.

Do not sample a few successful traces and claim they represent the entire latency distribution.

## 26. Defining SLI, SLO, and SLA

A good dashboard must answer: **"Are users receiving the service as promised?"**

- **SLI (Service Level Indicator):** metric measuring actual service quality.
- **SLO (Service Level Objective):** internal target for an SLI over a period.
- **SLA (Service Level Agreement):** contractual service commitment if applicable.

### 26.1. Example SLIs for a MongoDB-Backed API

```text
SLI availability:
  successful HTTP requests / eligible HTTP requests

SLI latency:
  proportion of eligible requests completing <= 250 ms

SLO:
  99% eligible requests complete <= 250 ms over 30 days
```

This is an example, not a recommended threshold for every MongoDB application.

Defining **eligible requests** is critical:

- Are health checks excluded?
- Do 4xx errors from invalid client input count as availability failures?
- How are client-canceled HTTP requests counted?
- Are gateway timeouts captured?

Without a shared definition, two dashboards can report different SLOs for the exact same traffic.

### 26.2. Error Budget

If the success SLO is 99.9% over a month:

\[
\text{error budget fraction}=1-0.999=0.001=0.1\%
\]

The goal is to balance feature delivery with reliability. When burn rate is high, teams can pause risky changes and focus on remediation.

### 26.3. Database SLO and API SLO Differ

A database metric:

```text
MongoDB command success rate >= 99.99%
```

does not guarantee:

```text
User checkout success rate >= 99.9%
```

because the API also depends on other services, business logic, and downstream processing.

Maintain both business-level and DB-level SLIs for diagnosis.

## 27. Designing a Minimum Dashboard

A practical MongoDB/app dashboard should include the following panels:

### 27.1. Row 1 — User Health

| Panel | Purpose |
|---|---|
| API request rate | User traffic |
| API error rate by endpoint/status | Availability |
| API latency p50/p95/p99 | User experience |
| Key business success rate | Business impact |

### 27.2. Row 2 — MongoDB Operations

| Panel | Purpose |
|---|---|
| Reads/writes/commands per second | Database load |
| Server operation mean latency | Processing speed |
| Driver command latency p95/p99 | Command timing |
| Driver error categories | DB errors |
| Slow query volume | Notable queries |
| Query targeting | Query/index efficiency |

### 27.3. Row 3 — Connections/Pools

| Panel | Purpose |
|---|---|
| Server `connections.current` | Open connections |
| Server `connections.active` | Current activity |
| Server `connections.available` | Headroom |
| Connection creation rate | Churn |
| Driver checked-out/idle/waiting | Pool pressure |
| Pool checkout duration p95 | Wait time |
| Pool checkout failures | Bottleneck signal |

### 27.4. Row 4 — Capacity/Topology

| Panel | Purpose |
|---|---|
| CPU, memory, disk IOPS/latency | Saturation |
| WiredTiger cache/dirty bytes | Storage pressure |
| Replication lag/elections | Replica set |
| Shard-specific hotspots | Sharding |
| Network ingress/egress | Data traffic |
| Search index sync lag | Derived indexing if used |

### 27.5. Row 5 — Changes

Add deployment/change annotations:

```text
09:30 deploy API v2.13
10:05 index build started
10:12 autoscale +4 pods
10:35 primary stepdown
11:00 backup job started
```

Having a change timeline helps distinguish release-induced regressions from organic traffic shifts.

## 28. Setting Actionable Alerts

Alerts should rely on **meaningful thresholds and sustained durations**, not single transient spikes.

Starting examples that must be tuned to your workload:

| Alert | Illustrative condition | Why |
|---|---|---|
| High API p95 | p95 > 300 ms for 10 min | Users waiting too long |
| API error rate | > 1% for 5 min with sufficient traffic | Many failing requests |
| Pool checkout failures | Continuous failures for 5 min | Requests cannot get connections |
| Low connection headroom | Available approaching limit | Risk of connection rejections |
| Connection churn | Unusually high creation rate | Client lifecycle/TLS overhead |
| Replication lag | Exceeds RPO/SLO threshold | Stale reads, availability |
| Low free disk | Below capacity margin | Risk of write failures |
| Sustained high CPU | High CPU paired with latency and queues | Resource saturation |
| Backup failed | A critical backup run failed | Loss of recoverability |
| Primary flapping | Repeated elections | Availability risk |

Thresholds are illustrative only. For low-traffic workloads, percentage alerts need a **minimum sample count**. For seasonal workloads, use time-based baselines or business-tier segmentation.

### 28.1. Do Not Alert Solely on Absolute Connection Count

A pool holding 500 connections may be normal. Better alerts trigger on **anomalous changes**, approaching server limits, rising checkout waits, or connection failures.

### 28.2. Multi-Window Alerts

An error-budget burn signal should detect both:

- Short, severe incidents;
- Small, prolonged degradations.

Combine short and long windows according to your telemetry backend and SLO. Avoid using a single threshold for all alerts.

### 28.3. Do Not Turn Alerts into Self-Inflicted Destruction Loops

Higher latency does not mean automatically running `killOp` on all active operations, restarting the replica set, or lowering write concern. Any automated remediation requires safety guards, ownership, idempotency, rollback, and dedicated testing.

## 29. Runbook: When p99 Latency Spikes

An investigation workflow:

```text
1. Confirm incident scope
      │
      ▼
2. API p95/p99 and traffic/errors
      │
      ▼
3. Driver command / pool waits
      │
      ▼
4. Server opLatencies, opcounters, connections
      │
      ▼
5. CPU, disk, cache, replication, sharding
      │
      ▼
6. Query profiler / explain / recent changes
      │
      ▼
7. Controlled mitigation
      │
      ▼
8. Verify SLO recovery
```

### 29.1. Step 1 — Scope

- One endpoint or the entire API?
- One tenant or all tenants?
- One region or all regions?
- Writes only or reads as well?
- Secondary reads only or primary?
- Search/Vector Search only or regular queries?

### 29.2. Step 2 — Are Users Actually Impacted?

Check HTTP p95/p99, error rate, and business success rate. If only one `mongostat` column spikes while API SLOs remain green, it may not be an incident.

### 29.3. Step 3 — Driver and Connection Pool

If pool wait rises:

- Did app instance count change?
- Is there a connection leak?
- Are queries holding connections too long?
- Are there server selection delays?
- Did pool config/timeouts change?
- Are there many retries?

### 29.4. Step 4 — Server/Query

If operation latency rises:

- Check recently deployed query shapes;
- `explain("executionStats")`;
- Docs examined/returned;
- Index changes;
- Cache/disk;
- Oplog/replication activity;
- Lock/ticket waits;
- Search index builds.

### 29.5. Step 5 — Mitigation

You might roll back code introducing a bad query, intentionally shed traffic temporarily, or optimize indexes following change control. Do not make production changes without understanding the blast radius.

## 30. Runbook: When Connections Spike Unexpectedly

Scenario:

```text
connections.current jumps from 300 to 3000
totalCreated/sec surges sharply
API p99 increases
pool checkout failures appear
```

Investigation checklist:

1. Did a deployment or autoscale event just occur?
2. Is `MongoClient` created once per process?
3. Did `maxPoolSize`, `minPoolSize`, or idle timeout change?
4. Is a load balancer or network resetting connections?
5. Did a primary stepdown occur?
6. Were TLS certs or credentials just rotated?
7. Are there new clients or monitoring jobs?
8. Are long-running operations holding connections?
9. Is there an attack/brute force or unexpected traffic?
10. Where do database connection limits and host resources stand?

### 30.1. Example of a Connection Storm

```text
200 app pods restart simultaneously
   │
   ▼
Each pod opens multiple connections at once
   │
   ▼
TLS + authentication overhead spikes
   │
   ▼
Server comes under pressure and timeouts rise
```

Mitigations can include **staggered rollouts, bounded connection warm-up, and backoff/jitter**, rather than infinitely raising max connections.

## 31. Runbook: When Errors Rise Without Latency Increasing

Scenario:

```text
Latency p95 stays at 80 ms
HTTP 5xx spikes suddenly
MongoDB command failures rise
```

Possible causes:

- Expired/invalid authentication credentials after rotation;
- Revoked user role;
- Wrong database name/authSource;
- Schema validation rejections;
- Duplicate key surge due to a regression;
- Query timeout configured too short;
- Network errors before the command starts;
- Application bug failing fast.

Do not look solely for slow queries. Classify exception codes and inspect the change timeline.

### 31.1. Permission Errors Should Not Be "Fixed" with Root

If an app loses access after a role change, investigate the exact privilege required. Never grant `root` just to silence errors; doing so treats the symptom by expanding the blast radius.

### 31.2. Timeouts May Come from Upstream

An application setting a 100 ms deadline while a call to another service provider has a 150 ms p95 can return timeouts even while MongoDB is healthy. Tracing pinpoints where time is spent.

## 32. When Traffic Rises While Errors and Latency Remain Stable

Not every traffic spike is an incident.

If:

```text
Throughput doubles
p95/p99 stays within SLO
Error rate remains stable
Connections/CPU scale proportionally
Disk/network retain headroom
```

the system may simply be scaling well.

Still, verify:

- Is the traffic growth sustainable?
- How much connection headroom remains?
- Is caching effective?
- Is search index lag growing?
- Is replication lag growing?
- What levels did prior load tests reach?

A traffic surge can be a **capacity planning signal** rather than an immediate incident.

## 33. Capacity Planning from Signals

Suppose workload is projected to grow:

```text
Current:           200 HTTP req/s
Per request:       2 MongoDB commands on average
6-month forecast:  500 HTTP req/s
```

A theoretical estimate:

```text
Current: ~400 DB commands/s
Future:  ~1000 DB commands/s
```

However, this multiplier changes if:

- Endpoint mix shifts;
- Batch reads/writes are optimized;
- Cache hit rate improves;
- Retry rate increases;
- A request triggers fan-out;
- Shard routing changes.

Load test using data, indexes, and configurations close to production.

### 33.1. Little's Law

A fundamental relationship between concurrency, throughput, and response time:

\[
L \approx \lambda W
\]

Where:

- \(L\): average number of operations in the system;
- \(\lambda\): average throughput (operations/s);
- \(W\): average time each operation spends in the system (s).

For example, at 200 operations/s and 0.05 s mean latency, average concurrency is roughly 10 operations.

This is a **steady-state average relationship**; you cannot derive p99 or `maxPoolSize` from a single multiplication. Account for burstiness, blocking, connection lifecycle, and capacity margin.

### 33.2. Warning Near Saturation

Latency typically rises rapidly as resources approach their limits. Do not size a system so normal load already runs at 99% capacity and expect every request to maintain a good p99.

## 34. Common Observability Pitfalls

| Mistake | Why it is wrong | How to fix |
|---|---|---|
| Using mean instead of p95/p99 | Hides tail latency | Histograms/percentiles |
| Comparing API latency with server opLatency as the same scope | Measures different paths | Separate layers |
| Using cumulative counters as QPS | Not divided by time | Compute delta/rate |
| Ignoring counter resets | Negative QPS after restart | Reset-aware telemetry |
| Summing counters across replica members as user requests | Replication causes double counting | Segment by node/traffic |
| Treating `network.numRequests` as HTTP RPS | Different protocol/layer | Use API metrics |
| Assuming 500 connections means a leak | Idle pools may be valid | Check trends/churn/waits |
| Treating `totalCreated` as open connections | It is a cumulative counter | Use `current` |
| Low MongoDB mean means fast API | Pool/network/app may be slow | End-to-end tracing |
| Assuming bigger pools are always better | Can increase server contention | Benchmark/set limits |
| Treating every `E11000` as an incident | May be an expected conflict | Classify by business case |
| Counting only HTTP 5xx | Retries can hide DB errors | Track driver failures |
| High error % on 2 requests is an outage | Sample size too small | Minimum volume/window |
| Global p95 = mean of per-node p95s | Mathematically invalid for percentiles | Aggregate histograms |
| High CPU must be the root cause | May be an effect of load | Correlate queries/I/O |
| One `explain` query defines the SLO | Excludes pool/API overhead | APM + metrics |
| Enabling full profiler without assessing overhead | Consumes resources, exposes data | Sampling/approval |
| Logging raw queries/requests | Can contain PII/secrets | Redaction |
| Alerts without owners | Nobody acts | Runbooks/on-call |
| Using `killOp` as an observation step | Mutates state | Separate approval |
| Creating a `MongoClient` per HTTP request | Connection churn | Singleton/shared lifecycle |
| Ignoring election/replication tracking | Misdiagnoses timeouts | Topology timeline |
| Treating search sync lag as API query latency | Different freshness concept | Track separately |
| A cluster-wide metric hides a shard hotspot | Data skew | Break down per shard |
| Dashboards with only CPU and RAM | Misses user impact | Golden signals |
| Picking thresholds by guesswork | Alert fatigue | SLOs, baselines, load tests |

## 35. Hands-On Exercises

### Exercise 1 — Distinguishing Latency Layers

A request has:

```text
HTTP duration:          900 ms
MongoDB command time:    30 ms
Pool checkout wait:     500 ms
External API:           200 ms
Other processing:       170 ms
```

1. Is the MongoDB server necessarily the primary bottleneck?
2. Which driver metrics should you monitor?
3. Should you add indexes before inspecting the pool?
4. Why is looking only at `opLatencies` insufficient?

### Exercise 2 — Computing Read Throughput from Counters

Data:

```text
T1 at 10:00:00:
  reads.ops = 100000

T2 at 10:01:00:
  reads.ops = 112000
```

1. Calculate reads/s.
2. If there were 5 retries, which metrics distinguish logical requests?
3. How do you handle a process restart between T1 and T2?
4. If T1 and T2 came from two different nodes, can you compare them directly?

### Exercise 3 — Computing Mean Operation Latency

```text
T1:
  reads.ops = 10000
  reads.latency = 5000000 μs

T2:
  reads.ops = 11000
  reads.latency = 7500000 μs
```

1. Calculate delta operations.
2. Calculate delta microseconds.
3. Convert to mean milliseconds.
4. Can you derive p95 from these two counters?

### Exercise 4 — p99 vs. Mean

An API has 99% of requests at 50 ms and 1% at 4 seconds.

1. Does the mean reflect the experience of the slow group?
2. What do p95 and p99 reflect?
3. Why is p99 noisy at low sample sizes?
4. Design histogram buckets aligned with an SLO.

### Exercise 5 — Network Counter

From two `network.bytesOut` samples:

```text
T1: 400000000 bytes
T2: 550000000 bytes
Interval: 30 seconds
```

1. Calculate bytes/s.
2. Convert to MiB/s.
3. List three causes of traffic increases.
4. Why shouldn't this be called the HTTP request rate?

### Exercise 6 — Connections and Churn

```text
T1 current=400, totalCreated=100000
T2 current=420, totalCreated=160000
Interval=5 minutes
```

1. What is the connection creation rate?
2. Did `current` rise sharply?
3. What are the risks of churn?
4. How should you inspect `MongoClient` lifecycle and recent deployments?

### Exercise 7 — Pool Saturation

API p99 is 1.2 seconds, server operations are only 15 ms, and pool checkout p99 is 1 second.

1. Where is the bottleneck likely located?
2. Which in-use/idle/waiting metrics should you measure?
3. Is increasing `maxPoolSize` indefinitely safe?
4. Propose load testing and concurrency controls.

### Exercise 8 — Error Rate with Small Sample Size

In a 5-minute window:

```text
Service A: 1 error / 10 requests
Service B: 1000 errors / 100000 requests
```

1. What is each service's error percentage?
2. Which service has the larger impact by request count?
3. Should alerts rely solely on percentage?
4. Propose combining thresholds and sustained duration.

### Exercise 9 — E11000

A service creating new usernames frequently receives duplicate key errors when a username already exists.

1. Is this an infrastructure failure?
2. How should it be logged and categorized?
3. What should you do if duplicate key errors jump 100x after a deployment?
4. Why shouldn't you drop the unique index just to reduce errors?

### Exercise 10 — Election

After a primary stepdown, the application sees server selection timeouts and an elevated connection creation rate.

1. Explain the relationship between topology and driver behavior.
2. Which metrics confirm an election?
3. When are retries valid?
4. Why shouldn't you restart all nodes to "stabilize" them?

### Exercise 11 — Unindexed Query

An endpoint returns 10 documents but has `totalDocsExamined=800000`.

1. What is the documents examined/returned ratio?
2. What should you inspect in `winningPlan`?
3. Which I/O/cache metrics might be affected?
4. Can you conclude that adding an index alone is enough without testing the query?

### Exercise 12 — Shard Hotspot

A sharded cluster shows Shard A CPU at 95%, B at 20%, and C at 15%.

1. Why does average CPU easily mask a hotspot?
2. How do you check the shard key and query targeting?
3. How can scatter-gather traffic affect metrics?
4. How should dashboards be organized by node/shard?

### Exercise 13 — Java Monitoring

Using `CommandListener`:

1. Count succeeded and failed commands.
2. Collect elapsed duration.
3. Add command name tags without including `_id` or raw queries.
4. Distinguish command errors from HTTP errors.
5. Add connection pool metrics via `ConnectionPoolListener`.

### Exercise 14 — Designing an SLO

A service requires:

```text
99% eligible requests <= 250 ms
30-day window
```

1. Choose an appropriate SLI.
2. Should HTTP 400 validation errors be counted?
3. How do you measure this using a histogram?
4. What should the team do when the error budget burns quickly?

### Exercise 15 — Golden Signals Dashboard

Design a dashboard containing:

- API p50/p95/p99;
- Reads/writes/commands/s;
- Error rates by category;
- Connections current/available/created;
- Pool checkout wait;
- CPU/disk/cache;
- Replication lag;
- Deployment annotations.

Explain the panel ordering for incident response purposes.

### Exercise 16 — Complete Runbook

Simulate:

```text
11:00 API p99 jumps from 250ms to 2s
11:02 traffic rises 30%
11:03 pool checkout timeouts appear
11:04 replica lag rises
11:05 connection creation rate rises
```

1. Rank candidate root-cause hypotheses.
2. List read-only commands and dashboards to inspect.
3. Identify correlations between each timestamp.
4. Propose a mitigation with a rollback plan.
5. Write criteria to confirm recovery.

## 36. Production Checklist for MongoDB Observability

### Metrics and Tracing

- [ ] API p50/p95/p99 are measured per endpoint/service.
- [ ] MongoDB command duration is measured via driver instrumentation.
- [ ] Pool checkout wait and checkout failures have metrics.
- [ ] Server `opLatencies` are collected with the right node, window, and units.
- [ ] Throughput is computed from counter deltas/rates.
- [ ] HTTP requests/s are kept separate from MongoDB operations/s.
- [ ] Network bytes/s are measured per node/role.
- [ ] Error rate categorizes timeout/auth/duplicate/network failures.
- [ ] Retry counts are observed independently of HTTP success.
- [ ] Connections current/active/available/created have dashboards.
- [ ] Counter resets are handled on server restarts.
- [ ] Trace/correlation IDs follow a privacy policy.

### Capacity and Topology

- [ ] CPU, RAM, disk IOPS/latency/free space are monitored.
- [ ] WiredTiger cache/eviction/dirty bytes have baselines.
- [ ] Slow query/query plan monitoring is enabled per permissions and overhead.
- [ ] Replica status/elections/replication lag have alerts.
- [ ] Sharded deployments are viewed per shard, not only as cluster averages.
- [ ] Search/Vector indexing lag is monitored if used.
- [ ] Backup and restore monitoring has an owner.
- [ ] Production-representative capacity/load tests exist.

### Alerts and Operations

- [ ] Every critical alert has an on-call owner and runbook.
- [ ] Thresholds are tied to SLOs/baselines rather than chosen arbitrarily.
- [ ] Percentage alerts enforce a minimum sample volume.
- [ ] Deployment/maintenance annotations are recorded.
- [ ] Alerts are tested on staging or through appropriate drills.
- [ ] Monitoring never automatically triggers destructive actions.
- [ ] Logs/metrics do not contain unnecessary secrets or PII.
- [ ] Telemetry has defined retention and access control policies.
- [ ] Post-incident reviews and alert tuning processes are in place.

## 37. MongoDB Reference Documentation

The pages below provide detailed descriptions by server version and deployment; before implementing, verify field names and semantics against the version you run:

- [MongoDB Monitoring](https://www.mongodb.com/docs/manual/administration/monitoring/)
- [MongoDB `serverStatus`](https://www.mongodb.com/docs/manual/reference/command/serverStatus/)
- [MongoDB `db.serverStatus()`](https://www.mongodb.com/docs/manual/reference/method/db.serverStatus/)
- [MongoDB `currentOp`](https://www.mongodb.com/docs/manual/reference/command/currentOp/)
- [MongoDB `explain`](https://www.mongodb.com/docs/manual/reference/method/cursor.explain/)
- [MongoDB Database Profiler](https://www.mongodb.com/docs/manual/tutorial/manage-the-database-profiler/)
- [MongoDB `mongostat`](https://www.mongodb.com/docs/database-tools/mongostat/)
- [MongoDB `mongotop`](https://www.mongodb.com/docs/database-tools/mongotop/)
- [MongoDB Atlas Monitoring](https://www.mongodb.com/docs/atlas/monitoring-alerts/)
- [MongoDB Atlas Alerts](https://www.mongodb.com/docs/atlas/configure-alerts/)
- [MongoDB Replica Set Monitoring](https://www.mongodb.com/docs/manual/administration/monitor-replica-sets/)
- [MongoDB Connection Pooling](https://www.mongodb.com/docs/manual/administration/connection-pool-overview/)
- [MongoDB Java Sync Driver Monitoring](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/monitoring/)
- [MongoDB Performance Best Practices](https://www.mongodb.com/docs/manual/administration/analyzing-mongodb-performance/)

## Conclusion

**Latency, traffic, errors, and connections** are the four core signal groups for observing a MongoDB system in production. However, they must be measured **at the right layer**:

- **Latency:** do not rely solely on server averages; track API p95/p99, command timing, pool wait, and distributed traces.
- **Traffic:** distinguish HTTP requests/s, MongoDB operations/s, network bytes/s, and replication activity; many MongoDB counters are **cumulative** and require time-window deltas.
- **Errors:** separate business rejections, driver/server failures, retries, timeouts, authentication issues, and write concern errors; avoid lumping every error into a meaningless single percentage.
- **Connections:** monitor current/active/available counts, creation rate, pool in-use/waiting counts, checkout latency, and churn; a high connection count **does not by itself prove** a leak.
- **Context:** CPU, disk, WiredTiger cache, query plans, replication, sharding, Search indexing, and deployment changes explain the real root cause.

A sound observability setup requires **metric definitions, units, measurement windows, histograms, dashboards, alerts with owners, runbooks, privacy controls, and recovery verification**. The ultimate measure is not how many charts you have created, but whether the operations team can **detect early, isolate the scope, mitigate safely, and confirm that the system has returned to its SLO**.

**MongoDB is neither "slow" nor "fast" based on a single number; observe the entire journey of a request and use the four signal groups to find the true cause before changing the system.**
