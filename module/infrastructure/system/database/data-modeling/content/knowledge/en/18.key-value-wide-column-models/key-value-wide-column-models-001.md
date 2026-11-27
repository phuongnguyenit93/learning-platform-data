# Key–Value Models and Choosing the Atomic Access Unit

## Learning Objectives

After this lesson, you will be able to:

- Explain the **key–value** model, how applications look up data by key, and the limitations when querying by attributes or relationships.
- Translate business requirements into **access patterns** to decide which data should reside together in a single value and which data should be split across separate keys.
- Design keys, value structures, lifecycles, and update rules for a real-world scenario, and identify issues arising from concurrent updates.
- Evaluate trade-offs regarding value size, read/write round trips, consistency, hot keys, and scalability.
- Know when to use a key–value model and when a relational, document, or wide-column model is more appropriate.

In **DATABASE_DATA_MODELING**, the goal is to build the skill of moving from business requirements to verifiable entities, relationships, constraints, and physical schemas. The key–value model illustrates a very different starting point from beginning with tables and joins: first, we ask **which keys does the application know, and what slice of data does it need to retrieve together?**

## 1. The Essence of the Key–Value Model

At a conceptual level, a key–value store maps a **key unique within the store's scope** to a **value**:

```text
key -> value

cart:shop_17:user_42 -> {"items":[{"sku":"A17","qty":2}]}
session:s_89          -> {"userId":"u_42","role":"buyer"}
feature:checkout:v2  -> {"enabled":true}
```

Basic operations typically take the following form:

| Operation | Meaning |
| --- | --- |
| `get(key)` | Retrieve the value associated with a known key. |
| `put(key, value)` | Create or update the value bound to a key. |
| `delete(key)` | Remove the key–value mapping. |
| Multi-key `get` or conditional operations | May be provided by the DBMS; syntax, guarantees, and limits vary by product. |

A **key** is typically a string or an identifier that can be encoded deterministically. A **value** can be text, raw bytes, serialized JSON, or a data type supported by the DBMS. A basic key–value database does not necessarily understand the attributes inside the value: the application is responsible for interpreting them.

For example, if you only know `GET cart:shop_17:user_42`, you can retrieve that user's cart quickly and directly. However, the question "how many carts contain SKU A17?" **does not automatically have an efficient solution** under the same design: this query does not have the keys of the target carts upfront.

Some commercial systems offer additional capabilities such as secondary indexes, structured data types, queries, or transactions. These are **product-specific DBMS capabilities**, not mandatory properties of every key–value model.

> **Distinction:** "Reading one value by one key" describes the **logical unit of access**. "Atomic update" describes a **transactional guarantee**. Reading an entire value does not by itself prove that a read–modify–write sequence is safe under concurrent updates.

## 2. Start from Access Patterns, Not Table Structures

Suppose an e-commerce system needs to manage shopping carts. Before naming keys or choosing Redis, DynamoDB, or another system, list the business behaviors.

| Business Action | Known Inputs | Data to Retrieve or Modify | Frequency / Requirements |
| --- | --- | --- | --- |
| Open cart | Shop ID and user ID | Full list of items and quantities | Frequent; low-latency reads |
| Add or change quantity | Shop ID, user ID, SKU | One item in the cart; return new state | Frequent; avoid lost updates |
| Remove expired carts | Cart key or expiration policy | Entire cart | Lifecycle-driven; can expire automatically |
| Confirm checkout | Shop ID and user ID | Cart snapshot and current price/inventory | Must revalidate against authoritative data sources |
| Popular SKU report | Time range, SKU | Many carts or transaction events | Aggregate query; requires a separate read model |

The first three rows point toward accessing the cart via a stable key. The last two rows show that **a single cart value should not be forced to solve every problem**, especially purchase transactions and analytics.

A useful line of reasoning:

1. **Who knows the key?** The cart screen knows the shop ID and user ID; system-wide reports typically do not know individual cart keys.
2. **To what extent is data read together?** If every page load requires fetching all items in the cart, grouping them can reduce round trips.
3. **To what extent is data written together?** If multiple devices edit the same cart, contention must be controlled; if parts are modified independently at high frequency, grouping can create a bottleneck.
4. **Do items live and expire together?** Items in a cart can share a single TTL; a completed order requires its own lifecycle and durability guarantees.
5. **Are there constraints or queries that span beyond a single value?** For example, enforcing email uniqueness across users, aggregating monthly revenue totals, or joining products with suppliers.

This is the process of identifying the **monolithic (atomic) access unit**: a group of data that most business operations need to retrieve, write, or manage in lifecycle as a single unit. This concept is close to an *aggregate* in domain-driven design, though it does not imply every aggregate must be stored under a single key.

