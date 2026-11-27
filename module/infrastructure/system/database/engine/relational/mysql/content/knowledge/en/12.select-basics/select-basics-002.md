# Selecting Columns, Expressions, Aliases, and Tableless Queries

This lesson belongs to the **Basic SELECT** chapter of the `DATABASE_MYSQL` module. The module aims at mastering MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, execution plan reading, query optimization, authorization, backup, and handling relational database operations issues. The `SELECT` statement is the foundation for reading data, computing values, presenting results, and quickly testing expressions directly in MySQL.

After this lesson, you will be able to select specific columns or all columns, write expressions in the SELECT list, assign aliases to result columns, understand `NULL` values and expression data types, and use tableless `SELECT` to perform calculations or test functions.

## 1. Basic Structure of SELECT

Common structure:

~~~sql
SELECT
    [ALL | DISTINCT]
    select_expr [, select_expr ...]
[FROM table_name]
[WHERE condition]
[GROUP BY group_expression]
[HAVING group_condition]
[ORDER BY sort_expression [ASC | DESC]]
[LIMIT row_count];
~~~

Where:

- `SELECT` specifies the values or columns to return.
- The `select_expr` list can contain column names, expressions, functions, or literals.
- `FROM` specifies the table or data source.
- `WHERE` filters input rows.
- `GROUP BY` groups rows into groups.
- `HAVING` filters groups.
- `ORDER BY` sorts the results.
- `LIMIT` restricts the number of returned rows.

This lesson focuses on the expression list after `SELECT`, column aliases, and queries without `FROM`. Filtering, grouping, and table join clauses will be covered in depth in subsequent lessons.

A simple query:

~~~sql
SELECT product_id, product_name, price
FROM products;
~~~

MySQL returns the three requested columns from the rows of the `products` table. Unlisted columns will not appear in the result.

### A SELECT Can Return Multiple Expressions

~~~sql
SELECT
    10 AS quantity,
    25.50 AS unit_price,
    10 * 25.50 AS line_total;
~~~

This query does not read any table. It evaluates three expressions and returns one row with three columns.

## 2. Selecting Specific Columns Instead of Everything

### Listing Column Names

The clearest approach is to explicitly list the columns to read:

~~~sql
SELECT product_id, product_name
FROM products;
~~~

Only these two columns are included in the result set. This approach offers several benefits:

- Readers immediately know which data the query needs.
- The application does not receive unused extra columns.
- Reduces network data transfer when tables have many columns or large content columns.
- Less affected when new columns are added to the schema.
- Easier to audit for sensitive data that might be returned unintentionally.

For example, a product listing page only needs ID, name, and price:

~~~sql
SELECT
    product_id,
    product_name,
    price
FROM products;
~~~

There is no need to fetch long descriptions, binary images, or JSON payloads if the screen does not use them.

### Using the Asterisk *

The `*` wildcard asks MySQL to return all columns from the data source:

~~~sql
SELECT *
FROM products;
~~~

It can be used during schema exploration or for quickly inspecting a small table. However, avoid defaulting to `SELECT *` in APIs or production queries because:

- Adding a new column can alter the result structure the application receives.
- It may read large columns, wasting I/O, memory, and bandwidth.
- It may return internal columns or unnecessary sensitive information.
- It makes it harder to identify the exact columns a query depends on.

### Selecting All Columns of One Table in a Multi-Table Query

When a query involves multiple tables, you can combine a table alias with an asterisk:

~~~sql
SELECT
    p.*,
    c.category_name
FROM products AS p
JOIN categories AS c
    ON c.category_id = p.category_id;
~~~

`p.*` selects only the columns of the table aliased as `p`. This is useful when you want all columns from one table and only specific columns from another.

### Qualifying Column References Clearly

A column can be referenced using:

- `column_name`: column name when unambiguous.
- `table_name.column_name`: table name and column name.
- `database_name.table_name.column_name`: database name, table name, and column name.

Example:

~~~sql
SELECT
    products.product_id,
    products.product_name
FROM shop.products;
~~~

When two tables share a column named `id`, specify the table explicitly:

~~~sql
SELECT
    customers.id AS customer_id,
    orders.id AS order_id
FROM customers
JOIN orders
    ON orders.customer_id = customers.id;
~~~

