# DECLARE, BEGIN, EXCEPTION, and END Block Structure in PL/pgSQL

In PostgreSQL, **PL/pgSQL** is a procedural language used to write functions (`FUNCTION`), procedures (`PROCEDURE`), trigger functions, and anonymous execution blocks (`DO`). Whereas pure SQL describes **the dataset to read or modify**, PL/pgSQL adds variables, branching, loops, nested blocks, and exception handling.

The foundation of PL/pgSQL is a **block**:

~~~sql
[ <<label>> ]
[ DECLARE
    -- Variable declarations
]
BEGIN
    -- Executable statements
[ EXCEPTION
    -- Error-catching and handling branches
]
END [label];
~~~

The four key keywords in this lesson are:

- **`DECLARE`:** declares variables, constants, data types, and initial values.
- **`BEGIN`:** marks the start of the statement section **of the PL/pgSQL block**.
- **`EXCEPTION`:** an optional section to handle errors raised inside the block.
- **`END`:** marks the end of the block, usually followed by a semicolon `;`.

The easiest thing to confuse: **`BEGIN ... END` in PL/pgSQL is not equivalent to `BEGIN; ... COMMIT;` in an SQL transaction**. And when a block has an `EXCEPTION` section that catches an error, PostgreSQL uses an **internal subtransaction** mechanism to roll back database changes made in the protected section before running the handler.

This lesson belongs to the **PL/pgSQL** chapter of the **Database Engine Relational PostgreSQL** module. The examples use a dedicated lab schema and can be practiced from scratch.

## 1. Learning Objectives

After this lesson, you can:

1. Write valid syntax for `DECLARE–BEGIN–END` blocks and blocks with `EXCEPTION`.
2. Use `DO` to run a PL/pgSQL block without saving a function.
3. Declare variables, constants, and `%TYPE`, `%ROWTYPE`, and `RECORD` types.
4. Distinguish the execution order of the declaration, statement, and exception-handling sections.
5. Use block labels (`label`), nested blocks, and variable scope to avoid naming mistakes.
6. Query data into variables with `SELECT ... INTO` and handle `STRICT`.
7. Use `IF`, loops, `PERFORM`, `FOUND`, and `GET DIAGNOSTICS` inside a block.
8. Catch specific errors such as `unique_violation`, `no_data_found`, and `division_by_zero`.
9. Read `SQLSTATE`, `SQLERRM`, and `GET STACKED DIAGNOSTICS`.
10. Understand **what gets rolled back** and **what is retained** after an exception handler runs.
11. Know when to catch an error and when to `RAISE;` to propagate it to the caller.
12. Avoid confusing block boundaries with transactions, savepoints, and procedures that use `COMMIT`.
13. Write multi-step logic that preserves consistency instead of swallowing errors unconditionally.
14. Recognize the performance and concurrency impact of blocks with `EXCEPTION`.

## 2. A Minimal PL/pgSQL Block

Example of an anonymous block:

~~~sql
DO $do$
BEGIN
    RAISE NOTICE 'Hello from a PL/pgSQL block';
END;
$do$;
~~~

Line breakdown:

- `DO` submits a PL/pgSQL block for **one-time** execution.
- `$do$...$do$` is a **dollar-quoted string** containing the body.
- `BEGIN` starts the PL/pgSQL statements.
- `RAISE NOTICE` emits a NOTICE-level message to the client/log according to configuration.
- `END;` closes the block.
- The `;` after `$do$` terminates **the SQL DO statement**.

This is **one SQL DO statement**, containing **one PL/pgSQL block** inside it.

### Dollar-Quoting vs. Single Quotes

You can use `$$ ... $$` or a tag such as `$do$ ... $do$`. Tags help prevent conflicts with other dollar-quoted strings inside the body.

~~~sql
DO $block$
BEGIN
    RAISE NOTICE 'An apostrophe: it''s valid SQL quoting';
END;
$block$;
~~~

The doubled single quote in `it''s` is escaping inside an SQL string. Dollar-quoting only avoids having to escape **the entire function/block body** as one giant single-quoted SQL string; it does not replace all rules for writing SQL strings inside it.

## 3. Diagram of a Full Block

~~~mermaid
flowchart TD
    A["Enter block"] --> D["DECLARE: create variables, evaluate initializers"]
    D --> B["BEGIN: execute statements in order"]
    B --> C{"Error in protected section?"}
    C -->|"No"| E["Skip EXCEPTION"]
    C -->|"Yes, matches handler"| R["Roll back DB changes in protected block"]
    R --> H["EXCEPTION: run handler"]
    C -->|"Yes, no match"| U["Propagate error to outer block/caller"]
    H --> F["END: exit block"]
    E --> F
~~~

**Both `DECLARE` and `EXCEPTION` are optional.** `BEGIN` and `END` are mandatory in the standard block structure.

### Example with All Sections

~~~sql
DO $do$
DECLARE
    v_numerator numeric := 10;
    v_denominator numeric := 2;
    v_result numeric;
BEGIN
    v_result := v_numerator / v_denominator;

    RAISE NOTICE 'Result = %', v_result;
EXCEPTION
    WHEN division_by_zero THEN
        RAISE NOTICE 'Cannot divide by zero';
END;
$do$;
~~~

With `v_denominator = 2`, no error occurs; the handler is skipped. If changed to `0`, `division_by_zero` is caught and the corresponding message is emitted.

### Order of Branches

A block with multiple `WHEN` clauses evaluates the declared error conditions in order. Once a matching handler is selected, PostgreSQL executes that handler; it does not fall through to run all remaining `WHEN` branches.

## 4. DECLARE Is a Declaration Section, Not an SQL DECLARE Cursor Statement

In PL/pgSQL:

~~~sql
DECLARE
    v_count integer := 0;
    v_name text;
    v_active boolean DEFAULT true;
~~~

is the variable declaration section belonging to the block.

In pure SQL, there is a `DECLARE` statement used to declare a cursor in its own context; **do not confuse the two syntaxes**.

### Do Not Write DECLARE After Entering BEGIN

Incorrect:

~~~sql
DO $do$
BEGIN
    -- INTENTIONALLY INVALID block syntax:
    DECLARE v_total integer := 0;
END;
$do$;
~~~

The correct approach is to place declarations before `BEGIN`, or open **a nested block** with its own `DECLARE`:

~~~sql
DO $do$
BEGIN
    RAISE NOTICE 'Outer block';

    DECLARE
        v_total integer := 0;
    BEGIN
        v_total := v_total + 1;
        RAISE NOTICE 'Inner total = %', v_total;
    END;
END;
$do$;
~~~

A nested block is valid inside the statement section of an outer block.

## 5. Variable Declaration Syntax

Template:

~~~sql
variable_name [CONSTANT] data_type
    [COLLATE collation_name]
    [NOT NULL]
    [{ DEFAULT | := | = } expression];
~~~

Practical example:

~~~sql
DO $do$
DECLARE
    v_id bigint := 1001;
    v_customer_name text DEFAULT 'Lan';
    v_amount numeric(12,2) := 125.50;
    v_active boolean := true;
    v_created_at timestamptz := clock_timestamp();
    v_note text;
BEGIN
    RAISE NOTICE 'id=%, name=%, amount=%, active=%',
        v_id, v_customer_name, v_amount, v_active;
    RAISE NOTICE 'created_at=%, note=%',
        v_created_at, v_note;
END;
$do$;
~~~

`v_note` has no initializer, so it defaults to SQL `NULL` unless constrained or declared otherwise.

### Use Recognizable Variable Names

A helpful convention:

- `p_` for function/procedure parameters.
- `v_` for local variables.
- `r_` for records.
- `c_` for constants.

This is a naming convention used in this lesson, not a PostgreSQL syntax requirement.

## 6. Distinguishing :=, DEFAULT, and = in DECLARE

In PL/pgSQL declarations, the following syntaxes can be used to specify an initial value:

~~~sql
DO $do$
DECLARE
    v_a integer := 10;
    v_b integer DEFAULT 10;
    v_c integer = 10;
BEGIN
    RAISE NOTICE 'a=%, b=%, c=%', v_a, v_b, v_c;
END;
$do$;
~~~

All three variables are initialized to 10.

However, when **assigning variables in the statements section**, use `:=` or `=` according to valid PL/pgSQL syntax:

~~~sql
v_a := v_a + 1;
~~~

Do not confuse PL/pgSQL variable assignment with SQL's `UPDATE ... SET column = expression` or with the equality comparison operator `=` inside a conditional expression.

## 7. Declaring Constants with CONSTANT

~~~sql
DO $do$
DECLARE
    c_tax_rate numeric CONSTANT := 0.10;
    v_price numeric(12,2) := 200.00;
    v_total numeric(12,2);
BEGIN
    v_total := v_price * (1 + c_tax_rate);

    RAISE NOTICE 'Total = %', v_total;
END;
$do$;
~~~

`CONSTANT` marks a variable that cannot be reassigned after initialization in the block.

Intentionally invalid example:

~~~sql
DO $do$
DECLARE
    c_tax_rate numeric CONSTANT := 0.10;
BEGIN
    -- INTENTIONALLY INVALID: cannot reassign a CONSTANT.
    c_tax_rate := 0.12;
END;
$do$;
~~~

Constants help express a fixed value in function logic. For business policies that change frequently, consider a versioned configuration table instead of hard-coding values across many functions.

## 8. NOT NULL and Initial Values

PL/pgSQL allows declaring variables with `NOT NULL`:

~~~sql
DO $do$
DECLARE
    v_attempt integer NOT NULL := 0;
BEGIN
    v_attempt := v_attempt + 1;
    RAISE NOTICE 'Attempt = %', v_attempt;
END;
$do$;
~~~

If a `NOT NULL` variable is declared with a NULL initial value or later assigned NULL, the system raises an error according to PL/pgSQL rules.

### Initialization Does Not Run Only Once Per Connection

When a block is **entered**, variable initialization expressions in `DECLARE` are evaluated according to PL/pgSQL rules. A nested block inside a loop can be entered many times; its local variables are initialized each time the block is entered.

~~~sql
DO $do$
DECLARE
    v_i integer;
