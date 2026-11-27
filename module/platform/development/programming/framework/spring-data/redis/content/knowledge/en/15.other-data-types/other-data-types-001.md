# Bitmap: Setting Bits, Reading Bits, and Counting Enabled Bits

Redis can store **on/off** states for a large number of objects by using individual bits of a String value. This representation is commonly referred to as a **Redis Bitmap**. For example, within a single day, an application wants to know which accounts have logged in: each account is assigned a fixed bit position; upon logging in, the application sets the bit at that position to `1`. Afterward, it can check an account using `GETBIT` or count the total number of enabled positions using `BITCOUNT`.

In Spring Data Redis, these operations can be called via `StringRedisTemplate` / `ValueOperations` and, for some low-level commands, via `RedisConnection`. Bitmaps are very efficient when IDs can be mapped to **relatively dense integer positions**, but they also come with easily overlooked limitations: **a Redis Bitmap is actually a Redis String**, bytes can be allocated up to the highest bit position, there is no member ordering or per-bit TTL, and `BITCOUNT` must scan the contents rather than being a constant-time count.

This lesson progresses from how bits are stored, numbering rules, Redis CLI examples, and Spring Boot Java code, to data design choices and operational costs when serving a large number of users.

## 1. What Is a Redis Bitmap?

In terms of Redis data types, **there is no standalone `bitmap` type** like Set or Hash. A bitmap uses a **Redis String** as a byte region, with commands that operate bit by bit:

- `SETBIT key offset value`: sets the bit at position `offset` to `0` or `1`.
- `GETBIT key offset`: reads the bit value at position `offset`.
- `BITCOUNT key`: counts the total number of `1` bits across the entire byte sequence.
- Related commands such as `BITPOS`, `BITOP`, and `BITFIELD` can be useful in extended use cases.

Example bit positions of the key `active:2026-11-12`:

```text
  Offset:      0  1  2  3  4  5  6  7 | 8  9  10 11 12 13 14 15
  Bit:         0  1  0  1  0  0  1  0 | 0  0   0  0  0  0  0  0
              └──────── Byte 0 ──────┘ └──────── Byte 1 ───────┘

  Enabled members: offset 1, 3, 6
  BITCOUNT = 3
```

Each offset represents a **numeric identifier** or a boolean state defined by the application's convention. Redis does not know which account bit 3 corresponds to: Spring Boot, the database, or the ID system must ensure the mapping between **business entity ↔ offset** is always accurate.

### Why Are Bitmaps Memory-Efficient?

In a pure bit representation, up to eight binary states are packed into a single byte:

\\[
\\text{Ideal payload size (bytes)} =
\\left\\lceil \\frac{N}{8} \\right\\rceil
\\]

Where `N` is the number of **bit positions to represent**, starting from offset `0`. One million positions correspond to about `1,000,000 / 8 = 125,000` bytes (~122 KiB) of payload; ten million positions correspond to about 1.25 MB of payload. This is **not yet** the total memory Redis uses for the key, as there is also overhead from objects, the allocator, and internal structures.

This efficiency only holds when the **offset space is relatively dense**. If there is only a single user at offset `100,000,000`, Redis still has to allocate enough bytes to represent from the first position up to that offset; the payload can exceed 12.5 MB even though **only one bit** is `1`.

## 2. Understanding Bit Offsets Before Writing Code

An **offset** is a non-negative integer representing a bit position. Redis numbers from `0`. For the first byte, offset `0` is the **most significant bit (MSB)**, and offset `7` is the least significant bit; offset `8` starts the second byte.

```text
Offset:       0 1 2 3 4 5 6 7
First byte:  1 0 0 0 0 0 0 1  = 10000001 (binary)
                              = 0x81 (hex)
```

For an offset `i`:

\\[
\\text{byteIndex} = \\left\\lfloor \\frac{i}{8} \\right\\rfloor
\\]

\\[
\\text{bitPositionFromMSB} = i \\bmod 8
\\]

If you need to manipulate bytes directly, the bit position from least significant to most significant is `7 − (i mod 8)`. In a Spring Data Redis application, **you do not need to shift bits manually** when using `SETBIT`/`GETBIT`, because Redis handles bit offsets according to the server's convention.

### Example of Setting the First Bits

```redis
SETBIT demo:bitmap 0 1
# 0: previous value at bit 0 was 0

SETBIT demo:bitmap 7 1
# 0: previous value at bit 7 was 0

GETBIT demo:bitmap 0
# 1

GETBIT demo:bitmap 1
# 0

GETBIT demo:bitmap 7
# 1

BITCOUNT demo:bitmap
# 2

STRLEN demo:bitmap
# 1 (byte)

TYPE demo:bitmap
# string
```

In this example, the first byte has the binary value `10000001`. `TYPE` returns `string` because a bitmap is a **usage pattern of Redis String**, not a separate Redis data type.

### `SETBIT` Values and Return Results

```redis
SETBIT demo:flag 5 1
# 0

SETBIT demo:flag 5 1
# 1

SETBIT demo:flag 5 0
# 1

GETBIT demo:flag 5
# 0
```

`SETBIT` returns the **previous value at the bit position**, not "number of newly added bits" and not `OK`:

| Previous value | Value to write | Return result | Final value |
| --- | --- | --- | --- |
| `0` | `1` | `0` | `1` |
| `1` | `1` | `1` | `1` |
| `1` | `0` | `1` | `0` |
| `0` | `0` | `0` | `0` |

