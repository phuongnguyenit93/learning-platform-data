# 7.8 Connection management, query frequency, and cardinality limits for monitoring data

A single JVM can expose hundreds of JMX attributes, numerous `ObjectName`s, and management notifications. The challenge in production is not merely calling `getAttribute()`, but **observing continuously over time without overloading the JVM, causing connection storms, or exploding the number of series in the time-series backend**. Three closely linked decisions govern this:

1. **Connection management:** who opens JMX connections, how long do they live, when are they closed, and how are timeouts, reconnects, and authorization handled?
2. **Query frequency:** which MBeans are queried, how many times per second, with what concurrency, and do polls overlap when a prior cycle hasn't finished?
3. **Cardinality limits:** when turning attributes and ObjectNames into metrics, how many unique label combinations exist and how fast do they churn?

For example, scraping 20 attributes across 100 JVMs every 15 seconds sounds small—yet if each attribute requires a remote round trip, one cycle sends roughly **2,000 calls**. If every metric also attaches dynamic `request_id` or `user_id` labels, millions of time series can appear, driving up CPU, memory, network, and storage costs while degrading dashboard and alert reliability. A sound design controls **cost across the JVM, collector, and metrics backend**.

This lesson builds an operational model for JMX in Java 17+: `JMXConnector` and `MBeanServerConnection` lifecycles, timeouts, backoff, bounded concurrency, polling cadence, counter vs. gauge semantics, allowlist attribute selection, cardinality math, and safe label design. The Java 17+ practice code runs standalone using the **internal** platform MBeanServer, requiring no open remote JMX ports or external services.

## 1. Model of a JMX monitoring system

A common pipeline:

```text
 [JVM A]       [JVM B]       [JVM C]
    |             |             |
 MBeanServer   MBeanServer   MBeanServer
    |             |             |
 JMX connector / JMX access (if configured and authorized)
    \             |             /
     \            |            /
      +--- monitoring collector ---+
          | connect/reconnect      |
          | discover + getAttrs    |
          | schedule + retry       |
          | transform + filter     |
          | limit labels/series    |
          +-----------+------------+
                      |
                 metrics backend
                      |
             dashboards / alerts
```

Each layer has distinct responsibilities:

| Layer | Responsibility | Risk if poorly designed |
| --- | --- | --- |
| JVM/MBean | Exposes management values | Slow/locking getters, too many MBeans, sensitive data |
| Connector | Transports requests/responses and events | Connection leaks, network drops, misconfigured auth/TLS, timeouts |
| Collector | Selects attributes, schedules polls, retries, transforms | Thundering herds, overlapping polls, turning missing data into 0 |
| Exporter/mapper | Converts `ObjectName` and values into labeled metrics | Dynamic labels, series churn, wrong units and metric types |
| Time-series backend | Stores series, runs queries/rates/alerts | Active series explosion, RAM/disk/query latency spikes |
| Operator | Reads data and makes decisions | Confusing snapshots with history, reconnects with restarts, noisy alerts |

**The JMX API is a management access model—it does not provide retention, rate calculation, or cardinality guardrails.** You must build those layers or use a proven exporter configured equivalently. Clearly separate a **remote connection** from a **local `MBeanServerConnection`**: identical read methods, very different costs, network errors, and resource lifecycles.

### 1.1 The managed unit is "target JVM instance," not just hostname

One host can run multiple JVMs. A pod/container can restart and change PID. A service can have multiple replicas. Therefore target identity should include:

- Authorized workload/service name.
- Environment/cluster/namespace per policy; not everything needs to become a metric label.
- Process/JVM instance ID or startup time to detect restarts.
- Endpoint and connection mode (local JMX, secured remote JMX, or in-process agent/exporter).
- Specific MBean `ObjectName` and attribute name.
- Sample timestamp, connection status, and data quality.

Do not treat connecting to `host:port` as proof of the right JVM if routing, NAT, sidecars, or deployments changed. `ObjectName` identifies beans only within **one MBeanServer** and can repeat across JVMs. `JMXConnector.getConnectionId()` identifies a connection **for that connection's lifetime**, not a durable service identity or a persistent metric label.

## 2. Managing the JMX connection lifecycle

### 2.1 Core APIs

Key components in Java SE:

| API | Purpose | Notes |
| --- | --- | --- |
| `JMXServiceURL` | Describes the JMX connector endpoint | Does not guarantee the endpoint is secure or always reachable |
| `JMXConnectorFactory.connect(url, env)` | Establishes the connection, returns connected `JMXConnector` | Can fail with I/O, security, or protocol/provider errors |
| `JMXConnector.getMBeanServerConnection()` | Obtains handle for remote JMX calls | Methods on the connection can still fail after handshake |
| `MBeanServerConnection.getAttributes(...)` | Reads multiple attributes from one MBean | Unreadable/missing attributes may be omitted silently |
| `JMXConnector.close()` | Closes client connection | Can throw `IOException` and `close()` itself can block/lag |
| `addConnectionNotificationListener(...)` | Listens for JMX connection status | Not a durable historical event log |
| `JMXConnector.getConnectionId()` | Server-assigned ID for the connection | Do not use as a label per reconnect |

`MBeanServerConnection` represents an access channel to a **local or remote** MBeanServer; local `MBeanServer` extends it. Over remote connections, a connection can succeed and later drop network or lose permissions; never assume a successful handshake guarantees every subsequent `getAttribute` will succeed.

### 2.2 Connect once, reuse conditionally, close with discipline

A collector should generally **reuse healthy connections** across polling cycles rather than reconnecting and re-authenticating every second, yet there is no rule for "immortal connections":

1. Open connections only to approved targets and endpoints.
2. Perform authentication/TLS and verify server identity via properly configured transport.
3. Run a lightweight bounded-cost probe confirming the exact target JVM.
4. Reuse the connector while healthy and permitted by transport policy.
5. On I/O or connection failures, mark the connection unhealthy; never keep using a stale `MBeanServerConnection` as if valid.
6. Reconnect with backoff/jitter, capped attempts, and strict resource cleanup.
7. On collector shutdown or target removal, remove listeners and call `close()` during lifecycle cleanup.

**Every new connect carries cost**: transport handshake, authentication, socket/thread allocation, and MBean checks. **Connections held forever** also face stale state, server redeploys, and resource leaks. Choose lifetimes based on provider, network policy, target count, failure rate, and real load.

