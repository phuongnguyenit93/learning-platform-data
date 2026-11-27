# INFORMATION_SCHEMA and Structured Metadata Lookup

## Lesson Objectives

After this lesson, you will be able to:

- Explain what `INFORMATION_SCHEMA` is and how it differs from a business database.
- Query lists of schemas, tables, views, columns, indexes, and constraints using SQL.
- Trace foreign key relationships and inspect structures within a schema.
- Leverage metadata for views, routines, triggers, events, and partitions when needed.
- Use metadata to build inventories, verify design conventions, and support migrations.
- Recognize limitations regarding visibility privileges, freshness, and accuracy of metadata.

In MySQL, if you want to know which tables a database has, which columns exist, what data types they have, what indexes are defined, or where foreign keys point, you do not need to open each table in an administration GUI. MySQL provides `INFORMATION_SCHEMA` to query metadata using SQL. As a result, schema inventory, technical documentation generation, design quality checks, and environment comparisons can all be automated.

## 1. What Is INFORMATION_SCHEMA?

**INFORMATION_SCHEMA** is a system database providing read-only views that describe MySQL metadata. Metadata is data describing the structure and properties of objects, such as:

- Schemas/databases and tables or views.
- Columns, data types, default values, charsets, and collations.
- Indexes, primary keys, unique keys, foreign keys, and check constraints.
- Views, stored procedures, functions, triggers, and events.
- Partitions and certain storage-engine-related information.
- Access privileges at the user, schema, table, and column scopes.

You can query `INFORMATION_SCHEMA` like a regular schema:

```sql
SELECT SCHEMA_NAME
FROM INFORMATION_SCHEMA.SCHEMATA
ORDER BY SCHEMA_NAME;
```

`INFORMATION_SCHEMA` is not a place to store business data and not a place to `INSERT`, `UPDATE`, or `DELETE` metadata. Its views present information that MySQL manages in the data dictionary and system components. In MySQL 8.0, the data dictionary is managed under a transactional data dictionary architecture; applications should use `INFORMATION_SCHEMA` and `SHOW` statements to read metadata rather than reading internal server tables or data files directly.

### 1.1. Distinguishing the three common system schemas

| Schema | Purpose | When to use? |
|---|---|---|
| `INFORMATION_SCHEMA` | Metadata about database structure and certain system states | When you need to know tables, columns, indexes, constraints, routines, or privileges |
| `performance_schema` | Instrumentation and runtime metrics on server activity | When investigating statements, waits, mutexes, I/O, and concurrency activity |
| `sys` | Helper views and routines for reading diagnostic data, mostly built atop Performance Schema and other metadata | When you need human-readable reports on workloads, statements, indexes, or resources |

The three schemas are related but do not replace one another. `INFORMATION_SCHEMA` answers "how is the structure declared?" Performance Schema helps answer "how is the server operating?" `sys` provides convenient aggregated perspectives for many operational scenarios.

## 2. How Metadata Is Organized and Queried

`INFORMATION_SCHEMA` contains many views. Each view describes a group of objects. Examples:

| View | Main contents |
|---|---|
| `SCHEMATA` | List of databases/schemas and default attributes |
| `TABLES` | Tables, views, storage engine, size, and certain statistics |
| `COLUMNS` | Columns, data types, ordinal position, nullability, default, and collation |
| `STATISTICS` | Indexes and individual key parts of each index |
| `TABLE_CONSTRAINTS` | Primary key, unique, foreign key, and check constraints |
| `KEY_COLUMN_USAGE` | Columns participating in constraints and referenced relationships |
| `REFERENTIAL_CONSTRAINTS` | `ON UPDATE` and `ON DELETE` rules for foreign keys |
| `CHECK_CONSTRAINTS` | Expressions and enforcement status of check constraints |
| `VIEWS` | View definitions and properties |
| `ROUTINES` | Stored procedures and functions |
| `TRIGGERS` | Triggers attached to tables |
| `EVENTS` | Event Scheduler objects |
| `PARTITIONS` | Partition and subpartition information |
| `SCHEMA_PRIVILEGES`, `TABLE_PRIVILEGES`, `COLUMN_PRIVILEGES` | Privileges granted at their respective scopes |

