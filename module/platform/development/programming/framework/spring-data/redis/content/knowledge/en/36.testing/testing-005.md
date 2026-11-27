# Testing Templates, Serializers, and Cross-Reading Data in Spring Data Redis

A Spring Data Redis application can write and read back data successfully using the same `RedisTemplate`, yet still fail when another service reads the same key with `StringRedisTemplate`, a newer application version, Redis CLI, or a client written in another language. The root cause usually lies not in the Redis server itself, but in **how Java objects, keys, hash fields, and values are converted into bytes**.

For example, two templates both see the logical string `"customer:42"`, yet one uses `StringRedisSerializer` while the other uses `JdkSerializationRedisSerializer`. Redis receives **two distinct byte sequences** as key names. Each template reading back its own data succeeds, while the other template sees a missing key. If the keys match but the value serializers differ, the result can be JSON rendered as a raw string, a deserialization failure, or a value of the wrong type.

Therefore, Spring Data Redis tests must verify the **storage contract**, not merely check that a Java call returns the right object:

1. Correct **Redis key bytes** and physical key name.
2. Correct **Redis data type**: String, Hash, List, Set, Sorted Set, Stream, and so on.
3. Correct **value bytes** and encoding format.
4. Correct **serializer/deserializer** on every read and write path.
5. Correct **schema/version**, charset, TTL, and legacy data handling rules.
6. Successful cross-reading between components designed to share data; controlled failure for incompatible combinations.

This lesson builds a testing strategy using JUnit 5, Spring Boot, Testcontainers, Redis CLI, and Spring Data Redis templates. The Java examples target **Spring Boot 3.x / Spring Data Redis 3.x / Java 17**. When using Spring Boot 4.x or another version, verify serializer APIs and dependencies against your actual BOM.

## 1. Redis Stores Bytes Only; It Has No Concept of Java Objects

When calling:

```java
redisTemplate.opsForValue().set("customer:42", customer);
```

the basic flow is:

```text
Java:
  key   = "customer:42"
  value = new CustomerProfile("42", "An", 120)
              |
              v
      RedisTemplate serializers
              |
       +------+------+
       |             |
       v             v
  key byte[]     value byte[]
       |             |
       +------+------+
              |
              v
         Redis command
       SET <key bytes> <value bytes>
              |
              v
       Redis stores data
```

Redis does not receive a `CustomerProfile` or a `String` in the Java sense. Redis receives key and value as raw byte arrays formatted by the serializers. Consequently:

- A key name logged by the application may not match the actual bytes stored by Redis.
- `GET` in Redis CLI returns raw data; it does not reconstruct Java objects.
- `StringRedisTemplate` decodes values as UTF-8 strings; it does not automatically parse JSON into DTOs.
- `RedisTemplate<String, CustomerProfile>` reads properly only if the bytes and schema match its configured serializer.
- Changing a serializer can change the **physical key**, making the application believe data was lost.

### 1.1. The Testing Contract Covers Four Transformations

```text
Write path:
 Java key   --KeySerializer------> Redis key bytes
 Java value --ValueSerializer----> Redis value bytes

Read path:
 Redis key bytes   <--KeySerializer-- Java key
 Redis value bytes --ValueSerializer--> Java value
```

Two parties sharing a Redis key must agree on **both the key serializer and the value format**. Testing only the value serializer without testing the key still leaves room for "data not found" bugs.

## 2. Which Templates Commonly Need Testing?

| API | Characteristics | Testing Question |
|---|---|---|
| `StringRedisTemplate` | String serializer for keys and values | Does it preserve Unicode and UTF-8 bytes? |
| `RedisTemplate<K,V>` | Configurable serializers, synchronous operations | Do keys/values/hashes match the wire format? |
| `ReactiveStringRedisTemplate` | Reactive API for String keys/values | Is the publisher subscribed, and are results/bytes compatible? |
| `ReactiveRedisTemplate<K,V>` | Reactive with serialization context | Does it share the same key/value format as the imperative template? |
| `RedisCacheManager` / Spring Cache | Dedicated key prefix, serializer, and cache entries | Is the cache readable across templates, and is TTL accurate? |
| Redis Repository | Mapping, entity keys, indexes, and auxiliary metadata | Do generated keys match expectations, and can Repositories read them after upgrades? |

**Never assume two APIs are compatible simply because they share a `RedisConnectionFactory`.** The connection factory manages connections; serializers are configured at the template, cache, or mapping layer.

### 2.1. Four Serializers to Keep Separate

`RedisTemplate` has:

```java
template.setKeySerializer(...);
template.setValueSerializer(...);
template.setHashKeySerializer(...);
template.setHashValueSerializer(...);
```

They do not serve the same role:

| Serializer | What Gets Converted to Bytes |
|---|---|
| Key serializer | Redis key name, e.g., `customer:42` |
| Value serializer | Values for String/List/Set/ZSet and related operations |
| Hash key serializer | **Field** inside a Redis Hash, e.g., `displayName` |
| Hash value serializer | Value of a hash field, e.g., `"An"` |

A very common bug is verifying `opsForValue()` works and assuming `opsForHash()` is compatible too. In practice, hash fields may be encoded completely differently.

## 3. Build a Compatibility Matrix Before Writing Tests

Suppose a system consists of:

- Service A using `StringRedisTemplate` to write strings.
- Service B using `RedisTemplate<String, CustomerProfile>` to write DTOs as JSON.
- Service C as a legacy version using Java native serialization.
- A Node.js script using a Redis client to read JSON.

Expected matrix:

| Writer | Reader | Expectation |
|---|---|---|
| String → String | `StringRedisTemplate` | Reads back exact Unicode |
| JSON DTO → JSON DTO | Same schema, same serializer | Compatible round-trip |
| JSON DTO → String | `StringRedisTemplate` | Receives **JSON string**, not DTO |
| Valid JSON string → JSON DTO | Typed JSON serializer | Readable if schema matches |
| Java native serialization → String | `StringRedisTemplate` | **Do not** expect a meaningful string |
| String key → JDK-serialized key | Differently configured template | Treated as **different keys** |
| String Hash fields → String Hash fields | Consistent serializers | Fields and values compatible |
| JSON v1 → JSON v2 | New version | Requires contract tests/migration |
| Key with TTL → Reading template | Same key, TTL remaining | Reading does not normally reset TTL |

Tests must express intentional data-sharing policies. Do not force every template to read every format. Sometimes the **right test verifies two formats are NOT compatible** and errors are handled cleanly.

## 4. When to Use Unit Tests, Integration Tests, and Contract Tests?

### 4.1. Unit Tests

Suitable for:

- Key-naming logic.
- Version/schema selection logic.
- Pure Java converters.
- Missing value handling, validation, and fallbacks.
- Testing serializers independently of a Redis server.

