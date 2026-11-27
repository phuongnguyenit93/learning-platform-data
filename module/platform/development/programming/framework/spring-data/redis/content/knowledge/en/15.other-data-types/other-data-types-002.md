# Bitfield and Operating on Numeric Fields in a Binary String

Redis is commonly introduced as a key–value store with String, Hash, List, Set, and Sorted Set types. However, **a Redis String does not hold only text**: fundamentally, its value can be an arbitrary sequence of binary bytes. Redis provides the **`BITFIELD`** command to treat that byte sequence as a memory region holding multiple **integer fields of arbitrary bit widths** and directly read, write, or increment/decrement individual fields.

For example, an application stores 100 counters, each requiring values only from 0 to 15. Using a separate key per value forces the system to pay key and metadata overhead for many entries. With Bitfield, each counter occupies **4 bits**, so the raw data for 100 counters needs only about **50 bytes**, excluding Redis key, Redis object, allocator, and other overheads.

In **Spring Data Redis**, the central API for this capability is:

```java
stringRedisTemplate.opsForValue().bitField(key, subCommands);
```

It accepts a `BitFieldSubCommands` object describing a sequence of `GET`, `SET`, `INCRBY` operations and overflow policies. This lesson explains how to organize binary data, map bits to numbers, invoke commands via Redis CLI and Java, enforce valid bounds, understand atomicity and concurrency, as well as the risks when applying it to production data.

## 1. When Is Bitfield Useful?

Suppose you have many small, independent numbers that need to be accessed by **known positions**:

- A set of scores from 0 to 15, using 4 bits per element.
- Event occurrence counters per time bucket, using 8 or 16 bits.
- Statuses represented as integer codes in a bounded range, such as 0–7 per position.
- A grid of tiles in a game, each holding a terrain type code or small score.
- Temporary statistical data with many fixed-numbered buckets.

A single Redis String can hold these numeric fields contiguously:

```text
Redis key: demo:metrics:packed

bit 0                             bit 31
  |                                  |
  v                                  v
+--------+--------+--------+--------+
|  u8 #0 |  u8 #1 |  u8 #2 |  u8 #3 |
+--------+--------+--------+--------+
|  00010 |  00025 |  00200 |  00000 |  ← interpreted values
+--------+--------+--------+--------+
```

Each `u8` field is 8 bits wide and represents an unsigned integer from **0 to 255**. Four fields reside together inside one Redis String, rather than four separate Redis keys.

### 1.1. How Does Bitfield Differ from Redis Hash?

Redis Hash:

```text
stats:42
    views    -> "120"
    likes    -> "15"
    shares   -> "7"
```

Redis Bitfield:

```text
stats:42:packed
    u16 at bit 0  -> views
    u16 at bit 16 -> likes
    u8  at bit 32 -> shares
```

Hash uses **business-meaningful field names**, which is convenient when the schema evolves or fields must be read by name. Bitfield uses **offset + width**, which fits when the set of fields is known in advance and a very compact representation is desired.

| Criterion | Hash | Bitfield in String |
|---|---|---|
| Attribute identification | Field name like `views` | Bit offset and width |
| Updating a single attribute | `HSET`, `HINCRBY` | `BITFIELD SET`, `INCRBY` |
| Direct readability via CLI | Easy to read | Must remember encoding and offset |
| Schema flexibility | Higher | Requires strict layout management |
| Very large count of small integer fields | Per-field overhead | Can be very byte-efficient |
| Arbitrary values/long strings/JSON | Suitable depending on field | Not suitable |
| Field-level TTL | Depends on Redis/API and design | No per-bit-slice TTL |
| Maintenance when adding/changing fields | Easier | May require migration |

**Do not choose Bitfield just to save a bit of RAM.** If the data has few fields, needs to be read by name, has a frequently changing schema, or requires manual debugging, Hash is usually simpler and less error-prone.

## 2. A Redis String Is a Byte Region, Not a UTF-8 String by Default

The Redis command:

```redis
SET demo:text "hello"
```

creates a Redis String containing the bytes of the word `hello`. Redis also allows a String value to contain binary bytes that do not form valid text.

When running:

```redis
BITFIELD demo:packed SET u8 0 255
```

the key `demo:packed` contains a single byte `11111111` (`0xFF`). This byte is **not** the text string `"255"` made of three ASCII characters.

The difference:

```text
SET demo:number "255"
    → ASCII bytes: 0x32 0x35 0x35

BITFIELD demo:packed SET u8 0 255
    → binary byte: 0xFF
```

Therefore, after writing with `BITFIELD`, you should not do:

```java
String text = redis.opsForValue().get("demo:packed");
```

and expect to receive `"255"`. With `StringRedisTemplate`, the value serializer is designed for UTF-8 strings, whereas the actual value may contain bytes that are invalid as text. The right way to read is to **keep using bitfield operations** with matching width and offset.

`StringRedisTemplate` is still suitable for executing `bitField(...)` thanks to its string key serializer. Calling bitfield operations invokes Redis commands on the internal bytes; it does not mean the binary value has become a readable Java String.

### 2.1. The Redis Type Seen by the Server Is Still `string`

```redis
TYPE demo:packed
```

When the key exists, the output is:

```text
string
```

There is no Redis type named `bitfield` separate from String. `BITFIELD`, `GETBIT`, `SETBIT`, `BITCOUNT`, and bitmap commands all operate on the **same Redis String data family**.

## 3. Bits, Bytes, and Numeric Field Positions

One byte has 8 bits:

```text
Byte 0:
+---+---+---+---+---+---+---+---+
| 7 | 6 | 5 | 4 | 3 | 2 | 1 | 0 |  ← bit significance
+---+---+---+---+---+---+---+---+
  ^                               ^
  |                               |
offset 0                       offset 7
```

In `BITFIELD` syntax, offset **0 is the most significant bit (MSB) of the first byte**, not the least significant bit.

Suppose we store:

```redis
BITFIELD demo:byte SET u8 0 165
```

165 in 8-bit binary is:

```text
165 decimal = 10100101 binary

Bit offset:   0 1 2 3 4 5 6 7
Bit value:    1 0 1 0 0 1 0 1
```

Reading:

```redis
BITFIELD demo:byte GET u8 0
```

returns 165.

Single-bit commands:

```redis
GETBIT demo:byte 0
GETBIT demo:byte 1
GETBIT demo:byte 2
```

return 1, 0, and 1, respectively.

### 3.1. Start Positions Are Measured in Bits, Not Bytes

The command:

```redis
BITFIELD demo:packed SET u8 16 42
```

means writing **8 bits starting at bit offset 16**, which is the third byte (zero-indexed). It does not mean writing at byte offset 16.

Formula for a sequence of fields with fixed width `w`:

\[
\text{bitOffset}(i) = i \times w
\]

Where `i` is the zero-based field index.

Example for `u4`:

| Index | Bit offset | Occupied bits |
|---|---:|---|
| 0 | 0 | 0–3 |
| 1 | 4 | 4–7 |
| 2 | 8 | 8–11 |
| 3 | 12 | 12–15 |

Being off by even one bit in the chosen offset causes fields to overlap, so writing one field will corrupt part of another.

### 3.2. Numeric Fields Do Not Have to Align with a Single Byte

For example:

```redis
BITFIELD demo:unaligned SET u5 3 23
```

A `u5` field starting at bit 3 occupies bit offsets 3–7, still within the first byte. If it starts at offset 7, the 5 bits span across the boundary between the first and second bytes.

Redis automatically handles positions unaligned with byte boundaries. This differs from many binary protocol libraries that require fields to be 8, 16, or 32 bits aligned.

## 4. Encoding: Signed `iN` and Unsigned `uN` Integers

Redis BITFIELD uses the encodings:

```text
uN → unsigned integer, N bits
iN → signed integer, N bits, two's complement representation
```

Examples:

| Encoding | Width | Valid value range |
|---|---:|---:|
| `u1` | 1 bit | 0 … 1 |
| `u2` | 2 bits | 0 … 3 |
| `u4` | 4 bits | 0 … 15 |
| `u8` | 8 bits | 0 … 255 |
| `u16` | 16 bits | 0 … 65,535 |
| `i4` | 4 bits | -8 … 7 |
| `i8` | 8 bits | -128 … 127 |
| `i16` | 16 bits | -32,768 … 32,767 |
| `i32` | 32 bits | -2,147,483,648 … 2,147,483,647 |

Redis supports **signed integers from 1 to 64 bits** and **unsigned integers from 1 to 63 bits** for the BITFIELD command. You should not use `u64` in executable examples, as Redis BITFIELD does not support 64-bit unsigned fields due to integer reply constraints in the protocol.

General formulas:

\[
uN: \quad 0 \le x \le 2^N - 1
\]

\[
iN: \quad -2^{N-1} \le x \le 2^{N-1} - 1
\]

Choose unsigned when **values are always non-negative**; choose signed when negative numbers must be represented. If values can exceed the chosen range, you must increase the field width or change the design.

### 4.1. The Same Bit Sequence Can Be Interpreted Differently

Suppose a byte is `11111111`:

```redis
DEL demo:signed
BITFIELD demo:signed SET u8 0 255
BITFIELD demo:signed GET u8 0 GET i8 0
```

Results of the two GETs:

```text
u8 → 255
i8 → -1
```

The physical byte did not change; decoding it with different encodings yields different values. **The schema must record both width and signedness**, not just the offset.

### 4.2. Why Do Negative Numbers Use Two's Complement?

In two's complement signed encoding, the highest bit represents the sign and the numeric value is decoded using two's complement. For instance:

```text
i8 -1   → 11111111
i8 -128 → 10000000
i8 127  → 01111111
```

This explains why, when an 8-bit signed integer overflows past 127 under `WRAP` mode, the result wraps around to -128.

## 5. The `BITFIELD` Command: Syntax and Return Structure

General form:

```redis
BITFIELD key
  [GET encoding offset]
  [SET encoding offset value]
  [INCRBY encoding offset increment]
  [OVERFLOW WRAP|SAT|FAIL]
  ...
```

A single call can contain **multiple subcommands**. Redis executes the subcommands in order and returns an array of results corresponding to each read/write/increment operation.

Example:

```redis
DEL demo:fields
BITFIELD demo:fields SET u8 0 12 SET u8 8 25 GET u8 0 GET u8 8
```

Expected result:

```text
1) (integer) 0     # First SET returns old value
2) (integer) 0     # Second SET returns old value
3) (integer) 12    # GET first field
4) (integer) 25    # GET second field
```

Within the same command, subsequent subcommands see the writes performed by preceding subcommands.

| Subcommand | Action | Result |
|---|---|---|
| `GET type offset` | Reads numeric field | Current value |
| `SET type offset value` | Replaces numeric field value | **Previous value** |
| `INCRBY type offset delta` | Increments/decrements a numeric field | **New value** |
| `OVERFLOW policy` | Changes overflow handling rule for subsequent operations | Produces no separate result element |

**Very common mistake:** assuming the result of `SET` is the new value. Remember that Redis returns the value before the write for `SET`, whereas `INCRBY` returns the value after incrementing.

### 5.1. GET on a Nonexistent Key

```redis
DEL demo:empty
BITFIELD demo:empty GET u8 0 GET i8 8
```

Returns 0 values. When reading beyond the existing portion of a String, Redis interprets missing bits as **`0` bits**.

A GET returning 0 **does not prove the data was previously created**. In a business-critical schema, you need an initialization flag, metadata/version, or a separate `EXISTS` check if you must distinguish "never created" from "explicitly 0".

### 5.2. SET/INCRBY Can Expand the String

```redis
DEL demo:grow
BITFIELD demo:grow SET u8 80 1
STRLEN demo:grow
```

Because the 8-bit field sits at offsets 80–87, the String requires at least 11 bytes. Redis expands it and zero-pads unwritten bits.

**Warning:** an erroneous offset in the billions can force Redis to try allocating a massive String, spiking latency, RAM usage, and even causing the command to fail. Offsets should be computed from **validated and bounded** indexes before sending to Redis.

## 6. Direct Offsets and `#index` Offsets

Redis offers two ways to write positions:

```redis
BITFIELD key GET u8 16
```

Reads a `u8` starting at **bit 16**.

```redis
BITFIELD key GET u8 #2
```

Here `#2` means **the second element (zero-indexed) at an 8-bit width**, i.e.:

\[
\text{offset} = 2 \times 8 = 16
\]

The two commands are equivalent when the encoding is `u8`.

Example:

```redis
DEL demo:array
BITFIELD demo:array SET u8 #0 10 SET u8 #1 20 SET u8 #2 30
BITFIELD demo:array GET u8 #0 GET u8 #1 GET u8 #2
```

Read results are 10, 20, 30, respectively.

### 6.1. `#index` Depends on Each Subcommand's Width

```redis
BITFIELD demo:array GET u8 #2
```

uses bit offset `2 × 8 = 16`.

However:

```redis
BITFIELD demo:array GET u16 #2
```

uses bit offset `2 × 16 = 32`.

**The same `#2` with different encodings points to different bit positions.** For a schema containing multiple fields of varying widths, using explicit bit offsets is usually easier to maintain.

### 6.2. Example Packing Two 4-Bit Values in One Byte

```redis
DEL demo:nibbles
BITFIELD demo:nibbles SET u4 0 10 SET u4 4 11
BITFIELD demo:nibbles GET u8 0
```

The GET result is **171**, because:

```text
10 decimal → 1010 (4 bits)
11 decimal → 1011 (4 bits)

Concatenating the two fields:
1010 1011 = 0xAB = 171 decimal
```

