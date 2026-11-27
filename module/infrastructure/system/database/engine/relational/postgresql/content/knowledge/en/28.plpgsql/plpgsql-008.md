# Dynamic SQL with EXECUTE, USING, and format

A sales system has an orders table, an archived orders table, and many kinds of reports. Most queries know the table names, column names, and structure at code-writing time. However, some tasks need to **construct SQL statements at runtime**: selecting a target table from a valid configuration, choosing a sort column per user request, applying a maintenance operation across multiple tables, or creating database objects according to a controlled convention.

In PL/pgSQL, the **`EXECUTE`** statement lets you execute a dynamically built SQL string. Two accompanying tools are especially important:

- **`USING`**: passes **data values** into `$1`, `$2`, ... placeholders inside the dynamic statement, avoiding manual value concatenation or escaping.
- **`format(...)`**: builds SQL strings containing **identifiers** such as schema/table/column names with `%I`, or literals with `%L` when genuinely needed; `%s` inserts raw text only and must be strictly controlled.

This is a topic about both **syntax and query planning** and **security and access control**. Writing a dynamic SQL statement is not enough: you need to know when it is truly necessary, which arguments are passed as data, how to protect identifiers, how to receive results, and the impact on transactions and concurrency.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **static** SQL from **dynamic** SQL in PL/pgSQL and choose the right approach.
2. Write the `EXECUTE command-string [INTO [STRICT] target] [USING ...]` syntax.
3. Use `$1`, `$2` placeholders to bind values into dynamic SQL statements.
4. Use `format('%I', ...)`, `format('%L', ...)`, and `format('%s', ...)` with the proper semantics.
5. Distinguish **data values**, **object names**, **SQL keywords**, and **SQL fragments**.
6. Build dynamic SELECT/INSERT/UPDATE/DELETE queries with tenant filtering, conditions, and table names.
7. Receive a single row with `INTO`, and detect 0 or multiple rows with `INTO STRICT`.
8. Use `GET DIAGNOSTICS ... ROW_COUNT` and understand the limitation of `FOUND` after `EXECUTE`.
9. Use `RETURN QUERY EXECUTE` and `FOR ... IN EXECUTE` to process multiple rows.
10. Build safe dynamic `ORDER BY` and DDL using whitelists and appropriate execution privileges.
11. Understand why `EXECUTE` replans every time, and when that is beneficial or harmful.
12. Apply these concepts with JDBC/Spring, error handling, observability, and hands-on exercises.

> **Environment:** The examples target modern PostgreSQL using `LANGUAGE plpgsql` in a practice schema. `EXECUTE` explained here is the **statement inside PL/pgSQL**, not to be confused with the server-level SQL command `EXECUTE prepared_statement(...)`. The DDL/DML examples modify the database; run them only on a lab database. Do not execute untrusted table names or SQL fragments under a privileged role.

## 2. Static SQL Is the Default Choice

Suppose you need to count orders:

```sql
SELECT count(*)
FROM sales.orders
WHERE tenant_id = 10;
```

If the table name is always `sales.orders`, dynamic SQL is **not needed**.

In PL/pgSQL:

```sql
SELECT count(*)
INTO v_count
FROM sales.orders
WHERE tenant_id = p_tenant_id;
```

This is a static query: PostgreSQL knows the SQL structure, and PL/pgSQL can manage execution plans using its cache/generic-custom plan mechanism.

### When Is Dynamic SQL Actually Needed?

Examples:

- The table name varies within a controlled list.
- The sort column or report column varies according to valid selections.
- Creating tables, indexes, or constraints via DDL for migration or administrative tasks.
- Generating SQL conditions that differ in **structure** based on enabled features.
- A query needs a dedicated plan on each call because input values have wildly different selectivity, after benchmarking confirms it.

Do not use dynamic SQL just to pass `tenant_id` or `status`: a static SQL query with normal parameters already solves that.

## 3. Big Picture of Dynamic SQL

```text
                         PL/pgSQL function
                                  │
                ┌─────────────────┴───────────────────┐
                │                                     │
          SQL structure                          Data values
       schema/table/column                       tenant/status
                │                                     │
      whitelist + format('%I')                      USING
        or validated keywords                   $1, $2, $3...
                │                                     │
                └─────────────────┬───────────────────┘
                                  │
                                  ▼
                      EXECUTE dynamic SQL
                                  │
                    ┌─────────────┴─────────────┐
                    │                           │
               SELECT result               DML/DDL effect
                    │                           │
            INTO / RETURN QUERY          ROW_COUNT / constraint
             FOR IN EXECUTE                transaction
```

**Critical boundary:** `USING` is for values appearing at **data value** positions in supported statements. It cannot turn a string into a table name or an SQL keyword. For identifiers, you must build SQL syntax with proper quoting.

## 4. PL/pgSQL EXECUTE Syntax

Pattern:

```sql
EXECUTE command_string
    [ INTO [STRICT] target ]
    [ USING expression [, ...] ];
```

Where:

- `command_string`: an SQL expression producing a `text` string containing the statement to execute.
- `INTO target`: fetches a single result row into a variable, record, or list of variables.
- `STRICT`: requires exactly **one row**, otherwise raising an exception.
- `USING expression...`: passes values for `$1`, `$2`, ... in the command string.

Minimal example:

```sql
DO $$
DECLARE
    v_result integer;
BEGIN
    EXECUTE 'SELECT $1::integer + $2::integer'
    INTO v_result
    USING 7, 5;

    RAISE NOTICE 'Result = %', v_result;
END;
$$;
```

Value-wise, the result is 12.

### What Is `$1` Inside a Dynamic SQL String?

`$1`, `$2` in the **command string** are placeholders corresponding to the expressions in the `USING` clause of that specific `EXECUTE` invocation. Do not assume they directly reference the first or second parameter of the enclosing PL/pgSQL function.

## 5. Distinguishing Two Easily Confused EXECUTE Commands

In PostgreSQL there are at least two contexts:

**PL/pgSQL dynamic EXECUTE:**

```sql
DO $$
DECLARE v_value integer;
BEGIN
    EXECUTE 'SELECT $1 + 1'
    INTO v_value
    USING 5;
END;
$$;
```

**SQL-level PREPARE/EXECUTE:**

```sql
PREPARE add_one(integer) AS
SELECT $1 + 1;

EXECUTE add_one(5);

DEALLOCATE add_one;
```

| PL/pgSQL `EXECUTE` | SQL `PREPARE`/`EXECUTE` |
|---|---|
| Takes a dynamic SQL string | Uses a predefined prepared statement name |
| Uses `USING` in PL/pgSQL | Passes arguments to `EXECUTE name(...)` |
| Parses/plans the dynamic command on every call | Reuses prepared statements/plans per PostgreSQL rules |
| Results can be received via PL/pgSQL `INTO` | Result is a server-level SQL result set |
| Suitable when **SQL structure** changes | Suitable when **SQL structure stays fixed** across calls |

Do not mix PL/pgSQL's `EXECUTE 'SELECT ...' USING ...` syntax with `EXECUTE prepared_name(...)` in plain SQL examples.

## 6. Creating the Lab Schema and Data

Create a dedicated schema so application data is not affected:

```sql
CREATE SCHEMA IF NOT EXISTS lesson_dynamic_sql;

CREATE TABLE lesson_dynamic_sql.orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED')),
    amount NUMERIC(14,2) NOT NULL
        CHECK (amount >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_orders_tenant_status_created
ON lesson_dynamic_sql.orders (
    tenant_id, status, created_at DESC
);

INSERT INTO lesson_dynamic_sql.orders (
    tenant_id, customer_id, status, amount, created_at
)
VALUES
    (10, 101, 'NEW',       120000.00, TIMESTAMPTZ '2026-10-01 09:00:00+07'),
    (10, 101, 'PAID',      350000.00, TIMESTAMPTZ '2026-10-02 09:00:00+07'),
    (10, 102, 'PAID',      990000.00, TIMESTAMPTZ '2026-10-03 09:00:00+07'),
    (10, 103, 'CANCELLED', 150000.00, TIMESTAMPTZ '2026-10-04 09:00:00+07'),
    (20, 201, 'PAID',      870000.00, TIMESTAMPTZ '2026-10-05 09:00:00+07'),
    (20, 202, 'NEW',       210000.00, TIMESTAMPTZ '2026-10-06 09:00:00+07');
```

### Why Have `tenant_id`?

A multi-tenant system must enforce access control by user and organization. In these labs, `p_tenant_id` illustrates filtering; in production, the tenant value must come from a **trusted authorization context**, not just an arbitrary integer sent by the client.

### Rule for Retrying

The table creation and insert statements above are designed to run when the schema/table does not exist yet. If you have already run them once, use a fresh lab database or clean up data in a controlled manner; do not re-run `CREATE TABLE` with the same name and treat an "already exists" error as an `EXECUTE` issue.

## 7. The Static Approach: No EXECUTE Needed When Structure Is Fixed

```sql
CREATE OR REPLACE FUNCTION lesson_dynamic_sql.total_paid_static(
    p_tenant_id BIGINT
)
RETURNS NUMERIC
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_total NUMERIC;
BEGIN
    SELECT COALESCE(SUM(amount), 0)
    INTO v_total
    FROM lesson_dynamic_sql.orders
    WHERE tenant_id = p_tenant_id
      AND status = 'PAID';

    RETURN v_total;
END;
$$;

SELECT lesson_dynamic_sql.total_paid_static(10);
-- 1340000.00 (350000 + 990000)
```

Advantages:

- The SQL is directly readable.
- Table/column dependencies are clearer.
- No manual command-string construction is needed.
- Data types and testing are easier to manage.
- PL/pgSQL can leverage plan management for static SQL.

If the business logic only queries `lesson_dynamic_sql.orders`, this is usually the approach you should choose.

## 8. Switching to Dynamic SQL When the Table Name Changes

Suppose there are multiple reporting tables with the same `tenant_id`, `status`, and `amount` structure, selected via a valid configuration.

```sql
CREATE OR REPLACE FUNCTION lesson_dynamic_sql.total_by_table(
    p_table_name TEXT,
    p_tenant_id BIGINT,
    p_status TEXT
)
RETURNS NUMERIC
LANGUAGE plpgsql
AS $$
DECLARE
    v_total NUMERIC;
    v_sql TEXT;
BEGIN
    IF p_table_name IS DISTINCT FROM 'orders' THEN
        RAISE EXCEPTION 'Unsupported source table: %', p_table_name;
    END IF;

    v_sql := format(
        'SELECT COALESCE(SUM(amount), 0)
           FROM %I.%I
          WHERE tenant_id = $1 AND status = $2',
        'lesson_dynamic_sql',
        p_table_name
    );

    EXECUTE v_sql
    INTO v_total
    USING p_tenant_id, p_status;

    RETURN v_total;
END;
$$;

SELECT lesson_dynamic_sql.total_by_table(
    'orders',
    10,
    'PAID'
);
-- 1340000.00
```

### Analysis

`format('%I.%I', 'lesson_dynamic_sql', p_table_name)` creates a two-part schema/table SQL object name, with each component properly quoted.

`$1` is `p_tenant_id` and `$2` is `p_status` passed via `USING`. Never concatenate these values directly into the SQL string.

### Why Have a Whitelist?

Although `%I` **quotes the name** to prevent breaking the SQL statement structure, it does not prove that the caller is **authorized** to read that table. A function that accepts an arbitrary table name can inadvertently turn into an API for reading other objects that the function owner role has access to.

The lab example only allows `orders`; when extending it, use a list of allowed tables aligned with business logic, permissions, and data structure.

## 9. Three Categories of Components Requiring Different Handling

| Component | Example | How to place into dynamic SQL |
|---|---|---|
| **Data values** | `tenant_id = 10`, `status = 'PAID'` | `$1`/`$2` + `USING` |
| **Object names** | `lesson_dynamic_sql.orders` | `format('%I.%I', schema, table)` |
| **Fixed SQL keywords** | `ASC`, `DESC` | Validate/whitelist first, then embed text into structure |
| **Complex SQL fragments** | `WHERE ... AND ...` | Generate from controlled components; never accept raw text verbatim from the client |

### Boundary Example

Do not do this:

```sql
-- Wrong: placeholder cannot replace a table name.
EXECUTE 'SELECT count(*) FROM $1'
INTO v_count
USING p_table_name;
```

PostgreSQL needs to know the **relation identifier** at SQL parse time. `$1` represents a **value**, not a syntax piece that can substitute for a table or column.

