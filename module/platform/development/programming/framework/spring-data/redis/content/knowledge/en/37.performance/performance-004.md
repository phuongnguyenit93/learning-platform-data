# Controlling Value Size, Member Count, and Key Count in Spring Data Redis

Redis is usually very fast when operating on small data, but the performance of a Spring Data Redis application can degrade sharply if **a single value is too large**, **a collection contains too many elements**, or **the key count grows without bound**. These three problems have different symptoms and solutions: a `GET` returning several MB of JSON consumes network bandwidth and JVM memory; an `SMEMBERS` on a Set with millions of members can produce a huge response and block the application; and millions of small keys increase memory management overhead, keyspace scans, and recovery time.

This lesson focuses on how to **design limits at the data layer and application layer** when using `RedisTemplate`, `StringRedisTemplate`, `ReactiveRedisTemplate`, Spring Cache, or Redis Streams. Topics include measuring real Redis keys, comparing data model choices, restricting commands that return many elements, controlling growth, safe cleanup methods, and repeatable performance tests.

> **Principle:** There is no single maximum number suitable for every system. All thresholds in this lesson are **examples of application policies** that must be calibrated to RAM capacity, requests/second, latency SLOs, serializers, network, workload, and Redis version.

## 1. Three Growth Dimensions to Control Separately

Consider an e-commerce platform using these keys:

```text
product:100:detail             -> String containing JSON
product:100:viewers            -> Set of user IDs
ranking:daily                  -> Sorted Set
cart:42                        -> Hash
events:checkout               -> Stream
session:aaaaaaaa...            -> String with TTL
```

There are at least three size dimensions:

| Dimension | Example | Primary Risk |
|---|---|---|
| **Size of a single value** | 5 MB product JSON | Large responses, CPU-heavy serialization/deserialization, heap/GC, and bandwidth |
| **Number of members in a collection** | Set with 2 million user IDs, Hash with 300,000 fields | O(N) full-read commands, large responses, hot keys, expensive deletions |
| **Total number of Redis keys** | Every session/event creates a key without TTL | Per-key overhead, continuously growing RAM, persistence/replication/scan cost, and eviction |

A fourth dimension must be added: **access frequency**. A 500 KB key read tens of thousands of times per second can be worse than a 5 MB key rarely read. That is a **hot key** problem, not just a big key problem.

### 1.1. Distinguishing Big Keys and Hot Keys

```text
Big key:
  Large byte volume or member count
  -> RAM, network payload, O(N), deletion, serialization

Hot key:
  Operations/second concentrated on the same key/slot
  -> CPU/node bottleneck, contention, request queue

Big + hot:
  Many requests loading the same huge collection
  -> usually the most dangerous case
```

A Redis Cluster shards **keys** across hash slots, but it does not automatically split **a single giant key** across multiple primaries. Moving from Standalone to Cluster helps distribute millions of keys, yet one heavily hit Set still belongs to a single slot at any given time.

## 2. Why Does One Large Key Slow Down the Entire System?

The cost is not merely the bytes stored in Redis. A read command may traverse:

```text
Redis memory
    |
    v
Redis processes command and builds reply
    |
    v
Socket / network / TLS
    |
    v
Lettuce or Jedis receives bytes
    |
    v
Spring Data Redis deserializer
    |
    v
Java String / DTO / Collection
    |
    v
Business logic / JSON HTTP response
```

If a value is 2 MB of JSON, the application may create additional in-memory representations: receive byte arrays, Strings/JsonNodes, DTOs, HTTP response JSON, and I/O buffers. **2 MB stored in Redis does not mean the request uses only 2 MB of JVM RAM.**

Similarly, `HGETALL` on a 200,000-field Hash can allocate a huge Map, many small objects, GC pressure, and an enormous response. Do not judge a command solely by nominal Big-O complexity: **response size** and **decoding cost** also determine latency.

### 2.1. Four Places to Measure

1. **Redis RAM:** bytes/key, total memory, fragmentation, dataset size.
2. **Redis CPU/latency:** slow commands, large payloads, blocking operations, hot shards.
3. **Network:** bytes per response, bandwidth, TLS overhead, and round trips.
4. **Java application:** deserialization time, allocation rate, heap, GC, p95/p99 request latency.

Looking only at `INFO memory` misses many issues. For example, Redis may still have plenty of RAM while an HTTP request calling `SMEMBERS` times out transferring and decoding hundreds of thousands of elements.

## 3. Measuring Value Size and Member Count with Redis CLI

On a **test** Redis instance or with an observation account holding appropriate permissions, start with low-impact commands:

```bash
redis-cli -h 127.0.0.1 -p 6379 TYPE product:100:detail
redis-cli -h 127.0.0.1 -p 6379 STRLEN product:100:detail
redis-cli -h 127.0.0.1 -p 6379 MEMORY USAGE product:100:detail

redis-cli -h 127.0.0.1 -p 6379 HLEN cart:42
redis-cli -h 127.0.0.1 -p 6379 SCARD product:100:viewers
redis-cli -h 127.0.0.1 -p 6379 ZCARD ranking:daily
redis-cli -h 127.0.0.1 -p 6379 LLEN notifications:42
redis-cli -h 127.0.0.1 -p 6379 XLEN events:checkout
```

| Command | What Does It Measure? | What Does It Not Measure? |
|---|---|---|
| `STRLEN key` | Length of a Redis String value in **bytes** | Excludes key/allocator overhead |
| `HLEN key` | Number of fields in a Redis Hash | Not byte count inside the Hash |
| `SCARD key` | Number of members in a Redis Set | Not byte size or access frequency |
| `ZCARD key` | Number of members in a Sorted Set | Not byte size |
| `LLEN key` | Number of elements in a List | Not RAM usage |
| `XLEN key` | Number of entries remaining in a Stream | Not pending/ACK count or bytes/entry |
| `MEMORY USAGE key` | Estimated RAM Redis uses for key and value, including overhead | Excludes full network/JVM costs or total replication cost |
| `TYPE key` | Redis data type | Does not identify Java serializer/schema |

A Java String with Unicode characters does not necessarily have `String.length()` equal to Redis `STRLEN`. Redis measures **bytes**, not Java UTF-16 code units.

### 3.1. MEMORY USAGE and SAMPLES

```redis
MEMORY USAGE cart:42
MEMORY USAGE cart:42 SAMPLES 20
MEMORY USAGE cart:42 SAMPLES 0
```

For nested multi-element structures, Redis can **sample** elements to estimate size. By default it samples a few elements; `SAMPLES 0` scans all elements for a fuller estimate, at the cost of CPU on very large collections. Do not run `SAMPLES 0` in bulk on busy production instances without evaluating impact.

`MEMORY USAGE` reflects internal structures, overhead, and the allocator; the same payload byte count can consume different RAM across encodings, Redis versions, and system architectures. Do not substitute `STRLEN` for `MEMORY USAGE` when budgeting RAM.

### 3.2. Check Type Before Measuring

`STRLEN` only works for Redis Strings. If a key is a Hash, running `STRLEN` returns `WRONGTYPE`. Likewise, `HLEN` does not apply to Sets. An inventory tool should call `TYPE` or know the exact namespace/schema before selecting a cardinality command.

## 4. Total Key Count and Memory Consumption

Instance-level inspection commands:

```bash
redis-cli -h 127.0.0.1 -p 6379 INFO memory
redis-cli -h 127.0.0.1 -p 6379 INFO keyspace
redis-cli -h 127.0.0.1 -p 6379 INFO stats
redis-cli -h 127.0.0.1 -p 6379 DBSIZE
redis-cli -h 127.0.0.1 -p 6379 MEMORY STATS
```

Notable fields:

| Group | Example Fields | Meaning |
|---|---|---|
| RAM | `used_memory`, `used_memory_human` | How much memory Redis is using |
| Configuration | `maxmemory`, `maxmemory_policy` | Memory cap and eviction policy |
| Fragmentation | `mem_fragmentation_ratio`, allocator metrics | Overhead/fragmentation; do not interpret one metric in isolation |
| Keyspace | `db0:keys=...,expires=...,avg_ttl=...` | Key count, keys with expiration, and reported average TTL |
| Eviction | `evicted_keys` | Keys removed due to memory policy |
| Expiration | `expired_keys` | Keys that expired and were processed |
| Cache access | `keyspace_hits`, `keyspace_misses` | Access signals; do not alone determine cache quality |

`DBSIZE` counts keys in the **current connection's database**. In Redis Cluster, each node holds part of the keyspace; `DBSIZE` on one primary is **not** the key count of the entire Cluster. Redis Cluster uses logical database `0`.

### 4.1. Many Keys Can Still Cost More Than Grouping Into a Collection

One million small String keys carry overhead for:

- Key names and values.
- Entries in the Redis dictionary.
- Expiration metadata if TTL is set.
- Data encoding and internal memory allocation.
- Persistence, replication, and scan/expire cycles.

You cannot compute exact memory solely from value length. A better approach is benchmarking **on the actual Redis version and configuration**:

```text
M1 = used_memory on empty test Redis
Create N keys with typical key/value sizes
M2 = used_memory after stabilization

Sample memory-per-key ≈ (M2 - M1) / N
```

Repeat across String, Hash, Set, ZSet structures and different serializers. Leave headroom for fragmentation, buffers, persistence fork/copy-on-write, and traffic peaks; never set `maxmemory` equal to just the estimated payload sum.

## 5. Finding Big Keys More Safely Than KEYS *

Redis CLI supports keyspace analysis:

```bash
# Detect very long Strings, and Hashes/Sets/Lists/ZSets with many members.
redis-cli -h 127.0.0.1 -p 6379 --bigkeys

# Detect keys consuming high RAM based on MEMORY USAGE results.
redis-cli -h 127.0.0.1 -p 6379 --memkeys

# Some redis-cli versions also provide distribution/Top N statistics.
redis-cli -h 127.0.0.1 -p 6379 --keystats
```

`--bigkeys` uses type-appropriate measures, such as String length or collection member count. It **does not necessarily find the highest-RAM key**, because a Hash with few fields where each field is huge can still consume massive RAM. `--memkeys` / `--keystats` provide better memory analysis; option availability depends on the Redis CLI version.

These modes use scanning, not an instantaneous snapshot operation. Full data scans still generate load; in production, run during authorized windows, throttle the rate, and record the node/cursor/scan scope.

### 5.1. Throttling Scan Rate

Per Redis CLI documentation, you can use `-i` to pause between command batches:

```bash
redis-cli -h 127.0.0.1 -p 6379 --bigkeys -i 0.1
```

`0.1` merely illustrates a suitable pause interval for an investigation run. It does not guarantee zero latency impact. If Redis traffic is very high, consider running on an authorized replica, while noting replication lag and replica read restrictions.

### 5.2. Why Not Use KEYS *?

```redis
KEYS *
```

This command can scan the entire keyspace in one shot and keep Redis busy for a long time, stalling other clients. In Spring applications, `redisTemplate.keys("*")` usually issues `KEYS` on the server; do not call it in production endpoints or scheduled jobs to count/delete by prefix.

Replace it with cursor-based `SCAN` that bounds work per iteration. Yet **SCAN is not free**: scanning millions of keys still consumes total CPU/network and time.

## 6. SCAN, HSCAN, SSCAN, ZSCAN: Batching Instead of Loading Everything

Incremental iteration commands:

```redis
SCAN 0 MATCH app:cache:* COUNT 100
HSCAN cart:42 0 COUNT 100
SSCAN product:100:viewers 0 COUNT 100
ZSCAN ranking:daily 0 COUNT 100
```

The result has the form:

```text
1) next-cursor
2) entries in the current batch
```

The application uses the returned cursor for the next call, terminating **only when the cursor returns to 0**.

Key points to remember:

1. `COUNT 100` is a **hint for how much work Redis performs**, not a guarantee of "at most 100 elements per response."
2. An iteration may return **0 elements** while the cursor is not yet 0.
3. As data mutates, an element may be returned **more than once**; application handlers must be idempotent or deduplicate if needed.
4. This is not a consistent snapshot of the keyspace.
5. `SCAN MATCH` filters results by pattern; it does not turn scanning into an O(1) prefix lookup.
6. Some collections stored in compact encodings may return all elements in a single call despite a small `COUNT`, depending on Redis version and encoding thresholds.

### 6.1. Why Are Full-Collection Read Commands Dangerous?

| Command | Problem When Collection Is Large | Alternative |
|---|---|---|
| `SMEMBERS key` | Returns the entire Set | `SSCAN`, or design index-based pagination |
| `HGETALL key` | Returns every field/value | `HMGET` needed fields, `HSCAN` for inventory |
| `LRANGE key 0 -1` | Returns the entire List | `LRANGE` over small ranges |
| `ZRANGE key 0 -1` | Returns the entire Sorted Set | `ZRANGE`/`ZREVRANGE` by page |
| `XRANGE stream - +` | Returns entire Stream history | `XRANGE ... COUNT n` and cursor ID |
| `KEYS pattern` | Scans entire keyspace in one command | `SCAN` with cursor |

`HSCAN`/`SSCAN` do not automatically provide **stable user-facing pagination** while a collection undergoes concurrent writes/deletes. If an API requires ordered pagination, a Sorted Set with appropriate scores/members or an indexed database is usually more suitable.

## 7. Setting a Value Size Budget by **Serialized Bytes**

Suppose an endpoint stores a small configuration in Redis:

```text
Key:    app:settings:{tenant-42}
Value:  JSON config
Policy: no more than 32 KiB UTF-8 bytes per document
TTL:    15 minutes
```

**32 KiB is only an example** of a business policy limit, not Redis String's maximum limit. When choosing an actual limit, measure p95/p99 JSON size, network payload, and latency.

### 7.1. Mistake: Counting Java String.length()

```java
if (json.length() > 32_768) {
    throw new IllegalArgumentException("Too large");
}
```

`String.length()` counts UTF-16 code units, not the number of bytes that `StringRedisSerializer` writes to Redis. For instance, Vietnamese characters or emojis can take multiple UTF-8 bytes.

More accurate for Strings:

```java
byte[] bytes = json.getBytes(java.nio.charset.StandardCharsets.UTF_8);
if (bytes.length > 32 * 1024) {
    throw new IllegalArgumentException(
            "Redis JSON exceeds 32 KiB policy");
}
```

If using JDK serialization, a JSON serializer, compression, or encryption, measure **the actual bytes produced by that serializer**, rather than inferring from a Java object's `toString()`.

### 7.2. Example Spring Service Enforcing a JSON Value Limit

```java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class BoundedSettingsCache {

    private static final int MAX_JSON_BYTES = 32 * 1024;
    private static final Duration TTL = Duration.ofMinutes(15);

    private final StringRedisTemplate redis;
    private final ObjectMapper mapper;

    public BoundedSettingsCache(
            StringRedisTemplate redis,
            ObjectMapper mapper) {
        this.redis = redis;
        this.mapper = mapper;
    }

    public void store(String tenantId, SettingsDto settings) {
        if (tenantId == null ||
                !tenantId.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("Invalid tenantId");
        }
        try {
            String json = mapper.writeValueAsString(settings);
            int bytes = json.getBytes(StandardCharsets.UTF_8).length;

            if (bytes > MAX_JSON_BYTES) {
                throw new IllegalArgumentException(
                        "Settings payload exceeds limit: " + bytes);
            }

            String key = "app:settings:{" + tenantId + "}";
            redis.opsForValue().set(key, json, TTL);
        } catch (JsonProcessingException error) {
            throw new IllegalArgumentException(
                    "Cannot serialize settings", error);
        }
    }
}
```

