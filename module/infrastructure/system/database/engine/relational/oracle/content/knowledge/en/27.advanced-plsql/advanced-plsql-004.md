# SAVE EXCEPTIONS, SQL%BULK_EXCEPTIONS, and Partial Error Handling

When processing bulk data in PL/SQL, FORALL sends multiple DML executions using bulk binding, reducing context-switching overhead between the PL/SQL engine and the SQL engine. However, an element in a collection can cause DML to fail due to unique key, foreign key, CHECK constraint, NOT NULL, conversion errors, or other data rules. Without an error-handling strategy, a single error can stop FORALL before the entire batch is processed.

SAVE EXCEPTIONS allows FORALL to continue executing the remaining iterations when one iteration encounters a DML error. After trying all iterations, Oracle raises the aggregate exception ORA-24381. In the exception handler, the program reads SQL%BULK_EXCEPTIONS to find which iteration failed and its corresponding error code. SQL%BULK_ROWCOUNT reports how many rows were affected by each iteration; SQL%ROWCOUNT reports the total number of rows affected by the bulk DML.

This is a partial-success mechanism. It does not automatically COMMIT, does not automatically retry, and does not decide whether the business logic accepts the successful rows or must ROLLBACK the entire batch. The author must explicitly design how errors map back to inputs, log persistence, retries, and transaction termination.

After this lesson, you can:

- Understand why FORALL needs a per-iteration error-handling strategy.
- Distinguish default FORALL behavior from FORALL SAVE EXCEPTIONS.
- Catch the ORA-24381 exception using PRAGMA EXCEPTION_INIT.
- Read SQL%BULK_EXCEPTIONS.COUNT, ERROR_INDEX, and ERROR_CODE.
- Use SQLERRM with a negative error code to retrieve the Oracle message.
- Map errors back to input elements in the collection.
- Combine SQL%BULK_ROWCOUNT and SQL%ROWCOUNT to summarize results.
- Handle dense and sparse collections, INDICES OF, and VALUES OF.
- Persist errors into a log table, distinguishing same-transaction logging from independent logging.
- Decide whether to keep partial success, roll back the whole batch, or retry failed items.
- Distinguish SAVE EXCEPTIONS from DML error logging (LOG ERRORS).
- Design batch DML that can be monitored, recovered, and safely re-run.

> Examples use LAB_ tables in a dedicated practice schema. COMMIT/ROLLBACK statements are an application transaction decision; FORALL does not auto-commit.

## 1. Context: Errors in Bulk DML

### 1.1. What Problem Does FORALL Solve?

A regular DML loop performs many context switches between PL/SQL and SQL:

```sql
FOR i IN 1 .. l_employee_ids.COUNT LOOP
    UPDATE employees
    SET status = 'ACTIVE'
    WHERE employee_id = l_employee_ids(i);
END LOOP;
```

With hundreds of thousands of elements, this row-by-row approach can create significant overhead. FORALL sends collection values into a DML statement using bulk binding:

```sql
FORALL i IN 1 .. l_employee_ids.COUNT
    UPDATE employees
    SET status = 'ACTIVE'
    WHERE employee_id = l_employee_ids(i);
```

FORALL is not a regular PL/SQL loop. It applies only to a single DML statement inside the FORALL body and uses collection indices to bind values for multiple executions.

### 1.2. Why Do Per-Element Errors Occur?

Suppose an INSERT batch has 5 elements:

| Iteration | Input | Result |
| ---: | --- | --- |
| 1 | Code A01, quantity 10 | Valid |
| 2 | Code A02, quantity 20 | Valid |
| 3 | Code A01, quantity 30 | Duplicate unique key |
| 4 | Code A04, quantity -5 | Violates CHECK |
| 5 | Code A05, quantity 40 | Valid |

If each iteration is an independent INSERT inside FORALL, iterations 3 and 4 can fail while 1, 2, and 5 remain valid. The program needs to know exactly which element failed and why.

### 1.3. Not Every 0-Row Case Is an Exception

An UPDATE that finds no rows matching WHERE normally succeeds with 0 rows affected. This does not raise an exception by itself and is not recorded in SQL%BULK_EXCEPTIONS.

Example:

```sql
FORALL i IN 1 .. l_ids.COUNT
    UPDATE lab_employee
    SET status = 'ACTIVE'
    WHERE employee_id = l_ids(i);
```

If an ID does not exist, that iteration can have SQL%BULK_ROWCOUNT(i) = 0, which is not a DML error. Distinguish clearly:

- No matching rows: DML succeeds, row count can be 0.
- DML failure: Oracle raises an error, such as ORA-00001 or ORA-02290.

## 2. Default FORALL Behavior

### 2.1. Without SAVE EXCEPTIONS

Example:

```sql
FORALL i IN 1 .. l_codes.COUNT
    INSERT INTO lab_items (item_code)
    VALUES (l_codes(i));
```

If an iteration raises a DML error, default FORALL stops at that error and propagates the exception. Changes performed by previous iterations of that FORALL itself are rolled back when FORALL fails. Changes made before FORALL in the transaction are not automatically rolled back just because FORALL failed.

This means the batch does not automatically continue to inputs after the failed element. If you need to capture errors and continue processing remaining elements, use SAVE EXCEPTIONS.

### 2.2. Illustrative Example

Suppose a collection has 5 codes, and the 3rd code duplicates a unique key. Without SAVE EXCEPTIONS:

```sql
FORALL i IN 1 .. l_codes.COUNT
    INSERT INTO lab_items (item_code)
    VALUES (l_codes(i));
```

When iteration 3 fails:

- FORALL stops.
- Iterations 4 and 5 are not executed.
- Changes from previous iterations in the same FORALL are rolled back.
- The exception propagates to the enclosing block.

If the requirement is for valid rows to still be written and failed rows to be saved for review, this default behavior does not meet the requirement.

### 2.3. DML Exceptions Differ from PL/SQL Logic Checks

SAVE EXCEPTIONS collects errors raised during each DML execution inside FORALL. It does not automatically turn every PL/SQL logic error into an entry in SQL%BULK_EXCEPTIONS.

- Unique/check/foreign key violations in an iteration: can be collected.
- An element not matching an UPDATE WHERE clause: not an error, row count is 0.
- A PL/SQL error occurring before FORALL starts: not part of FORALL's error list.
- Parse errors, privilege errors, or statement structural errors: not necessarily row-level errors saved as an iteration error.

## 3. How Does SAVE EXCEPTIONS Work?

### 3.1. Syntax

Add SAVE EXCEPTIONS after the FORALL bounds clause:

```sql
FORALL i IN 1 .. l_codes.COUNT SAVE EXCEPTIONS
    INSERT INTO lab_items (item_code)
    VALUES (l_codes(i));
```

If an iteration fails:

1. Oracle records the error information for the iteration.
2. The failed DML iteration is not considered successful.
3. Oracle continues with the remaining iterations.
4. After trying the iterations, if any errors were saved, Oracle raises exception ORA-24381.
5. The PL/SQL block catches the exception and reads SQL%BULK_EXCEPTIONS.

### 3.2. Timeline

```text
FORALL ... SAVE EXCEPTIONS
          |
          v
     Iteration 1 ---- DML succeeds
          |
          v
     Iteration 2 ---- DML error -> save error
          |
          v
     Iteration 3 ---- DML succeeds
          |
          v
     Iteration 4 ---- DML error -> save error
          |
          v
     Iteration 5 ---- DML succeeds
          |
          v
     End of FORALL
          |
          v
     ORA-24381 is raised
          |
          v
     EXCEPTION HANDLER
       - SQL%BULK_EXCEPTIONS
       - SQL%BULK_ROWCOUNT
       - SQL%ROWCOUNT
```

### 3.3. SAVE EXCEPTIONS Does Not Ignore Errors

SAVE EXCEPTIONS does not make a statement always succeed. It aggregates per-iteration errors for the program to handle after FORALL has tried all elements. If errors occurred, the aggregate exception is still raised.

Do not swallow ORA-24381 and report the batch as completely successful. The caller needs to receive a partial-success status or the appropriate business exception.

### 3.4. Successful Changes Remain in the Current Transaction

With SAVE EXCEPTIONS, successful iterations keep their changes in the current transaction. Oracle does not COMMIT those rows. The caller can:

- COMMIT to keep both the successful rows and error logs if the business allows partial success.
- ROLLBACK to cancel all changes in the transaction.
- ROLLBACK TO SAVEPOINT to cancel the batch portion while keeping changes made before the savepoint.

Failed iterations leave no successful DML changes of their own. The transaction remains under the caller's control.

## 4. Catching ORA-24381 with PRAGMA EXCEPTION_INIT

### 4.1. ORA-24381 Is an Aggregate Error

When FORALL SAVE EXCEPTIONS has at least one failed iteration, Oracle raises:

```text
ORA-24381: error(s) in array DML
```

In PL/SQL, you can name an exception for error code -24381 using PRAGMA EXCEPTION_INIT.

### 4.2. Exception Declaration

```sql
DECLARE
    e_bulk_errors EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_bulk_errors, -24381);
BEGIN
    NULL;
END;
/
```

ERROR_CODE in SQL%BULK_EXCEPTIONS is provided as a positive number; when declaring the exception, use the negative Oracle code -24381.

### 4.3. Catching the Error

```sql
EXCEPTION
    WHEN e_bulk_errors THEN
        -- Handle the bulk error list.
        NULL;
```

A dedicated handler helps distinguish partial bulk errors from other errors. If WHEN OTHERS is still needed, place it after specific handlers and re-raise unexpected errors.

### 4.4. Distinguishing ORA-24381 from Underlying Errors

ORA-24381 reports that one or more DML iterations failed. The specific error code for each iteration is in SQL%BULK_EXCEPTIONS(j).ERROR_CODE, for example:

| Error Code | Example Meaning |
| --- | --- |
| ORA-00001 | Unique constraint/index violation |
| ORA-01400 | Insert NULL into a NOT NULL column |
| ORA-02290 | CHECK constraint violation |
| ORA-02291 | Foreign key parent key not found |
| ORA-02292 | Cannot delete parent row because child rows exist |
| ORA-12899 | Value too large for column |

These are common examples; actual error codes depend on the statement and schema.

## 5. SQL%BULK_EXCEPTIONS

### 5.1. Structure

SQL%BULK_EXCEPTIONS is a collection belonging to the implicit bulk SQL cursor. Each element describes an error saved by FORALL SAVE EXCEPTIONS.

| Attribute | Meaning |
| --- | --- |
| SQL%BULK_EXCEPTIONS.COUNT | Number of recorded errors |
| SQL%BULK_EXCEPTIONS(j).ERROR_INDEX | Iteration index associated with the error |
| SQL%BULK_EXCEPTIONS(j).ERROR_CODE | Oracle error code as a positive number |

Example of reading errors:

```sql
FOR j IN 1 .. SQL%BULK_EXCEPTIONS.COUNT LOOP
    DBMS_OUTPUT.PUT_LINE(
        'Iteration = ' ||
        SQL%BULK_EXCEPTIONS(j).ERROR_INDEX
    );

    DBMS_OUTPUT.PUT_LINE(
        'Error code = ' ||
        SQL%BULK_EXCEPTIONS(j).ERROR_CODE
    );

    DBMS_OUTPUT.PUT_LINE(
        SQLERRM(-SQL%BULK_EXCEPTIONS(j).ERROR_CODE)
    );
END LOOP;
```

### 5.2. Why Is ERROR_CODE Positive?

ERROR_CODE stores the error number without the minus sign. SQLERRM accepts a negative error code to generate the message. Therefore, use:

```sql
SQLERRM(-SQL%BULK_EXCEPTIONS(j).ERROR_CODE)
```

Do not pass a positive code to SQLERRM and expect the corresponding error message.

### 5.3. ERROR_INDEX Maps Back to Input

With FORALL using a contiguous range:

```sql
FORALL i IN 1 .. l_ids.COUNT SAVE EXCEPTIONS
```

If ERROR_INDEX = 3, the error belongs to iteration i = 3; you can use l_ids(3) to find the original input.

With sparse collections or when using INDICES OF/VALUES OF, you must understand the bounds clause mapping. Do not assume position j in SQL%BULK_EXCEPTIONS is the original collection index. Use the index reported by Oracle and map it properly according to how FORALL traverses the collection.

### 5.4. Error Ordering

SQL%BULK_EXCEPTIONS is the list of collected errors. Use ERROR_INDEX as the key to identify the iteration, not position j in the error list as the input index. A batch might only fail at iterations 2 and 9; then the error collection has two elements, while ERROR_INDEX reports 2 and 9 respectively.

### 5.5. Multiple Errors on the Same Key

If inputs repeat the same business key, one iteration can succeed while a subsequent iteration hits a unique violation. ERROR_INDEX helps locate the exact input element that caused the error. Do not store only the business key if you need to distinguish two duplicate input rows; also store batch ID, source row number, or correlation ID.

## 6. SQL%BULK_ROWCOUNT and SQL%ROWCOUNT

