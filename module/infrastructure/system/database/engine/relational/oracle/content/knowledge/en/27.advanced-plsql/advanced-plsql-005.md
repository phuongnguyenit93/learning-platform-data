# Set-Based SQL vs. Loops and Bulk Processing

> **Topic:** Database Engine Relational Oracle  
> **Chapter:** Advanced PL/SQL  
> **Objective:** Know how to choose between set-based SQL, PL/SQL loops, and bulk processing; understand context-switching overhead between the PL/SQL engine and the SQL engine; use BULK COLLECT to fetch multiple rows per call and FORALL to send batched DML; handle dense/sparse collections, partial errors, affected row counts, and transaction boundaries; measure performance and choose an appropriate batch size.

## 1. Why Distinguish Set-Based Processing from Row-by-Row Processing?

A business requirement can be expressed in two ways:

- Update the salary of all employees in department 10 by 5%.
- Read each employee in department 10, compute the new salary in PL/SQL, and UPDATE each row one by one.

Both approaches can produce the same result, but execution differs. Oracle SQL is designed to process sets of rows in a single statement. When you write a PL/SQL loop that executes a SQL statement for each row, the program can incur a large number of control switches between the PL/SQL engine and the SQL engine.

Set-based processing example:

~~~sql
UPDATE employees
SET salary = salary * 1.05
WHERE department_id = 10;
~~~

Row-by-row processing example:

~~~sql
BEGIN
    FOR r IN (
        SELECT employee_id, salary
        FROM employees
        WHERE department_id = 10
    ) LOOP
        UPDATE employees
        SET salary = r.salary * 1.05
        WHERE employee_id = r.employee_id;
    END LOOP;
END;
/
~~~

The first UPDATE lets the SQL engine process the entire set of rows. The second loop fetches each row into PL/SQL and sends a separate UPDATE for every row.

When the row count is large, the difference in SQL calls can be substantial. Therefore, when a transformation can be expressed in a single SQL statement, start with set-based SQL. Only move to loops or bulk processing when business rules genuinely require PL/SQL logic or controlled batch chunking.

## 2. The SQL Engine and the PL/SQL Engine

Oracle Database has separate execution components for SQL and PL/SQL. When PL/SQL invokes SQL, control transfers to the SQL engine; when the SQL statement completes, control returns to the PL/SQL engine.

A loop containing DML inside it can repeat this transfer thousands or millions of times.

~~~text
PL/SQL engine
    |
    | call SQL for one row
    v
SQL engine
    |
    | complete one DML
    v
PL/SQL engine
    |
    | process next row
    v
SQL engine
    |
    | complete next DML
    v
...
~~~

This is commonly referred to as **context switching** between PL/SQL and SQL.

### 2.1. Row-by-Row Processing

With 100,000 rows, a loop can incur:

- One cursor open/setup.
- Many row fetches.
- 100,000 individual DML executions.
- Many control switches between the two engines.
- Repeated parse/execute/bind overhead depending on how it is written and optimized.

Not every engine switch carries the same cost, and Oracle can optimize certain cases. Nevertheless, row-by-row designs often generate substantial unnecessary repeated work.

### 2.2. Set-Based SQL

With set-based SQL, a single statement describes the transformation across the entire row set:

~~~sql
UPDATE employees
SET bonus = CASE
                WHEN performance_score >= 90 THEN salary * 0.20
                WHEN performance_score >= 80 THEN salary * 0.15
                ELSE salary * 0.05
            END
WHERE department_id = 10;
~~~

The SQL engine can optimize access paths, joins, filters, and DML over the entire dataset. The optimizer has full global information about the statement to choose an execution plan.

### 2.3. Bulk Processing

When not all logic fits into a single SQL statement, bulk processing helps reduce engine switches:

1. BULK COLLECT retrieves multiple rows into collections in one fetch.
2. PL/SQL processes the batch data.
3. FORALL sends DML for multiple collection elements in a single bulk-bind call.

~~~text
SQL engine
    |
    | BULK COLLECT: fetch a batch
    v
PL/SQL collection
    |
    | process batch logic
    v
FORALL
    |
    | send multiple DML binds
    v
SQL engine
~~~

Bulk processing reduces context switching, but it does not eliminate SQL execution costs, index maintenance, constraints, redo, undo, or locking. Nor does it automatically COMMIT.

## 3. Priority Order When Choosing a Processing Approach

| Approach | Mechanism | When to Use |
|---|---|---|
| Set-based SQL | A single SELECT/INSERT/UPDATE/DELETE/MERGE over a row set | Rules can be expressed in SQL |
| Cursor FOR LOOP | Fetch and process row by row; Oracle manages OPEN/FETCH/CLOSE | Need custom per-row PL/SQL logic, moderate row count |
| Explicit cursor + loop | Manually manage OPEN/FETCH/CLOSE | Need control over cursor lifecycle, attributes, or locking |
| BULK COLLECT + FORALL | Batched fetch and batched DML | Need per-row PL/SQL processing on large datasets |
| BULK COLLECT without FORALL | Fetch many rows for PL/SQL computation | Need dataset in memory or read-only/off-DB processing |

Practical guidelines:

1. Look for a way to write a single set-based SQL statement first.
2. If the logic strictly requires PL/SQL, see whether a cursor FOR LOOP is sufficient.
3. If the loop performs heavy DML or fetches over a large dataset, measure and consider BULK COLLECT/FORALL.
4. If the dataset is too large to hold in PGA, chunk batches with LIMIT.
5. If batches span multiple transactions, design for restartability and idempotency.

