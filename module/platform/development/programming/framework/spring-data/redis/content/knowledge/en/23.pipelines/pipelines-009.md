# Pipelining Capabilities on Redis Cluster and Driver Differences in Spring Data Redis

**Pipelining** is a technique for sending multiple Redis commands consecutively without waiting for each command's response, then receiving results in a batch. In Redis Standalone, a connection typically goes to one server, making the command flow relatively easy to picture. However, **Redis Cluster distributes keys by hash slot**: commands inside the same pipeline may need to go to different master nodes. Therefore, the question "Does Spring Data Redis support pipelining on Cluster?" must be answered at three layers:

1. **Redis server:** each node still understands the pipeline protocol over a TCP connection; Cluster enforces slot routing rules and restrictions on multi-key commands.
2. **Java driver (Lettuce or Jedis):** determines whether commands can be batched, split across nodes, managed across multiple connections, redirected on `MOVED`/`ASK`, and reassembled into results.
3. **Spring Data Redis:** `RedisTemplate.executePipelined(...)` uses the driver's `RedisConnection` adapter and has its own limitations, which are not identical to every feature of the native API.

**Do not infer that "the driver supports Redis Cluster" means "every Spring Data Redis pipeline method is supported on Cluster."** Spring Data Redis documentation across the 3.5/4.1 branches notes that pipelining is limited to Redis Standalone, while also describing Lettuce-based Redis Cluster support and exceptions for certain cross-slot commands. Verify **your exact Spring Data Redis version + connector + specific operation** before using `executePipelined` on Cluster. When cross-node batching is required and the Spring API does not provide it, you can use the driver's cluster-aware native API in a controlled way.

## 1. How does a pipeline reduce round trips?

Without pipelining:

```text
Application    Redis
   | SET k1 v1   |
   |----------->  |
   | <------ OK   |
   | SET k2 v2   |
   |----------->  |
   | <------ OK   |
   | SET k3 v3   |
   |----------->  |
   | <------ OK   |
```

The application must wait for each response before sending the next command. If network round-trip time (RTT) is 2 ms, 500 sequential commands can spend substantial time merely waiting on the network, before counting processing overhead.

With pipelining:

```text
Application    Redis
   | SET k1 v1   |
   | SET k2 v2   |
   | SET k3 v3   |
   |----------->  |  Receive/process commands
   | <------ OK   |
   | <------ OK   |
   | <------ OK   |
```

This is a **logical** representation of reducing response waits; the driver may flush data over one or more socket writes. Pipelining does not mean Redis executes all commands in a single CPU instruction or an atomic transaction.

### Pipelines differ from batch commands and transactions

| Concept | Mechanism | Primary guarantee |
|---|---|---|
| Multiple normal commands | Send one command, wait for one response | Simple, yet incurs many network wait rounds |
| **Pipeline** | Send multiple commands consecutively, receive responses afterward | Reduces round-trip cost; **does not create a transaction** |
| Multi-key command, e.g., `MSET k1 v1 k2 v2` | One Redis command containing multiple keys | Follows the hash-slot rules of **a single command** |
| `MULTI`/`EXEC` | Queue and execute commands consecutively without other clients interleaving | Command group is not interleaved; no SQL-style rollback |
| Lua / Redis Function | Execute logic inside Redis | Atomic execution unit per script/function semantics; has other constraints |

A pipeline of 100 `SET` commands is still **100 separate commands**. Some commands can succeed while others fail. Losing the connection while sending/receiving responses can leave an uncertain state regarding which commands ran; design safe retries.

Redis also has to buffer results until the client reads them. Therefore, do not pack an unbounded number of commands into one pipeline: split into **bounded batches**, and measure memory, latency, and throughput.

## 2. Why is Redis Cluster more complex than Standalone?

Redis Cluster partitions the keyspace into **16,384 hash slots**. For a normal key, the slot is computed as:

```text
slot = CRC16(key) mod 16384
```

Each master node owns a set of slots. Hypothetical example:

```text
Redis Cluster

Master A          Master B          Master C
slots 0..5000     slots 5001..10000 slots 10001..16383
    |                  |                   |
    +-- item:1         +-- item:2          +-- item:3
```

The example above only illustrates distribution; actual slots for `item:1`, `item:2`, and `item:3` must be computed with `CLUSTER KEYSLOT`, not guessed from key names as drawn.