### 6.1. SQL%BULK_ROWCOUNT(i)

SQL%BULK_ROWCOUNT(i) returns the number of rows affected by the DML execution corresponding to iteration i of FORALL.

Example:

```sql
FORALL i IN 1 .. l_ids.COUNT SAVE EXCEPTIONS
    UPDATE lab_employees
    SET status = 'ACTIVE'
    WHERE employee_id = l_ids(i);
```

If the first ID matches one row, the second ID matches no rows, and the third ID matches one row:

| Iteration | SQL%BULK_ROWCOUNT |
| ---: | ---: |
| 1 | 1 |
| 2 | 0 |
| 3 | 1 |

No exception is raised simply because iteration 2 has a row count of 0.

### 6.2. SQL%ROWCOUNT

After FORALL, SQL%ROWCOUNT is the total number of rows affected by the DML executions in the bulk statement. In the example above, the total is 2.

When SAVE EXCEPTIONS encounters errors, capture the total successful rows in a PL/SQL variable inside the handler:

```sql
EXCEPTION
    WHEN e_bulk_errors THEN
        l_total_rows := SQL%ROWCOUNT;
        l_error_count := SQL%BULK_EXCEPTIONS.COUNT;
```

Capture these values before running logging SQL statements or calling other procedures, because SQL%ROWCOUNT describes the most recent SQL statement.

### 6.3. Comparison

| Attribute | Question Answered |
| --- | --- |
| SQL%ROWCOUNT | How many total rows did the bulk DML affect? |
| SQL%BULK_ROWCOUNT(i) | How many rows did iteration i affect? |
| SQL%BULK_EXCEPTIONS.COUNT | How many failed iterations were saved? |
| ERROR_INDEX | Which iteration encountered an error? |
| ERROR_CODE | What is the Oracle error code for that iteration? |

### 6.4. Total Iterations Does Not Equal Total Rows

If a conditional UPDATE iteration can affect multiple rows, SQL%BULK_ROWCOUNT(i) can be greater than 1. If no rows match, the value is 0. Therefore:

- Attempted iterations = number of inputs traversed by FORALL.
- Failed iterations = SQL%BULK_EXCEPTIONS.COUNT.
- Total affected rows = SQL%ROWCOUNT.

These three numbers are not necessarily equal.

## 7. Standard Error-Handling Pattern

### 7.1. General Skeleton

```sql
DECLARE
    e_bulk_errors EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_bulk_errors, -24381);

    l_rows_affected PLS_INTEGER := 0;
    l_error_count   PLS_INTEGER := 0;
BEGIN
    FORALL i IN 1 .. l_values.COUNT SAVE EXCEPTIONS
        INSERT INTO target_table (value_col)
        VALUES (l_values(i));

    l_rows_affected := SQL%ROWCOUNT;

EXCEPTION
    WHEN e_bulk_errors THEN
        l_rows_affected := SQL%ROWCOUNT;
        l_error_count := SQL%BULK_EXCEPTIONS.COUNT;

        FOR j IN 1 .. l_error_count LOOP
            DBMS_OUTPUT.PUT_LINE(
                'Input index = ' ||
                SQL%BULK_EXCEPTIONS(j).ERROR_INDEX
            );
            DBMS_OUTPUT.PUT_LINE(
                'Error = ' ||
                SQLERRM(-SQL%BULK_EXCEPTIONS(j).ERROR_CODE)
            );
        END LOOP;
END;
/
```

This is an illustrative skeleton. In a real application, you need to add collection declarations, input mapping, a transaction policy, and a way to return status to the caller.

### 7.2. Catching ORA-24381 Separately

A dedicated handler helps distinguish partial bulk errors from other errors:

```sql
EXCEPTION
    WHEN e_bulk_errors THEN
        -- Handle the bulk error list.
        NULL;
    WHEN OTHERS THEN
        -- Unexpected error.
        RAISE;
```

Do not turn every exception into a generic "bulk failed" line; doing so hides programming errors, privilege issues, invalid objects, or other runtime errors.

### 7.3. Capture Information Before Logging

If the handler INSERTs into a log table, that INSERT changes SQL%ROWCOUNT. Save it first:

```sql
l_rows_affected := SQL%ROWCOUNT;
l_error_count   := SQL%BULK_EXCEPTIONS.COUNT;
```

If you need to execute another FORALL, copy the error details you need to keep into a separate PL/SQL collection before running the next FORALL.

## 8. Complete Example: Multi-Row INSERT and Error Recording

### 8.1. Create the Target Table

Run in the lab schema:

```sql
CREATE TABLE lab_bulk_items (
    item_id    NUMBER(10)
        CONSTRAINT pk_lab_bulk_items PRIMARY KEY,
    item_code  VARCHAR2(20)
        CONSTRAINT uq_lab_bulk_items_code UNIQUE,
    quantity   NUMBER(10)
        CONSTRAINT ck_lab_bulk_items_qty CHECK (quantity >= 0),
    item_name  VARCHAR2(30) NOT NULL
);
```

### 8.2. Populate Input Collections and Run FORALL

```sql
DECLARE
    TYPE t_item_ids IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    TYPE t_item_codes IS TABLE OF VARCHAR2(20) INDEX BY PLS_INTEGER;
    TYPE t_quantities IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    TYPE t_item_names IS TABLE OF VARCHAR2(30) INDEX BY PLS_INTEGER;

    l_ids   t_item_ids;
    l_codes t_item_codes;
    l_qty   t_quantities;
    l_names t_item_names;

    e_bulk_errors EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_bulk_errors, -24381);

    l_rows_affected PLS_INTEGER := 0;
    l_error_count   PLS_INTEGER := 0;
BEGIN
    l_ids(1) := 1;
    l_ids(2) := 2;
    l_ids(3) := 3;
    l_ids(4) := 4;
    l_ids(5) := 5;

    l_codes(1) := 'A01';
    l_codes(2) := 'A02';
    l_codes(3) := 'A01'; -- Duplicate code from iteration 1.
    l_codes(4) := 'A04';
    l_codes(5) := 'A05';

    l_qty(1) := 10;
    l_qty(2) := 20;
    l_qty(3) := 30;
    l_qty(4) := -5; -- Violates CHECK constraint.
    l_qty(5) := 40;

    l_names(1) := 'Keyboard';
    l_names(2) := 'Mouse';
    l_names(3) := 'Duplicate';
    l_names(4) := 'Invalid quantity';
    l_names(5) := 'Monitor';

    BEGIN
        FORALL i IN 1 .. l_ids.COUNT SAVE EXCEPTIONS
            INSERT INTO lab_bulk_items (
                item_id, item_code, quantity, item_name
            )
            VALUES (
                l_ids(i), l_codes(i), l_qty(i), l_names(i)
            );

        l_rows_affected := SQL%ROWCOUNT;

    EXCEPTION
        WHEN e_bulk_errors THEN
            l_rows_affected := SQL%ROWCOUNT;
            l_error_count := SQL%BULK_EXCEPTIONS.COUNT;

            DBMS_OUTPUT.PUT_LINE(
                'Successful affected rows = ' || l_rows_affected
            );
            DBMS_OUTPUT.PUT_LINE(
                'Failed iterations = ' || l_error_count
            );

            FOR j IN 1 .. l_error_count LOOP
                DECLARE
                    l_index PLS_INTEGER;
                    l_code  PLS_INTEGER;
                BEGIN
                    l_index := SQL%BULK_EXCEPTIONS(j).ERROR_INDEX;
                    l_code := SQL%BULK_EXCEPTIONS(j).ERROR_CODE;

                    DBMS_OUTPUT.PUT_LINE(
                        'Iteration ' || l_index ||
                        ', item_id=' || l_ids(l_index) ||
                        ', item_code=' || l_codes(l_index)
                    );
                    DBMS_OUTPUT.PUT_LINE(
                        'Oracle error=' || l_code ||
                        ', message=' || SQLERRM(-l_code)
                    );
                END;
            END LOOP;
    END;
END;
/
```

