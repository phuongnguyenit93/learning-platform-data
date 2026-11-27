# Parameter Serialization and Script Result Deserialization in Spring Data Redis

## 1. The Core Issue: In What Form Do Java Objects Enter Lua?

Redis Lua scripts are commonly invoked from Java using `RedisTemplate.execute(...)`, `StringRedisTemplate.execute(...)`, or `RedisScript`. A common misconception is thinking Lua receives Java objects directly — **it does not**. Spring Data Redis must convert keys and arguments into **byte arrays** before sending `EVAL`/`EVALSHA`. When Redis returns a result, Spring Data Redis must interpret the Redis reply type and optionally deserialize the payload back into a Java type.

Basic flow:

```text
Java:
  RedisScript<T>
  List<K> keys
  Object... args
       |
       | Spring Data Redis serialization
       v
Redis request:
  EVALSHA <sha> <numkeys> <key-bytes>... <arg-bytes>...
       |
       | Redis passes bytes to the script
       v
Lua:
  KEYS[1], KEYS[2], ...
  ARGV[1], ARGV[2], ...
       |
       | Script executes redis.call(...)
       v
Redis reply:
  integer / bulk string / array / nil / error / ...
       |
       | RedisScript result type + result serializer
       v
Java:
  Long / Boolean / String / List / null / ...
```

This lesson aims to make clear **which side is responsible for data conversion**, how to choose appropriate serializers, and how to design stable data contracts between Java and Lua.

After this lesson, you will be able to:

- Distinguish `KEYS` from `ARGV`, both in purpose and in the serializer used.
- Understand why `StringRedisTemplate` is often the simplest choice for passing numeric and string arguments into Lua.
- Declare `RedisScript<T>` with an appropriate return type.
- Read `Long`, `Boolean`, `String`, `List`, or `null` results and recognize when JSON is warranted.
- Use `RedisTemplate.execute` overloads to specify argument and result serializers.
- Spot issues caused by `JdkSerializationRedisSerializer`, JSON serializers, numeric types, and binary data.
- Design scripts that are resilient to invalid inputs, unexpected results, and Redis Cluster constraints.

## 2. Understanding KEYS, ARGV, and Results at the Redis Level

A Lua script is invoked by Redis using a structure equivalent to:

```redis
EVAL "<lua script>" <number-of-keys> <key1> ... <keyN> <arg1> ... <argM>
```

Or when the script is already identified by SHA:

```redis
EVALSHA <sha1> <number-of-keys> <key1> ... <keyN> <arg1> ... <argM>
```

Inside the script:

- `KEYS[1]`, `KEYS[2]`, ... hold the Redis key names explicitly declared in the call.
- `ARGV[1]`, `ARGV[2]`, ... hold business parameters: quantities, statuses, request IDs, payloads, etc.
- Lua indexes arrays starting at **1**, unlike Java's 0-based indexing.
- Every `KEYS[i]` and `ARGV[i]` arriving in Lua is fundamentally a byte string. Redis has no awareness that it originally came from a `BigDecimal`, enum, or Java DTO.

Example from Redis CLI:

```redis
EVAL "return {KEYS[1], ARGV[1], ARGV[2]}" 1 demo:counter 5 hello
```

Meaning:

```text
KEYS[1] = "demo:counter"
ARGV[1] = "5"
ARGV[2] = "hello"
```

Lua does not automatically recognize `ARGV[1]` as an integer. If arithmetic is needed, the script must convert it:

```lua
local amount = tonumber(ARGV[1])
```

If the string cannot be parsed as a number, `tonumber` returns `nil` for invalid conversions. Using that value in arithmetic or a Redis command can raise an error.

### 2.1. Why Separate KEYS and ARGV?

This separation serves several purposes:

1. **Routing:** in Redis Cluster, clients and servers use declared Redis keys to apply hash-slot rules.
2. **Script contract:** the script knows which parameters are key names to access data and which are simply business values.
3. **Control:** the same script can run across different keys and values without altering Lua source code.
4. **Maintainability:** instead of concatenating key names into Lua source, the application passes keys via a dedicated list.

Never put Redis key names inside `ARGV` and assemble keys dynamically in Lua to dodge Cluster constraints. Keys accessed by a script must be properly declared and satisfy same-hash-slot requirements.

## 3. Which Serializers Does RedisTemplate Use When Executing Lua?

With the standard overload:

```java
<T> T execute(RedisScript<T> script, List<K> keys, Object... args);
```

`RedisTemplate` handles converting inputs and outputs.

Under `DefaultScriptExecutor`'s default behavior in Spring Data Redis:

- **Keys** use the template's **key serializer**.
- **`ARGV` arguments** use the template's **value serializer**.
- **Byte-based results** use the template's **value serializer** for deserialization when the script's return type requires it.
- Certain return types such as `Long` and `Boolean` are mapped from the Redis reply type directly, rather than passing through a string/JSON serializer to decode numbers.
- The expected Java type is specified via `RedisScript<T>.getResultType()`.

Consequently, **the serializers configured on the template directly affect what data Lua sees**, not merely regular `GET`/`SET` commands.

Quick reference table:

| Component | Java data | Default conversion |
|---|---|---|
| `keys` list | `List<String>` or `List<K>` | `template.getKeySerializer()` |
| `args` elements | `Object...` | `template.getValueSerializer()` |
| Bulk string result | Bytes from Redis | `template.getValueSerializer()` when using the default overload |
| Integer result | Redis integer reply | Typically mapped directly to `Long` when result type is `Long` |
| Boolean result | Appropriate reply type | Converted according to the `Boolean` type declared by `RedisScript` |
| Array result | Redis array reply | Elements are deserialized per the applicable result rules |
| No result | Redis nil or script returns no meaningful value | May be represented as `null` depending on reply and result type |

