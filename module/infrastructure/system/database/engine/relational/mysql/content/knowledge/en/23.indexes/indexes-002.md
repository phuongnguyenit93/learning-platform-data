# PRIMARY, UNIQUE, and Secondary Indexes in InnoDB

InnoDB uses B-trees to organize data and locate rows. A `PRIMARY KEY` identifies the primary key of a table, `UNIQUE` ensures one or more columns contain unique values according to MySQL comparison rules, and secondary indexes support searching and sorting on other columns. These three concepts are related, yet serve distinct purposes.

In InnoDB, the primary key is typically the clustered index: row data resides in the leaf pages of the primary key B-tree. Each secondary index is a separate B-tree and additionally stores the primary key to locate the corresponding row. Therefore, choosing the primary key affects the size and cost of every secondary index, while creating too many indexes increases storage footprint and write costs.

In the `DATABASE_MYSQL` module, index design must start from data constraints and real queries. A unique index can both enforce uniqueness and serve queries; a non-unique secondary index can improve read speed but cannot replace a business constraint. This lesson focuses on MySQL 8.0 and later with InnoDB.

## Objectives

After this lesson, you will be able to:

- Distinguish `PRIMARY KEY`, `UNIQUE KEY`, and non-unique secondary indexes.
- Explain clustered indexes and how secondary indexes locate rows in InnoDB.
- Create single-column primary keys, composite keys, unique indexes, and regular indexes.
- Understand how `NULL`, collation, and comparison rules affect uniqueness.
- Explain why a multi-column unique index only enforces uniqueness on the full combination.
- Understand the leftmost prefix of composite indexes and choose appropriate column ordering.
- Recognize prefix indexes and the limitations of unique prefix indexes.
- Use indexes to support queries, covering access, and foreign keys.
- Inspect indexes using `SHOW INDEX`, `INFORMATION_SCHEMA`, and `EXPLAIN`.
- Weigh write costs, storage size, redundant indexes, and schema changes.

## 1. Three common types of indexes

| Type | Primary role | Uniqueness rule | Count per table |
|---|---|---|---|
| `PRIMARY KEY` | Row identifier and InnoDB clustered index | Always unique, does not accept `NULL` | At most one |
| `UNIQUE KEY` | Enforces uniqueness of a column or column combination | Unique by comparison rules; nullable columns can have multiple `NULL`s | Can have multiple |
| Regular secondary index | Supports filtering, joins, sorting, and covering access | Does not enforce uniqueness | Can have multiple |

Both `PRIMARY KEY` and `UNIQUE KEY` create an index. In MySQL, `UNIQUE KEY` and `UNIQUE INDEX` are two ways to declare a unique index; unique constraints are enforced by MySQL using unique indexes. Regular secondary indexes are created using `INDEX` or `KEY`.

Comprehensive example:

```sql
CREATE TABLE app_user (
    user_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(255) NOT NULL,
    username VARCHAR(80) NOT NULL,
    display_name VARCHAR(160) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (user_id),
    UNIQUE KEY uq_user_email (email),
    UNIQUE KEY uq_user_username (username),
    KEY idx_user_status_created (status, created_at)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4;
```

In this table:

- `user_id` is the primary key, uniquely identifying each row.
- `email` and `username` have unique indexes to prevent two accounts from using the same value according to the column's collation.
- `(status, created_at)` is a regular secondary index supporting queries by status and timestamp.
- `display_name` has no index because the example has not established a query needing to filter or sort by this column.

## 2. PRIMARY KEY in InnoDB

A primary key is a row-identifying constraint. A table can have only one primary key; that key may consist of one or multiple columns. Every column belonging to the primary key is treated as `NOT NULL`.

### 2.1. Single-column primary key

```sql
CREATE TABLE product (
    product_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    product_name VARCHAR(150) NOT NULL,
    price DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (product_id)
) ENGINE=InnoDB;
```

`product_id` is the unique key for each product. `AUTO_INCREMENT` assigns a new numeric value when an insert omits the ID. You should not assume IDs will be strictly gapless: rollbacks, row deletions, ID allocation caches, or other operational factors can create gaps.

### 2.2. Composite primary key

When row identity is determined by multiple columns, a composite primary key can be used:

```sql
CREATE TABLE order_item (
    order_id BIGINT UNSIGNED NOT NULL,
    line_no INT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id, line_no),
    KEY idx_order_item_product (product_id)
) ENGINE=InnoDB;
```