Because of this, if an application sets a bit to `1` and the command returns the old value `0`, the application knows **this is a transition from off to on** at the moment the server processed the command. However, that does **not** by itself prove the entity was recorded for the first time in all history: the key might have expired via TTL, been deleted, or had its bit reset to `0` by another job earlier.

## 3. Essential Redis Bitmap Commands

| Command | Meaning | Typical complexity | Notes |
| --- | --- | --- | --- |
| `SETBIT key offset 0/1` | Sets a bit, returns the old bit | `O(1)` for the bit operation; creating a large string for the first time can have significant allocation cost | Can create the key if it does not exist yet |
| `GETBIT key offset` | Reads a bit | `O(1)` | Positions not yet in the string are treated as `0` |
| `BITCOUNT key` | Counts all `1` bits | `O(N)` in the number of bytes scanned | Not a pre-maintained counter in Redis |
| `BITCOUNT key start end` | Counts `1` bits in a byte range | `O(N)` in the specified byte slice | Under the default syntax, `start/end` are **byte positions** |
| `BITPOS key bit` | Finds the first occurrence of bit `0` or `1` | Depends on the amount of data to scan | Pay attention to behavior on unallocated `0`-bit regions |
| `BITOP AND/OR/XOR/NOT` | Performs bitwise operations across Strings | Depends on the length of the longest string | Can create a large destination String |
| `BITFIELD` | Reads/writes/increments fixed-width bit fields | Depends on the number of operations | Different from a single boolean state per bit |

These commands operate on the bytes of a Redis String. If the key is currently a Hash, Set, or List, calling `GETBIT` or `SETBIT` will result in a data type error such as `WRONGTYPE`.

### Reading Bits Beyond the Allocated Range

```redis
GETBIT bitmap:never-created 123
# 0

BITCOUNT bitmap:never-created
# 0
```

For a nonexistent key, `GETBIT` returns `0`. This **does not distinguish between**:

- No event has ever occurred.
- The key exists, but the bit has not been enabled.
- The key expired via TTL or was deleted.
- The data was rotated/refreshed into another period.

If you need to distinguish an **"unknown"** state from **"known to be false"**, you cannot rely solely on a single bit; you need separate metadata, events, or a trusted source of truth.

### Counting by Range: `BITCOUNT` Uses Byte Offsets by Default

```redis
SETBIT demo:range 0 1
SETBIT demo:range 7 1
SETBIT demo:range 8 1

BITCOUNT demo:range
# 3

BITCOUNT demo:range 0 0
# 2: counts only the first byte, covering bit offsets 0..7

BITCOUNT demo:range 1 1
# 1: counts only the second byte, covering bit offsets 8..15
```

In Redis versions that support the `BIT` unit option, you can specify the range in **bits**, though you should not assume every Redis server/client supports that syntax. With the standard `BITCOUNT key start end`, `start` and `end` are **not two bit offsets**. Confusing the units will produce incorrect results.

`BITCOUNT` supports ranges following Redis conventions and treats the range end as **inclusive**. If you need to count a group of bits that does not align with byte boundaries, you must apply appropriate reading/masking or use the bit-unit command variant when supported by the server.

## 4. Choosing Problems Suitable for Bitmaps

Bitmaps are especially well-suited for **true/false questions over an ID domain already mapped to offsets**:

- Has user ID 137 logged in today?
- Which accounts have received a notification campaign?
- Has task internal ID 8,012 been processed in a run?
- Which test sessions have completed?
- Counting active users on a day (if each user maps uniquely to one bit).

Example of a daily login tracking model:

```text
Key: bitmap:login:2026-11-12

Offset 0  → userIndex 0 (account A)
Offset 1  → userIndex 1 (account B)
Offset 2  → userIndex 2 (account C)
...
Offset 99 → userIndex 99

User A logs in → SETBIT key 0 1
User C logs in → SETBIT key 2 1
Count logged-in users → BITCOUNT key = 2
```

Unlike a Redis Set, a bitmap **does not retain member IDs on its own**. If you need to list the users who logged in, you must know how to convert from an offset back to a user ID. If the mapping is lost or IDs are reused, bitmap data can become impossible to interpret accurately.

### When Should You Not Use a Bitmap?

| Requirement | Why a Bitmap may be unsuitable | Alternative to consider |
| --- | --- | --- |
| IDs are random UUIDs/arbitrary strings | No small, contiguous numeric offsets; ID → offset mapping must be stored separately | Redis Set storing members directly |
| A few hundred members in a huge ID space | String must span up to the highest offset, wasting memory | Redis Set; another sparse structure |
| Need to retrieve users in order of participation | Bitmaps only represent flags, not order/timestamps | Sorted Set or an indexed database |
| Need per-member data | Each bit has only two states | Hash or per-member data keys |
| Need per-member TTL | Basic Redis TTL applies to the whole key | Sorted Set with deadline as score, or key per member |
| Frequent deletion and reuse of IDs | Old bits can be misinterpreted as new entities | Non-reusable IDs or a generation/migration mechanism |
| Need to store action counts per user | A bit only indicates yes/no; it cannot represent counts | Counter, Hash, or an appropriate structure |

