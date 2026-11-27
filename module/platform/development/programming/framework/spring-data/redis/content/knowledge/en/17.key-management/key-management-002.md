# Synchronous Deletion with DEL and Asynchronous Reclamation with UNLINK in Spring Data Redis

When invalidating a login session, evicting stale cache entries, or cleaning up temporary data in Redis, an application needs to remove **keys**. The two directly related commands are `DEL` and `UNLINK`. Both make the key inaccessible under its old name as soon as the command completes, but they differ in **how memory holding the value is reclaimed**. This difference becomes especially important when a key stores a very large Hash, List, Set, or Sorted Set.

In Spring Data Redis, the corresponding operations are `RedisTemplate.delete(...)` and `RedisTemplate.unlink(...)`. Understanding them helps you choose a deletion approach that meets latency requirements without mistaking "asynchronous" for deleting a key at some indeterminate time.

## 1. Two Parts of Deleting a Key

A Redis key can be thought of as having two parts:

1. **Keyspace mapping:** the key name pointing to the data object.
2. **Object memory:** the structure and elements allocated to store the value.

To delete a key, Redis must remove the keyspace mapping and free the object's memory. Under normal handling, `DEL` performs both steps on the command execution thread, whereas `UNLINK` unlinks the key name first and offloads expensive memory reclamation to a background thread.

```text
Client sends DEL my:key
      |
      v
Redis removes key from keyspace
      |
      v
Redis frees memory during command execution
      |
      v
Returns result to client

Client sends UNLINK my:key
      |
      v
Redis removes key from keyspace
      |                         \
      v                          \--> Queues memory reclamation work
Returns result to client                  to background thread
                                         |
                                         v
                                  Reclaims memory later
```

**Core point:** "Asynchronous UNLINK" refers to memory reclamation, not that the key remains readable after the command returns. The key name is already removed from the keyspace during the `UNLINK` command itself. If another process writes to the same name afterward, that is new data.

## 2. Comparing DEL and UNLINK

| Aspect | `DEL` | `UNLINK` |
|---|---|---|
| Syntax | `DEL key [key ...]` | `UNLINK key [key ...]` |
| Key accessibility after command completes | Old key is gone | Old key is gone |
| Memory reclamation | Typically performed on the command execution thread | Fast key unlink; expensive reclamation is moved to a background thread |
| Cost for String keys | Typically O(1) | O(1) when unlinking a single key |
| Cost for large Hash/List/Set/Sorted Set | Can grow with element count and block command processing | O(1) per key on the execution path; freeing happens later |
| Deleting multiple keys | O(number of keys) plus value-freeing cost | O(number of keys) on the execution path plus background freeing work |
| Return value | Number of keys actually deleted | Number of keys actually unlinked from keyspace |
| Suitable use cases | Small keys, few keys, simple operations | Large keys, bulk data cleanup, latency-sensitive workloads |

Redis processes key deletion sequentially and preserves the atomicity of the keyspace change. Background memory freeing running later does not make the old key reappear.

**Configuration exception:** Redis has a `lazyfree-lazy-user-del` option that allows user-invoked `DEL` to also use lazy free. Therefore, saying "`DEL` always frees synchronously" is too absolute: that is the normal behavior when this option is disabled. `UNLINK` explicitly expresses the intent to offload reclamation work to the background at the command level.

## 3. Hands-On with Redis CLI

### 3.1. Deleting a Small Key with DEL

```redis
SET session:42 "active"
EXISTS session:42
# (integer) 1

DEL session:42
# (integer) 1

EXISTS session:42
# (integer) 0

DEL session:42
# (integer) 0
```

`DEL` returns `1` when the key existed and was deleted. The second call returns `0` because the key no longer exists. The result is **the number of keys deleted**, not the number of elements inside the value. With multiple keys:

```redis
SET session:43 "active"
SET session:44 "expired"
DEL session:43 session:44 session:missing
# (integer) 2
```

### 3.2. Deleting a Data Structure with UNLINK

```redis
HSET report:2026:11 author "team-a" state "ready" rows "100000"
EXISTS report:2026:11
# (integer) 1

UNLINK report:2026:11
# (integer) 1

EXISTS report:2026:11
# (integer) 0
HGETALL report:2026:11
# (empty array)
```

The example uses a small Hash for easy testing. The latency benefit of `UNLINK` becomes much clearer when the value is very large and freeing it is costly. The key does not need to wait for the background thread to finish freeing memory before disappearing from the keyspace.

```redis
SET cache:a "A"
SET cache:b "B"
UNLINK cache:a cache:b cache:unknown
# (integer) 2
```

Non-existent keys are ignored by both commands. Calling delete again is safe if the goal is simply to ensure the key no longer exists.

### 3.3. Observing Memory After Deletion

```redis
INFO memory
INFO stats
SLOWLOG GET 10
```

