# Collation Coercibility and Illegal Mix of Collations Errors

Collation determines how MySQL compares and sorts strings: whether letter case is distinguished, whether accents are distinguished, which characters are considered equivalent, and how trailing spaces are handled. When an expression combines multiple strings with different collations, MySQL must select a collation to perform the comparison or produce the result. That selection rule is called **collation coercibility**.

If MySQL cannot determine a valid collation, the query can fail with an error such as **Illegal mix of collations**. This error commonly appears when joining two columns created at different times or in different environments, when comparing a column with a literal having a different charset/collation, or when combining string expressions.

In the **DATABASE_MYSQL** module, understanding coercibility helps resolve SQL errors, standardize schemas, preserve comparison semantics, and retain index usability. Always check character sets, collations, expression origins, and the downstream impact of a collation change before editing queries or running migrations.

## 1. Distinguishing character sets and collations

These two concepts are related, yet solve two different problems:

- **Character set** defines the set of characters and how characters are encoded into bytes. For example, **utf8mb4** can represent full Unicode characters, including non-BMP characters.
- **Collation** defines the rules for comparing and sorting strings belonging to a character set. For example, **utf8mb4_0900_ai_ci** is a collation of **utf8mb4** that is accent-insensitive and case-insensitive.

One character set can have many collations. Therefore, two columns that both use **utf8mb4** can still fail to compare directly if they have different collations without a valid resolution rule.

Some common suffixes:

| Name component | Meaning |
|---|---|
| **_ai** | Accent-insensitive: does not distinguish accents in comparisons |
| **_as** | Accent-sensitive: distinguishes accents |
| **_ci** | Case-insensitive: does not distinguish uppercase/lowercase |
| **_cs** | Case-sensitive: distinguishes uppercase/lowercase |
| **_bin** | Binary comparison rules for the corresponding collation |

For example, under an **_ai_ci** collation, strings differing in accents or case can be treated as equal. Under an **_as_cs** collation, those differences are preserved during comparisons. Exact behavior depends on the specific collation, the Unicode version it is based on, and attributes such as **PAD SPACE** or **NO PAD**.

Do not treat two collations as equivalent just because both belong to **utf8mb4**. Changing a collation can alter results of **=**, **LIKE**, **ORDER BY**, **GROUP BY**, key comparisons, and index uniqueness.

## 2. Where is collation inherited?

MySQL maintains defaults at multiple levels:

1. **Server:** default character set and collation of the instance.
2. **Database:** default values for the database, typically taken from the server default at creation time if unspecified.
3. **Table:** default for the table, typically inherited from the database.
4. **Column:** collation of each string column, typically inherited from the table.
5. **Connection and literal:** charset/collation used when the client sends strings and when MySQL interprets literals in the session.

Example of creating a database and table with explicit values:

```sql
CREATE DATABASE appdb
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE customers (
    customer_id BIGINT PRIMARY KEY,
    display_name VARCHAR(150) NOT NULL
) ENGINE = InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
```

In this example, the **display_name** column inherits the table's character set and collation. You can specify them explicitly at the column level if a column has different comparison requirements:

```sql
CREATE TABLE external_identifiers (
    identifier VARCHAR(80)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_bin
        NOT NULL,
    PRIMARY KEY (identifier)
) ENGINE = InnoDB;
```

This suits identifiers where letter case or every character must be distinguished under binary rules. Choose collations based on data semantics; do not use **_bin** mechanically for every column.

**Changing defaults does not mean converting existing data.** **ALTER DATABASE ... CHARACTER SET ... COLLATE ...** changes the default for objects created afterward; it does not automatically convert the collation of existing columns. Likewise, changing a table's default does not automatically convert existing string columns.

## 3. What is collation coercibility?

When an expression contains multiple strings with different collations, MySQL assigns each operand a coercibility level. A lower numeric value gives that operand's collation higher priority during resolution.

