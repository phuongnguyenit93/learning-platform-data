# Quoting Identifiers and Values to Prevent SQL Injection in PL/pgSQL

## 1. The Problem: When SQL Statements Are Built from Strings

In PostgreSQL, PL/pgSQL allows constructing and executing SQL statements dynamically:

```sql
EXECUTE v_sql;
```

This capability is useful when part of the SQL structure varies at runtime: periodic archive table names, a column chosen from an allowed list, an administrative schema name, or a sort mode. However, **SQL injection** can occur if a developer concatenates untrusted data directly into the SQL statement.

Unsafe example:

```sql
v_sql :=
    'SELECT count(*) FROM quote_lab.orders ' ||
    'WHERE customer_code = ''' || p_customer_code || '''';

EXECUTE v_sql INTO v_count;
```

If `p_customer_code` contains a single quote, the statement can fail or change meaning. A value containing special characters is not automatically treated as pure data just because it comes from a PL/pgSQL variable.

PostgreSQL provides multiple tools to handle the three categories of components properly:

- **Identifiers:** schema, table, column, index, sequence, and function names.
- **Data values:** customer codes, amounts, dates, search keywords, and note strings.
- **SQL syntax:** `ORDER BY`, `ASC`/`DESC`, operators, relation names, or DDL clauses intentionally selected by the application.

```text
                  Value coming from request
                           |
               +-----------+------------+
               |                        |
          Data value             Object/column name
               |                        |
           Use USING             Check allowlist
               |                        |
        $1, $2, $3...             %I / quote_ident
               |                        |
               +------------+-----------+
                            |
                  Controlled SQL text
                            |
                   PL/pgSQL EXECUTE
                            |
              Still must check PRIVILEGES
```

> **Top priority:** for values inside dynamic `SELECT`/`INSERT`/`UPDATE`/`DELETE` statements, use `EXECUTE ... USING` instead of embedding literals into the string. For object/column names that cannot be passed as parameters, use `format('%I', ...)` or `quote_ident(...)` **after validating against an allowlist**. Quoting prevents syntax confusion; it does not grant safe access permissions by itself.

## 2. Learning Objectives

After this lesson, you will be able to:

1. Recognize the three layers: SQL text, identifiers, and data values.
2. Explain the roles of `quote_ident`, `quote_literal`, and `quote_nullable`.
3. Use `format('%I')`, `format('%L')`, and `format('%s')` properly.
4. Understand why `%I` and `%L` cannot be used interchangeably.
5. Understand how `quote_literal`, `quote_nullable`, and `format` handle `NULL`.
6. Write `EXECUTE ... USING` to bind typed values without string concatenation.
7. Know the boundary: bind parameters cannot represent table names, column names, or SQL keywords.
8. Construct SQL statements with **separate schema and table names**, rather than quoting a dot as a single identifier.
9. Use allowlists to guard dynamic table, column, and sort direction choices.
10. Distinguish injection via literals, identifiers, keywords, and SQL patterns.
11. Avoid common mistakes when writing `LIKE`, `ILIKE`, and regular expressions with user input.
12. Use `IS NOT DISTINCT FROM` when comparing `NULL` values under equality semantics.
13. Handle dynamic `ORDER BY` and bounded `LIMIT` without allowing arbitrary SQL.
14. Distinguish PL/pgSQL `EXECUTE` from SQL `EXECUTE` for prepared statements.
15. Understand plan-caching characteristics of static SQL versus dynamic SQL.
16. Write illustrative PL/pgSQL functions with full input validation and safe statements.
17. Protect `SECURITY DEFINER` routines with a trusted `search_path`.
18. Test with single quotes, Unicode characters, `NULL`, and strings intended to alter SQL structure.
19. Identify utility DDL situations where values cannot be bound as parameters.
20. Apply a review checklist and practice exercises in Java/JDBC applications.

## 3. First: How SQL Text Differs from an SQL Value

A fixed-structure SQL query:

```sql
SELECT order_id, customer_code
FROM quote_lab.orders
WHERE customer_code = 'O''Reilly';
```

Here:

- `SELECT`, `FROM`, `WHERE` are SQL syntax.
- `quote_lab.orders`, `order_id`, `customer_code` are identifiers.
- `'O''Reilly'` is **a string literal**.

The data string `O'Reilly` is represented inside an SQL literal by **two single quotes** where the literal content has one quote.

In PL/pgSQL, instead of building those doubled quotes yourself, bind the value:

```sql
EXECUTE
    'SELECT count(*)
     FROM quote_lab.orders
     WHERE customer_code = $1'
INTO v_count
USING p_customer_code;
```

The value `p_customer_code` is not concatenated into SQL source code. PostgreSQL receives it as a **parameter value** with proper type semantics.

### 3.1. An Identifier Is Not a String Literal

```sql
SELECT order_id FROM quote_lab.orders;
```

If you write:

```sql
SELECT 'order_id' FROM quote_lab.orders;
```

PostgreSQL returns **a constant text value** `order_id` for every row rather than reading the `order_id` column.

### 3.2. Double Quotes and Single Quotes Serve Different Roles

- `'customer_code'`: string literal.
- `"customer_code"`: column identifier.
- `"Customer Code"`: identifier preserving uppercase letters and spaces.
- `customer_code`: unquoted identifier, subject to PostgreSQL lowercase folding rules.

### 3.3. "Syntactically Valid" Does Not Mean "Authorized"

`format('%I', 'salary')` can generate a valid SQL column name. However, if the user is not authorized to access the `salary` column, quoting that name **does not protect the data**.

**Quoting handles syntactic structure. Authorization handles permitted objects and rows.**

## 4. Setting Up the PL/pgSQL Lab

Run these commands only in a **test database**. Injection examples neither require nor encourage touching production data.

### 4.1. Creating the Schema and Table

```sql
CREATE SCHEMA IF NOT EXISTS quote_lab;

CREATE TABLE quote_lab.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id integer NOT NULL,
    customer_code text NOT NULL,
    status text NOT NULL
        CHECK (status IN (
            'NEW', 'PAID', 'CANCELLED'
        )),
    amount numeric(12,2) NOT NULL
        CHECK (amount >= 0),
    note text,
    created_at timestamptz NOT NULL
        DEFAULT clock_timestamp()
);
```

### 4.2. Loading Data with Quotes and Unicode

```sql
INSERT INTO quote_lab.orders (
    tenant_id,
    customer_code,
    status,
    amount,
    note,
    created_at
)
VALUES
    (10, 'ALICE', 'NEW', 120.00, 'First order',
        timestamptz '2026-01-02 09:00:00+00'),
    (10, 'O''Reilly', 'PAID', 320.00, 'Customer''s note',
        timestamptz '2026-01-03 10:00:00+00'),
    (10, 'VN-ĐỎ', 'NEW', 42.00, NULL,
        timestamptz '2026-01-04 11:00:00+00'),
    (10, 'A%_B', 'PAID', 51.00, 'Contains wildcard characters',
        timestamptz '2026-01-05 12:00:00+00'),
    (20, 'ALICE', 'PAID', 999.00, 'Other tenant',
        timestamptz '2026-01-06 13:00:00+00'),
    (20, 'O''Reilly', 'CANCELLED', 777.00, NULL,
        timestamptz '2026-01-07 14:00:00+00');
```

There are two tenants (10 and 20), matching customer codes across tenants, Unicode data, single quotes, `%`/`_` wildcards, and `NULL`.

### 4.3. Creating an Archive Table for Dynamic Identifier Practice

```sql
CREATE TABLE quote_lab.orders_archive (
    order_id bigint PRIMARY KEY,
    tenant_id integer NOT NULL,
    customer_code text NOT NULL,
    status text NOT NULL,
    amount numeric(12,2) NOT NULL,
    note text,
    created_at timestamptz NOT NULL
);

INSERT INTO quote_lab.orders_archive (
    order_id, tenant_id, customer_code,
    status, amount, note, created_at
)
VALUES
    (1001, 10, 'ALICE', 'PAID', 10.00,
        'Old data', timestamptz '2025-01-01 00:00:00+00'),
    (1002, 20, 'BOB', 'PAID', 20.00,
        'Old data', timestamptz '2025-01-02 00:00:00+00');
```

This dataset illustrates two table names **explicitly permitted by the system**, not every table in the database.

### 4.4. Basic Statistics

```sql
ANALYZE quote_lab.orders;
ANALYZE quote_lab.orders_archive;

SELECT
    tenant_id,
    COUNT(*) AS orders_count,
    SUM(amount) AS total_amount
FROM quote_lab.orders
GROUP BY tenant_id
ORDER BY tenant_id;
```

From here on, examples use the `quote_lab` schema so real objects are easy to identify.

## 5. `quote_ident(text)`: Quoting SQL Identifiers

The `quote_ident` function takes **one identifier** and returns a text representation safe to place in an identifier position within SQL text.

```sql
SELECT
    quote_ident('orders') AS regular_name,
    quote_ident('Order Details') AS spaced_name,
    quote_ident('select') AS keyword_name,
    quote_ident('CustomerCode') AS mixed_case;
```

In meaning:

- `orders` can be returned unquoted since double quotes are unnecessary.
- `Order Details` is wrapped in double quotes because it contains a space.
- `select` needs double quotes because it is a keyword.
- `CustomerCode` needs double quotes to preserve uppercase letters if that exact identifier is intended.

### 5.1. `quote_ident` Does Not Always Add Double Quotes

This is an important detail. `quote_ident('orders')` returns `orders` rather than `"orders"`.

Its job is to produce a **syntactically valid identifier**, not to guarantee that the output always starts and ends with double-quote characters.

### 5.2. Identifiers Containing Double Quotes

```sql
SELECT quote_ident('has"quote') AS escaped_identifier;
```

A double quote inside an identifier must be doubled inside the quoted identifier so it does not terminate the name prematurely.

### 5.3. Identifiers Containing Dots

```sql
SELECT quote_ident('quote_lab.orders');
```

This treats it as **one** identifier containing a dot, not two components (schema + table). The output corresponds to a quoted identifier such as `"quote_lab.orders"`.

If you want a fully qualified relation:

```sql
SELECT
    quote_ident('quote_lab') || '.' ||
    quote_ident('orders') AS qualified_name;
```

The result produces two identifiers joined by an **SQL syntactic dot**.

### 5.4. Does a Quoted Identifier Mean It Is Permitted?

No. `quote_ident('pg_authid')` simply quotes a name; it does not check whether the caller is permitted to access sensitive system catalogs.

