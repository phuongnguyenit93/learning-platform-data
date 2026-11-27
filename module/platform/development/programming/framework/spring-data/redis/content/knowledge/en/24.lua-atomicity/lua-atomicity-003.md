# Passing Key Lists, Arguments, and Result Types When Running Lua in Spring Data Redis

## 1. Why Separate Keys, Arguments, and Results?

Spring Data Redis lets you run Lua scripts on Redis via `RedisTemplate.execute(RedisScript<T>, List<K>, Object...)`. This is a valuable tool when an operation must **conditionally read and then write data as an atomic operation on Redis**: for example, deleting a lock only if the token still matches, conditionally decrementing stock, incrementing a counter, or updating multiple keys under one rule.

To keep scripts easy to use and safe, distinguish three components:

- **Key list**: the Redis keys that the script will access, passed via Java's `keys` parameter and received in the Lua `KEYS` table.
- **Business argument list**: tokens, quantities, TTLs, expected states, etc., passed via Java's `args` and received in the Lua `ARGV` table.
- **Result**: the value the script `return`s, converted by Spring Data Redis into the Java type declared in `RedisScript<T>` and handled by the appropriate serializer.

Logic example: *delete a session lock key only if its current value matches the token provided by the caller*.

```lua
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
```

Meaning:

| Expression | Sample value | Role |
| --- | --- | --- |
| `KEYS[1]` | `lock:order:42` | Redis key name to read and potentially delete |
| `ARGV[1]` | `request-token-abc` | Value to compare against the key's content |
| `return 1` | `1` | One key was deleted |
| `return 0` | `0` | Key does not exist or token did not match |

`GET` and `DEL` execute inside a single script running on Redis. No other process interleaves between the two script commands, avoiding the race window of calling `GET` then `DEL` across two separate calls.

## 2. From Redis `EVAL` to `RedisTemplate.execute(...)`

Redis has the general syntax:

```redis
EVAL "return {KEYS[1], KEYS[2], ARGV[1], ARGV[2]}" 2 first:key second:key alpha beta
```

Structure:

```text
EVAL <script> <numkeys> <key1> ... <keyN> <arg1> ... <argM>
                       |-----------------| |---------------|
                              KEYS                  ARGV

Lua:
KEYS[1] = "first:key"
KEYS[2] = "second:key"
ARGV[1] = "alpha"
ARGV[2] = "beta"
```

In Redis CLI, `numkeys = 2` tells Redis that **the next two arguments are key names**, and the remaining arguments are regular parameters. The script does not need to declare `numkeys` again.

In Spring Data Redis:

```java
List<String> keys = List.of("first:key", "second:key");
List<?> result = redisTemplate.execute(
        script, keys, "alpha", "beta");
```

Spring automatically computes the key count from `keys.size()` and sends the corresponding command (usually preferring `EVALSHA` if cached, falling back when needed). Developers must preserve the **exact order** of keys and arguments expected by Lua.

Several important rules:

1. Lua uses **1-based** table indexing, so use `KEYS[1]` and `ARGV[1]`; never use `KEYS[0]` like a Java array.
2. Pass `keys` using `List.of(...)`; pass remaining arguments via `Object... args` in exact order.
3. `KEYS` contains **key names**, not key contents. Use `redis.call('GET', KEYS[1])` to read data.
4. `ARGV` contains **parameter values**, such as tokens, TTLs, or quantities; do not pass key names in `ARGV` and assemble key names inside Lua.
5. The number of keys and the number of arguments can differ; they are not positionally paired key/value entries.
6. Every value sent over the Redis protocol is serialized. Inside Lua, data read from `ARGV` is typically a string/byte string, even when Java passes numbers.

## 3. Defining a Script with `DefaultRedisScript<T>`

Spring Data Redis represents scripts through the `RedisScript<T>` interface. For custom scripts, the common class is `DefaultRedisScript<T>`.

Example using the "compare token then delete" script:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.data.redis.core.script.RedisScript;