This clearly demonstrates that Bitfield **does not store numbers as decimal strings**. Both small numbers are packed into a single byte of binary data.

## 7. Incrementing or Decrementing Fields with `INCRBY`

A counter can live inside a numeric field:

```redis
DEL demo:counter
BITFIELD demo:counter INCRBY u8 0 1
BITFIELD demo:counter INCRBY u8 0 1
BITFIELD demo:counter GET u8 0
```

The increment results are 1 and 2, respectively, and GET returns 2.

Decrement using a negative increment:

```redis
BITFIELD demo:counter INCRBY u8 0 -1
```

Starting from 2, the result is 1.

`INCRBY` on a field is executed by Redis as a server-side atomic operation, avoiding race conditions such as:

```text
Client A GET → add → SET
Client B GET → add → SET
```

Two clients simultaneously sending `BITFIELD ... INCRBY ...` on a field will see results matching the order in which Redis executed the commands.

### 7.1. A Single Command Can Increment Multiple Fields

```redis
BITFIELD demo:stats INCRBY u8 0 1 INCRBY u8 8 2 INCRBY u8 16 3
```

The subcommands run within **one Redis command**. This reduces round trips and prevents commands from other clients from interleaving between the subcommands of that command.

However, if one subcommand hits `OVERFLOW FAIL` and returns nil, the other subcommands **do not automatically roll back**. Do not treat `BITFIELD` as an "all-or-nothing" transaction just because it groups multiple subcommands into a single command.

## 8. Overflow: Behavior When Values Exceed Bit Range

An unsigned 4-bit integer `u4` can only store 0 through 15. If it is currently 15 and incremented by 1, what happens?

Redis lets you choose a policy:

- `WRAP` — wraps around to the opposite end of the value range, **default**.
- `SAT` — saturates at min/max; does not cross the limit.
- `FAIL` — refuses to modify the field on overflow, returning `nil` for that subcommand's result.

### 8.1. `WRAP`: Wrap Around

```redis
DEL demo:wrap
BITFIELD demo:wrap SET u4 0 15
BITFIELD demo:wrap INCRBY u4 0 1
BITFIELD demo:wrap GET u4 0
```

The result after incrementing is **0**, because:

```text
u4: 0 … 15
15 + 1 → 0 (WRAP)
```

Signed fields also wrap using two's complement:

```redis
DEL demo:wrap-signed
BITFIELD demo:wrap-signed SET i8 0 127
BITFIELD demo:wrap-signed INCRBY i8 0 1
```

Result is `-128`.

`WRAP` suits certain cyclic counters or modulo arithmetic. It is **dangerous** if 0 after wrapping gets interpreted as "no visits yet" or "quota reset".

### 8.2. `SAT`: Saturate at Bounds

```redis
DEL demo:sat
BITFIELD demo:sat SET u4 0 15
BITFIELD demo:sat OVERFLOW SAT INCRBY u4 0 1
BITFIELD demo:sat GET u4 0
```

Both the increment result and the GET result are **15**.

If the value is 14 and incremented by 5 with SAT, the result is also 15. When decrementing below 0, it stops at 0.

Use SAT when you want a metric clamped within a range and the application **accepts losing the excess amount**. For instance, a "0–15 level" can saturate at 15.

### 8.3. `FAIL`: Reject Operations Exceeding Bounds

```redis
DEL demo:fail
BITFIELD demo:fail SET u4 0 15
BITFIELD demo:fail OVERFLOW FAIL INCRBY u4 0 1
BITFIELD demo:fail GET u4 0
```

The `INCRBY` result is `nil`, and the field remains 15.

`FAIL` is useful when the application must **know that an increment was rejected** because the limit was reached.

You must distinguish `nil` caused by `OVERFLOW FAIL` from Java/Spring returning `null` in pipelines/transactions or API-layer issues. Do not assume every `null` means overflow without context.

### 8.4. `OVERFLOW` Policy Applies from Where It Is Declared Onward

```redis
BITFIELD demo:mixed \
  OVERFLOW SAT INCRBY u4 0 1 \
  OVERFLOW FAIL INCRBY u4 4 1
```

`SAT` affects operations following it until another `OVERFLOW` is encountered; `FAIL` similarly affects subsequent operations. `GET` does not use overflow because it is a read operation.

If a `BITFIELD` has multiple subcommands and one subcommand fails under `FAIL`, the remaining subcommands can still execute and mutate data. Do not treat the whole result array as a multi-field commit/rollback indicator.

### 8.5. Overflow Also Applies to `SET`

Not only `INCRBY`, the `SET` subcommand is also governed by the specified overflow policy. If you write a number outside the representable range without using `FAIL` or `SAT`, the value may be truncated/wrapped according to the chosen arithmetic rule.

**Always validate inputs on the Java side**, especially when `SET` is invoked with untrusted data. `OVERFLOW FAIL` is a safeguard at Redis, not a replacement for DTO/API validation.

## 9. `BITFIELD_RO`: Read-Only Numeric Field Access

Redis provides a dedicated read-only command **`BITFIELD_RO`**:

```redis
BITFIELD_RO demo:array GET u8 #0 GET u8 #1
```

This command allows only GET subcommands and forbids `SET`, `INCRBY`, or `OVERFLOW` mutations.

It is useful when you need to:

- Read only on replicas/connections or in environments with strict read-only permissions.
- Make intent explicit that the request does not mutate Redis.
- Simplify analysis and permission separation between read and write paths.

`BITFIELD_RO` is available on modern Redis versions; verify the server version in your project. Do not assume `ValueOperations.bitField(...)` in every Spring Data Redis version automatically emits `BITFIELD_RO` when you only add GET subcommands. That API typically maps to `BITFIELD`; if read-only routing or ACL compliance is mandatory, verify what the driver actually sends or use a lower-level API that supports `BITFIELD_RO`.

## 10. BITFIELD Compared with `SETBIT`, `GETBIT`, `BITCOUNT`

Easily confused commands:

| Command | Meaning | Example |
|---|---|---|
| `GETBIT key offset` | Read a 0/1 bit | Completion flag |
| `SETBIT key offset bit` | Write a 0/1 bit | Mark a member |
| `BITCOUNT key` | Count bits with value 1 | Count active days in a bitmap |
| `BITFIELD key GET u4 0` | Interpret multiple bits as an integer | Read level from 0–15 |
| `BITFIELD key SET u4 0 9` | Write multiple bits as an integer | Store a status code |
| `BITFIELD key INCRBY u4 0 1` | Increment an integer spanning several bits | Small counter |

If each position only needs **true/false**, `SETBIT`/`GETBIT` or a Set is simpler. If each position needs a value from 0–15, multiple bits are required; `BITFIELD` expresses this much more directly than calling `GETBIT` four times and assembling the number in Java.

Mixed example:

```redis
DEL demo:flags
SETBIT demo:flags 0 1
SETBIT demo:flags 3 1
BITFIELD demo:flags GET u4 0
```

