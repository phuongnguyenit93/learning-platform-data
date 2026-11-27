# Choosing the Right Data Structure Before Applying a Pattern

In **Spring Data Redis**, the same problem can be implemented using several different Redis structures. A product can be cached as a JSON `String` or a `Hash`; a task list can use a `List` or a `Stream`; a leaderboard should use a `Sorted Set` instead of pulling a list into Java to sort manually.

Choosing the wrong structure can force the application to scan entire datasets, introduce race conditions, trigger `CROSSSLOT` errors in Redis Cluster, prevent setting the required TTL, or force you to rebuild capabilities Redis already supports with atomic commands.

**Starting principle:** do not start with “should I use a String or a Hash?”, start with **the business operations that must be performed**, the consistency guarantees required, and how the data will grow. Only then choose a Redis structure and map it to the appropriate Spring Data Redis API.

This lesson outlines a selection workflow, compares data structure types, provides Java examples, and illustrates when to evolve a design as initial requirements change.

## 1. Model Data Access Patterns Before Picking a Redis Type

Before writing `RedisTemplate.opsForValue()` or `opsForHash()`, describe the read/write paths of the feature.

For example, an e-commerce system has these needs:

| Need | Questions to Answer | Structural Impact |
|---|---|---|
| Cache product details | Read the whole object or only a few fields? | JSON `String` or `Hash` |
| Count views | Need atomic increments across concurrent requests? | `String` with `INCR` |
| Wishlist of product IDs | Need fast membership checks without duplicates? | `Set` |
| Top best-selling products | Need top N by score, ranking, and score updates? | `Sorted Set` |
| Task queue | Need ACK/retry after a worker crashes? | `Stream` usually fits better than a plain `List` |
| Rate limiting | Fixed-window counting or sliding window? | `String`/`Sorted Set` with atomic commands or Lua |
| Count unique users | Are estimates acceptable? | `HyperLogLog` if error margin is acceptable |
| Store locations | Query by coordinates/radius? | Redis GEO commands |
| Boolean flags across millions of slots | Are positional indexes explicit and fairly dense? | Bitmap/bit operations on String |

Constraints to write down before designing:

1. **Primary access operations:** fetch entire object, fetch single field, check membership, fetch top N, enqueue/consume messages, or search by distance.
2. **Cardinality:** roughly how many keys, how many elements per key, and the byte size of one element.
3. **Churn rate:** writes per second and whether multiple clients mutate the same key.
4. **TTL:** does the entire group expire together, or does each element need an independent TTL?
5. **Ordering:** need FIFO, score ordering, or is order irrelevant?
6. **Duplicates:** may the same element be inserted multiple times?
7. **Durability and recovery:** can lost data be regenerated; are ACK/replay required?
8. **Redis topology:** standalone, primary/replica, or Cluster; are multi-key operations needed?
9. **Source of truth:** is Redis a database cache, temporary metrics, or the primary owner of business data?
10. **Testing and operations:** how to observe size, TTL, errors, lag, and data cleanup policies.

An application pattern may be sound under one set of constraints yet break immediately once requirements like “replay on worker crash” or “independent per-item expiration” are added.

## 2. Quick Map of Redis Data Structures

| Structure / Command | Data Shape | Strengths | Usually Unsuitable When |
|---|---|---|---|
| **String** | Byte strings, string integers, serialized JSON | `GET`/`SET`, counters, per-key TTL, whole-object caching | Frequently updating independent fields without reading/writing the full payload |
| **Hash** | One key containing multiple field -> value pairs | Read/write individual fields, `HINCRBY`, objects grouped under one key | Each field needs an independent lifecycle/TTL on unsupported versions/configs |
| **List** | Ordered sequence of elements | Push/pop at both ends, simple queues, short lists | Requiring ACK/replay, multiple independent consumer groups, membership/rank queries |
| **Set** | Unordered collection of unique elements | Membership checks, add/remove items, intersections/unions | Needing rank/position or preserving duplicates |
| **Sorted Set (ZSet)** | Unique members + numeric scores | Rankings, top N, score-range queries, time-ordered schedules | Needing a queue with ACKs/Pending Entries List |
| **Stream** | Append-only sequence of entries with monotonic IDs | Event logs, consumer groups, pending/ACK, replay within retention | Only needing a single counter or flag |
| **Pub/Sub** | Real-time notification channels, not persistent key/value state | Broadcasting messages to currently connected subscribers | Needing replay/ACK when subscribers are offline |
| **Bitmap / bit operations** | Bits backed by a String | Indexed boolean flags, bit counting | Very large sparse IDs causing wasteful bit allocation |
| **HyperLogLog** | Probabilistic cardinality estimator | Estimating unique count in tiny memory | Needing exact counts or enumerating members |
| **GEO** | Coordinate index built on Sorted Sets | Finding members near coordinates and within radius | Needing complex GIS geometry beyond Redis capabilities |
| **Optional modules** | RedisJSON, RedisBloom, Search... | Rich JSON queries, approximate membership, full-text search | Server lacks the module or the app only relies on core Redis |

Redis Strings, Hashes, Lists, Sets, Sorted Sets, and Streams are the core data structures. Bitmaps, HyperLogLog, and GEO expose **specialized command families** and internal representations; do not treat them all like interchangeable Java collections.

**No single data type is best for every pattern.** Read/write cost, memory overhead, concurrency behavior, and TTL requirements typically drive the choice.

## 3. Initial Structure Selection Decision Tree

```text
What needs to be stored?
   |
   +--> Single value / counter / cached payload
   |       |
   |       +--> GET/SET/counter ---------------------> String
   |       |
   |       +--> Mutate single fields of an object ---> Hash
   |
   +--> Multiple members in a group
   |       |
   |       +--> Only check group membership? --------> Set
   |       |
   |       +--> Need ordering by score/time? --------> Sorted Set
   |       |
   |       +--> Need ordered push/pop? --------------> List
   |
   +--> Event or task streams
   |       |
   |       +--> Need ACK/retry/replay/groups? -------> Stream
   |       |
   |       +--> Only broadcast to online listeners? -> Pub/Sub
   |
   +--> Analytics / spatial
           |
           +--> Approximate unique counts -----------> HyperLogLog
           |
           +--> Indexed boolean flags ---------------> Bitmap
           |
           +--> Coordinate/distance lookups ---------> GEO
```

This decision tree is only a **starting point**. For instance, a rate limiter might use a String counter for fixed windows, a Sorted Set for sliding windows, or another algorithm in Lua. All three are “rate limiting,” yet differing business requirements lead to different designs.

