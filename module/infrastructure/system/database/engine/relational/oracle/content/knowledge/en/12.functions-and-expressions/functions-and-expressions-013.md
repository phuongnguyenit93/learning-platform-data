# LEAST, GREATEST, and the Effects of NULL and Type Conversion in Oracle SQL

In Oracle Database, **`LEAST`** and **`GREATEST`** select the smallest or largest value from a list of expressions. They commonly appear in tasks such as picking the earlier start or end date, choosing the lower price between list price and promotional price, clamping a value within an allowed range, or comparing multiple thresholds within the same row.

```sql
SELECT LEAST(100, 80, 120) AS lowest_value,
       GREATEST(100, 80, 120) AS highest_value
FROM dual;
```

The results are `80` and `120`, respectively. However, results can be surprising when the argument list contains **`NULL`**, expressions of **different data types**, or a first argument that is a string rather than a number or date. In Oracle, the data type of the first argument plays a decisive role in type-conversion rules and the return data type. Therefore, do not treat these two functions like aggregate `MIN`/`MAX`, or assume Oracle will always guess the intended business type.

## 1. LEAST and GREATEST are scalar functions comparing within a single row

`LEAST(expr1, expr2 [, expr3 ...])` returns the smallest value among the supplied expressions.

`GREATEST(expr1, expr2 [, expr3 ...])` returns the largest value among the supplied expressions.

Both are **scalar functions**: each invocation evaluates its arguments once per expression evaluation, typically once per row in a query. They do not aggregate multiple rows into a single summary result.

```sql
SELECT LEAST(12, 5, 9) AS min_in_list,
       GREATEST(12, 5, 9) AS max_in_list
FROM dual;
```

| Expression | Result |
|---|---:|
| `LEAST(12, 5, 9)` | 5 |
| `GREATEST(12, 5, 9)` | 12 |

Row-level example:

```sql
SELECT product_id,
       regular_price,
       sale_price,
       LEAST(regular_price, sale_price) AS effective_price,
       GREATEST(regular_price, sale_price) AS higher_price
FROM products;
```

For each product, Oracle compares `REGULAR_PRICE` and `SALE_PRICE` within **that same row**. One row does not directly affect the result of another row.

### 1.1. Comparing multiple arguments

Both functions accept two or more expressions and can take many arguments:

```sql
SELECT LEAST(25, 18, 31, 12, 20) AS least_value,
       GREATEST(25, 18, 31, 12, 20) AS greatest_value
FROM dual;
```

The results are `12` and `31`. For long argument lists, wrap lines or use named CTE expressions so readers can identify each threshold. Never pass a mixed-type list without controlling argument order and conversions.

### 1.2. Comparison with MIN and MAX

The names can cause confusion:

- **`LEAST(a, b)`**: compares multiple expressions in a single evaluation, typically within one row.
- **`GREATEST(a, b)`**: similarly picks the largest value among expressions in the same row.
- **`MIN(column)`**: aggregate function finding the smallest value of one column across a group of rows.
- **`MAX(column)`**: aggregate function finding the largest value of one column across a group of rows.

Example:

```sql
-- Pick the lower price between two columns for each product.
SELECT product_id, LEAST(regular_price, sale_price) AS lower_price
FROM products;

-- Pick the lowest regular price across all products.
SELECT MIN(regular_price) AS lowest_regular_price
FROM products;
```

`MIN`/`MAX` are aggregate functions and normally **ignore NULL values** in the group; only if every value is NULL is the result NULL. `LEAST`/`GREATEST` in Oracle behave differently: **a single NULL argument turns the entire function result into NULL**. This is a critical difference when translating logic between aggregate and scalar expressions.

## 2. Syntax and argument data types

General syntax:

```sql
LEAST(expr1, expr2 [, expr3 ...])
GREATEST(expr1, expr2 [, expr3 ...])
```

Oracle must compare arguments under a compatible data type and comparison rule. Type resolution has two main cases:

1. **If the first expression is numeric:** Oracle determines the numeric type with the highest precedence in the list, converts remaining arguments to that numeric type, and returns that highest-precedence numeric type.
2. **If the first expression is non-numeric:** Oracle converts subsequent expressions to the data type of the first expression before comparing; the return type matches the first expression's type.

Therefore, **argument order can change both the comparison semantics and the return type**. For lists with mixed data types, put the first argument in the desired business type and use explicit `CAST`, `TO_NUMBER`, `TO_DATE`, or `TO_TIMESTAMP` when needed.

## 3. LEAST and GREATEST with NUMBER

When all arguments share a numeric type, behavior is intuitive:

```sql
SELECT LEAST(10, 20, 5) AS smallest_number,
       GREATEST(10, 20, 5) AS largest_number
FROM dual;
```

The results are `5` and `20`.

### 3.1. Numeric arguments of different types

