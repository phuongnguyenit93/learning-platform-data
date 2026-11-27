# Publication, Subscription, and Data Scope in PostgreSQL

Logical replication allows PostgreSQL to stream row-level data changes from a source database (publisher) to a target database (subscriber). The two central components of this mechanism are **publication** and **subscription**:

- **Publication** defines which tables and types of changes the publisher provides.
- **Subscription** defines which publisher is connected, which publications are received, and how the subscriber synchronizes data.

Data scope can be restricted by table, schema, row (row filter), and column (column list). Therefore, logical replication fits problems such as syncing a group of tables, isolating data by tenant, feeding data to an analytics system, or migrating parts of a database.

However, logical replication has clear boundaries. It replicates DML changes permitted by the publication; it does not automatically synchronize all DDL, roles, extensions, sequence states, or database configurations. The subscriber must have a compatible schema and needs a separate plan for components outside the publication scope.

~~~mermaid
flowchart LR
    A["Publisher database"] --> B["Publication"]
    B --> C["WAL logical decoding"]
    C --> D["Logical replication stream"]
    D --> E["Subscription"]
    E --> F["Initial table sync"]
    E --> G["Apply worker"]
    F --> H["Subscriber tables"]
    G --> H
~~~

This lesson belongs to the **Logical Replication** chapter, **Database Engine Relational PostgreSQL** module. We will cover publications, subscriptions, published operations, table/schema scope, row filters, column lists, replica identity, initial table synchronization, replication slots, partitioning, and how to monitor synchronization.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the roles of publisher, publication, subscriber, and subscription.
2. Distinguish logical replication from physical streaming replication.
3. Create a publication for one or multiple tables.
4. Create a publication for all tables or tables within a schema.
5. Select INSERT, UPDATE, DELETE, and TRUNCATE operations.
6. Use a row filter to restrict published rows.
7. Use a column list to restrict published columns.
8. Understand replica identity and requirements for UPDATE/DELETE.
9. Create a subscription and understand the initial table synchronization process.
10. Distinguish copy_data true and false.
11. Refresh a subscription when a publication changes.
12. Manage replication slots on the publisher.
13. Understand limitations regarding DDL, sequences, large objects, and global objects.
14. Handle partitioned tables and publication scope.
15. Monitor apply/sync status using system views.
16. Diagnose permission errors, schema mismatches, duplicate rows, and apply conflicts.
17. Design a data scope aligned with workload and security requirements.
18. Build a deployment, testing, and operations checklist for logical replication.

## 2. Logical Replication Architecture

Logical replication transmits data changes by SQL semantics, such as a row being INSERTed, UPDATEd, or DELETEd. The publisher uses WAL and logical decoding to produce a change stream. The subscriber receives the stream and applies it to the corresponding tables.

Components:

| Component | Role |
| --- | --- |
| Publisher | Source database emitting changes |
| Publication | Set of tables and operations allowed to be published |
| Logical decoding | Converts WAL into logical changes |
| Replication slot | Tracks consumer progress and retains necessary WAL |
| Subscription | Configuration for connecting and receiving publications |
| Initial table sync | Copies existing data at startup |
| Apply worker | Continuously applies changes on the subscriber |

A publisher can have multiple publications. A subscriber can create multiple subscriptions. A subscription can receive one or more publications from the same publisher database.

### Example

Suppose a sales system has a source database sales_prod and a reporting database sales_analytics.

- Publisher: sales_prod.
- Publication: sales_reporting_pub.
- Subscriber: sales_analytics.
- Subscription: sales_reporting_sub.

The publication includes only the customers and orders tables in the stream. The subscriber creates the corresponding tables and receives initial data, then applies new changes.

Logical replication is not a default multi-master mechanism. Having multiple nodes write to the same data requires dedicated conflict-handling design; do not assume PostgreSQL automatically resolves conflicts like a multi-master distributed database.

## 3. What Is a Publication?

A publication is an object in the publisher database defining the set of changes that the publisher makes available to subscribers.

A publication can include:

- A specific table.
- Multiple tables.
- All eligible tables in the database.
- Tables belonging to a schema, on supported versions.
- INSERT, UPDATE, DELETE, and TRUNCATE operations.
- Row filters and column lists, depending on publication type and version.

A publication is not a copy of a table and does not store published data. It is metadata describing the scope of changes being published.

### Which Database Does a Publication Belong To?

A publication is a database-level object. It is created in the source database and does not automatically appear in other databases in the same cluster.

Example:

~~~sql
CREATE PUBLICATION sales_pub
FOR TABLE public.customers, public.orders;
~~~

The command must be run inside the publisher database containing those tables.

### Publications Do Not Create Tables on the Subscriber

A publication only declares what data is emitted. The subscriber needs corresponding tables with a compatible schema, except that initial table synchronization can load rows into existing tables. Logical replication does not automatically deploy all schema DDL to the subscriber.

## 4. What Is a Subscription?

A subscription is an object in the subscriber database that stores publisher connection information, names of publications to receive, and replication state.

A subscription defines:

- Publisher connection string.
- One or more publication names.
- Whether the subscription is enabled.
- Whether to create a replication slot on the publisher.
- Whether to copy initial data.
- Slot name and certain apply/streaming options depending on version.

Example:

~~~sql
CREATE SUBSCRIPTION sales_sub
CONNECTION 'host=publisher.example.net port=5432 dbname=sales_prod user=logical_repl sslmode=verify-full'
PUBLICATION sales_pub;
~~~

In the example, the subscriber connects to the sales_prod database on the publisher and receives the sales_pub publication.

### Subscriptions Do Not Hold Data

A subscription is orchestration configuration. Data is loaded into subscriber tables; the replication slot on the publisher tracks the logical consumer's progress.

If a subscription is disabled, new changes may continue accumulating in WAL/slots depending on state. When re-enabled, the subscriber may need to apply the backlog; if the slot is lost or WAL is gone, a recovery procedure is needed.

## 5. Distinguishing Publication and Subscription

| Criterion | Publication | Subscription |
| --- | --- | --- |
| Where it resides | Publisher database | Subscriber database |
| Role | Defines data/changes to publish | Defines source and publications to receive |
| Contains connection string | No | Yes |
| Contains table list | Yes | Tracks synchronized relation membership |
| Has replication slot | Not directly | Usually creates/controls slot on publisher side |
| Has apply worker | No | Yes |
| Has initial copy | No | Can execute during creation/refresh |

One publication can be used by multiple subscribers. Each subscription typically has its own replication slot so the publisher tracks each consumer's progress independently.

## 6. Published Operations

A publication can select which operations to publish:

- INSERT
- UPDATE
- DELETE
- TRUNCATE

Example:

~~~sql
CREATE PUBLICATION orders_insert_only
FOR TABLE public.orders
WITH (publish = 'insert');
~~~

The publication emits only INSERTs for the orders table.

By default, a publication created normally publishes INSERT, UPDATE, DELETE, and TRUNCATE operations. Specify the option explicitly when you want to control the scope.

Example publishing only insert/update/delete:

~~~sql
CREATE PUBLICATION orders_dml_pub
FOR TABLE public.orders
WITH (publish = 'insert, update, delete');
~~~

