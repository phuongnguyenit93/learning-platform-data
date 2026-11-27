# Implicit Data Type Conversion, NLS, and Causes of Lost Index Access Paths

Oracle allows many SQL expressions to use values of different data types. When needed, the database can automatically convert one operand to the data type of the other operand. This mechanism is called **implicit data type conversion**. It makes SQL statements concise, but it can make results depend on session NLS settings, cause data errors, increase CPU usage, and most importantly, alter the expression on a column so that the optimizer cannot use the index access path the author expected.

A SQL statement might run correctly on a development machine yet fail in production because `NLS_DATE_FORMAT` or `NLS_NUMERIC_CHARACTERS` differs. A predicate that appears to compare a column directly with a bind value might become `TO_NUMBER(column) = :bind`; in that case, a regular index on the column may no longer be suitable. Similarly, `NLS_SORT`, collation, bind types from JDBC/ODP.NET, and functions like `UPPER`, `TRUNC`, and `NVL` can change how Oracle compares data or chooses an access path.

After this lesson, you will be able to:

- Identify implicit conversion in comparisons, joins, arithmetic, and function calls.
- Understand common conversion rules between NUMBER, character, DATE, and TIMESTAMP.
- Avoid depending on NLS_DATE_FORMAT and NLS_NUMERIC_CHARACTERS.
- Distinguish conversion on a bind/constant from conversion wrapping a column.
- Explain why conversion on a column can prevent index range scans or partition pruning.
- Understand the impact of CHAR, VARCHAR2, NCHAR, NVARCHAR2, and collation.
- Recognize the effects of NLS_COMP, NLS_SORT, and session settings.
- Bind data using the correct data type in the application.
- Use explicit conversion, format models, and NLS parameters explicitly.
- Design function-based indexes or virtual columns when querying by expression is a stable requirement.
- Read Predicate Information to find conversions in an execution plan.
- Diagnose ORA-01722, ORA-01843, ORA-01861, and common conversion errors.

> Conversion rules, collation, and SQL features may vary by Oracle version and data type. Examples in this lesson focus on common types; check the SQL Language Reference for your exact release, driver, and system NLS settings.

## 1. Data Types Are Part of SQL Semantics

### 1.1. Why Do Data Types Matter?

A data type determines:

- Which values can be stored.
- Which operations are meaningful.
- How values are compared and sorted.
- How conversion occurs between data and text.
- Precision, scale, character set, and length semantics.
- Which access paths the optimizer can use.

NUMBER, VARCHAR2, and DATE are not just different ways of storing the same value. NUMBER is compared arithmetically; VARCHAR2 is compared using character/collation rules; DATE represents a date and time down to the second. If NUMBER is compared with VARCHAR2, Oracle must choose a conversion rule to produce an evaluable expression.

### 1.2. Explicit and Implicit Conversion

Explicit conversion is specified by the author:

```sql
SELECT TO_NUMBER('1250') + 10
FROM dual;

SELECT TO_DATE(
           '2026-11-14',
           'YYYY-MM-DD'
       )
FROM dual;
```

Implicit conversion is performed by Oracle according to data type rules:

```sql
SELECT 1250 + '10'
FROM dual;
```

Oracle can convert the character value `'10'` to NUMBER to perform addition. The statement may run, but the reader cannot clearly see the conversion, and an input that is not a valid numeric string can cause an error.

### 1.3. Conversion Is Not Always Harmless

A conversion can:

- Change how comparisons behave.
- Depend on session NLS settings.
- Lose information or precision.
- Raise an error only when a specific row is evaluated.
- Wrap a function around an indexed column.
- Prevent partition pruning in some expressions.
- Cause the optimizer to estimate cardinality differently.

Therefore, explicit conversion and proper bind typing are part of SQL design, not merely a matter of style.

## 2. Common Implicit Conversion Rules

### 2.1. Character and NUMBER

In many comparisons between NUMBER and character, Oracle converts the character expression to NUMBER. For example:

```sql
SELECT *
FROM products
WHERE product_id = '100';
```

If PRODUCT_ID is NUMBER, Oracle can convert the literal `'100'` to NUMBER. Because the literal is a constant, the resulting expression can still be equivalent to:

```sql
WHERE product_id = 100
```

An index on PRODUCT_ID can still be used. However, you should not rely on implicit conversion; use a NUMBER bind or a properly typed literal.

### 2.2. Character Column Compared with NUMBER

If the column is VARCHAR2 while the bind/literal is NUMBER:

```sql
SELECT *
FROM legacy_products
WHERE product_code = 100;
```

Oracle may convert the character column to NUMBER:

```sql
WHERE TO_NUMBER(product_code) = 100
```

When the conversion wraps the column, a regular B-tree index on PRODUCT_CODE no longer directly matches the predicate expression. In addition, if a row contains `A100` or a non-numeric value, the SQL statement may raise ORA-01722.

### 2.3. Character and DATE

Comparing DATE with a string can cause the string to be converted to DATE using NLS_DATE_FORMAT:

```sql
SELECT *
FROM orders
WHERE order_date = '14-11-2026';
```

The result depends on the session's date format. If the session expects `DD-MON-RR`, the string above may fail; if the session uses `DD-MM-YYYY`, it may run. Use a DATE literal or TO_DATE with an explicit format mask.

### 2.4. DATE and TIMESTAMP

DATE and TIMESTAMP can be converted so that both sides have compatible data types. DATE does not store fractional seconds or a time zone; TIMESTAMP has fractional seconds; TIMESTAMP WITH TIME ZONE has time zone/offset information.

When comparing them, you need to understand how the data types are promoted/converted and what precision is preserved. Do not assume DATE and TIMESTAMP carry the same amount of information.

### 2.5. NUMBER and Binary Floating Point

Oracle NUMBER is a decimal numeric type with high precision within Oracle's limits; BINARY_FLOAT and BINARY_DOUBLE are binary floating-point types. When mixing numeric types, Oracle follows numeric precedence rules. The result may have different rounding semantics than NUMBER.

For currency, quantities, and values requiring decimal semantics, use NUMBER with appropriate precision/scale; avoid converting through binary floating point without a clear reason.

### 2.6. Do Not Rely on "Oracle Figuring It Out"

You should not rely on Oracle automatically converting:

- Date strings using a default format.
- Numeric strings using the session's decimal separator.
- Identifiers into numbers.
- NCHAR/VARCHAR2 across unclear character sets.
- Text binds into DATE/NUMBER in business SQL.

Define data types at the application boundary and perform explicit conversion when input is genuinely text.

## 3. Which Side of the Predicate Has the Conversion?

### 3.1. Column Preserved, Bind/Literal Converted

Suppose there is an index on ORDERS.ORDER_ID and ORDER_ID is NUMBER:

```sql
SELECT *
FROM orders
WHERE order_id = '12345';
```

If Oracle converts the literal to NUMBER, the predicate has the equivalent form:

```sql
WHERE order_id = 12345
```

The column still appears directly. An index range scan may be available if the cost and selectivity are appropriate.

### 3.2. Conversion Wrapping the Column

Suppose LEGACY_CODE is VARCHAR2 and there is an index on the column:

```sql
SELECT *
FROM legacy_items
WHERE TO_NUMBER(legacy_code) = :p_id;
```

