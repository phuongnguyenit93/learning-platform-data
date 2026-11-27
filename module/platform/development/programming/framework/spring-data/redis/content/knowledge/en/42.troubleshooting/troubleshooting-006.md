# Missing Repository Query Results Due to Out-of-Sync Indexes in Spring Data Redis

## 1. Symptom: Data Exists Yet findBy… Methods Return Empty

A Spring Boot application stores customers in Redis using a Spring Data Redis Repository. After writing data, lookup by ID succeeds, whereas lookup by email returns empty:

```java
repository.findById("c-101");                 // Optional containing Customer
repository.findByEmail("an@example.test");   // Optional.empty()
```

A developer opens the Redis CLI and sees that the customer's hash still exists. This causes confusion: **if the data is still in Redis, why can't the repository find it?**

The cause may be that **the secondary index used by Spring Data Redis for the derived query does not contain the membership matching the underlying data**. The repository does not perform a full scan of all Redis hashes to find every object whose `email` equals the requested value. For supported query properties, it relies on a separately managed index.

Illustration:

```text
                 CustomerRepository
                   /            \
                  /              \
        findById("c-101")   findByEmail("an@example.test")
                |                     |
                v                     v
       Redis hash "customers:c-101"   Redis secondary index SET
                |                     |
                v                     v
          email exists            no c-101 membership
                |                     |
                v                     v
         Returns Customer          Returns empty
```

This lesson shows how to **identify the exact failure class, inspect hash/index state, distinguish root causes, reproduce in a controlled way, and repair indexes safely**. The ultimate goal is to avoid silently dropping records during business lookups.

> **Principle:** `findById` and `findBy<Field>` can follow two different access paths. The continued existence of the primary hash **does not by itself prove** the secondary index is accurate.

## 2. Learning Objectives

After this lesson, you will be able to:

1. Explain how Spring Data Redis Repositories build and use secondary indexes.
2. Distinguish entity hashes, index sets, and auxiliary repository metadata.
3. Distinguish **missing index**, **stale index**, **truly absent data**, and **incorrect query conditions**.
4. Diagnose cases where `findById` finds data while `findByEmail`/`findByRegion` misses results.
5. Recognize the risks of direct updates via `RedisTemplate`, `HSET`, `DEL`, Lua, or processes outside the Repository.
6. Analyze the impact of TTL, expiration, Redis keyspace notifications, restarts, and listener downtime.
7. Design inspection and index-repair steps that do not accidentally delete data.
8. Write integration tests proving indexes update on proper Repository saves and can drift on out-of-band writes.
9. Design monitoring and a runbook to catch index drift early.

The examples use fictional customer names, emails, and regions; in real systems, avoid logging personal data or exposing it in dashboards.

## 3. Spring Data Redis Repository Differs From a Relational Database

In Spring Data JPA, a query can be executed by a database engine using an index table or a scan chosen by a query planner. With Spring Data Redis Repository, Redis does not provide a built-in SQL engine that natively understands `findByEmail`.

Spring Data Redis stores entities as Redis data structures and maintains **secondary indexes** to support query methods.

Example:

```java
@RedisHash("customers")
public class Customer {

    @Id
    private String id;

    @Indexed
    private String email;

    private String displayName;
}
```

Conceptually, the system maintains:

```text
Entity hash:
    customers:c-101
       id    = c-101
       email = an@example.test
       displayName = An

Index for email=an@example.test:
    <repository-managed index SET>
       member -> c-101 / key reference
```

When calling `findByEmail("an@example.test")`, the Repository resolves identifiers through the index, then loads the corresponding entities.

**Important:** Index key names, value encoding, and metadata structure are implementation details of the Spring Data Redis mapping/converter version. Examples illustrate keys like `customers:email:an@example.test`, but **do not assume that exact format is a stable contract across all versions**. During diagnosis, inspect the actual keys created by your application.

## 4. Data Categories Involved in Secondary Indexing

A Redis Repository can manage multiple key types:

| Data Category | Role | Examples |
| --- | --- | --- |
| Entity hash | Holds the object's fields | `customers:c-101` |
| Secondary index set | Maps property values to entity identifiers | Indexes by email, region |
| Helper/reference index metadata | Helps maintain index membership on entity change/delete | Auxiliary keys created by the mapping layer |
| TTL/expiration metadata | Manages object lifecycle | Expiring entity keys, shadow copies when enabled |
| Keyspace notification subscription | Receives expired events to clean up indexes when needed | Redis Pub/Sub/keyevent |

Do not delete unfamiliar keys sharing the entity prefix before confirming whether they are entity hashes, index sets, or Repository metadata.

Deleting only the hash while leaving the index causes queries to find **membership pointing to a missing entity**. Deleting only the membership while keeping the hash causes field queries to **miss the entity**.

## 5. Two Types of Index Mismatch to Distinguish

### 5.1. Missing Index Entry — Missing Results

```text
Hash:
  customers:c-101
  email = an@example.test

Index email=an@example.test:
  does not contain c-101
```

Consequence:

```java
findById("c-101")                 // Entity found
findByEmail("an@example.test")   // Entity not found
```

This is the exact failure described in the title: **Repository query missing results due to an out-of-sync index**.

### 5.2. Stale Index Entry — Index Pointing to Old State

```text
Hash:
  customers:c-101
  email = binh@example.test

Index email=an@example.test:
  still has c-101 membership

Index email=binh@example.test:
  does not yet have c-101 membership
```

Depending on the version and query execution path, querying the old email may still consider that ID or have to discard a non-matching entity; querying the new email may still fail to find it.

Both situations show that **the index no longer reflects the current value in the hash**.

### 5.3. Dangling Index Entry — Membership Pointing to a Gone Key

```text
Index region=north:
  contains c-101

Hash customers:c-101:
  does not exist
```

The usual consequence is that lookups traverse an ID with no remaining entity or return incomplete results. This drift appears when expiration/`DEL` cleanup is incomplete.

Do not lump all three cases together as "Redis lost data," because each requires a different remediation.

## 6. Ordered Diagnosis: Entity, Index, Query, Topology

Decision diagram:

```text
Repository findByEmail misses results
                 |
                 v
      Connected to the right Redis?
                 |
          +------+------+
          |             |
         No            Yes
          |             |
    Fix config      findById(id)
                        |
                  +-----+------+
                  |            |
                Empty      Entity found
                  |            |
          Check expired    Check indexed
          TTL/DB/prefix        field
                                 |
                                 v
                     Compare actual value
                        with query input
                                 |
                                 v
                        Check index set
                          membership
                                 |
                    +------------+------------+
                    |                         |
              Entry missing              Entry present
                    |                         |
          Investigate write path     Check read path,
          /migration/@Indexed        TTL, stale ID,
                                     serializer, query
```

Do not start with `FLUSHDB`, changing Redis versions, or a "full rebuild" before locating where the discrepancy lies.

## 7. Step 1: Confirm the Actual Redis Environment in Use

Check connection settings from deployment manifests and Spring Boot configuration:

```yaml
spring:
  data:
    redis:
      host: redis.internal
      port: 6379
      database: 0
      timeout: 3s
```

Possibilities to rule out:

- App A writes to development Redis while App B reads staging Redis.
- A service points to a different port.
- `spring.data.redis.database` differs when using standalone Redis.
- The entity prefix changed after a deploy.
- The service reads from a replica experiencing replication lag.
- Redis Sentinel master failed over while a client kept an old address.
- A Redis Cluster key is routed to another shard.
- Tests use an embedded/mock store instead of real Redis.
- TLS/ACL errors cause certain operations to fail, but exceptions are caught and turned into empty lists.

**Redis Cluster only supports database 0 under the cluster model**; do not rely on `SELECT 1` to isolate logical databases in Cluster.

If any exception is swallowed and converted into `Collections.emptyList()`, remove that behavior during diagnosis: **a failed query** and **a valid query returning empty** are two different events.

