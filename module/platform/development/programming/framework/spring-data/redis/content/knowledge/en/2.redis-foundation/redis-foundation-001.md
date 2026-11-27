# Redis Key–Value Model and Data Types

Redis is a primarily in-memory data management system that organizes data as **key–value** pairs. The important point is that **a value does not have to be just a simple string**: Redis provides multiple data structures designed for different operations, such as counting page views, storing user attributes, managing queues, tag sets, leaderboards, or event logs.

In Spring Data Redis, understanding the data model properly determines how you name keys, choose between `RedisTemplate` / `StringRedisTemplate`, and use operation groups such as `opsForValue()`, `opsForHash()`, `opsForList()`, or `opsForZSet()`.

## 1. Key–Value Mindset

### 1.1. One Key Points to a Typed Value

Think of Redis as a very large lookup table:

```text
Redis keyspace
│
├── product:1001:stock  ───────> "25"                       [String]
├── user:1001           ───────> {name: "An", city: "HCM"}  [Hash]
├── queue:emails        ───────> ["mail-1", "mail-2"]       [List]
├── post:42:tags        ───────> {"java", "redis"}          [Set]
└── ranking:week        ───────> {"an": 120, "binh": 90}    [Sorted Set]
```

A data entry has two parts:

- **Key:** a unique identifier for the data item within the scope of the Redis database in use; usually represented as a business-meaningful string.
- **Value:** the data associated with the key, holding a specific Redis type such as String, Hash, List, Set, Sorted Set, or Stream.

There is no concept of tables, rows, foreign keys, or default `JOIN` operations like in a relational database. Applications typically design keys and value structures around **how the data will be accessed**.

For example, if you want to immediately fetch the stock of a product by ID, a `product:1001:stock` key holding a number is appropriate. If you want to fetch multiple attributes of the same user, a Hash `user:1001` is usually clearer than creating a separate key for each attribute.

### 1.2. Structured Key Names, Without Redis Creating Folders

A common convention is:

```text
<entity-type>:<identifier>:<purpose>

user:1001
user:1001:sessions
product:SKU-42:stock
ranking:weekly:2026-W46
```

The colon (`:`) is just a character in the key name; Redis **does not automatically create a parent–child relationship** between `user:1001` and `user:1001:sessions`. Naming conventions help developers avoid key collisions, separate data, and manage lifetimes.

Keep key names consistent and reasonably descriptive, avoid putting sensitive data into key names, and avoid huge keys containing too many elements when the application always reads the entire value.

### 1.3. Common Key-Level Operations

The commands below operate at the **key** level, regardless of whether the value is a String, Hash, or List:

```redis
EXISTS user:1001                # Does the key exist?
TYPE user:1001                  # Example result: hash
EXPIRE user:1001 3600           # Expires after 3,600 seconds
TTL user:1001                   # Remaining seconds
DEL user:1001                   # Deletes the key and its entire value
```

With `TTL`, a result of `-1` means the key exists but has no expiration; `-2` means the key does not exist. `EXPIRE` is commonly used for caches, sessions, and temporary data. In basic usage, TTL is attached to the **key holding the structure**, rather than automatically attached individually to each element of a List or Set. Some newer Redis versions add support for expiration at the Hash field level.

When you need to iterate over keys on a system serving live traffic, use `SCAN` in batches instead of `KEYS pattern`, because `KEYS` can block the server when the keyspace is large:

```redis
SCAN 0 MATCH user:* COUNT 100
```

`SCAN` returns the next cursor and a batch of keys; you must continue iterating until the cursor returns to `0`. `COUNT` is only a hint for the number of elements per iteration and does not guarantee a fixed page size.

## 2. Map of Redis Data Types

| Type / Structure | Represented Value | Key Characteristics | Suitable Use Cases |
|---|---|---|---|
| **String** | Byte sequence, can represent numbers | Read/write whole value, increment/decrement numbers | Value caching, tokens, counters |
| **Hash** | Collection of `field → value` pairs | Access individual attributes | Profiles, configuration, object metadata |
| **List** | Ordered sequence of elements | Push/pop at both ends; duplicates allowed | Simple queues, recent item lists |
| **Set** | Collection of unique elements, no guaranteed order | Membership checks, intersection/union/difference | Tags, participant sets, set relationships |
| **Sorted Set (ZSet)** | Unique elements paired with a score | Ordered by score, rank queries | Leaderboards, prioritized data |
| **Stream** | Sequence of ID-tagged entries with multiple fields | Read by ID, consumer groups, acknowledgment | Event logs, persisted event processing |
| **Bitmap / Bitfield** | Bits or groups of bits inside a String | Compact representation of flags/counters | Attendance, status flags, packed counters |
| **HyperLogLog** | Distinct-element estimation structure | Memory-efficient, approximate result | Estimating unique visitors |
| **Geospatial** | Coordinates and location identifiers | Search by distance/radius | Stores, drivers, delivery points |

