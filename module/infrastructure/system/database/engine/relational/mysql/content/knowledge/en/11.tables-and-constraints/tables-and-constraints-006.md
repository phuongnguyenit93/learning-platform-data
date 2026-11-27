# CHECK Constraints and Enforcement Differences Across Versions

A `CHECK` constraint uses a Boolean expression to restrict the valid values of a row. For example, product quantity must be greater than 0, price cannot be negative, or a start date cannot be after an end date. The constraint is declared right in the schema so MySQL validates data on `INSERT` or `UPDATE`.

A critical detail when working with MySQL is that **the server version determines whether `CHECK` is actually enforced**. MySQL prior to 8.0.16 accepts `CHECK` syntax but ignores the constraint. Starting in MySQL 8.0.16, `CHECK` is enforced; constraints can be declared `ENFORCED` or `NOT ENFORCED`. Therefore, seeing a `CREATE TABLE` statement succeed or seeing the `CHECK` keyword in DDL is not enough to conclude that the data is protected.

This lesson explains how to declare `CHECK` constraints, how MySQL evaluates expressions, the limitations of `CHECK`, how to inspect metadata, and how to deploy safely when an environment spans multiple MySQL versions.

## 1. What Problems Does a CHECK Constraint Solve?

A table can have valid column data types yet still receive values that violate business rules. For instance, `quantity` is an integer, yet a negative quantity is invalid; `price` is a decimal, yet negative prices are forbidden; `start_date` and `end_date` are both valid dates, yet the interval can be inverted.

You can validate these conditions in the application, but if multiple applications, import scripts, or administrators write to the database, each one must reimplement the exact same rule. `CHECK` places the condition at the database level so every write statement against the table undergoes the same validation when the constraint is enabled.

Examples of common rules:

| Rule | Illustrative CHECK Expression |
| --- | --- |
| Quantity must be positive | `quantity > 0` |
| Price must be non-negative | `unit_price >= 0` |
| Percentage must be between 0 and 100 | `discount_percent BETWEEN 0 AND 100` |
| End date cannot precede start date | `start_date <= end_date` |
| Status belongs to an allowed set of values | `status IN ('draft', 'active', 'archived')` |

`CHECK` fits rules that can be evaluated from values within the same row. It does not replace primary keys, unique constraints, foreign keys, or complex business validation at the application layer.

## 2. Version Differences: Before and Since MySQL 8.0.16

This is the first thing to verify before relying on `CHECK`:

| MySQL Version | CHECK Behavior |
| --- | --- |
| MySQL 5.7 and earlier | `CHECK` syntax is accepted by the parser in many cases, but the constraint is ignored and does not protect data |
| MySQL 8.0.0 to 8.0.15 | Same: syntax is accepted, but `CHECK` is not enforced |
| MySQL 8.0.16 and later | `CHECK` is enforced by default; `ENFORCED` or `NOT ENFORCED` can be specified |
| MySQL 8.4 | Continues supporting `CHECK` enforcement using the MySQL 8.0.16+ mechanism |

The following example can execute successfully on both older and newer versions:

```sql
CREATE TABLE products (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    name VARCHAR(150) NOT NULL,
    price DECIMAL(13, 2) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT chk_products_price_nonnegative
        CHECK (price >= 0)
) ENGINE=InnoDB;
```

On MySQL prior to 8.0.16, the statement may create the table without errors, yet `price >= 0` is not enforced. An `INSERT` with a negative price will still be accepted. On MySQL 8.0.16 and later, the constraint is enforced by default and negative values are rejected.

Check the server version before deploying:

```sql
SELECT VERSION() AS mysql_version;
```

Do not treat successful DDL execution as proof that the constraint is active. Verify the version, check the enforcement status in metadata, and test a violating value in a test environment.

## 3. Column-Level and Table-Level CHECK Syntax

`CHECK` can be declared immediately after a column definition or at the table level.

### 3.1. Column-Level CHECK

```sql
CREATE TABLE products (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    name VARCHAR(150) NOT NULL,
    price DECIMAL(13, 2) NOT NULL
        CONSTRAINT chk_products_price_nonnegative CHECK (price >= 0),
    PRIMARY KEY (id)
) ENGINE=InnoDB;
```

This keeps the condition close to the checked column, making it easy to read when the rule involves only a single attribute.

### 3.2. Table-Level CHECK