For instance, you can invoke `serialize`/`deserialize` directly to test bytes, Unicode, and nulls. Unit tests **cannot prove** the Redis server actually receives the right key, enforces TTL, or executes `HSET` properly.

### 4.2. Integration Tests with Real Redis

Needed for:

- `SET`/`GET`, `HSET`/`HGET`, TTL, Redis types.
- Cross-reading between two templates over the same physical Redis key.
- Comparing raw bytes with Redis CLI.
- Catching `WRONGTYPE` or serializer mismatches.
- Testing reactive subscriptions and serialization contexts.

A test Redis instance in **Testcontainers** is much more trustworthy than mocking `RedisTemplate`. Mocks only prove Java code invoked `set` with some object, not which bytes were written to Redis.

### 4.3. Contract Tests Across Services and Versions

Needed when:

- Multiple services in Java/Node/Python share a keyspace.
- Rolling updates run both v1 and v2 simultaneously.
- Changing serializers or upgrading Jackson.
- Reading legacy data after DTO modifications.

Contract tests keep a set of **stable byte/schema fixtures** produced by a deployed writer version and require the new reader to decode them accurately. If the new version only writes and reads its own output, both writer and reader can introduce the same bug while tests stay green.

## 5. Practice Environment: Spring Boot + Testcontainers

Gradle dependencies for a Spring Boot 3.x application:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis-reactive'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'org.testcontainers:junit-jupiter'
}
```

In some projects, the reactive and synchronous starters share overlapping dependencies; pick the starter matching your goal and keep `spring-data-redis`/Lettuce aligned with the BOM. Testcontainers versions must also be managed by a matching BOM or declared explicitly if the build lacks dependency management.

Testcontainers requires a working Docker/compatible container runtime on the test runner. The snippets below are **test templates to place in a project**; no Gradle or container commands are executed while writing this lesson.

### 5.1. Creating a Dedicated Redis Container for Tests

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@SpringBootTest
@Testcontainers
class RedisTemplateIntegrationTest {

    @Container
    static final GenericContainer<?> redis =
            new GenericContainer<>(
                    DockerImageName.parse("redis:7.4-alpine"))
                    .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", redis::getHost);
        registry.add("spring.data.redis.port",
                () -> redis.getMappedPort(6379));
    }

    @Test
    void contextLoads() {
        // Behavioral tests will be added in subsequent sections.
    }
}
```

This is a skeleton test class assuming the project has `@SpringBootApplication` and Spring Data Redis auto-configuration. The Redis image is a **pinned test version**, not an instruction to upgrade production to that version. In CI, pin images to an approved version/digest and upgrade test versions intentionally alongside production Redis.

### 5.2. Never Use Production Redis in Integration Tests

The test setup should:

1. Use a dedicated Redis container/instance.
2. Scope key names per test, such as `it:397:profile:...`.
3. Never run `FLUSHALL` on a shared server.
4. Clean up the exact keys created by each test.
5. Never depend on test execution order.
6. Never claim standalone Redis tests cover Cluster/Sentinel behavior.

If you need to test pipelining, Cluster routing, or failover, run a test Redis environment reflecting that **topology**. A single Redis container cannot catch `CROSSSLOT` errors.

## 6. Configuring `StringRedisTemplate` and a JSON `RedisTemplate`

Example model:

```java
package example.redis;

public record CustomerProfile(
        String id,
        String displayName,
        int loyaltyPoints) {
}
```

A dedicated template writing `CustomerProfile` as JSON:

```java
package example.redis;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration(proxyBeanMethods = false)
public class ProfileRedisConfiguration {

    @Bean("profileJsonTemplate")
    public RedisTemplate<String, CustomerProfile> profileJsonTemplate(
            RedisConnectionFactory connectionFactory) {

        RedisTemplate<String, CustomerProfile> template =
                new RedisTemplate<>();
        template.setConnectionFactory(connectionFactory);

        StringRedisSerializer strings = new StringRedisSerializer();
        Jackson2JsonRedisSerializer<CustomerProfile> profiles =
                new Jackson2JsonRedisSerializer<>(CustomerProfile.class);

        template.setKeySerializer(strings);
        template.setValueSerializer(profiles);

        // If using Hash, configure field and field-value intentionally.
        template.setHashKeySerializer(strings);
        template.setHashValueSerializer(profiles);

        template.afterPropertiesSet();
        return template;
    }
}
```

Here `Jackson2JsonRedisSerializer<CustomerProfile>` is **bound to a specific type**. The snippet fits Spring Data Redis 3.x APIs; in newer versions, check the corresponding constructors and Jackson mapper APIs.

Note the two hash serializers in this configuration: hash fields are Strings, while **hash values are also configured to read/write `CustomerProfile`**, not plain Strings. Calling `opsForHash().put(key, "name", "An")` on this template does not match the DTO hash value contract. To store plain String fields, use `StringRedisTemplate` or a separate String-hash template.

### 6.1. Never Guess the Default `RedisTemplate` Configuration

A `RedisTemplate` without explicitly configured serializers defaults to `JdkSerializationRedisSerializer` in Spring Data Redis. `StringRedisTemplate` configures String serializers for keys, values, and hash fields. However, Spring Boot or a project can customize the `redisTemplate` bean; tests must inspect the **actual configuration** of the app rather than guessing from bean names.

A consistent policy to adopt:

```text
Keys:         UTF-8 String
Hash fields:  UTF-8 String
Values:       JSON DTO with explicit schema/version
Hash values:  Per each Hash's contract
```

This is a cross-language-friendly recommendation, not a mandatory format for every project.

## 7. Round-Trip Test: Writing and Reading with the Same Template

Inside an integration test configured as in section 5, inject:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.core.StringRedisTemplate;

class RoundTripExample {

    @Autowired
    private StringRedisTemplate strings;

    @Autowired
    @Qualifier("profileJsonTemplate")
    private RedisTemplate<String, CustomerProfile> profiles;