Common levels in MySQL:

| Value | Expression source | Example |
|---:|---|---|
| 0 | Explicit: has a specified **COLLATE** clause | **name COLLATE utf8mb4_bin** |
| 1 | Concatenation result of strings with different collations | A **CONCAT()** expression mixing two collations |
| 2 | Column, stored routine parameter, or local variable | **customers.display_name** |
| 3 | System constant | **USER()**, **VERSION()** |
| 4 | String literal | **'hello'** |
| 5 | Numeric or temporal value | **123**, **CURRENT_TIMESTAMP** |
| 6 | **NULL** or an expression derived from **NULL** | **NULL** |

The coercibility level is not a server-wide priority ranking of a collation. It only helps MySQL decide which collation is selected within a specific expression.

### 3.1. Inspecting an expression's coercibility

Use the following functions:

- **CHARSET(expr):** returns the character set of the expression.
- **COLLATION(expr):** returns the collation of the expression.
- **COERCIBILITY(expr):** returns the coercibility level of the expression.

Example:

```sql
SELECT
    CHARSET('hello') AS literal_charset,
    COLLATION('hello') AS literal_collation,
    COERCIBILITY('hello') AS literal_coercibility,
    COLLATION(USER()) AS user_collation,
    COERCIBILITY(USER()) AS user_coercibility;
```

For a column:

```sql
SELECT
    CHARSET(display_name) AS column_charset,
    COLLATION(display_name) AS column_collation,
    COERCIBILITY(display_name) AS column_coercibility
FROM customers
LIMIT 1;
```

A literal normally has coercibility 4, a column has coercibility 2, and a system constant such as **USER()** has coercibility 3. Because a column has higher priority than a literal, the column's collation is normally used when the literal can be converted appropriately.

You can make a collation explicit:

```sql
SELECT
    COLLATION(
        _utf8mb4'hello' COLLATE utf8mb4_bin
    ) AS chosen_collation,
    COERCIBILITY(
        _utf8mb4'hello' COLLATE utf8mb4_bin
    ) AS chosen_coercibility;
```

An expression with an explicit **COLLATE** clause has coercibility 0. It takes the highest priority during collation selection.

## 4. How does MySQL resolve differing collations?

General rules:

1. Compare the coercibility levels of the operands. The smaller level generally wins.
2. If levels are equal, inspect the character sets and their Unicode/non-Unicode nature.
3. If the character sets match yet collations differ, binary rules may take precedence where applicable.
4. If no valid collation can still be selected, MySQL raises a mix-of-collations error.

Important rules when coercibility levels are equal:

- If one string uses a Unicode character set and the other uses a non-Unicode character set, MySQL generally favors Unicode and converts the non-Unicode string to Unicode.
- If both share the same character set yet have different collations, a **_bin** collation can override the corresponding **_ci** or **_cs** collation.
- If both share the same character set and both have different non-binary collations, MySQL may be unable to pick one automatically and raise an error.
- If both operands have explicit **COLLATE** clauses that conflict, do not expect MySQL to guess your intent; the expression must be rewritten with a single consistent choice.

These rules have nuances by expression type and version. When investigating, run **COERCIBILITY()**, **CHARSET()**, and **COLLATION()** on the exact participating expressions rather than only looking at column names.

## 5. When does the Illegal mix of collations error appear?

A common error looks like:

```text
Illegal mix of collations
(utf8mb4_general_ci,IMPLICIT)
and (utf8mb4_0900_ai_ci,IMPLICIT)
for operation '='
```

The collation names and operation in the message depend on the data and SQL statement. **IMPLICIT** usually indicates an operand originating from a column or expression with that coercibility level, not a configuration setting that a user needs to enable.

### 5.1. Joining two columns with different collations

Suppose two tables were created at different times:

```sql
CREATE TABLE customers_legacy (
    customer_id BIGINT PRIMARY KEY,
    display_name VARCHAR(150)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_general_ci
        NOT NULL
) ENGINE = InnoDB;

CREATE TABLE customers_new (
    customer_id BIGINT PRIMARY KEY,
    display_name VARCHAR(150)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_ai_ci
        NOT NULL
) ENGINE = InnoDB;
```

Both columns use **utf8mb4**, yet their collations differ. In a JOIN condition, both columns have coercibility 2. If MySQL cannot resolve two collations at the same priority level, the query can fail:

```sql
SELECT
    old.customer_id,
    old.display_name,
    newer.display_name
FROM customers_legacy AS old
JOIN customers_new AS newer
  ON old.display_name = newer.display_name;
```

This is the classic scenario for a mix-of-collations error: two columns share the same charset yet have different comparison rules, and neither operand has a stronger coercibility to decide the outcome.

### 5.2. Literals, variables, and system constants

Literals usually have coercibility 4 and therefore yield to a column's coercibility 2. However, a literal with an introducer or explicit **COLLATE** can carry a different charset/collation.

Example specifying a UTF-8 literal explicitly:

```sql
SELECT *
FROM customers
WHERE display_name =
    _utf8mb4'Nguyễn An' COLLATE utf8mb4_0900_ai_ci;
```

This expression has an explicit collation. If the column uses a different collation, the comparison applies the rules of the collation specified for the expression. Ensure the chosen collation matches business semantics.

System constants such as **USER()** or **VERSION()** can carry a collation different from a column's. When compared directly against a column, the column's coercibility is higher than the system constant's, yet it should still be checked when nested inside **CONCAT()**, **CASE**, **UNION**, or other functions.

### 5.3. CONCAT, CASE, COALESCE, and UNION

The error does not occur only in **=**. Expressions combining multiple strings also require a common collation:

```sql
SELECT CONCAT(
    legacy.display_name,
    modern.display_name
)
FROM customers_legacy AS legacy
JOIN customers_new AS modern
  ON legacy.customer_id = modern.customer_id;
```

If two strings have different collations at the same coercibility level, the combined expression can end up with no single collation or trigger an error when used in a context requiring a specific collation.

Places to inspect include:

- **CONCAT()** and string expression operators.
- **CASE** expressions whose branches return strings from different sources.
- **COALESCE()** or **IFNULL()** mixing columns and literals/columns with differing collations.
- **UNION** branches with inconsistent types and collations.
- **ORDER BY**, **GROUP BY**, **LIKE**, or comparisons over combined expressions.

## 6. Diagnosing errors using metadata and coercibility functions

Do not fix errors by sprinkling **COLLATE** everywhere randomly. First identify the actual collation of each column and expression.

### 6.1. Checking server and connection settings

```sql
SELECT
    @@character_set_server AS server_charset,
    @@collation_server AS server_collation,
    @@character_set_database AS database_charset,
    @@collation_database AS database_collation,
    @@character_set_connection AS connection_charset,
    @@collation_connection AS connection_collation,
    @@character_set_client AS client_charset,
    @@character_set_results AS results_charset;
```

These variables show server, database, and session defaults. Current defaults do not necessarily reflect the collations of previously created tables.

You can list related variables:

```sql
SHOW VARIABLES LIKE 'character_set%';
SHOW VARIABLES LIKE 'collation%';
```

### 6.2. Checking column collations

Use **SHOW FULL COLUMNS**:

```sql
SHOW FULL COLUMNS FROM customers_legacy;
SHOW FULL COLUMNS FROM customers_new;
```

Or query **INFORMATION_SCHEMA.COLUMNS**:

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    COLUMN_NAME,
    CHARACTER_SET_NAME,
    COLLATION_NAME,
    COLUMN_TYPE,
    IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND COLUMN_NAME = 'display_name'