If a table name comes from a request, you still need an allowlist or a mapping from business choices to fixed object names.

### 5.5. What About `NULL`?

`quote_ident(NULL::text)` does not produce a usable identifier. `format('%I', NULL)` will raise an error because SQL has no "NULL identifier."

Validation should reject `NULL` or empty values **before constructing SQL**.

## 6. `quote_literal(anyelement)`: Quoting a Value as an SQL Literal

`quote_literal` returns a text string representing a safe SQL literal, for example:

```sql
SELECT
    quote_literal('hello') AS simple_literal,
    quote_literal('O''Reilly') AS apostrophe_literal,
    quote_literal(42) AS numeric_literal,
    quote_literal(DATE '2026-01-01') AS date_literal;
```

For `O'Reilly`, the output produces a string literal with surrounding single quotes and the inner quote escaped according to PostgreSQL rules.

### 6.1. Use Only When Building SQL Text Is Truly Necessary

In PL/pgSQL:

```sql
v_sql :=
    'SELECT count(*)
       FROM quote_lab.orders
      WHERE customer_code = ' ||
    quote_literal(p_customer_code);
```

handles quotes inside `p_customer_code` from a quoting standpoint, **but this is not the preferred approach** if the statement supports bound values.

Preferred approach:

```sql
EXECUTE
    'SELECT count(*)
       FROM quote_lab.orders
      WHERE customer_code = $1'
INTO v_count
USING p_customer_code;
```

### 6.2. Values and Data Types

`quote_literal` produces a **text** representation embedded back into SQL source, so subsequent parsing and type casting may depend on literal position, column types, implicit casts, and configuration.

`EXECUTE ... USING` passes values with their native data types, which is usually simpler and safer while avoiding unnecessary literal parsing and conversion.

### 6.3. Do Not Quote Identifiers with `quote_literal`

Wrong SQL position:

```sql
SELECT quote_literal('orders');
```

produces an SQL text literal, not a table identifier.

If you build:

```sql
'SELECT * FROM ' || quote_literal('orders')
```

the statement becomes `SELECT * FROM 'orders'`, which is invalid because a table cannot be referenced via a string literal.

**Use `%I`/`quote_ident` for table names; use `%L`/`quote_literal` for literal values.**

## 7. `quote_literal(NULL)`: A Serious Trap in String Concatenation

`quote_literal` is a **STRICT** function: if you pass SQL `NULL`, the result is **SQL NULL**.

```sql
SELECT
    quote_literal(NULL::text) IS NULL
        AS literal_returns_sql_null;
```

The result is `true`.

### 7.1. One NULL Part Turns the Entire SQL Text into NULL

```sql
SELECT
    'SELECT * FROM quote_lab.orders WHERE note = ' ||
    quote_literal(NULL::text)
        AS generated_sql;
```

Because of string concatenation `||` with `NULL`, `generated_sql` evaluates to SQL `NULL`.

If you pass that string to:

```sql
EXECUTE v_sql;
```

PostgreSQL raises an error such as **query string argument of EXECUTE is null**.

### 7.2. Do Not Confuse SQL NULL with the String `'NULL'`

- SQL `NULL`: absence of a value.
- Text `'NULL'`: the four characters N-U-L-L.
- SQL token `NULL` in a dynamic SQL string: the null literal parsed in SQL.

They differ in both type and semantics.

### 7.3. Does `quote_nullable` Solve Everything?

`quote_nullable` handles **representing NULL in SQL text**, but it does not automatically fix the semantics of `= NULL` in a `WHERE` clause.

You need to understand both parts—building the string safely **and** writing the `NULL` comparison properly.

## 8. `quote_nullable(anyelement)`: Avoiding NULL SQL Text on NULL Input

`quote_nullable` returns an SQL literal string for non-NULL values, and for SQL `NULL` input returns **text containing the `NULL` token**.

```sql
SELECT
    quote_nullable(NULL::text) AS null_token_text,
    quote_nullable('O''Reilly') AS quoted_text,
    quote_nullable(42) AS quoted_number;
```

You can verify:

```sql
SELECT
    quote_nullable(NULL::text) IS NULL
        AS returns_sql_null,
    quote_nullable(NULL::text) = 'NULL'
        AS returns_text_token;
```

Expected:

- `returns_sql_null = false`.
- `returns_text_token = true`.

### 8.1. Building SQL Without Becoming NULL on Missing Data

```sql
SELECT
    'SELECT count(*) FROM quote_lab.orders ' ||
    'WHERE note IS NOT DISTINCT FROM ' ||
    quote_nullable(NULL::text) AS sql_text;
```

The end becomes the SQL token `NULL`, so the command string remains intact.

### 8.2. The `= NULL` Trap

Do not use:

```sql
WHERE note = NULL
```

to find rows where `note IS NULL`. The expression `note = NULL` evaluates to `UNKNOWN`, not `TRUE`.

### 8.3. Null-Safe Comparison

```sql
WHERE note IS NOT DISTINCT FROM NULL
```

returns `TRUE` when `note` is also `NULL` and `FALSE` when only one side is `NULL`.

With bound parameters:

```sql
EXECUTE
    'SELECT count(*)
       FROM quote_lab.orders
      WHERE note IS NOT DISTINCT FROM $1'
INTO v_count
USING p_note;
```

This is the **preferred pattern** when you need equality semantics that treat `NULL` as matching `NULL`.

### 8.4. `IS DISTINCT FROM` for Inequality Comparisons

`IS DISTINCT FROM` treats `NULL` as a comparable value so it returns Boolean `TRUE`/`FALSE` instead of `UNKNOWN`.

```sql
SELECT
    NULL::text IS NOT DISTINCT FROM NULL::text
        AS both_null_equal,
    'abc'::text IS DISTINCT FROM NULL::text
        AS text_differs_from_null;
```

## 9. Comparison Table of Quoting Functions

| Function | Input | Output for SQL assembly | SQL `NULL` input |
| --- | --- | --- | --- |
| `quote_ident(text)` | An identifier | Valid identifier, possibly `"..."` | No useful NULL identifier |
| `quote_literal(value)` | A data value | SQL literal text with proper quotes/escapes | Returns SQL `NULL` |
| `quote_nullable(value)` | A data value or `NULL` | SQL literal text or `NULL` token | Returns text `'NULL'` |
| `format('%I', value)` | Identifier | Same intent as `quote_ident` | Raises an error on NULL identifier |
| `format('%L', value)` | Data value | Same intent as `quote_nullable` | Text `'NULL'` |
| `format('%s', value)` | Plain text substitution | No SQL quoting/escaping | Replaced with empty string |

**None of the functions in this table checks authorization.**

### 9.1. A Side-by-Side Example

```sql
SELECT
    quote_ident('Order Details') AS identifier_sql,
    quote_literal('Order Details') AS literal_sql,
    quote_nullable('Order Details') AS nullable_sql,
    format('%I', 'Order Details') AS format_identifier,
    format('%L', 'Order Details') AS format_literal;
```

### 9.2. Do Not Visually Misread Console Output

When a console displays `'abc'` or `"abc"`, those quotes **are inside the generated text value**, not a new data type.

Inspecting output with `SELECT quote_* (...)` only demonstrates how SQL source text is built; it does not mean those functions executed the generated SQL.

## 10. `format`: Building More Readable SQL Than `||` Concatenation

PostgreSQL supports:

```sql
format(format_string, arguments...)
```

Format specifiers that are particularly important in dynamic SQL:

- `%I`: inserts an **identifier** quoted per PostgreSQL rules.
- `%L`: inserts an SQL **literal**, handling `NULL`.
- `%s`: inserts **text** directly, **with no SQL quoting guaranteed**.
- `%%`: a literal percent character inside the format string.

### 10.1. Identifier Example

```sql
SELECT format(
    'SELECT %I FROM %I.%I',
    'Customer Code',
    'quote_lab',
    'orders'
);
```

The result is SQL text referencing column `"Customer Code"`, schema `quote_lab`, and table `orders`. The demo column does not exist in the lab table; this statement **only generates a string**, it does not execute it.

### 10.2. Literal Example

```sql
SELECT format(
    'SELECT * FROM quote_lab.orders WHERE customer_code = %L',
    'O''Reilly'
);
```

`%L` produces a literal representation with properly escaped single quotes.

### 10.3. How `%I` and `%L` Differ

```sql
SELECT
    format('%I', 'select') AS identifier_form,
    format('%L', 'select') AS literal_form;
```

One produces the identifier `"select"`, while the other produces the literal `'select'`.

### 10.4. `%s` Is Not for Untrusted SQL Input

```sql
SELECT format(
    'SELECT * FROM quote_lab.orders ORDER BY %s',
    'order_id DESC'
);
```

The output is valid SQL, but if the second argument comes directly from a user, they can inject **arbitrary SQL syntax**.

`%s` is only appropriate when text substitution inserts a fragment **generated by code from a fixed allowlist**, never raw user input.

### 10.5. Positional Specifiers

```sql
SELECT format(
    'SELECT %1$I FROM %2$I.%3$I ORDER BY %1$I',
    'order_id',
    'quote_lab',
    'orders'
);
```

`%1$I` reuses the first argument in multiple places, avoiding repetitive quoting code.

### 10.6. Percent Sign in a Format String

```sql
SELECT format('Progress: 50%% complete');
```

The output contains a single `%`. Do not confuse this with a `LIKE` wildcard; `format` and `LIKE` belong to separate language layers.

## 11. Schema and Table Names Must Be Quoted Separately

Wrong:

```sql
format('SELECT * FROM %I', 'quote_lab.orders')
```

This represents a single identifier named `quote_lab.orders`; it does **not** mean schema `quote_lab`, table `orders`.

Right:

```sql
format(
    'SELECT * FROM %I.%I',
    'quote_lab',
    'orders'
)
```

### 11.1. Inside PL/pgSQL

```sql
EXECUTE format(
    'SELECT count(*) FROM %I.%I',
    'quote_lab',
    'orders'
)
INTO v_count;
```

When the table name is chosen by the system from a validated list, this produces the proper identifier path.

### 11.2. No Dynamic SQL Needed When the Object Is Fixed

If you always read `quote_lab.orders`, write static SQL:

```sql
SELECT count(*)
INTO v_count
FROM quote_lab.orders;
```

It is usually simpler, easier to verify permissions on, and easier for PostgreSQL to optimize than dynamic SQL.

