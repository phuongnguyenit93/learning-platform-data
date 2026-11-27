# Cross-Partition Queries, Distributed Transactions, and Coordination Cost

## 1. The Problem: How Many Storage Locations Can One Business Request Touch?

Suppose an e-commerce platform holds hundreds of millions of orders. The business wants to partition data to manage storage and scale out. Yet requests such as "show this customer's orders," "calculate system-wide revenue," or "transfer funds between two wallets" can touch **multiple partitions or multiple servers**.

Three questions must be separated before picking a design:

1. **Where does data live?** One database with multiple physical partitions, or multiple shards/clusters where different machines hold write authority?
2. **How many places must reads visit?** Does the query route to one partition, or must it scatter, exchange data, and merge results?
3. **At what scope must writes stay consistent?** Do changes commit inside one transaction on one database, or span multiple sources of truth with independent transactions and response times?

A system can be **heavily partitioned** yet still process transactions inside **a single database**. Conversely, two shards sitting in the same datacenter still demand distributed coordination because they maintain independent transaction logs and commit authorities.

In data modeling, partitioning is not merely an operational decision. It shapes **keys, foreign keys, uniqueness, aggregate boundaries, JOINs, latency, recovery, and how users interpret query results**.

### Running Example

The platform manages:

- `Order`: customer orders, line items, and fulfillment status.
- `SeatInventory` or `StockReservation`: the sole authority allowed to confirm available stock/seats.
- `Payment`: provider-verified captures and refunds.
- `Customer`: customer data scoped by tenant and region.
- Reporting: daily sales by tenant, product, and sales channel.

If an order and its line items always share one partition, reading an order is cheap. If the order sits on shard A, reserved stock on shard B, and payment on shard C, "order placed successfully" cannot be treated as a single `UPDATE`.

## 2. Single-DB Partitioning vs. Multi-Writer Sharding

| Concept | Organization | Transaction / Constraint Scope | Typical Consequences |
| --- | --- | --- | --- |
| **Single-DBMS partitioning** | One logical table split into partitions by date, tenant, hash, etc. under one DBMS | Many engines support transactions across partitions of **the same database**; key/index/unique rules depend on DBMS | Managing large tables, partition pruning, easy periodic archiving/purging |
| **Multi-node sharding** | Data slices sit on independent nodes/clusters/databases; apps/routers route requests | Transactions are local per shard; cross-shard atomicity needs explicit coordination | Distributed throughput and capacity, adding network latency, partial node failures, and complexity |
| **Replication** | Multiple copies of the same data for reads and high availability | Depends on leader/quorum, synchronous vs. asynchronous | Does not split data size; replica reads can be stale |
| **Federation / distributed query** | Query engine reaches multiple stores or data services | Primarily read-oriented; does not automatically guarantee consistent snapshots across sources | JOINs and aggregations may transfer data across the network |
| **Co-location** | Frequently co-accessed rows or operations placed on the same partition/shard | Minimizes cross-node operations | Accelerates target workloads; can cause skew/hot shards |

**Critical distinction:** PostgreSQL declarative partitioning inside **one instance** does not turn PostgreSQL into a distributed transaction system. When a transaction updates two partitions in the same PostgreSQL database, it remains an ordinary database transaction. Cross-source atomic commit issues arise only when operations span **multiple independent databases/clusters**.

A data model must clarify which layer "partition" refers to: table, node, cluster, tenant, or business domain. Never infer a need for Sagas or Two-Phase Commit just from counting child partition tables.

## 3. Why Are Cross-Partition Queries More Expensive?

A query like "show all orders for tenant T in November" can route to a small subset of partitions when filter predicates match the partition key. By contrast, "find an arbitrary order ID without knowing the order month" may scan many partitions unless a routing table or suitable global index exists.

Three cost components must be evaluated:

- **Read volume:** how many partitions are opened, how many rows/pages are scanned, and can indexes be used?
- **Coordination cost:** how much work the router/coordinator spends planning, dispatching to shards, waiting, retrying, and merging?
- **Data exchange cost:** how many bytes cross the network for `JOIN`, `SORT`, `DISTINCT`, or `GROUP BY`; are shuffles/repartitions required?

When shards execute in parallel, latency is roughly:

~~~text
T_query ≈ T_routing
        + MAX(T_shard_i_processing + T_shard_i_transfer)
        + T_result_merge
        + T_coordination_overhead
~~~

This formula is a mental model of components, **not** an exact description of every engine or pipeline. If the coordinator runs sequentially or networks saturate, total cost climbs higher. Scaling from 1 shard to 20 shards increases the odds of hitting **one slow shard**: fan-out queries are governed by tail latency.

### Partition Pruning

**Partition pruning** happens when the optimizer skips partitions guaranteed not to hold matching rows, based on the partition key and filter expressions.

- If partitioned monthly by `placed_at`, an explicit date-range predicate typically prunes other months.
- If sharded by `tenant_id`, an exact `tenant_id` predicate lets the router target one shard.
- Filtering solely by `customer_name` with no mapping to the shard key may force fan-out.
- Writing `WHERE date(placed_at) = :day` can prevent some optimizers from inferring partition bounds compared to half-open intervals on the raw column; always inspect real execution plans.

### Example Queries

~~~sql
-- Typically favorable for RANGE partitioning on placed_at.
SELECT tenant_id, order_id, placed_at, status
FROM orders
WHERE tenant_id = :tenant_id
  AND placed_at >= TIMESTAMPTZ '2026-11-01 00:00:00+00'
  AND placed_at <  TIMESTAMPTZ '2026-12-01 00:00:00+00';

