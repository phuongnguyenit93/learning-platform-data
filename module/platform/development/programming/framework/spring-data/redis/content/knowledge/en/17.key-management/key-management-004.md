# Why You Must Be Cautious with KEYS and Large Data Scanning Commands

## 1. A Key-Lookup Operation Can Affect the Entire System

Suppose a Spring Boot application uses Redis to store login sessions, product caches, and API rate-limit counters:

~~~text
session:1234
session:5678
product:cache:1001
product:cache:1002
rate-limit:user:42
...
~~~

When you need to inspect or clean up the product cache, the natural approach seems to be finding all keys starting with `product:cache:` and then deleting them. Someone new to Redis might write:

~~~redis
KEYS product:cache:*
~~~

Or call it directly in Spring Data Redis:

~~~java
Set<String> keys = stringRedisTemplate.keys("product:cache:*");
~~~

Both approaches share a problem: **Redis has to traverse the database keyspace to determine which keys match**, even if the result contains only a few keys. When key counts grow into the millions and Redis is serving many other requests, a seemingly small administrative operation can raise latency for business requests.

This lesson belongs to the **Key Management** group in **Spring Data Redis**. The goal is to understand why bulk lookups require caution, how to scan incrementally using `SCAN` and `Cursor`, and when to design data so scanning is unnecessary.

## 2. Why Can KEYS Cause Bottlenecks?

### 2.1. What Does KEYS Do?

Syntax:

~~~redis
KEYS pattern
~~~

`pattern` uses glob-style matching, for example:

| Pattern | Meaning |
|---|---|
| `KEYS *` | Find all keys in the currently selected Redis database |
| `KEYS session:*` | Find keys with prefix `session:` |
| `KEYS product:cache:????` | Find keys with exactly four characters after the prefix |
| `KEYS user:[12]:*` | Find keys in the `user:1:` or `user:2:` groups |

**The complexity of `KEYS` is O(N)**, where `N` is the number of keys that must be examined, not just the number of keys returned. For example, if a store holds 5 million keys and only 10 match `product:cache:*`, Redis still performs work proportional to the size of that key store.

The result of `KEYS` is returned all at once. If many keys match the pattern, besides Redis traversal time, you also pay the cost of:

- Building and transmitting a large response over the network.
- Holding the result set in the caller's memory, especially when Spring Data Redis returns `Set<String>`.
- Deserializing key data through the encoder/decoder (`serializer`).
- Processing the entire result on the application side, potentially triggering thousands or millions of follow-up commands.

### 2.2. How Does Redis Process Commands?

Standard Redis command execution happens sequentially on the main command-processing thread. When one command consumes a lot of CPU time, other commands may have to wait before being served. Redis has separate I/O and background mechanisms, but they do not make a long `KEYS` command non-blocking.

Example:

~~~text
Time       ───────────────────────────────────────────────>

Client A: GET session:1234 ── ✓
Client B:                KEYS product:cache:* ────────── ✓
Client C:                      GET session:5678       ── ✓
Client D:                         INCR rate-limit:*  ─── ✓
                                  ↑
                           B and subsequent commands
                           may see increased latency
~~~

A `KEYS` command in a small test environment may run quickly. However, **execution time in testing is not enough to guarantee safety in production**, where data scale, concurrent load, hardware, and Redis topology can differ.

### 2.3. Common Design Mistake Example

~~~java
@Service
public class CacheMaintenanceService {

    private final StringRedisTemplate redis;

    public CacheMaintenanceService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    // Unsuitable for calling on a high-traffic request path.
    public long deleteAllProductCache() {
        Set<String> keys = redis.keys("product:cache:*");

        if (keys == null || keys.isEmpty()) {
            return 0L;
        }

        Long deleted = redis.delete(keys);
        return deleted == null ? 0L : deleted;
    }
}
~~~

This snippet carries two distinct risks:

1. `keys(...)` can scan the entire keyspace and produce a very large result set.
2. `delete(keys)` can perform a massive bulk deletion. With large structured values, synchronous memory freeing further increases Redis busy time.

Simply moving `KEYS` into a background task in Spring Boot does not solve the fact that Redis still has to execute a heavy command.

## 3. SCAN Splits Scanning into Small Rounds

