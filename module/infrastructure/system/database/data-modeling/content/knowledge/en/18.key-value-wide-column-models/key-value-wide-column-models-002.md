# Keyspace Design, Composite Keys, and Naming Conventions

## Learning Objectives

After this lesson, you will be able to:

- Distinguish **business identifiers**, **lookup keys**, **composite keys**, **partition keys**, and **sort/clustering keys** in data modeling.
- Translate access patterns into a consistent **keyspace** with explicit uniqueness scopes and room to evolve.
- Define unambiguous composite key encoding rules, standardize input normalization, and avoid exposing sensitive data in key names.
- Choose appropriate partition keys and sort keys when modeling **key–value** or **wide-column** data.
- Identify hot keys, oversized partitions, prefix misuse, tenant scoping errors, key-renaming risks, and key-version migration issues.
- Build a constraint table and verification checklist for a key design before putting it into production.

In **DATABASE_DATA_MODELING**, moving from business requirements to a clear data model involves choosing entities, relationships, keys, indexes, and physical schemas. For key–value and wide-column stores, **a key does more than identify a record**: how keys are structured can determine access paths, load distribution, scan order, consistency guarantees, and schema evolvability.

---

## 1. Understanding Key Types Correctly

A single business entity can carry multiple identifiers and appear in multiple key structures. For instance, an order has a stable `orderId`, belongs to a `shopId`, is created by a `customerId`, and has a `createdAt` timestamp.

| Concept | Meaning | Example |
| --- | --- | --- |
| **Business identifier** | Identifies an object within a business scope; can be independent of storage layout | `orderId = ord_908` |
| **Storage key** | Input used to locate a value/row in a specific store | `order:v1:shop_17:ord_908` |
| **Namespace** | Naming convention grouping keys by domain, environment, version, or entity | `cart:v1:...`, `order:v1:...` |
| **Composite key** | A key formed from multiple meaningful components | `(shopId, orderId)` |
| **Partition key** | Component determining which region/partition stores the data under the DBMS's mechanism | `(shopId, customerId)` |
| **Clustering/sort key** | Component used to organize or query rows in order **within a partition**, if supported by the product | `(createdAt, orderId)` |
| **Lookup/index key** | Maps from an alternate criterion to the primary identifier | `email-index:v1:<digest> → userId` |

Separate three questions:

1. **Which object is this?** Answered by the business identifier or logical primary key.
2. **How will the application find it?** Answered by the lookup key or index.
3. **Where will the storage engine place and order it?** Answered by the partition key, sort key, and product characteristics.

A **logical composite key** does not have to be concatenated into a single string. A key–value store accepting byte/string keys may need to encode multiple components into one key. In a wide-column model, many DBMSs let you declare separate columns for the partition key and clustering key. Do not confuse both cases with a "colon-delimited string."

> **Terminology note:** "Keyspace" is sometimes the name of a product-specific administrative object, such as a container scope holding tables. In this lesson, **keyspace** primarily refers to *the planning and naming convention for the keys used by the application*; when working with a specific product, verify the exact technical meaning of the term.

## 2. Start from Business Requirements and Access Paths

Suppose a multi-shop commerce platform needs to:

- Open the current cart using `shopId` and `userId`.
- Find an order given `shopId` and `orderId`.
- Display a customer's 20 most recent orders at a shop.
- Filter a customer's order history by date range.
- Look up an account by email during login.
- Aggregate monthly revenue across all shops.

No single key can optimize every requirement at once. Build an **access matrix** before writing key syntax.

| Requirement | Known Inputs | Output / Query Characteristics | Design Implication |
| --- | --- | --- | --- |
| Current cart | `shopId, userId` | One cart | Single lookup key on the ID pair |
| Order details | `shopId, orderId` | One order | An identifier sufficiently unique within the shop |
| Recent orders list | `shopId, userId` | Multiple ordered, bounded orders | Needs ordering within the customer group |
| History by date | `shopId, userId, [from,to)` | Time-range scan | Clustering/sort key and possibly time buckets |
| Login | User-entered email | Find corresponding user ID | Unique index on normalized email |
| Revenue report | Month, shop group | Aggregation across many customers and orders | Separate analytics model or summary tables |

