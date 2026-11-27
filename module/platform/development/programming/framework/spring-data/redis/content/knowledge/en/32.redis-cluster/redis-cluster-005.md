# Multi-Key Command Limits and CROSSSLOT Errors in Redis Cluster

> **Module:** Spring Data Redis  
> **Chapter:** Redis Cluster  
> **Topic:** Understanding why many Redis commands only accept keys in the same hash slot, diagnosing `CROSSSLOT` errors, using hash tags, and redesigning operations in Spring Data Redis when accessing multiple keys.

## 1. Context: why does a command work on standalone Redis but fail on Redis Cluster?

A Spring Boot application might currently use standalone Redis:

~~~redis
SET user:101:name "An"
SET user:102:name "Binh"
MGET user:101:name user:102:name
~~~

In standalone Redis, all keys live in the same Redis instance. The `MGET` command reads two keys in a single command and works normally.

When moving to Redis Cluster, keys are distributed across different **hash slots** and different nodes. If `user:101:name` and `user:102:name` belong to two different slots, an `MGET` command requesting both at once will be rejected:

~~~text
(error) CROSSSLOT Keys in request don't hash to the same slot
~~~

This is not because the keys do not exist. Nor is it because Redis Cluster lacks `MGET` support. The issue is that **the two keys do not belong to the same hash slot**, while the command asks to operate on multiple keys as a single unit.

The most important takeaway of this lesson:

> **A Redis Cluster command that truly operates on multiple keys usually requires all keys in that command to belong to the same hash slot. An application can access multiple keys across different slots via independent commands, but doing so does not yield a single atomic command across slots.**

This is a constraint of the Redis Cluster partitioning model, not a Spring Boot-specific bug.

### 1.1. Three goals to distinguish

When code needs multiple keys, ask yourself:

1. **Just fetching multiple values to aggregate?** You can issue multiple single-key requests and merge the results on the client side.
2. **Need a single multi-key Redis command?** The involved keys must share the same slot.
3. **Need atomicity across multiple keys?** Put them in the same slot and use the appropriate Redis command, transaction, or Lua/Redis Function; if they span multiple slots, change the consistency model.

Choosing the wrong goal easily leads to fixing `CROSSSLOT` by splitting a command while inadvertently breaking the atomicity required by the business logic.

## 2. Redis Cluster partitions data using 16,384 hash slots

Redis Cluster uses **16,384 hash slots**, numbered from 0 to 16383. Every key maps to one slot. The Cluster distributes slot ownership across primary nodes; replicas serve replication and failover roles.

### 2.1. Slot mapping formula

For a key without a valid **hash tag**, the slot is calculated as:

\[
\operatorname{slot}(key)=\operatorname{CRC16}(key)\bmod 16384
\]

The hash function processes the bytes of the Redis key, not Java's `String.hashCode()`. Therefore, you cannot use `String.hashCode() % 16384` as a substitute for Redis Cluster's hash slot calculation.

Conceptual example:

~~~text
user:101:name ──CRC16 / 16384──> slot A
user:102:name ──CRC16 / 16384──> slot B
user:103:name ──CRC16 / 16384──> slot C
~~~

The symbols A/B/C are illustrative; the exact slot must be computed from actual key bytes. Keys that look similar by prefix do **not automatically** share a slot.

### 2.2. Hash slots and cluster nodes are two separate layers

One Redis Cluster node can own thousands of slots:

~~~text
Redis Cluster
├── Primary node A: slot group 1
├── Primary node B: slot group 2
└── Primary node C: slot group 3
~~~

Two keys in different slots **can happen to** live on the same node at a given moment. However, a multi-key Redis command can still return `CROSSSLOT` because the rule checks the **slot**, not merely whether the two keys share the same current server address.

During resharding, a slot can move to another node. Therefore, your data model must be built around slots, not the assumption that one node always keeps a fixed set of keys.

### 2.3. Checking slots with Redis CLI

On a node belonging to the Redis Cluster:

~~~bash
redis-cli -c -h 127.0.0.1 -p 7000 CLUSTER KEYSLOT user:101:name
redis-cli -c -h 127.0.0.1 -p 7000 CLUSTER KEYSLOT user:102:name
~~~

`CLUSTER KEYSLOT key` returns the slot for the given key. When the two results differ, they **cannot** be sent together in a multi-key command requiring the same slot.

If a managed Redis environment restricts certain commands, use client tooling or provider-supported observability. Never infer that two keys share a slot merely from their key names or from residing on the same Redis node.

## 3. Hash tags: how to control which keys share a slot

Redis Cluster supports **hash tags**: a non-empty substring inside the first valid `{...}` brace pair recognized in the key name. Redis hashes the portion **inside the braces**, instead of hashing the entire key.

Example:

~~~text
order:{o-101}:status
order:{o-101}:items
order:{o-101}:payment
~~~

All three keys are hashed based on the tag `o-101`, and thus belong to the **same slot**.

~~~text
order:{o-101}:status   ───┐
order:{o-101}:items    ───┼── hash("o-101") ──> Same slot
order:{o-101}:payment  ───┘
~~~

This is the fundamental solution when a group of related keys must participate in the same Redis command.

### 3.1. How do hash tags apply?

| Key | Hashed Portion | Consequence |
|---|---|---|
| `user:101:profile` | Entire key | No deliberate slot grouping |
| `user:{101}:profile` | `101` | Same slot as keys tagged `{101}` |
| `user:{101}:settings` | `101` | Same slot as `user:{101}:profile` |
| `user:{102}:profile` | `102` | May belong to a different slot |
| `order:{o-101}:status` | `o-101` | Same slot as keys containing `{o-101}` |
| `{tenant-7}:user:101` | `tenant-7` | All keys tagged `tenant-7` share a slot |

**Note:** Two different tags **can coincidentally** fall into the same slot because there are only 16,384 slots. Only rely on sharing the exact same tag intentionally to guarantee co-location for keys that must be operated on together.

### 3.2. Practical test

~~~bash
redis-cli -c -h 127.0.0.1 -p 7000 CLUSTER KEYSLOT 'order:{o-101}:status'
redis-cli -c -h 127.0.0.1 -p 7000 CLUSTER KEYSLOT 'order:{o-101}:items'
redis-cli -c -h 127.0.0.1 -p 7000 CLUSTER KEYSLOT 'order:{o-101}:payment'
~~~

All three results must match given consistent key encoding.

Try next:

~~~bash
redis-cli -c -h 127.0.0.1 -p 7000 MGET 'order:{o-101}:status' 'order:{o-101}:payment'
~~~

If the keys hold Redis Strings and share a slot, `MGET` executes normally. If one key does not exist, that position returns nil; **a missing key is not the cause of `CROSSSLOT`**.

### 3.3. Beware empty or inconsistent tags

Example keys:

~~~text
user:{}:profile
user:{101}:profile
user:{101}:settings
user:{101:profile
~~~

Do not treat empty `{}` or an unclosed brace as a grouping hash tag. Hash tag parsing has edge cases; the simplest rule is to use **one clear, non-empty, stable `{...}` pair**, avoiding unrelated braces earlier in the name.

Do not encode the same logical ID differently across keys:

~~~text
order:{101}:status
order:{order-101}:payment
~~~

The two tags differ and are not guaranteed to share a slot. Standardize the key builder function across every publisher, consumer, and service.

### 3.4. Hash tags do not make Redis create data relationships

A hash tag only controls hash slot selection. It does not:

- Create foreign keys.
- Guarantee key existence.
- Make an entire multi-command sequence atomic.
- Maintain secondary indexes automatically.
- Set identical TTLs across keys.
- Guarantee business transactions with a database.

It only allows **commands requiring the same slot** to execute validly; atomicity still depends on the command or transaction used.

## 4. Multi-key commands commonly subject to same-slot constraints

To understand `CROSSSLOT`, first identify which commands carry multiple **key arguments**. Multiple value arguments in one command do not mean multiple Redis keys.

### 4.1. Common command groups

| Group | Commands | Example Requiring Multiple Keys |
|---|---|---|
| Redis String | `MGET`, `MSET`, `MSETNX` | Reading/writing multiple String keys |
| Multi-key delete | `DEL`, `UNLINK` | Deleting multiple keys in one command |
| Set operations | `SUNION`, `SINTER`, `SDIFF` | Computing results across multiple Sets |
| Store Set result | `SUNIONSTORE`, `SINTERSTORE`, `SDIFFSTORE` | Multiple source sets and destination key |
| Sorted Set operations | `ZUNION`, `ZINTER`, `ZDIFF`, and STORE variants | Multiple sorted set keys |
| Move/rename key | `RENAME`, `RENAMENX`, `COPY` | Source and destination keys |
| List operations | `LMOVE`, `BLMOVE`, `RPOPLPUSH` | Source and destination |
| Blocking operations | `BLPOP`, `BRPOP` | List of candidate keys |
| Stream multi-read | `XREAD`/`XREADGROUP` with multiple stream keys | Single command reading from multiple streams |
| Bitmap operations | `BITOP` | Destination key and multiple source keys |
| Scripting | `EVAL`, `EVALSHA`, `FCALL` | The `KEYS` list may have to share a slot |
| Transactions | `WATCH`, `MULTI`/`EXEC` containing multi-key ops | All involved keys must share a slot |

This list is illustrative; Redis adds commands across versions. For any command, inspect its **keyspec** and the Redis Cluster support of your Redis/client version.

### 4.2. Not every command with multiple arguments is multi-key

Example:

~~~redis
HSET user:{101}:profile name An city Hanoi level 4
~~~

This command has **one Redis key**, `user:{101}:profile`, while `name`, `city`, and `level` are fields of that same Redis Hash.

Therefore, `HSET` with multiple field/value pairs still operates on one key and cannot trigger `CROSSSLOT` from those fields.

Similarly:

~~~redis
LPUSH queue:tasks task1 task2 task3
SADD tags:product:101 red premium seasonal
ZADD ranking:daily 100 user101 90 user102
~~~

Values/members inside a Redis List/Set/Sorted Set are not separate Redis keys. Whenever you suspect a command "has multiple items", verify **which argument positions are key arguments**.

### 4.3. Multi-key commands that still work

The claim "Redis Cluster bans all multi-key commands" is **false**. Example:

~~~redis
MSET 'cart:{c-101}:count' 3 'cart:{c-101}:status' open
MGET 'cart:{c-101}:count' 'cart:{c-101}:status'
DEL 'cart:{c-101}:count' 'cart:{c-101}:status'
~~~

All keys share tag `c-101`, so on a normal cluster they belong to a single slot. Each native command keeps its semantics on the node owning that slot.

**Do not infer** that because all three commands succeed, the sequence `MSET → MGET → DEL` becomes a single transaction. Each command remains an independent operation unless wrapped in a transaction or script.

## 5. Reproducing CROSSSLOT with Redis CLI

Suppose a Redis Cluster is running with a node at `127.0.0.1:7000` in a demo environment.

### 5.1. An error example

~~~bash
redis-cli -c -h 127.0.0.1 -p 7000 SET 'cart:{c-101}:count' 3
redis-cli -c -h 127.0.0.1 -p 7000 SET 'cart:{c-202}:count' 5

redis-cli -c -h 127.0.0.1 -p 7000 CLUSTER KEYSLOT 'cart:{c-101}:count'
redis-cli -c -h 127.0.0.1 -p 7000 CLUSTER KEYSLOT 'cart:{c-202}:count'
~~~

If the two slots actually differ, running:

~~~bash
redis-cli -c -h 127.0.0.1 -p 7000 MGET 'cart:{c-101}:count' 'cart:{c-202}:count'
~~~

causes Redis to return the familiar error:

~~~text
CROSSSLOT Keys in request don't hash to the same slot
~~~

The example uses two different tags for illustration; **verify `CLUSTER KEYSLOT` first** because two different tags can happen to collide in the same slot.

### 5.2. Changing the key schema to share a slot

~~~bash
redis-cli -c -h 127.0.0.1 -p 7000 SET 'cart:{c-101}:count' 3
redis-cli -c -h 127.0.0.1 -p 7000 SET 'cart:{c-101}:status' open

redis-cli -c -h 127.0.0.1 -p 7000 MGET 'cart:{c-101}:count' 'cart:{c-101}:status'
~~~

Both keys share a tag, so `MGET` succeeds if both hold Redis Strings. Changing key names **is not** an automatic data fix: if legacy keys already exist and must be retained, the application needs a migration/copy procedure obeying Redis Cluster semantics.

### 5.3. Note when using redis-cli -c

The `-c` flag tells `redis-cli` to follow cluster redirections like `MOVED` or `ASK`. It **does not** alter a key's hash slot and **does not** turn a cross-slot `MGET` into a valid command.

Thus:

~~~text
redis-cli -c ... MGET key-slot-A key-slot-B
~~~

can still return `CROSSSLOT`. Switching Redis node endpoints or adding `-c` is not a fix for cross-slot multi-key requests.

## 6. CROSSSLOT vs. MOVED, ASK, and TRYAGAIN

These four messages appear in cluster environments but have different root causes.

| Message | Primary Meaning | Handling Approach |
|---|---|---|
| `CROSSSLOT` | Redis keys of **a single command** do not share a slot | Design keys with a shared tag, or split into independent commands if business logic permits |
| `MOVED slot host:port` | Client sent command to a node not owning the slot | Cluster-aware client updates topology and resends to the right node |
| `ASK slot host:port` | Slot/key is migrating and needs a temporary redirect | Cluster client handles ASKING/temporary redirect per protocol |
| `TRYAGAIN` | Operation cannot complete temporarily, possibly during resharding | Bounded retry with backoff when appropriate; check cluster state |

Do not catch all of these errors and retry infinitely:

- `MOVED`/`ASK` are routing mechanisms that compatible clients normally handle.
- `TRYAGAIN` can be transient; retrying may help.
- `CROSSSLOT` due to an incompatible key schema usually **never clears** even if you retry the same command thousands of times.

### 6.1. Why can same-slot keys still fail during migration?

While Redis Cluster is resharding, some same-slot multi-key commands may hit temporary errors if keys in that slot are temporarily in transition between source and target. This differs from `CROSSSLOT` caused by two keys permanently in two different slots.

If disruption occurs during resharding, check:

- Slot ownership and cluster topology.
- Whether the driver handles MOVED/ASK properly.
- Whether the error is transient or repeats on every run.
- Whether the keys are currently in a migrating/importing state.

Do not treat being in the same slot as a guarantee of "zero transient cluster errors ever".

## 7. Connecting Spring Boot to Redis Cluster

A Spring Boot application typically uses `spring-boot-starter-data-redis` with the Lettuce cluster-aware driver.

### 7.1. Dependencies

Gradle Kotlin DSL example:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-redis")
}
~~~

