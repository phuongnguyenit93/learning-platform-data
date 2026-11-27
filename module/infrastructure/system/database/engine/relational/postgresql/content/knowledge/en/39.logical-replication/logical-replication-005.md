# Row Filtering, Column Selection, and Version Support Checks in PostgreSQL

PostgreSQL logical replication allows a publication to publish only a subset of a table's data. Two key capabilities are **row filters** to restrict which rows are sent and **column lists** to restrict which columns are sent. They are useful when a subscriber only needs data for a specific tenant, region, business unit, or a subset of attributes for reporting.

These two features were added in **PostgreSQL 15**. The publisher uses `WHERE (...)` syntax in `CREATE PUBLICATION` to filter rows and a column list after the table name to select columns. The subscriber receives the filtered changes from the publication and applies them to target tables with compatible structures.

Choosing the right version on both ends is crucial. A PostgreSQL 15+ publisher can publish row-filtered/column-filtered changes to an older subscriber in some topologies, but a pre-PostgreSQL 15 subscriber does not apply those restrictions during initial table synchronization: it may copy all rows and all columns. PostgreSQL 18 adds support for replicating generated columns, with certain initial sync limitations when the subscriber is older than 18.

```text
                 PUBLISHER (PostgreSQL 15+)
              +-----------------------------+
              |       orders                |
              | tenant_id | id | amount |   |
              | status    | internal_note   |
              +--------------+--------------+
                             |
                  Row filter: tenant_id = 42
                             |
                  Column list: tenant_id,
                  id, amount, status
                             |
                             v
                  Logical publication
                             |
                             v
                  SUBSCRIBER
              +-----------------------------+
              |       orders                |
              | tenant_id | id | amount |   |
              | status                    |
              +-----------------------------+
```

This lesson belongs to the **Logical Replication** chapter of the *Database Engine Relational PostgreSQL* module. The goal is to master the syntax, semantics, replica identity constraints, interactions with partitioning and multiple publications, and how to verify feature support by version before deployment.

After this lesson, you will be able to:

1. Distinguish row filters and column lists.
2. Create a publication filtered by tenant or business condition.
3. Select columns to send while preserving a valid replica identity.
4. Explain how UPDATE can become INSERT or DELETE when a row enters/leaves a filter.
5. Identify supported and rejected row filter expressions.
6. Understand why TRUNCATE does not obey row filters/column lists.
7. Handle multiple publications, partitioned tables, and initial data synchronization.
8. Evaluate schema compatibility on the subscriber.
9. Check support across PostgreSQL 14, 15, 16, 17, and 18.
10. Detect security risks, schema changes, and data drift caused by filter configurations.

> **Practice scope:** Examples use two independent lab databases, one publisher and one subscriber. Publications are created on the publisher; subscriptions and target tables are created on the subscriber. Do not run DROP/TRUNCATE commands on production data for testing. Row filters and column lists reduce transmitted data, but they are not a security authorization mechanism for subscribers.

---

## 1. What Are Row Filters and Column Lists?

### 1.1. Row Filter

A row filter is a `WHERE` condition attached to a table in a publication. The publisher only emits rows satisfying that condition.

Example:

```sql
CREATE PUBLICATION tenant_42_pub
FOR TABLE sales.orders
WHERE (tenant_id = 42);
```

This publication only emits changes for rows with `tenant_id = 42`, following the row filter rules for INSERT/UPDATE/DELETE.

The row filter is evaluated on the publisher side before changes are sent to the subscriber. It does not create a physical view and does not alter source data.

### 1.2. Column List

A column list specifies which columns of a table are published:

```sql
CREATE PUBLICATION tenant_42_pub
FOR TABLE sales.orders (tenant_id, order_id, status, amount)
WHERE (tenant_id = 42);
```

In the example, the publication emits the four listed columns. Other columns, such as `internal_note`, are not sent in the row changes of this publication.

A column list does not alter the source table's schema. It only specifies the row data content emitted.

### 1.3. Using Both Together

A row filter and column list can be declared on the same table specification:

```sql
CREATE PUBLICATION tenant_42_orders
FOR TABLE sales.orders
    (tenant_id, order_id, status, amount, created_at)
    WHERE (tenant_id = 42)
WITH (publish = 'insert, update, delete');
```

This publication:

- Emits only rows belonging to tenant 42.
- Sends only the listed columns.
- Publishes INSERT, UPDATE, and DELETE.
- Does not publish TRUNCATE.

Omitting `truncate` from the publish list here is intentional. Row filters and column lists do not filter TRUNCATE; if TRUNCATE is published, the subscriber can receive a command to truncate the entire target table even though it only holds a subset of rows.

### 1.4. Distinguishing from Other Features

| Feature | Purpose | Impact |
|---|---|---|
| Row filter | Row selection | Restricts which rows are published |
| Column list | Column selection | Restricts columns in row changes |
| `publish` option | Operation type selection | Enables/disables INSERT, UPDATE, DELETE, TRUNCATE |
| `REPLICA IDENTITY` | Old row identification | Helps subscriber locate rows to UPDATE/DELETE |
| RLS | Authorization/row restriction in queries | Database row security mechanism |
| Subscription | Connects subscriber to publications | Creates logical replication workers/slot |

Do not confuse row filters with RLS or SELECT privileges. They relate to security context, yet they are distinct mechanisms.

---

## 2. Version Support

### 2.1. Row Filters and Column Lists Were Introduced in PostgreSQL 15

PostgreSQL 15 added selective publication content via:

- Row filters with `WHERE (...)`.
- Column lists after the table name.

Therefore, publishers on PostgreSQL 14 or earlier do not recognize this syntax in `CREATE PUBLICATION`. To use both features, the publisher must run PostgreSQL 15 or later.

### 2.2. Version Matrix

| Publisher version | Row filters | Column lists | Notes |
|---|---|---|---|
| PostgreSQL 14 and earlier | Not supported | Not supported | Publication lacks row-filter/column-list syntax |
| PostgreSQL 15 | Yes | Yes | First version with both features |
| PostgreSQL 16 | Yes | Yes | Continued support |
| PostgreSQL 17 | Yes | Yes | Continued support |
| PostgreSQL 18 | Yes | Yes | Adds generated-column replication support |

### 2.3. Publisher and Subscriber Can Differ in Version

Logical replication is designed to support certain cross-major-version scenarios, commonly used in upgrades or migrations. However, publication syntax support is a publisher-side feature, whereas initial data synchronization behavior depends on the subscriber version.

For row filters and column lists to work consistently from initial copy onward, both publisher and subscriber should run PostgreSQL 15 or later. If the subscriber is older, address the limitations in the next section before deploying.

### 2.4. Pre-PostgreSQL 15 Subscribers: Initial Copy Can Bypass Filters

If the publisher is PostgreSQL 15+ while the subscriber is on a version earlier than 15:

- Initial table synchronization does not apply row filters; all existing rows may be copied.
- Initial table synchronization does not apply column lists; all columns may be copied.
- After initial sync, the publisher still emits changes according to the configured row filter/column list.

This can create a dangerous state: the subscriber initially holds more rows/columns than intended, yet afterward receives only filtered changes. Extra rows copied initially do not automatically disappear just because the row filter stops publishing them.

If an older subscriber cannot be upgraded, implement a separate controlled initial load procedure, a target schema compatible with the old version's copy behavior, and an explicit reconciliation/cleanup step. Never assume the filter protected the initial snapshot.

### 2.5. PostgreSQL 18 and Generated Columns

PostgreSQL 18 adds the ability to replicate stored generated columns:

- Generated columns can be included directly in a column list.
- If no column list is specified, the publication option `publish_generated_columns = stored` allows emitting stored generated columns.
- If the subscriber is pre-PostgreSQL 18, initial table synchronization does not copy generated columns, even if the publisher enabled the option.

This is a separate change concerning generated columns; it does not mean row filters/column lists were only introduced in PostgreSQL 18.

### 2.6. Checking Versions on Both Ends

On the publisher:

```sql
SELECT
    version() AS full_version,
    current_setting('server_version') AS server_version,
    current_setting('server_version_num')::integer AS version_num,
    current_setting('server_version_num')::integer >= 150000
        AS supports_row_filters_and_column_lists;
```