From this matrix, we can design:

```text
cart:v1:<shopId>:<userId>      -> cartDocument
order:v1:<shopId>:<orderId>    -> orderDocument

Order history access path:
partition = (shopId, userId, monthBucket)
sort      = (createdAt DESC, orderId ASC)

Email lookup path:
email-lookup:v1:<emailDigest>  -> userId
```

This is a **conceptual design**. A key–value database that only supports `GET` by key does not natively provide range scans over `sort`; reading a recent orders list requires a separate structure/index or a store that supports ordered keys. Wide-column models are built to support reads by partition key and clustering key range, though which exact queries are valid depends on the DBMS.

## 3. Designing the Key Namespace

A namespace is a **contract between writers and readers**, used to prevent accidental collisions, separate business domains, and support observability and migrations.

A human-readable convention for a key–value system might look like:

```text
<entityType>:<keyFormatVersion>:<tenantId>:<logicalId>

cart:v1:shop_17:user_42
order:v1:shop_17:ord_908
profile:v1:shop_17:user_42
```

To turn the example into an enforceable contract, specify explicitly:

| Component | Rules to Define |
| --- | --- |
| `entityType` | Allowed value set, e.g., `cart`, `order`, `profile`; never mix synonyms like `orders` and `order` |
| `keyFormatVersion` | Version of the **key format** when encoding/structure changes; not every payload version bump requires a new key namespace |
| `tenantId` | Ownership scope; a stable internal ID consistent across services |
| `logicalId` | ID sufficiently unique within the stated scope; clarify whether it is mutable |
| Character encoding | UTF-8 vs. bytes; normalization, escaping, case sensitivity, and empty-value handling |
| Maximum length | Per key-length limits and overhead of the chosen product |
| Naming conventions | Lowercase fixed prefixes, delimiter rules, no raw PII embedded |
| Lifecycle rules | TTL, deletion, retention, ownership, and migration policy |

Do not treat `:` as a universal standard: it is just a representation convention. A store may accept binary keys, tuple-typed keys, or separate multi-column declarations.

### 3.1. Scope of Uniqueness

Asking "is `userId` unique?" is not enough. You must specify **unique within what scope**.

- If `orderId` is globally unique across the system, `orderId` may suffice to look up an order; including `shopId` in the key can still help with data isolation and scope checks.
- If `orderId` is only unique **within a shop**, then `(shopId, orderId)` is the complete identifier.
- If `cartId` is unique, yet each user has only one active cart per shop, you may need both `cartId → cart` and `(shopId, userId) → cartId`. This mapping pair introduces additional consistency requirements.

An identifier specification table should record the issuing authority, uniqueness scope, mutability, post-deletion reusability, and conflict handling. This information remains valuable even if you later move to SQL, document, or graph models.

### 3.2. Separating Environments and Applications

In some systems you may see keys like `prod:checkout:cart:v1:...`. An environment prefix helps when reading logs, but **does not replace proper environment isolation** using separate databases, credentials, clusters, or policies. Never rely on teams avoiding typos in prefixes to protect production data.

Namespaces organize structure; they are **not an authorization mechanism**. A user in tenant A must not be allowed to read tenant B merely because UI code only constructs `shop_A` keys. Services must verify permissions based on caller identity and access scope at the API boundary, query layer, and IAM/ACL mechanisms where available.

## 4. Choosing Business Identifiers: Natural or Surrogate?

A core decision is where the `logicalId` component comes from.

| Identifier Type | Example | Benefits | Risks to Control |
| --- | --- | --- | --- |
| **Natural key** | Tax ID, per-shop internal SKU | Meaningful to the business; easy lookup by known code | Can change, be mistyped, collide, or depend on scope |
| **Surrogate key** | `user_42`, UUID | Decouples identity from mutable attributes | Requires an allocation mechanism and lookup path from business attributes |
| **Time-ordered identifier** | Time-based ID, UUIDv7, ULID | Helpful in certain sort orders, logs, and analytics | Actual ordering depends on algorithm, system clock, precision, and encoding |
| **Randomly generated identifier** | UUIDv4 | Extremely low collision probability with a proper generator; distributes well in many designs | Hard to read; if used as a sort key, does not preserve chronological order |