A regular index on LEGACY_CODE stores character values, whereas the predicate searches by the expression `TO_NUMBER(LEGACY_CODE)`. Oracle cannot treat the two expressions as the same key without a corresponding function-based index or a valid transformation.

### 3.3. Sargability

A predicate is called sargable when the optimizer can use it to search via an access path such as an index or partition pruning rather than having to compute an expression across many rows before filtering. This term is a practical shorthand; actual index usage also depends on cost, statistics, index type, and the entire query.

Sargable example:

```sql
WHERE order_date >= DATE '2026-11-14'
  AND order_date <  DATE '2026-11-15'
```

Example with a function on the column:

```sql
WHERE TRUNC(order_date) = DATE '2026-11-14'
```

The second predicate may require computing `TRUNC` on column values. Without a matching function-based index, a regular index on ORDER_DATE may not be usable for an equality lookup of the `TRUNC` expression.

### 3.4. Conversion on the Bind Side Is Usually Easier to Optimize

If the column is NUMBER and the application receives text, convert the bind text once:

```sql
WHERE order_id = TO_NUMBER(:p_order_id_text)
```

When the bind is a valid numeric string and the format is specified, the conversion is on the bind expression side; the ORDER_ID column remains unmodified. However, it is even better for the application to bind a NUMBER directly to avoid parsing text in the database.

### 3.5. A Function Does Not Always Guarantee the Index Is Lost

Oracle can use a function-based index, a virtual column index, or a suitable transformation. In addition, the optimizer might choose a full table scan because its cost is lower. Diagnosis must be based on the predicate expression and the actual execution plan, not on the SQL syntax alone.

## 4. Implicit Conversion and Index Access

### 4.1. NUMBER Column Example

Suppose:

```sql
CREATE TABLE lab_number_codes (
    code_id NUMBER PRIMARY KEY,
    description VARCHAR2(100)
);
```

Properly typed predicate:

```sql
SELECT *
FROM lab_number_codes
WHERE code_id = :p_code_id;
```

The application binds `:p_code_id` as NUMBER. The optimizer can use the unique index/primary key index.

### 4.2. VARCHAR2 Column Example

Suppose:

```sql
CREATE TABLE lab_text_codes (
    code VARCHAR2(30) PRIMARY KEY,
    description VARCHAR2(100)
);
```

Predicate:

```sql
SELECT *
FROM lab_text_codes
WHERE code = 100;
```

If Oracle must convert CODE to NUMBER, values like `00100`, `100A`, and `100` may no longer have distinct semantics as character codes. The conversion can fail on non-numeric rows, and the index on CODE may not be usable for the expected access path.

If CODE is an identifier, bind a string:

```sql
WHERE code = :p_code
```

and bind `:p_code` as VARCHAR2.

### 4.3. Joining Two Columns of Different Data Types

For example:

```sql
SELECT *
FROM numeric_accounts n
JOIN legacy_accounts l
  ON n.account_id = l.account_code;
```

If ACCOUNT_ID is NUMBER and ACCOUNT_CODE is VARCHAR2, Oracle may convert the character side to NUMBER. This can:

- Wrap `TO_NUMBER` around `L.ACCOUNT_CODE`.
- Prevent using a regular index on ACCOUNT_CODE for the join key.
- Raise ORA-01722 if legacy data contains non-numeric characters.
- Make join cardinality and cost estimates less accurate.

The sustainable solution is to standardize the data type on both sides at the schema/ETL level rather than forcing every query to convert.

### 4.4. Join Keys with Leading Zeros

If `000123` and `123` are two different codes in business logic, do not convert them to NUMBER. Conversion strips leading zeros and causes the two keys to be treated as the same numeric value.

Text identifiers should use a character data type in both tables and bind strings. If a value is truly numeric, store NUMBER consistently.

### 4.5. Implicit Conversion in UNION/CASE/COALESCE

Expressions that return multiple data types may require Oracle to choose a common type:

```sql
SELECT CASE
         WHEN is_active = 'Y' THEN amount
         ELSE '0'
       END AS result_value
FROM invoices;
```

One branch is NUMBER, and the other is VARCHAR2. Oracle must resolve data type compatibility; conversion can cause errors or produce an unexpected result type. Write it explicitly:

```sql
SELECT CASE
         WHEN is_active = 'Y' THEN amount
         ELSE 0
       END AS result_value
FROM invoices;
```

Keep all branches the same data type and cast explicitly when required by the contract.

## 5. What Is NLS and How Does It Affect SQL?

### 5.1. NLS Settings

NLS (National Language Support) is a group of settings that affect how Oracle interprets, formats, and compares data according to language/region. Common settings:

| Setting | Impact |
| --- | --- |
| NLS_DATE_FORMAT | Default format when converting DATE to/from character in certain contexts |
| NLS_TIMESTAMP_FORMAT | Default format for TIMESTAMP |
| NLS_TIMESTAMP_TZ_FORMAT | Default format for TIMESTAMP WITH TIME ZONE |
| NLS_NUMERIC_CHARACTERS | Decimal separator and thousands grouping character |
| NLS_DATE_LANGUAGE | Month/day names and language tokens in date conversion |
| NLS_TERRITORY | Regional defaults, date/number formats, and related rules |
| NLS_SORT | Linguistic sorting/comparison rules |
| NLS_COMP | Character comparison mode |
| NLS_LENGTH_SEMANTICS | Default BYTE/CHAR when creating character columns in certain contexts |

Sessions can have different NLS settings depending on the client, connection pool, and `ALTER SESSION` statements. Do not assume a developer machine's configuration matches a production session.

### 5.2. Checking Session NLS

```sql
SELECT parameter, value
FROM nls_session_parameters
ORDER BY parameter;
```

You can check the corresponding database/instance parameters using `NLS_DATABASE_PARAMETERS` or `NLS_INSTANCE_PARAMETERS`. When investigating errors, session parameters are the starting point because conversions are often affected by session settings.

### 5.3. NLS Is Not a Data Type

`NLS_DATE_FORMAT` does not turn a DATE column into VARCHAR2. It affects how characters are represented/parsed in certain conversions. Similarly, `NLS_NUMERIC_CHARACTERS` does not turn NUMBER into text; it affects how the decimal point and grouping separator are interpreted/formatted.

Do not use NLS settings as a substitute for explicit data types.

## 6. NLS_DATE_FORMAT and Date Errors

### 6.1. Implicit Date Conversion

Risky example:

```sql
SELECT *
FROM orders
WHERE order_date = '14-11-2026';
```

Oracle needs to convert the character literal to DATE. If `NLS_DATE_FORMAT` is `DD-MM-YYYY`, it may parse; if it is `MM/DD/RR`, the string may fail or mean something different.

### 6.2. DATE Literal

Use an ANSI DATE literal for fixed dates:

```sql
SELECT *
FROM orders
WHERE order_date >= DATE '2026-11-14'
  AND order_date <  DATE '2026-11-15';
```

A DATE literal uses the `YYYY-MM-DD` format and does not depend on `NLS_DATE_FORMAT`. DATE contains both date and time down to the second; equality with a DATE literal matches midnight of that day, so a range is usually more accurate when you need all times within a day.

### 6.3. TO_DATE with a Format Mask

If user input is text:

```sql
WHERE order_date >= TO_DATE(
    :p_start_text,
    'YYYY-MM-DD'
)
```

If months are named in a specific language, specify `NLS_DATE_LANGUAGE`:

```sql
SELECT TO_DATE(
           '14-NOV-2026',
           'DD-MON-YYYY',
           'NLS_DATE_LANGUAGE=American'
       )
FROM dual;
```

Do not rely on month names using the session's default language.

### 6.4. TIMESTAMP Literal

Use a timestamp literal:

```sql
SELECT TIMESTAMP '2026-11-14 08:30:00.123456'
FROM dual;
```

For timestamps with a time zone, use the appropriate data type/literal or `TO_TIMESTAMP_TZ` with an explicit format mask and time zone. Do not parse an instant into DATE if you need to preserve the offset/time zone.

### 6.5. Avoid TO_CHAR on DATE Columns in WHERE

Not recommended:

```sql
WHERE TO_CHAR(order_date, 'YYYY-MM-DD') = '2026-11-14'
```

The expression applies `TO_CHAR` to every column value and typically prevents a direct index range scan on ORDER_DATE. Use a range predicate:

```sql
WHERE order_date >= DATE '2026-11-14'
  AND order_date <  DATE '2026-11-15'
```

If the business logic genuinely queries by a fixed `TO_CHAR` expression, a function-based index can be considered, though you must account for NLS/format semantics and maintenance cost.

## 7. NLS_NUMERIC_CHARACTERS and Numeric Conversion

### 7.1. Decimal and Grouping Characters

`NLS_NUMERIC_CHARACTERS` specifies the decimal character and the thousands grouping character. For example:

- `.,` : period for decimal, comma for grouping.
- `,.` : comma for decimal, period for grouping.

The strings `1,234.56` and `1.234,56` can represent the same value under different conventions. If implicit conversion depends on session NLS, the same input can parse differently or fail.

### 7.2. TO_NUMBER with a Format Model

If the input string uses a period for the decimal point and a comma for grouping:

```sql
SELECT TO_NUMBER(
           '1,234.56',
           '9G999D99',
           'NLS_NUMERIC_CHARACTERS = ''.,'''
       )
FROM dual;
```

In the format model:

- `D` is the decimal character according to `NLS_NUMERIC_CHARACTERS`.
- `G` is the grouping character according to `NLS_NUMERIC_CHARACTERS`.

Only use a format model that matches the actual input. Do not try to parse multi-format data with a single ambiguous mask.

### 7.3. TO_CHAR NUMBER

When generating text from NUMBER, use an explicit format model and NLS parameter:

```sql
SELECT TO_CHAR(
           1234.56,
           'FM999G999D00',
           'NLS_NUMERIC_CHARACTERS = ''.,'''
       )
FROM dual;
```

`TO_CHAR` output is text in the chosen format. If text is used for exchanging data between services, the contract must fix the decimal character, scale, and grouping rules.

### 7.4. Do Not Use TO_CHAR and Then Implicitly Convert Back

Poor pattern:

```sql
WHERE amount = TO_CHAR(:p_amount)
```

The two sides have different types; Oracle may have to convert back or handle it according to data type rules. If AMOUNT is NUMBER, bind NUMBER:

```sql
WHERE amount = :p_amount
```

If the input is text, parse it to NUMBER at the ingestion boundary and then bind NUMBER. Avoid creating a NUMBER → text → NUMBER round trip.

### 7.5. NLS and String Binds

If the application binds a number as VARCHAR2, Oracle may convert the text to NUMBER according to session NLS. Use driver APIs to bind the proper type:

- JDBC: `setBigDecimal` for decimals, `setLong`/`setInt` for integers where appropriate.
- ODP.NET: use `OracleDbType.Decimal`/`Int32`/`Int64` accordingly.
- OCI or other drivers: declare the appropriate bind data type.

Exact API names depend on the driver, but the principle is to bind the exact data type of the column and contract.

## 8. CHAR, VARCHAR2, NCHAR, and NVARCHAR2

### 8.1. CHAR and VARCHAR2

CHAR has a fixed length and is blank-padded to its declared length. VARCHAR2 has a variable length. Comparison rules between two character expressions can differ depending on data type and blank-padding semantics.

For example:

```sql
CREATE TABLE lab_char_compare (
    fixed_code CHAR(5),
    variable_code VARCHAR2(5)
);

INSERT INTO lab_char_compare
VALUES ('A', 'A');
```

Do not assume CHAR and VARCHAR2 behave identically when comparing strings with trailing spaces. When joining or comparing two columns of different types, understand conversion/blank-padding behavior and inspect actual data.

### 8.2. NCHAR and NVARCHAR2

NCHAR/NVARCHAR2 use the national character set. When comparing them with CHAR/VARCHAR2, Oracle may need to convert between the database character set and the national character set. This conversion can affect CPU, character representability, and the predicate expression.

Do not choose NCHAR/NVARCHAR2 merely because data contains Unicode; the `AL32UTF8` database character set already supports Unicode. Choose data types based on the existing schema, contract, and character set policy.

### 8.3. BYTE and CHAR Length Semantics

VARCHAR2 can declare its length in BYTE or CHAR:

```sql
CREATE TABLE lab_text_lengths (
    code_byte VARCHAR2(20 BYTE),
    code_char VARCHAR2(20 CHAR)
);
```

BYTE limits the number of bytes; CHAR limits the number of characters under Oracle semantics. With multibyte character sets, 20 characters can require more than 20 bytes. `NLS_LENGTH_SEMANTICS` affects the default when creating a column if not specified, but it does not alter the meaning of an already created column.

### 8.4. Comparing Across Character Sets

If two columns use different character data types, conversion may be performed according to character set compatibility. Characters that cannot be represented in the target set can cause errors or data loss depending on the conversion path/configuration.

When designing new schemas, prefer a database character set that supports Unicode (commonly `AL32UTF8`) and keep data types consistent. For legacy systems, check character sets before migrating or casting.

## 9. NLS_SORT, NLS_COMP, and Collation

### 9.1. Binary and Linguistic Comparison

Character comparison can be based on binary representation or linguistic rules. For example, case-insensitive or accent-insensitive rules can treat strings with different bytes as equivalent in certain comparisons/sorts.

`NLS_SORT` defines the linguistic sort order. `NLS_COMP` affects how linguistic comparison is applied in SQL. Specific settings may be inherited from the database/session and differ across connections.

### 9.2. Checking NLS_COMP and NLS_SORT

```sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_COMP',
    'NLS_SORT',
    'NLS_LANGUAGE',
    'NLS_TERRITORY'
)
ORDER BY parameter;
```

Do not change these settings in production to experiment without evaluating the impact on all SQL executed on the session/connection pool.

### 9.3. LINGUISTIC Comparison

When using `NLS_COMP = LINGUISTIC`, character comparisons can follow `NLS_SORT` instead of only binary comparison, within the scope supported by Oracle. This can change equality results, `ORDER BY`, and access paths.

For example:

```sql
ALTER SESSION SET NLS_COMP = LINGUISTIC;
ALTER SESSION SET NLS_SORT = BINARY_CI;

SELECT *
FROM lab_names
WHERE person_name = 'smith';
```

