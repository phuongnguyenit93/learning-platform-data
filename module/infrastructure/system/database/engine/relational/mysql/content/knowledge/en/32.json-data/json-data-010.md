# Multi-Valued Indexes and Limitations with JSON Arrays

This lesson belongs to the **JSON** chapter of the **DATABASE_MYSQL** module. The module aims at mastering MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query tuning, authorization, backups, and handling relational database operational issues. JSON enables storing flexible attributes, where arrays often represent sets of values such as region codes, tags, skills, or permissions on an entity. However, standard B-tree indexes are designed around a one-row-to-one-index-value relationship per key part. InnoDB's multi-valued index (MVI) solves the problem of finding rows by individual JSON array elements by creating multiple index records pointing to the same data row.

After this lesson, you will be able to explain the N:1 structure of MVI, create indexes using `CAST(... AS ... ARRAY)`, distinguish `MEMBER OF()`, `JSON_CONTAINS()`, and `JSON_OVERLAPS()`, read `EXPLAIN` to verify optimizer index usage, understand empty-array and NULL behaviors, evaluate limitations regarding ordering, range scans, covering indexes, foreign keys, collations, and DDL, and decide when to use MVI versus normalizing an array into a relational table.

## 1. The Problem: Finding a Row by an Element Inside a JSON Array

Suppose an application stores customers along with the postal codes where they can receive deliveries:

~~~json
{
  "name": "Lan",
  "zip_codes": [70000, 70001, 70003]
}
~~~

Table:

~~~sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    tenant_id INT NOT NULL,
    profile JSON NOT NULL
) ENGINE=InnoDB;
~~~

Query finding customers with code 70001:

~~~sql
SELECT customer_id, profile
FROM customers
WHERE 70001 MEMBER OF (profile->'$.zip_codes');
~~~

Without a suitable index, MySQL may have to read many rows and inspect each JSON document. A regular index on the entire `profile` column does not create a separate index entry for each element inside `zip_codes`.

A multi-valued index allows InnoDB to create one index record for each element of the selected array. For a row with three postal codes, the index holds three records all referencing that `customer_id`.

~~~text
One row in the customers table
customer_id = 42
zip_codes = [70000, 70001, 70003]

A multi-valued index
70000  ──┐
70001  ──┼──> customer_id = 42
70003  ──┘
~~~

This is an **N:1** relationship between index records and table rows: one row can produce many index records. MVI is an InnoDB secondary index designed for searching by elements in a JSON array.

MVI was introduced in MySQL 8.0.17. It does not exist in MySQL 5.7. Verify the server version before designing schemas or running migrations. [MySQL 8.0.17 Release Notes](https://dev.mysql.com/doc/relnotes/mysql/8.0/en/news-8-0-17.html).

## 2. How Does MVI Work?

An ordinary index can be pictured as follows:

| Primary key | Index value |
|---:|---|
| 10 | 70000 |
| 11 | 70001 |
| 12 | 70003 |

Each row contributes one index value for that key part.

With MVI, one row can contribute multiple values:

| Primary key | Element in JSON array | Index record |
|---:|---:|---|
| 10 | 70000 | 70000 -> 10 |
| 10 | 70001 | 70001 -> 10 |
| 10 | 70003 | 70003 -> 10 |
| 11 | 70001 | 70001 -> 11 |
| 12 | 70003 | 70003 -> 12 |

When searching for 70001, InnoDB can locate the index records carrying that value and fetch the corresponding rows.

MVI is implemented as a functional index over an implicitly generated virtual column derived from the JSON array expression. Users declare the `CAST` expression in the index; there is no need to manually create a virtual column to split out individual elements.

Characteristics of an MVI:

- Supported only on InnoDB tables.
- Is a secondary index, not a primary key.
- One key part can generate multiple index records for a single row.
- Can appear alongside single-valued key parts in a composite index.
- The JSON data remains stored in the JSON column; the index only accelerates element lookups.

MVI does not turn a JSON array into a relational table. It does not automatically enforce foreign keys per element, apply relational constraints per element, or provide all querying capabilities of a normalized child table.

## 3. Syntax for Creating a Multi-Valued Index

Basic structure:

~~~sql
CREATE INDEX index_name
ON table_name (
    (CAST(json_expression AS SQL_TYPE ARRAY))
);
~~~

Example:

~~~sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    profile JSON NOT NULL,
    INDEX idx_customer_zip (
        (CAST(profile->'$.zip_codes' AS UNSIGNED ARRAY))
    )
) ENGINE=InnoDB;
~~~