Depending on the Redis version, `INFO` exposes metrics such as `used_memory` and `lazyfree_pending_objects`. With `UNLINK`, memory may be freed **after** the command returns, so you cannot assume `used_memory` drops immediately. Process RSS also depends on the allocator and operating system; sometimes objects are already freed while RSS has not yet decreased. `SLOWLOG` helps detect slow commands, though it does not measure the full duration of `UNLINK` background work.

## 4. Using DEL and UNLINK Through Spring Data Redis

Spring Boot applications typically use the starter:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

For string key names, `StringRedisTemplate` is convenient because its key serializer uses strings. Key methods:

| Spring Data Redis API | Redis Command | Typical Result |
|---|---|---|
| `redisTemplate.delete(key)` | `DEL key` | `Boolean`: whether the key was deleted |
| `redisTemplate.delete(keys)` | `DEL key1 key2 ...` | `Long`: number of keys deleted |
| `redisTemplate.unlink(key)` | `UNLINK key` | `Boolean`: whether the key was unlinked |
| `redisTemplate.unlink(keys)` | `UNLINK key1 key2 ...` | `Long`: number of keys unlinked |

These APIs belong to `RedisOperations`, which `RedisTemplate` implements. Inside a pipeline or transaction, Spring Data Redis may return `null` when the command is queued; the actual result must be retrieved after execution. **Do not interpret `null` as a failed deletion.**

### 4.1. Purpose-Built Key Removal Service

```java
import java.util.Collection;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RedisKeyRemovalService {

    private final StringRedisTemplate redisTemplate;

    public RedisKeyRemovalService(StringRedisTemplate redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    // Small String key, such as session state.
    public boolean deleteSession(String sessionId) {
        String key = "session:" + sessionId;
        return Boolean.TRUE.equals(redisTemplate.delete(key));
    }

    // Key that may hold a large Hash, Set, or List.
    public boolean unlinkReport(String reportId) {
        String key = "report:cache:" + reportId;
        return Boolean.TRUE.equals(redisTemplate.unlink(key));
    }

    // Direct count retrieval is only for outside pipelines/transactions.
    public long unlinkKeys(Collection<String> keys) {
        if (keys.isEmpty()) {
            return 0L;
        }

        Long removed = redisTemplate.unlink(keys);
        if (removed == null) {
            throw new IllegalStateException(
                    "UNLINK result not available yet: check pipeline/transaction");
        }
        return removed;
    }
}
```

`unlinkReport(...)` still waits to send the command to Redis and receive the server response: it does **not** automatically turn the Java call into a reactive or fire-and-forget call. Asynchrony here lies in Redis's memory reclamation mechanism. If you need non-blocking client threads, that is a separate decision about reactive/asynchronous APIs.

A value of `true` means the key name was removed, **not** confirmation that memory has been returned to the operating system. Returning `false` when a key does not exist is normal for an idempotent delete operation.

### 4.2. Serializers and Namespaces Must Match

Redis stores key names as bytes. A key created by `StringRedisTemplate` or `redis-cli` may not match a key encoded by another serializer on `RedisTemplate<Object, Object>`. If `delete("session:42")` returns `false` even though the CLI shows a similar name, check:

- Whether the key serializer at **write** time and **delete** time are identical.
- Whether the application connects to the same Redis instance, logical database, or cluster.
- Whether namespace prefixes and key naming conventions are consistent.

Do not change the serializer of keys already active in production without a compatibility or data migration plan.

## 5. Cleaning Up Many Keys: SCAN Combined with Batched UNLINK

Suppose you need to clean up old cache entries with the prefix `report:archive:`. There are two sources of slowdown:

1. **Finding keys:** `KEYS report:archive:*` scans the entire keyspace in a single command, which can block Redis when data is large.
2. **Deleting values:** `DEL` on large objects can spend time freeing memory on the command execution thread.

A common approach is incremental scanning with `SCAN` followed by `UNLINK` in moderate batches. `SCAN` returns a cursor, **not** a consistent snapshot of the keyspace; it can return duplicate keys and has limited guarantees when data changes mid-scan. For cache cleanup, deleting the same key repeatedly is normally safe.

```java
import java.util.ArrayList;
import java.util.List;
import org.springframework.data.redis.core.Cursor;
import org.springframework.data.redis.core.ScanOptions;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ArchivedReportCleanup {

    private static final int BATCH_SIZE = 200;
    private final StringRedisTemplate redisTemplate;

    public ArchivedReportCleanup(StringRedisTemplate redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    public long unlinkArchivedReports() {
        ScanOptions options = ScanOptions.scanOptions()
                .match("report:archive:*")
                .count(500)
                .build();

        List<String> batch = new ArrayList<>(BATCH_SIZE);
        long removedCount = 0;

        // Always close the cursor after use.
        try (Cursor<String> cursor = redisTemplate.scan(options)) {
            while (cursor.hasNext()) {
                batch.add(cursor.next());
                if (batch.size() == BATCH_SIZE) {
                    removedCount += unlinkBatch(batch);
                    batch.clear();
                }
            }
        }

        if (!batch.isEmpty()) {
            removedCount += unlinkBatch(batch);
        }
        return removedCount;
    }

    private long unlinkBatch(List<String> keys) {
        Long removed = redisTemplate.unlink(keys);
        if (removed == null) {
            throw new IllegalStateException("Missing UNLINK result for batch");
        }
        return removed;
    }
}
```

