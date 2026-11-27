# Connection Pools, Server Selection, and Timeout Types

A Java application using MongoDB sometimes encounters the message:

~~~text
com.mongodb.MongoTimeoutException:
Timed out after 30000 ms while waiting for a server
that matches ReadPreferenceServerSelector{readPreference=primary}
~~~

The knee-jerk reaction is often to raise `maxPoolSize`, assuming "the driver ran out of connections." Yet the error above says **the driver could not select an eligible server** (for example, no primary was found)—not necessarily that the pool is full. Conversely, a request might select a primary yet **fail to obtain a connection from the pool**; or obtain a connection and **the query runs slowly**; or the socket **cannot open** due to networking. Each situation requires different diagnostics and configuration.

This lesson, **"Connection Pools, Server Selection, and Timeout Types"**, belongs to the **Java Driver** chapter of the *Database Engine Document MongoDB* module. It systematically explains how the **MongoDB Java Sync Driver** manages connections, discovers topology, selects servers, and applies timeouts. The emphasis is on **understanding the mechanisms, Java APIs, real-world errors, measurements, and tuning workflow** rather than randomly increasing numbers.

## Learning Outcomes

After this lesson, you will be able to:

1. Explain the lifecycle of a `MongoClient` and why clients must be reused.
2. Distinguish **per-server connection pools**, server monitoring sockets, and actual TCP connection counts.
3. Distinguish SDAM/topology discovery from pool checkout and server command execution.
4. Explain how the driver chooses **primary, secondary, and nearest**, read preference, latency window, and server selection timeout.
5. Configure `maxPoolSize`, `minPoolSize`, `maxConnecting`, `maxIdleTimeMS`, `maxLifeTimeMS`, and `waitQueueTimeoutMS`.
6. Distinguish `serverSelectionTimeoutMS`, `connectTimeoutMS`, `socketTimeoutMS`, `maxTimeMS`, `waitQueueTimeoutMS`, and `timeoutMS` (CSOT).
7. Use Java Sync Driver configuration via URI and `MongoClientSettings`, and understand option precedence.
8. Set service-level deadlines and handle timeouts, failovers, and retries without duplicating data.
9. Use CMAP, SDAM, command monitoring, and JMX to diagnose where requests are waiting.
10. Complete exercises on sizing, timeout budgets, server selection, and incident verification.

> **Version Note:** Examples primarily target **MongoDB Java Sync Driver 5.x**. Certain APIs (notably `timeout()`/CSOT, cursor timeout modes, and transaction timeouts) are new or have different semantics in 4.x. Current MongoDB Java Driver documentation still marks **CSOT as experimental**. Always check the documentation for the exact driver version you run rather than assuming Java 5.x defaults apply to other drivers. Latency and pool size numbers in examples are illustrative only.

## 1. End-to-End Path of a MongoDB Operation

~~~text
Java app calls collection.find(...).first()
                   |
                   v
       Build command + deadline
                   |
                   v
    Select server per topology/read preference
       [SDAM + server selection]
                   |
                   v
     Check out connection from that server's pool
       [CMAP: idle / create / wait / timeout]
                   |
                   v
       Send command over network socket
                   |
                   v
          mongod / mongos executes
        [query plan, locks, CPU, I/O]
                   |
                   v
        Receive response / cursor batch
                   |
                   v
     Return connection to pool per lifecycle
                   |
                   v
       Return Java result / throw exception
~~~

Do not interpret this diagram as *always* performing exactly one checkout per API call: a cursor involves multiple `getMore` calls; an operation may retry; transactions exhibit **connection pinning**; and load-balanced topologies behave differently. Use this as a mental model to separate **where time is spent and what failed**.

### 1.1. Five Distinct Stages

| Stage | Work Performed | If Slow or Failing |
|---|---|---|
| **Server discovery** | Monitors determine which server is primary/secondary/`mongos`, its health, and latency. | SDAM/topology issue. |
| **Server selection** | Selects a server matching read preference, tags, freshness, and latency. | `serverSelectionTimeoutMS` or CSOT. |
| **Connection checkout** | Leases a pooled connection or waits for a new/returned socket. | Legacy `waitQueueTimeoutMS` or CSOT. |
| **Socket/command** | TCP/TLS/auth, sending/receiving BSON commands, server execution. | `connectTimeoutMS`, `socketTimeoutMS`, `maxTimeMS`, CSOT, network/server error. |
| **Result lifecycle** | Consuming cursor, `getMore`, releasing resources, transaction commit/abort. | Cursor/transaction timeout, cancellation/cleanup. |

User-perceived latency is the **sum of these stages plus application overhead**:

\[
T_{\mathrm{HTTP}}
=T_{\mathrm{queue/app}}
+T_{\mathrm{selection}}
+T_{\mathrm{checkout}}
+T_{\mathrm{network/server}}
+T_{\mathrm{processing}}
\]

Bounding one component does not bound the total. For example, `maxTimeMS=200` does not prevent a request from waiting 2 seconds to check out a connection before the server even starts running.

### 1.2. Three Concepts Often Confused

- **Server:** an actual `mongod`/`mongos` process to which the driver can send operations.
- **Connection:** an opened, authenticated, reusable TCP/TLS channel.
- **Operation:** an action such as `find`, `aggregate`, `insertOne`, `getMore`, or `commitTransaction`; one HTTP request may execute multiple operations.

Adding more connections does **not** create more primaries, make indexes more efficient, or add MongoDB CPU/IOPS. It only alters how many **concurrent operations** can be sent over those connections up to what the server can handle.

## 2. `MongoClient`: One Object, Multiple Pools, Multiple Monitors

### 2.1. MongoClient Is Heavyweight and Thread-Safe

`MongoClient` manages topology discovery, pools, socket/TLS setup, credentials, session/retry behavior, and monitoring. The Java Sync Driver designs the client for use across **multiple threads**, so create **one `MongoClient` living for the application's lifecycle** per appropriate connection/workload.

**Avoid:**

~~~java
// ANTI-PATTERN: creating/closing MongoClient on every request.
Document getUserBad(String id, String uri) {
    try (MongoClient mongoClient = MongoClients.create(uri)) {
        return mongoClient
            .getDatabase("sample")
            .getCollection("users")
            .find(Filters.eq("_id", id))
            .first();
    }
}
~~~

Every request re-triggers topology discovery and creates/closes pools, increasing TLS/auth handshakes, CPU, socket counts, and connection churn.

**Prefer:**

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import org.bson.Document;

public final class UserRepository implements AutoCloseable {
    private final MongoClient client;
    private final MongoCollection<Document> users;

    public UserRepository(String uri) {
        this.client = MongoClients.create(uri);
        this.users = client.getDatabase("sample")
            .getCollection("users");
    }

    public Document getById(String id) {
        return users.find(Filters.eq("_id", id)).first();
    }

    @Override
    public void close() {
        client.close();
    }
}
~~~

The application instantiates `UserRepository` once or uses DI to manage a `MongoClient` bean. If Spring Boot already auto-configures a `MongoClient`, avoid accidentally creating extra clients inside individual repositories.

### 2.2. MongoClient Maintains a **Separate Pool per Server**

~~~text
              1 MongoClient
                    |
       +------------+------------+
       |            |            |
       v            v            v
   Primary P    Secondary A  Secondary B
    Pool P        Pool A       Pool B
   max=100        max=100      max=100
~~~

`maxPoolSize=100` means up to **100 pooled application connections per server**, not a single shared budget of 100 across the whole replica set. The driver also maintains **monitoring sockets** for server state (Java Driver docs note up to **two additional sockets per server**), outside the pooled connection cap.

Since the default read preference is `primary`, secondary pools in many services do not open many application sockets; **the configured ceiling does not equal currently open connections**.

### 2.3. Two `mongos` Routers Also Have Two Pools

If the driver connects to two routers `mongos-1` and `mongos-2`, each router gets its own pool per `MongoClient`. With `maxPoolSize=50`, one client can open up to 50 pooled connections to **each router**, not 50 combined.

The MongoDB driver picks routers based on topology and latency. The router handles routing to shards; a large app pool cannot fix a shard key hotspot or a slow aggregation.

### 2.4. Budget Formula When Scaling the Application

Suppose there are 15 pods, 1 `MongoClient` per pod, `maxPoolSize=80`, and all write traffic hits the same primary:

\[
\text{Potential pooled connections to primary}
=15\times1\times80=1200
\]

This is the **potential** ceiling, not the current count. If each pod accidentally creates 3 `MongoClient` instances, the ceiling jumps to `15×3×80=3,600`. Add monitoring sockets and clients from other services before concluding the DB has sufficient connection capacity.

### 2.5. Connection States and Pool Lifecycle

A socket can be:

1. **Connecting:** opening TCP/TLS, performing handshakes, and authenticating.
2. **Ready & idle:** available for checkout.
3. **Checked out:** actively used by an operation.
4. **Checked in:** returned for reuse.
5. **Closed:** due to idle/lifetime limits, network errors, or pool clear.

**Checked-out count** differs from **pool size** and from `serverStatus.connections.current`. The server may show 1,000 incoming connections while only a small fraction are actively executing operations.

### 2.6. Connecting to One Host with `directConnection=true`

`directConnection=true` instructs the driver to use single-server connection mode rather than discovering replica set topology through that host. Useful for administrative or lab tasks targeting a specific host, it is **not** the right default to "skip elections" for HA applications: the client will not fail over automatically to a new primary like a normal replica-set connection.

In production apps requiring HA, configure a proper seed list/replica set or Atlas SRV URI instead of forcing a direct connection to one member.

## 3. Connection Pool: Configuration and Java Sync Driver Defaults

Current **Java Sync Driver** documentation lists the defaults below (verify for your exact version):

| URI Option | Java Builder Equivalent | Java Driver 5.x Default | Role |
|---|---|---|---|
| `maxPoolSize` | `maxSize(int)` | 100 | Ceiling on pooled application connections **per server**. |
| `minPoolSize` | `minSize(int)` | 0 | Minimum connections the driver tries to maintain per lifecycle. |
| `maxConnecting` | `maxConnecting(int)` | 2 | Max sockets being **established concurrently** per pool. |
| `maxIdleTimeMS` | `maxConnectionIdleTime(long, TimeUnit)` | 0 | Max idle time; 0 = unlimited by this option. |
| `maxLifeTimeMS` | `maxConnectionLifeTime(long, TimeUnit)` | 0 | Max connection lifetime; 0 = unlimited by this option. |
| `waitQueueTimeoutMS` | `maxWaitTime(long, TimeUnit)` | 120,000 ms | Wait for a connection; deprecated when using CSOT. |

**Every setting must be interpreted per server pool.** Multiplying a value by 10 can multiply potential connections by 10 on **every primary, secondary, or `mongos`** the client talks to.

### 3.1. `maxPoolSize` Does Not Mean "Active Operations Running"

If a pool holds 100 connections and 95 are idle, 100 commands are not running simultaneously. Even if all 100 are checked out, they are not necessarily burning CPU continuously; some may be waiting on network, storage, or transactions. Measure:

- `checkedOutCount` and checkout wait p95/p99.
- Command execution p95/p99 by query type.
- Server CPU/IOPS/cache/locks and active operations.
- HTTP in-flight/queue depth and error rates.

### 3.2. `minPoolSize` and Cold Starts

`minPoolSize=20` can keep sockets warm and reduce post-idle latency, but many pods starting together can trigger a **connection storm**. It also **does not guarantee the pool instantly holds 20 sockets right after the constructor returns**; connection establishment and driver maintenance take time. Do not use a large `minPoolSize` as a substitute for application readiness/warmup.

### 3.3. `maxConnecting`: Bottleneck Before Reaching Max Size

Pool has `maxPoolSize=100`, `maxConnecting=2`, and 0 ready connections:

~~~text
100 requests arrive together
         |
         v
Pool can open very few connections at once
     [maxConnecting = 2]
         |
         +---- remaining requests wait for checkout
         |
         v
Connections become ready gradually and check out
~~~

Seeing checkout wait right after deployment does not necessarily mean you **hit `maxPoolSize`**; the pool may simply be **cold** and throttled by connection establishment rate. Raising `maxConnecting` speeds up ramp-up at the cost of higher TLS/auth/CPU spikes; measure carefully.

### 3.4. `maxIdleTimeMS` and `maxLifeTimeMS`

`maxIdleTimeMS` evicts connections idle too long, useful when firewalls or NAT gateways drop idle sockets before the driver notices. `maxLifeTimeMS` recycles sockets after a maximum age. Setting them too low causes handshake churn; setting them too high risks stale sockets across network middleboxes.

Never interpret `maxLifeTimeMS` as "a query cannot run longer than N ms": it is a **connection lifecycle setting**, not an operation deadline.

### 3.5. `waitQueueTimeoutMS` Does Not Cap Queue Size

If a pool has 10 connections and 1,000 Java threads call checkout simultaneously, `waitQueueTimeoutMS=5000` only bounds **wait duration** under legacy semantics—not "allow at most 5,000 requests in the queue"—and does not prevent out-of-memory failures.

To cap pending requests, place a **bounded executor, admission gate, or rate limit** in front of MongoDB calls. Modern Java 5.x encourages `timeoutMS`/CSOT for end-to-end operation bounds; see later sections to avoid mixing old and new timeouts.

## 4. Configuring Pools via `MongoClientSettings` and URI

### 4.1. Initializing a MongoClient with Custom Pool Settings

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import java.util.concurrent.TimeUnit;

public final class MongoClientConfig {
    private MongoClientConfig() { }

    public static MongoClient create(String uri) {
        MongoClientSettings settings = MongoClientSettings.builder()
            .applyConnectionString(new ConnectionString(uri))
            .applicationName("catalog-api")
            .applyToConnectionPoolSettings(pool -> pool
                .maxSize(64)
                .minSize(4)
                .maxConnecting(4)
                .maxConnectionIdleTime(45, TimeUnit.SECONDS)
                .maxConnectionLifeTime(30, TimeUnit.MINUTES))
            .build();

        return MongoClients.create(settings);
    }
}
~~~

These numbers are an **experimental configuration**; there is no proof that `64/4/4/45s/30m` fits every system. Size `maxSize` from in-flight load and server headroom, `minSize` from required warmup, and `maxConnecting` from reconnect/cold-start tests.

### 4.2. Equivalent URI

~~~text
mongodb://db1.example.internal:27017,db2.example.internal:27017,db3.example.internal:27017/?replicaSet=rs0&appName=catalog-api&maxPoolSize=64&minPoolSize=4&maxConnecting=4&maxIdleTimeMS=45000&maxLifeTimeMS=1800000
~~~

