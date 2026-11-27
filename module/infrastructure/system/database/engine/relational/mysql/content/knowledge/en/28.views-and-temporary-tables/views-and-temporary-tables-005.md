# View Dependencies, Schema Changes, and Inspecting Definitions

## Objectives

After this lesson, you will be able to:

- Explain dependency relationships between views, other views, and underlying tables.
- Inspect view lists, SQL definitions, output columns, execution privileges, and view metadata.
- Identify the impact of `ALTER TABLE`, renaming, or dropping columns/tables on views using them.
- Understand why `SELECT *` in a view definition does not automatically expand when an underlying table adds a column.
- Update views using `CREATE OR REPLACE VIEW` or `ALTER VIEW` in the proper dependency order.
- Plan schema migrations involving multiple interdependent views.
- Diagnose broken views using `CHECK TABLE`, `SHOW CREATE VIEW`, and `INFORMATION_SCHEMA`.
- Evaluate `ALGORITHM`, `SQL SECURITY`, `DEFINER`, and view updatability after changes.
- Understand limitations when views interact with temporary tables.

Examples target MySQL 8.0/8.4. Verify exact syntax, privileges, and metadata on your target server version before deploying.

## 1. What Objects Does a View Depend On?

A view is a schema object that stores a `SELECT` query definition. When an application reads a view, MySQL resolves that definition and accesses the tables or views referenced inside it.

Example:

```sql
CREATE TABLE products (
    product_id BIGINT UNSIGNED NOT NULL,
    sku VARCHAR(40) NOT NULL,
    product_name VARCHAR(160) NOT NULL,
    status VARCHAR(20) NOT NULL,
    price DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (product_id),
    UNIQUE KEY uq_products_sku (sku)
) ENGINE = InnoDB;

CREATE VIEW v_active_products AS
SELECT product_id, sku, product_name, price
FROM products
WHERE status = 'ACTIVE';
```

`v_active_products` depends on the `products` table and the columns `product_id`, `sku`, `product_name`, `price`, `status`. If another view queries `v_active_products`, that view in turn depends on this view.

### 1.1. Direct Dependencies and Indirect Dependencies

You can visualize the chain:

```text
products
   |
   v
v_active_products
   |
   v
v_active_product_names
   |
   v
v_product_catalog
```

Create the chained views:

```sql
CREATE VIEW v_active_product_names AS
SELECT product_id, product_name
FROM v_active_products;

CREATE VIEW v_product_catalog AS
SELECT product_id, product_name
FROM v_active_product_names;
```

`v_product_catalog` does not reference `products` directly, yet it indirectly depends on that table through two intermediate views. When renaming or dropping a column in `products`, you must check the entire view chain, not just the first view.

### 1.2. A View Is Not a Copy of Data

Regular views do not store a copy of query results like materialized views. MySQL stores the definition and executes it when queried. Data changes in underlying tables are reflected through the view according to the query's transaction and isolation semantics.

MySQL does not provide built-in materialized views that automatically store and refresh results. If an aggregated snapshot is needed, you need to design a summary table or a dedicated materialization mechanism.

### 1.3. A View Is a Schema Contract with Applications

Applications can rely on a view's name, column names, data types, column order, and filtering semantics. Therefore, views should be managed like a database API:

- Declare column lists explicitly.
- Keep column names and meanings stable.
- Avoid changing data types or column order in ways that break clients.
- Check dependent views before changing underlying schemas.
- Put view definitions under project migration/version control.

## 2. Declaring Views with Explicit Column Lists

You should explicitly select columns in the view definition:

```sql
CREATE VIEW v_active_products (
    product_id,
    product_sku,
    product_name,
    unit_price
) AS
SELECT
    product_id,
    sku,
    product_name,
    price
FROM products
WHERE status = 'ACTIVE';
```

The list after the view name defines output column names. It helps decouple the column names applications use from the physical column names of the underlying table.

### 2.1. Why Should You Avoid SELECT *?

Example:

```sql
CREATE VIEW v_products AS
SELECT *
FROM products;
```

MySQL determines the view's column list at the time the view is created or redefined. If the `products` table later gains a `category_id` column, the existing view does not automatically expand to return the new column.

