# JSON Serialization and Choosing Version-Appropriate Serializers in Spring Data Redis

When a Java application writes an object to Redis, Redis does not directly store Java classes, records, or objects. Redis receives a **byte sequence (`byte[]`)** sent by the client. **Serialization** is the process of turning a Java value into storable bytes; **deserialization** is the process of interpreting those bytes back into Java data when reading. Choosing a serializer dictates how keys appear in Redis, value formatting, compatibility across deployments, and security risks.

With **Spring Data Redis**, JSON is often chosen for application data and caches because it is easy to inspect, relatively language-agnostic, and convenient for managing structure. However, **no single JSON serializer fits every project and every version**. Specifically, Spring Data Redis 3.x is tied to Jackson 2; starting from Spring Data Redis 4.0, the primary JSON APIs switch to Jackson 3, changing class names and several important default behaviors. This lesson helps you choose the right serializer, write configurations for each version branch, control type metadata, and plan upgrades for existing data.

## 1. What Should You Master After This Lesson?

1. Distinguish **key serializer**, **value serializer**, **hash-key serializer**, and **hash-value serializer** in `RedisTemplate`.
2. Explain the differences among `StringRedisSerializer`, `Jackson2JsonRedisSerializer<T>`, `GenericJackson2JsonRedisSerializer`, `JacksonJsonRedisSerializer<T>`, `GenericJacksonJsonRedisSerializer`, and `JdkSerializationRedisSerializer`.
3. Decide when to use **typed JSON** (a concrete DTO type) and when to consider **generic JSON** (multiple runtime types).
4. Recognize API differences between Spring Data Redis 3.x/Jackson 2 and 4.x/Jackson 3 to avoid compilation errors or misreading data.
5. Configure JSON serializers for `RedisTemplate` and `RedisCacheManager` in the exact places they are used.
6. Understand issues around metadata such as `@class`, type erasure, stale cache data, schema evolution, and migration strategies.
7. Inspect actual values in Redis and isolate serialization errors, deserialization errors, mismatched key formats, cache misses, or incompatibilities.

Prerequisites: knowing how to create a Spring Boot application, configure `@Bean` definitions, inject services, use `RedisTemplate`/`StringRedisTemplate` at a basic level, and knowing Redis supports String, Hash, List, and Set data types.

## 2. Data Actually Stored in Redis

Suppose a Java service holds an object:

~~~java
public record ProductSnapshot(
        String id,
        String name,
        java.math.BigDecimal price
) {}

ProductSnapshot p =
        new ProductSnapshot("42", "Keyboard", new java.math.BigDecimal("590000"));
~~~

With an appropriate JSON serializer, the Redis String may hold a JSON string:

~~~json
{"id":"42","name":"Keyboard","price":590000}
~~~

Flow diagram:

~~~text
Java ProductSnapshot
       |
       | value serializer
       v
JSON bytes: {"id":"42", ...}
       |
       | Redis client sends SET command
       v
Redis key -> value byte sequence
       |
       | client GET, receives byte[]
       v
JSON bytes
       |
       | value deserializer + target type
       v
Java ProductSnapshot
~~~

JSON here is simply a **format inside a Redis String**. Redis does not understand `ProductSnapshot` objects on its own and does not automatically turn JSON into a Redis Hash. When using `opsForValue().set(...)`, Redis stores the value under type String regardless of whether the value is plain text, JSON, or binary.

For example:

~~~redis
TYPE shop:product:42
GET shop:product:42
TTL shop:product:42
~~~

If keys are written with `StringRedisSerializer` and a JSON value serializer, Redis CLI can read both the key name and the JSON. If keys were written with Java native serialization, key names may contain binary bytes and `GET shop:product:42` will not find the key you thought shared the same name.

### 2.1. Keys and Values Can Use Completely Different Serializers

A `RedisTemplate<K, V>` typically has four serializer slots:

| Setting | Data Converted | Manageable Choice |
| --- | --- | --- |
| `setKeySerializer(...)` | Keys of commands such as `GET`, `SET`, `DEL` | `StringRedisSerializer` |
| `setValueSerializer(...)` | Values of key-based commands like `GET`/`SET` | JSON serializer matching the data type |
| `setHashKeySerializer(...)` | Fields inside a Redis Hash, e.g., `name`, `price` | `StringRedisSerializer` |
| `setHashValueSerializer(...)` | Field values inside a Redis Hash | Schema-dependent: String, JSON, or appropriate serializer |

**Do not use a JSON serializer for ordinary keys just because values are JSON.** String keys are directly readable in the CLI, easy to track by namespace, and clear when multiple systems access Redis.

### 2.2. JSON Does Not Automatically Preserve All Java Traits

For example, JSON:

~~~json
{"id":"42","price":590000}
~~~

does not specify whether `price` should be a `BigDecimal` or `Integer`, does not tell which Java class produced the object, and carries no schema version unless designed by the application. During deserialization, the client needs either a **target type** or **valid type information** to reconstruct the data.

This explains why typed serializers and generic serializers behave differently.

## 3. Version Map: Spring Data Redis 3.x vs. 4.x

Before copying any JSON serializer example, identify the exact versions of **Spring Boot, Spring Data Redis, and Jackson** your build uses. Spring Boot typically manages versions via BOM/dependency management; do not swap only the Spring Data Redis or Jackson artifact without checking compatibility.

| Item | Spring Data Redis 3.x (typically with Boot 3.x) | Spring Data Redis 4.x (typically with Boot 4.x) |
| --- | --- | --- |
| Primary JSON library | Jackson 2 | Jackson 3 |
| `ObjectMapper` package | `com.fasterxml.jackson.databind.ObjectMapper` | `tools.jackson.databind.ObjectMapper` |
| Typed JSON serializer | `Jackson2JsonRedisSerializer<T>` | `JacksonJsonRedisSerializer<T>` |
| Generic JSON serializer | `GenericJackson2JsonRedisSerializer` | `GenericJacksonJsonRedisSerializer` |
| JSON ↔ Redis Hash mapper | `Jackson2HashMapper` | `JacksonHashMapper` |
| Default generic behavior | Jackson 2 generic serializer usually enables default typing on default construction | Jackson 3 generic serializer **does not enable default typing automatically** |
| `RedisSerializer.json()` | Prior to 4.0 uses generic Jackson 2 | From 4.0 switches to generic Jackson 3 |
| Jackson 2 API status | Primary API on 3.x branch | Marked deprecated for removal on 4.x branch |

**Common point of confusion:** The Jackson 3 serializer names in Spring Data Redis 4.x are `JacksonJsonRedisSerializer` and `GenericJacksonJsonRedisSerializer`. Some early 4.0 milestone docs mentioned names containing `Jackson3`; when writing code for a stable release, check the JavaDoc of the exact version you are using.

