# Pipeline Result Serialization and Choosing the Right Serializer in Spring Data Redis

## 1. Why do pipelines return results differently from normal Redis commands?

Pipelining enables sending multiple Redis commands over the same connection without waiting for a response after each command. When an application needs to read or write hundreds of keys, reducing round-trip wait cycles between the application and Redis can significantly improve execution time.

However, pipelining also highlights an easily overlooked issue: **Redis communicates in bytes, whereas Java works with String, Long, Boolean, Map, and domain objects**. One pipeline can return several different response types. Spring Data Redis must decide which parts need decoding via `RedisSerializer` and which parts are already numeric or status values.

Example:

~~~text
Java application                       Redis
      |                                  |
      | SET user:1 "An"                   |
      | GET user:1                        |
      | INCR stats:reads                  |
      | HGETALL user:1:flags              |
      |--------------------------------->|
      |                                  | processes commands
      |<---------------------------------|
      | status, bytes, integer, map      |
      |                                  |
      v
Spring Data Redis decodes corresponding elements
      |
      v
List<Object> pipeline results
~~~

This is why you cannot apply a single `(String)` or `(User)` cast to every element in `List<Object>`.

Two key questions must be answered:

1. **Which serializer was used when writing the data into Redis?**
2. **When reading pipeline results, which serializer does Spring Data Redis use to convert bytes back into objects?**

If the two sides are incompatible, you may encounter garbled characters, deserialization errors, wrong types, or misinterpreted results.

## 2. Two distinct serialization directions

A normal Redis call has two directions:

~~~text
Java Application
  |
  | WRITE: Java value -> RedisSerializer.serialize(...) -> byte[]
  v
Redis
  |
  | READ: byte[] -> RedisSerializer.deserialize(...) -> Java value
  v
Java Application
~~~

With pipelining, commands are sent in a batch, while responses are collected and decoded after the pipeline ends.

**Sending side:** If commands are called through `RedisTemplate`'s high-level API, the template can serialize keys/values according to its configuration. If called directly through `RedisConnection` in a `RedisCallback`, low-level commands typically take `byte[]`; the callback author must produce the exact bytes matching the stored data convention.

**Reading side:** `RedisTemplate.executePipelined(...)` collects replies and performs deserialization when returning `List<Object>`, using the serializer configured on the template or the serializer supplied via the method overload.

A common mistake is passing `StringRedisSerializer` at the result-reading step when the data in Redis was written using JSON or JDK serialization. Redis does not store universal metadata indicating "this value uses serializer X" for Spring to auto-detect.

## 3. Serializers to distinguish on RedisTemplate

A `RedisTemplate<K, V>` has multiple serializers rather than just one:

| Serializer | Primary purpose | Example data |
| --- | --- | --- |
| `keySerializer` | Encodes Redis keys | `user:42` |
| `valueSerializer` | Encodes/decodes values of commands like `GET`/`SET` | Object payload or String |
| `hashKeySerializer` | Encodes fields in a Redis Hash | `name`, `status` |
| `hashValueSerializer` | Encodes field values in a Redis Hash | `An`, `ACTIVE` |
| `stringSerializer` | Supports String-related operations when used by the template | Key names, text-formatted strings |
| `defaultSerializer` | Default serializer when the template falls back to defaults | Depends on template configuration |

Example of intentional configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.GenericJackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class RedisSerializationConfig {

    @Bean
    public RedisTemplate<String, Object> jsonRedisTemplate(
            RedisConnectionFactory factory) {

        RedisTemplate<String, Object> template = new RedisTemplate<>();
        template.setConnectionFactory(factory);

        StringRedisSerializer strings = new StringRedisSerializer();
        GenericJackson2JsonRedisSerializer json =
            new GenericJackson2JsonRedisSerializer();

        template.setKeySerializer(strings);
        template.setHashKeySerializer(strings);
        template.setValueSerializer(json);
        template.setHashValueSerializer(json);

        template.afterPropertiesSet();
        return template;
    }
}
~~~

The configuration above chooses:

- UTF-8 strings for keys and hash fields, easy to inspect with `redis-cli`.
- JSON encoding for values and hash values using the chosen serializer.
- Pipelines reading values from matching Redis structures follow the template's deserialization rules.

**Choose serializers consistently with already written data.** If the same key name previously stored JDK serialization and later switches to JSON, changing the template configuration does not automatically migrate old data. A migration strategy or new namespace/version is needed.

## 4. Differences between StringRedisTemplate and RedisTemplate

`StringRedisTemplate` is the natural choice when both keys and values are strings:

~~~java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class SimpleCounterStore {

    private final StringRedisTemplate redis;

    public SimpleCounterStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void saveLabel(String id, String label) {
        redis.opsForValue().set("label:" + id, label);
    }
}
~~~

`StringRedisTemplate` uses `StringRedisSerializer` for standard string parts, allowing `GET` results to be decoded into `String`.

`RedisTemplate<String, Object>` with JSON fits cases where you want to store DTOs and need object serialization/deserialization rules. An unconfigured default template may use JDK serialization, producing binary bytes that are not readable as plain text.

Basic selection table:

| Stored data | Typically suitable serializer | Notes |
| --- | --- | --- |
| Redis keys, hash fields | `StringRedisSerializer` | Easy to diagnose, stable when key names are text |
| String values | `StringRedisSerializer` | Readable with Redis CLI commands |
| JSON DTOs | JSON serializer, such as `GenericJackson2JsonRedisSerializer` | Needs schema rules and type metadata handling |
| Binary data | Pass-through byte serializer | Avoid arbitrarily converting bytes to String |
| Integers with `INCR`/`DECR` | Redis integer reply, not a JSON object | Do not force numbers into strings just because value serializer is String |
| Legacy Java native serialization compatibility | `JdkSerializationRedisSerializer` | Has Java class coupling and security considerations |
| Payloads shared across languages | JSON, text, or an agreed interoperable format | Standardize schema and versioning |

No single serializer is optimal for every scenario. The golden rule is **reading and writing with the exact same byte contract**.

## 5. What does the executePipelined API return?

Spring Data Redis provides overloads like:

~~~java
List<Object> executePipelined(RedisCallback<?> action);

List<Object> executePipelined(
    RedisCallback<?> action,
    RedisSerializer<?> resultSerializer
);
~~~

Alongside `RedisCallback`, the template also provides overloads accepting `SessionCallback`.

The result is `List<Object>` because commands in a pipeline can return many types:

~~~text
SET      -> status / Boolean depending on API path and driver
GET      -> bytes -> String / DTO after deserialization
INCR     -> integer -> Long
EXISTS   -> boolean/integer per command API
HGETALL  -> map of field/value after deserialization
LRANGE   -> list of elements
DEL      -> number of deleted keys
~~~

Do not rely on `SET` always producing `Boolean.TRUE` at a fixed index across every client/version. Exact reply structure can depend on the Redis command, driver, and Spring Data Redis handling; know the command sequence and result mapping beforehand when designing.

### Callback must return null

Essential usage:

~~~java
List<Object> results = template.executePipelined(
    (RedisCallback<Object>) connection -> {
        // Queue Redis commands into the pipeline.
        // Do not rely on immediate per-command replies.
        return null;
    }
);
~~~

The callback returns `null` because the callback's return value is not the channel for returning pipeline results. Actual replies appear in the list returned by `executePipelined`.

Do not write:

~~~java
Long count = connection.stringCommands().incr(keyBytes);

if (count > 10) {
    // Flawed pipeline mindset:
    // the INCR reply may not have been received inside the callback yet.
}
~~~

While queuing a pipeline, a command's result is usually not ready to process like a synchronous call. Execute result-dependent logic **after the pipeline closes and full responses arrive**, or split into separate communication phases.

## 6. StringRedisTemplate example: write, read, increment counter

Here is a complete pipeline example with text data:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.List;

import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class PipelineDemoService {

    private final StringRedisTemplate template;

    public PipelineDemoService(StringRedisTemplate template) {
        this.template = template;
    }

    public List<Object> executeSimplePipeline() {
        return template.executePipelined(
            (RedisCallback<Object>) connection -> {

                byte[] nameKey = "demo:name:42"
                    .getBytes(StandardCharsets.UTF_8);

                byte[] nameValue = "An"
                    .getBytes(StandardCharsets.UTF_8);

                byte[] counterKey = "demo:reads"
                    .getBytes(StandardCharsets.UTF_8);

                connection.stringCommands().set(
                    nameKey, nameValue
                );

                connection.stringCommands().get(nameKey);

                connection.stringCommands().incr(counterKey);

                return null;
            }
        );
    }
}
~~~

With `StringRedisTemplate`, the byte reply from `GET` can be decoded by `StringRedisSerializer` into `"An"`. The integer reply from `INCR` retains numeric semantics.

~~~text
Commands in order:
  SET demo:name:42 An
  GET demo:name:42
  INCR demo:reads

Expected semantic results:
  [SET reply, "An", Long value from INCR]
~~~

