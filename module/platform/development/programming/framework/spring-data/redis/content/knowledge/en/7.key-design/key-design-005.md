# Distinguishing Primary Keys, Index Keys, and Relationship Keys

In Redis, every piece of data is accessed through a **key**. However, not every key carries the same role in application design. When building systems with **Spring Data Redis**, we commonly need to distinguish three roles:

- **Primary/data key:** identifies the record or object being stored.
- **Index key:** enables looking up one or more records by attribute, status, or order without scanning the entire keyspace.
- **Relationship/link key:** describes associations between records, such as which orders a customer has.

This is an **application data-model classification**. Redis does not have tables, primary keys, foreign keys, or general-purpose secondary indexes like relational databases. Spring Data Redis can manage certain keys/indexes on your behalf when using Redis Repositories, but when operating directly with `RedisTemplate`, the application itself must maintain structures supporting queries and relationships.

## 1. Overview through an e-commerce example

Suppose a system has customer `42` and two orders `1001`, `1002`. Each order has a status, an owner, and a creation timestamp.

An illustrative Redis design:

~~~text
Primary keys (entity data)
  shop:customer:42              HASH  {name: "Lan", tier: "GOLD"}
  shop:order:1001               HASH  {customerId: "42", status: "PAID", ...}
  shop:order:1002               HASH  {customerId: "42", status: "PENDING", ...}

Index keys (lookup by condition)
  shop:order:by-status:PAID     SET   {"1001", "1008", "1013", ...}
  shop:order:by-status:PENDING  SET   {"1002", "1010", ...}

Relationship keys (customer - order association)
  shop:customer:42:orders       ZSET  {"1001" → 1710000000000,
                                     "1002" → 1710000001000}
~~~

In this example, each element inside the SET/ZSET is an **order ID**, not the full order payload. That ID leads to a primary key such as `shop:order:1001`.

| Role | Question answered | Common structures | Stored values/members |
|---|---|---|---|
| Primary key | "What is order 1001?" | HASH, STRING, JSON if supported | Order attributes |
| Index key | "Which orders have status PAID?" | SET, ZSET, or unique-mapping STRING | IDs of matching orders |
| Relationship key | "Which orders belong to customer 42?" | SET, ZSET, LIST, or HASH per relationship | IDs of associated objects |

**A SET or ZSET does not self-identify a key's role.** Two keys that are both SETs can have completely different meanings: one finds all orders by status, while another stores the list of orders belonging to a customer. Read the **naming convention and query purpose**, not merely the Redis data type.

## 2. Primary keys: identifying and holding entity state

### 2.1. A Redis key is an identifier string within a logical database

Example:

~~~redis
HSET shop:order:1001 id 1001 customerId 42 status PAID amount 250000
HGETALL shop:order:1001
HGET shop:order:1001 status
~~~

The key `shop:order:1001` is where the application locates order record `1001`. Fields inside the HASH are just attributes; an `id` field may be stored for display/object mapping, yet Redis itself **does not enforce that the `id` field matches the suffix of the key**.

Within a Redis logical database, key names must be unique: writing a new value to the same key name mutates that same key. Redis does not inherently understand that `shop:order:1001` and `shop:invoice:1001` share a business primary key.

A well-designed primary key needs:

1. **A stable identifier:** the ID does not change when a username, price, status, or frequently edited field changes.
2. **A clear namespace:** identifies application, entity type, and ID to avoid name collisions.
3. **A consistent format:** every creator/reader/deleter builds the key using the exact same rule.
4. **A defined lifecycle:** whether it persists indefinitely, has a short TTL, or is merely a cache snapshot must follow business requirements.
5. **No exposed sensitive data:** IDs or key names can show up in logs, traces, dashboards, and admin commands.

If the ID is already a UUID, you can use `shop:order:550e8400-e29b-41d4-a716-446655440000`. A UUID is not mandatory; what matters is a stable ID free of key collisions in the business scope.

### 2.2. Redis Repositories: `@Id` maps to the primary key

Spring Data Redis Repositories allow declaring entities and repositories:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash("shop:customer")
public class CustomerSnapshot {

    @Id
    private String id;

    private String displayName;

    protected CustomerSnapshot() {
    }