@Configuration
public class RedisLuaConfiguration {

    @Bean
    public RedisScript<Boolean> compareAndDeleteScript() {
        DefaultRedisScript<Boolean> script = new DefaultRedisScript<>();

        script.setScriptText("""
                if redis.call('GET', KEYS[1]) == ARGV[1] then
                    return redis.call('DEL', KEYS[1])
                end
                return 0
                """);

        script.setResultType(Boolean.class);
        return script;
    }
}
```

We declare `Boolean.class` because the script returns Redis integer `1` on successful deletion and `0` when nothing is deleted; Spring Data Redis's executor can map those integer values to Boolean.

Using it in a service:

```java
import java.util.List;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.stereotype.Service;

@Service
public class LeaseTokenService {

    private final StringRedisTemplate redis;
    private final RedisScript<Boolean> compareAndDeleteScript;

    public LeaseTokenService(
            StringRedisTemplate redis,
            @Qualifier("compareAndDeleteScript")
            RedisScript<Boolean> compareAndDeleteScript) {
        this.redis = redis;
        this.compareAndDeleteScript = compareAndDeleteScript;
    }

    public boolean releaseIfOwner(String resourceId, String token) {
        if (resourceId == null ||
                !resourceId.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("Invalid resourceId");
        }
        if (token == null || token.isBlank()) {
            throw new IllegalArgumentException("Invalid token");
        }

        String key = "lock:resource:" + resourceId;

        Boolean removed = redis.execute(
                compareAndDeleteScript,
                List.of(key),
                token
        );

        return Boolean.TRUE.equals(removed);
    }
}
```

Here:

- `List.of(key)` is passed into `KEYS[1]`.
- `token` is passed into `ARGV[1]`.
- The script returns `1` or `0`; Java receives `Boolean.TRUE` or `Boolean.FALSE`.
- `Boolean.TRUE.equals(removed)` is also safe when the result is `null`, such as in queued command execution or when a response is not yet available.

This snippet demonstrates the **token-checked lock release step**, not a complete distributed lock algorithm. In real lock usage, you need a unique token per acquisition, a TTL, disconnect handling, and appropriate business constraints. Never allow another client to arbitrarily pass a system-wide shared token.

### Storing Scripts in Resources Instead of Inline

For longer scripts, create a file, for example `src/main/resources/scripts/compare-and-delete.lua`:

```lua
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
```

Corresponding bean:

```java
@Bean
public RedisScript<Boolean> compareAndDeleteScript() {
    DefaultRedisScript<Boolean> script = new DefaultRedisScript<>();
    script.setLocation(
            new ClassPathResource("scripts/compare-and-delete.lua"));
    script.setResultType(Boolean.class);
    return script;
}
```

Import `org.springframework.core.io.ClassPathResource`. Declare script beans once and reuse them; `DefaultRedisScript` computes and provides the SHA-1 of the script content for hash-based execution. Do not instantiate a new `DefaultRedisScript` on every request.

## 4. Rules for Passing the `KEYS` List

### 4.1. Pass the Exact Count and Order

Suppose a script reads available stock from the first key and writes reserved stock to the second key:

```text
KEYS[1] -> stock:{sku42}:available
KEYS[2] -> stock:{sku42}:reserved
ARGV[1] -> 3
```

Java:

```java
List<String> keys = List.of(
        "stock:{sku42}:available",
        "stock:{sku42}:reserved"
);

