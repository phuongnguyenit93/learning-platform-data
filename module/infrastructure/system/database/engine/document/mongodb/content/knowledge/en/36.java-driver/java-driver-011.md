# Monitoring Topology, Pools, Commands, and Exception Classification in MongoDB Java Driver

## 1. Context: A Single Timeout Error Can Have Many Causes

A Java Spring Boot application uses a three-node MongoDB replica set. Normally the order-creation API writes in 30 ms. During maintenance, the primary steps down from node A to node B and the application begins reporting:

```text
com.mongodb.MongoTimeoutException:
Timed out while waiting for a server that matches
ReadPreferenceServerSelector{readPreference=primary}
```

An hour later, the app hits a "timeout" again, yet this time the cause is completely different: the primary is healthy and queries are fast, only **the connection pool ran out of available connections** due to a traffic spike.

On another occasion, the server accepts the command and returns `DuplicateKey` because the order already exists. If the application treats every exception as a "temporary network glitch" and retries indefinitely, the system can introduce further business bugs.

To distinguish these three cases properly, inspect **four observability layers** of the Java MongoDB Driver:

1. **Topology / SDAM:** which servers does the driver know about, which node can accept writes, and why can't a server be selected?
2. **Connection pool / CMAP:** how many connections exist, how long did checkout take, are callers waiting on the pool, or was the pool cleared?
3. **Command monitoring:** how long did `find`, `insert`, `aggregate`, etc. take, did they succeed or fail, and which database did they target?
4. **Exceptions & error labels:** did the failure stem from networking, no suitable server, authentication, write conflicts, execution timeouts, or an unknown transaction commit result?

**Core insight:** an exception type alone is never a complete diagnosis. Correlate **timestamps**, **topology events**, **pool events**, **command durations**, **application requests/traces**, and MongoDB server state.

### 1.1. Learning Objectives

After this lesson, you will be able to:

- Explain **Server Discovery and Monitoring (SDAM)**, **Connection Monitoring and Pooling (CMAP)**, and **Command Monitoring**.
- Register `ClusterListener`, `ServerListener`, `ServerMonitorListener`, `ConnectionPoolListener`, and `CommandListener` on `MongoClientSettings`.
- Interpret primary failover events, heartbeats, pool checkout failures, pool clears, and failed commands.
- Distinguish **server selection timeout**, **connection checkout timeout**, **socket timeout**, and **server execution timeout**.
- Use exception classes and `MongoException.hasErrorLabel()` to decide between **retry**, **reconcile**, or **fail fast**.
- Design metrics, traces, safe logs, dashboards, and alerts without triggering cardinality explosions.
- Write practical Java Sync Driver observability code and build runbooks for failover, pool exhaustion, auth/TLS failures, and command errors.
- Understand why driver retries never replace **business idempotency** or transaction correctness.

### 1.2. Versions and Scope

Examples focus on **MongoDB Java Sync Driver 5.x**, assuming Java 11+ where `String.isBlank()` is used. Method and event names match Java Driver 5.x APIs; verify against your project's exact version before compiling.

`MongoClient`, `MongoDatabase`, and `MongoCollection` in these examples belong to the **Sync Driver**. The Reactive Streams Driver uses a different asynchronous programming model, though SDAM, CMAP, and command concepts remain similar.

Example snippets are meant for **authorized lab or application environments**. Never intentionally step down a primary or exhaust connections in production just to "verify" these concepts.

## 2. Diagram of a Request Passing Through the Driver

```text
HTTP request / background job
          |
          v
    Business service
          |
          v
    MongoClient (long-lived)
          |
          +--------> SDAM monitor
          |           - topology descriptions
          |           - server descriptions
          |           - hello / heartbeat
          |
          v
     Server selection
          |
          v
    Select a suitable node
          |
          v
     Connection checkout <-------- Connection Pool (per server)
          |
          v
     Send MongoDB command
          |
          v
        mongod / mongos
          |
          v
     Receive reply or failure
          |
          v
     Decode BSON / result
          |
          v
     Return connection to pool
          |
          v
     Business response / error
```

### 2.1. One Request Spans Multiple Wait Stages

Logical breakdown:

\[
T_{\text{request}} \approx
T_{\text{app}} +
T_{\text{server selection}} +
T_{\text{pool checkout}} +
T_{\text{command}} +
T_{\text{decode}} +
T_{\text{other}}
\]

This is a **mental model**, not an exact additive identity of independent timers summing cleanly to request duration. Concurrency, retries, network handshakes, timeouts, and overlapping phases complicate real timings.

### 2.2. Four Observability Layers Answer Four Questions

| Layer | Question | Java Driver Signal |
|---|---|---|
| SDAM | Is a suitable primary or readable server available? | Cluster/server descriptions, heartbeats |
| CMAP | Is a connection available to use? | Checkouts, wait durations, pool clears/closes |
| Command | Did the command execute fast, slowly, or fail? | Started/succeeded/failed events, elapsed time |
| Exception | How should the application handle the failure? | Type, error code, error labels, cause |

### 2.3. Never Conflate the Layers

```text
Server selection 10 seconds
Pool checkout     1 ms
Command execution 8 ms

=> Command duration is low,
   yet the request is very slow waiting on server selection.
```

Consequently, a dashboard tracking only `CommandSucceededEvent.getElapsedTime()` will **miss** large portions of waiting time.

## 3. Three Event Systems in the Java Driver

The MongoDB Java Driver exposes three main groups of monitoring events:

| Group | Listener | Commonly Used Events |
|---|---|---|
| **SDAM — Topology** | `ClusterListener` | `ClusterOpeningEvent`, `ClusterDescriptionChangedEvent`, `ClusterClosedEvent` |
| **SDAM — Server** | `ServerListener` | `ServerOpeningEvent`, `ServerDescriptionChangedEvent`, `ServerClosedEvent` |
| **SDAM — Heartbeat** | `ServerMonitorListener` | `ServerHeartbeatStartedEvent`, `ServerHeartbeatSucceededEvent`, `ServerHeartbeatFailedEvent` |
| **CMAP — Pool** | `ConnectionPoolListener` | Pool open/clear/close, connection create/ready/close, checkout/checkin |
| **Commands** | `CommandListener` | `CommandStartedEvent`, `CommandSucceededEvent`, `CommandFailedEvent` |

### 3.1. Driver Events Are Client-Side, Not Database Auditing

`CommandListener` is not equivalent to MongoDB Enterprise/Atlas database auditing:

- A driver listener sees only operations issued by **that `MongoClient`**.
- Database auditing operates server-side under separate policies.
- Application listeners can be disabled or lost during a process crash.
- The driver does not emit command monitoring events for certain internal commands, notably topology-handshake/monitoring commands.

### 3.2. Listeners Run on Sensitive Execution Paths

Never write listeners that:

- Perform slow synchronous logging on every command.
- Issue synchronous HTTP requests to a monitoring backend.
- Instantiate a new `MongoClient` and query MongoDB inside each event.
- Block on global locks.
- Throw exceptions out of callbacks.

Instead, rely on lightweight counters/gauges, efficient metric recorders, or non-blocking/bounded exporters. **Your observer must never become the cause of an outage.**

## 4. Dependencies and `MongoClient` Lifecycle

### 4.1. Illustrative Gradle Dependency

```groovy
dependencies {
    implementation 'org.mongodb:mongodb-driver-sync:<compatible-5.x-version>'
}
```

The version string above is a placeholder. Real projects should pin dependencies and confirm compatibility against your BOM, framework, and server versions. Do not mix legacy Java Driver 3.x APIs arbitrarily with 5.x `com.mongodb.client.MongoClient`.

### 4.2. A Long-Lived `MongoClient`

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

public final class MongoLifecycle394 {
    private final MongoClient mongoClient;

    public MongoLifecycle394(String uri) {
        this.mongoClient = MongoClients.create(uri);
    }

    public MongoClient client() {
        return mongoClient;
    }

    public void shutdown() {
        mongoClient.close();
    }
}
```

In production apps, manage `MongoClient` as a singleton, DI bean, or managed component and invoke `close()` during service shutdown.

### 4.3. Why Not Create a New Client per Request?

Every `MongoClient` maintains its own topology monitors and connection pools. Creating one per HTTP request causes:

- Repeated pool opening and teardown.
- Excessive TCP and TLS handshakes.
- Spiking server connection counts.
- High CPU/memory overhead and tail latency.
- Metrics fragmented across ephemeral client IDs.

### 4.4. Do Not Pin URIs to a Single Primary

Example replica set URI:

```text
mongodb://db-a.internal.example:27017,db-b.internal.example:27017,db-c.internal.example:27017/?replicaSet=rsShop&tls=true&retryWrites=true
```

This URI lets the driver discover topology and elect a new primary automatically. `directConnection=true` is suited for targeted node diagnostics, not default production services needing failover.

### 4.5. Monitoring Privileges

Client-side driver listeners do not require granting `root` privileges. If you also query `replSetGetStatus` or `serverStatus` from the database, use a dedicated identity with appropriate privileges such as `clusterMonitor`.

## 5. SDAM: How the Driver Knows Topology

**SDAM = Server Discovery and Monitoring.** The driver uses `hello`/handshake replies and background monitors to track:

- Whether the deployment is standalone, replica set, sharded cluster via `mongos`, or load-balanced.
- Which server acts as primary, secondary, or router.
- Which servers are known or unknown.
- Round-trip-time estimates and reachability.
- Replica set name, member list, and advertised hostnames.
- Server selection eligibility under a given read preference.

### 5.1. Two Levels of Description

**ClusterDescription:** one `MongoClient`'s overall view of the deployment topology.

**ServerDescription:** the driver's view of an individual host.

```text
ClusterDescription:
  type = REPLICA_SET
  servers:
    db-a -> REPLICA_SET_PRIMARY
    db-b -> REPLICA_SET_SECONDARY
    db-c -> REPLICA_SET_SECONDARY
```

### 5.2. Descriptions Are Views, Not a Consensus Protocol

Each driver holds an **asynchronously updated view** of the deployment. A `ClusterDescriptionChangedEvent` means that client's local view changed—not proof that every client simultaneously observes identical state.

### 5.3. Failover Timeline

```text
T0: driver selects primary db-a
T1: db-a steps down
T2: driver detects not-primary or network error
T3: SDAM updates server descriptions
T4: driver discovers new primary db-b
T5: eligible operations resume or retry
```

Duration per step depends on elections, network latency, timeouts, heartbeats, and server selection behavior.

## 6. `ClusterListener`: Observing Writable Server Availability

Java example checking `ClusterDescriptionChangedEvent.getNewDescription().hasWritableServer()`:

```java
import com.mongodb.event.ClusterDescriptionChangedEvent;
import com.mongodb.event.ClusterListener;
import java.util.concurrent.atomic.AtomicBoolean;

public final class WritableTopology394 implements ClusterListener {
    private final AtomicBoolean writable = new AtomicBoolean(false);

    @Override
    public void clusterDescriptionChanged(
            ClusterDescriptionChangedEvent event) {
        boolean nowWritable =
            event.getNewDescription().hasWritableServer();

        boolean wasWritable = writable.getAndSet(nowWritable);
        if (wasWritable != nowWritable) {
            // Example: update metric gauge; do not log full ClusterDescription.
            System.out.println(
                "MongoDB writable server observed=" + nowWritable);
        }
    }

    public boolean writableInLastObservedView() {
        return writable.get();
    }
}
```

### 6.1. Registering the Listener

```java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

String uri = System.getenv("MONGODB_URI");
WritableTopology394 topology = new WritableTopology394();

MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .applyToClusterSettings(b ->
        b.addClusterListener(topology))
    .build();

try (MongoClient client = MongoClients.create(settings)) {
    client.getDatabase("admin").runCommand(
        new org.bson.Document("ping", 1));
}
```

### 6.2. Limitations of the `hasWritableServer` Boolean

It only reflects writability **in the driver's topology view at the instant observed**. It does NOT guarantee:

- Every new request will succeed.
- Authentication succeeded.
- The network won't drop right after the callback.
- Majority write concern can be satisfied.
- A specific transaction or command is supported.

Do not substitute this gauge for business write probes or server-side majority monitoring.

### 6.3. Watch Out for Startup State

At startup, the listener may not have received full server descriptions yet, so initial state can be `false`. Do not treat an initial startup `false` sample as an outage while the client is still discovering topology.

## 7. `ServerListener`: Tracking Individual Server State

A server can transition from primary to secondary, known to unknown, or vice versa.

```java
import com.mongodb.event.ServerDescriptionChangedEvent;
import com.mongodb.event.ServerListener;

public final class ServerChange394 implements ServerListener {
    @Override
    public void serverDescriptionChanged(
            ServerDescriptionChangedEvent event) {
        String before = String.valueOf(
            event.getPreviousDescription().getType());
        String after = String.valueOf(
            event.getNewDescription().getType());

        if (!before.equals(after)) {
            System.out.println(
                "Server role/type changed: " + before + " -> " + after);
        }
    }
}
```

**Production:** emit metrics or structured logs with controlled labels (deployment, before/after role) instead of printing full objects containing internal host addresses. Include server identity only under proper security controls.

### 7.1. `UNKNOWN` Does Not Always Mean the `mongod` Process Died

A server description can transition to `UNKNOWN` due to:

- DNS, network, TLS, or authentication handshake failure.
- Timeouts or socket errors.
- Election state transitions.
- Firewalls or private endpoints unreachable from **this specific client**.

Cross-check views from other app instances, Atlas/server metrics, and server logs to find the true root cause.

### 7.2. Do Not Equate Topology Changes with Per-Request Monitoring

`ServerDescriptionChangedEvent` fires only when a server description changes—not on every `find`. Command and application metrics must still be collected separately.

## 8. `ServerMonitorListener`: Heartbeats and Reachability

Server monitor events include:

- `serverHeartbeatStarted`.
- `serverHeartbeatSucceeded`.
- `serverHeartbeatFailed`.

Java example:

```java
import com.mongodb.event.ServerMonitorListener;
import com.mongodb.event.ServerHeartbeatSucceededEvent;
import com.mongodb.event.ServerHeartbeatFailedEvent;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.LongAdder;

public final class HeartbeatCounters394
        implements ServerMonitorListener {
    private final LongAdder succeeded = new LongAdder();
    private final LongAdder failed = new LongAdder();

    @Override
    public void serverHeartbeatSucceeded(
            ServerHeartbeatSucceededEvent event) {
        succeeded.increment();
        // Optionally record histogram; watch for awaited heartbeats.
    }

    @Override
    public void serverHeartbeatFailed(
            ServerHeartbeatFailedEvent event) {
        failed.increment();
        // Never log raw exceptions containing secrets or host details.
    }

    public long successCount() {
        return succeeded.sum();
    }

    public long failureCount() {
        return failed.sum();
    }
}
```

### 8.1. Registering

```java
MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .applyToServerSettings(b ->
        b.addServerMonitorListener(new HeartbeatCounters394()))
    .build();
```

### 8.2. The Awaited Heartbeat Duration Trap

MongoDB supports **streaming/exhaust `hello`** monitoring under compatible conditions. When `ServerHeartbeatSucceededEvent.isAwaited() == true`, `getElapsedTime()` includes **time the server deliberately waited before replying**.

Therefore:

```text
heartbeat elapsed = 10 seconds
awaited = true
```

**does NOT mean network RTT is 10 seconds**. Distinguish awaited monitoring events from round-trip-time estimates.

### 8.3. Load-Balanced Mode

In MongoDB load-balanced mode, the Java Driver **does not emit standard heartbeat-related SDAM events**. Never page an outage solely because "zero heartbeat events arrived" when deployed behind a load balancer.

### 8.4. Heartbeat Frequency

The driver exposes `heartbeatFrequencyMS`, `minHeartbeatFrequency`, and `serverMonitoringMode` with defaults varying by version and environment. Setting heartbeat intervals too low creates extra load; setting them too high delays topology discovery.

Never tune defaults merely to make dashboards look "smoother" without measuring impact.

## 9. Separating SDAM State from Health Checks

### 9.1. A Temporarily Missing Primary

```text
MongoDB replica set:
  db-a PRIMARY -> steps down
  db-b SECONDARY -> election -> PRIMARY

Client A:
  has not discovered new primary yet

Client B:
  already selected db-b
```

Client A and Client B may observe different states briefly even while the same cluster runs.

### 9.2. Application Health Probes

Distinguish carefully:

- **Liveness:** the JVM is running without deadlocks.
- **Readiness:** the instance can serve expected traffic.
- **Database readiness:** the driver can select a server meeting required read/write concerns within acceptable deadlines.

Never restart all 100 pods because a brief election makes readiness fail transiently; mass restarts trigger connection storms and prolong outages.

### 9.3. Observe from Both Client and Server Sides

A cluster can have a healthy primary while an app fails to connect due to TLS SAN mismatches, firewalls, or DNS. Server-only `rs.status()` **never proves** the client data path works.

A practical dashboard combines:

```text
SDAM events + pool checkouts + command failures
              +
MongoDB replSetGetStatus / Atlas metrics
              +
API error rate / latency
```

## 10. CMAP: How the Connection Pool Works

**CMAP = Connection Monitoring and Pooling.** Each `MongoClient` maintains an independent connection pool per server endpoint.

```text
MongoClient in Java Service
        |
        +-- Pool db-a
        |     conns idle / checked out
        |
        +-- Pool db-b
        |     conns idle / checked out
        |
        +-- Pool db-c
              conns idle / checked out
```

Beyond pooled application connections, the driver opens dedicated monitoring sockets per server; total server connections do not equal strictly `maxPoolSize` multiplied by node count.

### 10.1. One Connection Does Not Equal One Request

Connections are reused across many operations. One HTTP request might execute multiple MongoDB commands or transactions, and conversely the pool does not open a dedicated connection per HTTP request.

### 10.2. "Checked Out" Connections

When an operation borrows a connection from the pool, that connection is **in use**. Once finished or released, the driver checks it back in for reuse by other operations.

### 10.3. Checkout Occurs Before the Command

If a pool is busy, an operation may **wait for a connection** before `CommandStartedEvent` even fires. Command latency metrics miss pool wait time.

## 11. Connection Lifecycle and CMAP Events

```text
Pool opened
   |
   v
Connection created
   |
   v
Connection ready (handshake/auth complete)
   |
   v
Checkout started
   |
   +------> Checked out -> command -> Checked in
   |
   +------> Checkout failed (timeout/error/pool closed)
   |
   v
Connection closed / pool cleared / pool closed
```

In reality, events across a pool do not follow one rigid lockstep sequence: pools hold multiple connections concurrently, readiness can interleave with checkouts, clearing invalidates a generation, and connections are reused repeatedly.

### 11.1. Useful CMAP Events

| Event | Observability Meaning |
|---|---|
| `ConnectionPoolOpenedEvent` | Pool created for a server |
| `ConnectionCreatedEvent` | Driver started opening a connection |
| `ConnectionReadyEvent` | Connection completed setup and is usable |
| `ConnectionCheckOutStartedEvent` | Operation requested a connection |
| `ConnectionCheckedOutEvent` | Operation acquired a connection |
| `ConnectionCheckOutFailedEvent` | Failed to acquire a connection |
| `ConnectionCheckedInEvent` | Connection returned to pool |
| `ConnectionClosedEvent` | Connection closed with a reason |
| `ConnectionPoolClearedEvent` | Pooled connections in generation may be invalidated |
| `ConnectionPoolClosedEvent` | Pool shut down permanently |

### 11.2. Pool Clear Does Not Always Mean "Pool Exhausted"

A pool can be cleared after network errors, connection errors, or topology shifts; older connections are invalidated and the driver re-establishes new ones as needed.

**A burst of pool clears after a failover does not by itself prove an application connection leak.** Correlate timestamps with SDAM events and checkout failures.

## 12. `ConnectionPoolListener`: Counting Checkouts and Failures

Simple, **thread-safe** event counting example:

```java
import com.mongodb.event.ConnectionPoolListener;
import com.mongodb.event.ConnectionCheckedOutEvent;
import com.mongodb.event.ConnectionCheckedInEvent;
import com.mongodb.event.ConnectionCheckOutFailedEvent;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.LongAdder;

public final class PoolCounters394 implements ConnectionPoolListener {
    private final LongAdder checkedOut = new LongAdder();
    private final LongAdder checkedIn = new LongAdder();
    private final LongAdder checkoutFailed = new LongAdder();

    @Override
    public void connectionCheckedOut(ConnectionCheckedOutEvent event) {
        checkedOut.increment();
        long waitMicros = event.getElapsedTime(TimeUnit.MICROSECONDS);
        // Record waitMicros in a histogram with a safe server label.
    }

    @Override
    public void connectionCheckedIn(ConnectionCheckedInEvent event) {
        checkedIn.increment();
    }

    @Override
    public void connectionCheckOutFailed(
            ConnectionCheckOutFailedEvent event) {
        checkoutFailed.increment();
        String reason = event.getReason().name();
        // Increment counter per reason: TIMEOUT/CONNECTION_ERROR/POOL_CLOSED...
    }

    public long failedCount() {
        return checkoutFailed.sum();
    }
}
```

### 12.1. Registering the CMAP Listener

```java
MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .applyToConnectionPoolSettings(b ->
        b.addConnectionPoolListener(new PoolCounters394()))
    .build();
