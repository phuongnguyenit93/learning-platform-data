# Multi-Key Command Limitations When Running on Cluster

A Redis Set is a useful data structure for storing unique sets of elements: users belonging to a group, access permissions, eligible product codes, or sets of record IDs. In Spring Data Redis, the `SetOperations` API makes it easy to work with commands such as `SADD`, `SINTER`, `SUNION`, `SDIFF`, and `SMOVE`.

When Redis runs in **standalone** mode, many operations across different Sets can execute on the same server. When deployed on **Redis Cluster**, however, these keys are distributed across multiple **hash slots**, which may live on different primaries. Redis cannot arbitrarily run a single command to compute union, intersection, difference, or move elements across multiple slots as if all data lived in one place.

For Spring Data Redis, two distinct layers must be understood clearly:

1. **Server-side Redis command limits:** most Set commands taking multiple Redis keys require all keys to belong to **the same hash slot**.
2. **Client/framework behavior:** some cross-slot operations may be emulated by the driver or Spring Data Redis using multiple single-key commands and aggregated in Java. This differs from an atomic command on the Redis server, carries its own costs and limitations, and is not supported for every operation.

This lesson focuses on distinguishing those two layers, designing key names with **hash tags**, inspecting `CROSSSLOT` errors, and choosing the right strategy when a problem truly requires aggregating data across multiple shards.

> **Context:** Java examples use Spring Boot 3.3.x, Spring Data Redis 3.3.x, and Lettuce. Automatic cross-slot handling can vary across drivers, versions, and invocation modes, especially inside pipelines/transactions. Never treat a Java API call succeeding as proof that Redis executed an atomic multi-key command on the server.

## 1. Distinguishing "Multiple Elements" from "Multiple Keys"

This is the first distinction to clarify. One Redis Set is **one Redis key** holding many members:

~~~redis
SADD shop:42:favorite-products p1 p2 p3
SMEMBERS shop:42:favorite-products
SISMEMBER shop:42:favorite-products p2
SCARD shop:42:favorite-products
~~~

`SADD` here takes multiple **members**, yet operates on only **one Redis key**, `shop:42:favorite-products`. Redis Cluster can route the entire command to the slot owning that key; having three members does not turn it into a cross-slot command.

By contrast:

~~~redis
SINTER shop:42:favorite-products shop:42:in-stock-products
~~~

`SINTER` takes **two Redis keys**. Even though both have type SET, the cluster must determine whether both can be handled in the same hash slot.

| Command | Redis Keys Involved | Role |
|---|---:|---|
| `SADD key member [member ...]` | 1 | Add multiple members to one Set |
| `SREM key member [member ...]` | 1 | Remove multiple members from one Set |
| `SMEMBERS key`, `SSCAN key cursor` | 1 | Read/scan members of one Set |
| `SISMEMBER key member`, `SMISMEMBER key member ...` | 1 | Check membership |
| `SINTER key1 key2 ...` | 1 or more | Intersection of Sets |
| `SUNION key1 key2 ...` | 1 or more | Union of Sets |
| `SDIFF key1 key2 ...` | 1 or more | Difference of first Set minus remaining Sets |
| `SMOVE source destination member` | 2 | Move one member between two Sets |
| `SINTERSTORE destination key1 key2 ...` | Multiple keys including destination | Compute intersection and write result into destination Set |

**Member count is not the slot partitioning criterion.** Redis Cluster hashes the *key* name for routing. The number of keys accessed by a command determines whether multi-key restrictions apply.

## 2. Redis Cluster Partitions Keys into 16,384 Hash Slots

Redis Cluster divides the keyspace into **16,384 hash slots**, numbered from 0 to 16383. Each primary owns a subset of slots. For ordinary keys, the slot is computed roughly as:

~~~text
slot = CRC16(keyBytes) mod 16384
~~~

The important exception is a **hash tag** enclosed in curly braces, explained in detail later.

Conceptual diagram:

~~~mermaid
flowchart TD
    A["Spring Data Redis Application"] --> B["Cluster-aware Lettuce driver"]
    B --> S{"Key's hash slot"}
    S -->|slot in group A| P1["Primary A"]
    S -->|slot in group B| P2["Primary B"]
    S -->|slot in group C| P3["Primary C"]
    P1 --> K1["Set A"]
    P2 --> K2["Set B"]
    P3 --> K3["Set C"]
~~~

If two Sets belong to two different slots, **you cannot send a single server-side `SINTER`** directly across both keys in Redis Open Source Cluster, even if by coincidence both slots happen to be managed by the same node. The condition is **same slot**, not merely "same IP" or "same primary".

To illustrate the limit, consider an example on Redis Cluster:

~~~redis
SADD cohort:active u1 u2 u3
SADD cohort:paid u2 u3 u4
SINTER cohort:active cohort:paid
~~~

The two keys lack a shared hash tag, so they are **not guaranteed** to share a slot. If in reality they land in different slots and `SINTER` is sent directly to the server, Redis returns an error like:

~~~text
(error) CROSSSLOT Keys in request don't hash to the same slot
~~~

Two arbitrary keys can occasionally land in the same slot due to hash collision; therefore, **check actual slots** rather than judging solely by looking at key names.

### 2.1. Using `CLUSTER KEYSLOT` to Check a Key's Slot

When connected to a Redis Cluster in a test environment:

~~~bash
redis-cli -c -h 127.0.0.1 -p 7000 CLUSTER KEYSLOT cohort:active
redis-cli -c -h 127.0.0.1 -p 7000 CLUSTER KEYSLOT cohort:paid
~~~

Both commands return actual slot numbers. If the slot numbers differ, a direct `SINTER cohort:active cohort:paid` command on the cluster cannot run as a single server-side command.

Here `-c` allows `redis-cli` to follow `MOVED`/`ASK` redirections when needed. **`-c` does not make a `CROSSSLOT` command valid** and does not pull two keys into the same slot.

`CLUSTER KEYSLOT` computes slots from **key name bytes**. If your Java application uses a serializer that produces bytes different from what you type in the CLI, the real key's slot may differ. `StringRedisTemplate` with consistent string serialization makes cross-checking between Java and CLI straightforward.

## 3. Which Multi-Key Set Commands Are Subject to This Limit?

Key set operations:

~~~text
A = {u1, u2, u3}
B = {u2, u3, u4}

A ∩ B = {u2, u3}           SINTER
A ∪ B = {u1, u2, u3, u4}   SUNION
A - B = {u1}               SDIFF A B
B - A = {u4}               SDIFF B A
~~~

In Redis Cluster, **every key participating in a single multi-key Set command must reside in the same hash slot** for the Redis server to execute that command.

| Redis Command | Characteristics | Keys Required to Share a Slot for Server-Side Execution |
|---|---|---|
| `SINTER key1 key2 ...` | Returns intersection of sets | All source keys |
| `SUNION key1 key2 ...` | Returns union of sets | All source keys |
| `SDIFF key1 key2 ...` | Returns difference; source order matters | All source keys |
| `SINTERCARD numkeys key1 ... [LIMIT n]` | Returns intersection cardinality; Redis 7.0+ | All source keys |
| `SINTERSTORE dest key1 key2 ...` | Writes intersection to `dest` | **Destination and all source keys** |
| `SUNIONSTORE dest key1 key2 ...` | Writes union to `dest` | **Destination and all source keys** |
| `SDIFFSTORE dest key1 key2 ...` | Writes difference to `dest` | **Destination and all source keys** |
| `SMOVE source dest member` | Moves member from source to destination | Both `source` and `dest` |

With `*STORE` commands, a common mistake is putting only source keys in the same slot while placing `destination` in another keyspace. **Destination is also a Redis key in the same command**, so it must share the slot for single-command server-side execution.

Example of a slot-unsafe command:

~~~redis
SINTERSTORE campaign:result shop:{42}:active shop:{42}:paid
~~~

Both sources share hash tag `42`, but `campaign:result` lacks that tag. For a valid server-side command, give the destination the same tag:

~~~redis
SINTERSTORE shop:{42}:campaign-result shop:{42}:active shop:{42}:paid
~~~

`SMOVE` is no exception: `source` and `destination` must share a slot if moving the member needs to execute atomically on the Redis server.

### 3.1. Why Does Redis Enforce This Limitation?

A single `SINTER` on one Redis server can read both Sets, compute the intersection, and return the result. In Cluster, if two keys sit on different primaries, neither primary holds all the data to compute the intersection. Redis Open Source Cluster does not run distributed transactions or fan out a Set command across shards with consensus.

This is a design trade-off tied to scalability and distributed complexity:

- **One slot:** the server owning the slot handles the command under standard Redis execution semantics.
- **Multiple slots:** the application must redesign its key layout, or accept multiple independent operations aggregated client-side.
- **Multi-key transactions/writes:** splitting across multiple commands/primaries sacrifices single-command atomicity.

Redis can rebalance slots across primaries when nodes are added or removed. However, **changing which primary owns a slot never changes a key's slot number**, because slot numbers are derived solely from the key name.

## 4. Hash Tags: Keeping Related Sets in the Same Slot

Redis Cluster supports the hash tag rule: if a key name contains a valid non-empty substring inside curly braces, only that substring is hashed to determine the slot instead of the full key.

Example:

~~~text
shop:{42}:active-customers
shop:{42}:paid-customers
shop:{42}:eligible-customers
shop:{42}:campaign-result
~~~

These four keys share hash tag `42`, so they are **guaranteed to land in the same hash slot** in Redis Cluster under standard hash tag rules, even though the rest of their names differ.

### 4.1. Complete CLI Example

~~~redis
SADD shop:{42}:active-customers u1 u2 u3
SADD shop:{42}:paid-customers u2 u3 u4

SINTER shop:{42}:active-customers shop:{42}:paid-customers
SUNION shop:{42}:active-customers shop:{42}:paid-customers
SDIFF shop:{42}:active-customers shop:{42}:paid-customers