Lettuce is normally the default client in the Spring Boot Redis starter unless replaced by Jedis or custom configuration.

### 7.2. application.yml for Redis Cluster

~~~yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - redis-a.internal:7000
          - redis-b.internal:7001
          - redis-c.internal:7002
        max-redirects: 5
      connect-timeout: 2s
      timeout: 3s
~~~

Hostnames are illustrative. In real environments use actual cluster node addresses/endpoints and configure ACLs, passwords, TLS, topology refresh, read preferences, or Sentinel/Cluster per provider.

Across Spring Boot versions, Redis property prefixes can vary. Examples here follow the `spring.data.redis` structure used in modern Spring Boot.

### 7.3. RedisClusterConfiguration and connection factory

You can configure it manually:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisClusterConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;

@Configuration
public class RedisClusterClientConfiguration {

    @Bean
    LettuceConnectionFactory redisConnectionFactory() {
        RedisClusterConfiguration cluster =
                new RedisClusterConfiguration(List.of(
                        "redis-node-1.internal:6379",
                        "redis-node-2.internal:6379",
                        "redis-node-3.internal:6379"));

        return new LettuceConnectionFactory(cluster);
    }
}
~~~

This is an **alternative** to default auto-configuration; do not declare a manual factory bean alongside equivalent auto-configured properties without clear intent.

Connecting to the cluster properly only solves routing and authentication. It **does not relax** the restrictions on `MGET`, `MSET`, `EVAL`, `MULTI`, or other native multi-key commands.

## 8. Spring Data Redis: where do errors typically surface?

In Spring Data Redis, high-level methods can translate into Redis commands needing multiple keys. Example:

~~~java
List<String> keys = List.of(
        "cart:{c-101}:count",
        "cart:{c-202}:count");

List<String> values =
        stringRedisTemplate.opsForValue().multiGet(keys);
~~~

If the keys reside in different slots, behavior depends on the **specific API and client implementation**:

- If the client ultimately issues **one native MGET** with all keys, Redis Cluster returns `CROSSSLOT`.
- Some clients/high-level APIs may perform **scatter/gather**: grouping keys by slot and issuing multiple commands, then merging results. In that case the Java call may succeed, yet **it is not an atomic cross-slot native MGET**.
- Some template/driver versions have pipelining limits or distinct connection handling when spanning multiple slots.

Therefore, you cannot assert "every `multiGet` with cross-slot keys always throws" without checking your exact Spring Data Redis method and Redis driver version. Equally, you **must not** see the code return a list and conclude Redis now supports atomic cross-slot multi-key commands.

### 8.1. Distinguishing Java APIs from Redis commands

| Application API | Possible Underlying Operation | Implication |
|---|---|---|
| `opsForValue().get(k)` | One `GET` | Single key only; cluster client routes by slot |
| `opsForValue().multiGet(keys)` | `MGET` or multi-slot handling depending on implementation | Verify native command vs. scatter semantics |
| `opsForValue().multiSet(map)` | `MSET` or client decomposition | If decomposed, group atomicity is lost |
| `delete(Collection<K>)` | Multi-key `DEL` or grouped depending on implementation | Do not assume atomic group deletion |
| `executePipelined(...)` | Multiple commands sent without waiting for each reply | Does not bypass CROSSSLOT for a multi-key command |
| `multi()`/`exec()` | Redis transaction | Cannot guarantee cross-slot atomicity |
| `execute(script, keys, ...)` | `EVAL`/`EVALSHA` | Verify keys/slots and Redis scripting rules |

This table shows **semantic analysis**, not a promise that every API maps to one exact command across all Spring Data Redis versions.

### 8.2. Clues in exceptions

An application may see a message resembling:

~~~text
CROSSSLOT Keys in request don't hash to the same slot
~~~

wrapped inside a Spring Data Redis, Lettuce, or Redis client exception. The exact exception class depends on driver, version, and call site; you may see `DataAccessException` or a client exception in the cause chain.

When handling it:

1. Log the operation name, key count, and a redacted sample of keys if appropriate.
2. Look for `CROSSSLOT` in the exception cause chain.
3. Inspect the actual slots of the serialized keys.
4. Confirm whether the call site sends **a single multi-key command** or another high-level API.
5. Decide whether to update the key schema or split commands based on atomicity needs.

Do not swallow every `DataAccessException` and silently return a cache miss, as that masks key-design bugs causing incomplete data returns.

## 9. Solution A: use hash tags for keys that must be operated on together

Suppose an order has status, total amount, and payment info:

~~~text
order:{o-101}:status
order:{o-101}:total
order:{o-101}:payment
~~~

A group of same-tag keys can be read together:

~~~java
import java.util.List;
import org.springframework.data.redis.core.StringRedisTemplate;

public class OrderReadService {

    private final StringRedisTemplate redis;

    public OrderReadService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public List<String> readOrderFields(String orderId) {
        String tag = "{" + orderId + "}";

        return redis.opsForValue().multiGet(List.of(
                "order:" + tag + ":status",
                "order:" + tag + ":total",
                "order:" + tag + ":payment"));
    }
}
~~~

Here, all three Redis keys share the `{orderId}` hash tag. `multiGet` satisfies the slot condition to issue a native MGET.

### 9.1. Be careful with orderId

Never inject an ID from untrusted input directly into a key and allow `{` or `}` to alter the tag structure. You should:

- Validate IDs against a strict allowed pattern.
- Escape/encode special characters if free-form IDs are permitted.
- Apply namespacing by environment, service, and tenant appropriately.
- Avoid creating unboundedly long keys.

For example, if `orderId` is internally generated as a UUID, validating UUID format mitigates this risk. Still, two different UUIDs can hash to the same slot due to the finite slot space; that is normal Redis behavior.

### 9.2. Keep tags consistent across all services

If service A creates:

~~~text
order:{o-101}:status
~~~

while service B creates:

~~~text
order:{order-o-101}:payment
~~~

then multi-key reads/writes are no longer guaranteed to share a slot.

Define a shared key-builder utility at the data-access boundary, or at minimum document the key schema with consistent examples. Avoid copy-pasting string concatenation across controllers and services.

### 9.3. Aggregate-based design pattern

A useful pattern:

~~~text
customer:{customer-101}:profile
customer:{customer-101}:preferences

order:{order-101}:status
order:{order-101}:payment

session:{session-abc}:token
session:{session-abc}:metadata
~~~

