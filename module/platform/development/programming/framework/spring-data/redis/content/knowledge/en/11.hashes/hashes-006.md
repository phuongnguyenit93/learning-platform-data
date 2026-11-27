# Distinguishing the Hash Key Serializer from the Hash Value Serializer

In Spring Data Redis, when calling `redisTemplate.opsForHash().put("profile:42", "name", "Lan")`, we see three Java values: the Redis key name, the field name inside the Hash, and the field's value. Redis does not store Java objects directly; all of those components are converted to **bytes**. If any of the three serializers disagrees between writer and reader, data can appear missing, fail to decode, or stop working with Redis commands.

The two focal serializers in this lesson:

- **`hashKeySerializer`**: converts **Hash field names** to bytes and decodes field names when reading.
- **`hashValueSerializer`**: converts **Hash field contents** to bytes and decodes field contents when reading.

Easy-to-miss point: "Hash key" here means the **field**, not the top-level Redis key. The top-level Redis key is handled by `keySerializer`.

This lesson is framed around Spring Boot 3.3.x, Spring Data Redis 3.3.x, and `RedisTemplate`/`StringRedisTemplate`. The byte-formatting principles apply more broadly, though APIs and defaults should be checked when changing versions.

## 1. What Components Make Up a Redis Hash?

In Redis CLI:

~~~redis
HSET app:user:42 name "Lan" age "28" city "Da Nang"
HGET app:user:42 name
HGETALL app:user:42
~~~

Data visualization:

~~~text
Redis logical database
└── app:user:42            ← top-level key, Redis type = hash
    ├── name → Lan          ← hash key/field → hash value
    ├── age  → 28
    └── city → Da Nang
~~~

Three independent positions:

| Position | Example | Spring Data Redis serializer |
|---|---|---|
| Top-level Redis key | `app:user:42` | `keySerializer` |
| Hash key / field name | `name`, `age` | `hashKeySerializer` |
| Hash value / field value | `Lan`, `28` | `hashValueSerializer` |

Redis only cares about the bytes of the key, field, and value. It does not know a field name is a Java `String`, that a field means "age", or that a value is a DTO. If two applications point at Redis yet encode fields differently, Redis treats them as two distinct fields.

### 1.1. How Is an HSET Command Encoded?

~~~java
redisTemplate.opsForHash().put(
        "app:user:42",  // Redis key
        "name",         // Hash key: field name
        "Lan"           // Hash value: field content
);
~~~

Conceptually, this call works like:

~~~mermaid
flowchart TD
    A["HashOperations.put(key, field, value)"]
    A --> B["keySerializer → byte[]"]
    A --> C["hashKeySerializer → byte[]"]
    A --> D["hashValueSerializer → byte[]"]
    B --> E["Redis HSET"]
    C --> E
    D --> E
    E --> F["Hash field bytes → value bytes"]
~~~

When reading with `HGET`, Spring Data Redis uses `keySerializer` and `hashKeySerializer` to locate the right key/field. When Redis returns a value, Spring Data Redis uses `hashValueSerializer` to interpret the bytes back into a Java object.

### 1.2. Do Not Confuse `valueSerializer` with `hashValueSerializer`

`RedisTemplate` has four common serializers:

| Property | Primarily affects | Example |
|---|---|---|
| `keySerializer` | Redis keys across operation groups | `GET greeting`, `HGET app:user:42 name` |
| `valueSerializer` | Values of `ValueOperations` | `SET greeting hello` |
| `hashKeySerializer` | Fields in `HashOperations` | `name` in `HGET app:user:42 name` |
| `hashValueSerializer` | Field values in `HashOperations` | `Lan` in `HGET app:user:42 name` |

Therefore, **having called `setValueSerializer(...)` does not mean Hash values automatically use that serializer**. For Hashes, check `getHashValueSerializer()` or configure `setHashValueSerializer(...)`.

Other operation types such as List, Set, or Sorted Set have their own serialization rules according to the template's API. This lesson focuses strictly on Hashes.

## 2. Generic Types of HashOperations vs. Actual Serializers

Spring Data Redis defines:

~~~java
HashOperations<K, HK, HV>
~~~

Where:

- `K` is the Java type of the top-level Redis key.
- `HK` is the Java type of the Hash field name.
- `HV` is the Java type of the Hash field value.