A cluster-aware client must know which slot a key belongs to and which node owns that slot. When keys in a batch span multiple masters, the client must be able to:

- Compute the corresponding slot from the **serialized key bytes**.
- Pick the connection to the right node for each command.
- Send commands in batches across the involved connections/nodes.
- Receive results and reassemble them according to the API's contract.
- Handle topology changes, `MOVED` or `ASK` redirects, and partial errors.

That is the responsibility of a **cluster-aware client**, not an automatic property of the pipeline protocol on a single TCP socket.

### 2.1. Two distinct cross-slot issues

Distinguish between:

**Case A — multiple single-key commands, each operating on one key:**

```redis
SET user:100:name "An"
SET user:200:name "Binh"
GET user:100:name
```

The keys may belong to different slots. **In principle**, a cluster-aware client can route each command to its responsible node and optimize batch sending. Single-key commands do not inherently trigger `CROSSSLOT` errors just by appearing in the same client-side batch. However, a specific pipeline API may not support cross-node batching.

**Case B — a single command itself containing multiple keys:**

```redis
MGET user:100:name user:200:name
```

Redis Cluster typically requires all keys in **the same multi-key command** to belong to **the same hash slot**. Otherwise, the server may return:

```text
CROSSSLOT Keys in request don't hash to the same slot
```

Splitting an invalid `MGET` into two independent `GET` commands can avoid the multi-key constraint, **if** the driver can route individual commands. That changes semantics and command count, rather than pipelining somehow making a cross-slot `MGET` valid.

### 2.2. Hash tags force related keys into the same slot

If part of a key is enclosed in a valid brace pair `{...}`, Redis computes the slot from the substring inside. Example:

```redis
CLUSTER KEYSLOT order:{913}:state
CLUSTER KEYSLOT order:{913}:audit
CLUSTER KEYSLOT order:{913}:items
```

All three commands return **the same slot number** because they share the `{913}` hash tag.

Consequently, a multi-key command becomes valid:

```redis
MGET order:{913}:state order:{913}:audit
```

However:

```redis
MGET order:{913}:state order:{914}:state
```

usually fails with `CROSSSLOT`, because two different hash tags produce two different slots (barring rare hash collisions, which should never be relied upon).

Hash tags help design key groups that need same-slot operations; **do not place every key in the system under the same hash tag**, as that concentrates load onto a single master and defeats sharding.

## 3. How do MOVED and ASK affect pipelines?

Redis Cluster topology can change when:

- Rebalancing/resharding moves slots between masters.
- Failover replaces the master owning a slot.
- A newly started client has a stale cached slot map.
- Network or connectivity to a node is interrupted.

If a client sends a command to a node that no longer owns the slot, Redis may return:

```text
MOVED 12182 redis-node-b:6379
```

`MOVED` indicates the slot is now served by another node; the client should update its slot map and resend the command accordingly.

During slot migration, Redis may return `ASK`. This is a temporary redirect: the client must send `ASKING` to the target node before the redirected command, without permanently updating its slot map as with `MOVED`.

Without pipelining, the driver handles redirects and per-command errors relatively directly. When many commands have already been dispatched before waiting for results:

```text
Application
   |
   +-- GET keyA --> Master A --> OK
   |
   +-- GET keyB --> Master B --> MOVED to C
   |                             |
   |                             +--> retry keyB on C
   |
   +-- SET keyC --> Master C --> may succeed or time out
```

Results arriving from multiple connections may complete at different times. The driver must handle responses, redirects, and futures appropriately. **There is no global completion order across nodes** that you can rely on as a business guarantee. Some drivers support redirection during normal execution yet have specific limitations when pipelining/cross-node batching.

If a write command took effect while its response was lost during a network glitch, uncontrolled retries can duplicate side effects. For `INCR`, `LPUSH`, or inventory decrements, design for **idempotency** and reconciliation rather than treating timeouts as guaranteed non-writes.

## 4. Three layers of support: Redis, driver, and Spring Data Redis

