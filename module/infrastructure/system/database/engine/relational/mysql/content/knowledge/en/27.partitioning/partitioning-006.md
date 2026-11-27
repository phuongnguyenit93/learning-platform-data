# Foreign Key, Storage Engine, and Data Type Limitations by Version

Partitioning can help split a large table into smaller data units for lifecycle management, purging old data, and enabling partition pruning. However, not every table can be partitioned while keeping its existing foreign keys, primary keys, unique keys, and storage engine intact.

A design that ran fine on MySQL 5.7 may no longer be valid after upgrading to MySQL 8.0 because the partitioning architecture and list of supported storage engines changed. Partition key data types, partitioning expressions, and unique constraints also have specific restrictions. Failing to check them beforehand can cause `ALTER TABLE` failures or force data model changes.

This lesson focuses on the limitations to check before creating a partitioned table or converting an existing table to partitioning: foreign keys, primary/unique key relationships, storage engines, data types, partitioning expressions, and differences across MySQL versions.

## 1. Partitioning Does Not Remove Table Constraints

Partitioning divides a table's rows into partitions according to a rule. At the SQL level, applications still query a single logical table name; MySQL determines which partitions to access based on the partitioning expression.

Example event table split by month:

```sql
CREATE TABLE events (
    id BIGINT UNSIGNED NOT NULL,
    created_at DATETIME NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    payload JSON NULL,
    PRIMARY KEY (id, created_at)
)
ENGINE=InnoDB
PARTITION BY RANGE COLUMNS (created_at) (
    PARTITION p2026_01 VALUES LESS THAN ('2026-02-01'),
    PARTITION p2026_02 VALUES LESS THAN ('2026-03-01'),
    PARTITION p2026_03 VALUES LESS THAN ('2026-04-01'),
    PARTITION p_future VALUES LESS THAN (MAXVALUE)
);
```

Partitioning does not turn partitions into independent tables as far as constraints are concerned. Rules regarding primary keys, unique keys, foreign keys, and storage engines must still satisfy MySQL's requirements.

Before partitioning, answer:

- Does the table currently participate in any foreign key relationship as a child or parent?
- Do all primary keys and unique keys include the full partition key?
- Does the current storage engine support partitioning on the target version?
- Is the data type valid for the selected partitioning method?
- Does the partitioning expression use functions or operators permitted by MySQL?
- Will changing keys or engine alter application semantics?

## 2. Storage Engine Differences Across MySQL 5.7, 8.0, and 9.7

The storage engine determines how data is stored and many table capabilities. Partitioning also depends on the engine.

| Version | Partitioning support | Points to note |
|---|---|---|
| MySQL 5.7 | Had a generic partitioning handler with broader engine support; some engines still unsupported | MERGE, FEDERATED, and CSV are unsupported; InnoDB has foreign key restrictions; NDB only supports KEY/LINEAR KEY in production configurations |
| MySQL 8.0 | Partitioning is provided by native handlers in InnoDB and NDB | MyISAM, MERGE, CSV, FEDERATED, and engines without native handlers cannot create partitioned tables |
| MySQL 9.7 | Only InnoDB and NDB support native partitioning | Core restrictions on foreign keys, unique keys, and data types still apply; NDB has specific rules |

### 2.1. MySQL 5.7

MySQL 5.7 used a generic partitioning handler and supported partitioning across more storage engines than MySQL 8.0. Still, support did not mean every engine worked:

- MERGE is incompatible with user-defined partitioning.
- FEDERATED does not support partitioning.
- CSV does not support partitioning.
- InnoDB can be partitioned, but does not support foreign keys on partitioned tables.
- NDB only supports KEY or LINEAR KEY in production-supported configurations.

When upgrading from 5.7, do not assume a partitioned table using an older engine will continue working as before on 8.0.

### 2.2. MySQL 8.0

Starting in MySQL 8.0, partitioning is provided via native storage engine handlers. Only InnoDB and NDB support partitioning.

For example, specifying ENGINE=MyISAM on a partitioned table fails with an error stating the engine does not implement partitioning. MySQL does not automatically convert a table to InnoDB just because the statement includes PARTITION BY.

With InnoDB, no separate partitioning plugin needs to be enabled. However, foreign key and unique key restrictions still apply.

### 2.3. MySQL 9.7

MySQL 9.7 continues limiting partitioning to InnoDB and NDB. NDB only supports KEY or LINEAR KEY for user-defined partitioning; RANGE, LIST, and HASH are not applied as with InnoDB. For an NDB table with explicit partition keys declared, the table must have an explicit primary key and all columns in the partitioning expression must belong to the primary key. The case of PARTITION BY KEY() without listing columns follows specific rules.