## 4. Converting Loops to Set-Based SQL

Before turning to bulk processing, check whether the operation can be expressed directly in SQL.

### 4.1. Multi-Row UPDATE

Row-by-row:

~~~sql
BEGIN
    FOR r IN (
        SELECT employee_id
        FROM employees
        WHERE department_id = 10
    ) LOOP
        UPDATE employees
        SET status = 'REVIEWED'
        WHERE employee_id = r.employee_id;
    END LOOP;
END;
/
~~~

Set-based:

~~~sql
UPDATE employees
SET status = 'REVIEWED'
WHERE department_id = 10;
~~~

The second SQL statement is shorter and usually more efficient because the database processes the whole row set in one statement.

### 4.2. Classification with CASE

If each row is classified based on conditions, no loop is needed to assign values:

~~~sql
UPDATE employees
SET salary_band =
    CASE
        WHEN salary IS NULL THEN 'UNKNOWN'
        WHEN salary >= 15000 THEN 'HIGH'
        WHEN salary >= 8000 THEN 'MEDIUM'
        ELSE 'LOW'
    END;
~~~

The CASE expression is evaluated for each row within the same UPDATE statement.

### 4.3. INSERT ... SELECT

If you need to move filtered/transformed data into a target table:

~~~sql
INSERT INTO archived_orders (
    order_id,
    customer_id,
    order_date,
    total_amount
)
SELECT order_id,
       customer_id,
       order_date,
       total_amount
FROM orders
WHERE order_date < DATE '2025-01-01'
  AND status = 'CLOSED';
~~~

This is a set-based load. There is no need to SELECT row by row into PL/SQL and INSERT row by row unless mandatory custom logic requires it.

### 4.4. MERGE

If you need to update existing rows and insert missing rows:

~~~sql
MERGE INTO customer_summary t
USING (
    SELECT customer_id,
           COUNT(*) AS order_count,
           SUM(total_amount) AS total_amount
    FROM orders
    WHERE status = 'CLOSED'
    GROUP BY customer_id
) s
ON (t.customer_id = s.customer_id)
WHEN MATCHED THEN
    UPDATE SET
        t.order_count = s.order_count,
        t.total_amount = s.total_amount
WHEN NOT MATCHED THEN
    INSERT (customer_id, order_count, total_amount)
    VALUES (s.customer_id, s.order_count, s.total_amount);
~~~

MERGE can replace patterns that "read each key and then decide UPDATE vs. INSERT." Ensure the source does not produce multiple rows matching the same target row, and handle concurrency/unique constraints appropriately.

### 4.5. Aggregation Instead of Accumulator Loops

Do not read row by row to sum totals in PL/SQL when SQL SUM meets the requirement:

~~~sql
SELECT customer_id,
       SUM(total_amount) AS total_sales,
       COUNT(*) AS order_count
FROM orders
WHERE status = 'PAID'
GROUP BY customer_id;
~~~

SQL aggregation leverages set-based execution and returns the exact result set needed.

### 4.6. When Can't a Loop Be Replaced by One SQL Statement?

A loop can be justified if each row needs to:

- Call an API or procedure with its own side effects.
- Execute multiple steps where each step depends on the previous step's result.
- Apply a complex algorithm difficult to express in SQL.
- Capture errors and decide to continue or stop per row.
- Process based on state external to the database.

Even when per-row processing is necessary, reading and writing can often still be batched to reduce engine-switching overhead.

## 5. Cursor FOR LOOP Is Not Bulk Processing

A cursor FOR LOOP keeps code concise because Oracle manages the cursor automatically:

~~~sql
BEGIN
    FOR r IN (
        SELECT employee_id, salary
        FROM employees
        WHERE department_id = 10
    ) LOOP
        DBMS_OUTPUT.PUT_LINE(
            r.employee_id || ': ' || r.salary
        );
    END LOOP;
END;
/
~~~

However, the loop still processes each record in PL/SQL. If there is an UPDATE inside it for each record, the program still performs row-by-row DML.

A cursor FOR LOOP is appropriate when:

- The dataset is small or moderate.
- Per-row PL/SQL logic is required.
- There is no heavy bulk DML.
- Code clarity matters more than unproven bulk optimization.

Do not replace every cursor FOR LOOP with BULK COLLECT/FORALL out of habit. Bulk processing adds collections, memory bounds, and error-handling complexity; use it when you have measured a benefit or have throughput requirements.

## 6. BULK COLLECT: Fetching Multiple Rows into Collections

BULK COLLECT lets the SQL engine return multiple rows into PL/SQL collections in a single data transfer.

It can be used with:

- SELECT ... BULK COLLECT INTO.
- FETCH cursor BULK COLLECT INTO.
- DML RETURNING BULK COLLECT INTO in supported cases.

### 6.1. Declaring Collections

Example declaring nested table types in PL/SQL:

~~~sql
DECLARE
    TYPE id_list_t IS TABLE OF employees.employee_id%TYPE;
    TYPE salary_list_t IS TABLE OF employees.salary%TYPE;

    l_ids id_list_t;
    l_salaries salary_list_t;
BEGIN
    NULL;
END;
/
~~~

A collection can hold multiple values of the same type. When BULK COLLECTing multiple columns, you typically declare one collection per fetched column.

### 6.2. SELECT BULK COLLECT INTO

