# Customizing ObjectMapper and Keeping Configuration Consistent Across Parties

## 1. The Problem to Solve

Redis stores data as bytes, not Java objects directly. When using Spring Data Redis to cache a DTO, the application must decide how to convert the object into stored Redis data and how to reconstruct the object on read. When JSON is chosen, the component governing most conversion rules is **Jackson ObjectMapper**.

In a single-service application, writing and reading may appear effortless because both steps share the exact same serializer. Yet when Redis data is shared across multiple services, multiple deployed versions, or clients written in Python/Node.js, configuration differences quickly turn into bugs:

- Service A writes **Instant** as an ISO-8601 string, while Service B expects a numeric timestamp.
- Service A stores property **userId**, while Service B looks for **user_id**.
- Service A embeds Java class info **@class** in JSON, while another client knows nothing about that package/class.
- Service A ignores unknown properties; Service B rejects JSON whenever a new field appears.
- Service A stores a JSON object, while Service B reads the same key as a plain string or a Redis hash.
- Two services share a key prefix yet use different versions of the DTO structure.

Therefore, the task does not stop at calling **new ObjectMapper()**. You must design a **wire contract**, configure serializers in the right places, and ensure every party interprets the stored data identically.

In this article, "parties" include components within the same Spring Boot application, separate microservices, old/new releases running side by side, and non-Java applications.

## 2. Data Path Through ObjectMapper

With a **RedisTemplate<String, UserCacheDocument>** using a JSON serializer, the write/read flow looks like:

~~~text
Java UserCacheDocument
         |
         v
Jackson2JsonRedisSerializer<UserCacheDocument>
         |
         v
ObjectMapper: property names, dates, enums,
              modules, null policy, type handling
         |
         v
UTF-8 JSON bytes
         |
         v
Redis key -> value bytes
         |
         v
JSON bytes returned to reader
         |
         v
Reader's JSON deserializer / ObjectMapper
         |
         v
Java DTO / Python dict / JS object
~~~

Two components have distinct responsibilities:

**RedisSerializer** is the bridge between Java types and byte arrays. It is configured for key, value, hash key, or hash value on a **RedisTemplate**.

**ObjectMapper** determines how JSON is produced and parsed: property names, **java.time** modules, date formats, enums, nulls, unknown fields, custom serializers/deserializers, and polymorphic type handling.

The serializer selects where the mapper is used; the mapper does not automatically alter every Redis entry in the application.

### ObjectMapper Does Not Dictate the Redis Data Type

A **SET** command stores JSON inside the value of a Redis key of type **string**. Meanwhile, a Spring Data Redis entity using **@RedisHash** can be mapped to a **Redis hash** structure. Both may represent the same kind of Java object, yet **they do not share the same physical storage layout**.

For example:

~~~text
SET user-cache:v1:42 '{"userId":"42","displayName":"An"}'
~~~

is a Redis string holding JSON. When data lives in a Redis hash instead, calling **GET user-cache:v1:42** can return a **WRONGTYPE** error. Customizing `ObjectMapper` for a JSON value serializer does not cause a **@RedisHash** repository to start storing JSON strings.

## 3. Distinguishing JSON Serializer Choices in Spring Data Redis

| Component | Characteristics | When to Use |
|---|---|---|
| **StringRedisSerializer** | Encodes/decodes Strings, typically UTF-8; does not turn DTOs into JSON | Keys or values are already strings |
| **Jackson2JsonRedisSerializer<T>** | JSON bound to a fixed target Java type; accepts a custom ObjectMapper | A keyspace has a single clear DTO |
| **GenericJackson2JsonRedisSerializer** | Supports multi-type values; typically relies on type metadata to reconstruct objects | Multiple types are genuinely required and type handling is locked down |
| **JdkSerializationRedisSerializer** | Binary Java serialization format, no cross-language JSON contract | Only in systems accepting Java-specific format; avoid by default for shared data |

For keyspaces shared across services, a **typed JSON serializer** is usually easiest to control. Readers know the schema of **UserCacheDocument** upfront, and JSON does not need to depend on Java class/package names.

**GenericJackson2JsonRedisSerializer** is convenient when one template writes multiple object types, yet requires special care around type metadata, class name stability, package refactoring compatibility, and deserialization security. Never enable unrestricted default typing for data that external parties could modify.

Using a String key serializer does not mean the value serializer is also String. Both sides must match on the exact byte representation written, including the **key serializer**; if keys are written using JDK serialization and looked up with **redis-cli GET user-cache:v1:42**, the client may fail to locate the key because the actual bytes differ.

## 4. Start from the JSON Contract, Then Configure the Mapper

Suppose a group of services shares cached copies of user profiles. Define JSON contract version 1:

~~~json
{
  "schemaVersion": 1,
  "userId": "42",
  "displayName": "Nguyễn An",
  "updatedAt": "2026-11-12T10:20:00Z"
}
~~~

Accompanying conventions:

| Attribute | Convention | Meaning |
|---|---|---|
| Redis key | **user-cache:v1:{userId}** | Intentional keyspace and schema version |
| Redis type | **string** | One JSON document inside the value |
| Encoding | **UTF-8** | Clients agree on byte encoding |
| **schemaVersion** | Integer **1** | Marks payload format version |
| **userId** | String | Avoids confusing IDs with arithmetic numbers |
| **displayName** | String | Unicode text |
| **updatedAt** | ISO-8601 UTC, e.g., **2026-11-12T10:20:00Z** | Update timestamp |
| Field naming | **camelCase** | Identical names across all readers/writers |
| TTL | E.g., **15 minutes** | Cache entry expiry; not JSON version |
| Unknown fields | Convention that readers may ignore extra fields | Supports gradual rollout of optional fields |

Having both **schemaVersion** in the payload and **v1** in the key is not always mandatory together. The two versioning layers serve different purposes: key prefixes prevent misreading legacy keyspaces, while payload version fields help readers identify payload variants. Pick a clear strategy rather than adding version markers in two places out of habit.

The contract should also state how missing fields, **null** fields, unknown enum values, monetary/timestamp semantics, and shareable data rules are handled. Sharing the same **ObjectMapper** within Java reduces internal drift, yet **publishing the JSON convention is what lets other languages read the data**.

## 5. Creating an Explicit DTO for Redis Data

In Java, you can use a record:

~~~java
package com.example.redis.model;

import java.time.Instant;

public record UserCacheDocument(
    int schemaVersion,
    String userId,
    String displayName,
    Instant updatedAt
) {}
~~~

A record fits an immutable document well. When reading JSON, Jackson must know how to instantiate **UserCacheDocument**; modern Java and Jackson support records out of the box.

You do not have to reuse the exact same class for HTTP responses, database entities, and Redis caches. Tying all responsibilities to a single DTO risks accidentally mutating Redis payloads whenever public APIs or persistence entities change. For data consumed across services, a **dedicated Redis document** makes schema stability easier to enforce.

When designing the DTO, ask:

- Which values truly need to be stored, and which can be recomputed?
- Which fields might be absent when reading older versions?
- Are default values for new fields valid across all cases?
- Are there sensitive fields like passwords, access tokens, or secret keys that must stay out of shared documents?
- Would renaming a Java field accidentally change a JSON field name that consumers depend on?

## 6. Configuring a Dedicated ObjectMapper for RedisTemplate

Example using Spring Boot with **Spring Data Redis**, **Jackson**, and the Jackson module for **java.time**. Typical dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'com.fasterxml.jackson.core:jackson-databind'
    implementation 'com.fasterxml.jackson.datatype:jackson-datatype-jsr310'
}
~~~

When the application already uses a starter providing Jackson, you do not need duplicate explicit Jackson dependency declarations. Let Spring Boot dependency management govern library versions.

Create a template dedicated to **UserCacheDocument**:

~~~java
package com.example.redis.config;

import com.example.redis.model.UserCacheDocument;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import com.fasterxml.jackson.databind.json.JsonMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class UserRedisSerializationConfig {

    @Bean("userCacheRedisTemplate")
    public RedisTemplate<String, UserCacheDocument> userCacheRedisTemplate(
            RedisConnectionFactory connectionFactory) {

        ObjectMapper redisMapper = JsonMapper.builder()
            .addModule(new JavaTimeModule())
            .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
            .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
            .build();

        var jsonSerializer =
            new Jackson2JsonRedisSerializer<>(
                redisMapper,
                UserCacheDocument.class
            );

        var template = new RedisTemplate<String, UserCacheDocument>();
        template.setConnectionFactory(connectionFactory);
        template.setKeySerializer(new StringRedisSerializer());
        template.setValueSerializer(jsonSerializer);

        // Only needed when using hash operations; must explicitly match
        // the hash value data type managed by this template.
        template.setHashKeySerializer(new StringRedisSerializer());
        template.setHashValueSerializer(jsonSerializer);

        template.afterPropertiesSet();
        return template;
    }
}
~~~

This configuration illustrates clear boundaries:

1. **RedisConnectionFactory** handles connecting to Redis; it does not determine JSON shape.
2. **ObjectMapper** governs JSON formatting and DTO conversion rules.
3. **Jackson2JsonRedisSerializer<UserCacheDocument>** uses that mapper to produce and parse bytes.
4. **StringRedisSerializer** handles keys so they remain directly inspectable via Redis CLI.
5. **RedisTemplate** binds connection and serializers into a data-access API.

In this example, the **hash value serializer** is also set to **UserCacheDocument**, which only makes sense if the application genuinely stores such an object in each hash field. Do not assume every hash field of every key follows that structure. For applications using multiple Redis data types, use separate templates or adapters scoped to specific operations.

**API version note:** serializer constructors and Jackson configuration APIs vary across Spring Data Redis/Jackson lines. This example uses Spring Data Redis 3.x's constructor taking **ObjectMapper** and **Class<T>**. When upgrading major versions, match the target API; the JSON contract itself can remain stable even when serializer instantiation changes.