### 2.3 API pattern for closing connections with try-with-resources

The Java snippet below is an **illustrative method**; callers must supply a valid endpoint and authenticated environment strictly on authorized networks:

```java
import java.util.Map;
import javax.management.AttributeList;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

static AttributeList readOnce(
        JMXServiceURL url, Map<String, ?> approvedEnvironment)
        throws Exception {
    try (JMXConnector connector =
                 JMXConnectorFactory.connect(url, approvedEnvironment)) {
        MBeanServerConnection connection =
                connector.getMBeanServerConnection();
        ObjectName threading = new ObjectName("java.lang:type=Threading");
        return connection.getAttributes(threading,
                new String[] {"ThreadCount", "DaemonThreadCount"});
    }
}
```

This **is not a standalone Java file**: the method belongs inside a class, and `approvedEnvironment` security config must come from deployment. To avoid reconnecting on every scrape, hold the connector in a **resource owner** responsible for health, reconnect, and closing rather than recreating it per call as in this brief snippet. `AttributeList` returns after reading completes; never retain `MBeanServerConnection` for use after the connector closes.

**Important:** `JMXConnector.close()` in JDK 21 can **block for a noticeable duration** when a server fails or stops responding. `try-with-resources` guarantees cleanup is invoked, **not that `close()` is non-blocking**. If production enforces tight time budgets, implement controlled transport and shutdown management rather than assuming `close()` is instantaneous.

### 2.4 Never invent timeout property names as a universal JMX standard

Standard JMX defines connector APIs; **connect/read/idle/retry timeouts depend on the provider, transport, JDK release, and environment**. No arbitrary `-D...timeout` flag can be claimed as universally effective across all connectors.

Timeout design must separate:

- **DNS/endpoint resolution**: does the hostname resolve properly?
- **Connection establishment/TLS/auth**: handshake and authentication time.
- **Remote request/read**: is `getAttribute` slow due to network or the getter?
- **Total scrape deadline**: does the full cycle fit within cadence?
- **Shutdown/close**: cleanup can lag.
- **Retry/reconnect budget**: avoid hammering dead targets forever.

Exact timeout settings must follow **your specific provider/version documentation** and be verified under simulated network failures. Wrapping calls in `Future.get(timeout)` alone **does not guarantee** blocked I/O aborts immediately: `cancel(true)` requests an interrupt, not a guaranteed socket close across every RMI/provider implementation. Never spawn unbounded threads when prior calls refuse to exit.

### 2.5 Distinguishing connection status, empty data, and dead targets

| Symptom | Possible cause | Appropriate response |
| --- | --- | --- |
| Initial connection fails | Wrong endpoint, auth/TLS, network, server not listening | Check endpoint and security; apply backoff |
| Active connection emits `FAILED` | Network/server drop, connector state changed | Mark connector unhealthy; clean up and reconnect |
| `getAttributes` returns fewer fields | Missing/non-readable attribute, permission, or getter error | Inspect returned list; never fill in 0 |
| `InstanceNotFoundException` | MBean vanished/redeployed, wrong ObjectName/JVM | Rediscover boundedly, verify instance |
| Per-request timeout | Blocking getter, overloaded JVM, network/transport | Record timeout; cut fan-out, inspect resources |
| No fresh samples | Target, collector, or export pipeline failure | Keep missing/stale status and scrape health; never fake success |
| `getConnectionId` changes | Reconnect / new connection instance | Use to diagnose connection churn, not conclude JVM restart |

Multiple causes can occur together. Never conclude "GC broke JMX" from a single timeout.

## 3. Connection notifications and collector health

`JMXConnector.addConnectionNotificationListener(...)` receives `JMXConnectionNotification` events (when emitted by the provider per contract), such as:

- `OPENED`: connection opened.
- `CLOSED`: connection closed.
- `FAILED`: connection failed abnormally.
- `NOTIFS_LOST`: the client may have missed some remote notifications.

These are **connection events**, distinct from MBean notifications about heap thresholds or application queues. A `NOTIFS_LOST` notification warns about event-stream completeness; it does not imply metric polling lost the same samples.

Operational principles:

1. Track connection health via status, reconnect counts, connect latency, and I/O errors—**not** merely open TCP socket counts.
2. Register the listener once per connector lifecycle and remove it on cleanup.
3. Never perform blocking reconnects or heavy MBean queries directly inside the callback.
4. After reconnecting, re-verify the MBean registry/target identity and resubscribe listeners if needed.
5. Never treat `OPENED`/`CLOSED` as **durable history**; event streams can drop.
6. If monitoring relies on notifications, run periodic polling to reconcile state and use durable event storage where business requirements demand it.

**Why avoid using connection ID as a label?** Because the ID changes on every reconnect, creating a brand-new time series. If hundreds of targets reconnect often, series count climbs even with one JVM per target. Keep connection IDs in **access-restricted diagnostic logs** for tracing while using stable target identities for metrics.

## 4. Query frequency: cadence, measurement windows, and cost

### 4.1 Polling an attribute is not receiving an event

An MBean attribute is typically a **current snapshot** or **cumulative counter**. Calling `getAttribute` every 30 seconds cannot reveal brief peaks that rose and fell between two samples.

Example queue depth:

```text
T=00s: depth = 4   (polled)
T=10s: depth = 250 (spike)
T=20s: depth = 3   (spike over)
T=30s: depth = 4   (polled)
```

Polling only every 30 seconds shows 4 consistently and **misses the 250 spike**. Capturing peaks or causes requires events, histograms, high-watermarks, or controlled faster sampling depending on the goal. Even faster polling cannot guarantee catching every spike without event capture.

### 4.2 Classify data before picking an interval

| Observation kind | JMX example | Calculation / polling habit |
| --- | --- | --- |
| Instantaneous gauge | `ThreadCount`, `QueueDepth`, `HeapMemoryUsage.used` | Sample per goal and volatility; do not infer min/max between samples |
| Cumulative counter | GC collection count, completed tasks, request total | Compute delta/rate over time; detect restarts/resets |
| Slowly changing metadata/config | JVM vendor, version, bean names, fixed capacity | Discover/cache per lifecycle; do not query every second |
| Event/notification | Threshold crossing, MBean registered/unregistered | Subscribe if supported; reconcile against missed events |
| Expensive diagnostic | Heap dump, full thread dump, heavy histograms | Keep out of routine polling loops |
| Per-request trace | Individual request latency, stack/context | Never turn each request into a dynamic MBean/metric label |