`SettingsDto` is an application-defined business DTO. The example deliberately uses `StringRedisTemplate` so the stored bytes are the UTF-8 bytes of the measured JSON String; if switching to `RedisTemplate<String, SettingsDto>`, measure using the serializer attached to **that template**. Also enforce size limits at HTTP/API ingress so you do not parse a gigantic payload before discovering it exceeds the threshold.

### 7.3. Check Key Size Too

Overly long key names create memory overhead and increase bytes on every command. Use a concise yet operable schema:

```text
Reasonable:
  p:100:detail
  session:7f8a...

Unreasonable at scale:
  org:production:service:catalog:region:...:<entire request JSON>
```

Do not shorten keys to the point of collisions or losing tenant and environment isolation. In Redis Cluster, hash tags in keys also determine slot placement; changing key names can affect placement.

## 8. When a Value Is Large, Split the Data or Move to Another Storage?

An anti-pattern:

```text
report:2026-11-13 -> 20 MB JSON containing 50,000 result rows
```

Every `GET` pulls the entire report into the application, even when the user only needs the first 20 rows. When data is a large document or binary asset, options include:

| Solution | Suitable For | Things to Watch |
|---|---|---|
| Keep one Redis String | Small values, reading/writing the whole object | Always transfers full value |
| Split into page/chunk keys | Independent partial reads | Manifest, partial writes, versioning, cleanup, key count |
| Redis Hash by field group | Reading specific fields only | Field count limits, encoding, whole-key TTL |
| Redis Sorted Set | Ordered pagination by score/rank | Managing cardinality, ordering, and updates |
| Object storage + Redis pointer | Large documents, media, snapshots | Object fetch latency, access permissions, dual-system lifecycle |
| Indexed database | Querying/paginating across multiple attributes | Operational cost and transactional properties |

Do not blindly split one 20 MB JSON into 20,000 1 KB keys. That trades a **big value** problem for **key explosion**. Partition based on how the application **actually accesses** the data.

### 8.1. Reference Pattern Instead of Storing Large Content

```text
Redis:
  report:913:meta -> {
      "objectId": "reports/913/v4.json",
      "etag": "...",
      "status": "READY",
      "byteSize": 20000000
  }

Object storage:
  reports/913/v4.json -> large file
```

Readers fetch only small metadata from Redis; when a user requests the report, use a signed URL or a controlled download service. Never let a path or object ID from Redis turn into unchecked public access.

### 8.2. If Chunking Is Unavoidable

Example key naming:

```text
document:{913}:v4:chunk:0001
document:{913}:v4:chunk:0002
document:{913}:v4:chunk:0003
document:{913}:current -> v4
```

Write all chunks of the new version first, verify completeness, then update the `current` pointer **last**. Readers only read the published version to avoid mixing half old / half new documents. Include checksums, expected chunk counts, TTL/cleanup, and mid-crash handling. Keys sharing the hash tag map to the same slot, helpful for locality yet carrying hot-slot risk if one document is huge.

In Redis Cluster, multi-key operations have hash-slot constraints. Do not assume pipelining or multiple `SET` commands automatically become an atomic transaction.

## 9. Compression and Serializers: Fewer Bytes, Different Costs

When JSON payloads have many repetitive fields and moderate read frequency, compression can reduce network and RAM usage. However:

- Adds CPU cost for compression/decompression and allocations.
- Cannot be read directly via Redis CLI or `StringRedisTemplate` if stored as compressed binary.
- Small payloads sometimes grow **larger** when compressed due to headers/metadata.
- Individual fields of a compressed blob cannot be queried.
- Requires a versioned format so old and new readers interoperate.

A possible contract:

```text
payloadBytes = JSON UTF-8
compressedBytes = gzip(payloadBytes) if above threshold and saves enough
envelope = version + codec + payloadBytes
```

Benchmark **bytes after the entire serialize → compress/encrypt pipeline** along with CPU time and p95 latency, not just average compression ratio. If two services share a key, they need a format contract; changing serializers is not purely an internal optimization.

## 10. Controlling Member Count: Bounded Collections

A Set can grow unboundedly if code continuously calls:

```java
redis.opsForSet().add("product:100:viewers", userId);
```

If the Set stores **every** user who ever viewed a product, member count can grow without limit. Setting a TTL on the **Redis key** does not automatically evict old individual members while the Set keeps being refreshed.

Options:

1. **Hard cap:** reject adding new members once a threshold is reached.
2. **Sliding window:** keep only members active within a recent time window.
3. **Top-N:** keep only the N highest-scoring items.
4. **Bucketing:** split data into multiple keys by time, tenant, or partition.
5. **Approximate cardinality:** if only unique counts are needed, consider HyperLogLog instead of storing every ID.
6. **Cold storage:** move detailed history out of Redis, keeping a small index/cache.

These strategies differ in semantics. **Never silently apply a hard cap** if the application requires complete history for auditing.

## 11. Avoiding Races When Checking SCARD Then Calling SADD

Java code that looks right:

```java
Long count = redis.opsForSet().size(key);
if (count != null && count < 10_000) {
    redis.opsForSet().add(key, member);
}
```

Two workers can both observe `count = 9999`, then both `SADD` different members, pushing the Set past 10,000. **Checking cardinality and adding a member must be an atomic operation** when the cap is a hard constraint.

### 11.1. Lua Script to Cap Set Member Count

A script accepting `KEYS[1]` as the Set, `ARGV[1]` as the member, and `ARGV[2]` as max:

```lua
local key = KEYS[1]
local member = ARGV[1]
local maxMembers = tonumber(ARGV[2])

if not maxMembers or maxMembers < 1 then
    return redis.error_reply('Invalid maxMembers')
end

-- Member already exists: idempotent operation.
if redis.call('SISMEMBER', key, member) == 1 then
    return 0
end

if redis.call('SCARD', key) >= maxMembers then
    return -1
end

redis.call('SADD', key, member)
return 1
```

Result convention:

| Result | Meaning |
|---|---|
| `1` | Added a new member |
| `0` | Member already present, cardinality unchanged |
| `-1` | Set is full, addition rejected |

Lua ensures `SISMEMBER`, `SCARD`, and `SADD` execute without interleaving from other Redis clients **on the node executing the script**. On Cluster, the script uses one Redis key so it routes cleanly to that key's slot. This bounds **cardinality**, not bytes per member: a 1 MB member is still huge and must be validated in Java before invoking the script.

### 11.2. Calling the Script from Spring Data Redis

```java
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Component;

@Component
public class BoundedMemberSet {

    private static final int MAX_MEMBERS = 10_000;
    private static final int MAX_MEMBER_BYTES = 128;

    private static final String LUA = """
        local key = KEYS[1]
        local member = ARGV[1]
        local max = tonumber(ARGV[2])
        if redis.call('SISMEMBER', key, member) == 1 then
            return 0
        end
        if redis.call('SCARD', key) >= max then
            return -1
        end
        redis.call('SADD', key, member)
        return 1
        """;

    private static final DefaultRedisScript<Long> SCRIPT =
            new DefaultRedisScript<>(LUA, Long.class);

    private final StringRedisTemplate redis;

    public BoundedMemberSet(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public boolean add(String productId, String memberId) {
        if (productId == null ||
                !productId.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("Invalid productId");
        }
        if (memberId == null || memberId.isBlank() ||
                memberId.getBytes(StandardCharsets.UTF_8).length
                        > MAX_MEMBER_BYTES) {
            throw new IllegalArgumentException("Invalid memberId");
        }

        String key = "product:{" + productId + "}:viewers";
        Long result = redis.execute(
                SCRIPT, List.of(key),
                memberId, Integer.toString(MAX_MEMBERS));

        if (result == null) {
            throw new IllegalStateException("Result unavailable");
        }
        if (result == -1L) {
            throw new IllegalStateException("Set reached hard cap");
        }
        return result == 1L;
    }
}
```

