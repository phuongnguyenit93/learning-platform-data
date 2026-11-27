# SELECT, Column Lists, Aliases, and Expressions in PostgreSQL

When working with PostgreSQL, the `SELECT` statement is usually the starting point for every data-reading operation: retrieving a list of products, displaying an order, calculating a discounted selling price, presenting readable labels for a report, or transforming raw data into results a Java application can use. To write good queries, you need to know more than just `SELECT * FROM ...`—you also need to understand the **select list**, **output column names**, **aliases**, and how PostgreSQL determines the data type of each expression.

For example, given a single table containing `unit_price`, `stock_quantity`, and `discount_pct`, we can return:

```sql
SELECT
    product_name AS product,
    unit_price AS listed_price,
    ROUND(
        unit_price * (1 - COALESCE(discount_pct, 0) / 100),
        2
    ) AS discounted_price,
    unit_price * stock_quantity AS inventory_value
FROM select_lab.products;
```

The query above does not create four new columns in the table. It **produces four columns in the query result**, two of which are values computed from the source columns. This lesson helps clearly distinguish between stored data and values that exist only in the `SELECT` output.

Learning objectives for this lesson:

1. Write valid `SELECT` syntax with explicit column lists, `*`, and expressions without `FROM`.
2. Understand source columns, output names, and aliases with or without `AS`.
3. Use arithmetic, text, date, and boolean expressions, functions, `CASE`, `COALESCE`, and type casting.
4. Properly handle `NULL`, data types, and expressions that can cause errors.
5. Know that aliases can be referenced in `ORDER BY` and `GROUP BY`, and why they cannot be used directly in `WHERE`.
6. Distinguish between `SELECT`, `DISTINCT`, aggregate expressions, and row-ordering limitations.
7. Read common errors and choose stable query patterns for real-world applications.

The examples use modern PostgreSQL and focus on widely supported SQL syntax. Specific features are noted when needed; verify your PostgreSQL Server version if your operating environment differs from your study machine.

## 1. Basic Shape of SELECT

A simple `SELECT` statement typically looks like this:

```sql
SELECT
    expression_1 [AS alias_1],
    expression_2 [AS alias_2],
    ...
FROM schema_name.table_name
WHERE condition
ORDER BY sort_column
LIMIT row_count;
```

In this general example, `[ ... ]` denotes optional components and `...` is a placeholder rather than complete SQL code meant to be run verbatim.

The clauses have distinct roles:

| Component | Role |
| --- | --- |
| `SELECT` | Specifies **which columns or expressions** are returned. |
| Select list | Can include column names, constants, calculations, function calls, `CASE`, or other expressions. |
| `AS alias` | Assigns an output name to an expression/column; does not rename the column in the table. |
| `FROM` | Specifies the row source, typically a table, view, JOIN, or subquery. |
| `WHERE` | Filters rows based on a condition before producing the final select result according to SQL semantics. |
| `GROUP BY` | Groups rows together when using aggregates. |
| `HAVING` | Filters groups after aggregation. |
| `ORDER BY` | Defines how output rows are sorted. |
| `LIMIT` and `OFFSET` | Limits/positions a subset of results; usually paired with a deterministic `ORDER BY`. |

You do not need to understand every clause to get started. Focus on **the part after `SELECT` and before `FROM`**: that is the list of expressions PostgreSQL turns into output columns.

### 1.1. SELECT Returns a Result Relation

The query:

```sql
SELECT
    product_id,
    product_name,
    unit_price
FROM select_lab.products;
```

returns a set of rows with **three columns**, not necessarily all columns of the table. If the table also has `created_at` or `is_active`, they do not automatically appear in the result above.

The **number of output columns** is determined by the `SELECT` list. The **number of output rows** is affected by the data source and clauses such as `WHERE`, `GROUP BY`, `DISTINCT`, or `LIMIT`.

### 1.2. SQL Does Not Guarantee Row Order Without ORDER BY

```sql
SELECT product_id, product_name
FROM select_lab.products;
```

may display rows in ascending ID order in one run, but there is no guarantee it will stay that way. PostgreSQL may change the scan plan, use a different index, or execute in parallel. To get results in a specific order:

```sql
SELECT product_id, product_name
FROM select_lab.products
ORDER BY product_id;
```

Do not confuse **the order of columns in the select list** (determined by how you write it) with **the order of rows** (which requires `ORDER BY`).

## 2. Preparing Practice Data

To keep the examples self-contained, create the `select_lab` schema and the `products` table. Run this on a dedicated PostgreSQL lab instance, not on a production database.

```sql
CREATE SCHEMA IF NOT EXISTS select_lab;

CREATE TABLE select_lab.products (
    product_id bigint PRIMARY KEY,
    sku text NOT NULL UNIQUE,
    product_name text NOT NULL,
    category_code text NOT NULL,
    unit_price numeric(12, 2) NOT NULL
        CHECK (unit_price >= 0),
    stock_quantity integer NOT NULL
        CHECK (stock_quantity >= 0),
    discount_pct numeric(5, 2)
        CHECK (discount_pct BETWEEN 0 AND 100),
    is_active boolean NOT NULL DEFAULT true,
    created_at date NOT NULL
);
```

Insert sample data:

```sql
INSERT INTO select_lab.products (
    product_id, sku, product_name, category_code,
    unit_price, stock_quantity, discount_pct,
    is_active, created_at
)
VALUES
    (101, 'BOOK-SQL', 'Practical SQL Book', 'books',
     180000.00, 12, 10.00, true, DATE '2026-10-01'),
    (102, 'BOOK-PG', 'PostgreSQL Basics', 'books',
     240000.00, 5, NULL, true, DATE '2026-10-03'),
    (103, 'PEN-BLUE', 'Blue Pen', 'stationery',
     12000.00, 0, 0.00, true, DATE '2026-10-04'),
    (104, 'NOTE-A5', 'A5 Notebook', 'stationery',
     45000.00, 20, 5.00, true, DATE '2026-10-05'),
    (105, 'BAG-01', 'Book Bag', 'accessories',
     95000.00, 3, 15.00, false, DATE '2026-10-06'),
    (106, 'MUG-01', 'Ceramic Mug', 'accessories',
     110000.00, 8, NULL, true, DATE '2026-10-07');
```

Sample dataset:

| ID | SKU | Product Name | Category | Price | Stock | Discount (%) | Active |
| ---: | --- | --- | --- | ---: | ---: | ---: | --- |
| 101 | BOOK-SQL | Practical SQL Book | books | 180000 | 12 | 10 | true |
| 102 | BOOK-PG | PostgreSQL Basics | books | 240000 | 5 | NULL | true |
| 103 | PEN-BLUE | Blue Pen | stationery | 12000 | 0 | 0 | true |
| 104 | NOTE-A5 | A5 Notebook | stationery | 45000 | 20 | 5 | true |
| 105 | BAG-01 | Book Bag | accessories | 95000 | 3 | 15 | false |
| 106 | MUG-01 | Ceramic Mug | accessories | 110000 | 8 | NULL | true |

Here, `discount_pct = NULL` means no discount percentage has been recorded yet, **not automatically that the discount is 0%**. When practicing price calculations, this lesson uses an illustrative business assumption that `NULL` is temporarily treated as 0; real systems must explicitly decide this semantics.

The `CREATE TABLE` and `INSERT` statements only need to be run once on an empty schema. If you repeat `INSERT` with the same `product_id` or `sku`, PostgreSQL will report a primary key / unique constraint violation.

## 3. SELECT Does Not Require FROM

PostgreSQL allows a `SELECT` containing only one or more expressions without reading rows from a table.

```sql
SELECT 1;
```

```sql
SELECT
    10 + 20 AS sum_result,
    3 * 7 AS multiply_result,
    'Hello PostgreSQL' AS greeting;
```

Result:

| sum_result | multiply_result | greeting |
| ---: | ---: | --- |
| 30 | 21 | Hello PostgreSQL |

Another example:

```sql
SELECT
    CURRENT_DATE AS today,
    CURRENT_TIMESTAMP AS current_timestamp_value,
    100::numeric / 4 AS quarter_value;
```

When there is no `FROM`, a basic `SELECT` returns a single row containing the results of the expressions. Date and time values depend on the current time and session time zone, so the output on your machine may differ from someone else's illustrative date.

### When Is SELECT Without FROM Useful?

- Testing the syntax of functions and operators.
- Trying out type casting, string formatting, or date arithmetic.
- Querying current session setting values:

```sql
SELECT
    current_database() AS database_name,
    current_user AS role_name,
    current_setting('server_version') AS server_version;
```

- Constructing a single result row containing parameters or initial values.

Do not use `SELECT` as a substitute for operations that modify tables. A computed expression only produces an **output value**; it does not write data back to the table.

## 4. Column Lists: Explicitly Selecting What to Return

A select list can contain one or more items separated by commas:

```sql
SELECT
    product_id,
    sku,
    product_name
FROM select_lab.products
ORDER BY product_id;
```

You can change the column order:

```sql
SELECT
    product_name,
    product_id,
    sku
FROM select_lab.products
ORDER BY product_id;
```

The second query reads the same fields, but the column order in the result is product name, ID, then SKU. The physical column order in the table does not have to be the output order.

### 4.1. A Column Can Be Selected Multiple Times

```sql
SELECT
    product_name,
    product_name AS display_name
FROM select_lab.products
WHERE product_id = 101;
```

The result has two columns with the same value but different output names:

| product_name | display_name |
| --- | --- |
| Practical SQL Book | Practical SQL Book |

SQL allows duplicate expressions in the select list. However, repeating data is usually unnecessary unless it serves formatting, comparison, or a specific API contract.

### 4.2. Trailing Commas and Syntax Errors

Incorrect example:

```sql
-- Incorrect: trailing comma in the column list.
-- SELECT product_id, product_name,
-- FROM select_lab.products;
```

Do not confuse commas that separate **output expressions** with commas inside a function's argument list:

```sql
SELECT
    ROUND(unit_price, 0) AS rounded_price,
    COALESCE(discount_pct, 0) AS effective_discount
FROM select_lab.products;
```

In `ROUND(unit_price, 0)`, the comma separates the two function arguments; the comma after `AS rounded_price` separates two expressions in the select list.

## 5. SELECT *: When Is It Convenient, and When Should You Avoid It?

The `*` symbol represents **all columns of the row source** in the query context.

```sql
SELECT *
FROM select_lab.products
ORDER BY product_id;
```

For the lab table, the result contains all nine declared columns: `product_id`, `sku`, `product_name`, `category_code`, `unit_price`, `stock_quantity`, `discount_pct`, `is_active`, and `created_at`.

### 5.1. Advantages

- Quickly exploring an unfamiliar table in a learning environment.
- Inspecting data during short-term debugging.
- Quickly verifying results after inserting test data.

### 5.2. Drawbacks in Real Applications

| Risk | Impact |
| --- | --- |
| Fetching unnecessary columns | Increases the amount of data transferred, processed, or serialized. |
| Schema changes | Adding columns can change the shape of the `SELECT *` result. |
| Sensitive data | Accidentally exposes unnecessary information to the application/API layer. |
| Joining multiple tables | Can produce multiple columns with the same name, making ResultSet/DTO handling difficult. |
| Unclear API contract | Hard to tell which service depends on which column. |
| Large JSONB/text data | May read and transfer large payloads even when the screen only needs an ID/name. |

In APIs and frequently executed queries, list the required columns explicitly:

```sql
SELECT product_id, sku, product_name, unit_price
FROM select_lab.products
WHERE is_active = true
ORDER BY product_id;
```

Using `SELECT *` while debugging is not wrong, but turning it into a long-term data interface usually makes queries less clear and harder to control.

### 5.3. table_alias.*

When using a table alias, you can select all columns from one specific source:

```sql
SELECT p.*
FROM select_lab.products AS p
WHERE p.category_code = 'books';
```

`p.*` expands to the columns of source `p`. In queries with multiple tables, `p.*` distinguishes that source's columns from `*`, which retrieves columns from all sources present in the select list.

Even so, `p.*` still carries the wildcard drawback when the table schema changes. If you only need three columns, writing all three explicitly remains easier to maintain.

## 6. Column Aliases: AS Renames the Output, Not the Schema

A column alias is the name a query assigns to an output expression.

```sql
SELECT
    product_id AS id,
    product_name AS name,
    unit_price AS price
FROM select_lab.products
WHERE product_id = 101;
```

Result:

| id | name | price |
| ---: | --- | ---: |
| 101 | Practical SQL Book | 180000.00 |

The names `id`, `name`, and `price` exist only in this query result. The `select_lab.products` table still has its original column names such as `product_name` and `unit_price`.

### 6.1. AS Can Be Omitted, but Using It Is Recommended for Column Aliases

The following two forms can be equivalent:

```sql
SELECT product_name AS display_name
FROM select_lab.products;
```

```sql
SELECT product_name display_name
FROM select_lab.products;
```

In simple queries, PostgreSQL allows omitting `AS`. However, writing `AS` explicitly helps readers distinguish the **output name** from the next part of an expression, especially when the select list is long.

### 6.2. Aliasing Expressions Is Good Practice

```sql
SELECT
    product_id,
    unit_price * stock_quantity AS inventory_value
FROM select_lab.products;
```

Without an alias, PostgreSQL infers an output name when possible or displays a default name like `?column?` for certain expressions. Auto-generated names should not be treated as a stable contract for Java DTOs or reports.

### 6.3. Aliases with Spaces or Uppercase Letters

To set a human-readable display name with spaces or mixed case:

```sql
SELECT
    product_name AS "Product Name",
    unit_price AS "Listed Price"
FROM select_lab.products
ORDER BY product_id;
```

Double quotes `"..."` enclose a SQL **identifier**. They allow an alias containing spaces, accented characters, or uppercase letters to be preserved as intended.

Conversely:

```sql
SELECT product_name AS 'Product Name'
FROM select_lab.products;
```

is not a valid way to define an alias: single quotes denote a **SQL string literal**, not a quoted identifier.

In queries serving an API, it is usually better to use stable technical aliases like `product_name` or `discounted_price`; user-facing display labels in natural language should be decided at the UI layer when localization is needed.

## 7. Distinguishing Column Names, Table Aliases, and Schemas

A table can be referenced by its fully qualified name:

```sql
SELECT select_lab.products.product_name
FROM select_lab.products;
```

However, this is verbose and inconvenient when queries grow complex. We usually define a **table alias**:

```sql
SELECT
    p.product_id,
    p.product_name,
    p.unit_price
FROM select_lab.products AS p
WHERE p.is_active = true;
```

Here:

- `select_lab`: the schema name.
- `products`: the table name inside that schema.
- `p`: the alias for the row source in the query.
- `p.product_name`: the `product_name` column from source `p`.
- `AS p`: assigns a **table** alias, not a column alias.

Once you define the table alias `p`, use `p.column_name` consistently in the relevant parts of the query, especially with JOINs or column names that could collide.

### 7.1. Two Types of Aliases Have Different Scopes

```sql
SELECT
    p.product_name AS display_name,
    p.unit_price AS price
FROM select_lab.products AS p;
```

`p` is the name used **to reference the data source** within the query. `display_name` and `price` are **output names**. Do not assume that writing `AS display_name` makes `p.display_name` an existing column.

### 7.2. Ambiguous Columns with Multiple Sources

For example, joining the products table with an inline category lookup table created with `VALUES`:

```sql
SELECT
    p.product_id,
    p.product_name,
    c.category_label
FROM select_lab.products AS p
JOIN (
    VALUES
        ('books', 'Books'),
        ('stationery', 'Stationery'),
        ('accessories', 'Accessories')
) AS c(category_code, category_label)
    ON p.category_code = c.category_code
ORDER BY p.product_id;
```

`AS c(category_code, category_label)` names the **derived table source** and its columns. Both `p` and `c` have `category_code`. If you write:

```sql
-- Incorrect because category_code appears in both p and c:
-- SELECT category_code
-- FROM select_lab.products AS p
-- JOIN (VALUES ('books', 'Books')) AS c(category_code, category_label)
--   ON p.category_code = c.category_code;
```

PostgreSQL may report `column reference "category_code" is ambiguous`. The fix is to write `p.category_code` or `c.category_code` as intended.

**Rule of thumb:** use `table_alias.column_name` for clarity whenever multiple sources may contain columns with the same name.

## 8. Identifiers, Case Sensitivity, and Double Quotes

PostgreSQL distinguishes between:

1. **Unquoted identifiers**, such as `product_name` or `Product_Name`.
2. **Quoted identifiers**, such as `"Product_Name"` or `"Product Name"`.
3. **String literals**, such as `'paid'` or `'Books'`.

PostgreSQL folds unquoted identifiers to lowercase during parsing:

```sql
SELECT product_name
FROM select_lab.products;

SELECT PRODUCT_NAME
FROM select_lab.products;
```

Both queries resolve to the `product_name` column in the lab table.

On the other hand:

```sql
-- Usually reports that column "Product_Name" does not exist in the lab table:
-- SELECT "Product_Name"
-- FROM select_lab.products;
```

Double quotes instruct PostgreSQL to look up the identifier with the exact casing and characters inside the quotes.

### 8.1. Defining CamelCase Aliases

```sql
SELECT product_name AS "productName"
FROM select_lab.products;
```

The output name is exactly `productName`. Whereas:

```sql
SELECT product_name AS productName
FROM select_lab.products;
```

normally produces the output name `productname` because unquoted identifiers are folded to lowercase.

When designing Java mappings, ORMs, or serialization that require exact column names, quoting aliases can be useful. However, if the entire system uses unquoted `snake_case`, schema management is usually simpler.

### 8.2. Keywords and Hard-to-Read Names

