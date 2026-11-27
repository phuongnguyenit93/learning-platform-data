# RANGE, LIST, and HASH Partitioning in PostgreSQL

## 1. Why Partition a Table?

Suppose a system collects **500 million events** over several years. Operations routinely query events from the last 7 days and must delete data older than 12 months. If all events live in a single massive heap table, the following tasks can become expensive:

- Daily queries must inspect a huge volume of data and indexes.
- Row-by-row deletion of old data generates heavy WAL, dead tuples, and `VACUUM` work.
- Certain indexes grow huge, becoming hard to rebuild or maintain.
- Changing storage or backup policies for old data requires acting on the whole table.
- Table-wide statistics can mask differences across periods or groups.

**Partitioning** lets you manage one **logical table** composed of multiple **physical child tables** (*partitions*), based on a **partition key** value. Applications can continue querying the parent table as a single table; PostgreSQL routes rows to partitions and can **skip irrelevant partitions** when query predicates are clear enough.

PostgreSQL supports three core **declarative partitioning** strategies:

1. **RANGE:** splits by intervals of values, such as each month of `event_at`.
2. **LIST:** splits by discrete sets of values, such as `region IN ('north', 'central')`.
3. **HASH:** splits by a hash value of the key, such as distributing `customer_id` across multiple buckets.

### 1.1. Learning Objectives

After this lesson, you will be able to:

- Choose RANGE, LIST, or HASH based on workload and data management needs.
- Create a parent table with `PARTITION BY` and child partitions with `PARTITION OF` in SQL.
- Correctly explain RANGE **[lower, upper)** bounds, LIST value sets and `NULL`, and HASH `MODULUS`/`REMAINDER`.
- Observe which partition a row is routed to via `tableoid::regclass`.
- Read `EXPLAIN` plans to identify **partition pruning** and cases where pruning does not occur.
- Handle primary keys, `UNIQUE`, `FOREIGN KEY`, indexes, constraints, and partition key updates.
- Perform `ATTACH PARTITION`, `DETACH PARTITION`, and manage the partition lifecycle.
- Understand limitations of `DEFAULT` partitions, changing HASH partition counts, and multi-level partitioning.
- Monitor statistics, autovacuum, partition counts, resources, and production impact.
- Complete hands-on exercises, analyze scenarios, and choose appropriate approaches.

> **Environment note:** Examples target modern PostgreSQL with declarative partitioning. Details of concurrent indexing, foreign keys, pruning, partitioned indexes, and certain DDL commands may vary by version. Verify against your target version when deploying to production. Only run hands-on steps on a test database/schema you control; specifically, never `DROP`/`TRUNCATE`/`DETACH` real production data to experiment.

---

## 2. What Does a Partitioned Table Consist Of?

A simple RANGE model:

~~~text
                 Logical table: events
               PARTITION BY RANGE(event_at)
                          |
          +---------------+-----------------+
          |               |                 |
          v               v                 v
  events_2026_10    events_2026_11    events_2026_12
  [Oct 1, Nov 1)    [Nov 1, Dec 1)    [Dec 1, Jan 1)
       data              data              data
     + index           + index           + index
~~~

The **partitioned parent table** describes the logical schema and partitioning rules. In declarative partitioning, the parent itself has `relkind = 'p'` and **does not store ordinary data rows** in a parent heap; data resides in the **leaf partitions**.

Key concepts:

| Concept | Description |
|---|---|
| **Partitioned table / parent** | Logical table with a `PARTITION BY` definition; querying the parent normally reads data across its partitions |
| **Partition key** | Column or expression determining the routing path |
| **Partition bound** | RANGE/LIST/HASH specification determining which values each child accepts |
| **Partition / child** | A relation storing data, or an intermediate partitioned table |
| **Leaf partition** | A terminal child storing physical rows |
| **Default partition** | A partition catching values not matching any defined partition, for RANGE/LIST |
| **Partition pruning** | Skipping partitions proven unable to hold rows matching a query |
| **Partition-wise join/aggregate** | Conditional optimizations for joining/aggregating partition by partition |

### 2.1. Partitioning Is Not Sharding

Regular partitions still live within **the same PostgreSQL database/cluster**, sharing transactions, WAL, planner, and administration. Partitioning **does not automatically distribute a table across multiple machines** or scale total CPU/RAM capacity like multi-node sharding.

A partition can be placed in a separate tablespace by configuration, but that does not turn the system into a distributed database.

### 2.2. Partitioning Does Not Automatically Make Every Query Faster

If a query:

~~~sql
SELECT COUNT(*)
FROM partition_lab.events;
~~~

has no filter, PostgreSQL still has to aggregate across the relevant partitions. Having 48 partitions instead of one table does not eliminate the need to process every row.

Meaningful benefits usually arise when:

- Queries have **predicates aligned with the partition key** enabling pruning.
- Old partitions can be **DETACHed/DROPped** under a retention policy.
- Maintenance, indexing, or storage tasks can be performed per partition.
- Eligible partition-wise operations apply.
- Each partition's size and the total partition count are well chosen.

### 2.3. Choosing a Partition Key Has Long-Term Impact

The partition key affects more than routing. It governs:

- Query pruning effectiveness.
- Primary key / `UNIQUE` constraints on the parent table.
- How `UPDATE`s move rows between partitions.
- Index creation, statistics, and lifecycle management costs.
- Whether partitions can be added or removed without downtime.
- How many partitions a query must inspect.

Therefore, partitioning is a **data design and operational** decision, not an arbitrary `CREATE TABLE` clause.

---

## 3. Comparing the Three Strategies Before Writing SQL

| Criterion | RANGE | LIST | HASH |
|---|---|---|---|
| Splitting rule | Ordered intervals | Discrete sets of values | Hash function result by modulus/remainder |
| Example keys | `event_at`, `order_date`, `account_id` ranges | `region`, `country_code`, `status` | `customer_id`, `tenant_id` |
| Strengths | Range pruning; time-based retention management | Per-group policies for well-defined identities | Spreads many key values across buckets fairly evenly when appropriate |
| Well-suited queries | `event_at >= ... AND event_at < ...` | `region='north'`, `region IN (...)` | `customer_id=42` |
| Time-range queries | Usually very suitable if key is time | No inherent benefit if key is region | No inherent benefit if key is customer |
| Managing old data | Very convenient when partitioned by time | Convenient per specific group | Usually unsuitable for time-based retention |
| Increasing partition count | Adding new ranges is relatively straightforward if planned ahead | Adding/moving groups requires checking DEFAULT/data | Rebalancing is usually nontrivial once bucket coverage is full |
| DEFAULT partition | Supported | Supported | Not supported |
| NULL key | `DEFAULT` can accept `NULL`; RANGE bounds do not list `NULL` | Can define `FOR VALUES IN (NULL)` or use `DEFAULT` | `NULL` has hash routing semantics without relying on `DEFAULT` |
| Design risks | Timezone drift, missing new month's partition | Tiny/skewed groups, case sensitivity | Skew by hash key, bucket expansion, queries missing the key |
| Actual distribution | Follows data volume per interval | Follows row count per value/group | Follows distinct key distribution and hash, not guaranteed equal across 4 partitions |

**Quick rule of thumb:** monthly logs → RANGE; data with per-country policies → LIST; access primarily single-tenant by `tenant_id` aiming to split storage across buckets → HASH.

---

## 4. Declarative Partitioning Syntax Overview

### 4.1. Creating the Parent Table

~~~sql
CREATE TABLE schema_name.parent_table (
    id BIGINT NOT NULL,
    partition_key SOME_TYPE NOT NULL,
    payload TEXT
)
PARTITION BY RANGE (partition_key);
~~~

Similarly:

~~~sql
PARTITION BY LIST (partition_key)
~~~

or:

~~~sql
PARTITION BY HASH (partition_key)
~~~

### 4.2. Creating Partitions

RANGE:

~~~sql
CREATE TABLE schema_name.parent_2026_11
PARTITION OF schema_name.parent_table
FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');
~~~

LIST:

~~~sql
CREATE TABLE schema_name.parent_north
PARTITION OF schema_name.parent_table
FOR VALUES IN ('north', 'northern');
~~~

HASH:

~~~sql
CREATE TABLE schema_name.parent_h0
PARTITION OF schema_name.parent_table
FOR VALUES WITH (MODULUS 4, REMAINDER 0);
~~~

These three snippets merely show **syntax patterns**; do not run them sequentially against the same parent because `PARTITION BY` is fixed per parent table.

### 4.3. Routing on INSERT

~~~sql
INSERT INTO schema_name.parent_table (...)
VALUES (...);
~~~

PostgreSQL routes each row to the child with matching bounds. If no partition accepts the value and no `DEFAULT` exists, `INSERT` **raises an error**—it does not auto-create partitions.

### 4.4. Querying the Parent vs. Querying a Partition

~~~sql
SELECT * FROM schema_name.parent_table;
~~~

normally reads data across partitions according to the chosen plan.

~~~sql
SELECT * FROM schema_name.parent_2026_11;
~~~

reads only one specific partition. In most applications, query the **parent** to avoid hardcoding time-based partition names, and let the planner prune.

---

## 5. Creating a Safe Lab Schema

The following examples use a dedicated schema:

~~~sql
CREATE SCHEMA IF NOT EXISTS partition_lab;
~~~

Run these on a test database. Several `CREATE` statements use fixed object names; **do not re-run them in the same schema once created**, or use a fresh lab database/schema if starting over.

Dates in the examples are fixed illustrative milestones; they do not need to match the current system clock.

---

## 6. RANGE: Partitioning an Events Table by Month

### 6.1. Create a Time-Keyed Parent

~~~sql
CREATE TABLE partition_lab.events (
    event_id BIGINT NOT NULL,
    event_at TIMESTAMPTZ NOT NULL,
    tenant_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (event_at, event_id)
)
PARTITION BY RANGE (event_at);
~~~

Explanation:

- `event_at` is the partition key.
- `TIMESTAMPTZ` stores an absolute instant in time, supporting timezone conversion on input/output.
- `event_id` is supplied by the application or an ID service in this example.
- The primary key includes **`event_at` and `event_id`**; this relates to `UNIQUE` constraints on partitioned tables, explained later.
- The parent is a logical table and has no leaf partitions yet to hold data.

### 6.2. Create Three Monthly Partitions

~~~sql
CREATE TABLE partition_lab.events_2026_10
PARTITION OF partition_lab.events
FOR VALUES FROM ('2026-10-01 00:00:00+00')
           TO   ('2026-11-01 00:00:00+00');

CREATE TABLE partition_lab.events_2026_11
PARTITION OF partition_lab.events
FOR VALUES FROM ('2026-11-01 00:00:00+00')
           TO   ('2026-12-01 00:00:00+00');

CREATE TABLE partition_lab.events_2026_12
PARTITION OF partition_lab.events
FOR VALUES FROM ('2026-12-01 00:00:00+00')
           TO   ('2027-01-01 00:00:00+00');
~~~

October accepts timestamps from the start of 2026-10-01 up to **before** the start of 2026-11-01; November works similarly.

### 6.3. Create a DEFAULT Partition

~~~sql
CREATE TABLE partition_lab.events_other
PARTITION OF partition_lab.events
DEFAULT;
~~~

`DEFAULT` catches data outside the defined RANGE bounds, such as 2027-01 or 2026-09. It is a **fallback safety net**, and must not become a "catch-all dumping ground" holding hundreds of millions of rows because someone forgot to create the new month's partition.

### 6.4. Load Data Through the Parent Table

~~~sql
INSERT INTO partition_lab.events
    (event_id, event_at, tenant_id, event_type, payload)
VALUES
    (1001, '2026-10-31 23:59:59+00', 11, 'view', '{"page":"home"}'),
    (1002, '2026-11-01 00:00:00+00', 11, 'login', '{"device":"mobile"}'),
    (1003, '2026-11-15 08:30:00+00', 12, 'purchase', '{"amount":150}'),
    (1004, '2026-12-01 00:00:00+00', 13, 'logout', '{}'),
    (1005, '2027-01-05 10:00:00+00', 11, 'login', '{}');
~~~

The JSON strings are implicitly cast to the `JSONB` column on `INSERT`. If your environment/tool prefers explicit casts, write `'{"page":"home"}'::jsonb`.

### 6.5. Verify Routing via tableoid

~~~sql
SELECT
    event_id,
    event_at,
    tenant_id,
    event_type,
    tableoid::regclass AS physical_partition
FROM partition_lab.events
ORDER BY event_at, event_id;
~~~

Expected result:

| event_id | Partition |
|---:|---|
| 1001 | `partition_lab.events_2026_10` |
| 1002 | `partition_lab.events_2026_11` |
| 1003 | `partition_lab.events_2026_11` |
| 1004 | `partition_lab.events_2026_12` |
| 1005 | `partition_lab.events_other` |

`tableoid` reveals the OID of the physical relation actually storing the row. The `regclass` text representation may be shortened depending on `search_path`, so never rely on its formatted string as an application key.

### 6.6. The Parent Stores No Heap Rows

~~~sql
SELECT COUNT(*) AS all_rows
FROM partition_lab.events;
~~~

Expected: 5 if loaded once.

~~~sql
SELECT COUNT(*) AS only_parent_rows
FROM ONLY partition_lab.events;
~~~

Expected: 0 because a declarative partitioned parent stores no regular tuples. `ONLY` prevents descending into child partitions; it is not a trick for clearing data.

---

## 7. RANGE: Understanding Bounds and Special Values

### 7.1. Inclusive Lower Bound, Exclusive Upper Bound

RANGE follows the rule:

\[
\text{lower} \le x < \text{upper}
\]

For example:

~~~text
Partition October: [2026-10-01 00:00+00, 2026-11-01 00:00+00)
Partition November:[2026-11-01 00:00+00, 2026-12-01 00:00+00)
~~~

The instant **2026-11-01 00:00 UTC** belongs to November, not October. Adjacent partitions sit cleanly side by side without **overlapping**.

### 7.2. Do Not Use "23:59:59.999999" as an Upper Bound

Poor design pattern:

~~~text
October: FROM 2026-10-01 TO 2026-10-31 23:59:59
November: FROM 2026-11-01 TO ...
~~~

This creates a **gap** for fractional seconds right before the boundary. Always use the **start of the next month** as the upper bound. PostgreSQL excludes the upper endpoint automatically.

### 7.3. MINVALUE and MAXVALUE

RANGE can use special bound values:

~~~sql
CREATE TABLE partition_lab.range_demo (
    id BIGINT NOT NULL,
    score INTEGER
) PARTITION BY RANGE (score);

CREATE TABLE partition_lab.range_demo_low
PARTITION OF partition_lab.range_demo
FOR VALUES FROM (MINVALUE) TO (0);

CREATE TABLE partition_lab.range_demo_mid
PARTITION OF partition_lab.range_demo
FOR VALUES FROM (0) TO (100);

CREATE TABLE partition_lab.range_demo_high
PARTITION OF partition_lab.range_demo
FOR VALUES FROM (100) TO (MAXVALUE);
~~~

`MINVALUE`/`MAXVALUE` are **partition bound** markers, not `INTEGER` values that applications insert. For `score=NULL` without a `DEFAULT`, **RANGE has no partition accepting `NULL` automatically**.

### 7.4. DEFAULT Does Not Prove Data Matches Expected Domains

If `DEFAULT` catches everything outside three months, rows from the year 2001 or 2100 can still be inserted if other constraints allow them. `DEFAULT` prevents missing-partition errors, yet can mask input bugs or stopped partition-creation jobs.

Monitor row counts in `DEFAULT`:

~~~sql
SELECT COUNT(*) AS default_rows
FROM partition_lab.events_other;
~~~

### 7.5. Multi-Column RANGE Is Lexicographical

PostgreSQL can partition on multiple columns:

~~~sql
CREATE TABLE partition_lab.range_composite_demo (
    tenant_id INTEGER NOT NULL,
    seq_no INTEGER NOT NULL,
    note TEXT
)
PARTITION BY RANGE (tenant_id, seq_no);
~~~