ORDER BY TABLE_NAME;
```

If two columns use different charsets or collations, record them accurately before making changes. Also inspect length, nullability, defaults, and indexes because a column migration must preserve unrelated attributes.

### 6.3. Checking available collations

```sql
SHOW COLLATION LIKE 'utf8mb4%';
```

Not every MySQL version has the same collation list. For instance, collations with the **0900** element belong to MySQL 8.0; you cannot assume they exist on MySQL 5.7 or another MySQL-compatible product.

### 6.4. Measuring expression coercibility

When suspecting an expression is causing an error, inspect each operand independently:

```sql
SELECT
    CHARSET(display_name),
    COLLATION(display_name),
    COERCIBILITY(display_name)
FROM customers_legacy
LIMIT 1;
```

Inspect literals and system expressions:

```sql
SELECT
    CHARSET('hello') AS literal_charset,
    COLLATION('hello') AS literal_collation,
    COERCIBILITY('hello') AS literal_coercibility,
    COLLATION(USER()) AS system_collation,
    COERCIBILITY(USER()) AS system_coercibility;
```

For combined expressions, inspect each component and then inspect the **CONCAT()** or **CASE** result separately. This helps determine whether the collation is inherited from a column, literal, system constant, or set explicitly.

## 7. Query-level fixes

If the schema cannot be changed immediately, you can use **COLLATE** to specify the comparison collation explicitly. This is an intentional workaround for a single query or a temporary migration phase.

### 7.1. Choosing a unified collation for a JOIN

For two columns sharing the **utf8mb4** charset, you can specify the collation on one side:

```sql
SELECT
    old.customer_id,
    old.display_name,
    newer.display_name
FROM customers_legacy AS old
JOIN customers_new AS newer
  ON old.display_name COLLATE utf8mb4_0900_ai_ci
     = newer.display_name;
```

**COLLATE** makes the left operand explicit with coercibility 0. MySQL uses the specified collation to resolve the comparison.

Choose **utf8mb4_0900_ai_ci** only if business rules call for accent- and case-insensitive comparison under that collation. If identifiers must distinguish every character, choose another suitable collation.

### 7.2. Converting charset before choosing collation

If two columns have different character sets, adding **COLLATE** alone may not suffice because the collation must belong to the corresponding character set. You can convert one expression to a common charset and then specify the collation:

```sql
SELECT *
FROM legacy_customers AS old
JOIN modern_customers AS newer
  ON CONVERT(old.display_name USING utf8mb4)
       COLLATE utf8mb4_0900_ai_ci
     = newer.display_name;
```

Applying **CONVERT()** to a column can prevent the optimizer from using that column's native index effectively. Treat this as a temporary measure or for small datasets, after confirming the conversion loses no characters.

### 7.3. Specifying collation for a literal

If a column already has a standard collation, you can let the column dictate the collation and provide a literal with a clear charset:

```sql
SELECT *
FROM customers
WHERE display_name =
    _utf8mb4'Nguyễn An';
```

If you need to force a specific comparison rule, add **COLLATE** to the literal:

```sql
SELECT *
FROM customers
WHERE display_name =
    _utf8mb4'Nguyễn An' COLLATE utf8mb4_0900_ai_ci;
```

Distinguish the **_utf8mb4** introducer from **COLLATE**: the introducer declares the literal's character set; **COLLATE** specifies the comparison rule.

### 7.4. Re-checking the execution plan

**COLLATE**, **CONVERT()**, or functions applied to a column can affect index usage. After fixing a query, check:

```sql
EXPLAIN
SELECT
    old.customer_id,
    newer.display_name
FROM customers_legacy AS old
JOIN customers_new AS newer
  ON old.display_name COLLATE utf8mb4_0900_ai_ci
     = newer.display_name;
