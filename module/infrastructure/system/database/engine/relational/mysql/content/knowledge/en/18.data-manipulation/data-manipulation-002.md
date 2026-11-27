# Default Values, Auto-Generated Columns, and Omitted Columns in INSERT

When adding a row in MySQL, an application does not necessarily have to provide a value for every column. Some columns can receive default values, some receive auto-increment numbers from MySQL, and some are computed from other columns. Understanding these mechanisms keeps INSERT statements concise, ensures data consistency, and prevents confusion between "not passing a value", "passing NULL", and "requesting DEFAULT".

In MySQL, three concepts must be distinguished:

- **DEFAULT**: the value used when a column is omitted in INSERT or explicitly specified with the DEFAULT keyword.
- **AUTO_INCREMENT**: a mechanism that assigns sequentially increasing integer values, typically used as a row identifier.
- **Generated column**: a column computed from an expression based on other columns in the same row; users cannot arbitrarily assign values to it.

In addition, a column may be omitted from the INSERT column list. In that case, MySQL applies default rules based on the column definition and the active SQL mode. This lesson explains each case, how to verify the results, and common data-entry mistakes.

## Learning Objectives

After this lesson, you will be able to:

- Declare DEFAULT literals and DEFAULT expressions in MySQL.
- Distinguish omitting a column, specifying DEFAULT, and passing NULL.
- Explain the impact of NOT NULL and strict SQL mode when values are missing.
- Use AUTO_INCREMENT and retrieve the newly generated ID on the same connection.
- Distinguish AUTO_INCREMENT from a generated column.
- Declare generated columns as VIRTUAL or STORED.
- Omit generated columns in INSERT and understand the restriction on assigning values directly.
- Use DEFAULT in multi-row INSERT, INSERT ... SET, and INSERT ... SELECT.
- Understand how DEFAULT and ON UPDATE CURRENT_TIMESTAMP serve different roles.
- Inspect schemas, default values, and actual data before deployment.

## 1. Preparing the Practice Table

The table below models an order line item. Each row has an auto-increment ID, a default quantity of 1, a default status of NEW, an automatic creation timestamp, and a line total calculated as quantity multiplied by unit price.

    CREATE TABLE order_line_default_demo (
        line_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        order_code VARCHAR(30) NOT NULL,
        quantity INT UNSIGNED NOT NULL DEFAULT 1,
        unit_price DECIMAL(12,2) NOT NULL,
        line_total DECIMAL(14,2)
            GENERATED ALWAYS AS (quantity * unit_price) STORED,
        line_status VARCHAR(20) NOT NULL DEFAULT 'NEW',
        note VARCHAR(200) NULL DEFAULT NULL,
        created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        updated_at DATETIME(6) NOT NULL
            DEFAULT CURRENT_TIMESTAMP(6)
            ON UPDATE CURRENT_TIMESTAMP(6),
        PRIMARY KEY (line_id),
        UNIQUE KEY uq_order_line_default_order_code (order_code)
    ) ENGINE = InnoDB;

In this table:

- line_id is automatically assigned by AUTO_INCREMENT.
- quantity uses 1 if INSERT does not supply a value.
- unit_price is required because it is NOT NULL and has no DEFAULT.
- line_total is computed by MySQL from quantity and unit_price.
- line_status uses NEW if omitted.
- note allows NULL and has DEFAULT NULL.
- created_at receives the insert timestamp.
- updated_at receives the insert timestamp and updates automatically when the row changes according to the ON UPDATE rule.

Inspect the table definition:

    SHOW CREATE TABLE order_line_default_demo;

You can also view column metadata:

    SHOW COLUMNS FROM order_line_default_demo;

## 2. Omitting Columns in INSERT

When an INSERT statement includes a column list, columns not listed receive no value from the statement. MySQL applies each column's default value or value-generation rule.

Example:

    INSERT INTO order_line_default_demo
        (order_code, unit_price)
    VALUES
        ('ORD-001', 25.00);

The application sends only order_code and unit_price. MySQL handles the remaining columns:

| Column | Result |
|---|---|
| line_id | Assigns an AUTO_INCREMENT value |
| order_code | ORD-001 |
| quantity | 1 from DEFAULT |
| unit_price | 25.00 from INSERT |
| line_total | 25.00 computed by the generated expression |
| line_status | NEW from DEFAULT |
| note | NULL from DEFAULT |
| created_at | Insert timestamp |
| updated_at | Insert timestamp |

