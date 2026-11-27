# VIRTUAL and STORED Generated Columns and Expression Limitations

A generated column is a column whose value is computed by MySQL from an expression based on other columns in the same row. Instead of requiring applications to compute and write the same value in multiple places, you declare the expression directly in the table definition. MySQL automatically recalculates the value whenever source data changes and exposes the column as queryable.

MySQL supports two ways of storing generated columns: `VIRTUAL` and `STORED`. A `VIRTUAL` column is computed on read, whereas a `STORED` column is computed on write and stored alongside row data. Both can be indexed where supported by the storage engine. Therefore, the decision is not just "store or not", but involves CPU, disk space, indexing, read/write frequency, and expression restrictions.

This lesson belongs to the `DATABASE_MYSQL` module, focusing on table design, constraints, data types, SQL queries, indexes, transactions, query optimization, and relational database operations. Generated columns are particularly useful when expressing stable derived values, standardizing repeated query expressions, or indexing attributes extracted from JSON.

After this lesson, you will be able to:

- Explain generated columns and the differences between `VIRTUAL` and `STORED`.
- Declare generated columns in `CREATE TABLE` and `ALTER TABLE`.
- Understand when MySQL evaluates values and how indexing affects them.
- Use generated columns to index expressions or JSON properties.
- Recognize permitted expressions and critical limitations.
- Inspect the definition, generation expression, and indexes of a generated column.
- Choose VIRTUAL vs. STORED based on workload and plan safe schema changes.

## 1. What Is a Generated Column?

A generated column is a column whose value is determined by an expression declared in the schema. The expression typically references other columns in the same row. MySQL automatically maintains the derived value when rows are inserted or updated.

For example, an order line table with unit price, quantity, and line total:

```sql
CREATE TABLE order_lines (
    order_line_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    unit_price DECIMAL(12, 2) NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    line_total DECIMAL(22, 2)
        GENERATED ALWAYS AS (unit_price * quantity) STORED,
    PRIMARY KEY (order_line_id)
) ENGINE = InnoDB;

INSERT INTO order_lines (unit_price, quantity)
VALUES (125.50, 3);

SELECT unit_price, quantity, line_total
FROM order_lines;
```

`line_total` is computed by MySQL from `unit_price * quantity`. When the application updates `quantity` or `unit_price`, MySQL automatically recomputes the generated column. The application does not need to send `line_total` itself.

A generated column differs from a normal column maintained by the application. If an application stores `unit_price`, `quantity`, and `line_total` as three independent columns, application code must keep them consistent everywhere. A generated column moves the calculation rule into the schema so MySQL enforces consistency across all write statements.

## 2. Declaration Syntax

General syntax inside a column definition:

```sql
column_name data_type
    [GENERATED ALWAYS] AS (expression)
    [VIRTUAL | STORED]
    [NOT NULL | NULL]
    [UNIQUE [KEY] | [PRIMARY] KEY]
    [COMMENT 'description']
```

Where:

- `GENERATED ALWAYS` can be written explicitly; the keywords are optional in MySQL syntax.
- `AS (expression)` declares the expression producing the value.
- `VIRTUAL` specifies a virtual column computed on read; this is the default if neither `VIRTUAL` nor `STORED` is written.
- `STORED` instructs MySQL to compute the value on write and store it in the row.
- The declared data type determines how the expression result is represented.

Example using the default `VIRTUAL`:

```sql
CREATE TABLE products (
    product_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    price DECIMAL(12, 2) NOT NULL,
    tax_rate DECIMAL(5, 4) NOT NULL,
    price_with_tax DECIMAL(14, 2)
        AS (price * (1 + tax_rate)),
    PRIMARY KEY (product_id)
) ENGINE = InnoDB;
```

`price_with_tax` is `VIRTUAL` because `STORED` is omitted. To store the result inside the row, append the `STORED` keyword after the expression.

When choosing a data type, ensure it can accommodate the expression's output. MySQL converts the expression result to the declared type; if the result overflows, rounds, or truncates, the data may no longer match expectations. Use explicit `CAST()` when you need control over type and scale, and inspect SQL mode and warnings/errors during writes.

## 3. How Do VIRTUAL and STORED Differ?

