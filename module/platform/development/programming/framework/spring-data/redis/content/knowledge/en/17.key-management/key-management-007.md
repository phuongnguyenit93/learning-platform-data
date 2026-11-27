# Distinguishing Single-Node Operations from Cluster-Wide Operations in Redis Cluster

In Spring Data Redis, the same command name such as `KEYS`, `SCAN`, or `FLUSHDB` can mean very different things depending on whether **the command is sent to one Redis server** or **Spring Data Redis actively coordinates multiple servers**. Misunderstanding execution scope easily leads to two opposite issues: missing keys even though data exists, or accidentally scanning/deleting data on a larger scale than intended.

This lesson focuses on **key management** in Redis Cluster: identifying where keys live, recognizing operations that affect only a single node, executing operations that must cover the entire cluster, and choosing the right APIs in Spring Data Redis.

## 1. How Does Redis Cluster Partition Data?

Redis Cluster divides the keyspace into **16,384 hash slots** (from `0` to `16383`). Each key maps to a slot; each **primary node** (also called *master*) is responsible for a subset of slots. Replicas copy primary data for high availability; they are not independent data partitions to add onto statistical totals.

Example three-primary topology:

```text
                    Spring Data Redis Application
                               |
                      Cluster-aware client
                               |
              +----------------+----------------+
              |                |                |
        Primary A         Primary B         Primary C
        slots 0–5460      slots 5461–10922   slots 10923–16383
          /                    |                    \
     Replica A             Replica B             Replica C

  key1 → slot 3200  → A
  key2 → slot 8000  → B
  key3 → slot 14000 → C
```

The slots and key names in the diagram are illustrative. In a real cluster, the slot is calculated from the key name and looked up in the current slot map to determine the owning node. During failover or resharding, the node owning a slot can change.

It is essential to distinguish three concepts:

1. **Single-key operation**: for example `GET key`, `TTL key`, `EXPIRE key 60`, `DEL key`. Knowing the key name, the client computes the slot and routes to the right primary. Regardless of which seed address it uses, the data scope remains that key.
2. **Single-node operation**: for example executing `SCAN`, `KEYS`, or `DBSIZE` directly on Primary A. The command observes only the keys A currently serves; it does not automatically reach B and C.
3. **Cluster-wide operation**: the application/client sequentially or concurrently talks to the necessary primaries and aggregates results. This is a **client-side coordination mechanism**, not inherently an atomic Redis command applied across every node.

> **Note:** "Connected to a cluster" does not mean "every command runs across the whole cluster." You must check whether a given API routes by key, targets a single node, or *fans out* to multiple primaries.

## 2. Scope Comparison Table for Key Management Commands

| Operation | When Run on One Redis Node | When Targeting the Whole Redis Cluster | Key Takeaway |
|---|---|---|---|
| `GET`, `SET`, `TTL`, `EXPIRE`, `DEL` on **one key** | Cluster-aware client routes by the key's slot | No need to scan every node; the key still has one owning primary | Do not confuse "one key" with "any arbitrary node" |
| `KEYS pattern` | Returns only matching keys on the receiving node | Sends to each primary and merges result sets | `KEYS` scans the keyspace in a potentially blocking way, very risky on large data |
| `SCAN cursor MATCH pattern` | Incrementally traverses **that node's** keyspace | Scans each primary separately, each node has its own cursor | `SCAN` does not provide a cluster-wide snapshot; may return duplicate keys |
| `DBSIZE` | Counts keys on the receiving node | Collects counts from all primaries and sums them | Result captures different instants, not strictly atomic/consistent |
| `RANDOMKEY` | Picks a random key from the current node | Needs a selection/sampling mechanism across primaries | Picking a random node then a key can skew the sample |
| `FLUSHDB`, `FLUSHALL` | Deletes keyspace on the receiving node | Executed intentionally across all primaries | Destructive operation; calling on one node does **not** mean the whole cluster is wiped |
| `MGET`, `MSET`, `RENAME` and multi-key commands | Redis Cluster enforces hash-slot constraints for many atomic commands | Some Spring Data Redis APIs may split commands to support multiple slots; not every command does | Do not assume multi-slot operations are accepted or remain atomic |

