# Data Type Compatibility Across Set Operation Branches in Oracle

## 1. Why must UNION branches have compatible data types?

A report may need to merge customers from two systems, combine current transactions with historical data, or compute the intersection or difference between two lists of codes. In Oracle SQL, set operators such as `UNION`, `UNION ALL`, `INTERSECT`, and `MINUS` combine the results of multiple `SELECT` statements into a single result set.

Simple example:

```sql
SELECT employee_id
FROM current_employees
UNION ALL
SELECT employee_id
FROM former_employees;
```

Both SELECT statements have the same single output column, and both columns carry compatible data types. However, if one branch returns `NUMBER` and the other returns `VARCHAR2`, Oracle will not implicitly convert across data type groups merely because a string looks numeric:

```sql
-- May raise ORA-01790:
SELECT 100 AS item_id FROM dual
UNION ALL
SELECT '200' AS item_id FROM dual;
```

`100` is a numeric literal, whereas `'200'` is a character literal. When combining with a set operator, expressions in the same positional slot must be compatible under Oracle's data type rules.

This lesson belongs to the **Aggregation and Set Operations** chapter and focuses on:

- Column count and positional ordering rules across branches.
- Oracle's datatype group rules.
- Numeric conversion according to numeric precedence.
- Standardizing `CHAR`, `VARCHAR2`, `NCHAR`, and `NVARCHAR2`.
- Handling `DATE`, `TIMESTAMP`, `NULL`, and literals.
- Using `CAST` and conversion functions to unify output types.
- Recognizing common errors such as `ORA-01789` and `ORA-01790`.

The goal is not merely making the SQL run, but ensuring **the resulting data type accurately reflects data semantics** and does not lose information when merging.

## 2. Set operators and structural requirements

Oracle supports these common set operators:

| Operator | Meaning |
|---|---|
| `UNION` | Combines two result sets and removes duplicate rows |
| `UNION ALL` | Combines two result sets, keeping duplicate rows |
| `INTERSECT` | Returns rows appearing in both sets |
| `MINUS` | Returns rows in the left set that are not in the right set |

These operators share a common requirement: every branch must return the same number of columns, and corresponding columns must have compatible types.

### 2.1. Column counts must match

```sql
-- Both branches have one column:
SELECT employee_id
FROM current_employees
UNION
SELECT employee_id
FROM former_employees;
```

Invalid example:

```sql
-- First branch has 2 columns, second branch has only 1:
SELECT employee_id, employee_name
FROM current_employees
UNION
SELECT employee_id
FROM former_employees;
```

Oracle raises an error:

```text
ORA-01789: query block has incorrect number of result columns
```

If the business requires two columns, add a corresponding expression in the branch missing it, potentially using NULL cast to the appropriate type:

```sql
SELECT employee_id, employee_name
FROM current_employees
UNION ALL
SELECT employee_id, CAST(NULL AS VARCHAR2(100)) AS employee_name
FROM former_employees;
```

Do not insert an arbitrary placeholder value like `'N/A'` if NULL properly represents "no name in this source."

### 2.2. Column order must align semantically

Set operators match columns by **position**, not by alias name:

```sql
SELECT employee_id, employee_name
FROM current_employees
UNION ALL
SELECT department_id, department_name
FROM departments;
```

The SQL may be valid in column count and type, yet the output is meaningless if the first column in the first branch is employee ID while the first column in the second branch is department ID. Aliases from the first branch normally determine output column names; aliases in subsequent branches do not make Oracle reorder columns automatically.

Before writing `UNION`, define the output contract:

| Position | Unified meaning | Branch A | Branch B |
|---:|---|---|---|
| 1 | Entity ID | `customer_id` | `legacy_customer_id` |
| 2 | Display name | `customer_name` | `old_name` |
| 3 | Creation date | `created_at` | `imported_at` |
| 4 | Data source | literal `'CURRENT'` | literal `'LEGACY'` |

Each branch must place expressions in matching positions and standardize to compatible types.

## 3. Oracle's datatype group rules

For set operators, Oracle checks the data types of corresponding expressions. Types within the same group can be converted according to Oracle rules, but **never assume Oracle implicitly converts across different datatype groups**.

Typical example:

```sql
-- NUMBER and VARCHAR2 belong to different datatype groups:
SELECT 1 AS value FROM dual
UNION ALL
SELECT '1' AS value FROM dual;
```

The query raises:

```text
ORA-01790: expression must have same datatype as corresponding expression
```

Even though `'1'` might convert to NUMBER in an arithmetic operation or another comparison, that **does not mean** Oracle will implicitly convert a set operator's branch.

### 3.1. Numeric group

Numeric types such as `NUMBER`, `BINARY_FLOAT`, and `BINARY_DOUBLE` belong to the numeric group. Oracle applies numeric precedence rules when branches have differing numeric types.