### TRUNCATE Requires Attention

If a publication includes TRUNCATE, a TRUNCATE command on the publisher can be sent to the subscriber. A row filter does not turn TRUNCATE into a conditional row-by-row deletion. Therefore, a subscriber containing local data outside the synchronized dataset can be affected when receiving TRUNCATE.

If you do not want TRUNCATE emitted, exclude it from the publish option.

### There Is No SELECT Publication

SELECT is not a data change and is not a publish operation. A publication is not a remote query mechanism or read-through cache; the subscriber stores synchronized data for local querying.

## 7. Creating a Publication for a Table

Example:

~~~sql
CREATE PUBLICATION customers_pub
FOR TABLE public.customers;
~~~

Creating a publication for multiple tables:

~~~sql
CREATE PUBLICATION sales_core_pub
FOR TABLE
    public.customers,
    public.orders,
    public.order_items;
~~~

If you want to add a table later:

~~~sql
ALTER PUBLICATION sales_core_pub
ADD TABLE public.products;
~~~

Remove a table:

~~~sql
ALTER PUBLICATION sales_core_pub
DROP TABLE public.products;
~~~

Replace the table list:

~~~sql
ALTER PUBLICATION sales_core_pub
SET TABLE
    public.customers,
    public.orders,
    public.order_items;
~~~

Syntax and options vary by major version; check the documentation for your exact server version.

### Is a Newly Added Table Immediately Copied to the Subscriber?

No. Changing the publication on the publisher does not automatically complete updating relation membership and copying data on the subscriber. The subscription needs to refresh the publication to discover new tables and possibly run initial table synchronization.

## 8. Publication for All Tables

You can create a publication for all eligible tables in a database:

~~~sql
CREATE PUBLICATION all_tables_pub
FOR ALL TABLES;
~~~

This publication has a broad scope. Creating FOR ALL TABLES has special privilege requirements, typically superuser; check your version's documentation and system policies.

### When to Use FOR ALL TABLES?

- A subscriber needs a copy of nearly the entire database.
- Centrally managed environment with controlled scope.
- You want to automatically include many tables without managing each table individually.

### Risks

- May inadvertently publish sensitive data.
- Newly created eligible tables can enter the publication scope.
- The subscriber needs appropriate schemas and privileges for new tables.
- Cannot apply per-table row filters/column lists like a standard table-list publication.
- Broad scope makes data minimization harder to control.

If you only need a subset of tables, an explicit publication is usually easier to review.

## 9. Schema-Level Publication

On PostgreSQL versions supporting schema-level publications (starting from PostgreSQL 15), you can use:

~~~sql
CREATE PUBLICATION finance_schema_pub
FOR TABLES IN SCHEMA finance;
~~~

This includes eligible tables in the specified schema. You can add or remove schemas using corresponding ALTER PUBLICATION commands depending on version.

Example:

~~~sql
ALTER PUBLICATION finance_schema_pub
ADD TABLES IN SCHEMA reporting;
~~~

### Does a Schema Publication Automatically Publish DDL?

No. It determines which tables belonging to the schema are included in the publication. Creating a new table on the publisher does not automatically run CREATE TABLE on the subscriber. The corresponding schema must be deployed on the subscriber; the subscription needs to refresh membership when required.

### When to Use Schema-Level Publication?

- Tables in the schema share the same data policy.
- Schemas are used as business boundaries.
- New tables in the schema should be added to the publication via a refresh workflow.
- Different row filters/column lists per table are not required.

Do not use a schema publication if a schema contains both sensitive data and shareable data without a clear scoping plan.

## 10. What Is a Row Filter?

A row filter is a WHERE condition attached to a table in a publication to restrict which rows are published.

Example publishing only completed orders:

~~~sql
CREATE PUBLICATION completed_orders_pub
FOR TABLE public.orders
WHERE (status = 'completed');
~~~

A row filter lets the subscriber receive only part of the source table's data.

### Example by Tenant

~~~sql
CREATE PUBLICATION tenant_42_pub
FOR TABLE public.orders
WHERE (tenant_id = 42);
~~~

This publication restricts orders rows to those with tenant_id equal to 42.

If there are many tenants, you can create separate publications based on data policy, or design a separate pipeline. Account for operational overhead, number of subscriptions, and replication slots.

### Where Does the Row Filter Execute?

The condition is evaluated on the publisher when determining changes to emit. The subscriber receives changes that passed the publication condition; the subscriber does not re-evaluate the entire source table itself.

A row filter is not a general SQL authorization mechanism. Users with access to the publisher remain subject to PostgreSQL privileges on the publisher; subscriber users can read replicated data according to permissions on the subscriber.

## 11. Row Filter Limitations and Semantics

Row filters have important limitations:

- The condition must reference columns of the corresponding table.
- Not all SQL expressions are accepted; functions/operators must meet PostgreSQL volatility requirements.
- Row filters for UPDATE/DELETE have limitations related to replica identity.
- Row filters do not filter TRUNCATE operations.
- Row filters do not automatically resynchronize existing data just because the expression changed.

### UPDATE and DELETE

For UPDATE, the row filter condition is evaluated against the new row version; for DELETE, the condition is evaluated against the old row. Consequently, when a row crosses the filter boundary, the subscriber may not automatically end up in the same state as the result of a SELECT query re-running the entire condition.

Example: an order previously had status completed, and then the publisher changes status to cancelled. If the new UPDATE no longer satisfies the filter, the change may not be sent under the current condition, while the subscriber still retains the previous completed version.

Conversely, a row that was previously outside the published set and later transitions into satisfying the condition must also be carefully designed and tested; do not assume a row filter automatically acts like a full refresh.

If the subscriber must always reflect the exact current set of rows for a mutable predicate, design a backfill/reconciliation process or use another suitable pipeline.

### Columns Used in a Row Filter

For UPDATE/DELETE, the publisher needs to evaluate the condition on row identity. PostgreSQL restricts using columns in a row filter when the replica identity does not include those columns. If the filter uses a mutable column, check your version's rules and design an appropriate replica identity.

## 12. What Is a Column List?

A column list restricts the columns published for a table. This feature is supported in modern PostgreSQL versions (starting from PostgreSQL 15).

Example:

~~~sql
CREATE PUBLICATION customer_public_fields
FOR TABLE public.customers (customer_id, display_name, city);
~~~

The subscriber receives only the columns in that list per the publication definition.

### Why Use a Column List?

- Exclude columns containing data that does not need to be shared.
- Reduce transmitted data volume.
- Limit data scope for downstream systems.
- Separate business data from PII or secret columns.
- Allow the subscriber to have a schema focused on a specific use case.

### Identity Columns Must Be Considered

If the publication emits UPDATE or DELETE, the subscriber must receive enough information to identify the updated/deleted row. The column list must be compatible with replica identity requirements. In practice, it usually needs to include the primary key or replica identity columns.

Example:

~~~sql
CREATE PUBLICATION customer_changes_pub
FOR TABLE public.customers
    (customer_id, display_name, city, updated_at)
WITH (publish = 'insert, update, delete');
~~~

