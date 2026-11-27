# Unique Identifiers When Data Is Created Across Multiple Locations

## 1. The Problem: Multiple Data Creation Sites, One Identity Space

In the **DATABASE_DATA_MODELING** module, the task goes beyond picking a data type for an ID column. When translating business requirements into relational models, keys, constraints, and physical schemas, you must define **how an object is identified when records are created concurrently in multiple places**.

Consider a company writing orders in three places:

- The Hanoi store has an independent PostgreSQL database.
- The Ho Chi Minh City (HCMC) store has an independent PostgreSQL database.
- A tablet app can sell **offline**, syncing once network connectivity returns.

Each location currently has an orders table with an auto-incrementing key. Both of the first two databases can independently generate ID 1001:

~~~text
Hanoi (HN)                         HCMC (HCM)
orders:                            orders:
  id 1001 -> An's order              id 1001 -> Binh's order
  id 1002 -> Chi's order             id 1002 -> Dung's order

                Data synchronization
                       ↓
         Which order is id = 1001?
~~~

Each database enforces **primary key uniqueness within that database alone**. That does not prevent IDs from colliding when records are ingested into a central analytics warehouse or central service.

We can issue **global UUIDs**, use **composite keys `(origin_region, local_id)`**, allocate disjoint number ranges, or generate IDs from timestamps and node IDs. Yet every choice must handle real-world conditions: devices lose connectivity, clocks drift, regions get cloned, commands get retried, and systems get sharded.

This lesson, **"Unique Identifiers When Data Is Created Across Multiple Locations,"** belongs to the **Distribution and Partitioning** chapter. It explains how to design identity, compare generation algorithms, build PostgreSQL constraints, and verify multi-source synchronization. The concepts also apply when choosing relational, document, graph, or analytical storage models.

### Learning Outcomes

After this lesson, you will be able to:

1. Define uniqueness scope: **a single table, a tenant, a source system, a shard, or the entire system**.
2. Distinguish **business keys, surrogate/global IDs, event IDs, idempotency keys**, and display codes.
3. Compare sequences, range allocation, namespaced composite keys, UUIDv4, UUIDv7, ULID, Snowflake, and ID services.
4. Clearly separate guarantees enforced by **coordination** from guarantees backed only by **negligible collision probability**.
5. Design PostgreSQL schemas with `PRIMARY KEY`, `UNIQUE`, source mapping tables, registries, and retry detection.
6. Explain uniqueness boundaries on partitioned tables and independent databases.
7. Design offline synchronization, migrations, foreign-key management, and distributed failure tests.

## 2. "Unique" Must Always Carry a Scope

There is no single definition of uniqueness that fits every business rule.

| Scope | Example Key | Meaning |
|---|---|---|
| Single table | `PRIMARY KEY(id)` | No two rows in this table share `id` |
| Single tenant | `(tenant_id, order_code)` | Within one tenant, no two orders share the same code |
| Single source | `(source_system, source_order_key)` | Source codes are scoped by issuing system |
| Single region | `(origin_region, local_id)` | Two regions may issue the same `local_id` |
| System-wide | `global_order_id` | One ID identifies one object across all regions |
| Single request | `(tenant_id, client_id, request_id)` | Retries do not trigger duplicate business effects |
| Single event stream | `(aggregate_id, version)` | No two events share the same aggregate version |

A `UNIQUE` constraint in PostgreSQL protects **the database enforcing that constraint**. When two regions write to two independent databases, no magic turns two local constraints into one global constraint.

### 2.1. Same Number Does Not Mean Same Object

~~~text
(origin_region = HN, local_id = 1001)
(origin_region = HCM, local_id = 1001)
~~~

These could be two completely distinct orders. Alternatively, HCMC might hold a **replica** of an order created in Hanoi. You must know **where the record originated** and the business rules—not merely compare the number 1001.

### 2.2. Different IDs Do Not Guarantee Different Objects

Two CRM systems might generate two different UUIDs for the exact same customer. There is no ID collision, yet there is a **duplicate business entity**. Merging two profiles is an **identity resolution** problem requiring matching evidence, not a UUID generator problem.

### 2.3. Unique Does Not Mean Contiguous or Ordered by Commit

A sequence like 1, 2, 5, 9 is still completely unique. Sequences leave gaps when transactions roll back, caches are discarded, or allocated ranges go unused.

The order of **ID issuance** also does not match **COMMIT order**. A transaction receiving ID 1002 can commit before a transaction receiving ID 1001. If the business needs gapless voucher numbers or ledger posting order, model a **separate business document number/sequence** with its own closing workflow and regulations. Never force a distributed primary key to serve every role.

## 3. One Object May Need Multiple Types of Keys

An order created on a tablet may have:

| Field | Purpose | Can It Change? |
|---|---|---|
| **`global_order_id`** | Identifies the order everywhere | Should stay immutable once issued |
| **`source_order_key`** | Order code used by POS/ERP | May change during source migrations; keep audit trail |
| **`client_request_id`** | Identifies the `CreateOrder` command to prevent retries | Must stay identical across retries of the same command |
| **`order_number`** | Customer-facing code printed on receipts | Governed by separate legal/business rules |
| **`event_id`** | Identifies an event like `OrderCreated` | Preserved across event replays |
| **`aggregate_version`** | Sequential change number of an order | Increments per order stream rules |

**Global ID** identifies the record, **business key** identifies the object in its source, **idempotency key** identifies the request, and **event ID** identifies the event. One order can emit many distinct events; one request can trigger multiple events.

Never use `order_id` as the deduplication key for every operation: the same order can legitimately have two payments or two shipping events. Likewise, never generate a fresh `order_id` on every retry of the same request and assume UUID uniqueness keeps the system safe.

### 3.1. Namespace Is Part of Source Identity