**Never assume every template uses UTF-8 strings.** `StringRedisTemplate` is preconfigured for strings; a `RedisTemplate<String, Object>` might use JDK serialization or JSON depending on bean configuration.

## 4. Why Is StringRedisTemplate Usually Easy to Use with Lua?

`StringRedisTemplate` uses string serializers for both keys and values; string data is typically UTF-8 encoded. This aligns naturally with scripts using `tonumber`, string comparisons, or `redis.call("GET", ...)`.

Example initializing a key:

```java
import org.springframework.data.redis.core.StringRedisTemplate;

String key = "stock:{sku-42}:available";
stringRedisTemplate.opsForValue().set(key, "20");
```

Script invocation:

```java
Long result = stringRedisTemplate.execute(
    script,
    List.of(key),
    "3"
);
```

Logical data received by Lua:

```text
KEYS[1] = "stock:{sku-42}:available"
ARGV[1] = "3"
```

In Lua:

```lua
local quantity = tonumber(ARGV[1])
```

receives the number 3 if the argument truly is the string `"3"`.

### 4.1. Do Not Mistake `StringRedisTemplate` for Automatic Object Passing

If arguments include a DTO or `BigDecimal`, you must decide the **wire format**. `StringRedisTemplate` does not automatically know how to format arbitrary Java DTOs as JSON. Convert explicitly:

```java
String quantityText = Integer.toString(quantity);
String idempotencyToken = UUID.randomUUID().toString();

Long result = stringRedisTemplate.execute(
    script,
    List.of(redisKey),
    quantityText,
    idempotencyToken
);
```

If you need to pass a complex object, serialize it to JSON with a clear schema using Jackson or a codec understood by both sides.

## 5. Complete Example: Reserving Stock with a Lua Script

We have a key holding the remaining stock count:

```text
stock:{sku-42}:available = "20"
```

Goals:

- If the reservation request is invalid, modify nothing.
- If stock is insufficient, return code `0`.
- If reservation succeeds, subtract stock and return code `1`.
- Avoid two separate Java steps `GET` then `DECRBY` that other requests can interleave between.

### 5.1. The Lua File

Create `src/main/resources/scripts/reserve-stock.lua`:

```lua
-- KEYS[1] : stock key (Redis String containing an integer)
-- ARGV[1] : quantity to reserve, as a decimal string

local requested = tonumber(ARGV[1])

if requested == nil
   or requested <= 0
   or requested ~= math.floor(requested) then
    return -2
end

local rawAvailable = redis.call('GET', KEYS[1])

if rawAvailable == false then
    return -1
end

local available = tonumber(rawAvailable)

if available == nil then
    return -3
end

if available < requested then
    return 0
end

redis.call('DECRBY', KEYS[1], requested)
return 1
```

Agreed result codes:

| Lua result | Meaning |
|---:|---|
| `1` | Reservation succeeded |
| `0` | Insufficient stock |
| `-1` | Key does not exist |
| `-2` | Invalid quantity argument |
| `-3` | Stock data is not a valid numeric format |

Standardize the stock key format as an **integer string**. The snippet uses Lua's `tonumber`, suitable for ordinary quantities; for very large 64-bit integers, account for Lua numeric precision limits and Redis command integer constraints.

### 5.2. Defining RedisScript<Long>

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.data.redis.core.script.RedisScript;

@Configuration
public class RedisScriptConfiguration {

    @Bean
    RedisScript<Long> reserveStockScript() {
        return RedisScript.of(
            new ClassPathResource("scripts/reserve-stock.lua"),
            Long.class
        );
    }
}
```

Here `Long.class` is the **Java result type**, not the serializer for `ARGV`. Spring Data Redis knows the script is expected to return a Redis integer reply and converts it to `Long`.

Placing scripts in separate resource files makes editing, reading, and reusing much cleaner than concatenating long Java strings.

### 5.3. Calling the Script from a Service

```java
import java.util.List;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.stereotype.Service;

@Service
public class StockReservationService {

    private final StringRedisTemplate redis;
    private final RedisScript<Long> reserveStockScript;

    public StockReservationService(
            StringRedisTemplate redis,
            RedisScript<Long> reserveStockScript) {
        this.redis = redis;
        this.reserveStockScript = reserveStockScript;
    }

    public long reserve(String productId, long quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        // productId must be validated to preserve the hash tag format.
        String key = "stock:{" + productId + "}:available";

        Long code = redis.execute(
            reserveStockScript,
            List.of(key),
            Long.toString(quantity)
        );

        if (code == null) {
            throw new IllegalStateException(
                "Lua returned no result for reservation"
            );
        }

        return code;
    }
}
```

Before testing:

```java
stringRedisTemplate.opsForValue()
    .set("stock:{sku-42}:available", "20");
```

Example:

```java
long result = stockReservationService.reserve("sku-42", 3);
// result = 1
```

Afterwards:

```redis
GET stock:{sku-42}:available
```

The expected value is `17` assuming no other operations ran concurrently.

Connection across layers:

```text
Java long quantity=3
  |
  | Long.toString(quantity)
  v
String "3"
  |
  | StringRedisSerializer
  v
ARGV[1] = UTF-8 bytes of "3"
  |
  | Lua tonumber(ARGV[1])
  v
requested = 3
  |
  | Lua return 1
  v
Redis integer reply 1
  |
  | RedisScript<Long>
  v
