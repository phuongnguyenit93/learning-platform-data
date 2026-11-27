# Byte-Range Operations and String Appending in Spring Data Redis

Redis has a **String** data type, yet "string" here means **a sequence of bytes**, not necessarily text. A Redis String can hold UTF-8 characters, numeric strings, JSON, binary data, or an application-defined payload. Consequently, Redis provides commands that operate on **a slice of bytes** or **append bytes** without requiring the application to read and rewrite the entire value.

In Spring Data Redis, the corresponding operations typically live on `ValueOperations` of `RedisTemplate` or `StringRedisTemplate`. Four commands to master are:

| Redis Command | Meaning | Common Spring Data Redis API |
|---|---|---|
| `GETRANGE key start end` | Read a byte slice by index range | `opsForValue().get(key, start, end)` |
| `SETRANGE key offset value` | Overwrite a byte slice starting at offset | `opsForValue().set(key, value, offset)` |
| `APPEND key value` | Append bytes to the end of current value | `opsForValue().append(key, value)` |
| `STRLEN key` | Measure value length in **bytes** | `opsForValue().size(key)` |

This lesson aims to clarify offset semantics, single-command atomicity, UTF-8/serializer impacts, TTL behavior, and proper usage in Spring Data Redis.

## 1. A Redis String Is a Byte Sequence, Not a Java String

Consider an ASCII value:

```text
SET demo:text "HELLO"

Bytes (UTF-8/ASCII):   48 45 4C 4C 4F     (hex)
Byte index:             0  1  2  3  4
Displayed characters:   H  E  L  L  O
```

For ASCII, each character takes exactly one byte, so byte positions and character positions look identical. For Unicode, that is no longer true:

```text
SET demo:utf8 "AéB"

UTF-8 (hex):           41 C3 A9 42
Byte index:             0  1  2  3
Unicode characters:     A    é    B
                            └─ 2 bytes ─┘
```

The value `AéB` has three visible characters by ordinary counting, yet `STRLEN` returns **4** because Redis measures bytes. Accented Vietnamese letters, emoji, and other Unicode characters can also require multiple bytes. A complex displayed glyph may even consist of multiple Unicode code points.

### Distinguishing Three Length Layers

| Perspective | Example `AéB` | Meaning |
|---|---:|---|
| Java `String.length()` | 3 | Number of UTF-16 code units in Java string; not always equal to visible characters |
| UTF-8 `getBytes(UTF_8).length` | 4 | Number of bytes after encoding |
| Redis `STRLEN` | 4 | Number of bytes Redis stores in the value |

For emoji outside the Basic Multilingual Plane, Java's `String.length()` can even be 2 for a single code point because UTF-16 uses surrogate pairs. Therefore, **never use Java String character indexes to infer Redis byte positions**, unless you have guaranteed a single-byte encoding or an explicit byte-level protocol.

## 2. Reading a Byte Range with `GETRANGE`

### 2.1. Syntax and Indexing Rules

```redis
GETRANGE key start end
```

In Redis:

- `start` and `end` are **byte indexes**, starting at `0`.
- **Both endpoints are inclusive**: `GETRANGE key 0 3` retrieves up to four bytes.
- Negative indexes count from the end of the value: `-1` is the last byte, `-2` is the second-to-last byte.
- Out-of-bounds ranges are clamped by Redis to existing data; exceeding length in `end` is not an error by itself.
- If the key does not exist, the command returns an empty byte string. If the key holds an incompatible Redis type (e.g., List or Hash), Redis reports a type error.

Example:

```redis
SET demo:range "HELLO WORLD"

GETRANGE demo:range 0 4
# "HELLO"

GETRANGE demo:range 6 10
# "WORLD"

GETRANGE demo:range -5 -1
# "WORLD"

GETRANGE demo:range 0 -1
# "HELLO WORLD" — read the entire value

GETRANGE demo:range 100 200
# "" — range does not overlap data
```

Diagram:

```text
Value:       H E L L O   W O R L D
Index:       0 1 2 3 4 5 6 7 8 9 10

GETRANGE 0 4   └─────────┘         => HELLO
GETRANGE 6 10              └──────┘ => WORLD
GETRANGE -5 -1             └──────┘ => WORLD
```

**Note:** `GETRANGE key 0 -1` is not an efficient pagination command for large values; it requests reading the **entire** value. When you only need a prefix, suffix, or fixed segment, specify a narrow range.

### 2.2. Reading a "Header" and a Payload Slice

Suppose an application stores data using a protocol with a fixed four-byte header:

```text
V 1 0 0 | D A T A - 1 2 3
0 1 2 3   4 5 ...
```

You can read the header without fetching the entire value:

```redis
SET demo:packet "V100DATA-123"
GETRANGE demo:packet 0 3
# "V100"

GETRANGE demo:packet 4 -1
# "DATA-123"
```

This access pattern fits storage formats defining **fixed byte positions**. If data is JSON, CSV, or Unicode text without fixed byte frames, using `GETRANGE` with arbitrary indexes easily slices right through a field or character.

## 3. Overwriting a Byte Range with `SETRANGE`

### 3.1. `SETRANGE` Replaces Bytes in Place, Does Not Insert Characters

Syntax:

```redis
SETRANGE key offset value
```

The command writes byte sequence `value` into the existing value, **starting at byte index `offset`**. Bytes within the overwritten span are replaced; bytes after it remain in place if outside the written span. This is an **overwrite** operation, not `StringBuilder.insert()`.

Example:

```redis
SET demo:patch "Hello"
SETRANGE demo:patch 1 "it"
# (integer) 5 — current length of the Redis String in bytes

GET demo:patch
# "Hitlo"
```

Explanation:

```text
Before:  H e l l o
Index:   0 1 2 3 4

SETRANGE offset=1 value="it"
         ↓ ↓
After:   H i t l o
```

If you expected "Hitello" or "Hito", you confused `SETRANGE` with inserting or replacing the whole string. For complex text edits, use a more suitable storage format or process at the application layer with an explicit concurrency strategy.

### 3.2. Writing Immediately After the Last Byte

When offset equals the current length, the new segment lands after the old content:

```redis
SET demo:patch "Hello"
SETRANGE demo:patch 5 "!"
# (integer) 6

GET demo:patch
# "Hello!"
```

This looks like appending, yet requires knowing the **exact byte offset**. When multiple clients modify the same key concurrently, calling `STRLEN` then `SETRANGE` is **two separate commands**; the offset just read may already be stale. To append without depending on position, `APPEND` is usually preferable.

### 3.3. Offset Beyond Current Length: Redis Zero-Pads the Gap

If offset is greater than the current byte count, Redis fills the gap with `0x00` bytes up to the new position:

```redis
SET demo:gap "AB"
SETRANGE demo:gap 5 "Z"
# (integer) 6

STRLEN demo:gap
# (integer) 6
```

Exact byte representation:

```text
Index:  0    1    2    3    4    5
Byte:   41   42   00   00   00   5A
Text:    A    B   NUL  NUL  NUL   Z
```

Do not assume Redis inserts spaces or `'0'` characters; it inserts **zero bytes**, which can cause trouble if the application treats the value as ordinary text. With `StringRedisTemplate`, reading and printing strings containing NUL bytes can look confusing in logs; inspect data in hex when troubleshooting.

**Memory risk:** Never call `SETRANGE` with a huge offset taken directly from untrusted input. Redis may allocate a large block of bytes to fill the gap, spiking memory usage or failing due to size limits/`maxmemory`. Enforce strict offset and payload length bounds per your data contract.

### 3.4. Non-Existent Key

When using `SETRANGE` with a non-empty value on a missing key, Redis creates a new key; bytes before the offset are zero-filled if offset exceeds 0. The new key gets no automatic TTL unless the application sets expiration separately.

Example:

```redis
DEL demo:new-range
SETRANGE demo:new-range 3 "X"
STRLEN demo:new-range
# (integer) 4
```

The resulting value corresponds to `00 00 00 58` (hex), not a single-character string `X`. Offsets must be non-negative; negative values are not valid write offsets for `SETRANGE`.

## 4. Appending with `APPEND`

### 4.1. Syntax and Return Value

```redis
APPEND key value
```

`APPEND` appends new bytes to the **end** of the current value. Redis returns the **new length in bytes**.

```redis
SET demo:append "Hello"
APPEND demo:append " "
# (integer) 6

APPEND demo:append "Redis"
# (integer) 11

GET demo:append
# "Hello Redis"

STRLEN demo:append
# (integer) 11
```

If the key does not exist, `APPEND` creates a Redis String holding the passed value:

```redis
DEL demo:append-new
APPEND demo:append-new "first"
# (integer) 5

GET demo:append-new
# "first"
```

If the key currently holds a Redis Hash, List, or incompatible type, the command reports `WRONGTYPE` rather than converting to String.

### 4.2. A Single `APPEND` Is Atomic

Redis executes each `APPEND` command as an indivisible operation. If multiple clients concurrently issue:

```redis
APPEND demo:messages "A"
APPEND demo:messages "B"
```