### 3.2. Character group

Character types such as `CHAR`, `VARCHAR2`, `NCHAR`, and `NVARCHAR2` have specific character compatibility rules. Oracle can convert among compatible character types, though you must watch differences between database character set and national character set, lengths, and output type.

### 3.3. Datetime group

`DATE` and `TIMESTAMP` represent date/time data with different precision. When merging time columns, pick a unified output type. For instance, if fractional seconds must be preserved, standardize branches to `TIMESTAMP`; converting down to `DATE` drops fractional seconds.

For `TIMESTAMP WITH TIME ZONE` and `TIMESTAMP WITH LOCAL TIME ZONE`, clarify the time zone semantics to preserve. Never force them to timezone-less `TIMESTAMP` just to silence a type error if the business needs offset/region information.

### 3.4. Do not rely on implicit cross-group conversion

The following examples show cases requiring explicit standardization:

| Left branch | Right branch | Issue |
|---|---|---|
| `NUMBER` | `VARCHAR2` | Numeric and character |
| `DATE` | `VARCHAR2` | Datetime and character |
| `TIMESTAMP` | `NUMBER` | Datetime and numeric |
| `NUMBER` | `DATE` | Numeric and datetime |

Convert intentionally before combining, rather than waiting for Oracle to guess.

## 4. Numeric group: numeric precedence and result type

Oracle defines a precedence order among common numeric types:

```text
BINARY_DOUBLE
      >
BINARY_FLOAT
      >
NUMBER
```

When corresponding expressions are in the numeric group with different types, Oracle converts expressions to the type with higher precedence according to set-operator rules.

Illustrative example:

```sql
SELECT CAST(10 AS NUMBER) AS numeric_value
FROM dual
UNION ALL
SELECT CAST(20 AS BINARY_DOUBLE) AS numeric_value
FROM dual;
```

The resulting numeric type is determined by numeric precedence; in this example `BINARY_DOUBLE` takes precedence over `NUMBER`.

### 4.1. Why care about BINARY_FLOAT/BINARY_DOUBLE?

`NUMBER` is Oracle's decimal numeric type, suited for business data requiring decimal exactness such as currency. `BINARY_FLOAT` and `BINARY_DOUBLE` are binary floating-point types. When one branch introduces a binary floating-point type into a set operation, the overall result type can become binary floating-point.

This can affect:

- Decimal representation precision.
- Display formatting and rounding.
- How JDBC applications receive values.
- Subsequent calculations on the merged result.

If the business requires `NUMBER(12,2)`, standardize **every branch** to this type instead of letting a single `BINARY_DOUBLE` branch alter the output type:

```sql
SELECT CAST(current_amount AS NUMBER(12, 2)) AS amount
FROM current_orders
UNION ALL
SELECT CAST(legacy_amount AS NUMBER(12, 2)) AS amount
FROM legacy_orders;
```

Use precision/scale suited to business bounds. `CAST` may round or raise an error when values exceed bounds; never pick a target type smaller than real data.

### 4.2. Numeric strings must be parsed to numbers, not merely look like numbers

Wrong:

```sql
SELECT 100 AS amount FROM dual
UNION ALL
SELECT '200' AS amount FROM dual;
```

Right if `'200'` is genuinely numeric data:

```sql
SELECT CAST(100 AS NUMBER(12, 2)) AS amount
FROM dual
UNION ALL
SELECT TO_NUMBER('200', '999') AS amount
FROM dual;
```

If strings contain locale-specific decimal/grouping separators, specify a format model and NLS parameter:

```sql
SELECT CAST(100 AS NUMBER(12, 2)) AS amount
FROM dual
UNION ALL
SELECT TO_NUMBER(
           '1.234,56',
           '9G999D99',
           'NLS_NUMERIC_CHARACTERS='',.'''
       ) AS amount
FROM dual;
```

The second branch evaluates to numeric 1234.56. If source strings contain malformed values, `TO_NUMBER` will raise an error; do not mask data errors by converting everything to text just so the set operation runs.

## 5. Character group: CHAR, VARCHAR2, and national types

Character types can differ in fixed/variable length, padding, character set, and BYTE/CHAR semantics. Therefore, when merging sources, standardize the output type.

### 5.1. CHAR and VARCHAR2

Example:

```sql
SELECT CAST('A' AS CHAR(5)) AS item_code
FROM dual
UNION ALL
SELECT CAST('B' AS VARCHAR2(20)) AS item_code
FROM dual;
```

In typical character cases, Oracle determines the character result type by expression rules: `CHAR` of equal lengths may yield `CHAR`; if `CHAR` lengths differ or `VARCHAR2` is present, the result is typically `VARCHAR2` with an appropriate length. Do not rely on `CHAR` blank-padding to preserve identifiers; if codes have leading zeros or meaningful spaces, define the type and normalization rules explicitly.