### 11.3. Schema Qualification Also Matters for Security

A properly quoted identifier that is **not schema-qualified** still depends on `search_path`. For high-privilege routines, this can introduce shadowing risks.

Prefer explicit `schema.table` qualification for sensitive objects.

## 12. `EXECUTE ... USING`: Preferred Choice for Data Values

PL/pgSQL syntax:

```sql
EXECUTE command_string
    [INTO [STRICT] target]
    [USING expression [, ...]];
```

Example:

```sql
EXECUTE
    'SELECT count(*)
       FROM quote_lab.orders
      WHERE tenant_id = $1
        AND customer_code = $2'
INTO v_count
USING p_tenant_id, p_customer_code;
```

### 12.1. What Are `$1` and `$2`?

Inside a **PL/pgSQL `EXECUTE` command string**, `$1` receives the first expression in `USING`, and `$2` receives the second.

They are not text parameter-name substitutions and not column names.

### 12.2. No Manual SQL String Literal Layer

The value `O'Reilly` can be bound intact. You do not need to call `quote_literal` or double quotes manually.

### 12.3. Preserves Native Types

`USING` keeps data as typed parameters, assisting proper planning and casting rather than forcing every value into SQL literal text.

### 12.4. `NULL` Is a Valid Parameter

```sql
EXECUTE
    'SELECT count(*)
       FROM quote_lab.orders
      WHERE note IS NOT DISTINCT FROM $1'
INTO v_count
USING NULL::text;
```

Unlike concatenating `quote_literal(NULL)`, which wipes out the entire command string.

### 12.5. Combining Identifiers and Parameters

```sql
EXECUTE format(
    'SELECT count(*)
       FROM %I.%I
      WHERE tenant_id = $1 AND status = $2',
    'quote_lab',
    'orders'
)
INTO v_count
USING 10, 'PAID';
```

This is the canonical pattern:

- `%I.%I` for identifiers.
- `$1`/`$2` for values.
- Separate allowlisting and authorization for object selection.

## 13. Distinguishing SQL `EXECUTE` and PL/pgSQL `EXECUTE`

PostgreSQL has two contexts using the keyword `EXECUTE`.

### 13.1. SQL Prepared Statements

```sql
PREPARE find_order(integer) AS
SELECT order_id, status
FROM quote_lab.orders
WHERE tenant_id = $1;

EXECUTE find_order(10);

DEALLOCATE find_order;
```

Here, `EXECUTE find_order(10)` is an **SQL command executing a named prepared statement**.

### 13.2. Dynamic Commands in PL/pgSQL

```sql
EXECUTE
    'SELECT count(*) FROM quote_lab.orders WHERE tenant_id = $1'
INTO v_count
USING p_tenant_id;
```

This is a **PL/pgSQL statement** running a text command with PL/pgSQL's `INTO ... USING` syntax.

### 13.3. Why Distinguish Them?

You cannot arbitrarily copy PL/pgSQL's `INTO variable USING ...` syntax into a top-level SQL statement outside a function and expect it to behave the same way.

### 13.4. Dynamic `EXECUTE` Replans

With `EXECUTE command_string` in PL/pgSQL, PostgreSQL typically parses and replans the dynamic command on every execution, unlike static SQL statements in PL/pgSQL that can use cached plans under PostgreSQL's plan-caching rules.

This can help when parameters have heavily skewed selectivity, but adds planning overhead if invoked repeatedly in a large loop.

**Dynamic SQL is not a default speedup.** Use it when structure needs flexibility or for measured plan-sensitivity reasons.

## 14. Identifiers Cannot Be Bound with `USING`

Example with invalid intent:

```sql
-- Cannot use $1 as a table name:
EXECUTE 'SELECT count(*) FROM $1'
INTO v_count
USING p_table_name;
```

`$1` represents an **expression value**, not a table-name slot in the SQL grammar.

### 14.1. Same for Column Names

```sql
-- Do not substitute a column name with a data parameter:
EXECUTE 'SELECT $1 FROM quote_lab.orders'
USING 'status';
```

Here `$1` evaluates to a constant text value `'status'` on every row (in contexts where allowed), **it does not read the `status` column**.

### 14.2. Right Approach When Choosing a Column

```sql
EXECUTE format(
    'SELECT %I FROM quote_lab.orders WHERE tenant_id = $1',
    v_column_name
)
USING p_tenant_id;
```

Only allow `v_column_name` after verifying it against an allowlist.

### 14.3. SQL Keywords Cannot Be Bound as Parameters

```sql
ORDER BY created_at $1
```

does not let you pass `$1 = 'DESC'` as a sort-direction keyword.

Select a fixed `ASC` or `DESC` fragment in application/PL/pgSQL logic and assemble it into the SQL statement under strict control.

## 15. Quoting Does Not Replace an Allowlist

Suppose a user selects one of two tables:

- `quote_lab.orders`.
- `quote_lab.orders_archive`.

If they pass `pg_catalog.pg_user`, `format('%I.%I', ...)` still produces a syntactically valid reference to that object rather than asking "is the user permitted to select this table?"

### 15.1. Allowlist from Business Choices

```sql
IF p_source IS NULL
   OR p_source NOT IN ('current', 'archive')
THEN
    RAISE EXCEPTION 'Unsupported source'
        USING ERRCODE = '22023';
END IF;

v_table_name :=
    CASE p_source
        WHEN 'current' THEN 'orders'
        WHEN 'archive' THEN 'orders_archive'
    END;
```

This mapping prevents the user from choosing arbitrary table names.

### 15.2. Quote the Name After Selecting the Object

```sql
EXECUTE format(
    'SELECT count(*)
       FROM %I.%I
      WHERE tenant_id = $1',
    'quote_lab',
    v_table_name
)
INTO v_count
USING p_tenant_id;
```

### 15.3. Accepting Arbitrary `tenant_id` Is Not Authorization

A `SECURITY DEFINER` routine accepting `p_tenant_id integer` and letting a caller pass any tenant can expose metrics for every tenant, **even if all SQL quoting is spotless**.

For multi-tenant APIs, tenant scope must come from a **trusted identity/authorization context** or verified mapping, not solely from a self-declared caller parameter.

### 15.4. Identifier Length Limits and Spoofed Names

PostgreSQL limits identifier length at compile time (typically 63 bytes by default). An overly long name can be truncated according to parser/object-creation rules.

If business logic creates many objects from input, enforce name validation, collision checks, and ownership controls; `quote_ident` does not manage namespace governance.

## 16. Complete Function: Allowlisted Table Selection and Tenant Binding

The function below uses dynamic SQL solely because the table name switches between two predefined sources.

```sql
CREATE OR REPLACE FUNCTION quote_lab.count_orders(
    p_source text,
    p_tenant_id integer
)
RETURNS bigint
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, quote_lab, pg_temp
AS $fn$
DECLARE
    v_table_name text;
    v_count bigint;
BEGIN
    IF p_source IS NULL
       OR p_source NOT IN ('current', 'archive')
    THEN
        RAISE EXCEPTION 'Unsupported source: %', p_source
            USING ERRCODE = '22023';
    END IF;

    IF p_tenant_id IS NULL OR p_tenant_id <= 0 THEN
        RAISE EXCEPTION 'Invalid tenant id'
            USING ERRCODE = '22023';
    END IF;

    v_table_name :=
        CASE p_source
            WHEN 'current' THEN 'orders'
            WHEN 'archive' THEN 'orders_archive'
        END;

    EXECUTE format(
        'SELECT count(*) FROM %I.%I
         WHERE tenant_id = $1',
        'quote_lab',
        v_table_name
    )
    INTO v_count
    USING p_tenant_id;

    RETURN v_count;
END;
$fn$;
```

Test:

```sql
SELECT quote_lab.count_orders('current', 10)
    AS current_tenant_10;

SELECT quote_lab.count_orders('archive', 10)
    AS archived_tenant_10;

SELECT quote_lab.count_orders('current', 20)
    AS current_tenant_20;
```

Expected with the lab data:

| Call | Result |
| --- | ---: |
| `count_orders('current', 10)` | 4 |
| `count_orders('archive', 10)` | 1 |
| `count_orders('current', 20)` | 2 |

### 16.1. Why `INVOKER`?

This function does not need privilege escalation. Callers are allowed to invoke it and read the corresponding tables per direct grants or RLS in the lab.

If you want to hide the tables and expose only aggregate results via a definer API, add proper authorization and a scoped owner role. Never flip `SECURITY INVOKER` to `DEFINER` mechanically.

### 16.2. Why `SET search_path`?

It expresses the intent to resolve only built-ins and the trusted schema. The dynamic statement also qualifies `quote_lab` explicitly, reducing the risk of resolving the wrong table.

### 16.3. What If the Caller Lacks `SELECT`?

`SECURITY INVOKER` uses the caller's privileges; having `EXECUTE` on the function does not automatically grant `SELECT` on the two tables.

That is a normal permission error, distinct from a quoting bug.

## 17. Complete Function: Choosing an Allowed Column and Binding a Value

An endpoint wants to count orders by `status` or `customer_code`, without allowing arbitrary queries on `note` or `amount`.

```sql
CREATE OR REPLACE FUNCTION quote_lab.count_by_field(
    p_tenant_id integer,
    p_field text,
    p_value text
)
RETURNS bigint
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, quote_lab, pg_temp
AS $fn$
DECLARE
    v_count bigint;
BEGIN
    IF p_tenant_id IS NULL OR p_tenant_id <= 0 THEN
        RAISE EXCEPTION 'Invalid tenant id'
            USING ERRCODE = '22023';
    END IF;

    IF p_field IS NULL
       OR p_field NOT IN ('status', 'customer_code')
    THEN
        RAISE EXCEPTION 'Unsupported field'
            USING ERRCODE = '22023';
    END IF;

    EXECUTE format(
        'SELECT count(*)
         FROM quote_lab.orders
         WHERE tenant_id = $1
           AND %I = $2',
        p_field
    )
    INTO v_count
    USING p_tenant_id, p_value;

    RETURN v_count;
END;
$fn$;
```

Test:

```sql
SELECT quote_lab.count_by_field(
    10, 'status', 'PAID'
);

SELECT quote_lab.count_by_field(
    10, 'customer_code', 'O''Reilly'
);
```

Both inputs are bound as data values, while the column name is chosen from two permitted options and passed through `%I`.

### 17.1. Why Does the Field Use `%I`?

