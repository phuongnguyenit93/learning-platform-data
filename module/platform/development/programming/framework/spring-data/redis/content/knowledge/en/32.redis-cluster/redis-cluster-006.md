# Multi-Node Operations via RedisClusterConnection

In Redis Standalone, all keys are managed by a single Redis server. When moving to **Redis Cluster**, the keyspace is divided into **16,384 hash slots** distributed across multiple primary nodes. A Spring Data Redis application can still use familiar APIs like `RedisTemplate.opsForValue()`, yet tasks such as **discovering topology, inspecting a key's owner node, scanning keys on individual nodes, or monitoring multiple shards** require a deeper understanding of `RedisClusterConnection`.

**`RedisClusterConnection` is Spring Data Redis's cluster-aware connection interface**, enabling interaction with Redis Cluster connections and cluster-specific operations. However, it **does not turn multiple Redis nodes into a single server with global transactions**. Multi-node operations must routinely address slot-based routing, cross-slot commands, partial results on node failure, slot migration windows, and differences between primaries and replicas.

This lesson progresses from Redis Cluster fundamentals to Java examples using `RedisClusterConnection`, then analyzes how to design true multi-node operations in a Spring Data Redis application.

## 1. How does Redis Cluster distribute keys?

Redis Cluster has 16,384 hash slots, from `0` to `16383`. For normal keys, Redis determines the slot from the CRC16 of the key name per Redis Cluster rules, modulo the slot count.

```text
                       Redis Cluster
              16,384 hash slots (0..16383)
                             |
              +--------------+--------------+
              |              |              |
              v              v              v
         Primary A       Primary B       Primary C
        slot 0..5400   slot 5401..10900  slot 10901..16383
              |              |              |
              v              v              v
          Replica A      Replica B       Replica C
```

The slot ranges in the diagram are illustrative; the actual number of primaries and slot distribution depend on your cluster.

Example:

```text
product:101        -> one slot -> one primary
product:102        -> another slot -> possibly another primary
product:103        -> another slot -> possibly a third primary
```

When the application sends `GET product:101`, a cluster-aware Redis client such as Lettuce routes to the node currently managing that key's slot, based on discovered topology and redirection responses when necessary.

**A key is routed by slot, not permanently bound to one machine.** When Redis Cluster reshards or fails over, the node managing a slot can change. Applications should never cache a long-lived `key → node address` mapping as an immutable truth.

### Hash tags to place related keys in the same slot

If you must operate on multiple keys belonging to one aggregate, Redis Cluster supports **hash tags**:

```text
cart:{user42}:items
cart:{user42}:total
cart:{user42}:version
```

The `{user42}` substring is used in slot calculation, so all three keys map to the same hash slot. This is useful when a Lua script or multi-key transaction is needed.

Do not place all keys of an entire system under a shared hash tag like `{all}`: that concentrates all load into one slot, undermining Cluster distribution.

## 2. What is RedisClusterConnection?

Related interface types:

| API | Primary Role |
|---|---|
| `RedisConnectionFactory` | Provides connections to Redis; exposes a cluster connection path when configured properly |
| `RedisConnection` | Low-level connection API for standard Redis commands |
| `RedisClusterConnection` | Cluster-aware connection with node/slot/topology-specific operations |
| `RedisTemplate<K,V>` | High-level API using serializers and the connection factory |
| `StringRedisTemplate` | RedisTemplate configured with String serializers |
| `RedisClusterNode` | Describes a node known to Spring Data Redis in the Cluster |
| `LettuceConnectionFactory` | Connection factory backed by Lettuce, configurable for Redis Cluster |

`RedisClusterConnection` is appropriate when the application needs to work with **cluster-specific semantics** rather than single-key operations alone.

Typical capabilities:

- Retrieving the list of nodes currently known to the Cluster.
- Inspecting overall cluster info.
- Determining the node or slot associated with a key.
- Scanning data on specific nodes where supported by the API.
- Querying key counts in a slot or other cluster-specific metadata.
- Sending regular commands while letting the connection/driver route by key.

**Not every Redis Cluster operation must use `RedisClusterConnection` directly.** For key-based `GET`/`SET`, `RedisTemplate` is usually clearer and easier to maintain; the cluster-aware driver still handles routing underneath. Drop down to the connection layer only when you need topology inspection, node-scoped commands, or lower-level operational control.

### Do not mistake it for a single physical connection

The name `RedisClusterConnection` does not mean every command travels over one TCP socket or hits one Redis server. A library's cluster-aware connection can manage routes to multiple nodes and multiple physical connections depending on the driver.

Therefore, you cannot infer:

```text
Using the same RedisClusterConnection
             |
             v
All commands run in one Redis transaction   <-- FALSE
```

A Redis transaction is scoped to a specific connection/node and subject to slot constraints. Redis Cluster does not provide general-purpose atomic transactions across multiple primaries.

## 3. Preparing a Spring Data Redis application to connect to a Cluster

A Spring Boot application using Redis with Lettuce typically includes the dependency:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

Example Redis Cluster configuration in `application.yml`:

```yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - redis-node-1:6379
          - redis-node-2:6379
          - redis-node-3:6379
        max-redirects: 5
      timeout: 2s
```

