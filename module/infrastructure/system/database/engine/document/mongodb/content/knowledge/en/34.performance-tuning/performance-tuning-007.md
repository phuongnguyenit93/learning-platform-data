# Controlling Concurrency, Connection Pools, and Request Queues

A MongoDB application can run blazingly fast with 50 concurrent users yet grind to a halt and time out en masse when traffic hits 500 or 5,000. The knee-jerk reaction is **raising thread counts and `maxPoolSize`**, hoping "more connections means higher throughput." In reality, once the database is already saturated on CPU, I/O, locks, or storage-engine resources, running more queries in parallel **lengthens wait times, bloats memory, triggers retry storms, and degrades p99 latency**.

This lesson—**"Controlling Concurrency, Connection Pools, and Request Queues"** in the **Performance Tuning** chapter of the *Database Engine Document MongoDB* module—focuses on three distinct yet interconnected layers:

1. **Concurrency / admission control:** How many requests/operations are permitted to start or consume resources concurrently?
2. **Connection pool:** How many network connections does the MongoDB driver maintain and lend to operations at any moment?
3. **Queueing / backpressure:** When arrival rate exceeds processing capacity, how long should requests wait, when should they be rejected, and how do we prevent unbounded queues?

The ultimate goal is not maximizing every raw counter, but achieving **sustainable throughput**, **bounded p95/p99 latency**, **graceful resilience under overload**, and **clean recovery after spikes or failovers**.

> **Scope and versions:** Java examples primarily target **MongoDB Java Sync Driver 5.x** and modern MongoDB Server releases. APIs and timeout options vary across 4.x, 5.x, and patch versions; in particular, **Client-Side Operation Timeout (CSOT) `timeoutMS` is currently marked experimental by MongoDB**, and legacy timeout options have specific interaction and deprecation rules. Verify against your exact driver, server, and framework versions before deploying. Connection counts, timings, and load curves in this lesson are **illustrative scenarios**, not benchmarks from a real cluster.

## 1. Symptoms: Why Can Increasing the Connection Pool Slow Things Down?

Suppose an API looks up orders by customer:

~~~text
HTTP request
    |
    v
Application worker/thread
    |
    v
Admission gate (bounded admission)
    |
    v
MongoDB driver selects server
    |
    v
Check out connection from pool
    |
    v
MongoDB server receives command
    |
    v
Query execution / storage / network
    |
    v
Return connection -> Return HTTP response
~~~

Requests can wait at completely different stages:

- Waiting in the **HTTP worker/queue** before the handler runs.
- Waiting at an application-enforced **semaphore/bulkhead**.
- Waiting on **MongoDB server selection** when no eligible primary/secondary is found.
- Waiting on **connection checkout** when the pool has no idle connections left.
- Waiting on **connection establishment** during cold start when `maxConnecting` throttles concurrent connects.
- Waiting on **MongoDB command execution** due to CPU, disk, locks, cache misses, transaction conflicts, aggregation memory, or cluster routing.
- Waiting on network, responses, or cursor `getMore`; in some streaming use cases, connections may be held or re-borrowed according to cursor/batch semantics.

**Key takeaway:** "The request is waiting" does not tell you **where** it is waiting. If the server is saturated and you blindly raise the pool from 100 to 1,000, requests simply move from the **pool wait queue** to the **server execution queue**, with zero improvement in total latency.

### 1.1. Symptom and Investigation Matrix

| Symptom | Possible Cause | Evidence to Collect |
|---|---|---|
| Connection checkout wait p95 rises | Pool saturated or slow connection creation | CMAP driver events, checked-out/in-use, waiters, `maxConnecting` |
| `MongoTimeoutException` during server selection | Primary unavailable / topology / network issue | Server selection exception, topology view, failover status |
| Many connections, flat throughput | DB CPU/IOPS/locks saturated, slow queries | `serverStatus`, profiler, query plans, CPU/IOPS, p95 command execution |
| App CPU spikes, GC pauses | Excessive futures/threads/queued requests | Heap, GC logs, executor queue depth, thread dumps |
| Scaling pods suddenly slows DB | Each pod has its own pool opening connections | Pool count × pod count, connection creation rate, server connections |
| All requests time out after failover | Server selection, pool clear/reconnect, retry storm | SDAM/CMAP events, network, exponential backoff |
| Single query fast, HTTP p99 high | HTTP queue, admission wait, pool wait, network | End-to-end distributed tracing per stage |
| `maxTimeMS` timeout in DB | Query consumes too much server execution time | `explain`, indexes, aggregation, workload saturation |

### 1.2. Three Competing Objectives

1. **Resource utilization:** Do not leave the DB needlessly idle while valid requests wait.
2. **Bounded tail latency:** Do not queue 10,000 requests in front of a system capable of 100 requests/second.
3. **Fairness and availability:** One heavy tenant or report must not starve login or checkout APIs.

Sound architectures combine **concurrency limits + bounded queues + timeouts + load shedding**, and only then tune pool sizes against actual workload measurements.

## 2. Four Concurrency Layers to Distinguish

### 2.1. User / HTTP Concurrency

`concurrentRequests` is the number of requests currently processed or queued by the service—not equal to thread counts and not always equal to MongoDB connections. A single HTTP request might:

- Never touch MongoDB.
- Run 1 query and call another service.
- Run 3 sequential queries.
- Run 3 parallel queries via futures/reactive code.
- Hold a long-lived cursor or change stream.

Hence **1 request does not equal 1 MongoDB connection** at all times.

### 2.2. Application Concurrency / Worker Pool

Java Servlet thread pools, `ExecutorService`, virtual threads, Spring Reactor schedulers, or job workers govern **how many tasks execute concurrently**. A blocked thread waiting on a connection still ties up JVM resources and an HTTP worker slot.

With an asynchronous driver, many operations can stay **in-flight without one dedicated Java thread per operation**; however, database concurrency must still be bounded. Async does not mean infinite database capacity.

### 2.3. Driver Connection Pool

**A `MongoClient` maintains a separate pool per server** it communicates with in the topology, plus monitoring sockets outside the operation pool cap. A pool is a **cache/reuse mechanism for transport connections**, not a universal scheduler replacing all application queues.

When the driver needs a connection while all pooled connections are checked out and the pool has reached `maxPoolSize`, the thread/request **waits for checkout** up to its configured timeout.

### 2.4. MongoDB Server Execution Concurrency

Even if 200 connections fire commands at the primary simultaneously, the server will not execute 200 commands "just as fast as 20." MongoDB is bounded by:

- CPU cores, cgroup CPU quotas, and context switching.
- WiredTiger cache/eviction and disk IOPS/throughput.
- Lock contention and write conflicts.
- Storage engine concurrent tickets/admission.
- Query plans, indexes, sort/aggregation memory limits.
- Replication / write concern, sharding network / `mongos`.

**Pool size is not a server throughput quota.** A server can hold thousands of idle TCP connections while only a fraction have active operations running.

### 2.5. Multi-Tier Queue Diagram

~~~text
Incoming requests (rate λ)
    |
    v
HTTP ingress / load balancer
    |    [queue 1]
    v
Application admission gate
    |    [queue 2: bounded]
    v
Worker / async operation
    |    [wait for server selection]
    v
MongoDB driver pool
    |    [queue 3: connection checkout wait]
    v
mongod / mongos
    |    [internal scheduling/locks/tickets]
    v
Storage engine / disk
~~~

If a request waits 100 ms at each tier, HTTP latency hits hundreds of milliseconds even when the query executes in 10 ms. **Adding more queues never adds processing capacity.**

## 3. Quantitative Foundations: Little's Law and Capacity

### 3.1. Little's Law

In a stable steady-state system:

\[
L = \lambda W
\]

Where:

- \(L\): average number of work items **in the system** (including active service and waiting in queue if the measurement boundary includes the queue).
- \(\lambda\): actual completed throughput, requests/second.
- \(W\): average time each request spends within that same boundary, seconds.

For example, if a service completes 400 MongoDB operations/second and each operation holds a connection for 0.025 seconds on average:

\[
L \approx 400 \times 0.025 = 10
\]

At steady state, roughly **10 operations hold connections concurrently on average**. This does **not** mean you should set `maxPoolSize=10` everywhere; p95/p99 tails, burstiness, multi-query requests, retries, and server routing create peaks well above the average.

### 3.2. Deriving a Concurrency Budget from the Latency Budget

An API has a 200 ms p95 SLO, and non-DB logic consumes 80 ms. Roughly **120 ms** remain for waiting + MongoDB work:

~~~text
HTTP SLO p95:           200 ms
  Auth/validation:        20 ms
  Business/network:       60 ms
  DB selection/queue/run: 120 ms
~~~

Do not configure `waitQueueTimeoutMS=30s` on an HTTP request with a 200 ms SLO without reason; the client will time out long before the DB pool hands over a connection. **Deadlines must propagate end-to-end.**

### 3.3. Service Capacity and Queue Growth

If the DB sustains 500 operations/second while the app sends 800 operations/second:

\[
\Delta Q/\Delta t \approx 800 - 500 = 300 \ \text{operations/second}
\]

After 10 seconds, roughly ~3,000 operations are queued **if there is no admission/rejection and arrival rate stays constant**. Queue latency spikes; clients time out and retry, pushing the incoming rate even higher. This is an **overload feedback loop**.

### 3.4. Why Is 100% Utilization Dangerous?

With variable arrivals and service times, as utilization \(\rho\) approaches 1, wait times climb sharply in standard queueing models. **Never** design a system expecting DB CPU at 100% or the connection pool at 100% checked-out continuously and call that "optimal."

Heuristics like "keep utilization below 70–80%" are **starting points for measurement**, not MongoDB constants. Real workloads have skewed query durations, I/O, locks, and scheduling; pick thresholds via load tests and p95/p99 SLOs.

### 3.5. M/M/c Is a Model, Not Real MongoDB

An \(M/M/c\) queue model (Poisson arrivals, exponential service, \(c\) servers) illustrates the capacity–wait relationship. However, MongoDB exhibits **long-tailed** query durations, cache effects, indexes, replication, and shared resources; \(c\) does not necessarily equal `maxPoolSize`.

Therefore **do not** assume "pool 100 ⇒ 100 completely independent parallel queries" and plug it into an M/M/100 formula to size production. Use models to reason about trends, and **benchmark to pick real numbers**.

### 3.6. Throughput Differs from Concurrency

| Term | Example | Unit |
|---|---|---|
| Arrival rate | API receives 1,000 requests/s. | req/s |
| Completed throughput | DB completes 600 operations/s. | op/s |
| In-flight | 80 commands waiting or running. | operations |
| Pool occupancy | 50 connections currently checked out. | connections |
| Queue depth | 200 tasks awaiting a permit. | tasks |
| Latency p95 | 95% of requests complete within ≤250 ms. | milliseconds |
| Utilization | CPU at 75% or pool 90% in-use. | % |

**These metrics do not substitute for each other.** Watching only connection counts and throughput misses queue depth and tail latency.

## 4. How Does the MongoDB Java Driver Connection Pool Work?

Per current MongoDB Java Sync Driver documentation, **each `MongoClient` maintains one connection pool per server** in the topology it communicates with. Connections are opened **on demand**, checked out when an operation needs transport, and returned for reuse.

### 4.1. Per-Server Pools, Not One "Cluster-Wide Bucket"

Suppose a replica set has 3 members and one client:

~~~text
                     One MongoClient
                       |
           +-----------+-----------+
           |           |           |
           v           v           v
        Primary      Secondary1  Secondary2
         Pool P        Pool S1     Pool S2
       maxSize=100   maxSize=100 maxSize=100
~~~

`maxPoolSize=100` is a **per-server pool limit**, not necessarily 100 TCP sockets across the whole cluster. With default `primary` read preference, reads and writes hit the primary, while secondary pools stay small or open zero operation sockets until used.

The driver also maintains **monitoring sockets** for topology discovery—typically **two extra sockets per server** per current Java Driver docs—which do not count against `maxPoolSize` for application operations.

### 4.2. Connection Scaling When Scaling Pods Horizontally

If 20 application pods each run 1 `MongoClient` with `maxPoolSize=100`, and most operations hit the primary:

\[
20 \times 100 = 2{,}000
\]

That is the **potential ceiling of application connections to the primary**, **not the guaranteed open count**. Monitoring sockets, admin clients, backup agents, and other services add on top.

If each pod mistakenly creates **5 separate `MongoClient` instances**, the ceiling multiplies:

\[
20 \text{ pods} \times 5 \text{ clients/pod} \times 100
= 10{,}000 \text{ app connections to one server}
\]

This is a **configuration ceiling**, not necessarily 10,000 active commands; still, opening excessive connections consumes file descriptors, RAM, and TLS/auth handshake CPU.

### 4.3. Sharded Clusters with Multiple `mongos` Routers

If a `MongoClient` connects to 3 `mongos` endpoints, it maintains a **separate pool to each router**. `maxPoolSize=100` allows up to 100 pooled connections **per router** for that client, not 100 split across 3 routers.

Behind the routers, queries still route to specific shards. Adding app-to-`mongos` connections will not relieve a hot shard if the shard key or query pattern concentrates traffic on one shard.

### 4.4. Load Balancers, SRV, and DNS

With Atlas `mongodb+srv://...` URIs or load-balanced topologies, visible endpoints and pooling/routing depend on driver and deployment configuration. Do not multiply hostnames in a URI naively to predict physical `mongod` sockets. **Check real driver pool metrics and server-side connection counts**, alongside load balancer metrics.

### 4.5. An Open Connection Is Not Necessarily an Active Connection

Common connection states:

- **Created/open:** TCP/TLS/authenticated socket exists.
- **Idle/available in pool:** No operation currently uses it; ready for immediate checkout.
- **Checked out / in use:** Borrowed by an operation; may be sending a command, receiving a response, or waiting elsewhere in its lifecycle.
- **Connecting:** Currently opening/handshaking; bounded by `maxConnecting`.
- **Checkout waiting:** Operation waiting for an available connection.
- **Closed/cleared:** Socket closed due to idle/max lifetime, network error, stepdown, or pool clear.

Never treat server `connections.current` as equivalent to **checked-out** connections in the Java Driver; a server can hold thousands of idle connections while queries crawl due to DB saturation.

## 5. Key Connection Pool Parameters

Current MongoDB Java Sync Driver 5.x documentation describes:

| Setting | Meaning | Default Noted in Java 5.x Docs | Impact |
|---|---|---|---|
| `maxPoolSize` / `maxSize()` | Max pooled connections **per server** | 100 | Caps concurrent operations checking out from that pool |
| `minPoolSize` / `minSize()` | Minimum pooled connections maintained per pool semantics | 0 | Can keep pool warm; increases idle connections |
| `maxConnecting` / `maxConnecting()` | Max connections **opening concurrently** per pool | 2 | Throttles pool ramp-up on cold starts and bursts |
| `maxIdleTimeMS` | Max idle time before closing a pooled connection | 0 (unlimited) | Prevents stale idle sockets; shrinks idle footprint |
| `maxLifeTimeMS` | Max lifetime for a pooled connection | 0 (unlimited) | Proactively recycles connections; causes churn if too low |
| `waitQueueTimeoutMS` / `maxWaitTime()` | Max wait time for an available connection | Java 5.x docs note 2 min; **deprecated** with CSOT | Bounds legacy checkout wait time |

**Note on defaults:** The MongoDB **Server Manual** documents general driver-level defaults that can differ from **Java Driver** docs; verify against your **exact running driver version**. Specifically, when **CSOT `timeoutMS`** is set, several legacy timeouts (including `waitQueueTimeoutMS`) are ignored/overridden per Java Driver docs. Never assume two timeouts add together or that the smaller one always wins.

### 5.1. `maxPoolSize`: Do Not Size Solely from HTTP Thread Counts

Suppose an app has 250 HTTP worker threads, yet on average only 20 threads touch the DB at once because the rest wait on external APIs or compute. `maxPoolSize=250` may be unnecessary. Conversely, 50 async workers can generate 200 in-flight MongoDB operations if each request fans out parallel queries.

Choose `maxPoolSize` from **measured checked-out concurrency, checkout wait, tail latency, and server capacity**, not a rigid 1:1 copy of thread counts.

### 5.2. `minPoolSize`: Do Not Assume "Always Immediately Open N"

`minPoolSize` instructs the driver to maintain a minimum number of connections via background pool lifecycle maintenance; it does not guarantee all sockets are instantly warm the millisecond a pod starts. Setting `minPoolSize=100` across 100 pods can trigger a **connection storm on deployment**.

Applications should use **controlled readiness gates and warm-ups** rather than forcing all pods to race opening hundreds of TLS sockets at once.

### 5.3. `maxConnecting`: Cold Starts and Reconnect Storms

Per MongoDB specs, default `maxConnecting=2` limits **concurrent connection establishments per pool**. Even with `maxPoolSize=100`, if an empty pool suddenly receives 100 operations, it will not open 100 sockets simultaneously; only a bounded number establish in parallel.

Raising `maxConnecting` speeds up pool warm-up **at the cost of** higher TLS/auth handshake CPU and reconnect-storm risk. Adjust **cautiously** while watching both driver and server metrics.

### 5.4. `maxIdleTimeMS` and Idle Connections Through Firewalls

A firewall or NAT gateway may silently drop idle TCP sockets after 5 minutes. If the driver retains idle sockets for 30 minutes, the next request after a quiet period hits a stale socket. Set `maxIdleTimeMS` shorter than network/proxy idle timeouts and measure reconnect cost. Avoid setting it so low that sockets churn continuously and waste TLS CPU.

### 5.5. `maxLifeTimeMS` and Synchronized Recycling

Too short a max lifetime makes the driver recycle sockets constantly under high traffic. If pods restart together, recycling synchronizes into churn spikes that hurt tail latency. Always track **connection created/closed rates**, not just active counts.

### 5.6. `waitQueueTimeoutMS` Does Not Cap Queue Length

A connection checkout timeout **does not** cap how many callers can queue up. If 10,000 operations enter checkout at once with a 120-second timeout, thousands of threads/futures pile up, consuming RAM and retaining request contexts.

To bound queue depth, enforce **admission control / bounded worker queues** at the application layer. In Java 5.x, evaluate end-to-end **`timeoutMS`** rather than relying solely on legacy `waitQueueTimeoutMS`.

### 5.7. A Small `maxPoolSize` Does Not Replace a Queue Policy

A 10-connection pool ensures no more than ~10 operations hold checked-out sockets simultaneously, yet if 50,000 threads wait 2 minutes for checkout, the JVM still OOMs. Pool caps limit transport concurrency; **rejection, timeouts, and queue depth must still be enforced explicitly**.

## 6. Choosing the Right `MongoClient` Lifecycle

### 6.1. One Shared `MongoClient` per Service

**Classic mistake:**

~~~java
// BAD: creating a MongoClient per HTTP request.
public Document getOrderBad(String id) {
    try (MongoClient c = MongoClients.create(mongoUri)) {
        return c.getDatabase("shop")
            .getCollection("orders")
            .find(Filters.eq("_id", id))
            .first();
    }
}
~~~

Every call creates topology monitors, connection pools, handshakes, and TLS/auth sessions only to tear them down immediately; at 500 req/s, sockets, CPU, and churn explode.

**Recommended:** maintain a long-lived, thread-safe `MongoClient` scoped to the application lifecycle:

~~~java
public final class MongoResources implements AutoCloseable {
    private final MongoClient client;
    private final MongoCollection<Document> orders;

    public MongoResources(String uri) {
        this.client = MongoClients.create(uri);
        this.orders = client.getDatabase("shop")
            .getCollection("orders");
    }

    public Document getOrder(String id) {
        return orders.find(Filters.eq("_id", id)).first();
    }

    @Override
    public void close() {
        client.close();
    }
}
~~~

*Example assumes imports for `com.mongodb.client.MongoClient`, `MongoClients`, `MongoCollection`, `org.bson.Document`, and `com.mongodb.client.model.Filters`.* In Spring Boot, let DI manage a singleton `MongoClient` bean and close it on shutdown—never instantiate clients inside controllers.

### 6.2. When Multiple Clients Are Valid

You may maintain **two purposeful `MongoClient` instances** (e.g., latency-critical orders vs. background analytics) with separate pool/timeout budgets, or connect to **genuinely separate clusters**. That implements **client/pool-level bulkheads**, though you must still sum **total connection budgets**.

Never create a dedicated client per tenant or per request unless an extraordinary architectural constraint justifies the cost; multi-tenancy relies on logical auth/filters and admission fairness, not thousands of pools.

### 6.3. `MongoClient` Is Thread-Safe; Sessions Must Not Be Shared Arbitrarily

`MongoClient` is designed to be shared across threads. **`ClientSession`** has its own lifecycle and must not be passed concurrently across arbitrary parallel tasks; the Java Driver does not support concurrent operations sharing **the same `ClientSession`** as a general thread-safe object.

With transactions, each operation sequence holds its session and timeout, and **transactions hold resources longer** than single queries. Watch pool metrics to see the impact of long transactions.

### 6.4. Do Not Forget Shutdown

During graceful shutdown:

1. Flip readiness to stop accepting new requests.
2. Drain in-flight operations within a deadline.
3. Cancel tasks exceeding the drain deadline per framework/driver semantics.
4. Close `MongoClient` and executors after workers finish or time out.

Closing `MongoClient` **per request** is wrong, yet **never closing it** across complex process lifecycles or classloader reloads can also leak sockets and threads.

## 7. Timeouts: Distinguishing Five Different Mechanisms

A request can fail due to **no available server**, **no available connection**, **TCP connect failure**, **slow server query**, or **overall deadline expiration**. Lumping them all together as "MongoDB timeout" leads to the wrong remediation.

| Timeout Option | Core Scope | Key Takeaway |
|---|---|---|
| `serverSelectionTimeoutMS` | Driver waiting to pick a suitable server (primary/secondary/mongos) | Can fail even with idle pooled sockets if no eligible primary exists |
| `connectTimeoutMS` | Opening a TCP connection | Not the wait time to borrow an idle pooled socket |
| `waitQueueTimeoutMS` or Java `maxWaitTime()` (legacy) | Waiting for an available pooled connection | Does not cap queue depth; ignored/overridden when CSOT is active |
| `socketTimeoutMS` (legacy) | Network send/receive wait per socket semantics | Not a clean tool for capping server execution duration |
| `maxTimeMS` | Server-side execution cap on supported operations | Excludes app queue/pool wait; not an exact millisecond hard kill |
| `timeoutMS` (CSOT in modern Java 5.x) | **Client-side operation deadline**, covering selection, checkout, and execution | Experimental; when set, legacy timeouts may be ignored per docs |

### 7.1. Server Selection Differs from Pool Checkout

Example error:

~~~text
Timed out after 30000 ms while waiting for a server
that matches ReadPreferenceServerSelector{readPreference=primary}
~~~

The driver could not find a valid primary. Raising `maxPoolSize` **will not help**; check replica set elections, network, SDAM, auth, or DNS. Conversely, a pool checkout timeout means server selection succeeded yet **no pooled socket became free in time**.

### 7.2. Connection Establishment Differs from Connection Reuse

`connectTimeoutMS` applies when opening a new socket, covering network establishment per driver semantics. If server selection succeeds and the pool has 100 healthy idle sockets, operations check out immediately without opening new sockets.

During cold starts, `maxConnecting` caps parallel socket creation, so checkout wait can rise even when `maxPoolSize` has not been reached.

### 7.3. `maxTimeMS` Does Not Cover the Full HTTP Deadline

~~~javascript
// Example limiting server execution time for find.
db.orders.find({ tenantId: "A", status: "OPEN" }).maxTimeMS(500)
~~~

`maxTimeMS` is a server-side execution limit; it **excludes** HTTP queues, application semaphores, and driver pool checkout wait. MongoDB checks interruption points periodically rather than guaranteeing exact millisecond preemption.

Do not set a tiny `socketTimeoutMS` as a substitute for `maxTimeMS`; the client can sever the socket while the server keeps running/cleaning up, triggering retries and connection churn.

### 7.4. CSOT: Overall Deadline in Java Driver

MongoDB Java Sync Driver 5.x docs describe **Client-Side Operation Timeout (CSOT)** via `timeoutMS` / `MongoClientSettings.Builder.timeout()`. It spans:

~~~text
Start MongoDB operation
  |
  +-- server selection
  +-- connection checkout / possible connection creation
  +-- command execution and response
  |
  v
Deadline timeoutMS
~~~

Example:

~~~java
MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(mongoUri))
    .timeout(500L, TimeUnit.MILLISECONDS)
    .build();

MongoClient client = MongoClients.create(settings);
~~~

**Note:** CSOT is currently documented as **experimental** in Java Driver docs; check exact syntax, version compatibility, and inheritance rules. Do not copy this snippet into Java 4.x expecting `timeout()` to compile.

### 7.5. CSOT vs. Legacy Timeout Options

Per Java 5.x docs, when `timeoutMS` is set, legacy timeouts such as `waitQueueTimeoutMS`, `socketTimeoutMS`, `wTimeoutMS`, `maxTimeMS`, and `maxCommitTimeMS` may be **ignored** per CSOT rules. Thus a URI like:

~~~text
mongodb://host:27017/?timeoutMS=500&waitQueueTimeoutMS=10000
~~~

must not be read as "wait up to 10s in pool, 500ms total." Client-level `timeoutMS` governs the operation deadline per docs, overridable at database, collection, operation, or transaction scope. **Check docs for your exact driver version.**

If not using CSOT, legacy timeouts still work, yet they must align consistently with your **HTTP request deadline** and application admission timeout.

### 7.6. Application-Layer Timeouts

~~~text
HTTP deadline:          1,000 ms
  admission wait:         100 ms maximum
  MongoDB operation:      500 ms maximum
  transform/response:     100 ms
  reserve/retry margin:   300 ms
~~~

This is an **illustrative budget**. If a request already waited 700 ms in the HTTP queue, you cannot hand a full 500 ms budget to MongoDB and still keep a 1,000 ms HTTP SLA. Propagate **remaining deadline** downstream and reject early once budget runs out.

### 7.7. A Timeout Does Not Prove the Operation Rolled Back

A client timeout can occur after the server **committed a write** if the response packet was delayed or lost (especially during network partitions or elections). For writes, **never blindly retry** assuming "timeout => not written."

Use:

- Retryable writes/transactions where supported by driver and operation.
- Stable idempotency keys or unique business identifiers.
- Status checks when outcomes are ambiguous.
- No unbounded retries when the server is overloaded.

Admission control bounds **attempt counts**, while idempotency protects **business semantics**.

## 8. Configuring Java Sync Driver 5.x Within a Resource Budget

Consider a service with 4 application instances and a replica set. Pick **starting values to benchmark**, not universal defaults:

~~~text
App instances:     4
MongoClient/pod:   1
Pool max per node: 64
Pool min per node: 4
maxConnecting:     4
Connection idle:   30 s
Operation CSOT:    750 ms
~~~