**No single cadence fits all MBeans.** Choose based on SLO needs, data dynamics, getter/round-trip cost, target count, and desired detection latency. For instance, 15–30 second sampling may suit an overview dashboard, whereas catching millisecond spikes needs proper event sources—not cranking polling to thousands of calls per second.

### 4.3 Relationship between interval and query volume

Suppose:

- `T` = number of JVM targets.
- `B` = MBeans queried per target.
- `A` = attributes needed per bean.
- `P` = seconds between polls.

If a naive client reads attributes individually over remote JMX:

```text
attribute_reads_per_cycle = T × B × A
attribute_reads_per_second_average ≈ (T × B × A) / P
```

Example with `T=60, B=4, A=3, P=15`:

```text
60 × 4 × 3 = 720 attribute values / cycle
720 / 15 = 48 attribute values / second (average)
720 × (3600 / 15) = 172800 values / hour
```

Using `getAttributes(name, String[])` per bean to **cut remote round trips** reduces theoretical method calls to `T × B = 240 calls/cycle`, or roughly **16 calls/second**, yet the JVM **still reads 720 values**. This is a sizing estimate, **not a measured benchmark**: getter cost, transport overhead, and attribute counts per bean vary.

A multi-attribute batch is also not an atomic snapshot of the entire MBean/JVM; individual fields may be missing (the API drops them from `AttributeList`). **Never equate 720 requested values with 720 guaranteed returned values.**

### 4.4 Cost may sit inside the getter rather than the network

A well-designed getter reads an atomic counter, while another getter might lock a data structure, scan a huge collection, compute a histogram, or query OS stats. Polling MBeans too frequently can make monitoring itself cause CPU load, lock contention, or request slowdowns.

A sensible policy:

1. Fetch only genuinely required attributes via an allowlist.
2. Classify cheap/medium/expensive attributes with separate cadences.
3. Measure p50/p95/p99 of **scrape duration** and collection error rates, not just business metrics.
4. Bound timeouts and in-flight work so slow getters do not pile up overlapping requests.
5. For rarely changing metadata, cache `MBeanInfo` with invalidation when MBeans change.
6. If application latency climbs alongside monitoring load, test lowering cadence in a controlled check and compare.

Reducing round trips does not replace **designing cheap getters** or bounding total work per scrape.

## 5. Safe polling scheduling

### 5.1 fixed-rate, fixed-delay, and overlapping jobs

Suppose a target is polled every 10 seconds, yet one scrape takes 18 seconds:

- If the scheduler allows overlap, **two scrapes can run concurrently** against the JVM, compounding load and muddling timestamps.
- With a **sequential single worker** or single-flight guard, the next cycle does not overlap; the gap between samples stretches beyond 10s. This is safer for most workloads.
- `scheduleAtFixedRate` on a `ScheduledThreadPoolExecutor` does not run **successive executions of the same periodic task** concurrently per contract, yet separate tasks or separate collector instances can still hit the same target simultaneously; never assume the whole system is protected from overlap.
- `scheduleWithFixedDelay` waits a fixed gap after the previous execution finishes, helping prevent overlap and give breathing room—though actual cadence becomes **job duration + delay**.

Recommended pattern for distributed collectors:

```text
target JVM ──> one owner ──> at most one in-flight poll
                        |
                   bounded timeout
                        |
                 success / missing
                        |
          next schedule + jitter/backoff
```

If a cluster runs multiple collector replicas polling one target, a local mutex **is not enough**. Assign ownership by shard/leader or run one exporter per JVM scraped by the backend to avoid double collection.

### 5.2 Jitter prevents thundering herds

If 1,000 JVMs are scraped simultaneously at `00:00:00`, `00:00:15`, ..., network and CPU bursts can occur. **Small jitter** spreads start times:

```text
nominal_interval = 15 s
start_offset_per_target ∈ [0 s, 3 s]
retry_delay = capped_exponential_backoff + bounded_jitter
```

These numbers are **design examples**, not JMX defaults. Jitter should be stable/reproducible enough to keep target schedules steady; hashing target identity works if you watch for operational hash collisions and measure real load distribution.

With a nominal 15-second window, if a scrape lags, record the actual sample timestamp and real elapsed interval; never compute rates dividing by constant 15 when 23 seconds actually elapsed.

### 5.3 Bound concurrency at multiple levels

Enforce limits:

- **Per target:** at most one active scrape, preventing overlapping requests.
- **Per collector:** bounded total connections and in-flight requests.
- **Per host/pod/network:** avoid slamming one JVM/node with many concurrent tasks.
- **Retry budget:** cap reconnect attempts and retry rates.
- **Memory buffers/queues:** bounded; when full, drop or delay with explicit metrics rather than growing queues unboundedly.

If a collector runs 100 workers for 20 JVM targets, idle threads add no better telemetry. If it serves 10,000 targets, 1 worker is far too slow; the fix is **sharding, prioritization, batching, and capacity planning**, not unbounded threads.

## 6. Backoff, circuit breakers, and interpreting missing data

### 6.1 Do not retry relentlessly when an endpoint is down

When a JVM restarts or the network drops, retrying every 10 ms from many collectors creates a **retry storm**. Illustrative backoff schedule:

```text
initial_delay = 15 s
after 1 failure = 30 s
after 2 failures = 60 s
subsequent = 60 s capped + small jitter
```

Reset failure counters once connections stabilize. A circuit breaker can pause heavy queries to a failing target, allowing a light probe after cooldown. Separate auth/certificate errors (usually needing config fixes) from transient errors (eligible for bounded retries). Never log passwords or tokens in error context.

### 6.2 Missing is not zero

Suppose queue depth reads `T0 = 50`; `T1` times out; `T2 = 80`. Wrong approaches:

- Recording `T1 = 0`: fabricates a false drop.
- Keeping `T0 = 50` indefinitely without marking stale: looks "healthy" with no data.
- Computing delta `80 - 0` to report an 80-item jump when `T1` was never measured.
- Subtracting a pre-restart GC counter from a post-restart counter and reporting a negative rate.

The system needs dedicated collector health signals like `scrape_success` (1/0), scrape duration, last sample timestamp, and error category. **Missing data** is a valid measurement state; never coerce it into a "zero errors" business value.