SINTERSTORE shop:{42}:campaign-result shop:{42}:active-customers shop:{42}:paid-customers
SMEMBERS shop:{42}:campaign-result
~~~

Logical set results:

- Intersection: `{u2, u3}`.
- Union: `{u1, u2, u3, u4}`.
- Difference `active - paid`: `{u1}`.
- Destination `campaign-result`: holds intersection `{u2, u3}`.

Redis Sets do not preserve element order, so display order in `SMEMBERS`, `SINTER`, or `SUNION` is not part of the result contract. Do not write code depending on default Set ordering.

To verify same-slot placement:

~~~bash
redis-cli -c -h 127.0.0.1 -p 7000 CLUSTER KEYSLOT 'shop:{42}:active-customers'
redis-cli -c -h 127.0.0.1 -p 7000 CLUSTER KEYSLOT 'shop:{42}:paid-customers'
redis-cli -c -h 127.0.0.1 -p 7000 CLUSTER KEYSLOT 'shop:{42}:campaign-result'
~~~

All three replies must return the same slot number when Redis uses the standard Redis Cluster hashing algorithm.

### 4.2. Hash Tags Have Specific Syntax Rules

Sample key names:

| Key | Hashed Substring |
|---|---|
| `shop:{42}:active` | `42` |
| `shop:{42}:paid` | `42` |
| `shop:{43}:active` | `43` |
| `shop:{}:active` | Full key name because the first braces are empty |
| `shop:42:active` | Full key name because there is no hash tag |
| `shop:{42}:active:{other}` | First valid tag substring, i.e., `42` |

Do not assume every pair of braces in a key name behaves as you might guess. The rule keys off **the first matching curly-brace pair**. An empty tag produces no slot-pinning effect.

Place curly braces in the **key name**, not inside Set values or members. For instance:

~~~redis
SADD shop:active "{42}"
~~~

does not route key `shop:active` to tag `42`'s slot, because `{42}` here is a **member**, not the Redis key name.

### 4.3. What Should You Choose as the Hash Tag?

Choose **the data unit that needs multi-key commands executed together**:

| Data Group | Sample Keys | What Gets Co-Located |
|---|---|---|
| Sets for one shop | `shop:{42}:active`, `shop:{42}:paid` | Sets of shop 42 |
| Permissions for one user | `user:{u123}:roles`, `user:{u123}:permissions` | Sets of user u123 |
| Versions of one batch | `batch:{run-77}:before`, `batch:{run-77}:after` | Sets of the same batch |
| Data of one small tenant | `tenant:{acme}:group-a`, `tenant:{acme}:group-b` | Sets of tenant acme |

What matters is not where `{ }` looks tidy, but answering: **which keys actually need to participate together in a multi-key Set command?**

## 5. Overly Broad Hash Tags Can Break Load Balancing

A dangerous "fix" for `CROSSSLOT` is putting one shared tag on every key:

~~~text
{all}:shop:42:active
{all}:shop:57:active
{all}:shop:92:active
{all}:global:campaign
~~~

Every key tagged `{all}` is routed to **the exact same hash slot**. Redis Cluster assigns each slot to only one primary at a time, so huge keys and high traffic pile onto a single primary.

Potential consequences:

- Memory and CPU concentrate on a single node.
- One oversized keyspace degrades overall latency.
- Adding more primaries fails to scale that workload.
- During slot migration, migration pressure rises and multi-key commands may experience brief disruptions.

Hash tags solve **same-slot co-location**, not capacity, throughput, or availability limits.

### 5.1. "Pinning by Tenant" Also Has Trade-Offs

If each tenant has few keys and frequent multi-key queries, pinning by tenant can make sense. However, one giant tenant will still funnel all its keys into a single slot.

For huge tenants, consider finer partitioning—such as by tenant + entity group or business partition—and accept that certain tenant-wide set operations must be computed in multiple steps.

The right choice depends on:

1. Key count and total RAM per tag.
2. Requests/sec and Set operation complexity.
3. How often multi-key intersection/union/difference is truly needed.
4. Result sizes and member counts.
5. Whether global computations can be moved off the hot request path.

You cannot simultaneously force every key cluster-wide into one slot and expect Cluster to distribute those keys evenly across primaries.

## 6. How Spring Data Redis Represents Set Operations

Spring Data Redis exposes `SetOperations<K, V>`, typically via:

~~~java
SetOperations<String, String> sets = stringRedisTemplate.opsForSet();
~~~

Corresponding APIs:

| Spring Data Redis | Redis Meaning |
|---|---|
| `sets.add(key, members...)` | `SADD` |
| `sets.members(key)` | `SMEMBERS` |
| `sets.intersect(keyA, keyB)` | `SINTER` or equivalent connection mechanism |
| `sets.union(keyA, keyB)` | `SUNION` or equivalent connection mechanism |
| `sets.difference(keyA, keyB)` | `SDIFF` or equivalent connection mechanism |
| `sets.intersectAndStore(keyA, keyB, destination)` | `SINTERSTORE` or corresponding handling |
| `sets.unionAndStore(keyA, keyB, destination)` | `SUNIONSTORE` or corresponding handling |
| `sets.differenceAndStore(keyA, keyB, destination)` | `SDIFFSTORE` or corresponding handling |
| `sets.move(source, value, destination)` | `SMOVE` or corresponding handling |

The phrase "or equivalent mechanism" is crucial: the high-level API does not guarantee every call sends **exactly one Redis command**. In Redis Cluster environments, some results may be fulfilled by Spring Data Redis or the driver issuing multiple commands and aggregating client-side. This depends on the method, connection implementation, version, and pipeline/transaction mode.

### 6.1. Configuring Spring Boot for Redis Cluster

With Boot 3.x:

~~~yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - redis-node-1.internal:6379
          - redis-node-2.internal:6379
          - redis-node-3.internal:6379
      connect-timeout: 2s
      timeout: 3s
~~~

These hostnames are examples; they must exist in your deployment environment. The node list provides initial seed endpoints for the driver to discover Cluster topology. A normal standalone Redis instance does not become a Cluster just because a client lists multiple nodes.

Redis Cluster only supports logical database 0, so do not rely on `spring.data.redis.database: 2` to separate datasets when moving to Cluster.

With `spring-boot-starter-data-redis`, Lettuce is typically the default driver and supports Cluster connections. The driver automatically handling `MOVED` and `ASK` redirections for single keys **does not mean** it turns cross-slot multi-key commands into valid server-side commands.

### 6.2. Example Service Putting Keys in the Same Slot

~~~java
import java.util.Objects;
import java.util.Set;

import org.springframework.data.redis.core.SetOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ShopEligibilityService {

    private final SetOperations<String, String> sets;

    public ShopEligibilityService(StringRedisTemplate redis) {
        this.sets = redis.opsForSet();
    }

    private String key(String shopId, String suffix) {
        return "shop:{" + shopId + "}:" + suffix;
    }

    public void markActive(String shopId, String userId) {
        sets.add(key(shopId, "active"), userId);
    }

    public void markPaid(String shopId, String userId) {
        sets.add(key(shopId, "paid"), userId);
    }

    public Set<String> findEligible(String shopId) {
        Set<String> result = sets.intersect(
                key(shopId, "active"),
                key(shopId, "paid")
        );

        // Example assumes direct synchronous call outside pipeline/transaction.
        // SetOperations may return null when commands are queued in a
        // pipeline/transaction; do not treat temporary null as an empty Set.
        return Objects.requireNonNull(
                result,
                "Expected direct Redis Set result"
        );
    }

    public Long storeEligible(String shopId) {
        return sets.intersectAndStore(
                key(shopId, "active"),
                key(shopId, "paid"),
                key(shopId, "eligible")
        );
    }
}
~~~

Every key belonging to **the same `shopId`** shares the same tag and thus the same slot. Different shops can still distribute across different slots.

The snippet assumes `shopId` is a validated identifier containing no curly braces that would alter hash tag parsing. For user-supplied data, sanitize/validate ID formats before constructing key names.

`storeEligible` returns the element count written according to API semantics on direct successful calls. Inside a pipeline/transaction, some `RedisTemplate` methods return `null` temporarily because responses have not been collected yet; read results from the post-execution result list.

### 6.3. Serializers Also Affect Hash Slots

Redis computes slots from **the actual serialized key bytes**, not from the Java string prior to serialization.

If one service uses `StringRedisSerializer` for Redis keys while another uses JDK serialization or a JSON serializer for key names, they can transmit two distinct byte-level names even for the same Java input `"shop:{42}:active"`.

Therefore:

- Standardize `keySerializer` across every code path.
- For text-based key names, `StringRedisTemplate` or `StringRedisSerializer` is easiest to reason about.
- Do not assume the original string has an effective tag if the serializer alters its bytes.
- Verify actual slots whenever changing key formats.

The **Set member** serializer affects member values and cross-Set equality; the **Redis key** serializer directly determines the hash slot.

## 7. Cross-Slot in Spring Data Redis: Can It Compute Client-Side?

Avoid oversimplifying to "every `SetOperations.intersect()` call in Cluster always throws `CROSSSLOT`". Cluster-aware implementations in Spring Data Redis handle certain cross-slot operations by reading individual keys and combining them on the client side.

Spring Data Redis documentation notes, for instance, that cross-slot `MGET` can be split into single `GET` commands; for some Set intersections/unions, Spring Data Redis may also fall back to **client-side computation** when keys do not share a slot. Still, other operations cannot be safely decomposed into single-key commands and will fail.

Distinguish carefully:

| Case | What to Understand |
|---|---|
| Sending `SINTER keyA keyB` directly to Redis Cluster server across slots | Redis server returns `CROSSSLOT` |
| Calling cluster-aware Spring Data Redis APIs | Some operations may be emulated client-side; check exact implementation and version |
| Calling the same API when both keys share a slot | Can use direct server-side Set commands |
| Combining multiple slots via multiple Java commands | No cluster-wide snapshot/atomicity by default |
| Combining inside a Redis Cluster pipeline | Additional support restrictions apply depending on driver and operation |

**Never build business correctness on assumptions about fallback behavior.** Know explicitly whether an operation executes on the server or client, how much data crosses the network, and how concurrent updates affect results.

### 7.1. Client-Side Cross-Slot Can Consume Heavy RAM

Suppose two Sets live in two slots:

~~~text
segment:{east}:customers  → 1,500,000 IDs
segment:{west}:customers  → 1,200,000 IDs
~~~

If union/intersection runs client-side by reading all members of each Set, the application may pull millions of elements over the network and retain them in the JVM heap before returning a result.

Consequences:

- Network throughput spikes significantly.
- Redis nodes serialize/send huge payloads; the client deserializes massive numbers of members.
- JVM heap pressure and GC spike.
- Latency is dominated by the largest Set and the slowest network path.
- The final result itself may be too large for a REST response or downstream consumer.

An intersection returning just a handful of IDs can still pay the cost of reading massive datasets to find them. Thus, small **output** size does not imply small **computation** cost.

### 7.2. Multi-Step Client-Side Reads Have No Atomic Snapshot

Suppose:

~~~text
Time           Read Request                     Other Request
t1             Read Set A
t2                                              SADD A u9
t3                                              SREM B u9
t4             Read Set B
t5             Compute A ∩ B in Java
~~~

The two Sets are read at different times. The result computed in Java may not reflect a consistent point-in-time state of both Sets. Even though each `SMEMBERS` call runs atomically in Redis, the full **read A → read B → compute** sequence is not a distributed transaction.

If the use case is product recommendations, search caching, or approximate analytics, eventual consistency may be fine. If it decides access control, fund transfers, or inventory counts, establish explicit consistency guarantees and an authoritative data source.

### 7.3. Do Not Confuse Client Fallback with Transactions

A single same-slot server command and a cross-slot client command sequence have very different properties:

| Property | Single Same-Slot Server Command | Multi-Command Cross-Slot Client Path |
|---|---|---|
| Where union/intersection runs | Redis server | Java or driver |
| Round trips | Can be a single command | Multiple commands/round trips |
| Result snapshot at command execution | Under single Redis command semantics | No cross-shard snapshot by default |
| Member data transfer cost | Typically transmits only the result | May have to download source sets |
| Atomicity when writing destination | Commands like `SINTERSTORE` per same-slot Redis semantics | Must design destination update separately |
| Usable in transactions/pipelines | Under same-slot Redis semantics | Restricted and may be unsupported |

**If an atomic multi-Set operation is required on Redis Cluster, co-locate related keys in the same slot from the beginning.**

## 8. Computing Intersection/Union/Difference in Java When Sets Are Small

Sometimes key layout cannot be changed: one Set holds active users from region A and another holds members from region B, each on a different shard. If the Sets are **small, strictly bounded in size**, and the business tolerates reading at slightly different instants, the application can fetch each Set and compute in Java.

The example below is strictly for datasets bounded upfront by architecture:

~~~java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class SmallSetAggregationService {

    private final StringRedisTemplate redis;

    public SmallSetAggregationService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Set<String> intersectAcrossKeys(
            String firstKey,
            String secondKey
    ) {
        // Each members() call accesses only one Redis key,
        // so a cluster-aware driver can route each key independently.
        Set<String> first = Objects.requireNonNull(
                redis.opsForSet().members(firstKey),
                "Expected direct result for first Set"
        );

        Set<String> second = Objects.requireNonNull(
                redis.opsForSet().members(secondKey),
                "Expected direct result for second Set"
        );

        Set<String> result = new HashSet<>(first);
        result.retainAll(second);
        return result;
    }

    public Set<String> unionAcrossKeys(
            String firstKey,
            String secondKey
    ) {
        Set<String> first = Objects.requireNonNull(
                redis.opsForSet().members(firstKey)
        );
        Set<String> second = Objects.requireNonNull(
                redis.opsForSet().members(secondKey)
        );

        Set<String> result = new HashSet<>(first);
        result.addAll(second);
        return result;
    }

    public Set<String> differenceAcrossKeys(
            String firstKey,
            String secondKey
    ) {
        Set<String> first = Objects.requireNonNull(
                redis.opsForSet().members(firstKey)
        );
        Set<String> second = Objects.requireNonNull(
                redis.opsForSet().members(secondKey)
        );

        Set<String> result = new HashSet<>(first);
        result.removeAll(second);
        return result;
    }
}
~~~

This example uses `HashSet` to mirror set semantics; element order is not guaranteed. `differenceAcrossKeys(A, B)` differs from `differenceAcrossKeys(B, A)`.