When a URI has `?` and multiple options, join them with `&`. `maxPoolSize` has a different name from `maxSize()`, yet configures the exact same setting. In production, **never hardcode username/password** in examples or logs; use a secret manager, TLS, and your deployment's official connection string.

### 4.3. Precedence Between URI and Builder

~~~java
MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .applyToConnectionPoolSettings(pool -> pool.maxSize(64))
    .build();
~~~

Because the pool block runs **after** `applyConnectionString()`, `maxSize(64)` overrides the corresponding URI value in this builder sequence. However, **do not assume every option in every framework shares identical precedence**: Spring Boot adds auto-configuration/customizers and driver versions differ. Log **effective settings with credentials redacted** at startup, or inspect pool metrics to verify.

### 4.4. Adding Legacy `maxWaitTime()`

~~~java
MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .applyToConnectionPoolSettings(pool -> pool
        .maxSize(64)
        .maxWaitTime(200, TimeUnit.MILLISECONDS))
    .build();
~~~

`maxWaitTime()` maps to `waitQueueTimeoutMS` and is useful when **not** using CSOT on supporting drivers. When `timeoutMS` is set, current Java docs state **legacy timeouts are ignored per CSOT rules**, so do not configure `maxWaitTime(200ms)` alongside `timeout(30s)` and claim pool checkout is still capped at 200ms.

### 4.5. Coordinating Socket and Cluster Settings

~~~java
MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .applyToClusterSettings(cluster -> cluster
        .serverSelectionTimeout(5, TimeUnit.SECONDS)
        .localThreshold(15, TimeUnit.MILLISECONDS))
    .applyToSocketSettings(socket -> socket
        .connectTimeout(3, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS))
    .applyToConnectionPoolSettings(pool -> pool
        .maxSize(64)
        .maxConnecting(4))
    .build();
~~~

Note: `readTimeout()` is the Java builder's socket/read timeout corresponding to `socketTimeoutMS`, **not** a replacement for server-side `maxTimeMS`. An operation passes through server selection, pool checkout, and socket reads at distinct stages. With CSOT, **pick one clear deadline model** rather than stacking overlapping legacy timeouts.

### 4.6. Using Spring Boot / Spring Data

~~~yaml
spring:
  data:
    mongodb:
      uri: "mongodb://db1.example.internal:27017/?replicaSet=rs0&maxPoolSize=64&maxConnecting=4"
~~~

This is a **conceptual config sample** assuming proper host resolution; if listing only one seed host, the driver must still be able to resolve the advertised replica set member hosts. For Atlas, use the Atlas-provided `mongodb+srv://...`/TLS connection string rather than substituting arbitrary URLs.

In Spring Boot:

- Let the framework manage the **`MongoClient` singleton bean**.
- Avoid calling `MongoClients.create` inside requests or repositories.
- Check whether auto-configuration creates an extra client if you define a manual bean.
- With `MongoClientSettingsBuilderCustomizer`, verify customizer ordering and effective settings.
- Close the client during application shutdown/drain; never close between requests.

## 5. SDAM: How Does the Driver Know the Topology?

**SDAM (Server Discovery and Monitoring)** is how the driver discovers servers in a topology, tracks their health, and reacts when the primary changes. It is **distinct** from CMAP (Connection Monitoring and Pooling), even though both manage sockets and emit events.

### 5.1. Discovery with a Replica Set

~~~text
MongoClient connects to seed list
           |
           v
       Hello/handshake
           |
           v
 Driver learns replica set name,
 members, roles and topology info
           |
           v
 Monitor detects:
   - Primary P
   - Secondary S1
   - Secondary S2
           |
           v
 Server selection chooses an eligible node
           |
           v
 Checkout from that node's pool
~~~

When a server steps down or loses connectivity, the driver updates its cluster description and selects another eligible server when available. **Not every query probes every node**: SDAM maintains topology state asynchronously and the driver selects servers from that view.

### 5.2. Heartbeats and Topology Updates

Current Java Sync Driver documentation lists:

| Option | Default | Meaning |
|---|---:|---|
| `heartbeatFrequencyMS` | 10,000 ms | Interval between monitoring checks of server state. |
| `minHeartbeatFrequency` in Builder | 500 ms | Minimum interval between monitoring checks per docs. |
| `serverMonitoringMode` | `auto` | Allows selecting polling or streaming depending on environment (e.g., FaaS). |

Monitors can process immediate topology change signals, so do not rigidly assume "a new primary is only detected after exactly 10 seconds." Lowering heartbeats excessively adds network/server overhead and never replaces proper application timeouts.

### 5.3. Topology Timeline After an Election

~~~text
t0:  P is primary, S1/S2 secondaries
t1:  P down / stepdown
t2:  driver discovers no eligible primary
t3:  write operation waits at server selection
t4:  S1 becomes primary; SDAM refreshes
t5:  driver selects S1
t6:  checkout S1 connection, execute command
~~~

If an operation times out during `t3–t4`, the failure is **server selection**, not pool `maxPoolSize`. Once the driver sees `S1` as primary, if `S1`'s pool was cleared and lacks ready connections, latency shifts to **pool checkout / connection establishment**.

### 5.4. The Cluster Description in Exceptions Is Valuable

~~~text
Client view of cluster state is:
{
  type=REPLICA_SET,
  servers=[
    {address=db1:27017, type=UNKNOWN,
     exception=MongoSocketOpenException: connection refused},
    {address=db2:27017, type=REPLICA_SET_SECONDARY,
     state=CONNECTED},
    {address=db3:27017, type=UNKNOWN}
  ]
}
~~~

If only a secondary is reachable and the request requires `primary`, a server selection timeout is the expected behavior. **Never force writes onto a secondary** to "bypass the error": replica set writes normally require the primary.

### 5.5. Seed List vs. Final Member Set

A URI only needs valid seed hosts; the driver discovers members via handshake. However, **hostnames advertised by the server must resolve and be reachable from the application**—a common pitfall when MongoDB runs inside Docker/Kubernetes while clients run on another network.

For example, if an app connects via seed `localhost:27017`, the driver learns members `mongo1:27017` and `mongo2:27017` that only resolve inside the container network, causing server selection to fail. Configure replica set member addresses **to be routable from the client network**, rather than simply increasing timeouts.

### 5.6. `replicaSet` and Mismatched Names

URI:

~~~text
mongodb://db1:27017,db2:27017/?replicaSet=rs0
~~~

If the actual cluster is `rsOther`, the driver rejects those servers as mismatched members. Check the real replica set name, certificates/DNS/ports, and cluster description; never rename a production replica set just because an app has a typo in its URI.

### 5.7. TLS/DNS Errors Are Not Pool Exhaustion

`SSLHandshakeException`, certificate chain errors, hostname mismatches, DNS SRV lookup failures, connection refused, or network timeouts happen **before or during connection establishment**. Raising the pool cap cannot fix a bad certificate or truststore. Separate logs across:

- DNS lookup / seed list.
- TCP connect.
- TLS certificate/hostname verification.
- MongoDB authentication handshake.
- SDAM topology.
- Pool checkout and command execution.

## 6. Server Selection: Rules for Primary, Secondary, and Nearest

When an operation starts, the driver identifies **eligible servers** and picks from that set. In a replica set, eligibility includes:

1. **Operation type:** Normal writes require the primary; reads follow read preference.
2. **Member state:** Primary/secondary, healthy/reachable.
3. **Read preference:** `primary`, `primaryPreferred`, `secondary`, `secondaryPreferred`, `nearest`.
4. **Tags and staleness:** If configured, secondaries must satisfy tag sets and `maxStalenessSeconds`.
5. **Latency window:** Among eligible servers, the driver chooses a node whose RTT falls within the threshold window.

### 6.1. Read Preference Modes

| Mode | Server Selected for Reads | Considerations |
|---|---|---|
| `primary` (default) | Current primary. | Reads latest primary state per semantics; fails if no primary exists. |
| `primaryPreferred` | Prefers primary; falls back to secondaries if primary unavailable. | Can read stale data during fallback. |
| `secondary` | Eligible secondary. | Never falls back to primary; can be stale or have no eligible secondary. |
| `secondaryPreferred` | Prefers secondaries; falls back to primary if none eligible. | Can shift consistency behavior between secondary and primary after failover. |
| `nearest` | Member with RTT inside latency window, primary or secondary. | Does not guarantee freshest data; optimizes network RTT, not recency. |

**Writes do not route to secondaries when `readPreference=secondary` is set.** The driver still requires a writable server for standard writes. Transactions also impose constraints: per MongoDB docs, transactions containing reads must use **`primary` read preference**; do not configure `secondary` for a multi-document transaction expecting secondary routing.

### 6.2. Java Example with `ReadPreference`

~~~java
import com.mongodb.ReadPreference;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

MongoCollection<Document> inventory = mongoClient
    .getDatabase("shop")
    .getCollection("inventory")
    .withReadPreference(ReadPreference.secondaryPreferred());

Document item = inventory
    .find(new Document("_id", "SKU-100"))
    .first();
~~~

`withReadPreference` returns a **configured collection handle** for operations invoked on it; you do not need a new `MongoClient` just to change one collection's read preference. Secondary reads carry **replication lag**; avoid them when business logic demands strong read-after-write consistency immediately after a commit.

### 6.3. `localThresholdMS` and the Latency Window

Current Java Sync Driver docs state a default of `localThresholdMS=15`. Suppose eligible servers have round-trip times (RTT):

~~~text
S1: 10 ms  <-- fastest
S2: 21 ms
S3: 31 ms

Latency window threshold = 15 ms
Eligible by latency: RTT <= 10 + 15 = 25 ms
=> S1 and S2, excluding S3.
~~~

**Caution:** The latency window applies **after** filtering by role, read preference, tags, and staleness. If `readPreference` leaves only one eligible primary, `localThresholdMS` does not add secondaries as candidates. Server selection **picks randomly** within the latency window per driver semantics; do not assume it always picks the single lowest-RTT server every time.

### 6.4. `nearest` Does Not Mean "Closest Geographic Secondary"

`nearest` evaluates RTT across eligible servers—it has **no awareness** of geographic data residency or business consistency. A nearby secondary may lag replication, returning stale data despite low RTT. If regional routing is needed, combine tag sets, read preference, and topology policies while accounting for freshness and data-residency rules.

### 6.5. `maxStalenessSeconds` and Tag Sets

Read preferences can include:

- `maxStalenessSeconds` to exclude secondaries that lag too far behind (based on estimated lag).
- Tag sets to prefer or restrict nodes with matching tags, e.g., `region:ap-southeast`.

Do not treat max staleness as an **absolute guarantee** that "data is never older than N seconds": the driver estimates lag from replication metadata and monitoring, whereas strict consistency requires appropriate read concerns and transactional semantics. MongoDB docs enforce a minimum threshold for `maxStalenessSeconds` (typically >= 90 seconds); verify against your version and monitoring frequency before configuring.

### 6.6. Server Selection with `mongos`

On a sharded cluster, `MongoClient` selects a **`mongos` router** from the endpoint list within the eligible latency window, and `mongos` routes to shards. You cannot force shard-local queries via `localThresholdMS`; query targeting depends on shard keys, filters, and cluster metadata.

### 6.7. No Eligible Server: What Happens?

The driver waits for topology updates and retries selection until either:

- An eligible server is found, then it proceeds to pool checkout; or
- `serverSelectionTimeoutMS` (legacy) or the remaining CSOT deadline expires, throwing an exception.

**Waiting to select a server is different from waiting for a connection.** That is why an exception containing `ReadPreferenceServerSelector{readPreference=primary}` does not prove the pool is too small.

## 7. Timeout Types: Complete Comparison Table

The MongoDB Java Driver exposes multiple timeouts because **operations can stall at distinct stages**. Some limits are client-side, some are server-side, and some inherit from database, collection, or operation handles. There is no single `timeout` property that behaves identically across all driver versions.

| Option | Current Java Driver Default | Applies to Which Stage? | What It Does Not Solve |
|---|---|---|---|
| `serverSelectionTimeoutMS` | 30,000 ms | Waiting to select an eligible server per topology/read preference. | Pool checkout or server execution after selection. |
| `connectTimeoutMS` | 10,000 ms | Opening a TCP socket / network connection. | Waiting in queue for an existing pooled socket. |
| `socketTimeoutMS` | 0 (no legacy socket read/write limit). | Waiting to send/receive bytes on a socket. | Covering entire request or application queues. |
| `waitQueueTimeoutMS` | 120,000 ms in current Java docs, **deprecated**. | Waiting for an available pooled connection. | Bounding waiter count or server execution. |
| `maxTimeMS` | Unlimited unless set (per operation). | Server-side execution time for supported commands. | Server selection, pool wait, or end-to-end network. |
| `maxCommitTimeMS` | Per transaction options; unset by default. | Server-side transaction commit time limit per semantics. | Guaranteeing commit rolled back on response timeout. |
| `wTimeoutMS` | Per write concern, only when `wtimeout` is set. | Waiting for write concern acknowledgement. | Rolling back a write already applied on primary. |
| `timeoutMS` (CSOT) | Unset unless configured. | Client operation deadline across selection → checkout → execution. | HTTP processing before/after MongoDB, or automatic business rollback. |

**The defaults above apply to current Java Sync Driver documentation**; 4.x drivers, legacy `mongosh`, and server options may differ. When `timeoutMS` is set, related legacy options may be **ignored per CSOT documentation**, so never assume all defaults in the table remain active simultaneously.

### 7.1. Timeline Example to Pinpoint Expiration

~~~text
HTTP handler starts     0 ms
Auth/validation done   40 ms
Server selection done  90 ms   (+50)
Pool checkout done    240 ms   (+150)
Server command done   430 ms   (+190)
Transform/HTTP done   455 ms   (+25)
~~~

In this scenario:

- `serverSelectionTimeoutMS=200`: not violated because selection took 50 ms.
- `waitQueueTimeoutMS=100` (legacy): times out during checkout because waiting took 150 ms.
- `maxTimeMS=300`: not violated because server execution took 190 ms.
- `timeoutMS=400` (CSOT): the MongoDB operation times out before completion if measured from operation start to 430 ms.
- HTTP deadline 500 ms: total 455 ms fits within the illustrative SLA (ignoring p95/p99 variance).

The goal is not picking "the largest timeout", but **matching the limit to the slow stage and remaining budget**.

## 8. `serverSelectionTimeoutMS`: Pick a Primary/Secondary First

### 8.1. Meaning

The driver waits until topology contains **at least one eligible server** for the operation/read preference, or until selection times out. Current Java docs default to **30 seconds**. Exceptions typically look like:

~~~text
com.mongodb.MongoTimeoutException:
Timed out after 30000 ms while waiting for a server
that matches ReadPreferenceServerSelector{readPreference=primary}.
Client view of cluster state is ...
~~~