## 8. Step 2: Check by ID First

If the entity ID is known, call:

```java
Optional<Customer> byId =
    repository.findById("c-101");
```

This shows whether the Repository can load the entity by ID.

Possible outcomes:

| findById | findByEmail | Preliminary Interpretation |
| --- | --- | --- |
| Present | Present | Lookup path is healthy for this record |
| Present | Empty | Inspect field/index/query input |
| Empty | Empty | Data absent, expired, wrong prefix/DB, or mapping issue |
| Empty | Query hits stale membership | Possible dangling index |
| Present | Query returns wrong entity | Possible stale index or query semantics issue |

`findById` does not prove `email` is indexed. It only verifies the entity load path.

When multiple entities are missing from queries, obtain the expected ID set from an **independent source of truth**. `findAll()` on the same Redis Repository may not be ground truth across out-of-band manual writes, so do not assume it covers the entire keyspace.

## 9. Step 3: Inspect Redis With CLI

Run against a **test** Redis instance or an environment where read inspection is authorized:

```bash
redis-cli -h redis.internal -p 6379 PING
redis-cli -h redis.internal -p 6379 TYPE customers:c-101
redis-cli -h redis.internal -p 6379 HGETALL customers:c-101
redis-cli -h redis.internal -p 6379 TTL customers:c-101
```

`TYPE` confirms the key is actually a hash. `HGETALL` reveals fields when the serializer/mapping writes human-readable values.

**Security note:** Never print full hashes containing real emails, phone numbers, or tokens into public logs or tickets. Inspect only necessary fields and mask sensitive data.

If a binary serializer is used, `HGETALL` output can look unreadable. Do not infer the hash is "empty" just because a viewer tool cannot decode it; inspect raw bytes with Redis CLI or use the matching converter.

Inspect the keyspace with `SCAN`:

```bash
redis-cli -h redis.internal -p 6379 --scan --pattern 'customers:*'
```

`SCAN` does not provide a transactional snapshot and can return duplicates or miss keys if the keyspace mutates during iteration; handle deduplication and do not assume the namespace is static under concurrent writes.

Avoid `KEYS customers:*` on large keyspaces in production because it can block the Redis server while scanning.

## 10. Step 4: Identify the Actual Index Key

After running `repository.save(customer)` in an isolated environment, inspect newly created keys:

```bash
redis-cli --scan --pattern 'customers:*'
```

If you suspect a key is an index:

```redis
TYPE customers:email:an@example.test
SMEMBERS customers:email:an@example.test
SCARD customers:email:an@example.test
```

**The name `customers:email:an@example.test` is only an example.** Refer to the actual keys generated by your application rather than hardcoding patterns from an article.

When `TYPE` is `set`, inspect its members. Determine whether members are raw IDs, serialized IDs, or key references; do not write a repair script before verifying encoding.

If possible, save a test record with a synthetic email in test Redis and compare the keyspace **before and after save** to see the exact keys your Spring Data Redis version creates.

## 11. Step 5: Check Email Values and Normalization

Not every empty query is caused by index drift.

Example:

```text
Hash email = "An@Example.Test"
Query = "an@example.test"
```

Redis index lookups may rely on exact serialized/indexed values; do not assume case-insensitive matching like a relational database collation.

Other discrepancies:

- Leading/trailing whitespace.
- Unicode normalization.
- Inconsistent email/phone normalization between writer and reader.
- Indexed field being `null`.
- Enum serialized as a different string after an upgrade.
- Moving `@Indexed` from one field to another.
- Query referencing a property alias that does not match mapping.
- Query combining multiple predicates without matching indexes.

Example application-level normalization contract:

```java
public static String normalizeEmail(String email) {
    if (email == null) {
        throw new IllegalArgumentException(
            "Email is required"
        );
    }

    return email.trim().toLowerCase(
        java.util.Locale.ROOT
    );
}
```

This is an illustrative policy. Email canonicalization has nuances (especially in the local part), so define it per use case; do not force lowercasing without checking business rules.

**Important:** Both `save` and `findByEmail` must apply a consistent normalization policy. Fixing only the reader leaves older index entries mismatched.

## 12. Minimal Project Example: Customer Repository

For controlled reproduction, create a Spring Boot project with:

- Spring Data Redis.
- Spring Boot Test.
- Testcontainers JUnit Jupiter.
- A Redis server/container for integration tests.

In Maven, core dependencies (versions managed by the Spring Boot BOM):

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Pick Spring Boot, Spring Data Redis, Java, and Testcontainers versions matching your project. Do not upgrade every dependency just hoping "indexes magically start working" before identifying the cause.

## 13. Creating an Entity With @Indexed

File `Customer.java`:

```java
package com.example.customer;

import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("customers")
public class Customer {

    @Id
    private String id;

    @Indexed
    private String email;

    @Indexed
    private String region;

    private String displayName;

    protected Customer() {
    }

    public Customer(
            String id,
            String email,
            String region,
            String displayName) {
        this.id = id;
        this.email = email;
        this.region = region;
        this.displayName = displayName;
    }

    public String getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public String getRegion() {
        return region;
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public void setRegion(String region) {
        this.region = region;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
```

Annotations:

| Annotation | Role |
| --- | --- |
| `@RedisHash("customers")` | Specifies the Redis Repository keyspace |
| `@Id` | Identifies the entity |
| `@Indexed` on `email` | Requests a secondary index on email |
| `@Indexed` on `region` | Requests a secondary index on region |
| Getters/setters | Support mapping and sample state updates |

`@Indexed` is a mapping-layer indexing directive. It **does not automatically scan existing hashes created before the annotation was added**.

## 14. Creating the Repository Interface

File `CustomerRepository.java`:

```java
package com.example.customer;

import java.util.List;
import java.util.Optional;

import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, String> {

    Optional<Customer> findByEmail(String email);

    List<Customer> findByRegion(String region);
}
```

Notes:

- `findById` looks up directly by ID.
- `findByEmail` and `findByRegion` depend on secondary indexes for their respective properties.
- Spring Data Redis derived query support is **not equivalent to all SQL WHERE/JOIN operations**.
- Do not add `findByDisplayName` and assume it works if the field is unindexed or unsupported by the query mechanism.

Unsupported queries may be rejected at Repository creation time or at runtime depending on configuration/version. Never convert exceptions into empty results.

## 15. Enabling Redis Repositories

File `CustomerApplication.java`:

```java
package com.example.customer;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.data.redis.repository.configuration.EnableRedisRepositories;

@SpringBootApplication
@EnableRedisRepositories(
    basePackageClasses = CustomerRepository.class
)
public class CustomerApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            CustomerApplication.class,
            args
        );
    }
}
```

With Spring Boot, Redis Repositories can also be auto-configured depending on dependencies/settings; this example declares the package explicitly to avoid scanning unintended repositories.

If the application also uses Spring Data JPA, MongoDB, or multiple Spring Data modules, separate packages/repository types cleanly to prevent ambiguity among repository factories.

Recent Spring Boot Redis connection configuration:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      connect-timeout: 2s
      timeout: 3s
```

In Sentinel/Cluster environments, configure the appropriate topology instead of a single fixed standalone endpoint.

## 16. Standard Save Path Creates Indexes

Example executed in a Spring-managed service:

```java
Customer customer = new Customer(
    "c-101",
    "an@example.test",
    "north",
    "An"
);

repository.save(customer);

Customer byId =
    repository.findById("c-101").orElseThrow();

Customer byEmail =
    repository.findByEmail("an@example.test")
        .orElseThrow();
```

With valid data and metadata, the Repository mapping layer maintains the hash and required secondary indexes for annotated fields.

Conceptual flow:

```text
repository.save(customer)
           |
           v
Redis mapping converter
           |
           +-- serialize entity -> hash by ID
           |
           +-- maintain email index membership
           |
           +-- maintain region index membership
           |
           +-- maintain internal reference metadata
