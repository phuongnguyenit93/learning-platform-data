# CREATE VIEW and Using Views as a Query Boundary

A view in MySQL is a schema object that stores the definition of a `SELECT` statement and allows applications to query that definition like a logical table. Views help name shared query logic, hide underlying table structure, standardize data filtering, and create a boundary between the application's query interface and the storage model.

A regular view does not pre-store query results. When an application reads a view, MySQL processes the `SELECT` statement defined in the view together with the outer query. Depending on the structure, the optimizer can merge the view into the outer query block or materialize the intermediate result using an internal temporary table. Therefore, a view is an organizational and semantic query boundary; it is not automatically a cache, a physical table, or a guarantee of faster performance.

This lesson focuses on `CREATE VIEW`, designing views as a query boundary, updatability, `WITH CHECK OPTION`, the `MERGE`/`TEMPTABLE` algorithms, `SQL SECURITY` privileges, inspecting metadata, and measuring performance. Temporary tables are only mentioned to distinguish them from views; temporary tables have a different lifecycle and storage behavior.

## 1. What is a View?

A view is a named object in a schema, defined by a `SELECT` statement. Applications can read a view much like reading a table:

```sql
SELECT customer_id, customer_name
FROM v_active_customers
WHERE region_code = 'VN';
```

A view does not necessarily hold its own data. It provides a logical query layer based on one or more tables, other views, and expressions allowed in a `SELECT` definition.

A view is commonly used to:

- Encapsulate repeated filter conditions or JOINs.
- Provide stable column names and result structures for applications.
- Hide certain internal columns or sensitive data.
- Create a simple read interface over a multi-table schema.
- Reuse query logic and reduce duplication across multiple services/reports.
- Control access permissions through `SQL SECURITY DEFINER` or `INVOKER`.

A view does not replace data constraints, transactions, indexes, or schema design. If a query inside a view is incorrect or expensive, every query calling the view can inherit that problem.

## 2. Preparing Example Tables

The examples use customer and order tables:

```sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_name VARCHAR(150) NOT NULL,
    email VARCHAR(255) NOT NULL,
    region_code CHAR(2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customers_email (email),
    KEY idx_customers_region_status (region_code, status)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4;

CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(13, 2) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (order_id),
    KEY idx_orders_customer_status (customer_id, status),
    KEY idx_orders_created (created_at),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers (customer_id)
) ENGINE=InnoDB;
```

Insert a small dataset to test with:

```sql
INSERT INTO customers
    (customer_name, email, region_code, status)
VALUES
    ('An', 'an@example.test', 'VN', 'active'),
    ('Bình', 'binh@example.test', 'VN', 'inactive'),
    ('Chi', 'chi@example.test', 'SG', 'active');

INSERT INTO orders (customer_id, status, total_amount)
VALUES
    (1, 'paid', 120000.00),
    (1, 'pending', 80000.00),
    (3, 'paid', 250000.00);
```

In a real environment, ensure IDs are generated as expected or retrieve generated keys from the driver; the hardcoded IDs in this example are only meant to illustrate the newly created lab data.

## 3. Creating a Basic View

General syntax:

```sql
CREATE
    [OR REPLACE]
    [ALGORITHM = {UNDEFINED | MERGE | TEMPTABLE}]
    [DEFINER = user]
    [SQL SECURITY {DEFINER | INVOKER}]
VIEW view_name [(column_list)]
AS select_statement
[WITH [CASCADED | LOCAL] CHECK OPTION];
```

Example creating a view that only displays active customers:

```sql
CREATE VIEW v_active_customers AS
SELECT
    customer_id,
    customer_name,
    email,
    region_code,
    created_at
FROM customers
WHERE status = 'active';
```

Reading the view:

```sql
SELECT customer_id, customer_name, region_code
FROM v_active_customers
WHERE region_code = 'VN'
ORDER BY customer_name;
```

Applications do not need to repeat the `status = 'active'` condition everywhere. If the filtering logic changes, the view definition can be updated so consumers use the same query boundary.

