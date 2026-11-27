# Partition Keys, Bounds, and Default Partitions in PostgreSQL

When a PostgreSQL table grows from a few million to hundreds of millions of rows, **table partitioning** is a common way to organize the data. Instead of storing every row in one massive physical relation, PostgreSQL can route rows into multiple child tables based on a **partition key** and **partition bounds**.

For example, a system stores orders by creation date:

~~~text
orders (parent table declared with PARTITION BY RANGE)
  |
  +-- orders_2026_01 : [2026-01-01, 2026-02-01)
  +-- orders_2026_02 : [2026-02-01, 2026-03-01)
  +-- orders_default : all values not matching the ranges above
~~~

The date `2026-01-31` belongs to January, whereas `2026-02-01` **no longer** belongs to the January partition. When an application inserts a March row before a March partition exists, PostgreSQL places it into `orders_default` if the parent has declared a default partition. If no matching partition exists, the `INSERT` fails.

More importantly: once March rows already sit inside `orders_default`, adding a dedicated March partition **is not as simple as running a `CREATE TABLE` statement**. PostgreSQL must ensure no rows belonging to March remain in the default partition; if any do, the operation fails and requires a safe data migration plan.

This lesson explains:

- How to choose a **partition key** and distinguish `RANGE`, `LIST`, and `HASH`.
- How to understand **inclusive lower bounds, exclusive upper bounds**, `MINVALUE`, `MAXVALUE`, and multi-column ranges.
- The purpose and limitations of a **default partition** (*DEFAULT partition*).
- How `INSERT` routing works, handling `UPDATE`s that modify the key, and inspecting `tableoid`.
- Inspecting metadata, pruning, primary key/`UNIQUE` constraints, and migrating data out of `DEFAULT` when adding a new partition.
- Operational considerations: pre-creating partitions, out-of-range data, DDL locks, storage, and data retention.

**Terminology note:** "partition key" here refers to the *partition key*—the column or expression that determines which partition stores a row. It is **not a row lock or table lock** used to coordinate concurrent transactions.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Choose a partition key that reflects query patterns and data lifecycle management.
2. Explain the routing rules for `RANGE`, `LIST`, and `HASH`.
3. Write non-overlapping partition bounds without accidentally dropping boundary values.
4. Explain why `FOR VALUES FROM (a) TO (b)` includes `a` and excludes `b`.
5. Explain which rows `DEFAULT` accepts and how `NULL` values are handled.
6. Recognize that multi-column `RANGE` bounds compare as tuples rather than independent rectangular predicates.
7. Create a parent table, child partitions, a default partition, and query `tableoid`.
8. Migrate rows sitting in `DEFAULT` when introducing a new monthly partition.
9. Read `EXPLAIN` output to verify whether partition pruning takes place.
10. Design primary keys/`UNIQUE` constraints within the limits of partitioned tables.
11. Identify concurrency, locking, and missing-future-partition risks.

## 2. What Is Table Partitioning Actually?

With **declarative partitioning**, you create a parent table:

~~~sql
CREATE TABLE example_orders (
    order_id bigint NOT NULL,
    order_date date NOT NULL,
    amount numeric(12, 2) NOT NULL
) PARTITION BY RANGE (order_date);
~~~

The parent declares the schema and partitioning rules. Separate partition tables hold the physical rows:

~~~sql
CREATE TABLE example_orders_jan
PARTITION OF example_orders
FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
~~~

When executing:

~~~sql
INSERT INTO example_orders (order_id, order_date, amount)
VALUES (1, DATE '2026-01-15', 50000);
~~~

PostgreSQL routes the row into `example_orders_jan` based on the `order_date` key.

### 2.1. The Parent Table Holds No Rows of Its Own

In a standard declarative partitioned table, **the parent is a virtual partitioned relation**, while rows reside in the partitions (possibly across multiple subpartition levels).

~~~sql
SELECT *
FROM example_orders;
~~~

Querying the parent table reads rows from the eligible partitions.

### 2.2. Do Not Confuse Partitioning with Creating Separate Tables Manually

If you manually create standalone tables `orders_jan` and `orders_feb` without attaching them via `PARTITION OF`/`ATTACH PARTITION`, PostgreSQL **does not automatically know** they are partitions of `orders`. Querying the parent will not automatically `UNION ALL` independent tables either.

### 2.3. The Partition Key Drives Routing

~~~text
INSERT into parent
       |
       v
Evaluate partition key
       |
       v
Compare against partition bounds
       |
       +--> matching partition found -> store row in that partition
       |
       +--> no match found -> DEFAULT (if defined)
       |
       +--> no DEFAULT -> routing error
~~~

## 3. Three Strategies: RANGE, LIST, HASH

| Strategy | Key Definition | How Partitions Are Defined | Common Best Fits |
| --- | --- | --- | --- |
| `RANGE` | One or more ordered columns/expressions | Intervals `FROM ... TO ...` | Dates/months, numeric ID ranges, time-series data |
| `LIST` | One column or expression | Enumerated values `FOR VALUES IN (...)` | Countries, regions, statuses with managed value sets |
| `HASH` | One or more columns/expressions | Hash with `MODULUS` and `REMAINDER` | Spreading rows across buckets when no natural query range exists |

### 3.1. RANGE: Splitting by Intervals

~~~sql
PARTITION BY RANGE (order_date)
~~~

Very helpful if the application routinely queries:

~~~sql
WHERE order_date >= DATE '2026-01-01'
  AND order_date < DATE '2026-02-01'
~~~

and needs to archive, retain, or purge data by month.

### 3.2. LIST: Splitting by Enumerated Values

~~~sql
PARTITION BY LIST (region)
~~~

Regions `'north'` and `'south'` can live in dedicated partitions, while new or unforeseen values route to `DEFAULT` if present.

### 3.3. HASH: Splitting by Hash Value

~~~sql
PARTITION BY HASH (customer_id)
~~~

Useful for spreading data fairly evenly by ID, though it does not inherently help queries looking up "February" if time is not the partition key.

### 3.4. Choose the Strategy from Access Patterns

Do not pick a strategy based on a hunch that "more partitions equals faster." First determine:

- What are the common query predicates?
- Is time-based archival or deletion required?
- Is data heavily skewed by region or customer?
- How many partitions exist today, and how will that count grow?
- Is the key immutable under `UPDATE`s?
- Which `PRIMARY KEY`/`UNIQUE`/`FOREIGN KEY` invariants must hold?

## 4. Setting Up the Lab Schema

The commands below target a **lab database**. Never run partition creation, attachment, or movement exercises on production tables.

### 4.1. Create the Schema

~~~sql
CREATE SCHEMA part_lab;
~~~

### 4.2. Create a Date-Partitioned Parent Table

~~~sql
CREATE TABLE part_lab.orders (
    order_id bigint NOT NULL,
    order_date date NOT NULL,
    customer_id integer NOT NULL,
    region text NOT NULL,
    amount numeric(12, 2) NOT NULL CHECK (amount >= 0),
    status text NOT NULL DEFAULT 'new',
    PRIMARY KEY (order_id, order_date)
) PARTITION BY RANGE (order_date);
~~~

Points to note:

- `order_date` is the **partition key**.
- The primary key includes both `order_id` and `order_date` because PostgreSQL requires relevant partition key columns to be part of any unique/primary key on the parent.
- `order_date NOT NULL` keeps the date example straightforward; the nullable-key RANGE section explains how `NULL`s behave.
- `PRIMARY KEY (order_id, order_date)` **does not guarantee `order_id` alone is unique across different dates**.

### 4.3. Create January and February Partitions

~~~sql
CREATE TABLE part_lab.orders_2026_01
PARTITION OF part_lab.orders
FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');

CREATE TABLE part_lab.orders_2026_02
PARTITION OF part_lab.orders
FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');
~~~

### 4.4. Create a DEFAULT Partition

~~~sql
CREATE TABLE part_lab.orders_default
PARTITION OF part_lab.orders
DEFAULT;
~~~

Note: `DEFAULT` here is **partition declaration syntax**, completely distinct from `DEFAULT 'new'` which sets the column default value for `status`.

## 5. RANGE: Inclusive Lower Bound, Exclusive Upper Bound

Syntax:

~~~sql
FOR VALUES FROM (lower_bound) TO (upper_bound)
~~~

In RANGE partitioning, the fundamental rule is:

\[
\text{lower bound} \le \text{key} < \text{upper bound}
\]

In interval notation:

~~~text
[lower_bound, upper_bound)
 ^            ^
 inclusive    exclusive
~~~

### 5.1. Checking Boundary Dates

January partition:

~~~sql
FOR VALUES FROM ('2026-01-01') TO ('2026-02-01')
~~~

| order_date | In January? | Reason |
| --- | --- | --- |
| `2025-12-31` | No | Below lower bound |
| `2026-01-01` | Yes | Lower bound is **inclusive** |
| `2026-01-15` | Yes | Inside the interval |
| `2026-01-31` | Yes | Less than Feb 1 |
| `2026-02-01` | No | Equals upper bound, **excluded** |