Do not rely on this comparison table instead of testing on the exact minor version your system deploys. During upgrades, test CREATE TABLE/ALTER TABLE on the target MySQL release with the real schema and save the DDL results.

### 2.4. All Partitions in a Table Use the Same Storage Engine

All partitions of the same table must share the same storage engine. You cannot create January's partition with InnoDB, February's with MyISAM, and March's with ARCHIVE inside the same table.

MySQL 8.0/9.7 may accept ENGINE syntax within individual PARTITION clauses in certain contexts, but partition-level engine options do not make partitions use different engines; the table's engine applies across all partitions.

## 3. Foreign Key Limitations with Partitioned InnoDB Tables

This is the most critical limitation when migrating an OLTP table with parent/child relationships to partitioning.

In MySQL 5.7, 8.0, and 9.7, partitioned InnoDB tables do not support foreign keys. The restriction applies in both directions:

1. A partitioned InnoDB table cannot contain a foreign key referencing another table.
2. Another InnoDB table also cannot declare a foreign key referencing a partitioned InnoDB table.

In other words, a partitioned InnoDB table cannot act as either a child table or a parent table in a foreign key relationship.

### 3.1. Example of a Child Table with a Foreign Key

Suppose the orders table references customers:

```sql
CREATE TABLE customers (
    id BIGINT UNSIGNED NOT NULL,
    name VARCHAR(150) NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;

CREATE TABLE orders (
    id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id, created_at),
    KEY idx_orders_customer (customer_id),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(id)
) ENGINE=InnoDB;
```

Attempting to partition orders while keeping the foreign key produces invalid DDL:

```sql
ALTER TABLE orders
PARTITION BY RANGE COLUMNS (created_at) (
    PARTITION p_old VALUES LESS THAN ('2026-01-01'),
    PARTITION p_new VALUES LESS THAN (MAXVALUE)
);
```

MySQL rejects the operation because InnoDB does not support foreign keys on user-partitioned tables. Adding the partition key to the primary key does not resolve this foreign key restriction.

### 3.2. Example of a Referenced Parent Table

Suppose the customers table is partitioned by a date column:

```sql
CREATE TABLE customers (
    id BIGINT UNSIGNED NOT NULL,
    created_at DATE NOT NULL,
    name VARCHAR(150) NOT NULL,
    PRIMARY KEY (id, created_at)
)
ENGINE=InnoDB
PARTITION BY RANGE COLUMNS (created_at) (
    PARTITION p_old VALUES LESS THAN ('2026-01-01'),
    PARTITION p_new VALUES LESS THAN (MAXVALUE)
);
```

Another table cannot create a foreign key referencing the partitioned InnoDB customers table:

```sql
CREATE TABLE customer_notes (
    id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    customer_created_at DATE NOT NULL,
    note TEXT,
    PRIMARY KEY (id),
    KEY idx_customer_notes_customer (customer_id, customer_created_at),
    CONSTRAINT fk_notes_customer
        FOREIGN KEY (customer_id, customer_created_at)
        REFERENCES customers(id, created_at)
) ENGINE=InnoDB;
```

This example uses the exact column pair from the parent's primary key specifically to isolate the partitioning restriction. Even when the referenced key is valid, MySQL still prohibits another InnoDB table from referencing a partitioned InnoDB table.

### 3.3. NDB Is a Scoped Exception

NDB Cluster allows tables partitioned by KEY or LINEAR KEY to have foreign keys or be referenced by foreign keys from other tables. This is a capability of the NDB storage engine within the NDB Cluster architecture, not an exception for InnoDB.

Do not switch to NDB merely to bypass InnoDB's foreign key restriction. NDB has its own deployment model, data types, indexing, transactions, operations, and cluster requirements. Evaluate the entire workload and architecture before choosing an engine.

### 3.4. Foreign Key Column Data Types

Even when neither table is partitioned, the foreign key column and referenced column must be compatible:

- Parent and child tables must use the same storage engine; neither may be a temporary table.
- Foreign keys are enforced by InnoDB and NDB; with other engines, FOREIGN KEY syntax may be accepted by the parser while constraints are not enforced by the engine. Do not assume that appearing in DDL guarantees referential integrity.
- For integer types, width and signed/unsigned must match; for DECIMAL, precision and scale must match.
- For nonbinary strings, character set and collation must match. String lengths do not have to be identical.
- Both the referenced key and the foreign key require suitable indexes. On the child table, the foreign key columns must form the leading prefix of an index in the same order.
- Index prefixes on foreign key columns are not supported. Since TEXT/BLOB require a prefix length when indexed, they cannot serve as foreign key columns.
- Foreign keys cannot reference virtual generated columns.