Verify:

    SELECT
        line_id,
        order_code,
        quantity,
        unit_price,
        line_total,
        line_status,
        note,
        created_at,
        updated_at
    FROM order_line_default_demo;

Key point: omitting a column does not mean MySQL will automatically pick a business-valid value. The result depends on the column definition, column type, constraints, and SQL mode.

### 2.1. Why Should You Write the Column List?

Prefer:

    INSERT INTO order_line_default_demo
        (order_code, unit_price)
    VALUES
        ('ORD-002', 18.50);

Avoid INSERT without a column list:

    INSERT INTO order_line_default_demo
    VALUES (DEFAULT, 'ORD-003', DEFAULT, 18.50, DEFAULT,
            DEFAULT, DEFAULT, DEFAULT, DEFAULT);

When the column list is omitted, the writer must supply values in the order of all columns in the table. Adding, removing, or reordering columns can break old statements or assign data to the wrong positions. Generated columns must also be handled in their exact positions if the statement has no column list.

For applications, migrations, and import scripts, an explicit column list makes statements much more resilient to schema changes.

## 3. Omitting a Column, DEFAULT, and NULL Are Not the Same

The three forms below have different meanings:

    -- Omit note
    INSERT INTO order_line_default_demo (order_code, unit_price)
    VALUES ('ORD-010', 12.00);

    -- Request MySQL to use note's default
    INSERT INTO order_line_default_demo (order_code, unit_price, note)
    VALUES ('ORD-011', 12.00, DEFAULT);

    -- Explicitly pass NULL
    INSERT INTO order_line_default_demo (order_code, unit_price, note)
    VALUES ('ORD-012', 12.00, NULL);

In the sample table, note allows NULL and has DEFAULT NULL, so all three forms produce NULL for note. However, they do not represent the same rule:

- Omitting the column: MySQL applies the default according to the column definition.
- DEFAULT: requests using the column's default value at that position.
- NULL: sends an explicit NULL value; it does not ask MySQL to substitute a different default.

The difference is clearer with a NOT NULL column that has a default:

    INSERT INTO order_line_default_demo
        (order_code, unit_price, line_status)
    VALUES
        ('ORD-013', 10.00, DEFAULT);

line_status receives NEW. However:

    INSERT INTO order_line_default_demo
        (order_code, unit_price, line_status)
    VALUES
        ('ORD-014', 10.00, NULL);

fails in strict SQL mode because line_status is declared NOT NULL. DEFAULT is not synonymous with NULL, and NULL does not trigger the DEFAULT value.

### 3.1. Omitted Nullable Columns

If a column allows NULL and has no explicit DEFAULT clause, MySQL uses NULL as its implicit default when the column is omitted.

    CREATE TABLE nullable_default_demo (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        optional_text VARCHAR(100) NULL,
        PRIMARY KEY (id)
    ) ENGINE = InnoDB;

    INSERT INTO nullable_default_demo () VALUES ();

The new row has optional_text set to NULL. You can write the definition explicitly so schema readers see the intent clearly:

    optional_text VARCHAR(100) NULL DEFAULT NULL

Declaring DEFAULT NULL is explicit, though for a nullable column with no other default, NULL is already the implicit default.

### 3.2. NOT NULL Columns Without DEFAULT

If a NOT NULL column has no DEFAULT and is not an auto-generated column such as AUTO_INCREMENT or a generated column, the application must provide a value on INSERT.

For example, unit_price in the practice table:

    INSERT INTO order_line_default_demo (order_code)
    VALUES ('ORD-MISSING-PRICE');

In strict SQL mode, the statement is rejected because unit_price has no default value and none was provided. This is the desired behavior for required data: errors are caught immediately rather than silently storing a meaningless value.

## 4. SQL Mode and Implicit Defaults

Behavior when omitting a NOT NULL column without DEFAULT also depends on the SQL mode.

In MySQL 8.0, strict mode is normally enabled by default. For transactional tables like InnoDB, when an INSERT omits a value for a NOT NULL column without DEFAULT, MySQL raises an error instead of inserting an implicit default.

