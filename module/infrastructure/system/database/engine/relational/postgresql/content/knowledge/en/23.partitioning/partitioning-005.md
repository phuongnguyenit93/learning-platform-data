# INSERT Routing and Partition-Key-Changing UPDATEs in PostgreSQL

When a table holds tens of millions or billions of rows, applications rarely want every operation hitting one monolithic storage structure. PostgreSQL supports **declarative partitioning**: one **partitioned parent table** represents a logical table, while **child partitions** store different subsets of rows based on a **partition key**.

For example, an orders table partitioned by month:

~~~text
sales_events (logical table, PARTITION BY RANGE (event_date))
    |
    +-- sales_events_2026_01 : 01/01 <= event_date < 01/02
    |
    +-- sales_events_2026_02 : 01/02 <= event_date < 01/03
    |
    +-- sales_events_2026_03 : 01/03 <= event_date < 01/04
    |
    +-- sales_events_default : values not matching any partition above
~~~

The first question is: **when inserting into the parent, which partition receives the row?** The second, harder question is: **if an `UPDATE` changes `event_date` from January to February, how does PostgreSQL maintain partition boundaries?**

This lesson belongs to the **Partitioning** chapter of the **Database Engine Relational PostgreSQL** module and focuses on those two mechanisms. Afterward, you will understand:

- How PostgreSQL selects the target partition for each inserted row.
- Why `RANGE` bounds are **inclusive lower, exclusive upper**.
- How to inspect the physical partition via `tableoid::regclass`.
- What happens when no matching partition exists, when `DEFAULT` exists, or when the key is `NULL`.
- The difference between an **intra-partition UPDATE** and a **cross-partition UPDATE (row movement)**.
- Why moving rows generally executes as **DELETE from source + INSERT into destination**, along with its impact on triggers, indexes, WAL, locks, and transactions.
- `PRIMARY KEY`/`UNIQUE` restrictions on partitioned tables and their interaction with `ON CONFLICT`.
- How to handle errors when concurrent transactions update a row undergoing row movement.
- Workflows to audit, fix bad dates, provision new partitions, and practice with two PostgreSQL sessions.

> **Key takeaway:** With declarative partitioning, PostgreSQL routes rows by **partition key value**. Do not think of `UPDATE event_date = ...` as harmlessly editing a single cell: if the new value belongs to a different partition, the logical row changes physical storage location.

## 1. Logical Parent Table and Physical Child Tables

On an unpartitioned table, `INSERT INTO sales_events ...` writes a tuple into that table's own heap.

On a partitioned table:

~~~sql
CREATE TABLE sales_events (
    event_id bigint NOT NULL,
    event_date date NOT NULL,
    amount numeric(12,2) NOT NULL
) PARTITION BY RANGE (event_date);
~~~

`sales_events` is the **partitioned parent table**. Rows live in the corresponding child partitions, not in an ordinary heap on the parent itself.

~~~mermaid
flowchart TD
    I["INSERT INTO sales_events"] --> R["Partition routing by event_date"]
    R --> J["Jan: sales_events_2026_01"]
    R --> F["Feb: sales_events_2026_02"]
    R --> M["Mar: sales_events_2026_03"]
    R --> D["DEFAULT if no explicit partition matches"]
~~~

Applications can query through the parent:

~~~sql
SELECT *
FROM sales_events
WHERE event_date >= DATE '2026-02-01'
  AND event_date < DATE '2026-03-01';
~~~

PostgreSQL scans only the necessary partitions per planner/executor decisions. Returned rows share the same logical columns even though they live across multiple child relations.

### Distinguishing Three Operations

| Operation | When? | Goal |
| --- | --- | --- |
| **Partition routing** | `INSERT` and partition-key-changing `UPDATE` | Select the **destination partition for writes** |
| **Partition pruning** | Planning or executing an eligible query | Skip partitions **that do not need to be read** |
| **Partition maintenance** | Create, attach, detach, drop, maintain partitions | Manage **structure and data lifecycle** |

Both routing and pruning consult partition bounds, yet they are distinct operations. Good indexes do not eliminate the need for `INSERT` routing.

## 2. What Is a Partition Key?

The partition key determines which group a row belongs to. PostgreSQL offers three core declarative partitioning strategies:

| Type | Splitting Method | Example |
| --- | --- | --- |
| `RANGE` | Bounded value intervals | Orders by day/month |
| `LIST` | Enumerated set of values | Orders by region or status category |
| `HASH` | Distributed by hash of the key | Spreading load by tenant ID |

Examples:

~~~sql
PARTITION BY RANGE (event_date)
PARTITION BY LIST (region_code)
PARTITION BY HASH (tenant_id)
~~~

With `RANGE (event_date)`, **each row is routed by its own `event_date` value**, not by the timestamp when the `INSERT` runs.

An order inserted today with `event_date = DATE '2026-01-15'` still routes to January, not the current month.

### Partition Key Does Not Equal Primary Key

- **Partition key** determines **storage placement**.
- **Primary key** identifies rows and enforces uniqueness within constraint rules.
- **Foreign key** enforces referential integrity.

A column can serve multiple roles, yet **being a partition key does not make it unique**.

## 3. RANGE Bounds: Inclusive Lower, Exclusive Upper

A monthly partition:

~~~sql
FOR VALUES FROM ('2026-01-01') TO ('2026-02-01')
~~~

contains rows where:

~~~text
2026-01-01 <= event_date < 2026-02-01
~~~

Therefore:

- `2026-01-01` belongs to January.
- `2026-01-31` belongs to January.
- `2026-02-01` does **not** belong to January; it belongs to February if February exists.
- `2025-12-31` does not belong to January.

The **`[lower, upper)`** rule keeps adjacent intervals non-overlapping:

~~~text
Jan: [2026-01-01, 2026-02-01)
Feb: [2026-02-01, 2026-03-01)
Mar: [2026-03-01, 2026-04-01)
~~~

With `date` values, you never need `"23:59:59"` to mark the end of a month. Exclusive upper bounds express boundaries cleanly.

## 4. Building the Lab Dataset

Examples use a dedicated `partition_lab` schema.

**Warning:** the setup script runs `DROP SCHEMA IF EXISTS partition_lab CASCADE`, deleting everything inside that schema. Run only in a **learning database you control**, never in production or a schema holding valuable data.

### 4.1. Create the Partitioned Parent Table

~~~sql
-- RUN ONLY IN A LAB DATABASE.
DROP SCHEMA IF EXISTS partition_lab CASCADE;
CREATE SCHEMA partition_lab;

CREATE TABLE partition_lab.sales_events (
    event_date date NOT NULL,
    event_id bigint NOT NULL,
    tenant_id integer NOT NULL CHECK (tenant_id > 0),
    status text NOT NULL DEFAULT 'new'
        CHECK (status IN ('new', 'paid', 'cancelled')),
    amount numeric(12,2) NOT NULL CHECK (amount >= 0),
    note text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT pk_sales_events
        PRIMARY KEY (event_date, event_id)
) PARTITION BY RANGE (event_date);
~~~

Two key design choices:

1. The table is partitioned **by event date**, not default `created_at`.
2. The primary key includes **both `event_date` and `event_id`**. Why the constraint requires the partition key is explained in the `UNIQUE` section.

### 4.2. Create Monthly Partitions

~~~sql
CREATE TABLE partition_lab.sales_events_2026_01
PARTITION OF partition_lab.sales_events
FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');

CREATE TABLE partition_lab.sales_events_2026_02
PARTITION OF partition_lab.sales_events
FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');

CREATE TABLE partition_lab.sales_events_2026_03
PARTITION OF partition_lab.sales_events
FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');

CREATE TABLE partition_lab.sales_events_default
PARTITION OF partition_lab.sales_events
DEFAULT;
~~~

`DEFAULT` catches values **matching no explicit partition**. In this schema, that includes December 2025, April 2026, or any dates outside the three defined months.

Having `DEFAULT` is a design choice, **not mandatory** for every partitioned table. It avoids dropped requests when a partition is missing, yet can mask forgetting to create next month's partition.

### 4.3. Load Data Through the Parent Table

~~~sql
INSERT INTO partition_lab.sales_events (
    event_date,
    event_id,
    tenant_id,
    status,
    amount,
    note
)
VALUES
    ('2026-01-05', 1001, 1, 'new',       120.00, 'Jan A'),
    ('2026-01-31', 1002, 1, 'paid',      250.00, 'Jan end'),
    ('2026-02-01', 1003, 2, 'new',       180.00, 'Feb start'),
    ('2026-02-18', 1004, 2, 'new',        90.00, 'Feb B'),
    ('2026-03-01', 1005, 1, 'paid',      350.00, 'Mar start'),
    ('2026-03-31', 1006, 3, 'new',        70.00, 'Mar end'),
    ('2026-04-01', 1007, 3, 'new',        40.00, 'Beyond explicit months');
~~~

All seven rows go into **one `INSERT` on the parent**, yet PostgreSQL routes each tuple individually by `event_date`.

### 4.4. Observe Physical Placement

~~~sql
SELECT
    event_id,
    event_date,
    tenant_id,
    status,
    amount,
    tableoid::regclass AS physical_partition
FROM partition_lab.sales_events
ORDER BY event_date, event_id;
~~~

Expected partition placement:

| event_id | event_date | Partition |
| ---: | --- | --- |
| 1001 | 2026-01-05 | `partition_lab.sales_events_2026_01` |
| 1002 | 2026-01-31 | `partition_lab.sales_events_2026_01` |
| 1003 | 2026-02-01 | `partition_lab.sales_events_2026_02` |
| 1004 | 2026-02-18 | `partition_lab.sales_events_2026_02` |
| 1005 | 2026-03-01 | `partition_lab.sales_events_2026_03` |
| 1006 | 2026-03-31 | `partition_lab.sales_events_2026_03` |
| 1007 | 2026-04-01 | `partition_lab.sales_events_default` |

`tableoid` is a **system column** identifying the physical relation holding the tuple. Casting `::regclass` displays the relation name instead of a raw OID.

Names may render with or without schema prefixes depending on `search_path` and how PostgreSQL formats `regclass`.

## 5. How INSERT Routing Works Through the Parent

When the application runs:

~~~sql
INSERT INTO partition_lab.sales_events (
    event_date, event_id, tenant_id, amount
)
VALUES ('2026-02-10', 2001, 4, 99.00);
~~~

PostgreSQL:

1. Receives a tuple with `event_date = 2026-02-10`.
2. Evaluates the parent's partition key.
3. Finds the partition whose bounds cover that value.
4. Inserts the tuple into `sales_events_2026_02`.
5. Applies required constraints, indexes, triggers, and checks.
6. Lets the transaction commit or roll back.

~~~mermaid
flowchart TD
    A["INSERT into parent"] --> B["Read tuple's event_date"]
    B --> C{"In Jan?"}
    C -->|"Yes"| J["INSERT into Jan partition"]
    C -->|"No"| D{"In Feb?"}
    D -->|"Yes"| F["INSERT into Feb partition"]
    D -->|"No"| E{"In Mar?"}
    E -->|"Yes"| M["INSERT into Mar partition"]
    E -->|"No"| G{"DEFAULT exists?"}
    G -->|"Yes"| H["INSERT into DEFAULT partition"]
    G -->|"No"| X["Error: no matching partition"]