Conversely, you should not use `format('%I', p_status)` because `p_status` is a **text value** in a `WHERE` condition, not a column name.

## 10. format('%I'): Quoting Identifiers

`%I` formats an argument as an SQL identifier, quoted when necessary:

```sql
SELECT format('%I', 'orders');
-- orders

SELECT format('%I', 'Order Detail');
-- "Order Detail"

SELECT format('%I', 'order');
-- "order" if needed to avoid keywords/ensure valid syntax

SELECT format('%I.%I', 'sales reports', 'Order Detail');
-- "sales reports"."Order Detail"
```

### A `schema.table` Name Is Not a Single Identifier

A common pitfall:

```sql
SELECT format('%I', 'lesson_dynamic_sql.orders');
-- "lesson_dynamic_sql.orders"
```

The result is **one object name containing a dot inside the name**, not `schema.table`.

To produce a qualified name, split it into two parts:

```sql
SELECT format(
    '%I.%I',
    'lesson_dynamic_sql',
    'orders'
);
-- lesson_dynamic_sql.orders
```

When schema, table, and column come from input, apply `%I` **to each component individually**.

## 11. quote_ident and format('%I')

PostgreSQL provides `quote_ident(text)`:

```sql
SELECT quote_ident('Order Detail');
-- "Order Detail"

SELECT format('%I', 'Order Detail');
-- "Order Detail"
```

Both serve to build valid identifiers, but `format` is usually easier to read when assembling multiple parts:

```sql
SELECT format(
    'SELECT %I FROM %I.%I',
    'amount',
    'lesson_dynamic_sql',
    'orders'
);
```

Instead of concatenating strings repeatedly:

```sql
SELECT
    'SELECT ' || quote_ident('amount')
    || ' FROM '
    || quote_ident('lesson_dynamic_sql')
    || '.'
    || quote_ident('orders');
```

### `%I` Is Not Authorization

If a role has permission to create or access arbitrary tables, `%I` only ensures the name is parsed as an identifier. It does not restrict which tables a role can view or modify. Use whitelists, schema-qualified names, and grants/RLS when designing privileged routines.

## 12. format('%L'): Quoting SQL Literals

`%L` converts a value into a properly quoted SQL literal:

```sql
SELECT format('SELECT %L', 'O''Reilly');
-- SELECT 'O''Reilly'

SELECT format('SELECT %L', NULL::text);
-- SELECT NULL
```

`%L` corresponds to `quote_nullable` quoting semantics: a NULL value is represented as the text `NULL`, rather than turning the entire command string into SQL NULL.

### When to Use It?

When a utility statement or syntactic position does not accept a bound parameter from `USING`, you may need to insert a **properly quoted** literal.

However, in data SQL statements such as SELECT/INSERT/UPDATE/DELETE, **prefer USING**: data types are explicit, and values do not have to be converted into text and re-parsed.

Example:

```sql
-- Recommended approach:
EXECUTE
    'SELECT count(*) FROM lesson_dynamic_sql.orders
      WHERE status = $1'
INTO v_count
USING p_status;
```

Not every value should be turned into a literal just because `%L` exists.

## 13. format('%s'): Inserting Raw Text

`%s` inserts text **without quoting it as an identifier or literal**:

```sql
SELECT format(
    'ORDER BY amount %s',
    'DESC'
);
-- ORDER BY amount DESC
```

### Warning

If `p_direction` sent by a client is an arbitrary string, using:

```sql
format('ORDER BY amount %s', p_direction)
```

can produce unexpected SQL syntax. **Only use `%s` to insert whitelisted components** or structural SQL strings safely generated by the application itself.

Sort direction example:

```sql
IF p_direction IS NULL
   OR upper(p_direction) NOT IN ('ASC', 'DESC') THEN
    RAISE EXCEPTION 'Invalid sort direction';
END IF;

v_direction := upper(p_direction);
-- Call format(..., v_direction) only after validating
```

For column names, use `%I`, not `%s`; for data values, use `USING`, not `%s`.

## 14. Cheat Sheet for %I, %L, %s, and USING

| Syntax | Used for | Example input | Result / meaning |
|---|---|---|---|
| `%I` | Identifier | `'Order Detail'` | `"Order Detail"` |
| `%I.%I` | Schema and table | `'s', 't'` | `s.t` |
| `%L` | SQL literal | `'O''Reilly'` | `'O''Reilly'` in SQL text |
| `%s` | Validated raw string | `'DESC'` | `DESC` |
| `$1` + `USING` | Parameter value | `p_tenant_id` | Bound data, not SQL text |

### Practical Rule

> **Use `%I` for object names. Use `USING` for values. Use an allowlist for SQL keywords. Never accept raw SQL fragments from users.**

This is the single most important rule when writing dynamic SQL that incorporates application input.

## 15. Advanced format Specifiers

`format` supports positional argument selection and certain widths/flags:

```sql
SELECT format(
    '%2$I.%1$I',
    'orders',
    'lesson_dynamic_sql'
);
-- lesson_dynamic_sql.orders
```

`%2$I` uses the second argument as an identifier; `%1$I` uses the first argument.

When building a long SQL statement with many identifiers, positional placeholders can avoid repeating the same argument, though they can also make code harder to read. In everyday PL/pgSQL, clear sequential ordering is usually better than minimizing character count.

`format` is not an SQL AST builder: you must still understand the query structure and validate inputs.

## 16. NULL in format and Quote Functions

`%L` can handle SQL NULL to produce the literal `NULL`. `%I` cannot take a NULL identifier because there is no such thing as a "NULL identifier" for a table or column.

```sql
SELECT format('%L', NULL::text);
-- NULL as text in the resulting string

SELECT format('%s', NULL::text);
-- Empty string at the %s position
```

Try:

```sql
-- This statement raises an error because %I does not accept NULL:
-- SELECT format('%I', NULL::text);
```

### `quote_literal` and `quote_nullable`

`quote_literal(NULL)` returns SQL NULL because the function is strict, so string concatenation with `||` can turn the **entire SQL string into NULL**.

`quote_nullable(NULL)` produces the text `NULL`, which is better suited when you genuinely must build a dynamic literal.

`format('%L', value)` is more convenient in most cases than manual string concatenation.

## 17. USING Placeholders and Data Types

A dynamic SQL query:

```sql
DO $$
DECLARE
    v_count BIGINT;
BEGIN
    EXECUTE
        'SELECT count(*)
           FROM lesson_dynamic_sql.orders
          WHERE tenant_id = $1
            AND amount >= $2'
    INTO v_count
    USING 10::bigint, 200000::numeric;

    RAISE NOTICE 'Matches: %', v_count;
END;
$$;
```

`USING` passes **typed values**; PostgreSQL does not have to embed them as SQL string snippets and re-parse them.

### Ordering

`$1` corresponds to the first expression in `USING`, `$2` to the second expression. If you swap their order, you may encounter a type cast error or get wrong query results.

### Reusing the Same Placeholder Multiple Times

```sql
EXECUTE
    'SELECT count(*)
       FROM lesson_dynamic_sql.orders
      WHERE tenant_id = $1
        AND (customer_id = $2 OR order_id = $2)'
INTO v_count
USING 10::bigint, 101::bigint;
```

Multiple occurrences of `$2` reference the same bound value. Note that the check logic in this example is purely illustrative; do not combine confusing conditions when a clearer static query exists.

## 18. USING Prevents Single-Quote Errors and SQL Injection

Suppose the text input is:

```text
O'Reilly
```

If the code concatenates manually:

```sql
v_sql := 'SELECT ... WHERE customer_name = '''
         || p_name || '''';
```

the apostrophe in `O'Reilly` breaks the SQL literal, and can even open an SQL injection vulnerability if the input is crafted to alter syntax.

Instead:

```sql
v_sql := 'SELECT count(*)
          FROM some_allowed_table
          WHERE customer_name = $1';

EXECUTE v_sql INTO v_count USING p_name;
```

This last snippet is an illustrative template assuming a table with a `customer_name` column; do not run it verbatim if your lab database has no such table.

### A Common Misconception

`USING` protects **values**, but if you still concatenate `p_table_name` or `p_sort_expression` directly into the SQL string, the statement can still be altered. You must protect **structure** as well.

## 19. Which Statements Can Use USING?

Bound parameter symbols for `EXECUTE ... USING` are supported at **data value** positions in optimizable statements such as `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `MERGE`, and certain statements containing them per PostgreSQL rules.

**Utility statements** such as most DDL do not support substituting schema/table/column names with `$1`.

Wrong example:

```sql
-- Wrong: $1 does not become a table name:
-- EXECUTE 'ALTER TABLE $1 ADD COLUMN notes text'
-- USING p_table_name;
```

The right way is to build the identifiers in the SQL string using `%I`:

```sql
EXECUTE format(
    'ALTER TABLE %I.%I ADD COLUMN IF NOT EXISTS %I text',
    'lesson_dynamic_sql',
    p_table_name,
    'notes'
);
```

**However**, the object must be allowlisted and the caller must have appropriate DDL privileges. Safe quoting does not replace authorization or assessing locks and downtime.

## 20. EXECUTE and SELECT INTO: Two Places for INTO

In PL/pgSQL, a static SELECT can be written as:

```sql
SELECT amount
INTO v_amount
FROM lesson_dynamic_sql.orders
WHERE order_id = p_order_id;
```

With EXECUTE, the correct placement is:

```sql
EXECUTE
    'SELECT amount
       FROM lesson_dynamic_sql.orders
      WHERE order_id = $1'