In Jackson 3, most APIs moved packages from `com.fasterxml.jackson.*` to `tools.jackson.*`. **Notable exception:** many Jackson annotations remain in `com.fasterxml.jackson.annotation.*`, per the migration guide. Do not change annotation imports on a hunch.

### 3.1. How to Check Which Version Is Running

With Maven, inspect the dependency tree:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework.data:spring-data-redis
./mvnw dependency:tree -Dincludes=com.fasterxml.jackson.core:jackson-databind
./mvnw dependency:tree -Dincludes=tools.jackson.core:jackson-databind
~~~

With Gradle, use `dependencies` or `dependencyInsight`:

~~~bash
./gradlew dependencyInsight --dependency spring-data-redis --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

These are suggested commands for learners working on practice projects, not required during authoring. On Windows, use `mvnw.cmd` or `gradlew.bat` if your environment does not support Unix shell scripts.

Beyond library names, also check the Spring Boot version declared in the parent/BOM, active starters, and Java runtime. **The dependency tree output is the authoritative source showing which classes are actually on the classpath.**

## 4. Choosing Serializers by Data Type and Flexibility

| Serializer / Storage Approach | Used For | Strengths | Limitations and Notes |
| --- | --- | --- | --- |
| `StringRedisSerializer` | Keys, text, short codes, stringified numbers | Simple; readable in Redis CLI | Does not automatically turn JSON into objects |
| `Jackson2JsonRedisSerializer<T>` (3.x) | A single known DTO/record type | Clean JSON, typed when reading | Coupled to Jackson 2; requires knowing the exact target type |
| `JacksonJsonRedisSerializer<T>` (4.x) | A single known DTO/record type | Jackson 3 counterpart, easy schema control | Must configure Jackson 3 matching the version |
| `GenericJackson2JsonRedisSerializer` (3.x) | Multiple Java types stored under `Object` | Supports runtime type metadata | Metadata may embed class names; security and migration risks |
| `GenericJacksonJsonRedisSerializer` (4.x) | Generic data using Jackson 3 | Provides builder to control typing | **Does not enable typing by default**; must decide how types are restored |
| `JdkSerializationRedisSerializer` | Legacy Java systems already using Java binary serialization | Can restore Java objects under suitable conditions | Hard to debug, tightly coupled to Java classes, security and compatibility issues |
| `RedisSerializer.byteArray()` | Data with custom codecs, binary protocols | Leaves contents untouched | Application takes full responsibility for byte format |
| Redis Hash with string fields | Small properties needing individual operations | `HGET`/`HSET` per field | Needs conventions for schema, field types, and key-level TTL |

### 4.1. First Decision: Typed JSON or Generic JSON?

**Typed JSON** fits best when a namespace or cache stores a single DTO shape:

~~~text
shop:product:42  -> ProductSnapshot
shop:product:43  -> ProductSnapshot
shop:product:44  -> ProductSnapshot
~~~

The application knows `ProductSnapshot` ahead of time when reading, so JSON does not need to carry Java class names. This keeps the format compact, easy to share, and less coupled to code package names.

**Generic JSON** is useful when a single read path must handle multiple runtime types:

~~~text
cache:shared:key-A  -> ProductSnapshot
cache:shared:key-B  -> CustomerSummary
cache:shared:key-C  -> InventoryNotice
~~~

If the template is declared as `RedisTemplate<String, Object>`, the generic deserializer must know how to determine the concrete type. With only `Object` and plain JSON, it typically reconstructs `Map`/`List`/scalars or generic structures, **not the exact domain record/class**. Restoring subtypes requires a carefully designed type information mechanism.

**Default starting choice for most systems:** String keys, typed JSON values for DTOs with clear schemas, and caches partitioned by data type. Only consider generic JSON when polymorphism is genuinely required.

### 4.2. Why Not Use One `RedisTemplate<String, Object>` Everywhere?

Declaring generic `Object` lets services pass many types, at a cost:

1. The compiler cannot verify that a given key always holds the right DTO.
2. The deserializer may return `LinkedHashMap` instead of the expected class if type metadata is missing.
3. Type metadata can depend on class/package names, causing refactors to break reads of existing data.
4. Uncontrolled default typing carries deserialization risks on untrusted data.
5. One module can accidentally overwrite another module's key with a different schema.

Whenever application design allows, **one typed template per intentional data group** is far easier to govern.

## 5. Shared Baseline Example: ProductSnapshot

The following examples use Java 17+, Spring Boot with the Redis starter, and a running Redis server. Minimal model:

~~~java
package com.example.redis;

import java.math.BigDecimal;

public record ProductSnapshot(
        String id,
        String name,
        BigDecimal price
) {}
~~~

Sample entries will be stored under keys:

~~~text
shop:v1:product:42
shop:v1:product:43
~~~

The prefix `shop:v1` is an illustrative namespace/schema version; **you do not have to use this exact name**. The example product uses `BigDecimal` to avoid carelessly using `double` for prices. In real systems, also standardize currency units, rounding rules, JSON versioning, and missing-field rules.

Basic Maven dependencies when Spring Boot manages versions:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-json</artifactId>
    </dependency>
</dependencies>
~~~

This is only the dependency block; a project also needs the proper Spring Boot parent/BOM or build setup. Spring Boot 3.x uses Jackson 2 by default in the JSON starter; Spring Boot 4.x switches to Jackson 3 as the default. If a project includes other JSON modules or a custom BOM, inspect the dependency tree and compatibility before copying sample code.

Local Redis configuration example:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
~~~

If the app runs in Docker alongside Redis, `localhost` inside the app container does not point to the Redis container. Use the appropriate network hostname/service name. Never commit production Redis credentials into source code.

## 6. Configuring Typed JSON for Spring Data Redis 3.x (Jackson 2)

This is the common branch in **Spring Boot 3.x / Spring Data Redis 3.x** applications. Class to import:

~~~java
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
~~~

**Do not replace this class with `JacksonJsonRedisSerializer` while your project still uses Spring Data Redis 3.x**, because the new class does not exist in that branch.

Create `ProductRedisConfig.java`:

~~~java
package com.example.redis;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration(proxyBeanMethods = false)
public class ProductRedisConfig {

