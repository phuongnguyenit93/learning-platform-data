# Looking Up Columns, Default Values, Constraints, and Generated Columns

When taking over a MySQL schema, you need to know which columns each table has, what their data types are, which columns allow `NULL`, what the default values are, and which constraints protect the data. For tables with generated columns, you also need to know which expression computes the column and whether it is stored or computed on read.

MySQL provides commands such as `DESCRIBE`, `SHOW FULL COLUMNS`, `SHOW CREATE TABLE`, and views in `INFORMATION_SCHEMA` to look up metadata. Knowing how to pick the right source helps you inspect structure, write migrations, craft queries, and diagnose data errors without guessing from column names.

## 1. Table and Column Metadata in MySQL

In MySQL, `schema` and `database` are used almost synonymously when referring to the namespace containing tables, views, and related objects. Metadata is data describing the structure and properties of those objects.

A column's metadata can tell you:

- The column name and its position in the table.
- Full data type, length, precision, scale, charset, and collation.
- Whether the column allows `NULL`.
- Default value and auto-update behavior.
- Whether the column belongs to a primary key, unique index, or another index.
- Whether the column is `AUTO_INCREMENT`, invisible, or a generated column.
- The expression producing a generated column and whether it is `VIRTUAL` or `STORED`.
- Any comment recorded in the column definition.

Constraint metadata can reveal the constraint name, constraint type, participating columns, referenced table/columns, and `ON UPDATE` or `ON DELETE` rules for foreign keys.

Starting in MySQL 8.0, the data dictionary is managed inside MySQL Server, and supported SQL interfaces such as `INFORMATION_SCHEMA`, `SHOW`, and `DESCRIBE` are the proper ways to read metadata. Do not directly query or modify internal data dictionary structures.

## 2. Quickly Exploring Table Structure

Suppose a sales application has schema `shop` and table `order_items`. Some commonly used commands:

```sql
-- List columns and basic data types.
DESCRIBE shop.order_items;

-- Display collation, comments, and fuller details.
SHOW FULL COLUMNS FROM shop.order_items;

-- View the complete DDL that MySQL stores for the table.
SHOW CREATE TABLE shop.order_items\G

-- View indexes.
SHOW INDEX FROM shop.order_items;
```

`DESCRIBE` (or `DESC`) is handy for quickly viewing column names, types, `NULL`, keys, defaults, and `Extra`. `SHOW FULL COLUMNS` adds details such as collation, privileges, and comments. `SHOW CREATE TABLE` is usually the clearest way to verify the actual DDL, including constraints, generated expressions, engine, charset, and table options.

Do not confuse `COLUMN_KEY` or the `Key` column in `DESCRIBE` output with the complete set of constraints. Those fields primarily summarize a column's index role; to see full composite keys, foreign keys, and `CHECK` constraints, read the DDL or the corresponding metadata views.

## 3. Looking Up Columns via INFORMATION_SCHEMA.COLUMNS

`INFORMATION_SCHEMA.COLUMNS` contains one row for each column in tables and views visible to the current account.

### 3.1. Listing columns of a table

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ORDINAL_POSITION,
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    COLUMN_KEY,
    EXTRA,
    GENERATION_EXPRESSION,
    COLUMN_COMMENT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'shop'
  AND TABLE_NAME = 'order_items'
ORDER BY ORDINAL_POSITION;
```

Important metadata fields:

| Field | Meaning |
|---|---|
| `TABLE_SCHEMA`, `TABLE_NAME` | Schema and table containing the column |
| `ORDINAL_POSITION` | Column position in the table definition, starting at 1 |
| `COLUMN_NAME` | Column name |
| `DATA_TYPE` | Base data type, e.g., `int`, `varchar`, `decimal` |
| `COLUMN_TYPE` | Fuller type, which may include length, `unsigned`, or `enum` values |
| `IS_NULLABLE` | `YES` if `NULL` is allowed, `NO` otherwise |
| `COLUMN_DEFAULT` | Default value displayed by metadata; may be `NULL` |
| `COLUMN_KEY` | Summary of key/index role such as `PRI`, `UNI`, `MUL` |
| `EXTRA` | Additional attributes such as `auto_increment`, `on update`, `VIRTUAL GENERATED`, or `STORED GENERATED` |
| `GENERATION_EXPRESSION` | Expression used to compute a generated column; empty for regular columns |
| `COLUMN_COMMENT` | Column comment |

`COLUMN_TYPE` is more informative than `DATA_TYPE` when you need to know `BIGINT UNSIGNED`, `DECIMAL(12,2)`, or the list of `ENUM` values. For string columns, also check `CHARACTER_MAXIMUM_LENGTH`, `CHARACTER_SET_NAME`, and `COLLATION_NAME`; for numeric/date-time types, check `NUMERIC_PRECISION`, `NUMERIC_SCALE`, and `DATETIME_PRECISION`.

### 3.2. Finding a column across an entire schema

Example finding columns whose names contain `price` in schema `shop`:

```sql
SELECT
    TABLE_NAME,
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'shop'
  AND COLUMN_NAME LIKE '%price%'