The actual counter value depends on prior Redis state. This example focuses on **response types**, without assuming a counter always starts at 0.

### Why use getBytes(UTF_8) in the example?

`RedisConnection` is a low-level API accepting `byte[]`. Since both keys and values use UTF-8 text, calling `getBytes(StandardCharsets.UTF_8)` aligns with `StringRedisSerializer` in this case.

For values using JSON/JDK serialization, **do not replace every serializer with getBytes(UTF_8)**. Use the exact serializer used when writing.

## 7. Let the serializer handle both writing and reading

For JSON values, pick a defined serializer and pass it consistently. The example below illustrates the direct byte path in `RedisCallback`:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;

import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.GenericJackson2JsonRedisSerializer;

public class JsonPipelineReader {

    private final RedisTemplate<String, Object> template;
    private final GenericJackson2JsonRedisSerializer json =
        new GenericJackson2JsonRedisSerializer();

    public JsonPipelineReader(RedisTemplate<String, Object> template) {
        this.template = template;
    }

    public List<Object> writeThenRead() {

        byte[] key = "profile:42"
            .getBytes(StandardCharsets.UTF_8);

        byte[] value = json.serialize(
            Map.of("id", "42", "name", "An")
        );

        return template.executePipelined(
            (RedisCallback<Object>) connection -> {
                connection.stringCommands().set(key, value);
                connection.stringCommands().get(key);
                return null;
            },
            json
        );
    }
}
~~~

In the example:

1. `json.serialize(...)` produces bytes to write to Redis.
2. `connection.stringCommands().set(...)` knows nothing about `Map` because it only takes bytes.
3. `connection.stringCommands().get(...)` retrieves the byte reply.
4. The `executePipelined(..., json)` overload applies the JSON serializer to byte value results within the overload's handling scope.
5. `List<Object>` holds the command replies, where the `GET` result is decoded via the JSON serializer.

This code assumes this data key obeys the JSON contract. If other keys store plain strings or JDK bytes, mixing them in the same pipeline and decoding all with JSON can fail.

**Note on serializer lifecycle:** in a real application, inject the same shared serializer bean between template configuration and operation code rather than accidentally creating separate serializer instances with different type metadata rules in different places. Creating a standalone instance in the example only demonstrates passing a serializer to the overload.

## 8. What does the serializer passed to executePipelined change?

The overload accepting `resultSerializer` adjusts how **results** are decoded; it **does not automatically change the bytes sent inside the callback**.

Compare:

~~~text
A. WRITE direction inside RedisCallback
   Map/DTO --serialize(JSON)--> byte[] --SET--> Redis

B. READ direction after pipeline completes
   Redis --GET--> byte[] --resultSerializer--> Map/DTO
~~~

If you only swap the result serializer:

~~~java
template.executePipelined(
    (RedisCallback<Object>) connection -> {
        // Still writes however the code here constructs byte[].
        return null;
    },
    anotherSerializer
);
~~~

the commands inside the callback **do not automatically change** how they serialize keys or values.

Another detail: `RedisTemplate` uses different deserialization paths for scalar values, hash keys, and hash values. When passing a custom `resultSerializer`, do not assume every element inside every container/map type uses only that serializer. For `HGETALL` or nested lists, results are also governed by command rules and configured hash serializers. If mixing different structures in one pipeline, check the contract of each command type in your deployed version.

### Valid cases for a custom resultSerializer

- Needing to read legacy values with a serializer different from the template's default value serializer.
- A group of commands in the pipeline all return values in a specific format.
- Wanting a specialized pipeline to read binary payloads with a matching serializer.
- Needing to separate pipeline result decoding from template configuration in a controlled scope.

### Unsuitable cases

- A pipeline mixing keys with completely different byte formats while using only one shared resultSerializer.
- Expecting `resultSerializer` to dictate how `RedisConnection` writes bytes.
- Expecting `resultSerializer` to convert `Long` counters or `Boolean` statuses into DTOs.
- Expecting Spring to auto-infer schemas of all hashes and lists across multiple versions.

## 9. A pipeline with mixed results: how to read them?

Suppose a pipeline contains:

~~~text
SET user:42 ...
GET user:42
INCR metrics:reads
HGETALL flags:42
DEL cache:old
~~~

Results are returned as `List<Object>`. Some elements may be numeric values, some strings or DTOs, and some `Map<?, ?>`.

The safe way to read is binding **positional meaning** with **expected type**:

~~~java
List<Object> replies = pipelineResult;