**A Bitmap is not a Bloom filter.** A bitmap marks exact agreed-upon positions: if the mapping has no collisions and the key is not unexpectedly modified, there are no probabilistic false positives. A Bloom filter uses multiple hash functions/positions to save memory on large datasets while accepting a probability of false positives; it is a different data structure.

## 5. Designing the ID-to-Bit-Offset Mapping

This is the most critical step before writing code. `SETBIT` requires `offset` to be a non-negative integer, whereas the business domain may use `UUID`, usernames, profile numbers, or database IDs.

### 5.1. Dense Numeric IDs

If each user already has a **contiguous positive integer ID starting from 1** and IDs are never reused, you can define:

\\[
\\text{offset} = \\text{userId} - 1
\\]

For example, `userId=1` → offset `0`, `userId=10` → offset `9`. You must validate `userId > 0` and enforce allowed bounds before sending to Redis.

If IDs start from `0`, the offset can equal the ID itself. What matters most is a **consistent contract across all producers and consumers**.

### 5.2. Sparse Numeric IDs or UUIDs

Suppose there are currently only 100,000 users, but the largest ID is `900,000,000` because the system uses snowflake-like IDs or distributed allocation. Using the ID directly as an offset can create a very large string even when only a few bits are enabled.

You can build a stable mapping:

```text
user_uuid                           → denseIndex
7b...c1                             → 0
41...5d                             → 1
e2...99                             → 2
...
```

A **dense index** requires a durable management source with no duplicates, no arbitrary reuse, and reconciliation across multiple instances. Redis bitmaps do not solve dense index allocation for you. If you have to maintain a huge mapping table just to use a bitmap, you must factor in the combined cost of both the mapping and the bitmap; sometimes a Redis Set is simpler and more economical at real-world scale.

### 5.3. Do Not Use Arbitrary Modulo Hashing to Replace Mapping

A common mistake:

```java
long offset = Math.abs(userId.hashCode()) % 1_000_000;
```

Two different users can end up with the same offset due to a **hash collision**. When user A sets the bit, querying user B may also return `1` even though B never logged in. Modulo arithmetic does not produce a unique mapping; if the application tolerates probabilistic errors, that is already a different probabilistic data structure problem, not exact bitmap membership.

In addition, `Math.abs(Integer.MIN_VALUE)` remains negative; thus, the example above carries another technical bug besides collisions. For problems requiring accuracy, use offsets with guaranteed uniqueness.

### 5.4. Controlling Large Offsets

Redis enforces limits on `GETBIT`/`SETBIT` offsets based on String size and protocol constraints. In common Redis distributions, bitmaps are bounded by the maximum String size of roughly **512 MiB**, corresponding to a maximum offset of `2^32−1` bits, though actual limits and configurations can vary by version/server. Do not use a huge value simply because the Java `long` type allows it.

Even a **valid** offset can be dangerous: setting a bit at a very high position on a new key forces Redis to allocate/zero-fill the byte region up to that offset, potentially causing stalls and a sharp memory spike. The application should enforce an offset cap based on business scale (for example, only supporting `denseIndex` within an allocated range) far below Redis's technical maximum limit.

## 6. Creating a Spring Boot Project with Spring Data Redis

In a Spring Boot application, you need the Redis starter:

**Gradle Groovy DSL**

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

**Maven**

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
</dependency>
```

When the project already uses a compatible Spring Boot parent or BOM, the starter usually does not require an explicit version. Example connection configuration for Spring Boot 3.x:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
```

Lettuce is typically the default Redis client provided by the starter. On Docker/Kubernetes, `localhost` points to the application process's own network namespace; it must be changed to the actual Redis hostname/service.

### Why Choose `StringRedisTemplate`?

`StringRedisTemplate` uses String/UTF-8 serializers for keys and values, which matches key names readable in Redis CLI. When calling `setBit`, Redis operates directly on the bytes of the Redis String stored under that key; you do not have to serialize a separate Java object into a "binary bitset".

You should dedicate a **separate key namespace** for bitmaps, such as `bitmap:login:YYYY-MM-DD`. Do not mix the same key for JSON, text, or ordinary String values: `SETBIT` modifies specific bytes within the String and can corrupt text/JSON payloads.

## 7. Spring Data Redis: Setting Bits with `ValueOperations.setBit`

Method:

```java
Boolean oldBit = stringRedisTemplate.opsForValue()
        .setBit("bitmap:login:2026-11-12", 137L, true);
```

In a standard direct call, `setBit(key, offset, true)` sends the operation corresponding to `SETBIT key offset 1`. The `Boolean` result reflects the **previous bit value**, not the count of enabled bits.

To **clear the flag** at a position:

```java
Boolean oldBit = stringRedisTemplate.opsForValue()
        .setBit("bitmap:login:2026-11-12", 137L, false);
```

The application needs to know whether this "clearing" is valid from a business standpoint. For data such as "user has logged in today", once enabled, it is typically **not cleared** when the user logs out. For current "online/offline" presence state, clearing the bit may be necessary, but disconnect events and multiple concurrent sessions must be handled.

### Service for Recording Daily Activity

The following example service uses a bounded dense index to mark an account active during the day. Here, the index value is provided by a separate ID management source in the application:

```java
import java.time.LocalDate;
import java.util.Objects;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class DailyActivityBitmapService {

    // Example threshold representing a system policy, not a Redis limit.
    private static final long MAX_DENSE_INDEX = 9_999_999L;

    private final StringRedisTemplate redis;

    public DailyActivityBitmapService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public boolean markActive(LocalDate day, long denseIndex) {
        validateIndex(denseIndex);
        String key = keyFor(day);

        Boolean wasActive = redis.opsForValue().setBit(
                key,
                denseIndex,
                true
        );

        // true: bit transitioned from 0 to 1 on this call.
        // false: bit was already enabled previously.
        if (wasActive == null) {
            throw new IllegalStateException("SETBIT returned no result");
        }
        return !wasActive;
    }

    public boolean wasActive(LocalDate day, long denseIndex) {
        validateIndex(denseIndex);
        Boolean active = redis.opsForValue().getBit(
                keyFor(day),
                denseIndex
        );

        if (active == null) {
            throw new IllegalStateException("GETBIT returned no result");
        }
        return active;
    }

    private static String keyFor(LocalDate day) {
        Objects.requireNonNull(day, "day");
        return "bitmap:login:" + day;
    }

    private static void validateIndex(long denseIndex) {
        if (denseIndex < 0 || denseIndex > MAX_DENSE_INDEX) {
            throw new IllegalArgumentException("Invalid denseIndex");
        }
    }
}
```

**Semantics of `markActive`:** returns `true` when the previous bit was `0` and the command just set it to `1`; returns `false` if it was already `1` before. In business logic for "user's first activity today", this result can be useful, but remember that data can be lost due to TTL, failover, or key reset; do not use this result as a substitute for a business record requiring strict durability.

During pipelining/transactions, some Spring Data Redis APIs can return `null` because results are collected later. This example is intentionally written for direct calls; if moved into a pipeline, responses must be handled according to the corresponding API contract.

### Why Must the Offset Be Validated?

If a consumer accepts an arbitrary `denseIndex` from a URL/request and passes it straight into `setBit`, a caller could request a huge offset, forcing Redis to allocate many bytes or return an error. Validating the offset in the service bounds size according to business scale; additionally, endpoints still need authentication/authorization so users cannot toggle bits belonging to others.

## 8. Spring Data Redis: Reading Bits with `ValueOperations.getBit`

Reading the state of a single user:

```java
Boolean active = stringRedisTemplate.opsForValue().getBit(
        "bitmap:login:2026-11-12",
        137L
);
```

`GETBIT` is a lightweight operation, suitable when you need to know whether **one** user has the flag enabled. There is no need to download the entire bitmap into Java via `GET`, nor to call `BITCOUNT` if you only want to check a single user.

### Distinguishing a `0` Bit Result from a Nonexistent Key

```redis
GETBIT bitmap:login:unknown-date 137
# 0

EXISTS bitmap:login:unknown-date
# 0
```

`GETBIT` returns 0 for a nonexistent key, yet an existing key whose bit `137` is 0 also returns 0. If an API needs to report "data for this date has not been computed yet" instead of "inactive", maintain metadata about when data collection started/ended or the completion status of the job.

Calling `EXISTS` followed by `GETBIT` as two separate commands **does not create a consistent snapshot** when the key can be deleted or expire in between. If an atomic conclusion from both conditions is required, you can use Lua/Redis Functions on a single key or design verification state outside the bitmap.

## 9. Counting Enabled Bits with `BITCOUNT`

`BITCOUNT` returns the number of bits with value `1` in a Redis String. In an activity-tracking problem, if **each user has exactly one offset and is enabled at most once per day**, the result can represent the number of unique active users on that day.

```redis
SETBIT bitmap:login:2026-11-12 1 1
SETBIT bitmap:login:2026-11-12 3 1
SETBIT bitmap:login:2026-11-12 8 1
SETBIT bitmap:login:2026-11-12 3 1

BITCOUNT bitmap:login:2026-11-12
# 3, because bit 3 is counted only once
```

Conditions to interpret this number accurately:

- Each user is mapped to a **distinct offset**.
- No other writer uses the same key for a different meaning.
- Bits are set/retained under the same business policy.
- The key represents the exact day/period being measured (consistent time zone and period cutoff).
- Offset reuse does not mix data from two accounts.

If multiple users share the same offset due to a mapping bug, `BITCOUNT` will **undercount**. If the same user is assigned multiple offsets, the system can **overcount**. Redis does not automatically detect those discrepancies.

### Is `BITCOUNT` an `O(1)` Operation?

No. Fundamentally, Redis needs to count the enabled bits across the bytes examined. The cost is typically described as **`O(N)` in the number of bytes in the string** (or the number of bytes in the specified range). When a bitmap is tens or hundreds of MB long, calling `BITCOUNT` repeatedly on hot requests can drive CPU load and impact the latency of other commands.

For example:

```text
One million allocated bits        → ~125 KB payload
Ten million allocated bits        → ~1.25 MB payload
One hundred million allocated bits → ~12.5 MB payload
```

Every full-key `BITCOUNT` performs work proportional to the number of bytes to scan, even if only 100 bits are `1`. You should observe counting frequency, String length, and Redis load before deciding to use it in a high-traffic synchronous API.

### 9.1. Calling `BITCOUNT` with `RedisCallback`

One way to read the enabled bit count in Spring Data Redis is to use the low-level connection API:

```java
import java.nio.charset.StandardCharsets;
import java.time.LocalDate;
import java.util.Objects;
import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class DailyActivityCountService {

    private final StringRedisTemplate redis;

    public DailyActivityCountService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public long countActive(LocalDate day) {
        Objects.requireNonNull(day, "day");
        String key = "bitmap:login:" + day;

        // StringRedisTemplate uses UTF-8 for key names by default.
        byte[] keyBytes = key.getBytes(StandardCharsets.UTF_8);

        Long count = redis.execute(
                (RedisCallback<Long>) connection ->
                        connection.stringCommands().bitCount(keyBytes)
        );

        return Objects.requireNonNull(count, "BITCOUNT returned no result");
    }
}
```

`RedisCallback` lets you call low-level Redis Connection commands. You must use the **exact same encoding/key serializer** that was used when writing the data; in the example, the key is UTF-8 from `StringRedisTemplate`. If the application customizes the key serializer, do not arbitrarily convert keys with a different encoding.

Spring Data Redis APIs may vary slightly across version lines; the code above illustrates using `RedisConnection.stringCommands().bitCount(byte[])` in versions that support this interface. There is no need to download all raw bytes to the JVM and count bits yourself if you only want the bit count: Redis already provides the `BITCOUNT` command.

### 9.2. When Very Frequent Counting Is Needed

Suppose a dashboard calls `BITCOUNT` hundreds of times per second on a monthly bitmap. You should consider:

1. **Caching the count** with a short TTL if the business accepts update lag.
2. **Computing periodically** via an out-of-band job outside HTTP request paths, storing results per period.
3. **Maintaining a counter alongside setting bits** if fast count reads are needed, though you must handle atomicity, failover, and rebuilding when the counter drifts.
4. **Partitioning bitmaps by time/shard** if counting operations typically only need a small slice of data.

A counter updated alongside `SETBIT` is only accurate if it increments **when the previous bit was 0**; incrementing on every write call will double-count users. If `SETBIT` and `INCR` are two independent commands, the application can crash between them. The atomic solution is Lua/Redis Functions within a Redis scope that can access both the bitmap key and counter key according to hash slot rules.

For counts used in financial reporting, billing, or metrics requiring reproducibility, define an authoritative data source and reconciliation process rather than relying solely on a Redis counter.

## 10. Using Lua to Set a Bit and Increment a Counter on `0 → 1` Transition

When both a **bitmap** and a **counter** must be updated consistently on a single Redis node, you can use a short script:

```lua
-- KEYS[1]: bitmap key
-- KEYS[2]: count key
-- ARGV[1]: bit offset

local oldBit = redis.call('SETBIT', KEYS[1], tonumber(ARGV[1]), 1)

if oldBit == 0 then
    redis.call('INCR', KEYS[2])
end

return oldBit
```

The `SETBIT` command returns the old bit. If the old bit was `0`, the script increments the counter exactly once for the transition to `1`; if it was `1`, it does not increment. Commands inside the script execute atomically with respect to other client commands on the handling node, preventing race conditions when multiple requests mark the same user concurrently.

### Notes on Redis Cluster

The script above accesses **two keys**. In Redis Cluster, keys accessed by a script must reside in the same hash slot due to multi-key scripting restrictions. For example, a key convention sharing a hash tag for a day:

```text
bitmap:login:{2026-11-12}:data
bitmap:login:{2026-11-12}:count
```

Both keys have the hash tag `{2026-11-12}`, so they map to the same slot. In return, all data for a single day is concentrated onto one slot; actual load must be evaluated. If the system already uses keys like `bitmap:login:2026-11-12` without a hash tag, you cannot arbitrarily add a count key in a different slot and expect the script to work in Cluster.

### Limitations of an Accompanying Counter

If another job deletes the bitmap, clears bits back to 0, or deletes only the counter, the two states will drift out of sync. If a day's bitmap expires while the counter remains alive, `count` no longer represents the bitmap data. You must design **matching lifecycles**, deletion policies, writer permissions, and a procedure to rebuild the count from the bitmap when needed.

Incrementing a counter in Lua does not provide stronger durability than Redis persistence/replication mechanisms. When Redis crashes or fails over, durability still depends on infrastructure configuration. Do not confuse execution atomicity with durability across failures.

## 11. TTL for Daily or Campaign Bitmaps

Because a bitmap is a Redis String, TTL applies **to the entire key**, not to individual bits. For example:

```redis
SETBIT bitmap:login:2026-11-12 137 1
EXPIRE bitmap:login:2026-11-12 604800

TTL bitmap:login:2026-11-12
# Remaining seconds, approximately up to 7 days
```

This snippet uses two commands, so it is **not atomic**. If the application stops right after `SETBIT`, the key might not have a TTL attached. Moreover, calling `EXPIRE 604800` after **every** mark extends the deadline on every write. That may violate a policy to retain data for exactly seven days from key creation or exactly seven days after the reporting date.

### 11.1. Creating a Bitmap and Setting TTL in One Script

Redis `SETBIT` does not have `EX`/`PX` options like `SET`. If you need to guarantee that **initial creation** sets a TTL, you can use Lua:

```lua
-- KEYS[1]: bitmap key
-- ARGV[1]: offset
-- ARGV[2]: TTL seconds (positive)

local absent = redis.call('EXISTS', KEYS[1]) == 0
local oldBit = redis.call('SETBIT', KEYS[1], tonumber(ARGV[1]), 1)

if absent then
    redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2]))
end

return oldBit
```