If most traffic hits the primary, **the application connection ceiling to the primary is ~4 × 64 = 256** (excluding monitors and other clients). That does not mean the primary runs 256 active queries continuously.

### 8.1. Direct Java Configuration

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import java.util.concurrent.TimeUnit;

public final class MongoClientFactory {

    public static MongoClient create(String uri) {
        MongoClientSettings settings = MongoClientSettings.builder()
            .applyConnectionString(new ConnectionString(uri))
            .applicationName("orders-api")
            .applyToConnectionPoolSettings(pool -> pool
                .maxSize(64)
                .minSize(4)
                .maxConnecting(4)
                .maxConnectionIdleTime(30, TimeUnit.SECONDS)
            )
            // Java Driver 5.x CSOT: check exact version and support.
            .timeout(750L, TimeUnit.MILLISECONDS)
            .build();

        return MongoClients.create(settings);
    }
}
~~~

This example uses modern Java Driver `timeout()` and injects the URI from secure config—never hardcode credentials. On Java Driver 4.x or without CSOT, configure legacy options deliberately rather than mixing both timeout models unintentionally.

### 8.2. URI Instead of Builder

~~~text
mongodb://mongohost:27017/?appName=orders-api&maxPoolSize=64&minPoolSize=4&maxConnecting=4&maxIdleTimeMS=30000
~~~

Add `timeoutMS=750` when the driver version supports CSOT and you choose it. With Atlas `mongodb+srv`, never use placeholder `mongohost` outside labs; keep required TLS and auth parameters.

### 8.3. Spring Boot and Framework Ownership

In Spring Boot / Spring Data MongoDB, let dependency injection manage **one singleton `MongoClient` bean** via `spring.data.mongodb.uri` or a configuration class, rather than constructing clients in repositories or services. Example config:

~~~yaml
spring:
  data:
    mongodb:
      uri: "mongodb://db-host:27017/shop?maxPoolSize=64&maxConnecting=4"
~~~

This is an **illustrative Spring Boot snippet**, dependent on starter version. Store Atlas URIs with credentials in a secret store rather than committing secrets to YAML. If customizing via `MongoClientSettingsBuilderCustomizer`, verify **auto-configuration precedence** so you do not accidentally instantiate two `MongoClient` instances.

### 8.4. Separate Pools per Workload Class

Instead of sharing one pool across all traffic, isolate workloads:

~~~text
HTTP orders API:
  MongoClient A
  maxPoolSize 50
  admission limit 40
  short timeout

Background analytics:
  MongoClient B
  maxPoolSize 10
  admission limit 4
  longer timeout
~~~

This creates a **bulkhead** so reporting never starves orders API pool checkouts. The trade-off is **two clients × per-server pools per JVM**, so budget total connections and close both on shutdown. **Separate client pools alone do not isolate server CPU**; analytics queries still share DB IOPS/cache and need query tuning, scheduling, or cluster-tier isolation.

### 8.5. Calculate Connection Budgets Before Increasing Pools

An architectural worksheet:

| Variable | Hypothetical Value |
|---|---:|
| Pods | 12 |
| `MongoClient`s/pod | 2 |
| `maxPoolSize`/client/server | 80 |
| Max app connections to **one server** if both clients hit it | 1,920 |
| Monitoring sockets and other clients | Additional above this cap |

\[
12 \times 2 \times 80 = 1{,}920
\]

If the cluster enforces or recommends a lower connection cap, this setup is risky even though **each pod** looks like "only 80." As autoscaling scales pods from 12 to 40, the cap multiplies; enforce a **global connection budget** and app-level admission limits.

## 9. Admission Control: Proactively Capping In-Flight DB Operations

An **admission gate** in front of MongoDB ensures at most \(C\) concurrent operations enter the DB path. Excess requests either **wait briefly within bounds** or **fail fast**. That beats letting 5,000 requests pile up inside the connection pool.

### 9.1. Bounded Admission Diagram

~~~text
Incoming HTTP traffic
      |
      v
   Queue cap Q=80
      |
      +--- full? --> HTTP 429/503 / Retry-After / degrade
      |
      v
   Permits C=40
      |
      v
MongoDB driver
  Pool maxSize=64
      |
      v
 MongoDB server
~~~

If the gate caps at 40 and each operation holds at most one connection at a time, checked-out sockets from this path stay ≤ ~40. **However**, a single request might spawn parallel DB calls, cursors/transactions can hold sockets longer, and other traffic bypasses the gate—define control boundaries before doing naive arithmetic.

### 9.2. Semaphore in a Java Sync Driver Service

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public final class BoundedOrderLookup {
    private final MongoCollection<Document> orders;
    private final Semaphore permits = new Semaphore(32, true);

    public BoundedOrderLookup(MongoCollection<Document> orders) {
        this.orders = orders;
    }

    public Document findById(String id) throws InterruptedException {
        // Wait at most 50 ms for local admission.
        boolean admitted = permits.tryAcquire(50, TimeUnit.MILLISECONDS);
        if (!admitted) {
            throw new OverloadedException("MongoDB lookup at capacity");
        }

        try {
            return orders.find(Filters.eq("_id", id))
                .maxTime(400, TimeUnit.MILLISECONDS)
                .first();
        } finally {
            permits.release();
        }
    }

    public static final class OverloadedException extends RuntimeException {
        public OverloadedException(String message) { super(message); }
    }
}
~~~

**Meaning:** at most 32 concurrent calls execute inside this instance's MongoDB path, and callers wait at most 50 ms for a permit. `Semaphore(32, true)` aims for FIFO fairness yet **does not bound how many threads can wait on `tryAcquire` simultaneously**. You still need HTTP/request limits or a bounded executor outside so 100,000 callers do not pile up waiting 50 ms.

### 9.3. Difference Between `maxTime` and CSOT

In the snippet above, `.maxTime(400, TimeUnit.MILLISECONDS)` caps server execution time for `find`; connection checkout wait still depends on driver timeouts. When using **CSOT** (Java 5.x), pick an overall deadline aligned with the request budget rather than assuming `maxTime` bounds admission + checkout.

### 9.4. Permit Scope Must Cover the Whole Operation

If code does:

~~~java
permits.acquire();
MongoCursor<Document> cursor = collection.find(filter).iterator();
permits.release();
while (cursor.hasNext()) {
    consume(cursor.next());
}
~~~

the permit is released **before the cursor is actually consumed**, defeating the concurrency gate. For long/streaming cursors:

- Close cursors reliably with try-with-resources.
- Hold the permit while the task actively consumes DB resources.
- Enforce page/batch sizes and total deadlines.
- Avoid holding permits while a slow downstream consumer stalls; switch to bounded paging or buffering.

### 9.5. Semaphore Fairness Has a Cost

Fairness `true` reduces starvation yet adds scheduling overhead and can hurt throughput in certain workloads. Do not guess: measure per-tenant/priority tail latency and retry behavior. When QoS matters for critical requests, **bulkheads and priority queues** are clearer than one global fair semaphore.

## 10. Bounded Queues and Backpressure: Controlled Rejection

A semaphore caps **running tasks**, yet an unbounded queue in front of it still OOMs the JVM. Production designs must bound **running + waiting tasks** and specify overflow behavior.

### 10.1. Unbounded Queues Are an Anti-Pattern

~~~java
// NOT RECOMMENDED for workloads with sudden traffic spikes:
ExecutorService executor = Executors.newFixedThreadPool(32);
~~~

`Executors.newFixedThreadPool(32)` uses an **unbounded work queue** behind 32 threads. When 50,000 tasks arrive faster than completion, the queue grows without bound, triggering heap pressure, GC pauses, and cascading timeouts.

**A bounded thread pool does not mean a bounded queue.**

### 10.2. Bounded `ThreadPoolExecutor`

~~~java
import java.util.concurrent.*;

ThreadPoolExecutor dbExecutor = new ThreadPoolExecutor(
    16,                         // corePoolSize
    16,                         // maximumPoolSize
    0L,
    TimeUnit.MILLISECONDS,
    new ArrayBlockingQueue<>(64), // Queue cap 64
    new ThreadPoolExecutor.AbortPolicy() // Fail fast on saturation
);
~~~

When 16 tasks run and 64 sit queued, the 81st task fails immediately with `RejectedExecutionException` instead of piling up indefinitely. The controller/service should **map overload exceptions** into deliberate HTTP responses, increment metrics, respect deadlines, and never return internal stack traces to users.

### 10.3. Do Not Accidentally Block HTTP Threads Unboundedly

~~~java
// Pseudocode for a request handler using a dedicated executor:
try {
    Future<Document> job = dbExecutor.submit(
        () -> orders.find(Filters.eq("_id", orderId)).first()
    );
    return job.get(500, TimeUnit.MILLISECONDS);
} catch (RejectedExecutionException overloaded) {
    // Translate to 503 Service Unavailable or 429 with retry policy.
    throw new ServiceOverloadedException();
} catch (TimeoutException tooSlow) {
    // Timeout HTTP waiting; cancellation is best effort.
    job.cancel(true);
    throw new ServiceDeadlineException();
}
~~~

**Note that this is pseudocode, not complete compilable Java:** `job` would need to be declared outside `try` to be referenced in `catch`, and checked exceptions/cleanup must be handled in real code. The lesson is **never let a request outlive its deadline simply because it entered a queue**.

Even a bounded executor still ties up the calling HTTP thread during `Future.get`. For I/O-heavy APIs, consider async stacks or ingress admission (load balancer / API gateway) while keeping **bounded in-flight operations**.

### 10.4. Is `CallerRunsPolicy` Good?

`CallerRunsPolicy` forces the submitting thread to run the task when the queue is full, applying backpressure by slowing the caller. However, on an HTTP servlet thread, it **blocks the request thread too long**, starving the ingress pool; in event-loop/reactive apps, **running a blocking DB call on the event loop** is catastrophic.

Do not pick `CallerRunsPolicy` just because it "never drops requests." Under short deadlines and heavy spikes, **failing fast** protects the overall system far better.

### 10.5. Bounded Queues Do Not Always Have to Be FIFO

FIFO is simple yet insufficient when:

- One tenant submits thousands of reports while another just views a single order.
- 10-second background jobs sit ahead of 30 ms login requests.
- Continuous retries crowd out fresh requests.

Use **per-tenant caps, priority classes, separate short/long queues, quotas, or weighted fair queuing**. Guard against starvation: strict priority must not starve lower-priority work forever.

### 10.6. Sizing Queue Length from a Wait Budget

A simple estimate: if a service processes \(\mu=100\) operations/second and tolerates **at most 0.1 s average queue wait**, average queue depth should stay near or below:

\[
Q \approx \mu \times W_q = 100 \times 0.1 = 10
\]

This is a **heuristic from Little's Law**, not a p95 latency guarantee. Under bursty arrivals and variable service times, even a queue of 10 can make requests wait over 100 ms. Enforce **queue wait timeouts** and measure percentiles rather than relying on \(Q\) alone.

### 10.7. Policies When the Queue Is Full

| Response | When Appropriate | Risk |
|---|---|---|
| Return `HTTP 429` | Client exceeded quota/rate limit and may retry later | Retry storms without `Retry-After`/jitter |
| Return `HTTP 503` | Service overloaded / temporarily unable to serve | Needs proper health/alerts so LBs do not drain healthy pods needlessly |
| Graceful degradation | Skip secondary enrichment/reports, serve cached/minimal data | Stale data; requires clear SLA/freshness contract |
| Short bounded queue with timeout | Brief spikes while service retains headroom | Overly deep queues inflate tail latency |
| Offload to async job | Reports/exports not needing synchronous response | Needs durable queue, idempotency, job status API |
| Drop non-critical telemetry | Business permits sampling loss under load | Never apply to payments or orders |

### 10.8. Rejections Require Observability

For `ThreadPoolExecutor`, monitor at minimum:

- `getActiveCount()` — approximate active worker threads.
- `getQueue().size()` — current queue depth.
- `getCompletedTaskCount()` — completed tasks.
- `getTaskCount()` — total scheduled tasks.
- **Rejected tasks** counter via a custom `RejectedExecutionHandler` and metrics.
- Queue wait latency and execution time (measured separately).

Never rely on a single point-in-time snapshot; inspect p95/p99 time series during peaks.

## 11. Bulkheads: Isolating Workloads So One Pool Is Not Exhausted

A MongoDB cluster typically serves mixed workloads: fast point lookups, order updates, dashboard aggregations, exports, backfills, and long transactions. Sharing one gate, one queue, and one pool lets one heavy job starve the entire API.

### 11.1. Two-Tier Service Example

~~~text
                    MongoDB Cluster
                       |
          +------------+-------------+
          |                          |
          v                          v
  Interactive API                 Reporting Jobs
  - gate=40                       - gate=4
  - queue=40                      - queue=8
  - pool=64                       - pool=12
  - deadline=500ms                - deadline=20s
  - high priority                 - low priority
~~~

Numbers are illustrative. Separating gates and pools prevents reports from consuming API connections; **however, both still share DB CPU, cache, and disk** on the same cluster. Very heavy reporting requires scheduling, index/materialized-view design, or **cluster/shard-tier workload isolation** beyond client-side pools.

### 11.2. Per-Tenant Quotas

One tenant sending 10,000 req/s must not starve 100 other tenants completely. Consider:

~~~text
Global in-flight cap:       120
Per-tenant in-flight cap:    12
Per-tenant rate limit:       negotiated by plan
Reserved critical capacity:  20
~~~

However, across multiple **application instances**, a local cap of 12 per pod is not a global cap of 12. Across 20 pods, one tenant could hold up to 240 in-flight requests. To enforce a **global quota**, use an API gateway/load balancer, distributed token buckets, or coordination resilient to partitions/failures.