## 4. Naming View Columns Clearly

A view can declare a column name list after the view name or use aliases in `SELECT`:

```sql
CREATE VIEW v_customer_contact (
    id,
    display_name,
    contact_email,
    region
) AS
SELECT
    customer_id,
    customer_name,
    email,
    region_code
FROM customers;
```

The column list helps the view provide stable interface names that do not depend on internal column names. The number of declared columns must match the number of columns in the `SELECT` result, and names must not be duplicated.

You should list specific columns instead of using `SELECT *`. A view is a contract between the schema and consumers; adding a column to an underlying table should not accidentally change the interface an application relies on.

Aliases also help avoid duplicate column names when a view JOINs multiple tables:

```sql
CREATE VIEW v_order_details AS
SELECT
    o.order_id,
    o.created_at AS order_created_at,
    o.status AS order_status,
    o.total_amount,
    c.customer_id,
    c.customer_name,
    c.region_code
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id;
```

## 5. Views as a Query Boundary

A query boundary is responsible for providing the set of columns, filters, and data relationships that a consumer needs. For example, a reporting application only needs customer information and the total amount of paid orders:

```sql
CREATE VIEW v_customer_paid_totals AS
SELECT
    c.customer_id,
    c.customer_name,
    c.region_code,
    COUNT(o.order_id) AS paid_order_count,
    COALESCE(SUM(o.total_amount), 0.00) AS paid_total
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'paid'
GROUP BY
    c.customer_id,
    c.customer_name,
    c.region_code;
```

Consumers can use:

```sql
SELECT customer_id, customer_name, paid_total
FROM v_customer_paid_totals
WHERE region_code = 'VN'
ORDER BY paid_total DESC;
```

The view saves consumers from needing to know the JOIN, status condition, and aggregation logic. However, because the view contains `GROUP BY` and aggregates, it is not a directly updatable view. The purpose of this view is reading and aggregation.

A good query boundary should have:

- A name that reflects business meaning.
- A minimal and stable column list.
- Clearly defined filtering/JOIN rules.
- Understandable data types and aliases.
- Access permissions restricted by consumer.
- Execution plans verified with real queries.

## 6. Views Are Not Materialized Views or Caches

MySQL does not have native materialized views that automatically store the results of `CREATE VIEW`. A regular view stores a `SELECT` definition; every time it is queried, MySQL processes that definition alongside the outer query.

This means:

- Data changes in underlying tables can appear immediately in the next view read according to transaction isolation/snapshot rules.
- A view has no refresh schedule and does not store an independent result snapshot.
- Separate indexes cannot be created directly on a view like on a regular physical table.
- Performance depends on the underlying tables, indexes, optimizer, and query structure.

If pre-stored aggregated results are needed, you can design a summary table and an update process via batch/events. In that case, the application must manage data freshness, consistency, refreshes, locks, and recovery. Do not call a summary table a regular view.

## 7. ALGORITHM=MERGE and ALGORITHM=TEMPTABLE

MySQL has the following view processing algorithms:

| Algorithm | How It Works | Consequence |
| --- | --- | --- |
| `MERGE` | Merges the view definition into the outer query block | The optimizer can push down conditions and choose access paths on underlying tables |
| `TEMPTABLE` | Materializes the view result into an internal temporary table for execution | May require creating an intermediate result; the view is not updatable |
| `UNDEFINED` | Lets MySQL choose the appropriate processing method | This is the default choice if no algorithm is specified |

Example:

```sql
CREATE ALGORITHM = MERGE VIEW v_active_customers_merge AS
SELECT customer_id, customer_name, region_code
FROM customers
WHERE status = 'active';
```

With `MERGE`, the outer query can be optimized together with the conditions inside the view. This does not mean MySQL merely substitutes SQL text strings; it is a query block transformation process in the optimizer.

Example requesting `TEMPTABLE`:

```sql
CREATE ALGORITHM = TEMPTABLE VIEW v_paid_customer_totals AS
SELECT customer_id, SUM(total_amount) AS paid_total
FROM orders
WHERE status = 'paid'
GROUP BY customer_id;
```