In standard Redis Cluster, only logical database `0` is used; data is not partitioned using `SELECT 1`, `SELECT 2`, etc. as in standalone Redis.

## 3. Single-Key Operations: The Driver Finds the Owning Node

With `StringRedisTemplate` configured for Redis Cluster, developers normally do not need to know which primary holds a key when operating on a single key:

```java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;

public class SessionKeyService {
    private final StringRedisTemplate redis;

    public SessionKeyService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void demo() {
        String key = "session:{user42}:token";

        redis.opsForValue().set(key, "abc123", Duration.ofMinutes(15));
        String value = redis.opsForValue().get(key);
        Long ttlSeconds = redis.getExpire(key);
        Boolean removed = redis.delete(key);

        // Each command above targets the same logical key.
        // The cluster-aware driver routes requests to the key's slot.
    }
}
```

In `session:{user42}:token`, the `{user42}` part is a **hash tag**. Keys sharing the same valid hash tag, such as `session:{user42}:profile`, hash to the same slot. This is useful when the application needs multi-key operations requiring the same slot; it does not mean those keys stay on the same physical machine forever if the cluster redistributes slots.

For a single key, differences in the initial contact node are handled by the driver via slot metadata or `MOVED`/`ASK` redirections. However, `KEYS` and `SCAN` lack a single target key for slot-based routing, so you must pay attention to node scope or how the API aggregates results.

## 4. `KEYS`: Single-Node Results vs. Cluster-Merged Results

### 4.1. Redis `KEYS` Is Node-Local

Suppose a cluster has three primaries holding:

```text
Primary A: session:1001, cart:1001
Primary B: session:1002
Primary C: session:1003, product:10
```

If you send `KEYS session:*` **directly to A**, the result contains only `session:1001`. That does not prove `session:1002` and `session:1003` do not exist. Even `redis-cli -c` (which follows slot redirects) does not turn `KEYS` into a cluster-wide key query.

### 4.2. Spring Data Redis Provides Two Explicit Scopes

`RedisClusterConnection` distinguishes:

```java
import java.nio.charset.StandardCharsets;
import java.util.Set;
import org.springframework.data.redis.connection.RedisClusterConnection;
import org.springframework.data.redis.connection.RedisClusterNode;
import org.springframework.data.redis.connection.RedisConnectionFactory;

public class ClusterKeysExample {
    public static void run(RedisConnectionFactory factory,
                           RedisClusterNode selectedNode) {
        byte[] pattern = "session:*".getBytes(StandardCharsets.UTF_8);

        try (RedisClusterConnection connection = factory.getClusterConnection()) {
            // Queries only the specified node.
            Set<byte[]> oneNodeKeys = connection.keys(selectedNode, pattern);

            // Spring Data Redis sends KEYS to cluster primaries
            // and merges the returned results.
            Set<byte[]> clusterKeys = connection.keys(pattern);
        }
    }
}
```

This is an intentional distinction in Spring Data Redis: `keys(node, pattern)` queries only the specified node, whereas `keys(pattern)` on `RedisClusterConnection` gathers keys across primaries. When you only need to inspect one node, the higher-level `redisTemplate.opsForCluster().keys(node, pattern)` also expresses that scope via `RedisClusterNode`.

`RedisTemplate.keys(pattern)` normally delegates to `keys` on the underlying connection; on a Redis Cluster connection, result collection may span multiple primaries. Therefore, **do not equate "a single Java method call" with "a single command on one node."** Check the connection type, driver, and library version in use.

**Why avoid `KEYS` on production request paths?** Every `KEYS` command scans the keyspace on the receiving server. When fanned out to multiple primaries, the application can place load across the entire cluster and must buffer large key sets in memory to merge results. `KEYS` is suitable only for small test environments or tightly controlled operational tasks; for large datasets, prefer `SCAN`.

## 5. `SCAN`: Scanning One Node, Then Expanding to the Whole Cluster

`SCAN` is cursor-based. Each call returns a batch of keys and the next cursor; repeat until the cursor returns to `0`. Unlike `KEYS`, the application can process results incrementally, reducing how long each call occupies the server.