In MySQL 9.7, referencing a non-unique key in InnoDB is deprecated and governed by restrict_fk_on_non_standard_key. Migrate to standard PRIMARY KEY or UNIQUE KEY references before upgrading.

Starting in MySQL 9.6, the SQL layer handles InnoDB foreign keys by default; the innodb_native_foreign_keys variable controls delegating this handling back to InnoDB. Changing the enforcement layer does not lift the partitioning restriction: partitioned InnoDB tables still do not support foreign keys.

### 3.5. What Options Exist When Business Logic Requires Foreign Keys?

- Keep core relational tables unpartitioned if InnoDB foreign keys are required.
- Partition only historical/telemetry/archive tables that do not participate in foreign keys, after establishing clear referential validation mechanisms.
- If migrating data to a partitioned table, build application-level parent validation, orphan handling, and reconciliation jobs; never assume foreign keys remain engine-enforced.
- If both engine-level partitioning and foreign keys are required, evaluate NDB Cluster as a separate architectural option.

Never drop foreign keys just to make ALTER TABLE succeed. Before removing a constraint, establish where existence checks, parent delete/update propagation, and orphan detection will live.

## 4. Rule Requiring the Partition Key in Every Unique Key

MySQL requires all columns used in the partitioning expression to appear in every unique key on the table. This rule includes the PRIMARY KEY because a primary key is also a unique key.

Example partitioning by created_at:

```sql
CREATE TABLE events (
    id BIGINT UNSIGNED NOT NULL,
    created_at DATETIME NOT NULL,
    payload JSON,
    PRIMARY KEY (id)
)
ENGINE=InnoDB
PARTITION BY RANGE COLUMNS (created_at) (
    PARTITION p2026 VALUES LESS THAN ('2027-01-01'),
    PARTITION p_future VALUES LESS THAN (MAXVALUE)
);
```

This definition is invalid because the partition key created_at is not in primary key (id).

Structural key fix:

```sql
CREATE TABLE events (
    id BIGINT UNSIGNED NOT NULL,
    created_at DATETIME NOT NULL,
    payload JSON,
    PRIMARY KEY (id, created_at)
)
ENGINE=InnoDB
PARTITION BY RANGE COLUMNS (created_at) (
    PARTITION p2026 VALUES LESS THAN ('2027-01-01'),
    PARTITION p_future VALUES LESS THAN (MAXVALUE)
);
```

The new definition satisfies the partition key and unique key rule. However, primary key (id, created_at) only guarantees uniqueness of the pair; it does not guarantee id alone is unique across the entire table.

### 4.1. The Rule Applies to Every Unique Index

Suppose a table has:

```sql
PRIMARY KEY (id, created_at),
UNIQUE KEY uk_external_ref (external_ref)
```

When partitioning by created_at, the unique key on external_ref is still invalid because it lacks created_at. You must alter the unique key to include the partition key, such as:

```sql
UNIQUE KEY uk_external_ref_created (external_ref, created_at)
```

However, the new key only enforces that external_ref and created_at together are unique. It allows the same external_ref to appear on two different timestamps. If business logic requires external_ref to be globally unique, this is a change in semantics, not merely syntax.

### 4.2. Consequences for Globally Unique IDs

Time-based partitioning commonly wants created_at as the partition key to simplify dropping old partitions. Yet if the application relies on PRIMARY KEY(id) or UNIQUE(external_id), adding created_at as the partition key forces every unique key to include created_at.

Options to evaluate:

- Keep the table unpartitioned if global uniqueness is mandatory and must be enforced directly by MySQL.
- Use a composite key containing the partition key and accept composite uniqueness semantics.
- Use an unpartitioned registry table to enforce global IDs/business keys, backed by well-designed transactions and sync flows.
- Use distributed IDs/UUIDs to reduce collision probability at ID generation time, while recognizing this does not replace a global unique constraint in a partitioned table.

Never drop unique keys assuming application-generated IDs are sufficient unless a strategy for detecting and handling duplicates exists.

Technically, if a table has no unique keys at all, the rule requiring partition columns in every unique key no longer applies. However, removing all primary/unique keys eliminates database uniqueness protection and is rarely a safe fix.

### 4.3. Multi-Column Partitioning Expressions