Redis processes one command at a time, so bytes of **one `APPEND` payload cannot interleave inside another payload**. However, arrival and processing order across multiple clients is not a guaranteed business order. The result can be `AB` or `BA` depending on which Redis processes first.

Single-command atomicity **does not** automatically give you:

- Duplicate-write protection when a client retries after a timeout.
- Business-timestamp ordering across multiple producers.
- Appending only when a condition checked in an earlier command still holds.
- Multi-key transactions.
- Record framing, metadata, or independent per-record consumption.

To store queues, event logs, or message streams with multiple consumers, evaluate **Redis Streams (`XADD`/consumer groups)** or Lists (`LPUSH`/`RPUSH`) instead of growing a single `APPEND` String unboundedly.

### 4.3. `APPEND` vs. Read–Concatenate–Write

Dangerous pattern under concurrent requests:

```java
// Avoid when multiple clients update the same key:
String old = redis.opsForValue().get(key);
redis.opsForValue().set(key, (old == null ? "" : old) + suffix);
```

Between `get()` and `set()`, another client may have updated the key. The subsequent `set()` can overwrite all newer data. Moreover, plain `SET` can wipe out any existing TTL unless an expiration-preserving option is used.

When the goal is purely appending bytes, use:

```java
redis.opsForValue().append(key, suffix);
```

This delegates concatenation to Redis in one command, avoiding two-step read-modify-write in the application. If **conditional appending** is required (e.g., checking a version before writing), use a concurrency control mechanism such as a Lua script/Redis Functions or appropriate `WATCH`/`MULTI`/`EXEC`.

## 5. Measuring Size with `STRLEN`

`STRLEN key` returns the byte length of the value at key:

```redis
SET demo:length "ABC"
STRLEN demo:length
# (integer) 3

APPEND demo:length "DEF"
STRLEN demo:length
# (integer) 6
```

For a non-existent key, `STRLEN` returns `0`. For a key holding a non-String Redis type, the command may return a `WRONGTYPE` error.

`STRLEN` is useful for checking payload size limits and locating offsets in binary protocols; keep in mind:

1. This metric is **byte count**, not word count, Unicode code points, or visible characters.
2. The result reflects length at the **moment Redis executes the command** and may change immediately afterward if other clients are writing.
3. Nothing about `STRLEN` automatically makes a `STRLEN` then `SETRANGE` sequence atomic.

## 6. Distinguishing Read, Overwrite, and Append: Combined Example

Suppose a key holds `"012345"`:

```redis
SET demo:all "012345"

GETRANGE demo:all 1 3
# "123" — read-only; original value unchanged

SETRANGE demo:all 2 "AB"
# (integer) 6

GET demo:all
# "01AB45" — replaces two bytes at positions 2 and 3

APPEND demo:all "Z"
# (integer) 7

GET demo:all
# "01AB45Z"

STRLEN demo:all
# (integer) 7
```

| Command | Mutates Value? | Effect on Existing Bytes | Typical Result |
|---|---|---|---|
| `GETRANGE` | No | Reads a byte slice | Retrieved byte sequence |
| `SETRANGE` | Yes | Overwrites from offset; may extend value | New length in bytes |
| `APPEND` | Yes | Keeps old bytes, appends new bytes at end | New length in bytes |
| `STRLEN` | No | Measures only | Byte count |

Common practical questions: "Want to edit the 4th byte of a fixed header?" Use `SETRANGE` with the matching offset. "Want the last 12 bytes?" Use `GETRANGE key -12 -1`. "Want to append a marker at the end?" Use `APPEND`. "Want to know the number of Unicode characters in the content?" `STRLEN` **does not** answer that question.

## 7. Equivalents in `StringRedisTemplate`

In Spring Boot with Spring Data Redis, example Redis connection configuration:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
```

`StringRedisTemplate` uses string serializers, typically encoding keys/values as UTF-8. It suits **text or ASCII data** that the application can safely represent as Java `String`.

### 7.1. Service Example Using Range and Append

```java
package com.example.redis.string;

import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;
import org.springframework.stereotype.Service;

@Service
public class TextSegmentService {

    private final StringRedisTemplate template;

    public TextSegmentService(StringRedisTemplate template) {
        this.template = template;
    }

    public void create(String key, String value, Duration ttl) {
        template.opsForValue().set(key, value, ttl);
    }

    public String readBytes(String key, long start, long end) {
        // start/end are BYTE offsets in Redis, not Java char indexes.
        return template.opsForValue().get(key, start, end);
    }

