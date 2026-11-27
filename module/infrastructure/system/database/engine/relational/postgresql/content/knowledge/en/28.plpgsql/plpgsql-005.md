# LOOP, WHILE, FOR, FOREACH, and Loop Control in PL/pgSQL

In PostgreSQL, **PL/pgSQL** is a procedural language for writing functions, procedures, and anonymous code blocks with variables, conditionals, branching, loops, exceptions, and SQL. When working with datasets, PostgreSQL excels at **set-based SQL**; however, some tasks require stateful iteration, dynamic stopping conditions, traversing array elements, or intentionally processing rows one by one.

For example, a batch job might process up to 10 pending tasks, count attempts, and stop if a threshold is exceeded. Another function might iterate over values in an SQL array to compute a result or build a message. Such problems can use these constructs:

- `LOOP ... END LOOP`: general-purpose loop whose stopping condition you write with `EXIT`.
- `WHILE condition LOOP ... END LOOP`: checks the condition **before each iteration**.
- `FOR integer_variable IN lower..upper LOOP`: iterates over an integer range, supporting `REVERSE` and `BY`.
- `FOR record_variable IN query LOOP`: iterates over the rows of an SQL query.
- `FOR record_variable IN EXECUTE dynamic_query USING ... LOOP`: iterates over results of dynamic SQL.
- `FOREACH variable IN ARRAY expression LOOP`: iterates over elements of an **SQL array**, supporting `SLICE`.
- `EXIT`, `CONTINUE`, loop labels, and `RETURN` statements: control execution flow.

The lesson **"LOOP, WHILE, FOR, FOREACH, and Loop Control"**, in the **PL/pgSQL** chapter of the **Database Engine Relational PostgreSQL** module, covers syntax through practical usage in functions and procedures—avoiding infinite loops, handling errors, controlling transactions, and choosing set-based SQL when it is better.

> **Practice Safety:** All examples creating or modifying tables use a dedicated lab database. Never run data-modifying procedures, `DO` blocks containing DML, or heavy-load loops in production without controlling scope and transactions.

---

## 1. How PL/pgSQL Loops Differ from SQL SELECT

SQL expresses **the dataset to process**:

~~~sql
SELECT job_id
FROM pl_loop_lab.jobs
WHERE status = 'pending';
~~~

PL/pgSQL additionally expresses **control flow**:

~~~text
Initialize variables
     |
     v
Check condition
     |
     +-- false --> finish
     |
     v
Execute loop body
     |
     +--> update state / log
     |
     +--> CONTINUE, EXIT, or next iteration
~~~

When 100,000 rows can be processed by a single `UPDATE ... WHERE`, you usually **do not need** to loop 100,000 times running individual `UPDATE`s.

Loops are useful when each step needs different decisions, dependencies exist across iterations, batches must be capped, array elements must be processed, or control flow cannot be cleanly expressed in a single SQL statement.

### 1.1. Comparing the Constructs

| Construct | Iteration Source | Stopping Condition | Best Fit |
|---|---|---|---|
| `LOOP` | Unbounded by syntax | `EXIT`, `RETURN`, or error | Retries, state machines, complex exit conditions |
| `WHILE` | Boolean expression | When condition is not TRUE | Looping until a threshold or state change |
| `FOR i IN a..b` | Integer range | Exhausting the defined range | Counting iterations, generating sequence numbers |
| `FOR rec IN SELECT` | Query rows | Exhausting rows | Ordered processing over SQL results |
| `FOREACH ... IN ARRAY` | SQL array elements | Exhausting array | Iterating scalar elements or array slices |

`FOR` has several variants, so the actual set of constructs is broader than four names.

## 2. Where Are Loops Used?

PL/pgSQL loops appear in:

- `CREATE FUNCTION ... LANGUAGE plpgsql`.
- `CREATE PROCEDURE ... LANGUAGE plpgsql`.
- `DO $$ ... $$ LANGUAGE plpgsql` blocks.
- Trigger functions written in PL/pgSQL.

Shortest example using `DO` to observe output:

~~~sql
DO $$
DECLARE
    v_i INTEGER;
BEGIN
    FOR v_i IN 1..3 LOOP
        RAISE NOTICE 'Iteration %', v_i;
    END LOOP;
END;
$$ LANGUAGE plpgsql;
~~~

`NOTICE` messages appear in clients like `psql`, pgAdmin, or administrative tools depending on message settings. This is an **immediate one-off block**, not a saved function.

### 2.1. PL/pgSQL BEGIN Is Not BEGIN TRANSACTION

~~~sql
DO $$
BEGIN
    RAISE NOTICE 'Hello';
END;
$$;
~~~

`BEGIN ... END` is **PL/pgSQL block** syntax; it does not open a subtransaction. External SQL transactions use separate commands like `BEGIN; COMMIT; ROLLBACK;`.

### 2.2. Fundamental PL/pgSQL Structure

~~~sql
CREATE FUNCTION schema_name.example()
RETURNS INTEGER
LANGUAGE plpgsql
AS $body$
DECLARE
    v_result INTEGER := 0;
BEGIN
    -- Statements, conditionals, loops.
    RETURN v_result;
END;
$body$;
~~~

- `DECLARE` holds variable declarations.
- `:=` assigns values.
- `BEGIN ... END` wraps the block body.
- `LOOP`/`WHILE`/`FOR`/`FOREACH` are statements inside the block.
- `RETURN` exits a scalar-returning function when executed.

## 3. Reproducible Sample Data Schema

To practice with a stateful table and attempt counters, run in an **empty lab database**:

~~~sql
CREATE SCHEMA pl_loop_lab;

CREATE TABLE pl_loop_lab.jobs (
    job_id BIGINT PRIMARY KEY,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN (
            'pending', 'processing', 'done', 'failed'
        )),
    attempt_count INTEGER NOT NULL DEFAULT 0
        CHECK (attempt_count >= 0),
    created_at TIMESTAMPTZ NOT NULL
        DEFAULT statement_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL
        DEFAULT statement_timestamp()
);

CREATE TABLE pl_loop_lab.job_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_id BIGINT NOT NULL
        REFERENCES pl_loop_lab.jobs(job_id),
    event_type TEXT NOT NULL,
    event_note TEXT,
    created_at TIMESTAMPTZ NOT NULL
        DEFAULT statement_timestamp()
);

INSERT INTO pl_loop_lab.jobs (
    job_id, description, status, attempt_count
)
VALUES
    (1, 'Validate file A', 'pending', 0),
    (2, 'Import file B', 'pending', 1),
    (3, 'Export report C', 'done', 1),
    (4, 'Validate file D', 'pending', 0),
    (5, 'Send summary E', 'failed', 3),
    (6, 'Import file F', 'pending', 0),
    (7, 'Export report G', 'processing', 1),
    (8, 'Validate file H', 'pending', 2);

ANALYZE pl_loop_lab.jobs;
~~~

The dataset contains 8 jobs, of which 5 are in `'pending'` status (IDs 1, 2, 4, 6, 8).

### 3.1. Inspect Initial Data

~~~sql
SELECT
    job_id,
    status,
    attempt_count
FROM pl_loop_lab.jobs
ORDER BY job_id;
~~~

**Read-only** examples can run without altering the dataset. DML examples should be wrapped in a transaction with `ROLLBACK` in the lab to preserve initial state.

## 4. LOOP: General-Purpose Loop

Syntax:

~~~sql
[ <<label>> ]
LOOP
    statements;
END LOOP [ label ];
~~~

`LOOP` has no condition at the top. It continues until:

- A matching `EXIT` executes.
- The function executes `RETURN`.
- An error unwinds execution.
- Another valid control-flow construct exits the block.

### 4.1. Example: Incrementing a Counter and EXIT

~~~sql
DO $$
DECLARE
    v_counter INTEGER := 0;
BEGIN
    LOOP
        v_counter := v_counter + 1;

        RAISE NOTICE 'counter=%', v_counter;

        EXIT WHEN v_counter >= 5;
    END LOOP;
END;
$$;
~~~

Flow:

~~~text
counter = 0
  |
  v
+1 -> 1 -> EXIT? no
+1 -> 2 -> EXIT? no
+1 -> 3 -> EXIT? no
+1 -> 4 -> EXIT? no
+1 -> 5 -> EXIT? yes
  |
  v
End LOOP
~~~

### 4.2. EXIT WHEN Is Shorthand

Two equivalent ways to express the same intent:

~~~sql
EXIT WHEN v_counter >= 5;
~~~

and:

~~~sql
IF v_counter >= 5 THEN
    EXIT;
END IF;
~~~

`EXIT WHEN` is concise for simple stopping conditions. `IF ... THEN EXIT` is useful when you need to log or perform checks before exiting.

## 5. Placing EXIT at the Top vs. Bottom of a Loop

Checking right at the top:

~~~sql
DO $$
DECLARE
    v_i INTEGER := 0;
BEGIN
    LOOP
        EXIT WHEN v_i >= 3;

        v_i := v_i + 1;
        RAISE NOTICE 'i=%', v_i;
    END LOOP;
END;
$$;
~~~

The main loop body runs 3 times.

Checking at the bottom:

~~~sql
DO $$
DECLARE
    v_i INTEGER := 0;
BEGIN
    LOOP
        v_i := v_i + 1;
        RAISE NOTICE 'i=%', v_i;

        EXIT WHEN v_i >= 3;
    END LOOP;
END;
$$;
~~~

still runs 3 times in this example, but behaves differently if the initial value already satisfies the stopping condition.

### 5.1. Risk of Bottom-Checking

If an operation must not execute even once when the stopping condition is already true upfront, check the condition **before** the operation.

### 5.2. Can You Exit Without EXIT?

`RETURN` exits the entire function (or routine per its type), not just the loop. Never use `RETURN` in place of `EXIT` when work remains after the loop.

## 6. Infinite Loops and Safety Caps

A bug:

~~~sql
DO $$
BEGIN
    LOOP
        RAISE NOTICE 'never stops';
    END LOOP;
END;
$$;
~~~

is a loop with no intentional stopping condition. **Do not run this snippet.**

An infinite loop can:

- Keep a backend CPU-bound.
- Generate heavy WAL/I/O if it performs DML.
- Hold transactions and locks open indefinitely.
- Flood logs if it calls `RAISE`.
- Block other schema operations.
- Require administrative cancellation of the query or session.

### 6.1. Adding an Iteration Cap

~~~sql
DO $$
DECLARE
    v_attempt INTEGER := 0;
    v_max_attempt INTEGER := 10;
BEGIN
    LOOP
        EXIT WHEN v_attempt >= v_max_attempt;

        v_attempt := v_attempt + 1;
        RAISE NOTICE 'attempt=%', v_attempt;
    END LOOP;
END;
$$;
~~~

In production programs, stopping conditions also need timeouts, retry policies, and resource limits—never rely solely on "the task will finish eventually."

## 7. WHILE: Pre-Checked Condition Per Iteration

Syntax:

~~~sql
WHILE condition LOOP
    statements;
END LOOP;
~~~

PostgreSQL evaluates `condition` before running the loop body. The loop continues **only when the condition is TRUE**.

~~~sql
DO $$
DECLARE
    v_i INTEGER := 0;
BEGIN
    WHILE v_i < 5 LOOP
        v_i := v_i + 1;
        RAISE NOTICE 'i=%', v_i;
    END LOOP;
END;
$$;
~~~

Emits messages 1 through 5.

### 7.1. When Condition Is Initially FALSE

~~~sql
DO $$
DECLARE
    v_i INTEGER := 10;
BEGIN
    WHILE v_i < 5 LOOP
        RAISE NOTICE 'This will not run';
        v_i := v_i + 1;
    END LOOP;
