# Assignment, SELECT INTO, FOUND, and GET DIAGNOSTICS in PL/pgSQL

## 1. Why Must These Four Techniques Be Learned Together?

In PL/pgSQL, a business operation typically follows a sequence of steps:

1. Read data from a table into variables.
2. Check whether any row was found.
3. Execute an INSERT, UPDATE, or DELETE.
4. Determine how many rows were actually affected.
5. Log or handle exceptions using diagnostic metadata.

For example: an API requests changing an order's status. If the order does not exist, the system must return a different status than when the order is already in another state. If a UNIQUE or FOREIGN KEY violation occurs, the system must log the exact SQLSTATE without exposing sensitive data.

Four tools appear constantly:

- **Assignment `:=`:** evaluates an expression and stores the result in a PL/pgSQL variable.
- **`SELECT ... INTO`:** loads SQL query output into a variable, record, or row variable.
- **`FOUND`:** a special boolean variable indicating whether certain recently executed statements found or affected any rows.
- **`GET DIAGNOSTICS`:** retrieves metadata from the most recent SQL command such as `ROW_COUNT`; inside an `EXCEPTION` block, **`GET STACKED DIAGNOSTICS`** retrieves the error's cause.

**Key takeaway:** `FOUND` does not mean "the SQL statement succeeded"; `ROW_COUNT` does not mean "total rows matching a business condition"; PL/pgSQL's `SELECT INTO` is **not** the SQL table-creation statement of the same phrasing.

### 1.1. Objectives

After this lesson, you can:

- Write `DECLARE ... BEGIN ... END` blocks and assign matching data types.
- Distinguish `:=`, `SELECT INTO`, `PERFORM`, and `RETURNING INTO`.
- Explain results when a query returns **0, 1, or multiple rows**, with or without `STRICT`.
- Use `FOUND` without having it unintentionally overwritten by subsequent SQL statements.
- Read `bigint` `ROW_COUNT` immediately after INSERT/UPDATE/DELETE and dynamic `EXECUTE`.
- Distinguish `GET CURRENT DIAGNOSTICS` from `GET STACKED DIAGNOSTICS`.
- Handle `NO_DATA_FOUND`, `TOO_MANY_ROWS`, `unique_violation`, and use `SQLSTATE` safely.
- Analyze the behavior of `FOR`, `FETCH`, `RETURN QUERY`, function calls, and statements that do not alter `FOUND`.
- Design functions that return consistent results safely with respect to transactions and concurrency.
- Practice with the SQL lab and exercises with solutions.

### 1.2. Overview Example

~~~sql
CREATE OR REPLACE FUNCTION demo_lookup(p_id bigint)
RETURNS text
LANGUAGE plpgsql
AS $$
DECLARE
    v_name text;
    v_found boolean;
    v_rows bigint;
BEGIN
    SELECT customer_name
      INTO v_name
      FROM some_schema.customers
     WHERE customer_id = p_id;

    v_found := FOUND;
    GET DIAGNOSTICS v_rows = ROW_COUNT;

    IF NOT v_found THEN
        RETURN 'Not found';
    END IF;

    RETURN format('Found: %s; rows=%s', v_name, v_rows);
END;
$$;
~~~

This code **illustrates structure** and cannot run until `some_schema.customers` exists. The full lab is created later in the lesson.

---

## 2. PL/pgSQL Blocks and Variable Scope

### 2.1. Basic Structure

~~~sql
DO $$
DECLARE
    v_counter integer := 0;
    v_message text DEFAULT 'Start';
BEGIN
    v_counter := v_counter + 1;
    RAISE NOTICE '% / %', v_message, v_counter;
END;
$$ LANGUAGE plpgsql;
~~~

`DO` executes an **anonymous PL/pgSQL block** once. When writing a stored function or procedure, the body can likewise contain `DECLARE` and `BEGIN...END`, along with declared parameters and return type.

~~~text
DO / FUNCTION / PROCEDURE
  |
  +-- DECLARE: declare variables, types, initializers
  |
  +-- BEGIN: sequential execution
  |     |
  |     +-- Variable assignment / SELECT INTO / SQL / IF / LOOP
  |     |
  |     +-- GET DIAGNOSTICS / RAISE / RETURN
  |
  +-- EXCEPTION: error-catching branches, if present
  |
  +-- END;
~~~

### 2.2. Two Uses of BEGIN Have Different Meanings

- `BEGIN` in a PL/pgSQL block starts a **statement block**.
- `BEGIN;` in SQL outside a function opens a **transaction**.

Do not assume each PL/pgSQL block has its own transaction. In an ordinary function, SQL statements participate in the caller's active transaction.

### 2.3. Variable Declarations and Default Values

~~~sql
DO $$
DECLARE
    v_id bigint;
    v_amount numeric(12,2) := 100.50;
    v_status text DEFAULT 'open';
    v_enabled boolean := true;
    v_today date := CURRENT_DATE;
BEGIN
    RAISE NOTICE 'id=%, amount=%, status=%, enabled=%, today=%',
        v_id, v_amount, v_status, v_enabled, v_today;
END $$;
~~~

Without a default initializer, ordinary variables are initialized to **NULL**. Both `DEFAULT` and `:=` can specify an initialization expression. In valid declaration contexts, `=` is also accepted for initialization.

### 2.4. Initializer Expressions Are Evaluated Upon Entering the Block

~~~sql
DO $$
DECLARE
    v_started_at timestamptz := clock_timestamp();
BEGIN
    RAISE NOTICE 'Started at %', v_started_at;
END $$;
~~~

The expression is evaluated when the block is entered (in its execution context), not once when the function is defined. For `CONSTANT` variables, the value cannot be reassigned afterward.

### 2.5. Variables Typed to Match Tables

~~~sql
DO $$
DECLARE
    v_customer_id bigint;
    v_row record;
BEGIN
    v_customer_id := 101;
    RAISE NOTICE 'ID %', v_customer_id;
END $$;
~~~

A later section demonstrates `%TYPE`, `%ROWTYPE`, and `record` once the lab schema and tables are created.

---

## 3. Assignment `:=` and Right-Hand Expressions

### 3.1. Familiar Syntax

~~~sql
DO $$
DECLARE
    v_number integer := 4;
    v_label text := 'Order';
BEGIN
    v_number := v_number + 6;
    v_label := v_label || ' #' || v_number::text;

    RAISE NOTICE '%, result=%', v_label, v_number;
END $$;
~~~

`:=` is the assignment operator in PL/pgSQL. PostgreSQL also supports `=` for PL/pgSQL assignments in valid places; using `:=` usually makes code easier to distinguish from SQL's `=` comparison operator.

### 3.2. Assignment vs. Comparison

~~~sql
v_status := 'paid';  -- assignment
~~~

In a condition:

~~~sql
IF v_status = 'paid' THEN
    RAISE NOTICE 'Paid';
END IF;
~~~

`=` in `IF` is a **comparison operator** returning boolean (or NULL if SQL NULL participates under three-valued logic). Never write `IF v_status := 'paid' THEN` thinking it compares values.

### 3.3. Typed Variables, Validation, and Type Conversion

~~~sql
DO $$
DECLARE
    v_total numeric(12,2);
    v_text text := '18.50';
BEGIN
    v_total := v_text::numeric;
    RAISE NOTICE 'Total %', v_total;
END $$;
~~~

PL/pgSQL follows assignment cast rules; do not rely on implicit casts between user input and sensitive data types such as currency, IDs, or timestamps. Invalid conversions raise an error (e.g., `invalid_text_representation`).

### 3.4. Assigning SQL Expressions and Scalar Subqueries

~~~sql
DO $$
DECLARE
    v_count integer;
BEGIN
    v_count := (SELECT COUNT(*)::integer FROM pg_catalog.pg_class);
    RAISE NOTICE 'Catalog relations count: %', v_count;
END $$;
~~~

PL/pgSQL evaluates SQL expressions on the right-hand side. However, when the goal is to **read one or more columns from a query** and enforce 0/1/many-row behavior, `SELECT ... INTO [STRICT]` is usually clearer.

### 3.5. NULL in Assignments

~~~sql
DO $$
DECLARE
    v_a integer := NULL;
    v_b integer;
BEGIN
    v_b := v_a + 1; -- yields NULL

    RAISE NOTICE 'v_b=%', v_b;
    IF v_b IS NULL THEN
        RAISE NOTICE 'Arithmetic with NULL does not produce a number';
    END IF;
END $$;
~~~

`NULL` means "no known value," not 0 or an empty string.

### 3.6. COALESCE When a Default Value Is Desired

~~~sql
v_total := COALESCE(v_total, 0);
~~~

Use `COALESCE` when business rules **genuinely** treat NULL as 0. Do not replace every NULL with 0 automatically, as that can erase the distinction between "unknown" and "zero."

---

## 4. PL/pgSQL `SELECT ... INTO` Does Not Create Tables

### 4.1. Two Contexts Sharing the Keyword INTO

In PL/pgSQL:

~~~sql
SELECT customer_name
INTO v_customer_name
FROM app.customers
WHERE customer_id = 101;
~~~

means **assign query values into a PL/pgSQL variable**.

In plain SQL, the historical syntax:

~~~sql
SELECT *
INTO new_table
FROM old_table;
~~~

means creating a new table from a SELECT. Table creation should be written explicitly as:

~~~sql
CREATE TABLE new_table AS
SELECT * FROM old_table;
~~~

**Inside a PL/pgSQL function**, `SELECT ... INTO` is parsed using PL/pgSQL syntax for **variables**; do not use it to create tables. To create a table inside a function, use `CREATE TABLE ... AS SELECT ...` where DDL is permitted.

### 4.2. Valid Placements for INTO

A readable convention:

~~~sql
SELECT expression_list
INTO target_list
FROM ...
WHERE ...;
~~~

PostgreSQL PL/pgSQL accepts `INTO` in multiple positions within a SELECT statement, but placing it right after the SELECT list or following your team's standard improves readability. Examples in this lesson use:

~~~sql
SELECT ...
  INTO ...
  FROM ...;
~~~

### 4.3. Single Variable

~~~sql
DO $$
DECLARE
    v_database text;
BEGIN
    SELECT current_database()
      INTO v_database;

    RAISE NOTICE 'Database: %', v_database;
END $$;
~~~

`SELECT current_database()` always produces one row on success; the variable receives a string.

### 4.4. Multiple Variables

~~~sql
DO $$
DECLARE
    v_user text;
    v_schema text;
BEGIN
    SELECT current_user, current_schema()
      INTO v_user, v_schema;

    RAISE NOTICE 'User=%; schema=%', v_user, v_schema;
END $$;
~~~

The number and types of returned columns must be compatible with the target variables. Use consistent variable names to avoid confusion between SQL columns and PL/pgSQL variables.

### 4.5. SELECT INTO Does Not Guarantee One Row

If the WHERE clause is not selective enough, SELECT can produce 0, 1, or many rows. **Without STRICT**, PL/pgSQL assigns only the **first row returned by the executor** and discards the rest once the target is populated. Without `ORDER BY`, "the first row" is not guaranteed to follow any business key order.

This contrasts sharply with a common misconception:

> "SELECT INTO a scalar variable definitely throws an error if the query has two rows."

That is **false without STRICT** for SELECT. To catch multi-row results, use `INTO STRICT`.

### 4.6. SELECT with Output but Without INTO

In PL/pgSQL, writing:

~~~sql
SELECT 1;
~~~

inside a block raises the error **query has no destination for result data**. To execute a query and discard its output, use `PERFORM`:

~~~sql
PERFORM 1;
~~~

To return rows to the caller, use `RETURN QUERY` in a set-returning function or an appropriate RETURN statement.

---

## 5. Unified Practice Dataset

The SQL statements below create an isolated schema. Run them **once on a test database** with appropriate `CREATE` and table privileges. Do not use a production schema of the same name.

### 5.1. Create Schema

~~~sql
CREATE SCHEMA IF NOT EXISTS pl_diag_lab;
~~~

### 5.2. Create Customers Table

~~~sql
CREATE TABLE pl_diag_lab.customers (
    customer_id bigint PRIMARY KEY,
    customer_code text NOT NULL UNIQUE,
    customer_name text NOT NULL,
    customer_status text NOT NULL
        CHECK (customer_status IN ('active', 'inactive'))
);
~~~

### 5.3. Create Orders Table

~~~sql
CREATE TABLE pl_diag_lab.orders (
    order_id bigint PRIMARY KEY,
    customer_id bigint NOT NULL
        REFERENCES pl_diag_lab.customers(customer_id),
    amount numeric(12,2) NOT NULL CHECK (amount >= 0),
    order_status text NOT NULL
        CHECK (order_status IN ('new','paid','canceled')),
    created_at timestamptz NOT NULL
);
~~~

### 5.4. Load Sample Data

~~~sql
INSERT INTO pl_diag_lab.customers
    (customer_id, customer_code, customer_name, customer_status)
VALUES
    (101, 'C101', 'An', 'active'),
    (102, 'C102', 'Binh', 'active'),
    (103, 'C103', 'Chi', 'inactive');

INSERT INTO pl_diag_lab.orders
    (order_id, customer_id, amount, order_status, created_at)
VALUES
    (1001, 101, 250.00, 'new',      '2026-11-01 09:00:00+00'),
    (1002, 101, 125.50, 'paid',     '2026-11-02 10:00:00+00'),
    (1003, 102, 300.00, 'new',      '2026-11-03 11:00:00+00'),
    (1004, 102, 450.00, 'canceled', '2026-11-04 12:00:00+00'),
    (1005, 103, 100.00, 'new',      '2026-11-05 13:00:00+00');
~~~

### 5.5. Baseline Data for Reading Results

| Customer ID | Name | Status | Orders |
|---:|---|---|---:|
| 101 | An | active | 2 |
| 102 | Binh | active | 2 |
| 103 | Chi | inactive | 1 |

| Order ID | Customer | Amount | Status |
|---:|---:|---:|---|
| 1001 | 101 | 250.00 | new |
| 1002 | 101 | 125.50 | paid |
| 1003 | 102 | 300.00 | new |
| 1004 | 102 | 450.00 | canceled |
| 1005 | 103 | 100.00 | new |

Running `INSERT` multiple times with the same primary keys will cause unique errors on subsequent runs. To start over, use a fresh lab database/schema or clean up objects **confirmed to belong strictly to the lab** using an explicit reset procedure.

---

## 6. `%TYPE`, `%ROWTYPE`, and `record`

### 6.1. `%TYPE`: Variable Inheriting a Column's Type

~~~sql
DO $$
DECLARE
    v_name pl_diag_lab.customers.customer_name%TYPE;
    v_amount pl_diag_lab.orders.amount%TYPE;
BEGIN
    v_name := 'Example';
    v_amount := 199.90;
    RAISE NOTICE 'name=%, amount=%', v_name, v_amount;
END $$;
~~~

Using `%TYPE` keeps variables aligned with the corresponding schema column type, reducing type-mismatch bugs. If a column type changes, function recompilation and validation must still be checked; `%TYPE` does not eliminate all migration risks.

### 6.2. `%ROWTYPE`: Receiving an Entire Row with Known Structure

~~~sql
DO $$
DECLARE
    v_customer pl_diag_lab.customers%ROWTYPE;
BEGIN
    SELECT *
      INTO v_customer
      FROM pl_diag_lab.customers
     WHERE customer_id=101;

    RAISE NOTICE 'ID=%, name=%',
        v_customer.customer_id,
        v_customer.customer_name;
END $$;
~~~

`%ROWTYPE` provides fields matching the table's structure. If a query selects a different shape, assigning into the row variable will raise an incompatibility error.

### 6.3. `record`: Shape Determined by the Result

~~~sql
DO $$
DECLARE
    v_result record;
BEGIN
    SELECT
        c.customer_name AS name,
        COUNT(o.order_id) AS orders_count
    INTO v_result
    FROM pl_diag_lab.customers AS c
    LEFT JOIN pl_diag_lab.orders AS o
      ON o.customer_id = c.customer_id
    WHERE c.customer_id=101
    GROUP BY c.customer_name;

    RAISE NOTICE 'name=%, orders=%',
        v_result.name, v_result.orders_count;
END $$;
~~~

`record` is not bound to a specific row type at declaration time. After a successful SELECT INTO, it carries the fields defined by the result set. Never access a field that does not exist; doing so causes a runtime error.

### 6.4. Assigning a Whole Row vs. Individual Fields

~~~sql
DO $$
DECLARE
    v_customer pl_diag_lab.customers%ROWTYPE;
BEGIN
    SELECT * INTO v_customer
    FROM pl_diag_lab.customers
    WHERE customer_id=101;

    v_customer.customer_name := 'Temporary name';
    RAISE NOTICE 'In-memory record: %', v_customer.customer_name;
END $$;
~~~

This assignment modifies only the **local row/record variable**; it does not automatically UPDATE the table. To persist changes to the table, run a controlled SQL `UPDATE`.

---

## 7. Non-STRICT SELECT INTO: 0, 1, or Multiple Rows

### 7.1. Query Returns Exactly One Row

~~~sql
DO $$
DECLARE
    v_name text;
BEGIN
    SELECT customer_name
    INTO v_name
    FROM pl_diag_lab.customers
    WHERE customer_id=101;

    RAISE NOTICE 'name=%; FOUND=%', v_name, FOUND;
END $$;
~~~

Expected output: `v_name='An'` and `FOUND=true`.

### 7.2. Query Returns 0 Rows

~~~sql
DO $$
DECLARE
    v_name text := 'initial value';
BEGIN
    SELECT customer_name
    INTO v_name
    FROM pl_diag_lab.customers
    WHERE customer_id=999;

    RAISE NOTICE 'name=%; FOUND=%', v_name, FOUND;
END $$;
~~~

When non-STRICT SELECT INTO **finds no row**, PL/pgSQL sets the target to **NULL** rather than preserving `'initial value'`, and `FOUND=false`.

Do not write:

~~~sql
IF v_name = NULL THEN
    ...
END IF;
~~~