If both `ERP-VN` and `ERP-TH` have product code `P01`, they may not be the same product. The full key may be:

~~~text
(tenant_id, source_system, business_key)

(1, ERP-VN, P01) != (1, ERP-TH, P01)
(1, ERP-VN, P01) != (2, ERP-VN, P01)
~~~

If local order numbers reset daily at each counter, the namespace might also include **`store_id`, `register_id`, `business_date`**. Always match the source system's exact rules; never arbitrarily add or drop key parts just to make a `UNIQUE` constraint pass.

For string codes, never strip leading zeros or normalize casing if the source distinguishes them.

## 4. Types of Collisions and Duplicates to Handle

| Problem | Symptom | Primary Mitigation |
|---|---|---|
| **ID collision** | Two distinct objects share the same global ID | Sound algorithm/namespace, `UNIQUE`, and error handling |
| **Local ID collision** | Two shards both have `id=1001` | Preserve origin namespace or issue global IDs |
| **Retry duplicate** | One request creates two orders with different IDs | Idempotency key and durable result storage |
| **Duplicate entity** | Two distinct IDs describe the same customer | Identity resolution / canonical mapping |
| **Duplicate event delivery** | Broker delivers one event twice | Stable `event_id` and idempotent consumers |
| **Concurrent conflict** | Two writers claim the same business key | Write authority coordination, `UNIQUE`/transactions, reconciliation |
| **Identity reuse** | An old code is reissued to a new object | Code lifecycle control and namespace locking |
| **Cross-tenant mismatch** | Child row of tenant A points to tenant B's order | Proper FK or tenant/authorization validation |

ID generators solve only **part** of this table. A virtually collision-free random ID still will not stop a user from tapping "Place Order" twice or a network from replaying the same request.

## 5. Database Sequences: Simple, But Local in Scope

Inside a single PostgreSQL database, an identity column is often a clean choice:

~~~sql
CREATE TABLE local_order (
    local_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL
);
~~~

When all writers use **the same database/sequence**, the DBMS hands out distinct sequence values. Yet two databases with independent sequences can both hand out `local_id = 1`.

### 5.1. What Sequences Do NOT Guarantee

- No guarantee of gapless numbering.
- No guarantee that ID order matches `COMMIT` order.
- No automatic synchronization across independent databases or regions.
- If a database is cloned/restored and both copies accept writes, both can reissue IDs already present in the other.
- Does not provide business-request idempotency.

### 5.2. Exclusive Range Allocation

You can allocate disjoint ranges:

~~~text
HN:  [1,         1,000,000)
HCM: [1,000,000, 2,000,000)
DN:  [2,000,000, 3,000,000)
~~~

Each site generates IDs within its owned range. Correctness requires that **no two sites own the same range at any writable moment**.

You need a **range allocator** and durable metadata: allocated ranges, owner, allocation status, expiration/revocation timestamps if any, and recovery history. When a node is cloned or partitioned off the network, never reassign its range to a new node while the old node can still mint IDs.

Pros: IDs stay numeric and require no central call per record. Cons: complex range management, exhaustion, region transfers, and recovery.

### 5.3. Odd/Even or Stride Offsets

Two regions might use odd and even numbers. This is only safe if region count, offsets, and strides are assigned **exclusively and never altered casually**. Adding a third region, rebuilding a node, or restoring a backup can break the invariant.

Avoid stride-based numbering unless you have a strict registry, configuration change process, and verified region-count bounds.

## 6. Namespaced Composite Keys: Keep Local IDs Without Collisions

When data already has `local_id` and sources have stable namespaces, you can use:

~~~text
PRIMARY KEY(origin_region, local_id)
~~~

For example:

~~~sql
CREATE TABLE regional_order (
    origin_region text NOT NULL,
    local_order_id bigint NOT NULL,
    tenant_id bigint NOT NULL,
    created_at timestamptz NOT NULL,

    PRIMARY KEY (origin_region, local_order_id)
);
~~~

**`origin_region`** should be an **immutable** creation-site code, not the name of the region currently storing the record. If data moves from the HN shard to the HCM shard, its identity remains `(HN, 1001)`.

### 6.1. When Is This Appropriate?

- Integrating legacy databases with local auto-increment keys.
- You can guarantee each source's namespace never overlaps or gets improperly reused.
- APIs, queries, and FKs can handle composite keys.
- External systems do not strictly require a single scalar ID.

### 6.2. Trade-Offs

- Every child table must store **both components**; storing only `local_id` still risks mis-referencing.
- Indexes and JOINs can be larger than a single `bigint` key.
- Never change `origin_region` when display names or physical hosting locations change.
- Cloning a region so both instances write under the same namespace still causes collisions despite the composite key structure.
- If a record is replicated to a second region, you must distinguish whether it is a copy of the same object or a new record.

You can keep the source composite key as **`UNIQUE`** and add a global UUID as the **`PRIMARY KEY`** centrally to simplify foreign keys.

## 7. UUIDv4: Distributed ID Generation via Randomness

UUID version 4 carries roughly **122 random bits**, with remaining bits reserved for version and variant. Each node can mint IDs independently when backed by a **trusted cryptographic random number generator**.

### 7.1. Why Is It Useful?

- Mobile devices can generate IDs completely offline.
- Multiple regions do not need to request worker IDs or number ranges before creating records.
- Does not depend on clocks for the random portion of the ID.
- The 128-bit UUID format is natively supported by most languages, APIs, and databases.
- Data can sync later without remapping parent–child keys if the client preserves its UUID.

### 7.2. Collision Probability

Given $N$ possible random values and $n$ independent generations, when $n \ll \sqrt{N}$, the collision probability is approximately:

~~~text
P(collision) ≈ n(n - 1) / (2N)

UUIDv4:
N ≈ 2^122
n = 1,000,000,000
P ≈ 9.4 × 10^-20
~~~