The aggregated result is materialized into an internal temporary table when the view is used. This temporary table serves the execution process, not long-term data storage across statements.

## 8. When Can a View Not Be Merged?

Certain constructs prevent a view from being merged into the outer query block, for example:

- Aggregate functions such as `SUM()`, `COUNT()`.
- `DISTINCT`.
- `GROUP BY` or `HAVING`.
- `LIMIT`.
- `UNION` or `UNION ALL`.
- Window functions.
- Certain subqueries or other expressions incompatible with merging.

When merging is not possible, MySQL may materialize the view or use another processing method depending on the algorithm and version. If `ALGORITHM=MERGE` is declared on an unsupported structure, MySQL may issue a warning and fall back to processing as `UNDEFINED`; read warnings and inspect the execution plan instead of assuming the MERGE request was honored.

Do not write an aggregate view with `MERGE` just hoping to make queries faster. `GROUP BY` and aggregates generally require a separate result boundary; the optimizer must preserve that semantics.

## 9. Outer WHERE Conditions and Predicate Pushdown

With a mergeable view, conditions from the outer query can be combined with conditions inside the view so the optimizer can choose a better access path.

Example:

```sql
SELECT customer_id, customer_name
FROM v_active_customers
WHERE region_code = 'VN'
  AND customer_id >= 1000;
```

Logically, the query needs active customers in VN with IDs from 1000. If the view is mergeable, the optimizer can process these conditions directly against the `customers` table and use an appropriate index.

With a materialized view, outer conditions might not be pushed down across the materialization boundary in the same way; the intermediate result may be built first and then filtered. Exact behavior depends on the structure and version.

Inspect the plan:

```sql
EXPLAIN
SELECT customer_id, customer_name
FROM v_active_customers
WHERE region_code = 'VN'
  AND customer_id >= 1000;
```

Compare with a direct query on `customers`. Do not assume a view always adds overhead or is always free; inspect the plan and actual execution on representative data.

## 10. Updatable vs. Read-Only Views

A view can be updatable if MySQL can determine a sufficiently clear relationship between each view row and a row in an underlying table. Simple views based on a single table are usually updatable:

```sql
CREATE VIEW v_customer_status AS
SELECT customer_id, customer_name, status
FROM customers;
```

You can execute:

```sql
UPDATE v_customer_status
SET status = 'inactive'
WHERE customer_id = 1;
```

This statement updates the underlying `customers` table. The view does not store a separate copy of the row.

Not every view is updatable. Constructs that typically make a view non-updatable include:

- Aggregate functions or window functions.
- `DISTINCT`.
- `GROUP BY` or `HAVING`.
- `UNION`/`UNION ALL`.
- Certain subqueries in the select list or constructs that cannot map to a single underlying table row.
- `ALGORITHM=TEMPTABLE`.

Multi-table JOIN views have their own limitations: an `UPDATE` through a join view can only update one underlying table at a time; `INSERT` capability is also restricted. Check the updatability of a specific view definition rather than inferring it merely from `SELECT` working.

## 11. WITH CHECK OPTION: Keeping Written Rows Inside the View

A view with a filter condition may be updatable, but a write operation through the view might cause a row to no longer satisfy the view's condition. `WITH CHECK OPTION` prevents that.

Create a view containing only active customers:

```sql
CREATE OR REPLACE VIEW v_active_customers AS
SELECT customer_id, customer_name, status, region_code
FROM customers
WHERE status = 'active'
WITH CASCADED CHECK OPTION;
```

The following operation will be rejected because after updating, the row no longer satisfies `status = 'active'`:

```sql
UPDATE v_active_customers
SET status = 'inactive'
WHERE customer_id = 1;
```

`WITH CHECK OPTION` is useful when a view serves as a business boundary, such as consumers only being allowed to modify active rows or rows belonging to a specific region.

It does not replace authorization. Users still need appropriate privileges on the view; the view and underlying tables must have proper privilege configurations.