`BINARY_CI` is a sort setting that is case-insensitive according to binary case-insensitive rules. Check the availability and semantics of sort names on your specific version.

### 9.4. Why Might a Regular Index Not Be Suitable?

A regular B-tree index on PERSON_NAME is built using the column's expression/key semantics. If a query needs to compare using `NLSSORT` or a linguistic key different from the index key, Oracle may need to evaluate the conversion expression or choose a full scan.

If the workload frequently needs a specific case-insensitive/linguistic rule, you can create a function-based index on the corresponding `NLSSORT` expression, or use collation-aware design supported in your release.

### 9.5. Function-Based Index with NLSSORT

Illustrative example:

```sql
CREATE INDEX ix_lab_names_ci
ON lab_names (
    NLSSORT(person_name, 'NLS_SORT=BINARY_CI')
);
```

The predicate/query needs to use a compatible expression:

```sql
SELECT *
FROM lab_names
WHERE NLSSORT(
          person_name,
          'NLS_SORT=BINARY_CI'
      ) = NLSSORT(
          :p_name,
          'NLS_SORT=BINARY_CI'
      );
```

A function-based index can support an access path using the linguistic key. Verify the plan, collation rules, and behavior during Oracle upgrades; do not mix expressions with inconsistent NLS settings.

### 9.6. Column-Level Collation

Modern Oracle versions support column/expression-level collation in certain configurations, such as `BINARY_CI` or `BINARY_AI`. Availability depends on the release, compatibility, and `MAX_STRING_SIZE`/configuration. Collation declarations can make comparison semantics explicit instead of changing session-wide `NLS_COMP`.

Before using it, confirm collation is supported for the data type/column/index and client. Do not assume a collation syntax runs across all Oracle versions.

## 10. Functions on Columns and Lost Index Access

### 10.1. UPPER/LOWER

Predicate:

```sql
SELECT *
FROM customers
WHERE UPPER(email) = UPPER(:p_email);
```

A regular index on EMAIL does not necessarily support an equality lookup of `UPPER(EMAIL)`. If case-insensitive lookup is a common workload, create a function-based index:

```sql
CREATE INDEX ix_customers_email_upper
ON customers (UPPER(email));
```

Then the query uses the same expression. Alternatively, normalize/store a canonical email using a clear rule while keeping the original value if needed.

### 10.2. TRUNC on DATE

Avoid by default:

```sql
WHERE TRUNC(created_at) = DATE '2026-11-14'
```

Prefer a range:

```sql
WHERE created_at >= DATE '2026-11-14'
  AND created_at <  DATE '2026-11-15'
```

A range predicate allows an index range scan on CREATED_AT and often enables partition pruning if CREATED_AT is the partition key.

### 10.3. NVL/COALESCE on a Column

Predicate:

```sql
WHERE NVL(status, 'N') = 'Y'
```

The expression `NVL(STATUS,'N')` may not match a regular index on STATUS. In this example, the expression can be rewritten equivalently as:

```sql
WHERE status = 'Y'
```

Because NULL does not equal `'Y'`. However, do not rewrite it if the default value has different semantics or involves a different data type conversion.

### 10.4. Arithmetic on a Column

Predicate:

```sql
WHERE salary + 1000 > :p_limit
```

Can be rewritten as:

```sql
WHERE salary > :p_limit - 1000
```

This rewrite requires attention to overflow, NULL, and numeric data type/rounding. For regular NUMBER and linear addition, it can preserve semantics; for floating-point types or complex expressions, verify carefully.

### 10.5. CAST and TO_CHAR

`CAST(column AS datatype)`, `TO_CHAR(column)`, or `TO_NUMBER(column)` all create an expression on the column. If an index was created on the original column, do not assume Oracle can use it for the cast expression. Consider explicit conversion on the bind side, fixing the schema data type, or creating a function-based index when the expression is a stable requirement.

### 10.6. OR and Multiple Expressions

Predicates with multiple `OR` branches, functions, or mixed data types can cause the optimizer to choose OR expansion, bitmap operations, or a full scan. Do not conclude an index is lost solely because `OR` is present; read the plan to see whether each branch has its own access path.

## 11. Bind Data Types and the Application

### 11.1. Bind Variables Have Data Types

A bind variable is not just a placeholder holding a value. When the driver binds it, it sends the data type, length, and related attributes. If the column is NUMBER but the application binds VARCHAR2, Oracle may have to convert it. If the column is DATE but the application binds a string, the conversion may depend on NLS.

SQL:

```sql
SELECT *
FROM orders
WHERE order_id = :p_order_id
  AND order_date >= :p_start_date;
```

The application should bind `p_order_id` as NUMBER and `p_start_date` as DATE/TIMESTAMP accordingly, not as a formatted date string.

### 11.2. JDBC

With JDBC, choose the appropriate setter:

- `setLong`/`setInt` for integers based on value range.
- `setBigDecimal` for decimal NUMBER.
- `setDate` for SQL DATE when semantics match.
- `setTimestamp` for TIMESTAMP.
- `setString` for VARCHAR2/character.

Do not use `setString` for every bind just because the initial input came from an HTTP form. Parse/validate at the application boundary, then bind the proper data type.

### 11.3. ODP.NET

With ODP.NET, declare `OracleDbType` explicitly such as `Decimal`, `Int32`, `Date`, `TimeStamp`, or `Varchar2`. Avoid letting the provider infer from the .NET object type when the target data type requires exact semantics.

### 11.4. Connection Pools and Session NLS

Connection pools reuse sessions. If request A runs `ALTER SESSION` to change NLS settings and request B receives the same physical connection, request B can inherit unexpected settings if the pool does not reset session state.

Do not rely on mutable session NLS for parsing business data. If you must change session settings, manage/reset them explicitly at the pool boundary and verify reused connections.

### 11.5. Bind Mismatch and Child Cursors

Binds with different data types/sizes or incompatible session environments can affect cursor sharing and create child cursors in some cases. When there are unusually many child cursors, check `V$SQL_SHARED_CURSOR`, `V$SQL`, and bind metadata with DBA privileges.

Do not conclude every bind data type mismatch definitely creates a child cursor; this is one factor to check alongside bind sensitivity, optimizer environment, and other cursor incompatibility reasons.

## 12. Proper Explicit Conversion

### 12.1. Converting Text to NUMBER

If input is text, parse it once with an explicit format model:

```sql
SELECT TO_NUMBER(
           :p_amount_text,
           '9999999990D99',
           'NLS_NUMERIC_CHARACTERS = ''.,'''
       )
FROM dual;
```

Then bind NUMBER into business queries. Do not let every predicate parse text according to session NLS.

### 12.2. Converting Text to DATE

```sql
SELECT TO_DATE(
           :p_date_text,
           'YYYY-MM-DD'
       )
FROM dual;
```

If month names are written in words, add `NLS_DATE_LANGUAGE`. If the input includes a time zone, use `TO_TIMESTAMP_TZ` and the corresponding format mask; do not force it into DATE if you need to keep the offset.

### 12.3. CAST and CONVERT

`CAST` is used to convert data types according to the SQL type system:

```sql
SELECT CAST(:p_value AS NUMBER(12,2))
FROM dual;
```

`CONVERT` relates to character set conversion; it is not a date/number parsing function. Do not confuse `CONVERT` with `TO_NUMBER`/`TO_DATE`.