```

Check **key**, **type**, **rows**, **possible_keys**, and the join condition. A query that no longer errors yet degrades into a full table scan on a large table still requires remediation.

## 8. Standardizing collations at the schema level

If many queries frequently need **COLLATE** added, the underlying issue likely resides in the schema. Long-term, columns representing the same concept and participating in JOINs should share the same character set and collation unless a clear business requirement dictates otherwise.

### 8.1. Changing the database default

```sql
ALTER DATABASE appdb
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;
```

This statement changes the default for objects created afterward. It does not automatically convert the collations of existing columns.

### 8.2. Changing the table default and converting existing columns

Changing the table default for future columns:

```sql
ALTER TABLE customers
    DEFAULT CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;
```

To convert existing character columns to a new charset/collation:

```sql
ALTER TABLE customers
    CONVERT TO CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;
```

**CONVERT TO CHARACTER SET** can rebuild the table and indexes. Execution time, temporary storage, locks, and online capability depend on the version, engine, table size, and change type.

### 8.3. Changing a single column's collation

You can redefine a column using **MODIFY**:

```sql
ALTER TABLE customers
    MODIFY display_name VARCHAR(150)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_ai_ci
        NOT NULL;
```

When using **MODIFY**, redeclare all column attributes to preserve, such as type, length, **NULL/NOT NULL**, **DEFAULT**, **COMMENT**, generated expressions, and related properties. Omitting attributes can cause unintended schema changes.

## 9. Risks when changing collations

Changing a collation is not merely a technical bugfix. It can alter the comparison semantics of data and affect index uniqueness.

### 9.1. Unique indexes may uncover duplicate values

Suppose a column currently uses a case-sensitive collation, allowing both **Alice** and **alice** to be stored. If changed to a case-insensitive collation, the two values may be treated as equal. When rebuilding the unique index, the migration can fail with a duplicate key error.

Before changing, check for duplicate values under the target collation. Example when the column already uses the **utf8mb4** character set:

```sql
SELECT
    display_name COLLATE utf8mb4_0900_ai_ci AS normalized_name,
    COUNT(*) AS value_count
FROM customers
GROUP BY display_name COLLATE utf8mb4_0900_ai_ci
HAVING COUNT(*) > 1;
```

This query surfaces values that are distinct under the current collation yet equivalent under the target collation. For data spanning multiple charsets, convert to a common charset before applying the collation check.

If rows are returned, decide the business rule: merge records, rename codes, retain a sensitive collation, or adjust the unique key. Do not automatically delete one record just to make a migration pass.

### 9.2. Sort order and grouping results may change

A new collation can alter:

- Results of **=** and **LIKE** comparisons.
- **ORDER BY** ordering.
- **GROUP BY** groupings and **DISTINCT** results.
- Duplicate detection in unique indexes.
- Matching behavior in JOINs and search predicates.

A collation change can therefore alter business logic even when the underlying bytes in the table remain untouched.

### 9.3. Indexes and migration duration

String indexes are constructed using collation rules. When the collation changes, MySQL may need to rebuild indexes so key ordering reflects the new rules. Evaluate:

- Table and index sizes, including temporary space during rebuilds.
- Execution duration and locks affecting applications.
- Impact on replication lag and maintenance windows.
- Compatibility of applications, drivers, reports, and integrated systems.
- Restorable backups and a rollback plan.

Do not assume **ALTER TABLE ... CONVERT TO CHARACTER SET** is always online or instantaneous. Test the migration on a near-production copy before deploying.

## 10. Checking connection charset and collation

Even when columns are standardized, a client session might send literals with a different charset/collation than expected. MySQL has relevant variables:

- **character_set_client:** charset the server assumes for data sent by the client.
- **character_set_connection:** charset used to convert literals and string expressions during processing.
- **collation_connection:** default collation for string expressions in the connection.
- **character_set_results:** charset the server uses when sending results back to the client.

You can check them:

```sql
SELECT
    @@character_set_client,
    @@character_set_connection,
    @@collation_connection,
    @@character_set_results;