The first bits are `1001`, so `u4` at offset 0 has value 9.

Remember: these commands **all operate on the bytes of the same String**. If one service treats bit 0 as a boolean flag while another service calls `BITFIELD SET u4 0 ...`, the latter can inadvertently overwrite the former's flag. There must be a clear layout specification and ownership.

## 11. Preparing the Spring Boot Application

Use a local Redis server for testing, such as a Redis container or a dedicated development Redis instance.

With Gradle Groovy DSL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

Example `application.yml` for Spring Boot 3.x:

```yaml
spring:
  data:
    redis:
      host: ${REDIS_HOST:127.0.0.1}
      port: ${REDIS_PORT:6379}
      timeout: 2s
```

Spring Boot typically auto-configures `RedisConnectionFactory` and `StringRedisTemplate` when the starter and a suitable driver are present.

To verify Redis:

```redis
PING
```

Expected response:

```text
PONG
```

If Redis runs in Docker Compose and Spring Boot runs on the **host**, you typically connect via `127.0.0.1` and the published host port. If Spring Boot runs in another container on the same Compose network, the host is the Redis service name (for example `redis`), not `localhost`.

## 12. Java: Reading/Writing Numeric Fields with `BitFieldSubCommands`

Spring Data Redis provides:

```java
List<Long> bitField(
        K key,
        BitFieldSubCommands subCommands
);
```

`BitFieldSubCommands` is constructed via a fluent builder. Common sub-types:

```java
BitFieldSubCommands.BitFieldType.unsigned(8);
BitFieldSubCommands.BitFieldType.signed(16);
```

`valueAt(long)` takes an absolute bit offset.

### 12.1. Example: Setting, Reading, and Incrementing Two `u8` Counters

```java
package example.redis;

import java.util.List;

import org.springframework.data.redis.connection.BitFieldSubCommands;
import org.springframework.data.redis.connection.BitFieldSubCommands.BitFieldType;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class PackedMetricsService {

    private static final String KEY = "demo:metrics:packed";

    private final StringRedisTemplate redis;

    public PackedMetricsService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public List<Long> initializeAndRead() {

        BitFieldSubCommands commands = BitFieldSubCommands.create()
                .set(BitFieldType.unsigned(8)).valueAt(0).to(12)
                .set(BitFieldType.unsigned(8)).valueAt(8).to(25)
                .get(BitFieldType.unsigned(8)).valueAt(0)
                .get(BitFieldType.unsigned(8)).valueAt(8);

        return redis.opsForValue().bitField(KEY, commands);
    }

    public Long incrementSecond() {

        BitFieldSubCommands commands = BitFieldSubCommands.create()
                .incr(BitFieldType.unsigned(8)).valueAt(8).by(1);

        List<Long> results = redis.opsForValue().bitField(KEY, commands);

        return results == null || results.isEmpty() ? null : results.get(0);
    }
}
```

When calling `initializeAndRead()` on an empty key, the result is typically:

```text
[0, 0, 12, 25]
```

The first two positions are the **previous values** returned by `SET`; the next two positions are the GET results. Calling the method a second time will return different previous values because the key now holds data.

In `incrementSecond()`, the `INCRBY` subcommand returns the **value after incrementing**. Unless you change the overflow policy, Redis defaults to WRAP: incrementing 255 by 1 wraps back to 0.

### 12.2. Why Can `List<Long>` Contain `null`?

A single BITFIELD command with multiple subcommands produces multiple results; the Java API returns a matching `List<Long>`. If `OVERFLOW FAIL` prevents an increment from executing, that element in the result list can be `null` because Redis returned nil.

Furthermore, when the template is used inside a pipeline/transaction, the method may return `null` at queueing time instead of a real result list. You must distinguish **null for the whole list** from **null at a specific index in the list**.

Do not write:

```java
long current = results.get(0);
```

without checking for absent results in flows where overflow or pipelining is possible. Java will throw a `NullPointerException` when unboxing a null `Long` element.

### 12.3. Reading Without Writing

```java
public Long readFirst() {

    BitFieldSubCommands commands = BitFieldSubCommands.create()
            .get(BitFieldType.unsigned(8)).valueAt(0);

    List<Long> values = redis.opsForValue()
            .bitField("demo:metrics:packed", commands);

    return values == null || values.isEmpty() ? null : values.get(0);
}
```

This is an example of the **Spring API** issuing a bitfield GET request. As noted earlier, do not equate it with `BITFIELD_RO` for replica routing or ACL purposes without verifying what command the driver actually sends.

## 13. Java: `#index` with `Offset.multipliedByTypeLength()`

To build an array of fixed-width numeric fields, Spring Data Redis supports index-based offsets:

```java
import org.springframework.data.redis.connection.BitFieldSubCommands.Offset;
```

Creating an offset like `#3`:

```java
Offset fieldIndex3 = Offset.offset(3).multipliedByTypeLength();
```

Using it with `u8`:

```java
BitFieldSubCommands commands = BitFieldSubCommands.create()
        .get(BitFieldType.unsigned(8))
        .valueAt(Offset.offset(3).multipliedByTypeLength());
```

Equivalent Redis CLI:

```redis
BITFIELD demo:metrics:packed GET u8 #3
```

Which reads bits 24–31.

If you use `.valueAt(3)` with the same `u8`, that specifies **bit offset 3**, not the third field. The two reads differ:

```java
// Absolute bit offset 3:
.get(BitFieldType.unsigned(8)).valueAt(3)

// Field index 3, because 3 * 8 = 24:
.get(BitFieldType.unsigned(8))
    .valueAt(Offset.offset(3).multipliedByTypeLength())
```

When multiple fields have different widths, `.multipliedByTypeLength()` uses the width of that particular subcommand. Therefore, mixed-width layouts should use explicit fixed absolute bit offsets to avoid confusion.

## 14. Java: Choosing SAT and FAIL Overflow

Spring Data Redis lets you configure increment overflow behavior via the builder.

```java
import org.springframework.data.redis.connection.BitFieldSubCommands;
import org.springframework.data.redis.connection.BitFieldSubCommands.BitFieldType;
import org.springframework.data.redis.connection.BitFieldSubCommands.BitFieldIncrBy.Overflow;
```

### 14.1. Saturating `u4` Counter

```java
public Long addAtMost15(StringRedisTemplate redis, String key) {

    BitFieldSubCommands commands = BitFieldSubCommands.create()
            .incr(BitFieldType.unsigned(4))
            .valueAt(0)
            .overflow(Overflow.SAT)
            .by(1);

    List<Long> values = redis.opsForValue().bitField(key, commands);

    return values == null || values.isEmpty() ? null : values.get(0);
}
```

Once the field reaches 15, further increments continue to return 15. This suits a capped display level, though **it does not tell you whether the increment was accepted or saturated** from the number 15 alone. Business logic must decide how to interpret this result.