Use `v_name IS NULL`, or better yet check **`FOUND` immediately after the SELECT** when you need to distinguish whether a row was found.

### 7.3. Query Returns Multiple Rows Without STRICT

~~~sql
DO $$
DECLARE
    v_order_id bigint;
BEGIN
    SELECT order_id
    INTO v_order_id
    FROM pl_diag_lab.orders
    WHERE customer_id=101;

    RAISE NOTICE 'first order=%; FOUND=%', v_order_id, FOUND;
END $$;
~~~

There are two orders (1001 and 1002). A non-STRICT query **does not raise TOO_MANY_ROWS**; instead, it picks whichever row the executor returns first. `v_order_id` is **not guaranteed to be 1001** without an ORDER BY.

### 7.4. Selecting One Row Deterministically

~~~sql
SELECT order_id
INTO v_order_id
FROM pl_diag_lab.orders
WHERE customer_id=101
ORDER BY created_at DESC, order_id DESC
LIMIT 1;
~~~

When requesting the "latest order," `ORDER BY` should include a deterministic tie-breaker (such as the primary key) to avoid arbitrary selection when multiple rows share the same `created_at`.

### 7.5. LIMIT 1 Does Not Enforce Uniqueness

`LIMIT 1` satisfies the requirement to **pick one row**; it does not verify that only one row matches the predicate. When business rules require "there must be exactly one customer with this customer_code," use a UNIQUE constraint in the schema and consider `INTO STRICT` to catch invalid query assumptions.

### 7.6. Using SELECT INTO with Aggregation

~~~sql
DO $$
DECLARE
    v_count bigint;
BEGIN
    SELECT COUNT(*)
      INTO v_count
      FROM pl_diag_lab.orders
     WHERE customer_id=999;

    RAISE NOTICE 'count=%; FOUND=%', v_count, FOUND;
END $$;
~~~

Result: `v_count=0`, yet **`FOUND=true`**, because ungrouped `COUNT(*)` returns **one row containing 0**.

Thus, `FOUND` indicates "the statement returned a row," **not** "the aggregate value is greater than 0."

---

## 8. SELECT INTO STRICT: Requiring Exactly One Row

### 8.1. Syntax

~~~sql
SELECT customer_name
INTO STRICT v_name
FROM pl_diag_lab.customers
WHERE customer_id=101;
~~~

`STRICT` requires the query to return **exactly one row**.

| Rows from Query | Without STRICT | With STRICT |
|---:|---|---|
| 0 | Target becomes NULL, `FOUND=false` | Raises `NO_DATA_FOUND` |
| 1 | Target receives value, `FOUND=true` | Target receives value, `FOUND=true` |
| More than 1 | Target receives first row, `FOUND=true` | Raises `TOO_MANY_ROWS` |

### 8.2. STRICT Does Not Mean "No NULL Columns Allowed"

If a query returns exactly one row whose `optional_note` column is NULL, `INTO STRICT` still **succeeds**. STRICT checks **row count**, not whether every column inside the row is NOT NULL.

### 8.3. Example: Exactly One Row

~~~sql
DO $$
DECLARE
    v_name text;
BEGIN
    SELECT customer_name
      INTO STRICT v_name
      FROM pl_diag_lab.customers
     WHERE customer_id=101;

    RAISE NOTICE 'Customer=%', v_name;
END $$;
~~~

### 8.4. Example: NO_DATA_FOUND

~~~sql
DO $$
DECLARE
    v_name text;
BEGIN
    SELECT customer_name
      INTO STRICT v_name
      FROM pl_diag_lab.customers
     WHERE customer_id=999;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE NOTICE 'Customer does not exist';
END $$;
~~~

The exception is caught inside the block; `RAISE NOTICE` in the handler is just for demonstration. In an application, return a "not found" status or raise an appropriate domain-specific error.

### 8.5. Example: TOO_MANY_ROWS

~~~sql
DO $$
DECLARE
    v_order bigint;
BEGIN
    SELECT order_id
      INTO STRICT v_order
      FROM pl_diag_lab.orders
     WHERE customer_id=101;
EXCEPTION
    WHEN TOO_MANY_ROWS THEN
        RAISE NOTICE 'Customer 101 has more than one order';
END $$;
~~~

Orders 1001 and 1002 cause STRICT to raise an error, which is caught by the handler.

### 8.6. STRICT with Aggregates

~~~sql
SELECT COUNT(*)
INTO STRICT v_count
FROM pl_diag_lab.orders
WHERE customer_id=999;
~~~

Ungrouped `COUNT(*)` still returns **one row**, so STRICT **succeeds** with value 0. With `GROUP BY`, if no groups are produced, the query returns 0 rows and STRICT raises `NO_DATA_FOUND`.

### 8.7. STRICT Does Not Replace a UNIQUE Constraint

If data must be unique, define `UNIQUE` or `PRIMARY KEY` in the database schema. `INTO STRICT` is useful for asserting assumptions at runtime, but it cannot prevent concurrent transactions from inserting violating rows if the schema lacks constraints; only proper constraints enforce invariants consistently under concurrency.

---

## 9. FOUND: PL/pgSQL's Special Boolean Variable

### 9.1. Where Does FOUND Exist?

Every PL/pgSQL function invocation has a special boolean variable `FOUND`:

- Initialized to **false** at the start of each function invocation.
- Scoped to that PL/pgSQL function/block invocation, not server-wide.
- Updated by certain PL/pgSQL statements after execution.
- Readable via `IF FOUND THEN` or saved via `v_was_found := FOUND;`.

~~~sql
DO $$
BEGIN
    RAISE NOTICE 'FOUND at block start: %', FOUND;
    PERFORM 1;
    RAISE NOTICE 'FOUND after PERFORM 1: %', FOUND;
END $$;
~~~

### 9.2. FOUND After SELECT INTO

~~~sql
DO $$
DECLARE
    v_name text;
BEGIN
    SELECT customer_name INTO v_name
    FROM pl_diag_lab.customers
    WHERE customer_id=101;

    IF FOUND THEN
        RAISE NOTICE 'Customer found: %', v_name;
    ELSE
        RAISE NOTICE 'Customer not found';
    END IF;
END $$;
~~~

`FOUND=true` if SELECT INTO **successfully assigned from at least one row**; otherwise false.

### 9.3. FOUND Tracks the Most Recent Statement, Not a Specific Variable

Error-prone pattern:

~~~sql
SELECT customer_name INTO v_name
FROM pl_diag_lab.customers
WHERE customer_id=p_id;

PERFORM 1;

IF FOUND THEN
    -- Here FOUND reflects PERFORM 1, NO LONGER SELECT INTO!
END IF;
~~~

`PERFORM 1` produces a row and sets `FOUND=true`, masking whether SELECT INTO found anything.

### 9.4. Correct Pattern: Capture the Result Immediately After the Statement

~~~sql
SELECT customer_name INTO v_name
FROM pl_diag_lab.customers
WHERE customer_id=p_id;

v_customer_found := FOUND;

PERFORM 1;

IF v_customer_found THEN
    ...
END IF;
~~~

The boolean assignment `v_customer_found := FOUND` does not run a new SQL query. Never rely on `FOUND` across multiple steps; store it in a business-named variable when needed across steps.

### 9.5. FOUND Does Not Carry Row Counts

`FOUND` is strictly boolean. Whether an UPDATE affects 1 or 1,000 rows, `FOUND=true` in both cases. To obtain the exact row count, use `GET DIAGNOSTICS ... = ROW_COUNT`.

### 9.6. FOUND Is Not a Transaction Success Flag

An SQL statement returning **0 rows** can still **succeed completely** with `FOUND=false`. Conversely, a statement that raises an exception does not leave a meaningful new `FOUND` value to inspect; control jumps directly to an exception handler if caught.

---

## 10. Which Statements Update FOUND?

Not every PL/pgSQL statement resets `FOUND`. This is a frequent source of bugs when multiple SQL statements run consecutively.

| Statement | When Is FOUND True? | Notes |
|---|---|---|
| `SELECT ... INTO` | At least one row returned | Without STRICT, picks only the first row |
| `PERFORM query` | Query produces at least one row | Used when return values are discarded |
| `INSERT ...` | At least one row inserted | Includes `ON CONFLICT DO NOTHING` where 0 rows inserted -> false |
| `UPDATE ...` | At least one row affected | Does not mean the new value differs from the old value |
| `DELETE ...` | At least one row deleted | Can be false even when SQL succeeds |
| `MERGE ...` | At least one row affected per statement semantics | Version-dependent; PostgreSQL 15+ |
| `FETCH cursor INTO ...` | A row was fetched | Cursor may have reached the end |
| `MOVE cursor` | Moved position by at least one row | Does not return row data to application |
| `FOR query LOOP ... END LOOP` | Loop executed at least one iteration | **FOUND is set when the loop ends** |
| `FOREACH ... LOOP` | At least one iteration executed | Likewise set when the loop ends |
| `RETURN QUERY` or `RETURN QUERY EXECUTE` | At least one row added to result set | Inside set-returning functions |
| `EXECUTE dynamic_string` | **Does not update FOUND** | Use `GET DIAGNOSTICS ROW_COUNT` |
| Assignment `v := expression` | Does not alter FOUND | Previous FOUND value remains |
| `IF`, `RAISE` | Do not normally update FOUND | Never treat FOUND as global state |

### 10.1. A PERFORM Example

~~~sql
DO $$
BEGIN
    PERFORM 1
    FROM pl_diag_lab.customers
    WHERE customer_id=999;

    RAISE NOTICE 'Customer 999 exists? %', FOUND;

    PERFORM 1
    FROM pl_diag_lab.customers
    WHERE customer_id=101;

    RAISE NOTICE 'Customer 101 exists? %', FOUND;
END $$;
~~~

Expected: **false**, then **true**.

### 10.2. PERFORM Used to Discard SELECT Results

~~~sql
DO $$
BEGIN
    PERFORM pg_sleep(0.01);
    RAISE NOTICE 'Query executed';
END $$;
~~~

This is only a tiny lab illustration. In real code, calling functions with side effects requires understanding idempotency and retries. Do not use `PERFORM` as a "success check" when 0 rows is a valid empty result yet business logic still succeeds.

### 10.3. FOR Query Loop

~~~sql
DO $$
DECLARE
    r record;
    v_iterations integer := 0;
BEGIN
    FOR r IN
        SELECT order_id
        FROM pl_diag_lab.orders
        WHERE customer_id=101
        ORDER BY order_id
    LOOP
        v_iterations := v_iterations + 1;
        RAISE NOTICE 'Order %', r.order_id;
    END LOOP;

    RAISE NOTICE 'Iterations=%; FOUND=%', v_iterations, FOUND;
END $$;
~~~

Expected: two iterations, `FOUND=true` **after the loop**.

If SQL statements inside the loop update `FOUND`, its value inside the loop body reflects those statements. Under PL/pgSQL rules, the `FOR` loop sets `FOUND` **when the loop exits**, indicating whether any iterations ran.

### 10.4. FOREACH with an Empty Array

~~~sql
DO $$
DECLARE
    v_tag integer;
    v_count integer := 0;
BEGIN
    FOREACH v_tag IN ARRAY ARRAY[]::integer[]
    LOOP
        v_count := v_count + 1;
    END LOOP;

    RAISE NOTICE 'iterations=%, FOUND=%', v_count, FOUND;
END $$;
~~~

Zero iterations run, so `FOUND=false` when the loop terminates (overwriting status from earlier statements).

### 10.5. FOUND After DML

~~~sql
DO $$
BEGIN
    UPDATE pl_diag_lab.orders
       SET order_status='paid'
     WHERE order_id=-1;

    RAISE NOTICE 'UPDATE affected any rows? %', FOUND;
END $$;
~~~

Updating 0 rows is valid SQL; `FOUND=false`.

### 10.6. Capturing FOUND Before Running Another Statement

~~~sql
DO $$
DECLARE
    v_had_orders boolean;
    v_has_active_customer boolean;
BEGIN
    PERFORM 1 FROM pl_diag_lab.orders
    WHERE customer_id=101;

    v_had_orders := FOUND;

    PERFORM 1 FROM pl_diag_lab.customers
    WHERE customer_id=101 AND customer_status='active';

    v_has_active_customer := FOUND;

    RAISE NOTICE 'Has orders=%; active=%',
        v_had_orders, v_has_active_customer;
END $$;
~~~

Never read `FOUND` after the second statement expecting the first `PERFORM`'s status.

---

## 11. GET DIAGNOSTICS: Inspecting Post-Statement Metadata

### 11.1. Basic Syntax

~~~sql
GET DIAGNOSTICS v_rows = ROW_COUNT;
~~~

Equivalent explicit form:

~~~sql
GET CURRENT DIAGNOSTICS v_rows = ROW_COUNT;
~~~

`CURRENT` is optional for standard `GET DIAGNOSTICS`.

### 11.2. Two Common Diagnostic Items

| Item | Typical Target Type | Meaning |
|---|---|---|
| `ROW_COUNT` | `bigint` | Number of rows processed by the **most recent SQL command** per PL/pgSQL command status |
| `PG_CONTEXT` | `text` | String describing the **current call stack** at the `GET DIAGNOSTICS` call site |

`ROW_COUNT` does not accumulate across an entire transaction; `PG_CONTEXT` is neither an SQL query plan nor an exception traceback.

### 11.3. ROW_COUNT vs. FOUND

- `FOUND` answers "was any row processed or found?" for **statements supported by `FOUND`**.
- `ROW_COUNT` answers "how many rows?" for the **most recent SQL statement**, including dynamic `EXECUTE` statements that do not touch `FOUND`.

Example:

~~~sql
DO $$
DECLARE
    v_count bigint;
    v_found boolean;
BEGIN
    UPDATE pl_diag_lab.orders
       SET order_status='paid'
     WHERE customer_id=101 AND order_status='new';

    v_found := FOUND;
    GET DIAGNOSTICS v_count = ROW_COUNT;

    RAISE NOTICE 'found=%; affected=%', v_found, v_count;
END $$;
~~~

On the initial lab dataset, order 1001 transitions `new → paid`, giving `FOUND=true` and `ROW_COUNT=1`. **This command modifies the table**; to preserve baseline data, run inside a test transaction with `ROLLBACK` or use a dedicated lab copy.

### 11.4. Why Use bigint?

`ROW_COUNT` can be very large in bulk UPDATE or DELETE operations. Using `bigint` avoids the 32-bit signed `integer` limit and matches PostgreSQL's internal row-count type.

### 11.5. Capture Immediately After the Key Statement

~~~sql
UPDATE pl_diag_lab.orders
SET order_status='paid'
WHERE customer_id=101
  AND order_status='new';

GET DIAGNOSTICS v_updated = ROW_COUNT;
v_updated_any := FOUND;

-- Subsequent SELECT/UPDATE statements will overwrite the observed status.
~~~

This reads cleanly: `v_updated` and `v_updated_any` reflect the **immediately preceding UPDATE**.

### 11.6. Do Not Read ROW_COUNT After Intervening Statements

Incorrect:

~~~sql
UPDATE pl_diag_lab.orders
SET order_status='paid'
WHERE order_status='new';

PERFORM 1;

GET DIAGNOSTICS v_rows = ROW_COUNT;
~~~

Here `ROW_COUNT` no longer reflects the initial UPDATE. **Place `GET DIAGNOSTICS` immediately after the SQL statement being measured.**

### 11.7. Returned Rows Do Not Always Equal Updated/Matching Rows

A query:

~~~sql
SELECT COUNT(*) INTO v_count
FROM pl_diag_lab.orders
WHERE order_status='new';
~~~

returns one aggregate row containing the count of matching orders. To know **how many orders matched the predicate**, use `v_count`, not `GET DIAGNOSTICS ROW_COUNT`: the aggregate SELECT only produced 1 result row.

---

## 12. DML RETURNING INTO: Modifying Data and Capturing Output Together

### 12.1. UPDATE RETURNING INTO

~~~sql
DO $$
DECLARE
    v_amount numeric(12,2);
    v_rows bigint;
    v_found boolean;
BEGIN
    UPDATE pl_diag_lab.orders
       SET amount=amount + 50
     WHERE order_id=1001
     RETURNING amount INTO v_amount;

    v_found := FOUND;
    GET DIAGNOSTICS v_rows = ROW_COUNT;

    RAISE NOTICE 'amount=%, found=%, rows=%',
        v_amount, v_found, v_rows;
END $$;
~~~

When the update succeeds on one row, `v_amount` receives the post-UPDATE value; `FOUND=true`, `ROW_COUNT=1`.

### 12.2. DELETE RETURNING INTO

~~~sql
DO $$
DECLARE
    v_deleted_order bigint;
    v_rows bigint;
BEGIN
    DELETE FROM pl_diag_lab.orders
    WHERE order_id=-999
    RETURNING order_id INTO v_deleted_order;

    GET DIAGNOSTICS v_rows = ROW_COUNT;

    RAISE NOTICE 'deleted_id=%, rows=%, found=%',
        v_deleted_order, v_rows, FOUND;
END $$;
~~~

For a nonexistent ID, `v_deleted_order` becomes NULL, `ROW_COUNT=0`, and `FOUND=false`. This is not an SQL error.

### 12.3. INSERT RETURNING INTO

~~~sql
DO $$
DECLARE
    v_id bigint;
BEGIN
    INSERT INTO pl_diag_lab.orders
        (order_id,customer_id,amount,order_status,created_at)
    VALUES
        (2001,101,75.00,'new',now())
    RETURNING order_id INTO v_id;

    RAISE NOTICE 'new order id=%', v_id;
END $$;
~~~

Run only when `order_id=2001` does not already exist; repeating it on the same lab causes a unique violation. Wrap in a transaction with `ROLLBACK` to keep the dataset unchanged.

### 12.4. DML RETURNING Differs from SELECT INTO When Returning Multiple Rows

**Special note:** With `INSERT/UPDATE/DELETE/MERGE ... RETURNING ... INTO`, PL/pgSQL raises an error when `RETURNING` produces **more than one row**, **even without `STRICT`**.