If the partitioning expression uses multiple columns, all of those columns must appear in every unique key.

Example partitioning by tenant_id and date:

```sql
PARTITION BY HASH (tenant_id + YEAR(created_at))
PARTITIONS 16
```

Every unique key must include both tenant_id and created_at because both columns participate in the expression. The rule checks columns referenced in the expression, not just function names or return values.

## 5. Permitted Data Types for Partition Keys

Permitted data types depend on the partitioning method. You cannot take an arbitrary column and use it directly in every form of PARTITION BY.

### 5.1. RANGE, LIST, and HASH Using Integer Expressions

For expression-based RANGE, LIST, and HASH methods, the partitioning expression must return an integer value or NULL.

Example using YEAR(created_at):

```sql
CREATE TABLE sales (
    id BIGINT UNSIGNED NOT NULL,
    created_at DATETIME NOT NULL,
    amount DECIMAL(18,2) NOT NULL,
    PRIMARY KEY (id, created_at)
)
ENGINE=InnoDB
PARTITION BY RANGE (YEAR(created_at)) (
    PARTITION p_before_2025 VALUES LESS THAN (2025),
    PARTITION p2025 VALUES LESS THAN (2026),
    PARTITION p2026 VALUES LESS THAN (2027),
    PARTITION p_future VALUES LESS THAN (MAXVALUE)
);
```

YEAR(created_at) returns an integer, so it can serve as a partitioning expression. When using expressions, verify permitted functions and partition pruning behavior on the exact version.

You cannot simply write:

```sql
PARTITION BY RANGE (created_at)
```

with a DATETIME column as an integer-expression RANGE. To compare directly by date/time values, consider RANGE COLUMNS.

### 5.2. RANGE COLUMNS and LIST COLUMNS

RANGE COLUMNS and LIST COLUMNS take a column list instead of an integer expression. They support:

- Integer types.
- DATE and DATETIME.
- String/binary types such as CHAR, VARCHAR, BINARY, and VARBINARY.

DECIMAL, FLOAT, and non-integer numeric types are not supported as partitioning columns in these variants. TEXT and BLOB are also unsupported.

Example partitioning by DATE:

```sql
CREATE TABLE daily_metrics (
    metric_id BIGINT UNSIGNED NOT NULL,
    metric_date DATE NOT NULL,
    metric_value DECIMAL(18,4) NOT NULL,
    PRIMARY KEY (metric_id, metric_date)
)
ENGINE=InnoDB
PARTITION BY RANGE COLUMNS (metric_date) (
    PARTITION p2026_q1 VALUES LESS THAN ('2026-04-01'),
    PARTITION p2026_q2 VALUES LESS THAN ('2026-07-01'),
    PARTITION p2026_q3 VALUES LESS THAN ('2026-10-01'),
    PARTITION p2026_q4 VALUES LESS THAN ('2027-01-01'),
    PARTITION p_future VALUES LESS THAN (MAXVALUE)
);
```

Example LIST COLUMNS by region:

```sql
CREATE TABLE regional_targets (
    target_id BIGINT UNSIGNED NOT NULL,
    region_code CHAR(2) NOT NULL,
    target_amount DECIMAL(18,2) NOT NULL,
    PRIMARY KEY (target_id, region_code)
)
ENGINE=InnoDB
PARTITION BY LIST COLUMNS (region_code) (
    PARTITION p_asia VALUES IN ('VN', 'TH', 'SG'),
    PARTITION p_europe VALUES IN ('DE', 'FR', 'NL'),
    PARTITION p_americas VALUES IN ('US', 'CA', 'BR')
);
```

The LIST COLUMNS example illustrates string support. Every valid value must map to a partition in the declared lists; if the value domain changes, the partition definition must be updated.

### 5.3. KEY and LINEAR KEY

KEY/LINEAR KEY use MySQL's internal hashing function. Various supported data types may be used, except TEXT and BLOB.

Example:

```sql
CREATE TABLE tenant_events (
    id BIGINT UNSIGNED NOT NULL,
    tenant_code VARCHAR(40) NOT NULL,
    event_time DATETIME NOT NULL,
    PRIMARY KEY (id, tenant_code)
)
ENGINE=InnoDB
PARTITION BY KEY (tenant_code)
PARTITIONS 16;
```

Do not use prefix index parts as partition keys for KEY. Avoid declaring partition keys based on string prefixes like tenant_code(8); use the full column or a separate normalized column of a supported data type.

### 5.4. ENUM, SET, TEXT, and BLOB