-- Missing placed_at: needs a routing strategy by order_id
-- or may search across multiple partitions.
SELECT *
FROM orders
WHERE tenant_id = :tenant_id
  AND order_id = :order_id;
~~~

Never claim the second query **always runs a full scan**: it may use local indexes across partitions, a directory lookup, a global index if the DBMS supports one, or separate routing metadata. The issue is **search scope** and merge cost, not merely whether an index exists.

## 4. Choosing Partition/Shard Keys from Queries and Invariants

A good partition key balances **routing, load distribution, stability, and the scope of data needing joint transactions**.

| Candidate Key | Helpful For | Risks |
| --- | --- | --- |
| `tenant_id` | Tenant isolation, intra-tenant reads/writes, co-locating tenant data | Oversized tenants become hot shards; system-wide reports still fan out |
| `order_id` hash | Even order spread, lookups by order ID | Queries for all orders of a tenant or monthly lines scatter across shards |
| Monthly `placed_at` | Periodic pruning, monthly retention/archiving, time scans | New orders pile into the latest partition; order ID lookups without month scatter |
| `region_id` | Regional residency compliance, local workloads | Uneven regions, cross-region transactions, and region migrations |
| Composite `tenant_id + entity_id` | Clear routing scope and cross-tenant ID isolation | Requires canonical hash/key conventions; does not solve multi-entity queries |

Placing **`Order` and `OrderLine` on the same shard** is usually helpful because order creation and line items form a local consistency boundary. However, a single seat or inventory unit can be contested by **multiple Orders**: you cannot prevent double-booking merely by locking individual order rows.

### Co-Location Rule

~~~mermaid
flowchart LR
    R["Router by tenant_id / order_id"] --> A["Shard A: Order + related OrderLines"]
    R --> B["Shard B: other Orders"]
    A --> PA["Read order, lines, local updates"]
    B --> PB["Read other orders"]
    A -. "Placing order needs stock reservation" .-> I["Stock owner / inventory shard"]
    B -. "Placing order needs stock reservation" .-> I
~~~

The diagram shows that co-location solves **certain** common operations, not every invariant. Explicitly identify which aggregate owns inventory or seat counts; all competing bookings must converge on that single decision point.

### Hot Shards and Skew

Even hashing over customer IDs does not balance load if one customer is huge. Time-range partitioning does not automatically balance writes when new writes hit the latest interval. Choose keys from **read/write traffic** distribution, tenant sizes, access patterns, and key mutability.

**Never change a shard key in production without a migration plan**: changing keys can require moving rows, updating routes, handling in-flight requests, and ensuring two shards never accept authoritative writes simultaneously.

## 5. Cross-Partition JOINs: Co-Located, Broadcast, or Shuffle?

`JOIN`s easily incur heavy network costs when data sits in different places.

| Strategy | Mechanism | When to Use | Risks |
| --- | --- | --- | --- |
| **Co-located JOIN** | Rows with matching JOIN keys sit on the same shard; JOIN executes locally | Both tables are sharded by the same key with identical placement | Breaks down if the JOIN path differs from the shard key |
| **Broadcast JOIN** | Replicate a small table to workers for local JOINs | Dimension/reference data is genuinely small and changes per policy | "Small" table grows large; repeated copying, stale references |
| **Repartition / shuffle JOIN** | Stream one or both sides re-hashed by JOIN key so matches meet | Large tables neither co-located nor broadcastable | Heavy network transfer, disk spills, bottlenecks, and skew |
| **Lookup / remote JOIN** | Fetch reference rows via service/index by key | Selective access, few keys, valid caching | N+1 request patterns, timeouts, and cache staleness |
| **Precomputed mart / materialized view** | Pre-join frequent relationships | Repeated dashboards tolerating documented lag | Rebuilds, invalidation, and lag when sources mutate |

Suppose `orders` and `order_lines` both distribute by `order_id`. They can JOIN locally on each shard. Yet `dim_product` distributed by `product_id` may live elsewhere. For a product-category sales dashboard, broadcast the **small product dimension** or build an enriched fact/mart from event streams with clear lineage.

**You cannot partition the same copy of data along every JOIN key simultaneously.** Optimize for the primary workload, and serve secondary questions via indexes, materializations, read copies, or specialized services.

### Avoiding Fan-Out Traps from Wrong Grain

An order has 3 line items and 2 payments; joining `order_line` directly to `payment_movement` on `order_id` yields **6 rows** and doubles monetary amounts. This error occurs even when all rows sit in the same partition. Partitioning merely makes it harder to spot when local and global aggregations mix.

Define grain clearly:

- `fact_order_line`: one line item of one order.
- `fact_payment_movement`: one verified transaction from the payment source.
- `dim_product`: one product or product version per effective-time rules.

To report collected payments alongside line-item sales per day, **aggregate each fact to a compatible grain before joining**, or track separate metrics. Never take `SUM` after a many-to-many `JOIN` as valid truth.

## 6. GROUP BY, DISTINCT, TOP-K, and Global Pagination

Distributed aggregations typically run in two stages:

1. **Partial aggregation** inside each shard to shrink row transfer.
2. **Global merge** at the coordinator or next processing tier to combine results.

Example summing revenue by day and currency:

~~~text
Shard A: 2026-11-20 / VND -> 120,000,000
Shard B: 2026-11-20 / VND ->  80,000,000
Shard C: 2026-11-20 / USD ->       9,000

