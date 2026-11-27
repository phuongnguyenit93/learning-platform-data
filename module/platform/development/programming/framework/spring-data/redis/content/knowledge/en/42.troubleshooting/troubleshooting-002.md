# Data in redis-cli Differs from Application Results Due to Serializer

## 1. Scenario: Redis Has Data, but Two Tools See It Differently

A developer uses Spring Data Redis to write an object successfully:

```java
redisTemplate.opsForValue().set("user:42", user);
```

The application then reads it back:

```java
User user = (User) redisTemplate.opsForValue().get("user:42");
```

The result in Java is a valid `User`. However, when opening the terminal:

```bash
redis-cli GET user:42
```

it returns:

```text
(nil)
```

Another case: `redis-cli GET product:42` shows a string with strange characters or JSON containing a Java class name, whereas Java returns a complete object.

Or:

```redis
TYPE person:42
```

returns:

```text
hash
```

while the user tries running `GET person:42` and hits `WRONGTYPE`.

These symptoms do not necessarily mean Redis lost data, do not necessarily mean Redis Server and Spring Boot have different caches, and do not prove Redis has a bug. The root cause usually lies in the **serializer**, **Redis data type**, or how the key name is constructed.

> Redis stores **byte sequences for keys/values** and Redis data structures. `redis-cli` does not automatically know which serializer to use to decode a Java object, and Spring Data Redis can encode both the key and the value before sending commands.

This lesson belongs to the **Diagnostics** chapter of Spring Data Redis: moving from what an operator observes in `redis-cli` to identifying the exact bytes that the application sends and expects when reading.

### Learning Objectives

After completing this lesson, you will be able to:

1. Distinguish between logical Java data, serialized bytes, and the actual data stored in Redis.
2. Explain why `redis-cli GET key` returns `(nil)` even when `RedisTemplate` can read it.
3. Recognize signs of Java native serialization, JSON serialization, UTF-8 String, binary codecs, and Redis Hashes.
4. Distinguish between `keySerializer`, `valueSerializer`, `hashKeySerializer`, `hashValueSerializer`, and the Spring Cache serializer.
5. Use `TYPE`, `EXISTS`, `TTL`, `STRLEN`, `HGETALL`, and connection details to narrow down the root cause.
6. Write Java code to compare raw key/value bytes against the configured Redis serializer.
7. Understand why `StringRedisTemplate`, `RedisTemplate`, Redis Repository, Redis Cache, and reactive templates can view the same Redis instance in different ways.
8. Distinguish serializer issues from wrong Redis instance, logical database, key prefix, TTL, Cluster slot, and data format migration issues.
9. Plan a serializer change without breaking previously written data.
10. Design integration tests that read data created by older application versions to prevent deployment failures.

---

## 2. Redis Does Not Store Java Objects as the JVM Sees Them

When a Java application creates:

```java
record ProductDto(
    String id,
    String name,
    long priceInCents
) {}
```

and wants to store the object in Redis, Spring must convert the data into a representation that Redis accepts.

A typical path:

```text
Java object:
  ProductDto("p-42", "Laptop", 1999900)
          |
          v
RedisSerializer<ProductDto>
          |
          v
byte[]:
  [7B, 22, 69, 64, 22, 3A, ...]  (if UTF-8 JSON)
          |
          v
Redis protocol: SET <key bytes> <value bytes>
          |
          v
Redis String value (bytes)
```

When reading:

```text
Redis value bytes
          |
          v
RedisSerializer.deserialize(bytes)
          |
          v
Java ProductDto
```

`redis-cli` stands at a different position:

```text
redis-cli GET <key bytes>
          |
          v
Redis response bytes
          |
          v
Displayed according to redis-cli mode
```

The CLI does not run the application's `ObjectMapper.readValue(...)` or `JdkSerializationRedisSerializer.deserialize(...)` unless you explicitly write the corresponding decoding step yourself.

### 2.1. Multiple Transformations to Distinguish

| Component | Example | Does Redis natively understand Java? |
|---|---|---|
| Java object | `ProductDto("p-42", ...)` | No |
| Java key String | `"product:42"` | Not yet key bytes |
| Key serializer | `StringRedisSerializer` | Handled by Spring/client |
| Value serializer | JSON/JDK/custom codec | Handled by Spring/client |
| Redis key | Byte sequence | Used by Redis for lookup |
| Redis String value | Byte sequence | Stored by Redis, unaware of Java class |
| Redis Hash field | Byte sequence | Fields also need a serializer |
| redis-cli display | Printable string, escaped, or binary | Only a display representation |
| Java deserializer | `byte[] -> Java object` | Handled by application/driver |

Key point: **Redis String is a Redis data type**, not an indication that the value is a UTF-8-readable `java.lang.String`.

### 2.2. Redis TYPE Does Not Reveal the Serializer

```redis
TYPE product:42
```

If it returns:

```text
string
```

the value could be:

- UTF-8 text.
- JSON.
- Byte array from Java serialization.
- Protobuf/MessagePack.
- gzip/zstd compressed data.
- Encrypted data.
- A proprietary binary format used by the company.

`TYPE string` only states that Redis is storing a **Redis String** (binary-safe); it does not say the content is UTF-8 or JSON.

### 2.3. Binary Data Does Not Mean Corrupted Data

If the CLI displays:

```text
"\xac\xed\x00\x05..."
```

that may be the beginning of a Java Object Serialization stream. The hexadecimal prefix `AC ED 00 05` is a common indicator of Java native serialization, though you must still verify the actual serializer before drawing a conclusion.

Hard-to-read displayed data does not automatically mean a storage error. What needs to be confirmed is **the right bytes, the right serializer, and the right schema**.

---

## 3. A Single Spring Data Redis Call Can Serialize Both Key and Value

Consider:

```java
redisTemplate.opsForValue().set(
    "customer:42",
    customer
);
```

Conceptually, the client performs:

```text
Java key:
    "customer:42"
        |
        v
keySerializer.serialize(...)
        |
        v
Redis key bytes

Java value:
    Customer object
        |
        v
valueSerializer.serialize(...)
        |
        v
Redis value bytes
```

The two serializers are **independent**. An application might use:

```text
Key:   JDK serialization
Value: JDK serialization
```

or:

```text
Key:   UTF-8 String
Value: JSON
```

or:

```text
Key:   UTF-8 String
Value: Protobuf binary
```

Therefore, an error where the CLI cannot find the key and an error where the CLI sees an unreadable value can be **two separate issues**.

### 3.1. Unexpected Key Serializer Leads to `(nil)`

Suppose `RedisTemplate` uses JDK serialization for keys:

```java
redisTemplate.opsForValue().set("user:42", user);
```

In practice, the key bytes sent may be a binary sequence starting with a Java serialization header rather than the ASCII/UTF-8 string:

```text
u s e r : 4 2
```

When the CLI runs:

```redis
GET user:42
```

it sends the **UTF-8 bytes of the literal `user:42`**, which differ from the bytes serialized by Java.

Redis compares keys byte-by-byte; since the two byte sequences do not match, it returns `(nil)`.

```text
Java client key bytes:
    [AC ED 00 05 ... "user:42" ...]   (illustrative)

redis-cli key bytes:
    [75 73 65 72 3A 34 32]           (UTF-8 "user:42")

Result:
    two different Redis keys
```

**Do not simply switch to `redis-cli --raw` expecting to find the key.** `--raw` controls how the CLI formats the output; it does not convert the key argument into `JdkSerializationRedisSerializer` bytes.

### 3.2. Different Value Serializer Leads to "Strange" Data

If the key uses a String serializer while the value uses Java serialization:

```text
Key bytes:   "user:42"
Value bytes: AC ED 00 05 ...
```

then:

```redis
GET user:42
```

will find the key but return a hard-to-read binary string.

When Java uses the matching `JdkSerializationRedisSerializer`, those bytes can be converted back into an object.

### 3.3. Two Applications Can Read Different Values Because of Different Serializers

For example:

```text
Service A:
    keySerializer = String
    valueSerializer = JSON

Service B:
    keySerializer = String
    valueSerializer = JDK
```

Both use the same Redis Server and the same `"product:42"` key. Service A writes JSON; Service B reads the bytes and tries to decode them as Java native serialization.

The outcome may be:

```text
SerializationException
StreamCorruptedException
ClassCastException
```

or another decoding error depending on the code and configuration.

A "healthy" Redis Server does not guarantee that two applications share the same **data contract**.

---

## 4. Common Serializers in Spring Data Redis

### 4.1. StringRedisSerializer

Purpose:

```text
Java String <-> bytes according to configured charset
```

With common UTF-8:

```java
new StringRedisSerializer()
```

Example:

```java
String input = "hello";
byte[] data = new StringRedisSerializer().serialize(input);
```

Redis receives bytes suitable for text. The CLI can usually read:

```redis
GET lab:greeting
```

when both the key and value use corresponding String serializers.

**Unicode note:** `String.length()` in Java is not equal to the number of UTF-8 bytes. Vietnamese characters can occupy multiple bytes; when measuring payload size, use `serializedBytes.length`.

### 4.2. JdkSerializationRedisSerializer

Converts objects using Java native serialization. Some `RedisTemplate` configurations may use Java serialization by default for most operations if not customized, but **you must inspect the actual bean** instead of assuming this is the default in every application.

Common indicators:

```text
AC ED 00 05 ...
```

Risks:

- Not human-readable in `redis-cli`.
- Depends on class name, `serialVersionUID`, and Java object graph compatibility.
- Can break after package/class/schema changes.
- Native Java deserialization of data from untrusted sources requires strict security evaluation.
- Difficult to share the byte contract with non-Java applications.

**Enabling native Java deserialization indiscriminately for data controllable by untrusted parties is not recommended.**

### 4.3. Jackson JSON serializer

A family of serializers using Jackson to convert Java objects into JSON bytes.

Illustrative value example:

```json
{"id":"p-42","name":"Laptop","priceInCents":1999900}
```

In some polymorphic/generic JSON configurations, the JSON also contains type metadata, such as an `@class` field or another type hint mechanism. **The exact field name, structure, and content depend on the serializer, ObjectMapper, Spring Data Redis/Jackson version, and configuration.**

A CLI user might see:

```json
{
  "@class": "com.example.ProductDto",
  "id": "p-42",
  "name": "Laptop",
  "priceInCents": 1999900
}
```

which differs from the deserialized Java object because the CLI only prints JSON, whereas the Java mapper converts JSON into a class.

Do not assume JSON always includes type metadata for every Jackson serializer; likewise, do not enable polymorphic deserialization to read untrusted data without a security review.

### 4.4. Custom binary serializer

Possible formats include:

```text
Protobuf
MessagePack
Avro
Kryo
Compressed JSON
Encrypted binary
Domain-specific binary codec
```

The CLI may display strange characters even when the data is completely valid. It is not always possible to determine the exact codec from just the first few bytes.

You must inspect the application's **serializer bean, schema/version, and data contract**.

### 4.5. Serializer and Redis Data Type Are Two Different Axes

| Redis type | Typical Spring API | Related serializers |
|---|---|---|
| String | `opsForValue()` | Key/value serializers |
| Hash | `opsForHash()` | Key/hashKey/hashValue serializers |
| List | `opsForList()` | Key/value serializers and corresponding mapping |
| Set | `opsForSet()` | Key/value serializers |
| Sorted Set | `opsForZSet()` | Key/value serializers |
| Stream | `opsForStream()` | Stream key/record mapping/serialization per API |
| Pub/Sub | `convertAndSend`/listeners | Message serializers per configuration |
| Spring Cache | `RedisCacheManager` | Cache key/value serialization pairs |
| Redis Repository | Repository converter/mapping | May differ from `opsForValue` serializer |