## 12. LOCAL and CASCADED CHECK OPTION

When a view is built on top of another view, `CHECK OPTION` can have different scopes:

- `LOCAL`: checks the condition of the current view.
- `CASCADED`: checks the conditions of the current view and related underlying views.
- If neither `LOCAL` nor `CASCADED` is specified, the default is `CASCADED`.

Example:

```sql
CREATE VIEW v_vn_customers AS
SELECT customer_id, customer_name, status, region_code
FROM customers
WHERE region_code = 'VN';

CREATE VIEW v_active_vn_customers AS
SELECT customer_id, customer_name, status, region_code
FROM v_vn_customers
WHERE status = 'active'
WITH CASCADED CHECK OPTION;
```

Writing through `v_active_vn_customers` must satisfy both `status = 'active'` and `region_code = 'VN'` in the view chain.

When using `LOCAL`, the outer view checks its own condition; the underlying view's condition is not necessarily enforced by the outer layer's check option. Explicitly design and test view layers if using nested views as write boundaries.

## 13. SQL SECURITY DEFINER and INVOKER

A view can perform privilege checks on underlying tables under the identity of the definer or the caller:

| Mode | Identity Used for Privilege Checks on Underlying Objects | Meaning |
| --- | --- | --- |
| `SQL SECURITY DEFINER` | View definer | Consumers can be granted privileges on the view without needing direct privileges on every underlying table |
| `SQL SECURITY INVOKER` | User invoking the view | Consumers need appropriate privileges on the accessed underlying objects |

If not specified, the default is `DEFINER`.

Example creating a view that runs with the caller's privileges:

```sql
CREATE ALGORITHM = MERGE
SQL SECURITY INVOKER
VIEW v_public_customer_directory AS
SELECT customer_id, customer_name, region_code
FROM customers
WHERE status = 'active';
```

With `INVOKER`, the user querying the view must have the necessary privileges on the underlying tables. With `DEFINER`, MySQL checks underlying privileges against the definer; the definer account must exist and have the necessary privileges.

## 14. Views as an Authorization Layer

A view can expose only the necessary columns, such as excluding emails or internal data from an interface meant for a reporting team:

```sql
CREATE DEFINER = 'report_viewer'@'localhost'
SQL SECURITY DEFINER
VIEW v_customer_public AS
SELECT customer_id, customer_name, region_code
FROM customers
WHERE status = 'active';
```

Then grant read privileges on the view to the appropriate role/user:

```sql
GRANT SELECT ON app_db.v_customer_public
TO 'report_reader'@'%';
```

Consumers are only granted `SELECT` on the view if they do not need direct access to underlying tables. This creates a smaller data surface, but the definer must be managed carefully.

Security principles:

- Use a definer with the minimum privileges needed for the view definition.
- Do not use a high-privilege admin account as the definer if unnecessary.
- Verify that the definer account still exists after migrations or user changes.
- Do not include sensitive columns in a view just because current consumers do not select them yet.
- Check `SELECT`, `SHOW VIEW`, and required privileges when creating/modifying views.
- Verify permissions using the actual application user/role, not just a DBA account.

Views are not an absolute hiding mechanism if users still have direct access to underlying tables or other access paths. Permissions must be designed holistically.

## 15. CREATE OR REPLACE, ALTER VIEW, and DROP VIEW

When you need to change a view definition, you can use `CREATE OR REPLACE VIEW`:

```sql
CREATE OR REPLACE VIEW v_active_customers AS
SELECT customer_id, customer_name, email, region_code
FROM customers
WHERE status = 'active';
```

Or:

```sql
ALTER VIEW v_active_customers AS
SELECT customer_id, customer_name, email, region_code
FROM customers
WHERE status = 'active';
```

Drop a view:

```sql
DROP VIEW IF EXISTS v_active_customers;
```

`CREATE OR REPLACE` replaces an existing view definition; it requires appropriate privileges, usually including privileges to create the view and drop the old object. Do not use it as a way to update underlying tables. Before changing a view used by multiple applications, check consumers and column list compatibility.