## 4. String: Single Values, Counters, and Whole-Object Caching

### 4.1. When to Use String?

String fits when each key holds **one value**:

```text
app:feature:checkout       -> ENABLED
product:42:price           -> 950000
rate:login:{user-42}:60s   -> 17
cache:product:v1:42        -> ProductSnapshot JSON
```

Spring Data Redis example:

```java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;

public class StringExamples {
    private final StringRedisTemplate redis;

    public StringExamples(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void saveFlag(String name, String value) {
        redis.opsForValue().set(
                "feature:" + name,
                value,
                Duration.ofMinutes(10));
    }

    public String getFlag(String name) {
        return redis.opsForValue().get("feature:" + name);
    }

    public Long incrementViewCount(long productId) {
        return redis.opsForValue().increment(
                "product:" + productId + ":views");
    }
}
```

`INCR`/`DECR` are atomic Redis commands at the single-key level. When merely incrementing a counter, never do `GET` followed by `SET value + 1` in Java, as two concurrent requests reading the same stale value will overwrite each other.

### 4.2. Caching JSON in a String

A product can be stored as a JSON payload:

```text
key: cache:product:v2:42

value:
{
  "id": 42,
  "name": "Study Desk",
  "price": 950000,
  "sourceVersion": 12
}
```

Pros: a single `GET` fetches the entire DTO, per-entity TTL is straightforward, schema versioning is clean, and it pairs naturally with cache-aside.

Trade-off: modifying a single field typically means deserializing the entire value, updating the object, and rewriting the full payload. With concurrent writers, `GET -> mutate Java object -> SET` risks **lost updates** unless guarded by optimistic versioning or atomic compare-and-set.

### 4.3. TTL and SET

`SET key value EX seconds` creates or updates a value with TTL in one command. In Spring:

```java
redis.opsForValue().set(
        "cache:product:v2:42",
        jsonPayload,
        Duration.ofMinutes(5));
```

Keep in mind: a plain `SET` overwriting a value **drops the old TTL** unless a new TTL or a TTL-preserving option is specified. If an entry must always expire, never accidentally call `set(key, value)` without expiration afterward.

### 4.4. Using Strings for Temporary Locks and Conditional Writes

Some cases require creating a key only if absent:

```java
Boolean acquired = redis.opsForValue()
        .setIfAbsent(
                "locks:job:{42}",
                "request-unique-token",
                Duration.ofSeconds(30));
```

This corresponds to `SET key value NX EX ...`: a conditional write with TTL in a single command, closing the race window of separate `SETNX` followed by `EXPIRE`.

Still, **a key created with NX + TTL is not a complete distributed lock**. Releasing must verify the owner token (for example, via Lua); lease expiration, renewal, fencing tokens, and overdue operations must all be designed explicitly.

## 5. Hash: Objects Updated Field by Field

Suppose an application manages session state whose attributes change at different frequencies:

```text
key: session:{abc123} (Hash)

fields:
  userId      -> 42
  lastPage    -> /catalog
  requestCount-> 19
  status      -> ACTIVE
```

With a Redis Hash, you can read or update individual fields instead of rewriting the whole JSON blob.

Spring Data Redis:

```java
import java.time.Duration;
import java.util.Map;
import org.springframework.data.redis.core.StringRedisTemplate;

public class SessionHashService {

    private final StringRedisTemplate redis;

    public SessionHashService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void saveSession(String sessionId, String userId) {
        String key = "session:{" + sessionId + "}";

        redis.opsForHash().putAll(key, Map.of(
                "userId", userId,
                "status", "ACTIVE",
                "requestCount", "0"));

        redis.expire(key, Duration.ofMinutes(30));
    }

    public Long addRequest(String sessionId) {
        return redis.opsForHash()
                .increment(
                        "session:{" + sessionId + "}",
                        "requestCount",
                        1);
    }

    public Object getStatus(String sessionId) {
        return redis.opsForHash()
                .get("session:{" + sessionId + "}", "status");
    }
}
```

`HINCRBY` atomically increments an integer field. However, `putAll` followed by `expire` in the snippet are **two separate Redis operations**. If the process crashes after writing the Hash and before setting the TTL, a non-expiring key can be left behind. When TTL is a strict invariant, bundle the steps with Lua/transactions as appropriate or use an alternative atomic write-with-TTL design.

### 5.1. Hash Does Not Automatically Use Less Memory Than String

Redis can use compact encodings for small Hashes, yet actual memory overhead depends on field count, value sizes, encoding thresholds, and Redis allocator behavior. There is no absolute rule that “Hash is always better than a JSON String.”

If an object is almost always read and written as a whole, a JSON String may be simpler and more efficient. If hot single-field updates or `HINCRBY` are needed, a Hash has clear advantages.

### 5.2. Hash TTL

In the classic model, `EXPIRE key` applies TTL to the **entire Hash**, not automatically per field. Newer Redis releases may offer **Hash field expiration commands** depending on server version and client/API support; never assume every Spring Data Redis deployment supports them identically.

If each field needs an independent TTL and field-level expiration is unconfirmed, you may need separate keys per item or a Sorted Set keyed by expiration timestamps. Picking a Hash just because an object has fields creates operational headaches if those fields must expire independently.

## 6. Choosing JSON String vs. Hash for an Entity

| Question | JSON String | Redis Hash |
|---|---|---|
| Usually read the whole object? | Natural, single `GET` | `HGETALL` or multiple `HMGET` |
| Frequently update one small field? | Must rewrite payload or use extra JSON tools | `HSET`, `HINCRBY` |
| Each entity needs one TTL? | `SET` with TTL is convenient | `EXPIRE` on the Hash key |
| Complex/nested JSON schema? | Easy to preserve DTO schema | Must flatten or serialize nested fields |
| Need atomic field increment? | Needs separate counter key; cannot `INCR` inside JSON | `HINCRBY` |
| Using Spring Redis Repository? | Needs custom mapping if stored as String | Repositories typically map aggregates to Hashes + auxiliary keys |
| Memory cost? | Depends on payload and serializer | Depends on field count and Redis encoding; must measure |
| Query by arbitrary attribute? | No automatic indexing on Strings | Hashes have no built-in secondary indexes either |

**Do not mistake a Redis Hash for a SQL table queryable by any column.** To find every session with `status=ACTIVE`, storing `status` inside a Hash does not automatically create an index for that query.

With **Spring Data Redis Repositories**, the framework maps entities to Hashes and manages metadata/index keys per annotations and configuration. Writing directly via `RedisTemplate` outside the Repository can leave Repository-managed secondary indexes out of sync.

## 7. Set: Unique Members and Membership Checks