However, **one cursor represents only one node's keyspace**. To inspect the entire cluster, iterate through each primary and keep a separate cursor per node. There is no single "cluster-wide SCAN cursor" in the standard Redis protocol.

### 5.1. Scanning All Primaries with Spring Data Redis

The following code uses `RedisClusterConnection.scan(node, options)` to make each scan's scope explicit. The example assumes key names are stored with a UTF-8 serializer such as `StringRedisSerializer`.

```java
import java.nio.charset.StandardCharsets;
import java.util.function.Consumer;
import org.springframework.data.redis.connection.RedisClusterConnection;
import org.springframework.data.redis.connection.RedisClusterNode;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.Cursor;
import org.springframework.data.redis.core.ScanOptions;

public class ClusterKeyScanner {
    private final RedisConnectionFactory factory;

    public ClusterKeyScanner(RedisConnectionFactory factory) {
        this.factory = factory;
    }

    public void forEachSessionKey(Consumer<String> consumeKey) {
        ScanOptions options = ScanOptions.scanOptions()
                .match("session:*")
                .count(500)  // Hint for batch size, not a hard LIMIT.
                .build();

        try (RedisClusterConnection connection = factory.getClusterConnection()) {
            for (RedisClusterNode node : connection.clusterGetNodes()) {
                if (!node.isMaster()) {
                    continue; // Avoid double-counting copies from replicas.
                }

                try (Cursor<byte[]> cursor = connection.scan(node, options)) {
                    while (cursor.hasNext()) {
                        String key = new String(
                                cursor.next(), StandardCharsets.UTF_8);
                        consumeKey.accept(key);
                    }
                }
            }
        }
    }
}
```

Example call:

```java
ClusterKeyScanner scanner = new ClusterKeyScanner(connectionFactory);
scanner.forEachSessionKey(key -> System.out.println("Found: " + key));
```

Step-by-step meaning:

1. Fetch the node list from cluster topology.
2. Select only `isMaster()` nodes so replica data is not repeated.
3. Open a **separate** `SCAN` cursor for each primary and stream keys; close the cursor after use.
4. Finish after scanning the primaries discovered at the start.

This is a key-scanning example, not a full production-grade scanner. For recurring jobs on large datasets, rate-limit, track scanned node counts, handle per-node failures, consider retries/checkpoints, and handle topology changes mid-scan. Never silently report "completed" if a primary failed or was unreachable.

### 5.2. `SCAN` Does Not Produce a Consistent Snapshot

Understand these properties accurately:

- `COUNT 500` is a **hint** to Redis; a round may return fewer, more, or even zero matching keys while the cursor has not yet finished.
- A key may appear multiple times in a pass. If processing requires uniqueness, use deduplication or idempotent operations.
- Keys added or deleted mid-scan can cause results to differ between rounds. During resharding, a key may move nodes, causing misses or reprocessing if scanning only a fixed topology.
- A `MATCH` pattern filters matching keys but does not prevent scanning large portions of the keyspace. `SCAN` reduces per-call blocking; total scan cost remains significant.
- The application layer must close cursors/connections and avoid collecting all keys into a huge `List`/`Set` when incremental processing works.

If you need exact point-in-time figures, `SCAN` is not a cross-cluster snapshot transaction. Dedicated accounting/reconciliation designs or pausing writes and verifying topology may be needed depending on business rules.

## 6. `DBSIZE`, `FLUSHDB`, and Administrative Commands: Scopes Are Easy to Confuse

Not every administrative command has cluster-wide semantics when connected through a cluster-aware client.

### `DBSIZE` on One Node

```bash
# This command is sent directly to the node at 127.0.0.1:7000.
redis-cli -h 127.0.0.1 -p 7000 DBSIZE
```

The returned value is the number of keys served by that node, not automatically the total across other primaries. To estimate the cluster total, collect counts from **each primary** and sum them. Because primaries are not measured simultaneously, the sum is not atomically consistent; failover, resharding, and concurrent writes/deletes during measurement all affect the result.

### `FLUSHDB`/`FLUSHALL`: Always Verify Scope Before Using