**Distinguishing logical types from storage types:** Bitmap, Bitfield, and HyperLogLog are implemented on top of String values; Geospatial data is built on top of Sorted Set. Therefore, `TYPE` does not necessarily return the functional category name in the table above. Some Redis versions or distributions also provide extended types/features, such as JSON documents or vector search; check what is supported on the server you are using.

## 3. String: Single Values and Counters

String is the most basic type. Whether storing text, serialized JSON, binary data, or numbers, Redis treats a String value as a sequence of bytes. For arithmetic operations, the content must represent a valid integer/number as required by the command.

```redis
SET product:1001:name "Mechanical Keyboard"
GET product:1001:name

SET product:1001:stock 25
INCR product:1001:stock
INCRBY product:1001:stock 4
DECR product:1001:stock
GET product:1001:stock
```

After incrementing by 1, adding 4, and decrementing by 1, `product:1001:stock` has the value `29`. Commands like `INCR` and `INCRBY` are atomic at the single-command level, which is very convenient for counters under concurrent requests.

String also supports setting a time-to-live at write time:

```redis
SET session:token:abc "user:1001" EX 1800
GET session:token:abc
TTL session:token:abc
```

Here `EX 1800` sets a 30-minute expiration. A normal `SET` replaces the current value and removes the key's existing TTL unless a supported TTL-preserving option is used; keep this in mind when refreshing caches or sessions.

**When to choose String:** the application usually reads/writes the entire value, needs a counter, or wants to store serialized data. If you frequently update individual fields of an object, consider Hash.

## 4. Hash: Grouping Attributes of an Object

A Hash stores multiple `field → value` pairs under a single Redis key. This is a natural choice when modeling a small object whose attributes can be read and modified independently.

```redis
HSET user:1001 name "An" city "Ho Chi Minh" loginCount 0
HGET user:1001 name
HMGET user:1001 name city
HINCRBY user:1001 loginCount 1
HGETALL user:1001
HDEL user:1001 city
```

`HGET` fetches only one field; `HGETALL` fetches all field–value pairs. A non-existent field returns an empty/null value depending on the client interface. All fields belong to the same key `user:1001`, so a TTL set on that key affects the entire Hash.

Points to note:

- A Hash is a single Redis value; `name` and `city` are **fields**, not independent keys in the keyspace.
- Redis does not automatically know that `loginCount` is a Java `int` property: a counter can use `HINCRBY` when its value represents a valid integer.
- Avoid running `HGETALL` frequently on a Hash with a very large number of fields; fetch only the needed fields or iterate in batches with `HSCAN`.
- Hash does not have relationships, multi-object filtering queries, or automatic secondary indexes like an SQL table.

**Design example:** `user:1001` is a Hash holding the profile; `user:1001:roles` can be a separate Set if the application needs to check roles and perform set operations.

## 5. List: Ordered Sequences and Simple Queues

A List stores elements in sequence order. Elements can be duplicated; pushing or popping at either end fits queue/deque structures well.

```redis
RPUSH queue:emails "mail-1" "mail-2" "mail-3"
LRANGE queue:emails 0 -1
LPOP queue:emails
LRANGE queue:emails 0 -1
```

`RPUSH` appends at the tail; `LPOP` removes from the head, so the two commands create a FIFO queue: `mail-1` is consumed first. If you push and pop at the same end, the model behaves like a LIFO stack. `LRANGE key 0 -1` reads the entire list; it is only suitable when the list is sufficiently small.

Common commands:

| Command | Meaning |
|---|---|
| `LPUSH` / `RPUSH` | Insert one or more elements at the head/tail |
| `LPOP` / `RPOP` | Remove and return the head/tail element |
| `LLEN` | Get the number of elements |
| `LRANGE` | Read a slice by index range |
| `BLPOP` | Wait for an element to appear in one of the specified Lists |