for (int i = 0; i < replies.size(); i++) {
    Object reply = replies.get(i);

    if (reply instanceof String text) {
        System.out.println("String reply: " + text);
    } else if (reply instanceof Number number) {
        System.out.println("Numeric reply: " + number.longValue());
    } else if (reply instanceof Map<?, ?> map) {
        System.out.println("Hash fields: " + map.size());
    } else {
        System.out.println(
            "Reply #" + i + ": " + String.valueOf(reply)
        );
    }
}
~~~

This snippet illustrates type recognition, **not a replacement for the positional command contract**. In business code, you must know which element corresponds to `GET user:42`, which to `INCR`, and which to `DEL`.

Do not write:

~~~java
// Error-prone if the first reply is SET status rather than String.
String user = (String) replies.get(0);
~~~

or:

~~~java
// Error-prone if this value is Long/Boolean/Map.
byte[] raw = (byte[]) replies.get(2);
~~~

### Designing pipelines by data-type group

A maintainable strategy:

~~~text
Pipeline A: read multiple String keys
  GET name:1, GET name:2, GET name:3
  -> same StringRedisSerializer

Pipeline B: read multiple JSON DTO keys
  GET product:1, GET product:2
  -> same JSON serializer

Pipeline C: update counters
  INCR count:1, INCR count:2
  -> numeric replies
~~~

Splitting pipelines by contract simplifies deserialization and error handling. You do not have to cram unrelated commands into one large pipeline just to save a round trip.

## 10. Hashes require hashKeySerializer and hashValueSerializer

Redis Hashes differ from String values. Example:

~~~redis
HSET user:42 name An status ACTIVE
HGETALL user:42
~~~

In bytes:

~~~text
Redis Hash key:  "user:42"  -> keySerializer
Hash field:     "name"     -> hashKeySerializer
Hash value:     "An"       -> hashValueSerializer
~~~

In `RedisTemplate`, `hashKeySerializer` and `hashValueSerializer` can differ from `valueSerializer`.

Example of an all-string configuration:

~~~java
RedisTemplate<String, String> template = new RedisTemplate<>();
template.setConnectionFactory(connectionFactory);

StringRedisSerializer strings = new StringRedisSerializer();

template.setKeySerializer(strings);
template.setValueSerializer(strings);
template.setHashKeySerializer(strings);
template.setHashValueSerializer(strings);
template.afterPropertiesSet();
~~~

Low-level pipeline:

~~~java
List<Object> replies = template.executePipelined(
    (RedisCallback<Object>) connection -> {
        byte[] hashKey = "user:42".getBytes(StandardCharsets.UTF_8);
        byte[] field = "status".getBytes(StandardCharsets.UTF_8);
        byte[] value = "ACTIVE".getBytes(StandardCharsets.UTF_8);

        connection.hashCommands().hSet(hashKey, field, value);
        connection.hashCommands().hGetAll(hashKey);

        return null;
    }
);
~~~

The `HGETALL` result has a map structure; Spring Data Redis processes hash entries according to the corresponding serializer configuration. If `hashKeySerializer` is String while `hashValueSerializer` is JSON, fields may be Strings while values are decoded objects.

**Classic bug:** writing field `name` as UTF-8 while hash key serializer is configured as JDK serialization. When reading, Redis looks for different bytes than the written field. Depending on the operation, it may return `null`, an unexpected map, or a decoding error.

### Do not assume hash types from the value serializer

A template configured with:

~~~text
keySerializer       = String
valueSerializer     = JSON
hashKeySerializer   = String
hashValueSerializer = String
~~~

is completely valid. In that case, `GET` values and `HGETALL` values follow different conventions. Choose the pipeline and casts according to the structure being read.

## 11. Do commands returning numbers and statuses need a serializer?

Not every Redis reply is bytes that need converting into a String or DTO.

Examples:

~~~redis
INCR page:views
DEL cache:old
TTL session:42
EXISTS session:42
SCARD users:online
~~~

These commands return data representing integers or booleans depending on the API. In Java, results are typically types such as `Long` and `Boolean` already converted from RESP replies by the driver/Spring. `StringRedisSerializer` should not be used to assume every reply is a `String`.

Mental model table:

| Reply kind | Example | How to handle |
| --- | --- | --- |
| Binary bulk string | `GET key` | Decode with the matching value serializer |
| Hash map | `HGETALL key` | Decode hash keys/values per contract |
| List/set of bulk strings | `LRANGE`, `SMEMBERS` | Determine the serializer for each element |
| Integer | `INCR`, `SCARD`, `TTL` | Preserve numeric semantics |
| Status/Boolean | `SET` and status commands via driver | Use the actual API's type |
| Nil/null | `GET missing` | Handle absent key, avoid blind casting |