Here customer_id is included in the list so the subscriber can identify the row if it serves as the appropriate replica identity.

### A Column List Is Not Complete Column Masking

It restricts columns in the logical replication stream. It does not automatically remove columns from the publisher or subscriber tables, nor does it replace access controls on the subscriber. If the subscriber table has additional columns, those columns can be kept locally with appropriate schemas and defaults/nullability.

## 13. Combining Row Filters and Column Lists

You can combine both scopes:

~~~sql
CREATE PUBLICATION tenant_42_orders_pub
FOR TABLE public.orders
    (order_id, tenant_id, customer_id, status, total_amount)
    WHERE (tenant_id = 42);
~~~

Result:

- Only the orders table.
- Only rows where tenant_id equals 42.
- Only the listed columns.
- Published operations determined by the publication's publish option.

Exact syntax and combinability should be confirmed against your major version. Column lists and row filters were introduced in PostgreSQL 15; schema-level publications are also supported starting in this version.

### When Is Combining Useful?

- A subscriber only needs a single tenant.
- A data warehouse only needs certain fields.
- A downstream service does not need sensitive identifying data.
- Data synchronization by bounded context.

### Risks

If the filter/column list changes, you must evaluate existing data on the subscriber. Changing the publication definition does not automatically delete previously synchronized old rows or automatically populate all previously unpublished rows. A refresh, resnapshot, or reconciliation may be necessary.

## 14. Replica Identity and UPDATE/DELETE

Logical replication needs to know how to identify a row on the publisher so the subscriber can apply the corresponding UPDATE or DELETE.

By default, PostgreSQL uses the primary key as replica identity if present.

Check:

~~~sql
SELECT
    c.oid::regclass AS table_name,
    c.relreplident AS replica_identity
FROM pg_class AS c
WHERE c.oid = 'public.orders'::regclass;
~~~

The value d represents default; i is index; f is full; n is nothing.

### REPLICA IDENTITY DEFAULT

~~~sql
ALTER TABLE public.orders
REPLICA IDENTITY DEFAULT;
~~~

PostgreSQL uses the primary key if one exists.

### REPLICA IDENTITY USING INDEX

You can choose a suitable unique index:

~~~sql
ALTER TABLE public.orders
REPLICA IDENTITY USING INDEX orders_replica_key;
~~~

The index must satisfy PostgreSQL requirements regarding uniqueness, non-partiality, and required columns.

### REPLICA IDENTITY FULL

If no suitable primary key/unique index exists:

~~~sql
ALTER TABLE public.orders
REPLICA IDENTITY FULL;
~~~

FULL stores/sends the entire old row information needed to identify changes. This can increase WAL size and require the subscriber to search rows across multiple columns; an appropriate index on the subscriber helps apply perform more efficiently.

### REPLICA IDENTITY NOTHING

NOTHING provides no row identity for UPDATE/DELETE. It is not suitable for publications needing to emit those operations; you can restrict the publication to INSERT only or choose a different replica identity.

## 15. INSERT-Only Publications and Tables Without a Primary Key

If a table has no primary key, but the publication emits only INSERT:

~~~sql
CREATE PUBLICATION audit_append_pub
FOR TABLE public.audit_events
WITH (publish = 'insert');
~~~

Replica identity for UPDATE/DELETE may not be needed because those operations are not published.

If you later add UPDATE/DELETE to the publication, you must review replica identity and verify existing data. Do not assume the subscriber can apply UPDATE/DELETE based merely on physical row location.

## 16. Creating a Subscription

On the subscriber, first create compatible tables/schemas. Then:

~~~sql
CREATE SUBSCRIPTION sales_sub
CONNECTION 'host=publisher.example.net port=5432 dbname=sales_prod user=logical_repl sslmode=verify-full'
PUBLICATION sales_pub;
~~~

Common default behaviors include:

- The subscription is enabled.
- A publisher replication slot is created named after the subscription unless specified otherwise.
- Existing data of the publication's tables is copied.
- The apply worker begins receiving changes after initialization.

Explicit options:

~~~sql
CREATE SUBSCRIPTION sales_sub
CONNECTION 'host=publisher.example.net port=5432 dbname=sales_prod user=logical_repl sslmode=verify-full'
PUBLICATION sales_pub
WITH (
    copy_data = true,
    create_slot = true,
    enabled = true
);
~~~

Options may vary by version; check CREATE SUBSCRIPTION for your server.

### Connection User on the Publisher

The role used in the connection string needs appropriate replication privileges and necessary access to published tables, especially during initial table synchronization. Verify SELECT and related privilege requirements per version, row filters, and table scope.

Do not grant superuser to the connection user merely to bypass a permission error. Identify the specific missing privilege and grant only the minimum required.

## 17. Preparing the Subscriber Schema

Logical replication does not automatically create schemas/tables on the subscriber from a publication. You must create the corresponding schema beforehand.

Example on the subscriber:

~~~sql
CREATE SCHEMA sales;

CREATE TABLE sales.customers (
    customer_id bigint PRIMARY KEY,
    display_name text,
    city text
);

CREATE TABLE sales.orders (
    order_id bigint PRIMARY KEY,
    customer_id bigint,
    status text,
    total_amount numeric(12,2)
);
~~~

The structure must be compatible with the publisher. Logical replication maps columns by name; column order can differ, but names and data types must be compatible with the replicated data.

The subscriber can have extra columns if those columns are supplied with default values or allow NULL, depending on the case. Do not rely on schema mismatch as a transformation mechanism.

### Schema Drift

If the publisher adds a column, the subscriber does not automatically run ALTER TABLE. Deploy DDL in the proper order:

1. Add a compatible column on the subscriber.
2. Add the column on the publisher and update the publication column list if used.
3. Refresh the subscription when metadata needs updating.
4. Verify the apply worker and data.
5. Only then change application logic that depends on the new column.

When dropping/renaming a column, coordinate both sides and the publication scope.

## 18. Initial Table Synchronization

When creating a subscription with copy_data = true, PostgreSQL performs initial table synchronization for tables selected by the publication.

General process:

1. The subscription is created and connects to the publisher.
2. Tables needing synchronization are identified.
3. Initial table sync workers copy existing data.
4. Changes occurring during the copy are tracked so none are lost.
5. After the copy completes, the apply worker continues streaming changes.
6. The subscription progresses to synchronized state.

With multiple tables, there can be multiple table sync workers, though count and scheduling depend on configuration/version.

### Initial Copy Is Not a Full Database Clone

It only copies tables included in the publication within the applied row/column scope. It does not automatically copy:

- Roles/global objects.
- DDL outside table data.
- Sequence state as a continuous synchronization mechanism.
- Extension binaries.
- Large objects in a comprehensive synchronized manner.
- Server configuration.

## 19. copy_data true and false

### copy_data = true

~~~sql
CREATE SUBSCRIPTION sales_sub
CONNECTION 'host=publisher.example.net dbname=sales_prod user=logical_repl'
PUBLICATION sales_pub
WITH (copy_data = true);
~~~

Existing table data is synchronized to the subscriber.

Use when:

- The subscriber is new and target tables are empty.
- You want PostgreSQL to orchestrate initial synchronization.
- There is no pre-verified copy of the data.

### copy_data = false

~~~sql
CREATE SUBSCRIPTION sales_sub
CONNECTION 'host=publisher.example.net dbname=sales_prod user=logical_repl'
PUBLICATION sales_pub
WITH (copy_data = false);
~~~

The subscription does not copy existing data upon creation. It receives changes occurring after startup per replication state.

Use when:

- The subscriber was already preloaded using another method.
- A separate baseline synchronization workflow exists.
- You want to avoid re-copying already prepared data.

### Risks of copy_data=false

If the subscriber is not truly identical to the publisher at the starting point, subsequent changes will not automatically fix all historical discrepancies. Rows may be missing, extra rows may exist, or sequence states may be wrong. You must establish a consistent starting point and verify data before enabling the subscription.

## 20. Refreshing a Publication

When a publication changes, the subscriber needs to update its list of subscribed tables.

Example:

~~~sql
ALTER SUBSCRIPTION sales_sub
REFRESH PUBLICATION;
~~~

You can control data copying for newly added tables:

~~~sql
ALTER SUBSCRIPTION sales_sub
REFRESH PUBLICATION
WITH (copy_data = false);
~~~

REFRESH PUBLICATION updates the subscription's relation membership to match the current publication. If new tables exist, PostgreSQL can spawn table sync to copy initial data according to the option.

### When Is a Refresh Needed?

- The publisher adds a table to the publication.
- The publisher removes a table from the publication.
- A schema publication gains new eligible tables.
- A publication definition changes and the subscriber needs to update relation metadata.
- Column/row filter changes need to be recognized by the subscriber per version semantics.

### Does Removing a Table from a Publication Delete the Subscriber Table?

No. Refreshing a publication updates the subscription so it stops receiving changes from that table; it does not automatically DROP TABLE on the subscriber. The table and its existing data remain until an administrator handles them separately.

This is an important point when changing data scope: stopping replication does not mean deleting previously synchronized data.

## 21. ALTER SUBSCRIPTION

Common management operations:

Pause:

~~~sql
ALTER SUBSCRIPTION sales_sub DISABLE;
~~~

Re-enable:

~~~sql
ALTER SUBSCRIPTION sales_sub ENABLE;
~~~

Change publication list:

~~~sql
ALTER SUBSCRIPTION sales_sub
SET PUBLICATION sales_pub, customer_pub;
~~~

Refresh:

~~~sql
ALTER SUBSCRIPTION sales_sub
REFRESH PUBLICATION;
~~~

Change connection:

~~~sql
ALTER SUBSCRIPTION sales_sub
CONNECTION 'host=publisher-new.example.net dbname=sales_prod user=logical_repl sslmode=verify-full';
~~~

Exact syntax and options depend on PostgreSQL major version. When changing publisher host/credentials, inspect replication slots on both old and new publishers to avoid orphaned slots or creating duplicate apply streams.

## 22. Publisher-Side Replication Slot

A subscription normally creates a logical replication slot on the publisher to retain WAL for the subscriber.

View slots:

~~~sql
SELECT
    slot_name,
    slot_type,
    database,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    wal_status
FROM pg_replication_slots
WHERE slot_type = 'logical'
ORDER BY slot_name;
~~~

The wal_status column and some other fields may depend on version.

### Why Is a Slot Needed?

The slot tells the publisher how far the consumer has confirmed. PostgreSQL retains necessary WAL so the subscriber can resume if temporarily disconnected.

### Risks of Inactive Slots

If a subscriber stops for a long time or a slot is abandoned:

- Necessary WAL may be retained.
- pg_wal can grow rapidly.
- The primary disk can fill up.
- Other workloads can be affected.

Monitor slot activity, confirmed_flush_lsn, restart_lsn, and WAL retention. Do not drop a slot merely because active = false; verify whether the subscription still needs the slot.

## 23. Dropping Subscriptions and Replication Slots

When dropping a subscription, PostgreSQL normally attempts to drop the associated replication slot on the publisher. This requires connectivity to the publisher and appropriate privileges.

Example:

~~~sql
DROP SUBSCRIPTION sales_sub;
~~~

If the publisher is unreachable and the subscription must be removed on the subscriber, you may need to disable the subscription, disassociate the slot following your version's procedure, and then drop the subscription; afterward, connect to the publisher and drop the orphaned slot separately.

Do not delete a slot while the subscriber still needs it to continue. Once a slot is dropped, its WAL retention guarantee ends and the subscriber may fail to catch up if needed WAL has been recycled.

## 24. Publications and DDL

Logical replication does not automatically replicate DDL such as:

- CREATE TABLE.
- ALTER TABLE.
- DROP TABLE.
- CREATE INDEX.
- ALTER TYPE.
- CREATE FUNCTION.
- CREATE EXTENSION.

DDL must be deployed separately on the subscriber in a compatible order.

### Example: Adding a Column

Publisher:

~~~sql
ALTER TABLE public.customers
ADD COLUMN loyalty_tier text;
~~~

The subscriber needs the corresponding column before the publisher starts sending row changes containing that column, depending on publication column lists and version behavior.

The safe procedure is typically to deploy compatible DDL on the subscriber first, then modify the publisher and publication. For complex schema migrations, use expand-and-contract:

1. Add a new nullable/appropriately defaulted column on the subscriber.
2. Add the column on the publisher.
3. Update publication scope.
4. Synchronize/backfill data.
5. Switch the application.
6. Remove the old column after no subscribers need it.

## 25. Sequences and Identity Columns

Logical replication replicates row changes, but sequence state is not continuously synchronized like a table stream.

If a table uses serial/identity:

- ID values are transmitted in row changes.
- Sequence objects and current values must be managed separately.
- The subscriber may have a sequence value lower than the maximum value in the data.
- If the subscriber is promoted or allowed to write, new inserts can cause duplicate keys if sequences have not been adjusted.

Before turning the subscriber into a write target, synchronize sequence state through a controlled procedure and stop/coordinate writes to avoid race conditions.

Do not treat logical replication as a complete copy of all database state.

## 26. Large Objects, Extensions, and Global Objects

Logical publications focus on table changes. Do not assume they synchronize:

- PostgreSQL large objects.
- Role definitions and memberships.
- Comprehensive database-level grants/ownership.
- Tablespace definitions.
- Extension binaries.
- Server configuration.
- DDL and object metadata outside the publication table stream.

If the application uses large objects, a separate copy/verify workflow is needed. If roles/extensions are needed, use configuration management or backup/restore global objects per policy.

## 27. Partitioned Tables

Logical replication supports partitioned tables, though publication scope and change representation depend on options.

Example:

~~~sql
CREATE PUBLICATION events_pub
FOR TABLE public.events;
~~~

If events is a partitioned table, the publisher can publish changes from partitions. The publish_via_partition_root option controls whether changes are emitted as the root partitioned table or leaf partitions, depending on version.

Example:

~~~sql
CREATE PUBLICATION events_pub
FOR TABLE public.events
WITH (publish_via_partition_root = true);
~~~