Example:

~~~java
HashOperations<String, String, String> hashes =
        stringRedisTemplate.opsForHash();

hashes.put("app:user:42", "name", "Lan");
String name = hashes.get("app:user:42", "name");
~~~

In this example, all three Java types are String. However, generics only guide the Java compiler. **Java types do not automatically determine byte format.** A `RedisTemplate<String, Object>` can still use JDK serialization; a `RedisTemplate<String, AddressDto>` does not automatically configure a JSON serializer unless told to.

Basic Hash methods and where serializers come into play:

| Method | Redis command | Role |
|---|---|---|
| `put(key, field, value)` | `HSET` | Encode key, field, value |
| `get(key, field)` | `HGET` | Encode key/field; decode value if present |
| `putAll(key, map)` | Multi-field `HSET` | Encode each field/value |
| `entries(key)` | `HGETALL` | Decode **both fields and values** |
| `keys(key)` | `HKEYS` | Decode field names |
| `values(key)` | `HVALS` | Decode field values |
| `hasKey(key, field)` | `HEXISTS` | Encode key/field |
| `delete(key, fields...)` | `HDEL` | Encode key/fields |
| `increment(key, field, delta)` | `HINCRBY` / `HINCRBYFLOAT` | Value in Redis must have a valid numeric representation |

If `get()` returns `null` while `entries()` throws an error, examine how fields are encoded and how returned fields are decoded: the two commands interact with different bytes.

## 3. What Does `hashKeySerializer` Actually Handle?

### 3.1. Field Names Are Matched by Bytes

For the Java String `"name"`:

~~~text
StringRedisSerializer:
  UTF-8 bytes: 6E 61 6D 65

JdkSerializationRedisSerializer:
  Java serialization stream: AC ED 00 05 ...
  (includes metadata for Java String)
~~~

These two representations **differ in bytes**. If application A uses `StringRedisSerializer` to write a field named `name`, and application B uses `JdkSerializationRedisSerializer` to look up `name`, Redis does not treat them as the same field.

Imagine the Hash contains:

~~~text
app:user:42
  field bytes [6E 61 6D 65]                    → "Lan"
  field bytes [AC ED 00 05 ...String "name"]    → "Mai"
~~~

Both fields can coexist. When each client serializes the String `name` in its own format, each reads a different entry. Redis does not deserialize Java objects to compare the semantic meaning of field names.

### 3.2. Wrong Field Serializer Causes False Cache Misses

Suppose A wrote:

~~~java
// A uses hashKeySerializer = StringRedisSerializer
hashA.put("app:user:42", "name", "Lan");
~~~

B reads the same top-level key with a different field serializer:

~~~java
// B uses hashKeySerializer = JdkSerializationRedisSerializer
Object name = hashB.get("app:user:42", "name");
~~~

`name` can come back `null` even though the Redis Hash still contains a text field named `name`. Redis simply receives the field bytes sent by B and does not find them.

This is a **wrong field lookup** issue, not a network failure and not necessarily a `hashValueSerializer` issue. If B calls `entries()`, Redis returns all field bytes; B may then throw an error trying to deserialize the UTF-8 field using the Java deserializer.

### 3.3. Why Is String Usually Used for Field Names?

Field names are typically stable labels:

~~~text
name
email
status
createdAt
shipping
billing
~~~

With `StringRedisSerializer`:

- Field names display clearly in Redis CLI.
- Other clients using UTF-8 can access the same fields.
- No coupling to Java class names or `serialVersionUID`.
- Commands `HGET`, `HDEL`, `HEXISTS` are easy to invoke from other languages.

If field names are derived from user content, standardize character normalization, encoding, and length limits. A String serializer does not automatically perform validation or security checks.

### 3.4. Top-Level Key Serializer Mismatches Happen Even Earlier

If A writes with `keySerializer = StringRedisSerializer`:

~~~text
Redis key bytes → "app:user:42"
~~~

while B uses `keySerializer = JdkSerializationRedisSerializer`, the top-level Redis key itself already has different bytes. B is querying an entirely different key, regardless of whether `hashKeySerializer` is right or wrong.

When data appears lost, inspect **from outside in**:

~~~text
keySerializer       → locates the right Redis key?
hashKeySerializer   → locates the right Hash field?
hashValueSerializer → decodes the field contents properly?
~~~