    @Test
    void jsonProfileRoundTrip() {
        String key = "it:397:profile:" + UUID.randomUUID();
        CustomerProfile expected =
                new CustomerProfile("42", "An Nguyễn", 120);

        try {
            profiles.opsForValue().set(key, expected);

            CustomerProfile actual =
                    profiles.opsForValue().get(key);

            assertThat(actual).isEqualTo(expected);
        } finally {
            profiles.delete(key);
        }
    }
}
```

`RoundTripExample` illustrates the **test body**; to run standalone, place it inside the `@SpringBootTest`/`@Testcontainers` class from section 5 or add complete annotations and configuration to a separate test class.

This test verifies:

- The serializer can encode `CustomerProfile`.
- Redis accepts and retains a value.
- The deserializer reconstructs an equal object.

However, it **does not prove the JSON on the wire is compatible with other systems**. If the writer and reader share the same symmetric serializer bug, round-trip still passes.

### 7.1. Include Unicode to Catch Charset Bugs

Do not test only `"Alice"`. Include samples such as:

```text
"An Nguyễn"
"Tiếng Việt có dấu"
"東京"
"🚀"
"Quotes \" and newline\n"
"Name with leading/trailing spaces"
```

These samples expose wrong charsets, escaping errors, or unintended normalization steps. For Unicode, compare **values after deserialization** and, for multi-language contracts, verify **UTF-8 encoded bytes**.

## 8. Cross-Read Test: JSON Template Writes, `StringRedisTemplate` Reads

This is the most important test when two different APIs share a key:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;
import org.junit.jupiter.api.Test;

@Test
void jsonWriterCanBeReadAsRawString() throws Exception {
    String key = "it:397:cross:" + UUID.randomUUID();
    CustomerProfile expected =
            new CustomerProfile("42", "Linh", 27);

    try {
        profiles.opsForValue().set(key, expected);

        String rawJson = strings.opsForValue().get(key);

        assertThat(rawJson).contains("\"id\":\"42\"");
        assertThat(rawJson).contains("\"displayName\":\"Linh\"");

        // Reading back with the typed serializer must yield the same object.
        assertThat(profiles.opsForValue().get(key))
                .isEqualTo(expected);
    } finally {
        strings.delete(key);
    }
}
```

Here both templates use compatible key serializers, so they **resolve to the exact same physical key**. The JSON serializer produces bytes valid as a UTF-8 String; `StringRedisTemplate` reads the **JSON string**, though it does not convert JSON into `CustomerProfile`.

To verify JSON contents properly without depending on **field ordering**, parse the tree:

```java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = new ObjectMapper();
JsonNode tree = mapper.readTree(rawJson);

assertThat(tree.path("id").asText()).isEqualTo("42");
assertThat(tree.path("loyaltyPoints").asInt()).isEqualTo(27);
```

This is better than matching an entire JSON literal string when a serializer may reorder properties while preserving semantics.

### 8.1. Cross-Reading in the Reverse Direction

If another system writes a **valid JSON string matching the same schema**:

```java
String key = "it:397:external-json";

strings.opsForValue().set(key,
        "{\"id\":\"43\",\"displayName\":\"Bình\",\"loyaltyPoints\":8}");

CustomerProfile profile =
        profiles.opsForValue().get(key);
```

We expect `profile` to populate all three fields. This simulates a Node/Python service writing raw JSON that the Java reader can decode.

Conversely, if the writer stores:

```java
strings.opsForValue().set(key, "not-json");
```

the JSON deserializer **cannot** read a valid `CustomerProfile`. Record this error as a **data contract violation**, rather than automatically assuming “Redis is down.”

## 9. Testing Key Bytes: Two Templates Can Point to Different Keys

Suppose legacy code uses Java serialization for keys:

```java
import org.springframework.data.redis.serializer.JdkSerializationRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

String logicalKey = "it:397:legacy-key";

byte[] utf8Key =
        new StringRedisSerializer().serialize(logicalKey);

byte[] javaSerializedKey =
        new JdkSerializationRedisSerializer().serialize(logicalKey);
```

The two byte arrays differ. For example, Java native serialization of a String typically starts with magic bytes:

```text
AC ED 00 05 ...
```

The UTF-8 string `"it:397:legacy-key"` begins with the bytes for `'i'`, `'t'`, `':'`, `'3'` ... Redis treats them as two independent Redis keys.

A unit test checking bytes:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

@Test
void keySerializerChangesPhysicalKey() {
    String key = "it:397:legacy-key";

    byte[] raw = key.getBytes(StandardCharsets.UTF_8);
    byte[] javaBytes =
            new JdkSerializationRedisSerializer().serialize(key);

    assertThat(raw).isNotEqualTo(javaBytes);
    assertThat(HexFormat.of().formatHex(raw))
            .isNotEqualTo(HexFormat.of().formatHex(javaBytes));
}
```

Do not test by relying on Redis CLI printing binary keys as garbled characters: terminals render unprintable bytes differently. When exact comparisons are needed, read raw `byte[]` via the driver or serialize client-side and use a hex dump.

### 9.1. Testing Two Templates Against One Test Redis Instance

Create a legacy template **intentionally** using JDK serialization for keys and values:

```java
RedisTemplate<String, String> legacy = new RedisTemplate<>();
legacy.setConnectionFactory(connectionFactory);
legacy.setKeySerializer(new JdkSerializationRedisSerializer());
legacy.setValueSerializer(new JdkSerializationRedisSerializer());
legacy.afterPropertiesSet();

String key = "it:397:legacy";
legacy.opsForValue().set(key, "OLD");

// In terms of key bytes, StringRedisTemplate looks up a different key.
assertThat(strings.opsForValue().get(key)).isNull();

// Yet the legacy template reads back the key it wrote.
assertThat(legacy.opsForValue().get(key)).isEqualTo("OLD");

legacy.delete(key);
```

`connectionFactory` is the `RedisConnectionFactory` from the test context. Keys must be scoped to the test and deleted afterward.

This situation is frequently misdiagnosed as “Redis lost data” when the data actually lives under a **differently serialized key name**. In Redis Cluster, changing key bytes can also change the **hash slot** and target node.

## 10. Testing Hashes: Field Serializers and Value Serializers

A Redis Hash has:

```text
Redis key:     customer:42:settings
Redis field:   locale
Redis value:   vi-VN
```

When using `StringRedisTemplate`:

```java
String key = "it:397:hash";

strings.opsForHash().put(key, "locale", "vi-VN");
strings.opsForHash().put(key, "theme", "dark");

assertThat(strings.opsForHash().get(key, "locale"))
        .isEqualTo("vi-VN");