List works well for simple queues, but if you need ID-tagged events, multiple consumers, processing state tracking, and replayability, Stream is usually a better fit. Because `LPOP` removes the element immediately, the application also has to design its own recovery flow if a consumer receives a job and then fails.

## 6. Set: Unique, Unordered Collections

A Set does not contain two identical elements. This type is useful when the main question is “does this element belong to the set?” or “which elements do two groups have in common?”.

```redis
SADD post:42:tags "redis" "spring" "java" "redis"
SCARD post:42:tags
SISMEMBER post:42:tags "redis"
SMEMBERS post:42:tags

SADD post:43:tags "redis" "docker"
SINTER post:42:tags post:43:tags
SUNION post:42:tags post:43:tags
SDIFF post:42:tags post:43:tags
```

`SCARD post:42:tags` returns `3`, because adding `redis` again does not create a duplicate element. `SINTER` finds the intersection, `SUNION` finds the union, and `SDIFF` returns elements present in the first set but not the subsequent ones.

**Do not rely on the display order of `SMEMBERS`:** Set does not guarantee ordering. For large sets, avoid pulling the entire set into the application if you only need to check one member; use `SISMEMBER`. You can iterate in batches using `SSCAN`.

## 7. Sorted Set (ZSet): Ranking by Score

Sorted Set combines **element uniqueness** with a numeric **score**. Redis orders elements by score; when scores are equal, the order among members is determined lexicographically by member name. It is well suited for leaderboards, priority values, and lists that require rank-based queries.

```redis
ZADD ranking:week 120 "an" 90 "binh" 110 "chi"
ZRANGE ranking:week 0 -1 WITHSCORES
ZRANGE ranking:week 0 2 REV WITHSCORES
ZINCRBY ranking:week 35 "binh"
ZREVRANK ranking:week "binh"
ZSCORE ranking:week "binh"
```

After adding 35 points, `binh` has a score of `125`, placing at the top of the leaderboard if no element has a higher score. `ZREVRANK` returns the 0-based rank, where `0` is the highest position.

Quick comparison:

- **List:** prioritizes insertion order and two-ended operations; duplicates allowed.
- **Set:** membership checks and set operations; no ranking.
- **Sorted Set:** requires ordering by score/rank; each member appears only once.

Inserting or updating an element in a Sorted Set generally takes logarithmic time in the number of elements, in exchange for efficient rank queries. When a leaderboard is very large, read by range instead of fetching the entire set.

## 8. Stream: ID-Tagged Event Sequences

A Stream holds multiple entries, each with an ID and a set of field–value pairs. Unlike a plain List, Stream is designed for cases where an application needs to consume time-ordered data, track read positions, and optionally organize **consumer groups**.

```redis
XADD orders:events * orderId "1001" state "CREATED"
XADD orders:events * orderId "1002" state "PAID"
XLEN orders:events
XRANGE orders:events - +
XREAD COUNT 10 STREAMS orders:events 0-0
```

The `*` tells Redis to generate an ID for the new event. `XREAD` with ID `0-0` reads entries whose IDs are greater than that marker. In practice, you can read from a persisted ID, perform blocking reads to wait for new events, or use a consumer group.

Typical consumer group flow:

```redis
XGROUP CREATE orders:events processors 0 MKSTREAM
XREADGROUP GROUP processors worker-1 COUNT 10 STREAMS orders:events >
# After processing succeeds, use the actual ID returned by XREADGROUP:
XACK orders:events processors <entry-id>
```

`XREADGROUP` reads new messages for a group; messages delivered but not yet acknowledged with `XACK` remain in the pending list. To handle consumer failures, the application needs a mechanism to inspect and reclaim pending messages. `XACK` **does not automatically delete entries from the Stream**; to bound storage usage, you must apply an appropriate trimming or deletion policy.

Stream solves a different problem from Pub/Sub: Pub/Sub broadcasts messages to currently connected subscribers without retaining a Stream-style backlog; Stream stores entries so they can be re-read until removed or trimmed by policy.

## 9. Specialized Structures

### 9.1. Bitmap and Bitfield

Bitmap allows accessing individual bits within a String value. Each bit can represent a binary state—for example, whether user `42` was active on a given day:

```redis
SETBIT active:2026-11-12 42 1
GETBIT active:2026-11-12 42
BITCOUNT active:2026-11-12
```

`BITCOUNT` counts the number of bits set to `1`. Bitmap saves memory when IDs are fairly contiguous and the problem is mainly true/false flags. However, setting a bit at an extremely large offset can expand the value significantly; do not use sparse, huge IDs as offsets without careful sizing.