```

### 12.2. `LongAdder` Subtraction Is Not an Exact Gauge

`checkedOut.sum() - checkedIn.sum()` is only a rough approximation over the listener's lifetime; pool clears/closes, concurrent delivery order, and restarts can make the difference meaningless as **current pool utilization**.

For accurate active/idle/pending gauges per server, track full **pool lifecycle state** or use JMX MXBeans / supported instrumentation; verify semantics around clears and closes.

### 12.3. Checkout Duration

In Java Driver 5.x, `ConnectionCheckedOutEvent.getElapsedTime(TimeUnit)` measures elapsed time from checkout start to checkout acquisition. This closely tracks **connection wait time**, including new socket setup time when a new connection had to be opened.

Track p50/p95/p99 histograms rather than raw checkout counts alone.

## 13. Distinguishing Three Checkout Failure Reasons

`ConnectionCheckOutFailedEvent.getReason()` reports categories including:

- **TIMEOUT:** waiting for a connection exceeded the limit.
- **CONNECTION_ERROR:** error creating or initializing a connection.
- **POOL_CLOSED:** pool has already closed.

### 13.1. `TIMEOUT`

Investigate:

- Is `maxPoolSize` saturated?
- Are checkout wait p95/p99 values climbing?
- Are operations holding connections too long?
- Did HTTP concurrency spike suddenly?
- Is `maxConnecting` throttling new connection creation?

### 13.2. `CONNECTION_ERROR`

Investigate:

- DNS, TCP, TLS, CA, or certificate issues.
- Is the MongoDB host reachable?
- Authentication failures.
- Network partitions or overloaded servers.

**Increasing `maxPoolSize` never fixes an invalid certificate.**

### 13.3. `POOL_CLOSED`

Investigate:

- Was `MongoClient.close()` called?
- Is the service shutting down?
- Is a per-request client being created and closed prematurely?

### 13.4. Do Not Lump All Checkout Failures Under "MongoDB Down"

If the host is healthy while checkouts time out under heavy app concurrency, the database team will see zero server errors. Client-side telemetry is essential.

## 14. Important Pool Settings

| Setting | Meaning | Trade-off |
|---|---|---|
| `maxPoolSize` | Maximum connections **per server pool** | Too low: queueing; too high: excessive server connections |
| `minPoolSize` | Minimum connections maintained open | Too high: holds idle resources unnecessarily |
| `maxConnecting` | Concurrent connection creations **per pool** | Too low: cold-start tail latency |
| `maxIdleTimeMS` | Closes connections idle too long | Too short: frequent handshakes |
| `maxLifeTimeMS` | Maximum lifetime of a connection | Rotation churn if too short |
| `maxWaitTime` / `waitQueueTimeoutMS` | Wait limit for checkout | Must align with operation deadlines |
| `timeoutMS` (Client-Side Operation Timeout, where supported) | Total operation time budget | May supersede legacy wait settings |

### 14.1. Common Defaults in 5.x Docs

```text
maxPoolSize   = 100 / server pool
minPoolSize   = 0
maxConnecting = 2
```

These are defaults documented for current drivers, not blanket recommendations for every cluster. Exact defaults and timeouts vary by driver version, API, and URI options.

### 14.2. Legacy `waitQueueTimeoutMS`

Current MongoDB Java Sync Driver documentation marks `waitQueueTimeoutMS` as **deprecated** and recommends client-level timeouts for certain scenarios.

If an older project still sets `waitQueueTimeoutMS` or builder `maxWaitTime`, check how they interact with modern `timeoutMS`. Never stack multiple timeouts assuming each triggers independently.

### 14.3. Limits Apply per Server

With three `mongos` routers and one `MongoClient`:

```text
maxPoolSize=100

Pool mongos-a: up to 100 pooled conns
Pool mongos-b: up to 100 pooled conns
Pool mongos-c: up to 100 pooled conns
```

Do not misread `maxPoolSize=100` as "the entire `MongoClient` uses at most 100 sockets across all servers combined".

## 15. Java Pool Configuration Example

```java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import java.util.concurrent.TimeUnit;

public final class ClientWithPool394 {
    public static MongoClient create(String uri) {
        return MongoClients.create(
            MongoClientSettings.builder()
                .applyConnectionString(new ConnectionString(uri))
                .applyToConnectionPoolSettings(b -> b
                    .maxSize(80)
                    .minSize(5)
                    .maxConnecting(4)
                    .maxConnectionIdleTime(60, TimeUnit.SECONDS)
                    .addConnectionPoolListener(new PoolCounters394()))
                .applyToClusterSettings(b -> b
                    .serverSelectionTimeout(15, TimeUnit.SECONDS))
                .retryWrites(true)
                .retryReads(true)
                .build());
    }
}
```

`80`, `5`, `4`, and `15 seconds` are **illustrative values**. Never apply them in production without knowing app concurrency, number of `MongoClient` instances, server count, and server connection limits.

### 15.1. Size Pools Across the Entire Fleet

Example:

```text
Application replicas = 50
MongoClient per replica = 1
maxPoolSize per server = 80

Theoretical pooled capacity per targeted server
  = 50 * 80 = 4,000
```

That is the **theoretical ceiling** if every pool maxes out, before adding monitoring sockets, controllers/other apps, load distribution, and topology effects. Server connections can surge even though each individual app pod looks modest at pool size 80.

### 15.2. Little's Law as an Estimation Tool

At steady state:

\[
L \approx \lambda W
\]

If 500 requests/second hold a connection for 20 ms on average:

\[
L \approx 500 \times 0.02 = 10
\]

This estimates only the **average in-flight DB operations** under simplified assumptions—before traffic bursts, fan-out queries, transactions, per-server pools, and tail latency. Always benchmark under realistic load.

### 15.3. Do Not Fix Slow Queries with Larger Pools

If each query takes 3 seconds due to a collection scan, adding connections increases concurrency and drives disk and CPU even deeper into saturation. Optimize queries and indexes before or alongside pool tuning.

## 16. Pool Cleared After Failover

Typical timeline:

```text
T0   Primary A healthy
T1   Primary A steps down
T2   Driver detects network/not-primary error
T3   Pool to A cleared
T4   Server description for A changes
T5   Server B recognized as primary
T6   Pool to B creates/uses connections
T7   Commands succeed on B
```

### 16.1. Pool Clears Are a Valuable Signal

Counting `connectionPoolCleared` per server helps spot:

- Failovers and stepdowns.
- Network instability.
- Server errors triggering pool invalidation.
- Disrupted credential or certificate rotations.

### 16.2. Do Not Page on Every Single Clear

A pool clear can be normal during topology changes. Page instead when:

- Clears repeat rapidly.
- Checkout failure rate spikes.
- Application errors persist.
- SDAM shows no writable server.

### 16.3. Connection Pool Churn

Signals:

```text
connectionsCreated/sec rising
connectionsClosed/sec rising
checkout duration p99 rising
poolCleared/sec rising
```

Causes include flaky networking, overly aggressive idle/max-lifetime settings, creating too many `MongoClient`s, rolling restarts, or election storms.

## 17. Detecting Connection Leaks and Long-Held Connections

A connection checked out for a long time is not always a leak. It may reflect:

- Long-running queries or aggregations.
- Long transactions.
- Slowly iterated cursors.
- Change streams or tailable cursors.
- Unusual session or workload patterns.

### 17.1. Distinguishing Leaks from Slow Operations

```text
Scenario A:
  Pool in-use rises
  Command duration rises
  Server CPU/disk high

=> Likely slow queries, not necessarily a leak.

Scenario B:
  Pool in-use climbs continuously
  Command rate stays flat or unrelated
  Cursors/transactions remain open long

=> Inspect resource lifecycle and leaks.
```

### 17.2. Cursor Lifecycle in Java

```java
import com.mongodb.client.MongoCursor;
import org.bson.Document;

try (MongoCursor<Document> cursor =
         collection.find().limit(1000).iterator()) {
    while (cursor.hasNext()) {
        Document doc = cursor.next();
        // Process minimally; avoid expensive blocking I/O in this loop.
    }
}
```

Use `try-with-resources` whenever holding cursors explicitly; never leave cursors dangling or omit closing them. Exact connection/cursor pinning behavior depends on driver and server operations.

### 17.3. Transactions

Long transactions can pin resources and cause contention. Never start a transaction and wait minutes for user confirmation.

### 17.4. Additional Metrics

Track open cursors, active transactions, command durations, pool in-use gauges, and app concurrency together to isolate the root cause.

## 18. JMX: An Option for Monitoring Connection Pools

The Java Driver ships `JMXConnectionPoolListener`, registering MXBeans for pools readable via JConsole or JMX agents.

Example:

```java
import com.mongodb.management.JMXConnectionPoolListener;

MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .applyToConnectionPoolSettings(b ->
        b.addConnectionPoolListener(
            new JMXConnectionPoolListener()))
    .build();
```

### 18.1. When to Use JMX

- Your Java app already runs a JMX exporter or APM agent.
- You want per-server pool size, in-use, and idle counts.
- You want pool visibility without writing a custom CMAP state tracker.

### 18.2. JMX Is Not Secure by Default

If exposing remote JMX, enforce authentication, TLS, and network isolation. An unauthenticated public JMX endpoint exposes sensitive runtime details.

### 18.3. Relationship to Micrometer and Prometheus

You can scrape JMX metrics into Prometheus or wire CMAP listeners directly to Micrometer. **Avoid running duplicate overlapping instrumentation** without standardized units and metric naming.

## 19. Command Monitoring: Observing Executed Commands

`CommandListener` receives client-side MongoDB command lifecycle events:

```text
CommandStartedEvent
       |
       +-- CommandSucceededEvent
       |
       +-- CommandFailedEvent
```

### 19.1. Commonly Useful Fields

| Field | Use Case |
|---|---|
| `commandName` | Group by `find`, `insert`, `aggregate`, `update`, etc. |
| `databaseName` | Partition metrics by database where allowed |
| `requestId` | Correlate start and completion of a specific wire command |
| `operationId` | Correlate command attempts belonging to one logical operation per driver semantics |
| Connection/server metadata | Identify target endpoint |
| `elapsedTime` | Command completion latency histograms |
| Success/failure | Error rates by command name and exception family |

### 19.2. Which Commands Do Not Appear?

The driver suppresses command monitoring events for **certain internal commands**, including initial handshakes and topology-monitoring `hello` calls.

To monitor heartbeats, register `ServerMonitorListener`—do not count `CommandStartedEvent("hello")` and assume full SDAM visibility.

### 19.3. One Query Can Emit Multiple Commands

Cursor execution:

```text
find -> getMore -> getMore -> killCursors
```

One API request can trigger multiple MongoDB commands, each with its own timing. Command counts do not equal HTTP request counts.

## 20. Java `CommandListener` Logging Only Safe Metadata

```java
import com.mongodb.event.CommandListener;
import com.mongodb.event.CommandStartedEvent;
import com.mongodb.event.CommandSucceededEvent;
import com.mongodb.event.CommandFailedEvent;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.LongAdder;

public final class SafeCommandMetrics394 implements CommandListener {
    private final LongAdder succeeded = new LongAdder();
    private final LongAdder failed = new LongAdder();

    @Override
    public void commandStarted(CommandStartedEvent event) {
        // Capture command name only; DO NOT log event.getCommand().
        String cmd = event.getCommandName();
        // Optional: count starts by allowlisted command names.
    }

    @Override
    public void commandSucceeded(CommandSucceededEvent event) {
        succeeded.increment();
        long millis = event.getElapsedTime(TimeUnit.MILLISECONDS);
        String cmd = event.getCommandName();
        // recordHistogram("mongodb.command.duration", millis, cmd);
    }

    @Override
    public void commandFailed(CommandFailedEvent event) {
        failed.increment();
        long millis = event.getElapsedTime(TimeUnit.MILLISECONDS);
        String cmd = event.getCommandName();
        String failureType =
            event.getThrowable().getClass().getSimpleName();
        // Record only allowlisted cmd and failureType, not raw payload.
    }

    public long failedCommands() {
        return failed.sum();
    }
}
```

### 20.1. Registering

```java
MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .addCommandListener(new SafeCommandMetrics394())
    .build();