INTO v_amount
USING p_order_id;
```

**Do not write `SELECT ... INTO v_amount` inside the dynamic command string** expecting PL/pgSQL to capture it into a variable. In server-level SQL, `SELECT INTO` means creating a new table in certain contexts, unlike PL/pgSQL's `SELECT ... INTO`.

To receive one row from dynamic SQL, place `INTO target` **outside the string**, as part of the `EXECUTE` syntax.

## 21. Returning a Single Value with EXECUTE INTO

```sql
CREATE OR REPLACE FUNCTION lesson_dynamic_sql.count_by_status(
    p_tenant_id BIGINT,
    p_status TEXT
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_count BIGINT;
BEGIN
    EXECUTE
        'SELECT count(*)
           FROM lesson_dynamic_sql.orders
          WHERE tenant_id = $1
            AND status = $2'
    INTO v_count
    USING p_tenant_id, p_status;

    RETURN v_count;
END;
$$;

SELECT lesson_dynamic_sql.count_by_status(10, 'PAID');
-- 2
```

This is syntactically valid `EXECUTE` and `USING`, but **not a good reason to use dynamic SQL**: the table and column names are all fixed. A static version is cleaner and lets PL/pgSQL manage plan caching.

Just because code runs does not prove it is the right architecture.

## 22. Queries Returning No Rows with INTO

`EXECUTE ... INTO target` without `STRICT`:

- If the query returns at least one row, PostgreSQL assigns the **first row** to `target`.
- If the query returns zero rows, `target` receives corresponding SQL NULL values.
- If the query returns multiple rows, the remaining rows are not assigned to `target`.

Example:

```sql
DO $$
DECLARE
    v_amount NUMERIC;
BEGIN
    EXECUTE
        'SELECT amount
           FROM lesson_dynamic_sql.orders
          WHERE order_id = $1'
    INTO v_amount
    USING -1::bigint;

    RAISE NOTICE 'Amount: %', v_amount;
END;
$$;
```

In the lab, `order_id = -1` does not exist, so `v_amount` is NULL.

### If There Are Multiple Rows

Do not write a SELECT without `ORDER BY` and assume the "first row" is always a specific record. SQL guarantees no order without a valid sorting clause.

## 23. INTO STRICT: Requiring Exactly One Row

```sql
CREATE OR REPLACE FUNCTION lesson_dynamic_sql.find_order_amount(
    p_order_id BIGINT
)
RETURNS NUMERIC
LANGUAGE plpgsql
AS $$
DECLARE
    v_amount NUMERIC;
BEGIN
    EXECUTE
        'SELECT amount
           FROM lesson_dynamic_sql.orders
          WHERE order_id = $1'
    INTO STRICT v_amount
    USING p_order_id;

    RETURN v_amount;
END;
$$;
```

With `INTO STRICT`:

- **0 rows** → `NO_DATA_FOUND` exception (SQLSTATE typically `P0002`).
- **1 row** → assigns the data properly.
- **More than 1 row** → `TOO_MANY_ROWS` exception (SQLSTATE typically `P0003`).

### When Should You Use STRICT?

When the API contract requires **exactly one row**—for instance, a primary-key lookup where the business assumption is that the record must exist.

With a `count(*)` query, the aggregate result always has one row even when zero source rows match, so `STRICT` does not detect "order not found"; you must distinguish `count = 0` from the aggregate row count.

## 24. Selectively Catching STRICT Errors

```sql
CREATE OR REPLACE FUNCTION lesson_dynamic_sql.find_order_amount_or_null(
    p_order_id BIGINT
)
RETURNS NUMERIC
LANGUAGE plpgsql
AS $$
DECLARE
    v_amount NUMERIC;
BEGIN
    BEGIN
        EXECUTE
            'SELECT amount
               FROM lesson_dynamic_sql.orders
              WHERE order_id = $1'
        INTO STRICT v_amount
        USING p_order_id;

        RETURN v_amount;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            RETURN NULL;
    END;
END;
$$;
```

A multi-row error is still raised and not silently converted to NULL. This is a contract choice: "does not exist" is treated as a valid outcome; "multiple matches" is a violation.

### Do Not Catch WHEN OTHERS and Pretend Data Is Missing

If every exception is turned into NULL or 0, the application can mask permission errors, bad table names, schema drift, or invalid queries. Catch error types with specific semantics, log safely, and let the rest be handled at the transaction boundary.

## 25. Does EXECUTE Change FOUND?

An easy-to-miss PL/pgSQL detail: **`EXECUTE` does not modify the special `FOUND` variable** the way many static SQL statements in PL/pgSQL do.

Therefore, do not write:

```sql
EXECUTE v_sql USING p_value;
IF FOUND THEN
    -- Not guaranteed to reflect the status of the EXECUTE just run.
END IF;
```

Instead, after dynamic DML, use `GET DIAGNOSTICS ... ROW_COUNT`; with `EXECUTE ... INTO`, use `INTO STRICT` or check the result/semantics as required.

## 26. GET DIAGNOSTICS ROW_COUNT After EXECUTE

Example tenant-scoped UPDATE:

```sql
CREATE OR REPLACE FUNCTION lesson_dynamic_sql.cancel_new_orders(
    p_tenant_id BIGINT
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_affected BIGINT;
BEGIN
    EXECUTE
        'UPDATE lesson_dynamic_sql.orders
            SET status = $1
          WHERE tenant_id = $2
            AND status = $3'
    USING 'CANCELLED', p_tenant_id, 'NEW';

    GET DIAGNOSTICS v_affected = ROW_COUNT;
    RETURN v_affected;
END;
$$;
```

Calling within a lab transaction:

```sql
BEGIN;

SELECT lesson_dynamic_sql.cancel_new_orders(10);

SELECT status, count(*)
FROM lesson_dynamic_sql.orders
WHERE tenant_id = 10
GROUP BY status;

ROLLBACK;
```

### Why Roll Back?

So the lab does not alter data for subsequent examples. A function containing a dynamic UPDATE performs transactional modifications; `ROLLBACK` restores the original data.

`ROW_COUNT` is the number of rows processed by the most recent SQL statement per `GET DIAGNOSTICS`. Read it **immediately after EXECUTE**; another SQL statement executed in between can overwrite the diagnostic info.

## 27. EXECUTE with INSERT and RETURNING

Example inserting an order and returning its ID:

```sql
CREATE OR REPLACE FUNCTION lesson_dynamic_sql.insert_order_dynamic(
    p_tenant_id BIGINT,
    p_customer_id BIGINT,
    p_amount NUMERIC
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_order_id BIGINT;
BEGIN
    IF p_amount IS NULL OR p_amount < 0 THEN
        RAISE EXCEPTION 'Amount must be nonnegative';
    END IF;

    EXECUTE
        'INSERT INTO lesson_dynamic_sql.orders
             (tenant_id, customer_id, status, amount)
         VALUES ($1, $2, $3, $4)
         RETURNING order_id'
    INTO v_order_id
    USING p_tenant_id, p_customer_id, 'NEW', p_amount;

    RETURN v_order_id;
END;
$$;

BEGIN;
SELECT lesson_dynamic_sql.insert_order_dynamic(
    10, 104, 75000.00
);
ROLLBACK;
```

Because the SQL command is `INSERT ... RETURNING`, the output can be captured using `EXECUTE ... INTO`.

### Note on Multi-Row RETURNING

DML statements with `RETURNING` that produce multiple rows while trying to assign into a **single target** require careful handling; PL/pgSQL can raise an error when `INSERT/UPDATE/DELETE/MERGE ... RETURNING` returns multiple rows for a single `INTO`, even without writing `STRICT`. If you need all rows, use `RETURN QUERY EXECUTE` or another set-oriented design.

## 28. Conditional Dynamic DELETE

```sql
DO $$
DECLARE
    v_deleted BIGINT;
BEGIN
    EXECUTE
        'DELETE FROM lesson_dynamic_sql.orders
          WHERE tenant_id = $1
            AND status = $2'
    USING 10::bigint, 'CANCELLED'::text;

    GET DIAGNOSTICS v_deleted = ROW_COUNT;
    RAISE NOTICE 'Deleted rows: %', v_deleted;
END;
$$;
```

**Warning:** This block deletes real data in the active transaction. If you only want to test it:

```sql
BEGIN;
-- Run the DO block above here.
ROLLBACK;
```

In practice, deleting data must be backed by proper retention policies, permissions, auditing, and transactions. `USING` cannot stop a `DELETE` that is missing a `WHERE` clause or has an overly broad condition due to a mistake by the SQL author.

## 29. Dynamic MERGE with Input Data

On PostgreSQL versions that support `MERGE`, this optimizable statement can use bound values in appropriate positions via `EXECUTE ... USING`.

Concept:

```text
MERGE INTO target
USING (SELECT $1 AS id, $2 AS status) source
ON target.id = source.id
WHEN MATCHED THEN UPDATE...
WHEN NOT MATCHED THEN INSERT...
```

On versions or cases where `MERGE` is unsupported, use `INSERT ... ON CONFLICT` as appropriate. Do not concatenate values manually just because the statement is complex; use parameters and verify isolation/concurrency semantics.

A `MERGE` example should only be written once you have confirmed the PostgreSQL version and real table shape; the main examples in this lesson use SELECT/INSERT/UPDATE/DELETE so they can run standalone.

## 30. RETURN QUERY EXECUTE: Returning Multiple Rows

A single `EXECUTE ... INTO` normally fetches one row. For set-returning functions:

```sql
CREATE OR REPLACE FUNCTION lesson_dynamic_sql.orders_for_tenant(
    p_tenant_id BIGINT,
    p_status TEXT
)
RETURNS TABLE (
    order_id BIGINT,
    amount NUMERIC,
    created_at TIMESTAMPTZ
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_sql TEXT;
BEGIN
    v_sql :=
        'SELECT o.order_id, o.amount, o.created_at
           FROM lesson_dynamic_sql.orders AS o
          WHERE o.tenant_id = $1
            AND o.status = $2
          ORDER BY o.created_at DESC, o.order_id DESC';

    RETURN QUERY EXECUTE v_sql
    USING p_tenant_id, p_status;
END;
$$;

SELECT *
FROM lesson_dynamic_sql.orders_for_tenant(10, 'PAID');
```

### What Must Match

- `RETURNS TABLE` declares the **result columns and types**.
- The dynamic SELECT returns exactly **three columns**, in the right order and with compatible types.
- `RETURN QUERY EXECUTE` appends the rows to the function's result set.
- When no rows match, the result set can be empty.

`RETURN QUERY EXECUTE` is useful when the **source structure** varies while the output shape remains a fixed contract. If the output columns themselves also vary by input, SQL/JDBC applications will struggle to know the received shape; you would need a different API or the `record` type with a column definition list at call time.

## 31. Why Static SELECT Is Often Enough Instead of RETURN QUERY EXECUTE

The `orders_for_tenant` function just written has an entirely fixed SQL structure. It can be simplified using a `LANGUAGE sql` function or a static `RETURN QUERY SELECT ...`:

```sql
CREATE OR REPLACE FUNCTION lesson_dynamic_sql.orders_for_tenant_static(
    p_tenant_id BIGINT,
    p_status TEXT
)
RETURNS TABLE (
    order_id BIGINT,
    amount NUMERIC,
    created_at TIMESTAMPTZ
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    RETURN QUERY
    SELECT
        o.order_id,
        o.amount,
        o.created_at
    FROM lesson_dynamic_sql.orders AS o
    WHERE o.tenant_id = p_tenant_id
      AND o.status = p_status
    ORDER BY o.created_at DESC, o.order_id DESC;
END;
$$;
```

### Differences

- `RETURN QUERY SELECT`: static query, clear dependencies, plans managed by PL/pgSQL's mechanism.
- `RETURN QUERY EXECUTE`: query string built at runtime and planned on every invocation.

If there is no reason to change the SQL structure, there is no need for `EXECUTE`.

## 32. FOR ... IN EXECUTE: Iterating Row by Row

PL/pgSQL allows running a dynamic query and looping over its rows:

```sql
DO $$
DECLARE
    v_order RECORD;
    v_tenant_id BIGINT := 10;
BEGIN
    FOR v_order IN EXECUTE
        'SELECT order_id, status, amount
           FROM lesson_dynamic_sql.orders
          WHERE tenant_id = $1
          ORDER BY order_id'
        USING v_tenant_id
    LOOP
        RAISE NOTICE 'Order %, status %, amount %',
            v_order.order_id,
            v_order.status,
            v_order.amount;
    END LOOP;
END;
$$;
```

### When to Use It?

- Processing records dynamically selected using valid table/column names.
- Executing per-row PL/pgSQL logic when pure SQL cannot express it simply.
- Running small maintenance tasks with logging and validation.

However, a row-by-row loop is not the default way to update hundreds of thousands of records. A set-based SQL `UPDATE ... WHERE ...` usually reduces overhead and leverages the executor better.

## 33. FOR ... IN EXECUTE and FOUND

A `FOR ... IN EXECUTE` loop iterates over the rows from the query. After the loop finishes, `FOUND` follows loop semantics, unlike a standalone `EXECUTE` statement.

```sql
DO $$
DECLARE
    v_row RECORD;
BEGIN
    FOR v_row IN EXECUTE
        'SELECT order_id
           FROM lesson_dynamic_sql.orders
          WHERE tenant_id = $1'
        USING -1::bigint
    LOOP
        NULL; -- No rows in the lab.
    END LOOP;

    RAISE NOTICE 'Loop produced rows: %', FOUND;
END;
$$;
```

In this example, the loop body does not run, so `FOUND` is typically false after the loop.

### Compared to EXECUTE INTO

Do not extrapolate this rule to `EXECUTE ... INTO`: **the EXECUTE statement itself does not change FOUND**, so confirming results should rely on `STRICT`, output values, or appropriate diagnostics.

## 34. FOR record IN EXECUTE or RETURN QUERY EXECUTE?

| Goal | Suitable approach |
|---|---|
| Return the entire result set to the caller | `RETURN QUERY EXECUTE` |
| Process each row with PL/pgSQL | `FOR record IN EXECUTE ... LOOP` |
| Fetch a single value | `EXECUTE ... INTO` |
| Execute dynamic UPDATE and get row count | `EXECUTE ... USING` + `GET DIAGNOSTICS ROW_COUNT` |
| Execute DDL | `EXECUTE format(...)` |

If a set-based SELECT/UPDATE can replace a loop, prefer it unless sequential processing is genuinely required.

### When Using a Loop to Modify the Database

Think about transaction size, lock duration, exception behavior, and partial work on failure. A loop inside a function does not create a separate transaction per row.

## 35. RECORD and Dynamically Shaped Targets

`RECORD` in PL/pgSQL can receive a row whose structure is determined at runtime:

```sql
DO $$
DECLARE
    v_row RECORD;
BEGIN
    EXECUTE
        'SELECT order_id, status, amount
           FROM lesson_dynamic_sql.orders
          ORDER BY order_id
          LIMIT 1'
    INTO v_row;

    RAISE NOTICE 'Order = %, amount = %',
        v_row.order_id,
        v_row.amount;
END;
$$;
```

### Advantage

`RECORD` is flexible when the column list changes. However, an API returning an unstable structure is difficult to call from Java or other SQL queries.

### Risk

If the dynamic query does not return an `amount` column, accessing `v_row.amount` will fail at runtime. PL/pgSQL cannot validate all `RECORD` field names when the function is created.

When the interface returned to the application has a fixed shape, prefer typed variables or `RETURNS TABLE` with explicit aliases and casts.

## 36. Dynamic ORDER BY: Why Extra Care Is Required

An orders list screen allows:

- Sorting by `created_at`, `amount`, or `order_id`.
- Choosing `ASC` or `DESC`.
- Enforcing a row limit and tenant scope.

Wrong:

```sql
v_sql := 'SELECT ... ORDER BY ' ||
         p_sort_column || ' ' || p_direction;
```

If the inputs are client-controlled, this is **SQL fragment injection**. `USING` cannot bind column names or `ASC`/`DESC` keywords; you must **map inputs to a set of allowed values**.

## 37. Building Safe Dynamic ORDER BY

```sql
CREATE OR REPLACE FUNCTION lesson_dynamic_sql.search_orders(
    p_tenant_id BIGINT,
    p_sort_column TEXT DEFAULT 'created_at',
    p_direction TEXT DEFAULT 'DESC',
    p_limit INTEGER DEFAULT 20
)
RETURNS TABLE (
    order_id BIGINT,
    amount NUMERIC,
    created_at TIMESTAMPTZ
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_column TEXT;
    v_direction TEXT;
    v_sql TEXT;
BEGIN
    v_column := CASE p_sort_column
        WHEN 'amount' THEN 'amount'
        WHEN 'created_at' THEN 'created_at'
        WHEN 'order_id' THEN 'order_id'
        ELSE NULL
    END;

    IF v_column IS NULL THEN
        RAISE EXCEPTION 'Unsupported sort column: %',
            p_sort_column;
    END IF;

    IF p_direction IS NULL
       OR upper(p_direction) NOT IN ('ASC', 'DESC') THEN
        RAISE EXCEPTION 'Unsupported sort direction';
    END IF;
    v_direction := upper(p_direction);

    IF p_limit IS NULL OR p_limit < 1 OR p_limit > 100 THEN
        RAISE EXCEPTION 'Limit must be between 1 and 100';
    END IF;

    v_sql := format(
        'SELECT o.order_id, o.amount, o.created_at
           FROM lesson_dynamic_sql.orders AS o
          WHERE o.tenant_id = $1
          ORDER BY o.%I %s, o.order_id DESC
          LIMIT $2',
        v_column,
        v_direction
    );

    RETURN QUERY EXECUTE v_sql
    USING p_tenant_id, p_limit;
END;
$$;
```

### What Is Controlled Here?

- Sort column: `CASE` whitelist, then `%I`.
- Direction: `ASC`/`DESC` whitelist, then `%s`.
- Tenant: bound `$1` via `USING`.
- Limit: bound `$2` and constrained to 1–100.
- Table name: fixed using a schema-qualified name.

`ORDER BY ... order_id DESC` provides a tie-breaker when the primary sort column has duplicate values, keeping ordering deterministic.

## 38. Calling `search_orders` with Various Sort Orders

```sql
-- Default: created_at DESC
SELECT *
FROM lesson_dynamic_sql.search_orders(10);

-- Amount ascending
SELECT *
FROM lesson_dynamic_sql.search_orders(
    10,
    'amount',
    'ASC',
    10
);

-- ID descending
SELECT *
FROM lesson_dynamic_sql.search_orders(
    p_tenant_id => 10,
    p_sort_column => 'order_id',
    p_direction => 'DESC'
);
```

### Inputs That Must Be Rejected

```sql
-- Disallow column names not in the list:
-- SELECT * FROM lesson_dynamic_sql.search_orders(
--     10, 'customer_id', 'ASC', 10
-- );

-- Disallow SQL fragments supplied by the client:
-- SELECT * FROM lesson_dynamic_sql.search_orders(
--     10, 'amount', 'DESC NULLS LAST', 10
-- );
```

Do not turn these rejections into "retry with string concatenation"; expand the whitelist or add a newly designed sort mode with clear semantics.

## 39. Why Not Use `ORDER BY $1`?

A common mistake:

```sql
EXECUTE
    'SELECT order_id, amount
       FROM lesson_dynamic_sql.orders
      ORDER BY $1'
USING p_sort_column;
```

`$1` is a **constant text value on every row**, not a dynamic reference to a column named `p_sort_column`. Sorting by a constant value does not produce the intended ordering.

A column name is an **identifier**, so you must use `%I` and accept only choices from a whitelist. Never use `USING` to try to substitute an identifier.

## 40. CASE in ORDER BY Can Replace Dynamic SQL

If there are only two sort choices, a static query is sometimes sufficient:

```sql
SELECT order_id, amount, created_at
FROM lesson_dynamic_sql.orders
WHERE tenant_id = 10
ORDER BY
    CASE WHEN 'amount' = 'amount' THEN amount END ASC,
    order_id DESC;
```

The example above illustrates a fixed sort branch; inside a function, the first `'amount'` can be replaced with a parameter. However, if the columns have different types (such as numeric and timestamptz), a single `CASE` cannot arbitrarily return incompatible types, so separate expressions/branches are usually needed.

### When to Choose the Static Approach?

- Few variants and short SQL.
- Want to avoid replanning caused by EXECUTE.
- No need for a different SELECT structure.
- `ORDER BY` remains easy to verify.

### When Is Dynamic Better?

- Many column/direction variants with a clear whitelist.
- Static SQL using `CASE` becomes complex, hard to read, or degrades index plans.
- The planner needs a concrete `ORDER BY` expression to consider an index scan instead of sorting.

Always inspect `EXPLAIN` on realistic data rather than deciding purely on code length.

## 41. Using a Whitelist for Table Names

An API optionally reads current data or archived data:

```text
source = 'current' → lesson_dynamic_sql.orders
source = 'archive' → lesson_dynamic_sql.orders_archive
```

If the archive has not been created yet, the function should not run blindly. A controlled mapping:

```sql
v_table_name := CASE p_source
    WHEN 'current' THEN 'orders'
    WHEN 'archive' THEN 'orders_archive'
    ELSE NULL
END;

IF v_table_name IS NULL THEN
    RAISE EXCEPTION 'Unsupported source';
END IF;
```

Then:

```sql
v_sql := format(
    'SELECT count(*) FROM %I.%I WHERE tenant_id = $1',
    'lesson_dynamic_sql',
    v_table_name
);
```

**The whitelist restricts which tables can be accessed**, while `%I` ensures the name is quoted properly. Both solve different problems.

## 42. Schema Name, Table Name, and Case Sensitivity

PostgreSQL folds unquoted identifiers to lowercase according to its rules:

```sql
SELECT format('%I.%I', 'lesson_dynamic_sql', 'orders');
```

needs no quotes for simple names.

For names with uppercase letters or spaces:

```sql
SELECT format('%I.%I', 'Sales Data', 'Order Detail');
```

the result includes quotes for each identifier.

### Why Not Automatically Lowercase Every Input?

If the database already has quoted names with uppercase letters, lowercasing changes the identifier. It is best to use consistent naming conventions and draw object names from trusted metadata or whitelists, rather than accepting arbitrary user-supplied naming styles.

## 43. Using `regclass` When Justified

PostgreSQL has the `regclass` type to represent the OID of a relation. A `regclass` value is resolved via the object-name mechanism and formats safely for SQL:

```sql
SELECT 'lesson_dynamic_sql.orders'::regclass;
```

In some trusted maintenance procedures, passing a `p_relation regclass` parameter can be clearer than passing an arbitrary text table name.

### However, `regclass` Does Not Perform Authorization

A `regclass` indicates that a relation resolved; it **does not prove the caller has permission to read or modify it**. A `SECURITY DEFINER` routine accepting an arbitrary `regclass` can still cause a confused-deputy vulnerability by exercising the owner's privileges on an unauthorized object.

If you build SQL from `regclass`, you must still check:

- The schema containing the relation.
- The relation kind (table/view/partition...).
- ACLs/ownership.
- The set of permitted objects.
- Quoting and resolution against `search_path`.

Do not treat `regclass` as a "security shield" in place of an allowlist.

## 44. Dynamic DDL with format('%I')

A migration tool or admin routine sometimes needs to add a column whose name depends on configuration:

```sql
CREATE OR REPLACE PROCEDURE lesson_dynamic_sql.add_notes_column(
    p_table_name TEXT
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_table_name IS DISTINCT FROM 'orders' THEN
        RAISE EXCEPTION 'Only orders table is allowed';
    END IF;

    EXECUTE format(
        'ALTER TABLE %I.%I ADD COLUMN IF NOT EXISTS %I text',
        'lesson_dynamic_sql',
        p_table_name,
        'notes'
    );
END;
$$;
```

Invocation:

```sql
-- Run only if intentionally altering the lab table schema:
-- CALL lesson_dynamic_sql.add_notes_column('orders');
```

### Why Not Use USING for Column Names?

DDL requires identifiers in SQL syntax; bound parameters cannot substitute for them. Use `%I` for each name and whitelist permitted names and modes.

### Production Warning

`ALTER TABLE` can acquire heavy locks and impact performance. A DDL procedure does not automatically make a migration "online" or zero-downtime. You need concurrency, deployment, and rollback planning.

## 45. Dynamic CREATE INDEX

Sometimes a maintenance tool creates an index on a specified column. Example syntax:

```sql
DO $$
DECLARE
    v_index_name TEXT := 'ix_orders_amount_lab';
    v_table_name TEXT := 'orders';
    v_column_name TEXT := 'amount';
BEGIN
    EXECUTE format(
        'CREATE INDEX IF NOT EXISTS %I ON %I.%I (%I)',
        v_index_name,
        'lesson_dynamic_sql',
        v_table_name,
        v_column_name
    );
END;
$$;
```

Because the table/column names in the example are code-owned constants, `%I` builds valid syntax. If they come from input, whitelist them and verify permissions and table kind.

### Do Not Run `CREATE INDEX CONCURRENTLY` Inside a DO Block or Function

`CREATE INDEX CONCURRENTLY` cannot run inside a transaction block; a PL/pgSQL `DO` block or function is not an appropriate place to execute it. An external migration tool can send `CREATE INDEX CONCURRENTLY` as a top-level SQL command under the proper conditions.

Before creating an index in production, check existing indexes, write overhead, build time, locks, and disk/WAL impact.

## 46. Dynamic DDL and Column Data Types

Suppose a tool wants to create a new column with a user-specified type:

```text
type = text
type = numeric
type = timestamptz
```

Do not concatenate a raw string directly into:

```sql
format('ALTER TABLE ... ADD COLUMN data %s', p_type)
```

unless `p_type` has been **mapped to a valid type expression from a whitelist**.

Example:

```sql
v_type_sql := CASE p_type
    WHEN 'text' THEN 'text'
    WHEN 'money' THEN 'numeric(14,2)'
    WHEN 'timestamp' THEN 'timestamptz'
    ELSE NULL
END;

IF v_type_sql IS NULL THEN
    RAISE EXCEPTION 'Unsupported type';
END IF;
```

Then `%s` only inserts a **code-owned constant SQL type fragment**, never raw user input.

### General Principle

Keywords, operators, data types, `ORDER BY` directions, and expression structures must be selected from a **controlled input language**; you cannot just quote everything with `%I` and assume the SQL is valid.

## 47. DDL and Literal Values

For a utility statement that requires a constant value in SQL text, `USING` may not apply; use `%L` or `quote_nullable` when genuinely needed.

Example adding a comment to an allowed table:

```sql
DO $$
DECLARE
    v_comment TEXT := 'Lab data: O''Reilly examples';
BEGIN
    EXECUTE format(
        'COMMENT ON TABLE %I.%I IS %L',
        'lesson_dynamic_sql',
        'orders',
        v_comment
    );
END;
$$;
```

`COMMENT ON TABLE` is a utility statement, so the table name uses `%I.%I` and the comment uses a **quoted SQL literal** via `%L`.

### Why Not Use `%s` for the Comment?

If raw comment text is inserted directly, quotes or punctuation can break the SQL. `%L` creates a literal following quoting rules. In optimizable SELECT/DML statements where values can be bound, use `USING` instead of `%L`.

## 48. Dynamic CREATE TABLE Following a Naming Policy

A monthly archiving job may create a target table named by period:

```text
orders_2026_10
orders_2026_11
orders_2026_12
```

Never take an arbitrary raw `p_table_name` from the client. Construct the name from **validated values** such as year and month, then pass it through `%I`:

```sql
CREATE OR REPLACE PROCEDURE lesson_dynamic_sql.create_monthly_stage(
    p_year INTEGER,
    p_month INTEGER
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_table_name TEXT;
BEGIN
    IF p_year IS NULL OR p_year < 2000 OR p_year > 2100
       OR p_month IS NULL OR p_month < 1 OR p_month > 12 THEN
        RAISE EXCEPTION 'Invalid year/month';
    END IF;

    v_table_name := format(
        'orders_stage_%s_%s',
        p_year,
        lpad(p_month::text, 2, '0')
    );

    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %I.%I (
             stage_id bigint PRIMARY KEY,
             tenant_id bigint NOT NULL,
             amount numeric(14,2) NOT NULL
         )',
        'lesson_dynamic_sql',
        v_table_name
    );
END;
$$;
```

This illustrates safe table naming, **not a complete partitioning system**. If real partitioning is needed, use `PARTITION BY`, `ATTACH PARTITION`, bounds, constraints, and automation per PostgreSQL documentation; do not create unbounded standalone tables without a retention policy.

## 49. Dynamic SQL and Multi-Tenant Databases

Two common architectures:

**Shared table:**

```text
orders(tenant_id, order_id, ...)
```

This is typically a case where table-name dynamic SQL is **not needed**; static queries filtered by `tenant_id` with appropriate RLS and indexes work well.

**Schema per tenant:**

```text
tenant_a.orders
tenant_b.orders
```

Here, the schema name varies. However, a function taking `p_schema` from the client and running `format('%I.orders', p_schema)` does not provide authorization by itself.

### Safer Design

- Map an authenticated tenant to its schema in a trusted registry.
- Whitelist or look up schema ownership/metadata.
- Use `%I` in SQL to quote the schema name.
- Apply appropriate role permissions/RLS.
- Audit privileged queries.
- Do not rely solely on schema names to prevent cross-tenant access.

If all data resides in a shared table, dynamic schemas often only add complexity and security risk.

## 50. SECURITY INVOKER and SECURITY DEFINER

By default, routines use **`SECURITY INVOKER`**: privileges for data operations are checked against the caller under the applicable rules.

**`SECURITY DEFINER`** runs with the owner's privileges; it is sometimes needed for a restricted API, but is especially dangerous if the routine constructs dynamic SQL from user-chosen table or column names.

### Confused-Deputy Risk

Dangerous example:

```sql
-- Illustrative anti-pattern; do not create in the database:
-- CREATE FUNCTION privileged_count(table_name text)
-- RETURNS bigint SECURITY DEFINER AS $$
-- BEGIN
--   EXECUTE format('SELECT count(*) FROM %I', table_name);
-- END;
-- $$ LANGUAGE plpgsql;
```

If the owner has access to many tables, a caller can try to use the function as a backdoor to operate on data they normally cannot access.

### How to Design Safely

- Use `SECURITY DEFINER` only when there is a specific reason.
- Minimize the owner role's privileges.
- Validate/whitelist object names and permitted operations.
- Use schema-qualified names.
- Set a safe `search_path`.
- Protect `EXECUTE` privileges on the routine.
- Check whether table owners bypass RLS under PostgreSQL rules.

`%I` prevents parsing/injection flaws inside an identifier; **it does not prevent abuse of the owner's privileges**.

## 51. `search_path` in SECURITY DEFINER

An example of a more protective configuration:

```sql
-- Configuration template for privileged routines;
-- apply only after auditing the entire body:
-- CREATE FUNCTION admin.some_function(...)
-- RETURNS ...
-- LANGUAGE plpgsql
-- SECURITY DEFINER
-- SET search_path = pg_catalog, trusted_schema, pg_temp
-- AS $$ ... $$;
```

### Why Pay Attention to This?

Unqualified object names are resolved via `search_path`. If an untrusted schema is in the path and a caller can create objects there, a privileged routine risks resolving and invoking an object created by someone else.

Core principles:

- Schema-qualify critical tables and functions.
- Include only trusted schemas in the `search_path` of `SECURITY DEFINER` routines.
- Pay attention to `pg_temp` placement per current security recommendations.
- Never grant untrusted roles `CREATE` in schemas trusted by privileged routines.
- Restrict dynamic SQL strictly to the necessary objects.

### RLS Privileges

`SECURITY DEFINER` can change which role RLS applies to, and the table owner may bypass RLS depending on configuration; do not treat `WHERE tenant_id = $1` with a client-supplied tenant as complete access control.

## 52. Dynamic SQL Does Not Change Transaction Boundaries

`EXECUTE` runs the statement inside the active transaction of the function, procedure, or caller.

```sql
BEGIN;

SELECT lesson_dynamic_sql.cancel_new_orders(10);

SELECT status, count(*)
FROM lesson_dynamic_sql.orders
WHERE tenant_id = 10
GROUP BY status;

ROLLBACK;
```

Dynamic DML changes roll back with the transaction, just like static SQL.

### EXECUTE Is Not an Independent Transaction

Executing an SQL string via PL/pgSQL `EXECUTE` does not create its own transaction or auto-commit. PostgreSQL has specific transaction-control restrictions inside functions and procedures; `EXECUTE` alone does not bypass them.

### Transactional DDL

Many PostgreSQL DDL commands also obey transaction semantics, though there are exceptions and special conditions such as `CREATE INDEX CONCURRENTLY`. Do not assume "every DDL rolls back under all conditions" or "every DDL requires autocommit"; verify each command type.

## 53. Exception Handling and Rollback in PL/pgSQL

`EXECUTE` can raise:

- `undefined_table` if the object does not exist.
- `undefined_column` if the column is invalid.
- `insufficient_privilege` if the role lacks permissions.
- `syntax_error` if the command string has invalid syntax.
- `unique_violation`, `check_violation`, `foreign_key_violation` on invalid DML data.
- `deadlock_detected` or serialization failures under concurrency.

Example catching only a missing table:

```sql
DO $$
DECLARE
    v_count bigint;
BEGIN
    BEGIN
        EXECUTE
            'SELECT count(*) FROM lesson_dynamic_sql.nonexistent_table'
        INTO v_count;
    EXCEPTION
        WHEN undefined_table THEN
            RAISE NOTICE 'Table does not exist';
    END;
END;
$$;
```

### Do Not Catch Everything and Proceed Blindly

If you use `WHEN OTHERS THEN RETURN 0`, you can turn a security error or DB outage into "0 orders", corrupting metrics. Distinguish normal business outcomes from system failures.

An `EXCEPTION` block uses a subtransaction under PL/pgSQL rules to undo effects inside the failing block scope; you still need clear transaction boundaries and rollback policies in the application.

## 54. Retrieving SQLSTATE, SQLERRM, and Diagnostics on Error

```sql
DO $$
DECLARE
    v_state text;
    v_message text;
BEGIN
    BEGIN
        EXECUTE
            'SELECT * FROM lesson_dynamic_sql.table_does_not_exist';
    EXCEPTION
        WHEN OTHERS THEN
            GET STACKED DIAGNOSTICS
                v_state = RETURNED_SQLSTATE,
                v_message = MESSAGE_TEXT;

            RAISE NOTICE 'SQLSTATE = %, message = %',
                v_state, v_message;
    END;
END;
$$;
```

This example illustrates reading diagnostics; in production, do not catch `OTHERS` merely to hide failures. You can log in a controlled way and then `RAISE;` to propagate the exception to the caller if the error truly ought to fail the transaction.

### Distinguishing `ROW_COUNT` and `GET STACKED DIAGNOSTICS`

- `GET DIAGNOSTICS ... ROW_COUNT` gets the number of rows processed by the most recent statement.
- `GET STACKED DIAGNOSTICS` is used inside an exception handler to inspect the caught error.

Do not use `ROW_COUNT` to check how many rows "would have been found" when the query failed to execute.

## 55. Guarding Before Accessing Object Names

If an admin utility needs to check whether a table exists:

```sql
SELECT to_regclass('lesson_dynamic_sql.orders');
-- regclass or NULL if it cannot be resolved
```

In PL/pgSQL:

```sql
DO $$
DECLARE
    v_table_name text := 'orders';
    v_relation regclass;
BEGIN
    IF v_table_name IS DISTINCT FROM 'orders' THEN
        RAISE EXCEPTION 'Unsupported table';
    END IF;

    v_relation := to_regclass(
        format('%I.%I', 'lesson_dynamic_sql', v_table_name)
    );

    IF v_relation IS NULL THEN
        RAISE EXCEPTION 'Required relation missing';
    END IF;

    RAISE NOTICE 'Resolved relation: %', v_relation;
END;
$$;
```

### A Limitation

Checking existence and accessing afterward can be subject to concurrent schema changes (TOCTOU). Permissions, locking, and runtime exception handling are still required. `to_regclass` does not replace authorization.

## 56. Inspectable and Debuggable SQL Construction Paths

When a dynamic query is long, hold the SQL in a clear variable:

```sql
v_sql := format(
    'SELECT count(*)
       FROM %I.%I
      WHERE tenant_id = $1
        AND status = $2',
    'lesson_dynamic_sql',
    v_table_name
);

EXECUTE v_sql INTO v_count USING p_tenant_id, p_status;
```

This helps to:

- Read the SQL structure clearly.
- Observe the query shape in logs or diagnostics.
- Verify the exact number of placeholders.
- Avoid concatenating fragments from unclear sources.

### Do Not Log Sensitive Values

`USING` keeps bound values out of `v_sql`, letting you log the SQL template without automatically exposing inputs. However, parameter values may appear in other logs if they contain sensitive data; design appropriate logging and redaction policies.

Do not run `RAISE NOTICE 'SQL = %', v_sql` in production on dynamic SQL containing secret literals inserted via `%L` without controlling log access.

## 57. EXPLAIN with Dynamic SQL Statements

To understand the plan of dynamic SQL, capture the **final statement and representative parameter values** in a safe environment, then run `EXPLAIN` on an equivalent query:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COALESCE(SUM(amount), 0)
FROM lesson_dynamic_sql.orders
WHERE tenant_id = 10
  AND status = 'PAID';
```

### Why Representative Data Matters

- On six lab rows, a Seq Scan may be cheaper than an Index Scan.
- On a multi-million-row table, `tenant_id` and `status` have different selectivity.
- Partitioning and statistics affect the plan.
- Variations in `work_mem`, caching, and parallelism also matter.

**`EXPLAIN ANALYZE` actually executes the statement**, so never run it directly against a production dynamic UPDATE/DELETE without appropriate safeguards or rollback.

## 58. EXECUTE and the Planning Mechanism

In PL/pgSQL, static SQL statements can be prepared/planned and PostgreSQL chooses between generic and custom plans according to engine rules.

By contrast, `EXECUTE` dynamic SQL **does not cache plans in the same way for the command string inside PL/pgSQL**: the SQL string is parsed and planned on every execution.

### When Beneficial

A query whose optimal plan is sensitive to input values: tenant 1 has 100 records, while tenant 2 has millions of records. Replanning lets the planner choose a path tailored to the values of the current call.

### When Harmful

A simple query executed thousands of times with the same structure and only changing IDs can incur unnecessary parse/plan overhead.

### Avoid Absolute Assumptions

`EXECUTE` guarantees neither a faster plan nor always a slower one. It trades **planning overhead** for the ability to choose a plan based on the current command and values. Benchmark p95 latency, throughput, and CPU on your application workload.

## 59. When to Intentionally Use EXECUTE for Replanning

A static query in PL/pgSQL might settle on a generic plan that is suboptimal for heavily skewed data distributions. You can use dynamic `EXECUTE` with fixed SQL text and `USING`:

```sql
EXECUTE
    'SELECT count(*)
       FROM lesson_dynamic_sql.orders
      WHERE tenant_id = $1
        AND status = $2'
INTO v_count
USING p_tenant_id, p_status;
```

This is a case where dynamic SQL **may be intentional** even with unchanging structure, to force replanning on each invocation.

### Preconditions

- You have proven a generic/custom plan issue using real data and `EXPLAIN`.
- You have already reviewed statistics and index design.
- Planning cost does not outweigh execution gains.
- You do not build the SQL string by concatenating raw input.

Do not use `EXECUTE` as a default "optimization trick" for every SELECT.

## 60. Parameter Types and Implicit Casts

Values bound via `USING` carry concrete PostgreSQL types. The dynamic query's parser infers or checks the types of `$1`/`$2` in context:

```sql
DO $$
DECLARE
    v_number numeric;
BEGIN
    EXECUTE 'SELECT $1::numeric * $2::numeric'
    INTO v_number
    USING 12.5, 2;

    RAISE NOTICE 'Result = %', v_number;
END;
$$;
```

### Why Explicit Casts Sometimes Help

- Ensures the right operator/function overload is chosen.
- Prevents invalid implicit casts from text to numeric.
- Helps when `NULL` makes type inference ambiguous.
- Makes the input/output contract clearer.

However, do not blindly cast arbitrary user text to numeric assuming it is always valid; validation is still needed.

## 61. NULL and WHERE Conditions

This query:

```sql
EXECUTE
    'SELECT count(*)
       FROM lesson_dynamic_sql.orders
      WHERE status = $1'
INTO v_count
USING NULL::text;
```

cannot find rows where `status` is NULL using `= NULL`, because SQL uses three-valued logic. Since the lab's `status` column is `NOT NULL`, the count is 0.

If business logic needs to treat two NULLs as equal, you can use:

```sql
WHERE some_nullable_column IS NOT DISTINCT FROM $1
```

in the corresponding dynamic SQL.

### `%L` Does Not Fix NULL Semantics Either

`format('WHERE x = %L', NULL)` produces `WHERE x = NULL`, which still fails to match under equality. Safe quoting and SQL NULL logic are two separate concerns.

## 62. Building Dynamic Filters with Multiple Optional Conditions

This is a common requirement: optionally filter by status, minimum amount, and maximum amount. Dynamic SQL is **not needed** in every case:

```sql
SELECT order_id, amount
FROM lesson_dynamic_sql.orders
WHERE tenant_id = 10
  AND ('PAID'::text IS NULL OR status = 'PAID')
  AND (NULL::numeric IS NULL OR amount >= NULL::numeric)
  AND (1000000::numeric IS NULL OR amount <= 1000000::numeric);
```

In static SQL, this is the optional-predicate pattern `p IS NULL OR ...`. It is easy to write, though it can affect selectivity and planning when many predicates are combined.

### If You Want Minimal Query Structure Based on Inputs

You can construct a dynamic `WHERE` containing only the enabled conditions, while **never embedding values directly into the string**:

```text
base: WHERE tenant_id = $1
if status present: AND status = $2
if min present:    AND amount >= $3
```

In an actual implementation, you must keep placeholder numbering and the `USING` list consistent. If there are only a few combinations, consider `IF` branches with static SQL or a handful of predefined `EXECUTE` statements; avoid building a fragile custom query-builder string just for premature optimization.

## 63. A Function That Picks a Column While Returning a Stable Type

Sometimes an API wants to read one of three fields—`status`, `amount`, or `customer_id`—for an order. Those columns have different underlying types, so pick a **stable return type** if the function must be easy to call from JDBC.

```sql
CREATE OR REPLACE FUNCTION lesson_dynamic_sql.order_field_text(
    p_tenant_id BIGINT,
    p_order_id BIGINT,
    p_field TEXT
)
RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
    v_column TEXT;
    v_value TEXT;
BEGIN
    v_column := CASE p_field
        WHEN 'status' THEN 'status'
        WHEN 'amount' THEN 'amount'
        WHEN 'customer_id' THEN 'customer_id'
        ELSE NULL
    END;

    IF v_column IS NULL THEN
        RAISE EXCEPTION 'Unsupported field';
    END IF;

    EXECUTE format(
        'SELECT (o.%I)::text
           FROM lesson_dynamic_sql.orders AS o
          WHERE o.tenant_id = $1
            AND o.order_id = $2',
        v_column
    )
    INTO v_value
    USING p_tenant_id, p_order_id;

    RETURN v_value;
END;
$$;

SELECT lesson_dynamic_sql.order_field_text(
    10, 1, 'status'
);
```

### Why Return `text`?

Because `status` is `text`, `amount` is `numeric`, and `customer_id` is `bigint`, this function provides a **common display representation** for all three. However, if the caller needs numeric addition or arithmetic, returning `text` is no longer ideal; use dedicated typed APIs instead.

### Security Note

Whitelisting columns also prevents callers from requesting fields outside the API contract. `%I` quotes a column safely, but does not decide which fields are allowed to be exposed.

## 64. RETURN QUERY EXECUTE with Controlled Source Tables

If you need to query across several tables sharing a schema:

```sql
CREATE OR REPLACE FUNCTION lesson_dynamic_sql.read_order_source(
    p_source TEXT,
    p_tenant_id BIGINT
)
RETURNS TABLE (
    order_id BIGINT,
    status TEXT,
    amount NUMERIC
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_table TEXT;
    v_sql TEXT;
BEGIN
    v_table := CASE p_source
        WHEN 'current' THEN 'orders'
        ELSE NULL
    END;

    IF v_table IS NULL THEN
        RAISE EXCEPTION 'Unsupported source';
    END IF;

    v_sql := format(
        'SELECT o.order_id, o.status, o.amount
           FROM %I.%I AS o
          WHERE o.tenant_id = $1
          ORDER BY o.order_id',
        'lesson_dynamic_sql',
        v_table
    );

    RETURN QUERY EXECUTE v_sql USING p_tenant_id;
END;
$$;

SELECT *
FROM lesson_dynamic_sql.read_order_source('current', 10);
```

Later, if an `orders_archive` table exists with the same column contract, you can add the `archive` source to the mapping. Make sure the table exists and that permissions, column types, and data state align. Never let callers pass arbitrary unrestricted table names.

## 65. Choosing Operators Dynamically: Never Insert Raw Input

Suppose a user wants to filter `amount`:

```text
mode = gt → >
mode = ge → >=
mode = lt → <
mode = le → <=
```

A safe approach is mapping:

```sql
v_operator := CASE p_mode
    WHEN 'gt' THEN '>'
    WHEN 'ge' THEN '>='
    WHEN 'lt' THEN '<'
    WHEN 'le' THEN '<='
    ELSE NULL
END;

IF v_operator IS NULL THEN
    RAISE EXCEPTION 'Unsupported comparison mode';
END IF;

v_sql := format(
    'SELECT count(*) FROM lesson_dynamic_sql.orders
      WHERE tenant_id = $1 AND amount %s $2',
    v_operator
);

EXECUTE v_sql INTO v_count
USING p_tenant_id, p_threshold;
```

The code above is an **illustrative function body snippet** using variables declared outside, not a standalone executable statement.

### Why Use `%s` Here?

`>` or `>=` are **SQL operators**, not identifiers or data values. `%s` is safe here solely because `v_operator` is selected from code-owned constants.

Never allow `p_mode` to be raw SQL such as `'OR true'` and insert it directly via `%s`.

## 66. Dynamic WHERE and Array Filters

If a user wants to filter by multiple statuses, there is no need to build a string like:

```text
status IN ('PAID','NEW','CANCELLED')
```

by concatenating literals.

Use an array parameter:

```sql
DO $$
DECLARE
    v_count BIGINT;
    v_statuses TEXT[] := ARRAY['PAID', 'NEW'];
BEGIN
    EXECUTE
        'SELECT count(*)
           FROM lesson_dynamic_sql.orders
          WHERE tenant_id = $1
            AND status = ANY($2)'
    INTO v_count
    USING 10::bigint, v_statuses;

    RAISE NOTICE 'Matches: %', v_count;
END;
$$;
```

`ANY($2)` passes a list of values with an explicit `text[]` type. Do not write `format('status IN (%s)', p_statuses)`, because formatting an array as text does not automatically produce a valid SQL literal list and creates risks if concatenated without control.

### Notes on NULL and Empty Arrays

- An empty array matches zero rows with `= ANY`.
- An array containing `NULL` can affect three-valued logic.
- A completely `NULL` array differs from an empty array.

The application must define the semantics of "no status selected": return all rows, return none, or raise an error.

## 67. Dynamic LIMIT and OFFSET Are Also Data Values

`LIMIT` and `OFFSET` are not identifiers. If the query supports placeholders, use `USING`:

```sql
EXECUTE
    'SELECT order_id, amount
       FROM lesson_dynamic_sql.orders
      WHERE tenant_id = $1
      ORDER BY order_id
      LIMIT $2 OFFSET $3'
USING p_tenant_id, p_limit, p_offset;
```

This is a statement snippet inside PL/pgSQL; to process the rows, use `FOR ... IN EXECUTE` or `RETURN QUERY EXECUTE` instead of calling `EXECUTE` and discarding the result.

### Validating Bounds

`p_limit` should have an upper bound, such as 1–100 or per API policy. `p_offset` must be non-negative and not excessively large for your SLA. On large tables, deep pagination is costly; consider keyset pagination.

Passing `LIMIT` via `USING` does not automatically protect against a request asking for millions of rows unless the application caps the value.

## 68. Dynamic SQL with Table Names Matching Keywords

Suppose a table named `"Order"` contains uppercase letters and matches an SQL-parser keyword. Never guess how to add quotes manually:

```sql
SELECT format(
    'SELECT count(*) FROM %I.%I',
    'lesson_dynamic_sql',
    'Order'
);
```

`%I` quotes as needed to produce `"Order"`.

### Quoting Is Not "Escaping Whole SQL"

Many developers get into the habit of putting double quotes around the entire string `schema.table.column`:

```text
"schema.table.column"
```

That is **a single identifier**, not three qualified parts. Separate each identifier with `%I.%I.%I` when the structure requires it.

## 69. Checking Output Structure and Schema Drift

If a dynamic query returns:

```sql
SELECT order_id, amount, created_at ...
```

while the function declares:

```sql
RETURNS TABLE (
    order_id integer,
    amount text,
    created_at date
)
```

PostgreSQL will raise an error for incompatible return structure rather than silently coercing arbitrary values into any type just because the SQL text was assembled at runtime.

### How to Handle It

- Write output columns and types explicitly.
- Use intentional casts and aliases.
- When reading multiple sources, require them to adhere to a **data contract**.
- If the schema changes, migrations must update functions and clients together.
- Do not use `SELECT *` on tables with varying schemas while expecting `RETURNS TABLE` to stay stable.

Dynamic SQL defers certain errors to runtime; it does not bypass PostgreSQL's type system.

## 70. Batch Operations: Prefer Set-Based Statements

Suppose you need to mark all `NEW` orders as `CANCELLED` for a tenant. A single dynamic UPDATE:

```sql
EXECUTE
    'UPDATE lesson_dynamic_sql.orders
        SET status = $1
      WHERE tenant_id = $2
        AND status = $3'
USING 'CANCELLED', p_tenant_id, 'NEW';
```

is usually far better than:

```text
FOR each order:
  EXECUTE UPDATE by order_id
```

because a loop incurs repeated parse/plan/execution cycles and can prolong transactions and locks.

### When Is a Loop Still Reasonable?

When each row requires non-SQL logic hard to express set-based, needs per-row exception handling, or needs controlled batching. Even then, you must manage lock ordering, retries, and transaction scope.

## 71. Dynamic SQL and Multi-Tenant Data Access Control

A function:

```sql
CREATE FUNCTION read_any_table(
    p_table text,
    p_tenant_id bigint
) ...
```

if run as `SECURITY DEFINER` and allowing users to pick any table can become a data exposure path.

To design safely:

1. Do not accept arbitrary schema/table names if the API only needs two known sources.
2. Map source keys to a trusted list of table names.
3. Schema-qualify identifiers using `%I.%I`.
4. Authenticate/authorize the tenant on the backend or via RLS.
5. Do not grant `EXECUTE` privileges more broadly than required.
6. Prevent attackers from creating objects in `search_path` that could be invoked under the owner's privileges.
7. Audit role ownership and RLS bypass behavior.

A syntactically safe SQL statement can still violate authorization if the routine is over-privileged.

## 72. JDBC: Binding Parameters into a PL/pgSQL Function

A Java application does not need to build dynamic SQL on the client just because the database function uses dynamic SQL internally. Call the function through a prepared statement:

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class OrderReports {
    public static BigDecimal total(
            Connection conn,
            long authorizedTenantId,
            String status
    ) throws SQLException {
        String sql = """
            SELECT lesson_dynamic_sql.total_by_table(
                'orders',
                ?,
                ?
            )
            """;

        try (PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setLong(1, authorizedTenantId);
            ps.setString(2, status);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException(
                        "Expected one aggregate row"
                    );
                }
                return rs.getBigDecimal(1);
            }
        }
    }
}
```

### Key Takeaways

- Java binds **values** with JDBC `?` placeholders.
- The PL/pgSQL function builds the table reference using `format('%I')` and passes tenant/status via `USING`.
- `authorizedTenantId` must come from verified access control, not from an arbitrary request parameter.
- JDBC does not need to know the function's internal SQL command string.

Still, the backend must ensure the function does not allow choosing unauthorized tables.

## 73. JDBC: Dynamic ORDER BY via a Controlled API

You can call `search_orders`:

```java
String sql = """
    SELECT order_id, amount, created_at
    FROM lesson_dynamic_sql.search_orders(?, ?, ?, ?)
    """;

try (PreparedStatement ps = conn.prepareStatement(sql)) {
    ps.setLong(1, authorizedTenantId);
    ps.setString(2, sortColumn);
    ps.setString(3, sortDirection);
    ps.setInt(4, Math.min(Math.max(pageSize, 1), 100));

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong("order_id");
            BigDecimal amount = rs.getBigDecimal("amount");
            java.time.OffsetDateTime created =
                rs.getObject(
                    "created_at",
                    java.time.OffsetDateTime.class
                );
            // Map row to DTO.
        }
    }
}
```

This snippet is a skeleton; it assumes `conn`, `authorizedTenantId`, `sortColumn`, `sortDirection`, `pageSize`, and a driver supporting appropriate timestamp mapping.

### Why Validate in the Database Too?

The frontend may restrict `sortColumn` via a dropdown, but the API can still be called directly. The `search_orders` function enforces a whitelist and maximum `LIMIT`, so it does not rely solely on the UI.

### Avoid Abusing a Generic Search API

Do not let the application send a string like `ORDER BY foo DESC; ...` as a parameter. Pass **structured choice values** (a column enum and a direction enum) for the backend/database to map.

## 74. Spring/JdbcTemplate

A Spring service can call the function through `JdbcTemplate`:

```java
String sql = """
    SELECT order_id, amount, created_at
    FROM lesson_dynamic_sql.search_orders(?, ?, ?, ?)
    """;

var results = jdbcTemplate.query(
    sql,
    (rs, rowNum) -> new OrderSummary(
        rs.getLong("order_id"),
        rs.getBigDecimal("amount"),
        rs.getObject(
            "created_at",
            java.time.OffsetDateTime.class
        )
    ),
    authorizedTenantId,
    sortColumn,
    sortDirection,
    20
);
```

This assumes `OrderSummary` and `JdbcTemplate` already exist. The application should establish clear transaction boundaries for data-modifying routines and map SQLSTATE codes to appropriate API errors.

If Spring calls a DML procedure via `CALL`, consider how the transaction manager interacts with it; PL/pgSQL `EXECUTE` inside a procedure does not create a separate transaction on its own.

## 75. SQLSTATE and Error Classification in Java

Dynamic SQL errors can be surfaced to the client via `SQLException.getSQLState()`:

```java
try {
    // Call function/procedure containing dynamic SQL.
} catch (SQLException ex) {
    String state = ex.getSQLState();

    if ("42P01".equals(state)) {
        // undefined_table: schema/contract error,
        // should not be treated as "0 results".
    } else if ("42501".equals(state)) {
        // insufficient_privilege:
        // privilege error that needs security handling.
    } else if ("40P01".equals(state)) {
        // deadlock_detected:
        // may retry the entire transaction per policy.
    } else {
        throw ex;
    }
}
```

This is a classification example. In a real application, never catch and discard an exception without returning an error or rolling back as appropriate. Transaction errors such as serialization failures or deadlocks generally require retrying the **entire unit of transaction**, not blindly re-running one statement.

### Do Not Expose Internal SQL Text

Database exception messages can reveal schema/table names or data. Public APIs should return appropriate error codes/details rather than exposing raw SQL command strings and stack traces to end users.

## 76. Protecting Against Heavy Queries Even After Injection Prevention

A dynamic SQL query with a perfect whitelist can still run very expensively if:

- A user requests 100 million rows without a `LIMIT`.
- They sort on an unindexed column without sufficient filtering.
- They run `count(*)` repeatedly on a huge table.
- They query a large tenant during peak hours.
- A function runs row by row instead of set-based.

Countermeasures:

- Cap page sizes and allowable sort/filter options.
- Enforce timeouts and query budgets.
- Review indexes and statistics.
- Apply rate limiting.
- Benchmark on representative data.
- Monitor temp I/O, buffer reads, and concurrency.

`USING` protects syntax and values; **it does not enforce resource quotas**.

## 77. Observing Dynamic SQL in Real Environments

Metrics and signals to track:

| Signal | Investigation hint |
|---|---|
| Rising `42P01` error rate | Table naming, migration timing, or schema drift |
| `42703` errors | Column no longer exists |
| `42501` errors | Role, `GRANT`, `search_path`, or `SECURITY DEFINER` |
| High runtime | Plan, input selectivity, indexes, and sorting |
| Many distinct query shapes | SQL structure may be varying unnecessarily |
| Rising planning CPU | `EXECUTE` replanning too frequently |
| Lock waits | Dynamic UPDATE/DDL holding locks too long |
| Temp reads/writes | Sort/hash spills in dynamic queries |

### Logging

Log query shapes/fingerprints, routine names, validated tenant scopes, and elapsed times. Avoid logging sensitive raw parameters, secrets, or entire user-supplied SQL literals.

`pg_stat_statements` can help observe statement patterns in environments where the extension is installed and configured, though it does not replace reading the execution plan for a specific case.

## 78. When to Use Migration Tools Instead of Dynamic DDL

If a schema change is known at release time, prefer **versioned migrations**:

```sql
ALTER TABLE lesson_dynamic_sql.orders
ADD COLUMN IF NOT EXISTS source_channel TEXT;
```

Instead of creating an admin function that accepts table/column/type names and runs `EXECUTE format(...)`.

### Benefits of Migrations

- Review DDL before deployment.
- Version tracking and rollback control.
- Assessing locks, index sizes, and backfills.
- Separating migration privileges from runtime application privileges.
- Avoiding giving APIs permission to alter schemas arbitrarily.

Dynamic DDL fits when you genuinely must generate objects whose **names or structures vary with data** under strict governance. Never use it simply to avoid writing migration scripts.

## 79. Case Study: Reporting Across Multiple Tables with Identical Structure

A reporting service has two sources:

```text
orders_current
orders_archive
```

If both tables share the `tenant_id`, `amount`, and `status` columns, a function selecting the source via a whitelist can use:

```text
source 'current' → table current
source 'archive' → table archive
```

SQL structure:

```sql
v_sql := format(
    'SELECT COALESCE(SUM(amount), 0)
       FROM %I.%I
      WHERE tenant_id = $1 AND status = $2',
    v_schema,
    v_table
);

EXECUTE v_sql INTO v_total
USING p_tenant_id, p_status;
```

This is a PL/pgSQL body snippet, not a standalone function. `v_schema` and `v_table` must come from a trusted mapping, and the caller must have privileges on the respective sources.

### Is Dynamic SQL Always Necessary?

If both tables share the same structure and you need to query both, a `UNION ALL` view may allow the application to use static SQL. If sources are partitioned by time, PostgreSQL partition pruning can be a better solution than manual table selection.

Only use dynamic SQL when the **benefits of runtime structural selection** outweigh complexity, planning, and permission costs.

## 80. Case Study: Sorting by User-Selected Column

Requirements:

- Client selects `amount`, `created_at`, or `order_id`.
- Client selects `ASC` or `DESC`.
- Maximum 100 rows.
- Can only view its own tenant.

The `search_orders` function above satisfies this by:

1. Whitelisting column names.
2. Whitelisting sort directions.
3. Using `format('... %I %s ...')` for the structural parts.
4. Using `USING p_tenant_id, p_limit` for values.
5. Using a stable `ORDER BY` with a tie-breaker.

### Production Additions

- Tenant authorization from session/roles.
- Allowed status filters.
- Mapping sort fields to supporting indexes.
- Appropriate pagination (`OFFSET` or keyset).
- Testing SQL injection, NULLs, and invalid values.
- Measuring throughput and p95 latency per sort column.

An injection-safe function can still perform poorly as an API if every newly enabled sort leads to a full scan and disk sort.

## 81. Case Study: Admin Tool Choosing a Column for Statistics

An admin tool needs to compute `count(distinct ...)` on a selected column:

```sql
CREATE OR REPLACE FUNCTION lesson_dynamic_sql.distinct_count(
    p_column TEXT
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_column TEXT;
    v_count BIGINT;
BEGIN
    v_column := CASE p_column
        WHEN 'tenant_id' THEN 'tenant_id'
        WHEN 'customer_id' THEN 'customer_id'
        WHEN 'status' THEN 'status'
        ELSE NULL
    END;

    IF v_column IS NULL THEN
        RAISE EXCEPTION 'Unsupported column';
    END IF;

    EXECUTE format(
        'SELECT count(DISTINCT %I)
           FROM lesson_dynamic_sql.orders',
        v_column
    )
    INTO v_count;

    RETURN v_count;
END;
$$;
```

### Security Note

The function fixes the `orders` table, whitelists columns, and returns only an aggregate. Still, aggregates can leak information depending on data and scope; when exposed to multi-tenant users, add `tenant_id = $1` and authorization. **Returning only a count does not automatically make a query privacy-safe.**

## 82. Case Study: Table-Per-Tenant Is an Architectural Decision

A system sometimes chooses:

```text
orders_tenant_10
orders_tenant_20
orders_tenant_30
```

Constructing table names via:

```sql
format('orders_tenant_%s', p_tenant_id)
```

still requires:

- Validating the tenant ID and verifying a real mapping.
- Using `%I` when treating the name as an identifier.
- Managing synchronized migrations across tables.
- Keeping indexes and constraints identical.
- Bounding relation counts to avoid catalog bloat.
- Enforcing role isolation and permissions.

Do not assume "one table per tenant" is inherently safer than a shared table with RLS. PostgreSQL partitioning, shared-schema multi-tenancy, and schema-per-tenant each have trade-offs; dynamic SQL is merely an implementation tool for the chosen architecture.

## 83. Common Mistakes

**"Using EXECUTE for every SELECT makes it faster."** False. PL/pgSQL `EXECUTE` plans every time and incurs planning overhead.

**"PL/pgSQL EXECUTE is SQL PREPARE/EXECUTE."** False. The two mechanisms have different syntax and plan-caching behavior.

**"USING can bind table and column names."** False. It passes data values, not identifiers.

**"ORDER BY $1 sorts by the passed column."** False. `$1` is a value, not a column reference.

**"%I and %L work the same way."** False. `%I` quotes identifiers; `%L` quotes literals.

**"%s is always safe because it uses format()."** False. `%s` inserts a raw string and can introduce injection.

**"format('%I', 'schema.table') produces schema.table."** False. It produces a single identifier containing a dot; use `%I.%I`.

**"format('%I', input) proves the user is allowed to access the table."** False. Quoting and authorization are separate concerns.

**"format('%L', NULL) automatically makes WHERE x = NULL evaluate to true."** False. SQL `NULL` equality follows three-valued logic.

**"quote_literal(NULL) always concatenates safely."** False. A strict `NULL` return can turn the entire concatenated expression into `NULL`; use `quote_nullable` when a literal is needed.

**"SELECT ... INTO var goes inside the dynamic SQL string."** False. `INTO` for PL/pgSQL `EXECUTE` must sit outside the command string.

**"EXECUTE INTO always enforces exactly one row."** False. Use `STRICT` when you require exactly one row.

**"EXECUTE automatically updates FOUND."** False. Use `GET DIAGNOSTICS ROW_COUNT` or other appropriate checks.

**"INSERT RETURNING INTO silently ignores arbitrary extra rows."** Do not assume that; DML `RETURNING` multiple rows into a single target can raise an error.

**"RETURN QUERY EXECUTE returns only one row."** False. It appends multiple rows for a set-returning function.

**"FOR IN EXECUTE is always better than a set-based UPDATE."** False. Row-by-row loops add overhead and extend lock duration.

**"Dynamic SQL can return any column structure and RETURNS TABLE will coerce it automatically."** False. PostgreSQL still validates the return type.

**"CREATE INDEX CONCURRENTLY runs inside a PL/pgSQL DO block."** False. That command cannot be run inside an active transaction block.

**"DDL via EXECUTE is automatically online."** False. DDL still carries locking and deployment trade-offs.

**"SECURITY DEFINER + %I is completely safe."** False. Owner privileges, `search_path`, allowlists, RLS, and input validation still matter.

**"regclass proves permission to access the relation."** False. It helps resolve an object; it does not replace ACL checks.

**"An undefined_table error always means 0 rows."** False. It is a schema/runtime error that must be handled explicitly.

**"USING replaces validation on LIMIT and filters."** False. Bound values can still produce an overly broad query.

**"Dynamic SQL must always log all values for debugging."** Not by default; sensitive data in logs must be protected.

**"A query that runs fast on six lab rows represents production."** False. Representative data volume and distribution are required.

## 84. Dynamic SQL Design Checklist

Before shipping a dynamic SQL routine to production, ask yourself:

1. Can static SQL be used instead?
2. Which **structural** part genuinely needs to change at runtime?
3. Are all identifiers quoted with `%I` component by component?
4. Are all data values bound using `USING`?
5. Is `%s` ever used with untrusted raw data?
6. Are SQL keywords, operators, and type fragments whitelisted?
7. Are source tables and columns mapped from an allowed list?
8. Does tenant/authorization data come from a trusted source?
9. Does the function use `SECURITY DEFINER`, and are its owner and `search_path` safe?
10. Do you need one row, multiple rows, or a row count?
11. Are you using `INTO STRICT`, `RETURN QUERY EXECUTE`, `FOR IN EXECUTE`, or `GET DIAGNOSTICS` correctly?
12. Are `NULL` and zero-row cases handled per business rules?
13. Is a stable return-column and typed contract guaranteed?
14. Are query cost, `LIMIT`, and execution time bounded?
15. Have plans and latency been benchmarked on both very common and very rare values?
16. Are exceptions and rollbacks handled properly rather than hidden?
17. Has DDL been reviewed for locks, privileges, and rollback feasibility?
18. Have schema/index changes and JDBC/Spring callers been tested?

This is a **design checklist for using dynamic SQL**, not a substitute for an independent content QA pass in documentation production.

## 85. Safe Workflow for Constructing Dynamic SQL

### Step 1 — State the Requirement

Example: "Allow sorting the order list by one of three columns, capped at 100 rows."

### Step 2 — Separate Structure from Values

**Structure:** sort column, sort direction.

**Values:** tenant ID, `LIMIT`, status filter.

### Step 3 — Map Structure

Use `CASE`/whitelists to determine the exact permitted SQL identifiers and keywords; never accept raw SQL strings.

### Step 4 — Build SQL with `format`

`%I` for column/table/schema names, `%s` for validated keywords.

### Step 5 — Bind Data with `USING`

`$1`, `$2` matching typed values; apply casts and validation where needed.

### Step 6 — Choose How to Receive Results

`INTO`/`STRICT`, `RETURN QUERY EXECUTE`, `FOR ... IN EXECUTE`, or `ROW_COUNT`.

### Step 7 — Enforce Access Control

Schema-qualified names, safe role/`search_path`, tenant scope, and `EXECUTE` privileges.

### Step 8 — Check Runtime Characteristics

Plans, indexes, sorts, buffers, and WAL/locks for DML/DDL.

### Step 9 — Test Edge Cases

Missing/`NULL`, invalid column names, keywords, Unicode, quoting, no rows, multiple rows, and overly broad queries.

### Step 10 — Deploy with Observability

Record error classes and safe query shapes, monitor p95 latency, permissions, and migrations.

## 86. Practice Exercises

### Exercise 1 — Static or Dynamic SQL?

A function always reads `lesson_dynamic_sql.orders` and filters by `tenant_id`. Write a static SQL version. Explain why `EXECUTE` is unnecessary.

### Exercise 2 — Basic PL/pgSQL EXECUTE

Write a `DO` block using `EXECUTE 'SELECT $1 + $2' INTO v_result USING 7,5`. Print the result.

### Exercise 3 — Distinguishing the Two EXECUTEs

Compare PL/pgSQL `EXECUTE command-string USING ...` with SQL `PREPARE ...; EXECUTE prepared_name(...)`. How do their planning mechanisms differ?

### Exercise 4 — USING Two Values

Count orders by tenant and status using dynamic SELECT with `$1`, `$2`. Do not concatenate inputs directly into the SQL string.

### Exercise 5 — `%I` for Table Names

Construct `SELECT count(*) FROM lesson_dynamic_sql.orders` using `format('%I.%I', ...)`. Try a table name containing spaces.

### Exercise 6 — Dots Inside an Identifier

Compare `format('%I', 'lesson_dynamic_sql.orders')` with `format('%I.%I', 'lesson_dynamic_sql', 'orders')`. Why is the first result wrong when you want a qualified table?

### Exercise 7 — `%L` and Single Quotes

Construct `SELECT 'O''Reilly'` using `format('%L', value)`. Observe how PostgreSQL escapes the single quote.

### Exercise 8 — `%s` Only for Validated Data

Build a dynamic `ORDER BY` direction using an `ASC`/`DESC` whitelist. Why must you never insert `p_direction` directly from the API?

### Exercise 9 — `quote_ident` and `format`

Write two ways to generate SQL selecting the `"Order Date"` column from the `"Sales Report"` table. Which is easier to read?

### Exercise 10 — `quote_nullable`

Compare `quote_literal(NULL)` and `quote_nullable(NULL)` when concatenating SQL strings. Why is `%L` convenient for nullable literals?

### Exercise 11 — Do Not Bind Identifiers with USING

Explain why `EXECUTE 'SELECT count(*) FROM $1' USING 'orders'` fails. Rewrite it using `%I` and a whitelist.

### Exercise 12 — Do Not Bind ORDER BY Columns

Explain why `ORDER BY $1` does not sort by the column name passed as a parameter. Write a version using `%I`.

### Exercise 13 — EXECUTE INTO

Write a dynamic SELECT fetching `amount` by order ID into a numeric variable. What is the result when no row is found?

### Exercise 14 — INTO STRICT

Write a function finding `amount` that requires exactly one row. Test a nonexistent ID and a non-unique query returning multiple rows. Observe the corresponding SQLSTATEs.

### Exercise 15 — STRICT and Aggregates

Why does `SELECT count(*)` return one row even when the table has no matching records? Does `STRICT` detect "no orders found" in this case?

### Exercise 16 — FOUND and EXECUTE

Run a dynamic UPDATE and inspect `FOUND`; explain why you should not rely on it to determine how many rows `EXECUTE` affected. Write the solution using `GET DIAGNOSTICS ROW_COUNT`.

### Exercise 17 — Dynamic UPDATE

Write a function changing `NEW` to `CANCELLED` for a tenant and returning the updated row count. Run it inside `BEGIN`/`ROLLBACK`.

### Exercise 18 — INSERT RETURNING

Write a dynamic order `INSERT` that returns `order_id` via `EXECUTE ... INTO`. Pass all values via `USING`.

### Exercise 19 — Dynamic DELETE

Write a `DELETE` for `CANCELLED` orders of a tenant; use `GET DIAGNOSTICS` and `ROLLBACK` in the lab to verify the row count.

### Exercise 20 — RETURN QUERY EXECUTE

Create a function returning multiple orders for a tenant with `order_id`, `amount`, and `created_at`. Explain why `RETURNS TABLE` is used.

### Exercise 21 — FOR IN EXECUTE

Use a `RECORD` in a `FOR ... IN EXECUTE` loop to print order ID and amount with `NOTICE`. For an empty result set, what does the loop do?

### Exercise 22 — RECORD at Runtime

A dynamic query returns `status`, `amount`; afterward the code reads `record.nonexistent_field`. Why does the error only appear at runtime?

### Exercise 23 — Dynamic ORDER BY

Call `search_orders(10, 'amount', 'ASC', 10)`. Explain how column/direction were validated and how `LIMIT` is bound.

### Exercise 24 — Invalid Sort Input

Try passing a column string not in the allowed list. What error should the function return instead of running an arbitrary expression?

### Exercise 25 — Bounded LIMIT

Test negative `LIMIT`, `0`, and `10000`. How does the function reject requests exceeding the API budget?

### Exercise 26 — Whitelisting Source Tables

Design a `current`/`archive` mapping to tables with compatible structures. Why is `format('%I')` insufficient on its own to protect access?

### Exercise 27 — `regclass`

Use `to_regclass` to check whether a relation exists. Why does an existence check not replace permissions or completely eliminate races with concurrent DDL?

### Exercise 28 — Dynamic DDL

Write a procedure allowing only adding the `notes text` column to the `orders` table in the lab schema. Use `%I.%I` and a whitelist.

### Exercise 29 — CREATE INDEX

Use `EXECUTE format(...)` to create an index on `amount` in the lab. Why must `CREATE INDEX CONCURRENTLY` not be run inside a `DO` block?

### Exercise 30 — SQL Type Keywords

A user chooses `text`, `numeric(14,2)`, or `timestamptz`. Write an allowlist mapping for data types rather than inserting a raw string into `%s`.

### Exercise 31 — COMMENT ON TABLE

Use `format('COMMENT ON TABLE %I.%I IS %L', ...)` with a comment containing single quotes. Why does the comment require `%L`?

### Exercise 32 — Year/Month Table Names

Create the `create_monthly_stage` procedure with validated year and month. Explain how it differs from true partitioning.

### Exercise 33 — Security Definer

A `SECURITY DEFINER` function accepts an arbitrary table name. List three ways a caller could abuse the owner's privileges and three protective measures.

### Exercise 34 — `search_path`

Explain the risk of using unqualified table names inside a privileged routine when users can create objects in a schema on `search_path`.

### Exercise 35 — SQLSTATE

Run a dynamic SELECT on a nonexistent table inside an exception block and use `GET STACKED DIAGNOSTICS` to extract `SQLSTATE` and `MESSAGE_TEXT`. Why should you not return `0` for all errors?

### Exercise 36 — Replanning

Compare static PL/pgSQL SQL and dynamic `EXECUTE` when tenant A has a few rows and tenant B has millions of rows. Plan a benchmark to decide whether to replan on every call.

### Exercise 37 — NULL-Aware Filter

Write an `IS NOT DISTINCT FROM $1` condition for a nullable column and compare it with `= $1` when the input is `NULL`.

### Exercise 38 — SQL Arrays with ANY

Pass `ARRAY['PAID','NEW']::text[]` via `USING` and use `status = ANY($2)`. Why is this better than concatenating an `IN (...)` string manually?

### Exercise 39 — JDBC/Spring

Write a `PreparedStatement` calling `search_orders` with bound parameters, adding timeout/limit policies. Where must the backend obtain the tenant ID?

### Exercise 40 — Architecture Synthesis

A multi-tenant reporting system requires:

- Data in both current and archive tables.
- Users choose among three sort columns and `ASC`/`DESC`.
- Optional filtering by a list of statuses.
- An admin system needing to create new monthly staging tables.
- Queries executed through Spring/JDBC.
- Some routines running with higher privileges than the caller.

Design:

1. Which parts should use static SQL and which genuinely need `EXECUTE`?
2. How are sources, columns, directions, and types mapped via whitelists?
3. Where are `%I`, `%L`, `%s`, and `USING` used?
4. Are results received via `INTO`, `ROW_COUNT`, or `RETURN QUERY EXECUTE`?
5. How are tenant isolation, roles, `SECURITY DEFINER`, and `search_path` secured?
6. Which SQLSTATE codes must be distinguished from zero-row cases?
7. What benchmarking, replanning, indexing, timeout, and pagination strategies meet the SLA?
8. What lock, migration, and retention controls govern dynamic staging DDL?

## Conclusion

**PL/pgSQL `EXECUTE` lets you construct and execute an SQL statement at runtime.** It is a powerful tool when the **statement structure** changes—such as table names, column names, sort directions, or DDL targets. However, it should not replace static SQL when only `WHERE` values change.

The core rule is **separating SQL structure from data**: use `format('%I', ...)` for identifiers, `USING` to bind typed values via `$1`/`$2`, `%L` for literals when string construction is genuinely unavoidable, and `%s` solely for whitelisted keywords and operators. `format` does not automatically make raw SQL fragments safe, nor does identifier quoting replace permission checks.

To receive results, use **`EXECUTE ... INTO`** for one row, **`INTO STRICT`** when exactly one row is required, **`GET DIAGNOSTICS ROW_COUNT`** after dynamic DML, **`RETURN QUERY EXECUTE`** when returning sets, and **`FOR ... IN EXECUTE`** when iterating over results. Remember that **EXECUTE itself does not update FOUND**, and `SELECT ... INTO` for PL/pgSQL variables belongs outside the dynamic string.

Finally, dynamic SQL is **planned on every execution**, which can help value-sensitive queries but adds planning overhead. Prefer set-based SQL, enforce strict privileges on `SECURITY DEFINER`, control `search_path`, never trust client-supplied tenant inputs, avoid unnecessary runtime DDL privileges, and measure `EXPLAIN` on realistic workloads. Used deliberately, `EXECUTE`, `USING`, and `format` let you build flexible routines while preserving strong typing, security, and maintainability.