~~~

Each row in a batch is routed by its own partition key value. It does not copy all rows to every child and filter afterward.

### Inspecting with RETURNING

~~~sql
BEGIN;

INSERT INTO partition_lab.sales_events (
    event_date, event_id, tenant_id, amount
)
VALUES ('2026-02-10', 2001, 4, 99.00)
RETURNING
    event_id,
    event_date,
    tableoid::regclass AS physical_partition;

ROLLBACK;
~~~

`RETURNING` emits the inserted row's columns, including the physical partition holding the tuple. `ROLLBACK` leaves the original dataset untouched.

## 6. One Multi-Row INSERT Can Target Multiple Partitions

~~~sql
BEGIN;

INSERT INTO partition_lab.sales_events (
    event_date, event_id, tenant_id, amount
)
VALUES
    ('2026-01-10', 2011, 4, 10.00),
    ('2026-02-10', 2012, 4, 20.00),
    ('2026-03-10', 2013, 4, 30.00),
    ('2026-04-10', 2014, 4, 40.00)
RETURNING
    event_id,
    event_date,
    tableoid::regclass AS physical_partition;

ROLLBACK;
~~~

The four rows route to Jan, Feb, Mar, and `DEFAULT` respectively.

### Statement Atomicity

A multi-row `INSERT` is a single SQL statement. If **one row triggers an error failing the entire statement** without explicit error handling, earlier rows from that statement are never committed individually.

Inside a normal transaction, a failed statement also puts the transaction into an aborted state until `ROLLBACK` or rolling back to a savepoint.

When ingesting multi-source data, decide explicitly:

- Should the **entire batch succeed or fail together**?
- Or should it **split batches and quarantine failing rows** under a dedicated import protocol?
- Should out-of-range dates be rejected, fixed prior to `INSERT`, or routed to a controlled quarantine area?

Never treat `DEFAULT` as a complete error-handling mechanism without monitoring and triage.

## 7. Direct Child INSERT vs. Parent INSERT

Normally, always write through the parent:

~~~sql
INSERT INTO partition_lab.sales_events (
    event_date, event_id, tenant_id, amount
)
VALUES ('2026-02-20', 2021, 2, 55.00);
~~~

PostgreSQL selects the partition automatically.

If writing **directly into a child**:

~~~sql
BEGIN;

INSERT INTO partition_lab.sales_events_2026_02 (
    event_date, event_id, tenant_id, amount
)
VALUES ('2026-02-20', 2022, 2, 55.00);

ROLLBACK;
~~~

the command targets a relation that still enforces its partition constraint. `2026-02-20` lies within Feb's bounds, so it succeeds.

However:

~~~sql
-- INTENTIONALLY WRONG: does not re-route to March because Feb is targeted directly.
INSERT INTO partition_lab.sales_events_2026_02 (
    event_date, event_id, tenant_id, amount
)
VALUES ('2026-03-10', 2023, 2, 55.00);
~~~

is rejected because the row violates February's partition constraint.

**Rule:** use the **parent table** as your unified write entry point unless you have a clear operational reason to target a child directly and guarantee valid bounds. Direct inserts are never a way to force PostgreSQL to store an "off-month" row inside a chosen partition.

## 8. What Happens When No Matching Partition Exists?

Our main lab has `DEFAULT`, so dates outside Jan–Mar land in `sales_events_default`.

To observe behavior **without `DEFAULT`**, create a separate test table:

~~~sql
CREATE TABLE partition_lab.missing_destination_demo (
    event_id bigint NOT NULL,
    event_date date NOT NULL,
    description text
) PARTITION BY RANGE (event_date);

CREATE TABLE partition_lab.missing_destination_jan
PARTITION OF partition_lab.missing_destination_demo
FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
~~~

Insert within January:

~~~sql
BEGIN;

INSERT INTO partition_lab.missing_destination_demo (
    event_id, event_date, description
)
VALUES (1, '2026-01-15', 'inside bounds');

ROLLBACK;
~~~

Insert in February:

~~~sql
-- INTENTIONAL ERROR: demo table only has a January partition.
INSERT INTO partition_lab.missing_destination_demo (
    event_id, event_date, description
)
VALUES (2, '2026-02-15', 'no target partition');
~~~

PostgreSQL raises an error because **no destination partition exists** for that value. If running inside an explicit transaction, roll back before continuing once the transaction enters an aborted state.

### A Missing-Partition Error Is No Excuse to Alter event_date

Never rewrite Feb 15 to Jan 31 just to make `INSERT` succeed—doing so corrupts **business truth**.

Proper fixes include:

- Creating the February partition.
- Adopting a monitored, intentional `DEFAULT` policy.
- Rejecting unsupported out-of-range dates.
- Routing invalid records to a dedicated staging/quarantine table for review.

## 9. DEFAULT: Safety Net Against Missing Partitions, with Operational Costs

In the lab:

~~~sql
SELECT
    event_id,
    event_date,
    tableoid::regclass AS stored_in
FROM partition_lab.sales_events
WHERE event_id = 1007;
~~~

The April 01 row resides in `sales_events_default`.

`DEFAULT` has two sides:

**Benefits:**

- `INSERT`s still have a place to land if next month's partition wasn't created in time.
- Reduces sudden failures in ingestion pipelines.
- Enables a controlled review workflow for out-of-bounds rows.

**Risks:**

- Can mask broken partition-creation schedules.
- `DEFAULT` can swell over time, forcing queries to inspect unexpected out-of-range data.
- When adding a new explicit partition, PostgreSQL must verify `DEFAULT` **holds no rows matching the new bounds**.
- If `DEFAULT` already holds April rows, creating an April partition will not automatically relocate those rows into it.

### Inspecting Data Volume in DEFAULT

~~~sql
SELECT
    COUNT(*) AS default_rows,
    MIN(event_date) AS min_date,
    MAX(event_date) AS max_date
FROM partition_lab.sales_events_default;
~~~

With the initial seed, `default_rows = 1`.

Production systems should track `DEFAULT` row counts and alert on unexpected growth. `DEFAULT` is never a permanent substitute for time-based partition management.

## 10. Adding a New Partition When DEFAULT Already Holds Matching Data

Suppose you want to create the April partition:

~~~sql
-- Target syntax only; do not run directly while DEFAULT
-- already holds April rows without a migration plan.
CREATE TABLE partition_lab.sales_events_2026_04
PARTITION OF partition_lab.sales_events
FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');
~~~

Because `sales_events_default` currently holds a row for `2026-04-01`, PostgreSQL checks partition constraints and **rejects the operation** because defining the new partition conflicts with rows living in `DEFAULT`.

**PostgreSQL does not automatically migrate existing `DEFAULT` rows into a new partition simply because you ran DDL.**

You need an explicit migration procedure, such as:

1. Identify `DEFAULT` rows belonging to April.
2. Plan locks and transactions to prevent concurrent `INSERT`s into that date range.
3. Move misplaced rows into an appropriate standalone staging table via a controlled workflow.
4. Ensure `DEFAULT` holds no rows matching the new bounds.
5. Create/`ATTACH` the April partition appropriately.
6. Verify row completeness, uniqueness, and application health afterward.

On large tables this is sensitive because `ATTACH PARTITION` or changing bounds requires validation and locks. Never run a naive "delete and re-insert" script in production without data-safety guarantees and a lock/downtime budget.

## 11. NULL in the Partition Key

In our lab:

~~~sql
event_date date NOT NULL
~~~

so inserting `event_date = NULL` violates `NOT NULL`:

~~~sql
-- INTENTIONAL ERROR: NULL date is forbidden by schema.
INSERT INTO partition_lab.sales_events (
    event_date, event_id, tenant_id, amount
)
VALUES (NULL, 3001, 1, 10.00);
~~~

If another partitioned table **allows a `NULL` partition key**, routing follows the strategy and declared partitions. In `RANGE` and `LIST`, `DEFAULT` can absorb unmatched values including `NULL` when permitted. In `LIST`, you can also declare a dedicated `FOR VALUES IN (NULL)` partition.

For date-driven domains, the best choice is usually a **`NOT NULL` partition key with an explicit policy for unknown dates**, avoiding silent accumulation of `NULL`s in an unbounded `DEFAULT`.

## 12. UPDATE That Does Not Change the Partition Key

Example updating status on a January event:

~~~sql
BEGIN;

UPDATE partition_lab.sales_events
SET
    status = 'paid',
    amount = 130.00,
    updated_at = clock_timestamp()
WHERE event_date = DATE '2026-01-05'
  AND event_id = 1001
RETURNING
    event_id,
    event_date,
    status,
    amount,
    tableoid::regclass AS physical_partition;

ROLLBACK;
~~~

`event_date` stays `2026-01-05`. The logical row stays in the January partition.

This **does not mean PostgreSQL overwrites the tuple in place**. Standard MVCC `UPDATE` mechanics still apply: a new tuple version is written in the January partition's heap.

The distinction is that **the row does not move to a different child relation** because the partition key stays within bounds.

### Updating the Key While Staying in the Same Partition

~~~sql
BEGIN;

UPDATE partition_lab.sales_events
SET event_date = DATE '2026-01-20'
WHERE event_date = DATE '2026-01-05'
  AND event_id = 1001
RETURNING event_id, event_date, tableoid::regclass;

ROLLBACK;
~~~

The date changes from Jan 05 to Jan 20, still inside January's bounds. This updates the partition key **without triggering row movement**.

**Cross-partition movement occurs only when the new value maps to a different partition.**

## 13. UPDATE Changing the Key to Another Partition

This is the core mechanism of this lesson.

Suppose row `event_id = 1001` currently sits in January:

~~~text
event_id   = 1001
event_date = 2026-01-05
partition  = sales_events_2026_01
~~~

A business operation corrects the event date:

~~~sql
BEGIN;

UPDATE partition_lab.sales_events
SET
    event_date = DATE '2026-02-12',
    updated_at = clock_timestamp()
WHERE event_date = DATE '2026-01-05'
  AND event_id = 1001
RETURNING
    event_id,
    event_date,
    tableoid::regclass AS physical_partition;

SELECT
    event_id,
    event_date,
    status,
    tableoid::regclass AS physical_partition
FROM partition_lab.sales_events
WHERE event_id = 1001;

ROLLBACK;
~~~

Inside the transaction, `RETURNING` and the subsequent `SELECT` show logical row 1001 with `event_date = 2026-02-12` inside **the February partition**.

After `ROLLBACK`, the committed lab data reverts to Jan 05 inside January.

### Why Can't It Stay in January?

The January partition has bounds:

~~~text
2026-01-01 <= event_date < 2026-02-01
~~~

A row dated Feb 12 **no longer satisfies January's partition constraint**. PostgreSQL must guarantee every partition contains only rows valid under its constraint.

Hence, when supporting row movement for `UPDATE`s through a partitioned table, PostgreSQL locates the destination partition from the **post-update key value**.

## 14. Row Movement Is Essentially DELETE + INSERT at the Storage Layer

An `UPDATE` moving a row across partitions is not just flipping a metadata pointer. PostgreSQL executes a relocation semantically equivalent to:

~~~text
1. Locate source row in Jan partition.
2. Compute updated row values: event_date = 2026-02-12.
3. Determine new row belongs to Feb partition.
4. Delete logical row version from Jan partition.
5. Insert corresponding row version into Feb partition.
6. Protect all steps under the same transaction, constraints, and locks.
~~~