In this example, `10,000` and `128 bytes` are illustrative policy limits. If the Set needs to expire automatically, **add** TTL handling; the code above intentionally neither refreshes nor clears TTL to avoid altering semantics beyond the example's scope.

**Practical note:** a hard-capped Set can reject new users permanently if there is no mechanism to remove old members. If business logic needs "active in the last 15 minutes," choose a timestamp-scored Sorted Set with time-based pruning rather than an unaged Set.

## 12. Sliding Window with Sorted Set

Suppose you need users who interacted in the last 15 minutes. With a Sorted Set:

```text
Key:    activity:{product-100}
Member: userId
Score:  timestamp milliseconds
```

Whenever a user is active, record:

```redis
ZADD activity:{product-100} 1763000000000 user-42
```

Prune old history:

```redis
ZREMRANGEBYSCORE activity:{product-100} -inf 1762999100000
```

Timestamps in the example are illustrative. In a real system, the cutoff is computed from current time and the policy duration. If timestamps come from untrusted clients, clock skew may occur; consider using the server clock or a verified time source.

Count retained members:

```redis
ZCARD activity:{product-100}
```

### 12.1. Prune Regularly, Do Not Just Count

Without calling `ZREMRANGEBYSCORE` or having an appropriate key TTL, the Sorted Set still grows without bound. Prune on every write, on a schedule, or using a hybrid strategy; on very large Sets, bulk deletion still costs O(M) in the number of removed elements.

If you need a **hard cap** of at most N members in addition to the time window, add controlled trimming of the lowest-ranked/oldest elements. Under concurrency, use Lua to make `ZADD`/`ZREMRANGEBYSCORE`/rank-trimming atomic when invariants require it.

### 12.2. Be Careful With TTL

`EXPIRE activity:{product-100} 900` sets a TTL **on the entire Sorted Set**, not per member. Refreshing `EXPIRE` on every activity keeps the key alive indefinitely while old members remain unless pruned by score.

Do not confuse "key has TTL" with "collection self-limits member count." The two policies are independent.

## 13. Top-N with Sorted Set: Keeping Only the Most Important Elements

A leaderboard that only needs the **top 100 highest-scoring products** should not keep an unbounded number of products in the same key just so every request calls `ZREVRANGE 0 99`.

Example:

```redis
ZADD ranking:daily 98 product-100
ZADD ranking:daily 87 product-101

# Keep at most 100 highest-scoring members.
ZREMRANGEBYRANK ranking:daily 0 -101

# Read only the top 20 elements.
ZREVRANGE ranking:daily 0 19 WITHSCORES
```

`ZREMRANGEBYRANK key 0 -101` removes the lowest-ranked elements, leaving at most the top 100 elements (highest scores). This does not satisfy full-catalog ranking requirements if the application truly needs to query every product: in a Top-100-only leaderboard, items ranked 101 and below have already been discarded.

If multiple writers update the ranking concurrently and the cap must hold **at all times**, combine `ZADD` and rank trimming in Lua or use a controlled single writer. Two independent commands leave a window where the collection exceeds the cap.

### 13.1. Avoid Reading the Entire Leaderboard

In Spring Data Redis:

```java
import java.util.Set;
import org.springframework.data.redis.core.StringRedisTemplate;

public Set<String> topProducts(
        StringRedisTemplate redis, int page, int size) {

    if (page < 0 || size < 1 || size > 100) {
        throw new IllegalArgumentException("Invalid page");
    }
    long start = (long) page * size;
    long end = start + size - 1;

    return redis.opsForZSet()
            .reverseRange("ranking:daily", start, end);
}
```

The query returns **one page**, avoiding materializing a Map/List of the entire Sorted Set. However, rank-based pagination does not provide a stable snapshot when scores/members mutate concurrently: consecutive pages can duplicate or skip items as ranks shift. For immutable pagination, use snapshots/versions or score/member cursors with explicit tie-breaking rules.

## 14. Bounding Lists and Distinguishing Ring Buffers from Reliable Queues

A List keeping the 100 most recent log messages can use:

```redis
LPUSH audit:recent "event-101"
LTRIM audit:recent 0 99
```

`LPUSH` prepends the new element; `LTRIM 0 99` keeps the first 100 elements. If two writers run concurrently between the two commands, the limit can temporarily be exceeded. If an atomic cap is required, use Lua:

```lua
redis.call('LPUSH', KEYS[1], ARGV[1])
redis.call('LTRIM', KEYS[1], 0, tonumber(ARGV[2]) - 1)
return redis.call('LLEN', KEYS[1])
```

This is a **best-effort ring buffer** or recent-items list. It is **not** a job processing queue with ACK/replay: `LTRIM` drops old elements even if no consumer has processed them yet. If messages must never be lost, use Redis Streams with consumer groups or an appropriate queuing system.

### 14.1. Range Reads

```redis
LRANGE audit:recent 0 19
LRANGE audit:recent 20 39
```

In Spring:

```java
List<String> firstPage =
        redis.opsForList().range("audit:recent", 0, 19);
```

Never call `range(key, 0, -1)` in an endpoint when the List can grow to hundreds of thousands of elements.

## 15. Bounding Hashes: Field Count and Per-Field Value Length

Example:

```text
user:{42}:preferences
  theme             -> "dark"
  locale            -> "vi-VN"
  notificationOptIn -> "true"
```

A compact Hash for related attributes can be more efficient than creating a separate Redis String per attribute. Yet if a Hash stores **a field for every user click**, field count can grow indefinitely into a big key.

Inspect:

```redis
HLEN user:{42}:preferences
HSTRLEN user:{42}:preferences locale
HSCAN user:{42}:preferences 0 COUNT 50
MEMORY USAGE user:{42}:preferences
```

`HSTRLEN` measures the byte length of a **String field value inside a Hash**, not the entire Hash. `HLEN` measures field count. To read a few known fields, use `HMGET`/`HGET` instead of `HGETALL`.

### 15.1. Compact Encoding and listpack

Redis optimizes many small aggregates using compact encodings. In Redis 7.x, small Hashes or Sorted Sets may use **listpack**, transitioning to another representation when exceeding thresholds such as:

```conf
hash-max-listpack-entries 512
hash-max-listpack-value 64
zset-max-listpack-entries 128
zset-max-listpack-value 64
```

These are **example defaults from certain Redis 7.x builds**, not a guarantee that every Redis version uses the exact same settings. When a collection crosses entry count or member size thresholds, Redis can switch encodings and memory-per-entry can change noticeably.

Do not "optimize" by raising `hash-max-listpack-entries` to millions without benchmarking CPU and latency. Compact encodings save RAM, yet operations may scan contiguous elements linearly; Redis docs highlight this as a memory-vs-CPU trade-off.

### 15.2. Hashes Have Key-Level TTL

`EXPIRE user:{42}:preferences 600` sets TTL on the entire Hash key. Newer Redis versions added field-level expiration mechanisms for Hashes, though support through Spring Data Redis depends on the exact Redis version, driver, and API. For systems spanning multiple versions, do not assume every Hash field expires independently like a standalone Redis key.

If per-attribute TTL is required, consider separate keys or values carrying timestamps and cleanup logic, while keeping key count controlled.