### Why Create ObjectMapper Inside the Redis Configuration?

A Spring Boot app typically has an **ObjectMapper** serving HTTP JSON. Mutating that shared mapper directly can unintentionally alter HTTP API outputs or other Jackson consumers. For example, disabling numeric timestamps for Redis could break an HTTP controller relying on that mapper.

A dedicated Redis mapper gives storage rules an independent lifecycle. If you want to reuse application modules or naming conventions, build the mapper from Spring Boot's configured **Jackson2ObjectMapperBuilder**, yet still construct a **separate instance** before applying Redis-specific customizations.

An `ObjectMapper` is safe to reuse across threads once fully configured. Never invoke **registerModule**, **setDateFormat**, **setPropertyNamingStrategy**, or default typing settings while the template is actively serving concurrent requests.

## 7. Example Writing and Reading with the Configured Template

~~~java
package com.example.redis.service;

import com.example.redis.model.UserCacheDocument;
import java.time.Duration;
import java.util.Optional;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class UserProfileCache {
    private final RedisTemplate<String, UserCacheDocument> redis;

    public UserProfileCache(
            @Qualifier("userCacheRedisTemplate")
            RedisTemplate<String, UserCacheDocument> redis) {
        this.redis = redis;
    }

    public void put(UserCacheDocument document) {
        redis.opsForValue().set(
            key(document.userId()),
            document,
            Duration.ofMinutes(15)
        );
    }

    public Optional<UserCacheDocument> find(String userId) {
        return Optional.ofNullable(
            redis.opsForValue().get(key(userId))
        );
    }

    public void evict(String userId) {
        redis.delete(key(userId));
    }

    private String key(String userId) {
        return "user-cache:v1:" + userId;
    }
}
~~~

Write example:

~~~java
var document = new UserCacheDocument(
    1,
    "42",
    "Nguyễn An",
    java.time.Instant.parse("2026-11-12T10:20:00Z")
);
userProfileCache.put(document);
~~~

With the configuration above, the Redis value is stored as JSON bytes equivalent to:

~~~json
{
  "schemaVersion": 1,
  "userId": "42",
  "displayName": "Nguyễn An",
  "updatedAt": "2026-11-12T10:20:00Z"
}
~~~

Field ordering and whitespace are not guarantees of a JSON contract unless a system specifically requires canonical output. What must remain consistent are **field names, value types, data semantics, timestamp formats, and character encoding**.

To inspect data directly:

~~~bash
redis-cli --raw GET user-cache:v1:42
redis-cli TTL user-cache:v1:42
~~~

**GET** lets you inspect the stored JSON; **TTL** reports remaining seconds before expiry, or whether the key is persistent or missing. Do not confuse TTL with connection timeouts or serializer settings.

## 8. ObjectMapper Customizations That Directly Affect the Contract

### 8.1. Dates, Times, Timezones, and Precision

Jackson requires **JavaTimeModule** to properly handle **java.time** types such as **Instant**, **LocalDate**, and **OffsetDateTime**.

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
    .build();
~~~

**WRITE_DATES_AS_TIMESTAMPS** is a serialization setting; if two parties configure it differently, one may write ISO-8601 strings while the other writes numeric values or other timestamp structures.

Agree explicitly on semantics:

- **Instant** represents an absolute instant in time, typically formatted as ISO-8601 with **Z** for UTC.
- **LocalDate** carries only a calendar date without timezone, e.g., **2026-11-12**.
- **LocalDateTime** contains no offset/timezone; never assume it defaults to UTC when crossing system boundaries.
- **Epoch milliseconds** differ from **epoch seconds** and from micro/nanosecond precision.

If using numeric timestamps, document the unit, precision, and large-integer handling explicitly. Never make readers guess "13 digits must mean milliseconds."

For multi-timezone systems, ISO-8601 with UTC or explicit offset is easier to interpret than ambiguous date strings. If the user's original timezone must be preserved, store it as a separate contract field rather than relying on the JVM default timezone.

### 8.2. Property Names: camelCase, snake_case, and @JsonProperty

Suppose the Java field is **userId**:

~~~json
{"userId":"42"}
~~~

With **PropertyNamingStrategies.SNAKE_CASE** enabled, JSON typically becomes:

~~~json
{"user_id":"42"}
~~~

A reader expecting **userId** will not recognize **user_id** without matching configuration or aliases.

You can set a mapper-wide rule:

~~~java
import com.fasterxml.jackson.databind.PropertyNamingStrategies;

mapper.setPropertyNamingStrategy(
    PropertyNamingStrategies.SNAKE_CASE
);
~~~

This must be set **before the mapper begins serving traffic**. If only a few fields need fixed external names, annotate them with **@JsonProperty** on the DTO:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;

public record UserIdWire(
    @JsonProperty("user_id") String userId
) {}
~~~

Refactoring Java field names should never silently alter Redis field names that consumers rely on. For shared data, treat JSON property names as an API contract.

### 8.3. Unknown Properties and Forward Compatibility