`order_id` can repeat because one order has multiple line items; `line_no` can repeat across different orders. Only the pair `(order_id, line_no)` is unique.

Column order in a composite primary key matters to the B-tree. Key `(order_id, line_no)` supports lookups by `order_id` or by both columns; it does not provide an equivalent access path for queries filtering only on `line_no`.

### 2.3. InnoDB uses the primary key as the clustered index

In InnoDB, row data is stored in the leaf pages of the clustered index, which is usually the primary key. Queries by primary key traverse the clustered B-tree to find the row. Secondary indexes store the secondary key along with the primary key values needed to locate the row.

If a table declares no primary key, InnoDB selects the first unique index where every column is `NOT NULL` as the clustered index, if one exists. If no suitable key exists, InnoDB generates a hidden internal row ID as the clustered index. Application table design should declare an explicit primary key for clear row identification and referential relationships.

### 2.4. Primary keys should be stable

Changing a primary key can change the row's position in the clustered index and require updating every secondary index carrying that key. If the primary key is referenced by other tables, migrations also affect foreign keys, child data, and applications.

Prefer keys that are unique, `NOT NULL`, stable, and reasonably narrow. `BIGINT` often fits internal IDs; natural composite keys remain sensible when components are small, stable, and accurately reflect row identity. Do not use a mutable column such as email or name as a primary key simply because it currently appears unique.

## 3. UNIQUE KEY and unique constraints

A unique index prevents two rows from having the same value across all indexed columns, according to the data type and collation comparison rules. You can declare a unique index when creating the table:

```sql
CREATE TABLE customer (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(255) NOT NULL,
    external_ref VARCHAR(60) NOT NULL,
    phone VARCHAR(30) NULL,
    status VARCHAR(20) NOT NULL,
    PRIMARY KEY (customer_id),
    CONSTRAINT uq_customer_email UNIQUE (email),
    UNIQUE KEY uq_customer_external_ref (external_ref),
    UNIQUE INDEX uq_customer_phone (phone)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4;
```

All of the forms above create a unique index. Constraint/index names help operators identify constraints in error messages and metadata. In MySQL, a unique constraint is enforced by an index; there is no separate unique constraint structure independent of an index as in some other DBMSs.

You can add a unique index after table creation via `ALTER TABLE`. For example, with an initial import table lacking constraints:

```sql
CREATE TABLE customer_email_import (
    import_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(255) NOT NULL,
    PRIMARY KEY (import_id)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4;

ALTER TABLE customer_email_import
ADD UNIQUE KEY uq_customer_email_import (email);
```

If existing data already contains duplicates according to the comparison rules, the command to create the unique index will fail. Find and resolve duplicate data before deploying the constraint.

### 3.1. UNIQUE on a single column

```sql
CREATE TABLE customer_email_registry (
    email VARCHAR(255) NOT NULL
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4;

CREATE UNIQUE INDEX uq_customer_email_registry
ON customer_email_registry (email);
```

Each non-`NULL` email value can appear at most once according to the collation. If the `email` column is `NOT NULL`, every row must have an email and emails must be unique.

### 3.2. UNIQUE on multiple columns

```sql
CREATE TABLE tenant_member (
    member_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    username VARCHAR(80) NOT NULL,
    full_name VARCHAR(160) NOT NULL,
    PRIMARY KEY (member_id),
    UNIQUE KEY uq_tenant_username (tenant_id, username)
) ENGINE=InnoDB;
```

This unique index guarantees that a `username` cannot repeat within the same `tenant_id`. The same username can appear across two different tenants:

| tenant_id | username | Valid? |
|---:|---|---|
| 10 | `alex` | Yes |
| 10 | `sam` | Yes |
| 20 | `alex` | Yes |
| 10 | `alex` | No, duplicate combination `(10, 'alex')` |

Unique `(tenant_id, username)` does not guarantee `tenant_id` is unique or `username` is unique across the entire table. It only enforces uniqueness of the full tuple.

### 3.3. UNIQUE and NULL

In MySQL, a unique index permits multiple rows to contain `NULL` in a nullable column because `NULL` is not compared as equal to `NULL` during uniqueness checks. Example:

```sql
CREATE TABLE contact_method (
    contact_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    optional_phone VARCHAR(30) NULL,
    PRIMARY KEY (contact_id),
    UNIQUE KEY uq_optional_phone (optional_phone)
) ENGINE=InnoDB;

INSERT INTO contact_method (optional_phone)
VALUES (NULL), (NULL), ('0900000001');
```

Two `NULL` rows are permitted; however, inserting another row with `'0900000001'` will violate the unique index.

With a composite unique index, if any nullable component in the combination is `NULL`, MySQL can allow multiple rows having the same values in the remaining columns and `NULL` in that component. For example, unique `(tenant_id, optional_code)` does not prevent multiple rows with the same `tenant_id` and `optional_code IS NULL`.

If business rules require a unique value to be mandatory, declare those columns `NOT NULL`. Do not use a nullable unique index as a way to guarantee every row has an identifier.

### 3.4. Unique indexes protect uniqueness under concurrent writes

You should not check for duplicates using a `SELECT` followed by an `INSERT` as if those two operations always execute sequentially:

```sql
SELECT customer_id
FROM customer
WHERE email = 'new@example.com';

-- If no row exists, the application then INSERTs.
```

Two requests can run `SELECT` concurrently, both observe no email yet, and both attempt to insert. The unique index is the final layer of protection in the database: only one row with that value is accepted; the other request receives a duplicate key error (typically error 1062). The application can test the outcome directly via `INSERT` and handle unique violation errors according to business logic.

You can use `INSERT ... ON DUPLICATE KEY UPDATE` when the business rule genuinely calls for updating the conflicting row. This statement triggers on conflicts against any primary key or unique index; if a table has multiple unique keys, you must clearly understand which row can conflict and avoid ambiguous upsert designs. Do not use upsert merely to mask duplicate errors.

### 3.5. UNIQUE depends on collation

For string columns, uniqueness comparisons obey collation. With a case-insensitive collation, two strings like `'Alice'` and `'alice'` may be treated as equivalent and cannot coexist in a unique index. An accent-insensitive collation can also treat accented and unaccented characters as equivalent.

Inspect column charset/collation and choose comparison rules according to business requirements:

```sql
SHOW FULL COLUMNS FROM customer;
```

If an identifier must distinguish bytes or case, choose an appropriate collation—such as a binary collation for string columns, or a `BINARY` type when data is genuinely raw bytes. Do not change collation just to allow visually identical duplicates; clearly define name/code normalization rules before creating a unique index.

## 4. Non-unique secondary indexes

A regular secondary index creates an additional access path to rows. It does not prevent repeated values:

```sql
CREATE INDEX idx_customer_status
ON customer (status);
```

Multiple customers can share the same `status`. The index helps MySQL quickly locate rows with the filtered status, without changing data validity rules.

Query example:

```sql
SELECT customer_id, email
FROM customer
WHERE status = 'ACTIVE';
```

If `status` has adequate selectivity and the table is large enough, the optimizer may use `idx_customer_status`. If most rows are `ACTIVE`, a table scan may be cheaper; having an index does not mean the optimizer must always use it.

### 4.1. Secondary indexes store the primary key

An InnoDB secondary index leaf entry contains the indexed columns together with the primary key components needed to locate the row in the clustered index. For example, if the primary key is `customer_id` and the secondary index is `(status)`, the entry can be thought of logically as `(status, customer_id)`.

This allows queries needing only `status` and `customer_id` to potentially be served via a covering index without reading the clustered record:

```sql
EXPLAIN
SELECT status, customer_id
FROM customer
WHERE status = 'ACTIVE';
```

If the query needs `email` and `email` is not in the secondary entry, InnoDB may have to look up the clustered index to retrieve that column:

```sql
SELECT status, customer_id, email
FROM customer
WHERE status = 'ACTIVE';
```

This is why primary key width affects the storage size of every secondary index, including non-unique ones.

### 4.2. Secondary indexes can also be composite

Create an orders table used in the following composite index examples:

```sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    external_ref VARCHAR(80) NOT NULL,
    PRIMARY KEY (order_id)
) ENGINE=InnoDB;

CREATE INDEX idx_order_status_created
ON orders (status, created_at);
```

Composite indexes support queries based on the column order of the index. `idx_order_status_created` can support filtering by `status`, or by `status` combined with a `created_at` range; it does not directly replace an index solely on `created_at` when the query lacks a suitable predicate on the leading column.

