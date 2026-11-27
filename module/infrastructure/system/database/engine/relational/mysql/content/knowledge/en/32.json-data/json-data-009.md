# Generated Columns, Functional Indexes, and Indexing JSON Paths

MySQL stores JSON documents in the JSON data type, but does not automatically create a B-tree for every property or path inside a document. If queries frequently filter by `$.brand`, `$.price`, or check an element in the `$.tags` array, simply calling JSON_EXTRACT in WHERE can force MySQL to read and evaluate the expression across many rows.

There are three key techniques:

- **Generated column**: create a column from an expression, typically a JSON path, and then index that column.
- **Functional index**: index an expression directly without declaring a visible generated column in the schema.
- **Multi-valued index**: index multiple values from a JSON array to find rows containing a specific element.

The three techniques have different purposes and limits. Generated columns fit when a JSON path becomes a stable business attribute. Functional indexes fit when an expression is reused repeatedly without needing a named auxiliary column. Multi-valued indexes fit scalar arrays requiring membership checks. None of these techniques automatically replaces a normalized relational model when data requires foreign keys, constraints, or complex JOINs.

This lesson falls within the `DATABASE_MYSQL` scope: designing indexes for JSON paths, choosing proper data types and collations, understanding leftmost prefix and index-matching expression rules, reading EXPLAIN to verify the optimizer, and evaluating write overhead and MySQL version limits.

## 1. Why Standard Indexes Do Not Directly Index Every JSON Property

Example product table:

~~~sql
CREATE TABLE product (
    product_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    product_name VARCHAR(150) NOT NULL,
    attributes JSON NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (product_id)
) ENGINE = InnoDB;
~~~

A JSON document may contain many properties:

~~~json
{
  "brand": "Northwind",
  "price": 129.90,
  "active": true,
  "tags": ["sale", "outdoor"],
  "warehouse": {
    "city": "Da Nang",
    "code": "DN-01"
  }
}
~~~

Query finding products by brand:

~~~sql
SELECT product_id, product_name
FROM product
WHERE JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.brand')) = 'Northwind';
~~~

A JSON column ensures data is stored as valid JSON, but does not create individual indexes per path. Without an appropriate index structure, MySQL may have to read many rows and evaluate JSON_EXTRACT.

You can inspect the plan:

~~~sql
EXPLAIN
SELECT product_id, product_name
FROM product
WHERE JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.brand')) = 'Northwind';
~~~

If there is no suitable access path, the `type` column may show `ALL`, indicating the optimizer expects a table scan. On large tables with frequent queries, this is a sign to evaluate a generated column or functional index.

## 2. Three Techniques for Indexing JSON

| Technique | How It Works | Best For |
|---|---|---|
| Generated column + index | Extracts a JSON value into an SQL-typed column and creates an index on it | Stable scalar paths needing a clear column name or reuse across many queries |
| Functional index | Indexes an expression directly; MySQL implements it via a hidden virtual generated column | Fixed expressions without needing a visible extra column in the schema |
| Multi-valued index | One JSON array row can generate multiple index entries | Finding rows containing a specific element in a scalar array |

Before choosing, determine:
- Is the JSON path fixed or does it vary per request?
- Is the value a string, number, boolean, date, or array?
- Are JOINs, foreign keys, or constraints needed on that value?
- Is the query equality, range, membership, or sort?
- Does the extracted column need to appear in SELECT and many other queries?
- Does your MySQL version support the required feature?

## 3. What Is a Generated Column?

A generated column is a column whose value is computed from an expression. Applications do not write values to it directly like ordinary columns; MySQL computes the value from the declared expression.

Syntax:

~~~sql
column_name data_type
    [GENERATED ALWAYS] AS (expression)
    [VIRTUAL | STORED]
~~~

Two kinds:

- `VIRTUAL`: the value is computed when the column is read; not stored in the clustered row record like a STORED column.
- `STORED`: the value is computed on write and stored in the row.

If neither VIRTUAL nor STORED is specified, a generated column defaults to VIRTUAL.

Example extracting `brand` from JSON:

~~~sql
ALTER TABLE product
    ADD COLUMN brand VARCHAR(64)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_ai_ci
        GENERATED ALWAYS AS (
            JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.brand'))
        ) VIRTUAL;
~~~

The `brand` column is an SQL scalar of type VARCHAR. We can query it like a normal column:

~~~sql
SELECT product_id, product_name, brand
FROM product
WHERE brand = 'Northwind';
~~~

### 3.1. Why Is an Explicit Data Type Needed?

JSON_EXTRACT returns a JSON value. To index by scalar, you must convert the value to an appropriate SQL type.

Examples:
- Brand code: VARCHAR.
- Price: DECIMAL.
- Quantity: UNSIGNED or an appropriate integer type.
- Status flag: TINYINT/BOOLEAN by convention.
- Date: DATE or DATETIME if data has a valid format.

Do not extract everything as VARCHAR if business logic needs numeric or date comparisons. String comparisons can produce different ordering than arithmetic: `'100'` comes before `'20'` lexicographically.