Each **aggregate** groups related keys that must be operated on together under its own tag. This generally distributes load much better than tagging across an entire tenant.

## 10. Solution B: execute multiple independent commands when atomicity is not needed

If you simply need to display two independent pieces of data for two users, you **do not need** to force all keys into the same slot.

Example:

~~~text
user:101:name
user:102:name
~~~

You can read each key separately and combine them:

~~~java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public Map<String, String> readIndependentKeys(
        StringRedisTemplate redis, List<String> keys) {

    Map<String, String> result = new LinkedHashMap<>();

    for (String key : keys) {
        result.put(key, redis.opsForValue().get(key));
    }

    return result;
}
~~~

Each `GET` touches only one key, so the cluster-aware client routes it to the node owning that key's slot. Still:

- Commands run sequentially in the loop, incurring multiple RTTs.
- There is no consistent snapshot across the two slots.
- If the second command fails, the first has already been read.
- For rapidly changing keys, results may reflect different points in time.

If high performance is needed, you can organize concurrent or grouped `GET`s using a client supporting cluster-aware distribution. Just manage concurrency, connection load, timeouts, and result ordering.

### 10.1. ReactiveRedisTemplate and combining results

In WebFlux:

~~~java
import java.util.Map;
import reactor.core.publisher.Mono;
import reactor.util.function.Tuple2;

Mono<String> first =
        reactiveRedisTemplate.opsForValue().get("user:101:name");
Mono<String> second =
        reactiveRedisTemplate.opsForValue().get("user:102:name");

Mono<Tuple2<String, String>> combined = Mono.zip(first, second);
~~~

This example executes two independent Redis `GET` commands, with no multi-key native command. Note that `Mono.zip` completes empty if either publisher emits no item; when one key may be missing, provide an appropriate fallback policy so you do not lose the remaining result.

Reactor publishers help compose I/O, yet **do not create a cross-slot Redis transaction**.

### 10.2. Scatter/gather trades off semantics

A client may automatically:

1. Group keys by slot.
2. Send one or more requests to each node.
3. Collect responses.
4. Reassemble results to match the original key order.

This involves **multiple operations**, even if presented as a single Java method. The upside is ease of use; the downsides are:

- No atomicity across the whole key set.
- A single node failure can leave partial completion.
- Can increase request count and retry complexity.
- Data on different nodes may be read at slightly different instants.

If business logic only aggregates data for display, scatter/gather may be acceptable. If consistency guarantees are required, it does not replace a Redis transaction or a redesigned data model.

## 11. Solution C: consolidate multiple fields into one Redis key

Sometimes, instead of five separate Redis String keys, a single Redis Hash is a better fit.

Replace:

~~~text
user:101:name
user:101:email
user:101:city
~~~

with:

~~~redis
HSET user:101 name An email an@example.test city Hanoi
HGETALL user:101
~~~

All fields reside inside **one Redis key**, `user:101`. `HGETALL` operates on a single key and avoids multi-key slot constraints.

Spring Data Redis:

~~~java
import java.util.Map;
import org.springframework.data.redis.core.StringRedisTemplate;

public class UserHashStore {

    private final StringRedisTemplate redis;

    public UserHashStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void saveUser(String id, String name, String city) {
        redis.opsForHash().putAll(
                "user:" + id,
                Map.of("name", name, "city", city));
    }

    public Map<Object, Object> loadUser(String id) {
        return redis.opsForHash().entries("user:" + id);
    }
}
~~~

Benefits:

- One hash key instead of many string keys.
- `HGETALL`/`HMGET` fetches multiple fields from the same key.
- `HSET` updates a subset of fields on the key.
- No hash tag needed to keep fields together in one key.

Trade-offs remain:

- TTL applies to the **entire Redis key** normally, rather than per-field TTL across all versions/deployments.
- An overly large Hash can make `HGETALL` bandwidth-heavy.
- If fields have independent lifecycles, merging them may be unsuitable.
- Serialization and schema evolution still need management.

Newer Redis versions offer hash-field expiration capabilities, but do not assume your Spring Data Redis and Redis deployment support all of those APIs; the key-level TTL model remains the common safe mental model.

### 11.1. When is consolidating data a good direction?

Combine into a single Redis Hash when the fields:

- Belong to one aggregate and are usually read together.
- Share ownership and lifecycle.
- Do not require independent expiration.
- Do not create an oversized object.
- Do not require transactions across multiple keys.

If fields must be updated together with single-command semantics, `HSET` across multiple fields on one key is typically simpler than orchestrating a Redis transaction across multiple String keys.

## 12. Transactions: MULTI/EXEC and WATCH on Redis Cluster

A Redis transaction executes commands inside `MULTI`/`EXEC` sequentially without other clients' commands interleaving during execution. Redis Cluster has no general distributed transaction spanning multiple hash slots.

### 12.1. Valid same-slot transaction

Example:

~~~redis
MULTI
SET 'account:{a-101}:balance' 900
SET 'account:{a-101}:updatedAt' '2026-11-13T03:00:00Z'
EXEC
~~~

Both keys share tag `a-101`. On a connection to the node owning the slot, the transaction can execute the batch properly.

### 12.2. Multi-slot transactions are not guaranteed

Example:

~~~redis
MULTI
DECRBY 'account:{a-101}:balance' 100
INCRBY 'account:{a-202}:balance' 100
EXEC
~~~

The two accounts have different tags, typically landing in two different slots. Redis Cluster does not provide an atomic `MULTI`/`EXEC` transaction across those slots. Depending on client/command handling, errors can occur while queuing or executing.

**Do not "fix" the error by sending each account update separately** if business logic requires an atomic transfer. Splitting into two commands risks debiting one account without crediting the other on network failure.

If these are payment balances, the source of truth belongs in a system/protocol providing appropriate consistency, such as a transactional database. Redis can serve as a cache, temporary counter, or part of a controlled design.

### 12.3. WATCH is also slot-constrained

`WATCH` provides optimistic locking: the client watches keys, reads data, then issues `MULTI`/`EXEC` to update only if watched keys remain unmodified.

When `WATCH` or a transaction touches multiple keys in a cluster, participating keys must also satisfy **same-slot** rules so Redis can execute on a single shard.

~~~text
WATCH account:{a-101}:balance account:{a-101}:limit
... read/check ...
MULTI
... update same-slot keys ...
EXEC
~~~

In Spring Data Redis, `SessionCallback` ensures transaction operations reuse the same Redis session/connection, yet **it does not make keys in different slots share a slot**.

### 12.4. Redis transactions do not roll back like SQL

Do not interpret "atomic" here as rolling back every command in the batch if a runtime error occurs. Redis `MULTI`/`EXEC` transactions do not provide RDBMS-style automatic rollback when a command inside `EXEC` fails.

Distinguish:

- **No interleaving:** when `EXEC` runs, valid commands in the batch execute consecutively.
- **Race conditions:** use `WATCH` or Lua if you must inspect values before updating.
- **Rollback:** Redis does not undo earlier successful commands when a later command errors.
- **Multi-slot distribution:** the cluster does not provide atomic multi-shard transactions via `MULTI` alone.

