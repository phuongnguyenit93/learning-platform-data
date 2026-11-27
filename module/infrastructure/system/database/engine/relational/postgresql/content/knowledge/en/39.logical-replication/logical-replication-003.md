# Replica Identity and Requirements for UPDATE or DELETE

In PostgreSQL logical replication, an INSERT change can be sent by transmitting the new row. For UPDATE or DELETE, the subscriber also needs to know **which old row on the subscriber corresponds to the row that just changed on the publisher**. PostgreSQL needs a stable identifier to locate that row. This mechanism is called **replica identity**.

Replica identity determines what information about the old row is written to WAL and sent via logical replication. Normally PostgreSQL uses the primary key. If a table has no primary key, you can choose an eligible unique index or use REPLICA IDENTITY FULL to send the entire old row. Without an appropriate identity, UPDATE and DELETE on a published table can fail when logical decoding/replication needs to identify the row.

This lesson explains the four modes—DEFAULT, USING INDEX, FULL, and NOTHING—requirements for primary keys/unique indexes, how the publisher sends old-row identity, how the subscriber applies UPDATE/DELETE, limitations with publication column lists, partitioned tables, and schema changes, as well as how to detect and resolve replica identity errors.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain why logical replication needs old-row identification for UPDATE and DELETE.
2. Distinguish replica identity from primary key and unique constraint.
3. Explain REPLICA IDENTITY DEFAULT, USING INDEX, FULL, and NOTHING.
4. Choose an appropriate primary key or unique index as replica identity.
5. Configure replica identity using ALTER TABLE.
6. Understand the old key/old tuple data written to WAL and transmitted to the subscriber.
7. Distinguish publisher requirements from structures needed on the subscriber.
8. Identify errors when a publication emits UPDATE/DELETE.
9. Understand the impact of FULL on WAL volume, CPU, and row lookup.
10. Design migrations to add/switch replica identity while minimizing downtime.
11. Handle column lists, row filters, partitions, TOAST, and schema drift.
12. Verify logical replication using SQL, logs, and test cases.

> **Version:** This lesson focuses on built-in PostgreSQL logical replication. Certain behaviors/options depend on the major version. If using an extension or CDC connector, also check how the decoder/connector interprets replica identity.

## 2. Why Do UPDATE and DELETE Need Old-Row Identification?

Suppose the publisher has a table:

```sql
CREATE TABLE public.customer (
    customer_id BIGINT PRIMARY KEY,
    email TEXT NOT NULL,
    display_name TEXT NOT NULL
);
```

A transaction runs:

```sql
UPDATE public.customer
SET display_name = 'An Nguyen'
WHERE customer_id = 42;

DELETE FROM public.customer
WHERE customer_id = 42;
```

The subscriber needs to know which row must be updated or deleted. customer_id=42 is a stable identifier, so PostgreSQL can send the old key instead of the entire old row.

### INSERT Differs from UPDATE/DELETE

- INSERT: the subscriber receives the new row and inserts it.
- UPDATE: the subscriber must locate the old row, then apply the new values.
- DELETE: the subscriber must locate the old row and delete it.
- TRUNCATE: handled as a table-level operation; no per-row identity is needed.

Replica identity matters primarily for UPDATE and DELETE. A table that only publishes INSERT does not need old-row identity to send insert records.

## 3. Replica Identity Flow in Logical Replication

```text
Publisher table
      |
      | UPDATE / DELETE
      v
Replica identity determines old-row key
      |
      v
WAL logical decoding
      |
      v
Logical replication stream
      |
      v
Subscriber apply worker
      |
      +--> locate old row
      |
      +--> UPDATE new values / DELETE matched row
```

The publisher determines which old-row identity is recorded and sent. The subscriber uses the received identity information to find the corresponding row in the target table. The subscriber must have a compatible schema and matching data to apply successfully.

### Replica Identity Is Not a Schema Synchronization Mechanism

Logical replication does not automatically replicate DDL in general. Creating primary keys/indexes, changing data types, adding columns, or changing replica identity must be deployed appropriately on both subscriber and publisher. An active publication/subscription does not automatically guarantee both sides always have identical schemas.

## 4. What Is Replica Identity?

Replica identity is a table-level setting that tells PostgreSQL what information about the old row must be recorded in WAL so logical decoding can emit UPDATE/DELETE.

Modes:

| Mode | Meaning |
|---|---|
| DEFAULT | Uses primary key if the table has a primary key |
| USING INDEX | Uses an eligible user-selected unique index |
| FULL | Records the entire old row |
| NOTHING | Records no old-row identity |

Inspect the configuration:

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    c.relreplident AS replica_identity_code
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n.nspname, c.relname;
```

relreplident is an internal code: d is default, i is index, f is full, and n is nothing. In day-to-day operations, use \d+ table_name in psql or inspect the catalog to view details.

## 5. DEFAULT: Using the Primary Key

DEFAULT is PostgreSQL's default mode. If a table has a primary key, the primary key is used as the replica identity.

```sql
CREATE TABLE public.orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status TEXT NOT NULL,
    total_amount NUMERIC(12, 2) NOT NULL
);

ALTER TABLE public.orders
REPLICA IDENTITY DEFAULT;
```

For UPDATE or DELETE, PostgreSQL only needs to send the old primary key values as the identifier, along with any new data needed for an update.

### Why Is DEFAULT Usually a Good Choice?

- Primary keys are unique.
- Primary key columns cannot be NULL.
- A unique index supports lookups.
- Old-row identity is smaller than sending the entire row.
- Key semantics are typically already defined by the application.

### Tables Without a Primary Key

If a table has no primary key, DEFAULT does not automatically pick an arbitrary column as identity. PostgreSQL cannot assume email, name, or another value is unique. When a publication emits UPDATE/DELETE, a suitable identity must be configured.

## 6. Inspecting Existing Primary Keys

List primary key constraints:

```sql
SELECT
    n.nspname AS schema_name,
    t.relname AS table_name,
    con.conname AS primary_key_name,
    pg_catalog.pg_get_constraintdef(con.oid) AS definition