BEGIN
    FOR v_i IN 1..3 LOOP
        DECLARE
            v_counter integer := 0;
        BEGIN
            v_counter := v_counter + 1;
            RAISE NOTICE 'Iteration %, inner counter %',
                v_i, v_counter;
        END;
    END LOOP;
END;
$do$;
~~~

`v_counter` is created/re-initialized upon entering the inner block, so it prints 1 on each iteration rather than accumulating up to 3.

## 9. Declaring Variables Based on Column Types with %TYPE

When a table column has type `numeric(12,2)`, a related variable can be declared using the column's type instead of copying it manually.

Assuming a table `plpgsql_lab.accounts` exists:

~~~sql
DECLARE
    v_balance plpgsql_lab.accounts.balance%TYPE;
~~~

`%TYPE` references the data type of a column or variable via PL/pgSQL's type-resolution mechanism. This is useful when the schema evolves and you want logic to track the declared type.

### Notes

- `%TYPE` refers only to the **data type**; it does not automatically carry table constraints or triggers.
- When code depends on precision or casts, you must still test schema migrations.
- Do not reference `%TYPE` from a table that has not been created yet when creating a function: the function may require that relation to exist to resolve the declaration.

The lab section below creates the tables before using `%TYPE`.

## 10. %ROWTYPE and RECORD

Two ways to represent a row:

~~~sql
DECLARE
    v_account plpgsql_lab.accounts%ROWTYPE;
    r_any record;
~~~

**`%ROWTYPE`** is bound to the row structure of a known relation.

**`RECORD`** is flexible; its field structure is determined by the row assigned from a suitable query.

Example after the lab tables have been created:

~~~sql
DO $do$
DECLARE
    v_account plpgsql_lab.accounts%ROWTYPE;
    r_summary record;
BEGIN
    SELECT a.*
    INTO STRICT v_account
    FROM plpgsql_lab.accounts AS a
    WHERE a.account_id = 1;

    SELECT
        COUNT(*) AS account_count,
        SUM(balance) AS total_balance
    INTO r_summary
    FROM plpgsql_lab.accounts;

    RAISE NOTICE 'Owner=%, balance=%',
        v_account.owner_name, v_account.balance;

    RAISE NOTICE 'Accounts=%, total=%',
        r_summary.account_count, r_summary.total_balance;
END;
$do$;
~~~

`%ROWTYPE` provides access to fields known from the schema. `RECORD` is useful when a result contains multiple computed columns, though the risk of runtime field-name/type errors is higher if no structure has been assigned properly.

## 11. BEGIN ... END Is a Block, Not a Transaction

This is the most important distinction in this lesson:

| Syntax | Context | Meaning |
| --- | --- | --- |
| `BEGIN ... END;` | PL/pgSQL | Delimits a **statement block** |
| `BEGIN;` | SQL outside PL/pgSQL | Starts an **SQL transaction** |
| `COMMIT;` | SQL transaction | Commits the transaction |
| `ROLLBACK;` | SQL transaction | Aborts the transaction |
| `EXCEPTION WHEN ...` | PL/pgSQL block | Catches errors in the block, with internal rollback of the protected portion |

Example of running external SQL:

~~~sql
BEGIN; -- SQL transaction, not a PL/pgSQL block.

DO $do$
BEGIN
    RAISE NOTICE 'Inside a PL/pgSQL block';
END;
$do$;

ROLLBACK; -- Ends/aborts the SQL transaction.
~~~

`END;` inside `DO` **does not commit** the transaction. If `DO` modifies data inside an external SQL transaction, those changes still obey that transaction's `COMMIT`/`ROLLBACK`.

### Why Is the Keyword BEGIN Reused?

Two different syntactic contexts share the same keyword. PostgreSQL knows whether it is parsing an SQL statement or a PL/pgSQL body. Do not read code by the rule "seeing `BEGIN` means a new transaction starts."

## 12. A PL/pgSQL Function Is Also a Block

Create a simple function:

~~~sql
CREATE OR REPLACE FUNCTION plpgsql_lab.add_tax(
    p_price numeric,
    p_rate numeric
)
RETURNS numeric
LANGUAGE plpgsql
AS $fn$
DECLARE
    v_total numeric;
BEGIN
    IF p_price IS NULL OR p_rate IS NULL THEN
        RETURN NULL;
    END IF;

    v_total := p_price * (1 + p_rate);

    RETURN v_total;
END;
$fn$;
~~~

Call it:

~~~sql
SELECT plpgsql_lab.add_tax(100.00, 0.10);
~~~

The result is 110 under numeric arithmetic.

### Differences Between DO and a Function

- `DO` executes a block once and does not declare a return type for the caller.
- `FUNCTION` has a signature, name, parameters, and `RETURNS`.
- A function declared `RETURNS numeric` must return an appropriate value via `RETURN` along all required execution paths.
- A function can be called from SQL according to function-category, volatility, and side-effect rules.
- A function must not arbitrarily use SQL `COMMIT`/`ROLLBACK` to control a transaction managed by its caller.

Declarations inside a function's `DECLARE` section are still local variables, not table columns or session variables.

## 13. Lab Setup: Accounts and Event Log

From here on, the examples use concrete data. Run them only in a dedicated lab database.

**Warning:** `DROP SCHEMA IF EXISTS plpgsql_lab CASCADE` deletes all objects in the `plpgsql_lab` schema. Do not run this command in production.

~~~sql
-- RUN ONLY ON A PRACTICE DATABASE.
DROP SCHEMA IF EXISTS plpgsql_lab CASCADE;

CREATE SCHEMA plpgsql_lab;