A serializer only solves **byte representation**; it does not invent business types when Redis returns integers, statuses, or nil.

## 12. Pipelining does not mean every reply is useful payload data

When building a pipeline for bulk writes:

~~~text
SET a 1
SET b 2
SET c 3
~~~

the goal may simply be reducing round trips when sending commands. The results are write status/replies; there is not necessarily a business payload to deserialize.

If you only need confirmation that commands were sent and processed, do not build a complex mapping layer trying to convert every reply into a DTO. When you need to check which individual commands succeeded, understand how the driver/Spring reports errors, reply counts, and command order. Redis does not turn a pipeline into a transaction; some commands may execute before a later command fails.

### Do not use pipelines to depend on earlier command results

Business example:

~~~text
GET inventory:sku-1
if remaining > 0:
  DECR inventory:sku-1
~~~

You cannot place `GET` and an `if` branch inside a pipeline callback and expect to read the result immediately. When an atomic decision is needed on Redis, use an appropriate technique such as a Lua script or a properly designed conditional transaction. Pipelining only optimizes round-trip exchanges; it does not create atomicity or transaction locking.

## 13. Choosing among JSON, String, JDK, and bytes

### StringRedisSerializer

Suitable for keys, hash fields, and plain text values.

**Pros:** UTF-8 is easy to inspect, cross-client compatible, compact payloads. **Cons:** does not automatically represent complex Java object types; storing structured data requires defining your own format.

Example:

~~~java
StringRedisSerializer serializer = new StringRedisSerializer();

byte[] bytes = serializer.serialize("ACTIVE");
String value = serializer.deserialize(bytes);
~~~

### JSON serializer

Suitable for DTOs exchanged across services or read by tools outside Java.

**Pros:** relatively human-readable, supports schemas with explicit field names. **Cons:** parsing cost and schema/type-metadata compatibility issues. Some JSON serializers can store runtime type info; understand type-handling policies and trusted data boundaries.

~~~java
GenericJackson2JsonRedisSerializer json =
    new GenericJackson2JsonRedisSerializer();

byte[] bytes = json.serialize(
    Map.of("id", "42", "enabled", true)
);

Object restored = json.deserialize(bytes);
~~~

If the system needs deterministic DTO types, consider a JSON serializer with explicit type configuration, migration rules, and application validators/schemas. Do not arbitrarily enable polymorphic deserialization for untrusted data.

### JdkSerializationRedisSerializer

May appear in default `RedisTemplate` configurations or legacy systems.

**Pros:** can reconstruct Java objects compatible with Java serialization. **Cons:** coupled to Java classes and versions, hard to interoperate across languages, larger payloads, and security risks when deserializing untrusted bytes.

Do not choose JDK serialization for data that could be tampered with by untrusted actors or needs to be shared outside Java. If required to read legacy data, restrict byte sources and allowed deserializable classes.

### Byte array serializer

Suitable when preserving binary payloads, small images, compressed blobs, or custom formats. When working with raw bytes, avoid converting to `String` and back, since binary data is not necessarily valid UTF-8 text.

**Common thread:** the serializer used when reading a pipeline must be compatible with the exact bytes written. The Java class name matters less than the established wire-format contract.

## 14. Multi-format data in the same Redis namespace

Consider three keys:

~~~text
user:1        -> JSON {"id":1,"name":"An"}
user:2        -> Java serialized object (legacy)
user:3        -> plain text "guest"
~~~

If you call `MGET` or multiple `GET`s in a pipeline using **one JSON resultSerializer**, only compatible JSON values can be read properly. For Java serialization bytes or plain text, JSON decoding may throw errors or produce invalid data.

Approaches:

**A. Standardize the contract first.** Migrate all keys to the new schema, or introduce a versioned namespace like `user:v2:...`. This is the cleanest option when you control the data.

**B. Split pipelines by serializer.** Use pipeline A for JSON, B for text, and C for legacy. Each batch has clear rules.

**C. Read raw bytes and decode via controlled metadata.** Store format version or type outside the payload, then select the right decoder per key. This requires actively managing results and taking care with nested hashes/lists.

Do not guess formats by trying JSON and randomly falling back to JDK deserialization for every received byte array. That makes errors unpredictable and widens the risk surface.

## 15. When reading raw bytes is needed, define an explicit contract

You can write a pass-through `RedisSerializer<byte[]>`:

~~~java
import org.springframework.data.redis.serializer.RedisSerializer;
import org.springframework.lang.Nullable;

public class RawBytesSerializer implements RedisSerializer<byte[]> {