### 6.3 Why simple timeouts are not always enough

Remote requests can block inside Java RMI or another provider. Spawning a new thread for every timeout without ever freeing stuck threads exhausts collector workers and heap. `Future.cancel(true)` requests an interrupt, yet not all transport I/O aborts promptly. Production solutions combine provider-supported transport timeouts, bounded worker/connection lifecycles, isolation of failing tasks, thread-leak monitoring, and clean connector recovery.

**Never invent an undocumented JMX timeout property** and claim it works across every JVM/JDK.

## 7. Querying the right MBeans and reducing calls

### 7.1 Discover frequently only when truly needed

Avoid calling `queryNames(null,null)` every 5 seconds to enumerate **every MBean** and read every attribute on every bean. Problems:

- The registry holds platform beans, application beans, libraries, and diagnostic beans.
- Dynamic beans may appear and vanish with workload.
- Metadata and attribute values can expose internal names/secrets or incur high cost.
- Every dynamic `ObjectName` can spawn a new metric group.
- In multi-tenant environments, overly broad queries create unrelated observation overhead.

Start with a **bounded set of ObjectNames/domain patterns**, such as `java.lang:type=Threading` or `com.example.monitoring:type=Queue,name=Orders`, paired with an attribute allowlist. Cache discovery for the JVM's lifetime or refresh infrequently; on `InstanceNotFoundException`/redeploy, refresh with backoff.

### 7.2 getAttributes instead of N getAttribute calls, while checking missing fields

`MBeanServerConnection.getAttributes(ObjectName,String[])` requests multiple attributes of **one** MBean:

```java
AttributeList list = connection.getAttributes(
        new ObjectName("java.lang:type=Threading"),
        new String[] {"ThreadCount", "DaemonThreadCount"});
```

This is an **illustrative snippet inside a method holding** `connection`; it is not a standalone program. The API may **omit unreadable/unavailable attributes** from `AttributeList`. Never assume the result contains both values or preserves request array order; inspect each `Attribute`'s name.

Do not bundle hundreds of attributes "for convenience" across different MBeans; each call targets **one** ObjectName. For data requiring an atomic snapshot of multiple fields, JMX does not provide that guarantee automatically; the app can expose a dedicated read-only composite snapshot, or dashboards must accept a consistency window.

### 7.3 Cache MBeanInfo, but not blindly across JVM lifetimes

`getMBeanInfo` returns an MBean's attribute/operation metadata. Usually you fetch it once at discovery or when beans change, not on every scrape. However:

- MBeans can unregister and re-register with a new contract.
- `DynamicMBean` metadata can depend on runtime state.
- Service redeploys/restarts can change attribute names or types.
- A JMX endpoint can route to a different instance after reconnect.

Therefore key metadata caches by **JVM instance + ObjectName**, apply sensible TTL/invalidation, and handle contract mismatches gracefully. Never keep metadata cached forever across restarts.

### 7.4 Restricting access rights and safety

Collectors should use **read-only permissions** when purely monitoring. Never grant broad `setAttribute` or `invoke` rights just to read metrics. Operations can flush caches, reset counters, or restart components. Protect remote connectors with network boundaries, authentication, TLS, and least privilege; never expose unauthenticated remote JMX on the Internet.

Command lines, URL credentials, session IDs, ObjectNames, and notifications can carry sensitive data. Log only connection IDs/target aliases when diagnosing, never passwords or raw environment maps.

## 8. What is cardinality, and why does it cause problems?

**Metric cardinality in a time-series backend** is the number of distinct label combinations the backend must store for that metric. In Prometheus-style models, each unique combination of **metric name + label names/values** creates a time series. Changing a label from `instance=A` to `instance=B` creates another series. Rapidly changing identifier labels cause **series churn**: old series stop updating while still occupying storage/metadata index resources for a retention window.

Cardinality differs from:

- **Sample count:** a single series sampled 240 times/hour is still one series (for a constant label set).
- **Metric name count:** one metric can spawn millions of series due to labels.
- **MBean count:** one MBean can have many attributes/series; an app can create thousands of dynamic MBeans.
- **Target JVM count:** each target can emit hundreds of series.
- **Log text volume:** series count is a metadata/index/query scaling problem, not just raw sample bytes.

### 8.1 Combinatorial upper-bound formula

If a metric has independent labels with at most `n1, n2, ..., nk` distinct values, potential series count is:

```text
potential_series_per_metric ≤ n1 × n2 × ... × nk
```

The `≤` sign reflects that not every combination necessarily occurs in practice. Still, this is an **upper-bound estimate** to control design risk before real distribution data exists.

Hypothetical example:

| Label | Maximum values |
| --- | ---: |
| `service` | 3 |
| `environment` | 2 |
| `instance` (per service/env) | 4 |
| `collector` | 3 |
| `status` | 2 |

Upper bound: `3 × 2 × 4 × 3 × 2 = 144 series` for one metric. Adding `request_id` with 10,000 values pushes the upper bound to **1,440,000 series**. Most JMX metrics have **zero reason** to attach request IDs at the series level; per-request tracing belongs in logs/traces with appropriate retention, sampling, and access control.

**Even a single unbounded label** can blow through the budget even when every other label has only a handful of values.

### 8.2 Labels that look harmless yet are highly dynamic

| Proposed label | Risk | Alternative |
| --- | --- | --- |
| `request_id`, `trace_id` | Nearly every request spawns a new series | Keep in traces/logs, never as metric labels |
| `user_id`, email, phone | Unbounded, private data | Drop; aggregate by permitted groups |
| `session_id`, token | Unbounded, sensitive | Never place in metrics |
| Full URL/path with ID | Every distinct path/query spawns a series | Route template like `/orders/{id}`, never raw IDs |
| `exception_message` | Free-form input text, may contain secrets | Exception class/category allowlist |
| Raw `sql_query` | Distinct literals/queries, leaks data | Normalized query type/operation |
| Dynamic `thread_name` | Embeds numbers/IDs/sessions; large domain | Thread pool name or role group |
| Full `ObjectName` | May contain dynamic IDs | Map to stable MBean type/name subset |
| `connection_id` | New ID on every reconnect | `reconnect_total` metric per stable target |
| `pid` | Changes across restarts, collides across container namespaces | Use lifecycle-aware instance identity in target metadata |
| Timestamp inside label | New series on every scrape | Timestamps belong on **sample timestamps**, not labels |