`status` and `customer_code` are **column names**, so they cannot be substituted with `USING p_field`.

### 17.2. Why Does the Value Use `$2`?

`p_value` is **data**, not SQL source text.

### 17.3. When `p_value` Is `NULL`

The predicate `field = $2` matches nothing when `$2` is SQL `NULL`. If the API wants "field is NULL", define a dedicated operation or use `IS NOT DISTINCT FROM` when null-safe semantics are desired.

### 17.4. Why Not Allow Every Column?

If `p_field = 'amount'` is allowed while `p_value` is `text`, implicit casts or operator resolution can cause errors or semantic bugs. More importantly, depending on the application, users may **not be authorized to filter on sensitive columns**.

### 17.5. This Query Still Needs Authorization for a Public API

An invoker function relies on database roles and RLS having proper permissions. If adapted into a definer API, `p_tenant_id` must be verified from a trusted source.

## 18. Returning Multiple Rows with `RETURN QUERY EXECUTE`

`RETURN QUERY EXECUTE` works inside PL/pgSQL functions returning a result set.

```sql
CREATE OR REPLACE FUNCTION quote_lab.find_orders(
    p_tenant_id integer,
    p_field text,
    p_value text
)
RETURNS TABLE (
    order_id bigint,
    customer_code text,
    status text
)
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, quote_lab, pg_temp
AS $fn$
BEGIN
    IF p_tenant_id IS NULL OR p_tenant_id <= 0 THEN
        RAISE EXCEPTION 'Invalid tenant'
            USING ERRCODE = '22023';
    END IF;

    IF p_field IS NULL
       OR p_field NOT IN ('status', 'customer_code')
    THEN
        RAISE EXCEPTION 'Unsupported search column'
            USING ERRCODE = '22023';
    END IF;

    RETURN QUERY EXECUTE format(
        'SELECT o.order_id, o.customer_code, o.status
         FROM quote_lab.orders AS o
         WHERE o.tenant_id = $1
           AND o.%I = $2
         ORDER BY o.order_id',
        p_field
    )
    USING p_tenant_id, p_value;
END;
$fn$;
```

Try:

```sql
SELECT *
FROM quote_lab.find_orders(
    10, 'customer_code', 'O''Reilly'
);

SELECT *
FROM quote_lab.find_orders(
    10, 'status', 'NEW'
);
```

### 18.1. Risk If the Allowlist Is Omitted

If the function accepts any column name, callers can probe other columns, infer data existence, or trigger type errors. `%I` only prevents breaking SQL syntax; it does not enforce the API contract.

### 18.2. Risk If the Tenant Filter Is Omitted

A text parameter containing `' OR true --` cannot defeat parameter binding, yet if code omits the tenant predicate, results can still leak data from other tenants. That is an **authorization bug**, not injection.

### 18.3. `RETURNS TABLE` Must Match Output

With `RETURN QUERY EXECUTE`, the number of returned columns and their types must match the `RETURNS TABLE` definition. Proper quoting cannot fix a data type mismatch.

## 19. Safe Dynamic `ORDER BY`

An API can allow sorting by:

- `created_at`.
- `amount`.
- `order_id`.

And direction `ASC` or `DESC`.

### 19.1. Never Put Raw `p_sort` Directly into `%s`

Wrong:

```sql
EXECUTE format(
    'SELECT * FROM quote_lab.orders ORDER BY %s',
    p_sort_from_user
);
```

Because `%s` does not quote SQL syntax, input can inject unpermitted expressions or SQL clauses.

### 19.2. Select Column from Allowlist

```sql
IF p_sort_column IS NULL
   OR p_sort_column NOT IN (
       'created_at', 'amount', 'order_id'
   )
THEN
    RAISE EXCEPTION 'Unsupported sort column'
        USING ERRCODE = '22023';
END IF;
```

### 19.3. Derive Direction from a Boolean

```sql
v_direction :=
    CASE WHEN p_descending
        THEN 'DESC'
        ELSE 'ASC'
    END;
```

When `p_descending` is `NULL`, `CASE ELSE` picks `ASC` in this example. Production code can choose to reject `NULL` if preferred.

### 19.4. Assembling the SQL

```sql
EXECUTE format(
    'SELECT order_id, amount, created_at
     FROM quote_lab.orders
     WHERE tenant_id = $1
     ORDER BY %I %s, order_id DESC
     LIMIT $2',
    p_sort_column,
    v_direction
)
USING p_tenant_id, p_page_size;
```

This illustrative snippet must sit in an appropriate PL/pgSQL context; if returning a result set, use `RETURN QUERY EXECUTE`.

- `%I` quotes the allowlisted column name.
- `%s` inserts only the **code-generated `ASC`/`DESC` string**.
- `$1` is the tenant value.
- `$2` is the page-size value.

### 19.5. Capping Page Size

`LIMIT $2` binds the value without bounding resource usage on its own. Validate it:

```sql
IF p_page_size IS NULL
   OR p_page_size < 1
   OR p_page_size > 100
THEN
    RAISE EXCEPTION 'Invalid page size'
        USING ERRCODE = '22023';
END IF;
```

### 19.6. Tie-Breakers and `NULL` Ordering

When sorting by `order_id`, adding a trailing `order_id` tie-breaker is redundant but harmless. For other columns, a trailing unique key keeps pagination stable. If the sort column is nullable, decide `NULLS FIRST`/`LAST` explicitly; never let raw input supply that SQL clause.

## 20. `LIKE`/`ILIKE`: Parameter Binding Does Not Escape Wildcards

A distinct issue from SQL injection is **pattern injection**.

Suppose the user enters:

```text
A%_B
```

If you write:

```sql
EXECUTE
    'SELECT count(*)
     FROM quote_lab.orders
     WHERE customer_code LIKE $1'
INTO v_count
USING '%' || p_search || '%';
```

then `%` and `_` inside `p_search` **remain `LIKE` wildcards**.

Parameter binding prevents SQL syntax injection, but it does not automatically treat the input as literal search characters.

### 20.1. Using an Explicit Escape Character

Choose `!`:

- `!` -> `!!`.
- `%` -> `!%`.
- `_` -> `!_`.

In PL/pgSQL:

```sql
v_literal_search := replace(
    replace(
        replace(p_search, '!', '!!'),
        '%', '!%'
    ),
    '_', '!_'
);

v_pattern := '%' || v_literal_search || '%';

EXECUTE
    'SELECT count(*)
     FROM quote_lab.orders
     WHERE customer_code LIKE $1 ESCAPE ''!'''
INTO v_count
USING v_pattern;
```

Inside a PL/pgSQL single-quoted string, `''!''` produces the SQL clause `ESCAPE '!'`. For fixed command strings, you can use dollar quoting instead of nested single quotes:

```sql
EXECUTE $sql$
    SELECT count(*)
    FROM quote_lab.orders
    WHERE customer_code LIKE $1 ESCAPE '!'
$sql$
INTO v_count
USING v_pattern;
```

### 20.2. Testing Literal Characters

When `p_search = 'A%_B'`, properly escaped code searches for text containing **literal** `A%_B` rather than matching arbitrary strings.

### 20.3. What If Users Are Allowed to Enter Wildcards?

That is a different search feature. Define its UX clearly and guard query cost with length limits, rate limits, timeouts, and indexes instead of silently treating it as plain-text search.

### 20.4. Regex Is Also a Pattern Language

Binding:

```sql
WHERE note ~ $1
```

prevents SQL injection via the regex parameter, yet still lets the regex engine interpret metacharacters. If you want a literal substring search, do not evaluate raw user regexes without a policy.

## 21. `quote_literal` and `standard_conforming_strings`

In PostgreSQL, SQL string escaping involves a detail about backslashes. The setting:

```sql
SHOW standard_conforming_strings;
```

is enabled by default in modern PostgreSQL, so backslashes inside ordinary string literals are not treated as SQL parser escapes the way `E'...'` strings are.

### 21.1. Adding Backslashes Manually Is Error-Prone

Do not rely on replacements like:

```text
replace(input, "'", "\'")
```

and assume it is safe for all SQL literals. Backslash/quote behavior depends on how the parser interprets the literal.

### 21.2. Use PostgreSQL Quoting Primitives

`quote_literal` / `format('%L')` generate SQL literal representations per PostgreSQL rules. For values in dynamic queries, still prefer `EXECUTE ... USING` so you avoid building literals altogether.

### 21.3. Dollar Quoting Is Not for Untrusted Runtime Input

Dollar-quoted strings such as:

```sql
DO $body$
BEGIN
    RAISE NOTICE 'Hello';
END
$body$;
```

are great for writing **fixed source code** containing quotes. Never take arbitrary input and wrap it between `$tag$ ... $tag$` delimiters as a runtime escaping mechanism: input could contain your chosen delimiter, ending the string prematurely.

### 21.4. Three Easily Confused Escaping Layers

When Java calls PostgreSQL PL/pgSQL, there may be:

1. Java source string escaping.
2. SQL command text escaping.
3. Regex/`LIKE` pattern escaping.

Bind parameters eliminate the dangerous SQL command-text escaping layer, while pattern semantics must still be handled explicitly.

## 22. `format('%L')` When Literals Must Be Embedded in Utility Statements

`EXECUTE ... USING` supports parameter placeholders for **optimizable SQL commands** where PostgreSQL allows them, such as `SELECT`, `INSERT`, `UPDATE`, `DELETE`, and `MERGE` depending on version.

Many **utility statements** such as `CREATE`/`ALTER`/`COMMENT` do not accept data parameters where DDL text expects literals.

### 22.1. DDL Comment Example

If an administrative workflow is permitted to set a comment on an allowlisted table:

```sql
EXECUTE format(
    'COMMENT ON TABLE %I.%I IS %L',
    'quote_lab',
    'orders',
    p_comment
);
```

- `%I.%I` for schema + table.
- `%L` for the SQL comment literal, even with quotes.
- `p_comment` can be `NULL`; `%L` emits the `NULL` token to remove the comment per `COMMENT` semantics.

### 22.2. This Is an Admin Example, Not a Public API

`COMMENT ON TABLE` is DDL requiring appropriate privileges. Do not let untrusted users set arbitrary table comments merely because `format` quotes the string.

### 22.3. Quote the Object Path Properly

Wrong:

```sql
format('COMMENT ON TABLE %I IS %L',
       'quote_lab.orders',
       'Example');
```

Right:

```sql
format('COMMENT ON TABLE %I.%I IS %L',
       'quote_lab', 'orders', 'Example');
```

