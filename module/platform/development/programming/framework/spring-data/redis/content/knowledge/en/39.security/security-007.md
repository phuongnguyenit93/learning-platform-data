# Validating Input Data Before Deserialization

In Spring Data Redis, a `RedisTemplate.opsForValue().get(key)` call can look simple: read a value, convert bytes into a Java object, and return it to the service. Yet **deserialization is a security boundary**, because data stored in Redis is not inherently trustworthy just because it resides on internal infrastructure.

Redis may hold data written by multiple applications, payloads constructed from user requests, legacy data from earlier deployments, restored backups, or corrupted content written by a compromised service. If an application deserializes directly into arbitrary objects, invalid data can cause type errors, excessive CPU/memory consumption, or, with **unsafe deserializers and configurations**, unexpected code-execution behavior.

This lesson focuses on **validating input data *before* deserialization** in Spring Data Redis: defining trust boundaries; selecting safe formats; bounding sizes; checking schemas, versions, and fields; using fixed-type DTOs; controlling polymorphic deserialization; handling corrupted entries; and testing both normal paths and malicious or oversized payloads.

One essential principle to distinguish:

- **Pre-deserialization validation:** checking conditions observable from raw bytes or metadata *before* invoking a parser/object mapper, such as byte size and read source boundaries.
- **Constrained parsing:** configuring the parser to bound nesting depth, string length, and number length, while forbidding arbitrary Java class selection.
- **Post-deserialization validation:** after parsing into a **predefined DTO**, validating fields, value ranges, and consistency with the key and business context.

You cannot fully validate JSON structure before parsing JSON; therefore you must **combine all three layers** rather than expecting a regex or a `TYPE` command to protect the whole path.

## 1. Why Is Data from Redis Still Untrusted Input?

Redis is usually deployed on a private network with ACLs and TLS, yet a private network **does not turn every stored value into a trusted object**. Common write flows include:

~~~text
User HTTP request
           |
           v
      Service A
           |
     SET cache:user:42
           |
           v
          Redis
           ^
           |
  Service B / Batch migration /
  Consumer / Backup restore
           |
           v
      Service C reads
           |
           v
 Deserialize -> Java object -> business logic
~~~

Even when Redis is shielded from the Internet, stored data may:

1. **Originate from external input.** Fields like `displayName`, `metadata`, or `filters` taken from requests remain untrusted data when cached.
2. **Be modified by another application.** A service accidentally sharing a namespace or using a different serializer can write incompatible payloads.
3. **Break during migrations.** Old and new deployments with different schemas may read the same key.
4. **Come from a backup restore.** Snapshots may hold outdated data incompatible with current code.
5. **Be altered by a permitted writer.** Redis ACLs shrink the attack surface, yet a compromised writer can still store payloads that readers must validate.
6. **Be far larger than expected.** Byte-valid values can trigger heap/GC spikes or dramatic expansion during parsing.

Therefore:

> Redis authentication and network isolation control **who can access the data store**; validation and serializer policies control **which data may become an application object**.

These two defensive layers complement rather than replace one another.

## 2. Data Flow in Spring Data Redis

With a serializer-configured template:

~~~text
                  Application
                      |
                  GET key
                      |
                      v
                 Redis server
                      |
                   raw bytes
                      |
                      v
               Redis driver
                      |
                      v
       RedisSerializer.deserialize(bytes)
                      |
                      v
               Java object
                      |
                      v
             Business validation
                      |
                      v
                   Service
~~~

An easy-to-miss detail: if `RedisTemplate<String, SomeObject>` uses a serializer that constructs objects automatically, deserialization has already run by the time `get(...)` **returns to the service**. Validating after `get(...)` is **too late** to prevent risks occurring during object instantiation.

To inspect **raw input bytes before parsing**, there are two approaches:

- Use a dedicated template reading `byte[]`, then check size and invoke a parser with explicit policies.
- Implement a custom `RedisSerializer<T>` that checks bytes inside `deserialize(byte[])` **before** handing them to a safe parser.

For illustrative code, the first approach makes the validation boundary clearer. In large applications, the second approach ensures all components sharing that serializer obey a central policy.

### Common Serialization APIs

| Storage Approach | How Data Is Converted | Risks to Watch |
| --- | --- | --- |
| `StringRedisSerializer` | UTF-8 bytes to String | Oversized strings, bad encoding, downstream parsing |
| `GenericJackson2JsonRedisSerializer` | JSON to object, potentially using type metadata | Allowed types, polymorphism config, schema/versioning |
| `Jackson2JsonRedisSerializer<T>` or DTO-bound JSON serializer | JSON to a known target type | Payload size, parser constraints, field validation |
| `JdkSerializationRedisSerializer` | Java Object Serialization stream to object | Deserialization risks of untrusted object graphs |
| `byte[]` serializer | Returns raw bytes from Redis | Lets you check before parsing, yet requires explicit limits and validation |
| Custom serializer | Depends on implementation | Must not bypass size caps, type allowlists, or validation |

**No serializer automatically makes business data trustworthy.** Properly configured JSON avoids arbitrary Java object-graph reconstruction; yet oversized, deeply nested, schema-invalid JSON or uncontrolled polymorphic metadata remains risky input.

## 3. Risks of Native Java Deserialization

`JdkSerializationRedisSerializer` relies on Java Object Serialization. That mechanism can reconstruct **arbitrary graphs of Java objects**, not merely a simple data DTO. On untrusted payloads, reconstructing arbitrary object graphs is a well-known risk class in the Java ecosystem, particularly if unsuitable classes/gadgets exist on the classpath.

An anti-pattern:

~~~java
RedisTemplate<String, Object> template = new RedisTemplate<>();
template.setValueSerializer(
    new org.springframework.data.redis.serializer.JdkSerializationRedisSerializer()
);

// When reading the value, Java Object Serialization may run
// before business code has any chance to validate the object.
Object value = template.opsForValue().get("cache:untrusted");
~~~

If the payload was tampered with beforehand, checking `value instanceof ExpectedDto` **after** `get` returns cannot undo risks triggered during deserialization itself.

### Choices for New Designs

- **Prefer fixed-schema DTOs** with serializers creating only required types.
- For JSON, specify a concrete target type such as `ProductCacheV1.class` instead of parsing into a class named by the input.
- Never store arbitrary object graphs in Redis simply to "read them back as-is" in another service.
- Never use native Java serialization for data influenced by users, external services, or untrusted sources.
- If a legacy system must use Java serialization, plan migration, lock down the data store, restrict types using filtering mechanisms such as `ObjectInputFilter` at deserialization time, and test on your target JDK/Spring versions.

Java filtering mechanisms reduce risk in legacy systems, but they are **not an excuse to keep unrestricted deserialization for untrusted input**. Migrating to an explicit schema format and typed DTOs is normally the right path.

## 4. JSON Also Needs Type Control: Avoid Unrestricted Polymorphism

Jackson is the standard tool for reading JSON in Spring. JSON itself does not carry Java objects, yet a polymorphic deserialization setup that lets the payload pick the target Java class reintroduces risks similar to unauthorized object creation.

Be especially cautious of:

~~~java
// Anti-pattern on untrusted data:
// mapper.activateDefaultTyping(... overly broad validator ...);

// Or a DTO letting the payload name arbitrary Java classes
// via type metadata using Id.CLASS without an allowlist.
~~~

Warning signs to audit:

- Default typing enabled on an `ObjectMapper` shared across diverse data.
- A JSON value carrying Java type metadata outside caller control.
- A subtype validator (`PolymorphicTypeValidator`) allowing overly broad packages.
- A deserialization target of `Object.class` when business logic expects one DTO.
- A service payload capable of instantiating classes from unrelated modules not meant for data transfer.

### Safer Pattern: Fixed DTOs

~~~java
public record ProductCacheV1(
    String productId,
    String title,
    long priceCents,
    long version
) {
}
~~~

Parse JSON directly into `ProductCacheV1.class` rather than reading a class name from JSON. If business rules truly require multiple subtypes, define a **closed set of subtypes** with schema-level discriminators rather than letting data name Java classes.

Example:

~~~java
import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;

@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "kind"
)
@JsonSubTypes({
    @JsonSubTypes.Type(
        value = FixedDiscount.class,
        name = "FIXED"
    ),
    @JsonSubTypes.Type(
        value = PercentDiscount.class,
        name = "PERCENT"
    )
})
public sealed interface Discount
    permits FixedDiscount, PercentDiscount {
}

public record FixedDiscount(long amountCents)
    implements Discount {
}

public record PercentDiscount(int percent)
    implements Discount {
}
~~~

In this pattern, `kind` selects only from declared subtypes (`FIXED` or `PERCENT`). You still must check that `amountCents` is non-negative, `percent` falls within range, and payload size is bounded. `Id.NAME` with a fixed subtype allowlist differs fundamentally from letting input choose arbitrary Java class names.

## 5. What Should Be Checked *Before* Calling the Parser?

Before parsing a Redis payload into a DTO, an input guard can enforce:

1. **Byte-length cap.** Reject values exceeding the budget for that key type.
2. **Expected format.** For example, this namespace holds only UTF-8 JSON; never decode arbitrarily as a Java object stream.
3. **Key namespace and caller scope.** A product reader accepts only valid IDs and accesses only `cache:product:v1:`.
4. **Schema/version envelope** when using a prefix format or separately verified metadata.
5. **Parser resource limits.** JSON nesting depth, string length, number length, and trailing tokens.
6. **Allowed target types.** The parser instantiates only a known DTO, never a class named by the payload.

After parsing, also verify:

- Are any required fields missing?
- Does the ID inside the value match the key or request?
- Are enums, states, and monetary values within valid domains?
- Is the schema version currently supported?
- Are there unknown fields, duplicate fields, or out-of-contract data?
- What happens when content is invalid: fail closed, conditionally evict, or quarantine?

### Size Checks Are an Early Guard, Not an Absolute Memory Shield

When `GET` returns a byte array to the client, **the payload bytes have already been transferred and allocated by Redis/the driver** before Java checks `bytes.length`. Application-level limits stop the parser from allocating even larger object graphs, yet do not eliminate network transfer, Redis output buffers, or initial byte allocations.

Therefore, also enforce:

- Size limits **when writing** values into the namespace.
- Never letting user endpoints store arbitrarily huge values.
- Avoiding commands that return massive entire collections when pagination/limits are possible.
- Proper Redis memory, network, and client limits.
- For large payloads, storing them elsewhere and keeping only a reference/metadata in Redis.

A `cache:product:v1:42` key with a 16 KiB budget differs from a Stream log entry or long report document. **Never apply a single context-free limit across every key type.**

## 6. Distinguishing Trust Across Redis Keys, Values, and Schemas

A system may build both keys and values from inputs. Checking only the value after reading a key still leaves key-namespace vulnerabilities:

~~~text
Input userId: "../admin"
        |
        v
key = "cache:user:" + userId
        |
        v
Accesses or overwrites wrong key region if authorization logic trusts the key
~~~

Redis has no filesystem `../` path traversal concept, yet this example shows how **unchecked string concatenation** breaks predictable key contracts, causes namespace collisions, or breaks tenant boundaries. Identifiers containing delimiters, newlines, or control characters also corrupt logs and monitoring.

Define the contract explicitly:

~~~text
Key template:
  cache:product:v1:{productId}

productId:
  [A-Za-z0-9_-]{1,64}

Serializer:
  UTF-8 key
  JSON value, ProductCacheV1

Maximum value bytes:
  16 KiB

TTL:
  Matches data class cache policy
~~~

Restricting identifier syntax **does not replace authorization checks**. If Redis holds per-tenant data, derive the tenant from an authenticated context rather than trusting a client-supplied `tenantId` inside the payload.

## 7. Spring Data Redis Example: Read Bytes First, Validate, Then Parse DTO

The following example implements a product cache enforcing:

- Keys shaped `cache:product:v1:{productId}`; `productId` allows only letters, digits, underscores, and hyphens, 1–64 characters.
- Values stored as UTF-8 JSON, capped at **16 KiB** prior to parsing.
- Deserializes solely into `ProductCacheV1`, never reading Java class names from payloads.
- JSON bounds nesting depth, string length, number length, and rejects duplicate fields.
- DTO must carry a supported schema version, `productId` matching the key, valid title, and non-negative price.
- Cache miss is handled separately; invalid payloads raise a measurable, handleable error.

This design applies **controlled raw-byte cache reading**, without altering the global behavior of every `RedisTemplate` in the application.

### 7.1. Dependencies

With Spring Boot 3.x, Java 21, and Groovy Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'com.fasterxml.jackson.core:jackson-databind'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
}
~~~

This example uses Jackson APIs providing `StreamReadConstraints` (Jackson 2.15+). In a Spring Boot project, rely on **BOM-managed dependency versions** and confirm your actual Jackson version supports those options. Never mix incompatible Jackson core/databind versions on the classpath.

### 7.2. Creating a `byte[]`-Only Template

~~~java
package com.example.redis.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.RedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class SafeRedisTemplateConfiguration {

    @Bean("rawJsonRedisTemplate")
    RedisTemplate<String, byte[]> rawJsonRedisTemplate(
            RedisConnectionFactory connectionFactory) {

        RedisTemplate<String, byte[]> template =
            new RedisTemplate<>();

        template.setConnectionFactory(connectionFactory);
        template.setKeySerializer(new StringRedisSerializer());
        template.setValueSerializer(RedisSerializer.byteArray());
        template.setHashKeySerializer(new StringRedisSerializer());
        template.setHashValueSerializer(RedisSerializer.byteArray());
        template.setDefaultSerializer(RedisSerializer.byteArray());
        template.afterPropertiesSet();
        return template;
    }
}
~~~

`StringRedisSerializer` keeps keys in UTF-8. Values return as `byte[]`, letting code check `bytes.length` **before invoking Jackson**. This bean takes no responsibility for parsing arbitrary objects inside the template.

Never swap serializers across existing `RedisTemplate` beans without checking which keys hold legacy formats. Changing serializers on an active namespace is a **storage-protocol change** that can render existing keys unreadable or turn them into cache misses.

### 7.3. Allowed Target DTO

~~~java
package com.example.redis.security;

public record ProductCacheV1(
    String productId,
    String title,
    long priceCents,
    int schemaVersion
) {
}
~~~

Never allow clients to supply JSON with arbitrary class names to instantiate objects other than `ProductCacheV1`. A Java record is an illustrative DTO; if real data includes nested structures, every nested type also needs an explicit schema and bounds.

### 7.4. Resource-Bounded Parser

~~~java
package com.example.redis.security;

