# Setting a Fixed TTL for Entities Saved with a Repository in Spring Data Redis

Not all data stored in Redis needs to exist indefinitely. An order draft might only be valid for 30 minutes; a verification code might expire after a few minutes; temporary processing workflow data can be removed when it is no longer needed. With **Spring Data Redis Repositories**, a simple way to specify a fixed time to live for an entire entity type is to declare `timeToLive` on the `@RedisHash` annotation.

For example:

```java
@RedisHash(value = "checkout-drafts", timeToLive = 1800)
public class CheckoutDraft {
    @Id
    private String id;
}
```

The number `1800` represents **1,800 seconds = 30 minutes**. When the Repository saves a `CheckoutDraft`, Spring Data Redis sets an expiration time on the Redis key representing the entity. Once expired, the key is no longer read as an existing entity, even if the application does not call a delete method.

This lesson explains what a fixed TTL means, how to configure it, how Redis Repository maintains TTL across the entity lifecycle, and key considerations around updates, queries, indexes, and expiration events.

## 1. What is TTL and why set it on an entity?

**TTL (Time To Live)** is the remaining duration before a Redis key expires. Redis stores the expiration timestamp at the **key** level and handles key expiration itself. For an entity managed by a Redis Repository, the entity data typically resides in a Redis Hash, so the TTL is applied to **the Redis key holding that Hash**.

```text
Java entity: CheckoutDraft(id="draft-001")
          |
          | checkoutDraftRepository.save(...)
          v
Redis Hash: checkout-drafts:draft-001
          |
          +-- id            = draft-001
          +-- customerId    = customer-42
          +-- note          = Awaiting confirmation
          +-- _class        = ...CheckoutDraft
          |
          +-- TTL = 1800 seconds
                    |
                    v
          Expired --> key is no longer accessible
```

The TTL applies to **the entire entity key**. Redis does not delete the `note` field separately first while keeping `customerId`. If individual attributes need different expiration times, separate keys or a different data model must be designed.

Some use cases suited for a fixed TTL:

| Data type | Purpose of TTL | Example |
|---|---|---|
| Checkout drafts | Avoid keeping abandoned drafts forever | 30 minutes |
| Temporary verification codes | Limit the valid usage window | 5 minutes |
| Short-lived processing state | Clean up state that is no longer needed | 1 hour |
| Temporary business session data | For sessions with a well-defined lifetime | 20 minutes |

These numbers are for illustration only, not default lifetimes in Spring Data Redis. An appropriate lifetime must come from business requirements.

### How does TTL differ from manual deletion?

- With `deleteById(...)`, the application actively deletes the entity through the Repository.
- With TTL, Redis determines when the key expires based on the expiration attached to the key.
- **Expiration** is different from **memory eviction**. Depending on the `maxmemory` policy, Redis may evict a key before its TTL ends.
- Redis TTL is a key lifecycle management mechanism and does not automatically replace requirements for durable storage, auditing, or business operations that must be guaranteed to execute.

Redis uses the expiration timestamp and detects expired keys upon access or during background cleanup cycles. Therefore, the moment a deletion event is emitted should not be treated as a millisecond-accurate timer. Even so, once the deadline has passed, normal read operations will treat the expired key as nonexistent.

## 2. Configuring a Fixed TTL with @RedisHash

`@RedisHash` marks a class as an aggregate root stored in a Redis Repository. Beyond specifying the **keyspace**, the annotation supports the `timeToLive` attribute:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash(value = "checkout-drafts", timeToLive = 1800)
public class CheckoutDraft {

    @Id
    private String id;

    private String customerId;

    private String note;

    protected CheckoutDraft() {
        // For Spring Data when instantiating the entity.
    }

    public CheckoutDraft(String id, String customerId, String note) {
        this.id = id;
        this.customerId = customerId;
        this.note = note;
    }

    public String getId() {
        return id;
    }

    public String getCustomerId() {
        return customerId;
    }

    public String getNote() {
        return note;
    }

    public void changeNote(String note) {
        this.note = note;
    }
}
```

In this example:

| Declaration | Role |
|---|---|
| `@RedisHash("checkout-drafts")` | Declares the keyspace; the Redis key typically has the form `checkout-drafts:<id>` |
| `timeToLive = 1800` | Configures the lifetime for each entity when saved by the Repository |
| `@Id` | Identifies the ID value used to build the Redis key |
| `customerId`, `note` | Business fields mapped into the Redis Hash |

**The default unit of `timeToLive` is seconds.** Thus, `timeToLive = 60` corresponds to one minute; `timeToLive = 3600` corresponds to one hour. Document the unit clearly in comments or use a specifically named constant to reduce confusion with milliseconds.

For example:

```java
private static final long THIRTY_MINUTES_IN_SECONDS = 30 * 60;