This has two consequences:

- Applications may not see the new column even though the underlying table has it.
- Maintainers may mistakenly assume `SELECT *` is always re-evaluated against the current schema.

If you want the view to expose new columns, update the definition using `CREATE OR REPLACE VIEW` or `ALTER VIEW` with the new column list.

### 2.2. Duplicate Column Names and Computed Expressions

Each output column of a view must have a unique name. When using expressions or multiple tables with matching column names, specify clear aliases:

```sql
CREATE VIEW v_order_summary AS
SELECT
    o.order_id,
    o.customer_id,
    COUNT(i.item_id) AS item_count,
    SUM(i.quantity * i.unit_price) AS calculated_total
FROM orders AS o
JOIN order_items AS i
  ON i.order_id = o.order_id
GROUP BY o.order_id, o.customer_id;
```

Alias names become part of the view's interface. Changing an alias can break client queries or dependent views.

## 3. Inspecting the List of Views in a Schema

### 3.1. SHOW FULL TABLES

List tables and views:

```sql
SHOW FULL TABLES FROM sales;
```

The `Table_type` column indicates whether an object is a `BASE TABLE` or `VIEW`.

Filter only views:

```sql
SHOW FULL TABLES FROM sales
WHERE Table_type = 'VIEW';
```

### 3.2. INFORMATION_SCHEMA.VIEWS

`INFORMATION_SCHEMA.VIEWS` provides view metadata:

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    VIEW_DEFINITION,
    CHECK_OPTION,
    IS_UPDATABLE,
    DEFINER,
    SECURITY_TYPE,
    CHARACTER_SET_CLIENT,
    COLLATION_CONNECTION
FROM information_schema.VIEWS
WHERE TABLE_SCHEMA = 'sales'
ORDER BY TABLE_NAME;
```

Commonly inspected fields:

| Field | Meaning |
|---|---|
| `TABLE_SCHEMA`, `TABLE_NAME` | Schema and view name |
| `VIEW_DEFINITION` | Stored SELECT definition |
| `CHECK_OPTION` | `NONE`, `LOCAL`, or `CASCADED` |
| `IS_UPDATABLE` | Indicates whether the view is evaluated as updatable |
| `DEFINER` | Account that defined the view |
| `SECURITY_TYPE` | `DEFINER` or `INVOKER` |
| `CHARACTER_SET_CLIENT` | Client character set when the view was created |
| `COLLATION_CONNECTION` | Connection collation when the view was created |

`VIEW_DEFINITION` may not display in full if the account lacks required privileges. When you need to verify definitions, use an account granted appropriate `SHOW VIEW` privileges.

### 3.3. SHOW CREATE VIEW

This is the direct way to inspect the view creation statement:

```sql
SHOW CREATE VIEW sales.v_active_products;
```

The output shows the `SELECT` definition, `ALGORITHM`, `DEFINER`, `SQL SECURITY`, and `CHECK OPTION` if present. Save this output during migration workflows or compare it against definitions in source control.

### 3.4. DESCRIBE and SHOW COLUMNS

Inspect the output schema:

```sql
DESCRIBE sales.v_active_products;

SHOW FULL COLUMNS FROM sales.v_active_products;
```

You can cross-check with column metadata:

```sql
SELECT
    COLUMN_NAME,
    ORDINAL_POSITION,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    CHARACTER_SET_NAME,
    COLLATION_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = 'sales'
  AND TABLE_NAME = 'v_active_products'
ORDER BY ORDINAL_POSITION;
```

The data type of a view column is derived from the SELECT expression. Changing an underlying table column's type can change the view's output type after the definition is updated or re-resolved; verify the output schema rather than assuming clients are unaffected.

## 4. Inspecting Dependencies with VIEW_TABLE_USAGE

MySQL provides `INFORMATION_SCHEMA.VIEW_TABLE_USAGE` to inspect tables or views used in a view definition.

```sql
SELECT
    VIEW_SCHEMA,
    VIEW_NAME,
    TABLE_SCHEMA,
    TABLE_NAME