    public CustomerSnapshot(String id, String displayName) {
        this.id = id;
        this.displayName = displayName;
    }

    public String getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

~~~java
import org.springframework.data.repository.CrudRepository;

public interface CustomerSnapshotRepository
        extends CrudRepository<CustomerSnapshot, String> {
}
~~~

An object with ID `42` is typically mapped to a Redis HASH under keyspace `shop:customer`, forming a primary key of `shop:customer:42`. In Java code, `@Id` marks the ID property; `@RedisHash("shop:customer")` specifies the entity keyspace. Spring Data Redis may also create internal keys to manage the repository and indexing; do not assume every framework-managed key works identically to application-crafted keys.

Notes:

- `@Id` is a **Spring Data** mapping concept, not a Redis server-level primary key constraint.
- `CrudRepository.findById("42")` uses ID/keyspace mapping; no manual keyspace scan query is needed.
- `CrudRepository.deleteById("42")` follows repository mechanics, unlike manually deleting a hash without updating internal indexes.
- When Redis serves as a **cache snapshot**, the ID in Redis may match the ID in the primary database; that does not automatically create a shared transaction across both systems.
- A `@RedisHash` object is persisted via Redis Repositories mapping. Avoid arbitrarily mixing manual `RedisTemplate` `HSET` operations with repository operations on the same key without understanding the metadata/indexes the repository maintains.

### 2.3. Primary keys do not necessarily hold all source data

Many systems use PostgreSQL/MySQL as the source of truth and Redis to accelerate reads:

~~~text
Database row: orders.id = 1001          ← authoritative data source
         │
         └── produces cache/snapshot copy
                 ↓
Redis HASH: shop:order:1001             ← fast-access copy
~~~

In this model, "Redis primary key" means **the key identifying the snapshot record**, not a claim that Redis is the sole transactional store for orders. Document the authoritative data source, TTL, and cache update rules clearly.

## 3. Index keys: navigating from search criteria to IDs

### 3.1. Why are index keys needed?

Redis does not automatically support SQL-style queries over all HASHes like:

~~~sql
SELECT id FROM orders WHERE status = 'PAID';
~~~

If each order exists only under `shop:order:<id>`, the application must already know the key list or scan, read, and filter every record. Scanning the entire keyspace per request generally breaks down as data grows.

Instead, if screens frequently ask "all PAID orders?", we maintain a **reverse lookup**:

~~~redis
SADD shop:order:by-status:PAID 1001 1008 1013
SMEMBERS shop:order:by-status:PAID
~~~

The result is the ID set `{"1001", "1008", "1013"}`. The application then reads the primary keys `shop:order:1001`, `shop:order:1008`, and `shop:order:1013` to fetch full records.

~~~mermaid
flowchart LR
    Q["Find PAID orders"] --> IDX["SET shop:order:by-status:PAID"]
    IDX --> I1["ID 1001"]
    IDX --> I2["ID 1008"]
    IDX --> I3["ID 1013"]
    I1 --> O1["HASH shop:order:1001"]
    I2 --> O2["HASH shop:order:1008"]
    I3 --> O3["HASH shop:order:1013"]
~~~

This is an **application-designed index**. Redis server does not inspect the `status` field inside HASHes and sync the index SET for you.

### 3.2. Common index types

| Query need | Example storage | Usage notes |
|---|---|---|
| Filter by an attribute shared by multiple records | `shop:order:by-status:PAID` → SET of IDs | Group membership lookup, unordered |
| Fetch orders by time | `shop:order:by-created-at` → ZSET of ID + timestamp | Score-range queries, ordering, and result limits |
| Fetch pending orders in a region | `shop:order:region:HCM:status:PENDING` → SET of IDs | Build composite indexes only when actual queries demand them |
| Look up one ID by unique external code | `shop:order:by-external-ref:ABC-9` → STRING `"1001"` | Single-ID lookup; requires uniqueness enforcement |
| Look up by ranking score | `shop:product:by-popularity` → ZSET of product ID + score | Sort by score, top-N |

**SET** works well for group intersections/unions (`SINTER`, `SUNION`) when data and topology allow. **ZSET** works well for score ordering/ranges; scores are floating-point numbers, so specify units and precision (e.g., millisecond timestamps). **STRING** is convenient for mapping one unique value to one ID.

Do not create indexes for every field "just in case we search by it later". Every index consumes RAM and complicates writes, updates, and deletes.

### 3.3. Multi-result indexes do not enforce uniqueness

With a SET:

~~~redis
SADD shop:customer:by-tier:GOLD 42
SADD shop:customer:by-tier:GOLD 57
SMEMBERS shop:customer:by-tier:GOLD
~~~

Having two customers with value `GOLD` is completely valid. If an attribute must be unique, such as a username, merely naming an index `by-username` does not create a SQL `UNIQUE` constraint.

One application-managed unique lookup approach:

~~~redis
SET shop:customer:by-username:lan 42 NX
GET shop:customer:by-username:lan
~~~

The `NX` option ensures `SET` succeeds only when the key does not already exist. However, **succeeding on the index key write does not make creating the customer HASH and all other indexes atomic**. If creating the HASH subsequently fails or username changes race, the system needs proper commit/rollback or reconciliation logic. True uniqueness must be protected across the **entire create/update flow**.

### 3.4. Spring Data Redis `@Indexed`

When using **Redis Repositories**, Spring Data Redis supports secondary indexes on properties annotated with `@Indexed`:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("shop:customer")
public class IndexedCustomer {