    @Bean("productRedisTemplate")
    public RedisTemplate<String, ProductSnapshot> productRedisTemplate(
            RedisConnectionFactory connectionFactory) {

        RedisTemplate<String, ProductSnapshot> template = new RedisTemplate<>();
        template.setConnectionFactory(connectionFactory);

        StringRedisSerializer keySerializer = new StringRedisSerializer();
        Jackson2JsonRedisSerializer<ProductSnapshot> valueSerializer =
                new Jackson2JsonRedisSerializer<>(ProductSnapshot.class);

        template.setKeySerializer(keySerializer);
        template.setValueSerializer(valueSerializer);

        // If using Redis Hash operations, select serializers for fields/values.
        template.setHashKeySerializer(keySerializer);
        template.setHashValueSerializer(valueSerializer);

        return template;
    }
}
~~~

**Explanation:**

- `RedisConnectionFactory` is auto-configured by Spring Boot when using the Redis starter with valid configuration. No manual factory creation is needed for this serializer lesson.
- `keySerializer` converts String keys into readable bytes in Redis CLI.
- `valueSerializer` converts `ProductSnapshot` to JSON bytes and knows how to restore `ProductSnapshot.class`.
- `hashValueSerializer` in this example assumes Hash field values are whole `ProductSnapshot` objects. If your Hash has string fields like `name`/`price`, use a different serializer matching that schema. Do not use this pattern for every Hash by default.
- `@Bean("productRedisTemplate")` helps services inject the right bean when the app defines multiple `RedisTemplate` instances. Spring invokes the appropriate template initialization lifecycle when managing the bean.

When you want to customize how Jackson 2 reads/writes, pass `com.fasterxml.jackson.databind.ObjectMapper` via the constructor (do not use `setObjectMapper(...)`, which has been deprecated since 3.0):

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;

// objectMapper: Jackson 2 bean configured appropriately by the application.
Jackson2JsonRedisSerializer<ProductSnapshot> valueSerializer =
        new Jackson2JsonRedisSerializer<>(
                objectMapper,
                ProductSnapshot.class
        );
~~~

For `Instant`, `LocalDateTime`, enums, or custom value objects, verify the mapper has the required modules/features and that date/time formats stay compatible across deployments. HTTP JSON working properly does not guarantee your Redis mapper shares the same configuration if you instantiate `new ObjectMapper()` separately.

## 7. Configuring Typed JSON for Spring Data Redis 4.x (Jackson 3)

From Spring Data Redis 4.0 onward, the corresponding class is:

~~~java
import org.springframework.data.redis.serializer.JacksonJsonRedisSerializer;
~~~

This is the **typed JSON serializer on Jackson 3**. If code still imports `Jackson2JsonRedisSerializer` on 4.x, the old API is marked deprecated for removal and should be replaced alongside a data migration plan.

Using the same `ProductSnapshot` model from section 5, the configuration bean is:

~~~java
package com.example.redis;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.JacksonJsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration(proxyBeanMethods = false)
public class ProductRedisConfig {

    @Bean("productRedisTemplate")
    public RedisTemplate<String, ProductSnapshot> productRedisTemplate(
            RedisConnectionFactory connectionFactory) {

        RedisTemplate<String, ProductSnapshot> template = new RedisTemplate<>();
        template.setConnectionFactory(connectionFactory);

        StringRedisSerializer keySerializer = new StringRedisSerializer();
        JacksonJsonRedisSerializer<ProductSnapshot> valueSerializer =
                new JacksonJsonRedisSerializer<>(ProductSnapshot.class);

        template.setKeySerializer(keySerializer);
        template.setValueSerializer(valueSerializer);
        template.setHashKeySerializer(keySerializer);
        template.setHashValueSerializer(valueSerializer);

        return template;
    }
}
~~~

**Do not declare both `ProductRedisConfig` classes from sections 6 and 7 in the same project.** Pick the one matching your Spring Data Redis line. Architecturally, both examples create a `RedisTemplate` with String keys and typed JSON values; the difference lies in the serializer API and underlying JSON library.

When customizing the Jackson 3 mapper, import from `tools.jackson.databind.*` (such as `tools.jackson.databind.ObjectMapper`) and use the constructor/builder supported by that version's JavaDoc. In Spring Boot 4, the default JSON mapper is typically auto-configured as `tools.jackson.databind.json.JsonMapper`. Never pass Jackson 2's `com.fasterxml.jackson.databind.ObjectMapper` into a Jackson 3 serializer by mistake.

### 7.1. Why Can't You Just Rename Classes to Finish Migration?

Differences between Jackson 2 and Jackson 3 go beyond class names:

- Packages and some mapper/reader/writer APIs differ.
- Default configurations and module registration methods may change.
- Serialized JSON can differ in typing details, null handling, date/time formats, or type metadata.
- Some legacy DTO annotations/configs need re-verification.
- Existing Redis data from the old version will be read by the new version; it does not reformat itself after upgrading dependencies.

**To upgrade safely, verify the actual wire format** and design how legacy keys will be handled before running multiple application versions concurrently.

## 8. Using a Typed RedisTemplate in a Service

A service does not need to care whether the application uses Jackson 2 or Jackson 3 as long as the `productRedisTemplate` bean has the same type:

~~~java
package com.example.redis;

import java.time.Duration;
import java.util.Optional;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductSnapshotService {

    private final RedisTemplate<String, ProductSnapshot> redis;

    public ProductSnapshotService(
            @Qualifier("productRedisTemplate")
            RedisTemplate<String, ProductSnapshot> redis) {
        this.redis = redis;
    }

    public void put(ProductSnapshot product) {
        if (product == null || product.id() == null
                || product.id().isBlank()) {
            throw new IllegalArgumentException("Product ID is required");
        }

        redis.opsForValue().set(
                key(product.id()),
                product,
                Duration.ofMinutes(10)
        );
    }

    public Optional<ProductSnapshot> get(String id) {
        return Optional.ofNullable(redis.opsForValue().get(key(id)));
    }

    public boolean remove(String id) {
        return Boolean.TRUE.equals(redis.delete(key(id)));
    }

    private String key(String id) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("Product ID is required");
        }
        return "shop:v1:product:" + id;
    }
}
~~~

**At runtime:** `put(...)` writes a Redis String containing JSON with a 10-minute TTL; `get(...)` uses the same value serializer to restore `ProductSnapshot`; `remove(...)` deletes the key. A cache miss returns `Optional.empty()`, which should not be treated as a JSON error.

Example call inside a method injecting `ProductSnapshotService`:

~~~java
var product = new ProductSnapshot(
        "42", "Keyboard", new java.math.BigDecimal("590000")
);
productSnapshotService.put(product);
System.out.println(productSnapshotService.get("42"));
~~~

Do not place demo data-writing snippets into production startup code. Redis data can outlive the process lifecycle, so production code needs key namespace conventions and legacy schema handling.

## 9. Typed JSON vs. Generic JSON Differ in Type Metadata

### 9.1. Typed Serializer Already Knows the Target Type