`2026-02-01` routes to the February partition because February begins right on that date.

### 5.2. Two Adjacent Intervals Do Not Overlap

~~~text
January:  [2026-01-01, 2026-02-01)
February: [2026-02-01, 2026-03-01)
~~~

They **meet at the boundary** without sharing any single date value. This is the standard design to prevent overlaps and gaps.

### 5.3. Why Not Use the Last Day of the Month?

Instead of setting the upper bound to `2026-01-31`, always use the **first day of the next month**. If you wrote:

~~~sql
FOR VALUES FROM ('2026-01-01') TO ('2026-01-31')
~~~

then `2026-01-31` itself would be **excluded from the partition** because upper bounds are exclusive.

### 5.4. Not All Months Have the Same Number of Days

~~~text
Feb 2026: [2026-02-01, 2026-03-01)
Feb 2028: [2028-02-01, 2028-03-01)
~~~

2028 is a leap year; defining the upper bound as the **first day of the following month** remains automatically accurate without manually typing "28 or 29."

## 6. Hands-On: Observing Where Rows Are Routed

~~~sql
INSERT INTO part_lab.orders (
    order_id, order_date, customer_id,
    region, amount, status
) VALUES
    (101, '2026-01-01', 1, 'north', 100000, 'paid'),
    (102, '2026-01-31', 1, 'north', 150000, 'paid'),
    (103, '2026-02-01', 2, 'south', 200000, 'new'),
    (104, '2026-02-28', 3, 'central', 50000, 'paid'),
    (105, '2026-03-01', 4, 'north', 120000, 'new'),
    (106, '2025-12-31', 5, 'south', 80000, 'paid');
~~~

In this sample:

- `101` and `102` land in `orders_2026_01`.
- `103` and `104` land in `orders_2026_02`.
- `105` (March) and `106` (December of the previous year) land in `orders_default`.

### 6.1. Inspecting via tableoid

~~~sql
SELECT
    order_id,
    order_date,
    tableoid::regclass AS physical_partition
FROM part_lab.orders
ORDER BY order_date, order_id;
~~~

`tableoid` is a system column holding the OID of the physical relation owning the tuple. Casting to `regclass` reveals the partition name. Never use a partition name as a permanent business key—data can be moved across partitions.

### 6.2. Counting Rows per Partition

~~~sql
SELECT
    tableoid::regclass AS physical_partition,
    COUNT(*) AS n_orders
FROM part_lab.orders
GROUP BY tableoid
ORDER BY physical_partition::text;
~~~

Each partition currently holds **two rows** (January: 2; February: 2; DEFAULT: 2).

### 6.3. Reading a Child Partition Directly

~~~sql
SELECT order_id, order_date
FROM part_lab.orders_2026_01
ORDER BY order_id;
~~~

Querying a child partition reads only rows **within that specific child relation**. Normally, applications should query the parent table and let PostgreSQL route or prune partitions automatically, instead of concatenating monthly partition names in application SQL.

## 7. Without a Matching Partition and Without DEFAULT

A partitioned table does **not** have to declare `DEFAULT`:

~~~sql
CREATE TABLE part_lab.strict_events (
    event_id bigint NOT NULL,
    event_date date NOT NULL
) PARTITION BY RANGE (event_date);

CREATE TABLE part_lab.strict_events_jan
PARTITION OF part_lab.strict_events
FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
~~~

Try:

~~~sql
INSERT INTO part_lab.strict_events(event_id, event_date)
VALUES (1, '2026-02-15');
~~~

Since no February partition and no `DEFAULT` exist, PostgreSQL raises a routing error:

~~~text
ERROR: no partition of relation "strict_events"
found for row
~~~

Do not treat this as a "weird PostgreSQL bug." It simply indicates **the key value does not fall inside any partition** permitted by the parent.

### 7.1. Benefits of Omitting DEFAULT

- Early detection of bad dates or out-of-range data.
- Forces future partition-creation jobs to work reliably.
- Prevents out-of-range rows from silently piling into an ever-growing catch-all table.

### 7.2. Trade-Off

If someone forgets to create the partition for a new period, `INSERT` fails and disrupts data ingestion. Continuously running systems need **automated partition pre-creation ahead of time**.

## 8. MINVALUE and MAXVALUE for RANGE

PostgreSQL supports special unbounded endpoints for RANGE:

- `MINVALUE`: smaller than every ordinary value for that key position.
- `MAXVALUE`: larger than every ordinary value for that key position.

Example on a separate table to avoid colliding with existing partitions:

~~~sql
CREATE TABLE part_lab.measurements (
    measurement_id bigint NOT NULL,
    sample_date date NOT NULL,
    value numeric NOT NULL
) PARTITION BY RANGE (sample_date);

CREATE TABLE part_lab.measurements_before_2026
PARTITION OF part_lab.measurements
FOR VALUES FROM (MINVALUE) TO ('2026-01-01');

CREATE TABLE part_lab.measurements_2026
PARTITION OF part_lab.measurements
FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');

CREATE TABLE part_lab.measurements_after_2026
PARTITION OF part_lab.measurements
FOR VALUES FROM ('2027-01-01') TO (MAXVALUE);
~~~

### 8.1. MINVALUE/MAXVALUE Are Not Literal Dates

`MINVALUE` does not mean `DATE '0001-01-01'`, and `MAXVALUE` is not an infinite date value that applications insert. They are **bound symbols inside partition definitions**.

### 8.2. NULL Keys Still Need Separate Handling

`MINVALUE`/`MAXVALUE` do not make `NULL` fall into a RANGE partition automatically. `NULL` is not an ordered value like an ordinary date. If a partition key is nullable and must accept `NULL`, see the `DEFAULT`/LIST sections below.

### 8.3. When to Use Unbounded Endpoints?

A `MINVALUE → 2026-01-01` partition is handy for holding archived older history. However, a "everything before 2026" partition can grow massive and reduce monthly management benefits; choose granularity based on queries and retention.

## 9. LIST Partitions: Bounds Are Enumerated Values

Not all data fits continuous intervals. For geographic regions or business categories, `LIST` works well.

~~~sql
CREATE TABLE part_lab.shipments (
    shipment_id bigint NOT NULL,
    region text,
    weight_kg numeric NOT NULL
) PARTITION BY LIST (region);

CREATE TABLE part_lab.shipments_north
PARTITION OF part_lab.shipments
FOR VALUES IN ('north', 'northeast');

CREATE TABLE part_lab.shipments_south
PARTITION OF part_lab.shipments
FOR VALUES IN ('south');

CREATE TABLE part_lab.shipments_default
PARTITION OF part_lab.shipments
DEFAULT;
~~~

### 9.1. LIST Routing

~~~sql
INSERT INTO part_lab.shipments (
    shipment_id, region, weight_kg
) VALUES
    (1, 'north', 2.0),
    (2, 'northeast', 1.5),
    (3, 'south', 3.0),
    (4, 'central', 4.0),
    (5, NULL, 0.5);
~~~

| region | Partition |
| --- | --- |
| `north` | `shipments_north` |
| `northeast` | `shipments_north` |
| `south` | `shipments_south` |
| `central` | `shipments_default` |
| `NULL` | `shipments_default` in this setup |

### 9.2. A Value Cannot Belong to Two LIST Partitions

You cannot list `'north'` in both `shipments_north` and `shipments_south`. Partition value sets must be **disjoint under partitioning equality rules**.

### 9.3. LIST Partitions Can Explicitly Accept NULL

On another LIST table, PostgreSQL allows declaring:

~~~sql
CREATE TABLE part_lab.labels (
    label_id bigint NOT NULL,
    label text
) PARTITION BY LIST (label);

CREATE TABLE part_lab.labels_missing
PARTITION OF part_lab.labels
FOR VALUES IN (NULL);

CREATE TABLE part_lab.labels_other
PARTITION OF part_lab.labels
DEFAULT;
~~~

Here `label IS NULL` routes to `labels_missing`, not `DEFAULT`.

### 9.4. How LIST Differs from RANGE for NULL

LIST can **explicitly enumerate `NULL` as a partition value**. RANGE does not form ordered intervals containing `NULL`; a nullable RANGE key either falls into `DEFAULT` or fails if no `DEFAULT` exists.

## 10. HASH Partitions: MODULUS and REMAINDER

For ID keys without natural time groupings:

~~~sql
CREATE TABLE part_lab.activity (
    activity_id bigint NOT NULL,
    customer_id bigint NOT NULL,
    event_kind text NOT NULL
) PARTITION BY HASH (customer_id);

CREATE TABLE part_lab.activity_p0
PARTITION OF part_lab.activity
FOR VALUES WITH (MODULUS 4, REMAINDER 0);

CREATE TABLE part_lab.activity_p1
PARTITION OF part_lab.activity
FOR VALUES WITH (MODULUS 4, REMAINDER 1);

CREATE TABLE part_lab.activity_p2
PARTITION OF part_lab.activity
FOR VALUES WITH (MODULUS 4, REMAINDER 2);