### 11.3. Weighted Fair Queuing and Starvation

When multiple tenants share resources:

- Partition by tenant/priority class with weighted quotas.
- Enforce hard deadlines on stale queued tasks.
- Prevent indefinite starvation of low-priority work.
- Reserve capacity for health checks, auth, and critical writes.
- Bound tenant/report query complexity, not just raw request counts.

If a report burns 20 seconds of server CPU while a lookup takes 10 ms, rate-limiting strictly by **requests/second** ignores true cost. Consider **cost-aware admission** (estimated query complexity or compute budgets).

### 11.4. Do Not Over-Fragment Pools

Creating a separate `MongoClient` per endpoint, tenant, or HTTP request multiplies pools and monitoring sockets by \(N\), flooding the cluster with idle sockets and handshakes. **A few intentional bulkheads** beat thousands of client instances.

### 11.5. Implementing Fairness in Java

A straightforward pattern:

- Global gate (e.g., 80 permits).
- Per-tenant gate (e.g., 8 permits) managed with LRU eviction for inactive tenants.
- Dedicated background reporting gate (e.g., 4 permits).
- Upon arrival, **acquire permits in a fixed order**, releasing any acquired permits immediately if a later acquire fails.
- Place a bounded queue and deadline at ingress.

Never hold a global permit while **waiting seconds** for a saturated tenant's permit—that lets one saturated tenant block global capacity. Use deliberate acquire ordering or non-blocking try-acquire with rollback.

## 12. Rate Limiting Differs from Concurrency Limiting

### 12.1. Two Mechanisms Protecting Against Two Different Risks

A **rate limiter** caps arrivals over time (e.g., 100 req/s). A **concurrency limiter** caps simultaneous in-flight executions (e.g., 20 operations).

A 100 req/s rate limit does not prevent 100 requests from **arriving in the same 10 ms** (if burst tokens allow). A concurrency cap of 20 does not stop an abusive tenant from blasting 10,000 requests/s that all get rejected, burning ingress and logging CPU.

Usually you need **both**:

~~~text
Ingress rate limit / token bucket
           |
           v
Deadline-aware bounded queue
           |
           v
Concurrency limiter / bulkhead
           |
           v
MongoDB driver pool
~~~

### 12.2. Token Bucket

A token bucket with capacity \(B\) and refill rate \(r\) tokens/s:

- Each request consumes a token.
- When tokens are available, brief bursts are permitted.
- When empty, requests wait briefly within bounds or are rejected.
- Counting 1 token per **request** ignores query cost; weight tokens by endpoint or query class when needed.

For instance, `r=100 req/s, B=200` allows a 200-request burst before settling to 100 req/s. If each request launches 3 concurrent MongoDB operations, DB load far exceeds the HTTP request rate.

### 12.3. Adaptive Concurrency Control

A static cap \(C=40\) may be suboptimal as query mixes shift. **Adaptive concurrency** adjusts \(C\) within guardrails using latency and queue signals:

~~~text
If latency is low, errors are low, DB has headroom:
  increase C slowly.

If p95/p99, queue wait, timeouts rise:
  decrease C faster, enable load shedding.

Keep C within [C_min, C_max].
~~~

This is a control-loop strategy, not "drop everything whenever p95 twitches." Latency can rise from network issues, missing indexes, failovers, or downstream services; diagnose bottlenecks and dampen oscillations.

### 12.4. Autoscaling Can Worsen Overload

Suppose the DB is saturated, yet HPA scales pods from 10 to 30 due to high HTTP CPU. Every new pod opens pools and pushes more parallel requests; the database **gains zero extra capacity** and latency collapses further.

In this situation:

- Scaling the app only helps **application-bound** bottlenecks.
- DB-bound workloads require global admission budgets and database tuning.
- Scale MongoDB compute, sharding, or indexes when genuinely needed.
- Throttle pod startup to prevent connection storms.

**HPA and pool limits must be co-designed**, especially when autoscaling on request count.

## 13. Java Reactive/Async and Virtual Threads: No "Free Concurrency"

### 13.1. Async I/O Does Not Expand MongoDB Capacity

An application using the Java Reactive Streams Driver can manage 10,000 publishers/subscriptions with far fewer worker threads than blocking code. Yet if all 10,000 fire `find()` at the same primary, the server still has to execute thousands of commands.

~~~text
Blocking model:
  N tasks -> N Java threads blocked waiting for DB (up to pool/worker limits)

Reactive/async model:
  N tasks -> small number of event-loop threads
           -> still N in-flight or queued DB operations
~~~

Eliminating blocked OS threads does not give MongoDB more CPU or IOPS. **Reactive stacks still require concurrency caps, bounded buffers, and backpressure.**

### 13.2. Never Call the Sync Driver on an Event-Loop Thread

~~~java
// Illustrative ANTI-PATTERN in a reactive handler:
Mono.fromCallable(() ->
    syncCollection.find(Filters.eq("_id", id)).first()
);
~~~

Wrapping a blocking call in `Mono.fromCallable` does not move execution off the event loop; if subscribed on an event-loop scheduler, it stalls the entire event loop. If you must wrap the Sync Driver inside Reactor, offload to a blocking-I/O scheduler **and cap concurrency**:

~~~java
Mono.fromCallable(() ->
        syncCollection.find(Filters.eq("_id", id)).first()
    )
    .subscribeOn(Schedulers.boundedElastic());
~~~

**Caveat:** Requires appropriate Reactor imports and dependencies; `boundedElastic` bounds thread count yet can still queue tasks, so **never** treat it as a complete backpressure policy. The native approach is using the **Reactive Streams Driver** with explicit concurrency controls.

### 13.3. Bounding `flatMap` Concurrency

~~~java
// Reactor pseudocode using a configured Reactive MongoDB repository:
Flux.fromIterable(orderIds)
    .flatMap(
        id -> repository.findById(id),
        16 // up to roughly 16 inner publishers subscribed concurrently
    );
~~~

`flatMap(..., 16)` caps concurrency **within that single pipeline**, not globally across the service. If 100 HTTP requests run that pipeline concurrently, total inner subscriptions reach ~1,600. Add request/tenant-level gates or a data-access-layer cap for global budgets.

### 13.4. Backpressure Does Not Fix Server Bottlenecks Automatically

Reactive backpressure lets downstream consumers demand items at a sustainable pace, but:

- Already-sent MongoDB commands cannot magically be "unsent."
- Active subscriptions may hold cursors and pull `getMore` batches repeatedly.
- Unbounded `buffer()` or `collectList()` operators pull everything into RAM.
- Unbounded `parallel()` rails can flood writes concurrently.

Use batch/page bounds, `limitRate`/concurrency controls per library semantics, deadlines, and bounded buffers rather than assuming "non-blocking" automatically shields the DB.

### 13.5. Java Virtual Threads

Java virtual threads make **blocking I/O** cheap in thread memory, yet they do not alter:

- MongoDB driver `maxPoolSize`.
- Query execution duration.
- DB CPU, IOPS, locks, or tickets.
- Total queued requests.

10,000 virtual threads waiting on a 100-connection pool are still 10,000 pending tasks (even with lower thread memory overhead than platform threads). **Keep semaphores, bounded queues, and deadlines** even when using virtual threads.

### 13.6. Async Cancellation and Permit Release

When an HTTP client disconnects or times out:

- Propagate cancellation to DB operations where supported by driver/framework.
- Close cursors, subscriptions, and sessions cleanly.
- Release semaphore permits and queue slots on every error/cancel path.
- Guard against double-release when completion and timeout race.
- Prevent expired requests from holding resources indefinitely.

Do not assume `Future.cancel(true)` instantly halts server-side query execution; interruption semantics depend on driver, network state, and server operation. Rely on server/CSOT deadlines and monitor active operations.

## 14. Driver Telemetry: Measuring Connection Checkout Properly

The MongoDB Java Driver emits **Connection Monitoring and Pooling (CMAP)**, **Command Monitoring**, and **Server Discovery and Monitoring (SDAM)** events. These are essential to separate pool wait from server selection and command execution.

### 14.1. Key CMAP Events to Track

| Event / Metric | What It Reflects | Warning Signal |
|---|---|---|
| Pool created/ready/cleared/closed | Per-server pool lifecycle | Frequent pool clears during network/failover events |
| Connection created/ready/closed | Socket establishment and churn | Creation storms or error-driven closes |
| Check-out started | An operation needs a connection | Spike in starts matching traffic |
| Check-out succeeded | Connection borrowed | In-use staying near cap for long periods |
| Check-out failed | Failed to obtain connection | Pool timeout / pool closed / error reason |
| Checked in | Connection returned to pool | Mismatch vs. checkout → suspect leaks/long ops |
| Check-out wait time | Elapsed from started to succeeded/failed | p95/p99 climbs while command duration stays flat |
| In-use connections | Currently checked-out connections | Hitting `maxSize` continuously |

**Distinction:** pool wait occurs **before sending a command**, while command latency measures **after dispatch**. Separating them prevents raising pool sizes when slow queries are actually holding connections too long.

### 14.2. A Simple Java `ConnectionPoolListener`

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.event.ConnectionPoolListener;
import com.mongodb.event.ConnectionCheckedOutEvent;
import com.mongodb.event.ConnectionCheckOutFailedEvent;
import java.util.concurrent.atomic.LongAdder;

public final class PoolMonitoringExample {

    static class PoolCounters implements ConnectionPoolListener {
        final LongAdder checkedOut = new LongAdder();
        final LongAdder checkoutFailures = new LongAdder();

        @Override
        public void connectionCheckedOut(ConnectionCheckedOutEvent event) {
            checkedOut.increment();
        }

        @Override
        public void connectionCheckOutFailed(ConnectionCheckOutFailedEvent event) {
            checkoutFailures.increment();
        }
    }

    public static MongoClient newClient(String uri, PoolCounters counters) {
        MongoClientSettings settings = MongoClientSettings.builder()
            .applyConnectionString(new ConnectionString(uri))
            .applyToConnectionPoolSettings(pool -> pool
                .maxSize(64)
                .addConnectionPoolListener(counters))
            .build();
        return MongoClients.create(settings);
    }
}
~~~

**This example counts cumulative events**, not a full metrics implementation. `checkedOut` tracks **cumulative successful checkouts**, **not current in-use sockets**. To track active in-use counts, decrement in `connectionCheckedIn` or use JMX/gauges. Never label a cumulative counter `inUse` in production dashboards.

### 14.3. JMX Pool Listener

The MongoDB Java Driver ships `JMXConnectionPoolListener` exposing per-server JMX MXBeans with attributes such as:

- `clusterId`, `host`, `port`.
- `minSize`, `maxSize`.
- `size` — current pooled connections.
- `checkedOutCount` — pooled connections currently in use.

Register this listener per MongoDB docs and export via JMX exporter / Micrometer / Prometheus. Never expose unauthenticated remote JMX to the public internet.

### 14.4. `CommandListener` for Execution Timing

The Java Driver provides `CommandStartedEvent`, `CommandSucceededEvent`, and `CommandFailedEvent`. Use them to measure:

- `find`, `aggregate`, `update`, and `insert` commands.
- Command durations and failure rates.
- Query shapes/collections with **PII redacted**, never logging raw payloads by default.
- MongoDB command latency separated from HTTP/queue latency.

**Caution:** Command monitoring does not capture time spent **waiting on admission permits or pool checkout**. Instrument those stages separately with spans and gauges.

### 14.5. SDAM to Explain Server Selection

Observe events during topology shifts:

~~~text
Primary fails
    |
    v
SDAM discovers no eligible primary
    |
    v
Requests wait on server selection
    |
    v
Election/new primary
    |
    v
Pools clear/reconnect, operations retry
~~~

During failover, `serverSelectionTimeoutMS` dominates failures. **Raising `maxPoolSize` cannot conjure a primary**, and aggressive post-election retries can overwhelm the newly elected primary.

### 14.6. A Complete Request Trace

~~~text
traceId=ORD-1001
  HTTP request parse       4 ms
  Auth validation          7 ms
  Admission queue wait    18 ms
  Mongo server selection   2 ms
  Pool checkout wait      34 ms
  MongoDB command         21 ms
  Business transform       5 ms
  HTTP response            3 ms
--------------------------------
  Total                  94 ms
~~~

Hypothetical timings. If `pool checkout` jumps from 34 to 180 ms, investigate pool saturation, churn, or cold starts. If `command` jumps from 21 to 300 ms, investigate indexes, queries, or server resources—raising the pool then will only worsen contention.

### 14.7. Keep Metric Labels Low-Cardinality

Never put `requestId`, `userId`, or raw `queryText` into Prometheus labels—cardinality explodes and exhausts memory/storage. Stick to `service`, `deployment`, `cluster`, `serverAddress` (within bounds), `commandName`, `endpointClass`, and `outcome`; keep `traceId` in tracing/logs with bounded retention.

## 15. MongoDB Server-Side Metrics: Looking Inside the Database

In `mongosh` with server monitoring privileges:

~~~javascript
const admin = db.getSiblingDB("admin")
const status = admin.runCommand({ serverStatus: 1 })

printjson(status.connections)
printjson(status.opcounters)
printjson(status.globalLock)
~~~

`serverStatus` returns many fields, some varying by MongoDB version or Atlas tier. Do not assume every field exists on every cluster, and avoid dumping raw sensitive metrics into public logs.

### 15.1. `connections` Is Not Driver Pool Wait

Per the MongoDB Manual:

- `connections.current`: current incoming connections (app, monitors, and other clients).
- `connections.available`: remaining incoming connections the server can accept under current limits.
- `connections.totalCreated`: cumulative connections created since server startup.
- `connections.active`: incoming client connections with operations currently in progress (version-dependent).
- `connections.rejected`: rejected connections (introduced in specific versions).

A server with `current=2,000` and `active=80` holds mostly **idle sockets**. Never infer CPU/IOPS overload solely from `current`, nor assume the server is healthy solely because `available` looks high.

### 15.2. `globalLock.currentQueue`

~~~javascript
const st = db.getSiblingDB("admin")
  .runCommand({ serverStatus: 1 })

printjson(st.globalLock?.currentQueue)
~~~

`globalLock.currentQueue.readers/writers` reports operations waiting on global locks. **This is not the driver connection checkout queue**, nor does it cover every internal MongoDB queue. If `globalLock.currentQueue` is near zero while app pool checkout p99 climbs, the bottleneck is likely **client-side**, not a global lock.

### 15.3. Admission Queue Metrics in MongoDB 8.0+

MongoDB 8.x manuals describe `serverStatus.queues` metrics for ingress/execution admission, with version-dependent fields like `queues.ingress.normalPriority.queueLength` or `queues.execution.read/write`. Exact additions and semantics vary across patch releases. These expose **server-side queueing**, not Java Driver CMAP checkout waits.

Do not write monitoring assertions requiring `queues.ingressSessionEstablishment` if your cluster has not reached the release introducing those fields (for example, fields added in MongoDB 8.2).

### 15.4. `db.currentOp()` and `$currentOp`

With appropriate permissions, inspect active operations:

~~~javascript
db.getSiblingDB("admin").aggregate([
  { $currentOp: { allUsers: true, idleConnections: false } },
  { $match: { active: true } },
  { $project: {
      ns: 1,
      op: 1,
      secs_running: 1,
      waitingForLock: 1,
      appName: 1,
      command: 1
  }}
])
~~~

**Security warning:** `command` can expose query filters and sensitive data. In production, restrict projections and privileges, and never forward raw output to unsecured destinations. `currentOp` fields vary by version and topology and may require elevated privileges.

### 15.5. Query Profiler and `explain`

When command duration climbs, inspect queries before raising `maxPoolSize`:

~~~javascript
db.orders.explain("executionStats").find({
  tenantId: "tenant-a",
  status: "OPEN"
}).sort({ createdAt: -1 }).limit(20)
~~~

Inspect `totalDocsExamined`, `totalKeysExamined`, index/collection scans, and sort stages. A query scanning 1 million documents to return 20 rows **does not become cheaper** just because the driver opens 100 more TCP sockets.

The profiler carries overhead and privilege constraints; enable carefully with sampling rather than logging every production query indefinitely.

### 15.6. MongoDB Server Tickets Do Not Equal `maxPoolSize`

MongoDB/WiredTiger uses admission/tickets for concurrent read/write operations. Parameter names and tuning mechanisms changed across MongoDB 6.x, 7.x, and 8.x (7.x introduced dynamic ticket tuning). **Never arbitrarily set "storage engine concurrent tickets = pool size"** or tweak internal parameters just to match numbers. Follow release documentation/support and test thoroughly.

### 15.7. Opening More Connections Can Make Outages Worse

Suppose the DB exhibits:

~~~text
High CPU 95%
WiredTiger cache eviction pressure
Slow collection scan
Disk IOPS near limit
~~~

Enlarging the pool sends even more concurrent commands into the server, intensifying contention and **raising command latency**. Fix queries, indexes, data models, or server capacity first, using an admission gate to cap load until the root cause is fixed.

## 16. Connection Storms, Failovers, and Retry Amplification

The worst load spikes often happen not at steady state, but when **the whole fleet reconnects simultaneously** after an outage or deploy.

### 16.1. Cold Start of Dozens of Pods

~~~text
Rolling deploy turns into near-simultaneous restart:

  30 new application pods
    x 1 MongoClient/pod
    x 3 mongos endpoints
    x minPoolSize 20
  = up to 1,800 warm pooled connections intended across routers

  Plus monitoring sockets, admin/services, retries.
~~~

These figures are **ceilings/estimates**, not proof 1,800 sockets open at the exact same millisecond. Still, launching thousands of simultaneous TLS/auth handshakes spikes CPU/network, backs up `maxConnecting` queues, and breaks HTTP readiness checks.

Mitigations:

- **Rolling/canary deploys** rather than restarting all pods at once.
- Rate-limited / jittered warm-up.
- Do not set `minPoolSize` higher than genuinely needed.
- Tune `maxConnecting` conservatively rather than uncapping it.
- Separate liveness from readiness to prevent restart loops.
- Track connection created/closed rates, not just pool size.

### 16.2. Replica Set Primary Election

~~~text
Primary A fails
     |
     +--> Driver SDAM detects topology change
     +--> Pending writes wait for a writable primary
     +--> Pools may clear/reconnect
     +--> New primary B elected
     +--> Backlogged clients retry simultaneously
                |
                v
        Secondary bottleneck becomes new primary bottleneck
~~~

Raising `serverSelectionTimeoutMS` lets requests **wait out** brief elections, yet if the HTTP deadline is 500 ms, waiting 30 seconds is pointless. Conversely, an ultra-short timeout causes high failures during normal elections. Align with **business deadlines**, adding fallback/degradation and jitter.

### 16.3. Retry Storms

Suppose the DB receives 800 ops/s while capacity is 600. If 10% time out and clients immediately retry 3 times, effective arrival rate climbs sharply:

~~~text
Original arrivals:       800 req/s
Retries from timed out:  can add hundreds of req/s
Total DB attempts:       > original rate
~~~

Retries make overload **self-amplifying**. Enforce:

- Retry only **transient/recoverable errors** on **idempotent/retryable operations**.
- Cap attempts and total deadline.
- Apply **exponential backoff with jitter** on client-initiated retries.
- Do not retry when an admission gate explicitly signaled overload.
- Monitor **attempt rate** separately from **original request rate**.
- Add circuit breakers when dependencies are down.

### 16.4. Idempotency for Writes

A `POST /orders` request times out after the server inserts the order, losing the response. If the client retries with a brand-new ID, it creates **two orders**. Use stable `requestId`/`idempotencyKey` fields backed by unique indexes or transactions.

~~~javascript
// Illustrative document pattern with a stable business key.
{
  _id: "ORDER-10001",
  tenantId: "tenant-a",
  requestId: "REQ-abc-20261114",
  status: "CREATED"
}
~~~

Never assume every `updateMany`, aggregate write, or multi-step workflow is automatically safe to retry; consult retryable writes/transactions docs and domain invariants.

### 16.5. Network Partitions and Half-Open Connections

When firewalls/NAT drop idle sockets, the pool retains stale connections. The next checkout hits a network error, clearing the pool and reconnecting. Inspect `connectionClosed` reasons, `maxIdleTimeMS`, `connectTimeoutMS`, server selection timeouts, and network devices instead of raising pool size and ignoring the root cause.

### 16.6. Circuit Breakers vs. Semaphores

| Mechanism | Decision |
|---|---|
| Semaphore / bulkhead | Is there a concurrency permit available right now? |
| Rate limiter | Have arrivals exceeded the allowed rate over a window? |
| Circuit breaker | Is the dependency failing continuously enough to short-circuit calls temporarily? |
| Timeout / deadline | Does enough time remain to finish usefully? |
| Retry / backoff | Should we retry after a transient failure? |
| Cache / fallback | Can we serve degraded results within policy? |

These mechanisms complement rather than replace each other. Opening a circuit breaker does not roll back an already-running MongoDB query; cancellation and cleanup are still needed.

### 16.7. Readiness After Reconnect

Heavy readiness probes (e.g., every pod running a large aggregation every second) pile load onto a recovering cluster. Keep health checks lightweight, never put **expensive real queries** on liveness probes, and avoid killing/restarting pods during brief failovers—which triggers another connection storm.

## 17. Load Testing: Finding the "Knee Point" Instead of One Peak QPS Number

Load testing aims to locate where **throughput begins saturating while latency and rejections surge** (the knee point). That identifies safe budgets and alert thresholds—not the highest unstable QPS right before collapse.

### 17.1. Build a Representative Workload

A realistic API workload mixes operations:

| Operation Class | Hypothetical Share | Characteristics |
|---|---:|---|
| Find order by ID | 55% | Indexed point lookup, fast read |
| Find recent orders | 20% | Equality + sort, needs compound index |
| Create/update order | 15% | Writes / unique keys, `writeConcern` |
| Dashboard aggregate | 8% | Potentially heavy sort/group CPU/IOPS |
| Export/report | 2% | Long cursor reading many batches |

Benchmarking 100% in-RAM `findOne({_id: ...})` never represents a system with aggregations and write contention. Match data size, indexes, document sizes, hot/cold keys, read/write ratios, and shard routing.

### 17.2. Step Up Load Gradually

Example plan:

~~~text
Stage A:  100 req/s for 5 min
Stage B:  200 req/s for 5 min
Stage C:  400 req/s for 5 min
Stage D:  600 req/s for 5 min
Stage E:  800 req/s for 5 min
Cool down and observe recovery
~~~

This is an **illustrative scenario**. Run only in authorized environments with sufficient capacity and guardrails—never stress production without planning. Use stage durations long enough for caches to warm, pools to ramp, GC to settle, and indexes to reach steady state.

### 17.3. Charts to Plot

- Offered arrival RPS and completed RPS on the same timeline.
- HTTP p50/p95/p99 latency and error/timeout rates.
- MongoDB command p50/p95/p99 per operation class.
- Driver checkout wait p95/p99 and checked-out connections.
- Connection created/closed rates and pool clears.
- Executor queue depth, admission in-flight, and reject counters.
- MongoDB CPU/IOPS/cache, active ops, queues, and locks.
- JVM CPU/heap/GC, thread counts, and event-loop lag.
- Retry attempts vs. original requests.

Never watch only p50; p99 can degrade tenfold while p50 barely moves.

### 17.4. Open-Loop vs. Closed-Loop Load Tests

**Closed-loop:** each virtual user waits for a response before sending the next request. When the server slows down, the client automatically slows arrivals, **hiding overload** (coordinated omission). **Open-loop:** the generator dispatches on a fixed arrival schedule, revealing queue growth and rejections under insufficient capacity.

Consider both:

- Open-loop to test overload control and deadline adherence.
- Closed-loop to model interactive user sessions with think time.
- Specify whether metrics record arrival time or completion time.
- Ensure the load generator itself never hits CPU or network saturation.

### 17.5. Finding the Knee Point with Two Metrics

Suppose:

| Incoming RPS | Completed RPS | HTTP p95 | Rejected |
|---:|---:|---:|---:|
| 100 | 100 | 60 ms | 0% |
| 300 | 300 | 75 ms | 0% |
| 500 | 500 | 120 ms | 0% |
| 700 | 620 | 650 ms | 4% |
| 900 | 625 | 2,500 ms | 15% |

**Hypothetical data.** Around 620 completed RPS, throughput flattens while p95 and rejections skyrocket—marking saturation. An admission gate can **keep accepted-request latency bounded** by shedding excess load early, while balancing **availability SLOs** and client retry behavior.

### 17.6. Controlled Grid Testing of Pool and Gate Values

Run a focused test matrix, for example:

~~~text
Pool maxSize:  32, 64, 128
Gate C:        16, 32, 48
Queue Q:       0, 32, 64
~~~

Do not brute-force combinations on production; pick a reasoned subset while holding indexes, corpus, and traffic mix constant. For each cell measure **sustained throughput, p95/p99, error/rejection rates, pool checkout wait, and DB CPU/IOPS**.

### 17.7. Tuning `maxConnecting` Separately

Test cold-start and reconnect scenarios, measuring:

- Time for the pool to reach target occupancy.
- Connection establishment p95/p99.
- Server handshake/TLS/auth CPU.
- Connection creation and rejection rates.
- Impact on request p99 after deploys or failovers.

Higher `maxConnecting` speeds cold ramp-up in some cases yet risks connection storms. Tuning `maxPoolSize` alone does not optimize connection ramp-up.

### 17.8. Always Run Overload and Recovery Tests

Do not just ramp load up and stop. Simulate:

1. Brief 10–30 second load spikes.
2. Temporary loss of a service instance.
3. A primary election on a lab replica set.
4. Load returning to baseline.
5. Confirming queues **drain**, retries subside, and latencies recover.

A resilient system does not merely resist overload—it **recovers cleanly from overload** once traffic normalizes.

## 18. Query Optimization Can Replace Pool Expansion

### 18.1. Shorter Query Hold Times Mean Higher Throughput

If a `find` takes 100 ms on a 20-connection pool, theoretical max ops/s ignoring waits and overhead is roughly:

\[
\frac{20}{0.100}=200 \text{ ops/s}
\]

If an index cuts execution to 10 ms:

\[
\frac{20}{0.010}=2{,}000 \text{ ops/s}
\]

These are **idealized upper-bound illustrations**, not real capacity, since DB CPU/IOPS and per-request overhead matter. Still, the principle holds: **cutting service time** beats adding sockets when the server is saturated.

### 18.2. Indexing to Match Query Shapes

~~~javascript
// Common query:
db.orders.find({
  tenantId: "tenant-a",
  status: "OPEN"
}).sort({ createdAt: -1 }).limit(20)

// Candidate index to benchmark:
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
})
~~~

With a good index, connection hold time drops and CMAP checkout wait falls **without touching pool size**. Keep in mind write amplification and storage trade-offs; check `explain` and benchmark first.

### 18.3. Eliminating N+1 Queries

Suppose an HTTP handler reads 100 order IDs via 100 sequential calls:

~~~javascript
// Suboptimal approach:
for (const id of ids) {
  db.orders.findOne({ _id: id })
}
~~~

Batch them:

~~~javascript
db.orders.find({ _id: { $in: ids } })
~~~

Where business semantics permit, batching slashes network round trips and pool checkouts. Huge `$in` lists still grow costly or hit response limits, so enforce **bounded batch sizes** and backpressure.

### 18.4. Pagination and Cursors

A report returning 2 million documents ties up memory and connection resources for ages. Instead:

- Project only needed fields.
- Paginate in batches along indexed stable keys.
- Prefer keyset pagination over deep `skip()` offsets.
- Close cursors promptly with `try-with-resources`.
- Use async jobs or streaming with bounded buffers.

**Do not** assume an open cursor pins one TCP socket continuously for its entire lifetime in every driver mode; checkout lifecycles differ across initial `find`, `getMore`, and transactions. Inspect CMAP events to measure real usage.

### 18.5. Bulk Writes

Thousands of single inserts create excessive round trips and overhead. `insertMany`/`bulkWrite` with **bounded batch sizes** raises throughput, though:

- Huge batches spike peak memory and max latency.
- Ordered vs. unordered operations differ in error behavior.
- Retries and idempotency must align with business rules.
- Background bulk jobs must not starve online API budgets.

Tune bulk batch sizes and background admission limits together.

### 18.6. Fixing Schema and Data Distribution

If one tenant or shard key is red-hot, enlarging connection pools cannot balance the hotspot. Redesign shard keys, isolate workloads, cache read-only data, or maintain materialized summaries. That is a **data modeling/routing problem**, not a transport pool problem.

## 19. Three Real-World Design Scenarios

### 19.1. Order Lookup API p99 Spikes at Peak Hours

**Hypothetical state:**

~~~text
10 app pods
1 MongoClient/pod
maxPoolSize=100
HTTP request worker threads/pod=200
Average MongoDB command=18 ms
MongoDB checkout wait p99=420 ms
HTTP p99=650 ms
DB CPU=55%, disk utilization=45%
~~~

Metrics suggest DB headroom remains, yet **checkout wait** is high. Hypotheses to verify:

1. Are long cursors or transactions holding connections too long?
2. Are all 100 sockets per pod genuinely checked out continuously?
3. Is `maxConnecting` slowing cold starts right after deploys?
4. Are 10 extra unmonitored `MongoClient` instances created per pod?
5. Do some requests fan out 10 parallel queries each?
6. Are server selection or pool clears adding to checkout duration?

**Do not blindly raise the pool.** If CMAP confirms 100/100 checked out and DB headroom exists, test bumping `maxSize` to 128 **alongside an admission gate, monitoring, and rollback**. If checked out is only 20/100 yet checkout p99 is high, investigate connection churn, `maxConnecting`, or failovers instead of raising the cap.

### 19.2. Dashboard Reports Cause Checkout API Timeouts

**Hypothetical state:**

~~~text
One shared MongoClient
Pool maxSize=60

Interactive API:
  ~40 short queries concurrent

Dashboard export:
  50 long aggregations concurrently

Observed:
  pool checked-out=60
  waiting API requests=hundreds
  command p99=several seconds
~~~

**Remediation:**

- Isolate a **reporting gate C=4 or C=8** with a bounded job queue.
- Optionally use a dedicated reporting `MongoClient`/small pool, budgeting total connections.
- Optimize aggregations, indexes, and materialized rollups.
- Offload large exports to async jobs with status polling.
- Enforce tight SLOs for interactive APIs and bounded longer timeouts for reports.
- Verify DB CPU/IOPS headroom remains sufficient for interactive traffic.

Separating pools while **heavy reports still saturate server CPU/IOPS** will leave the API slow. Control **server resource consumption** via scheduling, query tuning, or cluster capacity.

### 19.3. HPA Pod Scaling Overwhelms the Database

**Scenario:**

~~~text
5 pods initially
maxPoolSize=100 per pod
Potential primary pool cap=500

Traffic spike -> HPA to 30 pods
Potential primary pool cap=3,000
~~~

Even with each pod capped at 100, the fleet's ceiling jumped 6×. With static server capacity, extra connections shift queueing onto the DB, spiking context switching and cache contention.

**Remediation:**

1. Enforce a **global request/concurrency budget** at the gateway or via distributed rate limiters.
2. Adjust per-pod gates relative to max HPA replica counts in capacity planning.
3. Tune `minPoolSize`, warm-up, and `maxConnecting` to dampen connect storms.
4. Watch DB bottlenecks—never use app HPA to cure DB-bound saturation.
5. For sustained growth, plan controlled MongoDB scaling (CPU, storage, sharding, query redesign).

## 20. Overload Incident Diagnostic Runbook

### Step 1 — Define Scope and Timeline

- Which endpoints are impacted? Reads, writes, reports, or the whole cluster?
- Did errors start after a deploy, traffic spike, index change, failover, or HPA scale-out?
- How many app pods and `MongoClient` instances exist? Replica set or `mongos` topology?
- How did HTTP p95/p99, error rates, and completed QPS shift?
- Is MongoDB showing CPU, disk, memory, or lock pressure?

**Never jump straight from `MongoTimeoutException` to "the pool needs more connections."**

### Step 2 — Inspect Waiting by Layer

~~~text
HTTP latency high?
  |
  +-- HTTP worker queue high?
  |     -> ingress threads, executor, admission
  |
  +-- Admission wait high?
  |     -> concurrency gate too small OR DB slow
  |
  +-- Server selection timeout?
  |     -> topology, primary, network, election
  |
  +-- Pool checkout wait high?
  |     -> in-use near max OR connection creation/churn
  |
  +-- Command duration high?
  |     -> query plan, CPU, I/O, locks/tickets
  |
  +-- Response processing slow?
        -> huge payload, app CPU, GC, network
~~~

### Step 3 — Inspect the Driver Pool

1. CMAP `connectionCheckOutStarted` / `CheckedOut` / `CheckOutFailed`.
2. Current pool size and checked-out count (JMX).
3. Checkout wait p50/p95/p99.
4. Connection created/closed rates and pool-cleared events.
5. Actual `maxConnecting` and min/max pool settings **after framework overrides**.
6. Number of `MongoClient` instances per process and across the fleet.

### Step 4 — Inspect the MongoDB Server

1. `serverStatus.connections.current/active/available/rejected` per version.
2. CPU, IOPS, cache, and eviction.
3. `globalLock.currentQueue` and `queues` where supported.
4. `currentOp` to spot long-running commands.
5. Slow query logs/profiler and `explain` for heavy query shapes.
6. Replication lag, elections, and shard targeting.

Never leave high-level profiling running indefinitely in production or log sensitive query parameters unredacted.

### Step 5 — Apply Targeted Emergency Mitigations

| Observation | Action |
|---|---|
| DB CPU/IOPS saturated, many long queries | Throttle report admission, rate-limit heavy endpoints, tune queries, evaluate DB scaling |
| Pool maxed out while DB has headroom | Check for long ops, test modest `maxSize` bump and re-measure, keep queues bounded |
| Pool not full, high creation rate, slow checkout | Inspect `maxConnecting`, `minPool` warm-up, DNS/TLS/network, pool clears/reconnects |
| No primary / SDAM failover | Check cluster health; temporarily degrade/reject and retry with jitter |
| HTTP threads exhausted | Trim synchronous fan-out, use bounded/async executors, fail fast |
| Reports causing starvation | Isolate reporting bulkhead/queue, schedule jobs |
| Retry rate exceeds original traffic | Cap retries, add exponential backoff + jitter, trip circuit breakers |
| New deploy multiplied `MongoClient`s | Fix singleton reuse, lower min pools, roll out gradually |

### Step 6 — Verify Recovery

- Has completed throughput returned to normal levels?
- Have HTTP p95/p99 and pool checkout p99 dropped?
- Are rejection rates controlled and client retries well-behaved?
- Are MongoDB `connections.current/active` and CPU/IOPS stable?
- Do queues **drain** cleanly once traffic subsides?
- Were any database writes duplicated or lost from retries?

### Step 7 — Prevent Recurrence

1. Document incident timeline and bottleneck evidence.
2. Add alerts for queue depth, checkout wait, and retry amplification.
3. Benchmark realistic query mixes + peak traffic in staging.
4. Align global connection budgets, HPA bounds, and admission policies.
5. Fix indexes, query plans, or data models as needed.
6. Test failovers and rolling deploys for reconnect storms.
7. Roll out changes via canaries/feature flags with rollback ready.

## 21. Reference Architecture for a Load-Bounded MongoDB API

~~~text
                    HTTP clients
                         |
                         v
                    API Gateway
               - rate quota per tenant
               - max body/request size
                         |
                         v
                   App Instances
          +--------------+--------------+
          |              |              |
          v              v              v
     Auth/validation  Deadline context  Tracing
          |
          v
    Per-tenant admission gate
          |
          v
    Global in-flight gate + bounded queue
          |
          +-- capacity exceeded --> 429/503 + bounded retry guidance
          |
          v
      Operation class router
          |
          +-- interactive  -> MongoClient A (small/fast budget)
          |
          +-- background   -> MongoClient B (smaller C, long budget)
          |
          v
       MongoDB cluster
          |
          v
  Driver CMAP/SDAM + Command metrics
  ServerStatus/Profiler/Atlas monitoring
          |
          v
   SLO-aware tuning and alerts
~~~

### 21.1. Core Invariants

- **One stable `MongoClient`** per workload class, never per request.
- **End-to-end deadlines**, never unbounded waits across tiers.
- **Bounded queues** with explicit rejection policies.
- **Per-tenant and global concurrency** sized to topology and pod counts.
- **Pool sizes based on measured concurrency**, not thread counts.
- **Optimized query plans and indexes**; transport tuning cannot save collection scans.
- **Idempotent retries + capped attempts + jitter**.
- **Observability** separating HTTP, queue, checkout, command, and server layers.
- **Canaries and rollbacks** for pool, timeout, or bulkhead changes.

### 21.2. Defaults Are Not SLAs

Current MongoDB Java Driver docs list `maxPoolSize=100` and `maxConnecting=2`. Those numbers **are not universal recommendations for every application**, nor do they imply "MongoDB runs 100 operations optimally in parallel." They are general-purpose driver defaults; measure your real workload.

### 21.3. Multi-Cluster / Multi-Region Note

If requests route across multiple MongoDB clusters by region or tenant, enforce budgets **per destination cluster/server**. One global cap of 100 in the app will not stop 95 heavy requests hitting one cluster while another gets 5. Use partitioned gates and per-cluster monitoring to catch hotspots.

### 21.4. Protecting Admin and Health Paths

Reserve minimal capacity for **health checks, essential admin queries, and incident diagnostics**. However, never expose privileged admin APIs on the public internet just to "bypass rate limits." Pair authentication, authorization, and network controls with dedicated reserved admission slots.

## 22. Common Misconceptions

| Misconception | Why It Is Wrong | Proper Practice |
|---|---|---|
| "Raising `maxPoolSize` always boosts throughput." | DB may already be CPU/IO/lock saturated | Measure checkout + command latency + server resources first |
| "Pool=100 means max 100 sockets cluster-wide." | Limit is **per server and per `MongoClient`** | Multiply pods × clients × per-server cap |
| "Every HTTP request needs its own `MongoClient`." | Spawns pools, monitors, and TLS handshakes | Reuse singleton/workload-scoped clients |
| "100 worker threads means pool size must be 100." | Not all threads hit DB at once; fan-out varies | Measure concurrent checked-out sockets |
| "`connections.current=2,000` means 2,000 active queries." | Many sockets are idle or monitors | Inspect `connections.active`, CMAP, and `currentOp` |
| "`maxConnecting=100` is always faster than 2." | Causes connection/TLS/auth storms | Tune cold-start ramp conservatively |
| "`minPoolSize=100` makes all pods ready instantly." | Warm-up still incurs socket establishment | Rate-limit rollouts/warm-ups and readiness checks |
| "`maxIdleTimeMS=0` is always best." | Risks stale firewall sockets and idle bloat | Align below NAT/firewall idle timeouts |
| "`waitQueueTimeoutMS` bounds queue length." | Bounds wait time (legacy), not waiter count | Enforce bounded ingress/executor queues |
| "`waitQueueTimeoutMS` and CSOT `timeoutMS` always combine." | Depending on Java Driver version, CSOT ignores legacy timeouts | Pick one deadline model per docs |
| "`maxTimeMS` includes pool wait time." | Server limit excludes client waits | Use end-to-end deadlines / CSOT |
| "`socketTimeoutMS` is the right way to cap slow queries." | Socket timeout is not a clean server execution cap | Fix query plans + `maxTimeMS` or CSOT |
| "Server selection timeout means the pool is too small." | No eligible primary or topology/network failure | Check SDAM and replica set health |
| "`MongoTimeoutException` means the write did not commit." | Response may be lost after server commit | Use idempotency and retryable write semantics |
| "`Semaphore(20)` limits waiting threads to 20." | Unbounded callers can block waiting for permits | Use bounded HTTP/executor queues and short wait budgets |
| "`newFixedThreadPool(32)` has a queue of 32." | Default queue is **unbounded** | Use `ThreadPoolExecutor` + bounded queue |
| "`CallerRunsPolicy` is always safe." | Can stall HTTP threads or event loops | Pick fast rejection or async handling per SLO |
| "Reactive apps have no backpressure issues." | Async still drives huge in-flight DB ops | Bound `flatMap` concurrency + global gates |
| "Virtual threads eliminate DB bottlenecks." | Only lowers blocking-thread overhead | Bound in-flight ops/queues and tune MongoDB |
| "More parallel requests always lower p99." | Queueing and contention spike near saturation | Find the knee point and keep headroom |
| "HTTP QPS = DB operation QPS." | One request can run 0, 1, or many DB calls | Measure MongoDB command rates separately |
| "A 100/s rate limit stops 100 simultaneous requests." | Token buckets allow bursts | Pair with a concurrency cap |
| "Concurrency cap 20 means max 20 req/s." | Fast slots serve many req/s sequentially | Distinguish in-flight count from arrival rate |
| "A local cap of 10 per pod caps the service at 10." | 20 pods allow up to 200 in-flight | Use distributed quotas or budget across replicas |
| "Separate pools A/B keep reports from slowing DB." | They still share server CPU, IOPS, and cache | Budget server resources and tune queries |
| "Scaling HPA always fixes latency." | DB-bound overload worsens as pools multiply | Enforce global budgets and DB scaling plans |
| "Retrying timed-out requests infinitely helps recovery." | Retry amplification deepens overload | Enforce deadlines, backoff + jitter, circuit breakers |
| "Low DB command time guarantees low HTTP latency." | Queues, admission, checkout, network, GC add up | Trace every stage end-to-end |
| "`globalLock.currentQueue` is the driver pool queue." | It is a server-side lock queue, not CMAP wait | Separate client and server metrics |
| "Cumulative `checkedOut` counter equals current in-use." | Needs check-ins or a gauge | Use gauges / JMX `checkedOutCount` |
| "All `serverStatus` fields exist across all versions/tiers." | Fields vary by release and Atlas tier | Check version docs and handle missing keys |
| "Load tests only need peak QPS." | QPS plateaus while p99 and errors explode | Measure sustained throughput + latency + error rate |
| "Closed-loop generators expose overload accurately." | They throttle arrivals when responses slow | Include open-loop fixed-arrival tests |
| "Indexing has nothing to do with connection pools." | Faster queries hold connections far shorter | Prioritize query optimization |
| "Long cursors must load everything into a `List`." | Causes memory spikes and long holds | Stream/paginate with clean lifecycle management |
| "Hit a timeout? Bump it to 2 minutes." | Masks backlogs and breaks SLOs | Diagnose the stalled stage and align with business deadlines |
| "Autoscaling pods with pool=100 keeps DB cap at 100." | Each pod/client opens its own pools | Capacity-plan for max replica counts |