Do not assume a single `RedisTemplate` bean controls all data across every abstraction in the project.

---

## 5. StringRedisTemplate and RedisTemplate Are Not the Same

### 5.1. StringRedisTemplate

`StringRedisTemplate` is designed for String data:

```java
@Autowired
StringRedisTemplate stringRedisTemplate;
```

Example:

```java
stringRedisTemplate.opsForValue().set(
    "lab:message",
    "Xin chào"
);
```

On the matching Redis database:

```redis
GET lab:message
```

The CLI can display the corresponding text if the terminal/locale handles UTF-8 properly.

### 5.2. RedisTemplate<K,V>

`RedisTemplate` allows configuring custom serializers:

```java
RedisTemplate<String, Object> template;
```

Seeing the generic `<String,Object>` alone is **not enough** to know whether key bytes are UTF-8 or value bytes are JSON. You need to inspect:

```text
template.getKeySerializer()
template.getValueSerializer()
template.getHashKeySerializer()
template.getHashValueSerializer()
```

and the serializers used in the relevant execution path.

### 5.3. Two Beans Can Coexist

An application may declare:

```java
@Autowired
StringRedisTemplate stringRedisTemplate;

@Autowired
RedisTemplate<String, Object> redisTemplate;
```

Both call:

```java
stringRedisTemplate.opsForValue().get("user:42");
redisTemplate.opsForValue().get("user:42");
```

yet the two calls may use different key serializers. One call sees a value; the other returns `null` or throws a decoding error.

**Before debugging data, identify the exact bean injected in the running code path.**

### 5.4. Example Creating a RedisTemplate Using String Keys and JSON Values

An illustrative configuration using the Spring Data Redis Jackson 2 serializer:

```java
package com.example.redis;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.GenericJackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class RedisSerializationConfig {

    @Bean
    RedisTemplate<String, Object> jsonRedisTemplate(
            RedisConnectionFactory connectionFactory) {

        RedisTemplate<String, Object> template =
            new RedisTemplate<>();

        template.setConnectionFactory(connectionFactory);
        template.setKeySerializer(
            new StringRedisSerializer()
        );
        template.setValueSerializer(
            new GenericJackson2JsonRedisSerializer()
        );
        template.setHashKeySerializer(
            new StringRedisSerializer()
        );
        template.setHashValueSerializer(
            new GenericJackson2JsonRedisSerializer()
        );

        template.afterPropertiesSet();
        return template;
    }
}
```

**Version note:** Jackson serializer APIs and class names may differ in newer Spring Data Redis/Jackson generations. This is an example for versions that include this class; in practice, use the serializer appropriate for the release you are running. For data belonging to a specific class, a typed serializer with an explicit schema may be more appropriate than a generic polymorphic JSON serializer.

With the configuration above, the CLI can see the String key directly, though the value may still contain JSON/type metadata depending on the serializer.

### 5.5. Do Not Change the Serializer Just to Make CLI Output Look Prettier

If production already holds a million keys written with JDK serialization, immediately switching `keySerializer` to String can make the application **unable to find** the old keys.

If you switch `valueSerializer` to JSON while keys still contain JDK bytes, the application may throw decoding errors.

A serializer is **the contract for persisted data**, not just a display preference.

---

## 6. Analyzing the Question: Why Does the CLI Return `(nil)`?

A result like:

```redis
GET user:42
```

```text
(nil)
```

can have several causes:

1. The key genuinely does not exist.
2. Spring uses a different key serializer, so the raw bytes differ from `user:42`.
3. Spring Cache uses a prefix, such as `users::42` instead of `user:42`.
4. The app is connecting to a different Redis host/port.
5. The app uses a different logical database (`SELECT`/database index) on standalone Redis.
6. In Redis Cluster, the key belongs to another node/slot, or the CLI does not follow redirects properly.
7. The key expired due to TTL or was evicted.
8. The app changed its key naming scheme or version namespace.
9. Another writer deleted the key before you checked.
10. The CLI is hitting a different container/network endpoint than the instance Spring accesses.

**Do not conclude it is a serializer issue from a single `(nil)` line.**

### 6.1. Check the Connection First

In an authorized environment:

```redis
PING
INFO server
INFO keyspace
```

Verify from the deployment/connection factory:

```text
Redis hostname
Port
TLS enabled
ACL username
Logical database index (standalone)
Cluster/Sentinel configuration
Namespace/prefix
Application environment
```

Do not put Redis passwords into command-line history or logs just for debugging.

### 6.2. Redis logical databases

On standalone Redis, the application may use a DB index other than 0:

```text
Spring client -> DB 2
redis-cli default -> DB 0
```

In the appropriate CLI invocation:

```bash
redis-cli -n 2
```

Then run `GET` on the key again.

However, **Redis Cluster does not support multiple standalone-style logical databases**; typically only DB 0 is used. Do not treat `SELECT 2` as a fix for Cluster issues.

### 6.3. Key prefix

Spring Cache may generate a key like:

```text
products::42
```

when Java code uses:

```java
@Cacheable(cacheNames = "products", key = "#productId")
```

Depending on the prefix, serializer, and cache manager configuration, the actual Redis key is **not simply `"42"`**.

A Redis Repository might use:

```text
people:<id>
```

or a keyspace declared by the entity, rather than a key you guess manually.

If the CLI uses the wrong key name, whether the value serializer is right or wrong is irrelevant.

### 6.4. Expired Key

```redis
TTL user:42
PTTL user:42
```

Common special return values:

```text
-2: key does not exist
-1: key exists but has no TTL
>=0: remaining time-to-live for the key
```

If `GET` returns `(nil)` and `TTL` returns `-2`, that confirms **the key bytes queried by the CLI do not exist at that moment**. It does not prove that a key created by the app with another serializer does not exist either.

### 6.5. Do Not Use `KEYS *` Indiscriminately in Production

`KEYS` scans the keyspace and can cause unwanted impact on large datasets. With proper authorization:

```redis
SCAN 0 MATCH product:* COUNT 100
```

is a more incremental way to iterate, though you should understand:

- `SCAN` can return duplicates or miss/shift items while the keyspace is changing.
- `MATCH` operates on **key bytes/patterns**; it does not decode Java-serialized keys.
- The pattern `product:*` will not necessarily match keys with a JDK-serialized binary prefix.
- `COUNT` is a hint, not a guarantee of exactly 100 keys.
- Redis Cluster requires checking the appropriate node/primary scope.
- Key names may contain PII; do not dump raw lists into shared logs.

---

## 7. CLI Sees a Binary Value: How to Handle It?

Suppose:

```redis
GET user:42
```

returns hard-to-read escaped content.

Analyze in the following order:

1. Is `TYPE user:42` equal to `string`?
2. Which value serializer does the application use?
3. Are the key bytes in the app and CLI identical?
4. Are there signs of a known binary format (JDK header, gzip, custom prefix...)?
5. Is the value compressed or encrypted?
6. Did the serializer change across deployment versions?
7. Is the CLI terminal displaying UTF-8 incorrectly?
8. Are there security requirements preventing us from viewing the raw payload?

### 7.1. redis-cli Display Modes

Invocation options:

```bash
redis-cli GET lab:message
redis-cli --raw GET lab:message
```

`--raw` changes how **the response is printed**. It does not convert object bytes into a Java object and does not make the server decode JSON.

For binary values, printing raw bytes to a terminal may emit control characters, causing garbled display or terminal/log risks. In a lab, you can pipe the output to a hex viewer:

```bash
redis-cli --raw GET lab:binary | xxd -g 1
```

Note that `redis-cli` may append a newline for display; CLI output in a pipeline should not be assumed to match the original value byte-for-byte unless verified. When exact comparison is needed, prefer reading raw bytes through a Redis connection API in a test rather than relying on stdout formatting.

Do not run hex/raw payload printing on **real production secrets**, because hex also exposes the entire value in reversible form.

### 7.2. Java Serialization Header

A Java Object Serialization stream typically starts with:

```text
AC ED 00 05
```

Seeing these bytes is a **hint** that the value was Java-serialized. However, you still need to check:

```text
Actual writer's value serializer
Class type
serialVersionUID
Correct Redis key
Data format in an earlier writer version
```

You cannot decode it properly just by knowing the header if the corresponding class/schema is missing.

### 7.3. JSON Is Readable in the CLI, but Java Still Cannot Read It

For example, the CLI shows valid JSON:

```json
{"id":"p-42","name":"Laptop"}
```

Yet `redisTemplate.opsForValue().get("product:42")` throws an exception.

Possible causes:

- Java is using a JDK deserializer for a JSON value.
- A typed JSON serializer expects type metadata, but the payload lacks it.
- Field or class names changed.
- `ObjectMapper` has different custom modules/constructors.
- The JSON follows schema V1, while the app expects V2.
- A field contains a number/enum/time format that the new mapper cannot handle.
- Generic `Object` is decoded into a `Map`, and the code casts it to `ProductDto`.
- The value is a JSON String literal while the code expects a JSON object.

**Valid JSON syntax does not guarantee valid Java type mapping.**

---

## 8. Key Serializer and Value Serializer Mismatch: Quick Identification Table

| Situation | In Java | In CLI | Primary suspect |
|---|---|---|---|
| Java reads it, CLI `GET name` returns nil | Object returned | `(nil)` | Key bytes/prefix/DB/host |
| Java reads it, CLI shows `\xac\xed...` | Valid object | Binary/escaped | JDK value serializer |
| Java reads it, CLI shows JSON `@class` | Valid object | JSON metadata | Generic typed JSON serializer |
| `StringRedisTemplate` reads `null`, `RedisTemplate` reads it | Different template behavior | Key exists | Different key serializer |
| `GET` returns WRONGTYPE | App uses `opsForHash` or Repository | `TYPE hash` | Redis data type mismatch |
| CLI `HGETALL` shows strange fields | App `opsForHash` reads properly | Binary field names/values | Hash serializers |
| Java throws JSON parse error, CLI shows binary | Java error | Binary payload | Value serializer mismatch |
| Java throws invalid class/type | Java error | Data present | Old Java/schema serialization |
| CLI sees JSON, but app returns `null` | Possibly different key | JSON present at queried key | Key prefix/DB/serializer/transaction/race |
| Both app and CLI see key, but values differ at two times | Different result | Different value | Concurrency, TTL, replica lag, caching |
| Cache `@Cacheable` reads it, `RedisTemplate` `GET` does not | Different abstractions | Data exists | Cache serializer/key prefix |
| Repository `findById` works, CLI `GET` fails | Entity mapped | `WRONGTYPE` | Redis Hash, not Redis String |

This table is a **diagnostic guide**, not a definitive diagnosis from a single symptom.

---

## 9. Comparing Raw Key Bytes from Java

The surest way to know whether two serializers produce the same key is to **compare bytes**, not Java Strings.

Example using Java 17+:

```java
import java.util.Arrays;
import java.util.HexFormat;

import org.springframework.data.redis.serializer.JdkSerializationRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

public class KeySerializerComparison {

    public static void main(String[] args) {
        String logicalKey = "user:42";

        byte[] utf8Key =
            new StringRedisSerializer().serialize(logicalKey);

        byte[] jdkKey =
            new JdkSerializationRedisSerializer().serialize(logicalKey);

        System.out.println(
            "Equal bytes? " + Arrays.equals(utf8Key, jdkKey)
        );

        // Only print hex on fake data in tests.
        System.out.println(
            "UTF-8: " + HexFormat.of().formatHex(utf8Key)
        );

        System.out.println(
            "JDK:   " + HexFormat.of().formatHex(jdkKey)
        );
    }
}
```