## 16. Redis Streams: MAXLEN, MINID, Pending Entries, and Retention

A Stream continuously receives new events:

```redis
XADD events:checkout * eventId evt-001 type CREATED
```

Without retention, history can grow infinitely. Redis supports appending and trimming nearly at once:

```redis
XADD events:checkout MAXLEN ~ 10000 * eventId evt-002 type CREATED
```

The `~` flag requests **approximate trimming**, which is usually more efficient than exact trimming. Consequently, `XLEN events:checkout` may stay **above 10,000** for some time depending on macro-node layout and Redis version. If policy mandates a hard cap, evaluate `MAXLEN =` and its cost; however, a hard cap does not guarantee retention suits slow consumers.

### 16.1. Do Not Blindly Trim Unprocessed Data

With consumer groups:

```text
events:checkout
       |
       +--> billing-workers: PEL has unACKed messages
       |
       +--> analytics-workers: reading slowly
```

If old records are trimmed purely by `MAXLEN`, messages still needed by workers can be purged from the Stream before recovery re-reads them. Some Redis versions offer policies handling consumer group references during trimming, so check exact server version contracts; do not assume pending metadata guarantees payloads remain stored.

Determine retention from:

- Incoming event rate.
- Consumption rate of the slowest group.
- Retry/backoff duration.
- Tolerable downtime.
- RAM/disk capacity.
- Ability to archive to more durable storage.

A Stream with millions of entries can still be read in batches, yet the server still needs RAM and persistence; do not treat Streams as free infinite history storage.

### 16.2. Querying Partial History

```redis
XLEN events:checkout
XINFO STREAM events:checkout
XINFO GROUPS events:checkout
XRANGE events:checkout - + COUNT 100
```

Paginate by Stream ID after the last record rather than repeatedly calling unbounded `XRANGE - +`. When reading via consumer groups, design explicit PEL recovery rather than just limiting `XREADGROUP` batch size.

## 17. Total Key Count: TTL, Namespaces, and Data Lifecycle

A dangerous code path:

```java
redis.opsForValue().set(
        "request:" + requestId,
        json);
```

If every request creates a new key **without TTL/cleanup**, key count grows with cumulative requests. For instance, an app handling 500 requests/second that creates a new key per request generates 43.2 million keys per day—purely counting key volume before memory overhead.

If data is only needed briefly, set TTL on creation:

```java
redis.opsForValue().set(
        "request:" + requestId,
        json,
        java.time.Duration.ofMinutes(30));
```

**Not all data should have a TTL.** Business keys that must persist until confirmed/processed should not vanish simply because a fixed duration elapsed. Classify data clearly:

| Data Category | Suggested Lifecycle |
|---|---|
| Cache | TTL based on freshness and origin load |
| Session | Expiration per session policy |
| Deduplication key | TTL longer than valid retry/replay window |
| UnACKed Queue/Stream | Retention based on processing lag and downtime |
| Temporary upload/chunk | TTL and cleanup for unpublished versions |
| Lock | Lease TTL with safe renewal/ownership |
| Secondary index | Synchronize lifecycle with the data it describes |

### 17.1. TTL Is Not a Hard Cap on Total Key Count

Suppose requests/second jump 10x: the same 30-minute TTL now produces 10x as many live keys. TTL caps **lifetime**, not directly **concurrent total count**.

To budget keys, estimate:

```text
liveKeys ≈ newKeysPerSecond × averageLifetimeSeconds
```

This approximation assumes relatively steady traffic and few early deletes. In practice, provision for traffic peaks, expiration backlog, retries, and TTL distribution.

### 17.2. Avoid Expiring All Keys in the Same Second

If one million cache keys are created in a batch with the exact same 3600-second TTL, they can expire near-simultaneously, causing cache refresh spikes, higher DB load, and cache stampedes. When business logic allows, add **TTL jitter**:

```java
long baseSeconds = 3_600;
long jitterSeconds =
        java.util.concurrent.ThreadLocalRandom.current()
                .nextLong(0, 301);

java.time.Duration ttl =
        java.time.Duration.ofSeconds(
                baseSeconds + jitterSeconds);
```

Jitter in this example extends TTL by up to 300 seconds. If there is a strict maximum staleness limit, pick a jitter range that keeps data within SLA.

## 18. maxmemory and Eviction Policies Do Not Replace Bounded Design

Redis provides:

```redis
CONFIG GET maxmemory
CONFIG GET maxmemory-policy
INFO memory
INFO stats
```

Common eviction policies:

| Policy | General Behavior |
|---|---|
| `noeviction` | Does not evict to serve new writes; commands needing more memory may return errors |
| `allkeys-lru` | Evicts keys using approximate LRU across the entire keyspace |
| `allkeys-lfu` | Evicts keys using approximate access frequency |
| `volatile-lru` | Considers only keys with an expiration set |
| `volatile-ttl` | Prioritizes keys with shorter remaining expiration per policy |

**Do not rely on eviction as a business correctness mechanism.** If Redis holds both expendable cache and unprocessed jobs, `allkeys-lru` can evict job keys. For critical data, isolate instances/Clusters or use durable storage instead of sharing an evicting RAM pool.

`maxmemory` also does not guarantee the entire Redis process stays below that exact RAM figure: replication/persistence buffers, allocator fragmentation, fork copy-on-write, and other memory areas follow separate accounting rules. Monitor process RSS and real headroom.

### 18.1. When Memory Hits the Ceiling

Inspect at least:

- `used_memory` and `maxmemory`.
- How fast `evicted_keys` grows.
- `expired_keys` and count of keys with TTL.
- Spring p95/p99 latency and error rate.
- Which keys/namespaces are growing in cardinality.
- Redis replication/persistence lag or failures.

Do not keep raising `maxmemory` without locating the source of growth. If the root cause is a Set that never deletes members, extra RAM only delays the failure.

## 19. Spring Cache: Avoid Caching Oversized Objects and Lists

Example:

```java
@Cacheable(cacheNames = "productSearch", key = "#query")
public List<ProductDto> search(String query) {
    return productRepository.search(query);
}
```

If a query can return 100,000 products, caching **the entire List** in one key produces an oversized value. Clients needing only page 1 still deserialize the whole List.

Better design:

```java
@Cacheable(
        cacheNames = "productSearchPages",
        key = "#query + ':' + #page + ':' + #size")
public PageDto<ProductDto> searchPage(
        String query, int page, int size) {

    if (size < 1 || size > 100) {
        throw new IllegalArgumentException("Invalid size");
    }
    return productRepository.searchPage(query, page, size);
}
```

`ProductDto`, `PageDto`, and the repository are project-defined components. For `PageDto`, avoid serializing entire entity graphs or unnecessary lazy relationships. Even a 100-item page can be huge if each `ProductDto` embeds images or giant nested objects.

### 19.1. Separate Pages Increase Key Count

Page caching trades one large value for many smaller keys. Therefore, control:

- Maximum page size.
- Allowed cacheable query combinations.
- Key generation/canonicalization.
- TTL and invalidation.
- Access frequency; avoid caching every unique bot query.
- Total key budget per cache namespace.

If every user searches a random string and each creates 100 page keys, total key count can explode even if every value is small. Consider caching only popular queries or using an admission policy.

### 19.2. Cache Serializers Also Add Overhead

`RedisCacheManager` has its own serializer, not necessarily the one used by `StringRedisTemplate`. When benchmarking cache entry size, measure **actual bytes in Redis**, not just your estimated JSON size. Type metadata, wrapper objects, and key prefixes all add bytes.

## 20. Partitioning Collections to Avoid Unbounded Single Keys

A system-wide Hash:

```text
all:orders -> millions of orderId fields
```