Renaming columns, removing columns, or changing result types can break applications even though the view still creates successfully. Treat views as API/schema contracts and manage changes with appropriate versioning or migrations.

## 16. Viewing Definitions and View Metadata

Inspect a view definition:

```sql
SHOW CREATE VIEW v_active_customers\G
```

List views in a schema:

```sql
SHOW FULL TABLES
WHERE Table_type = 'VIEW';
```

Or query metadata:

```sql
SELECT
    TABLE_NAME,
    DEFINER,
    SECURITY_TYPE,
    CHECK_OPTION,
    IS_UPDATABLE,
    VIEW_DEFINITION
FROM INFORMATION_SCHEMA.VIEWS
WHERE TABLE_SCHEMA = DATABASE();
```

`VIEW_DEFINITION` may be restricted or not shown in full depending on privileges. `IS_UPDATABLE` is useful information to check, though appropriate operations should still be tested in a test environment.

If underlying tables change, a view can become invalid or no longer fit consumers. Use `SHOW CREATE VIEW`, check metadata, and re-test queries after schema migrations.

## 17. ORDER BY Inside a View Does Not Guarantee Final Result Order

An `ORDER BY` can be defined inside a view, but consumers should not rely on it as a final ordering contract. If the outer query has its own `ORDER BY`, the outer query's ordering applies; the optimizer may also ignore ordering inside the view when it is not needed to preserve semantics.

Avoid doing this:

```sql
CREATE VIEW v_recent_orders AS
SELECT order_id, customer_id, created_at
FROM orders
ORDER BY created_at DESC;
```

and then assuming every statement:

```sql
SELECT * FROM v_recent_orders;
```

will always return the same order. Put the ordering in the consuming query:

```sql
SELECT order_id, customer_id, created_at
FROM v_recent_orders
ORDER BY created_at DESC, order_id DESC;
```

`ORDER BY` inside a view is just part of the query definition; stable ordering must be requested in the outermost `SELECT`.

## 18. Views Do Not Accept Parameters

Views do not have input parameters like stored procedures/functions. You cannot create a view with syntax like `v_orders(customer_id)` to pass a customer ID at call time.

Instead, consumers add conditions:

```sql
SELECT order_id, status, total_amount
FROM v_order_details
WHERE customer_id = 42;
```

If parameterized logic is needed, you can use an appropriate stored procedure, function, or let the application pass bind parameters to queries against the view. Do not concatenate SQL strings from user input; always use prepared statements/parameter binding to prevent SQL injection.

## 19. Nested Views and Dependency Management

Views can reference other views to create logical layers. Example:

```sql
CREATE VIEW v_vn_customers AS
SELECT customer_id, customer_name, status, region_code
FROM customers
WHERE region_code = 'VN';

CREATE VIEW v_active_vn_customers AS
SELECT customer_id, customer_name, region_code
FROM v_vn_customers
WHERE status = 'active';
```

Layering can make logic reusable, but too many layers make dependencies hard to track and execution plans hard to read. When modifying underlying tables or lower-level views, you must check upper-level views and consumers.

Do not create circular references between views. Follow naming conventions, manage definitions through migrations, and store view creation scripts in source control. When deploying, create or update objects in dependency order.

## 20. How Do Views and Temporary Tables Differ?

| Criterion | Regular View | Temporary Table |
| --- | --- | --- |
| Object | SELECT definition stored in schema | Temporary physical table created in a session |
| Data | Does not store its own results | Stores inserted or materialized rows |
| Lifecycle | Exists until DROP/schema change | `CREATE TEMPORARY TABLE` exists for the session, automatically dropped when the session ends |
| Reusability | Multiple sessions can query based on privileges | Only the session that created the temporary table can see it |
| Indexes | Uses indexes of underlying tables | Indexes can be created on the temporary table |
| Purpose | Encapsulate logic and query interface | Store intermediate datasets per session |
| Freshness | Reads underlying data according to transaction snapshot | Temporary data persists according to operations written to the table |

