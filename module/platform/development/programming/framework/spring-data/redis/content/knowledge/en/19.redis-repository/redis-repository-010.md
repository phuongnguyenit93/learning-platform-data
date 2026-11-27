# Managing Keyspaces and Indexes When Multiple Applications Write Data

In **Spring Data Redis Repositories**, `@RedisHash` determines where entities are stored by keyspace, and `@Indexed` enables querying certain properties via secondary indexes. Both mechanisms are straightforward when a single application owns the data. When multiple applications connect to the same Redis instance or cluster, keyspaces and indexes become a **shared data contract across applications**.

Two applications can accidentally write to the same key. Even without colliding on the primary key, one application updating a Redis Hash directly while another uses a repository can cause **the Hash and secondary indexes to drift out of sync**. As a result, reading by ID sees the new data, while querying with `findByStatus(...)` misses it or relies on stale indexes.

To operate safely, you must manage **keyspace naming, ID scoping, write ownership, schema and serializers, indexes, TTLs, version upgrades, and reconciliation** together.

## 1. What Is a Redis Repository Keyspace?

Redis is a key-value store. Key names must be unique within the Redis database an application connects to. Redis does not inherently know which service owns a group of keys; applications must agree on prefixes and naming conventions.

Spring Data Redis example:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash("orders")
public class OrderRecord {

    @Id
    private String id;

    private String status;

    // Constructors, getters, and setters...
}
```

A record with ID `o-1001` is typically stored at a key of the form:

```text
orders:o-1001
```

In that model, `orders` is the **keyspace**, and `o-1001` is the **entity ID**. Redis Repository uses Redis Hashes and mapping rules to persist entity properties. When `@RedisHash` is declared without an explicit name, the mapping context has rules to infer the keyspace from the entity type/configuration. In multi-application environments, specify an explicit keyspace as part of the data contract so renaming a Java class or package does not inadvertently change storage addresses.

**A keyspace is a logical name, not an isolated Redis database or SQL table.** Two services connecting to the same database and writing `orders:o-1001` are mutating the exact same key. Beyond the entity Hash key, the repository can also create auxiliary keys to track ID lists in the keyspace and secondary indexes. Therefore, namespace boundaries must cover **all framework-created metadata keys as well**.

## 2. Keyspace Conventions When Multiple Applications Share Redis

An easy-to-manage convention:

```text
<domain-or-service>:<environment>:<entity>:<schema-version>
```

Examples:

```text
commerce:prod:orders:v2
commerce:staging:orders:v2
catalog:prod:products:v1
identity:prod:sessions:v3
fulfillment:prod:tasks:v1
```

This is a system-chosen convention, not mandatory Spring Data Redis syntax. With:

```java
@RedisHash("commerce:prod:orders:v2")
public class OrderRecord {
    @Id
    private String id;
}
```

ID `o-1001` typically maps to the entity key:

```text
commerce:prod:orders:v2:o-1001
```

Each segment addresses a specific concern:

| Segment | Meaning | Risk if omitted |
|---|---|---|
| Domain or service | Identifies which team/service owns the data | Two services mutate the same keys |
| Environment | Separates dev, staging, production | Tests corrupt production data |
| Entity | Distinguishes orders, products, sessions | Two entity types collide on IDs |
| Schema version | Separates incompatible storage contracts | Older apps misread newer payloads |
| ID | Unique identifier within the keyspace | Overwrites records from another source |

### 2.1. IDs Must Be Unique Across the Actually Shared Scope

If applications A and B both create orders with ID `123` and share the keyspace `commerce:prod:orders:v2`, both can write to `commerce:prod:orders:v2:123`. Separating services in code does not help Redis distinguish two different entities.

Options include UUID/ULID or IDs prefixed with tenant/source:

```text
o-01J...
tenant-17:o-1001
partner-a:order-1001
```

When concatenating segments, define how delimiters and special characters are encoded. Above all, IDs must be stable: changing an ID essentially moves to a new key, requiring index and reference updates.

### 2.2. Environments and Redis Cluster

If a Redis instance is shared across dev/staging/prod, environment prefixes help identify data, but **do not provide strict security isolation**. For sensitive data or high operational risk, separate infrastructure resources and access controls appropriately.

Do not rely on Redis logical database numbers as a general solution for Redis Cluster: Redis Cluster normally supports only database 0. Namespace design and Redis ACLs/cluster separation must match the actual topology.

The value passed to `@RedisHash("...")` is a constant in the annotation. If the environment requires choosing keyspaces dynamically, use Spring Data Redis mapping keyspace configuration or separate deployments by connection. Do not assume the annotation resolves arbitrary environment placeholders unless supporting mechanisms are configured.

## 3. How Do `@Indexed` Secondary Indexes Work?

Redis Hashes do not inherently support arbitrary queries by field. Spring Data Redis Repositories support **secondary indexes** for properties annotated with `@Indexed`.

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("commerce:prod:orders:v2")
public class OrderRecord {

    @Id
    private String id;

    @Indexed
    private String status;

    @Indexed
    private String shopId;

    private long totalInCents;

    public OrderRecord() {
    }

    public OrderRecord(
            String id, String status, String shopId, long totalInCents) {
        this.id = id;
        this.status = status;
        this.shopId = shopId;
        this.totalInCents = totalInCents;
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }

    public String getShopId() { return shopId; }
    public void setShopId(String shopId) { this.shopId = shopId; }

    public long getTotalInCents() { return totalInCents; }
    public void setTotalInCents(long totalInCents) {
        this.totalInCents = totalInCents;
    }
}
```