If you reference an unqualified column when multiple tables contain that name, MySQL may raise the error `Column ... is ambiguous`. Adding explicit prefixes makes the query easier to read and prevents column mix-ups.

## 3. Expressions in the SELECT List

Each item after `SELECT` is called a select expression (`select_expr`). An expression can be:

- A column name.
- A numeric, string, date/time, or boolean literal.
- An arithmetic operation.
- A comparison or logical operation.
- A function call.
- A conditional expression such as `CASE`.
- A combination of multiple expressions.

MySQL evaluates the expressions for each input row and returns the values as result columns.

Suppose the `products` table has the following columns:

| Column | Data Type | Meaning |
|---|---|---|
| `product_id` | INT | Product ID |
| `product_name` | VARCHAR(200) | Product name |
| `price` | DECIMAL(12,2) | Selling price |
| `stock_quantity` | INT | Stock quantity |
| `discount_rate` | DECIMAL(5,2) | Discount percentage |
| `description` | VARCHAR(500) | Short description, nullable |
| `category_id` | INT | Category ID |
| `status` | VARCHAR(20) | Product status |

You can calculate the discounted amount directly in SELECT:

~~~sql
SELECT
    product_id,
    product_name,
    price,
    discount_rate,
    price * (1 - discount_rate / 100) AS discounted_price
FROM products;
~~~

The `discounted_price` column is computed when the query runs. It does not create a new column in the `products` table.

### Arithmetic Operations

Common operators:

| Operator | Meaning | Example |
|---|---|---|
| `+` | Addition | `price + 10` |
| `-` | Subtraction | `price - 5` |
| `*` | Multiplication | `price * stock_quantity` |
| `/` | Division | `price / 2` |
| `DIV` | Integer division | `17 DIV 5` |
| `%` or `MOD` | Remainder | `17 % 5` |
| `-` | Negation | `-price` |

Example:

~~~sql
SELECT
    17 + 5 AS addition_result,
    17 - 5 AS subtraction_result,
    17 * 5 AS multiplication_result,
    17 / 5 AS division_result,
    17 DIV 5 AS integer_division_result,
    17 MOD 5 AS remainder_result;
~~~

The result of `/` division can be a decimal number; `DIV` returns the integer quotient according to MySQL integer division rules. Choose an appropriate data type if the result is used for monetary calculations or stored into another column.

### Operator Precedence and Parentheses

MySQL performs multiplication and division before addition and subtraction. When an expression has multiple business steps, use parentheses to make intent explicit:

~~~sql
SELECT
    price * (1 - discount_rate / 100) AS discounted_price
FROM products;
~~~

If parentheses are misplaced or omitted, the evaluation order can produce unexpected results. Especially for financial expressions, verify the `DECIMAL` type, rounding rules, and precision rather than arbitrarily converting to `FLOAT`.

## 4. String Expressions and Common Functions

### Concatenating Strings with CONCAT

In MySQL, use `CONCAT()` to join strings:

~~~sql
SELECT
    CONCAT('MySQL', ' ', 'Database') AS course_name;
~~~

You can concatenate columns:

~~~sql
SELECT
    CONCAT(product_name, ' - ', product_id) AS product_label
FROM products;
~~~

If any argument to `CONCAT()` is `NULL`, the result is usually `NULL`. When you need to replace `NULL` with an empty string or a default value, use `COALESCE()` or `IFNULL()`:

~~~sql
SELECT
    CONCAT(
        product_name,
        ' - ',
        COALESCE(description, 'No description')
    ) AS product_summary
FROM products;
~~~

### CONCAT_WS

`CONCAT_WS(separator, ...)` joins arguments with a separator:

~~~sql
SELECT
    CONCAT_WS(' ', first_name, middle_name, last_name) AS full_name
FROM customers;
~~~

`CONCAT_WS` skips `NULL` arguments after the separator argument. If the separator itself is `NULL`, the result is `NULL`. This differs from `CONCAT()`, where a single `NULL` argument turns the entire result into `NULL`.

### Converting Uppercase and Lowercase

~~~sql
SELECT
    UPPER(product_name) AS uppercase_name,
    LOWER(product_name) AS lowercase_name
FROM products;
~~~

Results are affected by the character set and MySQL's character handling. For Unicode text, use an appropriate charset such as `utf8mb4`.

### Character Length vs. Byte Length