Java Long 1
```

### 5.4. Assumptions That Must Be Clear

The example assumes the stock key is a Redis String holding a non-negative integer, data is not written with an incompatible binary serializer, and every command executes on the node serving the key. If a product involves multiple related keys in Redis Cluster, every key accessed by the script must share the same hash slot.

If you only need a simple `DECRBY`, the Redis command itself is already atomic. The script adds value here by combining the **stock sufficiency check** and the **quantity decrement** into a single step.

## 6. Mapping Lua Return Types to Java

A Redis script does not return a Java object directly. It returns a **Redis protocol reply**. Spring Data Redis uses the result type declared on `RedisScript<T>` to decide how to interpret it.

Common mappings in a RESP2 context:

| Lua returns | Typical Redis reply | Recommended Java/RedisScript type |
|---|---|---|
| `return 42` | Integer | `Long.class` |
| `return redis.call('INCRBY', key, 1)` | Integer | `Long.class` |
| `return redis.call('EXISTS', key)` | Integer `0` or `1` | `Long.class`, or `Boolean.class` when interpreted as a flag |
| `return 'READY'` | Bulk string | `String.class` with string serializer |
| `return redis.call('GET', key)` | Bulk string or nil | `String.class`, check for `null` |
| `return {ARGV[1], ARGV[2]}` | Array | `List.class` |
| `return false` under Lua/RESP2 rules | Nil/null reply | Handle `null` appropriately |
| `return redis.status_reply('OK')` | Status reply | Interpret according to reply and client API |
| Script returns an error via `redis.error_reply(...)` | Error reply | Client-side exception, not a normal result DTO |

**Note on RESP3:** Redis introduces additional reply types and conversion rules between Lua and RESP3, though exact Spring Data Redis behavior depends on framework and driver versions. This guide focuses on common types for broad compatibility.

### 6.1. RedisScript<Long>

```java
DefaultRedisScript<Long> script = new DefaultRedisScript<>();
script.setScriptText("return 15");
script.setResultType(Long.class);

Long value = stringRedisTemplate.execute(script, List.of());
```

Expected result is `15L`.

For integer replies, conversion uses the Redis reply type directly and normally **bypasses JSON/String result serializers**.

### 6.2. RedisScript<Boolean>

```java
DefaultRedisScript<Boolean> script = new DefaultRedisScript<>();
script.setScriptText("return redis.call('EXISTS', KEYS[1])");
script.setResultType(Boolean.class);

Boolean exists = stringRedisTemplate.execute(
    script,
    List.of("demo:flag")
);
```

`EXISTS` returns integer `0` or `1`. Converting to `Boolean` works well for `true`/`false` logic, but if you need to preserve status codes like `-1`, `0`, `1`, use `Long` to avoid losing information.

Do not invent multiple distinct numeric codes and cram them into `Boolean`: a boolean expresses only two states.

### 6.3. RedisScript<String>

```java
DefaultRedisScript<String> script = new DefaultRedisScript<>();
script.setScriptText("return ARGV[1]");
script.setResultType(String.class);

String value = stringRedisTemplate.execute(
    script,
    List.of(),
    "hello"
);
```

`ARGV[1]` contains the bytes of `"hello"`; the script returns a bulk string and `StringRedisTemplate` decodes it to a Java `String`.

If you use a `RedisTemplate` with a JDK or JSON value serializer while the script returns the raw string `"hello"`, deserialization can misbehave or throw an error. **The reply format and result serializer must be compatible.**

### 6.4. Lua nil or Missing Data

```java
DefaultRedisScript<String> script = new DefaultRedisScript<>();
script.setScriptText("return redis.call('GET', KEYS[1])");
script.setResultType(String.class);

String value = stringRedisTemplate.execute(
    script,
    List.of("missing:key")
);
```

If the key does not exist, the returned value can be `null`.

Never assume `null` always means "business object does not exist." A script might `return nil`, return Lua `false` under RESP2 rules, or be invoked with an unsuitable `resultType`. Define a clear **return status contract**; when multiple outcomes exist, use numeric codes or an explicit JSON status.

### 6.5. Scripts Needed Only for Side Effects

When a script only writes data and Java needs no business reply, you can set the result type to `null` as supported by the `RedisScript` API:

```java
DefaultRedisScript<Void> script = new DefaultRedisScript<>();
script.setScriptText(
    "redis.call('SET', KEYS[1], ARGV[1]); return nil"
);
script.setResultType(null);
```

This configuration states that the application expects no specific Java return value. Still handle exceptions when Redis errors occur; "no result" **does not mean "no errors."**

## 7. Numeric Types: The Most Common Trap

Lua can receive `"10"` and convert it via `tonumber`, yet you must distinguish strings, Java numbers, and Redis reply types.

### 7.1. Passing Numbers from Java

Use explicit decimal strings:

```java
String amount = Long.toString(quantity);

Long result = stringRedisTemplate.execute(
    script,
    List.of("counter:{tenant-7}:value"),
    amount
);
```

Lua:

```lua
local n = tonumber(ARGV[1])
if not n then
    return redis.error_reply('quantity must be numeric')