When publishing via root, the subscriber needs a table structure compatible with the root relation. If publishing via leaf partitions, the subscriber must have matching relation mappings for the partition tables.

### Choosing a Partition Strategy

- Want the subscriber to see a single logical table: consider publishing via the partition root.
- Want to preserve leaf partition mapping: verify partition structures on both sides.
- When attaching/detaching partitions, understand membership changes and publication behavior for your version.
- Test partition pruning, routing, and DDL migrations before production.

Do not assume a partitioned table is handled identically to a regular table in every publication configuration.

## 28. Publication Filters and Multiple Publications

A subscription can receive multiple publications from the same publisher database.

Example:

~~~sql
CREATE SUBSCRIPTION analytics_sub
CONNECTION 'host=publisher.example.net dbname=sales_prod user=logical_repl'
PUBLICATION orders_pub, customers_pub;
~~~

If the same table appears in multiple publications of a subscription, row filters and column lists must be understood according to PostgreSQL's merging rules. In many cases, rows are selected if they satisfy the filter of at least one publication containing that table (OR semantics), and column lists are combined across the published column scopes.

This can widen the data scope beyond expectations. When multiple publications overlap:

- Check which tables appear in multiple publications.
- Check each publication's filter.
- Check column lists.
- Evaluate publish operations.
- Test actual data on the subscriber.

Do not assume multiple publications automatically combine filters with AND logic.

## 29. Table Mapping and Column Names

Logical replication matches publisher/subscriber tables by schema/table identity managed by the subscription and maps columns by name.

Practical rules:

- The subscriber table must exist.
- Column names and types must be compatible.
- Column order can differ, because mapping is by name.
- Extra columns on the subscriber need defaults or must allow NULL if not supplied by the publisher.
- Columns excluded from the publication receive no values from the stream.
- Constraints on the subscriber can cause apply failures if data is incompatible.

If the publisher renames a column before the subscriber is updated, apply may fail or metadata may mismatch. DDL rollouts must be coordinated.

## 30. Apply Workers and Data Conflicts

The subscriber applies changes received from the publisher. If the subscriber has data written independently into the same tables, conflicts can occur:

- INSERT colliding on primary key.
- UPDATE failing to find the row.
- DELETE failing to find the row or encountering different data.
- Unique constraint violation.
- Foreign key violation.
- Type/schema mismatch.
- Triggers/constraints on the subscriber altering or rejecting data.

By default, logical replication does not provide a generic conflict resolution mechanism to merge bidirectional changes. The apply worker can stop on error and require administrator intervention.

### Best Practices

- Avoid writing directly to tables managed by a subscription.
- If subscriber-local data is needed, isolate it in separate schemas/tables.
- Ensure the publisher is the source of truth for replicated tables.
- Monitor logs and subscription stats.
- Design reconciliation if local writes are possible.
- Do not use a subscription as a multi-master solution.

## 31. Triggers and Constraints on the Subscriber

The logical replication apply worker has specific behavior regarding triggers. Regular triggers on the subscriber do not fire by default as they do for application DML; triggers configured appropriately such as ENABLE REPLICA or ENABLE ALWAYS can fire according to PostgreSQL semantics.

This must be verified if the subscriber relies on triggers to:

- Compute derived values.
- Write audit logs.
- Update secondary tables.
- Enforce business rules.

Constraints on the subscriber can still affect apply. A constraint incompatible with publisher data can cause the worker to fail. Do not disable constraints indiscriminately just to keep replication running; fix the schema or source data.

## 32. Monitoring Subscriptions

The pg_stat_subscription view shows worker status and receive progress:

~~~sql
SELECT
    subid,
    subname,
    pid,
    relid::regclass AS relation_name,
    received_lsn,
    latest_end_lsn,
    latest_end_time
FROM pg_stat_subscription
ORDER BY subname, relid;
~~~

Time/LSN columns and presentation may vary by version. There may be one row for the main apply worker and rows for table sync workers.

View subscription configuration:

~~~sql
SELECT
    subname,
    subenabled,
    subslotname,
    subpublications
FROM pg_subscription
ORDER BY subname;
~~~

The pg_subscription catalog contains sensitive connection information in other columns; do not SELECT or log connection strings containing secrets unnecessarily.

## 33. Monitoring Table Synchronization

The pg_subscription_rel catalog stores the synchronization state of each relation.

~~~sql
SELECT
    s.subname,
    r.srrelid::regclass AS relation_name,
    r.srsubstate,
    r.srsublsn
FROM pg_subscription_rel AS r
JOIN pg_subscription AS s
    ON s.oid = r.srsubid
ORDER BY s.subname, r.srrelid::regclass::text;
~~~

srsubstate indicates the synchronization phase of the relation. State characters and semantics are internal metadata; consult the catalog documentation for your exact version when analyzing deeply.

If a table stays in sync state for a long time, check the table sync worker, publisher load, network, and logs.

## 34. Monitoring the Publisher Side

On the publisher:

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication
ORDER BY application_name;
~~~

Logical replication connections can appear in replication sender statistics. Distinguish them from physical standbys using application name, slot, and connection metadata.

View logical slots:

~~~sql
SELECT
    slot_name,
    plugin,
    database,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
WHERE slot_type = 'logical'
ORDER BY slot_name;
~~~

An inactive slot or stagnant confirmed_flush_lsn may indicate the subscriber is not applying or not connected.

## 35. Subscription Error Statistics

On PostgreSQL versions providing pg_stat_subscription_stats, you can check:

~~~sql
SELECT *
FROM pg_stat_subscription_stats;
~~~

The view can include counts of apply errors, sync errors, and stats reset timestamps. Exact names/columns and access privileges depend on version.

Combine with:

- Publisher server logs.
- Subscriber server logs.
- pg_stat_subscription.
- pg_subscription_rel.
- pg_replication_slots.
- pg_stat_replication.

Do not just check subenabled = true and conclude replication is healthy. Workers can be repeatedly erroring or lagging heavily even while the subscription is enabled.

## 36. Handling Permission Denied Errors

Errors can arise when:

- The replication role lacks LOGIN/REPLICATION.
- HBA does not allow the connection source.
- The publisher user lacks read privileges on tables for initial copy.
- The subscriber user lacks privileges to create/write tables.
- Subscription owner/privileges are inappropriate.
- A row filter or object requires special permissions per version.

Check each side:

1. Verify the user in the connection string.
2. Check role attributes on the publisher.
3. Check HBA rules and source IP.
4. Check SELECT privilege on publisher tables when initial sync needs it.
5. Check create/write privileges on subscriber objects.
6. Inspect logs to identify the failing object and operation.

Do not grant global SUPERUSER merely to work around an unidentified permission error.

## 37. Handling Relation Does Not Exist Errors

Common causes:

- The subscriber has not created the schema/table.
- The publication added a new table, but the subscription has not been refreshed.
- Schema/table names differ.
- DDL rename/drop was not deployed in sync.
- Partition mapping is incompatible.
- Table sync has not completed or is in an error state.

Resolution:

1. Identify the relation on both publisher and subscriber.
2. Check the publication table list.
3. Check the subscription relation state.
4. Deploy compatible DDL on the subscriber.
5. Refresh the publication if membership changed.
6. Retry sync according to version guidance.