import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.StreamReadConstraints;
import com.fasterxml.jackson.core.StreamReadFeature;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class SafeJsonConfiguration {

    @Bean("productCacheObjectMapper")
    ObjectMapper productCacheObjectMapper() {
        StreamReadConstraints constraints =
            StreamReadConstraints.builder()
                .maxNestingDepth(16)
                .maxStringLength(8192)
                .maxNumberLength(40)
                .build();

        JsonFactory jsonFactory = JsonFactory.builder()
            .streamReadConstraints(constraints)
            .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
            .build();

        ObjectMapper mapper = new ObjectMapper(jsonFactory);
        mapper.enable(
            DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES
        );
        mapper.enable(
            DeserializationFeature.FAIL_ON_TRAILING_TOKENS
        );
        return mapper;
    }
}
~~~

Explanation:

- `maxNestingDepth(16)`: rejects JSON nested deeper than allowed by the application.
- `maxStringLength(8192)`: caps individual string lengths in the parser; total byte-size limits apply separately.
- `maxNumberLength(40)`: caps numeric token length to reduce risk from extreme numbers.
- `STRICT_DUPLICATE_DETECTION`: forbids duplicate field names in the same JSON object.
- `FAIL_ON_UNKNOWN_PROPERTIES`: catches payloads containing fields outside the DTO schema.
- `FAIL_ON_TRAILING_TOKENS`: rejects trailing JSON tokens after the first value.

A dedicated bounded `ObjectMapper` for caching is safer than altering a global mapper without knowing the impact on other APIs. If adding Java Time modules or custom formats, register them intentionally and test against your schema.

**Never enable broad default typing on this mapper.** Never set the target to `Object.class` just to accept arbitrary value shapes.

### 7.5. Exception and Controlled Read Layer

~~~java
package com.example.redis.security;