### 3.2. VIRTUAL or STORED?

| Criterion | VIRTUAL | STORED |
|---|---|---|
| Value in clustered row | Not stored like a regular column | Stored |
| Computation | Computed on read, unless materialized via an index | Computed and stored on write |
| Row size | Smaller | Increases by value size |
| Index | Secondary indexes can be created on virtual generated columns with InnoDB | Indexes can be created |
| Write cost | Still computes and updates index if indexed | Computes value, stores column, and updates index if indexed |
| When suitable | Auxiliary column primarily serving indexes or queries | Frequently read values, expensive computations, or explicitly stored in row |

A common point of confusion: an index on a VIRTUAL generated column still stores key values inside the secondary index structure. VIRTUAL only means the value is not stored in the clustered row like a STORED column; it does not mean the index must recompute the expression by scanning JSON on every lookup.

STORED is not automatically faster in all cases. It increases row size and write cost. Measure on your actual workload.

## 4. Creating an Index on a JSON-Extracting Generated Column

After adding `brand`, create the index:

~~~sql
CREATE INDEX idx_product_brand
ON product (brand);
~~~

Query:

~~~sql
SELECT product_id, product_name
FROM product
WHERE brand = 'Northwind';
~~~

The optimizer can use `idx_product_brand` to locate rows with matching `brand`.

Check:

~~~sql
EXPLAIN
SELECT product_id, product_name
FROM product
WHERE brand = 'Northwind';
~~~

Inspect indexes:

~~~sql
SHOW INDEX FROM product;
~~~

### 4.1. Extracting Price as DECIMAL

Add a generated column for price:

~~~sql
ALTER TABLE product
    ADD COLUMN price DECIMAL(12, 2)
        GENERATED ALWAYS AS (
            CAST(
                JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.price'))
                AS DECIMAL(12, 2)
            )
        ) VIRTUAL,
    ADD INDEX idx_product_price (price);
~~~

Range query:

~~~sql
SELECT product_id, product_name, price
FROM product
WHERE price >= 100.00
  AND price < 200.00
ORDER BY price;
~~~

The B-tree index on `price` can support equality, range, and certain access orders. Whether filesort is avoided also depends on predicates, ORDER BY, and the actual plan.

### 4.2. Extracting Booleans

Example `active` attribute:

~~~sql
ALTER TABLE product
    ADD COLUMN is_active TINYINT
        GENERATED ALWAYS AS (
            CASE
                WHEN JSON_EXTRACT(attributes, '$.active') = CAST('true' AS JSON)
                    THEN 1
                WHEN JSON_EXTRACT(attributes, '$.active') = CAST('false' AS JSON)
                    THEN 0
                ELSE NULL
            END
        ) VIRTUAL,
    ADD INDEX idx_product_active (is_active);
~~~

This approach distinguishes `true`, `false`, and missing/mistyped cases using NULL. JSON Schema validation at the write layer may be needed to ensure `active` is always a boolean.

Do not perform arbitrary CASTs without defining how mistyped JSON values are handled. Invalid data can cause warnings, unexpected conversions, or errors depending on the expression and SQL mode.

## 5. Missing Paths, JSON null, and SQL NULL

When indexing a JSON path, explicitly decide how to represent each case:

1. Path does not exist in the document.
2. Path exists with JSON null.
3. Path exists with a properly typed scalar value.
4. Path exists but with the wrong type, e.g., string instead of number.
5. Source JSON column is SQL NULL if the schema allows it.

These cases should not be conflated blindly. For example, JSON_EXTRACT returns SQL NULL when a path does not exist; JSON null is a JSON value, and its conversion via JSON_UNQUOTE/CAST can differ from SQL NULL.

You can inspect:

~~~sql
SELECT
    JSON_EXTRACT(attributes, '$.brand') AS brand_json,
    JSON_TYPE(JSON_EXTRACT(attributes, '$.brand')) AS brand_type,
    JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.brand')) AS brand_text
FROM product;
~~~

If you need to distinguish missing from JSON null, use JSON_CONTAINS_PATH and JSON_TYPE:

~~~sql
SELECT
    JSON_CONTAINS_PATH(attributes, 'one', '$.brand') AS path_exists,
    JSON_TYPE(JSON_EXTRACT(attributes, '$.brand')) AS brand_type
FROM product;
~~~

Design generated expressions so NULL cases carry accurate business semantics. In particular, test documents with missing paths, JSON null, and wrong types before creating indexes on production tables.

## 6. What Is a Functional Index?

A functional index lets you index an expression directly instead of creating a visible named generated column.

MySQL has supported functional key parts since MySQL 8.0.13. Functional indexes are implemented internally via hidden virtual generated columns.

Example:

~~~sql
CREATE INDEX idx_product_brand_expr
ON product (
    (
        CAST(
            attributes->>'$.brand'
            AS CHAR(64) CHARACTER SET utf8mb4
        ) COLLATE utf8mb4_0900_ai_ci
    )
);
~~~

Note the syntax has two pairs of parentheses around the key part expression. The expression itself must be wrapped in its own parentheses.