The expression:

~~~sql
CAST(profile->'$.zip_codes' AS UNSIGNED ARRAY)
~~~

means:

1. Extract the array at JSON path `$.zip_codes`.
2. `CAST` scalar elements to the specified SQL type.
3. Declare the result as an SQL data type array using the `ARRAY` keyword.
4. InnoDB creates corresponding index records for the array values.

You can create the index after the table already exists:

~~~sql
CREATE INDEX idx_customer_zip
ON customers (
    (CAST(profile->'$.zip_codes' AS UNSIGNED ARRAY))
);
~~~

Or:

~~~sql
ALTER TABLE customers
ADD INDEX idx_customer_zip (
    (CAST(profile->'$.zip_codes' AS UNSIGNED ARRAY))
);
~~~

In index definitions, the expression must be wrapped in the key part's parentheses. Therefore, you commonly see two pairs of parentheses around the `CAST` expression.

### Choosing the Right SQL Type

The type before `ARRAY` defines the data type of each index value. Choose the type based on actual data:

- `UNSIGNED`: non-negative integer codes such as numeric postal codes or numeric IDs.
- `SIGNED`: integers that may be negative.
- `CHAR`/`VARCHAR`: string elements with appropriate length and collation.
- Other types supported by `CAST`, subject to MVI rules and limits.

Do not use `CAST AS BINARY` for a multi-valued key part; the `BINARY` type is prohibited. `JSON` is also not a valid target type for creating an SQL array index.

The index type must match how the application queries. If data contains integers while the query compares against strings, `MEMBER OF()` will not automatically convert between string and numeric types. Standardize element types before creating the index.

### Arrays Must Contain Scalar Elements of the Same Logical Type

Good example:

~~~json
{
  "zip_codes": [70000, 70001, 70003]
}
~~~

Problematic example:

~~~json
{
  "zip_codes": [70000, "70001", null]
}
~~~

Arrays mixing numbers, strings, and JSON `null` make `CAST` and comparisons unpredictable. JSON `null` is not permitted inside values indexed by an MVI. Validate input data so elements have uniform types and contain no JSON `null`.

## 4. Using MEMBER OF() to Find an Element

`MEMBER OF()` checks whether a value is an element of a JSON array.

~~~sql
SELECT customer_id
FROM customers
WHERE 70001 MEMBER OF (profile->'$.zip_codes');
~~~

The result contains customers having element 70001 in `zip_codes`.

The optimizer can use MVI for `MEMBER OF()` in `WHERE` if the expression matches the index and the cost-based plan chooses that index.

### Data-Type Comparison Is Exact

`MEMBER OF()` does not automatically convert strings to numbers or numbers to strings.

~~~sql
SELECT
    17 MEMBER OF ('[23, "17", 17]') AS numeric_match,
    '17' MEMBER OF ('[23, "17", 17]') AS string_match;
~~~

The two checks have different value types. Do not rely on MySQL automatically converting numeric strings to numbers when searching elements in a JSON array.

If a value is stored as a string, the query must use a string. If stored as a number, the query must use a number.

Partial matching also does not occur: searching for number `7` does not match element `17`; searching for string `'a'` does not match `'abc'`.

### MEMBER OF() Returning NULL

If the test value or JSON array is SQL `NULL`, `MEMBER OF()` returns `NULL`. That result is neither `TRUE` nor `FALSE`.

For JSON object or array elements, pass a properly typed JSON value using `CAST(... AS JSON)`, `JSON_OBJECT()`, or `JSON_ARRAY()` as appropriate. MVI is most commonly used for scalar arrays such as numbers or strings.

## 5. Distinguishing MEMBER OF(), JSON_CONTAINS(), and JSON_OVERLAPS()

All three operations can be accelerated by MVI when used appropriately in `WHERE`, yet their semantics differ.

| Function/Operator | Meaning for Arrays | Business Example |
|---|---|---|
| `MEMBER OF()` | Whether a scalar is inside the array | Customer has zip code 70001 |
| `JSON_CONTAINS()` | Every element of candidate must exist in target | Customer has both zip codes 70001 and 70003 |
| `JSON_OVERLAPS()` | Only needs at least one shared element | Customer has any of the supported zip codes |

### MEMBER OF(): Finding a Single Value

~~~sql
SELECT customer_id
FROM customers
WHERE 70001 MEMBER OF (profile->'$.zip_codes');
~~~

This checks whether a scalar is an element of the array.