Experimental example:

~~~sql
DO $$
DECLARE
    v_id bigint;
BEGIN
    UPDATE pl_diag_lab.orders
       SET amount=amount
     WHERE customer_id=101
     RETURNING order_id INTO v_id;
EXCEPTION
    WHEN TOO_MANY_ROWS THEN
        RAISE NOTICE 'RETURNING produced more than one row';
END $$;
~~~

In the initial lab data, customer 101 has two orders, so `RETURNING` tries to return two rows—PL/pgSQL does not silently pick the first row as non-STRICT `SELECT INTO` does. The error is caught, and changes in the block are rolled back by the exception subtransaction.

### 12.5. For Bulk Updates, Do Not Use Scalar RETURNING INTO

When processing **every updated row**, you can:

- Run DML **without RETURNING INTO** and read `ROW_COUNT`.
- Use `RETURN QUERY UPDATE ... RETURNING ...` inside a set-returning function where appropriate.
- Write set-based SQL instead of looping one UPDATE per row.
- Use an audit table or a `RETURNING` CTE to store all changed IDs within the transaction.

Accurate counting example:

~~~sql
DO $$
DECLARE
    v_rows bigint;
BEGIN
    UPDATE pl_diag_lab.orders
       SET order_status='paid'
     WHERE order_status='new';

    GET DIAGNOSTICS v_rows = ROW_COUNT;
    RAISE NOTICE 'Updated % orders', v_rows;
END $$;
~~~

**This is real DML.** In the lab, wrap it in `BEGIN; DO ...; ROLLBACK;` to test without persisting changes.

---

## 13. SELECT INTO + FOUND, or SELECT EXISTS / COUNT?

### 13.1. When You Need a Single Value

~~~sql
SELECT customer_name
  INTO v_name
  FROM pl_diag_lab.customers
 WHERE customer_id=p_customer_id;

IF NOT FOUND THEN
    ...
END IF;
~~~

Appropriate when you actually need the retrieved value.

### 13.2. When You Only Need to Check Existence

~~~sql
SELECT EXISTS (
    SELECT 1
    FROM pl_diag_lab.orders
    WHERE customer_id=p_customer_id
)
INTO v_has_order;
~~~

This query **always returns one boolean row** on success, so `FOUND=true` even when `v_has_order=false`. With this pattern, **check `v_has_order`**, not `FOUND`, to see whether an order exists.

### 13.3. PERFORM for an Existence Check

~~~sql
PERFORM 1
FROM pl_diag_lab.orders
WHERE customer_id=p_customer_id;

IF FOUND THEN
    ...
END IF;
~~~

`FOUND` directly reflects whether the query returned at least one row. For existence checks, adding `LIMIT 1` (`PERFORM 1 ... LIMIT 1`) makes intent explicit and lets the planner stop early when an index fits.

### 13.4. When You Need the Exact Count

~~~sql
SELECT COUNT(*)
INTO v_order_count
FROM pl_diag_lab.orders
WHERE customer_id=p_customer_id;
~~~

Correct when business logic requires the count. `COUNT(*)` may scan more rows than an existence check; avoid using `COUNT(*)` solely to check existence on huge tables when a boolean suffices.

### 13.5. When Exactly One Row Must Exist

~~~sql
SELECT customer_name
INTO STRICT v_name
FROM pl_diag_lab.customers
WHERE customer_code=p_code;
~~~

With a UNIQUE constraint on `customer_code`, `STRICT` validates the missing case and catches broken assumptions. If you prefer not to raise on missing rows, use non-STRICT `SELECT INTO` + `FOUND`.

### 13.6. Quick-Choice Table

| Goal | SQL/PLpgSQL | What to Inspect? |
|---|---|---|
| Fetch one value if present | `SELECT ... INTO` | Target + `FOUND` |
| Require exactly one row | `SELECT ... INTO STRICT` | `NO_DATA_FOUND` / `TOO_MANY_ROWS` |
| Only check existence | `PERFORM 1 FROM ... LIMIT 1` | `FOUND` |
| Check existence into a boolean | `SELECT EXISTS(...) INTO v_bool` | `v_bool`, **not `FOUND`** |
| Count rows matching predicate | `SELECT COUNT(*) INTO v_count` | `v_count` |
| Check if UPDATE affected any rows | `UPDATE ...` | `FOUND` |
| Count rows affected by UPDATE | `UPDATE ...; GET DIAGNOSTICS` | `ROW_COUNT` |
| Single-row DML returning output | `UPDATE/INSERT/DELETE ... RETURNING INTO` | Target + `FOUND` |
| Multi-row DML, only need count | DML without `RETURNING INTO`; `GET DIAGNOSTICS` | `ROW_COUNT` |

---

## 14. Dynamic SQL with EXECUTE: The Special Case for FOUND

### 14.1. EXECUTE Is Used When SQL Is Built at Runtime

~~~sql
DO $$
DECLARE
    v_id bigint := 101;
    v_name text;
    v_rows bigint;
BEGIN
    EXECUTE
        'SELECT customer_name FROM pl_diag_lab.customers
          WHERE customer_id=$1'
    INTO v_name
    USING v_id;

    GET DIAGNOSTICS v_rows = ROW_COUNT;

    RAISE NOTICE 'name=%, row_count=%', v_name, v_rows;
END $$;
~~~

`EXECUTE ... INTO target USING ...` captures dynamic SQL output. Use `USING` for **data values** to avoid unsafe literal concatenation.

### 14.2. EXECUTE **Does Not Update FOUND**

This is a core distinction:

~~~sql
DO $$
DECLARE
    v_name text;
    v_rows bigint;
    v_found_before boolean;
BEGIN
    PERFORM 1 FROM pl_diag_lab.customers WHERE customer_id=101;
    v_found_before := FOUND; -- true

    EXECUTE
        'SELECT customer_name FROM pl_diag_lab.customers
          WHERE customer_id=$1'
    INTO v_name
    USING 999;

    GET DIAGNOSTICS v_rows = ROW_COUNT;

    RAISE NOTICE 'found_before=%, FOUND_now=%, dynamic_rows=%',
        v_found_before, FOUND, v_rows;
END $$;
~~~

The dynamic SELECT does not find customer 999, so `v_name=NULL` and `ROW_COUNT=0`. Yet **`FOUND` remains true from the earlier PERFORM**. Never use `IF FOUND` to check dynamic `EXECUTE`.

### 14.3. Correct Pattern After EXECUTE

~~~sql
EXECUTE v_sql INTO v_value USING p_id;
GET DIAGNOSTICS v_rows = ROW_COUNT;

IF v_rows = 0 THEN
    ...
END IF;
~~~

If the target value can legitimately be NULL, never use `IF v_value IS NULL` to detect missing rows. `ROW_COUNT` accurately reports whether the dynamic statement returned a row.

### 14.4. Dynamic EXECUTE ... INTO STRICT

~~~sql
EXECUTE
    'SELECT customer_name FROM pl_diag_lab.customers
      WHERE customer_id=$1'
INTO STRICT v_name
USING p_customer_id;
~~~

`INTO STRICT` on dynamic `EXECUTE` raises `NO_DATA_FOUND` or `TOO_MANY_ROWS` if the query does not return exactly one row, following standard PL/pgSQL rules.

### 14.5. Never Concatenate Table Names from Input

Incorrect:

~~~text
v_sql := 'SELECT * FROM ' || untrusted_table_name;
~~~

Use `format('%I', identifier)` for object names, `USING` for values, and validate allowed table/column names against a whitelist.

~~~sql
DO $$
DECLARE
    v_schema text := 'pl_diag_lab';
    v_table text := 'customers';
    v_id bigint := 101;
    v_count bigint;
BEGIN
    EXECUTE format(
        'SELECT COUNT(*) FROM %I.%I WHERE customer_id=$1',
        v_schema, v_table
    )
    INTO v_count
    USING v_id;

    RAISE NOTICE 'count=%', v_count;
END $$;
~~~

`SELECT COUNT(*)` always produces one row; `v_count` holds the matching customer count, whereas `ROW_COUNT` after a dynamic aggregate SELECT reflects the 1 result row, **not `v_count`**.

### 14.6. EXECUTE Dynamic UPDATE

~~~sql
DO $$
DECLARE
    v_rows bigint;
BEGIN
    EXECUTE
        'UPDATE pl_diag_lab.orders
           SET order_status=$1
         WHERE order_id=$2'
    USING 'paid', -999;

    GET DIAGNOSTICS v_rows = ROW_COUNT;
    RAISE NOTICE 'dynamic update affected % rows', v_rows;
END $$;
~~~

Expected `v_rows=0` in the lab. `FOUND` is not updated by dynamic `EXECUTE`, even when the dynamic SQL is an UPDATE.

### 14.7. Dynamic SQL and Plan Caching

PL/pgSQL can cache query plans for static statements where appropriate. Dynamic `EXECUTE` strings are planned on each execution, which may be helpful or costly depending on parameter-sensitive plans and workload. **Never choose dynamic SQL just to avoid `FOUND`**; use it only when the query structure itself must vary at runtime.

---

## 15. GET DIAGNOSTICS PG_CONTEXT: Knowing the Current Execution Location

### 15.1. Syntax

~~~sql
DO $$
DECLARE
    v_context text;
BEGIN
    GET DIAGNOSTICS v_context = PG_CONTEXT;
    RAISE NOTICE 'Current PL/pgSQL stack:%', chr(10) || v_context;
END $$;
~~~

`PG_CONTEXT` returns a string describing the **current call stack**, including PL/pgSQL functions/blocks and execution line numbers where PostgreSQL can report them.

### 15.2. PG_CONTEXT Is Not Error Context

During normal execution, `GET DIAGNOSTICS ... PG_CONTEXT` reports the **current location**. When an exception occurs and you need **where the error originated**, use `GET STACKED DIAGNOSTICS ... PG_EXCEPTION_CONTEXT` inside the exception handler.

Reading `PG_CONTEXT` inside a handler returns the **current stack at the handler**, not necessarily the full original error location.

### 15.3. Using PG_CONTEXT for Logging

In large procedures, the call stack helps identify which line was executing when a log entry was written. However:

- Never expose internal call stacks in HTTP APIs to clients.
- Stacks can reveal schema/function names, line numbers, and internal logic.
- Logs require proper security and retention policies.
- Include request/transaction correlation IDs to link logs with observability tools.

### 15.4. Retrieving Multiple Diagnostic Items in One Statement

~~~sql
DO $$
DECLARE
    v_rows bigint;
    v_context text;
BEGIN
    PERFORM 1;
    GET DIAGNOSTICS
        v_rows = ROW_COUNT,
        v_context = PG_CONTEXT;

    RAISE NOTICE 'rows=%', v_rows;
    RAISE NOTICE 'context:%', chr(10) || v_context;
END $$;
~~~

For clarity and accuracy, capture needed diagnostics immediately after the statement rather than running unnecessary commands beforehand.

---

## 16. GET STACKED DIAGNOSTICS: Inspecting the Current Exception

### 16.1. Two Diagnostic Forms to Distinguish

| Syntax | Where Used? | Primary Information |
|---|---|---|
| `GET [CURRENT] DIAGNOSTICS ...` | During normal PL/pgSQL execution (or in a handler if current context is needed) | `ROW_COUNT`, `PG_CONTEXT` |
| `GET STACKED DIAGNOSTICS ...` | Inside an `EXCEPTION` handler processing an error | `RETURNED_SQLSTATE`, `MESSAGE_TEXT`, `PG_EXCEPTION_*`, and object metadata |

`GET STACKED DIAGNOSTICS` is not for retrieving row counts after an UPDATE. It is specifically for **the exception currently being caught**.

### 16.2. Common Stacked Diagnostic Items

| Item | Meaning |
|---|---|
| `RETURNED_SQLSTATE` | 5-character SQLSTATE code of the error |
| `MESSAGE_TEXT` | Primary error message |
| `PG_EXCEPTION_DETAIL` | Error detail text, if available |
| `PG_EXCEPTION_HINT` | Error hint text, if available |
| `PG_EXCEPTION_CONTEXT` | Execution stack/path at the point of error |
| `COLUMN_NAME` | Related column name, if provided |
| `CONSTRAINT_NAME` | Related constraint name, if provided |
| `DATATYPE_NAME` | Related data type, if provided |
| `TABLE_NAME` | Related table, if provided |
| `SCHEMA_NAME` | Related schema, if provided |

Not every error populates all fields. Missing fields return empty strings; never assume `CONSTRAINT_NAME` is always populated.

### 16.3. Example: Catching a Unique Key Violation

~~~sql
DO $$
DECLARE
    v_state text;
    v_message text;
    v_constraint text;
    v_detail text;
BEGIN
    INSERT INTO pl_diag_lab.customers
        (customer_id,customer_code,customer_name,customer_status)
    VALUES
        (101,'C999','Duplicate ID','active');
EXCEPTION
    WHEN unique_violation THEN
        GET STACKED DIAGNOSTICS
            v_state = RETURNED_SQLSTATE,
            v_message = MESSAGE_TEXT,
            v_constraint = CONSTRAINT_NAME,
            v_detail = PG_EXCEPTION_DETAIL;

        RAISE NOTICE
            'sqlstate=%, constraint=%, message=%',
            v_state,v_constraint,v_message;
END $$;
~~~

Because the lab already has customer 101, the INSERT violates the PK and the handler runs. No duplicate customer 101 row is inserted.

### 16.4. SQLSTATE and Condition Names

PostgreSQL defines 5-character SQLSTATE codes; common ones include:

| Exception Name | SQLSTATE | Typical Cause |
|---|---|---|
| `unique_violation` | `23505` | PK or UNIQUE conflict |
| `foreign_key_violation` | `23503` | FK target missing or still referenced |
| `not_null_violation` | `23502` | Writing NULL to a NOT NULL column |
| `check_violation` | `23514` | CHECK constraint failed |
| `no_data_found` | `P0002` | `SELECT INTO STRICT` returned 0 rows |
| `too_many_rows` | `P0003` | `SELECT INTO STRICT` returned multiple rows |
| `raise_exception` | `P0001` | `RAISE EXCEPTION` without a custom code |
| `division_by_zero` | `22012` | Division by zero |
| `serialization_failure` | `40001` | Isolation conflict / retry needed |
| `deadlock_detected` | `40P01` | Deadlock detected by PostgreSQL |

These are only a subset of PL/pgSQL errors; rely on exact `SQLSTATE` values from handlers rather than parsing error text that can vary across versions or locales.

### 16.5. SQLSTATE and SQLERRM Inside a Handler

Inside an `EXCEPTION` handler, PL/pgSQL provides special variables `SQLSTATE` and `SQLERRM` directly.

~~~sql
DO $$
BEGIN
    RAISE EXCEPTION 'Test failure';
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'SQLSTATE=%, message=%',
            SQLSTATE, SQLERRM;
END $$;
~~~

These variables are **only meaningful/available inside an exception-handling context**; never treat them as persistent state after ordinary SELECTs or UPDATEs.

### 16.6. PG_EXCEPTION_CONTEXT vs. PG_CONTEXT

~~~sql
DO $$
DECLARE
    v_error_context text;
    v_current_context text;
BEGIN
    PERFORM 1 / 0;
EXCEPTION
    WHEN division_by_zero THEN
        GET STACKED DIAGNOSTICS
            v_error_context = PG_EXCEPTION_CONTEXT;

        GET DIAGNOSTICS
            v_current_context = PG_CONTEXT;

        RAISE NOTICE 'Error origin:%',
            chr(10) || v_error_context;
        RAISE NOTICE 'Current handler:%',
            chr(10) || v_current_context;
END $$;
~~~

`v_error_context` describes where the error occurred; `v_current_context` describes where code is currently executing inside the handler.

### 16.7. Never Expose Sensitive Error Details

`PG_EXCEPTION_DETAIL` may contain conflicting key values or other sensitive data. Log it only to protected logs per operational policy; never return raw messages, details, hints, or stacks directly to clients.

---

## 17. Exception Blocks and Rollback of In-Block Changes

### 17.1. A Block with EXCEPTION Uses a Subtransaction Mechanism

In PL/pgSQL, when an error is caught by `EXCEPTION`, database changes **made inside that block before the error** are rolled back. However, PL/pgSQL local variables keep their values at the moment control entered the handler.

### 17.2. Example: An INSERT Before an Error

~~~sql
DO $$
DECLARE
    v_step text := 'initial';
BEGIN
    BEGIN
        INSERT INTO pl_diag_lab.customers
            (customer_id,customer_code,customer_name,customer_status)
        VALUES
            (900,'C900','Temporary','active');

        v_step := 'after first insert';

        INSERT INTO pl_diag_lab.customers
            (customer_id,customer_code,customer_name,customer_status)
        VALUES
            (101,'C101X','Duplicate ID','active');
    EXCEPTION
        WHEN unique_violation THEN
            RAISE NOTICE 'Step reached: %', v_step;
    END;
END $$;
~~~

When the second INSERT violates the PK, the first INSERT **inside the `EXCEPTION` block** is also rolled back. `v_step` still holds `'after first insert'` inside the handler, illustrating that PL/pgSQL variables do not roll back like database row changes.

### 17.3. Verify the Data

~~~sql
SELECT COUNT(*)
FROM pl_diag_lab.customers
WHERE customer_id=900;
~~~

Expected: `0` when starting from clean lab data, because the inner block rolled back.

### 17.4. Catching an Exception Does Not Commit the Transaction

An `EXCEPTION` handler allows a function to continue, but it never commits any transaction. If the caller rolls back the outer transaction, all remaining uncommitted changes are rolled back as well.

### 17.5. Never Catch OTHERS and Silently Ignore All Errors

An anti-pattern that makes debugging painful:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        RETURN NULL;
~~~

This hides permission, schema, constraint, deadlock, type, and logic errors behind an indistinguishable NULL result. Catch **only errors that business logic truly knows how to handle**; otherwise use `RAISE;` to rethrow after minimal safe logging.

### 17.6. Never Catch Serialization/Deadlock Errors and Pretend Success

