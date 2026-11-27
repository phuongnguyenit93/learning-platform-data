# Type Conversion and Data Serialization Classes in Spring Data Redis

When a Java application works with Redis, data does not automatically move from a Java object into a typed storage slot. Redis accepts and returns byte sequences, while Spring Data Redis provides multiple layers to convert between **Java objects**, **intermediate representations**, and **Redis data**. Understanding the boundary between **conversion** and **serialization** helps you pick the right configuration, avoid data-reading errors, and preserve compatibility across application versions.

In the Spring Data Redis architecture, distinguish three groups:

1. **`RedisSerializer` and `RedisSerializationContext`**: determine how keys, values, and hash fields are encoded to bytes and decoded from bytes when accessed via templates, caches, or reactive APIs.
2. **`RedisConverter`, `MappingRedisConverter`, `RedisCustomConversions`**: used in the object-to-Redis-hash mapping model, especially with **Spring Data Redis Repositories**.
3. **Application classes** such as DTOs, entities, services, and caches: determine data types, business meaning, TTLs, and key-naming conventions.

Not every Spring Data Redis API takes the same processing path. For instance, `RedisTemplate.opsForValue().set(...)` uses a value serializer; by contrast, a repository for a `@RedisHash` entity uses a mapping converter to turn entity properties into fields of a Redis hash.

## 1. The big picture: how does a Java object reach Redis?

When saving a value via `RedisTemplate`, the conceptual flow is:

```text
Java service
    |
    | redisTemplate.opsForValue().set(key, product)
    v
RedisTemplate<K, V>
    |-- keySerializer   : K -> byte[]
    |-- valueSerializer : V -> byte[]
    v
RedisConnectionFactory / RedisConnection
    |
    | send SET kBytes vBytes command
    v
Redis server
    |
    | store key/value pair as bytes
    v
GET -> byte[] -> valueSerializer.deserialize(...) -> Java object
```

When a repository stores an object as a Redis hash, the processing path differs:

```text
UserRepository.save(user)
    |
    v
Redis Repository / RedisKeyValueAdapter
    |
    v
MappingRedisConverter
    |-- RedisMappingContext: entity metadata
    |-- conversion service and RedisCustomConversions
    |-- convert properties into hash fields/values
    v
Redis hash: HSET profiles:<id> field value ...
    |
    v
HGETALL ... -> MappingRedisConverter.read(...) -> Java entity
```

Thus, a **serializer** defines the byte representation of a value at the client–Redis boundary, whereas a **converter** in the mapping mechanism governs how a Java type is represented in or reconstructed from the storage structure. A JSON serializer can be configured on `RedisTemplate`, yet that does not mean a Redis Repository automatically stores entire entities as single JSON strings.

## 2. Why is serialization needed even though Redis has its own data types?

Redis provides structures such as strings, hashes, lists, sets, sorted sets, and streams. Nevertheless, the keys and values sent over the Redis protocol remain binary byte sequences. Redis has no built-in notion that a byte sequence represents a `Product`, `LocalDate`, `UUID`, or any specific Java object.

Suppose a service wants to store:

```java
public record Product(String id, String name, long priceMinor) {}

Product product = new Product("p42", "Notebook", 199000);
```

The same object can be represented in several ways:

```text
UTF-8 JSON:
{"id":"p42","name":"Notebook","priceMinor":199000}

Custom string format:
p42|Notebook|199000

Java native serialization:
byte[] in Java Object Serialization format

Redis hash:
HSET catalog:product:p42 id "p42" name "Notebook" priceMinor "199000"
```

These representations are **not directly interoperable**. If one application writes JSON while another reads with Java serialization, decoding fails even when both connect to the same Redis instance and use the same key name.

Therefore, a data contract should cover at least: **key name, Redis data type, serializer/converter, encoding, payload structure, schema-evolution rules, and TTL**.

## 3. `RedisSerializer<T>`: converting between Java and `byte[]`

`RedisSerializer<T>` is the most common interface at the template level. Its two foundational operations look conceptually like:

```java
byte[] serialize(T value);
T deserialize(byte[] bytes);
```

Writes invoke `serialize`; reads invoke `deserialize`. Either method can throw `SerializationException` if a payload is invalid or cannot be converted to the target type. How `null` is handled depends on the specific serializer and API; do not assume `null`, an absent key, and a serialized null payload always carry the same meaning.

Common serializers:

| Class / group | Stored data | Strengths | Notes |
|---|---|---|---|
| `StringRedisSerializer` | UTF-8 strings | Readable in `redis-cli`, good cross-language interoperability | Suited for strings; does not turn arbitrary Java objects into JSON |
| `Jackson2JsonRedisSerializer<T>` | JSON for a fixed target type | Human-readable payload, explicit type contract | Requires configuring target type and mapper/schema carefully as data evolves |
| `GenericJackson2JsonRedisSerializer` | JSON for multiple Java types, typically with type info | Convenient for polymorphic values or multi-type caches | Type metadata and Jackson configuration affect compatibility and security |
| `JdkSerializationRedisSerializer` | Java native serialization | Can read/write compatible Java objects | Hard to use outside Java; security risks when deserializing untrusted data; brittle under class changes |
| `GenericToStringSerializer<T>` | Converts objects to strings and then bytes | Handy for simple types with a matching converter | Not a general solution for complex objects |
| Custom serializer | Application-defined byte format | Full control over encoding, performance, versioning | Must maintain compatibility and error handling manually |

By default, `RedisTemplate` may use `JdkSerializationRedisSerializer` for several slots when left unconfigured. In new applications, **declare serializers explicitly** according to your data contract. `StringRedisTemplate` is convenient whenever both keys and values are strings: its serializers are preconfigured for strings.

### Why does output in `redis-cli` look different?

With a string or UTF-8 JSON serializer, `GET` typically produces readable text:

```bash
redis-cli --raw GET catalog:product:v1:p42
```

```json
{"id":"p42","name":"Notebook","priceMinor":199000}
```

By contrast, payloads from Java native serialization are binary, so `redis-cli` renders unreadable control characters. Do not assume a key is corrupted just because it is not plain text; identify **the original write format** and use the matching decoder.

## 4. Four serializer slots on `RedisTemplate`

A `RedisTemplate<K,V>` distinguishes key and value serializers depending on the Redis command family:

| `RedisTemplate` setting | Applies to | Example |
|---|---|---|
| `keySerializer` | Primary keys of commands | Key of `SET`, `GET`, Redis hash key |
| `valueSerializer` | Values in value, list, set, sorted set operations, etc. | Value of `SET product:42 <payload>` |
| `hashKeySerializer` | Field names inside a Redis hash | `name`, `price` in `HSET product:42 name ...` |
| `hashValueSerializer` | Field values inside a Redis hash | Value `"Notebook"` in `HSET product:42 name ...` |

The template also has additional serializer settings, such as a default serializer or string serializer used by certain operations. The key point is that **key, value, hash field, and hash value are four distinct roles**; do not configure only `valueSerializer` and assume every Redis structure uses the same rule.

For example, in:

```java
redisTemplate.opsForHash().put("catalog:inventory", "p42", "50");
```

`"catalog:inventory"` goes through `keySerializer`, `"p42"` goes through `hashKeySerializer`, and `"50"` goes through `hashValueSerializer`. The template's `valueSerializer` does not govern how `"50"` is stored inside the Redis hash.

## 5. Spring Boot example: configuring `RedisTemplate` with JSON

The example below targets Spring Boot 3.x, Spring Data Redis, Java 17+, and an auto-configured `RedisConnectionFactory`. Applications typically declare the Spring Data Redis starter and provide environment-specific Redis connection configuration.

Define the object:

```java
package com.example.catalog;

public record Product(String id, String name, long priceMinor) {}
```

Configure the template with UTF-8 string keys and JSON values dedicated to `Product`:

```java
package com.example.catalog;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class RedisTemplateConfig {

    @Bean
    public RedisTemplate<String, Product> productRedisTemplate(
            RedisConnectionFactory connectionFactory) {

        RedisTemplate<String, Product> template = new RedisTemplate<>();
        template.setConnectionFactory(connectionFactory);

        StringRedisSerializer stringSerializer = new StringRedisSerializer();

        template.setKeySerializer(stringSerializer);
        template.setValueSerializer(
                new Jackson2JsonRedisSerializer<>(Product.class));

        // If opsForHash() is used with string field names and field values.
        template.setHashKeySerializer(stringSerializer);
        template.setHashValueSerializer(stringSerializer);

        template.afterPropertiesSet();
        return template;
    }
}
```

Service using the template:

```java
package com.example.catalog;

import java.time.Duration;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductRedisStore {
    private final RedisTemplate<String, Product> template;

    public ProductRedisStore(RedisTemplate<String, Product> productRedisTemplate) {
        this.template = productRedisTemplate;
    }

    public void save(Product product) {
        String key = "catalog:product:v1:" + product.id();
        template.opsForValue().set(key, product, Duration.ofMinutes(20));
    }

    public Product find(String id) {
        return template.opsForValue().get("catalog:product:v1:" + id);
    }
}
```

Calling `save(new Product("p42", "Notebook", 199000))` sends to Redis:

```text
Key (UTF-8) : catalog:product:v1:p42
Value (JSON): {"id":"p42","name":"Notebook","priceMinor":199000}
TTL         : 20 minutes at write time
```

This is a **Redis string** containing JSON, not a Redis hash. `HGETALL catalog:product:v1:p42` cannot read this value because the key's Redis data type is string; use `GET` or `opsForValue()` instead.

In this example, `Product` contains only strings and integers, so the JSON serializer handles it directly. For types such as `Instant`, `LocalDateTime`, `Optional`, or complex mappings, configure an `ObjectMapper` and Jackson modules appropriate for your version and time conventions. Do not assume a serializer instantiated via a standalone constructor automatically picks up every Spring Boot `ObjectMapper` customization.

## 6. When should you use `StringRedisTemplate`?

When data is genuinely strings, numbers stored as strings, or JSON payloads constructed explicitly by the application, you can use `StringRedisTemplate`:

```java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class TokenStore {
    private final StringRedisTemplate redis;

    public TokenStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void put(String tokenId, String accountId) {
        redis.opsForValue().set(
                "auth:token:v1:" + tokenId,
                accountId,
                Duration.ofMinutes(10));
    }

    public String get(String tokenId) {
        return redis.opsForValue().get("auth:token:v1:" + tokenId);
    }
}
```

With `StringRedisTemplate`, `accountId` is stored as a UTF-8 string. A JSON-configured `RedisTemplate<String, Product>` and a `StringRedisTemplate` can coexist in the same application, but if they read the same key, **the payload must match the format expected by the reader**. Java generic types do not automatically convert Redis data from one format to another.

## 7. `RedisSerializationContext` and reactive APIs

In reactive Spring Data Redis, `ReactiveRedisTemplate<K,V>` accepts a **`RedisSerializationContext<K,V>`**. This context groups serialization rules for keys, values, hash keys, and hash values, typically via `SerializationPair`.

Conceptual example using a Lettuce reactive connection factory:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.ReactiveRedisConnectionFactory;
import org.springframework.data.redis.core.ReactiveRedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializationContext;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class ReactiveRedisConfig {

    @Bean
    ReactiveRedisTemplate<String, Product> reactiveProductRedisTemplate(
            ReactiveRedisConnectionFactory factory) {

        StringRedisSerializer keys = new StringRedisSerializer();
        Jackson2JsonRedisSerializer<Product> values =
                new Jackson2JsonRedisSerializer<>(Product.class);

        RedisSerializationContext<String, Product> context =
                RedisSerializationContext
                    .<String, Product>newSerializationContext(keys)
                    .value(values)
                    .hashKey(keys)
                    .hashValue(values)
                    .build();

        return new ReactiveRedisTemplate<>(factory, context);
    }
}
```

With this context, `reactiveTemplate.opsForValue().set(key, product)` applies the `values` serializer and returns `Mono<Boolean>`, while reads return `Mono<Product>`. The reactive API changes execution to an asynchronous non-blocking model; **it does not make Redis natively understand Java objects**. Byte formats across synchronous and reactive APIs must still match whenever both access the same keyspace.

`ReactiveStringRedisTemplate` fits when both keys and values are strings. As with `RedisTemplate`, choose the template matching the actual storage format and data types.

## 8. `MappingRedisConverter`: mapping entities to Redis hashes

In Spring Data Redis Repositories, `@RedisHash` marks an entity type to be managed under Redis's key–value repository model. Under standard repository configuration, Spring Data Redis uses `MappingRedisConverter` to decompose objects into Redis hash fields.

Example:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash("profiles")
public class UserProfile {
    @Id
    private String id;
    private String displayName;

    public UserProfile() {}

    public UserProfile(String id, String displayName) {
        this.id = id;
        this.displayName = displayName;
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public String getDisplayName() { return displayName; }
    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
```

Repository:

```java
import org.springframework.data.repository.CrudRepository;

public interface UserProfileRepository
        extends CrudRepository<UserProfile, String> {
}
```