FROM information_schema.VIEW_TABLE_USAGE
WHERE VIEW_SCHEMA = 'sales'
ORDER BY VIEW_NAME, TABLE_SCHEMA, TABLE_NAME;
```

The result represents direct usage relationships between views and referenced objects. The object in `TABLE_NAME` can be a base table or another view.

### 4.1. Finding Views That Reference a Specific Table

For example, finding views referencing `sales.products`:

```sql
SELECT
    VIEW_SCHEMA,
    VIEW_NAME
FROM information_schema.VIEW_TABLE_USAGE
WHERE TABLE_SCHEMA = 'sales'
  AND TABLE_NAME = 'products'
ORDER BY VIEW_SCHEMA, VIEW_NAME;
```

This query helps identify views that directly depend on the `products` table.

### 4.2. Finding Views That Reference Another View

```sql
SELECT
    VIEW_SCHEMA,
    VIEW_NAME
FROM information_schema.VIEW_TABLE_USAGE
WHERE TABLE_SCHEMA = 'sales'
  AND TABLE_NAME = 'v_active_products';
```

The output shows views using `v_active_products`. You can continue querying to trace the dependency chain.

### 4.3. Indirect Dependencies Must Be Traced Across Multiple Levels

If `v_catalog` references `v_active_product_names`, and that view references `v_active_products`, then a query filtering directly on `products` only finds views referencing `products` if those views have a direct relationship in metadata. To build a complete graph, trace view-to-view edges across multiple levels.

When the number of views is large, export the edge list from `VIEW_TABLE_USAGE` and construct the deployment order in a migration tool or admin script. Do not rely merely on view names or alphabetical order.

### 4.4. Privileges and Metadata Visibility

Metadata visibility can depend on account privileges. If results omit views you know exist, check `SHOW VIEW` privileges and access privileges on the relevant schemas before concluding there are no dependencies.

## 5. Impact of Underlying Table Schema Changes

A view stores a definition dependent on object and column names. DDL on underlying tables can render a view invalid or alter the data/output types clients receive.

### 5.1. Adding a New Column

Suppose the current view is:

```sql
CREATE VIEW v_product_list AS
SELECT product_id, sku, product_name
FROM products;
```

Then add a column:

```sql
ALTER TABLE products
    ADD COLUMN category_id BIGINT UNSIGNED NULL;
```

The view can still work because the columns it references have not changed, but `category_id` does not automatically appear in view results. To expose the new column, update the view definition.

### 5.2. Renaming a Column Referenced by a View

Suppose the view references `sku`. If you run:

```sql
ALTER TABLE products
    RENAME COLUMN sku TO product_code;
```

the view definition still contains the old column name and can become invalid. Queries using or checking the view can report an invalid column reference error.

Before renaming, find all dependent views, prepare new definitions, and deploy in a safe order. Do not assume MySQL automatically updates all dependent views to the new column name.

### 5.3. Dropping a Column Referenced by a View

```sql
ALTER TABLE products
    DROP COLUMN product_name;
```

If the view or a dependent view requires `product_name`, that definition is no longer valid. You must update or drop dependent views before dropping the column, or perform a phased compatible migration.

### 5.4. Changing Data Types

Example:

```sql
ALTER TABLE products
    MODIFY price DECIMAL(18,4) NOT NULL;
```

The view may still resolve, but output types, precision, conversion rules, or expression results can change. Clients relying on the old type may need updating. Check `SHOW CREATE VIEW`, `DESCRIBE view`, and sample results after DDL.

### 5.5. Renaming or Moving a Table

Renaming a table or moving a table to another schema can make referenced names in a view definition incorrect. Treat this operation as a dependency change requiring explicit view migrations. Inspect `VIEW_TABLE_USAGE`, stored definitions via `SHOW CREATE VIEW`, and run `CHECK TABLE` after deployment.

### 5.6. Adding or Modifying Indexes

Index changes usually do not invalidate a view because view definitions depend on columns and expressions, not index names. However, the execution plan of queries through the view can change. Use `EXPLAIN` on view queries to verify performance after index or statistics changes.

## 6. CREATE OR REPLACE VIEW and ALTER VIEW

When underlying schemas change, views need to be updated via view DDL.

### 6.1. CREATE OR REPLACE VIEW

`CREATE OR REPLACE VIEW` creates a view if it does not exist or replaces an existing view definition:

```sql
CREATE OR REPLACE VIEW v_product_list AS
SELECT
    product_id,
    product_code,
    product_name,
    category_id