Suppose a new writer adds a field:

~~~json
{
  "schemaVersion": 1,
  "userId": "42",
  "displayName": "Nguyễn An",
  "updatedAt": "2026-11-12T10:20:00Z",
  "avatarUrl": "https://example.org/avatar/42"
}
~~~

An older reader only has the original four fields. With:

~~~java
mapper.disable(
    DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES
);
~~~

the reader ignores **avatarUrl** during deserialization. This allows adding optional fields while two service versions run concurrently.

However, ignoring unknown fields **does not guarantee full compatibility**. If an existing field is removed, changes type, or changes meaning, old readers may read wrong values or miss data. For business-critical data, add post-deserialization validation and clear schema policies.

### 8.4. Nulls, Missing Fields, and Default Values

Three cases must be distinguished:

~~~json
{"displayName": "An"}
~~~

~~~json
{"displayName": null}
~~~

~~~json
{}
~~~

An **absent field**, a **field with value null**, and a **field holding an empty string** can carry different meanings. Enabling:

~~~java
import com.fasterxml.jackson.annotation.JsonInclude;

mapper.setSerializationInclusion(
    JsonInclude.Include.NON_NULL
);
~~~

omits Java properties with **null** values from written JSON. That is a contract change: consumers can no longer tell "writer explicitly set null" apart from "writer does not know this field" from the payload alone.

For critical fields, require presence and validate after reading. Never assume an absent primitive **int schemaVersion** on a Java record equals a valid version; primitive defaults can mask schema errors unless explicitly checked.

### 8.5. Enums and Changing Values

Example:

~~~java
public enum AccountStatus {
    ACTIVE, SUSPENDED
}
~~~

JSON might contain:

~~~json
{"status":"ACTIVE"}
~~~

Adding **PENDING** in a new writer can break deserialization in old readers. Renaming **SUSPENDED** to **DISABLED** also breaks the wire contract without an explicit mapping layer.

Define an enum strategy:

- Use stable string codes decoupled from display names.
- When adding new statuses, determine how older consumers will behave.
- If fallback behavior is needed, implement it deliberately with logging/metrics to surface unknown values.
- Never let an unrecognized enum silently fall back to a higher-privilege or less-restrictive state.

### 8.6. Decimals and Large Integers

JSON only defines syntax for numbers; it does not guarantee identical precision across languages. Java **BigDecimal** and JavaScript **Number** behave differently; large 64-bit integers exceed JavaScript `Number`'s safe integer range.

For prices, exchange rates, or large IDs, standardize representation upfront. Example:

~~~json
{
  "priceMinorUnits": "199900",
  "currency": "VND"
}
~~~

This illustrative design encodes integer minor units as strings, protecting consumers from default numeric precision loss. You can also use decimal strings with an agreed convention, such as **"1999.00"**. What matters is that every participant agrees on **units, scale, rounding rules, and data types**.

## 9. Consistency Across RedisTemplate, HTTP, and Spring Cache

A single project may simultaneously contain:

~~~text
HTTP ObjectMapper
       |
  JSON API response

RedisTemplate<String, UserCacheDocument>
       |
  Jackson2JsonRedisSerializer
       |
  user-cache:v1:*

RedisCacheManager
       |
  RedisCacheConfiguration
       |
  cache namespace

Spring Data Redis Repository
       |
  RedisMappingContext / @RedisHash
       |
  Redis hash + index metadata
~~~

They do not automatically share the same serializer or data layout.

### 9.1. RedisTemplate Does Not Control Spring Cache

If code uses **@Cacheable**, cached entries flow through **RedisCacheManager** and **RedisCacheConfiguration**. Calling **RedisTemplate.setValueSerializer(...)** does not automatically change the serializer used by the cache manager.

To apply a dedicated JSON serializer to caches, configure it on the cache manager:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.serializer.RedisSerializationContext;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import java.time.Duration;

@Configuration
public class UserCacheManagerConfig {

    @Bean("userCacheManager")
    public RedisCacheManager userCacheManager(
            RedisConnectionFactory connectionFactory) {

        var serializer = new Jackson2JsonRedisSerializer<>(
            UserCacheDocument.class
        );

        RedisCacheConfiguration configuration =
            RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(Duration.ofMinutes(15))
                .serializeValuesWith(
                    RedisSerializationContext
                        .SerializationPair
                        .fromSerializer(serializer)
                );

        return RedisCacheManager.builder(connectionFactory)
            .cacheDefaults(configuration)
            .build();
    }
}
~~~

This example illustrates **where to attach the cache serializer**, without using the customized mapper from section 6. To guarantee identical formatting, replace **serializer** with an instance built using that **ObjectMapper** and schema. Furthermore, a cache manager serving multiple methods with distinct return types usually **cannot** safely apply a single fixed **UserCacheDocument** serializer across all cache names. Configure cache managers/configs per cache type or adopt an appropriate serialization contract.

When using **@Cacheable**, also distinguish key prefixes and key encodings generated by the cache abstraction; do not assume keys produced by the cache manager match keys built by **UserProfileCache.key(...)**.