After `repository.save(new UserProfile("u42", "An"))`, storage uses a **Redis hash** under a key like `profiles:u42`. Hash fields represent properties and may also include mapping metadata depending on configuration, such as a `_class` field. Do not assume the hash contains solely the fields declared in the class or that internal layout remains identical across all versions/configurations.

Roles of the components:

| Component | Responsibility |
|---|---|
| `RedisMappingContext` | Holds entity metadata, properties, and mapping structure |
| `MappingRedisConverter` | Converts back and forth between objects and hash data per the mapping |
| `RedisCustomConversions` | Registers custom converters for types that cannot or should not use default mapping |
| `RedisKeyValueAdapter` / Repository | Coordinates save, read, delete, and repository operations with Redis |
| `@RedisHash`, `@Id` | Declares a Redis entity and its identifier |

**Key boundary:** `@RedisHash("profiles")` does not simply invoke `StringRedisSerializer` or `Jackson2JsonRedisSerializer` on the whole object. Repositories have their own mapping pipeline. Configuring `valueSerializer` on a `RedisTemplate<String, Product>` bean does not make a `UserProfile` Redis Repository store each entity as a single JSON string.

## 9. `RedisCustomConversions`: defining custom type conversions

Suppose the domain has a `EmailAddress` value object:

```java
public record EmailAddress(String value) {}
```

Inside a repository entity:

```java
@RedisHash("profiles")
public class UserProfile {
    @Id
    private String id;
    private EmailAddress email;

    public UserProfile() {}

    // Appropriate getters, setters, and constructors are declared here.
}
```

If you want `EmailAddress` stored as a single UTF-8 byte field inside the Redis hash, register two directional converters explicitly:

```java
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;
import org.springframework.data.convert.WritingConverter;
import org.springframework.data.redis.core.convert.RedisCustomConversions;

@WritingConverter
class EmailAddressToBytes implements Converter<EmailAddress, byte[]> {
    @Override
    public byte[] convert(EmailAddress source) {
        return source.value().getBytes(StandardCharsets.UTF_8);
    }
}

@ReadingConverter
class BytesToEmailAddress implements Converter<byte[], EmailAddress> {
    @Override
    public EmailAddress convert(byte[] source) {
        return new EmailAddress(new String(source, StandardCharsets.UTF_8));
    }
}

@Configuration
class RedisConversionConfig {
    @Bean
    RedisCustomConversions redisCustomConversions() {
        return new RedisCustomConversions(List.of(
                new EmailAddressToBytes(),
                new BytesToEmailAddress()));
    }
}
```

On write:

```text
UserProfile.email: EmailAddress("an@example.com")
       |
       v
EmailAddressToBytes
       |
       v
byte[] UTF-8: "an@example.com"
       |
       v
field "email" in Redis hash
```

On read, `BytesToEmailAddress` restores the value object from the byte sequence. This pattern is useful for **value objects**, custom identifiers, legacy types, or cases requiring exact control over a property's representation. Converters apply only within the registered mapping context; they do not replace the `valueSerializer` of every `RedisTemplate` in the application.

### Principles when writing converters

- Use explicit source and target types and annotate with `@ReadingConverter`/`@WritingConverter` to avoid ambiguity for types the system might convert in both directions.
- Both directions must agree on encoding/format—such as UTF-8, ISO-8601, or a versioned binary schema.
- For value objects with invariants, validate inputs and handle invalid values transparently instead of silently constructing broken objects.
- Once an old converter has written data, changing formats can render historical records unreadable. Plan compatibility or migration upfront.
- Avoid overly broad converters like converting every object to `String`, which can unexpectedly alter how unrelated properties map.

Not every custom type requires a converter. Spring Data Redis can map simple properties and nested objects with default rules. Add converters only when you deliberately want a specific representation, such as a compact layout, legacy compatibility, or preserving value-object invariants.

## 10. Distinguishing a Redis hash from JSON inside a Redis string

These two storage options have different semantics even when representing the same product:

**Option A — JSON in a Redis string:**

```redis
SET catalog:product:v1:p42 '{"id":"p42","name":"Notebook","priceMinor":199000}'
GET catalog:product:v1:p42
```

**Option B — Redis hash with individual fields:**

```redis
HSET catalog:product-hash:v1:p42 id p42 name "Notebook" priceMinor 199000
HGET catalog:product-hash:v1:p42 name
HGETALL catalog:product-hash:v1:p42
```