Global:
2026-11-20 / VND -> 200,000,000
2026-11-20 / USD ->       9,000
~~~

Never sum 200 million VND and 9,000 USD without an approved exchange-rate rule specifying timestamp and rate source.

| Operator | How Can It Merge Locally? | Caveats |
| --- | --- | --- |
| `SUM`, `COUNT` | Local sums, then sum partial sums | Same grain, units, no double counting |
| `AVG` | Combine `SUM` and `COUNT`, then divide | Never compute an unweighted `AVG(AVG(...))` |
| `MIN`, `MAX` | Min/max of local values | `NULL`s, filters, and time semantics must match |
| `COUNT(DISTINCT customer_id)` | Needs global deduplication or an error-bounded sketch | Same customer spans shards; summing local distinct counts is wrong |
| `TOP K` | Each shard returns candidates; coordinator merges/sorts | Tie-breakers and filters must align; return enough candidates |
| `ORDER BY ... LIMIT/OFFSET` | Local sort and merge | Large `OFFSET` wastes resources; live mutations shift pages |

### Consistent Pagination

For a system-wide order list, `ORDER BY placed_at DESC` is non-deterministic when orders share identical timestamps. Add a scope-unique tie-breaker:

~~~sql
ORDER BY placed_at DESC, tenant_id DESC, order_id DESC
~~~

**Keyset pagination** using a cursor with all sort columns generally beats large `OFFSET`s. Still, if data mutates between requests, even keyset cursors **do not guarantee an immutable global snapshot** unless backed by a consistency watermark or an explicit policy tolerating live drift.

On auditable dashboards, publish the **as-of/watermark/snapshot version** alongside numbers rather than displaying totals without saying how current each shard is.

## 7. Consistency When Reading Across Multiple Shards

A query spanning 10 shards can read data captured at 10 slightly different points in time:

- Shard A has committed `PaymentCaptured`.
- Shard B has not yet received the shipping status event.
- Shard C's read replica lags behind its leader.
- One shard is failing over and returns data from an older log position.

Thus, "the query finished" does not mean the result is **a globally consistent snapshot**.

### Consistency Expectations to Document

| Read Need | Acceptable Level | Mechanisms to Consider |
| --- | --- | --- |
| Minute-level ops dashboard | Eventual consistency with measured lag | Per-shard lag, watermarks, label numbers provisional |
| User viewing newly created order | **Read-your-writes** after command succeeds | Read leader, session token/version, or await projection for that order |
| Period-close financial reports | Consistent/reconciled source cutoff per rules | Source barriers/checkpoints, period locking, versioned restatements |
| Fund transfers or balance writes | Atomicity/serializability at authoritative source | Explicit transactions and protocols; never decide from stale replicas |
| Forensic query as of time X | Must distinguish "known at X" vs. "effective at X" | Source time and record time, bitemporal modeling if needed |

A single distributed database may support global snapshots/distributed transactions, yet **never assume** arbitrary federated queries do. When combining engines without shared transaction clocks or commit protocols, state snapshot limits explicitly—sometimes a watermarked, reconciled report is far more trustworthy than a promise that "everything is real-time."

### Parallel Queries Can Miss or Double-Count Moving Data

During resharding, a row may copy from A to B or change routes. A query fanning out to both A and B without valid identity/cutover rules can double-count an order; flipping routes too early can drop in-flight rows.

You need **routing epochs/versions**, cutover gates, per-shard read-ownership rules, and deduplication by business key and record version. Appending `DISTINCT` at the end fails whenever two copies carry different statuses or amounts.

## 8. Global Constraints Are Harder Than Local Constraints

One of the biggest trade-offs of sharding is that **PK, FK, `UNIQUE`, `CHECK`, and transactions** may only be enforced by the DBMS within **a single shard**.

| Invariant | In One Database / Shard | When Data Is Sharded |
| --- | --- | --- |
| Unique order key per tenant | Unique key/PK enforced directly | Requires unique routing/namespace, global registry, or guaranteed ID scheme |
| One seat belongs to at most one active booking | Unique/lock on seat/reservation table under one owner | Bookings across shards must call the single **seat owner** to decide |
| Line item references an existing order | FK inside the same supporting DBMS | Cross-shard FKs are rarely enforced by DBMS; needs workflow/checks |
| Never deduct balance below limit | Locks and transactions on the balance owner | Limits spanning shards need a central reservation point or global consistency |
| Daily totals are accurate | Query on one snapshot, grain, and unit | Requires complete partial aggregates, dedup, watermarks, and reconciliation |

**Redefine aggregate boundaries when needed.** If "never double-sell a seat" is a hard invariant, locking `Booking` by `booking_id` fails when two bookings on different shards pick the same seat. The final authority must be `SeatInventory`, `SeatReservation`, or a store/transaction that serializes reservations for that seat.

### Global Uniqueness

A UUID offers negligible collision odds, which is different from an **enforceable business uniqueness constraint**. Emails, promo codes, or seat numbers require strict uniqueness within explicit scopes. Options:

- **Route every record sharing the unique key to the exact same owner** so the local database enforces the constraint.
- Use a **registry/uniqueness service** with reserve/commit/release steps, request IDs, and timeout handling.
- Use **namespaced keys** (`tenant_id + external_id`) when uniqueness is tenant-scoped.
- Redesign business rules so uniqueness is not needlessly global.

A global registry introduces a new **coordination point** and potential hotspot—it is never free. Never rely on pre-checking `SELECT NOT EXISTS` across shards followed by independent writes when concurrent races exist.