Oracle defines numeric precedence. Among common numeric types, precedence order is:

```text
BINARY_DOUBLE  >  BINARY_FLOAT  >  NUMBER
```

If the first argument is numeric, Oracle inspects numeric arguments in the list to determine the highest-precedence type, then converts the others to that type.

Illustrative example:

```sql
SELECT LEAST(
           CAST(10 AS NUMBER),
           CAST(2.5 AS BINARY_DOUBLE),
           CAST(7 AS NUMBER)
       ) AS least_numeric
FROM dual;
```

Here, `BINARY_DOUBLE` has higher precedence than `NUMBER`, so the result type under numeric precedence is `BINARY_DOUBLE`. When an application requires decimal exactness for currency, do not casually introduce `BINARY_FLOAT`/`BINARY_DOUBLE` into `NUMBER` expressions; use consistent types and binds.

### 3.2. Avoid mixing NUMBER with unchecked strings

```sql
-- Oracle must convert '20' to a number because the first argument is NUMBER.
SELECT LEAST(10, '20') AS result
FROM dual;
```

Oracle converts `'20'` to `20`, returning `10`. However, if the string is not a valid number:

```sql
-- Can raise a conversion error such as ORA-01722.
SELECT LEAST(10, 'TWENTY')
FROM dual;
```

the conversion fails and the SQL statement errors. Never treat character columns as numbers merely because current rows happen to contain digits. Column, bind parameter, and literal types should be declared consistently.

### 3.3. First argument is CHAR: results can differ

Compare these two expressions:

```sql
SELECT LEAST(10, '2') AS numeric_first,
       LEAST('10', 2) AS character_first
FROM dual;
```

Under Oracle's type rules:

- `LEAST(10, '2')`: the first argument is numeric, so Oracle converts `'2'` to a number; the numeric result is `2`.
- `LEAST('10', 2)`: the first argument is character, so Oracle converts `2` to character data for comparison. In standard character sorting, `'10'` precedes `'2'`, so the result is the string `'10'`.

| Expression | Comparison Type | Illustrative Result |
|---|---|---|
| `LEAST(10, '2')` | Numeric | `2` |
| `LEAST('10', 2)` | Character | `'10'` |
| `GREATEST(10, '2')` | Numeric | `10` |
| `GREATEST('10', 2)` | Character | `'2'` |

This is a key example showing how **reordering arguments can alter the result**. Never write `LEAST(char_column, numeric_column)` when business intent is numeric comparison; convert explicitly or fix the schema.

### 3.4. Explicitly convert strings to NUMBER

If source data is character-typed yet represents numbers, convert before comparing:

```sql
SELECT LEAST(
           TO_NUMBER('125'),
           TO_NUMBER('80'),
           100
       ) AS least_amount
FROM dual;
```

The result is numeric `80`. With real data, specify explicit format models and NLS parameters whenever strings contain decimal markers or group separators:

```sql
-- Example parsing a string with comma decimal and period grouping.
SELECT TO_NUMBER(
           '1.234,50',
           '9G999D99',
           'NLS_NUMERIC_CHARACTERS = '',.'''
       ) AS parsed_amount
FROM dual;
```

`NLS_NUMERIC_CHARACTERS = ',.'` sets comma as decimal and period as group separator. String quotes in the example follow Oracle SQL escaping. When parsing CSV/API inputs, know the source format and never rely on implicit session `NLS_NUMERIC_CHARACTERS`.

## 4. LEAST and GREATEST with character types

When the first argument is a character type, Oracle converts remaining arguments to the corresponding character type before comparing. Consequently, results follow **string collation order**, not any numeric values those strings might represent.

```sql
SELECT LEAST('100', '20', '3') AS least_text,
       GREATEST('100', '20', '3') AS greatest_text
FROM dual;
```

Under standard binary character order, the illustrative results are `'100'` and `'3'`. This differs from numeric comparison, where 3 is smallest and 100 is largest.

### 4.1. String comparison is not numeric comparison

```sql
SELECT LEAST('2', '10') AS result
FROM dual;
```

Under standard character comparison, the result is `'10'`, because the first character `'1'` precedes `'2'`. For a numeric result, write:

```sql
SELECT LEAST(TO_NUMBER('2'), TO_NUMBER('10')) AS result
FROM dual;
```

The result is numeric `2`. Do not patch character columns by zero-padding strings just to make lexicographical order match numeric order if the column truly stores numeric data; the better solution is storing `NUMBER`.

### 4.2. Collation and NLS affect character comparisons

When comparing character data, Oracle applies the active comparison/collation rules for the expression based on version and configuration. Binary, linguistic, case-insensitive, or accent-insensitive sorting can produce different results for uppercase/lowercase, accents, and languages.

For instance, if a system requires case-insensitive or accent-insensitive comparisons, do not assume `LEAST('a','B')` returns the same result across all collations. Identify active collation or NLS settings and test on the target database. **Character set and collation are two separate concepts**: character set defines character encoding; collation defines comparison and sort order.

