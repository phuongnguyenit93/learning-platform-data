# Configuring Generic Types and Serializers of RedisTemplate

When working with **Spring Data Redis**, a statement like `redisTemplate.opsForValue().set("product:42", product)` looks like an operation on a Java `Map`. However, Redis does not understand `Product`, `Long`, or `LocalDateTime` directly. Redis stores **byte sequences** under its data structures. Therefore, the application must decide:

- What types will Java treat the **key** and **value** as when programming?
- By what rules are those values **encoded into bytes** and **decoded from bytes**?
- Do String values, Hash fields, and Hash values need different serialization approaches?
- Which `RedisTemplate` instances can read data written by another instance?
- What happens when changing serializers in a system that already has data?

The two central concepts of this lesson are **the generic type parameters `RedisTemplate<K, V>`** and **`RedisSerializer`**. They are related but not interchangeable: **generics determine the types used at compile time, while serializers determine what bytes are actually stored in Redis**.

## 1. Where Does RedisTemplate Sit in the Data Flow?

~~~text
                        Spring Boot Application
                                 |
                   RedisTemplate<String, Product>
                        (Java API / generics)
                                 |
                       RedisSerializer for:
                 key / value / hash key / hash value
                                 |
                      byte[] of key and value
                                 |
                          RedisConnection
                                 |
                          Lettuce / Jedis
                                 |
                           Redis server
                                 |
                      byte[] stored in Redis
~~~

When calling `opsForValue().set(key, value)`, `RedisTemplate` typically performs the following steps:

1. Accepts `key` and `value` as Java objects.
2. Uses the **key serializer** to convert the key into bytes.
3. Uses the **value serializer** to convert the value into bytes.
4. Sends the Redis command through `RedisConnectionFactory` and the driver.
5. When reading back, uses the corresponding serializer to decode bytes into Java objects.

For example, the same Java value `42L`:

| Serializer | Bytes written (description) | Visible in Redis CLI | Reading with another serializer |
|---|---|---|---|
| `StringRedisSerializer` with string `"42"` | UTF-8 for the two characters `4` and `2` | `42` | Java/JDK serializer does not recognize this as a serialized object |
| `GenericToStringSerializer<Long>` | String representation of the number, usually `42` | `42` | Requires a serializer that accepts numeric strings |
| `JdkSerializationRedisSerializer` | Binary with Java serialization format header | Not readable as plain text | String/JSON serializer cannot decode it |
| JSON serializer for an appropriate object | JSON bytes, e.g., `{"id":42}` | Readable as JSON | Java/JDK serializer does not read it as a JDK object |

Redis has no built-in mechanism to auto-detect JSON, Java serialization, or class names. The serializer used at **read** time must be compatible with the data that was written.

## 2. Understanding the Two Generic Parameters: RedisTemplate<K, V>

Basic declaration:

~~~java
public class RedisTemplate<K, V> {
    // Redis operations with key type K and value type V
}
~~~

A template:

~~~java
RedisTemplate<String, ProductSnapshot> productRedisTemplate;
~~~

means:

- `K = String`: methods that accept a primary Redis key are programmed with `String`.
- `V = ProductSnapshot`: operations working directly with values typically use `ProductSnapshot`.

Example:

~~~java
ProductSnapshot product =
        new ProductSnapshot(42L, "SKU-42", "Keyboard");

productRedisTemplate.opsForValue()
        .set("shop:product:42", product);

ProductSnapshot loaded = productRedisTemplate.opsForValue()
        .get("shop:product:42");
~~~

Here, generic types help the compiler check calls and the IDE suggest the right types. However, **declaring generics does not automatically select JSON, String, or Java serialization**. `RedisTemplate` needs the appropriate serializer for operations to be converted accurately.

### 2.1. Generics Are Java Type Checking, Not a Redis Schema

Java implements generics via type erasure: at runtime, generic type information does not automatically turn into a Redis schema. These two templates can both access the key `shop:product:42`:

~~~java
RedisTemplate<String, ProductSnapshot> productTemplate;
RedisTemplate<String, String> stringTemplate;
~~~

However, they are **not automatically compatible**. If `productTemplate` writes JSON and `stringTemplate` reads using `StringRedisSerializer`, the result may just be a JSON string rather than a `ProductSnapshot`. If one template uses JDK serialization and another uses JSON, deserialization can fail.

Generic types also do not prevent another service from writing invalid data to the same key via Redis CLI or a different template. **The storage contract must be defined at the keyspace, serializer, and data schema levels**.

### 2.2. Common Declarations