### JSON_CONTAINS(): All Candidate Elements Must Exist

~~~sql
SELECT customer_id
FROM customers
WHERE JSON_CONTAINS(
    profile->'$.zip_codes',
    CAST('[70001, 70003]' AS JSON)
);
~~~

`candidate` is a two-element array. A row matches only if `target` array contains both 70001 and 70003.

When `candidate` is a scalar, `JSON_CONTAINS` on a target array checks whether that scalar is in the array.

### JSON_OVERLAPS(): Only One Overlapping Element Needed

~~~sql
SELECT customer_id
FROM customers
WHERE JSON_OVERLAPS(
    profile->'$.zip_codes',
    CAST('[70001, 70003]' AS JSON)
);
~~~

A row matches if the target array has at least one element from the candidate array.

Example:

| zip_codes | JSON_CONTAINS [70001,70003] | JSON_OVERLAPS [70001,70003] |
|---|---:|---:|
| [70001,70003] | 1 | 1 |
| [70001,70002] | 0 | 1 |
| [70003] | 0 | 1 |
| [70002,70004] | 0 | 0 |

`JSON_CONTAINS` is an AND condition over candidate elements. `JSON_OVERLAPS` is an OR condition: only one shared element is needed.

Do not swap one function for the other if business requirements differ. A query can return significantly more or fewer rows solely from changing containment/overlap semantics.

## 6. How the Optimizer Uses MVI

MySQL can use MVI to locate rows for the following predicates in `WHERE`:

- `MEMBER OF()`
- `JSON_CONTAINS()`
- `JSON_OVERLAPS()`

Example:

~~~sql
EXPLAIN
SELECT customer_id
FROM customers
WHERE 70001 MEMBER OF (profile->'$.zip_codes');
~~~

Fields to check:

| EXPLAIN Field | What to Observe |
|---|---|
| `possible_keys` | Whether the MVI appears in the list of candidate indexes |
| `key` | Whether the optimizer chose the MVI |
| `type` | Access type `range` may appear when using MVI |
| `rows` | Estimated rows to read |
| `filtered` | Percentage of rows remaining after filtering |
| `Extra` | Remaining conditions checked after fetching rows |

`JSON_CONTAINS` example:

~~~sql
EXPLAIN
SELECT customer_id
FROM customers
WHERE JSON_CONTAINS(
    profile->'$.zip_codes',
    CAST('[70001,70003]' AS JSON)
);
~~~

`JSON_OVERLAPS` example:

~~~sql
EXPLAIN
SELECT customer_id
FROM customers
WHERE JSON_OVERLAPS(
    profile->'$.zip_codes',
    CAST('[70001,70003]' AS JSON)
);
~~~

The optimizer is not forced to pick the index in every situation. With small tables, low-selectivity values, or stale statistics, a table scan may be cheaper.

After creating an index on an InnoDB table, you can update statistics:

~~~sql
ANALYZE TABLE customers;
~~~

Do not merely see that an index exists in `SHOW INDEX` and assume queries are using it. Check `EXPLAIN` and measure on production-scale data.

### JSON Expressions Must Match the Index

The index is created on a specific JSON path. Queries should use the same JSON expression and path defined by the index.

Example index:

~~~sql
CREATE INDEX idx_customer_zip
ON customers (
    (CAST(profile->'$.zip_codes' AS UNSIGNED ARRAY))
);
~~~

Matching predicate:

~~~sql
WHERE 70001 MEMBER OF (profile->'$.zip_codes')
~~~

If the application queries a different path such as `$.preferred_zip` or `$.addresses[*].zip`, the index on `$.zip_codes` does not automatically serve that path.

Review JSON expressions, element types, and predicates before creating indexes. Avoid creating multiple redundant MVIs for rarely queried paths.

## 7. MVI in Composite Indexes

An MVI can serve as one key part inside a composite index alongside single-valued key parts.

Example:

~~~sql
CREATE INDEX idx_tenant_zip
ON customers (
    tenant_id,
    (CAST(profile->'$.zip_codes' AS UNSIGNED ARRAY))
);
~~~

Query:

~~~sql
SELECT customer_id
FROM customers
WHERE tenant_id = 10
  AND 70001 MEMBER OF (profile->'$.zip_codes');
~~~

The index can support combining the `tenant_id` predicate with searching an element in the array.

There can be **only one multi-valued key part per index**. Remaining key parts must be single-valued key parts. The MVI key part can appear at different positions within a composite index per supported syntax.