@RedisHash(value = "checkout-drafts", timeToLive = 1800)
public class CheckoutDraft {
    // ...
}
```

Annotations require compile-time constants, so you cannot directly pass a variable read dynamically from `application.yml` into `timeToLive`. If the lifetime needs to vary by deployment configuration or per entity, you should consider other TTL configuration approaches rather than trying to force a dynamic value into the annotation.

**Note:** A fixed value in `@RedisHash` applies uniformly to entities of that class according to the Repository's save policy. This differs from `@TimeToLive` placed on a property or method to allow the lifetime to vary per instance.

## 3. Connecting the Repository to Redis

For a Spring Boot application using Spring Data Redis, the dependency is typically:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

Example connection configuration in `application.yml`:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
```

This is a local Redis configuration for demonstration purposes; real-world applications must configure connection details, authentication, TLS, cluster, or sentinel according to the runtime environment. In a Spring Boot environment with proper repository configuration, Redis Repositories can be detected automatically. If you need to enable them explicitly:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.repository.configuration.EnableRedisRepositories;

@Configuration
@EnableRedisRepositories
public class RedisRepositoryConfig {
}
```

Repository for the entity:

```java
import org.springframework.data.repository.CrudRepository;

public interface CheckoutDraftRepository
        extends CrudRepository<CheckoutDraft, String> {
}
```

When using `CrudRepository`, the application calls `save`, `findById`, `existsById`, and `deleteById`. Spring Data Redis handles mapping and reading/writing the underlying Redis Hash. There is no need to manually issue `EXPIRE` after every save just to apply the declared fixed TTL.

## 4. Service Example Using an Entity with a Fixed TTL

A service that operates on drafts:

```java
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class CheckoutDraftService {

    private final CheckoutDraftRepository repository;

    public CheckoutDraftService(CheckoutDraftRepository repository) {
        this.repository = repository;
    }

    public CheckoutDraft create(
            String draftId,
            String customerId,
            String note
    ) {
        CheckoutDraft draft =
                new CheckoutDraft(draftId, customerId, note);
        return repository.save(draft);
    }

    public Optional<CheckoutDraft> find(String draftId) {
        return repository.findById(draftId);
    }

    public CheckoutDraft updateNote(String draftId, String newNote) {
        CheckoutDraft draft = repository.findById(draftId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Draft does not exist or has expired: " + draftId
                ));

        draft.changeNote(newNote);
        return repository.save(draft);
    }

    public void delete(String draftId) {
        repository.deleteById(draftId);
    }
}
```

Usage flow:

```java
CheckoutDraft saved = draftService.create(
        "draft-001",
        "customer-42",
        "Awaiting shipping address confirmation"
);

Optional<CheckoutDraft> draft = draftService.find("draft-001");