public final class InvalidCachedPayloadException
        extends RuntimeException {

    public InvalidCachedPayloadException(String message) {
        super(message);
    }

    public InvalidCachedPayloadException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Reader service:

~~~java
package com.example.redis.security;

import java.io.IOException;
import java.util.Objects;
import java.util.Optional;
import java.util.regex.Pattern;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class SafeProductCacheReader {

    private static final int MAX_VALUE_BYTES = 16 * 1024;
    private static final int SUPPORTED_SCHEMA = 1;
    private static final long MAX_PRICE_CENTS = 100_000_000_000L;

    private static final Pattern PRODUCT_ID =
        Pattern.compile("[A-Za-z0-9_-]{1,64}");

    private final RedisTemplate<String, byte[]> redis;
    private final ObjectMapper mapper;

    public SafeProductCacheReader(
            @Qualifier("rawJsonRedisTemplate")
            RedisTemplate<String, byte[]> redis,
            @Qualifier("productCacheObjectMapper")
            ObjectMapper mapper) {
        this.redis = Objects.requireNonNull(redis);
        this.mapper = Objects.requireNonNull(mapper);
    }

    public Optional<ProductCacheV1> find(String productId) {
        validateProductId(productId);
        String key = "cache:product:v1:" + productId;

        byte[] bytes = redis.opsForValue().get(key);
        if (bytes == null) {
            return Optional.empty();
        }

        // Step 1: check byte length BEFORE parsing.
        if (bytes.length == 0 || bytes.length > MAX_VALUE_BYTES) {
            throw new InvalidCachedPayloadException(
                "Cache payload has invalid byte length"
            );
        }

        final ProductCacheV1 value;
        try {
            // Step 2: bounded parser and fixed DTO type.
            value = mapper.readValue(bytes, ProductCacheV1.class);
        } catch (IOException parseError) {
            throw new InvalidCachedPayloadException(
                "Cache payload is not valid ProductCacheV1",
                parseError
            );
        }

        // Step 3: validate parsed data against the contract.
        validateValue(value, productId);
        return Optional.of(value);
    }

    public static void validateProductId(String productId) {
        if (productId == null
                || !PRODUCT_ID.matcher(productId).matches()) {
            throw new IllegalArgumentException(
                "Invalid product identifier"
            );
        }
    }

    private static void validateValue(
            ProductCacheV1 value, String expectedProductId) {

        if (value == null) {
            throw new InvalidCachedPayloadException(
                "Cache payload must be an object"
            );
        }
        if (value.schemaVersion() != SUPPORTED_SCHEMA) {
            throw new InvalidCachedPayloadException(
                "Unsupported cache schema version"
            );
        }
        if (!expectedProductId.equals(value.productId())) {
            throw new InvalidCachedPayloadException(
                "Cache object identifier does not match key"
            );
        }
        if (value.title() == null
                || value.title().isBlank()
                || value.title().length() > 200
                || value.title().codePoints()
                    .anyMatch(Character::isISOControl)) {
            throw new InvalidCachedPayloadException(
                "Invalid product title"
            );
        }
        if (value.priceCents() < 0
                || value.priceCents() > MAX_PRICE_CENTS) {
            throw new InvalidCachedPayloadException(
                "Price is out of accepted range"
            );
        }
    }
}
~~~

#### Boundaries of This Example

1. `get(...)` on a `byte[]`-valued template yields raw payload bytes. Length checking occurs **before JSON parsing**, though after Redis/the driver allocates the raw bytes.
2. `null` from `GET` is a **cache miss**, not corrupted data.
3. JSON literal `null` does not produce a valid DTO: `mapper.readValue` returns `null` and `validateValue` rejects it.
4. The parser instantiates only `ProductCacheV1`, never a payload-specified subtype.
5. Missing primitive fields default (`0`), so always check `schemaVersion`, value ranges, and consistency; complex DTOs can use Bean Validation or custom validators.
6. Confirming `productId` matches the key prevents using data mistakenly written under another key; **it does not replace authorization** when accessing user data.
7. Never log raw `bytes` or raw JSON in exceptions; messages report only the error category.

### 7.6. Guarding the Write Path to Reduce Invalid Payloads

Safe reading is the final gate, yet systems should also **validate before writing**:

~~~java
package com.example.redis.security;

import java.time.Duration;
import java.util.Objects;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class SafeProductCacheWriter {

    private static final int MAX_VALUE_BYTES = 16 * 1024;

    private final RedisTemplate<String, byte[]> redis;
    private final ObjectMapper mapper;

    public SafeProductCacheWriter(
            @Qualifier("rawJsonRedisTemplate")
            RedisTemplate<String, byte[]> redis,
            @Qualifier("productCacheObjectMapper")
            ObjectMapper mapper) {
        this.redis = Objects.requireNonNull(redis);
        this.mapper = Objects.requireNonNull(mapper);
    }

    public void store(
            ProductCacheV1 value, Duration ttl) {
        Objects.requireNonNull(value);
        Objects.requireNonNull(ttl);
        SafeProductCacheReader.validateProductId(
            value.productId()
        );
        if (ttl.isZero() || ttl.isNegative()) {
            throw new IllegalArgumentException(
                "Cache TTL must be positive"
            );
        }

        // Production should reuse the reader's shared DTO validator
        // rather than maintaining two separate validation contracts.
        if (value.schemaVersion() != 1
                || value.title() == null
                || value.title().isBlank()
                || value.title().length() > 200
                || value.priceCents() < 0) {
            throw new IllegalArgumentException(
                "Invalid cache DTO"
            );
        }

        byte[] bytes;
        try {
            bytes = mapper.writeValueAsBytes(value);
        } catch (JsonProcessingException error) {
            throw new IllegalArgumentException(
                "Cannot serialize cache DTO", error
            );
        }
        if (bytes.length == 0 || bytes.length > MAX_VALUE_BYTES) {
            throw new IllegalArgumentException(
                "Serialized cache payload exceeds limit"
            );
        }

        redis.opsForValue().set(
            "cache:product:v1:" + value.productId(),
            bytes,
            ttl
        );
    }
}
~~~

In production, extract DTO validation into a shared validator so reader and writer enforce the exact same constraints. If other producers write to this namespace, **every producer must honor the contract**; a safe internal writer never excuses skipping validation on the reader.

## 8. Beyond Values: Redis Hashes, Streams, and Pub/Sub Also Carry Input

### 8.1. Redis Hash

With `HashOperations.entries(key)`, a service may receive many fields and values. For large Hashes, calling `HGETALL` pulls the **entire Hash** to the client before Java can inspect the field count.

Mitigations:

- Cap field counts and field sizes **on write**.
- Prefer `HGET` for explicit field lists when the full Hash is unneeded.
- Do not pull massive Hashes only to count entries afterward.
- If scanning many fields, consider cursor scanning/pagination per API semantics while bounding total items processed.
- For JSON-valued fields, apply the same byte limits, parser bounds, and typed DTOs.

A producer-written `className` or `type` field must never become an arbitrary Java class to instantiate. Map domain type codes to a closed allowlist of subtypes.

### 8.2. Redis Streams

Redis Streams store entries with field/value pairs that may come from external producers. Consumer groups do not guarantee schema validity. Before acknowledging (`XACK`) an entry:

1. Bound individual field/value sizes and field counts where producers are controllable.
2. Verify event type and schema version belong to the supported set.
3. Parse into concrete DTOs; never let events name arbitrary Java classes.
4. Validate business identifiers, timestamps, ranges, and tenant context.
5. `XACK` only per policy after successful handling or controlled dead-letter/quarantine routing.

Never `XACK` and discard unparseable entries blindly if evidence retention or reprocessing is required. Conversely, infinitely retrying a malformed payload creates a **poison message** stalling consumers; configure retry caps, DLQs, and observability.

### 8.3. Redis Pub/Sub

Pub/Sub is not a durable message queue. Messages published to a channel are delivered to active subscribers and decoders, without replay if a subscriber is offline.

Use a listener adapter that validates:

- The channel is on the expected list.
- Message size is within bounds.
- Encoding and message schema are valid.
- The event type is permitted; never deserialize arbitrary Java objects.
- A single malformed message cannot permanently crash the listener/container.

A subscriber must never read a Pub/Sub payload and use it directly as a class name, bean name, or command to execute.

## 9. Spring Cache and Redis Repositories: Put Validation in the Right Place

With `@Cacheable`, Spring Cache invokes the Redis cache manager and serializer **before** the business method or controller executes. Deserialization errors or risks can trigger inside the cache lookup layer itself:

~~~text
HTTP request
     |
     v
@Cacheable interceptor
     |
     v
RedisCacheManager / RedisCache
     |
     v
Cache value serializer
     |
     +-- deserialization happens here
     |
     v
Service method may never run on a cache hit
~~~

Therefore, you cannot simply put `@Valid` on the business method's return DTO and assume **every cache hit is validated before deserialization**. For protected data:

1. Configure a **safe value serializer** directly in the cache manager or per-cache configuration.
2. Pick **bounded DTOs/value types** instead of `Object` with trusted type metadata.
3. Enforce byte-size limits inside the serializer's `deserialize(byte[])` when cache infrastructure owns deserialization.
4. Configure serializers **per cache name** when caches differ in schemas and budgets.
5. Perform business-layer validation post-parse when constraints depend on user/tenant or business state.

### 9.1. Example Input-Guarding Serializer

Instead of parsing outside the template as earlier, you can write a serializer dedicated to `ProductCacheV1`. When cache infrastructure calls `deserialize`, the serializer checks raw bytes first.

~~~java
package com.example.redis.security;

import java.io.IOException;
import java.util.Objects;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.data.redis.serializer.RedisSerializer;
import org.springframework.data.redis.serializer.SerializationException;

public final class BoundedProductCacheSerializer
        implements RedisSerializer<ProductCacheV1> {

    private static final int MAX_BYTES = 16 * 1024;
    private final ObjectMapper mapper;

    public BoundedProductCacheSerializer(ObjectMapper mapper) {
        this.mapper = Objects.requireNonNull(mapper);
    }

    @Override
    public byte[] serialize(ProductCacheV1 value)
            throws SerializationException {
        if (value == null) {
            return new byte[0];
        }

        try {
            byte[] bytes = mapper.writeValueAsBytes(value);
            if (bytes.length > MAX_BYTES) {
                throw new SerializationException(
                    "Product cache value exceeds byte limit"
                );
            }
            return bytes;
        } catch (IOException error) {
            throw new SerializationException(
                "Cannot encode ProductCacheV1", error
            );
        }
    }

    @Override
    public ProductCacheV1 deserialize(byte[] bytes)
            throws SerializationException {
        if (bytes == null || bytes.length == 0) {
            return null;
        }
        if (bytes.length > MAX_BYTES) {
            throw new SerializationException(
                "Product cache value exceeds byte limit"
            );
        }

        try {
            ProductCacheV1 value =
                mapper.readValue(bytes, ProductCacheV1.class);

            if (value == null
                    || value.schemaVersion() != 1
                    || value.title() == null
                    || value.title().isBlank()
                    || value.title().length() > 200
                    || value.priceCents() < 0) {
                throw new SerializationException(
                    "Invalid ProductCacheV1 payload"
                );
            }
            return value;
        } catch (IOException error) {
            throw new SerializationException(
                "Cannot decode ProductCacheV1", error
            );
        }
    }
}
~~~

This serializer:

- Checks **byte length** before `mapper.readValue`.
- Parses directly into a **fixed type**.
- Throws `SerializationException` on invalid payloads.
- Reuses the `ObjectMapper` configured earlier with `StreamReadConstraints`.

In production code, extract field checks into a **shared validator** and add missing checks like `productId` and price upper bounds. A serializer whose `deserialize(byte[])` receives only bytes without the key cannot verify that `productId` matches the key being read; key/tenant consistency checks must live in a layer with full context.

Returning `byte[0]` for null serialization matches simple serializer conventions, yet verify the **null/cache-miss contract of your cache manager** in your Spring Data Redis version. Never assume every cache infrastructure treats zero-length values identically. In real systems, explicitly configure whether caching null values is allowed and align with Spring Cache conventions.

### 9.2. Notes on Repository Mapping

Spring Data Redis Repositories read Hashes and map multiple fields onto an entity. Annotating an entity with `@RedisHash` does not make every field safe:

- Put constraints on DTOs/entities and validate **before use** in business logic.
- For fields holding custom-serialized JSON, enforce byte and parser limits for those fields.
- Restrict what user input can write into sensitive properties.
- Never equate successfully reading an entity with authorization.
- During schema changes, handle versioning/migrations and check reader/writer compatibility.

**Redis repository mapping and native Java object deserialization are distinct mechanisms**; risks depend on serializers, mapping configuration, and each field's data origin. Do not lump all mapping errors under a vague "Redis is untrusted" label.

## 10. Resource Limits and Denial-of-Service Resilience

Even when a parser forbids arbitrary object instantiation, syntactically valid payloads can still exhaust CPU, heap, or application threads.

### 10.1. Oversized Values

~~~text
GET cache:small-object
       |
       v
Redis returns 15 MB instead of <= 16 KiB
       |
       v
Driver receives/allocates bytes
       |
       v
Application checks byte size -> rejects parsing
~~~

Checking after receiving bytes **prevents memory blowup during parsing**, yet still pays the cost of fetching 15 MB. Defense requires write-side caps, thoughtful key/value design, and size monitoring. If Redis holds diverse large objects, do not blindly run full `GET`s hoping Java-side size checks alone prevent resource exhaustion.

### 10.2. Deeply Nested JSON

A JSON payload under the byte cap can still nest thousands of arrays or objects. The parser needs depth bounds independent of byte length—such as `maxNestingDepth(16)` for a shallow DTO.

### 10.3. Extremely Long Strings and Numbers

A long string field or huge multi-digit number raises parsing cost. `maxStringLength` and `maxNumberLength` act as parser-level guards; post-parse checks enforce stricter domain rules, like capping product titles at 200 characters.

### 10.4. Unbounded Collections

When data contains a large `List` or `Map`, byte limits do not directly reflect post-parse object graph overhead. For DTOs with collections, cap **element counts, total nested items, and business cardinality**. Where streaming parser APIs allow, read incrementally and abort once item caps are exceeded instead of building a giant collection first.

### 10.5. Decompression Bombs

If an app compresses values before storing in Redis and decompresses before JSON parsing, a tiny payload can expand enormously:

~~~text
Compressed Redis value 8 KiB
          |
          v
    Unbounded decompression
          |
          v
   Tens or hundreds of MB
          |
          v
      JSON deserializer
~~~

Checking `compressedBytes.length` is **not enough**. Cap **decompressed byte count**, expansion ratio, CPU/timeouts, and parser depth. Decompressing into an unbounded byte buffer before checking length can already be too late.

### 10.6. Aggregate Resource Usage Under Concurrency

A 16 KiB payload looks tiny, yet 20,000 concurrent requests reading values simultaneously still creates heavy allocation pressure:

~~~text
memory pressure ≈ in-flight payload count × bytes per payload
               + object allocations + driver buffers
               + framework overhead
~~~

This is a conceptual model, not an exact heap formula. Add **concurrency limits**, timeouts, pool/connection queues, request budgets, and circuit breakers. Bounded parsers do not replace backpressure.

## 11. Choosing Behavior on Invalid Payloads

A schema-invalid Redis payload should not always be treated like a normal cache miss. Behavior depends on Redis's role:

| What Redis Holds | When Payload Is Invalid | Typically Appropriate Action |
| --- | --- | --- |
| Fully regenerable DB-backed cache | Can load authoritative data | Record metric, bounded fallback, controlled cache refresh |
| Sessions/authentication | Cannot trust session state | Fail closed; never grant permissions or treat session as valid |
| Rate limits/quotas/locks | Bad data breaks correctness | Halt critical action, investigate/reconcile |
| Unprocessed Stream events | Corrupt payload risks poison message | Route to DLQ/quarantine per policy, never `XACK` blindly |
| Primary business data in Redis | Deleting risks data loss | Preserve bytes and metadata, alert incident/migration |

### 11.1. Never Catch All Exceptions and Return Empty

An anti-pattern:

~~~java
try {
    return Optional.ofNullable(redis.opsForValue().get(key));
} catch (RuntimeException error) {
    return Optional.empty();
}
~~~

This collapses all of the following into "key missing":

- Redis connection/timeout errors.
- Schema-invalid data.
- Serialization errors.
- Missing ACL permissions.
- Programming bugs.

Instead, distinguish **cache miss**, **invalid payload**, **Redis unavailable**, and **business error**. For best-effort caches, falling back on certain error classes may be valid, provided metrics and database load shedding are in place.

### 11.2. Never Blindly Delete Newer Values While Cleaning Corrupt Cache Entries

Suppose:

~~~text
T0   Reader A reads corrupt cache bytes
T1   Writer B updates key with valid JSON
T2   Reader A unconditionally calls DEL key
T3   B's valid value is deleted
~~~

If auto-evicting corrupt entries, account for write races. For regenerable caches, blind eviction may just add misses while loading the primary store. Alternatives:

- Let the key expire via TTL and move to a new versioned namespace.
- Evict only via an atomic **compare-and-delete** verifying the stored payload still matches the corrupt bytes read, if the need is clear.
- Send entry metadata to safe quarantine/logs without printing sensitive raw payloads.
- Use a dedicated migration job rather than bulk deleting in the request path.

If using Lua compare-and-delete, cap argument sizes and weigh the cost of resending large bytes. With versioned payloads or timestamps, compare-and-set/version checks are often cleaner.

### 11.3. Poison Messages and Error Classification

A message failing due to an unsupported schema differs from a transient connection error:

- Connection errors: retry with bounded backoff and deadlines.
- Malformed JSON or unknown subtypes: retrying the exact same bytes **will not fix the data**.
- Newer schema version: deploy compatible consumers or apply versioning/forwarding rules.
- Business validation failure: reject, DLQ, or reconcile; do not assume a parser bug.

This classification prevents corrupt entries from looping indefinitely or overwriting valid state.

## 12. Redis ACLs, TLS, and Namespace Separation as Complementary Controls

Client-side validation does not replace Redis access control. A multi-service system should apply:

1. **TLS** between applications and Redis/Sentinel when required by infrastructure or threat models, enforcing certificate verification per policy.
2. **Least-privilege Redis ACLs:** services receive only needed commands and key patterns.
3. **Separate writer and reader identities** where fitting. Read-only cache consumers need no write/delete rights across Redis.
4. **Namespaces by function, schema version, and tenant** paired with proper authorization.
5. **Environment separation:** never share Redis or credentials between test and production.
6. **Secret protection:** never hardcode Redis passwords in code, stack traces, or committed config files.
7. **Write-anomaly monitoring:** alert on oversized payloads, unexpected key types, and decode error spikes.

Example key convention:

~~~text
cache:product:v1:<id>
cache:user:v3:<tenant>:<id>
stream:events:v2
lock:job:<jobId>
~~~

Key prefixes reduce collisions and blast radius, yet Redis ACL key patterns and tenant authorization must be thoughtfully engineered; **a prefix alone does not constitute a data authorization system**.

### Integrity and Confidentiality Are Distinct Properties

- TLS protects data **in transit**, not whether values stored inside Redis match a schema.
- Encryption at rest reduces byte exposure on disk, not making decrypted payloads automatically trustworthy.
- Signatures/HMACs detect tampering if backed by **separate protected verification keys**, yet do not prevent oversized payloads, schema drift, or replay without extra design.
- Schema validation catches many malformed inputs, yet cannot prove the writer was authorized to update that record.

When integrity from a specific producer must be verified, wrap payloads in an envelope with schema version, payload, issuer, and MAC/signature verified **before deserializing the payload into objects**, while protecting verification keys and countering replay per your threat model. Never add an unkeyed `checksum` field and claim it stops malicious writers.

## 13. Unit Testing: Covering Pre- and Post-Deserialization Paths

A test suite for `SafeProductCacheReader` should prove that **oversized payloads are rejected before reaching the mapper**, and that the parser/validator reject malformed payloads. Unit tests can mock `RedisTemplate` to inject arbitrary bytes without needing a Redis server.

Example using JUnit 5, Mockito, and AssertJ:

~~~java
package com.example.redis.security;

import java.nio.charset.StandardCharsets;
import java.util.Optional;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.core.ValueOperations;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class SafeProductCacheReaderTest {

    private RedisTemplate<String, byte[]> redis;
    private ValueOperations<String, byte[]> values;
    private SafeProductCacheReader reader;

    @BeforeEach
    void setUp() {
        redis = mock(RedisTemplate.class);
        values = mock(ValueOperations.class);
        when(redis.opsForValue()).thenReturn(values);

        reader = new SafeProductCacheReader(
            redis,
            new SafeJsonConfiguration().productCacheObjectMapper()
        );
    }

    @Test
    void returnsEmptyWhenKeyIsMissing() {
        when(values.get("cache:product:v1:p-1"))
            .thenReturn(null);

        assertThat(reader.find("p-1")).isEmpty();
    }

    @Test
    void readsKnownDtoWhenJsonIsValid() {
        byte[] payload = """
            {
              "productId": "p-1",
              "title": "Keyboard",
              "priceCents": 125000,
              "schemaVersion": 1
            }
            """.getBytes(StandardCharsets.UTF_8);

        when(values.get("cache:product:v1:p-1"))
            .thenReturn(payload);

        Optional<ProductCacheV1> result = reader.find("p-1");

        assertThat(result).isPresent();
        assertThat(result.orElseThrow().title())
            .isEqualTo("Keyboard");
    }

    @Test
    void rejectsOversizedBytesBeforeJsonParsing() {
        byte[] oversized = new byte[16 * 1024 + 1];
        when(values.get("cache:product:v1:p-1"))
            .thenReturn(oversized);

        assertThatThrownBy(() -> reader.find("p-1"))
            .isInstanceOf(InvalidCachedPayloadException.class)
            .hasMessageContaining("byte length");
    }

    @Test
    void rejectsInvalidJson() {
        byte[] malformed = "{\"productId\":"
            .getBytes(StandardCharsets.UTF_8);
        when(values.get("cache:product:v1:p-1"))
            .thenReturn(malformed);

        assertThatThrownBy(() -> reader.find("p-1"))
            .isInstanceOf(InvalidCachedPayloadException.class);
    }

    @Test
    void rejectsUnexpectedJsonField() {
        byte[] payload = """
            {
              "productId": "p-1",
              "title": "Keyboard",
              "priceCents": 125000,
              "schemaVersion": 1,
              "unexpected": "not-in-schema"
            }
            """.getBytes(StandardCharsets.UTF_8);
        when(values.get("cache:product:v1:p-1"))
            .thenReturn(payload);

        assertThatThrownBy(() -> reader.find("p-1"))
            .isInstanceOf(InvalidCachedPayloadException.class);
    }

    @Test
    void rejectsWrongSchemaVersion() {
        byte[] payload = """
            {
              "productId": "p-1",
              "title": "Keyboard",
              "priceCents": 125000,
              "schemaVersion": 99
            }
            """.getBytes(StandardCharsets.UTF_8);
        when(values.get("cache:product:v1:p-1"))
            .thenReturn(payload);

        assertThatThrownBy(() -> reader.find("p-1"))
            .isInstanceOf(InvalidCachedPayloadException.class)
            .hasMessageContaining("schema");
    }

    @Test
    void rejectsObjectClaimingAnotherProductId() {
        byte[] payload = """
            {
              "productId": "p-999",
              "title": "Keyboard",
              "priceCents": 125000,
              "schemaVersion": 1
            }
            """.getBytes(StandardCharsets.UTF_8);
        when(values.get("cache:product:v1:p-1"))
            .thenReturn(payload);

        assertThatThrownBy(() -> reader.find("p-1"))
            .isInstanceOf(InvalidCachedPayloadException.class)
            .hasMessageContaining("identifier");
    }

    @Test
    void rejectsInvalidIdentifierBeforeRedisAccess() {
        assertThatThrownBy(() -> reader.find("tenant:other:p-1"))
            .isInstanceOf(IllegalArgumentException.class);
    }
}
~~~

These tests verify the **implemented application branches**. They do not prove Redis actually stores expected bytes, Redis ACLs are properly configured, or all cache serializers are safe; those require integration tests and infrastructure verification.

In this example, `mock(RedisTemplate.class)` and `mock(ValueOperations.class)` may trigger unchecked warnings due to Java generic type erasure. Use `@SuppressWarnings("unchecked")` locally per project conventions. Mock generic warnings are never an excuse to allow deserialization into `Object.class` in production.

### Testing Duplicate Fields and Deeply Nested JSON

When enforcing strict schemas, also test:

~~~json
{
  "productId": "p-1",
  "productId": "p-2",
  "title": "Keyboard",
  "priceCents": 125000,
  "schemaVersion": 1
}
~~~

With `STRICT_DUPLICATE_DETECTION`, JSON containing two `productId` keys must be rejected. JSON nested beyond `maxNestingDepth` must also be rejected by the parser. Likewise, test oversized strings/numbers and unknown fields.

Never write tests assuming "last field wins" on duplicate fields; behavior can vary across parsers or services, creating **parser differential** vulnerabilities where a validator sees one value and an executor sees another.

## 14. Integration Testing: Real Bytes Stored in Redis

Unit tests control raw byte inputs, yet cannot guarantee real templates and serializers do not add unintended conversions. Using Testcontainers, verify:

- Valid JSON written via the writer reads back via the reader into the DTO.
- Malformed bytes written directly to the test key are rejected by the reader.
- Values exceeding the byte budget are never parsed.
- Missing keys return empty instead of masking Redis errors.
- Cleanup deletes only isolated test keys.

Example:

~~~java
package com.example.redis.security;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Testcontainers
@SpringBootTest(
    classes = SafePayloadIntegrationTest.TestApp.class
)
class SafePayloadIntegrationTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import({
        SafeRedisTemplateConfiguration.class,
        SafeJsonConfiguration.class,
        SafeProductCacheReader.class,
        SafeProductCacheWriter.class
    })
    static class TestApp {
    }

    @Container
    static final GenericContainer<?> REDIS =
        new GenericContainer<>(DockerImageName.parse("redis:7.2-alpine"))
            .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add(
            "spring.data.redis.port",
            () -> REDIS.getMappedPort(6379)
        );
    }

    @Autowired
    @Qualifier("rawJsonRedisTemplate")
    RedisTemplate<String, byte[]> rawRedis;

    @Autowired
    SafeProductCacheReader reader;

    @Autowired
    SafeProductCacheWriter writer;

    @Test
    void knownDtoCanRoundTrip() {
        String id = "it-" + UUID.randomUUID();
        String key = "cache:product:v1:" + id;

        try {
            writer.store(
                new ProductCacheV1(id, "Monitor", 400000, 1),
                Duration.ofSeconds(30)
            );

            ProductCacheV1 loaded = reader.find(id).orElseThrow();
            assertThat(loaded.productId()).isEqualTo(id);
            assertThat(loaded.title()).isEqualTo("Monitor");
            assertThat(loaded.schemaVersion()).isEqualTo(1);
        } finally {
            rawRedis.delete(key);
        }
    }

    @Test
    void rejectsMalformedRedisValue() {
        String id = "it-" + UUID.randomUUID();
        String key = "cache:product:v1:" + id;

        try {
            rawRedis.opsForValue().set(
                key,
                "{not valid json".getBytes(StandardCharsets.UTF_8),
                Duration.ofSeconds(30)
            );

            assertThatThrownBy(() -> reader.find(id))
                .isInstanceOf(InvalidCachedPayloadException.class);
        } finally {
            rawRedis.delete(key);
        }
    }

    @Test
    void rejectsPayloadLargerThanPolicy() {
        String id = "it-" + UUID.randomUUID();
        String key = "cache:product:v1:" + id;

        try {
            rawRedis.opsForValue().set(
                key,
                new byte[16 * 1024 + 1],
                Duration.ofSeconds(30)
            );

            assertThatThrownBy(() -> reader.find(id))
                .isInstanceOf(InvalidCachedPayloadException.class);
        } finally {
            rawRedis.delete(key);
        }
    }
}
~~~