CREATE TABLE part_lab.activity_p3
PARTITION OF part_lab.activity
FOR VALUES WITH (MODULUS 4, REMAINDER 3);
~~~

### 10.1. HASH Partitioning Does Not Use Date Ranges

PostgreSQL hashes the partition key and applies modulus/remainder rules to pick a partition. **Never assume `customer_id = 4` automatically lands in `p0`** just because `4 % 4 = 0`—PostgreSQL evaluates the **hash of the key**, not a raw remainder of the ID.

### 10.2. No DEFAULT Partition Like RANGE/LIST

`HASH` does not support a `DEFAULT` partition. If a bucket is missing, any key hashing to that unconfigured remainder fails on insert with no partition found.

### 10.3. Moduli Must Be Compatible

PostgreSQL allows certain mixed-modulus hash configurations under divisibility/compatibility rules so bounds never overlap. In simple setups, stick to a uniform `MODULUS 4` with all four remainders.

### 10.4. HASH Does Not Help Time-Range Queries

~~~sql
WHERE event_time >= ...
~~~

If the partition key is `customer_id` alone, PostgreSQL cannot eliminate hash partitions using `event_time`. Choose your partitioning strategy from **actual predicates**, not merely a desire to spread load.

## 11. Multi-Column RANGE: Tuple Comparison

A partitioned table can use multiple keys:

~~~sql
CREATE TABLE part_lab.coordinates (
    point_id integer NOT NULL,
    a integer NOT NULL,
    b integer NOT NULL
) PARTITION BY RANGE (a, b);

CREATE TABLE part_lab.coordinates_band
PARTITION OF part_lab.coordinates
FOR VALUES FROM (1, 10) TO (2, 20);

CREATE TABLE part_lab.coordinates_default
PARTITION OF part_lab.coordinates
DEFAULT;
~~~

**Do not misread** this bound as:

~~~text
1 <= a < 2
AND
10 <= b < 20
~~~

PostgreSQL compares **tuples from left to right (lexicographically)**.

### 11.1. Illustration

The range `FROM (1,10) TO (2,20)` means:

~~~text
(a,b) >= (1,10)
AND
(a,b) <  (2,20)
~~~

comparing `a` first and then `b`.

| (a,b) | In Partition? | Explanation |
| --- | --- | --- |
| `(1,9)` | No | Less than lower bound |
| `(1,10)` | Yes | Equals lower bound |
| `(1,999)` | Yes | `a=1` is less than 2, even with huge `b` |
| `(2,-100)` | Yes | `a=2`, and `b=-100` is less than 20 |
| `(2,19)` | Yes | Less than upper bound |
| `(2,20)` | No | Equals upper bound |
| `(3,0)` | No | Greater than upper bound |

### 11.2. Testing Routing

~~~sql
INSERT INTO part_lab.coordinates(point_id, a, b)
VALUES
    (1, 1, 10),
    (2, 1, 999),
    (3, 2, -100),
    (4, 2, 20);

SELECT
    point_id,
    a,
    b,
    tableoid::regclass AS physical_partition
FROM part_lab.coordinates
ORDER BY point_id;
~~~

The first three rows land in `coordinates_band`; the fourth lands in `coordinates_default`.

### 11.3. Why Can Composite Ranges Be Surprising?

If your goal is "each tenant gets separate date ranges," writing `PARTITION BY RANGE (tenant_id, order_date)` without grasping lexicographical bounds creates ranges spanning unexpected tenants and dates.

When you need to split by tenant **and then by month**, consider **subpartitioning** or a different structural design rather than expecting rectangular semantics from multi-column RANGE.

## 12. Column vs. Expression Partition Keys

PostgreSQL supports partition keys as columns and, under suitable constraints, **expressions**.

Conceptual example:

~~~sql
CREATE TABLE part_lab.telemetry (
    telemetry_id bigint NOT NULL,
    sensor_id text NOT NULL,
    reading numeric NOT NULL
) PARTITION BY LIST (lower(sensor_id));
~~~

When using an expression key, consider:

- Whether the expression satisfies partition key rules, including immutability and return type.
- Whether query predicates will trigger partition pruning effectively.
- Whether `PRIMARY KEY`/`UNIQUE` constraints on the parent are restricted because the key uses an expression.
- Whether all applications understand the key normalization semantics (e.g., `lower`).

### 12.1. Not Every Function Is Allowed

An expression depending on the current time or session state violates the requirement for stable deterministic routing. Never design:

~~~sql
-- Bad design: value changes with the current clock.
PARTITION BY RANGE (now())
~~~

### 12.2. You Do Not Need an Expression to Split by Month

For `date` or `timestamptz` columns, `PARTITION BY RANGE (created_at)` with first-of-month bounds is usually simpler and prunes cleanly when queries filter with direct range predicates.

### 12.3. Rules for PRIMARY KEY/UNIQUE

In declarative partitioned tables, parent unique constraints have strict requirements on the partition key. With an expression key, do not assume every parent `PRIMARY KEY`/`UNIQUE` works the same as with plain column keys.

## 13. What Values Does a DEFAULT Partition Receive?

A `DEFAULT` partition receives key values **not matching any explicitly declared partition**.

~~~sql
CREATE TABLE part_lab.orders_default
PARTITION OF part_lab.orders
DEFAULT;
~~~

In our current lab, `DEFAULT` can accept:

- Dates before `2026-01-01`.
- Dates from `2026-03-01` onward, since only January and February have dedicated partitions.
- Never `NULL` in `orders`, because `order_date` is `NOT NULL`.

### 13.1. DEFAULT Is Not a Dedicated "Partition for NULL"

`DEFAULT` is the **complement of all explicit partitions**, not strictly a null bucket. With a nullable RANGE key, `NULL` routes to `DEFAULT` unless prevented by constraints; with LIST, `NULL` may instead go to an explicit `FOR VALUES IN (NULL)` partition.

### 13.2. Only One DEFAULT per Partitioned Level

You cannot create two `DEFAULT` partitions acting as catch-alls at the same level under one parent. If you need to classify bad or unknown data, organize your schema and operational workflows explicitly instead of expecting multiple `DEFAULT`s.

### 13.3. Is DEFAULT a Safety Net or a Risk?

**Pros:** applications can keep ingesting data when an unexpected value arrives (provided other constraints pass).

**Risks:** failures in scheduled partition creation won't trigger `INSERT` errors; rows silently pile into `DEFAULT`, bloating storage, slowing queries, and complicating future extraction into proper partitions.

## 14. Inspecting Data Inside DEFAULT

~~~sql
SELECT
    COUNT(*) AS rows_in_default,
    MIN(order_date) AS earliest_date,
    MAX(order_date) AS latest_date
FROM part_lab.orders_default;
~~~

With the initial sample data: `rows_in_default=2`, min `2025-12-31`, max `2026-03-01`.

### 14.1. Group by Month to See Missing Ranges

~~~sql
SELECT
    date_trunc('month', order_date::timestamp)::date
        AS month_start,
    COUNT(*) AS n_orders
FROM part_lab.orders_default
GROUP BY 1
ORDER BY 1;
~~~

This inspects **`DEFAULT` contents directly**—it is not a parent pruning query. It helps reveal months missed during provisioning.

### 14.2. Tracking the Share of Rows in DEFAULT

~~~sql
WITH counts AS (
    SELECT
        (SELECT COUNT(*) FROM part_lab.orders) AS all_rows,
        (SELECT COUNT(*) FROM part_lab.orders_default)
            AS default_rows
)
SELECT
    all_rows,
    default_rows,
    ROUND(
        100.0 * default_rows / NULLIF(all_rows, 0), 2
    ) AS default_pct
FROM counts;
~~~

In production, running `COUNT(*)` too often can be expensive. Rely on monitoring/estimates per policy and run exact counts only when needed.

### 14.3. A Bad Business Date Can Still Be Type-Valid

`DATE '2036-01-01'` is a valid `date`, yet could be a **business data bug**. `DEFAULT` cannot tell it is anomalous; applications or check constraints must enforce valid business bounds.

## 15. What Happens When Adding a New Partition with DEFAULT Present?

In the lab, the row:

~~~text
order_id=105, order_date=2026-03-01
~~~

currently sits in `orders_default`.

Now if you try:

~~~sql
CREATE TABLE part_lab.orders_2026_03
PARTITION OF part_lab.orders
FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');
~~~

PostgreSQL must narrow `DEFAULT`'s domain so it **no longer includes March rows**. Because `DEFAULT` currently contains `2026-03-01`, the operation fails since the updated default constraint is violated.

### 15.1. Why Doesn't the Database Move Rows Automatically?

Defining a new partition is a metadata/DDL operation with constraint validation, **not an automatic background data-migration command moving rows out of `DEFAULT`**.

Once out-of-range rows accumulate in `DEFAULT`, you must plan data movement and coordinate concurrent writes.

### 15.2. Why Must Concurrent Transactions Be Handled?

Suppose you:

1. Copy March rows out of `DEFAULT`.
2. Delete March rows from `DEFAULT`.
3. Attach the March partition.