With an initially empty table and the sample data, iterations 1, 2, and 5 can INSERT successfully; iteration 3 violates the unique constraint; iteration 4 violates the CHECK constraint. The expected total affected rows is 3, and the error count is 2.

### 8.3. View Successful Data

```sql
SELECT item_id, item_code, quantity, item_name
FROM lab_bulk_items
ORDER BY item_id;
```

The expected result contains codes A01, A02, and A05. Failed rows were not inserted.

### 8.4. Verify Transaction State

Successfully inserted rows still belong to the current transaction. If you run ROLLBACK, the batch's successful rows are rolled back. If you want to keep the lab results, COMMIT after verifying the outcome. Do not add an automatic COMMIT inside a shared bulk procedure if the caller needs to control a broader transaction.

## 9. Writing Errors to an Error Log Table

### 9.1. Why Is an Error Table Needed?

DBMS_OUTPUT is only useful when an operator is watching the output. Background batches need to persist error information to:

- Know which batch had errors.
- Trace back to the source input that caused the error.
- View Oracle error codes and messages.
- Retry the exact failed elements after fixing data.
- Track counts of successful and failed rows.
- Reconcile with the source file or upstream system.

### 9.2. Create the Log Table

```sql
CREATE TABLE lab_bulk_error_log (
    error_log_id  NUMBER GENERATED BY DEFAULT AS IDENTITY
                  CONSTRAINT pk_lab_bulk_error_log PRIMARY KEY,
    batch_id      VARCHAR2(50) NOT NULL,
    input_index   NUMBER,
    source_key    VARCHAR2(100),
    error_code    NUMBER,
    error_message VARCHAR2(2000),
    logged_at     TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);
```

### 9.3. Log Each Error

In the exception handler, capture summary values first, then log each error:

```sql
EXCEPTION
    WHEN e_bulk_errors THEN
        l_rows_affected := SQL%ROWCOUNT;
        l_error_count := SQL%BULK_EXCEPTIONS.COUNT;

        FOR j IN 1 .. l_error_count LOOP
            l_index := SQL%BULK_EXCEPTIONS(j).ERROR_INDEX;
            l_code := SQL%BULK_EXCEPTIONS(j).ERROR_CODE;

            INSERT INTO lab_bulk_error_log (
                batch_id,
                input_index,
                source_key,
                error_code,
                error_message
            )
            VALUES (
                p_batch_id,
                l_index,
                l_source_keys(l_index),
                l_code,
                SQLERRM(-l_code)
            );
        END LOOP;
```

The snippet above should be placed inside a procedure/block that declares p_batch_id, l_index, l_code, and the l_source_keys collection. If the collection is sparse or uses VALUES OF, map inputs according to the actual bounds clause.

### 9.4. Same-Transaction Logging

If the log table is INSERTed in the same transaction:

- COMMIT keeps both successful DML rows and error logs.
- ROLLBACK discards both successful DML rows and error logs.
- This is a good choice if the log is part of the batch outcome and must stay consistent with the transaction.

### 9.5. Transaction-Independent Logging

Sometimes diagnostic logs must be preserved even when the caller rolls back the entire batch. You can design a separate autonomous transaction logger, but you must consider:

- Independent logs can persist even when the business batch is rolled back.
- The logger must receive the batch ID, input key, and error details via parameters.
- Do not call external services or write excessive per-row logs unnecessarily.
- Do not let the logger read uncommitted data from the parent transaction.
- Do not turn autonomous transactions into an uncontrolled way to partially commit business data.

For bulk errors, the simplest and most controllable approach is usually to store logs in the same transaction and let the caller decide whether to commit or roll back. Only use independent logging when operational requirements truly demand it.

## 10. Dense and Sparse Collections and ERROR_INDEX

### 10.1. Dense Collection

A dense collection has contiguous indices, such as 1, 2, 3, 4:

```sql
FORALL i IN 1 .. l_ids.COUNT SAVE EXCEPTIONS
    INSERT INTO lab_target (id) VALUES (l_ids(i));
```

In this case ERROR_INDEX corresponds directly to i, so you can use l_ids(ERROR_INDEX) to find the input.

### 10.2. Sparse Collection

An associative array collection can have indices 10, 20, 50 instead of 1, 2, 3. In that case you should not use 1..COUNT because elements 1, 2, 3 do not exist.

Use INDICES OF:

```sql
FORALL i IN INDICES OF l_ids SAVE EXCEPTIONS
    DELETE FROM lab_target
    WHERE id = l_ids(i);
```

INDICES OF iterates over existing subscripts. When handling ERROR_INDEX, map according to the subscript/iteration reported by FORALL rather than using the ordinal position in the error list as the input index.

### 10.3. VALUES OF

VALUES OF uses an index collection to specify elements of the data collection:

```sql
TYPE t_index_list IS TABLE OF PLS_INTEGER
    INDEX BY PLS_INTEGER;

l_selected_indices(1) := 10;
l_selected_indices(2) := 50;

FORALL i IN VALUES OF l_selected_indices SAVE EXCEPTIONS
    UPDATE lab_target
    SET status = 'READY'
    WHERE id = l_ids(i);
```