## 13. Lua scripts and Redis Functions: same-slot remains a key constraint

Lua/Redis Functions bundle conditional checks and updates into a single server-side execution on Redis. When running on Redis Cluster, keys accessed by a script/function must obey cluster rules and cannot arbitrarily touch keys across multiple hash slots.

### 13.1. Example script updating two same-tag keys

Suppose we need to enforce a quota limit and increment an action counter for a user:

~~~lua
local quotaKey = KEYS[1]
local counterKey = KEYS[2]
local limit = tonumber(ARGV[1])

local quotaUsed = tonumber(redis.call('GET', quotaKey) or '0')
if quotaUsed >= limit then
    return 0
end

redis.call('INCR', quotaKey)
redis.call('INCR', counterKey)
return 1
~~~

Invoking via Redis CLI with same-tag keys:

~~~redis
EVAL "local n=tonumber(redis.call('GET',KEYS[1]) or '0'); if n>=tonumber(ARGV[1]) then return 0 end; redis.call('INCR',KEYS[1]); redis.call('INCR',KEYS[2]); return 1" 2 'quota:{u-101}:used' 'quota:{u-101}:actions' 100
~~~

Both Redis keys share `{u-101}` and therefore share a slot. The script performs the check and updates consecutively in one atomic server-side execution per Lua scripting semantics.

### 13.2. Declare keys explicitly

In Redis scripting, keys accessed by the script should be passed explicitly via the `KEYS` list. Never construct new key names purely from `ARGV` inside the script and hope the cluster routes to another node.

~~~text
KEYS[1] = quota:{u-101}:used
KEYS[2] = quota:{u-101}:actions
ARGV[1] = 100
~~~

Redis Cluster needs to know which keys a command/script touches in order to route and enforce slot constraints. Accessing a key in another slot inside a script is invalid for normal cluster operations.

### 13.3. Calling scripts in Spring Data Redis

Spring Data Redis provides `RedisScript` and `RedisTemplate.execute(...)` to run Lua.

Structural example:

~~~java
import java.util.List;
import org.springframework.data.redis.core.script.DefaultRedisScript;

DefaultRedisScript<Long> script = new DefaultRedisScript<>();
script.setScriptText("""
    local used = tonumber(redis.call('GET', KEYS[1]) or '0')
    if used >= tonumber(ARGV[1]) then return 0 end
    redis.call('INCR', KEYS[1])
    redis.call('INCR', KEYS[2])
    return 1
    """);
script.setResultType(Long.class);

Long result = stringRedisTemplate.execute(
        script,
        List.of(
                "quota:{u-101}:used",
                "quota:{u-101}:actions"),
        "100");
~~~

This Java example uses text blocks (Java 15+) and a configured `StringRedisTemplate`. Using the same tag satisfies the slot requirement. Depending on driver/Redis versions, errors may be wrapped in Spring or Redis client exceptions.

**Note:** A script atomic on one Redis shard does not create a distributed transaction with a database or another Redis shard. Long-running scripts also block command processing on that shard; keep logic concise and avoid overusing Lua for everything.

## 14. Pipelines do not solve CROSSSLOT

**Pipelining** reduces wait time between commands by sending multiple requests before reading all replies. It **does not** alter key placement rules.

Example pipeline of commands:

~~~text
GET user:101:name
GET user:102:name
GET user:103:name
~~~

Each `GET` has a single key. A cluster-aware driver may route individual requests to appropriate nodes per its pipeline support, reducing overhead. Still, do not assume every use of `executePipelined(...)` on a cluster supports every node/connection combination.

If a pipeline contains:

~~~text
MGET user:101:name user:102:name
~~~

it remains **one multi-key command**. If the two keys are in different slots, the native command still triggers `CROSSSLOT`.

### 14.1. Pipelines, scatter/gather, and transactions

| Technique | Reduces round trips? | Accesses cross-slot keys? | Group atomicity? |
|---|---|---|---|
| Multiple independent GETs | Not automatically | Yes, via cluster-aware routing | No |
| Pipelining independent GETs | Possibly, depending on client | Yes if client supports cluster pipeline routing | No |
| Native MGET | Yes, single command | Only when keys share a slot | Single-command semantics on shard |
| High-level scatter/gather MGET | Can optimize | Possible depending on API/client | Not atomic across slots |
| MULTI/EXEC | Does not automatically reduce RTT | Not for multi-slot transactions | Group execution on same shard |
| Lua/Function | Single server-side round trip | Not arbitrarily across slots | Atomic on shard when validly designed |

Selecting a technique must begin with data consistency requirements, followed by network optimization.

## 15. Redis Repository and secondary indexes on a Cluster

Spring Data Redis Repository can use `@RedisHash`, `@Id`, and `@Indexed` to store entities, indexes, and metadata. When running on Redis Cluster, recognize that a repository may emit **multiple commands across multiple internal keys**, not just one entity key.

Example entity:

~~~java
@RedisHash("products")
public class ProductEntity {
    @Id
    private String id;

    @Indexed
    private String category;
}
~~~

The repository may store the entity in a Redis Hash and create index structures for finder queries. Those index and entity keys are subject to corresponding Redis Cluster routing/operations.

### 15.1. Do not assume all Repository operations are atomic

A `repository.save(entity)` call looks like a single Java method call, yet does not mean Redis executes one atomic command underneath. Spring Data Redis Repository handles mapping, indexes, and TTL via its own mechanisms; cluster placement can expose multi-key constraints more sharply.

If the application requires entity and index updates as an atomic transaction, verify actual support and semantics; never assume Redis Repository guarantees that on a Cluster.

### 15.2. Hash tags on Repository-generated keys

Do not put `@RedisHash("products:{tenant}")` and assume every auxiliary key generated by Repository will automatically use that tag as you expect. Internal keys may follow different conventions, and repository internals do not necessarily expose full control over every key's placement.

A safer approach is to:

1. Determine whether Redis Cluster fits your current repository model.
2. Inspect the exact commands and keyspaces generated.
3. Consider `RedisTemplate` with a controlled key schema for operations needing same-slot guarantees.
4. Offload complex queries/indexes to a suitable datastore if strong consistency is needed.
5. Read the Spring Data Redis documentation for your exact version regarding Redis Cluster and repositories before deploying.

### 15.3. Redis Cache abstraction and cache key prefixes

`RedisCacheManager` typically names keys like:

~~~text
products::101
products::102
~~~

Having the same prefix **does not mean two keys share a slot**. If a feature needs a native MGET across multiple cache keys, sharing a cache name does not satisfy the slot constraint.

Likewise, serializers can alter key bytes; when computing slots, Redis hashes the **actual bytes**, not the logical Java key object.

## 16. Why does an overly broad hash tag cause hotspots?

Hash tags solve the correctness requirement of putting multiple keys in the same slot. However, if all keys are placed under the same tag:

~~~text
order:{all}:o-101:status
order:{all}:o-102:status
order:{all}:o-103:status
...
~~~

then every key lands in **one hash slot**, and that slot belongs to one primary node at a time. Redis Cluster cannot distribute the load of those keys across multiple primary nodes while they share the same slot.