```

Redis CLI:

```redis
TYPE it:397:hash
HGET it:397:hash locale
HGETALL it:397:hash
```

Expected:

```text
hash
"vi-VN"
locale => vi-VN
theme  => dark
```

### 10.1. A Hash Field Encoded with JDK Serialization

If another template keeps `StringRedisSerializer` for keys but configures `JdkSerializationRedisSerializer` for **hash keys** (fields):

```java
RedisTemplate<String, String> mixed = new RedisTemplate<>();
mixed.setConnectionFactory(connectionFactory);
mixed.setKeySerializer(new StringRedisSerializer());
mixed.setValueSerializer(new StringRedisSerializer());
mixed.setHashKeySerializer(new JdkSerializationRedisSerializer());
mixed.setHashValueSerializer(new StringRedisSerializer());
mixed.afterPropertiesSet();
```

Then:

```java
mixed.opsForHash().put("it:397:hash-mixed", "locale", "vi-VN");
```

The physical Redis key is still readable as a String, but the hash field `locale` is sent as Java serialized bytes. Running:

```redis
HGET it:397:hash-mixed locale
```

will not find a field with UTF-8 bytes `locale`, because Redis Hashes compare fields byte-for-byte. Takeaway: **verify the hash key serializer independently from the key serializer**.

### 10.2. Do Not Mix `Hash<String,String>` and `Hash<String,DTO>` Across Fields on the Same Template

A field containing JSON:

```text
HSET customers:hash profile '{"id":"42","displayName":"An","loyaltyPoints":120}'
```

`StringRedisTemplate` can read field `profile` as a JSON string. A template configured with a `CustomerProfile` hash value serializer can decode it if key and hash-field bytes match. If some hash fields are plain Strings like `ACTIVE` and others are JSON DTOs, do not use a single typed-DTO serializer for **every field** and assume reads will always work.

Pick a clean schema per Redis Hash, or use separate templates per data type when needed.

## 11. Cross-Checking Stored Data with Redis CLI

Redis CLI is useful because it shows **server-side data** independently of Java objects:

```bash
redis-cli -h 127.0.0.1 -p 6379 \
  TYPE 'it:397:profile:42'

redis-cli -h 127.0.0.1 -p 6379 --raw \
  GET 'it:397:profile:42'

redis-cli -h 127.0.0.1 -p 6379 \
  TTL 'it:397:profile:42'

redis-cli -h 127.0.0.1 -p 6379 \
  HGETALL 'it:397:hash'
```

Never use `GET` to read a Redis Hash; Redis returns `WRONGTYPE`. Check `TYPE` first, then run the matching command.

### 11.1. Readable Raw JSON Does Not Guarantee Successful Deserialization

Redis CLI might print:

```json
{"id":"42","displayName":"An","loyaltyPoints":120}
```

Yet a newer Java class may require another field or an incompatible type. Therefore you need **two checks**:

1. The raw format matches the expected JSON/schema.
2. The current reader template actually deserializes it into a usable DTO.

For native binary serialization, `redis-cli --raw` is not guaranteed to print readable characters; never treat garbled terminal output as the sole failure criterion.

### 11.2. Diagnosing Missing Keys

If Java sees `null` while Redis CLI shows a similarly named key:

- Check database index (Standalone) or Cluster mode.
- Check key namespace/prefix and key generator.
- Check the bytes produced by the key serializer.
- Check whether TTL already expired.
- Check that both target the exact same host/port/TLS/ACL.
- Check the Redis key type, not just the logical name.

A JDK-serialized key cannot be fetched with `GET "customer:42"` as a UTF-8 String. Use the matching serializer or raw byte inspection tools.

## 12. Testing Serializers Standalone Without Booting Redis

`RedisSerializer<T>` can be tested directly:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.data.redis.serializer.StringRedisSerializer;

class StringSerializerTest {

    private final StringRedisSerializer serializer =
            new StringRedisSerializer();

    @Test
    void unicodeIsStoredAsUtf8() {
        String value = "Tiếng Việt 🚀";

        byte[] serialized = serializer.serialize(value);

        assertThat(serialized)
                .isEqualTo(value.getBytes(StandardCharsets.UTF_8));
        assertThat(serializer.deserialize(serialized))
                .isEqualTo(value);
    }
}
```

Similarly for typed JSON:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;

class CustomerSerializerTest {

    @Test
    void jsonRoundTripPreservesFields() {
        Jackson2JsonRedisSerializer<CustomerProfile> serializer =
                new Jackson2JsonRedisSerializer<>(
                        CustomerProfile.class);

        CustomerProfile expected =
                new CustomerProfile("42", "Hà", 5);

        byte[] bytes = serializer.serialize(expected);
        CustomerProfile decoded = serializer.deserialize(bytes);

        assertThat(decoded).isEqualTo(expected);
    }
}
```

### 12.1. Compare Against Golden Fixtures Instead of Only Objects

Example JSON contract:

```json
{"id":"42","displayName":"Hà","loyaltyPoints":5}
```

Store a **stable fixture** generated by an approved writer version. Test that the new reader decodes the fixture and verify semantic fields. Only assert exact byte equality when byte-for-byte parity with another system is mandatory; for JSON, comparing parsed structures avoids false failures from property ordering.

**Golden fixtures must be updated deliberately.** Never overwrite a fixture with output from the new build and call it proof of backward compatibility.

## 13. Typed JSON, Generic JSON, and Java Native Serialization

Common serializer groups:

| Serializer | Characteristics | Risks to Test |
|---|---|---|
| `StringRedisSerializer` | Explicit UTF-8 Strings | Misreading binary data, differing key encodings |
| `JdkSerializationRedisSerializer` | Java native object stream | Coupled to Java class/`serialVersionUID`, unfriendly across languages |
| `Jackson2JsonRedisSerializer<T>` | JSON targeting a known type | Schema and target type must stay consistent |
| `GenericJackson2JsonRedisSerializer` | JSON embedding type metadata for generic object deserialization | Type metadata, data trust, format changes |
| Custom serializer | CBOR/Protobuf/MessagePack or internal format | Requires byte contracts and backward compatibility |

### 13.1. Typed JSON Needs No Java Class Name in Every Record

With `Jackson2JsonRedisSerializer<CustomerProfile>`, the reader already knows the target `CustomerProfile.class`. The JSON payload stays focused on object fields. This is relatively easy to share across languages once the API schema is clear.

### 13.2. Generic Serializers and Type Hints

`GenericJackson2JsonRedisSerializer` embeds type metadata in JSON to reconstruct arbitrary objects without knowing the target type up front. This is convenient for heterogeneous caches, yet Node/Python clients may not understand or want extra metadata fields. Records containing Java class names also break easily during package or class renames.

**Do not blindly enable Jackson default typing or polymorphic deserialization on untrusted data.** Allowed deserialization types must follow strict allowlist policies, and Redis payloads require trusted ACLs/sources.

### 13.3. Java Serialization Is Not a Default Cross-Service Format

Java native serialization is tied to class names, field layouts, and Java compatibility. Besides poor multi-language interoperability, deserializing untrusted payloads poses security risks. When data is meant to be shared across services or languages, prefer an explicitly published, versioned **schema format** with compatibility tests.

Do not assume JSON always beats binary formats across every workload. Protobuf, CBOR, or specialized formats can be more efficient; the core requirement is an **agreed byte contract** tested across versions.

## 14. Schema Evolution: Testing v2 Readers Against v1 Data

Suppose an older version wrote:

```json
{"id":"42","displayName":"An"}
```

And the new version expects:

```json
{"id":"42","displayName":"An","loyaltyPoints":0}
```

A Java record with `int loyaltyPoints` may default to `0` when the JSON field is missing, depending on Jackson settings and model types. However, that **does not prove every schema change is safe**, especially with required fields, constructor validation, enums, or renamed fields.

### 14.1. Changes Requiring Tests

| Change | Risk |
|---|---|
| Adding an optional field | Old reader may ignore or fail on unknown fields |
| Adding a required field | New reader cannot read legacy data |
| Renaming a property | Legacy data fails to map |
| Changing `String` to number/enum | Parse failures or semantic mismatch |
| Renaming Java package/class with generic type hints | Old class cannot be resolved |
| Changing key prefix | New reader sees cache misses instead of existing entries |
| Changing serializer | Incompatible bytes |
| Changing TTL | Old keys do not retroactively pick up new policies |

### 14.2. Multi-Version Test Fixtures

A test suite should maintain:

```text
fixtures/
  profile-v1.json
  profile-v2.json
  profile-invalid.json
  profile-unknown-field.json