## 9. PostgreSQL Example: Monthly Partitions Still Share One Transaction

The example below models orders and line items inside **one PostgreSQL database**, partitioned by `placed_at`. The goal is distinguishing partition pruning from cross-machine transactions.

~~~sql
CREATE TABLE orders (
    tenant_id       UUID NOT NULL,
    placed_at       TIMESTAMPTZ NOT NULL,
    order_id        UUID NOT NULL,
    customer_id     UUID NOT NULL,
    status          VARCHAR(24) NOT NULL
                    CHECK (status IN
                        ('PLACED', 'CANCELLED', 'FULFILLED')),
    total_minor     BIGINT NOT NULL CHECK (total_minor >= 0),
    currency        CHAR(3) NOT NULL,
    PRIMARY KEY (tenant_id, placed_at, order_id)
) PARTITION BY RANGE (placed_at);

CREATE TABLE orders_2026_11 PARTITION OF orders
    FOR VALUES FROM ('2026-11-01 00:00:00+00')
               TO   ('2026-12-01 00:00:00+00');

CREATE TABLE orders_2026_12 PARTITION OF orders
    FOR VALUES FROM ('2026-12-01 00:00:00+00')
               TO   ('2027-01-01 00:00:00+00');

CREATE INDEX ix_orders_tenant_date
    ON orders (tenant_id, placed_at DESC);

CREATE TABLE order_lines (
    tenant_id       UUID NOT NULL,
    placed_at       TIMESTAMPTZ NOT NULL,
    order_id        UUID NOT NULL,
    line_no         INTEGER NOT NULL CHECK (line_no > 0),
    product_id      UUID NOT NULL,
    quantity        NUMERIC(18, 3) NOT NULL CHECK (quantity > 0),
    line_minor      BIGINT NOT NULL CHECK (line_minor >= 0),
    PRIMARY KEY (tenant_id, placed_at, order_id, line_no),
    FOREIGN KEY (tenant_id, placed_at, order_id)
        REFERENCES orders (tenant_id, placed_at, order_id)
) PARTITION BY RANGE (placed_at);

CREATE TABLE order_lines_2026_11 PARTITION OF order_lines
    FOR VALUES FROM ('2026-11-01 00:00:00+00')
               TO   ('2026-12-01 00:00:00+00');

CREATE TABLE order_lines_2026_12 PARTITION OF order_lines
    FOR VALUES FROM ('2026-12-01 00:00:00+00')
               TO   ('2027-01-01 00:00:00+00');
~~~

**Meaning and limits:**

1. PostgreSQL requires PK/UNIQUE on a partitioned table to include **the partition key** per supported rules. Hence `orders` includes `placed_at` in its PK.
2. With this PK, the database **does not automatically enforce** `(tenant_id, order_id)` uniqueness across all months. An order ID could be inserted in another month without a separate business safeguard.
3. The foreign key from `order_lines` to `orders` shares `placed_at`, identifying the parent row by the chosen physical key. On other DBMSs or multi-cluster sharding, verify FK support separately.
4. This example only creates two months; production must pre-create partitions, manage boundaries, handle missing partitions, maintain indexes, retention, and migrations.
5. Use `TIMESTAMPTZ` and UTC half-open intervals to prevent boundary overlaps. "Month by local business date" is a different requirement that may call for a normalized `business_day` partition key.
6. Mutating `placed_at` after insert can force row relocation across partitions and complicate FKs. For orders, keep the authoritative placement timestamp immutable; handle corrections through separate workflows.

### Multi-Partition Transaction in One Database

~~~sql
BEGIN;

INSERT INTO orders (
    tenant_id, placed_at, order_id,
    customer_id, status, total_minor, currency
) VALUES (
    :tenant_id, :placed_at, :order_id,
    :customer_id, 'PLACED', :total_minor, :currency
);

INSERT INTO order_lines (
    tenant_id, placed_at, order_id,
    line_no, product_id, quantity, line_minor
) VALUES (
    :tenant_id, :placed_at, :order_id,
    :line_no, :product_id, :quantity, :line_minor
);

COMMIT;
~~~

Even though both tables are partitioned, these two writes commit or roll back inside **a single PostgreSQL transaction**. This is **not 2PC across independent shards**.

If `order_id` must be unique per tenant across all time, you can add an **unpartitioned** `order_id_registry(tenant_id, order_id, placed_at)` table with `PRIMARY KEY (tenant_id, order_id)` and register the ID inside the same transaction. Note that a registry table can grow large or become a hotspot; across multiple clusters, global uniqueness still requires an owner/coordination mechanism. Never treat a single-DB registry as an automatic multi-cluster solution.

### Checking Pruning via the Execution Plan

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, status, total_minor
FROM orders
WHERE tenant_id = :tenant_id
  AND placed_at >= TIMESTAMPTZ '2026-11-01 00:00:00+00'
  AND placed_at <  TIMESTAMPTZ '2026-12-01 00:00:00+00';
~~~

In a suitable test environment, inspect which partitions are scanned, row counts, timings, buffers, and index effectiveness. `EXPLAIN ANALYZE` **executes the query**; avoid running it carelessly on live write statements. Never assume every PostgreSQL version or distributed SQL engine picks the identical plan for the same SQL.

## 10. When One Command Must Mutate Two Shards: Requirements to Define

Consider transferring 100,000 VND from a wallet on shard A to a wallet on shard B. From a business standpoint, you must never report "transfer succeeded" if funds were debited on A without being credited on B.

