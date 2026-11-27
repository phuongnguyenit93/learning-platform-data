# Partitioning Key Requirements in UNIQUE and PRIMARY Keys

When a MySQL table is partitioned, the partitioning expression determines which partition each row is placed in. InnoDB must ensure unique constraints work properly across the entire table, even when rows reside in different partitions. Therefore, MySQL enforces an important rule: **every column used in the partitioning expression must appear in every UNIQUE key of the table, including the PRIMARY KEY**.

This rule directly affects primary key design, business keys, and how uniqueness is enforced when partitioning by date, tenant, or another attribute. If you partition by created_at while wanting order_id to be globally unique, PRIMARY KEY(order_id) does not satisfy MySQL's requirement. If you change it to PRIMARY KEY(created_at, order_id), MySQL accepts the design, but the new constraint only guarantees the pair of created_at and order_id is unique; individual order_id values can still repeat across two different dates.

In the **DATABASE_MYSQL** module, partitioning is commonly used to manage large tables, narrow query scope via partition pruning, and support data lifecycles. This lesson explains the UNIQUE/PRIMARY key rule, why it exists, valid and invalid DDL examples, its impact on business key semantics, and ways to preserve global uniqueness when the partition key differs from the business key.

## 1. MySQL's Core Rule

For a partitioned table, every column appearing in the partitioning expression must be part of **every unique key** declared on the table.

Unique keys here include:

- PRIMARY KEY.
- Any other UNIQUE INDEX or UNIQUE KEY.

Example table partitioned by created_at:

```sql
CREATE TABLE events (
    event_id BIGINT UNSIGNED NOT NULL,
    created_at DATE NOT NULL,
    event_type VARCHAR(40) NOT NULL,
    PRIMARY KEY (created_at, event_id),
    UNIQUE KEY uq_created_type (created_at, event_type)
)
ENGINE = InnoDB
PARTITION BY RANGE COLUMNS (created_at) (
    PARTITION p2025 VALUES LESS THAN ('2026-01-01'),
    PARTITION p2026 VALUES LESS THAN ('2027-01-01'),
    PARTITION pmax VALUES LESS THAN (MAXVALUE)
);
```

The partitioning expression uses created_at. Both the PRIMARY KEY and the UNIQUE KEY contain created_at, so the rule is satisfied.

A UNIQUE key may contain additional columns; what is mandatory is that no column participating in the partitioning expression may be omitted.

### 1.1. Multi-Column Partitioning Expressions

If the partitioning expression references multiple columns, all of those columns must be present in each unique key.

Example partitioning by HASH of tenant_id and region_id:

```sql
CREATE TABLE tenant_events (
    tenant_id BIGINT UNSIGNED NOT NULL,
    region_id INT UNSIGNED NOT NULL,
    event_id BIGINT UNSIGNED NOT NULL,
    external_ref VARCHAR(80) NOT NULL,
    PRIMARY KEY (tenant_id, region_id, event_id),
    UNIQUE KEY uq_tenant_region_ref (
        tenant_id,
        region_id,
        external_ref
    )
)
ENGINE = InnoDB
PARTITION BY HASH (tenant_id + region_id)
PARTITIONS 16;
```

The expression uses both tenant_id and region_id. Both columns appear in the PRIMARY KEY and the UNIQUE KEY.

If a unique key contains only tenant_id and omits region_id, that key is invalid with the partitioning expression above.

### 1.2. Functions in the Partitioning Expression Do Not Remove the Requirement

If the partitioning expression uses a function on a column, the referenced column must still appear in every unique key.

Example:

```sql
CREATE TABLE audit_events (
    event_id BIGINT UNSIGNED NOT NULL,
    created_at DATETIME NOT NULL,
    event_code VARCHAR(40) NOT NULL,
    PRIMARY KEY (created_at, event_id),
    UNIQUE KEY uq_created_event_code (created_at, event_code)
)
ENGINE = InnoDB
PARTITION BY RANGE (YEAR(created_at)) (
    PARTITION p2025 VALUES LESS THAN (2026),
    PARTITION p2026 VALUES LESS THAN (2027),
    PARTITION pmax VALUES LESS THAN MAXVALUE
);
```

Even though the expression is YEAR(created_at), the created_at column must still appear in every unique key.

Do not confuse a partitioning expression with an independent computed value: MySQL inspects the underlying columns used in the expression when enforcing the key rule.