Long result = redis.execute(reserveScript, keys, "3");
```

Swapping the two keys could make the script decrement the wrong counter. Developers should name variables clearly and document the KEYS/ARGV contract at the top of the script:

```lua
-- KEYS[1]: stock available
-- KEYS[2]: stock reserved
-- ARGV[1]: number of units to reserve
```

A helpful practice is constructing the `keys` list in one dedicated Java location instead of duplicating list assembly across multiple services.

### 4.2. Every Key Accessed by the Script Must Be Declared in `KEYS`

Redis requires key names accessed by a script to be passed in the key arguments list. Avoid writing:

```lua
-- Avoid: key name constructed from ARGV
local key = "stock:" .. ARGV[1]
return redis.call('GET', key)
```

Proper approach:

```lua
-- Java passes "stock:sku42" in KEYS[1]
return redis.call('GET', KEYS[1])
```

This rule matters because Redis Cluster must identify the node/hash slot holding the keys; Redis also needs to separate keys from ordinary data in command metadata and related policies.

### 4.3. Key Serializer

With `StringRedisTemplate`, key names are encoded using `StringRedisSerializer`, so Lua sees literal text key names like `stock:sku42`.

With a `RedisTemplate<K,V>` using a different serializer, a key string may be encoded into bytes that do not match the human-readable name shown in `redis-cli`. Scripts operate on **raw Redis key bytes**, not on how Java displays the key object.

If data was stored with key serializer A while the script passes keys with serializer B, Lua may access an entirely different key even though the Java strings look identical. Keep key serialization consistent between data writes and script invocations.

## 5. Redis Cluster: Keys Must Reside in the Same Hash Slot

When a script operates on multiple keys in Redis Cluster, those keys must reside in the **same hash slot**. Two different key names are typically distributed to different slots, and a multi-key command may fail with `CROSSSLOT`.

Example at risk of landing in different slots:

```text
stock:sku42:available
stock:sku42:reserved
```

They may land in two different slots because the entire key name is hashed. The deliberate way to colocate slots is using a **hash tag** enclosed in curly braces:

```text
stock:{sku42}:available
stock:{sku42}:reserved
       ^^^^^
       same portion used to compute the slot
```

Both keys share the tag `sku42` and thus the same hash slot. Never use one global hash tag like `{all}` for every product in a large system, as that concentrates load onto a single slot. Choose a tag representing the natural unit of atomic operations: product ID, order ID, or tenant ID depending on the use case.

If running standalone Redis, keys do not face cluster slot restrictions, yet clean key naming still makes future migration easier.

**Never pass a user-supplied list of `KEYS` directly** if the script can write or delete. Construct key names from validated identifiers and fixed prefixes in the application, and configure ACLs as appropriate.

## 6. Passing `ARGV` and Type Conversion in Lua

`ARGV` holds ordinary parameters as bytes/strings after Spring serialization. Lua has no native Java `Long` or `BigDecimal` types:

```lua
local quantity = tonumber(ARGV[1])
local ttlSeconds = tonumber(ARGV[2])
local status = ARGV[3]
```

Java side example:

```java
redis.execute(
        someScript,
        List.of("order:{42}:state"),
        "3",        // ARGV[1]: quantity
        "120",      // ARGV[2]: ttl
        "PENDING"   // ARGV[3]: status
);
```

### Validate Inputs Before Writing

Never assume `ARGV[1]` is always valid:

```lua
local quantity = tonumber(ARGV[1])

if quantity == nil or quantity <= 0 or quantity % 1 ~= 0 then
    return redis.error_reply('ERR quantity must be a positive integer')
end
```

If an argument is missing, `tonumber(nil)` returns `nil`. If the string is non-numeric, `tonumber` also returns `nil`. Checking inside Lua protects the script even if Java-side validation was bypassed.

Note also that numbers in traditional Redis Lua scripting use double-precision floating point; very large integers can lose precision when converted via `tonumber`. For Redis signed 64-bit counters, prefer passing validated integer strings directly to `INCRBY`/`DECRBY` and avoiding large-number arithmetic inside Lua.

Do not pass arbitrary JDK-serialized objects into `ARGV` and then call `tonumber` or literal string comparisons; Lua will see serializer byte headers rather than the text a developer expects.

### ARGV Holds Values, Not Java Parameter Names

Spring sends arguments **positionally**. If Lua has:

```lua
local expected = ARGV[1]
local replacement = ARGV[2]
```

then calling:

```java
redis.execute(compareAndSetScript, List.of(key),
        replacement, expected);  // Wrong order