Do not create a composite index with two `ARRAY` expressions:

~~~sql
-- Invalid: two multi-valued key parts in the same index
CREATE INDEX idx_invalid
ON customers (
    (CAST(profile->'$.zip_codes' AS UNSIGNED ARRAY)),
    (CAST(profile->'$.tag_ids' AS UNSIGNED ARRAY))
);
~~~

If two independent arrays must be queried simultaneously, consider two separate MVIs or normalizing each relationship into a child table.

### Choosing Key Part Order

With composite indexes, key part order still matters for queries filtering by single-valued columns. Design based on workload:

- Tenant/account columns frequently filtered by equality can come first.
- MVI goes in a position matching array predicates.
- Test queries with and without the tenant filter.
- Do not assume a single composite index serves every query variant well.

MVI does not abolish the leftmost prefix principle of composite indexes. Measure execution plans on real queries.

## 8. MVI Does Not Support Ordering or Range Scans

This is an important limitation.

An MVI cannot be used to:

- Sort results by array element like an ordinary B-tree index.
- Support range scans across array value intervals.
- Serve as a primary key.
- Use `ASC` or `DESC` in the key part definition.

Example query:

~~~sql
SELECT customer_id
FROM customers
WHERE 70000 <= ANY (profile->'$.zip_codes');
~~~

You cannot assume MVI will serve a range search like a single-valued index. MVI is optimized for supported membership/containment/overlap checks.

Similarly, if the requirement is retrieving customers ordered by ascending zip code, MVI does not provide that order. You must sort results or use a different data model.

If business logic needs:

- Finding values within a range.
- Sorting by individual elements.
- Paginating by element.
- Frequent statistics or `GROUP BY` by individual element.

consider a relational child table with one row per element.

## 9. MVI Is Not a Covering Index

A covering index holds every column required by a query, allowing the engine to return results without reading clustered rows.

MVI does not support index-only scans / covering indexes. Because index records for multiple elements point to the same clustered row and carry specific access constraints, MySQL still needs to access table rows to fetch result columns or verify conditions.

Example:

~~~sql
SELECT customer_id, profile
FROM customers
WHERE 70001 MEMBER OF (profile->'$.zip_codes');
~~~

MVI can help find `customer_id` faster, but it does not mean the full `profile` is returned directly from the index.

When queries return many columns or many rows, clustered-record lookup costs still apply. Do not expect MVI to behave like a standard covering secondary index.

## 10. Limitations with Primary Keys, Foreign Keys, and Index Prefixes

Key limitations:

| Capability | MVI |
|---|---|
| Secondary index | Yes |
| Primary key | No |
| UNIQUE secondary index | Yes; uniqueness applies across generated index values |
| Foreign key specification | No |
| Index prefix | No |
| ASC/DESC | No |
| Range scan | No |
| Index-only scan | No |
| Covering index | No |
| Composite index with single-valued key parts | Yes |
| Two MVI key parts in the same index | No |

An MVI can be defined as a `UNIQUE` index, but uniqueness applies to the generated index values. This is not a relational constraint replacing a foreign key. If you must guarantee that every ID in a JSON array references an existing parent row, MVI cannot enforce that.

If existing data has duplicate values under unique index rules, creating a `UNIQUE` MVI will fail. Once the index exists, writes producing a duplicate index key may also be rejected. Choose `UNIQUE` only when business logic requires uniqueness across the entire generated key (including single-valued key parts if the index is composite); it is not a foreign key and does not verify existence of referenced rows.

Example storing product IDs in a JSON array:

~~~json
{
  "product_ids": [100, 101, 102]
}
~~~

MVI can accelerate finding orders containing `product_id` 101, yet does not guarantee product 101 exists in the `products` table.

If referential integrity is needed, use an `order_items` table:

~~~sql
CREATE TABLE order_items (
    order_id BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (order_id, product_id),
    CONSTRAINT fk_order_items_order
        FOREIGN KEY (order_id) REFERENCES orders(order_id),
    CONSTRAINT fk_order_items_product
        FOREIGN KEY (product_id) REFERENCES products(product_id)
) ENGINE=InnoDB;
~~~

This is the proper relational model when each element has identity, its own attributes, or requires constraints.

## 11. Empty Arrays, SQL NULL, and JSON null

MVI exhibits special behavior with empty values and NULL.