If the key does not exist yet, the script both sets the bit and sets the TTL before returning; no other client command can interleave between the two operations while the script runs. If the key already exists, it preserves the existing expiration. This represents a policy choice: "TTL starts when the bitmap is first created", rather than "TTL from last activity".

**Limitation:** if a key **already exists without a TTL** due to legacy data or another writer, the script above does not automatically fix that state. A system where every bitmap must always expire can add a check for `TTL == -1` in the script to apply an expiration, or run a job to remediate old data. Clarify the policy before adding conditions.

### 11.2. Expiring at an Absolute Deadline

For daily statistics, sometimes you want all keys for day `D` to expire at a fixed time, such as **00:00 UTC after D + 30 days**, regardless of when the first user was active. In that case, setting expiration using a Unix timestamp may fit better than `EXPIRE N` relative to write time.

If using `EXPIREAT`/`PEXPIREAT` in a script, clearly define:

- Time zone used to determine the reporting date: UTC or a business time zone.
- Whether the deadline is specified in Unix seconds or milliseconds.
- Whether keys for an already-expired day are allowed to be recreated.
- If the system spans multiple time zones, which day an event belongs to at the cutoff boundary.

Setting a bit on an expired day's key can recreate the key if the writer does not validate the allowed period. TTL only cleans up data; it does not automatically reject late events under business policy.

### 11.3. Handling Multiple Sessions

If a bitmap represents "logged in at least once today", `SETBIT ... 1` can be called multiple times for the same offset without increasing `BITCOUNT`. However, if a bitmap represents "currently online", one session logging out does not mean the user is offline while a second session remains connected. One bit per user is **not enough** to track concurrent session counts; an appropriate presence structure or mechanism is needed.

## 12. Counting Multi-Day Active Users and `BITOP`

One benefit of bitmaps sharing the same offset mapping is that days can be combined using bitwise operations:

```text
Day A:      1 0 1 0 0 1 0 0
Day B:      0 1 1 0 0 0 1 0

OR:         1 1 1 0 0 1 1 0  → active on at least one day
AND:        0 0 1 0 0 0 0 0  → active on both days
```

Redis CLI:

```redis
BITOP OR bitmap:union:temp bitmap:login:2026-11-11 bitmap:login:2026-11-12
BITCOUNT bitmap:union:temp

BITOP AND bitmap:intersection:temp bitmap:login:2026-11-11 bitmap:login:2026-11-12
BITCOUNT bitmap:intersection:temp
```

Interpretation:

- `OR` sets bit `1` if the user was active on **at least one** day.
- `AND` sets bit `1` if the user was active on **both** days.
- `XOR` sets bit `1` if bits differ between two inputs, suitable for symmetric difference problems.

`BITOP` stores the result into a **destination Redis String**. This is derived data that consumes memory; it requires a clear namespace and TTL/cleanup policy. Do not use a destination key that collides with source data unless the business logic intentionally wants to overwrite it.

### Conditions for Meaningful OR/AND Operations

The bitmaps must share the **exact same offset → user mapping**. If day A uses offset `42` for user X while day B uses offset `42` for user Y, OR/AND still produces an arithmetic result, but it is wrong with respect to users. Reusing dense indexes over time breaks cross-period comparisons.

In Redis Cluster, multi-key `BITOP` operations must follow slot rules just like other multi-key commands. Do not assume keys for different days always fall in the same hash slot; if cross-node aggregation is required, change the key/hash-tag design or aggregate via a different mechanism.

### Cost of Bitwise Set Operations

`BITOP` generally has to inspect the bytes of the input Strings, with cost proportional to data length; it is not an `O(1)` operation for a hundred-million-bit set. The result is also materialized as a new String. For dashboards querying multiple date ranges, you may need a batch job generating weekly/monthly aggregate snapshots or a dedicated analytics engine instead of running `BITOP` over all data on every HTTP request.

## 13. Memory Estimation and Impact of Sparse Offsets

A bitmap spanning up to the highest offset `M` has a payload of at least:

\\[
\\text{bytes} = \\left\\lfloor \\frac{M}{8} \\right\\rfloor + 1
\\]

when `M ≥ 0` has been allocated. This formula gives the **byte length of the Redis String** needed to hold the bit at offset `M`; in practice, Redis adds object/allocator overhead and other costs.

| Highest offset written | Minimum String bytes | Approximate size |
| --- | ---: | --- |
| 7 | 1 | 1 B |
| 999 | 125 | 125 B |
| 999,999 | 125,000 | ~122 KiB |
| 9,999,999 | 1,250,000 | ~1.19 MiB |
| 99,999,999 | 12,500,000 | ~11.92 MiB |
| 999,999,999 | 125,000,000 | ~119.21 MiB |

Suppose only 2,000 users are active, but the highest index is `999,999,999`; the bitmap can take roughly 125 MB of payload just to reach that position. A Redis Set storing those 2,000 members directly can be far more efficient, even though Set has per-member overhead.

**Selection rule:** do not evaluate a bitmap by the number of `1` bits; look at the **highest offset that can appear** and the ID density within that range.

### Big Keys and Latency

A `SETBIT` at a high offset on a nonexistent String may require allocating a large memory block and zero-initializing its bytes. Even though the bit-write complexity is described as close to `O(1)`, the **initial expansion** can still incur significant allocation/zero-fill cost and trigger a latency spike.