CheckoutDraft updated = draftService.updateNote(
        "draft-001",
        "Shipping address added"
);
```

After saving, the Repository sets the key's expiration. Once the key expires, `findById("draft-001")` returns `Optional.empty()` if no process has recreated that key. The service should treat a not-found result as a normal outcome for TTL-backed data; an HTTP API can translate that into a message indicating the draft has expired or does not exist according to the business contract.

**Important:** The service code only illustrates the data flow. If an update operation must prevent concurrent overwrites, simply reading and calling `save` does not automatically provide optimistic locking or distributed transactions. Concurrency issues must be handled separately.

## 5. When Does TTL Start and How Does It Change?

With `@RedisHash`'s fixed TTL, the practical point to observe is **when the entity is saved via the Repository**. When `save` sets the expiration, Redis starts counting down from that moment.

Example with TTL = 1,800 seconds:

```text
12:00  repository.save(draft)       -> TTL is approximately 1800 seconds
12:05  repository.findById(id)      -> TTL is approximately 1500 seconds
12:10  repository.findById(id)      -> TTL is approximately 1200 seconds
12:12  repository.save(draft)       -> TTL is reset to approximately 1800 seconds
12:42  if no new save occurs        -> key has reached its expiration time
```

These timestamps are illustrative and do not account for execution time or other write operations.

### 5.1. Reads do not automatically extend TTL

Calling `findById(...)` only reads the entity. It is **not** a sliding-session TTL renewal operation. If a draft is created at 12:00 and a user only reads it repeatedly, the key still expires about 30 minutes after the last save unless other logic actively renews it.

If the business requires "30 minutes from the last activity," that is a **sliding expiration** policy, which differs from a fixed TTL attached to `@RedisHash`. You need to design an explicit renewal operation, track activity, and pay attention to concurrency.

### 5.2. Saving again usually resets the expiration

When you modify an entity and call `repository.save(entity)`, Spring Data Redis saves the entity state and reapplies the configured TTL. This typically **resets** the countdown starting from the new save.

This detail matters for drafts: if a job updates `note` every minute, the draft can continue to exist as long as the job keeps saving the entity periodically. If the requirement is "expire strictly 30 minutes after creation," re-saving with a fixed 30-minute TTL does **not** fully satisfy that requirement.

Two policies must be distinguished:

| Policy | Meaning | Fixed TTL on `@RedisHash` |
|---|---|---|
| 30 minutes from the last save | Each save can extend the lifetime | Matches the usual behavior |
| 30 minutes from creation, regardless of updates | Absolute deadline | Requires calculating remaining time or avoiding resets |
| 30 minutes from the last read or user action | Activity-based sliding expiration | Repository reads alone do not auto-renew |

If you choose a TTL of "30 minutes from creation," one approach is to store `expiresAt` as business data and compute the remaining TTL when saving, apply an appropriate `@TimeToLive` mechanism, or control writes under a dedicated policy. You must define how to handle cases where the expiration timestamp has already passed and avoid unintended extensions.

### 5.3. Deleting and recreating with the same ID

`deleteById(id)` actively deletes the entity. A subsequent `save` with the **same ID** can create a new key with a fresh TTL. Redis does not store a "history of expired IDs" to forbid recreation. If the business requires preventing ID reuse, a separate mechanism is needed.

## 6. Inspecting TTL Directly in Redis

After calling `repository.save(...)`, you can inspect the key using Redis CLI. With `@RedisHash("checkout-drafts")` and ID `draft-001`, the key is typically:

```text
checkout-drafts:draft-001
```

An illustrative inspection:

```redis
TYPE checkout-drafts:draft-001
# hash

HGETALL checkout-drafts:draft-001
# Fields/values mapped from CheckoutDraft

TTL checkout-drafts:draft-001
# (integer) 1794
```

`TTL` returns the **remaining seconds**. The value `1794` is just an example roughly six seconds after saving; you should not expect to see `1800` at all times.

To measure more precisely in milliseconds:

```redis
PTTL checkout-drafts:draft-001
# (integer) 1793200
```

Meaning of the results:

| Return value from `TTL`/`PTTL` | Interpretation |
|---|---|
| Non-negative integer | Remaining time: seconds for `TTL`, milliseconds for `PTTL` |
| `-1` | Key exists but has no expiration |
| `-2` | Key does not exist, including when it has expired |

Once the TTL expires:

```redis
EXISTS checkout-drafts:draft-001
# (integer) 0

TTL checkout-drafts:draft-001
# (integer) -2
```

If `TTL` returns `-1` right after saving through the Repository, check whether the data was written using the right entity with `@RedisHash(timeToLive = ...)`. The actual operation may have used `RedisTemplate` or raw Redis commands instead of the Repository, or a later command may have cleared the expiration. Also ensure the CLI is connected to the same Redis instance and logical database as the application.

### Distinguishing value updates from TTL changes with Redis commands

To understand Redis at the key level:

```redis
SET demo:ttl "hello" EX 60
TTL demo:ttl
# roughly 60 seconds remaining

EXPIRE demo:ttl 120
TTL demo:ttl
# roughly 120 seconds remaining