View names and column sets can change across MySQL versions. When writing tools for multiple versions, identify the target version and check the view structure on that version. Do not assume every column exists across all MySQL releases.

### 2.1. Basic lookup syntax

A query typically follows this form:

```sql
SELECT column_a, column_b
FROM INFORMATION_SCHEMA.some_view
WHERE condition
ORDER BY column_a;
```

Schema and table names in metadata are usually compared as strings. Filter early on `TABLE_SCHEMA` or `SCHEMA_NAME` to narrow the scope. Avoid querying metadata across the entire server when you only need a single database.

For example, listing business schemas while excluding system schemas:

```sql
SELECT SCHEMA_NAME
FROM INFORMATION_SCHEMA.SCHEMATA
WHERE SCHEMA_NAME NOT IN (
    'information_schema',
    'mysql',
    'performance_schema',
    'sys'
)
ORDER BY SCHEMA_NAME;
```

Do not rely on an implicit ordering of results. If a deterministic report is needed, always specify `ORDER BY`.

## 3. Inventorying Schemas and Tables

### 3.1. List of databases

The `SCHEMATA` view provides schema names and default properties such as character set, collation, and SQL path.

```sql
SELECT
    SCHEMA_NAME,
    DEFAULT_CHARACTER_SET_NAME,
    DEFAULT_COLLATION_NAME
FROM INFORMATION_SCHEMA.SCHEMATA
WHERE SCHEMA_NAME = 'shop';
```

Charset/collation information at the schema level is the default for subsequently created objects. A table or column can declare its own charset/collation, so you cannot conclude from this result alone that every column in the schema shares the same collation.

### 3.2. List of tables and views

The `TABLES` view describes both base tables and views:

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    TABLE_TYPE,
    ENGINE,
    TABLE_COLLATION,
    CREATE_TIME,
    UPDATE_TIME
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'shop'
ORDER BY TABLE_TYPE, TABLE_NAME;
```

`TABLE_TYPE` typically indicates whether an object is a `BASE TABLE` or a `VIEW`. `ENGINE` shows the table's storage engine; for views, this value is usually `NULL`.

Several columns in `TABLES` require careful interpretation:

- `TABLE_ROWS` for InnoDB is an estimate, not an exact row count.
- `DATA_LENGTH` and `INDEX_LENGTH` represent data and index sizes as reported by the storage engine; they do not always match the file sizes you see on the filesystem.
- `DATA_FREE` reflects free space as reported by the engine, not bytes that can immediately be reclaimed by a simple operation.
- `UPDATE_TIME` can be `NULL` or fail to reflect the exact most recent update timestamp, especially for InnoDB.
- `CREATE_TIME` and other statistics depend on the engine and version.

If you need an exact row count for a table, query `COUNT(*)` on that table itself. On large tables, counting can consume significant I/O and time; evaluate system load before running it.

### 3.3. Storage capacity report by schema

You can aggregate sizes reported by metadata:

```sql
SELECT
    TABLE_SCHEMA,
    COUNT(*) AS table_count,
    ROUND(SUM(DATA_LENGTH) / 1024 / 1024, 2) AS data_mb,
    ROUND(SUM(INDEX_LENGTH) / 1024 / 1024, 2) AS index_mb,
    ROUND(SUM(DATA_LENGTH + INDEX_LENGTH) / 1024 / 1024, 2) AS total_mb,
    SUM(TABLE_ROWS) AS estimated_rows
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_TYPE = 'BASE TABLE'
  AND TABLE_SCHEMA = 'shop'
GROUP BY TABLE_SCHEMA;
```

These are estimated/engine-reported metrics for inventory and trend comparison. Do not sum `TABLE_ROWS` and treat it as an exact InnoDB row total. If you need a server-wide capacity report, you can omit the schema filter while still excluding system schemas and understanding how engines report sizes.

## 4. Inspecting Columns and Data Types

The `COLUMNS` view is one of the most frequently used views. It shows which table each column belongs to, its ordinal position, data type, nullability, default, and charset/collation attributes.

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ORDINAL_POSITION,
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    EXTRA,
    CHARACTER_SET_NAME,
    COLLATION_NAME
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'shop'
  AND TABLE_NAME = 'orders'
ORDER BY ORDINAL_POSITION;
```

Important columns:

- `COLUMN_NAME`: the column name.
- `ORDINAL_POSITION`: the position of the column in the table definition, starting at 1.
- `DATA_TYPE`: the base data type, such as `int`, `varchar`, `decimal`.
- `COLUMN_TYPE`: a more detailed representation, which may include length, precision, `unsigned`, or `enum`/`set` values.
- `IS_NULLABLE`: indicates whether the column allows `NULL`.
- `COLUMN_DEFAULT`: the default value reported by metadata.
- `EXTRA`: additional attributes such as `auto_increment`, generated column, or other version-dependent properties.
- `CHARACTER_SET_NAME` and `COLLATION_NAME`: column-level string attributes.

Note: `COLUMN_DEFAULT` can be `NULL` either when the column has a default of `NULL` or when the definition has no `DEFAULT` clause. If you need to distinguish exact syntactic details, cross-check `SHOW CREATE TABLE`.

Example finding string columns whose collation differs from the schema's default collation:

```sql
SELECT
    c.TABLE_NAME,
    c.COLUMN_NAME,
    c.COLUMN_TYPE,
    c.CHARACTER_SET_NAME,
    c.COLLATION_NAME
FROM INFORMATION_SCHEMA.COLUMNS AS c
JOIN INFORMATION_SCHEMA.SCHEMATA AS s
  ON s.SCHEMA_NAME = c.TABLE_SCHEMA
WHERE c.TABLE_SCHEMA = 'shop'
  AND c.COLLATION_NAME IS NOT NULL
  AND c.COLLATION_NAME <> s.DEFAULT_COLLATION_NAME
ORDER BY c.TABLE_NAME, c.ORDINAL_POSITION;
```

This query helps locate differences worth reviewing. A differing collation is not necessarily an error; it may be an intentional business decision. Check the rationale before standardizing.

### 4.1. Finding columns with data types to review

Example finding columns using `TEXT` or `BLOB` types in a schema:

```sql
SELECT
    TABLE_NAME,
    COLUMN_NAME,
    DATA_TYPE,
    COLUMN_TYPE,
    IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'shop'
  AND DATA_TYPE IN ('text', 'mediumtext', 'longtext',
                    'blob', 'mediumblob', 'longblob')
ORDER BY TABLE_NAME, ORDINAL_POSITION;
```

Metadata helps build a list for review. Data type decisions must be based on data size, query patterns, indexes, charset, and business requirements; do not automatically change a type simply because an inventory query flags it.

## 5. Inspecting Indexes

The `STATISTICS` view provides index metadata. Each key part is usually one row, so a multi-column index appears across multiple rows ordered by `SEQ_IN_INDEX`. The query below uses `IS_VISIBLE`, suitable for MySQL versions that support invisible indexes; if a tool must run on an older version, remove this column from the `SELECT` list.

```sql
SELECT
    TABLE_NAME,
    INDEX_NAME,
    NON_UNIQUE,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    COLLATION,
    CARDINALITY,
    SUB_PART,
    INDEX_TYPE,
    IS_VISIBLE
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA = 'shop'
ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX;
```

Meaning of key columns:

- `INDEX_NAME`: index name; `PRIMARY` is the primary key.
- `NON_UNIQUE = 0`: unique index; `1`: non-unique index.
- `SEQ_IN_INDEX`: position of the key part within a composite index.
- `COLUMN_NAME`: indexed column; may be `NULL` for certain functional key parts.
- `SUB_PART`: prefix length if only a prefix of the column is indexed.
- `CARDINALITY`: estimated number of distinct values in the index; not a fixed exact figure.
- `INDEX_TYPE`: index type, commonly `BTREE`.
- `IS_VISIBLE`: visible/invisible status of the index on supported versions.

For example, if index `idx_customer_created` has `customer_id` at position 1 and `created_at` at position 2, it is a composite index ordered across those two columns. Key-part order affects whether the index can be used for filter predicates and sorting; seeing both columns inside an index is not enough to conclude the index fits a query.

### 5.1. Finding tables without a primary key

A primary key identifies rows and serves as the foundation for InnoDB's clustered index. You can list base tables without a declared primary key:

```sql
SELECT
    t.TABLE_SCHEMA,
    t.TABLE_NAME,
    t.ENGINE
FROM INFORMATION_SCHEMA.TABLES AS t
LEFT JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS AS tc
  ON tc.TABLE_SCHEMA = t.TABLE_SCHEMA
 AND tc.TABLE_NAME = t.TABLE_NAME
 AND tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
WHERE t.TABLE_SCHEMA = 'shop'
  AND t.TABLE_TYPE = 'BASE TABLE'
  AND tc.CONSTRAINT_NAME IS NULL
ORDER BY t.TABLE_NAME;
```

The result is a list for review. A table without a primary key may be an intentional design, but with InnoDB, consider row identification, secondary indexes, replication, and accurate updates/deletes. Do not automatically add a primary key before determining an appropriate natural key or surrogate key.

### 5.2. Inspecting indexes by table

To inspect a specific table, you can use both `INFORMATION_SCHEMA` and `SHOW` commands:

```sql
SELECT
    INDEX_NAME,
    NON_UNIQUE,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    CARDINALITY,
    INDEX_TYPE,
    IS_VISIBLE
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA = 'shop'
  AND TABLE_NAME = 'orders'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;

SHOW INDEX FROM shop.orders;
```

Metadata results describe index structure, but they do not prove the optimizer will use an index for a particular query. To evaluate the execution plan, run `EXPLAIN` on the actual query and cross-check with data, statistics, and workload.

## 6. Inspecting Constraints and Foreign Key Relationships

Constraint metadata often requires combining multiple views:

- `TABLE_CONSTRAINTS` shows the constraint type.
- `KEY_COLUMN_USAGE` shows columns participating in constraints and referenced column details.
- `REFERENTIAL_CONSTRAINTS` provides referential actions such as `ON UPDATE` and `ON DELETE`.
- `CHECK_CONSTRAINTS` provides check constraint expressions on supported versions.

List constraints in a schema:

```sql
SELECT
    TABLE_NAME,
    CONSTRAINT_NAME,
    CONSTRAINT_TYPE
FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
WHERE TABLE_SCHEMA = 'shop'
ORDER BY TABLE_NAME, CONSTRAINT_TYPE, CONSTRAINT_NAME;
```

### 6.1. Viewing foreign key relationships

```sql
SELECT
    kcu.TABLE_NAME,
    kcu.CONSTRAINT_NAME,
    kcu.COLUMN_NAME,
    kcu.ORDINAL_POSITION,
    kcu.REFERENCED_TABLE_SCHEMA,
    kcu.REFERENCED_TABLE_NAME,
    kcu.REFERENCED_COLUMN_NAME,
    rc.UPDATE_RULE,
    rc.DELETE_RULE
FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE AS kcu
LEFT JOIN INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS AS rc
  ON rc.CONSTRAINT_SCHEMA = kcu.CONSTRAINT_SCHEMA
 AND rc.TABLE_NAME = kcu.TABLE_NAME
 AND rc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
WHERE kcu.TABLE_SCHEMA = 'shop'
  AND kcu.REFERENCED_TABLE_NAME IS NOT NULL
ORDER BY kcu.TABLE_NAME, kcu.CONSTRAINT_NAME, kcu.ORDINAL_POSITION;
```

With composite foreign keys, each column is one row. `ORDINAL_POSITION` pairs source and target columns in the exact order. `UPDATE_RULE` and `DELETE_RULE` indicate referential behavior, such as `CASCADE`, `RESTRICT`, `NO ACTION`, or `SET NULL`, depending on the constraint.

### 6.2. Inspecting check constraints

On MySQL 8.0.16 and later, check constraints are enforced and can be queried in `INFORMATION_SCHEMA`:

```sql
SELECT
    tc.TABLE_NAME,
    tc.CONSTRAINT_NAME,
    tc.CONSTRAINT_TYPE,
    cc.CHECK_CLAUSE,
    cc.ENFORCED
FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS AS tc
JOIN INFORMATION_SCHEMA.CHECK_CONSTRAINTS AS cc
  ON cc.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA
 AND cc.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
WHERE tc.TABLE_SCHEMA = 'shop'
  AND tc.CONSTRAINT_TYPE = 'CHECK'
ORDER BY tc.TABLE_NAME, tc.CONSTRAINT_NAME;
```

If you must support older MySQL versions, check `CHECK` support before running this query. In older versions, `CHECK` syntax could be accepted without actually being enforced as expected.

