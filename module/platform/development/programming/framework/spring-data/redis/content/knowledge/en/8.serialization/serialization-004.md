# Java Binary Serialization and Risks When Reading Untrusted Data

In **Spring Data Redis**, Java objects are not sent over the network verbatim. Redis stores and returns byte sequences; the application side must decide how to convert **object → byte[]** when writing and **byte[] → object** when reading. Choosing a serializer affects data format, cross-service sharing, compatibility across version updates, performance, and especially **trust boundaries during deserialization**.

One built-in option is `JdkSerializationRedisSerializer`, which uses **Java native serialization** via `ObjectOutputStream` and `ObjectInputStream`. This mechanism is convenient for storing Java objects, yet deserializing an untrusted stream can trigger behavior in classes on the classpath rather than merely "reading a few fields." Consequently, it is unsuitable as an input format for data controlled by untrusted actors.

This article explains how that mechanism works, where it appears in Spring Data Redis, the risks to recognize, and how to transition toward safer, more controllable data structures.

> **Technical context:** Examples use Java 21, Spring Boot 3.3.x, and Spring Data Redis 3.3.x. The phrase "safer" in this article always comes with conditions regarding data origin, parser type, allowed classes, input validation, and deployment configuration. No single serializer guarantees all input data is safe on its own.

## 1. Redis Stores Bytes, While Java Operates on Objects

Suppose an application has an object:

~~~java
public record ProductCacheValue(
        String id,
        String name,
        long version
) {
}
~~~

We want to store it under key `catalog:product:42`. The general path:

~~~mermaid
flowchart LR
    A["ProductCacheValue in JVM"] --> B["RedisSerializer.serialize()"]
    B --> C["byte[]"]
    C --> D["Redis SET catalog:product:42"]
    D --> E["Redis holds binary-safe value"]
    E --> F["Redis GET"]
    F --> G["byte[] returned to JVM"]
    G --> H["RedisSerializer.deserialize()"]
    H --> I["ProductCacheValue or error"]
~~~

Redis does not know about `ProductCacheValue`, does not load Java classes, and does not run `readObject()` to store values. Java serialization/deserialization work happens on the **Java client** before sending or after receiving bytes. Redis supports binary keys/values, so a single Redis server can hold values written by Java, Python, Node.js, or command-line tools.

This creates an important requirement: **every client reading the same key must understand the same byte format**. If service A writes a Java serialized object while service B uses a JSON parser to read it, they cannot exchange data merely by pointing to the same Redis address.

### 1.1. Two Directions of a Serializer

Spring Data Redis uses the `RedisSerializer<T>` abstraction, conceptually having two operations:

~~~java
byte[] serialize(T value);
T deserialize(byte[] bytes);
~~~

When calling:

~~~java
redisTemplate.opsForValue().set("catalog:product:42", product);
~~~

the template uses its key serializer and value serializer to turn both key and value into bytes. For Redis types such as HASH, there are also hash-key and hash-value serializers.

When calling:

~~~java
ProductCacheValue product =
        redisTemplate.opsForValue().get("catalog:product:42");
~~~

the template retrieves bytes from Redis and passes them into the value serializer's `deserialize` direction. If bytes were written in the wrong format or tampered with, failure occurs at this step before business logic processes the object.

### 1.2. "Binary" Does Not Mean Security Encryption

Java binary serialization produces **a structured format intended for the JVM**. It does not automatically encrypt secrets, verify byte origin, or provide tamper-proof signatures.

If an application puts tokens, user details, or sensitive data into serialized objects, the fact that the payload is unreadable by eye in `redis-cli` **does not mean its contents are protected**. Redis access controls, TLS transport encryption, secret management, and retention policies must be handled independently.

## 2. How Does Java Native Serialization Work?

The Java Serialization API is built around `java.io.ObjectOutputStream` and `java.io.ObjectInputStream`.

A Java class can opt into the default serialization mechanism by implementing the `Serializable` marker interface:

~~~java
import java.io.Serial;
import java.io.Serializable;

public final class LegacyProduct implements Serializable {

    @Serial
    private static final long serialVersionUID = 1L;

    private final String id;
    private final String name;