```

Each fixture carries an explicit contract:

- Reader v2 reads v1 and applies valid defaults.
- Reader v2 reads v2 normally.
- Reader v2 rejects invalid schemas cleanly.
- Old reader during rolling deployment behaves deterministically on v2 data.

You do not need every reader to support infinite historical versions. However, you must define the **compatibility window** while two versions coexist and while long-TTL Redis entries remain live.

### 14.3. When Changing Formats/Serializers

A controllable migration strategy:

```text
Version A:
  legacy:customer:42   -> Java serialized data

Version B:
  v2:customer:42       -> JSON data
```

Reader B:

1. Try reading the v2 key with the new serializer.
2. If the v2 key **does not exist**, consider reading the legacy key with the old serializer.
3. Convert the object to the new schema and write the v2 key.
4. Apply the v2 TTL according to agreed policy.
5. Do not delete old keys until every reader still needing them has been replaced.
6. Emit metrics on fallback reads to know when migration is complete.

**Never silently fall back when the v2 key exists but fails deserialization.** That indicates data corruption or a schema mismatch; raise an alert/error rather than masking bad data.

## 15. TTL and Writes: Do Not Let Serializer Tests Accidentally Wipe Expirations

Two distinct patterns:

```java
strings.opsForValue().set(
        "it:397:ttl", "READY",
        java.time.Duration.ofMinutes(2));
```

and:

```java
strings.opsForValue().set("it:397:ttl", "UPDATED");
```

A plain `SET` does not preserve the existing TTL unless called with expiration-preserving options, so overwriting a key without specifying an expiration clears its TTL. When testing migrations or “cross-read then rewrite” flows, do not check only the value.

Integration test example:

```java
import static org.assertj.core.api.Assertions.assertThat;
import java.time.Duration;

String key = "it:397:ttl:profile";
try {
    strings.opsForValue().set(key, "READY",
            Duration.ofSeconds(60));

    Duration before = strings.getExpire(key);
    assertThat(before).isGreaterThan(Duration.ZERO);

    String read = strings.opsForValue().get(key);
    assertThat(read).isEqualTo("READY");

    Duration after = strings.getExpire(key);
    assertThat(after).isGreaterThan(Duration.ZERO);
    assertThat(after).isLessThanOrEqualTo(before);
} finally {
    strings.delete(key);
}
```

Because real clocks and execution time reduce TTL, never assert `before.equals(after)`. TTL tests should allow a sensible range rather than demanding millisecond precision unless specifically testing timing commands.

### 15.1. Null, Missing, and Empty Differ

States that may need distinction:

| State | Example | How to Test |
|---|---|---|
| Key does not exist | `GET` returns nil | Template returns `null` or reactive `Mono.empty()` |
| Key exists with empty String | `SET key ""` | Returns `""`, not missing |
| JSON `null` value | JSON bytes representing null | Depends on serializer and API; requires explicit contract |
| Object with null field | `{"name":null}` | Valid DTO or error depending on schema |
| Key exists with wrong type | Redis Hash instead of String | `WRONGTYPE`, not a deserialization error |

Do not use a Java `null` return value as sole proof that a Redis key holds no data. You may need `hasKey`, `TYPE`, raw bytes, and serializer semantics.

## 16. Reactive Templates: Testing Subscriptions and Cross-Reading

Reactive APIs do not dispatch commands imperatively. Redis command Publishers normally execute only when subscribed.

Example test using `StepVerifier`:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import reactor.test.StepVerifier;

String key = "it:397:reactive";

StepVerifier.create(
        reactiveStrings.opsForValue().set(key, "WRITTEN")
                .then(reactiveStrings.opsForValue().get(key))
)
    .expectNext("WRITTEN")
    .verifyComplete();

// Cross-read from the imperative template sharing the same key bytes.
assertThat(strings.opsForValue().get(key))
        .isEqualTo("WRITTEN");

strings.delete(key);
```

`reactiveStrings` is a `ReactiveStringRedisTemplate` bean from the Spring context. `StepVerifier` acts as the subscriber in the test; creating a `Mono` without calling `verifyComplete()` will not execute the command.

### 16.1. Why Not Call `subscribe()` and Assert Immediately?

Flaky example:

```java
reactiveStrings.opsForValue().set(key, "READY").subscribe();
assertThat(strings.opsForValue().get(key)).isEqualTo("READY");
```

`subscribe()` does not wait for the Redis command to complete. The blocking assertion can run before Redis receives `SET`. Fix this using `StepVerifier` or returning the Publisher to a reactive test runner that awaits completion properly.

### 16.2. Every Subscription Can Re-Execute the Command

```java
Mono<Long> source =
        reactiveStrings.opsForValue().increment("it:397:counter");
```

If a test subscribes twice, the counter increments twice. Cross-read tests must distinguish **one record written once** from **a source operation re-subscribed**. Especially with `retry` or `repeat`, do not blame the serializer when data was mutated twice.

### 16.3. `ReactiveRedisTemplate` with Custom Serializers

Conceptual context configuration example:

```java
import org.springframework.data.redis.connection.ReactiveRedisConnectionFactory;
import org.springframework.data.redis.core.ReactiveRedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializationContext;
import org.springframework.data.redis.serializer.StringRedisSerializer;

RedisSerializationContext<String, CustomerProfile> context =
        RedisSerializationContext
                .<String, CustomerProfile>newSerializationContext(
                        new StringRedisSerializer())
                .value(new Jackson2JsonRedisSerializer<>(
                        CustomerProfile.class))
                .build();

ReactiveRedisTemplate<String, CustomerProfile> reactiveProfiles =
        new ReactiveRedisTemplate<>(
                reactiveConnectionFactory, context);
```