Errors `40001` and `40P01` generally require **retrying the entire transaction at the application layer**. Never catch them and return `FOUND=false`, because they do not mean "row not found."

---

## 18. When to Use RAISE; to Rethrow an Error?

### 18.1. Log Safely, Then Rethrow

~~~sql
DO $$
DECLARE
    v_state text;
    v_message text;
BEGIN
    PERFORM 1 / 0;
EXCEPTION
    WHEN OTHERS THEN
        GET STACKED DIAGNOSTICS
            v_state = RETURNED_SQLSTATE,
            v_message = MESSAGE_TEXT;

        RAISE NOTICE 'Failure SQLSTATE=%, message=%',
            v_state, v_message;
        RAISE;
END $$;
~~~

This example **intentionally rethrows the error** for demonstration, so running the `DO` block ultimately fails with `division_by_zero`. In applications, callers catch exceptions at the appropriate boundary; do not run this in a deployment pipeline expecting all statements to pass.

### 18.2. RAISE EXCEPTION with a Custom SQLSTATE

~~~sql
RAISE EXCEPTION 'Order % does not exist', p_order_id
    USING ERRCODE = 'P0002';
~~~

You can specify condition names or valid SQLSTATE codes. However, **avoid reusing system error codes arbitrarily** when APIs need to distinguish multiple scenarios; define a clear, consistent error contract.

### 18.3. Reading SQLSTATE Beats Parsing Error Messages

PostgreSQL error messages can embed column names, schema names, and constraint names, and may change across versions or locales. When deciding on retries or classifying unique/FK errors, use `RETURNED_SQLSTATE` or condition names—not substring matching on English text like `"duplicate key"`.

### 18.4. Pattern for Handling Unique Violations by Constraint Name

~~~sql
DO $$
DECLARE
    v_constraint text;
BEGIN
    INSERT INTO pl_diag_lab.customers
        (customer_id,customer_code,customer_name,customer_status)
    VALUES
        (101,'CXXX','Duplicate','active');
EXCEPTION
    WHEN unique_violation THEN
        GET STACKED DIAGNOSTICS
            v_constraint = CONSTRAINT_NAME;

        IF v_constraint = 'customers_pkey' THEN
            RAISE NOTICE 'Customer ID already exists';
        ELSE
            RAISE;
        END IF;
END $$;
~~~

This relies on the actual PK constraint name; if you rename constraints or migrate schemas, update the check accordingly. **Explicitly name constraints in migrations** if application logic inspects them, and never mask unique violations from other constraints.

---

## 19. Complete Function: Looking Up a Customer with Clear Results

### 19.1. Lookup by Primary Key, Without STRICT

~~~sql
CREATE OR REPLACE FUNCTION pl_diag_lab.get_customer_name(
    p_customer_id bigint
)
RETURNS text
LANGUAGE plpgsql
AS $$
DECLARE
    v_name text;
BEGIN
    SELECT customer_name
      INTO v_name
      FROM pl_diag_lab.customers
     WHERE customer_id=p_customer_id;

    IF NOT FOUND THEN
        RETURN NULL;
    END IF;

    RETURN v_name;
END;
$$;
~~~

Test:

~~~sql
SELECT pl_diag_lab.get_customer_name(101) AS existing_name;
SELECT pl_diag_lab.get_customer_name(999) AS missing_name;
~~~

Expected: `'An'` and `NULL`.

### 19.2. A Limitation of Returning NULL

If `customer_name` were nullable, returning NULL would be ambiguous between "customer does not exist" and "customer exists with NULL name." In our lab, `NOT NULL` prevents that ambiguity. In real systems, return a **composite status/result**, use `STRICT` with an exception, or return a `FOUND` flag alongside the value.

### 19.3. STRICT Function with a Specific Exception

~~~sql
CREATE OR REPLACE FUNCTION pl_diag_lab.get_customer_name_strict(
    p_customer_id bigint
)
RETURNS text
LANGUAGE plpgsql
AS $$
DECLARE
    v_name text;
BEGIN
    SELECT customer_name
      INTO STRICT v_name
      FROM pl_diag_lab.customers
     WHERE customer_id=p_customer_id;

    RETURN v_name;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE EXCEPTION 'Customer % not found', p_customer_id
            USING ERRCODE = 'P0002';
END;
$$;
~~~

Success test:

~~~sql
SELECT pl_diag_lab.get_customer_name_strict(101);
~~~

For 999, the function raises an exception. This is appropriate when "customer must exist" is a mandatory **precondition**, not a normal empty result.

### 19.4. Catching TOO_MANY_ROWS Still Requires Schema Constraints

Because `WHERE` filters on the PRIMARY KEY `customer_id`, valid data guarantees at most one row. `STRICT` handles missing rows, while `TOO_MANY_ROWS` cannot happen unless the query or schema changes. The PK—not `STRICT`—is what guarantees uniqueness.

---

## 20. Complete Function: Updating an Order and Returning Row Count

### 20.1. Function That Only Updates Orders in 'new' Status