Redis provides a family of incremental scanning commands:

| Command | Scan Scope |
|---|---|
| `SCAN` | Keys in the Redis database |
| `HSCAN` | Fields and values in a Hash |
| `SSCAN` | Elements of a Set |
| `ZSCAN` | Elements and scores in a Sorted Set |

`SCAN` does not return the entire result in a single call. It takes a **cursor** and returns a new cursor alongside the list of keys from the current round. The caller uses the new cursor to continue.

~~~redis
SCAN 0 MATCH product:cache:* COUNT 200
~~~

Visualizing a scan cycle:

~~~text
SCAN 0 MATCH product:cache:* COUNT 200
    │
    ├── next cursor: 348
    └── key list: [product:cache:1, product:cache:5, ...]

SCAN 348 MATCH product:cache:* COUNT 200
    │
    ├── next cursor: 772
    └── key list: [product:cache:9, ...]

SCAN 772 MATCH product:cache:* COUNT 200
    │
    ├── next cursor: 0
    └── key list: [...]
    
cursor = 0 in the RESULT of a round ⇒ one full scan pass complete
~~~

The cursor numbers above are illustrative only; actual values depend on data state.

### 3.1. COUNT Is a Hint About Workload

`COUNT 200` **does not mean** Redis will definitely return exactly 200 keys, or never return more than 200 keys. It is a hint adjusting the amount of work performed per round.

Redis may return fewer, more, or even zero keys in a scan round. If the returned cursor is still non-zero, the scan **has not finished**, even if that round's key list is empty.

Increasing `COUNT` generally reduces network round trips but can increase individual command duration. Decreasing `COUNT` splits work into smaller chunks but increases network round trips. An appropriate value depends on data size, Redis latency, network, and system load; there is no single safe default for every application.

### 3.2. MATCH Does Not Turn SCAN into an Indexed Query

`MATCH product:cache:*` filters results matching the pattern. Redis still has to traverse portions of the keyspace to find matches. It does not automatically build an index for the `product:cache:` prefix.

If only 1 in 100,000 keys has the target prefix, many scan rounds may return empty lists; the total amount of work remains significant. **`SCAN` reduces the risk of a single long-running command, but it does not eliminate total scan cost.**

In terms of complexity, a single `SCAN` call has a small average cost, whereas a full scan pass has a total cost of **O(N)**. Actual duration per round is still affected by `COUNT`, the filter pattern, and data structure state.

### 3.3. SCAN Does Not Provide a Consistent Data Snapshot

While the scan runs, other clients may add, delete, or expire keys. As a result:

- A key **may appear multiple times**. Processing logic must tolerate encountering the same key again.
- Keys added or deleted during the scan **may or may not appear**, depending on timing.
- Keys continuously present from the start to the end of a full scan pass are guaranteed by Redis to be returned at least once.
- A scan over an unbounded, continuously growing dataset may struggle to finish.
- You cannot treat the results of a `SCAN` pass as an exact list of keys at a single point in time.

Therefore, if you need batch deletion, statistics updates, or data processing, design operations to be **safely repeatable (idempotent)**. If business requirements demand a consistent snapshot or absolute accuracy, simple key scanning does not meet that requirement.

## 4. Using SCAN in Spring Data Redis

### 4.1. Appropriate Usage with StringRedisTemplate

Spring Data Redis supports `scan(ScanOptions)` and returns `Cursor<K>`. The example below fetches **at most 50 sample keys** from the cache namespace without loading all keys into a large collection.

~~~java
import java.util.LinkedHashSet;
import java.util.Set;

import org.springframework.data.redis.core.Cursor;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ScanOptions;
import org.springframework.stereotype.Service;

@Service
public class ProductCacheKeyInspector {

    private static final String PREFIX = "product:cache:";

    private final StringRedisTemplate redis;