Bitfield also operates on a String, but treats contiguous groups of bits as signed/unsigned integers:

```redis
BITFIELD counters:packed SET u8 0 7 GET u8 0
```

This example writes the value `7` into an 8-bit unsigned field at offset `0`, then reads it back. Only use it when you clearly understand the numeric bounds, bit offsets, and overflow behavior.

### 9.2. HyperLogLog

HyperLogLog is used to **estimate the number of distinct elements** with a small memory footprint, making it suitable for statistics such as daily unique visitors:

```redis
PFADD visitors:2026-11-12 "user-1" "user-2" "user-1"
PFCOUNT visitors:2026-11-12
```

`PFCOUNT` returns an **approximate** count, not a strict exact guarantee. HyperLogLog also does not provide the full list of added elements and cannot replace a Set if you need to check “is user-1 in this set?”.

### 9.3. Geospatial

Geospatial stores locations by longitude and latitude and supports finding locations within a radius:

```redis
GEOADD store:locations 106.701 10.777 "store-a"
GEOADD store:locations 106.710 10.780 "store-b"
GEOPOS store:locations "store-a"
GEOSEARCH store:locations FROMLONLAT 106.700 10.775 BYRADIUS 5 km WITHDIST
```

The coordinate order in `GEOADD` is **longitude first, latitude second**. Geospatial is built on Sorted Set, so `TYPE store:locations` returns `zset`. Distance query results are approximate geographic calculations; applications should choose appropriate units and radii.

### 9.4. Extended Types or Modules

Beyond the structures above, a Redis deployment may include capabilities for JSON documents, search, vectors/embeddings, and other specialized workloads. Command names and availability depend on the Redis version and the modules or distribution deployed. Therefore, when designing a Spring Data Redis application, distinguish **core Redis data types** from separately installed extensions.

## 10. Choosing a Data Type Based on the Required Query

Suppose you are building an e-commerce application with a shopping cart, product tags, inventory, and event history. Instead of starting with “how many tables should there be?”, ask “each time the application accesses Redis, what operation does it need?”.

| Requirement | Example Key Pattern | Reasonable Choice | Why |
|---|---|---|---|
| Read inventory count | `product:1001:stock` | String | `GET`, `INCRBY`, `DECRBY` |
| Update profile attributes | `user:1001` | Hash | `HGET`, `HSET`, `HINCRBY` per field |
| Pop next job from queue | `queue:emails` | List | `RPUSH` + `LPOP` |
| Check which tags a product has | `product:1001:tags` | Set | Deduplicated, `SISMEMBER` |
| Top users by score | `ranking:weekly` | Sorted Set | Score and rank |
| Record order events for processing | `orders:events` | Stream | IDs, progress tracking, consumer groups |
| Record daily activity status | `active:yyyy-mm-dd` | Bitmap | Bit representing status |
| Estimate unique visitors | `visitors:yyyy-mm-dd` | HyperLogLog | Approximate cardinality, memory-efficient |
| Find stores near current location | `store:locations` | Geospatial | Search by location/radius |

The same entity can appear across multiple keys to serve different access patterns. For example, `product:1001` is a Hash describing the product, while `product:1001:stock` is a String used for fast increments and decrements. This design requires clear conventions on which data is the source of truth and how to keep attributes synchronized when they appear in multiple places.

## 11. Important Rules When Working with Redis

### 11.1. Each Key Has One Type at Any Given Time

```redis
SET demo:key "hello"
HSET demo:key name "An"
```

The second command will fail with a `WRONGTYPE` error because `demo:key` is currently a String. You cannot use Hash commands to operate on a String key. Note that `SET demo:key ...` can **overwrite** the value and data type stored at that key; avoid reusing the same key name for two different purposes.

### 11.2. A Single Command Is Usually Atomic; a Sequence of Commands Is Not Guaranteed to Be

`INCR counter` is an atomic increment command. In contrast, the sequence `GET counter`, computing in Java, and then `SET counter` can suffer lost updates when multiple threads run concurrently. Business steps spanning multiple keys also do not automatically form an atomic transaction. Prefer dedicated data commands and consider transactions or scripts when consistency across multiple operations is required.

### 11.3. TTL, Memory Size, and Full-Collection Queries

