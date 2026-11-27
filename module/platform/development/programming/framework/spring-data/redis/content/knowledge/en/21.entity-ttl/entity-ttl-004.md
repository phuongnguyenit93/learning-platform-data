# Interaction Between Save, Entity Updates, and Time To Live in Spring Data Redis

## 1. Entity TTL: why can a save operation change the expiration time?

In Spring Data Redis, we commonly store an **entity** as a Redis Hash through a repository. Entities such as temporary login sessions, unpaid shopping carts, order drafts, or verification codes should not live forever. Redis supports **TTL (*Time To Live*)** so a key expires automatically after a duration.

However, TTL is not just a property set once when data is created. When an application calls `save`, updates an entity, modifies a field in Redis, or writes the same ID again, **the time to live can be preserved, reset, or removed**, depending on the API and TTL configuration.

For example:

```text
09:00  Create draft with 10-minute TTL → expected expiration at 09:10
09:06  User edits content and application calls save(...)
09:10  Has the draft expired or not?
```

The answer depends on the intended policy:

- **Sliding expiration:** new activity is allowed to renew the lifetime; the draft may expire at 09:16.
- **Absolute/fixed deadline from creation:** despite editing at 09:06, the draft still expires around 09:10.
- **Update data only, without changing expiration:** requires an update path that preserves the Redis key's remaining TTL.

This lesson examines the relationship between `CrudRepository.save`, `@RedisHash(timeToLive = ...)`, `@TimeToLive`, partial updates, and Redis TTL commands. The goal is to choose expiration behavior intentionally while avoiding accidental data resurrection or extension.

## 2. Redis TTL operates on the key, not on individual fields

In Redis, TTL is attached to **the entire key**. If an entity maps to a hash at key `demo:draft:d-1001`, the fields `title`, `content`, and `ownerId` share the single expiration time of that key.

```text
Key: demo:draft:d-1001
Type: hash

  id       → d-1001
  title    → Checkout draft
  content  → Draft in progress
  ownerId  → user-42

TTL of the whole key: 600 seconds
```

Therefore, if the draft expires, it is not just the `content` field that disappears: the entire key is no longer readable as before.

Commonly used Redis commands:

| Command | Meaning |
|---|---|
| `EXPIRE key seconds` | Sets or changes a key's time to live in seconds |
| `PEXPIRE key milliseconds` | Sets TTL in milliseconds |
| `TTL key` | Reads remaining seconds to live |
| `PTTL key` | Reads remaining milliseconds to live |
| `PERSIST key` | Removes expiration so the key stays until deleted another way |
| `DEL key` / `UNLINK key` | Deletes the key regardless of TTL |

Meaning of `TTL` return values:

- **0 or greater**: key has an expiration; the number is remaining time in seconds.
- **`-1`**: key exists but has no expiration.
- **`-2`**: key no longer exists.

Example using Redis CLI:

```redis
HSET demo:draft:d-1001 title "Draft"
EXPIRE demo:draft:d-1001 600
TTL demo:draft:d-1001
```

If `TTL` was just set, the result will be near 600 seconds and then count down. Redis does not promise millisecond-exact key removal, but once expired, read operations no longer treat the key as valid data.

**Distinguishing TTL from business time:** TTL is a storage lifecycle mechanism. Rules like "an order cannot be paid after 10 minutes" may also require an `expiresAt` field and validation at the business layer; relying solely on a key-expired event to trigger critical actions is insufficient.

## 3. Declaring a fixed TTL with @RedisHash

Spring Data Redis Repository supports setting a default entity TTL using `@RedisHash(timeToLive = ...)`.

**`OrderDraft.java`**

```java
package com.example.demo.redis;

import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash(value = "demo:draft", timeToLive = 600)
public class OrderDraft {

    @Id
    private String id;

    private String ownerId;

    private String content;

    public OrderDraft() {
    }

    public OrderDraft(String id, String ownerId, String content) {
        this.id = id;
        this.ownerId = ownerId;
        this.content = content;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getOwnerId() {
        return ownerId;
    }

    public void setOwnerId(String ownerId) {
        this.ownerId = ownerId;
    }

    public String getContent() {
        return content;
    }

    public void setContent(String content) {
        this.content = content;
    }
}
```

Meaning:

- `@RedisHash(value = "demo:draft")`: the entity's keyspace.
- `timeToLive = 600`: default TTL of **600 seconds**, equal to 10 minutes, when the repository persists the entity under this policy.
- `@Id`: identifier; for example, ID `d-1001` maps to key `demo:draft:d-1001`.
- Regular fields like `content` do not automatically receive independent TTLs.

Repository:

**`OrderDraftRepository.java`**

```java
package com.example.demo.redis;

import org.springframework.data.repository.CrudRepository;

public interface OrderDraftRepository
        extends CrudRepository<OrderDraft, String> {
}
```

When Spring Data Redis Repositories are enabled, the application can call:

```java
OrderDraft draft = new OrderDraft(
        "d-1001",
        "user-42",
        "Draft content"
);

repository.save(draft);
```

The repository maps the object to Redis and sets the key's lifetime according to the entity configuration.

### Does saving again set a new TTL?

**For an entity with a fixed TTL from `@RedisHash(timeToLive = 600)`, saving again usually reapplies the 600-second window**, so the expiration time is recalculated from that save.

Example in an environment where no other task modifies the key:

```text
09:00:00  save(draft)          TTL near 600s  → expires around 09:10
09:06:00  edit content
09:06:01  save(draft)          TTL near 600s  → expires around 09:16
09:10:00  key still exists
09:16:01  key may have expired
```

This is the right behavior if the convention is **each save renews the lifetime**.

It is not appropriate if the deadline must remain fixed from order creation. In that case, choose a different design rather than expecting `save` to automatically keep the previous write's remaining TTL.

## 4. Per-entity flexible TTL with @TimeToLive

If each record needs a different TTL, Spring Data Redis supports the `@TimeToLive` annotation on a numeric property or a method.

Example draft whose TTL is decided by business logic:

**`VariableTtlDraft.java`**

```java
package com.example.demo.redis;

import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.TimeToLive;

@RedisHash("demo:variable-draft")
public class VariableTtlDraft {

    @Id
    private String id;

    private String content;

    @TimeToLive
    private Long ttlSeconds;

    public VariableTtlDraft() {
    }

    public VariableTtlDraft(
            String id,
            String content,
            Long ttlSeconds
    ) {
        this.id = id;
        this.content = content;
        this.ttlSeconds = ttlSeconds;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getContent() {
        return content;
    }

    public void setContent(String content) {
        this.content = content;
    }

    public Long getTtlSeconds() {
        return ttlSeconds;
    }

    public void setTtlSeconds(Long ttlSeconds) {
        this.ttlSeconds = ttlSeconds;
    }
}
```

Repository for this entity:

```java
package com.example.demo.redis;

import org.springframework.data.repository.CrudRepository;

public interface VariableTtlDraftRepository
        extends CrudRepository<VariableTtlDraft, String> {
}
```

Saving a draft that lives 5 minutes:

```java
VariableTtlDraft draft = new VariableTtlDraft(
        "d-2001",
        "Temporarily stored content",
        300L
);

variableTtlDraftRepository.save(draft);
```

With `@TimeToLive` on a numeric property, its value determines the time to live. The default unit is **seconds**; if you want to specify it explicitly, Spring Data Redis versions support:

```java
import java.util.concurrent.TimeUnit;
import org.springframework.data.redis.core.TimeToLive;

@TimeToLive(unit = TimeUnit.SECONDS)
private Long ttlSeconds;
```

Do not declare `@TimeToLive` on **both a property and a getter method** on the same entity. These two approaches are mutually exclusive alternatives; declaring both creates conflicting TTL configuration.

### How do property TTL and class-annotation TTL differ?

| Configuration approach | Characteristics | When to use |
|---|---|---|
| `@RedisHash(timeToLive = 600)` | Fixed TTL for the entity class on every persist | All drafts share the same renewal-on-save policy |
| `@TimeToLive private Long ttlSeconds` | TTL taken dynamically from each object | Each draft has a different lifetime |
| `@TimeToLive` on a method | TTL computed on demand from the method's result | Lifetime policy depends on entity logic |
| Explicit Redis `EXPIRE` | Controls TTL outside the repository | Need to adjust expiration in a separate operation; must understand interaction with the next save |

To avoid confusion, the examples in this lesson use `@RedisHash(timeToLive = ...)` **or** `@TimeToLive` per entity, rather than combining both into a harder-to-reason-about policy.

## 5. Common pitfall: reading an entity with @TimeToLive and re-saving it