Views are suitable when you want to name shared query logic. Temporary tables are suitable when you need to store intermediate results for use across multiple statements in a session or need dedicated indexes for a temporary dataset.

A view's `ALGORITHM=TEMPTABLE` does not turn a view into a user-managed `CREATE TEMPORARY TABLE`. It is an internal temporary result for view execution, scoped to the lifetime of the query.

## 21. Measuring View Performance

You cannot conclude whether a view is fast or slow simply from having an extra named layer. Inspect what plan the query is optimized into:

```sql
EXPLAIN
SELECT customer_id, customer_name
FROM v_active_customers
WHERE region_code = 'VN';
```

Compare with the direct query:

```sql
EXPLAIN
SELECT customer_id, customer_name
FROM customers
WHERE status = 'active'
  AND region_code = 'VN';
```

Check:

- Whether the view is merged or materialized.
- Whether outer conditions are pushed down to underlying tables.
- Which index is chosen and how many estimated rows need to be read.
- Whether there are expensive temporary tables, sorts, or aggregates.
- Whether `EXPLAIN ANALYZE` shows actual rows/loops differing significantly from estimates.

On MySQL 8.0.18 and later, you can use `EXPLAIN ANALYZE` with suitable read queries:

```sql
EXPLAIN ANALYZE
SELECT customer_id, customer_name
FROM v_active_customers
WHERE region_code = 'VN';
```

This command executes the query. Only run it on safe SELECTs and consider load if the dataset is large or production is sensitive.

## 22. Indexes Belong to Underlying Tables, Not Views

You cannot create indexes directly on a regular view in MySQL. If queries through a view are slow due to filtering or JOINs, check the indexes of the underlying tables.

For example, a view filtering customers by region and status:

```sql
CREATE VIEW v_active_customers AS
SELECT customer_id, customer_name, region_code
FROM customers
WHERE status = 'active';
```

Consumer queries additionally filter by `region_code`. An index `(region_code, status)` may suit this access pattern:

```sql
SHOW INDEX FROM customers;
```

In the DDL in section 2, the index `(region_code, status)` was already created under the name `idx_customers_region_status`. Use `SHOW INDEX` to verify existing indexes before altering the schema; do not recreate an index that already exists. Index column order should be based on actual conditions, cardinality, and workload. A view only provides a query layer; indexes are still managed on underlying tables.

## 23. Limitations and Caveats When Designing Views

- Views do not accept parameters; consumers must filter in the outer query or use appropriate routines.
- Views do not store results persistently and do not have their own indexes.
- Views with aggregates, `DISTINCT`, `GROUP BY`, `HAVING`, `UNION`, `LIMIT`, or window functions are typically not updatable and may not be mergeable.
- `TEMPTABLE` materializes results for execution and makes the view non-updatable.
- Multi-table JOIN views have update restrictions; a single UPDATE through a join view can only update one underlying table at a time.
- `ORDER BY` inside a view does not replace `ORDER BY` in the outer query.
- `SELECT *` makes the view interface hard to control when the schema changes.
- A definer can lose privileges or be dropped, causing the view to fail on execution.
- Deeply nested views make dependencies and plans hard to trace.
- Privileges on a view have no security value if consumers still have broad privileges on underlying tables.

## 24. Process for Designing and Deploying Views

1. Identify consumers and the data they actually need.
2. Finalize the view name, column list, and stable aliases.
3. Write the underlying `SELECT` and verify correct results with NULLs, duplicates, and cardinality.
4. Decide whether the view is read-only or needs to be updatable.
5. If updatable, check supported conditions and consider `WITH CHECK OPTION`.
6. Choose `SQL SECURITY DEFINER` or `INVOKER` according to the permission model.
7. Choose the default algorithm first; only specify MERGE/TEMPTABLE when there is a reason and it has been measured.
8. Create views via migrations and manage them in source control.
9. Grant least privileges to consumers and verify the definer.
10. Run `SHOW CREATE VIEW` and check `INFORMATION_SCHEMA.VIEWS`.
11. Use `EXPLAIN`/`EXPLAIN ANALYZE` with key consumer queries.
12. Check dependencies after underlying table migrations and deploy with a rollback plan.