### 14.2. Counter Rejecting Increments at 255

```java
public boolean tryIncrementU8(StringRedisTemplate redis, String key) {

    BitFieldSubCommands commands = BitFieldSubCommands.create()
            .incr(BitFieldType.unsigned(8))
            .valueAt(0)
            .overflow(Overflow.FAIL)
            .by(1);

    List<Long> values = redis.opsForValue().bitField(key, commands);

    if (values == null || values.size() != 1) {
        throw new IllegalStateException("BITFIELD did not return one result");
    }

    // null at index 0 means the increment was rejected due to overflow.
    return values.get(0) != null;
}
```

`OVERFLOW FAIL` prevents incrementing beyond the `u8` range. If the field is already 255, Redis returns nil and leaves the field unchanged.

**Business limitation:** this method only guarantees "the value in the field does not exceed 255 during this increment"; it does not ensure each request increments only once, does not set a TTL, and does not solve duplicate increments after timeouts.

## 15. Designing a Fixed-Width Counter Array

Suppose a dashboard stores event counts across 24 hourly buckets. Each hour is a `u16`, holding 0–65,535.

One key per day:

```text
metrics:events:2026-11-12
    hour 0  → u16 #0
    hour 1  → u16 #1
    ...
    hour 23 → u16 #23
```

Minimum raw data:

\[
24 \times 16 = 384 \text{ bits} = 48 \text{ bytes}
\]

This size **excludes** Redis key and allocator overhead, yet illustrates the benefit of packing many small fields.

### 15.1. Example Service for Hourly Counters

```java
package example.redis;

import java.time.Duration;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.List;

import org.springframework.data.redis.connection.BitFieldSubCommands;
import org.springframework.data.redis.connection.BitFieldSubCommands.BitFieldType;
import org.springframework.data.redis.connection.BitFieldSubCommands.BitFieldIncrBy.Overflow;
import org.springframework.data.redis.connection.BitFieldSubCommands.Offset;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class HourlyPackedCounter {

    private static final int HOURS = 24;
    private static final int BITS_PER_HOUR = 16;

    private final StringRedisTemplate redis;

    public HourlyPackedCounter(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Long increment(LocalDate date, int hour) {
        validateHour(hour);

        BitFieldSubCommands commands = BitFieldSubCommands.create()
                .incr(BitFieldType.unsigned(BITS_PER_HOUR))
                .valueAt(Offset.offset(hour).multipliedByTypeLength())
                .overflow(Overflow.FAIL)
                .by(1);

        List<Long> result =
                redis.opsForValue().bitField(key(date), commands);

        if (result == null || result.size() != 1) {
            throw new IllegalStateException("Unexpected BITFIELD response");
        }

        // null: counter has reached 65535 and was not incremented.
        return result.get(0);
    }

    public Long read(LocalDate date, int hour) {
        validateHour(hour);

        BitFieldSubCommands commands = BitFieldSubCommands.create()
                .get(BitFieldType.unsigned(BITS_PER_HOUR))
                .valueAt(Offset.offset(hour).multipliedByTypeLength());

        List<Long> result =
                redis.opsForValue().bitField(key(date), commands);

        return result == null || result.isEmpty()
                ? null
                : result.get(0);
    }

    public Boolean expireDay(LocalDate date, Duration ttl) {
        return redis.expire(key(date), ttl);
    }

    private static void validateHour(int hour) {
        if (hour < 0 || hour >= HOURS) {
            throw new IllegalArgumentException("hour must be 0..23");
        }
    }

    private static String key(LocalDate date) {
        return "metrics:events:" +
                date.format(DateTimeFormatter.ISO_LOCAL_DATE);
    }
}
```

In this example:

- The `hour` index is bounded to `[0, 23]`, preventing writes outside the intended 48-byte region.
- `u16` caps values at 65,535; `Overflow.FAIL` returns null when the counter cannot increment further.
- Each day uses a separate key; you do not grow a giant String holding years of unbounded data.
- `LocalDate` reflects the date in the time zone chosen by the application. UTC or a business time zone must be consistent between producers and dashboards.
- `expireDay` is a separate operation and is not automatically invoked after `increment`; design an appropriate TTL/retention policy if keys should only be kept for a finite duration.

### 15.2. What Should You Watch Out for with TTL in This Model?

`BITFIELD INCRBY` **does not automatically set a TTL** on the String. If a new key is created by an increment, it can persist indefinitely unless an expiration or eviction policy applies.

For example:

```java
redis.expire("metrics:events:2026-11-12", Duration.ofDays(30));
```

This command applies the TTL to **the entire String containing all 24 fields**, not to individual hours.

If the requirement "old days must disappear automatically" is a strict invariant, incrementing and calling `EXPIRE` as two commands leaves a failure window between them. You can use a Lua script or an atomically designed write/expire flow if required. Consider the impact on concurrent writers and TTL refresh rules—do not blindly reset the TTL on every increment if the intent is to expire relative to a fixed calendar day.

## 16. Combining Multiple Fields in One Key with a Clear Layout

Bitfield has no field names. The application must maintain a **layout specification**, for example:

| Field | Encoding | Bit offset | Value range | Meaning |
|---|---|---:|---:|---|
| `status` | `u3` | 0 | 0–7 | Status code |
| `priority` | `u5` | 3 | 0–31 | Priority |
| `attempts` | `u8` | 8 | 0–255 | Attempt count |
| `delta` | `i16` | 16 | -32,768…32,767 | Signed value |

Total width is 32 bits (4 bytes):

```text
bit offset:
0       3       8                16                         32
|-------|-------|----------------|--------------------------|
| u3    | u5    | u8             | i16                      |
|status |priority| attempts      | delta                    |
```

Redis commands:

```redis
DEL demo:layout
BITFIELD demo:layout SET u3 0 5 SET u5 3 17 SET u8 8 9 SET i16 16 -12
BITFIELD demo:layout GET u3 0 GET u5 3 GET u8 8 GET i16 16
```

The GET results are 5, 17, 9, and -12, respectively.

### 16.1. Why Must Binary Schemas Be Versioned?

If version A treats bits 0–2 as `status` and bits 3–7 as `priority`, while version B changes `status` to `u4` starting at 0, the two versions will interpret **the exact same 4 bytes** in two different ways. That can produce corrupted business data while Redis still responds normally.

Some strategies:

- Document the layout explicitly in code and documentation.
- Put the **version in the key**, such as `job:packed:v1:42` and `job:packed:v2:42`.
- If necessary, reserve a few bits in the layout for `schemaVersion`, while evaluating range constraints and upgrade rules.
- When switching versions, use dual-read or a clear migration plan; avoid having two app versions write to the same key under different layouts.

Key-based versioning is usually simpler if there is already a cache TTL and data can be reconstructed from another source.

### 16.2. Overlapping Fields

If you run:

```redis
BITFIELD demo:overlap SET u8 0 255
BITFIELD demo:overlap SET u8 4 0
```

the second field starts at bit 4 and spans to bit 11, thereby **overwriting part of the first field's bits**. Redis has no knowledge that developers expected those two fields to be independent; Redis simply obeys offsets and widths.

Centralize offset calculations in a single class or helper with strict validation rather than letting every endpoint compute offsets with ad-hoc formulas.

## 17. Complexity and Memory Savings

For each BITFIELD subcommand, Redis typically operates on a small bit slice in near O(1) time with respect to bounded field widths, without parsing JSON or scanning an entire Hash. However, end-to-end performance also depends on:

- The number of subcommands in a single command.
- The Redis String size and whether allocation/expansion occurs.
- Serialization, network, round-trips, pipelining, and application latency.
- Contention from multiple clients mutating the same key.
- Redis persistence, replication, and memory pressure.

### 17.1. Raw Size Estimation Formula

For `N` fields of equal width `w`, packed contiguously from offset 0:

\[
\text{rawBytes} = \left\lceil \frac{N \times w}{8} \right\rceil
\]

Examples:

| Field count | Width | Bit size | Raw data bytes |
|---:|---:|---:|---:|
| 100 | 4 | 400 | 50 |
| 1,000 | 8 | 8,000 | 1,000 |
| 24 | 16 | 384 | 48 |
| 10,000 | 2 | 20,000 | 2,500 |

This is the **size of the String's bytes**, not `MEMORY USAGE` for the whole Redis key. Redis also adds object, allocator, metadata, and key-name overhead. If there are very few fields, the storage savings may not justify the layout complexity.

### 17.2. Do Not Confuse "Compact" with "Cheap in Every Situation"

Suppose you pack one million `u8` fields into a single String. The raw data is roughly 1 MB, which may be acceptable in RAM, but if every request increments the same field on the same key, that key can still become a **Hot Key**. In Redis Cluster, a single key belongs to **one hash slot**, so it cannot be automatically spread across multiple nodes.

To scale by tenant, day, or metric group, split across multiple keys:

```text
metrics:tenant:42:2026-11-10
metrics:tenant:42:2026-11-11
metrics:tenant:42:2026-11-12
```

Do not accumulate years of history into a single String. A key written at a very distant offset can become a Big Key even when only a few fields are actually used.

## 18. Validating Offsets and Input Bounds

Bit offsets may be computed from a user ID or positional index. If an index originates from a request, it must be bounded before sending to Redis.

Dangerous pattern:

```java
// NOT RECOMMENDED: unbounded index.
long offset = userProvidedIndex * 16L;
redis.opsForValue().bitField(
        key,
        BitFieldSubCommands.create()
                .set(BitFieldType.unsigned(16))
                .valueAt(offset)
                .to(value)
);
```

Issues:

1. Negative indexes are invalid.
2. Huge indexes can cause sudden String expansion.
3. Multiplication can overflow Java `long`.
4. The value may fall outside the 16-bit range.
5. Request-supplied keys may access unintended namespaces.
6. There is no cap on total key size.

Safer pattern:

```java
private static final int FIELD_WIDTH = 16;
private static final int MAX_FIELDS = 1024;

private static long bitOffset(int index) {
    if (index < 0 || index >= MAX_FIELDS) {
        throw new IllegalArgumentException("index out of range");
    }

    return Math.multiplyExact((long) index, FIELD_WIDTH);
}

private static long requireU16(long value) {
    if (value < 0 || value > 65_535) {
        throw new IllegalArgumentException("value must fit u16");
    }
    return value;
}
```

With `MAX_FIELDS = 1024`, a String of contiguous `u16` fields will have a maximum raw data size of about 2,048 bytes. Bounding this makes memory consumption predictable.

In Redis Cluster, shard/node count and key distribution still need to be designed around access patterns; bounding byte size does not eliminate Hot Key risks.

## 19. Atomicity, Concurrency, and Uncertain Outcomes

### 19.1. A Single Increment Subcommand Is Atomic on the Redis Side

When two Spring Boot instances concurrently send:

```redis
BITFIELD metrics:today INCRBY u16 0 1
```

Redis processes the command sequentially on the node holding the key, avoiding lost updates from a Java read-modify-write cycle.

This is useful for small counters. However, **command atomicity does not mean each business action happens only once**.

### 19.2. Timeouts and Retries Can Cause Duplicate Increments

For example:

```text
T1: Spring Boot sends INCRBY u16 0 1
T2: Redis increments from 10 to 11
T3: Network fails before Spring Boot receives the response
T4: Client retries
T5: Redis increments from 11 to 12
```

One business request incremented the counter twice. `INCRBY` is atomic **per execution**, not idempotent.

If deduplication is required, you may need to store a `requestId`/business event ID and enforce uniqueness appropriately, or use a script that checks an idempotency key alongside incrementing the counter. When multiple Redis keys are involved, Redis Cluster may require them to share a hash slot; critical database-backed state needs a dedicated consistency strategy.

### 19.3. Multiple Fields Within One `BITFIELD`

```redis
BITFIELD metrics:today INCRBY u8 0 1 INCRBY u8 8 1
```

Both increments occur in a single command and execute sequentially without other commands interleaving. Yet when `OVERFLOW FAIL` applies and one increment is rejected, the other increment can still succeed.

If the business rule is **either both counters increment or neither increments**, validate conditions for both before mutating—for example via a properly designed Lua script; do not treat `BITFIELD` with two `INCRBY`s and `FAIL` as a rollback transaction.

### 19.4. `StringRedisTemplate` Can Be Shared Across Threads

A configured `StringRedisTemplate` can be injected into singleton services and shared across request/worker threads. Do not store a low-level `RedisConnection` in a field shared across threads.

Each `bitField` call is executed by the template through Spring Data Redis's connection management. If you need pipelining or transactions, use Spring-managed callbacks/sessions rather than passing connections manually across threads.

## 20. Pipelining, Transactions, and Batched `BITFIELD` Subcommands

You can reduce round trips by grouping **multiple operations on the same key** into a single `BITFIELD` instead of calling `bitField()` separately for each field.

Example:

```java
BitFieldSubCommands commands = BitFieldSubCommands.create()
        .get(BitFieldType.unsigned(8)).valueAt(0)
        .get(BitFieldType.unsigned(8)).valueAt(8)
        .get(BitFieldType.unsigned(8)).valueAt(16);

List<Long> values = redis.opsForValue().bitField("demo:packed", commands);
```

A single Redis call returns a list of three values.

### 20.1. Should You Use Redis Pipelining?

When updating **many different keys**, pipelining can reduce round trips for some workloads. But if you only have a few fields on the same key, a single `BITFIELD` with multiple subcommands is already quite compact.

Notes:

- Pipelining does **not** turn independent commands into an atomic transaction.
- Inside a pipeline/transaction, the API may return `null` immediately at queueing time; results are collected from the pipeline/`EXEC` output according to Spring Data Redis semantics.
- Choose an appropriate serializer if pipeline results include raw bytes or special return types.
- Use `BITFIELD` with a fixed layout; do not queue thousands of unbounded subcommands from user input.

### 20.2. When to Use Redis Transactions?

`MULTI`/`EXEC` can group Redis commands into a Redis transaction, though it lacks relational-database-style rollback on all error types and does not automatically participate in SQL transactions. Problems requiring conditional logic across multiple fields are often easier to express using a **small Lua script**, where conditions are checked before writing.

If a script touches multiple keys in Redis Cluster, account for hash slots and topology execution constraints.

## 21. BITFIELD and Redis TTL

TTL always applies to **the Redis key holding the entire byte sequence**; there is no per-field TTL for `u8 #2` or `i16 16`.

```redis
BITFIELD demo:packed SET u8 #0 10 SET u8 #1 20
EXPIRE demo:packed 300
TTL demo:packed
```

Once the TTL expires, the entire key disappears; reading any field will return 0 under the nonexistent-key rule unless the application distinguishes existence.

In Spring Data Redis:

```java
redis.expire("demo:packed", Duration.ofMinutes(5));
```

If different fields require different lifecycles, split groups into **separate keys** by day, tenant, session, or data category.

### 21.1. `INCRBY` Does Not Automatically Reset Daily

A daily counter needs a key containing a canonically formatted date:

```text
metrics:views:2026-11-12
metrics:views:2026-11-13
```

Using **a single fixed key** and expecting `INCRBY` to reset at midnight is a design flaw. Create keys per day and attach a TTL longer than the retention window so old days are cleaned up.

For critical statistics, evaluate Redis durability and maintain an authoritative durable source rather than relying exclusively on bitfield counters.

## 22. BITFIELD with Spring Cache and Redis Repositories

`BITFIELD` is a low-level data command operating on the bytes of a Redis String. It differs from caching an object with `@Cacheable`.

For example, when using Spring Cache:

```java
@Cacheable(cacheNames = "productById", key = "#id")
public Product getProduct(long id) { ... }
```

The cache abstraction serializes values according to `RedisCacheManager` configuration and manages its own keys/TTLs. It does not provide bit layouts for individual attributes.

Similarly, Redis Repositories with `@RedisHash` operate on object mapping and repository metadata, and do not store entities as packed Bitfield integers.

**Never let multiple abstraction layers write to the same Redis key with different formats.** If the cache manager writes JSON/Java serialization into `metrics:today` while a Bitfield service mutates that key, data will be overwritten or fail to decode.

Use clear namespaces:

```text
app:cache:product:42            → object cache
app:hash:user:42                → Redis Hash
app:bitfield:daily:2026-11-12   → packed binary counters
```

## 23. Inspecting Binary Data in Redis

After creating:

```redis
BITFIELD demo:packed SET u8 0 10 SET u8 8 20
```

Useful diagnostic commands:

```redis
TYPE demo:packed
STRLEN demo:packed
BITFIELD demo:packed GET u8 0 GET u8 8
BITCOUNT demo:packed
TTL demo:packed
MEMORY USAGE demo:packed
```

Meaning:

| Command | Observation |
|---|---|
| `TYPE` | Type is still `string` |
| `STRLEN` | **Byte** length of the Redis String |
| `BITFIELD GET` | Numeric field values according to layout |
| `BITCOUNT` | Number of `1` bits, **not** the sum of field values |
| `TTL` | Remaining lifetime of the **entire key** |
| `MEMORY USAGE` | Estimated Redis memory for the key, including overhead |

`BITCOUNT` on a `u8` with value 10 (`00001010`) returns 2 enabled bits, **not 10**. Thus it cannot replace summing counters.

### 23.1. Why Not Use `GET` for Debugging?

`GET` may return unprintable bytes that render poorly in a terminal or cause decoding errors. Using `BITFIELD GET` with the right width/offset is much clearer.

In development environments, some tools can display bytes in hex, but avoid logging raw binary or sensitive data to production logs.

### 23.2. Avoid Scanning the Entire Keyspace to Find Packed Counters

Keys should be directly determinable from business context, such as date and tenant. Do not write an endpoint running `KEYS app:bitfield:*` on production Redis and iterating every String to aggregate metrics. If cross-key aggregation is needed, maintain a list of partitions or use an appropriate analytics system. `SCAN` can support controlled maintenance tasks, but it is not a query engine.

## 24. When Should You Not Use Bitfield?

Bitfield is not a good fit for all counters.

| Requirement | Structure to consider | Why |
|---|---|---|
| A single integer counter without small bounds | Redis String with `INCRBY` | Simpler, no manual width management |
| A few named, evolving attributes | Redis Hash | `HGET`/`HSET` by name, easier to maintain |
| Many booleans by stable ID | Bitmap/`SETBIT` | Each item needs only 1 bit |
| Many small integers by index | Bitfield | Compact packing |
| Counters exceeding 63/64-bit range | Different model or split data | BITFIELD has bit-width limits |
| Monetary values or critical transactions | Database/transactions and proper representation | Requires strong consistency/durability |
| Querying by attributes across millions of objects | Database/search/index | Bitfield has no field-name queries |
| Fields requiring independent TTLs | Multiple keys or different data model | Redis String TTL applies to the whole key |
| Frequently changing schema | Hash or JSON document | Bit layouts are harder to migrate |
| One extremely write-heavy field on Redis Cluster | Partition load by business design | A single key still maps to one slot |

If the problem is just a simple counter, using:

```java
redis.opsForValue().increment("views:article:42");
```

can be vastly clearer than designing a `u16` at offset 0 and handling overflows. Choose Bitfield only when packing many small numbers genuinely justifies the schema design cost.

## 25. Operational and Security Risks

### 25.1. Large Offsets Can Trigger Large Allocations

A field at a very distant bit offset forces Redis to extend the String up to the write region, even if all preceding bits are zero. Always validate input indexes and cap maximum sizes before building commands.

In addition, Redis Strings have maximum size limits imposed by server/protocol/driver; do not design huge numeric arrays assuming one key can grow without bound.

### 25.2. Hot Keys in Redis Cluster

A String holding hundreds of thousands of fields is still **one key in one slot**. If all requests write to the same key, the owning shard can become bottlenecked. Load can be distributed by partitioning by tenant, day, category, or a stable shard key when business rules permit.

### 25.3. Avoid Information Disclosure via Bit Positions

If users can guess `userId` or indexes and read from a shared bitmap containing other users' states, the API can inadvertently leak data. Redis key layouts must be paired with application-layer authorization, network isolation, and proper ACLs. Do not treat Bitfield as an encryption/security mechanism; it is merely **compact data encoding**.

### 25.4. Persistence and Failover