In Redis, `SMEMBERS` on an absent key returns an empty set, yet Spring Data Redis can return `null` when commands are queued in a pipeline/transaction. Therefore the code explicitly demands **direct results**; do not mix these methods into a pipeline callback while expecting immediate Sets.

Limits to state clearly before adopting this approach:

- **Use only for small Sets with a hard architectural size limit.** Do not wait until after `SMEMBERS` to check size; by then huge data is already on the heap.
- Two reads do not form an atomically consistent snapshot.
- There is no atomic write-back to Redis like same-slot `SINTERSTORE`.
- All clients must share the same member serializer/encoding so Java's `Set.contains` matches Redis member identity.
- Timeouts, rate limits, pagination, or an alternative query design may be needed for larger sets.

This is an **application-level trade-off**, not a way to "unlock cross-slot freely" on the Redis server.

### 8.1. For Large Sets, Never Use Unbounded `SMEMBERS`

`SMEMBERS` returns every member. For very large Sets, application-level options include:

- Redesigning key layout so critical computations run server-side in a single slot.
- Reading the smaller set and checking membership in the other Set via single-key commands, if cost is acceptable.
- Using `SSCAN` to process incrementally in batch jobs, recognizing that SCAN neither gives a consistent snapshot under concurrent writes nor prevents duplicates.
- Building a **materialized set/read model** from events or the primary data source, updated along business workflows.
- Moving complex union/intersection queries over massive data into a system with an appropriate query/indexing model.

If strict point-in-time accuracy is required over rapidly mutating data across shards, merely switching from `SMEMBERS` to `SSCAN` will not solve consistency requirements.

## 9. Special Care with Cross-Slot `*STORE` and `SMOVE`

### 9.1. Destination Is Not an Ignorable Auxiliary Key

`SINTERSTORE`, `SUNIONSTORE`, and `SDIFFSTORE` read source sets and write the result into a destination set. The destination can be completely overwritten with the computed result. Therefore, slot constraints apply to **the destination too**.

Proper hash-tag example:

~~~redis
SADD group:{42}:active u1 u2 u3
SADD group:{42}:paid u2 u3

SINTERSTORE group:{42}:eligible group:{42}:active group:{42}:paid
SMEMBERS group:{42}:eligible
~~~

If you rename the destination to `group:eligible:42`, you cannot assume the Redis server executes the command in one slot.

### 9.2. Client-Side Emulation of STORE Across Shards Is Non-Atomic

A client-side approach might look like:

~~~text
1. Read Set A from shard A
2. Read Set B from shard B
3. Compute A ∩ B in Java
4. Delete old destination
5. Write each member into new destination
~~~

This introduces failure windows:

- A period where the destination is empty or holds only partial results.
- Application crash after deleting destination but before finishing writes.
- Sources mutating while computing.
- Other clients observing intermediate destination state.
- Retries requiring idempotency and explicit result versioning.

When reading/writing across shards, a Redis transaction on one shard does not become a distributed transaction. If publishing an atomic snapshot **specifically within the destination slot** is required, you can write to a temporary versioned key in the destination's slot and atomically swap pointers or rename within that slot. Still, that **does not produce an atomic snapshot of cross-shard sources**; it only cleans up result publication.

### 9.3. `SMOVE` Mutates Two Sets

~~~redis
SMOVE group:{42}:waiting group:{42}:active u7
~~~

When both keys share a slot, Redis can move the member in one command. If source and destination sit in different slots, you cannot rely on a single server-side `SMOVE`.

Doing it manually:

~~~text
SREM source u7
SADD destination u7
~~~

consists of **two independent commands** with a failure window between them. If `SREM` succeeds and `SADD` fails, the member disappears from both Sets. Reversing the order can briefly place the member in both Sets simultaneously. If the transition represents critical business state, choose a data store with suitable transactions or design compensation/reconciliation.

## 10. Pipelines, Transactions, and Lua Also Obey Slot Rules

### 10.1. Pipelining Does Not Make a CROSSSLOT Command Valid

Pipelining reduces round-trip latency by sending multiple commands without waiting for each reply. It does not make a Redis server own data in another slot, and **never turns a cross-slot `SINTER A B` into a valid Redis command**.

Spring Data Redis documentation on Redis Cluster also notes specific limits for **cluster pipelining**: in documented versions, pipelining support is primarily via Lettuce, and cross-slot multi-key commands such as `sMove`, `sInter`, `sInterStore`, `sUnion`, `sUnionStore`, and `sDiff`, `sDiffStore` are unsupported in this mode. Therefore, never conclude from a normal call's client-side fallback that it will also work inside a pipeline.

### 10.2. `MULTI/EXEC` Cannot Span Multiple Slots Like a Distributed Transaction

A multi-key Redis Cluster transaction requires participating keys to share the same hash slot.

Conceptual example:

~~~redis
MULTI
SADD group:{42}:active u7
SREM group:{42}:waiting u7
EXEC
~~~

Both keys sharing tag `42` is the prerequisite for this transaction model to execute on the Redis server owning that slot. Conversely, if the second key sits in another slot, do not treat `MULTI/EXEC` as a workaround for `CROSSSLOT`.