    public ProductCacheKeyInspector(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Set<String> sampleKeys() {
        ScanOptions options = ScanOptions.scanOptions()
                .match(PREFIX + "*")
                .count(200)
                .build();

        Set<String> sample = new LinkedHashSet<>();

        // Cursor holds connection resources during the scan.
        try (Cursor<String> cursor = redis.scan(options)) {
            while (cursor.hasNext() && sample.size() < 50) {
                String key = cursor.next();

                if (key != null && key.startsWith(PREFIX)) {
                    sample.add(key);
                }
            }
        }

        return sample;
    }
}
~~~

Explanation of the key points:

1. `StringRedisTemplate` uses strings for key names and keeps the code readable.
2. `ScanOptions` specifies the filter pattern and `COUNT`. This is still incremental scanning, not an indexed lookup.
3. `Cursor<String>` provides a way to iterate results without receiving the entire key list from the server in a single response.
4. The `try-with-resources` block closes the cursor even if an exception occurs or iteration stops after 50 keys. Closing the cursor frees connection resources held by Spring Data Redis.
5. `LinkedHashSet` removes duplicate keys in the small sample. Memory grows only up to the 50-item cap in this example.
6. `startsWith(PREFIX)` reinforces the intent to handle a specific namespace; here the fixed prefix pattern is controlled by the application.

This is a **sampling function for inspection**, not an inventory of every key. Once 50 items are reached, the scan stops intentionally.

> In an application using Redis Cluster, scan scope must be verified according to your configuration and driver. A `SCAN` pass on one node only scans keys belonging to that node. Do not assume that a cursor from an arbitrary connection covers every node in the cluster.

### 4.2. Why Shouldn't You Call keys() in an Endpoint?

Compare the two:

~~~java
// May scan the entire keyspace and return a large result set.
Set<String> allKeys = redis.keys("product:cache:*");

// Incremental scan; the application bounds the number of keys kept in memory.
try (Cursor<String> cursor = redis.scan(
        ScanOptions.scanOptions()
                .match("product:cache:*")
                .count(200)
                .build())) {

    int inspected = 0;
    while (cursor.hasNext() && inspected < 100) {
        String key = cursor.next();
        // Fast processing, avoiding side effects when keys repeat.
        inspected++;
    }
}
~~~

The `inspected < 100` bound here limits **the number of items the program receives and processes**, not strictly 100 internal Redis operations or total keys examined. The workload of `SCAN` still depends on how Redis finds matching keys.

For displaying paginated lists to end users, Redis cursors are **not** stable page numbers: data can change, keys can repeat, and a single call does not guarantee an item count. If a business feature needs stable pagination or sorting, store an appropriate index from the start.

### 4.3. Scanning for Cleanup: Control the Processing Step Too

When you must clean up keys by prefix, you can use `SCAN` to collect keys in small batches, then use `UNLINK` to instruct Redis to remove them from the keyspace and perform expensive memory reclamation asynchronously where appropriate.

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.redis.core.Cursor;
import org.springframework.data.redis.core.ScanOptions;
import org.springframework.data.redis.core.StringRedisTemplate;

// Intended only for maintenance tasks with a defined namespace scope.
public long unlinkSomeProductCacheKeys(StringRedisTemplate redis) {
    String prefix = "product:cache:";
    ScanOptions options = ScanOptions.scanOptions()
            .match(prefix + "*")
            .count(200)
            .build();

    List<String> batch = new ArrayList<>(100);
    long submitted = 0;
    long maxSubmitted = 1_000;

    try (Cursor<String> cursor = redis.scan(options)) {
        while (cursor.hasNext() && submitted < maxSubmitted) {
            String key = cursor.next();

            if (key == null || !key.startsWith(prefix)) {
                continue;
            }

            batch.add(key);
            submitted++;

            if (batch.size() >= 100) {
                redis.unlink(batch);
                batch.clear();
            }
        }
    }

    if (!batch.isEmpty()) {
        redis.unlink(batch);
    }

    return submitted;
}
~~~

**Meaning and limitations of the example:**

- `100` is the deletion command batch size; `1_000` is the cap on keys submitted during a single maintenance pass. Both numbers are examples to tune from real measurements.
- Use only prefixes the job is authorized to manage. Never interpolate arbitrary user-supplied glob patterns and perform bulk deletion.
- `submitted` counts how many times keys were passed to the command, **not how many keys were actually deleted**: the cursor may return duplicates, keys may expire or be deleted by another process; the return value of `unlink(...)` reflects the keys Redis actually unlinked in each command.
- `UNLINK` lowers the risk of blocking Redis when reclaiming large values, but it does not make scanning cost disappear and does not eliminate all CPU, memory, or I/O impact.
- Do not pile every key across the entire system into a single list before deleting. For large jobs, prefer small batches, rate limiting, run caps, and pause capability.
- When writes continue steadily into the same namespace, scan-and-delete can affect newly created keys. You need business rules on data age or namespace versioning rather than blindly deleting everything matching a pattern.

In real environments, deletion should be governed by an operational job with clear permissions and scope rather than triggered ad hoc from user requests.

## 5. Other Commands That Can Also Cause Heavy Load

Being cautious with `KEYS` does not mean simply swapping every `KEYS` for `SCAN`. Commands that fetch **an entire large data structure** can also generate heavy responses and consume processing time.

| Need | Risky Operation on Large Data | Better Approach |
|---|---|---|
| List keys across the database | `KEYS *` or `KEYS prefix:*` | `SCAN` in batches, scoped and rate-limited |
| Read an entire Set | `SMEMBERS key` | `SSCAN` or design element-level access |
| Read an entire Hash | `HGETALL key` | `HSCAN` or `HMGET` needed fields |
| Read an entire Sorted Set | `ZRANGE key 0 -1` | Slice by rank/score range, or `ZSCAN` when iterating |
| Read an entire List | `LRANGE key 0 -1` | `LRANGE` in small slices |
| Delete many keys/large values | `DEL` on large amounts of data | Small batches; consider `UNLINK` with appropriate semantics |
| Inventory every value in one request | Unbounded read loops and processing | Offload to background jobs, set resource budgets, use indexes |

`SCAN` scans database keys, whereas `HSCAN`, `SSCAN`, and `ZSCAN` scan **elements within a data structure**. They are not interchangeable. `LRANGE` typically needs index-range slicing; Redis has no equivalent `LSCAN`.

Also separate **scanning** from **post-scan processing**. Running `SCAN` and then calling a huge value-read command for every key, or firing an enormous `UNLINK` batch, can still overload the system.

## 6. Designing Data to Avoid Scanning Every Key

A better approach for many business requirements is knowing keys upfront or maintaining an intentional access structure.

### 6.1. Knowing Keys from Business Identifiers

If the API already knows product ID `1001`, access it directly:

~~~java
String key = "product:cache:1001";
String value = redis.opsForValue().get(key);
~~~

Direct access to a known key avoids pattern scanning.

### 6.2. Using TTL for Temporary Data

Caches should have a time-to-live when business rules permit:

~~~java
redis.opsForValue().set(
        "product:cache:1001",
        jsonPayload,
        java.time.Duration.ofMinutes(15)
);
~~~

With an appropriate TTL, Redis expires keys automatically. The need to run a scan job to clear the whole cache drops substantially. However, TTL does not replace requirements that demand immediate revocation.

### 6.3. Maintaining a Dedicated Index When Listing Is Needed

If you frequently need to know the products belonging to a category, you can maintain an index Set:

~~~redis
SADD category:42:product-ids 1001 1002 1003
SMEMBERS category:42:product-ids
~~~

For very large sets, also avoid `SMEMBERS` and use `SSCAN` or a suitable paginated query approach.

Maintaining an index requires keeping data keys and the index consistent across adds, deletes, and expirations. For example, a cache key expires automatically, but its member in the Set does not disappear on its own. Therefore, this index is an architectural choice with its own update and cleanup costs, not a free solution.

### 6.4. Versioning Namespaces to Invalidate Caches

If the task is to invalidate the entire cache of a data group, you can use versioning:

~~~text
product:cache:v17:1001
product:cache:v17:1002

Switch active version from v17 to v18:

product:cache:v18:1001
product:cache:v18:1002
~~~

New requests only access `v18`. Keys under `v17` expire via TTL. This avoids having to scan and delete every key at the moment of a version switch, provided the application manages cache versions consistently.

## 7. Operational Principles for Large Datasets

Practical guidelines when writing Redis applications or administrative jobs:

1. **Define scope before scanning.** Know the exact database, namespace, key owner, and impact of reading or deleting.
2. **Never place full-store scan commands on latency-sensitive request paths.** If scanning is necessary, use rate- and resource-limited maintenance jobs.
3. **Set bounds on time, key count, batch size, and cancellation.** Even `SCAN` can take a long time if a job runs continuously until every key is visited.
4. **Close cursors.** In Spring Data Redis, `Cursor` must be closed after processing to avoid holding connection resources.
5. **Accept duplicates and concurrent mutations.** Perform only actions safe to repeat; do not rely on `SCAN` for exact counts of changing data.
6. **Observe real metrics.** Measure command latency, CPU, memory, bandwidth, commands per second, and application-side latency during scans. `SLOWLOG` and `LATENCY DOCTOR` can help investigate slowdowns.
7. **Account for deployment topology.** In Redis Cluster, scanning must account for keys distributed across nodes; in multi-tenant environments, broad key patterns can touch unintended data.
8. **Prefer directly addressable data.** TTLs, purposeful indexes, and cache versioning are usually better than periodically finding every key by pattern.

## 8. Hands-On: Comparing KEYS and SCAN in a Test Environment

Run this on a development Redis instance or test database, never on a shared production datastore.

Create a few sample keys:

~~~redis
SET product:cache:1001 "A"
SET product:cache:1002 "B"
SET product:cache:1003 "C"
SET session:1 "user-1"
~~~

Find keys with `KEYS`:

~~~redis
KEYS product:cache:*
~~~

Scan incrementally:

~~~redis
SCAN 0 MATCH product:cache:* COUNT 2
~~~

Take the cursor from the previous response and continue:

~~~redis
SCAN <cursor-from-previous-round> MATCH product:cache:* COUNT 2
~~~

Repeat until **the returned cursor is `0`**. If a round returns no keys while the cursor is still non-zero, you must keep going. Do not assume the returned key count equals the `COUNT` value.

You can use the CLI tool to automatically scan keys under a prefix:

~~~bash
redis-cli --scan --pattern 'product:cache:*'
~~~

This tool handles the cursor loop for you. However, if you do not limit output and print millions of keys, the client machine still has to receive and process huge amounts of data; using `--scan` does not automatically guarantee a lightweight operation.

### Check-Your-Understanding Questions

**Scenario A:** A database has 2 million keys, and only 20 start with `invoice:`. Does calling `KEYS invoice:*` only examine 20 keys?

No. Search cost still depends on the size of the keyspace traversed. Few results do not mean little work.

**Scenario B:** `SCAN 0 MATCH invoice:* COUNT 100` returns an empty array and cursor `912`. Can you conclude no matching keys exist?

No. You must continue with cursor `912` until you receive cursor `0`, unless intentionally stopped by a job limit.

**Scenario C:** A scan job sees the same key twice and needs to increment a business counter. What can happen?

If it increments on every appearance, the count can exceed reality. You need a deduplication strategy, a better data source for exact counting, or an idempotent operation design.

**Scenario D:** Is replacing `DEL` with `UNLINK` and using `KEYS *` to fetch millions of keys before deleting safe?

No. `UNLINK` may reduce synchronous memory-reclamation cost, but `KEYS *` still scans the entire keyspace and builds a massive result. You should revisit the deletion goal, scope, TTL/namespace mechanisms, and bounded batch processing.

## 9. Takeaways

- `KEYS` is useful for exploring small datasets or controlled ad-hoc tasks, but it has **O(N)** complexity and can raise Redis latency when the key store is large.
- `SCAN` splits traversal into multiple rounds; it does **not** turn pattern matching into an indexed lookup or provide a consistent data snapshot.
- `COUNT` is a hint; only a returned cursor of `0` indicates the end of the scan.
- In Spring Data Redis, prefer `scan(ScanOptions)` and **close the `Cursor`**, while bounding in-memory data and application-side work.
- For repeated access needs, consider key design, TTLs, index structures, or cache versioning to avoid scanning all data.

### References

- Redis — [KEYS](https://redis.io/docs/latest/commands/keys/).
- Redis — [SCAN and the SCAN command family](https://redis.io/docs/latest/commands/scan/).
- Spring Data Redis — [RedisTemplate API](https://docs.spring.io/spring-data/redis/docs/3.5.x/api/org/springframework/data/redis/core/RedisTemplate.html).