~~~java
new Jackson2JsonRedisSerializer<>(ProductSnapshot.class); // Redis 3.x
new JacksonJsonRedisSerializer<>(ProductSnapshot.class);  // Redis 4.x
~~~

These two lines belong to **two different version branches** and must not be used together in the same project. Both know `ProductSnapshot.class` up front. JSON values typically look like:

~~~json
{"id":"42","name":"Keyboard","price":590000}
~~~

The deserializer has enough information to instantiate `ProductSnapshot`. When all data in a namespace shares one type, this is a simple and clean data contract.

### 9.2. Generic Serializer and the `@class` Field

The generic serializer in Jackson 2 often uses dynamic/default typing to embed class information. An illustrative JSON value might look like:

~~~json
{
  "@class": "com.example.redis.ProductSnapshot",
  "id": "42",
  "name": "Keyboard",
  "price": 590000
}
~~~

The exact shape can vary depending on mapper, object type, typing configuration, and version; do not assume `@class` is always present in every value. Type metadata tells the deserializer the actual class when reading under `Object`, yet couples Redis data to Java package and class names.

If you rename the package from `com.example.redis.ProductSnapshot` to `com.example.catalog.ProductSnapshot`, old data containing the previous class name may fail to deserialize. This is one reason to prefer typed DTOs, namespace versioning, and planned migrations.

### 9.3. Major Change Starting in Spring Data Redis 4.0

On the 3.x branch:

~~~java
import org.springframework.data.redis.serializer.GenericJackson2JsonRedisSerializer;

GenericJackson2JsonRedisSerializer serializer =
        new GenericJackson2JsonRedisSerializer();
~~~

Developers commonly use this class for `RedisTemplate<String, Object>` or Redis Cache configurations holding multiple object types. The no-arg constructor of the Jackson 2 serializer enables dynamic typing by default, yet **should not be used unchecked with untrusted data**.

On the 4.x branch:

~~~java
import org.springframework.data.redis.serializer.GenericJacksonJsonRedisSerializer;

GenericJacksonJsonRedisSerializer serializer =
        GenericJacksonJsonRedisSerializer.builder().build();
~~~

**Do not assume these two snippets behave identically.** According to Spring Data Redis upgrade documentation, the Jackson 3 generic serializer **does not enable default typing by default**. Therefore, when reading strictly as `Object`, the result may be generic structures instead of the expected Java DTO.

If restoring multiple runtime types is truly necessary, explicitly decide how types are identified and **restrict which classes are allowed to be deserialized**.

### 9.4. Enabling Default Typing in 4.x Must Include Type Constraints

Spring Data Redis 4.x provides:

~~~java
GenericJacksonJsonRedisSerializer.builder()
        .enableDefaultTyping(typeValidator)
        .build();
~~~

The `typeValidator` parameter is a `tools.jackson.databind.jsontype.PolymorphicTypeValidator` built by the application with rules allowing only truly needed types. You can use `BasicPolymorphicTypeValidator` and allowlist trusted domain packages/classes:

~~~java
import org.springframework.data.redis.serializer.GenericJacksonJsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializer;
import tools.jackson.databind.jsontype.BasicPolymorphicTypeValidator;
import tools.jackson.databind.jsontype.PolymorphicTypeValidator;

PolymorphicTypeValidator validator =
        BasicPolymorphicTypeValidator.builder()
                .allowIfSubType("com.example.redis.dto.")
                .build();

RedisSerializer<Object> serializer =
        GenericJacksonJsonRedisSerializer.builder()
                .enableDefaultTyping(validator)
                .build();
~~~

This snippet illustrates **allowlisting DTOs within an application-controlled package**, not a complete configuration for arbitrary object graphs. If DTOs contain collections, wrappers, or required subtypes, the validator must be designed and tested to handle those types properly. Never configure a validator that permits all classes indiscriminately just to silence deserialization errors.

**Security risk:** Polymorphic/default typing on untrusted JSON sources can cause dangerous deserialization if arbitrary classes are permitted. Redis is not automatically a safe source: an attacker might write data to Redis via another vulnerability, an integrated service, or misconfigured shared keys. Restrict Redis write permissions, prevent clients from supplying arbitrary type metadata, and prefer typed DTOs whenever possible.

## 10. Choosing the Right Serializer for Spring Cache Redis

Spring Cache uses annotations such as `@Cacheable`, `@CachePut`, and `@CacheEvict`. When backed by Redis, Spring uses `RedisCacheManager`/`RedisCacheConfiguration` to configure key/value serializers for **cache entries**.

**Common pitfall:** you configure a `RedisTemplate<String, ProductSnapshot>` with JSON, yet `@Cacheable` continues using a different serializer. Changing serializers on a `RedisTemplate` **does not automatically change `RedisCacheManager` settings**.

By Spring Data Redis defaults, Redis Cache typically has:

| Component | Important Default |
| --- | --- |
| Key serializer | `StringRedisSerializer` |
| Value serializer | `JdkSerializationRedisSerializer` |
| Cache key prefix | Based on cache name, typically `cacheName::key` |
| TTL | No default expiration unless configured |
| Caching nulls | May be enabled under default configuration |

To cache JSON values, configure `RedisCacheConfiguration` explicitly. The example below applies to **an application caching only `ProductSnapshot` via this CacheManager**:

### 10.1. Redis Cache JSON for Spring Data Redis 3.x

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializationContext;

@Configuration(proxyBeanMethods = false)
public class ProductCacheConfig {

    @Bean
    RedisCacheManager cacheManager(RedisConnectionFactory factory) {
        var valueSerializer =
                new Jackson2JsonRedisSerializer<>(ProductSnapshot.class);

        RedisCacheConfiguration config =
                RedisCacheConfiguration.defaultCacheConfig()
                        .entryTtl(Duration.ofMinutes(10))
                        .disableCachingNullValues()
                        .serializeValuesWith(
                                RedisSerializationContext.SerializationPair
                                        .fromSerializer(valueSerializer)
                        );

        return RedisCacheManager.builder(factory)
                .cacheDefaults(config)
                .build();
    }
}
~~~

### 10.2. Redis Cache JSON for Spring Data Redis 4.x

Replace only the serializer instantiation with the Jackson 3 API:

~~~java
import org.springframework.data.redis.serializer.JacksonJsonRedisSerializer;

var valueSerializer =
        new JacksonJsonRedisSerializer<>(ProductSnapshot.class);
~~~

The `RedisCacheConfiguration` lines with `serializeValuesWith(...)` follow the same structure. **The two snippets belong to two different versions**; do not put both serializers into the same class.

### 10.3. Why Is the Example Above Only for One Value Type?

