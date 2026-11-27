# Indexes, Unique Keys, and Constraints on Partitioned Tables in PostgreSQL

## 1. The Problem: Partitioning a Large Table While Preserving Correctness

An event tracking system has hundreds of millions of rows. To cut maintenance costs and speed up date-based queries, the engineering team splits the table by month:

```text
events (partitioned parent table)
  |
  +-- events_2026_01  [2026-01-01, 2026-02-01)
  |
  +-- events_2026_02  [2026-02-01, 2026-03-01)
  |
  +-- events_2026_03  [2026-03-01, 2026-04-01)
  |
  +-- ...
```

The first question is: if before partitioning the table had:

```sql
PRIMARY KEY (event_id)
```

can we keep that same `event_id` primary key on the parent after switching to **daily/monthly RANGE partitioning**?

Under standard PostgreSQL **declarative partitioning**, you cannot create `PRIMARY KEY (event_id)` on a parent partitioned by `event_date`, because any unique/primary key on the parent must include **all partition key columns**. PostgreSQL maintains physical indexes per partition rather than one single B-tree spanning all partitions.

A valid design is:

```sql
PRIMARY KEY (event_date, event_id)
```

yet this enforces a **different rule**:

- It ensures each `(event_date, event_id)` pair appears at most once.
- It does **not** prevent `event_id` from repeating across **two different days or months**.

Consequently, partitioning is not purely a performance decision. It impacts **primary keys, foreign keys, UPSERTs, ID modeling, uniqueness invariants, and write protocols**.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish between a **partitioned table**, physical partitions, and parent-level indexes.
2. Understand how indexes declared on the parent map to physical indexes on partitions.
3. State the exact requirements for `UNIQUE` and `PRIMARY KEY` on partitioned tables.
4. Explain why **per-partition uniqueness** differs from **dataset-wide uniqueness**.
5. Design `(partition_key, id)` keys, multi-column natural keys, and matching foreign keys.
6. Recognize restrictions involving expression partition keys, multi-level partitioning, and nullable columns.
7. Create shared parent indexes as well as specialized local indexes on individual partitions.
8. Explain why direct `CREATE INDEX CONCURRENTLY` on a partitioned parent is restricted, and how to build per partition instead.
9. Use `ALTER INDEX ... ATTACH PARTITION` to link child indexes to a parent index.
10. Distinguish **partition pruning** from **index scans**, and see why ID-only lookups may probe many partitions.
11. Understand impacts on `FOREIGN KEY`, `ON CONFLICT`, `CHECK`, and `NOT NULL`.
12. Choose an architecture when business rules **mandate globally unique IDs**.
13. Inspect partition/index structures via system catalogs and `EXPLAIN`.
14. Plan operations, partition expansion, maintenance, and safe constraint verification.

---

## 2. Declarative Partitioning in PostgreSQL

A table declared as:

```sql
CREATE TABLE ... (
    ...
) PARTITION BY RANGE (event_date);
```

is a **partitioned table**. It represents a logical relation with one shared table name, while the parent itself **contains no data rows the way a regular heap table does**.

Rows are routed into specific partitions by their partition key value.

Example:

```text
INSERT event_date = 2026-01-12
    -> events_2026_01

INSERT event_date = 2026-02-18
    -> events_2026_02
```

PostgreSQL supports three primary strategies:

| Type | Examples | Best Fit |
|---|---|---|
| `RANGE` | Dates/months, ID ranges | Interval queries and time-based purging |
| `LIST` | Regions, data categories | Clear enumerated categories |
| `HASH` | Hash of tenant ID, event ID | Even load spreading on well-distributed keys |

### 2.1. A Partition Is a Real Data Table

Each partition is an actual table with its own physical storage:

```text
events (partitioned parent: logical relation)
    |
    +-- events_2026_01 (physical table + physical index)
    |
    +-- events_2026_02 (physical table + physical index)
```

Each partition has:

- Its own heap data pages.
- Its own physical indexes.
- Its own statistics and maintenance metadata.
- Independent storage parameters, tablespace, or maintenance schedules.
- A partition range constraint managed by PostgreSQL.

Do not picture one big heap with small indexes acting like page bookmarks. Partitioning fundamentally alters the relation hierarchy and access paths.

### 2.2. INSERT Routing and SELECT Pruning

- **INSERT routing:** PostgreSQL picks the matching partition for each written row.
- **Partition pruning:** PostgreSQL skips partitions proven unable to match query predicates.
- **Index access:** once target partitions are selected, PostgreSQL picks Seq Scan, Index Scan, Bitmap Scan, or another plan inside each partition.

These three steps are **distinct**. Having an index never causes partition pruning if the query omits compatible predicates on the partition key.

## 3. A Parent Index Is Not a Global B-Tree

When creating an index on the parent:

```sql
CREATE INDEX idx_events_tenant_date
ON part298.events(tenant_id, event_date);
```

PostgreSQL creates a **partitioned index definition at the parent level** and **corresponding physical indexes on each partition**, when run in standard form and operations succeed.

Diagram:

```text
part298.events
  |
  +-- idx_events_tenant_date (partitioned index, logical)
          |
          +-- physical index on events_2026_01
          |
          +-- physical index on events_2026_02
          |
          +-- physical index on events_2026_03
```

**There is no single global B-tree** where looking up `tenant_id` once jumps across all months as in an unpartitioned index.

When a query spans multiple partitions, the planner/executor probes the indexes of **multiple partitions** and combines the results.

### 3.1. What Purpose Does the Parent Index Serve?

It acts as the logical definition and management link for child partition indexes. It enables:

- Declaring a consistent indexing policy across partitions.
- Automatically creating/attaching matching indexes on partitions.
- Backing primary key or `UNIQUE` constraints when eligible.
- Automatically applying parent index definitions to newly added partitions.

It does **not** store every partition's keys inside a single shared physical tree.

### 3.2. Child Indexes Can Exist Independently

An individual partition can also have its own local index without a parent-level definition—for instance, an index tailored to one month or a specialized reporting campaign.

That is a **local index**, and its scope never extends to become a parent-wide constraint.

## 4. Preparing the Practice Schema

The SQL statements below are for a **learning database**; never run them against production tables or schemas holding critical data.

### 4.1. Create the Schema

```sql
CREATE SCHEMA IF NOT EXISTS part298;
```

### 4.2. Create a Date-Partitioned Events Table

```sql
CREATE TABLE part298.events (
    event_date date NOT NULL,
    event_id bigint NOT NULL,
    tenant_id integer NOT NULL,
    event_type text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (event_date, event_id)
) PARTITION BY RANGE (event_date);
```

Notice right from the DDL:

- The partition key is `event_date`.
- The primary key contains **both `event_date` and `event_id`**.
- The primary key enforces `NOT NULL` on both columns and uniqueness of the **pair**.
- It does **not** enforce global `event_id` uniqueness.

### 4.3. Create Monthly Partitions

```sql
CREATE TABLE part298.events_2026_01
PARTITION OF part298.events
FOR VALUES FROM (DATE '2026-01-01')
           TO   (DATE '2026-02-01');

CREATE TABLE part298.events_2026_02
PARTITION OF part298.events
FOR VALUES FROM (DATE '2026-02-01')
           TO   (DATE '2026-03-01');

CREATE TABLE part298.events_2026_03
PARTITION OF part298.events
FOR VALUES FROM (DATE '2026-03-01')
           TO   (DATE '2026-04-01');
```

In `RANGE`, the lower bound is **inclusive** and the upper bound is **exclusive**.

Hence:

```text
2026-01-31 belongs to events_2026_01
2026-02-01 belongs to events_2026_02
2026-03-01 belongs to events_2026_03
```

### 4.4. Insert Data Through the Parent Table

```sql
INSERT INTO part298.events(
    event_date, event_id, tenant_id, event_type, payload
)
VALUES
    (DATE '2026-01-10', 1001, 7, 'LOGIN',   '{"ok":true}'),
    (DATE '2026-01-10', 1002, 7, 'PAYMENT', '{"amount":150}'),
    (DATE '2026-02-10', 1003, 7, 'LOGIN',   '{"ok":true}'),
    (DATE '2026-02-20', 1004, 8, 'PAYMENT', '{"amount":300}'),
    (DATE '2026-03-03', 1005, 8, 'LOGIN',   '{"ok":true}');
```

PostgreSQL routes each row to the matching monthly partition.

### 4.5. Inspect Which Partition Holds Each Row

```sql
SELECT
    tableoid::regclass AS physical_partition,
    event_date,
    event_id,
    tenant_id,
    event_type
FROM part298.events
ORDER BY event_date, event_id;
```

System column `tableoid` reveals the physical partition storing each row. In the lab, January rows sit in `events_2026_01`, February in `events_2026_02`, and March in `events_2026_03`.

### 4.6. What If We Insert a Date Without a Partition?

Example:

```sql
-- Run separately to observe the expected error:
INSERT INTO part298.events(
    event_date, event_id, tenant_id, event_type
)
VALUES (DATE '2026-04-01', 1006, 7, 'LOGIN');
```

In the current fixture there is **no April partition and no `DEFAULT` partition**. The statement is expected to fail with no partition found for row.

Having or omitting a default partition affects whether out-of-range rows are accepted; it **does not alter** parent `UNIQUE` key requirements.

## 5. Which Indexes Did PostgreSQL Create for PRIMARY KEY?

After creating a parent with `PRIMARY KEY (event_date,event_id)`, PostgreSQL creates matching unique indexes on each partition to enforce the constraint.