## 2. Why Does MySQL Require the Partition Key in Unique Keys?

A unique index must detect two rows sharing the same key regardless of where they are stored. In a partitioned table, indexes are organized per partition; MySQL does not provide a single global unique index spanning all partitions.

The partitioning expression determines which partition holds each row. If all partition key columns are also inside the unique key, any two rows with the same unique key value necessarily have the same partition key value and are therefore routed to the same partition. The storage engine can then check uniqueness locally within that partition.

If the unique key did not contain the partition key, two rows could share the same unique key value while having different partition key values. They could be placed into two different partitions; without a global unique index, MySQL could not use a single partition's local index to detect a conflict in another partition.

Example partitioning by date:

- Row A: order_id = 9001, created_at = 2026-01-10.
- Row B: order_id = 9001, created_at = 2026-02-10.

The two rows have the same order_id but different created_at values, so they go into different time partitions. With only UNIQUE(order_id), enforcing uniqueness would require checking both partitions. MySQL's rule prevents declaring such a unique key on a partitioned table.

This is an intentional design limitation, not an accidental syntax quirk.

## 3. Invalid Example: Partitioning by Date When PRIMARY KEY Has Only ID

Suppose the initial requirements are:

- Partition orders by created_at to manage data by month/year.
- order_id is the primary key and must be unique.
- external_ref is a unique transaction code.

The following DDL is invalid:

```sql
CREATE TABLE orders_bad (
    order_id BIGINT UNSIGNED NOT NULL,
    created_at DATE NOT NULL,
    external_ref VARCHAR(80) NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (order_id),
    UNIQUE KEY uq_external_ref (external_ref)
)
ENGINE = InnoDB
PARTITION BY RANGE COLUMNS (created_at) (
    PARTITION p2025 VALUES LESS THAN ('2026-01-01'),
    PARTITION p2026 VALUES LESS THAN ('2027-01-01'),
    PARTITION pmax VALUES LESS THAN (MAXVALUE)
);
```

Both PRIMARY KEY(order_id) and UNIQUE(external_ref) lack created_at. MySQL rejects this definition.

Error messages typically belong to this family:

- A PRIMARY KEY must include all columns in the table's partitioning function.
- A UNIQUE INDEX must include all columns in the table's partitioning function.

The exact message may vary depending on version and which key is checked first. The meaning remains that unique keys must include the partition column.

### 3.1. Adding the Partition Key to the PRIMARY KEY

It can be changed to:

```sql
CREATE TABLE orders_by_date (
    order_id BIGINT UNSIGNED NOT NULL,
    created_at DATE NOT NULL,
    external_ref VARCHAR(80) NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (created_at, order_id),
    UNIQUE KEY uq_created_external_ref (created_at, external_ref),
    KEY idx_customer_created (customer_id, created_at)
)
ENGINE = InnoDB
PARTITION BY RANGE COLUMNS (created_at) (
    PARTITION p2025 VALUES LESS THAN ('2026-01-01'),
    PARTITION p2026 VALUES LESS THAN ('2027-01-01'),
    PARTITION pmax VALUES LESS THAN (MAXVALUE)
);
```

This DDL is valid under the partition-key-in-unique-key rule:

- PRIMARY KEY(created_at, order_id) contains created_at.
- UNIQUE(created_at, external_ref) contains created_at.
- The non-unique index idx_customer_created is not a unique key, so it is not required to contain the partition key.

However, the semantics have changed. The primary key guarantees the pair (created_at, order_id) is unique, not that order_id alone is unique. Likewise, UNIQUE(created_at, external_ref) only guarantees external_ref is unique within the same created_at, not across the entire table.

**Never assume that adding the partition key to a unique key preserves the original business uniqueness semantics.** This is the most common design error when converting an existing table to partitioning.

## 4. Valid Example: Per-Tenant Uniqueness When Partitioning by Tenant

Adding the partition key does not always weaken semantics. If the business requirement is already uniqueness within a tenant's scope, partitioning by tenant can align naturally with the business key.

For example, each tenant has its own external_ref, while two different tenants are allowed to use the same external_ref:

```sql
CREATE TABLE tenant_orders (
    tenant_id BIGINT UNSIGNED NOT NULL,
    order_id BIGINT UNSIGNED NOT NULL,
    external_ref VARCHAR(80) NOT NULL,
    created_at DATETIME NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (tenant_id, order_id),
    UNIQUE KEY uq_tenant_external_ref (tenant_id, external_ref),
    KEY idx_tenant_created (tenant_id, created_at)
)
ENGINE = InnoDB
PARTITION BY HASH (tenant_id)
PARTITIONS 16;
```

