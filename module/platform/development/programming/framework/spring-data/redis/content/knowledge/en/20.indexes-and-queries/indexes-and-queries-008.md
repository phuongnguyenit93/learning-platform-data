# Writes Outside the Repository and the Risk of Out-of-Sync Indexes

In Spring Data Redis, a `RedisRepository` does not merely store entity content in a Redis Hash. When an entity has properties marked with `@Indexed`, the framework also manages **auxiliary keys for queries**; for certain operations, it also maintains a keyspace ID set and lifecycle metadata. These structures are updated when operations flow through the **Spring Data Redis Repository** mapping mechanism.

Problems arise when that same data is modified directly via `redis-cli`, Redis commands, `RedisTemplate`, or another service. Successfully modifying a Redis Hash **does not mean** the Repository-managed indexes are updated as well. As a result, `findById()` may read the new value while `findByEmail()` fails to find the record, or a query for the old value still returns an entity that has already changed.

This lesson clarifies what is stored, when indexes drift, how to inspect and restore consistency, and how to structure write paths to minimize errors.

## 1. Redis Repositories Manage Multiple Data Structures

Suppose an application stores customers:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("customers")
public class Customer {
    @Id
    private String id;

    private String name;

    @Indexed
    private String email;

    @Indexed
    private String status;

    public Customer() {}