Inspect:

```sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'part298'
  AND tablename IN (
      'events',
      'events_2026_01',
      'events_2026_02',
      'events_2026_03'
  )
ORDER BY tablename, indexname;
```

You will see primary-key index definitions on the parent and partitions, with exact names varying by PostgreSQL's auto-naming and DDL history.

### 5.1. PRIMARY KEY Is Not Just a Label

When declaring a primary key on a partitioned parent:

- PostgreSQL registers the constraint at the parent level.
- Each partition maintains its own matching constraint/index.
- The partition key guarantees **two rows with the full identical primary key** can never validly reside in different partitions.
- The local child index detects duplicate key pairs within the target partition.

Thus, table-wide uniqueness rests on **partition routing by the partition key combined with per-partition unique indexes**.

## 6. Core Rule: UNIQUE/PRIMARY KEY Must Include the Partition Key

In PostgreSQL declarative partitioning, when creating a `PRIMARY KEY` or `UNIQUE` constraint on a **partitioned parent**, the declared columns must **include all partition key columns**.

If partitioned by:

```sql
PARTITION BY RANGE (event_date)
```

structures like the following can be valid:

```sql
PRIMARY KEY (event_date, event_id)

UNIQUE (event_date, tenant_id, event_id)

UNIQUE (event_date, event_type, event_id)
```

assuming other constraints, column types, and partitioning rules are also met.

However:

```sql
UNIQUE (event_id)
```

**cannot be declared as a unique constraint on a parent** partitioned solely by `event_date`.

### 6.1. Trying to Create an ID-Only Unique Index on the Parent

On our lab table:

```sql
-- Run separately to observe the expected error:
CREATE UNIQUE INDEX idx_events_global_event_id
ON part298.events(event_id);
```

PostgreSQL rejects this unique index on the partitioned parent because `event_date`, the partition key column, is missing from the unique key.

The message will read along the lines of:

```text
unique constraint on partitioned table must include
all partitioning columns
```

Exact wording varies by version. This is an **architectural limitation**, not a typo in `CREATE UNIQUE INDEX`.

### 6.2. Trying to Declare an ID-Only Primary Key on Another Parent Table

For a new table:

```sql
CREATE TABLE part298.events_bad_design (
    event_date date NOT NULL,
    event_id bigint NOT NULL,
    PRIMARY KEY (event_id)
) PARTITION BY RANGE (event_date);
```

This DDL is rejected right at table creation. You must redesign the key model or partition key—there is no option telling PostgreSQL to "scan every partition on every insert."

## 7. Why Per-Partition UNIQUE Is Not Enough

Consider two rows:

```text
(event_date=2026-01-10, event_id=2000)
(event_date=2026-02-10, event_id=2000)
```

Both share `event_id = 2000`, yet route to **two different partitions**.

Suppose each partition has:

```sql
CREATE UNIQUE INDEX ... ON partition(event_id);
```

January's index sees ID 2000 once. February's index also sees ID 2000 once. Neither index sees the whole table to catch **cross-month duplicates**.

Diagram:

```text
events_2026_01
  UNIQUE(event_id)
       2000 -> valid

events_2026_02
  UNIQUE(event_id)
       2000 -> valid

Logically across parent:
       event_id=2000 appears twice
       with no global unique index catching it
```

### 7.1. Testing a Valid Composite PRIMARY KEY

In the fixture, we can insert two rows with the same `event_id` on different dates:

```sql
INSERT INTO part298.events(
    event_date, event_id, tenant_id, event_type
)
VALUES
    (DATE '2026-01-12', 9000, 7, 'LOGIN'),
    (DATE '2026-02-12', 9000, 7, 'LOGIN');
```

**Both rows are valid** under `PRIMARY KEY (event_date,event_id)` because the key pairs differ.

Verify:

```sql
SELECT event_id, COUNT(*) AS occurrences
FROM part298.events
WHERE event_id = 9000
GROUP BY event_id;
```

Result after insertion: `occurrences = 2`.

This proves:

> **A unique `(event_date,event_id)` key does not make `event_id` unique.**

### 7.2. Duplicate Key Pairs Are Rejected

With `(2026-01-12,9000)` already present:

```sql
-- Run separately to observe the expected unique_violation:
INSERT INTO part298.events(
    event_date, event_id, tenant_id, event_type
)
VALUES (DATE '2026-01-12', 9000, 7, 'LOGIN');
```

This fails with SQLSTATE `23505` because the **full primary key** collides.

If testing intentional errors inside an explicit `BEGIN` transaction, run `ROLLBACK` or roll back to a savepoint before issuing subsequent queries.

## 8. Uniqueness Scope: Parent vs. Child

Distinguish these cases carefully:

| Structure | Enforced Invariant | Guarantees `event_id` Unique Across Months? |
|---|---|---|
| Parent `PRIMARY KEY (event_date,event_id)` | Each **pair** of date + ID is unique | **No** |
| `UNIQUE(event_id)` on Jan partition only | ID unique **within January** | **No** |
| Unpartitioned table with `UNIQUE(event_id)` | ID unique across the whole table | Yes |
| `HASH(event_id)` table with parent `PRIMARY KEY(event_id)` | ID itself routes to partition | Yes, within the partitioned table and constraint |
| Unpartitioned ID registry with `PRIMARY KEY(event_id)` | ID unique in registry | Yes in registry; must stay synced with events table |

When discussing "global uniqueness," ask:

- **Unique on which columns?**
- **Over what scope?** One month, one tenant, or system-wide?
- **Who enforces it?** A PostgreSQL constraint or application convention?
- **What happens under concurrent writes?**
- **Must foreign keys reference one column or multiple?**

## 9. Rules for Expression Partition Keys

An important limitation: to define `UNIQUE` or `PRIMARY KEY` on a partitioned parent, **the partition key must consist of plain columns**, not expressions or function calls, per PostgreSQL's rules for verifying uniqueness via partitioned indexes.

Example of an expression-keyed design:

```sql
-- Structural example for discussion; not a lab schema:
CREATE TABLE demo_region_events (
    event_id bigint NOT NULL,
    region_code text NOT NULL
)
PARTITION BY LIST ((lower(region_code)));
```

Even if a unique index includes raw `region_code`, actual partition routing uses **`lower(region_code)`**. PostgreSQL does not deduce arbitrary expression relationships to prove parent-wide uniqueness across local indexes.

### 9.1. Modeling Workarounds

If the business requires a unique constraint on the parent:

- Store the normalized value in a **real column** maintained by application/triggers/generated rules.
- Partition directly on that normalized column rather than an expression.
- Include all required partition key columns in `UNIQUE`/`PK`.
- Use another ID/registry model if uniqueness cannot align with the partition key.

Never write a trigger function that "checks all partitions for duplicates" and assume it equals a concurrency-safe `UNIQUE` constraint.

## 10. Multi-Level Partitioning: Check the Entire Tree

PostgreSQL supports **subpartitioning**.

Example:

```text
orders_parent
    PARTITION BY LIST (tenant_id)
        |
        +-- orders_tenant_7
              PARTITION BY RANGE (ordered_on)
                  |
                  +-- orders_tenant_7_2026_01
                  +-- orders_tenant_7_2026_02
        |
        +-- orders_tenant_8
              PARTITION BY RANGE (ordered_on)
                  |
                  +-- orders_tenant_8_2026_01
```

When defining a parent `UNIQUE`/`PK` backed by indexes across leaf partitions, you must account for **all partition keys across all involved levels**.

A key containing only `tenant_id` separates tenant partitions, yet cannot prevent the same key from repeating across two months **inside one tenant** when leaves split further by date.

### 10.1. Candidate Key Example

To enforce **uniqueness per tenant + date + order ID**:

```text
UNIQUE (tenant_id, ordered_on, order_id)
```

includes every partition key column across the tree shown above.

In real designs, PostgreSQL checks constraint and index compatibility at every level during creation/attachment. Always test multi-level DDL explicitly rather than assuming any arbitrary tree accepts any unique index.

### 10.2. Per-Tenant Uniqueness Differs from System-Wide Uniqueness

`UNIQUE(tenant_id,order_id)`, when properly modeled and enforced, allows:

```text
tenant=7, order_id=100
tenant=8, order_id=100
```

This is **right** if IDs only need to be unique **within a tenant**.

It is **wrong** if an `order_id` must never repeat across any two tenants.

## 11. PRIMARY KEY Also Governs NOT NULL and Foreign Keys

A primary key entails two things:

1. Key columns are **`NOT NULL`**.
2. Key combinations **cannot duplicate**.

In our fixture:

```sql
PRIMARY KEY (event_date, event_id)
```

referencing an event by **`event_id` alone is insufficient** to identify a unique event under the declared constraint.

### 11.1. Creating a Child Table Referencing the Composite Key

```sql
CREATE TABLE part298.event_comments (
    comment_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_date date NOT NULL,
    event_id bigint NOT NULL,
    comment_text text NOT NULL,
    FOREIGN KEY (event_date, event_id)
        REFERENCES part298.events(event_date, event_id)
);
```

The comments table stores both key columns to reference an event by the parent's primary key.

Example:

```sql
INSERT INTO part298.event_comments(
    event_date, event_id, comment_text
)
VALUES (
    DATE '2026-01-10',
    1001,
    'Verified event'
);
```

### 11.2. Why Can't FOREIGN KEY(event_id) Be Used Directly?

Consider:

```sql
-- DDL example with no matching unique key on the parent:
FOREIGN KEY (event_id)
REFERENCES part298.events(event_id)
```