`CHAR_LENGTH()` returns the number of characters; `LENGTH()` returns the number of bytes:

~~~sql
SELECT
    'Cơ sở dữ liệu' AS sample_text,
    CHAR_LENGTH('Cơ sở dữ liệu') AS character_count,
    LENGTH('Cơ sở dữ liệu') AS byte_count;
~~~

With UTF-8, a single character can occupy multiple bytes. Do not use `LENGTH()` to count user-visible characters.

## 5. Conditional Expressions: CASE, IF, and NULL

### CASE

`CASE` produces values across multiple conditional branches:

~~~sql
SELECT
    product_id,
    product_name,
    stock_quantity,
    CASE
        WHEN stock_quantity = 0 THEN 'Out of stock'
        WHEN stock_quantity < 10 THEN 'Low stock'
        ELSE 'In stock'
    END AS stock_status
FROM products;
~~~

You can also use the simple comparison form against a single expression:

~~~sql
SELECT
    CASE 'A'
        WHEN 'A' THEN 'Active'
        WHEN 'I' THEN 'Inactive'
        ELSE 'Unknown'
    END AS status_label;
~~~

The `THEN`/`ELSE` branches return values whose type MySQL aggregates across the branches. If branches have incompatible types, MySQL may convert the result type. Return values of consistent types and clear formats.

### IF

The `IF(condition, value_if_true, value_if_false)` function returns one of two values:

~~~sql
SELECT
    product_name,
    IF(stock_quantity > 0, 'In stock', 'Out of stock') AS availability
FROM products;
~~~

If the condition is `NULL`, MySQL treats it as not true and selects the third branch. For multi-branch logic or greater clarity, `CASE` is usually easier to read.

### NULL Is Neither 0 Nor an Empty String

`NULL` represents an unknown or missing value. It is distinct from:

- The number `0`.
- The empty string `''`.
- A string containing spaces.
- The value `FALSE`.

Arithmetic expressions with `NULL` typically return `NULL`:

~~~sql
SELECT
    NULL + 10 AS arithmetic_result,
    CONCAT('Product: ', NULL) AS concat_result;
~~~

The result of both expressions is `NULL`.

Do not test for `NULL` using the `=` operator:

~~~sql
-- Incorrect way to check for NULL
SELECT NULL = NULL AS comparison_result;
~~~

The comparison result is `NULL` (`UNKNOWN`), not `TRUE`. Use:

~~~sql
SELECT
    NULL IS NULL AS is_null,
    NULL IS NOT NULL AS is_not_null;
~~~

### COALESCE and IFNULL

`COALESCE(v1, v2, ...)` returns the first non-`NULL` argument:

~~~sql
SELECT
    product_name,
    COALESCE(description, 'No description') AS display_description
FROM products;
~~~

`IFNULL(value, replacement)` takes two arguments and replaces `NULL` with the fallback value:

~~~sql
SELECT
    product_name,
    IFNULL(description, 'No description') AS display_description
FROM products;
~~~

Use `COALESCE` when there are multiple fallback options; use `IFNULL` when there is only one replacement value.

### NULL-Safe Equality

MySQL provides the `<=>` operator for null-safe comparison:

~~~sql
SELECT
    NULL <=> NULL AS both_null,
    10 <=> NULL AS one_null,
    10 <=> 10 AS same_value;
~~~

The results are `1`, `0`, and `1` respectively. This operator is useful when comparing two values while still wanting to match when both are `NULL`.

## 6. Type Casting and Conversion in Expressions

MySQL can automatically convert types when expressions combine numbers, strings, and dates/times. This is implicit conversion. It is convenient but can also produce unpredictable results when data is inconsistent.

Example:

~~~sql
SELECT
    '10' + 5 AS numeric_result,
    CONCAT('10', 5) AS string_result;
~~~

In an addition expression, the string may be converted to a number. In `CONCAT`, the arguments are treated as strings for concatenation.

If the string is not numeric:

~~~sql
SELECT
    'abc' + 5 AS converted_result;
~~~

MySQL may convert the non-numeric string portion to `0` and emit a Warning depending on context. Do not rely on implicit conversion to handle invalid input data.

### CAST

Use `CAST(expr AS type)` to request an explicit conversion:

~~~sql
SELECT
    CAST('125.75' AS DECIMAL(10,2)) AS amount,
    CAST('2026-11-19' AS DATE) AS report_date,
    CAST(123 AS CHAR) AS text_value;