Queries must use an expression matching the index expression:

~~~sql
SELECT product_id, product_name
FROM product
WHERE (
    CAST(
        attributes->>'$.brand'
        AS CHAR(64) CHARACTER SET utf8mb4
    ) COLLATE utf8mb4_0900_ai_ci
) = 'Northwind';
~~~

In MySQL, `->>` is shorthand for JSON_UNQUOTE(JSON_EXTRACT()). However, for the optimizer to reliably recognize the functional index, use the matching expression with the same result type and collation as when creating the index. Do not arbitrarily change CAST, CHAR length, or COLLATE and expect the index to always be matched.

### 6.1. Why Must JSON Results Be CAST?

JSON_UNQUOTE/`->>` expressions can have a long string result type such as LONGTEXT. Functional key parts cannot use types incompatible with index key limits like that. CASTing to CHAR with a bounded length establishes an indexable key type.

Length must be chosen according to the data domain:
- Too short can truncate values and alter semantics.
- Too long widens the index and increases storage cost.
- Charset and collation affect comparisons and key size.

If `brand` has a business limit of 64 characters, CHAR(64) may be reasonable. If values are long or require prefix semantics, consider a generated column and suitable data type; functional key parts do not support prefix length declarations like ordinary column indexes.

### 6.2. Functional Index or Generated Column?

| Criterion | Functional Index | Generated Column + Index |
|---|---|---|
| Visible extra column | No; hidden virtual generated column | Yes, named column |
| Querying | Must use matching expression for optimizer recognition | Can query directly by column name |
| Reusability | Expression may need repeating in SQL | Column can be used in SELECT, JOIN, WHERE, and ORDER BY |
| Data type | Must be specified in expression, often needs CAST | Explicit column type declaration |
| Schema maintenance | Fewer extra columns | Easier to read schema and document property meaning |
| Fit | A fixed expression rarely needing exposure as an attribute | A JSON path acting as a business property used in many places |

A functional index is not a way to index arbitrary stored functions. Functional key part expressions face restrictions similar to generated columns: no subqueries, variables, parameters, disallowed stored or loadable functions, and they must obey key type/length limits.

## 7. Conditions for Expressions to Match a Functional Index

The optimizer can only use a functional index when the query expression corresponds to the indexed key part under MySQL's expression-matching and result-type rules.

Example index:

~~~sql
CREATE INDEX idx_product_price_expr
ON product (
    (
        CAST(
            attributes->>'$.price'
            AS DECIMAL(12, 2)
        )
    )
);
~~~

Query expression:

~~~sql
SELECT product_id
FROM product
WHERE CAST(
    attributes->>'$.price'
    AS DECIMAL(12, 2)
) >= 100.00;
~~~

If the query is written as:

~~~sql
WHERE CAST(attributes->>'$.price' AS CHAR(30)) >= '100'
~~~

the data type and semantics differ; the functional index on DECIMAL is not a matching access path.

Changes that can prevent the optimizer from recognizing the expression:
- Changing the JSON path.
- Changing CAST type or precision/scale.
- Changing collation.
- Changing string normalization.
- Wrapping in different functions.
- Changing expression order or form in a way the optimizer does not treat as equivalent.

When an expression represents shared logic, a named generated column is usually easier to maintain. A query like `WHERE price >= 100` avoids repeating long expressions and reduces the risk of syntax drift.

## 8. Indexing Nested JSON Paths

JSON paths can point to nested attributes:

~~~json
{
  "warehouse": {
    "city": "Da Nang",
    "code": "DN-01"
  }
}
~~~

Extracting `city`:

~~~sql
ALTER TABLE product
    ADD COLUMN warehouse_city VARCHAR(80)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_ai_ci
        GENERATED ALWAYS AS (
            JSON_UNQUOTE(
                JSON_EXTRACT(attributes, '$.warehouse.city')
            )
        ) VIRTUAL,
    ADD INDEX idx_product_warehouse_city (warehouse_city);
~~~

Query:

~~~sql
SELECT product_id, product_name
FROM product
WHERE warehouse_city = 'Da Nang';
~~~

The JSON path in a generated expression is constant. If an application needs to search across arbitrary dynamic paths, a single index for one fixed path cannot automatically serve every path.

### 8.1. Indexing Multiple Paths

If queries frequently use `brand`, `price`, and `warehouse.city`, you can create multiple generated columns/indexes:

~~~sql
ALTER TABLE product
    ADD COLUMN brand VARCHAR(64)
        GENERATED ALWAYS AS (
            JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.brand'))
        ) VIRTUAL,
    ADD COLUMN price DECIMAL(12, 2)
        GENERATED ALWAYS AS (
            CAST(
                JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.price'))
                AS DECIMAL(12, 2)
            )
        ) VIRTUAL,
    ADD COLUMN warehouse_city VARCHAR(80)
        GENERATED ALWAYS AS (
            JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.warehouse.city'))
        ) VIRTUAL,
    ADD INDEX idx_product_brand (brand),
    ADD INDEX idx_product_price (price),
    ADD INDEX idx_product_city (warehouse_city);