### 4.3. CHAR and VARCHAR2

`CHAR` uses fixed-length semantics with blank padding; `VARCHAR2` stores variable-length strings. Oracle applies blank-padded or nonpadded comparison semantics depending on expression types. When passing differing character types to `LEAST`/`GREATEST`, pay attention to the first argument's type and resulting conversions.

In systems using string identifiers, standardize data types and normalization rules. Never compare a `CHAR(10)` column against a client `VARCHAR2` without understanding trailing-space effects.

### 4.4. UPPER/LOWER does not make comparison linguistically natural

You can write:

```sql
SELECT LEAST(UPPER(code_a), UPPER(code_b)) AS least_upper_code
FROM lab_codes;
```

yet the result still follows the active collation on the uppercased strings. It does not strip accents, normalize Unicode, or cover all locale rules. When linguistic rules are required, configure NLS/collation explicitly and apply expressions consistently.

## 5. LEAST and GREATEST with DATE/TIMESTAMP

These functions select the earliest or latest datetime when arguments share compatible types.

```sql
SELECT LEAST(
           DATE '2026-11-01',
           DATE '2026-11-15',
           DATE '2026-11-10'
       ) AS earliest_date,
       GREATEST(
           DATE '2026-11-01',
           DATE '2026-11-15',
           DATE '2026-11-10'
       ) AS latest_date
FROM dual;
```

The results are `2026-11-01` and `2026-11-15`. Oracle `DATE` includes date and time down to seconds, even though `DATE 'YYYY-MM-DD'` literals start at 00:00:00.

### 5.1. Using LEAST to find the earlier start date

```sql
SELECT booking_id,
       LEAST(check_in_date, requested_date) AS effective_start
FROM bookings;
```

Each row returns the earlier of check-in date and requested date. If either column is `NULL`, `LEAST` returns `NULL`; never assume Oracle automatically picks the other date.

### 5.2. Using GREATEST to clamp a lower bound

```sql
SELECT booking_id,
       GREATEST(valid_from, DATE '2026-01-01') AS effective_from
FROM subscriptions;
```

This picks the later date between `VALID_FROM` and 01/01/2026. If `VALID_FROM` is `NULL`, the result remains `NULL`; if business logic treats `NULL` as "unbounded" or "not yet set", handle it explicitly.

### 5.3. Avoid date strings dependent on NLS_DATE_FORMAT

Do not rely on implicit conversion from strings:

```sql
-- Not recommended: depends on session NLS_DATE_FORMAT.
SELECT LEAST('01/02/2026', DATE '2026-02-10')
FROM dual;
```

`'01/02/2026'` can be interpreted differently depending on session format or fail to parse. Use date literals or `TO_DATE` with an explicit format:

```sql
SELECT LEAST(
           TO_DATE('01/02/2026', 'DD/MM/YYYY'),
           DATE '2026-02-10'
       ) AS earliest_date
FROM dual;
```

The result is 01/02/2026. This explicitly states that the source string uses `DD/MM/YYYY`.

### 5.4. DATE and TIMESTAMP require explicit CAST

`DATE`, `TIMESTAMP`, `TIMESTAMP WITH TIME ZONE`, and `TIMESTAMP WITH LOCAL TIME ZONE` differ in precision and timezone rules. Do not mix them arbitrarily in `LEAST`/`GREATEST`, because Oracle may convert to the first argument's type or per data-type rules, dropping fractional seconds or altering timezone interpretation.

If business logic requires comparing timestamps, cast arguments explicitly to the same type, for example:

```sql
SELECT LEAST(
           CAST(start_time AS TIMESTAMP),
           CAST(end_time AS TIMESTAMP)
       ) AS earlier_timestamp
FROM lab_schedule;
```

This example assumes a conceptual `LAB_SCHEDULE` table. If data carries timezones, align on a common reference (such as UTC) and use timezone-aware types; `CAST` alone does not replace timezone business decisions.

## 6. NULL: the biggest source of surprises

In Oracle SQL, `NULL` represents an unknown or missing value. With `LEAST` and `GREATEST`, **if any argument is `NULL`, the function returns `NULL`**.

```sql
SELECT LEAST(10, NULL, 20) AS least_value,
       GREATEST(10, NULL, 20) AS greatest_value
FROM dual;
```

Both expressions evaluate to `NULL`.

### 6.1. One NULL column makes the entire result NULL

Suppose `PRODUCT_PRICES` has `REGULAR_PRICE` and `SALE_PRICE`:

| Product | Regular price | Sale price | `LEAST(regular_price, sale_price)` |
|---|---:|---:|---|
| A | 100 | 80 | 80 |
| B | 150 | `NULL` | `NULL` |
| C | `NULL` | 90 | `NULL` |
| D | `NULL` | `NULL` | `NULL` |