FROM products;
```

This command is useful for migrations with a clear target definition. However, changing the column list, aliases, or output types can impact clients and dependent views. Downstream dependencies must be checked before replacing.

### 6.2. ALTER VIEW

`ALTER VIEW` modifies the definition of an existing view:

```sql
ALTER VIEW v_product_list AS
SELECT
    product_id,
    product_code,
    product_name,
    category_id
FROM products;
```

`ALTER VIEW` does not create a new view if one does not already exist. If a migration must be idempotent in a create-or-replace style, use the corresponding syntax and verify privileges.

### 6.3. Declaring Full View Attributes

You can explicitly declare algorithm, definer, and security:

```sql
CREATE OR REPLACE
    ALGORITHM = UNDEFINED
    DEFINER = CURRENT_USER
    SQL SECURITY INVOKER
VIEW v_product_list (
    product_id,
    product_code,
    product_name,
    category_id
) AS
SELECT
    product_id,
    product_code,
    product_name,
    category_id
FROM products;
```

In multi-server deployment environments, control `DEFINER` and that account's privileges. `CURRENT_USER` captures the current account at statement execution time; do not copy a specific definer from development to production if that account does not exist or lacks corresponding privileges.

### 6.4. Changing a View Can Break Dependent Views

Suppose `v_active_product_names` references `v_active_products`. If you replace `v_active_products` and remove the `product_name` column, the upper view can become invalid.

Deploy changes in dependency order:

1. Update views closest to underlying tables first.
2. Update views referencing those views.
3. Continue upward to higher-level views.
4. Verify the entire chain and clients.

When removing a column, a two-phase compatible rollout may be needed: add the new column/alias first, migrate clients and dependent views to the new name, and only then drop the old column.

## 7. View ALGORITHM and Execution Impact

MySQL supports the following `ALGORITHM` options:

- `MERGE`: attempts to merge the view definition into the outer query so the optimizer processes them as one combined query.
- `TEMPTABLE`: materializes the view result into an internal temporary table before processing the remainder.
- `UNDEFINED`: lets MySQL choose the appropriate algorithm.

Example:

```sql
CREATE OR REPLACE ALGORITHM = MERGE VIEW v_active_products AS
SELECT product_id, sku, product_name, price
FROM products
WHERE status = 'ACTIVE';
```

### 7.1. MERGE

With a mergeable view, conditions from the outer query can be pushed down to underlying tables and the optimizer can choose underlying table indexes. This usually avoids intermediate materialization.

Not every view can be merged. Constructs such as aggregates, `GROUP BY`, `DISTINCT`, `UNION`, and certain subqueries or expressions restrict merging.

### 7.2. TEMPTABLE

`TEMPTABLE` creates an intermediate table holding view results before the outer query continues. It can be useful in certain scenarios, but incurs materialization costs and typically makes the view non-updatable.

Do not confuse the internal temporary table used for executing a view with an application-created `CREATE TEMPORARY TABLE`. They have different lifecycles and purposes.

### 7.3. UNDEFINED

`UNDEFINED` gives the optimizer the choice. This is usually the right default when there is no clear reason to force an algorithm. Read `SHOW CREATE VIEW` to inspect stored attributes and use `EXPLAIN` on actual queries to understand the plan.

## 8. SQL SECURITY and DEFINER

A view can execute under the privileges of its definer or its caller.

### 8.1. SQL SECURITY DEFINER

`DEFINER` is the default if not specified otherwise. Queries on the view use the definer account's privileges to access underlying objects.

This allows granting applications SELECT on a view without granting direct SELECT on every underlying table. However, the definer must be managed carefully:

- The definer account must exist and have required privileges on referenced objects.
- Definer privileges should be kept at the minimum necessary level.
- Do not use DBA/root accounts as the definer for ordinary application views.
- When deploying to other environments, account and privilege differences must be handled.

### 8.2. SQL SECURITY INVOKER

`INVOKER` uses the privileges of the account calling the view:

```sql
CREATE OR REPLACE
    SQL SECURITY INVOKER