These addresses are examples. Production setups require real hosts, TLS, ACLs, secrets, timeouts, and reconnect policies suited to your infrastructure.

The nodes in configuration are **seed nodes** enabling the driver to reach the Cluster and discover topology. They are not necessarily all nodes in the cluster, nor does it mean only those three nodes will be contacted.

### 3.1. Configuring the connection factory manually when needed

If not relying on auto-configuration, you can construct the factory as follows:

```java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisClusterConfiguration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;

@Configuration
public class RedisClusterConfig {

    @Bean
    public RedisConnectionFactory redisConnectionFactory() {
        RedisClusterConfiguration cluster =
                new RedisClusterConfiguration(
                        List.of(
                                "redis-node-1:6379",
                                "redis-node-2:6379",
                                "redis-node-3:6379"));

        cluster.setMaxRedirects(5);

        return new LettuceConnectionFactory(cluster);
    }
}
```

In real Spring Boot projects, normally pick **one way to configure the connection factory**: either via properties and auto-configuration, or an explicitly managed bean. Creating multiple factories without clear separation can send `RedisTemplate`, cache managers, and `RedisClusterConnection` calls to different Redis deployments.

If you need replica reads, automatic topology refresh, or custom TLS/SSL, configure them on the driver/Lettuce client configuration; `maxRedirects` does not replace those settings.

### 3.2. Do not use Standalone to infer Cluster behavior

A test that merely executes `GET`/`SET` on Redis Standalone proves your serializer works, but does not prove:

- Node discovery works properly.
- Multi-slot routing works properly.
- `MOVED`/`ASK` handling during resharding works.
- Multi-key same-slot scripts work.
- Partial node failures are reported and handled accurately.
- Multi-node scanning neither skips keys nor double-counts duplicates.

These requirements must be verified against a **real Redis Cluster or a test environment simulating a true Cluster topology**, not a single Redis server.

## 4. Obtaining RedisClusterConnection from RedisConnectionFactory

Spring Data Redis provides a path to obtain a cluster connection from the connection factory when configured for Cluster mode.

```java
import org.springframework.data.redis.connection.RedisClusterConnection;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.stereotype.Service;

@Service
public class ClusterConnectionExample {

    private final RedisConnectionFactory factory;

    public ClusterConnectionExample(
            RedisConnectionFactory factory) {
        this.factory = factory;
    }

    public void inspectConnection() {
        try (RedisClusterConnection connection =
                     factory.getClusterConnection()) {

            // Cluster-aware operations are performed here.
            System.out.println(connection.clusterGetClusterInfo());
        }
    }
}
```

Only call `getClusterConnection()` when the application is genuinely configured for Cluster mode. A connection factory that does not support Cluster mode may reject the request; treat that as a configuration error rather than assuming a "single-node Cluster".

Low-level connections must be **closed/released within their proper lifecycle**. In the example, `try-with-resources` ensures `close()` runs upon exit. Do not cache a `RedisClusterConnection` obtained from the factory and share it arbitrarily across threads or keep it open across failovers/reshards.

Underlying connection implementations may manage shared connections or pools; calling `close()` lets the abstraction return/release resources according to the Spring Data Redis contract.

## 5. Discovering the node list and Cluster status

### 5.1. clusterGetNodes()

`RedisClusterConnection.clusterGetNodes()` allows the application to inspect the nodes known to Spring Data Redis and the driver.

```java
import org.springframework.data.redis.connection.RedisClusterConnection;
import org.springframework.data.redis.connection.RedisClusterNode;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.stereotype.Service;

@Service
public class ClusterTopologyService {

    private final RedisConnectionFactory factory;

    public ClusterTopologyService(RedisConnectionFactory factory) {
        this.factory = factory;
    }

    public void printKnownNodes() {
        try (RedisClusterConnection connection =
                     factory.getClusterConnection()) {

            Iterable<RedisClusterNode> nodes =
                    connection.clusterGetNodes();

            for (RedisClusterNode node : nodes) {
                System.out.println(
                        "Node=" + node.getId()
                        + " address=" + node.getHost()
                        + ":" + node.getPort());
            }
        }
    }
}
```

The node list is a **snapshot of topology at query time**, not an immutable registry. During failover or slot migration, topology changes. To detect and react to topology shifts, rely on driver refresh and observability—do not query once at startup and assume it remains valid forever.

Redis Cluster contains **primaries and replicas**. When iterating nodes for a data operation, decide whether it should run on primaries, replicas, or both. For example, scanning keys across all primaries is usually preferable to scanning replicas as well, since replicas hold copies and would duplicate counts.

### 5.2. clusterGetClusterInfo()

`clusterGetClusterInfo()` returns summary Cluster information via the Spring Data Redis abstraction.

```java
public String clusterHealthSummary(
        RedisConnectionFactory factory) {

    try (RedisClusterConnection connection =
                 factory.getClusterConnection()) {
        return connection.clusterGetClusterInfo().toString();
    }
}
```

Summary info is helpful for health checks or investigations, yet **a healthy cluster state does not prove multi-node business operations execute atomically or cannot fail**.