~~~

Common target types include:

- `SIGNED`, `UNSIGNED`
- `DECIMAL(p,s)`
- `CHAR`
- `DATE`
- `DATETIME`
- `TIME`
- `JSON`

You can also use `CONVERT(expr, type)` or `CONVERT(expr USING charset)` for certain type-casting or character-set conversion goals.

Casting does not guarantee that all data converts validly. Check Warnings, SQL mode, and post-conversion outputs when processing unclean data.

## 7. Column Aliases with AS

An alias names a result column of a `SELECT`. An alias does not rename the actual column in the table and does not create a new column in the schema.

~~~sql
SELECT
    product_name AS name,
    price AS unit_price,
    price * stock_quantity AS inventory_value
FROM products;
~~~

The result has headers:

- `name`
- `unit_price`
- `inventory_value`

Aliases are especially useful for long expressions, reports, and data returned to applications.

An alias is also not an intermediate variable that can be immediately reused in another expression within the same `SELECT` list. For example, you cannot write `price * stock_quantity AS inventory_value` and then reference `inventory_value + 10` in the next expression of the same `SELECT`. Repeat the expression or wrap the query in a derived table/CTE if you need to reuse that name.

### Write AS Explicitly

MySQL allows omitting the `AS` keyword:

~~~sql
SELECT
    product_name name,
    price unit_price
FROM products;
~~~

However, use `AS` for readability and to avoid missing-comma bugs:

~~~sql
-- price may be interpreted as an alias for product_name
SELECT product_name price
FROM products;
~~~

If the intent is to select two columns, the correct query is:

~~~sql
SELECT
    product_name,
    price
FROM products;
~~~

### Aliases Can Contain Spaces

If you need a header with spaces, quote the identifier using backticks:

~~~sql
SELECT
    product_name AS `Product name`,
    price * stock_quantity AS `Inventory value`
FROM products;
~~~

For alias names with special characters or colliding with keywords, backticks tell MySQL it is an identifier. Avoid using single quotes to reference an alias in other clauses because single quotes are interpreted as string literals there.

### Where Can Aliases Be Used?

MySQL allows referencing expression aliases in:

- `ORDER BY`
- `GROUP BY`
- `HAVING`

Example:

~~~sql
SELECT
    product_name,
    price * stock_quantity AS inventory_value
FROM products
ORDER BY inventory_value DESC;
~~~

You cannot use a `SELECT`-list alias in `WHERE`:

~~~sql
-- Invalid: alias is not yet defined when WHERE is processed
SELECT
    product_name,
    price * stock_quantity AS inventory_value
FROM products
WHERE inventory_value > 1000;
~~~

Repeat the expression or use a subquery/CTE when you want to name a computed value and then filter in an outer layer:

~~~sql
SELECT *
FROM (
    SELECT
        product_name,
        price * stock_quantity AS inventory_value
    FROM products
) AS product_values
WHERE inventory_value > 1000;
~~~

### Avoid Aliases That Match Column Names

Do not give an alias the same name as another column in the same data source. When MySQL resolves names in `ORDER BY`, `GROUP BY`, or `HAVING`, a conflict between a column name and an alias can make the query confusing or emit a Warning.

Choose clear, unique names within the `SELECT` list, such as `calculated_total`, `customer_label`, `stock_status`.

## 8. SELECT Without FROM

MySQL can evaluate expressions without reading a table:

~~~sql
SELECT 1 + 1;
~~~

Result:

~~~text
+-------+
| 1 + 1 |
+-------+
|     2 |
+-------+
~~~

Some useful examples:

~~~sql
SELECT
    VERSION() AS mysql_version,
    CURRENT_USER() AS authenticated_account,
    DATABASE() AS current_database,
    NOW() AS current_time;
~~~

These functions return the server version, effective MySQL account, currently selected database, and session timestamp.

A `SELECT` that only evaluates expressions without reading tables does not require the `SELECT` privilege on a database/table. The `SELECT` privilege is checked when the statement actually accesses a table or view.

### Quick Calculations

~~~sql
SELECT
    1250 * 1.08 AS price_with_tax,
    100 DIV 7 AS whole_groups,
    100 MOD 7 AS remainder;
~~~