Example standardizing to `VARCHAR2(20)`:

```sql
SELECT CAST(current_code AS VARCHAR2(20)) AS item_code
FROM current_items
UNION ALL
SELECT CAST(legacy_code AS VARCHAR2(20)) AS item_code
FROM legacy_items;
```

### 5.2. NCHAR and NVARCHAR2

`NCHAR` and `NVARCHAR2` use the national character set. If one branch returns a national type and the other returns a regular character type, clarify the desired output type and use `CAST`/appropriate conversions. Do not assume all character types can be mixed without affecting character sets or output metadata.

For example, if the output contract is `NVARCHAR2`:

```sql
SELECT CAST(current_name AS NVARCHAR2(100)) AS display_name
FROM current_customers
UNION ALL
SELECT CAST(legacy_name AS NVARCHAR2(100)) AS display_name
FROM legacy_customers;
```

If the output contract is `VARCHAR2` on an `AL32UTF8` database, standardizing both branches to `VARCHAR2` may be preferable. Base the decision on schema, character sets, and consuming applications.

### 5.3. Do not convert identifiers to NUMBER if leading zeros must be preserved

Two values:

```text
'00125'
'125'
```

may be two distinct codes, even though parsing them to NUMBER yields 125 for both. When merging product codes, postal codes, or customer codes, the right type is usually character:

```sql
SELECT CAST(current_code AS VARCHAR2(30)) AS code
FROM current_products
UNION ALL
SELECT CAST(legacy_code AS VARCHAR2(30)) AS code
FROM legacy_products;
```

Only convert to NUMBER when the field truly represents a numeric quantity and leading zeros carry no meaning.

## 6. DATE and TIMESTAMP: unifying time precision

### 6.1. Merging DATE and TIMESTAMP

An older source has `DATE`, while a newer source has `TIMESTAMP`:

```sql
SELECT CAST(old_event_date AS TIMESTAMP) AS event_time
FROM old_events
UNION ALL
SELECT new_event_timestamp AS event_time
FROM new_events;
```

Promoting `DATE` to `TIMESTAMP` keeps date/time to the second and fills fractional seconds with 0. If fractional seconds from the new source must be preserved, do not downcast both branches to `DATE`.

### 6.2. When a DATE result is desired

If the output contract only requires precision to the second:

```sql
SELECT CAST(new_event_timestamp AS DATE) AS event_time
FROM new_events
UNION ALL
SELECT old_event_date AS event_time
FROM old_events;
```

This is an intentional decision: fractional seconds from `TIMESTAMP` are truncated when converting to `DATE`.

### 6.3. Do not parse dates with NLS-dependent strings

Avoid:

```sql
SELECT '14/11/2026' AS event_date FROM dual
UNION ALL
SELECT DATE '2026-11-15' AS event_date FROM dual;
```

One branch is character and the other is DATE. Parse the string into a date:

```sql
SELECT TO_DATE('14/11/2026', 'FXDD/MM/YYYY') AS event_date
FROM dual
UNION ALL
SELECT DATE '2026-11-15' AS event_date
FROM dual;
```

Or standardize both to TIMESTAMP if the output contract requires it.

### 6.4. Time zone is part of data semantics

Do not strip time zones just to force two branches to match:

```sql
-- Think carefully before dropping the offset:
CAST(event_time_tz AS TIMESTAMP)
```

If one source has `TIMESTAMP WITH TIME ZONE` and the other is timezone-less `TIMESTAMP`, determine the time zone of the naive branch first. A value like `2026-11-14 16:30:00` does not by itself tell you whether it is UTC or Vietnam time.

If the output must preserve time zone info, standardize both branches to `TIMESTAMP WITH TIME ZONE` using a specific rule. If only UTC instants are needed, convert explicitly to UTC before merging. Never slap `+00:00` onto local data whose time zone is unverified.

## 7. NULL in set branches: CAST to define the type

A branch may lack data for a column. Using NULL is appropriate, but you should specify its type:

```sql
SELECT customer_id,
       customer_name,
       credit_limit
FROM current_customers
UNION ALL
SELECT legacy_id,
       legacy_name,
       CAST(NULL AS NUMBER(12, 2)) AS credit_limit
FROM legacy_customers;
```

`CAST(NULL AS NUMBER(12,2))` gives the third-position expression an explicit NUMBER type.

### 7.1. Untyped NULLs in expressions

Examples:

```sql
SELECT CAST(NULL AS DATE) AS closed_at
FROM dual
UNION ALL
SELECT DATE '2026-11-14' AS closed_at
FROM dual;
```

This is a clean way to write a date column that may lack values. For numeric types:

```sql
SELECT CAST(NULL AS NUMBER(12, 2)) AS amount
FROM dual
UNION ALL
SELECT CAST(125.50 AS NUMBER(12, 2)) AS amount
FROM dual;
```

For character types:

```sql
SELECT CAST(NULL AS VARCHAR2(100)) AS note
FROM dual
UNION ALL
SELECT CAST('Imported' AS VARCHAR2(100)) AS note
FROM dual;
```

### 7.2. Do not substitute a dummy value for NULL

If a historical source lacks `created_at`, `CAST(NULL AS DATE)` accurately expresses "no creation date in this source." Using `DATE '1900-01-01'` as a dummy value can cause reports to treat it as a real date, skewing filters, statistics, and business logic.

If an application wants to display `N/A`, replace it at the presentation layer or intentionally with `CASE`/`TO_CHAR`; do not erase the NULL semantics of data just to merge branches.

## 8. CAST in each branch: output standardization pattern

A maintainable approach is defining the column contract first, then casting every branch to the same types:

```sql
SELECT
    CAST(current_id AS NUMBER(12)) AS entity_id,
    CAST(current_name AS VARCHAR2(100)) AS entity_name,
    CAST(current_created_at AS TIMESTAMP(6)) AS created_at,
    CAST('CURRENT' AS VARCHAR2(10)) AS source_name
FROM current_entities

UNION ALL

SELECT
    CAST(legacy_id AS NUMBER(12)) AS entity_id,
    CAST(legacy_name AS VARCHAR2(100)) AS entity_name,
    CAST(legacy_created_at AS TIMESTAMP(6)) AS created_at,
    CAST('LEGACY' AS VARCHAR2(10)) AS source_name
FROM legacy_entities;
```

This SQL assumes source data converts cleanly. If `legacy_id` is a string containing non-numeric characters, `CAST(... AS NUMBER)` will fail; use `TO_NUMBER` with an appropriate format and handle bad rows during staging/validation.

### 8.1. Standardizing numeric strings

```sql
SELECT CAST(current_amount AS NUMBER(12, 2)) AS amount
FROM current_payments
UNION ALL
SELECT TO_NUMBER(
           legacy_amount_text,
           'FM999G999G999D99',
           'NLS_NUMERIC_CHARACTERS='',.'''
       ) AS amount
FROM legacy_payments;
```

In this example, the legacy string is parsed under a specific convention. If `legacy_amount_text` contains invalid values, the query will fail; type standardization does not cleanse bad data on its own.

### 8.2. Standardizing character codes

```sql
SELECT CAST(current_product_code AS VARCHAR2(30 CHAR)) AS product_code
FROM current_products
UNION ALL
SELECT CAST(legacy_product_code AS VARCHAR2(30 CHAR)) AS product_code
FROM legacy_products;
```

If one source is typed `NUMBER`, determine whether the code is truly numeric. Converting to `VARCHAR2` may lose original formatting if leading zeros were already stripped when stored as a number. Standardize according to the code contract, not syntax alone.

## 9. What role do format models play in set operators?

Format models are not directly type-compatibility rules. They are used when converting between **text** and **numeric/datetime values**.

Example where both branches return the same DATE type:

```sql
SELECT TO_DATE('14/11/2026', 'FXDD/MM/YYYY') AS event_date
FROM dual
UNION ALL
SELECT DATE '2026-11-15' AS event_date
FROM dual;
```

The format model `DD/MM/YYYY` parses the first string into a DATE; after conversion, both branches return DATE.

Conversely, if a text result is needed:

```sql
SELECT TO_CHAR(DATE '2026-11-14', 'YYYY-MM-DD') AS event_date_text
FROM dual
UNION ALL
SELECT CAST('2026-11-15' AS VARCHAR2(10)) AS event_date_text
FROM dual;
```

Both branches return character types. However, the output is now **text**, no longer a DATE suitable for date comparisons, date arithmetic, or direct datetime functions.

### 9.1. Choosing output types by consumption needs

| Need | Suitable output type |
|---|---|
| Sorting/filtering/computing intervals | `DATE` or `TIMESTAMP` |
| Monetary and quantity arithmetic | `NUMBER` with proper precision/scale |
| Preserving codes with leading zeros | `VARCHAR2` or suitable character type |
| Displaying dates as `DD/MM/YYYY` | Can use `TO_CHAR` at the reporting layer |
| Sending timestamps with offsets | Timezone-aware type and explicit UTC/region convention |
| Column lacking data in one branch | `CAST(NULL AS target_type)` |

Do not format every column to strings before `UNION` just to avoid `ORA-01790`. That loses native types and makes downstream operations harder to keep accurate.

## 10. Special data types and set operator limitations

Not every Oracle type can participate in set operators in the standard way.

### 10.1. LOB and collection types

Oracle imposes restrictions on types such as:

- `BLOB`
- `CLOB`
- `BFILE`
- Collection types such as `VARRAY` and nested tables

These types are not directly supported in many SQL set operations. `LONG` is also a legacy type with heavy restrictions when used with operators like `UNION`, `INTERSECT`, and `MINUS`.

When merging record lists that include LOBs, it is usually best to combine **primary keys or metadata columns** first, then fetch LOBs by key:

```sql
SELECT document_id, source_name
FROM current_documents
UNION ALL
SELECT document_id, source_name
FROM archived_documents;
```

Once you have the ID list, the application or a follow-up query can read LOB contents from each source. This avoids asking the set operator to compare LOB contents directly.

### 10.2. Object types and user-defined types

User-defined object types and collections have their own compatibility rules; do not assume they behave like `NUMBER`/`VARCHAR2`. If a query returns object types, verify operator and Oracle version support; in many designs, it is better to project scalar attributes and combine those.

### 10.3. Check version and data type documentation

Some conversion capabilities and data type rules vary by Oracle version. When working with LOBs, JSON, spatial, object types, or extended types, consult the SQL Language Reference for your exact running version. Never force every special type into `VARCHAR2` if doing so truncates data, hits length limits, or incurs heavy conversion overhead.

## 11. Do UNION, UNION ALL, INTERSECT, and MINUS differ in type rules?

Regarding data type compatibility, all set operators follow the same principle: corresponding column counts must match and types must be compatible. Their primary difference lies in how rows are combined:

| Operator | Duplicate handling | Type compatibility required |
|---|---|---|
| `UNION` | Eliminates duplicate rows in output | Yes |
| `UNION ALL` | Keeps duplicate rows | Yes |
| `INTERSECT` | Returns rows common to both sets | Yes |
| `MINUS` | Returns rows only in the left branch | Yes |

`UNION ALL` is not a workaround to bypass type errors. Example:

```sql
-- Still incompatible even with UNION ALL:
SELECT 10 FROM dual
UNION ALL
SELECT '20' FROM dual;
```

Likewise, `INTERSECT` and `MINUS` do not implicitly convert `VARCHAR2` to `NUMBER` for comparisons.

### 11.1. Duplicate behavior does not change the column contract

```sql
SELECT CAST(10 AS NUMBER) AS value FROM dual
UNION
SELECT CAST(10 AS NUMBER) AS value FROM dual;
```

The result has one row.

```sql
SELECT CAST(10 AS NUMBER) AS value FROM dual
UNION ALL
SELECT CAST(10 AS NUMBER) AS value FROM dual;
```

The result has two rows. Both statements still require compatible NUMBER types in the first column position.

## 12. ORDER BY and aliases in set queries

The `ORDER BY` of a compound query is normally placed **once at the end** of the entire expression:

```sql
SELECT employee_id AS id
FROM current_employees
UNION ALL
SELECT employee_id
FROM former_employees
ORDER BY id;
```

Output column names come from the first SELECT branch. Aliases in later branches do not redefine output column names:

```sql
SELECT employee_id AS entity_id
FROM current_employees
UNION ALL
SELECT employee_id AS old_id
FROM former_employees
ORDER BY entity_id;
```

Do not place `ORDER BY` arbitrarily between branches:

```sql
-- Do not write ORDER BY between branches in a standard compound query:
-- SELECT ... FROM current_employees ORDER BY employee_id
-- UNION ALL
-- SELECT ... FROM former_employees;
```

If individual sorting is needed before another operation, design a subquery/inline view appropriately. Sorting inside a branch does not substitute for sorting the final output.

## 13. Common errors

| Error | Cause | Resolution |
|---|---|---|
| `ORA-01789: query block has incorrect number of result columns` | SELECT branches have different column counts | Add/remove columns so all branches have equal counts |
| `ORA-01790: expression must have same datatype as corresponding expression` | Positional column types are incompatible | Choose a target type and CAST/parse explicitly |
| `ORA-00932: inconsistent datatypes` | Expressions have incompatible types in conversion context | Check each expression's type and standardize outputs |
| `ORA-01722: invalid number` | Source string cannot be parsed as a number | Validate data and format/NLS before `TO_NUMBER` |
| `ORA-01861` or ORA-018xx errors | Datetime string does not match format or is invalid | Use `TO_DATE`/`TO_TIMESTAMP` with the exact format |
| Code output loses leading zeros | Code was converted to NUMBER | Keep codes as character type |
| Timestamp loses fractional seconds | Cast TIMESTAMP down to DATE | Standardize to TIMESTAMP if precision is needed |
| Timestamps shifted by time zone | Dropped time zone or misinterpreted naive timestamp | Clarify time zone and standardize explicitly |
| Numeric output type changed | One branch used BINARY_FLOAT/BINARY_DOUBLE | CAST branches to NUMBER if required by business |
| NULL has unclear or wrong type | Bare NULL used in combined expression | `CAST(NULL AS target_type)` |
| UNION runs, but data is semantically wrong | Positional columns do not share meaning | Define a positional column contract before writing SQL |