Setting `cacheDefaults(config)` applies that typed JSON serializer to any cache without its own custom config. If the application adds caches returning `CustomerSummary` or `List<OrderDto>`, they will not fit `ProductSnapshot.class`.

Real-world applications usually pick one of these options:

1. Give each cache name its own `RedisCacheConfiguration` with a serializer matching its return type, registered via `withInitialCacheConfigurations(...)`.
2. Use a generic serializer **with strict type and security controls** when heterogeneous value types genuinely cannot be separated.
3. Design a cache DTO/envelope with a stable schema that all cached values conform to.

For instance, when using `@Cacheable(cacheNames = "productSnapshot", key = "#id")`, the cached method should return the exact type handled by `productSnapshot`'s serializer. Do not cache a method returning `String` into a region hardcoded for `ProductSnapshot`.

### 10.4. Nulls and Cache Misses

Distinguish clearly between:

- **Key does not exist:** Redis `GET` returns nil, which Spring Cache treats as a cache miss.
- **Method actually returns `null`:** May be cached using a special marker if caching null values is enabled; the serializer must support this case.
- **JSON literal `null`:** Not necessarily identical to how Spring Cache represents `NullValue`.
- **Key exists yet value fails to deserialize:** That is a data/schema error, not a valid cache miss.

In the typed examples above, `disableCachingNullValues()` avoids null-marker complexity for practice purposes. If business logic needs negative caching (caching "not found" results), choose a serializer and an explicit representation for absent results.

With generic Jackson 3, the builder supports Spring Cache null markers when configured properly; align it with your typing setup. Do not copy Jackson 2 null-caching settings without verifying them on Spring Data Redis 4.x.

## 11. Type Erasure and Generic Collections: Why Do Reads Produce List<Map>?

Suppose you want to store:

~~~java
List<ProductSnapshot> products = List.of(
        new ProductSnapshot("42", "Keyboard", new BigDecimal("590000")),
        new ProductSnapshot("43", "Mouse", new BigDecimal("240000"))
);
~~~

In Java, `List<ProductSnapshot>.class` does not exist because generic types are erased at runtime. If you only supply `List.class` when deserializing JSON, elements can turn into `LinkedHashMap` instead of `ProductSnapshot`.

With **Jackson 2 / Spring Data Redis 3.x**, you can use an explicit `JavaType`:

~~~java
import com.fasterxml.jackson.databind.JavaType;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;

ObjectMapper mapper = new ObjectMapper();
JavaType listType = mapper.getTypeFactory()
        .constructCollectionType(List.class, ProductSnapshot.class);

Jackson2JsonRedisSerializer<List<ProductSnapshot>> serializer =
        new Jackson2JsonRedisSerializer<>(mapper, listType);
~~~

This snippet is for the Jackson 2 branch. With Spring Data Redis 4.x, use `JacksonJsonRedisSerializer` and Jackson 3's `JavaType`/mapper per that version's JavaDoc; **never mix `com.fasterxml.jackson.databind.JavaType` into a constructor expecting `tools.jackson.databind.JavaType`**.

If multiple modules need a collection type, consider creating an explicit wrapper DTO:

~~~java
public record ProductBatch(
        String batchId,
        List<ProductSnapshot> products
) {}
~~~

Then the template can store a concrete `ProductBatch`. A wrapper can also carry versioning, creation timestamp, and domain context while avoiding type erasure issues at the Redis boundary.

## 12. Redis Hash: Serializers Differ from Hash Mappers

A Redis Hash key might look like:

~~~redis
HSET shop:product:42 name "Keyboard" price "590000"
HGETALL shop:product:42
~~~

In this case:

- Top-level key `shop:product:42` is a String.
- Hash fields `name`, `price` are Strings.
- Hash values `Keyboard`, `590000` can also be Strings.

A simple configuration:

~~~java
template.setKeySerializer(new StringRedisSerializer());
template.setHashKeySerializer(new StringRedisSerializer());
template.setHashValueSerializer(new StringRedisSerializer());
~~~

If the template has generic type `RedisTemplate<String, ProductSnapshot>`, understand that this setup is for Hash fields holding string values; using a dedicated Hash template or `StringRedisTemplate` reduces Java type ambiguity in operations.

A **Hash mapper** such as `Jackson2HashMapper` (3.x) or `JacksonHashMapper` (4.x) is a different mechanism: it turns an object into a set of fields/values and maps them to a Redis Hash. It is **not equivalent** to placing a JSON String inside each hash field.

For example, an object:

~~~json
{"id":"42","name":"Keyboard","price":590000}
~~~

can be represented as:

~~~text
Redis String key:
  shop:product:42 -> '{"id":"42","name":"Keyboard","price":590000}'

Redis Hash key:
  shop:product:42 -> { id: '42', name: 'Keyboard', price: '590000' }
~~~

These two cases use different Redis data structures: in the CLI, `TYPE key` returns `string` vs. `hash`. Reading a Hash with `GET` causes a `WRONGTYPE` error; reading a JSON String with `HGETALL` does the same.

Spring Data Redis 4.x replaces `Jackson2HashMapper` with `JacksonHashMapper`. When migrating Redis Hashes, check **flattened** vs. **hierarchical** format, field names, and how old values are read. The migration guide documents compatibility mode options for legacy Jackson 2 Hash mapper data.

## 13. RedisTemplate Defaults Differ from What You Might Expect

Many bugs come from declaring:

~~~java
RedisTemplate<String, ProductSnapshot> template = new RedisTemplate<>();
template.setConnectionFactory(connectionFactory);
return template;
~~~

and assuming `<String, ProductSnapshot>` automatically provides String/JSON serializers. **It does not.** Java generic types do not change `RedisTemplate`'s default serializers; an unconfigured template can use Java native serialization.

Consequences:

- Keys are encoded in binary format, so CLI does not display them as the expected strings.
- Values are Java serialization bytes, not JSON.
- Another template using a String serializer reads what looks like the same key in code, yet sends different bytes.
- After renaming Java classes/packages, old binary data becomes harder to keep compatible.

To use JSON, explicitly set at least the key and value serializers. If the application performs Hash operations, explicitly set hash-key/hash-value serializers as well.

`StringRedisTemplate` is a solid choice for inherently String data, such as counters, short-lived tokens, and simple statuses. Do not push arbitrary Java objects through `StringRedisTemplate` and forget manual JSON conversion on read.

## 14. Choosing Serializers by Real-World Scenario

### Scenario A: Product Detail Cache

**Requirement:** a cache named `productSnapshot` storing a `ProductSnapshot` DTO with a 10-minute TTL.