`@TimeToLive` on a **property** has an important behavior: when the repository reads an entity from Redis, Spring Data can populate that property with **the key's actual remaining TTL** by reading `TTL` or `PTTL`.

Suppose we create an entity:

```java
variableTtlDraftRepository.save(
        new VariableTtlDraft("d-2001", "Draft", 300L)
);
```

After about 120 seconds:

```java
VariableTtlDraft loaded =
        variableTtlDraftRepository.findById("d-2001")
                .orElseThrow();

System.out.println(loaded.getTtlSeconds());
```

The read `ttlSeconds` value may be only around **180 seconds**. This is not the original 300-second TTL stored permanently as historical metadata, but the **remaining time to live** at read time.

If right afterward you modify the content:

```java
loaded.setContent("Content updated");
variableTtlDraftRepository.save(loaded);
```

then the `save` uses the TTL value on the object. If that value is still around 180 seconds, the key continues with an expiration near 180 seconds from the save; it **does not automatically revert to 300 seconds** just because the method is `save`.

### Two different business intents

**Intent A — do not renew when only editing content:**

```java
VariableTtlDraft loaded =
        variableTtlDraftRepository.findById("d-2001")
                .orElseThrow();

loaded.setContent("Edited without intentional renewal");
variableTtlDraftRepository.save(loaded);
```

The TTL property read from Redis helps keep the expiration relatively close to the old deadline. However, this **does not guarantee preserving the exact deadline**: time elapsed between read and write, TTL unit rounding, and concurrent writes still introduce drift. For an exact deadline, store an independent `expiresAt` timestamp and apply corresponding enforcement.

**Intent B — renew for a full 5 minutes on every edit:**

```java
VariableTtlDraft loaded =
        variableTtlDraftRepository.findById("d-2001")
                .orElseThrow();

loaded.setContent("Edited and renewed");
loaded.setTtlSeconds(300L);

variableTtlDraftRepository.save(loaded);
```

Here, we **explicitly reset the TTL property** before calling `save`. The new TTL is clearly established as 300 seconds.

**Practical lesson:** when using `@TimeToLive` on a property, do not call `save` on a freshly read entity without checking the TTL property's value; that value may be the **remaining TTL**, no longer the configuration from when the entity was created.

## 6. Comparing save, direct updates, and Redis commands with respect to TTL

Redis has specific TTL rules for each type of operation. Operations that modify data on **the same key** do not necessarily strip the TTL.

For example, with a key that has a 600-second TTL:

```redis
HSET demo:draft:d-1001 content "Old version"
EXPIRE demo:draft:d-1001 600
TTL demo:draft:d-1001
```

Editing a field with `HSET`:

```redis
HSET demo:draft:d-1001 content "New version"
TTL demo:draft:d-1001
```

A regular `HSET` **preserves the key's running TTL**: it neither resets it to 600 seconds nor makes the key persistent.

Comparison:

| Operation | TTL behavior to understand |
|---|---|
| `repository.save(entity)`, entity with fixed 600s TTL | Repository persists and applies the entity's TTL policy; typically recreates the 600-second window |
| `repository.save(entity)`, entity with `@TimeToLive` property | Applies the TTL value currently on the object (which may be remaining TTL after a read) |
| `HSET key field value` | Typically preserves the existing key's TTL |
| `EXPIRE key 300` | Changes the key's TTL to roughly 300 seconds from invocation |
| `PERSIST key` | Removes the expiration time |
| `DEL key` / `UNLINK key` | Deletes the key immediately or via Redis's async memory reclamation |
| Regular `SET key value` | Overwrites key content and typically clears old TTL unless a TTL-preserving option is used; can also change data type |
| Entity expires naturally | Redis removes the primary key; subsequent `findById` no longer finds it |

**Do not use `SET` to update a repository's Redis Hash.** `SET` writes a string value onto the key and can replace the hash, preventing the repository from reading the entity properly. When updating a field via low-level Redis operations, `HSET` matches the data type, though synchronization of repository-managed indexes and metadata remains a concern.

### Why does repository.save differ from HSET?

Redis Repositories operate at the **entity level**, including mapping, data writes, TTL handling, and potentially index updates. `HSET` is purely a field-level Redis operation. Therefore, although both can modify a field inside a hash, their effects on TTL and auxiliary structures are not automatically identical.

If a project uses a repository to manage entities and indexes, standardize on the official update path for business-meaningful changes.

## 7. Full updates with save vs. partial updates with PartialUpdate

