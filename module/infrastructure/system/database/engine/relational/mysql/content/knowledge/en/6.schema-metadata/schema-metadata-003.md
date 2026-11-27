# Object Names, Backticks, and Reserved Keywords

Database, table, column, index, constraint, and alias names appear in nearly every SQL statement. A name may be character-valid yet fail because it collides with a keyword; the exact same table name can also be handled differently between Windows and Linux due to case-sensitivity rules. MySQL uses backticks to quote identifiers, but quoting must be applied in the right places and is no substitute for good naming conventions.

This lesson belongs to the **DATABASE_MYSQL** module. The module aims to help you master MySQL—from table design, data types, keys, and SQL queries to indexes, transactions, and concurrency control—while practicing reading execution plans, query tuning, privilege management, backups, and troubleshooting relational database operations. In the **Schema and Metadata** chapter, this lesson focuses on how to name objects, use backticks properly, identify reserved keywords, and inspect metadata to avoid errors during development, migrations, and deployment.

## 1. What Is an Identifier?

In SQL, an **identifier** is a name used to identify an object or element in a statement. Common types of identifiers in MySQL include:

| Type | Example | Identifies |
|---|---|---|
| Database / schema | `sales_db` | A database. In MySQL, `SCHEMA` is generally equivalent to `DATABASE`. |
| Table | `customers`, `order_items` | A table or view. |
| Column | `customer_id`, `created_at` | An attribute in a table or view. |
| Index | `idx_orders_created_at` | A structure supporting data access. |
| Constraint | `fk_orders_customer` | A constraint such as a foreign key or CHECK. |
| Alias | `c`, `monthly_total` | A temporary name used within the scope of a query. |
| Stored object | `calculate_tax`, `after_order_insert` | A procedure, function, trigger, or event. |

An identifier differs from a **literal/value**. In `WHERE customer_id = 101`, `customer_id` is a column name while `101` is a value. In `WHERE email = 'an@example.com'`, `email` is an identifier while `'an@example.com'` is a string literal.

```sql
SELECT c.customer_id, c.email
FROM sales_db.customers AS c
WHERE c.customer_id = 101;
```

In the example above:

- `sales_db` is a database name.
- `customers` is a table name.
- `c` is a table alias.
- `customer_id` and `email` are column names.
- `101` is the value being compared.

Distinguishing identifiers from values is critical when writing dynamic SQL, using prepared statements, and preventing SQL injection.

## 2. Identifier Naming Rules

### 2.1. Characters and length limits

MySQL supports both unquoted identifiers and quoted identifiers. Exact character rules depend on the object type and version, but a safe, portable convention across environments is:

- Start with an ASCII letter or an underscore `_`.
- Use letters, digits, and `_` for the remainder.
- Use unaccented ASCII for object names to avoid differences across tools, filesystems, deployment scripts, and terminal environments.
- Do not include spaces, hyphens `-`, dots, or special characters without a clear reason.
- Avoid naming objects after SQL keywords or names easily confused with functions and data types.

Most common object names such as databases, tables, columns, indexes, constraints, and routines have a 64-character limit. Certain other name types have their own limits, so check the rules for the specific object type when generating names automatically or generating schemas via code.

The following names are readable and migration-friendly:

```text
customers
order_items
customer_id
created_at
idx_orders_customer_created_at
fk_order_items_order
```

The names below may require quoting or cause friction across environments:

```text
order-items       -- contains a hyphen
customer email    -- contains a space
select            -- collides with a reserved keyword
TênKháchHàng      -- accented characters, differing across tools and conventions
```

Backticks can make MySQL accept awkward names, but they do not make those names easy to maintain. Prefer renaming to simple identifiers whenever you still control schema design.

### 2.2. Consistent naming conventions

A practical convention for MySQL projects:

| Component | Suggested convention | Example |
|---|---|---|
| Database | `snake_case`, describing the business domain | `sales_db` |
| Table | A consistent singular or plural rule | `customers`, `orders`, `order_items` |
| Column | `snake_case`, expressing meaning | `customer_id`, `created_at` |
| Primary key | `id` or `<entity>_id`, consistent project-wide | `order_id` |
| Foreign key | Same name as the referenced key | `customer_id` |
| Index | Prefix by purpose | `idx_orders_customer_created` |
| Unique key | Prefix `uq_` | `uq_customers_email` |
| Foreign key constraint | Prefix `fk_` | `fk_orders_customer` |
| Check constraint | Prefix `chk_` | `chk_order_items_quantity` |

Consistency matters most. If one module uses `customer_id`, another uses `customerId`, and a third uses `cust_no` for the same concept, joining, reading metadata, and generating code become harder. Standardize rules across schemas and migrations.

Do not cram too much information into a name. For example, `idx_orders_customer_created_at_status_total_amount` may reflect a multi-column index, but the name is overly long and hard to read. Choose a name that is distinct enough and easy to understand; the actual index structure is inspected via metadata.

## 3. What Are Backticks Used For?

### 3.1. Quoting identifiers

MySQL uses backticks `` ` `` to quote identifiers. This allows using names that contain spaces, hyphens, or collide with reserved keywords.

For example, a legacy schema with a table named `order` and a column named `select`:

```sql
CREATE TABLE `order` (
    `order_id` BIGINT UNSIGNED NOT NULL,
    `select`   VARCHAR(100) NOT NULL,
    PRIMARY KEY (`order_id`)
);

INSERT INTO `order` (`order_id`, `select`)
VALUES (1001, 'First order');

SELECT `order_id`, `select`
FROM `order`;
```

Without backticks, `order` and `select` can be interpreted as keywords in SQL context, leading to syntax errors or unintended parsing.

Backticks surround **object names**, not string values. Compare:

```sql
-- Correct: identifiers use backticks, strings use single quotes.
SELECT `customer_id`
FROM `customers`
WHERE `email` = 'an@example.com';

-- Wrong intent: 'customer_id' is a string literal, not a column name.
SELECT 'customer_id'
FROM `customers`;
```

The second statement can still execute, but it returns the literal string `customer_id` for every row instead of the values in the column of that name.

### 3.2. Quoting names with spaces or special characters

Backticks allow quoting an identifier containing characters that an unquoted form does not permit:

```sql
CREATE TABLE `sales-archive` (
    `row id` BIGINT NOT NULL,
    `net amount` DECIMAL(12, 2) NOT NULL
);

SELECT `row id`, `net amount`
FROM `sales-archive`;
```

This is valid syntax, but such names are inconvenient in SQL, ORM mapping, shell scripts, migrations, and BI tools. For new schemas, choose `sales_archive`, `row_id`, and `net_amount`.

### 3.3. If an identifier contains a backtick

To place a literal backtick inside a quoted identifier, MySQL uses two consecutive backticks to represent one backtick in the name:

```sql
CREATE TABLE `report``archive` (
    `row``id` BIGINT NOT NULL
);
```

The actual table name is `report`archive` (with one backtick in the middle), and the actual column name is `row`id`. This is a capability of the quoting syntax, not a convention to use in application schemas.

### 3.4. Quoting each part of a qualified name

Object names can be written in database, table, and column form. When quoting is needed, quote each component individually:

```sql
SELECT `c`.`customer_id`, `c`.`email`
FROM `sales_db`.`customers` AS `c`
WHERE `c`.`customer_id` = 101;
```

Do not quote the entire dotted string as if it were a single name:

```sql
-- Incorrect qualification meaning:
SELECT * FROM `sales_db.customers`;

-- Correct:
SELECT * FROM `sales_db`.`customers`;
```

In the wrong example, MySQL looks for a table literally named `sales_db.customers` in the default database, rather than interpreting `sales_db` as the database and `customers` as the table.

If the database has already been selected with `USE sales_db`, you can specify just the table:

```sql
USE `sales_db`;