### 12.4. Explicit Conversion Can Still Lose Index Access

Explicit does not mean optimal. For example:

```sql
WHERE TO_NUMBER(varchar_code) = :p_number
```

This still wraps the conversion around the column and can prevent a regular index on VARCHAR_CODE. The goal is to place conversion at the right boundary, not merely to add a `TO_` function to every expression.

### 12.5. Using VALIDATE_CONVERSION When Appropriate

Oracle provides `VALIDATE_CONVERSION` in modern releases to check whether an expression can be converted to a target data type:

```sql
SELECT varchar_code
FROM legacy_items
WHERE VALIDATE_CONVERSION(
          varchar_code AS NUMBER
      ) = 1;
```

This function is useful in data cleansing/staging. Do not assume a `VALIDATE_CONVERSION` predicate turns an index on a text column into a numeric index; it may still need to evaluate many rows.

### 12.6. DEFAULT ON CONVERSION ERROR

Some conversion functions support `DEFAULT ... ON CONVERSION ERROR` depending on the version, such as `TO_NUMBER`/`TO_DATE` in supported releases:

```sql
SELECT TO_NUMBER(
           'not-a-number' DEFAULT NULL ON CONVERSION ERROR
       )
FROM dual;
```

This is a proactive way to choose a result when conversion fails. Do not use NULL/default to silently accept invalid data if the contract requires rejecting it.

## 13. Function-Based Indexes and Virtual Columns

### 13.1. When to Use a Function-Based Index?

If querying by an expression is a stable requirement, such as `UPPER(email)`, `TRUNC(order_date)`, or `NLSSORT(name)`, you can create an index on that expression:

```sql
CREATE INDEX ix_orders_order_day
ON orders (TRUNC(order_date));
```

The query uses the same expression:

```sql
SELECT *
FROM orders
WHERE TRUNC(order_date) = DATE '2026-11-14';
```

Oracle can use the function-based index if the expression is compatible and the cost is appropriate.

### 13.2. Virtual Columns

A virtual column defines an expression in the schema:

```sql
ALTER TABLE legacy_items ADD (
    numeric_code GENERATED ALWAYS AS (
        CASE
            WHEN VALIDATE_CONVERSION(
                     varchar_code AS NUMBER
                 ) = 1
            THEN TO_NUMBER(varchar_code)
        END
    ) VIRTUAL
);

CREATE INDEX ix_legacy_items_numeric_code
ON legacy_items(numeric_code);
```

This is an illustrative example; the expression and `VALIDATE_CONVERSION` must be supported in your release. For legacy data, it is better to clean and standardize the data type if the business data is truly numeric.

### 13.3. Function-Based Indexes Have Costs

Indexed expressions:

- Consume storage.
- Increase INSERT/UPDATE/DELETE overhead.
- Require appropriate statistics.
- May need rebuilding if function implementation or collation assumptions change.
- Must use compatible expressions in queries.

Do not create a function-based index merely to mask a schema mismatch that can be fixed at the root.

### 13.4. DETERMINISTIC and User-Defined Functions

If a user-defined function is used in a function-based index, Oracle requires the function to be declared `DETERMINISTIC`. The author must guarantee that the same input produces the same output; it must not depend on mutable tables, `SYSDATE`, session NLS, or package state.

Do not declare `DETERMINISTIC` just to make the index compile. A false declaration can cause results/indexes to become inconsistent with current data.

### 13.5. The Index Expression Must Match the Query

An index on `UPPER(email)` does not automatically support any arbitrary expression such as `LOWER(TRIM(email))` or `NLSSORT(email,...)`. Check the expression in the index definition and the predicate in the plan. The optimizer can normalize some equivalent expressions, but you should not assume every expression is recognized identically.

## 14. Conversion and Partition Pruning

### 14.1. The Partition Key Must Use the Proper Data Type

If a table is partitioned by ORDER_DATE, a range predicate on the DATE column can enable partition pruning:

```sql
SELECT *
FROM partitioned_orders
WHERE order_date >= DATE '2026-11-01'
  AND order_date <  DATE '2026-12-01';
```

### 14.2. Functions/Conversions on the Partition Key

Predicate:

```sql
WHERE TO_CHAR(order_date, 'YYYY-MM') = '2026-11'
```

can make pruning harder because an expression wraps the partition key. Use the corresponding DATE range:

```sql
WHERE order_date >= DATE '2026-11-01'
  AND order_date <  DATE '2026-12-01'
```

### 14.3. Static and Dynamic Pruning

An execution plan may show specific `Pstart`/`Pstop` values or `KEY` for dynamic pruning. Bind variables, subqueries, or runtime expressions can cause pruning to be determined at execution time. Do not look only at `Pstart`/`Pstop` in `EXPLAIN PLAN` to draw conclusions; inspect the actual cursor plan and partition statistics.

### 14.4. Bind Conversion

If the partition key is DATE, binding DATE helps the optimizer understand the predicate directly. If binding text, Oracle may implicitly convert according to NLS or force a different expression. Parse text to DATE at the application boundary and then bind DATE.

### 14.5. Range Boundaries and Time

For `TIMESTAMP` or `TIMESTAMP WITH TIME ZONE` columns, build ranges with the matching data type. Watch out for time zones/daylight saving time if the range is a local calendar day. Do not use a DATE literal for a column with time-zone-aware instant semantics without defining conversion rules.

## 15. Conversion and Cardinality Estimates

### 15.1. The Optimizer Needs to Understand the Predicate

The CBO estimates the number of rows matching a predicate based on statistics, histograms, data types, and expressions. When a predicate wraps a function or implicit conversion, the optimizer may find it difficult to use the base column's statistics directly.

### 15.2. Histograms and Skew

If a column has a skewed distribution, a histogram can help estimate selectivity for specific values. However, conversion or an expression can prevent the base column's histogram from accurately describing the predicate expression.

### 15.3. Expression Statistics

For frequently used expressions, Oracle can gather statistics related to function-based indexes/virtual columns. Consider creating a virtual column or function-based index so the expression has clearer metadata/statistics.

### 15.4. Bind Peeking and Bind Sensitivity

A query with different bind values can have different selectivities. If bind data types are inconsistent or the NLS environment changes, in addition to conversion issues, there may also be multiple child cursors or different plans. Check the actual child cursor and bind metadata rather than assuming one plan is used for every request.

### 15.5. Do Not Use Hints to Mask Bad Conversions

An `INDEX` hint cannot fix conversion semantics, invalid data, or a non-sargable predicate. Fix the data type/bind/expression first, then evaluate access paths and statistics.

## 16. Reading Execution Plans to Find Implicit Conversion

### 16.1. Predicate Information

`DBMS_XPLAN` can show conversions in Predicate Information. For example, a predicate on VARCHAR2 converted to NUMBER may show an expression like:

```text
filter(TO_NUMBER("L"."ACCOUNT_CODE")=:B1)
```

This indicates a conversion is being applied to the ACCOUNT_CODE column. If there is a regular index on ACCOUNT_CODE, this predicate does not directly match the character key.

### 16.2. DISPLAY_CURSOR