```

introduces a logic bug even though Java compiles cleanly. Expose a service method with clearly named parameters instead of calling raw scripts from many places.

## 7. Complete Example: Reserving Stock with Two Keys and One Argument

The script takes two same-slot keys: `available` and `reserved`, along with the quantity to reserve in `ARGV[1]`.

File `scripts/reserve-stock.lua`:

```lua
-- KEYS[1]: stock:{sku}:available
-- KEYS[2]: stock:{sku}:reserved
-- ARGV[1]: quantity, positive integer

local requested = tonumber(ARGV[1])
if requested == nil or requested <= 0 or requested % 1 ~= 0 then
    return redis.error_reply('ERR invalid quantity')
end

local availableRaw = redis.call('GET', KEYS[1])
if availableRaw == false then
    return 0
end

local available = tonumber(availableRaw)
if available == nil or available < requested then
    return 0
end

local reservedRaw = redis.call('GET', KEYS[2])
if reservedRaw ~= false and tonumber(reservedRaw) == nil then
    return redis.error_reply('ERR reserved value is not numeric')
end

redis.call('DECRBY', KEYS[1], ARGV[1])
redis.call('INCRBY', KEYS[2], ARGV[1])
return 1
```

Spring configuration:

```java
@Bean
public RedisScript<Long> reserveStockScript() {
    DefaultRedisScript<Long> script = new DefaultRedisScript<>();
    script.setLocation(
            new ClassPathResource("scripts/reserve-stock.lua"));
    script.setResultType(Long.class);
    return script;
}
```

Java service:

```java
@Service
public class StockReservationService {

    private final StringRedisTemplate redis;
    private final RedisScript<Long> reserveStockScript;

    public StockReservationService(
            StringRedisTemplate redis,
            @Qualifier("reserveStockScript")
            RedisScript<Long> reserveStockScript) {
        this.redis = redis;
        this.reserveStockScript = reserveStockScript;
    }

    public boolean reserve(String sku, long quantity) {
        if (sku == null || !sku.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("Invalid SKU");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }

        String tag = "{" + sku + "}";
        List<String> keys = List.of(
                "stock:" + tag + ":available",
                "stock:" + tag + ":reserved"
        );

        Long result = redis.execute(
                reserveStockScript, keys, Long.toString(quantity));

        return Long.valueOf(1L).equals(result);
    }
}
```

Result meaning: `1L` = took the reservation branch; `0L` = insufficient stock or missing available key. If the script raises a Redis error, Spring throws the corresponding exception. Never interpret every exception as "out of stock."

**Scope boundary of this example:** it ensures commands inside the script are not interleaved by other operations; it does **not** guarantee *full rollback* if one command fails after an earlier command wrote data. For instance, the reserved counter could overflow integer limits in `INCRBY` after `available` was already decremented by `DECRBY`. For critical inventory workloads, validate overflow bounds, key types, and required state **before writing**, and add an idempotency key and reconciliation process when commit outcomes are uncertain due to connection loss.

If you need to update stock across different slots, you cannot make a cross-slot script valid by altering Java code; redesign the partitioning/key schema or cross-node consistency mechanism.

## 8. Result Types `RedisScript<T>`: Long, Boolean, String, List, null

When declaring `DefaultRedisScript<T>`, `setResultType(...)` tells Spring how to interpret the value returned by Redis. Lua's return type and the serializer must align with that declaration.

| Lua `return` | Typical Redis reply | Java should declare | Example |
| --- | --- | --- | --- |
| `return 42` | Integer reply | `Long.class` | `Long count = ...` |
| `return 1` or `return 0` | Integer reply | `Boolean.class` when representing true/false | `Boolean success = ...` |
| `return "READY"` | Bulk string | `String.class` when using String serializer | `String value = ...` |
| `return {1, "OK"}` | Array reply | `List.class` | `List<?> parts = ...` |
| `return nil` or `return false` per Lua/RESP2 mapping | Null bulk reply | May receive `null` in Java | Must check for null |
| Script only produces side effects, no result needed | Ignore output | `setResultType(null)` | Still handle command errors |

Spring Data Redis does not support arbitrary Java classes directly as a result type; map responses to integers, booleans, arrays, or deserializable values. For complex objects, return a JSON string built in the script and parse it in Java.

### 8.1. Integer: Use `Long.class`

Lua:

```lua
return redis.call('INCR', KEYS[1])
```

Java:

```java
DefaultRedisScript<Long> script = new DefaultRedisScript<>();
script.setScriptText("return redis.call('INCR', KEYS[1])");
script.setResultType(Long.class);

