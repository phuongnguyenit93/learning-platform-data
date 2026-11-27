# Excluding Non-Persistent Properties with `@Transient`

When using **Spring Data Redis Repositories**, a Java object can be mapped to a **Redis Hash**: the entity's properties become data written to Redis and restored when read back. However, not all information carried by an object should be persisted. Some properties exist solely for presentation, temporary calculations, request tracing, or intermediate results.

In such cases, use **Spring Data's `@Transient`** to instruct the mapping mechanism to skip the property. This is a decision about the **stored data model**, not merely hiding a field when serializing HTTP JSON responses.

## 1. What Problem Does `@Transient` Solve?

Suppose an application manages customer profiles in Redis:

- **`id`**: identifier to retrieve the profile.
- **`fullName`** and **`loyaltyPoints`**: business data that must be persisted.
- **`requestTraceId`**: tracing code meaningful only during the current request.
- **`displayBadge`**: display label computed specifically for the UI.

If all five properties are saved, Redis stores unnecessary transient data. That bloats stored data, creates the risk of reading stale values back, and blurs the boundary between business state and presentation state.

Mark transient properties with:

~~~java
import org.springframework.data.annotation.Transient;

@Transient
private String requestTraceId;
~~~

Spring Data recognizes this property as a **non-persistent property** in the mapping model. When the entity is written via Spring Data Redis Repository, its value is not placed into the Redis Hash. When the entity is reconstructed from Redis, the framework does not read that value from Redis either.

> Be sure to import `org.springframework.data.annotation.Transient`. In this lesson, all examples refer to entity mapping with Spring Data Redis, specifically the `@RedisHash` and Redis Repository model.

## 2. Entity Example: Saving Business Data, Skipping Transient Data

Define a `CustomerProfile` entity:

~~~java
package com.example.redis.profile;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;
import org.springframework.data.redis.core.RedisHash;

@RedisHash("customer-profile")
public class CustomerProfile {

    @Id
    private String id;

    private String fullName;

    private int loyaltyPoints;

    @Transient
    private String requestTraceId;

    @Transient
    private String displayBadge;

    public CustomerProfile() {
        // Allows the framework to instantiate the entity when reading data.
    }

    public CustomerProfile(String id, String fullName, int loyaltyPoints) {
        this.id = id;
        this.fullName = fullName;
        this.loyaltyPoints = loyaltyPoints;
    }

    public String getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public void setFullName(String fullName) {
        this.fullName = fullName;
    }

    public int getLoyaltyPoints() {
        return loyaltyPoints;
    }

    public void setLoyaltyPoints(int loyaltyPoints) {
        this.loyaltyPoints = loyaltyPoints;
    }

    public String getRequestTraceId() {
        return requestTraceId;
    }

    public void setRequestTraceId(String requestTraceId) {
        this.requestTraceId = requestTraceId;
    }

    public String getDisplayBadge() {
        return displayBadge;
    }

    public void setDisplayBadge(String displayBadge) {
        this.displayBadge = displayBadge;
    }
}
~~~

Define the repository:

~~~java
package com.example.redis.profile;

import org.springframework.data.repository.CrudRepository;

public interface CustomerProfileRepository
        extends CrudRepository<CustomerProfile, String> {
}
~~~

In a Spring Boot application with Spring Data Redis and Redis Repositories enabled, `save` maps the entity to Redis data, and `findById` reconstructs the object from stored data.

Usage example:

~~~java
CustomerProfile profile =
    new CustomerProfile("customer-42", "Nguyen Lan", 120);

profile.setRequestTraceId("req-8f22");
profile.setDisplayBadge("Loyal Customer");

repository.save(profile);

CustomerProfile loaded = repository.findById("customer-42")
    .orElseThrow();

System.out.println(loaded.getFullName());       // Nguyen Lan
System.out.println(loaded.getLoyaltyPoints());  // 120
System.out.println(loaded.getRequestTraceId()); // null
System.out.println(loaded.getDisplayBadge());   // null
~~~