| Data type | RANGE/LIST/HASH expression | RANGE/LIST COLUMNS | KEY/LINEAR KEY |
|---|---|---|---|
| INT/BIGINT | Usable directly if expression is valid | Supported | Supported |
| DATE/DATETIME | Usable via permitted integer-returning functions like YEAR/TO_DAYS | Directly supported | Supported |
| CHAR/VARCHAR/BINARY/VARBINARY | Needs a suitable integer expression | Supported | Supported |
| ENUM | Cannot be used in partitioning expressions | Not in the supported type list for COLUMNS | Can be used with KEY per KEY rules |
| SET | Should not be used directly in expressions | Not in the supported type list for COLUMNS | Can be used with KEY per KEY rules |
| TEXT/BLOB | Not supported | Not supported | Not supported |

For ENUM/SET, do not infer eligibility merely because they can be represented internally as numbers or strings. Rules differ between expressions and KEY. Verify against the exact partitioning method and target version.

### 5.5. Spatial and FULLTEXT

These restrictions apply to partitioned tables:

- Spatial columns such as POINT, LINESTRING, or GEOMETRY cannot be used in partitioned tables.
- Partitioned tables do not support FULLTEXT indexes or FULLTEXT search.
- Temporary tables cannot be partitioned.

If a table needs full-text search or GIS data, evaluate splitting that data into an unpartitioned table or a specialized search system.

## 6. Partitioning Expression and Function Restrictions

A partitioning expression must deterministically select a stable partition for a given data value. MySQL does not allow arbitrary SQL expressions.

Constructs prohibited in partitioning expressions:

- Stored procedures or stored functions.
- Loadable functions, plugins, or UDFs.
- Declared variables or user variables.
- Subqueries.
- Functions outside MySQL's permitted list.

Commonly permitted built-in functions include:

- YEAR(), MONTH(), DAY(), DAYOFMONTH(), DAYOFYEAR().
- TO_DAYS(), TO_SECONDS().
- UNIX_TIMESTAMP() when used with a TIMESTAMP column.
- DATEDIFF(), HOUR(), MINUTE(), SECOND().
- ABS(), CEILING(), FLOOR(), MOD().

The full list depends on version. Never assume any arbitrary built-in function is allowed in a partition expression.

### 6.1. Operators and Return Types

For expression partitioning with RANGE/LIST/HASH:

- +, -, and * are allowed when returning an integer or NULL.
- DIV is supported.
- Division operator / is not allowed in partitioning expressions.
- Bitwise operators such as |, &, ^, <<, >>, and ~ are not allowed.

Invalid expression example:

```sql
PARTITION BY RANGE (amount / 100)
```

Even if the expression appears numeric, the / operator is outside the permitted set. Use supported expressions and verify the return type.

### 6.2. SQL Mode Must Remain Stable

MySQL does not record the SQL mode used when creating a user-partitioned table in a way that guarantees identical expression interpretation forever. Changing SQL mode can alter expression evaluation, causing queries or INSERTs to route to different partitions or fail.

This also impacts replication. If source and replica run with different SQL modes, partition expressions may evaluate differently; rows may land in different partitions or statements may succeed on the source and fail on the replica.

Recommendations:

- Record @@GLOBAL.sql_mode and @@SESSION.sql_mode when designing tables.
- Keep SQL mode consistent between source and replica.
- Do not change SQL mode arbitrarily after creating partitioned tables.
- During upgrades or configuration changes, test INSERT/UPDATE with boundary values and partitioning expressions.

## 7. Notable Differences by Version

| Limitation | MySQL 5.7 | MySQL 8.0 | MySQL 9.7 |
|---|---|---|---|
| Storage engine partitioning | Generic handler, broader support though some engines unsupported | Native handler: InnoDB and NDB | Native handler: InnoDB and NDB |
| InnoDB foreign keys with partitioning | Not supported | Not supported | Not supported |
| NDB partitioning | KEY/LINEAR KEY | KEY/LINEAR KEY | KEY/LINEAR KEY |
| Unique keys must contain partition columns | Yes | Yes | Yes |
| TEXT/BLOB as partition key | Not supported | Not supported | Not supported |
| FULLTEXT on partitioned tables | Not supported | Not supported | Not supported |
| Spatial columns in partitioned tables | Not supported | Not supported | Not supported |
| Maximum partition count without NDB | 8192 including subpartitions | 8192 including subpartitions | 8192 including subpartitions |

### 7.1. Changes with KEY Partitioning and Prefix Indexes

