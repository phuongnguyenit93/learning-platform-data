# ctid, tableoid, and the Limits of Physical Identifiers in PostgreSQL

When querying a PostgreSQL table, in addition to application-defined columns, you can read several **system columns** provided by PostgreSQL. The two columns that most commonly cause confusion are:

- **ctid**: the physical location of a row version (tuple version) inside a table.
- **tableoid**: the OID of the physical table storing that row.

They are useful for storage investigations, identifying which partition a row comes from, or processing a batch of rows within a single SQL statement. However, they are **not durable business identifiers** like a primary key.

A row can be UPDATED and produce a new tuple version with a different ctid. A table can be rewritten by VACUUM FULL or CLUSTER, changing physical locations. When querying a partitioned table or inheritance parent, ctid is only meaningful within each child table; it must be combined with tableoid to distinguish the source relation.

~~~mermaid
flowchart TD
    R["A PostgreSQL row"] --> V["MVCC tuple version"]
    V --> C["ctid = (block, offset)"]
    V --> T["tableoid = physical table OID"]
    C --> L["Temporary physical location"]
    T --> P["Identifies the relation holding the row"]
    L --> N["Can change after UPDATE / rewrite"]
    P --> J["Combine tableoid + ctid when a locator is needed"]
    J --> U["Does not replace a business key"]
~~~

This lesson belongs to the **Storage** chapter, module **Database Engine Relational PostgreSQL**. We will cover tuple structure, MVCC, operations that change ctid, how tableoid behaves with partitions, use cases for locators within a single statement, and why they must not be stored as long-term keys.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain ctid as a physical tuple identifier of type tid.
2. Read ctid as a pair of block number and item/offset number.
3. Explain tableoid and how casting to regclass reveals the relation name.
4. Distinguish a physical locator from a primary key/business key.
5. Understand why UPDATE creates a new tuple version and usually changes ctid.
6. Understand that HOT updates still create a new tuple version, even though index entries may not need updating.
7. Distinguish the impact of regular VACUUM from VACUUM FULL/CLUSTER and rewrite operations.
8. Use tableoid to identify the partition or inheritance child containing a row.
9. Combine tableoid and ctid when a locator must distinguish among multiple physical tables.
10. Use ctid for batch maintenance within a single statement when appropriate.
11. Understand concurrency limits, row locks, MVCC snapshots, and partition row movement.
12. Avoid using ctid as a primary key, foreign key, pagination token, replication key, or long-term bookmark.
13. Know that related system columns such as xmin and xmax are also not stable audit fields.
14. Inspect data and catalogs without relying on fixed physical values.
15. Choose logical keys and design appropriate indexes for business queries.

## 2. What Are System Columns?

PostgreSQL stores additional metadata for each tuple. Some of this metadata can be accessed via system column names:

| System column | Data type | Meaning |
| --- | --- | --- |
| **tableoid** | oid | OID of the relation containing the tuple |
| **ctid** | tid | Physical location of the tuple version within the relation |
| **xmin** | xid | Transaction ID associated with inserting the tuple version |
| **xmax** | xid | Transaction ID associated with delete/update or certain tuple locking states |
| **cmin** | cid | Command ID associated with insert within a transaction |
| **cmax** | cid | Command ID associated with delete/update within a transaction |

These columns are managed by PostgreSQL, not declared by you in CREATE TABLE.

### Not Included in SELECT *

For example:

~~~sql
SELECT *
FROM public.orders;
~~~

normally returns only the columns defined in the table, **without automatically adding system columns**. To read them, you must name them explicitly:

~~~sql
SELECT
    order_id,
    status,
    tableoid,
    ctid,
    xmin,
    xmax
FROM public.orders;
~~~

You can also use a table alias:

~~~sql
SELECT
    o.order_id,
    o.tableoid,
    o.ctid
FROM public.orders AS o;
~~~

System columns are tools for observing storage/MVCC. Do not treat them as ordinary business fields to serialize into APIs.

## 3. What Is ctid?

ctid has the PostgreSQL type tid, representing the tuple's position within a relation as a pair:

~~~text
(block_number, item_offset)
~~~

For example, a value looks like:

~~~text
(12,7)
~~~

This means:

- 12: block/page number in the relation.
- 7: item identifier/offset number of the line pointer on that page.

A page typically has the size configured for PostgreSQL (usually 8 KiB, though it can differ by build). A block contains the page header, line pointers, and tuple data; the item offset identifies a line pointer on the page.

**ctid is not a row sequence number** and does not mean "the 7th row of the table on page 12" in SQL order.

### Example of Inspecting ctid

~~~sql
SELECT
    order_id,
    status,
    ctid
FROM public.orders
ORDER BY order_id
LIMIT 20;
~~~

Illustrative output:

| order_id | status | ctid |
| ---: | --- | --- |
| 101 | new | (0,1) |
| 102 | paid | (0,3) |
| 103 | new | (1,2) |

These values only illustrate the format. **There is no rule that smaller order_id must have smaller ctid**, nor that ctids are contiguous without gaps.

### ctid Belongs to a Tuple Version

PostgreSQL uses MVCC. A logical row can have multiple tuple versions due to UPDATEs. ctid only identifies the location of **a specific physical version**, not the permanent identity of the logical row.

## 4. What Is tableoid?

tableoid is the OID of the relation containing the tuple. For a regular table, every row read from that table has the same tableoid.

Example:

~~~sql
SELECT
    tableoid,
    tableoid::regclass AS physical_table,
    ctid,
    order_id
FROM public.orders
ORDER BY order_id;
~~~

- tableoid returns the OID value.
- tableoid::regclass casts the OID to a human-readable relation name.
- ctid shows the tuple's position within that relation.

### OID Is Not a Business ID

An OID helps PostgreSQL reference an object in the catalog at the current time. It is not a durable table code across all lifecycles:

- DROP followed by CREATE recreates the relation as a new object.
- Dump/restore creates new objects in the target cluster; do not use old OIDs as external identifiers.
- OIDs are a bounded identifier space and not a long-term storage contract.
- Renaming a relation does not necessarily change its OID, though its displayed name changes.

Therefore, tableoid is useful for **identifying which relation holds the row in the current database**, not as a global table ID to persist in business events forever.

## 5. How Do ctid and tableoid Relate?

Within a single table, ctid is usually sufficient to locate a tuple version inside that relation at a suitable point in time.

However, when querying multiple relations through inheritance or a partitioned table, multiple tables can simultaneously have a tuple with a ctid such as (0,1). ctid is not unique across tables.

Therefore, when you need a locator over results that may span multiple relations:

~~~sql
SELECT
    tableoid::regclass AS source_table,
    ctid,
    order_id