If `SALE_PRICE` is missing, `LEAST` does not automatically pick `REGULAR_PRICE`. The function sees one unknown argument, so the outcome is unknown per null-propagation rules.

### 6.2. NULL differs from 0 and from a default value

Never assume `NULL` equals 0:

```sql
SELECT LEAST(100, NULL) AS result
FROM dual;
```

The result is `NULL`, not 0 and not 100. If business logic treats a missing price as 0, state it explicitly with `NVL`/`COALESCE` after verifying semantics. For selling prices, replacing an unknown price with 0 can falsely report products as free.

### 6.3. Truth tables are not how LEAST/GREATEST operate

`LEAST`/`GREATEST` do not return `TRUE/FALSE/UNKNOWN`; they return **a value of the expression's data type** or `NULL`. Three-valued logic comes into play when that result is used inside a comparison predicate:

```sql
SELECT product_id
FROM products
WHERE LEAST(regular_price, sale_price) < 100;
```

If `LEAST(...)` returns `NULL`, `< 100` evaluates to `UNKNOWN`, so the row is excluded by `WHERE`.

## 7. Handling NULL according to business rules

There is no single NULL-replacement trick valid for every problem. Before using `NVL`, `COALESCE`, or `CASE`, answer: **does NULL mean missing data, not applicable, unknown, or unbounded?**

### 7.1. NVL: substituting NULL with a default value

`NVL(expr1, expr2)` returns `expr2` when `expr1` is `NULL`, otherwise `expr1`.

```sql
SELECT LEAST(
           NVL(regular_price, 999999),
           NVL(sale_price, 999999)
       ) AS lowest_available_price
FROM product_prices;
```

This uses a large value `999999` as a **sentinel** so the other price wins if one is missing. However, a sentinel is valid only if real prices never reach that threshold and `NULL` genuinely means "no candidate". If real prices can exceed it, or `NULL` means "undetermined", this approach breaks.

`NVL` also applies type-conversion rules driven by the first argument and numeric precedence; do not pass incompatible types expecting implicit conversion to behave safely.

### 7.2. COALESCE: picking the first non-NULL expression

`COALESCE(expr1, expr2, ...)` returns the first non-`NULL` expression in order. It is readable when listing fallback sources:

```sql
SELECT COALESCE(sale_price, regular_price, list_price) AS chosen_price
FROM product_prices;
```

This is **priority fallback selection**, not picking the lowest price. If `SALE_PRICE` is present, it is returned even if `REGULAR_PRICE` is lower. Never use `COALESCE` in place of `LEAST` when business logic requires comparing values.

### 7.3. Combining COALESCE or CASE with LEAST/GREATEST

To pick the lowest price among **known** prices, filter out nulls first or substitute safely. With two columns, `CASE` is crystal clear:

```sql
SELECT product_id,
       CASE
           WHEN regular_price IS NULL THEN sale_price
           WHEN sale_price IS NULL THEN regular_price
           ELSE LEAST(regular_price, sale_price)
       END AS lowest_known_price
FROM product_prices;
```

Outcomes:

- Both present: picks the lower price.
- Only regular price present: picks regular price.
- Only sale price present: picks sale price.
- Both `NULL`: returns `NULL`.

This expresses the rule **"ignore one unknown price if the other is present"**. If business rules state "cannot determine lowest price whenever any price is missing", keep `LEAST`'s native null propagation.

### 7.4. GREATEST with NULL and unbounded dates

Suppose a contract has `valid_from` and `valid_until`. If `VALID_UNTIL = NULL` means "no expiration date", you cannot blindly write:

```sql
GREATEST(valid_from, valid_until)
```

because the result will be `NULL`. Express business logic clearly—for instance, picking the later effective start between contract start and a cutoff date:

```sql
SELECT contract_id,
       GREATEST(valid_from, DATE '2026-01-01') AS effective_start
FROM contracts;
```

If you need the latest end date while `NULL` means perpetual, define explicit rules (such as returning an `UNBOUNDED` status or omitting an end date). Avoid picking a far-future sentinel date if applications might mistake it for a real expiration date.

### 7.5. CASE to cleanly preserve all cases

When logic grows complex, `CASE` is easier to control:

```sql
SELECT product_id,
       CASE
           WHEN regular_price IS NULL AND sale_price IS NULL THEN NULL
           WHEN regular_price IS NULL THEN sale_price
           WHEN sale_price IS NULL THEN regular_price
           WHEN regular_price <= sale_price THEN regular_price
           ELSE sale_price
       END AS lowest_known_price
FROM product_prices;
```

This preserves the `NUMBER` type when the columns are `NUMBER` while expressing the policy unambiguously. For three or more columns, you can use `UNPIVOT`, `CROSS APPLY`/`LATERAL`, or a normalized schema to filter nulls and take `MIN`, weighing complexity and performance.