The parent has no valid `UNIQUE`/`PRIMARY KEY` on `event_id` alone, so PostgreSQL cannot use `event_id` as a unique foreign-key target.

Modern PostgreSQL supports **foreign keys referencing partitioned tables** and foreign keys defined on partitioned tables under compatible schemas/versions, provided **the referenced key is validly guaranteed unique**.

Do not think partitioning removes all foreign-key support; the core constraint here is **defining a valid unique target key**.

### 11.3. Consequences for APIs and ORMs

If an endpoint previously accepted only:

```text
GET /events/1001
```

and after partitioning `event_id=1001` can appear in multiple months, that endpoint **no longer uniquely identifies a single event** by ID alone.

Options:

- Require the partition key as well: `event_date + event_id`.
- Enforce global ID uniqueness via another model.
- Repartition so `event_id` is part of the partition key.
- Maintain a lookup/registry outside the partitioned parent.

Never convert a primary key to composite while leaving application code assuming "`event_id` alone uniquely identifies everything."

## 12. UNIQUE with NULL: Contrast with PRIMARY KEY

`PRIMARY KEY` forbids `NULL` in key columns. Standard `UNIQUE` has distinct `NULL` semantics.

Suppose a partitioned table has:

```sql
UNIQUE (event_date, external_code)
```

where `external_code` is nullable. Under PostgreSQL's default `UNIQUE` behavior, **`NULL`s are treated as distinct** and do not trigger duplicate errors.

Modern PostgreSQL versions also support `NULLS NOT DISTINCT` on `UNIQUE` constraints/indexes to treat `NULL`s as duplicates when needed.

Remember:

- Adding `NULLS NOT DISTINCT` **does not create a global index**.
- Parent `UNIQUE` constraints must still include all partition key columns.
- Null semantics cannot bypass missing partition key columns.
- If business rules forbid null key parts, declare `NOT NULL` explicitly.
- Partition key columns follow `RANGE`/`LIST`/`HASH` and `DEFAULT` null-routing rules; never rely on `NULL` comparisons as an "automatic unique key."

## 13. CREATE INDEX on a Partitioned Parent

**Non-unique** indexes on the parent are far more flexible than unique indexes: they **do not have to** include all partition key columns.

Example:

```sql
CREATE INDEX idx_part298_events_tenant
ON part298.events(tenant_id);
```

This DDL is valid in principle even though the partition key is `event_date`.

PostgreSQL creates a partitioned index on the parent and corresponding local indexes on all existing partitions.

### 13.1. Which Queries Does This Index Serve?

```sql
SELECT event_date, event_id, event_type
FROM part298.events
WHERE tenant_id = 7;
```

The local indexes on `tenant_id` speed up finding tenant 7 rows **within each partition**, yet because `WHERE` omits `event_date`, the query must still inspect **many or all partitions**.

If the query is:

```sql
SELECT event_date, event_id, event_type
FROM part298.events
WHERE tenant_id = 7
  AND event_date >= DATE '2026-02-01'
  AND event_date <  DATE '2026-03-01';
```

PostgreSQL can **prune** down to February alone and then use February's local index if cost-effective.

### 13.2. A Parent Index Is Not a "Global Index Scan"

Never picture it as:

```text
Index(tenant_id) on parent
    -> single lookup
    -> returns all months
```

The accurate model is:

```text
Determine which partitions must be read
    |
    +-- January partition: local index/scan
    +-- February partition: local index/scan
    +-- March partition: local index/scan
    |
Combine matching rows
```

The planner uses nodes like `Append` or `Merge Append` over per-partition scans. Exact plans depend on version, data distribution, and predicates.

## 14. Composite Indexes and Column Ordering on Partitions

Consider a hot query:

```sql
SELECT event_id, event_date, event_type
FROM part298.events
WHERE tenant_id = 7
  AND event_date >= DATE '2026-02-01'
  AND event_date <  DATE '2026-03-01'
ORDER BY event_date DESC, event_id DESC
LIMIT 20;
```

A well-suited index:

```sql
CREATE INDEX idx_part298_events_tenant_date_id
ON part298.events(
    tenant_id,
    event_date DESC,
    event_id DESC
);
```

Depending on data and plan:

1. `event_date` drives **partition pruning**.
2. Inside the surviving partition, the index uses `tenant_id` for equality.
3. Trailing keys `event_date DESC, event_id DESC` support ordering and `LIMIT`.
4. The planner can avoid sorting or limit how many rows are read.

### 14.1. Do Not Blindly Put the Partition Key First in Every Index

If most queries **always hit a single partition** and filter by `event_id`, a local index on `(event_id)` can suffice inside that partition.

Conversely, if queries span multiple partitions and sort by date, column order matters greatly.

There is no rule saying "every partition index must start with the partition key." Distinguish:

- **Mandatory** inclusion of the partition key in parent `UNIQUE`/`PRIMARY KEY`.
- **Performance-driven** column choice in non-unique B-tree indexes.

### 14.2. PRIMARY KEY Is Also an Index

`PRIMARY KEY (event_date,event_id)` already creates a B-tree in that order. When queries filter:

```sql
WHERE event_date = DATE '2026-02-10'
  AND event_id = 1003
```

the PK index serves it well.

When querying only:

```sql
WHERE event_id = 1003
```

the PK's leading `event_date` column makes it suboptimal across partitions. You may add a non-unique `(event_id)` index, while remembering that still **does not make `event_id` globally unique**.

## 15. Partition Pruning Is Not an Index Scan

The two decisions are independent:

### 15.1. Good Pruning, Still a Seq Scan

```sql
SELECT *
FROM part298.events
WHERE event_date >= DATE '2026-02-01'
  AND event_date <  DATE '2026-03-01';
```

PostgreSQL reads only `events_2026_02`. If February is tiny or the query reads most of February's rows, a **Seq Scan on that single partition** is completely optimal.

### 15.2. No Pruning, Still Uses Indexes Across Many Partitions

```sql
SELECT *
FROM part298.events
WHERE event_id = 9000;
```

Without an `event_date` predicate, PostgreSQL cannot use date ranges to tell which month holds that ID. If each partition has an index on `event_id`, it performs multiple index lookups across multiple partitions.

### 15.3. Why Does This Matter for ID-Based APIs?

An API knowing only `event_id` cannot prune to the right month unless:

- The ID encodes or maps to the partition key and the app supplies it in queries.
- A registry/lookup resolves `event_date` from `event_id`.
- Partitioning uses an ID-based strategy instead.
- Workload requirements tolerate scanning all partitions at an acceptable cost.

Time partitioning shines for **retention and range queries**, yet can be awkward for **date-less ID lookups**.

## 16. Using EXPLAIN to Observe Partition Pruning

Once lab data is loaded:

```sql
ANALYZE part298.events;
```

Query with a month predicate:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_date, event_id, tenant_id
FROM part298.events
WHERE event_date >= DATE '2026-02-01'
  AND event_date <  DATE '2026-03-01'
  AND tenant_id = 7;
```

Inspect:

- How many partitions appear in the plan.
- Whether each partition uses `Seq Scan`, `Index Scan`, or `Bitmap Heap Scan`.
- `actual rows` and `Buffers`.
- Which predicates appear as `Index Cond` vs. `Filter`.

### 16.1. Compare with a Query Without a Date Filter

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_date, event_id, tenant_id
FROM part298.events
WHERE tenant_id = 7;
```

Here the planner must examine all three partitions because `tenant_id` does not constrain date ranges.

### 16.2. The Planner Can Prune at Plan Time or Runtime

With explicit constants, pruning generally occurs at planning time.

In prepared statements or plans with runtime parameters, PostgreSQL also performs **execution-time partition pruning**. Never conclude "seeing multiple partitions in an initial generic plan means all of them actually scan data" when runtime parameters are present.

Check `EXPLAIN (ANALYZE, BUFFERS)` and version-specific runtime pruning indicators.

### 16.3. Watch Out for Expressions on the Partition Key

```sql
WHERE date_trunc('month', some_timestamp) = ...
```

does not automatically equate to a prunable range predicate if the partition key, types, and expressions do not match. When partitioned by a date column, prefer direct sargable range predicates on the column when aligned with business semantics.

## 17. Per-Partition Local Indexes

You can create an index on just one partition:

```sql
CREATE INDEX idx_part298_events_2026_02_type
ON part298.events_2026_02(event_type);
```

This helps queries touching February only. It is not automatically created for January, March, or future months.

### 17.1. When Are Local-Only Indexes Useful?

Examples:

- Old historical partitions are rarely read and do not need all indexes used by hot partitions.
- The newest partition gets heavy queries on a specialized column.
- One partition has a skewed data distribution.
- An ad-hoc reporting campaign targets only one specific year/month.

### 17.2. Risk of Inconsistency

If the same query can span multiple partitions with mismatched indexes, plans and latencies can fluctuate wildly by month.

Track:

- Which partitions lack an index.
- Which index policies belong to the parent.
- Which indexes are intentional local exceptions.
- Build and maintenance cost of each index.
- Whether newly provisioned partitions get required policy indexes.

Never mistake a local index for a table-wide parent policy or constraint.

## 18. Partial Indexes on Partitioned Tables

A workload looking only for `PAYMENT` events:

```sql
SELECT event_date, event_id, tenant_id
FROM part298.events
WHERE event_type = 'PAYMENT'
  AND event_date >= DATE '2026-02-01'
  AND event_date <  DATE '2026-03-01';
```

