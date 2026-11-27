# Scanning and Deleting by Group Within a Namespace with Spring Data Redis

## 1. Problem Statement and Goal

In an application using Spring Data Redis, many kinds of data may coexist inside a single Redis database: product caches, session states, temporary order data, deduplication keys, counters, and multi-tenant data. When you need to clean up data for **one specific group**, you must accurately identify the keys belonging to that group before deleting them.

For example, an order management system stores the keys:

```text
shop:orders:v1:tenant:42:state:OPEN:1001
shop:orders:v1:tenant:42:state:OPEN:1002
shop:orders:v1:tenant:42:state:DONE:1003
shop:orders:v1:tenant:73:state:OPEN:2001
shop:products:v1:item:1001
```

Requirement: clean up the `OPEN` order group for tenant `42`. Only the first two keys should be processed; the `DONE` key, tenant `73`, and the `products` group must remain untouched.

This lesson focuses on three steps:

1. Designing a **namespace** (key name prefix) specific enough to demarcate data ownership.
2. Incrementally scanning keys belonging to the namespace using `SCAN MATCH` instead of blocking the entire keyspace with `KEYS`.
3. Deleting in batches with `UNLINK` or `DEL`, while controlling scope, system load, and concurrent data mutations.

**Limitation of the technique:** Redis has no concept of physical directories or namespaces like a filesystem. A namespace is purely a naming convention; Redis treats each key name as an independent string. Choosing the right prefix and search pattern is therefore the application's responsibility.

## 2. Designing a Namespace to Select the Right Group

A convention should reflect the application, data domain, version, and grouping dimensions you need to manage:

```text
<application>:<domain>:<version>:tenant:<tenantId>:state:<state>:<entityId>
```

In the example:

| Component | Example | Role |
|---|---|---|
| Application and domain | `shop:orders` | Distinguishes from other data domains |
| Version | `v1` | Enables schema changes or cleanup of old versions |
| Tenant | `tenant:42` | Isolates data by tenant |
| State | `state:OPEN` | Group of keys to operate on |
| Identifier | `1001` | Identifies each individual key |

The prefix of the group to delete is:

```text
shop:orders:v1:tenant:42:state:OPEN:
```

The scan pattern is that prefix plus `*`:

```text
shop:orders:v1:tenant:42:state:OPEN:*
```

The trailing `:` at the end of the prefix is critical. Searching for `...:state:OPEN*` could also match `OPEN_ARCHIVED` or `OPENED`. The tighter the prefix, the lower the risk of accidentally deleting unrelated data.

### Never Inject Arbitrary Strings into Scan Patterns

In Redis, `MATCH` uses *glob* syntax: `*` matches multiple characters, `?` matches one character, `[abc]` matches one character in the given set. Consequently, if a user-supplied `tenantId` contains special characters, the scan could expand unintentionally.

Validate each dynamic segment against strict rules, such as allowing only letters, digits, underscores, and hyphens. Never accept an arbitrary `pattern` directly from an HTTP request to execute a group deletion. Also clearly separate namespaces used for cache data from namespaces holding authoritative business data: cache deletions are recoverable, whereas deleting source data usually requires separate business workflows and controls.

## 3. Why Use SCAN Instead of KEYS?

Both commands can filter key names by pattern, but they work differently:

| Criterion | `KEYS pattern` | `SCAN cursor MATCH pattern COUNT n` |
|---|---|---|
| How results are fetched | Returns the entire matching list in one command | Traverses incrementally across multiple commands and a cursor |
| Impact on a large keyspace | Can block Redis during lookup, producing a huge result | Distributes work across rounds, better suited for operations |
| Client memory | May have to hold a very large list | Can process key by key or in small batches |
| Consistency | Reflects a single command execution | Not an immutable snapshot when the keyspace changes |
| Typical usage | Controlled diagnostics on small datasets | Maintenance tasks, browsing, and group deletion |

Redis CLI example:

```redis
SCAN 0 MATCH shop:orders:v1:tenant:42:state:OPEN:* COUNT 500
```

Redis returns a **new cursor** and a list of keys. The client keeps passing the returned cursor, even when a round's list is empty. A full traversal ends only when the cursor returns `0`.