## 4. `hashValueSerializer` Handles Field Contents

### 4.1. The Same Field Can Hold Different Formats

Suppose the Redis key and field are:

~~~text
app:user:42
  field: profile
~~~

The value can be encoded in several ways:

| Storage format | Example bytes/representation | On read |
|---|---|---|
| UTF-8 String | `Lan` | `StringRedisSerializer` |
| JSON String | `"Lan"` including JSON quotes | JSON serializer for String |
| JSON object | `{"name":"Lan","age":28}` | JSON serializer for DTO |
| Java Serialization | `AC ED 00 05 ...` | Compatible JDK deserializer |
| Protobuf | schema-defined bytes | Matching schema Protobuf parser |

Redis does not store an extra tag saying "this is JSON" on a field. Producer and consumer must agree.

### 4.2. Wrong Value Serializer Usually Causes Decode Errors

Suppose:

~~~text
keySerializer      = StringRedisSerializer
hashKeySerializer  = StringRedisSerializer
~~~

A writes the `profile` field as JSON, while B uses `JdkSerializationRedisSerializer` to read. Redis finds **the exact field** and returns JSON bytes. B then attempts to process them as a Java serialized stream, hitting `SerializationException`, `StreamCorruptedException`, or related errors.

Comparing failure modes:

| Mismatched component | What Redis sees | Common symptom |
|---|---|---|
| `keySerializer` | Different Redis key bytes | Top-level key not found |
| `hashKeySerializer` | Different field bytes | `HGET` returns nil; Java may receive `null` |
| `hashValueSerializer` | Field exists, but value bytes mismatch parser | Deserialization error, wrong result type |
| Same key name used for another Redis type | Key exists, not a HASH | `WRONGTYPE` |

Some parsers can succeed on bytes yet return semantically wrong objects. Thus, "no exception thrown" is not sufficient proof of schema compatibility.

### 4.3. Hash Values Containing Numbers: Watch Redis Commands

A statistics-style Hash:

~~~redis
HSET app:stats:42 views 10
HINCRBY app:stats:42 views 1
HGET app:stats:42 views
~~~

With field value as decimal text `10`, Redis `HINCRBY` can increment it to `11`.

If the value is actually Java-serialized bytes of Integer `10`, or a JSON String with quotes `"10"`, Redis does not consider it a valid decimal integer and can return an error:

~~~text
ERR hash value is not an integer
~~~

Therefore, serializers must fit **the Redis commands you need to run**, not just convenience during Java deserialization.

## 5. When to Choose `StringRedisTemplate`?

`StringRedisTemplate` uses String serializers for Redis keys/values and Hash fields/values, making it well suited for Hashes storing text or string-formatted numbers.

~~~java
import java.util.Map;

import org.springframework.data.redis.core.HashOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class UserProfileHashStore {

    private final HashOperations<String, String, String> hashes;

    public UserProfileHashStore(StringRedisTemplate redis) {
        this.hashes = redis.opsForHash();
    }

    public void save(String userId, String name, String city) {
        hashes.putAll(
                "app:user:" + userId,
                Map.of("name", name, "city", city)
        );
    }

    public String findName(String userId) {
        return hashes.get("app:user:" + userId, "name");
    }

    public Map<String, String> findAll(String userId) {
        return hashes.entries("app:user:" + userId);
    }

    public void removeCity(String userId) {
        hashes.delete("app:user:" + userId, "city");
    }
}
~~~

After calling:

~~~java
store.save("42", "Lan", "Da Nang");
~~~

you can inspect via Redis CLI:

~~~redis
TYPE app:user:42
HGET app:user:42 name
HGET app:user:42 city
HKEYS app:user:42
HGETALL app:user:42
~~~

Field names and values are human-readable. `HGET app:user:42 name` returns `"Lan"` if the key/field has not been modified, deleted, or expired.

For numeric data, `StringRedisTemplate` does not automatically convert `"28"` to a Java Integer. The application must parse and validate appropriately:

~~~java
String rawAge = hashes.get("app:user:42", "age");

if (rawAge == null) {
    // Missing field, handle according to business logic.
} else {
    int age = Integer.parseInt(rawAge);
}
~~~

Do not automatically treat every absent field as 0, as that can mask data errors.