If another transaction inserts a new March row into `DEFAULT` in between those steps, the attach fails or rows are missed. You need **proper transactions, locks, or synchronization**—never run separate autocommit steps hoping nobody writes in the meantime.

## 16. Lab Workflow: Moving Data from DEFAULT and Attaching a Partition

This is a learning pattern using **strong locks and a short transaction** to illustrate atomicity. Do not copy it verbatim onto large production tables, as heavy table locks block reads and writes for too long.

### 16.1. Goal

Upon completion:

~~~text
orders_2026_01  -> January
orders_2026_02  -> February
orders_2026_03  -> March
orders_default  -> before January and from April onward
~~~

And row `order_id=105` will reside in `orders_2026_03`.

### 16.2. Operations in One Transaction

~~~sql
BEGIN;

-- Lab: strong lock to prevent concurrent changes during movement.
LOCK TABLE part_lab.orders
IN ACCESS EXCLUSIVE MODE;

-- Create an unattached standalone table with matching columns/defaults/constraints.
CREATE TABLE part_lab.orders_2026_03 (
    LIKE part_lab.orders INCLUDING DEFAULTS INCLUDING CONSTRAINTS
);

-- Prove every row placed in this table belongs to March.
ALTER TABLE part_lab.orders_2026_03
ADD CONSTRAINT orders_2026_03_date_check
CHECK (
    order_date >= DATE '2026-03-01'
    AND order_date < DATE '2026-04-01'
);

-- Move March rows into the staging table that will become the new partition.
INSERT INTO part_lab.orders_2026_03 (
    order_id, order_date, customer_id,
    region, amount, status
)
SELECT
    order_id, order_date, customer_id,
    region, amount, status
FROM part_lab.orders_default
WHERE order_date >= DATE '2026-03-01'
  AND order_date < DATE '2026-04-01';

-- Remove originals from DEFAULT within the same transaction.
DELETE FROM part_lab.orders_default
WHERE order_date >= DATE '2026-03-01'
  AND order_date < DATE '2026-04-01';

-- Attach the populated table as the official March partition.
ALTER TABLE part_lab.orders
ATTACH PARTITION part_lab.orders_2026_03
FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');

COMMIT;
~~~

**This is a lab procedure** intentionally using strong locking to highlight atomicity. On very large production tables, analyze copy duration, locks, WAL, constraints, indexes, foreign keys, replication lag, and write control before picking an online/batched strategy.

### 16.3. Why Use a Standalone Table Before ATTACH?

`CREATE TABLE ... PARTITION OF` fails immediately if `DEFAULT` holds matching rows. With a standalone table, you can inspect and migrate the data first, then **`ATTACH`** once `DEFAULT` no longer holds conflicting rows.

### 16.4. CHECK Constraint on the New Table

The constraint:

~~~sql
CHECK (
    order_date >= DATE '2026-03-01'
    AND order_date < DATE '2026-04-01'
)
~~~

proves the new table's rows belong to the expected interval. Because `order_date` is `NOT NULL` here, no `NULL` can make the `CHECK` evaluate to unknown.

In suitable cases, PostgreSQL uses this validated constraint to skip scanning the new table during `ATTACH PARTITION`. Still, **checking `DEFAULT` and locking must be accounted for separately**.

### 16.5. Why Use ACCESS EXCLUSIVE Lock in the Lab?

We must prevent other transactions from inserting or updating rows through the parent or partitions mid-move. This lock is simple for teaching, yet **highly intrusive**—blocking even ordinary `SELECT`s for the duration of the transaction.

In production, schedule appropriately and choose lower-lock designs or maintenance windows rather than applying heavy locks by default.

### 16.6. What If a Step Fails?

Because the DDL/DML steps run inside one PostgreSQL transaction, `ROLLBACK` undoes all uncommitted changes. After an error inside a transaction, always roll back explicitly rather than issuing more SQL on an aborted transaction.

### 16.7. Verify After Commit

~~~sql
SELECT
    order_id,
    order_date,
    tableoid::regclass AS physical_partition
FROM part_lab.orders
ORDER BY order_id;

SELECT COUNT(*) AS march_rows
FROM part_lab.orders_2026_03;

SELECT COUNT(*) AS remaining_march_in_default
FROM part_lab.orders_default
WHERE order_date >= DATE '2026-03-01'
  AND order_date < DATE '2026-04-01';
~~~

Row `105` should now live in `orders_2026_03`, and `DEFAULT` should hold zero March rows.

## 17. Key Considerations for ATTACH PARTITION

`ALTER TABLE ... ATTACH PARTITION` attaches an existing table into the partition tree with specified bounds.

### 17.1. Schema Must Match

The attached table must have compatible columns, types, constraints, and properties matching the parent. Never assume an arbitrary staging table can attach while PostgreSQL silently fixes mismatched columns.

### 17.2. Every Row Must Satisfy the Bounds

If the staging table holds `order_date='2026-04-01'` when attaching `TO ('2026-04-01')`, it **violates** the bound because the upper bound is exclusive. PostgreSQL validates the data and rejects the attach.

### 17.3. Tables Without a Matching CHECK May Require a Scan

When attaching a pre-populated table, PostgreSQL may scan it to ensure no rows lie outside the bounds. A validated `CHECK` with a matching predicate lets PostgreSQL skip that scan when provable.

### 17.4. DEFAULT May Also Require a Scan

When adding a new partition range, `DEFAULT` must be verified to hold no matching rows. If `DEFAULT` is huge and lacks a proving constraint, the attach may scan `DEFAULT` and hold locks for a noticeable time.

### 17.5. CREATE PARTITION and ATTACH Have Different Locking

`CREATE TABLE ... PARTITION OF` and `ALTER TABLE ... ATTACH PARTITION` acquire different lock modes on the parent, child, and default partition. While `ATTACH` often lowers parent lock impact in some scenarios, it still checks and locks related relations. Never describe it as **completely online and lock-free**.

### 17.6. Indexes and Constraints

Parent partitioned indexes/constraints must be satisfied on the new partition per PostgreSQL rules. On large tables, building or checking required indexes takes resources; plan ahead rather than assuming `ATTACH` is always instant.

### 17.7. Production Workflows Must Account for Concurrent Writes

While writes continue flowing, determine:

- Can write paths be paused briefly during cutover?
- Can data be moved in batches followed by a very brief lock to finish?
- Are long-running transactions holding snapshots or locks?
- Do replication, CDC, or triggers depend on partition changes?
- How will you roll back or retry if attach hits contention?

Never attempt an "online migration" with three loose statements and leave race conditions unhandled.

## 18. After Adding March, Routing Changes

Test:

~~~sql
INSERT INTO part_lab.orders (
    order_id, order_date, customer_id,
    region, amount, status
) VALUES
    (107, '2026-03-20', 6, 'central', 350000, 'paid'),
    (108, '2026-04-01', 7, 'north', 90000, 'new');
~~~

Expected:

- `107` lands in `orders_2026_03`.
- `108` lands in `orders_default` because April has no dedicated partition yet.

~~~sql
SELECT
    order_id,
    order_date,
    tableoid::regclass AS physical_partition
FROM part_lab.orders
WHERE order_id IN (107, 108)
ORDER BY order_id;
~~~

### 18.1. Pre-Create Future Partitions Before Data Arrives

In production, creating April's partition **before April 1** routes April rows directly from the start, avoiding later migration out of `DEFAULT`.

### 18.2. DEFAULT Is Not an Auto-Draining Queue

PostgreSQL **does not move existing `DEFAULT` rows into a newly created/attached partition in the background**. You need an operational procedure to detect, move, and verify them.

## 19. Can a Partition Key Be NULL?

This depends on strategy, schema, and constraints.

### 19.1. RANGE Partitioning with a Nullable Key

~~~sql
CREATE TABLE part_lab.optional_dates (
    item_id integer NOT NULL,
    event_date date
) PARTITION BY RANGE (event_date);

CREATE TABLE part_lab.optional_dates_2026
PARTITION OF part_lab.optional_dates
FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');

CREATE TABLE part_lab.optional_dates_default
PARTITION OF part_lab.optional_dates
DEFAULT;
~~~

Here, a row with `event_date IS NULL` matches no explicit RANGE interval and goes into `DEFAULT`.

~~~sql
INSERT INTO part_lab.optional_dates(item_id, event_date)
VALUES (1, NULL);

SELECT
    item_id,
    tableoid::regclass AS physical_partition
FROM part_lab.optional_dates;
~~~

### 19.2. NOT NULL Prevents NULLs from Reaching DEFAULT

In `part_lab.orders`, `order_date NOT NULL` rejects `NULL` values. Even having `DEFAULT` will not bypass a `NOT NULL` column constraint.

### 19.3. LIST Can Dedicate a Partition to NULL

As shown earlier with `FOR VALUES IN (NULL)`. When such a partition exists, `NULL` routes to that explicit partition while `DEFAULT` receives other unlisted values.

### 19.4. HASH with a Nullable Key

If a HASH key column allows `NULL`, PostgreSQL still has hash/routing semantics for it and does not rely on a `DEFAULT` partition. Still, evaluate business correctness, distribution, and constraints before allowing null keys.