This is an **extremely small probability** assuming a proper randomness source—not a mathematical proof of impossibility. Fixed seeds, weak RNGs, cloned generator states, or truncated UUIDs invalidate this estimate.

Therefore:

1. Use reputable UUID libraries backed by proper entropy sources.
2. Never truncate bits just for shorter codes without re-evaluating collision risk.
3. Persist the ID once upon creation and reuse it on retries.
4. Still enforce `PRIMARY KEY`/`UNIQUE` at the database level.
5. Define how rare conflicts are handled: never overwrite an existing different record.

### 7.3. UUIDv4 Encodes No Ordering

UUIDv4 cannot be used to infer creation date, `COMMIT` order, or event order. If APIs need the newest orders, store **`created_at`** and explicit ordering fields—never use `MAX(order_id)`.

## 8. UUIDv7 and ULID: Time-Ordered Prefix, Not a Global Clock

UUIDv7 places a **Unix millisecond timestamp** in the leading bits followed by random/counter bits. ULID uses a layout of **48 timestamp millisecond bits** and **80 random bits**, commonly encoded as **26 base32 characters**.

Both can be generated across distributed sites, generally yield **roughly time-sorted** IDs, and provide better B-tree index locality than UUIDv4.

| Property | UUIDv4 | UUIDv7 | ULID |
|---|---|---|---|
| Logical size | 128 bits | 128 bits | 128 bits |
| Contains timestamp bits | No | Yes | Yes |
| Offline generation | Yes | Yes, with proper generator | Yes, with proper generator |
| Approximate time ordering | No | Yes, subject to clock/counter | Yes, subject to clock/counter |
| Clock-dependent layout | No | Yes | Yes |
| Guarantees global COMMIT order | No | No | No |

### 8.1. What the Timestamp Inside an ID Does NOT Prove

- Two servers can have skewed clocks.
- A server's clock can step backward.
- Many IDs can be minted within the exact same millisecond.
- A transaction can mint an ID first yet `COMMIT` after another transaction.
- A backdated event does not carry its business effective time inside the ID's timestamp bits.
- An offline device can have a wildly wrong clock even though its IDs remain unique.

Some generators guarantee **monotonicity** within a process or millisecond. Read your library's exact contract; **local monotonicity does not mean cross-region monotonicity**.

### 8.2. Selection Criteria

If your API/database supports native UUIDs and you want rough chronological ordering, UUIDv7 is a strong candidate. If using string-encoded ULIDs, standardize casing, encoding, and collation/comparison rules.

Do not assume every PostgreSQL version ships with a built-in UUIDv7 function. In examples below, **IDs are generated by the application or a verified ID component** and bound as SQL parameters.

**Business timestamps and commit times** must be stored and defined explicitly—never parse them out of an ID and treat them as authoritative truth.

## 9. Snowflake ID: Integer from Timestamp, Worker, and Sequence

One common 64-bit Snowflake layout allocates bits as:

~~~text
| 1 sign bit | 41 elapsed milliseconds | 10 worker bits | 12 sequence bits |
~~~

This layout provides representational bounds of:

- Roughly **69.7 years** from a custom epoch with 41 bits.
- Up to **1,024 worker IDs** with 10 bits.
- Up to **4,096 sequence values** per millisecond per worker with 12 bits.

Bit-packing formula:

~~~text
id = (elapsed_ms << 22)
   | (worker_id << 12)
   | sequence
~~~

These numbers are **logical bit-layout limits**, not guaranteed database or infrastructure throughput.

### 9.1. Worker IDs Must Be Exclusive

If Hanoi and HCMC both mint IDs using **`worker_id = 17`** at the same millisecond and sequence value, two identical IDs will collide.

A hostname, PID, or IP address is not automatically an exclusive worker ID. Containers get cloned, VMs get restored, IPs get recycled, and multiple datacenters can share identical configs.

You need a registry/allocator with:

- Disjoint worker ID assignment.
- Leases, renewals, and owner state where appropriate.
- **Fencing** so a node losing its lease cannot keep writing under stale authority.
- Handling when a lease expires while the old node is still running.
- Restart recovery that never reuses an already-issued `(timestamp, worker, sequence)` tuple.

### 9.2. Clock Rollback and Sequence Overflow

**Clock rollback:** a worker mints IDs at millisecond $T$, then the system clock jumps back to $T - 10$. If the generator resets the sequence and reuses the older timestamp, `(time, worker, sequence)` tuples can repeat.

Options: pause until the clock catches up, use a bounded logical monotonic clock within verified limits, or refuse ID issuance and alert. Never silently reissue older IDs.

**Sequence overflow:** exhausting all 4,096 values within one millisecond on one worker must wait for the next millisecond or trigger a safe fallback; **never wrap back to 0** within the same millisecond.

### 9.3. Snowflake IDs Roughly Increase with Time, Not COMMIT Order

An earlier-minted transaction can commit later, and node clocks can drift. Never use **`MAX(snowflake_id)`** as proof of the last committed update or latest business event.

Snowflake fits high-throughput workloads needing a **compact `bigint`** and willing to operate worker/clock coordination. For offline mobile clients without safe worker-ID allocation, UUIDs are usually far more practical.

## 10. Central ID Service and Availability

An ID service can issue one ID per request or allocate number blocks to workers.

~~~mermaid
flowchart TD
    HN["HN Writer"] --> G["ID service / range allocator"]
    HCM["HCM Writer"] --> G
    ETL["ETL importer"] --> G
    G --> R["Durable allocation registry"]
    HN --> D1["Save order at HN"]
    HCM --> D2["Save order at HCM"]
~~~

Pros: coordinates keyspace cleanly and issues numeric IDs. Trade-offs to weigh:

- Network latency on the record-creation path.
- If the service goes down, workers without a cached block may stall on ID creation.
- Allocation state, failover, and restores can reissue ranges if designed poorly.
- Leases must prevent old and new owners from issuing overlapping ranges simultaneously.
- IDs allocated for rolled-back transactions leave numeric gaps.
- An ID service **does not guarantee** that the business command succeeded or the transaction committed.

For extended offline operation, you can pre-allocate ranges, but you must manage lost devices, backup restores, range exhaustion, and reclamation rules.

## 11. Decision Table for Choosing an ID Strategy

| Requirement | Typical Best Fit | Verification Notes |
|---|---|---|
| Single centralized write database | Identity / sequence | Never assume gapless or exact commit order |
| Multiple legacy systems with local sequences | `(origin_id, local_id)` or crosswalk | Stable namespace, no improper reuse |
| Offline clients creating orders independently | UUIDv4 / UUIDv7 / ULID | RNG quality, clocks, persist ID across retries |
| Must use 64-bit integers | Snowflake or range allocator | Worker/range allocation, clock rollback |
| Centrally governed numbering | ID service | HA, latency, fencing, and recovery |
| Request deduplication | Idempotency key | Payload match, scope, and response replay |
| Event sequence within one order | `(aggregate_id, version)` | Expected-version check and transactions |
| Canonical ID across multiple CRMs | Identity mapping | Never merge entities solely by matching names |
| Date-partitioned table | PK includes partition key; registry if needed | Check global uniqueness limits |

Never choose a technology before agreeing on **uniqueness scope, offline capability, write rate, query patterns, key length, and migration process**.

## 12. PostgreSQL Model: Global Order ID and Source Keys

Suppose a system ingests orders from multiple POS/ERP/mobile clients, each generating a verified global UUID.

~~~sql
CREATE TABLE customer_order (
    order_id uuid PRIMARY KEY,
    tenant_id bigint NOT NULL,
    source_system text NOT NULL,
    source_order_key text NOT NULL,
    status_code text NOT NULL
        CHECK (status_code IN (
            'CREATED', 'CONFIRMED', 'CANCELLED', 'COMPLETED'
        )),
    created_at timestamptz NOT NULL DEFAULT statement_timestamp(),

    CONSTRAINT uq_order_source_key
        UNIQUE (tenant_id, source_system, source_order_key),

    CONSTRAINT ck_source_not_blank
        CHECK (length(btrim(source_system)) > 0),

    CONSTRAINT ck_order_key_not_blank
        CHECK (length(btrim(source_order_key)) > 0)
);

CREATE INDEX idx_order_tenant_created
    ON customer_order (tenant_id, created_at DESC);
~~~

| Component | What It Protects |
|---|---|
| **`PRIMARY KEY(order_id)`** | No two rows share the same UUID in this database |
| **`UNIQUE(tenant_id, source_system, source_order_key)`** | One source order code maps to at most one row per tenant/source |
| **`NOT NULL`** | Source keys cannot bypass uniqueness via `NULL` |
| **`CHECK`** | Blocks whitespace-only strings and out-of-domain statuses |
| **`INDEX(tenant_id, created_at)`** | Queries orders by tenant and time range |

Both PK and `UNIQUE` are scoped to **the database holding the table**. If two regions write to separate databases before syncing, both databases can accept the same source key independently. Independent UUIDs make ID collisions negligible, **but do not prevent duplicate business requests across regions**.

### 12.1. Is a Tenant-Scoped Composite Key Enough?

~~~sql
CREATE TABLE tenant_local_order (
    tenant_id bigint NOT NULL,
    local_id bigint NOT NULL,
    created_at timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, local_id)
);
~~~

This key is only safe if all writers for the same tenant **coordinate `local_id` allocation**. If HN and HCM both write for tenant 1 with separate sequences starting at 1, `(tenant_id=1, local_id=1)` still collides when merged.

### 12.2. IDs Do Not Replace Authorization

APIs must validate tenant scope and object permissions:

~~~sql
SELECT order_id, status_code
FROM customer_order
WHERE tenant_id = :tenant_id
  AND order_id = :order_id;
~~~

Colons denote application-bound parameters. Hard-to-guess UUIDs are not access tokens and never substitute for authorization checks.

## 13. Idempotency: UUIDs Do Not Prevent Retry Duplicates

Suppose mobile sends `CreateOrder`, the database commits, and the response drops. Mobile retries. If the server mints a second UUID and saves a second order, neither UUID collides—yet **one request created two orders**.

You need a **`request_id`** minted once per operation by the client and preserved across retries.

~~~sql
CREATE TABLE order_create_request (
    tenant_id bigint NOT NULL,
    client_id text NOT NULL,
    request_id uuid NOT NULL,
    payload_fingerprint text NOT NULL,
    order_id uuid NOT NULL UNIQUE
        REFERENCES customer_order(order_id),
    created_at timestamptz NOT NULL DEFAULT statement_timestamp(),

    PRIMARY KEY (tenant_id, client_id, request_id)
);
~~~

A request ID must have an explicit **scope and retention window**. The same `request_id` with a different payload must return a **conflict**, never silently treat it as the same command; compute the fingerprint from normalized business fields.

### 13.1. Atomic Write Protocol

1. Validate tenant, actor, source, and `request_id`.
2. Inside a transaction, claim the idempotency key or business key lock under concurrency rules.
3. Create one order with a new `global_order_id` only if the request has not been processed yet.
4. Store the idempotency outcome linked to `order_id`.
5. Commit atomically when both tables live in the same database.
6. If the key already exists, verify payload equivalence and return the **existing `order_id`/result** without inserting another order.
7. For multi-stage workflows, persist processing state and appropriate retry rules.

For sources with a trustworthy **`source_order_key`**, you can use:

~~~sql
INSERT INTO customer_order (
    order_id, tenant_id, source_system, source_order_key, status_code
)
VALUES (
    :generated_order_id, :tenant_id, :source_system,
    :source_order_key, 'CREATED'
)
ON CONFLICT (tenant_id, source_system, source_order_key)
DO NOTHING
RETURNING order_id;
~~~

When zero rows are returned, run a **follow-up `SELECT`** to fetch the existing record and verify business equivalence. Never assume every unique conflict is a harmless retry; it could be a mapping bug or a client reusing a code for a different order.

### 13.2. Multi-Region Sync Needs Same-Scope Enforcement

If the exact same `request_id` reaches HN and HCM during a network partition, each site may **accept it independently** because its local `UNIQUE` cannot see the other site. Guaranteeing a single authoritative order requires:

- Routing requests to a **single writer** for that key scope.
- Coordinating via a global registry/consensus when connected.
- Or allowing **provisional** writes and reconciling later—without advertising strong uniqueness at all times.

Picking UUIDv7 instead of UUIDv4 does not solve that business race condition.

## 14. Event ID, Aggregate Version, and Message Replay

One order can emit events:

~~~text
order_id = UUID-ORDER

event_id=UUID-E1, aggregate_version=1: OrderCreated
event_id=UUID-E2, aggregate_version=2: PaymentConfirmed
event_id=UUID-E3, aggregate_version=3: OrderShipped
~~~

When a broker redelivers the same event, it must **keep the same `event_id`**, unlike creating a new event for a new business state change.

~~~sql
CREATE TABLE order_domain_event (
    event_id uuid PRIMARY KEY,
    order_id uuid NOT NULL REFERENCES customer_order(order_id),
    aggregate_version bigint NOT NULL
        CHECK (aggregate_version >= 1),
    event_type text NOT NULL,
    event_payload jsonb NOT NULL,
    accepted_at timestamptz NOT NULL DEFAULT statement_timestamp(),

    UNIQUE (order_id, aggregate_version)
);
~~~

**`UNIQUE(order_id, aggregate_version)`** prevents two mutations from claiming the same version in this database. It does not guarantee sequential versions 1, 2, 3 have no gaps; you still need an `expected_version` append protocol and replay checks.

### 14.1. Outbox and Idempotent Consumers

If a business transaction commits and publishing to a broker fails afterward, firing-and-forgetting after commit can lose events.

A **transactional outbox** persists business state and outbound messages inside the same transaction on the authoritative database. A publisher retries on failure. Because messages can be delivered more than once, consumers deduplicate using `event_id` or an appropriate business key.

Never mint a fresh `event_id` on every publisher retry; doing so turns one event into multiple identities and breaks deduplication.

## 15. Partitioning: Per-Partition `UNIQUE` Is Not Global

An events table can be **`PARTITION BY RANGE(event_ts)`** for retention. PostgreSQL requires `UNIQUE`/`PRIMARY KEY` constraints on partitioned tables to include the partition key under supported configurations.

~~~sql
CREATE TABLE partitioned_order_event (
    event_id uuid NOT NULL,
    order_id uuid NOT NULL,
    event_ts timestamptz NOT NULL,
    event_type text NOT NULL,

    PRIMARY KEY (event_ts, event_id)
)
PARTITION BY RANGE (event_ts);

CREATE TABLE order_event_2026_07
PARTITION OF partitioned_order_event
FOR VALUES FROM (
    TIMESTAMPTZ '2026-07-01 00:00:00+00'
) TO (
    TIMESTAMPTZ '2026-08-01 00:00:00+00'
);

CREATE TABLE order_event_2026_08
PARTITION OF partitioned_order_event
FOR VALUES FROM (
    TIMESTAMPTZ '2026-08-01 00:00:00+00'
) TO (
    TIMESTAMPTZ '2026-09-01 00:00:00+00'
);
~~~

`(event_ts, event_id)` is unique across the partitioned logical table. However, the exact same `event_id` can reappear with a different `event_ts` in another month.

Creating `UNIQUE(event_id)` **individually on each child partition** only protects uniqueness **within each partition**. It cannot substitute for a global unique constraint across partitions when rows may carry different periods.

### 15.1. Out-of-Partition ID Registry

~~~sql
CREATE TABLE event_identity_registry (
    event_id uuid PRIMARY KEY,
    first_event_ts timestamptz NOT NULL,
    first_order_id uuid NOT NULL,
    payload_fingerprint text NOT NULL
);
~~~

If **`event_id` must be unique across the entire database**, run a transaction:

1. Attempt to `INSERT` `event_id` into the registry.
2. On conflict, verify metadata/payload and return retry or conflict status.
3. If new, `INSERT` the event into `partitioned_order_event`.
4. `COMMIT` both or `ROLLBACK` both.

An unpartitioned registry enforces `event_id` uniqueness **within that database**, even when raw events span monthly partitions. Note that the registry carries its own write/storage cost and retention policy.

### 15.2. Retention Changes the Deduplication Window

If raw events are retained for 90 days, purging the registry on the same schedule allows an event replayed after 90 days to look brand new. Set an explicit **idempotency window**, account for source replay capabilities, and retain the registry longer than raw events if needed.

A local registry also does not protect disconnected regional databases. Strong global constraints require coordination or matching routing policies.

## 16. Sharding and Consistency with Multi-Site Writes

If all data for a tenant routes to **one authoritative writer**, that database can enforce `UNIQUE` on tenant + business key. Yet if two regions write to **the same key scope**, no local `UNIQUE` prevents both from accepting the same code during a partition.

| Model | Protection Mechanism | Trade-Off |
|---|---|---|
| **Single writer / owner** | One authority responsible for the key | Routing, failover, cross-region latency |
| **Disjoint namespaces** | Each site only mints IDs in its assigned domain | Namespace/range registry and recovery |
| **Distributed UUIDs** | Negligible collision probability | Does not prove zero business duplicates |
| **Global registry/coordination** | Check-and-reserve keys at a shared authority | Availability and latency under network partitions |
| **Local provisional + reconciliation** | Accept locally, resolve conflicts upon reconnect | Provisional state, compensations/business conflicts |