## 6. Explicitly Configuring All Four Serializers on RedisTemplate

An explicit configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration(proxyBeanMethods = false)
public class TextHashRedisConfiguration {

    @Bean("textHashRedisTemplate")
    RedisTemplate<String, String> textHashRedisTemplate(
            RedisConnectionFactory connectionFactory
    ) {
        RedisTemplate<String, String> template = new RedisTemplate<>();
        template.setConnectionFactory(connectionFactory);

        StringRedisSerializer text = new StringRedisSerializer();

        template.setKeySerializer(text);
        template.setValueSerializer(text);
        template.setHashKeySerializer(text);
        template.setHashValueSerializer(text);

        return template;
    }
}
~~~

Naming the bean `textHashRedisTemplate` avoids accidentally overriding the default `redisTemplate` bean. When multiple templates exist, inject with `@Qualifier` so each service selects the right serializer.

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.HashOperations;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class TextHashUsage {

    private final HashOperations<String, String, String> hashes;

    public TextHashUsage(
            @Qualifier("textHashRedisTemplate")
            RedisTemplate<String, String> template
    ) {
        this.hashes = template.opsForHash();
    }

    public void write() {
        hashes.put("app:demo:1", "field", "value");
    }
}
~~~

### 6.1. A Very Common Mistake: Setting Only key/value Serializers

~~~java
RedisTemplate<String, String> template = new RedisTemplate<>();
template.setConnectionFactory(connectionFactory);

template.setKeySerializer(new StringRedisSerializer());
template.setValueSerializer(new StringRedisSerializer());

// Forgot setHashKeySerializer(...)
// Forgot setHashValueSerializer(...)
~~~

The author may assume `opsForHash()` also uses the String serializer, yet `hashKeySerializer` and `hashValueSerializer` are two independent settings. If left unset, RedisTemplate's default serializer mechanism may populate **JdkSerializationRedisSerializer**, depending on template configuration.

Then the top-level key is readable in Redis CLI because `keySerializer` is String, while field names and values look like binary Java data. A client using `StringRedisTemplate` will not be able to read them the same way.

**Check all four serializers** when designing a custom `RedisTemplate`, especially if the application shares a keyspace with other services.

### 6.2. Disabling the Default Serializer Does Not Mean "Use String"

`RedisTemplate` has a default serializer and a flag controlling whether to enable it. Disabling default serializer population can leave unconfigured slots handling raw bytes or exhibiting API/driver-dependent behavior.

The reliable approach is to explicitly configure serializers for every operation type the bean uses. Do not treat `enableDefaultSerializer=false` as an automatic way to apply UTF-8.

## 7. String Hash Fields with JSON DTO Values

If every field holds an object of the same type, you can use String for the Hash key and typed JSON for the Hash value.

Example:

~~~text
app:user:42:addresses (HASH)
  shipping → {"city":"Da Nang","street":"12 Tran Phu"}
  billing  → {"city":"Hue","street":"8 Le Loi"}
~~~

### 7.1. DTO

~~~java
public record AddressDto(
        String city,
        String street
) {
}
~~~

### 7.2. Typed Template

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration(proxyBeanMethods = false)
public class AddressHashConfiguration {

    @Bean("addressHashRedisTemplate")
    RedisTemplate<String, AddressDto> addressHashRedisTemplate(
            RedisConnectionFactory connectionFactory,
            ObjectMapper objectMapper
    ) {
        RedisTemplate<String, AddressDto> template =
                new RedisTemplate<>();

        template.setConnectionFactory(connectionFactory);

        StringRedisSerializer text = new StringRedisSerializer();

        Jackson2JsonRedisSerializer<AddressDto> json =
                new Jackson2JsonRedisSerializer<>(
                        objectMapper,
                        AddressDto.class
                );

        template.setKeySerializer(text);
        template.setHashKeySerializer(text);
        template.setValueSerializer(json);
        template.setHashValueSerializer(json);

        return template;
    }
}
~~~

Here:

- Top-level Redis keys and Hash field names are serialized as UTF-8 text.
- Hash field values are serialized as JSON for `AddressDto`.
- `valueSerializer` is also JSON in case the application wants to use `opsForValue()` with the same DTO, though this setting **does not replace `hashValueSerializer`**.