## 20. Overlapping Bounds and Gaps

PostgreSQL forbids same-level partitions from having overlapping bounds.

### 20.1. Overlapping Intervals Are Rejected

Once you have:

~~~sql
FOR VALUES FROM ('2026-01-01') TO ('2026-02-01')
~~~

you cannot add another partition under the same parent with:

~~~sql
-- Intentional overlap example; do not run as a migration.
FOR VALUES FROM ('2026-01-15') TO ('2026-02-15')
~~~

because the intervals overlap from Jan 15 up to before Feb 1.

### 20.2. Meeting Cleanly at Bounds Is Valid

~~~text
[2026-01-01, 2026-02-01)
[2026-02-01, 2026-03-01)
~~~

These two intervals **do not overlap**.

### 20.3. Gaps Can Still Exist

~~~text
[2026-01-01, 2026-02-01)
[2026-03-01, 2026-04-01)
~~~

February is a **gap**. With `DEFAULT`, February rows land in `DEFAULT`; without it, inserting February rows fails.

### 20.4. Check Coverage Beyond Syntax Validity

PostgreSQL blocks invalid/overlapping bounds, yet cannot know your operational rule is "every month must have exactly one partition." Use automation and coverage checks aligned with your business calendar.

## 21. Primary Keys and UNIQUE on Partitioned Tables

This topic is easily overlooked when choosing a partition key.

### 21.1. Why Must PRIMARY KEY Include the Partition Key?

For:

~~~sql
CREATE TABLE part_lab.orders (
    order_id bigint NOT NULL,
    order_date date NOT NULL,
    ...
    PRIMARY KEY (order_id, order_date)
) PARTITION BY RANGE (order_date);
~~~

Each partition has its own local index enforcing uniqueness on its subset of rows. PostgreSQL does not use a **standalone global unique index spanning all partitions** as some other engines do.

For a parent `UNIQUE`/`PRIMARY KEY` constraint to guarantee table-wide uniqueness across partitions, its key must include all partition key columns under PostgreSQL's rules.

### 21.2. Why Is PRIMARY KEY(order_id) Rejected Here?

An `order_id=100` in January and `order_id=100` in February would sit in two separate partitions. A local index on `order_id` cannot detect the duplicate in the other partition.

Hence:

~~~sql
-- Invalid as a parent-level PRIMARY KEY
-- for PARTITION BY RANGE(order_date):
PRIMARY KEY (order_id)
~~~

### 21.3. A Composite PK Does Not Mean order_id Alone Is Unique

~~~sql
INSERT INTO part_lab.orders (
    order_id, order_date, customer_id,
    region, amount, status
) VALUES
    (999, '2026-01-10', 1, 'north', 10000, 'paid'),
    (999, '2026-02-10', 1, 'north', 10000, 'paid');
~~~

These two rows have **different `(order_id, order_date)` pairs**, so they do not violate the composite PK. However, if the application identifies orders **solely by `order_id`**, this could break business assumptions.

### 21.4. Options When Global order_id Uniqueness Is Required

Depending on requirements:

1. Design business keys to include the partition key (e.g., identifying orders by ID+date).
2. Use a system-wide unique ID generator (sequence/UUID) plus application rules—noting that **a sequence itself is not a global `UNIQUE` constraint**, and auto-generated IDs do not prevent manual/buggy duplicate inserts.
3. Maintain an unpartitioned lookup/registry table with `UNIQUE(order_id)` coordinated transactionally when DB-level enforcement is mandatory.
4. Re-evaluate the partition key—or partitioning altogether—if global uniqueness is a critical invariant.

Never claim a composite PK guarantees standalone `order_id` uniqueness when the constraint only covers the pair.

### 21.5. Expression Partition Keys

PostgreSQL imposes additional restrictions on parent `UNIQUE`/`PRIMARY KEY` constraints when the partition key contains expressions or function calls. Verify PK requirements before choosing an expression partition key.

## 22. Indexes on Partitioned Tables

An index defined on the parent is a **partitioned index**, backed by matching physical indexes on each partition.

~~~sql
CREATE INDEX idx_orders_customer_date
ON part_lab.orders (customer_id, order_date DESC);
~~~

PostgreSQL creates and manages corresponding child indexes automatically under supported rules.

### 22.1. Pruning Differs from Index Scans

A query:

~~~sql
SELECT order_id, amount
FROM part_lab.orders
WHERE order_date >= DATE '2026-02-01'
  AND order_date < DATE '2026-03-01'
  AND customer_id = 2;
~~~

benefits from **two independent decisions**:

1. Partition pruning eliminates irrelevant January, March, and `DEFAULT` partitions.
2. Inside February, PostgreSQL chooses `Seq Scan` or `Index Scan` based on data and indexes.

Partition pruning **does not guarantee an `Index Scan`**.

### 22.2. Avoid Redundant Indexes on Every Column

With many partitions, adding one parent index creates many child indexes, increasing storage and DML maintenance overhead. Base indexes on actual query patterns and selectivity.

### 22.3. Indexes Do Not Fix Missing Bounds

An index on `order_date` cannot make an April `INSERT` succeed if no April partition and no `DEFAULT` exist. That is a **routing error**, not a lookup issue.

## 23. Partition Pruning Based on Keys and Bounds

**Partition pruning** is PostgreSQL's ability to skip partitions that cannot contain rows matching query predicates.

~~~sql
EXPLAIN
SELECT order_id, amount
FROM part_lab.orders
WHERE order_date >= DATE '2026-02-01'
  AND order_date < DATE '2026-03-01';
~~~

From the bounds:

~~~text
Jan:     [2026-01-01, 2026-02-01)
Feb:     [2026-02-01, 2026-03-01)
Mar:     [2026-03-01, 2026-04-01)
Default: everything else
~~~

the planner sees that **only the February partition** satisfies the date range.

### 23.1. EXPLAIN Might Not Show an Append Node

If planning-time pruning eliminates all but one partition, the plan may show a direct scan on `orders_2026_02` with **no multi-child `Append`**.

### 23.2. Pruning Is Not Scanning Everything and Filtering Afterward

When a partition's bounds rule it out in advance, PostgreSQL **does not scan** that partition at all—unlike scanning all data and applying a `Filter` afterward.

### 23.3. Parameters and Runtime Pruning

~~~sql
PREPARE find_by_date(date, date) AS
SELECT order_id, amount
FROM part_lab.orders
WHERE order_date >= $1
  AND order_date < $2;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE find_by_date('2026-02-01', '2026-03-01');
~~~

Depending on the plan and whether values are known at plan time, PostgreSQL can prune at **planning time**, **executor initialization**, or execution stages. Plans may display `Subplans Removed` or `never executed` nodes. Do not expect every plan output to look identical.

### 23.4. Understanding DEFAULT During Pruning

`DEFAULT` carries an implicit constraint excluding all explicitly declared bounds. When a query targets February—which has an explicit partition—PostgreSQL can prune `DEFAULT` using bound knowledge.

However, if a query looks up **April** before an April partition exists, `DEFAULT` may be the only place capable of holding matching rows and will be scanned/indexed accordingly.

## 24. Writing Predicates for Effective Pruning

Direct conditions on the partition key are easiest for the planner to reason about:

~~~sql
WHERE order_date >= DATE '2026-02-01'
  AND order_date < DATE '2026-03-01'
~~~

### 24.1. Avoid Transformations That Obscure Ranges

~~~sql
WHERE EXTRACT(YEAR FROM order_date) = 2026
~~~

This does not have the same direct range shape on the partition key as a date interval. The planner may fail to deduce the exact partition set from this expression.

To query all of 2026, write explicitly:

~~~sql
WHERE order_date >= DATE '2026-01-01'
  AND order_date < DATE '2027-01-01'
~~~

### 24.2. Preserve Timezone Semantics

If the key is `timestamptz`, start-of-month boundaries depend on a specific timezone (e.g., UTC). A month in a local timezone has different UTC boundaries; in regions with DST, day lengths can also shift.

### 24.3. Pruning Depends on Matching Types and Operators

Type casts, collations, functions on the partition key, or complex predicates can inhibit pruning. Always verify with `EXPLAIN` on the actual query rather than guessing from column names.

### 24.4. Queries Omitting the Partition Key May Scan All Partitions

~~~sql
SELECT order_id, amount
FROM part_lab.orders
WHERE customer_id = 42;
~~~

Since the parent is partitioned by date, if the query offers no date bounds, PostgreSQL may have to inspect **many partitions**. Local indexes on `customer_id` still help inside each child, yet do not act as a global index jumping straight to the right partition without knowing the date.

## 25. Updating the Partition Key: Row Movement

PostgreSQL can handle an `UPDATE` that modifies the partition key by **moving the row to the matching partition** under supported conditions:

~~~sql
BEGIN;

UPDATE part_lab.orders
SET order_date = DATE '2026-02-15'
WHERE order_id = 101
  AND order_date = DATE '2026-01-01';

SELECT
    order_id,
    order_date,
    tableoid::regclass AS physical_partition
