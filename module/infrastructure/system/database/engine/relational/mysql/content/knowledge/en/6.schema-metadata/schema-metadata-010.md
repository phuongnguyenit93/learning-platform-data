# Comments, Naming Conventions, and Schema Documentation

A MySQL schema is more than a collection of tables and columns. As a system grows, developers and operators need to understand what data each table stores, what meaning and unit each column has, which queries each index serves, how tables relate to one another, and who owns the data. Comments, naming conventions, and schema documentation answer those questions right during database design and maintenance.

MySQL supports comments as metadata for tables, columns, and indexes. Comments are stored alongside the object definition and can be read back via `SHOW CREATE TABLE` or `INFORMATION_SCHEMA`. Naming conventions establish consistent expression; schema documentation combines DDL, metadata, relationship diagrams, and business descriptions so others can understand, inspect, and change the database safely.

## 1. Why Are Comments and Naming Conventions Needed?

Names like `status`, `type`, `value`, or `code` are often insufficient to explain business meaning. An `orders` table might contain payment status, shipping status, and processing status; if there is only a column named `status`, readers must search through code or ask the schema author to understand the values.

A well-documented schema helps:

- New developers quickly understand the data model and business rules.
- SQL authors know which columns can be filtered, joined, or used as keys.
- Operators recognize critical data during backups, restores, and incident response.
- Analytics teams understand the meaning, units, and boundaries of data.
- Migrations have a solid basis for assessing impacts on applications and reports.

Comments should supplement meaning that object names cannot express clearly on their own. Good names aid quick recognition; comments explain semantics, units, rules, and special cases.

## 2. Distinguishing SQL Comments from Schema Comments

SQL provides comment syntax for readers to understand statements:

```sql
-- Get orders pending processing
SELECT id, customer_id, status
FROM orders
WHERE status = 'pending';

# This is also a single-line comment in MySQL
SELECT COUNT(*) FROM customers;

/* Multi-line comment
   used to explain a SQL snippet */
SELECT id, email
FROM customers;
```

`--`, `#`, and `/* ... */` comments belong to the SQL statement text. They help readers of source code or migrations, but do not become table/column descriptions in schema metadata.

Conversely, the `COMMENT` keyword in DDL stores descriptions on database objects:

```sql
CREATE TABLE customers (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(254) NOT NULL COMMENT 'Email used for login and contact',
    PRIMARY KEY (id)
) ENGINE=InnoDB
  COMMENT='Customer information of the system';
```

These comments are attached to table and column definitions. They can be read back after closing the connection or from any administrative tool with privileges to view metadata.

## 3. Adding Comments to Tables

In `CREATE TABLE`, use the `COMMENT` table option to describe the purpose of the table:

```sql
CREATE TABLE orders (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'pending',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_orders_customer_created_at (customer_id, created_at)
) ENGINE=InnoDB
  COMMENT='Purchase orders created by customers';
```

A table comment should answer concisely: which entity or event the table represents, which business domain the data belongs to, and any key caveats. Do not use a table comment to copy an entire design doc or record transient information such as who is currently on call.

You can update the comment on an existing table:

```sql
ALTER TABLE orders
COMMENT = 'Customer purchase orders and processing status';
```

Changing a comment is a DDL change. Apply it through managed migrations like any other schema change so change history remains reproducible and reviewable.

## 4. Adding Comments to Columns

Column comments explain business meaning, value domains, units, or interpretation rules. Example:

```sql
CREATE TABLE products (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Internal product ID',
    sku VARCHAR(64) NOT NULL COMMENT 'Unique product SKU managed by the business',
    name VARCHAR(200) NOT NULL COMMENT 'Display name of the product',
    price DECIMAL(13, 2) NOT NULL COMMENT 'Selling price in the store currency',
    is_active BOOLEAN NOT NULL DEFAULT TRUE COMMENT 'Indicates whether the product is permitted for sale',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation timestamp',
    PRIMARY KEY (id),
    UNIQUE KEY uq_products_sku (sku)
) ENGINE=InnoDB
  COMMENT='Catalog of products permitted for sale';
```

A good comment for the `price` column should state the currency unit or the rule determining currency if the system supports multiple currencies. If prices are stored in the smallest unit, such as dong or cents, state that clearly to avoid misinterpretation. If prices can be negative for adjustments, refunds, or ledger entries, document that rule as well.

When modifying a column comment via `ALTER TABLE ... MODIFY COLUMN`, redeclare the full data type and all column attributes:

```sql
ALTER TABLE products
MODIFY COLUMN price DECIMAL(13, 2) NOT NULL
COMMENT 'Selling price, denominated in VND';
```

Do not omit `NOT NULL`, `DEFAULT`, `UNSIGNED`, `AUTO_INCREMENT`, or other existing attributes when using `MODIFY COLUMN`. The statement above is appropriate only if the current definition is indeed `DECIMAL(13, 2) NOT NULL` with no other attributes to preserve.

## 5. Index Comments and Comment Limitations

MySQL allows attaching a comment to an index to explain the index's purpose:

```sql
CREATE TABLE orders (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(24) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    KEY idx_orders_customer_created_at (customer_id, created_at)
        COMMENT 'Supports order history by customer and time'
) ENGINE=InnoDB
  COMMENT='Customer purchase orders';
```

An index comment should explain the workload or query pattern the index supports. However, a comment does not make the optimizer choose an index, nor does it guarantee faster queries. Verify queries and execution plans using `EXPLAIN`.

Not every kind of constraint has an independent comment field like tables or columns. For foreign keys, check constraints, and business rules, give them meaningful names, add notes in migrations or schema documentation, and use metadata to inspect queryable relationships.

## 6. Reading Comments via MySQL Metadata

### 6.1. Viewing table definitions

`SHOW CREATE TABLE` returns the DDL statement MySQL uses to describe the table, including columns, indexes, constraints, engine, and comments:

```sql
SHOW CREATE TABLE orders\G
```

This is a quick way to verify the actual schema on the server, especially when comparing against migrations or DDL files in a repository.

### 6.2. Viewing table comments

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ENGINE,
    TABLE_COMMENT
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_TYPE = 'BASE TABLE'
ORDER BY TABLE_NAME;
```

`TABLE_COMMENT` holds the table's description. `TABLE_TYPE` distinguishes physical base tables from views in metadata results.

### 6.3. Viewing column comments

```sql
SELECT
    TABLE_NAME,
    ORDINAL_POSITION,
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    COLUMN_KEY,
    EXTRA,
    COLUMN_COMMENT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