The two `@Transient` properties still exist as normal fields **on the in-memory Java object**. For instance, immediately before or after calling `save(profile)`, `profile.getRequestTraceId()` still returns `"req-8f22"`. The annotation does not clear values from the object itself.

The difference only appears when creating **a new instance from Redis data**: non-persisted properties receive Java default values (`null` for `String`, `false` for `boolean`, `0` for primitive numeric types), unless the constructor, field initializers, or application logic sets them.

## 3. What Does the Redis Hash Contain?

With `@RedisHash("customer-profile")` and ID `customer-42`, Spring Data Redis typically stores the entity under a key like:

~~~text
customer-profile:customer-42
~~~

Conceptually, the data looks like:

| Property | Saved in Redis Hash? | Reason |
| --- | --- | --- |
| `id` | Participates in entity identity | Annotated with `@Id` |
| `fullName` | Yes | Normal persistent property |
| `loyaltyPoints` | Yes | Normal persistent property |
| `requestTraceId` | No | Annotated with `@Transient` |
| `displayBadge` | No | Annotated with `@Transient` |

A Hash may also contain Spring Data type information, such as `_class`, depending on mapper configuration. Therefore, do not write tests asserting the Hash has strictly two data fields total. What should be asserted is that business fields hold the expected values and skipped fields **do not appear**.

Data flow diagram:

~~~text
        CustomerProfile in Java
     ┌──────────────────────────────┐
     │ id = "customer-42"           │
     │ fullName = "Nguyen Lan"      │
     │ loyaltyPoints = 120          │
     │ requestTraceId = "req-8f22"  │
     │ displayBadge = "Loyal"       │
     └──────────────┬───────────────┘
                    │ repository.save(...)
                    ▼
          Spring Data Redis Mapper
             │              │
             │              └── @Transient → skipped
             ▼
       Redis Hash (persisted data)
     ┌──────────────────────────────┐
     │ fullName = "Nguyen Lan"      │
     │ loyaltyPoints = 120          │
     │ [mapping metadata if any]    │
     └──────────────┬───────────────┘
                    │ repository.findById(...)
                    ▼
         New CustomerProfile in Java
     ┌──────────────────────────────┐
     │ fullName = "Nguyen Lan"      │
     │ loyaltyPoints = 120          │
     │ requestTraceId = null        │
     │ displayBadge = null          │
     └──────────────────────────────┘
~~~

Do not deduce the exact Hash layout solely from the Java class name. Key prefixes, serializers, nested types, and metadata can depend on configuration. In the simple example above, the check we care about is that `requestTraceId` and `displayBadge` are not written to Redis by the mapper.

## 4. Verifying with Integration Tests

The surest way to verify a property is excluded is to **save an entity with non-null values**, read it back via the repository, and inspect the Hash in Redis. If you only set `null` before saving, the absence of that field in Redis does not prove `@Transient` is working.

With Gradle Groovy and Spring Boot managing dependency versions, a minimal test configuration could be:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
}
~~~

The following example is placed in a Spring Boot project that has scanned and created `CustomerProfileRepository`. Redis is started via Testcontainers to avoid touching a shared Redis instance:

~~~java
package com.example.redis.profile;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@Testcontainers
class CustomerProfileRepositoryTest {

    @Container
    static final GenericContainer<?> REDIS =
        new GenericContainer<>(DockerImageName.parse("redis:7.2-alpine"))
            .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisConnection(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add("spring.data.redis.port",
            () -> REDIS.getMappedPort(6379));
    }

    @Autowired
    CustomerProfileRepository repository;

    @Autowired
    StringRedisTemplate redis;