`reactiveConnectionFactory` is a `ReactiveRedisConnectionFactory` dependency. When imperative and reactive templates read the same key, **their key/value serialization contexts must match**. If Hashes or Streams are also used, verify their corresponding serializers too—not just `value(...)`.

## 17. Testing Malformed Data and Wrong Redis Types

A robust system also tests **invalid cases**:

### 17.1. Corrupted JSON

```java
String key = "it:397:invalid-json";
try {
    strings.opsForValue().set(key, "{broken-json");

    org.assertj.core.api.Assertions.assertThatThrownBy(
            () -> profiles.opsForValue().get(key))
        .isInstanceOf(RuntimeException.class);
} finally {
    strings.delete(key);
}
```

You can assert a more specific class like `SerializationException` depending on the API and version. Log error details in a controlled way, **without dumping sensitive raw payloads**.

### 17.2. Wrong Redis Key Data Type

```java
String key = "it:397:wrongtype";
try {
    strings.opsForHash().put(key, "field", "value");

    org.assertj.core.api.Assertions.assertThatThrownBy(
            () -> strings.opsForValue().get(key))
        .isInstanceOf(RuntimeException.class);
} finally {
    strings.delete(key);
}
```

This error comes from running Redis `GET` on a Hash, not from a JSON serializer. Check `TYPE key` before diagnosing.

### 17.3. Unknown Fields and Invalid Enums

JSON containing an unrecognized property:

```json
{"id":"42","displayName":"An","loyaltyPoints":120,"newField":"x"}
```

An older reader may ignore it or fail depending on Jackson configuration. Tests must lock down the **expected policy** for rolling deployments.

For enums:

```json
{"status":"UNKNOWN_FROM_FUTURE"}
```

never silently coerce it into another valid status if that corrupts business logic. An intentional unknown-value fallback may be used, provided downstream semantics are verified.

### 17.4. Do Not Hide Failures with a Catch-All Returning `null`

Risky pattern:

```java
try {
    return profiles.opsForValue().get(key);
} catch (Exception ignored) {
    return null;
}
```

This collapses corrupt payloads, schema mismatches, connection drops, and missing keys into the exact same `null`. Good design should:

- Distinguish **cache miss** from **serialization failure**.
- Log safe error codes and key namespaces.
- Never overwrite legacy values with defaults if the reader cannot understand the payload.
- Alert on contract drift.
- Fall back only according to explicitly defined policies.

## 18. Cross-Reading Across Multiple Application Versions

An integration test running the new writer and new reader in the same JVM **does not prove** compatibility with an older service version running live. During rolling deployments:

```text
Service v1 --------> Redis keyspace <-------- Service v2
      |                                       |
  Serializer v1                          Serializer v2
  Schema v1                              Schema v2
```

Cover at least these scenarios:

1. Writer v1 → reader v1 (baseline).
2. Writer v1 → reader v2 (backward compatibility).
3. Writer v2 → reader v1 (forward compatibility during the rolling window).
4. Writer v2 → reader v2.
5. Cross-language writer/reader via golden JSON fixtures.
6. Keys written before serializer or key-prefix changes.

You do not need v1 to read v2 forever once migration finishes; however, during the overlap window, data contracts must enforce explicit guarantees.

### 18.1. Refactoring Java Classes While Preserving the JSON Schema

If services exchange JSON with `id` and `displayName`, renaming an internal Java class does not change the wire format as long as a typed serializer omits class names. Conversely, serializers embedding class-name type metadata may fail to read old entries after package refactors.

Therefore, test the **wire-format contract**, not just object equality within the current codebase.

### 18.2. Adding `schemaVersion` When Formats Must Evolve

A payload can carry:

```json
{
  "schemaVersion": 2,
  "id": "42",
  "displayName": "An",
  "loyaltyPoints": 120
}
```

Readers inspect the version to choose the right parser or migration path. Do not confuse the JSON payload version with the Redis server version or Gradle dependency version.

When `schemaVersion` is part of the object, tests must verify writers populate it accurately and readers support all versions within the supported window.

## 19. Redis Cluster: Key Serializers Also Determine Hash Slots

Redis Cluster computes:

```text
slot = CRC16(serialized_key_bytes) mod 16384
```

Switching a key from:

```text
UTF-8("cart:{42}:items")
```

to Java native serialization of the same logical string produces **different key bytes**. That can:

- Create a brand-new physical Redis key.
- Map the key to a different hash slot.
- Trigger `CROSSSLOT` errors in multi-key commands.
- Cause read-only paths to see cache misses after deploying the new serializer.

Thus, tests on standalone Redis can miss Redis Cluster regressions. For keys that must share a slot, use the same String key serializer and check:

```redis
CLUSTER KEYSLOT cart:{42}:items
CLUSTER KEYSLOT cart:{42}:total
```

Two UTF-8 keys with the same hash tag `{42}` are guaranteed to share a slot. A different serializer can alter the bytes and break that assumption.

### 19.1. Do Not Test Only Whether Single-Key Commands Succeed

Single-key `GET` commands can succeed on Cluster even after keys move to different slots. Failures appear only on:

- Multi-key `MGET`/`MSET`.
- `MULTI`/`EXEC`.
- Multi-key Lua scripts.
- Pipelines/adapters with version-specific slot restrictions.

Contract tests should verify **key bytes and hash slots together** whenever business logic relies on co-location.

## 20. Spring Cache and Redis Repositories Have Their Own Formats

### 20.1. `RedisCacheManager` Does Not Automatically Inherit `StringRedisTemplate`'s Serializer

Spring Data Redis Cache uses its own `RedisCacheConfiguration`, including:

- Key prefix, typically cache name plus `::`.
- Serializers for cache keys and values.
- TTL and null-caching policies.

Example:

```text
Spring Cache logical:
  cacheName = productViews
  key       = "p-100"

Physical Redis key may be:
  productViews::p-100
```

However, the Redis Cache value may be Java-serialized bytes or JSON depending on `CacheManager` config. Therefore, `StringRedisTemplate.opsForValue().get("productViews::p-100")` **is not guaranteed** to return a readable JSON string.

To make cached values readable across languages, configure serializers on **`RedisCacheManager`**, not just on a `RedisTemplate` bean. Tests must call through a `@Cacheable` method and inspect the raw key/value stored in test Redis.

### 20.2. Redis Repositories Have Entity Mapping and Auxiliary Keys

A Redis Repository using `@RedisHash`, `@Id`, and `@Indexed` creates multiple auxiliary keys and Sets. `MappingRedisConverter`/`RedisCustomConversions` mapping is not identical to serializing a DTO as JSON via `RedisTemplate.opsForValue().set(...)`.