The `Arrays.equals` result tells you whether the two keys are byte-identical. In this example, the two serializers produce different representations.

Do not use this code to dump session tokens/PII in production. A hex string is a reversible representation of the original bytes, **not redaction**.

### 9.1. Actual Comparison Must Use the Injected Bean's Serializer

The example above uses two sample serializers for explanation. In a real project, you must identify the serializer used by the exact code path in question:

```java
RedisSerializer<?> configuredKeySerializer =
    redisTemplate.getKeySerializer();
```

Then use that serializer in a test authorized to access the appropriate data.

If the application has multiple beans:

```text
default redisTemplate
jsonRedisTemplate
stringRedisTemplate
cacheManager
reactiveTemplate
```

do not take the serializer from bean A to draw conclusions about bytes produced by bean B.

### 9.2. Comparing Bytes with a Unit Test

A guiding test:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.data.redis.serializer.StringRedisSerializer;

class RedisKeyFormatTest {

    private final StringRedisSerializer keySerializer =
        new StringRedisSerializer();

    @Test
    void keyFormatIsStable() {
        byte[] actual =
            keySerializer.serialize("product:v2:p-42");

        assertThat(actual).isEqualTo(
            "product:v2:p-42".getBytes(
                java.nio.charset.StandardCharsets.UTF_8
            )
        );
    }
}
```

This test protects the **wire format** of the key better than just checking `"product:v2:p-42".equals(...)` at the Java layer.

---

## 10. Reading Redis Raw Bytes via RedisConnection

To separate serializer bugs from stored data, you can use a low-level Redis connection in an isolated integration test.

Example with a String key:

```java
import java.nio.charset.StandardCharsets;

import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;

public class RawRedisInspector {

    private final StringRedisTemplate redis;