can benefit from a partial index:

```sql
CREATE INDEX idx_part298_payment_tenant_date
ON part298.events(tenant_id, event_date)
WHERE event_type = 'PAYMENT';
```

Defining it on the parent creates matching partial indexes on each partition.

### 18.1. Predicates Must Match the Query

The planner uses a partial index only when it can prove the query needs no rows excluded by the index's `WHERE` predicate.

A query with:

```sql
WHERE event_type = 'PAYMENT'
```

matches the predicate directly.

However, a generic prepared plan with:

```sql
WHERE event_type = $1
```

cannot prove `$1` is always `'PAYMENT'`, so the planner cannot safely choose the partial index in a generic plan.

### 18.2. Partial UNIQUE Is Still Not a Global Unique Index

Do not assume:

```sql
CREATE UNIQUE INDEX ... ON parent(event_id)
WHERE event_type='PAYMENT';
```

bypasses partition-key requirements simply because the predicate narrows the rows. Uniqueness is still enforced via local indexes and must obey PostgreSQL's partition-key rules.

### 18.3. Distinguish Constraints from Partial Unique Indexes

A **partial unique index** enforces "at most one matching row" within the scope provable by keys/partitions. It is not identical to a standard `UNIQUE CONSTRAINT` for all purposes—such as serving as a foreign-key target or certain inference rules.

Verify that your chosen constraint satisfies all referential and business requirements.

## 19. INCLUDE and Covering Indexes on Partitions

B-tree indexes can include non-key payload columns:

```sql
CREATE INDEX idx_part298_events_tenant_date_cover
ON part298.events(tenant_id, event_date DESC, event_id DESC)
INCLUDE (event_type);
```

On each partition, the index stores:

- **Key columns:** `tenant_id`, `event_date`, `event_id`.
- **Included column:** `event_type`.

A query:

```sql
SELECT event_date, event_id, event_type
FROM part298.events
WHERE tenant_id = 7
  AND event_date >= DATE '2026-01-01'
  AND event_date <  DATE '2026-02-01'
ORDER BY event_date DESC, event_id DESC
LIMIT 20;
```

can use the index for filtering, ordering, and returning all requested columns.

### 19.1. INCLUDE Columns Are Not Search Keys

If `event_type` sits only in `INCLUDE`, it **does not** act as a B-tree key column to narrow range scans the way key columns do.

### 19.2. Index Only Scans Can Still Touch the Heap

PostgreSQL checks the visibility map/MVCC to see if pages are all-visible without visiting the heap. If heap pages are not all-visible, `Index Only Scan` still incurs `Heap Fetches`.

Because each partition has its own `VACUUM` and visibility state, the same monthly query can see different heap fetch counts across months.

### 19.3. Do Not INCLUDE Huge Payloads

Avoid stuffing large `JSONB` columns into every B-tree `INCLUDE` just to "skip heap reads" without evaluating index bloat, entry size limits, write amplification, and real query access patterns.

## 20. CREATE INDEX CONCURRENTLY Cannot Run Directly on a Partitioned Parent

On an unpartitioned heap table:

```sql
CREATE INDEX CONCURRENTLY idx_name
ON schema.table_name(column_name);
```

minimizes write blocking compared to regular `CREATE INDEX`, subject to its own restrictions.

On a **partitioned parent**, however, PostgreSQL enforces an important limitation: **`CREATE INDEX CONCURRENTLY` is not supported directly across the whole parent tree**.

This matters deeply once a table has hundreds of large partitions under continuous write traffic.

### 20.1. Why Avoid Plain CREATE INDEX During Peak Traffic?

A single command on the parent builds indexes across all existing partitions, acquiring locks and running for a duration proportional to total data size—potentially disrupting concurrent DML significantly.

For continuously running systems, plan to:

- Build indexes **`CONCURRENTLY`** on each physical partition where supported.
- Declare an initially invalid parent index using `ON ONLY`.
- Attach each child index to the parent index.
- Verify the parent index once all partitions are attached.

This is PostgreSQL's standard workflow to construct a partitioned index online without blocking the entire tree under a plain parent `CREATE INDEX`.

## 21. Building a Parent Index via ON ONLY + ATTACH PARTITION

This section uses a separate lab table to avoid colliding with indexes already built on `events`.

### 21.1. Create the measurements Table

```sql
CREATE TABLE part298.measurements (
    measured_on date NOT NULL,
    device_id integer NOT NULL,
    measured_value double precision NOT NULL
) PARTITION BY RANGE (measured_on);

CREATE TABLE part298.measurements_2026_01
PARTITION OF part298.measurements
FOR VALUES FROM (DATE '2026-01-01')
           TO   (DATE '2026-02-01');

CREATE TABLE part298.measurements_2026_02
PARTITION OF part298.measurements
FOR VALUES FROM (DATE '2026-02-01')
           TO   (DATE '2026-03-01');
```

### 21.2. Create the Index Definition ON ONLY Parent

```sql
CREATE INDEX idx_part298_measurements_device_time
ON ONLY part298.measurements(device_id, measured_on);
```

Effect:

- Creates the **partitioned index definition** on the parent.
- Does **not** build indexes on existing partitions.
- Marks the parent index **invalid** until every required partition has a matching index attached.

An invalid parent index does not stop valid child indexes from being used locally by queries; it indicates the parent-wide definition is **not yet complete**.

### 21.3. Build Indexes CONCURRENTLY on Each Partition

Run each statement independently, outside an explicit transaction block:

```sql
CREATE INDEX CONCURRENTLY idx_part298_measurements_2026_01_device_time
ON part298.measurements_2026_01(device_id, measured_on);

CREATE INDEX CONCURRENTLY idx_part298_measurements_2026_02_device_time
ON part298.measurements_2026_02(device_id, measured_on);
```

**Notes:**

- `CREATE INDEX CONCURRENTLY` cannot run inside an explicit transaction block.
- Each partition is a physical table eligible for concurrent indexing.
- On large partitions, monitor each build and handle failures.
- If a concurrent build fails, an invalid local index may remain; never `ATTACH` it until cleaned up and rebuilt validly.

### 21.4. ATTACH Child Indexes

```sql
ALTER INDEX part298.idx_part298_measurements_device_time
ATTACH PARTITION
    part298.idx_part298_measurements_2026_01_device_time;

ALTER INDEX part298.idx_part298_measurements_device_time
ATTACH PARTITION
    part298.idx_part298_measurements_2026_02_device_time;
```

PostgreSQL verifies index compatibility and records the partitioned-index relationship.

Once **all required partition indexes** are attached, the parent partitioned index transitions to valid.

### 21.5. Check indisvalid

```sql
SELECT
    c.relname AS index_name,
    i.indisvalid,
    i.indisready
FROM pg_index AS i
JOIN pg_class AS c
    ON c.oid = i.indexrelid
WHERE i.indexrelid =
    'part298.idx_part298_measurements_device_time'::regclass;
```

Once the parent index is complete, `indisvalid` should be `TRUE`.

### 21.6. With Many Partitions

Track the full list of existing partitions and their indexes; if only partially completed, **never report the parent index build as done**.

When creating future partitions later, ensure the parent's index policy keeps applying. If a partition lacks a matching index or an `ATTACH` fails, re-verify structural state per your runbook.

## 22. Limitations of CREATE INDEX CONCURRENTLY

Even when executed per physical partition, `CONCURRENTLY` has notable caveats:

- Cannot run inside an explicit transaction block.
- Uses multiple scan/wait phases, often taking longer than a regular `CREATE INDEX`.
- Can fail and leave behind an `INVALID` index.
- Avoid unsupported overlapping concurrent index builds on the same table.
- Concurrent unique index builds have extra duplicate-handling mechanics; duplicate errors must be resolved.
- On large tables, I/O, WAL, and storage consumption remain heavy even though DML blocking is reduced.

**"CONCURRENTLY" never means "zero locks and zero production impact."** It reduces certain blocking, not all resource costs.

### 22.1. Can ATTACH Be Used for UNIQUE?

You can construct a **partitioned unique index** this way when the `UNIQUE` key satisfies partition-key inclusion and PostgreSQL constraints. Never assume building local unique indexes on each child allows attaching them into a parent `UNIQUE` index that omits the partition key.

Correctness requires **a unique key compatible with partition routing**, not an `ATTACH` trick.

### 22.2. PRIMARY KEY/UNIQUE Constraints and USING INDEX

Do not assume a regular table's `ADD CONSTRAINT ... USING INDEX` syntax works identically on a partitioned parent across all versions. Partitioned indexes and constraints follow distinct DDL rules; check `ALTER TABLE` docs for your running PostgreSQL version.

For large `PK`/`UNIQUE` migrations, plan and test explicitly rather than copying a non-unique index script blindly.

## 23. Adding Future Partitions and Indexes Later

Suppose in April the system needs a new partition:

```sql
CREATE TABLE part298.events_2026_04
PARTITION OF part298.events
FOR VALUES FROM (DATE '2026-04-01')
           TO   (DATE '2026-05-01');
```

With declarative partitioning, valid parent-level constraints and indexes automatically propagate to the new partition.

### 23.1. Do Not Assume Child-Only Local Indexes Propagate

An index created directly on `events_2026_02` **does not automatically** become a policy for `events_2026_04`.

If specialized local indexes are needed, partition provisioning scripts must know which months should receive them.

### 23.2. Attaching a Pre-Populated Table

When running `ALTER TABLE ... ATTACH PARTITION` on an existing table, PostgreSQL must verify rows satisfy bounds and ensure compatible constraints, indexes, and locks.