`COUNT 500` is a **hint** for the number of keys per scan step, not a guarantee of returning exactly 500 keys. `BATCH_SIZE = 200` is only an illustrative number; choose based on key count, latency, and actual load. If cleaning up millions of keys, rate-limit, schedule the work, and monitor resources because `UNLINK` still consumes CPU to free data on the background thread.

In Redis Cluster, multi-key operations can be subject to **hash slot** constraints. Do not assume an arbitrary list of keys can be passed to a single `DEL`/`UNLINK` command across every cluster deployment. You can group keys in the same slot using pre-designed hash tags, or process per key/slot appropriately for your driver; `SCAN` on a cluster also needs to cover the relevant nodes. Verify the routing capabilities of your configuration before running large cleanups.

## 6. Choosing Commands by Scenario

| Scenario | Starting Choice | Explanation |
|---|---|---|
| Deleting a small String login-session key | `DEL` or `UNLINK` | Freeing cost is usually low; `DEL` is simple |
| Deleting a key holding hundreds of thousands of elements | `UNLINK` | Avoids blocking Redis due to freeing a large structure |
| Deleting many cache keys after source data changes | Batched `UNLINK` | Offloads expensive reclamation to the background |
| Cleaning cache by prefix in production | `SCAN` + batched `UNLINK` | Avoids scanning the entire keyspace with `KEYS` |
| Data only needs time-based expiration | Set TTL via `EXPIRE` or at write time | Redis manages expiration automatically, reducing manual deletion needs |
| Deleting only one field of a Hash | `HDEL` | `DEL` and `UNLINK` delete **the entire key**, not a single field |

Both commands share the same business goal of removing key names. The main difference is command execution duration and how memory-freeing work is scheduled.

## 7. Misconceptions to Avoid

**"UNLINK returns before the key disappears."** False. Redis removes the key from the keyspace while processing `UNLINK`. What is deferred is memory reclamation. Once the command succeeds, subsequent reads no longer see the old value under that key name.

**"UNLINK reduces OS memory immediately."** There is no such guarantee. Objects may still be waiting for lazy free; even after freeing, the allocator may retain memory pages for reuse.

**"UNLINK creates no load."** False. Redis still looks up and unlinks keys; the background thread still needs CPU to free objects. A massive deletion wave can build a background work queue and resource pressure. You must tune batch sizes and avoid designing big keys in the first place.

**"Once deleted, the key cannot reappear."** False if another process keeps writing to the same key name. This is a contention issue between business operations; if control is needed, use data versioning, conditional writes, or appropriate synchronization. Switching from `DEL` to `UNLINK` does not solve race conditions.

**"A `null` result from RedisTemplate means deletion failed."** False inside pipelines/transactions. You must retrieve and interpret results at the corresponding execution point.

**"DEL/UNLINK can replace HDEL/SREM."** Both commands delete **the entire key**. To remove a single Hash field use `HDEL`, to remove a Set member use `SREM`; other data types have their own element-level modification commands.

## 8. Operational Principles

Before cleaning a high-traffic Redis instance, know **value sizes**, **number of keys to delete**, and **acceptable latency thresholds**. A big key is usually a sign to revisit the data model rather than merely changing the deletion command.

For short-lived data, set a clear TTL and namespace upon creation. For prefix-based cleanup, use `SCAN` and delete in a controlled manner. Monitor latency, `SLOWLOG`, memory, and pending lazy-free tasks. Measure on representative data before deciding on a production batch size.

**Takeaway:** `DEL` normally both unlinks the key and frees the value during command execution (unless lazy-free configuration changes behavior); `UNLINK` prioritizes fast key unlinking and moves expensive reclamation work to the background. In both cases, once the command completes, the key name no longer maps to the old data.

## References

- [Redis — DEL](https://redis.io/docs/latest/commands/del/): syntax, complexity, return value.
- [Redis — UNLINK](https://redis.io/docs/latest/commands/unlink/): unlinking keys and background memory reclamation.
- [Redis — SCAN](https://redis.io/docs/latest/commands/scan/): cursor-based scanning and its guarantees/limitations.
- [Spring Data Redis — RedisOperations API](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/core/RedisOperations.html): `delete`, `unlink`, and `scan` methods.