END;
$$;
~~~

The loop body runs **0 times**.

### 7.2. When Condition Is NULL

In PL/pgSQL, `WHILE` continues only when the Boolean expression evaluates to `TRUE`. If it evaluates to `NULL` (unknown), the loop does not run that iteration. Never treat `NULL` as `TRUE`.

## 8. Choosing LOOP vs. WHILE

Two ways to express the same logic:

~~~sql
-- LOOP + EXIT:
LOOP
    EXIT WHEN v_i >= 5;
    v_i := v_i + 1;
END LOOP;
~~~

~~~sql
-- WHILE:
WHILE v_i < 5 LOOP
    v_i := v_i + 1;
END LOOP;
~~~

Practical guideline:

- Use `WHILE` when the continuation condition is **clear at the top of every iteration**.
- Use `LOOP` when there are multiple exit points or the exit check naturally occurs mid-iteration or at the end.
- For a fixed integer range, prefer integer `FOR` over both.
- For an SQL row set, prefer `FOR record IN query` over manual cursor management.

### 8.1. Avoid Duplicating Complex Conditions

If a loop checks three state variables, avoid duplicating the same complex expression across multiple branches; extract a Boolean variable or helper function when it improves clarity.

## 9. Integer FOR: Iterating Over a Numeric Range

Syntax:

~~~sql
FOR variable IN [ REVERSE ] lower_bound..upper_bound
    [ BY step ]
LOOP
    statements;
END LOOP;
~~~

Example:

~~~sql
DO $$
DECLARE
    v_i INTEGER;
BEGIN
    FOR v_i IN 1..5 LOOP
        RAISE NOTICE 'i=%', v_i;
    END LOOP;
END;
$$;
~~~

Values in order: 1, 2, 3, 4, 5.

### 9.1. The Integer FOR Variable Is Automatically Scoped to the Loop

For integer `FOR`, PostgreSQL implicitly creates an **integer loop variable scoped to the loop**, even if an outer variable shares the same name. Thus examples are often written concisely as:

~~~sql
DO $$
BEGIN
    FOR i IN 1..3 LOOP
        RAISE NOTICE '%', i;
    END LOOP;
END;
$$;
~~~

There is no need to declare `i` in `DECLARE`.

### 9.2. The Upper Bound Is Inclusive

`1..5` runs from 1 to 5, **including both 1 and 5**. For 5 zero-based iterations, use `0..4`.

## 10. Integer FOR with REVERSE

~~~sql
DO $$
BEGIN
    FOR i IN REVERSE 5..1 LOOP
        RAISE NOTICE 'i=%', i;
    END LOOP;
END;
$$;
~~~

Produces 5, 4, 3, 2, 1.

### 10.1. Do Not Swap Bounds Without REVERSE

~~~sql
FOR i IN 5..1 LOOP
    ...
END LOOP;
~~~

with the default ascending step does not count downward. When the lower bound exceeds the upper bound, an ascending loop executes 0 iterations.

### 10.2. REVERSE Requires Descending Bound Order

In `FOR i IN REVERSE lower..upper`, PostgreSQL steps down from the first bound to the second. Write `5..1` to count downward; never write `1..5` with `REVERSE` expecting it to count down from 5.

## 11. Integer FOR with BY

`BY` specifies a positive step size; direction is controlled by whether `REVERSE` is present.

~~~sql
DO $$
BEGIN
    FOR i IN 2..10 BY 2 LOOP
        RAISE NOTICE 'even=%', i;
    END LOOP;
END;
$$;
~~~

Output: 2, 4, 6, 8, 10.

~~~sql
DO $$
BEGIN
    FOR i IN REVERSE 10..1 BY 3 LOOP
        RAISE NOTICE 'reverse=%', i;
    END LOOP;
END;
$$;
~~~

Output: 10, 7, 4, 1.

### 11.1. BY Must Be Positive

Never use `BY 0` or `BY -1` to alter stepping. To step backward, use `REVERSE` with a positive step.

### 11.2. When Bounds Are Not Divisible by BY

~~~sql
FOR i IN 1..8 BY 3 LOOP
    ...
END LOOP;
~~~

visits 1, 4, and 7; it does not force an extra iteration at 8.

## 12. Integer FOR Bounds Are Evaluated Once on Loop Entry

The `lower_bound`, `upper_bound`, and `step` expressions of an integer `FOR` loop are evaluated **once when the loop begins**.

~~~sql
DO $$
DECLARE
    v_upper INTEGER := 3;
BEGIN
    FOR i IN 1..v_upper LOOP
        RAISE NOTICE 'i=% upper=%', i, v_upper;
        v_upper := 10;
    END LOOP;
END;
$$;
~~~

The loop still runs 3 iterations rather than extending to 10 when `v_upper` changes inside the body.

### 12.1. When Iteration Count Must React to Runtime State

If you need to re-check a changing threshold on each pass, `WHILE` or `LOOP + EXIT WHEN` fits better than an integer `FOR` with upfront-evaluated bounds.

## 13. Scope of Integer FOR Variables

~~~sql
DO $$
DECLARE
    i INTEGER := 100;
BEGIN
    RAISE NOTICE 'before=%', i;

    FOR i IN 1..3 LOOP
        RAISE NOTICE 'inside=%', i;
    END LOOP;

    RAISE NOTICE 'after=%', i;
END;
$$;
~~~

An integer `FOR` creates its own loop-scoped variable that shadows any outer variable of the same name. Once the loop ends, the outer `i` still holds `100`.

That is why you should never inspect the loop counter after `FOR` ends to deduce how many iterations ran; use a dedicated accumulator variable instead.

## 14. Integer FOR for Bounded Calculations

A function summing 1 to N:

~~~sql
CREATE FUNCTION pl_loop_lab.sum_1_to(
    p_n INTEGER
)
RETURNS BIGINT
LANGUAGE plpgsql
IMMUTABLE
STRICT
AS $$
DECLARE
    v_total BIGINT := 0;
BEGIN
    IF p_n < 0 OR p_n > 100000 THEN
        RAISE EXCEPTION
            'p_n out of supported range: %', p_n;
    END IF;

    FOR i IN 1..p_n LOOP
        v_total := v_total + i;
    END LOOP;

    RETURN v_total;
END;
$$;
~~~

Call:

~~~sql
SELECT pl_loop_lab.sum_1_to(5);
~~~

Result: `15`.

### 14.1. Empty Range

For `p_n = 0`, the range `1..0` runs 0 iterations and returns `0`.

### 14.2. Not Every Series Sum Needs a Loop

For valid N, the mathematical formula:

\[
1 + 2 + \dots + N = \frac{N(N+1)}{2}
\]

is simpler and avoids loop overhead. The example above teaches `FOR`, **not** a recommendation to loop for arithmetic series.

## 15. CONTINUE: Skipping the Remainder of the Current Iteration

`CONTINUE` does not exit the entire loop; it jumps directly to the **next iteration**.

~~~sql
DO $$
BEGIN
    FOR i IN 1..6 LOOP
        CONTINUE WHEN i % 2 = 0;

        RAISE NOTICE 'odd=%', i;
    END LOOP;
END;
$$;
~~~

Prints only 1, 3, 5.

### 15.1. CONTINUE WHEN

~~~sql
CONTINUE WHEN condition;
~~~

is equivalent in intent to:

~~~sql
IF condition THEN
    CONTINUE;
END IF;
~~~

when the condition evaluates to `TRUE`.

### 15.2. Control Flow

~~~text
Inspect a value
       |
       v
Should skip?
    /       \
  Yes       No
   |          |
CONTINUE    Run remaining body
   |          |
   +----------+
       |
       v
 Next iteration
~~~

### 15.3. Never Put Mandatory Updates After CONTINUE

If every iteration must increment an attempt counter, place that update **before** `CONTINUE` or structure the conditionals clearly. Any statement after `CONTINUE` in the same iteration is skipped.

## 16. EXIT: Exiting the Current Loop

~~~sql
DO $$
BEGIN
    FOR i IN 1..10 LOOP
        EXIT WHEN i > 4;

        RAISE NOTICE 'i=%', i;
    END LOOP;
END;
$$;
~~~

Outputs 1, 2, 3, 4. When `i=5`, `EXIT` terminates the loop.

### 16.1. EXIT vs. CONTINUE

| Statement | Effect |
|---|---|
| `CONTINUE` | Skips the rest of the current iteration and moves to the next |
| `EXIT` | Exits the loop |
| `RETURN` | Exits the function returning a result (or terminates the routine) |
| `RAISE EXCEPTION` | Raises an error, catchable by an `EXCEPTION` block |
| `RETURN NEXT` | Emits an item to a set-returning function's result without stopping the loop |

### 16.2. EXIT WHEN Does Not Return a Function Value

`EXIT WHEN ...` only exits the loop; execution continues with statements following `END LOOP;`.

## 17. Loop Labels: <<label>>

With nested loops, labels clarify which loop to exit.

~~~sql
DO $$
BEGIN
    <<outer_loop>>
    FOR i IN 1..3 LOOP
        <<inner_loop>>
        FOR j IN 1..3 LOOP
            RAISE NOTICE 'i=% j=%', i, j;

            EXIT outer_loop
                WHEN i = 2 AND j = 2;
        END LOOP inner_loop;
    END LOOP outer_loop;

    RAISE NOTICE 'finished';
END;
$$;
~~~

When `i=2 AND j=2`, `EXIT outer_loop` exits **both loops**, not just the inner `j` loop.

### 17.1. Where to Place Labels?

~~~sql
<<my_loop>>
LOOP
    ...
END LOOP my_loop;
~~~

Repeating the label at `END LOOP my_loop;` makes nested code easier to follow and must match the opening label when written.

### 17.2. Avoid Ambiguous Labels

Names like `outer_loop` or `jobs_loop` are clearer than `l1`/`l2` in multi-level routines. If you have 4–5 nested loops, consider refactoring into set-based SQL or smaller functions for maintainability.

## 18. CONTINUE with an Outer Loop Label

`CONTINUE outer_loop` skips the remainder of any inner loops and advances to the **next iteration of the outer loop**.

~~~sql
DO $$
BEGIN
    <<customer_loop>>
    FOR customer_id IN 1..3 LOOP
        FOR item_no IN 1..3 LOOP
            IF customer_id = 2 AND item_no = 2 THEN
                CONTINUE customer_loop;
            END IF;

            RAISE NOTICE
                'customer=% item=%',
                customer_id, item_no;
        END LOOP;
    END LOOP customer_loop;
END;
$$;
~~~

For customer 2, once item 2 is encountered, the item loop stops for that customer and control jumps to customer 3.

### 18.1. Label Rules Differ Between EXIT and CONTINUE

`EXIT label` can target a loop or, in appropriate contexts, a labeled `BEGIN ... END` block. `CONTINUE label` must target a loop; never use `CONTINUE` to jump to a non-loop labeled `BEGIN` block.

## 19. Nesting Multiple FOR Loops

Example generating coordinate pairs:

~~~sql
DO $$
BEGIN
    FOR row_no IN 1..3 LOOP
        FOR col_no IN 1..2 LOOP
            RAISE NOTICE
                'cell=(%,%)',
                row_no, col_no;
        END LOOP;
    END LOOP;
END;
$$;
~~~

The inner body executes:

\[
3 \times 2 = 6
\]

times. If each loop runs 1,000 times, total iterations reach one million. Over real database tables, nested loops easily cause **multiplicative complexity**.

### 19.1. When Nested Loops Hide a JOIN

If logic iterates over every customer and then over every order, consider a query like:

~~~sql
SELECT
    c.customer_id,
    j.job_id