VIEW v_public_products AS
SELECT product_id, sku, product_name
FROM products
WHERE status = 'ACTIVE';
```

Callers need the necessary privileges on objects accessed through the view. This avoids depending on a single definer's privileges, though it does not provide a delegation layer hiding underlying tables in the way DEFINER is often used.

### 8.3. Checking Definer and Security Type

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    DEFINER,
    SECURITY_TYPE
FROM information_schema.VIEWS
WHERE TABLE_SCHEMA = 'sales'
ORDER BY TABLE_NAME;
```

Or:

```sql
SHOW CREATE VIEW sales.v_public_products;
```

If a view works in development but fails in production, check the definer, SELECT privileges on underlying tables, view access privileges, and whether the definer account exists.

## 9. CHECK OPTION and View Updatability

Some views can be updated. `WITH CHECK OPTION` requires rows INSERTed/UPDATEd through the view to continue satisfying the view's condition.

Example:

```sql
CREATE OR REPLACE VIEW v_active_products AS
SELECT product_id, sku, product_name, status
FROM products
WHERE status = 'ACTIVE'
WITH CASCADED CHECK OPTION;
```

If an application updates `status` to `INACTIVE` through the view, the operation is rejected because the new row no longer satisfies the view condition.

### 9.1. LOCAL and CASCADED

- `LOCAL`: checks the condition of the current view.
- `CASCADED`: checks the condition of the current view and related underlying views in the view chain according to check option rules.

If unspecified, the default is `CASCADED` when `CHECK OPTION` is present.

### 9.2. Schema Changes Can Affect Updatability

A view can transition from updatable to non-updatable if its definition is modified to include aggregates, `DISTINCT`, `GROUP BY`, `UNION`, or disallowed constructs. Check:

```sql
SELECT
    TABLE_NAME,
    IS_UPDATABLE,
    CHECK_OPTION
FROM information_schema.VIEWS
WHERE TABLE_SCHEMA = 'sales';
```

Do not assume a view remains updatable just because it previously allowed UPDATEs. After a migration, verify both metadata and test write operations in a test environment.

## 10. Inspecting Views After Schema Changes

### 10.1. CHECK TABLE

MySQL supports `CHECK TABLE` to check views:

```sql
CHECK TABLE sales.v_active_products;
```

This command can detect views referencing tables, columns, or routines that are no longer valid. If a view is invalid, the output may state causes such as invalid table/column/function references or definer/invoker privilege issues.

You can check multiple views:

```sql
CHECK TABLE
    sales.v_active_products,
    sales.v_active_product_names,
    sales.v_product_catalog;
```

`CHECK TABLE` is a metadata check step; it does not replace testing queries and application privileges.

### 10.2. SHOW CREATE VIEW

```sql
SHOW CREATE VIEW sales.v_active_products;
```

Compare the definition against source control or expected migration state. Check table/column names, aliases, algorithm, definer, and security type.

### 10.3. DESCRIBE View

```sql
DESCRIBE sales.v_active_products;
```

Ensure the column list, data types, and nullability match the contract used by clients.

### 10.4. Test SELECT

```sql
SELECT *
FROM sales.v_active_products
LIMIT 10;
```

Run the query under the actual application account, not just a DBA account. The fact that a DBA can read the view does not prove the runtime account has sufficient privileges or that the definer is valid.

### 10.5. EXPLAIN Queries Through the View

```sql
EXPLAIN FORMAT=JSON
SELECT product_id, product_name
FROM sales.v_active_products
WHERE product_id = 1001;
```

Check whether the view is merged or materialized, which index on underlying tables is chosen, estimated row counts, and whether conditions are pushed down. A view that is valid in metadata can still produce an unsuitable execution plan.

## 11. Safe Schema Changes with Multiple Dependent Views

Do not execute an arbitrary sequence of DDL statements when multiple views use underlying tables. Plan migrations according to the dependency graph.

### 11.1. Step 1: Build the Dependency List