Do not test a Repository round-trip and assume `StringRedisTemplate` can read the repository entity as a JSON string. If interoperability is required, explicitly define the format and physical keys produced by the repository.

### 20.3. Do Not Run `KEYS *` Against Production Redis for Comparison

When debugging a test, inspect only the test's namespace using bounded `SCAN` or specific key lookups. `KEYS *` degrades performance on large servers; in Redis Cluster, scanning one node does not cover the entire cluster.

## 21. Testing Serializers in Pipelines and Transactions

With `RedisTemplate.executePipelined(...)`, methods invoked inside the callback typically return `null` at enqueue time; the final result list returned by the pipeline uses the template's serializers or a specified result serializer to decode responses.

Therefore, checking “`get` returned null inside the callback” **does not prove the value is missing**.

In a supported environment:

```java
List<Object> results = strings.executePipelined(
        (org.springframework.data.redis.core.RedisCallback<Object>)
                connection -> {
                    byte[] key = "it:397:pipeline".getBytes(
                            java.nio.charset.StandardCharsets.UTF_8);
                    byte[] value = "READY".getBytes(
                            java.nio.charset.StandardCharsets.UTF_8);

                    connection.stringCommands().set(key, value);
                    connection.stringCommands().get(key);

                    return null;
                });
```

Read `results` **after** the pipeline completes rather than reading synchronous `GET` returns inside the callback. Element count and types depend on the API, serializers, and commands; verify against your version's contract. Clean up the test key afterward.

`MULTI`/`EXEC` transactions also have distinct result semantics; serializer mismatches can surface when Spring decodes queued replies. Test using the real transaction API rather than assuming sequential calls behave identically to pipelining or transactions.

## 22. What Should a Minimal Integration Test Suite Include?

Tests can be organized as follows:

| Test | Writer | Reader/Verifier | Criterion |
|---|---|---|---|
| `string_round_trip` | String Template | String Template | Exact Unicode/empty strings |
| `json_round_trip` | JSON DTO Template | JSON DTO Template | DTO equals expected value |
| `json_raw_read` | JSON DTO Template | String Template / raw parser | Valid JSON schema |
| `external_json_read` | String Template with JSON fixture | JSON DTO Template | Cross-read into DTO |
| `physical_key_bytes` | JDK vs. UTF-8 key serializers | Compare `byte[]` | Intentionally distinct key bytes |
| `legacy_key_visibility` | JDK key Template | String Template | Do not mistake for missing key |
| `hash_field_encoding` | Different hash key serializers | `HGET`/Hash operations | Correct field bytes |
| `wrongtype_handling` | Redis Hash | String `GET` | Error detected and classified |
| `invalid_json_handling` | Raw malformed JSON | Typed JSON Template | Never silently return default |
| `ttl_preserved_on_read` | `SET` with TTL | `GET` + `PTTL` | Reading does not reset TTL |
| `reactive_cross_read` | Reactive String Template | Imperative String Template | Matching bytes and completion |
| `schema_v1_v2` | Golden fixture v1 | Reader v2 | Backward compatibility |
| `cache_serializer` | `@Cacheable` method | Raw Redis bytes / Cache | Valid cache format |
| `cluster_hash_slot` | Key formatter | `CLUSTER KEYSLOT` | Co-located keys share a slot |

Not every test has to run on every pull request. You can split them:

- Very fast unit tests.
- Standalone Redis integration tests on every PR.
- Serializer version contract tests on schema changes.
- Cluster/upgrade tests on release pipelines or schedules.

However, **any cross-communicating feature** must have at least one test executing both the real write path and the real read path, not just mocks.

## 23. Avoiding Flaky Tests and Cleaning Up Test Data Properly

Common causes of flakiness:

1. Two parallel tests sharing a key.
2. Writing with a reactive Publisher without awaiting completion.
3. Setting a TTL so short that the key expires between assertions.
4. Test environment reusing a Redis container carrying stale data.
5. Assertions depending on JSON property ordering.
6. Using fixed `Thread.sleep` to wait for commands or replication.
7. Tests assuming a replica immediately reflects writes made on the master.
8. Running `FLUSHALL` on a shared Redis instance.

### 23.1. Use Unique Keys per Test

```java
String testId = java.util.UUID.randomUUID().toString();
String key = "it:397:" + testId + ":profile";
```

Clean up with `delete(key)` in `finally` or `@AfterEach`. If a test creates multiple auxiliary keys, track and delete all of them. On Redis Cluster, ensure cleanup matches key serializers and connection factory constraints.

### 23.2. Set Timeouts and Scope Test Data

When testing reactive pipelines:

```java
StepVerifier.create(
        reactiveStrings.opsForValue().get("it:397:known"))
    .expectNext("READY")
    .expectComplete()
    .verify(java.time.Duration.ofSeconds(5));
```

This assumes the key was prepared beforehand. A timeout prevents tests from hanging indefinitely if Redis is unavailable; pick a duration suited to CI. Avoid overly tight timeouts that flake under build-machine load.

### 23.3. Do Not Target Replicas When Asserting Read-After-Write

Replication introduces lag. If a test writes to the master and immediately reads from a replica, failures can stem from eventual consistency rather than serialization. Pick the right read preference and explicitly distinguish tests verifying eventual consistency.

## 24. Troubleshooting Errors by Symptom

| Symptom | Possible Cause | Check |
|---|---|---|
| Write succeeds, another Template reads `null` | Different key serializer or prefix | Compare serialized key bytes |
| Redis CLI `GET` shows strange characters | Binary serialization | Hex dump and verify serializer |
| Readable as JSON String, typed DTO fails | Schema, target type, or Jackson mismatch | Parse JSON, check fields/types |
| `SerializationException` or stream read error | Wrong value serializer | Verify writer format and consumer config |
| `WRONGTYPE` | Key exists with a different Redis type | `TYPE key`, inspect namespace |
| `HGET` misses field yet Hash has data | Different hash key serializer | Compare field bytes/`HGETALL` |
| JSON field reordering breaks test | Asserting whole literal string | Compare parsed JSON tree/schema |
| Changing DTO breaks reading old cache | Missing schema migration | Golden fixtures + versioned adapter |
| Redis stores data yet UTF-8 garbles | Charset mismatch or double encoding | Compare raw bytes and both serializers |
| Written key disappears | TTL, eviction, delete, or wrong DB | `PTTL`, `INFO memory`, connection config |
| Reading same key twice yields changing counter | Publisher subscribed/retried twice on side-effecting write | Log subscriptions and command semantics |
| Flaky test outcomes | Key collisions, TTL, async races | Isolate keys/containers, `StepVerifier`, deterministic fixtures |
| Works standalone, fails on Cluster | Key serialization shifts slot or cross-slot multi-key command | `CLUSTER KEYSLOT`, hash tags, driver support |
| Cache format differs from template | `RedisCacheManager` uses separate config | Inspect `RedisCacheConfiguration` |
| Repository does not read as JSON value | Repository mapping differs from `RedisTemplate` JSON | Check entity keys/Hash/converters |