Check the session SQL mode:

    SELECT @@SESSION.sql_mode;

Also check the global mode:

    SELECT @@GLOBAL.sql_mode;

Common strict modes are STRICT_TRANS_TABLES and STRICT_ALL_TABLES.

If strict mode is disabled, MySQL may use a data-type implicit default and emit a warning when a required value is missing. For example, the implicit value may be 0 for numeric types, an empty string for string types, or a zero date depending on the type and related SQL modes. Never rely on this behavior when designing applications.

| Column Definition | When Omitted in INSERT |
|---|---|
| Has DEFAULT literal or expression | Uses the DEFAULT value |
| Nullable, no other DEFAULT declared | Uses NULL |
| AUTO_INCREMENT | Assigns an auto-increment value |
| Generated column | MySQL computes it from the expression |
| NOT NULL, no DEFAULT, strict mode | Typically raises an error with InnoDB |
| NOT NULL, no DEFAULT, non-strict mode | May use an implicit type default and emit a warning |

If testing in a non-strict environment, inspect warnings immediately after INSERT:

    SHOW WARNINGS;

Do not disable strict mode just to make an incomplete INSERT succeed. Fix the column list or the DEFAULT definition according to business rules. Implicit defaults can produce incorrect data that still looks type-valid.

## 5. Declaring a DEFAULT Literal

A DEFAULT literal is a fixed value declared in the column definition:

    CREATE TABLE account_preference_demo (
        account_id BIGINT UNSIGNED NOT NULL,
        language_code VARCHAR(10) NOT NULL DEFAULT 'vi',
        page_size INT UNSIGNED NOT NULL DEFAULT 20,
        is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
        time_zone VARCHAR(64) NULL DEFAULT 'Asia/Ho_Chi_Minh',
        PRIMARY KEY (account_id)
    ) ENGINE = InnoDB;

When omitting the columns with defaults:

    INSERT INTO account_preference_demo (account_id)
    VALUES (1001);

MySQL creates the row with language_code = 'vi', page_size = 20, is_enabled = TRUE, and time_zone = 'Asia/Ho_Chi_Minh'.

A DEFAULT should reflect a stable business rule, such as a default language, initial status, or default quantity. Do not set arbitrary defaults just to bypass missing-data errors.

### 5.1. DEFAULT Across Data Types

The default value must be compatible with the column's data type and constraints:

    CREATE TABLE typed_default_demo (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        display_name VARCHAR(100) NOT NULL DEFAULT '',
        retry_count INT UNSIGNED NOT NULL DEFAULT 0,
        amount DECIMAL(12,2) NOT NULL DEFAULT 0.00,
        is_active TINYINT(1) NOT NULL DEFAULT 1,
        metadata JSON NULL DEFAULT NULL,
        PRIMARY KEY (id)
    ) ENGINE = InnoDB;

Do not use 0 or an empty string to represent "unknown" if the business needs to distinguish missing data. In that case, NULL or a dedicated status is more accurate.

## 6. DEFAULT Expressions

Starting in MySQL 8.0.13, you can declare an expression as the default value for many column types. The expression must be enclosed in parentheses to distinguish it from a literal default.

Example creating a reminder timestamp two days after the current time:

    CREATE TABLE reminder_default_demo (
        reminder_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        title VARCHAR(150) NOT NULL,
        created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        remind_at DATETIME(6) NOT NULL
            DEFAULT (CURRENT_TIMESTAMP(6) + INTERVAL 2 DAY),
        PRIMARY KEY (reminder_id)
    ) ENGINE = InnoDB;

created_at uses the special temporal default syntax CURRENT_TIMESTAMP(6). remind_at uses a computed expression, so it is wrapped in parentheses:

    DEFAULT (CURRENT_TIMESTAMP(6) + INTERVAL 2 DAY)

On INSERT:

    INSERT INTO reminder_default_demo (title)
    VALUES ('Check order');

MySQL automatically populates created_at and remind_at using the insert timestamp.

### 6.1. When Is a Default Expression Evaluated?

A default expression is applied when INSERT omits the column or specifies DEFAULT. The value is generated for the inserted row at that moment; it is not an expression re-evaluated on every SELECT.