In MySQL 8.0.21, using prefix key parts in KEY partitioning became deprecated with warnings; prefix columns are ignored when computing the partition key. If all key parts use prefixes, the statement can fail.

MySQL 9.7 documentation states explicitly that prefix columns are not supported in partitioning keys and statements may be rejected. When upgrading from 8.0, audit tables using PARTITION BY KEY() or KEY(column) with index prefixes.

### 7.2. ADD COLUMN ALGORITHM=INSTANT and EXCHANGE PARTITION

In MySQL 8.0, after executing ALTER TABLE ... ADD COLUMN ... ALGORITHM=INSTANT on a partitioned table, that table can no longer use EXCHANGE PARTITION under documented limitations. If the system uses partition exchange to load or archive data, verify the DDL plan and exchange capability before applying instant column additions.

### 7.3. More Partitions Is Not Always Better

For non-NDB tables, the maximum limit is 8192 partitions, including subpartitions. This is a technical limit, not a design target.

Hundreds or thousands of partitions increase metadata, file handles, table-opening overhead, DDL duration, and memory consumption for operations like LOAD DATA. Create only as many partitions as needed for pruning and maintenance; avoid overly tiny or excessive partitions without measurable benefit.

## 8. Design Example: Partitioning by Date While Still Needing a Unique Key

Suppose a system stores audit events by date, needs a primary key, and wants partitioning to purge expired data.

Invalid design:

```sql
CREATE TABLE audit_events (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    created_at DATETIME NOT NULL,
    actor_id BIGINT UNSIGNED NOT NULL,
    action_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (id)
)
ENGINE=InnoDB
PARTITION BY RANGE COLUMNS (created_at) (
    PARTITION p2026_01 VALUES LESS THAN ('2026-02-01'),
    PARTITION p2026_02 VALUES LESS THAN ('2026-03-01'),
    PARTITION p_future VALUES LESS THAN (MAXVALUE)
);
```

The primary key has only id and lacks created_at. MySQL rejects it because partition columns must appear in every unique key.

A design that can satisfy the unique key rule:

```sql
CREATE TABLE audit_events (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    created_at DATETIME NOT NULL,
    actor_id BIGINT UNSIGNED NOT NULL,
    action_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (id, created_at),
    KEY idx_audit_actor_time (actor_id, created_at)
)
ENGINE=InnoDB
PARTITION BY RANGE COLUMNS (created_at) (
    PARTITION p2026_01 VALUES LESS THAN ('2026-02-01'),
    PARTITION p2026_02 VALUES LESS THAN ('2026-03-01'),
    PARTITION p_future VALUES LESS THAN (MAXVALUE)
);
```

This design satisfies the unique key rule, yet the primary key no longer guarantees id alone is unique across the whole table. If APIs or external systems rely on id alone as a global unique identifier, resolve that before deployment.

Furthermore, a partitioned InnoDB table cannot hold a foreign key to an actor table nor be referenced by foreign keys from other tables. If audit events require engine-enforced referential integrity, consider keeping the table unpartitioned or altering the data model.

## 9. Checking a Schema Before Migrating to Partitioning

### 9.1. Confirm Version and Engine

```sql
SELECT VERSION();

SHOW TABLE STATUS LIKE 'orders';
SHOW CREATE TABLE orders;
```

Record the server version, engine, keys, constraints, and current definition. Do not rely on table names or old migrations to guess the actual engine.

### 9.2. List Foreign Keys in the Schema

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    CONSTRAINT_NAME,
    COLUMN_NAME,
    REFERENCED_TABLE_SCHEMA,
    REFERENCED_TABLE_NAME,
    REFERENCED_COLUMN_NAME
FROM information_schema.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA = DATABASE()
  AND REFERENCED_TABLE_NAME IS NOT NULL
ORDER BY TABLE_NAME, CONSTRAINT_NAME, ORDINAL_POSITION;
```

This query finds relationships where the table acts as a child. To find other tables referencing the table you intend to partition, filter REFERENCED_TABLE_NAME by the target table name.

### 9.3. Inspect Existing Partition Metadata

```sql
SELECT
    TABLE_NAME,
    PARTITION_NAME,
    PARTITION_METHOD,
    PARTITION_EXPRESSION,
    PARTITION_DESCRIPTION,
    TABLE_ROWS
FROM information_schema.PARTITIONS
WHERE TABLE_SCHEMA = DATABASE()
  AND PARTITION_NAME IS NOT NULL