With a repository, the simplest pattern is:

```java
OrderDraft draft = repository.findById("d-1001")
        .orElseThrow();

draft.setContent("Updated content");
repository.save(draft);
```

This is a **read, mutate object, then save** flow. If using `@RedisHash(timeToLive = 600)`, the `save` interacts with TTL according to the entity's 600-second policy.

In some cases, you only want to modify a few attributes without **rewriting the entire entity**. Spring Data Redis provides `PartialUpdate` to declare property-level changes.

Example for an entity with a `@TimeToLive` property like `VariableTtlDraft`:

```java
import org.springframework.data.redis.core.PartialUpdate;
import org.springframework.data.redis.core.RedisKeyValueTemplate;

// redisKeyValueTemplate is injected by Spring:
PartialUpdate<VariableTtlDraft> update =
        new PartialUpdate<>("d-2001", VariableTtlDraft.class)
                .set("content", "Edited content");

redisKeyValueTemplate.update(update);
```

This updates the `content` property via the partial update API without needing to load the entire entity in the service layer.

### When you want to intentionally update TTL

`PartialUpdate` supports the `refreshTtl(true)` option:

```java
PartialUpdate<VariableTtlDraft> update =
        new PartialUpdate<>("d-2001", VariableTtlDraft.class)
                .set("ttlSeconds", 600L)
                .refreshTtl(true);

redisKeyValueTemplate.update(update);
```

Meaning: modify the TTL property and instruct Redis to update the **expiration on the Redis server** to the new value. This makes TTL renewal explicit when using the partial update mechanism.

You can update both data and TTL in a single call:

```java
PartialUpdate<VariableTtlDraft> update =
        new PartialUpdate<>("d-2001", VariableTtlDraft.class)
                .set("content", "Edited draft")
                .set("ttlSeconds", 900L)
                .refreshTtl(true);

redisKeyValueTemplate.update(update);
```

**Note:** `refreshTtl(true)` is an explicit choice requesting expiration refresh, not a flag to enable blindly on every update. When only changing a field and wanting to preserve the running deadline, avoid accidentally resetting TTL. Also distinguish `RedisKeyValueTemplate`'s partial update API from `CrudRepository.save`; the two write paths have different purposes and TTL interactions.

### When should you be cautious with partial updates?

- If the updated field has `@Indexed`, secondary index changes must be accounted for; use the proper mapping-aware API rather than raw `HSET`.
- Updating nested properties, maps, or collections may still require extra reads or Redis operations; do not assume partial updates are always faster.
- If a key expired right before the update, the operation must decide **whether recreating the key is allowed**; do not assume every update command automatically rejects nonexistent keys.
- Spring Data Redis versions can differ in behavioral details; verify against the library version in use when choosing a TTL API.

## 8. Designing TTL policies: renew on save or keep the deadline?

The same entity with two different expiration policies leads to two different designs.

### 8.1. Sliding TTL: the draft stays alive while the user is active

Suppose every user edit should extend the lifetime by another 10 minutes.

```text
Created at 09:00 → expires 09:10
Edited  at 09:06 → expires 09:16
Edited  at 09:13 → expires 09:23
```

For this goal, an entity with `@RedisHash(timeToLive = 600)` or a `@TimeToLive` property reassigned to 600 before saving may be suitable.

**Service example with fixed TTL:**

```java
package com.example.demo.service;

import com.example.demo.redis.OrderDraft;
import com.example.demo.redis.OrderDraftRepository;
import org.springframework.stereotype.Service;

@Service
public class DraftEditor {

    private final OrderDraftRepository repository;

    public DraftEditor(OrderDraftRepository repository) {
        this.repository = repository;
    }

    public OrderDraft updateContent(String id, String content) {
        OrderDraft draft = repository.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException("Draft not found")
                );

        draft.setContent(content);

        // With @RedisHash(timeToLive = 600),
        // save reapplies the TTL policy.
        return repository.save(draft);
    }
}
```

Keep in mind: calling `save` repeatedly on the same entity does not just incur write overhead; it alters the key's lifecycle. If the system invokes `save` from a frequent synchronization job, the draft may stay alive longer than desired even after the user stops being active.

### 8.2. Absolute deadline: expire at an immutable point in time

For example, a verification code is valid only until 09:10 regardless of how many times auxiliary details are updated.

You can store the expiration time as a business value, such as `expiresAt`, and whenever persisting again, **compute TTL from the current time to the deadline**. Idea:

```text
expiresAt = 09:10:00

09:00:00  TTL approximately 600s
09:06:00  TTL approximately 240s
09:09:30  TTL approximately  30s
09:10:01  Overdue: reject update
```

An entity using `@TimeToLive` can add an `expiresAt` property:

```java
@RedisHash("demo:fixed-deadline-draft")
public class DeadlineDraft {

    @Id
    private String id;

    private String content;

    private Instant expiresAt;

    @TimeToLive
    private Long ttlSeconds;

    // Appropriate constructor, getters, and setters.
}
```

In the service, before saving you can use an injected `Clock`:

```java
Instant now = clock.instant();
Duration remaining = Duration.between(now, draft.getExpiresAt());

if (remaining.isZero() || remaining.isNegative()) {
    throw new IllegalStateException("Draft has expired");
}

long ttlSeconds = remaining.getSeconds();

if (ttlSeconds < 1L) {
    throw new IllegalStateException("Draft is about to expire / expired in seconds");
}

draft.setTtlSeconds(ttlSeconds);
repository.save(draft);
```

This example requires importing `java.time.Clock`, `java.time.Duration`, and `java.time.Instant`. It is a **service logic sketch**, assuming `draft` was obtained from a trusted source and `clock` was provided. When millisecond-exact deadlines are required, choose the appropriate unit and rounding policy.

**Important:** computing remaining time and calling `save` is not atomic with respect to the clock and Redis. If writes can be delayed or run concurrently, add deadline/version checks at the write point matching business requirements. For verification codes, the deadline must continue to be checked during code verification even if the key still exists in Redis.

### 8.3. Do not renew when updating auxiliary information

For example, when only recording a processing count or updating a technical field while preserving the key's TTL. You can consider `PartialUpdate` without requesting a TTL refresh, or an appropriate Redis Hash operation when indexes and mappings are controlled.

Do not call `repository.save` on an entity with a fixed TTL if the intent is to preserve the **exact** current expiration timestamp: a save may reapply the TTL policy and extend the key.

## 9. Experimenting with reading TTL before and after save

You can inspect TTL using `StringRedisTemplate` in a test environment. The snippet only reads TTL without directly modifying the repository-managed hash.

```java
package com.example.demo.service;

import java.util.concurrent.TimeUnit;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

@Component
public class DraftTtlInspector {

    private final StringRedisTemplate redis;

    public DraftTtlInspector(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Long remainingSeconds(String draftId) {
        String key = "demo:draft:" + draftId;
        return redis.getExpire(key, TimeUnit.SECONDS);
    }
}
```

Example sequence of operations:

```java
OrderDraft draft = repository.save(
        new OrderDraft("d-1001", "user-42", "First time")
);

Long ttl1 = inspector.remainingSeconds("d-1001");
// Near 600 seconds right after save.

draft.setContent("Second time");
repository.save(draft);

Long ttl2 = inspector.remainingSeconds("d-1001");
// Near 600 seconds again after re-save with fixed TTL.
```

To clearly observe TTL decreasing and then increasing again, **take the two readings with real elapsed time between them**; calling them back-to-back can look identical. Do not assert `TTL == 600` as a strict condition because execution time, network latency, and Redis rounding can shift the returned seconds slightly.

### Checking with Redis CLI

After the repository saves ID `d-1001`:

```redis
TYPE demo:draft:d-1001
HGETALL demo:draft:d-1001
TTL demo:draft:d-1001
PTTL demo:draft:d-1001
```

To observe the renewal policy, note the timestamp/TTL, perform a `save` through the application, then read `TTL` again.

Distinguish two data sources:

- **Server TTL** obtained via `TTL` or `PTTL` is the current state of the Redis key.
- **The `@TimeToLive` property** on the Java object may reflect the TTL read at an earlier moment.

If you need to decide whether editing should be allowed near expiration, reading TTL alone beforehand does not guarantee the key still exists when the write runs. Write conditions must account for concurrent changes.

## 10. What happens when saving an entity whose TTL has already expired?

Suppose:

```text
09:00  save(entity id = d-1001)
09:10  Redis expires key demo:draft:d-1001
09:12  A worker still holding the old Java object calls save(...)
```

A standard `repository.save(entity)` call is a **save-by-ID** operation. If the key was removed due to TTL, the repository can **recreate the key** and apply the entity's TTL just like a fresh save.