    @Test
    void transientPropertiesAreNotSavedToRedisHash() {
        String id = "customer-" + UUID.randomUUID();
        String redisKey = "customer-profile:" + id;

        try {
            CustomerProfile profile =
                new CustomerProfile(id, "Nguyen Lan", 120);
            profile.setRequestTraceId("req-test-123");
            profile.setDisplayBadge("VIP");

            repository.save(profile);

            // Business data is saved.
            assertThat(redis.opsForHash().get(redisKey, "fullName"))
                .isEqualTo("Nguyen Lan");
            assertThat(redis.opsForHash().get(redisKey, "loyaltyPoints"))
                .isEqualTo("120");

            // Transient data does not appear in the Redis Hash.
            assertThat(redis.opsForHash().hasKey(redisKey, "requestTraceId"))
                .isFalse();
            assertThat(redis.opsForHash().hasKey(redisKey, "displayBadge"))
                .isFalse();

            // Subsequent read builds the entity from persisted state.
            CustomerProfile loaded = repository.findById(id)
                .orElseThrow();

            assertThat(loaded.getFullName()).isEqualTo("Nguyen Lan");
            assertThat(loaded.getLoyaltyPoints()).isEqualTo(120);
            assertThat(loaded.getRequestTraceId()).isNull();
            assertThat(loaded.getDisplayBadge()).isNull();
        } finally {
            repository.deleteById(id);
        }
    }
}
~~~

In the example, the Redis key uses the keyspace from `@RedisHash("customer-profile")`. When an application customizes the keyspace, alters keys via a custom converter, or changes the identifier strategy, adjust how keys are determined in tests accordingly. To run Testcontainers, the test machine needs Docker or a compatible container runtime.

If you want to inspect manually with Redis CLI after running the save snippet:

~~~redis
HGETALL customer-profile:customer-42
HGET customer-profile:customer-42 requestTraceId
HGET customer-profile:customer-42 displayBadge
~~~

Both `HGET` commands for `@Transient`-marked fields will find no values in the Hash just written by the mapper. Avoid confusing a `nil` result with a field whose Java value happened to be `null`: only testing with non-null initial values and reading back clearly demonstrates the expected behavior.

## 5. Distinguishing `@Transient` from Other Mechanisms

Several mechanisms look similar but affect different pipelines.

| Mechanism | Primary Scope | Usage Example |
| --- | --- | --- |
| `org.springframework.data.annotation.Transient` | Spring Data persistent property mapping, including Redis Repository | Do not store `requestTraceId` in the Redis Hash |
| Java `transient` keyword | Java Object Serialization and reflection/mapping mechanisms inspecting modifiers | Field excluded from default Java serialization |
| `com.fasterxml.jackson.annotation.JsonIgnore` | Jackson JSON serialization/deserialization | Hide field from JSON API when using Jackson |
| `jakarta.persistence.Transient` | JPA/Hibernate mapping | Do not map field as a column in a relational database |
| Assigning property to `null` | Value of the object at a given moment | Not synonymous with removing the property from the mapping model |

### 5.1. `@Transient` Is Not Synonymous with `@JsonIgnore`

Consider the property:

~~~java
@Transient
private String requestTraceId;
~~~

Spring Data Redis Repository skips the field when mapping to the Redis Hash. However, if the Java object still holds `requestTraceId` and is returned by a REST Controller, Jackson **can still output that field to JSON** via its getter. To change the JSON API, use an appropriate DTO or Jackson configuration like `@JsonIgnore`.

Conversely:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnore;

@JsonIgnore
private String internalNote;
~~~

Jackson's annotation does not make `internalNote` transient in Spring Data Redis Repository. Do not use a JSON annotation to replace storage rules.

If a field must be excluded at both layers, you can apply both annotations or separate the entity and API DTO:

~~~java
@Transient
@JsonIgnore
private String requestTraceId;
~~~

Only use this combination when both requirements genuinely exist. For larger APIs, **dedicated DTOs** usually make it clearer which fields are allowed in responses.