| Layer | General capability | What to verify |
|---|---|---|
| Redis server Standalone | Supports pipelining over a single connection | Batch size, per-command execution time |
| Redis Cluster | Each node still supports pipelining; multi-key commands are slot-restricted | Slot distribution, MOVED/ASK, cross-slot, failover |
| Lettuce native | Cluster-aware routing; asynchronous API can dispatch multiple commands before awaiting replies | Connections/nodes, response futures, flush policy, timeouts, retries |
| Jedis native | Pipeline via version-specific API; newer versions offer `ClusterPipeline` | Actual Jedis version, supported single-node/cross-node command sets |
| Spring Data Redis | `RedisTemplate.executePipelined` uses the `RedisConnection` adapter | **Cluster pipeline scope supported by Spring Data Redis and connector**, not inferred from native APIs |

The official Spring Data Redis Pipelining documentation (3.5/4.1 branches) explicitly notes a limitation: **"Pipelining is limited to Redis Standalone."** The same page also describes Cluster support primarily via Lettuce, alongside cases of unsupported cross-slot commands. Read this as an **integration scope warning**, rather than concluding every `executePipelined` call on Cluster works simply because Lettuce supports Cluster.

A system can end up in this situation:

```text
Lettuce native cluster async:
    supports dispatching multiple commands to multiple nodes
             |
             | DO NOT infer
             v
RedisTemplate.executePipelined on Cluster:
    guaranteed to work for every command, every version
```

Because capabilities vary by version, check the exact Spring Data Redis version in use (for example via the Spring Boot BOM), **not** only the feature table of the latest documentation release.

## 5. Lettuce: async model, Cluster routing, and flushing

**Lettuce** is built on Netty and provides synchronous, asynchronous, and reactive APIs. In cluster mode, `RedisClusterClient` maintains a slot map and uses connections to the appropriate nodes. The async API allows issuing multiple commands consecutively, each returning a `RedisFuture<T>`; the application can await results after all commands have been dispatched.

Lettuce handles `MOVED`/`ASK` redirects and supports periodic or event-driven topology refreshes. This enables batching across keys in different slots **at the native client level**, though it does not turn the batch into a cross-node transaction.

### 5.1. Lettuce native async example on Cluster

This snippet assumes an accessible Cluster seed node at `127.0.0.1:7000` and a compatible Lettuce dependency. It uses the native API to illustrate driver capabilities, **not** `RedisTemplate.executePipelined` code.

```java
import io.lettuce.core.LettuceFutures;
import io.lettuce.core.RedisFuture;
import io.lettuce.core.RedisURI;
import io.lettuce.core.cluster.RedisClusterClient;
import io.lettuce.core.cluster.api.StatefulRedisClusterConnection;
import io.lettuce.core.cluster.api.async.RedisAdvancedClusterAsyncCommands;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutionException;

public final class LettuceClusterBatchExample {

    public static void main(String[] args) throws Exception {
        RedisClusterClient client = RedisClusterClient.create(
                RedisURI.create("redis://127.0.0.1:7000"));

        try {
            try (StatefulRedisClusterConnection<String, String> connection =
                         client.connect()) {

                RedisAdvancedClusterAsyncCommands<String, String> async =
                        connection.async();

                List<RedisFuture<String>> pending = new ArrayList<>();

                // Each SET has only one key. Keys can reside in different slots.
                for (int i = 0; i < 100; i++) {
                    pending.add(async.set("demo:customer:" + i, "READY"));
                }

                boolean finished = LettuceFutures.awaitAll(
                        Duration.ofSeconds(10),
                        pending.toArray(new RedisFuture[0]));

                if (!finished) {
                    throw new IllegalStateException(
                            "Timeout while waiting for Redis Cluster batch");
                }

                for (RedisFuture<String> result : pending) {
                    // Each future can succeed or complete exceptionally.
                    String status = result.get();
                    if (!"OK".equals(status)) {
                        throw new IllegalStateException(
                                "Unexpected SET reply: " + status);
                    }
                }
            }
        } finally {
            client.shutdown();
        }
    }
}
```

Key details in the example:

1. `RedisClusterClient` computes slots and chooses the right node for each `SET`.
2. The loop **does not call `get()` after every `set()`**; commands are dispatched before waiting for results.
3. `awaitAll` only waits for futures to complete within the timeout; **completing** can still mean completing with failure. Check each `result.get()`.
4. Future results belong to individual commands; do not assume node A always finishes before node B.
5. These are independent write commands; if one future fails, other keys may already have been updated.