This is a critical scenario for data with strict validity windows:

- A user saves an open page after the session has expired.
- A slow worker writes the result of an overdue task.
- An expired draft or verification code is resurrected by a late update.
- Two tasks hold different versions of an object and the later save brings the key back.

**Repository.save does not mean "update only if the key still exists and has not expired."**

### Solutions when resurrecting data is forbidden

One or more measures can be applied:

1. Separate **creation** flows from **valid update** flows in the service. On edits, read the entity first and reject if it no longer exists.
2. Store `expiresAt` in a trusted source and validate the business deadline.
3. If writing after expiration must be strictly prevented under concurrency, use an **atomic conditional operation in Redis** tailored to your design (e.g., Lua script / Redis Function) instead of separate "EXISTS then SAVE" calls.
4. Use a version/token or job status to discard results from stale tasks.

Simply checking `existsById` then calling `save` **is not atomic**: the key can expire between the two commands. Depending on criticality, allowing a draft cache to be recreated might be acceptable; verification codes or financial transactions require stricter rules.

## 11. TTL and concurrent updates

Consider two workers reading the same entity that has a 300-second TTL:

```text
09:00  Entity exists, TTL 300s
09:01  Worker A reads entity (remaining TTL near 240s)
09:02  Worker B reads entity (remaining TTL near 180s)
09:03  Worker B sets new TTL 300s and saves
09:04  Worker A saves stale copy with ttlSeconds near 240s
```

The last save can **overwrite data and alter the TTL** to the value on Worker A's object. Actual write order matters more than read order. Even on a single Redis key, two workers can still hit a *lost update*.

Another variation:

- Worker A only wants to edit `content`.
- Worker B wants to shorten validity down to 60 seconds.
- If A re-saves the entity with the old TTL after B, B's shortened expiration may be unintentionally altered.

Ways to mitigate this:

| Scenario | Approach |
|---|---|
| Data is purely cache and lost updates are acceptable | Last-write-wins convention, setting TTL per clear policy |
| Independent field updates | Use an appropriate partial update API, avoiding rewriting the whole entity unnecessarily |
| TTL owned by one component | Isolate TTL mutation authority; only that component extends or shortens it |
| Must not write past deadline | Atomic conditional check-and-write in Redis or primary data store |
| Need to prevent lost updates | Apply versioning / conditional write mechanisms supported by your design |
| Multiple services share a keyspace | Standardize model, serialization, TTL, and write methods |

Spring's `@Transactional` does not automatically ensure that two repository calls from different workers avoid lost updates or enforce deadlines accurately. Redis transaction behavior requires explicit configuration and must still consider consistency across auxiliary keys.

## 12. TTL, secondary indexes, and expiration events

When using Spring Data Redis Repository, beyond the primary hash there can be keys supporting indexes and metadata. For example:

```java
import org.springframework.data.redis.core.index.Indexed;

@Indexed
private String ownerId;
```

This index supports querying by `ownerId`, yet **the primary hash's TTL expiring does not mean Redis automatically removes every member from secondary indexes**.

Spring Data Redis provides a mechanism to listen for expiration events to manage the entity lifecycle, including cleaning up leftover index references.

### RedisKeyExpiredEvent and listeners

When appropriately configured, the repository uses Redis keyspace notifications and a listener to receive key-expired events. Spring Data Redis can publish `RedisKeyExpiredEvent` so other parts of the application know an entity expired.

An explicit repository configuration can set the listener mode:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.RedisKeyValueAdapter.EnableKeyspaceEvents;
import org.springframework.data.redis.repository.configuration.EnableRedisRepositories;