~~~sql
DECLARE
    TYPE id_list_t IS TABLE OF employees.employee_id%TYPE;
    TYPE name_list_t IS TABLE OF employees.employee_name%TYPE;

    l_ids id_list_t;
    l_names name_list_t;
BEGIN
    SELECT employee_id, employee_name
    BULK COLLECT INTO l_ids, l_names
    FROM employees
    WHERE department_id = 10
    ORDER BY employee_id;

    FOR i IN 1 .. l_ids.COUNT LOOP
        DBMS_OUTPUT.PUT_LINE(
            l_ids(i) || ': ' || l_names(i)
        );
    END LOOP;
END;
/
~~~

Both collections receive the same number of rows at matching positions. Row i of L_IDS pairs with row i of L_NAMES.

If SELECT returns no rows, the collections become empty; SELECT BULK COLLECT does not raise NO_DATA_FOUND simply because zero rows matched.

### 6.3. Limitations of BULK COLLECT Without LIMIT

SELECT BULK COLLECT INTO loads the entire result set into PL/SQL memory. If a query returns millions of records or each record carries large CLOB/LOB values, PGA usage can spike and cause memory errors or hurt scalability.

Use unbounded BULK COLLECT only when result set size is bounded and fits comfortably in memory. For large datasets, use an explicit cursor with FETCH BULK COLLECT LIMIT.

## 7. FETCH BULK COLLECT with LIMIT

LIMIT specifies the maximum number of rows fetched per batch. Instead of loading all results into a collection at once, the program retrieves chunks.

Example:

~~~sql
DECLARE
    CURSOR c_employees IS
        SELECT employee_id, salary
        FROM employees
        WHERE department_id = 10
        ORDER BY employee_id;

    TYPE id_list_t IS TABLE OF employees.employee_id%TYPE;
    TYPE salary_list_t IS TABLE OF employees.salary%TYPE;

    l_ids id_list_t;
    l_salaries salary_list_t;
    c_limit CONSTANT PLS_INTEGER := 500;
BEGIN
    OPEN c_employees;

    LOOP
        FETCH c_employees
        BULK COLLECT INTO l_ids, l_salaries
        LIMIT c_limit;

        EXIT WHEN l_ids.COUNT = 0;

        FOR i IN 1 .. l_ids.COUNT LOOP
            DBMS_OUTPUT.PUT_LINE(
                l_ids(i) || ': ' || l_salaries(i)
            );
        END LOOP;
    END LOOP;

    CLOSE c_employees;
END;
/
~~~

Each FETCH retrieves at most 500 rows. The final batch may contain fewer than 500 rows; the subsequent FETCH returns an empty collection and the loop exits.

### 7.1. Why Check COUNT = 0?

With FETCH BULK COLLECT LIMIT, the final batch may contain fewer rows than LIMIT even though the cursor has reached the end of the result set. If you put EXIT right after FETCH based on cursor%NOTFOUND, some code patterns will skip processing the last batch because %NOTFOUND already indicates no more rows remain after that fetch.

The safe, memorable pattern is:

~~~sql
FETCH c_employees BULK COLLECT INTO l_ids LIMIT c_limit;
EXIT WHEN l_ids.COUNT = 0;

-- Process the entire batch just fetched
~~~

Checking for an empty collection guarantees every fetched row is processed before the loop terminates.

### 7.2. Process the Batch Before the Next Fetch

After each bulk fetch, the collection holds the current batch. Process the batch before calling FETCH again because the collection's contents are replaced by the new fetch results.

If you need to retain data across multiple batches, copy/append it to another collection or persist it to a staging table; do not assume the fetch collection accumulates batches automatically.

### 7.3. LIMIT Is Not COMMIT

LIMIT only caps how many rows each FETCH returns. It does not automatically COMMIT, release transactions, or release row locks.

If each batch runs DML, the changes remain in the current transaction until COMMIT or ROLLBACK. Choosing to commit per batch is a separate transaction decision with implications for atomicity, locking, and restartability.

## 8. FORALL: Sending Batched DML

FORALL is a PL/SQL construct that executes a single DML statement repeatedly over collection elements via bulk binding. It reduces switches between the PL/SQL engine and SQL engine compared to running a DML statement inside each iteration of a LOOP.

Example:

~~~sql
DECLARE
    TYPE id_list_t IS TABLE OF employees.employee_id%TYPE;
    l_ids id_list_t;
BEGIN
    SELECT employee_id
    BULK COLLECT INTO l_ids
    FROM employees
    WHERE department_id = 10;

    FORALL i IN 1 .. l_ids.COUNT
        UPDATE employees
        SET status = 'REVIEWED'
        WHERE employee_id = l_ids(i);
END;
/
~~~

FORALL is not a standard PL/SQL loop. PL/SQL sends the bind values from the collection to the SQL engine in bulk. The DML still runs for each bound value, but engine-switching overhead is reduced.

### 8.1. Dense Collection Requirement

Syntax:

~~~sql
FORALL i IN 1 .. l_ids.COUNT
    DELETE FROM staging_orders
    WHERE order_id = l_ids(i);
~~~

This pattern assumes the collection has contiguous indices from 1 to COUNT. If elements have been deleted with DELETE or indices start elsewhere, the 1..COUNT range can attempt to access non-existent indices.

For a dense collection freshly populated by BULK COLLECT, indices are normally 1..COUNT, so this pattern fits.

### 8.2. FORALL Contains Only One DML Statement

Within a FORALL, the body is a single DML statement applied across collection indices. You cannot place multiple distinct UPDATE/INSERT/DELETE statements inside one FORALL, nor call arbitrary PL/SQL procedures inside it as in a regular LOOP.