| Value of Array Expression | Index Behavior |
|---|---|
| Empty array `[]` | Creates no index entries for the row |
| Expression evaluates to SQL `NULL` | Stores one index entry containing `NULL` pointing to the row |
| JSON/typed array column is SQL `NULL` | InnoDB stores one `NULL` entry pointing to the row |
| JSON `null` element inside array | Not permitted; raises `Invalid JSON value` error |

Example:

~~~json
{"zip_codes": []}
~~~

The row has no index entry for `zip_codes`. This makes sense if membership queries only search for concrete values, since an empty array has no elements.

If the JSON path does not exist, the expression may return SQL `NULL`. Distinguish a path with no data from an empty array.

Do not place JSON `null` inside an indexed array:

~~~json
{"zip_codes": [70001, null, 70003]}
~~~

Validate and normalize data before creating the index. If the application needs to represent "unknown", "no data yet", or "not applicable", establish a clear convention among SQL `NULL`, missing path, and empty array.

### SQL NULL Differs from JSON null

- SQL `NULL` is the NULL state of an SQL expression/column.
- JSON `null` is the `null` literal inside a JSON document.
- MVI can create a `NULL` index entry when the array expression returns SQL `NULL`.
- JSON `null` as an element of an indexed array is prohibited.

Do not lump these cases into a single rule during validation or reporting.

## 12. Limit on Number of Elements per Row

MVI generates multiple index records for one row. The total length of key values generated for a single row is bounded by the amount of data that fits on a single undo log page: 65,221 bytes according to the MySQL 9.7 documentation.

There is no fixed element count applicable across all data types. The maximum number of elements depends on individual value sizes. Documentation notes a test could hold up to 1,604 integer keys for one row, though this is not a universal guarantee across all schemas.

When the limit is exceeded, MySQL can return an error like:

~~~text
ERROR 3905 (HY000):
Exceeded max number of values per record for multi-valued index
~~~

Design implications:

- Do not use MVI for unbounded arrays.
- Enforce a maximum array length at the application layer.
- Measure real element sizes.
- Monitor insert/update errors as arrays grow.
- Switch to a child table if a row can hold thousands or tens of thousands of frequently changing elements.

The index byte limit is an important physical constraint, not merely a performance issue.

## 13. Data Type, Charset, and Collation Limitations

A multi-valued key part must be a JSON expression `CAST` to an SQL data type `ARRAY`.

Notes:

- Do not `CAST` to `BINARY ARRAY`.
- Do not `CAST` to `JSON ARRAY`.
- For strings, only certain charset/collation combinations are supported.
- Combinations listed in the MySQL 9.7 documentation include the `binary` charset with its default binary collation and `utf8mb4` with the default `utf8mb4_0900_as_cs` collation.
- Do not use `USING HASH`; InnoDB uses B-tree.
- Index prefixes are not supported for MVI.

If you need to index a string array, check the actual collation of the expression and target type. Do not assume every `utf8mb4` collation is accepted.

Example design with an integer array usually avoids collation complications:

~~~sql
CREATE INDEX idx_zip_codes
ON customers (
    (CAST(profile->'$.zip_codes' AS UNSIGNED ARRAY))
);
~~~

For string arrays, verify charset/collation and case-sensitivity rules before creating the index.

## 14. Creating an MVI Does Not Support Online Index Creation

A critical operational limitation: online creation of a multi-valued index is not supported. Creating an MVI uses `ALGORITHM=COPY`.

That means index creation may have to copy/rebuild the table, consuming significant:

- Disk space.
- I/O.
- CPU.
- Metadata lock duration during relevant phases.
- Resources for generating index entries from every JSON element.

Before creating an MVI on a large table:

1. Check the row count and JSON document sizes.
2. Estimate the total number of elements to index.
3. Verify disk space for the copy/rebuild operation.
4. Assess I/O load and replication lag.
5. Test on a production-sized dataset copy.
6. Schedule deployment within an appropriate maintenance window.
7. Prepare a rollback or recovery plan if DDL fails.

Do not assume `CREATE INDEX` for an MVI shares the same online DDL behavior as a standard secondary index.

After creating the index successfully, update statistics with `ANALYZE TABLE` when appropriate and verify query plans.

## 15. Write Cost and Updating JSON Arrays

MVI speeds up certain read queries, but every indexed element adds an index record.

Example:

- Row A with 2 zip codes: generates roughly 2 index entries.
- Row B with 20 zip codes: generates roughly 20 index entries.
- Row C with 200 zip codes: generates roughly 200 index entries.

When updating a JSON array, InnoDB must update the corresponding index entries. If arrays change frequently and contain many elements, write overhead can be substantial.