A wishlist can be represented as:

```text
key: wishlist:{user-42} (Set)
members:
  product-100
  product-205
  product-901
```

Required operations are “add product,” “remove product,” and “is this product in the wishlist?”. A Redis Set fits better than a List because duplicate members are never stored in the same Set.

Example:

```java
import java.util.Set;
import org.springframework.data.redis.core.StringRedisTemplate;

public class WishlistService {

    private final StringRedisTemplate redis;

    public WishlistService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Long add(String userId, String productId) {
        return redis.opsForSet().add(
                "wishlist:{" + userId + "}",
                productId);
    }

    public Boolean contains(String userId, String productId) {
        return redis.opsForSet().isMember(
                "wishlist:{" + userId + "}",
                productId);
    }

    public Long remove(String userId, String productId) {
        return redis.opsForSet().remove(
                "wishlist:{" + userId + "}",
                productId);
    }

    public Set<String> members(String userId) {
        return redis.opsForSet().members(
                "wishlist:{" + userId + "}");
    }
}
```

`SADD` and `SISMEMBER` fit when order does not matter. `SADD` returns the count of newly added members, which can detect whether a member already existed at the Set level.

### 7.1. Using Sets for Deduplication

Example tracking processed event IDs:

```text
processed-events:{consumer-A} (Set)
  event-101
  event-102
  event-103
```

Calling `SADD` a second time with the same event ID will not duplicate it in the Set. Still, “`SADD` succeeds, then run business logic” **does not guarantee exactly-once execution** if the app crashes between marking the Set and committing to the database.

When deduplication state must stay consistent with another database's side effects, rely on transactions, unique constraints/idempotency, or an outbox at the authoritative store. A Redis Set only provides atomic membership within Redis.

### 7.2. Set Limitations

- No defined business ordering; never rely on `SMEMBERS` order.
- If you need top N by score, use a Sorted Set.
- If members need individual TTLs, `EXPIRE` on the Set key cannot expire members independently.
- `SMEMBERS` returns the entire set, which gets heavy at high cardinality; consider `SSCAN` and pagination.
- At large scale, monitor `SCARD`, memory, and expiration/cleanup policies.

## 8. Sorted Set: Scores, Rankings, and Time-Based Scheduling

A Redis Sorted Set (ZSet) pairs each unique member with a numeric **score**. Redis maintains score order, supporting top-N queries, score ranges, and rank lookups.

Leaderboard example:

```text
leaderboard:weekly:{game-1} (ZSet)

alice -> score 1250
bob   -> score 990
cara  -> score 1800
```

The application updates scores and fetches the top entries:

```java
import java.util.Set;
import org.springframework.data.redis.core.StringRedisTemplate;

public class LeaderboardService {

    private final StringRedisTemplate redis;

    public LeaderboardService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Double addScore(String gameId, String playerId, double delta) {
        return redis.opsForZSet().incrementScore(
                "leaderboard:weekly:{" + gameId + "}",
                playerId,
                delta);
    }

    public Set<String> topPlayers(String gameId, long count) {
        if (count <= 0) {
            return Set.of();
        }

        return redis.opsForZSet().reverseRange(
                "leaderboard:weekly:{" + gameId + "}",
                0,
                count - 1);
    }

    public Long rankFromTop(String gameId, String playerId) {
        return redis.opsForZSet().reverseRank(
                "leaderboard:weekly:{" + gameId + "}",
                playerId);
    }
}
```

`ZINCRBY` increments a score atomically on a single ZSet key/member. `reverseRank` returns a **0-based** position, not a 1-based user-facing rank. If `reverseRank` returns `null`, the member is not in the ZSet.

### 8.1. Handling Tied Scores

When multiple members share the same score, Redis breaks ties lexicographically by member. Never assume tie ordering automatically reflects play time or registration order. If strict tie-breaking is required, design composite scores or auxiliary data carefully without losing floating-point precision.

### 8.2. Sorted Sets for Delayed Jobs

You can store “eligible run time” as the score:

```text
delayed-jobs (ZSet)

job-A -> 1760000100000
job-B -> 1760000200000
job-C -> 1760000300000
```

Workers query jobs whose score is less than or equal to the current time. However, splitting “read due jobs” and “remove from ZSet” into two commands can let multiple workers claim the same job.

When **atomic claiming** is required, use Lua or an appropriate Redis command to pop/remove safely. After claiming, you still need a retry policy if a worker dies mid-execution. If the core requirement is **message delivery with ACKs**, consider Redis Streams instead of rebuilding an entire PEL and recovery protocol around a ZSet.

### 8.3. Limitations Worth Remembering

- Scores use floating-point numbers; be careful with oversized timestamps or exact-equality expectations.
- TTL normally applies to the entire ZSet key; individual members do not auto-expire by score.
- ZSets carry ordering/indexing overhead; avoid them when only membership is needed.
- Score/rank range queries outperform fetching everything into Java to sort.
- A single key with millions of members can turn into a **hot key** or cause heavy load on broad range scans.

## 9. List: Ordered Push/Pop, Not an ACK-Capable Queue

A Redis List preserves element order and supports pushes/pops from both ends. Simple queue example:

```text
jobs:thumbnail (List)

producer: LPUSH job-id
consumer: RPOP job-id
```

Spring:

```java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;

public class SimpleJobQueue {

    private final StringRedisTemplate redis;

    public SimpleJobQueue(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Long submit(String jobId) {
        return redis.opsForList()
                .leftPush("jobs:thumbnail", jobId);
    }

    public String take() {
        return redis.opsForList()
                .rightPop("jobs:thumbnail", Duration.ofSeconds(2));
    }
}
```

`LPUSH` + `RPOP` yields FIFO order when strictly pushing to one end and popping from the opposite end. Blocking pop waits up to a timeout instead of tight polling.

**Message loss problem:** once a consumer runs `RPOP`, the item is removed from the List. If the consumer crashes immediately afterward, the job is gone from the queue and Redis maintains no Pending Entries List.

### 9.1. Reliable Queues with Lists Are Possible, Yet Labor-Intensive

A classic pattern uses “ready” and “processing” lists:

```text
ready-list
    |
    | atomically move
    v
processing-list
    |
    +--> worker succeeds -> remove from processing
    |
    +--> worker crashes  -> watchdog detects and moves back to ready
```

Redis offers commands like `LMOVE`/`BLMOVE` to move elements between Lists atomically. Even so, you still must build ownership tracking, timeouts, retries, idempotency, and recovery logic. When consumer groups, replay, and pending recovery are needed, **Streams** usually cut down custom protocol boilerplate.