If multiple DML operations are needed, use separate FORALL statements or redesign as a single set-based SQL statement. Each FORALL can form a distinct bulk work unit.

### 8.3. FORALL with INSERT

~~~sql
DECLARE
    TYPE id_list_t IS TABLE OF employees.employee_id%TYPE;
    TYPE name_list_t IS TABLE OF employees.employee_name%TYPE;

    l_ids id_list_t;
    l_names name_list_t;
BEGIN
    SELECT employee_id, employee_name
    BULK COLLECT INTO l_ids, l_names
    FROM employees
    WHERE department_id = 10;

    FORALL i IN 1 .. l_ids.COUNT
        INSERT INTO employee_snapshot (
            employee_id,
            employee_name,
            captured_at
        )
        VALUES (
            l_ids(i),
            l_names(i),
            SYSTIMESTAMP
        );
END;
/
~~~

### 8.4. FORALL with DELETE

~~~sql
FORALL i IN 1 .. l_ids.COUNT
    DELETE FROM staging_orders
    WHERE order_id = l_ids(i);
~~~

If an ID does not exist, that DML iteration simply affects 0 rows; that is not necessarily an error. Use SQL%BULK_ROWCOUNT to inspect rows affected per iteration.

## 9. Sparse Collections: INDICES OF and VALUES OF

A collection can become sparse after elements are deleted or when storing only selected indices.

Example:

~~~sql
l_ids(1) := 10;
l_ids(3) := 30;
l_ids(7) := 70;
~~~

The collection has COUNT = 3, but its indices are 1, 3, and 7. FORALL 1..COUNT will try to access indices 2 and 3 over range 1..3, which does not match the actual existing indices.

### 9.1. INDICES OF

INDICES OF instructs FORALL to iterate over the indices that currently exist in the collection:

~~~sql
FORALL i IN INDICES OF l_ids
    DELETE FROM staging_orders
    WHERE order_id = l_ids(i);
~~~

You can restrict by an index range using the appropriate syntax:

~~~sql
FORALL i IN INDICES OF l_ids BETWEEN 1 AND 100
    DELETE FROM staging_orders
    WHERE order_id = l_ids(i);
~~~

Use this when the source collection is sparse and you want to apply DML to all existing elements.

### 9.2. VALUES OF

VALUES OF uses an index collection to specify which indices in the data collection to process:

~~~sql
DECLARE
    TYPE id_list_t IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    TYPE index_list_t IS TABLE OF PLS_INTEGER INDEX BY PLS_INTEGER;

    l_ids id_list_t;
    l_selected_indices index_list_t;
BEGIN
    l_ids(10) := 1001;
    l_ids(20) := 1002;
    l_ids(30) := 1003;

    l_selected_indices(1) := 10;
    l_selected_indices(2) := 30;

    FORALL i IN VALUES OF l_selected_indices
        DELETE FROM staging_orders
        WHERE order_id = l_ids(i);
END;
/
~~~

Here only indices 10 and 30 of L_IDS are used. L_IDS(20) is skipped.

The collection used with VALUES OF must have a type/indexing compatible with FORALL rules. Verify that referenced indices exist in the data collection before building the index list.

## 10. Handling Errors in FORALL with SAVE EXCEPTIONS

By default, if a DML iteration in FORALL fails and the exception is unhandled, FORALL stops at the first error and propagates the exception. When you need to continue remaining iterations and collect errors, use SAVE EXCEPTIONS.

Example:

~~~sql
DECLARE
    TYPE id_list_t IS TABLE OF NUMBER;
    l_ids id_list_t := id_list_t(10, 20, -1, 40);

    e_bulk_errors EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_bulk_errors, -24381);
BEGIN
    FORALL i IN 1 .. l_ids.COUNT SAVE EXCEPTIONS
        INSERT INTO target_ids(id)
        VALUES (l_ids(i));

    DBMS_OUTPUT.PUT_LINE('All rows inserted');

EXCEPTION
    WHEN e_bulk_errors THEN
        DBMS_OUTPUT.PUT_LINE(
            'Number of failed iterations: ' ||
            SQL%BULK_EXCEPTIONS.COUNT
        );

        FOR j IN 1 .. SQL%BULK_EXCEPTIONS.COUNT LOOP
            DBMS_OUTPUT.PUT_LINE(
                'Iteration=' ||
                SQL%BULK_EXCEPTIONS(j).ERROR_INDEX ||
                ', Error=' ||
                SQLERRM(-SQL%BULK_EXCEPTIONS(j).ERROR_CODE)
            );
        END LOOP;
END;
/
~~~

The example requires an appropriate constraint on TARGET_IDS to produce an observable error; if all values are valid, the exception handler does not run.

### 10.1. ORA-24381

When SAVE EXCEPTIONS encounters one or more failed iterations, Oracle continues executing the remaining iterations and then raises ORA-24381 (error(s) in array DML).

You can map the error with:

~~~sql
PRAGMA EXCEPTION_INIT(e_bulk_errors, -24381);
~~~

Inside the exception handler:

- SQL%BULK_EXCEPTIONS.COUNT is the number of failed iterations.
- ERROR_INDEX identifies the associated iteration/index.
- ERROR_CODE is the Oracle error code stored without a negative sign in the attribute.
- SQLERRM(-ERROR_CODE) retrieves the error message text.

### 10.2. Partial Success and Transactions