```

Do not replace `save` with direct `HSET` and expect indexing steps to run automatically. Redis only executes the `HSET` sent by the client; the Redis server knows nothing about Java `@Indexed` annotations.

## 17. Intentionally Reproducing Index Drift in a Test Environment

Perform this only on an isolated test Redis instance.

**Initial state:**

```java
repository.save(new Customer(
    "c-101",
    "an@example.test",
    "north",
    "An"
));
```

At this point, querying the old email returns the entity.

Suppose another piece of code writes directly to the Redis hash:

```java
StringRedisTemplate template = ...;

template.opsForHash().put(
    "customers:c-101",
    "email",
    "binh@example.test"
);
```

This changes the field value in the hash without invoking Redis Repository index maintenance.

The state can become:

```text
Entity hash:
    customers:c-101
       email = binh@example.test

Index for an@example.test:
    still has c-101

Index for binh@example.test:
    does not have c-101
```

Then:

```java
repository.findById("c-101");               // Entity found
repository.findByEmail("binh@example.test"); // May be empty
```

**Important point:** If field/value serializers or mapping differ from the example, a raw `HSET` may also write a payload that the converter cannot decode. When reproducing, verify how entity hashes are actually stored in your project's Redis setup rather than forcing raw field encoding if it differs.

This experiment also shows why editing hashes via Redis CLI in production can break secondary indexes.

## 18. Integration Test Catching Out-of-Repository Writes

Use Spring Boot, Testcontainers, and real Redis. Example:

```java
package com.example.customer;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Optional;

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

@SpringBootTest
@Testcontainers
class CustomerIndexIntegrationTest {

    @Container
    static final GenericContainer<?> REDIS =
        new GenericContainer<>(
            DockerImageName.parse("redis:7.4.2-alpine")
        ).withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(
            DynamicPropertyRegistry registry) {
        registry.add(
            "spring.data.redis.host",
            REDIS::getHost
        );

        registry.add(
            "spring.data.redis.port",
            () -> REDIS.getMappedPort(6379)
        );
    }

    @Autowired
    CustomerRepository repository;

    @Autowired
    StringRedisTemplate redis;

    @Test
    void repositorySaveCreatesSecondaryIndex() {
        String id = "c-test-101";

        repository.save(new Customer(
            id,
            "an@example.test",
            "north",
            "An"
        ));

        assertThat(repository.findById(id)).isPresent();

        assertThat(
            repository.findByEmail("an@example.test")
        ).isPresent();

        assertThat(
            repository.findByRegion("north")
        ).extracting(Customer::getId)
         .contains(id);
    }

    @Test
    void rawHashUpdateDoesNotMaintainEmailIndex() {
        String id = "c-test-102";

        repository.save(new Customer(
            id,
            "old@example.test",
            "north",
            "An"
        ));

        // Intervene only in test Redis.
        // Assumes the field is stored as a String.
        redis.opsForHash().put(
            "customers:" + id,
            "email",
            "new@example.test"
        );

        assertThat(
            repository.findById(id)
        ).isPresent();

        // No repository save call to add
        // membership for the new email.
        assertThat(
            repository.findByEmail("new@example.test")
        ).isEmpty();
    }
}
```

### Limitations of This Example

- The test relies on default mapping of `email` to a string-compatible hash field. With custom converters/serializers, adjust the raw write accordingly.
- In larger suites, use unique IDs or clean up the test namespace carefully.
- This test **illustrates one root cause**; it does not claim every empty `findByEmail` result is a missing index.
- Never run this index-corrupting variant against production Redis.

When code actually causes index drift, do not "fix" it by adding a full-keyspace `SCAN` to every request; fix the write path.

## 19. Updating Through the Repository Instead of the Redis Hash API

One way to update:

```java
public Customer changeEmail(
        String id,
        String newEmail) {

    Customer customer =
        repository.findById(id).orElseThrow();

    customer.setEmail(newEmail);

    return repository.save(customer);
}
```

The goal is to give the Repository an opportunity to update index metadata alongside the entity.

If multiple services write the same entity, or if both Repository and raw Redis APIs are used, establish **a single write ownership strategy**.

Not every `save` guarantees:

- An atomic distributed transaction with another database.
- Freedom from races when two writers update the same ID.
- Instant consistency across every brief window between multiple Redis commands.
- Zero lost updates across failover.

At the business level, define concurrency, versioning, or locking policies if multiple writers can race.

## 20. Notes on PartialUpdate and Other Write Paths

Spring Data Redis supports partial entity updates in certain APIs/versions, such as `PartialUpdate` with `RedisKeyValueTemplate`. When using an officially supported API, the mapping layer can manage impacts on indexes and TTL according to the implementation's capabilities.

However, that **does not mean** any partial update at any layer knows how to update indexes.

Distinguish:

| Write Path | Index Maintenance |
| --- | --- |
| `repository.save(entity)` | Managed by mapping layer according to metadata |
| Repository delete methods | Includes cleanup through repository path |
| Supported `PartialUpdate` API | Check behavior by version and operation |
| `StringRedisTemplate.opsForHash().put` | Does not apply `@Indexed` annotations |
| `redis-cli HSET` | Unaware of Java mapping metadata |
| Lua writing hashes directly | Does not maintain Repository indexes |
| External application writing Redis | No guarantee of Repository index maintenance |
| `DEL customers:c-101` from CLI | Does not clean up repository-managed metadata |

If existing code uses raw `HSET`, treat it as a prime drift suspect before blaming the Redis driver or Spring query execution.

## 21. Adding @Indexed After Data Already Exists

Deployment scenario:

```text
Version 1:
    Customer.email has no @Indexed
    repository.save() creates millions of customer hashes

Version 2:
    Add @Indexed to email
    deploy new application