With a two-column key, bound comparisons are **lexicographical**, not "both `tenant_id` in range A and `seq_no` in range B" as independent intervals.

For example, a partition:

~~~sql
CREATE TABLE partition_lab.range_composite_1
PARTITION OF partition_lab.range_composite_demo
FOR VALUES FROM (1, 0) TO (2, 0);
~~~

accepts keys like `(1,0)` and `(1,999)`, but rejects `(2,0)`. It is not a "rectangle" of `tenant_id` 1 to 2 and `seq_no` 0 to 0.

Do not use multi-column RANGE as a substitute for **multi-level subpartitioning** if your requirement genuinely needs independent splitting by time and tenant.

---

## 8. Pruning with RANGE: Why Queries Need Compatible Predicates

### 8.1. Half-Open Range Queries

~~~sql
EXPLAIN
SELECT event_id, event_at, tenant_id
FROM partition_lab.events
WHERE event_at >= TIMESTAMPTZ '2026-11-10 00:00:00+00'
  AND event_at <  TIMESTAMPTZ '2026-11-20 00:00:00+00';
~~~

With accurate partition metadata, the planner can exclude October, December, and `DEFAULT` from data access because **only November can hold matching rows**.

An illustrative plan:

~~~text
Seq Scan on events_2026_11
  Filter: (event_at >= ... AND event_at < ...)
~~~

With only five rows in the table, PostgreSQL may pick a Seq Scan on the right partition—this **does not mean partitioning failed**. Pruning and choosing **index scan vs. seq scan inside a partition** are separate decisions.

### 8.2. Queries Without the Key

~~~sql
EXPLAIN
SELECT *
FROM partition_lab.events
WHERE tenant_id = 11;
~~~

Because the parent is partitioned by `event_at`, PostgreSQL cannot tell from `tenant_id=11` alone which month holds the events. The plan may use `Append` over the partitions, with each child using its local index if one exists.

### 8.3. Difference Between Partition Pruning and Index Filtering

- **Partition pruning:** skips entire child relations that cannot contain matching rows.
- **Index filtering:** inside each remaining relation, uses an index to locate matching rows/pages.
- **Row filter:** the executor checks predicates on retrieved candidate rows.

An optimal query can **both prune partitions and use a local index**. Do not conflate the two mechanisms.

### 8.4. Checking How Many Partitions Actually Run

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM partition_lab.events
WHERE event_at >= TIMESTAMPTZ '2026-11-01 00:00:00+00'
  AND event_at <  TIMESTAMPTZ '2026-12-01 00:00:00+00';
~~~

Look at which child nodes actually execute, `Subplans Removed` if present, and `never executed` for branches eliminated at runtime. Output varies by PostgreSQL version, predicate complexity, prepared parameters, and plan type.

---

## 9. RANGE and Time: Timezone Is Part of the Design

### 9.1. TIMESTAMPTZ Stores an Instant, Not a "Wall-Clock String + Original Timezone"

In PostgreSQL, `TIMESTAMPTZ` represents an **instant**. Its formatted display can vary by session timezone:

~~~sql
SHOW TimeZone;

SELECT
    TIMESTAMPTZ '2026-11-01 00:00:00+00'
        AS utc_instant;
~~~

If a session displays in `Asia/Ho_Chi_Minh` (+07 in this example), the same instant renders as **07:00 on Nov 01**. Routing depends on the **instant value** and bounds, not the formatted UI string.

### 9.2. UTC Day Partitions Differ from Local Days

An event at `2026-10-31 20:00:00+00` is the morning of Nov 01 in Vietnam time, yet it falls in the **October UTC partition** if bounds are defined in UTC.

If business logic requires "each partition is a local calendar day," **design partition keys/bounds according to local-day rules** and watch out for daylight saving time (DST) where applicable. Never assume `date(event_at)` in a session's timezone always matches a UTC partition month.

### 9.3. Timezone Queries Should Derive Bounds on the Partition Key

For example, a query truly targeting Nov 01 in `Asia/Ho_Chi_Minh`:

~~~sql
SELECT event_id, event_at
FROM partition_lab.events
WHERE event_at >= TIMESTAMP '2026-11-01 00:00:00'
                      AT TIME ZONE 'Asia/Ho_Chi_Minh'
  AND event_at <  TIMESTAMP '2026-11-02 00:00:00'
                      AT TIME ZONE 'Asia/Ho_Chi_Minh';
~~~

This converts **both endpoints** to the same type as `event_at` so PostgreSQL has a chance to prune via RANGE. In regions with DST, compute **both local-day boundaries explicitly** like this rather than blindly adding 24 hours.

### 9.4. Wrapping the Partition Key in a Function Can Inhibit Pruning

~~~sql
-- Must inspect the plan; do not assume equivalent pruning capability:
WHERE date_trunc('month', event_at) =
      TIMESTAMPTZ '2026-11-01 00:00:00+00'
~~~

Depending on timezone definitions, the expression's semantics may also differ. If the parent is partitioned directly on `event_at`, a half-open range condition on the raw key is generally clearer for pruning.

---

## 10. LIST: Partitioning by Value Groups

### 10.1. Create a Regional Support Tickets Table