~~~mermaid
flowchart LR
    A["Jan: event 1001, 2026-01-05"] --> U["UPDATE event_date = 2026-02-12"]
    U --> D["DELETE source tuple in Jan"]
    U --> I["INSERT target tuple in Feb"]
    D --> T["Same transaction"]
    I --> T
    T --> R["After COMMIT: one logical row in Feb"]
~~~

At the SQL level, you ran **one `UPDATE` statement**. Internally—and for row-level triggers and indexes—it acts as **a `DELETE` and an `INSERT` on two distinct relations**.

### Not Two Separate Commits

If the `UPDATE` or transaction fails, PostgreSQL will never commit the source `DELETE` while skipping the destination `INSERT` inside an atomic transaction.

**Atomicity holds:** row movement cannot silently lose a row by "deleting and forgetting to insert" due to an ordinary exception mid-statement.

This does not cover external side effects if a trigger or application calls external APIs unsafely; those side effects must be handled explicitly.

## 15. Verifying Row Counts Before and After Movement

An experiment to verify consistency:

~~~sql
BEGIN;

SELECT
    event_id,
    event_date,
    tableoid::regclass AS physical_partition
FROM partition_lab.sales_events
WHERE event_id = 1001;

UPDATE partition_lab.sales_events
SET event_date = DATE '2026-03-15'
WHERE event_date = DATE '2026-01-05'
  AND event_id = 1001
RETURNING
    event_id,
    event_date,
    tableoid::regclass AS physical_partition;

SELECT COUNT(*) AS total_logical_rows
FROM partition_lab.sales_events
WHERE event_id = 1001;

SELECT
    COUNT(*) FILTER (
        WHERE tableoid = 'partition_lab.sales_events_2026_01'::regclass
    ) AS in_jan,
    COUNT(*) FILTER (
        WHERE tableoid = 'partition_lab.sales_events_2026_03'::regclass
    ) AS in_mar
FROM partition_lab.sales_events
WHERE event_id = 1001;

ROLLBACK;
~~~

Inside the transaction, expect:

- `total_logical_rows = 1`.
- `in_jan = 0`.
- `in_mar = 1`.

This confirms the logical row moved rather than being duplicated by the `UPDATE`.

**Note:** the lab's primary key is `(event_date,event_id)`. It does not forbid another row with `event_id = 1001` on a different date if inserted separately. Counting by `event_id` here only makes sense because we know the lab dataset has no duplicate IDs across dates.

## 16. UPDATE Through the Parent vs. Directly on a Partition

When updating a date that may cross bounds, target the **partitioned parent table**:

~~~sql
UPDATE partition_lab.sales_events
SET event_date = DATE '2026-02-15'
WHERE event_date = DATE '2026-01-05'
  AND event_id = 1001;
~~~

Reasons:

- The parent knows the entire partition tree.
- PostgreSQL has full visibility to route to the new destination.
- SQL stays decoupled from specific child table names.
- The same DML interface continues working when new partitions are added.

Avoid writing:

~~~sql
-- Do not use as a general pattern to move a row to Feb.
UPDATE partition_lab.sales_events_2026_01
SET event_date = DATE '2026-02-15'
WHERE event_id = 1001;
~~~

expecting it to route just like the parent. Targeting a leaf directly applies leaf constraints and execution paths that depend on structure and version; to keep code reliable, **always target the parent for writes that may cross partitions**.

### Do Not Update Child Tables Directly Just "For Guaranteed Speed"

Directly querying a specific child can shave off a bit of planner work in narrow cases, at the cost of tight coupling to partition names. PostgreSQL provides partition pruning to skip irrelevant children when querying the parent with proper predicates.

## 17. Moving from Jan to Feb vs. Jan to DEFAULT

Updating the date to an explicit partition:

~~~sql
BEGIN;

UPDATE partition_lab.sales_events
SET event_date = DATE '2026-02-21'
WHERE event_date = DATE '2026-01-05'
  AND event_id = 1001
RETURNING event_id, event_date, tableoid::regclass;

ROLLBACK;
~~~

routes to the February partition.

Updating to a date with no explicit partition:

~~~sql
BEGIN;

UPDATE partition_lab.sales_events
SET event_date = DATE '2026-05-15'
WHERE event_date = DATE '2026-01-05'
  AND event_id = 1001
RETURNING event_id, event_date, tableoid::regclass;

ROLLBACK;
~~~

routes to `sales_events_default`.

If the table **has no `DEFAULT`** and no matching partition exists, a key-changing `UPDATE` **fails** for lack of a destination. Automatic partition creation during `UPDATE` **does not exist** in standard declarative partitioning.

## 18. Error When Moving to a Non-Existent Partition

Using `missing_destination_demo`, which only has a January partition:

~~~sql
BEGIN;

INSERT INTO partition_lab.missing_destination_demo (
    event_id, event_date
)
VALUES (11, '2026-01-10');

-- INTENTIONAL ERROR: no Feb partition and no DEFAULT.
UPDATE partition_lab.missing_destination_demo
SET event_date = DATE '2026-02-10'
WHERE event_date = DATE '2026-01-10'
  AND event_id = 11;

-- Must ROLLBACK after an error in a transaction.
ROLLBACK;
~~~

With no destination partition, PostgreSQL cannot keep the row in Jan because the new value violates Jan's bounds. The transaction fails and cannot commit.

### Distinguish from an UPDATE Matching Zero Rows

~~~sql
UPDATE partition_lab.sales_events
SET event_date = DATE '2026-02-10'
WHERE event_date = DATE '2026-01-09'
  AND event_id = 1001;
~~~

This updates **0 rows** because `WHERE` matches nothing—completely different from "matched a row, but no destination partition exists."

Applications should check `UPDATE ... RETURNING` or affected row counts to distinguish stale input state from structural partition errors.

## 19. PRIMARY KEY and UNIQUE on Partitioned Tables

A `PRIMARY KEY` or `UNIQUE` constraint declared on a **partitioned parent table** must obey PostgreSQL's declarative partitioning rules: all partition key columns **must be included in the unique constraint**. When partition keys use expressions or functions, additional restrictions apply.

Why?

PostgreSQL primarily enforces uniqueness using **per-partition local indexes**. If you declared only `UNIQUE(event_id)` on a table partitioned by `event_date`, two rows with the same `event_id` on different dates could land in separate partitions whose local unique indexes cannot see one another.

Therefore, in our lab we chose:

~~~sql
PRIMARY KEY (event_date, event_id)
~~~

instead of:

~~~sql
-- INTENTIONALLY INVALID for a table partitioned by event_date:
ALTER TABLE partition_lab.sales_events
ADD CONSTRAINT uq_only_event_id UNIQUE (event_id);
~~~

A constraint on `event_id` alone excludes the partition key and fails parent uniqueness requirements.

### A Composite PK Does Not Guarantee Table-Wide event_id Uniqueness

Two records:

~~~text
event_date = 2026-01-05, event_id = 9001
event_date = 2026-02-05, event_id = 9001
~~~

have **distinct composite keys** because their dates differ. They can coexist under the table's primary key even if business rules disallow it.

Never use `PRIMARY KEY (event_date,event_id)` and claim PostgreSQL enforces **`event_id` alone** as globally unique.

## 20. How to Design When event_id Must Be Globally Unique

If business rules forbid repeating an ID across months, several strategies exist:

1. **Choose a partition key compatible with the unique key**, e.g., hash-partitioning by ID if time-range retention isn't needed.
2. **Make date/tenant part of the business key** if that genuinely reflects the entity's natural identity.
3. **Use an unpartitioned registry table with `PRIMARY KEY(event_id)`**, inserting into the registry and partitioned table in the same transaction.
4. **Use sequences or UUIDs to minimize collision risk**, remembering that an ID generator is not a database-enforced table-wide unique constraint if another source can insert arbitrary IDs.
5. **Rethink the data model** if frequent date edits clash with stable identity requirements.

Registry example:

~~~sql
CREATE TABLE partition_lab.event_identity_registry (
    event_id bigint PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now()
);
~~~

Creation flow:

~~~sql
BEGIN;

INSERT INTO partition_lab.event_identity_registry(event_id)
VALUES (6001);

INSERT INTO partition_lab.sales_events (
    event_date, event_id, tenant_id, amount
)
VALUES ('2026-02-18', 6001, 1, 10.00);

COMMIT;
~~~

If two transactions try to claim the same `event_id`, the registry's unique key blocks one of them. However, the application must **enforce this protocol across all write paths**, avoid bypassing the registry, and manage registry cleanup/updates when partitioned rows change.

### Why Must the Registry Share the Same Transaction?

If the registry `INSERT` commits first and the partitioned `INSERT` fails afterward, you are left with a "reserved" ID and no matching event. Some workflows accept that intentionally with recovery logic, yet for atomic event creation both inserts belong in one transaction.

## 21. Updating the Date and Colliding with the Composite Primary Key

Suppose you already have:

~~~text
(2026-01-05, event_id=1001)
(2026-02-18, event_id=1004)
~~~

Moving event 1001 to Feb 18 while keeping ID 1001 **does not conflict** with event 1004 because the key pairs differ.

Yet if another event already exists with key:

~~~text
(2026-02-18, event_id=1001)
~~~

then moving event 1001 from Jan to `(2026-02-18,1001)` violates the composite PK's uniqueness.

Test safely in the lab:

~~~sql
BEGIN;

INSERT INTO partition_lab.sales_events (
    event_date, event_id, tenant_id, amount
)
VALUES ('2026-02-18', 1001, 1, 5.00);

-- INTENTIONAL ERROR: destination (2026-02-18,1001) already exists.
UPDATE partition_lab.sales_events
SET event_date = DATE '2026-02-18'
WHERE event_date = DATE '2026-01-05'
  AND event_id = 1001;

ROLLBACK;
~~~

Upon unique violation, the transaction errors and must roll back. PostgreSQL will never automatically merge two rows simply because their `event_id` matches.

## 22. How ON CONFLICT Handles Duplicates on INSERT

With the composite PK:

~~~sql
BEGIN;

INSERT INTO partition_lab.sales_events (
    event_date, event_id, tenant_id, amount
)
VALUES ('2026-01-05', 1001, 1, 120.00)
ON CONFLICT (event_date, event_id)
DO NOTHING
RETURNING event_id, event_date;

ROLLBACK;
~~~

Since `(2026-01-05,1001)` already exists, `DO NOTHING` returns **0 rows**.

An upsert updating a non-key field:

~~~sql
BEGIN;

INSERT INTO partition_lab.sales_events (
    event_date, event_id, tenant_id, amount
)
VALUES ('2026-01-05', 1001, 1, 135.00)
ON CONFLICT (event_date, event_id)
DO UPDATE
SET
    amount = EXCLUDED.amount,
    updated_at = clock_timestamp()
RETURNING
    event_id, event_date, amount,
    tableoid::regclass AS physical_partition;

ROLLBACK;
~~~

Here the conflicting row sits in Jan and `DO UPDATE` modifies only `amount` without changing the date, so **no partition movement occurs**.

### Same event_id on a Different Date Is Not a Conflict

~~~sql
BEGIN;