Repository:

```java
import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface OrderRecordRepository
        extends CrudRepository<OrderRecord, String> {

    List<OrderRecord> findByStatus(String status);
    List<OrderRecord> findByShopId(String shopId);
}
```

Logical representation of the data:

```text
commerce:prod:orders:v2:o-1001
    |
    +-- status = "CREATED"
    +-- shopId = "shop-7"
    +-- totalInCents = 250000

Secondary index on status:
    CREATED -> o-1001, o-1002, ...

Secondary index on shopId:
    shop-7  -> o-1001, o-1010, ...
```

Spring Data Redis may use Redis Sets to track entity keys associated with indexed values. Exact index keys and metadata depend on mapping and library version; the diagram above **illustrates relationships**, not fixed internal key names for the application to manipulate directly.

When an entity is written through the repository, the framework knows which properties are indexed and performs the corresponding bookkeeping. When `status` changes from `CREATED` to `PAID`, memberships for the old and new values must be updated accordingly.

### `@Indexed` Is Not a Unique Constraint

Multiple orders can share `status = CREATED` and coexist in the index. Likewise, annotating `externalOrderCode` with `@Indexed` does not prevent two entities from holding the same code. If business logic requires unique values, use an atomic write/check mechanism in a store capable of enforcing that constraint; do not rely on `@Indexed` to prevent duplicates.

## 4. Why Can Writing Hashes Directly Cause Index Drift?

Suppose application A saves an order through the repository:

```java
orderRepository.save(
        new OrderRecord("o-1001", "CREATED", "shop-7", 250000L));
```

From the system's view, Hash `o-1001` and index metadata `status=CREATED` are maintained according to Spring Data Redis's mechanism.

Application B might only know the Redis key, and run:

```redis
HSET commerce:prod:orders:v2:o-1001 status PAID
```

`HSET` updates the value in the Hash, yet **does not execute Spring Data Redis Repository's mapping and secondary index management**. The state can become:

```text
Hash o-1001:
    status = PAID

Index CREATED:
    still contains o-1001

Index PAID:
    does not yet contain o-1001
```

Then:

```text
findById("o-1001")       -> reads Hash, sees PAID
findByStatus("PAID")     -> may miss o-1001
findByStatus("CREATED")  -> may still follow stale membership
```

Depending on how results are mapped, stale indexes can yield results that fail to match predicates or cause extra reads. The root issue is that **the Hash and the index no longer reflect the same version**.