SELECT `customer_id`, `email`
FROM `customers`;
```

Qualified names prevent confusion when one server has multiple databases containing tables with the same name.

## 4. Backticks, Single Quotes, and Double Quotes

These three quote styles cannot be substituted for one another arbitrarily:

| Syntax | Meaning in standard MySQL | Example |
|---|---|---|
| Backtick `` `...` `` | Quotes identifiers | `` `order` ``, `` `customer_id` `` |
| Single quote `'...'` | String literal | `'pending'`, `'An'` |
| Double quote `"..."` | Usually a string literal; changes when `ANSI_QUOTES` is enabled | `"pending"` |

When SQL mode `ANSI_QUOTES` is enabled, double quotes are used to quote identifiers and are no longer interpreted as string literals in the usual way. This can cause legacy SQL statements to change meaning across environments with different SQL modes.

Example:

```sql
-- Stable, unambiguous approach in MySQL:
SELECT `customer_id`
FROM `customers`
WHERE `status` = 'ACTIVE';
```

In MySQL, use backticks for identifiers when quoting is needed and single quotes for string literals. This convention reduces dependence on `ANSI_QUOTES`.

## 5. SQL Keywords and Reserved Keywords

### 5.1. Keywords and reserved keywords

MySQL has keywords used in SQL syntax. Some keywords are marked as **reserved**, meaning they cannot be used as unquoted identifiers in normal contexts because the parser must recognize them as syntactic elements.

For example, words like `SELECT`, `FROM`, `WHERE`, `ORDER`, `GROUP`, `KEY`, and `INDEX` have syntactic roles. If you name a table `order` or a column `group`, you must quote them with backticks:

```sql
CREATE TABLE `order` (
    `order_id` BIGINT NOT NULL,
    `group`    VARCHAR(50),
    PRIMARY KEY (`order_id`)
);
```

Not every keyword is reserved. Some nonreserved keywords can still be used as unquoted identifiers in certain contexts. However, a keyword can be promoted to reserved in a newer MySQL version. A name that once worked can start failing after an upgrade.

Therefore, for new schemas, avoid using keywords as object names even when the current version allows them. If you must maintain compatibility with an older schema, quote consistently and test migrations on the target version.

### 5.2. Looking up the keyword list on MySQL 8.0

MySQL 8.0 provides `INFORMATION_SCHEMA.KEYWORDS`, which contains keyword information and a `RESERVED` column indicating whether the word is reserved:

```sql
SELECT WORD, RESERVED
FROM INFORMATION_SCHEMA.KEYWORDS
WHERE WORD IN ('ORDER', 'GROUP', 'RANK', 'WINDOW', 'KEY')
ORDER BY WORD;
```

The list and reserved status depend on the version. Run the query on the exact target server instead of relying on a list found for another version. If the version in use does not provide this metadata table, consult the MySQL documentation for that specific version.

To check a specific word:

```sql
SELECT WORD, RESERVED
FROM INFORMATION_SCHEMA.KEYWORDS
WHERE WORD = UPPER('rank');
```

If the word does not appear or the metadata table is unavailable on the current version, you cannot conclude the word is definitely safe to use; check the syntax documentation for that version.

### 5.3. Why can version upgrades break old names?

MySQL adds syntax and keywords over time. An existing identifier that collides with a new keyword can become ambiguous or invalid if left unquoted.

An upgrade process should include:

1. Identifying existing database, table, column, routine, and alias names.
2. Comparing them against the target version's reserved keyword list.
3. Checking SQL statements, views, routines, triggers, events, and migrations that use those names.
4. Adding backticks in the right places or renaming objects according to a compatibility plan.
5. Running integration tests on the target MySQL version before upgrading production.

Do not inspect only table names. A column named `rank` or an alias colliding with a keyword can also break SQL statements when the version changes.

## 6. Case Sensitivity in Object Names

### 6.1. Database and table names depend on the operating system

MySQL stores databases and tables in the filesystem in a platform-dependent way. Therefore, how uppercase/lowercase letters are compared in database and table names is affected by the operating system and the `lower_case_table_names` variable.

Check the current value:

```sql
SELECT @@lower_case_table_names;
```

The three meaningful values are:

| Value | How names are stored | How database/table names are compared |
|---:|---|---|
| `0` | Stored with exact declared letter case | Case-sensitive. |
| `1` | Stored in lowercase | Case-insensitive. |
| `2` | Stored as declared but normalized on lookup | Case-insensitive; requires a case-insensitive filesystem. |

The default depends on the platform and how the data directory was initialized. On many Unix/Linux systems, the default is typically `0`; Windows typically uses `1`; macOS typically uses `2` on a case-insensitive filesystem. Check the actual value rather than assuming based on the OS name.

In MySQL 8.0, `lower_case_table_names` is fixed when initializing the data directory and cannot be changed arbitrarily after the server has been initialized. Changing it improperly can prevent the server from starting or cause it not to recognize data correctly. Do not use changing this variable as a quick fix for table name mismatches between Windows and Linux.

### 6.2. Column names and aliases

Database and table names can be affected by filesystem rules; column names are case-insensitive in MySQL. Even so, writing names consistently keeps schemas readable and reduces confusion when moving to ORMs or other tools.

Write consistently, for example:

```sql
SELECT `customer_id`, `created_at`
FROM `orders`;
```

Avoid creating tables with the same name differing only in case, such as `Orders` and `orders`, because behavior can differ between a Windows developer machine and a Linux server. A convention of using lowercase for databases and tables is safe and portable.

## 7. Aliases and Qualification to Avoid Ambiguous Names

When joining multiple tables, the same column name can appear in more than one table. Without specifying the source, MySQL may report an ambiguous column error.

Example:

```sql
SELECT customer_id, order_id
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id;
```

If both tables have `customer_id`, an unqualified name causes ambiguity. A clearer way to write it:

```sql
SELECT
    c.customer_id,
    o.order_id,
    o.created_at
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id;
```

Short aliases like `c`, `o`, `p` are convenient for short queries. For long queries or many joins, meaningful aliases like `customer`, `sales_order`, `product` can be easier to read.

Column aliases also make result column names clear:

```sql
SELECT
    o.customer_id,
    COUNT(*) AS order_count,
    SUM(o.total_amount) AS total_revenue