Do not create an empty table with the right name while ignoring column/type/constraint compatibility.

## 38. Handling Duplicate Keys and Apply Conflicts

Example:

~~~text
ERROR: duplicate key value violates unique constraint
DETAIL: Key (order_id)=(1001) already exists.
~~~

Investigate:

- Is an application performing local writes on the subscriber?
- Did initial copy re-run on a table that already had data?
- Are multiple subscriptions writing into the same table?
- Is the publisher emitting the same data scope from multiple publications?
- Is the schema/table mapping wrong?
- Did a manual restore create duplicate rows?

Choose the resolution based on the source of truth. You may need to delete or adjust conflicting rows on the subscriber, resynchronize the table, or rebuild the subscriber. Do not drop constraints just to let the worker proceed without understanding data invariants.

## 39. What Is the Impact of Changing Publication Scope?

Suppose a publication initially publishes all orders:

~~~sql
CREATE PUBLICATION orders_pub
FOR TABLE public.orders;
~~~

Later it is restricted:

~~~sql
ALTER PUBLICATION orders_pub
SET TABLE public.orders
WHERE (status = 'completed');
~~~

Changing the filter does not automatically delete rows the subscriber already received earlier that no longer satisfy the condition. Nor does it automatically reload all current rows matching the new predicate.

When changing scope, decide:

- Does the table need a resnapshot?
- Does old data need to be deleted?
- Do previously unpublished rows need to be copied?
- Did replica identity/column list change?
- Should apply be paused to perform a migration?

A scope change is a data change, not just a metadata update.

## 40. Sensitive Data and Tenant Isolation

Row filters and column lists can reduce the data transmitted to a subscriber, but publications should not be treated as the sole security boundary.

Example isolating tenant data:

~~~sql
CREATE PUBLICATION tenant_42_pub
FOR TABLE public.orders
    (order_id, tenant_id, status, total_amount)
    WHERE (tenant_id = 42);
~~~

Ensure that:

- Only administrative roles can alter the publication.
- The subscriber only grants access to users authorized to read that tenant's data.
- No other publication unintentionally widens the scope.
- No table-local writes break consistency.
- Row filters cannot be altered outside a review process.
- Subscriber backups are protected just like sensitive source data.

If strong security isolation is the goal, consider separate database/cluster architectures, subscriber access controls, and network segmentation—not just row filters.

## 41. Logical Replication and Failover

Logical replication can be used to migrate data or feed another system, but it does not replace a physical standby for full-cluster HA.

When the publisher fails over:

- The subscriber needs to connect to the new publisher.
- The logical replication slot must exist and be in an appropriate state on the new node.
- The subscription connection string may need updating.
- WAL/logical decoding state must be handled according to version and HA design.
- Not all slot configurations are automatically synchronized to standbys by default.

Designing HA for logical replication requires examining replication slot synchronization/failover support for your specific major version. Do not assume promoting a physical standby guarantees all logical subscribers continue uninterrupted.

## 42. When to Use Logical Replication?

Common use cases:

- Replicating selected tables to a reporting database.
- Migrating data between major versions.
- Offloading read/analytics workloads.
- Sharing data across systems.
- Synchronizing tables by tenant or business domain.
- Building downstream pipelines for search/analytics.

Not suitable when you need a complete physical copy of the cluster, need to replicate all DDL/global objects, or need multi-master conflict resolution without additional architecture.

## 43. Logical Replication vs. Physical Replication

| Criterion | Logical replication | Physical replication |
| --- | --- | --- |
| Unit of change | Row-level logical changes | Physical WAL changes |
| Scope | Publications/tables | Entire physical cluster |
| Table selection | Yes | No |
| Row/column filters | Yes, per version/features | No |
| DDL | Managed separately | Via WAL |
| Cross-version migration | Suitable within supported limits | Generally requires physical compatibility |
| Subscriber reads | Normal database, writable per policy | Read-only physical standby during recovery |
| Conflict handling | Apply conflicts possible | Physical replay via WAL |
| Full-cluster HA | Does not replace physical standby | Primary use case |

Choose the mechanism according to your goal. Both can be used in the same architecture: physical standbys for HA and logical publications/subscriptions for data distribution.

## 44. End-to-End Example: Synchronizing the orders Table

Suppose:

- Publisher database: sales_prod.
- Subscriber database: sales_reporting.
- Publisher host: publisher.example.net.
- Replication role: logical_repl.
- Publication: orders_reporting_pub.
- Subscription: orders_reporting_sub.

### Step 1: Create Role on Publisher

~~~sql
CREATE ROLE logical_repl
    WITH LOGIN REPLICATION
         NOSUPERUSER NOCREATEDB NOCREATEROLE;
~~~

Set the password via a secure mechanism. Grant additional SELECT privileges on tables needing initial synchronization per policy.

### Step 2: Create Publication

~~~sql
CREATE PUBLICATION orders_reporting_pub
FOR TABLE public.orders
WITH (publish = 'insert, update, delete');
~~~

### Step 3: Configure HBA/Network

Restrict the subscriber host, use TLS, and configure authentication methods per policy. HBA rules must match user, source address, and connection type.

### Step 4: Create Schema/Table on Subscriber

~~~sql
CREATE TABLE public.orders (
    order_id bigint PRIMARY KEY,
    customer_id bigint NOT NULL,
    status text NOT NULL,
    total_amount numeric(12,2) NOT NULL
);
~~~

Structure must be compatible with the publisher.

### Step 5: Create Subscription

~~~sql
CREATE SUBSCRIPTION orders_reporting_sub
CONNECTION 'host=publisher.example.net port=5432 dbname=sales_prod user=logical_repl sslmode=verify-full'
PUBLICATION orders_reporting_pub
WITH (copy_data = true);
~~~

### Step 6: Monitor

Subscriber:

~~~sql
SELECT *
FROM pg_stat_subscription
WHERE subname = 'orders_reporting_sub';
~~~

Publisher:

~~~sql
SELECT
    slot_name,
    active,
    confirmed_flush_lsn
FROM pg_replication_slots
WHERE slot_name = 'orders_reporting_sub';
~~~

### Step 7: Verify Data

Compare row counts, aggregates, and business invariants across both databases. Verify the apply worker has no errors and lag stays within operational thresholds.

## 45. Example: Synchronizing One Tenant and Selected Columns

Publisher:

~~~sql
CREATE PUBLICATION tenant_42_reporting_pub
FOR TABLE public.orders
    (order_id, tenant_id, customer_id, status, total_amount)
    WHERE (tenant_id = 42);
~~~

Subscriber needs a compatible table:

~~~sql
CREATE TABLE public.orders (
    order_id bigint PRIMARY KEY,
    tenant_id bigint NOT NULL,
    customer_id bigint,
    status text,
    total_amount numeric(12,2)
);
~~~

Create subscription:

~~~sql
CREATE SUBSCRIPTION tenant_42_reporting_sub
CONNECTION 'host=publisher.example.net dbname=sales_prod user=logical_repl sslmode=verify-full'
PUBLICATION tenant_42_reporting_pub;
~~~