Run the same query on the subscriber. For reference, `150000` corresponds to PostgreSQL 15.0; `180000` corresponds to PostgreSQL 18.0.

Do not check only the psql client version. Publication syntax is parsed by the publisher server; initial synchronization behavior depends on the subscriber server.

### 2.7. Checking Tools and Servers Separately

```bash
psql --version
pg_dump --version
```

These commands show client tool versions. To see the actual server version, connect to each node and run `SHOW server_version;`.

### 2.8. Checking Release Notes

Before using generated columns or newer features, read the release notes for your exact major version. Syntax appearing in current documentation may not exist on older servers.

---

## 3. Sample Table Design for Row Filters and Column Lists

### 3.1. Source Table

Example orders table:

```sql
CREATE SCHEMA IF NOT EXISTS sales;

CREATE TABLE sales.orders (
    tenant_id       BIGINT NOT NULL,
    order_id        BIGINT NOT NULL,
    status          TEXT NOT NULL,
    amount          NUMERIC(14, 2) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    internal_note   TEXT,
    payment_token   TEXT,
    PRIMARY KEY (tenant_id, order_id)
);
```

The primary key is `(tenant_id, order_id)`. This structure is convenient for tenant filtering because `tenant_id` is part of the replica identity.

### 3.2. Sample Data

```sql
INSERT INTO sales.orders
    (tenant_id, order_id, status, amount, internal_note, payment_token)
VALUES
    (42, 1001, 'paid',    120000, 'priority customer', 'tok-a'),
    (42, 1002, 'pending',  80000, 'call before ship',  'tok-b'),
    (43, 2001, 'paid',    450000, 'internal review',   'tok-c'),
    (44, 3001, 'draft',    25000, 'not confirmed',     'tok-d');
```

### 3.3. Subscriber Goal

Suppose the subscriber only needs:

- Orders belonging to tenant 42.
- Columns `tenant_id`, `order_id`, `status`, `amount`, `created_at`.
- Does not need `internal_note` or `payment_token`.

The row filter determines the row set; the column list determines the column set.

### 3.4. Creating the Publication

On a PostgreSQL 15+ publisher:

```sql
CREATE PUBLICATION tenant_42_orders
FOR TABLE sales.orders
    (tenant_id, order_id, status, amount, created_at)
    WHERE (tenant_id = 42)
WITH (publish = 'insert, update, delete');
```

Omit `TRUNCATE` from the publish list so a truncate command is not sent to the entire target table.

### 3.5. Creating the Subscriber Table

On the subscriber:

```sql
CREATE SCHEMA IF NOT EXISTS sales;

CREATE TABLE sales.orders (
    tenant_id   BIGINT NOT NULL,
    order_id    BIGINT NOT NULL,
    status      TEXT NOT NULL,
    amount      NUMERIC(14, 2) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, order_id)
);
```

The subscriber does not need the two columns `internal_note` and `payment_token`, because they are not in the column list. Published columns must exist on the subscriber and have compatible data types.

### 3.6. Creating the Subscription

On the subscriber, the executing role needs appropriate privileges to create subscriptions and the target table must already be prepared:

```sql
CREATE SUBSCRIPTION tenant_42_sub
CONNECTION 'host=publisher.example.net port=5432 dbname=appdb user=replicator password=replace-me sslmode=verify-full'
PUBLICATION tenant_42_orders
WITH (copy_data = true);
```

The connection string illustrates syntax only. Production should use a passfile/secret manager instead of placing passwords directly in SQL scripts or logs.

### 3.7. Expected Result

On the publisher, four rows exist. On the subscriber, only the two rows for tenant 42 are initially synced; only five columns are copied.

```sql
SELECT tenant_id, order_id, status, amount, created_at
FROM sales.orders
ORDER BY tenant_id, order_id;
```

The subscriber does not receive `internal_note` or `payment_token`.

---

## 4. Row Filter Evaluation Rules

### 4.1. Only TRUE Conditions Are Published

Row filters are evaluated on the publisher:

- TRUE: row qualifies to be published.
- FALSE: row is not published.
- NULL: row is not published.

This follows standard SQL WHERE semantics: only TRUE values are retained.

### 4.2. Conditions Must Be Enclosed in Parentheses

Syntax:

```sql
CREATE PUBLICATION p_orders
FOR TABLE sales.orders
WHERE (tenant_id = 42 AND status <> 'draft');
```

The expression after WHERE must be enclosed in parentheses. Each table specification can have its own condition.

### 4.3. Permitted Expressions

Row filters allow only simple expressions. Not supported:

- User-defined functions.
- User-defined operators.
- User-defined types.
- User-defined collations.
- System column references.
- Non-immutable built-in functions.

Examples of simple conditions:

```sql
WHERE (tenant_id = 42)
WHERE (status IN ('paid', 'shipped'))
WHERE (amount >= 100000 AND tenant_id = 42)
```

These examples illustrate expression syntax. If the publication emits UPDATE/DELETE, every column used in the filter must belong to the replica identity; not every example is valid for every table definition.

Do not use time-dependent functions like `now()` in a filter because their results vary over time and they are not immutable expressions. If a date cutoff is needed, compute a fixed boundary and store it as an appropriate literal/configuration.

### 4.4. A Row Filter Is Not an Arbitrary Query

You cannot call business functions, join other tables, or query reference tables inside a row filter. The expression evaluates solely on columns of the row being published.

If filtering based on data in another table is needed, consider:

- Denormalizing the filter attribute into the source table.
- Using a separate staging/materialized process table.
- Building another logical replication/application ETL pipeline.
- Filtering on the subscriber after loading data, if transmitting the source data to the subscriber is acceptable.

### 4.5. Role Used for Evaluation

The row filter is evaluated under the role used for the subscription's replication connection. Privileges and row-level security on the publisher can affect which data is visible.

Do not assume filters always run as superuser. Design roles, table ownership, and RLS policies clearly; test behavior using the actual replication role in a lab environment.

---

## 5. Replica Identity Constrains Row Filters and Column Lists

### 5.1. Why Do UPDATE/DELETE Need Replica Identity?

The subscriber must know which row to UPDATE or DELETE. The publisher sends old-row identifying information based on replica identity.

Normally, PostgreSQL uses the primary key as replica identity. Without a primary key, you can choose a suitable unique index or use `REPLICA IDENTITY FULL`.

### 5.2. Row Filters for UPDATE/DELETE

If a publication emits UPDATE or DELETE, columns referenced in the row filter must belong to the replica identity.

For example, table `sales.orders` has primary key:

```sql
PRIMARY KEY (tenant_id, order_id)
```

The following filter is valid:

```sql
WHERE (tenant_id = 42)
```

The following filter is invalid for a publication with UPDATE/DELETE if `status` is not part of the replica identity:

```sql
WHERE (status = 'paid')
```

This is because the publisher needs to evaluate the filter for both old/new rows during UPDATE and locate the old row when applying changes.

### 5.3. Column Lists for UPDATE/DELETE

If a publication emits UPDATE or DELETE, the column list must include all replica identity columns.

Example with primary key `(tenant_id, order_id)`:

```sql
CREATE PUBLICATION tenant_42_orders
FOR TABLE sales.orders
    (tenant_id, order_id, status, amount)
    WHERE (tenant_id = 42);
```

The column list retains both `tenant_id` and `order_id`, so the subscriber has enough information to identify the row.

### 5.4. When Publishing INSERT Only

When a publication emits only INSERT, replica identity constraints on row filters/column lists are relaxed:

- The row filter can reference any column of the row.
- The column list can omit replica identity columns.

Example:

```sql
CREATE PUBLICATION paid_order_inserts
FOR TABLE sales.orders (status, amount, created_at)
WHERE (status = 'paid')
WITH (publish = 'insert');
```

This is an insert-only publication. If UPDATE or DELETE is added later, you must re-evaluate the filter and column list before changing the publish option.

### 5.5. REPLICA IDENTITY FULL

If a table lacks an appropriate key, you can use:

```sql
ALTER TABLE sales.orders REPLICA IDENTITY FULL;
```

Then the entire row is used to identify the old row for UPDATE/DELETE. This fallback carries higher overhead because logical decoding must process more data and the subscriber must match rows by full contents.

Prefer a primary key or suitable unique index instead of using FULL across all tables.

### 5.6. Using a Unique Index as Replica Identity

You can select a unique index satisfying PostgreSQL requirements:

```sql
CREATE UNIQUE INDEX orders_replica_key
ON sales.orders (tenant_id, order_id);

ALTER TABLE sales.orders
REPLICA IDENTITY USING INDEX orders_replica_key;
```

A unique index used as replica identity must satisfy PostgreSQL requirements regarding uniqueness, non-partial/non-expression structure, and NOT NULL columns. Check the documentation for your running version.

### 5.7. Common Errors

If a filter uses a column outside the replica identity or a column list omits identity columns in a publication with UPDATE/DELETE, CREATE/ALTER PUBLICATION may be rejected or publishing operations may be invalid.

Do not fix the error by dropping the primary key from the subscriber. Redesign the replica identity on the publisher and keep a compatible key structure on the subscriber.

---

## 6. UPDATE Can Become INSERT or DELETE

### 6.1. Row Filters Evaluate Both Old and New Rows

When an UPDATE is processed, PostgreSQL evaluates the row filter against both the before-update and after-update row versions.

| Old row | New row | Emitted change |
|---|---|---|
| Does not match | Does not match | Not published |
| Does not match | Matches | INSERT |
| Matches | Does not match | DELETE |
| Matches | Matches | UPDATE |

The goal is for the subscriber to accurately reflect the exact row set defined by the row filter on the publisher.

### 6.2. Row Entering the Selected Set

Suppose the publication uses:

```sql
WHERE (tenant_id = 42)
```

A row previously belonging to tenant 43 is updated to tenant 42. The old row did not match; the new row matches. The subscriber receives an INSERT to add the new row into the published dataset.

### 6.3. Row Leaving the Selected Set

A row previously belonging to tenant 42 is moved to tenant 43. The old row matched; the new row does not match. The subscriber receives a DELETE to remove the previously sent row.

### 6.4. Both Versions Match

If tenant_id remains 42, changes to status or amount are published as an UPDATE (if the publication enables UPDATE).

### 6.5. Neither Version Matches

If tenant_id remains 43, the UPDATE is not published to the tenant 42 subscriber.

### 6.6. Operational Consequences

A row filter is not merely "checking only the new row." PostgreSQL maintains the dataset boundary on the subscriber by transforming UPDATEs into INSERTs/DELETEs when membership changes.

This only works properly when replica identity is sufficient to locate the old row and required columns are published.

### 6.7. Changing Filter Conditions

If you change a filter from `tenant_id = 42` to `tenant_id IN (42, 43)`, existing tenant 43 rows are not automatically added just because the publication definition changed. You must consider refresh/initial synchronization or a backfill process so the subscriber receives all data newly entering scope.

Similarly, when narrowing a filter, rows already on the subscriber that are no longer in scope may remain if the filter change did not generate corresponding DML deletes. Plan data reconciliation after modifying a publication.

---

## 7. Column Lists: Rules and Target Schema

### 7.1. Accepts Only Simple Column Names

A column list contains only simple column references:

```sql
CREATE PUBLICATION p_orders
FOR TABLE sales.orders (tenant_id, order_id, status, amount);
```

Column lists cannot be combined with the `FOR TABLES IN SCHEMA` specification; `FOR ALL TABLES` and `FOR TABLES IN SCHEMA` also do not allow per-table filters/lists. When row/column selection is needed, declare individual tables with `FOR TABLE`.

Do not use expressions, calculations, aliases, or renames in a column list. Forms like `lower(email)`, `amount * 1.1`, or `email AS contact` are not valid column list syntax.

If transformation/renaming is needed, use a schema/view/ETL in another layer. A publication column list only selects source columns.

### 7.2. Column Order Is Not Preserved

The order of names in a column list is not used as positional column ordering. Logical replication maps by column name. The subscriber needs the published columns with matching names and compatible data types.

### 7.3. The Subscriber Can Have Extra Columns

The subscriber table must have at least all published columns. It may have extra local columns, provided those extra columns have a valid way to obtain values when replication applies INSERT.

For example, an extra column `subscriber_tag TEXT` can use a default or allow NULL. If it is NOT NULL without a default, INSERTs from the apply worker can fail because the publisher does not send that column.

### 7.4. The Subscriber Can Omit Excluded Columns

If the column list omits `internal_note` and `payment_token`, the target table does not need to declare those two columns. This is useful when the subscriber has a leaner schema, though schema mapping must be verified before enabling the subscription.

### 7.5. Explicit List vs. No List Declared

Without a column list, PostgreSQL publishes all regular columns of the table, including columns added in the future.

If an explicit column list enumerates all current columns, newly added columns later will not be automatically published. This is an important difference when schemas evolve.

### 7.6. Schema Evolution Example

Initially:

```sql
CREATE PUBLICATION p_orders
FOR TABLE sales.orders (tenant_id, order_id, status, amount);
```

Later the publisher adds:

```sql
ALTER TABLE sales.orders
ADD COLUMN fulfillment_region TEXT;
```

The new column does not automatically appear in the existing column list. If the subscriber needs it:

1. Create a compatible column on the subscriber.
2. Check replica identity and publication requirements.
3. Update the column list via ALTER PUBLICATION.
4. Plan a backfill for existing data if needed.
5. Verify replication continues normally.

### 7.7. Column Lists Are Not Secure Projections

A column list can reduce payload size and avoid syncing unnecessary attributes. However, do not treat it as a security measure guaranteeing a subscriber cannot access excluded columns. Publications do not enforce per-subscriber column-level access controls.

If sensitive data must be protected, enforce privileges on the publisher, create a separated data source, or use an appropriate security mechanism. Do not rely on column lists as a confidentiality boundary.

---

## 8. TRUNCATE Is Not Restricted by Row Filters or Column Lists

### 8.1. Row Filters Do Not Apply to TRUNCATE

Row filters evaluate row changes only. TRUNCATE is a whole-relation operation, not a set of row events to filter row by row.

Therefore, if a publication emits TRUNCATE, the command is sent to the subscriber without applying the row filter.

### 8.2. Column Lists Also Do Not Apply to TRUNCATE

Column lists restrict row payload data. TRUNCATE carries no row payload, so column lists do not alter its behavior.

### 8.3. Risk for Partial-Row Subscribers

Suppose a subscriber receives only tenant 42. The target table holds only tenant 42's rows. If an application runs TRUNCATE on the publisher table and the publication emits TRUNCATE, the subscriber may truncate the entire target table, even if the publisher intended to clear data in a broader context.

### 8.4. Safer Publication Configuration

For partial-data publications, typically omit TRUNCATE:

```sql
CREATE PUBLICATION tenant_42_orders
FOR TABLE sales.orders
    (tenant_id, order_id, status, amount)
    WHERE (tenant_id = 42)
WITH (publish = 'insert, update, delete');
```

### 8.5. When Business Logic Needs to Delete Many Rows

Instead of TRUNCATE, use a conditional DELETE so logical replication can apply the row filter per row:

```sql
DELETE FROM sales.orders
WHERE tenant_id = 42
  AND status = 'cancelled';
```

DELETE emits only row changes matching the filter. Evaluate performance impact and WAL record volume for large-scale deletions.

### 8.6. Inspecting Publish Options

```sql
SELECT
    pubname,
    pubinsert,
    pubupdate,
    pubdelete,
    pubtruncate
FROM pg_publication
ORDER BY pubname;
```

If a publication has partial rows, verify `pubtruncate` is false unless full-table truncate semantics on the subscriber are explicitly intended.

---

## 9. Multiple Publications Publishing the Same Table

### 9.1. Row Filters Are Combined with OR

A subscription can subscribe to multiple publications containing the same table. If publications define different row filters for the same operation, PostgreSQL combines them with OR.

Example:

```sql
CREATE PUBLICATION tenant_42_pub
FOR TABLE sales.orders WHERE (tenant_id = 42);

CREATE PUBLICATION tenant_43_pub
FOR TABLE sales.orders WHERE (tenant_id = 43);
```

If a subscription subscribes to both publications, rows belonging to tenant 42 or tenant 43 are emitted.

### 9.2. An Unfiltered Publication Negates Another Filter

If one publication has no row filter for that operation, or the table is included via `FOR ALL TABLES`/`FOR TABLES IN SCHEMA`, the filter condition from another publication becomes redundant because an unrestricted source exists.

Example:

```sql
CREATE PUBLICATION all_orders
FOR TABLE sales.orders;

CREATE PUBLICATION tenant_42_only
FOR TABLE sales.orders WHERE (tenant_id = 42);
```

A subscription receiving both publications will receive all rows via `all_orders`; the tenant 42 filter no longer restricts the overall dataset.

### 9.3. Column Lists Cannot Be Arbitrarily Combined

A subscription subscribing to multiple publications where the same table is published with different column lists is currently unsupported.

```sql
CREATE PUBLICATION p_a
FOR TABLE sales.orders (tenant_id, order_id, status);

CREATE PUBLICATION p_b
FOR TABLE sales.orders (tenant_id, order_id, amount);
```

Do not create a subscription expecting PostgreSQL to automatically union both lists into four columns. CREATE SUBSCRIPTION will reject conflicting configurations; if a publication is ALTERed after the subscription exists, apply errors can occur.

### 9.4. Changing a Column List After Subscription Creation

If modifying a column list on a publication currently used by a subscriber, check every other publication in the same subscription that publishes the same table. Column lists must match per support requirements.

If a mismatch state already occurred, align the column lists and potentially recreate the subscription or drop/add publications via ALTER SUBSCRIPTION according to your version's guidance.

### 9.5. Designing One Publication per Subscriber

When different subscribers need different column sets, you can create separate publications per subscriber group, but do not combine publications with conflicting column lists for the same table in one subscription.

Maintain a mapping table:

| Subscriber | Publication | Row filter | Column list |
|---|---|---|---|
| Tenant 42 | tenant_42_pub | tenant_id = 42 | Required business columns |
| Tenant 43 | tenant_43_pub | tenant_id = 43 | Same compatible column set |
| Analytics | analytics_pub | No filter or dedicated filter | Analytics column set |

Check subscriptions for publication overlap before creating new ones.

---

## 10. Partitioned Tables and publish_via_partition_root

### 10.1. Publications Can Include Partitioned Tables

When adding a partitioned table to a publication, current and future partitions belong to the publication per PostgreSQL rules. Row filters and column lists can be taken from the root or from individual partitions.

### 10.2. publish_via_partition_root = false

This is the default. Each leaf partition's own row filter and column list are used when emitting changes from that partition.

This can be useful when each partition has a tailored policy or schema, but you must ensure configurations across all partitions align with replication intent.

### 10.3. publish_via_partition_root = true

When enabled:

```sql
CREATE PUBLICATION regional_orders
FOR TABLE sales.orders
    (tenant_id, order_id, status, amount)
    WHERE (tenant_id = 42)
WITH (
    publish = 'insert, update, delete',
    publish_via_partition_root = true
);
```

The row filter and column list are taken from the root partitioned table. Changes occurring directly on a leaf partition are also published under the root's identity/schema.

### 10.4. Inspecting Partition Configuration

```sql
SELECT
    p.pubname,
    p.pubviaroot,
    pt.schemaname,
    pt.tablename,
    pt.attnames,
    pt.rowfilter
FROM pg_publication AS p
JOIN pg_publication_tables AS pt
  ON pt.pubname = p.pubname
WHERE p.pubname = 'regional_orders'
ORDER BY pt.schemaname, pt.tablename;
```

The view may show leaf partitions expanded from the partitioned root. Inspect the view schema on your exact major version.

### 10.5. Direct TRUNCATE on a Partition

When `publish_via_partition_root = true`, TRUNCATE executed directly on a partition has specific rules; PostgreSQL does not publish certain direct partition TRUNCATE operations per documented behavior. Even so, row filters/column lists are still not TRUNCATE filters. Partial-data publication designs should disable truncate unless explicitly required.

### 10.6. New Partitions

When creating/attaching a new partition:

- Check whether the partition belongs to the publication via root/schema scope.
- If `publish_via_partition_root = false`, inspect the filter and column list on the partition.
- If true, inspect the configuration on the root.
- Confirm the subscriber has a compatible target table/partition.
- Test insert/update/delete routed through the root and operations directly on the leaf.

### 10.7. Different Partition Structures Between Publisher and Subscriber

Logical replication can publish changes via the root so the subscriber uses a different partition structure or an unpartitioned table, provided schema/identity mapping is compatible. Do not assume both partition trees automatically sync DDL; DDL is not replicated.

---

## 11. Initial Data Synchronization and copy_data

### 11.1. Initial Copy

When creating a subscription with `copy_data = true`, PostgreSQL copies existing data of subscribed tables. When publisher and subscriber both support row filters/column lists, initial sync applies:

- The row filter to select rows.
- The column list to select columns.

After initial copy finishes, apply workers continue receiving new changes from the publisher.

### 11.2. copy_data = false

```sql
CREATE SUBSCRIPTION tenant_42_sub
CONNECTION 'host=publisher.example.net dbname=appdb user=replicator sslmode=verify-full'
PUBLICATION tenant_42_orders
WITH (copy_data = false);
```

When using `copy_data = false`, the subscription does not automatically copy pre-existing rows. It only applies changes occurring after subscription startup. A separate initial load synchronized with the replication position is needed to avoid missing or duplicating data.

### 11.3. The publish Option Does Not Control Initial Copy

The publication `publish` option selects which DML operations are emitted in the replication stream. Initial data synchronization does not follow this option when copying existing rows.

For example, a publication that only emits UPDATE/DELETE still copies existing data during initial sync if the subscription uses `copy_data = true`.

### 11.4. Row Filters in Initial Sync

If the publisher has a row filter and the subscriber is PostgreSQL 15 or later, initial copy fetches only rows matching the condition. If a subscription receives multiple publications for the same table, row filters are combined with OR for the same operation.

### 11.5. Subscribers Older Than 15

If the subscriber is pre-PostgreSQL 15:

- Initial copy ignores row filters and copies all rows.
- Initial copy ignores column lists and copies all columns.

After initial copy, changes are emitted according to the publisher's filter/list. The initial dataset may exceed the intended scope; upgrade the subscriber or use a separate initial data workflow.

### 11.6. Avoiding Excess Stale Data

If the subscriber already contains data before creating the subscription, `copy_data = true` can cause duplicate keys or conflicts. With `copy_data = false`, ensure initial data matches the publication filter/column list and replication start point.

Do not run bulk deletes on the subscriber to "fix" data after initial sync without knowing what transactions are currently applying and the slot/worker state.

### 11.7. Checking Table Synchronization State

```sql
SELECT
    srrelid::regclass AS relation,
    srsubstate,
    srsublsn
FROM pg_subscription_rel
ORDER BY srrelid::regclass::text;
```

Table sync state helps identify whether a table is copying, catching up, or ready. Exact state codes and meanings depend on PostgreSQL version; check catalog documentation before writing automation.

---

## 12. Systematically Checking Version Support

### 12.1. Checking the Publisher

Run on the publisher:

```sql
SHOW server_version;

SELECT current_setting('server_version_num')::integer AS version_num;
```

If the publisher is below 150000, do not use row filter/column list syntax.

### 12.2. Checking the Subscriber

Connect separately to the subscriber and run the same queries. Do not infer subscriber initial sync behavior from the publisher's version.

Record both:

| Node | Server version | Role | Feature to verify |
|---|---|---|---|
| Publisher | 15+ | Create publication and filter changes | Row filter, column list |
| Subscriber | 15+ | Initial copy per filter/list | Initial sync selects right rows/columns |
| Subscriber | 14 and earlier | Legacy subscriber | Initial copy may copy all rows/columns |
| Publisher | 18+ | Generated column source | `publish_generated_columns` and generated column list |
| Subscriber | Pre-18 | Legacy generated-column target | Initial copy does not copy generated columns |