**Choice:** typed JSON matching your Spring Data Redis version, String keys, and a dedicated cache namespace. No Java-class-name type metadata is needed when the value type is fixed.

### Scenario B: Storing Counters

**Requirement:** increment product view counts with `INCR` and read counts via CLI.

**Choice:** `StringRedisTemplate` with String serializer. Redis `INCR` understands integer string values without needing a JSON DTO. Also avoid storing JSON like `{"count":5}` and reading/rewriting the whole object on every increment.

### Scenario C: One CacheManager Holding Multiple Result Types

**Requirement:** caching multiple methods returning heterogeneous DTO types.

**Choice:** prefer configuring serializers per cache name; if generic serialization is genuinely required, use the version-appropriate serializer with strict type metadata controls. On 4.x, remember the generic serializer does not enable default typing by default.

### Scenario D: Java and Node.js Applications Sharing Data

**Requirement:** both reading/writing product keys.

**Choice:** JSON with a stable schema, String keys, clearly specified timestamps, decimals, enums, field naming, and versioning. Avoid metadata tied to Java class names, especially since Node.js has no knowledge of those classes.

### Scenario E: Redis Hash Updated Field by Field

**Requirement:** updating status or price without rewriting a large JSON blob.

**Choice:** Redis Hash with appropriate field serializers, or a properly configured hash mapper. Do not assume a JSON serializer on `opsForValue()` automatically supports field-level `HSET`.

### Scenario F: Legacy Project Storing JDK Binary

**Requirement:** migrating data to JSON without breaking live caches.

**Choice:** check whether caches are regenerable, inventory legacy keys, use versioned namespaces or a controlled rollout/migration. Swapping serializers while reusing old keys causes read failures on existing data.

## 15. Jackson 2 → Jackson 3 Migration: Data Does Not Upgrade Itself

When upgrading Spring Data Redis 3.x to 4.x, the goal is not just **code compiling**. Redis may hold millions of keys written by a Jackson 2 serializer yesterday, while new processes start reading with Jackson 3.

### 15.1. Common Risks

1. **JSON format shifts:** property naming, null handling, dates, or type metadata differ between mapper versions.
2. **Different generic type metadata:** runtime types previously recorded in a way the new serializer cannot read or interpret identically.
3. **Java class renames:** `@class` metadata points to a class whose package changed.
4. **Rolling deployments:** old and new instances read/write the same key concurrently, racing between two formats.
5. **Cached null markers:** marker encoding changes, causing errors when reading cached nulls.
6. **Hash format:** 3.x and 4.x Hash mappers may map fields differently.
7. **Long-lived data:** infinite TTL keeps old keys around indefinitely across code deployments.

### 15.2. Simplest Strategy for Regenerable Caches

If Redis only stores **caches** and a database is the primary source:

~~~text
Old version:
  shop:v1:product:42  -> Jackson 2 bytes

New version:
  shop:v2:product:42  -> Jackson 3 bytes
~~~

Change the prefix/key namespace so the new version never misreads old data. During a rolling deployment, the old version continues using `v1` and the new version uses `v2`. Once old instances stop, let old keys expire by TTL or clean them up via a controlled process.

Pros: far simpler than reading/writing multiple formats on the same key. Con: the new cache starts cold, so evaluate potential database load spikes.

**Never run `FLUSHALL`/`FLUSHDB` in production** just because you changed a serializer. Those commands wipe data beyond your feature scope and can impact other services.

### 15.3. When Data Cannot Be Deleted and Rebuilt

If Redis holds state that must be preserved, a real migration process is needed:

1. Inventory namespaces, Redis types (String/Hash/Stream), TTLs, and existing formats.
2. Define a target JSON schema as independent of Java classes as possible.
3. Prepare a reader for old data using a compatible Jackson 2 serializer, and a reader/writer for the new format using Jackson 3.
4. Build a batched migration job to convert old data to the new namespace/format with error handling.
5. Maintain rollback capability and prevent old instances from writing legacy data into the new namespace.
6. Test with sanitized real-world sample data covering nulls, collections, enums, dates, and prior versions.
7. Switch traffic to the new reader only after rules for remaining legacy data are decided.

In the 4.x branch, legacy Jackson 2 APIs remain available as deprecated for removal to support migration, yet they should not be treated as a long-term choice. Spring Data Redis documentation recommends using `GenericJackson2JsonRedisSerializer` to read legacy generic Jackson 2 data during the transition.

### 15.4. Why Not "Try Jackson 3, Catch, and Fall Back to Jackson 2" on Every GET?

Fallback can be helpful during transition, yet consider:

- A JSON value may parse without throwing while having the wrong **semantic type**, so no exception does not mean correctness.
- Double reads slow down cache misses and legacy reads, increasing load.
- Rewriting the same key while two app versions run concurrently allows one instance to corrupt the other's format.
- You must time-box the transition, track legacy key counts, and plan fallback removal.

Explicit key versioning or a separate migration pipeline is usually easier to control.

### 15.5. `RedisSerializer.json()` Is Also a Checkpoint

Code written before Spring Data Redis 4:

~~~java
RedisSerializer<Object> valueSerializer = RedisSerializer.json();
~~~

may still compile after upgrading, yet **the factory's behavior changed from generic Jackson 2 to generic Jackson 3**. Do not infer old data remains compatible just because the build compiles. When using factory shortcuts, check the exact version's docs for typing behavior and stored format.

## 16. Managing JSON Schemas Across Multiple Upgrades

A clear JSON contract makes future migrations easier:

~~~json
{
  "schemaVersion": 2,
  "productId": "42",
  "name": "Keyboard",
  "priceAmount": "590000",
  "currency": "VND",
  "updatedAt": "2026-11-12T08:15:00Z"
}
~~~

This is an **illustrative schema**, not a format mandated by Spring Data Redis. Here, money is represented as a decimal string to reduce precision ambiguity across languages; timestamps follow ISO-8601 UTC; `schemaVersion` lets readers distinguish versions.

Rules to keep consistent:

| Rule | Clear Example | What Happens Without a Rule |
| --- | --- | --- |
| Field names | `productId` instead of oscillating between `id`/`product_id` | Old readers may miss fields |
| New fields | Have defaults or are marked optional | Old objects lacking the field fail reads or miss data |
| Removed fields | Use a deprecation/migration phase | Old readers still require missing fields |
| Enums | Standardize stored names/strings | Renaming enum constants breaks old readers |
| Timestamps | Explicit UTC/offset/epoch and unit | Wrong timezone, seconds-vs-milliseconds confusion |
| Money | Decimal string or amount/currency structure | Lost precision and currency mix-ups |
| Type metadata | Present or absent, property name, allowlist rules | Generic readers reconstruct wrong types |
| Versioning | Version field or key prefix version | Unclear how to read legacy schemas |
| TTL | Define how long data lives | Old keys linger forever or vanish unexpectedly |