FROM pl_loop_lab.jobs AS j
JOIN (
    VALUES (1::BIGINT), (2::BIGINT)
) AS c(customer_id)
    ON (j.job_id % 2) + 1 = c.customer_id;
~~~

This is merely a synthetic JOIN illustration, not a real business relation between jobs and customers. In real applications, use proper foreign keys and JOIN conditions instead of two-level matching loops.

## 20. FOR record IN query: Iterating Over SQL Rows

Syntax:

~~~sql
FOR target IN
    SELECT ...
LOOP
    statements;
END LOOP;
~~~

`target` is typically a `RECORD` variable or a row/composite variable with a compatible shape.

~~~sql
DO $$
DECLARE
    v_job RECORD;
BEGIN
    FOR v_job IN
        SELECT
            job_id,
            description,
            attempt_count
        FROM pl_loop_lab.jobs
        WHERE status = 'pending'
        ORDER BY job_id
    LOOP
        RAISE NOTICE
            'job=% attempts=% desc=%',
            v_job.job_id,
            v_job.attempt_count,
            v_job.description;
    END LOOP;
END;
$$;
~~~

Logical outcome: iterates over pending jobs returned by the SELECT.

### 20.1. Do Not Confuse Integer FOR with Query FOR

- `FOR i IN 1..10 LOOP` implicitly creates an integer loop counter.
- `FOR rec IN SELECT ... LOOP` requires a record/row variable or compatible target variable list.
- `FOR rec IN EXECUTE ... LOOP` runs a dynamic SQL query.

In query `FOR`, the target variable **must be declared** beforehand (or use declared scalar target variables). Do not assume a `record` variable is created automatically like an integer loop counter.

## 21. RECORD and %ROWTYPE

A `RECORD` variable adapts its shape to the rows returned by the query:

~~~sql
DECLARE
    v_record RECORD;
~~~

Access `v_record.job_id` once the loop's SELECT supplies a `job_id` column.

`%ROWTYPE` binds the variable to the row structure of a table or view:

~~~sql
DECLARE
    v_job pl_loop_lab.jobs%ROWTYPE;
~~~

Example:

~~~sql
DO $$
DECLARE
    v_job pl_loop_lab.jobs%ROWTYPE;
BEGIN
    FOR v_job IN
        SELECT *
        FROM pl_loop_lab.jobs
        WHERE status = 'pending'
        ORDER BY job_id
    LOOP
        RAISE NOTICE
            'job=% status=%',
            v_job.job_id,
            v_job.status;
    END LOOP;
END;
$$;
~~~

### 21.1. When to Use RECORD?

- Query selects a custom set of columns.
- Only a few columns from a JOIN are needed.
- Receiving dynamic query results with matching fields.

### 21.2. When to Use %ROWTYPE?

- Query matches the exact row structure of a known table or view.
- You want fields aligned directly with that schema object.
- You need to work with full rows in a suitable operation.

If a query omits a field and code accesses `v_record.some_field`, a runtime error occurs. A flexible `RECORD` variable does not replace verifying output contracts.

## 22. Query FOR with Multiple Scalar Variables

PL/pgSQL allows a list of scalar target variables when the query returns matching columns:

~~~sql
DO $$
DECLARE
    v_job_id BIGINT;
    v_attempt INTEGER;
BEGIN
    FOR v_job_id, v_attempt IN
        SELECT
            job_id,
            attempt_count
        FROM pl_loop_lab.jobs
        WHERE status = 'pending'
        ORDER BY job_id
    LOOP
        RAISE NOTICE
            'job=% attempts=%',
            v_job_id, v_attempt;
    END LOOP;
END;
$$;
~~~

Advantage: no `record` variable needed for two columns. Drawback: changing column order or types in the query can silently break or error. Use explicit column lists and avoid arbitrary `SELECT *`.

## 23. Query FOR and ORDER BY

SQL does not guarantee row order without `ORDER BY`. Therefore, if loop behavior depends on order:

~~~sql
FOR v_job IN
    SELECT job_id
    FROM pl_loop_lab.jobs
    WHERE status = 'pending'
    ORDER BY job_id
LOOP
    ...
END LOOP;
~~~

`ORDER BY job_id` makes traversal order deterministic.

### 23.1. Should You Always Include ORDER BY?

Not necessarily. If rows are independent and order does not matter, sorting adds unnecessary cost. Add `ORDER BY` only when needed for correctness, fairness, pagination/batching, or ordered output.

### 23.2. Ordering Alone Does Not Solve Concurrency

If multiple workers process jobs concurrently, `ORDER BY job_id` does not stop two workers from reading and updating the same row. You still need locking, transactions, and a proper job-claiming strategy.

## 24. Query FOR Returning 0 Rows

~~~sql
DO $$
DECLARE
    v_job RECORD;
BEGIN
    FOR v_job IN
        SELECT job_id
        FROM pl_loop_lab.jobs
        WHERE status = 'never_exists'
    LOOP
        RAISE NOTICE 'This body will not run';
    END LOOP;

    RAISE NOTICE 'After the loop';
END;
$$;
~~~

With 0 rows, the `FOR` body runs 0 times, and statements after `END LOOP;` still execute.

### 24.1. Using FOUND After FOR

In PL/pgSQL, a `FOR` loop sets `FOUND` upon exiting to indicate whether at least one iteration ran.

~~~sql
DO $$
DECLARE
    v_job RECORD;
BEGIN
    FOR v_job IN
        SELECT job_id
        FROM pl_loop_lab.jobs
        WHERE status = 'pending'
    LOOP
        NULL;
    END LOOP;

    IF FOUND THEN
        RAISE NOTICE 'At least one pending job';
    ELSE
        RAISE NOTICE 'No pending jobs';
    END IF;
END;
$$;
~~~

**Important:** `FOUND` is a special variable updated by several SQL/PL/pgSQL statements. Inspect it right after the loop if you rely on it, before any subsequent DML or `SELECT INTO` overwrites it.

## 25. FOUND Inside vs. Outside a Loop

An easy point of confusion:

- `FOR`/`FOREACH` sets `FOUND` when **exiting the loop**.
- Statements inside the loop body like `UPDATE`, `PERFORM`, or `SELECT INTO` update `FOUND` immediately during that iteration.

Thus `FOUND` observed **inside** a query `FOR` reflects the latest SQL statement run inside the body, not the loop status itself.

For reliable counts, use an explicit variable:

~~~sql
DO $$
DECLARE
    v_job RECORD;
    v_processed INTEGER := 0;
BEGIN
    FOR v_job IN
        SELECT job_id
        FROM pl_loop_lab.jobs
        WHERE status = 'pending'
    LOOP
        v_processed := v_processed + 1;
    END LOOP;

    RAISE NOTICE 'rows visited=%', v_processed;
END;
$$;
~~~

## 26. GET DIAGNOSTICS ROW_COUNT After DML

When running DML inside a loop:

~~~sql
DO $$
DECLARE
    v_affected BIGINT;
BEGIN
    UPDATE pl_loop_lab.jobs
    SET updated_at = statement_timestamp()
    WHERE job_id = -1;

    GET DIAGNOSTICS v_affected = ROW_COUNT;

    RAISE NOTICE 'affected=%', v_affected;
END;
$$;
~~~

For `job_id = -1` in the lab, `v_affected` is 0.

### 26.1. ROW_COUNT vs. FOUND

- `FOUND` is Boolean.
- `ROW_COUNT` is the row count affected by the most recent qualifying SQL statement.
- `ROW_COUNT` must be captured immediately after the statement being measured, before another SQL command alters diagnostics.

Use `GET DIAGNOSTICS` whenever you need exact counts for batch limits or write verification.

## 27. FOR rec IN EXECUTE: Dynamic Queries

Syntax:

~~~sql
FOR record_variable IN
    EXECUTE dynamic_sql
    [ USING value1, value2, ... ]
LOOP
    statements;
END LOOP;
~~~

Read-only example with a fixed table name:

~~~sql
DO $$
DECLARE
    v_job RECORD;
    v_sql TEXT :=
        'SELECT job_id, status
         FROM pl_loop_lab.jobs
         WHERE status = $1
         ORDER BY job_id';
BEGIN
    FOR v_job IN
        EXECUTE v_sql USING 'pending'
    LOOP
        RAISE NOTICE
            'job=% status=%',
            v_job.job_id, v_job.status;
    END LOOP;
END;
$$;
~~~

`USING` passes parameter values safely instead of concatenating user literals directly into SQL.

### 27.1. The $1 Placeholder in Dynamic Queries

Inside dynamic SQL strings, `$1` is a parameter placeholder bound by `USING`. Never confuse it with outer function parameters that happen to have different names.

### 27.2. Dynamic Queries Have Planning Overhead

`EXECUTE` does not reuse PL/pgSQL's static SQL plan cache the same way; it plans the dynamic query at runtime. Use dynamic SQL only when query structure itself genuinely varies.

## 28. Dynamic Identifiers and SQL Injection

If table names are dynamic, never pass them through `USING` as data values expecting them to act as identifiers.

Safe pattern:

~~~sql
CREATE FUNCTION pl_loop_lab.count_status_dynamic(
    p_schema NAME,
    p_table NAME,
    p_status TEXT
)
RETURNS BIGINT
LANGUAGE plpgsql
SECURITY INVOKER
AS $$
DECLARE
    v_sql TEXT;
    v_count BIGINT;
BEGIN
    v_sql := format(
        'SELECT COUNT(*) FROM %I.%I WHERE status = $1',
        p_schema, p_table
    );

    EXECUTE v_sql
    INTO v_count
    USING p_status;

    RETURN v_count;
END;
$$;
~~~

- `%I` quotes identifiers safely.
- `USING` binds data values.
- `SECURITY INVOKER` runs with the caller's privileges per standard rules.
- The query assumes the target table has a `status` column.
- Real applications should **whitelist permitted schemas and tables**, not rely on quoting alone.

Never build `SECURITY DEFINER` dynamic SQL accepting caller-supplied table names without strict authorization and validation.

## 29. Query FOR vs. Cursor FETCH

`FOR rec IN SELECT ... LOOP` iterates over query results without manual cursor management.

When you need step-by-step fetch control, use an explicit cursor:

~~~sql
DO $$
DECLARE
    v_job RECORD;
    cur_jobs CURSOR FOR
        SELECT job_id, status
        FROM pl_loop_lab.jobs
        ORDER BY job_id;
BEGIN
    OPEN cur_jobs;

    LOOP
        FETCH cur_jobs INTO v_job;

        EXIT WHEN NOT FOUND;

        RAISE NOTICE
            'job=% status=%',
            v_job.job_id, v_job.status;
    END LOOP;

    CLOSE cur_jobs;
END;
$$;
~~~

### 29.1. Why FETCH Pairs Naturally with LOOP

- `FETCH` attempts to read the next row.
- `FOUND` indicates whether a row was fetched.
- `EXIT WHEN NOT FOUND` stops cleanly at the end of the cursor.

### 29.2. When to Use an Explicit Cursor?

When you need cursor APIs (`OPEN`/`FETCH`/`MOVE`/`CLOSE`), flexible fetch increments, or interaction with external cursor consumers. For simply iterating through query rows, query `FOR` is shorter and less error-prone.

### 29.3. Cursors and Transactions

Cursors are scoped to transactions by default; transaction-ending commands affect open cursors. Never assume a regular cursor survives `COMMIT` unless explicitly declared holdable with full awareness of its semantics.

## 30. FOREACH: Iterating Over SQL Arrays

Syntax:

~~~sql
FOREACH target [ SLICE n ]
IN ARRAY array_expression
LOOP
    statements;
END LOOP;
~~~

Example:

~~~sql
DO $$
DECLARE
    v_number INTEGER;