### 12.3. Inspecting Publication Catalogs

On a PostgreSQL 15+ publisher:

```sql
SELECT
    pubname,
    schemaname,
    tablename,
    attnames,
    rowfilter
FROM pg_publication_tables
WHERE schemaname = 'sales'
ORDER BY pubname, tablename;
```

This view displays tables in publications along with column lists and row filters if configured. For partitioned tables, the view may expand details to partitions per publication semantics.

### 12.4. Inspecting Publication-Level Options

```sql
SELECT
    pubname,
    puballtables,
    pubinsert,
    pubupdate,
    pubdelete,
    pubtruncate,
    pubviaroot
FROM pg_publication
ORDER BY pubname;
```

Some columns may differ by major version. Use the psql command `\dRp+` to view publications in a readable format:

```text
\dRp+
\dRp+ tenant_42_orders
```

### 12.5. Inspecting Publication Table Membership

```sql
SELECT *
FROM pg_publication_tables
WHERE pubname = 'tenant_42_orders';
```

Confirm:

- Table has the right schema/name.
- Column list contains replica identity columns.
- Row filter has the right expression.
- No other publication accidentally publishes the same table unfiltered.

### 12.6. Inspecting Subscriptions

On the subscriber:

```sql
SELECT
    subname,
    subenabled,
    subslotname,
    subpublications
FROM pg_subscription
ORDER BY subname;
```

To view worker state:

```sql
SELECT
    subname,
    pid,
    relid::regclass AS relation,
    received_lsn,
    latest_end_lsn,
    latest_end_time
FROM pg_stat_subscription;
```

Views and columns may change across versions. Check catalog documentation before packaging into a monitoring query shared across multiple major versions.

### 12.7. Testing Features with a Test Publication

In a lab, create a small table and test the syntax:

```sql
CREATE TABLE public.feature_probe (
    id BIGINT PRIMARY KEY,
    region TEXT NOT NULL,
    payload TEXT,
    private_value TEXT
);

CREATE PUBLICATION feature_probe_pub
FOR TABLE public.feature_probe (id, region, payload)
WHERE (region = 'APAC');
```

If the server does not support the syntax, CREATE PUBLICATION will report a parse/feature error. After testing, drop the lab publication/table.

### 12.8. Generated Columns from PostgreSQL 18

On PostgreSQL 18:

```sql
CREATE TABLE public.invoice (
    invoice_id BIGINT PRIMARY KEY,
    net_amount NUMERIC(12, 2) NOT NULL,
    tax_amount NUMERIC(12, 2) NOT NULL,
    gross_amount NUMERIC(12, 2)
        GENERATED ALWAYS AS (net_amount + tax_amount) STORED
);

CREATE PUBLICATION invoice_pub
FOR TABLE public.invoice
    (invoice_id, net_amount, tax_amount, gross_amount);
```

Column lists can name generated columns directly. If not using an explicit list, the publication option `publish_generated_columns = stored` controls emitting stored generated columns. Subscribers older than PostgreSQL 18 do not copy generated columns during initial sync; verify schemas and versions before using.

---

## 13. Security and Row-Level Security

### 13.1. Row Filters Are Not Security Boundaries

Row filters can reduce data sent to a subscriber, but they should not be the sole protection layer for sensitive data.

PostgreSQL currently has no per-publication privilege allowing a subscriber to be authorized for only one specific publication. A replication connection can access publications according to system privileges and configuration; other publications may emit the same data.

### 13.2. Column Lists Are Not Column-Level Access Controls

Column lists reduce payload and schema footprint, but they do not guarantee a malicious subscriber cannot obtain excluded column values. Use publisher-side privileges, database separation, data masking, or dedicated pipelines if confidentiality is required.

### 13.3. Replication Roles

The role connecting for replication must have the REPLICATION attribute or be superuser, along with LOGIN and required SELECT privileges for initial table copy.

Do not use superuser as the default replication user. Grant least privilege and restrict connections via pg_hba.conf/network policies.

### 13.4. RLS on the Publisher

If the replication role lacks SUPERUSER or BYPASSRLS, row security policies on the publisher may be enforced. This can affect which rows the replication connection sees.

If you do not trust all table owners, you can use connection option `options=-crow_security=off` so replication fails rather than executing a row security policy added by an owner. Check security documentation for your exact version and test with the actual role.

### 13.5. Row Filter Expressions and RLS

A row filter is a publication condition; RLS is a policy controlling row access. Both layers can jointly affect which data is read/replicated. Do not assume a filter replaces a policy or a policy replaces publication scope.

### 13.6. Subscriber Privileges

The apply worker on the subscriber executes with a security context governed by the subscription owner and the version's table owner/role-switching rules. Ensure the owner can apply DML on target tables and does not trigger unintended triggers/rules.

### 13.7. Protecting Credentials and Network

- Use SCRAM or certificate authentication.
- Use TLS and verify server certificates.
- Protect password files/secret managers.
- Open network access only to required subscribers.
- Monitor replication connections.
- Never log connection strings containing passwords.

---

## 14. Monitoring Row Filters and Column Lists

### 14.1. Viewing Publication Definitions

```sql
SELECT
    pubname,
    schemaname,
    tablename,
    attnames,
    rowfilter
FROM pg_publication_tables
ORDER BY pubname, schemaname, tablename;
```

This is how to verify the actual configuration after a publication is created/altered. Do not rely solely on past migration scripts.

### 14.2. Viewing Subscription Status

```sql
SELECT
    subname,
    pid,
    received_lsn,
    latest_end_lsn,
    latest_end_time
FROM pg_stat_subscription;
```

If a subscription has no worker, check `subenabled`, connectivity, slots, logs, and apply status.

### 14.3. Viewing Table Synchronization

```sql
SELECT
    srrelid::regclass AS relation,
    srsubstate,
    srsublsn
FROM pg_subscription_rel
ORDER BY srrelid::regclass::text;
```

Initial sync can take a long time on large tables. Row filters reduce the rows to copy when supported by the subscriber; column lists reduce columns in initial copy when supported by the version.

### 14.4. Verifying Actual Data

On the publisher:

```sql
SELECT COUNT(*)
FROM sales.orders
WHERE tenant_id = 42;
```

On the subscriber:

```sql
SELECT COUNT(*)
FROM sales.orders;
```

Two counts may differ temporarily when replication is lagging. For exact comparisons, pause writes in a lab or establish a verifiable reconciliation point, then compare by primary key and published column values.

### 14.5. Checking Present Columns

On the subscriber:

```sql
SELECT
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'sales'
  AND table_name = 'orders'
ORDER BY ordinal_position;
```

Compare against the column list and schema contract. Do not assume columns omitted from the publication are automatically dropped from the subscriber.

### 14.6. Checking Replication Errors

Read PostgreSQL logs on both publisher and subscriber. Common errors relate to:

- Missing or invalid replica identity.
- Column list missing identity columns.
- Subscriber missing published columns.
- Incompatible data type mapping.
- Apply worker lacking write privileges.
- Conflicting publication column lists.
- Initial synchronization incompatibility with an older subscriber.

### 14.7. Operational Metrics

Monitor:

- Subscription worker state.
- Replication lag and latest end LSN/time.
- Initial table sync progress/state.
- Publisher WAL retention/slot health.
- Apply errors and retry counts.
- Row counts/reconciliation drift.
- Disk/network/CPU during initial copy.

Row filters can reduce rows, yet do not automatically eliminate all logical decoding or metadata overhead. Column lists shrink payloads, but performance must be measured under real workloads.

---

## 15. Safely Modifying Publications

### 15.1. Adding a Table with Row Filter and Column List

```sql
ALTER PUBLICATION tenant_42_orders
ADD TABLE sales.refunds
    (tenant_id, refund_id, order_id, amount)
    WHERE (tenant_id = 42);
```

This alters the publication definition on the publisher. If the subscription is not yet tracking the new table, refresh the publication on the subscriber using the appropriate workflow to spawn a table synchronization worker.