Consequences can include:

- One node running hot on CPU while others sit idle.
- Memory skew: one node holds the bulk of the data.
- Network traffic concentrated on one connection/node.
- Business hotspots causing bottlenecks disproportionate to total cluster capacity.
- Adding nodes fails to spread a single hot slot across multiple nodes simultaneously.

### 16.1. Tag by aggregate rather than system-wide

Poor if you want distribution:

~~~text
product:{all}:p-101
product:{all}:p-102
product:{all}:p-103
~~~

Better for independent aggregates:

~~~text
product:{p-101}:core
product:{p-101}:stock

product:{p-102}:core
product:{p-102}:stock

product:{p-103}:core
product:{p-103}:stock
~~~

Each product has its key group colocated, while different products spread across many slots.

### 16.2. Is tagging by tenant suitable?

~~~text
tenant:{t-01}:user:101
tenant:{t-01}:user:102
tenant:{t-01}:orders
~~~

This pattern puts multiple keys of a tenant in the same slot, though a large tenant can become a hotspot. If business logic only needs atomicity per order, tagging by `orderId` is generally better than tagging the entire tenant.

Tag choice should follow the **smallest atomicity boundary truly needed**. The more keys you force into one slot, the less load distribution you retain.

### 16.3. Do not abuse hash tags just to "fix an error"

If an endpoint needs to read 100,000 independent user profiles, do not give all keys the same tag just to run `MGET`. Client-side batching/scattering is usually better because it avoids pinning hot data to one shard.

## 17. When cross-slot multi-key operations are needed and business correctness still matters

Some requirements cannot be solved simply by "issuing multiple GETs":

- Transferring balances between two accounts in two slots.
- Placing an order that deducts stock across multiple different products simultaneously.
- Moving an item between two Redis Lists in different slots.
- Writing state and distributed indexes belonging to two shards.

If atomicity across keys is mandatory, consider these design options:

### 17.1. Co-locate keys that genuinely belong to the same transaction

If all participating keys are updated together frequently and do not create an oversized hotspot, share a hash tag for that **specific group**. Then use native multi-key commands or Lua/transactions with appropriate semantics.

Example of multiple keys for a single booking:

~~~text
booking:{b-101}:state
booking:{b-101}:hold
booking:{b-101}:expiresAt
~~~

### 17.2. Consolidate data into a single key

A Redis Hash or JSON String can store an aggregate in one Redis key. When all fields reside in one key, several operations reduce to a single-key command.

Just weigh payload size, aggregate contention, TTLs, and the cost of reading/writing the entire object.

### 17.3. Use a transactional source of truth

If the domain involves money, physical inventory, or critical permissions, a relational database or system with proper transactions/constraints should usually hold the authoritative state. Redis can act as a secondary cache/index refreshed via events/outbox.

Never try to simulate a distributed ACID transaction using two Redis Lua scripts running on two shards. Two separate scripts do not form a globally atomic transaction.

### 17.4. Saga/compensation when eventual consistency is acceptable

Some workflows can be broken into steps with:

1. A business operation ID / idempotency key.
2. Persisted state for each step.
3. Retries when a step fails.
4. Compensation when business actions must be undone.
5. Reconciliation if states diverge.

This is more complex than a single transaction and requires explicit business decisions. Redis Cluster does not automatically supply sagas, system-wide distributed locks, or compensation.

### 17.5. Multi-key atomicity does not mean exactly-once

Even when keys share a slot and a script succeeds, the client may time out before receiving the reply. Retrying a non-idempotent `INCR`/`LPUSH` can apply the side effect twice. Build idempotency and confirmation state around critical operations.

## 18. Choose the key schema before writing code

A helpful practice is tabulating **which groups of keys must be updated or read atomically**.

| Operation | Key Group | Same Slot Needed? | Recommendation |
|---|---|---|---|
| View two independent user profiles | `user:101`, `user:102` | No | Separate GETs and merge |
| Update multiple attributes of one user | `user:{101}:profile`, `user:{101}:settings` | Yes if using a single native multi-key op | Tag by user or combine into a Hash |
| Read multiple items in a cart | `cart:{c-101}:item:1`, `cart:{c-101}:item:2` | Yes if using native MGET | Tag by cart |
| Fetch multiple unrelated categories | `category:1`, `category:2` | Not required | Scatter/gather or cache an aggregate |
| Transfer funds between two accounts | `account:{a-101}`, `account:{a-202}` | Cannot force multi-slot transaction | Use DB transaction or redesign model |
| Booking with state and hold | `booking:{b-101}:state`, `booking:{b-101}:hold` | Yes if script/transaction needed | Tag by booking |
| Log entries for multiple users | Multiple stream keys | No if each XADD is independent | Independent commands; handle errors per command |

A good tagging strategy aligns **data boundaries** with **atomicity boundaries**. If a group grows too large, consider splitting the workflow and adopting controlled eventual consistency.

### 18.1. Key builder in Java

Centralize key construction rules:

~~~java
public final class RedisClusterKeys {

    private RedisClusterKeys() {
    }

    public static String orderStatus(String orderId) {
        return "order:{" + validate(orderId) + "}:status";
    }

    public static String orderPayment(String orderId) {
        return "order:{" + validate(orderId) + "}:payment";
    }