If you want a value that changes over time whenever a row is read, DEFAULT is not the right mechanism. Compute the value in the query or application. If you want a column to update automatically when the row changes, see the ON UPDATE CURRENT_TIMESTAMP rule in a later section.

### 6.2. Limitations of DEFAULT Expressions

Default expressions have restrictions. You cannot use them as arbitrary expressions referencing other columns in the same row. For example, you cannot use DEFAULT to compute a line total from quantity and unit_price:

    -- Invalid idea for DEFAULT:
    -- line_total DECIMAL(14,2) DEFAULT (quantity * unit_price)

If a value must be computed from other columns in the same row, use a generated column:

    line_total DECIMAL(14,2)
        GENERATED ALWAYS AS (quantity * unit_price) STORED

Default expressions are also restricted in which expressions are allowed; you cannot include subqueries, parameters, variables, or arbitrary stored functions in a default. Check the documentation for your exact MySQL version and test CREATE TABLE on the target deployment version before using complex expressions.

### 6.3. Version Compatibility

DEFAULT expressions are supported starting in MySQL 8.0.13. If the application must run on MySQL 5.7 or earlier versions, do not assume default expression syntax will work. Check the server version:

    SELECT VERSION();

For multi-environment systems, migrations must be tested against the lowest supported MySQL version.

## 7. DEFAULT in INSERT Statements

You can request the default value for a column using the DEFAULT keyword:

    INSERT INTO order_line_default_demo
        (order_code, quantity, unit_price, line_status)
    VALUES
        ('ORD-020', DEFAULT, 30.00, DEFAULT);

quantity receives 1 and line_status receives NEW.

If the columns are omitted altogether, the same defaults are applied:

    INSERT INTO order_line_default_demo
        (order_code, unit_price)
    VALUES
        ('ORD-021', 30.00);

DEFAULT is useful when an INSERT statement is generated dynamically and needs to express explicitly that a column should use its default, or when a multi-row statement has specific rows that need the default value in a given position.

### 7.1. DEFAULT in Multi-Row INSERT

Each row can use DEFAULT in its corresponding position:

    INSERT INTO order_line_default_demo
        (order_code, quantity, unit_price, line_status)
    VALUES
        ('ORD-030', DEFAULT, 10.00, DEFAULT),
        ('ORD-031', 3,        12.00, 'READY'),
        ('ORD-032', 5,        15.00, DEFAULT);

Rows ORD-030 and ORD-032 use default quantity/status; row ORD-031 supplies explicit values.

If a column is omitted from the INSERT column list, it is omitted for all rows in that statement. If different values are needed per row, list the column and use DEFAULT or an explicit value at each position.

### 7.2. DEFAULT in INSERT ... SET

MySQL supports the INSERT ... SET form:

    INSERT INTO order_line_default_demo
    SET
        order_code = 'ORD-040',
        unit_price = 45.00,
        quantity = DEFAULT,
        line_status = DEFAULT;

This form can be easy to read when inserting a single row and assigning columns by name. For multiple rows, INSERT ... VALUES is usually more compact and appropriate.

### 7.3. DEFAULT in INSERT ... SELECT

INSERT ... SELECT can use a target column list to specify where data is inserted:

    CREATE TABLE order_import_stage (
        source_code VARCHAR(30) NOT NULL,
        source_price DECIMAL(12,2) NOT NULL
    ) ENGINE = InnoDB;

    INSERT INTO order_import_stage (source_code, source_price)
    VALUES
        ('SRC-001', 11.00),
        ('SRC-002', 22.00);

    INSERT INTO order_line_default_demo (order_code, unit_price)
    SELECT source_code, source_price
    FROM order_import_stage;

Other columns in the target table continue to use their defaults, AUTO_INCREMENT, or generated expressions. The number and order of expressions in SELECT must match the target column list.

If you need an explicit DEFAULT expression in a SELECT list, check the syntax and context for your MySQL version; the most maintainable approach is usually to list only the source columns to insert and let the remaining target columns be omitted.

## 8. AUTO_INCREMENT: Automatic ID Allocation

AUTO_INCREMENT is an attribute of an integer column, commonly used to assign a new identifier to each row. It is not a generated column: it does not compute values from other columns, but instead uses the table's sequence generator.

