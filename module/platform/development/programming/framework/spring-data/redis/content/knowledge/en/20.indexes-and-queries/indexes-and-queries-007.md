# Impact of Entity Updates and Deletions on Indexes in Spring Data Redis

## 1. The Problem: Data Changes Must Be Reflected in Query Results

In Spring Data Redis Repositories, an entity is stored by **ID** and can be looked up by properties that have declared secondary indexes. For example, a delivery management application stores records with `id`, `status`, `warehouse`, and `description`. Users want to query shipments awaiting processing at each warehouse.

Suppose an entity has an initial state:

```text
id          = delivery-101
status      = PENDING
warehouse   = HCM
description = Awaiting packing
```

When updating the status to `SHIPPED`, the following requirements must be met:

- `findById("delivery-101")` returns the entity with the new status.
- `findByStatus("PENDING")` no longer treats that entity as a member of the old group.
- `findByStatus("SHIPPED")` finds the entity in the new group.
- When deleting the entity, the indexes used to look it up must also be updated.

If you change data only in the Redis Hash while ignoring indexes, the application can end up with **correct primary data but wrong query results**. This is why understanding the update and deletion lifecycle through Spring Data Redis Repositories is essential.

This lesson explains how indexes work, what happens when calling `save` and `delete`, why TTLs can leave stale indexes behind, and how to organize safe write and delete flows.

## 2. What Is a Secondary Index in Redis Repositories?

Redis is a key–value data store. When you know an entity's exact key, reading by ID is straightforward. However, the question "all deliveries with `status = PENDING`" cannot be solved from IDs alone.

Spring Data Redis Repositories support certain property queries via secondary indexes. You mark a property with `@Indexed`; Spring Data manages additional Redis structures to link **property values** to **the IDs of matching entities**.

Conceptual model:

```text
Primary key:
  demo:delivery:delivery-101
    id          -> delivery-101
    status      -> PENDING
    warehouse   -> HCM
    description -> Awaiting packing

Index by status:
  status=PENDING -> {delivery-101, delivery-102, ...}
  status=SHIPPED -> {delivery-203, ...}

Index by warehouse:
  warehouse=HCM -> {delivery-101, delivery-203, ...}
```

Index structures typically rely on Redis Sets and internal keys so Spring Data can track information needed for cleanup on updates or deletions. The diagram above depicts **data relationships**, not a guarantee of exact key names or internal field contents across all Spring Data Redis versions.

### Primary Keys vs. Secondary Indexes

| Component | Purpose | Who Manages It? |
|---|---|---|
| Entity Redis Hash | Stores the property data of an entity | Redis Repository via mapping mechanism |
| ID and keyspace | Identifies the entity, used by `findById` | Entity with `@Id` and `@RedisHash` |
| Secondary index | Finds entities by a property other than ID | Spring Data Redis per `@Indexed` and mapping config |
| Auxiliary metadata/indexes | Tracks keys in the keyspace and index cleanup info | Redis Repository infrastructure |

Because indexes are stored as additional Redis data, inserting, modifying, or deleting an entity can involve **multiple keys and multiple Redis commands**, not just a single `HSET` or `DEL` command.

## 3. Declaring an Entity and Repository to Observe Index Lifecycle

Spring Boot dependency example:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-redis")
}
```

Local Redis configuration:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
```

These values are for learning environments only. In real environments, configure authentication, TLS, endpoints, and Redis topology properly.

### 3.1. Defining the Entity

**`DeliverySnapshot.java`**

```java
package com.example.delivery.redis;

import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("demo:delivery")
public class DeliverySnapshot {

    @Id
    private String id;

    @Indexed
    private String status;

    @Indexed
    private String warehouse;

    private String description;

    public DeliverySnapshot() {
    }

    public DeliverySnapshot(
            String id,
            String status,
            String warehouse,
            String description
    ) {
        this.id = id;
        this.status = status;
        this.warehouse = warehouse;
        this.description = description;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public String getWarehouse() {
        return warehouse;
    }

    public void setWarehouse(String warehouse) {
        this.warehouse = warehouse;
    }

    public String getDescription() {
        return description;
    }

    public void setDescription(String description) {
        this.description = description;
    }
}
```