In a Spring Boot application, do not spin up countless `RedisClusterClient` instances per request. Clients/drivers should have a managed lifecycle, be reused via configured beans, limit in-flight commands, and close resources on shutdown.

### 5.2. Lettuce flush policy

Spring Data Redis provides an API to configure Lettuce pipeline flushing on `LettuceConnectionFactory`:

```java
import org.springframework.data.redis.connection.lettuce.LettuceConnection;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;

// Conceptual configuration example on an application-owned factory.
LettuceConnectionFactory factory = /* application-configured bean */;
factory.setPipeliningFlushPolicy(
        LettuceConnection.PipeliningFlushPolicy.buffered(50));
```

`buffered(50)` flushes after every 50 commands in a pipeline according to the support provided by your Spring Data Redis/Lettuce version. This option **controls flush timing**; it does not unlock commands rejected by Cluster for being cross-slot or make `executePipelined` support a Cluster configuration that the adapter does not support.

At the native Lettuce level, you can use `setAutoFlushCommands(false)`, dispatch multiple async commands, call `flushCommands()`, and re-enable auto-flush. However, auto-flush is a **connection-level** state; if the same native connection serves multiple threads, toggling it can affect other threads' commands. Only control flushing that way when you own a dedicated connection and manage its lifecycle.

In most applications, the main benefit of pipelining comes from not awaiting each future; do not tune flush policies without measurements proving a benefit.

## 6. Jedis: synchronous-style pipelines and differences between native and Spring

**Jedis** provides a pipeline API for Redis operations. In Standalone mode, Jedis typically creates a pipeline object, queues commands, and calls `sync()` to send/receive results. Each command returns a `Response<T>`, which should only be read after the pipeline has synced.

Conceptual example with the native Jedis API:

```java
import redis.clients.jedis.Jedis;
import redis.clients.jedis.Pipeline;
import redis.clients.jedis.Response;

try (Jedis jedis = new Jedis("127.0.0.1", 6379)) {
    try (Pipeline pipeline = jedis.pipelined()) {
        Response<String> first = pipeline.set("demo:j:1", "A");
        Response<String> second = pipeline.set("demo:j:2", "B");

        pipeline.sync();

        System.out.println(first.get());
        System.out.println(second.get());
    }
}
```

The pattern above is for **Standalone**. Do not grab a connection to an arbitrary Redis Cluster node and pipeline keys belonging to all nodes, because a node that does not own a slot returns `MOVED` and the driver must re-route.

### 6.1. Jedis Cluster pipeline is not uniform across all versions

Modern Jedis releases include a `ClusterPipeline` mechanism on the cluster-aware client, allowing single-key commands to be split by node. However, **the `JedisCluster.pipelined()`/`ClusterPipeline` API depends on the native Jedis version**, and its presence does not guarantee that Spring Data Redis's `JedisConnection` adapter exposes an equivalent pipeline on Cluster.

In Jedis versions that provide this API, usage looks like:

```java
import redis.clients.jedis.HostAndPort;
import redis.clients.jedis.JedisCluster;
import redis.clients.jedis.ClusterPipeline;
import redis.clients.jedis.Response;

// Only applies to Jedis versions that provide JedisCluster.pipelined().
try (JedisCluster cluster = new JedisCluster(
        new HostAndPort("127.0.0.1", 7000))) {

    try (ClusterPipeline pipeline = cluster.pipelined()) {
        Response<String> a = pipeline.set("demo:{42}:a", "A");
        Response<String> b = pipeline.set("demo:{43}:b", "B");

        pipeline.sync();

        System.out.println(a.get());
        System.out.println(b.get());
    }
}
```

Modern Jedis `ClusterPipeline` restricts operations to **commands that can target a single node**. Commands that must run across multiple shards or all nodes, as well as multi-key commands across different slots, can be rejected inside the pipeline, even though individual `SET` commands in different slots can be routed to their respective nodes.

If the Jedis version in your project lacks `ClusterPipeline` or does not support the desired operation, **do not invoke API names by guessing**. Pick a verified driver/version, issue single commands per slot, or implement application-level batching and measure the results.

### 6.2. Comparison table between Lettuce and Jedis