Evaluate:

- Average and high-percentile element counts.
- `INSERT`/`UPDATE` frequency.
- Churn rate of elements inside arrays.
- Index footprint.
- Lock contention and write amplification.
- How much membership query latency improves.

Do not add MVIs to every JSON array. Index only paths with genuine search workloads.

## 16. When to Use MVI vs. When to Normalize?

MVI is suitable when:

- A row holds a small or moderate set of scalar values.
- The application frequently searches for rows by an element in the array.
- The relationship does not need foreign keys per element.
- Range scans, ordering, or grouping by individual elements are not required.
- The JSON array is part of a flexible document updated per row.
- Queries use `MEMBER OF()`, `JSON_CONTAINS()`, or `JSON_OVERLAPS()`.

A relational child table is better suited when:

- Each element has its own attributes.
- Foreign keys and referential integrity are required.
- `UNIQUE`/constraints per element with explicit relational semantics are needed.
- Range queries or sorting by element values are needed.
- Frequent joins with other tables are needed.
- Statistics, `GROUP BY`, or pagination per element are needed.
- Arrays have large element counts or change constantly.
- Queries span multiple dimensions and varied predicates.

| Criterion | JSON Array + MVI | Relational Child Table |
|---|---|---|
| Finding a single element | Good with supported predicates | Good with B-tree index |
| Finding multiple elements at once | `MEMBER OF`/`CONTAINS`/`OVERLAPS` | `JOIN`/`GROUP BY` |
| Foreign key per element | No | Yes |
| Range scan by element | No | Yes |
| `ORDER BY` element | Not supported via MVI | Yes |
| Covering index | No | Possible |
| Data flexibility | High | More explicit schema |
| Updating a single element | Update JSON and MVI | `INSERT`/`UPDATE`/`DELETE` child row |
| Very large arrays | Subject to byte/index entry limits | Easier to scale and paginate |

A helpful rule of thumb: if an element inside an array is actually an independent business relationship, consider a child-table model before choosing a JSON array.

## 17. Practice Lab: Creating an MVI and Testing the Three Predicates

This lab uses a `customers` table storing an array of postal codes. Data is deliberately designed to distinguish `MEMBER OF`, `JSON_CONTAINS`, and `JSON_OVERLAPS`.

### Step 1: Create Database and Table

~~~sql
CREATE DATABASE IF NOT EXISTS mysql_mvi_lab;
USE mysql_mvi_lab;

CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    tenant_id INT NOT NULL,
    profile JSON NOT NULL,
    KEY idx_tenant (tenant_id)
) ENGINE=InnoDB;
~~~

### Step 2: Load Data

~~~sql
INSERT INTO customers (customer_id, tenant_id, profile)
VALUES
    (1, 10, '{"name":"Lan","zip_codes":[70000,70001,70003]}'),
    (2, 10, '{"name":"Minh","zip_codes":[70001,70002]}'),
    (3, 10, '{"name":"An","zip_codes":[70003]}'),
    (4, 20, '{"name":"Binh","zip_codes":[70002,70004]}'),
    (5, 20, '{"name":"Hoa","zip_codes":[]}'),
    (6, 20, '{"name":"Nam","zip_codes":[70001,70003]}');
~~~

### Step 3: Query Before Creating MVI

~~~sql
EXPLAIN
SELECT customer_id
FROM customers
WHERE 70001 MEMBER OF (profile->'$.zip_codes');
~~~

Observe `type`, `possible_keys`, `key`, and `rows`. Because the lab table is small, the optimizer may pick a table scan.

### Step 4: Create the Multi-Valued Index

~~~sql
CREATE INDEX idx_customer_zip
ON customers (
    (CAST(profile->'$.zip_codes' AS UNSIGNED ARRAY))
);
~~~

### Step 5: Update Statistics

~~~sql
ANALYZE TABLE customers;
~~~

### Step 6: Test MEMBER OF

~~~sql
SELECT customer_id
FROM customers
WHERE 70001 MEMBER OF (profile->'$.zip_codes')
ORDER BY customer_id;
~~~

Expected result: customers 1, 2, and 6.

### Step 7: Test JSON_CONTAINS

~~~sql
SELECT customer_id
FROM customers
WHERE JSON_CONTAINS(
    profile->'$.zip_codes',
    CAST('[70001,70003]' AS JSON)
)
ORDER BY customer_id;
~~~

Expected result: customers 1 and 6, since both contain both codes.

### Step 8: Test JSON_OVERLAPS