Here:

- The partitioning expression uses only tenant_id.
- The PRIMARY KEY includes tenant_id.
- The UNIQUE KEY includes tenant_id.
- All rows for the same tenant_id are routed to the same partition.
- UNIQUE(tenant_id, external_ref) ensures external_ref does not collide within a tenant, even when the tenant has many orders.

Query:

```sql
SELECT order_id, amount
FROM tenant_orders
WHERE tenant_id = 42
  AND external_ref = 'EXT-2026-0001';
```

The tenant_id predicate enables partition pruning; the unique index further supports lookup inside the corresponding partition.

If the requirement is for external_ref to be globally unique across the system, this design is insufficient: the same external_ref can appear under a different tenant. In that case, choose a more suitable partition key or add a global uniqueness mechanism in another structure.

## 5. UNIQUE Prefixes and the Partition Key

The partition key rule also applies to unique indexes using a string column prefix.

Example partitioning by tenant_id:

```sql
CREATE TABLE tenant_documents (
    tenant_id BIGINT UNSIGNED NOT NULL,
    document_id BIGINT UNSIGNED NOT NULL,
    path VARCHAR(2000) NOT NULL,
    PRIMARY KEY (tenant_id, document_id),
    UNIQUE KEY uq_tenant_path_prefix (tenant_id, path(120))
)
ENGINE = InnoDB
PARTITION BY HASH (tenant_id)
PARTITIONS 8;
```

The tenant_id key is present in the UNIQUE key, satisfying the partitioning rule. However, the UNIQUE prefix only enforces that the first 120 characters of path do not collide within a tenant; it does not enforce uniqueness of the full path string semantics.

Two independent requirements must be checked:

1. Does the unique key include all partition columns?
2. Does the unique key accurately represent business uniqueness?

A DDL statement can be valid for partitioning yet still wrong for business logic if the prefix is too short or if a composite key alters the uniqueness scope.

## 6. Can the Partition Column Sit in Any Position in a Unique Key?

The rule requires partition columns to appear in the unique key; it does not require them to always come first in the key.

Example partitioning by created_at:

```sql
CREATE TABLE events_position_demo (
    event_id BIGINT UNSIGNED NOT NULL,
    created_at DATE NOT NULL,
    source_id BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (event_id, created_at),
    UNIQUE KEY uq_source_date (source_id, created_at)
)
ENGINE = InnoDB
PARTITION BY RANGE COLUMNS (created_at) (
    PARTITION p2026 VALUES LESS THAN ('2027-01-01'),
    PARTITION pmax VALUES LESS THAN (MAXVALUE)
);
```

Both unique keys contain created_at, even though created_at is not the leading column of the PRIMARY KEY.

However, column position affects B-tree leftmost prefix usability. If queries typically filter by created_at and then event_id, the order (created_at, event_id) may fit better than (event_id, created_at). If queries typically search by event_id, the reverse order may be more useful.

Therefore, distinguish:

- **Partitioned table validity:** partition columns must appear in every unique key.
- **Query efficiency:** key part ordering must match the workload and leftmost prefix access.
- **Uniqueness semantics:** the set of columns in the unique key defines the scope over which values must be unique.

Do not reorder key columns just to satisfy the rule without examining primary queries first.

## 7. A Unique Key on a Partitioned Table Is Not a Global Unique Index

MySQL does not provide a global unique index for partitioned tables in a way that can enforce a key lacking the partition key across all partitions.

Suppose a table is partitioned by month:

```sql
CREATE TABLE payment_events (
    event_id BIGINT UNSIGNED NOT NULL,
    paid_at DATE NOT NULL,
    provider_txn_id VARCHAR(100) NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (paid_at, event_id),
    UNIQUE KEY uq_paid_provider_txn (paid_at, provider_txn_id)
)
ENGINE = InnoDB
PARTITION BY RANGE COLUMNS (paid_at) (
    PARTITION p202601 VALUES LESS THAN ('2026-02-01'),
    PARTITION p202602 VALUES LESS THAN ('2026-03-01'),
    PARTITION p202603 VALUES LESS THAN ('2026-04-01'),
    PARTITION pmax VALUES LESS THAN (MAXVALUE)
);
```