    public LegacyProduct(String id, String name) {
        this.id = id;
        this.name = name;
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

When writing, `ObjectOutputStream` describes an object graph including types, fields, references, and metadata needed to reconstruct it according to Java's serialization protocol.

Example generating bytes locally:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.ObjectOutputStream;

LegacyProduct product = new LegacyProduct("42", "Keyboard");

ByteArrayOutputStream output = new ByteArrayOutputStream();

try (ObjectOutputStream stream =
             new ObjectOutputStream(output)) {
    stream.writeObject(product);
}

byte[] serialized = output.toByteArray();
System.out.println("Byte count = " + serialized.length);
~~~

This is an **outbound serialization** operation from an object created by the application. It does not read untrusted bytes.

In the Java Object Serialization format, a typical stream header begins with the hex bytes:

~~~text
AC ED 00 05 ...
~~~

Subsequent bytes may contain class descriptors, class names, `serialVersionUID`, field values, and graph metadata. When viewed with text tools, some fragments may be printable while many are unreadable. This header helps **identify the likelihood** of a Java serialized stream, yet **does not prove the stream is trustworthy or valid**.

### 2.1. Which Parts Get Stored?

| Component | Common Handling | Meaning |
|---|---|---|
| Normal instance fields | Can be written per the class's serialization mechanism | Restores object state |
| `static` fields | Not part of normal serialized instance state | Static values belong to the class in the current JVM |
| `transient` fields | Not written by the default serialization mechanism | Used when a field should not participate in default representation |
| `serialVersionUID` | Serialization version identifier of the class | Assists compatibility checks between class descriptor and stream |
| Object graph references | Represented to support graphs and shared references | Not just a flat structure like ordinary JSON |
| `readObject` / `readResolve` / `writeObject` | Class-specific hooks per Java's mechanism | Can alter write/restore behavior and execute logic |

If an object references other objects, objects within the graph are serialized according to their respective rules; not just top-level fields are written. Classes implementing `Externalizable` additionally have their own custom read/write mechanisms.

### 2.2. Why Is `readObject()` Different from Simple Data Parsing?

The call:

~~~java
Object value = objectInputStream.readObject();
~~~

does not merely construct a key/value map. It can:

1. Read class descriptors recorded in the stream.
2. Locate the corresponding classes on the classpath/class loader.
3. Reconstruct the object graph and apply deserialization logic of the involved classes.
4. Invoke Java serialization hooks during restoration if classes define them.
5. Return the final object or throw an error if the stream, types, or rules are invalid.

Under certain conditions, **side effects or code inside class hooks can run before the caller casts or inspects the returned object**. This is the foundation of insecure deserialization risk.

## 3. Where Does `JdkSerializationRedisSerializer` Appear in Spring Data Redis?

### 3.1. How This Serializer Connects to RedisTemplate

Spring Data Redis includes `org.springframework.data.redis.serializer.JdkSerializationRedisSerializer` to convert Java objects to Java serialized streams and back.

Example declaring a template using Java serialization **for illustration only**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.JdkSerializationRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration(proxyBeanMethods = false)
public class LegacyRedisSerializationConfig {

    @Bean("legacyRedisTemplate")
    RedisTemplate<String, Object> legacyRedisTemplate(
            RedisConnectionFactory factory
    ) {
        RedisTemplate<String, Object> template = new RedisTemplate<>();
        template.setConnectionFactory(factory);

        template.setKeySerializer(new StringRedisSerializer());
        template.setHashKeySerializer(new StringRedisSerializer());

        JdkSerializationRedisSerializer jdk =
                new JdkSerializationRedisSerializer();
        template.setValueSerializer(jdk);
        template.setHashValueSerializer(jdk);

        return template;
    }
}
~~~

In this setup, key `catalog:product:42` is encoded as UTF-8 text, while the value is a Java binary stream. Therefore `redis-cli GET catalog:product:42` may return data looking like strange characters. Redis still stores it under Redis type `string`; "Java object" is a client-side interpretation, not a new Redis data type.

**Do not copy this configuration for keys receiving data from untrusted sources.** It is shown to help recognize a system currently using Java serialization format.

### 3.2. Defaults That Are Easy to Overlook

When using Spring Data Redis, distinguish between:

| Tool | Typical Key Serializer | Typical Value Serializer |
|---|---|---|
| Uncustomized default `RedisTemplate` | Java serialization per template default config | `JdkSerializationRedisSerializer` |
| `StringRedisTemplate` | `StringRedisSerializer` | `StringRedisSerializer` |
| `RedisCacheConfiguration.defaultCacheConfig()` | `StringRedisSerializer` | `JdkSerializationRedisSerializer` |
| Explicitly configured `RedisTemplate` | Decided by application | Decided by application |

With `RedisTemplate`, a generic type `RedisTemplate<String, MyDto>` **does not automatically turn bytes into JSON**. Generics only help the Java compiler check part of the API's types; byte encoding is still decided by the actual serializers.

With Spring Cache, if `RedisCacheManager` uses the default configuration without replacing the serializer, Redis cache values may be using Java native serialization even when business services never call `RedisTemplate` directly.

~~~java
@Cacheable(cacheNames = "productById", key = "#id")
public ProductCacheValue find(String id) {
    // Example method reading from the authoritative data source.
    return repository.findById(id);
}
~~~

Just seeing `@Cacheable` is not enough to know what bytes sit in Redis. You must check which `CacheManager` is actually active, how `RedisCacheConfiguration` is configured, and which serializer applies to each cache.

### 3.3. Identifying Existing Java Serialized Data

When authorized to inspect a given environment/key, you can examine metadata without deserializing:

~~~bash
redis-cli TYPE catalog:product:42
redis-cli STRLEN catalog:product:42
redis-cli TTL catalog:product:42
~~~

`TYPE` returns `string` for values holding Java serialized streams because Redis knows nothing of Java classes; `STRLEN` returns the value size in bytes. `TTL` helps understand the key lifecycle.

When byte inspection is needed, use a tool suited for binary data in a test environment, and avoid logging entire serialized payloads verbatim or sending payloads to unnecessary services. Seeing header `AC ED 00 05` is an indicator of format, **not an invitation to read that object with `ObjectInputStream`**.

## 4. What Data Counts as Untrusted?

There is a common misconception: "Redis is in a private network, so all bytes in Redis are trustworthy." In reality, **the trust boundary lies in who controls writing the data**, not merely the server's network location.

Data sources to evaluate include:

- A REST/API endpoint accepting user-supplied values and writing them to Redis.
- Import jobs, message consumers, or third-party services pushing bytes into Redis.
- A Redis instance shared by multiple applications/teams without separated write permissions.
- Keys written by an older application version or another service using a different serializer.
- Caches restored from backups or copied from unverified environments.
- Compromised Redis accounts, networks, or administrative tools with write access.
- Cases where an application lets input select an arbitrary key and reads a key belonging to another source.

Not every case is an attack. A service using the wrong serializer can produce **incompatible data** without malicious intent. However, if an actor can control a serialized byte stream that your application reads with `JdkSerializationRedisSerializer`, that can be an entry point requiring treatment as **insecure deserialization**.

### 4.1. Path of the Risk

~~~mermaid
flowchart TD
    A["Source able to write bytes into Redis"] --> B["Key trusted by app as cache object"]
    B --> C["String/RedisTemplate or Redis Cache reads bytes"]
    C --> D["JdkSerializationRedisSerializer.deserialize()"]
    D --> E["ObjectInputStream restores object graph"]
    E --> F["Hooks and behaviors of classes on classpath"]
    F --> G["Side effects / errors / overload depending on content and classes"]
    G --> H["Business code only receives object or exception afterward"]
~~~

Crucial point: casting such as `(Product) value` or checking `instanceof Product` after deserialization is not an early enough safeguard. If an unsafe object graph has already been processed inside `readObject()`, a subsequent `ClassCastException` cannot undo side effects that already occurred.

### 4.2. Possible Consequences

| Risk | Conceptual Mechanism | Conditions to Note |
|---|---|---|
| **Unintended behavior execution** | Classes with hooks or method invocation chains during deserialization | Depends on classes/gadgets available on classpath and actor's control over bytes |
| **Remote Code Execution (RCE)** in severe cases | Dangerous gadget chains triggered when reconstructing the graph | Not every Java stream causes RCE; requires a viable exploitation path |
| **Denial of Service (DoS)** | Deep/large graphs, many elements/references, or payloads causing heavy CPU/RAM work | Can happen even without RCE gadgets |
| **Abnormal application behavior** | Missing classes, incompatible stream descriptors, wrong object type received | Can occur as operational incidents without malicious intent |
| **Business data corruption** | Reading the wrong key/serializer or interpreting objects from an old version | Causes cache misses, exceptions, or wrong results if handled loosely |

Java Serialization does not automatically "run whichever class the sender wants": classes must exist and be usable on the application side, and various environmental constraints also shape the outcome. However, **merely changing the classpath or adding a dependency with suitable gadgets can alter the attack surface** without changing a single line of Redis-reading code.

### 4.3. Why Are Gadget Chains Concerning?

In Java, many libraries contain methods handling lifecycles, comparators, collections, proxies, or custom serialization. Certain object types can trigger various methods during deserialization. If these behaviors chain together into an unintended effect, an attacker can exploit them.

To grasp this lesson, there is no need to craft payloads or enumerate specific gadget chains. The essential rule is: **never treat a byte stream controlled by an untrusted party as a valid Java object merely because it can be fed into `ObjectInputStream`**.

## 5. Compatibility Risks During Version Upgrades

Even if Redis only receives data from your own application, Java binary serialization tightly couples stored data to JVM class structures.

### 5.1. `serialVersionUID` Checks Versions, Not Schema Migration

For a `Serializable` class, `serialVersionUID` is used to match the serialized class descriptor version during deserialization. If the reading class has a `serialVersionUID` incompatible with the stream, `InvalidClassException` may occur.

Example:

~~~java
import java.io.Serial;
import java.io.Serializable;

public final class CachedAccount implements Serializable {

    @Serial
    private static final long serialVersionUID = 1L;

    private String id;
    private String tier;
}
~~~

In a later deployment, code changes the class structure, package name, or field semantics. Keeping `serialVersionUID = 1L` **does not automatically transform old data into the new business-valid schema**.

Specifically:

- Adding/removing fields follows certain Java Serialization compatibility rules, yet business code may reject post-deserialization default values.
- Renaming a package/class can cause the JVM to fail to find the old class.
- Changing a field type or an associated class becoming non-serializable can break reads/writes.
- A new version might introduce dependencies/hooks that change deserialization risk.
- When multiple services run different class versions, the same payload might deserialize in one service and fail in another.

**Do not rely on keeping `serialVersionUID` unchanged as your sole data migration strategy.**

### 5.2. Common Errors When Reading Old Caches

| Java/Spring Error Encountered | Typical Explanation | Investigation Action |
|---|---|---|
| `InvalidClassException` | Stream class and current class are incompatible per serialization rules | Compare versions, UIDs, class structural changes |
| `ClassNotFoundException` | Client lacks the class described in the stream | Check renamed packages/classes, dependencies/classloaders |
| `StreamCorruptedException` | Bytes do not match the expected stream format | Check writer's serializer, key collisions, corrupted data |
| `ClassCastException` | Deserialized object does not match the type caller expects | Check key schema/serializers and format changes |
| Spring `SerializationException` | Adapter layer wrapping underlying serialize/deserialize error | Read root cause; do not blindly retry the same payload forever |
| Memory errors / latency spikes | Oversized payload, complex graph, or resource-heavy deserialization | Check size limits, key ownership, data origin |

A fallback of "try JDK serialization if JSON fails" can accidentally **reopen the old attack surface**. For regenerable cache data, a cleaner recovery path is usually to delete or re-namespace old cache entries and rewrite them in the new format.

### 5.3. Unsuitable for Cross-Language Sharing

Java Serialization is a Java-specific format. A Go or Python service cannot naturally read objects produced by `JdkSerializationRedisSerializer` directly like an ordinary JSON object.

If Redis serves as an exchange layer between multiple services or languages, choose an agreed schema such as JSON DTOs with explicit fields, Protocol Buffers, or a binary format with schemas and appropriate parsers. Then **schema versioning** must be managed independently of Java class names and JVM versions.

## 6. Simplest Option: Store Only Strings When Sufficient

Not all data in Redis needs an entire object graph. For tokens, counters, flags, IDs, or small status values, `StringRedisTemplate` is usually enough and easy to control.

~~~java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class FeatureFlagStore {

    private final StringRedisTemplate redis;

    public FeatureFlagStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void save(String flagId, boolean enabled) {
        redis.opsForValue().set(
                "feature:v1:" + flagId,
                Boolean.toString(enabled),
                Duration.ofMinutes(10)
        );
    }

    public boolean isEnabled(String flagId) {
        String raw = redis.opsForValue().get(
                "feature:v1:" + flagId
        );
        return "true".equalsIgnoreCase(raw);
    }
}
~~~

Here, values are handled as strings without invoking Java Object Serialization. That eliminates the **specific JDK deserialization path**, though you still must control inputs (such as IDs, string lengths, formats, and key write permissions). This simple example treats missing or malformed values as false; for critical business logic, define explicit error behavior instead of defaulting to false.

For counters, use `opsForValue().increment(key)` on numeric values following an appropriate string convention. Do not serialize an entire object just to read a single integer.

## 7. Storing Objects as JSON with Fixed-Type DTOs

When objects must be stored, a more operable approach is to use **DTOs with explicit schemas** and a JSON serializer configured for a target type.

### 7.1. DTO for Caching

~~~java
public record ProductCacheValue(
        String id,
        String name,
        long version
) {
}
~~~

This DTO holds only the fields needed for caching. It does not contain session-attached JPA entities, proxy objects, connections, Java exceptions, or unrelated complex references.

Expected JSON example:

~~~json
{
  "id": "42",
  "name": "Keyboard",
  "version": 3
}
~~~

JSON improves observability, yet **JSON is not automatically safe**. What matters is that the parser only instantiates allowed types, enforces reasonable size/depth limits, and does not process untrusted type metadata in an open-ended manner.

### 7.2. Creating a Typed JSON Template

Example for Spring Boot 3.3.x / Spring Data Redis 3.3.x:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration(proxyBeanMethods = false)
public class ProductRedisConfig {

    @Bean("productRedisTemplate")
    RedisTemplate<String, ProductCacheValue> productRedisTemplate(
            RedisConnectionFactory connectionFactory,
            ObjectMapper objectMapper
    ) {
        RedisTemplate<String, ProductCacheValue> template =
                new RedisTemplate<>();

        template.setConnectionFactory(connectionFactory);

        StringRedisSerializer text = new StringRedisSerializer();
        Jackson2JsonRedisSerializer<ProductCacheValue> json =
                new Jackson2JsonRedisSerializer<>(
                        objectMapper,
                        ProductCacheValue.class
                );

        template.setKeySerializer(text);
        template.setHashKeySerializer(text);
        template.setValueSerializer(json);
        template.setHashValueSerializer(json);

        return template;
    }
}
~~~

The bean is named `productRedisTemplate` to indicate its purpose. It uses a JSON serializer bound to the **specific type `ProductCacheValue`**. Operations using this template must match that DTO type; do not share a typed template across unrelated object types.

Spring Boot usually provides an `ObjectMapper` when the application includes Jackson and appropriate Jackson configuration. The code relies on the application's configured `ObjectMapper`; if the system enables broad Jackson polymorphic default typing or uses dangerous custom deserializers, evaluate and fix that configuration. **Simply replacing `JdkSerializationRedisSerializer` with a JSON serializer that instantiates arbitrary classes is not necessarily safe.**

### 7.3. Service Using an Explicit Template

~~~java
import java.time.Duration;
import java.util.Optional;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductCacheStore {

    private final RedisTemplate<String, ProductCacheValue> redis;

    public ProductCacheStore(
            @Qualifier("productRedisTemplate")
            RedisTemplate<String, ProductCacheValue> redis
    ) {
        this.redis = redis;
    }

    public void put(ProductCacheValue product) {
        redis.opsForValue().set(
                "catalog:product:v2:" + product.id(),
                product,
                Duration.ofMinutes(20)
        );
    }

    public Optional<ProductCacheValue> find(String id) {
        ProductCacheValue value = redis.opsForValue().get(
                "catalog:product:v2:" + id
        );
        return Optional.ofNullable(value);
    }

    public void evict(String id) {
        redis.delete("catalog:product:v2:" + id);
    }
}
~~~

Using the `v2` prefix prevents new JSON code from trying to read Java serialization bytes at the old key `catalog:product:42`. Once old keys' TTL expires or the system performs controlled cleanup, old data disappears without routing old streams through the new deserialization path.

What still belongs at the application layer: validating `id`, DTO lengths and contents, access controls, TTL, and cache miss handling. If a payload fetched from Redis does not match the expected JSON/type, the serializer should fail rather than implicitly falling back to JDK deserialization.

### 7.4. Choosing Typed JSON Serializers Over Arbitrary Polymorphism

With Spring Data Redis, common choices include:

| Serializer | Idea | What to Watch Out For |
|---|---|---|
| `StringRedisSerializer` | String ↔ UTF-8 bytes | Only suitable for clearly text-shaped data |
| `Jackson2JsonRedisSerializer<T>` | JSON for a fixed Java type | Check `ObjectMapper`, custom deserializers, target type, and input bounds |
| `GenericJackson2JsonRedisSerializer` | JSON for multiple object types using type information | Carefully audit type metadata/default typing when reading untrusted data |
| `JdkSerializationRedisSerializer` | Java native binary object graph | Never deserialize untrusted data |
| `RedisSerializer.byteArray()` / raw bytes | Keeps bytes as raw data | Caller must define and validate schema when decoding |

Do not conclude that a serializer named "JSON" means **zero deserialization risk**. For example, Jackson has polymorphic type handling mechanisms; when payload metadata is allowed to dictate instantiated classes without tight restrictions, another risk surface appears. Whenever you control the schema, **concrete DTOs with allowed fields** are far easier to audit than open configurations accepting "any Object".

## 8. Spring Cache Must Be Reviewed Separately

An application might not use `RedisTemplate` directly yet still use Redis through Spring Cache:

~~~java
@Cacheable(cacheNames = "productById", key = "#id")
public ProductCacheValue findById(String id) {
    return loadProductFromDatabase(id);
}
~~~

When using `RedisCacheManager` with default `RedisCacheConfiguration`, the default value serializer uses Java serialization. Therefore, converting a manual service to a typed JSON template **does not automatically change `@Cacheable`'s serializer**.

Example configuring **a single cache holding only `ProductCacheValue`** with typed JSON:

~~~java
import java.time.Duration;
import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializationContext;

@Configuration(proxyBeanMethods = false)
public class RedisCacheSerializationConfig {

    @Bean
    RedisCacheManager redisCacheManager(
            RedisConnectionFactory connectionFactory,
            ObjectMapper objectMapper
    ) {
        Jackson2JsonRedisSerializer<ProductCacheValue> serializer =
                new Jackson2JsonRedisSerializer<>(
                        objectMapper,
                        ProductCacheValue.class
                );

        RedisCacheConfiguration productCache =
                RedisCacheConfiguration.defaultCacheConfig()
                        .entryTtl(Duration.ofMinutes(20))
                        .serializeValuesWith(
                                RedisSerializationContext
                                        .SerializationPair
                                        .fromSerializer(serializer)
                        );

        return RedisCacheManager.builder(connectionFactory)
                .withInitialCacheConfigurations(
                        Map.of("productById", productCache)
                )
                .disableCreateOnMissingCache()
                .build();
    }
}
~~~

In the example, cache `productById` is configured for a specific DTO. `disableCreateOnMissingCache()` prevents an undeclared cache name from being dynamically created with a **default value serializer** different from the configured cache.

This is a sample configuration for a single typed cache. If an application has multiple caches holding different DTO types, declare appropriate serializers per cache and control which caches may be created. Do not use `ProductCacheValue`'s serializer to deserialize `List<Product>`, `Customer`, or other objects without a matching schema.

When changing cache formats, also evaluate **key prefixes** and existing data in Redis. Switching from JDK binary to JSON while keeping the old keyspace can cause the new application's first reads to fail upon encountering mismatched bytes.

## 9. If You Must Keep JDK Serialization in a Legacy System

Sometimes a legacy system still relies on Java serialization and cannot migrate immediately. In that case, prioritize **not accepting bytes from untrusted sources**, narrowing which keys can be read, isolating write permissions, and planning to phase out the old format. Deserialization filters are only a supplementary defense layer.

### 9.1. Java ObjectInputFilter: Restricting Classes and Resources

Java supports serialization filtering via `java.io.ObjectInputFilter`, introduced in JEP 290 and extended with context-specific filter factories in JEP 415.

A filter can return allowed, rejected, or undecided for classes/arrays and enforce object graph limits, such as:

- Graph depth (`maxdepth`).
- Number of references (`maxrefs`).
- Stream size in bytes (`maxbytes`).
- Array size (`maxarray`).
- Allowed or disallowed classes/packages/modules by pattern.

An **illustrative pattern** for a JVM process needing to read legacy data:

~~~text
-Djdk.serialFilter=maxdepth=20;maxrefs=1000;maxbytes=1048576;maxarray=10000;com.example.cache.dto.*;java.base/java.lang.*;java.base/java.util.*;!*
~~~

This is **not a configuration to apply verbatim to every application**:

- `com.example.cache.dto.*` is only an example package name; determine the exact classes actually allowed.
- Base Java packages can be broader than needed and still contain many classes; narrow them wherever feasible.
- Pattern syntax, pattern ordering, array/class graph rules, and limits must match the exact JDK in use.
- A JVM-wide filter can affect other Java deserialization mechanisms in the same process, not just Redis.
- Filters must be configured **before** data is deserialized; inspecting objects after instantiation cannot substitute for input filtering.
- A filter reduces risk but does not guarantee safety against all behavior of permitted classes.

If passing `-D...` in a shell command, `;` characters must be properly quoted/escaped for the shell in use; those semicolons are part of the **property value**, not separate shell commands.

`ObjectInputFilter` helps govern which object types get reconstructed and certain resource limits. It **does not replace authenticating data sources, eliminating dangerous gadgets, or moving to an explicit-schema format**. Filtering behavior also depends on the JDK, filter factory, and how `ObjectInputStream` is constructed, so verify actual behavior in practice.

### 9.2. Do Not Rely on Post-Deserialization Casting

The following reasoning pattern is not safe enough:

~~~java
Object deserialized = /* ObjectInputStream.readObject() */;
if (!(deserialized instanceof LegacyProduct)) {
    throw new IllegalArgumentException("Wrong type");
}
~~~

The `instanceof` check happens **after** reading the object graph. If bytes can be controlled by an untrusted actor, checking the type at this point does not block side effects that already ran during deserialization.

Defenses must sit **before or inside** the read process: block untrusted write sources, do not use Java deserialization for their data, and apply filters/limits while legacy formats still exist.

### 9.3. Restricting Redis ACLs and Write Paths

Cache data can still become a dangerous input source if another service has permission to write to the same keyspace.

Define clearly:

1. Which services have permission to **write** and **read** key groups using Java serialization.
2. Which Redis accounts/ACLs and key patterns are permitted access.
3. Whether Redis sits on a private network, uses TLS, and manages credentials properly.
4. Whether any services/workers/debug tools can directly modify bytes at those keys.
5. When a deserialization error occurs, what rule governs deleting the key, raising an error, or falling back without infinite re-deserialization loops.

Redis ACLs can restrict commands/keys an account accesses, yet they do not verify that written bytes represent a valid serialized DTO, nor do they turn Redis into an unconditionally trusted data source.

### 9.4. Resource Limits When Reading Cache

Beyond class filters, also consider:

- Maximum accepted value size and number of keys read per request.
- Redis command timeouts and request latency budgets.
- Risk of concurrent requests reading large payloads spiking JVM heap/GC.
- Handling corrupted keys without triggering continuous retry loops.
- Monitoring serializer/deserializer error counts, payload sizes, cache miss rates, and anomalies.

TTLs do not neutralize a dangerous payload while the key remains alive; eviction is not a security control either.

## 10. Migrating from Java Serialization to a New Format

A serializer change is not like changing how data is displayed. It is a **change to the data protocol stored in Redis**. If the old app writes JDK bytes and the new version tries parsing JSON at the same key, reads can fail immediately.

A migration approach for regenerable cache data:

~~~text
Before:
  catalog:product:42  → Java serialization bytes (legacy)

After:
  catalog:product:v2:42 → typed JSON DTO (new)
~~~

Transition flow:

1. Choose the new schema and version the keyspace, e.g., `catalog:product:v2:<id>`.
2. The new application version reads/writes only `v2` keys using the new serializer.
3. On a cache miss at `v2`, read from the **authoritative data source** (trusted database/API) and populate the new cache.
4. Let old keys expire naturally by TTL, or clean them up through an authorized, controlled process.
5. Once all consumers have migrated, remove legacy code and dependencies using JDK serialization if no longer needed.

This avoids having to deserialize legacy data just to convert formats. It also isolates the two formats so old and new bytes never mix under the same key name.

For data where Redis is the **sole store** and cannot be regenerated from an authoritative source, a different controlled migration is needed: verify payload provenance, isolate the legacy reader environment, restrict classes/resources, write results in the new schema, reconcile counts/hashes, and prepare a recovery plan. Do not leave production systems "trying JDK then trying JSON" on every request indefinitely.

### 10.1. Versioning Strategy

When designing the new serializer, you can combine:

- **Key versioning:** `product:v2:42`.
- **Schema version in payload:** `"schemaVersion": 2` when structural variants must be managed.
- **Explicit DTOs:** field types, nullability, and defaults clearly documented.
- **TTL:** old caches phase out within a reasonable time window if business rules permit.
- **Source of truth:** a path to regenerate values on cache miss or malformed payloads.

Do not rely on Java class names as an exchange protocol identifier across multiple services. If a Java class is renamed while the JSON schema stays constant, compliant consumers can continue reading without disruption.

## 11. Distinguishing Incompatible Data Errors from Security Indicators

When a Redis `GET` fails during deserialization, the cause could be:

~~~mermaid
flowchart TD
    A["Redis read returns byte[]"] --> B{"Correct serializer for key?"}
    B -->|No| C["Wrong format / version / key collision"]
    B -->|Yes| D{"Payload valid against schema?"}
    D -->|No| E["Corrupt data, missing class, wrong field/type"]
    D -->|Yes| F{"Byte source trusted?"}
    F -->|No or unknown| G["Do not deserialize arbitrary Java types; handle per trust boundary"]
    F -->|Yes| H["Proceed with logic validation and resource limits"]
~~~

A `StreamCorruptedException` does not by itself prove an attack; it may stem from another service writing JSON to a key that your code reads with a JDK serializer. Conversely, **successful deserialization does not prove bytes are safe**. Investigation must combine deployment history, producers/consumers, Redis write permissions, key prefixes, and stack traces.

When logging errors:

- Log **redacted/masked key names** or key pattern groups rather than printing raw values.
- Log serializer type, schema version, producer app if known, payload size, and exception class.
- Never log full serialized bytes, credentials, or objects containing personal data.
- Avoid infinite retries on the same corrupted value.
- Decide whether cache failures should be treated as cache misses and rebuilt from the authoritative source or returned as controlled errors; this depends on data semantics.

## 12. Serializer Decision Matrix by Use Case

| Data in Redis | Recommended Direction | Rationale |
|---|---|---|
| Counters, flags, simple formatted tokens | `StringRedisTemplate` / String serializer | Simple, no Java object graph needed |
| Cache of a single known DTO, backed by a database | Typed JSON serializer with fixed DTO | Observable, versionable, minimal coupling to Java classes |
| Data exchanged across Java, Go, Node.js | JSON/Protobuf or agreed schema format | Cross-language compatibility |
| Data written by external/untrusted parties | Schema-based parser, input validation and limits | Never let bytes choose which Java class to instantiate |
| Spring `@Cacheable` caches | Configure `RedisCacheManager` and per-cache serializers | Prevents accidentally using default JDK value serializer |
| Legacy Java serialization data from old systems | Isolate and plan removal; filters only as secondary layer | Reduces risk surface during transition |
| Critical business data that cannot be lost | Proper database/persistence design; Redis in a defined role | Serializers do not provide durability or transactions |

Do not pick a serializer merely because the configuration snippet is short. Those bytes can outlive a single application release and become an inter-service data contract.

## 13. Common Pitfalls

**Pitfall 1: "Redis is in a private subnet, so JDK deserialization is safe."**

Another permitted service, an import job, or a leaked credential can still inject bytes into Redis. Trust boundaries must be evaluated along the **write → store → read** path, not just network topology.

**Pitfall 2: "Casting to the DTO right after `get()` is enough."**

If the serializer already called `ObjectInputStream.readObject()`, object graph instantiation happened before the cast. Checking business types afterward does not replace controlling deserialization.

**Pitfall 3: "Using `RedisTemplate<String, Product>` guarantees JSON storage."**

Generic types do not choose serializers. A template may still use `JdkSerializationRedisSerializer` for keys/values unless configured explicitly.

**Pitfall 4: "Unreadable binary data is encrypted data."**

Java serialization provides neither confidentiality nor integrity. TLS, access control, secrets management, and proper protections are still required.

**Pitfall 5: "Fixing `serialVersionUID` means every version stays readable."**

UID is only part of compatibility rules. Class names, fields, data types, and restoration logic can still change in incompatible ways.

**Pitfall 6: "Changing one RedisTemplate's serializer switches the whole system."**

`StringRedisTemplate`, other `RedisTemplate` beans, Redis Repositories, and Spring Cache can each use different serializers/configurations. Trace the actual read/write path of every keyspace.

**Pitfall 7: "JSON is always safe regardless of configuration."**

JSON with unrestricted polymorphic type metadata or dangerous custom deserializers still poses risks. Prefer fixed DTOs, clear schemas, validation, and controlled parser configurations.

**Pitfall 8: "Try JSON, and on error automatically fall back to Java deserialization."**

If data comes from untrusted sources, that fallback keeps the dangerous entry point open. Explicit keyspace versioning and migration are better.

## 14. Design Principles to Take Away

1. **Know which serializer is actually running.** Inspect configurations of `RedisTemplate`, `StringRedisTemplate`, and `RedisCacheManager` instead of guessing from annotations or generic types.
2. **Never invoke Java native deserialization on bytes that could be controlled by untrusted actors.** This is the single most important step to avoid Java's insecure deserialization risk class.
3. **Choose formats based on data contracts.** For typical caches, strings or typed JSON DTOs are easier to manage than Java object graphs.
4. **Never enable arbitrary type resolution.** When using JSON, constrain polymorphism, custom deserializers, and instantiable classes.
5. **Apply resource limits and access controls.** Block unauthorized writers, limit payload sizes, structural depth, timeouts, and Redis permissions.
6. **For legacy JDK serialization, filters are only an extra layer.** JEP 290/JEP 415 reduce some risks yet do not replace removing unsafe formats at untrusted boundaries.
7. **Version data and migrations explicitly.** Change keyspaces or schemas when changing formats; avoid misreading JDK bytes as JSON and vice versa.
8. **Maintain an authoritative source able to rebuild caches.** When a cache payload is malformed or untrusted, the safest response is often to discard the cache entry and rebuild from the trusted source.

Spring Data Redis makes converting between objects and bytes convenient, yet that very convenience can hide the fact that **deserialization executes Java logic inside the JVM**. Understanding this boundary helps you design caches with clear schemas, lower-risk version upgrades, and no entry points for untrusted object graphs via Redis.

## References

- [Spring Data Redis — Serializers and RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html)
- [Java 21 — Object Serialization Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/serialization/index.html)
- [Java 21 — ObjectInputFilter API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectInputFilter.html)
- [OpenJDK JEP 290 — Filter Incoming Serialization Data](https://openjdk.org/jeps/290)
- [OpenJDK JEP 415 — Context-Specific Deserialization Filters](https://openjdk.org/jeps/415)
- [CWE-502 — Deserialization of Untrusted Data](https://cwe.mitre.org/data/definitions/502.html)