```sql
CREATE TABLE order_items (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(13, 2) NOT NULL,
    discount_percent DECIMAL(5, 2) NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    CONSTRAINT chk_order_items_quantity_positive
        CHECK (quantity > 0),
    CONSTRAINT chk_order_items_unit_price_nonnegative
        CHECK (unit_price >= 0),
    CONSTRAINT chk_order_items_discount_range
        CHECK (discount_percent BETWEEN 0 AND 100)
) ENGINE=InnoDB;
```

Table-level `CHECK` is convenient when the condition combines multiple columns in the same row. For example:

```sql
CONSTRAINT chk_events_date_range
    CHECK (starts_at <= ends_at)
```

The expression is evaluated solely on data in the current row. `CHECK` does not query other tables to validate cross-table rules.

## 4. How Does MySQL Evaluate CHECK?

During `INSERT` or `UPDATE`, MySQL evaluates the constraint expression. Under SQL logic, the result has three states:

- `TRUE`: the row satisfies the condition and is accepted.
- `FALSE`: the row violates the condition and is rejected if the constraint is enforced.
- `UNKNOWN` (`NULL`): the row is accepted; the expression did not return `FALSE`.

The `UNKNOWN` case is crucial. For example:

```sql
CREATE TABLE inventory (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    quantity INT NULL,
    PRIMARY KEY (id),
    CONSTRAINT chk_inventory_quantity_positive
        CHECK (quantity > 0)
) ENGINE=InnoDB;
```

Outcomes:

| `quantity` Value | `quantity > 0` | CHECK |
| ---: | --- | --- |
| `5` | `TRUE` | Accepted |
| `0` | `FALSE` | Rejected |
| `-2` | `FALSE` | Rejected |
| `NULL` | `UNKNOWN` | Accepted |

If business rules forbid `NULL`, you must also declare `NOT NULL`:

```sql
quantity INT NOT NULL,
CONSTRAINT chk_inventory_quantity_positive CHECK (quantity > 0)
```

`CHECK (quantity > 0)` is not equivalent to `quantity IS NOT NULL`. Design nullability and value conditions as two separate rules.

## 5. Examples Validating Data on INSERT and UPDATE

Create a products table:

```sql
CREATE TABLE catalog_products (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    sku VARCHAR(50) NOT NULL,
    price DECIMAL(13, 2) NOT NULL,
    stock_quantity INT NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    PRIMARY KEY (id),
    UNIQUE KEY uq_catalog_products_sku (sku),
    CONSTRAINT chk_catalog_products_price
        CHECK (price >= 0),
    CONSTRAINT chk_catalog_products_stock
        CHECK (stock_quantity >= 0),
    CONSTRAINT chk_catalog_products_status
        CHECK (status IN ('draft', 'active', 'archived'))
) ENGINE=InnoDB;
```

Valid operations:

```sql
INSERT INTO catalog_products (sku, price, stock_quantity, status)
VALUES ('KB-001', 1250000.00, 10, 'active');

UPDATE catalog_products
SET stock_quantity = 8
WHERE sku = 'KB-001';
```

Violating operations:

```sql
-- Negative price violates chk_catalog_products_price
INSERT INTO catalog_products (sku, price, stock_quantity, status)
VALUES ('KB-002', -100.00, 5, 'active');

-- Negative stock violates chk_catalog_products_stock
UPDATE catalog_products
SET stock_quantity = -1
WHERE sku = 'KB-001';

-- Status outside allowed list
INSERT INTO catalog_products (sku, price, stock_quantity, status)
VALUES ('KB-003', 500000.00, 2, 'deleted');
```

On MySQL 8.0.16 and later when constraints are enforced, violating operations are rejected with a CHECK constraint error. The standard error code is `3819` (`ER_CHECK_CONSTRAINT_VIOLATED`). Applications should handle errors according to the constraint and business context rather than treating every write failure as a connection error.

## 6. CHECK Can Combine Multiple Columns

Some rules only make sense when comparing multiple columns in the same row:

```sql
CREATE TABLE promotions (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    regular_price DECIMAL(13, 2) NOT NULL,
    sale_price DECIMAL(13, 2) NOT NULL,
    starts_on DATE NOT NULL,
    ends_on DATE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT chk_promotions_regular_price
        CHECK (regular_price >= 0),
    CONSTRAINT chk_promotions_sale_price
        CHECK (sale_price >= 0 AND sale_price <= regular_price),
    CONSTRAINT chk_promotions_date_range
        CHECK (starts_on <= ends_on)
) ENGINE=InnoDB;
```