With SAVE EXCEPTIONS, successful iterations remain pending changes in the transaction; failed iterations are reported separately. They do not auto-COMMIT.

The caller must decide to:

- Accept successful rows and record errors for retry.
- ROLLBACK the entire transaction if the batch must be atomic.
- Move failed rows to a reject/quarantine table.
- Mark status so subsequent runs do not reprocess duplicates.

Never catch ORA-24381 and ignore it. Without recording errors and processing status, a batch can lose data or produce incomplete results that the caller mistakes for success.

### 10.3. Do Not Use SAVE EXCEPTIONS as a Substitute for Validation

If invalid data conditions are known upfront, validate before FORALL or enforce constraints. SAVE EXCEPTIONS is useful when a batch must continue despite unexpected row failures, not as an excuse to skip data validation.

## 11. SQL%BULK_ROWCOUNT and SQL%BULK_EXCEPTIONS

FORALL provides attributes to inspect bulk DML outcomes.

### 11.1. SQL%BULK_ROWCOUNT

SQL%BULK_ROWCOUNT(i) reports the number of rows affected by the i-th iteration of FORALL.

~~~sql
DECLARE
    TYPE id_list_t IS TABLE OF NUMBER;
    l_ids id_list_t := id_list_t(10, 20, 30);
BEGIN
    FORALL i IN 1 .. l_ids.COUNT
        UPDATE employees
        SET status = 'REVIEWED'
        WHERE employee_id = l_ids(i);

    FOR i IN 1 .. l_ids.COUNT LOOP
        DBMS_OUTPUT.PUT_LINE(
            'Input ' || l_ids(i) ||
            ', affected=' || SQL%BULK_ROWCOUNT(i)
        );
    END LOOP;

    DBMS_OUTPUT.PUT_LINE('Total affected=' || SQL%ROWCOUNT);
END;
/
~~~

SQL%ROWCOUNT after FORALL is the total number of rows affected by the bulk DML. SQL%BULK_ROWCOUNT lets you inspect each iteration's result.

Read these attributes immediately after the corresponding FORALL, before running another DML statement that could overwrite implicit SQL cursor attributes.

### 11.2. SQL%BULK_EXCEPTIONS

SQL%BULK_EXCEPTIONS holds failed iteration details when FORALL uses SAVE EXCEPTIONS. Read it only inside the corresponding exception handler; record errors before performing other work that changes the diagnostic context.

### 11.3. Mapping ERROR_INDEX to Source Data

If FORALL uses `1 .. l_ids.COUNT`, ERROR_INDEX typically maps directly to the collection position. If using INDICES OF or VALUES OF, understand the index/iteration semantics to trace back to the right source row.

When logging errors, store the row's business key alongside the error code, not just the iteration number. This supports retries and investigation after the collections go out of scope.

## 12. RETURNING BULK COLLECT INTO

Certain DML statements can return values from affected rows. When working with multiple rows, RETURNING BULK COLLECT INTO loads those values into collections.

Example with DELETE:

~~~sql
DECLARE
    TYPE id_list_t IS TABLE OF employees.employee_id%TYPE;
    l_deleted_ids id_list_t;
BEGIN
    DELETE FROM employees
    WHERE department_id = 99
    RETURNING employee_id BULK COLLECT INTO l_deleted_ids;

    DBMS_OUTPUT.PUT_LINE(
        'Deleted rows: ' || l_deleted_ids.COUNT
    );
END;
/
~~~

It can be combined with FORALL in cases supported by Oracle:

~~~sql
DECLARE
    TYPE id_list_t IS TABLE OF employees.employee_id%TYPE;
    l_ids id_list_t := id_list_t(100, 200, 300);
    l_deleted_ids id_list_t;
BEGIN
    FORALL i IN 1 .. l_ids.COUNT
        DELETE FROM employees
        WHERE employee_id = l_ids(i)
        RETURNING employee_id BULK COLLECT INTO l_deleted_ids;

    DBMS_OUTPUT.PUT_LINE(
        'Returned IDs: ' || l_deleted_ids.COUNT
    );
END;
/
~~~

When multiple iterations return results, the RETURNING collection receives returned values in bulk; do not assume returned element indices always match the input collection indices. If per-row mapping is needed, design explicit keys and reconciliation.

## 13. End-to-End Processing Pattern: BULK COLLECT + FORALL

Suppose you need to read orders in READY status, compute a fee by customer type in PL/SQL, and update fees across many rows.

Simple example:

~~~sql
DECLARE
    CURSOR c_orders IS
        SELECT order_id, shipping_fee
        FROM orders
        WHERE status = 'READY'
        ORDER BY order_id;

    TYPE id_list_t IS TABLE OF orders.order_id%TYPE;
    TYPE fee_list_t IS TABLE OF orders.shipping_fee%TYPE;

    l_ids id_list_t;
    l_fees fee_list_t;
    c_limit CONSTANT PLS_INTEGER := 500;
BEGIN
    OPEN c_orders;

    LOOP
        FETCH c_orders
        BULK COLLECT INTO l_ids, l_fees
        LIMIT c_limit;

        EXIT WHEN l_ids.COUNT = 0;

        FOR i IN 1 .. l_ids.COUNT LOOP
            -- Illustrative example of calculation rules in PL/SQL.
            -- If the expression is simple, move it directly into a set-based UPDATE.
            l_fees(i) := CASE
                WHEN l_fees(i) IS NULL THEN 0
                ELSE l_fees(i)
            END;
        END LOOP;

        FORALL i IN 1 .. l_ids.COUNT
            UPDATE orders
            SET shipping_fee = l_fees(i)
            WHERE order_id = l_ids(i);
    END LOOP;

    CLOSE c_orders;
    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        IF c_orders%ISOPEN THEN
            CLOSE c_orders;
        END IF;
        ROLLBACK;
        RAISE;