```

### 20.2. Keep Duration Units Consistent

`getElapsedTime(TimeUnit.MILLISECONDS)` truncates sub-millisecond commands to `0`. For microsecond histograms:

```java
long micros = event.getElapsedTime(TimeUnit.MICROSECONDS);
```

Never mix microsecond samples into a dashboard labeled in milliseconds.

### 20.3. Duration Covers a Single Command Attempt

Per-attempt command duration excludes server selection, pool checkout, and outer retries. Combine it with end-to-end distributed traces and request histograms.

## 21. Command Metrics Are Not Server-Side Profiling

### 21.1. Client-Side Duration

`CommandSucceededEvent.getElapsedTime()` measures the command attempt from the driver's perspective, including serialization and network reply round-trip as defined by the driver spec.

### 21.2. Server-Side Query Execution

MongoDB `explain("executionStats")`, the database profiler, slow query logs, and `serverStatus` reveal:

- Index scans vs. `COLLSCAN`.
- `totalKeysExamined` and `totalDocsExamined`.
- Server-side execution duration.
- Query shapes, locks, CPU, and disk activity where exposed.

### 21.3. The Two Sources Can Differ

Example:

```text
Client command elapsed: 250 ms
Server query processing: 30 ms
```

The gap can include network latency, server queueing, payload transfer, JVM pauses, or measurement boundary differences. Do not declare with certainty "the network added 220 ms" solely from subtracting two numbers.

### 21.4. One Query Is Not One Logical Operation

`find` + `getMore`, aggregation cursors, bulk writes, and transaction commits all generate multiple command events. Attach instrumentation to distributed business traces for aggregate analysis.

## 22. Security: Command Payloads Can Contain PII or Secrets

**Never** print full commands:

```java
// Forbidden in production:
System.out.println(event.getCommand().toJson());
```

Filters and updates frequently carry:

- Emails, phone numbers, street addresses, personal IDs.
- Password reset tokens or refresh tokens.
- Order details and payment info.
- Tenant identifiers and business logic.
- Sensitive collection or namespace names.

### 22.1. Driver Redaction Has Limits

The driver automatically redacts **specific sensitive commands** per specification, which does **not** mean every `find` or `update` payload is masked.

Serializing `event.getCommand()` directly in an application logger will leak user data.

### 22.2. Permitted Structured Metadata

```text
service=order-api
command=update
result=failed
exceptionFamily=connectivity
durationMs=12
topologyType=replicaSet
```

### 22.3. Never Log Raw Connection Strings

```java
// Wrong: may expose username/password and sensitive query parameters.
log.info("Connecting with URI: {}", mongoUri);

// Better:
log.info("Initializing MongoDB client for service=order-api");
```

### 22.4. When Deep Debugging Is Needed

Use synthetic staging data, time-bounded sampling, field masking, explicit access approval, and strict retention. Never turn on raw command logging across all of production just to chase one bug.

## 23. Request IDs, Operation IDs, and Trace IDs

### 23.1. Driver Request ID

`CommandStartedEvent.getRequestId()` identifies the wire command request, useful for correlating events within the same client/connection context.

### 23.2. Operation ID

`getOperationId()` correlates command attempts under one logical driver operation per driver-version semantics, **not** a system-wide business request ID.

### 23.3. HTTP Traces

```text
HTTP requestId = R1001
     |
     v
OrderService span = S23
     |
     v
MongoDB command operation (find/update)
     |
     v
driver requestId / operationId
```

Connecting these layers properly requires framework instrumentation and OpenTelemetry context propagation. Do not expect driver `requestId` to automatically carry your HTTP request ID.

### 23.4. Cardinality Warning

Never place `requestId`, `operationId`, `orderId`, or raw `userId` in **Prometheus metric labels**; unbounded cardinality will overwhelm TSDB storage. Reserve them for properly secured traces and logs.

## 24. Designing Intentional Metric Names and Labels

### 24.1. Suggested Metrics

| Metric | Type | Bounded Labels |
|---|---|---|
| `mongo_driver_topology_writable` | Gauge (0/1/unknown) | service, deployment |
| `mongo_driver_sdam_changes_total` | Counter | type, deployment |
| `mongo_driver_heartbeat_failures_total` | Counter | server group, reason class |
| `mongo_driver_pool_checkout_seconds` | Histogram | service, server role |
| `mongo_driver_pool_checkout_failures_total` | Counter | reason, server group |
| `mongo_driver_pool_clears_total` | Counter | server group |
| `mongo_driver_command_seconds` | Histogram | command, outcome |
| `mongo_driver_command_failures_total` | Counter | command, error family |
| `mongo_driver_application_errors_total` | Counter | business operation, retry decision |

**This is a suggested naming convention**, not metrics emitted automatically under these names by the MongoDB Java Driver.

### 24.2. Dangerous Labels to Avoid

- Raw MongoDB URIs or sensitive hostnames.
- Unbounded user-created collection names.
- Usernames, emails, tokens, `orderId`, or `requestId`.
- Exception messages containing literal query values.
- `getThrowable().toString()` used directly as a label.

### 24.3. Use Histograms Instead of Averages Alone

```text
avg command latency = 10 ms
p99 command latency = 1500 ms
```

The average looks healthy while 1% of requests suffer severe delays. Track p99 for pool checkouts and server selection timeouts too.

## 25. Observability: How Metrics, Logs, and Traces Differ

**Metrics:** pre-aggregated numbers suited for alerts and SLOs; keep labels low-cardinality.

**Logs:** contextual event records requiring redaction, scoping, and retention controls.

**Traces:** linked spans from API → service → MongoDB exposing end-to-end latency breakdown.

### 25.1. Example Trace Structure

```text
POST /checkout [480 ms]
  validation [2 ms]
  MongoDB find inventory [10 ms]
  MongoDB update inventory [40 ms]
  MongoDB insert order [35 ms]
  payment RPC [360 ms]
```

Looking only at MongoDB commands hides the 360 ms spent in the payment RPC.

### 25.2. One Trace Is Not Statistical Proof

One fast request trace does not prove p95 is healthy. Metrics capture distributions, while traces explain outlier behavior.

### 25.3. Driver Listeners Do Not Auto-Sample

If you sample traces or command logs, implement sampling in the instrumentation layer while keeping aggregate counters 100% accurate. Never let sampling drop rare but critical failure signals silently.

## 26. Exception Taxonomy: Starting from `MongoException`

Most MongoDB operational errors extend `com.mongodb.MongoException`, though callers can also see:

- `IllegalArgumentException` from invalid inputs.
- `CodecConfigurationException` or BSON serialization errors.
- `NullPointerException` or application bugs.
- Network/TLS/JVM exceptions attached as causes.

**Never catch generic `Exception` and treat all errors as temporary MongoDB outages.**

### 26.1. A Pragmatic Classification Table

| Family | Typical Exceptions | Suggested Handling Focus |
|---|---|---|
| **Server selection / topology** | `MongoTimeoutException` | SDAM state, missing primary, host selection, timeout |
| **Socket / network** | `MongoSocketException` and subclasses | DNS/TCP/TLS/proxy/network, unknown write outcome |
| **Authentication** | `MongoSecurityException`; server command code 18 | Credentials, `authSource`, certs, RBAC |
| **Authorization** | `MongoCommandException` with code 13 | User roles/privileges, fail fast |
| **Write duplicate / conflict** | `MongoWriteException`, `MongoBulkWriteException` | Error codes, unique indexes, idempotency |
| **Write concern** | `MongoWriteConcernException` | Unmet acknowledgment, reconcile state |
| **Server command** | `MongoCommandException` | Error code, labels, command context |
| **Execution timeout** | `MongoExecutionTimeoutException` or timeout code | Query plan, `maxTimeMS`, server load |
| **Transactions** | `MongoException` carrying transaction error labels | Retry body or commit per semantics |
| **Serialization / config** | BSON/codec/config exceptions | Fix code, schema, or config; never loop retries |

### 26.2. Exception Type Alone Cannot Decide Retries

`MongoCommandException` could signal validation errors, auth issues, not-primary errors, or rejected commands. Always inspect error code, error labels, command name, and execution context.

### 26.3. Mind Subclass Ordering in `catch` Blocks

If you catch `MongoException` before `MongoWriteException`, the more specific handler below never executes. Catch specialized subclasses first and general types afterward.

## 27. Distinguishing Four Types of Timeout

| Timeout Type | Stage Where It Occurs | Symptoms / Source |
|---|---|---|
| **Server selection timeout** | Finding an eligible node | `MongoTimeoutException`, cluster description |
| **Pool checkout timeout** | Waiting for a pooled connection | CMAP checkout failed: `TIMEOUT` |
| **Socket / connect timeout** | Socket setup or I/O wait | Socket/network exception and cause |
| **Server execution timeout** | Server caps execution duration | `maxTimeMS`, server timeout error/code |

### 27.1. Server Selection

```text
No server matches ReadPreference.primary
Cause: election, only secondaries visible, bad TLS/DNS, network partition
```

Resolution: inspect SDAM topology, host states, server-side election/quorum, TLS, and firewalls. **Increasing pool size will not elect a primary.**

### 27.2. Pool Checkout

```text
Primary discovered and healthy
Command hasn't started
Checkout fails with TIMEOUT
```

Resolution: inspect pool size, checkout wait durations, active connections, slow queries, app concurrency, and `maxConnecting`.

### 27.3. Socket / Connect

```text
Socket connection refused / read timed out / TLS handshake failed
```

Resolution: check network/TLS/certs/DNS, server load, proxies/load balancers, and client socket timeouts. Watch for **unknown write outcomes** if the request already reached the server before failing.

### 27.4. Server Execution

```javascript
db.orders.find({ status: "CREATED" })
  .maxTimeMS(2000);
```

The server aborts operations exceeding the budget per command semantics and returns a timeout error. Never mask an expensive `COLLSCAN` simply by raising every timeout.

### 27.5. Client-Side Operation Timeout

Java Driver 5.x offers `timeoutMS` (depending on version/API) to enforce an **overall operation budget**. It differs from server-side `maxTimeMS` and alters legacy timeout behavior.

Before tuning, confirm **which timeout actually fired** using exceptions alongside CMAP, SDAM, and command events.

## 28. Common Server Error Groups

| Condition | Signal | Action |
|---|---|---|
| Duplicate key | Error code `11000`; `MongoWriteException` or bulk write error | Check unique index and idempotency |
| Unauthorized | Error code `13` | Fix RBAC/role/namespace; do not retry |
| Authentication failed | Error code `18` | Check user, `authSource`, secret, mechanism |
| Not primary / topology change | Matching server error code / label | SDAM + driver retry + failover handling |
| Write concern failed/timeout | `MongoWriteConcernException` / details | Verify outcome and majority status |
| Execution time exceeded | `maxTimeMS`-related error | Fix query plan, indexes, or server capacity |
| Transient transaction failure | `TransientTransactionError` label | Retry entire transaction safely |
| Unknown transaction commit | `UnknownTransactionCommitResult` label | Retry commit per protocol |

### 28.1. Do Not Hardcode Every Server Error Code into an App Enum

MongoDB releases can add or refine error codes and labels. Favor **API error labels** for retry mechanics where supported, alongside well-known codes like duplicate key (`11000`) for business logic.

### 28.2. Duplicate Key Is Not Automatically an "Infrastructure Outage"

A unique index violation can reflect:

- A legitimate business conflict.
- A client retrying with the same `requestId`.
- An ID-generation bug.
- Duplicate data during migration.

Distinguish these cases cleanly rather than blindly returning HTTP 500.

### 28.3. Authorization (13) Is Not Authentication (18)

- **Authentication:** identity or credentials were rejected.
- **Authorization:** identity succeeded, yet permissions deny the operation.

Each has distinct root causes and runbooks.

## 29. `MongoException.hasErrorLabel()`

The Java Driver supports:

```java
boolean transientTxn =
    e.hasErrorLabel("TransientTransactionError");

boolean unknownCommit =
    e.hasErrorLabel("UnknownTransactionCommitResult");