`@RedisHash` specifies the keyspace, `@Id` identifies the ID, and `@Indexed` marks properties used in value-based queries. `description` does not have `@Indexed` because the example does not need to look up records by description text.

### 3.2. Defining the Repository

**`DeliveryRepository.java`**

```java
package com.example.delivery.redis;

import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface DeliveryRepository
        extends CrudRepository<DeliverySnapshot, String> {

    List<DeliverySnapshot> findByStatus(String status);

    List<DeliverySnapshot> findByWarehouse(String warehouse);
}
```

Spring Data Redis implements the repository via its infrastructure when repository scanning and Redis connection are properly configured. `findByStatus` and `findByWarehouse` query by indexed properties. Do not assume all JPA query operators are supported by Redis Repositories.

## 4. When Creating a New Entity, How Are Indexes Added?

Create an entity through the repository:

```java
DeliverySnapshot delivery = new DeliverySnapshot(
        "delivery-101",
        "PENDING",
        "HCM",
        "Awaiting packing"
);

repository.save(delivery);
```

Logically, the save operation must perform related steps:

1. Map the properties of `DeliverySnapshot` to the Redis Hash corresponding to its ID.
2. Write the data so `findById("delivery-101")` can read it back.
3. Register the ID in structures managing entities within the keyspace.
4. Write the necessary index relationships: `status=PENDING` and `warehouse=HCM`.
5. Save or update auxiliary information for subsequent modifications and deletions.

After saving succeeds, queries:

```java
List<DeliverySnapshot> pending =
        repository.findByStatus("PENDING");

List<DeliverySnapshot> hcm =
        repository.findByWarehouse("HCM");
```

can return `delivery-101` through both groups if the related data and indexes were created properly.

**Do not think of `save` as a single Redis command.** Mapping and updating indexes are handled by the repository layer, and operations touching multiple keys are not automatically atomic like a relational database transaction.

## 5. When Updating an Indexed Property

This is the most important case: a property marked with `@Indexed` changes its value.

For example, transitioning a delivery from `PENDING` to `SHIPPED`:

```java
DeliverySnapshot delivery = repository.findById("delivery-101")
        .orElseThrow(() ->
                new IllegalArgumentException("Delivery not found")
        );

delivery.setStatus("SHIPPED");
repository.save(delivery);
```

After the `save` call, the index model should reflect:

| Component | Before Update | After Update |
|---|---|---|
| Hash `delivery-101` | `status=PENDING` | `status=SHIPPED` |
| Group `status=PENDING` | Contains `delivery-101` | No longer contains `delivery-101` |
| Group `status=SHIPPED` | Does not contain `delivery-101` | Contains `delivery-101` |
| Group `warehouse=HCM` | Contains `delivery-101` | Still contains `delivery-101` |

In the entity save flow through Spring Data Redis Repository, the repository infrastructure manages **removing old index links and creating new index links** corresponding to the entity's current state. This mechanism relies on Spring Data Redis's mapping/index metadata; the application does not have to manually invoke `SREM` and `SADD` for every property change.

### Updating Multiple Indexed Properties at Once

```java
DeliverySnapshot delivery = repository.findById("delivery-101")
        .orElseThrow();

delivery.setStatus("SHIPPED");
delivery.setWarehouse("HN");
repository.save(delivery);
```

Expected state:

```text
status=PENDING  : no longer contains delivery-101
status=SHIPPED  : contains delivery-101
warehouse=HCM   : no longer contains delivery-101
warehouse=HN    : contains delivery-101
```

At the model level, each indexed property is affected independently. If an object updates multiple fields in a single `save`, the repository must synchronize all corresponding indexes.

### Re-Saving with the Exact Same Value