If node-specific monitoring is needed, also observe connection health, memory, command throughput, latency, and replica lag per node. Metrics from one seed node do not represent the entire cluster.

## 6. Finding the node managing a key

To check where a key is currently managed, call `clusterGetNodeForKey(...)` with the **key's byte array**, not an unserialized Java value.

Example:

```java
import org.springframework.data.redis.connection.RedisClusterConnection;
import org.springframework.data.redis.connection.RedisClusterNode;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.serializer.StringRedisSerializer;

public RedisClusterNode findOwner(
        RedisConnectionFactory factory,
        String redisKey) {

    StringRedisSerializer serializer = new StringRedisSerializer();
    byte[] rawKey = serializer.serialize(redisKey);

    try (RedisClusterConnection connection =
                 factory.getClusterConnection()) {
        return connection.clusterGetNodeForKey(rawKey);
    }
}
```

If the application uses another serializer, the byte array passed to slot lookup must match the **exact physical key bytes Redis receives**. A Java key with the same display string serialized into two different byte sequences can produce different key names and slots.

Example:

```text
Java key = "product:101"

String serializer:
    Redis key bytes = UTF-8("product:101")

Serializer with prefix/different format:
    Redis key bytes = a different byte sequence
    => physical key and slot may differ
```

Note also: `clusterGetNodeForKey(...)` reflects topology known at that moment. If the Cluster is actively moving slots, the real owner node can change right after the lookup. Never use a one-time lookup to hardcode static routing logic for hours.

### Viewing hash slots directly via Redis CLI

```bash
redis-cli -c -h redis-node-1 -p 6379 \
    CLUSTER KEYSLOT 'cart:{user42}:items'

redis-cli -c -h redis-node-1 -p 6379 \
    CLUSTER KEYSLOT 'cart:{user42}:total'
```

Two keys sharing the `{user42}` hash tag must map to the same slot. This is especially important before using Lua scripts or multi-key transactions.

## 7. Sending per-key commands over the same RedisClusterConnection

The simplest way to operate across multiple nodes is to **iterate over keys belonging to different slots and let the cluster-aware driver route each command**.

Example reading multiple string keys:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.data.redis.connection.RedisClusterConnection;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.serializer.StringRedisSerializer;
import org.springframework.stereotype.Service;

@Service
public class ClusterKeyReader {

    private final RedisConnectionFactory factory;
    private final StringRedisSerializer serializer =
            new StringRedisSerializer();

    public ClusterKeyReader(RedisConnectionFactory factory) {
        this.factory = factory;
    }

    public Map<String, String> readValues(List<String> keys) {
        Map<String, String> result = new LinkedHashMap<>();

        try (RedisClusterConnection connection =
                     factory.getClusterConnection()) {

            for (String key : keys) {
                byte[] rawKey = serializer.serialize(key);

                // Cluster-aware connection/driver determines route
                // from key/slot under the active Cluster config.
                byte[] rawValue =
                        connection.stringCommands().get(rawKey);

                result.put(key, rawValue == null
                        ? null
                        : serializer.deserialize(rawValue));
            }
        }

        return result;
    }
}
```

If the list contains:

```text
product:101
product:102
product:103
```

the three keys may be served by three different primaries. On the Java side we use one `RedisClusterConnection` abstraction, while each `GET` command is routed individually by slot.

**The example above executes commands sequentially**, not as an atomic `MGET` operation and not automatically pipelined. Some libraries/drivers support scatter-gather or Cluster pipelining optimizations in certain APIs, so check your exact version instead of assuming it from this loop.

### When to use RedisTemplate instead of the low-level connection?

For a business path that only needs `GET`/`SET`:

```java
@Service
public class ProductCache {

    private final StringRedisTemplate redis;