### Testing Functions and Expressions

~~~sql
SELECT
    UPPER('mysql') AS upper_text,
    CHAR_LENGTH('Cơ sở dữ liệu') AS character_count,
    ROUND(123.4567, 2) AS rounded_value,
    COALESCE(NULL, NULL, 'fallback') AS fallback_value;
~~~

### Checking Session Variables

~~~sql
SELECT
    @@SESSION.sql_mode AS session_sql_mode,
    @@SESSION.time_zone AS session_time_zone,
    @@SESSION.autocommit AS session_autocommit;
~~~

System variables can be read with the `@@variable_name` syntax. Use `@@SESSION` or `@@GLOBAL` when you want to specify the scope explicitly.

### What Is DUAL?

You can write:

~~~sql
SELECT 1 + 1 FROM DUAL;
~~~

`DUAL` is a dummy table name for compatibility with certain other database systems. MySQL does not require `FROM DUAL` when a query references no tables:

~~~sql
SELECT 1 + 1;
~~~

Both approaches produce the same result in this example. In MySQL, prefer `SELECT` without `FROM` to keep statements concise and clearly show there is no source table. `DUAL` is only needed when maintaining syntactic compatibility or migrating queries across database engines.

### How Many Rows Does SELECT Without FROM Return?

A `SELECT` consisting of constant expressions or functions, with no `FROM` and no row-eliminating condition, returns one row:

~~~sql
SELECT 'MySQL' AS database_name, 9 + 7 AS version_major_minor;
~~~

The result has one row and two columns.

If a `WHERE` condition evaluates to false, the result can have zero rows:

~~~sql
SELECT 1 AS value
WHERE 1 = 0;
~~~

A `SELECT` without `FROM` is still a query; it simply does not need a table as its data source.

## 9. ALL, DISTINCT, and Duplicate Results

By default, `SELECT` uses `ALL`, meaning duplicate rows are retained:

~~~sql
SELECT ALL category_id
FROM products;
~~~

The `ALL` keyword can be omitted because it is the default.

Use `DISTINCT` to remove duplicate rows across the selected column set:

~~~sql
SELECT DISTINCT category_id
FROM products;
~~~

When selecting multiple columns, MySQL removes rows only when the entire selected combination of values is duplicated:

~~~sql
SELECT DISTINCT
    category_id,
    status
FROM products;
~~~

This differs from deduplicating by `category_id` alone. If the category is the same but the status differs, both rows are kept.

You can use `DISTINCT` on expressions:

~~~sql
SELECT DISTINCT
    LOWER(product_name) AS normalized_name
FROM products;
~~~

`DISTINCT` does not automatically sort results in business order. If you need a stable order, use `ORDER BY` explicitly.

## 10. SELECT Results Have No Default Order

Without `ORDER BY`, MySQL does not guarantee row ordering. Any observed order can change depending on indexes, execution plans, data changes, version, or server activity.

Application code should not assume:

~~~sql
SELECT product_id, product_name
FROM products;
~~~

will always return rows in ascending `product_id` order just because the data currently appears that way.

If order matters, specify it:

~~~sql
SELECT product_id, product_name
FROM products
ORDER BY product_id ASC;
~~~

For stable pagination, use a unique sort key or add a secondary tie-breaker key:

~~~sql
SELECT product_id, product_name
FROM products
ORDER BY product_name ASC, product_id DESC
LIMIT 20;
~~~

Do not rely on physical row order or index order if the query does not request sorting.

## 11. Combined Example: Building Output for a List Screen

Suppose a product management page needs to display:

- Product ID.
- Product name.
- Current price.
- Discounted price.
- Inventory status.
- Display label for the user.

You can write:

~~~sql
SELECT
    p.product_id AS id,
    p.product_name AS name,
    p.price AS original_price,
    p.price * (1 - p.discount_rate / 100) AS discounted_price,
    CASE
        WHEN p.stock_quantity <= 0 THEN 'Out of stock'
        WHEN p.stock_quantity < 10 THEN 'Low stock'
        ELSE 'In stock'
    END AS stock_status,
    CONCAT(
        p.product_name,
        ' (#',
        p.product_id,
        ')'
    ) AS display_label
FROM products AS p
ORDER BY p.product_name ASC, p.product_id ASC
LIMIT 50;
~~~

Notable points:

- Only the required columns are selected.
- The price calculation expression has a clear alias.
- `CASE` produces stock status based on inventory.
- `CONCAT` formats the display label.
- `ORDER BY` defines the order.
- `LIMIT` caps the number of returned rows.

If `discount_rate` can be `NULL`, the calculation `price * (1 - discount_rate / 100)` can also return `NULL`. When business logic treats `NULL` as no discount, intentionally use `COALESCE(discount_rate, 0)`.

## 12. Hands-On Practice: Expressions, Aliases, and Tableless SELECT

The following statements use a dedicated lab database.

### Step 1: Calculations Without a Table

~~~sql
SELECT
    250 * 1.08 AS price_after_tax,
    250 DIV 7 AS full_groups,
    250 MOD 7 AS remaining_units;
~~~

Explain the result of each expression and distinguish `/` division from `DIV`.

### Step 2: Testing String Functions and NULL

~~~sql
SELECT
    CONCAT('MySQL', ' ', 'Lab') AS course_name,
    CONCAT('Name: ', NULL) AS concat_with_null,
    CONCAT_WS(' ', 'Nguyen', NULL, 'An') AS concat_ws_result,
    COALESCE(NULL, NULL, 'default') AS fallback_value,
    CHAR_LENGTH('Cơ sở dữ liệu') AS character_count,
    LENGTH('Cơ sở dữ liệu') AS byte_count;
~~~

Observe how `CONCAT` and `CONCAT_WS` handle `NULL`, and compare character count versus byte count.

### Step 3: Creating the Test Table

~~~sql
CREATE DATABASE IF NOT EXISTS mysql_select_basics_lab;
USE mysql_select_basics_lab;

CREATE TABLE products (
    product_id INT NOT NULL PRIMARY KEY,
    product_name VARCHAR(100) NOT NULL,
    price DECIMAL(10,2) NOT NULL,
    discount_rate DECIMAL(5,2) NULL,
    stock_quantity INT NOT NULL,
    description VARCHAR(500) NULL,
    category_id INT NOT NULL,
    status VARCHAR(20) NOT NULL
) ENGINE=InnoDB;

INSERT INTO products
    (product_id, product_name, price, discount_rate, stock_quantity,
     description, category_id, status)
VALUES
    (1, 'Keyboard', 850000.00, 10.00, 25, 'Mechanical keyboard', 1, 'A'),
    (2, 'Mouse', 250000.00, 5.00, 6, NULL, 1, 'A'),
    (3, 'Monitor', 4200000.00, NULL, 0, '27-inch monitor', 2, 'I'),
    (4, 'USB Hub', 320000.00, 0.00, 80, 'USB-C hub', 1, 'A');
~~~

### Step 4: Selecting Specific Columns

~~~sql
SELECT product_id, product_name
FROM products;
~~~

Compare with:

~~~sql
SELECT *
FROM products;
~~~

List the extra columns returned by the asterisk.

### Step 5: Computing Expressions and Assigning Aliases

~~~sql
SELECT
    product_name AS name,
    price AS original_price,
    price * (1 - COALESCE(discount_rate, 0) / 100) AS final_price,
    stock_quantity * price AS inventory_value
FROM products;
~~~

Explain why `COALESCE(discount_rate, 0)` gives the Monitor row a discounted price equal to its original price.

### Step 6: Using an Alias in ORDER BY

~~~sql
SELECT
    product_name,
    price * stock_quantity AS inventory_value
FROM products
ORDER BY inventory_value DESC;
~~~

Try replacing the alias with the full expression. Observe whether the result changes.

### Step 7: Testing the Error of Referencing an Alias in WHERE

The following statement is invalid:

~~~sql
SELECT
    product_name,
    price * stock_quantity AS inventory_value
FROM products
WHERE inventory_value > 1000000;
~~~

Rewrite it using the expression:

~~~sql
SELECT
    product_name,
    price * stock_quantity AS inventory_value
FROM products
WHERE price * stock_quantity > 1000000;
~~~

Or use a derived table:

~~~sql
SELECT *
FROM (
    SELECT
        product_name,
        price * stock_quantity AS inventory_value
    FROM products
) AS product_values
WHERE inventory_value > 1000000;
~~~

### Step 8: Testing DISTINCT

~~~sql
SELECT DISTINCT discount_rate
FROM products;
~~~