Operations that easily introduce drift:

- Running `HSET` or `HDEL` directly on a `@Indexed` field.
- Running `DEL` on the primary key without running corresponding index cleanup.
- Rewriting the Hash from another Redis client/language unaware of repository metadata.
- Two applications both using repositories but having **divergent `@Indexed` fields, converters, mappings, or schema versions**.
- Importing data directly into Redis and querying via `findBy...` without building secondary indexes for the imported data.

**Crucial contract:** A repository-managed keyspace needs **a single consistent write mechanism for both Hashes and indexes**. It is not enough that "every application uses the same key names"; they must also agree on how data is updated and deleted.

## 5. Three Models for Sharing Redis Across Applications

### Model A — Each Application Owns Its Own Keyspace

```text
Shared Redis
  |
  +-- catalog:prod:products:v1:*     <- catalog-service
  +-- commerce:prod:orders:v2:*      <- order-service
  +-- identity:prod:sessions:v3:*    <- identity-service
  +-- analytics:prod:projections:v1:*<- analytics-service
```

Each service manages its own schema and indexes; other services request data via APIs/events. This is usually the easiest model to operate unless there is a compelling need to write directly to the same entity set.

### Model B — One Writer Service, Multiple Reader Services

`order-service` creates/updates orders; `report-service` only reads.

Shared reading requires understanding the exact keyspace, serializers, field names, ID semantics, and schema evolution policy. If `report-service` only needs reporting, using an API or a dedicated projection typically reduces coupling to internal mapping.

Point to remember: direct read-only access is still **coupling to the storage format**. Changing classes/packages or converters in the owning application can break the reader application.

### Model C — Multiple Applications Writing the Same Keyspace

`order-api` creates orders; `billing-worker` updates status after payment; `sync-worker` synchronizes external orders.

Risks include:

1. ID collisions and record overwrites.
2. Mismatched serializers, field names, or enums.
3. Inconsistent sets of indexed properties.
4. One writer dropping or altering TTLs on write.
5. Concurrent writes causing lost updates.
6. One writer deleting keys while another leaves stale metadata.
7. Rolling deployments mixing old and new schema versions simultaneously.

If shared writing is unavoidable, parties must agree on a **versioned contract**, share consistent write/concurrency mechanisms, and coordinate deployments. Simply sharing `@RedisHash` declarations is not enough.

## 6. Every Keyspace Needs a Data Owner

Ownership can be documented with a governance table:

| Keyspace | Owning service | Other consumers | Indexed fields | TTL |
|---|---|---|---|---|
| `commerce:prod:orders:v2` | `order-service` | `report-service` via API/events | `status`, `shopId` | Per order lifecycle |
| `catalog:prod:products:v1` | `catalog-service` | `commerce-service` via API/events | `categoryId` | Per cache policy |
| `identity:prod:sessions:v3` | `identity-service` | Authorized services | Per query needs | Mandatory TTL |

This is a **recommended governance table**, not an automated configuration tool. It helps implementation teams answer:

- Who is allowed to create, update, and delete entities? Who is read-only?
- Which fields may change, and via which commands or events?
- Who owns the schema, converters, TTLs, and `@Indexed` definitions?
- When records are deleted or expire, who is responsible for index cleanup?
- Who is authorized to change keyspaces, add/remove indexes, and run backfills?
- When drift occurs, which team performs reconciliation?

**One logical owner does not mean a single JVM.** A service can have multiple replicas or workers. Those replicas still must handle concurrency, yet all follow **the same update contract**.

If another service needs to change order status, a manageable design is sending a command/event to the owning service and letting it write via its repository. Services needing queryable reporting data can build their own **dedicated read projection** in their own namespace.

## 7. Concurrent Writes Can Cause Lost Updates or Corrupted Indexes

Suppose two workers read an order simultaneously:

```text
             Initial state: CREATED
                         |
              +----------+-----------+
              |                      |
          Worker A                Worker B
       reads CREATED           reads CREATED
              |                      |
      sets status=PAID       sets status=CANCELLED
              |                      |
      repository.save(...)   repository.save(...)
              |                      |
              +----------+-----------+
                         |
       Result depends on ordering and operation interleaving
```