Lists remain reasonable for short stacks/queues, best-effort jobs, or when durability already lives elsewhere in the application.

## 10. Stream: ID-Ordered Events, Consumer Groups, and Pending Recovery

A Redis Stream stores ordered entries with sequential IDs:

```text
stream: orders:events

1730000000000-0 -> {type: OrderCreated, orderId: 42}
1730000000100-0 -> {type: OrderPaid, orderId: 42}
1730000000200-0 -> {type: OrderShipped, orderId: 42}
```

Capabilities that make Streams fitting:

- Producers append events with `XADD`.
- Consumers read with `XREAD` or `XREADGROUP`.
- Multiple consumers inside a group divide up new entries.
- Redis maintains a Pending Entries List (PEL) for delivered but not yet `XACK`ed messages.
- Recovery can leverage `XPENDING`, `XCLAIM`, or `XAUTOCLAIM`.
- Independent groups can read the same stream at separate offsets.
- Entries can be retained for replay within a configured retention window.

### 10.1. Writing to a Stream with Spring Data Redis

Example producer appending a `MapRecord`:

```java
import java.util.Map;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.RecordId;
import org.springframework.data.redis.core.StringRedisTemplate;

public class OrderEventPublisher {

    private final StringRedisTemplate redis;

    public OrderEventPublisher(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public RecordId publish(String orderId, String eventType) {
        MapRecord<String, String, String> record =
                MapRecord.create(
                        "orders:events",
                        Map.of(
                                "orderId", orderId,
                                "eventType", eventType));

        return redis.opsForStream().add(record);
    }
}
```

`RecordId` is the entry's position ID inside the stream, distinct from the `orderId` inside the payload.

Reading in Spring Data Redis can use `StreamOperations` or `StreamMessageListenerContainer` for background workers. Consumer groups must be initialized at the proper offset alongside explicit ACK/recovery policies.

### 10.2. Streams Do Not Guarantee Exactly-Once Business Execution

A consumer might update the database and crash **before sending `XACK`**. The message stays pending, and another worker reclaims and reprocesses it. Therefore, enforce idempotency keyed by event ID or business operation ID.

`XACK` clears the group's pending status; **it does not physically delete the entry from the stream**. Enforce retention/trimming aligned with capacity and group replay requirements.

### 10.3. List vs. Stream

| Need | List | Stream |
|---|---|---|
| Simple push/pop | Great | Possible, though heavier |
| Single FIFO queue | Good if honoring opposite ends | Read in stream ID order |
| Post-processing ACK | Must build manually | Supported via consumer groups/PEL |
| Retry after consumer crash | Must manage manually | Supports reclaiming pending entries |
| Multiple independent groups reading every event | Not built-in | Yes |
| Historical replay | Custom retention required | Supported within trim retention |
| Capacity and trimming | Manage list length | Manage stream retention |
| Exactly-once business semantics | No | No; requires idempotency |

If tasks merely need “hand off to a live worker, acceptable to lose on crash,” a plain List can suffice. If losing jobs is unacceptable and retries plus backlog visibility are required, evaluate Streams right from the structure-selection stage.

## 11. Pub/Sub: Ephemeral Broadcast vs. Stream

Redis Pub/Sub is not a key retaining message history. Producers `PUBLISH` to a channel, and subscribers currently connected and subscribed at that moment receive the notification.

```text
PUBLISH channel "inventory-updated"

        |
        +--> online subscriber A
        +--> online subscriber B
        +--> online subscriber C

Offline subscribers have no personal queue for replay.
```

Pub/Sub fits ephemeral hints—for instance, “you may want to refresh UI state”—where the system can fall back to querying the source of truth if a message is missed.

Never rely on Pub/Sub alone when requirements demand:

- processing messages even if subscribers are temporarily offline;
- ACKs, consumer groups, or retries;
- event replay to rebuild state;
- guaranteeing zero missed critical business commands.

In Spring Data Redis, `RedisMessageListenerContainer` serves imperative Pub/Sub, whereas `StreamMessageListenerContainer` is a separate component for Streams. The names look similar, yet their **delivery semantics differ completely**.

## 12. Bitmap: Offset-Based Boolean Flags and Size Limits

Bitmaps in Redis rely on String bit operations. Suppose user IDs are known contiguous integers from 0 up to a bounded limit and you want to record “checked in today”:

```text
attendance:2026-11-13 (bitmap)

offset 42 -> 1
offset 43 -> 0
offset 44 -> 1
```

Spring Data Redis:

```java
import org.springframework.data.redis.core.StringRedisTemplate;

public class AttendanceBitmap {

    private final StringRedisTemplate redis;

    public AttendanceBitmap(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Boolean markPresent(long userIndex) {
        return redis.opsForValue().setBit(
                "attendance:today",
                userIndex,
                true);
    }

    public Boolean isPresent(long userIndex) {
        return redis.opsForValue().getBit(
                "attendance:today",
                userIndex);
    }
}
```

`SETBIT`/`GETBIT` by offset represent flags compactly bit by bit. However, if IDs are extremely sparse—such as a user ID in the billions—writing to a huge offset forces Redis to allocate a String spanning all intervening zero bits, wasting massive amounts of memory.

Bitmaps do not provide per-bit TTLs; TTL applies to the whole daily/group key. Standardize the ID -> offset mapping and partition keys cleanly by window.

## 13. HyperLogLog: Approximate Distinct Counting

A site wants to estimate daily unique visitors without necessarily tracking every individual user ID.

Redis HyperLogLog supports:

```text
PFADD daily:unique:2026-11-13 user-42 user-43 ...
PFCOUNT daily:unique:2026-11-13
```

Spring Data Redis:

```java
import org.springframework.data.redis.core.StringRedisTemplate;

public class UniqueVisitorEstimator {

    private final StringRedisTemplate redis;

    public UniqueVisitorEstimator(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Long addVisitor(String day, String userId) {
        return redis.opsForHyperLogLog()
                .add("visitors:unique:" + day, userId);
    }

    public Long estimate(String day) {
        return redis.opsForHyperLogLog()
                .size("visitors:unique:" + day);
    }
}
```

HyperLogLog saves memory for cardinality estimation with statistical error; it **cannot list the underlying users** and is inappropriate if exact counts are mandatory.

If you need to ask “did user-42 visit?”, a `Set` fits better because it stores membership. If you only need approximate unique-visitor charts, HyperLogLog often beats maintaining huge Sets.

In product analytics, label numbers clearly as **estimates** rather than presenting them as exact billing or entitlement counts.

## 14. GEO: Storing Locations and Querying by Distance