If `status` remains `PENDING`, logical group membership does not change. However, do not rely on the assumption that Spring Data Redis skips all network writes when `save` receives an unchanged entity; exact persistence and performance behavior depend on implementation and version.

## 6. When Updating Only a Non-Indexed Property

Changing `description` while keeping `status` and `warehouse`:

```java
DeliverySnapshot delivery = repository.findById("delivery-101")
        .orElseThrow();

delivery.setDescription("Packed, awaiting handover");
repository.save(delivery);
```

Because `description` is not annotated with `@Indexed`, the system does not need to maintain a lookup group for that description string. In terms of query results, membership in the `status` and `warehouse` groups must remain unchanged.

This does not mean `save` only modifies the single `description` field with one `HSET` command. The repository saves entities via Spring Data Redis's mapping mechanism; if you need to mutate a single field directly with minimal cost, choose the appropriate API while understanding its impact on indexes if that field is indexed.

### Property Becoming `null` or Being Cleared

Suppose an indexed property previously had `warehouse=HCM`, and then changes to `null`:

```java
delivery.setWarehouse(null);
repository.save(delivery);
```

The link in the `warehouse=HCM` group should no longer point to the entity. When a field no longer has an indexed value, there is no reason for the entity to remain in the old group. How `null` is mapped to Redis depends on the converter; the key point here is **updating through the repository so related indexes stay synchronized**.

For indexable collection or nested properties, adding, removing, or replacing elements can also alter multiple index relationships. Verify property-type and query support boundaries in the Spring Data Redis version you are using.

## 7. When Deleting an Entity via `CrudRepository`

Delete a single entity by ID:

```java
repository.deleteById("delivery-101");
```

Or when you already hold the object:

```java
repository.delete(delivery);
```

For an indexed entity, a valid deletion must clean up both primary data and links in secondary indexes.

### Before and After Deletion

Suppose the object has state:

```text
id=delivery-101
status=SHIPPED
warehouse=HN
```

Expectations after deleting via the repository:

| Component | Before Deletion | After Deletion |
|---|---|---|
| Hash of `delivery-101` | Exists | Gone |
| Lookup `findById` | Returns entity | Returns `Optional.empty()` |
| Index `status=SHIPPED` | Contains ID | No longer contains ID |
| Index `warehouse=HN` | Contains ID | No longer contains ID |
| Repository support metadata | Retains entity info | Adjusted accordingly |

Spring Data Redis Repositories use the managed tracking information for the entity and its indexes to clean up stale links. This is why **you should delete via the repository if the data was created and indexed by the repository**.

### Deleting Multiple and Deleting All

```java
repository.deleteAll(List.of(deliveryA, deliveryB));
```

This deletes a specific group of entities. Meanwhile:

```java
repository.deleteAll();
```

has a much broader scope: it requests deleting all entities managed by the repository. With a large keyspace, cleaning up data and indexes can require many Redis operations. Never expose `deleteAll()` behind a public API or an automated job lacking strict bounds and access control.

**Do not treat ID as a mutable field to "rename" an entity.** If a record's ID changes from `delivery-101` to `delivery-999`, treat it as creating a new entity and deleting the old entity in your business workflow. Simply changing the `id` property on an object and calling `save` does not mean Spring Data Redis atomically migrates the old key and all indexes.

## 8. Why Direct Deletion via `RedisTemplate` or Redis CLI Can Corrupt Indexes?

Suppose an entity was saved via the repository with:

```text
ID:     delivery-101
status: PENDING
```

Then another process deletes the primary Redis key using:

```redis
DEL demo:delivery:delivery-101
```

Redis only deletes the specified key. It **has no awareness** that the key represents a Java entity linked to Spring Data-managed secondary indexes. Auxiliary index keys may still hold references to `delivery-101`.

A subsequent `findByStatus("PENDING")` query can encounter an index member whose primary data no longer exists. Actual behavior may be missing records, unexpected query results, or lingering index entries, depending on the read mechanism and data state; do not expect the repository to instantly repair changes made outside it.

The same situation happens when editing an indexed field via raw commands:

```redis
HSET demo:delivery:delivery-101 status SHIPPED
```

The Hash now contains `SHIPPED`, while the Spring Data-managed index may still reflect `PENDING`. The Redis command does not notify the repository's secondary index manager to update groupings.

### Comparing Update Approaches

| Operation Method | Changes Primary Data | Maintains Repository Index |
|---|---|---|
| `repository.save(entity)` | Yes, per entity mapping | Managed by Spring Data Redis Repository |
| `repository.deleteById(id)` | Yes | Managed by repository in delete flow |
| `redisTemplate.opsForHash().put(...)` | Yes, on chosen field | Does not auto-sync repository secondary index |
| `redisTemplate.delete(key)` / Redis `DEL` / `UNLINK` | Yes, on specified key | Does not auto-clean repository-managed metadata/indexes |
| Direct Redis `EXPIRE` | Sets TTL on key | Depends on expiration handling; not equivalent to full repository delete |

Therefore, a useful operational rule is: **A keyspace managed by a Redis Repository should have one unified write/delete mechanism.** If you must mix raw operations and repositories, proactively design how indexes stay consistent; do not assume the two API layers automatically know what the other is doing.

## 9. Hands-On: Observing Queries Before and After Update and Deletion

The following example illustrates the entity lifecycle via the repository API. You can place this code in a runner enabled only under a learning profile to avoid creating or deleting data unintentionally during normal runs.

**`DeliveryIndexDemo.java`**

```java
package com.example.delivery.demo;

import com.example.delivery.redis.DeliveryRepository;
import com.example.delivery.redis.DeliverySnapshot;

import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("redis-index-demo")
public class DeliveryIndexDemo implements CommandLineRunner {

    private final DeliveryRepository repository;

    public DeliveryIndexDemo(DeliveryRepository repository) {
        this.repository = repository;
    }

    @Override
    public void run(String... args) {
        String id = "delivery-demo-101";

        // Clean up any previous test record, if present.
        repository.deleteById(id);

        // 1. Create an entity with two indexed properties.
        DeliverySnapshot item = new DeliverySnapshot(
                id,
                "PENDING",
                "HCM",
                "Pending processing"
        );
        repository.save(item);

        System.out.println(
                "Found in PENDING: " + containsId("PENDING", id)
        );

        // 2. Change status via repository.
        item.setStatus("SHIPPED");
        repository.save(item);

        System.out.println(
                "Still in PENDING: " + containsId("PENDING", id)
        );
        System.out.println(
                "Found in SHIPPED: " + containsId("SHIPPED", id)
        );

        // 3. Delete entity via repository.
        repository.deleteById(id);

        System.out.println(
                "Entity still exists: " + repository.existsById(id)
        );
        System.out.println(
                "Still in SHIPPED: " + containsId("SHIPPED", id)
        );
    }

    private boolean containsId(String status, String id) {
        return repository.findByStatus(status)
                .stream()
                .anyMatch(item -> id.equals(item.getId()));
    }
}
```

Activate the runner for a test environment using the `redis-index-demo` profile according to your project's Spring Boot run setup. Redis must be reachable and the repository must be registered by Spring.

If no other process alters data during execution, the logical expectation is:

```text
Found in PENDING: true
Still in PENDING: false
Found in SHIPPED: true
Entity still exists: false
Still in SHIPPED: false
```

The example uses `containsId` instead of comparing the entire `List` because Redis in a test environment might already hold other entities with the same status.

This example illustrates **the expected behavior when updating and deleting through a repository**. If results differ from expectations, check indexes, mapping, repository configuration, and interference from other jobs.

## 10. TTL and Expiration Events: How Are Indexes Cleaned Up?

TTL introduces a special case: an entity can disappear because Redis automatically expires its key, without the application **ever calling `repository.deleteById`**.

Example entity with a 15-minute TTL:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash(value = "demo:temporary-delivery", timeToLive = 900)
public class TemporaryDelivery {

    @Id
    private String id;

    @Indexed
    private String status;