```

In the mysql client, you can set the connection charset/collation with:

```sql
SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci;
```

This command updates the session charset variables for client, connection, and results. In Java applications using Connector/J, configure encoding/collation through the driver and verify session values after connecting. Avoid calling **SET NAMES** arbitrarily when the driver already manages the charset or when a connection pool reuses sessions.

Connection charset does not change a column's collation. A session using **utf8mb4_0900_ai_ci** can still query a table with a **utf8mb4_general_ci** column; MySQL continues to apply coercibility rules to resolve expressions.

## 11. Workflow for resolving collation mix errors

When encountering **Illegal mix of collations**, follow this sequence:

1. **Read the full error.** Record the collations, coercibilities in parentheses, and the failing operation such as **=**, **LIKE**, or concatenation.
2. **Identify the expression.** Isolate the JOIN, WHERE, CONCAT, CASE, COALESCE, or UNION combining strings.
3. **Inspect source columns.** Use **SHOW FULL COLUMNS** or **INFORMATION_SCHEMA.COLUMNS** to get each column's charset/collation.
4. **Check coercibility.** Use **CHARSET()**, **COLLATION()**, and **COERCIBILITY()** on the operands.
5. **Confirm business rules.** Should the comparison distinguish case, accents, characters, or trailing spaces?
6. **Choose the fix.** Use **COLLATE** for localized cases; use **CONVERT()** when unifying charsets is required; plan schema standardization if the error recurs.
7. **Check for duplicate data.** Before changing a collation, find duplicates under the target collation, especially when unique indexes exist.
8. **Check the execution plan.** Run **EXPLAIN** after fixing to catch lost index usage or rising join costs.
9. **Test the migration.** Back up, test the conversion on staging, and verify comparison results before applying to production.

## 12. Common mistakes

| Misconception | Correct understanding |
|---|---|
| Same **utf8mb4** guarantees direct comparability | Two columns with the same charset can still have different collations and trigger errors |
| **COLLATE** changes the character set | **COLLATE** selects comparison rules; **CONVERT(... USING ...)** converts an expression's charset |
| Changing database default converts all old columns | It only changes defaults for newly created objects; existing columns require migration |
| Adding **COLLATE** on either side never hurts performance | Collation expressions can alter the access path and index usability |
| A **_ci** collation only affects ORDER BY | It also affects **=**, JOIN, GROUP BY, DISTINCT, LIKE, and unique indexes |
| No errors after changing collation means semantics stayed identical | Previously distinct strings may become equivalent |
| Collation mix errors always come from the connection | They often stem from two columns, expressions, or UNION branches having different collations |
| **SET NAMES** fixes the collations of all tables | It only adjusts session charset/collation, not columns in the schema |

## 13. Takeaways

- Character set determines how characters are encoded; collation determines how strings are compared and sorted.
- Coercibility is the priority rank MySQL uses when selecting a collation for an expression; lower numbers mean higher priority.
- Columns normally have coercibility 2, literals 4, system constants 3, and expressions with explicit **COLLATE** 0.
- Two columns sharing the same charset yet having different collations can cause **Illegal mix of collations** in JOINs or comparisons.
- Use **CHARSET()**, **COLLATION()**, **COERCIBILITY()**, **SHOW FULL COLUMNS**, and **INFORMATION_SCHEMA.COLUMNS** to diagnose.
- **COLLATE** handles localized cases; **CONVERT()** changes an expression's charset and can impact index usage.
- Standardizing collations across semantically equivalent columns is the long-term solution, but requires checking duplicates, unique indexes, sort order, and execution plans.
- Collation changes may require rebuilding tables/indexes, requiring backups and pre-production migration testing.
- Connection collation and column collation are separate levels; **SET NAMES** does not convert existing schemas.

Once you understand coercibility and collation resolution rules, you can pinpoint the exact source of collation mix errors, choose comparison rules aligned with business logic, and roll out schema changes safely while keeping MySQL performance under control.