```

**Adding the annotation does not automatically scan old Redis keys to backfill indexes for existing entities.**

As a result:

- Customers created after deployment are searchable by email.
- Older customers not yet re-saved/backfilled may lack index membership.
- `findById` still works.
- The failure pattern is typically **only older records missing from results**.

### Remediation Approach

1. Plan a controlled index backfill.
2. Obtain the target ID set from a trusted source.
3. Read entities and re-write via the Repository path when safe.
4. Avoid stripping TTL or overwriting concurrently updated data.
5. Add checkpointing and progress metrics.
6. Verify samples before, during, and after backfill.
7. Rate-limit execution so Redis is not overloaded.

Do not run a bulk Redis CLI `SADD` script using guessed key formats without verifying the exact index metadata and helper sets managed by the Repository.

## 22. Renaming Fields or Mapping Paths

Example:

```text
Version 1: customer.email
Version 2: customer.primaryEmail
```

If `@Indexed` moves to the new field while older data still stores `email`, queries on `primaryEmail` cannot find older entities.

Possible states:

- Old hashes lack the new field.
- Converter alias/mapping is mismatched.
- Old index remains while the new index has not been populated.
- Some pods run v1 while others run v2.
- Serializers or custom conversions changed.
- Normalization differs across deployments.

This is a **schema migration** problem, not merely a Redis memory issue.

Follow a versioned rollout process:

1. Define payload schema and index schema.
2. Ensure new readers handle old data or use a separate namespace.
3. Backfill data and indexes as required.
4. Shift query traffic once index coverage meets requirements.
5. Retire old paths only after old producers are gone.
6. Maintain a rollback plan if index drift spikes.

## 23. Redis Repositories Do Not Support Every Query Type

Common misconceptions:

```java
List<Customer> findByDisplayNameContaining(String text);
List<Customer> findByEmailIgnoreCase(String email);
List<Customer> findByRegionOrderByDisplayNameAsc(String region);
```

Do not assume every Spring Data JPA derived query behaves identically in Redis Repositories.

Spring Data Redis supports specific query patterns backed by indexed fields, with capabilities varying by version. Partial-text matching, complex sorting, joins, or relational-style filters may not be supported.

When a query does not return expected results, verify first:

- Is the query method supported by Spring Data Redis?
- Does the field have `@Indexed` or matching index configuration?
- Is there a query predicate without index backing?
- Are casing and serialization consistent?
- Is Redis Search/RediSearch or another data store needed for full-text/range queries?

Do not hand-craft fake indexes to force an unsupported query to mimic SQL.

## 24. TTL: Entity May Expire Before Index Cleanup Runs

An entity with TTL:

```java
@RedisHash(value = "customers", timeToLive = 600)
public class Customer {
    // @Id, @Indexed ...
}
```

The `timeToLive` value in this annotation is expressed in the unit supported by the Redis mapping configuration—typically seconds as shown here.

When TTL elapses:

```text
Entity hash customers:c-101 -> expired
Secondary index SET        -> may need membership cleanup
```

Spring Data Redis can listen to Redis keyspace expiration events to handle cleanup/index metadata updates.

**Important point:** Redis keyspace notifications use Pub/Sub; if the listener is down, events can be missed. Do not treat event delivery as a durable queue.

### Potential Impacts

- Hash is gone while index membership remains -> dangling entry.
- Listener is disabled or lacks permission to configure notifications.
- Application downtime overlaps with expiration.
- Managed Redis disallows `CONFIG SET`.
- Key was evicted or raw-deleted instead of expiring through the expected path.
- Replica/failover shifts event timing relative to expectations.

Depending on mapping and query execution, dangling entries can add lookup overhead or anomalous outcomes; **missing results while the hash still exists** requires investigating other causes like missing membership or normalization.

## 25. Keyspace Notifications: Configuration and Observation

Redis provides:

```bash
redis-cli -h redis.internal -p 6379 CONFIG GET notify-keyspace-events
```

When keyevent expiration notifications are needed, a common setting is:

```conf
notify-keyspace-events Ex
```

Where:

- `E`: keyevent notification channels.
- `x`: expired events.

Production settings may combine other flags; do not overwrite production configuration without understanding existing flags.

In a test environment with admin privileges:

```bash
redis-cli -h redis-test.internal -p 6379 CONFIG SET notify-keyspace-events Ex
```

This is a **runtime change on the Redis server**, not merely a Spring annotation.

### When Does Spring Create the Listener?

Spring Data Redis provides `@EnableRedisRepositories` configuration and keyspace event management options depending on version, such as `ON_STARTUP`, `ON_DEMAND`, or `OFF` in `RedisKeyValueAdapter.EnableKeyspaceEvents`.

Example:

```java
import org.springframework.data.redis.core.RedisKeyValueAdapter;
import org.springframework.data.redis.repository.configuration.EnableRedisRepositories;

@EnableRedisRepositories(
    basePackageClasses = CustomerRepository.class,
    enableKeyspaceEvents =
        RedisKeyValueAdapter.EnableKeyspaceEvents.ON_STARTUP
)
class RedisRepositoryConfiguration {
}
```

If repositories are already enabled on `CustomerApplication`, do not add a duplicate configuration class like this without adjusting the existing setup. This is **an alternative option**, not a snippet to paste alongside an existing annotation.

Depending on version and option, Spring may attempt to set notification flags via Redis `CONFIG`; managed services may forbid this. Inspect startup logs and configure infrastructure accordingly.

## 26. Why Listener Downtime Causes Index Drift

Timeline:

```text
T0 Customer c-101 has 60s TTL
T1 Spring app restarts, listener offline
T2 Redis key customers:c-101 expires
T3 Redis emits expired event
T4 No subscriber receives event
T5 Spring app comes back online
T6 Secondary index metadata may still point to c-101
```

Redis Pub/Sub **does not replay** the T3 event to a subscriber reconnecting at T5.

Distinguish:

- **Missing index:** hash exists, membership missing.
- **Dangling index:** hash gone, membership remains after expiration.
- **Operational consequence:** both can make queries disagree with expected state, though their causes and fixes differ.

For systems requiring accurate indexes, schedule periodic reconciliation/backfill instead of relying solely on notifications.

## 27. Shadow Copies and Expired Key Events

Some Spring Data Redis Repository versions retain a **phantom/shadow copy** of the entity for a window after TTL expiration so `RedisKeyExpiredEvent` can include the object's data.

Key considerations:

- Shadow copies can increase memory usage.
- Shadow copy contents may hold sensitive data needing protection.
- Configuration options control shadow copy behavior depending on version.
- If shadow copies are disabled, event payloads may lack full entity data even when the ID is known.
- Listener downtime still does not turn Pub/Sub into a durable queue.

Do not "fix" index drift by keeping shadow copies forever or inflating TTL without identifying root cause. Evaluate memory, retention, and privacy requirements.

## 28. Key Eviction and Expiration Are Not the Same

A Redis instance configured with:

```conf
maxmemory 512mb
maxmemory-policy allkeys-lru
```

can evict an entity key **before its TTL expires**. Eviction is not the same as expiration, and you must not assume an expired-key cleanup listener will automatically handle evicted or manually `DEL`eted keys.

Ways a key can disappear:

| Cause | What to Check |
| --- | --- |
| TTL expiration | Keyspace expired events, listener state |
| Memory eviction | `evicted_keys`, maxmemory policy |
| Repository delete | Repository index cleanup path |
| Raw `DEL` | Bypasses Java repository index maintenance |
| Admin cleanup/flush | Can strip metadata unexpectedly |
| Failover/replication lag | State divergence across primaries/replicas |
| Schema/prefix change | Reader querying a different keyspace |

If a system uses Redis Repositories for critical state, do not share the same Redis eviction pool with disposable caches where early eviction breaks data semantics.

## 29. Replica Data May Lag Behind the Primary Index

Redis replication is usually asynchronous.

If the application reads from replicas:

```text
Primary: entity hash written
Replica: not all changes applied yet
```

During the replication-lag window, queries can miss new index membership or hashes.

Check:

- `INFO replication`.
- Lettuce/Jedis read routing.
- Primary vs. replica endpoints.
- Whether failover/promotion occurred.
- Whether operations require read-your-writes consistency.

Note that within a single Redis stream, commands replicate in order; do not assume a replica always received the hash while missing the index in every scenario. Observe actual state and timing.

If immediate reads after writes are required, prefer primary reads or a store with appropriate consistency guarantees.

## 30. Races Between Multiple Writers

Two services concurrently edit the same customer:

```text
Writer A reads old email
Writer B reads old email

Writer A changes email -> a1@example.test
Writer B changes region -> south on old object

Writer A repository.save(...)
Writer B repository.save(...)
```

If B re-saves the full stale entity, it can overwrite A's email change, leaving both entity state and index membership different from what users expect.

This is a **concurrent update / lost update** problem; not every missing query result is an index-maintenance bug.

Design approaches:

- Assign a single owner service for writes.
- Use optimistic locking/versioning when supported by the mapping layer.
- Avoid read-modify-write on stale snapshots.
- Define field-level update semantics.
- Use atomic Redis operations where appropriate.
- Test concurrency against real Redis, not just Mockito.
- Measure and reconcile both hashes and indexes after races.

Do not build a manual secondary index schema as a workaround for lost updates.

## 31. Recovery Approach: Do Not Delete All Indexes First

When index drift is detected, actions **you should not run right away**:

```bash
redis-cli FLUSHDB
redis-cli FLUSHALL
redis-cli KEYS '*'
```

`FLUSHDB`/`FLUSHALL` wipe data; `KEYS` can severely impact production latency.

Also avoid:

- Blindly deleting every key starting with `customers:`.
- Running `SADD`/`SREM` against unverified key patterns.
- Overwriting millions of hashes with stale snapshots from a script.
- Resetting TTLs on business-deadline keys without assessing impact.
- Rebuilding under thousands of concurrent writers with no consistency plan.
- Skipping backups/snapshots before bulk operations.

**Prioritize fixing the write path and planning a checkpointed backfill** instead of patching symptoms with manual Redis commands.

## 32. Diagnostic Plan Before Repair

Collect a sample set of records:

| ID | `findById` | Actual field | `findByField` | Index membership |
| --- | --- | --- | --- | --- |
| c-101 | Present | an@example.test | Missing | Missing |
| c-102 | Present | binh@example.test | Present | Present |
| c-103 | Empty | — | Reference entry present | Stale |
| c-104 | Present | south | Missing | Normalization mismatch |

Values are illustrative; verify actual membership.

Classification groups:

- A: entity hash has data, index missing.
- B: index exists, entity gone.
- C: hash value and index disagree.
- D: wrong query / case mismatch.
- E: serializer / prefix / topology change.
- F: unsupported query method.

Classifying prevents a single "repair" pass from corrupting the other groups.

## 33. Single-Entity Repair: Controlled Repository Path

In a test environment or authorized maintenance window:

```java
Customer customer =
    repository.findById("c-101").orElseThrow();