Validation may scan large tables. Pre-validating a matching `CHECK` constraint can skip certain scans in supported scenarios, yet never assume `ATTACH` is always instantaneous.

### 23.3. DEFAULT Partition

A `DEFAULT` partition catches rows matching no explicit partition.

However, when later adding a new partition whose range overlaps data sitting in `DEFAULT`, you must migrate/remove those rows and satisfy constraints before creating/attaching the new partition.

A `DEFAULT` partition avoids immediate `INSERT` failures, yet **never replaces scheduled partition provisioning** or solves global uniqueness.

## 24. UNIQUE, PRIMARY KEY, and ON CONFLICT

PostgreSQL supports `INSERT ... ON CONFLICT` with matching unique constraints or indexes.

Our fixture has:

```sql
PRIMARY KEY (event_date, event_id)
```

So we can write:

```sql
INSERT INTO part298.events(
    event_date, event_id, tenant_id, event_type, payload
)
VALUES (
    DATE '2026-02-10', 1003, 7, 'LOGIN',
    '{"ok":false}'::jsonb
)
ON CONFLICT (event_date, event_id)
DO UPDATE SET
    payload = EXCLUDED.payload;
```

This upserts by **date + ID pair**, not by `event_id` alone.

### 24.1. ON CONFLICT(event_id) Does Not Work Automatically

On our current schema:

```sql
-- No matching unique constraint/index on parent(event_id) alone:
INSERT INTO part298.events(
    event_date, event_id, tenant_id, event_type
)
VALUES (DATE '2026-02-11', 1003, 7, 'LOGIN')
ON CONFLICT (event_id)
DO NOTHING;
```

Because no unique arbiter exists on `event_id` alone at the parent, this conflict target fails.

### 24.2. DO NOTHING Does Not Make IDs Globally Unique

Even when writing `ON CONFLICT DO NOTHING` without specifying a conflict target, PostgreSQL only catches conflicts defined by existing constraints/indexes. It **never** invents a `unique(event_id)` rule that the schema does not enforce.

Two rows sharing `event_id` on different `event_date`s do not conflict under the composite primary key.

### 24.3. UPDATE Changing the Partition Key

PostgreSQL supports row movement across partitions during supported partition-key `UPDATE`s, yet `ON CONFLICT DO UPDATE` has **restrictions** against modifying the conflicting row's partition key in a way that would move it to another partition.

When designing upserts with time partitioning:

- Never assume you can "shift an event to a different date" inside `ON CONFLICT DO UPDATE`.
- Check your version's documentation and test explicitly.
- If `event_date` is part of the key, changing the date mutates the composite identity and foreign references.

## 25. CHECK and NOT NULL on Partitioned Tables

Constraints like `CHECK` and `NOT NULL` declared on the parent protect rows across the partition hierarchy under inheritance/declarative partitioning rules.

Example:

```sql
ALTER TABLE part298.events
ADD CONSTRAINT event_type_not_blank
CHECK (length(btrim(event_type)) > 0);
```

This guarantees every event row has a non-empty trimmed `event_type`.

### 25.1. CHECK Validates Individual Rows, Not Cross-Partition Uniqueness

For instance:

```sql
CHECK (tenant_id > 0)
```

is a row-level rule.

Whereas:

```text
Each event_id appears at most once system-wide.
```

is a **multi-row** rule. You cannot turn it into a `CHECK` running a subquery across all partitions and expect it to be safe under concurrency.

### 25.2. Child vs. Parent CHECK Constraints

Under declarative partitioning, parent constraints apply across partitions. Child-specific constraints can further restrict a single partition when allowed.

Never drop parent constraints from a child "to speed up imports"—doing so breaks the shared table contract.

### 25.3. Constraint Validation on Attach

When attaching a populated table, PostgreSQL must verify data satisfies parent bounds and constraints—another reason partition migrations aren't just metadata renames.

## 26. EXCLUDE Constraints and Similar Limits

`EXCLUDE` is useful for rules such as **preventing overlapping time intervals** when paired with suitable operators and index methods.

On an unpartitioned table, GiST + range operators express non-overlapping rules cleanly. On a partitioned parent, however, verify:

- Does the partitioning scheme guarantee any two potentially conflicting rows route to the same partition?
- Do partition key columns participate in the exclusion constraint with the required comparison operator?
- Does your PostgreSQL version support `EXCLUDE` on a partitioned parent with that structure?
- Is an extension like `btree_gist` needed for equality on scalar columns?

In versions supporting `EXCLUDE` on partitioned tables, partition key columns must participate in the constraint in a way ensuring **rows in different partitions cannot conflict**—typically via **equality** on the partition key.

**Never treat `EXCLUDE` as an arbitrary global uniqueness/overlap index** capable of checking pairs across partitions without involving the partition key.

### 26.1. Semantic Limitation Example

Suppose conference room bookings are partitioned by **start month**, while a meeting can span month-end. Two overlapping bookings for the same room might start in **two different months/partitions**.

A per-partition overlap constraint would miss the cross-month collision. Design partition keys, constraints, or coordination logic to protect the true invariant.

## 27. When Business Rules Require Globally Unique event_id

This is the most critical architectural decision in this lesson.

Requirement:

```text
Each event_id appears at most once across all of events,
regardless of date, month, tenant, or partition.
```

Partitioning by `event_date` with `PK(event_date,event_id)` **does not satisfy** that requirement.

Several design paths exist.

### 27.1. Option A — Partition by event_id Instead

Partitioning by **`HASH(event_id)`**:

```sql
CREATE TABLE part298.events_by_hash (
    event_id bigint NOT NULL,
    event_date date NOT NULL,
    event_type text NOT NULL,
    PRIMARY KEY (event_id)
) PARTITION BY HASH (event_id);
```

Create four partitions:

```sql
CREATE TABLE part298.events_by_hash_p0
PARTITION OF part298.events_by_hash
FOR VALUES WITH (MODULUS 4, REMAINDER 0);

CREATE TABLE part298.events_by_hash_p1
PARTITION OF part298.events_by_hash
FOR VALUES WITH (MODULUS 4, REMAINDER 1);

CREATE TABLE part298.events_by_hash_p2
PARTITION OF part298.events_by_hash
FOR VALUES WITH (MODULUS 4, REMAINDER 2);

CREATE TABLE part298.events_by_hash_p3
PARTITION OF part298.events_by_hash
FOR VALUES WITH (MODULUS 4, REMAINDER 3);
```

Here the partition key is `event_id`, so `PRIMARY KEY(event_id)` is valid.

**Why does global uniqueness hold?**

Any two rows with the same `event_id` route to the **exact same partition**, where that partition's local unique index catches the duplicate—no global physical index needed.

Trade-offs:

- `event_id` lookups prune straight to one bucket.
- Monthly purging via `DETACH`/`DROP` is no longer simple like `RANGE(date)`.
- Date-only queries must typically scan all hash partitions.

### 27.2. Option B — Accept a Composite Key

Keep `RANGE(date)` and define the business identifier as:

```text
(event_date, event_id)
```

All APIs, FKs, lookups, cache keys, and external references must carry both components.

Pros:

- Date partitioning supports retention and time-range queries.
- Enforced directly by the parent PK.

Cons:

- ID alone does not identify a row.
- Foreign keys become composite.
- ORMs, URLs, upserts, and consumers must propagate the date.

**Choose this only if the business domain genuinely accepts composite identity.**

### 27.3. Option C — Unpartitioned ID Registry

Maintain a dedicated table with a true `UNIQUE`/`PK` on ID:

```sql
CREATE TABLE part298.event_id_registry (
    event_id bigint PRIMARY KEY,
    event_date date NOT NULL
);
```

Write workflow:

```sql
BEGIN;

INSERT INTO part298.event_id_registry(event_id, event_date)
VALUES (50001, DATE '2026-02-15');

INSERT INTO part298.events(
    event_date, event_id, tenant_id, event_type
)
VALUES (
    DATE '2026-02-15', 50001, 7, 'LOGIN'
);

COMMIT;
```

If two transactions attempt to claim `event_id=50001`, the registry PK blocks the second one.

Mandatory conditions:

- **Every write path creating events must register the ID in the same transaction**.
- If inserting the event fails, the registry insert must roll back together.
- Manage deletions, date changes, retention, and ID reuse consistently.
- The registry can become a write hotspot or add write overhead.
- Keep references and cleanup aligned.

### 27.4. A Registry Does Not Automatically Provide an event_id → events FK

If other tables reference `event_id_registry(event_id)`, the FK proves **the ID was registered**, not that the detail row still exists in `events` if retention later purges old partitions while leaving the registry.

Applications must clarify whether the registry is a permanent ID ledger or a strict 1-to-1 mirror of active events, and enforce that contract across inserts, deletes, and migrations.

### 27.5. Option D — Sequence/UUID ID Generation

A shared sequence:

```sql
CREATE SEQUENCE part298.event_id_seq;
```

or UUIDs **reduce collision likelihood** and provide consistent ID issuance, yet distinguish carefully:

- A sequence yields new values on `nextval` per sequence semantics.
- Applications or admins can still manually insert duplicate IDs if the schema allows it.
- Sequences can be altered/reset and do not constrain arbitrary inserts across partitions.
- Random UUIDs have tiny collision probability, which is not equivalent to a database-enforced parent `UNIQUE` constraint.

**Generating distinct IDs and enforcing `UNIQUE` are two different guarantees.** If strict zero-duplicate invariants are required, pair with appropriate constraints or protocols.