### 5.2. `@Transient` in Repositories Differs from `RedisTemplate` Saving Arbitrary Values

Spring Data Redis offers multiple ways to work with data:

~~~java
repository.save(profile);                  // Entity -> Redis Hash mapping
redisTemplate.opsForValue().set(key, obj); // Serializer configured for value
~~~

The first uses Spring Data Redis's entity mapping infrastructure, where `@Transient` applies. The second uses `RedisTemplate`'s serializer: this could be JDK serialization, Jackson JSON, or a custom serializer. **Do not assume any arbitrary serializer honors `@Transient`.**

Similarly, a Redis cache managed by Spring Cache (`@Cacheable` + `RedisCacheManager`) usually writes values through the cache's serializer. To exclude properties from cache payloads, check the actual serializer and configure serialization accordingly; entity `@Transient` is not a universal guarantee across all Redis write paths.

This is a common misconception: seeing the same Redis server and assuming every write operation uses the same entity converter.

### 5.3. `@Transient` and Java `transient`

You can write:

~~~java
private transient String requestTraceId;
~~~

The Java `transient` keyword has language-level semantics, particularly for Java serialization. Spring Data may also recognize this modifier when building property metadata. However, when you want to clearly express **the intent to exclude from Spring Data's persistent model**, use `org.springframework.data.annotation.Transient`. It directly documents the mapping contract that code readers need to understand.

Do not assume every serialization mechanism skips the field in the same way; verify the specific storage path.

## 6. Typical Uses of Non-Persistent Properties

### 6.1. Values Recomputed from Persisted Data

Instead of writing a display badge to Redis and having to update it whenever loyalty points change, compute it on demand:

~~~java
@Transient
private String displayBadge;

public String getDisplayBadge() {
    return loyaltyPoints >= 100 ? "VIP" : "Standard";
}
~~~

In this approach, Redis only needs to store `loyaltyPoints`. After reloading the entity, the getter still computes the right badge. Note: a getter containing computation logic does not automatically make the property transient; the annotation on the field is the clear signal for the Spring Data mapper.

If a getter simply returns a transient field without recomputing it, the value after loading from Redis is typically `null`. Therefore, explicitly decide whether the property is **computed on demand**, **populated after loading**, or **not needed beyond the original request**.

### 6.2. Request Context or Single-Operation Data

Examples include `requestTraceId`, the name of the user viewing the data, or validation state within a workflow. These vary per request and make no sense as long-lived entity state.

In many cases, it is better to keep context in a service/request-scoped object or DTO, because the same persisted entity may be used across multiple requests. When attaching an auxiliary field to the entity during a flow is still necessary, `@Transient` prevents accidentally persisting it.

### 6.3. Properties That Must Not Be Indexed or Queried from Redis

A field excluded from stored data also cannot be assumed to exist in indexes or repository queries. For instance, if `displayBadge` is computed dynamically yet you need to find all "VIP" customers directly in Redis, simply adding a query method by `displayBadge` is not enough.

Choose among:

- Storing a queryable business property and updating it under clear rules.
- Querying from the persisted underlying data, such as `loyaltyPoints`, with compatible indexing/query support.
- Computing the label after reading data if data volume and query goals permit.

`@Transient` expresses the decision that the property **is not part of persistent state**, so do not design Redis queries as though the field were written.

## 7. Notes on Constructors, Getters, and Property Access

### Entity Materialization Constructor

Spring Data must instantiate the object and populate persistent properties when reading from Redis. For entities using a persistence constructor, do not require passing a value that exists only on a `@Transient` field:

~~~java
// Design to avoid if this is the required constructor to materialize the entity:
public CustomerProfile(
        String id,
        String fullName,
        String requestTraceId) {
    // requestTraceId is not in Redis for the framework to restore.
}
~~~