    public Customer(String id, String name, String email, String status) {
        this.id = id;
        this.name = name;
        this.email = email;
        this.status = status;
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
}
```

Corresponding repository:

```java
import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, String> {

    List<Customer> findByEmail(String email);

    List<Customer> findByStatus(String status);
}
```

Assuming the application has configured Spring Data Redis and enabled Redis Repositories, the call:

```java
customerRepository.save(new Customer(
        "c-100",
        "An",
        "an@example.test",
        "ACTIVE"
));
```

does not only create the primary key `customers:c-100`. Logically, the repository can also manage:

| Data Group | Purpose | Illustrative Example |
|---|---|---|
| **Entity Hash** | Holds property values of one customer | `customers:c-100` |
| **Keyspace management set** | Helps track entities belonging to `Customer` | `customers` |
| **Secondary index by email** | Finds entities with a specific email | `customers:email:an@example.test` |
| **Secondary index by status** | Finds entities with a specific status | `customers:status:ACTIVE` |
| **Index/lifecycle tracking metadata** | Supports updating and cleaning index links on change/delete | Auxiliary keys managed by Spring Data |

The index key names in the table reflect **common conventions** of Spring Data Redis, not a contract for applications to write to directly; actual representation also depends on mapping configuration, serializers, and library version. The table's goal is to distinguish the **data-bearing Hash** from **auxiliary query structures**.

Diagram:

```text
            customerRepository.save(customer)
                           |
                 Spring Data mapping
                           |
          +----------------+-----------------+
          |                |                 |
          v                v                 v
     Entity HASH      Keyspace SET     Secondary index SETs
  customers:c-100       customers       customers:email:...
                                       customers:status:...
          |                                  |
          |                        stores links to entity
          +----------------------------------+
```

Redis does not understand the `@Indexed` annotation itself. It is the Spring Data layer that creates and uses the index structures. Therefore, a Redis server will happily accept direct `HSET`, `HDEL`, `DEL`, or `EXPIRE` commands without knowing it needs to maintain Repository indexes.

## 2. Why Can ID Lookups and Property Queries Differ?

`findById("c-100")` already knows the identifier and keyspace, so the Repository can construct the primary key `customers:c-100` and load the corresponding Hash.

Conversely, `findByEmail("an@example.test")` does not know upfront which ID has that email. With the Redis Repository **secondary index** mechanism, the lookup flow is essentially:

1. Identify the index for the `email` property with value `an@example.test`.
2. Find entity references inside the corresponding index set.
3. Load entities from the primary keys pointed to by the index set.

```text
findById("c-100")
    |
    +--> customers:c-100 --> current HASH

findByEmail("an@example.test")
    |
    +--> index email=an@example.test
               |
               +--> reference customers:c-100
                         |
                         +--> current HASH
```

If the Hash and index disagree, the two read paths can return different results. A Redis Hash can exist validly yet **not be listed in the index**; or an index can contain a reference to a deleted key or changed property.

This is the key distinction between:

- **Physical existence of a Hash:** the question "Does Redis still hold key `customers:c-100`?"
- **Searchability via Repository:** the question "Do Spring Data's index structures still point accurately to the entity for this query condition?"

Both must be checked separately when diagnosing bugs.

## 3. Typical Scenario: `HSET` Outside the Repository Leaves Indexes Stale

Suppose an entity was initially created through the Repository:

```java
customerRepository.save(new Customer(
        "c-100", "An", "an@example.test", "ACTIVE"
));
```

At this point, logical data is:

```text
customers:c-100 (HASH)
  id     = c-100
  name   = An
  email  = an@example.test
  status = ACTIVE

email index:  an@example.test  --> customers:c-100
status index: ACTIVE           --> customers:c-100
```

Later, an operations tool edits the email attribute directly:

```bash
redis-cli HSET customers:c-100 email binh@example.test
```

The `HSET` command succeeds if Redis accepts the field update. However, it **affects only the specified Hash**. It does not run the Repository mapper, so it does not update links in Spring Data's secondary indexes.

The post-operation state may be:

```text
HASH customers:c-100:
  email = binh@example.test       <-- changed value

Index email=an@example.test:
  still contains customers:c-100  <-- stale reference

Index email=binh@example.test:
  missing customers:c-100         <-- missing new reference
```

From the application:

```java
// Directly loads primary key; sees new email.
Customer byId = customerRepository.findById("c-100")
        .orElseThrow();
System.out.println(byId.getEmail()); // binh@example.test

// Queries new email index; may not find c-100.
List<Customer> byNewEmail =
        customerRepository.findByEmail("binh@example.test");

// Queries old email index; may still find candidate c-100.
List<Customer> byOldEmail =
        customerRepository.findByEmail("an@example.test");
```

**Do not assert that every version/configuration always returns the exact same mismatch pattern**: some read paths may skip missing keys or apply extra handling. The fundamental issue is that **old indexes are not updated by a manual `HSET`**, and index query results are no longer guaranteed to reflect current Hash data.

If an operation modifies a **non-indexed** field such as `name`, queries by `email` generally do not need index membership changes just because `name` changed. Even so, manual writes must preserve proper field representation and handle races against the Repository; you cannot conclude from one error-free example that all direct writes are safe.

## 4. Which Out-of-Repository Operations Cause Which Drift?

Not every Redis command causes the exact same consequence. Examine **which key** is modified and **which metadata** should have changed alongside it.

| Operation Outside Repository | What Changes Directly | Risk to Repository |
|---|---|---|
| `HSET customers:c-100 email ...` | Changes an `@Indexed` field value | Old value index retains reference; new value index lacks reference |
| `HDEL customers:c-100 email` | Deletes an indexed field | Index for old email may still remain |
| `HSET customers:c-999 ...` creating new Hash | Creates a physical entity bypassing mapping | Keyspace/index sets and metadata may be missing; `findAll()` or `findByEmail()` misses it |
| `DEL customers:c-100` or `UNLINK ...` | Deletes primary Hash | Index may retain reference to nonexistent key; keyspace set may hold stale entry |
| `EXPIRE customers:c-100 60` | Sets TTL directly on Hash | Index/metadata lifecycle is not necessarily synced as via Repository |
| `PERSIST customers:c-100` | Removes TTL from Hash | May cause expiration handling or entity TTL policy to diverge from expectations |
| `HSET customers:c-100 name ...` | Changes non-indexed field | New value readable by ID, yet still risks lost updates if Repository saves stale object |
| `RENAME customers:c-100 customers:c-200` | Renames physical key | Internal ID, keyspace set, indexes, and references may retain old address |
| Direct writes to index sets | Manually edits index members | Extra/missing query hits; hard to distinguish valid data from tampered data |

These Redis commands execute at the **key/value** level, with no guarantee of updating relational rules across keys used by Spring Data Redis Repositories.

### Does Using `RedisTemplate` Avoid the Problem?

Not automatically. Example:

```java
import org.springframework.data.redis.core.StringRedisTemplate;

public class DirectRedisWriter {
    private final StringRedisTemplate template;