Questions to ask:

- **Atomicity:** must both sites commit or neither?
- **Isolation:** mid-transfer, what intermediate state may other transactions observe?
- **Durability:** if a node crashes, can committed states or transfer intent still be recovered?
- **Timeout/unknown outcome:** on timeout, how do we verify whether the credit occurred?
- **Idempotency:** could retrying the command transfer money twice?
- **Invariants:** where are total liabilities and spending limits enforced? Is a ledger the authoritative source?

Never confuse **atomic commit** with **business completion**. An external payment rail may not return final settlement immediately even after the local database commits a `TRANSFER_PENDING` row.

## 11. Two-Phase Commit (2PC): Atomic Commit with Coordination Cost

**Two-Phase Commit** coordinates multiple transaction participants to decide **commit together or abort together**, assuming all participants support the protocol and persist required logs durably.

### Phase 1 — Prepare

The coordinator asks each participant to validate and prepare its piece of the transaction. Participants durably record prepared state per DBMS mechanics, hold required locks/resources, and reply whether they can commit.

### Phase 2 — Commit or Abort

- If all reply prepared, the coordinator durably logs the commit decision and tells all participants to commit.
- If any participant fails to prepare, the coordinator decides abort and tells all participants to roll back.
- If the coordinator or network fails after prepare, participants may remain **blocked in an uncertain state** holding locks until the decision recovers.

~~~mermaid
sequenceDiagram
    participant App as Service
    participant C as Coordinator
    participant A as Shard A
    participant B as Shard B
    App->>C: Begin distributed transaction
    C->>A: PREPARE
    C->>B: PREPARE
    A-->>C: PREPARED
    B-->>C: PREPARED
    Note over C: Persist decision durably
    C->>A: COMMIT
    C->>B: COMMIT
    A-->>C: ACK
    B-->>C: ACK
    C-->>App: Committed
~~~

This diagram shows the **happy path**. When the coordinator crashes after prepare, decision recovery and resolving indoubt participants are mandatory parts of the design—never skip them just because a demo only shows the happy path.

### Trade-Offs of 2PC

| Benefits | Costs / Risks to Evaluate |
| --- | --- |
| Atomic commit across protocol-supporting participants | Extra round trips, durable logging, coordinator, and recovery paths |
| Preserves a "single transaction" mental model at commit level | Prepared transactions hold locks/resources; stalls during node/coordinator faults |
| Fits when partial commits are strictly unacceptable | Unusable when a "participant" is an external API lacking prepare/rollback |
| Supported in specialized distributed SQL / transaction coordinators | Must evaluate cross-node isolation and real fault tolerance, not just feature names |

**2PC does not automatically guarantee global serializability.** Atomic commit decides only whether parts commit or abort together; how concurrent transactions interleave and observe data still depends on system-wide isolation and concurrency control. Nor does it create "exactly once" for emails, message brokers, or external banks outside the transaction.

In PostgreSQL, prepared transactions like `PREPARE TRANSACTION` require dedicated configuration and governance; never enable them just to "solve" a business flow without a reliable coordinator, monitoring for stuck prepared transactions, and recovery runbooks.

## 12. Sagas and Compensating Actions: Business Coordination Instead of One Commit

When independent services cannot join one distributed transaction, a **Saga** orchestrates a sequence of **local transactions** paired with failure-handling and compensating actions.

Ticket-booking workflow example:

1. `Booking` creates a `PENDING` record in its own store.
2. `SeatInventory` places a time-bounded hold and confirms the reservation.
3. `Payment` issues a capture request with an idempotency key.
4. Once `Payment` confirms capture, `Booking` transitions to `CONFIRMED`.
5. If seat holding fails or capture is declined, earlier steps are canceled/compensated according to actual state.

~~~mermaid
flowchart TD
    B["Booking PENDING"] --> S["Seat: reserve with idempotency key"]
    S --> OK{"Seat held?"}
    OK -->|"No"| X["Booking REJECTED"]
    OK -->|"Yes"| P["Payment: request capture"]
    P --> C{"Verified outcome?"}
    C -->|"Captured"| F["Booking CONFIRMED"]
    C -->|"Failed"| R["Release seat if reservation still valid"]
    R --> Z["Booking FAILED"]
    C -->|"Unknown / timeout"| U["Payment PENDING_RECONCILIATION"]
    U --> Q["Poll provider / wait callback / reconcile"]
    Q --> C
~~~

**Subtleties:**

- "Sending a refund command" means `RefundRequested`, not `RefundConfirmed`. Compensations cannot always instantaneously undo a completed capture.
- A sent email or shipped parcel **cannot roll back like SQL rows**; compensation must model a new business fact (apology, recall, refund) with explicit limits.
- If `Payment` times out, **never assume capture failed** and send a fresh charge with a new ID. Reconcile using the transaction ID / idempotency key.
- Sagas embrace **intermediate states**. APIs and dashboards must represent `PENDING`, `FAILED`, `COMPENSATING`, or `NEEDS_REVIEW` instead of forcing binary success/failure.
- Sagas **are not equivalent to system-wide ACID atomicity**; they manage long-lived workflows and consistency over time.

### Minimal Orchestration State Design

A Saga task table might track `saga_id`, `business_request_id`, `step`, `state`, `expected_entity_version`, `retry_count`, `last_error_code`, and expiration deadlines. Every step needs a **stable idempotency key**—never mint a random new request ID on retries.

When choosing a Saga, explicitly specify **when the system is allowed to show business success** and which steps can actually be compensated after real-world side effects.