Long count = stringRedisTemplate.execute(
        script,
        List.of("metrics:requests")
);
```

Redis integer replies map to `Long`. Do not declare `Integer.class` just because numbers are small: Spring Data Redis scripting APIs typically use `Long.class` for integer replies.

### 8.2. True/False Condition: Use `Boolean.class` and Return `1`/`0`

Lua:

```lua
if redis.call('EXISTS', KEYS[1]) == 1 then
    return 1
end
return 0
```

Java:

```java
DefaultRedisScript<Boolean> script = new DefaultRedisScript<>();
script.setScriptText("""
        return redis.call('EXISTS', KEYS[1]) == 1 and 1 or 0
        """);
script.setResultType(Boolean.class);

Boolean exists = stringRedisTemplate.execute(
        script, List.of("session:42"));
```

In Lua, `true` and `false` are not equivalent to integers `1` and `0` at the Redis reply level. Under Lua/RESP2 rules, `return true` converts to integer `1`, whereas `return false` converts to a null reply, easily confused with missing results. Returning explicit `1`/`0` ensures Java receives an unambiguous boolean.

### 8.3. String: Use the Matching Serializer

Lua:

```lua
return redis.call('GET', KEYS[1])
```

Java:

```java
DefaultRedisScript<String> script = new DefaultRedisScript<>();
script.setScriptText("return redis.call('GET', KEYS[1])");
script.setResultType(String.class);

String status = stringRedisTemplate.execute(
        script, List.of("order:42:status"));
```

When the key holds string data, `StringRedisTemplate` deserializes the bulk string to a Java `String`. If the key does not exist, Redis `GET` returns nil and Spring can return `null`; `null` does not necessarily mean the script failed.

If using `RedisTemplate<Object,Object>` with the default JDK serializer, a returned Lua string may not be valid serialized data for a Java object. Select or pass an explicit result serializer.

### 8.4. List: Use `List.class` and Inspect Element Types

Lua:

```lua
local exists = redis.call('EXISTS', KEYS[1])
local value = redis.call('GET', KEYS[1]) or ""
return { exists, value }
```

Java:

```java
DefaultRedisScript<List> script = new DefaultRedisScript<>();
script.setScriptText("""
        local exists = redis.call('EXISTS', KEYS[1])
        local value = redis.call('GET', KEYS[1]) or ""
        return { exists, value }
        """);
script.setResultType(List.class);

List<?> result = stringRedisTemplate.execute(
        script, List.of("order:42:status"));