### Workflow for resolving ORA-01790

When encountering `ORA-01790`, check in order:

1. Count the expressions in each branch's SELECT list.
2. Match column 1 against column 1, column 2 against column 2, and so on.
3. Inspect the actual expression data type, not just the base table column type.
4. Determine the datatype group and desired output type.
5. Add `CAST` or parsing functions in each branch.
6. Check risks of losing precision, leading zeros, fractional seconds, or time zones.
7. Verify whether all source values convert cleanly.

Do not fix the error by casting everything to `VARCHAR2` before deciding how the output will be used.

## 14. Inspecting data types from the data dictionary

When unsure of source column types, inspect metadata rather than guessing from displayed values.

### 14.1. Viewing column types in the current schema

```sql
SELECT table_name,
       column_name,
       data_type,
       data_length,
       data_precision,
       data_scale,
       char_length,
       char_used
FROM user_tab_columns
WHERE table_name IN ('CURRENT_ORDERS', 'LEGACY_ORDERS')
ORDER BY table_name, column_id;
```

Useful metadata columns:

| Column | Meaning |
|---|---|
| `DATA_TYPE` | Data type name |
| `DATA_LENGTH` | Length in bytes |
| `DATA_PRECISION` | Numeric precision where applicable |
| `DATA_SCALE` | Numeric scale where applicable |
| `CHAR_LENGTH` | Character length for character types |
| `CHAR_USED` | BYTE (`B`) or CHAR (`C`) semantics where applicable |

If tables belong to another schema and you have visibility privileges, use `ALL_TAB_COLUMNS` and filter on `OWNER`. For broader administrative visibility, `DBA_TAB_COLUMNS` can be used if appropriate privileges are granted.

### 14.2. Checking expression types after conversion

An expression's type can differ from its source column type:

```sql
SELECT CAST(amount_text AS NUMBER(12, 2)) AS amount
FROM import_rows;
```

The result has type NUMBER even though the base column is VARCHAR2. When checking a set operator, examine **the type of the expression in the SELECT list**, not just the source column metadata.

### 14.3. Checking query output types via client tools

SQL Developer, SQLcl, or JDBC metadata can reveal output column data types. When a query uses `UNION`, check the actual output types after Oracle resolves numeric precedence or character result types—especially if `BINARY_DOUBLE`, differing `CHAR` lengths, or national types are involved.

## 15. Designing real-world merge queries

### 15.1. Merging customers from new and legacy systems

Suppose:

- `CURRENT_CUSTOMERS.customer_id` is NUMBER.
- `LEGACY_CUSTOMERS.customer_code` is VARCHAR2, containing only valid numeric codes.
- Both sources have customer names of different lengths.
- The legacy source has no `created_at`.

You can standardize as follows:

```sql
SELECT
    CAST(customer_id AS NUMBER(12)) AS customer_id,
    CAST(customer_name AS VARCHAR2(100)) AS customer_name,
    CAST(created_at AS TIMESTAMP(6)) AS created_at,
    CAST('CURRENT' AS VARCHAR2(10)) AS source_name
FROM current_customers

UNION ALL

SELECT
    TO_NUMBER(customer_code, '999999999999') AS customer_id,
    CAST(legacy_name AS VARCHAR2(100)) AS customer_name,
    CAST(NULL AS TIMESTAMP(6)) AS created_at,
    CAST('LEGACY' AS VARCHAR2(10)) AS source_name
FROM legacy_customers;
```

This example assumes `customer_code` holds valid formatted numbers. If codes have meaningful leading zeros, keep the `customer_id` output as VARCHAR2 instead of TO_NUMBER. If source `created_at` is DATE, casting up to TIMESTAMP preserves seconds and pads fractional seconds with 0.

### 15.2. Merging monetary amounts

```sql
SELECT
    CAST(payment_id AS NUMBER(12)) AS payment_id,
    CAST(amount AS NUMBER(14, 2)) AS amount
FROM current_payments

UNION ALL

SELECT
    CAST(old_payment_id AS NUMBER(12)) AS payment_id,
    TO_NUMBER(
        amount_text,
        'FM9G999G999D99',
        'NLS_NUMERIC_CHARACTERS='',.'''
    ) AS amount
FROM legacy_payments;
```

Here the `amount` output column is numeric, suitable for addition/aggregation. If legacy data fails to parse, cleanse/log bad records during import rather than converting `amount` to text to dodge errors.

### 15.3. Merging events from multiple time zones

If both sources already store `TIMESTAMP WITH TIME ZONE`, preserve that type when combining:

```sql
SELECT event_id,
       event_time_tz
FROM region_a_events
UNION ALL
SELECT event_id,
       event_time_tz
FROM region_b_events;
```

If one source is timezone-less `TIMESTAMP`, determine its true time zone and convert properly before merging. No `CAST` can invent a time zone that the data does not provide.

## 16. Comprehensive hands-on lab

The following examples use self-created test tables. Run them in a practice schema with `CREATE TABLE` privileges; do not use production tables. Some statements are marked as intentional error cases for you to uncomment and observe individually.

### Step 1. Trigger a column-count mismatch error

```sql
-- Intentionally wrong: two branches return different column counts.
-- SELECT 1 AS id, 'A' AS code FROM dual
-- UNION ALL
-- SELECT 2 AS id FROM dual;
```

Oracle raises `ORA-01789`.

### Step 2. Trigger a datatype-group mismatch error

```sql
-- Intentionally wrong: NUMBER and VARCHAR2 in the same position.
-- SELECT 1 AS value FROM dual
-- UNION ALL
-- SELECT '2' AS value FROM dual;
```

Oracle raises `ORA-01790`.

### Step 3. Standardize to NUMBER

```sql
SELECT CAST(1 AS NUMBER(10, 2)) AS value
FROM dual
UNION ALL
SELECT CAST(2 AS NUMBER(10, 2)) AS value
FROM dual;
```

Both branches return the same NUMBER(10,2) type.

### Step 4. Parse text to DATE

```sql
SELECT TO_DATE('14/11/2026', 'FXDD/MM/YYYY') AS event_date
FROM dual
UNION ALL
SELECT DATE '2026-11-15' AS event_date
FROM dual;
```

Both branches return DATE.

### Step 5. Use typed NULL

```sql
SELECT CAST(100 AS NUMBER(12, 2)) AS amount
FROM dual
UNION ALL
SELECT CAST(NULL AS NUMBER(12, 2)) AS amount
FROM dual;
```

The output has one number and one NULL, both typed NUMBER.

### Step 6. Observe numeric precedence

```sql
SELECT CAST(10 AS NUMBER) AS value
FROM dual
UNION ALL
SELECT CAST(20 AS BINARY_DOUBLE) AS value
FROM dual;
```

Inspect the result type using a SQL client tool or JDBC metadata; the numeric type with higher precedence is used for the merged result.

### Step 7. Create tables for two sources

```sql
CREATE TABLE demo_current_source (
    item_id NUMBER,
    item_name VARCHAR2(50),
    amount NUMBER(12, 2),
    created_at DATE
);

CREATE TABLE demo_legacy_source (
    item_code VARCHAR2(20),
    item_name CHAR(30),
    amount_text VARCHAR2(30),
    created_text VARCHAR2(20)
);
```

### Step 8. Insert sample data

```sql
INSERT INTO demo_current_source
VALUES (101, 'Current A', 1250.50, DATE '2026-11-14');

INSERT INTO demo_current_source
VALUES (102, 'Current B', 300.00, DATE '2026-11-15');

INSERT INTO demo_legacy_source
VALUES ('201', 'Legacy A', '1.234,56', '14/11/2026');

INSERT INTO demo_legacy_source
VALUES ('202', 'Legacy B', '450,00', '15/11/2026');

COMMIT;
```

### Step 9. Merge with unified types

```sql
SELECT
    CAST(item_id AS NUMBER(12)) AS item_id,
    CAST(item_name AS VARCHAR2(50)) AS item_name,
    CAST(amount AS NUMBER(12, 2)) AS amount,
    CAST(created_at AS TIMESTAMP(6)) AS created_at,
    CAST('CURRENT' AS VARCHAR2(10)) AS source_name
FROM demo_current_source

UNION ALL

SELECT
    TO_NUMBER(item_code, '999999999999') AS item_id,
    CAST(item_name AS VARCHAR2(50)) AS item_name,
    TO_NUMBER(
        amount_text,
        'FM9G999G999D99',
        'NLS_NUMERIC_CHARACTERS='',.'''
    ) AS amount,
    CAST(
        TO_DATE(created_text, 'FXDD/MM/YYYY')
        AS TIMESTAMP(6)
    ) AS created_at,
    CAST('LEGACY' AS VARCHAR2(10)) AS source_name
FROM demo_legacy_source;
```

The output has the same five columns in the same order with standardized types. If legacy codes are identifiers with meaningful leading zeros, change the `item_id` output design to a character type in both branches.

### Step 10. Clean up the test tables

Only after confirming these are the exact tables just created and no data needs to be kept:

```sql
DROP TABLE demo_legacy_source PURGE;
DROP TABLE demo_current_source PURGE;
```

`DROP TABLE ... PURGE` removes the table and data, bypassing the recycle bin per statement behavior; DDL performs an implicit commit. Do not run on business objects or shared tables.