This integration test runs against a dedicated Redis instance; the test runner needs Docker or a compatible container runtime. `@Import` registers the lesson's template, mapper, reader, and writer. Each test builds UUID-scoped keys to avoid collisions and cleans up only its own key in `finally`. Never run `FLUSHALL` or `FLUSHDB` on a potentially shared Redis.

This example does not verify an ACL policy or TLS connection because the minimal Redis container does not configure them. When security requirements include ACL/TLS, add corresponding environment integration tests.

### Test Reading Legacy-Serialized Payloads Too

A long-lived system may have stored on the same key:

~~~text
cache:product:123
  ├── JDK serialization from version A
  ├── generic-typed JSON from version B
  └── fixed-DTO JSON from version C
~~~

In that case, changing the serializer for the same key **does not automatically migrate existing values**. Integration tests should include byte fixtures representing supported legacy versions and confirm code handles migration contracts as intended.

Do not keep a risky deserializer in the live request path just to read every legacy format when an isolated migration job can convert them under controlled conditions.

## 15. Schema Migration Without Reopening Deserialization Risks

A common excuse for keeping overly permissive deserializers is "we still need to read old data." Long term, that creates security debt. To adopt fixed-schema DTOs safely, separate **legacy data reading** from the **new request read path**.

### 15.1. Versioned Namespaces