### 22.1. Five Questions for Every Configuration Review

1. **How many `MongoClient` instances and per-server pools does each app instance maintain across the topology?**
2. **At which layer are in-flight operations and queue depths actually bounded?**
3. **What is the end-to-end request deadline?** Do admission wait, checkout, and server execution fit within it?
4. **Where is the database actually saturating?** CPU, I/O, indexes, locks, storage tickets, or shard hotspots?
5. **What happens under overload?** How does the system reject/degrade, bound retries, drain queues, and recover?

## 23. Practice Exercises and Solutions

Exercises use hypothetical environments; when testing hands-on, use an **authorized replica set or Atlas lab**, dedicated synthetic data, and bounded load. QPS/latency numbers are for reasoning practice, **not executed benchmarks**.

### Exercise 1 — Per-Server Pools

**Prompt:** A `MongoClient` connects to a 3-member replica set with `maxPoolSize=100`. Is the client's total pooled connection cap across the entire replica set 100?

**Answer:** No. The driver maintains **one pool per server**, each capped at 100. Actual connections depend on read preference and topology; monitoring sockets also sit outside the pool. Nor are 300 sockets immediately opened upfront.

### Exercise 2 — Multiple Pods

**Prompt:** 12 pods each run 1 `MongoClient` with `maxPoolSize=50`, and traffic primarily hits the primary. What is the ceiling for application pooled connections to the primary?

**Answer:** \(12 \times 50 = 600\), excluding monitoring sockets, admin tools, and other services—and this is a **configuration ceiling**, not a guaranteed active socket count.

### Exercise 3 — Multiple `MongoClient`s

**Prompt:** Each pod creates 4 `MongoClient`s across 25 pods, with `maxPoolSize=80` per server per client. What is the app connection ceiling to the primary if all four clients target it?

**Answer:** \(25 \times 4 \times 80 = 8{,}000\). That is why you never create clients per request and must calculate fleet-wide pool budgets.

### Exercise 4 — Little's Law

**Prompt:** 600 MongoDB operations/s hold a connection for 20 ms on average. Estimate the average number of operations holding connections concurrently.

**Answer:** \(L = 600 \times 0.020 = 12\). Do not pick 12 as the final pool size—you need headroom for bursts and latency tails.

### Exercise 5 — Lower Service Time

**Prompt:** An index cuts average query duration from 100 ms to 25 ms. Ideally, how does the capacity of the same 20 connections change?

**Answer:** \(20 / 0.1 = 200\) ops/s vs. \(20 / 0.025 = 800\) ops/s—potential throughput quadruples if no other bottleneck blocks it. Do not claim the real DB automatically hits exactly 800 ops/s.

### Exercise 6 — Arrivals Exceeding Capacity

**Prompt:** A DB sustains 400 ops/s while the app sends 650 ops/s with no rejection. How fast can the queue grow?

**Answer:** \(650 - 400 = 250\) ops/s in a simplified model. Over 8 seconds, ~2,000 pending ops accumulate if conditions hold, triggering timeouts and retries. Enforce admission and queue caps.

### Exercise 7 — Threads vs. Pool

**Prompt:** A server has 300 HTTP threads, yet p95 concurrency is only 25 MongoDB calls. Is `maxPoolSize=300` automatically optimal?

**Answer:** No. Thread count does not equal DB concurrency. Size pools using checked-out metrics, checkout wait, bursts, and server capacity; 300 may be an excessively high ceiling.

### Exercise 8 — `maxConnecting`

**Prompt:** Pool max=100, min=0, `maxConnecting=2`. After restart, 100 requests arrive simultaneously. Do 100 sockets open at once?

**Answer:** No; concurrent **socket establishments** per pool are capped by `maxConnecting`. Excess requests wait; cold-start latency depends on TLS/auth handshakes and connection reuse.

### Exercise 9 — `minPoolSize`

**Prompt:** 50 pods set `minPoolSize=40` targeting one primary. Roughly how many pooled connections are targeted to stay warm at the primary?

**Answer:** By configuration, roughly \(50 \times 40 = 2{,}000\) pooled connections to the primary once each pool reaches min size—not guaranteed instantaneous at boot. Factor in handshake storms and memory footprint.

### Exercise 10 — Pool at Max

**Prompt:** Pool max=20, all 20 connections are checked out, and a new request arrives. What happens?

**Answer:** The driver waits for an available connection up to its timeout/deadline instead of opening a 21st connection above max. If the deadline expires, a checkout timeout exception occurs.

### Exercise 11 — `waitQueueTimeoutMS`

**Prompt:** Does `waitQueueTimeoutMS=5000` cap the queue at 5,000 entries?

**Answer:** No. It sets the legacy max wait time for a socket, **not** queue length. Use bounded admission/executor queues.

### Exercise 12 — CSOT + Legacy Wait

**Prompt:** Java Driver 5.x sets `timeoutMS=250` and `waitQueueTimeoutMS=5000`. Should you expect checkout to wait up to 5 seconds?

**Answer:** No. Per current CSOT docs, `timeoutMS` sets the overall operation deadline and legacy timeout options are ignored when set. Verify exact version and inheritance rules.

### Exercise 13 — `serverSelectionTimeoutMS`

**Prompt:** "No primary found" errors happen during an election while the pool is nearly empty. Will raising `maxPoolSize` fix it?

**Answer:** No; the failure is in **server selection/topology**, not pool exhaustion. Inspect SDAM, elections, network, and deadlines/retries.

### Exercise 14 — `maxTimeMS`

**Prompt:** A query sets `maxTimeMS=100` yet waits 800 ms in the HTTP executor before calling the DB. Will the request finish in 100 ms?

**Answer:** No. `maxTimeMS` only caps server execution, excluding app queues and checkout waits. Propagate end-to-end deadlines and bound admission waits.

### Exercise 15 — Timeout Longer Than SLA

**Prompt:** HTTP SLO is 250 ms, yet pool wait timeout is 120 seconds. Is that sensible?

**Answer:** Usually not. Align deadlines and fail fast when insufficient budget remains rather than holding thousands of doomed requests.

### Exercise 16 — `MongoClient` per Request

**Prompt:** An API creates and closes a `MongoClient` on every request. Why do latency and socket counts explode?

**Answer:** Repeated topology monitoring, pool creation, TLS/auth handshakes, and socket churn. Reuse a thread-safe singleton `MongoClient` per application lifecycle.

### Exercise 17 — Semaphore

**Prompt:** `Semaphore(16)` wraps a MongoDB call; 200 callers block on `acquire()` with no timeout. Can the system still suffer queue overload?

**Answer:** Yes. A semaphore caps 16 active callers yet **does not bound waiting callers**. Use `tryAcquire(timeout)` plus bounded HTTP/executor queues.

### Exercise 18 — Fixed Executor

**Prompt:** Does `Executors.newFixedThreadPool(20)` mean at most 20 tasks can be submitted to the system?

**Answer:** No. It caps 20 worker threads while using an **unbounded** queue by default. Use `ThreadPoolExecutor` with `ArrayBlockingQueue` and an explicit rejection policy.

### Exercise 19 — `CallerRunsPolicy`

**Prompt:** When the queue fills, `CallerRunsPolicy` makes the HTTP or event-loop thread run the blocking MongoDB query itself. Is that always good?

**Answer:** No. It can stall request threads or event loops and propagate overload upstream. Choose rejection/degradation or async models suited to your SLO; never block an event loop.

### Exercise 20 — Reactive `flatMap`

**Prompt:** Each Reactor request uses `flatMap(..., 16)`. How many inner operations can 100 concurrent requests spawn?

**Answer:** Up to ~1,600 concurrent inner subscriptions if all run simultaneously with enough items; `16` is **local concurrency**, not a global cap. Add global or per-tenant admission where needed.

### Exercise 21 — Virtual Threads

**Prompt:** A service moves from platform threads to Java virtual threads with the Sync Driver. Can you remove the 64 in-flight query limit?

**Answer:** No. Virtual threads lower blocking thread overhead, yet DB connections, CPU, and IOPS remain finite. Keep bounded admission, deadlines, and query monitoring.

### Exercise 22 — Global vs. Per-Pod Limits

**Prompt:** Each pod enforces a 10-permit gate across 30 pods, with no gateway quota for Tenant A. How many concurrent operations can Tenant A run?

**Answer:** Up to \(30 \times 10 = 300\) fleet-wide across local gates if all slots go to Tenant A. Enforce distributed/global per-tenant quotas if business rules cap A at 10.

### Exercise 23 — Rate Limiting

**Prompt:** A token bucket refills at 100 req/s with burst capacity 250. Can 250 requests arrive almost simultaneously?

**Answer:** Yes, if the bucket is full. Rate limiting does not replace **concurrency limiting**; pair with concurrency gates to shield the DB from simultaneous bursts.

### Exercise 24 — Retry Storms

**Prompt:** The DB is overloaded, 20% of requests time out, and the app immediately retries 3 times. What happens?

**Answer:** Attempt volume surges, increasing resource contention and locking the DB in a prolonged overload loop. Bound retries and deadlines, add exponential backoff + jitter, shed load, and keep writes idempotent.

### Exercise 25 — Write Timeout with Unknown Outcome

**Prompt:** A client calls `insertOne` and times out waiting for a response. Can it safely retry with a brand-new `_id` without checking?

**Answer:** No. The server may have already committed the write. Use stable business IDs/idempotency keys, retryable writes, and status checks before issuing a new operation to avoid duplicates.

### Exercise 26 — Secondary Read Preference

**Prompt:** Routing reads to secondaries—is that guaranteed to cut pool wait and raise throughput?

**Answer:** Not guaranteed. The driver opens secondary pools, offloading the primary at the expense of replication lag/staleness; secondaries also have finite CPU/IOPS. Measure and enforce consistency rules.

### Exercise 27 — Two `mongos` Routers

**Prompt:** A `MongoClient` connects to two `mongos` routers with `maxPoolSize=80`. Does the client have only 80 pooled connections total?

**Answer:** No; pooling is **per server/router** used by the driver. It can maintain two pools capped at 80 each depending on topology/traffic, plus monitoring sockets and other clients.

### Exercise 28 — Pool Metrics

**Prompt:** A cumulative `checkedOut` counter rises by 100,000 in 5 minutes. Are 100,000 sockets currently in use?

**Answer:** No. That is the **count of checkout events**, not an active in-use gauge. Track check-ins or JMX `checkedOutCount`.

### Exercise 29 — Driver Wait vs. Server Wait

**Prompt:** Checkout wait p99=200 ms, command execution p99=10 ms, DB CPU=30%. What should you inspect first?

**Answer:** Pool occupancy, `maxConnecting`/cold starts, connection churn, `MongoClient` count, and app queues. Upgrading DB CPU will not help; raise `maxPoolSize` only if evidence proves the pool cap is the bottleneck and server headroom exists.

### Exercise 30 — DB Saturated

**Prompt:** MongoDB CPU=97%, disk IOPS near limit, command p99=1,200 ms, pool max=100, current checked-out=95. Should you raise the pool to 1,000?

**Answer:** Usually no. More concurrent commands worsen contention. Throttle admission/reports, optimize queries/indexes/sharding/storage, or scale the DB; measure before/after.

### Exercise 31 — `serverStatus.connections.current`