| Criterion | `VIRTUAL` | `STORED` |
| --- | --- | --- |
| Evaluation time | When the value is read or needed for an operation | When the row is inserted or updated |
| Stored in row data | No | Yes |
| Read cost | May have to evaluate the expression on read | Reads the already computed and stored value |
| Write cost | Evaluated when needed to maintain values/indexes | Evaluated and written when the row changes |
| Row storage size | Takes no space inside the row | Consumes storage according to column type |
| Indexing | Supports secondary indexes if engine allows | Supports indexes if engine allows |
| Source data changes | Value computed from new data on read | MySQL updates stored value when row changes |

### 3.1. VIRTUAL

With `VIRTUAL`, MySQL does not store the generated column's value in the row's data area. When a query requests the value, MySQL evaluates the expression from source columns. This saves table space and avoids storing duplicate data derivable from other columns.

VIRTUAL fits well when:

- The expression is simple with low evaluation cost.
- The column is read infrequently or only in specific queries.
- You do not want an extra physical copy of the derived value.
- You want a lean schema while keeping clear column names and types.

Do not assume VIRTUAL is always faster. If queries scan many rows and repeatedly evaluate a complex expression, CPU overhead can become significant.

### 3.2. STORED

With `STORED`, MySQL evaluates the expression when a row is inserted or updated and stores the result inside the row. On read, MySQL retrieves the stored value instead of recomputing the expression from scratch.

STORED fits well when:

- The expression is expensive to compute and the column is read frequently.
- Read workload is much heavier than write workload.
- You want to physically materialize the derived value to reduce read-time CPU.
- You need a generated column that satisfies storage requirements of another feature that restricts VIRTUAL columns.

In return, STORED increases row size and write overhead. Whenever source columns change, MySQL must recompute and write the generated column value.

### 3.3. An Index on VIRTUAL Does Not Mean Zero Storage

InnoDB supports secondary indexes on `VIRTUAL` generated columns. When an index is created, the indexed values are stored inside the index structure and updated whenever source data changes. Thus, VIRTUAL takes no space in the clustered row itself, yet an index on it still consumes disk space and increases write overhead.

This is a key optimization insight: if the goal is fast filtering on an expression, you can use an indexed VIRTUAL generated column without necessarily switching to STORED. Measure read/write workload and index footprint before deciding.

## 4. Creating Indexes on Generated Columns

Generated columns can be indexed so queries can filter on derived values without scanning and evaluating the expression for every row. InnoDB supports secondary indexes on generated columns, including VIRTUAL ones.

Example normalizing emails to lowercase for lookup:

```sql
CREATE TABLE app_users (
    user_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(255) NOT NULL,
    email_normalized VARCHAR(255)
        GENERATED ALWAYS AS (LOWER(email)) VIRTUAL,
    PRIMARY KEY (user_id),
    UNIQUE KEY uk_app_users_email_normalized (email_normalized)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_0900_ai_ci;
```

Query:

```sql
SELECT user_id, email
FROM app_users
WHERE email_normalized = LOWER('User@example.com');
```

An index can accelerate lookups on `email_normalized`. However, email normalization also depends on business rules and collation. `LOWER()` alone does not resolve every email comparison rule; establish a normalization policy across both the application and database.

An index can be added after the table already exists:

```sql
CREATE INDEX idx_products_price_with_tax
ON products (price_with_tax);
```

When evaluating, use `EXPLAIN` to confirm whether the optimizer picks the index in actual queries:

```sql
EXPLAIN
SELECT product_id, price_with_tax
FROM products
WHERE price_with_tax >= 1000.00;
```

An index is only beneficial when query predicates and data distribution cause the optimizer to choose it. Do not index every generated column; every index takes space and adds overhead to `INSERT`, `UPDATE`, and `DELETE`.

## 5. Generated Columns and JSON

An application can store flexible payloads in a JSON column while still needing frequent filtering on a few properties. Generated columns let you extract JSON properties into strongly typed columns and index them.

Example:

```sql
CREATE TABLE event_log (
    event_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    payload JSON NOT NULL,
    event_type VARCHAR(50)
        GENERATED ALWAYS AS (
            JSON_UNQUOTE(JSON_EXTRACT(payload, '$.type'))
        ) STORED,
    event_date DATE
        GENERATED ALWAYS AS (
            CAST(JSON_UNQUOTE(JSON_EXTRACT(payload, '$.eventDate')) AS DATE)
        ) VIRTUAL,
    PRIMARY KEY (event_id),
    KEY idx_event_log_type (event_type),
    KEY idx_event_log_date (event_date)
) ENGINE = InnoDB;
```