~~~

Do not index every path merely because it exists in JSON. Every index increases storage size and INSERT/UPDATE/DELETE cost. Index only paths with frequent queries and measurable benefit.

### 8.2. Composite Indexes on Generated Columns

If queries always filter by `brand` and `price`:

~~~sql
SELECT product_id, product_name
FROM product
WHERE brand = 'Northwind'
  AND price >= 100.00
  AND price < 200.00;
~~~

You can evaluate a composite index:

~~~sql
CREATE INDEX idx_product_brand_price
ON product (brand, price);
~~~

A composite index ordered with equality first and range second can seek `brand` and then scan the `price` range. The leftmost prefix rule still applies just like on ordinary columns.

If a query filters solely on `price` without `brand`, the `(brand, price)` index lacks a matching leftmost prefix to seek directly by `price`. A separate index may be needed if the workload truly requires it.

## 9. Multi-Valued Indexes for JSON Arrays

Scalar generated columns and functional indexes generally fit when each row has one value for a path. However, JSON arrays hold multiple elements:

~~~json
{
  "tags": ["sale", "outdoor", "featured"]
}
~~~

If you need to find products having tag `sale`, a standard scalar index over the whole JSON document does not directly solve membership queries.

InnoDB has supported multi-valued indexes since MySQL 8.0.17. A single row can produce multiple index entries corresponding to the elements in a JSON array.

Example:

~~~sql
CREATE INDEX idx_product_tags
ON product (
    (
        CAST(attributes->'$.tags' AS CHAR(32) ARRAY)
    )
);
~~~

The `CAST ... AS ... ARRAY` expression marks the key part as multi-valued. This example assumes `tags` is a JSON array containing strings of suitable length.

Membership query:

~~~sql
SELECT product_id, product_name
FROM product
WHERE 'sale' MEMBER OF (attributes->'$.tags');
~~~

The optimizer can use the multi-valued index to find rows containing matching elements. Syntax and optimization capabilities depend on the MySQL version; verify with EXPLAIN on the actual server.

### 9.1. JSON_CONTAINS and JSON_OVERLAPS

Predicates checking elements/arrays can also leverage multi-valued indexes in forms supported by MySQL.

Find a single element:

~~~sql
SELECT product_id
FROM product
WHERE JSON_CONTAINS(
    attributes->'$.tags',
    JSON_QUOTE('sale')
);
~~~

Find rows sharing at least one element:

~~~sql
SELECT product_id
FROM product
WHERE JSON_OVERLAPS(
    attributes->'$.tags',
    JSON_ARRAY('sale', 'featured')
);
~~~

JSON_CONTAINS checks whether `candidate` is contained in `target` under JSON containment rules. JSON_OVERLAPS checks whether two documents share at least one value. Do not substitute the two functions for each other mechanically.

### 9.2. Element Types Must Match

If `tags` is a numeric array:

~~~json
{
  "tag_ids": [10, 20, 30]
}
~~~

You can index it as `UNSIGNED ARRAY`:

~~~sql
CREATE INDEX idx_product_tag_ids
ON product (
    (
        CAST(attributes->'$.tag_ids' AS UNSIGNED ARRAY)
    )
);
~~~

The predicate must use properly typed numeric literals:

~~~sql
SELECT product_id
FROM product
WHERE 20 MEMBER OF (attributes->'$.tag_ids');
~~~

Do not mix string `"20"` and number `20` in the same array if the application requires consistent semantics. The CAST type, literal type, and JSON array element type must be designed consistently.

### 9.3. A Multi-Valued Index Is Not a Normal Covering Index

Because one row can generate many index entries, multi-valued indexes have different limitations than standard B-tree secondary indexes. They primarily help locate rows by membership. Do not assume they can serve all SELECT columns without accessing base rows, or provide ORDER BY ordering.

If a query must return multiple attributes and sort by another column, EXPLAIN may show extra row lookups or filesort.

## 10. Limitations of Multi-Valued Indexes

Limitations to keep in mind during design:
- Supported only on InnoDB.
- Requires MySQL 8.0.17 or later.
- Only one multi-valued key part per index.
- Arrays must be CAST to an appropriate scalar type.
- Not a covering index / index-only scan.
- Cannot support ordinary range scans or sort order like a scalar B-tree.
- Cannot serve as a foreign key.
- Does not turn a JSON array into a relation with per-element constraints/uniqueness.
- Must test JSON types, NULL values, and empty arrays on the target version.

For arrays containing complex objects, many-to-many relationships, or per-element attributes, a normalized child table is usually better suited:

~~~sql
CREATE TABLE product_tag (
    product_id BIGINT UNSIGNED NOT NULL,
    tag VARCHAR(32) NOT NULL,
    PRIMARY KEY (product_id, tag),
    KEY idx_product_tag_tag_product (tag, product_id),
    CONSTRAINT fk_product_tag_product
        FOREIGN KEY (product_id)
        REFERENCES product(product_id)
) ENGINE = InnoDB;
~~~