## 13. Transactional Outbox: Local Transactions and Reliable Messaging

**Transactional outbox** closes the dangerous gap between "committed in DB" and "published message." Inside the **local** transaction, the app persists both the business record and an outbox row.

~~~sql
CREATE TABLE booking_outbox (
    message_id       UUID PRIMARY KEY,
    booking_id       UUID NOT NULL,
    event_type       VARCHAR(100) NOT NULL,
    schema_version   SMALLINT NOT NULL CHECK (schema_version > 0),
    payload          JSONB NOT NULL
                     CHECK (jsonb_typeof(payload) = 'object'),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at     TIMESTAMPTZ
);

CREATE INDEX ix_booking_outbox_pending
    ON booking_outbox (created_at, message_id)
    WHERE published_at IS NULL;
~~~

Updating `booking.state` and inserting into `booking_outbox` in the same transaction prevents losing **publication intent** after commit. A relay forwards messages to the broker; if the relay crashes after sending but before marking `published_at`, the message gets redelivered. Consumers must deduplicate by `message_id` and/or business operation key.

**Outbox does not make cross-shard transactions atomic.** It provides a reliable handoff from a local transaction to downstream steps. If `SeatInventory` and `Booking` remain independent sources of truth, their interaction still needs confirmations, timeouts, idempotency, and compensations.

### Preventing Duplicate Processing at Consumers

A consumer can keep a `processed_message(consumer_name, message_id)` table with a composite PK, inserting the marker and updating its read model **within the same transaction**. If the marker already exists, skip the duplicate. Updating the target first and recording the marker in a separate transaction allows crashes between the two to double-apply updates.

Distinguish:

- `message_id`: identifies the message delivery to stop duplicate replay.
- `business_request_id`: identifies the business operation to stop duplicate commands.
- `entity_version`: detects stale or out-of-order states.
- `event_id`: identifies the fact accepted at the source.

Never assume one ID substitutes cleanly for all the others in every architecture.

## 14. Choosing Among Local Transactions, 2PC, Sagas, and Boundary Redesign

| Approach | Core Guarantee | When to Choose | What It Does NOT Solve Automatically |
| --- | --- | --- | --- |
| **Single-DB / single-shard transaction** | Atomicity/isolation within DBMS scope | Core invariants can co-locate | External APIs, brokers, and other data sources |
| **2PC / distributed transaction** | Atomic commit across supporting participants | Partial commits unacceptable; infra provides coordinator and isolation | Side effects lacking prepare, global serializability unless guaranteed |
| **Saga** | Coordinates local transactions and compensations | Independent services; managed intermediate states acceptable | Instant physical rollback or system-wide atomicity |
| **Reservation / escrow / owner** | Turns a global invariant into a single-owner decision | Contested resources, stock, or quotas needing clear enforcement | Latency to owner, hotspots, and owner availability |
| **Async read model / ETL** | Aggregations or views built from multiple sources | No immediate cross-shard write decision needed | Staleness/consistency and source reconciliation errors |

**Shrink the coordination boundary first** before reaching for expensive protocols:

- Co-locate records tied by tight invariants.
- Assign a clear single owner for inventory/seats/balances.
- Avoid transactions mutating Catalog, Order, CRM, and Analytics together merely because one API wants a rich response.
- Separate transactional decision data from analytical reporting data.
- Turn non-synchronous steps into outbox + projections with explicit SLAs.

2PC or Sagas are **consequences of consistency requirements and source-of-truth boundaries**, not the starting point of data modeling.

## 15. Resharding: Moving Data Increases Coordination Cost

When a shard outgrows capacity, the system may need to split shards, add nodes, or migrate a tenant. This is far more than copying rows.

High-level workflow:

1. **Map current ownership** of each partition/shard and `routing_epoch` version.
2. **Prepare target and copy historical data** with checksums, row counts, and access boundaries.
3. **Tail ongoing changes** via CDC/logs/sync ensuring zero missed commits; never rely on pre-commit `MAX(id)` as a safe watermark.
4. **Catch up the tail**; verify row counts, business keys, versions, monetary totals, deletes, and corrections.
5. **Transfer write authority** using fencing tokens/leases or locks; never allow two shards to commit simultaneously as valid owners.
6. **Switch read routing** and observe stale/duplicate anomalies until target proves trustworthy.
7. **Decommission legacy source** per retention and approved rollback plan.

If router A holds an old routing epoch while router B holds the new one, two requests can hit different shards. Use versioned redirects/lookup directories, fencing, or equivalent mechanisms matched to your system's fault tolerance and consistency model.

### Balance Load by More Than Row Counts

A shard holding 1 million cold historical orders can be far lighter than a shard holding 50,000 orders under heavy write contention. Monitor **CPU, write QPS, lock contention, network, storage, I/O, replication lag, and per-key hotspots**—not just row counts.

Adding nodes spreads storage, yet **does not eliminate query fan-out cost**. A report querying all tenants may hit even more nodes after scaling out.

## 16. Differences Across Storage Engines and Data Models