Insert sample data:

```sql
INSERT INTO event_log (payload) VALUES
('{"type":"ORDER_CREATED","eventDate":"2026-11-19","orderId":1001}'),
('{"type":"PAYMENT_RECEIVED","eventDate":"2026-11-20","orderId":1001}');
```

Query by extracted properties:

```sql
SELECT event_id, event_type, event_date
FROM event_log
WHERE event_type = 'ORDER_CREATED'
  AND event_date >= '2026-11-19';
```

Important notes:

- Choose data types and lengths suited to all JSON values that may appear.
- Use `JSON_UNQUOTE()` when extracting string scalars to avoid keeping JSON string quotes.
- If a property can be absent or mistyped, define expected `NULL`/cast behavior and validate input data.
- `CAST(... AS DATE)` only works when JSON values adhere to a valid date format. Non-standard data may yield unexpected results or errors depending on context.
- Attributes used heavily for filtering, joining, sorting, or constraints may belong as real relational columns rather than living solely inside JSON.

## 6. Generated Column Expression Limitations

Not every SQL expression is permitted in a generated column. MySQL must be able to recompute the value consistently from row data alone.

### 6.1. Expressions Must Depend Only on Same-Row Data

A generated column can reference other columns in the same table and use operators, literals, and allowed functions. It cannot act as a subquery reading other tables.

Conceptually valid example:

```sql
CREATE TABLE measurements (
    measurement_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    width_mm DECIMAL(10, 2) NOT NULL,
    height_mm DECIMAL(10, 2) NOT NULL,
    area_mm2 DECIMAL(20, 4)
        GENERATED ALWAYS AS (width_mm * height_mm) STORED,
    PRIMARY KEY (measurement_id)
) ENGINE = InnoDB;
```

The expression `width_mm * height_mm` depends strictly on columns in the same row.

### 6.2. No Subqueries or External Table References

You cannot use a subquery to compute a generated column:

```sql
-- Invalid: generated column expressions cannot contain subqueries
CREATE TABLE invalid_example (
    item_id BIGINT NOT NULL,
    category_name VARCHAR(100)
        AS ((SELECT name FROM categories WHERE categories.id = item_id))
);
```

If a value must come from another table, use a `JOIN` in queries, create an appropriate view, or maintain a regular column via controlled business logic or triggers. Do not try to use generated columns as a replacement for joins.

### 6.3. No Variables, Parameters, or Nondeterministic Functions

A generated column expression cannot depend on state outside the row, such as:

- User variables or system variables.
- Stored functions or loadable functions.
- Subqueries or prepared statement parameters.
- Nondeterministic functions that can return different results even when row data is unchanged, such as `NOW()`, `RAND()`, or `UUID()`.

Invalid example:

```sql
-- Invalid: NOW() varies depending on evaluation time
CREATE TABLE invalid_created_at (
    created_at DATETIME NOT NULL,
    age_in_seconds BIGINT AS (TIMESTAMPDIFF(SECOND, created_at, NOW()))
);
```

If you need creation timestamps, store them in a normal column with `DEFAULT CURRENT_TIMESTAMP`. If you need elapsed time relative to the current time when querying, compute it in the `SELECT` query instead of defining a generated column.

### 6.4. Do Not Reference AUTO_INCREMENT Columns

A generated column cannot reference an `AUTO_INCREMENT` column. Auto-increment values are allocated during insert execution, which violates MySQL's expression rules for generated columns.

If you need a code derived from an auto-increment ID, compute it in queries or in the application layer after the ID has been allocated. Do not declare a generated column based on an auto-increment column.

### 6.5. Do Not Assign Values Directly to Generated Columns

During `INSERT` or `UPDATE`, applications cannot set arbitrary values on a generated column. Omit the column from the write list or specify the `DEFAULT` keyword where supported.

```sql
-- Valid: write only source columns
INSERT INTO order_lines (unit_price, quantity)
VALUES (80.00, 2);

-- Invalid: directly assigning a generated column value
UPDATE order_lines
SET line_total = 100.00
WHERE order_line_id = 1;
```