BEGIN
    FOREACH v_number IN ARRAY
        ARRAY[10, 20, 30]::INTEGER[]
    LOOP
        RAISE NOTICE 'value=%', v_number;
    END LOOP;
END;
$$;
~~~

Outputs 10, 20, 30.

**`FOREACH` in PL/pgSQL works on SQL arrays**, not directly on JSON arrays. To iterate over a JSONB array, use `jsonb_array_elements` inside a query `FOR` or convert it properly to an SQL array.

## 31. FOREACH with Text Arrays

~~~sql
DO $$
DECLARE
    v_tag TEXT;
BEGIN
    FOREACH v_tag IN ARRAY
        ARRAY['priority', 'gift', 'fragile']::TEXT[]
    LOOP
        RAISE NOTICE 'tag=%', v_tag;
    END LOOP;
END;
$$;
~~~

Use cases:

- Processing lists of IDs or tags passed as SQL arrays.
- Validating elements against complex rules.
- Building formatted strings from multiple items.
- Branching per element.

If you only need to check whether elements satisfy a predicate, SQL expressions with `ANY` or `unnest` are usually simpler than a loop.

## 32. FOREACH with an Array Input Parameter

~~~sql
CREATE FUNCTION pl_loop_lab.sum_array(
    p_numbers INTEGER[]
)
RETURNS BIGINT
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    v_number INTEGER;
    v_total BIGINT := 0;
BEGIN
    FOREACH v_number IN ARRAY
        COALESCE(p_numbers, ARRAY[]::INTEGER[])
    LOOP
        v_total := v_total + COALESCE(v_number, 0);
    END LOOP;

    RETURN v_total;
END;
$$;
~~~

Call:

~~~sql
SELECT pl_loop_lab.sum_array(ARRAY[1, 2, 3]);
SELECT pl_loop_lab.sum_array(ARRAY[1, NULL, 3]);
SELECT pl_loop_lab.sum_array(ARRAY[]::INTEGER[]);
~~~

Results: `6`, `4`, and `0` respectively, under the policy **NULL elements count as 0**.

### 32.1. Handling a NULL SQL Array

In this example, `COALESCE(p_numbers, ARRAY[]::INTEGER[])` converts a NULL SQL array to an empty array. That is an **intentional design choice**, not mandatory behavior for every function.

### 32.2. NULL Elements Inside an SQL Array

An SQL array can contain NULL elements. Writing `v_total := v_total + v_number` without `COALESCE` would turn `v_total` into NULL. Decide explicitly whether to skip NULL elements, treat them as 0, or reject the input.

## 33. FOREACH with SLICE

For multi-dimensional SQL arrays, `SLICE n` yields **subarrays** of dimensionality `n` on each iteration instead of scalar elements.

Two-dimensional array example:

~~~sql
DO $$
DECLARE
    v_row INTEGER[];
BEGIN
    FOREACH v_row SLICE 1 IN ARRAY
        ARRAY[
            [1, 2, 3],
            [4, 5, 6]
        ]::INTEGER[][]
    LOOP
        RAISE NOTICE 'row=%', v_row;
    END LOOP;
END;
$$;
~~~

On each iteration, `v_row` is a 1-D SQL array holding one row of the 2-D array.

### 33.1. SLICE 0 vs. SLICE 1

- Omitting `SLICE` or specifying `SLICE 0`: iterates over scalar elements.
- `SLICE 1`: iterates over 1-D slices.
- The `SLICE` dimension must fit the array's dimensionality and match the target variable's type.

### 33.2. Arrays Must Have Valid Dimensionality

Never use `SLICE 1` on non-array values or mismatched dimensions. PostgreSQL enforces types and shapes; multi-dimensional SQL arrays must be rectangular.

## 34. FOREACH vs. Integer FOR Using Array Indices

You can iterate over an SQL array by index:

~~~sql
DO $$
DECLARE
    v_items INTEGER[] := ARRAY[10, 20, 30];
BEGIN
    FOR i IN
        array_lower(v_items, 1)
        ..
        array_upper(v_items, 1)
    LOOP
        RAISE NOTICE
            'index=% value=%',
            i, v_items[i];
    END LOOP;
END;
$$;
~~~

This works when you need the **index**, not only the value.

However, `array_lower`/`array_upper` return NULL on empty arrays, and passing NULL bounds to an integer range fails rather than executing 0 times. Guard against empty arrays first.

### 34.1. FOREACH Does Not Depend on Lower Bounds

`FOREACH` visits elements in storage order regardless of whether the array starts at index 0, 1, or another lower bound. When you only need values, `FOREACH` is cleaner than managing index bounds manually.

## 35. generate_subscripts: Safer Array Indexing

When you need both indices and values:

~~~sql
SELECT
    i,
    a[i] AS value
FROM (
    SELECT ARRAY[10,20,30]::INTEGER[] AS a
) AS src
CROSS JOIN LATERAL generate_subscripts(
    src.a, 1
) AS s(i)
ORDER BY i;
~~~

`generate_subscripts(array, dimension)` generates valid indices for that dimension and returns 0 rows for an empty array.

In PL/pgSQL:

~~~sql
DO $$
DECLARE
    v_items INTEGER[] := ARRAY[10,20,30];
    v_i INTEGER;
BEGIN
    FOR v_i IN
        SELECT generate_subscripts(v_items, 1)
    LOOP
        RAISE NOTICE
            'index=% value=%',
            v_i, v_items[v_i];
    END LOOP;
END;
$$;
~~~

This uses a query `FOR` over indices rather than `FOREACH` over values.

## 36. FOREACH Does Not Work Directly on JSON Arrays

A JSON array:

~~~sql
'[10,20,30]'::JSONB
~~~

is not an `INTEGER[]`.

Example expanding JSONB into rows and iterating:

~~~sql
DO $$
DECLARE
    v_elem JSONB;
BEGIN
    FOR v_elem IN
        SELECT elem
        FROM jsonb_array_elements(
            '[10,20,30]'::JSONB
        ) AS x(elem)
    LOOP
        RAISE NOTICE 'json element=%', v_elem;
    END LOOP;
END;
$$;
~~~

When you need element positions as well:

~~~sql
SELECT elem, ordinality
FROM jsonb_array_elements(
    '["A","B","C"]'::JSONB
) WITH ORDINALITY AS x(elem, ordinality)
ORDER BY ordinality;
~~~

Never write `FOREACH v IN ARRAY jsonb_value`; JSONB is not an SQL array expression.

## 37. CONTINUE and EXIT Inside FOREACH

~~~sql
DO $$
DECLARE
    v_value INTEGER;
BEGIN
    FOREACH v_value IN ARRAY
        ARRAY[1, 0, 2, -1, 3]
    LOOP
        CONTINUE WHEN v_value = 0;
        EXIT WHEN v_value < 0;

        RAISE NOTICE 'accepted=%', v_value;
    END LOOP;
END;
$$;
~~~

- Value `1`: printed.
- Value `0`: skipped.
- Value `2`: printed.
- Value `-1`: `EXIT`.
- Value `3`: never reached.

This clearly shows the difference between skipping one element and terminating the entire array traversal.

## 38. RETURN Inside a Function Loop

Example finding the first element above a threshold:

~~~sql
CREATE FUNCTION pl_loop_lab.first_above(
    p_numbers INTEGER[],
    p_limit INTEGER
)
RETURNS INTEGER
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    v_number INTEGER;
BEGIN
    IF p_numbers IS NULL THEN
        RETURN NULL;
    END IF;

    FOREACH v_number IN ARRAY p_numbers LOOP
        IF v_number > p_limit THEN
            RETURN v_number;
        END IF;
    END LOOP;

    RETURN NULL;
END;
$$;
~~~

Call:

~~~sql
SELECT pl_loop_lab.first_above(
    ARRAY[2, 5, 9, 3], 6
);
~~~

Result: `9`.

### 38.1. RETURN vs. EXIT

- `RETURN v_number`: returns the value and **exits the function immediately**.
- `EXIT`: exits only the current loop (or labeled loop); the function continues after `END LOOP`.

### 38.2. NULL in Comparisons

`v_number > p_limit` evaluates to NULL when either operand is NULL. Since `IF` only enters `THEN` on `TRUE`, NULL elements do not trigger `RETURN` here.

## 39. RETURN NEXT in Set-Returning Functions

Set-returning functions can emit rows from a loop using `RETURN NEXT`:

~~~sql
CREATE FUNCTION pl_loop_lab.even_numbers(
    p_from INTEGER,
    p_to INTEGER
)
RETURNS SETOF INTEGER
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
    IF p_to - p_from > 10000 THEN
        RAISE EXCEPTION 'Range too large';
    END IF;

    FOR i IN p_from..p_to LOOP
        IF i % 2 = 0 THEN
            RETURN NEXT i;
        END IF;
    END LOOP;

    RETURN;
END;
$$;
~~~

Call:

~~~sql
SELECT *
FROM pl_loop_lab.even_numbers(1, 8)
ORDER BY even_numbers;
~~~

Expected results: 2, 4, 6, 8.

### 39.1. RETURN NEXT Does Not Exit the Loop

After `RETURN NEXT i`, the loop continues and the function can emit more elements. The final `RETURN;` completes the set-returning function.

### 39.2. Check Bounds on Both Ends

The example bounds the difference for illustration. Production implementations must also guard against integer overflow, negative spans, and excessive iteration counts. Never pass untrusted bounds into loops generating millions of rows.

## 40. RETURN QUERY Is Usually Better Than Looping RETURN NEXT

When output rows come directly from a SELECT, PL/pgSQL provides `RETURN QUERY`:

~~~sql
CREATE FUNCTION pl_loop_lab.pending_job_ids(
    p_limit INTEGER
)
RETURNS TABLE(job_id BIGINT)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    IF p_limit < 0 OR p_limit > 1000 THEN
        RAISE EXCEPTION 'Invalid limit %', p_limit;
    END IF;

    RETURN QUERY
    SELECT j.job_id
    FROM pl_loop_lab.jobs AS j
    WHERE j.status = 'pending'
    ORDER BY j.job_id
    LIMIT p_limit;
END;
$$;
~~~

Call:

~~~sql
SELECT *
FROM pl_loop_lab.pending_job_ids(3);
~~~

On the sample dataset, this returns job IDs 1, 2, and 4.

### 40.1. When Is RETURN QUERY Better?

- A single SELECT expresses all output rows.
- No per-row procedural branching is required.
- PostgreSQL can optimize the query as a set.
- Code is shorter and carries less state than a loop.

When each row requires complex procedural logic, `FOR rec IN SELECT ... RETURN NEXT` remains valid; weigh performance and clarity.

## 41. Loops and COUNT(*) Are Not Equivalent in Efficiency

To count pending jobs:

~~~sql
SELECT COUNT(*)
FROM pl_loop_lab.jobs
WHERE status = 'pending';
~~~

is far simpler than:

~~~sql
DO $$
DECLARE
    v_count BIGINT := 0;
    v_job RECORD;
BEGIN
    FOR v_job IN
        SELECT job_id
        FROM pl_loop_lab.jobs
        WHERE status = 'pending'
    LOOP
        v_count := v_count + 1;
    END LOOP;

    RAISE NOTICE 'count=%', v_count;
END;
$$;
~~~

Both yield the same count in a snapshot, but the loop needlessly incurs per-row state updates and engine overhead.

### 41.1. The SQL vs. PL/pgSQL Test

> If you remove the loop and write one `SELECT`, `UPDATE`, `INSERT ... SELECT`, or `DELETE ... WHERE`, does it preserve exact semantics?

If yes, prefer set-based SQL before reaching for a loop.