    public TemporaryDelivery() {
    }

    // Constructors, getters/setters can be declared as in the previous example.
}
```

`timeToLive = 900` is in seconds. When the TTL expires, Redis deletes the primary key via expiration. However, Redis **does not understand Spring Data Redis secondary indexes**; cleaning up index relationships requires a Spring Data-side mechanism.

### 10.1. Keyspace Notifications and `RedisKeyExpiredEvent`

Spring Data Redis Repositories support listening to Redis key expiration events to handle entity lifecycle and index cleanup. This mechanism relies on Redis keyspace notifications / Redis Pub/Sub along with Spring Data Redis listeners.

You can explicitly enable the listener when configuring repositories manually:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.RedisKeyValueAdapter.EnableKeyspaceEvents;
import org.springframework.data.redis.repository.configuration.EnableRedisRepositories;

@Configuration
@EnableRedisRepositories(
        basePackages = "com.example.delivery.redis",
        enableKeyspaceEvents = EnableKeyspaceEvents.ON_STARTUP
)
public class RedisRepositoryConfiguration {
}
```

This is an example for **explicit repository configuration**; do not add duplicate configuration if the Spring Boot project already registers repositories elsewhere. Some managed Redis environments do not permit applications to alter `notify-keyspace-events`; in that case, configure notifications according to infrastructure capabilities and verify that the listener actually receives events.

### 10.2. Why Can Stale Indexes Exist After TTL?

Redis Pub/Sub is not a durable queue. If the application stops running, the listener is disabled, the connection drops, or the Redis key expires while no subscriber is attached, the expiration event may **not be processed** by Spring Data Redis.

The result can be:

```text
Hash demo:temporary-delivery:temp-1  -> expired
Index status=PENDING                  -> still references temp-1
```

Thus, having a TTL on the primary key does not guarantee that all auxiliary index keys are cleaned up immediately and completely in every situation.

### 10.3. Shadow Copies and Memory Impact

When expiration event support is enabled, Spring Data Redis may create an additional **shadow copy** (a temporary copy of entity data) to provide entity details inside the expiration event after the primary key disappears. This carries its own memory cost and lifetime.

If the application does not need entity contents in expiration events, you can consider configuring `shadowCopy = OFF` according to your Spring Data Redis version's support and requirements. However, disabling shadow copies reduces information available in events; evaluate both expiration processing needs and index cleanup mechanisms.

**Do not treat expiration events as the sole mechanism for business logic requiring exact once-only processing.** Such requirements typically need durable stateful jobs or proper queues.

## 11. What Happens When Multiple Processes Update Concurrently?

Suppose two workers load the same entity concurrently:

```text
Initial state: status=PENDING, warehouse=HCM

Worker A reads entity.
Worker B reads entity.

Worker A sets status=SHIPPED and saves.
Worker B sets description=Verified and saves.
```

If Worker B saves the **entire stale entity** after Worker A, data from the stale read can overwrite the new `status`. The repository may update indexes to match the record it just saved, yet the final state contradicts Worker A's intent.

Key point: **an index being consistent with the saved state does not mean business updates were not lost**.

Additionally, if a save/delete operation touches multiple Redis keys, network failures or mid-flight errors can leave primary data and index data temporarily out of sync. Do not assume `save` plus multiple index updates forms a fully atomic transaction merely because of the `CrudRepository` API.

Ways to reduce risk:

- For multi-writer operations, clearly define entity ownership rules and write ordering.
- When concurrency control is needed, evaluate optimistic locking/versioning, conditional checks, or atomic Redis operations designed specifically for your case; do not assume a JPA annotation works identically in Redis Repositories.
- When state is merely a derived cache, allow rebuilding entities/indexes from the canonical source of truth.
- For business flows requiring multi-entity transactions, consider a storage technology suited to those consistency requirements.

### How Does Redis Cluster Change Things?

In Redis Cluster, keys can reside in different hash slots. The entity key and index/metadata keys may fall into separate slots. Operations involving multiple keys or requiring multi-key commands are therefore subject to cluster topology constraints.