    @Override
    public byte[] serialize(@Nullable byte[] value) {
        return value;
    }

    @Override
    public byte[] deserialize(@Nullable byte[] bytes) {
        return bytes;
    }
}
~~~

When the result is a bulk string and Spring Data Redis applies this serializer, the application receives `byte[]` to decode according to its own schema:

~~~java
RawBytesSerializer raw = new RawBytesSerializer();

List<Object> replies = template.executePipelined(
    (RedisCallback<Object>) connection -> {
        connection.stringCommands().get(
            "format:v2:item:1".getBytes(StandardCharsets.UTF_8)
        );
        return null;
    },
    raw
);

Object first = replies.get(0);

if (first instanceof byte[] bytes) {
    // Application can decode according to the known format version.
}
~~~

**Scope:** the example applies to a `GET` result that is a bulk string. Do not assume this serializer automatically turns every hash, collection, or status command reply into a raw byte array; result structure construction depends on Spring Data Redis APIs.

In Spring Data Redis versions that provide a built-in byte array serializer factory, you can use that implementation instead of a custom class, as long as the readback contract preserves raw bytes.

## 16. Comparing executePipelined vs. opening a pipeline directly on RedisConnection

There are two common API levels.

**`RedisTemplate.executePipelined(...)`**

~~~text
RedisCallback / SessionCallback
           |
           v
RedisTemplate orchestrates pipeline
           |
           v
Redis connection receives raw replies
           |
           v
RedisTemplate deserializes per configuration
           |
           v
List<Object>
~~~

**`RedisConnection.openPipeline() / closePipeline()`**

~~~text
RedisConnection.openPipeline()
        |
        v
send low-level commands
        |
        v
RedisConnection.closePipeline()
        |
        v
raw driver/connection replies
~~~

When working directly with the connection, you may need to decode `byte[]` manually using the serializer you used. Do not confuse raw connection-level results with what `RedisTemplate.executePipelined` has already processed.

If writing application code with `RedisTemplate`, **prefer the pipeline mechanism provided by the template** for consistency with connection lifecycle and serialization rules. Drop down to the connection level only for specific reasons where decoding responsibility is clearly defined.

## 17. Common errors and diagnostics

### Error 1: Reading JDK bytes with StringRedisSerializer

Symptom: garbled characters, replacement characters, or downstream processing errors.

Cause: data is not UTF-8 text. Check the write-time serializer rather than trying to "fix" it with random encoding changes.

### Error 2: Reading plain text with a JSON serializer

Symptom: `SerializationException` or JSON parse error.

Cause: bytes like `ACTIVE` are not valid JSON strings unless quoted as JSON. Use the matching serializer or migrate formats.

### Error 3: Confusing value and hash value serializers

Symptom: `GET` returns the right object, but `HGETALL` yields unexpected fields/values or fails to decode.

Cause: `hashKeySerializer`/`hashValueSerializer` differ from `valueSerializer`. Verify Hash command contracts separately.

### Error 4: Casting every result element to String

Symptom: `ClassCastException: Long cannot be cast to String` or similar.

Cause: commands like `INCR`, `TTL`, and `DEL` return numeric results. Use types matching each response contract rather than relying blindly on a String template.

### Error 5: Using a command's return value immediately inside the callback

Symptom: `NullPointerException` or conditional branches not executing as expected.

Cause: the command is being queued; the reply is not available yet. Move decisions after the pipeline or choose an appropriate atomic mechanism.

### Error 6: Callback returning a result instead of null

Symptom: confusing code or the wrong expectation that the callback's return value is the reply list.

Cause: the callback's return value is not the result channel. Return `null` and read `List<Object>` from `executePipelined`.

### Error 7: Same key written with multiple serializers

Symptom: works in a fresh environment but fails where old cache entries exist, or fails only for a subset of keys.

Cause: historical data used a different format. Introduce versioned namespaces, migration, or controlled decoder grouping.

### Error 8: Assuming pipelining is a transaction

Symptom: observing some commands modified data even though another command failed.

Cause: pipelining optimizes transport, not all-or-nothing guarantees. When transactions are required, design `MULTI`/`EXEC`/Lua appropriately, including nested result parsing.

## 18. Design suggestion for a profile-list reading pipeline

Suppose there are 500 `profile:ID` keys stored in the same JSON format, and we need to fetch 50 profiles at a time.

Design:

1. Use UTF-8 keys following the convention `profile:v2:{id}`.
2. Store JSON values using a single consistent serializer with a stable schema/version.
3. Obtain the required list of IDs from an appropriate source.
4. Pipeline `GET` commands for those exact 50 keys.
5. Use the same JSON `resultSerializer` to decode.
6. Match results with input IDs in the order commands were queued.
7. Handle `null` if some keys have expired due to TTL.

Example:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.GenericJackson2JsonRedisSerializer;

public class ProfileBatchReader {

    private final RedisTemplate<String, Object> template;
    private final GenericJackson2JsonRedisSerializer json;

    public ProfileBatchReader(
            RedisTemplate<String, Object> template,
            GenericJackson2JsonRedisSerializer json) {
        this.template = template;
        this.json = json;
    }

    public List<Object> read(List<String> ids) {
        if (ids.isEmpty()) {
            return List.of();
        }

        return template.executePipelined(
            (RedisCallback<Object>) connection -> {
                for (String id : ids) {
                    byte[] key = ("profile:v2:" + id)
                        .getBytes(StandardCharsets.UTF_8);

                    connection.stringCommands().get(key);
                }
                return null;
            },
            json
        );
    }
}
~~~

**Note:** the service assumes the `json` serializer is configured compatibly with existing data. For production use, bound input ID counts and batch sizes, map `results[i]` to `ids[i]`, and handle missing keys and exceptions explicitly.

With 50 `GET`s, results can mix objects and `null`; using `List<Object>` is more realistic than immediately casting to `List<Profile>` without type checks.

### Result ordering issue

Replies are associated according to command order in the pipeline. If the API enqueues exactly one `GET` per ID in input order, the application can match by index.

~~~text
ids:        [p1, p2, p3]
commands:   GET p1, GET p2, GET p3
results:    [obj1, null, obj3]
~~~

Do not strip `null`s before aligning with IDs, as that shifts the positions of subsequent results. Only after building the `id -> decoded value` mapping can you filter missing entries according to the API contract.

## 19. When does pipelining speed things up and when does it not?

Pipelining reduces the network cost of many consecutive wait cycles, yet other costs remain:

~~~text
Approximate total request time:
  time to serialize many values
+ transmitting bytes to Redis
+ Redis processing commands
+ transmitting many replies back
+ deserializing results
+ business processing in Java
~~~

Optimizing the network does not make serialization free. Using large JSON objects in a pipeline can consume significant CPU and JVM memory; overly large batches can create byte bursts and pressure Redis/the client.

Principles:

- Choose batch size based on payload size and latency targets, not just command count.
- Do not pipeline millions of commands in a single call and keep the entire `List<Object>` in memory.
- Prefer commands that belong together in the same request and share the same serialization contract.
- If you only need a set of keys, consider batch-capable commands like `MGET` when values share the same type.
- If decisions depend on prior replies, do not force a sequential model into a pipeline.
- With Redis Cluster, pipelines may be distributed across nodes/slots depending on the client; evaluate cost and support against topology.
- Measure serialization, command sending, reply receiving, and deserialization times to find the real bottleneck.

### Pipelining is not always better than MGET

If the goal is reading multiple String keys, `MGET` can return multiple values in one command. Pipelining multiple `GET`s is useful when coordinating multiple command types or when available APIs cannot use a single batch command. Both require compatible serializer rules.

## 20. Choosing serializers by compatibility and data lifecycle

When deciding on a serializer, ask:

| Question | Why does it matter? |
| --- | --- |
| Which services read the Redis data? | Java binary formats may not suit Node.js/Python services |
| Do values need multi-version compatibility? | Changing DTOs can break old decoders |
| Do keys need inspection via redis-cli? | String key serializers are easier to debug than binary |
| Is data String, JSON, or arbitrary bytes? | Each type has its own contract |
| Are Redis Hashes used? | Both hash key and hash value serializers must be configured |
| Does the pipeline mix formats? | A single result serializer may be insufficient |
| Are values large or batches big? | Encode/decode cost and memory are significant |
| Does data come from untrusted sources? | Deserialization must restrict types and validate |
| Is migration from an old cache needed? | Changing serializers does not convert stored data |

A clear enough convention might look like:

~~~text
Namespace "profile:v2:*":
  key           -> StringRedisSerializer / UTF-8
  value         -> unified JSON serializer
  schemaVersion -> v2 in namespace or payload
  pipeline      -> read profile:v2 only, decode JSON

Namespace "metrics:*":
  key           -> StringRedisSerializer / UTF-8
  value         -> Redis integer commands
  pipeline      -> Long results

Namespace "avatar:*":
  key           -> StringRedisSerializer / UTF-8
  value         -> raw binary
  pipeline      -> read bytes, decoded by application layer
