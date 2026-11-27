# Impact of `save` on Existing Hash Contents in Redis Repositories

## 1. The Question: Does `save` Preserve Old Fields?

When using **Spring Data Redis Repository**, an entity is typically stored as a Redis Hash with a key of the form `<keyspace>:<id>`. The `repository.save(entity)` method supports saving a new entity or re-saving an entity that already has an ID.

A common point of confusion is: **re-saving an existing entity is not equivalent to updating only the changed fields of the Hash**. When replacing an existing entity, the default Redis Repository mechanism **deletes the old Hash contents and recreates the Hash from the mapped properties of the entity being saved**. Any fields that existed only in Redis and do not appear in the newly mapped data will be lost.

Brief example:

```text
Before save:
profiles:42
  id          = 42
  displayName = Minh
  email       = minh@example.test
  externalTag = VIP       <- field added directly into Redis

Entity passed to save:
  id          = 42
  displayName = Minh New
  email       = null

After repository.save(entity):
profiles:42
  _class      = ...Profile
  id          = 42
  displayName = Minh New

email       -> no longer a field in the Hash
externalTag -> no longer a field in the Hash
```

This is the behavior of **Redis Repositories and object-to-hash mapping**, not a general rule for all Redis operations. The Redis `HSET` command itself only overwrites specified fields, whereas `repository.save` operates at the entity level and may issue multiple Redis commands.

## 2. How Does a Redis Repository Convert an Entity into a Hash?

Spring Data Redis uses `RedisConverter` (typically `MappingRedisConverter`) to convert Java properties into Redis Hash fields.

Consider the entity:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash("profiles")
public class Profile {

    @Id
    private String id;

    private String displayName;
    private String email;

    public Profile() {
    }