After running the SQL, view the actual cursor:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +ALIAS +PEEKED_BINDS'
    )
);
```

`ALLSTATS LAST` is useful when runtime row-source statistics are gathered. `PEEKED_BINDS` can show bind values peeked during hard parse if available; it is not a complete record of every bind across every execution.

### 16.3. ACCESS and FILTER Predicates

In a plan:

- `ACCESS` predicates typically participate in determining the key/range for an access operation.
- `FILTER` predicates are evaluated to discard rows at the corresponding operation.

A predicate appearing in `FILTER` is not automatically bad. What to look for is which conversion/function is being applied, which operation handles it, and whether it increases the number of rows that must be read.

### 16.4. Index Range Scan Is Not an Absolute Goal

Even a sargable predicate can lead to `TABLE ACCESS FULL` if most of the table is selected, the table is small, or a full scan is cheaper. Evaluate:

- E-Rows and A-Rows.
- Buffers, physical reads, and elapsed time.
- Index clustering factor and selectivity.
- Predicate Information.
- Partition pruning.
- Bind values and child cursors.

Do not force an index merely because a query has an equality predicate.

### 16.5. EXPLAIN PLAN vs. Actual Cursor Plan

`EXPLAIN PLAN` shows an estimated plan in the explain context. It can differ from the runtime plan due to bind values, session settings, adaptive features, child cursors, or environment. Use `DISPLAY_CURSOR` to view the actual cursor executed by the application when investigating production issues.

## 17. Common Errors Caused by Conversion

| Error | Common Cause | Resolution |
| --- | --- | --- |
| ORA-01722: invalid number | Character value cannot be converted to NUMBER | Find bad data, validate in staging, fix data type/bind |
| ORA-01843: not a valid month | Date string does not match format/language | Use TO_DATE with explicit mask and NLS_DATE_LANGUAGE |
| ORA-01861: literal does not match format string | Input does not match format mask | Standardize producer and parser formats |
| ORA-01830: date format picture ends before converting entire input string | Format mask is shorter than input | Fix mask or input contract |
| ORA-06502: numeric or value error | Incompatible buffer/precision/conversion | Check data type, length, precision, and conversion |
| ORA-01481: invalid number format model | Invalid TO_CHAR/TO_NUMBER format model | Verify format model for the data type |
| ORA-00932: inconsistent datatypes | Expression mixes incompatible data types | Cast explicitly and unify branch data types |
| ORA-01426: numeric overflow | Conversion/arithmetic result exceeds NUMBER range | Check precision, scale, and input bounds |
| Index range scan disappears | Predicate wraps function/conversion around column | Convert on bind side, fix schema, or use FBI |
| Poor partition pruning | Function/conversion on partition key | Use properly typed range predicate |
| Different results across environments | Different NLS settings | Use explicit format/NLS parameters and proper bind types |

### 17.1. ORA-01722 Does Not Necessarily Point to the Failing Line

If a query has multiple predicates, the optimizer may change their evaluation order. Do not rely on writing a numeric-string check earlier in the `WHERE` clause to guarantee `TO_NUMBER` only runs on valid data.

Unsafe:

```sql
WHERE REGEXP_LIKE(code, '^[0-9]+$')
  AND TO_NUMBER(code) = :p_number
```

The optimizer does not guarantee evaluating `REGEXP_LIKE` before `TO_NUMBER`. Standardize the data beforehand, handle errors during staging conversion, or use `CASE` to control evaluation:

```sql
WHERE CASE
          WHEN VALIDATE_CONVERSION(code AS NUMBER) = 1
          THEN TO_NUMBER(code)
      END = :p_number
```

This is a safer way to express the conversion condition; it may still require a scan and does not replace schema cleanup.

### 17.2. Finding Unconvertible Data

```sql
SELECT code
FROM legacy_items
WHERE VALIDATE_CONVERSION(code AS NUMBER) = 0;
```

If your release does not support `VALIDATE_CONVERSION`, use a version-appropriate data check or handle it in ETL/application code. Do not run `TO_NUMBER` directly on every row just to find errors because the query itself may abort with ORA-01722.

## 18. Schema Design to Avoid Conversion

### 18.1. One Business Attribute, One Standard Data Type

If `account_id` is numeric, use NUMBER consistently across related tables. If `account_code` is an identifier, use VARCHAR2 consistently. Do not leave the same attribute as NUMBER in table A and VARCHAR2 in table B just because one older table ingested data from a text file.

### 18.2. Normalize Data at Ingress

At the data ingestion layer:

1. Validate input format.
2. Parse into the target data type.
3. Reject invalid values or store in staging for correction.
4. Bind typed values into DML.
5. Record raw input/hash if required for audit by policy.

Do not let every business query parse the same legacy column on the fly.

### 18.3. Separate Raw and Canonical Values

If you need to preserve the exact string sent by a user while also needing a normalized value for joins/searches, you can store two columns:

```sql
CREATE TABLE lab_external_ids (
    raw_id VARCHAR2(100),
    canonical_id VARCHAR2(100)
);
```

Canonicalization rules must be clear and stable. Do not normalize an ID to NUMBER if leading zeros or letters are meaningful.

### 18.4. Virtual Columns for Legacy Data

If the schema cannot be changed yet, a virtual column or a staging normalized column can provide a canonical data type for queries. Invalid values must be handled using `CASE`/`VALIDATE_CONVERSION` and the proper expression must be indexed.

### 18.5. Constraints and Data Quality

`NOT NULL`, `CHECK`, `FK`, and unique constraints provide metadata to the optimizer and protect data integrity. However, a `CHECK` constraint should not use a conversion that could fail on arbitrary rows; validate input before insertion and keep domain constraints simple.

### 18.6. Data Type Migration

When changing VARCHAR2 to NUMBER:

- Profile all data beforehand.
- Identify leading zeros, signs, whitespace, and formats.
- Handle duplicates after normalization.
- Create a new column or staging table to backfill.
- Validate row counts and values.
- Update application binds and joins.
- Create new indexes/constraints.
- Switch reads/writes with a rollback plan.

Do not `ALTER` a data type directly without knowing all data and dependencies.

## 19. Lab: Identifying Conversions That Prevent Index Access

These examples run in a lab schema. Use a separate schema; do not create or modify indexes on production tables.

### 19.1. Create Numeric Key Data

```sql
CREATE TABLE lab_conv_number (
    id NUMBER PRIMARY KEY,
    description VARCHAR2(100)
);

INSERT INTO lab_conv_number
SELECT level, 'Row ' || level
FROM dual
CONNECT BY level <= 10000;
COMMIT;

BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_CONV_NUMBER',
        cascade => TRUE
    );
END;
/
```

### 19.2. Compare Properly Typed Bind and Text Literal

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       *
FROM lab_conv_number
WHERE id = 500;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL, NULL, 'ALLSTATS LAST +PREDICATE'
    )
);
```

Try:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       *
FROM lab_conv_number
WHERE id = '500';
```

Observe Predicate Information. If Oracle converts the literal to NUMBER and keeps the ID column unmodified, the index can still be used.

### 19.3. Create Numeric Text Table

```sql
CREATE TABLE lab_conv_text (
    code VARCHAR2(20) PRIMARY KEY,
    description VARCHAR2(100)
);

INSERT INTO lab_conv_text
SELECT TO_CHAR(level, 'FM00000'), 'Code ' || level
FROM dual
CONNECT BY level <= 10000;