A `BITCOUNT` on a multi-MB String scans a large number of bytes repeatedly. If Redis serves other requests on the same instance, large bitmap operations can degrade overall latency. Validate inputs and size bounds before scaling up application replicas or dashboard counting traffic.

## 14. Monitoring Bitmaps on Redis and Spring Boot

Redis CLI commands you can use to inspect a bitmap key:

```redis
TYPE bitmap:login:2026-11-12
STRLEN bitmap:login:2026-11-12
BITCOUNT bitmap:login:2026-11-12
GETBIT bitmap:login:2026-11-12 137
TTL bitmap:login:2026-11-12
MEMORY USAGE bitmap:login:2026-11-12
```

| Command | What can be inferred |
| --- | --- |
| `TYPE` | A bitmap must appear as a Redis `string` |
| `STRLEN` | Number of bytes in the String; helps infer the allocated offset range |
| `BITCOUNT` | Number of enabled bits; requires understanding the mapping and counting cost |
| `GETBIT` | State at a known offset |
| `TTL` | Lifecycle of the entire key; `-1` means no TTL, `-2` means nonexistent |
| `MEMORY USAGE` | Memory allocated by Redis for the key; not strictly identical to `STRLEN` |

Additional observations from Redis and the application:

```redis
INFO commandstats
INFO memory
SLOWLOG GET 20
```

`SLOWLOG` focuses on command execution time inside Redis, excluding full network or client latency. On the Spring Boot side, also monitor Redis call latency, timeouts, pool wait time, serializer errors, throughput, and `BITCOUNT` invocation rate; not all metrics are available automatically if telemetry is not configured.

### Scenarios to Load-Test

1. Multiple workers concurrently setting bit `1` for the same user — `BITCOUNT` must not double-increment.
2. Thousands of distinct users marking activity on the same day — measure `SETBIT` throughput and Redis CPU.
3. First-time bitmap creation at a high offset — observe latency and memory spikes.
4. Dashboard calling `BITCOUNT` concurrently with other hot requests — check p95/p99.
5. Near TTL deadline — verify logic does not recreate expired day keys outside policy.
6. Redis recovery/restart — verify expectations around persistence and reconciliation data sources.

Testing `BITCOUNT` with only a 64-bit bitmap on a development machine does not represent the performance of a 100-million-bit bitmap in production.

## 15. Common Pitfalls and How to Identify Them

| Symptom | Possible cause | How to check or fix |
| --- | --- | --- |
| `GETBIT` always returns `0` | Key does not exist, wrong offset, wrong Redis database/prefix, key expired via TTL | Check key, mapping, `TTL`, and connection |
| `BITCOUNT` lower than actual user count | Multiple users sharing an offset, key deleted or recreated, some events not written | Audit mapping and write pipeline |
| `BITCOUNT` higher than actual user count | One user has multiple indexes, writer sets invalid bits, improper ID reuse | Check index allocation rules and source data |
| First `SETBIT` is very slow | High offset forces Redis to allocate a large String | Bound offsets and use a true dense index |
| Redis memory spikes unexpectedly | Writing bits at very distant positions, creating many period bitmap keys without cleanup | Check `STRLEN`, `MEMORY USAGE`, input IDs, and TTL |
| `BITCOUNT` is slow despite few `1` bits | Very long String, many `0` bits still must be scanned | Check `STRLEN`, reduce frequency, or partition |
| Dashboard double-counts after adding a separate counter | Counter increments on every `SETBIT`, even when old bit was `1` | Increment only on `0 → 1` transitions, atomically |
| `BITCOUNT key 0 0` yields unexpected result | Default range is in **bytes**, not bits | Distinguish byte offsets from bit offsets |
| Command fails with `WRONGTYPE` | Key holds a Hash/Set/List instead of a String | Use a dedicated bitmap namespace, inspect with `TYPE` |
| Previous day's data disappears unexpectedly | TTL expired or key was deleted | Clarify retention policy and authoritative source |
| User is offline but bit remains `1` | Bitmap tracks "was online" rather than current state | Re-evaluate bit semantics and session/presence logic |
| Old user's bit "transfers" to a new user | Dense index was reused | Do not reuse indexes while old data is still valid |

### Distinguishing Connection Errors from Data Errors

If Spring Data Redis throws `RedisConnectionFailureException` or a connection-phase timeout, you cannot conclude the bitmap itself is wrong. Check the Redis endpoint, authentication, networking, and client configuration first. Only once the application can read the key should you investigate offsets, serializers, Redis types, TTL, and bit counts.

## 16. Step-by-Step Hands-On Practice

The following commands are for a test Redis instance. Use a dedicated namespace and delete created keys when finished if they do not need to be kept.

### Exercise A — Setting, Reading, and Counting Bits

```redis
DEL lesson:bitmap:a
SETBIT lesson:bitmap:a 2 1
SETBIT lesson:bitmap:a 5 1
SETBIT lesson:bitmap:a 2 1
GETBIT lesson:bitmap:a 2
GETBIT lesson:bitmap:a 3
BITCOUNT lesson:bitmap:a
STRLEN lesson:bitmap:a
```

Expected: the first two `SETBIT` commands return the old bit `0`; rewriting offset `2` returns `1`. `GETBIT ... 2` is `1`, `GETBIT ... 3` is `0`, `BITCOUNT` is `2`, and `STRLEN` is `1` byte.

### Exercise B — Clearing a Bit

```redis
SETBIT lesson:bitmap:a 5 0
GETBIT lesson:bitmap:a 5
BITCOUNT lesson:bitmap:a
```