Example:

    CREATE TABLE support_ticket_demo (
        ticket_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        subject VARCHAR(160) NOT NULL,
        created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        PRIMARY KEY (ticket_id)
    ) ENGINE = InnoDB;

Omit ticket_id:

    INSERT INTO support_ticket_demo (subject)
    VALUES ('Unable to log in');

MySQL assigns a new ticket_id. You can retrieve the newly created ID on the same connection:

    SELECT LAST_INSERT_ID();

LAST_INSERT_ID() is tied to the current connection, making it suitable for applications to retrieve the ID of the INSERT just executed on the same connection. Do not fetch the ID using SELECT MAX(ticket_id), because another connection may insert concurrently and cause the result to belong to a different request's row.

### 8.1. Omitted, NULL, and 0 in AUTO_INCREMENT

For an AUTO_INCREMENT column:

- Omitting the column or passing NULL normally instructs MySQL to generate the next value.
- Passing 0 also normally requests generating the next value.
- If the NO_AUTO_VALUE_ON_ZERO SQL mode is enabled, 0 is stored as an explicit value instead of requesting a generated number.
- Passing an explicit positive number can be accepted if it does not violate key constraints; the counter adjusts so subsequent generated values do not collide with the used value.

Example:

    INSERT INTO support_ticket_demo (subject)
    VALUES ('Ticket A');

    INSERT INTO support_ticket_demo (ticket_id, subject)
    VALUES (NULL, 'Ticket B');

Check the mode:

    SELECT @@SESSION.sql_mode;

Do not use 0 as a sentinel value for AUTO_INCREMENT without controlling NO_AUTO_VALUE_ON_ZERO. For normal applications, omit the ID column or pass NULL to request ID generation.

### 8.2. AUTO_INCREMENT Does Not Guarantee Gapless Numbers

AUTO_INCREMENT assigns unique numbers via the storage engine's mechanism, not a gapless sequential document counter. Gaps can appear due to transaction rollbacks, failed inserts, deletions, or concurrent allocations.

Do not use:

- MAX(id) to infer the row count.
- Last ID minus first ID to infer the number of records.
- AUTO_INCREMENT for legal invoice numbers that must be strictly contiguous by regulation.
- Assumptions that ID order always matches transaction commit order.

If the business requires contiguous document numbers or custom numbering rules, you must design a separate sequence-allocation workflow and concurrency control.

### 8.3. Limits and Design of AUTO_INCREMENT

Typically, a table has only one AUTO_INCREMENT column; this column must be indexed and have an appropriate integer type. With InnoDB, it is usually the PRIMARY KEY.

Choose INT or BIGINT based on table scale and lifespan. If IDs grow rapidly, INT may exhaust its range sooner than expected. Referencing foreign key columns must have a compatible type, including the UNSIGNED attribute.

Do not alter the AUTO_INCREMENT value arbitrarily in production. Adjusting the counter should be done through planned DDL after verifying existing data.

## 9. Generated Columns: Columns Computed from Other Columns

A generated column is a column whose value is computed from an expression based on data in the same row. For example, a line total can be computed from quantity and unit price:

    CREATE TABLE invoice_line_generated_demo (
        invoice_line_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        quantity INT UNSIGNED NOT NULL,
        unit_price DECIMAL(12,2) NOT NULL,
        line_total DECIMAL(14,2)
            GENERATED ALWAYS AS (quantity * unit_price) STORED,
        PRIMARY KEY (invoice_line_id)
    ) ENGINE = InnoDB;

On insert:

    INSERT INTO invoice_line_generated_demo
        (quantity, unit_price)
    VALUES
        (3, 12.50);

MySQL computes line_total = 37.50. The application does not need to compute and send the total separately, preventing quantity/unit_price and line_total from drifting out of sync.

### 9.1. Do Not Assign Arbitrary Values to a Generated Column

Generated columns are managed by their expression. In INSERT, you can omit the generated column; if you list it, the provided value must be DEFAULT:

    INSERT INTO invoice_line_generated_demo
        (quantity, unit_price, line_total)
    VALUES
        (2, 20.00, DEFAULT);

You cannot supply an arbitrary computed value:

    -- Invalid: line_total is generated by MySQL
    INSERT INTO invoice_line_generated_demo
        (quantity, unit_price, line_total)
    VALUES
        (2, 20.00, 999.00);