Read `Client view of cluster state` to see:

- Cluster type and replica set members visible to the driver.
- Whether a primary is detected.
- Which servers are `UNKNOWN` or `CONNECTING`.
- Whether socket/DNS/TLS errors occurred.
- Whether nodes are healthy yet only `SECONDARY`.
- Whether hostnames in the replica set config are reachable from the app.

### 8.2. Java Builder

~~~java
MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .applyToClusterSettings(cluster -> cluster
        .serverSelectionTimeout(3, TimeUnit.SECONDS))
    .build();
~~~

Equivalent URI:

~~~text
mongodb://db1:27017,db2:27017/?replicaSet=rs0&serverSelectionTimeoutMS=3000
~~~

**This is an example configuration**, not a recommendation that "every app should time out after 3 seconds." Normal elections take a few seconds, so ultra-short timeouts cause transient errors; conversely, an HTTP API with a 500 ms deadline holds requests far too long with a 30-second timeout. Align policies from the application down to the driver.

### 8.3. Common Causes

| Cause | Symptom | Check |
|---|---|---|
| Primary stepdown/election | Temporarily no eligible primary; secondaries reachable. | Replica set status, SDAM transitions. |
| Network partition / DNS failure | Multiple nodes `UNKNOWN`/`CONNECTING`, socket refused/timed out. | DNS, ports, firewalls, TLS, SRV resolution. |
| Wrong replica set seed/advertised hosts | Driver discovers unreachable hostnames. | `rs.conf()` on authorized lab/cluster, actual network path. |
| Wrong `replicaSet` name | Members excluded for not matching expected set name. | URI `replicaSet` and cluster config. |
| Overly restrictive read preference | Tagged secondary missing or too stale. | Tags/`maxStalenessSeconds`/eligible nodes. |
| Unsuitable server role | Read requires secondary, none eligible. | Read preference and topology. |
| Load balancer / `mongos` unavailable | No router selectable. | Health of `mongos`/LB/network. |

### 8.4. Never Change Read Preference to "Fix" Networking at All Costs

Switching `primary` to `secondaryPreferred` may allow stale-tolerant reads to succeed, **however**:

- Writes still require a writable primary.
- Read-after-write queries can return stale values.
- Transaction read constraints still apply.
- If the network cannot reach the entire replica set, read preference will not conjure up a reachable server.

Switch only when **business rules permit the consistency trade-off** and the impact has been validated.

### 8.5. CSOT Deadlines Can Cut Selection Short

If `timeoutMS=500` is configured, an operation can hit its client deadline during selection even though `serverSelectionTimeoutMS=30000`. Always check **whether CSOT is enabled and which timeout governs** rather than attributing every selection timeout solely to `serverSelectionTimeoutMS`.

## 9. `connectTimeoutMS`: When a New Socket Cannot Open

### 9.1. Meaning

`connectTimeoutMS` bounds how long the driver waits to **open a new connection** before failing. Current Java docs specify a **10-second** default; `0` in the legacy option means no socket-open timeout.

~~~text
Driver needs a new socket
        |
        v
DNS/address resolution
        |
        v
TCP connect -> TLS handshake -> MongoDB handshake/auth
        |
        v
Connection ready for pool
~~~

Stages such as DNS, TLS, and handshakes may have their own JVM/driver timeouts. Do not assume one option guarantees the entire connection setup finishes in exactly N ms.

### 9.2. URI/Java

~~~text
mongodb://db1:27017/?connectTimeoutMS=3000
~~~

~~~java
MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .applyToSocketSettings(socket -> socket
        .connectTimeout(3, TimeUnit.SECONDS))
    .build();
~~~

### 9.3. When Connect Timeout Is Not Pool Exhaustion

The pool is empty after a cold start and the driver tries opening a socket to an unreachable host. Requests fail with `MongoSocketOpenException` or a nested `ConnectException`. Raising `maxPoolSize` will not make an unreachable host reachable. Check:

1. Are DNS/SRV records valid?
2. Ports, firewalls, security groups, and private endpoints.
3. TLS truststore, certificate SANs, and hostnames.
4. Is the server accepting connections or hitting OS/file-descriptor limits?
5. `maxConnecting` and pending socket establishments.

### 9.4. Network Timeouts vs. Slow Servers

If TCP connect succeeds yet a query takes 10 seconds due to `COLLSCAN`, **`connectTimeoutMS` does not bound query execution**. Inspect command monitoring, `maxTimeMS`/CSOT, and the query plan.

## 10. `socketTimeoutMS`: Waiting to Send/Receive Bytes on a Socket

### 10.1. Meaning

`socketTimeoutMS` is the socket read/write timeout per Java Driver semantics; current default is **0** (no legacy timeout). It is not a single clock measuring total MongoDB server execution across every step.

~~~text
Checkout succeeded
       |
       v
Write MongoDB command bytes
       |
       v
Wait for response bytes over network
       |
       v
Decode BSON result
~~~

If reading or writing stalls beyond the configured interval per driver semantics, the client throws `MongoSocketReadTimeoutException` or socket/network errors. **Never conclude a command did not execute** just because the client timed out waiting for the response.

### 10.2. Configuration

~~~text
mongodb://db1:27017/?socketTimeoutMS=15000
~~~

~~~java
MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .applyToSocketSettings(socket -> socket
        .readTimeout(15, TimeUnit.SECONDS))
    .build();
~~~

### 10.3. Why Overly Short Timeouts Are Dangerous

If an aggregation legitimately takes 2 seconds while `socketTimeoutMS=500`, the app repeatedly tears down sockets, clears/reconnects pools, and retries expensive operations. That causes **retry amplification**, not performance optimization.

Proper remedies include:

- Optimizing queries, indexes, and aggregations.
- Setting `maxTimeMS` to bound server-side execution when needed.
- Using CSOT with clear deadlines on supporting drivers.
- Moving large exports to async background jobs.
- Picking socket timeouts compatible with network/SLOs, avoiding overly tight values, and measuring error causes.

### 10.4. Socket Timeout Does Not Mean Rollback

For writes, the server may have committed even though the client timed out before receiving the acknowledgement. Before retrying, understand **retryable writes**, idempotency, and commit state; never generate a fresh `requestId` after every timeout.

## 11. `waitQueueTimeoutMS`: Waiting for Pool Checkout

### 11.1. When Does Pool Wait Occur?

A pool has `maxSize` 20. With 20 operations checked out, a 21st arrives:

~~~text
Pool server P:
  20 / 20 checked out
      |
      +-- new request wants connection
               |
               v
         wait for available connection
               |
         +-----+--------+
         |              |
      returned         timeout
         |              |
      checkout       exception
~~~

This duration is **connection checkout wait**—not server selection, and not counted in server-side `maxTimeMS`. Even when the server executes each command quickly, the driver will wait if too many concurrent operations contend for the pool.

### 11.2. Java 5.x Default and Deprecation

Current MongoDB Java Driver pool docs list `waitQueueTimeoutMS` defaulting to **120,000 ms (2 minutes)** and mark it **deprecated**, recommending client-level `timeoutMS` instead. If `timeoutMS` is set, legacy wait timeouts may be **ignored** per CSOT rules.

~~~java
MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .applyToConnectionPoolSettings(pool -> pool
        .maxSize(40)
        .maxWaitTime(200, TimeUnit.MILLISECONDS))
    .build();
~~~

This illustrates capping checkout wait at 200 ms **when not using CSOT** and when your driver version supports `maxWaitTime()`.

### 11.3. Checkout Timeout Is Not Deadlock Detection

Waiting too long for a connection can stem from:

- Pool cap too small for **legitimate concurrency**.
- Slow queries holding connections too long.
- Long-running cursors or transactions.
- Code forgetting to close cursors or sessions.
- Slow connection establishment due to `maxConnecting`, TLS, or handshakes.
- Single HTTP requests fanning out many parallel queries.
- Repeated pool clears during network instability or failovers.

**Do not** blindly raise `maxPoolSize`: if the server is already CPU/IOPS saturated, sending more parallel commands turns checkout wait into command wait and drives p99 higher.

### 11.4. The Driver Pool Is Not a Bounded Request Queue

Setting `maxPoolSize=40` caps checked-out sockets per server pool, but if tens of thousands of Java threads sit waiting on checkout for 120 seconds, the application can run out of memory or threads. Place a **semaphore, bounded `ThreadPoolExecutor` queue, or admission control** in front of MongoDB calls.

### 11.5. `maxConnecting` Can Cause Checkout Waits Even When the Pool Isn't Full

Right after restart, pool size is 0/100 and 100 callers arrive. `maxConnecting=2` throttles socket creation so callers wait. CMAP events distinguish these cases:

- **Pool full:** `checkedOutCount` sits near `maxSize`.
- **Cold start:** `size` is low while `ConnectionCreated`/`Ready` climbs slowly.
- **Network:** frequent `ConnectionClosed`/`PoolCleared` events and failures.

These are three separate diagnoses; there is no single "increase pool" button for all three.

## 12. `maxTimeMS`: Server-Side Execution Time on MongoDB

`maxTimeMS` enforces a **server-side execution** limit for supported operations. If a query exceeds the limit, the server aborts execution at interrupt points and returns an error. It **does not include** time spent waiting in admission queues, server selection, or pool checkout **before the command reaches the server**.

### 12.1. `find().maxTime()` Example in Java

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import java.util.concurrent.TimeUnit;

MongoCollection<Document> orders =
    mongoClient.getDatabase("shop").getCollection("orders");

Document one = orders
    .find(Filters.eq("status", "OPEN"))
    .maxTime(750, TimeUnit.MILLISECONDS)
    .first();
~~~

In `mongosh`:

~~~javascript
db.orders.find({ status: "OPEN" }).maxTimeMS(750)
~~~

This limit does not "make the query run faster." If a query scans the entire collection and takes 3 seconds, `maxTimeMS=750` simply turns a slow request into an early timeout; **the bottleneck is the query plan/indexes**. Use `explain("executionStats")` to analyze and optimize execution.

### 12.2. `aggregate` and Execution Limits

~~~java
List<Document> pipeline = List.of(
    new Document("$match", new Document("tenantId", "tenant-a")),
    new Document("$group",
        new Document("_id", "$status")
            .append("count", new Document("$sum", 1)))
);

List<Document> result = collection.aggregate(pipeline)
    .maxTime(2, TimeUnit.SECONDS)
    .into(new ArrayList<>());
~~~

Aggregation stages can use disk, memory, and cursors that issue `getMore`; total-time semantics across the initial command and subsequent cursor operations vary by server, driver, and CSOT. Never treat `maxTime` on the initial aggregation as an **absolute HTTP deadline** for the entire streaming cursor.

### 12.3. `maxTimeMS` Does Not Replace CSOT

Suppose:

~~~text
Server selection:    200 ms
Pool checkout:       800 ms
Server execution:    150 ms

maxTimeMS:            500 ms
Total MongoDB call:  1150 ms
~~~

The query stayed well under its 500 ms server limit, yet the call still took 1.15 seconds. For a client with a 900 ms operation deadline, use CSOT/timeout policies to cut off waiting during checkout/execution rather than relying solely on `maxTimeMS`.

### 12.4. When a Query Is Aborted, Investigate the Cause

Server execution expiration typically reports `MaxTimeMSExpired` or a corresponding error code—distinct from `ReadPreferenceServerSelector` or `Connection checkout timed out`. Check:

- Do indexes match selectivity and compound prefix order?
- Does the query trigger `COLLSCAN`, in-memory `SORT`, or huge `$group`?
- Are concurrent clients or transactions holding locks/resources?
- Is there lock, CPU, IOPS, or WiredTiger cache pressure?
- Is the deadline unreasonably short for the expected business operation?

Never increase the pool size just because you see `maxTimeMS` errors.

## 13. Write Concern Timeout: `wTimeoutMS` Does Not Mean the Write Failed

MongoDB write concern defines the **acknowledgement/durability** level required after a write. `wTimeoutMS`/`wtimeout` bounds **how long to wait for write concern satisfaction**; it does not roll back a write already applied on the primary.

### 13.1. Java Example

~~~java
import com.mongodb.WriteConcern;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

MongoCollection<Document> criticalOrders =
    mongoClient.getDatabase("shop")
        .getCollection("orders")
        .withWriteConcern(
            WriteConcern.MAJORITY.withWTimeout(
                1500, TimeUnit.MILLISECONDS));

criticalOrders.insertOne(new Document("_id", "ORD-1001")
    .append("state", "NEW"));
~~~

This shows a **legacy write concern timeout** when not overridden by CSOT; Java Driver 5.x CSOT docs state `wTimeoutMS` is among the timeout options **ignored when `timeoutMS` is set**.

### 13.2. Why You Must Never Retry by Creating a New Record

~~~text
Client -> Primary insert ORD-1001
Primary accepts and writes data
Replication acknowledgement is delayed
Client's wtimeout expires
~~~

The operation may already have succeeded on the primary while `w: "majority"` replication took longer than the timeout. Receiving an error/uncertain outcome **does not prove the insert never happened**. Retrying with `_id: ORD-1002` solely because of a timeout creates duplicate orders.

Business-safe patterns:

- Stable idempotency key / unique index per request.
- Retryable writes per driver + server semantics.
- Reading/verifying state when outcome is uncertain.
- Avoiding infinite retry loops during replica set lag.

### 13.3. Write Concern and Consistency

`w: 1`, `majority`, and `journal` govern **durability and replication guarantees**; they neither add pool connections nor alter primary selection for writes. Raising write concern can **increase operation latency**, holding connections longer and raising pool checkout occupancy. Always size and test pools using your production write concern.

## 14. CSOT: `timeoutMS` Bounds the **Entire MongoDB Operation**

**Client-Side Operation Timeout (CSOT)** is the modern Java Driver mechanism to apply a single deadline across all steps required to complete a MongoDB operation, including **server selection, connection checkout, and execution**. Official MongoDB docs currently mark this feature **experimental**; always verify APIs and timeout interactions for your exact **driver version**.

### 14.1. How CSOT Solves Fragmented Timeouts

Previously, an application might configure:

~~~text
serverSelectionTimeoutMS = 30000
waitQueueTimeoutMS       = 120000
socketTimeoutMS          = 30000
maxTimeMS                = 30000
~~~

When a request traverses sequential stages, total latency can grow unacceptably long even if no single stage breaches its individual cap. CSOT defines **one shared budget for the operation** instead of independent per-stage deadlines.

~~~text
Operation CSOT timeoutMS = 800 ms

  100 ms: select server
  200 ms: checkout pool
  300 ms: execute command
  200 ms: remain for response/other work