PERSIST demo:ttl
TTL demo:ttl
# (integer) -1
```

This example operates on a Redis String to directly illustrate the meaning of `EXPIRE` and `PERSIST`. For entities managed by a Repository, let the Repository govern a consistent TTL policy. Changing TTL manually may be overwritten on the next `save` with the fixed lifetime from the annotation.

## 7. @RedisHash(timeToLive) and @TimeToLive

Spring Data Redis supports two common ways to configure TTL:

### 7.1. Fixed TTL for the entire class

```java
@RedisHash(value = "checkout-drafts", timeToLive = 1800)
public class CheckoutDraft {
    @Id
    private String id;
}
```

Every entity of the same type shares the same TTL policy as declared on the class. This suits data with a uniform lifetime and is easy to read and implement.

### 7.2. Per-instance variable TTL

When individual entities need different lifetimes, you can use `@TimeToLive` on a property or method:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.TimeToLive;

@RedisHash("temporary-records")
public class TemporaryRecord {

    @Id
    private String id;

    @TimeToLive
    private Long remainingSeconds;

    protected TemporaryRecord() {
    }

    public TemporaryRecord(String id, long remainingSeconds) {
        this.id = id;
        this.remainingSeconds = remainingSeconds;
    }
}
```

Each instance can supply its own lifetime, such as 60, 300, or 900 seconds. When loading the entity from Redis, the property annotated with `@TimeToLive` can also be populated with the remaining TTL from Redis (including special values indicating no expiration).

**Do not both set a fixed TTL on the class and add a `@TimeToLive` property without clearly establishing precedence rules.** If you need a uniform TTL for all entities, `@RedisHash(timeToLive = ...)` is the direct approach. If you need a per-instance TTL, design the `@TimeToLive` mechanism and how time is computed/read consistently.

| Criterion | `@RedisHash(timeToLive = ...)` | `@TimeToLive` |
|---|---|---|
| Where configured | On the entity class | On a property or method |
| TTL value | A single fixed value | Can differ across instances |
| Best suited for | Drafts, cached entities with a shared lifetime | Lifetimes depending on business rules or per record |
| Reading remaining TTL back into the object | No built-in dedicated TTL property | Can use the annotated field |
| Complexity | Low | Requires managing the time calculation policy |

## 8. Entity TTL Differs from Auxiliary Redis Keys' TTL

Spring Data Redis Repository can store additional auxiliary Redis keys beyond the entity's Hash, such as:

- A set tracking IDs in the keyspace.
- Redis Sets used as secondary indexes for `@Indexed` fields.
- A copy supporting expiration events, when that feature is enabled.

For example:

```text
checkout-drafts:draft-001
  -> Entity's Redis Hash, TTL 1800 seconds

checkout-drafts
  -> ID set managed by Repository infrastructure

checkout-drafts:customerId:customer-42
  -> Example secondary index if customerId has @Indexed
```

**The Hash's TTL does not mean all auxiliary keys share the same TTL.** Redis expiration applies per Redis key. For secondary indexes, the Repository infrastructure maintains index members when saving/deleting entities and uses expiration events to help clean up related data. If a key expires without the application receiving the necessary event, an index Set may temporarily retain the ID of a nonexistent entity.

Therefore, do not build business logic assuming Redis will automatically delete all index Sets at the exact same moment as the Hash. When you need to read an entity, use the Repository and handle cases where an ID in the index has already expired.

## 9. Expiration Events and the Repository "Shadow Copy"

When an entity has a positive TTL, Spring Data Redis Repository has a mechanism to publish `RedisKeyExpiredEvent` based on Redis keyspace notifications. So that the event can carry the expired entity's data, the Repository can create a **shadow copy** (also called a phantom copy) with a lifetime roughly **5 minutes** longer than the original key.

Illustration:

```text
12:00  Save CheckoutDraft
       |
       +-- Original key gets TTL = 30 minutes
       |
       +-- A shadow copy may be created for expiration events

12:30  Original key expires
       |
       +-- Redis emits expiration notification (if configured)
       |
       +-- Spring Data may create RedisKeyExpiredEvent
       |
       +-- Shadow copy remains alive for an extra period
              to read data for the event
```

**Memory implication:** Entities with TTL can incur additional Redis memory usage from shadow copies, especially when payloads are large or the number of expiring entities is high. The original key's TTL still applies; the shadow copy serves the infrastructure and is not a draft that remains usable via the Repository by its original ID.

If you do not need the entity's data in the expiration event, consider disabling shadow copies:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.RedisKeyValueAdapter;
import org.springframework.data.redis.repository.configuration.EnableRedisRepositories;