## 5. Composite indexes and leftmost prefix

Given the index:

```sql
CREATE INDEX idx_tenant_status_created
ON orders (tenant_id, status, created_at);
```

The key order is `tenant_id` first, then `status`, then `created_at`. The B-tree is sorted by this tuple. Therefore, leftmost prefixes can generally be used as an access path:

| Query condition | Can use index prefix? |
|---|---|
| `tenant_id = 10` | Yes |
| `tenant_id = 10 AND status = 'PAID'` | Yes |
| `tenant_id = 10 AND status = 'PAID' AND created_at >= ...` | Yes |
| `status = 'PAID'` | Cannot use leftmost prefix in an equivalent way |
| `created_at >= ...` | Cannot use leftmost prefix in an equivalent way |

The optimizer may choose another index, index skip scan in some cases, or a table scan; the table above illustrates the basic leftmost prefix principle, not a guarantee that every prefixed query will always use the index.

### 5.1. Column order must be based on queries

If the workload usually queries by tenant and then filters by status and date range, `(tenant_id, status, created_at)` may fit well. If the workload usually searches by status across the entire system, that index will not necessarily serve that query well.

Do not mechanically apply the rule "the highest-selectivity column always goes first." You must consider:

- Equality conditions that frequently appear together.
- Range conditions and sorting columns.
- Whether queries are scoped by tenant.
- Distinct value counts and data distribution.
- Other queries that can leverage the leftmost prefix.
- Storage and index update costs.

### 5.2. Equality and range

In index `(tenant_id, status, created_at)`, equality conditions on `tenant_id` and `status` typically allow jumping to the matching key region and then applying a range scan on `created_at`:

```sql
SELECT order_id, created_at
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
  AND created_at >= '2026-01-01 00:00:00'
  AND created_at <  '2026-02-01 00:00:00';
```

Conditions on columns after a range usually do not continue narrowing the range scan in the same way preceding equality columns do, though they may still be evaluated as an index condition or filter. Inspect `EXPLAIN` to see which parts are actually used as access conditions.

## 6. Composite UNIQUE and NULL in practice

A composite unique index is commonly used to express scoped uniqueness:

```sql
CREATE TABLE external_identity (
    identity_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    provider VARCHAR(30) NOT NULL,
    provider_user_id VARCHAR(120) NOT NULL,
    tenant_id BIGINT UNSIGNED NULL,
    PRIMARY KEY (identity_id),
    UNIQUE KEY uq_provider_user_tenant
        (provider, provider_user_id, tenant_id)
) ENGINE=InnoDB;
```

If `tenant_id` is allowed to be `NULL`, multiple rows with the same `provider`, `provider_user_id`, and `tenant_id IS NULL` can exist. If business rules require each provider user to appear only once when the tenant is unspecified, design a stricter constraint—such as separating global and tenant-scoped cases or using a column representing a normalized value with a `NOT NULL` rule.

Do not use `COALESCE(tenant_id, 0)` in queries and assume a unique index on `tenant_id` enforces the same semantics. If you must normalize `NULL` to a sentinel, ensure the sentinel is not a valid business value and represent it with an appropriate generated column/index or schema design.

## 7. Prefix indexes

A prefix index indexes only the leading characters of a string column:

```sql
CREATE TABLE external_record (
    record_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    external_code VARCHAR(200) NOT NULL,
    description VARCHAR(200) NULL,
    PRIMARY KEY (record_id)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4;

CREATE INDEX idx_external_code_prefix
ON external_record (external_code(20));
```

A prefix index can reduce index size when string columns are long and queries match prefixes. It does not contain the full column value; if a query needs a full comparison, MySQL may have to re-check the row to confirm.

### 7.1. UNIQUE prefix does not guarantee full-string uniqueness

```sql
CREATE UNIQUE INDEX uq_code_prefix
ON external_record (external_code(12));
```