All inside one 800 ms budget.
~~~

### 14.2. Configuring `timeoutMS`

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import java.util.concurrent.TimeUnit;

MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .timeout(800L, TimeUnit.MILLISECONDS)
    .build();

MongoClient client = MongoClients.create(settings);
~~~

Or via URI:

~~~text
mongodb://db1:27017/?timeoutMS=800
~~~

**These examples require a Java Driver version supporting CSOT.** Do not copy them into older driver projects where the API does not exist.

### 14.3. Special CSOT Values

| `timeoutMS` | Meaning in Current Java Docs |
|---|---|
| Positive number, e.g., 800 | Limits operation completion to 800 ms. |
| `0` | No CSOT-based timeout (unlimited under this option). |
| Unset / `null` | Uses legacy timeout semantics from related options. |

**`0` does not mean "time out immediately"** in CSOT; per docs, it disables CSOT timeout enforcement. Never pick `0` in an SLA-bound production API just to avoid exceptions.

### 14.4. Affected Legacy Timeout Options

MongoDB Java Driver CSOT docs note that the following options are **deprecated and ignored when `timeoutMS` is set**:

- `waitQueueTimeoutMS`.
- `socketTimeoutMS`.
- `wTimeoutMS`.
- `maxTimeMS`.
- `maxCommitTimeMS`.

Therefore, configuring:

~~~text
...?timeoutMS=800&waitQueueTimeoutMS=5000&socketTimeoutMS=20000
~~~

does **not** mean "operation max 800 ms, while checkout can wait 5s and socket read 20s." The **800 ms operation timeout** governs under CSOT, while other constraints like `connectTimeoutMS`/server selection interact per implementation. Avoid mixing legacy and CSOT settings, as it breeds confusion and bugs.

### 14.5. Timeout Inheritance Hierarchy

CSOT can be configured at multiple levels:

| Level | Meaning |
|---|---|
| Client | Default for operations unless overridden. |
| Database | Applies to operations from that database handle. |
| Collection | Applies to operations from that collection handle. |
| Session | Default timeout for session lifecycle operations per config. |
| Transaction | Timeout within transaction scope if set. |
| Operation | Most specific level; highest precedence per docs. |

Note that this is **scope/config inheritance**, not "cumulative addition." Setting 500 ms on a collection does not add to an 800 ms client timeout to yield 1,300 ms. For transactions, verify how `ClientSessionOptions.defaultTimeout` and `TransactionOptions.timeout` interact.

### 14.6. Collection-Level Override Example

~~~java
MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .timeout(800L, TimeUnit.MILLISECONDS)
    .build();

try (MongoClient client = MongoClients.create(settings)) {
    MongoCollection<Document> reports =
        client.getDatabase("shop")
            .getCollection("reports")
            .withTimeout(2L, TimeUnit.SECONDS);

    reports.find(new Document("state", "READY")).first();
}
~~~

Here the `reports` collection handle grants a 2-second deadline instead of the client-level 800 ms. **Do not** stretch timeouts for every API just because one report is slow; isolate long-running workloads/queues with dedicated budgets.

### 14.7. HTTP Deadlines Differ from CSOT Deadlines

If a request waited 300 ms in an HTTP queue before calling MongoDB with an 800 ms CSOT, total HTTP time can reach **1,100 ms** or more once transforms and network are included. CSOT starts at the MongoDB operation—**it does not include time spent before the driver call**.

Good design:

1. Capture an **absolute request deadline** at ingress.
2. Before calling MongoDB, compute the **remaining budget**.
3. If too little time remains, reject or degrade instead of calling the DB.
4. Set operation CSOT from the remaining budget and business bounds.
5. Keep retries within the total budget; never reset deadlines infinitely.

### 14.8. Cursor Timeouts: Lifetime vs. Iteration?

MongoDB Java Driver CSOT docs define **cursor timeout modes**:

- `CURSOR_LIFETIME`: the timeout applies to the **entire lifetime** of the cursor, from initialization across all batch reads.
- `ITERATION`: the timeout applies to **each individual iteration/call such as `hasNext`, `next`, or `tryNext`**, refreshing per semantics; this is the default mode for tailable/change-stream cursors per docs.

Example when supported by your driver version:

~~~java
import com.mongodb.client.MongoCursor;
import com.mongodb.TimeoutMode;

try (MongoCursor<Document> cursor = collection
        .find(new Document("status", "READY"))
        .timeoutMode(TimeoutMode.CURSOR_LIFETIME)
        .cursor()) {
    while (cursor.hasNext()) {
        Document doc = cursor.next();
        consume(doc);
    }
}
~~~

`consume(doc)` is just an illustrative application helper; the example requires `collection` and a defined `consume` method. **Timeout mode requires a CSOT timeout to be inherited or configured on the client/database/collection** per docs. For long-lived change streams, never set a short cursor lifetime that forces constant restarts.

### 14.9. CSOT Does Not Guarantee Server-Side Rollback

A client's deadline can expire after the server executes a write but before the response returns. A timeout is a **client decision to stop waiting**, not proof of business state. Write/transaction retries must follow supported semantics and idempotency.

### 14.10. CSOT Also Affects Transactions and Encryption

CSOT docs include timeout support for:

- Session lifecycle / `ClientSessionOptions.defaultTimeout`.
- `TransactionOptions.timeout`.
- `ClientEncryptionSettings.timeout` in Client-Side Field Level Encryption.
- GridFS bucket operations and cursor iteration modes.

Do not assume a client or collection timeout automatically rolls back every transaction within an HTTP SLA: transaction lifecycle, commit ambiguity, and session cleanup remain distinct concerns.

## 15. Timeouts in Transactions and Sessions

### 15.1. Never Share a Session Concurrently at Will

A `ClientSession` must have a well-defined lifecycle. The Java Driver is not designed for multiple threads to run concurrent operations on **the same session** arbitrarily. Each transaction must stay on its session, target the primary per constraints, and handle retry/abort/commit per spec.

### 15.2. Setting a Transaction Timeout

~~~java
import com.mongodb.TransactionOptions;
import com.mongodb.client.ClientSession;
import java.util.concurrent.TimeUnit;

TransactionOptions options = TransactionOptions.builder()
    .timeout(2, TimeUnit.SECONDS)
    .build();

try (ClientSession session = client.startSession()) {
    session.startTransaction(options);

    // Use the same session for operations inside the transaction.
    // collection.updateOne(session, filter, update);
    // collection.insertOne(session, document);

    session.commitTransaction();
}
~~~

**Requires a MongoDB Java Driver supporting transaction-level CSOT**; `timeout()` may not exist in older releases. The snippet illustrates API/lifecycle only and performs no real operations.

### 15.3. Transaction Timeouts vs. Server Transaction Lifetime

MongoDB Server enforces its own transaction lifetime, lock, and resource limits independent of client operation timeouts. A transaction should never hold dozens of locks or long cursors simply because `timeoutMS` is large. Monitor `serverStatus`/`currentOp`/transaction metrics and keep transactions **short, bounded, and retryable**.

### 15.4. Commit Outcomes Can Be Ambiguous

Suppose:

~~~text
Client calls commitTransaction()
        |
        v
Server commits transaction
        |
        v
Network response lost / CSOT expires
~~~

The application must not conclude "the transaction did not commit" and replay the entire business workflow under a new ID. Use driver transaction retry helpers/`withTransaction` where appropriate, handle error labels like `UnknownTransactionCommitResult`, and use stable business IDs per the Transactions documentation.

### 15.5. `withTransaction` Does Not Make Non-MongoDB Side Effects Free to Retry

The driver retries transient errors according to transaction callback semantics, so callbacks must **not contain non-idempotent side effects outside MongoDB** (sending emails, charging cards) without an outbox or idempotency guard. Timeouts, retries, and connection pools are transport mechanisms; business correctness remains the application's responsibility.

## 16. Classifying Exceptions by Where They Occur

Never handle every `MongoException` with a blanket "retry after 1 second." Two timeouts can have completely different root causes and retry safety.

| Message / Exception Pattern | Likely Stage | How to Distinguish |
|---|---|---|
| `MongoTimeoutException` containing `ReadPreferenceServerSelector` | Server selection. | Client cluster description; is there an eligible primary/secondary? |
| `MongoTimeoutException` containing `Timed out waiting for a connection` / pool checkout | Connection pool. | Checked-out count, queue wait, connection churn. |
| `MongoSocketOpenException` / `ConnectException` | TCP connect/network. | Host/port/DNS/firewall/TLS/connect timeout. |
| `MongoSocketReadTimeoutException` | Socket read / response wait. | Server command duration, network, socket timeout config. |
| `MongoSecurityException` / authentication error | Credentials / auth handshake. | User/`authSource`/permissions/SCRAM/TLS identity. |
| Error code `MaxTimeMSExpired` or max time exceeded | Server execution. | Query plan/aggregation/locks/CPU/IOPS. |
| `MongoWriteConcernException`, wtimeout-related | Write concern acknowledgement. | Replication lag / majority availability; write may have applied. |
| Error label `TransientTransactionError` | Transient transaction failure. | Retry whole transaction via helper/spec within budget. |
| Error label `UnknownTransactionCommitResult` | Ambiguous commit outcome. | Retry commit/verify per spec; do not duplicate business actions. |
| `MongoInterruptedException` / cancellation-related | Caller thread interrupted or operation canceled. | Deadline/cancel behavior, cursor/session cleanup. |

**Exact classes and messages vary across driver versions**; this table is a diagnostic guide, not an immutable mapping. A socket error can also surface wrapped inside a server selection timeout if the driver cannot find any eligible server.

### 16.1. Classify by Context, Not Brittle String Parsing

Do not write:

~~~java
if (e.getMessage().contains("30000")) {
    // assume pool exhausted
}
~~~

Because `30000` could belong to **server selection** and error text is not a stable API. Rely on exception classes/causes, error labels/codes where available, CMAP/SDAM events, trace spans, and redacted cluster descriptions to identify the source.

### 16.2. Catching at the API Layer

~~~java
try {
    return orders.find(Filters.eq("_id", id)).first();
} catch (MongoTimeoutException e) {
    // Log correlationId, operation class, elapsed time,
    // server/pool/SDAM metrics from separate instrumentation.
    throw new ServiceUnavailableException(
        "Database deadline or server selection unavailable", e);
} catch (MongoException e) {
    // Other MongoDB command/network/auth/write errors need
    // classification by codes/labels and operation semantics.
    throw new DataAccessFailureException("Database operation failed", e);
}
~~~

The snippet uses hypothetical application exceptions `ServiceUnavailableException` and `DataAccessFailureException`; define them in your real project and never expose exception internals or credentials to clients. Retry policies for idempotent reads differ from writes.

### 16.3. Retrying Reads vs. Retrying Writes

The Java Driver supports retryable reads and writes under eligible conditions. However:

- Not all operations are retryable.
- Not all network timeouts carry retryable error labels.
- Manual application-side retries can multiply attempts because the driver already retries internally.
- Deadlines must cover the sum of all attempts.
- Writes must preserve identical business idempotency semantics.

Never wrap MongoDB calls in an unbounded `while(true)` retry loop.

## 17. CMAP: Observe the Connection Pool Instead of Guessing

**CMAP (Connection Monitoring and Pooling)** emits driver events covering pool and connection lifecycles. In the Java Driver, `ConnectionPoolListener` reveals how long operations wait for **checkout**, whether the pool is creating connections, or whether the pool was just cleared.

### 17.1. Key Events to Know

| Event | What It Reflects |
|---|---|
| `connectionPoolCreated` / `connectionPoolReady` | Pool created and ready per lifecycle. |
| `connectionPoolCleared` | Connections in the pool invalidated/cleared, usually due to topology/network. |
| `connectionCreated` | Driver initiated a new connection. |
| `connectionReady` | Connection completed handshake and is ready for use. |
| `connectionClosed` | Connection closed, with a reason on the event. |
| `connectionCheckOutStarted` | Operation began waiting/looking for a connection. |
| `connectionCheckedOut` | Operation acquired a pooled connection. |
| `connectionCheckOutFailed` | Checkout failed due to timeout, closed pool, or error. |
| `connectionCheckedIn` | Operation returned the connection to the pool. |

Never infer "checkout started without checked out" equals a leak: there may have been a **`connectionCheckOutFailed`** event. To track active checked-out connections, maintain a gauge incremented on `connectionCheckedOut` and decremented on `connectionCheckedIn` **with proper event matching**, or use the JMX listener.

### 17.2. Registering `ConnectionPoolListener` in Java

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.event.ConnectionPoolListener;
import com.mongodb.event.ConnectionCheckedOutEvent;
import com.mongodb.event.ConnectionCheckedInEvent;
import com.mongodb.event.ConnectionCheckOutFailedEvent;
import java.util.concurrent.atomic.LongAdder;

public final class PoolEventsDemo {
    static final class Counters implements ConnectionPoolListener {
        final LongAdder checkoutSuccess = new LongAdder();
        final LongAdder checkoutFailed = new LongAdder();
        final LongAdder checkedIn = new LongAdder();

        @Override
        public void connectionCheckedOut(ConnectionCheckedOutEvent e) {
            checkoutSuccess.increment();
        }

        @Override
        public void connectionCheckOutFailed(ConnectionCheckOutFailedEvent e) {
            checkoutFailed.increment();
        }

        @Override
        public void connectionCheckedIn(ConnectionCheckedInEvent e) {
            checkedIn.increment();
        }
    }

    public static MongoClient create(String uri, Counters c) {
        MongoClientSettings settings = MongoClientSettings.builder()
            .applyConnectionString(new ConnectionString(uri))
            .applyToConnectionPoolSettings(pool -> pool
                .maxSize(64)
                .addConnectionPoolListener(c))
            .build();
        return MongoClients.create(settings);
    }
}
~~~

**These are cumulative counters**, not a live gauge of currently open connections. Computing `checkoutSuccess - checkedIn` is only an approximation assuming no dropped events and cleanly managed lifecycles/ordering; for reliable live pool size and `checkedOutCount`, use JMX/MXBeans or a metrics library with proper synchronous gauges.

### 17.3. Why Event Timestamps Matter

To measure checkout wait latency:

~~~text
t=10:00:00.000  CheckOutStarted
t=10:00:00.083  CheckedOut

checkout wait = 83 ms
~~~

Instrumentation must **correlate events for the exact same operation/checkout attempt**; never subtract request A's event timestamp from request B's and call it latency. Use OpenTelemetry, Micrometer, or driver-native timing instrumentation rather than pairing events by server address alone under thousands of concurrent requests.

### 17.4. Minimum Metrics to Graph