Redis executes individual commands with per-command atomicity, yet a single repository operation can emit **multiple commands** to write the Hash, update indexes, update key tracking lists, and set TTL. Do not treat `repository.save(...)` as a cross-key business transaction.

To protect state:

- Coordinate writes through a single owning service.
- Enforce explicit state-transition rules, e.g., only allow `CREATED -> PAID` if not cancelled.
- Use idempotency keys for messages that may be redelivered.
- If compare-and-set/optimistic concurrency is needed, choose a mechanism that truly performs **atomic check-and-write** at the authoritative store.
- For business flows demanding strong consistency, consider keeping the source of truth in an appropriate transactional store and using Redis as a projection/cache.

Do not simply write an atomic `HSET` Lua script to "fix" the issue if the field is part of a secondary index: the script may update the Hash while leaving the index wrong. In Redis Cluster, multi-key scripts and transactions are also constrained by hash slots; entity keys and index keys may not live in the same slot. Therefore, ensuring atomicity across Hashes and related indexes requires deliberate design rather than assuming the framework handles it automatically.

## 8. Costs and Limits of `@Indexed`

Every index adds write work and consumes extra memory. When an indexed value changes, old membership must be removed and new membership added. Redis Repositories may also maintain keyspace ID sets to support repository operations.

| Event | Impact on data | What to watch |
|---|---|---|
| Create entity | Writes Hash and index membership | Number of indexed fields determines added work |
| Change `@Indexed` field | Updates Hash and membership | Do not edit raw Hash bypassing indexes |
| Change unindexed field | Updates only entity data per mapping | Do not add indexes unless queries need them |
| Delete via repository | Deletes entity and cleans related metadata | Avoid bypassing with raw `DEL` |
| TTL expiration | Redis removes the Hash | Index cleanup depends on configuration/events |
| Add `@Indexed` in code | New mapping knows to index the field | Existing data needs backfill/reindexing |

A low-cardinality `status` field can produce very large index sets. A field with millions of distinct values can produce millions of tiny sets. Both incur metadata overhead; do not annotate every property with `@Indexed` "just in case".

Repository secondary indexes are also **not a general-purpose search engine**. If the API requires full-text search, ranking, sorting, or complex pagination over very large sets, evaluate a read model or an appropriate query solution.

Values of indexed fields can appear inside metadata key names. Avoid putting secrets, tokens, or sensitive personal data into raw keys or indexes.

## 9. TTL, Expiration Events, and Leftover Indexes

An entity can be saved with a TTL, for example via `@RedisHash(timeToLive = ...)` or `@TimeToLive`. Redis expires the primary key, yet Redis does not know that Spring Data Redis secondary indexes are referencing that key.

Spring Data Redis offers **keyspace expiration events** to help clean up metadata/indexes upon entity expiration. This mechanism has limits:

- Redis must emit expiration notifications; an application listener must be configured and running.
- Redis Pub/Sub events are not buffered for disconnected subscribers; applications starting late miss past events.
- In Redis Cluster, keyspace events are node-scoped; you must understand cluster topology and subscription behavior.
- Physical expiration and event delivery do not necessarily happen at the exact second TTL reaches 0.
- Depending on configuration, Spring Data Redis may store an extra **shadow copy/phantom copy** living longer than the primary key so expiration events carry entity data; account for that memory overhead too.

Example:

```text
10:00:00  Save session:s7 with 15-minute TTL;
          index userId=u1 holds related membership.

10:15:00  Primary key expires.

10:15:00  Listener is interrupted and misses the event.

10:20:00  Index may still hold membership pointing to the gone key.
```

That is why **TTL does not guarantee clean indexes under all circumstances**. When multiple applications write data, avoid having each application set arbitrary TTLs or toggle event listeners inconsistently.

A reliable design should:

1. Designate which component is responsible for monitoring and handling expirations for the keyspace.
2. Configure Redis notifications at the infrastructure level if managed Redis restricts applications from running config commands.
3. Handle index queries that encounter entities whose primary keys no longer exist.
4. Run batch reconciliation or index-rebuild jobs when events are missed.
5. Measure stale membership counts and shadow-copy memory overhead, especially for short-TTL entities.

Do not bulk-delete keys that look like repository metadata without understanding the active library version's layout; accidental deletion can break queries or framework cleanup.

## 10. Schema and Serializers Are Also Part of the Contract

Two applications sharing a keyspace can still interpret data differently.

```text
Application A               Application B
-----------                 -----------
status: String              status: enum with different value names
totalInCents: long          total: BigDecimal
@Indexed(status)            No @Indexed(status)
TTL: 7 days                 TTL: 30 minutes
```

Spring Data Redis Repositories rely on mapping and converters. Complex or polymorphic data may depend on type metadata, custom converters, or property-naming rules. Changing Java classes/packages, serializers, or currency units can cause another application to misread data while still seeing the same Redis key.

If sharing directly is unavoidable, the contract should specify:

- Field names, types, ID format, units, and the meaning of `null`.
- Conversion rules and representations for special types.
- Which properties are indexed and how indexes are maintained on writes.
- TTLs, deletion rules, and missing-data recovery policies.
- Compatibility between old and new versions during rolling deployments.
- How unreadable or missing data is handled.

Between Java and services written in other languages, do not treat `@RedisHash`'s internal representation as an immutable cross-system protocol. APIs or events with versioned payloads are usually a more stable boundary.

## 11. Adding an Index to Existing Data: Backfill Required

Suppose one million `OrderRecord` records were saved before `status` carried `@Indexed`. In a later deployment, a developer adds:

```java
@Indexed
private String status;
```

Changing the annotation **does not automatically scan all one million Hashes and populate index memberships for existing data**. Records saved under the new mapping will appear in the index, while older records remain unindexed. `findByStatus("PAID")` may return an incomplete set.

Rollout approach:

1. Determine the existing ID range and active write sources.
2. Finalize the new entity version, schema, and target indexes.
3. Backfill using the mapping mechanism capable of populating the indexes, in load-bounded batches.
4. Track concurrent updates occurring during backfill; avoid overwriting newer records with stale snapshots.
5. Sample and reconcile Hashes against index memberships; switch queries to the new index only after meeting completeness criteria.

If scanning via Redis `SCAN`, iterate until the cursor finishes; a single call does not guarantee returning all keys, and the keyset can mutate while scanning. Do not conclude "backfill finished" from a single batch's item count.

## 12. Changing Keyspaces and Deploying New Versions

Changing the annotation:

```java
// Old version
@RedisHash("orders")

// New version
@RedisHash("commerce:prod:orders:v2")
```

does not migrate existing data automatically. This **changes the storage address of entities and metadata**. New readers may miss old keys; old writers keep writing to the old namespace during rollout.

A safe rollout follows staged phases:

### Phase A — Inventory

Identify all active writers/readers, schemas, secondary indexes, TTLs, key volumes, ID sources, and deletion rules.

### Phase B — Establish the New Namespace

Lock down `v2`, IDs, converters, `@Indexed` fields, owning service, and access permissions. Prepare v1 read capability to support migration.

### Phase C — Batch Migration

Read v1 in batches, transform, and save via v2 mapping so both Hashes and indexes are properly created. If data mutates during migration, use change events or coordination so v2 stays current and old backfills do not overwrite newer updates.

### Phase D — Switch Readers and Writers

Once v2 passes reconciliation checks, cut over read and write flows according to plan. If using temporary dual-writes, plan for retries/idempotency and cases where v1 succeeds while v2 fails. Two separate `save` calls do not automatically form a cross-keyspace transaction.

### Phase E — Retire v1

Decommission v1 only after no applications or consumers depend on it, retention windows have passed, and migration is verified. Clean up old metadata/indexes systematically, not just primary Hashes.