Redis provides Geo commands to store members with longitude/latitude coordinates under a key and query members near a point.

Example:

```text
geo:stores

store-42 -> (longitude, latitude)
store-77 -> (longitude, latitude)
```

Spring Data Redis exposes `GeoOperations`:

```java
import org.springframework.data.geo.Point;
import org.springframework.data.redis.core.StringRedisTemplate;

public class StoreLocationService {

    private final StringRedisTemplate redis;

    public StoreLocationService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Long addStore(String storeId, double lon, double lat) {
        return redis.opsForGeo()
                .add("geo:stores", new Point(lon, lat), storeId);
    }
}
```

Remember that `Point` here takes **longitude first, latitude second**. Swapping coordinates places stores in the wrong part of the globe or produces errors.

Redis GEO builds on Sorted Sets internally and covers common spatial proximity lookups; it is not a general GIS engine supporting arbitrary polygons, road-network routing distances, or geocoding. When routing paths and driving times are needed, integrate a dedicated routing engine.

A Geo key holding many members also does not expire individual stores automatically; manage member lifetimes and coordinate refreshes explicitly.

## 15. Specialized Redis Modules Are Not Available Everywhere

Sometimes requirements go beyond core Redis:

- **RedisJSON:** manipulating JSON structures via commands/paths when the server runs the corresponding module;
- **RedisBloom:** probabilistic membership structures when false positives are acceptable;
- **RediSearch/Search:** indexing and querying aligned with module schemas.

Never write code assuming every Redis OSS or managed Redis instance includes these commands. Verify module availability, server edition/version, and matching client operations. `RedisTemplate` does not turn a JSON String into a queryable RedisJSON document automatically.

**Selection rule:** depend on a module only when query requirements genuinely demand it and operations can support it; for simple whole-object caching, JSON Strings usually suffice.

## 16. Mapping Common Application Patterns to Structures

| Application Pattern | Starting Structure | Why | When to Revisit Design |
|---|---|---|---|
| Object caching | JSON String | Single `GET`/`SET`, per-entity TTL | Frequent single-field writes -> consider Hash |
| Session attributes | Hash | Per-field `HGET`/`HSET`/`HINCRBY` | Independent field TTLs -> consider separate keys |
| View counter | String counter | Atomic `INCR` | Time-series breakdown -> partition counters |
| Follow/watch list | Set | Deduplicated, fast membership | Need ordering -> use ZSet |
| Leaderboard | ZSet | Scores, ranks, top N | Multi-table historical snapshots -> add persistent storage |
| Simple job queue | List | Dual-end push/pop | Need ACK/replay -> consider Stream |
| Event pipeline | Stream | IDs, groups, ACK, PEL | Ephemeral broadcast only -> consider Pub/Sub |
| Membership dedup | Set | `SADD`/`SISMEMBER` | Massive scale tolerating false positives -> evaluate module |
| Timestamp schedule | ZSet | Query/claim by score | Need delivery ACK/recovery -> pair with Stream |
| Indexed boolean flags | Bitmap | Bit-level memory when offsets are dense | Sparse IDs -> Set may be better |
| Approximate unique count | HyperLogLog | Tiny fixed memory | Need exact counts -> Set or another analytics store |
| Nearest stores | GEO | Coordinate proximity search | Need road routing -> integrate GIS/routing service |
| Cache invalidation broadcast | Pub/Sub | Fan-out to online listeners | Cannot miss messages -> switch to Stream/durable broker |

This table does not replace profiling real workloads. One feature often needs **more than one structure**: for example, a ranking system using a ZSet for top N alongside Hashes/Strings for player profiles.

## 17. Key Naming Aligned with Semantics and Lifecycle

Key naming is part of structural design, not merely cosmetics.

Examples:

```text
cache:product:v2:42
counter:product:42:views
wishlist:{user-42}
leaderboard:weekly:{game-1}
orders:events
rate:login:{user-42}:20261113T0300
attendance:2026-11-13
visitors:unique:2026-11-13
```

A useful naming convention usually includes:

1. **Namespace:** `cache`, `counter`, `wishlist`, `jobs`, etc.
2. **Domain/entity:** `product`, `user`, `game`, etc.
3. **Schema/version** whenever payload formats evolve.
4. **ID/time bucket** to isolate TTLs and queries.
5. **Hash tag** when multi-key commands need the same slot in Redis Cluster.

Never embed secret tokens, passwords, or sensitive PII directly in key names: keys show up in logs, metrics, command traces, and Redis inspections.

### Too Long vs. Too Short Keys?

Overly long keys repeated across millions of entries add noticeable memory overhead; overly cryptic short keys hinder maintenance and invite collisions. Pick a convention clear enough for diagnostics yet compact at high cardinality.

### Never Mix Redis Data Types on the Same Key

If key `user:42` holds a Hash, you cannot arbitrarily call `GET user:42` as a String—Redis returns a `WRONGTYPE` error. Namespaces should reflect purpose and data type clearly; never let two services write different schemas to the same key.

## 18. TTL: Design Around the Unit of Expiration

Lifetime boundaries heavily influence **choosing keys vs. members/fields**.

| Unit That Expires | Clear Model | Caveat |
|---|---|---|
| One cached object | One String key per entity | `SET` with TTL |
| Multi-field session expiring together | One Hash key | `EXPIRE` on the key |
| Individual membership expiring independently | Separate keys or deadline model | Set members lack classic per-member TTL |
| Weekly leaderboard | Weekly ZSet | TTL per week/partition |
| Jobs due at different timestamps | ZSet with deadline scores | Score does not auto-delete due members |
| Retained event log | Stream with trimming policy | Key TTL differs from entry-level retention trimming |
| Daily visitor count | Daily HyperLogLog key | TTL per daily partition |

**A timestamp score is not a TTL.** Running `ZADD jobs:delayed 1760000100000 job-A` does not cause Redis to auto-delete or execute `job-A` at that timestamp. Workers must actively poll and process it.

Likewise, calling `XACK` on a Stream entry does not delete it from the stream, and Redis key expiration does not guarantee actions run at the exact moment of expiry.

### Avoid Unintended Immortal Keys

Example pipeline:

```java
redis.opsForHash().putAll(key, fields);
redis.expire(key, Duration.ofMinutes(30));
```

A failure window sits between these two commands. If the process stops before `EXPIRE`, the key can live without a TTL. For strict TTL invariants, group commands atomically as appropriate or choose a single-command key-creation pattern.

## 19. Atomicity: Pick Structures That Avoid Race Conditions

Single Redis commands execute atomically on their target, whereas a sequence of commands issued from Java **is not automatically atomic**.