ORDER BY TABLE_NAME, ORDINAL_POSITION;
```

This query is useful when finding where prices are stored or identifying which tables a change will impact. Filter by `TABLE_SCHEMA` to avoid mixing metadata from different schemas.

### 3.3. Metadata visibility privileges

Metadata views only display objects that the account has privilege to see under MySQL's rules. If a table does not appear in the results, the schema/table name may be wrong or the account may lack privileges to see that object. When investigating production, use a metadata-reading account granted appropriate privileges rather than defaulting to `root`.

## 4. Looking Up Default Values

A default value is used when an `INSERT` statement omits a value for a column, or when a statement explicitly specifies `DEFAULT`. It establishes the initial state of a row.

Example:

```sql
CREATE TABLE orders (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    status VARCHAR(20) NOT NULL DEFAULT 'NEW',
    note VARCHAR(500) NULL DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
) ENGINE=InnoDB;
```

In this example:

- `status` receives `'NEW'` if `INSERT` omits this column.
- `note` allows `NULL` and has an explicit default of `NULL`.
- `created_at` is assigned the row creation timestamp if no value is provided.
- `updated_at` is initialized to the current timestamp and automatically updates according to `ON UPDATE CURRENT_TIMESTAMP` rules when the row changes under MySQL's conditions.
- `id` is assigned an auto-increment value.

### 4.1. Distinguishing column omission, DEFAULT, and NULL

The following three forms are not completely identical:

```sql
-- Omit the status column: MySQL uses the column's default.
INSERT INTO orders (note) VALUES ('Call before delivery');

-- Explicitly request the default.
INSERT INTO orders (status, note) VALUES (DEFAULT, 'Deliver during business hours');

-- Assign NULL explicitly: do not use the default.
INSERT INTO orders (status, note) VALUES ('NEW', NULL);
```

If the column allows `NULL`, `NULL` is stored as an absent value in SQL semantics. If the column is `NOT NULL`, passing `NULL` typically raises an error. The default value is only used when the column is omitted or explicitly specified as `DEFAULT`.

If a `NOT NULL` column declares no default and is omitted during `INSERT`, the outcome also depends on SQL mode. In strict mode, MySQL typically rejects the missing value; in non-strict mode, MySQL may use an implicit default based on the data type and emit a warning. Do not rely on non-strict behavior to mask application omissions.

Check the SQL mode:

```sql
SELECT @@SESSION.sql_mode, @@GLOBAL.sql_mode;
```

### 4.2. Reading defaults from metadata

```sql
SELECT
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    EXTRA
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'shop'
  AND TABLE_NAME = 'orders'