FROM public.orders_parent;
~~~

The pair **(tableoid, ctid)** can be treated as a physical locator to distinguish tuples across multiple relations at query time.

### This Pair Is Still Not a Durable Key

- ctid can change when the tuple is UPDATED or the relation is rewritten.
- tableoid can change when a relation is dropped/recreated, altered structurally, or data is moved to another relation.
- Another transaction can change physical state after the locator was captured.
- Restoring to another cluster does not guarantee OIDs are preserved.

**(tableoid, ctid) is a short-lived physical locator, not a composite primary key.**

## 6. Why Does PostgreSQL Need ctid?

PostgreSQL stores table data in heap pages. Indexes need to reference tuple locations in the heap to find the corresponding row version. TID/ctid is part of that physical addressing mechanism.

A conceptual view:

~~~text
B-tree index entry
       |
       v
Heap TID (block, offset)
       |
       v
Heap page
       |
       v
Line pointer
       |
       v
Tuple version
~~~

This is a conceptual model. PostgreSQL also performs MVCC visibility checks, manages HOT chains, page pruning, and many other internal details. An index entry pointing to a heap location does not mean the tuple is necessarily visible to every transaction.

### Why Do SQL Users See ctid?

It is useful in several technical tasks:

- Tuple/version investigation.
- Diagnosing page/heap behavior.
- Selecting a physical group of rows for single-statement maintenance.
- Distinguishing rows coming from child relations.
- Checking certain duplicate-data issues lacking logical keys.

However, the fact that PostgreSQL exposes this column **does not turn it into a durable identification API for applications**.

## 7. MVCC: UPDATE Does Not Simply Overwrite the Old Tuple In Place

PostgreSQL uses Multi-Version Concurrency Control (MVCC). When a transaction UPDATES a row, the system typically creates a new tuple version and marks the old version as no longer visible to qualifying snapshots.

Simplified model:

~~~text
Before UPDATE:
  ctid=(4,2) -> tuple version A, status='new'

After UPDATE:
  ctid=(4,2) -> tuple version A (old version)
  ctid=(4,5) -> tuple version B (new version, status='paid')
~~~

Different transactions may see different versions depending on snapshot/visibility rules.

### Observing ctid Before and After UPDATE

Use the lab table from later in this lesson or your own test table:

~~~sql
BEGIN;

SELECT order_id, status, ctid
FROM jdbc_storage_lab.orders
WHERE order_id = 1;

UPDATE jdbc_storage_lab.orders
SET status = 'paid'
WHERE order_id = 1
RETURNING order_id, status, ctid;

ROLLBACK;
~~~

Inside the transaction, RETURNING ctid reports the location of the new tuple version created for the row after UPDATE. Exact values depend on the physical state of the table; never hard-code example values.

After ROLLBACK, the change is undone and the new version does not become committed data. This example only illustrates the lifecycle, not a test expecting ctid to increment by an arithmetic rule.

## 8. HOT Updates Still Create a New Tuple Version

**HOT (Heap-Only Tuple) update** is a PostgreSQL optimization when conditions allow, such as when updated columns do not require modifying index entries and the page still has enough space per HOT rules.

HOT can avoid adding new index entries for the new version by maintaining a chain within the same page.

However:

- HOT still creates a new tuple version.
- The new version's ctid can still differ from the old version.
- Being on the same page does not mean ctid stays unchanged, because the item offset can differ.
- HOT eligibility depends on schema/indexes, which columns change, and page free space; it cannot be forced merely by writing SQL UPDATE.

**Do not use ctid to detect "whether a row changed" as an audit mechanism.** Use a dedicated business version/timestamp column or explicitly designed audit logic.

## 9. UPDATE Can Change ctid Even When Updating Only One Column

Example:

~~~sql
UPDATE jdbc_storage_lab.orders
SET status = 'paid'
WHERE order_id = 1;
~~~

Even when changing only status, PostgreSQL still performs MVCC tuple versioning. There is no guarantee ctid remains unchanged.

Another case:

~~~sql
UPDATE jdbc_storage_lab.orders
SET status = status
WHERE order_id = 1;
~~~

An UPDATE can still create a new tuple version even when visible values do not change, unless the statement/trigger/condition is written to skip the operation. Do not rely on "identical values" to assume ctid will remain stable.

If you want to avoid no-op updates, you can write:

~~~sql
UPDATE jdbc_storage_lab.orders
SET status = 'paid'
WHERE order_id = 1
  AND status IS DISTINCT FROM 'paid';
~~~

This is an optimization based on data semantics. It does not turn ctid into a stable identifier.

## 10. Regular VACUUM and VACUUM FULL Differ

Two commands share the word VACUUM, yet their physical effects differ greatly:

| Command | Purpose | Physical impact to understand |
| --- | --- | --- |
| VACUUM table | Reclaim/reuse space from dead tuples and update the visibility map | Usually does not rewrite the entire heap to compact live rows |
| VACUUM (ANALYZE) table | Vacuum and update statistics | Not equivalent to rewriting the table |
| VACUUM FULL table | Compact the relation by rewriting | Creates a new relation copy and changes tuple locations |
| CLUSTER table USING index | Rewrite the table in index order | Can change the ctid of rows |
| Some ALTER TABLEs requiring rewrite | Convert structure/data types | Can create a new physical layout |

### Do Not Overstate Regular VACUUM

Regular VACUUM primarily marks/reclaims dead tuple regions for reuse and updates metadata; it is not like VACUUM FULL compaction. Do not claim that every regular VACUUM run changes the ctid of all live rows.

Yet the design conclusion remains: **ctid has no long-term stability guarantee**. UPDATEs, table rewrites, and other storage operations are enough to invalidate old locators.

### VACUUM FULL Requires a Strong Lock

VACUUM FULL rewrites the relation and takes a strong lock, potentially blocking concurrent access for its duration. It is not a "periodic cleanup" button to run casually on large tables.

## 11. CLUSTER and Rewrite Operations

CLUSTER reorganizes a table according to a specified index by rewriting the relation. Afterward, physical tuples may reside at new block/offset locations.

~~~sql
-- Syntax example; run only on the lab table after creating a suitable index.
CLUSTER jdbc_storage_lab.orders
USING idx_orders_customer;
~~~

An index named idx_orders_customer must actually exist. CLUSTER carries I/O and lock costs and does not automatically maintain physical order across subsequent writes.

Certain DDL changes can rewrite a table, depending on PostgreSQL version and the type of ALTER. Check the ALTER TABLE documentation and your specific deployment plan.

### What Must Never Be Assumed?

Do not save ctid today and rely on it tomorrow after a migration/rewrite. Do not treat ctid as a synchronization key with external systems. Do not expose it in URLs/APIs.