## 3. Design Example: One Cart per Key

Business assumptions for this example:

- Each user has at most one active cart per shop.
- The UI typically loads the entire cart; carts are usually small, though a size limit must still be enforced.
- Unchecked-out carts can expire 30 days after the last update.
- A user may open multiple tabs or devices and edit the cart concurrently.
- Selling prices, promotions, and inventory are revalidated at checkout; the cart only stores references and desired quantities.

### 3.1. Choosing the Key

```text
cart:<shopId>:<userId>
cart:shop_17:user_42
```

This key structure both namespaces the `cart` domain and ensures two shops can maintain separate carts for the same user. When designing keys, clarify:

- **Uniqueness:** one `(shopId, userId)` pair maps to one active cart; if the business allows multiple carts, add `cartId` or revise the mapping.
- **Stability:** avoid using mutable attributes like email, phone number, or display name as the primary identifier.
- **Parseability:** if IDs can contain the `:` delimiter, use encoding rules or an unambiguous key format.
- **Privacy:** keys may appear in logs, metrics, and backups; prefer internal IDs over sensitive data.
- **Partitioning:** keys affect load distribution; if the DBMS hashes keys, an extremely popular key can create a *hot key*.

There is no universal key syntax across all products. Colons here are a readability convention, not a requirement of the model.

### 3.2. Choosing the Value

```json
{
  "schemaVersion": 1,
  "cartId": "c_908",
  "revision": 8,
  "items": [
    { "sku": "A17", "quantity": 2 },
    { "sku": "B03", "quantity": 1 }
  ],
  "updatedAt": "2026-11-22T01:30:00Z"
}
```

Field explanations:

| Field | Role |
| --- | --- |
| `schemaVersion` | Allows the application to read and migrate values across structural versions. |
| `cartId` | Business ID of the cart, useful for logging or linking with the order placement flow. |
| `revision` | Logical version number supporting update checks; **only provides protection** if the storage engine offers conditional writes or suitable transactions. |
| `items` | Items typically read together; each SKU appears at most once. |
| `updatedAt` | Timestamp for business logic or observability; does not replace the store's TTL mechanism. |

**TTL (time to live)** should be managed by the storage engine's built-in expiration feature when available, rather than assuming an `updatedAt` field will delete data on its own. Whether TTL is renewed on every access or only on updates is a **business rule** that must be explicitly specified. Physical deletion may not occur to the exact millisecond at expiration time.

### 3.3. Reading and Updating

Reading a cart is a single key lookup:

```text
key = "cart:shop_17:user_42"
cart = store.get(key)
if cart is absent:
    cart = empty_cart()
return cart
```

When adding a SKU, the application might perform a read–modify–write cycle. However, if two devices read the same `revision = 8`, and device A adds SKU C01 while device B changes the quantity of A17, both overwriting the entire value can cause one of the two changes to be lost.

Therefore, you need **version-conditional writes** or atomic operations supported by the DBMS. The code below is **product-agnostic pseudocode**, not commands for a specific database engine:

```text
function setQuantity(shopId, userId, sku, quantity):
    key = cartKey(shopId, userId)

    repeat with bounded retries:
        current, storageVersion = store.getWithVersion(key)
        next = changeQuantity(current or emptyCart(), sku, quantity)
        validate(next)

        ok = store.putIfVersionMatches(
            key,
            expectedVersion = storageVersion,
            value = next,
            ttl = 30 days
        )
        if ok:
            return next

    raise ConcurrentUpdateError
```

Key takeaway: the loop is only safe if **checking the version and writing** form an atomic operation guaranteed by the data store. Simply incrementing `revision` inside the JSON and calling a regular `put` is **not sufficient**. Systems without compare-and-swap (CAS) support will need another suitable mechanism, such as atomic update operations, product-specific scripts/transactions, or a change in data model.

In production APIs, also set a bounded retry limit, handle duplicate requests with an idempotency key where needed, and surface clear conflict responses. Never run an unbounded retry loop when a key is under continuous contention.

## 4. Deciding Value Boundaries: Combine or Split?

There is no blanket rule stating "everything belonging to the same entity goes into one value." Compare options against **the exact business operations you must support**.