    public RawRedisInspector(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public int rawValueLength(String key) {
        byte[] rawKey =
            key.getBytes(StandardCharsets.UTF_8);

        byte[] rawValue = redis.execute(
            (RedisCallback<byte[]>) connection ->
                connection.stringCommands().get(rawKey)
        );

        return rawValue == null ? -1 : rawValue.length;
    }
}
```

Here, the callback uses the defined key bytes and fetches the raw bytes of the Redis String. The method only returns the length, **without printing the raw value**.

Conditions:

- `rawKey` must match the exact key bytes in Redis.
- The key must be a Redis String; if it is a Hash/List/Set, `GET` will fail with `WRONGTYPE`.
- If the key writer uses `JdkSerializationRedisSerializer`, do not pass UTF-8 key bytes as in the example; you must use the writer's exact serializer.
- APIs/callbacks may vary by Spring Data Redis version; use the approach supported in the running release.

### 10.1. Why Is This Approach Useful?

It separates two questions:

```text
(1) Does Redis hold a byte[] for these exact key bytes?
(2) Can the Java serializer decode that byte[] into an object?
```

If (1) has bytes but (2) fails, the issue likely lies in the value serializer/schema. If (1) has no bytes, go back to checking the key serializer/prefix/DB/TTL/endpoint.

### 10.2. Do Not Expose a Raw Inspector as a Public Admin API

An HTTP endpoint returning raw Redis bytes or raw hex can cause serious information disclosure.

If a diagnostic tool is needed, restrict it to:

```text
Test environments
Test namespaces
Authorized operators
No returning raw payloads to public clients
No writing secrets to centralized logs
Short activation window
```

---

## 11. Hash Serializers: Four Serializers, Not Two

For a Redis Hash:

```java
redisTemplate.opsForHash().put(
    "user:42",
    "displayName",
    "Alice"
);
```

there are multiple components:

```text
Redis top-level key:
    "user:42"           -> keySerializer

Hash field:
    "displayName"       -> hashKeySerializer

Hash field value:
    "Alice"             -> hashValueSerializer
```

Meanwhile, `valueSerializer` is generally used for other value operations such as `opsForValue`, `opsForList`, and `opsForSet`, depending on the API.

### 11.1. A Hash Can Have Binary Field Names

If `hashKeySerializer` uses JDK serialization, the CLI:

```redis
HGETALL user:42
```

may display unreadable field names even when the top-level key `user:42` is UTF-8.

In that case:

```redis
HGET user:42 displayName
```

may return `(nil)` because the CLI sends the field name `"displayName"` in UTF-8, whereas the Java writer sent field bytes encoded with JDK serialization.

### 11.2. Hash Field Values Can Also Be Binary

For example:

```text
Top-level key: String serializer
Hash field:    String serializer
Hash value:    JDK serializer
```

CLI `HGET user:42 displayName` finds the field but returns binary data.

You must inspect `getHashValueSerializer()`, not just `getValueSerializer()`.

### 11.3. An Explicit Configuration Pattern

For a Hash containing only Strings:

```java
RedisTemplate<String, String> template =
    new RedisTemplate<>();

template.setConnectionFactory(connectionFactory);
template.setKeySerializer(
    new StringRedisSerializer()
);
template.setValueSerializer(
    new StringRedisSerializer()
);
template.setHashKeySerializer(
    new StringRedisSerializer()
);
template.setHashValueSerializer(
    new StringRedisSerializer()
);
template.afterPropertiesSet();
```

This is an example for a String-only Hash, not a mandatory setting for all Java objects. If Hash values are DTOs, an appropriate serializer is needed.

### 11.4. Check the Redis Data Type Before Choosing a Command

```redis
TYPE user:42
```

If it is `hash`:

```redis
HGETALL user:42
HLEN user:42
```

Do not run `GET` on a Hash. If it is `string`:

```redis
GET user:42
STRLEN user:42
```

Do not run `HGETALL` on a String.

`WRONGTYPE` is an error from **choosing a Redis command that does not match the data type**, which is different from a JSON/JDK deserialization error.

---

## 12. Spring Data Redis Repositories Typically Store Entities as Redis Hashes

With a Redis Repository:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash("people")
public class Person {

    @Id
    private String id;

    private String name;

    // constructors/getters/setters...
}
```

A Spring Data Redis Repository can store an entity as a Redis Hash via a mapping converter, rather than as a single JSON String representing the entire object.

Conceptually:

```text
Key:
    people:<id>

Hash fields:
    _class
    id
    name
```

Key names, metadata fields, conversion rules, and auxiliary keys depend on the Spring Data Redis mapping version and configuration.

### 12.1. Why Does GET Fail?

An operator tries:

```redis
GET people:42
```

and gets:

```text
WRONGTYPE Operation against a key holding the wrong kind of value
```

Then:

```redis
TYPE people:42
```

may return:

```text
hash
```

The appropriate command to inspect this data type is:

```redis
HGETALL people:42
```

However, **do not assume every field is readable as JSON text**. Custom converters or mappings may store non-UTF-8 bytes.

### 12.2. Repositories Do Not Use the Same Serializer Path as opsForValue

A common mistake:

> "I set `redisTemplate.setValueSerializer(JSON)`, so all Redis Repositories will write JSON Strings."

Not necessarily. Redis Repository uses its own mapping/conversion layer to map entities to Hashes and manage index/TTL metadata according to its design.

To determine the Repository wire format, you must check:

```text
RedisKeyValueAdapter
RedisMappingContext
MappingRedisConverter
Custom converters
@RedisHash / @Indexed / @TimeToLive
Keyspace configuration
```

for the Spring Data Redis version in use.

### 12.3. Secondary Indexes and Metadata

`@Indexed` can create auxiliary keys or Set members. If you look in the CLI and see multiple keys associated with one entity, that is not necessarily duplicate data caused by a serializer.

You need to understand entity keys, index keys, TTL/shadow-copy behavior, and other metadata; do not delete unfamiliar keys before understanding their role.

### 12.4. Verifying the Entity Lifecycle

An integration test should verify:

```text
repository.save(person)
repository.findById(id)
repository.existsById(id)
Query indexed fields if used
TTL if configured
repository.deleteById(id)
```

and cross-check Redis `TYPE`/fields using fake data. Having `findById` work is one step, but it does not prove all indexes and TTLs remain valid after a serializer change.

---

## 13. Spring Cache Has Its Own Serializer and Key Prefix

An application:

```java
@Cacheable(cacheNames = "products", key = "#productId")
public ProductDto getProduct(String productId) {
    return productService.load(productId);
}
```

may use `RedisCacheManager`, which is not necessarily the same `RedisTemplate` bean you configured manually.

A Redis key might look like:

```text
products::p-42
```

though the format/prefix can be customized. When the CLI runs:

```redis
GET p-42
```

getting `(nil)` is completely expected if the actual key is `products::p-42`.

### 13.1. Cache Values Can Be JDK-Serialized Bytes

In common Spring Data Redis setups, `RedisCacheConfiguration` defaults to a String serializer for cache keys and Java serialization for cache values unless overridden. **Do not rely on this default and skip checking the actual CacheManager configuration.**

Depending on the version and project, cache values may use JSON, JDK, or a custom serializer.

What to check is the configuration of:

```text
RedisCacheManager
RedisCacheConfiguration
Key serialization pair
Value serialization pair
Cache-specific configuration
Null caching behavior
Key prefix
TTL
```

### 13.2. Illustrative JSON Cache Configuration

For Spring Data Redis versions that provide `GenericJackson2JsonRedisSerializer`:

```java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.serializer.GenericJackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializationContext;

@Configuration
public class RedisCacheConfig {

    @Bean
    RedisCacheManager redisCacheManager(
            RedisConnectionFactory connectionFactory) {

        RedisCacheConfiguration defaults =
            RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(Duration.ofMinutes(10))
                .serializeValuesWith(
                    RedisSerializationContext
                        .SerializationPair
                        .fromSerializer(
                            new GenericJackson2JsonRedisSerializer()
                        )
                );

        return RedisCacheManager
            .builder(connectionFactory)
            .cacheDefaults(defaults)
            .build();
    }
}
```

**Note:** Class/API names may differ depending on the Jackson/Spring Data Redis generation. Check the documentation for your specific version; do not copy an example from another version into your project without verifying it. If polymorphic type metadata is not needed, you can choose a typed JSON mapping with a clearer schema.

### 13.3. Changing the Cache Serializer Between Two Deployments

Suppose:

```text
App v1:
    products::p-42 = JDK-serialized ProductDto

App v2:
    products::p-42 = JSON ProductDto
```

App v2 reading an old cache entry with a JSON serializer may fail. App v1 reading a new entry with a JDK serializer may also fail.

This is a **data format migration**, not a `redis-cli` bug.

For rebuildable caches, you can transition to a planned key prefix/version namespace:

```text
products:v1::p-42
products:v2::p-42
```

However, you must plan for a cold cache, cache stampede, temporary memory overhead, and database load. If Redis holds non-rebuildable state, never delete data to "clear the cache" this way.

### 13.4. Cache Null Marker

Spring Cache may use a special representation for cached `null` values depending on configuration. When changing serializers, an old null marker may become incompatible.

If the CLI shows an unusual value that does not look like your DTO, it may be a cache null representation; check the `CacheManager` config instead of assuming data corruption.

---

## 14. How Can RedisTemplate and StringRedisTemplate Read the Same Key Differently?

Suppose an application has two beans:

```text
A: StringRedisTemplate
B: RedisTemplate<String,Object> using JDK key serializer
```

Operations:

```java
A.opsForValue().set("lab:key", "from-A");
B.opsForValue().set("lab:key", "from-B");
```

If B indeed uses a JDK key serializer, Redis can end up holding **two keys with different bytes** for the same logical Java String `"lab:key"`.

```text
Redis:
    UTF-8 key "lab:key"       -> value from-A
    JDK bytes of "lab:key"    -> value from-B
```

CLI:

```redis
GET lab:key
```

sees the value from A, whereas reading through B may return the value from B.

Thus, Java and CLI showing "different results" is not because Redis returns inconsistent data, but because **the two clients are querying two different keys**.

### 14.1. Inspecting Both Sets of Key Bytes

In an integration test:

```java
byte[] aKey =
    new StringRedisSerializer().serialize("lab:key");

byte[] bKey =
    new JdkSerializationRedisSerializer().serialize("lab:key");
```

If the bytes differ, they are two independent Redis key names.

### 14.2. Experiment Using Only Fake Data

This scenario should be reproduced in a test Redis under a `lab:` namespace. Do not intentionally create additional keys with mismatched serializers in production Redis just to see what happens.

---

## 15. Wrong Redis Database, Host, or Cluster Node Can Look Like a Serializer Error

Before suspecting the serializer, verify that both tools are talking to the **same place**.

### 15.1. Host and Port

```text
Spring:
    redis.prod.internal:6379

CLI:
    127.0.0.1:6379
```

The CLI might be talking to a local Redis instance, not production Redis.

In Kubernetes:

```text
localhost inside the app container
    !=
localhost on the developer's machine
```

A port-forward might also point to a different service or namespace.

### 15.2. Logical Database

Standalone Redis can have multiple logical DB indexes:

```redis
SELECT 0
SELECT 2
```

Spring's `LettuceConnectionFactory` might be configured for DB 2 while the CLI defaults to DB 0.

Do not assume `(nil)` is a key serializer mismatch before checking database selection.

### 15.3. Redis Cluster

Redis Cluster partitions keys by hash slots. A CLI without cluster redirection enabled or connected to a node that does not own the slot may receive:

```text
MOVED <slot> <host>:<port>
```

Use the appropriate cluster-aware capability of your CLI/driver, such as `redis-cli -c` in an authorized environment.

Keep in mind:

- A Redis Cluster does not have multiple logical DBs like standalone Redis.
- Key bytes directly affect the hash slot.
- Changing the key serializer can change the slot.
- Scanning patterns on a single node does not cover the entire cluster.
- The client and CLI may see different versions of a key if replication/failover/read routing is involved.

### 15.4. Replica lag

If the application reads from primary while the CLI reads from a replica or vice versa, values may differ during the replication lag window. This is a consistency/routing issue, **not a serializer issue**.

A solid diagnosis must distinguish:

```text
same key bytes?
same Redis node/primary/replica?
same point in time?
same serializer?
```

---

## 16. Unicode, Charset, and Terminal Encoding

Vietnamese data is particularly useful for spotting confusion between characters and bytes.

For example:

```java
String text = "Hà Nội";
```

When using UTF-8, accented characters occupy multiple bytes. If the writer app uses UTF-8 while the CLI terminal or reader uses a different encoding, the output can look wrong.

### 16.1. Three Different Encoding Concerns

```text
Java String -> Redis bytes:
    Determined by the serializer/charset.

Redis bytes -> redis-cli display:
    Determined by CLI display/escaping behavior and terminal settings.

Redis bytes -> Java String:
    Determined by the deserializer/charset.
```

Each step must be checked individually; do not jump to "Redis corrupted UTF-8."

### 16.2. Replacement Character

If a reader attempts to decode invalid bytes as UTF-8, it may produce the replacement character `�` or throw an error depending on its decoder policy.

Once a string already contains replacement characters, original byte information may have been lost at the display layer. If you need to investigate a binary format, retrieve the **raw byte[]**, do not rely on a mis-decoded String.

### 16.3. Do Not Use `String.length()` as the Byte Size Stored in Redis

```java
String value = "Tiếng Việt";
int chars = value.length();
int bytes =
    value.getBytes(StandardCharsets.UTF_8).length;
```

`chars` and `bytes` can differ. To measure the actual payload, use `serializer.serialize(value).length` once the active serializer has been identified.

### 16.4. Byte Order Mark (BOM) and Inconsistent Charsets

A JSON file or String produced by another source may include a UTF-8 BOM or use a different encoding; the Java JSON parser and the CLI may handle it differently.

Do not blindly `.trim()` every value to fix data; doing so can alter hashes/signatures or business content.

---

## 17. JSON Type Metadata: Why Does the CLI See @class While Java Does Not?

A generic JSON serializer may store Java type information in order to deserialize polymorphic objects.

Example value:

```json
{
  "@class": "com.example.catalog.ProductDto",
  "id": "p-42",
  "name": "Laptop"
}
```

The CLI sees this entire JSON; the Java deserializer can reconstruct `ProductDto`.

### 17.1. Metadata Is Not a Business Field

`@class` or type hints may be serializer metadata. Do not return raw Redis JSON directly in a public API if it contains internal package/class names or metadata outside the API contract.

### 17.2. Changing a Java Package Can Make Old Data Unreadable

If a class moves:

```text
com.example.catalog.ProductDto
    ->
com.example.product.ProductDto
```

an old JSON type hint may point to a class that no longer exists.

As a result, Java fails to read it even though the JSON in the CLI is still valid.

### 17.3. Do Not Fix This by Enabling Uncontrolled Default Typing

Deserializing polymorphic types from untrusted data can create security vulnerabilities. Prefer:

- A stable DTO schema.
- Explicit type mapping.
- Allowlists/validators for polymorphic types.
- A versioned data format.
- Reader-side migration for old type hints.

Do not treat arbitrary Java class names from Redis as instructions to instantiate objects if the data can be influenced by untrusted parties.

---

## 18. Compression/Encryption Makes Values Look Different Even When Serializer Logic Is Correct

An application may use a pipeline:

```text
ProductDto
    |
    v
JSON serialize
    |
    v
gzip compress
    |
    v
encrypt
    |
    v
Redis SET bytes
```

Then:

```redis
GET product:42
```

returns binary ciphertext, not JSON.

Java reading path:

```text
Redis bytes
    |
    v
decrypt
    |
    v
decompress
    |
    v
JSON deserialize
    |
    v
ProductDto
```

### 18.1. Why Can't You Just Run CLI GET and JSON.parse?

Because the Redis value is **post-compression/post-encryption**. The CLI lacks the decryption key, algorithm, nonce, version header, or schema.

### 18.2. Do Not Log Plaintext for Debugging

If you must verify the codec:

- Use fake data in a test environment.
- Compare byte lengths, codec versions, and round-trip assertions.
- Use test vectors without real secrets.
- Never write encryption keys or production plaintext to logs.
- Never post ciphertext that may contain sensitive data to public forums or tickets.

### 18.3. Encryption and Cache Keys

If the application also encrypts keys, the CLI cannot look them up using a UTF-8 logical key. Furthermore, key encryption can affect deterministic lookup and Cluster routing, so you must understand the custom key codec's contract.

---

## 19. Redis `DUMP` Is Not a Java Serializer

Redis provides the command:

```redis
DUMP key
```

which returns an internal binary serialized representation of the **Redis value** (related to the RDB mechanism), usable with corresponding Redis commands/tools under applicable conditions.

Do not confuse:

```text
Redis DUMP serialization
    !=
Java JdkSerializationRedisSerializer
```

Even when a Redis String holds plain text `"hello"`, the output of `DUMP` is a Redis binary format, not the ASCII bytes of `"hello"`.

Therefore, to determine the bytes Spring wrote as a Redis String value, use a raw `GET` through a Redis connection; **do not run DUMP and expect the original serializer payload**.

### 19.1. DUMP/RESTORE May Be Version-Dependent

When migrating across Redis Server versions, check the official documentation for Redis serialization format and compatibility. It also does not replace migrating your application's JSON/JDK schemas.

### 19.2. Be Careful When Sharing DUMP Output

A Redis DUMP can contain the entire value, including sensitive information. Binary does not mean safe to attach to a ticket.

---

## 20. RedisConnectionFactory: Where the Connection Context Is Defined

A Spring Data Redis client goes through:

```java
RedisConnectionFactory
```

with an appropriate implementation such as `LettuceConnectionFactory` or `JedisConnectionFactory`.

You need to verify:

```text
Host/port
Standalone/Sentinel/Cluster
Database index if standalone
TLS
ACL user
Read-from setting/replica reads if applicable
Timeout
Client connection identity
```

A `StringRedisTemplate` and a `RedisTemplate` can use **two different connection factories** if the project declares custom beans.

Therefore:

```java
redisTemplate.getConnectionFactory()
```

is a clue for verifying wiring. However, do not print the entire configuration object if `toString()` could expose secrets or sensitive endpoints.

### 20.1. Boot Auto-Configuration and Bean Overrides

Spring Boot may create a default template via auto-configuration, but a custom bean with a matching name/type can replace it or add another template.

If a service receives an injected bean with a qualifier:

```java
@Qualifier("secondaryRedisTemplate")
```

it may access a different Redis instance than the bean the operator assumes is the default.

### 20.2. Inspecting the Actual Bean

In test code (without logging secrets), inspect:

```text
Bean name
Template class
ConnectionFactory class
Serializer class
CacheManager class
```

Then compare them against the application's active configuration.

Do not infer everything from `application.yml` alone when the project has profiles, environment variables, a config server, and custom bean definitions.

---

## 21. Distinguishing Read Discrepancies Caused by Concurrency

Even when:

```text
Same key bytes
Same Redis instance
Same Redis type
Same serializer
```

two reads can still yield different values if the data changed in between:

```text
t0: Java GET -> status=PENDING
t1: Writer SET -> status=PAID
t2: redis-cli GET -> status=PAID
```

Avoid spending hours debugging JSON serializers when read/write timing differs.

### 21.1. Discrepancies Caused by TTL

```text
t0: app reads key
t1: key expires
t2: CLI GET returns nil
```

If a key has a short TTL, a difference of just a few seconds can produce two different observations.

### 21.2. Discrepancies Caused by Key Recreation

A key that is `DEL`eted and `SET` again has a new value. Even though the key name stays the same, the content and TTL can change.

### 21.3. Transaction/pipeline

A `RedisTemplate` participating in a Redis transaction may queue commands until `EXEC`; the return value at the moment code invokes a method can have different semantics than a call outside a transaction. Do not blame every `null` inside a transaction on the serializer.

### 21.4. Local Cache and Framework Cache

If the application adds Caffeine/local caching in front of Redis, a Java method may return data from the local cache without hitting Redis. The CLI inspects live Redis; the two results can differ due to multi-level caching.

Identify the **actual application read path**, not just a field named `redisTemplate`.

---

## 22. Step-by-Step Diagnostic Procedure Without Modifying Data

When a user reports:

> "In redis-cli I see X, but Java returns Y."

Follow this sequence.

### Step 1 — Record the exact symptom

For example:

```text
Java code path:
    productCache.get("p-42")

Java result:
    ProductDto(...)

CLI:
    GET product:p-42 -> nil
```

Distinguish between `(nil)`, `WRONGTYPE`, binary output, JSON with a different schema, or a Java exception.

### Step 2 — Verify the connection target

Identify:

```text
Redis instance/endpoint
Logical DB
Cluster/Sentinel topology
Read-from primary/replica
Environment/profile
TLS/auth user
```

Do not share passwords in reports.

### Step 3 — Identify the abstraction

Which is in use:

```text
StringRedisTemplate?
RedisTemplate<K,V>?
ReactiveRedisTemplate?
Spring Cache RedisCacheManager?
Redis Repository?
Low-level RedisConnection?
Custom codec?
```

### Step 4 — Obtain the actual key expression

Check:

```text
Key generator
Cache name/prefix
Repository keyspace
Tenant prefix
Hash tag
Schema/version prefix
```

**Do not guess the key from the method name.**

### Step 5 — Inspect the serializer for each position

```text
Key serializer
Value serializer
Hash key serializer
Hash value serializer
Cache key/value serialization
Repository converter
Reactive SerializationContext
```

### Step 6 — Compare key bytes, not just key Strings

Take a fake logical key and run the actual serializer in a test:

```text
expected raw bytes
actual bytes sent to Redis
```

If authorized and using the right key type, use a low-level callback to query the corresponding raw bytes.

### Step 7 — Check Redis TYPE

```redis
TYPE <safe-test-key>
```

Choose `GET`/`HGETALL`/`LRANGE`/... matching the exact type.

### Step 8 — Check TTL and current existence

```redis
EXISTS <safe-test-key>
TTL <safe-test-key>
```

If the key does not exist or has expired, you cannot draw conclusions about the value serializer from it.

### Step 9 — Separate raw byte retrieval from decoding

In a test:

```text
Redis has raw value bytes?
    |
    +-- No -> check key/DB/TTL/host/race.
    |
    +-- Yes -> try the writer's exact deserializer.
                  |
                  +-- Succeeds -> CLI display differs due to format.
                  |
                  +-- Fails -> serializer/schema/version mismatch.
```

### Step 10 — Inspect older writer configurations and versions

A key may have been created by an older writer version while a newer version changed the serializer.

Find:

```text
Writer artifact version
Serializer version/config
Java class/schema
Data format header/version
ObjectMapper settings
```

### Step 11 — Plan the least invasive solution

If it is only unusual CLI display during debugging: **no data modification is needed**.

If the cache data is rebuildable and you want to change the format: use a versioned namespace / cold-cache plan.

If it is critical state: you need a controlled migration, rollback, and restore test.

### Step 12 — Write preventive integration tests

Test data written by the old writer -> decoded by the new reader; then deploy a canary and monitor serializer errors and cache hit rates.

---

## 23. Quick Diagnostic Decision Diagram

```text
Java and redis-cli show different results
               |
               v
     Same Redis endpoint/DB?
          /          \
         No          Yes
         |            |
    Fix context       v
                 CLI key has right bytes?
                    /         \
                   No         Yes
                   |           |
             Different key     v
             serializer/     TYPE key?
             prefix            |
                 +-------------+--------------+
                 |                            |
               string                        hash/...
                 |                            |
                 v                            v
           Value bytes?                 Use matching command
             /      \                   Hash serializers?
            No      Yes                       |
            |        |                        v
        TTL/race     Decode with writer serializer
        /eviction     |
                     +-------------------+
                     |                   |
                  Succeeds             Fails
                     |                   |
              CLI display differs   Schema/format/
              due to binary/JSON    version mismatch
```

This diagram is only a guide. Redis Cluster redirects, replicas, and multi-layer caches may require additional diagnostic steps.

---

## 24. Direct Verification with a Round-Trip Test

A test using `StringRedisTemplate`:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;

@SpringBootTest
class StringRedisRoundTripIT {