The relational model supports foreign keys, unique constraints, JOINs, and flexible aggregate queries. A multi-valued index is an option to optimize membership queries on JSON arrays, not a reason to shove every many-to-many relationship into JSON.

## 11. JSON Paths and Data Types: Critical Choices

| Data in JSON | Generated Column / Index Type to Consider | Notes |
|---|---|---|
| Code/name | VARCHAR with explicit charset/collation | Choose appropriate length and consistent collation |
| Price | DECIMAL(p,s) | Avoid comparing numbers as strings |
| Quantity/ID | INT/BIGINT UNSIGNED if range fits | Validate negative values and overflow |
| Boolean | TINYINT or explicit representation | Distinguish false, missing, and JSON null |
| Date | DATE/DATETIME | Verify format and timezone |
| String tag list | Multi-valued CHAR ARRAY | Check length and collation |
| Numeric ID list | Multi-valued UNSIGNED ARRAY | Use numeric literals and JSON numbers consistently |

### 11.1. Strings and Collation

When extracting JSON strings, decide whether comparisons are case- and accent-sensitive. For example:
- `utf8mb4_0900_ai_ci`: accent-insensitive, case-insensitive.
- `utf8mb4_0900_as_cs`: accent-sensitive, case-sensitive.
- Other collations may have different rules.

Declaring explicit collation on a generated column clarifies index and predicate semantics. If the application requires case-sensitive identifiers, do not inadvertently use a case-insensitive collation.

### 11.2. Numeric Conversion

Do not index prices as VARCHAR if queries perform numeric comparisons:

~~~sql
-- String comparison can differ from numeric order:
WHERE price_text >= '100'
~~~

Use DECIMAL:

~~~sql
WHERE price >= 100.00
~~~

Choose precision/scale covering the value domain. CAST may round or emit warnings on invalid input; validate documents at write time.

### 11.3. Dates and Timezones

JSON can store dates as ISO strings. If filtering by date is needed, extract into DATE or DATETIME using supported expressions and standard formats. If values carry timezones, standardize storage (typically UTC) before CASTing. Do not rely on implicit conversion of arbitrarily formatted strings.

## 12. Indexing JSON with Generated Columns and Leftmost Prefix

A generated column is an SQL column, so all standard indexing rules still apply.

Example:

~~~sql
ALTER TABLE product
    ADD COLUMN brand VARCHAR(64)
        GENERATED ALWAYS AS (
            JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.brand'))
        ) VIRTUAL,
    ADD COLUMN price DECIMAL(12, 2)
        GENERATED ALWAYS AS (
            CAST(
                JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.price'))
                AS DECIMAL(12, 2)
            )
        ) VIRTUAL,
    ADD INDEX idx_product_brand_price (brand, price);
~~~

Index `(brand, price)`:
- Supports filtering on `brand`.
- Supports filtering on `brand` and `price`.
- Can support a range on `price` after an equality on `brand`.
- Does not have a leftmost prefix for `price` alone.

If queries filter solely by `price`, evaluate a separate `(price)` index. Do not add indexes before inspecting the workload.

## 13. Covering Indexes and JSON Queries

Example:

~~~sql
SELECT product_id, brand, price
FROM product
WHERE brand = 'Northwind'
  AND price >= 100.00;
~~~

In InnoDB, secondary index `(brand, price)` contains the row's primary key. Because `product_id` is the PRIMARY KEY and `brand`/`price` are in the index, the plan can be covering for this query. EXPLAIN may show `Using index`.

However, if SELECT adds `product_name`, which is not in the index:

~~~sql
SELECT product_id, product_name, brand, price
FROM product
WHERE brand = 'Northwind';
~~~

MySQL may have to access the clustered row to retrieve `product_name`. Do not widen an index with every column just to avoid one lookup if doing so makes the index overly wide and increases write overhead.

Functional indexes can also serve access paths, though covering behavior and EXPLAIN display depend on the expression and version. Named generated columns are usually easier to read when extracted values must be returned across many queries.

## 14. Verifying Whether the Optimizer Uses the Index

After creating a generated column or functional index, do not stop at DDL success. Inspect the execution plan.

### 14.1. EXPLAIN

~~~sql
EXPLAIN
SELECT product_id, product_name
FROM product
WHERE brand = 'Northwind';
~~~

Fields to check:
- `type`: access type, e.g., ref/range vs. ALL.
- `possible_keys`: indexes eligible for consideration.
- `key`: chosen index.
- `key_len`: length of the key part used.
- `rows`: estimated rows.
- `filtered`: estimated percentage of remaining rows.
- `Extra`: Using index, Using where, Using filesort, and other notes.

An index appearing in `possible_keys` but not in `key` means the optimizer did not choose that index for the current plan. This is not necessarily a bug; a full scan may be cheaper if the table is small or the predicate matches many rows.

### 14.2. EXPLAIN FORMAT=TREE

~~~sql
EXPLAIN FORMAT=TREE
SELECT product_id
FROM product
WHERE price >= 100.00
  AND price < 200.00;
~~~

TREE shows iterators and execution order. Use it to verify whether a range scan occurs on the `price` index.