## 8. Comparing LEAST/GREATEST with aggregate MIN/MAX

Their `NULL` differences can be summarized:

| Scenario | `LEAST(a, b)` | `MIN(a)` in a group |
|---|---|---|
| `a=10`, `b=5` | 5 | Aggregate depends on rows in column |
| One argument/value is NULL | Scalar function returns NULL if any argument is NULL | `MIN` ignores NULL when non-null values exist |
| All values NULL | NULL | NULL |
| Multiple rows | Evaluates per row in SELECT | Aggregates across multiple rows in group |

Example on a hypothetical table:

```sql
-- Pick the lower price per row, then find the lowest across rows.
SELECT MIN(LEAST(price_a, price_b)) AS lowest_row_price
FROM lab_compare_prices;
```

In this query, if a row has `PRICE_A` or `PRICE_B` as `NULL`, that row's `LEAST` is `NULL`; the outer `MIN` aggregate then skips that NULL result if other rows have non-NULL results. These are two separate evaluation layers. To skip NULLs at the row level, use `CASE` as shown earlier.

## 9. Implicit conversion and common bugs

Oracle allows implicit conversions in some expressions, yet relying on them can trigger runtime errors or change behavior when data, NLS settings, or argument order shift.

### 9.1. Invalid numeric strings

```sql
SELECT LEAST(100, 'ABC')
FROM dual;
```

Because the first argument is numeric, Oracle tries to convert `'ABC'` to a number. Conversion fails, raising `ORA-01722: invalid number`. Such bugs may surface only when a single dirty row appears, escaping small test runs.

### 9.2. Date strings dependent on NLS_DATE_FORMAT

```sql
-- Not recommended: date string without explicit format.
SELECT LEAST(DATE '2026-01-01', '02/01/2026')
FROM dual;
```

Because the first argument is `DATE`, Oracle must convert the second argument to DATE using implicit conversion and session formatting. One session with `DD/MM/YYYY` and another with `MM/DD/YYYY` interpret it differently, or fail outright. Use `TO_DATE` with an explicit format mask:

```sql
SELECT LEAST(
           DATE '2026-01-01',
           TO_DATE('02/01/2026', 'DD/MM/YYYY')
       ) AS earliest_date
FROM dual;
```

### 9.3. Incompatible data types

If arguments belong to incompatible data-type families, Oracle raises an inconsistent data types error such as `ORA-00932`. Check column types in the data dictionary and specify valid conversions before using the function.

```sql
SELECT column_name, data_type, data_length, data_precision, data_scale
FROM user_tab_columns
WHERE table_name = 'PRODUCT_PRICES'
ORDER BY column_id;
```

### 9.4. First-argument conversion rules

| Expression | First Argument Type | Primary Oracle Handling | Risk |
|---|---|---|---|
| `LEAST(10, '20')` | NUMBER | Converts string to NUMBER | Non-numeric string raises error |
| `LEAST('10', 20)` | Character | Converts number to character | Lexicographical comparison, not numeric |
| `LEAST(date_col, '2026-01-01')` | DATE | Converts string to DATE | Depends on NLS if format omitted |
| `LEAST('2026-01-01', date_col)` | Character | Converts DATE to character | String comparison; date format affects outcome |
| `LEAST(number_col, binary_double_expr)` | Numeric | Uses highest numeric precedence | Can alter precision/return type |

For maintainable queries, **arguments should share the same data type and semantic meaning**. When types differ, use `CAST` or explicit conversion functions and confirm the intended return type.

## 10. Effects of NLS and collation

NLS (National Language Support) governs regional and linguistic rules such as number/date formatting, sort order, and string comparison. For `LEAST`/`GREATEST`:

- When comparing numbers, NLS affects **string-to-number** implicit conversions.
- When comparing dates, NLS affects **string-to-DATE** implicit conversions without format masks.
- When comparing characters, active collation/linguistic rules govern case, accents, and language sort order.

Check session settings when troubleshooting inconsistent results:

```sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_DATE_FORMAT',
    'NLS_DATE_LANGUAGE',
    'NLS_NUMERIC_CHARACTERS',
    'NLS_SORT',
    'NLS_COMP'
)
ORDER BY parameter;
```

Session parameters can differ between SQL clients and application connection pools. Never assume a query tested in SQL Developer performs identical implicit conversions under JDBC.

### 10.1. Never rely on default NLS for incoming data

If an API passes dates as strings, parse them in the application layer or use `TO_DATE(:text, 'YYYY-MM-DD')` per explicit contract. If an API passes decimals as strings, use `TO_NUMBER` with explicit format/NLS or parse to `BigDecimal` before binding. **Never let `LEAST`/`GREATEST` guess input data types from raw strings.**

### 10.2. Character set vs. collation