    public ProductCache(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public String get(String productId) {
        return redis.opsForValue()
                .get("product:" + productId);
    }
}
```

`StringRedisTemplate` is usually clearer because it manages serializers and connection lifecycles automatically. Provided the factory is configured for Redis Cluster, key-based commands still route across the Cluster.

**Use `RedisClusterConnection` when you genuinely need cluster-specific APIs**, such as node discovery, placement inspection, scanning a single node, or building operational tools.

## 8. Scanning keys across multiple nodes with SCAN

A classic task requiring topology awareness is **listing keys matching a pattern** for reporting or operational tooling.

In Standalone, one `SCAN` command covers the single server. In a Cluster, **a `SCAN` command sent to one node does not scan all nodes**. To search the whole Cluster, iterate over the primaries holding slots and scan each node via supported APIs.

```text
          Pattern: cache:product:*
                      |
                      v
            Cluster node discovery
                      |
          +-----------+-----------+
          |           |           |
          v           v           v
      Primary A   Primary B   Primary C
          |           |           |
      SCAN match  SCAN match   SCAN match
          |           |           |
          +-----------+-----------+
                      |
                      v
              Aggregate results
                      |
                      v
            Dedupe / batch process
```

### 8.1. Spring Data Redis example

In Spring Data Redis versions exposing a node-scoped scan overload, a common pattern is `scan(RedisClusterNode, ScanOptions)`:

```java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.redis.connection.RedisClusterConnection;
import org.springframework.data.redis.connection.RedisClusterNode;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.Cursor;
import org.springframework.data.redis.core.ScanOptions;
import org.springframework.data.redis.serializer.StringRedisSerializer;

public List<String> scanProductKeys(
        RedisConnectionFactory factory) {

    StringRedisSerializer serializer = new StringRedisSerializer();
    ScanOptions options = ScanOptions.scanOptions()
            .match("cache:product:*")
            .count(200)
            .build();

    List<String> result = new ArrayList<>();

    try (RedisClusterConnection connection =
                 factory.getClusterConnection()) {

        for (RedisClusterNode node : connection.clusterGetNodes()) {
            // Scan primaries to avoid duplicating replica data.
            if (!node.isMaster()) {
                continue;
            }

            try (Cursor<byte[]> cursor =
                         connection.scan(node, options)) {

                while (cursor.hasNext()) {
                    result.add(
                            serializer.deserialize(cursor.next()));
                }
            }
        }
    }

    return result;
}
```

**Conditions for this example:** the `scan(node, options)` API and node role properties must exist in your Spring Data Redis version. Before integrating, verify exact method signatures and return types in your project's dependencies; modules/versions may differ in abstraction details.

Important points to keep in mind:

- `COUNT 200` is only a **work-size hint**, not a guarantee that Redis returns exactly 200 keys per batch.
- `SCAN` is cursor-based iteration, not a point-in-time atomic snapshot.
- A key may be returned multiple times, especially when data mutates during the scan; callers must tolerate duplicates.
- If keys are added or deleted while scanning, the result is not a consistent snapshot.
- Resharding, failover, or role changes mid-scan can cause missed or duplicated keys.
- Collecting all keys into an in-memory `List` can consume excessive memory. In production, process in batches or stream results with backpressure.
- Scanning primaries is standard to avoid counting replica copies twice; never assume reading the same pattern on replicas matches primary consistency.

**Do not use `KEYS cache:product:*` in large production clusters** as a shortcut for cluster-wide scanning: `KEYS` can block a node and still does not collect across the entire cluster on its own.

### 8.2. When the goal is bulk deletion

If you need to delete many keys matching a pattern, do not treat "SCAN then DEL everything at once" as a zero-cost operation:

```text
SCAN each primary
    |
    v
Collect matching keys
    |
    v
Split into small batches
    |
    v
DEL/UNLINK per key or slot-compatible group
    |
    v
Monitor errors, rate, and retry counts
```

`UNLINK` can offload synchronous memory reclamation for some values, yet still generates load and requires proper API usage. Pattern-based deletion **is not atomic across the Cluster**. Keys can be recreated while scanning or deleting.

For large cached datasets, consider versioned key prefixes or controlled invalidation instead of scanning and deleting millions of keys inside an HTTP request.

## 9. Counting keys by slot and by node

Redis Cluster exposes key counts for a slot and commands to inspect keys belonging to a slot. Spring Data Redis supports corresponding cluster-scoped operations at the `RedisClusterConnection` level in versions providing those APIs.

Purposes of these operations:

- Identifying which slots hold concentrated key counts.
- Checking data distribution after slot migrations.
- Supporting diagnostics or migration tooling.
- Verifying whether related keys land in the same slot as designed.

At the Redis CLI level, related commands include:

```bash
redis-cli -c -h redis-node-1 -p 6379 CLUSTER INFO
redis-cli -c -h redis-node-1 -p 6379 CLUSTER NODES
redis-cli -c -h redis-node-1 -p 6379 CLUSTER SLOTS
redis-cli -c -h redis-node-1 -p 6379 CLUSTER KEYSLOT 'cart:{user42}:items'
```

Slot counts or node counts must be interpreted in the context of **timestamp, queried node, and ongoing resharding**. Do not treat a transient metric as an exact business counter. Topology and key mutations during measurement can keep an aggregate report from reflecting an atomic snapshot.

### Do not confuse node counts with unique logical keys

If you scan both primaries and replicas, the same key appears on multiple nodes due to replication. Summing key counts across all nodes without filtering roles **counts replicated copies multiple times**, not unique logical keys in the Cluster.

If you simply need a count of cached entries or business entities, evaluate maintaining an explicit counter/inventory in a suitable datastore instead of running a full-cluster scan on every API call.

## 10. Multi-key commands and CROSSSLOT limits

Some Redis commands accept multiple keys, such as:

```redis
MGET product:101 product:102
MSET product:101 value1 product:102 value2
```

On Redis Cluster, multi-key commands sent to a single node typically require all keys to belong to the **same hash slot**. If keys reside in different slots, Redis can return `CROSSSLOT`, or the client/driver must split the operation by slot where a specific API supports it.

Do not assume every `multiGet`/`multiSet` overload in Spring Data Redis behaves identically across all drivers and versions. Some implementations provide client-side scatter-gather for certain calls, yet those operations **do not become Cluster-wide atomic**.

### Comparing three multi-key read strategies

| Approach | Characteristics | Limitations |
|---|---|---|
| Sequential `GET` per key | Each key routes individually; easy per-command error handling | Multiple round trips; slow for large batches |
| Same-slot `MGET` | One Redis command reading multiple string values | Restricted to matching data types and same-slot keys |
| Scatter-gather/pipeline per node | Can boost throughput for cross-slot keys | Driver/API-dependent; no global snapshot/transaction |

For large batches, group by slot or owner node if communication optimization is truly required, remembering that owners can shift during resharding. Never hardcode partitioning using node addresses looked up long ago.

### Hash tags for key groups that must operate together

```text
order:{1001}:state
order:{1001}:items
order:{1001}:payment
```

Keys sharing `{1001}` can participate in the same multi-key command or Cluster-compatible Lua script. In exchange, all data for one aggregate shares one slot. Choose hash tag granularity small enough so aggregates do not pile onto a single primary.

## 11. MULTI/EXEC transactions in Redis Cluster

A Redis `MULTI`/`EXEC` transaction has its execution boundary on the appropriate node/connection. Redis Cluster does not turn multi-slot transactions into two-phase distributed transactions.

```text
Primary A (slot X)             Primary B (slot Y)
       |                              |
       | MULTI                        |
       | SET key-X                    | SET key-Y
       | EXEC                         |
       |                              |
       +------ No shared atomic commit ------+
```

If business logic must update multiple keys in the same slot, an appropriate Redis transaction or Lua script can be used. If keys live in different slots/primaries, redesign consistency boundaries or use a transactional system with appropriate guarantees.

**Using the same `RedisClusterConnection` does not mean commands targeting different nodes share one `MULTI`.** Calling `multi()`/`exec()` without understanding slots, connection routing, and transaction state can fail or create false consistency assumptions.

In Spring Data Redis, `SessionCallback` is commonly used for Redis transactions via imperative `RedisTemplate`. However, that session model does not enable Cluster-wide transactions: it remains bound by Redis server and hash slot limits.

### Redis transactions do not roll back runtime errors SQL-style

Even when all keys share a slot and `EXEC` runs, a runtime error on one Redis command inside the transaction does not cause Redis to undo previously succeeded commands. Thus, "same slot" enables **co-located execution within one Redis boundary**, not a replacement for validation and recovery design.

## 12. Lua scripting on a Cluster

Lua scripts are commonly used to check conditions and write data in one server-side execution on Redis:

```lua
-- KEYS[1] = inventory:{sku42}:available
-- ARGV[1] = requested quantity

local qty = tonumber(ARGV[1])
if not qty or qty <= 0 or qty ~= math.floor(qty) then
    return -1
end

local rawStock = redis.call('GET', KEYS[1])
local stock = tonumber(rawStock)

if not stock or stock < qty then
    return 0
end

redis.call('DECRBY', KEYS[1], ARGV[1])
return 1
```

This is a single-key example, so it avoids multi-slot issues. If a script accesses multiple keys:

```text
inventory:{sku42}:available
inventory:{sku42}:reserved
inventory:{sku42}:processed
```

those keys must satisfy Redis Cluster slot constraints and be explicitly declared via `KEYS` per the script contract.

Scripting has two advantages over client-side read-then-write:

1. Conditions are checked directly on the server, eliminating gaps between round trips.
2. Steps inside the script cannot be interleaved by other clients' commands on the executing node.

However:

- Scripts do not run across multiple primaries as a distributed transaction.
- Long-running scripts can block other commands on that primary.
- If one write succeeds and the script hits a runtime error in a later step, the earlier write **does not automatically roll back**.
- If the client times out or failover happens mid-`EVAL`, the outcome may be ambiguous from the application's perspective.
- `EVALSHA` can hit `NOSCRIPT` on another node or after script cache eviction; the executor/driver must handle reloading properly.

### When isn't direct RedisClusterConnection needed for scripts?

For a business script, usually declare a `RedisScript<T>` and call `RedisTemplate.execute(...)`. A cluster-aware connection routes by the script keys where supported. Drop down to lower-level APIs only when cluster-specific control or operational behavior is needed.

Do not manually select a primary by IP address and send a multi-key script without verifying hash slots. Letting the driver route by key and explicitly verifying slot conditions is far more maintainable.

## 13. Pipelining across multiple nodes

Pipelining reduces round trips by sending multiple commands before collecting all replies. On Redis Cluster, keys can span multiple primaries, so pipeline behavior depends on the driver and connection configuration.

```text
Java application
      |
      +---- pipeline commands for slot A ---> Primary A
      |
      +---- pipeline commands for slot B ---> Primary B
      |
      +---- pipeline commands for slot C ---> Primary C
```

Things to check:

- Does the specific pipeline API support Cluster mode?
- How does the driver route each command by key and reassemble results?
- How is result ordering correlated back to command order?
- Can one slow node stall the entire batch?
- If one node fails, might writes on other nodes have already been applied?
- Are there limits on command count, payload size, and memory?

**Pipelining does not provide cluster-wide atomicity.** A batch can mutate data on primary A and fail on primary B. Never blindly retry an entire batch containing counter increments or non-idempotent event writes.

For multi-key reads, consider high-level APIs where the driver supports scatter-gather. For sensitive writes, design idempotency and reconciliation rather than relying on a pipeline as a commit boundary.

## 14. Redis Cluster resharding and MOVED/ASK responses

Cluster topology is not immutable. When slots move between primaries, the client can receive:

- **`MOVED`:** the slot now belongs to another node; the client must use the new route and update topology via supported mechanisms.
- **`ASK`:** a temporary redirect typically appearing during slot migration; the client must follow the ASK protocol to reach the target node.

```text
Client believes slot S is on Primary A
                 |
                 v
          Send GET key(S)
                 |
                 v
     Primary A returns MOVED/ASK
                 |
                 v
     Cluster-aware driver handles
     redirection per protocol rules
                 |
                 v
        Send to appropriate node
```

Some limitations:

1. The driver can handle redirects automatically, though coverage and retry counts depend on configuration.
2. While topology is changing, a prior owner lookup can immediately become stale.
3. If the redirect limit is exceeded, the application must handle the error rather than assuming Redis executed the command.
4. For commands with side effects, a network timeout leaves the client uncertain of the outcome—unlike a clear `MOVED` before execution.
5. Do not treat a topology change as a signal to wipe all Redis caches/keys.

Verify Lettuce topology refresh and redirect behavior in your actual deployment environment. Reaching one seed node does not guarantee every node advertised in topology is reachable from the application network, especially with containers or NAT.

## 15. Primaries, replicas, and read consistency

Redis Cluster typically pairs primaries with replicas. Redis replication is fundamentally asynchronous, so a replica can lag behind its primary.

```text
Application
      |
      +---- SET key ---> Primary A
      |                       |
      |                 Async replication
      |                       |
      +---- GET key ---> Replica A
                              |
                              v
                       May return stale value
```

If Lettuce is configured to read from replicas, a `GET` right after a `SET` can observe stale data even when both calls execute sequentially in Java.

Distinguish:

- **Reads for reports, dashboards, secondary caches:** sometimes tolerate replica lag.
- **Reads verifying permissions, balances, inventory, or write preconditions:** typically need an authoritative data source or stricter consistency.
- **Write scripts:** must execute on the appropriate primary/slot; do not assume a replica read preference keeps all reads/writes/scripts on the same node.

Whenever enabling a replica-read policy, evaluate:

- Acceptable staleness window.
- Behavior when a replica lags severely or becomes unavailable.
- Whether read-your-writes is required by a given API.
- How failover affects read/write routing and script caches.

Reading from replicas does not make multi-node operations "faster and fully consistent" by default.

## 16. Failover and uncertain execution outcomes

Suppose an application executes a batch of updates across multiple keys:

```text
1. SET product:101 READY (Primary A) -> succeeds
2. INCR metrics:updated (Primary B) -> sent
3. Connection reset before receiving step 2 reply
4. Primary B fails over
```

The application cannot know from the exception alone whether step 2 incremented the counter or not. If it retries the entire batch:

- Step 1 may simply overwrite the same value (absent concurrent writes).
- Step 2 could increment the counter a second time.
- Some data might not appear on the new primary as expected due to replication/failover timing.

Therefore, distinguish **error categories**:

| Error Type | Appropriate Assessment |
|---|---|
| `CROSSSLOT` returned explicitly before execution | Fix key/slot design; do not retry pointlessly |
| Explicit `MOVED`/`ASK` | Driver should handle redirects and topology |
| `NOSCRIPT` | Script not yet cached on queried node; executor should load/retry as supported |
| Timeout/network reset | Unknown whether the command took effect |
| Failure after partial writes | May have left partial state across keys/nodes |
| Replica returned stale data | Possible replication lag, does not mean primary missed the write |
| ACL/permission error | Authorization config bug; retries will not help without changing permissions |

For sensitive writes, use **operation IDs, idempotency, version checks, and reconciliation**. Specifically avoid putting `INCR` or `LPUSH` inside unbounded retry loops without duplicate detection.

## 17. Cross-Cluster transactions must be solved at the architecture layer

Suppose each node holds a slice of data:

```text
Primary A: account:alice:balance
Primary B: account:bob:balance
```

Transferring funds between two accounts requires **debiting A and crediting B** accurately. You cannot issue two commands over one `RedisClusterConnection` and assume all-or-nothing atomicity.

Design paths depend on requirements:

- Move authoritative balance updates into a transactional database.
- Maintain a durable ledger/event log and keep Redis projections read-only.
- If the scope fits within a single aggregate/slot, co-locate keys with a hash tag and use a Lua script or appropriate transaction.
- If multiple nodes must be coordinated, build a workflow with idempotency, transitional states, and saga/compensation reconciliation; do not call it a Cluster-wide Redis transaction.
- For financial data or sensitive state, prioritize business invariants and source-of-truth correctness over round-trip micro-optimizations.

A good key-slot layout reduces cross-slot needs for single-aggregate operations, yet a global hash tag can never substitute for proper consistency architecture.

## 18. Keep node administration operations off the business path

`RedisClusterConnection` and low-level `CLUSTER` commands may expose membership, slot allocation, failover, or topology-mutating capabilities in certain APIs/versions.

**Never let normal HTTP requests administer Redis Cluster** just to satisfy a business action. For example:

- Never trigger slot migrations as a workaround for `CROSSSLOT`.
- Never mark nodes failed or trigger failovers inside an order-processing path.
- Never create/delete slots ad hoc when a `GET` fails.
- Never grant cluster-admin privileges to a service that only reads/writes cache.

Operational actions belong in infrastructure tooling and workflows with proper authorization, monitoring, audit logs, and rollback plans. Business applications typically need permissions only for relevant keys/commands, not topology mutation rights.

### Cluster discovery data is also sensitive

Node lists and internal network addresses expose infrastructure topology. Never return raw `CLUSTER NODES`, credentials, or private infrastructure IPs in public APIs. If exposing a health endpoint, share only high-level status and keep node details inside access-controlled observability tools.

## 19. Testing multi-node operations

A test suite for Redis Cluster should cover **multiple real slots and multiple real primaries**, not just one familiar key.

### 19.1. Testing normal routing

1. Provision a test Cluster with multiple primaries.
2. Point Spring Data Redis to the Cluster's seed nodes.
3. Write/read keys across different slots.
4. Call `clusterGetNodes()` to verify discovery.
5. Call `clusterGetNodeForKey(...)` per key to inspect ownership.
6. Confirm the serializer produces the exact key bytes Redis actually stores.

### 19.2. Testing same-slot vs. cross-slot

```text
cart:{user42}:items
cart:{user42}:total          -> same slot

cart:{user42}:items
cart:{user99}:items          -> usually different slots
```

Test multi-key commands or scripts per contract:

- For same-tag keys: must execute along the slot-compatible path.
- For untagged/cross-slot keys: must cleanly reject or decompose per API contract, without assuming atomic transactions.
- Never rely on display string appearance alone if serializers alter key bytes.

### 19.3. Testing SCAN under concurrent mutations

While scanning across multiple nodes:

- Add some new keys.
- Delete some keys.
- Exercise partial cursor iteration.
- Simulate a connection drop on one node.
- Verify the application tolerates duplicates/partial results and reports errors properly.

An inventory or reconciliation scanner should explicitly document that results are **best effort as of observation**, not a strictly consistent snapshot.

### 19.4. Testing resharding and failover

In a controlled test environment:

- Move a slot to another primary.
- Observe `MOVED`/`ASK` and driver route updates.
- Read/write keys in the migrating slot.
- Inject a connection failure mid-way through a multi-key sequence.
- Trigger a primary failover and measure recovery time.
- Check script cache/`NOSCRIPT` behavior after node changes.
- Verify retry logic does not produce duplicate side effects.

These test your application's resilience against a **dynamic Cluster**, not just `PING`.

## 20. Monitoring per node, per slot, and Cluster-wide

A Redis Cluster can report healthy overall status while one primary is overloaded or its replica is lagging.

Metrics to collect:

| Scope | Metrics to Observe |
|---|---|
| **Cluster-wide** | cluster state, assigned slots, failed nodes, redirects, reshard/failover events |
| **Primary node** | CPU, memory, command latency, connected clients, blocked clients, network I/O |
| **Replica node** | replication lag, link state, catch-up ability |
| **Application** | p50/p95/p99 per command type, timeouts, retries, redirect failures |
| **Data** | Hot key/slot distribution, memory skew, key/value sizes |
| **Multi-node batches** | Success count, failure count, command types, and key ranges needing retry |
| **SCAN/maintenance** | Scan duration, nodes scanned, per-node errors, duplicates, batch sizes |

Redis CLI:

```bash
redis-cli -c -h redis-node-1 -p 6379 CLUSTER INFO
redis-cli -c -h redis-node-1 -p 6379 CLUSTER NODES
redis-cli -c -h redis-node-1 -p 6379 CLUSTER SLOTS

redis-cli -h redis-node-1 -p 6379 INFO stats
redis-cli -h redis-node-1 -p 6379 INFO memory
redis-cli -h redis-node-1 -p 6379 INFO commandstats
redis-cli -h redis-node-1 -p 6379 SLOWLOG GET 10
```

For `INFO`, collect from each relevant node to spot skew. `SLOWLOG` measures server-side Redis command execution time, excluding network and client queueing latency. Never run prolonged `MONITOR` or `KEYS *` on busy production Redis solely to gather metrics.

### Do not confuse "Cluster healthy" with "entire batch succeeded"

A batch can write successfully on primary A and fail on primary B even while `CLUSTER INFO` reports healthy overall state. Health checks measure infrastructure capacity, whereas batch outcomes require **per-operation reconciliation**.

## 21. Rules for handling partial results

When a business operation touches multiple keys across multiple nodes, define an explicit result contract:

```text
Input:
  keys = [key-A, key-B, key-C]

Output:
  key-A -> SUCCESS
  key-B -> FAILED (timeout; outcome unknown)
  key-C -> NOT_ATTEMPTED
```

Do not collapse these three states into a single boolean `false` and indiscriminately retry everything.

A Java model can represent per-key outcomes:

```java
public enum OperationStatus {
    SUCCESS,
    FAILED,
    UNKNOWN,
    NOT_ATTEMPTED
}

public record KeyOperationResult(
        String redisKey,
        OperationStatus status,
        String errorCode) {
}
```

Rules:

- **SUCCESS** when confirmed per the command contract.
- **FAILED** when explicitly rejected with no side effects.
- **UNKNOWN** when a timeout/network failure leaves execution uncertain.
- **NOT_ATTEMPTED** when execution stopped before sending the command for that key.

For `UNKNOWN`, inspect state, operation ID, or version before retrying. For non-idempotent commands with side effects like incrementing quantities, never assume "no reply received" means it is safe to resend.

If business logic mandates all-or-nothing across nodes, a partial-results list aids observability yet **does not make it transactional**. You must adjust the data model or add coordination/reconciliation protocols.

## 22. Common mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Treating `RedisClusterConnection` as a single node | Assuming all commands share one transaction/connection | Understand the cluster-aware abstraction and slot routing |
| Hardcoding `key → node IP` | Breaks on reshard/failover | Let the driver discover/route and refresh topology |
| Scanning `SCAN` on one node and calling it Cluster-wide | Misses keys on other nodes | Iterate across appropriate primaries |
| Scanning both primaries and replicas and summing counts | Double-counts replicated keys | Target primaries and scope deliberately |
| Using `KEYS *` for production inventory | Heavy load; can block nodes | Use rate-limited, batched SCAN |
| Failing to close cluster connections/cursors | Resource leaks | Use `try-with-resources` or release per API |
| Using different key serialization in slot checks | Miscalculates placement | Use exact physical key bytes |
| Calling multi-slot `MGET` expecting atomicity | Cross-slot error or non-atomic split | Group by slot; understand scatter-gather APIs |
| Putting all keys under `{all}` | Hot slot and lost distribution | Tag by appropriate aggregate |
| Using `MULTI`/Lua across multiple primaries | No Cluster-wide transaction | Redesign consistency boundaries |
| Pipelining across nodes and treating it as one commit | Can partially complete | Per-operation idempotency/reconciliation |
| Retrying whole batches after network timeouts | Can duplicate `INCR`/`LPUSH` | Track per-key outcomes and operation IDs |
| Assuming replicas always serve latest data | Stale reads | Read from primary when consistency is needed |
| Skipping MOVED/ASK/failover tests | Routing breaks during resharding | Test dynamic Cluster scenarios and driver config |
| Granting Cluster admin rights to business services | Risk of unintended topology changes | Principle of least privilege |
| Treating node metrics as business ACKs | Misjudges multi-node results | Track per-operation execution outcomes |

## 23. API selection workflow

```text
Need to interact with Redis Cluster?
                |
                v
     Standard single-key read/write only?
           +----+----+
           |         |
          Yes        No
           |         |
           v         v
    Cluster-aware  Need topology,
    RedisTemplate  slots, node/scan?
           |              |
           |              v
           |     RedisClusterConnection
           |              |
           +------+-------+
                  |
                  v
           Multi-key operation?
             +----+----+
             |         |
            No        Yes
             |         |
             v         v
         Route by   Atomicity needed
           slot     across keys?
                         |
                    +----+----+
                    |         |
                   Yes        No
                    |         |
                    v         v
             Keys in same   Per-key commands /
                slot?       controlled scatter-gather
                    |
               +----+----+
               |         |
              Yes        No
               |         |
               v         v
         Suitable    Change data model,
         Lua/MULTI   use transactional source,
                     or compensating workflow
               |         |
               +----+----+
                    |
                    v
         Test reshard/failover,
         timeouts, retry/idempotency
                    |
                    v
         Monitor each node and
         each command outcome
```

## 24. Summary

`RedisClusterConnection` enables Spring Data Redis to work with Redis Cluster-specific concerns: **node discovery, key placement lookup, topology inspection, per-node scanning, and slot-routed commands**. It is an essential tool for building operational utilities, inventories, diagnostics, or batch jobs across data distributed over multiple primaries.

Maintain clear boundaries:

1. **A cluster-aware connection is not a Cluster-wide transaction.** Commands targeting different primaries can succeed or fail independently.
2. **Slots are the unit of routing.** Multi-key commands, Lua scripts, and Redis transactions must obey slot constraints; hash tags group keys within an aggregate.
3. **Topology changes over time.** Resharding, `MOVED`/`ASK`, and failovers mean an owner lookup at one instant is not permanent truth.
4. **Multi-node scans do not produce atomic snapshots.** `SCAN` requires per-node cursors, rate limits, duplicate tolerance, and handling for node changes.
5. **Systems must tolerate uncertain outcomes.** Timeouts, disconnects, and retries on commands with side effects require idempotency, versioning, or reconciliation.
6. **Monitor both the whole Cluster and individual nodes.** Overloaded primaries, lagging replicas, or hot slots cannot be detected by a single `PING`.

For business paths needing only key-based `GET`/`SET`, prefer a cluster-aware `RedisTemplate` to leverage serializers and lifecycle management. When node/slot-level operations are genuinely required, use `RedisClusterConnection` while treating multi-node work as **a distributed problem with consistency limits and partial failures**, never as a single atomic Redis command chain across the entire Cluster.