repository.save(customer);
```

With an active mapping layer and intact metadata, saving can recreate/update secondary indexes for that entity.

**However, do not assume this call is always safe:**

- It can alter remaining TTL or trigger callbacks/event handlers.
- The entity hash may hold an unreadable legacy schema.
- Concurrent writers can be overwritten if the script holds an old snapshot.
- Repository index helper metadata may already be missing or corrupt.
- Old stale indexes may require extra cleanup depending on version behavior.
- The current version's mapping may write different index structures than the old version.

Afterward, verify `findById`, `findByField`, actual Redis index membership, and TTL.

Repairing one entity successfully **does not prove millions of others are fixed**.

## 34. Why TTL Must Be Preserved

Suppose:

```text
customers:c-101
TTL before repair = 120 seconds
```

If a script runs read -> `repository.save(customer)` unconditionally and the mapping sets a 600-second TTL, retention for that customer gets extended by 8 minutes.

For sessions, OTPs, or temporary records, that can be a business bug.

Before repairing:

```redis
PTTL customers:c-101
```

Determine:

- Is entity TTL governed by `@RedisHash(timeToLive=...)` or `@TimeToLive`?
- Does `@TimeToLive` preserve remaining expiration accurately?
- Does re-saving reset the deadline?
- Was a key without TTL intentional?
- Can the key expire between read and write?

Without a verified way to preserve expiration, **do not run automated production backfills** based solely on a read-save snippet.

A dedicated migration tool may be needed to build index membership safely with respect to the current schema and concurrent writers.

## 35. Backfilling Many Entities: Safe Plan

When adding `@Indexed` to existing data, run a controlled job:

```text
Identify source-of-truth IDs
           |
           v
Read entity by ID
           |
           v
Verify schema + required indexed field
           |
           v
Maintain index via repository-aware path
           |
           v
Verify query/index membership
           |
           v
Checkpoint success/failure
           |
           v
Repeat with rate limit
```

Requirements:

1. **Trusted ID source:** authoritative database or controlled scan; do not rely solely on the broken index.
2. **Idempotent job:** re-running does not create duplicate entries or corrupt logic.
3. **Rate limit:** prevents latency spikes on Redis.
4. **Checkpointing:** resumes cleanly after restarts.
5. **TTL policy:** avoids accidentally extending nearly expired records.
6. **Concurrency policy:** avoids overwriting fresh updates.
7. **Observability:** counts for scanned, repaired, skipped, failed.
8. **Verification:** pre/post coverage sampling and statistics.
9. **Rollback plan:** backups and recovery steps.
10. **Multi-version rollout:** ensure v1 writers are not still corrupting new indexes.

Do not run an unbounded `KEYS *` + `save` loop just because a 10-record test passed.

## 36. When Is a Full Index Rebuild Needed?

A broad rebuild may be required when:

- A new annotation was added after many hashes already existed.
- An external writer edited raw hashes over a long period.
- Old and new deployments use incompatible index schemas.
- Index helper metadata was lost.
- Index drift spans multiple tenants or shards.
- A Redis instance was restored from a snapshot out of sync with writers/mapping.

But "rebuild" must be defined explicitly:

- From which authoritative data source?
- Which version's index key naming and serialization?
- Should old indexes be removed, and how?
- Will there be downtime or dual-read/dual-write?
- How do you prevent mid-rebuild queries from returning partial results?
- Is there enough memory to hold two temporary index sets during migration?
- Is rollback possible?

Do not manually set TTLs on index SETs to match individual entity TTLs if those sets hold multiple IDs with different expirations; index lifecycles must follow your Repository/version's mechanism.

## 37. Versioned Migration Strategy

When building or refactoring a system, prefer:

```text
Repository schema v1:
    customers:v1:* + index v1

Repository schema v2:
    customers:v2:* + index v2
```

General workflow:

1. Deploy a migration-aware reader.
2. Write/sync into the new namespace in a controlled manner.
3. Backfill all eligible records.
4. Verify counts, samples, and index memberships.
5. Switch query traffic to v2.
6. Monitor mismatches and latency.
7. Retire v1 writers.
8. Clean up v1 only after a safe rollback window.

This is a design pattern; changing `@RedisHash` values does not migrate data automatically.

Splitting namespaces can double RAM usage during migration; perform capacity planning, especially when Redis enforces `maxmemory`/eviction.

## 38. Alternative: Query From an Authoritative Data Source

For critical entity data, Redis Repository should often act only as a read cache/index while a database remains the source of truth.

Example:

```text
GET customer by email
      |
      v
Redis Repository index
      |
      +-- HIT -> Validate business constraints
      |
      +-- MISS / suspected drift
               |
               v
         Authoritative DB query
               |
               v
          Repair or refresh cache
```

**Do not automatically treat every miss as index drift**: the customer may genuinely not exist.

When using fallback:

- Query an accurate authoritative source.
- Rate-limit fallback queries to avoid overloading the DB.
- Never create duplicate accounts/orders just because a Redis query missed.
- Emit mismatch metrics between Redis and the authoritative source.
- Ensure repairs do not overwrite newer updates.
- Never bypass authorization or tenant filtering when fetching from the DB.

This mitigates the blast radius of index drift, though it does not replace fixing the write path.

## 39. Use Redis Search When Queries Exceed Repository Index Capabilities

If query requirements include:

```text
Email prefix
Full-text name search
Numeric range
Sorting
Compound filters
Vector search
```

basic Spring Data Redis Repository secondary indexes may not fit.

You may need:

- Redis Search/Query Engine with its own schema/indexing, if supported by your deployment.
- Relational database queries/indexes.
- Elasticsearch/OpenSearch or another dedicated search engine.
- Service-managed denormalized keys and custom indexes if complexity is small and maintenance contracts are clear.

**Do not conflate the two mechanisms:** `@Indexed` in Redis Repositories is not a Redis Search index schema. Seeing an index in a Redis Search tool does not prove a Repository derived query uses it.

## 40. Redis Cluster: Topology-Aware Index Diagnosis

Redis Cluster shards data across 16,384 hash slots.

An entity hash and a secondary index SET can reside in different Redis keys. For multi-key operations, transactions, or scripts, Cluster enforces same-slot constraints, and Repository operation support depends on version and mapping design.

When production runs Cluster:

- Confirm Redis Cluster support and limitations for your Repository version.
- Do not assume all multi-key Repository operations execute atomically across Cluster.
- Query individual shards/nodes as needed rather than treating one seed node as holding the full keyspace.
- `SCAN` on one node does not scan the entire Cluster.
- Record topology and node IDs when errors occur.
- Distinguish `MOVED`/`ASK`/`CROSSSLOT` errors from legitimately empty queries.
- Never turn Cluster errors into `Optional.empty()`.

If the Redis Repository index model requires operations incompatible with Cluster topology, redesign data placement or query architecture; do not abuse a global hash tag to force the entire dataset into one slot.

## 41. Redis Replica Reads and Consistency

In a primary–replica topology:

```text
Primary A writes:
   hash update
   index SET membership