Similarly, you cannot update a generated column to an arbitrary value with UPDATE. Update the input columns instead; MySQL automatically recomputes the generated value.

### 9.2. VIRTUAL vs. STORED

MySQL supports two kinds of generated columns:

- VIRTUAL: values are evaluated when read; column values are not stored in the row data.
- STORED: values are evaluated on insert/update and stored in the row.

If no kind is specified, a generated column defaults to VIRTUAL.

VIRTUAL example:

    CREATE TABLE product_price_virtual_demo (
        product_id BIGINT UNSIGNED NOT NULL,
        unit_price DECIMAL(12,2) NOT NULL,
        tax_rate DECIMAL(5,4) NOT NULL DEFAULT 0.1000,
        price_with_tax DECIMAL(14,2)
            GENERATED ALWAYS AS (unit_price * (1 + tax_rate)) VIRTUAL,
        PRIMARY KEY (product_id)
    ) ENGINE = InnoDB;

STORED example:

    CREATE TABLE product_price_stored_demo (
        product_id BIGINT UNSIGNED NOT NULL,
        unit_price DECIMAL(12,2) NOT NULL,
        tax_rate DECIMAL(5,4) NOT NULL DEFAULT 0.1000,
        price_with_tax DECIMAL(14,2)
            GENERATED ALWAYS AS (unit_price * (1 + tax_rate)) STORED,
        PRIMARY KEY (product_id)
    ) ENGINE = InnoDB;

| Criterion | VIRTUAL | STORED |
|---|---|---|
| Stored in row data | No | Yes |
| Evaluation time | When reading the value | When inserting/updating the row |
| Row storage size | Smaller | Increases by column size |
| Write cost | Does not store generated value in row | Must compute and store on write |
| Read cost | May need to evaluate expression on read | Reads stored value |
| Indexing | Can be indexed | Can be indexed |

Which kind to choose depends on read frequency, expression cost, storage size, and workload. VIRTUAL is not always faster or always slower; if an index exists on a virtual generated column, InnoDB still stores the indexed values in the secondary index to serve queries.

### 9.3. Generated Expressions Must Follow Rules

A generated expression is not a place to run arbitrary programs. Expressions are restricted: no subqueries, variables, parameters, or arbitrary stored/loadable functions; functions and operators must satisfy generated-column deterministic rules. Do not use time-dependent functions like NOW() to define a generated column.

Generated columns fit stable expressions derived from data in the same row, for example:

- quantity * unit_price.
- CONCAT(first_name, ' ', last_name).
- LOWER(email) when the email normalization rule is well defined.
- Extracting a value from JSON using allowed functions.

If you need a value that changes over time, depends on external row data, or queries another table, compute it in the application, a trigger, or an appropriate update workflow rather than forcing it into a generated column.

### 9.4. Generated Columns and Indexes

You can create an index on a generated column to support queries filtering by the computed value:

    CREATE INDEX idx_invoice_line_total
    ON invoice_line_generated_demo (line_total);

Then:

    SELECT invoice_line_id, quantity, unit_price, line_total
    FROM invoice_line_generated_demo
    WHERE line_total >= 100.00;

An index can help MySQL locate rows by the generated value. Effectiveness should be verified with EXPLAIN on realistic data. Adding an index also increases storage usage and write overhead.

Generated columns are often useful when the same expression is repeated across many queries and needs a single consistent definition. Do not create generated columns for one-off expressions.

## 10. Distinguishing DEFAULT, AUTO_INCREMENT, and Generated Columns

The three mechanisms serve different purposes:

| Mechanism | Where Does the Value Come From? | Can the Application Send Its Own Value? | Example |
|---|---|---|---|
| DEFAULT | Fixed value or column default expression | Can supply a different valid value | status DEFAULT 'NEW' |
| AUTO_INCREMENT | Table sequence generator | Can omit/pass NULL for auto-generation; can insert explicit ID if valid | order_id BIGINT AUTO_INCREMENT |
| Generated column | Expression from columns in the same row | Cannot assign an arbitrary value; can omit or use DEFAULT | line_total = quantity * unit_price |

Example in a single INSERT:

    INSERT INTO order_line_default_demo
        (order_code, unit_price)
    VALUES
        ('ORD-050', 15.00);