## 12. tableoid in Partitioned Tables

Suppose an orders table is partitioned by month:

~~~sql
CREATE TABLE jdbc_storage_lab.partitioned_orders (
    order_id bigint NOT NULL,
    created_at date NOT NULL,
    amount numeric(12,2) NOT NULL,
    PRIMARY KEY (order_id, created_at)
) PARTITION BY RANGE (created_at);

CREATE TABLE jdbc_storage_lab.orders_2026_01
PARTITION OF jdbc_storage_lab.partitioned_orders
FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');

CREATE TABLE jdbc_storage_lab.orders_2026_02
PARTITION OF jdbc_storage_lab.partitioned_orders
FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');
~~~

Insert through the parent:

~~~sql
INSERT INTO jdbc_storage_lab.partitioned_orders (
    order_id, created_at, amount
)
VALUES
    (1, DATE '2026-01-10', 100.00),
    (2, DATE '2026-02-15', 200.00);
~~~

Query:

~~~sql
SELECT
    order_id,
    created_at,
    tableoid::regclass AS physical_partition,
    ctid
FROM jdbc_storage_lab.partitioned_orders
ORDER BY order_id;
~~~

Results show:

- The January row resides in orders_2026_01.
- The February row resides in orders_2026_02.
- tableoid::regclass reveals the actual physical partition storing the row.
- ctid is only the location within that partition.

### The Parent Partitioned Table Does Not Store These Rows

A partitioned table is a routing parent relation; rows are stored in child partitions. Querying the parent normally reads the relevant partitions. The tableoid system column on the result identifies the child relation that stored the tuple.

If you only SELECT ctid from the parent, different partitions can share the same ctid. To distinguish physical locators, select tableoid as well.

## 13. tableoid in Inheritance Tables

PostgreSQL also supports table inheritance:

~~~sql
CREATE TABLE jdbc_storage_lab.assets (
    asset_id bigint,
    description text
);

CREATE TABLE jdbc_storage_lab.vehicles (
    max_speed integer
) INHERITS (jdbc_storage_lab.assets);
~~~

Query the parent:

~~~sql
SELECT
    tableoid::regclass AS source_relation,
    ctid,
    asset_id,
    description
FROM jdbc_storage_lab.assets;
~~~

By default, querying the parent can include rows from child tables per inheritance semantics. tableoid indicates whether a row actually lives in the parent or a child.

Use ONLY to query solely that relation itself:

~~~sql
SELECT tableoid::regclass, ctid, asset_id
FROM ONLY jdbc_storage_lab.assets;
~~~

### Partitioning and Inheritance Are Not Identical

Partitioning defines partition keys, routing, constraints, and partition pruning rules. Inheritance is a more general parent-child mechanism. In both cases, tableoid helps identify the physical relation holding a row, but do not infer all partitioning semantics from inheritance.

## 14. Why Is ctid Not Unique Across Partitions?

Each heap relation has its own page/block numbering. Thus:

~~~text
orders_2026_01: ctid = (0,1)
orders_2026_02: ctid = (0,1)
~~~

is entirely possible.

If a parent query returns both rows and only ctid is kept, the locator does not uniquely identify which relation holds the tuple.

The pair:

~~~sql
SELECT tableoid, ctid
FROM jdbc_storage_lab.partitioned_orders;
~~~

distinguishes them.

For human-readable output:

~~~sql
SELECT
    tableoid::regclass AS relation_name,
    ctid,
    order_id
FROM jdbc_storage_lab.partitioned_orders;
~~~

**Even this pair is only a physical locator in the current state**, not a business key.

## 15. Updating a Partition Key Can Move a Row to Another Partition

An UPDATE changing the partition key can cause PostgreSQL to move the row from the old partition to the new partition:

~~~sql
UPDATE jdbc_storage_lab.partitioned_orders
SET created_at = DATE '2026-02-20'
WHERE order_id = 1
  AND created_at = DATE '2026-01-10';
~~~

If the target partition exists and accepts the new value, the row can be moved. Consequences:

- The physical relation changes.
- tableoid changes.
- ctid in the new partition is no longer the old locator.
- Index/constraint and trigger behaviors during partition movement must be understood for your PostgreSQL version.

In concurrent workloads, updating a row being moved between partitions by another transaction can trigger serialization errors in cases documented by PostgreSQL. Never use an old locator to continue operating after partition movement.

## 16. Using ctid to Inspect a Physical Row

If a query returned tableoid/ctid and you want to inspect it immediately within a suitable transaction, you can use the locator under very strict conditions.

Example on a single table:

~~~sql
BEGIN;

SELECT order_id, ctid
FROM jdbc_storage_lab.orders
WHERE order_id = 1;

-- Illustrates comparison form only; do not hard-code ctids from examples.
-- Use the value just observed within the same appropriate context.

ROLLBACK;
~~~

Do not build an API that accepts a client-supplied ctid and updates the corresponding row. A client could send a stale locator, another row's locator, or a locator that is no longer visible.

### Do Not Store ctid in Reference Tables

Anti-pattern:

~~~sql
CREATE TABLE app.pending_work (
    source_ctid tid NOT NULL
);
~~~

and then using source_ctid to look up rows across multiple transactions. UPDATE/rewrite/partition movement can invalidate the reference or point to a different tuple once the slot is reused.

Store the **primary key/business key**, and if version control is needed, store a version column or optimistic locking condition.

## 17. Using ctid Within a Single Statement to Delete Duplicates

A familiar technical use case is a legacy table containing duplicates without a primary key. You can target specific physical tuples for deletion in a single statement.

Illustrative example with a contacts table:

~~~sql
WITH ranked AS (
    SELECT
        ctid,
        row_number() OVER (
            PARTITION BY email
            ORDER BY created_at, ctid
        ) AS rn
    FROM jdbc_storage_lab.contacts
)
DELETE FROM jdbc_storage_lab.contacts AS c
USING ranked AS r
WHERE c.ctid = r.ctid
  AND r.rn > 1;
~~~

**The snippet above only runs if the jdbc_storage_lab.contacts table with email/created_at columns has been created.** It is a technique example, not part of the initial lab schema.

### Important Notes

- ctid is fetched and consumed within the exact same statement.
- For a single table, ctid distinguishes tuples within that relation.
- If the query spans multiple partitions/inherited relations, carry tableoid and join on both.
- ORDER BY created_at, ctid selects the survivor by technical tie-breaking; if business rules require keeping the newest/verified record, use business criteria.
- Back up and preview duplicates before running DELETE.
- Run inside a transaction, review affected row counts, and keep a rollback plan.

Do not delete duplicates solely by ctid without determining which row is the canonical record.