| Option | Illustrative Storage Layout | Pros | Costs / Risks |
| --- | --- | --- | --- |
| **Whole cart in one value** | `cart:shop_17:user_42 → {items:[...]}` | Single read for full cart, shared expiration, simple UI rendering | Editing one item may rewrite the whole cart; update contention; growing value size |
| **One item per key** | `cart-item:c_908:A17 → {quantity:2}` | Independent per-item updates, small values | Need to know/discover SKU list; loading cart requires multiple keys; full cart deletion and item synchronization are complex |
| **Cart + separate items** | `cart:c_908 → {itemIds:[...]}` plus multiple item keys | Flexible when individual items are large or change independently | Risk of list and item keys getting out of sync; often requires transactions or repair mechanisms |
| **Structured data store** | Document with field-level updates; or relational `Cart`/`CartItem` tables | Supports element updates, indexing, or constraints depending on engine capabilities | Modeling and operational costs depend on the DBMS |

In this example, **one key per cart** is a sensible starting point because whole-cart reads dominate, items share the same lifecycle, and size is bounded. If reality shows large carts, frequent independent concurrent edits, or queries across carts by SKU, the boundary must be reconsidered.

### 4.1. Five Questions for Choosing the Monolithic Unit

1. **Co-read:** are the fields almost always read together? If only 5% of requests need a large blob, do not force the other 95% to load it.
2. **Co-write:** do the fields truly need to change together? A single value can simplify full-replacement writes, but increases contention across unrelated updates.
3. **Lifecycle:** do they share the same owner, TTL, access permissions, deletion conditions, and retention policy?
4. **Bounds:** are the maximum size and growth rate acceptable under the storage engine's limits, bandwidth, latency, and cost?
5. **Consistency:** which invariants must hold immediately after every write? Do they reside entirely within one value or span multiple keys / data sources?

A sound boundary is usually where data is **read together frequently enough**, **modified with acceptable contention**, and **shares a common lifecycle**. This decision is measured from the workload, not merely from looking at JSON structure.

### 4.2. How "Monolithic Access Unit" Differs from "Atomic"

- **Monolithic in access:** the application fetches one logical unit using key `cart:shop_17:user_42`.
- **Atomicity of a single write:** the system may guarantee no half-written value is observed; you must check the contract of the specific command and product in use.
- **Atomicity of read–modify–write:** the entire sequence requires version conditions, server-side operations, or transactions to prevent lost updates.
- **Atomicity across multiple keys:** usually requires separate mechanisms; it cannot be inferred from single-key atomicity.

For example, combining `items` and `coupon` into the same value allows reading a consistent cart at a single version. However, it does **not** guarantee that deducting inventory, creating an order, and recording payment happen as a single cross-system transaction.

## 5. From Key Lookups to Query Models

The key–value model shines when the application already knows the key. Classify your requirements:

| Question to Answer | Key Known? | Design Direction |
| --- | --- | --- |
| "What is user U's cart at shop S?" | Yes: `(S,U)` | Direct single-key lookup. |
| "Who owns the session with token T?" | Yes: `T` or an appropriate hash | Single key bound to the session and TTL. |
| "Find all users by city?" | No | Needs query indexes, document, relational, or an appropriate analytics pipeline. |
| "Which carts contain SKU A17?" | No | Needs a separate read model/index; do not scan all keys for regular requests. |
| "User U's 10 most recent orders?" | U is known, but sorting and filtering are needed | May need a dedicated list key, a table with a sort key, a wide-column model, or a relational model. |

If two mandatory lookup patterns exist, such as `userId → profile` and `email → userId`, you can maintain an additional mapping key `email-index:<normalized-email> → userId`. However, updating an email must keep **both mappings consistent** and enforce email uniqueness under concurrent writes. A relational database with a unique constraint or a document database with a unique index may be a better fit. Simple `put` operations on two keys do not automatically enforce uniqueness constraints.

**Avoid designs that rely on "scanning all keys"** to serve regular business queries. Some products support key iteration for administration or background jobs, but full scans are not a substitute for bounded, indexed query strategies.

## 6. Constraints, Consistency, and Lifecycle

A structured value still needs an explicit set of rules.

### Constraints Within a Single Value

For a shopping cart, the application must validate:

- `quantity` is a positive integer within business limits.
- No two items share the same `sku`; remove the item when quantity reaches 0 if that is the API rule.
- Item count and overall payload size are bounded; missing data or unknown fields are handled according to `schemaVersion`.
- Key IDs (shop, user) and IDs inside the payload, if duplicated, must not contradict each other.
- Every value has its schema validated at the **write boundary**, not only during UI rendering.

The database may treat JSON as raw bytes and **will not enforce** these rules. Application code, API contracts, or product-provided schema validation features must take responsibility.

### Constraints Across Multiple Values

For example, "only one user owns email X" or "once an order is created, inventory quantities must be reserved" involves multiple keys and potentially multiple services. You must choose deliberately among:

- Transactions or conditional writes supported by the DBMS.
- Redesigning boundaries so fields requiring an invariant sit within a single update unit.
- Stateful multi-step workflows with idempotency, verification, and compensation if eventual consistency is acceptable.

Never assume "strong consistency" or "multi-key transactions" simply because a system belongs to the key–value category. Guarantee levels vary by DBMS, configuration, and command used.

### Expiration and Durability

TTL is suitable for login sessions, caches, or temporary carts when the business tolerates data disappearing. Clarify explicitly:

- Does TTL start at creation or refresh on every activity?
- After expiration, what does a read return and how does the application reconstruct state?
- When the store is under resource pressure, can the system evict data before TTL?
- To what extent must data be persisted, backed up, and recovered? Is losing carts after a crash acceptable?

**Cache and primary source of truth** are two distinct architectural roles. A key–value store can serve as the primary store if its durability, recovery, and update guarantees meet requirements; conversely, never place the sole record of a payment inside an evictable cache.

## 7. Size, Performance, and Partitioning

Key-based access often keeps the read path simple, yet total cost still depends on value design:

| Symptom | Cause | Mitigation |
| --- | --- | --- |
| Unbounded value growth | Appending history or infinite lists into one key | Enforce bounds, paginate with a different model, separate cold data |
| Rewriting many bytes to change one field | System requires full-value replacement | Consider field-level updates if supported or change boundaries |
| Frequent conflicts and retries | Many actors updating the same key | Measure contention; partition by writer or switch to appropriate atomic operations |
| Hot key | One key receives heavy traffic despite many partitions | Redesign work distribution; for additive counters, consider sharding and on-demand aggregation |
| Loading many keys for one screen | Splitting data too finely | Co-locate co-read data, or use batch/pipelining supported by the DBMS |
| Difficult analytical queries | Only key-based access paths exist | Build a separate read model/index or feed data into an analytics system |

You can roughly estimate the network payload of full-value writes:

```text
Approximate write payload ≈ updates/sec × average value size

Example: 500 updates/sec × 20 KiB/value ≈ 9.8 MiB/sec of payload data.
```

This is only a **one-way payload traffic estimate**, excluding replication, protocol overhead, logging, compression, pre-write reads, or retries; it cannot directly predict latency or server capacity. In particular, observe size percentiles (p95/p99), not just averages, because a few large outliers can dominate tail latency.

Hash-based key partitioning distributes **many independent keys** well, but does not automatically split traffic for a **single hot key**. Do not append random suffixes to keys if doing so makes the application lose direct lookup capability without a corresponding index.

## 8. Comparison with Other Data Models

The goal of data modeling is to choose structures that serve queries and business rules, not to pick one "best" model for every situation.

| Model | Typical Access | When It Fits Better |
| --- | --- | --- |
| **Key–Value** | Key known → retrieve/update one value or run supported operations | Sessions, caches, small carts, config by ID, transient state |
| **Document** | Read document by ID, often with queries/indexes on internal attributes | Flexible-schema records, multi-field search, sub-field updates (system-dependent) |
| **Wide-column** | Partition key, rows/columns, and ordering within a partition per a specific model | Logs/events or time series queried by entity and time range at very large scale |
| **Relational** | PK/FK, joins, filter predicates, transactions, and declarative constraints | Rich business relationships, multi-record updates, and strong integrity requirements |
| **Graph** | Nodes, edges, and multi-hop relationship traversal | Evolving connections, path/proximity queries |

For example, "the 50 most recent logins of user U" initially looks like `userId → value`, but an event sequence can grow without bound. Storing the entire history in a single blob forces every new login to rewrite a large payload and makes time-range reads awkward. A wide-column model partitioned by user and time bucket, with a clustering/sort key by timestamp, may make more sense. However, terms like "partition key," "clustering key," partition size limits, and update semantics **depend on the product**—rules from one database should not be assumed across all of them.

Models can be combined: keep active carts by key; persist official orders in a relational system; emit order events to an analytics pipeline. Boundaries are defined by the authoritative data source, consistency requirements, and access paths—not by a generic NoSQL label.

## 9. Anti-Patterns and How to Fix Them

### Anti-Pattern A: One Key Holding All User Activity

```text
user:u_42 -> {
  profile: {...},
  cart: {...},
  orders: [hundreds of thousands of items],
  activityLog: [millions of events]
}
```

Problems: reading a profile loads unrelated history; orders and activity have different lifecycles from the cart; every event write contends on the same key; size has no clear bound. Split small cart state, profile, orders, and event streams into units with their own access models. Key–value can still be used for the appropriate parts.

### Anti-Pattern B: One Key per Field Without a Business Reason