This unique index requires the first 12 characters (per the string type's prefix unit) not to collide, not that the entire `external_code` is unique. Two distinct codes sharing the same 12-character prefix will be rejected.

If business rules require the entire code to be unique, use a unique index on the full column when key length limits permit. Do not arbitrarily shorten a prefix just to shrink the index.

For `TEXT`/`BLOB`, MySQL requires a prefix length when creating an index. Prefix length is measured in characters for string types and bytes for binary types; account for charset and key length limits.

## 8. Indexes and foreign keys

InnoDB requires indexes to enforce foreign key relationships. Referenced columns in the parent table must be indexed per InnoDB requirements; typically they should reference a primary key or unique key. In the child table, InnoDB requires an index with the foreign key columns in the leading positions to check and locate related rows; if no suitable index exists, MySQL may create one automatically.

Example:

```sql
CREATE TABLE department (
    department_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    department_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (department_id),
    UNIQUE KEY uq_department_name (department_name)
) ENGINE=InnoDB;

CREATE TABLE employee (
    employee_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    department_id BIGINT UNSIGNED NOT NULL,
    employee_name VARCHAR(120) NOT NULL,
    PRIMARY KEY (employee_id),
    KEY idx_employee_department (department_id),
    CONSTRAINT fk_employee_department
        FOREIGN KEY (department_id)
        REFERENCES department (department_id)
) ENGINE=InnoDB;
```

`idx_employee_department` supports joins and checks child rows when updating/deleting parent rows. Do not create an identical redundant index solely because of a foreign key; check existing indexes before adding one.

Corresponding columns on both sides of a foreign key must have compatible types. For numeric types, pay attention to size and signed/unsigned; for strings, charset/collation must also be compatible per MySQL rules.

## 9. UNIQUE and handling duplicate data

Before adding a unique index to a table with existing data, find duplicate groups:

```sql
SELECT email, COUNT(*) AS duplicate_count
FROM customer
GROUP BY email
HAVING COUNT(*) > 1;
```

For composite unique keys:

```sql
SELECT tenant_id, username, COUNT(*) AS duplicate_count
FROM tenant_member
GROUP BY tenant_id, username
HAVING COUNT(*) > 1;
```

Note: `GROUP BY` groups `NULL` together into one group, whereas a unique index permits multiple `NULL`s. Therefore, a duplicate-finding query must filter nullable components according to MySQL unique semantics if you want to accurately predict whether index creation will fail.

Example finding duplicates only where all components are non-`NULL`:

```sql
CREATE TABLE optional_identity (
    identity_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NULL,
    optional_code VARCHAR(80) NULL,
    PRIMARY KEY (identity_id),
    UNIQUE KEY uq_optional_identity (tenant_id, optional_code)
) ENGINE=InnoDB;

SELECT tenant_id, optional_code, COUNT(*) AS duplicate_count
FROM optional_identity
WHERE tenant_id IS NOT NULL
  AND optional_code IS NOT NULL
GROUP BY tenant_id, optional_code
HAVING COUNT(*) > 1;
```

If a composite unique index has multiple nullable columns, inspect groups with any `NULL` component separately; those groups are not necessarily duplicates under unique index rules.

When creating a unique index fails due to a duplicate key, do not arbitrarily delete a row. Identify the canonical record, merge referencing data, handle history, and ensure the application stops creating duplicates during migration. For tables under continuous writes, a controlled rollout plan is needed to avoid races between data cleanup and unique index creation.

## 10. Using indexes for queries and reading EXPLAIN

Indexes are designed to support access paths. Example:

```sql
EXPLAIN
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 50;
```

When reading `EXPLAIN`, watch:

- `possible_keys`: indexes the optimizer considers as candidates.
- `key`: the index actually selected; `NULL` means no index was chosen.
- `key_len`: the length of the key prefix used by the chosen access path, not the total index size.
- `rows`: estimated rows to read; for InnoDB this can be an approximation.
- `filtered`: estimated percentage of rows remaining after filter conditions.
- `Extra`: details such as `Using index`, `Using index condition`, `Using filesort`, or `Using temporary`.

### 10.1. Covering index

If an index contains every column needed by the query, MySQL can read data from the index without an additional clustered record lookup. In `EXPLAIN`, `Using index` typically indicates the query is served via a covering index.

### 10.2. Index Condition Pushdown

`Using index condition` indicates predicates are pushed down to the storage engine to be evaluated on index entries before reading the full row. It is not synonymous with a covering index. A query can use index condition pushdown and still need a clustered record lookup.

### 10.3. EXPLAIN ANALYZE

MySQL 8.0.18 and later supports `EXPLAIN ANALYZE` for read queries, executing the query and reporting actual iterator row counts and timings. Example:

```sql
EXPLAIN ANALYZE
SELECT order_id, created_at
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 50;
```

This command actually executes the statement. Only run it on read queries with bounded scope and on lab/staging data when cost is unknown. Compare estimates against actuals to detect stale statistics, unexpected selectivity, or large intermediate row counts.

## 11. Creating, inspecting, and dropping indexes

Creating indexes:

```sql
CREATE INDEX idx_orders_created_at
ON orders (created_at);

CREATE UNIQUE INDEX uq_orders_external_ref
ON orders (external_ref);
```

Or using `ALTER TABLE`:

```sql
ALTER TABLE orders
ADD INDEX idx_orders_total_amount (total_amount);
```

Inspecting indexes:

```sql
SHOW INDEX FROM orders;
SHOW CREATE TABLE orders\G
```

You can read structured index metadata from `INFORMATION_SCHEMA.STATISTICS`:

```sql
SELECT
    INDEX_NAME,
    NON_UNIQUE,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    SUB_PART,
    COLLATION
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
```

`NON_UNIQUE = 0` indicates a unique index; `SEQ_IN_INDEX` gives column position; `SUB_PART` shows prefix length if the index covers only part of a column. This metadata describes the declared index and does not necessarily expose every physical detail of the primary key bytes InnoDB implicitly carries in secondary entries.

Dropping a secondary or unique index:

```sql
ALTER TABLE orders DROP INDEX idx_orders_created_at;
```

Dropping a primary key uses dedicated syntax:

```sql
ALTER TABLE orders DROP PRIMARY KEY;
```

Do not run a drop primary key command without a replacement plan. InnoDB still requires a clustered index; when a PK is dropped, it must pick another unique `NOT NULL` index or generate a hidden row ID. Changing the primary key can be expensive and affects all secondary indexes.

### 11.1. Index changes on large tables

Creating or dropping indexes may require reading and rebuilding index structures, consuming I/O, CPU, temporary disk space, and metadata locks. Many operations support online DDL or different `ALGORITHM`/`LOCK` modes depending on change type, engine, and version. Do not assume every `ALTER TABLE` is non-blocking or instantaneous.

Before changing production:

1. Check free disk space and build duration on a representative data copy.
2. Verify which algorithm/lock options your version supports.
3. Monitor replication lag and I/O load during the build.
4. Prepare monitoring and a rollback/recovery plan.
5. Verify queries after the change using `EXPLAIN` and real metrics.

## 12. Costs and redundant indexes

Every additional index consumes storage space and must be maintained on inserts, deletes, or updates to indexed columns. Having many indexes can increase write latency, redo/undo volume, I/O, backup duration, and migration costs.

Do not index every column. Consider:

- Which queries actually need the index?
- Is the index selective enough to reduce rows read?
- Does an existing composite index already serve the leftmost prefix?
- Is any index duplicated or covered by another index?
- Is the index used in the real workload?
- Is the additional write cost acceptable?

For example, if index `(tenant_id, status, created_at)` already exists, a separate `(tenant_id)` index may be redundant for many workloads because it is a leftmost prefix. However, do not drop it based solely on inference: a narrower index can be cheaper for a very frequent query, or the index may serve a foreign key or other requirement. Measure the workload and check constraints before removing it.

## 13. Common mistakes

| Mistake | Consequence | How to fix |
|---|---|---|
| Using nullable `UNIQUE` while expecting only one `NULL` | Multiple `NULL` rows are still accepted | Make it `NOT NULL` or explicitly model missing state |
| Thinking `UNIQUE (a, b)` makes `a` or `b` individually unique | Only the combination of both columns is enforced | Create separate unique indexes if business rules require it |
| Thinking index `(a, b)` serves queries filtering only on `b` like index `(b)` | Violates leftmost prefix | Design indexes around real query patterns |
| Creating a `UNIQUE` prefix for long codes | Only the prefix is forced unique; two distinct full values may be rejected | Use a full-column unique index if full-string uniqueness is required |
| Ignoring collation | Two differently cased/accented strings may be considered equal | Choose charset/collation matching identifier rules |
| Creating a unique index without checking existing data | DDL fails with duplicate key | Find, clean duplicates, and deploy in a controlled manner |
| Creating redundant indexes | Wastes space and slows DML | Evaluate index prefixes, workload, and constraints before dropping |
| Assuming the optimizer always uses an index | A table scan can be cheaper on small tables or low-selectivity predicates | Read `EXPLAIN`, measure on realistic data |
| Confusing `Using index condition` with covering index | Misjudging whether clustered row lookups occur | Distinguish ICP from `Using index` |
| Changing primary key without accounting for secondary indexes | Expensive DDL, impacts foreign keys and applications | Plan a full migration across all relationships |

## 14. Process for designing PRIMARY, UNIQUE, and secondary indexes

When designing a table, follow this sequence:

1. Define the identity of a row; choose a unique, `NOT NULL`, stable primary key.
2. List business rules prohibiting duplicate values; translate them into unique constraints/indexes.
3. Decide which columns must be `NOT NULL`; never let nullable unique indexes substitute for mandatory value rules.
4. Determine collation and string normalization rules for identifiers.
5. List common filtering, join, sorting, and range queries.
6. Design secondary/composite indexes following column order and leftmost prefix.
7. Account for the primary key being carried inside secondary indexes.
8. Verify indexes serving foreign keys and avoid creating duplicates.
9. Review DML cost, storage size, and DDL deployment time.
10. Validate with `SHOW INDEX`, `EXPLAIN`, and representative workloads; keep only indexes with a clear justification.

## 15. Practice exercises

Perform in an isolated InnoDB lab database:

1. Create table `app_user` with a `BIGINT AUTO_INCREMENT` primary key, unique email, unique username, and a secondary index on status/time.
2. Attempt to insert two rows with the same email; observe the duplicate key error.
3. Create a unique index on a nullable column; insert multiple `NULL`s and one duplicate non-null value to observe the behavior.
4. Create a composite unique key `(tenant_id, username)`; confirm the same username across two tenants succeeds while duplicates within one tenant are rejected.
5. Create a composite unique key with a nullable column; test combinations with `NULL` to confirm they are not treated as equal.
6. Change a test column's collation to case-insensitive; test `'Alice'` and `'alice'` with a unique index.
7. Create index `(tenant_id, status, created_at)`; test queries with and without the leftmost prefix.
8. Compare `EXPLAIN` for a query selecting only columns inside the secondary index versus a query needing an additional column outside the index.
9. Create a prefix index and a unique prefix index in the lab; test two distinct full strings sharing the same prefix.
10. Create parent-child tables with a foreign key; inspect the child's indexes and check whether an existing index satisfies the foreign key prefix.
11. Use `SHOW INDEX` and `INFORMATION_SCHEMA.STATISTICS` to list the table's indexes.
12. Create two indexes with overlapping prefixes; measure the workload and explain why an index cannot be dropped solely based on its name or structure.
13. Run `EXPLAIN ANALYZE` on a read query in the lab and compare estimated rows with actual rows.
14. Write an index proposal for an orders table: specify primary key, unique rules, secondary indexes, supported queries, and expected write cost.

You have completed this lesson when you can express data constraints using `PRIMARY`/`UNIQUE`, choose secondary indexes based on queries, predict behavior with `NULL`/collation, and explain the cost of each index in InnoDB.

## 16. Key principles to remember

- A table can have only one `PRIMARY KEY`; this key is always unique and rejects `NULL`.
- InnoDB typically uses the primary key as the clustered index; leaf pages contain the row data.
- `UNIQUE` creates a unique index; a table can have multiple unique indexes.
- A nullable unique index permits multiple `NULL`s; use `NOT NULL` if every row must have a value.
- A composite unique index enforces uniqueness on the full combination, not on individual columns.
- Collation determines how strings are compared in a unique index.
- Secondary indexes typically do not enforce uniqueness and store the primary key components needed to locate the row.
- Composite indexes follow leftmost prefix; column order must match queries.
- Prefix indexes store only part of a string; a unique prefix only guarantees prefix uniqueness.
- Indexes can support covering access, but `Using index condition` does not mean covering index.
- InnoDB needs suitable indexes to enforce foreign keys; avoid creating redundant indexes.
- Every index increases storage size and `INSERT`/`UPDATE`/`DELETE` cost; do not index every column.
- Existing duplicate data can cause unique index creation to fail.
- `EXPLAIN` shows the estimated access path; `EXPLAIN ANALYZE` executes the query and measures actuals.
- Evaluate indexes based on constraints, workload, and measurements—not merely index count.