scales poorly on Cluster because the entire Hash lives on one slot. Partitioning schemes include:

```text
orders:{tenant-42}:2026-11
orders:{tenant-42}:2026-12

orders:{tenant-43}:2026-11
orders:{tenant-43}:2026-12
```

Notice that the example above uses `{tenant-42}` for both months of the same tenant, so those keys **still map to the same hash slot**. To distribute across months or buckets, the tag must include the bucket:

```text
orders:{tenant-42:2026-11}:part-00
orders:{tenant-42:2026-11}:part-01
orders:{tenant-42:2026-12}:part-00
```

Keys sharing tag `tenant-42:2026-11` again share a slot. When distribution is needed **even within one month**, include the partition in the tag:

```text
orders:{tenant-42:2026-11:p00}
orders:{tenant-42:2026-11:p01}
orders:{tenant-42:2026-11:p02}
```

The choice depends on multi-key atomicity needs and query patterns. Putting all data under a shared tag preserves locality but risks a **hot slot**. Splitting tags reduces the ability to run multi-key transactions across partitions.

### 20.1. Estimating Partition Count

Example targeting an average of 5,000 members/partition with an expected peak of 200,000 members:

```text
Minimum partitions by average = ceil(200000 / 5000) = 40
```

This is a capacity-planning calculation; it does not guarantee every partition holds only 5,000 members if hashing skews distribution. For hard constraints, you still need cardinality guards and a repartitioning plan. Also account for per-key metadata and fan-out cost when queries touch multiple partitions.

### 20.2. Avoid "Fetch All" Operations

If you split data into 40 partitions, a "fetch all members" request simply issues 40 queries and still loads 200,000 members—the problem merely moved. Design paginated APIs, targeted indexes, or move aggregate queries to dedicated storage.

## 21. SCAN with StringRedisTemplate and Closing Cursors

Example scanning keys by namespace for **bounded inventory**:

```java
import java.util.ArrayList;
import java.util.List;
import org.springframework.data.redis.core.Cursor;
import org.springframework.data.redis.core.ScanOptions;
import org.springframework.data.redis.core.StringRedisTemplate;

public List<String> sampleKeys(
        StringRedisTemplate redis, String prefix, int maxKeys) {

    if (prefix == null ||
            !prefix.matches("[A-Za-z0-9:_-]{1,64}")) {
        throw new IllegalArgumentException("Invalid prefix");
    }
    if (maxKeys < 1 || maxKeys > 1_000) {
        throw new IllegalArgumentException("Invalid cap");
    }

    List<String> result = new ArrayList<>();
    ScanOptions options = ScanOptions.scanOptions()
            .match(prefix + "*")
            .count(100)
            .build();

    try (Cursor<String> cursor = redis.scan(options)) {
        while (cursor.hasNext() && result.size() < maxKeys) {
            result.add(cursor.next());
        }
    }
    return result;
}
```

Key points:

- `maxKeys` bounds **the number of keys returned in the Java List**, not the number of keys Redis must inspect.
- `SCAN` can return duplicates when the keyspace mutates. If uniqueness is needed, collect into a bounded client-side `Set`.
- `Cursor` must be closed.
- Do not treat the result of a sample pass as the exact key count of the namespace.
- `scan` scope on Cluster depends on adapter/API/driver; scanning one connection/node does not necessarily scan the entire Cluster. A full Cluster inventory requires targeting all primaries/shards.

For huge keyspaces, dedicated monitoring or write/delete-time counters are preferable to continuously scanning millions of keys for totals.

## 22. Cleaning Up Big Keys: UNLINK, Batching, and Data Ownership

When deleting a large Set/Hash/List from Redis, `DEL` can spend significant time freeing internal structures. Redis provides:

```redis
UNLINK old:oversized:set
```

`UNLINK` removes the key from the keyspace and frees most of the value's memory in the background, reducing command-thread latency compared to `DEL` for large objects. However, **actual RAM reclamation** happens asynchronously afterward and depends on the allocator; do not expect `used_memory_rss` to drop instantaneously.

In Spring Data Redis:

```java
Boolean removed = redis.unlink("old:oversized:set");
```

Only delete keys after verifying namespace, ownership, and retention policy. Never run `SCAN app:*` and `UNLINK` millions of keys at once in a request path; instead:

1. Run a rate/batch-limited cleanup job.
2. Log deletion reasons and validate key patterns strictly.
3. Use a cursor to locate keys, handling missing keys idempotently.
4. Monitor Redis latency, background free backlog, and memory.
5. Have a stop/rollback plan if the wrong scope is targeted.

If writers keep recreating keys or adding members after cleanup, one-off deletion only treats symptoms. Fix the **write path** so data stops growing unboundedly.

## 23. When to Use HyperLogLog, Bitmaps, or Bloom Filters?

Some applications store Sets solely to answer **roughly how many unique users**, without ever listing all IDs.

Example:

```redis
PFADD visitors:daily:2026-11-13 user-42
PFADD visitors:daily:2026-11-13 user-43
PFCOUNT visitors:daily:2026-11-13
```

Redis HyperLogLog **estimates distinct element counts** using tiny fixed memory, but cannot enumerate members. It has statistical error and is unsuitable when exact counts or exact membership lookups are required.

| Structure | Can Answer | Unsuitable When |
|---|---|---|
| Set | Exact membership, list members | Massive ID volume when only total count is needed |
| HyperLogLog | Approximate distinct count | Need exact IDs or exact count |
| Bitmap | Bit states by integer offset | Sparse/huge IDs that map poorly to offsets |
| Bloom filter (module/appropriate impl) | **Possible** membership, with false positives | Cannot tolerate false positives or need to list elements |

Do not silently switch a userId Set to HyperLogLog if business logic must export the list of viewers. Memory optimizations must preserve data requirements.

## 24. Redis Cluster: Limits by Node, Slot, and Big/Hot Keys

Redis Cluster uses 16,384 hash slots:

```text
Redis key bytes --> CRC16 --> slot --> master node
```

Measurement commands like `MEMORY USAGE key` and `SCARD key` must go to the node serving that key; cluster-aware clients route them for you. Yet `INFO memory` reports metrics for **the queried node**, not the entire Cluster total.

### 24.1. One Big Key Is Not Split by Cluster

```text
giant:set -> slot s -> Master B
```

Adding Master C does not split `giant:set` in two. To distribute a huge collection, **redesign the data model** into multiple keys/partitions with slot-distributing key names.

### 24.2. Hash Tags Can Overheat an Entire Shard

```text
user:{enterprise}:1
user:{enterprise}:2
user:{enterprise}:3
... all in the same slot
```

A shared tag `{enterprise}` gives locality but concentrates load onto one primary. Scope hash tags to the **unit truly needing multi-key atomicity**, not an entire large tenant.

### 24.3. Do Not Confuse Single-Node SCAN with Full-Cluster SCAN

`SCAN` inspects keys on the connected node only. A dashboard wanting total keys/bytes across a Cluster must collect across all primaries/shards, avoid double-counting replicas, and account for resharding/failover during collection. Redis `CLUSTER SHARDS` can discover topology on supported Redis versions.

## 25. Reactive Redis: Backpressure Does Not Split Large Commands

With `ReactiveRedisTemplate`, downstream supports backpressure and cancellation. Yet:

```java
reactiveRedis.opsForSet().members("huge:set")
```

Returning `Flux` does not automatically turn a full-Set Redis command into small `SSCAN` calls. If the underlying driver requests the entire collection, the client can still receive a giant reply before downstream processes items individually.

For incremental iteration, select an **API/command backed by SCAN** and verify streaming/scan semantics, e.g., `ReactiveSetOperations.scan(...)` on supported Spring Data Redis versions. Measure network bytes, connection lifetime, backpressure, and concurrency limits.