Table/column names that collide with SQL keywords or contain spaces must be handled with appropriate quoting. Still, you should avoid naming columns `"select"` or `"Order ID"` without a very specific reason. Meaningful, consistent, easy-to-type names help reduce query errors.

### 8.3. String Literals Do Not Replace Identifiers

```sql
SELECT
    'product_name' AS literal_text,
    product_name AS column_value
FROM select_lab.products
WHERE product_id = 101;
```

Result:

| literal_text | column_value |
| --- | --- |
| product_name | Practical SQL Book |

`'product_name'` is a fixed string returned for every row; `product_name` is the column name read from the table.

## 9. Arithmetic Expressions in the SELECT List

An **expression** can combine columns, constants, operators, and functions to compute a new value for each row.

For example, the inventory value at listed price:

```sql
SELECT
    product_id,
    product_name,
    unit_price,
    stock_quantity,
    unit_price * stock_quantity AS inventory_value
FROM select_lab.products
ORDER BY product_id;
```

For product 101, `180000.00 * 12 = 2160000.00`. For product 103, the stock quantity is 0, so the computed inventory value is 0.

### 9.1. Common Operators

| Operator | Meaning | Example |
| --- | --- | --- |
| `+` | Addition | `unit_price + 1000` |
| `-` | Subtraction or negation | `unit_price - 5000` |
| `*` | Multiplication | `unit_price * stock_quantity` |
| `/` | Division | `unit_price / 2` |
| `%` | Modulo (remainder) for compatible operand types | `stock_quantity % 2` |
| `( )` | Controls evaluation precedence | `(unit_price + 1000) * 2` |

Multiplication and division take higher precedence than addition and subtraction. Use parentheses when a business expression involves multiple steps:

```sql
SELECT
    10 + 2 * 3 AS without_parentheses,
    (10 + 2) * 3 AS with_parentheses;
```

Results: `16` and `36`.

### 9.2. Calculating Discounted Prices

Illustrative business assumption for this example: if `discount_pct` is SQL `NULL`, temporarily treat it as a 0% discount.

```sql
SELECT
    product_id,
    product_name,
    unit_price,
    discount_pct,
    ROUND(
        unit_price * (1 - COALESCE(discount_pct, 0) / 100),
        2
    ) AS discounted_price
FROM select_lab.products
ORDER BY product_id;
```

Sample output for several rows:

| product_id | unit_price | discount_pct | discounted_price |
| ---: | ---: | ---: | ---: |
| 101 | 180000.00 | 10.00 | 162000.00 |
| 102 | 240000.00 | NULL | 240000.00 |
| 104 | 45000.00 | 5.00 | 42750.00 |
| 105 | 95000.00 | 15.00 | 80750.00 |

`COALESCE(discount_pct, 0)` only determines the value **used in the calculation**; it does not modify the `discount_pct` column in the table.

If the business defines NULL as "not enough information to calculate a price", **do not silently replace it with 0**. In that case, you can return `NULL` or a status indicating missing data.

### 9.3. Integer Division vs. Decimal Division

PostgreSQL chooses the result type based on the operand types:

```sql
SELECT
    1 / 2 AS integer_division,
    1.0 / 2 AS numeric_division,
    1::numeric / 2 AS explicit_numeric_division;
```

Expected results:

| integer_division | numeric_division | explicit_numeric_division |
| ---: | ---: | ---: |
| 0 | 0.5 | 0.5 |

When both operands are integers, `/` performs integer division and truncates the fractional part. Do not compute a ratio using `successful_count / total_count` if both are integers and you expect 0.75; cast at least one operand to an appropriate decimal type.

```sql
SELECT
    3::numeric / 4 AS success_ratio;
```

### 9.4. Division by Zero

```sql
-- Do not run if you want to avoid a division-by-zero error:
-- SELECT 100 / 0;
```

If the denominator can be 0, you can use `NULLIF`:

```sql
SELECT
    100::numeric / NULLIF(0, 0) AS safe_result;
```

`NULLIF(0, 0)` returns SQL NULL, so the division yields NULL instead of a division-by-zero error in this case. You then need to decide whether NULL should be displayed as "undefined", 0, or another business message.

## 10. Expressions and Data Types: PostgreSQL Does Not Ignore Types

Table columns have their own types, for example:

- `product_id`: `bigint`.
- `sku`: `text`.
- `unit_price`: `numeric(12,2)`.
- `stock_quantity`: `integer`.
- `is_active`: `boolean`.
- `created_at`: `date`.

When columns are combined, PostgreSQL determines the output type based on the operators, functions, and casts used.

### 10.1. Checking an Expression's Type

```sql
SELECT
    pg_typeof(unit_price) AS price_type,
    pg_typeof(stock_quantity) AS stock_type,
    pg_typeof(unit_price * stock_quantity) AS value_type
FROM select_lab.products
WHERE product_id = 101;
```

`pg_typeof` returns the PostgreSQL type of an expression. In this example, `unit_price * stock_quantity` has the appropriate numeric type for arithmetic with `numeric`.

### 10.2. CAST and the :: Operator

PostgreSQL supports standard `CAST(... AS ...)` syntax:

```sql
SELECT
    CAST(12 AS numeric) / 5 AS ratio,
    CAST('2026-10-01' AS date) AS sample_date;
```

And the common PostgreSQL shorthand using `::`:

```sql
SELECT
    12::numeric / 5 AS ratio,
    '2026-10-01'::date AS sample_date;
```

Both are equivalent in many cases; `CAST` is standard SQL syntax, while `::` is concise and idiomatic in PostgreSQL.

### 10.3. Do Not Cast Arbitrarily Just to "Silence Errors"

For example:

```sql
SELECT ('250000'::text)::numeric AS amount;
```

This syntax is valid because the string looks like a number. However:

```sql
-- Non-numeric string, so casting will fail:
-- SELECT 'two_hundred'::numeric;
```

If input data is inconsistent, validate and clean it at the point of entry. Repeatedly applying `::numeric` to a text column storing monetary values both wastes conversion overhead and risks failing on malformed values.

### 10.4. Column Aliases Do Not Dictate Data Types

```sql
SELECT unit_price AS price
FROM select_lab.products;
```

The alias `price` only changes the **output name**; it does not turn `numeric` into `text` or `double precision`. If you need a different type, use an explicit cast expression:

```sql
SELECT
    unit_price::text AS price_text,
    unit_price AS price_numeric
FROM select_lab.products;
```

In Java, the returned data type affects how JDBC reads the value—for instance, `numeric` is typically handled properly with `BigDecimal` for monetary calculations, rather than converting monetary amounts to strings just for display.

## 11. Strings: Concatenation, Formatting, and Transformation

Output expressions can also combine text data.

### 11.1. The String Concatenation Operator ||

```sql
SELECT
    sku || ' - ' || product_name AS display_label
FROM select_lab.products
ORDER BY product_id;
```

One result row:

```text
BOOK-SQL - Practical SQL Book
```

`||` is the standard string concatenation operator in PostgreSQL. If any operand being concatenated is SQL NULL, the result of this concatenation typically becomes SQL NULL.

### 11.2. concat and concat_ws

```sql
SELECT
    concat(sku, ' - ', product_name) AS by_concat,
    concat_ws(' - ', sku, product_name, category_code)
        AS with_separator
FROM select_lab.products
WHERE product_id = 101;
```

`concat` converts arguments to text and ignores SQL NULL in the appropriate cases. `concat_ws` uses the first argument as a separator and skips NULL arguments. This can be more convenient than chaining `||` when data has optional parts.

However, **skipping NULL** is only appropriate if the business wants to omit part of a label when information is missing. Do not use it to mask missing required data.

### 11.3. Some Common Text Functions

```sql
SELECT
    product_name,
    upper(product_name) AS uppercase_name,
    lower(sku) AS lowercase_sku,
    length(product_name) AS name_length,
    trim('   PostgreSQL   ') AS trimmed_example
FROM select_lab.products
WHERE product_id = 101;
```

Notes:

- `upper` and `lower` handle characters according to the environment's locale/collation rules.
- `length(text)` measures the number of characters per PostgreSQL semantics, not necessarily the UTF-8 byte count.
- `trim` removes characters from the start/end based on how it is called; it does not modify the value stored in the table.

### 11.4. Single Quotes Inside String Literals

To include a `'` character inside a SQL string, write two consecutive single quotes:

```sql
SELECT 'It''s a PostgreSQL example' AS sample_text;
```

Do not confuse single quotes for string literals with double quotes around identifiers. Especially in Java, never concatenate user input directly into SQL; use parameter binding in `PreparedStatement` or the corresponding safe framework API.

## 12. SQL NULL and Expression Results

`NULL` is not zero, an empty string, or "false". It represents **no known SQL value** in the context of that expression.

### 12.1. Operations with NULL

```sql
SELECT
    100 + NULL::integer AS sum_with_null,
    'abc' || NULL::text AS text_with_null;
```

Both expressions return SQL NULL. You cannot add 100 to an unknown value and claim the result is 100, nor can you assume a missing string part must be an empty string.

For example:

```sql
SELECT
    product_id,
    unit_price,
    discount_pct,
    unit_price * (1 - discount_pct / 100)
        AS raw_discounted_price
FROM select_lab.products
ORDER BY product_id;
```

In rows where `discount_pct IS NULL`, `raw_discounted_price` is NULL. This is the correct SQL behavior, even if the UI wants to display something else.

### 12.2. COALESCE: Fallback Values

`COALESCE` returns the first argument that is **not SQL NULL** in its argument list:

```sql
SELECT
    product_id,
    discount_pct,
    COALESCE(discount_pct, 0) AS discount_for_calculation
FROM select_lab.products
ORDER BY product_id;
```

Important requirement: the arguments must have compatible data types under PostgreSQL's type resolution rules. Do not arbitrarily mix `numeric` with a descriptive text string and expect implicit conversion:

```sql
SELECT
    COALESCE(discount_pct::text, 'Not specified')
        AS discount_display
FROM select_lab.products
ORDER BY product_id;
```

Here, casting to `text` is intentional because the result is for **display**, not further arithmetic calculation.

### 12.3. NULLIF

`NULLIF(a, b)` returns SQL NULL if the two expressions are equal under the applicable comparison condition; otherwise, it returns the first argument's value.

```sql
SELECT
    NULLIF(0, 0) AS result_when_equal,
    NULLIF(7, 0) AS result_when_different;
```

A common use case is guarding division against a zero denominator:

```sql
SELECT
    25::numeric / NULLIF(5, 0) AS normal_division,
    25::numeric / NULLIF(0, 0) AS undefined_division;
```

### 12.4. IS NULL and IS NOT NULL

To find products without a recorded discount:

```sql
SELECT product_id, product_name
FROM select_lab.products
WHERE discount_pct IS NULL
ORDER BY product_id;
```

Do not use:

```sql
-- Incorrect for the intended semantics:
-- WHERE discount_pct = NULL
```

In SQL, `= NULL` evaluates to the unknown logical state (*UNKNOWN*), not `TRUE`. `WHERE` only keeps rows when the condition is `TRUE`.

### 12.5. IS DISTINCT FROM

PostgreSQL supports NULL-safe comparisons:

```sql
SELECT
    NULL::integer IS DISTINCT FROM 0 AS null_differs_from_zero,
    NULL::integer IS DISTINCT FROM NULL::integer AS two_nulls_distinct,
    5 IS NOT DISTINCT FROM 5 AS equal_values;
```

`IS DISTINCT FROM` treats NULL as a distinguishable value in comparison semantics, making it useful when comparing two columns without wanting an UNKNOWN result.

## 13. CASE: Creating Classification Columns from Conditions

`CASE` lets you choose an output value based on conditions.

### 13.1. CASE WHEN ... THEN ... ELSE

```sql
SELECT
    product_id,
    product_name,
    stock_quantity,
    CASE
        WHEN stock_quantity = 0 THEN 'Out of stock'
        WHEN stock_quantity < 5 THEN 'Low stock'
        ELSE 'In stock'
    END AS stock_status
FROM select_lab.products
ORDER BY product_id;
```

Sample output:

| product_id | stock_quantity | stock_status |
| ---: | ---: | --- |
| 101 | 12 | In stock |
| 102 | 5 | In stock |
| 103 | 0 | Out of stock |
| 104 | 20 | In stock |
| 105 | 3 | Low stock |
| 106 | 8 | In stock |

Branches are evaluated in order. If `stock_quantity = 0` matches the first branch, the result for that row is `'Out of stock'`, not `'Low stock'`. This is why more specific conditions should be placed before broader ones.

### 13.2. Simple CASE

```sql
SELECT
    category_code,
    CASE category_code
        WHEN 'books' THEN 'Books'
        WHEN 'stationery' THEN 'Stationery'
        WHEN 'accessories' THEN 'Accessories'
        ELSE 'Other'
    END AS category_name
FROM select_lab.products
ORDER BY product_id;
```

`CASE expression WHEN value` is suitable for mapping a single value to results via equality comparisons. `CASE WHEN condition` is more flexible for range comparisons, multiple columns, or boolean conditions.

### 13.3. CASE Does Not Replace Lookup Tables in All Cases

If categories change frequently, hard-coding dozens of codes inside `CASE` in every report becomes difficult to maintain. A `categories` table with `category_code` and a display name may be better. `CASE` is well-suited for small, stable mappings or specific output expressions.

### 13.4. Types of CASE Branches

The `THEN` and `ELSE` expressions must have result types that PostgreSQL can resolve together. For example:

```sql
SELECT
    CASE WHEN true THEN 100 ELSE 0 END AS numeric_result;
```

Do not have one branch return a `numeric` number and another return an arbitrary string `'unknown'` if you want the result to remain numeric. You can return `NULL` when a value is missing or cast everything to `text` at the display layer.

## 14. Boolean Expressions Are Output Columns Too

A conditional expression does not have to appear only in `WHERE`; it can be selected to display status flags:

```sql
SELECT
    product_id,
    product_name,
    stock_quantity > 0 AS in_stock,
    is_active AND stock_quantity > 0 AS available_for_sale
FROM select_lab.products
ORDER BY product_id;
```

The result contains boolean columns, which is convenient when the application needs to know whether a product can be sold.

### 14.1. Comparison Operators

Common operators:

| Expression | Meaning |
| --- | --- |
| `unit_price > 100000` | Price is greater than 100000. |
| `stock_quantity >= 5` | Stock is at least 5. |
| `is_active = true` | Product is active. |
| `category_code <> 'books'` | Category is not books. |
| `unit_price BETWEEN 50000 AND 200000` | Price is within the range, inclusive of both endpoints. |
| `category_code IN ('books', 'stationery')` | Category is in the list. |
| `product_name ILIKE '%sql%'` | Name contains "sql", case-insensitive per ILIKE semantics. |

`!=` is also supported by PostgreSQL for "not equal", though `<>` is the standard SQL form commonly seen.

### 14.2. AND, OR, and Parentheses

```sql
SELECT
    product_name,
    is_active,
    stock_quantity,
    is_active AND stock_quantity > 0 AS available
FROM select_lab.products;
```

When logic gets complex, use parentheses to express intent:

```sql
SELECT
    product_id,
    (
        is_active
        AND (
            category_code = 'books'
            OR stock_quantity >= 10
        )
    ) AS highlighted
FROM select_lab.products;
```

SQL uses three-valued logic: `TRUE`, `FALSE`, and `UNKNOWN`. Combinations involving NULL can return UNKNOWN; do not assume a boolean expression only ever produces two values if the underlying columns or expressions allow NULL.

## 15. Date and Time Expressions

PostgreSQL supports multiple temporal types such as `date`, `timestamp`, and `timestamptz`. In the lab table, `created_at` is `date`, so it has no hour/minute component.

### 15.1. Adding Days to a Date

```sql
SELECT
    product_id,
    created_at,
    created_at + 30 AS review_date
FROM select_lab.products
ORDER BY product_id;
```

With `date + integer`, the result is the date after that many days. This is different from adding an arbitrary string to a date.

### 15.2. Extracting Year and Month

```sql
SELECT
    product_id,
    created_at,
    EXTRACT(YEAR FROM created_at)::integer AS created_year,
    EXTRACT(MONTH FROM created_at)::integer AS created_month
FROM select_lab.products;
```

`EXTRACT` returns a numeric value representing a time component. If you want to group by month, it is usually better to keep a full year–month representation rather than just the month number 1–12 (otherwise October across different years would be merged together).

```sql
SELECT
    product_id,
    date_trunc('month', created_at::timestamp) AS month_start
FROM select_lab.products;
```

### 15.3. Formatting Dates as Text

```sql
SELECT
    product_id,
    to_char(created_at::timestamp, 'DD/MM/YYYY')
        AS created_date_label
FROM select_lab.products
ORDER BY product_id;
```

Here `to_char` is for **display formatting**; the `created_date_label` column is text, not `date`. If you need to filter by date range or compare chronologically, it is better to keep the original `date`/`timestamptz` column and format only at the presentation layer.

### 15.4. Avoiding Time Zone Confusion

With `timestamptz`, display depends on the session's `TimeZone` setting. If a report requires "date in Vietnam time", you must specify the business time zone before truncating a timestamp to a date. The lab table uses `date`, so it carries no time zone information.

## 16. Common Functions in SELECT

A select list can combine multiple kinds of functions:

```sql
SELECT
    product_id,
    length(product_name) AS name_chars,
    upper(sku) AS sku_upper,
    ROUND(unit_price * 1.05, 2) AS example_adjusted_price,
    COALESCE(discount_pct, 0) AS discount_for_math,
    CURRENT_DATE - created_at AS age_days
FROM select_lab.products
ORDER BY product_id;
```

In this example:

- `length` returns the number of characters in the name.
- `upper` produces an uppercase version.
- `ROUND` rounds a numeric expression.
- `COALESCE` picks a fallback value for NULL.
- `CURRENT_DATE - created_at` returns the number of days via `date - date` subtraction.