Many labels do not just waste RAM—they **leak sensitive data**: account names, internal hosts/endpoints, SQL strings, credentials, and config paths. The "no dynamic IDs" rule serves both performance and data governance.

### 8.3 High vs. low cardinality is not fixed by label name

`status` might have three values `ok|warn|error`, yet stuffing raw error messages into `status` makes it unbounded. `endpoint` might be five stable route templates or millions of individual URLs. `instance` is valuable for inspecting one JVM, yet grows with replica count and deploys.

Always inspect the **source of values**, not just the label name. A "safe-looking" label list can turn into high cardinality if application behavior shifts.

## 9. From ObjectName/attributes to metric labels

JMX often structures names like:

```text
com.example:type=Queue,name=Orders,tenant=ACME42
```

An exporter might turn domain/type/name/tenant into labels. If `tenant` has thousands of values and MBeans are spawned per request, series count explodes. Far better is an explicit allowlist mapping **from ObjectName to metric schema**, capping accepted values.

### 9.1 Pick the metric contract before mapping

Example **designed** schema:

```text
java_app_queue_depth{service="orders",environment="prod",pool="primary"} 12
java_app_queue_processing_total{service="orders",environment="prod",pool="primary"} 4210
```

These two lines **illustrate metric format**, not measurements from a live system. Never carry `tenant_id`, `session_id`, or the full `ObjectName` into labels. If customer-tier breakdown is needed, evaluate **aggregation into finite buckets** under privacy rules rather than putting real IDs into time series.

### 9.2 Enforce label values with an allowlist

Process:

1. Define **metric name**, unit, gauge/counter kind, and per-scrape semantics.
2. Specify the exact permitted label keys.
3. For each label key, define the valid value list or bounded source.
4. If values are invalid or excessive, prefer **dropping the dimension** or bucketing into `other` per tested policy rather than minting arbitrary series.
5. Never rename label schemas casually; schema changes require versioning/review.
6. Measure actual unique series and churn against backend budgets and alerts.

Allowlisting label keys alone **is not enough** if request IDs get stuffed into `pool`; validate **both value sources and domains**.

### 9.3 Necessary labels that still require lifecycle management

`instance`, `pod`, and `container` are essential for diagnosing restarts and distinguishing JVMs. They introduce churn whenever deployments replace instances. That is justified churn, requiring:

- Automatically stopping exports for deleted/stale targets.
- Stale markers or series expiration per backend design, never filling fake values.
- Appropriate retention and scrape intervals.
- Bounding replicas/scrape targets within monitoring budgets.
- Aggregating dashboards by `service`/`environment` for SLOs while keeping `instance` for drill-down.

Never strip all instance labels just to shrink cardinality if doing so merges separate JVMs and corrupts counter-reset detection.

## 10. Series budget, churn budget, and storage cost

### 10.1 Series budget is not sample budget

With `S` active series and interval `P` seconds:

```text
samples_per_hour_approx ≈ S × (3600 / P)
```

For `S=144, P=15`, that gives roughly `144 × 240 = 34,560 samples/hour` for those series if every scrape succeeds. Adding a request ID yielding `S=1,440,000` gives roughly **345,600,000 samples/hour** assuming every series stays active on every scrape. **This is a hypothetical upper bound**, not a real usage forecast: individual request IDs may exist for only one scrape, causing intense **series churn** rather than 1.44 million continuously active series. Even so, churn still heavily taxes metadata, indexes, and retention.

Never multiply "samples/hour" by a fixed byte constant to estimate disk usage without knowing encoding, replication, label sets, histogram formats, and retention.

### 10.2 Two kinds of limits to measure

- **Active series cardinality:** series considered active within the backend's current window.
- **Series churn:** new series appearing or disappearing over a time interval.

A service with 10,000 stable active series can be far easier to operate than one with only 2,000 active at any instant that spawns hundreds of thousands of new series per hour. Reconnects, dynamic MBean creation, or deployments embedding timestamps in names all cause churn.

### 10.3 Tiered budgeting

**Illustrative** policy ideas (not a JMX standard):

| Tier | Designable threshold / condition | Response |
| --- | --- | --- |
| Single MBean | Allowlist of exported attributes/labels | Drop out-of-scope fields |
| Single JVM target | Max exported series, max scrape duration | Narrow scope/interval, report sample loss |
| Single collector | Max connections/in-flight requests, memory queue | Rate-limit/shard and back off |
| Single service | Max unique series/churn per hour | Review labels and object creation |
| Whole backend | Active series, ingest rate, storage/query budget | Capacity planning and alerts |
| Privacy | Zero secrets/PII in label values | Strip fields before export |

**Never silently drop series and render charts as if complete.** When budgets are exceeded, emit `exporter_series_dropped_total` or equivalent status alongside clear info on affected metrics. Yet the "dropped count" metric itself must use bounded labels—never put the dropped request/user IDs onto it.

## 11. Right metric types: gauge, counter, and histogram

### 11.1 Gauge

A gauge reflects state at sample time, such as `ThreadCount` or `HeapMemoryUsage.used`. Dropping from 50 to 40 is normal. Never apply `rate` to a gauge to infer completed events unless an explicit derivative model applies.

### 11.2 Counter

Cumulative counters such as `GarbageCollectorMXBean.getCollectionCount()` or task totals. Reading one final number does not tell you current rate. Compute deltas between two samples on the **same JVM instance**, handling resets/restarts, undefined values (`-1` on some MXBeans), and missing samples. When converting milliseconds to seconds for a backend, convert units accurately and reflect them in metric names/metadata.

If a count drops due to a restart, never report "negative GCs"; separate series by instance/metadata or use the backend's counter-aware rate functions. Never call a cumulative counter a pause histogram.

### 11.3 Histograms and event data

If p95/p99 latency is required, polling `getAttribute("AverageLatency")` cannot reconstruct the distribution. You need histogram buckets, summaries, or event-level data instrumented with proper semantics and bounded label cardinality. Histograms with many buckets **multiply series count**: if each label combination has 12 bucket series plus count/sum, one metric family creates many series per combination. Check your specific backend/exporter model before sizing.

### 11.4 Lock down types and units

Examples:

- `getCollectionTime()` in the Java API returns **milliseconds**, yet Prometheus conventions favor **seconds**.
- Heap uses bytes; never name it `_mb` if values are bytes.
- Durations should carry the `_seconds` suffix where backend conventions require it.
- Counters typically use `_total` in Prometheus naming; gauges should not carry that suffix arbitrarily.
- Java `System.nanoTime()` is an elapsed clock, never a UTC timestamp.

Unit mismatches can cause alerts to misfire by factors of thousands even when connections work fine.

## 12. Notifications do not replace reliable polling schedules

An MBean can emit a `Notification` when crossing a threshold, yet:

- It may not support the exact event type you need.
- It may fire before you subscribe.
- Disconnected listeners miss events, and JMX guarantees no replay.
- `NOTIFS_LOST` at the connection layer only warns of possible missed notifications; it does not deliver the lost events.
- Callbacks can overload under thousands of events/s; listeners need bounded processing.
- Notification messages/`userData` can carry sensitive data.

Combined model: use notifications as a **fast signal**, slower polling to **reconcile state**, and dedicated persistent stores when auditing history. If an event carries `sequenceNumber`, treat it as per-source ordering, not global ordering across JVMs.

Never turn dynamic notification types or event sequence numbers into metric labels. Incrementing `jmx_notifications_total{type="threshold"}` over an approved type allowlist is fine; never export `sequence_number` as a label.

## 13. Standalone Java 17+ lab: budget math and local attribute reads

The demo code illustrates two goals:

1. **Default mode, deterministic:** computes upper-bound series, scrapes/hour, label allowlist checks, and backoff per an illustrative policy. Makes no remote connections and needs no external workload.
2. **`--local`, non-deterministic data:** reads two attributes from the **demo JVM's platform MBeanServer** to show `MBeanServerConnection.getAttributes` and checking for missing fields. It queries no remote JVM and asserts no fixed thread count.

Save `JmxMonitoringBudgetDemo.java`:

```java
import java.lang.management.ManagementFactory;
import java.util.HashMap;
import java.util.Map;
import java.util.Set;
import javax.management.Attribute;
import javax.management.AttributeList;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public class JmxMonitoringBudgetDemo {
    private static final Set<String> ALLOWED_LABEL_KEYS =
            Set.of("service", "environment", "instance", "collector", "status");

    static long product(int... dimensions) {
        long total = 1;
        for (int dimension : dimensions) {
            if (dimension <= 0) {
                throw new IllegalArgumentException("dimension must be positive");
            }
            total = Math.multiplyExact(total, dimension);
        }
        return total;
    }

    static long retryDelaySeconds(int consecutiveFailures) {
        int bounded = Math.min(Math.max(consecutiveFailures, 0), 2);
        return Math.min(60L, 15L << bounded);
    }

    static void showPolicy() {
        int secondsBetweenPolls = 15;
        long baseSeries = product(3, 2, 4, 3, 2);
        long withRequestIds = Math.multiplyExact(baseSeries, 10_000L);

        System.out.println("POLL_INTERVAL_SECONDS=" + secondsBetweenPolls);
        System.out.println("SCRAPES_PER_HOUR=" + 3600 / secondsBetweenPolls);
        System.out.println("BASE_SERIES_UPPER_BOUND=" + baseSeries);
        System.out.println("WITH_10000_REQUEST_IDS=" + withRequestIds);
        System.out.println("REQUEST_ID_ALLOWED="
                + ALLOWED_LABEL_KEYS.contains("request_id"));
        System.out.println("BACKOFF_FAILURE_0_SECONDS=" + retryDelaySeconds(0));
        System.out.println("BACKOFF_FAILURE_1_SECONDS=" + retryDelaySeconds(1));
        System.out.println("BACKOFF_FAILURE_2_SECONDS=" + retryDelaySeconds(2));
        System.out.println("BACKOFF_FAILURE_3_SECONDS=" + retryDelaySeconds(3));
    }

    static void showLocalAttributes() throws Exception {
        MBeanServerConnection connection =
                ManagementFactory.getPlatformMBeanServer();
        ObjectName threading = new ObjectName("java.lang:type=Threading");
        String[] requested = {"ThreadCount", "DaemonThreadCount"};

        AttributeList list = connection.getAttributes(threading, requested);
        Map<String, Object> received = new HashMap<>();
        for (Object entry : list) {
            Attribute attribute = (Attribute) entry;
            received.put(attribute.getName(), attribute.getValue());
        }

        System.out.println("LOCAL_REQUESTED=" + requested.length);
        System.out.println("LOCAL_RETURNED=" + received.size());
        System.out.println("LOCAL_THREAD_COUNT_PRESENT="
                + received.containsKey("ThreadCount"));
        System.out.println("LOCAL_DAEMON_COUNT_PRESENT="
                + received.containsKey("DaemonThreadCount"));
    }

    public static void main(String[] args) throws Exception {
        showPolicy();
        if (args.length == 1 && "--local".equals(args[0])) {
            showLocalAttributes();
        }
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac JmxMonitoringBudgetDemo.java
java JmxMonitoringBudgetDemo
```

**Exact stdout of default mode:**

```text
POLL_INTERVAL_SECONDS=15
SCRAPES_PER_HOUR=240
BASE_SERIES_UPPER_BOUND=144
WITH_10000_REQUEST_IDS=1440000
REQUEST_ID_ALLOWED=false
BACKOFF_FAILURE_0_SECONDS=15
BACKOFF_FAILURE_1_SECONDS=30
BACKOFF_FAILURE_2_SECONDS=60
BACKOFF_FAILURE_3_SECONDS=60
```

Explanation:

- `3600/15 = 240` scrapes per hour on a theoretical schedule, ignoring failures, jitter, and actual execution time.
- 3 services × 2 environments × 4 instances × 3 collectors × 2 states = **144** maximum combinations.
- Adding 10,000 request IDs: `144 × 10,000 = 1,440,000` upper bound, illustrating the risk of using request IDs as labels.
- `ALLOWED_LABEL_KEYS` omits `request_id`, so the code prints `false`. Real systems must also validate label **values**.
- Backoff after 0, 1, 2, 3 failures is 15, 30, 60, 60 seconds; this is a simulated policy model—**it makes no connections, executes no real retries, and omits jitter**.

To read local JMX:

```bash
java JmxMonitoringBudgetDemo --local
```