END;
/
~~~

The illustrative snippet assumes the SELECT list, collection types, and SHIPPING_FEE column exist. It simply demonstrates the pipeline of fetching batches, processing collections, and running bulk DML. If the rule is merely NVL(SHIPPING_FEE, 0), a set-based UPDATE statement is simpler and should be preferred.

### 13.1. Using Collections for Input Data

A cursor is not always necessary. If input data is already in a collection from an API or prior step, you can run FORALL directly.

~~~sql
DECLARE
    TYPE id_list_t IS TABLE OF NUMBER;
    l_ids id_list_t := id_list_t(10, 20, 30, 40);
BEGIN
    FORALL i IN 1 .. l_ids.COUNT
        UPDATE staging_orders
        SET status = 'PROCESSED'
        WHERE order_id = l_ids(i);
END;
/
~~~

### 13.2. Reading and Writing Batch by Batch

For large datasets:

1. Open the cursor.
2. FETCH BULK COLLECT LIMIT N.
3. Check for an empty collection.
4. Validate/transform the batch.
5. Execute FORALL DML.
6. Record row counts/errors for the batch.
7. Fetch the next batch.
8. Close the cursor.
9. COMMIT/ROLLBACK per transaction policy.

LIMIT controls how much data sits in memory. Commit boundaries must be designed separately.

## 14. Choosing Batch Size

Batch size is the maximum number of rows fetched in each BULK COLLECT LIMIT call. There is no single optimal value for all tables and workloads.

Too small a batch:

- Increases FETCH and FORALL calls.
- Increases engine switches.
- Increases coordination overhead.

Too large a batch:

- Consumes more PGA memory.
- Holds more data in collections.
- Can increase per-batch processing time and response latency.
- Can lengthen lock duration if DML/transactions run long.
- Makes recovery or error tracking harder if transaction policy is unclear.

Common starting points to test include 100, 500, 1,000, or 5,000 rows, but you must measure on real data and actual row sizes.

### 14.1. Influencing Factors

- Number of columns and data types fetched.
- Whether LOBs or large payloads are included.
- Available PGA and concurrency.
- PL/SQL processing time per row.
- Whether DML involves heavy indexes, triggers, foreign keys, or constraints.
- Redo/undo and I/O.
- Actual row count per batch.
- Lock contention levels.

Do not increase batch size solely to minimize FETCH count. The goal is steady throughput with bounded memory and appropriate transaction scope.

## 15. LIMIT and Transaction Boundaries

A fetch batch is not automatically a transaction. There are two common designs:

### 15.1. One Transaction for the Entire Job

- Fetch and process multiple batches.
- Do not COMMIT inside the loop.
- On unhandled error, ROLLBACK the entire transaction.
- On success, COMMIT once.

The advantage is whole-job atomicity. The downside is long-running transactions, extended locks, and large undo/redo generation before commit.

### 15.2. Commit per Batch

- Process one batch.
- Record batch status/checkpoint.
- COMMIT.
- Move to the next batch.

The advantage is shorter transactions and the ability to resume from checkpoints. The downside is losing whole-job atomicity; if batch 5 fails, earlier batches may already be committed.

If committing per batch, you need:

- Clear batch key/range partitioning.
- Durable processing status and checkpoints.
- Unique keys or idempotency to avoid duplicate processing.
- A retry and dead-letter/reject workflow for failed rows.
- Batch log writes in the same transaction as that batch's changes.
- Exclusion mechanisms so already-committed rows are not re-read.

### 15.3. Never COMMIT Row by Row

Committing on every iteration typically creates heavy overhead and complicates recovery logic. If you want batched transactions, commit after finishing a batch and saving its checkpoint, never row by row.

### 15.4. Cursors and Committing Between Batches

If a cursor stays open and relies on long-running consistent reads, committing mid-fetch can affect locking and fetch viability; with a `FOR UPDATE` cursor, COMMIT releases row locks and can cause the next fetch to fail with ORA-01002.

Never keep a `FOR UPDATE` cursor open across commits. Design a claim/lease mechanism or query a fresh batch after each commit when processing queues in chunks.

## 16. Dynamic SQL with FORALL

When a DML statement must be constructed at runtime, FORALL can be combined with EXECUTE IMMEDIATE in supported cases:

~~~sql
FORALL i IN 1 .. l_ids.COUNT
    EXECUTE IMMEDIATE
        'UPDATE staging_orders SET status = :1 WHERE order_id = :2'
        USING 'PROCESSED', l_ids(i);
~~~

Use bind variables for data values. Table/column names cannot be passed as bind variables; if identifiers must be dynamic, whitelist them or validate with DBMS_ASSERT appropriately.

Do not switch to dynamic SQL if the statement can be written statically. Dynamic SQL increases complexity, SQL injection risk, and makes dependency tracking harder.

## 17. Limits and Caveats of Bulk SQL

Bulk SQL has several limits and version-specific differences across Oracle releases:

- BULK COLLECT/FORALL work with PL/SQL collections of compatible types and indexing.
- FORALL applies a single DML statement over collection elements; it is not a loop for calling arbitrary procedures.
- Certain DML constructs, triggers, remote objects, or parallel DML have specific restrictions.
- Bulk SQL does not eliminate constraints, triggers, index maintenance, redo, undo, or row locks.
- Large collections can consume significant PGA memory.
- Dynamic SQL inside FORALL has specific binding rules.
- RETURNING BULK COLLECT and collection indexing should be verified on your target release.

Oracle imposes specific restrictions on bulk SQL with remote tables and parallel DML. Before designing distributed batches or expecting parallel execution, consult the PL/SQL Language Reference for your exact version.

## 18. Measure Performance Instead of Guessing

Compare at least three approaches on the same dataset:

1. A single set-based SQL statement.
2. A cursor FOR LOOP with row-by-row DML.
3. BULK COLLECT + FORALL.

You can use DBMS_UTILITY.GET_TIME for basic elapsed timing:

~~~sql
DECLARE
    l_start PLS_INTEGER;
    l_elapsed_cs PLS_INTEGER;
BEGIN
    l_start := DBMS_UTILITY.GET_TIME;

    UPDATE employees
    SET status = 'REVIEWED'
    WHERE department_id = 10;

    l_elapsed_cs := DBMS_UTILITY.GET_TIME - l_start;

    DBMS_OUTPUT.PUT_LINE(
        'Elapsed centiseconds = ' || l_elapsed_cs
    );

    ROLLBACK;
END;
/
~~~

GET_TIME returns time in centiseconds for this usage; take the difference between two calls. Benchmarks must use identical data, cache state, transaction context, and index/statistics conditions as closely as possible.

### 18.1. Metrics to Observe

- Elapsed time.
- CPU time.
- Logical reads/buffer gets.
- Physical reads.
- Number of SQL executions.
- Number of fetches.
- Redo/undo generation.
- PGA memory.
- Row lock waits and blocking.
- Successful/failed row counts.
- Commit duration.

### 18.2. Do Not Measure Just Once

Results can vary with buffer cache state, concurrency, statistics, bind values, and system load. Run multiple controlled trials, compare medians or distributions, and do not draw conclusions from a single fastest run.

Use SQL Trace/TKPROF, execution plans, runtime statistics, or SQL Monitor when appropriate and permitted. Do not enable broad tracing in production without assessing trace volume and overhead.

## 19. Hands-on Practice

Run exercises in a lab schema using dedicated tables that can be safely rolled back or dropped.

### Exercise 1 — Set-Based UPDATE

Create a `LAB_EMPLOYEES` table with many rows. Write a single UPDATE increasing salary by 5% for department 10. Record `SQL%ROWCOUNT`.

### Exercise 2 — Row-by-Row UPDATE

Rewrite Exercise 1 using a cursor FOR LOOP and row-by-row UPDATE. Compare the code and DML execution counts.

### Exercise 3 — BULK COLLECT Without LIMIT

Fetch all `employee_id` values into a collection and print `COUNT`. Test with increasing row counts and observe memory usage.

### Exercise 4 — BULK COLLECT LIMIT

Use a cursor with LIMIT 100, 500, and 1,000. Print row counts per batch and total processed rows. Verify the final batch has fewer rows than LIMIT.

### Exercise 5 — Checking the Final Batch

Test FETCH BULK COLLECT LIMIT with a total row count not divisible by LIMIT. Use `EXIT WHEN collection.COUNT = 0`; compare with exiting immediately on `cursor%NOTFOUND`.

### Exercise 6 — FORALL UPDATE

BULK COLLECT IDs, then FORALL UPDATE status. Compare elapsed time against the cursor loop.

### Exercise 7 — FORALL INSERT

Load source data into two collections and FORALL INSERT into a snapshot table. Reconcile row counts.

### Exercise 8 — Sparse Collection

Populate indices 1, 3, and 7 in an associative array. Try `FORALL 1..COUNT` and explain the error. Fix it using `INDICES OF`.

### Exercise 9 — VALUES OF

Create an ID collection and a collection holding selected indices. Use `VALUES OF` to process only a subset.

### Exercise 10 — SAVE EXCEPTIONS

Create a target table with a UNIQUE constraint. Intentionally send a duplicate value through `FORALL SAVE EXCEPTIONS`. Print `ERROR_INDEX`, `ERROR_CODE`, and `SQLERRM`.

### Exercise 11 — SQL%BULK_ROWCOUNT

Use FORALL UPDATE with both existing and non-existent IDs. Print affected rows per iteration and total `SQL%ROWCOUNT`.

### Exercise 12 — Batch Transactions

Split data into 500-row batches. Try one transaction for the entire job versus committing after each batch. Compare retryability, checkpoint state, and outcomes when intentionally inducing a mid-job failure.

### Exercise 13 — Comparing Three Approaches

Run the same update over the same row count using set-based SQL, cursor FOR LOOP, and BULK COLLECT + FORALL. Record elapsed time, buffer gets, and DML count.

### Exercise 14 — Architecture Selection

For each scenario below, explain whether to use set-based SQL, a cursor loop, or bulk processing:

- Update the same column with the same expression across one million rows.
- Call a complex PL/SQL procedure for each customer.
- Load staging data to a target table with per-batch validation.
- Compute total revenue by customer.
- Record each failing row individually while continuing to process valid rows.