Test cases:

- INSERT with tenant_id = 42.
- INSERT with another tenant_id.
- UPDATE changing status while keeping tenant_id.
- UPDATE changing tenant_id across the filter boundary.
- DELETE rows belonging to the tenant.
- TRUNCATE table if the publication permits this operation.

Do not deploy a tenant row filter to production before clearly defining behavior when rows switch tenants and how data reconciliation works.

## 46. Modifying a Publication and Refreshing a Subscription

Publisher adds a table:

~~~sql
ALTER PUBLICATION orders_reporting_pub
ADD TABLE public.order_items;
~~~

Subscriber creates the corresponding table first. Then refresh:

~~~sql
ALTER SUBSCRIPTION orders_reporting_sub
REFRESH PUBLICATION
WITH (copy_data = true);
~~~

PostgreSQL updates relation membership and synchronizes initial data for the new table according to the option.

If the subscriber already has an accurate baseline loaded via another process:

~~~sql
ALTER SUBSCRIPTION orders_reporting_sub
REFRESH PUBLICATION
WITH (copy_data = false);
~~~

Choose false only when a consistent baseline has been verified.

## 47. Common Mistakes

1. **Assuming a publication creates schemas/tables on the subscriber**, causing initial sync to fail with relation does not exist.
2. **Assuming logical replication synchronizes DDL**, whereas schema migrations must be deployed separately.
3. **Using a publication for all tables without auditing sensitive data**, making the scope broader than intended.
4. **Forgetting to refresh the subscription after adding a table**, leaving the subscriber unaware of the new relation.
5. **Assuming removing a table from a publication DROPs the subscriber table**, while subscriber data actually remains.
6. **Using copy_data=false when the subscriber lacks a consistent baseline**, causing missing data.
7. **Using copy_data=true on a subscriber table that already has duplicate data**, causing duplicate keys.
8. **Not configuring replica identity**, preventing UPDATE/DELETE from being published/applied.
9. **Using REPLICA IDENTITY FULL without evaluating WAL/CPU**, increasing overhead.
10. **Omitting identity columns from a column list**, preventing the subscriber from identifying rows.
11. **Treating a row filter as a full-refresh predicate**, overlooking state transitions across the filter boundary.
12. **Assuming a row filter applies to TRUNCATE**, causing unexpected deletion of subscriber data.
13. **Using multiple overlapping publications without understanding OR/column union**, widening scope unexpectedly.
14. **Failing to prepare a compatible table schema**, causing the apply worker to stop.
15. **Performing local writes into subscriber tables**, causing apply conflicts.
16. **Forgetting sequence state**, causing a promoted or writable subscriber to generate duplicate IDs.
17. **Assuming large objects, roles, and extensions are replicated**, even though they sit outside the publication table stream.
18. **Not monitoring replication slots**, causing WAL accumulation and disk exhaustion.
19. **Dropping a slot while the subscriber still needs it**, depriving the subscriber of the ability to resume from its previous position.
20. **Not checking table sync state**, mistaking an ongoing initial copy for completed replication.
21. **Not monitoring apply worker logs**, missing permission or constraint errors.
22. **Using logical replication instead of physical HA**, failing to meet cluster recovery requirements.
23. **Changing a row filter without resnapshot/reconciliation**, leaving stale rows on the subscriber.
24. **Changing a column list without coordinating the subscriber schema**, causing mismatches.
25. **Not testing partitioned table behavior**, resulting in incorrect subscriber mapping.
26. **Assuming subscription enabled equals healthy replication**, even though the worker may be failing or lagging.
27. **Exposing connection strings in catalog queries/logs**, leaking secrets.
28. **Not testing publisher failover and slot continuity**, causing subscriptions to break when the primary changes.

## 48. Practice Exercises with Answers

### Exercise 1. What is a publication?

**Answer:** An object on the publisher defining the tables and types of changes emitted to subscribers.

### Exercise 2. What is a subscription?

**Answer:** An object on the subscriber defining the publisher connection, publications to receive, and how to synchronize/apply.

### Exercise 3. What is the scope of a publication?

**Answer:** A specific database; it is not a cluster-wide object.

### Exercise 4. Create a publication for one table

~~~sql
CREATE PUBLICATION orders_pub FOR TABLE public.orders;
~~~

**Answer:** Publishes changes of the orders table with default publish operations.

### Exercise 5. Create an INSERT-only publication

~~~sql
CREATE PUBLICATION orders_insert_pub
FOR TABLE public.orders
WITH (publish = 'insert');
~~~

**Answer:** Emits only INSERTs.

### Exercise 6. Which operations does a default publication usually emit?

**Answer:** INSERT, UPDATE, DELETE, and TRUNCATE.

### Exercise 7. Create a publication for all tables

~~~sql
CREATE PUBLICATION all_pub FOR ALL TABLES;
~~~

**Answer:** A broad-scope publication for all eligible tables in the database; requires appropriate privileges.

### Exercise 8. From which version is schema-level publication supported?

**Answer:** PostgreSQL 15 and above.

### Exercise 9. What is a row filter used for?

**Answer:** Restricting published rows using a conditional expression.

### Exercise 10. Write a tenant filter

~~~sql
CREATE PUBLICATION tenant_pub
FOR TABLE public.orders
WHERE (tenant_id = 42);
~~~

**Answer:** Publishes only changes for rows satisfying tenant_id = 42 per row filter semantics.

### Exercise 11. Does a row filter filter TRUNCATE?

**Answer:** No. TRUNCATE is controlled by the publish option and is not converted into row-by-row deletion by the filter.

### Exercise 12. What is a column list used for?

**Answer:** Restricting which columns are sent for a table in a publication.

### Exercise 13. From which PostgreSQL version were column lists and row filters introduced?

**Answer:** PostgreSQL 15.

### Exercise 14. What does default replica identity use?

**Answer:** The primary key if the table has a primary key.

### Exercise 15. What does REPLICA IDENTITY FULL do?

**Answer:** Uses the entire old row as identifying information for UPDATE/DELETE, at higher data and row-lookup cost.

### Exercise 16. Create a subscription

~~~sql
CREATE SUBSCRIPTION orders_sub
CONNECTION 'host=publisher.example.net dbname=sales_prod user=logical_repl'
PUBLICATION orders_pub;
~~~

**Answer:** Creates a subscription receiving the orders_pub publication from the sales_prod publisher database.

### Exercise 17. What does copy_data=true mean?

**Answer:** Copies existing data of subscribed tables during initial table synchronization.

### Exercise 18. What does copy_data=false mean?

**Answer:** Skips initial copy; the subscriber must already have a consistent data baseline from another process.

### Exercise 19. Does adding a table to a publication automatically create the subscriber table?

**Answer:** No. Deploy the schema on the subscriber and refresh the publication.

### Exercise 20. Refresh a subscription

~~~sql
ALTER SUBSCRIPTION orders_sub REFRESH PUBLICATION;
~~~

**Answer:** Updates relation membership according to the current publication and synchronizes new tables per options.

### Exercise 21. Does removing a table from a publication delete subscriber data?

**Answer:** No. It stops receiving changes for the table; subscriber data remains.