## 7. Inspecting Views, Routines, Triggers, and Events

A schema contains more than tables. A system may include views, stored procedures, functions, triggers, and events. The corresponding metadata views help inventory these objects.

### 7.1. Views

```sql
SELECT
    TABLE_NAME AS VIEW_NAME,
    DEFINER,
    SECURITY_TYPE,
    CHECK_OPTION,
    IS_UPDATABLE,
    VIEW_DEFINITION
FROM INFORMATION_SCHEMA.VIEWS
WHERE TABLE_SCHEMA = 'shop'
ORDER BY TABLE_NAME;
```

`VIEW_DEFINITION` describes the `SELECT` query defining the view. The definition text may not be displayed in full if the account lacks appropriate privileges. Use `SHOW CREATE VIEW shop.view_name` to view the definition of a specific view when permitted.

### 7.2. Stored procedures and functions

```sql
SELECT
    ROUTINE_NAME,
    ROUTINE_TYPE,
    DEFINER,
    SECURITY_TYPE,
    SQL_DATA_ACCESS,
    IS_DETERMINISTIC,
    CREATED,
    LAST_ALTERED
FROM INFORMATION_SCHEMA.ROUTINES
WHERE ROUTINE_SCHEMA = 'shop'
ORDER BY ROUTINE_TYPE, ROUTINE_NAME;
```

You can additionally query `ROUTINE_DEFINITION` when you need to read the routine body and the account holds the required privileges. Avoid placing routine definitions containing sensitive logic into widely shared reports.

### 7.3. Triggers and events

```sql
SELECT
    TRIGGER_NAME,
    EVENT_MANIPULATION,
    EVENT_OBJECT_TABLE,
    ACTION_TIMING,
    ACTION_ORIENTATION,
    DEFINER
FROM INFORMATION_SCHEMA.TRIGGERS
WHERE TRIGGER_SCHEMA = 'shop'
ORDER BY EVENT_OBJECT_TABLE, TRIGGER_NAME;
```

```sql
SELECT
    EVENT_NAME,
    DEFINER,
    STATUS,
    EVENT_TYPE,
    EXECUTE_AT,
    INTERVAL_VALUE,
    INTERVAL_FIELD,
    LAST_EXECUTED
FROM INFORMATION_SCHEMA.EVENTS
WHERE EVENT_SCHEMA = 'shop'
ORDER BY EVENT_NAME;
```

Event metadata shows the schedule and declared status. For an event to run, the server's Event Scheduler must also be enabled. An event with status `ENABLED` in metadata does not guarantee that the scheduler is currently active.

## 8. Inspecting Partitions

For partitioned tables, the `PARTITIONS` view provides partition names, partitioning methods, partitioning expressions, and certain statistics:

```sql
SELECT
    TABLE_NAME,
    PARTITION_NAME,
    SUBPARTITION_NAME,
    PARTITION_METHOD,
    PARTITION_EXPRESSION,
    TABLE_ROWS,
    DATA_LENGTH,
    INDEX_LENGTH
FROM INFORMATION_SCHEMA.PARTITIONS
WHERE TABLE_SCHEMA = 'shop'
  AND PARTITION_NAME IS NOT NULL
ORDER BY TABLE_NAME, PARTITION_ORDINAL_POSITION;
```

Row and size statistics per partition may be estimates, especially with InnoDB. Metadata helps confirm whether a table is partitioned as intended; to evaluate partition pruning, inspect the query's execution plan using `EXPLAIN`.

## 9. Inspecting Privileges Across Scopes

`INFORMATION_SCHEMA` provides views for granted privileges, for example:

- `USER_PRIVILEGES`: global-scope privileges.
- `SCHEMA_PRIVILEGES`: schema-scope privileges.
- `TABLE_PRIVILEGES`: table-scope privileges.
- `COLUMN_PRIVILEGES`: column-scope privileges.

Example checking table privileges in a schema:

```sql
SELECT
    GRANTEE,
    TABLE_SCHEMA,
    TABLE_NAME,
    PRIVILEGE_TYPE,
    IS_GRANTABLE
FROM INFORMATION_SCHEMA.TABLE_PRIVILEGES
WHERE TABLE_SCHEMA = 'shop'
ORDER BY GRANTEE, TABLE_NAME, PRIVILEGE_TYPE;
```