Usage:

~~~java
import java.util.Map;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.HashOperations;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class AddressHashStore {

    private final HashOperations<String, String, AddressDto> hashes;

    public AddressHashStore(
            @Qualifier("addressHashRedisTemplate")
            RedisTemplate<String, AddressDto> template
    ) {
        this.hashes = template.opsForHash();
    }

    public void save(String userId, AddressDto address) {
        hashes.put(
                "app:user:" + userId + ":addresses",
                "shipping",
                address
        );
    }

    public AddressDto find(String userId) {
        return hashes.get(
                "app:user:" + userId + ":addresses",
                "shipping"
        );
    }

    public Map<String, AddressDto> findAll(String userId) {
        return hashes.entries("app:user:" + userId + ":addresses");
    }
}
~~~

When calling:

~~~java
store.save("42", new AddressDto("Da Nang", "12 Tran Phu"));
~~~

`HGET app:user:42:addresses shipping` returns the DTO's JSON. Another service can read it if both agree on JSON schema, key names, field names, and encoding.

### 7.3. Do Not Force One Typed Serializer Across Heterogeneous Value Types

A Hash containing:

~~~text
name      → "Lan"
age       → 28
profile   → {"city":"Da Nang"}
~~~

is not a fit for `Jackson2JsonRedisSerializer<AddressDto>` across all fields, because `name` and `age` are not `AddressDto`.

Options include:

- Store all field values as Strings, parsing and validating per field name.
- Split Hashes by value type, using one typed DTO per Hash.
- Store the whole object as one JSON value in a Redis STRING if per-field operations are not needed.
- Build an explicit schema and format if there is a strong reason to keep heterogeneous value types in one Hash.

Using a generic JSON serializer with type metadata can store multiple classes, but increases versioning complexity and deserialization risks for untrusted types. Prefer typed DTOs with explicit schemas whenever possible.

## 8. Practical Failure Matrix When Two Services Disagree on Serializers

Suppose service A writes a Hash with String serializers, and service B tries to read the same data:

| A writes | B reads | Likely outcome |
|---|---|---|
| String key, String field, String value | Same three serializers | Reads accurately |
| String key, String field, String value | JDK key, String field, String value | Cannot find top-level Redis key |
| String key, String field, String value | String key, JDK field, String value | `HGET` may return `null` due to different field bytes |
| String key, String field, JSON value | String key, String field, JDK value | Finds field, fails deserialization |
| String key, String field, String value | String key, String field, typed JSON value | May fail parsing or produce off-schema values |
| Uses Redis STRING at key `app:user:42` | B calls HashOperations on that key | `WRONGTYPE` |

Not every mismatch manifests the same way. When diagnosing, pinpoint whether the failure occurs at **locating the Redis key**, **locating the Hash field**, or **decoding the Hash value**.

### 8.1. `get()` Returns `null`: What to Check?

Example:

~~~java
String name = hashes.get("app:user:42", "name");
~~~

`null` can mean:

1. The top-level Redis key does not exist yet, expired via TTL, or was evicted.
2. The Redis key exists, but field `name` has not been written or was deleted.
3. `keySerializer` produces a different Redis key name than the writer used.
4. `hashKeySerializer` produces different field bytes than the writer used.
5. The application is pointing to the wrong Redis instance or logical database.

Inside a queued pipeline or transaction, many APIs also return `null` **temporarily because the response is not yet available**. That differs from an executed `HGET` where Redis returned nil.

### 8.2. `entries()` Fails While `get()` Simply Returns null

`get()` sends only the field bytes produced by the current serializer. If those field bytes do not match, Redis returns nil. By contrast, `entries()` pulls every field/value from Redis and deserializes each one; a field or value written by an older version can trigger an exception.

How to investigate: inspect the Redis key type, existing fields in Redis CLI, and the actual bean serializers wired into the Java code. Do not rush to delete data before finding the root cause.

### 8.3. `WRONGTYPE` Is Not a Hash Serializer Error

~~~redis
SET app:user:42 "hello"
HGET app:user:42 name
~~~

Redis key `app:user:42` currently has type STRING, so calling `HGET` returns `WRONGTYPE`. Changing `hashValueSerializer` will not change the key's type; resolve the keyspace collision or migrate the data.

## 9. Changing Serializers Does Not Migrate Existing Data