These are strictly **result column values**. PostgreSQL does not replace `unit_price` in the table with the price multiplied by 1.05, does not update `sku` to uppercase, and does not assign `discount_pct = 0` in stored data.

### 16.1. Functions Can Return Session-Scoped Values

```sql
SELECT
    current_database() AS database_name,
    current_schema() AS schema_name,
    current_user AS username;
```

These functions reflect the connection context and can be helpful when debugging environments. Do not hard-code them as immutable system-wide constants.

### 16.2. Functions Are Not Necessarily "Read-Only"

Not every expression used in `SELECT` is side-effect-free. PostgreSQL has functions that mutate state, such as sequence advancement functions, or user-defined functions with side effects. A statement starting with `SELECT` can also acquire row locks in appropriate SQL constructs.

Therefore, do not judge a query's safety solely because it begins with the `SELECT` keyword. Check the functions being called, the role's privileges, and actual side effects before running it on important environments.

## 17. WHERE Filters by Expressions, Not Directly by Output Aliases

`WHERE` selects rows that satisfy a condition before producing the final output according to query semantics.

```sql
SELECT
    product_id,
    product_name,
    unit_price
FROM select_lab.products
WHERE unit_price >= 100000
ORDER BY product_id;
```

PostgreSQL keeps rows where `unit_price >= 100000` and does not need to generate result rows for products that fail that condition.

### 17.1. Filtering with a Direct Calculation

```sql
SELECT
    product_id,
    product_name,
    unit_price * stock_quantity AS inventory_value
FROM select_lab.products
WHERE unit_price * stock_quantity > 1000000
ORDER BY inventory_value DESC;
```

The expression `unit_price * stock_quantity` appears in both the select list and `WHERE`. This is valid syntax.

### 17.2. Why Does WHERE inventory_value Not Work?

Incorrect example:

```sql
-- Incorrect: WHERE cannot directly reference an alias from the same-level select list.
-- SELECT
--     product_id,
--     unit_price * stock_quantity AS inventory_value
-- FROM select_lab.products
-- WHERE inventory_value > 1000000;
```

`inventory_value` is an output name created by `SELECT`. A `WHERE` clause at the same query level **cannot see that alias** as a source column.

The reason is explained by the standard logical processing order:

```text
FROM / JOIN
     |
     v
WHERE
     |
     v
GROUP BY / HAVING (if present)
     |
     v
SELECT: creates output columns and aliases
     |
     v
DISTINCT (if present)
     |
     v
ORDER BY
     |
     v
LIMIT / OFFSET
```

This is a **semantic reasoning model**, not a fixed physical execution schedule that PostgreSQL must follow step-by-step in the engine. The optimizer may transform or push down predicates as long as the SQL result remains equivalent.

### 17.3. Fix: Repeat the Expression Explicitly

```sql
SELECT
    product_id,
    unit_price * stock_quantity AS inventory_value
FROM select_lab.products
WHERE unit_price * stock_quantity > 1000000;
```

This is simple when the expression is short.

### 17.4. Fix: Subquery

When an expression is long, you can compute it in a subquery and filter in the outer query:

```sql
SELECT
    x.product_id,
    x.product_name,
    x.inventory_value
FROM (
    SELECT
        product_id,
        product_name,
        unit_price * stock_quantity AS inventory_value
    FROM select_lab.products
) AS x
WHERE x.inventory_value > 1000000
ORDER BY x.inventory_value DESC;
```

At the outer level, `x.inventory_value` is an **output column of the derived table source `x`**, so `WHERE` can reference it.

### 17.5. Fix: CTE

```sql
WITH product_values AS (
    SELECT
        product_id,
        product_name,
        unit_price * stock_quantity AS inventory_value
    FROM select_lab.products
)
SELECT
    product_id,
    product_name,
    inventory_value
FROM product_values
WHERE inventory_value > 1000000
ORDER BY inventory_value DESC;
```

A CTE (*Common Table Expression*) gives a name to an intermediate result. PostgreSQL may inline or materialize a CTE depending on version, structure, and hints; **do not use a CTE simply because you assume it is always faster than repeating an expression**. Its primary benefit is organizing SQL clearly.

## 18. ORDER BY Can Use SELECT Aliases

Unlike `WHERE`, `ORDER BY` can usually reference **output names** directly:

```sql
SELECT
    product_id,
    product_name,
    unit_price * stock_quantity AS inventory_value
FROM select_lab.products
ORDER BY inventory_value DESC, product_id ASC;
```

`inventory_value` is an alias defined in the select list; PostgreSQL allows using it as a sort key in `ORDER BY`.

### 18.1. ORDER BY an Unselected Source Column

In many cases, you can also sort by a source column that is not included in the output list:

```sql
SELECT
    product_id,
    product_name
FROM select_lab.products
ORDER BY created_at DESC, product_id;
```

You do not have to add `created_at` to the result if the application only needs ID/name. However, certain forms of `DISTINCT`, set operations, or complex expressions impose additional restrictions on `ORDER BY`, so verify the specific query's semantics.

### 18.2. ORDER BY Position

PostgreSQL allows:

```sql
SELECT
    product_name,
    unit_price
FROM select_lab.products
ORDER BY 2 DESC;
```

Here `2` refers to the **second output column**, i.e., `unit_price`. This is concise but fragile if someone changes the order of the select list. In long-lived code, it is usually better to write:

```sql
ORDER BY unit_price DESC
```

or use an explicit alias.

### 18.3. Alias Name Matching a Source Column

When a name could refer to either a **source column** or an **output alias**, PostgreSQL applies specific resolution rules per clause. In ambiguous situations, `ORDER BY` generally prefers simple output column names, whereas `GROUP BY` may prefer input columns. This is a strong reason to avoid giving an alias the same name as a column with a different meaning.

Example using an unambiguous distinct alias:

```sql
SELECT
    product_name,
    unit_price * stock_quantity AS stock_value
FROM select_lab.products
ORDER BY stock_value DESC;
```

If you need to sort by a full expression, writing the expression directly removes any doubt about which name is resolved.

## 19. DISTINCT and Output Expression Names

By default, `SELECT` does not remove rows with duplicate output values. To get a deduplicated list of product categories:

```sql
SELECT DISTINCT category_code
FROM select_lab.products
ORDER BY category_code;
```

Result:

```text
accessories
books
stationery
```

In this syntax:

```sql
SELECT DISTINCT
    category_code,
    is_active
FROM select_lab.products;
```

`DISTINCT` considers **the entire tuple of selected expressions**, not just the first column. If the same category has both active and inactive products, those two tuples remain two distinct rows.

### 19.1. SELECT ALL Is the Default

```sql
SELECT ALL category_code
FROM select_lab.products;
```

`ALL` specifies keeping duplicate output rows; omitting `ALL` yields the same default behavior. Thus, we usually write the shorter form:

```sql
SELECT category_code
FROM select_lab.products;
```

### 19.2. PostgreSQL's DISTINCT ON

PostgreSQL provides the `DISTINCT ON` extension to pick one representative row per key group:

```sql
SELECT DISTINCT ON (category_code)
    category_code,
    product_id,
    product_name,
    unit_price
FROM select_lab.products
ORDER BY category_code, unit_price DESC, product_id;
```

Intent: for each `category_code`, select the product with the highest `unit_price` according to the specified order. `DISTINCT ON` keeps the first row in each group based on `ORDER BY`. The `DISTINCT ON` expressions must match the leftmost expressions of `ORDER BY` as required by PostgreSQL.

**Important:** without an appropriate `ORDER BY`, which row represents each group is nondeterministic. `DISTINCT ON` is a PostgreSQL-specific feature; do not assume every SQL DBMS supports the same syntax.

## 20. Aggregate Expressions in SELECT

A select list does not only contain row-by-row expressions; it can also contain **aggregate functions** such as `COUNT`, `SUM`, `AVG`, `MIN`, and `MAX`.

```sql
SELECT
    COUNT(*) AS product_count,
    SUM(stock_quantity) AS total_stock,
    AVG(unit_price) AS average_price,
    MAX(unit_price) AS highest_price
FROM select_lab.products;
```

This query returns **a single aggregated row** for the input set, instead of one row per product.

### 20.1. COUNT(*) vs. COUNT(column)

```sql
SELECT
    COUNT(*) AS all_products,
    COUNT(discount_pct) AS products_with_discount_recorded
FROM select_lab.products;
```

`COUNT(*)` counts every row. `COUNT(discount_pct)` counts only rows where `discount_pct` is not SQL NULL. In the sample data there are 6 products, but only 4 rows have a recorded discount value (including `0`).

Do not interpret `COUNT(discount_pct)` as the number of products "currently discounted": a value of `0` is still counted. If you want to count products with a discount percentage **greater than 0**, use an appropriate condition.

### 20.2. GROUP BY and the Select List

To aggregate by category:

```sql
SELECT
    category_code,
    COUNT(*) AS product_count,
    SUM(stock_quantity) AS stock_total
FROM select_lab.products
GROUP BY category_code
ORDER BY category_code;
```

A common mistake:

```sql
-- Incorrect: product_name is neither grouped nor aggregated.
-- SELECT category_code, product_name, COUNT(*)
-- FROM select_lab.products
-- GROUP BY category_code;
```

When a query has `GROUP BY`, unaggregated columns in the select list generally must belong to the grouping keys or satisfy functional dependency conditions that PostgreSQL can determine under its rules. You cannot arbitrarily include `product_name` if each group contains multiple products with different names.

### 20.3. Can GROUP BY Use an Alias?

PostgreSQL allows referencing a simple output alias in `GROUP BY` in unambiguous situations:

```sql
SELECT
    category_code AS category_label,
    COUNT(*) AS product_count
FROM select_lab.products
GROUP BY category_label
ORDER BY category_label;
```

Here `category_label` is not a source column on the table, so PostgreSQL can resolve it as the alias for `category_code`. However, when an alias shares a name with an input column, `GROUP BY` has different resolution rules than `ORDER BY` and can produce unintended results.

For clarity and portability across databases:

```sql
SELECT
    category_code AS category_label,
    COUNT(*) AS product_count
FROM select_lab.products
GROUP BY category_code
ORDER BY category_label;
```

is usually easier to read. Do not assume `SELECT` aliases can be freely referenced inside arbitrary `GROUP BY`, `WHERE`, or `HAVING` expressions.

### 20.4. HAVING

For example, retrieving only categories with 2 or more products:

```sql
SELECT
    category_code,
    COUNT(*) AS product_count
FROM select_lab.products
GROUP BY category_code
HAVING COUNT(*) >= 2
ORDER BY product_count DESC, category_code;
```

`HAVING` filters **groups**. Do not use the `product_count` alias directly in `HAVING` at the same query level as if it were a source column; repeat the aggregate expression or use a CTE/subquery if you want to reuse it at an outer level.

## 21. SELECT Expressions in Queries with JOIN

When combining multiple sources, the select list still produces a single set of output columns:

```sql
SELECT
    p.product_id AS id,
    p.product_name AS name,
    c.category_label AS category,
    ROUND(
        p.unit_price * (1 - COALESCE(p.discount_pct, 0) / 100),
        2
    ) AS final_price
FROM select_lab.products AS p
JOIN (
    VALUES
        ('books', 'Books'),
        ('stationery', 'Stationery'),
        ('accessories', 'Accessories')
) AS c(category_code, category_label)
    ON c.category_code = p.category_code
WHERE p.is_active
ORDER BY p.product_id;
```

Each item in the select list can come from one source or combine multiple sources in a single expression. The table aliases `p` and `c` clarify which column belongs to which source.

Key points:

- Columns used in `ON` or `WHERE` do not need to appear in `SELECT`; those clauses reference source columns in the appropriate scope.
- The `final_price` expression is only an output price; it does not modify `unit_price`.
- If a JOIN matches one product to multiple rows on the right-hand source, that product can appear multiple times. `SELECT DISTINCT` sometimes hides the symptom, but you should inspect the keys and JOIN condition to address the root cause.

### 21.1. Selecting p.* Plus Computed Columns

```sql
SELECT
    p.*,
    p.unit_price * p.stock_quantity AS inventory_value
FROM select_lab.products AS p;
```

The result includes all columns of `p` plus an additional computed `inventory_value` column at the end. This syntax is valid, though if the output maps to a fixed DTO, an explicit column list is preferable.

## 22. SELECT with Expressions Over Nested Data

PostgreSQL also supports types such as `jsonb` and arrays. A select list can extract values from these types.

Illustrative example only (no changes to the lab table needed):

```sql
SELECT
    '{"status":"paid","customer":{"name":"Lan"}}'::jsonb
        ->> 'status' AS status_text,
    '{"status":"paid","customer":{"name":"Lan"}}'::jsonb
        #>> '{customer,name}' AS customer_name;
```

The `->>` operator returns the text of a key; `#>>` returns text at a nested path. These are still **expressions in the select list**, just like arithmetic operations or function calls.

However, do not collapse an entire relational design into a single JSONB column merely because `SELECT` can extract keys. Fields frequently used for JOINs, foreign key checks, uniqueness, monetary calculations, and independent updates are generally better modeled as standard relational columns/tables.

## 23. Expressions, the Optimizer, and Execution Cost

PostgreSQL determines execution plans using its optimizer. When reading a long `SELECT`, do not assume the engine always evaluates expressions line by line in text order before scanning the table.

### 23.1. Logical Semantics vs. Physical Execution Schedule

For example:

```sql
SELECT
    product_name,
    unit_price * stock_quantity AS inventory_value
FROM select_lab.products
WHERE category_code = 'books'
ORDER BY inventory_value DESC;
```

Logically, the query retrieves products in the books category, computes `inventory_value`, and then sorts the result. Yet PostgreSQL may choose how to scan data, push down filters, evaluate expressions, or sort according to the plan. SQL guarantees results according to query semantics, not a fixed top-down physical execution order.

### 23.2. EXPLAIN

```sql
EXPLAIN
SELECT
    product_id,
    unit_price * stock_quantity AS inventory_value
FROM select_lab.products
WHERE category_code = 'books';
```

`EXPLAIN` displays the estimated plan. When actual timing is needed in a permitted environment:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    product_id,
    unit_price * stock_quantity AS inventory_value
FROM select_lab.products
WHERE category_code = 'books';
```

`EXPLAIN ANALYZE` **actually executes the query**. For ordinary read-only `SELECT` statements this may be acceptable in a lab, but complex `SELECT` statements containing functions with side effects or resource-intensive queries still carry risk. Never run `ANALYZE` uncontrolled against production workloads.

### 23.3. Do Not Optimize Without Measuring

A short expression like `unit_price * stock_quantity` is rarely a major bottleneck compared to scanning millions of rows, joining without suitable indexes, or transferring large JSON documents over the network. Before adding derived columns to "avoid recomputing":

1. Measure query latency.
2. Check whether `WHERE` uses an appropriate index.
3. Inspect rows read vs. rows returned.
4. Evaluate network, serialization, and application-side overhead.
5. Weigh computing in SQL versus in the application based on real workloads.

Denormalizing by storing extra computed columns can increase synchronization costs and data-inconsistency risks; do not do it simply because an expression appears in `SELECT`.

## 24. Sorting and Limiting Results Deterministically

In applications, `SELECT` often combines `ORDER BY` and `LIMIT`:

```sql
SELECT
    product_id,
    product_name,
    unit_price AS price
FROM select_lab.products
WHERE is_active
ORDER BY price DESC, product_id
LIMIT 3;
```

The result contains up to three active products with the highest prices, using `product_id` as a tie-breaker when prices are equal.

### 24.1. Why Is LIMIT Without ORDER BY Error-Prone?

```sql
SELECT product_id, product_name
FROM select_lab.products
LIMIT 3;
```

This query merely asks for **any three rows** returned by PostgreSQL's current execution plan; it does not guarantee the three smallest IDs or the three newest products.

If the application wants the "three newest products":

```sql
SELECT product_id, product_name, created_at
FROM select_lab.products
ORDER BY created_at DESC, product_id DESC
LIMIT 3;
```

The secondary sort on `product_id` ensures deterministic results when multiple products share the same creation date.

### 24.2. ORDER BY NULLS FIRST/LAST

When sorting by a nullable column such as `discount_pct`:

```sql
SELECT product_id, discount_pct
FROM select_lab.products
ORDER BY discount_pct DESC NULLS LAST, product_id;
```

`NULLS LAST` instructs PostgreSQL to place NULL rows at the end for that sort column. This is important when "missing discount" should not be mixed ahead of concrete discount percentages.

## 25. SELECT Does Not Persist Derived Data

For example:

```sql
SELECT
    product_id,
    ROUND(unit_price * 1.1, 2) AS new_price
FROM select_lab.products
WHERE product_id = 101;
```

This is a **preview calculation of a new price in the output**. The table still stores `unit_price = 180000.00` for product 101.

To actually change `unit_price` in stored data, you need a DML operation such as `UPDATE` with the proper condition, transaction, and permissions. This lesson does not perform that operation because it focuses on **read queries, column projection, and computation**.

Similarly:

```sql
SELECT
    product_name AS "Display Name",
    stock_quantity > 0 AS is_in_stock
FROM select_lab.products;
```

does not create two physical columns `"Display Name"` and `is_in_stock` in the table. The names and values belong solely to the query's result set.

### 25.1. Aliases Do Not Replace Migrations

If an application changes its naming convention from `product_name` to `display_name`, an alias can provide compatibility in **a single query**:

```sql
SELECT product_name AS display_name
FROM select_lab.products;
```

However, other SQL statements still have to reference `product_name`, unless you use a view, alter the schema, or introduce a dedicated mapping layer.

## 26. Common Mistakes When Writing SELECT

### Mistake 1: Confusing Quote Types

```sql
-- Correct:
SELECT product_name AS "Product Name"
FROM select_lab.products;