Example:

~~~text
cache:product:v1:p-42   ← ProductCacheV1 JSON payload
cache:product:v2:p-42   ← ProductCacheV2 JSON payload
~~~

Workflow:

1. Define `ProductCacheV2` with explicit byte and parser limits.
2. Deploy new writers writing exclusively to `v2`.
3. New readers read `v2` using the matching serializer/validator.
4. If old cached data must be preserved, run a **separate** migration job on the bounded dataset reading `v1` under an evaluated safe policy.
5. Track migrated counts, rejected counts, and hit-ratio impact.
6. Wait for TTL expiry or run controlled `v1` cleanup once no consumers remain.
7. Remove legacy deserializer dependencies/configuration from normal request paths once finished.

For **fully regenerable caches**, reading `v1` back is often unnecessary: simply abandon `v1` and warm `v2` from the authoritative store with cache-stampede protections. For non-regenerable business data, use a fully reconciled migration rather than letting TTLs expire blindly.

### 15.2. Schema Version Inside the Payload

An illustrative JSON envelope:

~~~json
{
  "schemaVersion": 2,
  "productId": "p-42",
  "title": "Keyboard",
  "priceCents": 125000,
  "currency": "VND"
}
~~~

Never let payloads declare `javaClass` or `serializerClass` and instantiate them via reflection. The application can read a **version field from a finite allowed set**, dispatch to the matching reader/DTO, and reject unsupported versions.