In the example, the index collection selects elements l_ids(10) and l_ids(50). When using VALUES OF, carefully check what ERROR_INDEX represents in the context of the iteration/index collection and maintain a clear mapping from iteration to source row. Do not hard-code an assumption that error indices are always contiguous positions 1..COUNT.

### 10.4. Store Source Keys Alongside Data

For retries and auditing, keep in parallel:

- Collections holding DML data.
- A collection holding the source row number or business key.
- Batch ID/correlation ID.

When an error occurs, use ERROR_INDEX to trace back to the original input. If inputs are transformed or filtered before FORALL, store the mapping from iteration to source record as soon as you build the collection.

## 11. Combining BULK COLLECT and FORALL SAVE EXCEPTIONS

### 11.1. Fetching in Batches

For large source tables, do not BULK COLLECT all rows into PGA at once. Use a cursor with LIMIT:

```sql
DECLARE
    CURSOR c_source IS
        SELECT source_id, item_code, quantity, item_name
        FROM lab_source_items
        WHERE processed_flag = 'N';

    TYPE t_source_id IS TABLE OF lab_source_items.source_id%TYPE;
    TYPE t_code IS TABLE OF lab_source_items.item_code%TYPE;
    TYPE t_qty IS TABLE OF lab_source_items.quantity%TYPE;
    TYPE t_name IS TABLE OF lab_source_items.item_name%TYPE;

    l_source_ids t_source_id;
    l_codes      t_code;
    l_qty        t_qty;
    l_names      t_name;
BEGIN
    OPEN c_source;
    LOOP
        FETCH c_source BULK COLLECT
        INTO l_source_ids, l_codes, l_qty, l_names
        LIMIT 500;

        EXIT WHEN l_source_ids.COUNT = 0;

        -- FORALL processes the current batch.
        NULL;
    END LOOP;
    CLOSE c_source;
END;
/
```

Each FETCH retrieves at most 500 rows in the example. The batch size of 500 is illustrative; choose based on memory, row size, latency, and rollback scope.

### 11.2. Bulk Insert with SAVE EXCEPTIONS

Inside the batch loop, you can execute:

```sql
FORALL i IN 1 .. l_source_ids.COUNT SAVE EXCEPTIONS
    INSERT INTO lab_target_items (
        source_id, item_code, quantity, item_name
    )
    VALUES (
        l_source_ids(i), l_codes(i), l_qty(i), l_names(i)
    );
```

If errors occur, handle ORA-24381 right inside the loop to record errors for the current batch before fetching the next batch. Do not let the next batch's SQL%BULK_EXCEPTIONS overwrite the context needed to handle the previous batch.

### 11.3. Accumulating Successful Row Counts

SQL%ROWCOUNT reflects only the most recent FORALL. Use an accumulator variable:

```sql
l_total_inserted := l_total_inserted + SQL%ROWCOUNT;
```

If a batch raises ORA-24381, capture SQL%ROWCOUNT inside the handler and add it to the total. Similarly, accumulate error counts from SQL%BULK_EXCEPTIONS.COUNT.

### 11.4. Preserving Mapping Across Chunked Fetches

ERROR_INDEX is only meaningful within the current FORALL batch. If you need the global source row across the whole file, store the source row number in a collection for that batch. Example:

```sql
l_source_row_no(i) := l_global_row_no;
```

When an error occurs, use the iteration index to look up l_source_row_no and log the original row number. That way the error log pinpoints the source line rather than only reporting iteration 17.

## 12. SAVE EXCEPTIONS and Transaction Policy

### 12.1. Partial Success

If the business allows valid rows to be kept, the workflow can:

1. Run FORALL SAVE EXCEPTIONS.
2. Capture successful row count and the error list.
3. Write errors to the error table.
4. Mark source records as succeeded/failed per the batch contract.
5. Caller COMMITs once batch status is completely recorded.
6. Retry failed rows after data is fixed.

The key point is that batch status and error logs must remain consistent with the successful rows.

### 12.2. All-or-Nothing

If the business requires the entire batch to succeed or no rows to be kept, use a SAVEPOINT before FORALL:

```sql
SAVEPOINT before_bulk_batch;

BEGIN
    FORALL i IN 1 .. l_values.COUNT SAVE EXCEPTIONS
        INSERT INTO lab_target (value_col)
        VALUES (l_values(i));

EXCEPTION
    WHEN e_bulk_errors THEN
        ROLLBACK TO before_bulk_batch;
        RAISE;
END;
```

ROLLBACK TO SAVEPOINT undoes the batch's changes after that marker. It does not roll back changes made before the SAVEPOINT. If you write error logs after the rollback, those logs belong to the remaining transaction; the caller still needs to decide whether to commit.

### 12.3. Partial Success Does Not Mean Row-by-Row Commit

SAVE EXCEPTIONS does not commit after each iteration. If the caller has not committed, successful rows are not yet committed. Do not say "saved/persisted" when they are only "affected by DML."

In batch reports, separate:

- attempted_count: number of inputs sent to FORALL.
- affected_count: total rows actually affected by DML.
- failed_iteration_count: number of failed iterations.
- zero_row_count: number of iterations that succeeded without affecting any rows (for UPDATE/DELETE).
- committed_count: number of rows retained after transaction commit, if the application has a reliable way to determine it.

### 12.4. Exceptions Do Not Auto-Rollback the Entire Transaction

SAVE EXCEPTIONS raises ORA-24381 but does not decide to roll back the transaction. If the exception escapes the procedure, the caller can roll back; if a handler catches it and does not re-raise, the transaction continues. Design a clear exception contract so the caller does not accidentally commit partial data unknowingly.

### 12.5. Do Not COMMIT Inside Each Iteration

Do not place COMMIT inside a function/procedure called per element of FORALL. FORALL executes a bulk DML statement; transaction boundaries should be managed by the caller or batch coordinator. Committing too frequently undermines the ability to roll back the whole batch and creates states that are hard to recover from.

## 13. Safely Retrying Failed Elements

### 13.1. Do Not Retry Blindly

Not all errors can be retried immediately:

| Error Category | Examples | Typical Handling |
| --- | --- | --- |
| Invalid data | ORA-02290, ORA-01400, ORA-12899 | Fix input or reject record |
| Duplicate | ORA-00001 | Check idempotency/business rules; do not retry as-is |
| Missing parent | ORA-02291 | Load parent first or wait for dependency |
| Locking/concurrency | Some deadlock/serialization/lock timeout errors | Bounded retry after confirming transaction safety |
| Privilege/object error | ORA-01031, invalid object | Fix configuration/deployment, do not retry repeatedly |