- `pool.size` (open pooled connections).
- `pool.checkedOut` (in use).
- `pool.checkoutWait.p50/p95/p99`.
- `pool.checkoutFailed` by reason.
- `connection.created/ready/closed` rates.
- `pool.cleared` and topology events.
- `serverSelectionDuration` if exposed by instrumentation.
- `commandDuration` / errors by command name.

If you monitor only MongoDB `connections.current` without **per-client checkout wait**, you can miss application-side pool bottlenecks.

## 18. JMX and Command/SDAM Monitoring

### 18.1. `JMXConnectionPoolListener`

Java Driver docs show how to register it:

~~~java
import com.mongodb.management.JMXConnectionPoolListener;

JMXConnectionPoolListener jmxListener =
    new JMXConnectionPoolListener();

MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .applyToConnectionPoolSettings(pool ->
        pool.addConnectionPoolListener(jmxListener))
    .build();

MongoClient client = MongoClients.create(settings);
~~~

MXBeans appear under the `org.mongodb.driver` domain with attributes such as `clusterId`, `host`, `port`, `minSize`, `maxSize`, `size`, and `checkedOutCount`. Consume via JConsole, a JMX exporter, or Micrometer. **Never expose unauthenticated remote JMX**, as it leaks operational details.

### 18.2. CommandListener

`CommandListener` receives `CommandStartedEvent`, `CommandSucceededEvent`, and `CommandFailedEvent`. Use it to measure:

- Query/aggregate/insert/update/`getMore` durations.
- Failed commands by error type/code (without logging sensitive data).
- Retry attempts relative to requests.
- Separating command execution latency from checkout and server selection.

Example:

~~~java
import com.mongodb.event.CommandListener;
import com.mongodb.event.CommandStartedEvent;
import com.mongodb.event.CommandSucceededEvent;
import com.mongodb.event.CommandFailedEvent;

final class MongoCommandEvents implements CommandListener {
    @Override
    public void commandStarted(CommandStartedEvent event) {
        recordStarted(event.getCommandName());
    }

    @Override
    public void commandSucceeded(CommandSucceededEvent event) {
        recordSuccess(event.getCommandName());
    }

    @Override
    public void commandFailed(CommandFailedEvent event) {
        recordFailure(event.getCommandName());
    }

    private void recordStarted(String name) { /* metrics counter */ }
    private void recordSuccess(String name) { /* metrics counter */ }
    private void recordFailure(String name) { /* metrics counter */ }
}

// Register in builder:
// .addCommandListener(new MongoCommandEvents())
~~~

This listener only illustrates counters. For accurate durations, `CommandSucceededEvent` provides elapsed-time APIs (per driver version) and correlation IDs; use supported getters or a tracer rather than a global stopwatch under concurrent commands.

### 18.3. SDAM Events

SDAM listeners such as `ClusterListener`, `ServerListener`, and `ServerMonitorListener` expose:

- Cluster description changes.
- Member role transitions from `PRIMARY` to `UNKNOWN`/`SECONDARY`.
- Monitor heartbeat successes/failures.
- Topology and server availability.

When `serverSelectionTimeoutMS` triggers, the **SDAM timeline** shows whether the driver lost the primary, encountered an unreachable hostname, or was still discovering the cluster.

### 18.4. Separating Three Latency Views

~~~text
HTTP p99 latency
   |
   +--> Driver server selection wait
   |
   +--> Driver connection checkout wait
   |
   +--> MongoDB command duration
~~~

A single request can be slow across multiple stages; never add stage p99s mechanically to estimate total p99, because percentiles come from different requests. Use **per-request traces** and stage breakdowns.

### 18.5. Securing Metrics and Logs

- Never log full connection URIs containing passwords.
- Never log BSON commands containing PII/tokens without explicit policy.
- Never attach `userId`/`requestId`/query text to Prometheus labels (high cardinality).
- Mask internal hostnames/IPs when exporting metrics to untrusted systems.
- Enforce retention, RBAC, and auditing on traces.

## 19. Server-Side Metrics to Correlate with the Driver

In `mongosh` with monitoring privileges:

~~~javascript
const status = db.getSiblingDB("admin")
  .runCommand({ serverStatus: 1 })

printjson(status.connections)
printjson(status.opcounters)
printjson(status.globalLock?.currentQueue)
~~~

### 19.1. `serverStatus.connections`

Fields may include:

- `current`: total incoming client connections, including idle and monitor connections.
- `active`: incoming connections with an active operation per server semantics/version.
- `available`: remaining connections the server can accept.
- `totalCreated`: cumulative counter since server start.
- `rejected`: rejected connection statistics if supported by the version.

Never equate `pool.checkedOutCount` with `connections.current`: the server counts all clients, while the Java client counts one specific pool.

### 19.2. Locks, Queues, and Storage Engine

`globalLock.currentQueue` and server admission queues (where present) reflect **server-side waiting**, not `ConnectionPoolListener` checkout waits. MongoDB `serverStatus` 8.x/9.x may rename or introduce new `queues` metrics across patch versions; keep dashboards version-aware.

WiredTiger cache pressure, eviction, disk IOPS, CPU saturation, and poor query plans elevate **command latency**; enlarging the pool at that point only feeds more commands into the bottleneck.

### 19.3. Query Plans

~~~javascript
db.orders.explain("executionStats").find({
  tenantId: "tenant-a",
  status: "OPEN"
}).sort({ createdAt: -1 }).limit(25)
~~~

Inspect `totalKeysExamined`, `totalDocsExamined`, `IXSCAN`/`COLLSCAN`/`SORT` stages, and actual execution stats. If a query scans millions of documents to return 25, fixing the index/query cuts **connection hold time** far more effectively than enlarging the pool.

### 19.4. Active Operations

~~~javascript
db.getSiblingDB("admin").aggregate([
  { $currentOp: { allUsers: true, idleConnections: false } },
  { $match: { active: true } },
  { $project: {
      ns: 1,
      op: 1,
      secs_running: 1,
      waitingForLock: 1,
      appName: 1
  }}
])
~~~

`$currentOp` may require elevated privileges; never dump sensitive raw commands into public logs. Long-running operations may stem from cursors, transactions, or aggregations and drive up pool checkout wait.

## 20. Failover, Pool Clears, and Connection Storms

### 20.1. During a Primary Stepdown

~~~text
t0  App requests normally reach Primary P
t1  P steps down / connection breaks
t2  SDAM reports no eligible primary
t3  Writes wait for server selection
t4  New primary S1 elected
t5  Driver updates cluster description
t6  Pools may clear/reconnect; connections ramp up
t7  Backlogged writes + retries hit S1
~~~

At `t2–t3`, raising the pool on `P` helps nothing because **there is no eligible primary**. At `t6`, `maxConnecting` caps concurrent socket creation; too many pods reconnecting simultaneously can spark a TLS/auth storm. At `t7`, retries without backoff can hammer the newly elected primary.

### 20.2. Distinguishing Error Spikes During Failover

| Moment | Symptom | Action |
|---|---|---|
| Lost primary | Server selection timeout / `readPreference=primary`. | Check SDAM/election; wait within bounded business deadline. |
| Opening sockets to new primary | Connect/open exceptions, high creation rate. | Check network/TLS/DNS, `maxConnecting`, staggered warmup. |
| Server selected, pool still cold | Checkout wait rises, `size` below `maxSize`. | Observe pool ramp-up; avoid connection storms. |
| New server hit by retry surge | High command latency, server CPU/IOPS spike. | Apply admission/backoff/jitter, reduce fan-out. |
| API timed out, write may have committed | Unknown outcome. | Use idempotency and verify operation state. |

### 20.3. Do Not Restart All Pods Because of a Failover

If health probes kill and restart every pod during a MongoDB primary election, every fresh pod spins up new clients, pools, and monitor sockets, **extending recovery time**. Separate:

- **Liveness:** Is the process/JVM still alive?
- **Readiness:** Can it serve DB-dependent traffic right now?
- **Dependency availability:** What is the reachable state of primary/secondaries?

A service can be temporarily **not ready** for writes during a brief election while still being a healthy process that should not be restarted.

### 20.4. Idle Connections and Firewalls

After minutes of zero traffic, firewalls, NATs, or load balancers can silently drop idle TCP sockets. The app thinks the pool holds idle sockets; the first operation hits a read/write error, triggering pool clear or reconnect. Compare **network idle timeouts** against `maxIdleTimeMS` and inspect `connectionClosed` reasons; never enlarge the pool just to keep more stale sockets around.

### 20.5. TLS and Authentication Can Also Bottleneck

TLS handshakes and authentication consume CPU and network round trips. Setting `maxConnecting=100` warms one client's pool faster, but 50 pods doing it together causes a handshake storm. Monitor:

- Gap between `ConnectionCreated` and `ConnectionReady`.
- Server, application, and sidecar CPU.
- TLS/auth failures.
- `connectTimeoutMS` and network RTT.
- Post-failover connect/retry rates.

### 20.6. Separating Retryable Reads/Writes from Manual Retries

The MongoDB Java Driver performs `retryReads`/`retryWrites` where supported. If the application also layers 3 manual retries without accounting for internal driver retries, one user request multiplies DB attempts. Under overload:

\[
\mathrm{effectiveAttempts}
=\mathrm{originalRequests}\times
\mathrm{averageAttemptsPerRequest}
\]

For example, 500 RPS averaging 1.4 attempts/request yields 700 DB attempts/s (assuming one operation/request). This is **retry amplification**; cap attempts, enforce deadlines, and use exponential backoff with jitter to recover cleanly.

### 20.7. Overload Error Classification in Newer Versions

MongoDB 9.0+ introduces **Intelligent Workload Management / load shedding** on supported deployments; MongoDB Java Driver 5.8+ adds retry/retargeting handling for certain error labels such as `SystemOverloadedError`/`RetryableError` per docs. This is **version-dependent**—do not assume Java 5.2 recognizes modern overload labels. Consult your exact driver/server docs and prevent retry storms rather than retrying infinitely.

## 21. Designing Deadlines Around SLOs

### 21.1. Start from the User SLA

Suppose an order lookup API has a 400 ms p95 SLO:

~~~text
End-to-end HTTP budget     400 ms
  Auth/validation           40 ms
  App queue admission       40 ms
  MongoDB operation        240 ms
  Response transformation   30 ms
  Network/reserve           50 ms
~~~

This is an **illustrative budget**, not a statistically valid sum of p95s. It helps allocate deadlines across stages. If a request already queued for 250 ms at ingress, do not grant MongoDB another 240 ms while still promising a 400 ms response.

### 21.2. Passing the Remaining Deadline

~~~java
// Pseudocode: each HTTP request carries a reliable deadlineNanos.
long nanosLeft = deadlineNanos - System.nanoTime();
if (nanosLeft <= 0) {
    throw new RequestDeadlineExceededException();
}

long millisLeft = Math.max(1,
    TimeUnit.NANOSECONDS.toMillis(nanosLeft));

// Create override handle only when driver supports CSOT.
MongoCollection<Document> scoped =
    orders.withTimeout(millisLeft, TimeUnit.MILLISECONDS);

Document result = scoped.find(Filters.eq("_id", id)).first();
~~~

`deadlineNanos` must use the same process's monotonic clock; never pass `System.nanoTime()` across hosts since origins differ. `RequestDeadlineExceededException` is a custom application exception you define. For external HTTP deadline headers, convert reliably to remaining budget per server clock policy.

### 21.3. Never Rely on One Huge Timeout

Leaving `serverSelectionTimeoutMS=30s`, `waitQueueTimeoutMS=120s`, and `socketTimeoutMS=0` without CSOT or an HTTP deadline lets a single request hang longer than any user tolerates. Conversely, a 50 ms timeout on a network with 80 ms p99 produces constant false errors.

Choose timeouts based on:

1. **Business SLO** and operation criticality.
2. Normal p95/p99 latency by region and query class.
3. Typical failover duration.
4. Queue and pool saturation behavior.
5. Retryability and idempotency.
6. Fallback policies and error budgets.

### 21.4. HTTP Status Codes and Retry Hints

- `429 Too Many Requests` when a client or tenant exceeds quota.
- `503 Service Unavailable` when a dependency is temporarily overloaded or unavailable.
- Downstream timeouts may surface as `504 Gateway Timeout` at proxies or API gateways.

This is an **API policy mapping**, not a 1:1 translation of every MongoDB exception to an HTTP status. Never leak raw MongoDB exceptions containing hostnames or credentials to clients. If returning `Retry-After`, clients must apply jitter and cap attempts.

### 21.5. Read-Only vs. Writes

Idempotent reads can be retried on timeouts/network drops within driver semantics and deadlines; writes may already have committed, so they require stable request IDs, retryable write support, and outcome verification. Never retry:

~~~text
POST /orders with new _id each attempt
~~~

simply because the response timed out. With a stable `_id` or unique business key, retries detect duplicates as the same request and handle them safely by design.

## 22. Bounded Concurrency Around the MongoDB Java Sync Driver

### 22.1. A Pool Cap Alone Cannot Prevent Overload

~~~text
5000 HTTP requests arriving
        |
        v
5000 Java tasks waiting to checkout
        |
        v
MongoClient pool maxSize = 64
        |
        v
MongoDB server
~~~

The pool only caps simultaneously checked-out sockets; **5,000 tasks still hold threads, futures, and request contexts**. If the server slows down, long queues, timeouts, and retries create a self-sustaining overload loop.

### 22.2. Java Semaphore with Timeout

~~~java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public final class MongoReadGate {
    private final Semaphore permits = new Semaphore(24, true);
    private final MongoCollection<Document> orders;

    public MongoReadGate(MongoCollection<Document> orders) {
        this.orders = orders;
    }

    public Document findById(String id) throws InterruptedException {
        if (!permits.tryAcquire(30, TimeUnit.MILLISECONDS)) {
            throw new RejectedExecutionException(
                "MongoDB read admission full");
        }

        try {
            return orders.find(Filters.eq("_id", id)).first();
        } finally {
            permits.release();
        }
    }
}
~~~

**Requires imports** for `MongoCollection`, `Document`, `Filters`, `RejectedExecutionException`, and application classes. This illustrates admission control before hitting the DB. `Semaphore(24, true)` does not bound **waiters queued outside**; pair it with bounded HTTP/executor queues.

### 22.3. Bounded Executor

~~~java
ThreadPoolExecutor dbExecutor = new ThreadPoolExecutor(
    12, 12,
    0L, TimeUnit.MILLISECONDS,
    new ArrayBlockingQueue<>(48),
    new ThreadPoolExecutor.AbortPolicy()
);
~~~