### 25.1. Bounding Requests and Batch Processing

A reactive chain can bound concurrent requests:

```java
Flux.fromIterable(ids)
    .flatMap(
        id -> reactiveRedis.opsForValue().get("product:" + id),
        16
    );
```

`flatMap(..., 16)` limits concurrently subscribed inner Publishers, **not** the value size of each `GET`. If every product value is 5 MB, 16 concurrent reads still consume massive memory. Combine:

- Byte limits per value.
- ID count limits per request.
- Reasonable concurrency.
- Timeouts, circuit breakers, and latency measurement.
- Never calling `collectList()` on an unbounded or huge Flux.

Reactive programming cannot fix a data model with big keys using operators alone.

## 26. Observing Performance with SLOWLOG and Latency

Useful Redis commands:

```redis
SLOWLOG LEN
SLOWLOG GET 20
LATENCY LATEST
INFO commandstats
INFO memory
INFO stats
```

`SLOWLOG` records **Redis command execution time** exceeding the configured threshold; it does not measure full network round trip or JVM deserialization time. A 10 MB JSON response can slow down an HTTP request without standing out in SLOWLOG if key lookup itself was fast and transfer/parsing happened outside measured server execution.

Monitor together:

| Component | Metrics |
|---|---|
| Redis | command latency, slowlog, CPU, memory, evicted keys |
| Network | bytes/sec, bandwidth, socket timeouts |
| Lettuce/Jedis | command timeouts, pool/connection pressure |
| Java | heap usage, allocations, GC pauses, deserialization time |
| HTTP | p50/p95/p99 latency, response bytes, error rate |
| Data model | max value bytes, max members/key, total keys/namespace |

Do not apply Redis server fixes when the real culprit is a controller serializing 100,000 DTOs into JSON on every request.

## 27. Setting Namespace Budgets and Guardrails

Sample policy table:

| Namespace | Type | Illustrative Limit | Lifecycle | Read Path |
|---|---|---|---|---|
| `cache:product:*` | String JSON | 64 KiB/value | TTL 30 min ± jitter | `GET` |
| `session:*` | String | 8 KiB/value | Session TTL | `GET` |
| `cart:{user}:items` | Hash | 200 fields | Cart TTL | `HMGET` |
| `activity:{product}` | ZSet | 10,000 members | 15-min sliding window | Paginated `ZRANGE` |
| `ranking:daily` | ZSet | Top 1000 | Daily rebuild | Top-N pages |
| `events:checkout` | Stream | Retention by backlog/SLA | Safe XTRIM/archiving | Consumer group |
| `request:*` | String | 2 KiB/value | 30-min TTL | Read by ID |

**Numbers only illustrate how to write policies** and are not benchmarked limits. A namespace can also specify key count and total memory limits:

```text
namespace:
  maxValueBytes
  maxMemberBytes
  maxMembersPerKey
  maxKeysEstimate
  maxRetentionAge
  maxScanWorkPerJob
  maxReadPageSize
  expectedReadRate
  priorityForEviction
```

Redis has no built-in configuration enforcing all of these per-prefix quotas automatically. Most must be enforced at the application layer, via Lua/scripts, schedulers, proxies, or namespace/instance isolation.

## 28. Testing Size, Cardinality, and Key Count with Spring Data Redis

A good test checks not only return values but also **actual Redis state**.

### 28.1. Testcontainers on Dedicated Redis

Spring Boot 3.x + JUnit 5 test skeleton:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
}
```

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@SpringBootTest
@Testcontainers
class RedisSizePolicyIntegrationTest {

    @Container
    static final GenericContainer<?> redis =
            new GenericContainer<>(
                DockerImageName.parse("redis:7.4-alpine"))
                    .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisSettings(DynamicPropertyRegistry props) {
        props.add("spring.data.redis.host", redis::getHost);
        props.add("spring.data.redis.port",
                () -> redis.getMappedPort(6379));
    }

    @Autowired
    StringRedisTemplate template;

    @Test
    void redisIsAvailable() {
        // Add meaningful assertions in subsequent tests.
    }
}
```

Testcontainers requires Docker or a compatible runtime; the code merely illustrates tests to implement in a project. Never target production Redis in load tests. When upgrading Redis versions, re-verify memory/encoding behavior on the target version.

### 28.2. Testing UTF-8 Byte Limits

```java
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Test
void rejectValueExceedingByteLimit() {
    String payload = "🚀".repeat(10_000);

    assertThatThrownBy(() ->
            boundedCache.store("tenant42",
                    new SettingsDto(payload)))
        .isInstanceOf(IllegalArgumentException.class);
}
```

`boundedCache` and `SettingsDto` correspond to the service in section 7. Tests should assert that after failure **no Redis key is created**, and separately verify whether values exactly at the limit are accepted per policy.

### 28.3. Testing Atomic Set Limits Under Contention

1. Pick a test key and a small cap, e.g., `maxMembers = 10`.
2. Launch 50 tasks adding **50 distinct members** concurrently.
3. Wait for all to finish.
4. Assert `SCARD` does not exceed `10`.
5. Retry adding an already-present member; confirm it is not rejected as exceeding the cap per design semantics.

Do not claim two separate `SCARD` and `SADD` calls are atomic just because tests rarely trigger the race; use an atomic primitive like the Lua script in section 11.

### 28.4. Testing Large Values and Memory/Latency

On test Redis:

```text
Dataset A: 10,000 Strings, 100 B each
Dataset B: 10,000 Strings, 10 KiB each
Dataset C: 1 Hash with 10,000 fields
Dataset D: 10,000 Hashes with 1 field each
```

Measure:

- `INFO memory` before/after.
- `MEMORY USAGE` on sample keys.
- `GET`/`HGET`/`HSCAN` latency.
- Java allocations/GC when reading 10, 100, and 1,000 elements.
- RDB load time and network traffic if relevant.

Do not use numbers from a laptop as unverified production thresholds. Compare across payload sizes, concurrent requests, and matching topologies.

## 29. Common Pitfalls

| Symptom | Possible Cause | Mitigation |
|---|---|---|
| Single `GET` is very slow | Value too large, heavy deserialization/HTTP response | Measure bytes, switch to paging/references |
| Redis memory grows despite flat QPS | Keys lack TTL or collections accumulate members | Measure namespace cardinality and lifecycle |
| `SMEMBERS` causes request timeouts | Reading huge Set in full | `SSCAN` or paginated index |
| `HGETALL` triggers GC spikes | Hash has too many fields/values | `HMGET` needed fields, paginate, or split |
| `SCAN COUNT 100` returns >100 | COUNT is only a hint | Bound application output, do not assume exact batch |
| `MEMORY USAGE` smaller than expected or fluctuates | Sampling/encoding/allocator | Check SAMPLES, Redis version, dataset |
| Set exceeds cap despite `SCARD` check | Race between check and add | Atomic Lua or alternative model |
| TTL keeps extending while Set bloats | Key-level TTL refreshed without pruning old members | Score-based sliding window |
| Redis key count grows despite small origin data | Per-request/per-field key explosion | Choose aggregation/bucketing and TTL |
| Redis Cluster still overloads one primary | Hot key or overly broad hash tag | Split data model across keys/slots |
| Many cached keys but low hit rate | Cache key cardinality driven by user queries | Admission policy / cache hot queries only |
| `XADD MAXLEN ~ N` has `XLEN > N` | Approximate trimming | Allow headroom or change policy |
| Stream trim drops pending worker records | Retention ignores consumer groups | Coordinate ACK/retention/archiving |
| `DEL` big key causes latency spike | Freeing huge structure on command path | `UNLINK` and bounded cleanup |
| Low `used_memory` yet HTTP is slow | Network/JVM/response serialization bottleneck | Measure end-to-end, not just Redis |
| Eviction deletes critical data | Mixing cache and job data under `allkeys` policy | Separate deployments or use proper storage |
| `redisTemplate.keys("*")` disrupts production | Uses `KEYS` full scan | Use SCAN or writer-side counters |
| Changing serializer unexpectedly bloats values | Metadata/UTF-8/compression format | Measure serialized bytes and contract test |
| Deleted keys yet RSS RAM does not drop immediately | Allocator/fragmentation/async free | Monitor INFO memory and real memory pressure |