    public void overwriteBytes(String key, String fragment, long offset) {
        template.opsForValue().set(key, fragment, offset);
    }

    public Integer append(String key, String suffix) {
        return template.opsForValue().append(key, suffix);
    }

    public Long byteLength(String key) {
        return template.opsForValue().size(key);
    }

    public String readAll(String key) {
        return template.opsForValue().get(key);
    }
}
```

Here:

- `create()` writes the full value and attaches TTL via `Duration`.
- `readBytes()` calls `ValueOperations.get(K key, long start, long end)` to invoke Redis's range read; the result is a `String` deserialized from bytes.
- `overwriteBytes()` calls the `set(K key, V value, long offset)` overload to overwrite bytes starting at offset.
- `append()` appends the suffix and returns the new length if the operation yields a result.
- `byteLength()` measures the Redis String size in bytes.

**Important:** Naming the method `readBytes` only emphasizes that **offsets are in bytes**; the actual return type of `StringRedisTemplate` is still a Java `String`. If a byte range slices across a UTF-8 character or the value holds arbitrary binary bytes, deserialization to `String` may fail to reconstruct the original bytes cleanly. When exact byte preservation is required, use the raw bytes API shown next.

### 7.2. Calling the Service in a Simple Flow

```java
service.create("demo:profile:header", "USER0001", Duration.ofMinutes(5));

String prefix = service.readBytes("demo:profile:header", 0, 3);
// "USER"

service.overwriteBytes("demo:profile:header", "99", 4);
// USER9901

Integer length = service.append("demo:profile:header", "-OK");
// 11 bytes

String full = service.readAll("demo:profile:header");
// "USER9901-OK"
```

With the ASCII values here, 1 character = 1 byte, making the results visually intuitive. With Unicode characters, offsets must be calculated against the **serialized byte array**.

### 7.3. Do Not Assume Every `RedisTemplate` Uses UTF-8

`RedisTemplate<String, MyObject>` might use `JdkSerializationRedisSerializer`, a JSON serializer, or a custom serializer. If code calls `getRange()` or `set(..., offset)` on a value serialized into a complex binary format, the byte range may land inside the **serializer's header** or mid-object, rather than the "text part" the application expects.

Example:

```text
Java object ──JDK serializer──► [binary header][class metadata][data]
                                  ↑
                      Offset 0 is not the first character of the field name
```

**Never use `SETRANGE` to patch a few bytes inside JDK-serialized, JSON, or compressed payloads unless you own and understand the exact wire format.** The modified data may become undeserializable. For entities, cached objects, or hashes managed by Redis Repositories, update via the appropriate mapping API.

## 8. Accessing Raw Bytes When Exact Binary Handling Is Required

Suppose an application stores a binary payload or needs to inspect exact UTF-8 bytes. Instead of receiving a decoded `String`, retrieve `byte[]` directly through `RedisCallback`.

```java
package com.example.redis.string;