Once 12 tasks are running and 48 are queued, new tasks are rejected instead of piling up unboundedly. Avoid `Executors.newFixedThreadPool` for untrusted burst workloads since it uses an unbounded queue. Even with virtual threads or reactive code, **in-flight DB operations must remain bounded**.

### 22.4. Local Limits Differ from Global Limits

If each pod allows 24 permits and HPA scales to 30 pods, the deployment-wide ceiling reaches **720 concurrent calls**, not 24. For multi-tenant fairness or global DB budgets, enforce coordination at the gateway, via a distributed rate limiter, or by scaling per-pod caps with replica counts.

### 22.5. Isolating Workloads

A batch export holding connections for minutes can starve point-lookup APIs into timing out:

~~~text
Interactive API:
  MongoClient A
  gate=32
  pool max=48
  short deadline

Background reports:
  MongoClient B
  gate=4
  pool max=8
  longer deadline
~~~

Two clients create **two pools per server**, so sum total connections accordingly. Pool isolation prevents checkout starvation, yet **does not isolate DB-side CPU/IOPS**; optimize queries, schedule off-peak, use materialized summaries, or separate clusters/read nodes when needed.

## 23. Measurement-Driven Pool and Server Selection Tuning

### 23.1. Collect Metrics First

Build a dashboard covering:

| Scope | Metrics |
|---|---|
| HTTP/app | Arrival RPS, completed RPS, p95/p99, timeouts/rejections, queue depth. |
| Driver pool | `maxSize`, `size`, `checkedOutCount`, checkout wait p95/p99, checkout failures, created/closed/cleared rates. |
| Driver SDAM | Server selection failures, topology transitions, heartbeat failures, eligible servers. |
| Driver command | Command p50/p95/p99, retries, errors by command type. |
| MongoDB server | CPU, memory, WiredTiger cache, disk IOPS, `connections.current/active`, locks/queues. |
| Deployment | Pod/client counts, TLS handshake rate, network latency, HPA events. |

### 23.2. Step Load Gradually

~~~text
Request rate: 100 -> 200 -> 400 -> 600 -> 800 req/s
For each stage observe:
  completed throughput
  checkout wait
  server selection time
  command time
  HTTP p99 and error rate
~~~

These numbers are a **lab test scenario**, never to be run unannounced on production. Test both **open-loop fixed arrivals** (to observe queue growth past capacity) and **closed-loop user sessions** (to evaluate user experience).

### 23.3. Finding the Knee Point

| Incoming RPS | Completed RPS | HTTP p95 | Checkout p95 | Server CPU |
|---:|---:|---:|---:|---:|
| 100 | 100 | 70 ms | 2 ms | 22% |
| 300 | 300 | 95 ms | 5 ms | 45% |
| 500 | 500 | 145 ms | 18 ms | 76% |
| 700 | 610 | 700 ms | 200 ms | 96% |
| 900 | 615 | 2,200 ms | 500 ms | 99% |

**Hypothetical data:** Completed throughput saturates around 610–615 RPS while latency explodes. Simply enlarging the pool when DB CPU nears 100% will slow things down further. Instead:

1. Shed or bound concurrency/queues under overload.
2. Fix expensive queries and indexes.
3. Scale DB capacity if sustained demand genuinely exceeds limits.
4. Size the pool with headroom rather than guessing from a demo number.

### 23.4. When Is Raising `maxPoolSize` Justified?

When:

- `checkedOutCount` stays consistently near `maxSize`.
- Checkout wait p95/p99 is significant.
- Query/command execution is fast and server CPU/IOPS **still has headroom**.
- No connection creation or network issues exist.
- Admission/request budgets prevent server overload.

Even then, increase **stepwise** while measuring throughput, latency, and errors, always calculating total connections under autoscaling.

### 23.5. When Should You Shrink Pools or Concurrency?

When:

- Command p99 climbs as concurrency climbs.
- Server CPU, IOPS, or cache eviction nears saturation.
- Retry amplification pushes attempts beyond incoming demand.
- Long aggregations/cursors tie up resources.
- Pod count spikes while DB capacity stays fixed.

Lowering admission concurrency protects tail latency for accepted requests at the cost of a higher **rejection rate**; balance this against product SLOs rather than treating every rejection as a bug.

### 23.6. Testing `maxConnecting` Separately

After cold starts or failovers, measure:

- Time for the pool to reach needed occupancy.
- `ConnectionCreated` → `ConnectionReady` duration.
- TLS/auth CPU cost.
- Checkout latency.
- Server rejected connection count.

Raising `maxConnecting` from 2 to 8 may speed up ramp-up in one cluster yet cause handshake spikes in another. Never set it to 100 across 50 simultaneously starting pods.

### 23.7. Replica Set Tags and Latency Tuning

If `readPreference` is `secondary` yet server selection time is high:

1. Check whether an eligible secondary is alive.
2. Check whether tag sets match any member.
3. Check whether `maxStalenessSeconds` filters out all secondaries.
4. Check `localThresholdMS`: are members within the latency window?
5. Check network RTT, TLS, DNS, and `serverMonitoringMode`/heartbeat events.

**Never** just raise `serverSelectionTimeoutMS` to 120 seconds and call it fixed; your SLO will likely reject such waits.

### 23.8. Stage-by-Stage Troubleshooting Runbook

~~~text
Request slow / timeout
       |
       +-- No server suitable?
       |      -> SDAM, election, replicaSet, DNS, TLS,
       |         read preference, tags, staleness
       |
       +-- Server selected, checkout slow?
       |      -> CMAP checkedOut/maxSize, maxConnecting,
       |         pool clear, idle sockets, MongoClient count
       |
       +-- Checkout fast, command slow?
       |      -> MongoDB profiler/explain, CPU/IOPS,
       |         locks, cache, shard routing
       |
       +-- Command fast, HTTP slow?
       |      -> app queue, GC, transformation,
       |         downstream calls, network
       |
       +-- Write result uncertain?
              -> retryable write semantics, stable IDs,
                 verify outcome, don't blindly duplicate
~~~

## 24. Case Studies: Three Failures All Called "Timeout"

### 24.1. Case A — No Primary

~~~text
Cluster:
  db1 UNKNOWN (network down)
  db2 SECONDARY
  db3 SECONDARY
Read preference: primary
~~~

Even though secondary pools have idle connections, a `primary` read has no eligible server. The driver waits through selection and throws `MongoTimeoutException`; **raising `maxPoolSize` from 100 to 500 does nothing**.

**Resolution:** inspect election/network, choose a business-compatible read preference (for reads only), or enforce deadlines/fallbacks.

### 24.2. Case B — Primary Exists, Pool Full

~~~text
Primary healthy; RTT 5 ms
Pool maxSize 20
Checked-out count 20
20 long aggregations running
New find request wants connection
~~~

Server selection is fast, while checkout stalls. Enlarging the pool might help if server headroom exists, though long aggregations can saturate CPU/IOPS. Inspect **CMAP + server metrics**; usually rate-limit reports and optimize queries first.

### 24.3. Case C — Pool Idle, Query Slow

~~~text
Primary healthy
Pool size 40, checked-out 5
New find gets connection in 1 ms
Execution 10 seconds (COLLSCAN + SORT)
~~~

The driver pool is not the bottleneck. Inspect `explain`, indexes, filter selectivity, sorts, and server resources; apply `maxTimeMS`/CSOT appropriately to bound execution.

### 24.4. Case D — Cold Pool / Connection Establishment Bottleneck

~~~text
Pod just started
Pool maxSize=100, size=0
maxConnecting=2
100 operations arrive
TLS/auth handshake takes 100 ms each
~~~

Checkout wait spikes even though the pool has not reached `maxSize`. Use warmup/staggered rollouts, measure establishment times, and tune `maxConnecting` carefully; **do not** blindly set `maxPoolSize=1000`.

### 24.5. Case E — Write Timeout After Server Commit

~~~text
Client sends insert _id=ORD-101
Server writes document
Response lost due to network
Client sees timeout
~~~

**Never retry with `_id=ORD-102`** if it represents the same business request. Use an idempotency key, retryable write semantics, and state/transaction outcome verification.

## 25. Safe Lab: Observing Pool, Selection, and Timeouts on a Test Replica Set

This lab requires an authorized **isolated** MongoDB replica set, Java 17+ (or a JDK compatible with your driver version), MongoDB Java Sync Driver 5.x, and a lab network endpoint. Never induce failovers, block networks, or generate heavy load on production just to trigger exceptions.

### 25.1. Lab Objectives

1. Create a `MongoClient` with a small pool limit.
2. Register JMX/CMAP to inspect `size` and `checkedOutCount`.
3. Run normal `find()` calls and observe initial connection creation.
4. Submit **bounded** concurrent tasks to observe checkout wait.
5. Test an invalid URI or unreachable `primary` on the **lab** cluster.
6. Test different CSOT settings and see which stage expires.
7. Never extrapolate production performance from a tiny fixture.

### 25.2. Initialize Test Data

In `mongosh` connected to the **lab** replica set:

~~~javascript
const lab = db.getSiblingDB("java_pool_lab")
lab.orders.insertMany([
  { _id: "O-1", tenantId: "A", status: "OPEN", amount: 100 },
  { _id: "O-2", tenantId: "A", status: "PAID", amount: 200 },
  { _id: "O-3", tenantId: "B", status: "OPEN", amount: 150 }
])
lab.orders.createIndex({ tenantId: 1, status: 1 })
~~~

Run once; subsequent runs will hit duplicate `_id` errors. This dataset is too small to create noticeable checkout contention if queries finish in milliseconds; observing waits requires a **controlled-concurrency test harness** or lab-only server delay with resource monitoring.

### 25.3. Build Dependency

**Reference** Gradle snippet—choose the version matching your application:

~~~groovy
dependencies {
    implementation 'org.mongodb:mongodb-driver-sync:5.8.0'
}
~~~

The version listed illustrates the 5.x line at writing time; do not copy blindly if your project enforces BOM or Java compatibility constraints. Worker STEP 4 **does not run Gradle**; this content guides learners to build the lab later.

### 25.4. Java Demo with JMX Listener

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.management.JMXConnectionPoolListener;
import org.bson.Document;
import java.util.concurrent.TimeUnit;

public final class PoolLab {
    public static void main(String[] args) {
        String uri = System.getenv("MONGO_LAB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException("MONGO_LAB_URI required");
        }

        JMXConnectionPoolListener jmx = new JMXConnectionPoolListener();

        MongoClientSettings settings = MongoClientSettings.builder()
            .applyConnectionString(new ConnectionString(uri))
            .applicationName("pool-timeout-lab")
            .applyToConnectionPoolSettings(pool -> pool
                .maxSize(4)
                .minSize(0)
                .maxConnecting(2)
                .addConnectionPoolListener(jmx))
            .applyToClusterSettings(cluster -> cluster
                .serverSelectionTimeout(3, TimeUnit.SECONDS))
            .build();

        try (MongoClient client = MongoClients.create(settings)) {
            MongoCollection<Document> orders = client
                .getDatabase("java_pool_lab")
                .getCollection("orders");

            System.out.println(
                orders.find(Filters.eq("_id", "O-1")).first());

            // Inspect via JConsole while process still lives:
            // use a debugger or a controlled temporary pause in lab.
        }
    }
}
~~~

This snippet **closes the client immediately after the query**, so to inspect JMX in JConsole, keep the process alive with a debugger breakpoint or controlled lab pause—never add an infinite busy-wait loop. Never leave test `MongoClient` processes running indefinitely after the lab ends.

### 25.5. Never Expose Production Secrets in Logs

Use the `MONGO_LAB_URI` environment variable or a secret manager; configure TLS CA/truststore per deployment if required. Never print the raw URI, as it may contain credentials. Always redact sensitive users, passwords, and hostnames before sharing errors.

### 25.6. Measuring Pool Size Impact

In the lab:

1. Run a test with **bounded tasks and deadlines**.
2. Start with `maxPoolSize=4`.
3. Record checkout wait and checked-out count.
4. Try `maxPoolSize=8` while keeping workload, queries, and indexes constant.
5. Compare command time, CPU, and throughput before and after.
6. If server command time increases, do not claim pool 8 is better just because checkout wait dropped.

### 25.7. Controlled Timeout Testing

- Use a shorter `serverSelectionTimeoutMS` **in the lab** with an unreachable host to observe cluster selection errors.
- Use a small pool cap plus bounded concurrent operations to observe checkout waits/failures.
- Run an unindexed query on a **small/lab dataset** with `maxTime` to observe server-side time limits safely; never run massive aggregations to overload production.
- Enable CSOT on a supporting driver and compare behavior when selection, checkout, or commands are slow.

Timeout labs are for **reading exception types and events**, not generating destructive load.

### 25.8. Expected Behavioral Signals

| Experiment | Key Signal |
|---|---|
| No eligible primary | SDAM / `ReadPreferenceServerSelector` exception. |
| Small pool cap with concurrent calls | CMAP checkout wait/failed events. |
| Slow query with idle pool | High command latency, low checkout wait. |
| Cold start with low `maxConnecting` | Rate-limited `ConnectionCreated`/`Ready` events. |
| CSOT smaller than total MongoDB call time | Client operation times out before completion. |

There are no universal "standard" latency numbers for every machine; the lab goal is **accurately distinguishing the stages**.

## 26. Common Misconceptions That Cause Production Outages