end
```

If the application uses a JSON serializer for arguments, the number `10` may be sent as a JSON string `"10"` or JSON bytes representing `10`, depending on Java type and serializer; the exact wire bytes must be verified. Thus, when a script expects a number, passing a numeric string with `StringRedisSerializer` is usually easier to reason about.

### 7.2. Lua Numbers and Redis Integers Are Not Identical

Many traditional Redis Lua environments use IEEE-754 double-precision numbers. Integers exceeding double precision risk losing digits when converted via `tonumber`. Meanwhile, Redis counters like `INCRBY`/`DECRBY` have their own integer bounds.

For data requiring exact precision such as currency:

- Do not arbitrarily use Lua floating-point arithmetic to add or subtract money.
- Prefer the smallest integer unit (`minor units`, e.g., cents or base currency units per business rules) or an exact arithmetic strategy.
- Watch out for large integers passed through `tonumber` and `math.floor`.
- Validate allowed value ranges in both Java and the script.
- When a Redis command like `INCRBY` already fits, prefer Redis's integer semantics directly.

### 7.3. Do Not Return Decimals via `return 3.75` Expecting a Java Double

Under common Lua/Redis behavior, a Lua number converted to a Redis integer reply truncates its fractional part. Nor is `RedisScript<Double>` a standard choice for an integer reply.

If you genuinely need to return a decimal number, a clear approach is **returning a preformatted string** and parsing it in Java:

```lua
return tostring(3.75)
```

Java:

```java
DefaultRedisScript<String> script = new DefaultRedisScript<>();
script.setScriptText("return tostring(3.75)");
script.setResultType(String.class);

String raw = stringRedisTemplate.execute(script, List.of());
BigDecimal value = new BigDecimal(raw);
```

This preserves the output representation, though it **does not make floating-point arithmetic inside Lua exact**. When monetary precision is required, design calculations and storage around integer quantities or appropriate arithmetic from the beginning.

## 8. Returning Multiple Values with a Redis Array

Lua can return an array so Java receives a list:

```lua
return {ARGV[1], ARGV[2], 'OK'}
```

In Java:

```java
import java.util.List;
import org.springframework.data.redis.core.script.DefaultRedisScript;

DefaultRedisScript<List> script = new DefaultRedisScript<>();
script.setScriptText("return {ARGV[1], ARGV[2], 'OK'}");
script.setResultType(List.class);

List<?> reply = stringRedisTemplate.execute(
    script,
    List.of(),
    "u-7",
    "42"
);
```

Logical data:

```text
reply[0] = "u-7"
reply[1] = "42"
reply[2] = "OK"
```

For bulk-string elements, the template's result serializer must read the bytes properly. If an array mixes integers, nulls, and nested arrays, Java element types can vary; never blindly cast every element to `String`.

For a script returning:

```lua
return {1, 'READY', false}
```

Java may receive a list containing numbers, strings, and nil/null elements per reply conversion rules. When designing an API contract, **do not let Java code depend on implicit casting quirks** of an undocumented mixed structure.

### 8.1. A Redis Array Differs from a JSON Array

```lua
return {'a', 'b', 'c'}
```

returns a **Redis array reply**.

```lua
return cjson.encode({'a', 'b', 'c'})
```

returns a **bulk string containing JSON text**.

These two replies differ at the protocol level. To read a JSON string, declare `String.class` and use Jackson. To read a Redis array, use `List.class` with an appropriate serializer/result type.

## 9. Returning a Complex Object: An Explicit JSON Contract

If Java needs a status object with multiple fields:

```text
success
remaining
reason
requestId
```

then a JSON document with a stable schema is usually easier to evolve than positional arrays or multiple numeric codes.

Lua:

```lua
local requested = tonumber(ARGV[1])
if requested == nil then
    return cjson.encode({
        success = false,
        reason = 'INVALID_QUANTITY'
    })
end

local remaining = tonumber(
    redis.call('GET', KEYS[1]) or '0'
)

if remaining < requested then
    return cjson.encode({
        success = false,
        reason = 'INSUFFICIENT_STOCK',
        remaining = remaining
    })
end

local newBalance = redis.call(
    'DECRBY', KEYS[1], requested
)

return cjson.encode({
    success = true,
    reason = 'OK',
    remaining = newBalance
})
```

Java DTO:

```java
public record StockScriptResult(
    boolean success,
    String reason,
    Long remaining
) {}
```

Declare the script returning `String`:

```java
DefaultRedisScript<String> jsonScript = new DefaultRedisScript<>();
jsonScript.setScriptText(luaSource);
jsonScript.setResultType(String.class);
```

Call and parse:

```java
String json = stringRedisTemplate.execute(
    jsonScript,
    List.of("stock:{sku-42}:available"),
    "3"
);

if (json == null) {
    throw new IllegalStateException("Missing JSON response");
}

StockScriptResult result =
    objectMapper.readValue(json, StockScriptResult.class);
```

This assumes `luaSource` is the script above, `objectMapper` is a configured Jackson `ObjectMapper`, and the project uses a Java version supporting `record`. On older Java versions, use a regular DTO class.

**Benefit:** Lua defines the JSON structure; Java explicitly controls deserialization. Adding new fields later can follow schema versioning/migration rules instead of relying on positional indices in a Redis array.

### 9.1. Do Not Use JSON for Every Case

If a script only needs to return `0`/`1`, `Long` is simpler. JSON adds encoding, decoding, payload, and error-handling overhead. Choose JSON when the output has multiple fields or requires an explicit schema.

### 9.2. Returning JSON and Reading with an Automatic JSON Serializer

A template using a JSON serializer can deserialize a JSON bulk string directly into an object, but doing so depends on the **result serializer**, type metadata, and mapper configuration. It is easier to control when:

1. Lua returns JSON text.
2. Spring Data Redis decodes the text using `StringRedisSerializer`.
3. Java uses `ObjectMapper` to parse it into a known DTO type.

This cleanly separates **Redis wire format** from **business data schema**.

## 10. Customizing Serializers for Arguments and Results

Beyond the standard overload, `RedisTemplate` provides overloads allowing you to specify serializers for **arguments** and **results** per script execution.

Common API signature:

```java
<T> T execute(
    RedisScript<T> script,
    RedisSerializer<?> argsSerializer,
    RedisSerializer<T> resultSerializer,
    List<K> keys,
    Object... args
);
```

Suppose the application's template has a non-String value serializer, yet a script expects `ARGV[1]` as text and returns text:

```java
import java.util.List;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.data.redis.serializer.RedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