## 18. Using ctid + tableoid for Batch Maintenance

Some maintenance jobs need to grab a batch of rows, lock them, and update/delete them in the same statement. With partitioned tables, you can combine tableoid and ctid.

Conceptual example processing 500 pending events:

~~~sql
WITH batch AS (
    SELECT
        tableoid,
        ctid
    FROM jdbc_storage_lab.partitioned_events
    WHERE processed_at IS NULL
    ORDER BY event_id
    FOR UPDATE SKIP LOCKED
    LIMIT 500
)
UPDATE jdbc_storage_lab.partitioned_events AS e
SET processed_at = clock_timestamp()
FROM batch AS b
WHERE e.tableoid = b.tableoid
  AND e.ctid = b.ctid
RETURNING e.event_id, e.tableoid::regclass;
~~~

This snippet requires a partitioned table partitioned_events with matching columns; it illustrates a pattern, not a command runnable directly on the current lab schema.

### Why Use FOR UPDATE SKIP LOCKED?

- FOR UPDATE locks the selected rows within the transaction.
- SKIP LOCKED skips rows already locked by other transactions, useful for some worker queues.
- The CTE retains the locators of the selected tuples.
- The UPDATE in the same statement uses the locators to target the exact locked rows.

### Why Not Save ctid for the Next Run?

The current transaction locks and processes the same group of rows. After COMMIT, the locator must not be treated as a durable token. The next run must re-query using business conditions such as processed_at IS NULL.

### Do Not Replace Business ORDER BY with ctid

ORDER BY event_id defines priority by business key. ctid does not represent chronological order or processing priority. Only use ctid as a locator after selecting rows via meaningful conditions.

## 19. Batch DELETE with ctid

A single-statement pattern:

~~~sql
WITH batch AS (
    SELECT
        tableoid,
        ctid
    FROM jdbc_storage_lab.partitioned_events
    WHERE expires_at < current_date
    ORDER BY expires_at, event_id
    FOR UPDATE SKIP LOCKED
    LIMIT 500
)
DELETE FROM jdbc_storage_lab.partitioned_events AS e
USING batch AS b
WHERE e.tableoid = b.tableoid
  AND e.ctid = b.ctid
RETURNING e.event_id;
~~~

This pattern:

- Selects a batch of rows by business condition.
- Locks rows so other workers do not normally process them simultaneously.
- Deletes within the same statement/transaction.
- Returns logical IDs for logging/checkpointing.

**Never record ctid to execute DELETE in tomorrow's job.** If resumption is needed, record business keys or a checkpoint.

## 20. Concurrency: Why Same-Statement Execution Matters

Suppose:

1. Transaction A SELECTs the ctid of row 100.
2. A COMMITs.
3. Transaction B UPDATEs row 100, creating a new tuple version.
4. Transaction A reuses the old ctid in another transaction.

The locator A kept may now point to an old non-visible version or a physical slot reused over time. It is no longer a reliable logical identifier.

A safer pattern for batch maintenance is **select, lock, and modify in the same statement/transaction**, such as the FOR UPDATE SKIP LOCKED CTE above.

### MVCC and Locking

- ctid does not replace row locks.
- ctid does not prevent lost updates.
- ctid does not replace optimistic version checks.
- SKIP LOCKED has semantics that skip locked rows; the result is not a full snapshot of every qualifying row.
- Isolation level still affects how transactions see and handle concurrent changes.

## 21. Optimistic Locking Should Use a Version Column

If an application needs to detect whether a row was modified since it was read, add a version column:

~~~sql
ALTER TABLE jdbc_storage_lab.orders
ADD COLUMN version bigint NOT NULL DEFAULT 1;
~~~

Update:

~~~sql
UPDATE jdbc_storage_lab.orders
SET
    status = 'paid',
    version = version + 1
WHERE order_id = 1
  AND version = 3
RETURNING order_id, status, version;
~~~

If no row is returned, either the version changed or the row no longer exists; the application must handle the conflict per business contract.

### Why Is This Better Than ctid?

- Version is an explicitly designed logical field.
- It can be passed across APIs/checkpoints by contract.
- It does not depend on physical pages/offsets.
- It works alongside the primary key to detect concurrent modification.

Do not use ctid as a version counter. ctid has a physical format and no guarantee of sequential increase.

## 22. Pagination Using ctid Is an Unreliable Design

An anti-pattern:

~~~sql
SELECT order_id, ctid
FROM jdbc_storage_lab.orders
WHERE ctid > '(10,1)'::tid
ORDER BY ctid
LIMIT 100;
~~~

And then the next page stores the last ctid and uses it as a long-term cursor token.

Problems:

- UPDATEs give new tuple versions different ctids.
- Rows can be moved/rewritten.
- Physical order is not business order.
- Concurrent updates can shift a row's physical location.
- Partitioned tables require tableoid to disambiguate.
- VACUUM/rewrites and storage activity make physical locators unsuitable for durable bookmarks.

### Use Keyset Pagination on Logical Keys

~~~sql
SELECT order_id, status
FROM jdbc_storage_lab.orders
WHERE order_id > ?
ORDER BY order_id
LIMIT ?;
~~~

The order_id key is designed for pagination; it has indexes/constraints and far more stable semantics than ctid.

## 23. Can ctid Be Used Instead of a Primary Key?

**No.**

A primary key must be:

- Unique according to data rules.
- NOT NULL.
- Stable across the business lifecycle.
- Referenceable by foreign keys.
- Usable in APIs, events, replication, and application code.
- Backed by system-wide agreed semantics.

ctid:

- Is the physical location of a tuple version.
- Can change on UPDATE.
- Can change after rewrites.
- Has no business meaning.
- Is unsuitable for foreign keys.
- Is not guaranteed stable across restore/migration.

### What If a Table Lacks a Primary Key?

Identify a valid natural/business key or create a surrogate key (identity/UUID) by design. Do not choose ctid simply because it "looks unique right now."

## 24. ctid Is Not a Replication Identity

Logical replication needs to identify source rows to propagate UPDATE/DELETE via replica identity. Usually a primary key or suitable unique index is used.

If a table lacks a suitable key, PostgreSQL offers REPLICA IDENTITY FULL to use the entire row image with its associated limits/costs.

**ctid is not a durable replica identity for syncing between two databases.** A physical TID on the publisher has no equivalent meaning on the subscriber, because the two heap layouts are independent.

If logical replication is required, design a primary/unique key and replica identity matching your workload requirements.

## 25. System Columns xmin and xmax Are Not Audit Fields Either

xmin/xmax are often inspected when learning MVCC:

- xmin relates to the transaction creating the tuple version.
- xmax relates to the transaction deleting/updating the tuple or locking/transaction metadata under internal semantics.