~~~sql
SELECT customer_id
FROM customers
WHERE JSON_OVERLAPS(
    profile->'$.zip_codes',
    CAST('[70001,70003]' AS JSON)
)
ORDER BY customer_id;
~~~

Expected result: customers 1, 2, 3, and 6, since each customer has at least one of the two codes.

### Step 9: Check EXPLAIN After Indexing

~~~sql
EXPLAIN
SELECT customer_id
FROM customers
WHERE 70001 MEMBER OF (profile->'$.zip_codes');
~~~

Continue checking `JSON_CONTAINS` and `JSON_OVERLAPS`:

~~~sql
EXPLAIN
SELECT customer_id
FROM customers
WHERE JSON_CONTAINS(
    profile->'$.zip_codes',
    CAST('[70001,70003]' AS JSON)
);

EXPLAIN
SELECT customer_id
FROM customers
WHERE JSON_OVERLAPS(
    profile->'$.zip_codes',
    CAST('[70001,70003]' AS JSON)
);
~~~

If the optimizer chooses the MVI, `key` will show `idx_customer_zip` and access `type` may be `range`. Exact results depend on statistics, table size, and selectivity. A lab table with only a few rows does not force the optimizer to pick the index.

### Step 10: Observe Empty Array Behavior

Customer 5 has `zip_codes` as an empty array. Query:

~~~sql
SELECT customer_id
FROM customers
WHERE 70001 MEMBER OF (profile->'$.zip_codes');
~~~

does not return `customer_id` 5. An empty array has no index entry and contains no searched element.

### Step 11: Update the Array

~~~sql
UPDATE customers
SET profile = JSON_SET(
    profile,
    '$.zip_codes',
    JSON_ARRAY(70001, 70005)
)
WHERE customer_id = 5;
~~~

Query again:

~~~sql
SELECT customer_id
FROM customers
WHERE 70005 MEMBER OF (profile->'$.zip_codes');
~~~

Customer 5 is now found. InnoDB updates the MVI to match the JSON change.

### Step 12: Inspect Index Metadata

~~~sql
SHOW INDEX FROM customers;
~~~

Check index name, `non_unique`, `seq_in_index`, and index expression. You can use `SHOW CREATE TABLE` to inspect the full definition.

~~~sql
SHOW CREATE TABLE customers;
~~~

### Cleanup

~~~sql
DROP DATABASE mysql_mvi_lab;
~~~

Only run `DROP DATABASE` on the lab database you just created.

## 18. Common Errors and Fixes

| Symptom | Cause | Fix |
|---|---|---|
| Cannot create MVI | Table does not use InnoDB | Use InnoDB |
| `CAST ARRAY` errors | Invalid JSON path or target type | Check expression and SQL `ARRAY` type |
| Value not found despite appearing in JSON | String/numeric type mismatch or wrong JSON path | Standardize element types and verify path |
| JSON `null` causes `INSERT`/`UPDATE` error | JSON `null` is forbidden inside indexed arrays | Remove JSON `null` or define different data rules |
| Rows with empty array do not appear in index lookup | Empty arrays produce no index entries | Expected behavior; verify business logic |
| `EXPLAIN` does not pick MVI | Small table, low selectivity, stale stats, or non-matching predicate | `ANALYZE TABLE`, check `WHERE`, and test on realistic data |
| `JSON_CONTAINS` query returns fewer/different rows than expected | Confusing all-elements vs. any-element semantics | Use `JSON_OVERLAPS` if only one shared element is needed |
| `JSON_OVERLAPS` query returns more rows than expected | Only one shared element is needed to match | Use `JSON_CONTAINS` if all candidate elements are required |
| Cannot use MVI for `ORDER BY` | MVI does not support ordering | Sort results or use a child table |
| Range query does not use MVI | MVI does not support range scans | Normalize into a child table with a B-tree index |
| Want foreign key from JSON element | MVI cannot participate in foreign key specifications | Create a child table and FK |
| Want covering index | MVI does not support index-only scans | Design queries/relational tables accordingly |
| Cannot create two MVIs in the same index | Only one multi-valued key part per index | Create two separate indexes or normalize data |
| Creating index copies table slowly | Online MVI creation not supported; uses `ALGORITHM=COPY` | Plan disk space and maintenance window |
| Oversized array causes DML errors | Exceeded max total key-value bytes per row | Limit element count or use a child table |
| Cannot create string MVI | Unsupported charset/collation | Check `binary` or `utf8mb4_0900_as_cs` |
| DML slows down after adding MVI | Every element creates an index entry updated when JSON changes | Evaluate write amplification and drop unused indexes |