## 30. Hands-On Exercises

### Exercise 1 — Distinguishing Bytes, Members, and RAM

1. Write a String containing Unicode and a Hash with 50 fields.
2. Run `STRLEN`/`HLEN`/`MEMORY USAGE`.
3. Explain why `STRLEN` and `MEMORY USAGE` do not return the same number.
4. Add 5,000 fields to the test Hash and observe memory and `HGETALL` duration.
5. Use cursor-based `HSCAN` for bounded iteration.

### Exercise 2 — Detecting Big Keys

1. Create Strings, Hashes, Sets, and ZSets of varying sizes on test Redis.
2. Run `redis-cli --bigkeys` and `--memkeys`.
3. Compare the key with the most members against the key consuming the most RAM.
4. Run `MEMORY USAGE key SAMPLES 0` **only on test collections**.
5. Record the cost and note observations about sampling.

### Exercise 3 — Measuring JSON Values After Serialization

1. Create a DTO containing Vietnamese text/emoji.
2. Serialize into UTF-8 bytes.
3. Compare `bytes.length` and `String.length()`.
4. Enforce an example 32 KiB cap.
5. Test payloads just under, equal to, and over the cap; ensure oversized payloads are rejected without writing.

### Exercise 4 — Race-Free Set Capping

1. Test the `SCARD`-then-`SADD` pattern under 20 concurrent workers.
2. Replace it with atomic Lua.
3. Check the final `SCARD`.
4. Retry an already-present member when the Set is full.
5. Add a bytes/member limit to block oversized single members.

### Exercise 5 — Sliding Window and Top-N

1. Use a Sorted Set to record activity with timestamp scores.
2. Prune old members with `ZREMRANGEBYSCORE`.
3. Verify cardinality with `ZCARD`.
4. Build a leaderboard and trim by rank to keep Top 100.
5. Read by page instead of loading the entire Set.

### Exercise 6 — Comparing Key Explosion vs Hash

1. Create 10,000 String keys each holding one simulated field.
2. Measure `INFO memory`.
3. Clean up the test keys safely.
4. Store the same data inside one or several Hashes along business boundaries.
5. Re-measure memory, latency, and single-field read cost.
6. Explain the trade-off: fewer Hash keys vs big/hot key risk.

### Exercise 7 — Bounding Streams

1. Create a test Stream with `XADD MAXLEN ~ 1000`.
2. Append more than 1,000 entries.
3. Observe that `XLEN` can exceed 1,000.
4. Create a consumer group and leave one message pending.
5. Evaluate retention impact on PEL/payloads; design around realistic downtime.

### Exercise 8 — Redis Cluster and Hot Slots

1. In a test Cluster, create keys sharing hash tag `{all}` and inspect `CLUSTER KEYSLOT`.
2. Create keys tagged by partition.
3. Observe slot distribution.
4. Explain why a single big key does not split automatically when adding primaries.
5. Propose a partitioning scheme satisfying both same-slot needs and scaling.

## 31. Production Readiness Design Checklist

1. Does every namespace have a **max value bytes** limit measured after serialization?
2. Are key length and member ID length bounded?
3. Did you choose the right structure for the query pattern: String, Hash, Set, ZSet, Stream?
4. Is there a cardinality cap or retention policy on ever-growing collections?
5. Are hard caps enforced atomically under concurrency?
6. Do endpoints enforce a max page size and avoid loading full collections?
7. Does `SCAN` use cursors, close resources, and bound operational impact?
8. Are `KEYS *`/`SMEMBERS`/`HGETALL` eliminated from paths that can encounter large data?
9. Do transient keys have TTL/cleanup or a source of truth for recovery?
10. Is key count budgeted via traffic × lifetime plus peak headroom?
11. Have you distinguished big keys from hot keys and hot slots?
12. Are Redis `MEMORY USAGE`/`INFO memory` measured alongside network/JVM p99?
13. Does the eviction policy match data criticality?
14. With Spring Cache, are page/query combinations and serializers bounded?
15. With Redis Streams, does retention account for PEL, ACK, and slow consumers?
16. With Cluster, is data distribution verified across all primaries?
17. Does big-key cleanup use `UNLINK`/bounded jobs where appropriate?
18. Are there integration tests with production-scale data and concurrency checks?
19. Do thresholds have dashboards, alerts, and clear owners?
20. Is there a migration/repartitioning plan if the dataset outgrows initial bounds?

## 32. Conclusion

Controlling Redis performance cannot rely solely on "Redis runs in RAM." **Single-value size**, **collection element count**, and **total key count** are three distinct cost drivers; hot keys and hot slots compound them.

For values, measure **serialized bytes**, enforce limits on the write path, and use pagination or external references instead of giant JSON blobs. For Sets/Hashes/Lists/ZSets, check cardinality with dedicated commands, avoid full-collection loads, and use Lua for race-free hard caps. For Streams, size retention around consumer groups and remember `MAXLEN ~` is approximate. For total key counts, design TTLs/lifecycles, budget by traffic, clean up safely, and avoid creating a key for every transient event.

Finally, use `MEMORY USAGE`, `INFO memory`, `--bigkeys`/`--memkeys`, and `SCAN` to understand real data; combine them with SLOWLOG, network metrics, JVM/GC, and p99 latency to locate true bottlenecks. **Limits must be tested on real Redis under your target workload and server version**, because a system with millions of small keys and a system with one million-field Hash require completely different optimization strategies.

## References

- [Redis — MEMORY USAGE](https://redis.io/docs/latest/commands/memory-usage/): bytes/key, overhead, and `SAMPLES`.
- [Redis — SCAN](https://redis.io/docs/latest/commands/scan/): cursor, `COUNT`, duplicates, and consistency guarantees.
- [Redis — Redis CLI](https://redis.io/docs/latest/develop/tools/cli/): `--bigkeys`, `--memkeys`, `--keystats`, and scan options.
- [Redis — STRLEN](https://redis.io/docs/latest/commands/strlen/): byte length of a Redis String.
- [Redis — HLEN](https://redis.io/docs/latest/commands/hlen/): counting Hash fields.
- [Redis — SCARD](https://redis.io/docs/latest/commands/scard/): counting Set members.
- [Redis — ZCARD](https://redis.io/docs/latest/commands/zcard/): counting Sorted Set members.
- [Redis — LLEN](https://redis.io/docs/latest/commands/llen/): counting List entries.
- [Redis — XADD](https://redis.io/docs/latest/commands/xadd/): `MAXLEN` and Stream trimming.
- [Redis — UNLINK](https://redis.io/docs/latest/commands/unlink/): unlinking keys and asynchronous memory reclamation.
- [Redis — Memory optimization](https://redis.io/docs/latest/management/optimization/memory-optimization/): compact encodings, listpack, and CPU/RAM trade-offs.
- [Redis — Diagnosing latency](https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/latency/): big collections, blocking commands, and latency measurement.
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html): templates, serializers, and Redis operations.
- [Spring Data Redis — RedisTemplate API](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/core/RedisTemplate.html): `scan`, `unlink`, and Cursor management.
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html): cache configuration, serializers, TTL, and prefixes.
- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html): stream retention and consumer groups.