Try:

~~~sql
SELECT DISTINCT discount_rate, stock_quantity
FROM products;
~~~

Explain why the row counts of the two queries can differ.

### Step 9: Cleanup

~~~sql
DROP DATABASE mysql_select_basics_lab;
~~~

Run this only on the lab database you just created. The command deletes all practice tables and data.

## 13. Common Mistakes and Misconceptions

| Symptom | Cause | Solution |
|---|---|---|
| `Unknown column` in SELECT | Wrong column name or column does not belong to the data source | Check column name and table qualification |
| `Column ... is ambiguous` | Multiple tables have the same column name | Use `table_name.column_name` or a table alias |
| Alias cannot be used in WHERE | WHERE is processed before alias values in SELECT | Repeat the expression or use a derived table/CTE |
| Alias not recognized as expected | Missing comma causes the next expression to be parsed as an alias | Add the comma and write `AS` explicitly |
| Numeric result differs from expectation | Implicit type conversion or operator precedence | Use `CAST` and explicit parentheses |
| Expression evaluates to NULL | An operand is NULL or a function propagates NULL | Use `IS NULL`, `COALESCE`, or `IFNULL` per business rules |
| CONCAT returns NULL | Contains a NULL argument | Use `CONCAT_WS` or intentionally replace NULL |
| DISTINCT still returns multiple rows | The full combination of selected columns is not duplicated | Choose the exact column set to deduplicate |
| Row order changes | No `ORDER BY` | Specify `ORDER BY` with clear sort keys |
| `SELECT *` returns excessive data | Fetching unnecessary columns | List specific columns |

## 14. Key Principles to Remember

1. The list after `SELECT` can contain column names, literals, operations, functions, and conditional expressions.
2. Select only the columns you need; only use `*` when you genuinely want all columns.
3. When multiple tables share column names, qualify them with table names or table aliases.
4. Use `AS` explicitly to assign aliases to result columns and expressions.
5. An alias is a name in the result set; it does not alter the schema.
6. Aliases can be used in `ORDER BY`, `GROUP BY`, and `HAVING` under MySQL rules; do not use them directly in `WHERE`.
7. `NULL` is different from `0` and an empty string; use `IS NULL`, `COALESCE`, `IFNULL`, or `<=>` as appropriate.
8. Use `CAST` when explicit conversion is needed and check Warnings during data conversion.
9. `SELECT` without `FROM` can be used for calculations, testing functions, and inspecting system variables; `DUAL` is optional.
10. Without `ORDER BY`, there is no guarantee of row order.
11. `DISTINCT` removes duplicate rows based on the entire list of selected expressions.
12. In applications, return only necessary columns to reduce data transfer and avoid exposing unintended information.

## Official References

The syntax and behavior in this lesson are verified against the **MySQL 9.7 Reference Manual** as of **19-11-2026**:

1. [SELECT Statement](https://dev.mysql.com/doc/refman/9.7/en/select.html): expression lists, column selection, tableless `SELECT`, `DUAL`, `DISTINCT`, `ORDER BY`, and `LIMIT`.
2. [Problems with Column Aliases](https://dev.mysql.com/doc/refman/9.7/en/problems-with-alias.html): alias scope and why aliases cannot be used in `WHERE`.
3. [Expressions](https://dev.mysql.com/doc/refman/9.7/en/expressions.html): expressions, operators, and how MySQL evaluates values.
4. [Type Conversion in Expression Evaluation](https://dev.mysql.com/doc/refman/9.7/en/type-conversion.html): implicit type conversion in expressions.
5. [Flow Control Functions](https://dev.mysql.com/doc/refman/9.7/en/flow-control-functions.html): `CASE`, `IF`, `IFNULL`, and `COALESCE`.
6. [String Functions](https://dev.mysql.com/doc/refman/9.7/en/string-functions.html): `CONCAT`, `CONCAT_WS`, `LENGTH`, `CHAR_LENGTH`, `UPPER`, and `LOWER`.
7. [NULL Values](https://dev.mysql.com/doc/refman/9.7/en/working-with-null.html): `NULL` semantics and `NULL` checks.
8. [Privileges Provided by MySQL](https://dev.mysql.com/doc/refman/9.7/en/privileges-provided.html): `SELECT` privilege when reading tables vs. `SELECT` without table access.