**Prompt:** `connections.current=1500` while `connections.active=70`. Can you conclude 1,500 queries are actively running?

**Answer:** No. `current` includes idle sockets and monitors; `active` more closely reflects connections with active operations (version-dependent). Cross-check CMAP, `currentOp`, and CPU/IOPS.

### Exercise 32 — Lock Queue

**Prompt:** `globalLock.currentQueue.writers` climbs while Java CMAP checkout wait stays low. What does that indicate?

**Answer:** The bottleneck likely lies in **server lock/admission contention**, not connection pool checkout. Investigate long transactions, DDL, query patterns, and server resources—do not reflexively raise pool size.

### Exercise 33 — MongoDB 8.x Queues

**Prompt:** Monitoring code reads `serverStatus.queues.ingressSessionEstablishment` on MongoDB 7.0 and finds the field missing. Is the server broken?

**Answer:** No; many `queues` fields are **version/patch-gated**. Build version-aware dashboards rather than assuming identical `serverStatus` schemas across releases.

### Exercise 34 — HPA Scale-Out

**Prompt:** 8 pods × pool 100 scales to 40 pods × pool 100 while the primary does not scale. By what factor does the app connection ceiling rise?

**Answer:** From 800 to 4,000—**5×**. Raising connection ceilings adds zero DB execution capacity. Enforce global admission budgets and DB scaling plans.

### Exercise 35 — Bounded Queue via Little's Law

**Prompt:** A service completes 200 operations/s and targets ~50 ms average queue wait. Roughly what average queue length corresponds to that?

**Answer:** \(Q \approx 200 \times 0.05 = 10\) items. This is an **average heuristic**, not a p95 guarantee; enforce max wait times, queue caps, and load testing.

### Exercise 36 — Closed-Loop Load Testing

**Prompt:** 100 virtual users send the next request only after the prior response arrives. As latency rises, incoming RPS falls. Why does this hide overload?

**Answer:** Closed-loop load generation throttles arrivals alongside response time (**coordinated omission**), failing to test fixed external arrival demand. Add open-loop fixed-arrival tests to observe queue growth and rejections.

### Exercise 37 — Knee Point

**Prompt:** Completed RPS climbs from 100 to 620 with incoming load, then plateaus at ~625 as incoming hits 900 while p95 jumps from 120 ms to 2,500 ms. Conclusion?

**Answer:** The system saturates around ~620 ops/s under that workload. Establish headroom, bounded admission, and investigate server bottlenecks—never report 900 incoming RPS as achieved throughput.

### Exercise 38 — N+1 Queries

**Prompt:** Each request fetches 100 orders via 100 sequential `findOne` calls. How do you relieve pool and network pressure?

**Answer:** Batch with `find({_id: {$in: ids}})` using bounded ID lists, projections, response caps, and proper indexes. Avoid giant `$in` arrays and verify consistency and pagination rules.

### Exercise 39 — Long Cursors

**Prompt:** A report holds an open cursor streaming rows slowly to a client while the interactive API waits for connections. How do you fix this?

**Answer:** Isolate reporting behind its own bulkhead/queue, bound batch/page sizes, close cursors promptly, optimize queries, and offload exports to async jobs. Watch CMAP events to see how cursors borrow/hold connections rather than assuming every cursor pins one socket forever.

### Exercise 40 — Designing Admission for an API

**Prompt:** 15 pods each run 1 `MongoClient` with `maxPoolSize=64` per server across two workloads: orders API needing p95 < 300 ms, and reports taking up to 15 seconds. Propose a **verifiable** design, not just arbitrary numbers.

**Suggested Answer:**

1. Inventory read/write traffic and query shapes; measure command latency, in-use pool counts, and checkout wait.
2. Compute primary connection ceiling: \(15 \times 64 = 960\) pooled app connections (excluding monitors/other clients), noting this does not mean 960 active concurrent queries.
3. Keep a singleton `MongoClient` for orders; consider a separate reporting client/queue with a small cap.
4. Configure gateway rate limits and an interactive admission gate with a short bounded queue rejecting 429/503 when full.
5. Offload long reports to async jobs with a dedicated small concurrency cap \(C\) and bounded queue.
6. Set end-to-end deadlines aligned with the 300 ms orders SLO; give reports a longer yet bounded deadline rather than 2-minute queues.
7. Instrument CMAP/JMX metrics, SDAM failovers, command p95/p99, MongoDB CPU/IOPS/queues, and HPA pod counts.
8. Run open-loop load tests with realistic mixes, locate the knee point, compare gate/pool grids, and establish headroom.
9. Canary deploy while watching rejection rates, errors, DB pressure, and API p95/p99.
10. Test failover/reconnect storms, jittered/idempotent retries, and queue draining when load drops.

A strong answer proves **why** caps, queues, and timeouts were chosen via measurements—never declaring "`pool=64` is optimal" blind to the workload.

## 24. Quick Decision Table: Which Layer to Tune?

| Reliable Signal | Do Not Rush To | Investigate First |
|---|---|---|
| High checkout wait p99, checked-out near `maxPoolSize`, DB has headroom | Multiply `maxPoolSize` by 10 immediately | Long ops, client counts, modest cap + gate + canary |
| High checkout wait, many idle sockets in pool | Raise `maxPoolSize` | CMAP timings, pool clears, stale sockets, `maxConnecting`, topology |
| Server selection timeout | Enlarge the pool | Primary/secondary eligibility, elections, DNS/TLS/network |
| High command p99, CPU/IOPS near limits | Enlarge the pool | Indexes, scans, heavy aggregations, admission, DB capacity |
| HPA scales up and `connections.totalCreated` spikes | Raise `minPoolSize` on all pods | Singleton clients, staggered rollouts, warm-ups, global budget |
| High HTTP p99, low Mongo command p99 | Upgrade DB hardware | Ingress queues, admission wait, checkout, GC/network |
| Reports starve API slots | Give reports a bigger shared pool | Separate bulkheads/async jobs/query optimization |
| Queues grow nonstop when traffic > capacity | Make queues bigger/unbounded | Bounded queues, rejection/degradation, rate/concurrency limits |
| 429/503 rises in spikes while accepted latency stays healthy | Remove admission limits | Evaluate availability SLO, quotas, capacity, client retries |
| Write timeout after network event | Retry unconditionally with new ID | Retryable writes, stable idempotency keys, verify state |
| Bad p99 after failover | Restart all pods simultaneously | SDAM, reconnect storms, retry jitter, gradual recovery |
| One tenant slows down everyone | Raise `maxPoolSize` for all tenants | Per-tenant limits, expensive-query quotas, fairness |

### 24.1. Rollout Checklist for New Pool/Admission Settings

1. Record exact **server/driver/framework versions** and current baseline settings.
2. Pick target metrics/SLOs: checkout p99, HTTP p95, throughput, retry rate, error budget.
3. Locate the bottleneck via traces, CMAP, command, and server metrics.
4. State **one hypothesis**: e.g., pool max is constraining **and DB still has headroom**.
5. Make one small change and verify the connection budget at max HPA pods.
6. Run realistic mixed load tests, including bursts and recovery.
7. Canary deploy with live metrics and rollback ready.
8. Never bump all pools and timeouts together—you will not know what changed behavior.

### 24.2. Operational Configuration Manifest Fields

~~~text
service = orders-api
environment = production
driver_version = 5.x.y
server_version = <cluster version>
mongo_clients_per_pod = 1
max_pods = 30
read_preference = primary
max_pool_size_per_server = 64
min_pool_size_per_server = 4
max_connecting_per_pool = 4
application_in_flight_limit_per_pod = 40
application_queue_capacity_per_pod = 40
admission_wait_budget_ms = 50
mongo_operation_deadline_ms = 600
http_deadline_ms = 900
retry_max_attempts = 2
retry_backoff = exponential_with_jitter
~~~

This is an **illustrative manifest template**, not universally recommended numbers. In production, verify alongside real pod counts, query mixes, pool/SDAM metrics, server capacity, and SLO thresholds.

## 25. Official MongoDB Documentation

Use the links below to verify exact syntax and semantics. **Prioritize docs matching your exact MongoDB Java Driver version**, as defaults and timeout options evolve across releases.

### 25.1. Java Driver Connection Pools and Timeouts

1. [Java Sync Driver — Connection Pools](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/connection-pools/) — per-server pools, `maxSize`, `minSize`, `maxConnecting`, `maxWaitTime`, lifecycle.
2. [Java Sync Driver — Client-side Operation Timeout (CSOT)](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/csot/) — `timeoutMS`, Builder `timeout()`, inheritance, and ignored legacy timeouts.
3. [Java Sync Driver — Socket Settings](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/socket-settings/) — `connectTimeoutMS` and `socketTimeoutMS`.
4. [Java Sync Driver — Cluster Settings](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/cluster-settings/) — `serverSelectionTimeoutMS`, `localThresholdMS`.
5. [Java Sync Driver — Connection Troubleshooting](https://www.mongodb.com/docs/drivers/java/sync/current/connection/connection-troubleshooting/) — server selection errors, network, unavailable primary, pool behavior.
6. [MongoDB Connection String Options](https://www.mongodb.com/docs/manual/reference/connection-string-options/) — URI options, version-specific timeout semantics, and client pooling configuration.
7. [MongoDB Connection Pool Overview](https://www.mongodb.com/docs/manual/administration/connection-pool-overview/) — manual-level pool options/defaults, `maxConnecting`, and monitor sockets; cross-check driver-specific docs.

### 25.2. Monitoring

8. [Java Sync Driver — Monitoring](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/monitoring/) — CMAP `ConnectionPoolListener`, `CommandListener`, SDAM/JMX metrics.
9. [`serverStatus` Command](https://www.mongodb.com/docs/manual/reference/command/serverStatus/) — server connections, `globalLock`, version-gated `queues`, and storage engine statistics.
10. [`currentOp` Command](https://www.mongodb.com/docs/manual/reference/command/currentOp/) — active operations, `waitingForLock`, progress, per-namespace metrics.
11. [`$currentOp` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/currentOp/) — inspecting server/cluster operations per privileges and version.
12. [Analyze MongoDB Performance](https://www.mongodb.com/docs/manual/administration/analyzing-mongodb-performance/) — connection counts, locks, slow queries, and software/OS bottlenecks.
13. [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — reading execution plans, scans, sorts, and query optimization.

### 25.3. Concurrency, Transactions, and Query Performance

14. [Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — session/transaction resources, lifetimes, and error handling.
15. [WiredTiger Storage Engine](https://www.mongodb.com/docs/manual/core/wiredtiger/) — how cache, concurrency, and the storage engine operate.
16. [MongoDB Server Parameters](https://www.mongodb.com/docs/manual/reference/parameters/) — storage-engine concurrent tickets/limits varying by version; never tune without guidance.
17. [MongoDB Indexing Strategies](https://www.mongodb.com/docs/manual/applications/indexes/) — cutting query time by picking suitable indexes.
18. [`maxTimeMS` Operation](https://www.mongodb.com/docs/manual/reference/method/cursor.maxTimeMS/) — server-side time limits, distinct from client queues and CSOT.
19. [MongoDB Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/) — retry semantics and idempotency considerations.
20. [Connection Pool Monitoring Specification (MongoDB Drivers)](https://github.com/mongodb/specifications/blob/master/source/connection-monitoring-and-pooling/connection-monitoring-and-pooling.md) — CMAP events and semantics of checkout, check-in, and pool clears.

### 25.4. Cross-Checking Version Documentation

- **MongoDB Java Driver 5.x:** examples use `MongoClientSettings.builder()`, CSOT, and connection pool settings.
- **MongoDB Java Driver 4.x:** many options match, though newer methods/semantics may be absent or behave differently.
- **MongoDB Server 6.x/7.x/8.x/9.x:** `serverStatus` and storage-engine admission metrics evolve; never assume a rigid dashboard schema.
- **Spring Boot / Spring Data MongoDB:** auto-configuration and URI property bindings depend on starter/framework version.
- **Atlas free/shared tiers:** metrics and admin commands may be restricted; use Atlas monitoring APIs/dashboards appropriately.

Before picking parameters, answer: **which versions are running, what topology is deployed, how many `MongoClient`s and pods exist, what SLOs apply, and where did measurements locate the bottleneck?**

## 26. Conclusion

**Controlling concurrency, connection pools, and request queues** means **regulating capacity end-to-end from ingress to the database**—not picking the biggest possible `maxPoolSize`.

Three principles to remember:

1. **Pools regulate transport concurrency, not server capacity.** The MongoDB Java Driver maintains **pools per server and per `MongoClient`**, while monitoring sockets and other clients sit outside simple estimates. Account for pods, HPA scaling, and `MongoClient` counts together.
2. **Queues and deadlines must have hard bounds.** Neither `maxPoolSize` nor `waitQueueTimeoutMS` bounds pending caller counts. Enforce **admission gates, bounded executors/queues, rate limits, bulkheads, end-to-end deadlines, and explicit rejection/fallback policies** per SLA to prevent overload feedback loops.
3. **Measure before tuning.** Separate HTTP queues, admission wait, server selection, pool checkout, command duration, and server CPU/IOPS/locks. When queries/indexes or the DB are saturated, enlarging pools rarely helps; tune pools cautiously only once checkout is proven to be the bottleneck and server headroom exists.

A well-operated system is not one that **never rejects a request**, but one that preserves **sustainable throughput, predictable p95/p99 latency, recoverable errors, zero duplicate writes on retries**, and graceful survival when load exceeds design limits. **Set bounds from measured data, validate through load tests and failover drills, and roll out gradually with monitoring and rollback plans.**