    @Autowired
    StringRedisTemplate redis;

    @Test
    void cliReadableStringRoundTrip() {
        String key = "lab:string:42";
        String expected = "Xin chào";

        redis.opsForValue().set(key, expected);

        assertThat(
            redis.opsForValue().get(key)
        ).isEqualTo(expected);
    }
}
```

In the test Redis on the right DB:

```redis
GET lab:string:42
```

The CLI should be able to read the text through a terminal with proper UTF-8 support.

### 24.1. A Round-Trip with the Same Serializer Is Not Enough

If both the writer and reader in the same test use a **serializer that mismatches the production contract**, the test will still pass.

You also need:

```text
Writer V1 -> Reader V2
Reader V1 -> Writer V2 if rollback is needed
CLI raw type/key format tests
CacheManager key prefix tests
Repository mapping tests
```

### 24.2. Testing Against a Real Redis Instance

Mocking `RedisTemplate` only proves Java mock logic. It does not verify actual written raw bytes, Redis types, TTL, Cluster routing, or real serializer behavior.

Use Testcontainers or a dedicated Redis integration environment.

---

## 25. An Example Reading JSON with StringRedisTemplate and an Explicit Data Contract

If you want `redis-cli` to read JSON directly and the app only stores DTOs belonging to a controlled schema, you can use `StringRedisTemplate` together with Jackson `ObjectMapper`.

```java
package com.example.product;

import java.time.Duration;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductJsonCache {

    private final StringRedisTemplate redis;
    private final ObjectMapper objectMapper;

    public ProductJsonCache(
            StringRedisTemplate redis,
            ObjectMapper objectMapper) {
        this.redis = redis;
        this.objectMapper = objectMapper;
    }

    public void put(ProductDto product)
            throws JsonProcessingException {

        String key = "product:v2:" + product.id();
        String json = objectMapper.writeValueAsString(product);

        redis.opsForValue().set(
            key,
            json,
            Duration.ofMinutes(10)
        );
    }

    public ProductDto get(String productId)
            throws JsonProcessingException {

        String key = "product:v2:" + productId;
        String json = redis.opsForValue().get(key);

        if (json == null) {
            return null;
        }

        return objectMapper.readValue(json, ProductDto.class);
    }

    public record ProductDto(
        String id,
        String name,
        long priceInCents
    ) {}
}
```

In test Redis:

```redis
GET product:v2:p-42
```

will return a JSON String formatted according to the `ObjectMapper` configuration, rather than JDK-serialized bytes.

### 25.1. Why Choose a v2 Namespace?

`product:v2:` separates the new JSON contract from keys that may have been stored with another serializer under the old prefix.

It does not migrate data automatically: the new app needs to reload from the source of truth on cache misses, or have a migration aligned with business requirements.

### 25.2. Does the DTO Contain Non-Public Data?

If the object has sensitive fields, readable JSON in the CLI also means anyone authorized to view Redis keys can read those contents. **Ease of debugging does not take precedence over security.**

If data protection is required, look into encryption, ACLs, key management, and minimizing cached fields. Do not pick String JSON solely to make terminal output look clear.

---

## 26. Generic JSON Serializer vs. Typed JSON Serializer

### 26.1. Generic

A generic serializer may include type metadata so it knows which class to instantiate when deserializing into `Object`.

Advantages:

- One template can store multiple object types.
- Can round-trip polymorphic data if configured compatibly.

Trade-offs:

- Metadata increases payload size.
- Class/package changes introduce migration risk.
- Polymorphic deserialization requires security hardening.
- Redis CLI displays "strange"-looking metadata.

### 26.2. Typed

A typed serializer knows the target class upfront:

```text
ProductDto
```

Advantages:

- May not need class-name type metadata in the payload.
- Clearer data contract.
- Easier schema versioning.

Trade-offs:

- Cannot arbitrarily store any type into the same serializer template.
- Still requires schema evolution management.
- Specific Java serializer APIs vary across Spring Data Redis/Jackson versions.

### 26.3. Do Not Accidentally Mix JSON from Multiple Serializers

Two serializers that both produce JSON do not necessarily share the same wire format:

```text
Serializer A:
    {"id":"42","name":"Alice"}

Serializer B:
    {"@class":"...","id":"42","name":"Alice"}

Serializer C:
    ["com.example.Person",{"id":"42","name":"Alice"}]
```

These are illustrative shapes. Do not assume which JSON format a library class produces without checking the actual serializer configuration.

### 26.4. Schema Version Is More Useful Than Guessing Classes from Format

You can use:

```json
{
  "schemaVersion": 2,
  "id": "p-42",
  "name": "Laptop"
}
```

A reader can select the decoder/migrator explicitly based on `schemaVersion`. If the data can be controlled by an untrusted source, validate the schema and avoid decoding into disallowed Java types.

---

## 27. ReactiveRedisTemplate Also Has a Serialization Context

In the reactive API:

```java
ReactiveRedisTemplate<K, V>
```

converting keys/values to bytes can rely on `RedisSerializationContext<K,V>`.

Do not assume:

```text
ReactiveStringRedisTemplate
    ==
ReactiveRedisTemplate<String,Object>
```

in terms of wire format.

### 27.1. ReactiveStringRedisTemplate

Typically serves String keys and String values, similar in purpose to `StringRedisTemplate`, except its API returns `Mono`/`Flux` rather than synchronous values.

### 27.2. When Debugging Reactive Code, Watch Out for Lazy Subscription

For example:

```java
Mono<String> result =
    reactiveStringRedisTemplate.opsForValue().get("lab:key");
```

Creating a `Mono` does not necessarily send the command immediately. If you check the CLI before the `Mono` is subscribed to, you may mistakenly think the app wrote or read it when the command has not executed yet.

A pipeline with `.retryWhen(...)` may also hit Redis again on error; distinguish retries from serializer mismatches.

### 27.3. Do Not Block the Event Loop to Inspect Data

Do not use `.block()` indiscriminately inside a WebFlux request thread for debugging. Depending on context, it can cause performance or deadlock issues.

Prefer integration tests or safe metadata logging within the reactive chain.

### 27.4. Codec Configuration Must Be Consistent

If a blocking template uses String/JSON while a reactive template uses String/JDK, accessing the same key can cause decode mismatches.

Ensure the serializers of both access paths share the same data contract whenever Redis keys must be shared.

---

## 28. Redis Streams: Field/Value Serializers Also Create Differences

An application can write a Stream record:

```text
XADD orders:events * eventId evt-1 type CREATED payload ...
```

`redis-cli XRANGE` shows raw Stream fields/values the CLI way, while Spring Data Redis mapping may create a `MapRecord` or `ObjectRecord` and deserialize the data into a Java object.

### 28.1. Do Not Assume StringRedisTemplate Serializers Apply to Stream Mappers

The Stream API has its own mapping/serialization mechanisms via `StreamOperations`, `StreamReceiver`, `StreamMessageListenerContainer`, and configured `RedisSerializer`/conversions.

You must identify:

```text
Stream key
Record ID
Field names
Field value bytes
Object mapping
Target Java type
```

### 28.2. A Stream Record Can Contain Hash-Style Fields

In Redis Streams, record fields/values are byte sequences with their own semantics. Do not assume the entire object sits inside a single JSON String field; a mapper may split an object across multiple fields.

If CLI `XRANGE` shows some binary fields, check the specific mapper/serializer.

### 28.3. A Consumer Error Does Not Prove Stream Data Is Corrupted

If producer V1 and consumer V2 use different schemas, the consumer may fail deserialization; the Stream entry still exists and can be read via a V1 decoder.

Do not `XDEL` or `XTRIM` production messages just because a new Java deserializer cannot understand them.

### 28.4. When the Schema Changes

Use:

```text
eventId
eventType
schemaVersion
payload
```

or an equivalent mapping contract, and maintain compatibility for as long as older records still need to be processed.

---

## 29. Pub/Sub: redis-cli Subscribe Sees Text While the Application Sees an Object or Vice Versa

CLI:

```redis
SUBSCRIBE lab:events
```

can receive a text payload from a Spring publisher. However, when the publisher serializes an object into binary, the CLI will see hard-to-read bytes.

In Spring:

```java
redisTemplate.convertAndSend(
    "lab:events",
    eventObject
);
```

how the message is serialized depends on the `RedisTemplate` and its configuration.

### 29.1. Channels and Payloads Also Have Serializers

If the publisher and subscriber use different channel/topic encodings, a situation like this can occur:

```text
Spring listener subscribed logical channel A
CLI SUBSCRIBE literal channel A
```

yet the actual bytes/formats do not match as expected.

Before blaming Pub/Sub, check the String topic/channel encoding and the message serializer.

### 29.2. Pub/Sub Does Not Store Message History

If the CLI subscribes after the publisher has already published, it will not receive older messages under standard Redis Pub/Sub. That is delivery semantics, not a serializer bug.

### 29.3. Do Not Use MONITOR to Dump Production Payloads

`MONITOR` can expose command arguments containing tokens or PII. To verify Pub/Sub activity, use publish/receive count metrics, listener health, and fake event IDs in a test environment rather than logging full message contents.

---

## 30. Common Java Errors When Serializers Are Incompatible

### 30.1. SerializationException

A common exception hierarchy in Spring Data Redis when data cannot be serialized or deserialized. Inspect the cause chain in an appropriately secured logging environment, avoiding dumping raw values.

### 30.2. StreamCorruptedException

Can occur when Java's `ObjectInputStream` reads bytes that do not match the expected Java serialization format.

For example, UTF-8 JSON starts with `{` whereas the Java deserializer expects a Java stream header.

### 30.3. InvalidClassException

Can be caused by an incompatible `serialVersionUID` or class schema in JDK serialization.

### 30.4. ClassNotFoundException

Can occur when old data references a Java class/package that no longer exists in the new runtime.

### 30.5. JsonMappingException / MismatchedInputException

Can happen when a JSON payload has a different shape/type than the target object or when custom mapper settings do not align.

### 30.6. ClassCastException

The deserializer returns a `Map` or an object of another class that the code tries to cast, for example:

```java
ProductDto product =
    (ProductDto) template.opsForValue().get(key);
```

If it actually returns a `LinkedHashMap`, casting fails.

### 30.7. WRONGTYPE

A Redis error when the command type does not match, such as `GET` on a Hash. This is not a Java object deserialization exception, even though Spring Data Redis may ultimately wrap it into a Java exception.

### 30.8. NPE Due to null

If the key bytes do not exist, Spring may return `null`; calling a method on `null` triggers a `NullPointerException`.

Distinguish between:

```text
Missing key
    !=
Value serialized null marker
    !=
Deserialization error
```

Do not treat an NPE as proof of a broken serializer without first checking raw key presence.

---

## 31. Serializers Can Change After an Application Upgrade

A service has been running for months:

```text
App v1 -> JDK serializer
```

and then deploys:

```text
App v2 -> JSON serializer
```

Redis still retains old keys/values until they are overwritten or their TTL expires.

Mixed data scenario:

```text
product:1 -> JDK bytes
product:2 -> JSON bytes
product:3 -> JDK bytes
product:4 -> JSON bytes
```

Without a format discriminator or namespace, the new code struggles to know which key needs which decoder.

### 31.1. Do Not Equate Upgrading a Dependency with Automatic Data Migration

A newer Spring Data Redis or driver release does not automatically convert all old JDK-serialized values into JSON.

You need:

- A backward-compatible reader.
- Schema versioning.
- Versioned namespaces.
- Checkpointed batch migration.
- Cache invalidation when data is rebuildable.
- Write freeze/reconciliation if the data is a source of truth.

### 31.2. Can the Old App Read New Data?

Rolling the app back to v1 after v2 has written JSON may fail if v1 only understands JDK bytes.

Therefore, a migration plan must consider:

```text
V1 reads V1
V2 reads V1
V2 writes V2
V1 reads V2 (if rollback is required)
```

Do not just verify "v2 can read v1" and assume rollback is safe.

### 31.3. Avoid Changing Key Bytes in the Same Step If Unnecessary

When changing both the key serializer and the value serializer at once, if the CLI returns nil it is hard to tell if the issue is the key, and if Java fails to read it is hard to tell if the issue is the value.

Design migrations in clear phases, separating data format boundaries.

---

## 32. Versioned Namespaces for Rebuildable Caches

For a cache whose source of truth is a database, a safe approach is:

```text
products:v1::<id>  -> old serializer
products:v2::<id>  -> new serializer
```

Procedure:

1. The new app only reads/writes v2.
2. On a v2 miss, load from the database.
3. The old app continues using v1 during the transition period.
4. Canary checks serializer behavior and business behavior.
5. Prewarm hot keys or manage cache stampedes.
6. Clean up v1 keys according to TTL/retention policy.
7. Rolling back to the old app can still use v1 within the allowed window.

### 32.1. Cold Cache Risk

If 1 million cache entries switch to a new namespace:

```text
V2 starts with 0 cached keys.
```

The application may push heavy load back onto the database. Measure:

```text
Cache hit/miss
Database QPS
HTTP p95/p99
Redis command rate
Memory usage
TTL distribution
```

### 32.2. Do Not Apply to Non-Rebuildable State

Sessions, inventory reservations, queue/Stream messages, business counters, or token revocations may not be rebuildable from another database.

Do not delete those namespaces simply because the CLI displays binary.

---

## 33. In-Place Migration for Critical Data

If you must change serializers for non-rebuildable data:

### Step 1 — Identify the old contract

```text
Old key bytes
Old value bytes/codec
Data types
TTL
Secondary indexes
Schema/classes
Writer versions
```

### Step 2 — Prepare a backup and restore test

The backup must be restorable in an isolated environment. Having an RDB/AOF file on disk is not enough to prove the application can read the data after restore.

### Step 3 — Group keys by category

For example:

```text
String JSON
String JDK bytes
Hash field values
Repository entities/indexes
Streams
Session/counters
```

### Step 4 — Design a reader for both formats

Use an explicit version marker or keyspace version. Avoid "try JDK, and if it fails try JSON" on arbitrary data without controls, as it carries security and misdiagnosis risks.

### Step 5 — Handle concurrent writes

A job doing:

```text
GET old bytes
Decode
SET new bytes
```

can overwrite newer updates from the application during migration. You need a CAS/versioning strategy, write pauses, atomic Lua scripts on the same key/slot, or reconciliation tailored to the data.

### Step 6 — Preserve TTL

Do not reset session/OTP deadlines by granting a fresh, longer TTL. You may need to store absolute deadlines or compute `PTTL` safely while accounting for races and expiration between steps.

### Step 7 — Validate with the new app

Compare:

```text
Counts
Types
TTL
Sample decoded objects
Business invariants
Indexes
Stream positions/ACK states
```

### Step 8 — Canary and rollback

Only expand traffic when the new reader produces zero decode errors; decide before starting whether the old app needs to roll back onto the new format.

---

## 34. Issues When Using the Same Key Name for Multiple Data Types

Suppose an older team wrote:

```redis
SET order:42 "<serialized JSON>"
```

And a newer team writes:

```redis
HSET order:42 status PAID
```

A Redis key cannot be both a String and a Hash at the same time. `HSET` on a String causes `WRONGTYPE` until the key is replaced or deleted through a proper process.

A new implementation might try to "fix" this with:

```redis
DEL order:42
HSET order:42 status PAID
```

That **deletes old data** and can cause lost updates.

### 34.1. Changing a Redis Data Type Is a Migration

Use separate key namespaces:

```text
order:v1:42  -> String JSON
order:v2:42  -> Hash
```

or define a clear migration strategy. Do not treat String -> Hash as a simple Java serializer change.

### 34.2. Redis Repository and Custom Template Sharing a Namespace

If a Repository stores `people:42` as a Hash, a custom `RedisTemplate.opsForValue().set("people:42", ...)` can overwrite or change its type if the writer uses the same raw key bytes.

Segregate data-owning namespaces so abstractions do not accidentally share a key name with different Redis types.

---

## 35. Using Redis ACL/TLS Properly During Diagnostics

When comparing the app and CLI, do not temporarily disable TLS or use a public Redis admin password just to "GET quickly."

Some CLI errors:

```text
NOAUTH
NOPERM
TLS handshake failure
Connection refused
```

are access/network errors, not serializer issues.

### 35.1. Do Not Print Credentials in Shell History

If you need `redis-cli` in a protected environment, pass credentials according to approved secret management/runbook practices. Do not paste URLs containing passwords into tickets.

### 35.2. Read-Only Diagnostic User

A user granted read permission only on the necessary key families may suffice for `TYPE`, `GET`, `HGETALL`, and `TTL` depending on ACL policy, though command permissions and key patterns must be verified against your Redis version.

Do not grant `+@all` to work around a `NOPERM` error.

### 35.3. Log Only Metadata

Logs should include:

```text
operation
key family
serializer class
outcome
error class
value byte length (if permitted)
technical trace ID
```

Never log full keys/values, Java object `toString()`, passwords, or JWTs.

---

## 36. A Service with Two Different RedisTemplates: How to Inspect

Suppose the code is:

```java
@Service
public class CartService {

    private final RedisTemplate<String, Object> cartTemplate;

    public CartService(
            @Qualifier("cartRedisTemplate")
            RedisTemplate<String, Object> cartTemplate) {
        this.cartTemplate = cartTemplate;
    }
}
```

When debugging, you must inspect the `cartRedisTemplate` bean, not just a bean named `redisTemplate`.

### 36.1. Inspect the Serializer Class Name, Not the Payload

An internal diagnostic helper in tests:

```java
public static String serializerType(
        org.springframework.data.redis.serializer.RedisSerializer<?> s) {
    return s == null ? "<null>" : s.getClass().getName();
}
```

Then:

```java
System.out.println(
    serializerType(cartTemplate.getKeySerializer())
);
System.out.println(
    serializerType(cartTemplate.getValueSerializer())
);
System.out.println(
    serializerType(cartTemplate.getHashKeySerializer())
);
System.out.println(
    serializerType(cartTemplate.getHashValueSerializer())
);
```

This only checks the serializer class; actual behavior also depends on config/ObjectMapper/codec/version. Two instances of the same class can be configured differently.

### 36.2. Avoid Logging `toString()` of Serializer ObjectMapper Config

Some custom serializers hold references to mappers or keys. Do not blindly dump the whole bean/config object, as it may drag along secrets.

---

## 37. Errors Caused by Different Serialization Versions Without Changing the Serializer Class

Both environments use a Jackson serializer, yet:

```text
Old:
    ObjectMapper A

New:
    ObjectMapper B
```

differ in:

- Naming strategy.
- Enum representation.
- Date/time module.
- Type metadata rules.
- Unknown property handling.
- Polymorphic validator.
- Null/default inclusion.
- JSON escaping.
- Custom modules.

As a result, the CLI still sees JSON, but Java may deserialize it differently.

### 37.1. Test Round-Trip with Old Bytes

A test should keep representative byte fixtures generated by the old app:

```text
old-value.json
old-value.bin
old-key-bytes
```

with scrubbed fake data. The new reader must pass before rollout.

### 37.2. Verify Golden Files

Instead of only asserting:

```java
deserialize(serialize(object)).equals(object)
```

verify the **wire format**:

```text
serialize V2 according to contract
deserialize V1 fixture
```

Because a buggy serializer used for both reading and writing can still round-trip with itself while being incompatible with production data.

### 37.3. Null/Missing Fields

Fields absent in old JSON may be interpreted by new code as `null`, `0`, or a default. This is a semantic schema issue, not just an exception.

Verify business invariants of the object after deserialization, not merely "no exception thrown."

---

## 38. Inspecting Raw Bytes Safely: Distinguishing Previews from Size Measurement

If you need to inspect the format, you can do:

```java
byte[] serialized =
    serializer.serialize(testObject);

int byteCount = serialized.length;
```

In production, prefer logging:

```text
serializer name
payload bytes
schemaVersion
outcome
```

In a lab with fake data, you can inspect:

```java
HexFormat.of().formatHex(serialized)
```

**Never print hex bytes of real tokens, sessions, or user data.** Hex is neither encryption nor redaction.

### 38.1. Why Not Use MONITOR for Every Serializer Issue?

MONITOR can expose key/value arguments from many other services, create overhead, and leak sensitive data. Many questions can already be answered with:

- Serializer class/config in Spring.
- Unit tests serializing keys/values.
- Low-level reads in a Redis lab.
- `TYPE`, `TTL`, `STRLEN`, `HLEN`.
- Metadata logs and exception categories.

Use the smallest tool appropriate for the question.

---

## 39. Verifying Whether the Key Serializer Affects Redis Cluster Hash Slots

Redis Cluster computes the hash slot from the key bytes and hash tag (if valid).

For example, Java code intends to use:

```text
cart:{c-42}:items
cart:{c-42}:total
```

If the key serializer is String/UTF-8, both raw keys preserve `{c-42}` and usually hash to the same slot.

If the key serializer is JDK serialization, the raw bytes may have a binary prefix and framing. The tag syntax Redis sees at the byte level may differ from the developer's intent; you must check **raw bytes and `CLUSTER KEYSLOT` on actual keys**, not just the Java String.

### 39.1. Two Different Issues

```text
CLI does not see the key:
    because key bytes differ.

CROSSSLOT:
    because multiple raw keys hash to different slots.
```

Both can appear after changing a serializer.

### 39.2. Do Not Solve This by Using a Single Global Hash Tag

Grouping all keys under `{global}` to avoid `CROSSSLOT` creates a hot slot and defeats Cluster distribution.

Design hash tags around aggregates that need atomic operations, and keep key serializer bytes stable.

### 39.3. Not Every Redis Client Encodes Keys the Same Way

A custom binary key codec can generate bytes that typing a literal string into `redis-cli` cannot reproduce. When you need to query an exact binary raw key, use a test adapter that shares the same codec rather than typing guesses.

---

## 40. Discrepancies Not Caused by Serializers That Are Easily Mistaken for One

### 40.1. Stale cache in JVM

A service reads a local cache, while the CLI reads the latest Redis data.

### 40.2. Replica read lag

Spring is configured for replica reads while the CLI queries the primary, or vice versa.

### 40.3. Pipeline/transaction

Commands do not execute until the transaction commits or the pipeline flushes per the API's semantics.

### 40.4. Connection/timeout

A write command may have executed while the reply was lost; the app retries or throws an error while the CLI sees the data.

### 40.5. Key expiration/eviction

A key exists when the app reads it, but disappears before CLI `GET`.

### 40.6. Tenant/environment prefix

The app uses `tenant:t-7:user:42`; the CLI queries `user:42`.

### 40.7. Redis modules

`JSON.GET` is only meaningful when the corresponding module/feature is present. A plain JSON String stored via `SET` does not automatically become a RedisJSON document.

### 40.8. Client-side compression

The CLI sees binary, not because Redis Server compressed the `SET` value automatically, but because the application or serializer compressed it.

### 40.9. Same logical key, different raw key bytes

Error caused by the key serializer, not the value.

### 40.10. Same raw bytes, different decoder

Error caused by the value serializer/schema/charset.

### 40.11. Different Redis data types

Error caused by using the wrong `GET`/`HGETALL` API, not something solved by just swapping a JSON mapper.

### 40.12. Same Redis key but changed between reads

Error caused by concurrency, TTL, or replica behavior, not by format.

---

## 41. Safe Serializer Rollout Procedure

### Before the Change

- Determine whether the data source is rebuildable or not.
- Inventory key families, Redis data types, and TTLs.
- Identify the Spring beans/serializers performing writes.
- Collect representative fake data from the old writer.
- Check serializer version and Java class/schema.
- Create a backup and test restore if the data is critical.
- Record baseline cache hit rates and deserialization errors.
- Build integration tests for old writer -> new reader.
- Decide whether a rolled-back app must read new writes.

### During the Change

- Use a versioned namespace or a planned dual-reader.
- Do not overwrite old data if the old app cannot read the new format yet.
- Preserve TTL/deadline semantics.
- Limit canary writers and cold-cache load.
- Monitor `SerializationException`, `WRONGTYPE`, and `ClassCastException`.
- Do not run `FLUSHALL` to fix format errors.
- For Redis Cluster, verify hash slots/routing.
- For Streams/Repositories, verify mapping and indexes.

### After the Change

- Verify old data is readable or migrated.
- Verify new data is written under the right contract.
- Compare cache hit/miss, p99 latency, and database load.
- Check TTL, keyspace count, and memory.
- Verify recovery and rollback paths.
- Clean up old keys only once retention/correctness criteria are met.
- Document migration version, deployment date, and test results.

---

## 42. Exercise 1 — StringRedisTemplate and redis-cli

In an isolated test Redis:

```java
stringRedisTemplate.opsForValue().set(
    "lab:hello",
    "Xin chào Redis"
);
```

Run the CLI against the right host/DB:

```redis
TYPE lab:hello
GET lab:hello
STRLEN lab:hello
TTL lab:hello
```

Explain:

1. Why `TYPE` returns `string`.
2. Why `GET` displays the text if the terminal supports UTF-8.
3. Why `STRLEN` counts bytes instead of Java characters.
4. What happens if the CLI uses a different DB?

---

## 43. Exercise 2 — JDK Key Serializer Causes CLI to Return nil

In a lab, create two templates:

```text
A: String key serializer
B: JDK key serializer
```

Both write the same logical key `"lab:user:42"` with different fake values.

Tasks:

1. Read in Java using A and B.
2. Run CLI `GET lab:user:42`.
3. Print the hexadecimal of the **fake key bytes** in a unit test.
4. Compare them with `Arrays.equals`.
5. Explain why Redis can hold two independent keys.
6. State why `redis-cli --raw` does not resolve a key mismatch.

Do not experiment on a production Redis instance containing real customer data.

---

## 44. Exercise 3 — JDK Value Serializer

Configure:

```text
Key serializer: String
Value serializer: JDK
```

Write a serializable `DemoUser` object to test Redis.

1. Run `TYPE` on the key.
2. Run `GET` on the key in the CLI.
3. Read it back with the right `RedisTemplate`.
4. Try reading it with `StringRedisTemplate` on the **same raw key** and record the issue.
5. Identify the meaning of the `AC ED 00 05` prefix bytes if seen.
6. Explain why Redis String does not mean Java String.

---

## 45. Exercise 4 — JSON with Type Hints

Use a generic JSON serializer in a Spring Data Redis version that supports it.

1. Write a fake `ProductDto`.
2. Use CLI `GET` to inspect the JSON.
3. Check whether type metadata is present.
4. Rename/move the Java class/package in a test environment.
5. Read the old entry back with the new app.
6. Design a schema/version strategy to avoid arbitrary coupling to Java class names.

Discuss the risk of enabling polymorphic deserialization without an allowlist.

---

## 46. Exercise 5 — Hash Serializers

Configure:

```text
Key: String
Hash field: JDK
Hash value: JSON
```

Write:

```java
template.opsForHash().put(
    "lab:hash:42",
    "displayName",
    "Alice"
);
```

Observe:

```redis
TYPE lab:hash:42
HGETALL lab:hash:42
HGET lab:hash:42 displayName
```

Explain why the literal field `displayName` may not match the serialized field bytes.

Then switch `hashKeySerializer` to String in a **new lab namespace**, without recklessly modifying old data, and compare the results.

---

## 47. Exercise 6 — WRONGTYPE and Repository

Create an entity with `@RedisHash` and save it using a Redis Repository in a lab.

1. Call `repository.save`.
2. Identify the Redis keyspace.
3. Run `TYPE`.
4. Try `GET` and record `WRONGTYPE` if it is a Redis Hash.
5. Run `HGETALL`.
6. Compare the Hash fields with the Java entity.
7. If `@Indexed` is present, inspect the secondary index keys.
8. Read it back with `repository.findById`.

Why is `RedisTemplate` value serializer not the sole answer for how a Repository stores an entity?

---

## 48. Exercise 7 — Spring Cache Key Prefix

Create a method:

```java
@Cacheable(cacheNames = "products", key = "#productId")
public ProductDto loadProduct(String productId) {
    return database.load(productId);
}
```

Tasks:

1. Create a cache entry via the app.
2. Determine the actual key prefix via configuration/tests.
3. Compare CLI `GET p-42` with `GET <actual-key>`.
4. Check type/TTL.
5. Identify the `CacheManager` value serializer.
6. Predict what happens if another app uses a JDK serializer to read a JSON value.
7. Propose a test to guard the cache key format.

---

## 49. Exercise 8 — Wrong Logical Database

On a **test** standalone Redis:

1. Write a key to DB 2.
2. `redis-cli` connects to DB 0 by default.
3. Run `GET` and observe `(nil)`.
4. Switch the CLI to DB 2.
5. Read the key again.
6. Compare with the actual serializer.

Explain why you must verify host/port/DB **before** blaming the serializer.

Do not apply the `SELECT 2` example to Redis Cluster.

---

## 50. Exercise 9 — Unicode and Bytes

Use these strings:

```text
hello
Hà Nội
Tiếng Việt
```

In Java:

```java
byte[] raw =
    new StringRedisSerializer().serialize(value);
```

Measure:

```text
String.length()
raw.length
```

Store with `StringRedisTemplate` and read with a CLI configured with proper UTF-8.

Explain why the numbers can differ and why a terminal using the wrong charset may display mojibake.

---

## 51. Exercise 10 — Old JSON Data, New Serializer

Create two test app versions:

```text
V1: JSON schemaVersion=1
V2: JSON schemaVersion=2
```

Steps:

1. V1 writes data.
2. V2 reads old data.
3. Add/remove a field with a default value.
4. Change an enum or date format in tests.
5. Verify schema compatibility.
6. If rollback is needed, test V1 reading values written by V2.
7. Propose expand-and-contract or a versioned namespace.

Do not only assert that deserialization throws no error; verify that business data is semantically accurate.

---

## 52. Exercise 11 — Compression and Binary Redis String

In a test:

1. Create sample JSON.
2. Compress the JSON using an explicit codec.
3. Store the compressed bytes with an appropriately configured `RedisTemplate`.
4. Run CLI `TYPE` and `GET` in the test environment.
5. Use the application codec to decompress + decode.
6. Measure payload bytes before and after compression.
7. Do not log real raw bytes or keys.

Explain why you cannot look at `GET` in text form and conclude the data is corrupted.

---

## 53. Exercise 12 — Redis Cluster Hash Slot and Key Serializer

In a test Redis Cluster:

1. Create two logical keys sharing the hash tag `{cart-42}`.
2. Serialize them with `StringRedisSerializer`.
3. Inspect the bytes in a unit test.
4. Cross-check `CLUSTER KEYSLOT` with the actual key bytes.
5. Repeat the experiment with a different key serializer in a test namespace.
6. Check whether multi-key scripts/transactions are still same-slot.
7. Explain why changing a key serializer can affect both key lookup and routing.

---

## 54. Exercise 13 — Do Not Log Sensitive Data

Create a **fake** DTO:

```java
record DemoSession(
    String userId,
    String fakeToken
) {}
```

Instead of:

```java
log.debug("Redis session={}", session);
```

log:

```text
operation=session-cache-write
serializer=JSON
payloadByteBucket=1-4KiB
result=success
```

Discuss:

- Why is a hex-encoded raw payload not redaction?
- Why can a Redis key name also contain PII?
- Why shouldn't you run `MONITOR` across all of production just to find a serializer mismatch?
- Can you inspect the serializer class and byte length without logging the value?

---

## 55. Exercise 14 — Build a Diagnostic Decision Tree

Given the scenario:

```text
App:
    repository.findById("42") returns a valid Person.

CLI:
    GET people:42 -> WRONGTYPE.
```

Write a procedure:

1. Verify endpoint/DB.
2. Distinguish Repository vs `RedisTemplate`.
3. Check `TYPE`.
4. Use `HGETALL` if it is a Hash.
5. Identify custom converters.
6. Identify metadata/index keys.
7. Cross-check the Java object against fields via the mapping.
8. Use only fake or approved data.

Which conclusion is more reasonable: Redis has a bug, or the CLI used a command incompatible with the Redis type?

---

## 56. Exercise 15 — Distinguish Key Mismatch and Value Mismatch

Create three test cases:

```text
Case A:
    Key writer = JDK
    Value writer = JDK

Case B:
    Key writer = String
    Value writer = JDK

Case C:
    Key writer = String
    Value writer = JSON
```

For each case:

1. Run CLI `GET` using the literal String key.
2. Check whether the CLI finds the key.
3. If found, determine whether the value is text or binary.
4. Read it with the writer's serializer.
5. Read it with a mismatched serializer.
6. Record the resulting differences in exceptions/results.

Use a table to distinguish **key addressability** from **value decodability**.

---

## 57. Exercise 16 — Integration Test to Guard Against Upgrade Failures

Given a system using Spring Cache and Redis Repository.

Design a CI matrix:

```text
Old app writes -> New app reads
New app writes -> Old app reads (if rollback is needed)
String key bytes stable?
Cache key prefix stable?
Repository Hash mapping stable?
TTL/deadline preserved?
Indexed queries still correct?
No deserialization exceptions?
```

Use Redis Testcontainers or an equivalent integration environment with pinned versions. Use fake fixtures; never copy raw user/session data into the repository.

---

## 58. Common Misconceptions

### "GET returning nil means Redis has no data"

Not necessarily. The CLI may be using a different endpoint, DB, prefix, or raw key bytes.

### "Switching to redis-cli --raw lets you read Java objects"

No. `--raw` changes how bytes are printed; it does not run a Java serializer.

### "TYPE string means the value is text"

No. A Redis String can hold arbitrary binary bytes.

### "I use RedisTemplate<String,Object> so the key is definitely UTF-8"

No. The Java generic type does not determine the Redis key serializer.

### "I see JSON in the CLI so Java can definitely deserialize it"

No. Java might be using a JDK decoder, a different schema, or incompatible type metadata.

### "JSON containing @class means corrupted data"

Not necessarily. That may be metadata used for generic JSON serialization.

### "Just changing valueSerializer fixes everything"

Not if key bytes, hash field serializers, `CacheManager`, or Repository converters differ.

### "StringRedisTemplate and RedisTemplate always see the same key identically"

Not if they use different key serializers.

### "GET on a Repository entity returning WRONGTYPE means the serializer is broken"

No. A Redis Repository may store the entity as a Hash.

### "Changing keySerializer does not affect old data"

False. Changing key bytes can make the app unable to find previously written keys.

### "Changing the JSON serializer makes Redis migrate the data automatically"

No. Redis keeps the existing bytes until the data is rewritten or migrated.

### "If V1 reads V2 data, rollback is definitely safe"

You must test V1 reader reading V2 writer if rollback is required.

### "A hex string is non-sensitive because it is hard to read"

False. Hex is a reversible representation of bytes.

### "MONITOR is the only way to know what key Redis receives"

No. You can inspect the serializer, key generator, and raw bytes in a lab; `MONITOR` carries performance and security risks.

### "FLUSHALL is the fastest way to fix a serializer error"

No. It deletes Redis data and can cause unrecoverable loss of state.

### "Same Java key name means same Cluster hash slot"

Not if serializers produce different raw bytes. Cluster computes the slot from the actual Redis key bytes.

### "Once Spring Boot is upgraded and PING succeeds, all data is readable"

No. You must test old data, caches, repositories, streams, JSON/JDK codecs, and TTLs.

---

## 59. Diagnostic Checklist for Real Incidents

- [ ] Verified that the app and CLI are talking to the same Redis endpoint?
- [ ] Verified the logical DB (standalone) or Cluster topology?
- [ ] Are different primary/replica nodes being read, or is there replication lag?
- [ ] Identified the Spring abstraction (`StringRedisTemplate`, `RedisTemplate`, Cache, Repository, Reactive)?
- [ ] Identified the actual bean/qualifier and connection factory?
- [ ] Know the raw logical key, prefix, namespace, and `KeyGenerator`?
- [ ] Inspected the actual `keySerializer`?
- [ ] Inspected the actual `valueSerializer`?
- [ ] If Hash, inspected `hashKeySerializer` and `hashValueSerializer`?
- [ ] If Cache, inspected `RedisCacheConfiguration` serialization pairs?
- [ ] If Repository, inspected mapping converters and keyspace?
- [ ] Tried `TYPE`, `EXISTS`, `TTL` on the exact key bytes?
- [ ] Distinguished `(nil)`, `WRONGTYPE`, binary output, and decode exceptions?
- [ ] Checked whether the value just expired/was evicted or was modified by another writer?
- [ ] Compared serializer bytes in a test using fake data?
- [ ] Identified the old writer version and schema if the data pre-existed?
- [ ] Checked UTF-8/terminal display?
- [ ] Checked for compression/encryption/custom codecs?
- [ ] If Cluster, checked whether raw key bytes affect the hash tag/slot?
- [ ] Have an integration test for old writer -> new reader?
- [ ] Have a migration plan if changing serializers?
- [ ] Avoided `KEYS *`, `MONITOR`, or dumping secrets in production?
- [ ] Avoided deleting Redis keys/data before understanding the data type and recovery source?
- [ ] Report contents include only metadata and authorized data?

---

## 60. Self-Assessment Questions

1. How does Redis store a Java object?
2. Does Redis `TYPE string` mean the value is UTF-8?
3. How does `StringRedisSerializer` differ from `JdkSerializationRedisSerializer`?
4. Why can a `RedisTemplate` using a JDK key serializer cause CLI `GET user:42` to return nil?
5. What does `redis-cli --raw` affect, and what does it not affect?
6. When the CLI displays `AC ED 00 05`, which format should come to mind?
7. Why is that header alone not enough to prove the class/schema is readable?
8. What is the difference between a key serializer and a value serializer?
9. Which serializers does a Redis Hash require?
10. Why can `HGET user:42 displayName` return nil while Java reads the hash field successfully?
11. Does `WRONGTYPE` relate to Redis data types or a Java mapper?
12. Why can a Redis Repository entity usually not be read with `GET`?
13. Does Spring Cache necessarily use the `RedisTemplate` value serializer?
14. Why might a cache key be `products::42` instead of `42`?
15. Why can two `RedisTemplate` instances with the same generic types still produce different raw bytes?
16. If Java reads the data but the CLI cannot find the key, what steps should you check first?
17. If raw value bytes exist but deserialization fails, which causes should you investigate?
18. How can connecting to the wrong Redis DB produce symptoms similar to a serializer mismatch?
19. Does Redis Cluster support multiple logical DBs like standalone Redis?
20. Does changing the key serializer affect hash slots?
21. Why is `String.length()` not equal to payload bytes?
22. When does JSON include type metadata, and what risk does it pose when renaming a Java package?
23. Why must you test data written by older application versions?
24. Why is a round-trip test using the same serializer not sufficient?
25. How do you distinguish a cache that can be cleared from state that cannot be rebuilt?
26. Should you run `FLUSHDB` after just changing the JSON format?
27. How does RDB `DUMP` differ from JDK serialization?
28. Why is a hex payload not considered masked/hidden data?
29. How can you verify a Redis Hash value without logging raw PII?
30. If Java and the CLI read the same raw key at two different times, what non-serializer factors can produce different results?
31. Can Reactive Redis have not sent a command yet when it has not been subscribed to?
32. What kind of regression tests should a sound diagnostic runbook end with?

## 61. Key Takeaways

- **Redis stores bytes, not Java objects.** `redis-cli` displays response bytes while Spring Data Redis serializes/deserializes according to Java configuration.
- **A logical key String does not necessarily equal raw Redis key bytes.** Different key serializers can produce two independent keys, causing CLI `(nil)` even when Java can read it.
- **Distinguish the key serializer from the value serializer.** Key mismatch causes key-not-found; value mismatch causes unreadable binary or deserialization errors.
- **Redis `TYPE string` does not mean the value is text.** Java JDK-serialized bytes, JSON, Protobuf, and encrypted/compressed bytes can all live inside a Redis String.
- **`--raw` does not fix the key serializer and does not decode Java objects.** It only changes how the CLI formats output.
- **Hashes have separate serializers for fields and field values.** `opsForHash`/Repositories do not map to a `GET` String.
- **Spring Cache uses CacheManager serialization pairs and key prefixes**, which can differ from `RedisTemplate`; Redis Repositories use mapping converters that can store Hashes and index metadata.
- **Verify the right key bytes, right Redis type, and right DB/node** before concluding data is corrupted.
- **JSON that looks valid in the CLI can still fail to decode into a Java class**, especially with type metadata, schema migrations, and `ObjectMapper` settings.
- **Do not change a serializer in production as if changing a display format.** It is a data contract change; it requires old-data fixtures, integration tests, and a migration/rollback plan.
- **A serializer round-trip with itself does not prove backward compatibility** with old data or other applications.
- **Redis Cluster assigns slots by raw key bytes**; changing the key serializer can break key lookup, alter routing, or break multi-key same-slot behavior.
- **Do not use `FLUSHALL`, raw MONITOR, or log binary secrets to debug.** Prefer metadata, Redis `TYPE`/TTL, serializer byte tests with fake data, and structured diagnostics.
- **Always rule out non-serializer causes:** wrong endpoint/DB, cache prefix, TTL, eviction, replica lag, concurrency, transactions, and local caches.
- **Accurate diagnosis means verifying the Java object <-> byte[] <-> Redis data structure transformation path**, and writing tests to protect that contract.

### Official References

- [Spring Data Redis — Serializers](https://docs.spring.io/spring-data/redis/reference/redis/serializers.html)
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html)
- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html)
- [Spring Data Redis — Object-to-Hash Mapping](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/mapping.html)
- [Spring Data Redis — Reactive Redis](https://docs.spring.io/spring-data/redis/reference/redis/reactive.html)
- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html)
- [Spring Data Redis — Pub/Sub](https://docs.spring.io/spring-data/redis/reference/redis/pubsub.html)
- [Spring Data Redis — Redis Cluster](https://docs.spring.io/spring-data/redis/reference/redis/cluster.html)
- [Redis — Data types](https://redis.io/docs/latest/develop/data-types/)
- [Redis — GET](https://redis.io/docs/latest/commands/get/)
- [Redis — TYPE](https://redis.io/docs/latest/commands/type/)
- [Redis — HGETALL](https://redis.io/docs/latest/commands/hgetall/)
- [Redis — SCAN](https://redis.io/docs/latest/commands/scan/)
- [Redis — TTL](https://redis.io/docs/latest/commands/ttl/)
- [Redis — STRLEN](https://redis.io/docs/latest/commands/strlen/)
- [Redis — DUMP](https://redis.io/docs/latest/commands/dump/)
- [Redis — MEMORY USAGE](https://redis.io/docs/latest/commands/memory-usage/)
- [Redis — CLUSTER KEYSLOT](https://redis.io/docs/latest/commands/cluster-keyslot/)
- [Redis — redis-cli](https://redis.io/docs/latest/develop/tools/cli/)
- [Redis — Security](https://redis.io/docs/latest/operate/oss_and_stack/management/security/)
- [Spring Boot — Data Redis](https://docs.spring.io/spring-boot/reference/data/nosql.html)
- [Jackson — Documentation](https://github.com/FasterXML/jackson-docs)