ORDER BY ORDINAL_POSITION;
```

Important note: `COLUMN_DEFAULT` can be `NULL` when a column is declared `DEFAULT NULL`, and it can also be `NULL` when there is no `DEFAULT` clause at all. Therefore, looking at `COLUMN_DEFAULT` alone is not enough to distinguish these two cases. Check `SHOW CREATE TABLE` to confirm the underlying DDL.

When the default is an expression or function, how it is represented in metadata can vary by version. `SHOW CREATE TABLE` is the source to cross-check when you need the exact expression, such as temporal defaults or default expressions supported in a specific MySQL version.

### 4.3. Distinguishing DEFAULT from ON UPDATE

`DEFAULT CURRENT_TIMESTAMP` defines the initial value when creating a row. `ON UPDATE CURRENT_TIMESTAMP` specifies automatic updating of the timestamp column when the row changes and satisfies MySQL's conditions. These are two distinct behaviors; inspect `EXTRA` in metadata and the DDL in `SHOW CREATE TABLE` to recognize both completely.

## 5. Looking Up Table Constraints

Constraints are rules declared to protect data validity and relationships. MySQL commonly uses the following types:

| Type | Purpose | Example |
|---|---|---|
| `PRIMARY KEY` | Uniquely identifies each row and disallows NULL | `PRIMARY KEY (id)` |
| `UNIQUE` | Disallows duplicate key values | `UNIQUE KEY uq_email (email)` |
| `FOREIGN KEY` | Enforces referential relationships between child and parent tables | `FOREIGN KEY (product_id) REFERENCES products(id)` |
| `CHECK` | Validates a conditional expression on rows | `CHECK (quantity > 0)` |
| `NOT NULL` | Prevents a column from accepting NULL | `quantity INT NOT NULL` |

`NOT NULL` is declared as a column attribute and inspected via `IS_NULLABLE`; it does not always appear as a separate row in `INFORMATION_SCHEMA.TABLE_CONSTRAINTS`. Default values are also column attributes, not constraints.

### 5.1. Listing constraints with TABLE_CONSTRAINTS

```sql
SELECT
    CONSTRAINT_SCHEMA,
    TABLE_NAME,
    CONSTRAINT_NAME,
    CONSTRAINT_TYPE
FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
WHERE TABLE_SCHEMA = 'shop'
  AND TABLE_NAME = 'order_items'
ORDER BY CONSTRAINT_TYPE, CONSTRAINT_NAME;
```

`CONSTRAINT_TYPE` typically returns `PRIMARY KEY`, `UNIQUE`, `FOREIGN KEY`, or `CHECK`. The result shows the type and name of each constraint, but to know which columns participate and column order in composite keys, combine it with `KEY_COLUMN_USAGE`.

### 5.2. Looking up participating key columns and foreign keys

```sql
SELECT
    CONSTRAINT_NAME,
    COLUMN_NAME,
    ORDINAL_POSITION,
    REFERENCED_TABLE_SCHEMA,
    REFERENCED_TABLE_NAME,
    REFERENCED_COLUMN_NAME
FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA = 'shop'
  AND TABLE_NAME = 'order_items'
ORDER BY CONSTRAINT_NAME, ORDINAL_POSITION;
```

For composite keys, `ORDINAL_POSITION` shows the column order within the constraint. The `REFERENCED_...` fields are populated for foreign keys; they indicate the referenced schema, table, and column.

### 5.3. Looking up ON DELETE and ON UPDATE behavior

```sql
SELECT
    CONSTRAINT_NAME,
    TABLE_NAME,
    REFERENCED_TABLE_NAME,
    UPDATE_RULE,
    DELETE_RULE
FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA = 'shop'
  AND TABLE_NAME = 'order_items';
```

Common rules include `RESTRICT`, `CASCADE`, `SET NULL`, and `NO ACTION`. Check the column definition as well: `SET NULL` is valid only when the foreign key column allows `NULL`. Do not pick `CASCADE` just to avoid delete errors; clarify parent-child data lifecycle rules according to business logic.

### 5.4. Looking up CHECK constraints

In MySQL 8.0.16 and later, `CHECK` constraints are enforced. You can read their expressions using `INFORMATION_SCHEMA.CHECK_CONSTRAINTS`:

```sql
SELECT
    tc.TABLE_NAME,
    tc.CONSTRAINT_NAME,
    cc.CHECK_CLAUSE
FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS AS tc
JOIN INFORMATION_SCHEMA.CHECK_CONSTRAINTS AS cc
  ON cc.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA
 AND cc.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
WHERE tc.TABLE_SCHEMA = 'shop'
  AND tc.TABLE_NAME = 'order_items'
  AND tc.CONSTRAINT_TYPE = 'CHECK';