FROM orders AS o
GROUP BY o.customer_id;
```

Aliases in `SELECT` have their own scoping rules; do not assume an alias can be referenced in every clause. For example, in MySQL you can use aliases in `ORDER BY`, `GROUP BY`, and `HAVING` in supported contexts, but you generally cannot use a select-list alias in a `WHERE` clause at the same level because `WHERE` is evaluated before select alias values are produced.

## 8. Identifiers in Prepared Statements and Dynamic SQL

### 8.1. Parameter markers only substitute values

Prepared statements separate SQL from input data:

```sql
PREPARE find_customer FROM
    'SELECT customer_id, email
     FROM customers
     WHERE customer_id = ?';

SET @id = 101;
EXECUTE find_customer USING @id;
DEALLOCATE PREPARE find_customer;
```

The parameter marker `?` represents the `customer_id` value. It does not represent a table name or column name.

The example below does not make MySQL interpret `?` as a table name:

```sql
-- Cannot use a parameter marker to bind an identifier.
SELECT * FROM ?;
```

If you need to choose a table or column dynamically, the identifier must be resolved before sending the SQL statement. Input must be mapped through an allow-list of valid names permitted by the application.

### 8.2. Using an allow-list for dynamic identifiers in Java

Suppose the application lets users sort orders by creation time or total amount:

```java
String orderBy = switch (sortField) {
    case "created" -> "`created_at`";
    case "amount"  -> "`total_amount`";
    default -> throw new IllegalArgumentException("Unsupported sort field");
};

String directionSql = switch (direction.toUpperCase(Locale.ROOT)) {
    case "ASC"  -> "ASC";
    case "DESC" -> "DESC";
    default -> throw new IllegalArgumentException("Unsupported sort direction");
};