import java.nio.charset.StandardCharsets;
import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RawByteRangeReader {

    private final StringRedisTemplate redis;

    public RawByteRangeReader(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public byte[] readExactBytes(String key, long start, long end) {
        byte[] rawKey = key.getBytes(StandardCharsets.UTF_8);

        return redis.execute(
            (RedisCallback<byte[]>) connection ->
                connection.stringCommands().getRange(rawKey, start, end)
        );
    }
}
```

This snippet uses Spring's Redis connection abstraction while reading the **raw byte array** returned by Redis. You must match the key serializer: since `StringRedisTemplate` uses UTF-8 keys, the key is encoded via `StandardCharsets.UTF_8`. If Redis keys were written by another serializer, manually encoding keys as UTF-8 could query the wrong physical key name.

To inspect the result:

```java
byte[] fragment = reader.readExactBytes("demo:utf8", 1, 1);
System.out.println(java.util.HexFormat.of().formatHex(fragment));
// May print "c3" if the Redis value is UTF-8 encoded "AéB".
```

In this example, `0xC3` is only the **first byte** of the character `é`, so it does not form a complete UTF-8 sequence yet. Raw bytes let the application distinguish this accurately; converting it immediately to a Java String may cause the decoder to emit replacement characters or fail depending on configuration.

If an application works primarily with binary data, configure a dedicated `RedisTemplate<String, byte[]>` with a matching byte-array serializer. The key rule is **never accidentally mix text and binary serializers on the same keyspace**.

## 9. Slicing UTF-8 Mid-Character: An Easy-to-Miss Bug

Example `AéB` has bytes `41 C3 A9 42`. Different ranges:

| Command | Returned Bytes (hex) | Interpretation |
|---|---|---|
| `GETRANGE key 0 0` | `41` | Valid `A` |
| `GETRANGE key 1 1` | `C3` | First byte of `é`, incomplete for UTF-8 decoding |
| `GETRANGE key 1 2` | `C3 A9` | Valid `é` |
| `GETRANGE key 3 3` | `42` | Valid `B` |
| `GETRANGE key 0 -1` | `41 C3 A9 42` | Full `AéB` |

Try:

```redis
SET demo:utf8 "AéB"
STRLEN demo:utf8
# (integer) 4

GETRANGE demo:utf8 1 2
# "é" if terminal/redis-cli renders UTF-8 properly
```

For `GETRANGE demo:utf8 1 1`, never rely on terminal character rendering as byte proof; terminals may print replacement glyphs or escape sequences. Inspect hex output when diagnosing.

### 9.1. `SETRANGE` Can Corrupt Valid UTF-8

Suppose the initial value is `AéB` (hex `41 C3 A9 42`):

```redis
SETRANGE demo:utf8 1 "Z"
```

After the command, the bytes become `41 5A A9 42`. The trailing `A9` byte is an orphaned UTF-8 continuation byte without a leading byte. The Redis value remains valid bytes to Redis, **yet is no longer valid UTF-8 text**.

That is why range operations fit:

- Structured binary payloads with fixed offsets.
- ASCII strings with a strict data contract.
- Headers/segments with defined byte lengths.
- Deliberate byte-slice inspection or extraction.

They are unsuitable for editing the "Nth character" in Vietnamese or Unicode text without accounting for encoding boundaries.

### 9.2. How Should You Slice Unicode Characters?

If you need to slice text by characters:

1. Read the string via the active text serializer instead of slicing arbitrary Redis bytes.
2. Process by code point or grapheme cluster if user-visible characters are required.
3. Write the updated value back using proper concurrency control.

If text is large and requires frequent partial edits, a single Redis String may not be appropriate; consider splitting data into independent parts or storing structured records in suitable storage.

## 10. TTL During Range Reads, Range Writes, and Appends

Key expiration exists independently of byte-range semantics. `GETRANGE` and `STRLEN` are read commands, so they do not reset TTL.

When **modifying an existing key**, `APPEND` and `SETRANGE` generally preserve the existing expiration; they do not automatically refresh TTL like a full overwrite with plain `SET`.

Example:

```redis
SET demo:ttl "ABCD" EX 120
TTL demo:ttl
# Near 120 (depending on elapsed time)

APPEND demo:ttl "E"
TTL demo:ttl
# Continues counting down; does not jump back to 120

SETRANGE demo:ttl 0 "Z"
TTL demo:ttl
# Still the remaining TTL of the key

GET demo:ttl
# "ZBCDE"
```

Compare with:

```redis
SET demo:ttl "new-value"
TTL demo:ttl
# -1 — regular SET clears old TTL
```

Redis has the `KEEPTTL` option on `SET` when you want to replace the entire value while preserving the existing TTL. Spring Data Redis provides corresponding overloads and TTL management APIs; when using a template, verify whether the specific write operation preserves TTL.

Two cases to distinguish:

| Case | Behavior |
|---|---|
| `APPEND` or `SETRANGE` on a key **with an existing TTL** | Modifies value; old TTL continues |
| `APPEND` or `SETRANGE` creating a **new key** | New key gets no automatic TTL; needs `EXPIRE` or explicit expiration setup |

If a newly created key must always receive a TTL even under concurrent clients, design a suitable atomic protocol (e.g., Lua/Redis Function). Calling `APPEND` then `EXPIRE` as two separate commands leaves a gap between them; never assume that is a transaction.

### When a Key Vanishes Between Two Operations

`TTL = -2` or an empty `GETRANGE` result can stem from expiration, eviction, deletion, or the key never having existed. A byte-range read gives no metadata explaining why a key is gone. If logic must distinguish those cases, combine state design, metrics, or appropriate observability events.

## 11. Atomicity and Concurrency Scenarios

Redis executes **each** `GETRANGE`, `SETRANGE`, `APPEND`, and `STRLEN` command as a single Redis operation. This differs from guarantees over a **multi-command sequence**.

### 11.1. Two `SETRANGE` Commands Editing Overlapping Slices

Example:

```text
Initial value: "abcdefgh"

Client A: SETRANGE key 2 "XXX"
Client B: SETRANGE key 3 "YYY"
```

Each command is atomic on its own, yet they overwrite overlapping bytes. The final outcome depends on Redis execution order; there is no built-in conflict detection.

If segments must be updated by multiple workers:

- Partition non-overlapping byte regions if the protocol allows.
- Use versions and conditional update checks when consistency is strictly needed.
- Use scripts or optimistic-locking transactions when correctness requires multiple operations to run together.

### 11.2. `STRLEN` Followed by `SETRANGE` Is Not Equivalent to `APPEND`

```text
Client A: STRLEN key → 5
Client B: APPEND key "B" → key length 6
Client A: SETRANGE key 5 "A"
```

Client A can **overwrite** the byte B just appended at offset 5. When the goal is appending data, use `APPEND` instead of a manual offset-calculation sequence.

### 11.3. Using `APPEND` to Write Bounded Records

A Redis String appended endlessly grows in size. Concatenating JSON objects back-to-back:

```text
{"event":1}{"event":2}{"event":3}
```

lacks clear delimiters, making it hard for readers to detect record boundaries and resume from a valid offset. Even with newlines added, requirements like retries, ordering, retention, multiple consumers, and acknowledgments are not automatically solved.

When the goal is:

- **Event counters**: use `INCR`/`INCRBY` rather than appending `"1"` characters.
- **Simple queues**: evaluate Redis Lists.
- **Event logs or messages with consumer groups**: evaluate Redis Streams.
- **Partial object updates**: consider Redis Hashes if fields are independent.
- **Fixed-layout binary payloads**: `SETRANGE`/`GETRANGE` can fit if schema is strictly controlled.

## 12. Testing Behavior in Spring Data Redis

An integration test can use `StringRedisTemplate` against a test Redis instance to observe exact command behavior. The example below is written with JUnit 5 and a Spring Boot context configured for Redis; run only against a dedicated test Redis instance.

```java
package com.example.redis.string;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;

@SpringBootTest
class RedisByteRangeIntegrationTest {

    private static final String KEY = "test:range:demo";

    @Autowired
    private StringRedisTemplate redis;

    @AfterEach
    void cleanup() {
        redis.delete(KEY);
    }

    @Test
    void getRangeUsesInclusiveByteIndexes() {
        redis.opsForValue().set(KEY, "HELLO");

        assertEquals("HEL", redis.opsForValue().get(KEY, 0, 2));
        assertEquals("LO", redis.opsForValue().get(KEY, -2, -1));
        assertEquals(5L, redis.opsForValue().size(KEY));
    }

    @Test
    void setRangeOverwritesInsteadOfInserting() {
        redis.opsForValue().set(KEY, "Hello");
        redis.opsForValue().set(KEY, "it", 1);

        assertEquals("Hitlo", redis.opsForValue().get(KEY));
    }

    @Test
    void appendAddsBytesAndReturnsNewLength() {
        redis.opsForValue().set(KEY, "AB");
        Integer newLength = redis.opsForValue().append(KEY, "CD");

        assertEquals(4, newLength);
        assertEquals("ABCD", redis.opsForValue().get(KEY));
    }

    @Test
    void appendAndSetRangePreserveExistingTtl() {
        redis.opsForValue().set(KEY, "AB", Duration.ofMinutes(2));
        redis.opsForValue().append(KEY, "C");
        redis.opsForValue().set(KEY, "Z", 0);

        Long ttl = redis.getExpire(KEY);
        assertTrue(ttl != null && ttl > 0);
        assertEquals("ZBC", redis.opsForValue().get(KEY));
    }
}
```

Important test conditions:

- The Redis instance for testing must be isolated and never point to production Redis.
- `@SpringBootTest` must locate Redis connection properties in the test environment.
- Tests must clean up only keys they own; if tests run in parallel on the same Redis, use unique per-test prefixes or IDs.
- The TTL test does not assert the exact initial duration because real time elapses; it checks only that TTL remains positive afterward.

### Verifying Exact UTF-8 Bytes

When testing multi-byte data, verify raw ranges with byte arrays:

```java
import static org.junit.jupiter.api.Assertions.assertArrayEquals;

import java.nio.charset.StandardCharsets;
import org.springframework.data.redis.core.RedisCallback;

redis.opsForValue().set(KEY, "AéB");

byte[] keyBytes = KEY.getBytes(StandardCharsets.UTF_8);
byte[] firstByteOfEAcute = redis.execute(
    (RedisCallback<byte[]>) connection ->
        connection.stringCommands().getRange(keyBytes, 1, 1)
);

assertArrayEquals(new byte[] {(byte) 0xC3}, firstByteOfEAcute);
```

This example measures the exact bytes returned at the Redis layer, independent of how Java `String` renders incomplete UTF-8 sequences.

## 13. Practical Use Cases

### 13.1. Reading the Header of a Binary Payload

A service stores keys using a team-defined format:

```text
[4 byte magic][1 byte version][payload bytes...]
```

Instead of reading megabytes of payload just to check the version:

```redis
GETRANGE payload:123 0 4
```

The application must still verify all 5 bytes arrived and parse the schema properly. `GETRANGE` reduces bytes transferred to the client, though it does not understand header structure by itself.

### 13.2. Patching a Fixed Field in ASCII Data

Suppose the format is `STATUS=0;COUNT=0010` and the status byte offset is fixed:

```redis
SET demo:fixed "STATUS=0;COUNT=0010"
SETRANGE demo:fixed 7 "1"
GET demo:fixed
# "STATUS=1;COUNT=0010"
```

This works only when layout is fixed and updates are tightly controlled by the application. If a field can vary in length, writing bytes by offset breaks the layout.

### 13.3. Appending a Suffix to an ASCII Value

```redis
SET demo:trace "job-123"
APPEND demo:trace ":done"
GET demo:trace
# "job-123:done"
```

For small values and independent appends, `APPEND` is simple. If you need to collect long-lived event logs with multiple consumers or replay, choose another data structure to avoid an unboundedly growing String.

### 13.4. Slicing Unicode Text

A requirement to "extract the first 10 characters of a Vietnamese passage" **should not** be implemented with `GETRANGE key 0 9`. That reads 10 **bytes**, which can slice inside a Unicode character. Read and slice strings at the text layer, or design byte indexes/offsets while preserving UTF-8 boundaries when writing.

## 14. Performance Notes and Limitations

### 14.1. Large Values and Network Cost

`GETRANGE` returns only the requested byte slice, reducing transfer size when only a small segment is needed. However, Redis still holds the entire value in memory; `GETRANGE` **does not turn Redis Strings into a chunked storage engine**.

`APPEND` and `SETRANGE` resize values and can trigger additional memory allocations. Very large key values put pressure on:

- Redis RAM and eviction behavior.
- Network bandwidth when reading whole values.
- Replication and persistence overhead depending on configuration.
- Operation latency when handling large values.
- Data recovery or migration across nodes.

Enforce size limits at the application layer and monitor Redis memory/latency; never use unbounded `APPEND` as an infinite log file.

### 14.2. `SETRANGE` Is Not Random Disk Writing

Redis is primarily an in-memory data store. `SETRANGE` enables positional byte access within a **Redis String**, yet does not mean each command performs an in-place block update on disk. Redis still manages the data structure in RAM and persistence per server configuration.

### 14.3. Key and Serializer Management

When deploying Spring Data Redis:

- Use explicit key namespaces, such as `shop:prod:v1:segment:123`, so one service cannot misread another service's key.
- Standardize serializers across **every** read/write path touching the same key.
- Use `SETRANGE` only on data whose exact wire format and offsets are owned by the application.
- When multiple services or versions access the same data, review format compatibility and concurrency.
- Inspect `TYPE key` and `STRLEN key` in observability environments if `WRONGTYPE` or format mismatches occur.

### 14.4. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Thinking `GETRANGE` `end` is exclusive | Reads one byte too few or too many | Remember both `start` and `end` are inclusive |
| Using Java char index as Redis offset | Slices mid-UTF-8 byte sequence | Compute byte offsets per encoding; use raw bytes when needed |
| Thinking `SETRANGE` inserts bytes | Overwrites bytes after offset | Use the right operation or redesign format |
| Calling `SETRANGE` with a huge offset | Creates large zero padding, consuming RAM | Enforce offset and payload bounds |
| Using `STRLEN + SETRANGE` to append | Race condition under concurrency | Use `APPEND` |
| Using `GET + SET` to append | Lost updates; may lose TTL | Use `APPEND` or suitable atomic mechanism |
| Using `APPEND` as an infinite event queue | Value bloats, lacks messaging semantics | Use List/Stream per requirements |
| Using `SETRANGE` to patch binary-serialized objects | Data fails to deserialize | Update through proper serializer/mapping |
| Expecting `APPEND` to refresh TTL | Key still expires on old schedule | Reset TTL explicitly when needed |
| Grouping commands assuming atomicity | Other clients interleave | Use transactions/scripts/Functions when needed |

## 15. Step-by-Step Practice with Redis CLI

Practice on a dedicated learning Redis instance. The goal is observing the difference between byte ranges and string appending.

**Step 1 — Read a range:**

```redis
SET lab:bytes "0123456789"
GETRANGE lab:bytes 2 5
# "2345"

GETRANGE lab:bytes -3 -1
# "789"

STRLEN lab:bytes
# (integer) 10
```

**Step 2 — Overwrite at an offset:**

```redis
SETRANGE lab:bytes 3 "ABC"
# (integer) 10

GET lab:bytes
# "012ABC6789"
```

**Step 3 — Append to the end:**

```redis
APPEND lab:bytes "!"
# (integer) 11

GET lab:bytes
# "012ABC6789!"
```

**Step 4 — Inspect zero padding:**

```redis
DEL lab:gap
SETRANGE lab:gap 4 "X"
# (integer) 5

STRLEN lab:gap
# (integer) 5
```

The value has four `0x00` bytes before `X`. Inspect with a hex viewer to avoid confusing empty strings with zero bytes.

**Step 5 — Observe TTL is not refreshed:**

```redis
SET lab:ttl "A" EX 60
APPEND lab:ttl "B"
SETRANGE lab:ttl 0 "Z"
TTL lab:ttl
# Value keeps counting down from the initial SET

GET lab:ttl
# "ZB" if key has not expired yet
```

**Step 6 — Compare bytes and Unicode:**

```redis
SET lab:utf8 "AéB"
STRLEN lab:utf8
# (integer) 4

GETRANGE lab:utf8 1 2
# "é" if console decodes UTF-8 properly
```

For `GETRANGE lab:utf8 1 1`, the result is a single byte `0xC3`: do not treat it as a complete Unicode character.

## 16. Self-Check Questions

**1. `GETRANGE k 0 4` reads at most how many bytes?**  
Five bytes, because both `start` and `end` are inclusive.

**2. What does `GETRANGE k -1 -1` mean?**  
Reads the last byte if the key holds data.

**3. Given `SET k "HELLO"`, what is the result of `SETRANGE k 1 "AB"`?**  
`"HABLO"`. Two bytes at indexes 1 and 2 are overwritten; the remaining bytes stay intact.

**4. Why can `SETRANGE k 1000000 "X"` be dangerous even though it writes one character?**  
Redis may have to allocate zero-byte padding from the old length up to the new offset, making the value huge and consuming memory.

**5. Two concurrent requests want to append a suffix. Should you use `STRLEN` then `SETRANGE`, or `APPEND`?**  
`APPEND`, because appending runs in one Redis command; `STRLEN` then `SETRANGE` can race.

**6. What is the Redis `STRLEN` of `"AéB"` if stored as UTF-8?**  
Four bytes: `41 C3 A9 42`. This differs from the visible character count.

**7. Why should you not use byte-offset `GETRANGE` to extract the "first 10 characters" of Vietnamese text?**  
Because UTF-8 characters can span multiple bytes, so a 10-byte slice may cut through the middle of a character.

**8. Does `APPEND` on a key with a 30-second TTL reset the TTL back to 30 seconds?**  
No. The existing TTL keeps counting down; refreshing expiration requires an explicit TTL-setting operation.

**9. When should you use `RedisCallback` returning `byte[]` instead of `StringRedisTemplate.get(key, start, end)`?**  
When you must preserve exact binary payloads or slices that may contain incomplete UTF-8 byte sequences.

**10. Why does `APPEND` not replace Redis Streams for event systems?**  
Because an appended byte sequence has no message IDs, consumer groups, acknowledgments, per-consumer delivery, or retention policies.

## 17. Key Takeaways

- **`GETRANGE` reads a byte range** with 0-based indexing, inclusive endpoints, and negative-index support.
- **`SETRANGE` overwrites bytes from an offset**, rather than inserting characters; offsets past the end introduce zero-byte padding.
- **`APPEND` concatenates bytes at the end** in one atomic command and returns the new length.
- **`STRLEN` counts bytes**, not Unicode characters or Java `char` units.
- In Spring Data Redis, `StringRedisTemplate.opsForValue()` provides corresponding APIs, yet **offsets remain byte offsets** in the serialized representation.
- With UTF-8 text or binary values, manage encoding boundaries carefully; use raw byte APIs when preserving exact bytes.
- Modifying ranges or appending on a key with an existing TTL **does not automatically refresh expiration**; newly created keys need their own TTL policy.
- One atomic Redis command does not make a multi-command sequence atomic. Design concurrency around business semantics.

Understanding **byte ranges**, **overwrites**, and **appending** accurately helps you leverage Redis Strings effectively for fixed-layout data, avoid Unicode bugs, and pick the right Spring Data Redis abstraction when multiple requests update a single key.