```

Key labels include:

- `RetryableWriteError`: indicates driver/protocol retry semantics apply.
- `TransientTransactionError`: the **entire transaction** may be retried via transaction APIs.
- `UnknownTransactionCommitResult`: commit outcome is unknown; perform **commit retry** per protocol.
- `NoWritesPerformed`: on supporting server versions, indicates no writes executed across retryable write attempts.
- `ResumableChangeStreamError`: change stream failures that can be resumed cleanly per protocol.

### 29.1. Error Labels Are Not Business Domain Labels

An app may interpret `DuplicateKey` as "order already created," yet that is a domain decision grounded in unique indexes and persisted state—not a retry label for calling `insertOne` forever.

### 29.2. Never Invent Custom Labels Attached to Driver Exceptions

Driver and server control protocol error labels. Your app policy may map them into `retryable`, `reconcile`, or `permanent`, provided that stays an explicit **application classification**, never mistaken for native MongoDB labels.

### 29.3. Distinguish Intent from Outcome

`UnknownTransactionCommitResult` does not mean the transaction aborted. It means **commit status could not be determined when the error occurred**. Re-running the entire business operation risks duplicate side effects.

## 30. Exception Decisions: Fail Fast, Retry, or Reconcile?

Production systems need **action classification**, not merely exception class lists.

| Decision | Meaning | Examples |
|---|---|---|
| **FAIL_FAST** | Return clear error; fix input, role, or config | Authentication, unauthorized, validation |
| **RETRY_BOUNDED** | Bounded retries for eligible operations | Idempotent reads on transient network errors |
| **RETRY_TRANSACTION** | Retry full transaction per protocol | `TransientTransactionError` |
| **RETRY_COMMIT** | Retry commit without re-running body | `UnknownTransactionCommitResult` |
| **RECONCILE_OUTCOME** | Query state by operation ID before acting | Network timeout after sending a write |
| **ALERT_AND_ESCALATE** | Possible infrastructure or data risk | Lost majority, prolonged outage, write concern error |

### 30.1. Three Questions Before Any Retry

1. **Could the failure be transient?** Network failovers differ from duplicate keys.
2. **Is the operation safe to retry?** A `find` differs from charging money or sending a fresh `$inc`.
3. **Are deadlines and retry budgets enforced?** Infinite retries trigger retry storms, violate SLOs, and overload MongoDB.

### 30.2. Unknown Outcome Is Its Own Business State

```text
Client sends write
    |
    +-- Server applied write
    |
    +-- Connection lost before response
    |
    v
Client sees MongoSocketException
```

The application cannot know whether the server applied the write unless verified via deterministic state lookup or protocol-level retries.

### 30.3. Never Retry Based on Exception Class Name Alone

Two `MongoSocketException`s carry totally different risks:

- A side-effect-free `find`: bounded retries are generally reasonable.
- An `$inc` whose reply dropped: retrying as a fresh command can apply it twice.

Classification must combine **operation type + session/transaction state + error labels + domain idempotency**.

## 31. Java Example: Classifier for Business Error Handling

This snippet illustrates **recommending an action**; it does not execute retries itself.

```java
import com.mongodb.MongoException;
import com.mongodb.MongoSocketException;
import com.mongodb.MongoTimeoutException;
import com.mongodb.MongoSecurityException;
import com.mongodb.MongoWriteException;
import com.mongodb.MongoWriteConcernException;
import com.mongodb.MongoCommandException;

public final class MongoErrorDecision394 {
    public enum Decision {
        FAIL_FAST,
        RETRY_OPERATION_IF_SAFE,
        RETRY_TRANSACTION,
        RETRY_COMMIT_ONLY,
        RECONCILE_WRITE_OUTCOME,
        ALERT_AND_INVESTIGATE
    }

    public static Decision classify(
            MongoException e,
            boolean writeOperation,
            boolean transactionOperation) {

        // Inspect error labels before general exception types.
        if (transactionOperation
                && e.hasErrorLabel("UnknownTransactionCommitResult")) {
            return Decision.RETRY_COMMIT_ONLY;
        }

        if (transactionOperation
                && e.hasErrorLabel("TransientTransactionError")) {
            return Decision.RETRY_TRANSACTION;
        }

        if (e instanceof MongoSecurityException) {
            return Decision.FAIL_FAST;
        }

        if (e instanceof MongoWriteException) {
            MongoWriteException write = (MongoWriteException) e;
            if (write.getError().getCode() == 11000) {
                return Decision.FAIL_FAST;
            }
        }

        if (e instanceof MongoCommandException) {
            int code = ((MongoCommandException) e).getErrorCode();
            if (code == 13 || code == 18) {
                return Decision.FAIL_FAST;
            }
        }

        if (e instanceof MongoWriteConcernException) {
            // Write may have applied yet failed to satisfy write concern.
            return Decision.RECONCILE_WRITE_OUTCOME;
        }

        if (e instanceof MongoSocketException) {
            return writeOperation
                    ? Decision.RECONCILE_WRITE_OUTCOME
                    : Decision.RETRY_OPERATION_IF_SAFE;
        }

        if (e instanceof MongoTimeoutException) {
            return writeOperation
                    ? Decision.RECONCILE_WRITE_OUTCOME
                    : Decision.RETRY_OPERATION_IF_SAFE;
        }

        return Decision.ALERT_AND_INVESTIGATE;
    }
}
```

### 31.1. Why Doesn't the Classifier Execute Retries Automatically?

Because it **lacks context** about:

- Whether the write carries an idempotency key.
- Whether the driver's retryable-write protocol was already active.
- Whether the operation ran inside a transaction.
- Remaining request deadline budget.
- Whether the command type is eligible per driver docs.
- Whether domain semantics allow re-applying the effect.

Those responsibilities belong in orchestration/application services.

### 31.2. Evolve the Classifier per Application

The classifier above **omits** `MongoBulkWriteException`, all possible error codes, nested causes, and newer timeout APIs. It demonstrates risk categorization only, not a drop-in production library.

Never "fix" `MongoCommandException` code 13 by granting `root` to an application without proper privilege review.

### 31.3. Error Classification Must Be Tested

Example test matrix:

```text
Duplicate key            -> FAIL_FAST / domain-conflict
Auth failure             -> FAIL_FAST / configuration/security
Unknown commit label     -> RETRY_COMMIT_ONLY
Transient transaction    -> RETRY_TRANSACTION
Network after write      -> RECONCILE_WRITE_OUTCOME
Read selection timeout   -> RETRY_OPERATION_IF_SAFE (bounded)
```

Tests should also verify that raw PII and secrets never leak into exception logs.

## 32. Catching Exceptions in Java Sync Driver

Example inserting an order with a deterministic ID:

```java
import com.mongodb.MongoException;
import com.mongodb.MongoWriteException;
import com.mongodb.MongoTimeoutException;
import com.mongodb.MongoSocketException;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

public final class OrderInsert394 {
    public static void insert(
            MongoCollection<Document> orders,
            String orderId,
            String tenantId) {

        try {
            orders.insertOne(new Document("_id", orderId)
                .append("tenantId", tenantId)
                .append("status", "CREATED"));

            System.out.println("ORDER_CONFIRMED");

        } catch (MongoWriteException e) {
            if (e.getError().getCode() == 11000) {
                // Do not automatically treat duplicate as an infra outage.
                // Verify whether the existing order matches requestId and payload.
                System.out.println("ORDER_ALREADY_EXISTS_CHECK");
            } else {
                throw e;
            }

        } catch (MongoSocketException e) {
            // Outcome may be unknown if the request reached the server.
            System.err.println("ORDER_OUTCOME_UNCERTAIN");
            throw e;

        } catch (MongoTimeoutException e) {
            System.err.println("ORDER_TIMEOUT_INVESTIGATE");
            throw e;

        } catch (MongoException e) {
            System.err.println(
                "ORDER_DATABASE_FAILURE type=" +
                e.getClass().getSimpleName());
            throw e;
        }
    }
}
```

### 32.1. Purpose of Catching Exceptions

This pattern separates **observability from response decisions**, rather than providing a complete idempotent API. Production handlers must reconcile by business `requestId`, verify state on duplicates/timeouts, and never return success merely because an exception was caught.

### 32.2. Do Not Unconditionally Log Full `e.getMessage()`

Some exception strings include topology addresses, command details, or sensitive metadata. Log exception class names, safe error codes/categories, and correlation IDs, restricting full diagnostic details to controlled access levels.

## 33. Bulk Write Exceptions: Partial Failures Can Happen

With `bulkWrite()`, some operations can succeed while others fail depending on ordered vs. unordered mode.

```java
import com.mongodb.MongoBulkWriteException;
import com.mongodb.bulk.BulkWriteError;

try {
    collection.bulkWrite(writeModels);
} catch (MongoBulkWriteException e) {
    for (BulkWriteError error : e.getWriteErrors()) {
        int index = error.getIndex();
        int code = error.getCode();

        // Index maps to the operation's position within the batch.
        // Never log raw documents here.
        System.err.println(
            "Bulk write error index=" + index +
            " code=" + code);
    }

    // Inspect write result and write concern error if present.
    throw e;
}
```

### 33.1. Ordered vs. Unordered

- `ordered=true`: driver/server halt batch execution upon encountering a write error.
- `ordered=false`: operations execute independently; partial ordering is never equivalent to a transaction.

### 33.2. Never Replay an Entire Batch Blindly

If 700 of 1,000 writes succeeded, resending all 1,000 as fresh writes causes duplicate records or double increments.

Track per-item identity/idempotency and reconcile uncertain items selectively.

### 33.3. Write Concern Errors Differ from Write Errors

A command can apply writes to the primary yet still fail write concern satisfaction. Separate document validation/duplicate write errors from **acknowledgment/durability uncertainty**.

## 34. Transaction Labels and Layer-Appropriate Retries

### 34.1. `TransientTransactionError`

When an operation inside a transaction fails with `TransientTransactionError`:

```text
startTransaction
    |
    v
body operations
    |
    v
TransientTransactionError
    |
    v
abort/cleanup
    |
    v
retry entire transaction (bounded)
```

### 34.2. `UnknownTransactionCommitResult`

When commit throws `UnknownTransactionCommitResult`:

```text
transaction body successful
          |
          v
commitTransaction()
          |
          v
unknown commit result
          |
          v
retry commit as prescribed
          |
          v
confirmed outcome or explicit unresolved handling
```

**Never immediately re-run the transaction body just because the commit response dropped**, since the server may have committed already.

### 34.3. Callback API

The driver provides the transaction callback / convenient API on supported versions to apply label-based retries automatically. When using it, always remember the callback can execute multiple times.

### 34.4. External Side Effects

Never place direct SMS, email, or payment-charge calls inside a retryable callback without idempotency or a transactional outbox.

```text
MongoDB transaction:
  update order
  insert outbox event
commit
     |
     v
Outbox worker (idempotent)
     |
     v
Send notification / payment integration
```

### 34.5. Retry Budget

Transaction retries must enforce deadlines and backoff. Never retry endlessly when majority is unreachable, backend services are down, or errors are non-transient.

## 35. Retryable Writes: Driver Retry vs. Business Retry

### 35.1. Driver Retry

In supported deployments, the Java Driver defaults/configures `retryWrites(true)`, retrying eligible single-statement write attempts under qualifying errors via the retryable-write protocol.

### 35.2. Business Retry

An HTTP client sending a second `POST /orders` becomes a **brand new business request** if your backend generates fresh IDs each time, even with `retryWrites=true`.

```text
HTTP POST request R1
  -> insert order O1
  -> server executes
  -> response lost

HTTP POST request R2
  -> backend generates order O2
  -> insert succeeds