You cannot simultaneously guarantee **every isolated region always succeeds on writes** and **every duplicate business key is immediately rejected everywhere** without pre-partitioning key ownership.

### 16.1. Shard Location Should Never Be Immutable Identity

An order may migrate from shard A to shard B during rebalancing. **`global_order_id` must stay unchanged**, while routing/placement tables update. If an ID encodes `"current_shard_id"` and mutates on moves, child FKs, logs, and APIs break references.

You may embed an immutable **origin namespace** for traceability, but never use current physical placement as immutable identity.

## 17. Offline Devices: Create Once, Sync Many Times

An offline app must create orders and order lines before any server assigns keys. Two common patterns:

### 17.1. Client Mints Global UUIDs

~~~text
Mobile:
  order_id = UUID-A
  line_id  = UUID-L1, order_id = UUID-A
  line_id  = UUID-L2, order_id = UUID-A

Server:
  Stores order_id = UUID-A unchanged
  Stores child references to UUID-A
~~~

Benefit: zero FK remapping. Requirements:

- Generate IDs with a trusted library.
- **Persist IDs durably to local storage before sending.**
- On retries, send the exact same IDs and `request_id`.
- Server still validates tenant, permissions, payload, and unique constraints.
- Client-supplied IDs never imply the client is authorized to access that record.

### 17.2. Client Uses Temporary Keys, Server Mints Global IDs

~~~text
(local_installation_id, local_counter=42) -> global_order_id UUID-B
~~~

The server must store a durable mapping table. Retries with the same local key return the same global ID; all lines, payments, attachments, and events must remap consistently.

If an app is cloned or restored so two devices share the same `installation_id` and counter, local keys collide. Enforce independent installation namespace assignment or switch to per-object UUIDs.

### 17.3. Never Treat Client Clocks as Authoritative Truth

UUIDv7/ULID minted offline can contain wrong client dates. **`event_occurred_at`**, **`server_received_at`**, and **`business_effective_at`** should be modeled separately when needed. Never alter a global ID after sync just because its embedded timestamp looks off.

## 18. ID Uniqueness and Canonical Identity Are Two Separate Layers

Suppose:

~~~text
CRM-A: customer_id = UUID-1, source_key = C-501
CRM-B: customer_id = UUID-2, source_key = X-118
~~~

If two sources describe the same customer, having two distinct UUIDs **is not an ID collision**—it is two representations of one business entity.

A mapping schema:

~~~sql
CREATE TABLE canonical_customer (
    customer_id uuid PRIMARY KEY,
    display_name text
);

CREATE TABLE customer_source_map (
    tenant_id bigint NOT NULL,
    source_system text NOT NULL,
    source_customer_key text NOT NULL,
    customer_id uuid NOT NULL REFERENCES canonical_customer(customer_id),

    PRIMARY KEY (
        tenant_id, source_system, source_customer_key
    )
);
~~~

Multiple source keys can point to one `canonical_customer` once **verified**. Never auto-merge two profiles solely by matching name or email; they could be different people or shared accounts.

When merging or splitting identities, preserve decision rationale, source evidence, mapping history, and impact on facts/relationships. A unique technical key only states "these two rows are distinct"; it does not decide whether they belong to the same real-world entity.

## 19. Parent–Child References and Cross-Shard Constraints

In a single PostgreSQL database:

~~~sql
CREATE TABLE order_line (
    line_id uuid PRIMARY KEY,
    order_id uuid NOT NULL REFERENCES customer_order(order_id),
    line_no integer NOT NULL CHECK (line_no >= 1),
    quantity integer NOT NULL CHECK (quantity > 0),

    UNIQUE (order_id, line_no)
);
~~~

The FK ensures `order_id` references an existing order **within the database hosting the constraint**. It does not verify the line's tenant matches the order's tenant unless explicitly checked, nor can it check an order sitting in a **different database**.

When data is sharded:

- **Co-locate** `customer_order` and `order_line` on the same shard by `order_id`/tenant to keep local FKs.
- Validate via the authoritative service if child rows live on another shard.
- Allow pending states with reconciliation if eventual consistency is accepted.
- Maintain durable mapping/routing tables so references survive shard moves.

A unique UUID does not automatically solve **referential integrity** or multi-tenant isolation. Validate relationships at the right scope.

## 20. Performance, Security, and Ordering Rules

| Property | Bigint Sequence | UUIDv4 | UUIDv7 / ULID | Snowflake Bigint |
|---|---|---|---|---|
| Logical size | 64 bits | 128 bits | 128 bits | 64 bits |
| Independent generation without allocator | No, if shared sequence | Yes | Yes | Conditional on worker ID |
| Roughly time-ordered | Local issuance order | No | Usually | Usually |
| Clock dependency | None in generator | None | Yes | Yes |
| Main trade-off | Coordination and cross-region | Random B-tree inserts | Clock/RNG/counter | Node lease, clock, sequence |
| Proves commit order | No | No | No | No |

### 20.1. Size and Indexes

In PostgreSQL, the **`uuid`** type stores 16 bytes; 36-character `text` differs from native `uuid` storage. **`bigint`** is generally more compact, though total index entry size also includes tuple headers and extra columns.

Random UUIDv4 scatters B-tree inserts, potentially causing page splits and cache misses. UUIDv7 generally improves locality, yet an ascending key can also concentrate writes onto the right edge of an index or the newest shard. Benchmark on your real workload—never assume "ordered IDs" are universally faster in every setup.

### 20.2. IDs Are Not Security

Sequential IDs make record volumes easy to enumerate. UUIDv7 and Snowflake leak approximate **creation time**, and Snowflake can expose worker IDs. Hard-to-guess UUIDs **are not access tokens**; APIs must always verify authorization and tenant ownership.