| Store / Model | Common Distribution Strategies | Classic Pitfalls |
| --- | --- | --- |
| **Relational OLTP** | Tenant/order keys, indexes, time partitions; FKs/uniques within scope | Cross-shard JOINs, global constraints/transactions, hot keys |
| **Document databases** | Shard key by tenant/document owner; embed aggregates vs. reference | Queries missing shard key scatter; multi-doc/cross-shard transactions cost more |
| **Graphs** | Community/vertex partitioning, selective edge or neighbor replication | Traversals crossing partition boundaries hit many network hops; supernode fan-out |
| **Analytical / MPP** | Hash/range distribution, clustering, small broadcasts, shuffle joins | Data skew, massive shuffles, global distinct counts, merge time and scan cost |
| **Time-series** | Time + sensor/tenant keys, periodic rollups and retention | Current-interval hotspots, late edits to old partitions, measurement-ID uniqueness |

**Never copy rules blindly across engines.** Whether "shard keys must sit inside unique indexes" or "transactions span partitions" depends on the exact DBMS and partitioning setup. Read the technology's real contract and verify against your workload and failure modes.

Across all models, **identity, grain, time semantics, and invariant ownership** must remain crystal clear so the system always knows which slice of data it queries or updates.

## 17. Measuring Coordination Cost and Observing Operational Failures

A benchmark measuring single-query latency under zero failures is insufficient. Measure **tail latency, fan-out, network bytes transferred, and behavior when a shard slows down or disconnects**.

| Metric | What It Reflects | How to Use It |
| --- | --- | --- |
| **Partitions/shards touched per query** | Fan-out degree | Compare queries with vs. without routing keys |
| **Partition pruning ratio** | Partitions skipped | Catch query predicates misaligned with partition keys |
| **Rows/bytes shuffled** | Cross-node JOIN/`GROUP BY` cost | Decide between co-location, broadcast, or materialization |
| **p50/p95/p99 latency** | User latency and tail behavior | Measure impact of shard count growth or slow shards |
| **Coordinator CPU/memory/queue** | Bottleneck merging results | Consider partial aggregation, pushdown, query limits |
| **Lock wait / transaction duration** | Write/lock coordination | Catch long transactions or stuck prepared transactions |
| **Distributed commit failures / unknowns** | Hung/timed-out transactions needing recovery | Drive recovery and idempotency runbooks |
| **Saga pending/compensating age** | Incomplete workflows | Alert and reconcile stuck steps |
| **Outbox lag / duplicate count** | Relay delay and retries | Validate read-your-writes and consumer correctness |
| **Replica/CDC lag and watermarks** | Reporting freshness | Label provisional vs. finalized data; catch dropped records |
| **Hot shard/key skew** | Skewed load by tenant/ID | Guide splits, moves, routing, and rate limits |
| **Rebalance drift** | Missing/duplicate rows during moves | Reconcile source/target and routing epochs |

### Failure Scenarios to Rehearse

- One shard in a global query stalls for 10 seconds: does the coordinator time out or return partial data? **Never silently return partial results as complete.**
- A 2PC coordinator dies after both shards prepare: who recovers the decision and releases locks?
- The payment API times out after the provider captured funds: which ID do we retry with so we never double-charge?
- The outbox relay publishes a message and crashes before setting `published_at`: how do consumers deduplicate the replay?
- Resharding copies data while an update commits mid-transfer: which cursor proves zero missed updates?
- A lagging replica serves a period-end report: how does the system surface staleness?

Tie metrics and failure drills to **concrete SLOs**; without numerical targets, you cannot claim an architecture is "optimal" simply by adding shards.

## 18. Security, Privacy, and Auditability

Data distribution introduces governance risks too:

- **Tenant isolation:** routing keys must carry tenant scope so queries lacking `tenant_id` never cross tenants without authorization. Enforce at both authorization and data layers, not solely in the router.
- **Residency:** data restricted to specific geographies must obey residency across replicas, backups, caches, exports, and rebuild jobs.
- **Retention/deletion:** dropping time partitions is efficient, yet **does not automatically make wiping an entire period lawful**; legal holds and varied retention rules may apply.
- **Lineage:** global marts must trace back to source shards, versions/cursors, and transformation rules, especially after corrections.
- **Backup/restore:** snapshots taken across shards at different instants do not automatically form a globally consistent transaction backup; recovery needs consistent checkpoints or verified cutoffs.
- **Rebalancing:** staging copies may still hold personal data; govern permissions, encryption, and post-move cleanup.
- **Global IDs:** namespaces and reference identifiers must never be erroneously reused after moves, soft deletes, or onboarding new tenants.

Data from multiple regions or sources can carry distinct privacy rules. Never use replication as an excuse to "read every copy everywhere."

## 19. Partitioning Decision Workflow

A distribution **Architecture Decision Record (ADR)** should answer:

1. **Data and grain:** what are the business keys/PKs for `Order`, `OrderLine`, `PaymentMovement`, `Inventory`, and `Customer`?
2. **Query paths:** what are the top 10 highest-frequency/cost queries, and do predicates include shard keys?
3. **Invariants:** which operations must be immediately atomic/serializable; can they co-locate or route to a single owner?
4. **Partition keys:** tenant, order, region, or time? Verify real distribution and hotspots.
5. **Transaction scope:** single DB, multiple independent DBs, or multiple services with external side effects?
6. **JOIN/aggregation strategy:** co-located, broadcast, shuffle, precomputed mart, or two-stage queries?
7. **Read consistency:** eventual, read-your-writes, or period-close snapshots; which watermarks apply?
8. **Write strategy:** local transaction, 2PC, Saga, outbox, reservation/ledger owner?
9. **Evolvability:** adding shards, changing keys, resharding, schema migrations, history handling, and deletions?
10. **Verification:** SQL/constraints, chaos/failure tests, tail latency benchmarks, reconciliation, and rollback criteria?

### Condensed Decision Matrix