An `AL32UTF8` database does not automatically make string comparisons case-insensitive or accent-insensitive. Character set defines character encoding; collation defines comparison rules. When calling `LEAST`/`GREATEST` on multilingual strings, check the active collation rather than looking only at `NLS_CHARACTERSET`.

## 11. Using LEAST/GREATEST in business expressions

### 11.1. Clamping a value to a range

A common pattern is bounding a value within `[min_value, max_value]`:

```sql
SELECT input_value,
       GREATEST(min_value,
           LEAST(input_value, max_value)
       ) AS clamped_value
FROM lab_ranges;
```

Logic:

1. `LEAST(input_value, max_value)` caps the upper bound: if input exceeds max, return max.
2. `GREATEST(min_value, ...)` enforces the lower bound: if the result is below min, return min.

Example:

| Min | Input | Max | Clamp |
|---:|---:|---:|---:|
| 0 | -5 | 100 | 0 |
| 0 | 40 | 100 | 40 |
| 0 | 150 | 100 | 100 |

If any argument can be `NULL`, the entire expression can evaluate to `NULL`. Decide before clamping whether `NULL` represents invalid data, a default value, or an unknown state.

### 11.2. Picking the lower price between list price and promotional price

```sql
SELECT product_id,
       LEAST(list_price, promotion_price) AS display_price
FROM product_prices;
```

Use this directly only when both columns are guaranteed non-NULL. If `PROMOTION_PRICE` is populated only during promotions and is `NULL` otherwise, the expression above returns NULL for non-promotional products. To fall back to list price when no promotion exists:

```sql
SELECT product_id,
       COALESCE(LEAST(list_price, promotion_price), list_price) AS display_price
FROM product_prices;
```

This assumes `LIST_PRICE` is present; if `LIST_PRICE` is also `NULL`, the result remains `NULL`. Enforce `LIST_PRICE NOT NULL` or write an explicit `CASE` if both columns can be missing.

### 11.3. Finding the earliest timestamp among multiple milestones

```sql
SELECT task_id,
       LEAST(planned_start, approved_start, actual_start) AS earliest_start
FROM task_schedule;
```

If any milestone has not been entered, the result is `NULL`. To find the earliest **known** milestone, handle NULLs explicitly. With three columns, you can write a `CASE` expression, or unpivot milestones into rows and take `MIN` over non-null values, balancing scalability and performance.

### 11.4. Finding the tighter deadline between SLA and customer deadline

```sql
SELECT ticket_id,
       LEAST(sla_deadline, customer_deadline) AS effective_deadline
FROM support_tickets;
```

This picks the earlier deadline. Yet if the customer set no deadline (`CUSTOMER_DEADLINE = NULL`), Oracle returns NULL; if `NULL` means "no extra customer deadline", you likely want `SLA_DEADLINE`. Express that business rule explicitly with `CASE`/`COALESCE` rather than leaving readers to guess.

## 12. JDBC and bind parameters: avoiding implicit conversion

Java applications should bind properly typed values instead of passing everything as strings. Example using `LEAST` on two numeric parameters:

```java
String sql = "SELECT LEAST(?, ?) AS lower_value FROM dual";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setBigDecimal(1, new BigDecimal("125.50"));
    ps.setBigDecimal(2, new BigDecimal("80.25"));

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            BigDecimal value = rs.getBigDecimal("lower_value");
            System.out.println(value);
        }
    }
}
```

The result is `80.25`. `BigDecimal` fits monetary data requiring decimal precision; avoid `double` for financial arithmetic.

### 12.1. Binding DATE/TIMESTAMP with matching types

```java
String sql = "SELECT LEAST(?, ?) AS earlier_date FROM dual";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setDate(1, java.sql.Date.valueOf("2026-11-01"));
    ps.setDate(2, java.sql.Date.valueOf("2026-11-15"));

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            java.sql.Date earlier = rs.getDate("earlier_date");
        }
    }
}
```

For timestamps with hour/minute/second or timezone data, choose the appropriate JDBC API (`setTimestamp`, `setObject` with driver-supported `java.time` types, etc.) and align timezones. Never bind `'01/11/2026'` as a string when you can bind a typed `DATE`.

### 12.2. Binding NULL requires a SQL type

When a parameter can be `NULL`, JDBC must supply the proper SQL type via `setNull`:

```java
ps.setNull(1, java.sql.Types.NUMERIC);
```

or use `setObject(index, null, sqlType)` as supported by your driver/framework. Binding untyped NULLs can cause type inference errors or unintended conversions. Also, if any `LEAST`/`GREATEST` argument is null, the result can be null; handle nullable results with `getBigDecimal`/`getDate` and check `wasNull()` when reading primitive types.

### 12.3. Never concatenate user-entered literals

Avoid:

```java
// Not recommended: concatenating user strings into SQL.
String sql = "SELECT LEAST(" + inputA + ", " + inputB + ") FROM dual";
```