=> Double order despite driver retryWrites.
```

### 35.3. Idempotency Key

Example document:

```javascript
{
  _id: "O394-1",
  tenantId: "T01",
  requestId: "CHECKOUT-REQ-394",
  status: "CREATED"
}
```

Unique index:

```javascript
db.orders394.createIndex(
  { tenantId: 1, requestId: 1 },
  { unique: true }
);
```

When `requestId` collides, look up the existing order and verify payload/state before responding. On sharded collections, unique indexes must obey shard-key prefix rules.

### 35.4. `$inc` Risks Double Application

```javascript
db.stats394.updateOne(
  { _id: "orders" },
  { $inc: { count: 1 } }
);
```

Replaying `$inc` as a fresh business command increments twice. Use operation IDs with deduplication, outbox records, or transactional state transitions.

### 35.5. `NoWritesPerformed` Is Not Guaranteed to Appear

`NoWritesPerformed` appears only under specific server conditions/versions and is absent in many failures. **Its absence never proves a write executed.**

## 36. Combined Java Code Registering All Four Listener Groups

Factory class wiring everything together:

```java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

import java.util.concurrent.TimeUnit;

public final class InstrumentedMongoClient394 {
    private InstrumentedMongoClient394() {}

    public static MongoClient create() {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI missing");
        }

        return MongoClients.create(
            MongoClientSettings.builder()
                .applyConnectionString(new ConnectionString(uri))
                .applyToClusterSettings(b -> b
                    .addClusterListener(new WritableTopology394())
                    .serverSelectionTimeout(15, TimeUnit.SECONDS))
                .applyToServerSettings(b -> {
                    b.addServerListener(new ServerChange394());
                    b.addServerMonitorListener(
                        new HeartbeatCounters394());
                })
                .applyToConnectionPoolSettings(b -> b
                    .maxSize(80)
                    .minSize(5)
                    .maxConnecting(4)
                    .addConnectionPoolListener(
                        new PoolCounters394()))
                .addCommandListener(new SafeCommandMetrics394())
                .retryReads(true)
                .retryWrites(true)
                .build());
    }
}
```

### 36.1. Referenced Listener Classes

`WritableTopology394`, `ServerChange394`, `HeartbeatCounters394`, `PoolCounters394`, and `SafeCommandMetrics394` were defined in earlier sections.

Place them in matching source files or nested classes within your project. The factory snippet assumes those classes exist on the classpath rather than representing one self-contained file.

### 36.2. Production Instrumentation

Replace `System.out.println` with controlled metrics, traces, and structured logs. Never let listeners retain unbounded state or call MongoDB inside callbacks.

### 36.3. Do Not Confuse Profile Settings with Diagnostics

`maxSize(80)` above illustrates API usage only. Across 100 service replicas, aggregate connection capacity scales rapidly—plan capacity against cluster connection limits.

## 37. A Non-Destructive Lab to Generate Command Events

### 37.1. Create Client and Run `ping`

```java
import com.mongodb.client.MongoClient;
import org.bson.Document;

try (MongoClient client = InstrumentedMongoClient394.create()) {
    Document result = client.getDatabase("admin")
        .runCommand(new Document("ping", 1));

    System.out.println(
        "Ping result ok=" + result.get("ok"));
}
```

`ping` sends an application-level command that fires command monitoring events, unlike internal `hello` monitoring handshakes.

### 37.2. Read-Only Query

```java
long count = client
    .getDatabase("driver_lab_394")
    .getCollection("sample394")
    .countDocuments();

System.out.println("count=" + count);
```

If the collection does not exist, `countDocuments()` returns 0 cleanly without dropping or recreating real data just to test listeners.

### 37.3. Observing Events

Running a read emits events across layers:

- SDAM cluster/server events during discovery.
- CMAP pool opened, connection created/ready.
- Checkout and check-in.
- Command started and succeeded.

Do not expect an exact **1:1 event ratio per request**; connection pooling, reuse, and background heartbeats alter counts.

### 37.4. Trigger Intentional Errors Only in Lab Environments

To test `DuplicateKey`, use a dedicated lab collection and synthetic IDs—never inject bad passwords, network drops, or stepdowns into production.

## 38. Minimal Dashboard for Java + MongoDB

```text
┌────────────────────────────────────────────────────┐
│ MongoDB Java Driver Health — order-api              │
├────────────────────────────────────────────────────┤
│ Topology                                             │
│ writable server known: yes                           │
│ server description changes (5m): 2                   │
│ heartbeat failure rate: 0.1%                         │
├────────────────────────────────────────────────────┤
│ Pools                                                │
│ total in-use / available: 45 / 55                    │
│ checkout p95: 3 ms; p99: 35 ms                       │
│ checkout failures: 0.02% (TIMEOUT)                   │
│ pool clears (5m): 1                                 │
├────────────────────────────────────────────────────┤
│ Commands                                             │
│ find p95: 18 ms; update p95: 35 ms                   │
│ command failure rate: 0.2%                           │
│ top failure family: not-primary during election      │
├────────────────────────────────────────────────────┤
│ Application                                          │
│ HTTP 5xx: 0.3%; checkout SLO: degraded              │
│ retry attempts/request: increasing                   │
└────────────────────────────────────────────────────┘
```

The numbers above are **mock data**. Real deployments must break down metrics by `MongoClient`, server, cluster, application version, and sampling window.

### 38.1. Add Server-Side Metrics

Pair driver dashboards with:

- Replica set elections and primary availability.
- Replication lag and oplog window.
- MongoDB CPU, memory, and disk IOPS.
- `connections.current` versus connection limits.
- Slow query logs, profiler data, and index usage.
- Network throughput and latency.

### 38.2. Always Label Charts with Units

- Seconds for pool checkout latency.
- Milliseconds or microseconds for command latency.
- Monotonically increasing counters.
- Point-in-time gauges (never summed like counters).

### 38.3. Never Use Averages as Proof of Healthy p99

Latency distributions have long tails; p95 and p99 surface user pain even when averages look great.

## 39. Symptom-Based Alerts and Thresholds

| Alert | Suggested Condition | Primary Investigation Path |
|---|---|---|
| No writable server | Persists past grace window | SDAM, election, quorum, network |
| Rising heartbeat failures | Sustained increase on a server | Network, TLS, host health |
| High pool checkout p99 | Breaches SLO for several minutes | Pool utilization, slow queries, app concurrency |
| Pool checkout `TIMEOUT` | Rising failure rate | Exhaustion, leaks, `maxConnecting` |
| Pool clear storm | Frequent clears per minute | Stepdowns, connection resets, proxy |
| High command duration p99 | Spiking on a specific command | `explain`, indexes, server resources |
| Rising command failures | Grouped by command & exception family | Recent app releases, server changes |
| Authentication failures | Appears after deploy or rotation | Secrets, `authSource`, CAs |
| Unknown write outcomes | Anomalies on critical flows | Reconciliation and idempotency |
| Transaction retry spike | Tracks failover or contention | Elections, write conflicts |
| Silent instrumentation | Events/metrics vanish | Listener wiring, telemetry exporter |

### 39.1. Tune Thresholds per Workload

Avoid rigid universal rules like "checkout > 10 ms is critical" for every app. Heavy analytics, cross-region calls, cold starts, and bursty APIs have distinct baselines.

### 39.2. Alert on SLO Burn + Duration

A 1-second election blip rarely needs paging, whereas 5 minutes with no primary on the checkout service is severe. Tie alerts to sustained business impact.

### 39.3. Never Treat Missing Metrics as Zero Errors

If a listener is detached or the process crashes, a flat `command_failed_total` does not mean every command is succeeding. Alert on **missing telemetry**.

## 40. Runbook 1 — Server Selection Timeout During Primary Failover

### Symptoms

```text
MongoTimeoutException:
Timed out while waiting for a server
that matches ReadPreferenceServerSelector{readPreference=primary}
```

### Investigation

1. Inspect `ClusterDescriptionChangedEvent` before and after the error.
2. Check `ServerDescriptionChangedEvent` and heartbeat failures.
3. Verify primary state on MongoDB/Atlas/`rs.status()` if authorized.
4. Check voting majority and election history.
5. Verify DNS, SRV records, TLS, and firewalls from the application host.
6. Confirm the URI specifies the right `replicaSet` without an accidental `directConnection=true`.
7. Correlate API failure rates, retry latency, and affected pods.

### Response

- Election in progress: rely on driver retries, bounded request deadlines, and backpressure.
- TLS/DNS mismatch: fix certificates or networking; never disable validation.
- Lost quorum: restore member/connectivity per runbook; never blindly force replica set reconfiguration.

### What **Not** to Do

Never raise `maxPoolSize` when the cluster lacks a primary. Never restart all app pods simultaneously, which triggers a connection storm.

## 41. Runbook 2 — Pool Checkout Timeout While Primary Is Healthy

### Symptoms

```text
Topology writable = true
Heartbeat success = normal
Command duration p95 = 15 ms
Pool checkout p99 = 3 seconds
CheckoutFailed reason = TIMEOUT
```

### Investigation

1. Inspect active, idle, and waiting pool metrics per server.
2. Check `maxPoolSize`, `maxConnecting`, and client timeouts.
3. Check app concurrency and total `MongoClient` count.
4. Search for cursors or transactions pinning connections too long.
5. Check latency tails of slow background queries.
6. Verify server connection limits, CPU, and disk saturation.

### Remediation

- Shed or throttle bursts using backpressure and queue limits.
- Fix unclosed cursors and overly long transactions.
- Tune slow queries and missing indexes.
- Adjust pool size or warm-up settings if server capacity permits.
- Never raise pool sizes unconditionally to infinity.

### Resolution Criteria

Checkout p95/p99 returns to baseline, checkout failures drop to zero, server connections stay within budget, and API p95 stabilizes.

## 42. Runbook 3 — Continuous Pool Clears After Deployment

### Symptoms

```text
poolCleared rate rising
ConnectionCreated/sec rising
TLS handshakes/sec rising
CommandFailed rising
```

### Investigation

- Did the deployment alter CAs, certificates, or hostnames?
- Is the primary cycling elections repeatedly?
- Is traffic passing through an incompatible load balancer or proxy?
- Is `maxIdleTimeMS` configured too aggressively?
- Is code creating a fresh `MongoClient` per request?
- Are network idle timeouts or firewalls resetting connections?

### Remediation

Correlate timelines, fix networking/TLS/client lifecycle bugs, and use rolling rollouts. A single pool clear during an election is **not** an incident on its own.

## 43. Runbook 4 — Command Latency Rises While Pool Checkout Stays Fast

### Symptoms

```text
checkout p99 = 3 ms
find command p99 = 2.5 s
serverSelection stable
```

### Investigation

1. Group slow commands by command name and query shape using safe metadata logs.
2. Run `explain("executionStats")` on representative queries.
3. Check `totalDocsExamined`, `totalKeysExamined`, and `COLLSCAN`.
4. Measure server disk, CPU, cache hit ratios, network, and lock waits.
5. Check recent index changes, bloated documents, or N+1 query loops.
6. Verify whether latency rose across all services or a single endpoint.

### Remediation

Optimize filters, indexes, projections, and pagination; cut N+1 fan-out; or scale capacity with evidence. **Increasing pool size never fixes a bad query plan.**

## 44. Runbook 5 — Duplicate Key Spike After Failover

### Symptoms

```text
Election occurred
Driver command retries increased
API POST /orders duplicated
MongoWriteException code=11000
```

### Investigation

- Do duplicates share the same business `requestId`?
- Did the backend generate fresh IDs during HTTP retries?
- Is a unique index protecting the scoped key?
- Did duplicate webhooks or payment calls occur?
- Can you look up the prior request's state cleanly?

### Response

1. Patch missing application-level idempotency around retries.
2. Reconcile affected orders, payments, and inventory.
3. Separate expected idempotent collisions from corrupted duplicates.
4. Never auto-delete duplicate records before assessing business impact.
5. Add integration tests simulating dropped replies after server commit.

## 45. Runbook 6 — Authentication or TLS Failures

### Symptoms

```text
MongoSecurityException
MongoCommandException code 18
MongoCommandException code 13
TLS handshake failure / certificate verify failed
```

### Investigation

- Did secret rotation finish across every service replica?
- Do `authSource`, username, and auth mechanism match?
- Does the DB user hold roles on the target database/collection?
- Do CA trust stores, SANs, and hostnames match?
- Could clock skew invalidate certificates?
- Did network policies or private endpoints change?

### Action

Fix credentials, roles, and certificates under security policy, rotating exposed secrets if needed. Never escalate roles to `root` or disable TLS verification as a "temporary workaround".

## 46. Runbook 7 — Unknown Transaction Commit Result

### Symptoms

`MongoException.hasErrorLabel("UnknownTransactionCommitResult") == true` thrown at commit.

### Investigation

- Was the driver core transaction API or callback API used?
- Did the transaction already dispatch commit?
- Can state be queried by business operation ID?
- Did the error coincide with an election or network partition?
- Were any external side effects embedded in the callback?

### Response

Follow driver protocol: retry **commit** as appropriate; if retries exhaust deadlines with outcome still unknown, record state as pending reconciliation instead of fabricating success or blindly re-running the entire workflow.

### What Not to Do

Never resend payment charges or notifications without idempotency; never drop collections or spin up duplicate workflows merely because the commit reply vanished.

## 47. Runbook 8 — Users Report Slow API While MongoDB Commands Are Fast

### Symptoms

```text
HTTP p95 = 2s
Command p95 = 15ms
Pool checkout p95 = 1ms
SDAM stable
```

### Investigation

- Application serialization/deserialization overhead.
- HTTP server thread or connection pool saturation.
- JVM GC pauses or CPU throttling.
- Slow downstream HTTP services.
- Contended locks in business code.
- N+1 patterns: dozens of fast commands summing to a slow request.
- Long cursor/transaction loops performing many `getMore` calls.
- Uninstrumented server selection waits before commands start.

Never blame MongoDB for every API slowdown simply because it is the primary database.

## 48. Using OpenTelemetry and Micrometer Safely

### 48.1. With Spring Boot

A service commonly integrates:

- Spring Boot Actuator / Micrometer for request timers and counters.
- OpenTelemetry for distributed tracing.
- JMX pool monitoring or CMAP metrics adapters.
- `CommandListener` or official MongoDB instrumentation spans.

Avoid stacking overlapping auto-instrumentation blindly without checking for **duplicate spans/metrics** and sampling overhead.

### 48.2. Micrometer Histogram Example

Illustrative code if `micrometer-core` is on the classpath:

```java
import com.mongodb.event.CommandListener;
import com.mongodb.event.CommandSucceededEvent;
import com.mongodb.event.CommandFailedEvent;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.Set;
import java.util.concurrent.TimeUnit;