When using Spring Data Redis `SessionCallback` or Spring-managed transaction support, you still must respect topology and slot constraints. Adding Spring's `@Transactional` does not create a distributed transaction across multiple Redis primaries or between Redis and a SQL database.

### 10.3. Lua/EVAL Must Also Co-Locate Keys

Lua scripts execute on the Redis server and are commonly used when multi-step logic needs server-side atomicity. Yet in Cluster, scripts accessing multiple keys must still satisfy slot rules.

Keys touched by the script must be properly declared via `KEYS`/command arguments, never smuggled inside scripts to access keys on other shards. Hash tags help group keys manipulated together in the same script.

When an existing Redis command already handles same-slot multi-Set operations, prefer that built-in command over writing a complex Lua script.

## 11. Redis Cluster Can Return Errors During Resharding Even When Keys Share a Slot

Sharing a hash tag is a **necessary design prerequisite**, not a guarantee that multi-key commands succeed under all conditions.

Redis Cluster can migrate slots across primaries during rebalancing/resharding. During migration:

- Single-key commands may receive `MOVED` or `ASK` redirects so the client reaches the right node.
- For multi-key operations on a migrating slot, if some keys have not yet moved or are absent on the target node and Redis cannot guarantee unified execution in one place, Redis can return `TRYAGAIN`.
- Once slot migration finishes, multi-key operations in that slot resume normally under cluster rules.

Distinguish these errors/events:

| Error / Event | Typical Meaning | How to Handle |
|---|---|---|
| `CROSSSLOT` | Keys in one command do not hash to the same slot | Fix key design or execution approach |
| `MOVED` | Slot is owned by another node | Cluster-aware driver updates routing |
| `ASK` | Temporary redirection during migration | Driver handles per cluster protocol |
| `TRYAGAIN` | Slot is migrating and multi-key command cannot run immediately | Bounded retry with appropriate backoff |
| Timeout / network error | Slow connection, node failure, or heavy load | Monitor topology, timeouts, retries, and cluster health |

**Infinite retries never fix `CROSSSLOT`**, because key names still hash to different slots. `TRYAGAIN` during resharding, however, can be a transient error suited to a bounded retry policy.

## 12. Designing Sets for Typical Queries

### Case A: Intersecting States Within One Store

Requirement: users must be both **active** and **paid** in shop 42.

~~~text
shop:{42}:active
shop:{42}:paid
shop:{42}:eligible
~~~

These Sets are queried together routinely, so tagging by shop makes sense. `SINTER` or `SINTERSTORE` can run in the same slot. This is a clear win for hash tags.

### Case B: Intersecting Two Huge Global Groups

Requirement: find IDs belonging to both global marketing group A and membership tier B system-wide.

If both Sets are massive, pinning all global marketing keys into one slot risks creating a hotspot. Instead, consider these data models:

- Partition sets intentionally, compute results per partition, and merge.
- Maintain an index/materialized result in an appropriate system.
- Use an authoritative data store with native querying, or a stream/batch architecture for large workloads.
- Define target latency and consistency before choosing how results are updated.

No key naming trick enables a single cluster-wide server-side `SINTER` while simultaneously spreading all source sets freely across multiple slots.

### Case C: Moving a Member Between Two States

Requirement: transition a user from `pending` to `approved`.

~~~text
approval:{tenant-42}:pending
approval:{tenant-42}:approved
~~~

Use the same tag so `SMOVE` runs in one command. If this represents critical business state stored across multiple systems, clearly define the authoritative source and failure synchronization.

### Case D: Access Permissions Requiring Strict Accuracy

If the rule is "user holds both role X and entitlement Y", clarify which store is authoritative and when permissions take effect. Intersecting cached Sets read at two different moments can produce security-incorrect answers.

You can organize Sets per user so related keys share a slot and apply changes in a controlled way, or place authorization decisions in a system whose consistency/transaction guarantees meet your security requirements. Using Sets alone does not make an eventually consistent dataset appropriate for every security decision.

## 13. Checklist for Reviewing a Set Query Before Cluster Deployment

Suppose a service calls:

~~~java
Set<String> result = redis.opsForSet()
        .intersect(firstKey, secondKey);
~~~

Before deploying to a multi-shard path, walk through these steps:

1. **Count actual Redis keys.** `intersect` uses at least two keys, whereas `add(key, a, b, c)` uses only one.
2. **Identify the Redis key serializer.** Slots depend on actual key bytes, not just Java strings.
3. **Check each key's slot.** Use `CLUSTER KEYSLOT` in a test environment.
4. **If an atomic server-side command is required, place all keys in the same slot.** For `*STORE`, remember to include the destination.
5. **Assess key-pinning scope.** How broad is the tag, and could one slot become a hotspot?
6. **If multiple slots must be handled, know who computes the result.** Spring Data Redis, the driver, or application code? Does the operation/version/pipeline support it?
7. **Measure Set sizes and network/heap costs.** Client-side fallback can be very expensive.
8. **State the consistency level.** Is an eventually consistent multi-step result acceptable, or must it reflect one instant?
9. **Design error handling and retries.** `CROSSSLOT` requires fixing structure, `TRYAGAIN` during resharding allows bounded retries, and multi-step write failures need reconciliation.