### 9.2. @RedisHash Does Not Become JSON Just Because ObjectMapper Exists

**@RedisHash** uses Redis's own mapping mechanism to store objects as Redis hashes and optionally maintain secondary indexes. To produce JSON string values under a cross-language contract, use a dedicated template/adapter for that data.

Never let a template issue **SET** with a JSON string onto a key that a Redis repository treats as a Redis hash. Each Redis key holds one data type at a time; overwriting the type corrupts data or causes subsequent commands to fail with **WRONGTYPE**.

### 9.3. Should the HTTP Mapper Match the Redis Mapper?

Not necessarily. Parties must match **the specific contract they share**. A public HTTP API might use snake_case and different formats, while an internal cache uses camelCase. To reuse conventions safely, share explicit modules/conventions or convert through dedicated DTOs.

Avoid modifying the application-wide **ObjectMapper** just to fix a Redis issue. Enabling default typing, altering date formats, or disabling fail-on-unknown on the global mapper can impact HTTP, Kafka, and other JSON serializers across the app.

## 10. Keeping Services Independent While Understanding Shared Data

Consider two services:

~~~text
User Service (Java/Spring)
       |
       | write user-cache:v1:42
       v
  Redis JSON value
       ^
       | read user-cache:v1:42
       |
Notification Service (Node.js)
~~~

User Service can write via:

~~~java
redisTemplate.opsForValue().set(
    "user-cache:v1:42",
    new UserCacheDocument(
        1,
        "42",
        "Nguyễn An",
        Instant.parse("2026-11-12T10:20:00Z")
    ),
    Duration.ofMinutes(15)
);
~~~

Notification Service needs no Java classes. It only needs the Redis key, UTF-8, JSON schema, and timestamp rules. Illustrative JavaScript parsing logic once received:

~~~javascript
const raw = '{"schemaVersion":1,"userId":"42",'
  + '"displayName":"Nguyễn An",'
  + '"updatedAt":"2026-11-12T10:20:00Z"}';

const user = JSON.parse(raw);

if (user.schemaVersion !== 1 || typeof user.userId !== "string") {
  throw new Error("Unsupported user-cache payload");
}

const updatedAt = new Date(user.updatedAt);
if (Number.isNaN(updatedAt.getTime())) {
  throw new Error("Invalid updatedAt");
}
~~~

This covers the JSON contract check, omitting Node.js Redis client wiring. A production consumer should also validate all required fields, enforce payload size limits, and handle unsupported schema versions explicitly.

Even if each service builds its own mapper differently, data remains compatible as long as both honor the contract. **Compatibility is proven by actual bytes and schemas, not merely because two services both use Jackson.**

### Should You Share a Java DTO Library?

When all services are Java, a shared contract module can reduce field-naming drift. Still, a shared library introduces version coupling and does not solve rolling deployments on its own: older instances can still read payloads written by newer ones.

In polyglot architectures, maintain language-agnostic schema docs—such as JSON Schema or OpenAPI schemas for payloads—paired with sample payloads and compatibility tests. Define clearly who owns the contract, when schemas may change, and how consumers are notified.

## 11. Polymorphic JSON and the Risks of Java Type Information

A payload may contain type metadata when a generic serializer includes type information, for example:

~~~json
{
  "@class": "com.example.user.internal.UserRecord",
  "userId": "42",
  "displayName": "Nguyễn An"
}
~~~

The **@class** property ties JSON to a Java package/class. Refactoring **com.example.user.internal.UserRecord** into another package can prevent older clients from reconstructing the object. Python/Node.js clients likewise have no use for Java class names to interpret business schemas.

### Why Avoid Careless Default Typing?

Jackson supports polymorphic deserialization. Letting an untrusted payload dictate arbitrary Java classes to instantiate creates an expanded attack surface under unsafe deserialization settings, especially when the classpath includes types unsuitable for external instantiation.

Guidelines:

1. For keyspaces with fixed DTOs, prefer **typed serializers** and keep Java class names out of payloads.
2. Use polymorphic deserialization only when the domain genuinely requires multiple subtypes.
3. When needed, permit only approved subtypes using strict type constraints such as an appropriate **PolymorphicTypeValidator**; never enable unrestricted default typing.
4. Use stable domain type codes like **type: "EMAIL"** instead of turning Java class names into a public contract when supporting multiple event types.
5. Enforce Redis ACLs, network isolation, and keyspace write permissions to limit who can modify payloads.

Example of a Java-independent contract:

~~~json
{
  "schemaVersion": 1,
  "type": "EMAIL",
  "payload": {
    "recipientId": "42",
    "templateCode": "WELCOME"
  }
}
~~~

Consumers inspect **type** to pick an approved DTO, rather than reading an arbitrary class name from JSON to instantiate.

## 12. Upgrading Schemas While Multiple Versions Run Concurrently

A common failure: V2 deploys first and starts writing data V1 cannot parse. During rolling deployments, V1 and V2 instances access Redis at the same time.