RedisSerializer<String> utf8 = new StringRedisSerializer();

DefaultRedisScript<String> echo = new DefaultRedisScript<>();
echo.setScriptText("return ARGV[1]");
echo.setResultType(String.class);

String reply = redisTemplate.execute(
    echo,
    utf8,                  // args serializer
    utf8,                  // result serializer
    List.of("demo:echo"),  // key list
    "Hello Lua"
);
```

In this example `redisTemplate` is a properly configured `RedisTemplate<String, ?>` bean. Passing a key in the list that the script never uses should still be avoided; since the echo script only reads `ARGV`, `List.of()` can be passed instead.

Keep in mind: this overload customizes **args serializer** and **result serializer**. **The key serializer is still determined by the template**, so if keys must be plain Redis strings, configure `template.setKeySerializer(...)` accordingly or use `StringRedisTemplate`.

### 10.1. Case Where Result Type Is Long

With a `RedisScript<Long>`, Redis integer replies are converted directly according to the result type. Do not attempt to decode an integer reply as UTF-8 bytes or a JSON object.

Because the overload's Java generics require the result serializer to match `T`, when invoking a script returning `Long`, the simplest pattern is usually:

```java
Long count = stringRedisTemplate.execute(
    longScript,
    List.of("counter:{x}:value"),
    "1"
);
```

If arguments require a custom serializer, select an invocation style and serializer configuration matching the API contract of your Spring Data Redis version. Never create a `RedisSerializer<String>` and pretend it is a `RedisSerializer<Long>`.

### 10.2. When Are Custom Serializers Needed?

- The main template uses JDK serialization, while Lua expects text arguments.
- The template's value serializer uses JSON, while one script returns a raw Redis string.
- A script returns JSON with a defined schema and you want direct DTO deserialization.
- A script processes a binary payload with a custom format.
- You need to decouple the serializer for stored Redis values from the serializer for script arguments.

Specifying a different serializer at call time **does not change the format of data already stored in Redis**. A script reading a key still receives the raw bytes stored under that key. If the original value was written with JDK serialization, `GET` inside Lua still returns binary bytes even when `ARGV` uses UTF-8 strings.

## 11. Pitfalls When Using JdkSerializationRedisSerializer

A `RedisTemplate` may be configured to use `JdkSerializationRedisSerializer` for values. In that setup, a Java string `"10"` is not sent to Redis as the two character bytes `1`, `0`; it is wrapped in a Java serialization byte stream.

If the script runs:

```lua
local quantity = tonumber(ARGV[1])
```

then `ARGV[1]` is no longer the plain string `"10"`. `tonumber` conversion can fail.

Similarly, if the stock key was written through a JDK value serializer:

```java
redisTemplate.opsForValue().set("stock:available", 20L);
```

the stored Redis value is serialized binary data, not the text `"20"`. Lua:

```lua
local n = tonumber(redis.call('GET', KEYS[1]))
```

cannot deserialize a Java-serialized `Long` object on its own.

### 11.1. How to Fix It?

Pick one consistent strategy:

- For counters, balances, and integer stock: store values as **integer Redis Strings** using a string serializer and pass script arguments as matching strings.
- For DTOs: store JSON with an explicit schema and use `cjson.decode` in Lua only if the script truly needs to inspect fields.
- For binary data: process it in Lua only with format-aware logic, or keep business logic that requires decoding Java objects out of Lua.
- If the application needs both Java object serialization and Lua scripts, separate namespaces/keys cleanly to avoid format mismatches.

Avoid mixing `StringRedisTemplate` and a differently serialized `RedisTemplate` on **the same key** when the two sides do not share a wire format.

## 12. Using JSON for Parameters Passed into Lua

Suppose Java needs to pass a reservation request:

```json
{
  "quantity": 3,
  "requestId": "req-1001"
}
```

It can be serialized in Java to a JSON string:

```java
public record ReserveRequest(long quantity, String requestId) {}

ReserveRequest request = new ReserveRequest(3L, "req-1001");
String requestJson = objectMapper.writeValueAsString(request);

String responseJson = stringRedisTemplate.execute(
    jsonScript,
    List.of("stock:{sku-42}:available"),
    requestJson
);
```

Lua:

```lua
local ok, request = pcall(cjson.decode, ARGV[1])

if not ok or type(request) ~= 'table' then
    return cjson.encode({
        success = false,
        reason = 'INVALID_JSON'
    })
end

local quantity = tonumber(request.quantity)

if quantity == nil or quantity <= 0 then
    return cjson.encode({
        success = false,
        reason = 'INVALID_QUANTITY'
    })
end