```text
                    Migration window
                           |
             +-------------+--------------+
             |                            |
         old keyspace                  v2 keyspace
           orders:*              commerce:prod:orders:v2:*
             |                            ^
             +----- backfill + changes ---+
                                          |
                                    reader/writer v2
                                          |
                                   cutover and reconcile
                                          |
                                       retire v1
```

A schema migration is complete when **ID lookups and index-based queries** both reflect the target dataset as required.

## 13. Multi-Tenancy and Access Control

If two tenants share the ID `order-1`, a shared keyspace `commerce:prod:orders:v2` needs an identifier strategy to prevent key collisions.

For example:

```text
commerce:prod:orders:v2:tenant-17:order-1
commerce:prod:orders:v2:tenant-29:order-1
```

You can use tenant-prefixed IDs or per-tenant keyspaces depending on your model and tenant count. Either way, repository queries must enforce tenant boundaries in business logic. Having an indexed `tenantId` field alone does not automatically prevent cross-tenant queries.

When multiple services connect to Redis, you can use **Redis ACLs** with separate credentials and allowed key patterns to restrict write scope. However, ACLs must permit the exact keys used by the framework: entity Hashes, index Sets, keyspace metadata, and auxiliary keys when TTL shadow copies are enabled. If an ACL permits Hash keys yet denies index keys, repository operations can fail partially.

For data with strict isolation requirements, separate Redis deployments/instances or network boundaries can be more trustworthy than key prefixes alone.

## 14. Detecting and Investigating Index Inconsistency

Common symptoms:

| Symptom | Causes to investigate |
|---|---|
| `findById(id)` returns data, `findByStatus(status)` does not | Missing reindex, raw Hash writes, or index drift |
| Index points to an ID whose Hash is gone | Key deleted/expired, listener missed expiration |
| Deserialization errors after deployment | Incompatible schema, type metadata, or converter |
| TTL changes unexpectedly | Multiple writers applying different policies |
| Index key count grows rapidly | Added fields or high-cardinality indexed fields |
| Queries return different results across services | Divergent keyspaces/mappings/indexes |

Diagnostic commands:

```bash
# Scan by cursor within a specific namespace:
redis-cli --scan --pattern 'commerce:prod:orders:v2:*'

# Inspect type and contents of an entity:
redis-cli TYPE 'commerce:prod:orders:v2:o-1001'
redis-cli HGETALL 'commerce:prod:orders:v2:o-1001'
redis-cli TTL 'commerce:prod:orders:v2:o-1001'

# Overall Redis statistics:
redis-cli INFO commandstats
redis-cli INFO memory
redis-cli SLOWLOG GET 10
```

`--scan` uses `SCAN`, which is safer than `KEYS *` on large instances, yet still requires rate and scope awareness. Avoid `KEYS *` on busy production Redis instances.

Once you have verified the exact **actual index key name** from your mapping and library version, you can use `TYPE`, `SCARD`, and `SSCAN` to inspect Redis Set membership. Do not rely on conceptual diagrams to manually edit arbitrary keys sharing a prefix.

`INFO commandstats` reports instance-wide statistics; `SLOWLOG` records only commands exceeding the Redis server execution threshold, without capturing full read counts or network latency. Complement these with per-service telemetry, trace IDs, deployment versions, and repository operation metrics.

### Reconciling Data and Indexes

A reconciliation pass can sample IDs or iterate a known ID set, read the Hash, check the indexed field value, compare membership in the corresponding index, and log:

- **Missing membership:** Hash exists with an indexed value, yet is missing from the corresponding index.
- **Stale membership:** Index lists an ID whose Hash is missing or whose field value has changed.
- **Mapping error:** Key exists but fails to map back to an entity per contract.

Identify the **write path causing drift** before running bulk fixes. If an application continues issuing direct `HSET` commands, indexes will drift again immediately after rebuilding. Repair tooling must understand full repository bookkeeping, not just edit a single Redis Set.

## 15. Application Scenario: Order API and Billing Worker

Suppose three applications exist:

- `order-api` creates orders, returns lists, and queries by `status`.
- `billing-worker` receives payment outcomes and marks orders `PAID`.
- `report-service` reports on paid orders.

All share Redis.

### Error-Prone Design

```text
1. order-api:
   repository.save(Order("o-1001", status="CREATED"))
   -> Hash = CREATED
   -> index CREATED contains o-1001

2. billing-worker:
   HSET commerce:prod:orders:v2:o-1001 status PAID
   -> Hash = PAID
   -> index CREATED did not remove o-1001
   -> index PAID does not yet contain o-1001

3. report-service:
   findByStatus("PAID")
   -> may fail to find o-1001
```

Redis executed `HSET` properly. The bug comes from **bypassing the repository's index management rules**.

### Logical-Owner Design

```text
billing-worker
    |
    +-- PaymentConfirmed(orderId, eventId)
                    |
                    v
               order-service
                    |
         Idempotent event handling
         Validate state transition
                    |
                    v
           repository.save(...)
                    |
           +--------+--------+
           |                 |
        Order Hash        Index metadata
           |                 |
           +--------+--------+
                    |
              OrderPaid event
                    |
                    v
              report-service
          (API or dedicated projection)
```

In this model, `order-service` owns write logic, schema, and indexes for the orders keyspace. `billing-worker` requests changes via controlled commands/events; `report-service` reads through an API or its own projection. If multiple instances of `order-service` can process the same ID concurrently, race conditions and idempotency still need to be handled at the business layer.

When multiple writers cannot yet be eliminated, establish at minimum a versioned shared contract, compatible deployment workflows, a write mechanism that updates indexes consistently, and a reconciliation strategy—while planning to consolidate independent write paths.

## 16. Design Selection Flow Before Scaling Out Applications

```text
Does a new app need to write to Redis?
               |
               v
Does data belong to an owned keyspace?
      |                        |
     Yes                       No
      |                        |
      v                        v
Ask owner to               Choose namespace and ID
provide API/events         with clear boundaries
      |                        |
      v                        v
If direct reads needed:    Define schema, TTL,
agree on read contract     @Indexed, converters
and version                    |
      |                        v
      |                   Lock down write owner
      |                        |
      +-------------+----------+
                    |
                    v
          Design concurrency,
          ACLs, migration, and observability
```

Before introducing a new keyspace or index, answer: Who owns it? Are IDs unique? Who can modify indexed fields? How will legacy data be reindexed? What happens if an entity expires while the listener is down? If two deployment versions write concurrently, can lost updates occur?

## 17. Mistakes to Avoid

- **Using `@RedisHash("orders")` across uncoordinated services:** invites ID collisions and index conflicts.
- **Changing the keyspace and expecting automatic data migration:** old entities and metadata do not move automatically.
- **Treating `@Indexed` as a unique constraint:** indexes do not prevent two entities from sharing the same value.
- **Editing Hashes via `HSET` while querying via repository:** the Hash updates while secondary indexes stay stale.
- **Letting writers use mismatched serializers/schemas:** causes misread fields or mapping failures.
- **Adding `@Indexed` without reindexing old data:** `findBy...` returns incomplete lists.
- **Assuming `save` is a cross-Hash/index transaction:** no such guarantee holds under arbitrary concurrency.
- **Relying on expiration events always being delivered:** Pub/Sub can drop notifications; plan reconciliation.
- **Granting ACL permissions only to Hash keys:** overlooks index and metadata keys created by repositories.
- **Running `KEYS *` to inspect production:** causes heavy load on shared Redis.
- **Forgetting tenant scoping in queries:** keyspaces and `@Indexed` do not enforce access control automatically.

**Guiding principle:** Spring Data Redis Repository manages a **combined model of entities and index metadata**, not merely isolated Redis Hashes. When multiple applications write data, the keyspace is a contract over identity, schema, and ownership; secondary indexes are derived state that must stay synchronized with entities. Establish one logical owner per keyspace, use versioned namespaces, control all write paths, and verify behavior across state transitions, TTLs, backfills, and multi-version deployments.