line_id is assigned by AUTO_INCREMENT, quantity and line_status use DEFAULT, line_total is computed from quantity and unit_price, and created_at and updated_at receive the current timestamp.

Do not use DEFAULT as a substitute for a generated column if the value must always reflect the source columns. DEFAULT is applied on insert; a generated column is computed from row data and recalculated whenever source columns change.

## 11. DEFAULT and ON UPDATE CURRENT_TIMESTAMP

DEFAULT CURRENT_TIMESTAMP and ON UPDATE CURRENT_TIMESTAMP are two different behaviors.

- DEFAULT CURRENT_TIMESTAMP: supplies the initial timestamp when INSERT omits the column or specifies DEFAULT.
- ON UPDATE CURRENT_TIMESTAMP: automatically updates the timestamp when another column in the row changes according to MySQL's update rules.

Example:

    CREATE TABLE audit_timestamp_demo (
        record_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        description VARCHAR(200) NOT NULL,
        created_at DATETIME(6) NOT NULL
            DEFAULT CURRENT_TIMESTAMP(6),
        updated_at DATETIME(6) NOT NULL
            DEFAULT CURRENT_TIMESTAMP(6)
            ON UPDATE CURRENT_TIMESTAMP(6),
        PRIMARY KEY (record_id)
    ) ENGINE = InnoDB;

INSERT:

    INSERT INTO audit_timestamp_demo (description)
    VALUES ('Create record');

created_at and updated_at are assigned the current timestamp. When updating description:

    UPDATE audit_timestamp_demo
    SET description = 'Edited'
    WHERE record_id = 1;

updated_at changes automatically to the update timestamp; created_at remains unchanged.

If the application explicitly sets updated_at in the UPDATE, that explicit value is used. If a row is updated without actually changing the value of any other column, the auto-update rule may not trigger as it does when a change occurs; test the exact application statement.

Do not confuse ON UPDATE CURRENT_TIMESTAMP with a generated column. It is an automatic temporal update mechanism when a row changes, not an expression computed from other columns.

## 12. Using DEFAULT in UPDATE

MySQL allows setting a column to its default in an UPDATE using the DEFAULT keyword:

    UPDATE order_line_default_demo
    SET line_status = DEFAULT
    WHERE order_code = 'ORD-050';

line_status reverts to its declared default value, which is NEW.

You can use the DEFAULT(column_name) function in an expression to retrieve the column's default value:

    SELECT DEFAULT(line_status)
    FROM order_line_default_demo
    LIMIT 1;

This is useful when referencing a default inside a SQL expression. Remember that changing a default definition with ALTER TABLE does not automatically modify existing stored rows; UPDATE ... SET column = DEFAULT applies the current default to the updated rows.

## 13. Changing DEFAULT with ALTER TABLE

You can change a column's default value without modifying existing row values:

    ALTER TABLE order_line_default_demo
        ALTER COLUMN line_status SET DEFAULT 'PENDING';

From the moment the change takes effect, INSERTs that omit line_status or specify DEFAULT will use PENDING.

To drop an explicit default:

    ALTER TABLE order_line_default_demo
        ALTER COLUMN line_status DROP DEFAULT;

If the column remains NOT NULL and has no default after DROP DEFAULT, INSERTs omitting the column will need to provide a value in strict mode.

Changing a default does not retroactively update old rows. For example, rows that already have line_status = NEW keep NEW after the default changes to PENDING. If historical data needs normalization, run a separate UPDATE with appropriate conditions and planning.

On large tables, ALTER TABLE can consume resources or require a metadata lock. Consider the MySQL version, applicable DDL algorithm, lock duration, and rollout plan before modifying a production schema.

## 14. INSERT IGNORE Is Not a Substitute for DEFAULT

INSERT IGNORE can downgrade certain errors to warnings and allow the statement to continue with adjusted data or skipped rows depending on the error type. This does not mean every omitted column is handled according to business logic.

Do not use INSERT IGNORE simply to mask missing required columns. If data is invalid, the application needs to know which rows were rejected or which values were altered. Use DEFAULT when you want a default, pass valid values for required columns, and handle duplicate errors with an explicit policy.

After INSERT IGNORE, if used intentionally in an import pipeline, check the affected row count and SHOW WARNINGS. Do not assume all input rows were written successfully.