### 14.3. EXPLAIN ANALYZE

~~~sql
EXPLAIN ANALYZE
SELECT product_id
FROM product
WHERE brand = 'Northwind'
  AND price >= 100.00;
~~~

EXPLAIN ANALYZE executes the SELECT statement and reports actual row counts and timing. Compare estimated rows with actual rows to see if statistics reflect data distribution.

Run only in an appropriate environment if the query is heavy. EXPLAIN ANALYZE is not a read-only plan command; it executes the query.

### 14.4. ANALYZE TABLE

After loading large amounts of data or significantly changing JSON distribution:

~~~sql
ANALYZE TABLE product;
~~~

This command updates optimizer statistics. Re-run EXPLAIN afterward to check estimates and index choice. ANALYZE TABLE does not guarantee the optimizer will pick the new index; it only updates information used for cost estimation.

## 15. Generated Columns and Functional Indexes May Not Be Used When Predicates Do Not Match

Suppose generated column `brand` is defined as:

~~~sql
brand VARCHAR(64)
GENERATED ALWAYS AS (
    JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.brand'))
) VIRTUAL
~~~

The clearest query:

~~~sql
WHERE brand = 'Northwind'
~~~

The optimizer may also recognize the equivalent expression in some cases, but the safest and most maintainable approach is querying the generated column directly.

If a query uses a different path:

~~~sql
WHERE JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.manufacturer')) = 'Northwind'
~~~

that is a different attribute; the `brand` index cannot substitute.

If a query wraps the column in a function:

~~~sql
WHERE LOWER(brand) = 'northwind'
~~~

a regular `brand` index may not directly serve the `LOWER(brand)` expression, unless there is an appropriate functional index or another normalized design. Check EXPLAIN instead of guessing.

## 16. Heterogeneous JSON Data and Validation Strategy

An index on a JSON path assumes data at that path conforms to the expected value domain. If some rows store:

~~~json
{"price": 129.90}
~~~

while other rows store:

~~~json
{"price": "unknown"}
~~~

CASTing to DECIMAL can emit warnings or produce unexpected conversions. This makes query semantics hard to control.

Countermeasures:
- Validate JSON in the application layer before writing.
- Use JSON Schema validation if version and requirements fit.
- Use CHECK constraints to enforce simple rules where possible.
- Explicitly define the JSON type for each path.
- Define handling rules for missing and JSON null values.
- Audit existing data before adding generated columns/indexes.
- Monitor warnings and errors during migrations.

Example type check:

~~~sql
SELECT product_id
FROM product
WHERE JSON_TYPE(JSON_EXTRACT(attributes, '$.price')) NOT IN ('INTEGER', 'DOUBLE', 'DECIMAL');
~~~

This predicate is an example data audit; add handling for missing paths/NULL according to your data rules. Do not assume every numeric JSON value has the exact same JSON_TYPE across all document-creation methods.

## 17. Write and Operational Overhead

Every additional generated column/index carries a cost.

### 17.1. INSERT

When inserting a product, MySQL must:
- Write the JSON document.
- Evaluate generated expressions.
- Write entries into secondary indexes.
- For multi-valued indexes, write an entry for each array element.

A document with a 50-element array can produce far more index entries than one with a 2-element array.

### 17.2. UPDATE

When updating `attributes`:
- Affected generated expressions may need re-evaluation.
- Corresponding indexes must be maintained if key values change.
- Multi-valued indexes may need to update many entries when an array changes.

Do not assume changing a single JSON attribute is always cheap; measure according to document size and index count.

### 17.3. Storage Footprint

STORED generated columns increase row size. Secondary indexes increase index size. Functional indexes also store key entries even without a visible auxiliary column. Multi-valued indexes can grow substantially with the total number of elements across arrays.

Monitor:
- DATA_LENGTH and INDEX_LENGTH.
- Table size before/after.
- INSERT/UPDATE latency.
- Buffer pool pressure.
- Index build duration and lock/DDL impact.

## 18. When Should a Child Table Be Used Instead of a JSON Array?

Multi-valued indexes are convenient for simple membership, but a JSON array is not a full many-to-many relationship.

Use a child table when:
- Each element needs its own ID.
- Foreign keys are needed.
- Unique constraints on the product/tag pair are needed.
- Attributes on each link are needed.
- Frequent JOINs, aggregations, or per-element updates are needed.
- Independent permissions or element lifecycles must be managed.

The `product_tag` example in section 10 can support a `(tag, product_id)` index, foreign key, and unique key. If you only need to store a rarely changing list of labels with simple membership queries, a multi-valued index can be a leaner option.

Base the decision on data and query requirements, not merely element counts.

## 19. Versions and Feature Support

| Feature | MySQL Version |
|---|---|
| Generated columns | MySQL 5.7 and later |
| Functional key parts | MySQL 8.0.13 and later |
| Multi-valued indexes | MySQL 8.0.17 and later |
| JSON_OVERLAPS | MySQL 8.0.17 and later |
| EXPLAIN ANALYZE | MySQL 8.0.18 and later |