    public DirectRedisWriter(StringRedisTemplate template) {
        this.template = template;
    }

    public void changeEmailDirectly() {
        template.opsForHash().put(
                "customers:c-100",
                "email",
                "binh@example.test");
    }
}
```

`StringRedisTemplate` operates on Redis Hashes with standard Redis commands—**it does not invoke `CustomerRepository.save()` and does not coordinate Repository indexes**. Similarly, `RedisTemplate.opsForHash()`, Redis CLI, standalone Lettuce/Jedis clients, or another service writing directly to the same Hash can all desynchronize indexes.

Additionally, a direct-access template may use a different serializer than the Repository's converter. Even a simple field update could be written in the wrong type or binary format. Serializer compatibility is a separate requirement and **does not substitute for maintaining indexes**.

## 5. Writing and Updating Properly Through the Repository

When changing the email of an entity owned by `CustomerRepository`, the mapping-safe path is to load the entity, update the property, and save via the Repository:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Customer changeEmail(String id, String newEmail) {
        Customer customer = repository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Unknown customer: " + id));

        customer.setEmail(newEmail);
        return repository.save(customer);
    }
}
```

When operations go through the Repository, Spring Data Redis knows `Customer`'s `@Indexed` metadata and can update the appropriate index structures along with the entity data.

> Note on atomicity: Calling `repository.save()` does not automatically prove that all Hash, index, and keyspace set updates form a single atomic transaction against concurrent access. In Redis Cluster specifically, related physical keys may live on different hash slots. Spring's `@Transactional` should also not be slapped onto the example and assumed to provide multi-key Redis transactions; transactional behavior must be configured and evaluated separately.

The example above shows a **write path using the Repository's mapping/index mechanism**. If multiple concurrent writers modify the same entity, you must also address *lost updates* using an appropriate write-coordination policy.

### Multiple Writers Modifying Data Concurrently

```text
T0: Service A reads Customer(email=old, status=ACTIVE)
T1: Service B writes directly via HSET status BLOCKED
T2: Service A changes email and calls repository.save(stale customer)

Possible outcome:
  - status gets overwritten back to ACTIVE,
  - status index becomes out of sync at a point in time,
  - final data depends on timing and write mechanisms.
```

The Repository cannot detect that an out-of-band operation modified the Hash while an entity was held in application memory. When multiple systems must mutate the same data, designate **one authoritative write owner** and one unified update protocol.

## 6. Manually Created Keys Do Not Register Entities with Repositories

Another case is an import script creating many Hashes directly:

```bash
redis-cli HSET customers:c-900 id c-900 name "Imported User" \
  email imported@example.test status ACTIVE
```

After this command, `TYPE customers:c-900` may return `hash` and `HGETALL` shows the data. However, the object will likely not appear in:

- `customerRepository.findAll()`;
- `customerRepository.count()`;
- `customerRepository.findByEmail("imported@example.test")`;
- `customerRepository.findByStatus("ACTIVE")`.

The reason is that the import command only created the Hash, whereas the Repository also needs auxiliary structures to list and query entities. Moreover, when populating Hashes manually, required fields or Java type metadata might not match the converter's expectations, triggering mapping errors.

A more suitable import approach when entities should be managed by a Repository:

```java
Customer imported = new Customer(
        "c-900",
        "Imported User",
        "imported@example.test",
        "ACTIVE"
);

customerRepository.save(imported);
```

For bulk imports, you can use `saveAll(...)` in reasonable batches if suited to load and library version; measure performance carefully. Writing indexes and keyspace sets makes the cost higher than running a single `HSET`, yet that is the price of keeping queries accurate.

## 7. Keys Deleted or Expired Outside the Repository

### Direct Deletion via `DEL` or `UNLINK`

```bash
redis-cli DEL customers:c-100
```

Hash `customers:c-100` disappears, while index sets that pointed to it may still keep its membership. At this point:

- `findById("c-100")` usually stops returning the entity;
- email/status queries can still hit stale references;
- keyspace/index sets may grow bloated or miscount;
- how missing references are handled depends on the query path and configuration.

Deleting via `customerRepository.deleteById("c-100")` lets the Repository mechanism clean up structures it owns. Do not use manual `DEL` to remove entity Hashes and assume all indexes were cleaned up.

### TTL and Index Cleanup Mechanisms

Repositories can manage TTL via `@RedisHash(timeToLive = ...)` or `@TimeToLive`. With supported configuration, Spring Data Redis processes key expiration events to clean up related index structures. However, remember:

1. Redis emits expiration events according to *keyspace notifications* configuration and actual event mechanics; there is no guarantee every consumer always receives every event.
2. Listeners can be down, start late, or lose connectivity; in Redis Cluster, event subscription configuration and per-node scope require extra attention.
3. Setting or clearing TTL **directly** bypasses lifecycle info that the Repository may need to maintain.
4. Some configurations store temporary shadow copies of expiring data to populate events, creating auxiliary keys around expiration.

Therefore, even when the application only uses the Repository for saves, index cleanup policies after TTL must be designed and monitored. Do not assume calling `EXPIRE` manually on a Hash sets up and updates the full cleanup pipeline.

## 8. Detecting Index Drift in a Lab Environment

The diagnostic goal is comparing **Hash data** against **index links used by the Repository**. Take a record with known ID `c-100`.

### Step 1: Read the Primary Key

```bash
redis-cli TYPE customers:c-100
redis-cli HGETALL customers:c-100
redis-cli HGET customers:c-100 email
redis-cli TTL customers:c-100
```

These commands determine whether the Hash exists, its current email value, and its TTL. If `TYPE` returns something other than `hash`, pause before inspecting fields; another system may have written a different data type to the same key name.

### Step 2: Inspect Index Key Names

In a test environment with the example keyspace:

```bash
# SCAN only scans the connected node; loop with cursor until it returns 0.
redis-cli SCAN 0 MATCH 'customers:email:*' COUNT 100
redis-cli SCAN 0 MATCH 'customers:status:*' COUNT 100

# For a specific index key returned by SCAN:
redis-cli TYPE customers:email:an@example.test
redis-cli SMEMBERS customers:email:an@example.test
```

Interpret auxiliary key names and members according to the **active Spring Data configuration**. For example, index names can vary due to custom mapping or serializers. Do not run these commands to write/edit indexes in production.

### Step 3: Compare Against the Repository API

```java
Customer direct = customerRepository.findById("c-100")
        .orElse(null);

List<Customer> oldEmail =
        customerRepository.findByEmail("an@example.test");

List<Customer> newEmail =
        customerRepository.findByEmail("binh@example.test");
```

Cross-check: Which email is in the Hash? Which email index holds a reference to the primary key? Which IDs do the two Repository queries return? If the Hash and index contradict each other, that is clear evidence of desynchronization.

### Step 4: Distinguish Mapping Issues from Index Issues

There are at least three distinct error classes:

| Observation | Investigation Path |
|---|---|
| `findById()` loads wrong fields or fails conversion | Check physical Hash, serializer, `RedisConverter`, and entity metadata |
| `findById()` is right, but `findByEmail()` misses the ID | Check email index and history of field updates outside Repository |
| `findAll()` misses IDs even though Hashes exist | Check keyspace set, direct import/write paths, and key lifecycle |

Do not bulk-patch indexes before identifying the error type; if a serializer or mapping metadata mismatch is the root cause, manually adding elements to SETs will not fix it.

## 9. Common Causes of Desynchronization in Real Projects

### 9.1. Operational Commands Modifying Data Directly

Operators run `HSET` for a "quick fix" to an email or status. The Hash is immediately updated, but indexes never receive the change. Projects should provide an operational tool routing fixes through a managed service/repository, complete with audit logs of who changed what and why.

### 9.2. Imports/Migrations Writing Only Hashes

Import scripts use a raw Redis client for speed and skip creating the keyspace SET and secondary indexes. After import, ID lookups work while field queries fail. Import pipelines need to go through the repository or execute an index rebuild matching the active mapping.

### 9.3. Two Applications Sharing One Keyspace

Application A uses a Redis Repository with `@Indexed`, while B writes directly using the same `customers:<id>` convention. B may be unaware of the auxiliary keys A manages. Agree on **data ownership and write contracts** between both applications, especially when upgrading versions independently.

### 9.4. Changing Annotations or Mappings Without Migrating Data

For example, `status` was previously unindexed, and a new release adds `@Indexed`. Existing Hashes do not automatically get proper indexes merely because the app boots with the new annotation. Likewise, renaming fields, changing keyspaces, or swapping converters requires a backfill/migration plan.

### 9.5. Deletions/Expirations Lacking Cleanup

Hashes expire in Redis, while the listener or cleanup flow misses the required events; keyspace/index sets can keep stale references. Monitor index sizes and have reconciliation procedures rather than treating expiration events as a guaranteed durable delivery queue.

### 9.6. Uncoordinated Concurrent Updates

Two writers modify the same Hash, or one writer uses the Repository while another runs raw Hash commands. Operation order and stale reads dictate the final state; even accurate index maintenance per Repository call cannot prevent lost updates caused by another writer.

## 10. Prevention Principles When Using Redis Repositories

**The top principle is a single authoritative write path per entity.** If an entity falls under Repository ownership, create, update, and delete through the Repository or a service wrapping it to uphold the index contract.

Example of an application write gateway:

```java
import org.springframework.stereotype.Service;

@Service
public class CustomerCommands {

    private final CustomerRepository repository;

    public CustomerCommands(CustomerRepository repository) {
        this.repository = repository;
    }

    public Customer create(String id, String name, String email) {
        Customer customer = new Customer(id, name, email, "ACTIVE");
        return repository.save(customer);
    }

    public Customer changeStatus(String id, String status) {
        Customer customer = repository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Unknown customer: " + id));
        customer.setStatus(status);
        return repository.save(customer);
    }

    public void remove(String id) {
        repository.deleteById(id);
    }
}
```

Other services call operations on `CustomerCommands` instead of assembling `customers:<id>` keys and running `HSET`. When complex concurrency requirements exist, add versioning, appropriate optimistic locking, or business-level serialization; exact choices depend on stack capabilities.

Practical safeguards:

- **Define data ownership:** specify which component is allowed to modify entity Hashes and indexes.
- **Enforce Redis ACLs:** restrict direct write permissions for accounts meant only for querying or read-only operations where architecture permits.
- **Encapsulate write commands:** expose create/update/delete APIs/services instead of letting multiple systems edit Hashes directly.
- **Use standard import flows:** route through the Repository or a validated index-rebuild pipeline.
- **Monitor drift:** track entity counts, anomalous index reference counts, mapping failures, and missing-key hits.
- **Design for update contention:** multi-writer setups need coordination rules to prevent stale reads from overwriting newer changes.
- **Review TTLs and listeners:** verify real-world cleanup configuration and schedule reconciliation when events may be missed.

## 11. When Another System Must Write to the Same Redis

In some architectures, an ETL job, batch processor, or legacy system cannot immediately switch to Spring Data Redis Repositories. In that situation, choose an explicit synchronization contract.

| Approach | How It Operates | Trade-offs |
|---|---|---|
| **All writers call the service owning the Repository** | One component owns saving Hashes and indexes | Requires clean APIs and high availability of that service |
| **Writers emit requests/events; Repository service processes them** | Uses messages/streams as input; one consumer updates via Repository | Introduces lag; requires idempotency, retries, and event ordering |
| **Writers update all structures per unified protocol** | Self-manage Hashes, keyspace SET, indexes, and cleanup | Complex and coupled to internal mapping; brittle across upgrades |
| **Separate data store and build a dedicated read model** | Writers commit to canonical source; pipeline builds query indexes | Accepts eventual consistency; requires reconciliation |

With events/queues, **successfully publishing an event does not guarantee the index is updated yet**. Design error logging, duplicate handling, per-entity ordering, and replay/rebuild capabilities. If using transactions or Lua scripts to update multiple Redis keys—especially in Redis Cluster—account for hash slot rules and per-command atomicity; transactions do not automatically span across all shards.

Another option is dropping the Redis Repository secondary index model for data with many independent writers, replacing it with a data/query structure all writers can adhere to. That is an architectural decision, not merely changing a few Redis commands.

## 12. Reconciling and Restoring Drifted Indexes

Once corruption/drift is detected, the goal is to restore accurate relationships among:

```text
  Existing entity key
       |
       +--> current properties in Hash
       |
       +--> keyspace set membership
       |
       +--> corresponding secondary index links
```

A controlled recovery workflow:

1. **Choose the canonical data source.** Is the current Hash the business truth, or is a database/other system authoritative? If the Hash itself was written wrongly, rebuilding indexes from the Hash validates bad data.
2. **Determine the affected scope.** Keyspaces, `@Indexed` fields, entity subsets, or the timeframe of direct writes; measure volume before acting.
3. **Control competing writers.** Pause or coordinate writers causing drift so reconciliation does not race against continuous changes.
4. **Scan actual data accurately within scope.** If the keyspace set is already missing members, do not rely solely on `repository.findAll()` to discover affected Hashes. Use physical entity key scanning (e.g., `SCAN` by prefix, verify `TYPE`) and exclude index/metadata keys.
5. **Reconcile and rebuild mapping/indexes per active contract.** Given complete and valid entities, consider re-saving via the Repository to regenerate managed structures. However, simply calling `save()` per entity **may not remove every old index reference** if tracking metadata is already corrupted; verify results and have a plan for stale indexes.
6. **Verify bidirectional consistency.** If an entity has a current email, that email's index must reference it; no index should reference missing entities or outdated values.
7. **Log, measure, and prepare rollback.** Count processed entities, repaired indexes, conversion errors, and concurrent changes during the scan; keep operational backups/snapshots before bulk edits.
8. **Close the root-cause gap.** Without fixing out-of-Repository writes or TTL cleanup, data will soon drift again.

Never blindly delete all keys matching `customers*` to "wipe indexes": that pattern may include the entity Hashes themselves and critical keys. Rebuilding auxiliary indexes requires knowing **exact key names, types, and owners**.

### Why Is `findAll()` Insufficient as a Reconciliation Source?

If an importer created `customers:c-900` directly without adding it to the Repository's keyspace set, `findAll()` may not see `c-900`. Running:

```java
for (Customer customer : customerRepository.findAll()) {
    customerRepository.save(customer);
}
```

will not necessarily fix Hashes **omitted from enumeration in the first place**. To reconcile source data, you need an inventory channel independent of the suspected broken index, paired with proper filtering for actual entity keys.

### Why Is `SCAN` Not an Exact Snapshot Either?

`SCAN` processes keys in small batches, yet it can return duplicate keys and does not guarantee a frozen keyset while Redis handles ongoing writes and deletes. In Redis Cluster, each primary has its own scan cursor, and slots can migrate between nodes. Therefore, rebuild processes should be designed to be idempotent, track missed keys, and consider reruns/reconciliation passes or pausing mutations to meet consistency requirements.

## 13. How Does Redis Cluster Complicate Index Synchronization?

In Redis Cluster, keys `customers:c-100`, `customers:email:an@example.test`, and `customers` have their hash slots computed **from their physical key names**. They do not automatically land on the same primary just because they all start with `customers`.

```text
Redis Cluster

Primary A: customers:c-100
Primary B: customers:email:an@example.test
Primary C: customers

(Distribution diagram is illustrative only.)
```

If a writer uses a custom Redis transaction or Lua script to update multiple index keys, Redis Cluster enforces restrictions on multi-key operations spanning different hash slots. Do not assume a single command or script can atomically update all Hashes and indexes across all primaries.

Beyond atomicity:

- A `SCAN` command on one primary does not cover the entire cluster; a full inventory requires a strategy iterating over all primaries.
- Resharding or failover during reconciliation can cause duplicates, skipped keys, or retries.
- When part of a Hash/index update succeeds and the rest fails, the system needs a recovery mechanism aligned with the chosen sync protocol.

Therefore, **keeping indexes accurate across multiple writers and slots** must be handled in design, observability, and error handling—not assumed solely from the `@Indexed` annotation.

## 14. Lab Exercise to Reproduce Desynchronization

Run this only in an **isolated test Redis instance**, using the entity and Repository from the beginning of the lesson. The goal is to observe the divergence between Hash data and secondary index query results.

### Setup

Save a customer via the Repository:

```java
customerRepository.save(new Customer(
        "lab-01", "Lab User", "before@example.test", "ACTIVE"
));
```

Observe initial output:

```java
System.out.println(
        customerRepository.findById("lab-01").orElseThrow().getEmail());

System.out.println(
        customerRepository.findByEmail("before@example.test").size());
```

### Trigger an Out-of-Repository Change

In Redis CLI on the test environment:

```bash
redis-cli HSET customers:lab-01 email after@example.test
redis-cli HGET customers:lab-01 email
```

Continue reading:

```java
System.out.println(
        customerRepository.findById("lab-01").orElseThrow().getEmail());

System.out.println(
        customerRepository.findByEmail("before@example.test"));

System.out.println(
        customerRepository.findByEmail("after@example.test"));
```

The key observation is that **the field value changed while the index structures may still reflect the old link**. For each version/configuration, record the Hash contents, index key names, and returned IDs; do not just look at a single `size()` number and draw conclusions.

### Recover via the Valid Write Path

In the lab environment, try re-saving the entity through the Repository:

```java
Customer current = customerRepository.findById("lab-01")
        .orElseThrow();
current.setEmail("after@example.test");
customerRepository.save(current);
```

Then re-check both old and new indexes. This is a **lab experiment**, not a promise that a single `save` fixes every stale index in production. If wrong references remain, apply a controlled reconciliation/rebuild process according to active metadata.

Finally, clean up the lab data with `customerRepository.deleteById("lab-01")` and inspect the related auxiliary keys in the lab environment.

## 15. Self-Assessment Questions

**1.** Why does `findById("c-100")` read the new email while `findByEmail(newEmail)` fails to return the entity?  
Because ID lookup reads the primary Hash, whereas property lookup relies on secondary indexes; an out-of-Repository write may have altered the Hash without adding the new index link.

**2.** Does calling `StringRedisTemplate.opsForHash().put(...)` in the same Spring Boot app automatically update `@Indexed`?  
No. That is a low-level Hash operation, not equivalent to `repository.save()`.

**3.** Does running `HSET` to create a new Hash guarantee `findAll()` will find it?  
No. The Repository's keyspace set or other metadata may not have been updated.

**4.** Is running `HSET` outside the Repository on a field without `@Indexed` always safe?  
You cannot conclude that: that field's secondary index may not need updating, but serializer, mapping, and concurrent-update risks still apply.

**5.** Why can deleting a Hash with `DEL` leave traces behind in indexes?  
Redis only deletes the specified key; it has no awareness of auxiliary SETs holding references to that Hash.

**6.** Why shouldn't index recovery rely solely on iterating `repository.findAll()`?  
Because the keyspace management set itself may be missing manually written entities; the rebuild input could omit data.

**7.** Can `@Indexed` alone guarantee every Hash and index update is atomic in Redis Cluster?  
No. You must understand how the Repository and client execute commands across slots, along with concurrency and error handling; the annotation only declares indexing intent.

## 16. Conclusion

Spring Data Redis Repositories maintain a **structured data model** atop Redis: primary Hash keys store entities, while auxiliary SETs/metadata support enumeration and queries on `@Indexed` properties. Direct writes to Hashes do not trigger index management. Thus, **a correct Hash does not guarantee correct Repository queries**.

When an entity is managed by a Repository, route creates, updates, and deletes through one unified write path responsible for index maintenance. If imports, TTLs, Redis Cluster, or external writers exist, establish clear synchronization contracts, monitoring, and reconciliation. That is what ensures `findById()`, `findAll()`, and `findBy...()` reflect the exact same logical dataset.

## References

- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html): entity mapping and Repository mechanics.
- [Spring Data Redis — Indexes](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/indexes.html): secondary index mechanics and `@Indexed`.
- [Spring Data Redis — Query Methods](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/queries.html): queries based on indexed properties.
- [Spring Data Redis — Time To Live](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html): TTL, expiration events, and data cleanup.
- [Spring Data Redis — Object-to-Hash Mapping](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/mapping.html): converting objects to Redis Hashes.
- [Redis — HSET](https://redis.io/docs/latest/commands/hset/), [HDEL](https://redis.io/docs/latest/commands/hdel/), [DEL](https://redis.io/docs/latest/commands/del/): Redis-level command behavior on keys and fields.
- [Redis — SCAN](https://redis.io/docs/latest/commands/scan/): limitations of cursor-based key scanning.