~~~

With these rules, maintainers know which serializer each pipeline uses without guessing from returned data.

## 21. Hands-on: observing the path of results yourself

A small exercise in a test Redis environment:

### Case A — String

~~~redis
SET demo:text "hello"
GET demo:text
~~~

Use `StringRedisTemplate` to pipeline a `GET` command and observe the result is a `String` when deserialization matches.

### Case B — Integer

~~~redis
SET demo:counter 0
INCR demo:counter
~~~

Pipeline `INCR` and observe the numeric reply type; it does not need to become a `String` just because the template uses `StringRedisSerializer`.

### Case C — Hash

~~~redis
HSET demo:hash name An status ACTIVE
HGETALL demo:hash
~~~

Configure hash key/value serializers as String, then inspect the returned map.

### Case D — JSON

Use a JSON serializer to write an object through the Spring Data Redis API, then pipeline `GET` and read with a compatible JSON serializer. Swap in a mismatched `resultSerializer` in the test environment to see why deserialization must obey the contract.

### Case E — Non-existent key

Pipeline two `GET`s in order:

~~~text
GET demo:exists
GET demo:missing
~~~

Observe the `null` element and keep its position when mapping replies to IDs/keys. Do not remove `null`s before alignment.

## 22. Frequently asked questions

**Why does RedisTemplate return List<Object> instead of List<String>?**

Because a pipeline can contain commands returning different types: bulk strings, integers, booleans, maps, lists, or nulls. Spring cannot guarantee a single uniform generic type for every reply.

**Does `executePipelined(..., resultSerializer)` automatically serialize values on SET?**

No. That overload controls decoding of applicable results. When using low-level `RedisConnection`, developers must still construct the right bytes to send.

**With StringRedisTemplate, is every reply a String?**

No. Applicable byte replies are decoded into `String`; counters, statuses, or other structured data retain types according to the command API.

**Why does HGETALL have a different type from GET?**

Redis Hashes have their own field/value serializers, and `HGETALL` returns a map. Do not cast a map to a single value or assume hashes use the same serializer as `GET`.

**Can JSON and String be mixed in the same pipeline?**

You can send any commands, but decoding all bulk results with one shared serializer will easily fail. Split pipelines by format or receive raw bytes and decode in a controlled manner.

**Why does a normal GET work while executePipelined fails?**

The normal read path may use a specific `opsForValue` serializer, while the low-level callback constructs different bytes/serializers, or the pipeline `resultSerializer` does not match the format. Compare write path, read path, and hash/value serializer settings.

**Can pipelining be used for conditional updates on a newly read value?**

No. Pipelining does not provide the ability to wait and branch inside the callback based on replies. Use two phases with conditional checks, or a script/transaction suited to your correctness requirements.

**Is pipelining atomic?**

No. Commands in a pipeline are sent in a batch to reduce round trips; other commands can still interleave depending on system state, and there is no all-or-nothing guarantee like a transaction.

**Should I use the JDK serializer because it takes less code?**

Only when there is a specific compatibility reason and full control over data. JSON/String are usually easier to share and inspect; JDK serialization carries security, class-coupling, and cross-language costs/limits.

## 23. Implementation takeaways

- **Pipelines optimize communication**, without changing Redis's byte-oriented data nature or creating transactions.
- **Write serialization and read deserialization are two separate steps.** `resultSerializer` does not alter bytes written via `RedisConnection`.
- **`executePipelined` returns `List<Object>`** because replies have mixed types; always process by command type and enqueued order.
- **`StringRedisTemplate` suits strings**, whereas templates for DTOs need a serializer with an explicit schema.
- **Hashes have their own hashKeySerializer/hashValueSerializer.** Do not assume they match `valueSerializer`.
- **Mixed data needs a mixed strategy.** Split pipelines by format or define a controlled raw-bytes read path.
- **Performance optimization requires measuring encode/decode and memory too**, not just round-trip counts.

## References

- [Spring Data Redis – Pipelining](https://docs.spring.io/spring-data/redis/reference/redis/pipelining.html)
- [Spring Data Redis – Serializers](https://docs.spring.io/spring-data/redis/reference/redis/serializer.html)
- [Spring Data Redis – RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Data Redis – API RedisTemplate](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/core/RedisTemplate.html)
- [Spring Data Redis – API RedisSerializer](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/serializer/RedisSerializer.html)
- [Redis – Pipelining](https://redis.io/docs/latest/develop/using-commands/pipelining/)
- [Redis – Data types](https://redis.io/docs/latest/develop/data-types/)