String sql = "SELECT order_id, created_at, total_amount "
        + "FROM orders ORDER BY " + orderBy + " " + directionSql + " LIMIT ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setInt(1, limit);
    // Execute and read results.
}
```

`sortField` and `direction` are only selected from predefined branches. The `limit` value is still bound via a parameter marker. Never concatenate user-supplied strings directly into the identifier portion or SQL syntax.

Backticks are not a SQL injection defense if the identifier is still built from untrusted data. A string wrapped in backticks that contains backticks or unexpected syntax can still break out of the statement if handled improperly. An allow-list is the safest approach when the set of allowed identifiers is finite.

### 8.3. If identifiers must be generated from configuration

If a system must generate table names from configuration, validate names against strict rules before assembling SQL. An identifier-quoting function must double every internal backtick and wrap the whole name in backticks; however, syntactically valid quoting still does not replace checking permissions, allowed schemas, and business intent.

Never accept arbitrary database/table names from HTTP requests, file uploads, or message queues and put them straight into SQL. Identifier configurations should come from controlled internal configuration, or be mapped from a logical key to an allowed physical name.

## 9. Inspecting Names and Metadata in MySQL

### 9.1. Viewing a table's definition

`SHOW CREATE TABLE` returns the table definition recorded by MySQL, including column names, data types, indexes, constraints, engine, and related attributes:

```sql
SHOW CREATE TABLE `sales_db`.`orders`;
```

This is a useful way to verify actual names, identifier quoting, and constraints after running a migration.

Other commonly used commands:

```sql
SHOW DATABASES;
SHOW TABLES FROM `sales_db`;
SHOW COLUMNS FROM `sales_db`.`orders`;
SHOW INDEX FROM `sales_db`.`orders`;
```

### 9.2. Finding databases and tables in INFORMATION_SCHEMA

`INFORMATION_SCHEMA` provides structured metadata queryable with SQL:

```sql
SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'sales_db'
ORDER BY TABLE_NAME;
```

Inspecting columns and positions:

```sql
SELECT TABLE_NAME, ORDINAL_POSITION, COLUMN_NAME, COLUMN_TYPE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'sales_db'
  AND TABLE_NAME = 'orders'
ORDER BY ORDINAL_POSITION;
```

Inspecting indexes:

```sql
SELECT TABLE_NAME, INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX, COLUMN_NAME
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA = 'sales_db'
  AND TABLE_NAME = 'orders'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
```

Schema/table names in the `WHERE` conditions here are **string values**, so single quotes are used. This is a direct example distinguishing identifier quoting in SQL from literal syntax in metadata filter conditions.

### 9.3. Checking keywords and reserved status

On MySQL 8.0:

```sql
SELECT WORD, RESERVED
FROM INFORMATION_SCHEMA.KEYWORDS
WHERE WORD LIKE 'ORDER%'
ORDER BY WORD;
```

The result helps verify whether a word is reserved in the exact current server version. When developing migrations for multiple MySQL versions, check against both the lowest and highest versions supported by the project.

## 10. Renaming Objects and Application Impact

Renaming a table or column can affect more components than the visible SQL statement: views, stored routines, triggers, events, applications, ORM mappings, reports, migrations, and background jobs.

Example of renaming a table:

```sql
RENAME TABLE `sales_db`.`order_items_old`
TO `sales_db`.`order_items`;
```

Before renaming, find all references to the old name, assess compatibility during deployment, and check dependent objects. For systems requiring zero-downtime deployment, a multi-phase strategy may be necessary: add the new structure, migrate the application, sync data, and drop the old structure only after no consumers remain.

Do not rename hastily in production just for standardization. First inventory metadata and dependencies, prepare a reviewable migration, take appropriate backups, and test rollback or recovery plans.

## 11. Common Errors

| Symptom | Cause | How to handle |
|---|---|---|
| `You have an error in your SQL syntax` near a table name | Object name collides with a reserved keyword or lacks backticks | Quote the identifier in the right place or rename the object. |
| `Unknown column` even though the column name looks right | Wrong database/table, alias, spelling, or letter-case mismatch in a name component | Check `DATABASE()`, `SHOW CREATE TABLE`, `INFORMATION_SCHEMA.COLUMNS`, and qualification. |
| Works on Windows but fails on Linux | Inconsistent letter case in database/table names and different `lower_case_table_names` | Use consistent lowercase names; check the variable on each server. |
| A SQL query changes meaning after enabling `ANSI_QUOTES` | Double quotes were previously used for string literals | Use single quotes for strings and backticks for identifiers. |
| Prepared statement fails to bind a column name | Parameter markers only represent values | Use an identifier allow-list and assemble controlled structural parts. |
| Migration fails after upgrading MySQL | Existing identifier collides with a new reserved keyword or syntax changed | Check target-version keywords and test migrations before upgrading. |
| `Table ... doesn't exist` even though the name looks right | Wrong default database, table name case mismatch, or object not yet created | Use the fully qualified `database.table` name and inspect metadata. |