CREATE TABLE plpgsql_lab.accounts (
    account_id integer PRIMARY KEY,
    owner_name text NOT NULL UNIQUE,
    balance numeric(14,2) NOT NULL
        CHECK (balance >= 0),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE plpgsql_lab.events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_key text NOT NULL UNIQUE,
    detail text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE plpgsql_lab.transfers (
    transfer_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    from_account integer NOT NULL
        REFERENCES plpgsql_lab.accounts(account_id),
    to_account integer NOT NULL
        REFERENCES plpgsql_lab.accounts(account_id),
    amount numeric(14,2) NOT NULL CHECK (amount > 0),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

INSERT INTO plpgsql_lab.accounts (
    account_id, owner_name, balance
)
VALUES
    (1, 'Lan', 1000.00),
    (2, 'Minh',  500.00),
    (3, 'Hoa',  250.00);

INSERT INTO plpgsql_lab.events (
    event_key, detail
)
VALUES ('existing-event', 'Used to test unique violation');
~~~

All subsequent examples that modify balances or events are wrapped in an SQL transaction and `ROLLBACK` when their purpose is only to observe behavior.

### Verify Initial State

~~~sql
SELECT account_id, owner_name, balance
FROM plpgsql_lab.accounts
ORDER BY account_id;

SELECT event_key, detail
FROM plpgsql_lab.events
ORDER BY event_id;
~~~

Lan's account has 1000.00, Minh has 500.00, and Hoa has 250.00. The events table already contains the key `existing-event` to trigger unique violations.

## 14. Reading Columns into Variables with SELECT ... INTO

In PL/pgSQL, `SELECT ... INTO variable` assigns a query result to a variable:

~~~sql
DO $do$
DECLARE
    v_balance numeric(14,2);
BEGIN
    SELECT a.balance
    INTO v_balance
    FROM plpgsql_lab.accounts AS a
    WHERE a.account_id = 1;

    RAISE NOTICE 'Balance = %', v_balance;
END;
$do$;
~~~

**Do not confuse:** `SELECT ... INTO` inside PL/pgSQL assigns to variables; it is not the regular SQL table-creation syntax `SELECT INTO new_table`. To create a table in modern SQL, use `CREATE TABLE ... AS SELECT ...`.

### Query Returns No Rows

Without `STRICT`, a `SELECT ... INTO` returning no rows sets the target to NULL according to the applicable rules, and the `FOUND` variable becomes false.

~~~sql
DO $do$
DECLARE
    v_balance numeric(14,2);
BEGIN
    SELECT a.balance
    INTO v_balance
    FROM plpgsql_lab.accounts AS a
    WHERE a.account_id = -1;

    IF NOT FOUND THEN
        RAISE NOTICE 'No account found';
    END IF;
END;
$do$;
~~~

### Query Returns Multiple Rows

Without `STRICT`, `SELECT ... INTO` typically assigns the first row produced by the plan and discards the rest. You should not rely on a deterministic "first row" without an explicit `ORDER BY`.

## 15. SELECT INTO STRICT: Expecting Exactly One Row

~~~sql
DO $do$
DECLARE
    v_balance numeric(14,2);
BEGIN
    SELECT a.balance
    INTO STRICT v_balance
    FROM plpgsql_lab.accounts AS a
    WHERE a.account_id = 1;

    RAISE NOTICE 'Exact balance = %', v_balance;
END;
$do$;
~~~

When using `STRICT`:

- **No rows** → `NO_DATA_FOUND`.
- **More than one row** → `TOO_MANY_ROWS`.
- **Exactly one row** → assigns the variable.

Example catching a missing row:

~~~sql
DO $do$
DECLARE
    v_balance numeric(14,2);
BEGIN
    BEGIN
        SELECT a.balance
        INTO STRICT v_balance
        FROM plpgsql_lab.accounts AS a
        WHERE a.account_id = -1;
    EXCEPTION
        WHEN no_data_found THEN
            RAISE NOTICE 'Account does not exist';
    END;
END;
$do$;
~~~

### Why Is STRICT Important?

When business logic requires **exactly one record**, silently receiving NULL or picking an arbitrary row can mask anomalous data. Use `STRICT` when policy requires exactly one row and handle missing or duplicate cases explicitly.

## 16. PERFORM and FOUND When Return Values Are Not Needed

In PL/pgSQL, if you want to execute an SQL query while **discarding its result**, use `PERFORM`:

~~~sql
DO $do$
BEGIN
    PERFORM 1
    FROM plpgsql_lab.accounts AS a
    WHERE a.account_id = 2;

    IF FOUND THEN
        RAISE NOTICE 'Account 2 exists';
    ELSE
        RAISE NOTICE 'Account 2 not found';
    END IF;
END;
$do$;
~~~

`FOUND` is a boolean status variable managed by PL/pgSQL for specific statements such as `SELECT INTO`, `PERFORM`, and several DML operations.

### Do Not Use FOUND Long After the Statement

After subsequent statements that may update `FOUND`, its value no longer necessarily describes the original statement you cared about.

Example:

~~~sql
DO $do$
BEGIN
    PERFORM 1
    FROM plpgsql_lab.accounts
    WHERE account_id = 999;

    IF NOT FOUND THEN
        RAISE NOTICE 'Account not found';
    END IF;
END;
$do$;
~~~

Checking `FOUND` immediately after the relevant statement is clearer and less error-prone.

## 17. GET DIAGNOSTICS and ROW_COUNT

Sometimes you need to know how many rows were affected by a statement; use:

~~~sql
GET DIAGNOSTICS variable_name = ROW_COUNT;
~~~

Example:

~~~sql
BEGIN; -- SQL transaction for the lab.

DO $do$
DECLARE
    v_rows bigint;
BEGIN
    UPDATE plpgsql_lab.accounts AS a
    SET updated_at = clock_timestamp()
    WHERE a.account_id IN (1, 2);

    GET DIAGNOSTICS v_rows = ROW_COUNT;

    RAISE NOTICE 'Updated rows = %', v_rows;
END;
$do$;

ROLLBACK;
~~~

The expected result is 2 if the lab data still contains accounts 1 and 2.

### Distinguishing the Two Types of Diagnostics

- `GET DIAGNOSTICS ... ROW_COUNT`: retrieves execution status information for the relevant statement.
- `GET STACKED DIAGNOSTICS`: used inside an **exception handler** to retrieve information about the error currently being handled.

They are not interchangeable statements.

## 18. IF, LOOP, and RETURN Are Statements Inside BEGIN

`BEGIN` contains statements. Branching constructs have their own `END IF;` and loops have their own `END LOOP;`.

~~~sql
DO $do$
DECLARE
    v_i integer;
    v_sum integer := 0;
BEGIN
    FOR v_i IN 1..5 LOOP
        IF v_i % 2 = 0 THEN
            v_sum := v_sum + v_i;
        END IF;
    END LOOP;

    RAISE NOTICE 'Sum of even numbers = %', v_sum;
END;
$do$;
~~~

Here:

- `END IF;` closes the IF statement.
- `END LOOP;` closes the FOR LOOP statement.
- The final `END;` closes the outer PL/pgSQL block.

**Do not use `END;` to close `IF`**, as that breaks the syntactic structure.

## 19. Nested Blocks and Variable Scope

PL/pgSQL allows nesting multiple blocks:

~~~sql
DO $do$
DECLARE
    v_outer integer := 100;
BEGIN
    RAISE NOTICE 'Outer = %', v_outer;

    DECLARE
        v_inner integer := 20;
    BEGIN
        RAISE NOTICE 'Outer + inner = %',
            v_outer + v_inner;
    END;

    RAISE NOTICE 'Outer still = %', v_outer;
END;
$do$;
~~~

The outer block's `v_outer` variable can be accessed from the inner block unless shadowed. The `v_inner` variable is scoped only to the inner block and is no longer valid to access after that block ends.

### Distinguishing Scope from Transactions

Ending an inner block **does not commit a transaction**. It only ends the variable/statement scope of that block; database changes still belong to the active SQL transaction.

## 20. Shadowing: Inner Variables Hide Outer Variables

~~~sql
DO $do$
DECLARE
    v_status text := 'outer';
BEGIN
    DECLARE
        v_status text := 'inner';
    BEGIN
        RAISE NOTICE 'Inner status = %', v_status;
    END;

    RAISE NOTICE 'Outer status = %', v_status;
END;
$do$;
~~~

Inside the inner block, the nearest `v_status` name refers to the inner variable; it **shadows** the outer variable of the same name.

Shadowing can occasionally be useful, but it can make a long function hard to read, especially when variable names match SQL column names.

### Design Rules

- Use descriptive variable names instead of intentionally reusing names.
- Avoid local variables named the same as table columns unless necessary.
- Use table aliases to qualify SQL columns clearly.
- Use block labels if you genuinely need to reference a shadowed outer variable.

## 21. Block Labels with <<label>> ... END label

A block can have a label:

~~~sql
DO $do$
<<outer_block>>
DECLARE
    v_status text := 'outer';
BEGIN
    <<inner_block>>
    DECLARE
        v_status text := 'inner';
    BEGIN
        RAISE NOTICE 'Inside: %', v_status;
        RAISE NOTICE 'Outer qualified: %',
            outer_block.v_status;
    END inner_block;
END outer_block;
$do$;
~~~

Meaning:

- `<<outer_block>>` declares the outer label.
- `<<inner_block>>` declares the inner label.
- `outer_block.v_status` accesses the outer variable even though its name is shadowed.
- `END inner_block;` and `END outer_block;` close the corresponding blocks.

### Labels Are Not Schema Objects

`outer_block.v_status` is PL/pgSQL name-qualification syntax, not a reference to a table named `outer_block`.

Good labels can improve readability in deeply nested blocks, though they are **not required** for every simple block.

## 22. Avoiding Variable Names That Collide with SQL Column Names

Example prone to confusion:

~~~sql
-- Illustrating a naming-design mistake:
DECLARE
    balance numeric;
BEGIN
    SELECT balance INTO balance
    FROM plpgsql_lab.accounts;
END;
~~~

When an identifier could refer to either a PL/pgSQL variable or an SQL column, PostgreSQL follows conflict-resolution rules and may raise an ambiguity error.

A clearer approach:

~~~sql
DO $do$
DECLARE
    v_balance numeric(14,2);
BEGIN
    SELECT a.balance
    INTO v_balance
    FROM plpgsql_lab.accounts AS a
    WHERE a.account_id = 1;

    RAISE NOTICE 'Balance = %', v_balance;
END;
$do$;
~~~

Use the alias `a` to qualify the column and the prefix `v_` for the variable. Do not resolve every conflict by enabling settings that favor variables or columns and accepting that SQL might change meaning when the schema changes.

## 23. EXCEPTION Is an Optional Error-Handling Section

Structure:

~~~sql
BEGIN
    statements;
EXCEPTION
    WHEN condition_a THEN
        handler_statements;
    WHEN condition_b OR condition_c THEN
        handler_statements;
    WHEN OTHERS THEN
        fallback_statements;
END;
~~~

`EXCEPTION` is placed **after the block's main statements** and **before `END`**.

### Catching a Specific Error

~~~sql
DO $do$
BEGIN
    PERFORM 10 / 0;
EXCEPTION
    WHEN division_by_zero THEN
        RAISE NOTICE 'Cannot divide by zero';
END;
$do$;
~~~

The `division_by_zero` error is handled inside the block.

### EXCEPTION Is Not ELSE

Control only enters a handler when an **actual exception is raised**. `IF ... ELSE` handles normal business branching, whereas `EXCEPTION` handles error conditions.

Do not use `EXCEPTION` in place of a clear `IF` condition when "data does not meet the condition" is a routine occurrence.

## 24. Error Condition Names and SQLSTATE

PostgreSQL identifies errors using five-character `SQLSTATE` codes. PL/pgSQL supports condition names such as `unique_violation`.

| Condition Name | SQLSTATE | Meaning |
| --- | --- | --- |
| `unique_violation` | 23505 | UNIQUE/PRIMARY KEY violation |
| `foreign_key_violation` | 23503 | FOREIGN KEY violation |
| `check_violation` | 23514 | CHECK constraint violation |
| `not_null_violation` | 23502 | NOT NULL violation |
| `division_by_zero` | 22012 | Division by zero |
| `invalid_parameter_value` | 22023 | Invalid parameter value |
| `no_data_found` | P0002 | `INTO STRICT` found no rows |
| `too_many_rows` | P0003 | `INTO STRICT` received multiple rows |
| `raise_exception` | P0001 | Default RAISE EXCEPTION |
| `serialization_failure` | 40001 | Transaction needs retry according to policy |
| `deadlock_detected` | 40P01 | Deadlock detected |
| `lock_not_available` | 55P03 | Could not acquire requested lock |

Example using SQLSTATE directly:

~~~sql
DO $do$
BEGIN
    RAISE EXCEPTION 'Intentional error'
        USING ERRCODE = 'P0001';
EXCEPTION
    WHEN SQLSTATE 'P0001' THEN
        RAISE NOTICE 'Caught custom exception';
END;
$do$;
~~~

### When to Use Condition Names?

Names like `unique_violation` are easier to read than `SQLSTATE '23505'`. For application-defined codes such as `P1001`, you can use `WHEN SQLSTATE 'P1001'`.

Do not invent arbitrary codes and assume every client or framework already understands their semantics; establish a clear error contract in the application.

## 25. A Block Can Have Multiple WHEN Clauses

~~~sql
DO $do$
DECLARE
    v_input integer := 0;
BEGIN
    PERFORM 100 / v_input;
EXCEPTION
    WHEN division_by_zero THEN
        RAISE NOTICE 'Specific: cannot divide by zero';
    WHEN invalid_parameter_value THEN
        RAISE NOTICE 'Input parameter is invalid';
    WHEN OTHERS THEN
        RAISE NOTICE 'Unexpected error';
END;
$do$;
~~~

PostgreSQL chooses the matching handler.

**Handler order and scope must be intentional.** Placing a broad `WHEN OTHERS` fallback can hide bugs if it merely logs and silently continues.

### OTHERS Does Not Catch Absolutely Every Exception

In PL/pgSQL, `OTHERS` does not catch special errors such as `QUERY_CANCELED` and `ASSERT_FAILURE` in the normal way, although you can specify their condition names explicitly when appropriate.

Do not document `WHEN OTHERS` as guaranteeing it catches 100% of all system conditions.

## 26. When No Handler Matches

If an error occurs and the block has no matching `WHEN` branch, the error propagates to **the outer block or caller**.

~~~sql
DO $do$
BEGIN
    BEGIN
        RAISE EXCEPTION 'Failure'
            USING ERRCODE = 'P1001';
    EXCEPTION
        WHEN division_by_zero THEN
            RAISE NOTICE 'This handler does not match';
    END;
EXCEPTION
    WHEN SQLSTATE 'P1001' THEN
        RAISE NOTICE 'Outer block caught P1001';
END;
$do$;
~~~

Error `P1001` is not caught by the `division_by_zero` handler, so it propagates up to the outer block, where a matching handler exists.

### Why Is This Structure Useful?

Many applications want:

- Inner blocks responsible for specific business logic.
- Outer blocks responsible for logging, error translation, or cleanup.
- The final caller deciding on rollback, retry, or response.

Not every block needs `WHEN OTHERS`; **letting errors propagate** is usually the right behavior when the current block does not know how to handle them safely.

## 27. EXCEPTION Creates an Internal Subtransaction

This is the most important part of learning blocks.

When a block has `EXCEPTION` and an error is caught, PostgreSQL uses an **internal subtransaction** for the protected statement section:

1. Statements in the block begin executing.
2. A statement raises an error.
3. Database changes made by the protected portion of the block are rolled back to the state at the start of that portion.
4. The matching handler runs.
5. If the handler completes normally, execution continues after the block.
6. Changes made before the block in an outer scope are not automatically rolled back just because an inner exception was caught.

~~~mermaid
flowchart TD
    O["Outer block: UPDATE A"] --> N["Inner block with EXCEPTION"]
    N --> I["INSERT temp event"]
    I --> X["INSERT duplicate UNIQUE event -> error"]
    X --> RB["Roll back DB changes in inner protected block"]
    RB --> H["Handler unique_violation"]
    H --> C["Continue outer block"]
    C --> T["SQL transaction decides COMMIT/ROLLBACK"]
~~~

**Do not think of this as an application-issued `SAVEPOINT` command.** It is a PL/pgSQL-managed mechanism for executing exception blocks. It is conceptually similar to a local rollback, but it does not turn `BEGIN ... EXCEPTION ... END` into an independently committed transaction.

## 28. Experimenting with Rollback in an Inner Block

The lab already has event key `existing-event`. We intentionally try to insert this key again.

~~~sql
BEGIN; -- Outer SQL transaction, for lab testing only.

DO $do$
DECLARE
    v_attempts integer := 0;
BEGIN
    -- Modification in the outer block, before the inner exception block.
    UPDATE plpgsql_lab.accounts
    SET balance = balance + 1
    WHERE account_id = 1;

    BEGIN
        v_attempts := v_attempts + 1;

        -- First INSERT succeeds temporarily.
        INSERT INTO plpgsql_lab.events (
            event_key, detail
        )
        VALUES (
            'temporary-inside',
            'Should disappear after inner rollback'
        );

        -- Second INSERT causes unique_violation.
        INSERT INTO plpgsql_lab.events (
            event_key, detail
        )
        VALUES (
            'existing-event',
            'Intentional duplicate'
        );

    EXCEPTION
        WHEN unique_violation THEN
            RAISE NOTICE
                'Inner duplicate caught; attempts = %',
                v_attempts;
    END;

    RAISE NOTICE 'Outer block continues normally';
END;
$do$;

SELECT account_id, balance
FROM plpgsql_lab.accounts
WHERE account_id = 1;

SELECT event_key, detail
FROM plpgsql_lab.events
ORDER BY event_id;

ROLLBACK; -- Restore lab seed.
~~~

Expected state **before the outer SQL transaction's `ROLLBACK`**:

- Account 1 increases from 1000.00 to 1001.00 because its UPDATE occurred **before the inner block**.
- Event `temporary-inside` **does not exist**, because the first INSERT inside the inner protected block was also rolled back when the second INSERT failed.
- Event `existing-event` remains the only seeded row.
- The PL/pgSQL variable `v_attempts` still holds **1** inside the handler.

After the final SQL `ROLLBACK`, the outer account change is also undone.

### What Is Not Guaranteed to Roll Back?

Effects **outside transactional database state**—such as already-emitted NOTICE messages or side effects external to PostgreSQL—are not automatically "recalled." Sequences/identity generators may have advanced and will not rewind generated numbers even when an INSERT is rolled back.

Therefore, **do not treat sequence gaps as evidence that a transaction lost data**.

## 29. Local Variables Do Not Automatically Revert After an Exception

In the previous example, the statement:

~~~sql
v_attempts := v_attempts + 1;
~~~

assigned the local variable to 1 before the error occurred.

After database changes in the inner block are rolled back, **PL/pgSQL variables** retain the values they had at the time of the error. Local variables are not MVCC rows that automatically roll back like table data.

Short example:

~~~sql
DO $do$
DECLARE
    v_message text := 'before';
BEGIN
    BEGIN
        v_message := 'changed';

        RAISE EXCEPTION 'Intentional';
    EXCEPTION
        WHEN raise_exception THEN
            RAISE NOTICE 'Value after catch: %',
                v_message;
    END;
END;
$do$;
~~~

Expected output: `changed`.

### Design Consequence

If a variable `v_total` is incremented before an INSERT fails, the handler should not assume `v_total` automatically reverts to its old value. If business logic requires variables to match database state after a rollback, recompute them or design the control flow explicitly.

## 30. The Handler Runs After the Protected Section Rolls Back

Upon entering `EXCEPTION`, database changes **made in the protected block before the error** have already been rolled back by the internal mechanism.

The handler can then execute new statements, such as recording an audit row noting that the operation failed:

~~~sql
BEGIN;

DO $do$
BEGIN
    BEGIN
        INSERT INTO plpgsql_lab.events (event_key, detail)
        VALUES ('temporary', 'Will be rolled back');

        RAISE EXCEPTION 'Simulated failure';

    EXCEPTION
        WHEN raise_exception THEN
            INSERT INTO plpgsql_lab.events (
                event_key, detail
            )
            VALUES (
                'handler-audit',
                'Recorded after protected statements rolled back'
            );
    END;
END;
$do$;

SELECT event_key
FROM plpgsql_lab.events
WHERE event_key IN ('temporary', 'handler-audit')
ORDER BY event_key;

ROLLBACK;
~~~

Inside the SQL transaction before rollback, `handler-audit` can exist while `temporary` does not.

**However, `handler-audit` does not commit on its own!** If the outer transaction rolls back or the handler raises an uncaught error, the audit row will also be rolled back.

### Why Not Rely on an Audit Table to Guarantee Logs Despite Rollback?

A normal INSERT into an audit table within the same transaction does not guarantee durable audit logging if the caller rolls back. If failures must be recorded even when the transaction fails, design logging/outbox/monitoring with appropriate semantics rather than treating `EXCEPTION` as a default "autonomous transaction."

## 31. An EXCEPTION Handler Does Not Re-Run the BEGIN Section

When a handler catches an error, PostgreSQL **does not jump back to the start of the block** to run remaining statements.

~~~sql
DO $do$
BEGIN
    RAISE NOTICE 'Before error';

    RAISE EXCEPTION 'Stop here';

    RAISE NOTICE 'This will not be executed';

EXCEPTION
    WHEN raise_exception THEN
        RAISE NOTICE 'Caught at handler';
END;
$do$;
~~~

The NOTICE statement after `RAISE EXCEPTION` in the protected statements is not executed.

To retry, write an explicit bounded loop/retry policy, typically at the **whole-transaction** level for concurrency errors. There is no built-in "auto retry" from `WHEN`.

## 32. SQLSTATE and SQLERRM Inside a Handler

Inside a handler, two special variables are available:

- `SQLSTATE`: the 5-character error code.
- `SQLERRM`: the error message.

~~~sql
DO $do$
BEGIN
    RAISE EXCEPTION 'Demonstration failure'
        USING ERRCODE = 'P0001';

EXCEPTION
    WHEN SQLSTATE 'P0001' THEN
        RAISE NOTICE 'SQLSTATE = %', SQLSTATE;
        RAISE NOTICE 'SQLERRM = %', SQLERRM;
END;
$do$;
~~~

### Scope of Use

In PL/pgSQL, `SQLSTATE` and `SQLERRM` are used inside an exception handler to inspect the error being handled. Do not expect these values to remain meaningful in ordinary code outside a handler.

If you need to pass error details out of a function or store them in a table, capture them inside the handler and save them into variables or structured logs as appropriate.

## 33. GET STACKED DIAGNOSTICS: Reading Detailed Error Information

`GET STACKED DIAGNOSTICS` retrieves properties of the error currently being handled:

~~~sql
DO $do$
DECLARE
    v_state text;
    v_message text;
    v_detail text;
    v_hint text;
    v_context text;
BEGIN
    RAISE EXCEPTION 'Example validation error'
        USING
            ERRCODE = '22023',
            DETAIL = 'The input did not satisfy the contract',
            HINT = 'Pass a positive amount';

EXCEPTION
    WHEN invalid_parameter_value THEN
        GET STACKED DIAGNOSTICS
            v_state = RETURNED_SQLSTATE,
            v_message = MESSAGE_TEXT,
            v_detail = PG_EXCEPTION_DETAIL,
            v_hint = PG_EXCEPTION_HINT,
            v_context = PG_EXCEPTION_CONTEXT;

        RAISE NOTICE 'State: %, Message: %',
            v_state, v_message;
        RAISE NOTICE 'Detail: %, Hint: %',
            v_detail, v_hint;
        RAISE NOTICE 'Context: %', v_context;
END;
$do$;
~~~

Useful items:

| Diagnostics Field | Meaning |
| --- | --- |
| `RETURNED_SQLSTATE` | SQLSTATE code |
| `MESSAGE_TEXT` | Primary error message |
| `PG_EXCEPTION_DETAIL` | DETAIL text, if present |
| `PG_EXCEPTION_HINT` | HINT text, if present |
| `PG_EXCEPTION_CONTEXT` | Error context / call stack |
| `CONSTRAINT_NAME` | Constraint name when supplied by the error |
| `TABLE_NAME` | Related table name, if any |
| `SCHEMA_NAME` | Related schema name, if any |
| `COLUMN_NAME` | Related column name, if any |

Not every error populates all fields. For errors without detail or constraint metadata, the corresponding fields may be empty as returned by PostgreSQL.

**Do not send raw exception diagnostics containing sensitive data to end users.** Messages, query context, or object names can expose database structure. Log internally per policy and return a safe error contract.

## 34. Catching a UNIQUE Violation in the Lab

The events table has a UNIQUE constraint on `event_key`.

~~~sql
DO $do$
DECLARE
    v_constraint text;
    v_state text;
    v_message text;
BEGIN
    INSERT INTO plpgsql_lab.events (
        event_key, detail
    )
    VALUES (
        'existing-event',
        'Intentional duplicate'
    );

EXCEPTION
    WHEN unique_violation THEN
        GET STACKED DIAGNOSTICS
            v_constraint = CONSTRAINT_NAME,
            v_state = RETURNED_SQLSTATE,
            v_message = MESSAGE_TEXT;

        RAISE NOTICE 'State %, constraint %, message %',
            v_state, v_constraint, v_message;
END;
$do$;
~~~

With the seed data, the INSERT hits SQLSTATE `23505` and the handler runs.

### Should You Catch Every unique_violation?

Not always. If a function performs multi-table business logic, a UNIQUE error might come from a **different constraint** than the one you expect. Catching `unique_violation` and always treating it as a "normal duplicate event" can hide bugs.

When handling a very specific case, you should:

- Inspect `CONSTRAINT_NAME` when reliable and appropriate.
- Catch only around the specific statement inside a narrow inner block.
- Rethrow if the constraint or error is not in the expected set.
- Use `INSERT ... ON CONFLICT` when duplicates are a common business branch and match the semantics.

## 35. RAISE: NOTICE, WARNING, and EXCEPTION

`RAISE` supports multiple levels:

~~~sql
DO $do$
BEGIN
    RAISE DEBUG 'Debug detail';
    RAISE LOG 'Log message';
    RAISE INFO 'Information';
    RAISE NOTICE 'Notice';
    RAISE WARNING 'Warning';
END;
$do$;
~~~

Which levels are displayed or logged depends on client and server settings.

### RAISE EXCEPTION

~~~sql
DO $do$
DECLARE
    v_amount numeric := -10;
BEGIN
    IF v_amount <= 0 THEN
        RAISE EXCEPTION 'Amount must be positive: %',
            v_amount
            USING ERRCODE = '22023';
    END IF;
END;
$do$;
~~~

This statement **intentionally raises an error** when executed outside a handler and puts any open SQL transaction into an aborted state until an appropriate rollback occurs.

### Choosing Structured Messages

Prefer:

- An appropriate SQLSTATE.
- A clear message without exposing sensitive data.
- DETAIL/HINT when helpful for operations.
- Database-generated context logged in an appropriate place.

Do not overuse `RAISE NOTICE` as a replacement for an observability system. It is primarily useful for debugging, labs, or intentionally designed messaging.

## 36. RAISE; to Re-Throw the Current Error

If a handler only needs to log and pass the error up to the caller, use `RAISE;` **with no arguments** inside the handler:

~~~sql
DO $do$
BEGIN
    BEGIN
        RAISE EXCEPTION 'Original failure'
            USING ERRCODE = 'P1001';

    EXCEPTION
        WHEN SQLSTATE 'P1001' THEN
            RAISE NOTICE 'Inner handler observed P1001';
            RAISE; -- Rethrow original exception.
    END;

EXCEPTION
    WHEN SQLSTATE 'P1001' THEN
        RAISE NOTICE 'Outer handler caught rethrown P1001';
END;
$do$;
~~~

`RAISE;` preserves the original error being handled according to PL/pgSQL semantics. It is better than constructing a new message if you want the caller to receive the original SQLSTATE and context.

### When Should You Rethrow?

- You are not sure the error was handled safely.
- You only want to record it and let the transaction roll back.
- The handler sees a constraint name or SQLSTATE outside the expected cases.
- The caller needs to decide whether to retry or return an appropriate response.

**Swallowing an error does not mean the business operation succeeded.**

## 37. Errors Occurring Inside the Handler Itself

An important structural rule:

> A block's handler does not catch exceptions raised inside the statements of **that same handler**.

Example:

~~~sql
DO $do$
BEGIN
    BEGIN
        RAISE EXCEPTION 'First error'
            USING ERRCODE = 'P1001';

    EXCEPTION
        WHEN SQLSTATE 'P1001' THEN
            RAISE EXCEPTION 'Second error inside handler'
                USING ERRCODE = 'P1002';
    END;

EXCEPTION
    WHEN SQLSTATE 'P1002' THEN
        RAISE NOTICE 'Outer block caught handler failure';
END;
$do$;
~~~

To catch an error raised inside a handler, you need an enclosing outer block or an appropriate inner block. Do not assume that `WHEN OTHERS` in the same handler list will "catch a second time" any error thrown by an earlier handler.

## 38. Narrow vs. Broad Handlers

Compare two designs.

**Broad, prone to masking bugs:**

~~~sql
BEGIN
    -- Many operations across different tables.
    ...
EXCEPTION
    WHEN unique_violation THEN
        RAISE NOTICE 'Duplicate, ignore';
END;
~~~

If a UNIQUE constraint is violated on an unexpected table, this handler will still swallow the error.

**Narrow, easier to control:**

~~~sql
BEGIN
    -- Only the insert operation where duplicate is an expected case.
    INSERT INTO plpgsql_lab.events (
        event_key, detail
    )
    VALUES ('existing-event', 'demo');

EXCEPTION
    WHEN unique_violation THEN
        RAISE NOTICE 'Duplicate event key';
END;
~~~

You should still verify the error belongs to the expected constraint. For routine duplicates, `ON CONFLICT` can be clearer and cheaper:

~~~sql
INSERT INTO plpgsql_lab.events (
    event_key, detail
)
VALUES (
    'existing-event',
    'idempotent attempt'
)
ON CONFLICT (event_key)
DO NOTHING;
~~~

**Do not use exceptions for normal control flow when a better SQL statement exists.**

## 39. Overhead of Blocks with EXCEPTION

PL/pgSQL must set up error-handling/subtransaction machinery for any block containing `EXCEPTION`. Therefore, entering and exiting a block with a handler can be more expensive than a plain block.

That does not mean every single execution is dramatically slower, but inside a loop over millions of rows, the cost can become significant.

### Anti-Pattern

~~~sql
DO $do$
DECLARE
    v_i integer;
BEGIN
    FOR v_i IN 1..1000 LOOP
        BEGIN
            INSERT INTO plpgsql_lab.events (
                event_key, detail
            )
            VALUES ('existing-event', 'duplicate');

        EXCEPTION
            WHEN unique_violation THEN
                NULL; -- Anti-pattern demonstration only.
        END;
    END LOOP;
END;
$do$;
~~~

This example **intentionally generates 1,000 duplicate errors** and swallows them; do not run it for performance testing in production.

For idempotent inserts expected to hit many duplicate keys, consider `ON CONFLICT DO NOTHING`, batch inserts, and appropriate logging. Exception handlers are suited for **uncommon error cases** that logic can handle cleanly.

## 40. The Outer SQL Transaction Still Controls COMMIT/ROLLBACK

Example:

~~~sql
BEGIN; -- SQL transaction.

DO $do$
BEGIN
    UPDATE plpgsql_lab.accounts
    SET balance = balance + 5
    WHERE account_id = 3;

    RAISE NOTICE 'Updated Hoa balance';
END;
$do$;

SELECT balance
FROM plpgsql_lab.accounts
WHERE account_id = 3;

ROLLBACK; -- Undoes the UPDATE.
~~~

Even though `DO`'s `END;` has finished executing, the UPDATE is not durable until the SQL transaction commits. `ROLLBACK` undoes the change.

### What If DO Is Not Inside an Explicit SQL BEGIN?

In a client's standard autocommit mode, a `DO` statement runs in its own statement-level transaction. Even then, **that still does not mean every PL/pgSQL `BEGIN` starts a separate transaction**.

## 41. Functions, Procedures, and Transaction Control Authority

### FUNCTION

A PL/pgSQL function is invoked inside an SQL statement/transaction managed by the caller. Do not use `COMMIT`/`ROLLBACK` inside a function to end the caller's transaction.

~~~sql
CREATE OR REPLACE FUNCTION plpgsql_lab.touch_account(
    p_account_id integer
)
RETURNS boolean
LANGUAGE plpgsql
AS $fn$
BEGIN
    UPDATE plpgsql_lab.accounts
    SET updated_at = clock_timestamp()
    WHERE account_id = p_account_id;

    RETURN FOUND;
END;
$fn$;
~~~

### PROCEDURE

PostgreSQL provides `CREATE PROCEDURE` and `CALL` (since PostgreSQL 11). Certain `CALL`/`DO` contexts allow transaction control, subject to strict rules on call stack, transaction boundaries, and procedure structure.

**Do not conclude: "Because procedures exist, I can put COMMIT inside any BEGIN."**

Example of a procedure that does *not* manage transactions itself:

~~~sql
CREATE OR REPLACE PROCEDURE plpgsql_lab.mark_account(
    p_account_id integer
)
LANGUAGE plpgsql
AS $proc$
BEGIN
    UPDATE plpgsql_lab.accounts
    SET updated_at = clock_timestamp()
    WHERE account_id = p_account_id;
END;
$proc$;
~~~

Call it in the lab:

~~~sql
BEGIN;

CALL plpgsql_lab.mark_account(1);

ROLLBACK;
~~~

This `CALL` obeys the outer transaction.

### Important Restriction with EXCEPTION

Do not end a transaction with `COMMIT` or `ROLLBACK` inside a block surrounded by exception handlers, because blocks with `EXCEPTION` use internal subtransactions and transaction control has strict restrictions.

When designing a procedure that needs to commit multiple times, read the transaction management documentation for your exact PostgreSQL major version and structure it appropriately. Inside functions and triggers, never put transaction control in the body.

## 42. Multi-Step Application: Safe Funds Transfer Inside a Transaction

A transfer function includes:

1. Validate inputs.
2. Lock both accounts in a consistent order.
3. Verify both accounts exist.
4. Check sufficient balance.
5. Debit the source account.
6. Credit the destination account.
7. Record the transfer log.
8. Let the caller decide `COMMIT`/`ROLLBACK`.

Lab example:

~~~sql
CREATE OR REPLACE FUNCTION plpgsql_lab.transfer_funds(
    p_from integer,
    p_to integer,
    p_amount numeric
)
RETURNS void
LANGUAGE plpgsql
AS $fn$
DECLARE
    v_count integer;
    v_source_balance plpgsql_lab.accounts.balance%TYPE;
BEGIN
    IF p_from IS NULL
       OR p_to IS NULL
       OR p_amount IS NULL
       OR p_amount <= 0
       OR p_from = p_to
    THEN
        RAISE EXCEPTION 'Invalid transfer arguments'
            USING ERRCODE = '22023';
    END IF;

    -- Lock rows in ID order to reduce deadlock risk.
    PERFORM a.account_id
    FROM plpgsql_lab.accounts AS a
    WHERE a.account_id IN (p_from, p_to)
    ORDER BY a.account_id
    FOR UPDATE;

    SELECT COUNT(*)
    INTO v_count
    FROM plpgsql_lab.accounts AS a
    WHERE a.account_id IN (p_from, p_to);

    IF v_count <> 2 THEN
        RAISE EXCEPTION 'Account not found'
            USING ERRCODE = 'P1002';
    END IF;

    SELECT a.balance
    INTO STRICT v_source_balance
    FROM plpgsql_lab.accounts AS a
    WHERE a.account_id = p_from;

    IF v_source_balance < p_amount THEN
        RAISE EXCEPTION
            'Insufficient balance in account %',
            p_from
            USING ERRCODE = 'P1001';
    END IF;

    UPDATE plpgsql_lab.accounts
    SET balance = balance - p_amount,
        updated_at = clock_timestamp()
    WHERE account_id = p_from;

    UPDATE plpgsql_lab.accounts
    SET balance = balance + p_amount,
        updated_at = clock_timestamp()
    WHERE account_id = p_to;

    INSERT INTO plpgsql_lab.transfers (
        from_account, to_account, amount
    )
    VALUES (p_from, p_to, p_amount);
END;
$fn$;
~~~

### Understand the Demo's Limitations

This is a lab example for learning PL/pgSQL and atomicity, **not a complete production payment system**. Real systems also require business IDs, idempotency keys, authorization, currency precision rules, immutable ledgers, reconciliation, auditing, retry controls, and concurrency management.

`PERFORM ... ORDER BY account_id FOR UPDATE` attempts to lock accounts in a consistent order; this is a deadlock-reduction technique, not a guarantee that any workload is deadlock-free when other tables or locks are involved.

### Do Not Catch Errors to Silently Keep Half an Operation

The function above **has no `EXCEPTION` swallowing errors**. If an UPDATE or INSERT fails, the exception propagates to the caller and the transaction changes roll back according to transaction rules. That is far safer than a `WHEN OTHERS THEN RETURN;` handler that leads the client to think the transfer succeeded.

## 43. Testing a Transfer and Rolling Back

~~~sql
BEGIN;

SELECT plpgsql_lab.transfer_funds(
    1,
    2,
    100.00
);

SELECT account_id, owner_name, balance
FROM plpgsql_lab.accounts
ORDER BY account_id;

SELECT from_account, to_account, amount
FROM plpgsql_lab.transfers
ORDER BY transfer_id;

ROLLBACK;
~~~

Within the transaction:

- Lan: 1000.00 → 900.00.
- Minh: 500.00 → 600.00.
- Hoa: stays 250.00.
- One transfer log row is created.

After `ROLLBACK`, balances and the transfer log return to their pre-test state. **The identity sequence may still increment despite transaction rollback**, which is normal behavior.

### Why Does the Function Not Contain COMMIT?

The caller may need to execute additional steps for the same business operation within a single transaction. A function must not commit partway through and strip the caller of the ability to roll back the entire transaction.

## 44. Testing Insufficient-Balance Catching in an Outer Block

We can intentionally invoke a transfer exceeding the balance and catch business error code `P1001`:

~~~sql
DO $do$
BEGIN
    BEGIN
        PERFORM plpgsql_lab.transfer_funds(
            1,
            2,
            999999.00
        );

        RAISE NOTICE 'Transfer succeeded';

    EXCEPTION
        WHEN SQLSTATE 'P1001' THEN
            RAISE NOTICE 'Business error: insufficient funds';
    END;

    RAISE NOTICE 'Application flow continues';
END;
$do$;
~~~

`transfer_funds` raises an exception before performing any UPDATE because the balance is insufficient. The outer handler catches `P1001` and can report a business error instead of letting the client receive a raw SQL exception.

### Do Not Equate "Handler Finished" with "Transfer Succeeded"

If an API calls the function inside a handler like this, it must distinguish **successful transfer** from **insufficient funds**. A handler that only logs NOTICE and returns normally is a control-flow illustration; in a real application, return a structured status or let the service handle coded errors.

### When Should a Transfer Function Catch Exceptions Internally?

Only when the function has a specific recovery or diagnostic rule and still preserves atomicity. Catching `WHEN OTHERS THEN NULL;` just so "the app doesn't throw an error" can hide failed transactions and corrupt business results.

## 45. Exception Is Local Rollback, Not Transaction Retry

Certain errors require retries from the caller:

- `40001` — `serialization_failure`.
- `40P01` — `deadlock_detected`.

Example application rule:

~~~text
For each attempt up to a bounded retry count:
  BEGIN transaction
  Read relevant state and validate conditions
  Call business function(s)
  COMMIT
On SQLSTATE 40001 or 40P01:
  ROLLBACK
  Apply backoff
  Restart the WHOLE transaction and recompute decisions
On unique/validation errors:
  Handle according to business contract; do not retry blindly
~~~

**Do not retry only the final UPDATE statement** using data computed from a stale snapshot or old checks. Concurrency errors generally require re-evaluating the entire logic in a fresh transaction.

Likewise, do not write a PL/pgSQL loop catching `40001` and retrying indefinitely within a single call, as behavior depends on isolation levels, snapshots, and transaction boundaries.

## 46. When to Use EXCEPTION Instead of ON CONFLICT?

If the goal is to skip an already-existing `event_key`:

~~~sql
INSERT INTO plpgsql_lab.events (
    event_key, detail
)
VALUES (
    'existing-event',
    'Duplicate is an expected case'
)
ON CONFLICT (event_key)
DO NOTHING;
~~~

Compared to:

~~~sql
BEGIN
    INSERT INTO plpgsql_lab.events (
        event_key, detail
    )
    VALUES (
        'existing-event',
        'Duplicate is an expected case'
    );
EXCEPTION
    WHEN unique_violation THEN
        NULL;
END;
~~~

`ON CONFLICT` is usually clearer when duplicates on a specific key are an expected business branch. It avoids using exceptions for normal control flow and eliminates the risk of catching a UNIQUE violation from somewhere else.

### When EXCEPTION Is Truly Useful

- You need to roll back changes across a multi-statement block and take an alternative path.
- You need `SQLSTATE`/DETAIL/CONSTRAINT_NAME metadata from an unexpected error.
- You need to classify an error and translate it into an appropriate error contract.
- You need a narrow handler for logic that a single SQL statement cannot express.

## 47. EXCEPTION Does Not Replace Validation

For amounts:

~~~sql
IF p_amount IS NULL OR p_amount <= 0 THEN
    RAISE EXCEPTION 'Amount must be positive'
        USING ERRCODE = '22023';
END IF;
~~~

this is explicit validation. You should not blindly run an `UPDATE` that might violate a CHECK constraint and rely on a `check_violation` handler for every negative value when inputs can be checked upfront.

Still, database constraints must remain in place. Application or function validation can be bypassed via another write path; `CHECK`/`UNIQUE`/`FK` constraints are the final line of defense.

### Two-Layer Design

1. Validate inputs and business rules to return clear errors.
2. Keep constraints in the database to guard against errors from any write path.
3. Catch specific exceptions when handling race conditions or translating errors.
4. Do not swallow constraint errors outside the designed set.

## 48. Scope of EXCEPTION and Nested Blocks

An outer block does not automatically roll back its own changes when an inner block catches an error, provided those outer changes lie outside the inner block's protected rollback boundary.

Conversely, if **the outer block also has an `EXCEPTION` section** and an error propagates up to the outer handler, database changes in the outer protected portion are rolled back by the outer block's mechanism—including statements that had succeeded in earlier inner blocks.

~~~text
Outer protected statements
  ├── INSERT A
  ├── Inner block
  │     └── INSERT B
  └── RAISE EXCEPTION
Outer EXCEPTION handler
  └── Both A and B have been rolled back upon entering the outer handler
~~~

The rule depends on **which block actually catches the error**. Never look at a statement that "printed NOTICE successfully" and assume its row was committed.

### Be Careful with Local Variables

While database state rolls back, assigned PL/pgSQL variables retain their values. When code passes through multiple nested handlers, variables may no longer reflect the current database state unless recomputed.

## 49. Do Not Use EXCEPTION as an Autonomous Transaction

Some database systems offer autonomous transactions for isolated logging. **PostgreSQL's PL/pgSQL exception blocks do not become autonomous transactions.**

Example:

~~~sql
BEGIN;

DO $do$
BEGIN
    BEGIN
        RAISE EXCEPTION 'Example failure';
    EXCEPTION
        WHEN raise_exception THEN
            INSERT INTO plpgsql_lab.events (
                event_key, detail
            )
            VALUES (
                'audit-attempt',
                'This is still in outer SQL transaction'
            );
    END;
END;
$do$;

ROLLBACK;
~~~

The `audit-attempt` row is also rolled back when the outer transaction rolls back.

If the requirement is "failure logs must persist even when the main transaction rolls back," design logging through an appropriate channel or a supported separate-transaction mechanism with explicit trade-offs—never assume `EXCEPTION` does this.

## 50. Labeling and Splitting Large Functions

An oversized function with dozens of nested blocks is hard to read:

~~~text
Function
  DECLARE 20 variables
  BEGIN
    IF ...
      BEGIN
        LOOP ...
          BEGIN
            EXCEPTION ...
          END
        END LOOP
      EXCEPTION ...
      END
    END IF
  EXCEPTION ...
  END
~~~

Recommended practices:

- Split logic into functions with clear responsibilities.
- Use nested blocks only when genuine local scope or local rollback behavior is needed.
- Use labels to close and organize complex blocks.
- Declare variables close to the scope where they are actually used.
- Catch errors narrowly; avoid criteria-free `WHEN OTHERS`.
- Keep transaction boundaries in the caller/service as designed.
- Test both success paths and error paths.

Do not split code solely to shorten line counts; what matters is keeping variable scope, data flow, and exception semantics easy to understand.

## 51. Distinguishing BEGIN, END IF, END LOOP, and END CASE

| Opening Syntax | Closing Syntax | Role |
| --- | --- | --- |
| `BEGIN` | `END;` or `END label;` | PL/pgSQL block |
| `IF ... THEN` | `END IF;` | Conditional branch |
| `LOOP` | `END LOOP;` | Loop |
| `CASE ...` statement | `END CASE;` | PL/pgSQL CASE statement |
| `$fn$` | `$fn$;` | Terminates the body literal of CREATE FUNCTION |

Example:

~~~sql
DO $do$
DECLARE
    v_i integer := 0;
BEGIN
    LOOP
        v_i := v_i + 1;

        IF v_i >= 3 THEN
            EXIT;
        END IF;
    END LOOP;

    RAISE NOTICE 'Finished at %', v_i;
END;
$do$;
~~~

The number of `END` keywords does not equal the number of transactions. Each keyword closes its corresponding syntactic construct.

## 52. Semicolons in PL/pgSQL

Valid example:

~~~sql
DO $do$
DECLARE
    v_count integer := 0;
BEGIN
    v_count := v_count + 1;
    RAISE NOTICE 'Count = %', v_count;
END;
$do$;
~~~

Two terminators are needed:

1. `END;`: closes the block inside the DO body.
2. `$do$;`: the `;` terminates the SQL DO statement.

For a function:

~~~sql
CREATE OR REPLACE FUNCTION plpgsql_lab.identity_number(
    p_input integer
)
RETURNS integer
LANGUAGE plpgsql
AS $fn$
BEGIN
    RETURN p_input;
END;
$fn$;
~~~

Do not omit `;` after `RETURN` or after `END`.

### EXCEPTION Has No Semicolon Immediately After the Keyword

Correct:

~~~sql
EXCEPTION
    WHEN division_by_zero THEN
        RAISE NOTICE 'Division by zero';
~~~

Do not write `EXCEPTION;` as a standalone statement.

## 53. Common Mistakes

### 53.1. Thinking PL/pgSQL BEGIN Starts an SQL Transaction

`BEGIN ... END` inside a function or `DO` is a block. Transactions are managed by the SQL caller according to environment rules.

### 53.2. Using COMMIT Inside a Function

Functions must not commit the caller's transaction; procedures and `DO` have specific rules and forbid transaction control inside exception-block subtransactions.

### 53.3. Writing DECLARE Between Statements Without Opening a New Block

Declarations must precede `BEGIN` for their corresponding block.

### 53.4. Confusing END IF and END

`END IF;` closes an IF statement; `END;` closes a block. They are not interchangeable.

### 53.5. Declaring Variables with the Same Names as Columns

This can cause ambiguous references or alter query meaning. Use table aliases for columns and prefixes for variables.

### 53.6. Thinking Local Variables Have Session-Wide Scope

Variables belong to a block/function execution, not persistent session state.

### 53.7. Thinking Variables Automatically Roll Back After EXCEPTION

Database changes in the protected portion roll back, but PL/pgSQL variables retain their assigned values.

### 53.8. Thinking Execution Resumes After the Error Inside BEGIN Once Handled

Once control enters the handler, remaining statements before `EXCEPTION` are not executed.

### 53.9. Thinking EXCEPTION Automatically Commits Handler Writes

The handler still belongs to the outer SQL transaction; an outer rollback will undo everything.

### 53.10. Catching WHEN OTHERS and Staying Silent

This can hide data or logic errors and produce false success responses.

### 53.11. Thinking OTHERS Catches Absolutely Every Error

Special conditions such as `QUERY_CANCELED` and `ASSERT_FAILURE` behave differently under PostgreSQL semantics.

### 53.12. Failing to Rethrow Unexpected Errors

If there is no safe recovery plan, `RAISE;` is usually better than swallowing the error.

### 53.13. Catching unique_violation Around Too Many SQL Statements

You might catch a UNIQUE violation from a different constraint and misinterpret it as an expected duplicate.

### 53.14. Using Exceptions for Routine Duplicates

Where appropriate, `ON CONFLICT` is clearer and avoids repeated exception/subtransaction overhead.

### 53.15. Using SELECT INTO Without STRICT When Exactly One Row Is Required

It can silently assign NULL or an arbitrary row when multiple results exist.

### 53.16. Confusing PL/pgSQL SELECT INTO with SQL Table Creation

In PL/pgSQL, `SELECT ... INTO variable` assigns variables.

### 53.17. Checking FOUND After Several Subsequent Statements

It may have been overwritten by another statement. Check it immediately after the relevant statement.

### 53.18. Confusing GET DIAGNOSTICS with GET STACKED DIAGNOSTICS

One reads statement execution status; the other reads error details inside a handler.

### 53.19. Using SQLSTATE/SQLERRM Outside a Handler Expecting the Current Error

Read them within a valid exception-handling context.

### 53.20. Thinking RAISE NOTICE Equals RAISE EXCEPTION

NOTICE emits a message; EXCEPTION raises an error and transfers control through exception handling.

### 53.21. Thinking WHEN OTHERS Is a Retry Strategy

A handler does not automatically retry, and concurrency errors generally require retrying the whole transaction in the caller.

### 53.22. Using Too Many EXCEPTION Blocks Inside Loops

Subtransactions and exception handling add overhead; avoid using errors as routine branching over millions of rows.

### 53.23. Failing to Distinguish Handler Errors from Protected-Block Errors

Exceptions raised **inside a handler** require an outer block to catch; the same handler list does not re-catch errors thrown by a handler.

### 53.24. Returning Raw Diagnostics to End Users

This can leak schema details, SQL context, or sensitive data; enforce an error contract and logging policy.

### 53.25. Using Complex Nested Blocks to Hide Unclear Business Rules

Split logic into routines with explicit responsibilities, and test error paths and transaction behavior.

## 54. Practice Exercises with Answers

Practice after setting up the `plpgsql_lab` schema. For examples containing DML, wrap them in SQL `BEGIN; ... ROLLBACK;` using a single connection. Examples that intentionally raise uncaught errors must be rolled back before continuing.

### Exercise 1. Minimal Block

**Task:** Emit NOTICE "Hello PL/pgSQL".

~~~sql
DO $do$
BEGIN
    RAISE NOTICE 'Hello PL/pgSQL';
END;
$do$;
~~~

**Explanation:** Neither `DECLARE` nor `EXCEPTION` is needed; `BEGIN/END` are required.

### Exercise 2. Declaration and Addition

~~~sql
DO $do$
DECLARE
    v_a integer := 12;
    v_b integer := 8;
    v_total integer;
BEGIN
    v_total := v_a + v_b;
    RAISE NOTICE 'Total = %', v_total;
END;
$do$;
~~~

**Answer:** `v_total = 20`.

### Exercise 3. CONSTANT

**Question:** Can a variable declared as `CONSTANT` be reassigned after `BEGIN`?

**Answer:** No. A constant must be initialized appropriately and cannot be reassigned.

### Exercise 4. Uninitialized Variable

**Question:** What is the initial value of `DECLARE v_note text;`?

**Answer:** SQL NULL by default.

### Exercise 5. NOT NULL

**Question:** What happens if NULL is assigned to an `integer NOT NULL` variable?

**Answer:** PostgreSQL raises an error; a NOT NULL variable does not allow NULL values.

### Exercise 6. Nested Block Scope

~~~sql
DO $do$
DECLARE
    v_outer integer := 5;
BEGIN
    DECLARE
        v_inner integer := 7;
    BEGIN
        RAISE NOTICE 'Sum=%', v_outer + v_inner;
    END;
END;
$do$;
~~~

**Answer:** The inner block can read `v_outer`; prints 12. After the inner `END`, `v_inner` is no longer in scope for outer statements.

### Exercise 7. Shadowing

**Question:** If an inner block declares `v_name` with the same name as the outer block, which variable does an unqualified `v_name` inside refer to?

**Answer:** The inner variable according to nearest-scope resolution; the outer variable is shadowed.

### Exercise 8. Qualified Label

~~~sql
DO $do$
<<outer_block>>
DECLARE
    v_name text := 'outer';
BEGIN
    DECLARE
        v_name text := 'inner';
    BEGIN
        RAISE NOTICE '% / %',
            v_name, outer_block.v_name;
    END;
END outer_block;
$do$;
~~~

**Answer:** Prints `inner / outer`.

### Exercise 9. Does BEGIN ... END Commit?

**Answer:** No. PL/pgSQL `BEGIN/END` defines a block; the outer SQL transaction still controls `COMMIT`/`ROLLBACK`.

### Exercise 10. SELECT INTO with No Rows

~~~sql
DO $do$
DECLARE
    v_balance numeric;
BEGIN
    SELECT balance INTO v_balance
    FROM plpgsql_lab.accounts
    WHERE account_id = -1;

    RAISE NOTICE 'Found? %', FOUND;
END;
$do$;
~~~

**Answer:** `FOUND=false` if account -1 does not exist; the target receives NULL under non-STRICT rules.

### Exercise 11. INTO STRICT with No Rows

~~~sql
DO $do$
DECLARE
    v_balance numeric;
BEGIN
    BEGIN
        SELECT balance INTO STRICT v_balance
        FROM plpgsql_lab.accounts
        WHERE account_id = -1;
    EXCEPTION
        WHEN no_data_found THEN
            RAISE NOTICE 'Not found';
    END;
END;
$do$;
~~~

**Answer:** `NO_DATA_FOUND` is caught by the handler.

### Exercise 12. When Does TOO_MANY_ROWS Occur?

**Answer:** When `SELECT ... INTO STRICT` receives more than one row instead of exactly one row.

### Exercise 13. What Does PERFORM Do?

**Answer:** Executes a query while discarding its return values; `FOUND` can be checked to see whether rows were produced according to statement semantics.

### Exercise 14. ROW_COUNT

~~~sql
BEGIN;

DO $do$
DECLARE
    v_updated bigint;
BEGIN
    UPDATE plpgsql_lab.accounts
    SET updated_at = clock_timestamp()
    WHERE account_id IN (1, 2);

    GET DIAGNOSTICS v_updated = ROW_COUNT;
    RAISE NOTICE 'Rows=%', v_updated;
END;
$do$;

ROLLBACK;
~~~

**Answer:** Expected `v_updated = 2` on the standard seed data.

### Exercise 15. Catching Division by Zero

~~~sql
DO $do$
BEGIN
    PERFORM 10 / 0;
EXCEPTION
    WHEN division_by_zero THEN
        RAISE NOTICE 'Handled division by zero';
END;
$do$;
~~~

**Answer:** The handler catches SQLSTATE `22012`.

### Exercise 16. Catching UNIQUE

**Question:** Which condition is raised by inserting `event_key='existing-event'` into the events table?

**Answer:** `unique_violation`, SQLSTATE `23505`.

### Exercise 17. With Two WHEN Clauses

**Question:** If the error is `division_by_zero` and branches exist for both `division_by_zero` and `OTHERS`, which branch runs?

**Answer:** The specific matching branch `division_by_zero`; execution does not continue into `OTHERS`.

### Exercise 18. Does OTHERS Catch All Errors?

**Answer:** No; there are special conditions such as `QUERY_CANCELED` and `ASSERT_FAILURE`.

### Exercise 19. Unmatched Handler

**Question:** If an inner block only catches `division_by_zero` but `unique_violation` is raised, what happens?

**Answer:** The error propagates to the outer block/caller, where a matching handler may exist; otherwise the statement/transaction fails.

### Exercise 20. What Does EXCEPTION Roll Back?

**Answer:** Database changes inside the block's protected portion are rolled back when the exception is caught; DB changes made before the inner block outside that scope are not rolled back simply because of the inner exception.

### Exercise 21. Local Variables After Internal Rollback?

**Answer:** Assigned variable values remain as set. PL/pgSQL variables do not automatically roll back like database rows.

### Exercise 22. Does an Audit INSERT in a Handler Commit Independently?

**Answer:** No. The handler's INSERT still belongs to the outer SQL transaction; an outer `ROLLBACK` will undo it.

### Exercise 23. Where Are SQLSTATE and SQLERRM Used?

**Answer:** Inside an exception handler to read the code and message of the error being handled.

### Exercise 24. Retrieving the Violated Constraint Name

~~~sql
DO $do$
DECLARE
    v_constraint text;
BEGIN
    INSERT INTO plpgsql_lab.events(event_key)
    VALUES ('existing-event');

EXCEPTION
    WHEN unique_violation THEN
        GET STACKED DIAGNOSTICS
            v_constraint = CONSTRAINT_NAME;

        RAISE NOTICE 'Constraint=%', v_constraint;
END;
$do$;
~~~

**Answer:** The handler receives the constraint name from exception diagnostics when available.

### Exercise 25. What Does RAISE; Do?

**Answer:** Re-throws the exact exception currently being handled up to the caller or an outer handler, preserving original error semantics.

### Exercise 26. Who Catches Errors Inside a Handler?

**Answer:** An appropriate outer block/handler. The handler list of the same block does not re-catch errors raised inside its own handler.

### Exercise 27. What Should Be Used When Duplicates Are Normal?

**Answer:** `INSERT ... ON CONFLICT (event_key) DO NOTHING` is usually clearer and avoids using exceptions as normal control flow.

### Exercise 28. Why Does the Transfer Function Not Catch WHEN OTHERS THEN NULL?

**Answer:** It could turn a failed business transaction into an apparently successful result, preventing the caller from rolling back or handling the failure properly.

### Exercise 29. Why Not Retry Infinitely After SQLSTATE 40001?

**Answer:** You must roll back and retry **the whole transaction**, bound the retry count, and recompute business conditions. Infinite retries or retrying only the last SQL statement can be wrong or get stuck.

### Exercise 30. Cost Issue When Using EXCEPTION Millions of Times?

**Answer:** Handlers incur subtransaction overhead, and frequent exceptions add error-processing cost. Prefer set-based SQL, upfront validation, or `ON CONFLICT` where appropriate.

## 55. Best-Practice Checklist

- [ ] Blocks have `BEGIN ... END;` in the proper positions.
- [ ] `DECLARE` precedes `BEGIN`, declaring only variables needed by the block.
- [ ] Declare appropriate types and initializers; verify `NOT NULL`/`CONSTANT`.
- [ ] Use `%TYPE`/`%ROWTYPE` when types should stay aligned with the schema.
- [ ] Use variable prefixes and table aliases to avoid ambiguous names.
- [ ] Create nested blocks only when local scope or local rollback is needed.
- [ ] Use `<<label>>` when nesting or shadowing is complex.
- [ ] Distinguish `END;`, `END IF;`, `END LOOP;`, and `END CASE;`.
- [ ] Use `SELECT INTO STRICT` when exactly one row is expected.
- [ ] Check `FOUND`/`ROW_COUNT` immediately after the relevant statement.
- [ ] Catch specific errors using condition names or SQLSTATE.
- [ ] Do not treat `WHEN OTHERS` as a catch-all solution for every error.
- [ ] Use `GET STACKED DIAGNOSTICS` inside handlers when error metadata is needed.
- [ ] Do not expose raw sensitive error context in public APIs.
- [ ] Understand that exception blocks roll back **DB state**, not **local variables**.
- [ ] Do not treat handler/audit INSERTs as autonomous transactions.
- [ ] Rethrow errors that cannot be safely handled using `RAISE;`.
- [ ] Prefer `ON CONFLICT` for expected duplicates instead of overusing exceptions.
- [ ] Avoid exception blocks in hot loops when simpler alternatives exist.
- [ ] Never call `COMMIT` inside a function; procedures and `DO` have specific limits.
- [ ] Place SQL transaction boundaries in the caller/service as designed.
- [ ] Wrap data-modifying lab examples in SQL transactions and roll back afterward.
- [ ] Test success paths as well as validation, UNIQUE, FK, and insufficient-funds errors.
- [ ] For `40001`/`40P01`, implement bounded whole-transaction retries when safe.
- [ ] When code grows long, split responsibilities into clear routines instead of arbitrarily nesting handlers.
- [ ] Never run exception demos or `DROP SCHEMA` in production.

## 56. Official PostgreSQL Documentation

Sources to consult for the **major version of your PostgreSQL server**:

- [PL/pgSQL Structure](https://www.postgresql.org/docs/current/plpgsql-structure.html) — block structure, labels, variable scope.
- [PL/pgSQL Declarations](https://www.postgresql.org/docs/current/plpgsql-declarations.html) — DECLARE, CONSTANT, NOT NULL, %TYPE, %ROWTYPE.
- [PL/pgSQL Basic Statements](https://www.postgresql.org/docs/current/plpgsql-statements.html) — variable assignment, SELECT INTO, PERFORM, EXECUTE, diagnostics.
- [PL/pgSQL Control Structures](https://www.postgresql.org/docs/current/plpgsql-control-structures.html) — IF/LOOP/RETURN, exception handling.
- [Errors and Messages](https://www.postgresql.org/docs/current/plpgsql-errors-and-messages.html) — RAISE levels, SQLSTATE, message/detail/hint.
- [Error Codes](https://www.postgresql.org/docs/current/errcodes-appendix.html) — 23505, 23503, P0001, P0002, P0003, 40001.
- [DO](https://www.postgresql.org/docs/current/sql-do.html) — executing anonymous code blocks.
- [CREATE FUNCTION](https://www.postgresql.org/docs/current/sql-createfunction.html) — function signatures and LANGUAGE plpgsql.
- [CREATE PROCEDURE](https://www.postgresql.org/docs/current/sql-createprocedure.html) — procedures and CALL.
- [CALL](https://www.postgresql.org/docs/current/sql-call.html) — how to invoke procedures.
- [Transaction Management](https://www.postgresql.org/docs/current/plpgsql-transactions.html) — transaction control in procedures/DO and its limits.
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html) — concurrency, snapshots, and retries.
- [INSERT](https://www.postgresql.org/docs/current/sql-insert.html) — ON CONFLICT as an exception-free alternative.
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html) — row locks and deadlocks.

The `/current/` URLs point to the latest PostgreSQL documentation; when a server runs a specific major version, check the corresponding versioned documentation for exact syntax and applicable limits.

## 57. Summary

**Blocks are the organizational unit for control flow and scope in PL/pgSQL.** Properly understanding `DECLARE`, `BEGIN`, `EXCEPTION`, and `END` helps you write clear functions and procedures and handle errors without breaking data consistency.

Key takeaways:

1. **`DECLARE`** defines variables and initial values; **`BEGIN`** starts statements; **`EXCEPTION`** is an optional error-catching section; **`END`** closes the block.
2. **PL/pgSQL `BEGIN ... END` is not an SQL transaction.** `COMMIT`/`ROLLBACK` belong to the caller-managed transaction context, with specific limits for procedures/`DO`.
3. **Blocks can be nested and labeled.** Scope and shadowing determine which variable is read; `outer_block.variable` accesses a shadowed outer variable.
4. **`SELECT ... INTO STRICT`** enforces exactly one row and uses `NO_DATA_FOUND` and `TOO_MANY_ROWS`.
5. **When a handler catches an error**, PostgreSQL rolls back database changes in the protected block via an internal subtransaction; however, assigned PL/pgSQL variables retain their values.
6. **Handlers do not auto-commit** and do not re-run the statement section after an error. Errors raised inside a handler require an outer block to handle.
7. **`SQLSTATE`, `SQLERRM`, and `GET STACKED DIAGNOSTICS`** help classify and record errors. `RAISE;` rethrows the original error when it cannot be handled safely.
8. **Avoid catching `WHEN OTHERS THEN NULL;` unconditionally**; it can mask bugs and turn failed operations into apparent successes.
9. **Use exceptions for real errors**, while expected business branches should use validation or SQL features like `ON CONFLICT` when appropriate.
10. **Design transactions and retries explicitly**, especially with multi-step operations, concurrency, and external side effects.

When you properly separate **block scope, transaction scope, and exception-handling scope**, you can use PL/pgSQL to write testable multi-step logic, handle errors accurately, and protect PostgreSQL data consistency.