Broken rate-limiting check example:

```java
String oldValue = redis.opsForValue().get(key);
long next = Long.parseLong(oldValue) + 1;

if (next <= limit) {
    redis.opsForValue().set(key, Long.toString(next));
}
```

Two requests can read the same `oldValue` and overwrite each other or both pass the check. Picking a String counter is only step one: use an atomic command or Lua for **check + increment**.

### Lua Example: Fixed-Window Counter

```lua
-- KEYS[1] = counter key already scoped to the time bucket
-- ARGV[1] = TTL in milliseconds
-- ARGV[2] = window limit

local ttl = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])

if not ttl or ttl <= 0 or not limit or limit <= 0 then
    return -1
end

local current = tonumber(redis.call('GET', KEYS[1]) or '0')

if current >= limit then
    return 0
end

local next = redis.call('INCR', KEYS[1])

if next == 1 then
    redis.call('PEXPIRE', KEYS[1], ttl)
end

return 1
```

This script performs **check and increment** in one Redis execution, preventing races among concurrent callers on the same key. Spring Data Redis applications can declare Lua via `DefaultRedisScript<Long>` and run `RedisTemplate.execute(script, keys, args...)`.

Known limitations:

- This is a **fixed-window limiter**, not sliding-window or token-bucket.
- The key name must include the proper **time bucket**, not one eternal key.
- A stray pre-existing counter missing a TTL won't be repaired by the script when `next != 1`.
- An atomic Redis script does not form an atomic transaction with an external database.
- Timeouts after the script already ran mean retries could increment the counter twice; design retry contracts carefully.
- Lua does not automatically roll back earlier commands if a runtime error occurs later in the script.

### When to Use MULTI/EXEC, Lua, or a Single Command?

| Need | Approach |
|---|---|
| Increment one counter | Single `INCR`/`HINCRBY` |
| Create lock if absent with TTL | `SET NX EX` or matching API |
| Conditional check + update | Lua when keys fall within valid slot scope |
| Group Redis commands into a Redis transaction | `MULTI`/`EXEC` with full awareness of error/result semantics |
| Atomic SQL + Redis commit | Cannot be guaranteed solely by Redis transactions/Lua |
| Reprocess messages after failures | Stream + ACK + idempotency/outbox per source of truth |

Picking the right data structure is essential, and pairing it with the right **unit of atomicity** completes the design.

## 20. Redis Cluster: Lay Out Keys to Avoid CROSSSLOT

In Redis Cluster, keys hash across **16,384 hash slots**. Multi-key commands and Lua scripts generally require involved keys to reside in the same slot.

Example:

```text
cart:{user-42}:items
cart:{user-42}:total
```

Both keys share hash tag `{user-42}`, mapping to the same slot and supporting valid multi-key operations.

By contrast:

```text
cart:user-42:items
cart:user-43:items
```

have no guarantee of sharing a slot. A command operating atomically across both can fail with `CROSSSLOT`.

Keep in mind:

- Hash tags are a **routing rule**, not a business index.
- A multi-key Lua script does not distribute atomicity across multiple primaries.
- Redis Cluster has no single-primary cluster-wide `SCAN`.
- Funneling too many hot keys into one hash tag creates a **hot slot**.
- Structure choice affects distribution too: one giant system-wide ZSet is always **one Redis key** in one slot; its members never spread across primaries automatically.

If a global leaderboard ZSet becomes too hot, you may need seasonal/grouped sharding or a top-N aggregation layer—understanding that splitting keys complicates computing exact global ranks. Never split keys blindly and assume per-shard top N slices merge cleanly for every ranking rule.

## 21. Spring Cache Patterns Differ from Redis Repository Data

Spring Data Redis spans several API layers:

| API Layer | Typical Data | Key Consideration |
|---|---|---|
| `StringRedisTemplate` | String, Hash, Set, List, ZSet, Stream via string serializers | Developer explicitly designs keys and types |
| `RedisTemplate<K,V>` | Data shaped by configured serializers | Key/value byte formats dictate interoperability |
| `ReactiveRedisTemplate<K,V>` | Reactive Redis ops returning `Mono`/`Flux` | Does not alter underlying Redis structures |
| Spring Cache + `RedisCacheManager` | Entries keyed by cache name and key serializer | Typically caches payload as one value with entry TTL |
| Redis Repository | Aggregates mapped to Hashes plus metadata/index keys | Never bypass metadata/index updates when writing outside Repository |
| `StreamMessageListenerContainer` | Redis Stream entries and consumer groups | Receiving records does not automatically solve ACK/replay/idempotency |

Never assume “a Repository entity is just an object” so manually running `SET key JSON` is equivalent. Redis Repositories manage keyspaces, TTLs, secondary indexes, and mappings internally; mixing direct template writes with Repositories without updating metadata/indexes causes inconsistencies.

Likewise, configuring `RedisCacheManager` does not automatically convert cached entries into Hashes or Sorted Sets merely because a Java DTO has fields.

## 22. Serializers, Schemas, and Data Lifecycle

Redis stores raw bytes; Spring Data Redis maps between Java objects and Redis commands. A good structure choice still fails if serializers disagree.

Example:

```text
SET product:42:name Desk
```

created via Redis CLI has a plain string key. If a `RedisTemplate<Object,Object>` uses JDK serialization for keys, `get("product:42:name")` from Java sends different bytes and misses the expected entry.

Guidelines:

1. For string keys/fields/values, `StringRedisTemplate` keeps the wire format transparent.
2. When storing JSON DTOs, set an explicit serializer and schema version.
3. Changing serializers does not auto-migrate existing keys; plan migrations, short TTLs, or new namespaces.
4. Never write a Hash with string fields and read it back via a template using an incompatible field serializer.
5. Before changing a key's Redis type, verify what contracts other clients expect.
6. Commands like `TYPE`, `TTL`, `MEMORY USAGE`, and `SCAN` in appropriate environments inspect live shapes without guessing Java types.

Never dump sensitive raw payloads into logs when debugging serializers. Inspect metadata, key types, and obfuscated IDs instead.

## 23. Memory Cost and Operational Complexity

Never decide solely on “is String faster than Hash?”. Estimate:

- Number of Redis keys created.
- Members/fields per key.
- Byte sizes of keys, fields, values, and metadata.
- Write rate, read rate, and peak concurrency.
- Whether commands fetch all members at once.
- Redis eviction policy and memory limits.
- Which subsets need TTL or retention policies.
- Whether a huge key creates CPU/latency spikes when scanned or updated.
- Under Redis Cluster, whether keys balance evenly across slots or create hotspots.