Replica B reads:
   replication has not caught up
```

Queries routed to a replica can observe stale state during the asynchronous replication window.

Check:

- Lettuce `ReadFrom` policy.
- Whether the client reads primary or replica.
- `INFO replication` offsets/link state.
- Whether a failover occurred.
- Read-after-write consistency requirements.
- Whether timeouts are caught and turned into empty results.

If writes must be immediately visible to subsequent reads, route queries to the primary or use a store with suitable consistency rather than treating replica reads like transaction commits.

## 42. Metrics to Detect Index Drift

A useful dashboard:

| Suggested Metric | Meaning |
| --- | --- |
| `redis_repository_find_by_id_hit` | ID lookup returned an entity |
| `redis_repository_index_query_miss` | Secondary-index query returned no results |
| `redis_repository_index_mismatch` | Probe found entity/hash vs. index discrepancy |
| `redis_repository_repair_success` | Entities repaired successfully |
| `redis_repository_repair_failure` | Entities that failed repair |
| `redis_repository_repair_backlog` | Entities awaiting repair |
| `redis_keyspace_expiry_event_gap` | Monitoring signal for unstable event/cleanup flow |
| `redis_connection_errors` | Client/connection errors |
| `redis_replication_lag` | Replication lag per metric definition |
| `redis_key_evictions` | Keys dropped due to memory eviction |

These metric names are **suggestions**, not auto-generated defaults from Spring Boot/Micrometer.

A helpful ratio:

```text
index_coverage_ratio =
    number_of_authoritative_sample_records_found_by_index
    /
    number_of_authoritative_sample_records_tested
```

Use an accurate sample source, protect personal data, and break down stats by namespace/version.

Counting only "empty email queries" without knowing expected entities cannot prove every empty result is index drift.

## 43. Designing Sample Reconciliation

Do not scan millions of records on every request. Run a periodic verification job:

1. Draw a sample of IDs from an authoritative source.
2. Load each record by ID.
3. Read the `@Indexed` field value.
4. Query by that field.
5. Verify the entity ID appears in the result.
6. Record mismatch metrics using an **anonymized identifier hash**, never plaintext emails.
7. Classify missing/stale/dangling cases.
8. Repair only under an approved policy.

Pseudo-code example:

```java
for (String id : sampledIds) {
    Optional<Customer> byId =
        repository.findById(id);

    if (byId.isEmpty()) {
        continue;
    }

    Customer customer = byId.get();

    boolean found = repository
        .findByEmail(customer.getEmail())
        .map(Customer::getId)
        .filter(id::equals)
        .isPresent();

    if (!found) {
        metrics.increment("index_mismatch");
    }
}
```

Limitations: this snippet does not separate network errors from empty results if exceptions are masked lower down; it does not check stale entries for old emails; and it only covers sampled IDs. Use it to detect drift, not to claim 100% global index accuracy.

## 44. Classifying Root Cause With an Audit Trail

If email-change logs show:

```text
T0 Repository saved c-101: email=an@example.test
T1 External job executed HSET email=binh@example.test
T2 Query findByEmail(binh@example.test) returned empty
```

This timeline strongly points to an external writer.

If:

```text
T0 Deploy v2 adds @Indexed
T1 New customers query correctly
T2 Old customers not found by email
```

missing backfill is the strong candidate.

If:

```text
T0 Customer TTL expires
T1 App listener offline
T2 Redis index set still contains old ID
```

this is dangling membership from missed cleanup.

Investigate using logs, deployment history, and Redis snapshots rather than guessing "Spring Redis index bug."

## 45. Why Not Run SCAN + HGETALL on Every API Query?

A dangerous workaround:

```text
findByEmail failed
    |
    v
SCAN entire Redis
    |
    v
HGETALL each customer
    |
    v
compare email manually
```

Drawbacks:

- O(N) or worse relative to total keys/hashes.
- Multiplies network round trips.
- Can cause latency spikes and overload Redis.
- Does not yield a consistent snapshot while the keyspace changes.
- Risks scanning across tenants accidentally.
- Does not scale to millions of entities.

Rate-limited **offline/maintenance scans** are acceptable for inventory or backfill; never turn them into an API hot-path query engine.

If you need flexible, large-scale field queries, pick an appropriate indexing/query architecture.

## 46. Do Not Repair Indexes With Ad-Hoc SADD Without Understanding Metadata

Seeing missing membership, someone might try:

```redis
SADD customers:email:binh@example.test c-101
```

In a demo, that adds a member to a SET. But Spring Data Redis Repositories can also rely on **helper/reference index metadata**, mapping conventions, and serializers that must stay aligned.

Risks:

- Members may require IDs in a different encoding.
- Stale membership may remain in the old index.
- Subsequent Repository saves/deletes may not clean up manual entries.
- Keys may belong to a different namespace, tenant, or version.
- The entity's TTL may already be gone.
- A concurrent writer may have changed the email again.

Only run manual `SADD`/`SREM` inside a **repair tool verified against your exact implementation/version**, backed by tests and backups—not as a knee-jerk reaction to an empty query.

## 47. Duplicate Values and Multiple IDs in the Same Index

Example `region=north` index:

```text
Index region=north:
    c-101
    c-102
    c-103