UNIQUE(paid_at, provider_txn_id) allows the same provider_txn_id to appear on two different dates. This is correct if business rules define transactions as unique per day; it is wrong if provider_txn_id must be unique across the whole system.

A query filtering only by provider_txn_id:

```sql
SELECT *
FROM payment_events
WHERE provider_txn_id = 'PSP-998877';
```

has no paid_at condition and may have to check multiple partitions. There is no global unique index on provider_txn_id to prevent duplicates across partitions.

Partition pruning and uniqueness are two separate concerns. Pruning reduces the number of partitions read when predicates contain the partition key; it does not create a global unique constraint for other columns.

## 8. Ways to Preserve Global Uniqueness When Partitioning by Date

If you need to partition large data by date while keeping an ID or business code globally unique, several common designs exist.

### 8.1. Unpartitioned Registry Table

Create a smaller, unpartitioned table holding the unique business key. The partitioned table stores time-partitioned detail rows.

Example registry table:

```sql
CREATE TABLE payment_id_registry (
    provider_txn_id VARCHAR(100) NOT NULL,
    paid_at DATE NOT NULL,
    event_id BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (provider_txn_id),
    UNIQUE KEY uq_registry_event_id (event_id)
) ENGINE = InnoDB;
```

Date-partitioned event table:

```sql
CREATE TABLE payment_events_partitioned (
    event_id BIGINT UNSIGNED NOT NULL,
    paid_at DATE NOT NULL,
    provider_txn_id VARCHAR(100) NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (paid_at, event_id),
    UNIQUE KEY uq_event_date_provider (paid_at, provider_txn_id)
)
ENGINE = InnoDB
PARTITION BY RANGE COLUMNS (paid_at) (
    PARTITION p202601 VALUES LESS THAN ('2026-02-01'),
    PARTITION p202602 VALUES LESS THAN ('2026-03-01'),
    PARTITION pmax VALUES LESS THAN (MAXVALUE)
);
```

When receiving a new transaction, the application writes to both the registry and the detail table within the same InnoDB transaction:

```sql
START TRANSACTION;

INSERT INTO payment_id_registry (
    provider_txn_id,
    paid_at,
    event_id
)
VALUES (
    'PSP-998877',
    '2026-01-18',
    700001
);

INSERT INTO payment_events_partitioned (
    event_id,
    paid_at,
    provider_txn_id,
    amount
)
VALUES (
    700001,
    '2026-01-18',
    'PSP-998877',
    125000.00
);

COMMIT;
```

If provider_txn_id already exists, the INSERT into the registry fails on its PRIMARY KEY; the transaction must roll back and handle the duplicate according to business rules. If the insert into the partitioned table fails, rolling back also reverts the registry entry.

Advantages:

- The registry enforces global uniqueness of provider_txn_id.
- The detail table remains partitioned by date.
- You can look up the date and event_id from the registry first, then query the exact partition.
- InnoDB transactions ensure both writes succeed or roll back together.

Limitations:

- The registry grows with the number of business keys retained.
- The application must maintain both tables in the same transaction and handle retries.
- MySQL InnoDB user-partitioned tables do not support foreign keys; you cannot rely on an FK to bind the registry to the partitioned table.
- Registry retention must be defined. If registry entries are purged too early, an old provider_txn_id could be re-ingested.

Never ignore a duplicate error in the registry and still insert into the detail table. Explicitly determine whether the request is an idempotent retry or a data conflict.

### 8.2. Aligning the Partition Key with the Uniqueness Scope

If the business key is unique per tenant, partitioning by tenant_id can be a natural fit:

```sql
CREATE TABLE tenant_payment_events (
    tenant_id BIGINT UNSIGNED NOT NULL,
    provider_txn_id VARCHAR(100) NOT NULL,
    paid_at DATETIME NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (tenant_id, provider_txn_id)
)
ENGINE = InnoDB
PARTITION BY HASH (tenant_id)
PARTITIONS 16;
```

In this example, the business key is the pair (tenant_id, provider_txn_id), and the partition key tenant_id is in the unique key. MySQL can enforce uniqueness of this pair.

If you need to query or purge data by time, partitioning by tenant may not fit. Choosing a partition key must balance queries, retention, data distribution, and uniqueness.

### 8.3. Using Application-Generated Global IDs