In Redis Cluster, a `FLUSHDB` command sent directly to one primary deletes only that node's data; it is not a "wipe all shards" operation just because the node belongs to a cluster. Redis Cluster has only DB `0`, so `FLUSHDB` and `FLUSHALL` have equivalent effect on a node regarding DB scope. Wiping an entire cluster requires targeting each primary individually, or an administrative API with an explicit fan-out contract.

Spring Data Redis provides node-scoped administrative APIs, for example:

```java
// Example API signature: redisTemplate.opsForCluster().flushDb(node);
// Here node is a specific RedisClusterNode, not all primaries.
```

Never put whole-keyspace deletion commands inside user request handling logic. Deleting by business prefix should also use controlled scanning and deletion rather than turning a `session:*` pattern into `FLUSHDB` (which deletes **every** key on the node without prefix filtering).

## 7. Pattern-Based Deletion Across the Cluster: Proper Scope Workflow

Suppose a business requirement calls for removing `session:*` keys across a Redis Cluster. A controlled approach:

```text
Fetch cluster topology
         |
         v
Select list of primaries
         |
         v
SCAN MATCH session:* on primary A → process found keys
         |
         v
SCAN MATCH session:* on primary B → process found keys
         |
         v
SCAN MATCH session:* on primary C → process found keys
         |
         v
Aggregate stats, errors, scan timestamps, and processed nodes
```

For each key, the application can call `StringRedisTemplate.unlink(key)` to request Redis's asynchronous background memory freeing, or `delete(key)` if there is a reason to use `DEL`. These are **key-specific operations**: the driver routes by slot automatically, even if the key moved nodes since `SCAN` returned it. Example operation after clearly scoping and bounding the key list:

```java
// Call only after the workflow has properly scoped keys and controlled load.
for (String key : keysSelectedForDeletion) {
    redisTemplate.unlink(key);  // Per-key UNLINK, routed by slot.
}
```

This snippet illustrates deleting a single key via a routing-aware API; it is **not** a complete cluster-wide auto-deletion implementation. In production systems, replace `keysSelectedForDeletion` with a rate-limited/chunked stream, consider dry-run mode, log/emit metrics, enforce time bounds, and add stop conditions. Never load millions of keys into memory before starting deletion.

`UNLINK` only frees value memory in the background after removing the key from the keyspace; sending too many commands can still create I/O/CPU load on the cluster. If using a **multi-key** delete API in a single call, verify how it handles *cross-slot* rules; never assume a multi-slot Redis command is valid.

## 8. Scenarios That Easily Lead to Wrong Conclusions

### Scenario A: "Connected to node A, `GET` finds the key, but `SCAN` on A does not see it"

There is no contradiction. `GET key` is routed by the driver to the primary owning the key's slot; `SCAN` sent directly to A sees only keys currently on A. Check the key's slot and current owner before concluding data was lost.

### Scenario B: "`KEYS` in Spring returns more keys than `redis-cli KEYS`"

`RedisClusterConnection.keys(pattern)` can invoke `KEYS` on all primaries and return the merged result. `redis-cli` sending `KEYS` to a single node returns only that node's scope. Both behaviors can be working as designed, yet their cost and meaning are completely different.

### Scenario C: "`SCAN` reached cursor `0` yet many keys are still missing"

Cursor `0` only confirms completion of the pass on **that respective node**. Verify whether every primary was scanned, whether mid-run errors occurred, whether the `MATCH` filter is right, and whether the cluster recently migrated slots. If you need a consistent snapshot, `SCAN` itself cannot provide one.

### Scenario D: "Summing `DBSIZE` of both primaries and replicas doubles the key count"

Replicas hold copies of primary data. To estimate total logical keys, sum only across primaries; having more replicas does not increase the cluster's logical key count.

### Scenario E: "`MGET` on two keys in different slots works, so `RENAME` will work too"

This is a false assumption. Spring Data Redis can split certain multi-key commands into per-slot operations and combine the results (such as `MGET` on some execution paths). Commands requiring atomic or server-side execution across multiple keys can fail with `CROSSSLOT`. Check the specific API/command; if using multi-key transactions/scripts, design hash tags so related keys share a slot.

## 9. Inspecting a Cluster with `redis-cli` While Learning and Debugging