When troubleshooting object name errors, confirm the connected server, default database, exact name in metadata, and MySQL version before altering the schema.

## 12. Hands-On Exercises

### Exercise 1: Distinguish identifiers from literals

Create a `customers` table with columns `customer_id` and `email`. Run:

```sql
SELECT customer_id FROM customers;
SELECT 'customer_id' FROM customers;
```

**Task:** explain the difference between the results of the two statements and identify which parts are identifiers and which are string literals.

### Exercise 2: Use backticks with reserved keywords

Create a test table named `order` with a column named `select`. Query the data using backticks. Then try removing the backticks and record the error.

**Task:** explain why backticks help the parser recognize object names.

### Exercise 3: Check keywords by version

On MySQL 8.0, query `INFORMATION_SCHEMA.KEYWORDS` for `ORDER`, `GROUP`, `RANK`, and `WINDOW`.

**Task:** record the `RESERVED` column and explain why you should not rely on results from a different version.

### Exercise 4: Qualification and aliases

Join `customers` with `orders`, both having `customer_id`. Write a query with clear aliases and qualification for every column.

**Task:** try omitting qualification on a shared column name and observe the error or ambiguity.

### Exercise 5: Check case sensitivity

Run `SELECT @@lower_case_table_names;` in your development and test environments. Create a table with a lowercase name and query it using case variations allowed by the environment.

**Task:** explain why a lowercase table-naming convention makes migrations more portable between Windows and Linux.

### Exercise 6: Safe dynamic SQL

Write a Java method allowing orders to be sorted by `created_at` or `total_amount`, ascending or descending. Filter values and `LIMIT` must be bound using `PreparedStatement`.

**Task:** use an allow-list for identifiers and direction; explain why a column name cannot be bound with `?`.

## 13. Schema Naming Checklist

Before creating or reviewing a schema, check:

- [ ] Database, table, column, and index names accurately describe business meaning.
- [ ] `snake_case`, singular/plural rules, and key naming conventions are applied consistently.
- [ ] Object names avoid reserved keywords and names easily confused with SQL syntax.
- [ ] Names avoid spaces, hyphens, or special characters.
- [ ] Identifier lengths are within the limits for each object type.
- [ ] Databases and tables use lowercase consistently to avoid filesystem differences.
- [ ] Identifiers are quoted with backticks when necessary; string literals use single quotes.
- [ ] Each part of a qualified name is quoted individually (`database`.`table`.`column`).
- [ ] Dynamic SQL uses an allow-list for identifiers; data values are bound via prepared statements.
- [ ] Migrations and SQL statements are tested on the exact target MySQL version.

## 14. Key Takeaways

An identifier is an object name; a literal is a data value. MySQL uses backticks to quote identifiers, while single quotes are used for strings. Keywords and reserved keywords can change across versions; therefore, new schemas should avoid using keywords as object names. Database and table names are also affected by `lower_case_table_names` and the filesystem, so a consistent lowercase convention makes cross-platform deployments safer.

When writing SQL, clearly qualify table and column names, use readable aliases, verify metadata with `SHOW CREATE TABLE` or `INFORMATION_SCHEMA`, and construct dynamic SQL only from allowed identifiers. These habits reduce syntax errors, prevent confusion between objects and data, and keep schemas sustainable as applications and MySQL versions evolve.