An application can generate UUID/ULID or distributed IDs to minimize collision probability across nodes. This is an ID generation strategy, not a substitute for a UNIQUE constraint in MySQL.

If partitioned by date with only PRIMARY KEY(paid_at, event_id), the database still does not guarantee that event_id alone cannot repeat across two dates. If strict database-level enforcement is required, use a registry or a partition key design compatible with the unique key.

### 8.4. Accepting Per-Partition Uniqueness Scope

Sometimes business rules only require a code to be unique within a day or month. In that case, including the partition key in the unique key expresses the desired semantics.

For example, UNIQUE(paid_at, provider_txn_id) ensures the same provider_txn_id cannot repeat within the same paid_at. If paid_at is DATE, two transactions with the same provider_txn_id on two different dates are allowed.

Document the uniqueness scope clearly in business and API specs; avoid calling this "globally unique provider_txn_id".

## 9. Inspecting a Table Before Partitioning

Before adding partitioning to an existing table, checklist the following:

1. Which columns does the partitioning expression use?
2. Does the current PRIMARY KEY contain all partition columns?
3. Does every current UNIQUE KEY contain all partition columns?
4. Will the composite key after adding the partition column still match business semantics?
5. Do business-key lookup queries need to search across partitions?
6. Are there global uniqueness requirements needing a registry or supporting structure?
7. Do tables have FOREIGN KEYs referencing or referenced by this table?
8. Does the partition key fit retention, pruning, and data distribution?

Inspect current DDL:

```sql
SHOW CREATE TABLE orders;
```

List indexes:

```sql
SHOW INDEX FROM orders;
```

Inspect partition metadata:

```sql
SELECT
    PARTITION_NAME,
    PARTITION_METHOD,
    PARTITION_EXPRESSION,
    PARTITION_DESCRIPTION
FROM information_schema.PARTITIONS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders'
ORDER BY PARTITION_ORDINAL_POSITION;
```

Inspect columns in each index:

```sql
SELECT
    INDEX_NAME,
    NON_UNIQUE,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    SUB_PART
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
```

In STATISTICS output, NON_UNIQUE = 0 identifies PRIMARY/UNIQUE indexes. Cross-check each of those indexes against all columns referenced in PARTITION_EXPRESSION. Do not check only the PRIMARY KEY; a single secondary UNIQUE KEY missing a partition column also renders the DDL invalid.

For partitioning expressions containing functions or complex expressions, identify every input column of the expression. PARTITION_EXPRESSION metadata displays the expression, but does not automatically verify that all unique keys are valid.

## 10. Key Design Workflow When Creating a Partitioned Table

A practical workflow:

### Step 1: Finalize the Partition Key Based on Workload

Select columns based on queries, retention, data size, and row distribution—for example, created_at for time-based retention or tenant_id for tenant-isolated workloads.

Do not choose a partition key merely to work around a unique key DDL error.

### Step 2: List Business Keys

Write down the exact requirements:

- Is order_id globally unique across the system?
- Is external_ref unique per tenant?
- Is provider_txn_id globally unique or only within a single day?
- Can a user share the same username across different tenants?

Do not infer uniqueness scope from column names.

### Step 3: Verify Every Unique Key

For every PRIMARY/UNIQUE key, verify whether all partition columns are present. If any are missing, the DDL violates partitioning rules.

### Step 4: Evaluate Semantics After Adding the Partition Key

For example:

- Changing UNIQUE(email) to UNIQUE(created_at, email) allows the same email to appear on two different dates.
- Changing PRIMARY KEY(order_id) to PRIMARY KEY(created_at, order_id) allows the same order_id on two different dates.
- Keeping UNIQUE(tenant_id, external_ref) when partitioning by HASH(tenant_id) preserves per-tenant uniqueness.

If semantics change, do not deploy until a compensating design is in place.

### Step 5: Choose How to Enforce Global Uniqueness

Options include:

- Aligning the partition key with the uniqueness scope.
- Using an unpartitioned registry table with global PRIMARY/UNIQUE keys.
- Using a central identity table or ID generation service, if architecture permits.
- Redesigning partitioning so all values requiring uniqueness are routed to the same partition.

Clearly define which layer is responsible for enforcing uniqueness and how retries/concurrency are handled.

### Step 6: Test DDL and Concurrency

Create the table in a test environment and verify:

- DDL is accepted.
- Duplicates within the same partition are rejected.
- Duplicates across different partitions behave according to designed semantics.
- Concurrent inserts cannot bypass unique constraints.
- Partition pruning works for primary queries.
- Purge/retention jobs do not delete registry entries prematurely.

### Step 7: Plan the Migration

For existing tables, check for duplicate data before changing keys. You may need to create a new table, backfill in batches, sync ongoing changes, and cut over the application in phases. Never assume ALTER TABLE adding partitions is lightweight or non-blocking; evaluate rebuild duration, metadata locks, temporary disk space, and replication lag.

## 11. Migration Example: Orders Table Partitioned by Date

Suppose the legacy table is:

```sql
CREATE TABLE orders_legacy (
    order_id BIGINT UNSIGNED NOT NULL,
    created_at DATE NOT NULL,
    external_ref VARCHAR(80) NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id),
    UNIQUE KEY uq_external_ref (external_ref)
) ENGINE = InnoDB;
```

Business requirements:

- order_id is globally unique across the system.
- external_ref is globally unique across the system.
- Detail data is partitioned by created_at.

Simply changing keys to:

```sql
PRIMARY KEY (created_at, order_id),
UNIQUE KEY (created_at, external_ref)
```

is insufficient, because global uniqueness semantics turned into per-day uniqueness.

One option is maintaining a registry:

```sql
CREATE TABLE order_identity_registry (
    order_id BIGINT UNSIGNED NOT NULL,
    external_ref VARCHAR(80) NOT NULL,
    created_at DATE NOT NULL,
    PRIMARY KEY (order_id),
    UNIQUE KEY uq_registry_external_ref (external_ref)
) ENGINE = InnoDB;
```

Detail table:

```sql
CREATE TABLE orders_partitioned (
    order_id BIGINT UNSIGNED NOT NULL,
    created_at DATE NOT NULL,
    external_ref VARCHAR(80) NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (created_at, order_id),
    UNIQUE KEY uq_partition_date_ref (created_at, external_ref),
    KEY idx_customer_created (customer_id, created_at)
) ENGINE = InnoDB
PARTITION BY RANGE COLUMNS (created_at) (
    PARTITION p2025 VALUES LESS THAN ('2026-01-01'),
    PARTITION p2026 VALUES LESS THAN ('2027-01-01'),
    PARTITION pmax VALUES LESS THAN (MAXVALUE)
);
```

When creating a new order, within the same transaction:

1. Insert order_id and external_ref into the registry so the database enforces global uniqueness.
2. Insert detail data into the partitioned table.
3. Commit when both operations succeed; roll back both if either fails.

The registry table has no foreign key to the partitioned table because InnoDB user-defined partitioned tables do not support foreign keys. The application must ensure both records are written in the same transaction and run periodic reconciliation checks.

When reading by order_id, look up created_at in the registry first, then query the partitioned table using both created_at and order_id to prune to the exact partition.

## 12. Foreign Keys and Related Limitations

In MySQL, InnoDB user-defined partitioned tables do not support foreign keys in current MySQL 8.0 releases. This means a partitioned table cannot contain foreign keys in the standard way and cannot be referenced by foreign keys from other tables.

Therefore, if the existing data model relies heavily on FOREIGN KEYs, partitioning must be evaluated at the data design level. A registry table can enforce uniqueness with its own PRIMARY/UNIQUE keys, while the relationship between the registry and partitioned details must be managed through transactions, application logic, and consistency verification workflows.

Do not disable foreign_key_checks and assume constraints will be enforced automatically on a partitioned table. That variable does not turn an unsupported design into a model with full foreign keys.

In addition, partitioning imposes restrictions on column types, expressions, indexes, and storage engines. Check the documentation for your exact MySQL version before choosing a partition method or altering production schemas.

## 13. Common Mistakes and Misconceptions