### 15.2. Replacing Table Specifications

```sql
ALTER PUBLICATION tenant_42_orders
SET TABLE sales.orders
    (tenant_id, order_id, status, amount, created_at)
    WHERE (tenant_id = 42);
```

SET TABLE replaces the publication's list of table members. If the publication contains multiple tables, re-list all tables to keep; otherwise, omitted tables will be removed from the publication.

### 15.3. Dropping a Table

```sql
ALTER PUBLICATION tenant_42_orders
DROP TABLE sales.refunds;
```

Dropping a table from a publication stops publishing changes for that table after the altering transaction commits. It does not drop the table on the subscriber and does not delete already replicated data.

### 15.4. Changing a Filter

When expanding scope:

```sql
ALTER PUBLICATION tenant_42_orders
SET TABLE sales.orders
    (tenant_id, order_id, status, amount, created_at)
    WHERE (tenant_id IN (42, 43));
```

Changing the filter affects only subsequent changes. Existing tenant 43 rows on the publisher are not automatically backfilled just because the new filter includes them.

### 15.5. Changing a Column List

When adding a new column:

1. Add a compatible column on the subscriber first.
2. Determine values for existing rows on the subscriber.
3. Update the column list on the publisher.
4. Verify the publication and subscription continue operating.
5. Reconcile data after the change.

Do not expect an ALTER PUBLICATION to automatically backfill new column values for all existing rows.

### 15.6. Schema Changes via Expand/Contract

A safe sequence is typically:

1. **Expand:** add a nullable/default-compatible column on the subscriber.
2. **Expand:** add the column on the publisher.
3. Update the column list to publish the new column.
4. Backfill existing data via a controlled workflow.
5. Verify the subscriber is synchronized.
6. Switch the application to use the new column.
7. **Contract:** remove the old column once all consumers have transitioned.

Logical replication does not automatically replicate DDL. Schema migrations must be coordinated at both ends.

### 15.7. Filter Changes Require Reconciliation

When expanding a filter, backfill rows newly entering scope. When narrowing a filter, delete or archive rows no longer in scope on the subscriber. Use business keys and a verifiable cutover point to avoid missing updates during backfill.

### 15.8. Multiple Publications on One Subscription

Before ALTERing a column list:

- List all publications the subscription follows.
- Check whether other publications include the same table.
- Ensure column lists do not conflict.
- Ensure row filters combine via OR as intended.
- Plan the change and reconciliation after the apply worker resumes.

---

## 16. Troubleshooting

### 16.1. Server Rejects WHERE Syntax in CREATE PUBLICATION

The common cause is a publisher on PostgreSQL 14 or earlier. Check `SHOW server_version` on the publisher. Row filters were introduced in PostgreSQL 15.

### 16.2. Column List Syntax Not Supported

Like row filters, column lists were introduced in PostgreSQL 15. Upgrade the publisher or design another pipeline; upgrading the client version does not make an older server understand new syntax.

### 16.3. Row Filter Uses a Column Outside Replica Identity

If the publication emits UPDATE/DELETE, the filter may only reference columns belonging to the replica identity. Inspect:

```sql
SELECT
    c.relname,
    c.relreplident
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE n.nspname = 'sales'
  AND c.relname = 'orders';
```

`relreplident` shows the replica identity mode. Check the actual index and decide whether to add an appropriate key or use FULL if no other option exists.

### 16.4. Column List Missing Identity Columns

If the publication emits UPDATE/DELETE, ensure the column list contains all replica identity columns. For instance, if the table has primary key `(tenant_id, order_id)`, both must be in the list.

### 16.5. Subscriber Reports Missing Column

Compare `pg_publication_tables.attnames` on the publisher with `information_schema.columns` on the subscriber. Create the published columns before enabling/refreshing the subscription; check names and data types.

### 16.6. Subscriber Reports NOT NULL Violation

The target table likely has an extra NOT NULL column that the publisher does not send. Add a default, allow NULL, or adjust schema mapping so INSERT apply supplies a valid value.

### 16.7. Initial Sync Contains Rows Outside Filter

Check the subscriber version. If the subscriber is pre-PostgreSQL 15, initial sync ignores row filters and copies all table data. Plan cleanup/reinitialization or upgrade the subscriber.

### 16.8. Initial Sync Includes Excluded Columns

If the subscriber is pre-PostgreSQL 15, initial sync ignores column lists and copies all columns. If the target schema only has a subset of columns, initial sync can fail due to missing columns.

### 16.9. UPDATE Causes INSERT/DELETE on Subscriber

This may be expected behavior. If the old row did not match while the new row matches, UPDATE becomes INSERT. If the old row matched while the new row does not match, UPDATE becomes DELETE.

Verify old/new values and the row filter before treating this as a bug.

### 16.10. TRUNCATE Wipes All Subscriber Data

Row filters do not apply to TRUNCATE. Check `pubtruncate`; for partial-row publications, typically exclude TRUNCATE from the `publish` option.

### 16.11. Row Filter Does Not Restrict Data as Expected

Check:

- Whether the subscription follows another unfiltered publication.
- Whether the table belongs to a `FOR ALL TABLES` or `FOR TABLES IN SCHEMA` publication.
- Whether multiple row filters OR together into a broader set.
- Whether an RLS role affects visibility.
- Whether partitions use filters from the root or leaves.

### 16.12. Subscription Errors After Changing Column List

Check whether the same table is published by multiple publications with differing column lists. Make the lists compatible and perform the ALTER SUBSCRIPTION/recreate procedure per PostgreSQL version guidance.

### 16.13. Generated Columns Not Copied in Initial Sync

If the publisher is PostgreSQL 18 while the subscriber is pre-18, initial table synchronization does not copy generated columns. Upgrade the subscriber or build a compatible initial load process.

### 16.14. Filter Expression Rejected

Remove:

- User-defined functions/operators/types/collations.
- Non-immutable built-in functions.
- System columns.
- Columns outside replica identity if UPDATE/DELETE is enabled.

Keep expressions simple over permitted columns.

### 16.15. Replication Lag Increasing

Row filters/column lists do not guarantee faster replication in every case. Inspect logical decoding, WAL generation, network, apply workers, index/constraint overhead on the subscriber, and initial sync workers.

---

## 17. Lab Practice

### 17.1. Check Publisher Version

```sql
SHOW server_version;
SELECT current_setting('server_version_num')::integer;
```

Only proceed with row filter/column list examples if the publisher is PostgreSQL 15 or later.

### 17.2. Create Table and Publication

```sql
CREATE SCHEMA IF NOT EXISTS lab;

CREATE TABLE lab.customer_events (
    tenant_id BIGINT NOT NULL,
    event_id BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    event_time TIMESTAMPTZ NOT NULL,
    internal_payload JSONB,
    PRIMARY KEY (tenant_id, event_id)
);

CREATE PUBLICATION lab_tenant_42_pub
FOR TABLE lab.customer_events
    (tenant_id, event_id, event_type, event_time)
    WHERE (tenant_id = 42)
WITH (publish = 'insert, update, delete');
```

### 17.3. Inspect Publication Definition

```sql
SELECT
    pubname,
    schemaname,
    tablename,
    attnames,
    rowfilter
FROM pg_publication_tables
WHERE pubname = 'lab_tenant_42_pub';
```

Verify the tenant 42 filter and that the column list includes only the four selected columns.

### 17.4. Create Subscriber Table

On the subscriber:

```sql
CREATE SCHEMA IF NOT EXISTS lab;

CREATE TABLE lab.customer_events (
    tenant_id BIGINT NOT NULL,
    event_id BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    event_time TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, event_id)
);
```

The target table does not need the JSONB `internal_payload` column.

### 17.5. Create Subscription

On the subscriber:

```sql
CREATE SUBSCRIPTION lab_tenant_42_sub
CONNECTION 'host=publisher.example.net dbname=appdb user=replicator sslmode=verify-full'
PUBLICATION lab_tenant_42_pub
WITH (copy_data = true);
```

Wait for initial synchronization to complete, then inspect `pg_subscription_rel` and `pg_stat_subscription`.