```

In MySQL versions older than 8.0.16, `CHECK` syntax could be accepted by the parser without enforcing the constraint as newer versions do. When upgrading or investigating an older schema, confirm the server version and inspect the actual DDL; do not assume a `CHECK` constraint written in a migration file means the server is enforcing it.

## 6. What Is a Generated Column?

A generated column is a column whose value MySQL computes from an expression based on other columns in the same row. Applications do not directly dictate this column's value on `INSERT` or `UPDATE`; MySQL computes it from the declared expression.

For example, each order line item has a quantity and unit price. The line total can be computed automatically:

```sql
CREATE TABLE order_items (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    unit_price DECIMAL(10,2) NOT NULL,
    line_total DECIMAL(20,2)
        GENERATED ALWAYS AS (quantity * unit_price) STORED,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_order_id (order_id),
    CHECK (quantity > 0),
    CHECK (unit_price >= 0)
) ENGINE=InnoDB;
```

In this example, `line_total` is computed from `quantity * unit_price`. When inserting a row, the application only passes quantity and unit price:

```sql
INSERT INTO order_items (order_id, product_id, quantity, unit_price)
VALUES (9001, 42, 2, 125000.00);

SELECT quantity, unit_price, line_total
FROM order_items
WHERE order_id = 9001;
```

The `line_total` value is computed by MySQL. Do not pass an arbitrary value into a generated column; in write statements, a generated column may only be assigned `DEFAULT` per MySQL syntax.

### 6.1. VIRTUAL and STORED

MySQL supports two kinds of generated columns:

| Kind | Storage behavior | Characteristics |
|---|---|---|
| `VIRTUAL` | Value is not stored in row data; expression is evaluated when the value is read | Saves row storage space, though reads may need to evaluate the expression |
| `STORED` | Value is evaluated when inserting/updating the row and stored in the table | Consumes more storage space, though reading the value does not re-evaluate the expression from source columns |

If the kind is not specified, a generated column defaults to `VIRTUAL`. Both kinds can be indexed where MySQL supports it. With InnoDB, a secondary index on a virtual generated column stores the computed index values, so the index still carries storage and update overhead even though the value is not stored in the row data.

### 6.2. When should you use a generated column?

- When a value is always derived from data in the same row and should not be written inconsistently by applications.
- When you want to name a computed expression to make queries easier to read.
- When you want to index an eligible expression rather than repeating the expression across many queries.
- When you need to normalize part of the data, such as extracting a domain from an email or building a search key from a source column, provided the expression is supported and deterministic.

A generated column does not replace a regular column storing user-entered business data. If a value must be preserved as of the transaction time even when source columns might change later, store a snapshot in a regular column rather than recomputing automatically.

### 6.3. Expression limitations

A generated column expression must follow MySQL's restrictions. It can generally reference only columns in the same row and cannot use subqueries, variables, or non-deterministic functions prohibited by MySQL in generated expressions. You cannot use a generated column to read another table or call an external service.

If an expression depends on the current time like `NOW()` or depends on data outside the row, it is usually not suitable for a generated column. Use a regular column updated by the application or a separate aggregation workflow.

## 7. Looking Up Generated Columns in Metadata

### 7.1. Finding all generated columns in a schema

```sql
SELECT
    TABLE_NAME,
    COLUMN_NAME,
    COLUMN_TYPE,
    EXTRA,
    GENERATION_EXPRESSION
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'shop'
  AND GENERATION_EXPRESSION <> ''
ORDER BY TABLE_NAME, ORDINAL_POSITION;
```

`GENERATION_EXPRESSION` shows the computation expression. `EXTRA` typically shows `VIRTUAL GENERATED` or `STORED GENERATED`. Check `SHOW CREATE TABLE` to inspect the full type, nullability, indexes, and other properties.

### 7.2. Viewing the definition of a generated column

```sql
SHOW CREATE TABLE shop.order_items\G
```

The output may include a definition similar to:

```sql
`line_total` decimal(20,2)
  GENERATED ALWAYS AS ((`quantity` * `unit_price`)) STORED