~~~sql
CREATE OR REPLACE FUNCTION pl_diag_lab.mark_order_paid(
    p_order_id bigint
)
RETURNS TABLE (
    was_updated boolean,
    affected_rows bigint
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_rows bigint;
    v_found boolean;
BEGIN
    UPDATE pl_diag_lab.orders
       SET order_status='paid'
     WHERE order_id=p_order_id
       AND order_status='new';

    v_found := FOUND;
    GET DIAGNOSTICS v_rows = ROW_COUNT;

    was_updated := v_found;
    affected_rows := v_rows;

    RETURN NEXT;
END;
$$;
~~~

### 20.2. Test Safely Inside a Transaction

~~~sql
BEGIN;

SELECT *
FROM pl_diag_lab.mark_order_paid(1001);

SELECT order_id,order_status
FROM pl_diag_lab.orders
WHERE order_id=1001;

ROLLBACK;
~~~

With baseline data, the function returns `was_updated=true` and `affected_rows=1`; inside the transaction order 1001 becomes `paid`, then `ROLLBACK` restores `new`.

### 20.3. Calling with a Nonexistent Order

~~~sql
SELECT *
FROM pl_diag_lab.mark_order_paid(-999);
~~~

Expected: `false`, `0`. The function does not turn "0 rows updated" into an SQL exception, which can be a valid response depending on the API contract.

### 20.4. Do Not Conflate "Not Found" with "Invalid State"

With the function above, `was_updated=false` has two possible causes:

1. No order exists with that ID.
2. The order exists, but its status is not `new` (already `paid` or `canceled`).

If business logic must distinguish these two cases, add a lookup query / status code and proper concurrency control. You cannot tell them apart from `ROW_COUNT=0` alone when the WHERE clause checks both ID and status.

### 20.5. Concurrency and Atomic UPDATE

~~~sql
UPDATE pl_diag_lab.orders
SET order_status='paid'
WHERE order_id=p_order_id
  AND order_status='new';
~~~

This checks the precondition and updates atomically under PostgreSQL transaction semantics, which is generally safer than an application flow of "SELECT status → if new, run unguarded UPDATE" that invites race conditions.

Still, a single UPDATE does not solve every business problem: real payments need idempotency keys, locks/constraints, and consistency with external side effects. `FOUND=true` does not prove money was transferred or external services succeeded.

---

## 21. SELECT INTO STRICT vs. RETURNING INTO: Avoiding Redundant Queries

### 21.1. Read-Then-Update Pattern

~~~sql
SELECT amount INTO STRICT v_amount
FROM pl_diag_lab.orders
WHERE order_id=p_order_id;

UPDATE pl_diag_lab.orders
SET amount=v_amount + 10
WHERE order_id=p_order_id;
~~~

If another transaction modifies `amount` between the SELECT and UPDATE, this pattern risks computing from a stale value under certain isolation levels. Use it only with proper locking or isolation.

### 21.2. Direct Atomic Update Pattern

~~~sql
UPDATE pl_diag_lab.orders
SET amount=amount + 10
WHERE order_id=p_order_id
RETURNING amount INTO v_amount;
~~~

One SQL statement computes the new value from the current row and returns `v_amount`. Because `order_id` is the PK, `RETURNING` produces at most one row, fitting a scalar `INTO` target.

### 21.3. Handling Zero Rows

After UPDATE:

~~~sql
v_was_updated := FOUND;
GET DIAGNOSTICS v_rows = ROW_COUNT;
~~~

If no row matched, `v_amount` is NULL and `FOUND=false`. If the amount column were nullable, never rely on `v_amount IS NULL` to detect missing rows; inspect `FOUND` or `ROW_COUNT`.

### 21.4. When Multiple Rows Are Updated

Never use scalar `RETURNING INTO` after a multi-row UPDATE hoping it will "pick the first row." Multi-row `RETURNING` into a scalar target raises an error even without `STRICT`. Use a set-returning design or read `ROW_COUNT` instead.

---

## 22. Why Are Assignment, SELECT INTO, and GET DIAGNOSTICS Easily Confused?

### 22.1. Three Similar-Looking Lines with Different Data Sources

~~~sql
v_amount := 120.00;

SELECT amount INTO v_amount
FROM pl_diag_lab.orders
WHERE order_id=1001;

GET DIAGNOSTICS v_count = ROW_COUNT;
~~~

| Line | Effect on Variable | Reads Table Rows? | Sets FOUND from Statement? |
|---|---|---|---|
| `v_amount := 120.00` | Assigns literal/expression | Not necessarily | Assignment does not alter `FOUND` |
| `SELECT ... INTO` | Assigns from query result | Yes | Sets `FOUND` true/false |
| `GET DIAGNOSTICS` | Assigns diagnostic metadata like `ROW_COUNT` | Reads internal command status, not a business query | Does not infer `FOUND` of another query |

### 22.2. Non-STRICT SELECT INTO Does Not Count All Matching Rows

If:

~~~sql
SELECT order_id INTO v_id
FROM pl_diag_lab.orders
WHERE customer_id=101;
~~~

matches two orders, you **cannot** infer `ROW_COUNT=2` to conclude "the customer has two orders." Non-STRICT `SELECT INTO` only assigns one row; to count all matching rows, write:

~~~sql
SELECT COUNT(*) INTO v_order_count
FROM pl_diag_lab.orders
WHERE customer_id=101;
~~~

### 22.3. FOUND Does Not Keep a History Across Multiple Statements

SQL A sets `FOUND=true`, then SQL B sets `FOUND=false`; after B, no built-in variable preserves A's status. To track individual steps, save flags explicitly:

~~~sql
v_found_customer := FOUND;
v_rows_updated := v_rows;
~~~

### 22.4. ROW_COUNT Is Not Always "Rows Returned to HTTP"

DML `ROW_COUNT` reports rows processed by that SQL statement, not the record count an API response returns. For functions returning aggregates or paginated slices, output row count can differ from affected table rows.

### 22.5. Diagnostic Reads Must Be Tightly Coupled in Time

If you add a `PERFORM` or another SQL statement **between DML and `GET DIAGNOSTICS`** while debugging, you overwrite what you are trying to measure. Always capture `FOUND` and `ROW_COUNT` immediately after the target statement before logging or branching.

---

## 23. SELECT INTO with JOIN and Row Multiplication

### 23.1. A JOIN Can Return Multiple Rows Even When Filtering on a Primary Key

~~~sql
DO $$
DECLARE
    v_order_id bigint;
BEGIN
    SELECT o.order_id
      INTO v_order_id
      FROM pl_diag_lab.customers AS c
      JOIN pl_diag_lab.orders AS o
        ON o.customer_id=c.customer_id
     WHERE c.customer_id=101;

    RAISE NOTICE 'One of the order IDs: %', v_order_id;
END $$;
~~~

The `WHERE` clause selects one customer by PK, but the JOIN produces **two orders**. Without `STRICT`, one row is picked without a guaranteed `ORDER BY`.

### 23.2. Detecting More Than One Order

~~~sql
DO $$
DECLARE
    v_order_id bigint;
BEGIN
    SELECT o.order_id
      INTO STRICT v_order_id
      FROM pl_diag_lab.orders AS o
     WHERE o.customer_id=101;
EXCEPTION
    WHEN TOO_MANY_ROWS THEN
        RAISE NOTICE 'Customer has multiple orders';
END $$;
~~~

### 23.3. Fetching the Latest Order

~~~sql
SELECT order_id
  INTO v_order_id
  FROM pl_diag_lab.orders
 WHERE customer_id=101
 ORDER BY created_at DESC,order_id DESC
 LIMIT 1;
~~~

### 23.4. Fetching All Orders

Do not use scalar `SELECT INTO`. Alternatives include:

~~~sql
SELECT array_agg(order_id ORDER BY order_id)
INTO v_order_ids
FROM pl_diag_lab.orders
WHERE customer_id=101;
~~~

This returns **one aggregate row** containing an array of IDs. If there are no orders, `array_agg` returns NULL; wrap with `COALESCE(array_agg(...), '{}'::bigint[])` if you want an empty array.

Alternatively, use a cursor, `FOR` query loop, or `RETURN QUERY` in a set-returning function depending on row volume and processing needs.

### 23.5. SELECT INTO Is Not an Automatic Cursor

`SELECT INTO` does not create a cursor for iterating rows, nor does it loop over all rows like `FOR r IN SELECT ... LOOP`. It simply assigns a single target.

---

## 24. Cursors and FOUND in FETCH / MOVE

### 24.1. Simple Cursor Example

~~~sql
DO $$
DECLARE
    cur_orders CURSOR FOR
        SELECT order_id
        FROM pl_diag_lab.orders
        ORDER BY order_id;
    v_id bigint;
    v_fetch_found boolean;
BEGIN
    OPEN cur_orders;

    FETCH cur_orders INTO v_id;
    v_fetch_found := FOUND;

    RAISE NOTICE 'first=%; fetched=%', v_id, v_fetch_found;

    CLOSE cur_orders;
END $$;
~~~

`FETCH` sets `FOUND=true` if a row was retrieved, and `false` when no row remains.

### 24.2. When a Cursor Is Exhausted

~~~sql
DO $$
DECLARE
    cur_orders CURSOR FOR
        SELECT order_id
        FROM pl_diag_lab.orders
        WHERE order_id<0;
    v_id bigint;
BEGIN
    OPEN cur_orders;
    FETCH cur_orders INTO v_id;
    RAISE NOTICE 'FOUND=%; id=%', FOUND, v_id;
    CLOSE cur_orders;
END $$;
~~~

With no negative order IDs in the lab, `FOUND=false`.

### 24.3. MOVE Updates FOUND Based on Rows Traversed

`MOVE` repositions a cursor without returning row data like `FETCH`. If `MOVE` advances by one or more rows, `FOUND` becomes `true`; if not, `false`. Do not confuse this with `UPDATE`/`DELETE`: this applies strictly to cursor movement.

### 24.4. FETCH Can Overwrite FOUND

~~~sql
UPDATE pl_diag_lab.orders
SET order_status='paid'
WHERE order_id=1001;

-- FETCH cur_orders INTO v_id; -- if added here, FOUND reflects FETCH
IF FOUND THEN
    ...
END IF;
~~~

This is illustrative logic; do not run an actual UPDATE if you are only reading code. To verify whether the UPDATE matched a row, save `v_updated := FOUND` immediately after UPDATE **before calling `FETCH`**.

---

## 25. FOUND in RETURN QUERY and Set-Returning Functions

### 25.1. Function Returning Multiple Rows

~~~sql
CREATE OR REPLACE FUNCTION pl_diag_lab.list_customer_orders(
    p_customer_id bigint
)
RETURNS TABLE (
    order_id bigint,
    amount numeric,
    order_status text
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_had_rows boolean;
BEGIN
    RETURN QUERY
    SELECT o.order_id,o.amount,o.order_status
    FROM pl_diag_lab.orders AS o
    WHERE o.customer_id=p_customer_id
    ORDER BY o.order_id;

    v_had_rows := FOUND;

    IF NOT v_had_rows THEN
        RAISE NOTICE 'Customer % has no orders',p_customer_id;
    END IF;
END;
$$;
~~~

Test:

~~~sql
SELECT *
FROM pl_diag_lab.list_customer_orders(101);
~~~

Expected: two rows (orders 1001 and 1002).

### 25.2. RETURN QUERY Sets FOUND Without Exiting the Function

`RETURN QUERY` appends rows to the set-returning PL/pgSQL function's output buffer; execution continues with subsequent statements. A bare `RETURN;` (with no expression in a set-returning function) terminates execution.

### 25.3. Subsequent RETURN QUERY Calls

If a function executes multiple `RETURN QUERY` statements, `FOUND` reflects only the **most recent** `RETURN QUERY`, not "whether any row has ever been emitted in this function." Maintain an explicit counter or flag if you need cumulative status.

### 25.4. Dynamic RETURN QUERY EXECUTE

In set-returning functions with dynamic SQL, `RETURN QUERY EXECUTE` also updates `FOUND` based on rows appended. Do not confuse this with ordinary `EXECUTE dynamic_sql INTO ...`, which **does not update `FOUND`**.

---

## 26. Trigger Functions and FOUND

### 26.1. PL/pgSQL Triggers Have Additional Context Variables

In trigger functions, you routinely see `NEW`, `OLD`, `TG_OP`, and `TG_TABLE_NAME`. These do not replace `FOUND` or `ROW_COUNT`.

- `NEW`: new row (where applicable).
- `OLD`: old row (where applicable).
- `TG_OP`: `INSERT`, `UPDATE`, or `DELETE`.
- `FOUND`: still reflects PL/pgSQL statements inside the trigger function that update `FOUND`.

### 26.2. A Trigger Does Not Receive the Outer Statement's Total Affected Rows via FOUND

In a row-level trigger, the row count of the outer UPDATE statement is not mirrored into `FOUND` inside the trigger. `FOUND` inside a trigger invocation is local to the SQL statements executed by that trigger function.

### 26.3. DML Inside Triggers Can Affect Captured Command Status

If a trigger function executes its own INSERT/UPDATE/DELETE and you call `GET DIAGNOSTICS ROW_COUNT` inside it, that value reflects the most recent SQL command **inside the trigger function** under PL/pgSQL rules, not the outer DML statement's overall row count.

### 26.4. Designing Clear Audit Triggers

For row-by-row auditing, use `NEW`, `OLD`, and `TG_OP` according to trigger type; for auditing statement-wide batch counts, use statement-level triggers, transition tables, or caller-side logging. Never treat `FOUND` as a global event bus.

---

## 27. Logging with RAISE NOTICE and Error Management

### 27.1. RAISE Levels

Common levels:

~~~sql
RAISE DEBUG 'Debug information';
RAISE LOG 'Diagnostic event';
RAISE NOTICE 'Message for caller';
RAISE WARNING 'Warning';
RAISE EXCEPTION 'Abort on error';
~~~

Where messages appear depends on `client_min_messages`, `log_min_messages`, and server configuration. **`RAISE EXCEPTION`** transfers control to an exception handler or returns an error to the caller.

### 27.2. Never Log Sensitive Values Arbitrarily

Exception details can include primary keys, emails, or personal data. Separate restricted internal logs from public client API responses. With `GET STACKED DIAGNOSTICS`, prefer logging `SQLSTATE`, constraint names, and a request correlation ID, exposing full message/detail/context only under approved security policies.

### 27.3. Capture ROW_COUNT Before Complex Logging

~~~sql
UPDATE pl_diag_lab.orders
SET order_status='paid'
WHERE order_status='new';

GET DIAGNOSTICS v_updated = ROW_COUNT;
v_found := FOUND;

RAISE NOTICE 'Updated % rows',v_updated;
~~~

`RAISE` itself is not DML, but if a logging helper runs SQL, `FOUND`/`ROW_COUNT` will be overwritten; capturing them prior to any SQL-executing helper is a solid habit.

### 27.4. RAISE EXCEPTION Is Not a Status Return Value

Once `RAISE EXCEPTION` executes, code **does not continue** to the next line along the normal path. Never write:

~~~sql
RAISE EXCEPTION 'Not found';
IF NOT FOUND THEN
    -- Unreachable on the normal path after RAISE.
END IF;
~~~

Define your API contract clearly: either **return a status value** or **throw an exception** when missing. Each approach has trade-offs.

---

## 28. Correctness Under Concurrent Transactions

### 28.1. FOUND=true Does Not Lock Rows for Subsequent Steps

A query:

~~~sql
SELECT order_status INTO v_status
FROM pl_diag_lab.orders
WHERE order_id=p_id;

IF FOUND THEN
    -- Another transaction may alter order_status right after SELECT.
END IF;
~~~

`FOUND=true` only means the query found a row as of its snapshot. It **does not guarantee** another transaction will not modify that row immediately afterward.

### 28.2. Conditional Updates Are Usually Safer Than Separate SELECT + UPDATE

For transitioning `new → paid`:

~~~sql
UPDATE pl_diag_lab.orders
SET order_status='paid'
WHERE order_id=p_id
  AND order_status='new';
GET DIAGNOSTICS v_updated = ROW_COUNT;
~~~

A single statement avoids many read-modify-write race conditions. When additional side effects exist (such as decrementing inventory or issuing an invoice), wrap the steps in one transaction with proper constraints, idempotency, and locking.

### 28.3. SELECT FOR UPDATE

If business logic genuinely needs to read a row, evaluate rules, and update multiple tables within a transaction, use:

~~~sql
SELECT order_status
INTO STRICT v_status
FROM pl_diag_lab.orders
WHERE order_id=p_id
FOR UPDATE;
~~~

`FOR UPDATE` acquires a row lock within the transaction per PostgreSQL rules; it does not modify `order_status` itself. Ensure proper transaction boundaries and handle deadlocks/retries.

### 28.4. COUNT Followed by INSERT Has a Race Condition

Flawed idea:

~~~text
SELECT COUNT(*) INTO v_count FROM orders WHERE ...;
IF v_count=0 THEN
   INSERT ...;
END IF;
~~~

Two concurrent transactions can both observe `count=0` and both attempt to INSERT. Use a **UNIQUE constraint** with `INSERT ... ON CONFLICT` or appropriate locking/isolation to prevent duplicates.

### 28.5. ROW_COUNT Does Not Replace Data Constraints

`ROW_COUNT=1` confirms the UPDATE affected one row; it does not prove every business invariant holds if schemas, policies, or transactions are flawed. Database constraints remain essential.

### 28.6. Never Swallow serialization_failure

Under higher isolation levels, `40001` can occur. Never catch it and report "row not found." Retry the entire transaction at the transaction-management boundary using bounded retries and backoff.

---

## 29. Parameter Naming: Avoiding Column and Variable Collisions

### 29.1. Ambiguity-Prone Pattern

~~~sql
-- Avoid matching variable and column names:
SELECT amount INTO amount
FROM pl_diag_lab.orders
WHERE order_id=order_id;
~~~

`order_id` can refer to both the column and the variable, making `order_id=order_id` meaningless or raising ambiguity errors depending on configuration and context.

### 29.2. Use Prefixes and Table Aliases

~~~sql
SELECT o.amount
INTO v_amount
FROM pl_diag_lab.orders AS o
WHERE o.order_id=p_order_id;
~~~

- `p_` for parameters.
- `v_` for local variables.
- `o.` for SQL columns.

This reduces logic bugs and improves readability across multi-JOIN SQL.

### 29.3. Do Not Rely on #variable_conflict as a Default Fix

PL/pgSQL supports directives such as `#variable_conflict use_variable` and corresponding configuration settings to resolve ambiguities. Never rely on global or directive overrides to patch sloppy variable naming; **aliases and distinct prefixes** are far safer, especially in privileged functions.

### 29.4. Variables in Dynamic SQL

~~~sql
EXECUTE 'SELECT amount FROM pl_diag_lab.orders WHERE order_id=$1'
INTO v_amount
USING p_order_id;
~~~

Inside dynamic statements, `$1` binds from `USING`; it does not resolve PL/pgSQL variable names by string interpolation. Always pass parameter values via `USING` instead of concatenating text.

---

## 30. Distinguishing GET DIAGNOSTICS ROW_COUNT from Statement Statistics

### 30.1. ROW_COUNT Reflects One Just-Executed Statement

~~~sql
UPDATE pl_diag_lab.orders
SET amount=amount*1.01
WHERE customer_id=101;

GET DIAGNOSTICS v_count = ROW_COUNT;
~~~

It reports the rows updated by this single statement, not the total table size or cumulative rows across transactions.

### 30.2. ROW_COUNT Does Not Measure Whether Values Actually Changed

~~~sql
UPDATE pl_diag_lab.orders
SET order_status=order_status
WHERE customer_id=101;
~~~

Matching rows are still updated by SQL even when the logical value stays identical. `ROW_COUNT` counts rows processed by the statement, **not** only rows whose values changed.

### 30.3. An UPDATE Matching 0 Rows Still Succeeds

~~~sql
UPDATE pl_diag_lab.orders
SET amount=amount+10
WHERE order_id=-12345;
~~~

`ROW_COUNT=0`; no SQL exception is raised. The application decides whether zero affected rows is acceptable or a business error.

### 30.4. ROW_COUNT and Triggers/Rules

On tables with triggers or rewrite rules, affected row counts can behave less intuitively than "rows before vs. after." Understand PostgreSQL's command-tag / row-count rules for the actual statement rather than assuming `ROW_COUNT` summarizes cascading trigger side effects.

### 30.5. ROW_COUNT and COUNT(*)

`SELECT COUNT(*)` returns one row containing the count of matching rows. `ROW_COUNT` after that `SELECT INTO` simply reports that 1 result row was processed—it does not replace the count variable.

### 30.6. ROW_COUNT and pg_stat_statements

`pg_stat_statements` (when enabled) aggregates query metrics across many calls by query fingerprint, whereas `GET DIAGNOSTICS ROW_COUNT` reports **one statement's row count during a single function execution**. Neither replaces the other.

---

## 31. Comparing Mechanisms by Business Goal

| What Do You Need to Do? | Primary Tool | Status to Inspect |
|---|---|---|
| Assign literal/computed value | `v := expr` | Variable `v` itself |
| Read scalar from row | `SELECT ... INTO` | Target + `FOUND` |
| Catch wrong row count | `INTO STRICT` | Exceptions |
| Check existence without needing data | `PERFORM ... LIMIT 1` | `FOUND` |
| Check existence into boolean | `SELECT EXISTS(...) INTO v_exists` | `v_exists` |
| Count all matching rows | `COUNT(*) INTO v_count` | `v_count` |
| Check if DML affected rows | `UPDATE/DELETE/INSERT ...` | `FOUND` |
| Count DML-affected rows | `GET DIAGNOSTICS ... ROW_COUNT` | `bigint v_rows` |
| Single-row DML returning new values | `... RETURNING ... INTO` | Target + `FOUND` |
| Dynamic SQL single-row SELECT | `EXECUTE ... INTO ... USING` | Target + `ROW_COUNT` |
| Dynamic SQL DML | `EXECUTE ... USING` | `ROW_COUNT` |
| Inspect current execution stack | `GET DIAGNOSTICS ... PG_CONTEXT` | `text` context |
| Inspect caught error metadata | `GET STACKED DIAGNOSTICS` | `SQLSTATE`, `MESSAGE`, `DETAIL`... |
| Catch missing row explicitly | `INTO STRICT` + `WHEN NO_DATA_FOUND` | Handler |
| Iterate multi-row query | `FOR r IN SELECT ... LOOP` | `r`, counter, `FOUND` after loop |
| Return multiple rows from function | `RETURN QUERY` | Result set + `FOUND` |

---

## 32. Technique Selection Flowchart

~~~mermaid
flowchart TD
    A["Reading or modifying data in PL/pgSQL"] --> B{"Only computing an expression?"}
    B -- "Yes" --> C["Variable := expression"]
    B -- "No" --> D{"Reading or writing data?"}
    D -- "Read" --> E{"Need values or just a check?"}
    E -- "Need values" --> F{"Must be exactly one row?"}
    F -- "Yes" --> G["SELECT ... INTO STRICT"]
    F -- "No" --> H["SELECT ... INTO; check FOUND"]
    E -- "Existence only" --> I["PERFORM ...; check FOUND"]
    E -- "Need count" --> J["SELECT COUNT(*) INTO v_count"]
    D -- "Write" --> K{"Single-row RETURNING?"}
    K -- "Yes" --> L["DML ... RETURNING INTO"]
    K -- "No" --> M["DML; GET DIAGNOSTICS ROW_COUNT"]
    H --> N{"Dynamic EXECUTE?"}
    M --> N
    N -- "Yes" --> O["EXECUTE ...; read ROW_COUNT, not FOUND"]
    N -- "No" --> P["Capture FOUND/ROW_COUNT right after statement"]
    G --> Q{"Exception raised?"}
    L --> Q
    O --> Q
    Q -- "Yes" --> R["EXCEPTION ... GET STACKED DIAGNOSTICS"]
    Q -- "No" --> S["Return result per API contract"]
    R --> T["Classify SQLSTATE, log safely, retry/rethrow"]
~~~

Not every branch requires a PL/pgSQL function. When a single `UPDATE ... WHERE ... RETURNING` statement does the job cleanly, plain SQL can be clearer than a hundred-line function.

---

## 33. Common Misconceptions

| Misconception | Why It Is Wrong | Recommended Practice |
|---|---|---|
| "`:=` and `=` are always identical" | PL/pgSQL assignment differs from SQL comparison | Use `:=` for assignment and `=` for comparison |
| "Uninitialized variables default to 0" | They default to NULL | Account for NULL or set `DEFAULT` |
| "SELECT INTO inside a function creates a table" | PL/pgSQL `INTO` assigns variables | Use `CREATE TABLE AS SELECT` |
| "Non-STRICT SELECT INTO errors on >1 row" | It picks the first row | Use `STRICT` or `ORDER BY ... LIMIT 1` |
| "First row without ORDER BY always has smallest PK" | Order is never guaranteed | Add `ORDER BY` with tie-breaker |
| "0-row SELECT INTO keeps old target value" | It sets target to NULL | Check `FOUND` and target |
| "STRICT means column values cannot be NULL" | `STRICT` checks row count | Enforce `NOT NULL`/constraints if needed |
| "`COUNT(*)=0` → `FOUND=false`" | Aggregates still produce one row | Inspect `v_count` |
| "`SELECT EXISTS(false)` → `FOUND=false`" | `SELECT EXISTS` returns one boolean false row | Inspect `v_exists` |
| "`FOUND` remembers an earlier SELECT" | Subsequent statements overwrite it | Capture immediately |
| "`FOUND=true` means the SQL transaction committed" | It only reports row presence/impact | Handle transaction control separately |
| "`FOUND` tells how many rows" | It is boolean | Use `GET DIAGNOSTICS ROW_COUNT` |
| "`FOUND` after `EXECUTE` reflects dynamic SQL" | `EXECUTE` does not update `FOUND` | Use `ROW_COUNT` or `INTO STRICT` |
| "`ROW_COUNT` always equals total matching WHERE rows" | Reflects most recent SQL command | Use `COUNT(*)` when counting matches |
| "`ROW_COUNT` after `COUNT(*)` equals the count value" | `COUNT(*)` returns 1 row | Read target `v_count` |
| "`ROW_COUNT` after another `PERFORM` still reflects earlier DML" | Command status gets overwritten | Capture `ROW_COUNT` immediately |
| "`UPDATE SET x=x` does not count rows" | UPDATE still processes matching rows | `ROW_COUNT` does not measure value diffs |
| "Non-STRICT `DML RETURNING INTO` picks the first row" | Multiple RETURNING rows error | Use row count or set-returning pattern |
| "`PERFORM` does not touch `FOUND`" | `PERFORM` updates `FOUND` | Check or save state accordingly |
| "`FOR` loop sets `FOUND` the same way every iteration" | `FOR` sets `FOUND` on loop exit | Read after `END LOOP` |
| "`GET DIAGNOSTICS` retrieves error messages" | Current diagnostics hold `ROW_COUNT`/`PG_CONTEXT` | Use `GET STACKED` inside handlers |
| "`PG_CONTEXT` shows original error line" | `PG_CONTEXT` is current stack | Use `PG_EXCEPTION_CONTEXT` in handlers |
| "`SQLSTATE` is only in client drivers" | PL/pgSQL handlers can read it | Use `GET STACKED DIAGNOSTICS` |
| "Every exception should `WHEN OTHERS RETURN NULL`" | Masks logic/constraint/transaction bugs | Catch specifically, rethrow otherwise |
| "`EXCEPTION` block keeps SQL run before the error" | Changes in the block roll back when caught | Understand internal subtransactions |
| "Local variables roll back like DB rows" | Variables retain values into the handler | Never treat variables as commit proof |
| "If SELECT saw a row, it stays unchanged" | Concurrent transactions can modify it | Use atomic DML or row locking |
| "`COUNT` then `INSERT` guarantees uniqueness" | Concurrent race condition | Use `UNIQUE` + `ON CONFLICT` |
| "Colliding variable and column names are harmless" | Causes ambiguity or silent bugs | Use clear prefixes and aliases |
| "Dynamic SQL should concatenate raw user input" | SQL injection and quoting bugs | Use `USING` / `format('%I', ...)` |
| "`RAISE NOTICE` is automatic security auditing" | Logs do not replace transaction/audit policies | Implement proper auditing controls |

---

## 34. Maintainable PL/pgSQL Checklist

### 34.1. Variables and SQL

- [ ] Every variable has an explicit type and clear name (`p_`, `v_`).
- [ ] Use `%TYPE`/`%ROWTYPE` where schema alignment helps.
- [ ] Handle NULLs according to the business contract.
- [ ] Use SQL table/column aliases to prevent ambiguity.
- [ ] Never execute a bare `SELECT` producing output without `INTO`, `PERFORM`, or `RETURN QUERY`.
- [ ] Single-row SELECTs on multi-row data without `ORDER BY` have clearly understood semantics.

### 34.2. Assigning Results

- [ ] Can the query return 0 rows? Handle `FOUND`/`STRICT`.
- [ ] Can the query return multiple rows? Enforce uniqueness with `STRICT` or constraints if expecting one.
- [ ] Remember `COUNT(*)`/`EXISTS` always return one row, not a business `FOUND` flag.
- [ ] Ensure scalar `DML RETURNING INTO` targets cannot unexpectedly match multiple rows.
- [ ] Use `RETURNING INTO` on writes only when needed and cardinality is controlled.

### 34.3. FOUND and ROW_COUNT

- [ ] Capture `FOUND` immediately after the tracked statement.
- [ ] Never inspect `FOUND` after an intervening `PERFORM`/`SELECT`/`UPDATE`.
- [ ] Use `bigint` for `ROW_COUNT`.
- [ ] Place `GET DIAGNOSTICS` immediately after the target SQL statement.
- [ ] Never rely on `FOUND` after dynamic `EXECUTE`.
- [ ] Never confuse `ROW_COUNT` with `COUNT(*)`/aggregates.
- [ ] Read `FOUND` for `FOR`/`FOREACH` loops at the right moment (after `END LOOP`).

### 34.4. Exceptions

- [ ] Catch specific `SQLSTATE`/conditions; avoid unnecessary `WHEN OTHERS`.
- [ ] Use `GET STACKED DIAGNOSTICS` in handlers, not current `ROW_COUNT`.
- [ ] Never log or return sensitive `PG_EXCEPTION_DETAIL` to clients.
- [ ] Understand exception subtransactions; never treat local variables as proof of commit.
- [ ] Rethrow unhandled errors with `RAISE;`.
- [ ] Retry deadlocks and serialization failures at the transaction boundary.

### 34.5. Performance and Security

- [ ] Prefer set-based SQL over row-by-row loops where appropriate.
- [ ] Ensure indexes support key predicates.
- [ ] Do not run `SELECT COUNT(*)` solely to check existence when count is unneeded.
- [ ] Use `USING`/`format('%I', ...)` and identifier whitelists for dynamic SQL.
- [ ] Set appropriate execute privileges and `SECURITY DEFINER`/`INVOKER`.
- [ ] Write integration tests covering 0, 1, multiple rows, and constraint errors.
- [ ] Always roll back test DML runs when practicing.

---

## 35. Applied Case 1: Controlled Inventory Deduction

### 35.1. Requirements

A system needs to deduct inventory for an item. Insufficient stock must be distinguishable from a missing SKU (or handled appropriately), and deductions must stay safe when two concurrent transactions buy the same item.

### 35.2. Dedicated Illustrative Schema

~~~sql
CREATE TABLE pl_diag_lab.inventory (
    sku text PRIMARY KEY,
    available integer NOT NULL CHECK (available >= 0)
);

INSERT INTO pl_diag_lab.inventory(sku,available)
VALUES ('SKU-A',10),('SKU-B',0);
~~~

### 35.3. Deduction Function Using Conditional UPDATE

~~~sql
CREATE OR REPLACE FUNCTION pl_diag_lab.reserve_inventory(
    p_sku text,
    p_quantity integer
)
RETURNS TABLE (
    reserved boolean,
    affected_rows bigint
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_rows bigint;
BEGIN
    IF p_quantity IS NULL OR p_quantity <= 0 THEN
        RAISE EXCEPTION 'Quantity must be > 0'
            USING ERRCODE='22023'; -- invalid_parameter_value
    END IF;

    UPDATE pl_diag_lab.inventory AS i
       SET available = i.available - p_quantity
     WHERE i.sku = p_sku
       AND i.available >= p_quantity;

    GET DIAGNOSTICS v_rows = ROW_COUNT;

    reserved := (v_rows = 1);
    affected_rows := v_rows;

    RETURN NEXT;
END;
$$;
~~~

Here the UPDATE includes the stock predicate and executes atomically. `ROW_COUNT=1` means one row was deducted; `ROW_COUNT=0` means either the SKU does not exist **or** stock is insufficient—add classification logic if the API needs to distinguish those two cases.

### 35.4. Safe Test with ROLLBACK

~~~sql
BEGIN;

SELECT * FROM pl_diag_lab.reserve_inventory('SKU-A',3);
SELECT sku,available FROM pl_diag_lab.inventory WHERE sku='SKU-A';

ROLLBACK;
~~~

Expected: function returns `true, 1`; inside the transaction stock drops to 7, then `ROLLBACK` restores 10.

### 35.5. Do Not Split into Unguarded COUNT/SELECT + UPDATE

A pattern like:

~~~text
SELECT available INTO v_stock;
IF v_stock >= quantity THEN
    UPDATE inventory SET available = available-quantity;
END IF;
~~~

suffers from race conditions between concurrent purchases without proper locking/isolation. A conditional UPDATE guarding `available` is much safer in this scenario.

### 35.6. Why FOUND Alone Cannot Classify the Failure Reason

`FOUND=false` after UPDATE only says no row matched both the SKU and `available >= p_quantity`. If business logic must distinguish "SKU not found" from "out of stock," add a lookup with appropriate locking/transaction design; a single boolean cannot encode both reasons.

---

## 36. Applied Case 2: Batch UPDATE and Row-Count Auditing

### 36.1. Requirements

A batch job must cancel `new` orders created before a cutoff timestamp and record how many rows were updated.

~~~sql
CREATE TABLE pl_diag_lab.job_runs (
    run_id bigint PRIMARY KEY,
    job_name text NOT NULL,
    affected_rows bigint NOT NULL,
    finished_at timestamptz NOT NULL
);
~~~

### 36.2. Audit Function Within the Same Transaction

~~~sql
CREATE OR REPLACE FUNCTION pl_diag_lab.cancel_old_new_orders(
    p_before timestamptz,
    p_run_id bigint
)
RETURNS bigint
LANGUAGE plpgsql
AS $$
DECLARE
    v_updated bigint;
BEGIN
    UPDATE pl_diag_lab.orders
       SET order_status='canceled'
     WHERE order_status='new'
       AND created_at < p_before;

    GET DIAGNOSTICS v_updated = ROW_COUNT;

    INSERT INTO pl_diag_lab.job_runs
        (run_id,job_name,affected_rows,finished_at)
    VALUES
        (p_run_id,'cancel_old_new_orders',v_updated,clock_timestamp());

    RETURN v_updated;
END;
$$;
~~~

### 36.3. Capture ROW_COUNT Before the Audit INSERT

If you write:

~~~sql
UPDATE orders SET ...;
INSERT INTO job_runs ...;
GET DIAGNOSTICS v_updated = ROW_COUNT;
~~~

`v_updated` will reflect the **audit INSERT** (1 row), not the batch UPDATE. Always capture `ROW_COUNT` immediately after the UPDATE.

### 36.4. Test Run

~~~sql
BEGIN;

SELECT pl_diag_lab.cancel_old_new_orders(
    '2026-11-05 00:00:00+00',
    7001
);

SELECT * FROM pl_diag_lab.job_runs WHERE run_id=7001;

ROLLBACK;
~~~

The count depends on the lab state at runtime. With clean initial data, orders 1001 and 1003 are `new` before Nov 5, giving **2 rows**; order 1005 has `created_at` at `13:00 UTC` on Nov 5, so it is excluded.

### 36.5. UNIQUE Violation on Audit Insert

If `run_id` already exists, the audit INSERT raises `unique_violation`, causing the entire call (if unhandled) to fail and rolling back the preceding UPDATE under transaction semantics. For idempotency, design job keys and `ON CONFLICT` intentionally rather than blindly ignoring `unique_violation`.

---

## 37. Applied Case 3: Diagnosing Order Insertion Errors

### 37.1. Order-Insertion Function Catching Specific Errors

~~~sql
CREATE OR REPLACE FUNCTION pl_diag_lab.insert_order_safely(
    p_order_id bigint,
    p_customer_id bigint,
    p_amount numeric
)
RETURNS text
LANGUAGE plpgsql
AS $$
DECLARE
    v_state text;
    v_constraint text;
    v_message text;
BEGIN
    INSERT INTO pl_diag_lab.orders
        (order_id,customer_id,amount,order_status,created_at)
    VALUES
        (p_order_id,p_customer_id,p_amount,'new',clock_timestamp());

    RETURN 'created';
EXCEPTION
    WHEN unique_violation THEN
        GET STACKED DIAGNOSTICS
            v_state = RETURNED_SQLSTATE,
            v_constraint = CONSTRAINT_NAME;

        IF v_constraint = 'orders_pkey' THEN
            RETURN 'duplicate_order_id';
        END IF;
        RAISE;
    WHEN foreign_key_violation THEN
        GET STACKED DIAGNOSTICS
            v_state = RETURNED_SQLSTATE,
            v_constraint = CONSTRAINT_NAME,
            v_message = MESSAGE_TEXT;

        RETURN 'customer_not_found';
END;
$$;
~~~

### 37.2. Test Against Lab Data

~~~sql
SELECT pl_diag_lab.insert_order_safely(
    1001,101,75.00
);
~~~

Expected: `'duplicate_order_id'` assuming the default PK name `orders_pkey` and existing order 1001.

~~~sql
SELECT pl_diag_lab.insert_order_safely(
    3001,9999,75.00
);
~~~

Expected: `'customer_not_found'` when the FK violation triggers. No row is inserted when the exception is caught.

### 37.3. Do Not Mask Other Foreign Key Errors

In this simple example, `orders` has only one FK pointing to `customers`, so mapping `foreign_key_violation` to `customer_not_found` works. In real schemas with multiple FKs, inspect `CONSTRAINT_NAME`/`TABLE_NAME` and `RAISE;` if another constraint failed instead of returning a misleading message.

### 37.4. Never Leak PG_EXCEPTION_DETAIL to APIs

Unique/FK errors can include key values inside `DETAIL`. API responses should return meaningful error codes without leaking table names, keys, or internal stack traces.

### 37.5. Catching an Error Does Not Commit Earlier Steps

Returning `'duplicate_order_id'` only means this block caught the error. Any prior operations in the same transaction still depend on the caller's transaction boundary. Never equate a returned text status with `COMMIT`.

---

## 38. Applied Case 4: Replacing COUNT(*) with EXISTS / PERFORM

### 38.1. When You Only Need to Know Whether Active Customers Exist

Potentially wasteful approach:

~~~sql
SELECT COUNT(*) INTO v_count
FROM pl_diag_lab.customers
WHERE customer_status='active';

IF v_count > 0 THEN
    ...
END IF;
~~~

Better alternatives:

~~~sql
PERFORM 1
FROM pl_diag_lab.customers
WHERE customer_status='active'
LIMIT 1;

IF FOUND THEN
    ...
END IF;
~~~

Or:

~~~sql
SELECT EXISTS (
    SELECT 1 FROM pl_diag_lab.customers
    WHERE customer_status='active'
) INTO v_exists;

IF v_exists THEN
    ...
END IF;
~~~

### 38.2. When You Need the Exact Customer Count

If business logic genuinely needs to report "there are N active customers," `COUNT(*)` is right:

~~~sql
SELECT COUNT(*) INTO v_active_customers
FROM pl_diag_lab.customers
WHERE customer_status='active';
~~~

Never try to replace `COUNT(*)` with `FOUND` when you actually need a numeric quantity.

---

## 39. Design Decisions: Which Errors Should Surface to the API?

| Observation in PL/pgSQL | Possible Business Meaning | Appropriate Action |
|---|---|---|
| `SELECT INTO` finds no row | Object not found | Return not-found status or raise domain error |
| `INTO STRICT` `NO_DATA_FOUND` | Mandatory existence precondition violated | Catch if app expects missing; otherwise propagate |
| `INTO STRICT` `TOO_MANY_ROWS` | Query not unique | Audit schema constraints/query; rarely swallow |
| `UPDATE` `ROW_COUNT=0` | No row matched predicate | Could be missing or state conflict; differentiate if needed |
| `UPDATE` `ROW_COUNT=1` | Processed one row | Return success if remaining steps succeed |
| `UPDATE` `ROW_COUNT>1` | Set-based batch succeeded | Return count/audit as appropriate |
| `unique_violation` | Key already exists | Map specific constraint or use `ON CONFLICT` |
| `foreign_key_violation` | Invalid reference | Map by constraint name; avoid mislabeling |
| `serialization_failure` | Transaction retry needed | Retry at transaction boundary |
| `deadlock_detected` | Retry / investigate lock ordering | Never treat as missing row |
| `permission denied` | Role lacks privilege | Never disguise as empty data |
| `division_by_zero` | Input or logic bug | Validate/fix and propagate properly |

---

## 40. When to Use a PL/pgSQL Function vs. Plain SQL?

Not every need for `ROW_COUNT` justifies a stored function.

### 40.1. Plain SQL in the Application

Most database drivers already return affected-row counts directly:

~~~sql
UPDATE pl_diag_lab.orders
SET order_status='paid'
WHERE order_id=$1
  AND order_status='new';
~~~

The application can read the affected row count from the driver protocol without wrapping it in a PL/pgSQL function just to call `GET DIAGNOSTICS`.

### 40.2. PL/pgSQL Shines When

- Coordinating multiple SQL statements close to the data.
- Requiring `IF`/`LOOP`/`EXCEPTION` control flow.
- Returning structured status, row counts, and computed values per a contract.
- Classifying errors inside the DB by `SQLSTATE` or constraint name.
- Enforcing strict operation ordering and atomic semantics cleanly.

### 40.3. Single-Statement SQL Can Be Simpler and Faster

If all you need is:

~~~sql
UPDATE pl_diag_lab.orders
SET order_status='paid'
WHERE order_id=$1 AND order_status='new'
RETURNING order_id;
~~~

one SQL statement already tells the application whether a row was updated. Do not add 100 lines of PL/pgSQL if requirements do not call for it.

### 40.4. Do Not Turn Functions into Unnecessary DML Loops

Performance anti-pattern:

~~~text
FOR every order:
    UPDATE orders SET ...
END LOOP
~~~

When a single set-based UPDATE expresses the rule cleanly with no per-row external side effects, set-based SQL is far faster. `GET DIAGNOSTICS ROW_COUNT` still gives you the total rows updated by that batch statement.

---

## 41. PostgreSQL Reference Documentation

When targeting a specific PostgreSQL major version, cross-check the official documentation:

- [PL/pgSQL — Structure](https://www.postgresql.org/docs/current/plpgsql-structure.html): block structure, DECLARE, BEGIN/END, EXCEPTION.
- [PL/pgSQL — Declarations](https://www.postgresql.org/docs/current/plpgsql-declarations.html): variables, %TYPE, %ROWTYPE, RECORD, CONSTANT.
- [PL/pgSQL — Basic Statements](https://www.postgresql.org/docs/current/plpgsql-statements.html): assignment, SELECT INTO, STRICT, PERFORM, EXECUTE, GET DIAGNOSTICS.
- [PL/pgSQL — Control Structures](https://www.postgresql.org/docs/current/plpgsql-control-structures.html): FOUND, loops, RETURN QUERY, exception handling.
- [PL/pgSQL — Error Reporting](https://www.postgresql.org/docs/current/plpgsql-errors-and-messages.html): RAISE, error levels, SQLSTATE, MESSAGE/DETAIL/HINT.
- [PL/pgSQL — Trigger Functions](https://www.postgresql.org/docs/current/plpgsql-trigger.html): NEW, OLD, TG_OP, and trigger context.
- [PostgreSQL — Error Codes](https://www.postgresql.org/docs/current/errcodes-appendix.html): SQLSTATE mapping.
- [PostgreSQL — Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): concurrency, MVCC, serialization failures.
- [PostgreSQL — Data Manipulation RETURNING](https://www.postgresql.org/docs/current/dml-returning.html): values returned after DML.

`/current/` may point to a newer major version than your server runs. For version-dependent syntax or behavior, verify against your exact major version rather than guessing from another environment.

---

## 42. Practice Exercises

Exercises use `pl_diag_lab` from Section 5 unless stated otherwise. If you already ran DML examples that modified `orders`, results may differ. To check answers against clean seed data, use a fresh lab database or run changes inside a transaction with `ROLLBACK`. Some snippets below are intentionally broken to be fixed; never run them in production.

### Exercise 1 — Variable Declaration and Assignment

Write a `DO` block declaring `v_price numeric(12,2)` defaulting to `150.00` and `v_tax_rate numeric` defaulting to `0.1`. Assign `v_total := v_price * (1+v_tax_rate)` and print the result with `RAISE NOTICE`.

### Exercise 2 — NULL and Assignment

An uninitialized variable `v_a integer` is declared. What is `v_b := v_a + 5`? Show how to compute `v_b=5` when `v_a` is NULL without altering `v_a`'s original value.

### Exercise 3 — %TYPE

Declare a variable with the same type as `pl_diag_lab.orders.amount`. Assign it `199.90`.

### Exercise 4 — %ROWTYPE

Write a `DO` block using `%ROWTYPE` to fetch the full row for customer ID 101 and print `customer_code` and `customer_name`.

### Exercise 5 — record

Write a `SELECT ... INTO` query joining `customers` and `orders` to compute total order count and total amount for customer 101 into a `record` variable, then print both aggregate fields.

### Exercise 6 — SELECT INTO and New Tables

In PL/pgSQL, does `SELECT ... INTO new_table FROM ...` create a table or assign variables? Which syntax should be used if you actually want to create a table from a SELECT?

### Exercise 7 — Single-Row SELECT INTO

Write a function `get_customer_code(p_id bigint) RETURNS text` using `SELECT customer_code INTO v_code ... WHERE customer_id=p_id`, returning NULL if not found.

### Exercise 8 — Zero-Row SELECT INTO

~~~sql
DECLARE
  v_name text := 'initial';
BEGIN
  SELECT customer_name INTO v_name
  FROM pl_diag_lab.customers
  WHERE customer_id=999;
END;
~~~

After the SELECT, what are `v_name` and `FOUND`? Why is `'initial'` not kept?

### Exercise 9 — Multiple Rows Without STRICT

~~~sql
SELECT order_id INTO v_id
FROM pl_diag_lab.orders
WHERE customer_id=101;
~~~

There are two orders. Does PL/pgSQL raise `TOO_MANY_ROWS`? Is `v_id` guaranteed to be 1001?

### Exercise 10 — ORDER BY and LIMIT

Rewrite Exercise 9 to fetch the newest order by `created_at` with tie-breaker `order_id`. Does `LIMIT 1` prove the customer only has one order?

### Exercise 11 — INTO STRICT with No Rows

Write a `DO` block using `SELECT ... INTO STRICT` to look up customer 999 and catch `NO_DATA_FOUND` to emit a Notice.

### Exercise 12 — INTO STRICT with Multiple Rows

Write a `DO` block querying `order_id` for customer 101 and catching `TOO_MANY_ROWS`.

### Exercise 13 — STRICT and NULL Columns

A query returns exactly one row with `optional_note=NULL`. Does `INTO STRICT` raise `NO_DATA_FOUND`? Why or why not?

### Exercise 14 — COUNT(*) and FOUND

~~~sql
SELECT COUNT(*) INTO v_count
FROM pl_diag_lab.orders
WHERE customer_id=999;
~~~

What are the expected values of `v_count` and `FOUND`? Why?

### Exercise 15 — EXISTS and FOUND

~~~sql
SELECT EXISTS(
   SELECT 1 FROM pl_diag_lab.orders WHERE customer_id=999
) INTO v_exists;
~~~

What are `v_exists` and `FOUND`? Which variable should you check to see whether an order exists?

### Exercise 16 — PERFORM

Write a `PERFORM` statement checking if at least one order belongs to customer 101; then `IF FOUND` print `"exists"`.

### Exercise 17 — Overwritten FOUND

~~~sql
SELECT customer_name INTO v_name
FROM pl_diag_lab.customers
WHERE customer_id=999;

PERFORM 1;

IF FOUND THEN
    RAISE NOTICE 'customer found';
END IF;
~~~

Why is this code wrong? Fix it using a boolean variable `v_customer_found`.

### Exercise 18 — FOUND Upon Entering a Function

What is the initial value of `FOUND` at the start of every PL/pgSQL function call? Is it shared across two sessions or two function calls?

### Exercise 19 — FOUND with FOR LOOP

Write a `FOR r IN SELECT ... LOOP` iterating over customer 101's orders, counting iterations, and reading `FOUND` after `END LOOP`. If there are no orders, what is `FOUND` after the loop?

### Exercise 20 — FOUND with FOREACH

Write a `FOREACH` loop over `ARRAY[2,4,6]::integer[]` to sum the elements and print `FOUND` after the loop. With an empty array, what would `FOUND` be?

### Exercise 21 — 0-Row UPDATE

Write an UPDATE for order ID `-1`, then print `FOUND` and `ROW_COUNT`. Is this an SQL exception?

### Exercise 22 — ROW_COUNT Data Type

Why should the variable holding `ROW_COUNT` be declared `bigint` rather than `integer` in large batch jobs?

### Exercise 23 — ROW_COUNT Trap After Another Command

~~~sql
UPDATE pl_diag_lab.orders
SET order_status='paid'
WHERE order_status='new';

INSERT INTO pl_diag_lab.job_runs(...);

GET DIAGNOSTICS v_count = ROW_COUNT;
~~~

Which statement does `v_count` reflect? Fix the placement of `GET DIAGNOSTICS` to capture the UPDATE's row count.

### Exercise 24 — UPDATE RETURNING INTO

Write SQL incrementing order 1001's `amount` by 10 and capturing the new amount into `v_new_amount`. Inspect `FOUND` and `ROW_COUNT`.

### Exercise 25 — Multi-Row DML RETURNING

~~~sql
UPDATE pl_diag_lab.orders
SET amount=amount
WHERE customer_id=101
RETURNING order_id INTO v_order_id;
~~~

Why does this statement error even without `STRICT`? If you only want the affected row count, what should you do?

### Exercise 26 — SELECT COUNT and ROW_COUNT

After `SELECT COUNT(*) INTO v_count FROM orders WHERE status='new'`, why can `GET DIAGNOSTICS v_rows=ROW_COUNT` not replace `v_count` to get the number of `new` orders?

### Exercise 27 — EXECUTE Does Not Set FOUND

Before `EXECUTE`, `PERFORM 1` sets `FOUND=true`. A dynamic `SELECT INTO` for customer 999 returns no rows. What is `FOUND` after `EXECUTE`? What should be used to detect that the dynamic query found nothing?

### Exercise 28 — EXECUTE INTO STRICT

Write dynamic SQL fetching `customer_name` by `customer_id` using `EXECUTE ... INTO STRICT ... USING ...`. When the customer does not exist, what error is raised?

### Exercise 29 — Dynamic SQL Injection

A function receives a table name and customer ID. Write a safe dynamic `SELECT COUNT(*)`, using `format('%I.%I')` for schema/table and `USING` for customer ID. Why must you not concatenate inputs directly?

### Exercise 30 — GET DIAGNOSTICS PG_CONTEXT

Write a PL/pgSQL block saving `PG_CONTEXT` into a text variable and printing a Notice. Is this context the original stack trace of an earlier exception?

### Exercise 31 — GET STACKED DIAGNOSTICS

Write a `DO` block that intentionally violates the PK on customer 101, catches `unique_violation`, and retrieves `RETURNED_SQLSTATE`, `CONSTRAINT_NAME`, and `MESSAGE_TEXT`.

### Exercise 32 — Common SQLSTATEs

Match the SQLSTATEs `23505`, `23503`, `P0002`, `P0003`, `40001` with `unique_violation`, `foreign_key_violation`, `no_data_found`, `too_many_rows`, and `serialization_failure`.

### Exercise 33 — PG_CONTEXT vs. PG_EXCEPTION_CONTEXT

Inside a handler, you want both the line where the error occurred and the line where the handler is executing. Which two diagnostic items do you read? Why are they not interchangeable?

### Exercise 34 — EXCEPTION Subtransaction

A block with `EXCEPTION` inserts customer 900, sets `v_step='after insert'`, and then inserts customer 101 causing `unique_violation`. After catching the error, is customer 900 still in the table? What value does `v_step` hold?

### Exercise 35 — When to Rethrow?

A function catches `WHEN OTHERS`, logs `SQLSTATE`, and returns NULL. List three risks and write a `RAISE;` example rethrowing the error from the handler.

### Exercise 36 — COUNT-Then-INSERT Race Trap

Two concurrent transactions both observe `SELECT COUNT(*)=0` and then INSERT the same key. Why is there a race condition? What database constraint and SQL pattern prevent duplicates?

### Exercise 37 — SELECT FOR UPDATE

When you need to read `amount`, check a business rule, and update multiple tables in a transaction, how does `SELECT ... FOR UPDATE` help? Does `FOUND=true` take the place of a row lock?

### Exercise 38 — Interpreting ROW_COUNT=0

A paid-marking function runs `UPDATE ... WHERE order_id=p_id AND order_status='new'`. Name at least two reasons why `ROW_COUNT=0` might occur. How can you distinguish them if required?

### Exercise 39 — Job Audit Practice

Write a function `cancel_old_new_orders(p_before timestamptz) RETURNS bigint` changing `new` orders before `p_before` to `canceled` and returning the affected row count without writing an audit table.

### Exercise 40 — Large Datasets and Set-Based SQL

A function loops over 100,000 orders and runs an UPDATE per row. What approach is usually better when every row follows the same rule? How do you retrieve the affected count?

### Exercise 41 — Ambiguous Variable Name

Fix SQL containing `WHERE order_id=order_id` inside a function accepting `p_order_id` so it compares cleanly against the table column using a table alias.

### Exercise 42 — Triggers and FOUND

Why doesn't `FOUND` inside a trigger function report the outer DML statement's total affected row count? What should you use to inspect old/new row values?

### Exercise 43 — Transaction Rollback When Testing DML

Write a test block `BEGIN; DO $$ ... UPDATE ... GET DIAGNOSTICS ... $$; ROLLBACK;` to measure how many rows transition `new → paid` without keeping the changes.

### Exercise 44 — Synthesis

An API calls a stored function to:
1. Look up a customer by code.
2. Return `"customer_not_found"` if absent.
3. Update `new` orders to `paid` for that customer if present.
4. Return the updated row count.
5. On FK/UNIQUE errors, log `SQLSTATE` safely without turning the error into "not found."

Write the PL/pgSQL solution choosing appropriate `SELECT INTO`/`FOUND`/`ROW_COUNT`/`GET STACKED DIAGNOSTICS` calls and explain where each diagnostic check belongs.

---

## 43. Solutions and Practice Guide — Exercises 1 to 22

### Exercise 1 — Variable Assignment

~~~sql
DO $$
DECLARE
    v_price numeric(12,2) := 150.00;
    v_tax_rate numeric := 0.1;
    v_total numeric(12,2);
BEGIN
    v_total := v_price * (1 + v_tax_rate);
    RAISE NOTICE 'Total=%',v_total;
END $$;
~~~

Expected result: **165.00**. `:=` is the PL/pgSQL assignment operator; arithmetic on the right-hand side is evaluated and assigned to the target.

### Exercise 2 — NULL

If `v_a` is uninitialized, it is NULL; `v_a+5` is also NULL under SQL NULL propagation.

~~~sql
DO $$
DECLARE
    v_a integer;
    v_b integer;
BEGIN
    v_b := COALESCE(v_a,0) + 5;
    RAISE NOTICE 'v_a=%, v_b=%',v_a,v_b;
END $$;
~~~

`v_b=5`, while `v_a` remains NULL. Only apply a `NULL → 0` rule when business logic permits it.

### Exercise 3 — %TYPE

~~~sql
DO $$
DECLARE
    v_price pl_diag_lab.orders.amount%TYPE;
BEGIN
    v_price := 199.90;
    RAISE NOTICE 'price=%',v_price;
END $$;
~~~

`%TYPE` inherits the data type from the existing `amount` column.

### Exercise 4 — %ROWTYPE

~~~sql
DO $$
DECLARE
    v_customer pl_diag_lab.customers%ROWTYPE;
BEGIN
    SELECT *
      INTO v_customer
      FROM pl_diag_lab.customers
     WHERE customer_id=101;

    IF FOUND THEN
        RAISE NOTICE 'Code=%, name=%',
            v_customer.customer_code,
            v_customer.customer_name;
    END IF;
END $$;
~~~

With clean lab data, code is `C101` and name is `An`. The row target exposes fields matching the table.

### Exercise 5 — RECORD and GROUP BY

~~~sql
DO $$
DECLARE
    v_result record;
BEGIN
    SELECT
        c.customer_id,
        COUNT(o.order_id) AS number_of_orders,
        COALESCE(SUM(o.amount),0) AS total_amount
    INTO v_result
    FROM pl_diag_lab.customers AS c
    LEFT JOIN pl_diag_lab.orders AS o
      ON o.customer_id=c.customer_id
    WHERE c.customer_id=101
    GROUP BY c.customer_id;

    IF FOUND THEN
        RAISE NOTICE 'orders=%, total=%',
            v_result.number_of_orders,
            v_result.total_amount;
    END IF;
END $$;
~~~

Expected `number_of_orders=2`, `total_amount=375.50` on clean lab data. For nonexistent customer 999, the `GROUP BY` query produces 0 rows and `FOUND=false`.

### Exercise 6 — PL/pgSQL SELECT INTO

In PL/pgSQL, `SELECT ... INTO target` is syntax for **assigning to variables**. To create a new table from a SELECT, use SQL:

~~~sql
CREATE TABLE pl_diag_lab.customers_copy AS
SELECT *
FROM pl_diag_lab.customers;
~~~

This copies table data without automatically copying PKs, FKs, indexes, triggers, or grants. Run only when you intentionally want a new lab table.

### Exercise 7 — Function Reading Customer Code

~~~sql
CREATE OR REPLACE FUNCTION pl_diag_lab.get_customer_code(
    p_id bigint
)
RETURNS text
LANGUAGE plpgsql
AS $$
DECLARE
    v_code text;
BEGIN
    SELECT c.customer_code
      INTO v_code
      FROM pl_diag_lab.customers AS c
     WHERE c.customer_id=p_id;

    IF NOT FOUND THEN
        RETURN NULL;
    END IF;

    RETURN v_code;
END;
$$;
~~~

Test:

~~~sql
SELECT pl_diag_lab.get_customer_code(101),
       pl_diag_lab.get_customer_code(999);
~~~

Expected: `C101` and `NULL`.

### Exercise 8 — Zero Rows

After the SELECT:

- `v_name=NULL`.
- `FOUND=false`.

PL/pgSQL overwrites the target of non-STRICT `SELECT INTO` with NULL when 0 rows match instead of keeping `'initial'`. To apply a fallback value:

~~~sql
SELECT customer_name INTO v_name
FROM pl_diag_lab.customers
WHERE customer_id=999;

IF NOT FOUND THEN
    v_name := 'unknown';
END IF;
~~~

Use `FOUND` to detect missing rows rather than relying on a column value that might legitimately be NULL.

### Exercise 9 — Multiple Rows

Without `STRICT`, `SELECT INTO` takes the first row returned by the executor and **does not raise `TOO_MANY_ROWS`**. Without `ORDER BY`, `v_id` is not guaranteed to be 1001 or 1002 in any business order.

### Exercise 10 — Fetching the Newest Order

~~~sql
SELECT o.order_id
INTO v_id
FROM pl_diag_lab.orders AS o
WHERE o.customer_id=101
ORDER BY o.created_at DESC,o.order_id DESC
LIMIT 1;
~~~

In the initial lab data, order 1002 is newer than 1001. `LIMIT 1` means "pick one row," not "verify the customer only has one order."

### Exercise 11 — NO_DATA_FOUND

~~~sql
DO $$
DECLARE
    v_name text;
BEGIN
    SELECT c.customer_name
    INTO STRICT v_name
    FROM pl_diag_lab.customers AS c
    WHERE c.customer_id=999;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE NOTICE 'Customer 999 not found';
END $$;
~~~

`SELECT INTO STRICT` raises `NO_DATA_FOUND` (SQLSTATE `P0002`) when the query returns 0 rows.

### Exercise 12 — TOO_MANY_ROWS

~~~sql
DO $$
DECLARE
    v_id bigint;
BEGIN
    SELECT o.order_id
    INTO STRICT v_id
    FROM pl_diag_lab.orders AS o
    WHERE o.customer_id=101;
EXCEPTION
    WHEN TOO_MANY_ROWS THEN
        RAISE NOTICE 'Multiple orders found';
END $$;
~~~

The baseline lab data has orders 1001 and 1002. `STRICT` requires one row, so it raises `TOO_MANY_ROWS` (SQLSTATE `P0003`).

### Exercise 13 — STRICT Allows NULL Columns

If a query returns **exactly one row** whose column value is NULL, `INTO STRICT` **succeeds** and assigns NULL to the target. `STRICT` checks row cardinality, not column `NOT NULL` constraints—those must be enforced separately by schema or validation.

### Exercise 14 — COUNT(*) and FOUND

`v_count=0`, **`FOUND=true`**, because ungrouped `COUNT(*)` returns **one row** containing 0. To check whether orders exist, test `IF v_count>0`, not `IF FOUND`.

### Exercise 15 — EXISTS and FOUND

`v_exists=false`, **`FOUND=true`**. `SELECT EXISTS` returns one boolean false row, so `FOUND` reflects that a row was returned. Inspect `v_exists`.

### Exercise 16 — PERFORM

~~~sql
DO $$
BEGIN
    PERFORM 1
    FROM pl_diag_lab.orders
    WHERE customer_id=101
    LIMIT 1;

    IF FOUND THEN
        RAISE NOTICE 'exists';
    END IF;
END $$;
~~~

`PERFORM` discards the row data while updating `FOUND` based on whether any row was produced.

### Exercise 17 — Overwritten FOUND

The initial SELECT finds no row, setting `FOUND=false`. Then `PERFORM 1` produces a row and sets `FOUND=true`, causing the `IF` to lie about the customer.

Fix:

~~~sql
DO $$
DECLARE
    v_name text;
    v_customer_found boolean;
BEGIN
    SELECT customer_name INTO v_name
    FROM pl_diag_lab.customers
    WHERE customer_id=999;

    v_customer_found := FOUND;

    PERFORM 1;

    IF v_customer_found THEN
        RAISE NOTICE 'customer found';
    ELSE
        RAISE NOTICE 'customer not found';
    END IF;
END $$;
~~~

### Exercise 18 — Initial State

`FOUND=false` at the start of every PL/pgSQL function call. It is local to that invocation—never shared across sessions or persisted across separate function calls.

If an SQL statement updates `FOUND` inside a nested child function, the caller does not inherit the child's internal `FOUND`; the caller's `FOUND` reflects the caller's own statements.

### Exercise 19 — FOR Query

~~~sql
DO $$
DECLARE
    r record;
    v_count integer := 0;
    v_loop_had_rows boolean;
BEGIN
    FOR r IN
        SELECT order_id
        FROM pl_diag_lab.orders
        WHERE customer_id=101
        ORDER BY order_id
    LOOP
        v_count := v_count+1;
    END LOOP;

    v_loop_had_rows := FOUND;
    RAISE NOTICE 'iterations=%, found=%',
        v_count,v_loop_had_rows;
END $$;
~~~

Expected: `v_count=2` and `FOUND=true` after the loop. If the query returns 0 rows, the loop body never executes and `FOUND` after `END LOOP` is `false`.

### Exercise 20 — FOREACH

~~~sql
DO $$
DECLARE
    v_number integer;
    v_sum integer := 0;
    v_had_iterations boolean;
BEGIN
    FOREACH v_number IN ARRAY ARRAY[2,4,6]::integer[]
    LOOP
        v_sum := v_sum + v_number;
    END LOOP;

    v_had_iterations := FOUND;

    RAISE NOTICE 'sum=%, found=%',v_sum,v_had_iterations;
END $$;
~~~

Expected: `sum=12`, `FOUND=true`. With `ARRAY[]::integer[]`, 0 iterations run and `FOUND` becomes `false` when the loop ends.

### Exercise 21 — Zero-Row UPDATE

~~~sql
DO $$
DECLARE
    v_rows bigint;
    v_found boolean;
BEGIN
    UPDATE pl_diag_lab.orders
       SET order_status='paid'
     WHERE order_id=-1;

    v_found := FOUND;
    GET DIAGNOSTICS v_rows = ROW_COUNT;

    RAISE NOTICE 'found=%, row_count=%',
        v_found,v_rows;
END $$;
~~~

Expected: `found=false`, `row_count=0`. Updating 0 rows is a successful statement, **not an exception**.

### Exercise 22 — ROW_COUNT bigint

A bulk UPDATE across billions of rows can exceed the signed 32-bit `integer` limit (~2.147 billion). Declaring `ROW_COUNT` targets as `bigint` accommodates large counts and matches PostgreSQL's diagnostic type.

---

## 44. Solutions and Practice Guide — Exercises 23 to 44

### Exercise 23 — Place GET DIAGNOSTICS Right After UPDATE

In the original snippet, `GET DIAGNOSTICS ROW_COUNT` ran after inserting into `job_runs`, so it measured the INSERT instead of the batch UPDATE.

Fix:

~~~sql
UPDATE pl_diag_lab.orders
SET order_status='paid'
WHERE order_status='new';

GET DIAGNOSTICS v_updated = ROW_COUNT;

INSERT INTO pl_diag_lab.job_runs
    (run_id,job_name,affected_rows,finished_at)
VALUES
    (7002,'mark_orders_paid',v_updated,clock_timestamp());
~~~

Assuming `job_runs` exists and `run_id=7002` is unused. Wrap in a transaction and `ROLLBACK` when testing.

### Exercise 24 — UPDATE RETURNING INTO

~~~sql
DO $$
DECLARE
    v_new_amount numeric(12,2);
    v_found boolean;
    v_rows bigint;
BEGIN
    UPDATE pl_diag_lab.orders
       SET amount=amount+10
     WHERE order_id=1001
     RETURNING amount INTO v_new_amount;

    v_found := FOUND;
    GET DIAGNOSTICS v_rows = ROW_COUNT;

    RAISE NOTICE 'amount=%, found=%, count=%',
        v_new_amount,v_found,v_rows;
END $$;
~~~

With order 1001 present, `ROW_COUNT=1` and `FOUND=true`. Because this executes real DML, run inside `BEGIN; ... ROLLBACK;` in the lab to preserve baseline data.

### Exercise 25 — Multi-Row RETURNING

Updating by `customer_id=101` matches two orders. With scalar `RETURNING order_id INTO v_order_id`, PL/pgSQL raises `TOO_MANY_ROWS` **even without `STRICT`**.

If you only need the row count:

~~~sql
DO $$
DECLARE
    v_rows bigint;
BEGIN
    UPDATE pl_diag_lab.orders
       SET amount=amount
     WHERE customer_id=101;

    GET DIAGNOSTICS v_rows = ROW_COUNT;
    RAISE NOTICE 'updated=%',v_rows;
END $$;
~~~

On baseline data, `v_rows=2`. To capture all order IDs, use a set-returning SQL pattern rather than a single scalar variable.

### Exercise 26 — COUNT(*) Is Not ROW_COUNT

Ungrouped `SELECT COUNT(*)` returns **one row** holding the count. `v_count` holds the total number of `new` orders; `ROW_COUNT` only reports how many result rows the SQL statement returned (1). Therefore, read `v_count`.

### Exercise 27 — Dynamic EXECUTE Does Not Set FOUND

`FOUND` remains `true` from the preceding `PERFORM 1`. Dynamic SQL finds no customer, yet `EXECUTE` never updates `FOUND`.

~~~sql
DO $$
DECLARE
    v_name text;
    v_rows bigint;
BEGIN
    PERFORM 1;

    EXECUTE
        'SELECT customer_name FROM pl_diag_lab.customers
         WHERE customer_id=$1'
    INTO v_name
    USING 999;

    GET DIAGNOSTICS v_rows = ROW_COUNT;

    IF v_rows=0 THEN
        RAISE NOTICE 'Dynamic query found no customer';
    END IF;
END $$;
~~~

To raise an exception unless exactly one row matches, use dynamic `INTO STRICT`.

### Exercise 28 — Dynamic INTO STRICT

~~~sql
DO $$
DECLARE
    v_name text;
    p_customer_id bigint := 999;
BEGIN
    EXECUTE
        'SELECT customer_name FROM pl_diag_lab.customers
         WHERE customer_id=$1'
    INTO STRICT v_name
    USING p_customer_id;

    RAISE NOTICE 'name=%',v_name;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE NOTICE 'Customer % not found',p_customer_id;
END $$;
~~~

For ID 999, the dynamic SELECT returns no rows and `INTO STRICT` raises `NO_DATA_FOUND`.

### Exercise 29 — Safe Dynamic SQL

~~~sql
DO $$
DECLARE
    v_schema text := 'pl_diag_lab';
    v_table text := 'customers';
    p_customer_id bigint := 101;
    v_count bigint;
BEGIN
    IF v_schema <> 'pl_diag_lab'
       OR v_table <> 'customers' THEN
        RAISE EXCEPTION 'Table not allowed';
    END IF;

    EXECUTE format(
        'SELECT COUNT(*) FROM %I.%I WHERE customer_id=$1',
        v_schema,v_table
    )
    INTO v_count
    USING p_customer_id;

    RAISE NOTICE 'count=%',v_count;
END $$;
~~~

`%I` safely quotes **identifiers**, and `USING` binds **data values**, preventing SQL injection and escaping bugs. In functions accepting table names from callers, always whitelist permitted schemas/tables—quoting alone does not enforce authorization.

### Exercise 30 — PG_CONTEXT

~~~sql
DO $$
DECLARE
    v_current_context text;
BEGIN
    GET DIAGNOSTICS v_current_context=PG_CONTEXT;
    RAISE NOTICE 'Current context: %',v_current_context;
END $$;
~~~

`PG_CONTEXT` is the **current** call stack at the `GET DIAGNOSTICS` call, not the origin stack trace of an earlier exception. Inside handlers, use `GET STACKED DIAGNOSTICS ... PG_EXCEPTION_CONTEXT` to get the error origin.

### Exercise 31 — Catching unique_violation

~~~sql
DO $$
DECLARE
    v_state text;
    v_constraint text;
    v_message text;
BEGIN
    INSERT INTO pl_diag_lab.customers
        (customer_id,customer_code,customer_name,customer_status)
    VALUES
        (101,'C101X','Duplicate','active');
EXCEPTION
    WHEN unique_violation THEN
        GET STACKED DIAGNOSTICS
            v_state=RETURNED_SQLSTATE,
            v_constraint=CONSTRAINT_NAME,
            v_message=MESSAGE_TEXT;

        RAISE NOTICE 'state=%, constraint=%, message=%',
            v_state,v_constraint,v_message;
END $$;
~~~

Expected SQLSTATE `23505`. The constraint name depends on the schema, typically `customers_pkey` if created without an explicit PK name.

### Exercise 32 — SQLSTATE Mapping Table

| SQLSTATE | Exception Name |
|---|---|
| `23505` | `unique_violation` |
| `23503` | `foreign_key_violation` |
| `P0002` | `no_data_found` |
| `P0003` | `too_many_rows` |
| `40001` | `serialization_failure` |

Never classify errors by searching substrings in `MESSAGE_TEXT` when stable SQLSTATE codes are available.

### Exercise 33 — Two Types of Context

Inside a handler:

~~~sql
GET STACKED DIAGNOSTICS
    v_error_context=PG_EXCEPTION_CONTEXT;

GET DIAGNOSTICS
    v_current_context=PG_CONTEXT;
~~~

`v_error_context` gives the stack at **the point where the error occurred**; `v_current_context` gives the stack **where the handler is currently running**. The two strings can differ; never treat one as proving both.

### Exercise 34 — Exception Subtransaction

Customer 900 **is gone** after the inner `EXCEPTION` block catches the second error, because DB changes in the block body roll back. Meanwhile `v_step` still holds `'after insert'` upon entering the handler, because local PL/pgSQL variables do not roll back.

Never use `v_step` as proof that an INSERT committed.

### Exercise 35 — Catching OTHERS and Returning NULL

Three risks:

1. `permission denied` or schema errors get disguised as "data not found."
2. Deadlocks and serialization failures fail to trigger retries.
3. Constraint violations and data corruption are hidden, complicating debugging and returning wrong API results.

Rethrow pattern:

~~~sql
DO $$
DECLARE
    v_state text;
BEGIN
    PERFORM 1/0;
EXCEPTION
    WHEN OTHERS THEN
        GET STACKED DIAGNOSTICS v_state=RETURNED_SQLSTATE;
        RAISE NOTICE 'SQLSTATE=%',v_state;
        RAISE;
END $$;
~~~

This snippet **intentionally fails** at the end when executed. In production, log only permitted fields and do not catch/rethrow indiscriminately just to add overhead.

### Exercise 36 — COUNT-Then-INSERT Race

Two concurrent transactions can both observe `COUNT(*)=0` before either inserts. Without a constraint, both insert duplicate business keys; with `UNIQUE`, one fails with `23505`.

Required:

~~~sql
ALTER TABLE pl_diag_lab.customers
ADD CONSTRAINT uq_customers_code
UNIQUE (customer_code);
~~~

**The lab already defines `UNIQUE(customer_code)`**, so do not re-run adding a duplicate constraint. With uniqueness enforced, use `INSERT ... ON CONFLICT (customer_code) DO NOTHING` or `DO UPDATE` per contract. Never rely on `COUNT` before `INSERT` to enforce uniqueness.

### Exercise 37 — SELECT FOR UPDATE

`SELECT ... FOR UPDATE` acquires row-level locks on selected rows within the transaction (per PostgreSQL lock modes), coordinating concurrent transactions trying to lock or update the same rows. `FOUND=true` only says a row was read—it **does not acquire a row lock**; plain SELECT and `SELECT FOR UPDATE` behave differently.

Still, if a single set-based UPDATE with a predicate enforces the invariant directly, a separate `SELECT FOR UPDATE` may not be necessary.

### Exercise 38 — ROW_COUNT=0 Has Multiple Meanings

After:

~~~sql
UPDATE pl_diag_lab.orders
SET order_status='paid'
WHERE order_id=p_id AND order_status='new';
~~~

`ROW_COUNT=0` can mean:

- The ID does not exist.
- The ID exists, but its status is already `paid` or `canceled`.

When required to distinguish them, query afterward:

~~~sql
SELECT order_status INTO v_current_status
FROM pl_diag_lab.orders
WHERE order_id=p_id;
v_exists := FOUND;
~~~

Under concurrent updates, both steps must run within an appropriate transaction/locking model. Never assume the follow-up SELECT always reflects the exact state at the instant the UPDATE matched 0 rows across all isolation levels.

### Exercise 39 — Batch UPDATE Function

~~~sql
CREATE OR REPLACE FUNCTION pl_diag_lab.cancel_old_new_orders_count(
    p_before timestamptz
)
RETURNS bigint
LANGUAGE plpgsql
AS $$
DECLARE
    v_rows bigint;
BEGIN
    UPDATE pl_diag_lab.orders
       SET order_status='canceled'
     WHERE order_status='new'
       AND created_at < p_before;

    GET DIAGNOSTICS v_rows = ROW_COUNT;
    RETURN v_rows;
END;
$$;
~~~

Test:

~~~sql
BEGIN;
SELECT pl_diag_lab.cancel_old_new_orders_count(
    '2026-11-05 00:00:00+00'
);
ROLLBACK;
~~~

Clean seed data yields 2 rows (1001 and 1003). If the lab data was modified, the count varies accordingly. `RETURN v_rows` does not commit; persistence depends on the caller's transaction.

### Exercise 40 — Set-Based UPDATE Instead of a Loop

Typically use one statement:

~~~sql
DO $$
DECLARE
    v_rows bigint;
BEGIN
    UPDATE pl_diag_lab.orders
       SET amount=round(amount * 1.05,2)
     WHERE order_status='new';

    GET DIAGNOSTICS v_rows=ROW_COUNT;

    RAISE NOTICE 'Updated % rows',v_rows;
END $$;
~~~

Applying the change in one UPDATE instead of 100,000 separate UPDATEs lets PostgreSQL optimize scans/writes and avoids per-command overhead. Evaluate against your workload, since per-row external side effects alter the design.

### Exercise 41 — Aliases to Eliminate Name Ambiguity

Incorrect:

~~~sql
WHERE order_id=order_id
~~~

Correct:

~~~sql
SELECT o.amount
INTO v_amount
FROM pl_diag_lab.orders AS o
WHERE o.order_id=p_order_id;
~~~

Use `p_` for parameters, `v_` for variables, and `o.` for columns; never rely on conflict-resolution settings to guess identifiers.

### Exercise 42 — FOUND Inside Triggers

`FOUND` is a PL/pgSQL variable **local** to statements executed inside the trigger function, not the status of the outer DML statement across the table. In row-level triggers, use `NEW`, `OLD`, and `TG_OP` for row values and operation type; to inspect statement-wide row totals, use statement-level triggers with transition tables or check affected counts on the caller side.

### Exercise 43 — Testing UPDATE with ROLLBACK

~~~sql
BEGIN;

DO $$
DECLARE
    v_count bigint;
BEGIN
    UPDATE pl_diag_lab.orders
       SET order_status='paid'
     WHERE order_status='new';

    GET DIAGNOSTICS v_count=ROW_COUNT;
    RAISE NOTICE 'Transitioned % new orders to paid',v_count;
END $$;

ROLLBACK;
~~~

After `ROLLBACK`, the database returns to its pre-transaction state. Never call `COMMIT` inside an ordinary function. If a query triggers external side effects outside the database, PostgreSQL rollback cannot undo them.

### Exercise 44 — Combining SELECT INTO, FOUND, UPDATE, and Stacked Diagnostics

Sample function returning status and count:

~~~sql
CREATE OR REPLACE FUNCTION pl_diag_lab.pay_new_orders_by_code(
    p_customer_code text
)
RETURNS TABLE (
    result_code text,
    updated_orders bigint
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_customer_id bigint;
    v_rows bigint;
    v_found boolean;
    v_state text;
    v_constraint text;
BEGIN
    SELECT c.customer_id
      INTO v_customer_id
      FROM pl_diag_lab.customers AS c
     WHERE c.customer_code=p_customer_code;

    v_found := FOUND; -- Capture immediately after SELECT.

    IF NOT v_found THEN
        result_code := 'customer_not_found';
        updated_orders := 0;
        RETURN NEXT;
        RETURN;
    END IF;

    UPDATE pl_diag_lab.orders AS o
       SET order_status='paid'
     WHERE o.customer_id=v_customer_id
       AND o.order_status='new';

    GET DIAGNOSTICS v_rows=ROW_COUNT;

    result_code := 'updated';
    updated_orders := v_rows;

    RETURN NEXT;
    RETURN;

EXCEPTION
    WHEN unique_violation OR foreign_key_violation THEN
        GET STACKED DIAGNOSTICS
            v_state=RETURNED_SQLSTATE,
            v_constraint=CONSTRAINT_NAME;

        -- Internal logging may record v_state and v_constraint
        -- per policy, but never turn constraint errors
        -- into customer_not_found or swallow them.
        RAISE NOTICE 'Constraint failure SQLSTATE=%; constraint=%',
            v_state,v_constraint;
        RAISE;
END;
$$;
~~~

Explanation:

1. `SELECT ... INTO` looks up the ID by UNIQUE `customer_code`; if absent, `FOUND=false`.
2. Immediately capture `v_found := FOUND` before running any other SQL.
3. When the customer is absent, return an explicit status and `updated_orders=0`.
4. A set-based UPDATE transitions `new` orders to `paid`, avoiding per-order loops.
5. `GET DIAGNOSTICS ROW_COUNT` sits **immediately after the UPDATE**, before any logging or subsequent SQL.
6. If the UPDATE affects 0 rows, `result_code='updated'` with count `0` in this example simply means the batch ran with no `new` orders; an API might return a distinct code if business logic differentiates that.
7. Inside the handler, only read **GET STACKED DIAGNOSTICS** for the exception; never use `FOUND` or `ROW_COUNT` to classify unique/FK errors.
8. `RAISE;` ensures database errors are never hidden behind a false success status.
9. If the caller prefers a single output row rather than set-returning `RETURNS TABLE`, you can use `OUT` parameters or a composite return type consistently.
10. Calling and committing this function modifies real lab data; test inside a transaction with `ROLLBACK`.

Safe test run:

~~~sql
BEGIN;

SELECT *
FROM pl_diag_lab.pay_new_orders_by_code('C101');

SELECT *
FROM pl_diag_lab.pay_new_orders_by_code('NO_SUCH_CODE');

ROLLBACK;
~~~

With baseline data, `C101` has `new` order 1001 so the expected count is `1`, while the nonexistent code returns `customer_not_found` with count `0`. Data modifications in the transaction are rolled back at the end.

---

## 45. Summary

The four techniques in this lesson are closely related yet answer different questions:

1. **`:=`**: assigns an expression to a PL/pgSQL variable. Uninitialized variables default to NULL. Use `%TYPE` and `%ROWTYPE` to keep variable types aligned with the schema.
2. **`SELECT ... INTO`**: loads SQL output into a target. Without `STRICT`: 0 rows → target NULL, `FOUND=false`; 1 row → assigned, `FOUND=true`; multiple rows → picks an unguaranteed first row unless `ORDER BY` is present. `INTO STRICT` enforces one row, raising `NO_DATA_FOUND` or `TOO_MANY_ROWS` on mismatch.
3. **`FOUND`**: a local boolean flag updated by statements such as `SELECT INTO`, `PERFORM`, DML, `FETCH`, and loops. It **keeps no history**; save it immediately if subsequent statements run. Dynamic `EXECUTE` **does not** update `FOUND`.
4. **`GET DIAGNOSTICS ... ROW_COUNT`**: reads how many rows the most recent SQL command processed; place it right next to the measured command and store into a `bigint` variable. It does not replace `COUNT(*)` or `EXISTS` values.
5. **`GET DIAGNOSTICS ... PG_CONTEXT`**: reads the **current** call stack.
6. **`GET STACKED DIAGNOSTICS`**: inside an `EXCEPTION` handler, reads `RETURNED_SQLSTATE`, `MESSAGE_TEXT`, `CONSTRAINT_NAME`, `PG_EXCEPTION_CONTEXT`, and related error fields. It is not a tool for reading `ROW_COUNT`.
7. **DML `RETURNING INTO`**: works cleanly for single rows, but errors when multiple rows return into a scalar target; do not treat it like non-STRICT multi-row `SELECT INTO`.
8. **Set-based queries and constraints** are generally superior to read-then-update loops or `COUNT`-then-`INSERT` uniqueness checks. `FOUND`/`ROW_COUNT` observe results—they do not replace transaction isolation, locking, PK/FK constraints, or idempotency.
9. **Exceptions** must be classified by `SQLSTATE` and business rules; never swallow all errors and return NULL. When caught, DB changes inside the `EXCEPTION` block roll back via subtransaction while local variables keep their values.
10. **Measure accurately before optimizing:** choose `SELECT INTO` when you need data, `PERFORM`/`EXISTS` for existence, `COUNT(*)` for exact totals, `GET DIAGNOSTICS` for affected row counts, and `STACKED DIAGNOSTICS` when handling exceptions.

Remember the implementation flow: **define the 0/1/many-row contract → choose assignment or `SELECT INTO [STRICT]` → capture `FOUND` immediately → use `ROW_COUNT` for DML row counts, especially after dynamic `EXECUTE` → catch and classify errors via `SQLSTATE`/`STACKED DIAGNOSTICS` → verify transactions, concurrency, and privileges → test 0-row, multi-row, and constraint-error paths before shipping to production**.