```

`findByRegion("north")` often returns multiple entities. Because the index is a Redis SET:

- There are no duplicates of **the same member** within one SET.
- One region value can map to many IDs.
- SET member order does not guarantee business sorting.
- If a hash disappears, leftover membership creates a dangling entry.
- If a new hash lacks membership, the returned list is incomplete.

Do not rely on Redis SET ordering as API ordering. If stable sorting or pagination is needed, design an explicit strategy and verify Repository capabilities.

## 48. Why findById Alone Cannot Prove a Healthy Repository

These calls:

```java
repository.save(customer);
repository.findById(customer.getId());
```

can succeed even when `@Indexed` is missing or query indexes are broken.

Therefore, smoke tests for a Redis Repository with indexed queries should cover:

```text
save entity
findById exact ID
findByEmail exact value
update indexed field through repository
findByEmail new value
check old value no longer resolves incorrectly
delete entity
findById empty
findByEmail does not expose dangling stale entity
```

For TTL-enabled entities, also add:

```text
wait for expiration (bounded polling)
findById empty
monitor index cleanup behavior
```

These tests require real Redis; Mockito stubbing index membership does not verify Spring Data Redis mapping.

## 49. Test Updating an Indexed Field via Repository

Illustrative integration test:

```java
@Test
void savingChangedEmailUpdatesIndex() {
    Customer customer = new Customer(
        "c-test-201",
        "first@example.test",
        "north",
        "An"
    );

    repository.save(customer);

    assertThat(
        repository.findByEmail("first@example.test")
    ).isPresent();

    customer.setEmail("second@example.test");

    repository.save(customer);

    assertThat(
        repository.findByEmail("second@example.test")
    ).isPresent();

    assertThat(
        repository.findByEmail("first@example.test")
    ).isEmpty();
}
```

Run this test against your project's actual Spring Data Redis version to confirm the mapping/index-maintenance contract when changing fields.

If the test fails, investigate index helper metadata, mapping, serializers, write paths, TTL, and concurrent operations; do not immediately conclude `@Indexed` is broken.

In multi-test suites, use unique IDs, reset namespaces cleanly, and avoid concurrent tests sharing the same email.

## 50. Test Deleting via Repository

Example:

```java
@Test
void deletingEntityDoesNotLeaveItQueryable() {
    Customer customer = new Customer(
        "c-test-301",
        "delete@example.test",
        "south",
        "Binh"
    );

    repository.save(customer);

    repository.deleteById(customer.getId());

    assertThat(
        repository.findById(customer.getId())
    ).isEmpty();

    assertThat(
        repository.findByEmail("delete@example.test")
    ).isEmpty();
}
```

This test verifies behavior from the Repository's perspective, but does not prove every helper set key was completely removed in all cases unless you inspect the Redis keyspace/metadata directly.

To investigate memory leaks from dangling indexes, add assertions on test Redis set memberships matching your version's key layout.

## 51. Testing Expiration Requires Controlled Timing

Give a test entity a short TTL or use a test-specific repository configuration.

Procedure:

1. `repository.save` an entity with a TTL.
2. Verify `PTTL` is positive.
3. Verify `findByEmail` succeeds before expiration.
4. Poll `findById` until empty with a bounded timeout.
5. Observe the expired-event listener and index cleanup in the test environment.
6. Verify queries no longer return expired data.
7. Check for leftover metadata if needed.
8. Do not demand event delivery at the exact millisecond of TTL expiry.

Avoid `Thread.sleep(1000)` followed by hard assertions right on a 1-second boundary; schedulers, server load, and network jitter make such tests flaky.

Redis keyspace notifications are best-effort events, not a millisecond-accurate delivery timer.

## 52. Valuable Deployment Test Cases

Test matrix:

| Test | Goal |
| --- | --- |
| Save then findById | Entity hash mapping |
| Save then findByEmail | Email index creation |
| Save then findByRegion | Multi-result index |
| Update email via Repository | Remove old index / add new index |
| Update via raw HSET | Expose index drift risk |
| Delete via Repository | Entity no longer queryable |
| Raw DEL | Detect dangling metadata |
| TTL expiration with listener online | Cleanup behavior |
| TTL expiration while listener offline | Missed cleanup / reconciliation need |
| Deploy adding @Indexed to existing data | Backfill requirement |
| Query after Redis failover | Read routing / consistency |
| Mixed-version deployment | Schema/index compatibility |
| Rebuild with concurrent writes | No overwriting fresh updates |
| Redis Cluster | Verify topology support |
| Redis outage | Never treat exceptions as empty results |

A standalone Redis Testcontainer only verifies standalone behavior; it does not prove Sentinel failover or Cluster compatibility.

## 53. Monitoring Keyspace and Index Cardinality

Useful Redis server signals:

```bash
redis-cli -h redis.internal -p 6379 INFO keyspace
redis-cli -h redis.internal -p 6379 INFO memory
redis-cli -h redis.internal -p 6379 INFO stats
```

Track:

- Key count and keys with TTL.
- Used memory/RSS and maxmemory.
- Expired keys and evicted keys.
- Redis command errors.
- Application query hit/miss ratio.
- Redis Repository index mismatch probes.
- Repair backlog and throughput.
- Keyspace notification listener health.
- Node role and replication lag.

**Note:** Total Redis keys do not equal entity count: one entity can create multiple index and helper keys. Do not use `dbsize` as an exact Customer count without accounting for the keyspace model.

If you need an entity count, use the authoritative source or enumerate via verified index/root metadata.

## 54. Monitoring Listeners and Missed Events

Metrics to track:

```text
redis_repository_expiry_event_received_total
redis_repository_listener_connected
redis_repository_reconciliation_mismatch_total
redis_repository_repair_backlog
```

These are suggested metric names; Spring/Micrometer does not emit them out of the box.

If a listener disconnects, missed keyspace events are not replayed and may require reconciliation. Watch closely for:

- Redis reconnects/timeouts.
- Redis restarts.
- Spring pod restarts and listener startup.
- Managed Redis `notify-keyspace-events` reset to an incompatible value.
- Keys evicted prematurely.
- Full resyncs/failovers.
- Multiple application instances subscribing and how they handle events.

Do not treat "event count = 0" alone as proof of failure; no keys may have expired during that window.

## 55. Runbook for Missing Query Results

### Step 1 — Confirm the Symptom

Take a known entity ID from a trusted source.

```java
repository.findById(id);
repository.findByEmail(expectedEmail);
```

Record timestamp, application version, and environment.

### Step 2 — Verify Input and Topology

- Is the email normalized consistently?
- Are tenant and environment correct?
- Is Redis reading from primary or replica?
- Did prefix/keyspace change?
- Is an exception being caught and converted to empty?

### Step 3 — Inspect the Redis Hash

Use `TYPE`, `HGETALL`, or mapping-aware inspection on minimal required fields.

### Step 4 — Inspect the Index

Verify the actual SET key and membership for your Spring Data Redis version.

### Step 5 — Check Root Causes

- Raw `RedisTemplate`/CLI/Lua writers.
- Newly added `@Indexed` without backfill.
- Mixed-version schemas or serializers.
- TTL, eviction, or listener downtime.
- Concurrent updates.
- Cluster/replica lag.
- Unsupported query method.

### Step 6 — Assess Scope

Sample trusted IDs, estimate mismatch rate, and quantify business impact.

### Step 7 — Stop New Sources of Drift

Fix the writer, migration, or listener configuration first.

### Step 8 — Controlled Repair

Test on staging/test first, preserve TTL, take backups, rate-limit, and checkpoint.

### Step 9 — Verify Results

Compare `findById`, indexed queries, Redis membership, and the authoritative business source.

### Step 10 — Post-Fix Monitoring

Track mismatch, fallback, and latency over time to confirm drift does not recur.

## 56. Cause-and-Action Map

```text
Query missing results
       |
       +-- Entity gone
       |       -> check TTL / DB / eviction / keyspace
       |
       +-- Entity present, index missing
       |       -> @Indexed? raw write? backfill?
       |
       +-- Entity present, stale index
       |       -> out-of-repository update / schema migration
       |
       +-- Index points to missing entity
       |       -> expiration listener / raw DEL / event gap
       |
       +-- Index correct, query wrong
       |       -> case normalization / query support / serializer
       |
       +-- Query errored yet returned empty
       |       -> remove blanket catch / emit error metrics
       |
       +-- Topology mismatch
               -> primary/replica lag / Cluster routing / DB/prefix
```

The key takeaway is that **not every "not found" symptom shares the same root cause**.

## 57. Exercise A: Create and Inspect Secondary Indexes

Create two customers:

```java
repository.save(new Customer(
    "c-1", "an@example.test", "north", "An"
));