FROM part_lab.orders
WHERE order_id = 101;

ROLLBACK;
~~~

Inside the transaction, row `101` appears in `orders_2026_02`. After `ROLLBACK`, it remains in January as before.

### 25.1. Updating the Key Is Not Like Updating a Regular Column

Row movement involves cross-partition relocation, constraints, triggers, and concurrency contention. Applications should avoid routinely updating a date key used for routing and retention.

### 25.2. Missing Destination Partition

If updating `order_date` produces a value matching no partition and no `DEFAULT` exists, `UPDATE` fails because there is nowhere to route the row.

### 25.3. Composite Primary Key Changes

In the lab, `PRIMARY KEY (order_id, order_date)` includes the date. Changing the date also changes the logical primary key value; any foreign keys referencing the composite key or business rules relying on it must be carefully evaluated.

### 25.4. Never Use tableoid as a Long-Lived ID

`tableoid` only tells you which physical relation currently holds the row. After row movement, `DETACH`/`ATTACH`, or migrations, `tableoid` changes even when the business considers it the same order.

## 26. Old Data and Retention Policies

A common advantage of time-based partitioning is managing data lifecycles by interval.

For instance, once policy allows deleting January 2026 data, you can manage `orders_2026_01` directly instead of running a huge table-wide `DELETE`.

### 26.1. DETACH PARTITION

~~~sql
-- Syntax illustration; do not run if lab exercises still need January.
ALTER TABLE part_lab.orders
DETACH PARTITION part_lab.orders_2026_01;
~~~

Once detached, the child remains as an independent table, no longer visible when querying the parent.

### 26.2. DROP Partition

~~~sql
-- Destructive operation illustration; DO NOT run carelessly.
DROP TABLE part_lab.orders_2026_01;
~~~

Dropping a populated partition deletes all of its data. Verify backups, retention approvals, foreign keys, and archival rules before dropping.

### 26.3. DEFAULT Does Not Replace Retention Windows

If old rows share `DEFAULT` with recent rows lacking partitions, you cannot simply drop `DEFAULT` to purge old data. `DEFAULT` can hold rows from many different months and categories.

This is another operational reason **never to let `DEFAULT` grow unchecked**.

### 26.4. DETACH CONCURRENTLY Has Specific Prerequisites

Modern PostgreSQL supports concurrent detach variants with restrictions on transaction blocks, `DEFAULT` partitions, and server state. Never drop concurrent commands into a transaction-wrapped migration script without checking all requirements for your version.

## 27. Subpartitions: Subpartitioning

A partition can itself be partitioned—for instance, splitting by year first and then by month under each year:

~~~text
parent: RANGE(order_date)
  |
  +-- year_2026: RANGE(order_date)
  |     +-- jan_2026
  |     +-- feb_2026
  |     +-- ...
  |
  +-- year_2027: RANGE(order_date)
        +-- jan_2027
        +-- ...
~~~

### 27.1. Every Level Has Its Own Bounds

A row must satisfy **every ancestor level's bounds** along its routing path. Creating a subpartition with bounds exceeding its parent's bounds causes errors/restrictions or leaves the excess unreachable.

### 27.2. DEFAULT Per Level

A `DEFAULT` at one level is the complement of the bounds **at that level**, not a global catch-all bypassing upper levels.

### 27.3. Do Not Add Levels Just for Complexity

Adding partition levels increases metadata, object counts, planning/maintenance overhead, and migration complexity. Choose it only when workload, retention, and data volume clearly justify it.

## 28. Inspecting Partition Structure via Catalogs

PostgreSQL provides functions and catalogs to inspect the partition tree.

### 28.1. pg_partition_tree

~~~sql
SELECT
    relid::regclass AS partition,
    parentrelid::regclass AS parent,
    isleaf,
    level
FROM pg_partition_tree('part_lab.orders'::regclass)
ORDER BY level, relid::regclass::text;
~~~

`level=0` is the root parent; `isleaf=true` identifies leaf partitions.

### 28.2. Viewing Child Bound Expressions

~~~sql
SELECT
    c.oid::regclass AS partition_name,
    pg_get_expr(c.relpartbound, c.oid) AS partition_bound
FROM pg_class AS c
JOIN pg_inherits AS i
    ON i.inhrelid = c.oid
WHERE i.inhparent = 'part_lab.orders'::regclass
ORDER BY c.oid::regclass::text;
~~~

`partition_bound` outputs expressions like:

~~~text
FOR VALUES FROM ('2026-01-01') TO ('2026-02-01')
FOR VALUES FROM ('2026-02-01') TO ('2026-03-01')
FOR VALUES FROM ('2026-03-01') TO ('2026-04-01')
DEFAULT
~~~

### 28.3. Viewing the Partition Key

~~~sql
SELECT
    c.oid::regclass AS parent_table,
    pg_get_partkeydef(c.oid) AS partition_key
FROM pg_class AS c
WHERE c.oid = 'part_lab.orders'::regclass;
~~~

Expected: `RANGE (order_date)`.

### 28.4. pg_inherits and Declarative Partitions

`pg_inherits` stores parent/child relationships for both partitioning and legacy inheritance. Never assume a row in `pg_inherits` automatically implies a bounded declarative partition; combine `pg_class.relpartbound` and `pg_partition_tree` as needed.

### 28.5. tableoid to See Where Rows Live

~~~sql
SELECT
    tableoid::regclass AS partition,
    COUNT(*) AS rows_count
FROM part_lab.orders
GROUP BY tableoid
ORDER BY partition::text;
~~~

Catalogs describe **structure**; `tableoid` on rows reveals **actual data placement**.

## 29. EXPLAIN and Overhead with Many Partitions

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, order_date, amount
FROM part_lab.orders
WHERE order_date >= DATE '2026-02-01'
  AND order_date < DATE '2026-03-01';
~~~

Questions to check:

1. Which partitions appear in the plan?
2. Is `orders_default` scanned?
3. Is there an `Append`, or just a single scan?
4. Which nodes use `Seq Scan` and which use `Index Cond`?
5. What are `Buffers: shared hit/read` across the accessed relations?

### 29.1. EXPLAIN Is Not EXPLAIN ANALYZE

~~~sql
EXPLAIN SELECT ...;
~~~

only builds the plan.

~~~sql
EXPLAIN (ANALYZE, BUFFERS) SELECT ...;
~~~

actually executes the query to measure rows, timing, and buffers. For data-modifying statements, `EXPLAIN ANALYZE` executes the changes for real; never run it on production DML without wrapping or controlling the impact.

### 29.2. Effective Pruning Does Not Guarantee Low Latency

A single monthly partition can still hold tens of millions of rows. Even after pruning down to one partition, a query can remain slow if suitable indexes are missing or large sorts occur.

### 29.3. Too Many Partitions Carry Real Overhead

Thousands of partitions inflate metadata, planning time, autovacuum work, catalog lookups, and migration effort. Pruning skips irrelevant partitions, yet does not make large partition counts free.

## 30. Scheduled Partition Management

With monthly RANGE tables, operations usually follow a **pre-creation schedule**.

### 30.1. Example Operational Schedule

~~~text
On the 20th of every month:
  1. Identify upcoming months lacking partitions.
  2. Pre-create partitions for the next month / next few months.
  3. Verify bound metadata and check for overlaps.
  4. Check whether DEFAULT already holds any matching rows.
  5. If so, plan a safe data migration.
  6. Verify EXPLAIN pruning, permissions, and indexes.
  7. Log results and emit alerts on issues.
~~~

### 30.2. Pick Bounds in One Consistent Timezone

With `date` columns, day boundaries are usually clear. With `timestamptz`, decide whether months follow **UTC or a specific business timezone**, and use explicit offsets/types to avoid DST surprises or implicit conversions.

### 30.3. Do Not Trust Partition Names Alone

A table named `orders_2026_04` attached with the wrong bounds is still semantically wrong. Always inspect `pg_get_expr(relpartbound, ...)` rather than relying solely on naming conventions.

### 30.4. Monitoring DEFAULT

Detect:

- Whether new rows are landing in `DEFAULT`.
- Whether upcoming months already have partitions created.
- Whether `DEFAULT` is growing unexpectedly.
- Whether dates lie too far in the future or past.

If `DEFAULT` begins receiving unexpected data, treat it as a signal to fix **partition provisioning or upstream data validation**.

## 31. Common Design Mistakes

### Mistake 1. Treating the Partition Key as a Table Lock

`PARTITION BY RANGE(order_date)` does not lock transactions by date. It defines **routing and pruning** rules.

### Mistake 2. Treating TO as an Inclusive Bound

`TO ('2026-02-01')` **does not accept** Feb 1; it accepts values **strictly less than** Feb 1.

### Mistake 3. Using the Last Day of the Month for TO

`TO ('2026-01-31')` excludes Jan 31. Always use the first day of the next month.

### Mistake 4. Creating Overlapping Ranges

PostgreSQL rejects same-level partitions with intersecting bounds; there is no "first declared partition wins" rule.

### Mistake 5. Leaving a Month Missing While DEFAULT Hides It