```text
profile:u_42:name    -> "An"
profile:u_42:country -> "VN"
profile:u_42:locale  -> "vi"
```

If every screen needs all three fields, the cost of coordinating multiple keys and the risk of fields drifting out of version sync can outweigh the benefits of splitting them. A small, well-schemaed `profile:u_42` value is usually simpler. If individual fields have distinct access permissions or write frequencies, re-evaluate using real metrics.

### Anti-Pattern C: Only Keyed by User, While Reports Need Lookup by SKU

You cannot satisfy "all carts containing A17" merely by pointing out that the JSON includes a SKU field. Build a separate read model or change storage technology if that is a core query. If adding an inverted index, define how the index is updated and repaired upon cart edits, TTL expirations, or failed writes.

## 10. Design and Verification Workflow

When receiving a new requirement, follow this sequence:

1. **Translate business questions into concrete queries.** What are the inputs to each operation? Is the key known? Are filtering, sorting, pagination, or joins needed?
2. **Draw access unit boundaries.** Group fields commonly read and lifecycle-managed together; watch out for data that could grow unboundedly.
3. **List changes that can happen concurrently.** Identify invariants to protect, such as "one row per SKU" or "non-negative quantity."
4. **Define keys and values.** Identifier rules, uniqueness, schema structure, size limits, versioning, TTL, and deletion policies.
5. **Choose protection mechanisms.** Compare CAS, atomic updates, multi-key transactions, and consistency levels truly supported by the engine.
6. **Estimate load and validate against the workload.** Record key counts, read/write rates and distributions, p95/p99 sizes, retry counts, latency, and miss rates.
7. **Test changes and operations.** Test expired data, missing-key reads, schema version upgrades, crash recovery, and concurrent updates; design a migration plan if boundaries change.

### Minimum Test Suite for the Cart Example

| Scenario | Expected Outcome |
| --- | --- |
| Read a non-existent key | Returns an empty cart or "no cart" status per API contract, without ambiguous data errors. |
| Two devices edit the same `revision` | No lost updates; one operation succeeds, the other retries or receives a controlled conflict. |
| Add the same SKU twice | Does not create two lines for the SKU; quantity follows API rules. |
| Exceed item count or size limit | Explicitly rejected or routed to an appropriate model per policy. |
| TTL expiration | System handles the absent cart according to business rules; never assumes `updatedAt` enforces TTL automatically. |
| Legacy schema | Safe read/migration path exists; no silent data loss from format changes. |
| Order confirmation | Revalidates price/inventory, enforces order constraints and idempotency outside the cart value. |

## 11. Guided Practice Scenarios

**Scenario 1 — Per-tenant feature flags.** Every request knows `tenantId` and needs to fetch 10–20 feature flags for the tenant. Flags change only a few times a day and are published together as a configuration version.

- **Suggested model:** `features:<tenantId> → {schemaVersion, flags, publishedAt}`. Because they are read together, change infrequently, and share a lifecycle, a single value is a reasonable choice.
- **What to add:** authoritative configuration source, cache invalidation strategy on new releases, size bounds, and access control.

**Scenario 2 — Device logs.** Each device sends one record per second; the system must display the 1,000 most recent records and filter by time range.

- **Avoid:** appending all records into an unbounded `device:<deviceId>` value; the value will bloat, writes will contend, and time-range queries will be very hard.
- **Appropriate direction:** a time-series store or a wide-column model partitioned by device and time window; choose buckets and sort keys after measuring throughput and the DBMS's specific limits.

**Scenario 3 — High-frequency cart quantity changes.** The system initially stored the whole cart under one key. After launch, p99 update latency spiked, conflict retries surged, and some carts reached thousands of items.

- **How to analyze:** measure size distribution and per-key contention; determine which operations genuinely need to read the entire cart.
- **Adjustment direction:** enforce cart limits; use per-item updates if supported by the product; or split items and adopt a model/index with sufficient guarantees. Do not split mechanically if the cost of loading the full cart and synchronized deletions becomes excessive.

## Summary

A well-designed key–value model starts from **access patterns with known keys** and **data boundaries that truly belong together**. Grouping data makes reads convenient and can simplify lifecycle management; splitting data enables independent updates, avoids unbounded growth, and reduces contention in certain workloads. The right decision must account for queries, concurrent updates, business constraints, TTL, durability, and operations.

When reviewing a design, ask yourself three questions: **Which keys does the application know? Which exact slice of data does one access require? What must remain consistent after every change?** If a requirement cannot be satisfied by key lookups at an acceptable cost, that is a signal you need a different access model or a different storage technology.