Verify whether your Spring Data Redis version, Redis driver, and keyspace/index strategy fit the Redis Cluster in use. Do not assume repository updates/deletes clean all indexes in a single cluster-wide atomic multi-key command.

## 12. How to Detect Stale or Out-of-Sync Indexes

A secondary index can drift in two directions:

1. **Dangling references:** the index still holds an ID, while the corresponding entity was deleted, expired, or changed value.
2. **Missing references:** an entity has the matching field value, yet its ID was never added to the index—for example, data written with raw commands bypassing the repository.

Example table:

| Primary Data | Index | Consequence |
|---|---|---|
| `status=SHIPPED` | Still in `PENDING` | Queries for the old group may get stale references |
| `status=SHIPPED` | Missing from `SHIPPED` | Queries for the new group may miss the entity |
| Hash deleted | Index still holds ID | Index wastes memory and retains invalid references |
| Hash still exists | Index deleted manually | Index queries miss the entity even though `findById` finds it |

### Observing in a Development Environment

After saving an entity with ID `delivery-101`:

```redis
TYPE demo:delivery:delivery-101
HGETALL demo:delivery:delivery-101
```

Find keys associated with the keyspace in test data:

```redis
SCAN 0 MATCH demo:delivery:* COUNT 100
```

Continue `SCAN` using the returned cursor until the cursor returns to `0`. `COUNT` is only a hint for work per iteration, not a cap on total results. Actual index key names and internal metadata depend on Spring Data Redis; before inspecting with `SMEMBERS` or `SSCAN`, verify **which key is actually the index's Redis Set**.

Do not run `KEYS demo:delivery:*` on production Redis with large key counts, and do not manually call `SREM` on internal index keys without fully understanding the auxiliary tracking data managed by the repository.

### Cross-Checking Results via the Repository

Use both read paths during investigation:

```java
Optional<DeliverySnapshot> byId =
        repository.findById("delivery-101");

List<DeliverySnapshot> byStatus =
        repository.findByStatus("SHIPPED");
```

Compare the entity state fetched by ID against its presence in status query results. When observing discrepancies, first check write/delete paths outside the repository, TTL expiration timing, listeners, and write failures.

Do not conclude that an empty query result means "no Redis key exists"; a missing secondary index can also cause empty query results even though the entity still exists.

## 13. Preventing and Recovering from Inconsistent Indexes

### 13.1. Preventing Sources of Drift

For a keyspace managed by a Redis Repository:

1. Designate a single authoritative **write, update, and delete** path.
2. Use `repository.save` when modifying indexed properties; use `repository.deleteById` or `delete` when deleting entities.
3. Avoid raw operations on Hashes, index Sets, and repository metadata from other services.
4. Define TTL policies and configure listeners suited to your actual Redis deployment.
5. When needing indexes for legacy data, prepare a migration/conversion process instead of only adding `@Indexed` to the class and assuming historical records are indexed automatically.

### 13.2. When Data Has Already Drifted

Repair must begin by **identifying the trustworthy source of truth**. For example, if Redis is only a cache in front of a primary database, you can clear and rebuild part of the cache via the standard repository write path.

If Redis is the sole data store, proceed more carefully:

- Back up or snapshot necessary data before cleaning auxiliary structures.
- Identify the affected namespace scope and IDs that genuinely have data.
- Reconcile entity state against related index relationships.
- Rebuild via supported mapping paths; run in small batches and monitor impact.
- Avoid commands that flush the entire database or wipe indexes en masse before fully mapping relationships between entities, keyspaces, and auxiliary data.

There is no single Redis command to "repair all secondary indexes across all repositories" like a relational database provides. Recovery solutions depend on entity structure, query methods, library version, and recoverable data sources.

### 13.3. Do Not Mistake Indexes for the Source of Truth

A secondary index is a **derived structure supporting lookup**. If an index says an ID belongs to `PENDING`, that does not replace verifying that the primary data still exists and holds the right state—especially in concurrent-write environments or where operations bypassed the repository.