| Dominant Requirement | Design to Try First |
| --- | --- |
| Mostly per-tenant queries, rare cross-tenant | Co-locate by tenant; watch hot tenants |
| Massive periodic data with monthly retention | Range partition by day/month with indexes and partition lifecycle |
| Order and lines must commit together | Same database/shard with local transaction |
| A seat can only be sold once across sharded bookings | Dedicated seat owner / reservation service with concurrency control |
| Money transfer requiring joint commit across two transactional sources | Evaluate distributed transactions/2PC or revise ledger boundaries; verify isolation |
| Workflow with external providers, refunds/releases, intermediate states | Saga + outbox + idempotency + reconciliation |
| Daily enterprise-wide reporting | Partial aggregates / materialized analytical mart with watermarks and checks |
| Users must see their own writes immediately | Leader reads, session versions, or entity-scoped projection waits |

You rarely need every mechanism at once. Designs with fewer coordination paths are usually easier to get right, observe, and recover.

## 20. Practice Exercise: Optimizing Orders, Inventory, and System-Wide Reporting

**Context:** A multi-tenant event-ticketing platform serves multiple venues per tenant and thousands of seats per show. Orders and ticket lines write to shards by tenant/order; seat inventories belong to a separate Inventory service. Payment gateways return callbacks that can lag or repeat. Finance needs daily cash-flow reports by currency; support needs lookups for arbitrary order IDs.

### Design Tasks

1. **Draw the source-of-truth diagram:** `Order`, `SeatInventory`, `Payment`, `Customer`, and `Analytics`; identify each domain's DB/shard and owner.
2. **Choose shard keys:** compare `tenant_id`, `order_id`, `show_id`, and `placed_at` per domain; analyze fastest queries and worst hotspots for each choice.
3. **Define grain:** one order, one order line/ticket, one reservation per seat, one verified payment movement; avoid joining two facts of mismatched grain.
4. **Uniqueness/constraints:** how do you stop one seat from selling twice when two Bookings sit on different shards? Where must atomic/lock rules live?
5. **Order lookups:** a customer only knows `order_id`, not order date; design a global lookup/directory to avoid scanning every partition. Address stale routing and unique ID needs.
6. **Time partitioning:** design a monthly `orders` table and explain why PostgreSQL requires the partition key inside the PK; if `(tenant, order_id)` must stay unique forever, outline a registry or alternative partition key.
7. **JOINs:** explain when Order–OrderLine is co-located while Order–Product requires broadcast/shuffle or enriched copies.
8. **Aggregations:** write formulas for `gross_captured`, `refunded`, and `net_cash`, distinguishing them from `booked_sales`; never sum across different currencies.
9. **Global queries:** explain fan-out cost, partial aggregates, `COUNT DISTINCT`, and `TOP-K`; design pagination tie-breakers.
10. **Reservations:** describe local transactions inside `SeatInventory`, reservation idempotency, timeouts, and TTLs so unconfirmed holds never become sold tickets.
11. **Payments:** specify when to use a Saga, seat-release/refund steps, `PENDING_RECONCILIATION`, and why timeouts must not be treated as failures.
12. **2PC:** in a hypothetical transaction across two prepare-capable DBs, diagram both phases and explain what happens if the coordinator dies after prepare. List limits around isolation and external APIs.
13. **Read consistency:** pick acceptable consistency levels for customer pages, ops dashboards, and period-close finance reports; define watermarks.
14. **Resharding:** move a large tenant from shard A to B while orders keep arriving; design copying, CDC catch-up, fencing, cutover, and reconciliation.
15. **Observability:** list at least 8 metrics covering partition pruning, fan-out, network shuffles, p99, lock waits, saga lag, outbox lag, and migration drift.
16. **ADR:** choose a candidate design with workload, SLOs, failure tests, privacy controls, and rollback plan; state what evidence would make you reverse the choice.

### Self-Check Rubric

| Criterion | Passing Bar |
| --- | --- |
| **Terminology** | Never confuses single-DB partitions with independently transactional shards |
| **Keys** | Partition keys, PK/FK/unique constraints, and routing keys align with real workloads |
| **Read paths** | Includes pruning/lookups and analyzes fan-out, JOIN, and aggregation costs |
| **Invariants** | Seats never oversell; charges/refunds never claimed without provider confirmation |
| **Transactions** | Clearly differentiates local transactions, 2PC atomic commit, and Sagas with intermediate states |
| **Numeric accuracy** | No JOIN inflation, no cross-currency mixing, explicit watermark/snapshot policy |
| **Failure handling** | Covers retries/idempotency, coordinator recovery, unknown outcomes, and compensations |
| **Migration** | Enforces ownership/fencing and reconciliation on resharding—no lost or doubled rows |
| **Operations** | Measures p95/p99, skew, queues/locks, lag, network, and failure-injection tests |
| **Security** | Governs tenant isolation, retention, replicas/backups, and lineage |

**Conclusion:** choosing partitioning and distribution is not merely splitting data across machines. Sound designs preserve **efficient query paths** and **explicitly scoped business invariants**. Pruning, co-location, and partial aggregation cut read costs; single owners and local transactions cut coordination needs; 2PC buys atomic commit at the cost of locks, logging, and recovery complexity; Sagas handle multi-service workflows with intermediate states and compensations; outbox and idempotency protect message delivery. Only by deriving keys, grain, constraints, and transaction mechanisms from real requirements—and measuring fan-out, tail latency, and recoverability—can a system scale while keeping data explainable and verifiable.