### 12.1. Adding an Optional Field

V1:

~~~json
{
  "schemaVersion": 1,
  "userId": "42",
  "displayName": "Nguyễn An",
  "updatedAt": "2026-11-12T10:20:00Z"
}
~~~

V2 adds **avatarUrl**:

~~~json
{
  "schemaVersion": 1,
  "userId": "42",
  "displayName": "Nguyễn An",
  "updatedAt": "2026-11-12T10:20:00Z",
  "avatarUrl": "https://example.org/avatar/42"
}
~~~

Keeping **schemaVersion = 1** can be acceptable when this is a **compatible addition within the V1 contract** and old readers are designed to ignore unknown fields. Verify that old readers actually tolerate new fields rather than assuming intent equals behavior.

### 12.2. Changing Field Types or Meaning

Changing **updatedAt** from an ISO string to epoch milliseconds breaks readers expecting strings:

~~~json
{
  "schemaVersion": 2,
  "userId": "42",
  "displayName": "Nguyễn An",
  "updatedAtEpochMillis": 1794478800000
}
~~~

In this situation, you should:

- Create a new keyspace **user-cache:v2:{userId}**, or
- Deploy readers supporting both V1 and V2 with explicit branching, or
- Coordinate data migration and rolling deployment so new readers are deployed everywhere before writers switch formats.

Never mix V1 and V2 formats under the same key and hope every service version guesses correctly.

### 12.3. Controlled Change Workflow

A reliable workflow typically follows:

1. **Define the new schema** and rules for reading old data.
2. **Deploy compatible readers** (able to read V1 and V2 if needed) before any writer emits only V2.
3. **Roll out new writers** targeting the designated keyspace/version.
4. **Transition data** via cache miss repopulation or controlled migration, depending on Redis's role.
5. **Monitor deserialization errors** and remaining V1 read volume.
6. **Remove legacy read paths** only after the support window, TTL, or migration completes.

When Redis is strictly a regenerable cache, switching to a versioned key prefix and letting old keys expire by TTL is often simpler than migration. When Redis holds non-regenerable business data, plan data conversion, loss prevention, and rollbacks rigorously.

### 12.4. Dual-Read, Single-Write

For example, the new service prefers V2 and temporarily falls back to V1 when absent:

~~~text
READ user-cache:v2:42
   |
   +-- found -> deserialize V2
   |
   +-- absent -> READ user-cache:v1:42
                   |
                   +-- found -> deserialize V1, map to V2
                   |
                   +-- absent -> cache miss / load origin

WRITE -> user-cache:v2:42
~~~

This is the **dual-read, single-write** pattern. Avoid letting a V1 consumer keep running after the V2 writer stops updating V1 while that consumer still relies on fresh data. Exact rollout sequencing depends on deployment order and synchronization contracts across parties.

## 13. How to Share Configuration to Prevent Drift?

Two services can both use JSON yet diverge due to differing dependencies or teams. **Configuration drift** occurs when a minor change on one side is not reflected on the other.

Examples:

| Potential Drift Point | Service A | Service B | Consequence |
|---|---|---|---|
| Date format | ISO-8601 UTC | Epoch milliseconds | Wrong deserialization or failure |
| Property naming | camelCase | snake_case | Missing/unmapped fields |
| Enum | String | Ordinal | Mismatched data meaning |
| Unknown properties | Ignored | Throw error | Incompatible deployments |
| Type metadata | None | Requires **@class** | Reader cannot reconstruct object |
| Redis type | JSON String | Redis hash | **WRONGTYPE** |
| TTL | 15 minutes | 24 hours | Data stays stale longer than designed |

Prevent drift using these practices:

**Versioned contract:** document schema, key prefix, encoding, data type, TTL, and compatibility rules in one clear location.

**Shared configuration module:** when Java services share dependencies and release lifecycles, a small module can construct mappers/serializers per contract. Still test backward compatibility whenever upgrading that module.

**Golden payloads:** store canonical sample JSON and byte fixtures; all consumers test reading the samples, and all writers test producing compliant payloads. Unless field order is strictly required, compare parsed JSON trees rather than raw strings.

**Consumer-driven compatibility tests:** whenever a writer adds or alters fields, verify all supported consumers still read cleanly.

**Schema validation:** validate external payloads against explicit versions/contracts rather than treating "Jackson didn't throw" as sufficient.

**Error observability:** track deserialization failures, unknown schema versions, unusual cache misses, wrong TTLs, and invalid values.

The goal is not forcing every service to carry an identical **ObjectMapperConfig.java** file. The goal is producing and reading **the exact same data with the exact same meaning**, even across different programming languages.

## 14. Common Error Examples and How to Reason About Them

### 14.1. Error Reading Instant

**Symptom:** JSON contains **"updatedAt": "2026-11-12T10:20:00Z"**, yet the reader fails on **java.time.Instant**.

**Possible cause:** the Redis serializer's mapper lacks **JavaTimeModule**, or the reader uses a different serializer than the writer.