| Criterion | JSON in a Redis string | Redis hash |
|---|---|---|
| Redis read command | `GET` | `HGET`, `HMGET`, `HGETALL` |
| Updating a single attribute | Typically read/modify/rewrite full payload | Can update one field via `HSET` |
| Java mapping mechanism | Value JSON serializer | Hash mapping or `opsForHash()` |
| Type metadata | Depends on JSON serializer/schema | Depends on converters and mapping metadata |
| TTL | Attached to the whole Redis key | Standard TTL attaches to the Redis key (not individual hash fields) |
| Schema changes | Requires JSON versioning | Requires handling missing/extra fields and converters |

Choose a Redis hash when frequently manipulating individual fields or using Redis Repositories. Choose a JSON string when the unit of read/write is the whole object, you want a clean payload, and cross-language interoperability matters. Neither option is universally optimal: payload size, command count, update frequency, TTL, and indexing needs all influence the choice.

## 11. Serialization in Spring Cache is configured separately

When using Spring Cache backed by Redis, cached entries are handled via `RedisCacheManager` and `RedisCacheConfiguration`. Setting `valueSerializer` on a `RedisTemplate` **does not automatically apply to all caches**.

Example configuring a dedicated `products` cache storing only `Product`:

```java
import java.time.Duration;
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializationContext;

@Configuration
public class ProductCacheConfig {

    @Bean
    RedisCacheManager redisCacheManager(RedisConnectionFactory factory) {
        RedisCacheConfiguration productCache =
                RedisCacheConfiguration.defaultCacheConfig()
                    .entryTtl(Duration.ofMinutes(15))
                    .serializeValuesWith(
                        RedisSerializationContext.SerializationPair.fromSerializer(
                            new Jackson2JsonRedisSerializer<>(Product.class)));

        return RedisCacheManager.builder(factory)
                .withInitialCacheConfigurations(
                        Map.of("products", productCache))
                .build();
    }
}
```

This snippet selects a `Product`-typed JSON serializer specifically for **the cache named `products`**; other caches must be configured per their own data types. Cache entries still follow Spring Cache's key prefix, TTL, and read/write rules. Do not share the same typed serializer across caches holding incompatible object types.

General-purpose JSON serializers support multiple object types by embedding type metadata. That convenience requires reviewing polymorphism settings, where data originates, and class-name stability. When a cache holds a single known value type, a simple typed serializer is usually easier to govern.

Spring Session, Pub/Sub listeners, and other modules can also carry their own serialization settings or key namespaces. Whenever they share Redis, inspect the serializer **on the exact component producing the data**, rather than guessing from an arbitrary `RedisTemplate`.

## 12. Security when deserializing Redis data

Redis is often used as a shared cache or state store across multiple processes. Even inside an internal network, data can arrive from another service, an older version, or an untrusted source. Deserializing binary payloads into Java objects therefore introduces risk.

### Caution with Java native serialization

`JdkSerializationRedisSerializer` relies on Java Object Serialization. If an application deserializes data that external actors can modify or inject into Redis, native Java deserialization can be dangerous, especially when the classpath contains gadget classes with unsafe deserialization behavior.

For new data, prefer **strings, strictly typed JSON, or a controlled binary format**. If legacy systems mandate JDK serialization, restrict data access and configure JVM/library deserialization filters where available.

### Caution with polymorphic JSON

General-purpose Jackson serializers may embed Java class names or type metadata into JSON to reconstruct objects. Never enable permissive default typing on untrusted data without strict type allowlists. Moreover, embedding Java class names in payloads couples stored data to package and class names, making refactoring harder.

### Serializers do not replace access control

Readable JSON is not encryption, and opaque binary formats do not protect sensitive data. Protect sensitive records with authentication, TLS where appropriate, key-pattern ACLs, secret management, and strict retention/TTL policies.

## 13. Changing serializers: data compatibility issues

Suppose v1 stores products using the JDK serializer:

```text
Key: catalog:product:p42
Value: <Java serialization bytes>
```

v2 switches to a Jackson JSON serializer while reading the same key. Redis does not automatically translate old data into JSON. `GET` still returns legacy bytes, and Jackson's `deserialize` throws `SerializationException` or JSON parsing errors.

Changing a serializer is therefore a **data-contract change** comparable to changing a database schema.

A controllable strategy is **key namespace/versioning**:

```text
catalog:product:v1:p42  -> data in legacy format
catalog:product:v2:p42  -> JSON under new schema
```

The new application writes only `v2`. During migration, it can read `v2` first, fall back to reading `v1` with the legacy serializer, and backfill `v2` as needed. For caches easily rebuilt from a source of truth, simply bumping to `v2` and repopulating lazily is often cleaner. For primary operational data, define a full migration and verification plan before dropping old data.

Example procedure:

```text
1. Define v2 format and matching serializer.
2. Deploy code writing v2; prioritize reading v2.
3. For keys present only in v1, decode with v1 serializer and migrate to v2.
4. Preserve remaining TTL if expiration semantics matter.
5. Monitor deserialization errors and unmigrated keys.
6. Remove the v1 read path only once legacy data/behavior is no longer needed.
```

Avoid unbounded “try decoding as JSON, and on error fall back to JDK” logic; it hurts observability, masks corrupt payloads, and prolongs supporting unsafe deserialization paths. Explicit versioned namespaces reduce ambiguity.

### Changing fields or Java types inside JSON

Even when staying on JSON, renaming `priceMinor` to `price`, changing `long` to a complex structure, altering timestamp formats, or renaming packages (when payloads include type metadata) can break compatibility between old and new readers.

Depending on requirements, use migration DTOs, version fields, legacy property aliases, or readers tolerant of multiple schemas for a bounded transition period. Never treat JSON as automatic immunity against schema evolution.

## 14. Key serializers affect Redis Cluster and other clients

In Redis Cluster, hash slots are computed over **key bytes** (accounting for `{...}` hash tags), not Java objects in the application. If two clients encode the same key string into different byte sequences, they compute different slots and effectively access different keys.

For example:

```text
Java key: "shop:product:42"
StringRedisSerializer -> UTF-8 bytes of the string above
JdkSerializationRedisSerializer -> Java serialization header and bytes
```

Consequently, Java services or polyglot services sharing keys should standardize on `StringRedisSerializer`/UTF-8, ID normalization, delimiters, and prefixes. Key names should be predictable; avoid using Java object serialization bytes as Redis keys unless genuinely required.

In Cluster, multi-key commands may require keys to map to the same slot. Hash tags such as `cart:{u42}:items` and `cart:{u42}:total` ensure `{u42}` drives slot calculation when valid. **Serializers and hash tags are separate concerns**: serializers determine the key bytes; hash tags control which substring of those bytes determines the slot.

Changing a key serializer or key naming rule effectively changes storage identifiers. Old keys are not renamed automatically and become unreachable to new application code.

## 15. Common errors and root-cause identification

| Symptom | Likely cause | What to check |
|---|---|---|
| `SerializationException` on `GET` | Reader uses different serializer/type than writer; corrupt payload | Check key, `TYPE`, sample bytes/payload, versions, and writer serializer |
| `GET` returns `null` even though key is visible in Redis | Different key name from serializer/prefix/DB, or TTL expired | Compare key bytes, namespace, DB/Cluster, `EXISTS`, `TTL` |
| `WRONGTYPE` | Running `GET` on a Redis hash or `HGET` on a Redis string | Run `TYPE <key>` before changing read logic |
| `redis-cli` shows garbled characters | Payload is binary or JDK serialized | Identify the source serializer; do not edit raw bytes manually |
| JSON value missing fields or wrong types | Schema/record/class changed, or different Jackson config | Compare payload against active DTO/`ObjectMapper` |
| `opsForHash()` reads wrong fields/values | Confused `hashKeySerializer` or `hashValueSerializer` | Inspect each serializer configured on the template |
| Repository writes many hash fields instead of one JSON | Repository uses `MappingRedisConverter` | Verify whether Repository or `opsForValue()` is being called |
| Cache works in single version, fails during deployment | Versions use different serializers or models | Check `RedisCacheManager` config and schema-versioning strategy |
| Polyglot client cannot find key | Different encoding or key serializer | Standardize UTF-8 string keys and prefixes |

Diagnostic commands in an **authorized environment**:

```bash
redis-cli TYPE catalog:product:v1:p42
redis-cli TTL catalog:product:v1:p42
redis-cli --raw GET catalog:product:v1:p42

# For keys whose Redis type is actually hash:
redis-cli HGETALL profiles:u42
```

For Cluster, use a slot-aware client/CLI (such as `redis-cli -c`); endpoints and credentials depend on environment. Never run `KEYS *` in large-volume environments just to hunt down serializer issues, and never log personal data or secrets while debugging.