**Human-readable JSON does not eliminate the need for schema design.** A 5-minute cache may only need key versioning and TTL; state living for months requires serious compatibility and recovery planning.

## 17. Security When Deserializing JSON from Redis

Many developers assume an internal Redis instance always contains trusted data. In reality, Redis can be written to by multiple services, batch jobs, operational tools, or via vulnerabilities in another API.

### 17.1. Risks of Enabling Default Typing Carelessly

Generic typing can use Java class names inside JSON to decide which class to instantiate. If a deserializer accepts metadata from an untrusted source and permits arbitrary classes, it can create an insecure deserialization vector depending on classpath gadgets and runtime environment.

Ways to reduce risk:

- Prefer **typed** serializers with a fixed target type.
- If polymorphic typing is required, apply `PolymorphicTypeValidator` with a tight allowlist.
- Never call `enableUnsafeDefaultTyping()` as a quick fix for type errors.
- Never accept arbitrary class names from HTTP requests or Redis payloads for class loading.
- Restrict Redis ACLs: allow each service only the keys and commands it needs wherever possible.
- Isolate Redis data across environments and security boundaries; avoid cross-tenant shared keys.
- Monitor security advisories for Spring Data Redis, Jackson, and related dependencies.

### 17.2. Sensitive Data and Logging

JSON can be read directly from the CLI or monitoring tools. Therefore:

- Do not store plaintext passwords, secrets, unprotected access tokens, or unnecessary personal data in caches.
- Do not log entire JSON values in production just to debug serializers.
- Do not embed tokens or sensitive identifiers in keys that may surface in metrics or admin tools.
- Set appropriate TTLs and evict caches when data is no longer permitted to be stored.
- Enable TLS and authentication for Redis where required.

Serializers do not encrypt data for security; JSON and encryption solve two separate problems.

## 18. Nulls, Missing Data, and Object Versioning

Three situations can look similar from the business layer:

1. The Redis key was never created or its TTL expired.
2. The Redis key exists but holds a representation for null/absent data.
3. The Redis key exists, JSON parses, yet required object fields are missing.

They require different handling:

| Situation | Expected Behavior | Notes |
| --- | --- | --- |
| Key does not exist | Cache miss or `Optional.empty()` | Can load from authoritative source |
| Key holds a valid null marker | Follow negative caching policy | Requires serializer/`CacheManager` marker support |
| JSON misses an optional field | Apply explicit default | Avoid surprising behavior changes |
| JSON misses a required field | Raise error or require migration | Never assume an incomplete object is usable |
| JSON type incompatibility | Record serialization/deserialization error | Can delete regenerable cache, never delete authoritative data |

With `Jackson2JsonRedisSerializer` and `JacksonJsonRedisSerializer`, null has API-specific representation rules; do not assume literal JSON `null`, an empty byte array, a missing key, and Spring Cache `NullValue` are equivalent. When designing null caching, rely on the semantics of your chosen `CacheManager` and serializer.

## 19. Common Errors and Their Causes

| Symptom | Possible Cause | Approach |
| --- | --- | --- |
| `ClassNotFoundException` for `JacksonJsonRedisSerializer` | Project still uses Spring Data Redis 3.x | Use `Jackson2JsonRedisSerializer` or upgrade the full dependency line via BOM |
| `ClassNotFoundException` for `GenericJacksonJsonRedisSerializer` | Spring Data Redis version lacks the new API | Inspect dependency tree versions |
| Wrong `ObjectMapper` in constructor | Mixing Jackson 2 with Jackson 3 | Check `com.fasterxml.jackson.databind` vs. `tools.jackson.databind` |
| `ClassCastException: LinkedHashMap -> ProductSnapshot` | Generic JSON lacks sufficient type info | Use a typed serializer or controlled type metadata strategy |
| Old JSON has `@class` yet new reader fails | Metadata/type mapping changed or class renamed | Provide migration/compatibility reader, change namespace |
| `SerializationException` or `MismatchedInputException` | Old data violates schema, wrong serializer, target type mismatch | Inspect value format, class/fields, migration |
| `GET` returns null yet key appears in GUI | Different key bytes/serializer, wrong DB, namespace, TTL | Check key serializer, database, prefix, and lifetime |
| `WRONGTYPE Operation against a key` | Calling `GET` on a Hash or `HGETALL` on a String | Check `TYPE key` and use matching commands |
| DTO with `Instant` fails deserialization | Mapper lacks required module/format | Select mapper/modules matching Jackson version; check date format |
| Object misses fields after upgrade | Incompatible schema version | Design defaults/migration; do not silently skip critical fields |
| `@Cacheable` still stores binary | CacheManager retains default JDK serializer | Configure `RedisCacheConfiguration.serializeValuesWith(...)` |
| Reading wrong fields from Redis Hash | Different hash key/value serializer or hash mapper | Inspect `HGETALL`, flattened vs. hierarchical mapping |
| Value deserialization fails during two-version deploy | Same namespace with two wire formats | Versioned keys, controlled rollout/migration |
| Type metadata poses security risk | Unrestricted default typing enabled | Use typed DTOs or `PolymorphicTypeValidator` allowlist |
| Redis CLI displays strange characters | Serializer stores binary format | Inspect bytes; do not assume Redis itself is corrupted |

### 19.1. Do Not Use `KEYS *` to Investigate Large Redis Instances

When inspecting keys:

~~~redis
TYPE shop:v1:product:42
GET shop:v1:product:42
TTL shop:v1:product:42
SCAN 0 MATCH shop:v1:product:* COUNT 100
~~~

`SCAN` returns a cursor and must loop until cursor `0` to cover the keyspace. Avoid `KEYS *` on large production keyspaces; avoid `FLUSHDB`/`FLUSHALL` to "fix caches" without knowing which data will be affected.

### 19.2. When to Delete Broken Cache Entries vs. Fix Data?

If a key is strictly a **regenerable cache**, the application can apply a policy to discard broken keys and reload from the authoritative source, accompanied by metrics to track frequency. Still, never catch every exception and return defaults as though primary data existed. If a key holds non-regenerable business state, deleting it loses data and requires proper migration/recovery.

## 20. Hands-On Lab: Comparing Typed JSON in 3.x and 4.x

### 20.1. Setup

Run Redis locally via Docker:

~~~bash
docker run --name redis-json-lab -p 127.0.0.1:6379:6379 -d redis:7
docker exec -it redis-json-lab redis-cli PING
~~~