@Configuration
@EnableRedisRepositories(
    shadowCopy = RedisKeyValueAdapter.ShadowCopy.OFF
)
public class RedisRepositoryConfiguration {
}
```

When shadow copies are disabled, expiration events no longer carry a full copy of the expired entity. This decision must take into account business listeners and the secondary index cleanup mechanism in use.

### 9.1. Keyspace notifications are not a guaranteed-delivery event bus

Redis expiration events rely on Pub/Sub. Events may go unobserved if the listener has not started, the connection drops, or Redis does not have the required notification flags enabled. On managed Redis services, applications sometimes lack permission to change server configuration via the `CONFIG` command.

Therefore:

- Do not use `RedisKeyExpiredEvent` as the sole trigger to complete mandatory business operations, such as accounting postings or sending a notification that must not be lost.
- Do not assume the event is emitted at the exact instant TTL hits 0; Redis detects expirations according to its own processing mechanism.
- For index cleanup, monitor keyspace notification configuration and the possibility of missed events. Supplementary scan/reconciliation mechanisms may be needed when high consistency is required.
- In Redis Cluster, events are tied to the node holding the key; listeners must be connected and configured appropriately for the topology in use.

### 9.2. Configuring listener initialization

Spring Data Redis lets you control when the listener is registered via `@EnableRedisRepositories`. Example of initializing on application startup:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.RedisKeyValueAdapter;
import org.springframework.data.redis.repository.configuration.EnableRedisRepositories;

@Configuration
@EnableRedisRepositories(
    enableKeyspaceEvents =
            RedisKeyValueAdapter.EnableKeyspaceEvents.ON_STARTUP
)
public class RedisRepositoryConfiguration {
}
```

Depending on configuration, Spring Data Redis may attempt to set notification parameters on the Redis server. When connecting to a service that disallows `CONFIG`, configure notifications at the infrastructure level and adjust listener initialization accordingly. Do not copy-paste listener settings without evaluating your actual environment and requirements.

## 10. Key Considerations When Updating Entities with TTL

### 10.1. Repository save and raw Redis operations are not the same

For example:

```java
repository.save(draft);
```

This uses the Repository's mapping and TTL configuration. By contrast:

```java
stringRedisTemplate.opsForHash().put(
        "checkout-drafts:draft-001",
        "note",
        "Direct edit"
);
```

Direct Hash commands do not automatically inspect `@RedisHash` to create a TTL if the key has no expiration yet. Nor do they perform all the Repository's secondary index update steps. If operating on a key that already has a TTL, a regular `HSET` does not automatically renew the TTL of the entire key. Thus, the same business change can yield different TTL outcomes depending on the write path.

### 10.2. Do not assume changing a Java object immediately changes TTL

```java
CheckoutDraft draft = repository.findById("draft-001")
        .orElseThrow();

draft.changeNote("New content");
// No write command sent to Redis yet; TTL continues counting down.

repository.save(draft);
// Repository writes the change and reapplies the configured TTL.
```

Mutating fields in the JVM does not alter Redis. Only after the save method executes is there an effect on the key and its expiration.

### 10.3. Be careful with background tasks that continuously call save

If a job updates a draft's status every 10 seconds and calls `save` every time, a fixed 30-minute TTL will be reset continuously. You may have inadvertently turned "draft lives at most 30 minutes" into "draft lives at least 30 minutes after the job's last update."

You should clearly define:

1. Does expiration start from creation, from the last write, or from the last activity?
2. Which operations are allowed to renew the lifetime?
3. When must an entity be considered invalid from a business perspective?
4. If one thread reads an entity while another thread deletes/expires it, how should a subsequent write be handled?

Redis TTL enforces key lifecycle limits under the current configuration. It does not replace designing business expiration rules.

## 11. Common Issues and How to Handle Them

| Symptom | What to check | How to handle |
|---|---|---|
| `TTL key` always returns `-1` | Does the entity have `@RedisHash(timeToLive)`? Was it written via the Repository? | Use the proper Repository and verify the annotation / positive TTL |
| `TTL key` returns `-2` right after writing | Wrong key name, database, deleted key, or too-short lifetime | Check keyspace/ID, Redis connection, and expiration duration |
| TTL keeps jumping back near the initial value | Is a job or service repeatedly calling `save`? | Clarify which operations renew TTL; adjust policy if needed |
| `findById(...)` returns empty after some time | Key expired, was deleted, or was evicted | Handle nonexistent state in business logic |
| Key expired but index Set still holds the ID | Missed expiration event or writes/deletes bypassing the Repository | Review listener, notifications, and reconciliation mechanism |
| Redis uses more memory than expected | Shadow copies and auxiliary Redis keys | Measure usage; consider `shadowCopy = OFF` if appropriate |
| Not receiving `RedisKeyExpiredEvent` | Listener disabled, disconnected, or Redis missing notifications | Check connection config, keyspace notifications, and lifecycle |
| Calling `opsForValue().set(...)` but entity lacks annotation TTL | RedisTemplate does not use Repository entity mapping | Set TTL explicitly on the template operation or switch to Repository |
| Lifetime is off by 1,000x | Confusing seconds with milliseconds | Standardize units clearly; inspect with `TTL` and `PTTL` |
| Entity disappears before TTL | Deletion, eviction, or overwritten with different TTL config | Inspect delete paths, `maxmemory`, and actual key accesses |