### 17.6. Insert Row Belonging to Selected Tenant

On the publisher:

```sql
INSERT INTO lab.customer_events
    (tenant_id, event_id, event_type, event_time, internal_payload)
VALUES
    (42, 1, 'order_created', clock_timestamp(), '{"source":"api"}');
```

This row is published. The subscriber receives the four selected columns.

### 17.7. Insert Row Outside Filter

```sql
INSERT INTO lab.customer_events
    (tenant_id, event_id, event_type, event_time, internal_payload)
VALUES
    (43, 2, 'order_created', clock_timestamp(), '{"source":"api"}');
```

The tenant 43 row is not published to the tenant 42 subscriber.

### 17.8. UPDATE Row Entering Filter

```sql
UPDATE lab.customer_events
SET tenant_id = 42
WHERE tenant_id = 43
  AND event_id = 2;
```

Old row did not match; new row matches. The subscriber receives an INSERT for this row.

### 17.9. UPDATE Row Leaving Filter

```sql
UPDATE lab.customer_events
SET tenant_id = 43
WHERE tenant_id = 42
  AND event_id = 1;
```

Old row matched; new row does not match. The subscriber receives a DELETE for that row.

### 17.10. Verify Target Data

On the subscriber:

```sql
SELECT *
FROM lab.customer_events
ORDER BY tenant_id, event_id;
```

There is no `internal_payload` column; rows in the subscriber reflect the active filter condition after changes apply.

### 17.11. Verify TRUNCATE Is Not Published

```sql
SELECT pubname, pubtruncate
FROM pg_publication
WHERE pubname = 'lab_tenant_42_pub';
```

The value must be false per the example publication configuration. Do not test TRUNCATE in production to verify.

### 17.12. Clean Up Lab

Only in the lab environment:

```sql
-- On subscriber: stop and drop subscription first
DROP SUBSCRIPTION IF EXISTS lab_tenant_42_sub;

-- On publisher:
DROP PUBLICATION IF EXISTS lab_tenant_42_pub;
DROP TABLE IF EXISTS lab.customer_events;
```

If the subscription uses a replication slot on the publisher, verify the slot has been released or handled per procedure before dropping the publication.

---

## 18. Common Misconceptions

**1. "Row filters are supported starting in PostgreSQL 14."** False. Row filters were introduced in PostgreSQL 15.

**2. "Column lists are a PostgreSQL 18 feature."** False. Column lists exist since PostgreSQL 15; PostgreSQL 18 added generated-column replication.

**3. "Only the publisher needs to be 15+; subscriber version does not matter."** False. Subscribers before 15 ignore row filters and column lists during initial data synchronization.

**4. "Row filters only check the new row on UPDATE."** False. PostgreSQL evaluates both old and new rows, and can transform UPDATE into INSERT or DELETE.

**5. "Filter tenant_id = 42 will automatically delete all other tenants' rows from the subscriber."** No. Filters apply to emitted changes; changing a filter does not automatically reconcile all existing data.

**6. "Row filters can use custom functions."** No. Expressions are restricted; user-defined functions/operators/types/collations and non-immutable built-ins are disallowed.

**7. "Row filters can reference any column."** Only when the publication publishes INSERT exclusively. With UPDATE/DELETE, filter columns must belong to the replica identity.

**8. "Column lists can omit the primary key in all cases."** No. For UPDATE/DELETE, all replica identity columns must be retained.

**9. "Column lists allow renaming or computing columns."** No. They only accept simple column references.

**10. "Column lists guarantee excluded column data is inaccessible."** No. This is not a security boundary.

**11. "Row filters apply to TRUNCATE."** No. TRUNCATE is not filtered by rows.

**12. "Column lists apply to TRUNCATE."** No. TRUNCATE carries no row columns.

**13. "Multiple row filters can be combined with AND."** No. Filters for the same table/operation across multiple publications are combined with OR.

**14. "An unfiltered publication does not affect another filtered publication."** False. An unfiltered publication can render the other filter redundant.

**15. "Column lists from multiple publications can be unioned."** No. One subscription does not support the same table with differing column lists.

**16. "Column order in a column list is the transmission order."** No. Column name order is not preserved as positional ordering.

**17. "Having no column list is equivalent to listing all current columns."** No. Omitting the list includes future added columns; an explicit column list does not.

**18. "The subscriber must have an identical schema to the publisher."** Not necessarily, though it must have all published columns with compatible types; extra columns must get valid values on INSERT.

**19. "DDL is replicated alongside row changes."** No. Logical replication does not automatically emit DDL.

**20. "Changing a row filter automatically backfills old data."** No. A separate initial sync/backfill/reconciliation is required.

**21. "FOR TABLES IN SCHEMA supports column lists."** No. Column lists are not supported when a publication also uses FOR TABLES IN SCHEMA.

**22. "Partitioned tables always use the root's filter."** No. It depends on `publish_via_partition_root`.

**23. "Pre-18 subscribers always receive generated columns when the publisher enables the option."** No. Initial sync from a PostgreSQL 18 publisher to a pre-18 subscriber does not copy generated columns.

**24. "publish = 'update, delete' means initial sync does not copy rows."** No. Initial data synchronization does not obey the publish operation list.

**25. "Row filters replace RLS."** No. RLS and publication filters are two distinct mechanisms that can jointly affect data.

**26. "If the filter is right, subscribers can only ever see filtered data."** No. Security must be enforced on the publisher and at network/role boundaries.

**27. "pg_publication_tables is just metadata that does not need checking."** False. It is a vital place to confirm actual publication configuration.

**28. "Column lists always make replication faster."** Not guaranteed. Performance depends on decoding, WAL rate, network, apply, and workload.

**29. "copy_data = false automatically syncs old data."** No. It skips initial copy; a coordinated separate initial load is needed.

**30. "TRUNCATE is safe for partial-data subscribers because row filters restrict tenants."** False. Disable truncate publishing or design explicit semantics.

---

## 19. Practice Exercises and Answers

### Exercise 1 — Version

**Question:** Which PostgreSQL version first supported row filters and column lists?

**Answer:** PostgreSQL 15.

### Exercise 2 — Older Publisher

**Question:** Can a PostgreSQL 14 publisher create a publication with a WHERE row filter?

**Answer:** No. The syntax was introduced in PostgreSQL 15.

### Exercise 3 — Older Subscriber

**Question:** Publisher 15, subscriber 14: does initial sync apply the row filter?

**Answer:** No. Subscribers prior to 15 copy all rows during initial synchronization.

### Exercise 4 — Column List

**Requirement:** Publish only id and status.

```sql
CREATE PUBLICATION p_orders
FOR TABLE sales.orders (id, status);
```

### Exercise 5 — Row Filter

**Requirement:** Publish only tenant 42.

```sql
CREATE PUBLICATION p_tenant_42
FOR TABLE sales.orders
WHERE (tenant_id = 42);
```

### Exercise 6 — Combined

**Requirement:** Publish only tenant 42 and four columns.

```sql
CREATE PUBLICATION p_tenant_42
FOR TABLE sales.orders (tenant_id, order_id, status, amount)
WHERE (tenant_id = 42);
```

### Exercise 7 — NULL

**Question:** If a row filter returns NULL, is the row published?

**Answer:** No. Only TRUE is retained.

### Exercise 8 — Immutable Expression

**Question:** Can now() be used in a row filter?

**Answer:** No. It is a non-immutable function.

### Exercise 9 — User-Defined Function

**Question:** Can a custom function be called in a row filter?

**Answer:** No. Row filters only allow simple expressions per PostgreSQL rules.

### Exercise 10 — Replica Identity

**Question:** For UPDATE/DELETE, where must row filter columns belong?

**Answer:** Replica identity.

### Exercise 11 — Column List Identity

**Question:** What must the column list of a publication with UPDATE/DELETE include?

**Answer:** All replica identity columns.

### Exercise 12 — Insert Only

**Question:** If a publication only publishes INSERT, can the filter use a column outside the replica identity?

**Answer:** Yes.

### Exercise 13 — Update Entering Filter

**Question:** Old row does not match, new row matches: what does the subscriber receive?