To change a generated column's value, update the source columns referenced in its expression. MySQL recomputes the result automatically.

### 6.6. Dependency Order and Other Generated Columns

A generated column may reference other generated columns when the dependency relationship is valid. Do not create circular references or reference columns defined later in an invalid dependency order. When layering multiple derived values, declare them in clear dependency order or combine expressions if that keeps the schema clearer.

Example:

```sql
CREATE TABLE product_dimensions (
    product_id BIGINT UNSIGNED NOT NULL,
    width_cm DECIMAL(8, 2) NOT NULL,
    height_cm DECIMAL(8, 2) NOT NULL,
    area_cm2 DECIMAL(16, 4)
        AS (width_cm * height_cm) STORED,
    area_m2 DECIMAL(16, 8)
        AS (area_cm2 / 10000) VIRTUAL,
    PRIMARY KEY (product_id)
) ENGINE = InnoDB;
```

When designing multi-layer dependencies, test the DDL on the exact target MySQL version and avoid overly long formula chains that are hard to maintain.

## 7. Data Types and Expression Result Conversion

A generated column's data type is part of the schema; do not let the expression's implicit type dictate it without reviewing the value domain.

Monetary example:

```sql
CREATE TABLE invoice_lines (
    invoice_line_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    unit_price DECIMAL(12, 2) NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    discount_rate DECIMAL(5, 4) NOT NULL DEFAULT 0,
    line_total DECIMAL(22, 2)
        GENERATED ALWAYS AS (
            CAST(unit_price * quantity * (1 - discount_rate) AS DECIMAL(22, 2))
        ) STORED,
    PRIMARY KEY (invoice_line_id),
    CONSTRAINT chk_invoice_discount CHECK (discount_rate >= 0 AND discount_rate <= 1)
) ENGINE = InnoDB;
```

Here, `CAST()` clarifies the desired result scale. However, real-world monetary calculations also require rounding policies, tax logic, discounts, currency rules, and penny-allocation rules. A generated column only executes the declared expression—it does not understand accounting rules on its own.

For strings, specify a length large enough to hold the output. For JSON, decide how to handle missing keys, JSON `null`, wrong scalar types, and malformed values. For division, guard against zero denominators using safe expressions like `NULLIF(denominator, 0)` if `NULL` is an acceptable business outcome.

## 8. Indexes, the Optimizer, and Query Expressions

Generated columns are often used to promote a repeated query expression into the schema and index its output.

For example, an application frequently searches by email domain:

```sql
CREATE TABLE contacts (
    contact_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(255) NOT NULL,
    email_domain VARCHAR(255)
        GENERATED ALWAYS AS (SUBSTRING_INDEX(email, '@', -1)) VIRTUAL,
    PRIMARY KEY (contact_id),
    KEY idx_contacts_email_domain (email_domain)
) ENGINE = InnoDB;

SELECT contact_id, email
FROM contacts
WHERE email_domain = 'example.com';
```

Instead of computing `SUBSTRING_INDEX()` for every row at query time, MySQL can use the index on `email_domain` to locate matching values. Verify with `EXPLAIN` using representative data.

### 8.1. Comparing Generated Columns with Functional Indexes

MySQL 8.0.13 and later support functional key parts, allowing indexes directly on expressions:

```sql
-- If choosing a functional index instead of an index on a generated column,
-- drop the old index first to avoid maintaining two indexes for the same expression.
DROP INDEX idx_contacts_email_domain ON contacts;

CREATE INDEX idx_contacts_email_domain_expr
ON contacts ((SUBSTRING_INDEX(email, '@', -1)));
```

With a functional index, queries should also write the matching expression:

```sql
SELECT contact_id
FROM contacts
WHERE SUBSTRING_INDEX(email, '@', -1) = 'example.com';
```

MySQL implements functional indexes using hidden virtual generated columns under the hood. Use a functional index when you only need to index an expression without exposing a named derived column in the schema. Use an explicit generated column when you want to select, display, validate, or reuse the derived value as a named column.

Do not create both a functional index and a generated column index for the same expression without a clear reason; they duplicate storage and write maintenance overhead.

### 8.2. The Optimizer Can Recognize Matching Expressions

In some cases, the optimizer can use an index on a generated column even when a query writes an expression equivalent to the generated column's expression. Expression matching follows structural and result-type rules; do not assume two expressions that merely "look similar" will always trigger the same index.