Decision example:

```text
10 million products
  - Each product cached as a JSON String with 5-minute TTL:
      easy whole-object reads and per-entity expiration;
      many keys, JSON repeats field names across payloads.

  - One giant Hash mapping every product ID -> JSON:
      fewer top-level keys, yet pins load to one slot,
      harder per-product TTLs, doesn't scale across Cluster.

  - One Hash per product:
      clean field updates and per-entity TTLs,
      still lots of top-level keys plus field overhead to measure.
```

No verdict is final before benchmarking realistic workloads and payloads. Redis switches internal encodings based on structure size, affecting memory and latency. Choose based on **access patterns + operability**, not toy sample sizes.

### Avoid Full-Collection Commands on Large Sets

| Avoid Overusing | Why | Better Alternative |
|---|---|---|
| `KEYS *` in production | Blocking keyspace scan impacts latency | Bounded `SCAN` per node |
| `SMEMBERS` on huge Sets | Pulls every member into JVM memory | `SSCAN` or paginated design |
| `HGETALL` on huge Hashes | Pulls all fields and values | `HSCAN` or targeted `HMGET` |
| `LRANGE 0 -1` on huge Lists | Loads entire list | Bounded ranges and queue sizing |
| `ZRANGE 0 -1` on huge ZSets | Pulls whole leaderboard | Top N or bounded ranges |
| Unbounded `XRANGE - +` | Pulls whole stream history | Bounded `COUNT` and retention trimming |

Cursor-based scans (`SCAN`/`SSCAN`/`HSCAN`/`ZSCAN`) do not yield atomic snapshots while data mutates; results can duplicate items or miss concurrent edits. Design termination criteria and deduplication accordingly.

## 24. Three Examples of Evolving Designs as Requirements Change

### Example A — Shopping Cart: From Set to Hash

Initial requirement: “Just know which products a user picked.”

```text
cart:{user-42}:products (Set)
  product-100
  product-200
```

A Set handles unique membership cleanly. Then a new requirement arrives: “Each product has quantity 1, 2, 3... and quantities must update atomically.”

Switch to a Hash:

```text
cart:{user-42}:items (Hash)
  product-100 -> 2
  product-200 -> 5
```

`HINCRBY` increments/decrements each field's quantity. Still, if negative quantities or exceeding inventory must be blocked, add atomic validation (Lua or authoritative source checks) rather than calling `HINCRBY` and hoping counts stay valid.

If most-recently-added ordering is also needed, a Hash alone won't maintain it; you might add a Sorted Set tracking timestamps, which reintroduces cross-key atomicity and same-hash-slot concerns if updated together.

### Example B — Email Queue: From List to Stream

Initial requirement: “Each worker pops one email task.”

```text
email:ready (List)
LPUSH -> RPOP
```

Lists work fast. Then new requirements arrive:

- tasks must be retried if a worker crashes;
- visibility into how long pending tasks have waited;
- multiple workers coordinated in a group;
- replaying events by ID.

Here, a Stream fits much better:

```text
email:tasks (Stream)
  XADD
  XREADGROUP
  XACK
  XPENDING / XAUTOCLAIM
```

You still need idempotency, retry policies, and a DLQ. Switching structures alone does not stop duplicate emails after a worker crash.

### Example C — Leaderboard: From List to Sorted Set

Requirement: “Show the top 10 highest-scoring players.”

With a List, the application must fetch everything and sort in Java; as scores update frequently, maintenance becomes messy.

Use a ZSet:

```text
leaderboard:weekly:{game-1} (ZSet)

player-1 -> 120
player-2 -> 180
player-3 -> 95
```

`ZINCRBY`, `ZREVRANGE`, and `ZREVRANK` handle this natively. When requirements expand to keeping full seasonal history and deep analytics, keep the authoritative ledger in a database or analytics warehouse while using Redis ZSet as a fast projection for top-N queries.

## 25. Step-by-Step Pattern Application Workflow

A checklist to avoid picking structures out of habit:

1. **Write out the top three queries/commands** of the feature in business terms.
2. **Identify the source of truth:** is Redis authoritative or a rebuildable cache?
3. **Define the data unit:** one object, one member, one event, or a daily/per-user bucket.
4. **Match the structure to the primary access pattern**, not merely Java input shapes.
5. **Analyze race conditions:** which operations span multiple commands? Do atomic commands, Lua, or transactions cover them?
6. **Design TTL/retention:** key-level or member-level expiration; how is stale data pruned?
7. **Check Cluster layout:** do multi-key operations share slots; are there hot keys?
8. **Pick serializers and schema versions** so writers and readers agree on wire bytes.
9. **Define retry/idempotency rules** for client timeouts and redelivered worker messages.
10. **Benchmark realistic workloads** and adapt the structure as access patterns shift.

A pattern valid under “small data, single worker, no replay” often breaks when scaling to millions of members or concurrent multi-app writers.

## 26. Lab Exercises: Comparing Structures on Test Redis

Use a **dedicated lab Redis instance/Cluster**, never production data.

### Exercise 1 — String Counters and TTL

```bash
redis-cli SET views:product:42 0 EX 60
redis-cli INCR views:product:42
redis-cli INCR views:product:42
redis-cli GET views:product:42
redis-cli TTL views:product:42
redis-cli TYPE views:product:42
```

Next run `SET views:product:42 10` without a TTL and inspect `TTL` again. Note the takeaway regarding overwriting Strings and expiration.

### Exercise 2 — Hash vs. JSON String

```bash
redis-cli HSET session:lab userId 42 status ACTIVE requestCount 0
redis-cli HINCRBY session:lab requestCount 1
redis-cli HGET session:lab requestCount
redis-cli HGETALL session:lab
redis-cli EXPIRE session:lab 60
redis-cli TTL session:lab
```

Create an equivalent JSON String under a separate key and compare command steps when updating only `requestCount`. If checking `MEMORY USAGE`, remember measurements depend on Redis encodings and sample size—one small test doesn't prove one format always wins.

### Exercise 3 — Set Membership and ZSet Ranking

```bash
redis-cli SADD wishlist:lab p1 p2 p2
redis-cli SCARD wishlist:lab
redis-cli SISMEMBER wishlist:lab p2

redis-cli ZADD leaderboard:lab 10 alice 20 bob 15 cara
redis-cli ZREVRANGE leaderboard:lab 0 2 WITHSCORES
redis-cli ZREVRANK leaderboard:lab bob
redis-cli ZINCRBY leaderboard:lab 5 alice
```

Observe how the Set deduplicates members while the ZSet stores each member with a score and rank.