However, do not interpret them naively as:

~~~text
xmin = who created the row
xmax = who deleted the row
~~~

Because:

- A transaction ID is not an actor/user ID.
- XIDs have lifecycle/wraparound and internal representations.
- xmax can reflect locking metadata, not simply that the row was deleted.
- Freezing and visibility rules complicate interpreting raw XIDs.
- They are not timestamps.
- They do not replace an audit log.

### Want to Know Who Modified What and When?

Add intentional business metadata such as created_at, updated_at, created_by, updated_by, or an audit table/CDC. These fields also require clear trust boundaries; do not blindly trust client-supplied actor IDs as verified evidence.

## 26. Be Careful Joining Two Tables by ctid

Wrong:

~~~sql
SELECT *
FROM orders AS o
JOIN payments AS p
  ON o.ctid = p.ctid;
~~~

Two tables can both have a ctid such as (0,1); that does not mean they are the same row or business-related.

Right:

~~~sql
SELECT *
FROM orders AS o
JOIN payments AS p
  ON o.order_id = p.order_id;
~~~

If genuinely handling physical locators from multiple relations, retain both tableoid and ctid in context, while business joins must always rely on foreign keys/logical keys.

## 27. Finding Relation Names from tableoid

A useful query:

~~~sql
SELECT
    tableoid,
    tableoid::regclass AS relation_name,
    count(*) AS row_count
FROM jdbc_storage_lab.partitioned_orders
GROUP BY tableoid
ORDER BY relation_name;
~~~

The output shows row counts per physical relation.

### Why Is regclass Convenient?

regclass is an OID alias type for relations. Casting makes PostgreSQL format the relation name according to search_path/schema qualification rules.

If logging/diagnostics are needed, you can use:

~~~sql
SELECT
    tableoid::regclass::text AS relation_name,
    ctid,
    order_id
FROM jdbc_storage_lab.partitioned_orders;
~~~

Displayed names can still change if a relation is renamed. For long-term history, record schema/object migration metadata separately.

## 28. ctid and ORDER BY

You can write:

~~~sql
SELECT ctid, order_id
FROM jdbc_storage_lab.orders
ORDER BY ctid;
~~~

PostgreSQL can sort by tid values. However:

- This is physical locator order, not business order.
- The same order is not guaranteed after UPDATE/rewrite.
- It does not replace ORDER BY on business columns.
- It does not guarantee stable pagination under concurrent changes.

Using ORDER BY ctid for a diagnostic task or temporary physical selection can make sense, but never use it as the API/report order users expect.

## 29. Using ctid When a Table Has Duplicates and No Key: Proceed with Care

In a legacy table lacking a key, ctid may be a way to target a specific tuple in a maintenance statement.

Yet this is a **transitional fix**, not a long-term schema design.

The workflow should be:

1. Identify duplicates by business columns.
2. Choose the canonical row by business criteria.
3. Use ctid in the same statement to delete/update selected tuples.
4. Verify data after the operation.
5. Create a unique constraint/index if data and business rules permit.
6. Add a proper primary key if needed.
7. Update applications to reference the logical key.

If a table lacks a primary key, treat that as a data modeling issue to resolve.

## 30. Lab: Observing ctid Changes

Create the practice schema and table:

~~~sql
-- RUN ONLY IN A PRACTICE DATABASE.
DROP SCHEMA IF EXISTS jdbc_storage_lab CASCADE;
CREATE SCHEMA jdbc_storage_lab;

CREATE TABLE jdbc_storage_lab.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_ref text NOT NULL,
    status text NOT NULL DEFAULT 'new',
    amount numeric(12,2) NOT NULL CHECK (amount > 0),
    created_at timestamptz NOT NULL
        DEFAULT transaction_timestamp()
);

CREATE INDEX idx_orders_customer
ON jdbc_storage_lab.orders (customer_ref);

INSERT INTO jdbc_storage_lab.orders (
    customer_ref, status, amount
)
SELECT
    'customer-' || (g % 100)::text,
    'new',
    (10 + (g % 1000))::numeric(12,2)
FROM generate_series(1, 1000) AS s(g);

ANALYZE jdbc_storage_lab.orders;
~~~

### Initial Observation

~~~sql
SELECT
    order_id,
    customer_ref,
    status,
    tableoid::regclass AS physical_table,
    ctid
FROM jdbc_storage_lab.orders
WHERE order_id BETWEEN 1 AND 10
ORDER BY order_id;
~~~

Record the ctid from this observation only for comparison in the lab. Do not put concrete values into application code.

### UPDATE One Row

~~~sql
BEGIN;

SELECT order_id, status, ctid
FROM jdbc_storage_lab.orders
WHERE order_id = 1;

UPDATE jdbc_storage_lab.orders
SET status = 'paid'
WHERE order_id = 1
RETURNING order_id, status, ctid;

ROLLBACK;
~~~

Observe the ctid returned after UPDATE inside the transaction. You may see a different tuple version location; exact values depend on page layout and concurrent activity.

### Why ROLLBACK?

To restore the lab's business row state after observation. Sequence/identity allocations are not necessarily rolled back; do not expect contiguous subsequent IDs.

## 31. Partition Lab to Observe tableoid and ctid

~~~sql
CREATE TABLE jdbc_storage_lab.partitioned_orders (
    order_id bigint NOT NULL,
    created_at date NOT NULL,
    amount numeric(12,2) NOT NULL,
    PRIMARY KEY (order_id, created_at)
) PARTITION BY RANGE (created_at);

CREATE TABLE jdbc_storage_lab.orders_2026_01
PARTITION OF jdbc_storage_lab.partitioned_orders
FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');

CREATE TABLE jdbc_storage_lab.orders_2026_02
PARTITION OF jdbc_storage_lab.partitioned_orders
FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');

INSERT INTO jdbc_storage_lab.partitioned_orders
    (order_id, created_at, amount)
VALUES
    (1, DATE '2026-01-10', 10),
    (2, DATE '2026-01-11', 20),
    (3, DATE '2026-02-10', 30),
    (4, DATE '2026-02-11', 40);
~~~

Query:

~~~sql
SELECT
    order_id,
    tableoid::regclass AS physical_partition,
    ctid
FROM jdbc_storage_lab.partitioned_orders
ORDER BY order_id;
~~~

Observations:

- Rows in the same partition share the same relation name.
- Two independent partitions can have identical ctids.
- Only the tableoid/ctid pair distinguishes physical locators across them in that query.

## 32. Safe Batch Update Within the Same Statement

Using the single orders table and business conditions:

~~~sql
BEGIN;