You can combine `SCHEMA_PRIVILEGES` and `COLUMN_PRIVILEGES` to audit other scopes. When verifying the effective privileges of a specific account, `SHOW GRANTS FOR CURRENT_USER()` or `SHOW GRANTS FOR 'user'@'host'` is usually an easier starting point. Keep roles, inherited privileges, and authentication context in mind when interpreting effective privileges.

## 10. Using INFORMATION_SCHEMA in Practice

### 10.1. Generating a schema catalog

A documentation tool can run queries in sequence:

1. Fetch the schema list from `SCHEMATA`.
2. Fetch tables and views from `TABLES`.
3. Fetch columns from `COLUMNS`.
4. Fetch indexes from `STATISTICS`.
5. Fetch constraints and relationships from `TABLE_CONSTRAINTS`, `KEY_COLUMN_USAGE`, and `REFERENTIAL_CONSTRAINTS`.
6. Fetch view/routine/trigger definitions if permitted and truly needed.
7. Export to Markdown, HTML, or an internal data catalog.

When generating documentation, record the MySQL version, collection timestamp, and executing account. This helps readers understand which environment the documentation reflects and whether objects invisible to that account might be missing.

### 10.2. Detecting schema drift across environments

Schema drift occurs when structures across dev, test, staging, and production no longer match the intended version. Metadata queries can collect:

- Table and view names.
- Columns, types, nullability, and defaults.
- Indexes, key-part order, and visibility status.
- Constraints, foreign key relationships, and rules.
- Engine, charset, and collation.

Then normalize the results and compare across environments. Do not compare by pulling every column of `INFORMATION_SCHEMA.TABLES` verbatim, as many fields are dynamic statistics or engine-dependent. Select meaningful schema-definition properties while ignoring runtime values such as row estimates and update timestamps.

When drift is detected, treat versioned migrations or the desired schema in the repository as the source of truth. Create a reviewed migration to fix differences; avoid manual edits in production that leave other environments out of sync.

### 10.3. Pre- and post-migration checks

Before a migration, capture metadata for the affected objects. After the migration, re-run the corresponding queries and compare:

- Do new columns appear with the expected types and order?
- Do indexes have all key parts in the right order?
- Do foreign keys point to the right tables/columns?
- Are constraints created and enforced?
- Do tables still use the intended storage engine, charset, and collation?

For large DDL changes, metadata only confirms structure. You still need to verify actual data, query results, execution times, and application health.

## 11. Metadata Visibility and Limitations

### 11.1. Metadata visibility depends on privileges

MySQL does not necessarily display every server object to every account. Users generally see metadata only for objects they have privileges to access. Therefore:

- A table missing from query results does not necessarily mean the table does not exist.
- Two different accounts can receive different inventory results.
- An account used to build a data catalog needs read metadata privileges appropriate for the target scope.
- Do not grant server-wide administrative privileges just so a reporting tool can read metadata.

When results seem incomplete, check the connected account and its privileges:

```sql
SELECT USER(), CURRENT_USER();
SHOW GRANTS FOR CURRENT_USER();
```

### 11.2. Metadata and statistics are not the same thing

Some values in `INFORMATION_SCHEMA` describe relatively stable definitions; others are statistics provided by the storage engine. For instance, InnoDB's `TABLE_ROWS` and `STATISTICS.CARDINALITY` are estimates. They are useful for inventorying and guiding investigation, but should not be treated as exact figures for business reconciliation.

In MySQL 8.0, the `information_schema_stats_expiry` variable controls how long table statistics are cached in `INFORMATION_SCHEMA`. Check the current value:

```sql
SHOW VARIABLES LIKE 'information_schema_stats_expiry';
```

If you genuinely need fresh statistics from the storage engine for the current session, you can set:

```sql
SET SESSION information_schema_stats_expiry = 0;
```

Setting it to `0` disables caching benefits and can make metadata queries do extra work. Fresh statistics can still be estimates; this setting does not turn `TABLE_ROWS` into an exact count. Use it only with good reason and consider the impact on the server.

### 11.3. Avoid overly broad metadata queries

An `INFORMATION_SCHEMA` query on a server with tens of thousands of tables can generate substantial load, especially when retrieving engine statistics or object definitions. Good practices:

- Filter by schema and table as early as possible.
- Select only needed columns; avoid `SELECT *`.
- Avoid running frequent inventories on short intervals when the schema rarely changes.
- Paginate or split by schema/table when tools must process large volumes of metadata.
- Schedule heavy reports at appropriate times and monitor execution duration.
- Do not assume metadata queries are completely free just because they do not read business tables directly.

If DDL is running concurrently, results from multiple queries collected at different moments may no longer describe the same schema snapshot. Record the timestamp and migration version, or re-run checks after structural changes complete.

## 12. INFORMATION_SCHEMA and SHOW Statements

`INFORMATION_SCHEMA` excels at conditional queries, JOINs, aggregations, and automation. `SHOW` statements are often faster for manually inspecting a single object.

| Need | INFORMATION_SCHEMA | Corresponding SHOW statement |
|---|---|---|
| List tables | `INFORMATION_SCHEMA.TABLES` | `SHOW TABLES FROM shop` |
| View table definition | `COLUMNS`, `STATISTICS`, constraint views | `SHOW CREATE TABLE shop.orders` |
| View indexes | `STATISTICS` | `SHOW INDEX FROM shop.orders` |
| View views | `VIEWS` | `SHOW CREATE VIEW shop.some_view` |
| View privileges | `PRIVILEGES` views | `SHOW GRANTS` |
| View engine | `TABLES.ENGINE` | `SHOW TABLE STATUS FROM shop` |

To inspect the complete definition of a single table, `SHOW CREATE TABLE` is usually the clearest and most direct source. `INFORMATION_SCHEMA` shines when searching across many objects, joining metadata, or generating structured reports.

## 13. Hands-On Exercises

Assume a `shop` schema containing tables `customers`, `orders`, `order_items`, and `products`.

### Exercise 1: Build a schema inventory

Write a query to retrieve all tables and views in `shop`, along with object type and storage engine. Explain why a view does not have a storage engine like a base table.

### Exercise 2: Generate a column report

List the columns of `orders` in order, including data type, nullability, default, extra attributes, and collation. Identify which columns are generated or auto-increment, if any.

### Exercise 3: Inspect indexes

List the indexes of `orders` ordered by key part. Identify the primary key, unique indexes, and composite indexes. Explain why column order in a composite index matters.

### Exercise 4: Map foreign key relationships

Use `KEY_COLUMN_USAGE` to list the foreign keys of `order_items`. Map the relationship from source table to target table and identify `ON DELETE`/`ON UPDATE` rules.

### Exercise 5: Find tables without a primary key

Run the query from section 5.1 on a test schema. Review each discovered table and decide whether a primary key is needed.

### Exercise 6: Check schema drift

Run corresponding metadata queries on dev and test. Compare columns, indexes, and constraints of the same table. Produce a report highlighting differences and propose a migration to resolve them.

### Exercise 7: Check visibility privileges

Create an account with privileges on only a subset of tables. Compare `INFORMATION_SCHEMA.TABLES` query results when logged in as that account versus an administrative account. Explain why metadata listings can differ.

## 14. Self-Check

1. How does `INFORMATION_SCHEMA` differ from a business database?
2. Which views are used to look up columns, indexes, and foreign keys?
3. Why cannot InnoDB's `TABLE_ROWS` be used as an exact row count?
4. A composite index appears across multiple rows in `STATISTICS`. Which column indicates key-part order?
5. Why does a table missing from `INFORMATION_SCHEMA` not necessarily mean it does not exist?
6. When should you use `SHOW CREATE TABLE` instead of only reading `COLUMNS` and `STATISTICS`?
7. Why should you record the MySQL version and collection timestamp when exporting a data catalog?

**Suggested answers:** (1) `INFORMATION_SCHEMA` provides read-only metadata about objects and system properties. (2) `COLUMNS`, `STATISTICS`, `KEY_COLUMN_USAGE` combined with `TABLE_CONSTRAINTS`/`REFERENTIAL_CONSTRAINTS`. (3) It is a storage-engine estimate. (4) `SEQ_IN_INDEX`. (5) Metadata visibility depends on account privileges. (6) When you need a complete, readable table definition preserving syntactic details. (7) To know which version and point in time the report reflects, especially when schemas can change.