### 22.4. Do Not Expose Overly Broad "Arbitrary" DDL

Even with `%I`/`%L`, a definer function letting users create, drop, or rename objects in arbitrary schemas remains dangerous for both authorization and operations.

Expose only clearly defined operations with an explicit privilege model.

## 23. Special Cases in Quoting Identifiers

### 23.1. Uppercase and Case Folding

```sql
SELECT
    quote_ident('CustomerCode'),
    quote_ident('customercode');
```

In PostgreSQL:

- Unquoted identifiers are folded to lowercase.
- Quoted identifiers preserve exact spelling and case.

Therefore `"CustomerCode"` differs from `customercode` if both exist.

### 23.2. Spaces and Keywords

```sql
SELECT
    quote_ident('Order Details'),
    quote_ident('user'),
    quote_ident('select');
```

`quote_ident` determines when double quotes are required for SQL syntax.

### 23.3. Dots in Names

A single identifier `"a.b"` differs from the qualified reference `a.b`.

### 23.4. Schema Name from Caller

`quote_ident` represents the schema name accurately, **without verifying that the schema belongs to the caller's tenant**. In schema-per-tenant apps, map an authenticated tenant to its permitted schema on the server side.

### 23.5. Empty and `NULL` Object Names

An empty SQL identifier is normally invalid for object references. Validate before `format('%I')` instead of relying on parser errors as your primary validation.

### 23.6. Reserved Words

`quote_ident('select')` produces a valid quoted identifier `"select"`, yet naming tables or columns after SQL keywords hurts readability and operations. When designing new schemas, prefer simple, stable names.

## 24. Resolving Table Names with `regclass`: Benefits and Limits

PostgreSQL has the `regclass` type representing a relation OID and letting the parser resolve relation names.

```sql
SELECT
    'quote_lab.orders'::regclass AS orders_relation,
    'quote_lab.orders_archive'::regclass
        AS archive_relation;
```

### 24.1. Why Is `regclass` Useful?

- Confirms that a relation exists.
- Works cleanly with system catalogs and OIDs.
- In some admin APIs, reduces ambiguity between plain name strings and relation objects.

### 24.2. However, `regclass` Does Not Perform Authorization

A caller can resolve the name of a relation they are not allowed to access. If a definer routine accepts `regclass` and acts with owner privileges on that object, **allowlist and ownership checks** are just as necessary as with text names.

### 24.3. Do Not Rely Blindly on `search_path` When Parsing `regclass`

An unqualified `regclass` string depends on path resolution. In privileged code, prefer schema-qualified names and explicit OID/catalog checks.

### 24.4. Concurrent Object Changes

Between lookup and subsequent DDL, an object can be dropped, renamed, or replaced by another transaction depending on lock/DDL semantics. For privileged admin APIs, design proper locking and error handling rather than treating `regclass` as an immutable authorization lock.

## 25. `SECURITY DEFINER` Amplifies Risk in Dynamic SQL

A function declared with:

```sql
SECURITY DEFINER
```

executes with the owner's privileges inside the routine.

If a caller can supply a table name parameter, quoting only ensures the table name **contains no syntactic SQL injection**, while the owner can still access a relation the caller is unauthorized to read.

### 25.1. Dangerous Example Despite Proper Quoting

```sql
EXECUTE format(
    'SELECT count(*) FROM %I.%I',
    p_schema,
    p_table
)
INTO v_count;
```

If the owner has `SELECT` on many tables, a caller can supply any valid sensitive table and retrieve its row count.

### 25.2. Solutions

- Never let callers control arbitrary schema/table names.
- Map business choices to fixed object names.
- Use a dedicated `NOLOGIN` least-privilege owner role.
- Enforce authorization for tenant, row, and object scope.
- Never trust custom GUCs or self-declared caller parameters without verification.
- Schema-qualify objects and lock `search_path`.
- Revoke `EXECUTE` on the routine from `PUBLIC` unless all roles should invoke it.

### 25.3. Safe `search_path`

Definer template:

```sql
CREATE FUNCTION quote_lab.safe_admin_api(...)
RETURNS ...
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, quote_lab, pg_temp
AS $fn$
BEGIN
    -- Access only allowlisted/authorized objects.
END;
$fn$;
```

This is an **illustrative skeleton**, not a fully executable function because `...` stands for omitted declarations.

### 25.4. Why Does `pg_temp` Go Last?

The temporary schema can otherwise be searched before trusted schemas for **relation and type names** when not explicitly listed. Putting `pg_temp` last in the path and schema-qualifying tables reduces temporary-table shadowing risk in `SECURITY DEFINER`.

### 25.5. Why Does `pg_catalog` Go First?

It ensures built-in functions, operators, and types take precedence over schemas where untrusted objects might exist.

### 25.6. Setting `search_path` Alone Is Not Enough

If code runs `format('%I', p_table)` on an arbitrary table name, it can still access unauthorized objects within the trusted schema. `search_path` protects **name resolution**, while allowlists protect **authorization**.

## 26. Never Put an Untrusted Schema First in a Definer `search_path`

If callers have `CREATE` privilege in `public` or another shared schema, a definer routine with unqualified table, function, or operator references risks object shadowing.

Dangerous configuration:

```sql
SET search_path = untrusted, pg_catalog, quote_lab;
```

where `untrusted` is a schema an attacker can `CREATE` in.

Safer configuration:

```sql
SET search_path = pg_catalog, quote_lab, pg_temp;
```

provided `quote_lab` is genuinely a trusted schema where callers cannot `CREATE`/`ALTER` sensitive objects.

### 26.1. Never Assume `public` Is Safe Based on Legacy Defaults

`CREATE` privileges on `public` vary by PostgreSQL version, upgrades, and grants. Check actual privileges:

```sql
SELECT
    has_schema_privilege(
        'public',
        'CREATE'
    ) AS current_role_can_create;
```

Here, the first argument `'public'` in `has_schema_privilege(name, privilege)` refers to the schema name in the two-argument overload; the result checks the **current effective role's** privilege on schema `public`, not the `PUBLIC` pseudo-role. To check a specific role's privilege, use the three-argument overload:

```sql
SELECT has_schema_privilege(
    'quote_lab_reader',
    'public',
    'CREATE'
);
```

This last query runs only if role `quote_lab_reader` exists; a minimal lab setup may not have created that role yet.

### 26.2. Check RLS Too

A definer owner can bypass RLS under PostgreSQL's rules, especially when the owner is the table owner, a superuser, or has `BYPASSRLS`. Quoting does not restore bypassed policies.

### 26.3. Do Not Identify End Users via `CURRENT_USER` Inside Definer Routines

`CURRENT_USER` inside a definer context reflects the function owner per PostgreSQL semantics. With shared application logins, `SESSION_USER` does not distinguish web users either. Use a protected authorization context.

## 27. `PUBLIC EXECUTE` and Privileges on Dynamic SQL Functions

A newly created PostgreSQL function normally grants `EXECUTE` to `PUBLIC` by default unless default privileges were altered.

When creating a definer function containing dynamic SQL, avoid leaving an open privilege window:

```sql
BEGIN;

CREATE FUNCTION quote_lab.protected_api(
    p_customer_code text
)
RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, quote_lab, pg_temp
AS $fn$
DECLARE
    v_count bigint;
BEGIN
    EXECUTE
        'SELECT count(*)
         FROM quote_lab.orders
         WHERE customer_code = $1'
    INTO v_count
    USING p_customer_code;

    RETURN v_count;
END;
$fn$;

REVOKE ALL ON FUNCTION
    quote_lab.protected_api(text)
FROM PUBLIC;

-- GRANT only to a verified role that actually exists:
-- GRANT EXECUTE ON FUNCTION quote_lab.protected_api(text)
-- TO trusted_api_role;

COMMIT;
```

**This example only protects SQL quoting**, not multi-tenant row access: any caller granted `EXECUTE` without row authorization can retrieve `customer_code` counts across all tenants.

### 27.1. Combining `CREATE`/`REVOKE`/`GRANT` in One Transaction

This prevents a window during which the function already exists and is callable by `PUBLIC` before `REVOKE` executes.

### 27.2. Why Function Ownership Matters

If `protected_api` is owned by a superuser or over-privileged role, any authorization bug in its body has wide blast radius. Create it using the least-privileged owner role suitable for the task.

### 27.3. Never Let Callers Create Objects in Trusted Schemas

`USAGE` allows name lookup; `CREATE` allows object creation. Never grant broad `CREATE` on schemas listed in a definer routine's `search_path`.

## 28. Safe Practice with an Injection-Style String for Observation

Suppose the text input is:

```text
O'Reilly
```

If you try to build a literal via:

```sql
SELECT
    'SELECT * FROM quote_lab.orders
     WHERE customer_code = ''' ||
    'O''Reilly' ||
    '''' AS wrongly_concatenated;
```

the resulting SQL string may lack properly escaped quotes at the newly generated SQL layer.

### 28.1. Quoting a Literal

```sql
SELECT format(
    'SELECT * FROM quote_lab.orders
     WHERE customer_code = %L',
    'O''Reilly'
) AS correctly_quoted;
```

### 28.2. Quoting an Identifier

```sql
SELECT format(
    'SELECT %I FROM quote_lab.orders',
    'customer_code'
) AS column_sql;
```

### 28.3. A Value Crafted to Alter SQL Conditions

Suppose the input is:

```text
O'Reilly' OR TRUE --
```

When bound properly:

```sql
SELECT order_id, tenant_id
FROM quote_lab.orders
WHERE customer_code = 'O''Reilly'' OR TRUE --';
```

In this static SQL representation, the single quotes are doubled so the entire string remains **one literal data value**. It does not turn into `OR TRUE` SQL structure.

In application/PL/pgSQL code, instead of writing literals by hand:

```sql
EXECUTE
    'SELECT count(*)
     FROM quote_lab.orders
     WHERE customer_code = $1'
INTO v_count
USING p_untrusted_text;
```

### 28.4. Focus on Defense, Not Destructive Payloads

There is no need to run destructive commands or privilege escalations to prove risk. Comparing an **unsafe concatenated query** against a **bound query** suffices to demonstrate the data/syntax separation.

## 29. Dynamic `UPDATE`: Protecting Data Values and Business Rules

A PL/pgSQL routine may need to update an order's status.

### 29.1. Pattern with `USING`