**Approach:** inspect the actual bytes in Redis, the injected template, its value serializer, and modules on that exact `ObjectMapper`. Register **JavaTimeModule** on the serializer's mapper; never assume configuring the HTTP mapper also configured Redis serialization.

### 14.2. One Service Reads Empty Objects or Null Fields

**Symptom:** Redis JSON contains **user_id**, yet the Java DTO expects **userId**.

**Possible cause:** writer and reader use different naming strategies, or a field was renamed without maintaining an alias.

**Approach:** confirm canonical field names in the contract, then use **@JsonProperty/@JsonAlias** or consistent naming config to read legacy data. Never set **FAIL_ON_UNKNOWN_PROPERTIES = false** and assume the bug is fixed: the reader will skip **user_id** while still leaving **userId** null.

### 14.3. ClassNotFoundException or Type ID Error

**Symptom:** payload contains **@class** with an old package; after refactoring code, deserialization fails.

**Possible cause:** a generic serializer embedded Java class names as part of the data format.

**Approach:** evaluate moving to fixed DTOs or domain type discriminators; to handle existing data, build a controlled reader/migration. Never enable automatic instantiation of arbitrary classes just "to make reads succeed."

### 14.4. WRONGTYPE After Changing Access Mechanism

**Symptom:** a repository uses **@RedisHash**, while another service reads the same key via **opsForValue().get()**.

**Cause:** the two sides disagree on Redis data type. One expects a Redis hash; the other expects a Redis string.

**Approach:** standardize key owner, prefix, and data type. Use the matching API or migrate to another keyspace; `ObjectMapper` cannot fix Redis data type mismatches.

### 14.5. Cache Reads Succeed Yet Hold Stale Values

**Symptom:** service A writes with a 15-minute TTL; service B writes back to the same key via `SET` without a TTL or with a longer TTL.

**Cause:** a data contract covers not just JSON, but also key lifecycle.

**Approach:** define key ownership and TTL rules; use operations that apply the required TTL together. A **SET** command can modify or strip existing TTL depending on options, so never assume TTL is preserved automatically.

### 14.6. Adding a New Field Breaks Older Versions

**Symptom:** some pods running the older version cannot parse payloads written by the new version.

**Cause:** incompatible contract change or old readers having fail-on-unknown enabled.

**Approach:** check which versions are live; if only optional fields are added, configure readers to ignore unknown properties where appropriate. For breaking structural changes, use versioned keys/schemas and roll out readers before writers.

## 15. Verifying the Contract with Tests

### 15.1. Serializer Round-Trip Test

A focused unit test checks **serialize → deserialize** at the serializer layer without needing a Redis server:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import com.fasterxml.jackson.databind.json.JsonMapper;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;

class UserCacheSerializationTest {

    @Test
    void shouldRoundTripUserDocument() {
        var mapper = JsonMapper.builder()
            .addModule(new JavaTimeModule())
            .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
            .build();

        var serializer = new Jackson2JsonRedisSerializer<>(
            mapper,
            UserCacheDocument.class
        );

        var before = new UserCacheDocument(
            1,
            "42",
            "Nguyễn An",
            Instant.parse("2026-11-12T10:20:00Z")
        );

        byte[] bytes = serializer.serialize(before);
        assertNotNull(bytes);

        UserCacheDocument after = serializer.deserialize(bytes);
        assertEquals(before, after);
    }
}
~~~

This test proves **a single serializer** can read back its own output. It **does not prove** that Node.js, an older serializer, or another Jackson configuration can read it.

### 15.2. Golden JSON Test

Add a fixed sample payload:

~~~json
{
  "schemaVersion": 1,
  "userId": "42",
  "displayName": "Nguyễn An",
  "updatedAt": "2026-11-12T10:20:00Z"
}
~~~

Readers must deserialize this payload with the right semantics; writers must emit JSON with the same structure. Field order and whitespace need not be fixed.

Example verifying JSON shape using **JsonNode**:

~~~java
byte[] bytes = serializer.serialize(document);
JsonNode tree = mapper.readTree(bytes);

assertEquals(1, tree.path("schemaVersion").asInt());
assertEquals("42", tree.path("userId").asText());
assertEquals("2026-11-12T10:20:00Z",
    tree.path("updatedAt").asText());
~~~

This illustrative snippet assumes **serializer**, **document**, **mapper**, and Jackson/JUnit imports are already defined from the preceding test. Verifying JSON structure catches regressions where a mapper suddenly switches to snake_case or writes numeric timestamps.

### 15.3. Cross-Version Compatibility Tests

When V2 adds fields:

1. Read V1 payloads using the V2 reader.
2. Read V2 payloads using the V1 reader if the contract requires backward compatibility.
3. Verify required fields are never dropped or misinterpreted.
4. Test enums and large numbers/decimals with boundary values.
5. Test Unicode strings and `Instant` values written with non-UTC offsets representing the same instant.
6. Verify Redis data types, key serializers, and TTLs against a real Redis instance.