-- Incorrect if you want the column value:
-- SELECT 'product_name' FROM select_lab.products;
-- This expression is valid, but returns a constant string instead of the column value.
```

**Analysis:** single quotes `'` enclose string literals; double quotes `"` enclose identifiers. Using the wrong quote type can trigger a syntax error or silently return wrong data.

### Mistake 2: Using an Alias in WHERE

```sql
-- Incorrect:
-- SELECT unit_price * stock_quantity AS stock_value
-- FROM select_lab.products
-- WHERE stock_value > 1000000;
```

**Fix:** repeat the expression in `WHERE` or use a subquery/CTE to turn the alias into a source column for the outer query level.

### Mistake 3: Confusing Column Aliases with Table Aliases

```sql
-- Incorrect: display_name is not a column of source p.
-- SELECT p.product_name AS display_name, p.display_name
-- FROM select_lab.products AS p;
```

**Fix:** reference `p.product_name` when you need the source column; `display_name` is strictly an output name.

### Mistake 4: Calculating Percentages with Integer Division

```sql
SELECT 1 / 4 AS wrong_ratio,
       1::numeric / 4 AS correct_ratio;
```

The results differ: `0` versus `0.25`. Pay attention to operand types when calculating ratios.

### Mistake 5: Expressions with NULL Producing Unexpected Results

```sql
SELECT
    product_id,
    unit_price * (1 - discount_pct / 100)
        AS price_after_discount
FROM select_lab.products;
```

With a NULL discount, the discounted price is also NULL. **If** business rules allow treating NULL as 0%, use `COALESCE(discount_pct, 0)`.

### Mistake 6: Division by Zero

```sql
-- Can fail if quantity is 0:
-- SELECT unit_price / stock_quantity FROM select_lab.products;

-- Safer under "undefined if 0" semantics:
SELECT
    product_id,
    unit_price / NULLIF(stock_quantity, 0) AS ratio_value
FROM select_lab.products;
```

In this example, `ratio_value` only illustrates the technique to avoid division by zero; **it is not a recommended business metric like "price per stock unit"**.

### Mistake 7: Expecting Fixed Order Without ORDER BY

```sql
-- Does not guarantee returning the 3 products with the smallest IDs:
SELECT product_id FROM select_lab.products LIMIT 3;

-- Correct if you want the 3 smallest IDs:
SELECT product_id
FROM select_lab.products
ORDER BY product_id
LIMIT 3;
```

### Mistake 8: SELECT * in API Contracts

`SELECT *` may return new columns after a migration, changing the response shape or unintentionally exposing unnecessary data. Write an explicit column list for important API queries.

### Mistake 9: Ambiguous Column Names in JOINs

If both tables have `category_code`, writing `SELECT category_code` is likely to raise an ambiguity error. Use `p.category_code` or `c.category_code`.

### Mistake 10: GROUP BY Missing Required Columns or Expressions

```sql
-- Invalid on the sample dataset:
-- SELECT category_code, product_name, COUNT(*)
-- FROM select_lab.products
-- GROUP BY category_code;
```

A group can contain multiple product names; PostgreSQL cannot arbitrarily pick one name without a rule. Add appropriate grouping keys or use deliberate aggregates—do not use `DISTINCT` to mask a semantic error.

### Mistake 11: Treating an Alias as a Stored Column

`SELECT unit_price * 2 AS new_price` does not update the database. Only the returned result carries the name `new_price`.

### Mistake 12: Using COALESCE in Ways That Distort Business Semantics

`COALESCE(discount_pct, 0)` may be right if NULL means no discount applied. But if NULL means unverified data, replacing it with 0 hides the issue. SQL functions do not define business semantics for you.

### Mistake 13: Using Date Formatting Functions for Filtering

Instead of:

```sql
-- Can make date searching/sorting less effective:
-- WHERE to_char(created_at::timestamp, 'YYYY-MM') = '2026-10'
```

consider filtering by date range:

```sql
SELECT product_id, product_name
FROM select_lab.products
WHERE created_at >= DATE '2026-10-01'
  AND created_at < DATE '2026-11-01';
```

Keeping date columns in their native type makes comparisons clear and generally enables better use of suitable indexes.

### Mistake 14: Using SELECT DISTINCT to "Fix" Row Multiplication in JOINs

If a JOIN produces two rows for one product because the right-hand table has two matching records for the join key, `DISTINCT` may remove some duplicate outputs but does not guarantee correct logic. Inspect relationship cardinality and JOIN conditions instead.

## 27. A Complete Query Combining Multiple Techniques

Suppose we need to return active products with their code, name, original price, discounted price, inventory value, and stock status label:

```sql
SELECT
    p.product_id AS id,
    p.sku AS product_code,
    p.product_name AS display_name,
    p.unit_price AS listed_price,
    ROUND(
        p.unit_price
            * (1 - COALESCE(p.discount_pct, 0) / 100),
        2
    ) AS selling_price,
    p.unit_price * p.stock_quantity AS inventory_value,
    CASE
        WHEN p.stock_quantity = 0 THEN 'Out of stock'
        WHEN p.stock_quantity < 5 THEN 'Low stock'
        ELSE 'In stock'
    END AS stock_label,
    p.created_at + 30 AS review_date
FROM select_lab.products AS p
WHERE p.is_active
ORDER BY selling_price DESC, p.product_id
LIMIT 20;
```

Reading from the inside out:

1. `FROM select_lab.products AS p` declares the source `p`.
2. `WHERE p.is_active` selects active products.
3. The select list produces eight output columns, where `selling_price`, `inventory_value`, `stock_label`, and `review_date` are derived expressions.
4. `COALESCE` applies the assumption that a NULL discount is treated as 0% in the calculation.
5. `CASE` produces stock labels according to business thresholds.
6. `ORDER BY selling_price DESC, p.product_id` sorts by the selling price alias and ID tie-breaker.
7. `LIMIT 20` returns at most 20 rows.

If a discontinued product has `is_active = false`, it is filtered out by `WHERE` even if it has valid stock value or selling price.

### 27.1. Filtering a Derived Price Condition with a CTE

If the business only wants to display products whose discounted selling price is at least 100000:

```sql
WITH priced_products AS (
    SELECT
        p.product_id,
        p.product_name,
        p.is_active,
        ROUND(
            p.unit_price
                * (1 - COALESCE(p.discount_pct, 0) / 100),
            2
        ) AS selling_price
    FROM select_lab.products AS p
)
SELECT
    product_id,
    product_name,
    selling_price
FROM priced_products
WHERE is_active
  AND selling_price >= 100000
ORDER BY selling_price DESC, product_id;
```

In the outer query, `selling_price` is a column of the `priced_products` source, so it can be used in `WHERE`. A CTE avoids repeating long expressions at the same query level.

### 27.2. Column Name Contract for Java

With JDBC:

```sql
SELECT
    product_id AS product_id,
    product_name AS product_name,
    unit_price AS unit_price,
    ROUND(
        unit_price * (1 - COALESCE(discount_pct, 0) / 100),
        2
    ) AS selling_price
FROM select_lab.products
WHERE product_id = 101;
```

Aliases such as `product_id` and `selling_price` make result column names explicit when mapping into DTOs. Still, the Java application must use appropriate types: for `numeric` monetary amounts, `BigDecimal` is generally preferred over `double` to avoid floating-point rounding inaccuracies.

## 28. Practice Exercises

Solve the exercises in order inside the `select_lab` schema. The exercises below only use `SELECT`, so they do not alter the created data. You can compare your answers with the solutions in the next section.

### Exercise 1. Select Exactly Three Columns

Write a SQL query that returns `product_id`, `product_name`, and `unit_price` for all products in ascending ID order. Do not use `*`.

### Exercise 2. Define Aliases

Return three output columns named `id`, `name`, and `listed_price` from the corresponding table columns.

### Exercise 3. Calculate Inventory Value

Return `product_id`, `product_name`, and `inventory_value = unit_price * stock_quantity`. Only retrieve products with an inventory value above 500000, sorted descending by inventory value.

### Exercise 4. Integer Division

Predict the output of:

```sql
SELECT
    3 / 4 AS a,
    3.0 / 4 AS b,
    3::numeric / 4 AS c;
```

Explain why `a` differs from `b` and `c`.

### Exercise 5. Calculate Discounted Price

Return `product_id`, `product_name`, and `selling_price` after applying `discount_pct`. In this exercise, assume NULL means 0%. Round to two decimal places.

### Exercise 6. Create Stock Status Labels

Return `product_id`, `stock_quantity`, and `stock_label` according to these rules:

- Stock 0: `Out of stock`.
- Stock 1 to 4: `Low stock`.
- Stock 5 or more: `In stock`.

### Exercise 7. Separate NULL and 0

Write two queries: one finding products with `discount_pct IS NULL`, and one finding products with `discount_pct = 0`. Predict whether the two lists overlap.