Never embed sensitive data (emails, phone numbers, device identities) directly in keys without necessity and protection policies. Source codes can change, get reused, or contain personal data.

## 21. Migrating from Local Sequences to Global IDs

Suppose a legacy system has two `orders` tables in HN and HCM, both having issued `local_id = 1001`. Never arbitrarily "add one billion to HCM IDs": ranges can overflow, a third system can appear, backups get re-imported, or child FKs miss remapping.

Use a crosswalk table:

~~~sql
CREATE TABLE legacy_order_id_map (
    origin_region text NOT NULL,
    legacy_order_id bigint NOT NULL,
    global_order_id uuid NOT NULL UNIQUE,

    PRIMARY KEY (origin_region, legacy_order_id)
);
~~~

Process:

1. **Lock source namespaces:** `origin_region` must be the original creation site, unaffected by current hosting location.
2. **Audit local keys** and flag any codes that were reused.
3. **Mint a global ID for each source identity** using the chosen generator.
4. **Write the crosswalk** with `UNIQUE` so retries never create duplicate mappings.
5. **Backfill `orders`** and all child tables using the mapping.
6. **Reconcile FKs** across order lines, payments, shipments, audits, and events.
7. **Check for business-duplicate orders** across sources: this is identity resolution, never auto-merged by `local_id`.
8. **Switch new writes** to global IDs; retain legacy IDs for audit trails and legacy APIs.
9. **Gradually shift read paths**; monitor unmatched IDs, duplicates, and late-arriving data.
10. **Retain the mapping table durably** for the full lifetime of legacy references.

If migration requires dual-writing to another database, handle single-sided failures via outbox/CDC/retries and reconciliation—never assume two databases share an atomic transaction.

### 21.1. Verifying Mapping Completeness

Beyond row counts, reconcile:

- Every `(origin, legacy_id)` pair maps to exactly one `global_id`.
- No two distinct source objects share the same `global_id` outside approved merge policies.
- All child rows point to the right `global_id`.
- Monetary amounts, line counts, and finalized documents remain unaltered.
- Repeated backfill/retries create zero duplicate mappings.
- Late-arriving source records still receive proper mappings.

## 22. Testing Concurrency, Network Partitions, and Clock Failures

| Scenario | Expected Outcome |
|---|---|
| HN/HCM both create `local_id=1001` | Two distinct global IDs or two distinct `(origin, local)` pairs |
| Same `(tenant, source, key)` retried | Only one `CreateOrder` outcome is accepted |
| Same `request_id` with different payload | Returns conflict without mutating the existing order |
| Two tenants use the same source code | Allowed if uniqueness is scoped per tenant |
| UUID collides with existing PK | `INSERT` rejected; never overwrites existing row |
| Cloned device and counter | Duplicate namespace detected or per-object UUIDs used |
| Two Snowflake workers claim same node ID | Fencing/lease prevents concurrent issuance |
| Snowflake clock steps backward | Safely waits/fails; never reissues used ID tuple |
| 12-bit sequence overflows in 1 ms | Does not wrap; waits for next ms or rejects |
| Same `event_id` with different `event_ts` across monthly partitions | Registry/dedup protocol blocks if global event ID required |
| Consumer receives the same event twice | Does not trigger two payments or duplicate side effects |
| Order moves to another shard | Global ID stays unchanged; routing/FKs stay valid |
| Database restored from backup | Does not reuse ranges/worker state causing collisions |
| Same customer entered in two CRMs | Identity resolution kept separate from ID uniqueness |

### 22.1. Testing Generators

Test suites must verify format/version/bit layout, concurrent multi-process generation, worker restarts, clock drift, rollbacks, sequence overflow, worker-ID reassignment, and API/DB serialization round-trips.

**Observing zero duplicates across one million generated IDs does not mathematically prove UUIDv4 can never collide.** Reliability comes from algorithm, entropy, coordination where required, constraints, and monitoring.

### 22.2. Testing Transactions

- Two transactions racing on the same business key: only one succeeds per `UNIQUE` or policy.
- Timeout after `COMMIT`: retry returns the previously committed outcome.
- Registry `INSERT` succeeds but partitioned-table `INSERT` fails: both roll back together.
- Switching tenants or permissions: queries never leak data across tenants.
- Source sends the same `event_id` with a changed timestamp/payload: never silently treated as an identical retry.

## 23. Operations and Monitoring Identity Failures

| Metric | Purpose |
|---|---|
| IDs generated/sec per node | Forecast load and counter saturation |
| UUID generator errors | Detect broken RNGs or implementations |
| Unique violations by constraint | Separate collisions from retries or bad mappings |
| Idempotency replays vs. conflicts | Distinguish valid retries from payload mismatches |
| Clock rollbacks/skew | Prevent Snowflake failures and bad timestamps |
| Worker lease expirations/fencing | Prevent duplicate worker IDs |
| Remaining allocated ranges | Alert before exhaustion |
| Registry/dedup table size | Manage retention and write throughput |
| Unmapped legacy IDs | Catch migration gaps |
| Invalid cross-shard references | Catch broken logical integrity |
| Unsynced provisional records | Track offline lag and pending conflicts |
| Event consumer dedup rate | Monitor duplicate message deliveries |

A **unique violation** is far more likely a retry or business-key collision than a random UUID collision. Log **constraint name, source, and request code** safely for investigation without logging sensitive payloads.

### 23.1. Capacity and Rollover

With Snowflake, timestamp bit width plus custom epoch determines when the time space exhausts. Plan format or state upgrades well before that date—never let timestamps wrap to 0.

With range allocators, monitor remaining IDs and pre-allocate fresh ranges. With UUIDs, track generator quality and library versions, especially on client devices outside operations' direct control.