If a change is intentionally breaking, tests should confirm that older versions reject it **predictably** rather than failing sporadically or writing corrupted state.

### 15.4. Integration Tests Against Redis

A test using real Redis or a Redis test instance should verify:

- Keys have the byte format other clients expect to look up.
- Values are UTF-8 JSON conforming to the schema.
- **GET** reads a Redis string without `WRONGTYPE`.
- TTL is applied properly on write.
- Another service can actually deserialize the data.
- Missing keys trigger appropriate cache-miss handling.

Mocking **RedisTemplate** cannot verify serializers, Redis data types, or real TTL behavior. Meanwhile, pure Java JSON tests require no Redis server and run quickly on every commit.

## 16. Process for Rolling Out a Shared JSON Keyspace

Suppose a system is about to share **user-cache:v1** across three services.

**Step 1 — Lock down owner and data role.** Define which service may write, which may only read, whether Redis is regenerable cache or primary storage, and when entries must expire.

**Step 2 — Lock down the wire contract.** Document key pattern, Redis data type, UTF-8, JSON field names, field types, time format, null policy, enum policy, TTL, and schema version.

**Step 3 — Choose typed serializers.** Each explicit DTO keyspace should use a matching typed serializer; where polymorphism is needed, define permitted subtypes and type discriminators.

**Step 4 — Build ObjectMapper in configuration.** Register `JavaTimeModule`, set naming/date/unknown-field policies before use, and isolate from the HTTP `ObjectMapper`.

**Step 5 — Test writers and readers against shared sample data.** Verify golden payloads for both old and new versions. For polyglot setups, let each consumer verify contract compliance independently.

**Step 6 — Monitor errors in production.** Track deserialization failures, unknown schema versions, abnormal TTLs, and cache misses. Avoid logging raw payloads containing personal/sensitive data.

**Step 7 — Upgrade with a rollout plan.** Compatible changes can add optional fields; breaking changes should version keys/schemas and follow a phased rollout/migration plan.

When maintaining multiple templates/cache managers, document clearly which template governs which keyspace. Other teams can then assess impact before pointing another serializer or cache name at the same keys.

## 17. Reasoning Exercises

**Scenario A.** A Spring Boot REST API returns **updatedAt** as an ISO string, yet Redis stores a numeric timestamp. Why?

**Explanation:** HTTP JSON and `RedisTemplate` may use two different `ObjectMapper`/serializer instances. Inspect the **ObjectMapper inside the Redis value serializer**, its registered modules, and **WRITE_DATES_AS_TIMESTAMPS**; do not infer Redis behavior from HTTP responses.

**Scenario B.** A service refactors package **com.example.v1.User** to **com.example.v2.User**. Old Redis entries contain **@class** referencing the V1 package and fail to deserialize. What is the long-term fix?

**Explanation:** Avoid coupling shared JSON to Java class names by using typed DTOs and stable schemas or domain type codes. Design a migration for legacy payloads; never open default typing carelessly to suppress errors.

**Scenario C.** A new writer adds **avatarUrl**, and old readers throw unknown-property errors. Must you create a V2 keyspace?

**Explanation:** If only optional fields are added and old readers are allowed to ignore unknown fields, you can stay on V1 after verifying compatibility. If old readers must stay strict or semantics changed, use a versioning/deployment strategy instead.

**Scenario D.** Two services both use Jackson **ObjectMapper**, yet one cannot read **user_id** written by the other. Is "using the same library" enough?

**Explanation:** No. Naming strategies, annotations, and DTO schemas can still differ. Standardize field names in the contract and validate with golden payloads.

**Scenario E.** You customized **RedisTemplate** for JSON and annotated a method with **@Cacheable**, yet cached values cannot be read back through the template. Why?

**Explanation:** Spring Cache uses **RedisCacheManager/RedisCacheConfiguration** and does not automatically inherit serializers from a custom `RedisTemplate`. Check the active cache manager, key prefix, serializer, and cached data types.

**Scenario F.** A client times out while writing JSON via **SET**. Can you be sure the JSON is not in Redis?

**Explanation:** No. The server may have executed the command while the response was lost before reaching the client. When retrying or updating TTLs, consider idempotency, write ordering, and defenses against stale writes overwriting newer data. Correct `ObjectMapper` setup does not replace distributed error handling.

## 18. Key Takeaways

**ObjectMapper sits at the core of JSON serialization, yet cross-party consistency is defined by the actual data contract.** Safe multi-party Redis reads and writes require agreement on keys, Redis data types, UTF-8, JSON schemas, dates/times, enums, nulls, field naming, TTLs, and versioning.

In Spring Data Redis, keep mapper/serializer configuration in the infrastructure layer, attach the right serializers to the **RedisTemplate** or **RedisCacheManager** each feature actually uses, and avoid accidentally altering the shared HTTP `ObjectMapper`. For shared data, prefer stable DTOs and JSON contracts free of unnecessary Java class-name coupling. When schemas change, rely on sample payloads, compatibility tests, and phased writer/reader rollouts to prevent failures while multiple versions run side by side.