### Exercise 8. Use an Alias in ORDER BY

Return `sku`, `product_name`, and `unit_price AS price`; sort descending by `price`, breaking ties ascending by `sku`.

### Exercise 9. Use a CTE to Filter by a Named Expression

Create `WITH priced AS (...)` containing the `selling_price` column, then retrieve products whose discounted selling price is greater than or equal to 100000. Do not use a same-level select-list alias in `WHERE`.

### Exercise 10. Count Groups

Write a query returning `category_code`, product count, and total stock quantity per category, sorted by category name.

### Exercise 11. DISTINCT

Retrieve a deduplicated list of `category_code`. Then try `SELECT DISTINCT category_code, is_active` and explain why the row count can differ.

### Exercise 12. Pick the Highest-Priced Product per Category

Use `DISTINCT ON (category_code)` to retrieve `category_code`, `product_id`, `product_name`, and `unit_price` for the product with the highest listed price in each category.

### Exercise 13. Find the Alias Error

Why is this query invalid?

```sql
-- Do not run verbatim:
-- SELECT unit_price * stock_quantity AS stock_value
-- FROM select_lab.products
-- WHERE stock_value > 100000;
```

Provide two different ways to fix it.

### Exercise 14. Build a Display Label

Return a single `display_label` column formatted as `SKU - Product Name`. Use at least one approach with `||` or `concat_ws`.

### Exercise 15. New Date Column

Return `product_id`, `created_at`, and `review_date` equal to the creation date plus 30 days. Include only products created in October 2026.

### Exercise 16. Result Data Types

Use `pg_typeof` to inspect the result type of `unit_price * stock_quantity`. Then try casting `unit_price::text` and explain the impact on numeric calculations.

## 29. Suggested Solutions

### Solution 1

```sql
SELECT product_id, product_name, unit_price
FROM select_lab.products
ORDER BY product_id;
```

### Solution 2

```sql
SELECT
    product_id AS id,
    product_name AS name,
    unit_price AS listed_price
FROM select_lab.products;
```

### Solution 3

```sql
SELECT
    product_id,
    product_name,
    unit_price * stock_quantity AS inventory_value
FROM select_lab.products
WHERE unit_price * stock_quantity > 500000
ORDER BY inventory_value DESC, product_id;
```

In particular, you cannot replace the expression in `WHERE` with the same-level `inventory_value` alias.

### Solution 4

`a = 0` because of integer division; `b = 0.75` and `c = 0.75` because at least one operand is of a decimal/numeric type.

### Solution 5

```sql
SELECT
    product_id,
    product_name,
    ROUND(
        unit_price * (1 - COALESCE(discount_pct, 0) / 100),
        2
    ) AS selling_price
FROM select_lab.products
ORDER BY product_id;
```

### Solution 6

```sql
SELECT
    product_id,
    stock_quantity,
    CASE
        WHEN stock_quantity = 0 THEN 'Out of stock'
        WHEN stock_quantity < 5 THEN 'Low stock'
        ELSE 'In stock'
    END AS stock_label
FROM select_lab.products
ORDER BY product_id;
```

### Solution 7

```sql
SELECT product_id, product_name
FROM select_lab.products
WHERE discount_pct IS NULL
ORDER BY product_id;

SELECT product_id, product_name
FROM select_lab.products
WHERE discount_pct = 0
ORDER BY product_id;
```

On the sample dataset, NULL belongs to products 102 and 106; 0 belongs to product 103. They have different meanings and do not overlap under these two conditions.

### Solution 8

```sql
SELECT
    sku,
    product_name,
    unit_price AS price
FROM select_lab.products
ORDER BY price DESC, sku ASC;
```

### Solution 9

```sql
WITH priced AS (
    SELECT
        product_id,
        product_name,
        ROUND(
            unit_price * (1 - COALESCE(discount_pct, 0) / 100),
            2
        ) AS selling_price
    FROM select_lab.products
)
SELECT product_id, product_name, selling_price
FROM priced
WHERE selling_price >= 100000
ORDER BY selling_price DESC, product_id;
```

### Solution 10

```sql
SELECT
    category_code,
    COUNT(*) AS product_count,
    SUM(stock_quantity) AS total_stock
FROM select_lab.products
GROUP BY category_code
ORDER BY category_code;
```

### Solution 11

```sql
SELECT DISTINCT category_code
FROM select_lab.products
ORDER BY category_code;

SELECT DISTINCT category_code, is_active
FROM select_lab.products
ORDER BY category_code, is_active;
```

The first query yields three categories; the second also differentiates by active status. The `accessories` category has both active and inactive products, so it produces an additional distinct tuple.

### Solution 12

```sql
SELECT DISTINCT ON (category_code)
    category_code,
    product_id,
    product_name,
    unit_price
FROM select_lab.products
ORDER BY category_code, unit_price DESC, product_id;
```

`ORDER BY` determines which product is kept in each `category_code` group.

### Solution 13

`WHERE` cannot directly reference an output alias from the same-level `SELECT`. Two ways to fix it:

```sql
-- Repeat the expression.
SELECT unit_price * stock_quantity AS stock_value
FROM select_lab.products
WHERE unit_price * stock_quantity > 100000;
```

```sql
-- Create a source column for the outer query level.
SELECT x.stock_value
FROM (
    SELECT unit_price * stock_quantity AS stock_value
    FROM select_lab.products
) AS x
WHERE x.stock_value > 100000;
```

### Solution 14

```sql
SELECT sku || ' - ' || product_name AS display_label
FROM select_lab.products
ORDER BY product_id;
```

Or:

```sql
SELECT concat_ws(' - ', sku, product_name) AS display_label
FROM select_lab.products
ORDER BY product_id;
```

### Solution 15

```sql
SELECT
    product_id,
    created_at,
    created_at + 30 AS review_date
FROM select_lab.products
WHERE created_at >= DATE '2026-10-01'
  AND created_at < DATE '2026-11-01'
ORDER BY created_at, product_id;
```

### Solution 16

```sql
SELECT
    pg_typeof(unit_price * stock_quantity) AS computed_type,
    unit_price::text AS price_text,
    unit_price AS price_numeric
FROM select_lab.products
WHERE product_id = 101;
```

`price_text` is `text`, suitable for display; if you want to continue performing decimal calculations, keep the original `numeric` instead of converting to text and casting back.

## 30. Checklist When Writing SELECT for Applications

Before putting a query into a Java service, migration, or report:

1. **Select the right columns:** return only the fields needed; do not default to `SELECT *` for APIs.
2. **Name aliases clearly:** computed expressions and mapped columns have clear, consistent output names.
3. **Distinguish source columns from aliases:** `table_alias.column` on a source is different from `AS output_alias`.
4. **Understand data types:** avoid unintended integer division and use `numeric` appropriately for money.
5. **Handle NULL according to business rules:** `COALESCE`, `NULLIF`, and `IS NULL` must not be used merely to hide missing data.
6. **Filter at the right level:** `WHERE` cannot directly use a same-level `SELECT` alias; consider a CTE or subquery if needed.
7. **Keep results ordered:** use `ORDER BY` with a tie-breaker key when paginating or using `LIMIT`.
8. **Use functions and expressions intentionally:** every derived column must have a clear definition and does not alter underlying stored data.
9. **Be careful with JOIN and GROUP BY:** avoid ambiguous columns, unintended row multiplication, and ungrouped columns.
10. **Check permissions and sensitive data:** `SELECT` can return more information than expected; functions in `SELECT` are not always read-only.
11. **Measure before optimizing:** use `EXPLAIN` and representative data rather than adding physical columns just because a calculation looks long.
12. **Test edge cases:** NULL, zero stock, strings with quotes, zero price, inactive products, and empty result sets.

## 31. Summary

The essence of `SELECT` is **specifying the desired output**, not copying a table as-is:

- **The select list** determines the output columns and their order; `SELECT *` is handy for exploration but should generally be avoided in long-term data contracts.
- **Column aliases `AS ...`** name a column or expression in the result; table aliases in `FROM` help qualify sources, especially in JOINs.
- **Expressions** can be arithmetic, string concatenation, functions, booleans, date operations, `CASE`, `COALESCE`, `NULLIF`, or casts; PostgreSQL determines result types from expression semantics.
- **NULL is distinct from 0 and empty strings**; how NULL is substituted or displayed must follow business policy.
- **Output aliases work in `ORDER BY`** and some `GROUP BY` cases in PostgreSQL, but not directly in a same-level `WHERE`. When filtering by a complex named expression, use a subquery/CTE or repeat the expression.
- **`SELECT` does not update tables** simply by projecting an expression named `new_price` or `stock_value`.
- **Row order is not guaranteed without `ORDER BY`**, even when `LIMIT` is present.

Mastering select lists, aliases, and expressions helps you write clear SQL, read query plans, and build stable output data for PostgreSQL applications. It also lays the foundation for subsequent topics such as `WHERE`, `JOIN`, aggregation, subqueries, CTEs, and query optimization.