-- Continue checking requestId and executing business logic.
return cjson.encode({
    success = true,
    acceptedQuantity = quantity
})
```

This illustrates a data contract. `pcall` catches JSON parse failures without crashing the script immediately. The application still needs to validate payload size, field types, value bounds, and idempotency per business requirements.

**Never assume every JSON number is an arbitrarily exact integer.** If values can exceed Lua's exact integer precision, pass and handle them in an appropriate format.

### 12.1. When to Split Multiple ARGV Instead of One JSON?

With two or three simple parameters:

```java
redis.execute(script, keys, "3", "req-1001", "CONFIRMED");
```

Lua:

```lua
local quantity = tonumber(ARGV[1])
local requestId = ARGV[2]
local state = ARGV[3]
```

this approach requires fewer encode/decode steps. However, you must document **the order and meaning of each ARGV**. When a script interface has many optional fields or evolves across versions, schema-based JSON can be easier to extend.

## 13. Return Types to Avoid Misinterpreting

### 13.1. Lua Booleans Differ from Java Booleans

Under RESP2 conversion rules from Lua to Redis replies, `true` can be represented as integer `1`, and `false` as a nil reply. Therefore, if the application needs an unambiguous boolean outcome, a readable pattern is:

```lua
return redis.call('EXISTS', KEYS[1])
```

and declaring `RedisScript<Boolean>` when appropriate. When you need to distinguish "no result," "business rejection," and "precondition failed," return **integer codes** or JSON containing a `status` field.

Never use `false` to mean both "does not exist" and "script returned no result"; that makes the Java contract ambiguous.

### 13.2. Lua Numbers Returned as Redis Integers Can Drop Fractions

```lua
return 2.5
```

is not a reliable way to return a Java `Double` of `2.5` in typical Redis Lua environments. Use string or JSON formatting when returning decimals, and control calculation precision explicitly.

### 13.3. A JSON String Does Not Automatically Become a Java DTO

```lua
return cjson.encode({code='OK', count=3})
```

returns a **JSON bulk string**, not a Java `Map<String, Object>`. To obtain a DTO, use an appropriate result serializer or receive `String` and parse with Jackson.

### 13.4. A Lua Array Does Not Automatically Become a Named-Field Object

```lua
return {'OK', '3'}
```

returns a positional array without field names like `code` or `count`. If an interface must remain stable as fields are added, consider JSON with named fields.

### 13.5. Redis nil and Exceptions Are Two Distinct Outcomes

If a script executes:

```lua
return nil
```

Java may receive `null`.

If a script executes:

```lua
return redis.error_reply('INVALID_INPUT')
```

the client receives a Redis error and Spring Data Redis translates it into an appropriate exception. Never treat a Redis error as a successful DTO with a `null` value.

## 14. Script Errors: Are Writes Before an Error Rolled Back?

Lua scripts execute atomically in the sense that no commands from other clients interleave while the script runs on Redis. However, **atomicity against interleaving does not mean rolling back all changes if a script errors partway through**.

Example:

```lua
redis.call('SET', KEYS[1], 'DONE')
redis.call('INCR', KEYS[2])  -- May fail if the value is not numeric.
return 1
```

If `SET` succeeds and `INCR` subsequently fails, effects performed before the error **are not undone**.

Design principles:

1. **Validate inputs before writing.** Ensure `ARGV` has the right count, types, and valid ranges.
2. **Validate required state before writing.** Check stock counts, order status, and versions.
3. **Minimize runtime errors after the first write.** Use controlled data structures and value types.
4. **Handle exceptions on the Java side.** Distinguish script errors, Redis errors, timeouts, and valid business outcomes.
5. **Design idempotency/recovery** for cases where a command may have executed while the client lost the response.

`redis.call` normally turns Redis errors into script errors; `redis.pcall` returns an error structure for Lua to inspect. Catching an error does not roll back prior writes. Avoid using `pcall` to hide an inconsistent state.

## 15. Ensuring Script Keys Work Correctly with Redis Cluster

When calling `RedisTemplate.execute` on Redis Cluster, the `keys` list is not merely a variable passed into Lua. Those keys determine how the client computes hash slots and whether multi-key operations are valid.

Same-slot example:

```java
List<String> keys = List.of(
    "order:{o-101}:state",
    "order:{o-101}:receipt"
);
```

Lua:

```lua
redis.call('SET', KEYS[1], ARGV[1])
redis.call('SET', KEYS[2], ARGV[2])
return 1
```

Both keys share the `{o-101}` tag, so they hash to the same slot. Conversely:

```java
List<String> keys = List.of(
    "order:{o-101}:state",
    "inventory:{sku-42}:available"
);
```

are not guaranteed to share a slot. A script cannot turn operations across two primaries into a distributed transaction.

### 15.1. Key Serializers Also Affect Hash Slots

In Redis Cluster, slots are calculated from the **actual key bytes**. If a template uses JDK serialization for keys, the wire key is not the readable string seen in Java. That can cause:

- Keys not matching keys created by `StringRedisTemplate`.
- Hash tags not being recognized as intended in the raw bytes.
- `CLUSTER KEYSLOT` on an operator-typed string yielding a different slot than the binary key sent by the application.

When working with Redis Cluster and Lua, use a consistent key serializer—typically `StringRedisSerializer`—especially when relying on `{` and `}` hash tags.

### 15.2. Never Hide Keys Inside JSON ARGV

If a script receives JSON:

```json
{"targetKey":"account:{other}:balance"}
```

and runs:

```lua
redis.call('SET', request.targetKey, '100')
```

the script has hidden a key name inside `ARGV`. That violates the explicit key-declaration model required by Cluster and can cause errors or invalid routing behavior. Redis keys accessed by a script must be passed via the `KEYS` list and satisfy slot constraints.

## 16. EVALSHA, Script Cache, and Serializers Are Separate Responsibilities

Spring Data Redis commonly uses `ScriptExecutor` to execute `RedisScript`. When a script is already in Redis's cache, the client can send `EVALSHA` using the source script's SHA; if Redis does not recognize the SHA, the executor can fall back to `EVAL`.

This **does not alter** how `KEYS` and `ARGV` are serialized or how results are deserialized:

```text
Script source + SHA:
    identifies which Lua program executes.