`INSERT` still succeeds; data silently accumulates in `DEFAULT`, masking broken partition provisioning.

### Mistake 6. Thinking DEFAULT Only Receives NULL

`DEFAULT` receives every value **not matching any explicit partition**; `NULL` is only one case depending on strategy and constraints.

### Mistake 7. Thinking MINVALUE/MAXVALUE Include NULL

They are RANGE bound markers, **not values that turn `NULL` into an in-range value**.

### Mistake 8. Applying % Directly to an ID to Predict HASH Partitions

PostgreSQL hashes the key first and then takes modulus/remainder; it is not simple `customer_id % modulus` computed directly on the ID.

### Mistake 9. Trying to Create DEFAULT for HASH

HASH partitioning does not support `DEFAULT` like RANGE/LIST.

### Mistake 10. Reading Composite RANGE as Per-Column Intervals

`FROM (1,10) TO (2,20)` is a **lexicographical** tuple range, not `1<=a<2 AND 10<=b<20`.

### Mistake 11. Adding a New Month While DEFAULT Already Holds Its Rows

`DEFAULT`'s implicit constraint becomes invalid; you must move/delete conflicting rows and attach through a controlled workflow.

### Mistake 12. Copying Data Without Deleting from DEFAULT

During attach, `DEFAULT` still holds rows colliding with the new bound. Never treat copying alone as completing migration.

### Mistake 13. Running Copy/Delete/Attach in Separate Transactions

Concurrent writes can land back in `DEFAULT` between steps. Use proper transactions/locking or synchronization.

### Mistake 14. Believing ATTACH Never Scans or Locks

Both the new table and `DEFAULT` may require validation; DDL locks and scan costs can be substantial.

### Mistake 15. Creating PRIMARY KEY(order_id) When Partitioned by order_date

Parent `UNIQUE`/`PRIMARY KEY` constraints are constrained by the partition key; there is no automatic global unique index outside child indexes.

### Mistake 16. Assuming a Composite PK Makes order_id Globally Unique

`(order_id, order_date)` only enforces uniqueness of the **pair**; identical IDs on different dates remain valid.

### Mistake 17. Confusing Partition Pruning with Index Scans

Pruning skips partitions; scanning inside a surviving partition can still be a Seq Scan. They are two separate optimizations.

### Mistake 18. Omitting the Partition Key and Expecting Pruning

If partitioned by date while filtering only by customer ID, PostgreSQL may have to inspect many partitions.

### Mistake 19. Frequently Updating a Date Partition Key

Changing the partition key triggers row movement, costing more than ordinary updates and impacting constraints, triggers, and concurrency.

### Mistake 20. Assuming the Partition Name Enforces Bounds

Table names do not enforce bounds. Actual bound metadata governs routing.

### Mistake 21. Dropping DEFAULT to "Clear Bad Data"

`DEFAULT` may hold valid unpartitioned rows, historical data, and future data mixed together. Dropping it blindly can wipe out legitimate records.

### Mistake 22. Creating Unlimited Tiny Partitions

Too many partitions inflate metadata, planning, locking, and catalog overhead. Granularity must be justified.

### Mistake 23. Using Timestamps Without Clear Timezone Semantics

If monthly bounds follow UTC while the app expects another timezone, rows near midnight can land in unexpected months.

### Mistake 24. Expecting DEFAULT to Auto-Drain When a New Partition Appears

Nothing silently moves pre-existing `DEFAULT` rows into a newly created partition. You must migrate them explicitly.

## 32. Practice Exercises

Work in schema `part_lab`. Exercises creating new tables can use distinct table names in your lab database. For destructive operations, write illustrative SQL rather than running against real data.

### Exercise 1. Definition

What is a partition key? How does it differ from a row lock or table lock?

### Exercise 2. Month Bounds

Does the partition `FROM ('2026-01-01') TO ('2026-02-01')` include `2026-02-01`? Why or why not?

### Exercise 3. Last Day of Month

Why is `TO ('2026-01-31')` wrong if the goal is to hold all of January?

### Exercise 4. Leap Day

Write the bounds for February 2028 using two first-of-month boundaries.

### Exercise 5. Routing

In the lab setup, which partition receives `order_date='2025-12-31'`? Which receives `'2026-02-01'`?

### Exercise 6. tableoid

Write a query displaying `order_id`, `order_date`, and the actual partition name storing each row.

### Exercise 7. Without DEFAULT

What happens on `INSERT` if a row matches no partition and no `DEFAULT` exists?

### Exercise 8. MINVALUE and MAXVALUE

Write one partition holding all dates before `2026-01-01` and another holding all dates from `2027-01-01` onward.

### Exercise 9. LIST

Write a LIST partition accepting both `'north'` and `'northeast'`.

### Exercise 10. NULL in LIST

Write a dedicated partition accepting a LIST key of `NULL`. In that setup, does `NULL` still route to `DEFAULT`?

### Exercise 11. NULL in RANGE

With a nullable RANGE key and `DEFAULT`, where does a null row go? What if the column is `NOT NULL`?

### Exercise 12. HASH

Create 4 hash partitions on `customer_id`. Why can't you deduce a row's partition purely from `customer_id % 4`?

### Exercise 13. Composite RANGE

Does `FROM (1,10) TO (2,20)` contain `(1,999)` and `(2,-100)`? Explain.

### Exercise 14. DEFAULT

Give three reasons not to let `DEFAULT` grow unchecked.

### Exercise 15. Moving Data Out of DEFAULT

`DEFAULT` holds April rows and you want to attach an April partition. Why can't you simply attach without checking data?

### Exercise 16. Safe Workflow

Describe the sequence of creating staging, copying, deleting, attaching, and committing to extract a new month from `DEFAULT` in the lab; what concurrency issue exists?

### Exercise 17. CHECK Validation

Why can a validated `CHECK` proving the range bounds reduce scanning during attach?

### Exercise 18. Creating a New Partition

Write SQL to create the April 2026 partition **after** `DEFAULT` no longer holds any April rows.

### Exercise 19. PK

Why can't a parent partitioned by `order_date` simply declare `PRIMARY KEY(order_id)` at the parent level?

### Exercise 20. Composite Key

Does `PRIMARY KEY(order_id,order_date)` guarantee global uniqueness of `order_id`?

### Exercise 21. Pruning

Write a February 2026 query on `part_lab.orders` that gives PostgreSQL a chance to prune other partitions.

### Exercise 22. EXPLAIN

Write `EXPLAIN (ANALYZE, BUFFERS)` for the February query and list two indicators to check for pruning and scanning.

### Exercise 23. Omitting the Partition Key

Why might `WHERE customer_id=42` scan many partitions even if each child has a `customer_id` index?

### Exercise 24. Updating the Partition Key

When changing a row's `order_date` from January to February, what might PostgreSQL have to do?

### Exercise 25. Catalogs

Write queries using `pg_get_partkeydef`, `pg_partition_tree`, and `pg_get_expr(relpartbound,...)`.

### Exercise 26. Retention

Why is detaching/dropping an old partition usually easier to manage than row-by-row deletion, and what cautions apply?

### Exercise 27. Non-Sargable Queries

How can `EXTRACT(YEAR FROM order_date)=2026` hurt pruning? Write an equivalent range predicate.

### Exercise 28. Pre-Creating Partitions

Describe a recurring process ensuring you never rely on `DEFAULT` to catch new months' data.

## 33. Suggested Answers

### Exercise 1

The partition key is the column/expression deciding which physical partition stores a row, not a transaction concurrency lock.

### Exercises 2–3

`TO` is an **exclusive** upper bound, so Feb 1 does not belong to January. `TO('2026-01-31')` also excludes Jan 31; use `TO('2026-02-01')`.

### Exercise 4

~~~sql
FOR VALUES FROM ('2028-02-01') TO ('2028-03-01')
~~~

### Exercises 5–6

`2025-12-31` lands in `DEFAULT`; `2026-02-01` lands in `orders_2026_02`.

~~~sql
SELECT
    order_id,
    order_date,
    tableoid::regclass AS partition_name
FROM part_lab.orders
ORDER BY order_id;
~~~

### Exercise 7

`INSERT` fails because no matching partition exists; PostgreSQL does not auto-create partitions.

### Exercise 8

~~~sql
FOR VALUES FROM (MINVALUE) TO ('2026-01-01')
-- and:
FOR VALUES FROM ('2027-01-01') TO (MAXVALUE)
~~~

These bounds do not automatically accept `NULL`.

### Exercises 9–10

~~~sql
CREATE TABLE part_lab.shipments_north_answer
PARTITION OF part_lab.shipments
FOR VALUES IN ('north', 'northeast');
~~~

*The statement above is syntax-illustrative only:* the lab already has `shipments_north` with the same value set, so **do not run it again** or it will fail with overlap. On a fresh LIST table:

~~~sql
CREATE TABLE labels_null
PARTITION OF part_lab.labels
FOR VALUES IN (NULL);
~~~