| Criterion | Lettuce | Jedis |
|---|---|---|
| Core model | Netty, sync/async/reactive APIs | Primarily sync API, with pipeline objects |
| Standalone pipeline | Yes | Yes |
| Cluster-aware native API | `RedisClusterClient`, async futures, slot routing | `JedisCluster`/`ClusterPipeline` in supported versions |
| Receiving results | `RedisFuture<T>`, await after dispatching many commands | `Response<T>`, call `sync()` before reading |
| Flush tuning | Configurable flush in Spring/Lettuce via appropriate APIs | Pipeline queues commands and syncs via `sync()` |
| Redirects and topology | Lettuce cluster client supports `MOVED`/`ASK` and topology refresh | Depends on cluster client, configuration, and Jedis version |
| Spring Data Redis reactive API | Supported via Lettuce | No equivalent reactive connector |
| Spring adapter limits | Follow Spring Data Redis pipelining docs and exact version | Same; especially do not extrapolate from native Jedis pipelines |
| Pipelines and transactions | Two distinct mechanisms; avoid uncontrolled mixing | Spring Data Redis docs note pipelines and transactions are mutually exclusive in the Jedis connector |

There is no blanket conclusion that "Lettuce is always faster than Jedis" or vice versa. Actual performance depends on RTT, server load, node count, commands per batch, serializers, topology, connection pool, and how the API is used.

## 7. Spring Data Redis executePipelined: usage and limits

Spring Data Redis provides:

- `RedisTemplate.executePipelined(RedisCallback<?>)`: executes multiple commands in a pipeline and returns a list of results.
- `RedisTemplate.executePipelined(SessionCallback<?>)`: groups multiple `RedisOperations` within a session callback.
- Overloads allowing you to specify a serializer to decode results.

Example using `StringRedisTemplate` on Redis Standalone or an environment **verified** to support `executePipelined`:

```java
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RedisBulkWriter {

    private final StringRedisTemplate template;

    public RedisBulkWriter(StringRedisTemplate template) {
        this.template = template;
    }

    public List<Object> writeBatch(String tenantId, int count) {
        if (count < 0 || count > 500) {
            throw new IllegalArgumentException(
                    "count must be between 0 and 500");
        }

        return template.executePipelined(
                (RedisCallback<Object>) connection -> {
                    for (int i = 0; i < count; i++) {
                        String key = "demo:{" + tenantId + "}:item:" + i;
                        String value = "READY";

                        connection.stringCommands().set(
                                key.getBytes(StandardCharsets.UTF_8),
                                value.getBytes(StandardCharsets.UTF_8));
                    }

                    // Must return null: callback result is discarded;
                    // Redis command results come from the pipeline.
                    return null;
                });
    }
}
```

Key points to understand:

1. The callback is invoked to **queue Redis operations**, not to receive the result of each `SET` at call time.
2. The callback must **return `null`**; `executePipelined` returns `List<Object>` containing the pipeline results.
3. For operations like `GET`, results are typically decoded using `RedisTemplate`'s serializers; a custom serializer can be passed when needed.
4. Do not let a callback run unboundedly or issue millions of commands without batch limits.
5. If the current version's cluster adapter does not support pipelining, this example does not become valid merely because keys share a hash tag.

**Note on return values:** in a pipeline, APIs like `opsForValue().get(...)` may return `null` inside the callback because real results have not arrived yet. If you need to read and then use the result to decide the next command, you cannot write sequentially dependent logic inside a standard pipeline. Split into two phases, or choose an appropriate atomic command/script/transaction.

### 7.1. Configuring Redis Cluster in Spring Boot

Example seed-node configuration:

```yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - 127.0.0.1:7000
          - 127.0.0.1:7001
          - 127.0.0.1:7002
      timeout: 5s
```

Spring Boot typically defaults to Lettuce when the Redis starter is installed with standard configuration. Depending on Spring Boot version, you can swap connectors and configure the connection factory. Do not assume declaring `cluster.nodes` alters `executePipelined` limits in Spring Data Redis.

Check whether the application uses `LettuceConnectionFactory` or `JedisConnectionFactory`, verify the actual Spring Data Redis/Jedis/Lettuce versions in the dependency graph, and test the required operations in a real Redis Cluster environment.

### 7.2. When the cluster adapter does not support pipelining

If `executePipelined` throws `UnsupportedOperationException` or an equivalent error:

- Do not try forcing it through a `RedisConnection` to **one node** and sending arbitrary keys belonging to multiple slots.
- For small command counts, use `RedisTemplate` normal single-key calls so the driver routes each key.
- If high-volume independent commands on Cluster are needed and performance is a priority, consider **Lettuce native async cluster-aware** or **Jedis ClusterPipeline** matching your version.
- If commands span multiple keys, check same-slot placement and hash tags, or split into independent commands with partial-result handling.

Do not turn an API layer's lack of support into the assumption "Redis Cluster has no pipelining at the protocol level." The limitation may reside in the specific abstraction layer.

## 8. Grouping batches by slot or node

For multi-tenant data, you might structure keys as:

```text
user:{tenantA}:1
user:{tenantA}:2
user:{tenantB}:1
user:{tenantB}:2
```

Keys sharing `{tenantA}` land in the same slot, and likewise `{tenantB}`. This helps when business logic frequently touches multiple keys within a tenant using multi-key commands or scripts. However, if one tenant grows very large, all of that tenant's keys concentrate in one slot, easily creating a hotspot.

Batch-grouping options:

| Grouping strategy | Best suited when | Trade-offs |
|---|---|---|
| Single batch of arbitrary keys | Using a cluster-aware native API supporting fan-out | Multiple connections and non-simultaneous replies |
| By **slot** | Needing same-slot multi-key commands, or wanting routing control | Many small batches when data is widely scattered |
| By **node** | Batching many single-key commands on the same Redis master | Slots can change owners mid-run; must handle redirects |
| By **tenant hash tag** | Keys within a tenant need same-slot operations | Risk of a hot slot for high-traffic tenants |
| Fixed batch size, e.g., 200–500 commands | Wanting bounded memory/latency and reduced burst load | Must tune based on measurements |

**By node does not mean by slot.** One node typically owns many slots; commands like `MGET` still require keys in the same command to belong to the same **slot**, even when different slots reside on the same node.

### 8.1. Do not use hash tags just to "enable pipelining"

Redis Cluster **does not require** all single-key commands in a cluster-aware batch to share a slot. Hash tags are primarily needed when multi-key commands or scripts depend on keys being in the same slot. Adding `{all}` to every key just to pipeline can dump all load onto one shard.

Distinguish the problems:

- `CROSSSLOT`: constraint of a multi-key command or transaction/script.
- Missing `executePipelined` on Cluster: Spring Data Redis/driver API constraint.
- High latency: RTT, command count, serialization, node load, and batch sizing issue.

These three problems have different solutions.

## 9. Ordering, responses, and consistency

### 9.1. No automatic transactions

A pipeline:

```redis
SET stock:233 "10"
INCR stock:233
SET order:233 "PAID"
```

can send three commands very quickly, yet `SET order:233 PAID` is not a Redis-guaranteed commit marker if an earlier command fails. Redis can execute other commands in the batch even if one command returns an error. To protect invariants, design a transaction/script or separate synchronization mechanism.

### 9.2. Ordering per connection vs. across nodes

On a single Redis connection to one node, commands are processed in the protocol order received by that node. With cross-node batching:

```text
SET item:A status1 --> Node A --> OK
SET item:B status2 --> Node B --> OK
```

there is no guarantee Node A finishes before Node B even if both commands were dispatched sequentially on the JVM. If the second operation depends on the first operation **having completed**, await the result or structure the workflow explicitly; you cannot use a multi-node pipeline as a global transaction sequence.

### 9.3. Partial failures

A batch of 500 commands can yield:

- 480 success replies;
- 10 error replies due to data type or cross-slot errors;
- 10 commands with unknown execution status after a timeout/disconnect.

These illustrative numbers show failure structure. Systems must distinguish **succeeded commands**, **confirmed failed commands**, and **unknown outcomes**. Do not retry an entire batch of cumulative writes without idempotency.

If all operations are `SET key fixedValue` with identical fixed values, retrying carries less risk than `INCR` or `LPUSH`; even so, watch out for concurrent updates and business event ordering.

### 9.4. Pipeline results and serializers

`executePipelined` returns a result list rather than immediate results from each API call inside the callback. Spring Data Redis uses the template's serializers to decode applicable responses. If data is stored in binary or with an incompatible serializer, returned data can be decoded incorrectly or raise an exception.