if (result != null && result.size() == 2) {
    Long exists = (Long) result.get(0);
    String value = (String) result.get(1);
}
```

An array reply can mix Redis integers and bulk strings, so `List<?>` does not mean every element is a `String`. Element conversion—especially for nested arrays or custom serializers—must be agreed upon across the application.

An arbitrary map-like Lua table (e.g., `{status="OK", count=3}`) does not automatically turn into a Java `Map<String,Object>`. If you need a stable multi-field structure, return a JSON string and deserialize it explicitly in Java.

### 8.5. No Return Value

If Lua does not `return` or returns `nil`, Java may receive `null`. If a script only writes data and the application needs no output, `setResultType(null)` expresses that intent. However, **you cannot conclude from `null` that writes succeeded** in all cases, especially if the script is queued in a transaction or the connection dropped before the response arrived.

If business logic needs to distinguish "done," "not done," and "error," design explicit return codes or use appropriate status/error replies rather than collapsing everything to `null`.

## 9. Serializers: The Detail That Determines Whether Scripts Read Data Correctly

Execution involves multiple serialization points:

```text
Java keys       --key serializer--> Redis key bytes --> Lua KEYS
Java args       --args serializer-> Redis bytes     --> Lua ARGV
Lua return      --Redis reply------> result deserializer --> Java T
```

`StringRedisTemplate` is an intuitive choice when keys, arguments, and Redis values are all strings. By contrast, `RedisTemplate<String, SomeClass>` may use JSON, JDK serialization, or a custom format for values; in that case Lua will not necessarily read values as the expected plain strings.

Comparison script example:

```lua
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return 1
end
return 0
```

If the key holds a value encoded via JDK serialization, `GET` returns serialized object bytes; `ARGV[1]` as UTF-8 text will not match even if the logical Java values look identical. Align value formats from the start.

### Explicitly Specifying Serializers for Arguments and Results

`RedisTemplate` provides the overload:

```java
<T> T execute(
        RedisScript<T> script,
        RedisSerializer<?> argsSerializer,
        RedisSerializer<T> resultSerializer,
        List<K> keys,
        Object... args);
```

Example of a script returning String and accepting String arguments:

```java
RedisSerializer<String> text = new StringRedisSerializer();