In critical workflows, you may need to load the current entity and re-verify business preconditions before taking the next action.

## 14. Special Scenarios to Distinguish

| Scenario | What to Watch Out For? |
|---|---|
| Adding `@Indexed` after data exists | Old entities may lack corresponding index links; requires rebuild/migration plan |
| Renaming an indexed property | Old mapping/index may no longer match; manage legacy-version data |
| Renaming `@RedisHash` keyspace | Creates a new key area; old data and indexes do not move automatically |
| Changing only non-indexed fields | Logical index group membership does not change |
| Changing an `@Indexed` field to another value | Must remove old link and write new link |
| Setting an indexed field to `null` | Link to the old value should no longer exist |
| Deleting via repository | Repository manages both primary data and its index structures |
| Deleting Hash via Redis CLI or template | Can leave behind repository indexes/metadata |
| Redis expires key via TTL | Requires appropriate expiration listener to clean indexes; events can be missed |
| Two workers saving stale/new versions | Risk of lost updates; final index state follows whichever value was saved last |
| Redis Cluster | Account for multi-key constraints across hash slots and actual repository config |

## 15. Practice Scenarios and Reasoning

**Scenario 1:** An entity has `status=PENDING`, `warehouse=HCM`. The application changes `status` to `SHIPPED` and calls `repository.save`.

Reasoning: Primary data reflects `SHIPPED`; the link to index `PENDING` must be removed and the link to `SHIPPED` must be created. Group `warehouse=HCM` retains the entity because the `warehouse` field did not change.

**Scenario 2:** The application deletes the primary key via `StringRedisTemplate.delete(key)` and then calls `findByStatus("SHIPPED")`.

Reasoning: The primary key may be gone, but direct deletion did not update index relationships through the repository workflow. Check for dangling references rather than assuming deleting the primary key cleaned up everything related.

**Scenario 3:** An entity has a 10-minute TTL. During those 10 minutes, the service managing the repository stops; upon restart, property queries return unexpected results.

Reasoning: Redis may have expired the primary key while the listener missed the event to clean up indexes. Check keyspace notification settings, listener status, and index repair procedures—not just the TTL annotation.

**Scenario 4:** `@Indexed` is added to the `priority` property on an entity that already has millions of saved records.

Reasoning: Existing records are not automatically guaranteed to have the new index just because the Java class changed. Plan a re-save or index rebuild from a trustworthy data source, executed in throttled batches.

**Scenario 5:** Two processes concurrently read and save an entity. The final index accurately reflects the record saved by the second process, but the first process's change was lost.

Reasoning: Index synchronization and lost-update prevention are two distinct issues. Design concurrent write control at the business layer; do not infer transactional guarantees simply from using a repository.

## 16. Conclusion

When `@Indexed` is declared on a Redis entity, Spring Data Redis Repositories manage extra structures for property-based queries. Consequently:

- **Adding an entity** requires creating primary data and index links.
- **Updating an indexed value** requires moving the link from the old value to the new value.
- **Updating a non-indexed field** does not logically alter index membership.
- **Deleting via repository** cleans primary data along with repository-managed index links.
- **Modifying/deleting with raw Redis commands** can put primary data and indexes out of sync.
- **TTL expiration, concurrent writes, and partial failures** require dedicated design and monitoring.

A vital operational rule is to **route writes and deletions through one unified mechanism managing both entities and indexes**, control TTL lifecycles, and distinguish index accuracy from business consistency under concurrent writers.

### References

- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html)
- [Spring Data Redis — Secondary Indexes](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/indexes.html)
- [Spring Data Redis — Time To Live](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html)
- [Spring Data Redis — Queries and Query Methods](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/queries.html)
- [Spring Data Commons — CrudRepository](https://docs.spring.io/spring-data/commons/reference/repositories/core-concepts.html)
- [Redis — Keyspace notifications](https://redis.io/docs/latest/develop/pubsub/keyspace-notifications/)