```sql
SELECT
    VIEW_SCHEMA,
    VIEW_NAME,
    TABLE_SCHEMA,
    TABLE_NAME
FROM information_schema.VIEW_TABLE_USAGE
WHERE TABLE_SCHEMA = 'sales'
   OR VIEW_SCHEMA = 'sales'
ORDER BY VIEW_SCHEMA, VIEW_NAME, TABLE_SCHEMA, TABLE_NAME;
```

Note: this condition finds edges where either the view or the referenced object belongs to the `sales` schema; if dependencies cross other schemas, broaden the query scope.

### 11.2. Step 2: Save Current Definitions

For each important view, save `SHOW CREATE VIEW` to your migration repository or deployment artifact. Record output columns and security attributes.

### 11.3. Step 3: Classify Changes

Distinguish between:

- Adding a new column not currently used by views.
- Renaming or dropping a column currently referenced by views.
- Changing data types, nullability, or collation.
- Renaming a table or moving schemas.
- Changing indexes affecting only execution plans.
- Changing a view definition and its output contract.

Each category has a different testing scope.

### 11.4. Step 4: Roll Out in a Compatible Manner

For example, suppose `sku` needs to be renamed to `product_code`. You can split it into phases:

1. Add the new column `product_code` or establish a compatible synchronization mechanism.
2. Backfill data and verify both columns stay consistent according to business rules.
3. Create/update views exposing the `product_code` alias.
4. Migrate clients and dependent views to the new column.
5. Confirm no remaining dependencies on `sku`.
6. After a compatibility window, drop the old column.

This is the expand-and-contract pattern. How two columns are synchronized must be designed for the actual system; do not automatically add triggers without evaluating transactions, replication, and update ordering.

### 11.5. Step 5: Update in Dependency Order

If `v_low` depends on underlying tables, `v_mid` depends on `v_low`, and `v_top` depends on `v_mid`, the safe order is typically:

1. Update underlying tables.
2. Recreate `v_low`.
3. Recreate `v_mid`.
4. Recreate `v_top`.
5. Verify and test clients.

If you need to drop a view to change its structure, drop from higher-level dependent views downward first, then recreate from the bottom up. Do not drop an underlying view while upper-level views still depend on it.

### 11.6. Step 6: Verify and Release

```sql
CHECK TABLE
    sales.v_low,
    sales.v_mid,
    sales.v_top;

SHOW CREATE VIEW sales.v_low;
SHOW CREATE VIEW sales.v_mid;
SHOW CREATE VIEW sales.v_top;
```

Then run SELECT/EXPLAIN under the runtime account and verify application features depending on the views.

## 12. DDL, Transactions, and Rollback Plans

DDL statements such as `ALTER TABLE`, `CREATE VIEW`, `ALTER VIEW`, and `DROP VIEW` follow MySQL's own commit rules. Do not assume you can wrap an entire view/schema migration in a transaction and undo everything with `ROLLBACK`.

Before running a migration:

- Prepare reverse DDL or a plan to restore old definitions.
- Save `SHOW CREATE VIEW` before changes.
- Determine deployment order and downstream dependencies.
- Check metadata locks and DDL duration on large tables.
- Dry-run in a staging environment with data and privileges close to production.
- Roll out in compatible steps if clients deploy independently.

MySQL 8.0 supports atomic DDL for many supported operations, but atomic DDL does not mean a sequence of multiple distinct DDL statements forms a single transaction that can be rolled back together. Migrations must be designed for process-level recovery.

## 13. Views and Temporary Tables

A view is a schema object with a persistently stored definition. A session-created temporary table exists only within the current connection. Because of their different lifecycles and scopes, a view cannot be defined to reference a temporary table.

The following example is not a valid design:

```sql
CREATE TEMPORARY TABLE tmp_active_products (
    product_id BIGINT NOT NULL,
    product_name VARCHAR(160) NOT NULL
);

-- Cannot create a persistent schema view based on this temporary table.
```

If an application needs a view, reference persistent base tables. If session-scoped intermediate data is needed, query the temporary table directly within that session or stage data in a staging table with a managed lifecycle.

Do not confuse application-created temporary tables with internal temporary tables that the optimizer may use to execute an aggregate/materialized view.

## 14. Security and Privileges for Inspecting Definitions