WITH selected AS (
    SELECT ctid
    FROM jdbc_storage_lab.orders
    WHERE status = 'new'
    ORDER BY order_id
    FOR UPDATE SKIP LOCKED
    LIMIT 25
)
UPDATE jdbc_storage_lab.orders AS o
SET status = 'paid'
FROM selected AS s
WHERE o.ctid = s.ctid
RETURNING o.order_id, o.status, o.ctid;

ROLLBACK;
~~~

In a single table, ctid acts as a locator within that relation. SELECT locks the chosen rows and UPDATE uses the locator in the same statement.

### Partitioned Table Version

~~~sql
BEGIN;

WITH selected AS (
    SELECT tableoid, ctid
    FROM jdbc_storage_lab.partitioned_orders
    ORDER BY created_at, order_id
    FOR UPDATE SKIP LOCKED
    LIMIT 2
)
UPDATE jdbc_storage_lab.partitioned_orders AS p
SET amount = amount + 1
FROM selected AS s
WHERE p.tableoid = s.tableoid
  AND p.ctid = s.ctid
RETURNING p.order_id, p.tableoid::regclass, p.ctid;

ROLLBACK;
~~~

This example selects rows across multiple partitions and retains both tableoid/ctid. It only illustrates a batch locator; do not persist the locator pair beyond the transaction.

## 33. Why Must Selection Logic Stay Based on Business Keys?

In the sample batch:

~~~sql
ORDER BY created_at, order_id
~~~

establishes an explainable business ordering. ctid is only used afterward to target the locked tuples.

If replaced with:

~~~sql
ORDER BY ctid
~~~

the worker would prioritize by physical layout rather than timestamp, ID, or SLA. After a rewrite, the order could change.

**Select rows using meaningful business conditions/ordering, then use ctid as a temporary locator when technically justified.**

## 34. Controlled Batch DELETE

~~~sql
BEGIN;

WITH selected AS (
    SELECT tableoid, ctid
    FROM jdbc_storage_lab.partitioned_orders
    WHERE amount < 25
    ORDER BY created_at, order_id
    FOR UPDATE SKIP LOCKED
    LIMIT 100
)
DELETE FROM jdbc_storage_lab.partitioned_orders AS p
USING selected AS s
WHERE p.tableoid = s.tableoid
  AND p.ctid = s.ctid
RETURNING p.order_id, p.tableoid::regclass;

ROLLBACK;
~~~

This is a maintenance example with transaction rollback. In production, commit only with an approved deletion policy, backup/retention, and row-count verification. Never use locators saved from a previous run.

## 35. Why Not Store ctid in a Message Queue?

Suppose a worker publishes a message:

~~~json
{
  "table": "public.orders",
  "ctid": "(12,7)"
}
~~~

A consumer receives the message minutes later. Meanwhile:

- The row may have been UPDATED.
- The old tuple version may no longer be visible.
- The relation may have been rewritten or the row moved across partitions.
- The table name may have changed.
- The database may have been restored to another cluster.

The message no longer reliably locates the row.

### What Should the Message Contain?

~~~json
{
  "event_type": "order.reconcile",
  "order_id": "order-12345",
  "request_id": "req-abc"
}
~~~

Use the business ID and query the latest state appropriately. If version detection is needed, include a version column or event sequence with clear semantics.

## 36. ctid and CDC / Logical Decoding

Change Data Capture typically relies on WAL/logical decoding and replica identity to recognize changes under a replication model.

Do not design consumers treating the publisher's ctid as a subscriber key:

- Heap layouts are independent.
- Insert order/physical placement can differ.
- A table rewrite does not mean logical identity changed.
- Logical replication requires a primary/unique key or suitable replica identity.
- CDC events should carry logical keys and event metadata supported by the connector.

If a connector exposes ctid as auxiliary metadata, use it strictly per the connector/version contract, never turning it into an application primary key.

## 37. ctid, tableoid, and Index Scans

PostgreSQL indexes typically reference heap tuples via TIDs. When reading a plan:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, status
FROM jdbc_storage_lab.orders
WHERE order_id = 100;
~~~

You may see Index Scan or Index Only Scan depending on indexes/visibility map/columns. ctid is a heap-related physical locator concept, yet you do not need to SELECT ctid for PostgreSQL to use an index.

### Index-Only Scan Does Not Mean ctid Replaced Logical Keys

An index-only scan can fetch required data from the index when the visibility map allows confirming visibility without visiting the heap for every row. This is a separate query-plan optimization and does not alter the role of ctid.

## 38. Pages and Line Pointers: Do Not Interpret Offset as Byte Offset

ctid=(block,offset) is not:

- An absolute byte offset in the file.
- A row number in SQL results.
- A primary key.
- A WAL LSN.
- A transaction ID.
- A partition number.

Offset is the item/line-pointer number on the page. A tuple has a header, alignment, TOAST pointers, and storage details. For deep page-layout investigation, specialized tools/docs such as pageinspect (an optional extension) and version-specific knowledge are required.

Never calculate a file address by multiplying the block number by page size and adding offset as if offset were a byte position of the tuple.

## 39. tableoid Cast to regclass and Schema Resolution

tableoid::regclass displays the relation name conveniently. However, whether its text output is schema-qualified depends on search_path and name resolution.

To inspect OID and namespace:

~~~sql
SELECT
    c.oid,
    c.oid::regclass AS relation_name,
    n.nspname AS schema_name,
    c.relname
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE c.oid = (
    SELECT tableoid
    FROM jdbc_storage_lab.orders
    LIMIT 1
);
~~~

This is a read-only catalog query. pg_class.oid identifies the current relation in the catalog; do not persist it as a long-term external identifier.

## 40. Limitations of ctid and tableoid

| Characteristic | ctid | tableoid |
| --- | --- | --- |
| Physical addressing | Yes, tuple version | Identifies the relation holding the tuple |
| Unique within one relation at a given point | Yes for a tuple version | No, many rows share the same tableoid |
| Unique across multiple relations | No | Only when paired with ctid in the right context |
| Stable across UPDATE | No | Usually relation does not change unless the row moves tables |
| Stable across rewrite | No | Relation OID may remain or change depending on operation; not a durable contract |
| Business meaning | No | No |
| Usable as primary key | No | No |
| Usable as foreign key | No | No |
| Usable for long-term pagination | No | No |
| Usable in same-statement maintenance | Possible | Helpful across multiple partitions/relations |
| Identifies physical partition | Insufficient alone | Yes |

## 41. Designing Logical Identity Properly

A business table should typically have keys:

~~~sql
CREATE TABLE app.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    external_order_id text UNIQUE,
    customer_id bigint NOT NULL,
    status text NOT NULL,
    version bigint NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now()
);
~~~

Depending on the system:

- order_id is a surrogate primary key.
- external_order_id is a key from an external system if a uniqueness contract applies.
- version supports optimistic concurrency.
- created_at serves business timestamps.
- ctid/tableoid are used only for diagnostics or short-lived storage operations.

### Natural Key or Surrogate Key?

Choose based on business semantics, stability, size, uniqueness, and integration needs. Not every table needs both, yet most important tables need a reliable logical key.

## 42. Operations That Can Invalidate Old Locators

| Operation | Impact to keep in mind |
| --- | --- |
| UPDATE | Creates a new tuple version; new ctid may differ |
| HOT UPDATE | Still creates a new tuple version; line pointer position may differ on the same page |
| Regular VACUUM | Reclaims/prunes dead tuples; does not rewrite all live rows like VACUUM FULL |
| VACUUM FULL | Rewrites/compacts the relation; ctid changes |
| CLUSTER | Rewrites the table by index; ctid changes |
| Certain ALTER TABLEs | May rewrite the relation depending on operation/version |
| Partition key UPDATE | May move the row to another partition |
| DROP/CREATE table | New relation identity, new tableoid |
| Restore to another cluster | OIDs and physical layout are not preserved as an external contract |
| DELETE then re-INSERT | New row, new locator may be assigned |

Key point: **not every operation needs to change ctid** to conclude it is non-durable. Normal business operations like UPDATE alone are enough to make ctid unsuitable as an ID.

## 43. Common Mistakes

1. **Using ctid as a primary key** because it looks unique in the current table.
2. **Caching ctid in the application** and reusing it after an UPDATE.
3. **Using ctid as a foreign key** between two tables.
4. **Using ctid as a pagination token** in an API.
5. **Joining two tables solely on ctid**, causing accidental matches of physical positions.
6. **Querying a partitioned parent table with only ctid**, omitting tableoid.
7. **Assuming tableoid is a durable global ID** across dump/restore.
8. **Thinking ctid is a byte offset**, rather than a block/line-pointer pair.
9. **Thinking ctid increases with order_id or created_at**.
10. **Thinking HOT updates preserve ctid**, even though a new tuple version is still created.
11. **Assuming regular VACUUM and VACUUM FULL rewrite identically**.
12. **Running VACUUM FULL/CLUSTER in production without accounting for locks/I/O**.
13. **Using ctid to track every UPDATE**, instead of an audit/version column.
14. **Using xmin/xmax as actor IDs or timestamps**.
15. **Reusing an old ctid in a later transaction**, when the row may already have changed.
16. **Using locators without row locks in concurrent batch maintenance**.
17. **Omitting tableoid when handling multiple partitions**, targeting the wrong relation.
18. **Using ORDER BY ctid as business order**.
19. **Using ctid instead of a CDC replica identity**.
20. **Running SELECT * and expecting system columns to be returned**, when they must be selected explicitly.
21. **Thinking tableoid is a table name**, though its type is OID; cast to regclass when displaying.
22. **Failing to distinguish parent relations from physical child partitions**.
23. **Using ctid as a message queue locator** over time.
24. **Lacking a primary key on a legacy table and delaying logical identity design**.
25. **Failing to back up/preview before deleting duplicates with ctid**.

## 44. Practice Exercises with Answers

Use the jdbc_storage_lab schema when SQL is needed. Only run DELETE/UPDATE statements in a lab database; use transaction rollback when testing.

### Exercise 1. What is ctid?

**Answer:** A physical tuple identifier of type tid representing the block number and item/line-pointer offset of a tuple version in a relation.

### Exercise 2. What is tableoid?

**Answer:** The OID of the relation containing the tuple; useful for identifying the partition/inheritance child.

### Exercise 3. Does SELECT * return ctid?

**Answer:** Not automatically. Select system columns explicitly.

### Exercise 4. Read ctid of 10 orders

~~~sql
SELECT order_id, ctid
FROM jdbc_storage_lab.orders
ORDER BY order_id
LIMIT 10;
~~~

**Answer:** Returns ctid for the selected currently visible tuple versions.

### Exercise 5. Read table name from tableoid

~~~sql
SELECT tableoid, tableoid::regclass
FROM jdbc_storage_lab.orders
LIMIT 5;
~~~

**Answer:** The first column is the OID; the second column displays the relation name.

### Exercise 6. Is ctid a primary key?

**Answer:** No. UPDATE/rewrite can change it and it carries no business semantics.

### Exercise 7. What format does ctid have?

**Answer:** A pair (block_number, item_offset), e.g., illustrative format (12,7).

### Exercise 8. Can UPDATE change ctid?

**Answer:** Yes. PostgreSQL creates a new tuple version under MVCC.

### Exercise 9. Does a HOT update mean ctid stays the same?

**Answer:** No. HOT can preserve index entries and chain within the same page, yet still creates a new tuple version.

### Exercise 10. Is regular VACUUM the same as VACUUM FULL?

**Answer:** No. Regular VACUUM reclaims/reuses dead space; VACUUM FULL rewrites/compacts the relation.

### Exercise 11. Can CLUSTER change ctid?

**Answer:** Yes. It rewrites the relation in index order.

### Exercise 12. How is tableoid helpful in partition queries?

**Answer:** Identifies the actual child partition containing the row.

### Exercise 13. Can two partitions have the same ctid?

**Answer:** Yes. Block/offset numbering is independent per relation.

### Exercise 14. What should a locator across multiple partitions include?

**Answer:** Combine tableoid and ctid within the appropriate physical context.

### Exercise 15. Is the tableoid/ctid pair a long-term key?

**Answer:** No. ctid changes with tuple versions/rewrites; tableoid is not a durable external identity.

### Exercise 16. Why is joining two tables by ctid wrong?

**Answer:** Two independent relations can share physical TIDs while having no business relationship; use foreign keys/business keys.

### Exercise 17. When is ctid appropriate in batch maintenance?

**Answer:** When selecting and modifying tuples in the same statement/transaction, usually combined with row locks; never persist the locator for later use.

### Exercise 18. Why use tableoid in partitioned batch operations?

**Answer:** ctid is scoped only to a single relation; tableoid distinguishes which partition holds the tuple.

### Exercise 19. What does FOR UPDATE SKIP LOCKED do?

**Answer:** Locks selected rows and skips rows currently locked by others, suitable for certain worker queues/batch processing.

### Exercise 20. Can ctid replace optimistic locking?

**Answer:** No. Use a logical primary key combined with a version column/conditional UPDATE.

### Exercise 21. Is xmin equivalent to created_by?

**Answer:** No. It is transaction metadata, not a user identity.

### Exercise 22. Does xmax always mean the row was deleted?

**Answer:** No. It has complex internal semantics and can relate to lock metadata and visibility.