INSERT INTO partition_lab.sales_events (
    event_date, event_id, tenant_id, amount
)
VALUES ('2026-02-05', 1001, 1, 135.00)
ON CONFLICT (event_date, event_id) DO NOTHING
RETURNING event_id, event_date, tableoid::regclass;

ROLLBACK;
~~~

Even though `event_id = 1001` exists in Jan, the new `(event_date,event_id)` pair is **distinct**, so `INSERT` creates a **second row**. That obeys the constraint while possibly violating your intended business identity.

## 23. An Important Limitation of ON CONFLICT DO UPDATE

In PostgreSQL versions supporting declarative partitioned upserts, `INSERT ... ON CONFLICT DO UPDATE` **does not support moving the conflicting row to a different partition** by altering its partition key inside the `DO UPDATE` clause.

A deceptive mistake:

~~~sql
-- INTENTIONALLY INVALID: DO UPDATE tries to change the partition key
-- of the conflicting row from Jan to Feb.
INSERT INTO partition_lab.sales_events (
    event_date, event_id, tenant_id, amount
)
VALUES ('2026-01-05', 1001, 1, 140.00)
ON CONFLICT (event_date, event_id)
DO UPDATE
SET event_date = DATE '2026-02-05';
~~~

This is **not equivalent** to a normal `UPDATE` targeting the parent table with row movement.

The right way when business logic truly wants to update the date:

~~~sql
BEGIN;

UPDATE partition_lab.sales_events
SET
    event_date = DATE '2026-02-05',
    amount = 140.00
WHERE event_date = DATE '2026-01-05'
  AND event_id = 1001
RETURNING event_id, event_date, tableoid::regclass;

ROLLBACK;
~~~

### Upsert Summary

- Fresh `INSERT`: routes by the new key.
- `ON CONFLICT DO NOTHING`: skips rows matching the composite key.
- `ON CONFLICT DO UPDATE`: updates in place within the conflicting row's current partition; never rely on it to relocate rows across partitions.
- `UPDATE` via parent: the explicit path to alter the partition key and trigger row movement in supported PostgreSQL versions.

Never assume "UPSERT will look up the row by `event_id` and move it to the new month" when the unique key is actually `(event_date,event_id)`.

## 24. Triggers When an UPDATE Causes Row Movement

Row movement has special effects on triggers.

In principle in PostgreSQL, because a cross-partition `UPDATE` executes as **DELETE from source + INSERT into destination**, row-level triggers fire differently from an intra-partition `UPDATE`.

Under standard row-movement mechanics:

- Row-level **`BEFORE UPDATE`** on the source partition fires.
- Row-level **`BEFORE DELETE`** on the source partition fires.
- Row-level **`BEFORE INSERT`** on the destination partition fires.
- Afterward, row-level **`AFTER DELETE`** on source and **`AFTER INSERT`** on destination fire instead of **`AFTER UPDATE`** for the relocated row.
- Statement-level triggers for `UPDATE` fire according to statement-trigger rules on the target SQL table; a cross-partition `UPDATE` is not treated as two separate SQL statements sent by the client.

**Trigger specifics are a strong reason to check docs for your exact PostgreSQL major version**, especially when using audit trails, outbox tables, or cascading triggers.

### Do Not Turn One UPDATE into Two Unintended Business Events

If your application uses an `AFTER INSERT` trigger emitting "order created" and an `AFTER DELETE` trigger emitting "order deleted," **correcting an event date** can be misread by consumers as **canceling an old order and creating a new one** unless triggers/outboxes distinguish row movement.

Clarify explicitly:

- Does the event mean "row physically inserted" or "business entity created"?
- Does it mean "row physically deleted" or "business entity cancelled"?
- Should cross-partition moves emit a distinct `event.date_corrected` domain event?
- Do consumers enforce idempotency/deduplication by business key?

Never rely on `TG_OP` inside a row trigger alone to infer exact business semantics in all cases.

## 25. Trigger Lab: Observing DELETE and INSERT During Row Movement

Create a practice audit log **with no external email or API calls**.

~~~sql
CREATE TABLE partition_lab.dml_log (
    log_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    action text NOT NULL,
    relation_name text NOT NULL,
    event_id bigint NOT NULL,
    event_date date NOT NULL,
    logged_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE OR REPLACE FUNCTION partition_lab.log_sales_event_row()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        INSERT INTO partition_lab.dml_log(
            action, relation_name, event_id, event_date
        )
        VALUES (
            TG_OP,
            TG_RELID::regclass::text,
            OLD.event_id,
            OLD.event_date
        );
    ELSIF TG_OP = 'INSERT' THEN
        INSERT INTO partition_lab.dml_log(
            action, relation_name, event_id, event_date
        )
        VALUES (
            TG_OP,
            TG_RELID::regclass::text,
            NEW.event_id,
            NEW.event_date
        );
    END IF;

    -- Return value of an AFTER ROW trigger is ignored.
    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_sales_event_audit_ins_del
AFTER INSERT OR DELETE
ON partition_lab.sales_events
FOR EACH ROW
EXECUTE FUNCTION partition_lab.log_sales_event_row();
~~~

In declarative partitioning, row-level triggers defined on the parent propagate across partitions per PostgreSQL rules.

Test:

~~~sql
BEGIN;

UPDATE partition_lab.sales_events
SET event_date = DATE '2026-02-12'
WHERE event_date = DATE '2026-01-05'
  AND event_id = 1001;

SELECT
    action,
    relation_name,
    event_id,
    event_date
FROM partition_lab.dml_log
ORDER BY log_id;

ROLLBACK;
~~~

You will observe a **`DELETE` on Jan and an `INSERT` on Feb** reflecting row movement. Because the log inserts run inside the same transaction, `ROLLBACK` reverts both the log rows and the date change.

### Never Add This Trigger in Production Just to Observe

Logging every row trigger into another table increases WAL, latency, and lock/constraint contention. Adding an audit trigger in production just to inspect behavior alters the very workload you are measuring.

After the lab, keep everything inside the isolated practice schema. To reset lab data later, follow your verified schema-reset process.

## 26. Can a BEFORE Trigger Arbitrarily Reroute to Another Partition?

A risky assumption:

> "I'll always `INSERT` into the current month, and let a `BEFORE INSERT` trigger rewrite `event_date` to another month so PostgreSQL re-routes it."

Do not design around this assumption. PostgreSQL enforces restrictions when a **`BEFORE ROW` trigger** attempts to modify the partition key in a way that would route the row to a different partition than originally selected; it is not an unrestricted re-routing mechanism.

The safe pattern is:

1. **Normalize and determine the partition key before sending `INSERT`**.
2. Send writes through the **parent table**.
3. Let PostgreSQL route by the finalized key.
4. Use constraints and triggers for validation/business logic—**never rely on triggers to silently redirect partitions**.

For `UPDATE`s as well, examine interactions between `BEFORE` triggers and row movement. If a trigger mutates partition-key fields, verify behavior on your version with explicit tests.

## 27. Foreign Keys and Row Movement

Other tables may reference an event.

If the identifying key is:

~~~text
(event_date, event_id)
~~~

and a child table holds a foreign key to this pair, changing `event_date` **also alters part of the referenced key**.

Potential consequences:

- Foreign key checks must verify child rows.
- With `ON UPDATE CASCADE`, key changes cascade updates into child tables.
- With `RESTRICT`/`NO ACTION` in specific cases, the transaction fails if child references break.
- Execution overhead climbs sharply if many child tables reference the key.
- Locking and concurrency grow more complex than a regular column update.

**Design lesson:** if event dates are corrected often, embedding the date in the primary key forces every referencing foreign key to bear key-mutation costs. Revisit object identity and partitioning strategy before picking a date-based composite PK purely for syntax convenience.

### Do Not Confuse Row Movement with Changing Object Identity

Applications may treat `event_id` as a single persistent entity, while the database uses a composite PK to satisfy per-partition uniqueness. Keep both perspectives consistent; never rely on `ctid` or `tableoid` as durable business IDs.

## 28. UPDATE FROM and the Risk of Multiple Source Rows per Target

PostgreSQL supports updating from a source table/CTE:

~~~sql
WITH date_corrections (
    event_id,
    old_date,
    new_date
) AS (
    VALUES
        (1001::bigint, DATE '2026-01-05', DATE '2026-02-12'),
        (1002::bigint, DATE '2026-01-31', DATE '2026-03-05')
)
UPDATE partition_lab.sales_events AS e
SET
    event_date = c.new_date,
    updated_at = clock_timestamp()
FROM date_corrections AS c
WHERE e.event_id = c.event_id
  AND e.event_date = c.old_date
RETURNING
    e.event_id,
    e.event_date,
    e.tableoid::regclass AS physical_partition;
~~~

When testing in the lab, wrap in `BEGIN ... ROLLBACK` to preserve seed rows.

### A Specific Risk of UPDATE FROM

If `date_corrections` contains **multiple source rows** matching the same target row with different `new_date` values, the update outcome is non-deterministic; PostgreSQL does not guarantee which source row wins when the join is non-unique.

Therefore:

- Guarantee exactly one correction per target key.
- Enforce a unique constraint on the correction key if stored in a table.
- Or pick a deterministic winner via `ROW_NUMBER`/`DISTINCT ON`.
- Match `old_date` explicitly to avoid accidentally updating an `event_id` repeated in another partition.

**Never fix dates across millions of rows using `UPDATE FROM` before deduplicating the source mapping.**

## 29. A Multi-Row UPDATE Can Fan Out to Multiple Target Partitions

One statement:

~~~sql
BEGIN;

UPDATE partition_lab.sales_events
SET event_date = event_date + 31
WHERE event_date >= DATE '2026-01-01'
  AND event_date < DATE '2026-02-01'
RETURNING
    event_id,
    event_date,
    tableoid::regclass AS physical_partition;

ROLLBACK;
~~~

On the seed data:

- Jan 05 + 31 days → Feb 05.
- Jan 31 + 31 days → Mar 03.

One `UPDATE` can scatter **January source rows into multiple distinct target partitions**. Each row is routed individually based on its new partition key.

This is completely different from "renaming the January partition to February": renaming a table only updates metadata without changing `event_date` values or moving individual rows.

### Performance Considerations

A bulk cross-partition `UPDATE` generates:

- Many physical `DELETE`/`INSERT` operations.
- WAL volume and index maintenance on both source and destination partitions.
- Row triggers and FK checks.
- Lock contention.
- Dead tuples in the source partition.
- `VACUUM` and replication pressure.
- Long-running transactions if millions of rows are updated at once.

Evaluate batch sizes and operational impact before running large migrations.

## 30. Concurrent Transactions: Row Movement Can Cause Serialization Failures

Partitioning does not bypass MVCC or row-level locks. When two transactions modify the same row, PostgreSQL coordinates them.

One subtle race occurs when one transaction **moves a row to another partition** while a second transaction has already begun an `UPDATE`/`DELETE` targeting the old version.

In PostgreSQL versions supporting row movement, certain concurrent races raise an error such as:

~~~text
ERROR: tuple to be updated was already moved to another partition
SQLSTATE: 40001 (serialization_failure)
~~~

Exact wording varies by version and command, yet the takeaway is clear: **once a row moves partitions, PostgreSQL cannot always silently re-apply a concurrent `UPDATE`/`DELETE` on that row the way it would within a single partition**.

### Why Can't It Just "Wait and Continue Updating"?

Row movement changes the physical source and destination relations. The competing transaction may already be scanning a specific source partition under an older snapshot/condition. Automatically chasing a moved row across partitions in all cases could violate concurrency semantics.

The safe response to `40001` is to **roll back and retry the entire transaction**, re-reading the row and re-evaluating business logic against the new state.

## 31. Two-Session Lab: UPDATE Hitting a Row Being Moved Across Partitions

Open two `psql` sessions connected to the same lab database.

**Note:** this exercise uses a real `COMMIT` to demonstrate concurrency. Run it only when the lab still holds the exact seed `(2026-01-05,1001)`, with no other concurrent work on that row, and never in production.

**Session A:**

~~~sql
BEGIN;

UPDATE partition_lab.sales_events
SET event_date = DATE '2026-02-12'
WHERE event_date = DATE '2026-01-05'
  AND event_id = 1001
RETURNING event_id, event_date, tableoid::regclass;

-- Do NOT COMMIT yet; hold transaction A open.
~~~

**Session B, run while A is uncommitted:**

~~~sql
BEGIN;

UPDATE partition_lab.sales_events
SET
    status = 'paid',
    updated_at = clock_timestamp()
WHERE event_date = DATE '2026-01-05'
  AND event_id = 1001
RETURNING event_id, event_date, status;

-- Will block waiting on A.
~~~

**Session A finishes:**

~~~sql
COMMIT;
~~~

Once A commits, the waiting statement in B **can raise a concurrency/serialization error** because the row moved to a different partition. Under other interleavings (e.g., if B started only after A committed), B simply updates 0 rows because `WHERE event_date='2026-01-05'` no longer matches.

If B errors:

~~~sql
ROLLBACK;
~~~

If B does not error, finish B appropriately based on what happened, then inspect the final state in a new transaction.

### Check State After the Race

~~~sql
SELECT
    event_id,
    event_date,
    status,
    tableoid::regclass AS physical_partition
FROM partition_lab.sales_events
WHERE event_id = 1001;
~~~

Then—strictly in the lab once both sessions finish—restore the original date and status:

~~~sql
UPDATE partition_lab.sales_events
SET
    event_date = DATE '2026-01-05',
    status = 'new',
    updated_at = clock_timestamp()
WHERE event_date = DATE '2026-02-12'
  AND event_id = 1001;
~~~

### Concurrency Takeaways

- A successful `UPDATE` does not mean competing transactions automatically "follow" the moved row.
- `40001` signals you must **retry the transaction**, not tack `ON CONFLICT DO NOTHING` onto an `UPDATE`.
- If a client blindly retries with the stale `old_date`, it may match 0 rows. Decide explicitly: "update only if date hasn't changed" vs. "look up by `event_id` and apply the update."
- When external systems are involved, retries require idempotency to avoid duplicate external side effects.

## 32. SERIALIZABLE, REPEATABLE READ, and READ COMMITTED

Isolation levels govern how PostgreSQL handles snapshots and conflicts:

| Isolation Level | Key Takeaway for Cross-Partition UPDATEs |
| --- | --- |
| `READ COMMITTED` | Each statement takes a fresh snapshot; during a row-movement race it can still raise `40001` in specific cases |
| `REPEATABLE READ` | Transaction keeps one consistent snapshot; concurrent update conflicts abort the transaction rather than adopting newer versions |
| `SERIALIZABLE` | Adds serialization anomaly detection; always be ready to retry on `40001` |

Under every isolation level, **row movement must still obey bounds and constraints**. Isolation never permits placing a row into the wrong partition.

### What Should You Retry?

Right:

~~~text
BEGIN new transaction
  SELECT current data / required business preconditions
  Verify state and permissions
  UPDATE if still valid
COMMIT
~~~

Wrong:

~~~text
Keep decisions computed from the stale snapshot
Replay only the final UPDATE statement
Assume old event_date is still valid
~~~

If another transaction already committed a date change, business logic must decide whether to report a conflict, accept the new date, or ask the user to confirm.

## 33. Never Use tableoid/ctid as Persistent Identifiers

In diagnostic queries, `tableoid::regclass` is great for seeing which partition holds a row.

However:

- `tableoid` reflects a physical relation OID, whose meaning changes across maintenance, attach/detach, rebuilds, or partition moves.
- `ctid` is a physical tuple slot that changes on `UPDATE`, `VACUUM FULL`, and row movement.
- `xmin` is transaction metadata for a tuple version, not a stable business ID.

When row movement occurs, never persist `(tableoid,ctid)` as a long-lived API key. Rely on business identifiers and proper constraints.

**Practical reality:** if the physical primary key is `(event_date,event_id)` and `event_date` can change, design stable entity lookup at the API layer; never assume `event_id` alone is unique across the entire partitioned table.

## 34. Queries Must Filter by the Partition Key for Pruning to Work

A query:

~~~sql
EXPLAIN
SELECT event_id, amount
FROM partition_lab.sales_events
WHERE event_date >= DATE '2026-02-01'
  AND event_date < DATE '2026-03-01';
~~~

lets PostgreSQL **prune** partitions not intersecting February.

Conversely:

~~~sql
EXPLAIN
SELECT event_id, amount
FROM partition_lab.sales_events
WHERE date_trunc('month', event_date) =
      timestamp '2026-02-01 00:00:00';
~~~

wraps the partition key in an expression, so the planner cannot reliably deduce the same bound exclusions as a direct range predicate.

### Routing vs. Pruning

- `INSERT` with a Feb date routes to Feb.
- `UPDATE` changing Jan → Feb routes the new version to Feb.
- `SELECT` reading only Feb prunes Jan/Mar/`DEFAULT` when predicates allow.

All three involve the partition key, yet serve different roles.

### Do Not Query Child Tables Just to "Pick the Right Partition"

Query through the parent using clear predicates. Direct child queries are handy for maintenance/diagnostics, but couple application code to manual partition naming.

## 35. EXPLAIN for INSERT/UPDATE on Partitioned Tables

For `SELECT`, use:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, event_date, amount
FROM partition_lab.sales_events
WHERE event_date = DATE '2026-02-18';
~~~

For `UPDATE`, inspect the plan safely with:

~~~sql
EXPLAIN
UPDATE partition_lab.sales_events
SET event_date = DATE '2026-02-22'
WHERE event_date = DATE '2026-01-05'
  AND event_id = 1001;
~~~

`EXPLAIN` without `ANALYZE` only displays the estimated plan without executing the `UPDATE`.

To measure actual execution:

~~~sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL)
UPDATE partition_lab.sales_events
SET event_date = DATE '2026-02-22'
WHERE event_date = DATE '2026-01-05'
  AND event_id = 1001;