INSERT INTO lab_conv_text VALUES ('A100', 'Invalid numeric code');
COMMIT;

BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_CONV_TEXT',
        cascade => TRUE
    );
END;
/
```

### 19.4. Wrong-Type Predicate

```sql
SELECT *
FROM lab_conv_text
WHERE code = 100;
```

Oracle may attempt to convert CODE to NUMBER and encounter ORA-01722 due to row `A100`. Testing the query only on numeric data is not sufficient to prove the query is safe; the optimizer may read other rows depending on the plan.

### 19.5. Properly Typed Predicate

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       *
FROM lab_conv_text
WHERE code = '00100';
```

The predicate compares character to character and can use the primary key index. The result preserves leading-zero semantics.

### 19.6. Compare Function-Based Index

In the lab schema, if business requirements genuinely call for numeric interpretation:

```sql
CREATE INDEX ix_lab_conv_text_num
ON lab_conv_text (TO_NUMBER(code));
```

With data containing `A100`, creating the index expression may fail due to a conversion error. This illustrates why you should not patch a schema with a function-based index before cleaning the data. Do not continue using `TO_NUMBER` on the column until all values are verified valid.

## 20. Lab: NLS Date and Numeric Settings

### 20.1. Changing NLS_DATE_FORMAT in the Lab Session

```sql
ALTER SESSION SET NLS_DATE_FORMAT = 'DD-MM-YYYY';

SELECT TO_DATE('14-11-2026')
FROM dual;
```

Change the format:

```sql
ALTER SESSION SET NLS_DATE_FORMAT = 'MM/DD/YYYY';

SELECT TO_DATE('14-11-2026')
FROM dual;
```

The second conversion can fail because the input does not match. Try a DATE literal:

```sql
SELECT DATE '2026-11-14'
FROM dual;
```

The result does not depend on `NLS_DATE_FORMAT`.

### 20.2. Changing NLS_NUMERIC_CHARACTERS

```sql
ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,';
SELECT TO_NUMBER('1,234.56', '9G999D99')
FROM dual;

ALTER SESSION SET NLS_NUMERIC_CHARACTERS = ',.';
SELECT TO_NUMBER('1.234,56', '9G999D99')
FROM dual;
```

Observe how `D` and `G` are interpreted. When writing application code, specify the format model and NLS parameter explicitly rather than relying on `ALTER SESSION`.

### 20.3. Restoring the Session

In SQL Developer or SQL*Plus, close the lab session or reset the NLS settings to their original configuration. If using a connection pool, do not let session state changes leak to other requests.

## 21. Lab: Case-Insensitive Lookup and NLS_SORT

### 21.1. Create Data

```sql
CREATE TABLE lab_names (
    person_id NUMBER PRIMARY KEY,
    person_name VARCHAR2(100)
);

INSERT INTO lab_names VALUES (1, 'Smith');
INSERT INTO lab_names VALUES (2, 'SMITH');
INSERT INTO lab_names VALUES (3, 'smith');
INSERT INTO lab_names VALUES (4, 'Smyth');
COMMIT;

CREATE INDEX ix_lab_names_name
ON lab_names(person_name);

BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_NAMES',
        cascade => TRUE
    );
END;
/
```

### 21.2. Binary Equality

```sql
SELECT person_id, person_name
FROM lab_names
WHERE person_name = 'smith';
```

The result depends on the active binary/collation semantics. Do not assume all three capitalizations will match.

### 21.3. UPPER Expression

```sql
SELECT person_id, person_name
FROM lab_names
WHERE UPPER(person_name) = UPPER('smith');
```

The result can match `Smith`, `SMITH`, and `smith`. Check the plan with the regular index on PERSON_NAME; the `UPPER` expression may require a full scan if no matching index exists.

### 21.4. Function-Based Index

```sql
CREATE INDEX ix_lab_names_upper
ON lab_names(UPPER(person_name));

SELECT /*+ GATHER_PLAN_STATISTICS */
       person_id, person_name
FROM lab_names
WHERE UPPER(person_name) = UPPER(:p_name);
```

Check the actual plan and statistics. With a very small lab table, the optimizer may still choose a full scan due to cost; you can increase the test data size to observe the access path more clearly.

### 21.5. Using NLSSORT

Test the `NLSSORT` expression with a specific sort rule and compare the plan/results. Ensure the index expression and query expression match, and do not use NLS settings that change per request if the index is designed for a fixed rule.

## 22. Diagnosing Column and Bind Data Types

### 22.1. Inspect Column Data Types

```sql
SELECT
    column_name,
    data_type,
    data_length,
    char_length,
    char_used,
    data_precision,
    data_scale
FROM user_tab_columns
WHERE table_name = 'ORDERS'
ORDER BY column_id;
```

This information helps confirm whether a column is actually NUMBER, DATE, TIMESTAMP, VARCHAR2, or NCHAR/NVARCHAR2 and whether its length is in BYTE or CHAR.

### 22.2. Inspect Bind Data Types in a Cursor

Bind information can be viewed through dynamic performance views such as `V$SQL_BIND_CAPTURE`, if you have privileges. Bind capture does not record every bind on every execution and can be limited by sampling/cursor behavior.

```sql
SELECT
    sql_id,
    name,
    position,
    datatype_string,
    value_string,
    last_captured
FROM v$sql_bind_capture
WHERE sql_id = :p_sql_id
ORDER BY position;
```

Do not log sensitive bind values unmasked. In production data, access to `V$SQL_BIND_CAPTURE` must be controlled.

### 22.3. Finding SQL with Conversions in the Plan

DBAs can find cursor plans containing `TO_NUMBER`/`TO_DATE`/`TO_CHAR` expressions in Predicate Information by querying `V$SQL_PLAN` or reading `DBMS_XPLAN`. For example:

```sql
SELECT
    sql_id,
    child_number,
    operation,
    options,
    object_name,
    access_predicates,
    filter_predicates
FROM v$sql_plan
WHERE UPPER(access_predicates) LIKE '%TO_NUMBER%'
   OR UPPER(filter_predicates) LIKE '%TO_NUMBER%'
   OR UPPER(access_predicates) LIKE '%TO_DATE%'
   OR UPPER(filter_predicates) LIKE '%TO_DATE%';
```

This is a preliminary investigative query; expressions can be stored in other forms and the view can contain many cursors. Do not treat the output as an exhaustive list of every implicit conversion.

### 22.4. Checking NLS in the Application

Record session NLS metadata in diagnostics when environment-dependent errors occur. You do not necessarily need to log all NLS parameters on every request; you can log them when opening a connection or when a conversion error is detected. Ensure the connection pool resets state.

## 23. Common Errors and Resolutions