Some inspection operations require specific privileges:

- `SHOW CREATE VIEW` requires the `SHOW VIEW` privilege on the view.
- Reading data through a view requires appropriate privileges according to `SQL SECURITY DEFINER` or `INVOKER`.
- `CREATE VIEW`, `ALTER VIEW`, and `DROP VIEW` require corresponding administrative privileges on the schema/object.
- The definer account needs privileges on underlying tables or views per the definition.

Example granting definition-viewing privileges to an existing account:

```sql
GRANT SHOW VIEW ON sales.* TO 'report_reader'@'localhost';
```

This is an example account name. Replace it with an actual account per your authorization policy; do not grant broader privileges than needed. `SHOW VIEW` allows viewing the definition; it does not automatically grant SELECT on data through the view.

When troubleshooting issues, separate three questions:

1. Is the view definition valid?
2. Does the definer/invoker have sufficient privileges on underlying objects?
3. Does the application account have privileges to use the view and perform required operations?

A privilege error is not necessarily a schema dependency error; read the error message and inspect each layer.

## 15. Practice: Detecting and Fixing Views After Schema Changes

### 15.1. Create Table and View Chain

```sql
DROP VIEW IF EXISTS v_product_names;
DROP VIEW IF EXISTS v_active_products;
DROP TABLE IF EXISTS products;

CREATE TABLE products (
    product_id BIGINT NOT NULL,
    sku VARCHAR(40) NOT NULL,
    product_name VARCHAR(160) NOT NULL,
    status VARCHAR(20) NOT NULL,
    PRIMARY KEY (product_id)
) ENGINE = InnoDB;

CREATE VIEW v_active_products AS
SELECT product_id, sku, product_name
FROM products
WHERE status = 'ACTIVE';

CREATE VIEW v_product_names AS
SELECT product_id, product_name
FROM v_active_products;
```

### 15.2. Inspect Dependencies and Definitions

```sql
SELECT
    VIEW_SCHEMA,
    VIEW_NAME,
    TABLE_SCHEMA,
    TABLE_NAME
FROM information_schema.VIEW_TABLE_USAGE
WHERE VIEW_SCHEMA = DATABASE()
ORDER BY VIEW_NAME, TABLE_NAME;

SHOW CREATE VIEW v_active_products;
SHOW CREATE VIEW v_product_names;
```

### 15.3. Add a New Column

```sql
ALTER TABLE products
    ADD COLUMN category_id BIGINT NULL;
```

Verify:

```sql
DESCRIBE v_active_products;
```

`category_id` does not automatically appear in the view. Update the view:

```sql
CREATE OR REPLACE VIEW v_active_products AS
SELECT product_id, sku, product_name, category_id
FROM products
WHERE status = 'ACTIVE';
```

If `v_product_names` does not need `category_id`, it can continue working because the columns it references still exist. Nevertheless, run `CHECK TABLE` and SELECT to confirm.

### 15.4. Rename a Column and Update Dependencies

Suppose `sku` is renamed to `product_code`. First, identify all dependent views. After DDL:

```sql
ALTER TABLE products
    RENAME COLUMN sku TO product_code;
```

`v_active_products` still references `sku`, so it can become invalid. Update the lower-level view:

```sql
CREATE OR REPLACE VIEW v_active_products AS
SELECT product_id, product_code, product_name, category_id
FROM products
WHERE status = 'ACTIVE';
```

`v_product_names` only uses `product_id` and `product_name`; re-verify:

```sql
CHECK TABLE v_active_products, v_product_names;
SELECT * FROM v_active_products LIMIT 5;
SELECT * FROM v_product_names LIMIT 5;
```

### 15.5. Verify Output Schema and Privileges

```sql
SHOW CREATE VIEW v_active_products;
DESCRIBE v_active_products;

SELECT
    TABLE_NAME,
    DEFINER,
    SECURITY_TYPE,
    IS_UPDATABLE
FROM information_schema.VIEWS
WHERE TABLE_SCHEMA = DATABASE();
```

Run SELECT under an application account with corresponding privileges to verify actual behavior.

## 16. Common Mistakes