ROLLBACK;
~~~

`EXPLAIN ANALYZE` **actually runs the `UPDATE`**, so only run it wrapped in a rolled-back transaction in a lab or disposable database.

The `WAL` option is available in supported PostgreSQL versions (PostgreSQL 13+). Exact node names and details vary across versions and plans; do not require outputs to match another machine verbatim.

## 36. Overhead of Routed INSERTs

Partitioning helps organize storage and prune reads, yet `INSERT` incurs extra steps:

1. Evaluate the partition key from input values.
2. Locate the target partition.
3. Verify partition bounds/constraints.
4. Write the tuple to the target partition's heap.
5. Update matching indexes on that partition.
6. Write WAL and fire relevant triggers/FKs/constraints.
7. Handle concurrency and commit.

Actual overhead depends on partition count, tree depth, index count, row width, key distribution, buffer cache, and concurrency.

### One Multi-Row INSERT Is Not 100 Round Trips to 100 Partitions

PostgreSQL executes a multi-row `INSERT` statement and routes each tuple server-side. At the SQL/network level it remains one statement/transaction, not 100 client round trips just because 100 partitions exist.

### What Happens with Too Many Partitions?

Thousands of partitions are not "automatically faster." They can increase:

- Planner, catalog, and metadata overhead.
- Startup time and memory for certain plans.
- Number of objects/indexes requiring maintenance.
- DDL, autovacuum, backup, and monitoring effort.
- Likelihood of connections/workloads touching too many partitions at once.

Choose granularity (day/week/month) from data volume, retention, query patterns, load, and operations—never merely for naming convenience.

## 37. Specific Costs of Cross-Partition UPDATEs

When an `UPDATE` modifies only `status` while keeping the date in Jan, it updates the tuple within Jan's heap.

When an `UPDATE` changes Jan → Feb, PostgreSQL performs cross-partition row movement between two relations:

| Aspect | Intra-Partition UPDATE | Cross-Partition UPDATE |
| --- | --- | --- |
| Data location | Stays in the same child | Moves source → destination |
| MVCC mechanics | New tuple version | Delete in source, insert in destination per semantics |
| Indexes | Updates affected index columns (and HOT if eligible) | Index updates and cleanup across both source and destination |
| Triggers | Normal row `UPDATE` path | Fires corresponding row `DELETE`/`INSERT` triggers |
| WAL | Proportional to row/indexes | Often higher due to writes across two relations |
| FK / constraints | Checked for changed columns | May add checks for key changes and relation moves |
| Locks/concurrency | Ordinary row conflicts | Adds row-movement `40001` races |
| Vacuum | Old version becomes dead tuple | Source gets dead tuple; destination gets new tuple |

This is a conceptual comparison, not a fixed slowdown factor. Measure on your real workload.

### Should You Frequently Update the Partition Key?

If 30% of daily events shift dates into another month, partitioning by `event_date` creates substantial write amplification.

Re-evaluate:

- Is the partition key truly stable?
- Could you partition by `ingested_at` or `created_at` instead?
- Could the mutable business date live in a **different** column from the physical partition key?
- Do queries/retention strictly require partitioning by business date?
- How will FK and global ID consistency be handled?

**A good partition key fits queries and stays relatively stable.** Not every date column belongs in `PARTITION BY`.

## 38. When to Update event_date vs. When Not To

Valid reasons to `UPDATE` the partition key:

- Data arrived with an erroneous date that was verified and must be corrected.
- An event's "effective date" changes per legitimate business rules.
- Controlled migration moving misplaced rows out of `DEFAULT` into standard time partitions.

Cases where you should **not** abuse partition-key `UPDATE`s:

- Simply purging expired data for retention.
- Renaming partitions or changing storage layout.
- Shifting all January rows into February without an actual business date change.
- "Merging" small partitions into a larger one outside a proper data migration.

For monthly retention, **`DETACH`/`DROP` old partitions** is an entirely different operational workflow from updating millions of `event_date` values. Retention deletes or archives old periods—it doesn't rewrite historical business dates.

## 39. Batching UPDATEs Across Millions of Rows

PostgreSQL does not support `UPDATE ... LIMIT n` directly like some other DBMSs.

To migrate a large set of rows, select **a deterministic batch of keys** and update them, as shown in this lab pattern:

~~~sql
BEGIN;

WITH picked AS (
    SELECT
        event_date AS old_date,
        event_id
    FROM partition_lab.sales_events
    WHERE event_date >= DATE '2026-01-01'
      AND event_date <  DATE '2026-02-01'
    ORDER BY event_date, event_id
    LIMIT 100
    FOR UPDATE SKIP LOCKED
)
UPDATE partition_lab.sales_events AS e
SET
    event_date = e.event_date + 31,
    updated_at = clock_timestamp()