Specific error codes and retry policies depend on the workload. Retrying only makes sense when the cause is transient and the operation is idempotent or protected by a business key.

### 13.2. Idempotency Key

A batch may be re-run after a timeout or application failure. Use a source ID or batch ID with a unique constraint to prevent duplicate inserts on retry:

```sql
CREATE TABLE lab_import_target (
    source_record_id VARCHAR2(100) NOT NULL,
    payload_value    VARCHAR2(200),
    CONSTRAINT uq_lab_import_source UNIQUE (source_record_id)
);
```

A unique key helps detect that a record was already processed, though a duplicate does not by itself indicate whether old data matches new data. The application must define whether duplicates count as idempotent success, a conflict requiring investigation, or a versioned update.

### 13.3. Storing Retry State

The error log should include:

- Batch ID.
- Source record ID.
- Input version/hash if needed to detect whether data changed.
- Error code and error message.
- Status such as NEW, RETRY_READY, RETRIED, REJECTED, or equivalent.
- Retry count and last retry timestamp.

Do not store raw sensitive data in error messages if logs are broadly accessible; store reference keys and the details needed for traceability.

### 13.4. Bounding Retries

Set a maximum retry count, backoff, and stop condition. Permanent data errors such as CHECK violations will not resolve themselves on immediate re-runs. Infinite retries can stall batches, increase load, and generate repeated logs.

### 13.5. Retrying in Small Batches

After fixing failed inputs, you can gather only the failed records into a new collection and re-run FORALL. Do not re-run the entire batch if successful rows have already been committed, unless the DML is idempotent and duplicates are handled intentionally.

## 14. SAVE EXCEPTIONS vs. DML Error Logging (LOG ERRORS)

Oracle provides two different mechanisms for recording DML errors: PL/SQL bulk exception handling and SQL DML error logging.

### 14.1. SAVE EXCEPTIONS

- Used only with FORALL.
- Errors map back to iteration/input indices.
- Error codes can be read via SQL%BULK_EXCEPTIONS.
- Per-iteration row counts can be read via SQL%BULK_ROWCOUNT.
- Requires writing PL/SQL handlers and error persistence/retry logic.
- Fits well when inputs are in collections and you need to know the exact failing element.

### 14.2. LOG ERRORS

DML error logging allows certain row-level errors to be written into an error logging table while the statement continues processing other rows.

Create the error table:

```sql
BEGIN
    DBMS_ERRLOG.CREATE_ERROR_LOG(
        dml_table_name => 'LAB_TARGET_ITEMS',
        err_log_table_name => 'ERR$_LAB_TARGET_ITEMS'
    );
END;
/
```

Run DML:

```sql
INSERT INTO lab_target_items (
    item_id, item_code, quantity, item_name
)
SELECT
    item_id, item_code, quantity, item_name
FROM lab_source_items
LOG ERRORS INTO err$_lab_target_items ('BATCH-2026-01')
REJECT LIMIT UNLIMITED;
```

Then query the error table:

```sql
SELECT
    ora_err_number$,
    ora_err_mesg$,
    ora_err_tag$,
    item_id,
    item_code
FROM err$_lab_target_items
WHERE ora_err_tag$ = 'BATCH-2026-01';
```

Check the column names in the error table generated by DBMS_ERRLOG, as they depend on the target table's columns and Oracle version. Certain data types and error types are not supported for error logging this way.

### 14.3. Which Mechanism to Choose?

| Requirement | Usually Suitable Mechanism |
| --- | --- |
| Data is already in PL/SQL collections | FORALL SAVE EXCEPTIONS |
| Need error mapping by iteration and collection input | SAVE EXCEPTIONS |
| Large INSERT ... SELECT needing to skip supported row errors | LOG ERRORS |
| Need per-input retry control in PL/SQL | SAVE EXCEPTIONS |
| Need to log row-level errors directly inside SQL DML | LOG ERRORS |

The two mechanisms can serve similar workloads but do not completely replace each other. LOG ERRORS has limitations on error types and column types; SAVE EXCEPTIONS requires FORALL and PL/SQL collections.

### 14.4. Do Not Assume LOG ERRORS Catches Everything

Some statement-level errors, structural errors, parse errors, privilege errors, or cases excluded by Oracle are not converted into row errors in the log table. Consult the Oracle Database SQL Language Reference and DBMS_ERRLOG documentation for your exact release, DML type, and data types.

## 15. FORALL with UPDATE and DELETE

### 15.1. UPDATE with Some Failing Elements

Example updating balances:

```sql
DECLARE
    TYPE t_account_ids IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    TYPE t_amounts IS TABLE OF NUMBER INDEX BY PLS_INTEGER;

    l_ids t_account_ids;
    l_amounts t_amounts;

    e_bulk_errors EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_bulk_errors, -24381);
    l_total_rows PLS_INTEGER := 0;
BEGIN
    l_ids(1) := 10;
    l_ids(2) := 20;
    l_ids(3) := 30;

    l_amounts(1) := 100;
    l_amounts(2) := -50;
    l_amounts(3) := 200;

    FORALL i IN 1 .. l_ids.COUNT SAVE EXCEPTIONS
        UPDATE lab_accounts
        SET balance = balance + l_amounts(i)
        WHERE account_id = l_ids(i);

    l_total_rows := SQL%ROWCOUNT;
EXCEPTION
    WHEN e_bulk_errors THEN
        l_total_rows := SQL%ROWCOUNT;

        FOR i IN 1 .. l_ids.COUNT LOOP
            DBMS_OUTPUT.PUT_LINE(
                'Account ' || l_ids(i) ||
                ', affected rows=' || SQL%BULK_ROWCOUNT(i)
            );
        END LOOP;

        FOR j IN 1 .. SQL%BULK_EXCEPTIONS.COUNT LOOP
            DBMS_OUTPUT.PUT_LINE(
                'Failed input index=' ||
                SQL%BULK_EXCEPTIONS(j).ERROR_INDEX ||
                ', message=' ||
                SQLERRM(-SQL%BULK_EXCEPTIONS(j).ERROR_CODE)
            );
        END LOOP;
END;
/
```

The example assumes a constraint prohibiting negative balances. If an UPDATE matches an account but violates the constraint, that iteration can fail; if the account does not exist, the iteration can succeed with a row count of 0.

### 15.2. DELETE by ID List

```sql
FORALL i IN 1 .. l_order_ids.COUNT SAVE EXCEPTIONS
    DELETE FROM lab_orders
    WHERE order_id = l_order_ids(i);
```