## 24. Lab Exercise: Three Order-Creation Sites, Two Databases, and Offline Tablets

A retail system operates in HN, HCM, and on offline tablets. Requirements:

- Orders have stable IDs from the moment of creation.
- Zero ID conflicts when merging data.
- Retries never create duplicate orders or double payments.
- Orders and order lines preserve referential integrity.
- Tenant and source order codes are stored for traceability.
- Events can be partitioned monthly with 90-day raw retention.
- A single customer may have profiles in two CRM systems.
- Orders may migrate between shards in the future.

### 24.1. Reference Design

One approach:

~~~mermaid
flowchart TD
    A["Offline tablet"] --> U["Global UUID generated once"]
    HN["POS HN"] --> U
    HCM["POS HCM"] --> U
    U --> L["Store order + children with stable ID"]
    L --> X["Sync with idempotency key"]
    X --> C["Validate namespace / request"]
    C --> O["Authoritative order source"]
    O --> E["Outbox event preserves event_id"]
    E --> P["Idempotent consumer / reports"]
~~~

The model can use:

- **`order_id` UUIDv4/UUIDv7** generated once and persisted durably.
- **`(tenant_id, origin_system, source_order_key)`** as the unique business identity within the authoritative scope.
- **`(tenant_id, client_id, request_id)`** for request idempotency.
- **`line_id` UUID** per line, with FK to `order_id`.
- **Distinct `event_id` UUID** per event, plus `aggregate_version` to protect per-order sequence.
- **Source crosswalk** for legacy `bigint` IDs.
- **Event identity registry** if the partitioned table must enforce `event_id` uniqueness across months in the same database.
- **Canonical customer ID** and source mapping table for duplicate CRM profiles.

This fits offline-first operation, yet **does not automatically enforce strong business uniqueness if HN and HCM write the exact same source key while disconnected**. You still need a single authority, partitioned key-issuance rights, or provisional/reconciliation states.

### 24.2. Practice Questions

1. Write separate invariants for `global_order_id`, `source_order_key`, `request_id`, `event_id`, and `order_number`.
2. Explain why two `local_id` values of `1001` do not mean two orders are duplicates.
3. Choose among UUIDv4, UUIDv7, Snowflake, or composite keys; analyze offline support, indexing, and coordination.
4. If using Snowflake, how are worker IDs allocated and what must a node losing its lease do?
5. Design `orders`/`lines` tables with appropriate `UNIQUE`/`FK` constraints and tenant keys.
6. Trace retrying `CreateOrder` five times with the same `request_id` after the first response dropped; exactly one order must exist.
7. Handle a matching `request_id` with a different payload, and a single source sending two distinct requests for one source order code.
8. Explain why a UUID PK does not stop two profiles for the same customer.
9. If HN and HCM both accept an order during a network partition, what is the authoritative-source policy?
10. When partitioning events by `event_ts`, how is global `UNIQUE(event_id)` protected?
11. When syncing a tablet, which `order_id` does `order_line` point to, and when is remapping required?
12. When moving an order to another shard, why should `global_order_id` stay constant?
13. Design a crosswalk for two legacy sources that both issued `local_id = 1001`.
14. Propose a test matrix covering clock rollbacks, duplicate node IDs, retries, partitions, consumer replays, and migrations.
15. Describe tenant authorization; explain why hard-to-guess IDs are insufficient to secure APIs.

**Passing criteria:** explicit uniqueness scopes; ID strategy compatible with offline operation and sync; clear separation between ID collisions, retries, and duplicate entities; constraints enforced at the authoritative store; references and idempotency intact across partitioning and shard moves.

## 25. Design Review Checklist

- **Scope:** Must the ID be unique within a database, tenant, source, region, or the entire system?
- **Identity roles:** Are business keys, global IDs, request IDs, event IDs, and document numbers given separate roles?
- **Issuance:** Can all writers mint from the same space without colliding?
- **Offline:** Are IDs and request keys generated once and persisted durably before sending?
- **UUID:** Valid RNG and format, no unverified bit truncation, PK error handling in place?
- **Snowflake:** Worker leases/fencing, clock rollback, sequence overflow, and rollover defined?
- **Namespace:** Are origin/tenant/source exclusive, stable, and protected against improper reuse?
- **Database:** What actual scope do `PRIMARY KEY`/`UNIQUE` enforce?
- **Partitioning:** Does `event_id` require a database-wide registry, or is `(event_ts, event_id)` uniqueness sufficient?
- **Idempotency:** Do identical payloads return the prior outcome, mismatched payloads raise conflict, and consumer retries avoid double side effects?
- **Distribution:** If two regions write while disconnected, are business-key conflicts prevented or reconciled?
- **Relationships:** Do `FK`/`order_line` checks and tenant isolation hold across shards?
- **Identity resolution:** When multiple systems create profiles for one entity, is there canonical mapping and evidence-based merging?
- **Migration:** Do legacy IDs have a crosswalk, are all child FKs remapped, and is late-arriving data handled?
- **Ordering:** Are numeric IDs avoided as commit order or effective time when the algorithm does not guarantee it?
- **Security:** Do APIs enforce tenant/authorization checks instead of treating random IDs as access tokens?
- **Operations:** Are unique violations, worker leases, clock skew, range depletion, registries, and sync errors monitored?

**Conclusion:** identifiers created across multiple locations are only trustworthy with explicit **uniqueness scopes, issuance mechanisms, validation constraints, sync policies, and recovery procedures**. UUIDs enable independent generation with negligible collision odds; Snowflake yields compact integers at the cost of worker and clock coordination; composite keys and range allocators rely on disjoint namespaces. Regardless of choice, **non-colliding IDs alone never stop retries from duplicating side effects, never resolve duplicate entity profiles, and never replace transactional constraints or authorization**. Those must all be modeled and verified independently.