    private static String validate(String id) {
        if (id == null || !id.matches("[a-zA-Z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("Invalid id");
        }
        return id;
    }
}
~~~

Both methods use the same validated ID and therefore always produce the same hash tag. If business IDs can contain special characters or binary forms, define canonical encoding rather than arbitrarily rejecting valid IDs.

### 18.2. Namespaces and versions

Example:

~~~text
app:v2:order:{o-101}:status
app:v2:order:{o-101}:payment
~~~

Even when the prefix changes, the tag remains `o-101`, so both keys share a slot. If a schema update requires migrating from `v1` to `v2`, prepare a transition plan because changing key names does not move existing contents automatically.

## 19. Subtle edge cases easily overlooked

### 19.1. RENAME and COPY must also consider source and destination

An application running:

~~~redis
RENAME 'cache:{old}:profile' 'cache:{new}:profile'
~~~

is issuing a command operating on two Redis keys. If the two tags map to different slots, the command is not a valid cross-slot rename on Redis Cluster.

To move data across slots, you need a client-side copy/read-write/delete workflow handling partial failures. **Do not treat a copy → delete sequence as an atomic rename.**

### 19.2. XREAD across multiple Streams

An `XREAD STREAMS stream-A stream-B ...` command takes multiple stream keys. On Redis Cluster, those stream keys must satisfy slot constraints when executed in the same command.

Instead of bundling every tenant's stream into one command, you can:

- Use a single shared stream if architecture and load allow.
- Tag related streams together when multi-stream reads in one command are genuinely needed.
- Run separate subscriptions/consumers reading streams in different slots independently.

Consider load and reliability; do not force every stream into a single hot slot just to use one `XREAD`.

### 19.3. Multi-key DEL

~~~redis
DEL 'cache:{u-101}:a' 'cache:{u-202}:b'
~~~

can fail with `CROSSSLOT`. A loop issuing one `DEL` per key can delete both, though not atomically across slots. If deleting rebuildable cache entries, this trade-off is usually acceptable. If deletion is a critical business step, design idempotency and recovery.

### 19.4. Multi-key Set/Sorted Set commands

~~~redis
SINTER 'roles:{u-101}:assigned' 'roles:{u-101}:allowed'
~~~

shares a tag and can execute on one shard. However:

~~~redis
SINTER 'roles:{u-101}:assigned' 'roles:{u-202}:assigned'
~~~

is not guaranteed to share a slot. To intersect data across multiple users, consider reading Sets separately and intersecting in the client, or placing the query model in an appropriate datastore; if a consistent cross-user snapshot is mandatory, separate reads will not satisfy it.

### 19.5. Wildcards do not put keys in the same slot

Key names:

~~~text
products:*
products:{*}:*
~~~

do not force keys into the same slot. Wildcards are patterns for commands like `SCAN`/`KEYS`, not a catch-all hash tag for existing keys.

When `{*}` appears literally in a key, Redis treats `*` as the tag string, which **does not mean "match all keys"** in hash slot rules. Avoid confusing pattern syntax with hash tags.

### 19.6. SCAN in Redis Cluster

A normal `SCAN` operates within a single node/connection; traversing all keys in a Cluster requires running across every primary node or using a cluster-aware API that distributes the scan. This is not a multi-key command returning `CROSSSLOT`, but it directly affects the assumption that "one Redis connection sees the whole keyspace".

Never use `KEYS *` to scan a large production cluster. Bound key/cursor batches and measure scan impact.

### 19.7. Multi-key in cluster with unusual serializers

An application might construct Java key `order:{o-101}:status` yet serialize it with JDK binary format before sending to Redis. If the actual wire bytes include metadata/prefixes, `{o-101}` may not behave as expected.

Hash slots are computed from **serialized Redis key bytes**. When grouping keys with hash tags, prefer `StringRedisSerializer` or a controlled serializer that preserves exact tag bytes.

## 20. Debugging from exception back to key schema

Suppose application logs show:

~~~text
org.springframework.dao.DataAccessException: ...
CROSSSLOT Keys in request don't hash to the same slot
~~~

Diagnostic sequence:

**Step 1 — Locate the exact command or API.**

- `multiGet` or `multiSet`?
- `delete(Collection)`?
- Lua `execute` with a key list?
- `WATCH`/`MULTI`/`EXEC`?
- A multi-key repository operation?
- An `XREAD` spanning multiple streams?

**Step 2 — List the Redis key arguments of that exact command.**

Do not list fields/values and mistake them for keys.

**Step 3 — Inspect key bytes and hash slots.**

~~~bash
redis-cli -c -h node-1.internal -p 6379 CLUSTER KEYSLOT 'order:{o-101}:status'
redis-cli -c -h node-1.internal -p 6379 CLUSTER KEYSLOT 'order:{o-101}:payment'
~~~

If binary serializers produce the keys, use proper tooling to inspect actual bytes rather than relying solely on Java strings in a debugger.

**Step 4 — Determine whether atomicity is mandatory.**

- Not mandatory: issue individual commands or cluster-aware batching.
- Mandatory on a small group: design a shared hash tag or a single Redis Hash.
- Mandatory across shards: change the transaction/consistency model.

**Step 5 — Audit the key schema across all producers.**

If one service writes `user:{101}:profile` while another writes `user:101:settings`, fixing only one code path is not enough.

**Step 6 — Monitor infrastructure.**

If keys share a slot yet transient errors occur during resharding, check MOVED/ASK/TRYAGAIN, topology refresh, and failover handling. Do not lump all errors into a "CROSSSLOT fix".

## 21. Testing against a real Redis Cluster instead of standalone

A common pitfall is running unit/integration tests against standalone Redis, where `MGET key1 key2` always succeeds. Once deployed to a cluster, the exact same code throws `CROSSSLOT`.

### 21.1. Testing slot placement

With a key builder:

~~~java
String status = RedisClusterKeys.orderStatus("o-101");
String payment = RedisClusterKeys.orderPayment("o-101");
~~~

Verify against a real Redis Cluster:

~~~text
CLUSTER KEYSLOT status
CLUSTER KEYSLOT payment
~~~

They must match. This test validates key schema, not whether a Spring method is transactional.

### 21.2. Structuring test cases

| Test Case | Expectation |
|---|---|
| Two keys with same hash tag, `MGET` | Succeeds, given matching data types |
| Two keys in different slots, raw `MGET` | `CROSSSLOT` |
| Two independent cross-slot `GET`s | Succeeds via cluster-aware client |
| `MULTI` with same-slot keys | Succeeds under supported conditions |
| `MULTI` with cross-slot keys | Must not be relied upon as a distributed transaction |
| Lua with same-slot `KEYS` | Runs if script/commands are valid |
| Lua with cross-slot keys | Restricted by cluster rules |
| Driver handling `MOVED` | Routes/refreshes topology per configuration |
| Resharding/failover | Application applies proper retry/backoff and error handling |
| Mismatched serialization | Detects keys/slots no longer matching expectations |

Do not run Redis Cluster benchmarks in production to test these rules; a dedicated integration test or staging cluster resembling production topology is much better.

### 21.3. Do not automatically catch and retry every cross-slot error

A sound retry policy classifies exceptions:

~~~text
CROSSSLOT from bad schema          -> fail fast, alert to fix data model
MOVED/ASK                          -> cluster-aware client handles routing
TRYAGAIN or transient I/O          -> bounded retry/backoff if operation is safe
Timeout of non-idempotent command  -> check state/idempotency first
~~~

For `CROSSSLOT` caused by fixed key placement, adding retries only increases error traffic and latency.

## 22. Performance and load distribution after fixing CROSSSLOT

Fixing `CROSSSLOT` only addresses validity. A good key schema also evaluates:

- Slot distribution across primary nodes.
- Data/CPU concentration on a group of hash tags.
- Per-aggregate read/write workload.
- Batch sizes and network round trips.
- Whether multi-key operations cause lock contention or long execution times.
- Cost of copying/reshaping the data model.
- Scalability when adding primary nodes.

### 22.1. Overly broad hash tags

If every key shares `{global}`, the Cluster logically puts them all in the same slot. The system has multiple nodes yet cannot leverage distribution for that key group.

### 22.2. Overly narrow hash tags

If a transaction needs three keys whose tags differ, Redis returns `CROSSSLOT`. Pick co-location boundaries matching business invariants.

### 22.3. Co-location does not automatically make commands faster

Sharing a slot makes the command valid; performance still depends on payload size, command complexity, and node load. An `MGET` returning thousands of large values can cause network spikes and tail latency. Cap batch sizes and watch P95/P99 latency and Redis memory.

### 22.4. Self-scattering multi-key APIs can alter latency

A high-level API that splits work into multiple per-slot requests incurs extra round trips and introduces partial errors. When profiling performance, verify whether your code executes one native command or merges multiple sub-requests.

## 23. Frequently asked questions

**Q1. Does Redis Cluster forbid `MGET`?**

No. `MGET` works when keys belong to the same hash slot. If they span different slots, the native command fails with `CROSSSLOT`.

**Q2. If two keys reside on the same Redis node, is `MGET` guaranteed to work?**

No. Redis Cluster checks **hash slots**, not just the current node. Two different slots can live on the same node and still be invalid in a native multi-key command.

**Q3. Does passing `-c` to `redis-cli` fix `CROSSSLOT`?**

No. `-c` follows redirections like MOVED/ASK; it does not change slot placement.

**Q4. Why does using the same `user:` prefix still fail?**

Plain prefixes do not control slot grouping. Use a shared hash tag, such as `user:{101}:profile` and `user:{101}:settings`.

**Q5. Can I add hash tags to existing keys without migrating data?**

Changing a key name changes the Redis key; old data does not automatically appear under the new name. You need migration, dual-read/backfill, or cache rebuilding from the source of truth.

**Q6. Does a hash tag automatically make two SET commands atomic?**

No. It only puts both keys in the same slot. Use a single command with proper semantics, a transaction, or Lua to guard multi-step updates.

**Q7. Does Spring's `multiGet` always throw `CROSSSLOT` on cross-slot keys?**

Do not assert that for all drivers and versions. Some client APIs may scatter/gather; check your implementation. If native MGET is used, slot constraints still apply and there is no cross-slot atomicity.

**Q8. Can a Lua script run an atomic transaction across two slots?**

Not in standard Redis Cluster. Scripts run on a single shard and accessed keys must obey cluster key-slot rules.

**Q9. Can `HSET` writing multiple fields trigger `CROSSSLOT`?**

No, because fields of a Redis Hash belong to **one Redis key**. There is only one key argument in `HSET`.

**Q10. Will adding more Redis nodes fix `CROSSSLOT`?**

No. The error stems from a command referencing keys in different slots; adding nodes does not change keys' hash slots.

**Q11. Can sharing hash tags reduce scalability?**

Yes. All keys sharing a tag land in one slot, creating a hotspot if that group grows too large or hot. Co-locate only keys that genuinely need atomic multi-key operations.

**Q12. Does Redis Repository automatically avoid all `CROSSSLOT` errors?**

Never assume so. Repositories can generate internal keys/indexes/metadata; verify support and data modeling for your Spring Data Redis version.

**Q13. When should I use multiple GETs instead of MGET?**

When keys are independent, span different slots, and do not require an atomic snapshot. You can use cluster-aware parallel fetching with bounded concurrency.

**Q14. When should I use a Redis Hash instead of multiple String keys?**

When fields belong to the same aggregate, share lifecycles, are usually read/updated together, and do not require independent TTLs.

**Q15. Can `CROSSSLOT` be caused by a serializer?**

Possibly. Redis hashes the **actual key bytes**. If a serializer alters bytes or hash tags, key placement deviates from expectations. Prefer `StringRedisSerializer` and an explicit key schema when using tags.

**Q16. Do `MULTI`/`EXEC` transactions roll back SQL-style if one command errors?**

No. Redis transactions provide non-interleaved atomic execution semantics, yet do not automatically roll back earlier successful commands when a later command hits a runtime error.

## 24. Checklist before deploying multi-key operations on a Cluster

1. **Identify key arguments** for every command rather than counting total parameters.
2. **Measure hash slots** with `CLUSTER KEYSLOT` using the actual key bytes.
3. **Decide whether atomicity is required** across those keys.
4. **Choose hash tags** scoped to the smallest aggregate genuinely needing co-location.
5. **Avoid global tags** that create hot slots.
6. **Verify the key serializer** when using Spring Data Redis.
7. **Ensure the Spring driver is cluster-aware** with suitable topology refresh settings.
8. **Distinguish native multi-key commands** from client scatter/gather.
9. **Do not confuse pipelining/parallelism** with transactions.
10. **For WATCH/MULTI/EXEC/Lua**, ensure all involved keys meet slot constraints.
11. **For Repositories**, inspect generated keyspaces, indexes, TTLs, and commands.
12. **For legacy keys**, plan migration instead of changing prefixes and expecting Redis to move data.
13. **Test against a real Redis Cluster**, not only standalone.
14. **Classify CROSSSLOT/MOVED/ASK/TRYAGAIN** before retrying.
15. **Measure load distribution** and hotspots after grouping keys.
16. **Design idempotency** for operations that can succeed even when the client loses the reply.
17. **Never substitute a multi-slot cache** for a transactional source of truth when strict correctness is mandatory.

## 25. Summary

**CROSSSLOT reports that a single command references multiple Redis keys that do not belong to the same hash slot.** Redis Cluster uses 16,384 slots computed via `CRC16(key bytes) % 16384` and supports `{hash-tag}` to co-locate related keys.

In Spring Data Redis, distinguish the Java API from the underlying Redis commands. Some high-level methods distribute multiple operations across slots, yet that does not make native `MGET`/`MULTI`/`EVAL` atomic across the Cluster. Neither `-c`, MOVED/ASK routing, pipelining, nor `ReactiveRedisTemplate` removes slot constraints.

Three main paths:

- **Need native multi-key or atomic grouping:** design a shared hash tag per aggregate and use the appropriate Redis command/transaction/Lua.
- **Independent keys:** issue separate commands, or use client scatter/gather with bounded concurrency while accepting no atomicity.
- **Complex business boundaries:** consider a single Redis Hash, a transactional source-of-truth model, or an explicit eventual consistency protocol.

Final rule of thumb: **put keys that genuinely must stay consistent together into the same slot, without forcing the entire system into one slot just to avoid errors.** Proper hash tags preserve command validity while keeping Redis Cluster's ability to distribute load.

## References

- Redis — [Redis Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/): 16,384 hash slots, CRC16, hash tags, routing, MOVED/ASK, and multi-key restrictions.
- Redis — [Redis Cluster tutorial](https://redis.io/docs/latest/operate/oss_and_stack/management/scaling/): topology, slot mapping, and operating Redis Cluster.
- Redis — [CLUSTER KEYSLOT](https://redis.io/docs/latest/commands/cluster-keyslot/): calculating a slot from a key name.
- Redis — [MGET](https://redis.io/docs/latest/commands/mget/): reading multiple String keys.
- Redis — [MSET](https://redis.io/docs/latest/commands/mset/): writing multiple String keys and semantics.
- Redis — [Redis transactions](https://redis.io/docs/latest/develop/interact/transactions/): MULTI/EXEC, WATCH, and rollback limitations.
- Redis — [Redis scripting](https://redis.io/docs/latest/develop/programmability/eval-intro/): EVAL, KEYS/ARGV, and atomic server-side logic.
- Spring Data Redis — [Redis Cluster](https://docs.spring.io/spring-data/redis/reference/redis/cluster.html): Cluster configuration, slot operations, and cluster-aware APIs.
- Spring Data Redis — [RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html): template methods, serializers, and connection handling.
- Spring Data Redis — [Redis Transactions](https://docs.spring.io/spring-data/redis/reference/redis/transactions.html): SessionCallback and transaction semantics.