Bind parameters prevent SQL injection and preserve contract data types. Note that binds replace **values**, not column names, table names, or SQL keywords; structural identifiers must come from an allowlist.

## 13. Common errors

| Symptom / Error | Possible Cause | Resolution |
|---|---|---|
| `LEAST` returns NULL even though one column has data | At least one argument is NULL | Clarify NULL semantics; use CASE/COALESCE if NULL should be skipped |
| `LEAST('10','2')` returns `'10'` | Character comparison, not numeric | Convert explicitly to numbers or fix schema |
| `ORA-01722: invalid number` | String converted to number contains invalid text | Inspect data, use controlled conversion with explicit format |
| `ORA-01861` / datetime errors | Date string mismatches format during implicit conversion | Use `DATE` literals or `TO_DATE` with format masks |
| `ORA-00932: inconsistent datatypes` | Arguments cannot convert to a compatible type | Check data types and add explicit `CAST` |
| Results differ between SQL client and app | Different NLS session, bind types, or timezones | Compare session parameters and bind types |
| String comparison produces unexpected order | Collation, binary/linguistic sort, `CHAR`/`VARCHAR2` | Check active collation and test real strings |
| Switching MIN and LEAST alters NULL behavior | Aggregate MIN ignores NULL; scalar LEAST propagates NULL | Pick the right function for row-level vs. group-level logic |
| Clamp returns NULL | One of min/input/max is NULL | Define missing-data policy before clamping |

Exact error codes depend on expressions and data types. Never mask errors by blindly replacing every NULL with 0 or an empty string; that hides bad data and corrupts business logic.

## 14. Oracle SQL practice lab

This lab uses dummy table `LAB_LEAST_GREATEST`. Run only in a **DEV/TEST** schema with `CREATE TABLE` privileges and quota. Confirm your container/service before running; never use live data or run DDL in production.

### Step 1 — Confirm your environment

```sql
SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name,
       SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
       SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user
FROM dual;
```

### Step 2 — Create table and load data

```sql
CREATE TABLE lab_least_greatest (
    item_id NUMBER PRIMARY KEY,
    price_a NUMBER(10, 2),
    price_b NUMBER(10, 2),
    start_date DATE,
    end_date DATE,
    code_a VARCHAR2(20 CHAR),
    code_b VARCHAR2(20 CHAR)
);

INSERT ALL
    INTO lab_least_greatest VALUES
        (1, 100, 80, DATE '2026-11-01', DATE '2026-11-10', 'A10', 'A20')
    INTO lab_least_greatest VALUES
        (2, 150, NULL, DATE '2026-11-05', DATE '2026-11-03', 'B20', 'B10')
    INTO lab_least_greatest VALUES
        (3, NULL, 90, NULL, DATE '2026-11-08', 'C30', 'C20')
    INTO lab_least_greatest VALUES
        (4, NULL, NULL, DATE '2026-11-04', NULL, NULL, 'D10')
SELECT 1 FROM dual;

COMMIT;
```

### Step 3 — Row-level comparison

```sql
SELECT item_id,
       price_a,
       price_b,
       LEAST(price_a, price_b) AS least_price,
       GREATEST(price_a, price_b) AS greatest_price
FROM lab_least_greatest
ORDER BY item_id;
```

Observations:

- Row 1: results are 80 and 100, respectively.
- Row 2: both expressions return NULL because `PRICE_B` is NULL.
- Row 3: both expressions return NULL because `PRICE_A` is NULL.
- Row 4: both expressions return NULL because both arguments are NULL.

### Step 4 — Selecting known prices per business rules

```sql
SELECT item_id,
       CASE
           WHEN price_a IS NULL THEN price_b
           WHEN price_b IS NULL THEN price_a
           ELSE LEAST(price_a, price_b)
       END AS least_known_price
FROM lab_least_greatest
ORDER BY item_id;
```

Results: 80, 150, 90, NULL. Explain why rows 2 and 3 differ from Step 3.

### Step 5 — Comparing dates

```sql
SELECT item_id,
       start_date,
       end_date,
       LEAST(start_date, end_date) AS earlier_date,
       GREATEST(start_date, end_date) AS later_date
FROM lab_least_greatest
ORDER BY item_id;
```

Row 1 has earlier date 01/11 and later date 10/11; row 2 has 03/11 and 05/11; rows 3 and 4 return NULL because at least one milestone is NULL. If the requirement is "earliest known date", write separate NULL-skipping logic.

### Step 6 — Testing type conversion

```sql
SELECT LEAST(10, '2') AS numeric_result,
       LEAST('10', 2) AS character_result
FROM dual;
```

Observe the type and result differences. Next, run a **separate test statement in the lab** with an unconvertible string:

```sql
-- Intentionally triggers a conversion error; omit from automated scripts.
SELECT LEAST(10, 'TEN') FROM dual;
```