FROM picked AS p
WHERE e.event_date = p.old_date
  AND e.event_id = p.event_id
RETURNING
    e.event_id,
    e.event_date,
    e.tableoid::regclass AS physical_partition;

ROLLBACK;
~~~

This is a **syntax illustration**, not a complete migration framework.

Also account for:

- Batch ordering and termination conditions.
- Concurrent ingestion into old and new months.
- Whether rows skipped by `SKIP LOCKED` will be revisited in subsequent passes.
- Rows updated per commit, lock timeouts, and WAL volume.
- Unique key collisions at the destination partition.
- Recovery checkpoints if the job crashes mid-run.
- Idempotency of date shifts (adding 31 days twice is **not idempotent**).

### Never Unconditionally Re-Run Relative Date Shifts on Retry

~~~sql
SET event_date = event_date + 31
~~~

executed twice shifts rows into yet another month. A retry-safe migration checks an **explicit source date** or a deterministic `old_date → new_date` mapping with proper checkpoints and transactions.

## 40. COPY and Bulk Ingestion

For high-volume ingestion, PostgreSQL supports `COPY FROM` into a partitioned parent table under the syntax and version rules for partitioned tables. Rows are routed to their matching partitions.

Concept:

~~~sql
-- Syntax illustration; requires an actual file and appropriate privileges.
COPY partition_lab.sales_events (
    event_date, event_id, tenant_id, status, amount
)
FROM '/path/to/events.csv'
WITH (FORMAT csv, HEADER true);
~~~

`/path/to/events.csv` is just a placeholder—**do not run verbatim**. Server-side `COPY FROM 'file'` requires server filesystem access and privileges; `psql`'s `\copy` is a separate client-side workflow.

### Bulk Load Checklist

1. Pre-create partitions covering the entire incoming date range.
2. Monitor `DEFAULT` row counts if a `DEFAULT` partition exists.
3. Normalize timezones and dates before loading.
4. Validate unique keys and referential data.
5. Prepare a batch error-handling strategy.
6. Account for index, WAL, and replica lag impact.
7. Use a staging table when pre-validation or deduplication is needed.
8. Run `ANALYZE` on affected tables after large loads when appropriate.

Never drop constraints or safety checks recklessly just to speed up bulk loading.

## 41. CREATE INDEX on Parent and Partitions

A partitioned parent holds no ordinary data heap. Creating an index under PostgreSQL declarative partitioning manages a **partitioned index** on the parent alongside corresponding indexes on child partitions via supported DDL.

Example:

~~~sql
CREATE INDEX idx_sales_events_tenant_date
ON partition_lab.sales_events (
    tenant_id,
    event_date DESC,
    event_id
);
~~~

This index can accelerate:

~~~sql
SELECT event_id, event_date, amount
FROM partition_lab.sales_events
WHERE tenant_id = 1
  AND event_date >= DATE '2026-01-01'
  AND event_date < DATE '2026-02-01'
ORDER BY event_date DESC, event_id
LIMIT 20;
~~~

Never confuse **partition routing** with **index lookup**:

- Routing uses `event_date` to pick the child partition.
- Child indexes speed up finding/reading rows **inside that child** when predicates match.

Every `INSERT` must still route to the right child and maintain its local indexes.

### Inspecting Indexes

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'partition_lab'
  AND tablename LIKE 'sales_events%'
ORDER BY tablename, indexname;
~~~

If the parent defines a primary key, each partition also receives a matching index backing that constraint. Never add duplicate child indexes without checking first.

## 42. Why Indexes Do Not Replace Partitioning Rules

An index on `event_date` does not allow inserting Feb 15 into the January partition.

Conversely, effective partition pruning does not make queries inside a partition automatically fast; a 100-million-row partition still needs B-tree, BRIN, or other appropriate indexes.

Ask four separate questions:

1. **Do I have partitions covering all incoming write ranges?**
2. **Do `SELECT` predicates enable partition pruning?**
3. **Does each partition have indexes tailored to post-pruning queries?**
4. **How many indexes must each tuple write maintain inside a child?**

Addressing all four beats blindly adding more partitions.

## 43. Impact on Logical Replication and CDC

Downstream systems often consume PostgreSQL changes via logical replication or CDC. Physical row movement is critical when designing change streams.

Depending on PostgreSQL version, publication configuration, and connector behavior, a cross-partition `UPDATE` may be emitted/observed as **`DELETE` on source and `INSERT` on destination**, or mapped by the connector into another logical event.

When using Kafka/CDC/outbox pipelines:

- Verify the exact event types your connector emits.
- Confirm whether the business key remains stable when dates change.
- Never blindly interpret `DELETE+INSERT` as a real customer cancellation followed by a new order.
- Define reconciliation rules when consumers see out-of-order events.
- Enforce consumer idempotency on replay.
- Verify replica identity and the keys CDC uses to identify before/after rows.

Never extrapolate from an MVCC diagram to assume every PostgreSQL version and connector emits identical external events. **Test on your actual replication stack.**

## 44. Row Movement and Side Effects

A cross-partition `UPDATE` can touch:

- Row-level triggers on source and destination.
- Foreign key checks, including cascades.
- Audit logging.
- WAL and physical/logical replication.
- Indexes across both partitions.
- Autovacuum workload.
- CDC consumers.
- Application caches keyed by composite key.
- Child tables referencing `(event_date,event_id)`.

In any application, ask:

> If an event's date changes, can every system storing a reference to it still locate the exact entity?

If APIs pass only `event_id` while the database permits duplicate `event_id`s across dates, changing dates or moving partitions makes ID-only lookups ambiguous.

Never let partitioning undermine **business identity contracts**.

## 45. Date, Timestamp, and Timezone in Time-Partitioned Tables

Our lab uses `date` for clean boundaries. In production, many tables use `timestamptz`.

Example:

~~~sql
PARTITION BY RANGE (occurred_at)
~~~

with bounds like:

~~~sql
FOR VALUES FROM ('2026-01-01 00:00:00+00')
           TO ('2026-02-01 00:00:00+00')
~~~

Real-world systems must account for:

- Whether data boundaries follow UTC instants or local business days.
- Whether events from multiple timezones share one effective business date.
- Where conversions between `timestamp without time zone` and `timestamptz` occur.
- Whether monthly boundaries in DST-observing timezones convert accurately.
- Whether applications accidentally send timezone-less strings relying on session `TimeZone`.

If business rules split by "settlement day in Vietnam," explicitly define how timestamps map to business dates before routing. Never assume "UTC day" and "local day" match.

### Never Rush Changing Partition Key Data Types to Patch Timezone Bugs

Changing date/timestamp column types affects indexes, bounds, `CHECK` constraints, query plans, replication, and data migrations. Define **temporal semantics** first, then design the partition key.

## 46. How LIST and HASH Differ from RANGE

### LIST

Example:

~~~sql
CREATE TABLE partition_lab.region_events (
    event_id bigint NOT NULL,
    region_code text NOT NULL,
    description text
) PARTITION BY LIST (region_code);

CREATE TABLE partition_lab.region_events_north
PARTITION OF partition_lab.region_events
FOR VALUES IN ('NORTH');

CREATE TABLE partition_lab.region_events_south
PARTITION OF partition_lab.region_events
FOR VALUES IN ('SOUTH');

CREATE TABLE partition_lab.region_events_default
PARTITION OF partition_lab.region_events
DEFAULT;
~~~

An `INSERT` with `region_code = 'SOUTH'` routes to the South child. An `UPDATE` through the parent changing `region_code` to `'NORTH'` moves the row to the North child.

### HASH

Syntax example:

~~~sql
CREATE TABLE partition_lab.tenant_events (
    tenant_id integer NOT NULL,
    event_id bigint NOT NULL,
    payload text
) PARTITION BY HASH (tenant_id);

CREATE TABLE partition_lab.tenant_events_p0
PARTITION OF partition_lab.tenant_events
FOR VALUES WITH (MODULUS 2, REMAINDER 0);

CREATE TABLE partition_lab.tenant_events_p1
PARTITION OF partition_lab.tenant_events
FOR VALUES WITH (MODULUS 2, REMAINDER 1);
~~~

PostgreSQL routes by the hash of the partition key. If an `UPDATE` modifies `tenant_id` and its hash maps to the other remainder, row movement also occurs.

**Key difference:** `DEFAULT` partitions work for `RANGE`/`LIST` per supported syntax; never assume `HASH` has a `DEFAULT` partition like those two.

### Regardless of RANGE/LIST/HASH, Enforce Business Invariants

Just because you *can* `UPDATE` a partition key doesn't mean you should allow mutating a record's `tenant_id` without checking authorization and related FK/unique constraints.

## 47. Inspecting the Partition Tree

PostgreSQL provides catalogs and helper functions to inspect partition structure.

On versions supporting `pg_partition_tree`:

~~~sql
SELECT
    relid::regclass AS relation_name,
    parentrelid::regclass AS parent_relation,
    isleaf,
    level
FROM pg_partition_tree(
    'partition_lab.sales_events'::regclass
)
ORDER BY level, relation_name;
~~~

Where unavailable, inspect `pg_inherits` or equivalent metadata views.

To view partition bounds from `pg_class.relpartbound`:

~~~sql
SELECT
    c.oid::regclass AS partition_name,
    pg_get_expr(c.relpartbound, c.oid) AS partition_bound
FROM pg_class AS c
JOIN pg_inherits AS i
    ON i.inhrelid = c.oid
WHERE i.inhparent = 'partition_lab.sales_events'::regclass
ORDER BY c.oid::regclass::text;
~~~

Catalog metadata helps catch:

- Whether all upcoming months are created.
- Whether a `DEFAULT` partition exists.
- Whether bounds are contiguous without gaps.
- Whether any child is misnamed or omitted.
- Whether intermediate subpartition layers exist.

Never just check "does the table exist"—verify the actual bounds.

## 48. Monitoring Where Data Actually Resides

Row counts per physical partition:

~~~sql
SELECT
    tableoid::regclass AS physical_partition,
    COUNT(*) AS logical_rows,
    MIN(event_date) AS oldest_date,
    MAX(event_date) AS newest_date
FROM partition_lab.sales_events
GROUP BY tableoid
ORDER BY tableoid::regclass::text;
~~~

This reads real data across partitions. On multi-billion-row tables, avoid running it every second for monitoring; use catalog statistical estimates for routine dashboards and exact queries only when needed.

### Comparing with pg_stat_user_tables

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_autovacuum,
    last_analyze
FROM pg_stat_user_tables
WHERE schemaname = 'partition_lab'
  AND relname LIKE 'sales_events%'
ORDER BY relname;
~~~

`n_live_tup`/`n_dead_tup` are estimates, not exact live counts. When a partition experiences heavy row movement out of it, `n_dead_tup` rises and requires autovacuum/maintenance attention.

## 49. When Should New Partitions Be Created?

With monthly RANGE partitioning, maintain a disciplined workflow:

1. Pre-create partitions for upcoming months ahead of time.
2. Verify bounds are exact with no overlaps.
3. Confirm indexes, constraints, privileges, and triggers propagate as expected.
4. Check whether `DEFAULT` holds any data requiring migration.
5. Test `INSERT`s on the first day, last day, and boundary edge of each partition.
6. Monitor row counts landing in `DEFAULT`.
7. Alert well before the latest pre-created date bound runs out.
8. Maintain retention/`DETACH`/archival workflows for expired months.
9. Keep a rollback plan for failed DDL.
10. Never run ad-hoc bound-changing scripts during peak write load without assessing locks.

### Pre-Month Check Example

~~~sql
SELECT
    event_id,
    event_date,
    tableoid::regclass AS physical_partition
FROM partition_lab.sales_events
WHERE event_date >= DATE '2026-04-01'
ORDER BY event_date, event_id;
~~~

With the initial seed, an April row already sits in `DEFAULT`. That signals a data migration is needed before adding the April partition—**not a reason to delete `DEFAULT` rows blindly**.

## 50. Passing Partitioned Data Through JDBC

In Java/JDBC, insert through the parent table and bind the partition key with an appropriate SQL type.

Java example:

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.Date;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.LocalDate;

public record InsertedEvent(
    long eventId,
    LocalDate eventDate,
    String partitionName
) {}

public static InsertedEvent insertEvent(
        Connection connection,
        long eventId,
        LocalDate eventDate,
        int tenantId,
        BigDecimal amount
) throws SQLException {

    String sql = """
        INSERT INTO partition_lab.sales_events (
            event_date,
            event_id,
            tenant_id,
            amount
        )
        VALUES (?, ?, ?, ?)
        RETURNING
            event_id,
            event_date,
            tableoid::regclass::text AS partition_name
        """;

    try (PreparedStatement ps =
             connection.prepareStatement(sql)) {

        ps.setDate(1, Date.valueOf(eventDate));
        ps.setLong(2, eventId);
        ps.setInt(3, tenantId);
        ps.setBigDecimal(4, amount);

        try (ResultSet rs = ps.executeQuery()) {
            if (!rs.next()) {
                throw new SQLException(
                    "INSERT did not return an event"
                );
            }

            return new InsertedEvent(
                rs.getLong("event_id"),
                rs.getDate("event_date").toLocalDate(),
                rs.getString("partition_name")
            );
        }
    }
}
~~~

This passes `LocalDate` to a `date` column. pgJDBC can also use `setObject` with `java.time` types depending on driver version; pick one consistent convention across your codebase.

### Never Accept Partition Names from Clients as SQL Table Names

An anti-pattern:

~~~java
// Never interpolate partition names from untrusted input:
String sql = "INSERT INTO " + userSuppliedPartition + " ...";
~~~

This tightly couples applications to storage details and introduces SQL injection risk if identifiers aren't strictly controlled.

Use `INSERT INTO partition_lab.sales_events ...` and bind **the `event_date` value as a parameter**, letting PostgreSQL pick the destination.

## 51. JDBC: Moving Dates and Checking Affected Rows

~~~java
import java.sql.Connection;
import java.sql.Date;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.LocalDate;

public static boolean moveEventDate(
        Connection connection,
        long eventId,
        LocalDate oldDate,
        LocalDate newDate
) throws SQLException {

    String sql = """
        UPDATE partition_lab.sales_events
        SET
            event_date = ?,
            updated_at = clock_timestamp()
        WHERE event_date = ?
          AND event_id = ?
        RETURNING event_id
        """;

    try (PreparedStatement ps =
             connection.prepareStatement(sql)) {
        ps.setDate(1, Date.valueOf(newDate));
        ps.setDate(2, Date.valueOf(oldDate));
        ps.setLong(3, eventId);

        try (ResultSet rs = ps.executeQuery()) {
            return rs.next();
        }
    }
}
~~~

Return value semantics:

- `true`: the `UPDATE` matched a row and returned the updated record.
- `false`: no row matched; treat as stale `oldDate`, missing record, or insufficient permissions.
- `SQLException`: may indicate a missing partition, unique violation, FK failure, serialization failure, deadlock, or other error.

**Never arbitrarily change `oldDate` on retry.** If another user already updated the date, the application may need to report a conflict for user resolution.

### Transaction Ownership

A repository method should not commit or roll back on its own when transactions are managed by a service or framework. Multi-statement business operations must stay inside caller-controlled transaction boundaries.

## 52. Error Classification and Handling

| Scenario | Typical Signal | Recommended Handling |
| --- | --- | --- |
| Missing destination partition | Routing / partition constraint error | Create partition or reject/stage per policy |
| Direct `INSERT` out of bounds | Partition constraint violation | Fix write path to use parent or valid bounds |
| Composite PK collision at target | `23505` `unique_violation` | Check business identity and true conflict |
| Broken FK on key change | `23503` `foreign_key_violation` | Review references and `ON UPDATE` rules |
| Row movement concurrency | Possible `40001` `serialization_failure` | Roll back and retry full transaction when safe |
| Deadlock | `40P01` `deadlock_detected` | Roll back and retry with bounded attempts |
| Lock unavailable | `55P03` `lock_not_available` | Retry with backoff or return busy status |
| Unmatched `WHERE` | `UPDATE` affects 0 rows | Check stale state/`old_date` or not-found |
| Trigger error | `SQLException` from trigger | Inspect trigger, data, and business rules |

Never wrap every `SQLException` in an infinite retry loop. A unique violation is usually a real data conflict requiring handling, not a transient error that heals on retry.

For transaction retries, enforce max attempts, backoff, logging, and idempotency whenever external side effects exist outside PostgreSQL.

## 53. Common Mistakes

### 53.1. Thinking INSERT into Parent Stores Rows in a Parent Heap

The partitioned parent is logical; tuples route to child partitions.

### 53.2. Confusing Routing with Pruning

Routing picks the destination for writes; pruning narrows which partitions are read.

### 53.3. Thinking TO Bounds Are Inclusive

`FROM` is inclusive, `TO` is exclusive in `RANGE`.

### 53.4. Writing Directly to a Child Expecting Automatic Re-Routing to a Sibling

Direct child `INSERT`s do not re-route out-of-bounds rows across siblings.

### 53.5. Missing Next Month's Partition While Ingestion Continues

Without `DEFAULT`, inserts fail; with `DEFAULT`, data piles up outside intended monthly partitions.

### 53.6. Thinking DEFAULT Drains Automatically When a New Partition Appears

Adding a partition does not auto-migrate existing `DEFAULT` rows.

### 53.7. Thinking Partition-Key UPDATE Only Edits One Cell in the Same Heap

If the new key falls in another partition, PostgreSQL executes row movement.

### 53.8. Thinking Cross-Partition UPDATE Does Not Affect Triggers

Row movement triggers row-level `DELETE`/`INSERT` semantics, affecting audits and outboxes.

### 53.9. Thinking Row-Movement UPDATE Runs as Two Separate Transactions

It executes within the current atomic SQL transaction and never commits half-done.

### 53.10. Thinking UNIQUE(event_id) Can Be Declared on a Date-Partitioned Parent

Parent unique constraints must include all partition key columns per PostgreSQL rules.

### 53.11. Thinking PRIMARY KEY(event_date,event_id) Guarantees Global event_id Uniqueness

Different dates still allow repeating the same `event_id` under the composite key.

### 53.12. Using ON CONFLICT DO UPDATE to Move Conflicting Rows Across Partitions

Upsert has restrictions on moving conflicting rows across partitions; use a parent `UPDATE` when business logic calls for it.

### 53.13. Ignoring Row-Movement Concurrency

Another transaction moving a row can cause concurrent `UPDATE`/`DELETE`s to hit `40001` or affect 0 rows.

### 53.14. Retrying Only the Last Statement After 40001

Roll back and re-evaluate the entire transaction against fresh state.

### 53.15. Using ctid/tableoid as Long-Lived API Keys

They are physical storage metadata that change on moves or maintenance.

### 53.16. Moving Millions of Rows in One Huge Transaction

Causes WAL spikes, lock contention, replica lag, and `VACUUM` pressure; use batches and checkpoints.

### 53.17. Repeatedly Adding Days on Migration Retries

`SET event_date = event_date + 31` is non-idempotent; use explicit `old→new` mappings and checkpoints.

### 53.18. Partitioning on a Frequently Mutated Date Column

Creates heavy write amplification; prefer a more stable partition key.

### 53.19. Ignoring Timezones and Month Boundaries

One instant can fall into different months in UTC vs. local business time.

### 53.20. Thinking Indexes Solve Missing Partitions

Indexes accelerate intra-partition lookups; they never create routing destinations.

### 53.21. Not Monitoring DEFAULT

Silent `DEFAULT` growth hides broken provisioning and complicates maintenance.

### 53.22. Running EXPLAIN ANALYZE UPDATE on Production as a "Dry Run"

`ANALYZE` executes DML for real and modifies data.

### 53.23. Relying on BEFORE Triggers to Re-Route Partitions After Routing Starts

`BEFORE` triggers face limits when shifting rows to different partitions; set accurate partition keys before `INSERT`.

### 53.24. Overlooking Foreign Keys When Mutating a Composite PK

Changing `event_date` alters referenced keys in child tables, triggering constraint errors or cascades.

### 53.25. Thinking Partitioning Automatically Speeds Up Every Query

Queries omitting the partition key may scan many children, and indexes/plans still need tuning.

## 54. Practice Exercises with Answers

Exercises below build on `partition_lab` from Section 4. When running DML examples, wrap in `BEGIN ... ROLLBACK` to keep seed data clean. **Intentional-error** commands should be run alone or rolled back immediately.

### Exercise 1. Identifying the Partition for the First Day of a Month

**Question:** Does `event_date = 2026-02-01` route to Jan or Feb?

**Answer:** Feb. Jan's bound is `[2026-01-01,2026-02-01)`, which excludes `2026-02-01`.

### Exercise 2. Identifying the Partition for the Last Day of a Month

**Question:** Where does `2026-01-31` go?

**Answer:** `sales_events_2026_01`.

### Exercise 3. Inspecting tableoid

~~~sql
SELECT event_id, event_date,
       tableoid::regclass AS physical_partition
FROM partition_lab.sales_events
ORDER BY event_id;
~~~

**Answer:** 1001/1002 in Jan; 1003/1004 in Feb; 1005/1006 in Mar; 1007 in `DEFAULT`.

### Exercise 4. Inserting Multiple Months in One Statement

~~~sql
BEGIN;

INSERT INTO partition_lab.sales_events (
    event_date, event_id, tenant_id, amount
)
VALUES
    ('2026-01-10', 7001, 1, 10),
    ('2026-02-10', 7002, 1, 20),
    ('2026-03-10', 7003, 1, 30)
RETURNING event_id, tableoid::regclass;

ROLLBACK;
~~~

**Answer:** The three rows route to Jan, Feb, and Mar respectively.

### Exercise 5. Intra-Partition UPDATE

~~~sql
BEGIN;

UPDATE partition_lab.sales_events
SET status = 'paid'
WHERE event_date = DATE '2026-01-05'
  AND event_id = 1001
RETURNING tableoid::regclass;

ROLLBACK;
~~~

**Answer:** Stays in Jan because the date key did not change.

### Exercise 6. Updating the Key Within Jan

~~~sql
BEGIN;

UPDATE partition_lab.sales_events
SET event_date = DATE '2026-01-20'
WHERE event_date = DATE '2026-01-05'
  AND event_id = 1001