BITFIELD updates a String in Redis, yet durability across crashes/failovers depends on AOF/RDB, replication, sync policies, and storage infrastructure. Redis does not automatically turn a bit counter into a durable transaction log.

If counters carry business-critical value, establish auditing, replay, outbox, or another durable source of truth depending on RPO/RTO requirements.

### 25.5. Scripts, Transactions, and Schema Governance

When multiple services read/write the same layout, a single service changing a width or offset can logically corrupt the data. Place layout definitions and types in a shared library or data-owning service with schema versions and migration plans.

For incompatible changes, creating a new key version is safer than silently altering the schema of a key used by all running instances.

## 26. Common Pitfalls

**Mistaking `BITFIELD` for a separate Redis data type.** In reality, it operates on a byte-holding Redis String; `TYPE` remains `string`.

**Confusing offset with byte index.** Redis uses **bit offsets**; a `u8` at offset 16 starts at the third byte.

**Assuming `#3` always means bit offset 3.** `#3` is multiplied by the width of the accessed field; for `u8`, that is bit 24.

**Assuming `SET` returns the new value.** `SET` returns the **previous value**, whereas `INCRBY` returns the **new value**.

**Omitting an overflow policy.** The default is WRAP; incrementing a `u8` from 255 wraps back to 0, causing counter bugs.

**Using `SAT` and treating a max-value result as a successful increment.** Once saturated, SAT keeps returning the max; if you need to know when a write was rejected, use FAIL and inspect the result.

**Using `FAIL` and assuming all subcommands roll back.** No; FAIL rejects the overflowing subcommand, while other subcommands in the same BITFIELD may still execute.

**Using `u64` because Java has a 64-bit `long`.** Redis BITFIELD supports unsigned fields up to 63 bits; Java `long` is signed 64-bit.

**Using `StringRedisTemplate.opsForValue().get()` to read packed bytes.** The value might not be valid UTF-8; use `bitField` with the matching layout.

**Failing to validate indexes.** Huge offsets can force Redis to allocate huge byte regions, causing RAM spikes.

**Neglecting TTL management.** BITFIELD does not attach a TTL to a new String or individual fields; define an explicit retention policy.

**Keeping one oversized/hot key.** Compact packing does not remove slot, CPU, network, or contention limits.

**Letting multiple code paths write to the same key with different schemas.** Redis has no field-name/width metadata to catch layout mismatches; enforce a single owner and consistent versioning.

## 27. Hands-On Practice with `redis-cli`

Practice on a development Redis instance with `demo:` prefixed keys. Do not run delete commands on namespaces holding other application data.

### Step 1. Write Two 4-Bit Fields

```redis
DEL demo:lab:packed
BITFIELD demo:lab:packed SET u4 0 7 SET u4 4 12
BITFIELD demo:lab:packed GET u4 0 GET u4 4 GET u8 0
```

Expected:

```text
u4 #0 = 7
u4 #1 = 12
u8 #0 = 124 (0x7C)
```

Because:

```text
7  → 0111
12 → 1100

01111100 → 124
```

### Step 2. Compare Absolute Offset and `#index`

```redis
BITFIELD demo:lab:packed GET u4 4 GET u4 #1
```

Both read the second field with value 12.

### Step 3. Test WRAP, SAT, and FAIL

```redis
DEL demo:lab:overflow
BITFIELD demo:lab:overflow SET u4 0 15
BITFIELD demo:lab:overflow INCRBY u4 0 1
BITFIELD demo:lab:overflow GET u4 0
```

Default WRAP yields 0.

```redis
BITFIELD demo:lab:overflow SET u4 0 15
BITFIELD demo:lab:overflow OVERFLOW SAT INCRBY u4 0 1
BITFIELD demo:lab:overflow GET u4 0
```

SAT holds at 15.

```redis
BITFIELD demo:lab:overflow OVERFLOW FAIL INCRBY u4 0 1
BITFIELD demo:lab:overflow GET u4 0
```

FAIL returns nil for the increment, while GET still returns 15.

### Step 4. Signed Interpretation

```redis
DEL demo:lab:signed
BITFIELD demo:lab:signed SET u8 0 255
BITFIELD demo:lab:signed GET u8 0 GET i8 0
```

Returns 255 and -1 for the exact same bit sequence.

### Step 5. Observe Size and TTL

```redis
TYPE demo:lab:packed
STRLEN demo:lab:packed
MEMORY USAGE demo:lab:packed
EXPIRE demo:lab:packed 120
TTL demo:lab:packed
```

`STRLEN` shows the stored binary byte length, while `MEMORY USAGE` includes Redis object structural overhead. After the TTL expires, reading fields on the nonexistent key interprets missing bits as 0.

### Step 6. Clean Up Practice Data

```redis
UNLINK demo:lab:packed demo:lab:overflow demo:lab:signed
```

Delete only the demo keys just created. Do not use `FLUSHALL` to clean up an exercise if the Redis instance serves other workloads.

## 28. Technical Reference Documentation

- Redis Commands — `BITFIELD`: https://redis.io/docs/latest/commands/bitfield/
- Redis Commands — `BITFIELD_RO`: https://redis.io/docs/latest/commands/bitfield_ro/
- Redis Commands — `GETBIT`: https://redis.io/docs/latest/commands/getbit/
- Redis Commands — `SETBIT`: https://redis.io/docs/latest/commands/setbit/
- Spring Data Redis API — `ValueOperations.bitField(...)`: https://docs.spring.io/spring-data-redis/reference/api/java/org/springframework/data/redis/core/ValueOperations.html
- Spring Data Redis API — `BitFieldSubCommands`: https://docs.spring.io/spring-data-redis/reference/api/java/org/springframework/data/redis/connection/BitFieldSubCommands.html
- Spring Data Redis API — `BitFieldSubCommands.Offset`: https://docs.spring.io/spring-data-redis/reference/api/java/org/springframework/data/redis/connection/BitFieldSubCommands.Offset.html

API details may change across Redis server, Spring Data Redis, and driver versions; verify against the documentation of your actual version rather than blindly copying an example across all systems.

## Conclusion

`BITFIELD` lets you treat **a Redis String as a bit array holding multiple integer fields** of arbitrary widths. The `GET`, `SET`, and `INCRBY` subcommands read, write, and increment numeric fields by bit offset or `#index`, while `OVERFLOW WRAP|SAT|FAIL` dictates behavior when results exceed the representable range. With Spring Data Redis, you can use `StringRedisTemplate.opsForValue().bitField()` with `BitFieldSubCommands` to express those operations in Java.

Bitfield fits well when you need **many small integers, a stable layout, explicit index bounds, and compact storage**. To use it safely, you must define the bit/encoding schema, manage key-level TTL, control overflow, avoid huge offsets, account for Hot Keys/Redis Cluster, and handle retries/idempotency per business requirements. When flexibility and maintainability matter more than compactness, regular integer `String`s or Redis `Hash`es are usually simpler choices.