String result = redisTemplate.execute(
        stringResultScript,
        text,                   // serializer for ARGV
        text,                   // serializer for bulk-string result
        List.of("profile:42"),
        "expected-value"
);
```

Important distinction: the overload above lets you choose serializers for **arguments and result**; key names are still serialized by **the template's key serializer**. If you are using a `RedisTemplate` with an unsuitable key serializer, do not expect changing `argsSerializer` alone to fix key lookups.

For scripts returning integer `Long` or boolean `Boolean`, the Redis response is mapped according to `RedisScript.getResultType()`; the result serializer mainly applies to bulk strings and complex values.

## 10. Atomicity, Script Errors, and Retries

Redis runs a script's commands contiguously with respect to other pending commands on the same Redis instance/node, so combining "check + write" in one script avoids races between two client calls. However:

- **Atomicity against interleaving does not mean automatic rollback.** If a script writes one key and the next command errors, Redis does not automatically undo prior effects.
- Long scripts or large loops can block other Redis commands; keep logic short, limit operations, and avoid scanning the entire keyspace with `KEYS`.
- All Redis keys accessed by a script must pass through `KEYS`; do not dynamically construct keys from `ARGV` or from data read inside Redis.
- Lua scripts with syntax errors or invalid commands return errors to the client. Spring Data Redis normally translates them into exceptions under `DataAccessException`; never turn every error into a "false" outcome.
- If a script ran on Redis but the connection dropped before Java received the response, the application cannot be sure of the result. Retrying without idempotency can duplicate side effects, especially in scripts using `INCR`, balance transfers, or stock decrements.
- Across multiple Redis nodes, atomicity applies only on the node/slot executing the script, not as a distributed transaction across slots.

When using scripts for critical updates, define a controlled **operation ID/idempotency token** for retries. Specific implementations must also account for token TTL and keeping keys in the same hash slot under Redis Cluster.

### `EVALSHA` and the Script Cache

When a `RedisScript` is reused, Spring Data Redis normally tries `EVALSHA` to avoid resending the full script source on every call. If Redis does not yet have that SHA, the executor can fall back to `EVAL` to load and run the script.

This is a transport and caching optimization; **it does not alter the `KEYS`, `ARGV`, or result type contract**. The script cache can become empty after restarts, `SCRIPT FLUSH`, or routing to another cluster node; applications must never assume the SHA is always present.

## 11. Script Operations and Spring Transactions

A call to `redisTemplate.execute(script, keys, args)` may appear inside a `@Transactional` service. If that `RedisTemplate` is participating in a Spring-managed Redis transaction, the command may be queued inside `MULTI` until `EXEC`, rather than returning its final business value immediately at the call site.

Therefore:

- If you need **the script's return value immediately to branch logic**, know for certain whether the current template/connection is inside a transaction queue.
- An atomic script executed directly on Redis usually does not need to be wrapped in `MULTI/EXEC` just to prevent commands **inside that script** from interleaving.
- Never treat a script as part of an atomic rollback with SQL merely because it sits inside `@Transactional`. When two resources participate, design cross-system consistency and error handling separately.
- If the caller sees `null`, determine whether it came from a script nil reply, a serializer issue, or a queued command; do not guess from `null` alone.

## 12. Controlled Practice: From Redis CLI Commands to Java

Use only a test Redis instance or a namespace owned by your team; never touch production business keys.

### Exercise A — One Key, One Argument, Returning Boolean

Create a key:

```redis
SET demo:lua:lease token-123 EX 60
```

Run the script:

```redis
EVAL "if redis.call('GET',KEYS[1]) == ARGV[1] then return redis.call('DEL',KEYS[1]) end return 0" 1 demo:lua:lease token-123
```

First call is expected to return `(integer) 1`, deleting the key. Running the same script again returns `0`. In Spring, use `RedisScript<Boolean>` with `List.of("demo:lua:lease")` and argument `"token-123"` to get `true`/`false` accordingly.

### Exercise B — Two Keys, One Argument, Returning Integer

Initialize test data:

```redis
SET stock:{demo1}:available 10
SET stock:{demo1}:reserved 2
```

Call the reservation script from Section 7 with:

```text
KEYS[1] = stock:{demo1}:available
KEYS[2] = stock:{demo1}:reserved
ARGV[1] = "3"
```

On success, the script returns `1`; `available` becomes 7 and `reserved` becomes 5. If the request exceeds remaining stock, the script returns `0` and skips the write branch. Under Redis Cluster, both keys share tag `{demo1}` so they land in the same slot.

### Exercise C — Receiving a String or List

Store:

```redis
SET demo:lua:status READY
```

Use the script `return redis.call('GET', KEYS[1])` with `StringRedisTemplate` and `RedisScript<String>`. The expected Java value is `"READY"`. Then change the script to:

```lua
return { redis.call('EXISTS', KEYS[1]), redis.call('GET', KEYS[1]) }
```

Use `RedisScript<List>` and observe that the first element is an integer (typically `Long`) and the second element is a String produced by the result serializer. Do not cast the whole list to `List<String>`.

### Exercise D — Swapping the Order of Keys and Args

Try swapping `List.of(key1, key2)` to `List.of(key2, key1)` in a test environment to see why positional contracts matter. Never run this experiment against real counters because the script performs writes.

## 13. Common Errors and Diagnostic Guide

| Symptom | Likely cause | Resolution |
| --- | --- | --- |
| `ERR wrong number of arguments` or Lua accesses `nil` | Missing `KEYS[n]`/`ARGV[n]`, wrong key count, or wrong argument order. | Document the contract at the top of the script; verify `keys.size()` and `args`. |
| Script does not see a key Java just wrote | Mismatched key serializer, wrong keyspace, or different Redis database. | Check key bytes, connection, namespace, and serializers. |
| `CROSSSLOT Keys in request don't hash to the same slot` | Script accesses multiple keys in different hash slots. | Design a shared hash tag per transaction unit or change the schema. |
| `ClassCastException` when reading result | `getResultType()` or `List` element types differ from assumptions. | Pick `Long`/`Boolean`/`String`/`List` matching the reply; handle element types. |
| Bulk string deserialization failure | Unsuitable result serializer (e.g., JDK serializer on Lua text). | Use `StringRedisSerializer` or matching serializer; configure explicitly. |
| Java receives `null` | Script returned nil, command is queued, or reply handling failed. | Check execution path, inspect logs/errors, and review return contract. |
| `NOPERM` | Redis user lacks `EVAL`/`EVALSHA` or inner command/key permissions. | Grant least-privilege permissions for required commands and keys; inspect ACLs. |
| Redis latency spikes on script calls | Script does too much work or runs unbounded loops. | Bound key counts, simplify logic, and measure in test environments. |
| Retries increment a counter twice | Script ran but response was lost; caller retried. | Use an operation ID and proper idempotency. |
| Numeric mismatch on very large integers | Lua `tonumber` or floating-point arithmetic loses precision. | Bound value ranges, use Redis integer commands, and guard against overflow. |