These constraints ensure the promotional price is non-negative and does not exceed the regular price, while the start date is not after the end date. These are local conditions requiring only values in the same row, so they fit `CHECK` well.

If one of the columns can be `NULL`, comparison expressions can evaluate to `UNKNOWN` and the row will still be accepted. Clearly decide which columns are mandatory, which can be unspecified, and add `NOT NULL` or `NULL`-handling expressions as needed.

## 7. Allowed CHECK Expressions and Limitations

A `CHECK` expression must be deterministically evaluable from the row's own data. MySQL restricts components inside the expression to avoid dependencies on mutable state or external data.

Do not use the following in a CHECK expression:

- Subqueries.
- Stored functions or loadable functions.
- System variables, user variables, or parameters.
- Nondeterministic functions such as `NOW()`, `CURRENT_TIMESTAMP`, or `RAND()`.
- References to columns in other tables.

The following example is invalid:

```sql
-- Do not use current time in CHECK
CHECK (expires_at > CURRENT_TIMESTAMP)
```

Time conditions change continuously; a row valid at insert time could become "invalid" simply because time passes, even without any update statement. MySQL does not use `CHECK` to maintain such dynamic time-varying conditions.

If you need to check an expiration timestamp against the current time, check it in queries or the business layer when performing an action. If expired records need automatic processing, use a job/event scheduler or appropriate mechanism rather than putting dynamic conditions in `CHECK`.

## 8. CHECK Does Not Replace Other Constraint Types

Each constraint type has its own purpose:

| Mechanism | What It Guarantees | Example |
| --- | --- | --- |
| `NOT NULL` | Column must have a value | `email VARCHAR(254) NOT NULL` |
| `PRIMARY KEY` | Unique identifier and non-NULL | `PRIMARY KEY (id)` |
| `UNIQUE` | No two duplicate values per index/collation rules | `UNIQUE (email)` |
| `FOREIGN KEY` | Referenced value must exist per relationship | `customer_id REFERENCES customers(id)` |
| `CHECK` | Expression on row values must not evaluate to FALSE | `CHECK (quantity > 0)` |

For example, `CHECK (customer_id > 0)` only ensures the ID is positive; it does not ensure a customer with that ID exists. To enforce the relationship between orders and customers, use a foreign key.

`CHECK` also does not enforce uniqueness. `CHECK (email <> '')` only checks that email is non-empty; to prevent duplicate emails, you need `UNIQUE`. When a rule requires data across multiple rows or multiple tables, consider foreign keys, unique indexes, transactions, or appropriate business logic.

## 9. Declaring ENFORCED and NOT ENFORCED

Since MySQL 8.0.16, constraints can explicitly declare their enforcement state:

```sql
CREATE TABLE shipment_rules (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    weight_kg DECIMAL(8, 3) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT chk_shipment_weight_positive
        CHECK (weight_kg > 0) ENFORCED
) ENGINE=InnoDB;
```

`ENFORCED` is the default state, so the keyword can be omitted. When declared `NOT ENFORCED`, the constraint is stored in the schema, but MySQL does not validate it on data writes:

```sql
ALTER TABLE shipment_rules
ADD CONSTRAINT chk_shipment_weight_reasonable
CHECK (weight_kg <= 5000) NOT ENFORCED;
```

`NOT ENFORCED` can be helpful during migration preparation or to document a rule that cannot be turned on immediately. However, it does not protect data. Applications and operational workflows must treat this constraint as inactive until switched to `ENFORCED`.

You can toggle constraint state on supported MySQL versions:

```sql
ALTER TABLE shipment_rules
ALTER CHECK chk_shipment_weight_reasonable ENFORCED;
```

Or temporarily disable enforcement:

```sql
ALTER TABLE shipment_rules
ALTER CHECK chk_shipment_weight_reasonable NOT ENFORCED;
```

Do not disable constraints solely for fast data imports without a plan to validate and re-enable them. While `NOT ENFORCED`, write statements can introduce violating data into the table.

## 10. Adding CHECK to Tables with Existing Data

Before adding an enforced constraint, inspect existing data. For example, when adding `CHECK (price >= 0)` to a products table:

```sql
SELECT id, price
FROM catalog_products
WHERE (price >= 0) IS FALSE;
```

`IS FALSE` finds rows where the expression strictly evaluates to FALSE. Rows with `price IS NULL` yield `UNKNOWN` and will not be rejected by `CHECK` for this condition alone; if the column must have a value, check separately:

```sql
SELECT id
FROM catalog_products
WHERE price IS NULL;
```

After resolving violating rows, add the constraint:

```sql
ALTER TABLE catalog_products
ADD CONSTRAINT chk_catalog_products_price_nonnegative
CHECK (price >= 0) ENFORCED;
```

If existing data still contains violating rows, adding an enforced constraint will fail. On large tables, evaluate the data-validation scan cost, DDL duration, metadata locks, and workload impact on the exact MySQL version. Test on staging with production-like data sizes.

## 11. Renaming, Disabling, Enabling, and Dropping CHECK

Inspect DDL before altering:

```sql
SHOW CREATE TABLE catalog_products\G
```

Toggle enforcement status:

```sql
ALTER TABLE catalog_products
ALTER CHECK chk_catalog_products_price_nonnegative NOT ENFORCED;

ALTER TABLE catalog_products
ALTER CHECK chk_catalog_products_price_nonnegative ENFORCED;
```

Drop a constraint when the rule no longer applies:

```sql
ALTER TABLE catalog_products
DROP CHECK chk_catalog_products_price_nonnegative;
```

Constraint names should be managed through migrations so environments share identical schemas. Before dropping, confirm applications or pipelines no longer rely on that rule. If a rule changes, it is usually better to add a new constraint or update DDL via controlled migrations rather than making manual edits per environment.

## 12. Inspecting CHECK Status via Metadata

`SHOW CREATE TABLE` reveals constraints in the table definition and displays `NOT ENFORCED` status:

```sql
SHOW CREATE TABLE catalog_products\G
```

On MySQL 8.0.16 and later, you can query `INFORMATION_SCHEMA.TABLE_CONSTRAINTS` to inspect constraint types and enforcement status:

```sql
SELECT
    TABLE_NAME,
    CONSTRAINT_NAME,
    CONSTRAINT_TYPE,
    ENFORCED
FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA = DATABASE()
  AND CONSTRAINT_TYPE = 'CHECK'
ORDER BY TABLE_NAME, CONSTRAINT_NAME;
```

To inspect the expression of each constraint, join with `INFORMATION_SCHEMA.CHECK_CONSTRAINTS`:

```sql
SELECT
    tc.TABLE_NAME,
    tc.CONSTRAINT_NAME,
    tc.ENFORCED,
    cc.CHECK_CLAUSE
FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS AS tc
JOIN INFORMATION_SCHEMA.CHECK_CONSTRAINTS AS cc
  ON cc.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA
 AND cc.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
WHERE tc.CONSTRAINT_SCHEMA = DATABASE()
  AND tc.CONSTRAINT_TYPE = 'CHECK'
ORDER BY tc.TABLE_NAME, tc.CONSTRAINT_NAME;
```

These metadata columns are version-dependent. On older MySQL releases prior to 8.0.16, do not rely on `ENFORCED` to infer enforcement because CHECKs were not enforced. Use `SELECT VERSION()` and test actual runtime behavior.

## 13. Differences When Deploying Across Multiple Versions

In environments spanning development, staging, production, replicas, or multiple database clusters, not every server necessarily runs the exact same version. This creates risks when deploying CHECK constraints:

1. A migration creating `CHECK` may succeed on an older server while the constraint is silently ignored.
2. A newer server may reject data that legacy applications previously wrote without errors.
3. An older replica may not enforce CHECK even though the newer source does.
4. Environments have identical DDL yet exhibit different data behavior if versions are inconsistent.

Before enabling constraints, inventory the versions of every node that might accept writes, including primaries, promotable replicas, reporting environments that write data, and ETL/import jobs. Never assume a read-only replica can ignore version differences if it could be promoted to primary.

If the system still contains pre-8.0.16 servers, rely on application validation and other appropriate mechanisms until the entire write path supports enforcement. During mixed-version upgrades, do not rely on CHECK as the sole line of defense.

## 14. Safe CHECK Rollout Process

For tables with existing data and active applications, you can roll out in stages:

1. **Verify versions:** audit every server that can accept writes and confirm CHECK enforcement support.
2. **Define the rule:** clearly specify the value domain, nullability, and business exceptions.
3. **Audit existing data:** run queries to find violating rows; handle `NULL` separately because CHECK accepts `UNKNOWN`.
4. **Clean up data:** fix or quarantine invalid records per business rules, keeping an audit trail of changes.
5. **Deploy application compatibility:** ensure applications handle constraint errors and stop sending invalid data.
6. **Add the constraint:** add it as `ENFORCED`, or use `NOT ENFORCED` during preparation if needed.
7. **Enable enforcement:** if created `NOT ENFORCED`, verify data and switch to `ENFORCED`.
8. **Positive/negative testing:** verify valid data is accepted and violating data is rejected.
9. **Check metadata:** compare `SHOW CREATE TABLE` and `INFORMATION_SCHEMA` across every environment.
10. **Monitor applications:** watch CHECK errors, import logs, and rejected write counts after release.

If rollback is needed, clarify whether disabling or dropping the constraint allows invalid data to return. Rolling back DDL does not automatically restore values modified during the data cleanup step.

## 15. Handling CHECK Errors in Applications

When a write operation violates an enforced constraint, MySQL rejects the operation and returns an error. In MySQL 8.x, the standard error code is `3819` and the message names the violated constraint.

Applications should:

- Distinguish constraint errors from network errors, timeouts, or server errors.
- Return a clear business-friendly message, such as "Quantity must be greater than 0".
- Never expose raw SQL or internal database details to end users.
- Log the constraint name and necessary context without logging unnecessary sensitive data.
- Never infinitely retry invalid values; retries help transient errors, not deterministic data violations.

UI validation remains useful for early feedback. Database CHECK constraints provide the final line of defense for local rules, ensuring different clients abide by the same conditions.

## 16. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| MySQL 5.7 accepts CHECK so data is protected | Prior to 8.0.16, CHECK is accepted by the parser but ignored |
| CHECK only evaluates to TRUE or FALSE | Expressions can return UNKNOWN due to `NULL`; UNKNOWN is accepted |
| `CHECK (quantity > 0)` prevents NULL | No; you must add `NOT NULL` if NULL is invalid |
| CHECK can query another table | CHECK only evaluates expressions on the current row; no subqueries or external table references |
| `NOT ENFORCED` still validates data | No; the constraint is stored but not enforced |
| CHECK guarantees uniqueness or relationship existence | Use `UNIQUE` and `FOREIGN KEY` for those goals |
| Adding CHECK is always an instant DDL | MySQL may need to validate existing data and perform DDL work affecting the table |
| All nodes share the same DDL so behavior is identical | Pre-8.0.16 nodes do not enforce CHECK; align versions across the write path |

## 17. Hands-on Exercises

1. Create a `products` table with `CHECK (price >= 0)` and `CHECK (stock_quantity >= 0)` on MySQL 8.0.16 or later.
2. Insert a valid value, a negative value, and a `NULL` value; explain the outcome using the three states TRUE/FALSE/UNKNOWN.
3. Add `NOT NULL` to columns that forbid missing values and retry.
4. Create multi-column CHECKs `sale_price <= regular_price` and `starts_on <= ends_on`.
5. Add a `NOT ENFORCED` constraint, write violating data, then try switching to `ENFORCED`; observe how existing data is checked.
6. Query `INFORMATION_SCHEMA.TABLE_CONSTRAINTS` and `CHECK_CONSTRAINTS` to inspect status and expressions.
7. Run the same DDL on a pre-8.0.16 MySQL environment if available; verify that syntax is accepted while violating data is not blocked.
8. Design a CHECK rollout plan for a table with existing data and multiple concurrent writing applications.

## 18. Key Takeaways

A `CHECK` constraint validates expressions on data within a single row during insert or update. An expression returning `FALSE` rejects the operation; `TRUE` and `UNKNOWN` are accepted, so combine with `NOT NULL` if missing values are disallowed.

Version differences are mandatory to remember: MySQL prior to 8.0.16 accepts the syntax but ignores CHECK; starting in 8.0.16, constraints are enforced by default and can toggle between `ENFORCED` and `NOT ENFORCED`. Verify versions on all writable nodes, audit existing data, use metadata to confirm enforcement, and roll out via tested migrations. Use CHECK for local row rules; use `NOT NULL`, `UNIQUE`, `FOREIGN KEY`, and business logic for their respective guarantees.