@Configuration
@EnableRedisRepositories(
        basePackages = "com.example.demo.redis",
        enableKeyspaceEvents = EnableKeyspaceEvents.ON_STARTUP
)
public class RedisRepositoryConfiguration {
}
```

This is an example when choosing manual repository configuration. If Spring Boot already configures the repository appropriately, do not add redundant configuration unnecessarily.

**Important limitations:**

- Redis Pub/Sub **does not durably store** emitted events. If no suitable listener is active when a key expires, the event can be missed.
- Some managed Redis services disallow applications from changing `notify-keyspace-events` via `CONFIG`; configure and grant permissions per your environment.
- The listener may start at application startup or lazily when an entity with TTL is added; understand which mode is active.
- If expiration events are missed, secondary indexes may retain references to entities that no longer exist.

### Shadow copy (*phantom copy*)

To publish events containing entity content after the primary key expires, Spring Data Redis can store a temporary copy with a later expiration than the original. As described in the reference documentation, this copy typically persists for about **5 minutes** past the original's expiration time.

Implication: even after the primary entity expires, you may still see **auxiliary keys and some associated memory** in Redis. This is not necessarily a memory leak; distinguish primary data, indexes, and event-supporting copies.

If you do not need entity data inside expiration events, consider disabling `shadowCopy` as supported by your Spring Data Redis version. When disabled, expiration events may only carry ID/key information; weigh your business processing needs.

### Do not treat expired events as an infallible business timer

Expiration events help react to data lifecycles, but they do not replace mechanisms requiring guarantees:

- Never missing a task that must be processed.
- Exactly-once processing.
- Executing work at a committed timestamp.
- Maintaining consistent state between Redis and other systems.

For those requirements, use a business deadline and a queue/job mechanism that can be traced, retried, or acknowledged.

## 13. Checking TTL state in the application

A service often wants to distinguish three states:

```text
TTL = -2      Key does not exist
TTL = -1      Key exists without expiration
TTL >= 0      Key has an expiration with N seconds left
```

Example reading TTL:

```java
Long ttl = stringRedisTemplate.getExpire(
        "demo:draft:d-1001",
        java.util.concurrent.TimeUnit.SECONDS
);

if (ttl == null) {
    throw new IllegalStateException("Unable to read TTL");
}