A design is usually more resilient when using an **immutable internal ID** for identity while keeping mutable codes as attributes or secondary lookup mappings. For example, if a user changes their email, their `userId` stays the same and their cart key does not need to change. This is a guideline, not an absolute rule: if the business guarantees SKUs are immutable within a shop, `(shopId, sku)` can still be a valid primary key.

**Do not equate "time-ordered" with "exact global creation order."** UUIDv7 and ULID embed a timestamp component and can be convenient for approximate ordering, yet strict monotonicity across multiple machines or under clock skew depends on the generator. Paginated queries and business invariants still need a tie-breaker key like `orderId` when timestamps match.

### 4.1. Do Not Use Mutable Attributes as Primary Keys Without a Key-Rename Plan

Suppose the key is:

```text
account:customer@example.com -> profile
```

When the email changes, the application must create a new key, copy data, update references, and delete the old key. If one step fails, two profiles may exist or the lookup path may break.

An alternative design:

```text
account:v1:user_42            -> profile
email-lookup:v1:<digestEmail> -> user_42
```

Here, changing an email does not change the primary key. However, the `email-lookup` key still requires **uniqueness enforcement** and controlled updates: two concurrent registration requests must not claim the same email. Use transactions/conditional writes or a data source with a unique constraint to protect it; two sequential `put` commands do not guarantee uniqueness.

## 5. Unambiguous Composite Key Encoding

A logical composite key may be a tuple `(shopId, orderId)`. If the store takes a single string, the application needs an encoding function that maps **every valid tuple to a distinct key**.

### 5.1. Direct Concatenation Bug

Suppose `:` is used as the delimiter:

```text
encode("a:b", "c") = "a:b:c"
encode("a", "b:c") = "a:b:c"
```

Two distinct tuples produce the same string. This is an **encoding collision**, not a hash collision. Concatenating without a delimiter is even worse:

```text
encode("ab", "c") = "abc"
encode("a", "bc") = "abc"
```

There are three common fixes:

1. **Restricted character set + forbid the delimiter:** For example, generated IDs only allow `[a-z0-9_-]` so `:` never appears inside a component. Only valid if enforced everywhere IDs are created.
2. **Escape or percent-encode each component:** Use a uniform character encoding and escape rule, then join the encoded components. Explicitly specify escaping for `%` itself and never decode before splitting components.
3. **Length-prefix or typed binary format:** Write the byte length before each component so decoding is unambiguous; well suited when keys do not need to be human-readable.

Example of length-prefixed encoding in an internal system:

```text
logical tuple: ("a:b", "c")
encoded:       3#a:b1#c

logical tuple: ("a", "b:c")
encoded:       1#a3#b:c
```

In the ASCII example above, the number before `#` is the **UTF-8 byte length**, not necessarily the Unicode character count. With non-ASCII characters (such as Vietnamese text), calculate in bytes as defined by the chosen protocol. Never mix a byte-length encoder with a character-length decoder.

### 5.2. Normalization Rules Must Be Consistent

Depending on the field, decide before encoding a key:

- Are leading/trailing spaces allowed? If trimming, trim at a single input boundary and avoid altering IDs where spaces are meaningful.
- Is case significant? `SKU-a` may be a different code from `sku-a`; do not blindly lowercase all IDs.
- Should Unicode strings be normalized to a canonical form, such as NFC? Two visually identical strings can have different byte sequences.
- What timezone, precision, and format do timestamps use? Never mix local time with UTC in a sortable key field.
- Are null, empty string, and missing three distinct states? Never arbitrarily encode all three as an empty string.

**Email is particularly sensitive to normalization:** domains are case-insensitive, whereas rules for the local-part depend on the system and mail provider. Do not blindly strip dots or `+` subaddressing for every address. Define normalization rules based on your actual login contract, then apply them consistently during creation, lookup, and email changes.

### 5.3. Sample Encoding Contract

You can specify a key builder with product-agnostic pseudocode:

```text
function cartKey(shopId, userId):
    validateOpaqueId(shopId)
    validateOpaqueId(userId)
    return join(":", ["cart", "v1", shopId, userId])

function validateOpaqueId(id):
    require id is not empty
    require matches(id, "[A-Za-z0-9_-]+")
    require byteLength(UTF8(id)) <= configuredLimit
```

This pseudocode is only valid because the validator **forbids `:`** inside components. If a tenant ID, URL, email, or external code can contain that character, use a different encoding scheme. Also document that keys are case-sensitive at the byte level; two distinct IDs can be treated as different even if they look similar visually.

## 6. Key–Value Composite Keys vs. Wide-Column Keys

Two data stores can share the same entities and access patterns yet organize keys very differently.

### 6.1. In a Pure Key–Value Store

Example:

```text
order:v1:shop_17:ord_908 -> { ...order... }
```

The application supplies the full key to read the value. Including `shop_17` in the key **does not automatically** allow "fetching all orders for shop_17" cheaply. If the store partitions by hashing the entire key, keys sharing a prefix may be scattered across many partitions. Prefix scans are only efficient when the DBMS, indexes, and storage layout genuinely support them.

To support a per-user order list, you may need a separate **read model** such as a sorted list of IDs, or a database offering ordered keys. Maintaining a list in a separate key means every order creation may involve at least two writes: the primary order and the list. You must handle consistency conditions and recovery when one step fails.

### 6.2. In a Wide-Column Model

In a wide-column DBMS family, a table might be structured as:

```text
partition key: (shopId, userId)
clustering:    (createdAt DESC, orderId ASC)
non-key data:  total, status, currency, ...
```

Conceptual layout:

```text
Partition (shop_17, user_42)
  ├─ (2026-11-22T10:40:00Z, ord_908) -> status, total, ...
  ├─ (2026-11-21T15:12:00Z, ord_901) -> status, total, ...
  └─ (2026-11-20T08:05:00Z, ord_880) -> status, total, ...

Partition (shop_17, user_99)
  ├─ (2026-11-22T09:00:00Z, ord_910) -> ...
  └─ ...
```

The **partition key** selects the group of data to read. The **clustering key** defines row identity and ordering within that group, if the DBMS provides such clustering semantics. A layout stored descending by `createdAt` can serve "20 most recent orders" by reading the head of the partition; however, support for descending order, pagination, and specific limits varies by product.

Not every product labeled "wide-column" has Cassandra-like primary key semantics. For example, some systems use lexicographically sorted byte row keys across tablets, while others use a partition key plus a sort key. Always **translate query requirements into the actual primitives of your chosen product** before treating this as an implementation schema.

### 6.3. When Should a Component Be in the Partition Key?

Ask simultaneously:

- Do common queries provide all of these components?
- Is the number of partitions large enough to distribute load?
- What is the maximum size each partition can reach over 1 month, 1 year, and the full retention period?
- Is any tenant or entity dramatically hotter than the rest?
- How many partitions does a single query need to read? Can it be bounded and paginated?

For example, choosing only `shopId` as the partition key for all orders of a shop allows filtering by shop, yet one large shop can concentrate millions of orders and heavy writes into a single partition. Choosing `(shopId, userId)` spreads load by customer, but shop-wide queries must aggregate across many partitions. That is a direct trade-off between **query path** and **data distribution**.

## 7. Designing Sort Keys and Time-Based Queries

For ordered data such as orders, device logs, or events, a timestamp field often becomes part of the composite key. Three distinct concerns must be addressed:

1. **Ordering:** is data within a group organized to fetch the latest items or date ranges efficiently?
2. **Uniqueness:** two events can share the same timestamp; an ID or sequence number is needed as a tie-breaker.
3. **Scale:** unbounded growth for a single customer or device will cause partitions to grow too large.

### 7.1. Use Consistently Formatted Timestamps

If the storage engine sorts string keys in byte/lexicographical order, normalized timestamps ensure string order matches chronological order:

```text
2026-11-20T08:05:00.000Z
2026-11-21T15:12:00.000Z
2026-11-22T10:40:00.000Z
```

This is only reliable when **format, timezone, precision, and zero-padding are fixed**. Strings like `2026-2-5` and `2026-11-1` do not sort lexicographically in date order. Varying timezone offsets can also break chronological ordering of string representations.