## 28. Choosing a Partition Key by Query Patterns and Uniqueness

One partition key choice affects everything at once:

| Goal | `RANGE(event_date)` | `HASH(event_id)` |
|---|---|---|
| Monthly queries | Strong pruning with date predicates | Usually scans all hash partitions |
| Monthly retention/purge | Easy `DETACH`/`DROP` of monthly partition | Inconvenient |
| Lookup single `event_id` | Without date, may probe all months | Prunes by `event_id` |
| Parent `PK(event_id)` | Invalid without date | Valid on hash key |
| Parent `PK(event_date,event_id)` | Valid | Valid because `event_id` is included |
| Local tenant index | Possible per month | Possible per hash partition |
| Adding partitions | Follows calendar schedule | Follows hash modulus plan |
| Foreign key design cost | Often requires composite date+id | Can use `event_id` if `PK(id)` |

Never partition **merely** because "the table has many rows." Clarify first:

1. Which columns do primary queries filter on?
2. Is data purged/archived by time or by tenant?
3. Which IDs must be globally unique?
4. Which tables hold foreign keys referencing this table?
5. Are events frequently looked up by ID without knowing the date?
6. Can the entire application adopt a composite identity?
7. Are partition and index counts operationally sustainable?

## 29. Multi-Tenant: Unique per Tenant or System-Wide?

Example multi-tenant orders table partitioned by tenant:

```sql
CREATE TABLE part298.tenant_orders (
    tenant_id integer NOT NULL,
    order_id bigint NOT NULL,
    ordered_on date NOT NULL,
    amount_cents bigint NOT NULL CHECK (amount_cents >= 0),
    PRIMARY KEY (tenant_id, order_id)
) PARTITION BY HASH (tenant_id);
```

This is structurally sound because the parent PK includes the partition key `tenant_id`.

Uniqueness is:

```text
UNIQUE (tenant_id, order_id)
```

Therefore:

```text
tenant=7, order_id=42 -> valid
tenant=8, order_id=42 -> also valid
```

### 29.1. Do Not Treat order_id Alone as a System-Wide Identifier

If an application runs:

```sql
SELECT *
FROM part298.tenant_orders
WHERE order_id = 42;
```

it can return rows from multiple tenants and scan every partition. Beyond performance, omitting the tenant filter poses a **cross-tenant data-leak risk**.

Always query with the authenticated tenant:

```sql
SELECT *
FROM part298.tenant_orders
WHERE tenant_id = 7
  AND order_id = 42;
```

In real systems, derive `tenant_id` from trusted auth/authorization context rather than blindly trusting client-supplied parameters.

### 29.2. RLS Does Not Alter Per-Tenant Uniqueness

Row Level Security restricts which rows a session can read or write, yet does not change uniqueness rules governed by the partition key. Constraints, partition routing, and RLS solve different problems.

## 30. Inspecting Catalogs: Which Tables Are Partitions, Which Indexes Are Partitioned?

### 30.1. Listing the Partition Tree

PostgreSQL provides a helper function to view the partition hierarchy:

```sql
SELECT
    relid::regclass AS relation_name,
    parentrelid::regclass AS parent_relation,
    isleaf,
    level
FROM pg_partition_tree('part298.events'::regclass)
ORDER BY level, relation_name;
```

This lists the parent and leaf partitions along with tree depth.

### 30.2. Using pg_inherits

```sql
SELECT
    parent.oid::regclass AS parent_table,
    child.oid::regclass AS child_table
FROM pg_inherits AS inh
JOIN pg_class AS parent
    ON parent.oid = inh.inhparent
JOIN pg_class AS child
    ON child.oid = inh.inhrelid
WHERE parent.oid = 'part298.events'::regclass
ORDER BY child.relname;
```

`pg_inherits` also records inheritance/attachment relationships in other contexts; filter carefully by the target parent.

### 30.3. Distinguishing Parent Indexes from Child Indexes

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS index_name,
    c.relkind,
    t.relname AS indexed_table,
    i.indisunique,
    i.indisprimary,
    i.indisvalid
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
JOIN pg_index AS i
    ON i.indexrelid = c.oid
JOIN pg_class AS t
    ON t.oid = i.indrelid
WHERE n.nspname = 'part298'
ORDER BY t.relname, c.relname;
```

Relevant `pg_class.relkind` codes:

- `I`: partitioned index.
- `i`: regular physical index.

Inspect `relkind`, indexed table, and constraint flags together—never rely on index name alone.

### 30.4. Inspecting Index Partition Links

```sql
SELECT
    pi.inhparent::regclass AS parent_index,
    pi.inhrelid::regclass AS child_index
FROM pg_inherits AS pi
WHERE pi.inhparent =
    'part298.idx_part298_measurements_device_time'::regclass
ORDER BY child_index;
```

After the `ATTACH PARTITION` lab in Section 21, this shows each child index linked under the parent index.

## 31. Tracking Index Usage per Partition

Inspect usage stats:

```sql
SELECT
    relname AS table_name,
    indexrelname AS index_name,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'part298'
ORDER BY relname, indexrelname;
```

Because scans execute on physical partitions, inspect **indexes on the partitions actually queried**. Never check only the partitioned parent's stats row and assume an index is unused.

### 31.1. Index Presence Alone Does Not Guarantee Usage

A valid index may go unused if:

- The partition is tiny.
- Filter predicates match most rows.
- Operators or column order don't match the index.
- Pruning isn't narrowing partitions.
- Too many random heap fetches are needed.
- Sort/Seq Scan is cheaper.
- Statistics are stale or skewed.

Verify with `EXPLAIN (ANALYZE, BUFFERS)` on representative data before judging.

### 31.2. Size per Partition and Index

```sql
SELECT
    c.oid::regclass AS relation_name,
    pg_size_pretty(pg_relation_size(c.oid)) AS relation_size
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'part298'
  AND c.relkind IN ('r', 'i', 'I', 'p')