## 15. Inspecting Results and Metadata

To verify actual values:

    SELECT
        line_id,
        order_code,
        quantity,
        unit_price,
        line_total,
        line_status,
        note,
        created_at,
        updated_at
    FROM order_line_default_demo
    ORDER BY line_id;

To view defaults and generated expressions:

    SHOW CREATE TABLE order_line_default_demo;

You can query INFORMATION_SCHEMA:

    SELECT
        COLUMN_NAME,
        COLUMN_TYPE,
        IS_NULLABLE,
        COLUMN_DEFAULT,
        EXTRA,
        GENERATION_EXPRESSION
    FROM information_schema.columns
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'order_line_default_demo'
    ORDER BY ORDINAL_POSITION;

Useful fields:

| Field | Meaning |
|---|---|
| COLUMN_NAME | Column name |
| COLUMN_TYPE | Full data type |
| IS_NULLABLE | Whether the column allows NULL |
| COLUMN_DEFAULT | Default value displayed by metadata |
| EXTRA | Additional attributes such as auto_increment or generated |
| GENERATION_EXPRESSION | Expression of the generated column |

Metadata display for default expressions may differ from literals depending on the MySQL version. Use SHOW CREATE TABLE to inspect the full DDL definition and verify with a test INSERT in a sandbox.

## 16. Common Mistakes

- Thinking omitting a column is equivalent to passing NULL.
- Thinking passing NULL to a NOT NULL column triggers DEFAULT.
- Omitting a NOT NULL column without DEFAULT and expecting MySQL to pick a sensible business value.
- Disabling strict mode to hide missing-data errors.
- Using implicit defaults like 0 or an empty string without defining their meaning.
- Using DEFAULT expressions on MySQL versions older than 8.0.13.
- Writing a DEFAULT expression that references another column in the same row.
- Confusing DEFAULT with a generated column.
- Trying to assign an arbitrary value to a generated column.
- Assuming VIRTUAL columns cannot be indexed.
- Using AUTO_INCREMENT as gapless sequential document numbers.
- Using SELECT MAX(id) to retrieve the newly inserted ID instead of LAST_INSERT_ID().
- Not understanding the effect of NO_AUTO_VALUE_ON_ZERO when inserting 0 into AUTO_INCREMENT.
- Using INSERT without a column list, making value order dependent on table structure.
- Thinking ALTER TABLE changing a DEFAULT updates existing rows.
- Confusing DEFAULT CURRENT_TIMESTAMP with ON UPDATE CURRENT_TIMESTAMP.
- Using INSERT IGNORE to skip errors without inspecting warnings and actual row counts.

## 17. Checklist for Designing and Using INSERT

- Explicitly listed the columns the application must supply in INSERT.
- Identified which columns have DEFAULT, AUTO_INCREMENT, or a generated expression.
- Supplied values for all NOT NULL columns without an automatic generation mechanism.
- Distinguished omitting a column, DEFAULT, and NULL.
- Checked the deployment environment's SQL mode, especially strict mode.
- Used DEFAULT literals or expressions compatible with the target MySQL version.
- Ensured default expressions do not reference other columns or contain disallowed constructs.
- Chosen VIRTUAL or STORED based on workload and storage requirements.
- Avoided sending arbitrary values to generated columns.
- Used LAST_INSERT_ID() on the same connection when the newly assigned ID is needed.
- Avoided relying on AUTO_INCREMENT for gapless sequences.
- Understood ON UPDATE CURRENT_TIMESTAMP rules.
- Inspected definitions via SHOW CREATE TABLE and INFORMATION_SCHEMA metadata.
- Tested INSERT with omitted columns, DEFAULT, NULL, and missing required columns.
- Checked warnings and affected row counts when using import mechanisms that can ignore errors.

Default values, AUTO_INCREMENT, and generated columns let MySQL populate or compute part of the data during INSERT. To use them safely, clearly distinguish omitted columns from NULL, design DEFAULT around business rules, use AUTO_INCREMENT for identifiers rather than contiguous document numbers, and use generated columns for values derived from columns in the same row. Explicit column lists in INSERT, strict SQL mode, and metadata verification help catch data-entry errors early and keep schemas maintainable.