    @Id
    private String id;

    @Indexed
    private String email;

    private String displayName;

    protected IndexedCustomer() {
    }

    public IndexedCustomer(String id, String email, String displayName) {
        this.id = id;
        this.email = email;
        this.displayName = displayName;
    }

    public String getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

~~~java
import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface IndexedCustomerRepository
        extends CrudRepository<IndexedCustomer, String> {

    List<IndexedCustomer> findByEmail(String email);
}
~~~

When `IndexedCustomer` entities are saved via the repository, the framework maintains a secondary index for the `email` field to serve `findByEmail(...)` queries. Repository indexes are typically implemented via keys holding ID sets associated with indexed values; exact internal key names belong to the framework's mapping internals and can vary across versions, annotations, and keyspace strategies.

Three limitations to understand:

1. **`@Indexed` does not enforce uniqueness.** Two entities with the same email can still be saved unless business logic prevents it.
2. **Only framework-managed write paths are expected to maintain repository indexes.** Manually calling `HSET` on `email` via `RedisTemplate` may leave repository-managed indexes out of sync.
3. **Not every arbitrary query style has an index.** Check the supported query methods and indexing capabilities of Spring Data Redis; do not assume it is a full SQL/JPA query engine.

Beyond `@Indexed`, Spring Data Redis offers specialized indexing mechanisms (such as geospatial data) with their own mapping requirements. This lesson focuses on distinguishing key roles rather than covering every index variant.

## 4. Relationship keys: storing associations between entities

### 4.1. One-to-many: customer and orders

Given a customer, applications commonly want their list of orders:

~~~redis
ZADD shop:customer:42:orders 1710000000000 1001
ZADD shop:customer:42:orders 1710000001000 1002
ZREVRANGE shop:customer:42:orders 0 19
~~~

The key `shop:customer:42:orders` represents the **relationship** between customer 42 and their orders. Members `1001`, `1002` are IDs; scores allow sorting by creation time. Querying the link key does not return full orders; after retrieving IDs, the application dereferences `shop:order:<id>`.

Technically, this link key is also **a form of lookup index by customer ID**. We distinguish it as a "relationship key" to emphasize domain meaning: it models an association and carries two-sided maintenance responsibilities.

If you only need to know which orders a customer has without ordering, a SET is simpler:

~~~redis
SADD shop:customer:42:orders 1001 1002
SMEMBERS shop:customer:42:orders
~~~

Do not switch from SET to ZSET simply because ZSET has "more features": choose structures based on real queries and cost.

### 4.2. One-to-many or many-to-many?

For many-to-many, such as students enrolled in multiple courses:

~~~text
learning:student:42:courses       SET {"spring", "redis"}
learning:course:redis:students     SET {"42", "51", "76"}
~~~

These two keys are **two directions of the same relationship**. If queries need both directions, keeping two SETs enables fast reads yet requires consistent updates:

~~~redis
SADD learning:student:42:courses redis
SADD learning:course:redis:students 42
~~~

If only the first command succeeds, the relationship becomes visible from the student side but missing from the course side. Choose one of these strategies:

- Keep only one direction as authoritative and accept scanning/alternative lookups for the reverse direction.
- Maintain both directions inside a coordinated atomic operation if topology permits.
- Accept eventual consistency with retries and reconciliation for failed writes.

Each approach has trade-offs; storing both directions is a **modeling decision**, not a default mandated by Redis.

### 4.3. Relationship keys are not foreign keys

Redis does not prevent states like:

~~~text
shop:customer:42:orders contains ID 1001
but shop:order:1001 has been deleted.
~~~

Member `1001` is now an **orphan reference**. Redis still treats the SET/ZSET as valid, and there is no foreign key constraint automatically purging members. Conversely, an order may exist without ever being added to the link key, hiding it from the customer's list.

The application must define a policy when detecting orphan references: skip on read, remove the broken member, reload from the authoritative data source, enqueue recovery, or raise an error per requirements.

### 4.4. Embedded ID field vs. separate link key?

Not every relationship needs an independent link key.

When an order belongs to exactly one customer, `customerId=42` inside HASH `shop:order:1001` suffices to answer "who owns this order?" in one read. The link key `shop:customer:42:orders` is only needed if you must quickly answer the reverse question: "which orders belong to this customer?".

An effective design rule:

- **Reading child to parent:** consider storing the parent ID directly inside the child's data.
- **Reading parent to many children:** consider a SET/ZSET holding child IDs.
- **Directions rarely queried:** avoid creating extra keys that require continuous synchronization.

### 4.5. Spring Data Redis `@Reference` does not turn Redis into a relational DB

Spring Data Redis provides `@Reference` to point to separately stored Redis objects and resolve references during mapping within repository capabilities.

Illustrative example of referenced entities:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("shop:order")
public class OrderSnapshot {