**Answer:** INSERT.

### Exercise 14 — Update Leaving Filter

**Question:** Old row matches, new row does not match: what does the subscriber receive?

**Answer:** DELETE.

### Exercise 15 — Both Match

**Question:** Both old and new match: what does the subscriber receive?

**Answer:** UPDATE.

### Exercise 16 — TRUNCATE

**Question:** Does a row filter restrict TRUNCATE by tenant?

**Answer:** No. TRUNCATE is not restricted by row filters.

### Exercise 17 — Publish Option

**Requirement:** Do not publish TRUNCATE.

```sql
CREATE PUBLICATION p_partial
FOR TABLE sales.orders WHERE (tenant_id = 42)
WITH (publish = 'insert, update, delete');
```

### Exercise 18 — Multiple Filters

**Question:** How do two publications on the same table with filters tenant 42 and 43 combine?

**Answer:** OR; the subscription receives tenant 42 or 43 if both publications are subscribed.

### Exercise 19 — Unfiltered Publication

**Question:** Can an unfiltered publication invalidate another filter?

**Answer:** Yes. It can publish all rows for that operation.

### Exercise 20 — Column List Conflict

**Question:** Can one subscription follow the same table from two publications with different column lists?

**Answer:** Not supported.

### Exercise 21 — Column Order

**Question:** Does a column list preserve column order?

**Answer:** No. Logical replication maps by column name.

### Exercise 22 — Subscriber Schema

**Question:** Can a subscriber have extra local columns?

**Answer:** Yes, provided they receive valid values on INSERT apply, e.g., nullable or having a default.

### Exercise 23 — Future Column

**Question:** Without declaring a column list, are columns added later published automatically?

**Answer:** Yes. With an explicit column list, new columns are not added automatically.

### Exercise 24 — Partition Root

**Question:** Which parameter decides whether row filter/column list is taken from the root or leaf partition?

**Answer:** `publish_via_partition_root`.

### Exercise 25 — Initial Sync

**Question:** Does initial sync obey the publish operation list?

**Answer:** No. The publish option selects DML changes, not copying existing data.

### Exercise 26 — copy_data

**Question:** Does copy_data=false perform an initial copy?

**Answer:** No. A separate initial load is required.

### Exercise 27 — PostgreSQL 18

**Question:** Which version added generated-column replication?

**Answer:** PostgreSQL 18.

### Exercise 28 — Catalog

**Requirement:** View row filters and column lists.

```sql
SELECT pubname, schemaname, tablename, attnames, rowfilter
FROM pg_publication_tables;
```

### Exercise 29 — Version Check

**Requirement:** Check whether the publisher is version 15+.

```sql
SELECT current_setting('server_version_num')::integer >= 150000;
```

### Exercise 30 — Security

**Question:** Can a column list replace publisher-side security controls?

**Answer:** No. A column list is not a security boundary.

---

## 20. Deployment Checklist

### Version

1. Confirm the publisher version is PostgreSQL 15+.
2. Confirm the subscriber version and initial-sync behavior.
3. If using generated columns, confirm publisher/subscriber support PostgreSQL 18.
4. Read release notes for the exact versions.

### Publication

5. Define row scope by tenant/region/business rule.
6. Choose simple, immutable expressions.
7. With UPDATE/DELETE, use only filter columns belonging to replica identity.
8. Select the required column list.
9. Retain all replica identity columns in the list when UPDATE/DELETE is enabled.
10. Verify the table is not included in another unfiltered publication.
11. Verify multiple filters OR together as intended.
12. Avoid column-list mismatches for the same table in one subscription.
13. Disable TRUNCATE publishing for partial-data subscribers unless special semantics exist.

### Subscriber

14. Create target tables with all published columns.
15. Check data types, nullability, defaults, and replica identity.
16. Decide copy_data true/false.
17. If subscriber is pre-15, handle initial sync copying all rows/columns.
18. If subscriber is pre-18, handle generated columns initial sync.
19. Prepare DML apply privileges and replication connection.

### Operations

20. Inspect pg_publication_tables.
21. Inspect pg_subscription and pg_stat_subscription.
22. Monitor table synchronization states.
23. Reconcile rows/columns against a cutover point.
24. Check whether filter changes require backfill/cleanup.
25. Coordinate schema migrations on both publisher and subscriber.
26. Verify RLS/role context.
27. Do not use filters/lists as security boundaries.
28. Monitor WAL, replication lag, and apply errors.
29. Test INSERT/UPDATE/DELETE entering/leaving the filter.
30. Test restore/recovery and runbooks before production rollout.

---

## 21. Summary

Row filters and column lists enable logical replication to publish a subset of a table's data. Row filters decide **which rows** are sent; column lists decide **which columns** are sent. Both features were introduced in PostgreSQL 15 and carry important constraints regarding replica identity, initial synchronization, partitioning, multiple publications, and version compatibility.

Key takeaways:

- The publisher must be PostgreSQL 15 or later to declare row filters and column lists.
- Pre-PostgreSQL 15 subscribers ignore row filters/column lists during initial data synchronization; they may copy all rows and columns.
- PostgreSQL 18 adds generated-column replication; pre-18 subscribers have limitations when initially copying generated columns.
- If a publication has UPDATE/DELETE, filter columns must belong to replica identity and the column list must contain all identity columns.
- UPDATE is evaluated on both old and new rows; membership changes can be emitted as INSERT or DELETE.
- Row filters accept only simple expressions, disallowing user-defined functions/operators/types/collations, system columns, or non-immutable built-ins.
- Column lists accept only simple column names; transformations, aliases, or renames are not supported.
- Row filters and column lists do not restrict TRUNCATE. For partial-data subscribers, truncate publishing is typically disabled.
- Row filters from multiple publications for the same table/operation combine with OR; differing column lists for the same table in one subscription are not supported.
- Partition root vs. leaf determines which filter and column list are used via `publish_via_partition_root`.
- Initial data synchronization applies row filters/column lists based on subscriber version; the publish operation list does not control initial copy.
- Changing a filter or column list does not automatically backfill/reconcile existing data. Controlled schema migration, initial load, or backfill is needed.
- Row filters and column lists are not security boundaries; protect data on the publisher and at the network/role layers.

**Self-check question:** A PostgreSQL 18 publisher publishes the orders table for tenant 42 with a row filter and column list, while the subscriber runs PostgreSQL 14. Why might the subscriber receive more rows and columns than expected during initial sync? Because initial synchronization on pre-PostgreSQL 15 subscribers does not apply those two features. To deploy safely, check versions at both ends, replica identity, target schema, publish options, and any other publications sharing the table.

### Official PostgreSQL Documentation

- [PostgreSQL 15 Release Notes — row filters and column lists](https://www.postgresql.org/docs/15/release-15.html).
- [CREATE PUBLICATION — PostgreSQL 15](https://www.postgresql.org/docs/15/sql-createpublication.html).
- [Row Filters — PostgreSQL 15](https://www.postgresql.org/docs/15/logical-replication-row-filter.html).
- [Column Lists — PostgreSQL 15](https://www.postgresql.org/docs/15/logical-replication-col-lists.html).
- [CREATE PUBLICATION — Current](https://www.postgresql.org/docs/current/sql-createpublication.html).
- [Row Filters — Current](https://www.postgresql.org/docs/current/logical-replication-row-filter.html).
- [Column Lists — Current](https://www.postgresql.org/docs/current/logical-replication-col-lists.html).
- [Publication and Replica Identity — Current](https://www.postgresql.org/docs/current/logical-replication-publication.html).
- [Logical Replication Security — Current](https://www.postgresql.org/docs/current/logical-replication-security.html).
- [Logical Replication Architecture and Initial Snapshot — Current](https://www.postgresql.org/docs/current/logical-replication-architecture.html).
- [PostgreSQL 18 Release Notes — generated columns in logical replication](https://www.postgresql.org/docs/current/release-18.html).
- [CREATE SUBSCRIPTION — Current](https://www.postgresql.org/docs/current/sql-createsubscription.html).
- [Monitoring Statistics — Current](https://www.postgresql.org/docs/current/monitoring-stats.html).