FROM pg_catalog.pg_constraint AS con
JOIN pg_catalog.pg_class AS t
  ON t.oid = con.conrelid
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = t.relnamespace
WHERE con.contype = 'p'
ORDER BY n.nspname, t.relname;
```

A table with a primary key normally already has a corresponding unique index. If DEFAULT is active, there is no need to additionally specify USING INDEX for that primary key.

### Composite Primary Key

A primary key can consist of multiple columns:

```sql
CREATE TABLE public.order_items (
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    PRIMARY KEY (order_id, line_no)
);
```

The identity is the tuple (order_id, line_no). Both old values must be transmitted to identify the exact row.

## 7. How Do PRIMARY KEY and Replica Identity Differ?

A primary key is a relational model constraint: it enforces uniqueness and NOT NULL, and is commonly referenced by foreign keys. Replica identity is a table setting controlling old-row information for logical decoding.

| Concept | Role |
|---|---|
| Primary key | Data constraint, identifies rows in the schema |
| Unique constraint/index | Enforces uniqueness over columns/index expressions |
| Replica identity | Selects old-row identity recorded for logical replication |

A primary key can automatically act as the replica identity in DEFAULT mode. However, replica identity can also use another unique index or the entire row via FULL.

### Do Not Create a Primary Key Just to "Make Replication Work" Without Checking Data

Before adding a primary key, verify that the column or column pair is truly unique, non-NULL, and semantically stable. If existing data contains duplicates or NULLs, adding the constraint will fail or require cleaning the data first.

## 8. USING INDEX: Using a Unique Index

If a table lacks a primary key but has an eligible unique index, you can select that index as the replica identity.

Example:

```sql
CREATE TABLE public.account_profile (
    account_id BIGINT NOT NULL,
    external_ref TEXT NOT NULL,
    full_name TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX account_profile_external_ref_uq
ON public.account_profile (external_ref);

ALTER TABLE public.account_profile
REPLICA IDENTITY USING INDEX account_profile_external_ref_uq;
```

When external_ref is unique and non-NULL, PostgreSQL can use it to find the old row.

### Index Requirements

An index chosen as replica identity must:

- Be a unique index.
- Not be a partial index.
- Not be deferrable.
- Contain only columns marked NOT NULL.
- Be a valid index usable as a row identifier.

Check PostgreSQL documentation for your exact major version and inspect catalog/index definitions before making changes. A unique index allowing NULL in one or more columns does not meet this identity requirement.

### Why Must Columns Be NOT NULL?

A unique index in PostgreSQL can allow multiple rows containing NULL under default semantics. That does not guarantee unique identification as required by replica identity. Identity columns must hold non-NULL values to identify old rows reliably.

## 9. Finding Eligible Unique Indexes

List indexes on a table:

```sql
SELECT
    index_class.relname AS index_name,
    idx.indisunique,
    idx.indisvalid,
    idx.indisready,
    idx.indimmediate,
    idx.indpred IS NOT NULL AS is_partial,
    pg_catalog.pg_get_indexdef(idx.indexrelid) AS index_definition
FROM pg_catalog.pg_index AS idx
JOIN pg_catalog.pg_class AS index_class
  ON index_class.oid = idx.indexrelid
WHERE idx.indrelid = 'public.account_profile'::regclass
ORDER BY index_class.relname;
```

This query exposes unique/valid/partial/immediate properties. You must also check that all index key columns are NOT NULL; do not infer eligibility from indisunique=true alone.

Check nullability of columns in an index:

```sql
SELECT
    a.attname AS column_name,
    a.attnotnull AS is_not_null
FROM pg_catalog.pg_index AS i
CROSS JOIN LATERAL unnest(i.indkey) WITH ORDINALITY AS k(attnum, ord)
JOIN pg_catalog.pg_attribute AS a
  ON a.attrelid = i.indrelid
 AND a.attnum = k.attnum
WHERE i.indexrelid = 'public.account_profile_external_ref_uq'::regclass
  AND k.ord <= i.indnkeyatts
ORDER BY k.ord;
```

Index expressions or included columns must be evaluated according to exact version semantics; a replica identity index must identify rows via appropriate key columns. Prefer simple indexes on NOT NULL columns.

## 10. Configuring USING INDEX

Command:

```sql
ALTER TABLE public.account_profile
REPLICA IDENTITY USING INDEX account_profile_external_ref_uq;
```

Verify using psql:

```text
\d+ public.account_profile
```

Or check pg_class.relreplident and the associated index in the catalog.

### Index Referenced by Replica Identity

You cannot arbitrarily drop an index currently used as replica identity. Before dropping/rebuilding, switch replica identity to another suitable index or DEFAULT/FULL. Changing identity must be coordinated with the publication, subscriber, and workload.

## 11. FULL: Sending the Entire Old Row

When no primary key or suitable unique index exists, you can use:

```sql
ALTER TABLE public.legacy_customer
REPLICA IDENTITY FULL;
```

With FULL, PostgreSQL records information for the entire old row so logical decoding can emit the old row. The subscriber can use those values to find the row to update/delete.

### When Is FULL Useful?

- Legacy tables without a unique key.
- Cannot add a primary key/unique index immediately.
- A CDC consumer needs old row values to build change events.
- Temporary use during a migration before a stable key exists.

### Costs

- WAL can grow larger because the old tuple contains many columns.
- Logical decoding must process more data.
- The subscriber may have to search for rows across many columns instead of a small index key.
- Wide rows/TOASTed data can increase payload size and I/O.
- Data types lacking appropriate equality semantics can impose limits when searching for rows on the subscriber.

FULL is a compatibility workaround, not usually the optimal performance choice for large/write-heavy tables.

## 12. NOTHING: Recording No Old-Row Identity

You can configure:

```sql
ALTER TABLE public.event_ingest
REPLICA IDENTITY NOTHING;
```

NOTHING stores no old-row identity for the table. It is suitable for tables that only publish INSERT or when logical decoding of UPDATE/DELETE is not needed for that table.

### What If the Publication Emits UPDATE/DELETE?

When logical replication needs to emit UPDATE or DELETE from a table without a replica identity, the operation can fail with an error requiring replica identity. NOTHING does not mean PostgreSQL automatically searches rows using all columns.

### Example INSERT-Only Publication

An append-only event log may publish only inserts:

```sql
CREATE PUBLICATION event_pub
FOR TABLE public.event_ingest
WITH (publish = 'insert');

ALTER TABLE public.event_ingest
REPLICA IDENTITY NOTHING;
```

If the publication is later modified to publish update/delete, an appropriate identity must be configured before the workload generates those operations.

## 13. Comparing the Four Modes

| Mode | Old-row data | Requirements | Typical performance |
|---|---|---|---|
| DEFAULT | Primary key columns | Has PK | Good, generally recommended |
| USING INDEX | Unique index key columns | Unique, non-partial, non-deferrable, key columns NOT NULL | Good if index is appropriate |
| FULL | Entire old row | No PK/unique identity required | Can be expensive in WAL/CPU/lookup |
| NOTHING | No old-row identity | Suitable only when UPDATE/DELETE replication is not needed | Does not support update/delete |

### Selection Rules

1. Appropriate primary key exists: use DEFAULT.
2. No primary key, but a stable unique key exists: use USING INDEX.
3. Cannot create a key, yet update/delete replication is needed: consider FULL and measure cost.
4. Only publishing inserts or no update/delete needed: NOTHING may be suitable.

## 14. How Is UPDATE Transmitted?

Suppose:

```sql
UPDATE public.account_profile
SET full_name = 'New Name'
WHERE external_ref = 'EXT-42';
```

With replica identity set to the unique index external_ref, the publisher needs to send the old identity external_ref='EXT-42' and the new row values according to publication/schema mapping.

Subscriber:

1. Receives the update message.
2. Uses the old identity to locate the existing row.
3. Applies the new columns.
4. Writes the result in the subscriber transaction.

### Updating an Identity Column

If the identity column itself changes, the publisher still needs the old identity to locate the row before the change and sends the new value. For example, changing external_ref from EXT-42 to EXT-43: the subscriber must search using the old value EXT-42, then update it to EXT-43.

This is why the old key must be preserved in the change record.

## 15. How Is DELETE Transmitted?

Example:

```sql
DELETE FROM public.account_profile
WHERE external_ref = 'EXT-42';
```

The publisher sends the old row identifier. The subscriber locates the corresponding row and deletes it.

If the subscriber has no matching row, apply may report an error because it could not find the tuple to delete. Possible causes include:

- The subscriber was already missing the row.
- A direct write on the subscriber caused data drift.
- Schema/identity mapping is incompatible.
- The subscription started from an inconsistent state.
- A data migration or manual cleanup ran on only one side.

### Do Not Arbitrarily Modify the Subscriber

In a unidirectional model, the subscriber is typically treated as read-only for replicated data. Manual UPDATE/DELETE on the subscriber can cause divergence and make the apply worker fail on subsequent transactions.

## 16. Replica Identity on Publisher and Subscriber

Replica identity configured on the publisher determines the old-row identity written to WAL and sent in the logical replication stream. The subscriber receives that identity information to locate the row.

On the subscriber, the local replica identity setting does not override the identity sent by the publisher. However, the subscriber still needs a compatible schema and consistent data. An appropriate index on the subscriber makes lookups fast; without an appropriate index, finding rows can be costly or hit limitations depending on identity/data types.

If the subscriber simultaneously publishes data onward to another subscriber, the subscriber's own replica identity matters for its outgoing stream.

### Create Keys on Both Sides

In many deployments, the same primary key/unique index should be created on both publisher and subscriber. DDL is not automatically synchronized by logical replication, so deploy schema migrations on both sides in a safe order.

## 17. What Happens Without a Replica Identity?

A table without a primary key in DEFAULT mode has no valid old-row identity. If a publication requires UPDATE/DELETE, logical replication cannot produce a change record with enough information to apply accurately.

Example:

```sql
CREATE TABLE public.inventory_snapshot (
    warehouse_code TEXT NOT NULL,
    sku TEXT NOT NULL,
    quantity INTEGER NOT NULL
);

CREATE PUBLICATION inventory_pub
FOR TABLE public.inventory_snapshot;

UPDATE public.inventory_snapshot
SET quantity = 10
WHERE warehouse_code = 'WH1'
  AND sku = 'SKU-1';
```

If the table remains on DEFAULT without a primary key, the update can raise a replica identity error when processed by logical decoding.

### Verify Before Publishing

Before adding a table to a publication with update/delete:

- Confirm a primary key or suitable unique index exists.
- Check relreplident.
- Check that the column list includes identity columns.
- Run update/delete tests in a staging environment.
- Monitor publisher logs and subscriber apply status.

## 18. Publications and the List of Published Operations

A publication can choose which operations to emit:

```sql
CREATE PUBLICATION app_pub
FOR TABLE public.orders
WITH (publish = 'insert, update, delete, truncate');
```

Default values in modern versions typically publish insert, update, delete, and truncate. Check the exact configuration:

```sql
SELECT
    pubname,
    pubinsert,
    pubupdate,
    pubdelete,
    pubtruncate
FROM pg_catalog.pg_publication;
```

### Publish INSERT Only

If a table is append-only, you can restrict the publication:

```sql
CREATE PUBLICATION audit_insert_pub
FOR TABLE public.audit_events
WITH (publish = 'insert');
```

Not publishing UPDATE/DELETE means those operations are not sent to subscriptions via this publication. It does not prevent applications from running update/delete on the publisher.

## 19. Publication Column Lists and Replica Identity

A publication can restrict which columns are sent. However, if a publication specifies a column list, that list must include all columns belonging to the replica identity so the subscriber can identify the old row.

Example:

```sql
CREATE PUBLICATION account_pub
FOR TABLE public.account_profile (
    external_ref,
    full_name,
    updated_at
);
```

If external_ref is the replica identity index, the column list must retain external_ref. If an identity column is missing, the publication definition may be rejected or fail to satisfy update/delete requirements depending on version.

### FULL and Column Lists

With REPLICA IDENTITY FULL, the old identity is the entire row. The column list must be designed to include sufficient identity columns; because the identity is the full row, restricting columns via a column list may be incompatible with that requirement. Check exact version rules before deploying.

## 20. Row Filters and Old Rows

A publication can use a row filter to publish only rows matching an expression:

```sql
CREATE PUBLICATION active_customer_pub
FOR TABLE public.customer
WHERE (status = 'active');
```

For UPDATE/DELETE, row filters have specific semantics regarding the old row; an update that causes a row to transition from matching to non-matching or vice versa must be understood accurately for your version. Do not treat a row filter as a full bidirectional sync mechanism.

### Interaction with Replica Identity

Replica identity identifies which row to update/delete; the row filter determines whether the change belongs in the publication. The two mechanisms have different roles. Identity columns must still be transmitted as required by the publication column list.

## 21. Unique Indexes and NULL Semantics

A unique index can allow multiple NULL values under default NULL-distinct behavior. Therefore, UNIQUE alone does not prove an index can serve as replica identity.

Unsuitable example:

```sql
CREATE TABLE public.device (
    serial_no TEXT,
    model TEXT NOT NULL
);

CREATE UNIQUE INDEX device_serial_uq
ON public.device (serial_no);
```

serial_no is nullable, so the index does not meet replica identity index requirements. Verify data and constraints first:

```sql
ALTER TABLE public.device
ALTER COLUMN serial_no SET NOT NULL;

ALTER TABLE public.device
REPLICA IDENTITY USING INDEX device_serial_uq;
```

Only run SET NOT NULL if existing data contains no NULLs and business rules allow it. Otherwise, clean/backfill data and deploy the constraint according to a migration plan.

## 22. Partial Unique Indexes Cannot Be Used

Example:

```sql
CREATE UNIQUE INDEX active_user_email_uq
ON public.users (email)
WHERE is_active;
```

This index enforces uniqueness only for rows satisfying the predicate. Rows outside the predicate may share duplicate emails, so it cannot uniquely identify every row in the table. A partial index is not eligible as a replica identity.

If email needs to identify all rows, you must create a suitable unique index across the entire dataset or choose another key.

## 23. Deferrable Unique Constraints

A unique constraint can be declared DEFERRABLE, allowing uniqueness checks to be deferred until transaction end. A replica identity index requires immediately enforced uniqueness to serve as a row identifier; deferrable indexes are not eligible.

Example of a deferrable constraint:

```sql
CREATE TABLE public.external_account (
    external_id TEXT NOT NULL,
    owner_id BIGINT NOT NULL,
    CONSTRAINT external_account_uq
        UNIQUE (external_id)
        DEFERRABLE INITIALLY DEFERRED
);
```

If an identity is needed, design a non-deferrable unique index/constraint that meets the requirements. Do not alter constraint semantics purely for replication without reviewing application transaction behavior.

## 24. Composite Unique Indexes

A multi-column unique index can act as replica identity if all key columns meet the requirements:

```sql
CREATE UNIQUE INDEX shipment_key_uq
ON public.shipment (tenant_id, shipment_no);

ALTER TABLE public.shipment
REPLICA IDENTITY USING INDEX shipment_key_uq;
```

If both columns are NOT NULL, their combination identifies a row. The subscriber needs the same identity columns and compatible data/schema to apply changes.

### Composite Key Trade-offs

- More columns increase identity payload size.
- Key columns must be stable and have clear semantics.
- Larger indexes can affect write performance.
- If one key column changes, the old composite key is still needed to locate the row before updating.

## 25. Impact of FULL on WAL Volume

Suppose a table has 40 columns, including large JSON/text fields. With an identity index consisting of a single BIGINT, the old-row identity is small. With FULL, logical decoding needs information for the entire old row.

### Observable Impacts

- WAL bytes increase on update/delete-heavy workloads.
- Logical decoding throughput decreases.
- Network payload grows larger.
- Subscriber apply consumes more CPU and lookup work.
- Replication lag rises when the consumer cannot keep up.

There is no fixed multiplier. Cost depends on row width, number of modified columns, TOAST usage, workload, compression, and decoder implementation.

### Measure Before/After

Monitor:

- pg_stat_wal.wal_bytes delta.
- WAL records/FPI if relevant to the workload.
- Logical slot retained WAL distance.
- Publisher CPU/WAL write throughput.
- Subscriber apply lag.
- Network bytes.

Compare under the same workload and sample window.

## 26. FULL and Row Lookup on the Subscriber

With an identity index, the subscriber can use key columns to locate the row. With FULL, the subscriber must rely on old-row values across many columns to identify the row. Without a suitable index, lookup may have to scan many rows.

### Large Tables

A table with hundreds of millions of rows and high update/delete rates incurs significant cost if every change must match across many columns. FULL should be treated as a fallback when no good key is possible, not an optimal default.

### Equality Semantics

Comparing old-row values depends on data types and equality operators. Some data types or extension types may not support the required comparison semantics. Test update/delete with the exact production schema before relying on FULL.

## 27. Replica Identity and TOAST

TOAST stores large values outside the main heap tuple when needed. Large text, jsonb, bytea, or array columns can be TOASTed.

With a primary key/unique index as identity, PostgreSQL only needs the old key columns to identify the row. With FULL, old-row data is much wider and can significantly increase WAL/decoder work.

### How to Design

- Prefer small, stable identity keys.
- Avoid choosing large JSON/text payloads as keys.
- Place primary keys/unique keys on columns with clear semantics.
- Measure WAL/replication throughput on rows with TOAST data.

Do not assume every old TOAST value is always transmitted identically across all output plugins; check decoder/protocol version and test actual event payloads.

## 28. Updating a Primary Key

PostgreSQL allows updating a primary key if constraints remain valid:

```sql
UPDATE public.orders
SET order_id = 90042
WHERE order_id = 42;
```

Logical replication needs the old identity order_id=42 to find the subscriber row, then applies the new key 90042.

### Application Impact

Primary keys should normally be immutable. Changing a PK can affect foreign keys, cache keys, application references, and downstream consumers. Logical replication handles old/new identities, but it does not eliminate business-level impacts.

### Subscriber Conflict

If the subscriber already has a row with the new key 90042, the update can violate a unique constraint and stop the apply worker. This is data divergence/constraint conflict that requires investigation.

## 29. DELETE and No Matching Row on Subscriber

If the publisher deletes a row with identity customer_id=42 but the subscriber does not have that row, the apply worker may report that it cannot find the tuple to delete.

Causes:

- Subscription initialized from an inconsistent snapshot.
- Table was modified directly on the subscriber.
- A transaction/DDL migration was missed.
- Publication row filter/column list changed.
- Subscription was disabled or errored during a period.

### Resolution

1. Stop and record the apply error.
2. Identify the failing table/key and transaction.
3. Compare publisher/subscriber rows.
4. Determine the source of divergence.
5. Repair subscriber data via an approved procedure or resynchronize the table.
6. Resume the subscription and verify the worker advances.

Do not disable constraints or skip all apply errors just to keep replication running; doing so can mask deeper divergence.

## 30. UPDATE and No Matching Row on Subscriber

If the old identity finds no row on the subscriber, logical apply does not know which row to update. This is usually a sign that the two sides have diverged or the initial copy missed rows.

### Targeted Inspection

For identity customer_id:

```sql
SELECT *
FROM public.customer
WHERE customer_id = 42;
```

Run on both publisher and subscriber, comparing row state and transaction history if available. For large tables, query by specific key rather than performing arbitrary full table scans.

## 31. Unique Conflict on Subscriber

An update may find the right old row, yet the new value violates a unique constraint on the subscriber:

```sql
UPDATE public.account_profile
SET external_ref = 'EXT-99'
WHERE external_ref = 'EXT-42';
```

If the subscriber already has EXT-99 on another row, applying the transaction fails. Replica identity locates the old row; it does not resolve conflicts between new data and existing constraints.

### How to Handle

- Check who is writing directly to the subscriber.
- Check for schema/constraint drift.
- Check whether the publisher has duplicates due to differing constraints.
- Reconcile data according to business rules.
- Resume the subscription only after the root cause is fixed.

## 32. Replica Identity and Publication Column Lists

If a publication defines a column list, identity columns must be included. A migration reducing the transmitted columns can accidentally drop keys required for update/delete.

### Procedure for Changing a Column List

1. Identify the current replica identity.
2. List the identity columns.
3. Design the new column list including all identity columns.
4. Update the subscriber schema before the data is needed.
5. Alter the publication using version-supported syntax.
6. Test insert/update/delete.
7. Monitor apply errors and consumer output.

## 33. Replica Identity and Row Filters

A row filter does not replace replica identity. The filter decides which rows belong to the publication; identity locates the old row when a change is sent.

When an update changes a row's filter match status, behavior can differ from assuming "if the new row matches, it is always sent." PostgreSQL logical replication has specific row-filter semantics for old/new rows and publication versions. Filter designs must test all three scenarios:

1. Row transitions from non-matching to matching.
2. Row transitions from matching to non-matching.
3. Row matches both before and after the update.

For CDC consumers, document these semantics clearly so downstream systems do not misinterpret events as a complete mirror of all rows.

## 34. Partitioned Tables

Logical replication can publish partitioned tables; actual rows are stored in partitions. Check replica identity on the partitioned root and on partitions according to your version, as well as whether the publication uses the partition root or publishes partitions separately.

### Things to Verify

- Replica identity/index is applied to the right table/partition.
- Unique indexes on partitioned tables have constraints regarding the partition key.
- Each partition has an appropriate schema/identity.
- The subscriber has a compatible partition structure if partitioning is to be preserved.
- Partition attach/detach and DDL are synchronized via a separate procedure.

Do not assume every ALTER TABLE on the root produces identical identity/index behavior across all partitions/versions; inspect the catalog of each partition and run update/delete tests.

## 35. Inheritance and Table Boundaries

Traditional table inheritance and declarative partitioning behave differently in publications. A publication can publish parent/partitions depending on specific options. Replica identity must still be satisfied for the physical tables generating changes.

When using inheritance/partitioning, inspect pg_publication_tables, pg_class, pg_index, and leaf tables to confirm the exact objects actually being published.

## 36. Schema Migration to Add a Primary Key

If a table lacks an identity, the long-term solution is usually adding a stable primary key:

```sql
ALTER TABLE public.legacy_customer
ADD COLUMN customer_id BIGINT GENERATED BY DEFAULT AS IDENTITY;

ALTER TABLE public.legacy_customer
ADD CONSTRAINT legacy_customer_pkey
PRIMARY KEY (customer_id);

ALTER TABLE public.legacy_customer
REPLICA IDENTITY DEFAULT;
```

This is a simple example. On large tables, adding a column/PK can require a table rewrite, index build, and significant locks depending on version/data/default. A production-grade migration plan is required.

### When the Table Already Has Data

Check:

- Backfill strategy and sequence/identity values.
- Lock duration.
- Disk headroom for index builds.
- Replication lag during migration.
- DDL execution on the subscriber.
- Whether the application depends on new insert behavior.

Do not run a large ALTER TABLE in production based solely on a lesson example.

## 37. Creating a Unique Index Concurrently

On large tables, CREATE UNIQUE INDEX CONCURRENTLY can reduce write blocking compared to a regular index build, though it has multiple phases/overhead and can fail if duplicates exist.

Example:

```sql
CREATE UNIQUE INDEX CONCURRENTLY customer_external_id_uq
ON public.customer (external_id);
```

Once the index is valid and columns satisfy NOT NULL:

```sql
ALTER TABLE public.customer
REPLICA IDENTITY USING INDEX customer_external_id_uq;
```

CREATE INDEX CONCURRENTLY cannot run inside a transaction block. Verify indisvalid=true and check for duplicates/nulls before switching identity.

## 38. Safely Switching Replica Identity

Suppose you are currently using FULL and want to switch to a unique index:

1. Identify a candidate key.
2. Clean up duplicates/NULLs.
3. Create a valid unique index.
4. Confirm the index meets all requirements.
5. Deploy the corresponding index/schema on the subscriber.
6. Switch the publisher via ALTER TABLE ... REPLICA IDENTITY USING INDEX.
7. Test update/delete.
8. Monitor WAL bytes and apply lag.
9. Keep a rollback plan if the schema migration fails.

### Why Not Drop FULL First?

Switching directly to NOTHING or dropping an index before the new identity is ready can prevent subsequent updates/deletes from replicating. Prepare the new identity first, then switch the configuration.

## 39. Changing a Primary Key or Unique Index

When changing a key:

- Ensure the new key exists and is unique on the publisher.
- Create the schema/index on the subscriber.
- Switch replica identity in the proper order.
- Account for in-flight changes pending in the replication stream.
- Test key updates and deletes.
- Only drop the old index once no longer used by identity/constraints/foreign keys.

For downstream CDC, changing identity can alter key columns in the event schema; notify consumers and version the consumer contract.

## 40. Logical Replication and wal_level

The publisher requires wal_level=logical to support logical decoding/replication. Replica identity is part of the old-row information written/exposed for logical decoding.

Check:

```sql
SHOW wal_level;
```

Changing wal_level requires a restart. If the publisher uses physical replication alongside logical replication, logical still supports physical standbys, though WAL contains additional information needed for logical decoding.

## 41. Replica Identity and Logical Decoding Plugins

Logical decoding plugins may present old-row identity in different output formats. A CDC connector may need the old key to construct before/after events, route records, or handle deletes.

### Before Choosing FULL

- Check what primary key/replica identity the connector requires.
- Confirm the output plugin emits the old tuple under that mode.
- Check behavior with TOAST columns.
- Measure WAL/network/decoder throughput.
- Determine whether the downstream schema has a stable key.

A connector supporting FULL does not mean FULL is the optimal choice for every table.

## 42. Replica Identity and Logical Slots

Logical replication slots retain WAL needed by consumers. If a consumer falls behind, WAL retention grows. Using FULL can increase WAL volume in update/delete-heavy workloads, increasing pressure on slot retention.

Monitor:

```sql
SELECT
    slot_name,
    plugin,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    pg_size_pretty(
        pg_wal_lsn_diff(
            pg_current_wal_lsn(),
            restart_lsn
        )::bigint
    ) AS retained_wal_distance
FROM pg_catalog.pg_replication_slots
WHERE slot_type = 'logical';
```

LSN distance is an estimate in WAL address space, not exact disk usage of that slot alone. Combine it with pg_wal directory size and consumer metrics.

## 43. Performance Checklist

When evaluating replica identity:

- Few and small identity columns.
- Identity columns are NOT NULL.
- Unique key is stable according to business semantics.
- Subscriber has an appropriate index for lookups.
- Avoid FULL on large/write-heavy tables if a key can be created.
- Do not use partial/nullable/deferrable unique indexes.
- Column lists include all identity columns.
- CDC connectors understand the key schema.
- WAL rate/slot lag is measured before and after.

## 44. Monitoring Replica Identity Issues

Monitor:

- Publisher logs for replica identity errors.
- Subscription worker errors and apply lag.
- Logical slot restart_lsn/confirmed_flush_lsn.
- WAL bytes/s before and after identity changes.
- Per-table update/delete rates.
- Subscriber table row counts/key consistency.
- Duplicate/unique constraint violations.

### Checking Subscription Status

```sql
SELECT
    subname,
    pid,
    relid::regclass AS table_name,
    received_lsn,
    last_msg_send_time,
    last_msg_receipt_time,
    latest_end_lsn,
    latest_end_time
FROM pg_catalog.pg_stat_subscription;
```

The view schema may differ across major versions. Inspect apply worker error logs to identify the exact failing transaction/table/key when replication stops.

## 45. Troubleshooting: cannot update table because it does not have a replica identity

This error commonly appears when a publication emits update/delete but the table lacks an appropriate identity.

Procedure:

1. Identify the table and publication.
2. Check psql \d+ table or relreplident.
3. Inspect primary keys/unique indexes.
4. Choose DEFAULT, USING INDEX, or FULL.
5. Verify the publication column list.
6. Test a controlled update/delete.
7. Check the subscriber apply worker.

Example temporary mitigation:

```sql
ALTER TABLE public.legacy_customer
REPLICA IDENTITY FULL;
```

This can increase WAL volume. Use it as a temporary measure when necessary and plan to create a stable identity key if appropriate for the workload.

## 46. Troubleshooting: cannot use index as replica identity

Check:

- Is the index unique?
- Is it a partial index?
- Is it deferrable?
- Are all key columns NOT NULL?
- Is the index valid/ready?
- Does the index belong to the right table?
- Does the index have incompatible expression/include semantics?

Do not rely solely on the index name or UNIQUE in DDL. Use pg_index, pg_attribute, and pg_get_indexdef to verify.

## 47. Troubleshooting: subscriber row not found

If apply reports that a row was not found for update/delete:

1. Read the table/key from the error log.
2. Query the corresponding row on both publisher and subscriber.
3. Check whether the subscriber received direct writes.
4. Check initial copy/table synchronization.
5. Check row filter/publication changes.
6. Reconcile data or resynchronize the table.
7. Resume the subscription and confirm LSN advances.

Do not skip a failing transaction before knowing what data has diverged.

## 48. Troubleshooting: duplicate key on subscriber

If update/insert causes a duplicate key:

- Identify which unique constraint was violated.
- Find the conflicting row on the subscriber.
- Check for direct writes or multi-writer design.
- Compare schemas/constraints on both sides.
- Reconcile according to business rules.
- Resume apply only once data state is consistent.

Replica identity helps locate the old row; it does not prevent the subscriber from having conflicting new data.

## 49. Troubleshooting: WAL grows after enabling FULL

If WAL bytes increase noticeably:

1. Compare update/delete workloads before/after.
2. Confirm which tables were switched to FULL.
3. Measure row width and TOAST usage.
4. Check logical slot lag and retained WAL.
5. Check decoder/network throughput.
6. Build a unique key/index if business data permits.
7. Switch to USING INDEX or DEFAULT.
8. Re-measure under the same workload.

Do not switch back to NOTHING if the publication still requires update/delete.

## 50. Troubleshooting: publication column list missing identity

If a publication change is rejected or update/delete fails to work:

- Identify identity columns on the publisher.
- Read the column list in pg_publication_tables.
- Add all identity columns to the publication.
- Ensure the subscriber has corresponding columns.
- Test update/delete and verify apply.

## 51. INSERT-Only Tables and Event Sourcing

Some event/audit tables are designed to be append-only. If the application does not update/delete and the publication only needs inserts, you can configure:

```sql
CREATE PUBLICATION event_only_pub
FOR TABLE public.event_log
WITH (publish = 'insert');

ALTER TABLE public.event_log
REPLICA IDENTITY NOTHING;
```

This is a valid design when semantics are genuinely append-only. If the application runs a cleanup job executing DELETE, those deletes will not be sent via an insert-only publication; downstream retention/cleanup must be decided consistently.

## 52. Replica Identity in Multi-Table Publications

A publication containing multiple tables:

```sql
CREATE PUBLICATION app_pub
FOR TABLE public.customer, public.orders, public.order_items;
```

Each table has its own replica identity. One table having a PK does not protect all tables in the publication. Inspect all published tables:

```sql
SELECT
    pt.schemaname,
    pt.tablename,
    c.relreplident
FROM pg_catalog.pg_publication_tables AS pt
JOIN pg_catalog.pg_namespace AS n
  ON n.nspname = pt.schemaname
JOIN pg_catalog.pg_class AS c
  ON c.relnamespace = n.oid
 AND c.relname = pt.tablename
WHERE pt.pubname = 'app_pub'
ORDER BY pt.schemaname, pt.tablename;
```

If the same table name exists in multiple schemas, the query above still joins by namespace/table name and avoids matching the wrong object.

## 53. Testing Replica Identity in a Lab

Create a publisher table without a PK:

```sql
CREATE TABLE public.identity_demo (
    external_id TEXT NOT NULL,
    description TEXT NOT NULL,
    quantity INTEGER NOT NULL
);

INSERT INTO public.identity_demo
VALUES ('A-1', 'first', 10);
```

Create a unique index and set identity:

```sql
CREATE UNIQUE INDEX identity_demo_external_id_uq
ON public.identity_demo (external_id);

ALTER TABLE public.identity_demo
REPLICA IDENTITY USING INDEX identity_demo_external_id_uq;
```

Create a publication/subscription in the lab environment, then test:

```sql
UPDATE public.identity_demo
SET quantity = 20
WHERE external_id = 'A-1';

DELETE FROM public.identity_demo
WHERE external_id = 'A-1';
```

Verify the subscriber receives the update/delete accurately. Then test on a table with REPLICA IDENTITY NOTHING in a publication emitting update/delete to observe the error and logs.

## 54. Lab: FULL vs. Unique Index

Create two wide-row tables, one using USING INDEX and the other using FULL. Run equivalent update/delete workloads.

Record:

- pg_stat_wal.wal_bytes before/after.
- Logical slot retained distance.
- Publisher CPU.
- Subscriber apply throughput.
- Network bytes.
- Transaction latency.

### Results to Analyze

Do not compare total WAL bytes alone. Normalize by number of updated/deleted rows and keep row payload/workload identical. Identify whether FULL adds cost primarily on the publisher, network, or subscriber lookup.

## 55. Replica Identity and Initial Table Copy

Initial table synchronization copies existing rows from publisher to subscriber. Replica identity is specifically required for subsequent changes; initial copy does not replace configuring identity for ongoing changes.

When creating a subscription:

1. Confirm table schemas/columns are compatible.
2. Confirm replica identity before update/delete workloads run.
3. Verify initial copy completes.
4. Confirm table synchronization state.
5. Run an update/delete test after initial copy.

If the publisher emits changes during table sync, PostgreSQL coordinates snapshot/catch-up via the replication protocol. Do not manually copy CSV files into the subscriber and assume replication state is synchronized.

## 56. DDL and Replica Identity Do Not Replicate Automatically

Built-in logical replication does not automatically replicate all DDL. If you add a primary key/index on the publisher, deploy the corresponding change on the subscriber per your migration plan.

### Common Migration Order

1. Add columns/constraints/indexes on the subscriber safely.
2. Backfill data if needed.
3. Verify uniqueness/nullability on both sides.
4. Create a valid unique index on the publisher.
5. Switch replica identity.
6. Test update/delete.
7. Remove old structures once confirmed unused.

If schema changes run during a rolling deployment, control when the application starts writing new values to avoid mismatches.

## 57. Replica Identity and Bidirectional/Multi-Writer

Unidirectional logical replication generally assumes the publisher is the primary writer for replicated tables. If writes are allowed on both sides, issues can arise:

- The same key inserted on both sides.
- One side updates while the other side deletes.
- Different key values for the same logical entity.
- Apply conflicts and transaction failures.

Replica identity is not a conflict resolution system. Multi-writer setups require dedicated architecture: key allocation, conflict detection/resolution, write ownership/partitioning, and loop prevention.

## 58. Protecting Replica Identity in Schema Design

When designing a new table that will be published:

- Choose a stable primary key.
- Enforce NOT NULL and uniqueness.
- Avoid using mutable business attributes as identity if a good surrogate key exists.
- Do not use nullable unique keys as replica identity.
- Keep identity columns in publication column lists.
- Create matching keys/indexes on the subscriber.
- Test delete/update/primary key changes.

Surrogate keys like BIGINT identity or UUID often provide stable row identification. However, key type selection also depends on write distribution, index size, application semantics, and ID generation policy.

## 59. Checklist Before Enabling UPDATE/DELETE Publication

### Publisher

- wal_level=logical.
- Table has a primary key or suitable replica identity index/FULL.
- Publication enables the right operations.
- Column list contains identity columns.
- Row filter tested against old/new row transitions.
- Replication slot and WAL retention monitored.

### Subscriber

- Schema and data synchronized.
- Identity columns exist with compatible types.
- Suitable index exists for lookups when needed.
- No unauthorized direct writes.
- Constraints do not cause unexpected conflicts.
- Apply worker active.

### Operations

- Update/delete tests pass.
- Apply lag and logs monitored.
- Migration/rollback plan documented.
- Reseed/resync procedure documented.

## 60. Runbook: Enabling UPDATE/DELETE for a New Table

1. Identify the relevant publication and subscription.
2. Check whether the table has a primary key.
3. If no PK exists, identify a candidate unique key.
4. Clean up duplicates/NULLs.
5. Create an eligible unique index.
6. Create the corresponding index/schema on the subscriber.
7. Configure REPLICA IDENTITY DEFAULT or USING INDEX.
8. Ensure the publication column list includes identity columns.
9. Confirm subscriber initial copy/sync has completed.
10. Run an update/delete test.
11. Monitor publisher logs, subscription worker, and slot lag.
12. Open production workload according to the rollout plan.

## 61. Runbook: Table Without Identity Needing Update Replication

1. Assess urgency and update/delete volume.
2. Check whether a stable primary key can be added.
3. If not immediately possible, look for an eligible unique index.
4. If no candidate exists, consider FULL.
5. Measure row width/WAL/CPU/network/apply impact.
6. Verify equality support for data types.
7. Test subscriber row lookups and deletes.
8. Deploy temporarily with monitoring/rollback.
9. Plan migration to a stable key.
10. Do not use NOTHING when update/delete must be published.

## 62. Runbook: Apply Worker Fails Because Row Does Not Exist

1. Record subscription/table/key and the failing transaction.
2. Inspect the row on the publisher.
3. Inspect the row on the subscriber.
4. Check for direct subscriber writes and row filters.
5. Check initial copy/sync state.
6. Reconcile the table/key with the business owner.
7. Verify constraints/indexes.
8. Resume the subscription.
9. Monitor LSN/apply lag.
10. Identify the root cause to prevent recurring divergence.

## 63. Runbook: WAL Increases After Switching to FULL

1. Identify the table and timestamp of the replica identity change.
2. Compare WAL bytes before/after under an equivalent workload.
3. Measure update/delete rates and row width.
4. Inspect TOAST payloads.
5. Check logical slot lag/retained WAL.
6. Evaluate network and subscriber apply throughput.
7. Build a unique key/index if possible.
8. Switch to USING INDEX/DEFAULT.
9. Re-measure and verify CDC event compatibility.
10. Keep FULL if no safe alternative identity exists yet.

## 64. Practice Exercises

### Exercise 1 — Purpose of Replica Identity

Why does logical replication need old-row identity for UPDATE and DELETE, yet does not need it to locate an old row for INSERT?

### Exercise 2 — Four Modes

Compare DEFAULT, USING INDEX, FULL, and NOTHING in terms of old-row data sent, usage requirements, and cost.

### Exercise 3 — DEFAULT

A table has primary key customer_id. Explain which replica identity PostgreSQL selects when the table is in DEFAULT mode.

### Exercise 4 — No Primary Key

A table has an email column without a uniqueness constraint. Why can PostgreSQL not automatically use email as replica identity?

### Exercise 5 — Composite Key

An order_items table has primary key (order_id, line_no). Which values are used to locate the old row during DELETE?

### Exercise 6 — USING INDEX

Create a unique index on external_ref TEXT NOT NULL and configure it as replica identity. Write the SQL and explain the requirements.

### Exercise 7 — Nullable Unique Index

A unique index allows NULL. Why is it ineligible as replica identity? Outline a migration to safely make the column NOT NULL.

### Exercise 8 — Partial Index

A partial unique index applies only to active users. Why can that index not identify every row in the table?

### Exercise 9 — Deferrable Constraint

Explain why a deferrable unique constraint is unsuitable as replica identity.

### Exercise 10 — FULL

A legacy table has no key and must publish DELETE. Configure REPLICA IDENTITY FULL and list the performance risks.

### Exercise 11 — NOTHING

An event table only publishes INSERT. When is REPLICA IDENTITY NOTHING appropriate? What happens if the publication later enables DELETE?

### Exercise 12 — Updating Identity Column

The publisher changes external_ref from EXT-42 to EXT-43. Explain why the subscriber must receive the old identity EXT-42 before applying the new key.

### Exercise 13 — DELETE Missing Row

The subscriber does not have the row that the publisher just DELETEd. List causes of divergence and an investigation procedure.

### Exercise 14 — Subscriber Index

What role does the replica identity sent by the publisher play? Why should the subscriber still have an appropriate index for lookups?

### Exercise 15 — Publication Operations

Create an INSERT-only publication. State how it differs from a default publication that includes UPDATE/DELETE.

### Exercise 16 — Column List

A publication column list omits the primary key. Why does this fail to satisfy UPDATE/DELETE requirements? How should the column list be fixed?

### Exercise 17 — Row Filter

A row changes status from inactive to active in a publication with filter status='active'. Identify the old/new row cases that must be tested.

### Exercise 18 — FULL and Row Width

A table has 40 columns, large JSONB, and a BIGINT primary key. Compare old-row payload sizes between DEFAULT and FULL.

### Exercise 19 — TOAST

Explain why FULL can enlarge WAL/decoder payloads when large text/jsonb/bytea columns exist.

### Exercise 20 — Unique Index Inspection

Write a query using pg_index/pg_class to check unique, partial, valid flags, and index definitions.

### Exercise 21 — Column Nullability

Use pg_attribute and pg_index to determine whether the key columns of a candidate index are NOT NULL.

### Exercise 22 — Primary Key Inspection

Query pg_constraint to list primary keys and definitions for all tables in schema public.

### Exercise 23 — Index Drop

An index is currently used as replica identity. Why might DROP INDEX be rejected? What is the sequence to switch identity before dropping?

### Exercise 24 — FULL Performance Test

Design a benchmark comparing WAL bytes, CPU, network, and subscriber apply lag between FULL and USING INDEX.

### Exercise 25 — Logical Slots

Why can FULL cause a logical slot to retain more WAL when a consumer is slow? Write a query to check restart_lsn and confirmed_flush_lsn.

### Exercise 26 — Partitioned Table

A publication publishes a partitioned parent. What should be checked on root/leaf partitions regarding replica identity and unique indexes?

### Exercise 27 — DDL Migration

Add a primary key to a large published table. Design a migration covering backfill, index build, subscriber schema, and rollout.

### Exercise 28 — CREATE INDEX CONCURRENTLY

Why is concurrent index creation useful on large tables? List the states to verify before using it as replica identity.

### Exercise 29 — Primary Key Update

An update changes a primary key and the subscriber already has a row with the new key. Explain the conflict and how to investigate.

### Exercise 30 — Multi-Table Publication

A publication has 20 tables. Write a query listing the replica identity mode of each table and explain how to detect tables lacking an identity.

### Exercise 31 — CDC Connector

A CDC connector requires before/after events. Identify how replica identity affects payloads and what tests are needed for TOAST.

### Exercise 32 — wal_level

Explain why logical replication requires wal_level=logical and whether this setting requires a restart.

### Exercise 33 — Subscriber Direct Writes

An application writes directly to the subscriber and deletes a row. When the publisher sends DELETE, what can happen? Propose a write ownership policy.

### Exercise 34 — Unique Conflict

The old row is found on the subscriber, but the new value violates a unique constraint. Why is this not a replica identity error? How should it be handled?

### Exercise 35 — Initial Table Copy

Why does a successful initial copy not prove that subsequent updates/deletes can replicate? What checks should be performed after sync?

### Exercise 36 — Temporary FULL

Design a plan to use FULL temporarily for a legacy table, then switch to a unique index. How do you avoid any window without an identity?

### Exercise 37 — Multi-Writer

Two publishers write to the same logical entity. Why does replica identity not resolve conflicts? Design the layers needed for multi-writer.

### Exercise 38 — Apply Worker Errors

A subscription stops due to row not found. Write a runbook to identify table/key, reconcile data, and resume safely.

### Exercise 39 — WAL Spike

After switching 10 tables to FULL, WAL triples. Design metrics and a plan to transition back to key indexes where possible.

### Exercise 40 — Designing Logical Replication

A system has:

- Table customer with 100 million rows, customer_id BIGINT PK.
- Table legacy_event with 500 million rows, no PK, large row width.
- Table account with unique email, but email is currently nullable.
- A publication restricting columns sent to analytics.
- A CDC connector requiring before/after images.
- A read-only subscriber, though a batch job still writes directly to the subscriber.

Design:

1. Replica identity mode for each table.
2. Handling legacy_event and evaluating FULL cost.
3. Safe migration of nullable email to a unique identity.
4. Publication column lists containing all identity columns.
5. Subscriber schema/indexes and write ownership.
6. CDC event format and TOAST tests.
7. Monitoring WAL bytes, slot lag, and apply errors.
8. UPDATE/DELETE and key change testing.
9. Rollout/rollback sequence.
10. Runbook when the subscriber cannot find the old row or encounters a unique conflict.

## Conclusion

**Replica identity tells PostgreSQL what old-row information to send when logical replication processes UPDATE or DELETE.** DEFAULT uses the primary key and is usually the best choice. USING INDEX allows using a valid unique index when no primary key exists. FULL sends the entire old row, which can increase WAL, network, decoder, and subscriber lookup costs. NOTHING is only appropriate when UPDATE/DELETE replication is not needed for the table.

A good identity must be stable, unique, non-NULL, and backed by an appropriate index. A unique index used as replica identity cannot be partial or deferrable, and key columns must be NOT NULL. Publication column lists must retain identity columns; row filters and partitioning must be verified against the semantics of your PostgreSQL version.

The publisher determines the emitted old-row identity; the subscriber must have a compatible schema and consistent data to locate the row and apply the change. Direct subscriber writes, incomplete initial copies, or skewed migrations can lead to row-not-found/unique-conflict errors. Replica identity does not automatically synchronize DDL and is not a mechanism for resolving multi-writer conflicts.

Finally, test every table publishing UPDATE/DELETE, validate identity/key changes in staging, and monitor WAL bytes, logical slot lag, and apply worker errors. **Choosing a stable row key right from schema design usually makes logical replication simpler, more efficient, and easier to operate.**