| Error/Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| ORA-01722: invalid number | Character value cannot be converted to NUMBER | Find bad data, validate in staging, fix data type/bind |
| ORA-01843: not a valid month | Date string does not match format/language | Use TO_DATE with explicit mask and NLS_DATE_LANGUAGE |
| ORA-01861: literal does not match format string | Input does not match format mask | Standardize producer and parser formats |
| ORA-01830 | Format mask is shorter than input | Fix mask or input contract |
| ORA-06502 | Incompatible buffer/precision/conversion | Check data type, length, precision, and conversion |
| ORA-01481 | Invalid TO_CHAR/TO_NUMBER format model | Verify format model for the data type |
| ORA-00932: inconsistent datatypes | Expression mixes incompatible data types | Cast explicitly and unify branch data types |
| ORA-01426: numeric overflow | Conversion/arithmetic result exceeds NUMBER range | Check precision, scale, and input bounds |
| Index range scan disappears | Predicate wraps function/conversion around column | Convert on bind side, fix schema, or use FBI |
| Poor partition pruning | Function/conversion on partition key | Use properly typed range predicate |
| Different results across environments | Different NLS settings | Use explicit format/NLS parameters and proper bind types |
| Many child cursors | Incompatible bind metadata or optimizer environment | Check V$SQL_SHARED_CURSOR and bind types |

### 23.1. ORA-01722 Does Not Necessarily Point to the Failing Line

If a query has multiple predicates, the optimizer may change their evaluation order. Do not rely on writing a numeric-string check earlier in the `WHERE` clause to guarantee `TO_NUMBER` only runs on valid data.

Unsafe:

```sql
WHERE REGEXP_LIKE(code, '^[0-9]+$')
  AND TO_NUMBER(code) = :p_number
```

The optimizer does not guarantee evaluating `REGEXP_LIKE` before `TO_NUMBER`. Standardize the data beforehand, handle errors during staging conversion, or use `CASE` to control evaluation:

```sql
WHERE CASE
          WHEN VALIDATE_CONVERSION(code AS NUMBER) = 1
          THEN TO_NUMBER(code)
      END = :p_number
```

This is a safer way to express the conversion condition; it may still require a scan and does not replace schema cleanup.

### 23.2. Finding Unconvertible Data

```sql
SELECT code
FROM legacy_items
WHERE VALIDATE_CONVERSION(code AS NUMBER) = 0;
```

If your release does not support `VALIDATE_CONVERSION`, use a version-appropriate data check or handle it in ETL/application code. Do not run `TO_NUMBER` directly on every row just to find errors because the query itself may abort with ORA-01722.

## 24. Best Practices

1. **Declare data types consistently.** The same business attribute should have the same type across related tables.
2. **Bind the right type.** Bind NUMBER as NUMBER, DATE as DATE, TIMESTAMP as TIMESTAMP, and text as character.
3. **Parse text at the boundary.** Use `TO_NUMBER`/`TO_DATE` with explicit format masks and NLS parameters.
4. **Avoid implicit date/number conversion.** Do not depend on `NLS_DATE_FORMAT` or `NLS_NUMERIC_CHARACTERS`.
5. **Keep columns unmodified in predicates when possible.** Convert the bind/literal instead of wrapping a function around an indexed column.
6. **Use range predicates for dates.** Avoid `TRUNC`/`TO_CHAR` on DATE columns when a range can express the condition.
7. **Keep identifiers as character.** Do not convert codes with leading zeros or letters into NUMBER.
8. **Check join keys.** Avoid joining NUMBER to VARCHAR2 with conversion on one side.
9. **Understand NLS_COMP/NLS_SORT.** Linguistic comparison may require `NLSSORT`/FBI or appropriate collation.
10. **Use function-based indexes selectively.** Only create them when the expression is a stable, beneficial workload.
11. **Clean legacy data.** Do not use conversions in every query to compensate for a column holding mixed value types.
12. **Check partition pruning.** Predicates must match the partition key's data type.
13. **Read Predicate Information.** Look for `TO_NUMBER`, `TO_DATE`, `TO_CHAR`, `CAST`, and expressions wrapping columns.
14. **Compare actual plans.** Inspect A-Rows, E-Rows, buffers, and runtime, not just `EXPLAIN PLAN`.
15. **Monitor session NLS.** Connection pools must manage session state consistently.
16. **Do not use hints to mask data type errors.** Fix semantics and expressions before forcing access paths.
17. **Test across multiple NLS profiles.** The same payload must produce the same result per the contract.
18. **Verify after upgrades.** Conversion, collation, and optimizer behavior can differ across releases.

## 25. Self-Check Questions

1. What is implicit conversion and why can it make SQL unpredictable?
2. When comparing a NUMBER column with a character literal, which side does Oracle usually convert?
3. Why can comparing a VARCHAR2 column with NUMBER produce `TO_NUMBER(column)`?
4. How does conversion on the bind side differ from conversion wrapping an indexed column?
5. What does sargability mean?
6. Why should a code like `000123` not be converted to NUMBER if leading zeros are meaningful?
7. How does `NLS_DATE_FORMAT` affect implicit date conversion?
8. How does a DATE literal differ from a `TO_DATE` string?
9. Why does equality with a DATE literal only match midnight?
10. What does `NLS_NUMERIC_CHARACTERS` specify?
11. What do `D` and `G` mean in a number format model?
12. Why should you bind NUMBER instead of binding text containing digits?
13. How do CHAR and VARCHAR2 differ regarding blank-padding?
14. How do NCHAR/NVARCHAR2 relate to the national character set?
15. How do BYTE and CHAR length semantics differ?
16. How do `NLS_SORT` and `NLS_COMP` affect comparisons?
17. Why might a regular index not be suitable for linguistic comparison?
18. How does a function-based index support `UPPER`/`LOWER`/`NLSSORT`?
19. Why can `TRUNC(date_column)` prevent an index range scan?
20. What range predicate should you write to filter an entire day?
21. How can implicit conversion affect partition pruning?
22. Why can conversions and expressions make cardinality estimates less accurate?
23. How does `DISPLAY_CURSOR` differ from `EXPLAIN PLAN`?
24. How does Predicate Information help identify conversions?
25. Why does putting `REGEXP_LIKE` before `TO_NUMBER` in `WHERE` not guarantee evaluation order?
26. When should you use `VALIDATE_CONVERSION`?
27. When should you fix the schema instead of creating a function-based index?
28. How can a connection pool leak NLS session state between requests?

## 26. Mental Model

```text
SQL PREDICATE
    |
    v
  DATATYPE COMPARISON
    |
    +-- NUMBER vs CHARACTER
    +-- DATE/TIMESTAMP vs CHARACTER
    +-- CHAR/VARCHAR2/NCHAR
    +-- BINARY vs LINGUISTIC COLLATION
    |
    v
  IMPLICIT CONVERSION
    |
    +-- Depends on NLS
    +-- Can fail on data
    +-- Can wrap function around column
    |
    v
  INDEX / PARTITION ACCESS
    |
    +-- Unmodified column + properly typed bind
    |      -> access path usually available
    |
    +-- TO_NUMBER(column), TRUNC(column), UPPER(column)
           -> regular index may not match expression
           -> consider range rewrite / FBI / virtual column
    |
    v
  DIAGNOSTICS
    |
    +-- NLS_SESSION_PARAMETERS
    +-- USER_TAB_COLUMNS / bind metadata
    +-- DBMS_XPLAN Predicate Information
    +-- A-Rows / E-Rows / Starts / buffers
```

**Key takeaway:** implicit conversion can change semantics, depend on NLS, and make predicates non-sargable. Keep data types consistent, bind the proper types, parse text using explicit formats/NLS, keep indexed columns unmodified when possible, and confirm with the actual execution plan.