If deleting an order is blocked by a foreign key, that iteration can fail and be collected. A non-existent ID has a row count of 0, not an error. Use SQL%BULK_ROWCOUNT to distinguish iterations affecting zero rows from failed iterations.

### 15.3. MERGE and SAVE EXCEPTIONS

FORALL supports a single DML statement, which can be MERGE if the syntax/version and bind collections are compatible. SAVE EXCEPTIONS applies to errors in each MERGE execution within FORALL. SQL%BULK_EXCEPTIONS only reports the iteration and error code; it does not separate INSERT vs. UPDATE counts for each MERGE. If you need per-branch counts, design separate auditing/action tracking.

## 16. FORALL with Dynamic SQL

FORALL can also be used with EXECUTE IMMEDIATE where syntax is supported. Keep the SQL statement stable and bind collections in the right positions:

```sql
FORALL i IN 1 .. l_ids.COUNT SAVE EXCEPTIONS
    EXECUTE IMMEDIATE
        'UPDATE lab_employees
         SET status = :1
         WHERE employee_id = :2'
    USING l_statuses(i), l_ids(i);
```

Per-iteration DML errors can be collected using SAVE EXCEPTIONS. Never concatenate untrusted input directly into SQL text; bind values and use whitelists/DBMS_ASSERT for identifiers.

When using complex dynamic SQL, debugging is harder because the SQL text is built at runtime. Log the statement template, batch ID, and input index for traceability. Ensure bind order matches placeholders.

## 17. Notes on Triggers, Constraints, and Data-Dependent Errors

### 17.1. Triggers Can Cause DML Iterations to Fail

INSERT/UPDATE inside FORALL still fires triggers according to Oracle rules. If a trigger raises an exception, the corresponding iteration can fail and be collected if the error falls under SAVE EXCEPTIONS.

Do not assume SAVE EXCEPTIONS isolates trigger side effects outside transaction semantics. Successful trigger actions belong to the transaction; when the caller rolls back, they roll back too unless the trigger/procedure intentionally uses an autonomous transaction.

### 17.2. Deferred Constraints

Constraints may be checked immediately or deferred until commit time depending on declaration and transaction state. If an error only surfaces at COMMIT due to a deferred constraint, it does not necessarily appear as an iteration error for SAVE EXCEPTIONS to collect.

SAVE EXCEPTIONS does not replace checking constraints and errors at the transaction commit boundary.

### 17.3. Errors That Cannot Be Fixed by Retrying

ORA-01400, ORA-02290, and ORA-12899 usually reflect invalid input data. Retrying the exact same input without fixing the data will keep failing. Classify errors to transition them to REJECTED or wait for the upstream data source to correct them.

### 17.4. Potentially Transient Errors

Some concurrency or resource errors may be transient. However, do not retry immediately inside the handler without considering transaction state, lock state, idempotency, and the risk of repeating side effects. Use bounded retries, backoff, and clear transaction boundaries.

## 18. Designing an Operable Batch Process

A reliable bulk DML batch typically follows these steps:

1. Generate a batch ID: uniquely identifies a run and data source.
2. Read data: fetch with a bounded batch size.
3. Normalize inputs: validate format, nulls, domains, and duplicates where possible.
4. Build collections: keep source keys and source row numbers in parallel.
5. Run FORALL SAVE EXCEPTIONS: bulk DML.
6. Capture metrics: total affected rows, error count, and unmatched iterations.
7. Persist error details: batch ID, input key, ERROR_CODE, ERROR_MESSAGE.
8. Update source status: mark records successful only when the transaction has been handled per contract.
9. Decide transaction outcome: commit partial success or roll back the batch per business rules.
10. Retry/reject: retry fixable errors; reject permanent data errors.
11. Reconcile: compare input count, success, failure, zero-row, and committed counts.

### 18.1. Metrics to Record

| Metric | Meaning |
| --- | --- |
| batch_id | Batch identifier |
| input_count | Number of inputs read |
| attempted_count | Number of iterations sent to FORALL |
| affected_count | Total rows affected by DML |
| failed_count | Number of iterations with errors |
| zero_row_count | Number of iterations affecting zero rows |
| elapsed_ms | Processing duration |
| retry_count | Number of inputs retried |
| final_status | SUCCESS, PARTIAL, FAILED, or equivalent status |

For an INSERT where one input maps to one target row, affected_count can equal attempted_count minus failed_count. For UPDATE/DELETE that can affect 0 or many rows, do not use that formula.

### 18.2. Batch Statuses

| Status | Condition |
| --- | --- |
| SUCCESS | No errors and all business conditions met |
| PARTIAL | Both successful rows and failed/unmatched rows per policy |
| FAILED | Batch rolled back or unable to continue |
| RETRY_PENDING | Contains transiently failed inputs awaiting reprocessing |
| REJECTED | Permanent input errors not eligible for retry |

Exact definitions vary by system. What matters is that batch status stays consistent with the transaction and error log.

## 19. Common Errors and How to Handle Them

| Symptom | Cause | Resolution |
| --- | --- | --- |
| FORALL stops on first error | SAVE EXCEPTIONS not used | Add SAVE EXCEPTIONS if remaining iterations should continue |
| Handler does not catch ORA-24381 | Exception mapping not declared or wrong code caught | PRAGMA EXCEPTION_INIT(e_bulk_errors, -24381) |
| ERROR_INDEX points to wrong input | Confusing error list position with collection index | Use ERROR_INDEX and bounds clause mapping |
| Only total row count visible, not per input | Only reading SQL%ROWCOUNT | Read SQL%BULK_ROWCOUNT(i) and SQL%BULK_EXCEPTIONS |
| SQL%ROWCOUNT changes after logging | Handler runs INSERT/UPDATE log before capturing | Save row count immediately upon entering handler |
| 0-row DML not in error list | No rows matched WHERE, not an exception | Check SQL%BULK_ROWCOUNT(i) = 0 |
| Partial batch reported as SUCCESS | Handler swallows ORA-24381 without returning status | Return PARTIAL status or re-raise |
| Successful rows disappear after rollback | Caller rolled back transaction | Distinguish DML affected from committed |
| Error logs also disappear | Same-transaction logs rolled back | Decide between same-transaction and independent logging |
| Retry creates duplicates | No idempotency key or processed-state check | Use source key/unique constraint and retry policy |
| FORALL fails on sparse collection | Using 1..COUNT on non-contiguous collection | Use INDICES OF or VALUES OF |
| Error table lacks source info | Storing only ERROR_CODE | Store batch ID, source key, row number, and input reference |
| Error only appears at COMMIT | Deferred constraint or transaction boundary error | Handle commit errors separately; SAVE EXCEPTIONS does not catch all errors |
| Repeated retries still fail | Cause is permanent bad data | Classify error and transition to REJECTED |