Timestamp formatting only enables range queries if **the storage engine supports ordered traversal**. On a hash-based key–value store offering only `GET(key)`, putting a timestamp in the key does not grant range-query capability.

### 7.2. Add a Tie-Breaker Component

If a customer places two orders with the exact same `createdAt` down to the millisecond, a clustering key containing only the timestamp cannot distinguish the two rows in models where the clustering key uniquely identifies a row. A more complete design is:

```text
partition = (shopId, userId, monthBucket)
sort      = (createdAt DESC, orderId ASC)
```

Here `orderId` breaks ties when timestamps collide. Total ordering still needs a clear definition, especially across multiple machines with clock skew or late-arriving events. For logs requiring strict per-device ordering, a source-generated sequence number or a scoped centralized allocator may be more suitable than a wall-clock timestamp alone.

### 7.3. Time Bucketing to Bound Partition Size

If each user has a long history, instead of a `(shopId, userId)` partition spanning all years, you can bucket by month:

```text
partition = (shopId, userId, yyyyMM)
sort      = (createdAt DESC, orderId ASC)

(shop_17, user_42, 202611) -> November 2026 orders
(shop_17, user_42, 202610) -> October 2026 orders
```

Benefits: each partition has a tighter growth bound, making older data easier to manage. Trade-offs:

- Queries spanning multiple months must read multiple partitions and **merge results in order**.
- Fetching the 20 most recent orders may require reading the current month and stepping backward through prior months until enough rows are collected.
- Buckets that are too small create too many partitions and requests; buckets that are too large produce bloated partitions.
- If a single user generates extreme traffic within one month, a monthly bucket can still run hot; daily/hourly buckets or another strategy may be needed.

**How to choose bucket granularity:** estimate record count and bytes per user per time unit, covering p95/p99 cases and extreme outlier users. Compare against the product's practical limits and guidelines; never pick "monthly buckets" just because the name is convenient.

## 8. Distribution: Balanced Keys vs. Hot Keys

Suppose there are 1 million keys, yet 70% of requests read/write a single key `counter:global`. A large key count **does not mean load is balanced**. With hash partitioning, one key typically maps to one partition at a time; adding more nodes does not automatically split concurrent requests hitting **that same key**.

Common sources of hot keys:

| Key Pattern / Workload | Problem | Mitigation to Consider |
| --- | --- | --- |
| `counter:global` under continuous writes | One key absorbs all updates | Split the counter across multiple shards if business accepts aggregation; ensure accurate summation |
| `events:<today>` holding all events | Every producer writes to one unit | Partition by entity, source, and/or time bucket |
| Partition `(shopId)` for a massive shop | One tenant overwhelms the cluster | Add a high-cardinality component matching access patterns |
| `(deviceId, day)` for a very high-rate device | Daily bucket still runs hot | Measure load and use finer buckets or sharding, accepting read fan-out |
| Monotonically increasing keys in range-partitioned stores | Writes concentrate on the newest key range | Design distributed prefixes or product-appropriate partitioning/splitting |

**Sharding/salting** must specify both the write path and the read path. For example, a counter split into 16 shards:

```text
counter:checkout:v1:00 -> 120
counter:checkout:v1:01 -> 109
...
counter:checkout:v1:15 -> 131

total = sum(GET(counter:checkout:v1:00..15))
```

Each event must map to a shard via a controlled rule; reading the total must fetch and sum all shards, incurring the corresponding cost and consistency behavior. Never add random suffixes to a cart key, because when opening a cart by `shopId` and `userId`, the application would not know which shard to read.

If a system separates partition keys and clustering keys, **adding a field to the clustering key does not reduce partition load**: the actual partition key components must change to distribute rows across different partitions. Design around the physical routing algorithm of the chosen engine rather than inferring behavior from field names.

## 9. Key Names and Sensitive Data Constraints

Keys often appear where values do not: query logs, error messages, metrics, backups, admin tools, dashboards, and request tracing. Therefore, **never embed secrets, passwords, access tokens, or raw sensitive identifiers in keys**.

Examples to avoid:

```text
session:eyJhbGciOi...     # raw access token
email:alice@example.com  # raw email address
phone:+84...             # raw phone number
```

Use internal IDs or, for certain lookup paths, a suitable derived digest from a normalized value. When hashing low-entropy data (emails, phone numbers), **a plain hash usually does not guarantee anonymity** against dictionary attacks. If guessing resistance is required, consider HMAC with a securely managed secret key, while also defining key-rotation and index-migration procedures. HMAC also does not replace authorization checks, log hygiene, or encryption at rest.

Additional rules:

- Do not let arbitrary user input generate overly long keys or unbounded numbers of keys without quota controls.
- Do not trust a `tenantId` from a request without verifying it lies within the caller's authorized scope.
- Do not rely on prefixes like `admin` or `private` as a security boundary.
- Separate **stable identifiers** from **display attributes** such as shop name or URL slug so rebranding does not force key renames.

## 10. Secondary Lookup Keys and Consistency

An entity may need to be looked up by multiple paths, such as finding a user by `userId` or by email. When creating two mappings:

```text
user:v1:user_42                  -> { ...profile... }
email-lookup:v1:<emailDigest>   -> user_42
```

The application must define consistency semantics:

1. Can two accounts claim the same email? If not, creation requires an atomic **write-only-if-key-absent** operation or a unique constraint.
2. When an email changes, when does the new index entry become authoritative? Are transitional states permitted?
3. If profile creation succeeds but writing the lookup index fails, how does the system recover? Is there idempotent retry, rollback, or reconciliation?
4. When a user is deleted, is the email index removed immediately or retained as a tombstone per reuse policy?

Having "clean keys" only solves identification, not **cross-key invariants**. If strong synchronization is required and the product lacks suitable transactions, choose a data source that enforces the constraint or adjust the business workflow.

### 10.1. One Entity, Multiple Read Models

For example, orders may be queried by:

- `(shopId, orderId)` to read order details.
- `(shopId, userId, createdAt, orderId)` to read customer order history.
- `(shopId, status, createdAt, orderId)` to inspect in-progress orders.

Wide-column modeling often tailors each table/read model to a known set of queries, leading to data duplication or secondary lookup tables. When an order's status changes, all read models must be updated through a well-defined mechanism. Duplication speeds up reads while shifting cost to **writes and synchronization**. Document explicitly where immediate consistency is required, where eventual consistency is acceptable, and how duplicate or out-of-order events are handled.

## 11. Versioning, Key Changes, and Schema Migration

Never silently change the meaning of the same key prefix while multiple application versions coexist.

Suppose version 1 uses:

```text
cart:v1:<shopId>:<userId>
```

Later, you need to support multiple carts per user, identified by `cartId`:

```text
cart:v2:<shopId>:<cartId>
active-cart-by-user:v1:<shopId>:<userId> -> <cartId>
```

This is a change in **business model and access paths**, not merely a delimiter tweak. A migration plan should define:

1. **New contract:** how `cartId` is generated, uniqueness conditions, authoritative data source, and the `userId → cartId` mapping.
2. **Compatible reads:** during transition, read the new key first and fall back to the old key under controlled rules.
3. **Migration:** migrate active data; protect concurrent and newly arriving writes during migration with transactions/versioning or a single authoritative writer.
4. **Telemetry:** track remaining v1 keys, not-found errors, write versions, and discrepancies across mappings.
5. **Cutover:** drop the old read path only after verifying all required data has migrated or expired.
6. **Cleanup:** delete old keys according to retention/TTL policy after removing dependencies, avoiding premature deletion.

Not every JSON change warrants `v2` in the key. **Key versioning** is typically justified when identity, routing, or encoding changes; **value schema versioning** can be managed independently if the key format remains unchanged.

A design should state explicitly "what happens if a key needs to be renamed": create new keys, maintain aliases, keep backward compatibility, or rewrite all references. That is a vital part of **evolvability** in data modeling.

## 12. Validating a Design with a Complete Example

### 12.1. Problem Statement

An IoT temperature ingestion service:

- Each device belongs to a tenant.
- Devices emit from a few to thousands of readings per minute and may resend the same reading on network errors.
- The API must fetch the 100 latest readings for a device, or readings for a device within `[from, to)`.
- Data is retained for up to 90 days; a few tenants generate disproportionately high traffic.
- Each record has a `measurementId` unique within the device, an event timestamp, and a temperature value.

### 12.2. Proposed Design

Start with a key layout for a store supporting partitions and sort keys:

```text
partition key = (tenantId, deviceId, dayBucketUTC)
sort key      = (eventTime DESC, measurementId ASC)
value         = {temperature, receivedAt, qualityFlags, schemaVersion}
```

Sample data rows:

| Partition | Sort | Value |
| --- | --- | --- |
| `(tenant_7, dev_12, 20261122)` | `(2026-11-22T11:01:00.000Z, m_901)` | `{temperature: 24.1}` |
| `(tenant_7, dev_12, 20261122)` | `(2026-11-22T11:00:00.000Z, m_900)` | `{temperature: 24.0}` |
| `(tenant_7, dev_12, 20261121)` | `(2026-11-21T23:59:59.000Z, m_899)` | `{temperature: 23.8}` |

This design supports a read path by device and day. To fetch the 100 latest readings, the service starts at today's bucket and steps backward day by day until enough rows are gathered; if a tenant's readings are very sparse, bound the number of buckets scanned or add a supporting index. For date-range reads, identify the buckets intersecting the range and merge in time order.

**Duplicate delivery constraint:** merely adding `measurementId` to the clustering key **does not prevent** the same `measurementId` from appearing under different timestamps. If a device can resend an ID with an altered timestamp, establish a canonical timestamp source or maintain an idempotency constraint on `(tenantId, deviceId, measurementId)`. Uniqueness must be tied to the right business components, not assumed from a timestamp + ID pair.

**Load concern:** if one device sends thousands of readings per minute, a daily bucket can grow too large or hot. Measure writes/sec and bytes/day, then evaluate hourly buckets, additional sharding, or a specialized time-series engine; any extra sharding requires fan-out during range queries.

**TTL concern:** is the 90-day retention measured from `receivedAt` or `eventTime`? If devices send delayed data, the two choices yield different deletion behavior. State the policy clearly and verify row/column/partition TTL semantics in the DBMS, including the operational impact of deletions.

### 12.3. When Only Key–Value `GET/PUT` Is Available

You cannot fetch "the 100 latest readings" merely from knowing the prefix `measure:tenant_7:dev_12:...` if the store lacks prefix/ordered queries. Options include:

- Choosing a system with partition + sort keys or an appropriate time-series database.
- Maintaining an index/list of the latest measurement IDs per device using consistent update operations.
- Batching readings into **bounded chunks** per bucket when most reads consume entire chunks, enforcing size limits and overwrite protection.

The final design must satisfy **time-ordered reads**, **duplicate writes**, **size bounds**, and **what the storage engine genuinely supports**.

## 13. Common Key Design Mistakes

| Symptom | Why It Is a Problem | How to Fix |
| --- | --- | --- |
| Using email/slug/name as primary key | Values can change, leak sensitive info, or lack uniqueness in the desired scope | Use stable IDs; add controlled secondary lookup paths |
| Concatenating composite keys without escaping | Different tuples produce the same key | Forbid the delimiter or use a uniquely decodable encoding |
| Adding `tenantId` to the string and treating it as authorization | Read/write paths can still access the wrong tenant | Verify tenant from caller identity and permissions at API and storage layers |
| Assuming keys with a shared prefix are stored together | Hash partitioning can scatter keys based on the full string | Check actual partitioning mechanics and scan/range capabilities |
| Partitioning by entire `shopId` for multi-year history | Extremely large or hot partitions | Split by customer, data type, time bucket, or another read model per workload |
| Using timestamp alone as a unique key | Two events can collide in time; ordering is not strictly guaranteed | Add an ID/sequence and define idempotency constraints |
| Making time buckets too narrow | Excessive partitions and higher read fan-out/cost | Size buckets using measurements and SLAs |
| Appending random shards to every key | Impossible to derive the key directly from business IDs | Shard only with an explicit read/write routing strategy |
| Changing key conventions in-place in a live app | Breaks read paths across versions and leaves orphaned data | Version keys and run measured migrations |
| Treating every "composite key" as equivalent | Concatenated string keys differ from partition + clustering keys | Separate logical keys from product-specific query capabilities |