### Basic inspection commands

```redis
EXISTS checkout-drafts:draft-001
TYPE checkout-drafts:draft-001
HGETALL checkout-drafts:draft-001
TTL checkout-drafts:draft-001
PTTL checkout-drafts:draft-001
INFO memory
```

Inspect the exact entity key rather than inferring from still seeing an index Set or shadow copy. Distinguish the primary key from keys created by the Repository to support mapping and events.

## 12. Hands-On Exercise: Observing a Repository's Fixed TTL

Practice on a learning Redis instance using the `CheckoutDraft` entity with `timeToLive = 30` so you do not have to wait long. Steps:

1. Change the annotation to `@RedisHash(value = "checkout-drafts", timeToLive = 30)`.
2. Use `repository.save(...)` to create an entity with ID `draft-demo`.
3. Run `TTL checkout-drafts:draft-demo`; note the value around 30 seconds.
4. Call `repository.findById("draft-demo")` a few times and watch the TTL continue to decrease.
5. Before it expires, modify `note` and call `repository.save(...)`; observe the TTL reset near 30 seconds.
6. Without saving again, wait past the deadline and verify `findById(...)` returns empty and `TTL` returns `-2`.
7. Try saving an entity again with the same ID; observe Redis creating a new TTL lifecycle.

You can use the following snippet:

```java
CheckoutDraft draft = new CheckoutDraft(
        "draft-demo", "customer-demo", "Created"
);

repository.save(draft);

// After some time:
CheckoutDraft existing = repository.findById("draft-demo")
        .orElseThrow();
existing.changeNote("Updated");
repository.save(existing);
```

**Self-check questions:**

- Why does `findById` not reset the TTL back to 30 seconds?
- Why can `save` change the expiration deadline?
- Once the Redis Hash has expired, is it guaranteed that every secondary index Set disappears immediately?
- If the requirement is "exactly 30 minutes from creation," what needs to change so `save` does not accidentally renew it?

## 13. Principles for Production Adoption

When implementing fixed TTLs with Redis Repositories, choose lifetimes based on the **business lifecycle**, design consistent write paths through the Repository, and verify the TTL directly on the real key. Keep in mind that re-saving an entity resets expiration, whereas normal reads do not automatically renew it.

If the entity uses `@Indexed` or the application relies on `RedisKeyExpiredEvent`, also account for keyspace notifications, potential missed events, shadow copies, and index cleanup needs. For mandatory obligations such as billing, transaction recording, document issuance, or events that must not be lost, do not use Redis expiration events as the sole execution mechanism.

**Key takeaway:** `@RedisHash(timeToLive = 1800)` defines a class-level fixed TTL for entities saved using **Spring Data Redis Repository**. The Repository applies expiration to the entity's Redis key when saving; Redis decides when the key expires; the application must handle the fact that the entity may no longer exist and must design its own renewal or deadline policy if business requirements are more complex.

## References

- [Spring Data Redis — Time To Live](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html): `@RedisHash(timeToLive)`, `@TimeToLive`, and expiration event mechanics.
- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html): entity lifecycle and Repository components.
- [Spring Data Redis — Secondary Indexes](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/indexes.html): how Repositories manage secondary indexes.
- [Redis — EXPIRE](https://redis.io/docs/latest/commands/expire/): setting an expiration on a Redis key.
- [Redis — TTL](https://redis.io/docs/latest/commands/ttl/): reading remaining time in seconds and special return values.
- [Redis — Keyspace Notifications](https://redis.io/docs/latest/develop/pubsub/keyspace-notifications/): how Redis emits notifications on key expiration and Pub/Sub limitations.