ORDER BY TABLE_NAME, ORDINAL_POSITION;
```

This query can generate a basic data dictionary. Besides comments, it retrieves data types, `NULL` allowability, default values, key info, and extra attributes.

### 6.4. Viewing index comments

```sql
SELECT
    TABLE_NAME,
    INDEX_NAME,
    NON_UNIQUE,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    INDEX_TYPE,
    INDEX_COMMENT
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX;
```

`SEQ_IN_INDEX` indicates column order within a composite index. This order matters when evaluating whether an index fits a query's filtering and sorting conditions.

## 7. Naming Conventions for Databases, Tables, and Columns

Naming conventions should stay consistent across the entire module. A simple, readable convention for MySQL is lowercase and `snake_case`:

| Object | Suggested convention | Example |
| --- | --- | --- |
| Database/schema | Business domain or application name, lowercase | `commerce` |
| Table | Clear noun, consistently singular or plural | `customers`, `orders`, `order_items` |
| Column | Specific attribute name, `snake_case` | `customer_id`, `created_at` |
| Primary key | Consistent pattern across the whole system | `id` |
| Foreign key | Referenced entity name plus `_id` | `customer_id` |
| Unique index | `uq_<table>_<columns>` | `uq_customers_email` |
| Secondary index | `idx_<table>_<columns>` | `idx_orders_customer_created_at` |
| Foreign key | `fk_<child_table>_<parent_table>` | `fk_orders_customers` |
| Check constraint | `chk_<table>_<rule>` | `chk_products_price_nonnegative` |

Teams can adapt these conventions. What matters is applying the same rule consistently, ensuring names accurately reflect function, and avoiding naming collisions across objects.

### 7.1. Choosing singular or plural for table names

Either style works:

- Plural: `customers`, `orders`, `order_items`.
- Singular: `customer`, `order`, `order_item`.

There is no mandatory choice for every project. Pick one style as the standard and do not mix them arbitrarily. For example, if tables are plural, use `products`, `categories`, `payments` instead of suddenly adding a singular `invoice` table without reason.

### 7.2. Naming columns with clear semantics

Prefer `created_at` over `date`, `unit_price` over `price2`, and `payment_status` over `status` when a table has multiple statuses. For foreign keys, the column name should indicate the target entity, such as `customer_id` or `warehouse_id`.

For booleans, prefixes like `is_`, `has_`, or `can_` work well, such as `is_active`, `has_discount`, `can_refund`. For temporal values, standardize suffixes such as `_at` for timestamps, `_date` for dates without time, and `_time` for time of day. If storing timestamps in UTC, state that convention explicitly in documentation or comments whenever readers cannot deduce it from the system.

Do not encode data types into column names such as `str_customer_name` or `int_quantity`; types can change in the future and that information already lives in metadata. Avoid obscure internal abbreviations, overly generic names, and names easily confused with SQL keywords.

### 7.3. Naming indexes and constraints

An index name should indicate the table and main columns in the index's exact order. Example:

```sql
CREATE INDEX idx_orders_customer_status_created_at
ON orders (customer_id, status, created_at);
```

The name `idx_orders_customer_status_created_at` conveys a composite index on `customer_id`, `status`, `created_at`. The name does not substitute for understanding the leftmost prefix of a composite index; the leading column and column ordering still determine which query shapes can leverage the index.

Constraints should have stable names to make error messages readable and migrations easier to manage:

```sql
CREATE TABLE order_items (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    unit_price DECIMAL(13, 2) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT fk_order_items_orders
        FOREIGN KEY (order_id) REFERENCES orders (id),
    CONSTRAINT chk_order_items_quantity_positive
        CHECK (quantity > 0)
) ENGINE=InnoDB;
```

In MySQL, index names must be unique within a table; foreign key constraint names should be unique within a schema to avoid conflicts and simplify management across versions. Constraint names do not need to repeat an entire business rule sentence; keep them short, stable, and identifiable.

### 7.4. Avoiding operationally troublesome names

- Avoid using SQL keywords or function names as identifiers unless necessary; constantly quoting with backticks makes SQL harder to read.
- Avoid distinguishing names solely by uppercase/lowercase because database/table name behavior can vary by OS and `lower_case_table_names`.
- Avoid overly long names, hard-to-type names, or names embedding changing details like application version numbers.
- Avoid abbreviations understood by only one person on the team.
- Keep names stable; renaming columns/tables can affect code, migrations, views, triggers, reports, and data pipelines.

MySQL enforces identifier length limits per object type; many common object names such as databases, tables, columns, and indexes have a 64-character limit. Verify the specific limit for each object type and MySQL version when designing naming conventions.

## 8. Documenting Schemas Across Multiple Layers

In-database comments are helpful, but they cannot replace full design documentation. Combine the following layers:

| Documentation layer | Recommended content | Where maintained |
| --- | --- | --- |
| DDL/migrations | Table, column, index, constraint structures and changes over time | Repository and migration tools |
| Comment metadata | Short descriptions for tables, columns, and indexes | MySQL schema |
| Data dictionary | Column meaning, data type, units, nullability, defaults, data source | Project docs or data catalog |
| ERD | Entity relationships, cardinality, and keys | Architecture docs |
| Business rules | Status lifecycles, calculation formulas, retention rules | Business/domain docs |
| Operations and governance | Owner, data classification, retention, backup, SLA | Operations runbooks/catalogs |

DDL and migrations should be the source of truth capable of reproducing the schema. Explanatory docs help humans understand the design; if docs and DDL drift apart, identify the authoritative source and update the rest.

## 9. Generating a Data Dictionary from INFORMATION_SCHEMA

You can combine table and column metadata to produce a data catalog:

```sql
SELECT
    t.TABLE_NAME,
    t.TABLE_COMMENT,
    c.ORDINAL_POSITION,
    c.COLUMN_NAME,
    c.COLUMN_TYPE,
    c.IS_NULLABLE,
    c.COLUMN_DEFAULT,
    c.COLUMN_KEY,
    c.EXTRA,
    c.COLUMN_COMMENT
FROM INFORMATION_SCHEMA.TABLES AS t
JOIN INFORMATION_SCHEMA.COLUMNS AS c
  ON c.TABLE_SCHEMA = t.TABLE_SCHEMA
 AND c.TABLE_NAME = t.TABLE_NAME
WHERE t.TABLE_SCHEMA = DATABASE()
  AND t.TABLE_TYPE = 'BASE TABLE'
ORDER BY t.TABLE_NAME, c.ORDINAL_POSITION;
```

This query produces one row per column, accompanied by the table comment and column comment. You can export the output to CSV or feed it into an automated documentation pipeline. The runner must have privileges to view metadata for the relevant objects.

To document keys and relationships, you can query `TABLE_CONSTRAINTS` and `KEY_COLUMN_USAGE`:

```sql
SELECT
    tc.TABLE_NAME,
    tc.CONSTRAINT_NAME,
    tc.CONSTRAINT_TYPE,
    kcu.COLUMN_NAME,
    kcu.ORDINAL_POSITION,
    kcu.REFERENCED_TABLE_NAME,
    kcu.REFERENCED_COLUMN_NAME
FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS AS tc
LEFT JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE AS kcu
  ON kcu.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA
 AND kcu.TABLE_NAME = tc.TABLE_NAME
 AND kcu.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
WHERE tc.CONSTRAINT_SCHEMA = DATABASE()
ORDER BY tc.TABLE_NAME, tc.CONSTRAINT_NAME, kcu.ORDINAL_POSITION;
```

The results help identify primary keys, unique constraints, foreign keys, and referenced columns. For check constraints, you can additionally query `INFORMATION_SCHEMA.CHECK_CONSTRAINTS` and `TABLE_CONSTRAINTS` on supported versions to retrieve check expressions.

## 10. Principles for Writing Good Comments

Comments should be concise yet provide enough context for others to understand without guessing:

1. Explain business meaning rather than repeating the column name verbatim.
2. Specify units of measurement, currency, time zone, or code conventions whenever easily misunderstood.
3. Describe value domains, the meaning of `NULL`, default values, and special states when needed.
4. For indexes, explain the query pattern or reason for existence; avoid claiming performance gains without measuring.
5. Use consistent language across the entire schema, preferring short and concrete sentences.
6. Update comments alongside migrations whenever semantics or data types change.
7. Never include passwords, tokens, real personal data, or sensitive information in comments.

Weak examples:

```sql
email VARCHAR(254) COMMENT 'Email';
price DECIMAL(13, 2) COMMENT 'Price';
status VARCHAR(20) COMMENT 'Status';
```

Clearer examples:

```sql
email VARCHAR(254)
    COMMENT 'Email address used for login and receiving notifications';
price DECIMAL(13, 2)
    COMMENT 'Listed price, denominated in VND, excluding shipping fee';
status VARCHAR(20)
    COMMENT 'Payment status: pending, paid, failed, or refunded';
```

Example comments must match the application's actual rules. If status values can change or expand, maintain the value catalog in business docs or an appropriate lookup table rather than letting comments become stale lists.

## 11. Workflow for Maintaining Documentation as Schemas Evolve

Every schema change should be accompanied by updates to related documentation:

1. Create a reviewable, repeatable migration following project workflows.
2. Update DDL, table/column/index comments, and constraints if semantics change.
3. Assess impact on applications, reports, ETL, views, triggers, and data consumers.
4. Update the data dictionary, ERD, and relevant business rules.
5. Run the migration in a test environment and verify metadata via `SHOW CREATE TABLE`/`INFORMATION_SCHEMA`.
6. Review naming conventions, identifier lengths, compatibility, and backward compatibility.
7. Deploy through the release pipeline; record the schema version and updated documentation.

Do not manually edit a schema in production and forget to update migrations. If an emergency change occurs, create a corresponding reconciliation migration and update documentation immediately once the system stabilizes.

## 12. Hands-On Exercises

1. Create a `customers` table with a table comment and at least three column comments explaining semantics.
2. Create an `orders` table with clear column names, a named foreign key, and a composite index with a comment.
3. Use `SHOW CREATE TABLE` to read back the comments and actual structure.
4. Query `INFORMATION_SCHEMA.TABLES`, `COLUMNS`, and `STATISTICS` to build a simple data dictionary.
5. Query `TABLE_CONSTRAINTS` and `KEY_COLUMN_USAGE` to list relationships between tables.
6. Pick a table in a lab schema and rewrite generic column names such as `status`, `type`, and `value` into clearer names; explain the impact of renaming on applications.
7. Create a migration that only changes a comment and verify that migration history reflects that change.
8. Sketch a small ERD for `customers`, `orders`, and `order_items`, then cross-check the ERD against MySQL metadata.

## 13. Key Takeaways

Comments in SQL (`--`, `#`, `/* ... */`) annotate statements only; `COMMENT` in DDL stores metadata for a table, column, or index. Descriptions can be read back via `SHOW CREATE TABLE` and the `TABLE_COMMENT`, `COLUMN_COMMENT`, and `INDEX_COMMENT` columns in `INFORMATION_SCHEMA`.

Apply consistent naming conventions in lowercase and `snake_case`, using meaningful names for tables, columns, keys, indexes, and constraints. Schema documentation should combine DDL/migrations, comment metadata, a data dictionary, ERDs, business rules, and operations runbooks. Whenever a schema changes, update documentation alongside the migration and re-verify metadata in MySQL so documentation always reflects the real structure.