## 20. Best Practices

1. **Use SAVE EXCEPTIONS when you want remaining iterations to continue.** It is a deliberate choice for partial processing.
2. **Catch ORA-24381 properly.** Use PRAGMA EXCEPTION_INIT and keep a WHEN OTHERS handler for other errors.
3. **Read ERROR_INDEX, not the error list position as the input index.** Map according to the FORALL bounds clause.
4. **Record ERROR_CODE and message.** Call SQLERRM with the negative error code to build the message.
5. **Read SQL%BULK_ROWCOUNT for each iteration.** Distinguish errors from successful DML matching zero rows.
6. **Capture SQL%ROWCOUNT immediately in the handler.** Do not let log INSERT statements overwrite the total.
7. **Keep source keys and batch IDs.** Collection indices alone are insufficient to trace upstream data.
8. **Decide partial vs. all-or-nothing before running.** Use COMMIT/ROLLBACK/SAVEPOINT per contract.
9. **Never swallow ORA-24381.** The caller must know the batch had partial errors.
10. **Make retries bounded and idempotent.** Do not blindly retry permanent constraint errors.
11. **Fetch in batches using LIMIT.** Control PGA memory and transaction duration.
12. **Distinguish SAVE EXCEPTIONS from LOG ERRORS.** Choose based on data source, mapping needs, and error types.
13. **Check errors at the commit boundary.** Deferred constraints and transaction errors can surface after FORALL.
14. **Do not COMMIT inside every iteration.** Let the caller manage the transaction.
15. **Reconcile batch numbers.** Input, attempted, affected, failed, zero-row, and committed are distinct counts.

## 21. Hands-on Exercises

### Exercise 1 — Unique Violation

Create a table with a primary key on ID and use FORALL SAVE EXCEPTIONS to INSERT a collection containing duplicate IDs. Print:

- Total rows inserted.
- Number of failed iterations.
- ERROR_INDEX and ERROR_CODE of each error.
- Source ID that caused the error.

### Exercise 2 — Check Constraint

Add a CHECK constraint `quantity >= 0`. Feed a collection with both negative and positive quantities. Identify which iteration fails with ORA-02290; verify that valid iterations are still processed.

### Exercise 3 — 0-Row UPDATE

Use FORALL UPDATE over a list of IDs containing one non-existent ID. Read SQL%BULK_ROWCOUNT and explain why that ID does not appear in SQL%BULK_EXCEPTIONS.

### Exercise 4 — Sparse Collection

Create an associative array with subscripts 10, 20, and 50. Use INDICES OF and trigger a DML error. Capture ERROR_INDEX and map it back to the exact source record.

### Exercise 5 — Error Logging

Create an error table using DBMS_ERRLOG.CREATE_ERROR_LOG. Compare an INSERT ... SELECT using LOG ERRORS with FORALL SAVE EXCEPTIONS on the same dataset.

### Exercise 6 — Transaction Policy

Run a batch with 2 valid rows and 1 failing row. Try two scenarios:

1. COMMIT to keep successful rows and error logs.
2. ROLLBACK TO SAVEPOINT to cancel the entire batch.

Explain the state of the target table and error log after each scenario.

### Exercise 7 — Retry

Fix the inputs of the failed records, build a new collection containing only the failed items, and retry. Ensure no duplicate rows are inserted for records that succeeded in the first batch.

### Exercise 8 — Chunked Bulk Collect

Read 100,000 records from staging using BULK COLLECT LIMIT. For each batch, run FORALL SAVE EXCEPTIONS, accumulating affected count and error count. Reconcile total inputs against final counts.

## 22. Self-Check Questions

1. What overhead does FORALL solve compared to row-by-row DML?
2. What happens when default FORALL encounters a DML error?
3. How does SAVE EXCEPTIONS change iteration processing behavior?
4. Why does Oracle raise ORA-24381 after SAVE EXCEPTIONS?
5. How do you declare an exception for error code -24381?
6. What does SQL%BULK_EXCEPTIONS.COUNT represent?
7. What do ERROR_INDEX and ERROR_CODE mean?
8. Why must ERROR_CODE be negated when passed to SQLERRM?
9. How do SQL%BULK_ROWCOUNT(i) and SQL%ROWCOUNT after FORALL differ?
10. Is an UPDATE DML matching zero rows recorded in SQL%BULK_EXCEPTIONS?
11. Why can the iteration count differ from the affected row count?
12. With a sparse collection, why shouldn't you use 1..COUNT?
13. What roles do INDICES OF and VALUES OF play?
14. Why should source row numbers/business keys be kept alongside collections?
15. Does SAVE EXCEPTIONS automatically COMMIT successful iterations?
16. How do you roll back an entire batch while keeping changes made before the batch?
17. Why do same-transaction logs disappear when the caller rolls back?
18. When should an autonomous logger be used?
19. How does SAVE EXCEPTIONS differ from LOG ERRORS?
20. Why can a deferred constraint fail at COMMIT instead of inside FORALL?
21. Which errors should not be retried as-is?
22. Which fields are needed in an error log to support retries and reconciliation?

## 23. Mental Model

```text
FORALL ... SAVE EXCEPTIONS
          |
          v
    Try every iteration
          |
          +-- DML succeeds
          |      |
          |      +-- SQL%BULK_ROWCOUNT(i)
          |
          +-- DML fails
                 |
                 +-- Save ERROR_INDEX
                 +-- Save ERROR_CODE
          |
          v
    After completion
          |
          +-- Has errors -> ORA-24381
          |      |
          |      +-- SQL%BULK_EXCEPTIONS
          |      +-- SQLERRM(-ERROR_CODE)
          |      +-- Log / classify / retry
          |
          +-- No errors -> continue normally
          |
          v
    TRANSACTION POLICY
          |
          +-- COMMIT partial success if permitted
          +-- ROLLBACK TO SAVEPOINT if all-or-nothing
          +-- Caller decides final transaction outcome
```

**Key takeaway:** SAVE EXCEPTIONS lets FORALL continue past per-iteration DML errors and raises the aggregate error ORA-24381 upon completion. Use SQL%BULK_EXCEPTIONS to find failed inputs, SQL%BULK_ROWCOUNT to see how many rows each iteration affected, and SQL%ROWCOUNT for the total. Afterward, you must explicitly decide whether to keep partial success or roll back the entire batch; SAVE EXCEPTIONS does not auto-commit and does not replace a retry policy.