### Exercise 4 — List Queues and Lost Tasks on Worker Crash

```bash
redis-cli LPUSH jobs:lab job-1 job-2
redis-cli RPOP jobs:lab
redis-cli LRANGE jobs:lab 0 -1
```

After `RPOP`, the task is gone from the List. Simulate a “worker crash” by leaving the popped task unprocessed; note why there is no PEL and why reliable queues require extra mechanisms.

### Exercise 5 — Stream Consumer Groups and ACK

```bash
redis-cli XGROUP CREATE jobs:stream:lab workers 0-0 MKSTREAM
redis-cli XADD jobs:stream:lab '*' type SendEmail id 100
redis-cli XREADGROUP GROUP workers c1 COUNT 1 STREAMS jobs:stream:lab '>'
redis-cli XPENDING jobs:stream:lab workers
```

Note the Redis Stream ID returned by `XADD` or `XREADGROUP` and substitute it into:

```bash
redis-cli XACK jobs:stream:lab workers <record-id>
redis-cli XPENDING jobs:stream:lab workers
redis-cli XLEN jobs:stream:lab
```

`<record-id>` is a placeholder for the actual ID. Notice how ACK clears pending state while `XLEN` still retains the entry.

### Exercise 6 — Cluster Slots and Hash Tags

If running a lab cluster:

```bash
redis-cli -c -p 7000 CLUSTER KEYSLOT 'cart:{user-42}:items'
redis-cli -c -p 7000 CLUSTER KEYSLOT 'cart:{user-42}:total'
```

Both slots must match. Try keys without shared tags and note why multi-key commands can raise `CROSSSLOT`.

## 27. Self-Assessment Questions

**1. An object is usually read in full with rare single-field edits—should you start with String or Hash?**  
Usually start with a JSON String for simple read/write/TTL semantics, then measure workloads. If individual fields change often, Hash may fit better.

**2. Does a Redis Hash auto-create an index to query all objects with `status=ACTIVE`?**  
No. A Hash merely groups field/value pairs under one key. Secondary indexes require explicit mechanisms or properly managed Repositories/indexes.

**3. Why does a wishlist fit Set better than List?**  
Wishlists need duplicate-free membership checks, whereas Lists allow duplicates and aren't optimized for membership lookups.

**4. Why does a leaderboard fit ZSet?**  
Because it requires scores, top N, and rankings—all directly supported by ZSet operations.

**5. If workers must ACK and retry after crashes, is List or Stream usually more convenient?**  
Stream, thanks to consumer groups, the PEL, and claim/ACK commands—though business idempotency is still required.

**6. Does Pub/Sub buffer messages for offline subscribers?**  
No. It delivers only to currently connected subscribers and provides no replay/ACK like Streams.

**7. Can HyperLogLog tell you which specific user visited?**  
No. It estimates cardinality and does not store individual members for listing or exact membership checks.

**8. When a ZSet score is a timestamp, do jobs execute automatically when due?**  
No. Workers must fetch and process due members; scores are neither TTLs nor built-in schedulers.

**9. Why might one global ZSet fail to scale evenly across Redis Cluster?**  
Because the entire ZSet is a single Redis key pinned to one hash slot/primary; its members do not shard across nodes automatically.

**10. Does `@Transactional` wrapping a Redis command guarantee atomic commit with SQL?**  
No. Database transactions and Redis operations span separate resources and require independent consistency/recovery designs.

**11. Is calling `SMEMBERS` on a Set with millions of members advisable?**  
Generally no when processing subsets; prefer `SSCAN` or a different query design.

**12. Why shouldn't total memory alone determine data structure choice?**  
Because access patterns, TTL behavior, concurrency, cluster slots, error handling, and operational overhead often outweigh modest memory savings.

## 28. Summary of Selection Principles

- **String:** single values, counters, JSON caching with per-key TTL.
- **Hash:** entity fields under one key, individual field updates or integer increments.
- **List:** dual-end push/pop for simple queues/stacks without built-in ACKs.
- **Set:** deduplicated collections and fast membership checks, unordered.
- **Sorted Set:** scores, rankings, top N, and time-ordered schedules without built-in ACKs.
- **Stream:** ID-ordered event logs, groups, pending tracking, and ACK/replay within retention; requires idempotency.
- **Pub/Sub:** instant broadcasts to online subscribers with no durable retention.
- **Bitmap:** offset-indexed boolean flags when IDs are dense and bounded.
- **HyperLogLog:** approximate distinct counts without member enumeration.
- **GEO:** coordinate and radius lookups, not a full GIS replacement.

**Choose your Redis data structure according to business operations and invariants before applying an architectural pattern.** Once the type is chosen, still pin down TTLs, serialization, atomicity, Cluster constraints, retries, and recovery. A pattern only truly fits when Redis commands directly serve the application's actual queries—with well-understood costs and boundaries.

## References

- [Redis — Data Types](https://redis.io/docs/latest/develop/data-types/): Strings, Hashes, Lists, Sets, Sorted Sets, Streams, and specialized structures.
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html): Redis operations and serialization in Spring Data Redis.
- [Spring Data Redis — Object Mapping](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/mapping.html): aggregate mapping, Hashes, and implications of Redis Repositories.
- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html): Redis Streams, listeners, groups, and ACKs.
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html): cache data choices, serialization, and TTLs.
- [Redis — Strings](https://redis.io/docs/latest/develop/data-types/strings/): `GET`/`SET` and counters.
- [Redis — Hashes](https://redis.io/docs/latest/develop/data-types/hashes/): field/value pairs and Hash operations.
- [Redis — Sets](https://redis.io/docs/latest/develop/data-types/sets/): membership and sets.
- [Redis — Sorted Sets](https://redis.io/docs/latest/develop/data-types/sorted-sets/): scores, ranks, and ranges.
- [Redis — Lists](https://redis.io/docs/latest/develop/data-types/lists/): push/pop and queues.
- [Redis — Streams](https://redis.io/docs/latest/develop/data-types/streams/): event logs and consumer groups.
- [Redis — Bitmaps](https://redis.io/docs/latest/develop/data-types/bitmaps/): bit operations on Strings.
- [Redis — HyperLogLog](https://redis.io/docs/latest/develop/data-types/probabilistic/hyperloglogs/): approximate distinct counting.
- [Redis — Geospatial](https://redis.io/docs/latest/develop/data-types/geospatial/): GEO commands and locations.
- [Redis — Cluster Specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/): hash slots, hash tags, and multi-key limits.
- [Redis — SCAN](https://redis.io/docs/latest/commands/scan/): bounded keyspace iteration.