## 14. Pre-Schema Sign-Off Checklist

For each key type or table, produce a concise specification covering:

- **Owner & Scope:** Entity/aggregate type, owning service, and tenant scope.
- **Access Patterns:** Known inputs, `GET`/range/scan operations, filter predicates, sorting, pagination, frequency, and SLAs.
- **Identity:** Key components, ID types, uniqueness scope, issuer, mutability, and reuse rules.
- **Encoding:** Exact format, byte encoding, length limits, delimiter/escape or tuple rules, normalization, and invalid-input handling.
- **Physical Layout:** Partition key, sort/clustering key (if any), expected size and item count per partition, load distribution, and hot-key risk.
- **Correctness:** Single-value and cross-key invariants, concurrent writes, idempotency, and consistency conditions.
- **Security & Lifecycle:** PII exposure in keys, tenant authorization, TTL, retention, deletion, backup, and recovery.
- **Evolution:** Key/value versioning, identifier changes, backward-compatible reads, migration, observability, and old-data retirement.

Include at least four verification tests:

1. No two distinct key component tuples encode to the same key, including inputs with delimiters, Unicode, whitespace, and empty values.
2. The same logical entity always produces the **exact same canonical key** across all services and programming languages.
3. The largest entities and hottest tenants remain within chosen partition/size/cost limits; evaluate at p95/p99 rather than averages alone.
4. Changing a secondary lookup ID loses no data, violates no uniqueness constraints, and never permits cross-tenant reads.

## 15. Practice Exercises

### Exercise A — Multi-Tenant Cart

Requirement: a user has at most one active cart per shop, can change their email, and the same user ID appears across multiple shops.

Choose between the two keys:

```text
A. cart:<email>
B. cart:v1:<shopId>:<userId>
```

**Suggested answer:** B clearly expresses the cart's scope and uses stable IDs. However, it is only valid if `shopId` and `userId` are allocated/validated per rules without unescaped delimiters and the system enforces shop-level authorization. If multiple carts per shop are allowed, revise the business assumption and add `cartId` or an active-cart pointer mapping.

### Exercise B — Customer Orders

API needed: `GET /shops/{shopId}/customers/{userId}/orders?from=...&to=...&limit=20`, 5-year retention, large shops with millions of customers.

**Suggested model:** partition by `(shopId, userId, monthBucket)`, cluster by `(createdAt, orderId)`, with sort direction matching the query. Then compute how many partitions must be read across the date range; evaluate oversized/undersized buckets and design a separate `(shopId, orderId)` access path if order detail lookup by ID is needed.

### Exercise C — Composite Keys with Unsanitized Strings

Two input pairs are `("north:sales", "customer3")` and `("north", "sales:customer3")`. Show why joining with `:` fails, and propose an unambiguous encoding.

**Suggested answer:** both pairs produce `north:sales:customer3`. You can escape each component or use length-prefixing; specify byte counts, character sets, and consistent decoding rules. If prefix queries or sorting are required, check whether the encoding preserves those properties in the target store.

### Exercise D — One Overheated Device

All readings for device `dev_1` go into partition `(tenant_7, dev_1)`. After launch, writes bottleneck and partition size grows rapidly.

**Suggested answer:** evaluate daily/hourly buckets and sharding if needed, but decide only after measuring p95/p99 write load, partition size, and read fan-out cost. If queries frequently read continuous ranges, also evaluate a time-series database or a better-suited storage engine.

## Summary

**Key design is access-contract design.** A clear namespace tells you which domain a key belongs to, which entity it identifies, and how it can evolve. Composite keys must have unambiguous encoding and explicit uniqueness scopes. Partition and sort keys must be chosen from real workloads, because any change to key components alters storage placement, load distribution, and query scope.

When reviewing a design, always check: **Which key components does the application know? Are ordering or range filters required? How large and hot can data in the same partition grow? Where are consistency invariants and access permissions enforced?** Answering those four questions keeps a key–value or wide-column model aligned with business needs while remaining adaptable as data grows.