## 42. Batch Processing: FOR with Row Limits

A legitimate use of loops is processing a bounded batch of tasks with per-task handling.

Example **procedure without internal `COMMIT`** that claims pending jobs:

~~~sql
CREATE PROCEDURE pl_loop_lab.claim_pending_jobs(
    IN p_limit INTEGER
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_job RECORD;
    v_claimed INTEGER := 0;
BEGIN
    IF p_limit IS NULL
       OR p_limit < 1
       OR p_limit > 100
    THEN
        RAISE EXCEPTION 'Invalid limit %', p_limit;
    END IF;

    FOR v_job IN
        SELECT j.job_id
        FROM pl_loop_lab.jobs AS j
        WHERE j.status = 'pending'
        ORDER BY j.job_id
        FOR UPDATE SKIP LOCKED
        LIMIT p_limit
    LOOP
        UPDATE pl_loop_lab.jobs AS j
        SET status = 'processing',
            attempt_count = attempt_count + 1,
            updated_at = statement_timestamp()
        WHERE j.job_id = v_job.job_id
          AND j.status = 'pending';

        IF FOUND THEN
            INSERT INTO pl_loop_lab.job_events (
                job_id, event_type, event_note
            )
            VALUES (
                v_job.job_id,
                'claimed',
                'Claimed by demo procedure'
            );

            v_claimed := v_claimed + 1;
        END IF;
    END LOOP;

    RAISE NOTICE 'claimed=%', v_claimed;
END;
$$;
~~~

### 42.1. Test Inside a Lab Transaction

~~~sql
BEGIN;

CALL pl_loop_lab.claim_pending_jobs(2);

SELECT job_id, status, attempt_count
FROM pl_loop_lab.jobs
ORDER BY job_id;

SELECT job_id, event_type
FROM pl_loop_lab.job_events
ORDER BY event_id;

ROLLBACK;
~~~

On `ROLLBACK`, both the status updates and audit events from this procedure are undone (identity/sequence counters have separate non-transactional semantics and do not rewind).

### 42.2. Meaning of SKIP LOCKED

`FOR UPDATE SKIP LOCKED` skips rows locked by other transactions instead of blocking. It works well for **queue-like workflows** with multiple consumers, but:

- It does not provide a consistent "all pending jobs" report snapshot.
- It skips locked rows even if they have smaller job IDs.
- You still need fairness, retry, and timeout handling.
- Results depend on concurrent transactions.
- It does not guarantee exactly-once side effects outside the database.

### 42.3. Claim Procedure Does Not Self-COMMIT

Here the procedure only runs UPDATE and INSERT; the caller controls the transaction. That fits services wanting to commit the claim atomically alongside other work.

## 43. LIMIT in Query FOR and Duplicate Processing Risk

Without locking:

~~~sql
SELECT job_id
FROM pl_loop_lab.jobs
WHERE status = 'pending'
ORDER BY job_id
LIMIT 5;
~~~

two concurrent workers can observe the exact same jobs and both attempt to process them. A `FOR` loop does not prevent that.

Solutions depending on the use case:

- Lock rows with `FOR UPDATE SKIP LOCKED` inside short transactions.
- Claim atomically with `UPDATE ... WHERE ... RETURNING`.
- Enforce unique/idempotency keys on job outputs.
- Time out and reclaim stalled jobs.
- Protect external side effects with idempotency keys or an outbox pattern.

Never treat sequential looping in **one connection** as guaranteeing sequential execution across **multiple concurrent connections**.

## 44. Replacing Row-by-Row FOR with Set-Based UPDATE

If the goal is simply "mark up to 2 pending jobs as processing" without custom per-row branching, use set-based SQL:

~~~sql
WITH candidates AS (
    SELECT j.job_id
    FROM pl_loop_lab.jobs AS j
    WHERE j.status = 'pending'
    ORDER BY j.job_id
    FOR UPDATE SKIP LOCKED
    LIMIT 2
)
UPDATE pl_loop_lab.jobs AS target
SET status = 'processing',
    attempt_count = target.attempt_count + 1,
    updated_at = statement_timestamp()
FROM candidates AS c
WHERE target.job_id = c.job_id
RETURNING
    target.job_id,
    target.status,
    target.attempt_count;
~~~

This single atomic statement claims jobs cleanly and reduces overhead compared to a PL/pgSQL loop when no per-row logic is needed.

### 44.1. Using Returned Rows for Auditing

In suitable workflows, an `UPDATE ... RETURNING` CTE can feed directly into an `INSERT` within the same statement or transaction. Loops are not always the best glue between DML steps.

### 44.2. Isolation and Transaction Considerations

An atomic SQL statement does not make external non-DB workflows exactly-once. After claiming a job, a worker can crash; you still need retry/reclaim logic and idempotent processing.

## 45. Counting Iterations and Breaking Batches Deliberately

When each iteration performs distinct multi-step work, track an explicit counter:

~~~sql
DO $$
DECLARE
    v_processed INTEGER := 0;
    v_job RECORD;
BEGIN
    FOR v_job IN
        SELECT job_id
        FROM pl_loop_lab.jobs
        WHERE status = 'pending'
        ORDER BY job_id
    LOOP
        EXIT WHEN v_processed >= 3;

        RAISE NOTICE 'would process %', v_job.job_id;
        v_processed := v_processed + 1;
    END LOOP;

    RAISE NOTICE
        'processed=%',
        v_processed;
END;
$$;
~~~

However, the inner SELECT may still materialize or evaluate rows before `EXIT` triggers. When the cap is known upfront, **putting `LIMIT` directly in SQL** reduces work:

~~~sql
SELECT job_id
FROM pl_loop_lab.jobs
WHERE status = 'pending'
ORDER BY job_id
LIMIT 3;
~~~

## 46. WHILE for Multi-Batch Processing

Conceptual pattern:

~~~text
WHILE work remains and cap not exceeded
    |
    +--> Claim up to batch_size jobs
    |
    +--> Check claimed count
    |
    +--> If 0: EXIT
    |
    +--> Process / record results
    |
    +--> Next iteration
~~~

You can use `LOOP ... EXIT WHEN v_count = 0` instead of `WHILE` when the stopping condition is only known **after** running the batch SQL.

### 46.1. Never Poll a Queue Indefinitely Inside One Transaction

A loop repeatedly querying a table while idle causes busy-waiting, holds connections and transactions open, and burns CPU. Schedule polling from the application or worker scheduler using backoff and short transactions.

### 46.2. Do Not Use pg_sleep as a Queue Architecture

`pg_sleep` is fine for tests or small deliberate backoffs, but it holds a backend connection idle while waiting. Never build production queues out of infinite loops calling `pg_sleep` inside a database function.

## 47. Procedures with Per-Iteration COMMIT: Crucial Boundaries

Unlike functions, procedures can control transactions in **valid top-level `CALL` contexts**.

Small syntax demonstration:

~~~sql
CREATE PROCEDURE pl_loop_lab.write_demo_events(
    IN p_batches INTEGER
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_batches IS NULL
       OR p_batches < 1
       OR p_batches > 3
    THEN
        RAISE EXCEPTION
            'Invalid batch count %',
            p_batches;
    END IF;

    FOR batch_no IN 1..p_batches LOOP
        INSERT INTO pl_loop_lab.job_events (
            job_id, event_type, event_note
        )
        VALUES (
            1,
            'demo_commit',
            format('batch %s', batch_no)
        );

        COMMIT;
    END LOOP;
END;
$$;
~~~

Call at **top level**, outside any explicit transaction block:

~~~sql
CALL pl_loop_lab.write_demo_events(2);
~~~

### 47.1. Cannot Be Called Inside a Caller's BEGIN ... COMMIT

~~~sql
-- Illustrating an invalid call context:
BEGIN;

CALL pl_loop_lab.write_demo_events(2);

COMMIT;
~~~

A procedure executing internal `COMMIT` fails when called inside an explicit caller transaction block. In JDBC/Spring, check autocommit and `@Transactional` boundaries.

### 47.2. COMMIT Does Not Undo Earlier Iterations

If batch 1 commits and batch 2 fails, batch 1 stays committed. Design idempotency and checkpoints whenever partial commits are allowed.

### 47.3. Never COMMIT Inside an EXCEPTION Block

A PL/pgSQL block with `EXCEPTION` creates an internal subtransaction; you cannot commit or roll back transactions inside an active exception-protected block. Additional restrictions apply to `SECURITY DEFINER` and procedures with `SET` clauses.

## 48. Functions with Loops Must Never COMMIT

A function can loop and perform DML, but cannot execute transaction-control commands inside its body:

~~~sql
-- DO NOT do this inside CREATE FUNCTION:
-- LOOP
--     UPDATE ...;
--     COMMIT;
-- END LOOP;
~~~

Functions run inside the caller's or statement's transaction. To commit between batches:

- Move orchestration to the application across multiple transactions.
- Or use a top-level procedure permitted to manage transactions, with explicit retry and partial-commit policies.
- Never try to smuggle `COMMIT` into a function via dynamic SQL.

## 49. Exception Handling Inside a Loop

PL/pgSQL supports per-iteration error handling with `BEGIN ... EXCEPTION ... END`.

Intentional per-element handling demo:

~~~sql
DO $$
DECLARE
    v_text TEXT;
    v_integer INTEGER;
BEGIN
    FOREACH v_text IN ARRAY
        ARRAY['10','oops','20']
    LOOP
        BEGIN
            v_integer := v_text::INTEGER;
            RAISE NOTICE 'parsed=%', v_integer;
        EXCEPTION
            WHEN INVALID_TEXT_REPRESENTATION THEN
                RAISE NOTICE
                    'skipped invalid integer: %',
                    v_text;
        END;
    END LOOP;
END;
$$;
~~~

Logical outcome: parses `10`, skips `'oops'`, parses `20`.

### 49.1. Subtransactions Have Overhead

When an `EXCEPTION` block catches an error, database changes inside that block roll back under subtransaction semantics, while PL/pgSQL variables follow separate rules. Entering an exception block for **every row** in a huge batch can incur significant overhead.

### 49.2. Never Swallow All Errors

~~~sql
EXCEPTION WHEN OTHERS THEN
    NULL;
~~~

is an anti-pattern that hides constraint violations, permission errors, deadlocks, and corrupt data. Catch only specific error classes with defined recovery rules, log safe non-sensitive context, and rethrow when unsafe.

## 50. RAISE NOTICE, WARNING, and EXCEPTION

Inside a loop:

~~~sql
RAISE NOTICE 'job=%', v_job_id;
~~~

fits demos or bounded instrumentation.

- `RAISE NOTICE`: informational; does not abort the statement.
- `RAISE WARNING`: warning.
- `RAISE EXCEPTION`: raises an error and aborts normal flow unless caught.

### 50.1. Per-Row Logging Can Be Very Expensive

Over millions of iterations, emitting millions of notices/logs consumes CPU, disk, and client bandwidth. Log per batch or on significant state transitions, and emit aggregated metrics instead of per-row logs in production.

## 51. ASSERT and Loop Invariants

PL/pgSQL supports `ASSERT` in valid contexts for checking development assumptions:

~~~sql
DO $$
DECLARE
    v_counter INTEGER := 3;
BEGIN
    ASSERT v_counter >= 0,
        'Counter should be nonnegative';
END;
$$;
~~~

Whether `ASSERT` executes depends on `plpgsql.check_asserts`.

**Never use `ASSERT` in place of mandatory business validation**, especially since configuration can disable it. Use `IF ... THEN RAISE EXCEPTION` and database constraints for invariants that must always hold.

## 52. Timeouts, statement_timeout, and Resource Safety

A buggy loop can run far too long. PostgreSQL provides `statement_timeout` and related GUCs to bound execution time.

In a lab session:

~~~sql
BEGIN;

SET LOCAL statement_timeout = '5s';

DO $$
DECLARE
    v_count INTEGER := 0;
BEGIN
    WHILE v_count < 1000 LOOP
        v_count := v_count + 1;
    END LOOP;
END;
$$;

ROLLBACK;
~~~

This loop terminates quickly; the timeout acts as a safety net.

### 52.1. Never Treat statement_timeout as a Stopping Algorithm

Every loop must have a clear algorithmic stopping condition. Timeouts abort runaway requests; they do not preserve workflow consistency after partial commits.

### 52.2. Input Bounds Are an Essential Line of Defense

In public functions and procedures, bound:

- Maximum iterations.
- Maximum records processed.
- Maximum array length.
- Expected runtime.
- Nesting depth.
- Retry counts.
- Scope of rows allowed to be modified.

## 53. CONTINUE WHEN with Multiple Conditions

Example skipping rows failing validation:

~~~sql
DO $$
DECLARE
    v_job RECORD;
BEGIN
    FOR v_job IN
        SELECT
            job_id,
            status,
            attempt_count
        FROM pl_loop_lab.jobs
        ORDER BY job_id
    LOOP
        CONTINUE WHEN v_job.status <> 'pending';
        CONTINUE WHEN v_job.attempt_count >= 3;

        RAISE NOTICE
            'eligible job=%',
            v_job.job_id;
    END LOOP;
END;
$$;
~~~

If filtering can be expressed directly in SQL, it is cleaner and faster:

~~~sql
SELECT job_id
FROM pl_loop_lab.jobs
WHERE status = 'pending'
  AND attempt_count < 3
ORDER BY job_id;
~~~

Loops are justified only when **custom per-row procedural logic is needed after filtering**, not simply to duplicate a `WHERE` clause.

## 54. EXIT WHEN with NULL Conditions

`EXIT WHEN boolean_expression` exits only when the expression evaluates to **`TRUE`**. Both `FALSE` and `NULL` keep the loop running.

~~~sql
DO $$
DECLARE
    v_flag BOOLEAN := NULL;
    v_attempt INTEGER := 0;
BEGIN
    LOOP
        v_attempt := v_attempt + 1;

        EXIT WHEN v_flag;
        EXIT WHEN v_attempt >= 3;
    END LOOP;

    RAISE NOTICE
        'attempts=%',
        v_attempt;
END;
$$;
~~~

The NULL `v_flag` does not trigger `EXIT`; the 3-attempt guard stops the loop.

### 54.1. Express NULL Semantics Explicitly

To exit when `NULL` or `FALSE`:

~~~sql
EXIT WHEN v_flag IS NOT TRUE;
~~~

To exit only when explicitly `FALSE`, not `NULL`:

~~~sql
EXIT WHEN v_flag IS FALSE;
~~~

`IS TRUE`/`IS FALSE`/`IS NOT TRUE` are much clearer whenever Booleans can be NULL.

## 55. Loop Counters and Avoiding Overflow

`INTEGER` has a finite range. For loops that could accumulate very large counts, use `BIGINT` for counters or enforce tight iteration caps.

~~~sql
DECLARE
    v_processed BIGINT := 0;
~~~

Unbounded increments can overflow and fail the statement. In production batches, enforce practical limits far below `BIGINT` bounds.

### 55.1. Do Not Use Sequences as Ordinary Loop Counters

`nextval` mutates sequence state outside transactional rollback. For counting iterations inside a procedure, always use a PL/pgSQL variable.

## 56. FOREACH with Multi-Dimensional Arrays and NULLs

A multi-dimensional SQL array:

~~~sql
DO $$
DECLARE
    v_value INTEGER;
BEGIN
    FOREACH v_value IN ARRAY
        ARRAY[
            [1, NULL],
            [3, 4]
        ]::INTEGER[][]
    LOOP
        IF v_value IS NULL THEN
            RAISE NOTICE 'null element';
        ELSE
            RAISE NOTICE 'value=%', v_value;
        END IF;
    END LOOP;
END;
$$;
~~~

Without `SLICE`, `FOREACH` visits **scalar elements** in PostgreSQL's array traversal order.

### 56.1. SLICE 1 for Sub-Rows

~~~sql
DO $$
DECLARE
    v_slice INTEGER[];
BEGIN
    FOREACH v_slice SLICE 1 IN ARRAY
        ARRAY[
            [1, 2],
            [3, 4]
        ]::INTEGER[][]
    LOOP
        RAISE NOTICE 'slice=%', v_slice;
    END LOOP;
END;
$$;
~~~

`v_slice` is `INTEGER[]`; passing a scalar `INTEGER` target with `SLICE 1` causes a type mismatch.

## 57. Looping Over Arrays vs. ANY/ALL

If you only need to check whether a value exists in an array:

~~~sql
SELECT
    20 = ANY(ARRAY[10,20,30]) AS contains_20;
~~~

If you only need to check whether every element is positive:

~~~sql
SELECT
    0 < ALL(ARRAY[1,2,3]) AS all_positive;
~~~

These expressions are far simpler than `FOREACH` + Boolean flag + `EXIT`.

### 57.1. NULL in ANY/ALL

When an array contains NULL, `ANY`/`ALL` can evaluate to NULL depending on the operator and remaining elements. Know SQL three-valued logic rather than assuming unknown means FALSE.

### 57.2. When FOREACH Remains Useful

When each element requires complex transformation or order-dependent state accumulation, `FOREACH` can be clearer. Still, consider `unnest`, `array_agg`, and SQL array functions before writing a loop.

## 58. FOR with generate_series

To simply generate a range of data, SQL alone suffices:

~~~sql
SELECT g AS number
FROM generate_series(1, 10) AS g
ORDER BY g;
~~~

with no loop needed.

When you need to iterate over rows produced by `generate_series`:

~~~sql
DO $$
DECLARE
    v_num INTEGER;
BEGIN
    FOR v_num IN
        SELECT g
        FROM generate_series(1, 5) AS g
    LOOP
        RAISE NOTICE 'n=%', v_num;
    END LOOP;
END;
$$;
~~~

### 58.1. How Does This Differ from Integer FOR?

- `FOR i IN 1..5` is a PL/pgSQL integer range loop.
- `FOR i IN SELECT g FROM generate_series(...)` is a query `FOR` loop.
- `generate_series` composes seamlessly with set-based SQL, JOINs, and `INSERT ... SELECT`.

## 59. FOR with Timestamp Ranges

Integer `FOR` only accepts integer `lower..upper` ranges. To iterate by day, use a query `FOR` over `generate_series`:

~~~sql
DO $$
DECLARE
    v_day DATE;
BEGIN
    FOR v_day IN
        SELECT d::DATE
        FROM generate_series(
            DATE '2026-11-01',
            DATE '2026-11-05',
            INTERVAL '1 day'
        ) AS d
    LOOP
        RAISE NOTICE 'day=%', v_day;
    END LOOP;
END;
$$;
~~~

For timestamps and time zones, account for DST and calendar rules when scheduling logic matters. The example uses `DATE` and fixed bounds for clarity, not to solve every calendar edge case.

## 60. Loops in Trigger Functions

A trigger function can contain loops, though in many cases set-based SQL is preferable to row-by-row loops.

For instance, a row-level trigger already runs once per affected row during a bulk import. If that trigger also loops over many rows internally, total work explodes.

### 60.1. Guard Against Unintended Recursion

A trigger updating the very table that fired it can fire itself again. Combining loops with trigger recursion risks runaway chains.

Consider:

- Statement-level triggers and transition tables where appropriate.
- Guarding updates to avoid self-recursion.
- Keeping trigger logic minimal.
- Benchmarking bulk DML performance.

Never turn triggers into unbounded process engines.

## 61. Loops and Transaction Isolation

Query `FOR` reads data under your transaction's isolation and snapshot semantics. When another transaction modifies rows, visibility depends on:

- `READ COMMITTED` / `REPEATABLE READ` / `SERIALIZABLE`.
- Per-statement snapshots.
- Row-level locks.
- `FOR UPDATE` and lock clauses.
- Subsequent SQL statements inside the routine.
- Transaction boundaries managed by caller/procedure.

### 61.1. Never Assume a SELECT Loop Sees Live Concurrent Inserts

A query `FOR` iterates over one `SELECT`'s result set; it is not a streaming subscription that automatically picks up rows inserted by other transactions mid-loop.

To process continuously arriving tasks, structure polling/claiming across separate transactions or statements.

### 61.2. Loops Alone Do Not Guarantee Exactly-Once Execution

When transactions can roll back or workers can crash, job idempotency and state machines—not loop syntax—govern safe retries.

## 62. Deadlocks When Multiple Loops Update Rows in Opposite Orders

Two workers updating two rows in opposite orders:

~~~text
Worker A: locks job 1 -> waits for job 2
Worker B: locks job 2 -> waits for job 1
~~~

can trigger a deadlock.

Mitigations:

- Enforce consistent lock ordering, such as `ORDER BY job_id` when claiming.
- Keep transactions short.
- Avoid locking multiple tables in inconsistent orders.
- Retry transactions on deadlock per a bounded retry policy.
- Use set-based DML and clean locking strategies.

An `ORDER BY` on `FOR` alone cannot eliminate all deadlocks; inspect actual plans, lock acquisition, and full workflows.

## 63. Performance: Row-by-Row Loop vs. Set-Based SQL

Example incrementing `attempt_count` on all pending jobs:

**Row-by-row PL/pgSQL:**

~~~sql
DO $$
DECLARE
    v_job RECORD;
BEGIN
    FOR v_job IN
        SELECT job_id
        FROM pl_loop_lab.jobs
        WHERE status = 'pending'
    LOOP
        UPDATE pl_loop_lab.jobs
        SET attempt_count = attempt_count + 1
        WHERE job_id = v_job.job_id;
    END LOOP;
END;
$$;
~~~

**Set-based SQL:**

~~~sql
UPDATE pl_loop_lab.jobs
SET attempt_count = attempt_count + 1
WHERE status = 'pending';
~~~

Both examples **modify real data**; do not run them back-to-back expecting identical starting state.

### 63.1. Why Is Set-Based SQL Usually Better?

- Fewer SQL statement executions.
- The planner optimizes across the entire row set.
- Eliminates per-row context switching between PL/pgSQL and the SQL engine.
- Typically shortens lock durations and avoids redundant work when designed well.
- Shorter, easier-to-audit code.

Still, when each row requires multi-step branching or per-row side effects, a loop can be clearer. Benchmark on representative workloads.

## 64. Metrics to Measure When Using Loops

Use:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT job_id
FROM pl_loop_lab.jobs
WHERE status = 'pending'
ORDER BY job_id;
~~~

to inspect the driving query.

For multi-statement procedures or functions, an outer `EXPLAIN` does not automatically show internal query plans. Use instrumentation, tracing, `pg_stat_statements`, and appropriate logging.

Key metrics:

- Iteration count.
- Rows read/written.
- Per-batch and end-to-end latency.
- CPU, I/O, and WAL volume.
- Lock waits and deadlocks.
- Rows skipped due to locks or validation.
- Retry counts.
- Input or constraint errors.
- Memory and temp I/O.
- Transaction duration.

### 64.1. Never Benchmark Only Once

Caching, concurrency, and data skew introduce noise. Compare set-based SQL against loops on the same controlled dataset and workload rather than trusting a single run.

## 65. N+1 Query Risk Inside FOR Loops

Fetching N jobs and running a separate `SELECT` inside every iteration:

~~~sql
FOR v_job IN
    SELECT job_id
    FROM pl_loop_lab.jobs
LOOP
    SELECT COUNT(*)
    INTO v_count
    FROM pl_loop_lab.job_events
    WHERE job_id = v_job.job_id;
END LOOP;
~~~

runs one outer query plus N inner queries. At scale, overhead becomes severe.

Set-based SQL alternative:

~~~sql
SELECT
    j.job_id,
    COUNT(e.event_id) AS event_count
FROM pl_loop_lab.jobs AS j
LEFT JOIN pl_loop_lab.job_events AS e
    ON e.job_id = j.job_id
GROUP BY j.job_id
ORDER BY j.job_id;
~~~

You may also want an index:

~~~sql
CREATE INDEX idx_job_events_job_id
ON pl_loop_lab.job_events(job_id);
~~~

This is a lab suggestion; indexes add write and storage cost, so verify with real data before adding them.

## 66. Verifying Correctness When Exiting Early with EXIT

Suppose a loop processes at most 3 jobs while the query yields 5. After `EXIT`, the last 2 jobs are untouched. That may be an intentional batch limit—or a bug if callers believe "all" jobs were processed.

Name procedures, metrics, and logs accurately:

~~~text
claim_up_to_3_jobs  -> explicit cap
process_all_jobs    -> must prove complete processing
~~~

For batch APIs, consider returning:

- Number of claimed/processed rows.
- Whether more pending jobs likely remain.
- Batch or cursor identifier.
- Success or error status.

Never report `"SUCCESS processed all"` merely because a `FOR` loop stopped via `EXIT`.

## 67. A Loop Can Be Aborted Mid-Execution

A query, function, or procedure can terminate mid-run due to:

- Client cancellation.
- `statement_timeout`.
- Dropped connection.
- Server shutdown or failover.
- Constraint or deadlock errors.

If the entire loop runs inside one uncommitted transaction, uncommitted DML rolls back when the transaction aborts.

If a procedure already committed earlier batches, those batches remain persisted after a failure. Checkpointing, idempotency, and restartability belong in batch design—not just loop syntax.

## 68. Debugging Loops

When a loop runs the wrong number of times, inspect:

1. Initial variable values.
2. Variable types and potential NULLs.
3. Where loop control variables are modified.
4. `EXIT WHEN` / `WHILE` conditions.
5. `FOR ... .. ...` bounds and `BY` step.
6. Integer `FOR` variable shadowing/scope.
7. Whether labeled `EXIT`/`CONTINUE` targets the right loop.
8. Whether `CONTINUE` skips mandatory counter increments.
9. Whether the driving `FOR` query has the right `WHERE`/`ORDER BY`/`LIMIT`.
10. Whether an inner SQL statement overwrote `FOUND`.
11. Concurrent modifications or `SKIP LOCKED` skips.
12. Swallowed exceptions inside the loop.

### 68.1. Bounded Instrumentation

~~~sql
RAISE NOTICE
    'iteration=% processed=%',
    v_iteration, v_processed;
~~~

Avoid per-row logging in production. Log every 100 or 1,000 iterations or per batch, omitting sensitive inputs and PII.

## 69. Common Syntax Mistakes

### 69.1. Missing END LOOP

~~~sql
FOR i IN 1..3 LOOP
    RAISE NOTICE '%', i;
-- Missing END LOOP;
~~~

Every loop must close with `END LOOP;`.

### 69.2. Using break Instead of EXIT

PL/pgSQL uses `EXIT`, not `break`.

### 69.3. Misplaced CONTINUE

`CONTINUE` is valid only inside loops, not as a general jump statement.

### 69.4. Writing Java/Python FOR Syntax

Never write `for (i=0; i<5; i++)` or `for i in range(5)`. PL/pgSQL uses `FOR i IN 1..5 LOOP`.

### 69.5. Calling FOREACH on jsonb

SQL arrays and JSONB arrays are distinct types.

### 69.6. REVERSE with Ascending Bounds

`REVERSE 1..5` does not count down from 5 to 1; write `REVERSE 5..1`.

### 69.7. BY 0 or Negative Step

Integer `FOR` steps must be positive; use `REVERSE` to count downward.

### 69.8. Missing RECORD Declaration for Query FOR

Unlike integer `FOR`, query `FOR` targets require a declared record/row variable or compatible target list.

### 69.9. Concatenating Raw Input into Dynamic Queries

Creates SQL injection risks; use `format('%I', ...)` for identifiers and `USING` for values.

### 69.10. Missing Semicolon After END LOOP

Causes syntax errors on the following statement.

## 70. Common Logic Mistakes

### 70.1. LOOP Without EXIT

Causes infinite loops and ties up backend workers.

### 70.2. WHILE Without Updating Condition Variables

For example `WHILE i < 10` without updating `i` runs forever unless another exit condition triggers.

### 70.3. EXIT WHEN Evaluating to NULL

Only `TRUE` exits; handle NULL explicitly.

### 70.4. Using EXIT Instead of CONTINUE

Aborts all remaining items instead of skipping just one item.

### 70.5. Calling CONTINUE Before Incrementing Counters

Skips the update and can prevent reaching the stopping condition.

### 70.6. Using RETURN to Exit a Loop When Work Remains Afterward

`RETURN` exits the whole function, skipping code after the loop.

### 70.7. Confusing UPDATE's FOUND with FOR's FOUND

Capture diagnostics immediately or use separate variables.

### 70.8. Assuming Query FOR Has Deterministic Natural Order

Add `ORDER BY` whenever order matters.

### 70.9. Assuming Looping Over Pending Rows Prevents Race Conditions

You still need transactions, locks, or atomic claims.

### 70.10. Looping N UPDATEs Instead of One Set-Based UPDATE

Increases overhead and lock contention.

### 70.11. Ignoring SQL NULL Element Semantics in FOREACH

A NULL element turns uncoalesced sums or Boolean checks into NULL.

### 70.12. Looping Empty Arrays with array_lower/upper Unchecked

Bounds become NULL on empty arrays; use `FOREACH`, `generate_subscripts`, or explicit emptiness checks.

### 70.13. COMMIT Inside a Function

Disallowed; manage transactions according to routine type.

### 70.14. COMMIT Inside CALL Within an Explicit Transaction

Procedure transaction control has strict boundaries and cannot commit inside caller-started transactions.

### 70.15. Catching WHEN OTHERS and Ignoring Errors

Hides bugs and leaves hard-to-debug states.

### 70.16. Emitting Millions of RAISE NOTICE Calls

Inflates CPU and log volume.

### 70.17. Unbounded p_count / p_array Inputs

Can cause excessive load or unintended denial of service.

### 70.18. Using SKIP LOCKED While Claiming "Scanned All Rows"

Locked rows are skipped.

### 70.19. Lacking Idempotency After Partial Commits

Retries can duplicate work or external side effects.

### 70.20. Loops Inside Triggers Infinitely Re-Firing the Trigger

Design guards against trigger self-recursion.

## 71. Loop Structure Selection Guide

| Need | Suitable Construct |
|---|---|
| Loop until a mid-iteration condition holds | `LOOP` + `EXIT WHEN` |
| Condition known at the start of every iteration | `WHILE` |
| Loop from 1 to 10 | `FOR i IN 1..10` |
| Count down 10, 8, 6, 4, 2 | `FOR i IN REVERSE 10..1 BY 2` |
| Iterate rows from a static SQL query | `FOR rec IN SELECT` |
| Dynamic table/column names in query | `FOR rec IN EXECUTE ... USING` |
| Iterate an SQL array | `FOREACH variable IN ARRAY` |
| Iterate 1-D sub-rows of a 2-D SQL array | `FOREACH slice SLICE 1 IN ARRAY` |
| Iterate a JSONB array | `FOR rec IN SELECT jsonb_array_elements(...)` |
| Skip current item | `CONTINUE` |
| Exit current loop | `EXIT` |
| Exit outer loop from inner loop | `EXIT outer_label` |
| Advance outer loop to next iteration | `CONTINUE outer_label` |
| Exit function returning a scalar | `RETURN expression` |
| Emit multiple rows from a function | `RETURN NEXT` / `RETURN QUERY` |
| Simply count, aggregate, or bulk-update | **Set-based SQL** before writing a loop |

## 72. Tips for Maintainable Loops

- Use `p_` prefixes for parameters, `v_` for state variables, and clear record names.
- Give each loop **one clear purpose**.
- Keep stopping conditions close to the operations they guard.
- Enforce input and iteration limits whenever execution could run long.
- Use labels when nesting two or more loops with cross-level `EXIT`/`CONTINUE`.
- When array indices are needed, use `generate_subscripts` or `WITH ORDINALITY`.
- When query order matters, specify `ORDER BY`.
- Use `GET DIAGNOSTICS ROW_COUNT` for DML row counts.
- Whenever DML runs, identify the transaction owner and rollback semantics.
- Protect concurrent workflows with constraints, locks, and idempotency.
- Favor set-based SQL over loops for aggregations or bulk updates.
- Never fire per-row external side effects without compensation or retry safeguards.

## 73. Practice Exercises

### Exercise 1 — Basic LOOP

Write a `DO` block using `LOOP` to print numbers 1 through 5.

**Hint:** counter variable, increment each pass, `EXIT WHEN counter >= 5`.

### Exercise 2 — Top-Checked Exit Condition

Why does checking `EXIT` at the top of `LOOP` differ from checking at the bottom when the initial state already meets the threshold?

**Hint:** bottom-checking runs the body at least once.

### Exercise 3 — Infinite Loop

What risks arise from a `LOOP` with no `EXIT` or `RETURN`?

**Hint:** CPU, locks, timeouts, and log volume.

### Exercise 4 — WHILE

Write a `WHILE` loop printing even numbers from 2 to 10.

**Hint:** start at 2 and add 2.

### Exercise 5 — WHILE Initially FALSE

How many iterations does `WHILE 10 < 5 LOOP` execute?

**Hint:** 0.

### Exercise 6 — Boolean NULL

Does `WHILE NULL LOOP` execute its body?

**Hint:** no; only `TRUE` continues.

### Exercise 7 — Integer FOR

Write a `FOR` loop from 1 to 10.

**Hint:** `FOR i IN 1..10 LOOP`.

### Exercise 8 — Reverse FOR

Print 5, 4, 3, 2, 1.

**Hint:** `FOR i IN REVERSE 5..1 LOOP`.

### Exercise 9 — BY

Print 1, 4, 7, 10.

**Hint:** `FOR i IN 1..10 BY 3 LOOP`.

### Exercise 10 — Bounds Evaluated Once

If an upper bound in `FOR` is a variable modified inside the loop body, does the iteration count change?

**Hint:** no; integer `FOR` evaluates bounds once upon entering the loop.

### Exercise 11 — Scope

Set `i := 100` outside `FOR`, then run `FOR i IN 1..3`. What is the outer `i` afterward?

**Hint:** 100.

### Exercise 12 — CONTINUE

Print only odd numbers in `1..9`.

**Hint:** `CONTINUE WHEN i % 2 = 0`.

### Exercise 13 — EXIT

Print 1..4 then exit `FOR 1..10`.

**Hint:** `EXIT WHEN i > 4`.

### Exercise 14 — RETURN vs. EXIT

If summary statistics must still be returned after `END LOOP`, should you use `EXIT` or `RETURN` inside the loop?

**Hint:** `EXIT`.

### Exercise 15 — Outer Label

Exit two nested loops when `i=2` and `j=2`.

**Hint:** `<<outer_loop>>` and `EXIT outer_loop WHEN ...`.

### Exercise 16 — Continue Outer

Skip all remaining items for the current customer and advance to the next customer.

**Hint:** `CONTINUE customer_loop`.

### Exercise 17 — Query FOR

Iterate over `job_id` of pending jobs in the lab table.

**Hint:** `FOR r IN SELECT ... LOOP`.

### Exercise 18 — Record

Why is a `RECORD` or row variable needed in query `FOR`?

**Hint:** to hold the row structure returned by the `SELECT`.

### Exercise 19 — %ROWTYPE

Declare a variable matching a full row of `pl_loop_lab.jobs`.

**Hint:** `v_job pl_loop_lab.jobs%ROWTYPE;`.

### Exercise 20 — ORDER BY

Is a query `FOR` guaranteed to read jobs in `job_id` order if the `SELECT` lacks `ORDER BY`?

**Hint:** no.

### Exercise 21 — Empty Query

If a query `FOR` returns 0 rows, how many times does the loop body execute?

**Hint:** 0.

### Exercise 22 — FOUND

After `FOR`, what indicates whether the loop ran at least one iteration?

**Hint:** `FOUND`, read immediately before another SQL statement overwrites it.

### Exercise 23 — ROW_COUNT

Get the number of rows just updated inside a procedure.

**Hint:** `GET DIAGNOSTICS v_count = ROW_COUNT`.

### Exercise 24 — EXECUTE USING

Why use `USING` instead of concatenating text values into dynamic SQL?

**Hint:** parameter binding and safety.

### Exercise 25 — Dynamic Identifier

When constructing a table name from controlled trusted input, what should you use?

**Hint:** a whitelist and `format('%I', identifier)`.

### Exercise 26 — Cursor

When fetching a cursor until exhausted, what stopping condition pairs with `FETCH`?

**Hint:** `EXIT WHEN NOT FOUND`.

### Exercise 27 — FOREACH

Print each element of `ARRAY[10,20,30]`.

**Hint:** `FOREACH v IN ARRAY ... LOOP`.

### Exercise 28 — NULL Elements

What happens when summing array elements containing NULL without `COALESCE`?

**Hint:** the sum becomes NULL.

### Exercise 29 — SLICE 1

Iterate over each 1-D sub-array inside a 2-D SQL array.

**Hint:** `FOREACH v_slice SLICE 1 IN ARRAY ...`.

### Exercise 30 — SQL Array vs. JSON Array

Can `FOREACH` iterate directly over `'[1,2]'::jsonb`?

**Hint:** no; query with `jsonb_array_elements` or convert types appropriately.

### Exercise 31 — generate_subscripts

Safely retrieve SQL array indices even when the array is empty.

**Hint:** `generate_subscripts(array, 1)`.

### Exercise 32 — RETURN NEXT

Does `RETURN NEXT` terminate the loop?

**Hint:** no; it appends an item to the set-returning result.

### Exercise 33 — RETURN QUERY

When returning all pending jobs from a `SELECT`, should you loop `RETURN NEXT` per row?

**Hint:** consider `RETURN QUERY` / set-based SQL.

### Exercise 34 — Batch LIMIT

If you only need 5 jobs, is it better to `EXIT` after 5 rows or put `LIMIT 5` in SQL?

**Hint:** `LIMIT` usually reduces source query work.

### Exercise 35 — Concurrency

What happens if two workers query pending jobs without locking?

**Hint:** duplicate claims / race conditions.

### Exercise 36 — SKIP LOCKED

Does `SKIP LOCKED` guarantee scanning every pending job?

**Hint:** no; locked rows are skipped.

### Exercise 37 — Set-Based UPDATE

Write a single `UPDATE` incrementing `attempt_count` for all pending jobs instead of looping.

**Hint:** `UPDATE ... SET attempt_count=attempt_count+1 WHERE status='pending'`.

### Exercise 38 — Procedure COMMIT

Can a procedure with `COMMIT` inside a loop be called inside an explicit `BEGIN ... COMMIT` block?

**Hint:** transaction control is restricted and will raise an error.

### Exercise 39 — Exception

If one element fails casting to `INTEGER`, which block lets you skip it per policy?

**Hint:** `BEGIN ... EXCEPTION WHEN INVALID_TEXT_REPRESENTATION ... END`.

### Exercise 40 — Never Swallow Errors

Why is `EXCEPTION WHEN OTHERS THEN NULL` dangerous?

**Hint:** masks constraint, permission, and data errors.

### Exercise 41 — Timeout

Does `statement_timeout` replace algorithmic stopping conditions?

**Hint:** no, it is only a safeguard.

### Exercise 42 — Boolean NULL

How do you write `EXIT` when a Boolean is either `FALSE` **or `NULL`**?

**Hint:** `EXIT WHEN v_flag IS NOT TRUE`.

### Exercise 43 — COUNT(*) vs. Loop

To count pending jobs, choose `COUNT(*)` or a row-by-row `FOR` loop?

**Hint:** `COUNT(*)` when no per-row logic is needed.

### Exercise 44 — N+1

What is the drawback of looping `FOR` each job and running `COUNT` on `job_events` per iteration?

**Hint:** N+1 internal queries; replace with `JOIN`/`GROUP BY`.

### Exercise 45 — Retry After Partial Commits

Why does a batch procedure that commits each iteration need idempotency keys or checkpoints?

**Hint:** earlier batches do not roll back if a later batch fails.

## 74. Frequently Asked Questions

### What is the biggest difference between LOOP and WHILE?

`LOOP` has no header condition and requires `EXIT`/`RETURN`/error to stop. `WHILE` checks a condition before every iteration and runs only when `TRUE`.

### Does integer FOR require declaring variable i?

Not necessarily. PostgreSQL automatically creates an integer loop variable scoped to the integer `FOR` loop. Query `FOR`, however, requires a declared target row/record or variable list.

### Does FOR i IN 1..5 include 5?

Yes. Ranges are inclusive of both endpoints when direction and step permit.

### Can I count down using BY -1?

No. Use `REVERSE` with a positive step, e.g. `FOR i IN REVERSE 5..1 LOOP`.

### Do integer FOR bounds re-evaluate on each iteration?

No; bound and step expressions are evaluated once on loop entry. Use `WHILE` when evaluating state that changes mid-loop.

### Does CONTINUE exit the loop?

No. It skips the rest of the current iteration and starts the next one.

### Can one statement exit two nested loops?

Yes. Use a label and `EXIT outer_loop`.

### Does FOUND preserve FOR's status if an UPDATE runs inside the loop?

`FOUND` gets overwritten by SQL statements inside the body. `FOR`'s status is set upon exiting the loop; read it right after `END LOOP` or maintain a separate counter.

### Can FOREACH iterate directly over a JSONB array?

No. `FOREACH ... IN ARRAY` is for SQL arrays. For JSONB, use `jsonb_array_elements` inside a query `FOR` or cast/convert appropriately.

### What does FOREACH SLICE 1 mean?

Each iteration receives a 1-D SQL subarray from a multi-dimensional SQL array rather than a scalar element.

### Is a loop faster than a single UPDATE?

Not by default. For straightforward bulk updates, set-based SQL has much lower overhead. Loops make sense when per-row control flow is genuinely needed.

### Can procedures COMMIT each iteration while functions cannot?

Yes, in **valid PostgreSQL `CALL` contexts**. Procedures with `COMMIT` cannot be called arbitrarily inside explicit transactions or certain restricted contexts.

### Does FOR UPDATE SKIP LOCKED guarantee exactly-once processing?

No. It coordinates queue-like row claiming across concurrent workers, while retries, crashes, external side effects, and idempotency still require dedicated design.

### If an error happens on one iteration, can the next iteration continue?

You can catch expected exceptions with a `BEGIN ... EXCEPTION ... END` block, keeping subtransaction semantics and overhead in mind; never swallow all errors blindly.

### Should production loops log every iteration with RAISE NOTICE?

Usually no. Measure batch counts, latency, and errors, and log only significant events to avoid inflating CPU and log volume.

## 75. Summary

Key PL/pgSQL constructs to remember:

~~~sql
-- General loop:
LOOP
    ...
    EXIT WHEN condition;
END LOOP;

-- Pre-checked condition loop:
WHILE condition LOOP
    ...
END LOOP;

-- Integer range loop:
FOR i IN 1..10 BY 2 LOOP
    ...
END LOOP;

-- Descending integer loop:
FOR i IN REVERSE 10..1 BY 2 LOOP
    ...
END LOOP;

-- Query loop:
FOR rec IN SELECT ... LOOP
    ...
END LOOP;

-- Dynamic SQL loop:
FOR rec IN EXECUTE sql_text USING value LOOP
    ...
END LOOP;

-- SQL array loop:
FOREACH element IN ARRAY some_sql_array LOOP
    ...
END LOOP;

-- Array slice loop:
FOREACH slice SLICE 1 IN ARRAY multidim_array LOOP
    ...
END LOOP;

-- Skip one iteration:
CONTINUE WHEN skip_condition;

-- Exit one loop:
EXIT WHEN stop_condition;

-- Exit outer loop:
EXIT outer_loop;

-- Advance outer loop:
CONTINUE outer_loop;
~~~

Practical principles:

1. **`LOOP`** is flexible, but always requires an explicit stopping condition.
2. **`WHILE`** fits when the continuation condition is checked before each iteration.
3. **Integer `FOR`** iterates bounded ranges, supporting `REVERSE` and positive `BY`; bounds are evaluated once at entry.
4. **Query `FOR`** iterates SQL rows using `RECORD`, `%ROWTYPE`, or target lists, with `ORDER BY` when order matters.
5. **`FOR EXECUTE`** supports dynamic SQL; use `USING` for values and `format('%I')`/whitelists for identifiers.
6. **`FOREACH`** is for SQL arrays; for JSONB arrays use `jsonb_array_elements`—never confuse the two.
7. **`WITH ORDINALITY` / `generate_subscripts`** help when element positions are needed.
8. **`CONTINUE`** skips an iteration, **`EXIT`** exits a loop, and **`RETURN`** exits the function/routine per its contract; never confuse them.
9. Labels `<<outer_loop>>` make nested loop control explicit.
10. `FOUND` and `ROW_COUNT` observe outcomes—know which statements update them.
11. For job queues, **`FOR UPDATE SKIP LOCKED`** helps coordinate concurrent claiming without guaranteeing exactly-once effects by itself.
12. **Functions must never `COMMIT`**, and procedures may `COMMIT` only in valid `CALL` contexts; transaction boundaries govern atomicity and retries.
13. Catch errors selectively; `EXCEPTION` introduces subtransaction semantics and overhead.
14. Bound iteration counts, array sizes, batch sizes, retries, logs, and execution duration.
15. Whenever the task is simply aggregating, filtering, or bulk-updating rows, **prefer set-based SQL** over row-by-row loops.

Selection diagram:

~~~text
Are you processing a dataset?
                  |
                  v
Can one SQL SELECT / UPDATE / INSERT / DELETE
express the entire logic?
        /                         \
       Yes                         No
       |                            |
  Use set-based SQL          What are you iterating over?
                                  |
                   +--------------+--------------+
                   |              |              |
             Integer range   Query result    SQL array
                   |              |              |
              Integer FOR     FOR rec IN      FOREACH
                                   SELECT
                                      |
                       Need dynamic stopping condition?
                                   |
                              LOOP / WHILE
                                   |
                       EXIT / CONTINUE / labels
                                   |
                        Guard transactions, errors,
                        concurrency, and resources
~~~

The true value of PL/pgSQL loops is **expressing control flow when set-based SQL is insufficient or unclear**. Using `LOOP`, `WHILE`, `FOR`, `FOREACH`, `EXIT`, and `CONTINUE` properly makes code cleaner and more accurate; reaching for loops merely out of row-by-row programming habit forfeits PostgreSQL's greatest strength in set-based relational processing.