ORDER BY TABLE_NAME, PARTITION_ORDINAL_POSITION;
```

### 9.4. Check Unique Keys

```sql
SELECT
    TABLE_NAME,
    INDEX_NAME,
    GROUP_CONCAT(
        COLUMN_NAME
        ORDER BY SEQ_IN_INDEX
        SEPARATOR ', '
    ) AS index_columns
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND NON_UNIQUE = 0
GROUP BY TABLE_NAME, INDEX_NAME
ORDER BY TABLE_NAME, INDEX_NAME;
```

Cross-check each unique index against all columns in the partitioning expression. Missing even a single partition column in one unique index makes the partition definition invalid.

### 9.5. Check Partition Columns and Expressions

Verify:

- Does the partition column's data type support the chosen method?
- Does the expression return integer/NULL if using RANGE/LIST/HASH expressions?
- Are the functions used in the permitted list?
- Are any TEXT/BLOB, spatial types, or prefix key parts used?
- Does the column appear in every unique key?
- Is the SQL mode identical between source and replica?

## 10. Migration Roadmap When the Current Schema Is Incompatible

If a table currently has incompatible foreign keys or unique keys, you cannot simply append PARTITION BY to CREATE/ALTER. A controlled change roadmap is needed.

1. **Snapshot schema and dependencies:** save SHOW CREATE TABLE, foreign key lists, unique keys, indexes, triggers, and related application flows.
2. **Identify integrity requirements:** clarify which keys must be globally unique and which relationships must be enforced by MySQL.
3. **Choose target engine:** confirm the MySQL version and partitioning-capable engine.
4. **Design the partition key:** pick columns with valid, stable data types aligned with queries and retention.
5. **Redesign unique keys:** ensure every unique key includes all partition columns; evaluate semantic changes.
6. **Handle foreign keys:** if using partitioned InnoDB, redesign the model or keep relational tables unpartitioned; never drop constraints before an alternative mechanism exists.
7. **Audit data:** check for duplicates, orphans, NULLs, and out-of-range partition values.
8. **Test DDL on the exact version:** verify CREATE/ALTER, indexes, partition pruning, and maintenance operations.
9. **Run a dry-run migration:** measure duration, locks, disk space, replication impact, and rollback/recovery time.
10. **Cut over and reconcile:** compare row counts, checksums, business keys, and referential relationships before and after.

If global uniqueness or foreign keys are non-negotiable, keeping the table unpartitioned may be the right decision. Alternatives include separate archive tables, batched retention, proper indexing, or sharding under a different architecture.

## 11. Common Errors and How to Interpret Them

| Symptom | Cause | Resolution |
|---|---|---|
| Engine does not implement partitioning | Using MyISAM or another unsupported engine on MySQL 8.0/9.7 | Select InnoDB/NDB if appropriate and re-verify the schema |
| Foreign keys are not supported | Partitioned InnoDB table has or is referenced by an FK | Redesign relationships or keep the table unpartitioned |
| PRIMARY KEY must include all columns in partitioning function | Primary/unique key lacks a partition column | Redesign all unique keys and evaluate global uniqueness |
| Partition function returns wrong type | Expression does not return integer/NULL as required | Use supported functions/expressions or COLUMNS partitioning |
| Function not allowed in partition expression | Using a stored function, UDF, or unlisted function | Switch to a permitted built-in function |
| Cannot partition on TEXT/BLOB | Unsupported data type | Use a suitable normalized column or redesign the partition key |
| Cannot create FULLTEXT index | Partitioned tables do not support FULLTEXT | Offload full-text search to a separate table/index |
| Spatial column incompatible | Partitioned tables do not support spatial data types | Move GIS data to an unpartitioned table |
| Different partition placement on source/replica | Different SQL modes or mode-dependent expressions | Align SQL modes and audit expressions |
| EXCHANGE PARTITION fails after ADD COLUMN INSTANT | DDL operation restriction on partitioned tables | Verify migration order and exchange compatibility before ADD COLUMN |

## 12. Common Misconceptions

| Misconception | Reality |
|---|---|
| InnoDB supports foreign keys, so partitioned InnoDB tables also support them | InnoDB foreign keys and user-defined partitioning are incompatible |
| Only the primary key needs to include the partition key | Every unique key, including the primary key, must include all partition columns |
| Adding a partition column to a unique key leaves business semantics unchanged | Composite uniqueness is not equivalent to global uniqueness of the original column |
| Every storage engine can be partitioned | MySQL 8.0/9.7 only provide native partitioning in InnoDB and NDB |
| NDB and InnoDB support the same partition types | NDB only supports KEY/LINEAR KEY for user-defined partitioning |
| DATETIME can be used directly in any RANGE expression | RANGE expressions require integer returns; use RANGE COLUMNS for DATE/DATETIME |
| TEXT/BLOB works if given an index prefix | TEXT/BLOB are not supported as partition keys |
| Any built-in function works in partitioning expressions | Only a specific allowlist of functions is permitted |
| More partitions always mean faster queries | Many partitions increase metadata and management cost; 8192 is a technical cap, not a goal |
| Dropping foreign keys solves everything | An alternative mechanism is needed to guard referential integrity and reconcile orphans |

## 13. Checklist Before Creating or Upgrading a Partitioned Table

- Confirmed the exact MySQL version and storage engine?
- Does the engine have a native partitioning handler on the target version?
- Does the table have foreign keys as either child or parent?
- If using InnoDB, confirmed no FKs involve the partitioned table?
- If using NDB, is the partition method KEY/LINEAR KEY and does it meet PK requirements?
- Are all partition columns present in every primary/unique key?
- Does changing to composite keys break global uniqueness relied on by the application?
- Are data types valid for RANGE/LIST/HASH/COLUMNS/KEY?
- Are there incompatible TEXT/BLOB, spatial types, FULLTEXT indexes, or temporary tables?
- Does the partitioning expression use permitted functions and return the right type?
- Is SQL mode identical between source and replica?
- Is the partition count reasonable for storage size and maintenance workload?
- Are migration, validation, cutover, and rollback plans in place?
- Tested the DDL on the exact target MySQL version?

## 14. Official References

- [MySQL 5.7 — Restrictions and Limitations on Partitioning](https://dev.mysql.com/doc/mysql-partitioning-excerpt/5.7/en/partitioning-limitations.html)
- [MySQL 5.7 — Partitioning Limitations Relating to Storage Engines](https://dev.mysql.com/doc/mysql-partitioning-excerpt/5.7/en/partitioning-limitations-storage-engines.html)
- [MySQL 8.0 — Restrictions and Limitations on Partitioning](https://dev.mysql.com/doc/refman/8.0/en/partitioning-limitations.html)
- [MySQL 8.0 — Partitioning Keys, Primary Keys, and Unique Keys](https://dev.mysql.com/doc/refman/8.0/en/partitioning-limitations-partitioning-keys-unique-keys.html)
- [MySQL 8.0 — Partitioning Limitations Relating to Storage Engines](https://dev.mysql.com/doc/refman/8.0/en/partitioning-limitations-storage-engines.html)
- [MySQL 9.7 — Partitioning Overview](https://dev.mysql.com/doc/refman/9.7/en/partitioning-overview.html)
- [MySQL 9.7 — Restrictions and Limitations on Partitioning](https://dev.mysql.com/doc/refman/9.7/en/partitioning-limitations.html)
- [MySQL 9.7 — Foreign Key Constraints](https://dev.mysql.com/doc/refman/9.7/en/create-table-foreign-keys.html)
- [MySQL 8.0 — COLUMNS Partitioning and permitted data types](https://dev.mysql.com/doc/refman/8.0/en/partitioning-columns.html)
- [MySQL 8.0 — KEY Partitioning](https://dev.mysql.com/doc/refman/8.0/en/partitioning-key.html)
- [MySQL 9.7 — COLUMNS Partitioning and permitted data types](https://dev.mysql.com/doc/refman/9.7/en/partitioning-columns.html)
- [MySQL 9.7 — KEY Partitioning](https://dev.mysql.com/doc/refman/9.7/en/partitioning-key.html)
- [MySQL 9.7 — Partitioning Limitations Relating to Functions](https://dev.mysql.com/doc/refman/9.7/en/partitioning-limitations-functions.html)

## Conclusion

Before partitioning a MySQL table, simultaneously check foreign keys, primary/unique keys, storage engine, data types, and the partitioning expression. Partitioned InnoDB tables do not support foreign keys on either child or parent sides; every unique key must contain all columns in the partitioning expression; MySQL 8.0/9.7 only support native partitioning on InnoDB and NDB. RANGE/LIST/HASH expressions require integer results, whereas RANGE COLUMNS/LIST COLUMNS directly support integers, DATE/DATETIME, and eligible strings; TEXT/BLOB and spatial columns carry specific restrictions. Version differences, SQL mode, and changes to unique key semantics can directly impact migrations. Verify all of these conditions on the exact target version before running DDL, and preserve business constraints via an explicit alternative design if partitioning prevents MySQL from enforcing them.