    @Id
    private String id;

    private String customerId;

    @Indexed
    private String status;

    // Constructors, getters, setters required for mapping.
}
~~~

On another entity, a field can be annotated with `@Reference` pointing to a separately stored entity. However:

- Reference mapping **is not a foreign key constraint** in Redis server.
- There is no default cascading save/delete for referenced objects; each entity has its own lifecycle.
- References address object-graph representation/reading, while querying "all orders of a customer" still needs an appropriate access path: secondary index, application-managed relationship key, or another data store.

Do not use `@Reference` assuming bidirectional relationships, joins, and cascading deletes will behave like JPA.

## 5. How do the three keys work together?

Consider the flow of creating order `1001` for customer `42` with status `PAID`:

~~~mermaid
sequenceDiagram
    participant S as Spring Service
    participant R as Redis
    S->>R: HSET shop:order:1001 ...
    Note right of R: Primary data
    S->>R: SADD shop:order:by-status:PAID 1001
    Note right of R: Status index
    S->>R: ZADD shop:customer:42:orders timestamp 1001
    Note right of R: Link customer → order
    S->>R: SMEMBERS shop:order:by-status:PAID
    R-->>S: [1001, ...]
    S->>R: HGETALL shop:order:1001
    R-->>S: customerId, status, amount, ...
~~~

**The trio must be kept consistent according to business rules**:

| Change | Primary key | Index key | Relationship key |
|---|---|---|---|
| Create order | Create new HASH | Add ID to status group | Add ID to customer's order list |
| Change status `PENDING → PAID` | Update `status` field | Remove ID from PENDING index, add to PAID | Unchanged if customer did not change |
| Change customer (if allowed) | Update `customerId` | Status index unchanged | Remove from old customer, add to new customer |
| Delete order | Delete HASH | Remove ID from all relevant indexes | Remove ID from all relevant relationships |
| HASH TTL expires | HASH disappears | Risks leaving orphan IDs if self-managed | Risks leaving orphan IDs if self-managed |

This table shows that whenever a field used for indexing or linking changes, **updating only the HASH is not enough**.

## 6. A unified key organization scheme

### 6.1. Naming conventions

Establish a rule derivable from data type, role, and query condition:

~~~text
<app>:<entity>:<id>                         # Primary key
<app>:<entity>:by-<field>:<fieldValue>       # Index key
<app>:<parent>:<parentId>:<children>         # Relationship key
~~~

Examples:

~~~text
shop:order:1001
shop:order:by-status:PAID
shop:customer:42:orders
~~~

This is an **application convention**, not a mandatory Redis standard. `:` is only a separator and does not create a security namespace or sub-database.

Avoid vague names like `users`, `data1`, or `lookup` without indicating role. Whenever multiple key roles could collide on the same string, add markers like `by-` or `relation:` so a HASH is never overwritten with a SET.

### 6.2. Be careful with attribute values inside index key names

When indexing by email, URL, address, or user-supplied strings, define normalization and encoding rules:

- Should email lookups be case-insensitive?
- Can values contain `:` delimiters or Unicode?
- Could normalization collapse two genuinely distinct values into one?
- Could the key leak PII or secrets into logs and monitoring tools?

For sensitive attributes, use an appropriate lookup identifier, or a hash/HMAC strategy designed with reverse-lookup risks and secret key management in mind. Merely calling a generic `hash()` does not ensure information security.

### 6.3. Do not confuse key names with data structure types

Redis enforces the actual value type. If `shop:order:by-status:PAID` already exists as a STRING, calling `SADD` on that key returns a `WRONGTYPE` error. Define explicit types per key pattern and prevent different parts of the system from creating the same key name with different types.

Useful inspection commands in test environments:

~~~redis
TYPE shop:order:1001
TYPE shop:order:by-status:PAID
TYPE shop:customer:42:orders
TTL shop:order:1001
SCARD shop:order:by-status:PAID
ZCARD shop:customer:42:orders
~~~

Expected types here might be `hash`, `set`, and `zset`. If a key does not exist, `TYPE` returns `none`; that is not necessarily a logic bug when caches have TTLs.

## 7. Managing all three key types yourself with Spring Data Redis

### 7.1. Example using `StringRedisTemplate`

The code below explicitly shows which Redis operation writes each key role. It is suitable for **learning the model and building read models/caches**; three independent write commands **do not guarantee atomicity**.

~~~java
import java.util.Map;
import java.util.Set;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderRedisView {

    private final StringRedisTemplate redis;

    public OrderRedisView(StringRedisTemplate redis) {
        this.redis = redis;
    }

    private String orderKey(String orderId) {
        return "shop:order:" + orderId;
    }

    private String statusIndexKey(String status) {
        return "shop:order:by-status:" + status;
    }

    private String customerOrdersKey(String customerId) {
        return "shop:customer:" + customerId + ":orders";
    }

    public void putOrder(
            String orderId,
            String customerId,
            String status,
            long createdAtMillis
    ) {
        // (1) Primary key: order data HASH.
        redis.opsForHash().putAll(
                orderKey(orderId),
                Map.of(
                        "id", orderId,
                        "customerId", customerId,
                        "status", status,
                        "createdAt", Long.toString(createdAtMillis)
                )
        );

        // (2) Index key: SET of IDs by status.
        redis.opsForSet().add(statusIndexKey(status), orderId);

        // (3) Relationship key: ZSET of order IDs per customer.
        redis.opsForZSet().add(
                customerOrdersKey(customerId),
                orderId,
                createdAtMillis
        );
    }

    public Map<Object, Object> getOrder(String orderId) {
        return redis.opsForHash().entries(orderKey(orderId));
    }

    public Set<String> findOrderIdsByStatus(String status) {
        Set<String> ids = redis.opsForSet().members(
                statusIndexKey(status)
        );
        return ids == null ? Set.of() : ids;
    }

    public Set<String> findRecentOrderIdsForCustomer(
            String customerId,
            long maxItems
    ) {
        if (maxItems <= 0) {
            return Set.of();
        }
        Set<String> ids = redis.opsForZSet().reverseRange(
                customerOrdersKey(customerId),
                0,
                maxItems - 1
        );
        return ids == null ? Set.of() : ids;
    }
}
~~~

The list query methods return **IDs**, because the SET/ZSET stores only IDs. To display full orders, read the HASH for those IDs. Pipelining/batching can reduce network round trips, though pipelining **does not automatically create an atomic transaction**.

This example omits status changes, customer changes, deletes, duplicate writes, retries, and request concurrency. Calling `putOrder()` twice with the same ID and different statuses leaves an orphan ID in the old status index. This illustrates why **key design must be paired with write-lifecycle design**.

### 7.2. Choosing Redis Repositories vs. direct templates?

| Approach | Strengths | What you still must design |
|---|---|---|
| `CrudRepository` with `@RedisHash` / `@Indexed` | Framework maps objects, IDs, and managed secondary indexes | Supported queries, TTL, mapping, authoritative data source, complex relationships |
| `StringRedisTemplate` / `RedisTemplate` | Exact control over keys, types, commands, layout, and queries | Manual index/link creation, updates, and deletion; concurrency; orphan cleanup |
| Hybrid | Repository for some data and templates for custom read models | Define clear ownership boundaries; never overwrite repository metadata/indexes manually |

Do not assume that `@Indexed` on an entity updates an arbitrary SET created with `StringRedisTemplate`. **Framework-managed indexes** and **application-managed indexes** are two separate mechanisms, even when stored in the same Redis.

## 8. Consistency across creates, updates, and deletes

### 8.1. Partial failure is the most common cause

A flow creating three keys with three commands:

~~~text
HSET order:1001                 ✅
SADD by-status:PAID 1001        ✅
ZADD customer:42:orders ...     ❌ timeout
~~~

Even though the first two succeeded, the overall request may fail. Naive retries can insert IDs into the wrong index or cause side effects. For SETs, re-adding the same member is idempotent; for ZSETs, re-adding the same member updates its score. **Individual `SADD`/`ZADD` idempotency does not make the whole business flow idempotent**.

If all three keys reside on the same Redis instance and can be manipulated together, consider `MULTI/EXEC`, Lua scripts, or purpose-built atomic commands. Even then, understand their limits:

- `MULTI/EXEC` executes queued Redis commands in a transaction, but does not perform SQL-style rollback of prior writes if one command errors at execution time.
- Lua runs isolated from other Redis commands while executing, yet errors raised midway through do not automatically undo earlier writes in the script.
- Redis Cluster enforces **hash slot** constraints on multi-key transactions/scripts; arbitrary keys across slots cannot participate together.
- If PostgreSQL/MySQL is the source of truth, a Redis transaction does not form a cross-system ACID transaction across Redis and the relational database.

For rebuildable caches/read models, a common strategy is accepting **controlled eventual consistency**: emit update events upon database commit, retry idempotently, and reconcile periodically. For data requiring strict invariants, place those invariants in a store with suitable transactional guarantees.

### 8.2. Status changes must update old and new indexes

When `status` transitions from `PENDING` to `PAID`, the intended sequence of mutations is:

~~~redis
HSET shop:order:1002 status PAID
SREM shop:order:by-status:PENDING 1002
SADD shop:order:by-status:PAID 1002
~~~

This describes the required mutations, **not a guarantee that three standalone commands are atomic or safe against concurrent requests**.

If two concurrent requests change status, both may read the same old status and overwrite indexes out of order. Depending on requirements, use version checks / optimistic locking, server-side logic, appropriate transactions, or per-ID serialized updates.

A helpful rule: **every field appearing in an index name or score must have an explicit index-migration rule when that field changes**.

### 8.3. Ownership changes must migrate links

If business rules allow reassigning order `1001` from customer `42` to `57`, update the customer field and both relationship keys:

~~~redis
HSET shop:order:1001 customerId 57
ZREM shop:customer:42:orders 1001
ZADD shop:customer:57:orders 1710000000000 1001
~~~

For bidirectional relationships, update both sides accordingly. Never add a reverse link merely for convenience and forget the deletion/reassignment paths.

### 8.4. Deleting a primary key does not delete self-managed indexes or links

~~~redis
DEL shop:order:1001
~~~

This command **deletes only the named key**. Redis will not search `shop:order:by-status:PAID` or `shop:customer:42:orders` to remove member `1001`.

With self-managed keys, the application usually needs the old status and customer ID before deleting:

~~~text
Read old HASH → extract status and customerId
        ↓
Remove ID from status index
        ↓
Remove ID from customer link
        ↓
Delete primary HASH (or coordinate within a safe atomic operation)
~~~

If the authoritative source is an external database, another workflow may apply (DB commit → emit event/invalidation → update read model). Whichever order you choose, specify what happens if any step fails and whether commands can be retried safely.

### 8.5. TTLs can leave orphan members behind

Suppose a TTL is set on the order hash:

~~~redis
EXPIRE shop:order:1001 600
~~~

After 10 minutes, the HASH may vanish while self-managed SET/ZSETs still retain ID `1001` because they are **independent keys**. Result:

~~~text
SMEMBERS shop:order:by-status:PAID  → includes "1001"
HGETALL shop:order:1001            → empty
~~~

Options include:

- Aligning lifetimes on indexes/links when keys share semantics and suitable TTLs.
- Removing members during delete/expiration handlers with retry and reconciliation.
- Ignoring missing IDs on read and flagging them for cleanup.
- Periodically rebuilding indexes/links from the source of truth or when drift is detected.

With **Spring Data Redis Repositories**, the framework supports maintaining secondary indexes and mechanisms tied to key expiration events. However, Pub/Sub keyspace notifications are not durable queues; disconnected clients can miss events. Never assume self-managed links/indexes clean themselves up perfectly when entity TTLs expire.

## 9. Redis Cluster changes multi-key update capabilities

In Redis Cluster, Redis places each key into a **hash slot**. Two keys typically map to different slots, for example:

~~~text
shop:order:1001
shop:order:by-status:PAID
shop:customer:42:orders
~~~

Commands operating on **multiple keys as an atomic group** must obey Cluster slot rules. If your design requires multi-key operations in the same slot, you can use a **hash tag** enclosed in curly braces.

Example:

~~~text
shop:customer:{42}
shop:customer:{42}:orders
~~~

Both names share hash tag `42`, so they map to the same slot. However, `shop:order:{1001}` has a different tag; you cannot assume everything related can be updated in a single multi-key transaction.

Hash tags are an architectural decision:

- Co-locating multiple keys of the same customer in one slot can help certain operations.
- Stuffing all data into one tag to dodge `CROSSSLOT` errors causes skewed load and loses sharding benefits.
- Global status indexes hold order IDs across many customers, making "shard by customer" and "atomically update global status index" difficult to satisfy together.

Thus, **key design must account for both query patterns and topology**. A design that works cleanly on standalone Redis does not automatically retain the same properties in Redis Cluster.

## 10. When do index and link keys become expensive?

Every index/link key increases memory footprint and write amplification. Specifically:

1. **High cardinality:** indexing a nearly unique attribute creates huge numbers of tiny keys; consider direct STRING lookups by value if truly required.
2. **Large SET/ZSETs:** a `PAID` bucket with millions of IDs creates a huge key. `SMEMBERS` returns all members at once, spiking latency and response sizes.
3. **Index update fan-out:** one state change mutating multiple composite indexes increases command counts and desynchronization risk.
4. **Paginated queries:** `ZREVRANGE` is ordered; SETs lack stable ordering for pagination. For large sets, use score/rank queries and appropriate cursors.
5. **Stale accumulation:** indexes/links left uncleaned after primary keys are deleted produce wrong query results and waste RAM.

`SCAN` iterates the keyspace incrementally for maintenance tasks, yet **cannot replace a purposefully designed query index**. Similarly, `SSCAN`/`ZSCAN` iterate members incrementally and can return duplicates; if ordered pages are required, pick appropriate data structures and pagination strategies. Never run `KEYS shop:order:*` on a large Redis per user request.

A design decision table:

| Question | If "yes" | Recommendation |
|---|---|---|
| Accessed primarily by exact ID? | Yes | Primary key alone may suffice |
| Need fast filtering by status? | Yes | Status-based SET index |
| Need top-N / chronological order? | Yes | ZSET index or relationship ZSET |
| Need parent-to-many-children lookups? | Yes | SET/ZSET link depending on ordering |
| Need lookup by a unique code other than ID? | Yes | Uniqueness-controlled STRING lookup |
| Data mutates very frequently with complex relations/indexes? | Yes | Reduce index count or use a specialized database/search engine as the query source |

There is no "more indexes is always better" rule. An index is worthwhile only when the query it serves justifies its maintenance cost.

## 11. A practical key design workflow

Suppose the system requirement is:

> Display order details by ID; filter orders by status; show a customer's 20 most recent orders.

Work from **query requirements** to keys:

| Query | Key accessed | Typical command |
|---|---|---|
| Details of order 1001 | `shop:order:1001` | `HGETALL` |
| IDs of PAID orders | `shop:order:by-status:PAID` | `SMEMBERS` or `SSCAN` as appropriate |
| 20 newest orders of customer 42 | `shop:customer:42:orders` | `ZREVRANGE 0 19` |

Then define lifecycle rules:

| Business event | Primary hash | Status index | Customer link |
|---|---|---|---|
| Create order | Write hash | `SADD` | `ZADD` |
| Change status | `HSET` | `SREM` old / `SADD` new | Unchanged |
| Delete order | `DEL` | `SREM` | `ZREM` |

If the data is a rebuildable cache, add TTLs, reconciliation, and staleness limits. If it is authoritative data affecting finances or inventory, first establish transactions and constraints in the appropriate primary data store.

In a real system, document a brief specification right inside the module: key patterns, Redis types, keyspace/DB, serializers, TTLs, write owners, queries served, and update/delete flows. This prevents one team from treating `shop:order:1001` as a HASH while another treats the same key name as a STRING.

## 12. Typical mistakes

**Mistake 1 — Calling every Redis key a "primary key".**

This obscures the difference between entity data and query-supporting structures. When deleting `shop:order:1001`, applications may forget to remove external ID references.

**Mistake 2 — Assuming `@Indexed` behaves like a relational unique constraint.**

`@Indexed` provides field lookups within repository mapping boundaries. It does not guarantee uniqueness, referential integrity, or arbitrary joins/queries.

**Mistake 3 — Updating a HASH and assuming indexes update automatically.**

With template-managed SET/ZSETs, Redis has no knowledge that a HASH field maps to an index member. Synchronization rules must be implemented explicitly.

**Mistake 4 — Storing full object copies inside relationship keys.**

If a link key stores full object copies instead of IDs, the same order gets duplicated everywhere and drifts out of sync on updates. Storing IDs preserves a single entity read point, trading off an extra dereference step.

**Mistake 5 — Deleting a data key or letting its TTL expire and assuming all links vanish.**

Independent SET/ZSETs remain. Set appropriate TTLs or cleanups per key role, and plan for missed cleanup events.

**Mistake 6 — Using multi-key transactions as in standalone without considering Cluster.**

Hash slots dictate which keys can participate in multi-key operations. Design partitioning early whenever sharding is planned.

**Mistake 7 — Querying large SETs with `SMEMBERS` on every request.**

SETs have no guaranteed order and returning all members can send massive payloads. Choose structures and pagination matching real dataset sizes.

## 13. Remember the core distinctions

- **Primary key:** identifies the entity and leads directly to the entity's data, e.g., `shop:order:1001`.
- **Index key:** maps a search predicate to IDs, e.g., `shop:order:by-status:PAID`.
- **Relationship key:** maps an entity association to related IDs, e.g., `shop:customer:42:orders`.

A relationship key can technically be viewed as an index by parent ID, yet separating its name and design responsibility reminds engineers that **it is an association requiring maintenance whenever entities are created, reassigned, or deleted**.

When using **Spring Data Redis**, first decide who owns each key: **Redis Repositories** or **application logic written with `RedisTemplate`**. Next define read paths, update paths, desync prevention, TTLs, and Redis topology. Only then pick SET, ZSET, HASH, and exact key naming patterns.

## References

- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html)
- [Spring Data Redis — Secondary Indexes](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/indexes.html)
- [Spring Data Redis — Object References](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/references.html)
- [Spring Data Redis — Key Expirations](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html)
- [Redis — Hashes](https://redis.io/docs/latest/develop/data-types/hashes/)
- [Redis — Sets](https://redis.io/docs/latest/develop/data-types/sets/)
- [Redis — Sorted Sets](https://redis.io/docs/latest/develop/data-types/sorted-sets/)
- [Redis — Redis Cluster Specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/)