### Exercise 22. Does logical replication replicate DDL?

**Answer:** It does not automatically replicate DDL; schema changes must be deployed separately.

### Exercise 23. Is sequence state continuously replicated?

**Answer:** No. Sequence state must be managed separately, especially before the subscriber starts accepting writes.

### Exercise 24. What is pg_replication_slots used to view?

**Answer:** Logical/physical slots, active status, and progress/retention LSNs.

### Exercise 25. Why can an inactive slot be dangerous?

**Answer:** It can retain required WAL indefinitely, causing pg_wal to grow and fill up the disk.

### Exercise 26. What is pg_stat_subscription used for?

**Answer:** Monitoring apply workers, received LSN, and message receipt timestamps depending on version.

### Exercise 27. What is pg_subscription_rel used for?

**Answer:** Viewing the table synchronization state of each relation in a subscription.

### Exercise 28. Does logical replication automatically resolve local write conflicts?

**Answer:** There is no generic conflict resolution; the apply worker can stop on constraint violations or conflicting data.

### Exercise 29. Can one subscription receive multiple publications?

**Answer:** Yes, from the same publisher database.

### Exercise 30. When should you choose physical replication instead of logical replication?

**Answer:** When you need a full-cluster physical copy/HA and do not need to restrict scope at the table/row/column level.

## 49. Publication/Subscription Deployment Checklist

- [ ] Identify publisher, subscriber, and data source of truth.
- [ ] Clearly define the database and publication scope.
- [ ] Select table/schema/all tables following the principle of least privilege/scope.
- [ ] Select publish operations: INSERT/UPDATE/DELETE/TRUNCATE.
- [ ] Verify row filters and semantics when rows cross the filter boundary.
- [ ] Verify column lists and replica identity columns.
- [ ] Prepare appropriate primary keys/replica identities for UPDATE/DELETE.
- [ ] Verify PostgreSQL version supports schema publications/row filters/column lists.
- [ ] Create replication role and appropriate HBA/network controls.
- [ ] Protect connection credentials and TLS.
- [ ] Create compatible schemas/tables on the subscriber.
- [ ] Prepare extensions and object dependencies.
- [ ] Decide copy_data true/false based on baseline.
- [ ] Check initial table sync state.
- [ ] Refresh publication after scope changes.
- [ ] Define how DDL will be deployed separately.
- [ ] Plan for sequences/large objects/global objects.
- [ ] Monitor pg_stat_subscription and pg_subscription_rel.
- [ ] Monitor pg_replication_slots and WAL retention.
- [ ] Monitor publisher/subscriber logs and apply conflicts.
- [ ] Do not write locally to subscribed tables without a conflict design.
- [ ] Test INSERT/UPDATE/DELETE/TRUNCATE within scope.
- [ ] Test row filter boundary transitions.
- [ ] Test partition behavior.
- [ ] Verify subscriber data, constraints, indexes, and permissions.
- [ ] Test disable/enable and reconnect.
- [ ] Test publisher failover/slot continuity per HA design.
- [ ] Protect subscriber data like source data.
- [ ] Document RPO/lag targets and recovery runbooks.

## 50. Official PostgreSQL Documentation

Read the documentation for the major version you are deploying:

- [Logical Replication](https://www.postgresql.org/docs/current/logical-replication.html) — overview of publisher/subscriber and architecture.
- [Publication](https://www.postgresql.org/docs/current/logical-replication-publication.html) — creating publications, table scope, row filters, column lists, and partition behavior.
- [Subscription](https://www.postgresql.org/docs/current/logical-replication-subscription.html) — creating subscriptions, initial sync, refresh, and lifecycle.
- [Logical Replication Architecture](https://www.postgresql.org/docs/current/logical-replication-architecture.html) — workers, apply, and synchronization.
- [Logical Replication Restrictions](https://www.postgresql.org/docs/current/logical-replication-restrictions.html) — DDL, sequences, large objects, and restrictions.
- [CREATE PUBLICATION](https://www.postgresql.org/docs/current/sql-createpublication.html) — syntax and publication options.
- [ALTER PUBLICATION](https://www.postgresql.org/docs/current/sql-alterpublication.html) — modifying table/schema scope.
- [CREATE SUBSCRIPTION](https://www.postgresql.org/docs/current/sql-createsubscription.html) — connection, copy_data, slot, and options.
- [ALTER SUBSCRIPTION](https://www.postgresql.org/docs/current/sql-altersubscription.html) — enable/disable, refresh, connection, and publication list.
- [Logical Replication Monitoring](https://www.postgresql.org/docs/current/logical-replication-monitoring.html) — system views for monitoring.
- [Replication Configuration](https://www.postgresql.org/docs/current/runtime-config-replication.html) — WAL senders, slots, and replication settings.
- [Replication Slots](https://www.postgresql.org/docs/current/warm-standby.html#STREAMING-REPLICATION-SLOTS) — slot lifecycle and WAL retention.
- [REPLICA IDENTITY](https://www.postgresql.org/docs/current/sql-altertable.html) — configuring row identity on tables.
- [Privileges](https://www.postgresql.org/docs/current/ddl-priv.html) — object access privileges.
- [Client Connection Parameters](https://www.postgresql.org/docs/current/libpq-connect.html) — TLS and connection parameters.

The `/current/` URLs point to the current PostgreSQL documentation. Row filters, column lists, schema publications, partition options, subscription privileges, and monitoring columns can vary across major versions; verify documentation for your exact server/client versions before deploying to production.

## 51. Summary

**A publication defines the data and operations to be emitted; a subscription defines the data source to receive and how to apply changes.** Controlling scope is a critical design responsibility in logical replication.

1. **Publications reside in the publisher database; subscriptions reside in the subscriber database.**
2. **Publications can select tables, schemas, or all eligible tables**, depending on version and privileges.
3. **Publish operations include INSERT, UPDATE, DELETE, and TRUNCATE.** Do not enable all operations by default if data requirements do not need them.
4. **Row filters restrict rows and column lists restrict columns**, with features supported starting in PostgreSQL 15.
5. **TRUNCATE is not filtered row-by-row by a row filter.** Local data on the subscriber must be considered.
6. **UPDATE/DELETE require an appropriate replica identity.** FULL has higher cost and requires benchmarking.
7. **Subscriptions can copy initial data**, then apply changes continuously.
8. **copy_data=false is only safe when the subscriber already has a consistent baseline.**
9. **Publication changes require refreshing the subscription when relation membership/metadata needs updating.** Removing a table from a publication does not automatically delete subscriber data.
10. **DDL, sequences, large objects, roles, and extensions require separate procedures.**
11. **Replication slots retain WAL for consumers.** Non-advancing slots can fill up the disk.
12. **Logical replication is neither a multi-master conflict resolver nor a whole-cluster physical copy.**
13. **Monitor apply workers, table sync, slot lag, and logs** to catch errors early.
14. **Test scope transitions, schema migrations, and failover** before operating in production.

A well-designed publication/subscription setup must precisely define the shared tables, rows, columns, and operations; prepare a compatible schema on the subscriber; and maintain procedures for change management and continuous data verification.