MySQL 8.0 and 8.4 releases have minor version-specific differences in syntax, optimizer behavior, and limits. For MariaDB or MySQL-compatible services, do not infer equivalent features solely from similar syntax.

Runtime check:

~~~sql
SELECT VERSION();
~~~

Before deploying functional indexes or multi-valued indexes, consult documentation for the exact server version and test DDL on staging.

## 20. Workflow for Choosing a JSON Indexing Technique

1. Collect real queries and identify JSON paths used in WHERE/JOIN/ORDER BY.
2. Determine whether each path is scalar or an array.
3. Determine the data type and value domain of the JSON path.
4. Define semantics for missing paths, JSON null, and SQL NULL.
5. If a scalar path is stable and used in many places, create a generated column with an explicit SQL type.
6. If the expression is fixed and no auxiliary column is needed, consider a functional index (MySQL 8.0.13+).
7. If the path is a scalar array with membership queries, consider a multi-valued index (MySQL 8.0.17+).
8. If an array needs foreign keys, unique constraints, or per-element attributes, use a relational child table.
9. Choose charset/collation for strings and precision/scale for numbers.
10. Audit existing data before adding CASTs/indexes.
11. Create the index on staging and inspect EXPLAIN.
12. Use EXPLAIN ANALYZE to compare estimated rows with actual rows.
13. Evaluate ORDER BY, covering, ranges, and leftmost prefix.
14. Measure INSERT/UPDATE overhead and index storage footprint.
15. Deploy to production only with a DDL plan, backups, and monitoring.
16. Continue monitoring plans as JSON data distribution evolves.

## 21. Common Mistakes

| Mistake or Misconception | Cause | Fix |
|---|---|---|
| A JSON column auto-indexes all paths | The JSON type only guarantees valid JSON storage | Create a generated column, functional index, or multi-valued index |
| Indexing JSON_EXTRACT returning raw JSON | JSON type is not a standard scalar key | CAST/unquote to an appropriate SQL type |
| Using VARCHAR for prices | String comparison instead of numeric | Use DECIMAL |
| VIRTUAL generated columns cannot be indexed | Confusing VIRTUAL with lack of index storage | InnoDB supports secondary indexes on virtual generated columns |
| STORED is always faster than VIRTUAL | Ignoring storage footprint and write cost | Choose based on read/write workload |
| Functional indexes accept any expression | Functional key parts share generated column limits | Check expression restrictions |
| Functional indexes do not need CAST on JSON strings | Expression may yield an unindexable long string type | CAST to CHAR with explicit length and collation |
| Different query expressions still use the functional index | Optimizer must match expression and result type | Use the matching expression or a named generated column |
| One scalar index serves a JSON array | Arrays contain multiple elements | Use a multi-valued index or child table |
| Multi-valued indexes can be used for ORDER BY | They serve membership, not business sort order | Use a suitable scalar index for sorting |
| MVI replaces many-to-many tables | Lacks full FKs/constraints and per-element relations | Normalize into a join table when needed |
| Creating an index means the optimizer will use it | Cost model may choose a full scan or another access path | Check EXPLAIN/EXPLAIN ANALYZE |
| JSON null is the same as missing path | The two cases have different semantics | Check JSON_CONTAINS_PATH and JSON_TYPE |
| Adding many indexes does not affect writes | Every index must be maintained | Measure INSERT/UPDATE, storage, and cache impact |
| Functional indexes exist in all MySQL 8.0 releases | Requires at least 8.0.13 | Check VERSION() |
| Multi-valued indexes exist since MySQL 8.0.13 | Requires at least 8.0.17 | Check VERSION() and storage engine |

## 22. Practice Exercises

### Exercise 1: Generated Column for Brand

Create a `product` table with JSON `attributes`. Add a VARCHAR `brand` generated column and index. Insert at least 100,000 products, run queries filtering by `brand`, and compare EXPLAIN before and after indexing.

### Exercise 2: Generated Column for Price

Extract `price` as DECIMAL(12,2), create an index, and run range queries. Test `price` data as number, numeric string, invalid string, and missing path. Record warnings/errors and decide on validation.

### Exercise 3: VIRTUAL vs. STORED

Create two tables with identical JSON documents, one using a VIRTUAL generated column and one using STORED. Measure storage footprint, read time, and write time on a representative workload. Index both to compare.

### Exercise 4: Functional Index for a JSON Path

On MySQL 8.0.13+, create a functional index for `brand` with explicit CAST and collation. Write a query using the exact expression. Then alter CAST/collation/path and observe EXPLAIN.

### Exercise 5: Composite Index on Generated Columns

Create `brand` and `price` generated columns and create index `(brand, price)`. Compare brand-only, brand + price range, and price-only queries. Explain leftmost prefix.

### Exercise 6: Nested JSON Path

Extract `warehouse.city` into a generated column. Create an index and query by `city`. Test documents missing `warehouse`, missing `city`, and having `city` as JSON null.

### Exercise 7: Multi-Valued Index for Tags