Writing queries that reference the generated column name directly is usually clearest and easiest to control:

```sql
SELECT contact_id
FROM contacts
WHERE email_domain = 'example.com';
```

Check `EXPLAIN` or `EXPLAIN ANALYZE` on your actual MySQL version to confirm the access path. `EXPLAIN ANALYZE` executes the query, so only run it when the query's load is acceptable.

## 9. Inspecting Generated Columns in the Schema

### 9.1. SHOW CREATE TABLE

```sql
SHOW CREATE TABLE order_lines\G
```

The output displays data types, `GENERATED ALWAYS AS (...)` expressions, `VIRTUAL` or `STORED` mode, and associated indexes.

### 9.2. INFORMATION_SCHEMA.COLUMNS

```sql
SELECT
    TABLE_NAME,
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    EXTRA,
    GENERATION_EXPRESSION
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND GENERATION_EXPRESSION <> ''
ORDER BY TABLE_NAME, ORDINAL_POSITION;
```

`GENERATION_EXPRESSION` holds the expression used to generate the column. `EXTRA` typically reports `VIRTUAL GENERATED` or `STORED GENERATED`. Use this metadata when writing schema inspection tools or reviewing migrations.

### 9.3. Inspecting Indexes

```sql
SHOW INDEX FROM contacts;
```

Combine this with `EXPLAIN` to check whether queries use the generated column index. An index's mere existence does not guarantee the optimizer will choose it; selectivity, row counts, statistics, and access costs all influence the execution plan.

## 10. Modifying Generated Columns with ALTER TABLE

You can add a generated column to an existing table:

```sql
ALTER TABLE orders
ADD COLUMN order_year SMALLINT
    GENERATED ALWAYS AS (YEAR(placed_at)) VIRTUAL;
```

Then create an index:

```sql
CREATE INDEX idx_orders_order_year
ON orders (order_year);
```

Or change the expression or storage mode by modifying the column definition:

```sql
ALTER TABLE orders
MODIFY COLUMN order_year SMALLINT
    GENERATED ALWAYS AS (YEAR(placed_at)) STORED;
```

Converting between VIRTUAL and STORED (or vice versa) may require rebuilding the table, consuming time, I/O, and temporary disk space. Online/in-place capability depends on engine, version, and change type; do not assume `ALTER TABLE` is always instant or lock-free.

Before deploying a migration:

1. Check row counts, table size, and existing indexes.
2. Test the expression against real data, especially `NULL` values, mistyped values, and boundary values.
3. Estimate the time required to recompute the generated column and build indexes.
4. Budget for temporary disk space, redo/undo logs, and I/O load.
5. Test on a data copy close to production size.
6. Identify the DDL algorithm and lock level supported on the exact MySQL version.
7. Post-migration, verify `SHOW CREATE TABLE`, metadata, indexes, query results, and execution plans.

## 11. Limitations to Remember

| Limitation | Practical Meaning |
| --- | --- |
| No subqueries | Cannot read data from other tables inside a generated column expression |
| No stored or loadable functions | Cannot invoke custom logic outside MySQL's allowed built-in expression set |
| No variables or parameters | Value cannot depend on session state or runtime parameters |
| No nondeterministic functions | Cannot use `NOW()`, `RAND()`, `UUID()`, or values that change with time/context |
| Cannot reference AUTO_INCREMENT | Expression cannot depend on an auto-increment column |
| Cannot assign values directly | INSERT/UPDATE must modify source columns; generated values are computed by MySQL |
| No arbitrary DEFAULT on generated columns | Value is determined by the expression, not an independent default |
| Engine-dependent restrictions | Indexes, foreign keys, and certain features have restrictions per engine and VIRTUAL vs. STORED |
| Result type must match | Expression values may be cast, rounded, or overflow the declared type |

Generated columns are not suitable for every calculation. If an expression needs data from another table, depends on current time, requires complex business logic, or reads external state, use queries, views, application logic, or a dedicated data-maintenance process.

For foreign keys, partitioning, and special indexes, check the specific limitations of your MySQL version and storage engine before designing dependencies on generated columns. Do not assume every feature supported on ordinary columns works identically on VIRTUAL and STORED generated columns.

