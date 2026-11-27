# Designing Schemas, Access Keys, and Indexes by Query Pattern

> **Chapter:** Database Architecture  
> **Module:** CLOUD_ARCHITECTURE  
> **Scope:** Designing cloud application architectures from business requirements through networking, compute, data, and deployment models; balancing reliability, security, scalability, cost, and operations using a Well-Architected mindset.

## Learning Objectives

After this lesson, you can:

1. Translate business flows and query patterns into measurable storage requirements instead of starting from table names or popular database types.
2. Design relational schemas, primary keys, foreign keys, constraints, and data types to protect correctness.
3. Analyze access patterns to choose suitable partition keys, sort keys, or access keys in NoSQL models.
4. Design indexes based on filter predicates, sort order, pagination, and read/write frequency while recognizing index trade-offs.
5. Use execution plans, statistics, and load testing to validate designs rather than optimizing by guesswork.
6. Assess the impact of schema/index changes on migrations, locking, availability, security, cost, and cloud operations.

## 1. Start from How the Application Accesses Data

Database design is not just naming tables or picking data types. A schema must serve real actions: creating a booking, checking available slots, viewing schedules by day, retrieving customer history, canceling transactions, and generating reports. Those actions determine how data is stored, which keys protect correctness, and which indexes prevent queries from scanning the entire dataset.

Suppose we are building a scheduling platform. Initial requirements:

- A resource (doctor/room/equipment) has time-based slots.
- An exclusive slot can be confirmed for at most one booking.
- Users view schedules by resource and date range.
- Users view their booking history sorted by most recent.
- Staff search bookings by status and creation time for processing.
- Daily/status summary reports must not slow down booking transactions.

These are **query patterns/access patterns**. Each pattern must specify: who calls it, filter conditions, result ordering, typical record count returned, frequency, target latency, and consistency level. Only from there should you choose schemas and indexes.

### 1.1. Listing Access Patterns

| ID | Access Flow | Primary Conditions | Ordering / Result | Priority |
|---|---|---|---|---|
| Q1 | Find slots for a resource in a time range | `resource_id`, `start_time` range | `start_time` ascending | High, interactive |
| Q2 | View a customer's bookings | `customer_id` | `created_at` descending, paginated | High |
| Q3 | Get booking details | `booking_id` | Single record | High |
| Q4 | Check if a slot is already taken | `resource_id` + `slot_start` | One result / none | Very high, contention control |
| Q5 | Staff view bookings by status | `status` + `created_at` range | `created_at` descending | Medium |
| Q6 | Cancel a booking | `booking_id` + actor/permission | Check state then update status | High |
| Q7 | Report booking counts per day | date, status, optionally by region | Aggregated | Can run in background |

This list must be supplemented with numbers: how many calls/second for Q1; whether the typical query range is one day or three months; how many slots a resource has; how many pages Q2 reads; and whether data must reflect writes immediately. **Access patterns are a design input**, not documentation written after the schema is finished.

### 1.2. Quantifying Load and Latency

For each query, record:

- **Read/write ratio:** proportion of reads to writes, including retries and background jobs.
- **Cardinality:** number of distinct values in a column/partition key; whether distribution is uniform or skewed.
- **Selectivity:** fraction of records matching the filter predicate.
- **Result size:** row count, payload size, and whether joins or aggregations are needed.
- **Concurrency:** how many requests run simultaneously; whether they contend on the same key.
- **Freshness/consistency:** how stale data may be; whether read-after-write must show changes immediately.
- **Growth/retention:** daily/monthly storage growth, retention and deletion policies.
- **Latency objective:** p95/p99 and measurement point; timeouts and per-layer latency budgets.

For example, a p95 target under 200 ms for Q2 is only meaningful once you define user region, cache type, returned row count, load level, and data age. Never equate single-query timing on a developer laptop with production SLOs.

## 2. Choosing Data Models and Entity Boundaries

### 2.1. Relational Model for Linked and Transactional Data

For booking, entities have clear relationships: `Customer`, `Resource`, `Slot`, and `Booking`. An initial relational model:

~~~mermaid
erDiagram
    CUSTOMER ||--o{ BOOKING : creates
    RESOURCE ||--o{ SLOT : offers
    RESOURCE ||--o{ BOOKING : receives
    SLOT ||--o| BOOKING : reserved_by
    CUSTOMER {
        uuid customer_id PK
        string email
        datetime created_at
    }
    RESOURCE {
        uuid resource_id PK
        string name
        string status
    }
    SLOT {
        uuid slot_id PK
        uuid resource_id FK
        datetime starts_at
        datetime ends_at
    }
    BOOKING {
        uuid booking_id PK
        uuid customer_id FK
        uuid resource_id FK
        uuid slot_id FK
        string status
        datetime created_at
    }
~~~

This is a simple conceptual model. The constraint of one booking per slot must be enforced using a unique constraint or an appropriate transaction/locking mechanism; diagram relationship notation does not enforce constraints on its own.

Key principles:

- Each entity has a stable identifier; primary keys do not depend on mutable attributes like email or name.
- Use foreign keys to express relationships and enforce referential integrity where business rules require it.
- Use `NOT NULL`, `CHECK`, `UNIQUE`, and appropriate data types to turn business invariants into database constraints.
- Distinguish authoritative data from derived data/caches/search projections.
- Define data lifecycles and owners; avoid tables written to by multiple teams without governance rules.

### 2.2. Normalization and Denormalization

**Normalization** reduces duplication and update anomalies. For example, customer contact details should not be copied into multiple source-of-truth records if screens need the same current address. However, some read-heavy queries may need snapshots or projections to serve transaction history, search, or analytics.

| Option | Benefits | Trade-offs |
|---|---|---|
| Normalize `Customer`, `Resource`, `Booking` separately | Consistent source updates, minimal duplication | Queries may require joins |
| Store name snapshot at booking time | Preserves historical meaning even if name changes | Data duplication; must define which fields are snapshots |
| Separate aggregated read model | Fast reads, tailored per screen | Needs sync/async updates, eventual consistency |
| Denormalize multiple copies | Reduces joins in some queries | Higher risk of update drift and write cost |

Do not denormalize simply because a join seems slow. Measure queries, indexes, data volume, and latency first. If storing a snapshot, name it clearly—such as `resource_name_at_booking`—rather than confusing it with the Resource's current name.

## 3. Key Design: Identity, Integrity, and Contention

### 3.1. Primary Keys

A primary key uniquely identifies each row and is never null. Common options:

- **Surrogate key:** system-generated UUID or auto-incrementing integer; stable even when business attributes change.
- **Natural key:** inherent, stable business attribute; must evaluate mutability, security, and uniqueness scope.
- **Composite key:** multiple columns forming an identifier, suitable when uniqueness belongs to a combination such as `(resource_id, starts_at)`.

| Key Type | Pros | Considerations |
|---|---|---|
| Auto-incrementing integer | Compact, good index locality in some systems | Can expose scale, create write hotspots in distributed setups; needs sequences |
| Random UUID | Distributed generation, obscures creation order | Wide, can fragment indexes; larger storage/cache footprint |
| Time-ordered UUID/ID | Can improve time-based locality | Ordering does not necessarily reflect transaction commit order |
| Composite key | Expresses business constraints | Wide keys propagate into foreign keys/indexes; hard to change if components change |

No single key type fits every workload. Choose based on scale, write distribution, distributed ID generation needs, index size, obfuscation needs, and integration constraints.

### 3.2. Foreign Keys and Unique Constraints

PostgreSQL-style DDL example:

~~~sql
CREATE TABLE resource (
    resource_id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE customer (
    customer_id UUID PRIMARY KEY,
    email TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_customer_email UNIQUE (email)
);

CREATE TABLE slot (
    slot_id UUID PRIMARY KEY,
    resource_id UUID NOT NULL REFERENCES resource(resource_id),
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT ck_slot_time CHECK (ends_at > starts_at),
    CONSTRAINT uq_resource_slot UNIQUE (resource_id, starts_at)
);

CREATE TABLE booking (
    booking_id UUID PRIMARY KEY,
    customer_id UUID NOT NULL REFERENCES customer(customer_id),
    resource_id UUID NOT NULL REFERENCES resource(resource_id),
    slot_id UUID NOT NULL REFERENCES slot(slot_id),
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

In this example, `UNIQUE (resource_id, starts_at)` guarantees a unique start timestamp per resource in the `slot` table; the foreign key `booking.slot_id` alone does not guarantee only one booking per slot. If only one active booking may hold a slot, PostgreSQL can use a partial unique index:

~~~sql
CREATE UNIQUE INDEX uq_booking_active_slot
ON booking (slot_id)
WHERE status IN ('PENDING', 'CONFIRMED');
~~~

This example is engine-specific. If you need to retain multiple booking/cancellation history rows, the model must define which statuses hold the slot, when it is released, and how concurrent transactions are handled.

### 3.3. Never Rely Solely on Application Checks to Prevent Contention

A common bug:

~~~text
Request A: SELECT slot -> sees available
Request B: SELECT slot -> sees available
Request A: INSERT booking
Request B: INSERT booking
~~~

Two requests can both observe an available state before either writes. To protect the invariant, the database needs constraints, transactions with appropriate isolation/locking, or conditional writes/optimistic concurrency at the authoritative write store.

A unique index will reject the second insert on the same occupied slot. The application should translate that constraint violation into a domain error such as `SLOT_UNAVAILABLE`, without leaking raw SQL details. If a reservation hold workflow exists, you can use a `PENDING` status with an expiration/lease and a release job, provided expiration transitions remain transactionally consistent.

**Idempotency keys** protect a single retried request intent; unique constraints protect business invariants across distinct competing intents. Both mechanisms complement each other and do not replace one another.

### 3.4. Optimistic Concurrency and Pessimistic Locking

| Mechanism | How It Works | Best Fit When |
|---|---|---|
| **Optimistic concurrency** | Reads version, writes conditionally if version is unchanged; otherwise conflicts | Contention is rare and long-held locks should be avoided |
| **Pessimistic locking** | Locks the row/resource inside a transaction to block concurrent updates | Contention is frequent and serialization is needed |
| **Unique/conditional constraints** | Database only accepts states that do not violate invariants | Uniqueness/conditional rules can be expressed at the write point |

Optimistic update example:

~~~sql
UPDATE booking
SET status = 'CANCELLED',
    version = version + 1
WHERE booking_id = :booking_id
  AND version = :expected_version
  AND status = 'CONFIRMED';
~~~

If the affected row count is 0, the state changed or the booking no longer meets the expected conditions; the application must re-read and decide how to proceed.

In PostgreSQL, `SELECT FOR UPDATE` can lock rows within a transaction. Pessimistic locking reduces concurrency if held too long; never call external APIs or wait on user input while a transaction holds locks. Establish lock ordering to reduce deadlocks, keep transactions short, and apply bounded retries for deadlocks or serialization failures when operations are safe to retry.

## 4. Designing Access Keys in NoSQL

### 4.1. Query-First and Partition Keys

In distributed key-value/document databases, querying capabilities can be constrained by partition keys, sort keys, and supported query APIs. Therefore, list access patterns before choosing partitions.

A good partition key typically:

- Distributes traffic and data evenly; avoids a single hot value.
- Enables scoped queries without scanning the entire collection/table.
- Keeps data that must be read together within a single appropriate query.
- Is stable and has cardinality/distribution aligned with projected growth.

A sort key typically supports ordered filtering or range queries within the same partition—such as creation timestamp, record type, or version. Composite keys can combine entity types and sort attributes, though you must consider encoding, range queries, and uniqueness.

### 4.2. Access Pattern Example with Partition/Sort Keys

In a hypothetical NoSQL table supporting a partition key and sort key:

| Access Pattern | PK | SK | Result |
|---|---|---|---|
| Get customer's bookings, newest first | `CUSTOMER#id` | `BOOKING#createdAt#bookingId` | Query by PK, sort descending |
| Get booking details | `BOOKING#id` | `META` | Query/get by exact key |
| Get resource slots by time | `RESOURCE#id` | `SLOT#startAt#slotId` | Query PK + sort key range |
| Get bookings by status | May need secondary index | `STATUS#status#createdAt#id` | Query via index if available |

This is an illustrative logical model, not a universal schema for all NoSQL engines. Review the query API, item size limits, partition capacity, and index semantics of the chosen service.

### 4.3. Hot Partitions and Key Distribution

If all bookings are written under partition key `STATUS#PENDING`, traffic can concentrate on a single partition. Increasing total provisioned capacity does not necessarily relieve a single hot key.

Potential solutions:

- Choose a key with higher cardinality and more even distribution, such as tenant/resource/customer depending on access patterns.
- Use write sharding with an explicit shard/bucket count, then aggregate on read.
- Avoid using the current timestamp alone as a partition key if all writers hit the same value simultaneously.
- Monitor throttling, consumed capacity, partition skew, or equivalent provider metrics.

Write sharding complicates aggregate queries because reads must fan out across shards; apply it only when metrics show a hot partition and you have a read fan-out/aggregation plan.

### 4.4. Secondary Indexes and Additional Queries

A global secondary index (GSI) or similar secondary index enables querying by an alternate key. For instance, the base table partitions by customer, while the operations team needs to look up bookings by status. You can create an index with partition key `status` and sort key `createdAt#bookingId`.

Trade-offs:

- Secondary indexes increase storage and write/update costs.
- Some systems update indexes asynchronously; queries may be eventually consistent.
- Low-cardinality keys like `status` can cause skewed distribution/hot partitions.
- One index may not satisfy every filter combination; additional indexes or a separate query service may be needed.
- Must plan index backfill behavior upon creation and its impact on throughput.

Never create indexes for every attribute "just in case we need it later." Document the access pattern, volume, frequency, and SLA each index serves.

## 5. Index Design in Relational Databases

### 5.1. Indexes Help Queries Avoid Reading Too Much Data

An index is an auxiliary structure allowing the database to locate matching rows without scanning the entire table in many cases. With common B-trees, values are maintained in sorted order to support equality, range, and ordering predicates. The engine may choose an index scan, index-only scan, bitmap scan, or sequential scan depending on its execution plan.

Q2 example: get a customer's latest bookings:

~~~sql
SELECT booking_id, status, created_at
FROM booking
WHERE customer_id = :customer_id
ORDER BY created_at DESC
LIMIT 20;
~~~

Suggested index:

~~~sql
CREATE INDEX ix_booking_customer_created
ON booking (customer_id, created_at DESC);
~~~

Column order matters: `customer_id` is filtered by equality first, and `created_at` supports ordering within that customer's scope. The index can eliminate sorting and read fewer rows, though you must inspect the actual plan.

### 5.2. Leftmost Prefix and Composite Index Column Order

With a B-tree composite index `(customer_id, status, created_at)`, queries typically benefit when filtering by `customer_id` or `customer_id` plus `status`, then evaluating `created_at` within that subset. A query filtering only on `status` may not use this index effectively depending on the engine and statistics, since the key order begins with `customer_id`.

| Query | Potentially Suitable Index |
|---|---|
| `WHERE customer_id = ?` | `(customer_id)` or composite starting with `customer_id` |
| `WHERE customer_id = ? AND status = ?` | `(customer_id, status)` |
| `WHERE customer_id = ? ORDER BY created_at DESC` | `(customer_id, created_at DESC)` |
| `WHERE status = ? ORDER BY created_at DESC` | `(status, created_at DESC)` if workload justifies it |
| `WHERE created_at >= ?` across whole table | Index starting with `created_at` or suitable partitioning/strategy |

There is no absolute rule that "highest-selectivity column always goes first." You must weigh equality predicates, range predicates, sort order, actually queried prefixes, covering potential, index size, and overall workload. A composite index tuned for one query can degrade another.

### 5.3. Ranges, Sorting, and Pagination

For Q1 finding slots:

~~~sql
SELECT slot_id, starts_at, ends_at
FROM slot
WHERE resource_id = :resource_id
  AND starts_at >= :from_time
  AND starts_at < :to_time
ORDER BY starts_at ASC
LIMIT 100;
~~~

Index:

~~~sql
CREATE INDEX ix_slot_resource_start
ON slot (resource_id, starts_at);
~~~

Equality on `resource_id` precedes the range on `starts_at`. Half-open time intervals `[from, to)` prevent boundary duplicates when paginating or splitting days; timezones and timestamp conventions must stay consistent.

**OFFSET pagination**

~~~sql
SELECT booking_id, status, created_at
FROM booking
WHERE customer_id = :customer_id
ORDER BY created_at DESC, booking_id DESC
LIMIT 20 OFFSET 10000;
~~~

Large offsets incur the cost of reading and discarding many rows; newly inserted rows between page requests can also cause items to shift or duplicate. **Keyset/seek pagination** uses the values from the last row of the previous page:

~~~sql
SELECT booking_id, status, created_at
FROM booking
WHERE customer_id = :customer_id
  AND (created_at, booking_id) < (:last_created_at, :last_booking_id)
ORDER BY created_at DESC, booking_id DESC
LIMIT 20;
~~~

Suitable index:

~~~sql
CREATE INDEX ix_booking_customer_created_id
ON booking (customer_id, created_at DESC, booking_id DESC);
~~~

Keyset pagination requires a stable sort key and sufficient tie-breakers; `created_at` alone can collide. If data changes during pagination, decide the desired snapshot/consistency behavior.

### 5.4. Partial, Covering, and Expression Indexes

Some engines support specialized indexes:

~~~sql
CREATE UNIQUE INDEX uq_booking_active_slot
ON booking (slot_id)
WHERE status IN ('PENDING', 'CONFIRMED');

CREATE INDEX ix_customer_email_lower
ON customer (LOWER(email));
~~~

Partial indexes reduce entry count when only a subset of rows matters; expression indexes support matching predicates. A **covering index** (such as PostgreSQL `INCLUDE`) stores extra columns to return results without heap fetches under certain conditions, at the cost of increased storage and write overhead:

~~~sql
CREATE INDEX ix_booking_customer_created_cover
ON booking (customer_id, created_at DESC)
INCLUDE (booking_id, status);
~~~

Avoid redundant indexes when an equivalent or unique index already covers the query. Exact DDL and benefits depend on the database/version, configuration, statistics, and update frequency.

### 5.5. Selectivity and Why Indexes Are Not Always Used

An index pays off when it substantially reduces the volume of data read. If a query returns 80% of a table, a sequential scan can be cheaper than reading the index and performing random row lookups. An index on a boolean or low-cardinality status column has low selectivity on its own, yet can still be useful when combined with time, partitions, or a partial predicate.

The query planner considers:

- Row counts and page counts of the table/index.
- Data distribution and whether statistics are up to date.
- Actual predicate selectivity and correlations across columns.
- Expected returned rows and required sorts/hashes/joins.
- Cache hits, I/O, parallelism, and random vs. sequential access costs.
- Parameter values; a good plan for a large tenant may be poor for a small tenant.

Never force the planner to use an index with hints before understanding the plan. Check the query, data types/casts, and statistics first. Hints may be necessary on certain platforms, but they add coupling to specific versions and configurations.

## 6. Reading Execution Plans and Measuring Performance

### 6.1. EXPLAIN Is Evidence, Not Guesswork

In PostgreSQL, you can run:

~~~sql
EXPLAIN
SELECT booking_id, status, created_at
FROM booking
WHERE customer_id = '00000000-0000-0000-0000-000000000042'
ORDER BY created_at DESC
LIMIT 20;
~~~

In a safe environment for a query without side effects, `EXPLAIN (ANALYZE, BUFFERS)` reports actual timings and row counts:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT booking_id, status, created_at
FROM booking
WHERE customer_id = '00000000-0000-0000-0000-000000000042'
ORDER BY created_at DESC
LIMIT 20;
~~~

`ANALYZE` **actually executes the query**; for `UPDATE`/`DELETE` or functions with side effects, run only inside a controlled transaction and roll back appropriately, or inspect the non-executing plan. Key plan elements to examine:

| Plan Element | What to Check |
|---|---|
| Seq Scan / Index Scan / Index Only Scan | Is a large table scanned? Is the index used? Are heap fetches high? |
| Estimated vs actual rows | Are row estimates badly skewed? |
| Rows Removed by Filter | Are many rows read only to be discarded? |
| Sort / Hash / Aggregate | Are there large sorts/hashes spilling to disk or starved of memory? |
| Nested Loop / Hash Join / Merge Join | Does the join strategy fit table sizes and cardinality? |
| Buffers hit/read/temp | Reading from cache, storage, or writing temp files? |
| Planning/Execution time | Planner vs. execution time; measure repeatedly under load |

Never judge from a single run. Warm caches, concurrent workloads, vacuum/analyze runs, parameter values, and storage latency can change results markedly.

### 6.2. Before and After Adding an Index

Suppose Q2 returns 20 bookings from a table of tens of millions of rows:

~~~text
Before index:
  Full-table Seq Scan
  Filter customer_id
  Sort created_at DESC
  Limit 20

After index when planner sees benefit:
  Index Scan by customer_id, created_at DESC
  Limit 20
~~~

This is a conceptual illustration, not actual plan output. After creating an index, check actual rows, buffers, p95/p99 latency under concurrency, write throughput, and index overhead. If performance does not improve, re-examine selectivity, statistics, returned row counts, and caching before adding another index.

### 6.3. Measuring from the Application Perspective

Database query latency is not equal to API latency. Requests also traverse the network, connection pool, serialization, application logic, and potentially multiple queries. Collect:

- p50/p95/p99 for critical queries and the endpoints invoking them.
- Timeout, deadlock, serialization failure, and retry rates.
- Active/idle/waiting connection counts and connection acquisition time.
- Query throughput, rows read/returned, lock waits, and replication lag.
- CPU, memory, IOPS, storage throughput, cache hit ratios, and temp spills.
- Cost per query/workload where platform-provided or allocatable.

Mask or hash PII values in query logs; limit sampling and retention so telemetry itself does not create data exposure or cost risks.

## 7. Indexes, Write Costs, and Cloud Operations

### 7.1. Every Index Is a Structure That Must Be Maintained

On inserts/updates/deletes, the database must update affected indexes. Many or wide indexes can:

- Increase storage and backup size.
- Increase write amplification, CPU, I/O, and transaction duration.
- Slow down migrations and replica catch-up.
- Increase lock/resource contention during creation or rebuilds depending on engine mechanics.
- Increase managed database costs and recovery time.

| Index | Query Served | Importance | Justification to Keep |
|---|---|---|---|
| `uq_booking_active_slot` | Prevent double-booking a slot | Very high, correctness | Invariant and concurrency tests |
| `ix_booking_customer_created_id` | Customer booking history | High | Q2 p95 and execution plan |
| `ix_slot_resource_start` | Slot schedule by resource | High | Q1 plan, latency |
| `ix_booking_status_created` | Admin lookup by status | As needed | Query usage vs. write cost |

Indexes without proven queries, invariant protection, or meaningful usage should be candidates for removal. Dropping an index also requires workload verification; an infrequently used index might still be vital for an operational job.

### 7.2. Building Indexes Online/Concurrently

In production, building an index can acquire locks or spike I/O depending on the engine. PostgreSQL offers `CREATE INDEX CONCURRENTLY` to reduce write blocking compared to a regular build in many cases, though it has limitations and overhead; it cannot run inside a standard transaction block and can leave an invalid index if it fails. Other engines have different online index build options.

Before running a migration:

1. Check free storage, IOPS, CPU, replica lag, and baseline load.
2. Verify what locks the command takes, whether it runs concurrently with writes, and whether it runs in a transaction.
3. Test on staging with production-like volume and data distribution.
4. Set timeouts, schedules, owners, progress monitoring, and a failure recovery plan.
5. Verify index validity, query plans, and write latency once complete.

PostgreSQL example:

~~~sql
CREATE INDEX CONCURRENTLY ix_booking_customer_created
ON booking (customer_id, created_at DESC);
~~~

This command is specific to PostgreSQL; consult documentation for your exact version before running. "Online" does not mean zero resource consumption or zero latency impact.

### 7.3. Schema Evolution: Expand, Migrate, Contract

Schema changes while multiple application versions run concurrently must maintain compatibility:

1. **Expand:** add new columns/tables/indexes, usually nullable or with safe defaults; old code continues working.
2. **Deploy compatible code:** new code reads/writes the new format while handling legacy data.
3. **Backfill/migrate:** migrate data in idempotent, checkpointed batches while tracking progress.
4. **Switch:** switch reads to the new structure after verifying completeness.
5. **Contract:** drop legacy structures once no old code/consumers remain and the rollback window has closed.

Avoid adding `NOT NULL` columns or altering large keys in ways that trigger uncontrolled full-table scans or long locks. For columns requiring backfill, batch the work, rate-limit updates, and watch replication lag. Rolling back application code does not automatically undo migrated data.

## 8. Securing Schemas, Keys, and Queries

### 8.1. Role-Based Least Privilege

- Runtime accounts hold only the permissions needed for their operations; never use superuser/admin accounts in production connection strings.
- Read-only/reporting workloads should use read-only roles or dedicated replicas.
- Separate migration accounts hold DDL privileges and run only inside protected pipelines.
- Tenant/record-level access checks must be enforced at the data or service layer via trusted mechanisms; never trust a client-supplied `customer_id`.
- Use secret managers/workload identities wherever possible, rotate credentials, and encrypt connections and storage.

An index is not a security boundary. An index containing email addresses, phone numbers, or sensitive fields falls under the same data classification and must be protected across IAM, backups, logs, exports, and retention.

### 8.2. Preventing SQL Injection and Unsafe Dynamic Queries

Always bind parameters:

~~~sql
SELECT booking_id, status
FROM booking
WHERE customer_id = :authenticated_customer_id
  AND created_at >= :from_time;
~~~

Never concatenate raw input into SQL strings. Table/column names or sort directions generally cannot be bound as values; if dynamic queries are needed, map inputs strictly from a fixed allowlist. Authorize based on verified identity rather than trusting a client-supplied `customer_id` as proof of ownership.

### 8.3. Data Types, Timezones, and Null Semantics

Choosing the right types prevents subtle bugs:

- Store absolute timestamps using timezone-aware/UTC types appropriate to the engine; format into user timezones at display time. Avoid ambiguous local timestamps when cross-region comparisons are needed.
- Store money using `decimal`/`numeric` or the smallest integer currency unit per currency rules; avoid floating-point types for exact financial calculations.
- Define explicit status values and transition rules; consider enums/lookup tables and future status additions.
- In SQL semantics, `NULL` means unknown/absent—not an empty string or `0`.
- Column lengths, collations, normalization, and email/name uniqueness must match business and linguistic rules.

## 9. Partitioning, Sharding, and Large-Scale Storage Strategies

When tables grow very large, indexes are not the only tool. Partitioning splits a table into segments by range/list/hash within a logical database or cluster depending on the platform, aiding partition pruning, retention, and administration.

### 9.1. Time-Based Partitioning

For example, a daily-growing audit/event table can be partitioned by month:

~~~sql
CREATE TABLE booking_audit (
    audit_id UUID NOT NULL,
    booking_id UUID NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    action TEXT NOT NULL
) PARTITION BY RANGE (occurred_at);

CREATE TABLE booking_audit_2026_11
PARTITION OF booking_audit
FOR VALUES FROM ('2026-11-01 00:00:00+00')
TO ('2026-12-01 00:00:00+00');
~~~

Partition pruning helps when queries include a predicate on `occurred_at`; queries omitting the partition key may still scan multiple partitions. Unique/primary keys on partitioned tables may need to include the partition key depending on the engine. Understand DDL and foreign-key constraints for your exact database engine.

Partitioning makes detaching/dropping old partitions for retention much faster than row-by-row deletes. However, too many partitions raise catalog/planning overhead, while too few increase vacuum/maintenance and data-management cost. Base partition cadence and count on volume and retention.

### 9.2. Partitioning Is Not Sharding

| Mechanism | Scope | Goal | Complexity |
|---|---|---|---|
| Table partitioning | Within a database/cluster per engine support | Pruning, retention, managing large tables | Queries must align with partition key |
| Sharding | Splits data across multiple nodes/databases | Scale storage/throughput beyond one node | Routing, distributed transactions, rebalancing, backup/restore |
| Read replicas | Read-serving copies | Increase read capacity, isolate workloads | Replication lag, consistency, and failover |
| Archive/object storage | Cold data moved to cheaper tier | Lower hot-storage cost | Slower retrieval, different query path, lifecycle rules |

Shard only after proving a single-node bottleneck after optimizing schemas, queries, indexes, and exhausting service-level scaling options. Choose a shard key with strong cardinality/distribution that aligns with critical access patterns and minimizes cross-shard queries/transactions.

## 10. Design Workflow from Access Patterns to Schemas/Indexes

1. **Gather workload:** list queries/commands, callers, predicates, sorts, result sizes, read/write ratios, concurrency, and SLOs.
2. **Define invariants:** uniqueness, referential integrity, valid state transitions, transaction boundaries, retention, and security.
3. **Choose data model:** relational/document/key-value/wide-column based on relationships, transactions, queries, and engine limits.
4. **Choose primary/partition keys:** align with identity, locality, load distribution, and scaling needs.
5. **Define minimal indexes:** map each index to one or more queries; prioritize equality/range/ordering and uniqueness.
6. **Seed representative data:** realistic size, distribution, skew, nulls, historical data, and large tenants—not a handful of sample rows.
7. **Measure execution plans and load:** actual rows, buffers, p95/p99 latency, throughput, locks, CPU/I/O, replication lag, and cost.
8. **Test migrations:** verify locking, backfills, online index builds, rollbacks, and version compatibility.
9. **Operate:** establish dashboards, alerts, query/index owners, documented rationale, and review triggers when workloads shift.

### 10.1. Query ↔ Index Matrix

| Query ID | Predicate | Sort/Range | Proposed Index/Key | Verification |
|---|---|---|---|---|
| Q1 slots by resource/time | `resource_id = ?` | `starts_at` range, ASC | `(resource_id, starts_at)` | `EXPLAIN`, p95 across date windows |
| Q2 customer bookings | `customer_id = ?` | `created_at DESC, booking_id DESC` | `(customer_id, created_at DESC, booking_id DESC)` | Keyset pagination, actual rows |
| Q3 booking details | `booking_id = ?` | None | PK `booking_id` | Lookup latency |
| Q4 claim slot | `slot_id = ?`, active status | Unique | Unique/partial index per invariant | Concurrency tests |
| Q5 admin by status | `status = ?` | `created_at DESC` | `(status, created_at DESC)` if load warrants | Query usage and write cost |
| Q7 daily summary | Date range, group by status | Aggregate | Partition/summary/read model per volume | Batch latency and OLTP impact |

Multiple indexes can support a query, but total index count must be weighed against write cost. If Q5 is rarely run, a bounded scan or running on a read replica/warehouse may beat adding an index to the transactional table.

### 10.2. Documenting Rationale When Adding an Index

~~~text
Index: ix_booking_customer_created_id
Query served: Q2 - customer booking history
Predicate: customer_id = ?
Order: created_at DESC, booking_id DESC
Target: p95 under 200 ms at defined load
Observed benefit: eliminates sort and reduces rows read per customer
Cost: increases storage and index maintenance on INSERT
Evaluation: actual plan + before/after load test + write latency
Owner: Booking data owner
Revisit when: Q2 traffic, schema, or retention changes
~~~

Documenting rationale helps operators understand why each index exists and avoids accidental deletions or duplicate indexes.

## 11. Common Design Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Designing schema before listing queries | Repeated index patching, mismatched queries | Document access patterns and SLOs first |
| Relying solely on app-level availability checks | Race conditions and double bookings | Enforce constraints/transactions at the authoritative DB |
| Using email or mutable fields as primary key | Profile changes cascade into massive reference updates | Use surrogate or stable keys |
| Wrong column order in composite index | Query cannot use a helpful prefix or still sorts | Align with actual equality/range/sort predicates |
| Indexing every column "to make it fast" | Slow writes, bloated storage/backups | Create indexes only with query/invariant evidence |
| Indexing a standalone boolean column | Low selectivity; planner may ignore it | Combine with selective predicates or partial indexes |
| Very deep OFFSET pagination | Reads/skips many rows, unstable pages | Keyset pagination with tie-breakers |
| Partition key with hot values | Throttling/latency despite spare total capacity | Pick evenly distributed keys; shard only when measured |
| Denormalizing without sync updates | Copies drift out of sync | Clear source of truth, outbox/reconciliation |
| Using replicas to check latest-state invariants | Stale reads cause wrong decisions | Read with appropriate consistency from primary |
| Building large indexes during peak hours | Spikes in CPU/I/O/locks and replica lag | Plan online/concurrent builds, monitor, and test first |
| Failing to update statistics or read plans | Planner picks poor execution plans | Run analyze/statistics and check actual rows |

## 12. Lab: Designing Data and Indexes for a Scheduling Service

**Scenario:** The service manages `Customer`, `Resource`, `Slot`, and `Booking`. Slot-schedule reads are roughly 15x higher than booking writes; during peak hours many customers contend for the same slot. Staff look up bookings by status/creation date; customers paginate through their history. Data grows steadily each month. A target lookup API p95 under 200 ms at design load is a planning assumption, not a verified guarantee.

Complete these deliverables:

1. **Access patterns:** list at least 6 queries, callers, predicates, sorts, row counts, frequencies, and consistency needs.
2. **ERD and DDL:** define primary keys, foreign keys, `NOT NULL`, `CHECK`, and unique/invariant rules ensuring one slot is booked once.
3. **Concurrency:** trace two concurrent requests for the same slot; prove constraints/transactions block double bookings; distinguish idempotency keys from unique keys.
4. **Index matrix:** design indexes for resource/time schedules, customer history, booking details, and admin status lookups; justify column order and write costs.
5. **Pagination:** write a keyset query for booking history ordered by `created_at` and `booking_id`.
6. **NoSQL alternative:** if using a key-value/document DB, propose partition/sort keys and secondary indexes; identify hot-partition risks.
7. **Performance:** generate test data with realistic distribution/skew; run `EXPLAIN/ANALYZE` or equivalent; record actual rows, latency, buffers, query throughput, and write cost.
8. **Schema evolution:** add a field or index while multiple API versions run concurrently; describe expand/backfill/switch/contract and rollback.
9. **Well-Architected review:** document risks and verification checks across reliability, security, performance efficiency, cost, operations, and sustainability.

Sample design table:

| Query | Access Pattern | Correctness Constraint | Index/Key | Verification Metric |
|---|---|---|---|---|
| Slot schedule by resource | resource equality + time range | Prevent duplicate slots | `(resource_id, starts_at)` | p95 and rows examined |
| Customer history | customer equality + ordering | Read only authorized customer | `(customer_id, created_at, booking_id)` | p95 on first and deep pages |
| Book a slot | Lookup/claim slot | Unique active booking | Unique/conditional write | Concurrency tests |
| Admin status lookup | status + time | Authorized roles only | Workload-driven index if needed | Latency, write overhead |

**Completion criteria:** A reviewer can see which invariant each key protects, which query each index supports, why column orders/partition keys were chosen, how measurements prove the benefit, and what remaining costs/limits exist.

## 13. Well-Architected Evaluation

| Pillar | Questions for Schema, Key, and Index Design | Evidence |
|---|---|---|
| **Operational Excellence** | Are query/index catalogs, owners, migration plans, and runbooks in place? | ADRs, query dashboards, index rationales, migration rehearsals |
| **Security** | Are least privilege, tenant isolation, parameterized queries, and PII protection enforced? | IAM/role tests, access tests, audits, secret handling |
| **Reliability** | Do constraints and transactions protect data under concurrency/failures? Can it be restored? | Race tests, failover/restore tests, consistency checks |
| **Performance Efficiency** | Do critical queries hit target plans, cardinality, and latency? | `EXPLAIN ANALYZE`, load tests, p95/p99, rows examined |
| **Cost Optimization** | Do indexes/replicas/partitions justify their storage, I/O, and ops costs? | Storage, write latency, IOPS, cost allocation |
| **Sustainability** | Are redundant reads/scans, unused indexes/partitions, and excessive log retention avoided? | Query efficiency, lifecycle/retention, utilization |

No index is good in isolation from its workload. An index that speeds up one query can slow down inserts/updates; partitioning that simplifies retention can complicate global queries. Optimize for the **overall workload and system goals**, not one query at any cost.

## 14. Key Takeaways

- **Access patterns precede schemas:** know who reads/writes which data, under what predicates and ordering, and at what volume and SLOs.
- **Keys protect correctness:** primary keys identify; foreign keys protect references; unique/check constraints and transactions enforce invariants.
- **Indexes serve real queries:** equality, range, ordering, and pagination determine structure; every index carries write/storage/backup costs.
- **NoSQL requires query-driven partition/sort keys:** distribute evenly, avoid hot partitions, and account for secondary indexes/eventual consistency.
- **Execution plans and load tests are proof:** compare estimated vs. actual rows, buffers, latency, locks, throughput, and cost.
- **Schemas are operational assets:** compatible migrations, backup/restore, least privilege, retention, and ownership must be designed together.

Designing schemas, access keys, and indexes is the process of turning **business behavior** into **verifiable data storage and retrieval**. A strong database is not the one with the most indexes or the most complex schema—it is the one that keeps data accurate, serves critical queries within agreed latency/load/cost limits, and evolves safely as the application grows.