Suppose a legacy system wrote Hash values using Java native serialization:

~~~text
Before deploy:
  key: app:user:42
  field: profile  (UTF-8)
  value: AC ED 00 05 ...  (Java serialized object)

After deploy:
  same key and field
  app reads with JSON serializer, expecting JSON bytes
~~~

Switching the bean to JSON does not rewrite existing data in Redis. When the JSON parser encounters Java binary bytes, decoding fails.

Similarly, changing `hashKeySerializer` can cause multiple fields representing the same logical name with different bytes, leaving the Hash with semantically duplicate entries.

### 9.1. Migration Strategy for Reconstructible Cache

If another database is the canonical data source, you can version the keyspace:

~~~text
Legacy: app:user:42:addresses
New:    app:user:v2:42:addresses
~~~

Process:

1. Define serializers and schema for the new version.
2. New code reads/writes only `v2` keys.
3. Cache misses on `v2` read from the canonical database and populate the new cache.
4. Legacy keys expire naturally via TTL or are cleaned up by an authorized job.
5. After all consumers have migrated, remove the legacy serializers and code.

Do not implement a "try JSON, fall back to JDK deserialize" pattern on every request for bytes that could be altered by untrusted sources. Java native deserialization carries its own risks; migrations must enforce trust boundaries.

If Redis is the sole data store and cannot be reconstructed, migration requires reading legacy data in a controlled environment, transforming it, reconciling record counts, and having a rollback plan before deleting old data.

## 10. Inspecting with Redis CLI

In environments where inspection is permitted:

~~~bash
redis-cli TYPE app:user:42
redis-cli HLEN app:user:42
redis-cli HKEYS app:user:42
redis-cli HGET app:user:42 name
redis-cli HGETALL app:user:42
redis-cli TTL app:user:42
~~~

Meaning:

- `TYPE` confirms the top-level Redis key is indeed a HASH.
- `HLEN` shows the field count; useful when `get()` returns `null`.
- `HKEYS` returns field name bytes (the CLI attempts to render them).
- `HGET` reads the value of a specific field.
- `HGETALL` returns all fields/values, which can look unreadable if binary-encoded.
- `TTL` shows the TTL of the **top-level Redis key**.

Under the standard model, `EXPIRE app:user:42 ...` sets TTL for the entire Hash. Newer Redis versions offer field expiration features; specific support depends on Redis server, driver, and Spring Data Redis versions. Serializers are not a mechanism for managing per-field TTLs.

### 10.1. Checking Which Serializers a Bean Uses

A temporary inspection snippet for development environments:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Component;

@Component
public class RedisSerializerInspector {

    public RedisSerializerInspector(
            @Qualifier("addressHashRedisTemplate")
            RedisTemplate<String, AddressDto> template
    ) {
        System.out.println("key: " + template.getKeySerializer());
        System.out.println("value: " + template.getValueSerializer());
        System.out.println("hash key: " + template.getHashKeySerializer());
        System.out.println("hash value: " + template.getHashValueSerializer());
    }
}
~~~

This is a temporary example for verifying bean wiring. There is no need to keep `System.out.println` in production. If multiple `RedisTemplate` beans exist, inspect the exact bean injected into the service reading/writing the Hash; checking a different template proves nothing about the active code path.

Having the right current serializer for the new format also does not prove all existing keys already hold bytes in that format.

## 11. Serializers, Hash Mapping, and Redis Repositories Are Not the Same

Spring Data Redis includes object-to-Hash mapping mechanisms and Redis Repositories with `@RedisHash`, `@Id`, and `@Indexed`. Distinguish these layers:

| Layer | Purpose | Example |
|---|---|---|
| Object-to-Hash mapping | Converts a Java object into logical field/value pairs | `name → Lan`, `age → 28` |
| Hash serialization | Converts each logical field/value into bytes | UTF-8, JSON, Java serialization |
| Repository mapping | Manages keyspace, IDs, indexes, and entity lifecycle | `@RedisHash`, `@Id` |

A `HashMapper` can produce a map of fields/values from an object, yet communication with Redis still requires consistent byte representations. With repositories, the framework may also manage separate metadata/index keys. Changing serializers on a custom `RedisTemplate` **does not automatically change all formats used by Redis Repositories**.