In the main example, a no-arg constructor with assignable fields keeps mapping simple. If designing an immutable entity, ensure the persistence constructor or factory only requires data the mapper can supply, and compute temporary values after construction or outside the entity.

### Placing the Annotation on the Property Recognized by Spring Data

For field-based declarations like `CustomerProfile`, placing `@Transient` directly on the field to skip is clearest. If the project uses property access, constructor binding, or custom mapping, make sure the annotation sits on the exact property Spring Data detects; do not annotate an unrelated method expecting another field to vanish from Redis.

If you accidentally declare two distinct states, such as a `displayBadge` field and a separate property mapped independently via getters/setters, clarify which accessor corresponds to which property.

### Do Not Mistake `@Transient` for Sensitive-Data Protection

The annotation skips a field on **the storage path using Spring Data mapping**; it does not encrypt data, prevent logging, stop REST serialization, or guarantee other serializers omit the field. For sensitive data, still design appropriate DTOs, logging configurations, access controls, and storage policies.

## 8. When Modifying an Entity That Already Has Data in Redis

Suppose an earlier version persisted `displayBadge`, and later `@Transient` was added:

~~~java
@Transient
private String displayBadge;
~~~

Once code runs with the new mapper, subsequent writes will skip that property. However, **the annotation does not automatically run a migration removing old fields from every existing Redis Hash**. Distinguish clearly:

1. **New mapping behavior**: the property is no longer treated as persistent data.
2. **Legacy physical data**: keys already in Redis may still retain the old field until rewritten, deleted, expired, or cleaned up via a dedicated migration.

If old data must be purged completely, plan cleanup around the actual keyspace and data lifecycle. Especially for TTL-expiring data, evaluate whether letting old keys naturally expire is sufficient. Never issue a full-database flush command just to clean up one property.

`@Transient` also **does not alter a key's TTL**. Expiration is controlled by Redis Hash settings, `@RedisHash(timeToLive = ...)`, `@TimeToLive`, or explicit Redis commands; that is a separate concern from excluding a property from saved data.

## 9. Common Issues and How to Address Them

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Field still appears in REST JSON | `@Transient` only applies to Spring Data mapping | Use a DTO, `@JsonIgnore`, or Jackson config to shape JSON |
| Field still has a value right after `save` | The object in hand is still the in-memory instance | Reload the entity via `findById` to verify persisted state |
| Field appears in `opsForValue().set(...)` payload | Saved with a different serializer than Redis Repository | Inspect the actual `RedisSerializer` |
| Reading from Redis yields `null` for transient field | No stored data to restore | Recompute or populate after reading if business logic needs it |
| Old Redis keys still have the previously stored field | Legacy keys/Hashes from earlier version not cleaned up | Define a migration or TTL policy |
| Repository cannot query the transient field | Field is absent from persisted data/index model | Query by persistent properties or revise storage model |
| Entity materialization constructor fails | Constructor requires data belonging to skipped property | Design an appropriate persistence constructor |
| Wrong annotation imported from another library | Did not import `org.springframework.data.annotation.Transient` | Check imports and mapper configuration |

## 10. Design Principles

When deciding whether to mark a property with `@Transient`, ask: **If creating a fresh entity solely from Redis, do we need—and can we reconstruct—this property's value?**

- If the property is business data needed across requests, persist it with an appropriate persistence mechanism.
- If the property can be derived from persisted data, mark it transient and compute it on read/use.
- If the property serves only the current request or display, skip persisting it—and consider moving it to a separate DTO/context.
- If the property needs to be queried, indexed, or participate in Redis data relationships, model it as genuine persisted data.

With Spring Data Redis Repositories, `@Transient` is a simple tool to keep Redis Hashes focused on business state that truly needs to persist. Proper usage means **marking properties explicitly**, **verifying with a write-and-reload test**, and **distinguishing entity mapping from JSON/cache/value serialization**. That way, Java objects stay flexible for temporary computations while Redis data avoids bloat and stale state.