Expect `PONG`. If port 6379 is occupied, change the host port mapping and `spring.data.redis.port`. Bind test Redis to loopback; never expose an unauthenticated port to the Internet.

### 20.2. 3.x Practice Branch

1. Create a Spring Boot 3.x project with Redis starter and matching JSON/Jackson 2 dependencies.
2. Use `Jackson2JsonRedisSerializer<ProductSnapshot>` in `productRedisTemplate`.
3. Save two `ProductSnapshot` records under prefix `shop:v1:product:*` with a TTL.
4. Inspect via CLI using `GET`, `TYPE`, and `TTL`.
5. Read back through the typed service; verify the exact class and `BigDecimal` values.
6. Try reading raw JSON at the same key with `StringRedisTemplate` (observe only, do not overwrite).

### 20.3. 4.x Practice Branch

1. Create a separate Spring Boot 4.x project with Spring Data Redis 4.x.
2. Use `JacksonJsonRedisSerializer<ProductSnapshot>`.
3. Store data under prefix `shop:v2:product:*`.
4. Inspect the JSON format and read back via the typed template.
5. If testing generic serialization, create a separate key and use `GenericJacksonJsonRedisSerializer`; observe the result without default typing enabled.
6. Only when polymorphic types are needed and a type validator is constrained, test appropriate metadata on self-created data.

Do not run both projects against the same namespace. Separating `v1` and `v2` prevents one project from writing data the other cannot read.

### 20.4. Testing Spring Cache

1. Create a method returning `ProductSnapshot` annotated with `@Cacheable(cacheNames = "productSnapshot", key = "#id")`.
2. Configure `RedisCacheManager` with the typed JSON serializer matching your version branch.
3. Call the method once and then a second time; verify the second call hits cache by tracking repository read counts.
4. Inspect the key under the cache prefix and its JSON value in Redis CLI.
5. Update the price in the primary source, evict cache with `@CacheEvict`, and call again.
6. Determine the TTL and explain why TTL does not replace invalidation after business updates.

### 20.5. Observation Table

| Case | Serializer | Redis TYPE | Value Seen in CLI | Deserialized Java Type | Expected Result |
| --- | --- | --- | --- | --- | --- |
| Typed snapshot 3.x | `Jackson2JsonRedisSerializer<ProductSnapshot>` | string | JSON object | `ProductSnapshot` | Accurate data |
| Typed snapshot 4.x | `JacksonJsonRedisSerializer<ProductSnapshot>` | string | JSON object | `ProductSnapshot` | Accurate data |
| Text/counter | `StringRedisSerializer` | string | Text/number | `String` | Accurate value |
| Generic without type info | Generic JSON | string | JSON | May be Map/List/scalar | Observe limitation |
| Default cache | `JdkSerializationRedisSerializer` | string | Binary bytes | Java object under matching conditions | Different from JSON |
| Hash fields | String Hash serializer | hash | `HGETALL` returns fields | String or specified schema | Do not use `GET` |

This table shows **expected results for the described setups**, not benchmark or executed test output. Actual behavior also depends on your mapper and versions.

## 21. Self-Assessment Criteria

You should be able to explain the following questions:

1. Why does `RedisTemplate<String, ProductSnapshot>` not automatically store JSON solely from its generic type?
2. How does a key serializer differ from a value serializer? Why should String be used for keys in most use cases?
3. How do typed JSON and generic JSON differ in determining the object type when reading?
4. When do you use `Jackson2JsonRedisSerializer` vs. `JacksonJsonRedisSerializer`?
5. How do `GenericJackson2JsonRedisSerializer` and `GenericJacksonJsonRedisSerializer` differ in default typing behavior?
6. Why must `RedisSerializer.json()` be reviewed when upgrading from Spring Data Redis 3.x to 4.x?
7. How should you choose a `PolymorphicTypeValidator` when JSON type metadata is required?
8. Why should a deserializer never accept arbitrary class names from untrusted data?
9. Why might cache annotations still use the JDK serializer even after the application defines a JSON `RedisTemplate`?
10. When do you need separate `RedisCacheConfiguration` instances per cache name?
11. If a DTO contains `List<ProductSnapshot>`, why can deserializing with `List.class` yield `Map` elements?
12. How do a Redis Hash with three fields and a Redis String containing one JSON object differ?
13. How does renaming a Java package affect values containing `@class`?
14. If you need to upgrade Jackson while Redis holds only TTL-bounded caches, what is the simplest migration strategy?
15. If Redis holds non-regenerable state, why can't you just delete old cache entries to resolve deserialization errors?
16. When encountering `WRONGTYPE`, `ClassCastException`, and `SerializationException`, which distinct root-cause categories does each indicate?
17. How should timestamps and currency values be standardized across applications reading shared JSON?
18. How do you check which classes are actually on your classpath before choosing serializer APIs?

## 22. Official References

- [Spring Data Redis — Migration Guides (3.x → 4.x)](https://docs.spring.io/spring-data/redis/reference/upgrading.html): lists replacement classes, `RedisSerializer.json()` changes, default typing, and legacy data migration guidance.
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html): configuring cache key/value serializers, key prefixes, TTLs, and defaults.
- [Spring Data Redis 3.5 — Jackson2JsonRedisSerializer JavaDoc](https://docs.spring.io/spring-data/redis/reference/3.5/api/java/org/springframework/data/redis/serializer/Jackson2JsonRedisSerializer.html): typed constructors, `ObjectMapper`, and serializer config on the Jackson 2 branch.
- [Spring Data Redis 4.0 — JacksonJsonRedisSerializer JavaDoc](https://docs.spring.io/spring-data/redis/reference/4.0/api/java/org/springframework/data/redis/serializer/JacksonJsonRedisSerializer.html): typed serializer on Jackson 3.
- [Spring Data Redis 4.0 — GenericJacksonJsonRedisSerializer builder JavaDoc](https://docs.spring.io/spring-data/redis/reference/4.0/api/java/org/springframework/data/redis/serializer/GenericJacksonJsonRedisSerializer.GenericJacksonJsonRedisSerializerBuilder.html): typing options, validators, and Spring Cache null support.
- [Spring Boot 4.0 — JSON](https://docs.spring.io/spring-boot/4.0/reference/features/json.html): Jackson 3 as default, Jackson 2 for migration, and mapper configuration changes.

**Remember:** Always **choose serializers matching your actual library versions and key data contracts**. For DTOs with clear schemas, typed JSON serializers for Spring Data Redis 3.x or 4.x are usually easiest to manage. With generic JSON, understand type metadata and deserialization constraints. When upgrading from Jackson 2 to Jackson 3, treat already-stored Redis data as a format with its own lifecycle: changing code or dependencies does not automatically make old data compatible.