public final class CommandTimer394 implements CommandListener {
    private static final Set<String> ALLOWED =
        Set.of("find", "insert", "update",
               "delete", "aggregate", "getMore");

    private final MeterRegistry registry;

    public CommandTimer394(MeterRegistry registry) {
        this.registry = registry;
    }

    private String commandLabel(String name) {
        return ALLOWED.contains(name) ? name : "other";
    }

    private void record(String command, String outcome, long nanos) {
        Timer.builder("mongodb.client.command.duration")
            .tags("command", commandLabel(command),
                  "outcome", outcome)
            .register(registry)
            .record(nanos, TimeUnit.NANOSECONDS);
    }

    @Override
    public void commandSucceeded(CommandSucceededEvent event) {
        record(event.getCommandName(), "success",
               event.getElapsedTime(TimeUnit.NANOSECONDS));
    }

    @Override
    public void commandFailed(CommandFailedEvent event) {
        record(event.getCommandName(), "failure",
               event.getElapsedTime(TimeUnit.NANOSECONDS));
    }
}
```

### 48.3. Why Maintain an Allowlist?

Standard command names form a small bounded set, yet an explicit allowlist guarantees custom commands never blow up label cardinality. Never tag metrics with raw queries or user-defined collection names.

### 48.4. Avoid Synchronous Exporters

Recording metrics into an in-memory registry is far cheaper than synchronous HTTP calls in callbacks. Let a periodic exporter or sidecar scrape metrics asynchronously rather than pushing to Prometheus per command.

## 49. Lab Observability Test Plan

### 49.1. Verification Goals

- Listeners are wired properly.
- SDAM state transitions are captured.
- Pool checkout durations and failures reflect real behavior.
- Command events and durations use consistent units.
- Exception classification produces safe decisions.
- Zero PII or secrets leak into logs or metrics.

### 49.2. Non-Destructive Baseline Checks

1. Start the service with a valid lab connection string.
2. Run `ping` and `find` on a test collection.
3. Verify `CommandSucceededEvent`, checkout/checkin events, and writable topology view.
4. Confirm histograms receive samples with zero callback exceptions.
5. Close `MongoClient` and confirm pool close lifecycle events fire cleanly.

### 49.3. Authorized Lab Fault Injection

- Bad hostname URI: observe server selection/connection failures.
- Bad lab credentials: observe authentication rejection.
- Missing role in lab: observe authorization code 13.
- Duplicate unique key: observe code 11000.
- Slow query on synthetic dataset: observe duration and `maxTimeMS`.
- Controlled lab failover: observe SDAM updates, pool clear, and retries.
- Bounded load test: observe pool checkout queueing and tail latency.

**Never inject deliberate failures in production** just to verify monitoring works.

### 49.4. Expect Correlation, Not Exact Event Counts

Never write brittle tests asserting every `find` triggers exactly one heartbeat or one `ConnectionCreatedEvent`. Connection reuse and background monitoring cause counts to vary naturally.

### 49.5. Data Protection Test

Submit a synthetic lab document containing `fake-secret-394` and verify:

- It never appears in metric labels.
- It never appears in standard application logs.
- `CommandListener` never logs raw BSON payloads.
- Tracing exporters and pipelines retain no sensitive payloads.

## 50. Sharded Clusters and Load-Balanced Deployments

### 50.1. Sharded Clusters

Normally the Java Driver connects to `mongos` routers rather than targeting shard primaries directly via a replica set URI.

```text
Java MongoClient
   |
   +-- Pool mongos-a
   +-- Pool mongos-b
   |
   +-- Routes to shards via mongos