| Misconception | Problem | Reality |
|---|---|---|
| "`maxPoolSize=100` covers the whole cluster." | Driver creates one pool per server. | Multiply per server × clients × pods. |
| "100 open sockets means 100 active queries." | Sockets can be idle. | Check `checkedOutCount` / `connections.active`. |
| "Clients are lightweight; create per request." | Topology, pools, TLS, and auth are expensive. | Reuse `MongoClient`. |
| "Server selection and checkout are the same." | Eligible server selection happens before borrowing a socket. | Measure SDAM and CMAP separately. |
| "Selection timeout proves the pool is full." | There may be no eligible primary/secondary. | Inspect cluster description and read preference. |
| "Connect timeout is pool wait time." | Connect is opening a brand-new socket. | Separate `connectTimeoutMS` from checkout wait. |
| "Socket timeout is DB max execution time." | Socket read/write differs from command runtime. | Use `maxTimeMS`/CSOT and command timing. |
| "`maxTimeMS` covers the whole HTTP request." | Excludes app queues, selection, and checkout. | Enforce end-to-end deadlines. |
| "`waitQueueTimeoutMS=5s` caps 5,000 waiters." | Unit is time, not count. | Enforce bounded queues in the application. |
| "Legacy timeouts and CSOT always stack." | Java docs state many legacy options are ignored under CSOT. | Pick one deadline model deliberately. |
| "`timeoutMS=0` means time out immediately." | In CSOT, 0 disables timeout. | Use positive timeouts aligned with SLOs. |
| "Secondary read preference routes writes to secondaries." | Writes require a writable primary. | Read preference primarily governs reads. |
| "`nearest` guarantees freshest data." | Based on RTT, not replication freshness. | Use read concern and consistency policies. |
| "`localThresholdMS=15` always picks lowest RTT." | Defines a latency window of eligible servers. | Selection runs after role/tags/staleness filtering. |
| "`directConnection=true` preserves replica-set HA." | Single-server mode skips topology routing. | Use replicaSet/SRV URIs for HA. |
| "Only the seed host needs reachability." | Advertised members may be unreachable. | Ensure DNS/network reachability to all required endpoints. |
| "`maxConnecting=2` limits the pool to 2 connections." | Caps **concurrent** establishment, not max pool size. | Distinguish `maxConnecting` from `maxPoolSize`. |
| "Raising `minPoolSize` eliminates all timeouts." | Can cause connection storms and ignores selection issues. | Warm up based on measurements. |
| "Idle timeout is an operation timeout." | Manages socket lifecycle. | `maxIdleTimeMS` differs from CSOT. |
| "Write timeout guarantees the write failed." | Server may commit before response drops. | Use idempotency and verify outcomes. |
| "Retrying the whole transaction callback is always safe." | External side effects can repeat. | Use outbox or idempotent external operations. |
| "Pool full? Just multiply by 10." | DB CPU/IOPS may already be saturated. | Check server headroom and query plans. |
| "CSOT eliminates the need for HTTP deadlines." | CSOT excludes app queue and processing time. | Track absolute request deadlines. |
| "Reactive/virtual threads give infinite DB concurrency." | Server and pools still impose limits. | Enforce admission control and bounded queues. |
| "JMX `checkoutSuccess` is current checked-out count." | Cumulative counter differs from a gauge. | Read JMX `checkedOutCount` or matched events. |
| "`serverStatus.connections.current` is one client's pool." | Server counts all clients and monitors. | Check per-client driver pool metrics. |
| "Exception message strings are stable APIs." | Messages vary across versions. | Rely on classes, codes, labels, and telemetry. |
| "`maxTimeMS` error means network problem." | Usually server-side execution exceeded. | Inspect query plans and server metrics. |
| "No primary? Restart all pods." | Causes reconnect storms after election. | Use readiness probes, backoff, and SDAM. |
| "More retries fix timeouts." | Retry amplification worsens overload. | Cap attempts, add jitter, and enforce deadlines. |
| "Adding pool size adds DB CPU." | Connections do not create server capacity. | Tune queries or scale DB hardware. |

### 26.1. First-60-Seconds Diagnostic Checklist

1. Which exception class and message fragment: selection, checkout, socket, or server?
2. Does the cluster description show any eligible server?
3. What read preference, tags, or staleness filters is the driver using?
4. Is `MongoClient` truly a singleton, and what is the effective pool config?
5. What are `checkedOutCount`/`maxSize` and checkout wait?
6. Are there spikes in connections created/closed/cleared?
7. Are command p99 or server CPU/IOPS degraded?
8. Is CSOT or legacy timeout configuration currently in effect?
9. Do requests carry retry/duplication risks?
10. Are HTTP deadlines and availability SLOs still met?

## 27. Hands-On Exercises with Answers

Exercises use **hypothetical** figures, not real benchmarks or incidents. Whenever an exercise mentions failovers, network faults, or load tests, run them only on an **authorized lab or staging cluster**. The goal is choosing the right Java Driver mechanism, not forcing timeouts to "prove" performance.

### Exercise 1 — MongoClient per Request

**Prompt:** A controller calls `MongoClients.create(uri)` on every HTTP request and immediately calls `close()`. What goes wrong?

**Answer:** Every request repeats topology discovery, pool initialization, socket/TLS/auth handshakes, burning CPU/network and inflating latency and connection churn. Create a long-lived singleton `MongoClient` scoped to the app/service lifecycle and share that thread-safe client across repositories.

### Exercise 2 — Max Pool per Server

**Prompt:** A `MongoClient` connects to a 3-node replica set with `maxPoolSize=100`. Is the total pooled connection count across the cluster capped at 100?

**Answer:** No. There is a **separate pool per member**, each capped at 100; actual open connections depend on read preference and traffic. Monitoring sockets are additional to `maxPoolSize`. It is a potential ceiling, not the live open count.

### Exercise 3 — Calculating Primary Budget

**Prompt:** 20 pods, 1 `MongoClient` per pod, `maxPoolSize=80`, all writes going to the same primary. What is the ceiling on pooled app connections to the primary?

**Answer:** \(20\times80=1,600\) connections, plus monitoring and other clients for capacity planning. Do not conclude 1,600 active commands are always running.

### Exercise 4 — Two Clients per Pod

**Prompt:** 12 pods, 2 `MongoClient`s per pod, `maxSize=64` per client/server. Both clients hit the primary. What is the pooled connection ceiling to the primary?

**Answer:** \(12\times2\times64=1,536\). Separating clients intentionally by workload is fine, provided you calculate the combined budget.

### Exercise 5 — MaxConnecting

**Prompt:** Pool has `maxPoolSize=100`, `maxConnecting=2`. Does the pool hold at most two connections?

**Answer:** No. `maxConnecting` caps connections **being established concurrently**, while the pool can grow up to 100. Cold starts may be throttled by the establishment rate.

### Exercise 6 — MinPoolSize

**Prompt:** HPA simultaneously launches 100 pods with `minPoolSize=50`. What is the risk?

**Answer:** All pods warm pools at once, creating thousands of TCP/TLS/auth handshakes and a connection storm. Lower `minPoolSize` if unnecessary, stagger rollouts, check `maxConnecting`/readiness, and monitor created/ready rates.

### Exercise 7 — Idle Time

**Prompt:** A firewall closes idle sockets after 5 minutes, while the driver keeps idle connections indefinitely. What happens after a quiet period?

**Answer:** The driver checks out stale sockets and hits socket errors, pool clears, and reconnects. Set `maxIdleTimeMS` thoughtfully below the network idle timeout per docs and evaluate reconnect/CPU trade-offs.

### Exercise 8 — Connection Lifetime

**Prompt:** A developer sets `maxLifeTimeMS=500` expecting slow queries to abort after 500 ms. Is that right?

**Answer:** No. `maxLifeTimeMS` bounds **connection** lifecycle, not operation runtime. Use server-side `maxTimeMS` or CSOT/HTTP deadlines depending on the goal.

### Exercise 9 — Connection Checkout Queue

**Prompt:** Pool `maxSize=10`, 10 operations are checked out, and an 11th arrives. What happens?

**Answer:** The new operation waits to check out an available connection (up to its deadline/timeout) rather than opening an 11th connection past that server's cap. Monitor CMAP wait/failed events.

### Exercise 10 — `waitQueueTimeoutMS`

**Prompt:** Does setting `waitQueueTimeoutMS=5000` cap the queue at 5,000 tasks?

**Answer:** No. It is **milliseconds** spent waiting for a connection (legacy), not a task count. Use bounded admission/queues to cap pending requests.

### Exercise 11 — Mixing CSOT + waitQueueTimeout

**Prompt:** Java Driver 5.x sets `timeoutMS=800` and `waitQueueTimeoutMS=10000`. Can pool checkout wait 10 seconds?

**Answer:** No. Per CSOT docs, `timeoutMS` governs the operation deadline and legacy `waitQueueTimeoutMS` is ignored when CSOT is set. Verify version and override precedence.

### Exercise 12 — `timeoutMS=0`

**Prompt:** Under CSOT, does `timeoutMS=0` make MongoDB operations fail immediately upon starting?

**Answer:** No. In Java Driver CSOT docs, `0` means **no timeout** under that option. Use a positive value to enforce a deadline.

### Exercise 13 — Server Selection

**Prompt:** The driver sees a healthy secondary but no primary; a read using `ReadPreference.primary()` times out. Will enlarging the pool fix it?

**Answer:** No. There is no **eligible server**. Check elections, networking, and SDAM. If business logic tolerates stale reads, consider a different read preference for **reads only**—never convert writes into secondary writes.

### Exercise 14 — `serverSelectionTimeoutMS`

**Prompt:** `serverSelectionTimeoutMS=30000`. A request has a 200 ms SLO, and primary failover takes 3 seconds. Should the HTTP thread wait 30 seconds?

**Answer:** Usually no. Use a tighter end-to-end/CSOT deadline matching the SLO with controlled fallback/rejection so workers do not keep waiting long after callers timed out.

### Exercise 15 — Connect Timeout

**Prompt:** TCP connect to `db1` is blocked by a firewall. `maxPoolSize` is 200, yet the app throws `MongoSocketOpenException`. Should you increase `maxPoolSize`?

**Answer:** No. Check DNS, ports, firewalls, security groups, TLS/certificates, `connectTimeoutMS`, and socket establishment; pool capacity cannot create network reachability.

### Exercise 16 — Socket Timeout

**Prompt:** An aggregation needs 5 seconds while `socketTimeoutMS=1000`. After 1 second the client errors. Is it guaranteed the aggregation never ran?

**Answer:** No. The server may still be executing; a socket read timeout just means the client stopped waiting for the response. Optimize the aggregation, use appropriate `maxTimeMS`/CSOT, and avoid blindly retrying expensive work.

### Exercise 17 — Server-Side maxTime

**Prompt:** `find().maxTime(500ms)`, but the request waited 2 seconds for the pool and the server ran in 100 ms. Can HTTP latency still exceed 2 seconds?

**Answer:** Yes. `maxTimeMS` bounds only server execution, excluding pool checkout wait. Enforce end-to-end deadlines/CSOT and admission policies.

### Exercise 18 — Majority Write Timeout

**Prompt:** `insertOne` succeeded on the primary, but majority acknowledgement missed `wtimeout`. Can you safely retry immediately with a different `_id`?

**Answer:** No. `wtimeout` does not prove the write failed. Use stable idempotency keys, retryable writes, and outcome verification.

### Exercise 19 — Secondary Read Preference

**Prompt:** An app must immediately read an order just written to the primary. Should it switch to `secondaryPreferred` just because the primary is busy?

**Answer:** Only if replication lag and stale reads are acceptable to the business. If strong read-after-write consistency is required, secondaries are inappropriate. Optimize the primary, queries, and capacity first.

### Exercise 20 — Nearest

**Prompt:** Does `ReadPreference.nearest()` guarantee reading from the closest primary with the freshest data?

**Answer:** No. `nearest` selects any eligible primary or secondary within the RTT latency window with no freshness guarantee. Use explicit read concerns, read preferences, and consistency policies.

### Exercise 21 — Latency Window

**Prompt:** Three eligible secondaries have RTTs of 8, 17, and 27 ms. `localThresholdMS=15`. Which nodes fall inside the latency window?

**Answer:** Eligible RTTs must satisfy \(\le 8 + 15 = 23\text{ ms}\), so **the 8 ms and 17 ms nodes** are eligible; 27 ms is excluded. The driver will not necessarily pick 8 ms every time.

### Exercise 22 — Latency Window After Tags

**Prompt:** The fastest node at 5 ms RTT has tag `region:us`, while the request requires `region:ap`. The AP node has 40 ms RTT. Should the US node be selected?

**Answer:** Not if the tag filter is mandatory. **Eligibility filters by read preference and tags first**, then applies the latency window to the remaining candidates. Verify eligible members and tag sets.

### Exercise 23 — Max Staleness

**Prompt:** A secondary lags by several minutes. Does setting `maxStalenessSeconds` guarantee data is strictly "at most 60 seconds old" for every operation?

**Answer:** No. The driver uses estimated replication staleness and MongoDB enforces minimum thresholds based on monitoring/version; 60 seconds may not even be valid. Strong consistency requires proper read/write concerns and workflow design.

### Exercise 24 — Direct Connection

**Prompt:** To "improve HA," a developer sets `directConnection=true` pointing solely to the old primary. When that primary steps down, will the driver fail over like a full replica-set URI?

**Answer:** Do not expect it to. Direct mode forces single-server interaction; production replica-set HA requires discovery via seed list/`replicaSet` or an Atlas SRV URI.

### Exercise 25 — Advertised Hostnames

**Prompt:** An app connects to `localhost:27017` in Docker, but the replica set config advertises members `mongo1:27017`/`mongo2:27017` which the host OS cannot resolve. What fails?

**Answer:** The driver discovers unreachable member addresses and server selection fails. Fix network addressing or replica set config per approved deployment setup rather than simply raising `serverSelectionTimeoutMS`.

### Exercise 26 — CSOT Inheritance

**Prompt:** Client timeout is 800 ms, and a collection handle sets `withTimeout(2s)`. Are queries through that collection handle capped at 800 ms?

**Answer:** Under CSOT override semantics, the collection's **2-second** timeout overrides the client-level 800 ms for operations on that handle unless overridden more specifically. HTTP deadlines remain separate.

### Exercise 27 — HTTP Request Already Waited 700 ms

**Prompt:** HTTP deadline is 1 second, and the request already queued 700 ms upstream. The service starts a MongoDB call with 800 ms CSOT. Can it breach the HTTP deadline?

**Answer:** Yes. Only ~300 ms remain before the HTTP deadline, excluding response processing. Pass the **remaining deadline** into the DB call or reject early; CSOT does not track time spent before the driver call.

### Exercise 28 — Cursor Timeout Modes

**Prompt:** A cursor reads 100 batches, each taking 50 ms (5 seconds total). Do 1-second `CURSOR_LIFETIME` and 1-second `ITERATION` behave identically?

**Answer:** No. `CURSOR_LIFETIME` bounds total cursor lifetime and expires around ~1 second; `ITERATION` budgets each call/iteration per docs, allowing the cursor to finish if each batch call stays fast. Check your driver version's model and always close cursors.

### Exercise 29 — Tailable Cursors and Change Streams

**Prompt:** A change stream must run long-term. Should you set a 2-second `CURSOR_LIFETIME` CSOT and expect it to run for 24 hours?

**Answer:** No. For long-lived/tailable cursors, use appropriate iteration timeouts, resume policies, resume token checkpoints, and disconnect handling; avoid short lifetime deadlines that constantly kill the stream. Remember privileges and resource cleanup.

### Exercise 30 — JMX `checkedOutCount`

**Prompt:** Pool `size=60`, `checkedOutCount=55`, `maxSize=64`, checkout wait p99=250 ms. What should you inspect?

**Answer:** The pool is nearing its cap; check command durations, long transactions/cursors, server CPU/IOPS, and connection created/closed/cleared rates. You may cautiously raise the cap **if the server has headroom**, or shed concurrency and optimize queries if the server is saturated.