ORDER BY c.relname;
```

Logical partitioned parents/indexes (`p`, `I`) do not hold heap/index storage like child partitions (`r`, `i`). Sum across physical partitions/indexes to get true disk footprint rather than checking parent size and assuming the table uses zero disk.

## 32. Operational Overhead of Many Partitions and Indexes

Partitioning brings benefits, but is not free:

- Every partition is a relation with its own metadata.
- Every partition may carry multiple indexes.
- Query planning across huge partition counts adds cost.
- Parent DDL fans out across many partitions.
- `ANALYZE`/`VACUUM`/autovacuum and stats must be managed at the right granularity.
- Backups, restores, migrations, and retention touch more objects.
- Missing or misconfigured partitions cause `INSERT` failures.
- Inconsistent local index policies yield erratic performance across months.

### 32.1. Too Many Indexes per Partition

With 120 partitions and 8 indexes each, the database manages **960 physical indexes**, excluding parent definitions and other objects.

That is simple arithmetic, not a fixed PostgreSQL limit.

Adding one parent index triggers building many child indexes. Budget for:

- Build duration.
- Storage footprint.
- WAL and I/O volume.
- `INSERT`/`UPDATE`/`DELETE` write amplification.
- Ongoing maintenance cost.
- Provisioning time for new partitions.

### 32.2. Fast Retention Comes with Conditions

A major strength of `RANGE(date)` is detaching/dropping historical partitions per policy. Still:

- Check FKs, constraints, and data dependencies.
- Confirm retention windows and legal holds.
- Account for DDL lock and privilege requirements.
- Never drop a partition still referenced by active rows in other tables.
- Keep backups, restores, and ID registries consistent with purged history.

"Fast partition drops" are never an excuse to ignore referential integrity.

## 33. Managing UNIQUE/PK When Adding or Attaching Partitions

On a parent with a valid `PRIMARY KEY` or `UNIQUE` constraint:

1. Verify the new partition has matching columns, types, and `NOT NULL` flags.
2. Verify bounds do not overlap.
3. Check whether existing rows violate constraints.
4. Ensure compatible indexes exist or are built/attached properly.
5. Monitor locks and validation time during `ATTACH`.
6. Re-verify parent/child index state afterward.
7. Run representative `EXPLAIN` checks as needed.
8. Never declare migration success simply because the partition appears in catalogs.

### 33.1. New Tables Created with PARTITION OF

PostgreSQL automatically propagates matching parent indexes and constraints via declarative DDL.

### 33.2. Existing Tables Brought In via ATTACH PARTITION

Compatibility checks and index builds may require scanning and extra work. Never assume attaching an empty table and attaching a 100-million-row table carry the same operational impact.

### 33.3. Local Uniqueness Does Not Upgrade to Parent Uniqueness

Even if January, February, and March each have `UNIQUE(event_id)`, that still cannot prevent the same `event_id` from repeating across months. Never treat "every partition has a unique index" as proof of global uniqueness unless routing partitions by that exact key.

## 34. Distinguishing Idempotency, Uniqueness, and Ordering

Three easily conflated requirements:

**Uniqueness:**

```text
No two rows share the same key as defined by the constraint.
```

**Idempotency:**

```text
Re-sending the same request causes no duplicate business side effects.
```

**Ordering:**

```text
Results can be sorted by time/ID to return an exact top-N.
```

A `UNIQUE` constraint can help build idempotency, yet:

- `UNIQUE(event_date,event_id)` still permits the same `event_id` on two dates.
- If a retried client assigns a new `event_date` to the same `event_id`, it creates a second event.
- With a unique `(event_id)` registry, pair it with request keys/payload checks to separate valid retries from real conflicts.
- An index on `event_date` aids `ORDER BY` without enforcing `event_id` uniqueness.

Never expect a single index to solve all three requirements simultaneously.

## 35. Designing Tests for Constraints and Partition Routing

A test suite should cover:

| Test | Expected Outcome |
|---|---|
| Insert two identical `(date,id)` pairs | Rejected by composite PK |
| Insert same `id` on two different dates | Succeeds if PK is only `(date,id)` |
| `CREATE UNIQUE(id)` on `RANGE(date)` parent | Rejected for missing partition key |
| Non-unique `CREATE INDEX(id)` on parent | Succeeds |
| `UNIQUE(id)` on separate monthly children | Does not block duplicate IDs across children |
| `WHERE date` within one month | Prunes other months |
| `WHERE id` alone | Does not prune `RANGE(date)` |
| UPSERT on `(date,id)` | Conflicts on composite key |
| UPSERT targeting `(id)` alone | Fails: no matching unique arbiter |
| `FOREIGN KEY(date,id)` to parent | Valid against composite PK |
| `FOREIGN KEY(id)` to parent | Invalid: no `id`-only unique key on parent |
| Add new partition | Parent indexes/constraints propagate properly |
| Local index on one month only | Does not appear on other months |
| Parent index `ON ONLY` | Initially invalid |
| Attach all child indexes | Parent index becomes valid |
| Concurrent index build fails | Not marked complete; invalid index handled |
| Partition-key change in `UPDATE`/`UPSERT` | Verify exact limits and semantics |
| Insert date outside all RANGE bounds | Errors unless `DEFAULT` exists |
| Registry ID + event insert in one transaction | Preserves consistency across compliant writers |
| Concurrent inserts of same ID into registry | Registry PK blocks duplicates |
| Multi-level partitioning | Constraints include partition keys across involved levels |

### 35.1. Concurrency Testing Is Mandatory for Global ID Registries

Never test only two sequential `INSERT`s. Test:

- Two concurrent connections.
- Two transactions racing to claim the same `event_id`.
- Verify both cannot commit duplicate registry rows.
- Verify event and registry rows roll back or commit together.
- Test retries when connections drop near `COMMIT`.
- Test deletion and ID lifecycle per retention rules.

**Neither `CHECK` nor `SELECT NOT EXISTS` before `INSERT` replaces a `UNIQUE` constraint under concurrency.**

## 36. Common Pitfalls

### Pitfall 1 — Thinking a Parent Index Is a Single Global Physical B-Tree

A parent partitioned index is a logical structure backed by per-partition physical indexes.

### Pitfall 2 — Declaring PRIMARY KEY(id) on a RANGE(date) Table

The parent PK lacks the partition key and is rejected by PostgreSQL.

### Pitfall 3 — Adding Date to PK Yet Claiming ID Is Globally Unique

`PRIMARY KEY(date,id)` only makes the date+id pair unique.

### Pitfall 4 — Creating UNIQUE(id) Separately on Every Partition Thinking It Is Global

Different partitions can still hold identical `id` values.

### Pitfall 5 — Treating Sequences/UUIDs as Absolute UNIQUE Constraints

ID generation and uniqueness enforcement are distinct mechanisms.

### Pitfall 6 — Using an Expression Partition Key Expecting Parent UNIQUE to Work

Parent `UNIQUE`/`PK` constraints face restrictions with expression/function partition keys.

### Pitfall 7 — Ignoring Subpartition Keys in Multi-Level Trees

A parent constraint fails if deeper subpartitioning splits on a column omitted from the unique key.

### Pitfall 8 — Forgetting to Update Foreign Keys When PK Becomes Composite

Child tables referencing `id` alone can no longer identify a unique event.

### Pitfall 9 — Using ON CONFLICT(id) When Only PK(date,id) Exists

There is no single-column `id` unique arbiter.

### Pitfall 10 — Using ON CONFLICT DO NOTHING Thinking It Stops Cross-Month Duplicates

`DO NOTHING` only catches conflicts on existing constraints; it never creates global uniqueness.

### Pitfall 11 — Filtering Only by id and Expecting Pruning

`RANGE(date)` requires date predicates to eliminate partitions.

### Pitfall 12 — Seeing Partition Pruning and Assuming Index Scan Must Happen

The planner can choose `Seq Scan` inside a small partition; pruning and index access are distinct.

### Pitfall 13 — Requiring Every Non-Unique Index to Include the Partition Key

Only parent `UNIQUE`/`PK` constraints require the partition key—not regular non-unique indexes.

### Pitfall 14 — Running CREATE INDEX CONCURRENTLY Directly on the Parent

This is restricted; use the per-partition concurrent build workflow instead.

### Pitfall 15 — Creating a Parent Index ON ONLY and Forgetting to ATTACH All Child Indexes

The parent index stays invalid and the migration remains incomplete.

### Pitfall 16 — Attaching a Failed Concurrent Index Build

Invalid child indexes must never be treated as complete.

### Pitfall 17 — Assuming a February Local Index Propagates to March

Local child-only indexes are not parent policies.

### Pitfall 18 — Forgetting DEFAULT or Next Month's Partition Provisioning

`INSERT`s for uncovered dates will fail.

### Pitfall 19 — Writing a Row-Level CHECK Counting Partitions as "Uniqueness"

Row-level `CHECK`s cannot replace cross-row `UNIQUE` constraints and fail under races.

### Pitfall 20 — Keeping Unused Indexes on Every Partition

Extra indexes inflate writes, WAL, storage, and maintenance.

### Pitfall 21 — Checking Parent Index Scan Stats and Assuming the Index Is Unused

Inspect actual child index scan counters and `EXPLAIN` plans.

### Pitfall 22 — Switching Partition Strategy Without Evaluating Retention

`HASH(id)` allows `PK(id)` yet loses easy monthly `DETACH`/`DROP` purging.

### Pitfall 23 — Using an ID Registry Outside the Event Transaction

Leaves orphaned registry entries or unregistered events.

### Pitfall 24 — Dropping Historical Partitions While Ignoring Foreign Keys

Breaks referential integrity or hits constraint errors; align retention end-to-end.

### Pitfall 25 — Assuming Parent DDL Alone Reflects Operational Reality

Verify actual child structures, index validity, and all write/migration paths.

## 37. Practice Exercises with Answers

### Exercise 1. Does a Parent Partitioned Index Store All Index Entries Together?

**Answer:** No—not as one global physical B-tree; each partition holds its own physical index.

### Exercise 2. Why Is UNIQUE(event_id) Invalid on a RANGE(event_date) Parent?

**Answer:** The unique key lacks the `event_date` partition key, allowing identical `event_id`s in different partitions undetected by local indexes.

### Exercise 3. Write a Valid PK for RANGE(event_date) events

```sql
PRIMARY KEY (event_date, event_id)
```

**Answer:** Includes the partition key. Does not guarantee global `event_id` uniqueness.

### Exercise 4. Are Two Rows with the Same event_id on Different Dates Allowed?

**Answer:** Yes, if the PK is only `(event_date,event_id)` and no other constraint blocks it.

### Exercise 5. Two Rows with the Same (event_date,event_id) Pair?

**Answer:** No—rejected by the PK.

### Exercise 6. Must Non-Unique Indexes Include event_date?

**Answer:** No. `CREATE INDEX ON parent(event_id)` is valid.

### Exercise 7. Does Querying Only event_id Prune RANGE(event_date)?

**Answer:** No. Without a date filter, PostgreSQL cannot tell which month holds that `event_id` in this schema.

### Exercise 8. Which Mechanisms Apply When Filtering February and Tenant 7?

**Answer:** Partition pruning eliminates January and March; inside February, the planner picks an index scan or Seq Scan based on cost.

### Exercise 9. Create a Local Index for February Only

```sql
CREATE INDEX idx_part298_events_feb_event_type_lab
ON part298.events_2026_02(event_type);
```

**Answer:** Serves February only and does not apply to other months.

### Exercise 10. How Does a Parent Partial Index Work?

**Answer:** Creates matching partial indexes across children; queries must imply the index predicate for the planner to use it. It never turns a partial unique index lacking the partition key into a global unique constraint.

### Exercise 11. Is INCLUDE(event_type) a B-Tree Search Key?

**Answer:** No. `INCLUDE` holds payload columns for covering reads, not search keys or unique key columns.

### Exercise 12. Why Can Index Only Scan Still Have Heap Fetches?

**Answer:** PostgreSQL must check MVCC visibility on heap pages not yet marked all-visible.

### Exercise 13. Can You Run CREATE INDEX CONCURRENTLY Directly on a Partitioned Parent?

**Answer:** Not across the whole tree directly; create `ON ONLY` on the parent, build concurrent indexes per child, and `ATTACH` them.

### Exercise 14. Why Is an ON ONLY Parent Index Initially Invalid?

**Answer:** Child indexes have not been built/attached yet, so the partitioned index definition is incomplete.

### Exercise 15. When Does an ON ONLY Parent Index Become Valid?

**Answer:** Once all required matching child partition indexes are attached and valid.

### Exercise 16. What If One Child's CONCURRENTLY Build Fails?

**Answer:** Check the child index state and rebuild/clean up per runbook; never attach an invalid index or treat the build as done.

### Exercise 17. Write a Valid FK Referencing the Composite PK on events

```sql
FOREIGN KEY (event_date, event_id)
REFERENCES part298.events(event_date, event_id)
```

**Answer:** Matches the parent PK.

### Exercise 18. Why Is FK(event_id) Alone Invalid in This Schema?

**Answer:** The parent lacks a unique key on `event_id` alone.

### Exercise 19. Which Key Does ON CONFLICT Target?

```sql
ON CONFLICT (event_date, event_id)
DO NOTHING
```

**Answer:** The composite key protected by the PK, not `event_id` alone.

### Exercise 20. If PK(event_id) Is Mandatory, How Should Partitioning Change?

**Answer:** One option is `HASH(event_id)` with `PK(event_id)` and full hash partitions, weighing the trade-off of losing date-based partition purging.

### Exercise 21. What Does an ID Registry Guarantee?

**Answer:** A registry with `PK(event_id)` prevents duplicate IDs in the registry; requiring every event writer to register IDs in the same transaction extends that protection to `events`.

### Exercise 22. Does UUID Eliminate the Need for a UNIQUE Constraint?

**Answer:** No if business rules demand strict database enforcement. UUIDs offer very low collision probability, not a cross-partition `UNIQUE` constraint.

### Exercise 23. Can Tenants 7 and 8 Share the Same order_id Under PK(tenant_id,order_id)?

**Answer:** Yes, because `tenant_id` is part of the PK. This enforces per-tenant uniqueness, not global `order_id` uniqueness.

### Exercise 24. What Must UNIQUE Check Under Multi-Level Partitioning?

**Answer:** All partition key columns from all involved levels must be included per PostgreSQL's enforcement rules across the tree.

### Exercise 25. How Does UNIQUE with NULL Differ from PK?

**Answer:** PK forbids `NULL`; `UNIQUE` has distinct `NULL` semantics and optionally `NULLS NOT DISTINCT` depending on version. Neither bypasses partition-key inclusion rules.

### Exercise 26. Can April Rows Insert into the Current Fixture?

**Answer:** No—without an April partition or `DEFAULT`, inserts fail. Pre-create the new partition.

### Exercise 27. Inspect Partitions via SQL

```sql
SELECT relid::regclass, parentrelid::regclass, isleaf
FROM pg_partition_tree('part298.events'::regclass);
```

**Answer:** Displays the partition tree and leaf flags.

### Exercise 28. Check Parent Index Validity

```sql
SELECT i.indisvalid
FROM pg_index AS i
WHERE i.indexrelid =
  'part298.idx_part298_measurements_device_time'::regclass;