## 25. Hands-On Exercises

### Exercise 1 — Comparing `StringRedisSerializer` and JDK Serializer

1. Create the key string `it:397:test-key`.
2. Call `StringRedisSerializer.serialize` and `JdkSerializationRedisSerializer.serialize`.
3. Convert both byte arrays to hex.
4. Explain why the same logical string produces two distinct Redis keys.
5. If a test Redis Cluster is available, compare the slots of those byte arrays via the appropriate client/API.

### Exercise 2 — Writing a JSON DTO and Reading Raw

1. Create `CustomerProfile("42", "An Nguyễn", 120)`.
2. Write it with `profileJsonTemplate`.
3. Read it with `StringRedisTemplate`.
4. Parse the JSON string and verify each field.
5. Read back with the typed template and verify object equality.
6. Delete the exact key afterward.

### Exercise 3 — Reading Fixtures from Another Application

1. Use `StringRedisTemplate` or Redis CLI to write a JSON fixture:

   ```json
   {"id":"50","displayName":"Bình","loyaltyPoints":17}
   ```

2. Read it with `profileJsonTemplate`.
3. Verify the DTO matches.
4. Change `loyaltyPoints` to an invalid string and verify the contract error is detected.
5. Do not swallow the error by returning `null`.

### Exercise 4 — Hash Key and Hash Field Serializers

1. Use String Template to run `HSET it:397:hash locale vi-VN`.
2. Read back with String Template and Redis CLI.
3. Build a template with JDK hash key serialization.
4. Write field `locale` with that template into another Hash.
5. Run `HGET ... locale` in Redis CLI and observe the plain String field misses.
6. Explain why `setKeySerializer(String)` alone is not enough.

### Exercise 5 — TTL and Cross-Reading Tests

1. Write a JSON key with a 60-second TTL.
2. Read via String Template and typed Template.
3. Verify TTL continues decreasing across reads.
4. Overwrite the key without specifying a TTL in the test environment.
5. Explain why TTL can be wiped and how migrations preserve expiration policies.

### Exercise 6 — Reactive Templates and Subscriptions

1. Construct a `Mono<Boolean>` from `set` without subscribing.
2. Verify the key is not yet written in test Redis.
3. Use `StepVerifier` to wait for completion.
4. Cross-read using `StringRedisTemplate`.
5. Avoid fire-and-forget `subscribe()` followed immediately by assertions.

### Exercise 7 — Compatibility Across Version Upgrades

1. Capture a golden JSON fixture from an older writer version.
2. Run the new reader against the fixture.
3. Add a new field and an unknown field.
4. Test default and fallback rules.
5. Keep legacy fixtures in test resources so future upgrades retain compatibility proof.

### Exercise 8 — Testing Redis Cache Independently

1. Configure cache `productViews` with explicit serializers.
2. Populate an entry via a `@Cacheable` method.
3. Inspect the key prefix and TTL.
4. Read the raw value and check whether it is JSON, String, or binary.
5. Try reading with a compatible template; never assume `StringRedisTemplate` reads every object cache.

## 26. Checklist for Serializer Changes

Before changing a serializer or schema in a running system:

1. Are the physical key name and key serializer agreed upon?
2. Are there byte-level tests catching unintended key changes?
3. Do keys, hash keys, values, and hash values each have explicit contracts?
4. Are golden fixtures retained from older writer versions?
5. Can new readers decode legacy data during rolling deployments?
6. Do old readers need to decode new data during the transition window?
7. Is handling defined for malformed JSON, missing/unknown fields, and unfamiliar enums?
8. Is unsafe Jackson polymorphic typing avoided for untrusted payloads?
9. Is TTL preserved, or is a key-refresh plan defined?
10. Is it tested against real Redis using Testcontainers?
11. Are cross-read tests in place between imperative/reactive templates or cooperating services?
12. Are Redis Cache and Repositories tested if used by the application?
13. For Cluster, are hash slots and multi-key operations verified?
14. Are migration, rollback, and fallback-rate metrics prepared?
15. Are test datasets bounded with dedicated namespaces and safe cleanup?

## 27. Conclusion

**Testing `RedisTemplate` does not stop at “write with a template, read back with the same template.”** You must verify the wire contract: Redis key bytes, Redis types, value bytes, Hash serializers, JSON schemas, charsets, TTL, and every cross-reading path that exists in your architecture.

`StringRedisTemplate` is convenient for UTF-8 strings and inspection via Redis CLI. `RedisTemplate<String, CustomerProfile>` with a typed JSON serializer works well when DTOs have an explicitly defined schema. Java native serialization and generic JSON type metadata carry compatibility and security trade-offs; never assume every client decodes them identically.

A trustworthy test suite combines **unit tests on serializer bytes**, **integration tests with real Redis**, **contract tests using golden fixtures from prior versions**, and **cross-reading tests** across Templates, Reactive Templates, Redis CLI, or peer services. When changing serializers or upgrading versions, these tests distinguish cache misses caused by altered key bytes, schema mismatches, Redis type errors, and genuine connection failures—preventing silent deployments that break legacy data reads.

## References

- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html): `RedisTemplate`, `StringRedisTemplate`, and serialization configuration.
- [Spring Data Redis — Serializers](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html): Redis mapping/repositories and related serializer classes.
- [Spring Data Redis — Reactive Redis Support](https://docs.spring.io/spring-data/redis/reference/redis/redis-reactive.html): `ReactiveRedisTemplate`, `ReactiveStringRedisTemplate`, and serialization contexts.
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html): cache-specific serializers, key prefixes, and TTL.
- [Spring Data Redis API — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/core/RedisTemplate.html): configuring key/value/hash serializers.
- [Spring Data Redis API — RedisSerializer](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/serializer/RedisSerializer.html): byte conversion contract.
- [Testcontainers — JUnit Jupiter](https://java.testcontainers.org/test_framework_integration/junit_5/): Redis integration tests with real containers.
- [Spring Framework — DynamicPropertySource](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-dynamicpropertysource.html): providing dynamic container endpoints to Spring tests.
- [Project Reactor — StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html): testing Publishers and controlled subscriptions.
- [Redis — TYPE](https://redis.io/docs/latest/commands/type/): verifying a key's data type.
- [Redis — TTL](https://redis.io/docs/latest/commands/ttl/): checking key expiration.
- [Redis — Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/): key bytes, hash slots, and same-slot multi-key requirements.