### Example: two services writing the same key with different serializers

```text
Service A: StringRedisTemplate
  SET shared:flag "true"

Service B: RedisTemplate<String, Boolean>
  valueSerializer = JdkSerializationRedisSerializer
  GET shared:flag -> deserialization error or unexpected value
```

The fix is agreeing on one shared format—such as the string `"true"`/`"false"`—and configuring both sides with the same serialization contract. If the two services own distinct lifecycles and purposes, give them separate key namespaces to avoid writer conflicts.

## 16. Designing conversion layers with clear responsibilities

In applications handling multiple kinds of Redis data, one generic `RedisTemplate<Object,Object>` shared everywhere hides data types and formats. A more maintainable layout is:

```text
Application service
   |
   +-- ProductRedisStore
   |       +-- RedisTemplate<String, Product>
   |       +-- String key + Product JSON value
   |
   +-- TokenStore
   |       +-- StringRedisTemplate
   |       +-- String key + String value
   |
   +-- UserProfileRepository
   |       +-- Redis Repository
   |       +-- MappingRedisConverter / RedisCustomConversions
   |
   +-- Spring Cache
           +-- RedisCacheManager
           +-- Per-cache RedisCacheConfiguration
```

These components can share the same `RedisConnectionFactory` while owning separate serializers, converters, and data policies. Business services calling `ProductRedisStore.save(product)` stay insulated from Jackson details, encodings, or Redis byte layouts. When formats need updating, changes stay localized to the storage layer and migration flow rather than rippling across business logic.

Practical design principles:

- **Pick the Redis data type first:** string, hash, or another structure depending on required commands and access patterns.
- **Pick the right mapping path:** `RedisTemplate` goes through template serializers; Redis Repositories go through mapping/conversion; Spring Cache uses cache configurations.
- **Declare serializers explicitly:** favor UTF-8 string keys and clearly schema'd value formats for shared data.
- **Scope converters to domain types:** use `RedisCustomConversions` only when a property or value object genuinely needs custom mapping representation.
- **Version long-lived data:** serializers and schemas are part of the contract across application versions and services.
- **Tie TTL and namespaces to intent:** serializers do not provide TTLs or data isolation.
- **Restrict trusted inputs on deserialization:** be cautious with Java serialization and polymorphic JSON.

## 17. Self-check questions

**1. Why can `StringRedisTemplate` read a string while a default `RedisTemplate` might fail on the same key?**

Because the two templates may use different serializers. Sharing a Redis key name does not ensure the payload format matches every decoder. Align serializers or separate namespaces.

**2. Does `RedisTemplate.setValueSerializer(...)` change how `@RedisHash` Repositories map entities?**

Not in the sense of automatically altering repository mapping. Redis Repositories rely on `MappingRedisConverter` and registered custom conversions to read/write Redis hashes. Configure the component directly managing entities.

**3. When should you use `RedisCustomConversions` instead of `Jackson2JsonRedisSerializer`?**

Use custom conversions when controlling how a property or value object maps inside the Redis Repository mechanism. Use a JSON serializer when storing/reading a whole Java value as JSON at a template/cache boundary.

**4. Why can changing a serializer make existing Redis data or caches unreadable?**

Redis only stores bytes. New readers cannot automatically decode arbitrary byte formats produced by legacy writers. Use key versioning, migrations, or rebuild caches from the origin.

**5. When multiple programming languages share Redis, which key serializer usually interoperates best?**

UTF-8 `StringRedisSerializer`, paired with consistent prefixes and ID conventions. For values, agree on an explicit format such as JSON or a language-neutral binary schema decoupled from Java classes.

**6. Why can't a Redis hash and a JSON string for the same object share the same read command?**

Because their Redis data types differ. JSON strings use `GET`, while Redis hashes use `HGET`/`HGETALL`. Matching converters and serializers differ by storage path as well.

### Conclusion

In Spring Data Redis, **`RedisSerializer` defines byte representations in template operations**, **`RedisSerializationContext` groups those rules for reactive APIs**, and **`MappingRedisConverter` plus `RedisCustomConversions` handle object–Redis hash mapping in repositories**. Spring Cache maintains its own serialization config. Identifying each API's data path, aligning key/value formats, versioning schemas, and avoiding untrusted deserialization keep Redis reliable as applications scale and evolve across deployments.