Record the actual error code and explain why having NUMBER as the first argument forces Oracle to convert the string to a number.

### Step 7 — Comparing scalar vs. aggregate

```sql
SELECT MIN(price_a) AS min_price_a,
       MAX(price_a) AS max_price_a,
       MIN(LEAST(price_a, price_b)) AS min_of_row_least
FROM lab_least_greatest;
```

Explain why `MIN(price_a)` returns a value despite NULL rows, whereas `LEAST(price_a, price_b)` evaluates to NULL on those rows and is ignored by the outer `MIN`.

### Step 8 — Clean up practice data

Only when you confirm this is the lab table you created in DEV/TEST and no one else is using it:

```sql
DROP TABLE lab_least_greatest PURGE;
```

This DDL statement drops the object and data without placing it in the recycle bin. Never run it on production or any table outside your lab scope.

## 15. Pre-use mental checklist for LEAST/GREATEST

Before placing these expressions in a view, report, stored procedure, or API, ask:

1. Am I comparing **multiple columns in the same row** or aggregating **across multiple rows**? For multiple rows, use `MIN`/`MAX`.
2. Do all arguments share the same data type? If not, how will the first argument's type drive conversions?
3. If an argument is NULL, is returning NULL valid under business rules?
4. If skipping NULLs, should we pick the remaining value, apply a default, or report incomplete data?
5. Are any numeric/date strings depending on session NLS? Can we use explicit `TO_NUMBER`, `TO_DATE`, or `CAST`?
6. For Unicode strings, do active collation and locale match comparison requirements?
7. Does the JDBC application bind proper types (`BigDecimal`, `Date`, `Timestamp`) and handle nullable results?
8. Will the query run on large tables? Should we check the execution plan and cost if the function appears in a predicate?

## 16. Review questions

**Question 1.** What does `LEAST(10, 5, 20)` return?

**Answer:** `5`, the smallest value among the numeric arguments.

**Question 2.** What does `GREATEST(10, NULL, 20)` return in Oracle?

**Answer:** `NULL`, because one argument is NULL.

**Question 3.** Why does `LEAST(10, '2')` return 2 while `LEAST('10', 2)` returns `'10'`?

**Answer:** In the first call, the first argument is NUMBER so Oracle converts the string to a number; in the second, the first argument is character so Oracle converts the number to character and compares lexicographically.

**Question 4.** How does `LEAST` differ from `MIN` regarding NULLs?

**Answer:** `LEAST` returns NULL if any argument is NULL; aggregate `MIN` ignores NULLs as long as non-null values exist in the group.

**Question 5.** Why can `LEAST(DATE '2026-01-01', '02/01/2026')` depend on session settings?

**Answer:** The date string undergoes implicit conversion to DATE using `NLS_DATE_FORMAT`; use `TO_DATE` with an explicit format mask.

**Question 6.** How should you pick the lower of two price columns while ignoring a NULL column if the other has a value?

**Answer:** Use `CASE` to check each column for NULL and call `LEAST` only when both are populated.

**Question 7.** Does `COALESCE(sale_price, regular_price)` pick the lower price?

**Answer:** No. It returns the first non-NULL value in argument order; it does not compare magnitudes.

**Question 8.** When comparing strings with `LEAST`, does `AL32UTF8` guarantee case-insensitive comparison?

**Answer:** No. Character set and collation are separate concepts; verify active collation and NLS rules.

**Question 9.** Why should JDBC bind dates and numbers with native data types instead of strings?

**Answer:** It avoids NLS-dependent implicit conversions, reduces formatting bugs, and keeps data contracts explicit.

**Question 10.** Do `LEAST` and `GREATEST` automatically skip NULL arguments like MIN/MAX?

**Answer:** No. In Oracle, a single NULL argument causes these scalar functions to return NULL; skipping NULLs requires explicit logic.

## Conclusion

**`LEAST` selects the smallest value and `GREATEST` selects the largest value among passed expressions, typically within a single row.** They differ from aggregate `MIN`/`MAX` in scope and especially in `NULL` handling: in Oracle, a single NULL argument makes `LEAST`/`GREATEST` return NULL. When business rules require skipping unknown values or substituting defaults, write it explicitly using `CASE`, `COALESCE`, or `NVL`.

Type-conversion rules are equally vital: when the first argument is numeric, Oracle applies numeric precedence; when the first argument is non-numeric, subsequent arguments are converted to the first argument's type before comparison. Consequently, `LEAST(10, '2')` and `LEAST('10', 2)` yield different outcomes. Standardize data types, use explicit `CAST`/`TO_NUMBER`/`TO_DATE`, avoid implicit NLS dependencies, and bind proper types from JDBC. For multilingual string comparisons, verify collation rather than relying solely on the character set. These practices keep expressions concise, accurate, and consistent across environments.