Decision flow:

~~~mermaid
flowchart TD
    A["Need Redis Set operations"] --> B{"One key or multiple keys?"}
    B -->|One key| C["Use SADD/SREM/SISMEMBER/SMEMBERS..."]
    B -->|Multiple keys| D{"All keys in same hash slot?"}
    D -->|Yes| E["Prefer server-side commands like SINTER/SUNION/SMOVE"]
    D -->|No| F{"Can key model be aligned to query unit?"}
    F -->|Yes| G["Design appropriate hash tag, watch for hotspots"]
    F -->|No| H{"Small Sets and no global snapshot needed?"}
    H -->|Yes| I["Explicitly bounded client-side aggregation"]
    H -->|No| J["Partitioned read model / another query system"]
~~~

## 14. Misconceptions to Avoid

**"Two keys on the same node are enough."** Redis Cluster requires the same **hash slot**, not simply residing on the same primary at a given moment.

**"`SADD` with multiple members is a multi-key command."** `SADD key a b c` still touches only one Redis key; this differs from `SINTER keyA keyB`.

**"Adding `redis-cli -c` or Lettuce automatically solves CROSSSLOT."** Cluster-aware clients handle routing and certain specialized operations, yet do not turn every multi-key command into an atomic cross-shard operation.

**"Spring Data Redis can never process cross-slot Sets."** Some calls can be computed client-side. Check the specific method/version/driver and accept the different cost, limits, and consistency compared to server-side commands.

**"Since `SINTER` only returns a few elements, fallback is always cheap."** To find a few intersecting elements, the application may still have to download huge source Sets.

**"Only source keys need the same slot."** With `*STORE`, destination is also a key in the command; with `SMOVE`, both source and destination need the same slot for a server-side command.

**"Putting every key under `{global}` is optimal."** That concentrates all load onto one slot and defeats cluster distribution.

**"Pipelines or MULTI/EXEC bypass multi-slot restrictions."** They serve different purposes. A Redis transaction or script is not a distributed transaction across multiple primaries.

**"Same tag means never failing."** Resharding can cause transient `TRYAGAIN` errors; infrastructure also faces timeouts and connection errors.

## 15. Principles to Apply in Spring Data Redis

- **Design keys around actual operations:** know which Sets must be intersected, unioned, diffed, or moved together.
- **Keep hash tags narrow enough:** co-locate groups needing atomic multi-key commands while letting unrelated groups spread out.
- **Use a consistent key serializer:** slot hashing depends on the transmitted key bytes.
- **Verify with `CLUSTER KEYSLOT`:** never guess from key names or which node currently owns a slot.
- **Distinguish Redis server commands from Spring Data Redis client fallbacks:** especially with cross-slot calls, pipelines, and transactions.
- **Never overlook destinations in `*STORE` and `SMOVE`.**
- **Bound Java-side aggregations:** use only when dataset sizes are controlled and business logic tolerates multiple read instants.
- **Never assume cluster-wide atomicity:** multi-shard mutations need explicit strategies for consistency, retries, idempotency, and reconciliation.
- **Measure load and monitor resharding:** hot-slot CPU/RAM, data transfer times, and `TRYAGAIN` replies all carry operational significance.

Redis Cluster scales keyspaces by partitioning data across multiple primaries. In exchange, **multi-key** Set commands can no longer operate freely across arbitrary keys as on a single Redis instance. Understanding **hash slots**, **hash tags**, **server/client boundaries**, and **atomicity** lets you write Spring Data Redis code that fits the topology, rather than discovering limits only after moving to Cluster.

## References

- [Redis — Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/)
- [Redis — Multi-key operations](https://redis.io/docs/latest/develop/using-commands/multi-key-operations/)
- [Redis — CROSSSLOT error](https://redis.io/docs/latest/develop/reference/errors/common/crossslot/)
- [Redis — Scaling with Redis Cluster](https://redis.io/docs/latest/operate/oss_and_stack/management/scaling/)
- [Redis — SINTER](https://redis.io/docs/latest/commands/sinter/)
- [Redis — SUNION](https://redis.io/docs/latest/commands/sunion/)
- [Redis — SDIFF](https://redis.io/docs/latest/commands/sdiff/)
- [Redis — SMOVE](https://redis.io/docs/latest/commands/smove/)
- [Spring Data Redis — Redis Cluster](https://docs.spring.io/spring-data/redis/reference/redis/cluster.html)
- [Spring Data Redis — Redis Repositories Running on a Cluster](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/cluster.html)
- [Spring Data Redis API — SetOperations](https://docs.spring.io/spring-data/redis/docs/3.3.x/api/org/springframework/data/redis/core/SetOperations.html)