## 20. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Using a loop for a transformation expressible as one UPDATE | Excessive context switches and repeated DML | Write set-based SQL |
| Thinking a cursor FOR LOOP is bulk processing | Still processes row by row | Use BULK COLLECT/FORALL if batching is needed |
| BULK COLLECTing an entire large dataset | PGA growth, potential out-of-memory errors | FETCH LIMIT |
| Exiting immediately on %NOTFOUND after bulk fetch | May skip the final unprocessed batch | Check `collection.COUNT = 0` |
| Using FORALL 1..COUNT on a sparse collection | Non-existent index error | INDICES OF or VALUES OF |
| Thinking FORALL calls a procedure per element | Wrong model and invalid syntax | Use FORALL for DML; separate procedure loop if needed |
| Omitting SAVE EXCEPTIONS while expecting later rows to run after error | FORALL stops on first error | SAVE EXCEPTIONS and handle ORA-24381 |
| Catching ORA-24381 and ignoring it | Loss of failed-row information | Log business keys and error codes |
| Thinking BULK COLLECT LIMIT auto-COMMITs | Transaction stays open | Design commit boundaries explicitly |
| Committing row by row | High overhead, loss of atomicity | Commit per transaction/batch with checkpoints |
| Committing inside a cursor FOR UPDATE | Releases locks and can fail subsequent fetch | Never commit while a FOR UPDATE cursor still needs fetching |
| Using too large a batch size | Higher PGA usage and batch processing time | Measure and tune LIMIT |
| Using too small a batch size | More fetch/DML round-trips | Benchmark multiple batch sizes |
| Using FORALL for a uniform update | More complex than set-based SQL | Single UPDATE statement if possible |
| Running benchmarks under different conditions | Wrong conclusions | Control data, cache, statistics, and concurrency |

## 21. Checklist for Choosing and Implementing Bulk Processing

- [ ] Check whether a single set-based SQL statement can be used.
- [ ] Use CASE, JOIN, GROUP BY, INSERT SELECT, or MERGE where appropriate.
- [ ] Use loops only when PL/SQL logic is genuinely necessary.
- [ ] Distinguish cursor FOR LOOP from bulk processing.
- [ ] Use BULK COLLECT to fetch multiple rows per call.
- [ ] Use LIMIT for large datasets.
- [ ] Handle the final batch by checking for an empty collection.
- [ ] Choose appropriate collection types and indexing.
- [ ] Use FORALL for DML over collections.
- [ ] Use INDICES OF/VALUES OF for sparse collections.
- [ ] Use SAVE EXCEPTIONS when remaining iterations must continue and collect errors.
- [ ] Capture SQL%BULK_EXCEPTIONS and SQL%BULK_ROWCOUNT immediately after FORALL.
- [ ] Clearly define whether failed rows are retried, rejected, or roll back the entire batch.
- [ ] Separate batch size from transaction boundary.
- [ ] Implement checkpoints/idempotency if committing per batch.
- [ ] Never commit inside a cursor FOR UPDATE loop.
- [ ] Measure elapsed time, CPU, buffer gets, PGA, redo, and locks.
- [ ] Test on representative data before production deployment.

## 22. Key Takeaways

- Set-based SQL is the first choice whenever a transformation can be expressed via SELECT, INSERT, UPDATE, DELETE, or MERGE.
- Row-by-row PL/SQL often incurs heavy switching between the PL/SQL engine and the SQL engine.
- Cursor FOR LOOP manages OPEN/FETCH/CLOSE automatically but still processes row by row; it does not automatically become bulk processing.
- BULK COLLECT fetches multiple rows into collections in a single data transfer.
- FETCH BULK COLLECT LIMIT bounds PGA usage and processes large datasets in batches.
- With bulk fetches, check `collection.COUNT = 0` to exit only after every batch has been processed, including a final batch smaller than LIMIT.
- FORALL uses collection binding to send one DML statement for many elements and reduce context switching.
- FORALL 1..COUNT assumes a dense collection; use INDICES OF or VALUES OF when the collection is sparse.
- SAVE EXCEPTIONS lets remaining iterations continue and reports errors via ORA-24381/SQL%BULK_EXCEPTIONS.
- SQL%BULK_ROWCOUNT(i) reports rows affected per iteration; SQL%ROWCOUNT reports the bulk DML total.
- Bulk processing does not auto-COMMIT and does not eliminate redo, undo, index maintenance, triggers, or row locks.
- LIMIT is the fetch batch size, not a transaction boundary.
- Committing per batch requires checkpoints, retries, idempotency, and clear recovery rules.
- Choose batch size by measuring on representative data; there is no single optimal number for every workload.

### Oracle Documentation References

- [Oracle Database PL/SQL Language Reference — Bulk SQL and Bulk Binding](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/bulk-sql-and-bulk-binding.html) — BULK COLLECT, FORALL, LIMIT, SAVE EXCEPTIONS, and collection indexing.
- [Oracle Database PL/SQL Language Reference — Cursor Variables and Explicit Cursors](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/cursors-overview.html) — Cursor lifecycle, FETCH, and cursor attributes.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/) — Set-based SELECT, INSERT, UPDATE, DELETE, MERGE, and RETURNING.
- [Oracle Database Performance Tuning Guide](https://docs.oracle.com/en/database/) — SQL execution plans, runtime statistics, and performance measurement.
- [Oracle Database PL/SQL Packages and Types Reference](https://docs.oracle.com/en/database/) — DBMS_UTILITY, DBMS_APPLICATION_INFO, and observability utilities.

Details of bulk SQL, collection indexing, dynamic SQL, and parallel/remote restrictions depend on the Oracle release. Consult the documentation for your exact version, measure with representative dataset sizes, and test the final batch, sparse collections, partial failures, and rollbacks before deployment.