On MySQL 8.0.17+, create an MVI on `CAST(attributes->'$.tags' AS CHAR(32) ARRAY)`. Run MEMBER OF, JSON_CONTAINS, and JSON_OVERLAPS. Use EXPLAIN to verify the access path.

### Exercise 8: Multi-Valued Index for Numbers

Create a `tag_ids` array of JSON numbers. Create an MVI with `UNSIGNED ARRAY` and query membership with numeric literals. Test data containing strings instead of numbers and evaluate consistency.

### Exercise 9: Comparing MVI with a Join Table

Create `product_tag` with primary/foreign keys and a `(tag, product_id)` index. Compare membership queries, list updates, constraints, and write overhead against MVI.

### Exercise 10: Index Cost

Measure INSERT/UPDATE on a JSON-only table, a table with generated columns/indexes, and a table with MVI. Compare storage size, write latency, and query latency.

### Exercise 11: Reading Execution Plans

Run EXPLAIN FORMAT=TREE and EXPLAIN ANALYZE for each index type. Record key, estimated rows, actual rows, loops, filesort, and returned row count.

### Exercise 12: Production Design

Pick three JSON paths from a real workload. Propose a generated column, functional index, MVI, or child table for each path. Explain data types, collation, version, queries, write overhead, and migration plan.

## 23. Pre-Deployment Checklist

- [ ] Identified frequently queried JSON paths.
- [ ] Distinguished scalar paths from JSON arrays.
- [ ] Selected generated column, functional index, or multi-valued index matching the problem.
- [ ] Defined SQL data types and value domains for each path.
- [ ] Checked missing paths, JSON null, SQL NULL, and mistyped values.
- [ ] Chosen charset/collation for strings.
- [ ] Chosen DECIMAL/integer instead of string for numeric values.
- [ ] Aware that VIRTUAL is the default and STORED persists values in the row.
- [ ] Understand that indexes on VIRTUAL generated columns still store entries in the secondary index.
- [ ] Verified functional index expressions match query predicates.
- [ ] Checked functional key part limits and bounded-length CASTs.
- [ ] Verified version support for functional indexes.
- [ ] Verified version and InnoDB support for multi-valued indexes.
- [ ] Verified arrays contain properly typed scalars.
- [ ] Understand that MVI is not a covering index and does not replace foreign keys.
- [ ] Considered a relational child table when complex constraints/JOINs are needed.
- [ ] Checked leftmost prefix if creating composite indexes on generated columns.
- [ ] Ran EXPLAIN and EXPLAIN ANALYZE on representative data.
- [ ] Measured INSERT/UPDATE overhead and storage footprint.
- [ ] Verified DDL, backup, and post-deployment monitoring plans.

## 24. Conclusion

MySQL does not automatically build B-trees for every path inside a JSON document. For a stable scalar path, a generated column with an explicit SQL type followed by an index is usually readable and maintainable. Functional indexes (MySQL 8.0.13+) allow indexing a fixed expression without a visible auxiliary column, though queries must use the matching expression and result type. For JSON arrays holding scalars, InnoDB multi-valued indexes (MySQL 8.0.17+) can accelerate MEMBER OF, JSON_CONTAINS, or JSON_OVERLAPS in supported cases.

Choose data types and collations before creating indexes; distinguish missing paths, JSON null, and SQL NULL; validate data so CAST does not produce unexpected results. Generated columns and indexes still incur write and storage costs. Multi-valued indexes assist membership lookups but do not replace relational tables when foreign keys, unique constraints, or per-element management are required. Finally, verify with EXPLAIN and EXPLAIN ANALYZE on real data rather than relying solely on index DDL succeeding.

## Official References

- [MySQL 8.4 Reference Manual – JSON Data Type](https://dev.mysql.com/doc/refman/8.4/en/json.html)
- [MySQL 8.4 Reference Manual – JSON Search Functions](https://dev.mysql.com/doc/refman/8.4/en/json-search-functions.html)
- [MySQL 8.4 Reference Manual – Generated Columns](https://dev.mysql.com/doc/refman/8.4/en/create-table-generated-columns.html)
- [MySQL 8.4 Reference Manual – Secondary Indexes and Generated Columns](https://dev.mysql.com/doc/refman/8.4/en/create-table-secondary-indexes.html)
- [MySQL 8.4 Reference Manual – Functional Key Parts](https://dev.mysql.com/doc/refman/8.4/en/create-index.html)
- [MySQL 8.4 Reference Manual – Multi-Valued Indexes](https://dev.mysql.com/doc/refman/8.4/en/create-index.html#create-index-multi-valued)
- [MySQL 8.4 Reference Manual – JSON Table Functions and Operators](https://dev.mysql.com/doc/refman/8.4/en/json-search-functions.html)
- [MySQL 8.4 Reference Manual – EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/explain.html)
- [MySQL 8.4 Reference Manual – ANALYZE TABLE](https://dev.mysql.com/doc/refman/8.4/en/analyze-table.html)
- [MySQL 8.4 Reference Manual – InnoDB Index Types](https://dev.mysql.com/doc/refman/8.4/en/innodb-index-types.html)