~~~sql
CREATE TABLE partition_lab.support_tickets (
    ticket_id BIGINT NOT NULL,
    region TEXT,
    subject TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
PARTITION BY LIST (region);
~~~

Note: in this example `region` allows `NULL` to illustrate how LIST routes `NULL`. Without a primary key, duplicate `ticket_id` values can exist across partitions unless controlled by the application; the constraints section explains how to handle this.

### 10.2. Specific Value Groups

~~~sql
CREATE TABLE partition_lab.support_tickets_north
PARTITION OF partition_lab.support_tickets
FOR VALUES IN ('north', 'northern');

CREATE TABLE partition_lab.support_tickets_south
PARTITION OF partition_lab.support_tickets
FOR VALUES IN ('south');

CREATE TABLE partition_lab.support_tickets_null
PARTITION OF partition_lab.support_tickets
FOR VALUES IN (NULL);

CREATE TABLE partition_lab.support_tickets_other
PARTITION OF partition_lab.support_tickets
DEFAULT;
~~~

- Both `'north'` and `'northern'` route to the north partition.
- `'south'` routes to the south partition.
- `NULL` routes to the dedicated null partition.
- Remaining values such as `'west'` route to `DEFAULT`.

LIST value sets cannot overlap under the same parent. You cannot create another partition that also accepts `'north'`.

### 10.3. Load Data

~~~sql
INSERT INTO partition_lab.support_tickets
    (ticket_id, region, subject)
VALUES
    (1, 'north', 'App fails to log in'),
    (2, 'northern', 'Data entry error'),
    (3, 'south', 'Report request'),
    (4, 'west', 'Account support'),
    (5, NULL, 'Unspecified region');

SELECT
    ticket_id, region, subject,
    tableoid::regclass AS physical_partition
FROM partition_lab.support_tickets
ORDER BY ticket_id;
~~~

The tickets should land in north, north, south, other, and null respectively.

### 10.4. LIST Does Not Automatically Normalize Case

`'north'` and `'North'` are distinct values under `text` and typical collations; do not assume PostgreSQL automatically runs `lower(region)` before routing.

If the system needs case-insensitivity, you can:

- Normalize values in the application.
- Use a separate normalized column as the partition key.
- Consider an expression partition key `PARTITION BY LIST ((lower(region)))` when appropriate, while understanding `UNIQUE`/`PK` limitations on expression keys.

Never alter production data semantics implicitly.

### 10.5. LIST Takes a Single Partition Key

In declarative LIST partitioning, the partition key is limited to **one column or one expression** per level. To partition by country and then channel, use **subpartitioning**; do not write `PARTITION BY LIST(country, channel)` expecting arbitrary pair groups like multi-column RANGE.

---

## 11. LIST Pruning and Queries

### 11.1. Find Tickets by Region

~~~sql
EXPLAIN
SELECT ticket_id, subject
FROM partition_lab.support_tickets
WHERE region = 'north';
~~~

The planner can prune partitions that do not include `'north'`, reading only the north partition.

### 11.2. Query Multiple Regions

~~~sql
EXPLAIN
SELECT ticket_id, region, subject
FROM partition_lab.support_tickets
WHERE region IN ('north', 'south');
~~~

Can read north and south while skipping other partitions if the planner can deduce it.

### 11.3. Query NULL

~~~sql
EXPLAIN
SELECT ticket_id, subject
FROM partition_lab.support_tickets
WHERE region IS NULL;
~~~

Because a dedicated null partition exists, PostgreSQL can read just that partition. **`region = NULL` is not a valid SQL filter**; equality against `NULL` yields `UNKNOWN`, so always use `IS NULL`.

### 11.4. Query Without Region

~~~sql
EXPLAIN
SELECT COUNT(*)
FROM partition_lab.support_tickets
WHERE created_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00';
~~~

The parent is partitioned by `region`, not `created_at`, so a time filter alone normally cannot prune by region. You may need a time index on each partition, or reconsider the partitioning strategy if time-based queries dominate.

### 11.5. When Is LIST Reasonable?

- Group identities rarely change and require separate management.
- Data policies differ by region, country, or category.
- Many queries filter on one or a few groups.
- You want separate tablespaces, maintenance, or storage per group.
- You can monitor `DEFAULT` and handle newly introduced group values.

Do not choose LIST on `status` if statuses change constantly and every update moves rows across partitions, unless there is a compelling operational justification.

---

## 12. LIST: NULL, DEFAULT, New Groups, and Skew

### 12.1. NULL Is a Special Partitioning Value in LIST

A LIST partition can declare `FOR VALUES IN (NULL)`. If no dedicated `NULL` partition exists but `DEFAULT` does, `NULL` routes to `DEFAULT`. If neither exists, inserting `NULL` **finds no matching partition**.

This differs from `RANGE`, where ordered bounds do not accept `NULL` directly.

### 12.2. DEFAULT Also Catches Multiple Unlisted Values

In the lab, `'west'` landed in `support_tickets_other`. If `'east'` and `'central'` arrive tomorrow, they will also land in `DEFAULT` until dedicated partitions exist.

Query:

~~~sql
SELECT region, COUNT(*) AS ticket_count
FROM partition_lab.support_tickets_other
GROUP BY region
ORDER BY ticket_count DESC;
~~~

helps reveal which groups `DEFAULT` is accumulating. Never treat successful `INSERT`s as proof that the partition lifecycle is working properly.

### 12.3. Adding a New Partition When DEFAULT Already Holds Matching Data

If `DEFAULT` already holds `region='west'`, running:

~~~sql
-- Illustrates risk; must migrate DEFAULT data first:
CREATE TABLE partition_lab.support_tickets_west
PARTITION OF partition_lab.support_tickets
FOR VALUES IN ('west');
~~~

cannot simply be run straight away. PostgreSQL must ensure `DEFAULT` contains no rows matching the new partition's domain; if matching rows exist, creation/attachment will **fail** until the data is moved and safety checks pass.

Never just `DELETE` from `DEFAULT` to make DDL succeed: plan **row migration**, concurrent write handling, and rollback.

### 12.4. Skew in LIST

If 95% of tickets belong to `'north'`, the north partition becomes huge while `'south'` stays tiny. LIST does not balance row counts; it enforces **exact group membership**.

You can subpartition `'north'` by date/hash if genuinely needed and justified by the workload; avoid creating hundreds of partitions for rare values once the count becomes unmanageable.

---

## 13. HASH: Partitioning by Key Hash

### 13.1. Create a HASH Parent on customer_id

~~~sql
CREATE TABLE partition_lab.orders_hash (
    order_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    amount NUMERIC(12,2) NOT NULL CHECK (amount >= 0),
    placed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (customer_id, order_id)
)
PARTITION BY HASH (customer_id);
~~~

The primary key includes `customer_id` because it is the partition key. To guarantee `order_id` is unique **system-wide**, the application needs an appropriate ID generation/enforcement strategy; `PRIMARY KEY(customer_id,order_id)` only guarantees uniqueness of the pair.

### 13.2. Create Four Buckets

~~~sql
CREATE TABLE partition_lab.orders_hash_h0
PARTITION OF partition_lab.orders_hash
FOR VALUES WITH (MODULUS 4, REMAINDER 0);

CREATE TABLE partition_lab.orders_hash_h1
PARTITION OF partition_lab.orders_hash
FOR VALUES WITH (MODULUS 4, REMAINDER 1);

CREATE TABLE partition_lab.orders_hash_h2
PARTITION OF partition_lab.orders_hash
FOR VALUES WITH (MODULUS 4, REMAINDER 2);

CREATE TABLE partition_lab.orders_hash_h3
PARTITION OF partition_lab.orders_hash
FOR VALUES WITH (MODULUS 4, REMAINDER 3);
~~~

With `MODULUS 4`, valid `REMAINDER` values are 0, 1, 2, 3. Each partition key value is hashed by PostgreSQL using its operator class and lands in the corresponding remainder.

### 13.3. Load Data Through the Parent

~~~sql
INSERT INTO partition_lab.orders_hash
    (order_id, customer_id, amount)
VALUES
    (1, 101, 150.00),
    (2, 101, 200.00),
    (3, 102, 90.00),
    (4, 103, 45.00),
    (5, 104, 990.00),
    (6, 105, 110.00),
    (7, 106, 35.00),
    (8, 107, 80.00);

SELECT
    order_id,
    customer_id,
    amount,
    tableoid::regclass AS physical_partition
FROM partition_lab.orders_hash
ORDER BY order_id;
~~~

### 13.4. HASH Does Not Mean SQL Modulo on the ID

Incorrect assumption:

~~~text
If customer_id % 4 = 1
→ the row definitely goes to orders_hash_h1
~~~

PostgreSQL does not compute the partition remainder via ordinary `customer_id % 4`. It hashes **the value through a hash support function and internal rules**, then applies modulus/remainder.

Use `tableoid::regclass` to **observe actual routing** rather than predicting child names with simple integer modulo.

### 13.5. Orders for the Same Customer Land in the Same Partition

For the same partition key `customer_id=101`, rows route to the **same HASH partition** per the bound rule. This helps queries filtering by `customer_id`, yet if one customer produces 80% of all data, the partition holding that customer still grows huge.

HASH does not "spread one giant customer across multiple buckets" if you only hash on `customer_id`.

---

## 14. HASH: MODULUS, REMAINDER, and Coverage

### 14.1. A Bucket Is a Hash Set, Not an ID Range

The definition:

~~~sql
FOR VALUES WITH (MODULUS 4, REMAINDER 2)
~~~

means keys whose hash **yields remainder 2 modulo 4** belong to this partition.

It does not mean accepting `customer_id BETWEEN 2 AND 999999`, nor does it represent the third group of customers in ascending order.

### 14.2. HASH Has No DEFAULT Partition

Unlike RANGE/LIST, PostgreSQL **does not support `DEFAULT` for HASH partitioning**. If no partition covers the computed remainder, `INSERT` fails with "no partition of relation found for row."

### 14.3. Bounds Cannot Overlap

You cannot create two children both with `MODULUS 4, REMAINDER 1` under one parent. PostgreSQL must guarantee every value routes to at most one partition.

### 14.4. Can Different Moduli Coexist?

PostgreSQL has compatibility rules for hash partition bounds with different moduli; a larger modulus must be a valid multiple of the smaller modulus per declaration rules. However, **mixing moduli** does not cause the database to automatically move existing rows when you add a new child.

In introductory and standard operations, use a uniform modulus covering all remainders as planned, and design an explicit migration when bucket counts must change.

### 14.5. Four Buckets Do Not Guarantee 25% of Rows Each

An even split only approximates reality when there are enough independent key values with fairly uniform distribution. If a few keys are heavily skewed or distinct key counts are tiny, row distribution will be uneven.

Check:

~~~sql
SELECT
    tableoid::regclass AS partition_name,
    COUNT(*) AS row_count
FROM partition_lab.orders_hash
GROUP BY tableoid
ORDER BY row_count DESC, partition_name;
~~~

### 14.6. Pruning When Querying by the Hash Key

~~~sql
EXPLAIN
SELECT order_id, customer_id, amount
FROM partition_lab.orders_hash
WHERE customer_id = 101;
~~~

Because `customer_id` is the partition key, PostgreSQL can pinpoint the matching bucket and skip the others.

Conversely:

~~~sql
EXPLAIN
SELECT *
FROM partition_lab.orders_hash
WHERE order_id = 1;
~~~

`order_id` is not the partition key, so a predicate on `order_id` alone **cannot prune by `customer_id`**. Multiple partitions must be checked, even if each has a local index.

---

## 15. RANGE, LIST, and HASH: Routing Examples

| Strategy | Key/Bound | Test Value | Routing |
|---|---|---|---|
| Monthly UTC RANGE | October `[Oct 1, Nov 1)` | `2026-10-31 23:59:59+00` | October |
| Monthly UTC RANGE | November `[Nov 1, Dec 1)` | `2026-11-01 00:00:00+00` | November |
| RANGE | No partition for Jan, `DEFAULT` exists | `2027-01-05` | `DEFAULT` |
| RANGE | No `DEFAULT`, `NULL` value | `NULL` | No partition found |
| LIST | `IN ('north','northern')` | `'northern'` | North |
| LIST | `IN (NULL)` | `NULL` | `NULL` partition |
| LIST | `DEFAULT` | `'west'` | `DEFAULT` |
| HASH | `MODULUS 4`/4 buckets | `customer_id=101` | A bucket chosen by hash, **do not guess from `101%4`** |
| HASH | Missing bucket for remainder | Key hashing to missing remainder | `INSERT` errors: no partition found |

Values and keys in this table are illustrative. Actual routing depends on the created structure, data, and key types.

---

## 16. Decision Flowchart for Choosing a Strategy

~~~mermaid
flowchart TD
    A["Analyze workload and data lifecycle"] --> B{"What do most queries filter on?"}
    B -- "Time ranges or ordered values" --> C["RANGE"]
    B -- "A set of business-meaningful groups" --> D["LIST"]
    B -- "Equality on a high-cardinality key" --> E["HASH"]
    B -- "Multiple independent dimensions" --> F["Consider subpartitioning"]
    C --> G{"Interval-based retention?"}
    G -- "Yes" --> H["Split by appropriate day/month/week"]
    G -- "No" --> I["Compare with regular table + B-tree/BRIN"]
    D --> J{"Skewed groups or frequent changes?"}
    J -- "Yes" --> K["Revisit key, DEFAULT, or subpartitioning"]
    J -- "No" --> L["Partition by group"]
    E --> M{"Are there hot keys?"}
    M -- "Yes" --> N["Single-key HASH may skew; evaluate alternatives"]
    M -- "No" --> O["Start with reasonable bucket count"]
    F --> P["Measure partition count overhead and pruning"]
    H --> Q["Design PK/UNIQUE, indexes, automation"]
    I --> Q
    K --> Q
    L --> Q
    N --> Q
    O --> Q
    P --> Q
    Q --> R["EXPLAIN, benchmark, deploy safely"]
~~~

**There is no single default best option for every workload.** A B-tree or BRIN index on an unpartitioned table can be simpler and more effective when data is modest or retention does not require segment-by-segment management.

---

## 17. Inspecting the Partition Tree and Bounds from Catalogs

Creating partitions does not guarantee everything is attached as intended. Before adding indexes or migrating, verify the actual structure.

### 17.1. pg_partition_tree

On supported PostgreSQL versions:

~~~sql
SELECT
    relid::regclass AS relation_name,
    parentrelid::regclass AS parent_name,
    isleaf,
    level
FROM pg_partition_tree('partition_lab.events'::regclass)
ORDER BY level, relation_name::text;
~~~

Returned columns include:

- `relid`: parent or child in the tree.
- `parentrelid`: immediate parent relation (`NULL` for root).
- `isleaf`: whether it is a leaf partition or partitioned further.
- `level`: depth starting from the root.

When unsure whether a partition is a leaf, `isleaf` prevents assuming "every direct child holds data."

### 17.2. pg_inherits and pg_get_expr

PostgreSQL stores parent-child partition structure in system catalogs.

~~~sql
SELECT
    child.oid::regclass AS partition_name,
    parent.oid::regclass AS parent_name,
    pg_get_expr(child.relpartbound, child.oid) AS partition_bound
FROM pg_inherits AS inh
JOIN pg_class AS child ON child.oid = inh.inhrelid
JOIN pg_class AS parent ON parent.oid = inh.inhparent
WHERE inh.inhparent = 'partition_lab.events'::regclass
ORDER BY partition_name::text;
~~~

`pg_get_expr(... relpartbound ...)` prints expressions like:

~~~text
FOR VALUES FROM ('2026-11-01 ...') TO ('2026-12-01 ...')
FOR VALUES DEFAULT
~~~

Never edit `pg_class.relpartbound` or `pg_inherits` directly: these are internal catalogs managed strictly by PostgreSQL DDL.

### 17.3. Inspect the Parent Key

~~~sql
SELECT
    partrelid::regclass AS parent_table,
    partstrat,
    partnatts,
    pg_get_partkeydef(partrelid) AS partition_key_definition
FROM pg_partitioned_table
WHERE partrelid IN (
    'partition_lab.events'::regclass,
    'partition_lab.support_tickets'::regclass,
    'partition_lab.orders_hash'::regclass
);
~~~

Strategy codes are represented as:

| `partstrat` | Strategy |
|---|---|
| `r` | RANGE |
| `l` | LIST |
| `h` | HASH |

Use `pg_get_partkeydef` for a readable key definition instead of guessing from table names.

### 17.4. Never Rely on Table Name Suffixes for Routing

A table named `events_2026_11` can accidentally be created/attached with the wrong bounds if DDL has a bug. **The actual partition bound metadata** governs routing, not the child's name suffix.

---

## 18. Indexes on Partitioned Tables: Parent vs. Child

### 18.1. A Parent Index Is a Logical Object

On a declarative partitioned table:

~~~sql
CREATE INDEX idx_events_tenant_time
ON partition_lab.events (tenant_id, event_at DESC);
~~~

PostgreSQL creates a corresponding **partitioned index** on the parent and physical indexes on existing child partitions, per version and command capabilities.

Each leaf partition has its own **local index**. There is no single physical B-tree holding rows from all partitions the way a global index would.

### 18.2. Local Indexes Work Together with Pruning

A query:

~~~sql
EXPLAIN
SELECT event_id, event_at, event_type
FROM partition_lab.events
WHERE tenant_id = 11
  AND event_at >= TIMESTAMPTZ '2026-11-01 00:00:00+00'
  AND event_at <  TIMESTAMPTZ '2026-12-01 00:00:00+00'
ORDER BY event_at DESC
LIMIT 20;
~~~

can:

1. **Prune** down to November only.
2. Use the local index on `(tenant_id, event_at DESC)` in November.
3. Return the top 20 in order (depending on plan, size, and selectivity).

These are two distinct layers: pruning reduces the number of partitions examined; local indexes reduce the work **inside** the remaining partitions.

### 18.3. Do Parent Indexes Apply to Future Partitions?

When creating or attaching a new partition, PostgreSQL automatically creates or attaches matching child indexes for partitioned indexes defined on the parent per standard rules. Defining indexes at the parent level is therefore usually cleaner than manually scripting indexes for every child.

However, if you **attach a pre-populated table** and an index has to be built over large data, index creation can take a long time. Pre-building the matching index before attaching lets you control timing and locking.

### 18.4. Creating an Index on a Single Partition

~~~sql
CREATE INDEX idx_events_nov_event_type
ON partition_lab.events_2026_11 (event_type);
~~~

This index applies only to `events_2026_11`, not October or December. Useful when one partition has an unusual workload, though it requires clear operational documentation so future partitions aren't overlooked.

### 18.5. Do Not Duplicate Parent-Managed Indexes on Children

If the parent already manages local indexes on `(tenant_id,event_at)`, adding a child index with the identical definition only wastes disk space and increases write amplification. Check `pg_indexes` or catalogs before creating.

---

## 19. CREATE INDEX CONCURRENTLY on a Partitioned Table

### 19.1. Why Does It Require a Special Workflow?

`CREATE INDEX CONCURRENTLY` avoids blocking writes when indexing a **regular table**, yet PostgreSQL does not support it directly on a **partitioned parent table** like this:

~~~sql
-- Do not use: CREATE INDEX CONCURRENTLY directly on the parent.
CREATE INDEX CONCURRENTLY idx_parent_online
ON partition_lab.events (tenant_id, event_at);
~~~

In PostgreSQL versions where this restriction applies, the statement is rejected; you must build each **leaf index** concurrently and then attach them.

### 19.2. The ON ONLY Partitioned Index Pattern

A standard production workflow on large tables:

~~~sql
-- Create the parent index definition without attaching leaf indexes yet:
CREATE INDEX idx_events_tenant_at_online
ON ONLY partition_lab.events (tenant_id, event_at);
~~~

Then build indexes separately on each required leaf partition:

~~~sql
-- Run each statement independently, OUTSIDE an explicit transaction block:
CREATE INDEX CONCURRENTLY idx_events_oct_tenant_at_online
ON partition_lab.events_2026_10 (tenant_id, event_at);

CREATE INDEX CONCURRENTLY idx_events_nov_tenant_at_online
ON partition_lab.events_2026_11 (tenant_id, event_at);

CREATE INDEX CONCURRENTLY idx_events_dec_tenant_at_online
ON partition_lab.events_2026_12 (tenant_id, event_at);

CREATE INDEX CONCURRENTLY idx_events_other_tenant_at_online
ON partition_lab.events_other (tenant_id, event_at);
~~~

Attach each matching built index to the parent:

~~~sql
ALTER INDEX partition_lab.idx_events_tenant_at_online
    ATTACH PARTITION partition_lab.idx_events_oct_tenant_at_online;

ALTER INDEX partition_lab.idx_events_tenant_at_online
    ATTACH PARTITION partition_lab.idx_events_nov_tenant_at_online;

ALTER INDEX partition_lab.idx_events_tenant_at_online
    ATTACH PARTITION partition_lab.idx_events_dec_tenant_at_online;

ALTER INDEX partition_lab.idx_events_tenant_at_online
    ATTACH PARTITION partition_lab.idx_events_other_tenant_at_online;
~~~

Only once **all** existing partitions have compatible indexes properly attached does the parent partitioned index become valid.

This is a **procedural pattern**: before executing, verify the parent index does not already exist, check every existing child/`DEFAULT`, ensure exact index definition parity, check migration-tool transaction behavior, and verify lock availability.

### 19.3. Why Not Use BEGIN for Concurrent Index Builds?

`CREATE INDEX CONCURRENTLY` runs across multiple phases and **cannot execute inside an explicit transaction block**. Some migration tools wrap an entire migration file in a transaction by default; split non-transactional steps appropriately.

### 19.4. If a Child Index Build Fails

The child index may be left in an `INVALID` state. The parent index cannot become ready while a valid child index is missing.

Check:

~~~sql
SELECT
    idx.relname AS index_name,
    tbl.relname AS table_name,
    ix.indisvalid,
    ix.indisready,
    pg_get_indexdef(ix.indexrelid) AS definition
FROM pg_index AS ix
JOIN pg_class AS idx ON idx.oid = ix.indexrelid
JOIN pg_class AS tbl ON tbl.oid = ix.indrelid
JOIN pg_namespace AS ns ON ns.oid = tbl.relnamespace
WHERE ns.nspname = 'partition_lab'
  AND tbl.relname LIKE 'events%'
ORDER BY table_name, index_name;
~~~

Resolve the root cause before retrying. `IF NOT EXISTS` does not guarantee an existing same-named index is valid or has the intended definition.

### 19.5. This Does Not Create a Global Index

Attaching all child indexes to a parent partitioned index forms a **logical collection of indexes**. It does not create a single cross-partition B-tree and does not lift parent `UNIQUE`/`PRIMARY KEY` restrictions.

---

## 20. Primary Keys and UNIQUE on Partitioned Tables

### 20.1. Why Is PRIMARY KEY(event_id) Invalid with RANGE(event_at)?

Consider:

~~~sql
CREATE TABLE partition_lab.invalid_event_pk (
    event_id BIGINT PRIMARY KEY,
    event_at TIMESTAMPTZ NOT NULL
)
PARTITION BY RANGE (event_at);
~~~

In modern PostgreSQL, this definition is **invalid** because a primary key on a partitioned parent must include **every partition key column**. Otherwise, two separate partitions could both hold `event_id=123` because their local unique indexes do not coordinate globally.

**This is an expected-error example**: do not run it as a setup step for subsequent labs.

### 20.2. Valid Keys When Partitioning Directly on Columns

For the `events` table created earlier:

~~~sql
PRIMARY KEY (event_at, event_id)
~~~

The key includes `event_at`, so it can be enforced via local unique indexes on the partitions.

Understand precisely what this means: it guarantees the **pair `(event_at,event_id)`** is unique. It **does not prevent an `event_id` from appearing twice with different `event_at` timestamps**.

### 20.3. Conditions for UNIQUE and PRIMARY KEY on the Parent

In declarative partitioning, `UNIQUE`/`PRIMARY KEY` constraints on the parent must include **all partition key columns**, and the partition key **must not use expressions/function calls** if you want that constraint on the parent.

For example, valid on `LIST(region)`:

~~~sql
CREATE TABLE partition_lab.region_memberships (
    member_id BIGINT NOT NULL,
    region TEXT NOT NULL,
    PRIMARY KEY (region, member_id)
)
PARTITION BY LIST (region);
~~~

You cannot declare `PRIMARY KEY(member_id)` alone on the parent and expect PostgreSQL to build a global unique index across partitions.

### 20.4. Expression Partition Keys and Unique Constraints

For example:

~~~sql
-- Valid table creation example (no PK on parent):
CREATE TABLE partition_lab.regions_normalized (
    id BIGINT NOT NULL,
    region TEXT NOT NULL
)
PARTITION BY LIST ((lower(region)));
~~~

Declaring a `UNIQUE`/`PRIMARY KEY` on a partitioned parent whose partition key is an expression runs into PostgreSQL's column/operator restrictions; do not assume you can simply add a parent PK on `id`.

If the application needs global uniqueness independent of the partition key, consider:

- Redesigning the partition key or business key.
- Using a global ID generator and application-level guarantees, recognizing that a sequence **only issues numbers** and does not enforce a global `UNIQUE` constraint on the parent.
- A small unpartitioned registry table holding the unique key, updated transactionally alongside writes.
- An alternative data model if strict database-enforced global invariants are required.

### 20.5. Why Local UNIQUE Is Not Enough

Two partitions have two separate indexes. Each index sees only its own partition's rows. There is no unified global index checking `event_id` across all partitions.

Design APIs so they never treat `PRIMARY KEY (event_at,event_id)` as equivalent to "globally unique `event_id`," and avoid querying or referencing a partial key when business rules require identifying a single unique event.

### 20.6. NULL and UNIQUE

Traditional SQL `UNIQUE` treats `NULL` differently from ordinary equality; newer PostgreSQL versions add `NULLS NOT DISTINCT` for `UNIQUE` where supported. However, that **does not bypass** the requirement that parent constraints include the partition key. Never rely on `NULL` semantics to circumvent cross-partition uniqueness rules.

---

## 21. FOREIGN KEY and Integrity Constraints

### 21.1. Foreign Keys with Partitioned Tables

Modern PostgreSQL supports `FOREIGN KEY` constraints in many scenarios involving partitioned tables, both as the referencing and referenced side under schema/version rules. Still, when the target parent PK includes the partition key, an FK must reference **a key that is properly guaranteed unique**.

For example, if a dimension table has a normal key:

~~~sql
CREATE TABLE partition_lab.tenants (
    tenant_id INTEGER PRIMARY KEY,
    tenant_name TEXT NOT NULL
);

INSERT INTO partition_lab.tenants(tenant_id, tenant_name)
VALUES (11, 'Alpha'), (12, 'Beta'), (13, 'Gamma');
~~~

You can add an FK from `events.tenant_id`:

~~~sql
ALTER TABLE partition_lab.events
ADD CONSTRAINT fk_events_tenant
FOREIGN KEY (tenant_id)
REFERENCES partition_lab.tenants(tenant_id);
~~~

In the lab dataset, 11, 12, and 13 exist, so the FK succeeds. In production, adding an FK may require validation scans and locks across parent/child tables; follow an appropriate migration workflow.

### 21.2. Do Not Assume an FK Can Reference event_id Alone

With `events` having `PK(event_at,event_id)`, another table wanting an FK on `event_id` alone **has no unique target** on the parent. It must store the full composite key, or use a different registry/ID model.

### 21.3. CHECK and NOT NULL

Partitions inherit compatible constraints from the parent under declarative partitioning semantics. `CHECK` constraints can reinforce data invariants, though **partition bounds already govern routing**; do not define a `CHECK` that conflicts with bounds or place undocumented child-only constraints the application isn't aware of.

### 21.4. Exclusion Constraints and Global Uniqueness

Exclusion constraints on partitioned tables have scope restrictions by index/partition and version. Do not assume per-child exclusion constraints prevent overlaps **between two different children** when business predicates can span partition bounds. If global enforcement is required, choose a partition key and constraint design ensuring potentially conflicting rows always land in the same partition, or use another coordination/data model.

---

## 22. INSERT: Where Does Routing Happen?

### 22.1. Writing Through the Parent

~~~sql
INSERT INTO partition_lab.events
    (event_id, event_at, tenant_id, event_type)
VALUES
    (2001, '2026-11-20 03:00:00+00', 11, 'click');
~~~

PostgreSQL inspects the partition key and routes the row into `events_2026_11`.

### 22.2. Writing Directly to a Child

~~~sql
INSERT INTO partition_lab.events_2026_11
    (event_id, event_at, tenant_id, event_type)
VALUES
    (2002, '2026-11-21 04:00:00+00', 12, 'view');
~~~

Direct child writes are permitted with appropriate privileges, yet the row must still satisfy the **partition constraint**. Attempting to insert a January timestamp into the November child raises an error rather than re-routing to `DEFAULT`.

In applications, prefer writing through the parent to avoid coupling to child table names.

### 22.3. No Partition Accepts the Data

If a RANGE parent has no `DEFAULT` and no partition covers `event_at`, `INSERT` fails with a missing-partition error. PostgreSQL **never creates partitions automatically based on month names**.

### 22.4. INSERT ... SELECT, COPY, and Batch Ingestion

Bulk writing through the parent still routes each row by its partition key. Overhead can rise if there are too many partitions or each row must evaluate child constraints/indexes.

If an application ingests many events for the same month, batching by time can reduce client/transaction overhead, though locks, WAL, triggers, and recovery must be tested. Never bypass the parent straight to a child just "for speed" if it risks breaking routing or schema alignment.

### 22.5. ON CONFLICT on a Partitioned Table

PostgreSQL supports `INSERT ... ON CONFLICT` against eligible `UNIQUE`/`PK` constraints. Conflict detection only relies on **declared and supported unique constraints/indexes**.

Composite key example:

~~~sql
INSERT INTO partition_lab.events
    (event_id, event_at, tenant_id, event_type)
VALUES
    (1002, '2026-11-01 00:00:00+00', 11, 'login')
ON CONFLICT (event_at, event_id)
DO NOTHING;
~~~

This prevents duplicating the **pair** of keys, not duplicate `event_id` values at different `event_at` times.

### 22.6. ON CONFLICT DO UPDATE Is Not a Free-Form Partition Mover

In many PostgreSQL versions, `ON CONFLICT DO UPDATE` **is not supported when updating the partition key would move the conflicting row into a different partition**. Do not use `UPSERT` to shift `event_at` from November to December arbitrarily; check supported syntax and transaction/update semantics carefully.

---

## 23. Updating the Partition Key: Rows Can Move Between Partitions

### 23.1. When the Partition Key Changes

Suppose an event's timestamp is corrected from November to December:

~~~sql
BEGIN;

UPDATE partition_lab.events
SET event_at = TIMESTAMPTZ '2026-12-02 10:00:00+00'
WHERE event_id = 1003
  AND event_at = TIMESTAMPTZ '2026-11-15 08:30:00+00';

SELECT
    event_id, event_at, tableoid::regclass AS partition_name
FROM partition_lab.events
WHERE event_id = 1003;

ROLLBACK;
~~~

PostgreSQL can perform **row movement** from November to December internally using delete+insert mechanics when the partition key is updated.

Because the example ends with `ROLLBACK`, the original lab data stays untouched.

### 23.2. Row Movement Carries Cost and Contention

- Modifies indexes and constraints on both source and target partitions.
- Generates extra WAL and dead tuples.
- Triggers, FKs, and row locking follow specific rules you must understand.
- Under concurrent access, serialization failures (`SQLSTATE 40001`) or other conflicts can occur depending on isolation level and operation type.
- If the destination partition does not exist, `UPDATE` fails rather than auto-creating it.

### 23.3. Avoid Frequently Changing Partition Keys Unless Necessary

For instance, LIST partitioning on `status` (`new` → `processing` → `paid`) turns every state transition into cross-partition row movement rather than an in-place heap update. If the workload executes millions of status updates per hour, prefer a more stable partition key.

### 23.4. DELETE on the Parent

~~~sql
DELETE FROM partition_lab.events
WHERE event_at >= TIMESTAMPTZ '2026-10-01 00:00:00+00'
  AND event_at <  TIMESTAMPTZ '2026-11-01 00:00:00+00';
~~~

This can prune down to October, yet remains a **row-by-row `DELETE`** generating WAL, dead tuples, and `VACUUM` work. If the goal is removing an **entire** old partition for retention, `DETACH`/`DROP` is typically better suited, with its own workflow for locks, backups, FKs, and data safety.

**Do not run this DELETE in the lab if you want to keep October rows for later exercises**; it is shown as a business-logic example.

---

## 24. Partition Pruning: Compile-Time vs. Execution-Time

### 24.1. Compile-Time Pruning

When a query uses constant predicates:

~~~sql
EXPLAIN
SELECT COUNT(*)
FROM partition_lab.events
WHERE event_at >= TIMESTAMPTZ '2026-11-01 00:00:00+00'
  AND event_at <  TIMESTAMPTZ '2026-12-01 00:00:00+00';
~~~

The planner can exclude partitions unable to hold matching rows right at **plan time**.

### 24.2. Execution-Time Pruning

Parameterized query:

~~~sql
PREPARE count_events_in_range(timestamptz, timestamptz) AS
SELECT COUNT(*)
FROM partition_lab.events
WHERE event_at >= $1
  AND event_at <  $2;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE count_events_in_range(
    '2026-11-01 00:00:00+00',
    '2026-12-01 00:00:00+00'
);

DEALLOCATE count_events_in_range;
~~~

When the planner does not know concrete parameter values during planning (e.g., a generic plan), PostgreSQL can prune partitions during **initialization or execution** using parameter values, indicated by `Subplans Removed`, `never executed`, or zero loops on pruned children.

### 24.3. enable_partition_pruning

~~~sql
SHOW enable_partition_pruning;
~~~

Normally keep pruning enabled. In a lab session, you can test disabling it:

~~~sql
BEGIN;
SET LOCAL enable_partition_pruning = off;

EXPLAIN
SELECT COUNT(*)
FROM partition_lab.events
WHERE event_at >= TIMESTAMPTZ '2026-11-01 00:00:00+00'
  AND event_at <  TIMESTAMPTZ '2026-12-01 00:00:00+00';

ROLLBACK;
~~~

Disable pruning **strictly to observe the difference** in the lab; never treat this as a production tuning technique.

### 24.4. Does Pruning Require an Index?

No. Pruning relies on **partition bounds**, not an index on the partition key. Even if a partition has zero indexes, PostgreSQL can still eliminate irrelevant children.

Indexes are considered **afterward** on the surviving children to speed up intra-partition scans.

### 24.5. Pruning Depends on Operators and Expressions

Conditions using the partition key with matching operators, proper casts, and constants/parameters facilitate pruning. Arbitrary transformations on the key cannot always be inverted by the planner.

For example, with a `RANGE(event_at)` parent:

~~~sql
-- Generally pruning-friendly form:
WHERE event_at >= TIMESTAMPTZ '2026-11-01 00:00+00'
  AND event_at < TIMESTAMPTZ '2026-12-01 00:00+00'
~~~

differs from:

~~~sql
-- Can restrict pruning; inspect EXPLAIN:
WHERE EXTRACT(MONTH FROM event_at) = 11
~~~

The second form also matches **every year**, not just November 2026.

### 24.6. Parameterized Joins and Pruning

When joining another table that supplies a partition key value, PostgreSQL can perform execution-time pruning inside parameterized plans in supported cases. However, not every join or filter triggers runtime pruning; verify with `EXPLAIN (ANALYZE, BUFFERS)` on your actual workload.

---

## 25. When Pruning Alone Is Not Enough for Fast Queries

### 25.1. A Remaining Partition Is Still Huge

If you partition logs by **year**, querying the most recent hour still prunes down to **one yearly partition** holding hundreds of millions of rows. You still need suitable local indexes or monthly/daily partitioning matched to the workload.

### 25.2. Query Lacks the Partition Key

~~~sql
SELECT *
FROM partition_lab.events
WHERE tenant_id = 11;
~~~

The parent is partitioned by time while the query filters only on tenant, so every partition may be examined. Options include adding local tenant/time indexes, adding a valid time filter, or considering two-level partitioning. Never invent an artificial time cutoff if business requirements genuinely call for **all history**.

### 25.3. Unfiltered COUNT(*)

~~~sql
SELECT COUNT(*) FROM partition_lab.events;
~~~

Must aggregate across all relevant partitions. Partitioning does not maintain an automatic exact row counter that answers without scanning.

### 25.4. ORDER BY / LIMIT Across Many Partitions

~~~sql
SELECT event_id, event_at
FROM partition_lab.events
ORDER BY event_at DESC
LIMIT 20;
~~~

Depending on the plan, this may use local indexes with `MergeAppend`/`Limit` or touch many partitions. Do not assume PostgreSQL automatically knows "only the latest month has the rows needed" if there is no filter and other partitions could hold competing rows.

### 25.5. Too Many Partitions

Thousands or tens of thousands of partitions can inflate:

- Planning time and catalog/metadata lookups.
- Memory consumed by plans.
- Number of relations/indexes opened and locked.
- Maintenance, backup, monitoring, and schema migration costs.
- Risk of lock exhaustion when a single transaction touches many objects.

Never assume "more partitions = linearly faster." Choose granularity based on **per-partition size, retention, and filter patterns**.

---

## 26. Multi-Level Partitioning (Subpartitioning)

You can split by time first, and then by tenant or hash.

### 26.1. Create a Daily/Time RANGE Parent

~~~sql
CREATE TABLE partition_lab.multilevel_events (
    event_id BIGINT NOT NULL,
    event_at DATE NOT NULL,
    tenant_id INTEGER NOT NULL,
    payload TEXT
)
PARTITION BY RANGE (event_at);
~~~

### 26.2. Monthly Child Is Itself a HASH Partitioned Table

~~~sql
CREATE TABLE partition_lab.multilevel_events_2026_11
PARTITION OF partition_lab.multilevel_events
FOR VALUES FROM ('2026-11-01') TO ('2026-12-01')
PARTITION BY HASH (tenant_id);
~~~

This is both a child of the RANGE parent **and a second-level parent** for HASH partitions.

### 26.3. Create Two Leaf HASH Partitions

~~~sql
CREATE TABLE partition_lab.multilevel_events_2026_11_h0
PARTITION OF partition_lab.multilevel_events_2026_11
FOR VALUES WITH (MODULUS 2, REMAINDER 0);

CREATE TABLE partition_lab.multilevel_events_2026_11_h1
PARTITION OF partition_lab.multilevel_events_2026_11
FOR VALUES WITH (MODULUS 2, REMAINDER 1);
~~~

### 26.4. Load and Inspect

~~~sql
INSERT INTO partition_lab.multilevel_events
    (event_id, event_at, tenant_id, payload)
VALUES
    (1, DATE '2026-11-05', 101, 'A'),
    (2, DATE '2026-11-20', 102, 'B'),
    (3, DATE '2026-11-21', 103, 'C');

SELECT
    event_id, event_at, tenant_id,
    tableoid::regclass AS leaf_partition
FROM partition_lab.multilevel_events
ORDER BY event_id;
~~~

Each row passes through the RANGE rule and then the HASH rule, landing in a leaf partition.

### 26.5. Query Filtering Both Keys

~~~sql
EXPLAIN
SELECT *
FROM partition_lab.multilevel_events
WHERE event_at >= DATE '2026-11-01'
  AND event_at <  DATE '2026-12-01'
  AND tenant_id = 101;
~~~

The planner can prune at both levels when eligible.

### 26.6. Watch Out for Leaf Partition Multiplication

12 months × 32 HASH buckets = **384 leaf partitions/year**. Over 5 years that is 1,920 leaf partitions, not counting intermediate partitioned parents and indexes. Multi-level designs must weigh total object counts, lock overhead, and child-creation automation—not just theoretical pruning gains.

### 26.7. Do Not Assume Every Two-Dimensional Combination Exists

The lab only creates November 2026. Inserting a December row fails at level 1 for lack of a matching partition, even though November already has full HASH buckets. Every level must have **complete bounds** for the expected data domain.

---

## 27. Partition-Wise Join and Partition-Wise Aggregate

### 27.1. Concept of Partition-Wise Join

If two tables are partitioned compatibly on the **join key** and the join condition matches accordingly, the planner can join **corresponding partitions directly** and combine the results rather than materializing both full tables before joining.

~~~text
orders_h0  JOIN items_h0 ─┐
orders_h1  JOIN items_h1 ─┼─> Append/merge results
orders_h2  JOIN items_h2 ─┤
orders_h3  JOIN items_h3 ─┘
~~~

This is a conceptual diagram. For a valid plan, both sides must meet requirements on strategy/keys, data types, join conditions, and partition layout; merely having 4 partitions on two tables does not guarantee h0 joins directly with h0.

### 27.2. enable_partitionwise_join

~~~sql
SHOW enable_partitionwise_join;
~~~

In modern PostgreSQL, this setting is typically **off by default**. Where appropriate, you can test in a lab session:

~~~sql
BEGIN;
SET LOCAL enable_partitionwise_join = on;

EXPLAIN
SELECT *
FROM partition_lab.orders_hash AS o
JOIN partition_lab.orders_hash AS p
  ON p.customer_id = o.customer_id
WHERE o.customer_id = 101;

ROLLBACK;
~~~

This self-join query is **strictly for inspecting the plan**; running it unchecked could produce many rows if one customer has multiple orders. Do not treat it as a production workload.

### 27.3. enable_partitionwise_aggregate

~~~sql
SHOW enable_partitionwise_aggregate;
~~~

Depending on the query and partition keys, PostgreSQL can perform partial aggregation per partition before combining globally. However, a query like:

~~~sql
SELECT tenant_id, COUNT(*)
FROM partition_lab.events
GROUP BY tenant_id;
~~~

on `RANGE(event_at)` cannot assume each tenant lives in only one partition; a final aggregation step across partitions is required. Read the plan to see how far partition-wise aggregation applies.

### 27.4. Do Not Enable Partition-Wise Options Server-Wide by Habit

Partition-wise join/aggregate can increase node counts, planning time, and memory usage—especially with many partitions. Test on a realistic workload and compare `Planning Time`, `Execution Time`, buffers, and memory before changing server defaults.

---

## 28. UNIQUE Limitations Under Subpartitioning

If a parent is `RANGE(event_at)` and each monthly child is `HASH(tenant_id)`, any unique key enforced across **the entire tree** may need to include **partition keys from all involved levels** per PostgreSQL's constraint rules. Never assume `PRIMARY KEY(event_at,event_id)` suffices if leaves further split by `HASH(tenant_id)` where deeper-level constraints cannot enforce cross-bucket uniqueness.

In `multilevel_events`, no PK was declared to avoid creating the false impression that every level automatically maintains a global unique index.

In real designs:

1. List **all partition key columns** at the root and every intermediate level.
2. Identify the exact scope over which business keys must be unique.
3. Verify `UNIQUE`/`PK` rules on the parent and partitioned children for your PostgreSQL version.
4. Use a valid constraint or adjust your partitioning/data model if the invariant cannot be guaranteed.

This is why subpartitioning must be evaluated alongside **schema and constraints**, not `SELECT` queries alone.

---

## 29. RANGE Lifecycle Management: Pre-Creating Partitions Before Data Arrives

### 29.1. Why Pre-Create?

For continuous event streams, reaching the first of a new month without a partition causes:

- `INSERT` **failures** if there is no `DEFAULT`.
- `INSERT`s piling into an oversized `DEFAULT` if one exists.
- Irregular query, backup, and retention behavior.
- Adding the missing partition later fails or requires tricky data migration if `DEFAULT` already absorbed rows in the new range.

Therefore, schedule **partition pre-creation** well ahead of when data can arrive.

### 29.2. Creating a New Month

For example, creating February 2027 without overlapping the existing three months:

~~~sql
CREATE TABLE partition_lab.events_2027_02
PARTITION OF partition_lab.events
FOR VALUES FROM ('2027-02-01 00:00:00+00')
           TO   ('2027-03-01 00:00:00+00');
~~~

This command may have to scan `DEFAULT` to verify no February rows already exist there before assigning the new bound. In the lab, `DEFAULT` only holds January 2027, so February is empty; in production, **never assume `DEFAULT` is empty**.

### 29.3. Automating Periodic Partition Creation

An operational job should:

1. Determine exact boundary dates/times and timezone rules.
2. Calculate partitions required for several upcoming periods.
3. Inspect existing metadata to avoid duplicate creation.
4. Create/attach missing partitions.
5. Verify bounds, indexes, constraints, and tablespaces.
6. Monitor `DEFAULT` and routing errors.
7. Flag partitions approaching retention expiration.

Automation must be **idempotent**, handle concurrency (preventing two jobs from creating the same partition), handle errors cleanly, and never drop data based on miscalculated date variables.

### 29.4. What Partitions Does Backfilling Old Data Need?

If the application may backfill historical 2025 data, pre-creating only future months is not enough. You need partitions covering the backfill range or a `DEFAULT` partition, though `DEFAULT` is no substitute for planning historical partitions.

### 29.5. Daily, Weekly, Monthly, or Yearly Cadence?

| Granularity | Usually Reasonable When | Risks |
|---|---|---|
| Hourly | Extreme traffic with very short hot window | Huge object count and maintenance load |
| Daily | High daily volume needing daily retention | Many partitions after a few years |
| Monthly | Medium/high volume with monthly retention | Current month's partition may still grow huge |
| Yearly | Smaller datasets or rarely queried history | Huge partitions, weak pruning for multi-day queries |

Never apply a fixed row-count threshold across all workloads. Measure page counts, index sizes, queries, and operational overhead.

---

## 30. ATTACH PARTITION: Turning an Existing Table into a Child

### 30.1. Why Is ATTACH Useful?

Sometimes data is bulk-loaded into **a regular table** first, or you want to build indexes and validate rows before exposing it under the parent. `ATTACH PARTITION` attaches an existing relation as a child with specified bounds.

### 30.2. Create a Standalone Table with Matching Structure

~~~sql
CREATE TABLE partition_lab.events_2027_03
(LIKE partition_lab.events INCLUDING DEFAULTS INCLUDING CONSTRAINTS);
~~~

`LIKE` copies properties requested by the options. It does not guarantee copying **every** index, trigger, identity, permission, or parent attribute across all versions. On attach, PostgreSQL checks schema/constraint compatibility and binds indexes/constraints accordingly. Always verify the actual catalogs.

### 30.3. Prove Data Matches the Bounds

A validated constraint on the standalone table can prove it only holds rows from March 2027:

~~~sql
ALTER TABLE partition_lab.events_2027_03
ADD CONSTRAINT chk_events_2027_03_bound
CHECK (
    event_at >= TIMESTAMPTZ '2027-03-01 00:00:00+00'
    AND
    event_at < TIMESTAMPTZ '2027-04-01 00:00:00+00'
);
~~~

When the `CHECK` is **validated** and structured so PostgreSQL can use it as proof, `ATTACH` can skip scanning the entire standalone table just to verify bounds. Without a sufficient validated `CHECK`, PostgreSQL must scan and validate every row, which can be slow.

### 30.4. Attach the Table to the Parent

~~~sql
ALTER TABLE partition_lab.events
ATTACH PARTITION partition_lab.events_2027_03
FOR VALUES FROM ('2027-03-01 00:00:00+00')
           TO   ('2027-04-01 00:00:00+00');
~~~

Once attached, the table is no longer an arbitrary standalone table; it is a child bound by the parent's rules and metadata.

### 30.5. Locks During ATTACH

Under modern PostgreSQL rules, `ATTACH PARTITION` typically acquires **SHARE UPDATE EXCLUSIVE** on the parent and **ACCESS EXCLUSIVE** on the table being attached. If the parent has a `DEFAULT` partition, PostgreSQL may need to check `DEFAULT` under a strong lock unless a suitable validated constraint proves `DEFAULT` holds no rows in the new range.

Thus, "ATTACH is metadata-only" **does not mean** zero locks or zero scans. For large tables, pre-validate `CHECK` constraints and schedule during suitable traffic windows.

### 30.6. DEFAULT Can Block ATTACH

Suppose `events_other` contains March 2027 rows. When you try to attach `events_2027_03`, `DEFAULT` **cannot continue holding rows belonging to the new partition's domain**. PostgreSQL rejects the attach if overlapping rows exist.

You must plan a migration sequence:

- Block or coordinate new writes into the overlapping range while preserving transaction semantics, or use a dedicated dual-write/cutover strategy.
- Create the standalone table and matching indexes/constraints.
- Copy/move overlapping rows from `DEFAULT` into the standalone table and verify counts and data.
- Remove those rows from `DEFAULT` once safely persisted elsewhere.
- `ATTACH` the new partition once `DEFAULT` contains no overlapping rows.
- Resume writes and verify parent queries.

Never just run `DELETE FROM events_other WHERE event_at ...` and "hope" the data was saved elsewhere. On large tables, batch carefully and prevent any window where data disappears from parent queries.

### 30.7. Exclusion CHECK on DEFAULT to Avoid Scanning

You can add a **validated** `CHECK` constraint on `DEFAULT` proving it holds no rows in the new range—for example, the negation of March:

~~~sql
ALTER TABLE partition_lab.events_other
ADD CONSTRAINT chk_events_other_not_march_2027
CHECK (
    event_at < TIMESTAMPTZ '2027-03-01 00:00:00+00'
    OR
    event_at >= TIMESTAMPTZ '2027-04-01 00:00:00+00'
);
~~~

This applies when `DEFAULT` holds **no** March rows; if any exist, `ADD CHECK` validation fails. PostgreSQL can use this proof to skip scanning `DEFAULT` during attach. Still, adding/validating the `CHECK` carries its own lock and scan cost, so plan its timing.

**Note:** in the lab at Section 30.4, if you have already attached March, do not treat running this `ADD CHECK` afterward as required; it is a **pre-ATTACH preparation** technique, not an afterthought.

---

## 31. DEFAULT Partition: Should You Have One?

### 31.1. Having a DEFAULT

Pros:

- Prevents `INSERT` failures when unexpected months or groups arrive.
- Acts as a temporary landing zone for off-schedule data.
- Keeps parent queries able to see rows outside named bounds.

Cons:

- Can mask broken partition pre-creation jobs.
- Accumulated data can bloat `DEFAULT`.
- Attaching new partitions must prove `DEFAULT` holds no overlapping rows, sometimes causing scans/locks.
- Pruning must check `DEFAULT` whenever bounds cannot rule it out.

### 31.2. Not Having a DEFAULT

Pros:

- Out-of-range data is caught **immediately on `INSERT`**.
- Forces pipelines to pre-create partitions and respect ingestion schedules.

Cons:

- A failed pre-creation job can halt ingestion.
- Backfilling unusual historical data requires explicit partition planning.

### 31.3. Decide Based on Operational Requirements

If a payment ledger cannot tolerate events silently landing in the wrong month, **fail-fast** may beat `DEFAULT`. If a logging pipeline must keep ingesting with controlled risk, `DEFAULT` paired with alerting and dedicated cleanup may fit better.

Either way, monitor actively:

~~~sql
SELECT COUNT(*) AS unexpected_rows
FROM partition_lab.events_other;
~~~

Alert whenever `DEFAULT` receives rows outside acceptable rules—not only when the database throws errors.

### 31.4. DEFAULT Is Not a "Catch-All" for HASH

HASH does not support `DEFAULT`; ensure hash bounds cover every possible remainder or accept routing errors when buckets are missing.

---

## 32. DETACH PARTITION and Old Data Archival Policies

### 32.1. Detach from Parent Before Archiving/Deleting

A standard retention workflow:

1. Confirm the data interval has expired.
2. Verify backups, archives, and legal/compliance holds.
3. Stop or coordinate any writers targeting that period.
4. Run `DETACH PARTITION` using the appropriate mode.
5. Verify the table is unlinked from the parent while its data remains in the standalone relation.
6. Archive/export, and then **DROP** once approved.

Example to run only in an authorized lab:

~~~sql
ALTER TABLE partition_lab.events
DETACH PARTITION partition_lab.events_2026_10;
~~~

After `DETACH`, `events_2026_10` is a standalone relation and no longer appears in `SELECT`s on the parent. **Its data has not been deleted.**

### 32.2. Dropping a Partition or Child Table Is Destructive

~~~sql
-- Illustrative only, after backup/authorization/approval:
DROP TABLE partition_lab.events_2026_10;
~~~

`DROP TABLE` deletes the relation, its indexes, and can affect dependencies; it cannot be rolled back once committed. For retention, it can be far faster than deleting hundreds of millions of rows, yet fast DDL **does not reduce the risk of deleting the wrong period**.

### 32.3. DETACH PARTITION CONCURRENTLY

In supported PostgreSQL versions, this form:

~~~sql
ALTER TABLE partition_lab.events
DETACH PARTITION partition_lab.events_2026_10 CONCURRENTLY;
~~~

reduces locking impact on the parent via a multi-phase process, with important restrictions:

- Cannot run inside an explicit transaction block.
- Has restrictions when the parent has a **DEFAULT partition**.
- May still wait on active transactions/snapshots.
- Can leave a pending detach state if interrupted, requiring completion via a recovery command such as `FINALIZE` in supported versions.
- May not apply to every subpartition/dependency scenario depending on version.

**Because the lab `events` table currently has a `DEFAULT` partition, the statement above is syntax-illustrative only—not a directly valid step across the whole lab scenario.** When a `DEFAULT` partition exists, evaluate non-concurrent `DETACH` or redesign your plan per your version's docs.

### 32.4. Late-Arriving Data

If you detach/drop the October partition and an October event arrives in November or December:

- With a `DEFAULT` partition, it lands in `DEFAULT`.
- Without one, `INSERT` fails.
- Having another partition with overlapping bounds is invalid.

Before purging, define a **late-arriving data window** and handling policy. Never assume an old month is settled based solely on the current calendar date.

### 32.5. Backups, Replication, and Dependencies

`DETACH`/`DROP` partition can impact:

- Queries/reports reading the parent or the child directly.
- Foreign keys and referencing relations.
- Logical replication/subscriptions or pipelines reading children.
- Backups, restores, and PITR.
- Index/statistics caches and monitoring tools.
- Replica replay/WAL and maintenance windows.

A fast DDL command does not remove the need to verify these side effects.

---

## 33. Increasing HASH Partitions: It's Not Just "Adding h4"

### 33.1. Four Buckets Already Cover Every Remainder

Parent `orders_hash` has four partitions with `MODULUS 4, REMAINDER 0..3`. Every key value already routes to a bucket.

You cannot add a fifth HASH partition with `MODULUS 4, REMAINDER 4`, because valid remainders are only 0..3.

Nor can you add another partition with `MODULUS 4, REMAINDER 1`, as bounds would overlap.

### 33.2. Moving to Eight Buckets Requires Redistribution

Mathematically, scaling splits each old hash group into two groups under `MODULUS 8`, yet PostgreSQL **does not redistribute existing data automatically** just because you declare new partitions.

A migration must account for:

- Which new tables/children will be created.
- Whether old and new bounds ever overlap during any step.
- How rows will be moved between tables/partitions.
- How concurrent reads and writes will stay synchronized.
- Local/global uniqueness requirements.
- Locks and WAL/replication impact of row movement.
- How to roll back without data loss.

### 33.3. A Controlled Migration Approach

For large tables, you typically plan a workflow like:

~~~text
Create new 8-bucket HASH table/tree in a separate schema
                  |
                  v
Copy/backfill data in controlled batches
                  |
                  v
Sync ongoing writes occurring during backfill
                  |
                  v
Verify data, keys, and indexes
                  |
                  v
Controlled cutover (app / table rename / routing)
                  |
                  v
Monitor, keep rollback path, then clean up old table
~~~

This is a **migration pattern**, not a complete SQL script. Actual implementation depends on traffic, FKs, sequences, constraints, and acceptable downtime.

### 33.4. More Buckets Do Not Fix a Hot Key

If customer 101 generates 70% of rows, increasing from 4 to 32 hash partitions still places **every row for that `customer_id` in the exact same partition**. Addressing hot keys requires workload changes, tenant isolation, time subpartitioning, or another architecture.

### 33.5. Pick the Bucket Count Up Front

Consider distinct key counts, data growth, target child size, retention, query patterns, CPU/I/O, and catalog overhead. Do not choose bucket counts purely based on CPU core counts when the real goal is query or retention management.

---

## 34. Managing LIST When Adding or Renaming Groups

### 34.1. A New Group Without DEFAULT

If a LIST parent has only north/south and no `DEFAULT`, `region='west'` fails on `INSERT`. To support west, create its partition:

~~~sql
CREATE TABLE partition_lab.support_tickets_west
PARTITION OF partition_lab.support_tickets
FOR VALUES IN ('west');
~~~

**However**, in our lab `DEFAULT` already contains `'west'`, so this command will be rejected until `'west'` rows are moved out of `DEFAULT`. The SQL above shows the **target form**, not an immediate command to run on the lab sample as-is.

### 34.2. Renaming a Region

If the business renames `'north'` to `'north_v2'`, options include:

- Normalizing the value in the application and updating rows appropriately.
- Creating a partition for the new value (or adding it to the LIST values) via proper DDL.
- Migrating old rows to the new group and checking compatibility.
- Preventing two distinct values from representing the same region and splitting counts/metrics.

Mutable LIST partition keys trigger costly **row movement**. Prefer stable codes like `region_id` paired with a dimension table for display labels if names change often.

### 34.3. Never Split One LIST Value Across Two Same-Level Partitions

You cannot create two partitions both using `FOR VALUES IN ('north')` to split north at the same LIST level. If `'north'` grows too large, **subpartition north** by RANGE/HASH or change your key/design.

---

## 35. VACUUM, ANALYZE, and Statistics on Partitioned Tables

### 35.1. Leaf Partitions Hold the Real Data

Autovacuum/`VACUUM` manages dead tuples, visibility/freezing, and statistics on each relation storing data. Leaf partitions hold physical rows and need maintenance just like regular tables.

Inspect stats:

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
WHERE schemaname = 'partition_lab'
ORDER BY relname;
~~~

`n_live_tup`/`n_dead_tup` are **estimates**, not exact counts, and statistics can lag behind writes.

### 35.2. Vacuuming a Single Partition

~~~sql
VACUUM (ANALYZE) partition_lab.events_2026_11;
~~~

Run outside an explicit transaction block. It cleans and analyzes one partition without requiring you to vacuum all other partitions just to keep one child healthy.

### 35.3. Analyzing the Parent

~~~sql
ANALYZE partition_lab.events;
~~~

For partitioned tables, the planner needs parent-level statistics for queries against the parent. PostgreSQL does not necessarily auto-analyze the parent merely because child partitions receive heavy `INSERT`/`UPDATE` traffic; autovacuum treats a rowless parent differently from leaf tables.

Consequently, many systems **explicitly run `ANALYZE` on the parent** after major data or partition changes, alongside autoanalyze on leaves.

### 35.4. Do Not Confuse Dead Tuples with a Reason to Repartition

A partition accumulating dead tuples may be caused by heavy `UPDATE`/`DELETE` or long-running snapshots blocking `VACUUM`; table bloat alone does not mean switching from RANGE to HASH is the answer.

### 35.5. Per-Partition Statistics Can Help or Hurt

A potential upside: a month with a distinct status distribution gets stats tailored to that month. Yet with too many tiny partitions, statistics become noisy and planning overhead climbs.

Never assume partitioning guarantees accurate cardinality estimates on its own.

---

## 36. Checking Sizes, Indexes, and Data Distribution

### 36.1. Size of Each Child

~~~sql
SELECT
    c.oid::regclass AS relation_name,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size,
    pg_total_relation_size(c.oid) AS bytes
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE n.nspname = 'partition_lab'
  AND c.relname LIKE 'events_%'
ORDER BY bytes DESC, relation_name::text;
~~~

Note that `_` in `LIKE 'events_%'` is a single-character SQL wildcard; in this controlled lab schema the naming is clear. In strict production scripts, filter using `pg_partition_tree` and parent-child catalogs rather than name patterns alone.

### 36.2. Counting Rows per Partition

~~~sql
SELECT
    tableoid::regclass AS partition_name,
    COUNT(*) AS row_count
FROM partition_lab.events
GROUP BY tableoid
ORDER BY row_count DESC, partition_name;
~~~

This scans real data across all partitions, so **do not run tree-wide `COUNT(*)` too frequently** on multi-billion-row production tables. For routine monitoring, use statistical estimates and verify with `COUNT(*)` only when warranted.

### 36.3. Inspecting Child Indexes

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'partition_lab'
  AND tablename IN (
      'events_2026_10',
      'events_2026_11',
      'events_2026_12',
      'events_other'
  )
ORDER BY tablename, indexname;
~~~

Check for:

- Local PK on each partition.
- Parent-propagated indexes.
- Child-specific indexes.
- Redundant or invalid indexes.

### 36.4. Monitoring the DEFAULT Partition

On a RANGE system with `DEFAULT`:

~~~sql
SELECT
    date_trunc('month', event_at) AS event_month,
    COUNT(*) AS events_in_default
FROM partition_lab.events_other
GROUP BY date_trunc('month', event_at)
ORDER BY event_month;
~~~

This reveals **the distribution of unpartitioned data**. If `DEFAULT` grows very large, use stats, batching, or alerts so this report does not become a recurring expensive full scan.

---

## 37. Locks, WAL, and Operating Partition DDL

### 37.1. CREATE PARTITION Is Not Completely "Lock-Free"

`CREATE TABLE ... PARTITION OF parent`, `ATTACH PARTITION`, `DETACH PARTITION`, and parent index/constraint changes all acquire relation locks at various strengths.

When migrating by attaching pre-loaded tables, bound/index validation can scan the table or `DEFAULT`, extending lock duration. Tiny lab DDLs do not reflect production table behavior.

### 37.2. Checking What Is Blocking DDL

~~~sql
SELECT
    a.pid,
    a.application_name,
    a.state,
    a.wait_event_type,
    a.wait_event,
    pg_blocking_pids(a.pid) AS blocking_pids,
    LEFT(a.query, 180) AS sql_sample
FROM pg_stat_activity AS a
WHERE a.datname = current_database()
  AND (
       a.wait_event_type = 'Lock'
       OR cardinality(pg_blocking_pids(a.pid)) > 0
  )
ORDER BY a.pid;
~~~

A long transaction or `idle in transaction` session holding a lock can stall schema changes. Never blindly terminate a blocker without checking its owner and impact.

### 37.3. Timeouts in Migrations

Lab example:

~~~sql
BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '30s';

-- A brief DDL once everything is prepared:
-- ALTER TABLE ... ATTACH PARTITION ...

ROLLBACK;
~~~

`SET LOCAL` is transaction-scoped. If `lock_timeout` or `statement_timeout` aborts a statement, the transaction enters an aborted state and requires `ROLLBACK` or a valid savepoint. For `DETACH PARTITION CONCURRENTLY` and `CREATE INDEX CONCURRENTLY`—which cannot run inside `BEGIN`—configure timeouts at the session/job level per policy and reset them afterward.

### 37.4. Metadata Changes Can Affect Replication

Creating/attaching/detaching/dropping partitions, building indexes, and backfilling all generate WAL or alter schemas that downstream logical decoding or replicas must handle appropriately. Never assume "dropping a partition doesn't delete row by row" means replicas and backups are unaffected.

### 37.5. Separate High Availability from Partitioning

A partitioned table is still data inside one PostgreSQL database. It does not replace replication, backups, failover, or disaster recovery. Whenever altering partition lifecycles, assess the impact on primaries, standbys, logical replication, and downstream consumers.

---

## 38. Migrating a Large Unpartitioned Table to a Partitioned Table

### 38.1. You Cannot Simply ALTER a Regular Table into a RANGE Parent in One Step

In practice, converting a large heap table to partitioning almost always requires **building a new partitioned table and migrating/cutting over data**, rather than running a universal in-place `ALTER TABLE old PARTITION BY RANGE (...)`.

### 38.2. Architectural Workflow

~~~text
Old table: orders_old
          |
          v
Analyze workload, partition key, PK/UNIQUE/FK
          |
          v
Create orders_new PARTITION BY ...
          |
          v
Create child partitions, indexes, constraints
          |
          v
Backfill in batches; verify row counts/keys
          |
          v
Sync ongoing writes during migration
          |
          v
Controlled cutover (app routing / renaming)
          |
          v
Monitor, keep rollback plan, clean up old only when safe
~~~

### 38.3. Issues You Cannot Overlook

- An old PK on `order_id` alone cannot be kept on a new parent partitioned by `created_at`.
- Existing FKs from other tables referencing the old table's name/OID.
- Triggers, RLS policies, grants, sequences/identities, generated columns, and replication publications.
- Real-time writes arriving during backfill.
- Guaranteeing zero missing or duplicate rows at cutover.
- Index/constraint validation and lock durations.
- Rolling back if a service still depends on the old schema.

### 38.4. Never Rely on a Simple Rename Without Addressing Dependencies

`ALTER TABLE old RENAME TO ...` renames a relation, but **does not automatically rewire FKs, views, triggers, or privileges** onto a new table as intended. Design the migration with dependency checks and proper cutover mechanics rather than just swapping names.

### 38.5. Prioritize Data Correctness Over a Rushed Cutover

If a backfill step fails, you must know how to resume, detect missing rows, validate checksums/samples, and avoid losing in-flight writes. Partitioning pays off long term, whereas a botched cutover can cause immediate business data loss.

---

## 39. When Not to Partition

Partitioning is usually suboptimal if:

1. The table has only thousands to a few million rows and queries are already fast with B-tree/BRIN indexes.
2. Queries do not filter by the partition key and consistently scan all children.
3. Global `UNIQUE`/`PK` is needed on a column excluding the partition key and you cannot change the schema.
4. Distinct group counts are tiny or extreme skew prevents HASH/LIST from distributing load.
5. The partition key mutates frequently, causing heavy row movement.
6. Splitting too finely makes catalog/lock/planning overhead exceed any gains.
7. Automation for pre-creating partitions, retention, backups, and monitoring is missing.
8. You only need higher read throughput while the true bottleneck is bad joins, excessive `SELECT *`, network, or connection pooling.
9. The true goal is **multi-node sharding**; local partitioning cannot achieve that.
10. The workload continually aggregates all history, so partitioning helps management without removing the compute cost.

Before migrating to partitioned tables, benchmark a regular table with proper indexes and SQL tuning. Good optimization meets the goal—it doesn't add unnecessary complexity.

---

## 40. Common Errors and Misconceptions

| Misconception or Error | Consequence | Reality / Fix |
|---|---|---|
| "Partitioning makes every SELECT faster automatically" | Queries without the key still read many partitions | Check pruning and scan strategies |
| "The partitioned parent stores rows like a regular table" | Misunderstands `ONLY parent` and heap size | Physical rows live in leaf partitions |
| "RANGE upper bounds are inclusive" | First-of-month rows land in the wrong partition | Remember `[lower, upper)` |
| "October ends at 23:59:59" | Misses sub-second timestamps | Use next month's start as exclusive upper bound |
| "Multi-column RANGE is a 2D rectangle" | Unexpected bound acceptance | Multi-key RANGE compares lexicographically |
| "RANGE puts NULL in the nearest partition" | `INSERT NULL` fails with no partition found | Use `NOT NULL`, `DEFAULT`, or normalize |
| "LIST('north') also matches 'North'" | Routes to `DEFAULT` or errors | Normalize case or key |
| "LIST cannot accept NULL" | Incomplete syntax understanding | `FOR VALUES IN (NULL)` or `DEFAULT` |
| "LIST allows two children for 'north'" | Overlapping bounds are rejected | Subpartition if one group grows too large |
| "HASH is customer_id % N" | Predicts the wrong child | Routing uses hash operator classes |
| "HASH supports DEFAULT" | Invalid DDL | Cover all HASH remainders explicitly |
| "4 HASH buckets always split rows 25% each" | One hot key skews a partition | Measure skew and distinct keys |
| "To grow from 4 to 8 buckets, just add h4" | Invalid/overlapping bounds, no data movement | Plan an explicit rehash/repartition migration |
| "RANGE and HASH are multi-server sharding" | False resource expectations | Partitioning stays local to one database |
| "Creating a parent index creates a global index" | Misunderstands table-wide `UNIQUE` | Parent index is logical; child indexes are physical |
| "PK(event_id) works even when partitioned by event_at" | Constraint is rejected | Parent PK/UNIQUE must include partition key |
| "PK(event_at,event_id) makes event_id unique" | Duplicate `event_id` across different `event_at` | Understand composite key semantics |
| "CREATE INDEX CONCURRENTLY always works on a partitioned parent" | Rejected under current limitations | Build leaf indexes concurrently and attach |
| "A matching index name means it's usable" | Index might be `INVALID` | Inspect `pg_index.indisvalid` |
| "No need to pre-create next month because DEFAULT exists" | `DEFAULT` bloats and blocks `ATTACH` | Pre-create ahead and monitor `DEFAULT` |
| "ATTACH is metadata-only so zero scans/locks" | DDL may block and scan child/`DEFAULT` | Pre-validate `CHECK`, inspect locks |
| "Even with March rows in DEFAULT, ATTACH March works" | Rejected / unsafe | Migrate data with controlled cutover |
| "DETACH means DELETE" | Data remains in standalone table | Distinguish `DETACH` from `DROP` |
| "Dropping a partition is harmless because it's fast" | Loses an entire period's data | Verify retention, backups, and approval |
| "DETACH CONCURRENTLY works on any parent" | Hits `DEFAULT`/transaction restrictions | Check version rules and prerequisites |
| "Updating the partition key just updates one field" | Moves rows across leaves, adds WAL/locks | Design immutable keys where possible |
| "ON CONFLICT moves partitions freely" | Rejected on `DO UPDATE` row movement | Know row-movement limitations |
| "Pruning requires an index" | Unnecessary index creation | Pruning uses bounds; indexes accelerate inside children |
| "EXPLAIN showing Seq Scan means pruning didn't run" | Seq Scan on one small leaf is normal | Check which children were scanned |
| "EXTRACT(MONTH) = 11 equals November 2026" | Matches every November; hinders range pruning | Use explicit year-aware ranges |
| "UI timezone doesn't affect RANGE design" | Local-day data falls into a different UTC month | Pin timezone and bounds explicitly |
| "Enabling partitionwise join always improves performance" | Increases planning time/memory | Benchmark against your workload |
| "One partition per row is best" | Severe metadata/lock/planning overhead | Pick operational granularity |
| "Leaf autovacuum keeps parent stats fresh" | Parent planner stats can go stale | Monitor and run `ANALYZE` on parent |
| "Migrating a regular table via RENAME is enough" | FKs/views/triggers/dependencies break or stay tied | Plan full dependency-aware cutover |
| "Deleting 100M rows behaves like dropping a partition" | Vastly different WAL/dead tuples/maintenance | Use partition retention when aligned with policy |

---

## 41. Real-World Scenario 1: Access Logs Retained for 90 Days

### 41.1. Requirements

A system has:

- 20 million events/day.
- Queries usually target the last 1–3 days.
- Data must be kept for 90 days and old periods deleted quickly.
- Queries routinely filter `tenant_id` within an `event_at` range.
- Events can arrive up to 48 hours late.

### 41.2. Analysis of Options

**Daily `RANGE(event_at)`** is a strong candidate because both retention and primary predicates are time-based.

Monthly partitions would hold ~600 million events each—very large. Hourly partitions over 90 days would mean 90 × 24 = 2,160 partitions with higher overhead. Daily partitioning leaves ~90 active leaf partitions, a sensible starting point to benchmark.

### 41.3. Reference Design

~~~sql
CREATE TABLE partition_lab.access_logs (
    log_id BIGINT NOT NULL,
    tenant_id INTEGER NOT NULL,
    event_at TIMESTAMPTZ NOT NULL,
    path TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    PRIMARY KEY (event_at, log_id)
)
PARTITION BY RANGE (event_at);
~~~

Example day:

~~~sql
CREATE TABLE partition_lab.access_logs_2026_11_14
PARTITION OF partition_lab.access_logs
FOR VALUES FROM ('2026-11-14 00:00:00+00')
           TO   ('2026-11-15 00:00:00+00');
~~~

Index:

~~~sql
CREATE INDEX idx_access_logs_tenant_time
ON partition_lab.access_logs (tenant_id, event_at DESC);
~~~

Query:

~~~sql
SELECT log_id, event_at, path, status_code
FROM partition_lab.access_logs
WHERE tenant_id = 11
  AND event_at >= TIMESTAMPTZ '2026-11-13 00:00:00+00'
  AND event_at <  TIMESTAMPTZ '2026-11-15 00:00:00+00'
ORDER BY event_at DESC
LIMIT 100;
~~~

### 41.4. Lifecycle

- Pre-create partitions several days ahead.
- Monitor `DEFAULT` (if used) and routing errors.
- Retention considers only partitions whose entire bound has expired **and** cleared the 48-hour late-arrival window.
- Archive/back up, `DETACH` cleanly, verify, and only then `DROP`.
- Track daily partition sizes, autovacuum/index bloat, and replica lag.
- Keep parent/leaf statistics up to date.

### 41.5. Subtle Risk

`PK(event_at,log_id)` does not ensure `log_id` is unique across different `event_at` values. If APIs treat `log_id` as a standalone identifier, establish a separate ID generation/enforcement mechanism or pass the full composite key; never deploy to production before resolving that invariant.

---

## 42. Real-World Scenario 2: Regional Customer Data

### 42.1. Requirements

A company operates across `north`/`south`/`west` regions, each with distinct maintenance policies. Reporting queries typically filter by exact region, and customers rarely switch regions.

### 42.2. LIST Can Fit Well

~~~sql
CREATE TABLE partition_lab.region_orders (
    order_id BIGINT NOT NULL,
    region TEXT NOT NULL,
    customer_id BIGINT NOT NULL,
    placed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (region, order_id)
)
PARTITION BY LIST (region);

CREATE TABLE partition_lab.region_orders_north
PARTITION OF partition_lab.region_orders
FOR VALUES IN ('north');

CREATE TABLE partition_lab.region_orders_south
PARTITION OF partition_lab.region_orders
FOR VALUES IN ('south');

CREATE TABLE partition_lab.region_orders_west
PARTITION OF partition_lab.region_orders
FOR VALUES IN ('west');
~~~

### 42.3. Query

~~~sql
EXPLAIN
SELECT order_id, customer_id, placed_at
FROM partition_lab.region_orders
WHERE region = 'north'
  AND placed_at >= TIMESTAMPTZ '2026-11-01 00:00+00';
~~~

This can prune south and west. If `'north'` holds 95% of rows, pruning alone will not make north queries fast; local indexes and possibly subpartitioning are needed.

### 42.4. Avoid Using Status Instead of Region When Status Changes Often

If `status='new'` constantly transitions to `'paid'`, `LIST(status)` forces many `UPDATE`s to move rows across partitions. `region` may be stabler; still, if customers switch regions often, factor in row movement, uniqueness, and FKs.

---

## 43. Real-World Scenario 3: Multi-Tenant Table Always Queried by tenant_id

### 43.1. Requirements

A SaaS application serves 50,000 tenants; queries are mostly `WHERE tenant_id = ?`, with minimal time-based retention needs. Each tenant has a modest number of rows.

### 43.2. HASH Is a Candidate

~~~sql
CREATE TABLE partition_lab.tenant_messages (
    tenant_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    sent_at TIMESTAMPTZ NOT NULL,
    body TEXT NOT NULL,
    PRIMARY KEY (tenant_id, message_id)
)
PARTITION BY HASH (tenant_id);

CREATE TABLE partition_lab.tenant_messages_h0
PARTITION OF partition_lab.tenant_messages
FOR VALUES WITH (MODULUS 4, REMAINDER 0);

CREATE TABLE partition_lab.tenant_messages_h1
PARTITION OF partition_lab.tenant_messages
FOR VALUES WITH (MODULUS 4, REMAINDER 1);

CREATE TABLE partition_lab.tenant_messages_h2
PARTITION OF partition_lab.tenant_messages
FOR VALUES WITH (MODULUS 4, REMAINDER 2);

CREATE TABLE partition_lab.tenant_messages_h3
PARTITION OF partition_lab.tenant_messages
FOR VALUES WITH (MODULUS 4, REMAINDER 3);
~~~

### 43.3. Query

~~~sql
EXPLAIN
SELECT message_id, sent_at, body
FROM partition_lab.tenant_messages
WHERE tenant_id = 12345
ORDER BY sent_at DESC
LIMIT 50;
~~~

HASH can prune down to a single bucket. However, if that bucket holds millions of messages across many tenants, the query still needs a local index `(tenant_id,sent_at DESC)`.

### 43.4. Do Not Treat HASH as a Hot-Tenant Cure

If a single tenant produces 60% of all messages, it sits entirely inside one bucket; the imbalance remains unresolved. You may need a different partition strategy, a time dimension, or dedicated isolation for massive tenants.

### 43.5. What If Time-Based Deletion Is Required?

If 30-day retention is critical, plain HASH does not allow dropping old data via time partitions. Consider **`RANGE(time)` followed by `HASH(tenant)`**, or `RANGE(time)` alone with a local tenant index, carefully weighing partition counts and constraint impacts.

---

## 44. Practice Exercises

Exercises assume `partition_lab` and the tables created across previous sections exist. Some SQL exercises **do not necessarily need to be executed live** if earlier labs altered data/partitions. Work on an isolated database, and avoid `DELETE`/`DROP` without a recovery plan.

### Exercise 1 — Concepts

Explain declarative partitioning, parent table, leaf partition, partition key, and partition pruning. Does partitioning automatically distribute data across multiple PostgreSQL servers?

### Exercise 2 — Choosing a Strategy

For a 300-million-row application log queried by month and purged after two years, should you consider RANGE, LIST, or HASH? Why?

### Exercise 3 — RANGE Syntax

Write a statement to create `monthly_sales` with `sale_id BIGINT`, `sold_at DATE`, `amount NUMERIC`, partitioned by `sold_at`.

### Exercise 4 — November RANGE

Write the statement to create a partition accepting `sold_at` in November 2026 and explain its lower and upper bounds.

### Exercise 5 — Boundary Case

Does `2026-11-01 00:00:00+00` belong to October `[Oct 1,Nov 1)` or November `[Nov 1,Dec 1)`?

### Exercise 6 — MINVALUE/MAXVALUE

Write two partitions for `range_demo(score)`: one accepting scores below 0, and one accepting scores 0 and above. Does `NULL` automatically land in a RANGE partition?

### Exercise 7 — Multi-Column RANGE

With key `(tenant_id,seq_no)`, does bound `FROM(1,0) TO(2,0)` accept rows `(1,9999)` and `(2,0)`? Why or why not?

### Exercise 8 — DEFAULT RANGE

A January 2027 event is inserted when only October–December 2026 partitions and `DEFAULT` exist. Where does it go? What if `DEFAULT` does not exist?

### Exercise 9 — tableoid

Write SQL returning `event_id`, `event_at`, and the physical partition name holding each row. Why should apps query the parent while using `tableoid` only for diagnostics?

### Exercise 10 — Parent Only

What is `SELECT COUNT(*) FROM ONLY partition_lab.events` expected to return in the lab? Why?

### Exercise 11 — LIST Syntax

Create `tickets_by_region` partitioned by `region TEXT` and one child accepting `'north'` and `'northern'`.

### Exercise 12 — LIST NULL

Write a LIST child accepting `NULL` and a query selecting only tickets where `region IS NULL`. Why is `region = NULL` wrong?

### Exercise 13 — LIST DEFAULT

With LIST north/south and `DEFAULT`, where does `'west'` go? Describe the risk when `DEFAULT` already holds `'west'` and you try to `ATTACH` a dedicated west partition.

### Exercise 14 — LIST Case Sensitivity

Why shouldn't `region='North'` be assumed identical to `'north'`? How would you normalize it?

### Exercise 15 — HASH Syntax

Create a parent `hash_events(tenant_id BIGINT,event_id BIGINT)` partitioned by `tenant_id` with four children of modulus 4, remainders 0..3.

### Exercise 16 — HASH Routing

Can you determine the target child just by computing `tenant_id % 4`? How do you observe actual routing?

### Exercise 17 — HASH DEFAULT

Can HASH declare `FOR VALUES DEFAULT`? What happens if a required remainder is missing?

### Exercise 18 — Hot Key

One tenant produces 80% of events. Does `HASH(tenant_id)` with 16 buckets spread that tenant's workload evenly across 16 partitions?

### Exercise 19 — RANGE Pruning

Write an `EXPLAIN` query filtering events from Nov 10 to before Nov 20, 2026 UTC. Which children can PostgreSQL prune?

### Exercise 20 — HASH Pruning

Write a query finding `orders_hash` rows for customer 101. If a query filters only by `order_id`, does it prune down to one bucket?

### Exercise 21 — Pruning vs. Indexes

A plan performs only a Seq Scan on `events_2026_11` for a November query. Does that mean partition pruning failed?

### Exercise 22 — Pruning with Expressions

Why is `EXTRACT(MONTH FROM event_at)=11` not equivalent to November 2026, and why can it hinder pruning?

### Exercise 23 — Timezones

What local date is `2026-10-31 20:00+00` in Vietnam? Under UTC monthly RANGE partitions, does it go into October or November?

### Exercise 24 — Parent PRIMARY KEY

Why is `PRIMARY KEY(event_id)` invalid on a `RANGE(event_at)` table under standard partitioned parent PK rules? Which key is valid in the lab, and what uniqueness limitation does it have?

### Exercise 25 — Global UNIQUE

If `event_id` must be globally unique across the database regardless of `event_at`, is `PRIMARY KEY(event_at,event_id)` enough? Propose a safe data modeling strategy.

### Exercise 26 — Local Indexes

Write a parent index serving `WHERE tenant_id=? AND event_at BETWEEN... ORDER BY event_at DESC`. Where are the physical indexes created?

### Exercise 27 — CREATE INDEX CONCURRENTLY

Why can't you routinely run `CREATE INDEX CONCURRENTLY ON partitioned_parent(...)`? Outline the workflow using `ON ONLY` on the parent, building leaf indexes concurrently, and attaching them.

### Exercise 28 — UPDATE Row Movement

A November event updates `event_at` to December. Does the row move? What operational risks arise?

### Exercise 29 — ON CONFLICT

Why doesn't `ON CONFLICT(event_at,event_id) DO NOTHING` prevent the same `event_id` at two different timestamps?

### Exercise 30 — Subpartitioning

Write a schema partitioned by `RANGE(event_at DATE)` at level 1 and `HASH(tenant_id)` modulus 2 at level 2 for November 2026. State the total leaf count across 12 months × 2 buckets.

### Exercise 31 — Catalogs

Write a `pg_partition_tree` query for `events` and a query inspecting partition bounds via `pg_inherits`/`pg_class`.

### Exercise 32 — ATTACH Existing

A standalone table holds March 2027 data and needs attaching to `events`. Why is a validated `CHECK` bound on the standalone table helpful?

### Exercise 33 — DEFAULT Holding Overlapping Rows

`DEFAULT` holds March 2027 rows. Can you attach a March partition without moving data? Outline a conceptually safe migration workflow.

### Exercise 34 — DETACH vs. DROP

Contrast `DETACH PARTITION` and `DROP TABLE` regarding parent query visibility and physical data deletion.

### Exercise 35 — DETACH CONCURRENTLY

List at least three conditions/limitations to check before using `DETACH PARTITION CONCURRENTLY`. Can you run it directly on the lab `events` parent while it has a `DEFAULT` partition?

### Exercise 36 — HASH Rebalancing

A parent has all 4 partitions for modulus 4. Why can't you just add "remainder 4"? What must you plan to scale to 8 buckets?

### Exercise 37 — Autoanalyze

Why might the parent need a manual `ANALYZE` even when leaf partitions have fresh stats? Write the command.

### Exercise 38 — Retention

A daily logs table drops data older than 90 days while events can arrive up to 48 hours late. What must be verified before detaching/dropping a partition?

### Exercise 39 — New Partition Lifecycle

Write a checklist for preparing next month's RANGE partition to avoid writing into `DEFAULT` or hitting no-partition-found errors.

### Exercise 40 — Architecture Synthesis

A system has 10,000 tenants, billions of orders, 95% of queries filtering by `tenant_id` and a one-month range, and 2-year retention. Propose at least two viable partitioning strategies, compare pros/cons, and address leaf partition counts, parent PK/UNIQUE, and ingest speed.

---

## 45. Suggested Solutions

### Exercise 1 — Concepts

Declarative partitioning defines a **logical parent table** via `PARTITION BY` and bounded child tables. Physical rows are stored in **leaf partitions**; PostgreSQL routes `INSERT`s and can prune partitions unable to match `WHERE`. Partitioning inside one PostgreSQL database **does not shard across multiple servers**.

### Exercise 2 — Choosing RANGE for Time-Based Retention

**`RANGE(event_at)`** is a strong candidate because queries filter by month and old-data purging is also time-based. Once a partition passes retention and late-arrival windows, you can `DETACH`/`DROP` it instead of deleting millions of rows. Pick monthly vs. daily sizing after measuring data/index volume and partition counts.

### Exercise 3 — Creating a RANGE Parent

~~~sql
CREATE TABLE partition_lab.monthly_sales (
    sale_id BIGINT NOT NULL,
    sold_at DATE NOT NULL,
    amount NUMERIC(12,2) NOT NULL
)
PARTITION BY RANGE (sold_at);
~~~

If a PK is needed on the parent, it must include `sold_at` per partitioned `UNIQUE`/`PK` rules. Never blindly add `PRIMARY KEY(sale_id)` on a `RANGE(sold_at)` parent.

### Exercise 4 — November Partition

~~~sql
CREATE TABLE partition_lab.monthly_sales_2026_11
PARTITION OF partition_lab.monthly_sales
FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');
~~~

The lower bound `2026-11-01` is inclusive; the upper bound `2026-12-01` is exclusive. Every November date goes here, and December starts in the next partition.

### Exercise 5 — Boundary Case

`2026-11-01 00:00:00+00` belongs to **November**, not October. RANGE uses inclusive lower bounds and exclusive upper bounds.

### Exercise 6 — MINVALUE/MAXVALUE

On `range_demo(score)`, you could create:

~~~sql
CREATE TABLE partition_lab.range_demo_negative
PARTITION OF partition_lab.range_demo
FOR VALUES FROM (MINVALUE) TO (0);

CREATE TABLE partition_lab.range_demo_nonnegative
PARTITION OF partition_lab.range_demo
FOR VALUES FROM (0) TO (MAXVALUE);
~~~

These two statements are **an alternative** to `range_demo_low/mid/high` from Section 7; do not run both designs on the same parent because their bounds overlap.

`NULL` does not fall inside any RANGE bound automatically; handle `NULL` via `DEFAULT` or enforce `NOT NULL` on the key.

### Exercise 7 — Multi-Column RANGE

With lexicographical bounds `[(1,0),(2,0))`:

- `(1,9999)`: **accepted**, because the first key `1` is less than the upper bound's first key `2`.
- `(2,0)`: **rejected**, because it equals the exclusive upper bound.

Do not interpret multi-column RANGE as two independent numeric intervals.

### Exercise 8 — DEFAULT RANGE

On an `events` parent with `DEFAULT`, January 2027 has no dedicated partition, so the row goes to `events_other`. Without `DEFAULT` and without a January partition, `INSERT` raises a no-partition-found error.

### Exercise 9 — tableoid

~~~sql
SELECT
    event_id,
    event_at,
    tableoid::regclass AS physical_partition
FROM partition_lab.events
ORDER BY event_at, event_id;
~~~

Applications should normally `INSERT`/`SELECT` against the parent to stay decoupled from child names. `tableoid` is useful for diagnosing routing and spotting misplaced rows.

### Exercise 10 — ONLY Parent

~~~sql
SELECT COUNT(*)
FROM ONLY partition_lab.events;
~~~

Expected **0**, because a declarative partitioned parent stores no regular heap rows. Do not use `ONLY` in business queries meant to read leaf partition data.

### Exercise 11 — LIST Syntax

~~~sql
CREATE TABLE partition_lab.tickets_by_region (
    ticket_id BIGINT NOT NULL,
    region TEXT,
    subject TEXT NOT NULL
)
PARTITION BY LIST (region);

CREATE TABLE partition_lab.tickets_by_region_north
PARTITION OF partition_lab.tickets_by_region
FOR VALUES IN ('north', 'northern');
~~~

Other groups need their own children or `DEFAULT` before inserting non-north values.

### Exercise 12 — LIST NULL

~~~sql
CREATE TABLE partition_lab.tickets_by_region_null
PARTITION OF partition_lab.tickets_by_region
FOR VALUES IN (NULL);

SELECT ticket_id, subject
FROM partition_lab.tickets_by_region
WHERE region IS NULL;
~~~

`= NULL` evaluates to `UNKNOWN` in SQL three-valued logic; only `IS NULL` properly checks for `NULL`.

### Exercise 13 — DEFAULT and New Groups

`'west'` routes to `DEFAULT` if no west child exists. When you want to attach a dedicated west partition, `DEFAULT` **must contain no `'west'` rows**. If any exist, migrate them cleanly before attaching; never delete data just to make DDL pass.

### Exercise 14 — Case Sensitivity

`'north'` and `'North'` are typically distinct text values under standard collation/operator-class semantics. Normalize to lowercase at ingestion or use a stable `region_code`. If using an expression key `lower(region)`, check parent `PK`/`UNIQUE` limits and function/locale properties.

### Exercise 15 — Creating HASH

~~~sql
CREATE TABLE partition_lab.hash_events (
    tenant_id BIGINT NOT NULL,
    event_id BIGINT NOT NULL
)
PARTITION BY HASH (tenant_id);

CREATE TABLE partition_lab.hash_events_h0
PARTITION OF partition_lab.hash_events
FOR VALUES WITH (MODULUS 4, REMAINDER 0);

CREATE TABLE partition_lab.hash_events_h1
PARTITION OF partition_lab.hash_events
FOR VALUES WITH (MODULUS 4, REMAINDER 1);

CREATE TABLE partition_lab.hash_events_h2
PARTITION OF partition_lab.hash_events
FOR VALUES WITH (MODULUS 4, REMAINDER 2);

CREATE TABLE partition_lab.hash_events_h3
PARTITION OF partition_lab.hash_events
FOR VALUES WITH (MODULUS 4, REMAINDER 3);
~~~

All four remainders for modulus 4 are covered, routing keys across these bounds.

### Exercise 16 — HASH Routing

No. PostgreSQL uses its hash support function and partitioning semantics, not plain SQL modulo on `tenant_id`. Observe via:

~~~sql
SELECT tenant_id, event_id,
       tableoid::regclass AS target_partition
FROM partition_lab.hash_events
ORDER BY tenant_id, event_id;
~~~

Insert lab rows first so there is data to inspect.

### Exercise 17 — HASH DEFAULT

HASH has no `DEFAULT` partition. For any modulus/remainder missing a child, keys hashing to that remainder fail with no partition found.

### Exercise 18 — Hot Key

No. All rows with the same `tenant_id` route to **the same bucket**. HASH distributes distinct tenants, not a single massive tenant across 16 buckets. Consider time subpartitioning or an alternative design.

### Exercise 19 — RANGE Pruning

~~~sql
EXPLAIN
SELECT event_id, event_at
FROM partition_lab.events
WHERE event_at >= TIMESTAMPTZ '2026-11-10 00:00+00'
  AND event_at <  TIMESTAMPTZ '2026-11-20 00:00+00';
~~~

Bounds intersect only November, so PostgreSQL can prune October, December, and `DEFAULT`. With execution-time parameters/pruning, plan output can vary; inspect actual executed nodes.

### Exercise 20 — HASH Pruning

~~~sql
EXPLAIN
SELECT order_id, customer_id, amount
FROM partition_lab.orders_hash
WHERE customer_id = 101;
~~~

Can prune down to one HASH bucket. With only `WHERE order_id = 1`, `customer_id` is unknown, so all buckets typically must be checked.

### Exercise 21 — Seq Scan Can Still Reflect Good Pruning

No. If only `events_2026_11` is scanned, pruning eliminated all other children. Picking a Seq Scan on a small leaf is an independent cost-based choice. A local index becomes helpful once the leaf grows large and predicates are selective.

### Exercise 22 — EXTRACT MONTH

`EXTRACT(MONTH FROM event_at)=11` matches **November of every year**, not just 2026. PostgreSQL also cannot easily invert arbitrary function expressions into direct `event_at` bounds. Use a half-open range with full dates and timezone to specify the exact window.

### Exercise 23 — Timezone

`2026-10-31 20:00+00` corresponds to **2026-11-01 03:00** in Vietnam (+07). Since the parent partitions months in **UTC**, the row lands in **October** because the instant precedes `2026-11-01 00:00+00`.

### Exercise 24 — Parent PRIMARY KEY

A `RANGE(event_at)` parent uses local child indexes. `PK(event_id)` excludes the partition key and cannot be enforced globally under declarative partitioning rules. The lab uses:

~~~sql
PRIMARY KEY (event_at, event_id)
~~~

This composite PK is valid, yet only guarantees uniqueness of the **pair**; identical `event_id` values with different `event_at` timestamps can still exist.

### Exercise 25 — System-Wide Unique event_id

Not sufficient on its own. Options include:

- An unpartitioned registry table with `event_id PRIMARY KEY`, written in the same transaction as the event.
- A global ID generator (sequence/UUID/Snowflake-like) paired with application uniqueness controls, while **not mistaking the generator for a database-enforced global unique constraint** on the parent.
- Redesigning the partition key/PK or data model if the invariant must be strictly enforced by the database in all cases.

Choose based on transaction, FK, and scaling requirements; never rely purely on low UUID collision probability to ignore data contracts.

### Exercise 26 — Index for Tenant + Time

~~~sql
CREATE INDEX idx_events_tenant_time_answer
ON partition_lab.events(tenant_id, event_at DESC);
~~~

The parent index is logical; leaf partitions hold the corresponding physical indexes. Monthly queries prune first and use the local index afterward. If an equivalent index already exists from earlier steps, do not create a duplicate.

### Exercise 27 — Concurrent Index Build

Do not run `CREATE INDEX CONCURRENTLY` directly on the parent when your PostgreSQL version forbids it. Workflow:

1. Run `CREATE INDEX ... ON ONLY parent` to create the parent metadata index initially unattached/invalid.
2. Run `CREATE INDEX CONCURRENTLY` on each leaf **outside a transaction block**.
3. Run `ALTER INDEX parent_index ATTACH PARTITION child_index` for each valid, matching child index.
4. Verify all leaf indexes are attached and the parent's `indisvalid` is true.
5. If any build fails, clean up the invalid index before retrying.

### Exercise 28 — Row Movement

Updating the partition key from November to December can move the row version between leaf partitions via internal delete+insert mechanics. This increases WAL, index maintenance, and row locks, and can hit conflicts; if December is missing, the `UPDATE` fails. Choose stable keys whenever possible.

### Exercise 29 — ON CONFLICT

`ON CONFLICT(event_at,event_id)` only detects duplicates where **both columns match**. Matching `event_id` with a different timestamp does not violate the composite PK. Global `event_id` uniqueness requires a separate model/invariant.

### Exercise 30 — Subpartitioning

~~~sql
CREATE TABLE partition_lab.multi_demo (
    event_at DATE NOT NULL,
    tenant_id BIGINT NOT NULL,
    event_id BIGINT NOT NULL
)
PARTITION BY RANGE(event_at);

CREATE TABLE partition_lab.multi_demo_2026_11
PARTITION OF partition_lab.multi_demo
FOR VALUES FROM ('2026-11-01') TO ('2026-12-01')
PARTITION BY HASH(tenant_id);

CREATE TABLE partition_lab.multi_demo_2026_11_h0
PARTITION OF partition_lab.multi_demo_2026_11
FOR VALUES WITH(MODULUS 2, REMAINDER 0);

CREATE TABLE partition_lab.multi_demo_2026_11_h1
PARTITION OF partition_lab.multi_demo_2026_11
FOR VALUES WITH(MODULUS 2, REMAINDER 1);
~~~

12 months × 2 buckets = **24 leaf partitions**, plus intermediate parent levels and indexes. Queries touching months outside November need corresponding level-1 and level-2 partitions created.

### Exercise 31 — Catalogs

~~~sql
SELECT
    relid::regclass AS relation_name,
    parentrelid::regclass AS parent_name,
    isleaf,
    level
FROM pg_partition_tree('partition_lab.events'::regclass)
ORDER BY level, relid::text;
~~~

~~~sql
SELECT
    child.oid::regclass AS child_name,
    pg_get_expr(child.relpartbound, child.oid) AS bound
FROM pg_inherits AS i
JOIN pg_class AS child ON child.oid = i.inhrelid
WHERE i.inhparent = 'partition_lab.events'::regclass
ORDER BY child.oid;
~~~

Both queries inspect structure/metadata only; never update catalogs directly.

### Exercise 32 — CHECK Before ATTACH

A standalone table with a validated `CHECK` proving every row falls in `[2027-03-01,2027-04-01)` lets PostgreSQL **skip the bound-verification scan** during `ATTACH`. This shortens the attach lock/scan phase, though creating and validating the constraint and indexes beforehand still has its own cost.

### Exercise 33 — DEFAULT Holding Overlapping Rows

You cannot attach directly while `DEFAULT` holds rows matching the new partition. Steps:

1. Prepare the standalone partition with matching schema and bounds.
2. Coordinate writes so no new overlapping rows hit `DEFAULT` during cutover.
3. Copy/move March rows to the standalone table.
4. Verify completeness, uniqueness, and constraints.
5. Delete March rows from `DEFAULT` once safely stored and no writes were missed.
6. `ATTACH` in a controlled window; verify parent `SELECT`, `tableoid`, and row counts.
7. Maintain a rollback plan if any step fails.

On high-volume production tables, use proper dual-write/transaction/CDC sync rather than a naive short `DELETE + ATTACH` script.

### Exercise 34 — DETACH vs. DROP

`DETACH PARTITION` converts the child into a standalone relation; data remains intact, though **`SELECT` on the parent no longer reads it**. `DROP TABLE` destroys the relation and its data, requiring backups and recovery planning. Retention typically `DETACH`es, verifies, and archives before dropping.

### Exercise 35 — DETACH CONCURRENTLY

Check:

1. Does the PostgreSQL version support it?
2. Is it running outside a transaction block?
3. Does the parent have a `DEFAULT` partition (a key restriction)?
4. How to handle pending detach states after failure, such as `FINALIZE`.
5. FKs/dependencies, long transactions, lock waits, and traffic.

**The lab `events` parent has `DEFAULT`**, so `DETACH CONCURRENTLY` cannot be used directly on it as a drop-in example.

### Exercise 36 — HASH Rebalancing

`MODULUS 4` covers only remainders 0..3; remainder 4 is invalid. Moving to 8 buckets requires transitioning from old bounds to new ones, migrating/syncing data, handling concurrent writes, indexes/constraints, WAL/locks, and cutover. Creating a fresh 8-bucket HASH table and migrating/cutting over is often easier to reason about than overlapping bounds in place.

### Exercise 37 — ANALYZE Parent

Leaf autovacuum/autoanalyze does not automatically keep parent stats representative of new child data. After adding partitions or large bulk loads, consider:

~~~sql
ANALYZE partition_lab.events;
~~~

Combine with per-leaf stats and `EXPLAIN` checks. Do not run `ANALYZE` blindly on a tight loop without measuring its cost and cadence.

### Exercise 38 — 90-Day Retention and Late Arrivals

Before `DETACH`/`DROP`:

- Confirm the partition's bounds lie **completely** before the retention cutoff.
- Account for the 48-hour late-arrival window and other ingest SLAs.
- Check for active writers or backfills targeting that date.
- Verify backups/archives and legal hold requirements.
- Inspect FKs, downstream consumers, and logical replication/replicas.
- Keep a recovery plan if the job targets the wrong partition.
- Monitor late arrivals after structural changes.

Never drop a partition merely because most of its rows have expired if any rows must still be retained.

### Exercise 39 — New Partition Checklist

A solid workflow:

1. Compute exact lower/upper bounds and timezone.
2. Check existing partitions to avoid duplicates or overlaps.
3. Check `DEFAULT` for overlapping rows.
4. Pre-create/attach the child to the parent before the new period begins.
5. Verify child indexes, PK/constraints, and tablespace/storage.
6. Optionally test-insert a boundary row in a transaction and roll back.
7. Verify `tableoid` and `EXPLAIN` pruning.
8. Monitor `DEFAULT`, routing errors, and job schedules; alert if a partition is missing.

### Exercise 40 — Two Strategies for Many Tenants Queried by Tenant + Month

**Option A: Monthly RANGE, local index by tenant.**

- Around 24 partitions for 2-year retention (excluding future buffer/`DEFAULT`).
- Monthly pruning, plus `(tenant_id,event_at)` index within relevant months.
- Easy retention via detaching/dropping expired months.
- If a single month grows huge, individual partitions stay large, though indexed.
- Parent PK must include the time key; standalone `order_id` global uniqueness is not automatic.

**Option B: Monthly RANGE subpartitioned by HASH on tenant.**

- With 24 months × 8 buckets = **192 leaf partitions** (excluding parent layers).
- Queries filtering both month and tenant prune at both levels.
- Data/queries split into smaller children, at the cost of higher metadata/index counts, locks, and planning overhead.
- Hot tenants still concentrate into one bucket per month.
- `UNIQUE`/PK must include partition keys across levels; carefully check FKs and schema.
- Automation must create all 8 HASH leaves for **each month**.

A tenant-only HASH strategy aids equality lookups, yet **does not support efficient monthly retention via `DETACH`/`DROP`**, making it weaker when purging old data is primary.

**How to decide:** benchmark queries and ingest throughput on representative data, measuring buffers, planning time, disk/index overhead, retention speed, and production impact. Do not pick an option just because it creates more partitions.

---

## 46. Documentation and Keywords to Reference

When deploying on a specific PostgreSQL major version, cross-check:

- [PostgreSQL — Table Partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html): syntax, pruning, constraints, attach/detach, and declarative partitioning limits.
- [PostgreSQL — CREATE TABLE](https://www.postgresql.org/docs/current/sql-createtable.html): `PARTITION BY`, `PARTITION OF`, partition bounds.
- [PostgreSQL — ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html): `ATTACH PARTITION`, `DETACH PARTITION`, lock behavior, and restrictions.
- [PostgreSQL — Partition Pruning](https://www.postgresql.org/docs/current/ddl-partitioning.html#DDL-PARTITION-PRUNING): how the planner/executor skips partitions.
- [PostgreSQL — CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html): partitioned indexes and concurrent builds.
- [PostgreSQL — EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html): reading scan/pruning nodes and performance.
- [PostgreSQL — Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html): maintenance and statistics.

`/current/` URLs may point to a newer major PostgreSQL version than the one you run. Always open docs for your **actual server major version** and any related extensions when verifying syntax or edge-case restrictions.

---

## 47. Summary

**RANGE, LIST, and HASH all organize one logical table into multiple physical partitions, yet each optimizes different problems.**

- **RANGE:** suits ordered data and time-based lifecycles using **`[lower, upper)`** bounds with an exclusive upper endpoint. Strong for interval pruning and retention via partition lifecycle.
- **LIST:** suits discrete business groups such as region/country; children list discrete values, optionally with a `NULL` partition and `DEFAULT`. Requires monitoring casing, new values, skew, and migrating groups out of `DEFAULT`.
- **HASH:** suits equality lookups on keys with many distinct values aiming for bucketed distribution; uses **PostgreSQL hash `MODULUS`/`REMAINDER`**, not `key % N`. Has no `DEFAULT`, and scaling bucket counts requires data rebalancing.
- **Parent/child:** the parent is a logical relation, while leaves hold rows; `tableoid::regclass` inspects routing, and `pg_partition_tree` inspects tree structure.
- **Pruning:** relies on partition keys/bounds and matching predicates, **requiring no index**; inside leaves, local indexes govern row lookup speed. Queries omitting the key can scan many partitions.
- **Keys and uniqueness:** parent `PK`/`UNIQUE` constraints must include partition key columns per rules, and no global physical index spans partitions by default. Composite keys differ semantically from single-column uniqueness.
- **Row movement:** updating the partition key can relocate rows to another child, incurring WAL, index maintenance, and contention.
- **Indexes:** `CREATE INDEX` on the parent builds a logical partitioned index with local child indexes; for online builds on large parents, evaluate concurrent leaf index builds followed by `ATTACH`.
- **Lifecycle:** pre-create partitions, monitor `DEFAULT`, plan `ATTACH`/`DETACH`, understand locks and validation; never `DROP` retention data without backups and late-arrival checks.
- **Maintenance:** each leaf needs `VACUUM`/`ANALYZE`/index care; parent stats may need manual `ANALYZE`. Too many partitions raise planning, catalog, and lock costs.
- **Multi-level designs:** RANGE→HASH or LIST→RANGE can address multi-dimensional workloads, though leaf counts and PK/`UNIQUE`/maintenance constraints multiply quickly.
- **Performance:** measure `EXPLAIN (ANALYZE, BUFFERS)`, inspect pruning, scan nodes, planning time, index usage, write cost, and operational overhead; never assume partitioning beats a well-indexed regular table.

Practical workflow: **profile queries and retention → pick RANGE/LIST/HASH on a stable partition key → design bounds and PK/UNIQUE → build partitions/indexes properly → verify routing and pruning → monitor data, stats, and DEFAULT → automate pre-creation/retention → run ATTACH/DETACH with backups, timeouts, and a recovery plan**.