| Mistake | Consequence | How to handle |
|---|---|---|
| Adding the partition key only to PRIMARY KEY while forgetting secondary UNIQUEs | DDL is still rejected | Check every unique index |
| Thinking PRIMARY KEY(order_id) stays globally unique after changing to (created_at, order_id) | order_id can duplicate across dates | Use a registry or change the partitioning strategy |
| Thinking UNIQUE(created_at, email) equals UNIQUE(email) | Email is only unique within the same day | Define the exact uniqueness scope |
| Choosing a partition key for retention without considering business keys | Loss of ability to enforce global uniqueness | Design a registry/identity table |
| Thinking MySQL has a global unique index across partitions | DDL fails or semantics are wrong | Include partition columns in unique keys |
| Forgetting columns nested inside a partitioning expression | Invalid DDL | List all input columns of the expression |
| Checking only PRIMARY KEY during DDL review | Secondary unique index still lacks partition column | Inspect all rows with NON_UNIQUE = 0 |
| Using UUID to claim the database guarantees absolute uniqueness | No global UNIQUE constraint exists | Distinguish low collision probability from database enforcement |
| Using a UNIQUE prefix thinking the entire string is unique | Distinct values sharing a prefix may be rejected | Review prefix key semantics |
| Purging the registry too early when dropping old partitions | Previously used IDs can be reused | Design retention and idempotency carefully |
| Ignoring InnoDB partitioning FOREIGN KEY limitations | Relational model is not protected as intended | Re-evaluate schema and integrity strategy |

## 14. Checklist Before Taking a Partitioned Table to Production

**Partition design:**

- Partitioning expression chosen based on queries, retention, and data distribution.
- All columns participating in the expression are listed, including columns inside functions.
- Every PRIMARY KEY contains all partition columns.
- Every secondary UNIQUE KEY contains all partition columns.
- Uniqueness scope is clearly defined as global, per-tenant, per-day, or per-partition.

**Data integrity:**

- Did not inadvertently weaken UNIQUE(email), UNIQUE(order_id), or other business keys.
- Registry/identity table is in place if global uniqueness is needed.
- Registry and partitioned detail writes happen in the same transaction.
- Reconciliation checks exist when FOREIGN KEYs cannot be used.
- Policy keeps registry retention synchronized with partition retention.

**Queries and operations:**

- Primary queries include conditions on the partition key when pruning is needed.
- Non-unique indexes are designed for the workload after considering partitioning.
- Tested duplicate inserts within the same partition and across different partitions.
- Tested concurrent inserts and retries.
- Evaluated DDL migration, metadata locks, rebuild time, and replication lag.
- Verified syntax and limitations against the exact production MySQL version.

## 15. Key Takeaways

- Every column used in the partitioning expression must be present in every unique key of the table, including the PRIMARY KEY.
- If the expression uses multiple columns or functions on columns, all input columns must be included in each unique key.
- This rule enables MySQL to verify uniqueness inside the partition storing the row; MySQL does not provide a global unique index across all partitions.
- Adding the partition key to a unique key can alter semantics: UNIQUE(order_id) becoming UNIQUE(created_at, order_id) no longer enforces globally unique order_id values.
- Partitioning by tenant_id fits when the business key is the pair (tenant_id, business_key) and all rows of the same tenant land in the same partition.
- Prefix UNIQUE indexes still restrict uniqueness enforcement to the prefix length, independently of the partition key rule.
- A partition key does not have to lead the unique key to satisfy the rule, yet column order still affects leftmost prefix usage and query performance.
- When global uniqueness is required alongside date partitioning, consider an unpartitioned registry/identity table written in the same transaction as the detail table.
- Application-generated UUIDs/ULIDs do not automatically create a global UNIQUE constraint inside the database.
- InnoDB user-defined partitioned tables do not support foreign keys in MySQL 8.0; an appropriate data integrity strategy is required.
- Inspect SHOW CREATE TABLE, SHOW INDEX, and INFORMATION_SCHEMA.STATISTICS before migrating.
- Test duplicates, concurrent inserts, partition pruning, retention, and replication prior to deployment.

Partitioning must align with both data access paths and business uniqueness rules. Before finalizing a partition key, list all keys requiring uniqueness and define the uniqueness scope of each; if the two requirements conflict, design a registry or change the partitioning strategy before migrating.

## References

- MySQL 8.0 Reference Manual — Partitioning Keys, Primary Keys, and Unique Keys: https://dev.mysql.com/doc/refman/8.0/en/partitioning-limitations-partitioning-keys-unique-keys.html
- MySQL 8.0 Reference Manual — Partitioning Limitations Relating to Storage Engines: https://dev.mysql.com/doc/refman/8.0/en/partitioning-limitations-storage-engines.html
- MySQL 8.0 Reference Manual — Partition Pruning: https://dev.mysql.com/doc/refman/8.0/en/partitioning-pruning.html
- MySQL 8.0 Reference Manual — Partition Management: https://dev.mysql.com/doc/refman/8.0/en/partitioning-management.html