The program prints four additional `LOCAL_...` lines. Data may depend on implementation, permissions, and JVM; the code **does not hardcode** a fixed count of successful attributes. `ThreadCount` and `DaemonThreadCount` are standard attributes on `java.lang:type=Threading` on compatible HotSpot/JDKs, yet list handling still checks each field's presence rather than assuming requesting two fields always returns two fields.

### 13.1 What does the code teach, and what is missing for production?

The code demonstrates **budget math, label allowlisting, and attribute reads by name**—not a production monitoring agent. It lacks scheduling, remote networking, authentication/TLS, provider timeouts, persistence, Prometheus exposition, reconnects, and alerting. It intentionally opens no JMX port so it runs safely on any learning machine.

To evolve into a real collector, add a resource owner managing `JMXConnector`, bounded deadlines/retries, non-overlapping scheduling, logging/scrape health, a unit-explicit metric schema, timeout/restart tests, and full integration tests.

### 13.2 Remote lifecycle snippet for comparison

This method **is not a standalone Java file**; it illustrates the API shape once an application holds an approved `JMXServiceURL` and a `Map<String,?>` containing valid transport/auth configuration:

```java
import java.util.Map;
import javax.management.MBeanServerConnection;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

static void withAuthorizedConnection(
        JMXServiceURL endpoint,
        Map<String, ?> securedEnvironment) throws Exception {
    try (JMXConnector connector =
                 JMXConnectorFactory.connect(endpoint, securedEnvironment)) {
        MBeanServerConnection connection =
                connector.getMBeanServerConnection();
        // Only read allowlisted ObjectNames/attributes here.
        // Never log secrets, never invoke mutating operations.
    }
}
```

Reconnecting on every poll cycle is discouraged; for continuous polling, retain connections inside a component with an explicit lifecycle. Nor does this snippet provide universal timeouts, TLS, or authorization: those must be configured and tested for your actual connector provider. Never copy the snippet to expose unauthenticated JMX RMI.

## 14. Example operational policy config (not standard JMX syntax)

A configuration file for a monitoring service **might** look like:

```yaml
jmx_monitoring:
  enabled: true
  targets:
    source: "approved-service-discovery"
    maximum_total: 500
  connection:
    mode: "authenticated-tls-only"
    maximum_in_flight_per_target: 1
    maximum_in_flight_global: 40
    reconnect_initial_seconds: 15
    reconnect_cap_seconds: 60
    jitter_max_seconds: 3
  polling:
    cheap_interval_seconds: 15
    metadata_refresh_seconds: 600
    expensive_attributes_enabled: false
    allowed_mbeans:
      - "java.lang:type=Threading"
      - "java.lang:type=Memory"
    allowed_attributes:
      "java.lang:type=Threading": ["ThreadCount", "DaemonThreadCount"]
      "java.lang:type=Memory": ["HeapMemoryUsage"]
  cardinality:
    allowed_label_keys: ["service", "environment", "instance", "pool"]
    reject_label_keys: ["request_id", "user_id", "session_id", "full_url"]
    maximum_series_per_target: 300
    track_series_dropped: true
  quality:
    emit_scrape_success: true
    emit_scrape_duration: true
    emit_last_sample_age: true
```

**This is a fictional design manifest**, not a built-in configuration format for JMX, JConsole, Prometheus, or JMX Exporter. Specific keys and values must be implemented in your own collector or mapped to your chosen tool's schema. For example, `authenticated-tls-only` is a **policy requirement**, not a Java setting toggled by a YAML line.

**Notable design points:**

- Bounds per-target and global in-flight work to prevent connection storms.
- One poll at a time per target, preventing overlap.
- Metadata refreshes far less often than data sampling.
- Only two ObjectNames and a few allowlisted attributes.
- Disallows dynamic labels carrying user/request identifiers.
- Dedicated health metrics and tracking of dropped series.
- Rejects generic "poll every MBean, every attribute."

## 15. Operational scenarios to test your policy

### 15.1 One JVM stops responding while others remain healthy

**Context:** one target has a slow getter while 49 others respond normally. If a collector runs 50 threads with unlimited retries per target, the failing target can monopolize workers and sockets.

**Handling:** per-target budgets, provider timeouts, circuit breakers/backoff, bounded queues, and independent target ownership. Mark `scrape_success=0` for the failing target (per exporter contract) and leave business metrics missing/stale. Never turn queue depth into 0.

### 15.2 Active series jump 20x after a deploy

**Context:** a team adds an `exception_message` label containing error text. Each distinct value creates a series; initial samples/sec may barely budge if each error occurs briefly.

**Handling:** inspect schema diffs, top labels by unique value count, series churn, and new metric names. Strip free-form/sensitive fields from labels and replace with a bounded exception class/category. Never throw extra RAM at the metrics backend just to mask the bug.

### 15.3 Dashboard shows a sudden GC counter drop

**Context:** the collector reconnects right across a JVM restart; `GarbageCollectorMXBean.getCollectionCount()` drops from 5,000 to 10. Without restart markers on the series, dashboards may compute negative deltas or false spikes.

**Handling:** track process/JVM instance, uptime/start time, counter resets, and collector identity. Use the backend's counter-aware rate functions; never subtract two counters from **two different JVM instances** as if continuous.

### 15.4 Monitoring increases CPU or request latency

**Context:** a remote collector runs `queryNames(null,null)` every second and reads thousands of attributes.

**Handling:** identify expensive getters, lower discovery cadence, use allowlists, batch `getAttributes`, bound concurrency, and measure scrape latency. If symptoms persist, profile/optimize getters or let the app emit cheap metrics directly. **Never conclude JMX APIs are "always slow"**: cost depends on the beans, transport, and polling rate.

### 15.5 Notifications drop after reconnect

**Context:** JMX notifications are incomplete; the connector emitted `NOTIFS_LOST`.

**Handling:** verify resubscription, check filters and target identity, and add reconciliation polling. Never mistake absent notifications for zero events. If event completeness is required, store events in a dedicated durable system.

### 15.6 Two exporters scrape the same target

**Context:** two collectors in the same cluster both poll 200 attributes/10 seconds from the same JVM. Data may be double-sent or tagged with conflicting labels.

**Handling:** assign target/shard ownership, standardize metric/label mappings, deduplicate properly, or reduce collector count. Never assume an in-process lock stops a scraper running in another process.

### 15.7 Per-session MBeans spawn unbounded series

**Context:** an app registers `com.example:type=Session,id=<session-id>` for every session, and an exporter scrapes all of them automatically.