```sql
EXECUTE
    'UPDATE quote_lab.orders
     SET status = $1
     WHERE tenant_id = $2
       AND order_id = $3'
USING p_new_status, p_tenant_id, p_order_id;
```

All values stay bound, even if `p_new_status` contains quotes or unusual characters. Constraints on `status` will reject invalid values.

### 29.2. Check Privileges and Scope

If this is a definer function, a client could pass an arbitrary `p_tenant_id` unless the API validates it. Confirm that `p_tenant_id` belongs to the caller or is assigned by a trusted server layer.

### 29.3. Checking the Affected Row Count

```sql
GET DIAGNOSTICS v_affected = ROW_COUNT;
```

Run this immediately after the target statement to inspect affected rows. If exactly one order is expected, handle `0` and `> 1` explicitly.

### 29.4. Atomicity

Invariants such as "an order may only transition `NEW` -> `PAID`" belong in the `WHERE` clause:

```sql
EXECUTE
    'UPDATE quote_lab.orders
     SET status = $1
     WHERE tenant_id = $2
       AND order_id = $3
       AND status = $4'
USING 'PAID', p_tenant_id, p_order_id, 'NEW';
```

This pattern evaluates the transition condition atomically during the `UPDATE`, instead of checking beforehand and then updating unconditionally.

## 30. `quote_nullable` Does Not Replace NULL Logic in `DELETE`/`UPDATE`

Suppose you want to delete or count rows whose `note` matches a given value, including `NULL`.

Wrong SQL semantics:

```sql
WHERE note = NULL
```

Right for null-safe comparison:

```sql
WHERE note IS NOT DISTINCT FROM $1
```

### 30.1. In Dynamic SQL

```sql
EXECUTE
    'SELECT count(*)
     FROM quote_lab.orders
     WHERE tenant_id = $1
       AND note IS NOT DISTINCT FROM $2'
INTO v_count
USING p_tenant_id, p_note;
```

### 30.2. When Forced to Build Literal Text

```sql
v_sql := format(
    'SELECT count(*)
     FROM quote_lab.orders
     WHERE tenant_id = %L
       AND note IS NOT DISTINCT FROM %L',
    p_tenant_id,
    p_note
);
```

`%L` emits the `NULL` token when `p_note` is `NULL`, so the SQL remains valid.

### 30.3. Do Not Fall Back Into Concatenating Literals

Whenever the SQL command supports `USING`, use it. `format('%L')` is a tool for times when SQL text must be built, not a better default everywhere.

## 31. DDL and Object Names: There Is No "Bind Everything"

When constructing DDL, some parts must appear in the command as identifiers or syntax:

```sql
CREATE TABLE some_schema.some_table (...);
```

You cannot use a bind parameter for `some_table` or the `CREATE TABLE` keywords.

### 31.1. Schema/Table Names from Trusted Mapping

```sql
EXECUTE format(
    'CREATE TABLE %I.%I (id bigint PRIMARY KEY)',
    v_admin_schema,
    v_new_table
);
```

Execute only when:

- The caller is authorized to create tables in that schema.
- `v_admin_schema`/`v_new_table` come from a mapping or strict validation.
- No duplicate creation or object quota violation occurs.
- DDL runs under appropriate privilege and transaction boundaries.

### 31.2. Do Not Create New Schemas or Tables Per Request Unboundedly

An API allowing clients to create thousands of arbitrary tables causes catalog bloat, backup complexity, locking overhead, and governance issues—even if every identifier is properly quoted.

### 31.3. Utility DDL Needs Separate Literal Quoting

For `COMMENT ON`, default expressions, or similar clauses, `%L` may be needed. Never pass data through raw `%s` when inserting into SQL text.

### 31.4. Schema-Qualified Names and Privileges

A properly quoted `trusted_schema.some_table` still requires appropriate `DDL`/`SELECT`/`UPDATE` privileges. Quoting does not elevate roles or authorize the operation.

## 32. `format` with Dotted Identifiers and Unicode Characters

PostgreSQL permits quoted identifiers containing uppercase letters, spaces, and many valid Unicode characters.

```sql
SELECT format(
    'SELECT %I FROM %I.%I',
    'Tên cột',
    'quote_lab',
    'Báo Cáo'
);
```

This statement only generates **SQL text**; the demo table and column do not exist.

### 32.1. Unicode Identifier vs. Unicode Literal

- `%I` quotes the column name `Tên cột`.
- `%L` quotes the string value `Tên cột`.

A human sees the same text, while the SQL parser treats them differently.

### 32.2. Do Not Use Single Quotes for a Unicode Identifier

`'Tên cột'` is a string literal, not a column name.

### 32.3. Checking Object Existence

`quote_ident`/`format('%I')` only formats text; it does not create objects. If the object does not exist, the dynamic statement fails at runtime with `relation does not exist` or `column does not exist`.

### 32.4. Schema Qualification Reduces Ambiguity

If multiple schemas contain an `orders` table, use `%I.%I` with a verified schema rather than depending on the caller's `search_path`.

## 33. In Java/JDBC, `PreparedStatement` Is the Counterpart to `USING`

When a Java application calls the database, always prefer JDBC `PreparedStatement` for data values:

```java
String sql = """
    SELECT order_id, customer_code, status
    FROM quote_lab.orders
    WHERE tenant_id = ?
      AND customer_code = ?
    ORDER BY order_id
    """;

try (var ps = conn.prepareStatement(sql)) {
    ps.setInt(1, authenticatedTenantId);
    ps.setString(2, userInput);

    try (var rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(
                rs.getLong("order_id")
            );
        }
    }
}
```

### 33.1. Parameterization at Both Layers

- JDBC `?` keeps input as a data value for the SQL sent from Java.
- PL/pgSQL `EXECUTE ... USING` keeps input as a data value when PL/pgSQL builds a dynamic command.

If Java calls a PL/pgSQL function, the inside of the function must still be written safely; JDBC binding **does not magically fix string-concatenated dynamic SQL inside the function body**.

### 33.2. Never Pass Raw SQL Fragments via Function Parameters

Dangerous pattern:

```java
ps.setString(1, "status = 'PAID' OR TRUE");
```

If the called function concatenates that parameter into a dynamic `WHERE` clause as a raw fragment, it still has a design vulnerability even though JDBC bound it cleanly at the outer call.

### 33.3. Sort Options Must Be Allowlisted

In Java:

```java
String sortColumn = switch (requestedSort) {
    case "newest" -> "created_at";
    case "amount" -> "amount";
    default -> "order_id";
};
```

`sortColumn` is a code-owned fixed value. If you must send a column name to a PL/pgSQL function, the function should still validate it against an allowlist at the database boundary.

### 33.4. Never Embed Arbitrary User-Controlled Schema Names

When a multi-tenant system uses schema-per-tenant, the app must map an authenticated tenant to its schema name from trusted configuration rather than accepting a raw request parameter.

## 34. Performance: Static SQL Is Usually the First Choice

With fixed schema/table/column names, dynamic SQL is unnecessary:

```sql
SELECT count(*)
INTO v_count
FROM quote_lab.orders
WHERE tenant_id = p_tenant_id
  AND customer_code = p_customer_code;
```

### 34.1. Benefits of Static SQL

- Easier to read and review.
- The planner and PL/pgSQL can use cached plans where appropriate.
- No string-building overhead.
- Easier dependency tracking and privilege auditing.
- Smaller injection surface.

### 34.2. When Is Dynamic SQL Genuinely Needed?

- Controlled variation of object identifiers.
- DDL administration tooling.
- Query shapes that must adapt flexibly.
- Requiring per-call custom plans when verified by measurement.
- Metadata-driven tasks backed by strict allowlists.

### 34.3. Dynamic SQL Is Not Faster by Default

Every `EXECUTE command_string` may replan. If run inside a loop of 100,000 iterations, planning overhead can become substantial.

### 34.4. Do Not Run Dynamic SQL Row by Row If a Set-Based Solution Exists

Instead of looping over rows and running `EXECUTE SELECT count(*)` for each row, consider a single `JOIN` or aggregate query.