```

**Answer:** Expected true once all child indexes are attached.

### Exercise 29. Write a Query to Detect Duplicate event_id Across events

```sql
SELECT event_id, COUNT(*) AS n
FROM part298.events
GROUP BY event_id
HAVING COUNT(*) > 1
ORDER BY event_id;
```

**Answer:** **Detects** existing duplicates; it does not prevent concurrent transactions from creating duplicates.

### Exercise 30. Why Not Use a CHECK Constraint to Block Cross-Partition Duplicates?

**Answer:** `CHECK` is not a cross-row uniqueness mechanism, and custom `SELECT COUNT` checks are vulnerable to concurrency races without proper locking/constraints.

### Exercise 31. Can You Drop a Child-Only Local Index Without Affecting the Parent?

**Answer:** If it is a standalone unattached index not backing any constraint, yes, subject to privileges and DDL. If attached to a parent index or backing a constraint, dependencies forbid casual dropping.

### Exercise 32. Why Might a Low-Scan Index Not Be Redundant?

**Answer:** It may enforce `UNIQUE`/`PK`/`FK` checks, serve rare queries, or reflect a short observation window; check constraints, dependencies, and workload before dropping.

## 38. Pre-Production Checklist for Partitioned Tables

| Question | Reason |
|---|---|
| Is the partition key a column or expression? | Determines parent `UNIQUE`/`PK` feasibility |
| Which keys do subpartition levels use? | `UNIQUE` may need keys from multiple levels |
| Does business require ID uniqueness per day, tenant, or globally? | Guides schema choice |
| Does adding the partition key change existing PK semantics? | Prevents cross-partition ID duplicates |
| Do external FKs carry the full composite key? | Preserves referential integrity |
| Do ID-lookup APIs supply the partition key? | Avoids scanning every partition |
| Do hot queries include prunable predicates? | Minimizes partitions read |
| Which columns and order do non-unique indexes need? | Optimizes intra-partition scans |
| How are parent vs. local-only indexes governed? | Prevents missing or duplicate indexes |
| Are partial predicates or `INCLUDE` helpful? | Matches workload without bloated indexes |
| Is per-partition `CONCURRENTLY` indexing needed? | Minimizes DML blocking |
| Is the parent index `indisvalid=TRUE`? | Confirms build/`ATTACH` completion |
| Are failed/invalid index builds handled? | Avoids half-finished migrations |
| What validation scans/locks do partition creates/attaches incur? | Aids production scheduling |
| Is future partition pre-creation automated? | Prevents missing-partition `INSERT` errors |
| Can `DEFAULT` hold rows needing migration before opening new partitions? | Prevents overlap/attach failures |
| Does `ON CONFLICT` use the exact composite arbiter? | Prevents invalid upserts |
| Do partition-key `UPDATE`s trigger row movement? | Clarifies DML limits |
| Does any ID registry use an atomic write protocol? | Protects global uniqueness |
| Have concurrent inserts of the same ID been tested? | Exposes race conditions |
| Does retention impact FKs, registries, or backups? | Preserves cross-table consistency |
| Are index sizes, usage, and maintenance tracked per child? | Sustains long-term operations |

## 39. Official PostgreSQL Documentation

Cross-check against your running PostgreSQL version, as partitioned-table syntax and capabilities evolve across releases:

- [Table Partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html): partition routing, indexes, unique/primary keys, and partitioned table limits.
- [CREATE TABLE](https://www.postgresql.org/docs/current/sql-createtable.html): `PARTITION BY`, `PARTITION OF`, and constraints.
- [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html): index methods, `INCLUDE`, `UNIQUE`, and `CONCURRENTLY`.
- [ALTER INDEX](https://www.postgresql.org/docs/current/sql-alterindex.html): `ATTACH PARTITION` for indexes.
- [ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html): `ATTACH`/`DETACH PARTITION` and constraints.
- [Partition Pruning](https://www.postgresql.org/docs/current/ddl-partitioning.html#DDL-PARTITION-PRUNING): skipping irrelevant partitions.
- [Indexes](https://www.postgresql.org/docs/current/indexes.html): index selection, multicolumn, partial, and index-only scans.
- [Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): `UNIQUE`, `PRIMARY KEY`, `FK`, `CHECK`, and constraint semantics.
- [INSERT](https://www.postgresql.org/docs/current/sql-insert.html): `ON CONFLICT` and upsert limitations.
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): reading plans, pruning, and index scans.

Verify versions:

```sql
SHOW server_version;
SHOW transaction_isolation;
```

These examples are for study; do not treat them as benchmark results on a specific host or a pre-validated production migration.

## 40. Summary

For PostgreSQL declarative partitioning, keep four principles in mind:

### 40.1. Parent Indexes Are Logical; Child Indexes Are Physical

```text
events parent
   |
   +-- partitioned parent index
          |
          +-- Jan local index
          +-- Feb local index
          +-- Mar local index
```

A parent index does not become a single global B-tree covering all months.

### 40.2. UNIQUE/PK Must Include the Partition Key

```text
PARTITION BY RANGE(event_date)

PRIMARY KEY(event_id)             -> Invalid on parent
PRIMARY KEY(event_date,event_id)  -> Valid
```

However:

```text
UNIQUE(event_date,event_id)
    does not mean UNIQUE(event_id)
```

### 40.3. Partition Pruning and Local Indexes Are Two Separate Layers

```text
WHERE event_date = ...
    -> prunes down to matching partition(s)

WHERE tenant_id = ...
    -> uses local indexes across multiple partitions

WHERE event_id = ...
    -> without date, may probe every month
```

### 40.4. Global IDs Require an Architectural Decision

Core options:

- Partition by `event_id` itself so parent `PK(event_id)` can be enforced.
- Adopt composite identity `(event_date,event_id)` and update FKs/APIs accordingly.
- Use an unpartitioned ID registry with a unique constraint and atomic write protocol.
- Use sequences/UUIDs for ID generation without mistaking them for global `UNIQUE` enforcement.

### Key Principles to Remember

1. **Choose the partition key considering both query access and business constraints.**
2. **Parent `UNIQUE` and `PRIMARY KEY` must include all relevant partition key columns**; expression partition keys carry further restrictions.
3. **Per-partition unique indexes do not prove global uniqueness** on non-partition columns.
4. **Foreign keys and `ON CONFLICT` must target truly unique keys.**
5. **Non-unique indexes do not share the strict key requirement**, though query plans still rely on partition pruning.
6. **Direct `CREATE INDEX CONCURRENTLY` on a parent is restricted**; build per child and `ATTACH` into an `ON ONLY` parent index.
7. **Adding new partitions must align with index/constraint policies and validity checks.**
8. **A large table does not automatically become faster once partitioned**; many partitions/indexes add planning and operational cost.
9. **`CHECK`, sequences, UUIDs, and `SELECT NOT EXISTS` do not replace global `UNIQUE` constraints** under concurrent writes.
10. **Verify with catalogs, `EXPLAIN`, and concurrency tests** before modifying production.

**One sentence to remember:** PostgreSQL partitions data into physical tables with separate indexes; to enforce uniqueness at the parent level, **the unique key must align with partition routing**, or else you must change your identity model or build a separate global uniqueness mechanism.