**Handling:** replace per-session MBeans with aggregate metrics per pool/service, unregister MBeans on session end, exclude session IDs from labels, and monitor churn. Address PII governance too, since ObjectNames can expose identifiers.

## 16. Checklist before taking JMX monitoring to production

- [ ] Verified exact target JVM instances, endpoints, ObjectNames, and required attributes.
- [ ] Remote JMX opened strictly within permitted boundaries with TLS/authentication/authorization separating read-only from mutating access.
- [ ] Connectors have clear ownership, lifecycles, cleanup/`close()`, and reconnect handling.
- [ ] Transport/provider timeouts verified; no unverified property flags used.
- [ ] Per-target and global in-flight limits enforced with no overlapping scrapes.
- [ ] Polling intervals grounded in observation goals, getter cost, and target event duration.
- [ ] Jitter, backoff, and retry budgets configured to prevent thundering herds.
- [ ] `getAttributes` batching enabled where sensible, checking for missing fields and consistency.
- [ ] `queryNames`/`MBeanInfo` discovery scoped, rate-limited, TTL-cached, and invalidated across redeploys.
- [ ] Metrics distinguish gauge/counter/histogram with explicit units and reset logic.
- [ ] Missing data never coerced to 0; scrape health and last sample age emitted.
- [ ] Computed upper-bound label combinations, active series, and churn budgets.
- [ ] No `request_id`, `user_id`, email, token, ID-containing URLs, dynamic ObjectNames, or connection IDs in metric labels.
- [ ] Labels validated on both keys **and value domains**, not names alone.
- [ ] Explicit action defined when cardinality caps trip, with dropped-series counts exposed.
- [ ] Never infer p99 from average attributes or call GC collection time CPU %.
- [ ] JMX notifications paired with resubscribe/reconciliation, not treated as durable event stores.
- [ ] Tested target down, auth failure, timeout, restart, deploy, scale-out, and duplicate-exporter scenarios.
- [ ] Operational runbook tracks collector overhead, connections, worker queues, latency, and series counts.
- [ ] JMX outputs, metadata, and labels handled in compliance with privacy and retention policies.

## 17. Self-check exercises

**Question 1.** A collector polls 60 JVMs, 4 MBeans per JVM, 3 attributes per bean, every 15 seconds. If each attribute is read individually, what is the average read rate?

**Answer:** `60 × 4 × 3 = 720` attribute reads/cycle, or `48 reads/second` and `172,800 reads/hour` on a theoretical schedule. Batching `getAttributes` per bean drops remote calls to 240/cycle, though the JVM still reads all values and fields may be omitted.

**Question 2.** Why should you avoid using `JMXConnector.getConnectionId()` as a metric label?

**Answer:** Connection IDs change on reconnects, creating series churn unrelated to service changes. Use stable target/JVM instance identities for metrics and keep connection IDs in restricted diagnostic logs.

**Question 3.** `getAttributes` requests five fields and returns four. Can you treat the fifth field as 0?

**Answer:** No. The API can omit unavailable/unreadable attributes. Match returned names, record missing status, and call individual `getAttribute` if you need the exact error.

**Question 4.** Every new request registers an `ObjectName` containing `request_id`. What risk does this create?

**Answer:** Registry/MBean counts grow, lifecycles get complex, and if an exporter promotes `request_id` to a label, cardinality and churn explode. Use aggregate MBeans and dedicated tracing per request.

**Question 5.** One poll cycle takes 20 seconds while the interval is 10 seconds. What needs to change?

**Answer:** Prevent overlap, enforce deadlines and bounded concurrency, inspect expensive getters, or slow cadence / narrow scope. Never spawn unlimited threads trying to stay "on schedule."

**Question 6.** A metric has 3 services × 2 environments × 4 instances × 3 collector types × 2 states. What is the upper bound?

**Answer:** 144 series for that metric. Adding 10,000 request IDs yields an upper bound of 1,440,000—a design risk even if not every combination occurs simultaneously.

**Question 7.** When a JVM loses connectivity for one cycle, should the queue depth chart record 0?

**Answer:** No—0 is a valid business value. Record missing/stale and separate scrape failure state. On recovery, never compute a false delta from 0.

**Question 8.** Why is `Future.cancel(true)` insufficient as a timeout mechanism for all remote JMX requests?

**Answer:** Interrupts may not abort blocking transport/provider I/O immediately. You need provider-level timeouts, controlled connection lifecycles, and bounded workers/threads.

**Question 9.** Once JMX notifications are enabled, is polling still needed?

**Answer:** Depending on requirements: notifications do not guarantee persistence/replay and can drop across reconnects. Reconciliation polling catches missed events, while durable event systems are needed for full history.

**Question 10.** Does lowering the poll interval from 15 seconds to 1 second solve p99 request latency?

**Answer:** Not automatically. One snapshot per second cannot reconstruct request latency distributions and increases overhead. Use histograms/event traces and match cadence to your diagnostic question.

## References

- [Java SE 21 — JMXConnector](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/JMXConnector.html): connections, `close()`, listeners, and connection IDs.
- [Java SE 21 — JMXConnectorFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/JMXConnectorFactory.html): creating connectors, `connect`, providers/environments.
- [Java SE 21 — MBeanServerConnection](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html): `getAttribute`, `getAttributes`, queries, and omitted fields.
- [Java SE 21 — JMXConnectionNotification](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/JMXConnectionNotification.html): opened, closed, failed, notifications lost.
- [Java SE 21 — ManagementFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ManagementFactory.html): platform MBeanServer and MXBeans.
- [Java SE 21 — ScheduledThreadPoolExecutor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html): periodic tasks, scheduling, and concurrency semantics.
- [Prometheus — Metric and Label Naming](https://prometheus.io/docs/practices/naming/): label sets define time series; avoid unbounded identifiers.
- [Prometheus — The Zen of Prometheus](https://prometheus.io/docs/practices/the_zen/): series cardinality, labels, and metric instrumentation.

**Key takeaway:** managing JMX monitoring is a problem of **bounding resources and preserving data semantics**. Reuse connections with clear lifecycles and security, apply provider-supported timeouts/retries, avoid overlapping polls, measure true elapsed windows, allowlist attributes, and cap label cardinality at the source. A system that "collects every number" while slowing down the JVM, spawning millions of series, or turning missing data into 0 **is not** a trustworthy monitoring system.