```

This is the way to verify both the expression and storage type. The `EXTRA` metadata field only indicates the additional status; it is not enough to reconstruct the expression.

### 7.3. Checking indexes on generated columns

```sql
SHOW INDEX FROM shop.order_items;
```

Compare `Column_name`, `Key_name`, and column order in the index. If a query filters on a generated column without a suitable index, MySQL may have to compute the expression across many rows. However, adding an index also increases write cost and storage usage; check the execution plan before deciding.

## 8. A Complete Metadata Lookup Workflow

Suppose you inherit a legacy application and need to understand why the `line_total` column cannot be updated directly, while also verifying whether `status` has a default.

1. **Confirm the exact schema and table:** check `DATABASE()` and use explicit schema names in your commands.
2. **View the full DDL:** run `SHOW CREATE TABLE shop.order_items` to inspect constraints, defaults, generated expressions, and engine.
3. **List column metadata:** query `INFORMATION_SCHEMA.COLUMNS` to see types, nullability, defaults, `EXTRA`, and generation expressions.
4. **Identify constraints:** query `TABLE_CONSTRAINTS` and `KEY_COLUMN_USAGE`; for `CHECK`, inspect `CHECK_CONSTRAINTS` if supported by the version.
5. **Cross-check indexes:** use `SHOW INDEX` to see which columns are indexed and their order in composite indexes.
6. **Verify actual behavior:** test `INSERT`/`UPDATE` in a development environment and inspect errors or warnings; never test arbitrary writes on production.
7. **Document findings in migrations/docs:** record version assumptions, constraints, and planned changes so they can be re-verified later.

Example query summarizing key column metadata:

```sql
SELECT
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    COLUMN_KEY,
    EXTRA,
    GENERATION_EXPRESSION
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'shop'
  AND TABLE_NAME = 'order_items'
ORDER BY ORDINAL_POSITION;
```

Then use `SHOW CREATE TABLE` as the final proof of the DDL currently on the server. If migration files in Git differ from the server output, investigate deployment history and schema drift before running the next migration.

## 9. Common Mistakes

- **Using only DESCRIBE to infer the full structure:** this command is handy for quick previews, but it does not replace `SHOW CREATE TABLE` and constraint views.
- **Assuming `COLUMN_DEFAULT IS NULL` guarantees no default:** metadata can return `NULL` for both `DEFAULT NULL` and the absence of a default clause.
- **Confusing `COLUMN_KEY` with the full constraint list:** use `TABLE_CONSTRAINTS`, `KEY_COLUMN_USAGE`, and `SHOW CREATE TABLE`.
- **Assuming every CHECK is enforced:** MySQL prior to 8.0.16 does not enforce `CHECK` like newer versions do.
- **Writing values directly into a generated column:** values must be computed from the expression; applications should write to the source columns.
- **Assuming VIRTUAL never consumes index storage:** a secondary index on a virtual generated column still stores index keys.
- **Failing to check metadata privileges:** missing objects in results may occur because the account lacks visibility privileges.
- **Editing internal metadata:** the data dictionary must be managed via DDL and supported SQL interfaces; never manually alter system structures.

## 10. Column and Constraint Inspection Checklist

- Have I confirmed the right `TABLE_SCHEMA` and `TABLE_NAME`?
- Have I checked `SHOW CREATE TABLE` for the actual DDL?
- Do the full data types, nullability, charset, and collation match requirements?
- Does the column have a default? Does `COLUMN_DEFAULT` need cross-checking due to ambiguous `NULL`?
- Are `DEFAULT` and `ON UPDATE` clearly distinguished?
- Which constraints exist, which columns participate, and what is the column order of composite keys?
- Which table/column does each foreign key reference, and which delete/update rules does it use?
- Are `CHECK` constraints enforced by the current MySQL version?
- Is a generated column `VIRTUAL` or `STORED`, what is its expression, and is it indexed?
- Does the current account have sufficient privileges to see the metadata being queried?

## Conclusion

`DESCRIBE`, `SHOW FULL COLUMNS`, and `SHOW CREATE TABLE` enable fast structural exploration; `INFORMATION_SCHEMA.COLUMNS` provides detailed metadata on types, nullability, defaults, and generation expressions; and `TABLE_CONSTRAINTS`, `KEY_COLUMN_USAGE`, `REFERENTIAL_CONSTRAINTS`, and `CHECK_CONSTRAINTS` allow inspecting constraints. When analyzing schemas, combine these sources, pay attention to version differences and metadata privileges, and use actual DDL for verification. Understanding defaults, constraints, and generated columns leads to consistent data design, safe migrations, and fewer structural mistakes in MySQL.