However, if you must inspect the version **before parsing the entire JSON**, define a clear envelope and use a bounded streaming parser to extract the version or protected external metadata. Unboundedly parsing into `Map<String,Object>` just to peek at the version fails to bound resources before deserialization.

### 15.3. Reusing Schema Fixtures

To prevent parser skew across languages and services:

- Maintain canonical JSON fixtures for every supported version.
- Test duplicate JSON fields, unknown fields, and missing required fields.
- Test Unicode strings and character encoding.
- Define exact handling for invalid numbers, nulls, and enums.
- Enforce total byte and collection-size caps in the contract.
- When producers use a different language, verify producer and consumer share identical schema semantics.

A schema contract works only when **all writers and readers** enforce it consistently.

## 16. Telemetry: Tracking Rejected Payloads Without Leaking Data

When an invalid payload arrives, logging only a parser stack trace obscures impact. Yet **logging the raw Redis value** risks exposing sensitive data.

Fields worth recording:

| Observable Field | Safe Example | Purpose |
| --- | --- | --- |
| Namespace | `cache:product:v1` | Identifies data class |
| Failure category | `oversize`, `malformed_json`, `schema_mismatch` | Classifies root cause |
| Payload byte size | `18752` | Checks budget violations |
| Expected schema | `ProductCacheV1` | Identifies contract |
| Schema version | `1` or `unsupported` | Detects rollout skew |
| Service/producer identity | Authorized writer service name | Traces faulty producer |
| Trace/correlation ID | Managed technical ID | Links to request flow |
| Redis topology | Standalone/Sentinel/Cluster | Distinguishes data issues from failovers |

Avoid logging:

- Raw JSON values, byte payloads, or Java serialized bytes.
- Redis passwords, session tokens, or API keys.
- Full keys containing user IDs or tenant IDs unnecessarily.
- Unescaped/unredacted user-provided strings that can break log structure.
- Per-Redis-key metric labels that blow up cardinality.

Conceptual metrics:

~~~text
redis_payload_validation_failed_total{
  namespace="cache_product_v1",
  reason="oversize"
}

redis_payload_validation_failed_total{
  namespace="cache_product_v1",
  reason="schema_mismatch"
}
~~~

These are **suggested metric names**, not built-in Spring Boot metrics. Instrument them with Micrometer or your observability library.

Besides rejection counts, monitor:

- Cache miss and fallback rates after schema rollouts.
- Value size trends per namespace.
- Memory/GC pressure during decoding.
- Redis command latency and in-flight request counts.
- Number of producers emitting invalid values over short windows.
- Stream DLQ/quarantine entry counts.

An alert on a sudden spike in `schema_mismatch` right after a deployment is far more actionable than an isolated log line dumping a huge Jackson stack trace without namespace context.

## 17. Incident Response When Anomalous Payloads Are Detected

When a service reports deserialization failures:

~~~text
             Redis value read
                     |
                     v
         Byte length within limit?
             /               \
            No               Yes
             |                |
             v                v
        Reject early     Parse with DTO/constraints
                              |
                    +---------+----------+
                    |                    |
                  Error               Success
                    |                    |
                    v                    v
              Log category       Validate fields/ranges
                    |                    |
                    +---------+----------+
                              |
                              v
                        Apply policy
                   cache / session / stream /
                        business data
                              |
                +-------------+-------------+
                |             |             |
                v             v             v
          Bounded        Fail closed     Quarantine
          fallback            |          / migration
                |             |             |
                +-------------+-------------+
                              |
                              v
                      Metrics + investigation
~~~

Practical steps:

1. **Determine scope:** a single key, one namespace, or every newly deployed app?
2. **Collect safe metadata:** byte size, serializer/schema version, exception class, and timestamp.
3. **Check producers:** which service recently wrote to this namespace? Did a serialization library or record schema change?
4. **Assess data role:** regenerable cache or irreplaceable data?
5. **Contain blast radius:** throttle fallbacks, consumer retries, and write rates during the incident.
6. **Choose recovery:** fix the writer, migrate, switch to a new namespace, or quarantine—never wipe all of Redis by default.
7. **Reconcile:** verify new keys/values pass schema checks, error rates drop, and business flows recover.