## 17. Key principles to remember

1. **Equal column counts:** every SELECT branch must return the same number of expressions.
2. **Same position, same meaning:** the nth column of each branch must represent the same logical attribute.
3. **Datatype group compatibility:** do not rely on implicit conversion between NUMBER and VARCHAR2, or between DATE and strings.
4. **Standardize to target types:** use `CAST` in each branch when a stable output type is needed.
5. **Parse text properly:** use `TO_NUMBER`, `TO_DATE`, `TO_TIMESTAMP` with appropriate format models and NLS settings.
6. **Type NULLs when needed:** use `CAST(NULL AS target_type)`.
7. **Preserve precision:** do not downcast TIMESTAMP to DATE or promote NUMBER to BINARY_DOUBLE without assessing impact.
8. **Respect code nature:** codes with leading zeros or non-numeric characters should stay character-typed.
9. **Do not format to text too early:** `TO_CHAR` is for display output; data used for arithmetic should stay numeric/datetime.
10. **UNION ALL still requires type compatibility:** keeping duplicate rows does not relax data type rules.

## 18. Self-check questions

**Question 1.** Can two branches of `UNION ALL` return different numbers of columns?

**Answer:** No. Every branch must return the same number of expressions positionally.

**Question 2.** Why can `SELECT 1 FROM dual UNION ALL SELECT '1' FROM dual` fail?

**Answer:** `1` is NUMBER and `'1'` is VARCHAR2. Corresponding expressions belong to different datatype groups; Oracle does not implicitly convert across groups for set operators.

**Question 3.** Does `UNION ALL` skip type compatibility checks because it does not deduplicate?

**Answer:** No. `UNION ALL`, `UNION`, `INTERSECT`, and `MINUS` all require compatible column structures and types.

**Question 4.** When one branch lacks a creation date, what should be placed in the date column?

**Answer:** `CAST(NULL AS DATE)` or `CAST(NULL AS TIMESTAMP)` matching the chosen output type.

**Question 5.** Why should code `'00125'` not be converted to NUMBER in a merge query?

**Answer:** Converting to a number strips leading zeros; if they are part of the identifier, the result loses its meaning.

**Question 6.** What is the numeric precedence order among NUMBER, BINARY_FLOAT, and BINARY_DOUBLE?

**Answer:** `BINARY_DOUBLE` is highest, followed by `BINARY_FLOAT`, then `NUMBER`.

**Question 7.** When sources have DATE and TIMESTAMP, does promoting DATE to TIMESTAMP lose information?

**Answer:** It loses no existing DATE information; fractional seconds are filled with 0. Going from TIMESTAMP down to DATE truncates fractional seconds.

**Question 8.** Does a format model directly resolve ORA-01790?

**Answer:** No. Format models only parse or format data. After parsing, you must still ensure the resulting types of the branches are compatible.

**Question 9.** Does an alias in the second SELECT branch rename the output column of a UNION?

**Answer:** No. Output column names come from the first SELECT branch; branches match by position.

**Question 10.** Should you CAST every column to VARCHAR2 to avoid type errors?

**Answer:** No. Doing so loses numeric/datetime types, breaking sorting and arithmetic. Pick output types based on data semantics.

**Question 11.** Can set operators be used directly on CLOB/BLOB/collections just like on NUMBER?

**Answer:** Do not assume so. Oracle has restrictions on LOBs and collections; typically merge keys/metadata first and fetch LOBs separately.

**Question 12.** When two branches return TIMESTAMP WITH TIME ZONE and timezone-less TIMESTAMP, what must be clarified?

**Answer:** You must determine the time zone of the timezone-less branch and which result type to preserve. Do not arbitrarily attach UTC or drop offsets without a business rule.

## 19. Conclusion

`UNION`, `UNION ALL`, `INTERSECT`, and `MINUS` combine result sets by **column position**. Every branch must return the same column count, and corresponding expressions must have compatible types under Oracle rules. In particular, Oracle does not implicitly convert across datatype groups like `NUMBER` and `VARCHAR2` merely because text values look numeric. When needed, standardize explicitly with `CAST`, `TO_NUMBER`, `TO_DATE`, or `TO_TIMESTAMP`.

Define the output contract before writing the query: which columns are IDs, amounts, datetimes, text, or NULL; which types must be preserved; and whether precision, leading zeros, or time zones matter. `CAST(NULL AS target_type)` ensures branches missing data still carry an explicit type. Avoid formatting numbers/datetimes to strings too early, as that forfeits native arithmetic and comparisons.

When encountering `ORA-01789` or `ORA-01790`, verify column counts, positions, expression types, and source values branch by branch. A well-written set query does more than avoid syntax errors—it returns the exact structure and semantics the application requires.