### 34.5. `EXPLAIN` with Functions

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT quote_lab.count_orders('current', 10);
```

The `EXPLAIN` output of calling a function **does not necessarily reveal details of SQL statements executed inside the function**. Separate instrumentation may be required to inspect nested dynamic statements.

## 35. Debugging Dynamic SQL Without Logging Secrets

During development, you may want to inspect the generated SQL string.

### 35.1. Illustrative Log Statement

```sql
RAISE NOTICE 'Generated command: %', v_sql;
```

However, if `v_sql` contains sensitive data literals or identifiers, logs can accidentally leak:

- Customer codes.
- Tokens or personal information.
- Internal schema/table names.
- Dynamic DDL.
- Values the caller is not permitted to see.

### 35.2. Safer Logging

- Log the operation type or template identifier rather than the full command text.
- Log parameter counts/types without necessarily logging raw values.
- Use a request correlation ID.
- Redact or hash only when truly necessary under a security policy.
- Enforce log access control and retention policies.

### 35.3. Exception Handling

Error handling at the application and routine levels should distinguish:

- Invalid input / unsupported identifier.
- Permission denied.
- Object not found.
- Constraint violation.
- Unexpected internal failure.

Never catch `WHEN OTHERS THEN RETURN 0` across all failures and silently corrupt business results.

### 35.4. Error Messages and Quote Escaping

A query using `format('%I')` can still fail because the object does not exist or the user lacks permissions. Those are valid errors, not signs that `%I` is broken.

## 36. Test Input Suite for Quoting

In the lab, test these values using prepared/bound parameters:

| Input | Case to verify |
| --- | --- |
| `ALICE` | Simple value |
| `O'Reilly` | Single apostrophe |
| `A%_B` | Literal `LIKE` wildcards |
| `VN-ĐỎ` | Unicode |
| `NULL` (SQL `NULL`) | Null parameter |
| `''` | Empty string |
| `'  spaced  '` | Meaningful whitespace |
| `'select'` | SQL keyword if used as an identifier |
| `'Order Details'` | Identifier containing a space |
| `'a"b'` | Identifier containing a double quote |
| `'quote_lab.orders'` | Dotted name |
| `'x'' OR TRUE --'` | Text that would alter SQL if concatenated improperly |
| Very long string | Input bounds and resource limits |
| String with many `\` | String/regex escaping layers |
| `pg_temp` | Never allow as an untrusted schema for privileged lookups |
| Table name not in allowlist | Must be rejected |
| `NULL` sort column | Must be rejected or use an explicit default |

### 36.1. Do Not Test Return Values Alone

Verify that:

- The function returns the expected rows.
- No cross-tenant queries succeed.
- No unintended data modifications occur.
- No internal SQL leaks into logs.
- No failures happen due to a `NULL` command string.
- No arbitrary identifiers or SQL syntax are accepted.
- `SECURITY DEFINER` privileges, if used, behave properly.
- Performance remains acceptable on broad patterns.

### 36.2. Negative Tests Matter

Invalid inputs must be **explicitly rejected**, never falling back to querying the entire table or a higher-privilege default table.

### 36.3. Connection Pool Testing

If any routine uses session-level `search_path` or custom session context, test sequential requests across the same pooled connection to ensure no state leaks from request A to request B.

## 37. Common Mistakes and How to Fix Them

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Manually concatenating input inside single quotes | Can break SQL literals | `EXECUTE ... USING` |
| Using `quote_literal` on `NULL` then `||` | Turns entire command into `NULL` | `USING` or `quote_nullable` |
| Writing `column = NULL` | Evaluates to `UNKNOWN`, never matches `NULL` | `IS NOT DISTINCT FROM` / `IS NULL` |
| Using `quote_literal` for a table name | Produces string literal, not identifier | `%I` / `quote_ident` |
| Using `quote_ident` for a data value | Produces identifier, not data literal | `USING` / `%L` |
| Quoting `schema.table` with one `%I` | Produces one identifier containing a dot | `%I.%I` |
| Using `%s` with user input | Does not SQL-escape | Allowlist/fixed fragments or `USING` |
| Binding `$1` as a column name | Parameters hold values | `%I` identifier + allowlist |
| Binding `$1` as `ORDER BY DESC` | Keywords cannot be bound as values | Code-selected `ASC`/`DESC` |
| Letting caller pick any table | Quoting does not check permissions | Allowlist mapping |
| Letting caller pick any `tenant_id` | Authorization bypass | Trusted context + validation |
| Securing only the outer JDBC call | Inner function still concatenates strings | Bind inside PL/pgSQL too |
| Treating `LIKE $1` input as literal | `%` and `_` stay wildcards | Escape patterns explicitly with `ESCAPE` |
| Allowing unbounded arbitrary regex | Patterns can spike CPU | Policy/timeouts/indexes |
| Embedding input inside dollar quotes | Input can break the delimiter | Bind/quote values properly |
| Placing an untrusted schema in `search_path` | Object/function hijacking | Trusted `search_path` |
| Omitting `pg_temp` in definer `search_path` | Temp relations can shadow earlier | List `pg_temp` last |
| Superuser `SECURITY DEFINER` owner | Very broad blast radius | Least-privilege owner |
| Leaving `PUBLIC EXECUTE` open | Any role can invoke | `REVOKE` inside transaction |
| Assuming quoted schema name is safe | Can still target sensitive objects | Authorization |
| Running `EXECUTE` per row | High planning overhead | Set-based SQL |
| Concatenating formatted dates/numbers manually | Fragile type/timezone semantics | Bind typed parameters |
| Properly quoted DDL without checking rights | Privileges still apply | Manage `GRANT`/ownership |
| Logging full `v_sql` indiscriminately | Can leak PII/secrets | Structured sanitized logging |

## 38. Practice Exercises with Answers

Exercises use the `quote_lab` schema. Statement-level `EXECUTE` snippets belong inside a PL/pgSQL function or `DO` block with matching variable declarations; do not run PL/pgSQL `INTO variable USING ...` directly as a top-level SQL command.

### Exercise 1. How do identifiers and literals differ?

**Answer:** An identifier names an object or column; a literal represents a data value inside an SQL expression. Double quotes wrap quoted identifiers, while single quotes wrap string literals.

### Exercise 2. What is `quote_ident` used for?

**Answer:** A single SQL identifier such as a schema, table, or column name.

### Exercise 3. What is `quote_literal` used for?

**Answer:** A data value formatted as a literal inside SQL text; if the SQL statement supports parameters, prefer `USING`.

### Exercise 4. How does `quote_nullable` differ from `quote_literal`?

**Answer:** `quote_nullable(NULL)` returns text containing the `NULL` token, whereas `quote_literal(NULL)` returns SQL `NULL`.

### Exercise 5. Which function does `format('%I')` correspond to?

**Answer:** `quote_ident`, for quoting identifiers.

### Exercise 6. Which function does `format('%L')` correspond to?

**Answer:** `quote_nullable`, for formatting literals and `NULL` inside dynamic SQL text.

### Exercise 7. Does `format('%s')` automatically escape SQL?

**Answer:** No. Never use it with arbitrary text in SQL syntax positions.

### Exercise 8. How do you quote separate schema and table components?

```sql
SELECT format('%I.%I', 'quote_lab', 'orders');
```

**Answer:** Quote each component separately joined by the syntactic dot.

### Exercise 9. Why does `format('%I', 'quote_lab.orders')` miss the intent?

**Answer:** It creates a single identifier containing a dot, not a fully qualified `schema.table` reference.

### Exercise 10. Does `quote_ident('orders')` always add double quotes?

**Answer:** No. It adds them only when needed to represent a valid identifier.

### Exercise 11. Why must `quote_ident('Order Details')` use quotes?

**Answer:** Identifiers containing spaces cannot be written unquoted under standard SQL syntax.

### Exercise 12. How should `'O''Reilly'` be passed into a dynamic `SELECT`?

```sql
EXECUTE
    'SELECT count(*) FROM quote_lab.orders
     WHERE customer_code = $1'
INTO v_count
USING p_customer_code;
```

**Answer:** Bind `p_customer_code` instead of manually escaping quotes.

### Exercise 13. Why does `quote_literal(NULL)` break SQL concatenation?

**Answer:** As a `STRICT` function it returns SQL `NULL`, causing the entire `||` concatenation to evaluate to `NULL`.

### Exercise 14. Does `quote_nullable(NULL)` produce the string literal `'NULL'`?

**Answer:** No; it returns text representing the SQL `NULL` keyword without surrounding single quotes, not the character string `'NULL'`.

### Exercise 15. Does `column = NULL` match `NULL` rows?

**Answer:** No. It evaluates to `UNKNOWN`; use `IS NULL` or `IS NOT DISTINCT FROM`.

### Exercise 16. Write a null-safe comparison in dynamic SQL.

```sql
EXECUTE
    'SELECT count(*) FROM quote_lab.orders
     WHERE note IS NOT DISTINCT FROM $1'