| Declaration | Suitable for | Conditions |
|---|---|---|
| `StringRedisTemplate` | String keys and values, counters, markers, status codes | Template operations use string serializers |
| `RedisTemplate<String, String>` | A template dedicated to strings | Must configure String serializer for key/value |
| `RedisTemplate<String, ProductSnapshot>` | Values are objects of a specific type | Value serializer must be able to handle `ProductSnapshot` |
| `RedisTemplate<String, Long>` | Java values representing numbers | Serializer must produce a format suitable for the Redis commands being called |
| `RedisTemplate<String, byte[]>` | Binary values already encoded by the application | Requires a byte-array serializer |
| `RedisTemplate<String, Object>` | Multiple different value types | Requires a clear type metadata/format strategy; easily increases migration risk |

**Avoid using `RedisTemplate<Object, Object>` for every feature just because it is flexible.** A template with specific types usually makes the data contract easier to understand and reduces serializer mix-ups.

## 3. Serializer Positions in RedisTemplate

`RedisTemplate` has several independent serializer properties:

| Property | Used for | Example |
|---|---|---|
| `keySerializer` | Primary Redis key | `shop:product:42` |
| `valueSerializer` | String values, List/Set/ZSet elements, and corresponding APIs | JSON-encoded `ProductSnapshot` |
| `hashKeySerializer` | Redis Hash field | `name`, `price`, `stock` |
| `hashValueSerializer` | Value of a field in a Redis Hash | `"Keyboard"`, `"199000"` |
| `stringSerializer` | Certain String-typed arguments in Redis operations requiring string conversion | Not a switch that replaces all other serializers |
| `defaultSerializer` | Fallback for serializers not explicitly configured, if the default mechanism is enabled | May be a Java/JDK serializer |

When working with a Hash:

~~~text
Redis key:    shop:product:42
    field:    name
    value:    "Keyboard"
    field:    stock
    value:    "16"
~~~

`keySerializer` encodes `shop:product:42`; `hashKeySerializer` encodes `name` and `stock`; `hashValueSerializer` encodes the field values.

Do not confuse `hashKeySerializer` with the serializer for the **primary key**. Hash key here means **the field name inside the Hash**, not `shop:product:42`.

### 3.1. HashOperations Has Its Own Generics

API:

~~~java
HashOperations<K, HK, HV> hashOps = redisTemplate.opsForHash();
~~~

Where:

- `K`: primary Redis key.
- `HK`: hash field.
- `HV`: hash field value.

The two types `HK` and `HV` **do not have to match `V` of RedisTemplate**. For example, a `RedisTemplate<String, ProductSnapshot>` can still operate on a Hash whose fields and values are both `String`, provided `hashKeySerializer` and `hashValueSerializer` are configured appropriately:

~~~java
HashOperations<String, String, String> hashOps =
        productRedisTemplate.opsForHash();

hashOps.put("shop:product:42:metrics", "views", "125");
String views = hashOps.get("shop:product:42:metrics", "views");
~~~

However, you must actively decide the field/value types. Because `opsForHash()` can infer generic types from the target variable, the compiler does not verify that the runtime serializers are actually compatible.

### 3.2. Which Commands Use the Value Serializer?

At a high level:

- `opsForValue()`: String value.
- `opsForList()`: List elements.
- `opsForSet()`: Set members.
- `opsForZSet()`: Sorted Set members; scores remain numeric per the Redis protocol.
- `opsForHash()`: uses separate **hash key** and **hash value** serializers.
- Low-level operations via `RedisConnection` may work directly with byte arrays and do not necessarily go through the template's serializers.

Pub/Sub, Streams, script execution, or low-level callback APIs may have their own serializer contracts depending on the method. When using specialized features, check how that API accepts and returns bytes rather than assuming it follows the general `valueSerializer`.

## 4. Defaults of RedisTemplate and StringRedisTemplate

### 4.1. Default RedisTemplate Does Not Automatically Convert Objects to JSON

A `RedisTemplate` initialized with standard configuration may use `JdkSerializationRedisSerializer` as the default serializer for positions that are not explicitly configured.

Consequences:

- The key `"shop:product:42"` may be stored as Java binary serialization instead of human-readable UTF-8 text.
- `redis-cli --raw GET ...` may show unreadable bytes.
- Data is tightly coupled to Java classes, how Java serialization works, and compatibility across version changes.
- Unsuitable when Redis needs to be read directly by multiple languages or services using a shared format.

In Spring Boot, configuring:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
~~~

only specifies how to connect to Redis; **it does not mean your RedisTemplate bean is configured for JSON**. You must inspect the actual bean and any customizers used by the application.

### 4.2. StringRedisTemplate for String Keys and Values

`StringRedisTemplate` is a straightforward choice when you want key names and values to be readable in Redis CLI:

~~~java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class PageViewCounter {

    private final StringRedisTemplate redis;

    public PageViewCounter(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Long increment(long productId) {
        return redis.opsForValue()
                .increment("shop:product:views:" + productId);
    }

    public String getStatus(String jobId) {
        return redis.opsForValue()
                .get("shop:job:status:" + jobId);
    }
}
~~~

`StringRedisTemplate` configures string serializers for key, value, hash field, and hash value. It is very useful for:

- Counters using `INCR`/`DECR`.
- Markers with a TTL.
- Status strings such as `"PENDING"`/`"DONE"`.
- Hashes whose field names and values are both strings.
- Cases where an automatic object mapper is not needed.

To store objects via `StringRedisTemplate`, the application can convert objects to a JSON String itself before calling `set()` and parse them back on read; or use `RedisTemplate<String, ProductSnapshot>` with a JSON serializer so conversion is handled by the template.

### 4.3. Be Careful with Counters and JDK Serialization

Redis `INCR` requires the current value to represent a **Redis-compatible string integer**, not a serialized Java object.

If you create `RedisTemplate<String, Long>` but leave the value serializer as JDK binary, and then call `increment` or mix it with an `INCR` command from Redis CLI, the data may be incompatible.

The simplest and most accurate example for a counter:

~~~java
Long newValue = stringRedisTemplate
        .opsForValue()
        .increment("shop:metric:orders");
~~~

Do not infer from `V = Long` that Redis will store the string `"123"`. **It is the serializer and the Redis command type that determine compatibility**.

## 5. Configuring RedisTemplate<String, ProductSnapshot> with JSON

Suppose the project uses **Spring Boot 3.x, Spring Data Redis 3.x, and Jackson 2**, with a simple DTO:

~~~java
package com.example.shop.redis;

public record ProductSnapshot(
        Long id,
        String sku,
        String name
) {}
~~~

This is an object placed into Redis for the application to read back, and does not need to be a JPA entity. It is best to use a stable storage DTO and avoid accidentally serializing an entire entity graph with complex relationships.

Configuring a dedicated template:

~~~java
package com.example.shop.redis;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class ProductRedisTemplateConfig {

    @Bean("productRedisTemplate")
    public RedisTemplate<String, ProductSnapshot> productRedisTemplate(
            RedisConnectionFactory connectionFactory,
            ObjectMapper objectMapper) {

        RedisTemplate<String, ProductSnapshot> template =
                new RedisTemplate<>();

        template.setConnectionFactory(connectionFactory);

        StringRedisSerializer textSerializer =
                new StringRedisSerializer();

        Jackson2JsonRedisSerializer<ProductSnapshot> jsonSerializer =
                new Jackson2JsonRedisSerializer<>(
                        objectMapper, ProductSnapshot.class
                );

        template.setKeySerializer(textSerializer);
        template.setValueSerializer(jsonSerializer);

        // This example application uses String for Hash field and Hash value.
        template.setHashKeySerializer(textSerializer);
        template.setHashValueSerializer(textSerializer);

        template.afterPropertiesSet();
        return template;
    }
}
~~~

**Meaning of each choice:**

- `RedisTemplate<String, ProductSnapshot>` creates a Java API with String keys and ProductSnapshot values.
- `setKeySerializer(new StringRedisSerializer())` stores keys as UTF-8 text, making debugging convenient and compatible with Redis CLI tools.
- `setValueSerializer(jsonSerializer)` converts `ProductSnapshot` into JSON bytes and reads them back as `ProductSnapshot`.
- `setHashKeySerializer(textSerializer)` sets Hash field names to strings.
- `setHashValueSerializer(textSerializer)` establishes a **separate contract**: Hash field values will be String if using `HashOperations` with that type.
- `afterPropertiesSet()` initializes the template after configuration; Spring also invokes bean lifecycle callbacks when managing beans, and calling it explicitly in the example simply demonstrates the initialization step.

The Jackson serializer constructor pattern above corresponds to the Spring Data Redis branch using Jackson 2. JSON serializer APIs may differ between Spring Data Redis/Jackson versions; in a real project, choose the constructor supported by the dependencies in use.

### 5.1. Using via @Qualifier

If an application has multiple `RedisTemplate` beans, you should explicitly specify which bean is used:

~~~java
package com.example.shop.redis;

import java.time.Duration;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductSnapshotStore {

    private final RedisTemplate<String, ProductSnapshot> redis;

    public ProductSnapshotStore(
            @Qualifier("productRedisTemplate")
            RedisTemplate<String, ProductSnapshot> redis) {
        this.redis = redis;
    }

    public void save(ProductSnapshot product) {
        String key = "shop:product:" + product.id();
        redis.opsForValue().set(
                key, product, Duration.ofMinutes(20)
        );
    }

    public ProductSnapshot find(long productId) {
        return redis.opsForValue()
                .get("shop:product:" + productId);
    }

    public void remove(long productId) {
        redis.delete("shop:product:" + productId);
    }
}
~~~

The goal here is to store a JSON snapshot with a 20-minute TTL. In Redis CLI, if the value is JSON written by the serializer, you can read it:

~~~bash
redis-cli --raw GET shop:product:42
redis-cli TTL shop:product:42
~~~

Illustrative output of `GET`:

~~~json
{"id":42,"sku":"SKU-42","name":"Keyboard"}
~~~

The actual JSON shape depends on `ObjectMapper` (naming strategy, date/time modules, inclusion rules, and other settings). Do not couple another system to a JSON shape that has not been formalized as a contract.

### 5.2. Why Use an Injected ObjectMapper?

Spring Boot can configure a shared `ObjectMapper` with time modules, naming strategies, or null-handling rules. Using the injected mapper bean helps the serializer adhere to the formatting decisions managed by the application.

However, **sharing an ObjectMapper does not mean Redis JSON must necessarily match HTTP JSON**. Redis data has its own deployment compatibility requirements and TTLs; sometimes a mapper configured specifically for Redis DTOs is needed, as long as it is managed consistently.

Do not let minor REST response changes accidentally break compatibility with Redis-stored data if Redis holds long-lived entries.

## 6. Configuring for Hash: Field Serializer Different from Value Serializer

Suppose you need to store a Hash:

~~~text
HSET shop:product:42:info name "Keyboard"
HSET shop:product:42:info category "accessories"
~~~

You can use `StringRedisTemplate`:

~~~java
import org.springframework.data.redis.core.HashOperations;
import org.springframework.data.redis.core.StringRedisTemplate;

public class ProductHashStore {

    private final HashOperations<String, String, String> hashOps;

    public ProductHashStore(StringRedisTemplate template) {
        this.hashOps = template.opsForHash();
    }

    public void putName(long id, String name) {
        hashOps.put("shop:product:" + id + ":info", "name", name);
    }

    public String getName(long id) {
        return hashOps.get("shop:product:" + id + ":info", "name");
    }
}
~~~

For a Hash whose values are objects, configure `hashValueSerializer` according to that object type:

~~~java
template.setHashKeySerializer(new StringRedisSerializer());
template.setHashValueSerializer(
        new Jackson2JsonRedisSerializer<>(
                objectMapper, ProductSnapshot.class
        )
);
~~~

Then:

~~~java
HashOperations<String, String, ProductSnapshot> hashOps =
        template.opsForHash();

hashOps.put("shop:product:snapshots", "42", product);
ProductSnapshot p =
        hashOps.get("shop:product:snapshots", "42");
~~~

Changing a Hash value from String to a JSON object is a **data contract change**. An existing Hash field storing `"Keyboard"` will not automatically become `{"name":"Keyboard"}`, and the ProductSnapshot serializer will not necessarily be able to read the old data.

### 6.1. Can One Template Have Value Type ProductSnapshot and HashValue Type String?

Yes. The serialization groups are independent. For example:

~~~text
SET shop:product:42 <ProductSnapshot JSON>
HSET shop:product:42:metrics views "125"
~~~

The same template can do:

~~~java
RedisTemplate<String, ProductSnapshot> productRedisTemplate;

productRedisTemplate.opsForValue().get("shop:product:42");
// -> ProductSnapshot (JSON valueSerializer)

HashOperations<String, String, String> metrics =
        productRedisTemplate.opsForHash();

metrics.get("shop:product:42:metrics", "views");
// -> String (String hashValueSerializer)
~~~

This is valid when the serializers are configured properly. However, a single template holding too many different storage policies becomes harder to maintain. When two data groups have significantly different serialization/TTL/ownership rules, using **two clearly named templates** helps reduce errors.

## 7. Common Serializers and How to Choose

| Serializer | Suitable data | Advantages | Notes |
|---|---|---|---|
| `StringRedisSerializer` | `String` | UTF-8, easy to inspect and interact with via Redis CLI | Does not automatically convert arbitrary objects to JSON |
| `GenericToStringSerializer<T>` | Types with a stable String representation | Can convert numbers/simple types to strings via conversion | Requires consistent read/write converters |
| `JdkSerializationRedisSerializer` | Java objects via Java serialization | Simple when Serializable classes are compatible | Hard-to-read binary, tightly coupled to Java classes, security risk when deserializing untrusted data |
| `Jackson2JsonRedisSerializer<T>` | JSON of a specific type (Jackson 2 branch) | Clear format, typed Java API | Requires managing ObjectMapper/schema and class compatibility |
| `GenericJackson2JsonRedisSerializer` | Multiple dynamic Java types (Jackson 2 branch) | Capable of storing type info for dynamic types | Type metadata, payload size, and deserialization safety must be controlled |
| Byte-array serializer | `byte[]` | Preserves binary data controlled by the application | The application is responsible for formatting and decoding |

In newer versions of Spring Data Redis/Jackson, JSON serializer class names and constructors may differ. The examples in this lesson use the Spring Data Redis 3.x/Jackson 2 API branch to illustrate the contract rather than asserting every version is identical.

### 7.1. StringRedisSerializer: The Default Choice for Keys

UTF-8 keys are easy to understand:

~~~bash
redis-cli GET shop:job:status:123
redis-cli TYPE shop:product:42
redis-cli TTL shop:product:42
~~~

If keys use JDK binary serialization, typing `shop:product:42` in the CLI will not find the key because **the key bytes are different**. The problem is not that Redis lacks the key, but that the serialized bytes differ from the string typed in.

A common convention for applications with multiple data types:

- Primary key: String serializer.
- Hash field: String serializer.
- Value: depends on data type—can be String, JSON, or bytes.
- Hash field value: chosen independently according to the field's meaning.

### 7.2. GenericToStringSerializer<T> for Simple Value Types

For example, if you want the Java API to use `Long` while Redis bytes are numeric strings:

~~~java
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.GenericToStringSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

RedisTemplate<String, Long> numericTemplate = new RedisTemplate<>();
numericTemplate.setConnectionFactory(connectionFactory);
numericTemplate.setKeySerializer(new StringRedisSerializer());
numericTemplate.setValueSerializer(
        new GenericToStringSerializer<>(Long.class)
);
numericTemplate.afterPropertiesSet();
~~~

This snippet is a configuration fragment where `RedisConnectionFactory connectionFactory` is already available, not a complete application. The `Long` value uses a string representation via a converter, which can be suitable for Redis numeric commands if the actual representation matches a format Redis accepts.

For ordinary counters, `StringRedisTemplate.opsForValue().increment()` remains the simpler and more transparent choice.

### 7.3. JDK Serialization: Understanding the Risks

Java serialization produces bytes containing JVM metadata and rules. Some drawbacks:

- Key/value bytes are difficult to read with non-Java tools.
- Class changes can render old data impossible to deserialize.
- Interoperability with applications written in other languages is inconvenient.
- Deserializing untrusted binary data can cause serious security issues depending on classpath and configuration.

When Redis can be written to from untrusted sources, **do not use default Java deserialization as a mechanism for accepting arbitrary objects**. Restrict data sources, Redis write permissions, and object types, and choose a storage format with a clear contract.

### 7.4. Typed JSON vs. Dynamic JSON

**Typed JSON**:

~~~text
RedisTemplate<String, ProductSnapshot>
  -> Jackson2JsonRedisSerializer<ProductSnapshot>
  -> reads this key back as ProductSnapshot
~~~

**Dynamic JSON**:

~~~text
RedisTemplate<String, Object>
  -> serializer with type metadata
  -> reads back into various object types depending on metadata
~~~

The dynamic style can be convenient for polymorphic caches, but embedding Java class names in payloads ties the schema to package/class naming and increases the risk of deserializing unintended types. Do not enable broad default typing for uncontrolled data. Prefer DTOs and allowlists of permitted types if the application needs polymorphism.

JSON also does not guarantee security on its own: for sensitive data, design access control, encryption as required, and retention policies independently of serializer selection.

## 8. Redis Data Types That Require Thinking About Byte Format

### 8.1. String and Counters

~~~text
SET shop:job:status:123 DONE
INCR shop:metric:orders
~~~

String values or text-formatted integers work well with `StringRedisTemplate`. Do not write a `Long` with Java serialization and expect `INCR` to understand it as a number.

### 8.2. List, Set, and Sorted Set

With `RedisTemplate<String, ProductSnapshot>` using a JSON value serializer:

~~~java
redis.opsForList().rightPush("shop:recent-products", product);
redis.opsForSet().add("shop:featured-products", product);
redis.opsForZSet().add("shop:ranked-products", product, 95.5);
~~~

Elements of a List, Set, or ZSet are serialized using the template's **value serializer**. The ZSet score is a number managed by Redis, not the same bytes as `ProductSnapshot`.

Note when using objects as Set/ZSet members: Redis uniqueness is based on **serialized bytes**, not Java `equals()`. If the same product has JSON with a different field order or different metadata, Redis may treat it as two distinct members.

For Sets/ZSets that require stable identity, many systems choose to store **String IDs** instead of full JSON objects and fetch details from a separate key.

### 8.3. Hash

Hash has two additional serializers for fields and field values. A template using JSON for String values and String for Hash values is a valid configuration; conversely, forgetting `setHashValueSerializer` can cause Hash values to be written as JDK binary even when String values are stored as JSON.

### 8.4. Pub/Sub, Streams, and Scripts

Advanced Redis APIs may use their own codec/serialization rules for channels, messages, stream records, script args, and results. Do not assume that:

~~~java
template.setValueSerializer(jsonSerializer);
~~~

automatically sets JSON for **all** channels, fields, and payloads across every Redis API. For each feature, verify which data is serialized by the template and which is handled directly by callbacks or the driver.

## 9. Configuring Multiple RedisTemplates in the Same Application

A system may need both JSON for product caching and Strings for counters and markers.

~~~text
                       RedisConnectionFactory
                               |
               +---------------+---------------+
               |                               |
       StringRedisTemplate           productRedisTemplate
       key/value: String             key: String
       hash: String                  value: ProductSnapshot JSON
               |                               |
               +----------------+--------------+
                                |
                              Redis
~~~

Example service injecting two templates:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductMetricsService {

    private final StringRedisTemplate counters;
    private final RedisTemplate<String, ProductSnapshot> snapshots;

    public ProductMetricsService(
            StringRedisTemplate counters,
            @Qualifier("productRedisTemplate")
            RedisTemplate<String, ProductSnapshot> snapshots) {
        this.counters = counters;
        this.snapshots = snapshots;
    }

    public void viewed(long productId) {
        counters.opsForValue()
                .increment("shop:product:views:" + productId);
    }

    public ProductSnapshot snapshot(long productId) {
        return snapshots.opsForValue()
                .get("shop:product:" + productId);
    }
}
~~~

**Sharing a RedisConnectionFactory does not mean sharing serializers.** Each template has its own encoding policy and can use the same Redis server or topology.

When defining custom beans in Spring Boot:

- Give beans clear, meaningful names.
- Use `@Qualifier` when disambiguation is needed.
- Check auto-configuration conditions so you do not accidentally replace a default bean used by another component.
- Do not declare multiple beans with the same name unless intentionally overriding.
- Let Spring manage the lifecycle of the factory and templates rather than creating a new template per request.

## 10. Do Redis Cache and Spring Session Automatically Use RedisTemplate's Serializer?

They do not do so by default.

| Component | Primary serialization configuration |
|---|---|
| `RedisTemplate` | `setKeySerializer`, `setValueSerializer`, `setHashKeySerializer`, `setHashValueSerializer` |
| `StringRedisTemplate` | String serializers provided by the template |
| Spring Cache with Redis | `RedisCacheManager` and `RedisCacheConfiguration` |
| Spring Session with Redis | Repository and serializer dedicated to Spring Session, depending on configuration/version |
| Redis Repository | Repository keyspace mapping, converters, and serialization rules |

For example, changing:

~~~java
productRedisTemplate.setValueSerializer(jsonSerializer);
~~~

**does not mean** `@Cacheable` has switched to JSON or that HTTP session attributes have changed format. These components have their own abstractions and configurations, even though they may share the same `RedisConnectionFactory`.

For Redis Cache, you can configure `RedisCacheConfiguration.serializeValuesWith(...)` with an appropriate `RedisSerializationContext.SerializationPair`. For Spring Session, the serializer mechanism must be configured according to the corresponding Spring Session contract, not by arbitrarily modifying a `RedisTemplate`.

## 11. Java Types and JSON Schema When Upgrading Application Versions

Suppose Redis currently stores:

~~~json
{"id":42,"sku":"SKU-42","name":"Keyboard"}
~~~

In a new version, the DTO changes to:

~~~java
public record ProductSnapshot(
        Long id,
        String sku,
        String name,
        String category
) {}
~~~

With some Jackson configurations, the new missing field in JSON may receive `null`; with strict configurations or validation, deserialization may fail. Renaming fields or changing numeric types, enum types, package/class names, or date formats can also cause unintended backward-compatibility issues.

Treat Redis values as **schema-bound data**, even though Redis does not enforce a schema:

1. Define Redis storage DTOs separately from HTTP DTOs if their lifecycles differ.
2. Specify which serializer and ObjectMapper own each keyspace.
3. Bound TTLs of temporary data to shorten the window where multiple schemas coexist.
4. If a major format change is needed, use a version prefix such as `v2:shop:product:42`.
5. Choose a migration or dual-read strategy during rolling deployments.
6. Delete old keys only when you are certain no components still need to read them.

### 11.1. Migrating from JDK Binary to JSON

Scenario:

~~~text
Old version: key is serialized with JDK
             value is serialized with JDK

New version: key is UTF-8
             value is JSON
~~~

If the new version calls:

~~~java
jsonTemplate.opsForValue().get("shop:product:42");
~~~

it may receive `null` even though Redis still contains the old data. Reason: the UTF-8 key bytes of `"shop:product:42"` **differ** from the key bytes serialized with JDK.

If the key matches but the old value is JDK bytes, the new JSON serializer may throw a deserialization error. These are two distinct failure modes:

- **Data not found** because the key bytes changed.
- **Key found, but value unreadable** because the value serializer changed.

A migration strategy may include:

~~~text
1. Write new data using schema v2
2. During transition, try reading v2 first
3. On v2 miss, read via the corresponding v1 template/serializer
4. On v1 read success, convert to DTO v2 and write back
5. Monitor v1 read rate, wait for TTL or run planned cleanup
6. Remove v1 fallback once no old keys need to be served
~~~

In a migration using Redis Cluster, changing key bytes can also change the hash slot. Topology, multi-key operations, and data migration feasibility must be considered—not just swapping the Java serializer.

### 11.2. Do Not Write Multiple Schemas to the Same Key Per Request

If two application versions run concurrently—the old version writing JDK and the new version writing JSON to the same key—the stored data depends on whichever request wrote last. One side may succeed while the other fails.

During rolling deployments, schemas/serializers must be compatible for both **reads** and **writes**, or key namespaces must be clearly separated.

## 12. Null, TTL, and Deleted Data

Serializers do not determine TTL by themselves. For example:

~~~java
redis.opsForValue().set(
        "shop:product:42",
        product,
        Duration.ofMinutes(20)
);
~~~

TTL is determined by the Redis `SET` command or the template's expiration mechanism. The value serializer only encodes `product` into bytes.

Do not confuse these cases:

- `GET` on a non-existent key returns `null` through the API.
- A serializer may accept bytes representing JSON `null` under its own contract, if permitted.
- Spring Cache can choose to cache `null` or skip `null` depending on `RedisCacheConfiguration`.
- Specific `RedisTemplate` methods may behave differently when `null` is passed to a write operation.

In particular, **do not assume every `set(key, null)` means deleting the key**. Use `delete(key)` when the intent is deletion; if you need to store a "no value" state, define an explicit data format or marker.

## 13. Measuring Size and Inspecting Actual Stored Bytes

Redis CLI is useful for inspecting stored data:

~~~bash
redis-cli TYPE shop:product:42
redis-cli --raw GET shop:product:42
redis-cli STRLEN shop:product:42
redis-cli MEMORY USAGE shop:product:42
redis-cli TTL shop:product:42
~~~

Explanation:

- `TYPE` returns the Redis data type, such as String or Hash.
- `GET` lets you view the value when the key exists and is of type String.
- `STRLEN` returns the byte length of the **String value** in Redis, not the length of the key name.
- `MEMORY USAGE` returns Redis's estimated memory usage for the key/value.
- `TTL` shows the remaining lifetime of a key with an expiration.

If a key is JDK-serialized, typing its text name in the CLI may not find it. If the value is stored as JDK binary, `GET` will not show readable JSON. With a JSON serializer, `GET` can display JSON, though field order and metadata depend on the mapper.

### 13.1. Comparing Serializer Size

Two formats of the same object can use different byte counts. When evaluating in practice:

1. Save the same sample data under separate prefixes with their corresponding serializers.
2. Compare `STRLEN` for String values or `MEMORY USAGE` for relevant keys.
3. Also account for CPU conversion cost, bandwidth, value size, and migration complexity.
4. Test realistic payload distributions: small objects, large objects, null fields, long lists, Unicode.
5. Do not switch the whole system to another format just because a tiny sample saves a few bytes.

Choosing a serializer is a decision about **compatibility and clarity** before it is a micro-optimization of storage size.

## 14. Common Mistakes

### Mistake 1: Declaring Generics but Forgetting Serializers

~~~java
RedisTemplate<String, ProductSnapshot> template = new RedisTemplate<>();
template.setConnectionFactory(factory);
template.afterPropertiesSet();
~~~

Depending on configuration, the template may use a default serializer that does not match the intended JSON format. **Generics do not configure serialization**.

### Mistake 2: Setting Only valueSerializer and Forgetting keySerializer

~~~java
template.setValueSerializer(jsonSerializer);
// keySerializer is not configured
~~~

Keys may be serialized with the default serializer, resulting in the CLI not finding keys by readable names. Configure the key serializer explicitly.

### Mistake 3: Configuring a String Serializer for Objects

~~~java
RedisTemplate<String, ProductSnapshot> template = new RedisTemplate<>();
template.setValueSerializer(new StringRedisSerializer());
~~~

`StringRedisSerializer` does not automatically accept a `ProductSnapshot` object and serialize it to JSON. Type errors may occur when called, even though the template's generic declares `ProductSnapshot`.

### Mistake 4: Same Key Name, Different Encodings Across Two Templates

~~~text
StringRedisTemplate:               UTF-8 key, UTF-8 value
Default JDK-style RedisTemplate:   binary key, binary value
~~~

A key displaying the same name in Java can produce two different byte keys; if the key serializer matches but the value serializers differ, reading the data can fail.

### Mistake 5: Forgetting hashValueSerializer

`opsForHash()` uses dedicated hash settings. Switching the value serializer to JSON does not automatically switch all hash values to JSON.

### Mistake 6: Using Java Objects Directly in Redis Counters

`INCR`/`DECR` require a numeric format that Redis understands. A `Long` serialized as JDK binary is unsuitable. Prefer `StringRedisTemplate` for counters.

### Mistake 7: Using a Generic JSON Serializer with Uncontrolled Type Metadata

Polymorphic object formats may embed class information. For payloads from untrusted sources, unsafe deserialization settings can create security risks; it also breaks easily when packages or classes are renamed. Restrict allowed types and Redis write permissions.

### Mistake 8: Changing Serializers in Production Without Migrating Data

Changing byte encoding makes old keys unfindable or old values unreadable. Versioned keys, backward-compatible readers, and a key cleanup plan may be needed.

### Mistake 9: Assuming RedisTemplate Configuration Affects Cache and Session

`RedisCacheManager` and Spring Session have their own configurations. Modifying a `RedisTemplate` bean does not automatically change the serializers of every Redis-backed abstraction.

### Mistake 10: Using an Overly Generic Template for All Data Types

`RedisTemplate<String,Object>` storing all kinds of objects with varying schemas makes migrations hard to control. Use dedicated templates or keyspaces with clear contracts, especially for critical data.

## 15. Practice Exercises

### Exercise A: Choosing a Template for Simple Data

The application needs to store:

~~~text
shop:job:status:123 -> "DONE"
shop:metric:orders  -> 125
~~~

Appropriate choice: `StringRedisTemplate`. Status is read as a String; the counter uses `opsForValue().increment()` so Redis operates on a numeric string.

### Exercise B: Storing a Product JSON DTO

Requirement: `ProductSnapshot` with id/sku/name, meaningful keys, and a 20-minute TTL.

Solution approach: `RedisTemplate<String,ProductSnapshot>`, `StringRedisSerializer` for keys, typed JSON value serializer, `set(key, value, Duration)`. Read using the same serializer once the schema is defined.

### Exercise C: Hash Containing String Fields

~~~text
shop:product:42:metrics
   views  -> "125"
   likes  -> "9"
~~~

Solution approach: `HashOperations<String,String,String>` with both `hashKeySerializer` and `hashValueSerializer` using String. Independent of the `ProductSnapshot` DTO value serializer.

### Exercise D: Two Services Sharing the Same Redis

Service A writes `ProductSnapshot` using typed Jackson JSON; Service B, written in another language, needs to read the same data.

Solution approach: establish a contract for **UTF-8 key bytes, stable JSON schema, naming convention, versioning, TTL, and update policy**. Do not use Java JDK serialization as a cross-language exchange format.

### Exercise E: Migrating a System from JDK Serializer to JSON

Do not simply change `setValueSerializer` and deploy all instances. You must identify the old key serializer, prepare a v2 namespace or data conversion, ensure two concurrent versions can read/write safely, monitor the transition, and clean up old data.

## 16. Workflow for Choosing Generics and Serializers for a Feature

~~~text
                   Need to store data in Redis
                                |
                   What is the Java data type?
                    /                       \
             String / counter            DTO / object
                    |                       |
            StringRedisTemplate    Are there arbitrary types?
                    |                 /           \
                    |                No           Yes
                    |                |             |
                    |          Typed JSON      Design type
                    |          serializer       contract
                    |                |             |
                    +----------------+-------------+
                                     |
                         Is primary key a String?
                                     |
                            String key serializer
                                     |
                       Are Redis Hash ops needed?
                             /              \
                           Yes              No
                            |                |
                    Choose hash field/       |
                    hash value serializers   |
                            +--------+-------+
                                     |
                          Schema and TTL clear?
                                     |
                           Keyspace has owner?
                                     |
                         Configure dedicated bean
                         and inject via Spring DI
                                     |
                        Operations: inspect bytes,
                        migration, and compatibility
~~~

Four rules to remember:

1. **`RedisTemplate<K,V>` is a Java type contract**. It does not guarantee Redis knows what K/V are.
2. **The serializer is the byte contract in Redis**. Read and write formats must be compatible, including across services and application versions.
3. **Key, value, hash key, and hash value have separate serializers**. Choose them deliberately for each data structure.
4. **Do not change serializers while ignoring existing data**. When changing key bytes or value schemas, design migrations and manage namespaces/TTLs accordingly.

Choosing the right generic parameters and serializers from the start makes Spring Data Redis code easier to read, keys easier to operate, data shareable in a controlled manner, and avoids hard-to-detect bugs during application upgrades.