### Exercise 31 — JMX vs. serverStatus

**Prompt:** `serverStatus.connections.current=3,000`, yet the Java pool shows `checkedOutCount=12`. Is the Java listener broken?

**Answer:** Not necessarily. `current` measures all connections across all clients, idle sockets, and monitors on the server, whereas JMX measures one pool inside one `MongoClient`. Compare metric scopes first.

### Exercise 32 — Fast Commands, Slow API

**Prompt:** `CommandListener` shows `find` p99=15 ms, while HTTP p99=400 ms. Should you scale up DB CPU?

**Answer:** Not yet—no evidence points to DB CPU. Separate HTTP queuing/admission, server selection, CMAP checkout, JVM GC, response serialization, and network latency. MongoDB command execution is only one segment.

### Exercise 33 — SDAM Event

**Prompt:** At 10:00 cluster description switches `PRIMARY → UNKNOWN`, at 10:01 `SECONDARY → PRIMARY`, and writes timed out in selection during that window. Does that make sense?

**Answer:** Yes, that matches an election/topology transition. Inspect server logs, SDAM events, failover duration, and deadline/retry policies—do not blame pool size.

### Exercise 34 — Pool Clear

**Prompt:** After a network glitch, `connectionPoolCleared` spikes and checkout wait rises even though `maxPoolSize=100` and `size` is low. Why?

**Answer:** The pool was cleared/invalidated and had to rebuild connections; `maxConnecting`, TLS, and network RTT govern ramp-up. Tune reconnect/warmup rather than merely raising `maxSize`.

### Exercise 35 — Command Execution Rises with Pool Size

**Prompt:** Pool grew 50→200; checkout wait dropped, but command p99 jumped from 100 ms to 900 ms and DB CPU hit 98%. Should you keep 200?

**Answer:** Likely not; excess concurrent operations are saturating the server. Evaluate throughput, HTTP p99, rejections, and DB metrics, then consider lowering pool/admission caps, tuning queries, or scaling the DB.

### Exercise 36 — 30-Second Server Selection

**Prompt:** A test app connects with `replicaSet=rsWrong` and times out selection after ~30 seconds. Should you raise it to 120 seconds so it succeeds?

**Answer:** No. Fix the replica set name, URI, and network. A longer timeout only delays reporting the misconfiguration.

### Exercise 37 — Write Retry and Duplicate Orders

**Prompt:** An API creates an order with a brand-new random `_id` after each `MongoSocketReadTimeoutException`. What can happen?

**Answer:** The server may have committed the order on the earlier attempt, producing duplicates on retry. Use a stable `idempotencyKey`, unique business keys, retryable writes, and outcome verification.

### Exercise 38 — N+1 Queries

**Prompt:** One HTTP request executes 200 sequential `findOne` calls. Pool wait is near zero, yet the response is slow. Will enlarging the pool help?

**Answer:** Barely, because the queries run sequentially and network round trips dominate. Consider bounded `$in` batching/projections or query redesign and measure; pooling cannot eliminate 200 sequential round trips.

### Exercise 39 — Bounded Queue

**Prompt:** A service uses `Executors.newFixedThreadPool(16)` and receives 100,000 tasks. Does it hold at most 16 tasks in the JVM?

**Answer:** No. `newFixedThreadPool` uses an **unbounded task queue** by default. Use `ThreadPoolExecutor` with an `ArrayBlockingQueue`, controlled rejection/degradation, and end-to-end deadlines.

### Exercise 40 — Designing a Production Incident Diagnosis

**Prompt:** A 25-pod application using Java Driver 5.x (1 `MongoClient` per pod, pool max 100) sees HTTP p99 spike after failover. Logs show `MongoTimeoutException` without clarifying the stage; write requests have retries. Outline a diagnosis and remediation plan.

**Suggested Answer:**

1. Compute the pooled connection ceiling to the primary: `25×100=2,500`, plus monitors and other clients.
2. Gather exception classes, error codes/labels, and **redacted cluster descriptions** to separate server selection, checkout, socket, and server execution.
3. Inspect SDAM timeline: primary election, host reachability, TLS/DNS, read preferences.
4. Inspect CMAP: pool clears, connections created/ready, checkout wait, `checkedOut`/`maxSize`, `maxConnecting`.
5. Inspect command p95/p99 and `serverStatus` CPU/IOPS/connections/queues; never diagnose from HTTP p99 alone.
6. Check pod restarts/HPA and actual `MongoClient` instance counts to avoid reconnect storms.
7. Audit `retryReads`/`retryWrites` and manual retries, total attempt rates, jitter, and attempt caps.
8. Align deadlines from ingress to MongoDB: CSOT or legacy timeout model per driver version, never stacking blindly.
9. Guarantee stable idempotency keys and transaction outcome handling for ambiguous writes.
10. Use canary/controlled load tests to tune `maxPoolSize`, `maxConnecting`, admission caps, and rollback; measure completed throughput, p95/p99, timeouts/rejections, and recovery.

A valid answer is never simply "raise `maxPoolSize` to 500." It requires **evidence of the slow stage, target SLOs, and fixes matched to the bottleneck**.

## 28. Quick Reference for Java Developers

### 28.1. Picking Options by Goal

| What You Want to Control | Config / API to Read | Common Pitfall to Avoid |
|---|---|---|
| Max pooled connections **per server** | `maxPoolSize` / `maxSize()` | Not a global cap across all servers/pods. |
| Minimum warm sockets | `minPoolSize` / `minSize()` | Not an immediate readiness guarantee. |
| **Concurrent** connection openings | `maxConnecting` | Not the max pool size. |
| Closing idle sockets | `maxIdleTimeMS` | Not a query timeout. |
| Recycling sockets by age | `maxLifeTimeMS` | Not an operation deadline. |
| Waiting for an eligible server | `serverSelectionTimeoutMS` | Not pool checkout wait. |
| Selecting nearby RTT members/regions | `readPreference`, tags, `localThresholdMS` | Does not guarantee fresh data. |
| Opening a new TCP socket | `connectTimeoutMS` | Not pooled connection wait time. |
| Waiting on socket read/write | Legacy `socketTimeoutMS` | Not the whole HTTP deadline. |
| Waiting to check out a pooled connection | Legacy `waitQueueTimeoutMS` / `maxWaitTime()` | Does not cap waiter count. |
| Server command runtime | `maxTimeMS` / `FindIterable.maxTime()` | Excludes checkout and selection. |
| Waiting on write concern acknowledgement | `wTimeoutMS` | Does not roll back applied writes. |
| Overall MongoDB operation deadline | `timeoutMS` / `MongoClientSettings.Builder.timeout()` | CSOT experimental; excludes app queue before call. |
| Collection-level timeout | `collection.withTimeout(...)` | Only on CSOT-supporting drivers. |
| Transaction timeout | `TransactionOptions.timeout(...)` | Does not replace unknown-commit handling. |
| Cursor lifetime vs. iteration timeout | `timeoutMode(...)` | Differs for tailable/change-stream lifecycles. |

### 28.2. Picking Observability Tools

| Question | Tool |
|---|---|
| Does the driver see a primary? | SDAM cluster description, Cluster/Server listeners. |
| Is the pool full? | JMX `size`, `checkedOutCount`, `maxSize`. |
| How long is checkout wait? | CMAP `CheckOutStarted`/`CheckedOut`/`Failed` + tracing. |
| Are too many sockets being created? | CMAP created/ready/closed, `maxConnecting`, network/TLS metrics. |
| Is the server running slow commands? | `CommandListener`, server profiler, `explain`. |
| DB CPU/IOPS/lock pressure? | Atlas metrics/`serverStatus`, `$currentOp`. |
| Where is the HTTP request slow? | End-to-end distributed traces and queue metrics. |
| Did a timed-out write commit? | Error labels, stable business IDs, retryable writes/transactions docs. |

### 28.3. Sample Configuration Budget Sheet for Design Reviews

~~~text
Service:                  checkout-api
Java Driver:              5.x.y
MongoDB topology:         replica set rs0
Max application pods:     20
MongoClients per pod:     1
maxPoolSize per server:   64
maxConnecting per pool:   4
minPoolSize per server:   4
readPreference:           primary
serverSelectionTimeoutMS: based on SLO
CSOT timeoutMS:           based on remaining request deadline
admission concurrency:    bounded per instance
HTTP queue:               bounded
retry attempts:           capped and idempotent
monitoring:               CMAP + SDAM + command + serverStatus
~~~

This is a **configuration template**, not default recommended numbers. Choose values after measuring workload/server capacity and testing peak traffic and failover behavior.

## 29. Official Documentation

The MongoDB pages below are the authoritative source for syntax, defaults, and semantics. Several links use the `current` path, so **always check your exact Java Driver version**, server version, Atlas tier/topology, and notes on CSOT/overload handling before applying.

### 29.1. Java Driver Pools, Clusters, and Networking

1. [MongoDB Java Sync Driver — Connection Pools](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/connection-pools/) — per-server pools, default `maxPoolSize=100`, `maxConnecting=2`, min/idle/lifetime/wait settings.
2. [MongoDB Java Sync Driver — Cluster Settings](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/cluster-settings/) — default 30s `serverSelectionTimeoutMS`, default 15ms `localThresholdMS`, replica set name/direct connection.
3. [MongoDB Java Sync Driver — Server Settings](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/server-settings/) — `heartbeatFrequencyMS`, monitoring modes, and server listeners.
4. [MongoDB Java Sync Driver — Socket Settings](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/socket-settings/) — 10s `connectTimeoutMS`, 0 `socketTimeoutMS` in current docs.
5. [MongoDB Java Sync Driver — Connection Troubleshooting](https://www.mongodb.com/docs/drivers/java/sync/current/connection/connection-troubleshooting/) — diagnostic messages when server selection cannot find a primary/host.
6. [MongoDB Manual — Connection String Options](https://www.mongodb.com/docs/manual/reference/connection-string-options/) — URI parameters and cross-driver differences.

### 29.2. CSOT and Read Preference

7. [MongoDB Java Sync Driver — Client-Side Operation Timeout](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/csot/) — `timeoutMS`, experimental status, timeout inheritance, ignored legacy options, transaction/cursor modes.
8. [MongoDB Java Sync Driver — Read/Write Settings](https://www.mongodb.com/docs/drivers/java/sync/current/crud/read-write-config/) — `ReadPreference`, `ReadConcern`, `WriteConcern`, and collection-level overrides.
9. [MongoDB Manual — Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/) — primary/`secondaryPreferred`/nearest, maxStaleness, and tags.
10. [MongoDB Manual — Read Preference Tags](https://www.mongodb.com/docs/manual/core/read-preference-tags/) — filtering eligible members by tags.
11. [MongoDB Manual — maxStalenessSeconds](https://www.mongodb.com/docs/manual/core/read-preference-staleness/) — estimating secondary staleness and configuration limits.
12. [MongoDB Manual — maxTimeMS](https://www.mongodb.com/docs/manual/reference/method/cursor.maxTimeMS/) — server-side execution limit vs. client/network timeouts.
13. [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — majority, journal, and `wtimeout`.

### 29.3. Observability and Resource Behavior

14. [MongoDB Java Sync Driver — Monitoring](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/monitoring/) — CMAP, JMX `JMXConnectionPoolListener`, SDAM/Command events.
15. [MongoDB Driver Specifications — CMAP](https://github.com/mongodb/specifications/blob/master/source/connection-monitoring-and-pooling/connection-monitoring-and-pooling.md) — connection pool events/specification.
16. [MongoDB Driver Specifications — Server Selection](https://github.com/mongodb/specifications/blob/master/source/server-selection/server-selection.md) — selection algorithm, read preference, and latency window.
17. [MongoDB Manual — serverStatus](https://www.mongodb.com/docs/manual/reference/command/serverStatus/) — server connections/locks/resource statistics.
18. [MongoDB Manual — $currentOp](https://www.mongodb.com/docs/manual/reference/operator/aggregation/currentOp/) — active operations/latency/locks.
19. [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — query plans/`executionStats`, fixing slow queries.
20. [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — transaction lifetime, retry/commit ambiguity.
21. [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/) — retry semantics and idempotency protection.

### 29.4. What to Verify Before Copying Code

1. Driver 4.x or 5.x? Do `timeout()`, `withTimeout()`, and `timeoutMode()` exist?
2. Is CSOT configured at client, database, collection, session, or transaction level?
3. Are `maxWaitTime()`, `socketTimeoutMS`, and `maxTimeMS` still active under CSOT?
4. Does read preference satisfy business consistency and transaction constraints?
5. Can server selection actually pick an eligible server on the real topology?
6. Do cluster-advertised member hostnames resolve and route from the deployment?
7. Is the pool **full**, **warming**, or **clearing/reconnecting**?
8. Does the MongoDB server have headroom or is it saturated on CPU/IOPS/locks?
9. Do retryable writes/transactions enforce idempotency and deadline policies?
10. Have load tests verified both steady state and failover/recovery?

## 30. Conclusion

In the **MongoDB Java Driver**, a request must **select an eligible server**, **check out a connection from the right pool**, and **execute the command within its deadline**. These three stages interact but cannot substitute for one another; the same "timeout" symptom can stem from networking, elections, pool exhaustion, or slow queries.

Keep four points in mind:

1. **Share `MongoClient` and understand per-server pools.** `maxPoolSize` is not the entire application's connection total; factor in client count, pod count, topology, and monitoring sockets. `maxConnecting` throttles socket creation speed, not pool capacity.
2. **SDAM and server selection decide "where to send," while CMAP decides "which connection to borrow."** Fix `serverSelectionTimeoutMS` via topology/read preference/network; fix `waitQueueTimeoutMS`/checkout wait via pool lifecycle and concurrency; `connectTimeoutMS` and `socketTimeoutMS` govern networking/sockets. Never enlarge the pool when no primary is eligible.
3. **Timeouts must align with deadlines and semantics.** `maxTimeMS` is a server execution limit; `timeoutMS` in Java CSOT bounds the end-to-end MongoDB operation and overrides several legacy options (currently experimental). Client timeouts **do not mean writes or transactions rolled back**, so retries must be idempotent.
4. **Measure the real bottleneck before tuning.** Inspect CMAP/JMX/SDAM/command traces, MongoDB `serverStatus`/`explain`, and HTTP SLOs. When the DB is overloaded, apply bounded admission, query optimization, and capacity planning; only adjust pools stepwise with canary/rollback when the pool is genuinely the bottleneck and the server has headroom.

**Connection pool tuning is not about pushing the maximum number of requests into MongoDB—it is about ensuring every request is routed properly, never waits indefinitely, finishes within useful time, and preserves data correctness when failures occur.**