INTO v_count
USING p_note;
```

**Answer:** Handles both `NULL` and non-`NULL` `p_note` values cleanly.

### Exercise 17. Can `EXECUTE ... USING` bind a table name?

**Answer:** No; parameter placeholders represent data values, not identifiers.

### Exercise 18. How do you select a table name safely?

**Answer:** Map valid business options through an allowlist to fixed table names, then format with `format('%I.%I', ...)`.

### Exercise 19. Why can a properly quoted table name still expose unauthorized data?

**Answer:** A user might pass a valid table name they are not permitted to access; quoting does not enforce authorization.

### Exercise 20. Use `format` to build a `SELECT` for a column.

```sql
SELECT format(
    'SELECT %I FROM %I.%I',
    'customer_code',
    'quote_lab',
    'orders'
);
```

**Answer:** Generates SQL text with a quoted column identifier and a fully qualified table name.

### Exercise 21. Can `%I` and `%L` be swapped?

**Answer:** No. One formats an object name and the other formats a value literal; swapping them yields invalid SQL or wrong semantics.

### Exercise 22. How is an identifier containing a double quote handled?

**Answer:** `quote_ident` doubles the embedded double-quote character inside the quoted identifier when necessary.

### Exercise 23. Why must the keyword `select` be quoted when used as a column name?

**Answer:** `select` is an SQL keyword; the quoted identifier `"select"` tells the parser it is an object or column name.

### Exercise 24. When is using `%s` for `DESC` safe?

**Answer:** When the fragment is chosen by code from a Boolean or allowlisted enum, such as selecting strictly `'ASC'` or `'DESC'`.

### Exercise 25. Should a sort string like `'amount DESC, secret'` be accepted from users?

**Answer:** No. Users should pick from defined sort modes rather than supplying raw SQL fragments.

### Exercise 26. Must a bound page size still be validated?

**Answer:** Yes. Binding prevents injection but does not bound row count or CPU; cap it (for instance, 1–100).

### Exercise 27. How does SQL `EXECUTE` for `PREPARE` differ from PL/pgSQL `EXECUTE`?

**Answer:** SQL `EXECUTE` runs a named prepared statement; PL/pgSQL `EXECUTE` runs a dynamic command string and supports `INTO`/`USING`.

### Exercise 28. Does PL/pgSQL dynamic SQL cache plans like static SQL?

**Answer:** Normally it replans on each `EXECUTE`, which adds overhead but can help with heavily skewed parameter distributions.

### Exercise 29. Should `EXECUTE` be used to query a fixed table?

**Answer:** Usually no; static SQL is easier to review, can leverage cached plans, and has a smaller injection surface.

### Exercise 30. Why isn't JDBC binding enough if PL/pgSQL concatenates strings?

**Answer:** Outer JDBC binding protects only the call to the routine; inside the function body, string concatenation can still reinterpret data as SQL syntax.

### Exercise 31. Is dollar quoting foolproof for inserting user input?

**Answer:** No. The chosen delimiter could appear inside the input; dollar quoting is for fixed source code, not a substitute for parameterization.

### Exercise 32. Does `LIKE $1` escape `%` and `_` automatically?

**Answer:** No; they stay pattern wildcards. When searching literals, escape them with `ESCAPE '!'` and bind the escaped pattern.

### Exercise 33. How do you test literal `A%_B` in `customer_code`?

**Answer:** Build the contains pattern `%A!%!_B%` with `ESCAPE '!'` after escaping input characters in the right order, then bind it so `%` and `_` from input are not wildcards.

### Exercise 34. Does regex parameter binding treat metacharacters as literals?

**Answer:** No. It only binds the regex string as an SQL parameter while the regex engine still interprets metacharacters; enforce a policy/escaping or switch to literal `LIKE`.

### Exercise 35. How should values be quoted in `COMMENT ON` utility DDL?

```sql
SELECT format(
    'COMMENT ON TABLE %I.%I IS %L',
    'quote_lab',
    'orders',
    'Owner''s note'
);
```

**Answer:** `%I.%I` for the relation name, `%L` for the comment literal.

### Exercise 36. Can a table name use `USING` in `CREATE TABLE`?

**Answer:** No. The SQL grammar requires an identifier; quote identifiers, validate ownership/authorization, and build DDL only when permitted.

### Exercise 37. Does `quote_ident` create a table if the name does not exist?

**Answer:** No. It only returns text without touching catalogs.

### Exercise 38. Does `regclass` ensure the caller is permitted to use the relation?

**Answer:** No; it resolves an object/OID, whereas privileges and allowlists must be checked separately.

### Exercise 39. Why is `SECURITY DEFINER` especially risky with dynamic table names?

**Answer:** The SQL executes under the owner's privileges; callers could make the owner read or modify unauthorized objects without strict mapping and authorization.

### Exercise 40. Why must `search_path` be locked down in definer routines?

**Answer:** To prevent unqualified object lookups from being shadowed via untrusted schemas or `pg_temp`. Use a trusted path and fully qualify sensitive references.

### Exercise 41. Where should `pg_temp` sit in a definer `search_path`?

**Answer:** Typically last, such as `pg_catalog, quote_lab, pg_temp` where `quote_lab` is a trusted schema.

### Exercise 42. Where should `pg_catalog` sit?

**Answer:** First, ahead of application schemas, so built-in lookups are not shadowed by untrusted objects.

### Exercise 43. Does `SECURITY DEFINER` automatically obey the caller's RLS?

**Answer:** Do not assume so; the effective owner role may bypass RLS depending on privileges and table ownership. Enforce row authorization explicitly.

### Exercise 44. Is leaving `EXECUTE` granted to `PUBLIC` dangerous?

**Answer:** It can be dangerous for privileged routines. Revoke `PUBLIC EXECUTE` and grant it only to required roles per policy.

### Exercise 45. Do you still need tenant authorization after quoting table and column names?

**Answer:** Yes. Quoting protects syntax only; tenant isolation requires a trusted context, query predicates, and/or proper RLS.

### Exercise 46. When is `GET DIAGNOSTICS ROW_COUNT` used?

**Answer:** After dynamic DML when you need the number of affected rows to verify invariants or detect zero/unexpected multi-row changes.

### Exercise 47. Why avoid logging full dynamic SQL strings?

**Answer:** Command text can contain sensitive literals, identifiers, or internal schema info; prefer template IDs, sanitized metadata, and masking.

### Exercise 48. Why test single quotes, `NULL`, and Unicode?

**Answer:** Those inputs expose escaping bugs, parse/type assumptions, and normalization differences missed by happy-path tests.

### Exercise 49. How do SQL injection and pattern injection differ?

**Answer:** SQL injection lets data alter **SQL syntax/structure**; pattern injection alters **`LIKE`/regex pattern semantics** even when SQL syntax is safely bound.

### Exercise 50. List the steps to review a dynamic SQL function.

**Suggested answer:**

1. Is dynamic SQL actually necessary?
2. Separate identifiers, values, and fixed SQL fragments.
3. Use `USING` for values; use `%L` for DDL literals only when unavoidable.
4. Use `%I` and allowlists for identifiers.
5. Quote schema and table separately via `%I.%I`.
6. Never feed raw user input to `%s`.
7. Handle `NULL` explicitly with `IS NOT DISTINCT FROM` or branching.
8. Verify tenant, role, and object authorization—especially in definer routines.
9. Lock down a trusted `search_path` and `pg_temp` placement.
10. Audit `PUBLIC EXECUTE` and owner privileges.
11. Test single quotes, Unicode, `NULL`, `LIKE` wildcards, and unusual identifiers.
12. Measure performance, logging, and behavior under concurrency.

## 39. Pre-Production Review Process for Dynamic SQL

### Step 1. Classify All Inputs

Build a mapping table:

| Input | Category | Handling |
| --- | --- | --- |
| `tenant_id` | Data value | Bind, verify authorization |
| `customer_code` | Data value | Bind `$1` |
| `amount` | Data value | Bind numeric |
| `table_selector` | Business choice | Allowlist -> fixed table identifier |
| `column_selector` | Business choice | Allowlist -> `%I` |
| `sort_order` | SQL syntax fragment | Enum -> fixed `ASC`/`DESC` |
| `comment_text` | DDL literal | `%L` when binding is unsupported |
| `search_text` | `LIKE` literal/pattern | Bind + wildcard escaping when needed |
| `regex` | Regex pattern | Bind + validation/limits |

### Step 2. Default to Static SQL

Ask: "Can this be written as a parameterized static query?" If yes, prefer static SQL.

### Step 3. When Dynamic Is Necessary, Build from Trusted Building Blocks

```text
  Fixed SQL template
          |
+---------+------------+
|                      |
Identifiers        Data values
|                      |
Allowlist            USING
|                      |
%I + schema        $1, $2...
qualification
|                      |
+---------+------------+
          |
       EXECUTE
```

### Step 4. Test Negative Cases

- Object name outside the allowlist.
- `NULL` object name.
- Identifier containing a dot.
- Value containing a single quote.
- Unicode, quotes, and backslashes.
- `LIKE` pattern with literal `%`/`_`.
- Low-privilege user.
- Unauthorized cross-tenant ID.
- Definer function with an overly privileged owner.
- Pooled connections with varying `search_path`.
- Excessively long inputs and expensive queries.

### Step 5. Evaluate Plans and Overhead

Run `EXPLAIN (ANALYZE, BUFFERS)` on equivalent queries with representative parameters. Dynamic SQL does not use indexes any better simply because identifiers are quoted properly.

### Step 6. Privileges and Logging

- Verify grants and ownership.
- Prevent out-of-scope row exposure.
- Avoid logging raw values or secrets unnecessarily.
- Apply timeouts, result caps, and rate limits.
- Maintain rollback and migration plans for dynamic DDL.

## 40. Quick Checklist

| Question | Target state |
| --- | --- |
| Does this query truly have to be dynamic? | Specific justified reason |
| Are all values bound? | `EXECUTE ... USING` |
| Is `quote_literal` unnecessarily concatenated into optimizable SQL? | Refactor to `USING` |
| Are `NULL` values handled safely? | Never turns command string to `NULL` |
| Is null-safe equality needed? | `IS NOT DISTINCT FROM` |
| Are identifiers properly quoted? | `%I`/`quote_ident` |
| Are schema and table quoted separately? | `%I.%I` |
| Are identifiers allowlisted? | No arbitrary object selection |
| Can any user input reach `%s`? | No |
| Is `ORDER BY` direction from an enum? | Fixed `ASC`/`DESC` |
| Is page size bounded? | Validated and bound |
| Do DDL literals use `%L` when needed? | Appropriate placeholder type |
| Does the caller hold object privileges? | Privileges + authorization |
| Does the API enforce tenant isolation? | Trusted context |
| Does `SECURITY DEFINER` follow least privilege? | Scoped owner |
| Does `search_path` list `pg_catalog`/trusted/`pg_temp`? | Right order, trusted schemas |
| Are sensitive references fully qualified? | Explicit schema qualification |
| Could the owner bypass RLS? | Checked |
| Is `PUBLIC EXECUTE` restricted? | Only necessary roles |
| Are quotes/`NULL`/Unicode tested? | Covered |
| Are `LIKE` wildcards well-defined? | Escaped when searching literals |
| Are expensive queries prevented? | Timeouts/limits/indexes |
| Do dynamic SQL logs contain PII? | Redacted/aggregated |
| Does DML check affected row counts? | Business invariants enforced |
| Is per-row `EXECUTE` overused? | Consider set-based SQL |
| Were real query plans measured? | `EXPLAIN`/metrics |
| Was connection pooling tested? | No cross-request state leakage |

## 41. Summary

To prevent SQL injection in PL/pgSQL, you must separate **object names**, **data values**, and **SQL statement structure**.

Rules to remember:

1. **`EXECUTE ... USING` is the first choice for values** in statements that support parameters.
2. **`quote_ident` / `format('%I')` is for identifiers**, not values.
3. **`quote_literal` / `format('%L')` is for SQL literal text**, usually needed only when constructing a literal inside SQL text is unavoidable.
4. **`quote_nullable` and `%L` handle SQL `NULL`** when producing literal text; `quote_literal(NULL)` returns SQL `NULL` and can collapse the entire command string into `NULL`.
5. **`= NULL` never matches `NULL` rows**; use `IS NULL` or `IS NOT DISTINCT FROM` as semantics require.
6. **`format('%s')` does not quote or escape SQL**; never pass raw user input into SQL syntax positions.
7. **`%I.%I` is right for `schema.table`**, whereas `%I` on `'schema.table'` produces a single identifier containing a dot.
8. **Bind parameters cannot replace table, column, or keyword names**. Use an allowlist + `%I` for dynamic identifiers.
9. **Quoting is not authorization**: a valid object name can still belong to data the caller has no right to view.
10. **SQL injection differs from pattern injection**: binding text into `LIKE`/regex leaves pattern wildcards and metacharacters active.
11. **`SECURITY DEFINER` raises the stakes for flawed object or row checks**; owners need least privilege, a safe `search_path`, and explicit authorization.
12. **Static SQL is usually better when structure does not change**; dynamic `EXECUTE` carries planning overhead and extra failure modes.
13. **JDBC `PreparedStatement` at the Java layer does not protect dynamic SQL inside PL/pgSQL** if the database function still concatenates strings.
14. **Test `NULL`, quotes, Unicode, long inputs, cross-tenant IDs, and low-privilege roles**, not just the happy path.
15. **Performance and security go hand in hand**: proper quoting means little if a query triggers full table scans or leaks unauthorized rows.

A PL/pgSQL template worth memorizing:

```sql
-- Assumes v_schema/v_table/v_column have passed the allowlist,
-- p_tenant_id and p_value are data values.
EXECUTE format(
    'SELECT count(*)
       FROM %I.%I
      WHERE tenant_id = $1
        AND %I = $2',
    v_schema,
    v_table,
    v_column
)
INTO v_count
USING p_tenant_id, p_value;
```

**Final rule:** whenever you see `EXECUTE` in PL/pgSQL, ask in order: **"Which part is programmer-controlled SQL, which part is an object name, which part is a data value, who is allowed to choose that object, and under whose privileges will the SQL run?"** When each part has its proper safeguard—**static templates, parameter binding, identifier quoting, allowlists, and authorization**—dynamic SQL becomes far safer and easier to maintain.