- **TTL:** an expired key may disappear before the next read; the application must handle missing keys. Do not attach a TTL to data that must be retained long-term without an explicit expiration policy.
- **Memory size:** Redis typically keeps hot data in memory; a single key holding an oversized List/Hash/Set still consumes significant resources. Bound queue lengths, Stream entry counts, or history windows when the domain requires it.
- **Queries:** commands that return entire collections such as `SMEMBERS`, `HGETALL`, or `LRANGE 0 -1` can create heavy load. Use bounded ranges or batched scan commands as data grows.
- **Durability:** Redis provides persistence and replication depending on configuration, but choosing a data type does not by itself guarantee that data has been durably persisted. Apply operational policies commensurate with the criticality of the data.

## 12. Mapping to Spring Data Redis

Spring Data Redis provides operation APIs matching Redis data structures. In Spring Boot applications, `StringRedisTemplate` is convenient when keys and values/fields can be represented as strings:

```java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RedisDataExample {

    private final StringRedisTemplate redis;

    public RedisDataExample(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void writeSampleData() {
        // String: value with a 30-minute TTL.
        redis.opsForValue().set("product:1001:stock", "25", Duration.ofMinutes(30));
        redis.opsForValue().increment("product:1001:stock", 2);

        // Hash: attributes under a single key.
        redis.opsForHash().put("user:1001", "name", "An");
        redis.opsForHash().put("user:1001", "city", "Ho Chi Minh");
        redis.expire("user:1001", Duration.ofHours(1));

        // List: push onto the tail of the queue.
        redis.opsForList().rightPush("queue:emails", "mail-1");

        // Set: each tag exists only once.
        redis.opsForSet().add("product:1001:tags", "redis", "spring");

        // Sorted Set: store score for the leaderboard.
        redis.opsForZSet().add("ranking:weekly", "user:1001", 120.0);
    }
}
```

Commonly used APIs:

| Redis Type | Spring Data Redis API | Example Operations |
|---|---|---|
| String | `opsForValue()` | `get`, `set`, `increment` |
| Hash | `opsForHash()` | `put`, `get`, `entries`, `increment` |
| List | `opsForList()` | `leftPush`, `rightPush`, `leftPop`, `range` |
| Set | `opsForSet()` | `add`, `isMember`, `intersect` |
| Sorted Set | `opsForZSet()` | `add`, `incrementScore`, `reverseRange` |
| Stream | `opsForStream()` | `add`, `read`, `acknowledge` |
| Geospatial | `opsForGeo()` | `add`, `radius`, `search` (depending on API/version) |
| HyperLogLog | `opsForHyperLogLog()` | `add`, `size` |

For Java objects, `RedisTemplate<K, V>` allows customizing serializers for keys, values, hash keys, and hash values. What you observe via `redis-cli` depends on the serializer: a Java object does not automatically become a Redis Hash just because it has multiple fields. If a serializer writes the entire object under one key, the stored data may actually be a **Redis String containing an encoded payload**; to manipulate individual fields via `HGET`/`HSET`, you must actually store it using the Hash structure.

In addition, operations like `get`, `pop`, `isMember`, or reading a field may return `null` in certain cases (absent key or special execution contexts such as pipelining/transactions). Application code must account for this state rather than assuming data always exists.

## 13. Combined Example: Designing Data for a Use Case

Suppose you need to store information for a campaign consisting of: campaign attributes, participant set, individual scores, and participation events. You can choose the following separate keys:

```text
campaign:2026-fall             [Hash]       name, startDate, status
campaign:2026-fall:members     [Set]        user-1, user-2, ...
campaign:2026-fall:ranking     [Sorted Set] user-1→150, user-2→110, ...
campaign:2026-fall:events      [Stream]     participation actions, score additions, ...
```

A few corresponding operations:

```redis
HSET campaign:2026-fall name "Autumn Campaign" status "OPEN"
SADD campaign:2026-fall:members "user-1" "user-2"
SISMEMBER campaign:2026-fall:members "user-1"

ZADD campaign:2026-fall:ranking 150 "user-1" 110 "user-2"
ZRANGE campaign:2026-fall:ranking 0 9 REV WITHSCORES

XADD campaign:2026-fall:events * userId "user-1" action "JOIN"
```

This design clearly demonstrates one principle: **a key is the access address, while a data type is the set of operations optimized for the application's needs**. Choosing Hash, Set, Sorted Set, or Stream based on the desired read/write pattern makes the Redis model easy to understand and ensures Spring Data Redis code uses the right API group.