if (ttl == -2L) {
    // Key does not exist: may have been deleted or expired.
} else if (ttl == -1L) {
    // Key exists but has no expiration.
} else {
    // Has TTL: ttl seconds remaining.
}
```

`StringRedisTemplate` is suitable when key names are plain strings and the application actually uses the corresponding keyspace. With templates using custom key serializers, check serializer configuration before manually constructing keys to read TTL.

### What does TTL equal to 0 mean?

`TTL` has second-level resolution, so a key with a very small positive TTL can return 0 even though it has not vanished at the exact instant of the read. When you need finer visibility into expiration, use `PTTL` to view milliseconds.

Do not write logic such as "`ttl == 0` guarantees Redis has already deleted the key." When determining whether updates are permitted, proper conditional write logic is still needed.

### Repository-set TTL vs. TTL changed with EXPIRE

For example:

```redis
EXPIRE demo:draft:d-1001 60
TTL demo:draft:d-1001
```

If the application subsequently calls `repository.save(draft)` on an entity with `@RedisHash(timeToLive = 600)`, the repository's TTL policy may reset the key back near 600 seconds. Therefore, a TTL change made outside the repository is not guaranteed to survive the next entity save.

If you want to shorten a deadline permanently, store the **new policy** where all update paths honor it, rather than sending an isolated `EXPIRE` command while letting `save` flows keep renewing it.

## 14. Common misconceptions

### Misconception 1: "Every field update restarts the TTL"

Incorrect. `HSET` on a Redis Hash with an active expiration normally preserves the running TTL. Conversely, `repository.save` can reapply the entity's TTL policy. The two APIs serve different purposes.

### Misconception 2: "@TimeToLive always holds the initial TTL"

Incorrect when the annotation is on a property and the entity is **read back from Redis**. On read, Spring Data Redis can populate that property with the remaining TTL. To renew for a full duration, explicitly reassign the new TTL before saving.

### Misconception 3: "Calling save means updating only an existing key"

Incorrect. `save` can create or recreate a key by ID. If an entity has expired, an old Java object can still be re-persisted unless the application enforces rules preventing resurrection.

### Misconception 4: "When the hash's TTL expires, all indexes vanish at the same moment"

Not guaranteed. Redis does not directly manage Spring Data's secondary index metadata. Index cleanup depends on repository mechanics and expiration event processing.

### Misconception 5: "Reading TTL then saving preserves the exact deadline"

Not guaranteed. Time elapsed between operations, unit rounding, and concurrent writes can alter the result. If a hard deadline is required, store the timestamp and use appropriate write controls.

### Misconception 6: "PERSIST just refreshes the TTL"

`PERSIST` removes expiration completely. If a flow accidentally calls `PERSIST` on data meant to live a few minutes, the key can live indefinitely until deleted. Distinguish `PERSIST` from `EXPIRE`.

### Misconception 7: "Simply adding TTL to the entity causes old data to expire automatically"

Adding `@RedisHash(timeToLive = 600)` in source code does not cause previously saved keys that **have not been rewritten via the repository** to immediately gain a TTL. You need a migration strategy, explicit TTL assignment for legacy data, or an appropriate data cleanup policy.

## 15. Decision table for common operations

| Goal | Choice and caveats |
|---|---|
| Every record lives 10 minutes from the last `save` | `@RedisHash(timeToLive = 600)` |
| Each entity has its own TTL | `@TimeToLive` property or method |
| Read entity and renew for a full 5 minutes | Reassign `ttlSeconds = 300L` before saving |
| Edit content without intentionally renewing | Consider `PartialUpdate` without refreshing TTL; avoid re-saving with fixed TTL if deadline must hold |
| Change expiration separately via TTL property | `PartialUpdate.set("ttlSeconds", ...)` with `refreshTtl(true)` when using this API |
| Enforce hard deadline from creation | Store `expiresAt` and compute TTL from deadline; control concurrency where needed |
| Prevent updating an expired entity | Atomic conditional write control if accuracy is mandatory |
| Perform work after key expiration | Consider keyspace notifications, but use durable jobs if nothing may be missed |
| Query by secondary index after expiration | Ensure expiration handling is configured and plan stale-index cleanup |
| Change TTL directly with `EXPIRE` | Expect the next `save` to potentially reapply the entity's TTL |

## 16. Timeline practice questions

**Scenario A.** An entity has `@RedisHash(timeToLive = 600)`, is saved at 09:00, and saved again at 09:08. Assuming no other tasks intervene, roughly when is the new expiration?

**Explanation:** the second save applies the 600-second TTL policy. The key will usually expire around 09:18, roughly 10 minutes after the second save.

**Scenario B.** An entity using `@TimeToLive private Long ttlSeconds` is saved with 600 seconds. After 5 minutes, the repository reads it back; the TTL property is near 300. The application calls `save` without changing the TTL property.

**Explanation:** the save uses the TTL value on the object, which may be around 300 seconds; it does not automatically revert to 600. To renew for a full 600 seconds, reassign `ttlSeconds`.

**Scenario C.** A Redis hash has a 100-second TTL, then a field is updated with `HSET`. Will the TTL return to 600 seconds?

**Explanation:** `HSET` does not inspect Java TTL annotations; it normally preserves the Redis key's TTL. It does not automatically reset it to 600.

**Scenario D.** A draft expires, yet a worker holding an old object calls `repository.save`.

**Explanation:** `save` can recreate the key. If business rules forbid this, enforce creation/update conditions and write-time checks rather than relying solely on TTL.

**Scenario E.** The primary key expires while the application is down. After restart, queries by index still show traces of the old ID.

**Explanation:** expiration events over Redis Pub/Sub can be missed, leaving secondary index cleanup incomplete. Check listener setup and have an index repair strategy.

**Scenario F.** An entity has an absolute deadline at 12:00; at 11:59:45 the application still has permission to edit it. Is resetting 600 seconds of TTL on every save correct?

**Explanation:** no. Resetting 600 seconds would exceed the deadline. Apply only the **remaining** TTL until 12:00 and reject any disallowed operations past the deadline.

## 17. Practical guidelines for real systems

When implementing TTL for Spring Data Redis entities, align on four decisions before writing services:

1. **When does TTL count from?** From creation, from last write, from valid user activity, or from a business deadline?
2. **Who is allowed to change TTL?** Every `save`, only a dedicated renewal operation, or a specialized service?
3. **Once a key expires, can the same ID be recreated?** If not, the application needs anti-late-write guards, not just a single existence check.
4. **Are there metadata/indexes or tasks depending on expiry events?** If so, account for keyspace notifications, shadow copies, missed events, and recovery plans.

Answering these questions upfront avoids two opposite classes of bugs: **data expiring prematurely and losing valid state**, or **data being unintentionally extended or resurrected in violation of business rules**.

## References

- [Spring Data Redis — Time To Live](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html)
- [Spring Data Redis — Persisting Partial Updates](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/usage.html)
- [Spring Data Redis — PartialUpdate API](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/core/PartialUpdate.html)
- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html)
- [Redis — EXPIRE](https://redis.io/docs/latest/commands/expire/)
- [Redis — TTL](https://redis.io/docs/latest/commands/ttl/)
- [Redis — Keyspace notifications](https://redis.io/docs/latest/develop/pubsub/keyspace-notifications/)