RETURNING event_date, tableoid::regclass;

ROLLBACK;
~~~

**Answer:** Remains in Jan because Jan 20 falls within Jan's bounds.

### Exercise 7. Updating to Move to Feb

~~~sql
BEGIN;

UPDATE partition_lab.sales_events
SET event_date = DATE '2026-02-20'
WHERE event_date = DATE '2026-01-05'
  AND event_id = 1001
RETURNING event_id, event_date, tableoid::regclass;

ROLLBACK;
~~~

**Answer:** Inside the transaction, row 1001 resides in Feb; after rollback it returns to Jan.

### Exercise 8. Updating Date to April

**Question:** If `event_id 1001` changes to `2026-04-10`, where does it go?

**Answer:** `sales_events_default`, because the lab defines only Jan–Mar and `DEFAULT`.

### Exercise 9. Missing DEFAULT

**Question:** `missing_destination_demo` has only Jan; does inserting Feb succeed?

**Answer:** No. With no matching partition, PostgreSQL raises a routing error.

### Exercise 10. Direct Child INSERT Out of Bounds

~~~sql
INSERT INTO partition_lab.sales_events_2026_02 (
    event_date, event_id, tenant_id, amount
)
VALUES ('2026-03-01', 7101, 1, 15.00);
~~~

**Answer:** Invalid because the row falls outside Feb's bounds. Writing via the parent lets PostgreSQL route it to Mar.

### Exercise 11. What Does the Composite Primary Key Forbid?

**Question:** Do `(2026-01-05,9001)` and `(2026-02-05,9001)` violate `PRIMARY KEY(event_date,event_id)`?

**Answer:** No, because the key pairs differ. Enforcing global `event_id` uniqueness requires a different design.

### Exercise 12. Can One UPDATE Target Multiple Destinations?

~~~sql
BEGIN;

UPDATE partition_lab.sales_events
SET event_date = event_date + 31
WHERE event_date >= DATE '2026-01-01'
  AND event_date < DATE '2026-02-01'
RETURNING event_id, event_date, tableoid::regclass;

ROLLBACK;
~~~

**Answer:** Yes. On the seed data, 1001 moves to Feb while 1002 moves to Mar.

### Exercise 13. ON CONFLICT with Composite Key

**Question:** Does inserting `(2026-02-05,1001)` conflict with `(2026-01-05,1001)`?

**Answer:** No, because the partition key `event_date` is part of the composite PK.

### Exercise 14. Moving Partitions via ON CONFLICT DO UPDATE?

**Answer:** Do not use `ON CONFLICT DO UPDATE` to move a conflicting row's partition key to another partition; use `UPDATE` via the parent per supported mechanics.

### Exercise 15. What Do AFTER ROW Triggers Observe?

**Question:** Updating a row Jan → Feb logs which entries in an `AFTER INSERT/DELETE` audit trigger?

**Answer:** One row `DELETE` on source Jan and one row `INSERT` on destination Feb per row-movement mechanics—which is why both entries must not be treated blindly as two independent business actions.

### Exercise 16. Why Is WHERE old_date Important?

**Answer:** Filtering `event_date = old_date AND event_id = ...` detects concurrent state shifts. If another transaction already moved the row, `UPDATE` affects 0 rows or hits a concurrency error so the application reacts rather than guessing.

### Exercise 17. SQLSTATE on Concurrent Row Movement

**Question:** What does error `40001` require?

**Answer:** Roll back and retry **the entire transaction** when safe, re-reading the partition key and business preconditions rather than blindly repeating the stale `UPDATE`.

### Exercise 18. Why Not Update Millions of Rows in One Transaction?

**Answer:** Row movement triggers `DELETE+INSERT`, generating locks, WAL, index updates, FK checks, triggers, long transactions, bloat, and replica lag. Use batching, checkpoints, and monitoring.

### Exercise 19. Why Monitor DEFAULT?

**Answer:** If rows pile up in `DEFAULT` due to missing partitions, adding explicit partitions later becomes harder and queries/maintenance degrade. `DEFAULT` never auto-repartitions old rows.

### Exercise 20. Filtering Feb for Effective Pruning

~~~sql
SELECT *
FROM partition_lab.sales_events
WHERE event_date >= DATE '2026-02-01'
  AND event_date < DATE '2026-03-01';
~~~

**Answer:** Direct range predicates on the partition key let the planner/executor skip unneeded children easily.

### Exercise 21. Can Indexes Replace Partition Routing?

**Answer:** No. Indexes locate/maintain rows within a partition; routing picks the destination partition from bounds.

### Exercise 22. When to Use a Registry Table?

**Answer:** When `event_id` must be globally unique despite `event_date` range partitioning where the composite PK enforces only per-pair uniqueness. The registry uses its own unique PK and must share transactions/protocols consistently.

### Exercise 23. Is Partition Movement Two Independent Transactions?

**Answer:** No. A row-moving `UPDATE` runs inside the current SQL transaction with full atomicity for database changes.

### Exercise 24. How Do Timezones Affect Timestamp Partitioning?

**Answer:** One UTC instant can fall on a different local calendar day or month. Define business timezone rules, `timestamptz` types, and explicit bounds before designing.

### Exercise 25. Distinguishing LIST/HASH/RANGE

**Answer:** `RANGE` routes by intervals, `LIST` by enumerated values, and `HASH` by key hash. All three perform partition routing; `DEFAULT` applies to `RANGE`/`LIST` per rules, not `HASH`.

### Exercise 26. Should tableoid Be Used as a Public ID?

**Answer:** No. `tableoid` is physical relation metadata that changes on row movement or maintenance; business IDs require stable identifiers.

## 55. Production Readiness Checklist

1. **Choose the partition key** based on queries, retention, and value stability.
2. **Define exact bounds**, especially exclusive upper endpoints and timezones.
3. **Provision future partitions ahead of time** to prevent unexpected write errors.
4. **Decide explicitly on `DEFAULT`** and alert whenever `DEFAULT` receives rows.
5. **Use the parent as the main write target**, avoiding hardcoded child names in APIs.
6. **Test routing on start/end boundary dates** of each partition, including leap days and timezone boundaries.
7. **Test multi-row `INSERT`s** spanning multiple partitions.
8. **Test both intra-partition and cross-partition `UPDATE`s**.
9. **Verify targets with `RETURNING`/`tableoid`** in lab tests.
10. **Check parent uniqueness constraints:** partition key columns must be included in `PK`/`UNIQUE` per rules.
11. **Design global business IDs** if date-based composite PKs are insufficient.
12. **Do not rely on `ON CONFLICT DO UPDATE`** to move conflicting rows across partitions.
13. **Test row triggers** to avoid unintended business side effects.
14. **Evaluate `FK`/`ON UPDATE`** impacts when the partition key is part of a referenced key.
15. **Test concurrency** and handle `40001` via full transaction retries.
16. **Batch large date corrections** instead of massive single transactions.
17. **Avoid non-idempotent date shifts** when migrations may retry.
18. **Measure WAL, index, lock, vacuum, and replica lag** for heavy row movement.
19. **Verify query pruning** with direct predicates on the partition key.
20. **Schedule `CREATE`/`ATTACH`/`DETACH` partitions** accounting for locks and `DEFAULT` data.
21. **Monitor per-child metrics:** row counts, dead tuples, statistics, and index sizes.
22. **Ensure JDBC/ORMs bind typed dates** with clear transaction boundaries.
23. **Never use `tableoid`/`ctid`/`xmin` as durable business keys**.
24. **Maintain runbooks** for missing partitions, routing errors, unique conflicts, `40001`, and `DEFAULT` drainage.
25. **Check CDC/replication behavior** if consumers distinguish `DELETE+INSERT` from `UPDATE`.

## 56. Official PostgreSQL Documentation

When implementing, consult documentation for your **exact running PostgreSQL major version**, as declarative partitioning and row movement have evolved across releases:

- [Table Partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html) — declarative partitioning, bounds, routing, pruning, and limits.
- [INSERT](https://www.postgresql.org/docs/current/sql-insert.html) — `INSERT` into partitioned tables, `RETURNING`, and `ON CONFLICT`.
- [UPDATE](https://www.postgresql.org/docs/current/sql-update.html) — `UPDATE` modifying partition keys, row movement, and concurrency.
- [CREATE TABLE](https://www.postgresql.org/docs/current/sql-createtable.html) — `PARTITION BY`, `PARTITION OF`, `DEFAULT`, `FROM`/`TO`, and constraints.
- [ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html) — `ATTACH`/`DETACH PARTITION` and DDL effects.
- [Triggers](https://www.postgresql.org/docs/current/trigger-definition.html) — trigger execution, cross-partition behavior, and trigger levels.
- [Partitioning and Constraint Limitations](https://www.postgresql.org/docs/current/ddl-partitioning.html#DDL-PARTITIONING-DECLARATIVE-LIMITATIONS) — `PK`/`UNIQUE` restrictions and partitioned index traits.
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html) — snapshots, concurrency, and serialization errors.
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html) — row/table locks and deadlocks.
- [EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html) — reading plans and remembering `ANALYZE` executes DML.
- [System Columns](https://www.postgresql.org/docs/current/ddl-system-columns.html) — `tableoid`/`ctid`/`xmin`.
- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html) — reclaiming tuples after `UPDATE`/`DELETE`.
- [Error Codes](https://www.postgresql.org/docs/current/errcodes-appendix.html) — `23505`, `23503`, `40001`, and other errors to classify.

`/current/` points to the latest release; for any specific production server, check the docs matching your **exact version** before relying on a feature or restriction in migrations.

## 57. Summary

`INSERT` routing and partition-key-changing `UPDATE`s are foundational mechanics of PostgreSQL declarative partitioning.

Most important takeaways:

1. **Parent `INSERT`s route per row by partition key value.** `RANGE` bounds are inclusive lower and exclusive upper; `DEFAULT` catches only values matching no explicit partition.
2. **Without a matching partition, writes fail.** With `DEFAULT`, rows land in `DEFAULT`, yet never auto-migrate when new partition DDL is added later.
3. **Updating the key within the same bounds keeps the row in place.** If the new value maps to another child, PostgreSQL performs **row movement**, executing source `DELETE` plus destination `INSERT` inside the same transaction.
4. **Row movement carries real operational impact** on row triggers, constraints, indexes, WAL, vacuum, replication, and concurrency. Never mistake it for a trivial metadata edit.
5. **Parent `PK`/`UNIQUE` constraints are bound by the partition key.** Date-based composite PKs do not ensure global `event_id` uniqueness across partitions.
6. **`ON CONFLICT DO UPDATE` is not a general way to move conflicting rows across partitions.** Use `UPDATE` via the parent when business rules call for moving partitions.
7. **Concurrent `UPDATE`/`DELETE` plus row movement can raise `40001`.** Roll back and retry the whole transaction when safe, re-checking source dates and entity identity.
8. **Partitioning is not free.** Pick a stable key, pre-create future bounds, monitor `DEFAULT`, batch large moves, and measure the impact of bulk row movement.

Understanding exactly how PostgreSQL **routes rows on `INSERT` and relocates them when `UPDATE` changes the partition key** lets you design partitioned schemas that preserve data integrity, avoid elusive concurrency bugs, and manage time-series data cleanly.