With native drivers, results take the form of `RedisFuture<T>` (Lettuce) or `Response<T>` (Jedis); completion timing and reading semantics differ from Spring's `List<Object>`. Do not write a naive abstraction assuming all three APIs return results identically.

## 10. Performance: when does pipelining help and when does it hurt?

Pipelining helps when:

- There are many independent operations with minimal dependence on earlier command results.
- Network RTT is significant compared to per-command execution time.
- In-flight commands can be bounded and responses processed in batches.
- Driver and servers have capacity to handle batched traffic bursts.

Pipelining is less helpful or risky when:

- Each command has high CPU cost: pipelining does not make Redis execute a command faster.
- Each command depends on the previous result: you must wait and decide sequentially.
- Operations are blocking commands (`BLPOP`, `XREAD BLOCK`...) on an unsuitable connection.
- Oversized batches grow queues, response buffer memory, timeouts, and tail latency.
- The cluster is continuously resharding/failing over, increasing redirects and unknown outcomes.

### 10.1. Do not pick a batch size as an absolute "standard" number

A batch of 100 `SET` commands with tiny values differs vastly from 100 `HGETALL` commands returning large Hashes. Choose batch size based on **total request and response data**, not just command count.

For instance, a starting rule of thumb might be 100–500 small commands per batch, then tune by measuring. This is only an empirical starting point, with no guarantee of efficiency for every cluster.

Monitor:

| Metric | Meaning |
|---|---|
| Batch p50/p95/p99 latency | Large batches can increase tail latency |
| Throughput (commands/s) | Evaluates gains after reducing RTT |
| Timeouts and redirects | Detects unstable topology or overload |
| Node memory and output buffers | Pipelining many responses can create memory pressure |
| Connection pool, in-flight commands | Spots client-side queue backlogs |
| Per-master Redis CPU/network | Reveals hot shards caused by skewed hash tags |

Compare **the same workload** across sequential calls, Spring Standalone pipelining, and Lettuce/Jedis cluster-native batching (if supported). Do not extrapolate Standalone benchmark numbers to Cluster pipeline speeds.

## 11. Common issues

| Symptom | Possible cause | Resolution |
|---|---|---|
| `executePipelined` errors on Cluster | Spring Data Redis/driver adapter does not support the scenario | Check exact version and docs; use cluster-native API or single commands |
| `CROSSSLOT` on `MGET`/`MSET` | Keys in **one multi-key command** belong to different slots | Use hash tags for related groups or split into single commands |
| Sudden spike in `MOVED`/`ASK` | Topology changed, client holds stale slot cache | Check topology refresh, endpoints, driver redirect config |
| Some keys written, others missing | Pipelines are not transactions; partial failure | Track per-command outcomes, idempotent retry, reconcile |
| `GET` inside Spring callback returns `null` | Command is still in pipeline, no response yet | Read `executePipelined` result instead of immediate return |
| Results have wrong type | Template serializer differs from data format | Check serializers and result-serializer overload |
| Jedis lacks `JedisCluster.pipelined()` | Older Jedis version or different API | Check actual dependency, choose version-appropriate API |
| Jedis pipeline on one node keeps returning `MOVED` | Using single-node connection instead of cluster-aware pipeline | Use cluster-aware client or group keys by slot/node |
| Batch slower than normal commands | Batch too small, heavy response payload, timeouts, serialization | Measure RTT, payload, network; pick suitable size |
| Redis memory grows on large pipelines | Server buffers many unread responses | Split batches, consume responses steadily |
| Adding one hash tag overloads a node | All keys map to the same slot | Scope tags to reasonable groups, distribute hot tenants |
| Retrying `INCR` increments twice | Reply lost after command already ran | Use request IDs/idempotency and confirmation checks |

## 12. Practice: test limits instead of guessing

### Exercise 1 — Distinguish same-slot vs. different-slot keys

On a test Redis Cluster, run:

```redis
CLUSTER KEYSLOT profile:{acct-7}:name
CLUSTER KEYSLOT profile:{acct-7}:status
CLUSTER KEYSLOT profile:{acct-8}:name
```

The two keys with `{acct-7}` share a slot; the remaining key typically has a different slot. Then compare:

```redis
MSET profile:{acct-7}:name An profile:{acct-7}:status ACTIVE
MGET profile:{acct-7}:name profile:{acct-7}:status

# Use a cluster-aware Redis CLI, e.g., redis-cli -c:
MGET profile:{acct-7}:name profile:{acct-8}:name
```