    public Profile(String id, String displayName, String email) {
        this.id = id;
        this.displayName = displayName;
        this.email = email;
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public String getDisplayName() { return displayName; }
    public void setDisplayName(String displayName) { this.displayName = displayName; }

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
}
```

Repository:

```java
import org.springframework.data.repository.CrudRepository;

public interface ProfileRepository extends CrudRepository<Profile, String> {
}
```

The call:

```java
repository.save(new Profile("42", "Minh", "minh@example.test"));
```

creates a Hash in the `profiles` keyspace with ID `42`, corresponding to Redis key `profiles:42`. Typical representation:

```text
HGETALL profiles:42

_class      = com.example.Profile
id          = 42
displayName = Minh
email       = minh@example.test
```

The full name in `_class` depends on the Java package and type mapping configuration. If `@TypeAlias` is used, the type discriminator value may differ. The `_class` field is metadata managed by the mapper, not a user-added property.

For complex properties, the mapper may flatten them into fields like `address.city` and `address.country`. For collections and maps, field names can also include paths and indices. Consequently, "replacing the entire Hash" also affects nested fields: elements or properties no longer mapped will not be retained either.

## 3. Mechanism When Saving an Existing Entity

Spring Data Redis documentation illustrates the **replace existing** case with a sequence of operations conceptually like:

```redis
DEL   profiles:42
HMSET profiles:42 _class com.example.Profile id 42 displayName "Minh New"
```

This is an **illustrative command diagram**; the exact commands and how they are sent may vary by Spring Data Redis version, mapper, indexes, and TTLs. The key takeaway is that the old Hash is removed to avoid retaining fields no longer represented in the new entity, and the Hash is then rewritten.

The Repository may also update auxiliary structures, such as the keyspace ID set and secondary indexes for `@Indexed` properties. Hence, a single `save` is not necessarily a single `HSET` and should not be treated as an atomic Redis field update.

Comparing operations:

| Operation | Effect on Redis Hash | Unmentioned fields |
| --- | --- | --- |
| `HSET profiles:42 displayName "Minh New"` | Writes only the `displayName` field | Preserved if the Hash exists |
| `repository.save(profile)` with existing ID | Rewrites the full representation of the entity | May be deleted if not present in the mapping output |
| `PartialUpdate` for one property | Intentionally updates part of the data managed by Redis Repository | Properties not included in the update are generally preserved |
| `repository.deleteById("42")` | Deletes the entity from Redis Repository | Entire entity Hash is deleted |

This differs from the common mental model in SQL ORMs: do not assume calling `save` merely generates a statement equivalent to `UPDATE ... SET displayName = ...`.

## 4. Detailed Illustration: Manually Added Fields Are Lost

Suppose a profile was created via the repository. Another service or admin tool adds unmapped fields:

```redis
HSET profiles:42 externalTag "VIP"
HSET profiles:42 reviewStatus "APPROVED"
HGETALL profiles:42
```

The Hash may contain:

```text
_class      = com.example.Profile
id          = 42
displayName = Minh
email       = minh@example.test
externalTag = VIP
reviewStatus= APPROVED
```

Then the application calls:

```java
Profile p = repository.findById("42").orElseThrow();
p.setDisplayName("Minh New");
repository.save(p);
```

Even though the application read the entity first, `findById` only reconstructs the object from properties known to the mapper. `externalTag` and `reviewStatus` do not become properties of `Profile`, so they are not automatically carried into the next `save`.

Expected result:

```text
_class      = com.example.Profile
id          = 42
displayName = Minh New
email       = minh@example.test

externalTag  -> lost
reviewStatus -> lost
```

**Consequence:** multiple components writing to the same Redis Hash via two different mechanisms (Repository and `HashOperations`/`redis-cli`) can accidentally erase each other's data. Even an "auxiliary" field is still data that requires clearly designed ownership.

### Entity Fields Set to `null`

Even if a field is defined in the class, it can disappear if its value is not emitted by the mapper into the new Hash.

```java
repository.save(new Profile("42", "Minh New", null));
```

With default mapping for simple properties, `email = null` does not produce an `email` field in the new Hash. Because the old Hash was deleted, the previous email value is gone.

This matters greatly for update DTOs with missing fields:

```java
// Example NOT suitable when intending to change only displayName:
Profile p = new Profile(request.id(), request.displayName(), null);
repository.save(p);
```

If `null` is used to mean "the user did not send an email", calling `save` like this can cause email loss. The application must distinguish "property omitted" from "delete property".

### `@Transient` or Unmapped Properties

A field marked `@Transient` is not persisted by standard mapping. If a field with the same name was previously added directly to the Hash, the next `save` may also delete it. Renaming properties, changing converters, removing fields from a class, or altering nested class structures can have a similar effect.

## 5. How Are the Old Hash, TTL, and Auxiliary Structures Affected?

| Component | Impact to consider when re-saving an entity |
| --- | --- |
| Mapped field with a value | Rewritten from the current object, potentially overwriting the old value. |
| Mapped field that no longer produces a value | Does not appear in the new Hash; the old value is not kept just because it existed earlier. |
| Manually written, unmapped field | Lost when the Hash is recreated. |
| Nested fields or collection elements | Paths no longer produced by the mapper disappear. |
| `@Indexed` secondary index | The Repository updates auxiliary sets/indexes to match the new entity state; do not manually edit indexed fields with `HSET` and expect indexes to stay synced. |
| Redis key TTL | Deleting the old Hash also clears the TTL attached to the old key. Whether the new Hash has a TTL depends on the TTL policy applied by the Repository during save. |
| Changes from other requests/workers | May be lost if that worker wrote first and a stale entity is later `save`d. |

### TTL Analysis

Redis attaches time-to-live to the **key**, not to individual Hash fields. When the old key is `DEL`eted, the old expiration is lost with it. After the Repository creates the new key:

- If the entity has an expiration policy via `@RedisHash(timeToLive = ...)` or `@TimeToLive`, the Repository can issue `EXPIRE` to set a lifespan for the saved record.
- Without a corresponding TTL policy, you cannot expect an expiration previously placed on the old key by an external tool to be preserved automatically.
- If `@TimeToLive` is on a property read from Redis, the property may reflect the remaining TTL/PTTL. Understand the unit and value used by the mapper before re-saving; do not assume a save always preserves the exact original expiration timestamp.

Try testing in a dedicated environment:

```redis
EXPIRE profiles:42 120
TTL profiles:42
```

After a `repository.save` with an entity **that has no configured TTL**, check again:

```redis
TTL profiles:42
```

Typically, when a new key is created with no expiration applied, the result is `-1` (key exists with no expiration). If the key does not exist, `TTL` returns `-2`. When a TTL policy is declared on the entity, the result depends on the newly calculated and applied duration.

**Do not equate Redis Repository TTL with Spring Cache TTL.** The two abstractions use different storage mechanisms, so verify the exact write path in use.

### Secondary Indexes

If an entity has:

```java
@Indexed
private String email;
```

The Repository can create indexes by keyspace/field value and manage auxiliary sets to clean up old index entries when replacing the entity. When `email` changes from `a@example.test` to `b@example.test`, the old index entry must be removed and the new one created for queries to remain accurate.

Updating directly with `HSET profiles:42 email ...` does not trigger the Repository's index update mechanism. Then lookups by ID can diverge from searches via index-backed finders. Use `save` or `PartialUpdate` when Repository-managed structures must stay synchronized.

## 6. Choosing the Right Update Approach for Your Needs

### Approach A — Repository Owns the Whole Hash: Read, Modify, `save`

Suitable when all data under the key consists of mapped properties and the application accepts replacing the full entity state.

```java
Profile p = repository.findById("42")
        .orElseThrow(() -> new IllegalArgumentException("Profile not found"));

p.setDisplayName("Minh New");
repository.save(p);
```

With this approach, mapped fields read onto the object are saved back. However, manual fields outside the mapper are still not preserved. Nor does this protect against concurrent updates from two workers.

Choose this approach when replacing the entire entity is the explicit goal and a single consistent component owns the Hash.

### Approach B — `PartialUpdate`: Modify Only Changed Properties

Spring Data Redis provides `PartialUpdate` to express setting or deleting individual properties without loading and rewriting the entire entity. This operation goes through `RedisKeyValueTemplate.update(...)`, which supports maintaining indexes and certain related metadata during updates.

Example:

```java
import org.springframework.data.redis.core.PartialUpdate;
import org.springframework.data.redis.core.RedisKeyValueTemplate;

// redisKeyValueTemplate is injected from Spring configuration.
PartialUpdate<Profile> update =
        new PartialUpdate<Profile>("42", Profile.class)
                .set("displayName", "Minh New");

redisKeyValueTemplate.update(update);
```

To explicitly delete a property:

```java
PartialUpdate<Profile> update =
        new PartialUpdate<Profile>("42", Profile.class)
                .del("email");

redisKeyValueTemplate.update(update);
```

In both cases, the update intent is clearer than building an object with missing fields and calling `save`. `PartialUpdate` also supports complex properties, with caveats: nested path updates may not work for properties using custom conversions; setting an entire map may overwrite the old map contents. If TTL adjustment is needed, explicitly consider `refreshTtl(...)` and the entity's expiration metadata.

Use `PartialUpdate` when the data is owned by a Redis Repository but the business operation only alters a few fields. Do not assume partial update acts as a version check or lock against concurrent write conflicts.

### Approach C — `HashOperations`: Updating Fields Directly

If a data group is designed as a Redis Hash managed directly by `RedisTemplate`, you can update a single field directly:

```java
String key = "profile-aux:42";
stringRedisTemplate.opsForHash().put(key, "reviewStatus", "APPROVED");
```

This corresponds to `HSET` and updates only the chosen field without removing other fields in the key. However, operations through `HashOperations` **do not automatically maintain Redis Repository secondary indexes**, do not invoke entity lifecycle callbacks, and do not apply Repository-annotated TTLs.

Do not use `HSET` as a workaround to "keep safe" fields inside a Hash that a Repository will later `save`. A future `save` can still wipe those fields out.

### Approach D — Moving Auxiliary Data to a Separate Redis Key

When two components have different ownership and lifecycles, a clean design is:

```text
profiles:42            # Hash managed by ProfileRepository
profile-aux:42          # Auxiliary Hash managed by another component
```

That way, `repository.save(profile)` replaces `profiles:42` without touching `profile-aux:42`. Clearly define how the auxiliary key is cleaned up when the profile is deleted, its corresponding TTL, and access permissions across components.

If the auxiliary field is genuinely part of the domain entity, another option is to **add it to the mapped model** (for example, a `Map<String, String>`). Even so, you must read and retain the dynamic entries on the object passed to `save`; map entries absent from the object can still be lost on the next Hash replacement.

### Decision Table

| Need | Option to consider | What must be controlled |
| --- | --- | --- |
| Replace full entity state | `repository.save` | Hash and mapped data share a unified ownership source. |
| Change only one entity field | `PartialUpdate` | Indexes, TTL, custom converters, and concurrent operations. |
| Update a plain Hash owned by `RedisTemplate` | `HashOperations.put/putAll` | Manage indexes, TTL, validation, and schema yourself if needed. |
| Another service needs independent metadata | Auxiliary key in its own namespace | Lifecycle coupling, data deletion, and consistency. |
| Guarantee no lost concurrent updates | Version/CAS mechanism or suitable atomic operation | Conflict handling and bounded retries. |

## 7. Why Can `save` Still Cause Lost Concurrent Updates?

Suppose the initial profile is:

```text
displayName = Minh
email       = old@example.test
```

Two tasks read the same version:

```text
T1 reads Profile(id=42, displayName=Minh, email=old@example.test)
T2 reads Profile(id=42, displayName=Minh, email=old@example.test)

T1 changes displayName = Minh New
T2 changes email       = new@example.test

T1 calls repository.save(...)
T2 calls repository.save(...) afterward
```

T2's `save` may recreate the entire Hash from T2's stale object, resulting in:

```text
displayName = Minh                 # T1's change is lost
email       = new@example.test
```

Even though both T1 and T2 modified only a single Java property, both submitted **the full entity state** to save. This is a form of *lost update*. Moreover, the Repository may require multiple commands to manage the hash and indexes; do not treat `save` as a compare-and-swap or transaction guarding every step.

Mitigation options depending on requirements:

- Prefer field-level partial/atomic operations when business logic permits; this narrows the overwrite blast radius though it does not solve all logical conflicts.
- If you require "update only if data has not changed", use a proper optimistic concurrency design: read the current version, check and update atomically via Redis `WATCH`/`MULTI`/`EXEC` or an application-managed Lua script, with retry/conflict policies.
- If multiple fields must change together, design an atomic command or a unified protocol; do not arbitrarily mix half of a step in the Repository and half in `RedisTemplate`.
- Keep loaded objects short-lived; avoid re-saving a stale entity held in memory for minutes after other writers may have modified it.

Redis Repository is a convenient abstraction for persisting entities; it does not automatically make every `save` safe as a patch under multiple writers.

## 8. Observing Behavior in a Test Environment

The following lab is meant for a test Redis instance or a namespace containing no real data.

**Step 1 — Save an entity and inspect the Hash:**

```java
repository.save(new Profile("demo-1", "An", "an@example.test"));
```

```redis
HGETALL profiles:demo-1
TYPE profiles:demo-1
TTL profiles:demo-1
```

Expect `TYPE` to be `hash`; `HGETALL` shows the fields written by the mapper.

**Step 2 — Add a field manually and observe:**

```redis
HSET profiles:demo-1 externalTag "manual"
HGETALL profiles:demo-1
```

**Step 3 — Call `save` with the same ID:**

```java
repository.save(new Profile("demo-1", "An Renamed", "an@example.test"));
```

```redis
HGETALL profiles:demo-1
HEXISTS profiles:demo-1 externalTag
```

Expect `HEXISTS` to return `0` because the `externalTag` field was not in the entity written by the mapper.

**Step 4 — Check the null-field case:**

```java
repository.save(new Profile("demo-1", "An", null));
```

```redis
HEXISTS profiles:demo-1 email
```

Expect `0` under standard mapping: `null` values do not create a new field and the old Hash was replaced.

**Step 5 — Observe updating a single field selectively:**

```java
PartialUpdate<Profile> update =
        new PartialUpdate<Profile>("demo-1", Profile.class)
                .set("displayName", "An - partial update");
redisKeyValueTemplate.update(update);
```

Compare `HGETALL` before and after to see the targeted change. When testing with entities that have `@Indexed` or `@TimeToLive`, also inspect finder results and `TTL` to distinguish metadata from Hash fields.

In automated tests, use an isolated Redis instance (e.g., Testcontainers), test-specific namespaces/IDs, clean up test data after each case, and avoid running broad delete commands on a shared instance.

## 9. Common Misconceptions

**"`save` only updates the modified properties."**  
Incorrect for default Redis Repositories when replacing an existing entity. The entity is converted into a new Hash representation; Hash fields absent from that representation are lost.

**"Calling `findById` before `save` preserves manually added fields."**  
Not guaranteed. `findById` reconstructs the object according to the mapping and does not copy unknown Hash fields onto the Java object.

**"Marking an auxiliary field `@Transient` protects it from being overwritten."**  
On the contrary, a field excluded from mapping will not be written back to the Hash by the Repository upon replacement.

**"Adding a field with `HSET` is safe because `HSET` does not delete other fields."**  
That statement is true for `HSET` in isolation, but a future `repository.save` can recreate the entire Hash and delete the manually added field.

**"`save` preserves the TTL because only field data changed."**  
You cannot rely on that assumption: the old Hash may be `DEL`eted, clearing the old TTL, and the Repository's TTL policy then determines the new expiration.

**"Switching from `save` to `PartialUpdate` guarantees prevention of all lost updates."**  
No. Partial updates reduce the risk of overwriting unrelated fields, but concurrent updates to the same field or cross-field invariants still require consistency/synchronization policies.

## 10. Design Principles When Using Redis Repositories

1. Clearly define **who owns each Hash**. If a Repository owns `profiles:42`, avoid writing fields manually to the same key.
2. Use `save` when you intend to replace the full entity; use `PartialUpdate` or another design when only a few properties change.
3. Do not construct an entity from an incomplete DTO and call `save` if `null` means "unchanged".
4. When changing schemas or custom converters, evaluate the impact on fields that are no longer emitted; plan data migration if those fields matter.
5. For `@Indexed` properties, go through an abstraction that updates indexes; avoid letting Hash data and indexes drift apart.
6. Verify TTL behavior along write paths, especially when combining `@TimeToLive`, manually set expirations, and multiple Redis access paths.
7. Design lost-update prevention if multiple tasks write to entities sharing the same ID.
8. Inspect `HGETALL`, `HEXISTS`, and `TTL` in a test environment to observe actual effects before using with critical data.

**Remember:** `repository.save(entity)` in Spring Data Redis Repository expresses the intent to **persist the full representation of the entity**, and for an existing entity it can **delete the old Hash and recreate it from the mapping**. To keep out-of-entity data or modify a single field, choose the corresponding Hash ownership model and update API.

## References

- [Spring Data Redis — Redis Repositories Anatomy](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/anatomy.html): illustrates `DEL`, Hash rewriting, and secondary index updates when replacing an entity.
- [Spring Data Redis — Object-to-Hash Mapping](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/mapping.html): mapping rules and the note that unmapped fields are lost when the Hash is recreated.
- [Spring Data Redis — Repository Usage / Partial Updates](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/usage.html): `CrudRepository` and `PartialUpdate`.
- [Spring Data Redis — Time To Live](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html): `@RedisHash(timeToLive)`, `@TimeToLive`, and expiration effects.