Expected: setting `0` on an enabled bit returns the old value `1`, after which bit `5` is `0` and only one `1` bit remains in the bitmap.

### Exercise C — Confirming the Default Range Is in Bytes

```redis
DEL lesson:bitmap:b
SETBIT lesson:bitmap:b 0 1
SETBIT lesson:bitmap:b 7 1
SETBIT lesson:bitmap:b 8 1
BITCOUNT lesson:bitmap:b 0 0
BITCOUNT lesson:bitmap:b 1 1
BITCOUNT lesson:bitmap:b
```

Expected: `2`, `1`, and `3`, respectively. `0 0` refers to the first byte, not just bit offset `0`.

### Exercise D — Exploring the Cost of High Offsets

In a permitted test environment, try a moderate offset range and observe:

```redis
DEL lesson:bitmap:capacity
SETBIT lesson:bitmap:capacity 999999 1
STRLEN lesson:bitmap:capacity
BITCOUNT lesson:bitmap:capacity
MEMORY USAGE lesson:bitmap:capacity
```

Expected: `STRLEN` equals `125000` bytes, while `BITCOUNT` is only `1`. `MEMORY USAGE` is typically larger than the raw payload due to overhead. You do not need to push the offset into the hundreds of millions to understand the mechanism; doing so on a shared Redis instance can impact resources.

### Exercise E — Business Design Scenario

Suppose a company has 1 million user IDs **densely numbered from 1 to 1,000,000** and wants to count daily active users without needing ordering. You should:

1. Define `offset = userId - 1`.
2. Name keys `bitmap:login:<UTC-date>`.
3. Use `SETBIT key offset 1` when a user accesses the app.
4. Use `GETBIT` to check a single user.
5. Use `BITCOUNT` when total unique daily users need to be tallied.
6. Define retention and avoid unintentionally extending TTL on every visit.

Next, change the assumption: the IDs are now random UUIDs and only 10,000 users are active. Compare the total cost of a UUID → dense offset mapping against a Redis Set storing UUIDs directly. No single choice is always optimal; decide based on cardinality, memory, query needs, and mapping management overhead.

## 17. Self-Check Questions

**Question 1.** What does Redis `TYPE bitmap:login:2026-11-12` return after creating a bitmap with `SETBIT`? Why?

*Hint:* Redis stores Bitmaps as Strings, not as a standalone `bitmap` type.

**Question 2.** `SETBIT k 10 1` returns `0`. Does that mean the total number of `1` bits is currently `0`?

*Hint:* The return value of `SETBIT` is the **previous bit at that offset**.

**Question 3.** A set of user IDs has a maximum value of 100 million, yet only a few hundred IDs actually exist. Is using the ID directly as the bit offset beneficial?

*Hint:* String size is determined by the highest offset, not by the number of enabled bits.

**Question 4.** `GETBIT k 99` returns 0. Can you conclude that "user 99 has definitely never been active"?

*Hint:* The key might not exist yet, its TTL may have expired, or the offset mapping may have changed.

**Question 5.** Why should `BITCOUNT` not be treated as an `O(1)` counter when a bitmap is very long?

*Hint:* Redis has to inspect the bytes within the counting range.

**Question 6.** Does `BITCOUNT k 0 0` count strictly the single bit at offset `0`?

*Hint:* Under the default syntax, start/end are byte offsets.

**Question 7.** An application maintains one bitmap per day and needs to know which users were active on **at least one of two days**. When is `BITOP OR` semantically valid?

*Hint:* A user's offset must keep the same meaning across both days, and the destination key needs its own key/TTL management.

**Question 8.** Two concurrent requests mark user 10,000 with `SETBIT`. Why do both calls not create two enabled bits?

*Hint:* Each offset holds a single bit, and `SETBIT` operates atomically on that position.

**Question 9.** You want an active-user counter to increment as soon as a bit is enabled for the first time. Why is calling `SETBIT` followed by `INCR` insufficient for accuracy in crash scenarios?

*Hint:* Two separate commands can execute only partially; a script combines them when Redis key/slot rules are satisfied.

**Question 10.** A user has three active sessions simultaneously. If each bit corresponds to a user, does `BITCOUNT` represent the number of users or the number of sessions?

*Hint:* Bit meaning depends on the identifier mapping convention.

## 18. Key Takeaways

**A Redis Bitmap is a Redis String manipulated at the bit level.** With `SETBIT`, an application sets a `0/1` state at an offset; `GETBIT` inspects an offset; `BITCOUNT` counts all enabled bits. In Spring Data Redis, `StringRedisTemplate.opsForValue().setBit/getBit` is the direct way to work with single bits; `RedisCallback` with `RedisConnection.stringCommands().bitCount(...)` can be used when counting is needed.

Bitmaps are highly compact when **each entity has a stable offset and the ID space is dense**. However, `BITCOUNT` incurs cost proportional to byte length, `SETBIT` at very high offsets can allocate huge Strings, and a bit holds no timestamp, member metadata, or individual TTL. Proper design requires defining upfront the **offset mapping, key namespace, reporting date/period, retention policy, size limits, and concurrency requirements**. If you need arbitrary IDs, member lists, or pagination, Redis Set/Sorted Set may be more suitable; if you need durable figures, maintain an authoritative data source and reconciliation process independent of the bitmap.