`COUNT 500` is a workload hint per round, **not** a guarantee of returning exactly 500 keys. `MATCH` filters the keys scanned in each round; a pattern matching very few keys may still require many rounds to scan the whole keyspace. The total complexity of a full `SCAN` pass still depends on the size of the key set being scanned.

**SCAN guarantees to remember:**

- A scan pass may return **the same key multiple times**; downstream operations must be safely repeatable.
- Keys appearing or disappearing mid-scan may be seen or skipped.
- A completed pass will see keys that existed continuously from start to finish, but does not produce a consistent point-in-time snapshot.
- A round returning an empty list does not mean scanning is finished.

`SCAN` suits cleanup tasks that can be rerun safely. If the problem requires a **fixed, exact, zero-miss** set of keys under concurrent writes, add coordination with writers or maintain a dedicated group index.

## 4. Scanning Keys with StringRedisTemplate

For plain UTF-8 string key names, `StringRedisTemplate` avoids mismatches with key serialization from another configured `RedisTemplate`. Spring Data Redis provides `scan(ScanOptions)` returning a `Cursor<String>`; the cursor must be closed after use.

Example of a service that only previews a subset of keys in a group:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Pattern;

import org.springframework.data.redis.core.Cursor;
import org.springframework.data.redis.core.ScanOptions;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderKeyBrowser {

    private static final String ROOT = "shop:orders:v1:";
    private static final Pattern SAFE_SEGMENT =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");

    private final StringRedisTemplate redis;

    public OrderKeyBrowser(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public List<String> previewOpenOrders(String tenantId, int maxResults) {
        validateSegment(tenantId);

        if (maxResults < 1 || maxResults > 200) {
            throw new IllegalArgumentException("maxResults must be 1..200");
        }

        String prefix = ROOT + "tenant:" + tenantId + ":state:OPEN:";
        ScanOptions options = ScanOptions.scanOptions()
                .match(prefix + "*")
                .count(500)
                .build();

        List<String> keys = new ArrayList<>();

        try (Cursor<String> cursor = redis.scan(options)) {
            while (cursor.hasNext() && keys.size() < maxResults) {
                String key = cursor.next();

                // Guard against unexpected pattern structure changes.
                if (key.startsWith(prefix)) {
                    keys.add(key);
                }
            }
        }

        return keys;
    }

    private static void validateSegment(String value) {
        if (value == null || !SAFE_SEGMENT.matcher(value).matches()) {
            throw new IllegalArgumentException("Invalid tenantId");
        }
    }
}
```

Example:

```java
List<String> sample = browser.previewOpenOrders("42", 20);
sample.forEach(System.out::println);
```

The method returns **up to 20 key names for preview**, not an exact count of the entire group. Stopping the cursor early at this limit is acceptable for a preview feature; never use the list size to infer the total number of existing keys.

For `RedisTemplate<K, V>` with a different serializer, identify the exact key serializer. Do not decode or delete `byte[]` by guessing string names if keys are actually stored in a binary format.

## 5. Deleting a Group in Batches with SCAN and UNLINK

After previewing, a maintenance job can continue scanning and deleting in batches. In Redis:

- `DEL key [key ...]` deletes keys and frees memory synchronously; freeing certain large data structures can cause latency spikes.
- `UNLINK key [key ...]` unlinks keys from the keyspace and frees memory in a Redis background task. This is typically the right choice for multi-key cache cleanup on Redis versions supporting `UNLINK` (Redis 4.0 and later).
- Both commands return **the number of keys actually removed**, which may be lower than requested because keys expired, were already deleted, or were returned as duplicates during scanning.

The example below applies to **standalone Redis or Redis Sentinel**, where a multi-key delete command is sent to a single Redis server. The group is scoped strictly to a tenant and order state.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Pattern;

import org.springframework.data.redis.core.Cursor;
import org.springframework.data.redis.core.ScanOptions;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderKeyCleanupService {

    private static final String ROOT = "shop:orders:v1:";
    private static final Pattern SAFE_SEGMENT =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");

    private static final int SCAN_COUNT_HINT = 500;
    private static final int UNLINK_BATCH_SIZE = 200;

    private final StringRedisTemplate redis;

    public OrderKeyCleanupService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    /**
     * Call only from an authenticated, permission-restricted maintenance task.
     * Returns the number of keys actually unlinked, not the number of keys scanned.
     */
    public long deleteOrderStateGroup(String tenantId, String state) {
        String prefix = groupPrefix(tenantId, state);

        ScanOptions options = ScanOptions.scanOptions()
                .match(prefix + "*")
                .count(SCAN_COUNT_HINT)
                .build();

        List<String> batch = new ArrayList<>(UNLINK_BATCH_SIZE);
        long removed = 0;

        try (Cursor<String> cursor = redis.scan(options)) {
            while (cursor.hasNext()) {
                String key = cursor.next();

                // Re-verify the full authorized prefix.
                if (!key.startsWith(prefix)) {
                    continue;
                }

                batch.add(key);

                if (batch.size() >= UNLINK_BATCH_SIZE) {
                    removed += unlinkBatch(batch);
                    batch.clear();
                }
            }
        }

        if (!batch.isEmpty()) {
            removed += unlinkBatch(batch);
        }

        return removed;
    }

    private long unlinkBatch(List<String> keys) {
        Long count = redis.unlink(List.copyOf(keys));
        if (count == null) {
            throw new IllegalStateException("UNLINK returned no count");
        }
        return count;
    }

    private static String groupPrefix(String tenantId, String state) {
        validateSegment(tenantId, "tenantId");
        validateSegment(state, "state");
        return ROOT + "tenant:" + tenantId + ":state:" + state + ":";
    }

    private static void validateSegment(String value, String field) {
        if (value == null || !SAFE_SEGMENT.matcher(value).matches()) {
            throw new IllegalArgumentException("Invalid " + field);
        }
    }
}
```

Intended invocation:

```java
long removed = cleanupService.deleteOrderStateGroup("42", "OPEN");
System.out.println("Removed keys: " + removed);
```

Processing flow:

1. Validate each dynamic segment and build a prefix with a trailing delimiter.
2. Build `ScanOptions` to filter keys belonging to the group.
3. Read from the cursor incrementally; do not load all keys into a large `Set`.
4. Accumulate up to 200 key names, call `unlink(Collection<String>)`, and clear the list.
5. When the cursor finishes, delete the remaining final batch and return the count confirmed unlinked by Redis.

The 200-key limit is **the size of each delete command**, not a cap on how many keys the whole job can delete. `COUNT` and batch size are independent parameters: the first affects how Redis scans, while the second affects how many keys are sent per `UNLINK` command. Tune both by measuring load, latency, and actual cleanup throughput.

**Note on mid-run failures:** If an `UNLINK` command or connection fails after several batches have already succeeded, the call may throw an exception even though Redis has already deleted part of the data. Never infer "the whole job did not run" from an exception. Persist job progress, allow reruns, and treat deleting an already-absent key as safe.

### When to Use DEL?

You can replace `redis.unlink(keys)` with `redis.delete(keys)` when the system requires `DEL`, such as when Redis does not support `UNLINK` or infrastructure specifics demand it. On large datasets, evaluate latency because `DEL` can free objects synchronously. Do not grow batch sizes unboundedly for either option.

## 6. Testing Operations on Redis CLI in a Test Environment

Create sample data using key names matching the example convention:

```redis
SET shop:orders:v1:tenant:42:state:OPEN:1001 "draft-A"
SET shop:orders:v1:tenant:42:state:OPEN:1002 "draft-B"
SET shop:orders:v1:tenant:42:state:DONE:1003 "final-C"
SET shop:orders:v1:tenant:73:state:OPEN:2001 "draft-D"
SET shop:products:v1:item:1001 "product"
```

Inspect the group to process:

```redis
SCAN 0 MATCH shop:orders:v1:tenant:42:state:OPEN:* COUNT 100
```

Continue running `SCAN` with the cursor returned by Redis until the cursor returns to `0`. Key order and round counts are not fixed. After confirming the two keys in the target group, illustrate the delete command:

```redis
UNLINK shop:orders:v1:tenant:42:state:OPEN:1001 shop:orders:v1:tenant:42:state:OPEN:1002
```

Verify scope with `EXISTS`:

```redis
EXISTS shop:orders:v1:tenant:42:state:OPEN:1001
EXISTS shop:orders:v1:tenant:42:state:DONE:1003
EXISTS shop:orders:v1:tenant:73:state:OPEN:2001
```

If no other task writes or deletes concurrently, the expected results are `0`, `1`, and `1`, respectively. The CLI example explicitly deletes the two named keys. **Never** pass a wildcard pattern containing `*` directly to `UNLINK` or `DEL` expecting Redis to expand it: deletion commands take concrete key names, not patterns.

## 7. Safety When Multiple Processes Write Concurrently

`SCAN` and `UNLINK` do not form a transaction spanning the entire group. While other workers continue writing:

- A newly created key **after** the cursor has already passed its region may be left behind.
- Existing keys may expire via TTL or be deleted before the batch reaches them, lowering the count unlinked by `UNLINK`.
- A key may be seen by `SCAN`, deleted, and **recreated with the same name** before `UNLINK`. The delete command risks removing the new value.
- Writers continuously creating keys in the namespace will make cleanup results unstable; a single scan pass does not guarantee an empty namespace afterward.

Solutions depend on business requirements:

**"Best effort" cache cleanup.** Allow one or more reruns, track progress, use TTLs, and do not treat scan output as an atomic snapshot.

**Cleaning up an old namespace after a version switch.** First switch readers and writers to the new prefix, e.g., `shop:orders:v2:`, stop writing to `v1`, and then clean up `v1`. When you must be certain old writers have stopped, verify old processes have shut down or apply controlled version transitions before deleting.

**Group deletion with high consistency requirements.** Design a group index updated along the write/delete path, a maintenance job queue, or a key/version coordination mechanism paired with specific business operations. A distributed lock is only helpful if **every relevant writer** obeys that protocol; a lock by itself does not make `SCAN` atomic.

Do not use key-name cleanup jobs as a substitute for source-data retention or regulated data deletion workflows.

## 8. Redis Cluster: Mind Nodes and Hash Slots

Redis Cluster distributes keys by **hash slot**, so you should never treat an entire cluster as a single unified keyspace that can be scanned and deleted with any arbitrary command.

Differences from the example above:

- `SCAN` operates on the target node's keyspace. To clean a namespace whose keys live across multiple nodes, you must ensure all **primary nodes** holding those keys are scanned (Spring Data Redis provides `RedisClusterConnection.scan(RedisClusterNode, ScanOptions)`).
- A single `UNLINK key1 key2 ...` command sending multiple keys from different hash slots can fail with `CROSSSLOT`. A simple approach is deleting key by key via key routing; a more optimized approach is grouping batches by hash slot before issuing multi-key commands.
- When topology changes or resharding occurs mid-cleanup, the job needs a way to rerun and re-verify scope. Never infer that the whole cluster was scanned from one node's cursor.
- Redis provides `{...}` syntax to place keys into the same hash slot; use it only when the design needs multi-key same-slot operations and you have evaluated hot-node skew risks. A large tenant forced into one slot can create a hot node.

If the application uses Redis Cluster, implement cluster-aware scanning and slot-aware deletion paths before running real jobs. The `OrderKeyCleanupService` snippet above intentionally demonstrates standalone/Sentinel Redis connections only.

## 9. Reducing Operational Risk When Cleaning Large Namespaces

A job deleting a large number of keys should follow a clear process:

| Measure | Benefit and Application |
|---|---|
| Choose a specific prefix | Fix application, domain, version, and tenant; restrict input variables |
| Preview (dry run) | Print the pattern and sample keys for operator verification; this is not a full inventory |
| Confirm scope | Record tenant, state, environment, and requester before permitting the job to run |
| Operational quotas | Cap keys per batch, command rate, and concurrent jobs; support job cancellation |
| Track progress | Log keys scanned, keys unlinked, duration, errors, and group pattern; avoid logging sensitive data |
| Safe reruns | Design idempotent jobs and handle partially completed prior runs |
| Monitor load | Watch Redis latency, CPU, memory usage, and allocation/reclamation rates during runs |
| Access control | Only authorized jobs can delete; where appropriate, restrict Redis ACLs by key pattern |

For very large namespaces, a synchronous call on an HTTP thread can exceed request timeouts. Usually, move it to a background job with an identifier, progress status, batched execution, and stop controls. Do not use `KEYS` to "pre-count" in high-load environments; `DBSIZE` counts the whole database, not an individual namespace.

If you strictly need an **exact key count** before deleting, counting with `SCAN` under concurrent writes can still yield duplicates or misses. Use an index/metadata with an appropriate update contract, or pause writes and inventory during a coordinated window.

## 10. When Should You Avoid Namespace Scanning?

`SCAN MATCH` is very useful for periodic cleanup or data investigation, but it is not always the best design for features that need frequent group queries.

### Group Index Using a Redis Set

You can maintain a Set containing the key names belonging to a group:

```text
shop:orders:v1:index:tenant:42:state:OPEN
    -> shop:orders:v1:tenant:42:state:OPEN:1001
    -> shop:orders:v1:tenant:42:state:OPEN:1002
```

When writing a key, the application adds the key name to the Set via `SADD`; when deleting or changing groups, it updates the corresponding Set via `SREM`. When cleaning up, scan Set members with `SSCAN` and process each key. This avoids filtering across the entire keyspace, but increases write overhead and requires handling stale index entries (for example, keys whose TTL expired while their names remained in the Set).

### TTL and Versioned Namespaces

If data is only short-lived, setting a TTL when creating the key is usually simpler and safer than large-scale deletion jobs. For caches rebuilt from another source, switching to a versioned namespace and letting old versions expire naturally can reduce scan/delete work. Do not set default TTLs on long-lived data without defining its business lifecycle first.

### Deleting a Known Set of Specific Keys

If you already have a concrete list of keys, call `unlink(Collection<String>)` or `delete(Collection<String>)` directly without `SCAN`. When the item to remove is inside a `Hash` or `Set` structure, use field/member operations (`HDEL`, `SREM`, etc.) if the intent is removing an element rather than deleting the entire Redis key.

## 11. Common Pitfalls

| Symptom | Possible Cause | How to Handle |
|---|---|---|
| Deletes keys from another group | Pattern too broad, missing trailing `:` on prefix, input contains glob characters | Standardize prefix, validate segments, verify with dry run |
| Scans fewer keys than expected | `COUNT` misunderstood as total limit, stopping on empty list return | Follow cursor until end; remember `COUNT` is only a hint |
| Keys reappear after cleanup | Writers still active, concurrent TTL/writes, scanned only one cluster node | Coordinate writers, rerun, check entire cluster |
| Deleted count is lower than scanned count | Keys duplicated in `SCAN`, expired, or deleted by another process | Use `UNLINK` return count as the actual deleted count |
| Using `KEYS` causes Redis latency spikes | Scans and returns a large key set in a single command | Use `SCAN` and small batches |
| `CROSSSLOT` error | Sending multiple keys from different slots in Redis Cluster | Group by slot or delete key by key via cluster client |
| Keys not found despite appearing in Redis CLI | Different Redis DB, node, namespace, or key serializer | Verify connection config and key serialization |
| Job interrupted with unknown deleted count | Operation spans multiple commands, each batch succeeds independently | Persist per-batch results, support idempotent retries |
| Memory does not drop immediately after `UNLINK` | Memory freeing happens asynchronously | Monitor background tasks and memory usage over an appropriate observation window |

## 12. Takeaways for Practice

With Spring Data Redis, the typical pattern is **clear namespace → validate pattern → cursor-based `SCAN` → batched processing/deletion → observe and rerun if needed**. Always distinguish key-name scope from hash-slot scope, scanned keys from actually deleted keys, and incremental traversal from a consistent snapshot.

The illustrative code fits cache key groups or temporary data named by convention running on standalone/Sentinel Redis. When the application uses Redis Cluster, sustains continuous write traffic, or requires high business accuracy, add coordination and handling tailored to the limitations outlined above.

### References

- [Redis — SCAN](https://redis.io/docs/latest/commands/scan/)
- [Redis — UNLINK](https://redis.io/docs/latest/commands/unlink/)
- [Spring Data Redis — RedisTemplate API](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/core/RedisTemplate.html)
- [Spring Data Redis — RedisClusterConnection API](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/connection/RedisClusterConnection.html)