## 14. Principles for Maintainable Script Design

1. Define the contract at the top of the Lua file: `KEYS[1..n]`, `ARGV[1..m]`, valid result codes, and allowed error cases.
2. Use `KEYS` for **every accessed Redis key**; use `ARGV` for **all parameter values**. Never interpolate untrusted input directly into script source.
3. Bound and validate identifiers in Java before constructing keys; validate business values in Lua before writing.
4. Choose `StringRedisTemplate` when data is stored as strings; when using other serializers, document encoding for keys/args/results explicitly.
5. Ensure all keys in a multi-key script share the same slot on Redis Cluster.
6. Return small, explicit results: `Long` for numbers, `Boolean` for 1/0, `String` for text, `List` for tuples.
7. Design for realistic errors and recovery: Redis scripts do not automatically roll back commands that succeeded before an error.
8. Declare one reusable `RedisScript<T>` bean per script, placing Lua in resource files when content grows.
9. For sensitive mutations, implement retry idempotency, failure metrics, and minimal logging (never log secret tokens).
10. Verify serializers, Lua reply types, Redis Cluster slots, and command preconditions before going to production.

## 15. Self-Check Questions

1. When calling `redisTemplate.execute(script, List.of("a", "b"), "x", "y")`, what are `KEYS[2]` and `ARGV[1]`?
2. Why should a Redis key name be passed through `KEYS` instead of `ARGV`, especially in Redis Cluster?
3. When Lua returns integer `1`/`0`, in which cases should you declare `RedisScript<Boolean>` vs. `RedisScript<Long>`?
4. Why shouldn't a script returning `{1, "OK"}` be cast directly to `List<String>`?
5. If Java writes a Redis value using JDK serializer while Lua compares against UTF-8 text, what logic bug occurs?
6. Does a script that runs atomically with respect to interleaving automatically roll back prior succeeded commands if the final command fails?
7. How must a client handle retries after losing connection while executing an `INCR` script to avoid incrementing twice?
8. Inside a Spring-managed Redis transaction, why might `execute(...)` not return the final result immediately?

**Remember:** `RedisTemplate.execute(...)` bridges **Lua's `KEYS`/`ARGV`/`return` contract** with **Java's `List<K>`/`Object... args`/`RedisScript<T>`**. Redis Lua atomicity is fully meaningful only when the key list is accurate, arguments are serialized consistently, the result type matches, and cluster, error, and retry constraints are explicitly designed.

## References

- [Spring Data Redis — Scripting](https://docs.spring.io/spring-data/redis/reference/redis/scripting.html): `RedisScript`, `DefaultRedisScript`, usage of `RedisTemplate.execute(...)`, and result types.
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html): serializers, Redis operations, and callbacks.
- [Redis — Scripting with Lua](https://redis.io/docs/latest/develop/programmability/eval-intro/): script execution and `KEYS`/`ARGV` rules.
- [Redis — EVAL](https://redis.io/docs/latest/commands/eval/): `numkeys` syntax and key arguments.
- [Redis — Lua API](https://redis.io/docs/latest/develop/programmability/lua-api/): `redis.call`, `redis.pcall`, and Lua/Redis type conversions.
- [Redis — Redis Cluster Specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/): hash slots, hash tags, and multi-key command constraints.