| Situation | Cause | How to Handle |
|---|---|---|
| View fails after renaming a column | Definition still references the old name | Find dependencies, update views from bottom up |
| Added a column but view does not return it | View column list is fixed at creation/redefinition time | Use CREATE OR REPLACE VIEW or ALTER VIEW |
| DROP COLUMN fails or view becomes invalid | Column is still referenced by views or view can no longer resolve | Find dependent views and perform a compatible migration |
| Upper-level view fails even though lower-level view works | Upper-level view depends on changed names/columns in lower-level view | Trace multi-level dependencies and recreate downstream views |
| SHOW CREATE VIEW cannot show definition | Missing SHOW VIEW privilege | Request appropriate least-privilege access |
| View works in dev but fails in production | Definer does not exist or privileges differ | Check DEFINER, SECURITY_TYPE, and underlying object privileges |
| View still runs but application fails | Output data types, aliases, or column order changed | DESCRIBE, check contract, and test clients |
| View changes to non-updatable | New definition contains aggregates, DISTINCT, GROUP BY, or restricted constructs | Check IS_UPDATABLE and redesign write operations |
| CHECK TABLE reports invalid reference | Referenced table/column/routine is no longer valid | Read SHOW CREATE VIEW, fix dependencies, then re-CHECK |
| DDL migration cannot be rolled back | DDL has implicit commit/separate atomic DDL behavior | Use phased migrations with recovery DDL |
| View references temporary table | Temporary tables are session-scoped, not persistent objects | Use persistent base tables or suitable staging tables |

## 17. Checklist for Deploying Schema Changes Involving Views

- [ ] Listed views in relevant schemas.
- [ ] Queried `INFORMATION_SCHEMA.VIEW_TABLE_USAGE` to map direct dependencies.
- [ ] Traced indirect dependencies across views.
- [ ] Saved `SHOW CREATE VIEW` for affected views.
- [ ] Checked output columns, data types, aliases, and column order.
- [ ] Identified whether DDL adds, renames, or drops columns/tables or changes data types.
- [ ] Avoided unnecessary reliance on `SELECT *`.
- [ ] Prepared view update order from lowest-level dependencies upward.
- [ ] Verified `ALGORITHM`, `DEFINER`, `SQL SECURITY`, and `CHECK OPTION`.
- [ ] Checked definer accounts and application privileges.
- [ ] Ran `CHECK TABLE`, `SHOW CREATE VIEW`, `DESCRIBE`, and test SELECTs.
- [ ] Used EXPLAIN to inspect execution plans through key views.
- [ ] Tested view-dependent clients after migration.
- [ ] Prepared a recovery plan since a sequence of DDL statements is not a single rollbackable transaction.
- [ ] Did not create views depending on temporary tables.

## 18. Conclusion

Views depend on table names, column names, expressions, and other views referenced in their definitions. Underlying schema changes can make views invalid or alter their output column contracts. Adding columns does not automatically expand views created with `SELECT *`; renaming or dropping referenced columns can break the view and dependent views.

Use `INFORMATION_SCHEMA.VIEWS`, `VIEW_TABLE_USAGE`, `SHOW CREATE VIEW`, `DESCRIBE`, and `CHECK TABLE` to inventory views, inspect definitions, and trace dependencies. During migrations, save current definitions, update views from the bottom up, verify `DEFINER`/`SQL SECURITY`, test with application accounts, and prepare recovery plans for DDL sequences. Managing views as schema contracts keeps underlying table changes safe and prevents errors from cascading across application layers.

## References

- [MySQL 8.4 Reference Manual: CREATE VIEW Statement](https://dev.mysql.com/doc/refman/8.4/en/create-view.html)
- [MySQL 8.4 Reference Manual: The INFORMATION_SCHEMA VIEWS Table](https://dev.mysql.com/doc/refman/8.4/en/information-schema-views-table.html)
- [MySQL 8.4 Reference Manual: The INFORMATION_SCHEMA VIEW_TABLE_USAGE Table](https://dev.mysql.com/doc/refman/8.4/en/information-schema-view-table-usage-table.html)
- [MySQL 8.4 Reference Manual: CHECK TABLE Statement](https://dev.mysql.com/doc/refman/8.4/en/check-table.html)