```

Monitor:

- `mongos` server selection.
- Pool checkout and socket errors per router.
- Command latencies for cross-shard queries.
- Underlying shard replica set metrics and alerts server-side as needed.

### 50.2. Load-Balanced Mode

Behind supported load balancers, SDAM heartbeat semantics differ from replica sets and **heartbeat events may not be emitted at all**.

Never assume "heartbeat count = 0" means the database is down; rely on pool, command, application probes, and load balancer telemetry.

### 50.3. Atlas

MongoDB Atlas provides rich server and cluster telemetry, yet client-side SDAM, CMAP, and command monitoring remain vital because Atlas cannot see **time spent waiting on pool checkout inside your JVM**.

### 50.4. Self-Managed Deployments

Beyond driver events, operations require `serverStatus`, replica set monitoring, network/disk logs, slow query analysis, and host metrics. Neither client nor server telemetry replaces the other.

## 51. Security and Observability Boundaries

### 51.1. Fields to Exclude

- Connection strings containing usernames or passwords.
- Raw commands, filters, and update documents.
- Full `Throwable.toString()` when query literals appear.
- Raw user IDs, emails, or phone numbers.
- Session credentials, private keys, or JWTs.
- Unbounded request IDs in metric labels.

### 51.2. Access Tiers

| Audience | Appropriate Telemetry |
|---|---|
| Developer | Aggregated latency/error metrics and sanitized logs |
| On-call SRE | Topology, pool, and command metrics; safe host labels |
| DBA | Server-side status, query plans, cluster alerts |
| Security | Audit logs, access anomalies, redaction verification |
| Break-glass | Deeper diagnostics under explicit time-limited approval |

### 51.3. Driver Events Are Infrastructure Metadata

Hostnames, database names, query shapes, and failure reasons expose deployment architecture; protect them with TLS, RBAC, retention limits, and centralized logging policies like any operational data.

### 51.4. Instrumentation Overhead

Command volume can be massive:

```text
10,000 commands/sec
-> logging 1 KB/command
-> ~10 MB/sec of logs (rough estimate)
```

Never enable verbose per-command logging permanently. Rely on counters, histograms, targeted sampling, and time-bounded diagnostics.

## 52. Common Anti-Patterns

| Anti-Pattern | Problem | Better Alternative |
|---|---|---|
| Creating `MongoClient` per HTTP request | Excessive pools and handshakes | Managed singleton |
| Blaming every `MongoTimeoutException` on pool exhaustion | Could be server selection | Check SDAM vs. CMAP |
| Treating `CommandSucceededEvent` as total request latency | Misses selection, checkout, and app time | End-to-end distributed tracing |
| Using `ping` to claim all writes will succeed | Checks neither majority nor business logic | Proper readiness/write checks |
| Logging `event.getCommand()` | Exposes PII and secrets | Allowlisted metadata only |
| Making synchronous HTTP calls in listeners | Blocks driver threads | Async/bounded metric exporters |
| Putting full exception messages in metric labels | Cardinality blowup & data leaks | Bounded error family/code/label |
| Reading awaited heartbeat elapsed time as network RTT | False slow-network alarms | Check `isAwaited()` |
| Paging on zero heartbeats in load-balanced mode | False outage alarms | Mode-aware monitoring |
| Equating command counts 1:1 with HTTP requests | Cursors/`getMore`/txns emit multiple commands | Trace correlation |
| Treating `maxPoolSize` as a cluster-wide cap | Pools are per server | Fleet-wide capacity math |
| Enlarging `maxPoolSize` for slow queries | Amplifies server overload | `explain`/indexes + sizing |
| Increasing `maxConnecting` arbitrarily | Connection handshake storms | Load benchmarking |
| Assuming pool cleared = connection leak | Often caused by failover | Correlate SDAM & network events |
| Assuming `TIMEOUT` checkout failure = server down | Often pool saturation | Check in-use/wait metrics |
| Tuning timeouts without outer request deadlines | Backlog and queueing | CSOT + deadline budgets |
| Retrying every `MongoException` | Infinite loops / corrupt writes | Use labels + operation semantics |
| Treating `UnknownTransactionCommitResult` as aborted | Duplicate side effects | Retry commit / reconcile |
| Using `RetryableWriteError` to handle duplicate HTTP POSTs | Duplicate orders | Business idempotency key |
| Treating write concern timeouts as "not written" | Write may have applied | State reconciliation |
| Catching `MongoException` ahead of subclasses | Unreachable specific handlers | Catch specialized subclasses first |
| Disabling TLS verification after failover | Critical security gap | Fix CA/SAN/DNS |
| Skipping missing-telemetry tests | Silent observability blind spots | Alert on missing metrics |
| Looking only at client telemetry | Misses server bottlenecks | Combine Atlas/server metrics |
| Looking only at server metrics | Misses pool and selection waits | Client instrumentation |
| Forcing primary stepdown on production to test alerts | Threatens availability | Controlled staging drills |

## 53. Practice Exercises

### Exercise 1 — Four Diagnostic Layers

An HTTP request takes 3 seconds while the MongoDB command duration is only 5 ms. What stages outside command execution could consume that time, and which metrics reveal each stage?

### Exercise 2 — Topology Listener

Write a `ClusterListener` maintaining a gauge of `1` when a writable server exists and `0` otherwise. Why doesn't this gauge guarantee a majority write will succeed?

### Exercise 3 — Server Listener

Write a `ServerListener` logging transitions from `REPLICA_SET_PRIMARY` to `REPLICA_SET_SECONDARY` using sanitized metadata.

### Exercise 4 — Heartbeats

`ServerHeartbeatSucceededEvent.getElapsedTime()` returns 10 seconds with `isAwaited() == true`. Should you report 10 seconds of network RTT? Explain why or why not.

### Exercise 5 — Load-Balanced Mode

A service running in load-balanced mode emits zero heartbeat events even though commands succeed normally. Is instrumentation broken?

### Exercise 6 — Pool Lifecycle

Trace the lifecycle `ConnectionPoolOpened` → `ConnectionCreated` → `ConnectionReady` → `ConnectionCheckedOut` → `ConnectionCheckedIn` → `ConnectionClosed`. Why isn't there a `ConnectionCreated` event for every checkout?

### Exercise 7 — CMAP Failures

Design `connectionCheckOutFailed` counters split by failure reason alongside a checkout-duration histogram. When should you declare a pool exhaustion incident?

### Exercise 8 — Pool Sizing

40 app instances each run one `MongoClient` with `maxPoolSize=100` targeting a primary. Compute the theoretical pooled connection ceiling on the primary and list factors making actual connection counts differ.

### Exercise 9 — `maxConnecting`

After a rollout, `connectionCreated` climbs slowly, request queues grow, yet pools sit below max size. What role does `maxConnecting` play, and what should you benchmark?

### Exercise 10 — Connection Leaks

Active pool connections keep climbing while command latency stays flat and several long transactions remain open. Formulate hypotheses and diagnostic steps without immediately raising `maxPoolSize`.

### Exercise 11 — `CommandListener`

Write a listener counting `find`, `aggregate`, and `update` successes and failures by command name without ever logging raw BSON payloads.

### Exercise 12 — Cursors

An API endpoint iterates 20,000 documents via a cursor using multiple `getMore` calls. Why do many command events appear for one HTTP request?

### Exercise 13 — Metric Labels

Given labels `commandName`, `databaseName`, `requestId`, `tenantId`, and `exceptionMessage`, which labels pose Prometheus cardinality risks? Propose a safe replacement schema.

### Exercise 14 — Server Selection Timeout

The replica set already elected a new primary, yet Java reports server selection timeouts. Explain how to inspect `ClusterDescription`, DNS, `replicaSet` name, TLS, and URI.

### Exercise 15 — Checkout Timeout

Topology is stable and command p95 is 20 ms, yet pool checkout p99 hits 2 seconds. List three possible causes and how to distinguish them.

### Exercise 16 — Socket Exception

A client sends an update and gets connection reset. Can you conclude the update never happened? Design reconciliation by operation ID.

### Exercise 17 — Error Code 11000

A retried HTTP POST hits code 11000 creating a duplicate order. Why shouldn't you blindly map 11000 to HTTP 500? What business attributes must you compare?

### Exercise 18 — AuthN vs. AuthZ

Distinguish error codes 18 and 13. If a Java service lacks permissions on a new collection, what should you fix and what must you avoid doing?

### Exercise 19 — Error Labels

Contrast `TransientTransactionError` and `UnknownTransactionCommitResult` regarding retrying the transaction body vs. retrying commit.

### Exercise 20 — Retry Budget

A service immediately retries every failed command 20 times during a primary election. What risk does this pose to the newly elected primary? Design bounded retries with backoff and jitter.

### Exercise 21 — Bulk Writes

A batch of 1,000 inserts hits 20 duplicate keys. Contrast ordered vs. unordered execution, and explain why you must never replay the entire batch blindly without inspecting write results.

### Exercise 22 — Micrometer

Create a command duration histogram tagged by an allowlisted `commandName` and `outcome`. Why must `orderId` never be a tag?

### Exercise 23 — Tracing

Total HTTP request duration is 500 ms while MongoDB commands total 60 ms. Sketch a sample trace showing other spans and how to verify where the remaining latency went.

### Exercise 24 — Pool Clears

Following an election, `poolCleared` spikes once and settles back down. When is this healthy recovery, and when should it trigger an alert?

### Exercise 25 — Spring Boot Readiness

All pods restart simultaneously during a brief primary election. Redesign liveness and readiness probes to prevent restart storms without returning false success when writes are failing.

### Exercise 26 — Driver Observability Security

A `CommandListener` logs `event.getCommand().toJson()`, exposing user emails and password reset tokens. Propose code fixes, remediation for already-ingested logs, and regression tests.

### Exercise 27 — Staging Failover Drill

Design a failover drill on a lab replica set: capture baselines, run an authorized planned stepdown, observe SDAM/pool/command events, and confirm API self-recovery.

### Exercise 28 — End-to-End Timeline Scenario

Given the timeline:

```text
10:00:00 primary A steps down
10:00:01 SDAM no writable server
10:00:01 pool A cleared
10:00:04 new primary B discovered
10:00:05 pool checkout p99 500ms
10:00:06 command p99 25ms
10:00:07 API errors back to baseline
```

Distinguish election duration, driver recovery time, pool warm-up duration, and user-visible impact.

### Exercise 29 — Error Classifier

Build a decision table covering `MongoTimeoutException`, `MongoSocketException`, `MongoWriteException`, `MongoWriteConcernException`, `MongoCommandException`, and transaction labels, mapping each to fail-fast, retry, or reconcile.

### Exercise 30 — Complete Observability Design

Architect observability for a 100-pod Java service talking to a MongoDB Atlas replica set:

1. One `MongoClient` per pod.
2. SDAM, CMAP, and command listeners feeding metrics.
3. Timeout and retry budgets.
4. Application idempotency for checkout.
5. Log redaction and PII controls.
6. Prometheus histograms and alerts.
7. Runbooks for failover, pool exhaustion, auth/TLS, and duplicate keys.
8. Staging test plan with pass/fail evidence criteria.

## 54. Pre-Production Deployment Checklist

### 54.1. MongoClient and SDAM

1. Java Driver version verified compatible with MongoDB deployment.
2. One long-lived `MongoClient` managed by the process or DI container.
3. Valid replica set / SRV URI without pinning a single primary.
4. DNS, TLS, SANs, and `authSource` tested from the app runtime environment.
5. Visibility into cluster, server, and heartbeat monitoring.
6. No false heartbeat alerts in load-balanced mode.
7. Server selection timeout aligned with outer request deadlines.

### 54.2. Pools

1. Pool sizes and `maxConnecting` benchmarked across the full pod fleet.
2. Checkout duration histograms and reason-split failure counters instrumented.
3. Visibility into connections created, closed, and pools cleared.
4. Active, idle, and waiting pool counts monitored via JMX or custom state.
5. Cursors and transactions reliably closed within scope.
6. Zero per-request `MongoClient` instantiation.
7. Backpressure configured to prevent retry and connection storms.

### 54.3. Commands and Exceptions

1. Command latency segmented by operation type and outcome.
2. Zero raw BSON commands or credentials written to logs.
3. Exceptions classified cleanly by type, error code, and error label.
4. Retryable reads/writes aligned with driver semantics.
5. Business idempotency and unknown-outcome reconciliation implemented.
6. Transaction error labels handled distinctly for body vs. commit.
7. Bulk write errors handle partial batch success properly.

### 54.4. Metrics and Operations

1. p95/p99 SLOs defined for API and DB stages.
2. Alerts configured for missing writable servers, pool timeouts, and command failures.
3. Dashboards unify SDAM + CMAP + commands + server metrics.
4. Zero unbounded or PII labels in metrics.
5. Alerts configured for silent/missing telemetry pipelines.
6. Failover drills and incident runbooks tested in staging.
7. Clear ownership assigned for investigation, rollback, and tuning.

## 55. Summary

**The MongoDB Java Driver spans multiple operational layers that no single exception string can summarize.** SDAM determines which nodes can accept operations; CMAP manages connection pools; command monitoring observes dispatched commands; and exception types, error codes, and error labels drive decisions to fail fast, retry, or reconcile.

**Pinpointing where latency lives is step one of optimization.** Failing to locate a primary is not pool exhaustion; slow pool checkouts are not slow server queries; `CommandSucceededEvent` excludes full HTTP request time; and awaited heartbeat durations do not equal network RTT.

**Keep listeners lightweight and safe.** Register `ClusterListener`, `ServerListener`, `ServerMonitorListener`, `ConnectionPoolListener`, and `CommandListener` via `MongoClientSettings`; emit low-cardinality counters and histograms; never log raw commands or secrets; and never perform blocking I/O inside callbacks.

**Error classification is a constrained business decision.** `MongoTimeoutException`, `MongoSocketException`, `MongoWriteException`, `MongoWriteConcernException`, and `MongoCommandException` convey distinct failure semantics. Labels `TransientTransactionError` and `UnknownTransactionCommitResult` dictate body vs. commit retries—never replacing checkout or payment idempotency.

**Measure resilience end-to-end from user to database.** Great dashboards unite topology availability, pool wait/failure metrics, command latency/errors, HTTP SLOs, and server telemetry. During failovers, success means not just "a new primary exists" but **clients discover it cleanly, pools stabilize, zero business actions duplicate, and users receive accurate responses**.

## 56. Reference Documentation

- [MongoDB Java Sync Driver — Monitoring](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/monitoring/): SDAM, command, and connection pool listeners.
- [MongoDB Java Sync Driver — Logging](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/logging/): logging and sensitive data protection.
- [MongoDB Java Sync Driver — Connection Pools](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/connection-pools/): `maxPoolSize`, `maxConnecting`, timeouts, and JMX.
- [MongoDB Java Sync Driver — Cluster Settings](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/cluster-settings/): server selection and `ClusterListener`.
- [MongoDB Java Sync Driver — Server Settings](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/server-settings/): `ServerListener`, heartbeats, and monitoring modes.
- [MongoDB Java Sync Driver — Connection Troubleshooting](https://www.mongodb.com/docs/drivers/java/sync/current/connection/connection-troubleshooting/): network, authentication, timeouts, and topology diagnostics.
- [MongoDB Java Sync Driver — Limit Execution Time](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/limit-execution-time/): Client-Side Operation Timeout and timeout settings.
- [MongoDB Java Driver API — com.mongodb.event](https://mongodb.github.io/mongo-java-driver/5.6/apidocs/driver-core/com/mongodb/event/package-summary.html): listener and event APIs.
- [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/): retryable-write protocol and limitations.
- [MongoDB Manual — Retryable Reads](https://www.mongodb.com/docs/manual/core/retryable-reads/): read operation retries.
- [MongoDB Manual — Transactions in Applications](https://www.mongodb.com/docs/manual/core/transactions-in-applications/): `TransientTransactionError` and `UnknownTransactionCommitResult`.
- [MongoDB Manual — Server Discovery and Monitoring](https://github.com/mongodb/specifications/blob/master/source/server-discovery-and-monitoring/server-discovery-and-monitoring.md): SDAM behavior and driver semantics.
- [MongoDB Driver Specifications — Connection Monitoring and Pooling](https://github.com/mongodb/specifications/blob/master/source/connection-monitoring-and-pooling/connection-monitoring-and-pooling.md): CMAP events, checkout, and pool lifecycle.
- [MongoDB Driver Specifications — Command Logging and Monitoring](https://github.com/mongodb/specifications/blob/master/source/command-logging-and-monitoring/command-logging-and-monitoring.md): command event fields and redaction.