repository.save(new Customer(
    "c-2", "binh@example.test", "north", "Binh"
));
```

Tasks:

1. Call `findById` for both.
2. Call `findByEmail` for each email.
3. Call `findByRegion("north")` and verify both IDs.
4. Use Redis CLI `SCAN` to inspect the keys created by the Repository.
5. Identify index SETs and their memberships.
6. Explain why an index SET is not an entity hash.

## 58. Exercise B: Reproduce Missing Index via Raw HSET

On a test Redis instance:

1. `repository.save` a customer.
2. Use raw `HSET` to change the email field.
3. Read the entity with `findById`.
4. Call `findByEmail(newEmail)`.
5. Inspect index membership for both the old and new emails.
6. Implement a write-path fix without scanning every key.
7. Explain why a one-off manual `SADD` is not necessarily a complete repair.

## 59. Exercise C: Adding @Indexed After Deployment

Suppose one million Customer records already exist.

The new version adds:

```java
@Indexed
private String email;
```

Tasks:

1. Explain why older records may not be found.
2. Choose an authoritative source of IDs for backfill.
3. Design a checkpointed, rate-limited job.
4. Ensure TTLs are not unintentionally extended.
5. Choose a strategy for handling concurrent writers.
6. Design sample verification and a rollback plan.
7. Propose when to switch query traffic to the new index.

## 60. Exercise D: TTL and Listener Outage

A customer has a 60-second TTL; the Spring app shuts down at second 30 and restarts at second 120.

Tasks:

1. Describe what likely happens to the hash.
2. Describe what index membership may remain.
3. Explain why Redis Pub/Sub does not replay expired events.
4. Distinguish expired, evicted, and raw-deleted keys.
5. Propose a reconciliation job for dangling indexes.
6. Design a test using bounded polling instead of sleeping right on the boundary.

## 61. Exercise E: Identifying an Incorrect Query

Customers store emails:

```text
An@Example.Test
binh@example.test
```

Query:

```java
findByEmail("an@example.test");
```

Tasks:

1. Analyze the normalization policy.
2. Determine whether index lookup can miss due to case mismatch.
3. Add validation/normalization on both save and query paths.
4. Design a migration for legacy records.
5. Write an integration test to prevent behavioral divergence across deployments.

## 62. Exercise F: Redis Cluster and Index Maintenance

Suppose the application uses Redis Cluster with `@RedisHash`/`@Indexed`.

Tasks:

1. Identify your Spring Data Redis version and Cluster support limits.
2. Check where entity hashes and index SETs are routed.
3. Determine whether multi-key operations require the same hash slot.
4. Watch for `CROSSSLOT`, `MOVED`, and `ASK` errors.
5. Propose changes to key placement or query architecture if required.
6. Explain why a standalone Redis Testcontainer is insufficient to prove Cluster compatibility.

## 63. Common Misconceptions

**"findById finding data means findByEmail must find it too."**

No. `findById` uses the entity hash, whereas `findByEmail` depends on secondary index membership.

**"Redis automatically builds an index on HSET."**

No. Redis knows nothing about Java's `@Indexed` annotation; indexing is handled by the mapping layer or a separate indexing system.

**"Simply adding @Indexed automatically indexes existing data."**

No. Records written before the index declaration may require migration/backfill.

**"Every JPA derived query works in Redis Repository."**

No. Redis Repositories have their own set of query capabilities and limits.

**"If HGETALL looks right and the query fails, the Redis server must be broken."**

Not necessarily. The index may be missing, query input may mismatch, or serializers/mapping versions may differ.

**"If an email changes, raw HSET is enough."**

No. Raw `HSET` does not update Repository index sets.

**"Keyspace notifications handle every key disappearance."**

No. Expiration, eviction, raw deletion, and downtime involve different mechanics; Pub/Sub does not replay missed events during offline windows.

**"Expired key events are a durable queue."**

No. Redis Pub/Sub events are lost if no subscriber is connected.

**"Different Redis logical DBs or prefixes guarantee consistent indexes."**

No. They only separate namespaces at their respective levels and do not replace mapping index maintenance.

**"Running SADD to put a member into an index is a safe repair."**

Not unless you have verified encoding, helper metadata, TTL, and concurrent writes.

**"Running SCAN over every hash per request is a fix for missing indexes."**

No. It causes O(N) load and does not scale.

**"Redis Cluster is just standalone Redis with more nodes."**

No. Cluster introduces hash slots, redirects, and multi-key constraints.

**"A read after a write in Redis always sees the new data."**

Not with replica routing, replication lag, or non-atomic multi-command writes.

**"Re-saving millions of entities is always a safe backfill."**

Not by default. It can reset TTLs, overwrite newer updates, spike load, and introduce other risks.

## 64. Frequently Asked Questions

### Why does findById return a result while findByEmail does not?

Because they use two different access paths. Email queries rely on properly maintained secondary indexes; if the entity hash exists but index membership is missing, the query returns empty.

### Does @Indexed automatically create a Redis Search index?

No. Spring Data Redis Repository secondary indexing is separate from Redis Search/Query Engine indexing. Each system has its own schema and query pipeline.

### Can I update a Redis hash with StringRedisTemplate?

At the Redis command level, yes—but then you must manage the impact on Repository indexes yourself. Without a dedicated sync mechanism, do not mix raw writes and expect Repository query indexes to stay updated automatically.

### Should every property be indexed?

No. Index only fields that need to be queried and are supported, because indexes consume memory and add write/update/delete maintenance overhead.

### Why are only older customers missing?

`@Indexed` was likely added after those records already existed, and no backfill has been run yet.

### Why does an index still contain an ID whose TTL expired?

The expiration event listener may have missed the event, cleanup may not have completed, or the key was removed outside the Repository. Inspect lifecycle and metadata.

### Does Redis Repository guarantee an atomic transaction across the hash and all index SETs?

Do not assume writes across hashes and index sets form a globally atomic distributed transaction with other systems. Check API/version behavior whenever concurrency and consistency are critical.

### Can I use Redis CLI to repair indexes?

Only once you fully understand and verify key layout, index metadata, encoding, and concurrent writers; prefer repository-aware repair tested in staging first.

### Should I delete old indexes and recreate them?

Never impulsively. A large rebuild requires an authoritative data source plus control over downtime, TTL, memory, rollback, and verification.

### Does Redis Cluster affect Redis Repository indexes?

Yes, it can—due to key placement, multi-key restrictions, and mapping/version limits. Test against a real Cluster topology.

### How do I tell an empty query apart from a Redis outage?

Do not swallow exceptions into empty results. Log and meter connection/timeout errors separately; reserve empty returns for successful queries that found no matching data.

### Can index drift be eliminated completely?

You can reduce risk with single write ownership, consistent repository paths, schema migrations, controlled TTLs, monitoring, and reconciliation. In distributed systems, however, you should still design detection and remediation for drift.

### Should I use findAll to backfill every entity?

Understand its semantics and what data the Repository actually tracks. If raw records exist outside repository management, `findAll` may not cover everything. Prefer a verified source of IDs.

### Will putting a cache in front of Redis Repository fix the problem?

No. Caching can mask the bug longer; fix index maintenance or authoritative fallback queries first.

## 65. Summary

When a Spring Data Redis Repository returns incomplete results, determine **whether the underlying data still exists** and **whether the secondary index accurately reflects the field**.

Core takeaways:

1. `findById` and `findBy<Field>` can take different access paths.
2. `@Indexed` makes the Repository maintain secondary indexes, but does not backfill pre-existing data.
3. Raw `HSET`, `DEL`, Lua, and external writers **do not update Spring Data Redis index metadata**.
4. Missing indexes, stale indexes, and dangling indexes are distinct states.
5. TTL/expiration, listener downtime, and Pub/Sub keyspace notifications can leave metadata needing reconciliation.
6. Never assume Redis Repository query semantics or serializers match JPA.
7. Repairs require understanding the actual schema, preserving TTL, avoiding overwriting concurrent updates, and supporting checkpoints/rollback.
8. Verify with **Redis integration tests**, not just Mockito.
9. With Redis Cluster or replicas, account for topology, replication consistency, and multi-key constraints.
10. For critical data, maintain an authoritative data source and drift detection/repair rather than assuming secondary indexes are always infallible.

> **Safe workflow:** confirm symptom -> inspect ID and hash -> check index membership -> classify root cause -> fix write path -> run controlled repair -> verify with queries and monitoring.

Following this workflow lets teams diagnose "data exists yet search misses it" without losing records or introducing new errors during remediation.

## References

- [Spring Data Redis – Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html)
- [Spring Data Redis – Secondary Indexes](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/indexes.html)
- [Spring Data Redis – Time To Live](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html)
- [Spring Data Redis – RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Data Redis – Redis Cluster](https://docs.spring.io/spring-data/redis/reference/redis/cluster.html)
- [Spring Data Redis – Keyspace Events](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html)
- [Redis – SCAN](https://redis.io/docs/latest/commands/scan/)
- [Redis – HGETALL](https://redis.io/docs/latest/commands/hgetall/)
- [Redis – SADD](https://redis.io/docs/latest/commands/sadd/)
- [Redis – SMEMBERS](https://redis.io/docs/latest/commands/smembers/)
- [Redis – TYPE](https://redis.io/docs/latest/commands/type/)
- [Redis – TTL](https://redis.io/docs/latest/commands/ttl/)
- [Redis – Keyspace Notifications](https://redis.io/docs/latest/develop/pubsub/keyspace-notifications/)
- [Redis – Replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/)
- [Testcontainers for Java](https://java.testcontainers.org/)