The second `MGET` normally receives `CROSSSLOT`. Even if the same Java program issues it inside a pipeline, slot rules for multi-key commands still hold.

### Exercise 2 — Standalone pipeline with Spring Data Redis

Create a `StringRedisTemplate.executePipelined` service as in section 7, issue 100 `SET` commands, and collect `List<Object>`. Verify:

1. The callback returns `null`.
2. The result list has elements matching the queued commands, according to your version's API behavior.
3. Data is actually present in Redis after the pipeline completes.

Compare sequential vs. pipelined times in a test environment, never against production data.

### Exercise 3 — Same workload on Cluster

Re-run the single-key `SET` workload using:

1. `StringRedisTemplate` sequential calls through a cluster-aware connection factory.
2. `executePipelined` on your exact Spring Data Redis/driver version (recording whether it is supported).
3. Lettuce native async cluster-aware; or Jedis `ClusterPipeline` if supported by the dependency.

Record successes/failures, latency, throughput, redirect counts, and final key state. If `executePipelined` is unsupported, note **which API layer reported the error** instead of concluding the Redis server lacks pipelining.

### Exercise 4 — Observing redirects

In a controllable test Cluster environment, migrate a slot or trigger a failover and observe responses via Lettuce/Jedis. Evaluate:

- Does the driver refresh topology automatically or require configuration?
- Are received responses matched back to the right requests?
- On connection drop, does the client know for sure which writes executed?
- Does the retry mechanism cause duplicate operations?

Topology changes should only be run in an intentional test environment. The important lesson is error handling and idempotency, not forcing redirects on a live business Redis instance.

## 13. Implementation principles

1. **Verify the support layer.** Redis Cluster supports single-key commands and each node understands pipelining, but `RedisTemplate.executePipelined` must be verified against your adapter version.
2. **Distinguish many single-key commands from one multi-key command.** A batch of independent `SET`s across slots is not the same as an `MSET` spanning multiple slots.
3. **Choose the driver for real needs.** Lettuce excels at async/reactive and cluster-aware futures; Jedis has sync pipelines and native ClusterPipeline in newer releases. Native features do not automatically translate into Spring adapter features.
4. **Do not assume batches are transactions.** Nodes can complete at different times and commands can partially succeed.
5. **Bound batches and in-flight commands.** Measure request/response sizes, timeouts, p99 latency, and per-node memory.
6. **Design the keyspace deliberately.** Use hash tags when same-slot multi-key operations are needed, avoiding funneling the whole system into one slot.
7. **Handle topology changes.** Configure refreshes, timeouts, retries, and reconciliation per command semantics; do not blindly retry cumulative commands.

## References

- [Spring Data Redis — Pipelining](https://docs.spring.io/spring-data/redis/reference/redis/pipelining.html): `executePipelined`, serializers, Lettuce flush policy, and notes on pipeline/Cluster limits.
- [Spring Data Redis — Drivers](https://docs.spring.io/spring-data/redis/reference/redis/drivers.html): Lettuce/Jedis capability matrix, cluster connections, pipelining, transactions, and reactive APIs.
- [Redis — Pipelining](https://redis.io/docs/latest/develop/using-commands/pipelining/): mechanism for reducing round trips and reasons for batching.
- [Redis — Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/): hash slots, hash tags, `MOVED`, and `ASK`.
- [Redis — CROSSSLOT error](https://redis.io/docs/latest/develop/reference/errors/common/crossslot/): rules for multi-key commands on Cluster.
- [Lettuce — High Availability and Sharding](https://redis.github.io/lettuce/ha-sharding/): cluster routing and topology refresh.
- [Lettuce — Asynchronous API](https://redis.github.io/lettuce/user-guide/async-api/): `RedisFuture` and dispatching multiple commands before awaiting.
- [Redis — Jedis Pipelines and Transactions](https://redis.io/docs/latest/develop/clients/jedis/transpipe/): Jedis pipelines and `Response<T>` types.
- [Jedis — ClusterPipeline source](https://github.com/redis/jedis/blob/master/src/main/java/redis/clients/jedis/ClusterPipeline.java): example of native ClusterPipeline and multi-node command constraints in Jedis versions with this feature.