### Exercise 23. What does tableoid::regclass return?

**Answer:** A readable relation name following regclass/search_path rules.

### Exercise 24. Can ctid serve as an API cursor token?

**Answer:** No. Use keyset pagination on a stable primary/business key.

### Exercise 25. What can updating a partition key do?

**Answer:** It can move the row to another partition, causing both tableoid and ctid to change.

### Exercise 26. Where can SELECT on an inheritance parent return rows from?

**Answer:** From the parent and children per default semantics; use ONLY to read solely the parent relation.

### Exercise 27. Why is ctid not used as a logical replication key?

**Answer:** Publisher and subscriber have separate physical layouts; replication identity requires a logical key/replica identity.

### Exercise 28. How to count rows per partition?

~~~sql
SELECT tableoid::regclass, count(*)
FROM jdbc_storage_lab.partitioned_orders
GROUP BY tableoid
ORDER BY 1;
~~~

**Answer:** Groups by the physical relation OID of the partitions holding rows.

### Exercise 29. Why not hard-code '(0,1)' in an UPDATE?

**Answer:** The locator may belong to another row or be stale; it must be obtained in the proper statement/transaction with appropriate locking logic.

### Exercise 30. What design is appropriate to detect whether a row has been modified?

**Answer:** A logical primary key combined with a version column or optimistic locking condition, not ctid.

## 45. Checklist for Safe System Column Usage

- [ ] Understand ctid is a tuple version's TID, not a business ID.
- [ ] Read ctid as a block/line-pointer pair, not a byte offset.
- [ ] Select system columns explicitly; do not expect SELECT * to return them.
- [ ] Use tableoid::regclass to inspect the relation holding a row.
- [ ] Combine tableoid + ctid when a locator spans multiple relations/partitions.
- [ ] Never store ctid as a primary key, foreign key, or external identifier.
- [ ] Never use ctid as an API pagination token or long-term checkpoint.
- [ ] Never use xmin/xmax as actor/timestamp audit fields.
- [ ] Understand UPDATE creates a new tuple version and ctid can change.
- [ ] Distinguish HOT updates from "no new tuple version."
- [ ] Distinguish regular VACUUM from VACUUM FULL/CLUSTER.
- [ ] Account for DDL rewrites and partition movement.
- [ ] Select rows using business conditions/order, using ctid as a temporary locator when needed.
- [ ] If operating across multiple partitions, keep tableoid alongside ctid.
- [ ] Use appropriate row locks/transactions for concurrent batch maintenance.
- [ ] Never persist locators across COMMIT for later processing.
- [ ] Use primary/business keys for application logic.
- [ ] Use a version column for optimistic concurrency.
- [ ] Use an appropriate replica identity for logical replication/CDC.
- [ ] Preview/back up and define survivor criteria before deduplicating.
- [ ] Measure lock/I/O impact and schedule maintenance windows for VACUUM FULL/CLUSTER.
- [ ] Never treat ctid as business ordering.
- [ ] Check catalogs/version when investigating storage.
- [ ] Document physical locator limits in code reviews and operational runbooks.

## 46. Official PostgreSQL Documentation

Consult according to your deployed major version:

- [System Columns](https://www.postgresql.org/docs/current/ddl-system-columns.html) — tableoid, ctid, xmin, xmax, and other system columns.
- [MVCC Introduction](https://www.postgresql.org/docs/current/mvcc-intro.html) — Multi-Version Concurrency Control.
- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html) — VACUUM, dead tuples, visibility map, and freeze.
- [VACUUM](https://www.postgresql.org/docs/current/sql-vacuum.html) — VACUUM and FULL.
- [CLUSTER](https://www.postgresql.org/docs/current/sql-cluster.html) — rewriting/reordering a relation.
- [Table Partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html) — partitioned tables, routing, and partition movement.
- [Inheritance](https://www.postgresql.org/docs/current/ddl-inherit.html) — table inheritance.
- [UPDATE](https://www.postgresql.org/docs/current/sql-update.html) — UPDATE and RETURNING.
- [DELETE](https://www.postgresql.org/docs/current/sql-delete.html) — DELETE and USING/RETURNING.
- [SELECT](https://www.postgresql.org/docs/current/sql-select.html) — locking clauses such as FOR UPDATE/SKIP LOCKED.
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html) — row locks and concurrency.
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html) — snapshots/MVCC.
- [Data Types: Object Identifier Types](https://www.postgresql.org/docs/current/datatype-oid.html) — OID, regclass, and aliases.
- [System Catalog pg_class](https://www.postgresql.org/docs/current/catalog-pg-class.html) — relation metadata.
- [System Catalog pg_namespace](https://www.postgresql.org/docs/current/catalog-pg-namespace.html) — schema metadata.
- [Logical Replication](https://www.postgresql.org/docs/current/logical-replication.html) — logical replication concepts.
- [ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html) — operations that can alter structure/storage.
- [EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html) — inspecting execution plans.

The /current/ path points to the latest PostgreSQL documentation. Storage details, HOT, partition movement, and certain DDL rewrites may vary by major version; check the documentation for your actual server.

## 47. Summary

**ctid and tableoid describe the physical location and containing relation of a tuple; they do not define the durable identity of a business row.**

Key takeaways:

1. **ctid is the TID of a tuple version**, consisting of a block number and item offset within the relation.
2. **tableoid is the OID of the physical relation holding the row**, which can be cast to regclass to display the table/partition name.
3. **UPDATE creates a new tuple version**, so ctid can change; HOT updates also create a new version.
4. **Regular VACUUM differs from VACUUM FULL**. Regular VACUUM reclaims/reuses dead space, whereas VACUUM FULL and CLUSTER rewrite the relation and can change tuple locations.
5. **Partition/inheritance queries need tableoid to identify the child relation**. ctid alone cannot distinguish tuples across two different tables.
6. **(tableoid, ctid) is useful as a temporary physical locator**, especially when operating within the same statement/transaction.
7. **Never store ctid/tableoid as a primary key, foreign key, pagination token, queue message, or replication identity**.
8. **Use primary/business keys for identity** and a version column for optimistic locking.
9. **Use FOR UPDATE/appropriate transactions** when batch maintenance must lock selected rows; ctid does not replace concurrency control.
10. **xmin/xmax are also MVCC metadata**, not actor IDs, timestamps, or audit history.
11. **Storage/rewrite/migration operations can invalidate old locators**, so strictly bound their usage scope.
12. **Designing schemas with logical identity from the start** keeps applications, CDC, and operations stable.

When you clearly separate **the physical address of a tuple** from **the logical identity of data**, you can leverage system columns for PostgreSQL diagnostics and maintenance without creating fragile dependencies on how the database happens to store rows.