## 12. Choosing VIRTUAL or STORED Based on Workload

| Scenario | Starting Choice | Reason |
| --- | --- | --- |
| Simple expression, rarely read | VIRTUAL | Avoids storing unnecessary derived values |
| Frequently read expression, high compute cost | STORED | Computed on write, reducing CPU on reads |
| Need an index on a derived value | VIRTUAL or STORED with index | InnoDB supports secondary indexes on virtual generated columns |
| Extracted JSON column used in filter predicates | Indexed VIRTUAL or indexed STORED | Choose based on read/write cost and storage needs |
| Write-heavy table, complex expression | Benchmark both options | STORED increases write cost; VIRTUAL can increase read CPU or index maintenance |
| Value depends on another table or current time | Do not use a generated column | Expression violates same-row deterministic constraints |

Do not choose STORED solely to add an index. If the engine supports indexing VIRTUAL columns and the column does not need to reside in the clustered row, VIRTUAL can meet the requirement. Conversely, if queries frequently read the value across large row sets without a suitable index, STORED can save CPU.

Measure with realistic data:

- Read/write ratio.
- Expression evaluation cost.
- Row and index sizes.
- Number of rows scanned/filtered.
- Query latency and CPU/I/O utilization.
- Rebuild cost when altering the expression.

## 13. Hands-on Exercises

1. Create an `order_lines` table with `line_total` as VIRTUAL, insert data, and inspect computed values.
2. Update `unit_price` and `quantity`; confirm the generated column updates automatically without directly updating it.
3. Create an equivalent table with `line_total` as STORED. Compare `SHOW CREATE TABLE` and `INFORMATION_SCHEMA.COLUMNS` metadata.
4. Create an index on a VIRTUAL generated column. Run `EXPLAIN` for a query filtering on that column and record the selected index.
5. Create an `event_log` table with a JSON payload and a generated column extracting `event_type`. Test inserting JSON with missing keys, JSON null, and wrong value types; record the results.
6. Try creating a generated column using `NOW()` or a subquery in a lab environment and observe the DDL error. Explain why that expression is disallowed.
7. Add a generated column to an existing table via `ALTER TABLE`. Estimate the time, storage, and locking impact on a large table.
8. Create a functional index on an expression and compare it with a named generated column plus index. Choose one approach and justify why.
9. Write a query using `EXPLAIN` or `EXPLAIN ANALYZE` to evaluate the benefit of an index on a generated column using suitably distributed data.

## 14. Design and Deployment Checklist

- [ ] Expression depends only on allowed data within the same row.
- [ ] Expression avoids subqueries, variables, parameters, stored/loadable functions, and nondeterministic functions.
- [ ] Does not reference any `AUTO_INCREMENT` column.
- [ ] Data type and length accommodate all possible expression outputs.
- [ ] Rules for `NULL`, casting, rounding, and charset/collation are defined.
- [ ] VIRTUAL or STORED is chosen based on read/write ratio and compute cost.
- [ ] If indexed, engine support is verified and index maintenance cost is evaluated.
- [ ] Actual queries are verified with `EXPLAIN`.
- [ ] Dependent constraints such as foreign keys or partitioning are verified against version/engine limits.
- [ ] Migration is tested on representative data with a rollback/recovery plan.
- [ ] Post-deployment DDL, metadata, indexes, and query results are verified.

## 15. Completion Criteria

You have completed this lesson when you can create and inspect VIRTUAL/STORED generated columns, explain when values are computed and stored, build indexes on appropriate generated columns, use them to query JSON properties, recognize expression limitations, and choose an approach based on workload. You should also know how to alter generated columns through controlled migrations and verify the results post-deployment.

## References

- [MySQL 8.4 Reference Manual — CREATE TABLE and Generated Columns](https://dev.mysql.com/doc/refman/8.4/en/create-table-generated-columns.html)
- [MySQL 8.4 Reference Manual — Secondary Indexes and Generated Columns](https://dev.mysql.com/doc/refman/8.4/en/create-table-secondary-indexes.html)
- [MySQL 8.4 Reference Manual — CREATE INDEX](https://dev.mysql.com/doc/refman/8.4/en/create-index.html)
- [MySQL 8.4 Reference Manual — JSON Functions](https://dev.mysql.com/doc/refman/8.4/en/json-functions.html)