## 25. Common Mistakes and Misconceptions

| Misconception / Mistake | Reality | How to Handle |
| --- | --- | --- |
| Views pre-store SELECT results | Regular views store query definitions | Use a summary table if materialized data is needed |
| Views always make queries slow | Views can merge into the outer query block | Check EXPLAIN and the execution plan |
| ALGORITHM=TEMPTABLE is an application-managed temp table | It is an internal intermediate result per execution | Use CREATE TEMPORARY TABLE if data must persist across statements |
| Views with GROUP BY can still be updated like tables | Aggregates/GROUP BY usually make views non-updatable | Use a read-only view or update underlying tables with separate DML |
| WITH CHECK OPTION is a privilege mechanism | It checks that written rows still satisfy view conditions | Design GRANT and SQL SECURITY separately |
| DEFINER and INVOKER are the same | They use different identities to check underlying privileges | Choose based on the least privilege model |
| ORDER BY inside a view guarantees order for every read | Outer queries need their own ORDER BY | Sort in the final SELECT |
| Parameters can be passed to views | Views do not accept parameters | Use bind parameters in the outer query or routines |
| Indexes can be created directly on views | Indexes belong to underlying tables | Optimize indexes/access paths on underlying tables |
| CREATE OR REPLACE is always safe for consumers | Column changes can break the application contract | Check dependencies and schema versioning |

## 26. Hands-on Exercises

1. Create the `customers` and `orders` tables from the example; create the view `v_active_customers`.
2. Use the view in a query filtering on `region_code`; compare results with a direct query on the table.
3. Create a view with an explicit column list/aliases and inspect `SHOW CREATE VIEW`.
4. Create a view aggregating paid orders by customer; explain why this view is not updatable.
5. Create a simple updatable view; update a row through the view and inspect the underlying table.
6. Add `WITH CASCADED CHECK OPTION`; try updating a row so it no longer satisfies the view condition and observe the error.
7. Create two view layers with different conditions; compare `LOCAL` and `CASCADED CHECK OPTION`.
8. Create one view with `SQL SECURITY INVOKER` and one with `DEFINER`; test using users with different privileges.
9. Compare `ALGORITHM=MERGE` and `TEMPTABLE` using `EXPLAIN`; note the plan differences.
10. Put `ORDER BY` inside a view, then run an outer query with a different `ORDER BY`; explain the resulting order.
11. Inspect `INFORMATION_SCHEMA.VIEWS`, `IS_UPDATABLE`, `DEFINER`, and `SECURITY_TYPE`.
12. Compare a view with `CREATE TEMPORARY TABLE` for an intermediate result set used across multiple statements.
13. Try changing an underlying table schema in a lab environment; verify the view and consumers after migration.

## 27. Key Takeaways

A view is a schema object storing a `SELECT` definition, helping encapsulate logic and create a query boundary with clear naming, column lists, and access privileges. Regular views do not store results, do not have their own indexes, and are not caches/materialized views. The optimizer may merge a view into the outer query or materialize temporary results based on the algorithm; `MERGE`, `TEMPTABLE`, and `UNDEFINED` behave differently.

Simple single-table views can be updatable; aggregates, `DISTINCT`, `GROUP BY`, `HAVING`, `UNION`, window functions, and `TEMPTABLE` usually make views non-updatable. `WITH CHECK OPTION` ensures written rows continue to satisfy the view's conditions; `LOCAL` and `CASCADED` differ in how underlying views are checked. `SQL SECURITY DEFINER` uses the definer's privileges, whereas `INVOKER` uses the caller's privileges; choose a minimal definer and manage that account carefully. `ORDER BY` inside a view does not guarantee final ordering, views do not accept parameters, and indexes must be designed on underlying tables. Manage views like query contracts: list columns explicitly, manage migrations/dependencies, verify privileges, and use `EXPLAIN`/`EXPLAIN ANALYZE` to confirm execution plans.