If a `NULL` partition is already declared (like `labels_missing` in the lab), you cannot create a duplicate `NULL` partition. When a `NULL` partition exists, `NULL` values route there instead of `DEFAULT`.

### Exercise 11

A nullable RANGE key with `DEFAULT` routes `NULL` into `DEFAULT`; `NOT NULL` rejects `NULL` on `INSERT`/`UPDATE` before routing.

### Exercise 12

~~~sql
FOR VALUES WITH (MODULUS 4, REMAINDER 0)
FOR VALUES WITH (MODULUS 4, REMAINDER 1)
FOR VALUES WITH (MODULUS 4, REMAINDER 2)
FOR VALUES WITH (MODULUS 4, REMAINDER 3)
~~~

Routing uses PostgreSQL's hash function before taking modulus/remainder; it is not simple division by 4 on the raw ID.

### Exercise 13

Both `(1,999)` and `(2,-100)` belong to the range: tuples compare left-to-right rather than enforcing two separate per-column bounds.

### Exercise 14

`DEFAULT` can mask missing partitions, grow huge and hard to optimize, and force future partition attachments to scan or migrate data under long locks.

### Exercises 15–16

Because `DEFAULT` holds rows belonging to the new range, narrowing `DEFAULT` would violate its partition constraint. Within an appropriate transaction/synchronization strategy: lock to block concurrent writes, create a staging table with a March/April `CHECK`, copy rows, delete matching rows from `DEFAULT`, attach the staging table, and commit. Production needs tailored planning to avoid long locks.

### Exercise 17

A validated `CHECK` proving every row in staging lies inside the bounds lets PostgreSQL skip scanning the entire staging table for validation under eligible conditions. `DEFAULT` may still require scanning/validation.

### Exercise 18

~~~sql
CREATE TABLE part_lab.orders_2026_04
PARTITION OF part_lab.orders
FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');
~~~

**Run only once** `DEFAULT` holds no April rows and no partition already covers that bound.

### Exercises 19–20

There is no automatic global unique index. `PRIMARY KEY(order_id)` cannot be enforced globally if the same ID appears in two different date partitions. `PRIMARY KEY(order_id,order_date)` protects only the **pair**, not `order_id` alone.

### Exercises 21–22

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, amount
FROM part_lab.orders
WHERE order_date >= DATE '2026-02-01'
  AND order_date < DATE '2026-03-01';
~~~

Check whether the plan excludes Jan/Mar/`DEFAULT`, whether the February scan uses `Seq Scan` or `Index Scan`, and inspect buffers/timing.

### Exercise 23

The partition key is date, so customer ID alone cannot identify which date partition holds the rows. Per-child indexes on customer ID speed up searching inside each partition without necessarily reducing how many partitions are inspected.

### Exercise 24

PostgreSQL may perform row movement between the January and February partitions with associated constraints, triggers, and concurrency semantics; if the target partition is missing and no `DEFAULT` exists, it fails.

### Exercise 25

~~~sql
SELECT pg_get_partkeydef('part_lab.orders'::regclass);

SELECT
    relid::regclass AS partition,
    parentrelid::regclass AS parent,
    level
FROM pg_partition_tree('part_lab.orders'::regclass);

SELECT
    c.oid::regclass AS child,
    pg_get_expr(c.relpartbound, c.oid) AS bound
FROM pg_class AS c
JOIN pg_inherits AS i
  ON i.inhrelid = c.oid
WHERE i.inhparent = 'part_lab.orders'::regclass;
~~~

### Exercise 26

Managing a physical partition simplifies monthly retention compared to row-by-row deletion, yet `DETACH`/`DROP` carries data-loss, locking, FK, backup, policy, and dependency risks. Never run casually.

### Exercise 27

~~~sql
WHERE order_date >= DATE '2026-01-01'
  AND order_date < DATE '2027-01-01'
~~~

Direct predicates on the partition key prune much more reliably in most cases, whereas `EXTRACT` can prevent the planner from deriving bounds.

### Exercise 28

On a schedule, pre-create partitions for several upcoming months ahead of data arrival; verify bound metadata, inspect `DEFAULT` and alert if unexpected months appear; monitor job runs and plan migrations if rows ever fall into `DEFAULT`.

## 34. Quick Reference Table

| Need | Syntax / Meaning |
| --- | --- |
| Time-based partition key | `PARTITION BY RANGE (order_date)` |
| January range | `FROM ('2026-01-01') TO ('2026-02-01')` |
| RANGE bounds | `[lower, upper)` — inclusive lower, exclusive upper |
| Range before all other dates | `FROM (MINVALUE) TO ('2026-01-01')` |
| Open-ended future range | `FROM ('2027-01-01') TO (MAXVALUE)` |
| Regional partitioning | `PARTITION BY LIST (region)` |
| LIST values | `FOR VALUES IN ('north','south')` |
| NULL in LIST | `FOR VALUES IN (NULL)` |
| HASH partitioning | `PARTITION BY HASH (customer_id)` |
| HASH bucket | `FOR VALUES WITH (MODULUS 4, REMAINDER 0)` |
| RANGE/LIST catch-all | `CREATE TABLE ... PARTITION OF ... DEFAULT` |
| Inspect physical partition | `tableoid::regclass` |
| Inspect partition tree | `pg_partition_tree(parent::regclass)` |
| Inspect partition key | `pg_get_partkeydef(parent_oid)` |
| Inspect bounds | `pg_get_expr(relpartbound, oid)` |
| Attach existing table | `ALTER TABLE parent ATTACH PARTITION child FOR VALUES ...` |
| Detach partition | `ALTER TABLE parent DETACH PARTITION child` |
| Pruning | Planner/executor skips partitions failing key predicates |
| Verify pruning | `EXPLAIN (ANALYZE, BUFFERS)` |
| Monitor DEFAULT | `SELECT ... FROM parent_default` |
| Parent PK/UNIQUE | Must include all partition key columns |
| Changing partition key | Can trigger row movement |

## 35. Pre-Operations Checklist

1. **Does the partition key match real queries?** Are predicates filtering on that date/region/ID?
2. **Are RANGE bounds `[lower,upper)` correct?** Any missing end-of-month dates or timezone mismatches?
3. **Are partitions contiguous as planned?** Any unintended gaps or overlaps?
4. **Is DEFAULT truly needed?** If omitted, how do apps handle out-of-range errors?
5. **What dates/regions are sitting in DEFAULT?** Are growth alerts configured?
6. **How are NULL values routed?** Via `NOT NULL`, a LIST `NULL` partition, or `DEFAULT`?
7. **Are composite ranges understood lexicographically?** Any accidentally broad intervals?
8. **Does HASH have full bucket coverage and valid modulus/remainder?** No naive ID modulo assumptions?
9. **Do parent PK/UNIQUE constraints include the partition key?** Is global identity truly protected?
10. **Are future partitions pre-created ahead of time?** Automated and monitored?
11. **If DEFAULT holds rows for a new bound, what is the migration workflow?**
12. **How long can CREATE/ATTACH scan or hold locks?** Tested on production-like volume?
13. **Are there concurrent writers or long transactions?** Maintenance window or online strategy needed?
14. **Do new partitions get proper constraints, indexes, and permissions?**
15. **Will UPDATEs change the partition key often?** What is the impact of row movement?
16. **Does EXPLAIN prune irrelevant partitions?** Any huge `Seq Scan` left in surviving partitions?
17. **Does retention require detaching/dropping partitions?** Backups, FKs, and dependencies verified?
18. **Are excessive partition counts adding overhead?** Is granularity justified?
19. **Are checks verifying bound metadata rather than trusting partition names?**
20. **Are rows landing in the expected partitions?** Checked via `tableoid` and `DEFAULT` monitoring?

## 36. Summary

Three core concepts of declarative partitioning in PostgreSQL:

1. **Partition key** determines **how each row is routed** to a partition. In `RANGE` it marks position in an ordered range; in `LIST` it matches an enumerated set; in `HASH` it maps via a hash function. The partition key is **not a transaction lock**.
2. **Partition bounds** define each partition's non-overlapping domain. In `RANGE`, the lower bound is **inclusive** and the upper bound is **exclusive**: `[2026-01-01, 2026-02-01)` includes Jan 31 and excludes Feb 1. Multi-column `RANGE` compares **lexicographically**, not as independent per-column intervals.
3. **Default partition** (`DEFAULT`) catches values falling outside explicit partitions in `RANGE`/`LIST`, when constraints allow. It reduces short-term routing errors, yet can mask missing partitions. Before creating a new partition, any rows already in `DEFAULT` matching the new bound **must be handled first**, or the operation will fail.

A well-designed partitioning setup is **semantically accurate and operationally maintainable**: align the key with queries and retention, define consistent bounds, pre-create future partitions proactively, monitor `DEFAULT`, uphold appropriate uniqueness invariants, and verify with `EXPLAIN` that pruning truly occurs.

Whenever preparing to add a new partition, ask: **"Which exact values does this bound cover, does `DEFAULT` already hold any rows in that bound, and how will attaching lock or validate data?"** Answering these three questions prevents the most common failures when scaling time-partitioned tables.