The commands below are for **observation** only in a practice cluster. Replace host/port with a running node's address:

```bash
# View nodes, roles, and slot ranges advertised in the topology.
redis-cli -h 127.0.0.1 -p 7000 CLUSTER NODES

# Compute the slot for a specific key.
redis-cli -h 127.0.0.1 -p 7000 CLUSTER KEYSLOT 'session:{user42}:token'

# Check key count on a single node (does not sum across the cluster).
redis-cli -h 127.0.0.1 -p 7000 DBSIZE

# Scan one node; repeat with the returned cursor until cursor is 0.
redis-cli -h 127.0.0.1 -p 7000 SCAN 0 MATCH 'session:*' COUNT 100

# Read a key: -c allows redis-cli to follow slot redirects.
redis-cli -c -h 127.0.0.1 -p 7000 GET 'session:{user42}:token'
```

When `SCAN` returns a non-zero cursor, issue the next `SCAN <new-cursor> ...` **on that exact same node**. For a cluster-wide view, locate the primaries from topology and run separate loops on each primary. Do not run `KEYS *` to inspect an entire production cluster; and do not treat `CLUSTER NODES` as proof that keys were queried on every node: that command returns only **topology metadata**.

## 10. Choosing a Strategy by Goal

| Goal | Suitable Strategy | What Not to Assume |
|---|---|---|
| Read/delete/set TTL on a known key | `StringRedisTemplate`/`RedisTemplate` with the specific key | That you must manually find the node and connect directly |
| Inspect keys on one primary for debugging | `scan(node, options)` or `keys(node, pattern)` on small data | That results represent the whole cluster |
| Find keys by prefix across the whole cluster | `SCAN` each primary, stream-process, track per-node outcomes | That there is one cluster-wide cursor or consistent snapshot |
| Quickly list all keys in a small lab cluster | `RedisClusterConnection.keys(pattern)` once cost is understood | That this is safe for large production clusters |
| Count keys | Collect `DBSIZE` from each primary, noting point-in-time drift | Summing replicas too; that the total is a transactional snapshot |
| Delete keys by business prefix | Scan per node then delete **per key** with routed commands, rate-limited | That `FLUSHDB` supports a pattern filter |
| Use multi-key operations | Check slot constraints of the command; consider `{hashTag}` | That Spring automatically splits or keeps every multi-key command atomic |

## 11. Takeaways When Designing Key Management Features

- **A single known key**: let the cluster-aware driver route by hash slot.
- **A specific node**: use APIs accepting `RedisClusterNode` or connect directly to that node; `SCAN`/`KEYS`/`DBSIZE` reflect only that node's scope.
- **The entire cluster**: explicitly verify which APIs fan out and which require iterating over primaries and aggregating results yourself.
- **Replicas**: are copies of primaries, not additional data shards to add to totals.
- **Operational safety**: use `SCAN` for large traversals, close cursors, avoid buffering all results, rate-limit, handle per-node errors, and account for resharding/failover.

The key takeaway in Spring Data Redis is that **operation scope is determined by the method and connection type**. Two calls both containing the word "keys" can query a single primary in one case and broadcast to all primaries in the other; understanding that prevents both missing keys and causing unexpected load on Redis Cluster.

## References

- [Spring Data Redis — Redis Cluster](https://docs.spring.io/spring-data/redis/reference/redis/cluster.html): slot routing, difference between `keys(pattern)` and `keys(node, pattern)`, multi-key handling.
- [Spring Data Redis — RedisClusterConnection API](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/connection/RedisClusterConnection.html): `keys`, `scan`, and node-targeted operations.
- [Spring Data Redis — ClusterOperations API](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/core/ClusterOperations.html): administrative operations taking a node parameter.
- [Redis — Scale with Redis Cluster](https://redis.io/docs/latest/operate/oss_and_stack/management/scaling/): hash slots, primaries, replicas, slot rebalancing, and multi-key operation limits.
- [Redis — SCAN](https://redis.io/docs/latest/commands/scan/): cursors, `MATCH`, `COUNT`, consistency limitations on results.
- [Redis — FLUSHDB](https://redis.io/docs/latest/commands/flushdb/): scope and impact of data deletion commands.