keySerializer:
    determines the bytes of KEYS.

argsSerializer:
    determines the bytes of ARGV.

RedisScript resultType + resultSerializer:
    determines how Java interprets the result.
```

You can reuse a `RedisScript` as a singleton bean instead of creating new sources per request. Reuse reduces resource/source overhead and works smoothly with the script cache, though it never replaces input validation or a clear result contract.

When a script changes, its SHA changes with the content; deploy changes uniformly across application instances so Java does not expect an old result format while the updated script returns a new schema.

## 17. Handling Errors at the Service Layer

A service calling Lua should distinguish:

- **Business outcomes:** e.g., `1` for success, `0` for insufficient stock.
- **Invalid results:** unexpected `null`, unknown codes, JSON missing required fields.
- **Script/serializer errors:** incompatible Redis reply or Lua raising an error.
- **Operational errors:** timeouts, connection drops, failovers.
- **Unknown outcomes due to timeout:** the script may have completed while Java never received the reply.

Code handling example:

```java
Long code = stringRedisTemplate.execute(
    reserveStockScript,
    List.of(key),
    Long.toString(quantity)
);

if (code == null) {
    throw new IllegalStateException("Script returned null");
}

switch (code.intValue()) {
    case 1:
        // Reservation succeeded.
        break;
    case 0:
        // Insufficient stock.
        break;
    case -1:
        // Key has not been initialized.
        break;
    case -2:
        // Invalid parameter.
        break;
    case -3:
        // Stock value is not numeric.
        break;
    default:
        throw new IllegalStateException(
            "Unexpected Lua status code: " + code
        );
}
```

This snippet illustrates classifying status codes; in a real application, map them to domain enums or outcomes rather than letting controllers interpret `-1`, `-2`, `-3`.

**Never blindly retry a script with side effects** after a timeout. If the script already decremented stock and the reply was lost, retrying could decrement it again. When durability against retries is needed, include an idempotency token in the contract and record token processing state atomically within the same key/slot.

### 17.1. Simple Idempotency Contract Example

In Redis Cluster, two keys can be colocated:

```text
stock:{sku-42}:available
stock:{sku-42}:request:req-1001
```

Lua checks whether the request was already processed; if not, it checks stock, decrements it, and stores the request outcome. Both keys share tag `{sku-42}`, allowing them to operate in the same slot when supported by the client.

However, you must define the TTL and uniqueness of the request ID. If the idempotency key expires too early, a replayed old request can be processed a second time. A time-bounded token store does not guarantee eternal idempotency.

## 18. Common Errors and Causes Table

| Symptom | Possible cause | Resolution |
|---|---|---|
| `tonumber(ARGV[1])` returns `nil` | `ARGV` holds Java serialization bytes, unexpected JSON string, or non-numeric text | Verify `argsSerializer`, pass decimal Strings, and validate |
| Java throws deserialization error when Lua returns `"OK"` | Template uses JDK/JSON value serializer while script returns plain text | Use `StringRedisSerializer` for result or change the return format |
| Java receives `null` when expecting String | Missing key, Lua `false`/`nil`, or mismatched result type | Clarify nil vs. error; validate the result |
| Java expects `Double` but gets another value | Lua numbers typically map to Redis integer replies in standard mode | Return string/JSON for decimals; parse explicitly in Java |
| Casting to `List<String>` throws `ClassCastException` | Redis array contains integers, nils, or nested replies | Use `List<?>`, inspect each element, or return JSON |
| `CROSSSLOT` on multi-key script | `KEYS` do not share the same slot | Use an aggregate hash tag and verify with `CLUSTER KEYSLOT` |
| Key exists in CLI but script GET cannot read it | Different key serializer or different Redis database | Check wire byte format and connection config |
| Lua `GET` sees strange bytes | Value was stored via JDK/JSON serializer contrary to expectations | Standardize value format; do not read binary as text |
| JSON parse error | Lua returned non-JSON status or payload broke schema | Set script result to `String`, validate/parse JSON with error handling |
| Script errors after partial writes | Runtime error after a write command | Validate upfront, keep scripts short, add recovery and idempotency |
| `NoScript`/script reload needed | Script SHA is not in the node's cache | Use `ScriptExecutor`/appropriate `EVAL` fallback; never assume shared cache across nodes |
| Timeout after `execute` | Redis/network/driver issue; execution state unknown | Use request IDs and verify state before retrying |

## 19. Practical Measurement and Observability

To see exactly what a script sends, test with sample keys and args in an isolated environment:

```redis
SET demo:lua:counter 10
EVAL "return {KEYS[1],ARGV[1],redis.call('GET',KEYS[1])}" 1 demo:lua:counter 3
```

Compare against a call from `StringRedisTemplate`. When both represent strings identically, behavior is far more predictable.

For production scripts:

1. Record metrics for success rates, business rejections, and operational errors.
2. Track latency, call volume, and payload size by group; never log sensitive data or raw serialized objects.
3. Bound `ARGV` sizes when receiving JSON payloads from APIs.
4. Keep scripts short without unbounded loops or huge return arrays.
5. Monitor memory and client output buffers if scripts return large JSON/arrays.
6. Account for schema versioning when changing result formats.

`EVAL` and `EVALSHA` execute on the Redis node; long scripts increase latency for other requests because Redis's atomic script execution prevents other commands from interleaving.

## 20. Choosing the Right Result Format

| Requirement | Recommended option | Reason |
|---|---|---|
| Increment counter, return new integer | `RedisScript<Long>` | Directly receives Redis integer |
| Existence check or yes/no condition | `RedisScript<Boolean>` or `Long` | Boolean for two states; Long for multiple codes |
| Return a simple string/status | `RedisScript<String>` with string serializer | Concise, easy to understand |
| Return a list of simple values | `RedisScript<List>` | Uses Redis array; inspect element types |
| Return a multi-field DTO | JSON text + `String` + Jackson | Named-field contract, easy to version |
| Return binary data with a custom codec | Explicitly chosen matching serializer | Controls raw bytes and schema |
| Script only writes, Java needs no value | Result type `null`/`Void` as appropriate | Avoids unnecessary deserialization; still handle errors |

No single serializer fits every data type. The sound approach is defining the **wire format contract** between Java and Lua first, then configuring templates, scripts, and result types to follow that same contract.

## 21. Guided Hands-On Exercises

### Exercise 1 — Identifying KEYS and ARGV

Run from Redis CLI:

```redis
EVAL "return {KEYS[1],ARGV[1],ARGV[2]}" 1 demo:lua:key 12 READY
```

Identify each returned element. Then write the equivalent `StringRedisTemplate.execute` call using `RedisScript<List>` and arguments `"12"`, `"READY"`.

### Exercise 2 — The Serializer Trap

Create two templates: one using `StringRedisSerializer` for values, and one using JDK serialization. Pass the string `"12"` to both with the script:

```lua
local n = tonumber(ARGV[1])
if not n then return -1 end
return n + 1
```

Explain why the input bytes differ, and how to use the `execute` overload with an explicit `argsSerializer` so the script receives numeric text. Never assume identical Java objects produce identical wire bytes.

### Exercise 3 — Handling JSON Results

Write Lua returning:

```lua
return cjson.encode({
    accepted = true,
    remaining = 7,
    reason = 'OK'
})
```

Use `RedisScript<String>` and `ObjectMapper` to parse into a Java DTO. Then change `reason` or add a `requestId` field to see why named-field JSON is easier to evolve than positional arrays.

### Exercise 4 — Nil Results vs. Errors

Write two scripts:

```lua
return redis.call('GET', KEYS[1])
```

and:

```lua
return redis.error_reply('INVALID_REQUEST')
```

Invoke both via `StringRedisTemplate` on a nonexistent key. Compare Java receiving `null` against the client throwing an exception.

### Exercise 5 — Cluster and Hash Tags

Declare two keys:

```text
order:{o-9}:state
order:{o-9}:receipt
```

Use `CLUSTER KEYSLOT` on Redis Cluster to confirm they share a slot. Write a script updating both keys via `KEYS[1]` and `KEYS[2]`, passing values in `ARGV[1]` and `ARGV[2]`. Explain why a third key tagged `{o-10}` cannot automatically participate in the same atomic execution.

### Exercise 6 — Safe Stock Reservation

Use the `reserve-stock.lua` script from Section 5:

1. Initialize stock to `"20"` via `StringRedisTemplate`.
2. Request 3 units, verify result `1` and remaining stock `17`.
3. Request 100 units, verify result `0` and stock unchanged.
4. Pass negative or non-numeric quantities as input.
5. Delete the stock key and invoke again, verifying code `-1`.
6. Describe what mechanism is needed to prevent double-decrementing when Java times out and retries the same request.

## 22. Key Takeaways

- `KEYS` and `ARGV` in Lua arrive as Redis byte data; Lua **never receives Java objects directly**.
- By default, Spring Data Redis uses the **key serializer for KEYS** and **value serializer for ARGV**, while result decoding depends on `RedisScript<T>` and the result serializer.
- `StringRedisTemplate` is straightforward when scripts expect string-encoded text and numbers; a `RedisTemplate` with JDK/JSON serializers can send completely different bytes.
- `RedisScript<Long>`/`Boolean` use dedicated Redis reply type conversions; bulk strings and arrays require matching serializers and result types.
- For complex DTOs, JSON text + Jackson provides an explicit contract. A Redis array and a JSON array are **two distinct reply forms**.
- Validate `tonumber(ARGV[i])`, especially against invalid inputs and values too large for exact Lua numeric representation.
- `execute` overloads can specify separate **args serializers** and **result serializers**; the key serializer remains governed by the template.
- Scripts are atomic against command interleaving, but **do not automatically roll back writes performed before a runtime error**.
- On Redis Cluster, keys accessed by a script must be declared and obey hash-slot constraints; `ARGV` parameters must never be used to bypass that requirement.
- Return contracts must clearly define `null`, status codes, JSON schemas, and exceptions; for operations with side effects, design idempotency before retrying after timeouts.

### Official References

- [Spring Data Redis — Scripting](https://docs.spring.io/spring-data/redis/reference/redis/scripting.html)
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Data Redis — Serializers](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/mapping.html)
- [Spring Data Redis — Redis Cluster](https://docs.spring.io/spring-data/redis/reference/redis/cluster.html)
- [Redis — EVAL](https://redis.io/docs/latest/commands/eval/)
- [Redis — EVALSHA](https://redis.io/docs/latest/commands/evalsha/)
- [Redis — Lua API and scripts](https://redis.io/docs/latest/develop/programmability/lua-api/)
- [Redis — Lua scripts introduction](https://redis.io/docs/latest/develop/programmability/eval-intro/)
- [Redis — Scripting and atomicity](https://redis.io/docs/latest/develop/programmability/eval-intro/)