Writing directly into a Hash managed by a repository can corrupt indexes/metadata or write fields with mismatched serializers. Decide who owns each key group and keep mapping and serialization rules consistent.

## 12. Security and Cross-Service Compatibility

### 12.1. Avoid Casual Use of Java Native Serialization

`JdkSerializationRedisSerializer` uses Java Object Serialization. Deserializing untrusted byte streams can trigger unexpected code execution or resource consumption via classpath gadgets/hooks. Risk depends on byte provenance and the application classpath.

For Hashes shared across services or storing externally influenced data, prefer:

- `StringRedisSerializer` for Redis keys and Hash fields.
- Strings for simple data and numbers that need direct Redis command operations.
- Typed JSON DTOs or well-defined schemas for structured objects.

Even JSON needs appropriate parser settings, schema validation, and type-resolution policies. Do not allow arbitrary Java class instantiation from type metadata in untrusted payloads.

### 12.2. Cross-Language Data Contracts

If Java, Python, and Node.js share a Redis Hash, all parties must agree on:

~~~text
Redis key encoding: UTF-8
Hash field encoding: UTF-8
Hash value encoding: JSON per predefined schema
Schema version: 2
~~~

Also define how to handle missing fields, empty values, literal `"null"` strings vs. JSON `null`, numeric types, timezones, TTLs, and schema versions. Never assume every language converts types identically.

### 12.3. Generics Do Not Replace Serializers

~~~java
RedisTemplate<String, AddressDto> template;
~~~

does not mean the template stores Hash values as JSON. Only when `setHashValueSerializer(...)` is configured accordingly will bytes match the desired format. To verify, inspect the runtime serializer and actual stored bytes, not just the generic signature.

## 13. Decision Table for Choosing Redis Hash Serializers

| Use case | Redis key | Hash key | Hash value |
|---|---|---|---|
| User profile with simple String fields | String | String | String |
| Statistics needing `HINCRBY` | String | String | Decimal text |
| Hash holding multiple addresses of the same DTO type | String | String | Typed JSON for `AddressDto` |
| Hash shared across Java/Node/Python | Agreed encoding | Agreed encoding | Cross-language JSON/schema |
| Legacy system storing Java binary | Inspect existing data | Inspect actual format | Plan controlled migration |

Key principles:

1. **`hashKeySerializer` manages field names**, not the top-level Redis key name.
2. **`hashValueSerializer` manages field value bytes**, independently of `valueSerializer`.
3. **`opsForHash()` needs three compatible serializers**: key, hash key, and hash value.
4. **Use String for field names whenever possible** for observability, integration, and direct commands.
5. **Choose the value serializer based on data type and commands**: numbers needing `HINCRBY`, JSON DTOs needing schemas, text needing consistent encoding.
6. **When seeing `null`, check key and field** before assuming the value failed to decode.
7. **When hitting deserialization errors, check schema/value serializer** after confirming key/field lookup matched.
8. **Changing serializers does not rewrite Redis**: version the keyspace or run an explicit migration.
9. **Explicitly configure all four serializers when creating a custom RedisTemplate**, and inject the right bean.
10. **Do not mix manual writes with repositories** without understanding mappings and internal keys.

A Redis Hash is simply a structure of **Redis key → field bytes → value bytes**. Mastering this boundary lets you explain why the same Java field can turn into two distinct Redis fields, why `HGET` can return `null` even though data is right there, and why changing `hashValueSerializer` can break reads of older data.

## References

- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Data Redis — Serializers](https://docs.spring.io/spring-data/redis/reference/redis/serializers.html)
- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html)
- [Spring Data Redis API — RedisTemplate](https://docs.spring.io/spring-data/redis/docs/3.3.x/api/org/springframework/data/redis/core/RedisTemplate.html)
- [Spring Data Redis API — HashOperations](https://docs.spring.io/spring-data/redis/docs/3.3.x/api/org/springframework/data/redis/core/HashOperations.html)
- [Redis — Hashes](https://redis.io/docs/latest/develop/data-types/hashes/)
- [Redis — HGET](https://redis.io/docs/latest/commands/hget/)
- [Redis — HSET](https://redis.io/docs/latest/commands/hset/)
- [Redis — HINCRBY](https://redis.io/docs/latest/commands/hincrby/)