### Rollout Error Example

Before deploy:

~~~text
Service A writes JSON v1 with integer priceCents.
Service B reads ProductCacheV1.
~~~

After deploy:

~~~text
New Service A writes priceCents as an object { amount, currency }.
Old Service B still reads ProductCacheV1.
~~~

If both share the `v1` prefix, deserialization breaks en masse or misinterprets values. A safer approach is **bumping `schemaVersion`/namespace `v2`, testing compatibility, and rolling out producer–consumer cleanly**, instead of turning off `FAIL_ON_UNKNOWN_PROPERTIES` and hoping for the best.

## 18. Common Mistakes

| Mistake | Risk | Remediation |
| --- | --- | --- |
| Trusting Redis values because Redis sits on a private network | Writers or external inputs can still corrupt data | Treat values as untrusted input; validate against contracts |
| `RedisTemplate<String,Object>` with arbitrary-type serializer | Can instantiate unexpected object graphs | Prefer typed DTOs and restricted serializers |
| Native Java deserialization on untrusted data | Object graph/gadget and resource risks | Avoid; migrate or strictly filter legacy types |
| Enabling overly broad Jackson default typing | Payloads can control Java subtypes | Avoid arbitrary `Id.CLASS`; use closed allowlists |
| Deserializing before checking size | Parser may already allocate huge objects | Read raw bytes or check inside serializer before parsing |
| Checking only compressed byte length | Decompressed output can expand massively | Bounded decompression and parser limits |
| Setting only max byte size | Small, deeply nested or high-field-count JSON still spikes CPU/RAM | Add depth, string, number, and collection limits |
| Parsing into `Map<String,Object>` for "flexibility" | Unclear schema, weak type safety | Versioned DTOs with explicit validation |
| Trusting payload-declared type metadata | Parser can instantiate unintended types | Typed DTOs or discriminator + closed subtype allowlist |
| Deleting the key on every decode error | Risk of data loss or wiping newer valid writes | Policy per data class and conditional cleanup |
| Retrying every decode error | Poison messages/cache entries never heal themselves | Classify malformed/schema errors; DLQ or migrate |
| Swallowing serializer errors as cache misses | Hides rollout bugs or incompatible formats | Record metrics and apply bounded fallback |
| Validating only on write | Other writers or backups can introduce bad payloads | Validate at the read boundary too |
| Validating only in controllers | `@Cacheable` deserializes before the method runs | Enforce limits in the Redis serializer/cache layer |
| Not verifying payload ID matches key | Serving data belonging to another resource | Check key and DTO share the same context |
| Using Redis key prefixes as authorization | Other tenants can read data if code skips checks | Verify identity and permissions in the service |
| Logging raw payloads on parse errors | Leaks secrets or PII | Log reason, namespace, byte size, and trace ID |
| Changing serializers on existing keys without migration | Widespread cache misses and decode errors | Version namespaces, roll out cleanly, test fixtures |
| Testing only valid JSON | Misses oversize, unknown subtypes, duplicate fields | Write unit and integration tests for bad payloads |
| Bounding parser limits without bounding concurrency | Many valid inputs still exhaust heap/CPU | Concurrency limits, backpressure, memory budgets |

## 19. When Is Validation Not Enough?

Some issues cannot be solved by JSON validation alone:

**Authorization:** a payload may match the schema perfectly yet belong to a resource the caller cannot view. Verify identity, tenant, and roles in the business layer.

**Stale data:** a valid DTO may hold outdated data from a replica or uninvalidated cache. Design appropriate TTLs, versioning, consistency, and invalidation.

**Data integrity:** valid JSON does not prove an authorized producer wrote it. Require ACLs, writer controls, and cryptographic integrity checks if required by your threat model.

**Atomicity:** multiple valid keys do not make multi-step business updates atomic. Design Redis transactions/scripts, database transactions, or idempotency explicitly.

**Availability:** a parser rejecting oversized payloads cannot save a server flooded by huge `GET`s. Enforce write-side limits, thoughtful data modeling, network/connection limits, and load shedding.

**Schema evolution:** strict validators reject new versions until compatible readers roll out. Plan rollouts and migrations rather than disabling all checks.

Security at the deserialization boundary is **one piece of defense in depth**, not a replacement for consistency and access controls.

## 20. Implementation Checklist for Spring Data Redis

For any new Redis namespace, answer these questions before implementing:

- **Who writes this key?** Which Redis user, service identity, and upstream data source.
- **What is the value?** String, JSON DTO, Hash, Stream event, or raw bytes?
- **What are the limits?** Maximum encoded bytes, nesting depth, string length, collection size, and TTL.
- **Which types can be created?** Fixed DTOs or allowlisted subtypes; never Java classes named by input.
- **Which schema versions are supported?** How versions roll out across multiple services.
- **Where does validation live?** Before the parser, inside the parser/serializer, and after DTO mapping.
- **What happens on invalid data?** Cache fallback, fail closed, DLQ/quarantine, or migration.
- **How is it tested?** Bad-byte unit tests and real-Redis integration tests.
- **How is it monitored?** Track failure reasons, namespaces, sizes, rejection counts, and business impact.

A concise workflow:

~~~text
            Define Redis namespace + schema
                           |
                           v
           Grant least-privilege writer/reader ACLs
                           |
                           v
              Validate data before SET
                           |
                           v
                 Redis stores raw bytes
                           |
                           v
               Read bytes with proper budget
                           |
                           v
                Check byte length early
                           |
                           v
            Parser with resource constraints
                           |
                           v
                   Fixed-type DTO
                           |
                           v
            Validate version/ranges/context
                           |
                  +--------+--------+
                  |                 |
                Valid            Invalid
                  |                 |
                  v                 v
           Use in service    Error-handling policy
                              + safe telemetry
~~~

## 21. Summary

**Validating input data before deserialization** in Spring Data Redis requires deeper design than calling `RedisTemplate.get(...)` and checking for `null`. Redis is a byte store; the serializer decides how those bytes are interpreted and turned into Java objects.

Core practices:

1. **Never blindly trust Redis values.** Data can come from user inputs, other writers, migrations, or backups.
2. **Avoid native Java deserialization and unrestricted polymorphic typing** for untrusted inputs.
3. **Check byte limits before running the parser**, alongside resource constraints for JSON, collections, and compressed payloads.
4. **Deserialize into concrete DTOs**, with explicit schema versions and closed subtype lists when needed.
5. **Validate post-parse** business invariants, identifiers, tenants, and value ranges.
6. **Place validation at the actual deserialization boundary**, especially inside `RedisTemplate` and Spring Cache serializers.
7. **Classify errors by data role**, never retrying endlessly or deleting critical data on parse errors.
8. **Test with raw bytes and a real Redis instance**, covering oversized payloads, malformed JSON, unsupported fields, wrong versions, and key mismatches.
9. **Combine ACLs, TLS, telemetry, and migrations** to shrink the fault surface and detect anomalous data early.

A secure application is not one whose parser "can read anything," but one that **accepts only authorized data, within bounded resources, matching a schema the business logic understands**. When those boundaries sit before and during deserialization, Spring Data Redis caches and streams stay fast without turning Redis data into an uncontrolled path for creating Java objects.