## 19. MVI Design and Operations Checklist

- [ ] Server runs MySQL 8.0.17 or later.
- [ ] Table uses InnoDB.
- [ ] Chosen JSON path is accurate and stable.
- [ ] Array elements have consistent scalar types.
- [ ] SQL `ARRAY` type matches data and queries.
- [ ] Data contains no JSON `null` inside indexed arrays.
- [ ] Differences among SQL `NULL`, JSON `null`, and empty arrays are understood.
- [ ] Predicate is in `WHERE` and uses `MEMBER OF`, `JSON_CONTAINS`, or `JSON_OVERLAPS`.
- [ ] Correct all-elements vs. any-element semantics chosen.
- [ ] Verified JSON expression in queries matches the index definition.
- [ ] At most one multi-valued key part per index.
- [ ] Do not expect MVI to support `ORDER BY`, range scans, or covering scans.
- [ ] Do not use MVI as primary key or foreign key.
- [ ] Evaluated whether a composite index with single-valued key parts is needed.
- [ ] Estimated element counts and total key-value size per row.
- [ ] Evaluated write amplification when JSON arrays change.
- [ ] Verified charset/collation if indexing strings.
- [ ] Accounted for `ALGORITHM=COPY` and disk space when creating the index.
- [ ] Ran `ANALYZE TABLE` when appropriate.
- [ ] Checked `EXPLAIN` on production-scale data.
- [ ] Considered a child table if FK, ranges, ordering, joins, or per-element analytics are needed.

## 20. Principles to Remember

1. MVI is an InnoDB secondary index for JSON arrays.
2. MVI creates multiple index records pointing to one data row, in an N:1 relationship.
3. MVI has existed since MySQL 8.0.17.
4. Create an MVI with `CAST(JSON expression AS SQL_TYPE ARRAY)`.
5. The optimizer can use MVI for `MEMBER OF()`, `JSON_CONTAINS()`, and `JSON_OVERLAPS()` in `WHERE`.
6. `JSON_CONTAINS` requires all candidate elements to be contained; `JSON_OVERLAPS` only requires one shared element.
7. `MEMBER OF` compares elements by JSON type; do not rely on automatic string/numeric conversion.
8. Each index has at most one multi-valued key part, though it can combine with single-valued key parts.
9. MVI does not support ordering, range scans, index-only scans, or covering indexes.
10. MVI cannot be a primary key and cannot be used in foreign key specifications.
11. Empty arrays produce no index entries; JSON `null` inside an indexed array is prohibited.
12. Total key-value length per row is limited by an undo log page; there is no single fixed element count for all types.
13. Creating an MVI does not support online index creation and uses `ALGORITHM=COPY`.
14. Every element adds index storage and update cost.
15. If relationships, constraints, ranges, ordering, or per-element analytics are needed, consider a normalized child table.

## Official References

Syntaxes and limits in this lesson were cross-checked against the **MySQL 9.7 Reference Manual** and MySQL 8.0 release notes:

1. [MySQL 9.7 — CREATE INDEX: Multi-Valued Indexes](https://dev.mysql.com/doc/refman/9.7/en/create-index.html): `CAST ARRAY` syntax, composite indexes, supported predicates, nullability, and MVI limitations.
2. [MySQL 9.7 — Functions That Search JSON Values](https://dev.mysql.com/doc/refman/9.7/en/json-search-functions.html): `MEMBER OF()`, `JSON_CONTAINS()`, `JSON_OVERLAPS()`, and search semantics.
3. [MySQL 9.7 — CREATE TABLE Statement](https://dev.mysql.com/doc/refman/9.7/en/create-table.html): declaring key parts and multi-valued indexes in `CREATE TABLE`.
4. [MySQL 9.7 — Multiple-Column Indexes](https://dev.mysql.com/doc/refman/9.7/en/multiple-column-indexes.html): composite indexes and leftmost prefix.
5. [MySQL 8.0 Release Notes — What Is New in MySQL 8.0](https://dev.mysql.com/doc/refman/8.0/en/mysql-nutshell.html): MVI supported by InnoDB since MySQL 8.0.17.
6. [MySQL 8.0.17 Release Notes](https://dev.mysql.com/doc/relnotes/mysql/8.0/en/news-8-0-17.html): introduction of MVI, `CAST ARRAY`, and optimizer-supported predicates.
