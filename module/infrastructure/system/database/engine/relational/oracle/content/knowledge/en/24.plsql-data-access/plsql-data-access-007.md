# Row Locking with Cursor FOR UPDATE and WHERE CURRENT OF in PL/SQL

An order-processing workflow often needs to read a row, inspect its current state, and then update that very row. If an application runs a plain `SELECT` first, processes for a while, and runs an `UPDATE` later, another session could modify the row in the meantime. In that case, the program's decision would be based on stale data. Oracle provides **`SELECT ... FOR UPDATE`** to read and lock rows simultaneously, and **`WHERE CURRENT OF`** to `UPDATE` or `DELETE` the exact row at the cursor's current position.

In PL/SQL, a cursor declared with `FOR UPDATE` lets the program iterate through a locked set of rows. On each `FETCH`, the cursor is positioned on a row; an `UPDATE` or `DELETE` using `WHERE CURRENT OF cursor_name` operates on the current row without needing to pass the primary key or `ROWID` again. Row locks are held until the transaction issues `COMMIT` or `ROLLBACK`. Closing the cursor does not release the locks.

This lesson belongs to the **PL/SQL and Data** section of Database Engine Relational Oracle. It explains `FOR UPDATE` cursors, the `OF` clause, `WAIT`/`NOWAIT`/`SKIP LOCKED`, `WHERE CURRENT OF`, lock lifecycles, concurrency handling, deadlocks, and how to use locking cursors in safe data-update workflows.

After this lesson, you will be able to:

- Distinguish a standard read cursor from a `FOR UPDATE` cursor.
- Use `SELECT ... FOR UPDATE` to lock rows to be processed.
- Declare explicit cursors with `FOR UPDATE OF`.
- Choose `WAIT`, `NOWAIT`, or `SKIP LOCKED` according to your concurrency policy.
- Use `WHERE CURRENT OF` to `UPDATE`/`DELETE` the cursor's current row.
- Understand the difference between cursor position, row locks, and transaction boundaries.
- Avoid issuing `COMMIT` mid-fetch on a `FOR UPDATE` cursor.
- Design a worker queue with `SKIP LOCKED` when semantics allow.
- Handle lock errors, timeouts, and deadlocks.
- Recognize the limitations of `SELECT FOR UPDATE` in complex queries.

> **Example scope:** Syntax follows Oracle Database 19c. Tables suffixed with `_LAB` are intended for a practice schema. Test concurrency using two independent sessions. Never run locking experiments against production business tables.

## 1. Why lock rows when reading to update?

Suppose an application processes leave requests. It reads an employee's remaining balance, checks eligibility, and deducts the requested days. If two sessions both read the same balance before either updates, both may assume the request is valid.

~~~text
SESSION A                         SESSION B
---------                         ---------
SELECT balance = 5
                                  SELECT balance = 5
Check request 4 days
                                  Check request 4 days
UPDATE balance = 1
                                  UPDATE balance = 1
COMMIT
                                  COMMIT
~~~

This is a race condition in the read-then-write pattern. Results can become incorrect if the application writes back values computed from an outdated snapshot without conflict control.

One approach is to place the condition directly in the `UPDATE`:

~~~sql
UPDATE leave_balance_lab
SET remaining_days = remaining_days - :requested_days
WHERE employee_id = :employee_id
  AND remaining_days >= :requested_days;
~~~

Then check `SQL%ROWCOUNT`. For workflows that need to read multiple fields, check multiple conditions, or perform several operations based on the row being processed, `SELECT FOR UPDATE` is the appropriate tool:

~~~sql
SELECT remaining_days
FROM leave_balance_lab
WHERE employee_id = :employee_id
FOR UPDATE;
~~~

Oracle locks the selected row so other transactions cannot concurrently modify the same row until the current transaction ends.

## 2. Standard cursors vs. FOR UPDATE cursors

### 2.1. Standard read cursor

A standard cursor queries and fetches data under read consistency. It does not acquire row locks merely by reading rows:

~~~sql
DECLARE
    CURSOR c_employee IS
        SELECT employee_id, full_name, monthly_salary
        FROM employee_lock_lab
        WHERE department_id = 10;

    l_employee c_employee%ROWTYPE;
BEGIN
    OPEN c_employee;
    FETCH c_employee INTO l_employee;
    CLOSE c_employee;
END;
/
~~~

While the cursor reads, other sessions can still update those rows. A read cursor sees data consistent as of the query's snapshot; it does not promise that values stay unchanged until the program decides to `UPDATE`.

### 2.2. Cursor with FOR UPDATE

Add `FOR UPDATE` to the `SELECT` statement:

~~~sql
DECLARE
    CURSOR c_employee IS
        SELECT employee_id, full_name, monthly_salary
        FROM employee_lock_lab
        WHERE department_id = 10
        FOR UPDATE;
BEGIN
    OPEN c_employee;
    -- Rows in the result set are locked for the transaction.
    CLOSE c_employee;
    ROLLBACK;
END;
/
~~~

When a `FOR UPDATE` cursor is opened, Oracle locks the rows in the result set according to `SELECT FOR UPDATE` semantics. Other transactions trying to `UPDATE`/`DELETE` those locked rows must wait, or receive an error if the query specified `NOWAIT` or a `WAIT` timeout.

### 2.3. FOR UPDATE does not mean locking the entire table

`SELECT FOR UPDATE` locks the selected rows in the specified tables of the query. By default, it does not turn the `SELECT` into an exclusive table lock. Concurrent DML can still proceed on other rows as long as it does not conflict with the locked rows.

Oracle also uses table-level locks to coordinate DML/DDL; however, the purpose of `FOR UPDATE` here is to protect the selected rows.

### 2.4. When is a FOR UPDATE cursor useful?

- Reading a row and updating that same row under multiple business conditions.
- Iterating through pending rows and updating their status.
- Claiming a work item record so one worker takes ownership of processing it.
- Performing `UPDATE`/`DELETE` on the current row without reconstructing the predicate manually.
- Preventing another session from modifying the row between the read and write steps.

Do not use `FOR UPDATE` on every `SELECT`. Unnecessary locking increases blocking, reduces concurrency, and can cause deadlocks.

## 3. Declaring a cursor with FOR UPDATE

### 3.1. Basic syntax

Template:

~~~sql
CURSOR cursor_name IS
    select_statement
    FOR UPDATE [OF column_list]
    [NOWAIT | WAIT integer | SKIP LOCKED];
~~~

The `FOR UPDATE` clause belongs to the cursor's `SELECT` statement. Options:

- `FOR UPDATE`: locks selected rows in the relevant tables according to Oracle rules.
- `OF column_list`: identifies the table or tables whose rows should be locked via the listed columns.
- `NOWAIT`: if a row to be locked is held by another session, return an error immediately.
- `WAIT n`: wait up to `n` seconds to acquire the lock.
- `SKIP LOCKED`: skip rows currently locked by another transaction.

Do not combine `NOWAIT`, `WAIT`, and `SKIP LOCKED` simultaneously; pick the single policy appropriate for the query.

### 3.2. FOR UPDATE OF

Example of a cursor joining employees with departments:

~~~sql
DECLARE
    CURSOR c_employee IS
        SELECT
            e.employee_id,
            e.full_name,
            e.department_id,
            d.department_name
        FROM employee_lock_lab e
        JOIN department_lock_lab d
          ON d.department_id = e.department_id
        WHERE e.department_id = 10
        FOR UPDATE OF e.monthly_salary;
BEGIN
    OPEN c_employee;
    CLOSE c_employee;
    ROLLBACK;
END;
/
~~~

`OF e.monthly_salary` identifies `EMPLOYEE_LOCK_LAB` as the table whose rows should be locked. It does not mean only the `MONTHLY_SALARY` column is locked or that only that column can be updated. Row locks protect the entire row, not individual columns.

When a query joins multiple tables and only employee rows will be modified, `OF` clarifies which table to lock. If rows in multiple tables need modification, you can specify columns from each table using supported syntax.

### 3.3. OF does not require the column to be in the SELECT list

The `OF` list identifies the target table through the specified column. The column named in `OF` does not have to appear in the select list, as long as it is valid in the query and referenced with the proper alias.

### 3.4. FOR UPDATE in cursors declared in packages/procedures

A cursor can be declared in a PL/SQL block, procedure, or package body. What matters is that the cursor remains open and positioned on a row to use `WHERE CURRENT OF`. If consumers outside a package invoke a locking workflow, design a clear API; never obscure cursor or transaction ownership.

## 4. Opening the cursor, FETCH, and lock lifecycle

### 4.1. OPEN cursor FOR UPDATE

Example:

~~~sql
DECLARE
    CURSOR c_employee IS
        SELECT employee_id, monthly_salary
        FROM employee_lock_lab
        WHERE department_id = 10
        FOR UPDATE OF monthly_salary;
BEGIN
    OPEN c_employee;
    -- The cursor is open and result set rows are locked.
    CLOSE c_employee;
    ROLLBACK;
END;
/
~~~

`OPEN` starts cursor execution. With `FOR UPDATE`, Oracle acquires the necessary locks on rows in the result set. Exact timing and locking work depend on the execution plan and how the query executes; programmatically, treat the result row set as locked once requested.

### 4.2. FETCH positions the current row

After `FETCH`, the cursor has a current row. `WHERE CURRENT OF` uses this current position to identify the row to `UPDATE` or `DELETE`:

~~~sql
FETCH c_employee INTO l_employee;

UPDATE employee_lock_lab
SET monthly_salary = monthly_salary * 1.05
WHERE CURRENT OF c_employee;
~~~

There is no need to rewrite the predicate by primary key. `WHERE CURRENT OF` binds the DML operation to the row the cursor is currently positioned on.

### 4.3. CLOSE cursor does not release row locks

Closing the cursor only ends usage of the cursor and frees cursor resources. Row locks acquired by `SELECT FOR UPDATE` remain held until the transaction issues `COMMIT` or `ROLLBACK`.

~~~text
OPEN FOR UPDATE
      |
      v
FETCH / UPDATE CURRENT ROW
      |
      v
CLOSE CURSOR
      |
      | row locks remain held
      v
COMMIT or ROLLBACK
      |
      v
Release transaction locks
~~~

This is critical in operations. Never close a cursor and assume another session can immediately modify the row. To release locks, you must end the transaction.

### 4.4. COMMIT/ROLLBACK ends the transaction

- `COMMIT` confirms changes and releases transaction locks.
- `ROLLBACK` discards uncommitted changes and releases locks.
- `ROLLBACK TO SAVEPOINT` undoes changes after the savepoint per Oracle rules; the transaction remains open.

Do not keep a transaction open long after cursor processing finishes. Long transactions hold row locks longer and increase waiting for other sessions.

## 5. WHERE CURRENT OF

### 5.1. Meaning

`WHERE CURRENT OF cursor_name` specifies the current row of an open `FOR UPDATE` cursor. The `UPDATE` or `DELETE` statement operates on that exact row.

~~~sql
UPDATE table_name
SET column_name = expression
WHERE CURRENT OF cursor_name;
~~~

or:

~~~sql
DELETE FROM table_name
WHERE CURRENT OF cursor_name;
~~~

The cursor must be declared with `FOR UPDATE`, currently open, and fetched onto a valid current row. If the cursor is unopened, closed, or has no valid current row, the statement cannot use that position.

### 5.2. Updating the current row

~~~sql
DECLARE
    CURSOR c_employee IS
        SELECT employee_id, full_name, monthly_salary
        FROM employee_lock_lab
        WHERE department_id = 10
        FOR UPDATE OF monthly_salary;

    l_employee c_employee%ROWTYPE;
BEGIN
    OPEN c_employee;

    LOOP
        FETCH c_employee INTO l_employee;
        EXIT WHEN c_employee%NOTFOUND;

        UPDATE employee_lock_lab
        SET monthly_salary = monthly_salary * 1.05
        WHERE CURRENT OF c_employee;
    END LOOP;

    CLOSE c_employee;
    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        IF c_employee%ISOPEN THEN
            CLOSE c_employee;
        END IF;
        ROLLBACK;
        RAISE;
END;
/
~~~

This example gives a 5% raise to employees in department 10. The cursor selects and locks the rows; each `FETCH` positions on a row; `UPDATE ... WHERE CURRENT OF` updates the current row.

### 5.3. Deleting the current row

~~~sql
DECLARE
    CURSOR c_expired_job IS
        SELECT job_id, created_at
        FROM job_queue_lock_lab
        WHERE status = 'CANCELLED'
          AND created_at < SYSTIMESTAMP - INTERVAL '30' DAY
        FOR UPDATE OF status;

    l_job c_expired_job%ROWTYPE;
BEGIN
    OPEN c_expired_job;

    LOOP
        FETCH c_expired_job INTO l_job;
        EXIT WHEN c_expired_job%NOTFOUND;

        DELETE FROM job_queue_lock_lab
        WHERE CURRENT OF c_expired_job;
    END LOOP;

    CLOSE c_expired_job;
    COMMIT;
END;
/
~~~

`DELETE ... WHERE CURRENT OF` deletes the row currently pointed to by the cursor. After deleting the current row, continue calling `FETCH` to move to the next row.

### 5.4. UPDATE/DELETE without re-specifying the primary key

`WHERE CURRENT OF` is helpful when:

- The select list does not include the primary key.
- The cursor query contains joins or expressions.
- You want to avoid repeating predicates that might drift.
- You want to express clearly that the operation acts on the row currently processed by the cursor.

However, if business logic needs the primary key for auditing, logging, or APIs, still select that key into the record.

### 5.5. The DML target must match the cursor

With a multi-table join cursor, `FOR UPDATE OF e.salary` locks rows of the specified table. `WHERE CURRENT OF` is used to `UPDATE`/`DELETE` rows of the table identifiable through the cursor. If the cursor involves multiple tables or complex transformations, verify updatable-cursor rules and test the specific DML statement on your target release.

## 6. Cursor FOR LOOP and WHERE CURRENT OF

A cursor `FOR LOOP` automatically opens, fetches, and closes the cursor. It can be combined with `WHERE CURRENT OF`:

~~~sql
DECLARE
    CURSOR c_employee IS
        SELECT employee_id, full_name, monthly_salary
        FROM employee_lock_lab
        WHERE department_id = 20
        FOR UPDATE OF monthly_salary;
BEGIN
    FOR r_employee IN c_employee LOOP
        UPDATE employee_lock_lab
        SET monthly_salary = monthly_salary + 200
        WHERE CURRENT OF c_employee;
    END LOOP;

    COMMIT;
END;
/
~~~

Inside the loop, the cursor is open and currently positioned on the `r_employee` row. `WHERE CURRENT OF c_employee` targets that exact row.

### 6.1. Benefits of cursor FOR LOOP

- No need to declare a separate record variable.
- No manual `OPEN`/`FETCH`/`EXIT`/`CLOSE`.
- Concise and readable code.
- Oracle automatically closes the cursor when the loop finishes normally or exits scope.

### 6.2. Exception handling note

A cursor `FOR LOOP` manages the cursor lifecycle automatically. If an exception occurs, the cursor is closed upon exiting the loop scope. However, the transaction may still be open and holding locks. The exception handler must decide `COMMIT`/`ROLLBACK` according to the unit of work.

~~~sql
DECLARE
    CURSOR c_employee IS
        SELECT employee_id, monthly_salary
        FROM employee_lock_lab
        WHERE department_id = 20
        FOR UPDATE;
BEGIN
    FOR r IN c_employee LOOP
        UPDATE employee_lock_lab
        SET monthly_salary = monthly_salary + 200
        WHERE CURRENT OF c_employee;
    END LOOP;

    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
~~~

## 7. FOR UPDATE OF in JOIN queries

### 7.1. Locking only the table to be updated

Suppose a query reads employees and department names:

~~~sql
SELECT
    e.employee_id,
    e.full_name,
    e.department_id,
    d.department_name
FROM employee_lock_lab e
JOIN department_lock_lab d
  ON d.department_id = e.department_id
WHERE d.department_id = 10
FOR UPDATE OF e.monthly_salary;
~~~

`OF e.monthly_salary` requests locks on matching rows in `EMPLOYEE_LOCK_LAB`. `DEPARTMENT_LOCK_LAB` is only used for filtering and display; it is not designated for locking in this example.

### 7.2. Why use OF?

If a query joins multiple tables and omits `OF`, Oracle may lock rows across multiple tables in the result per `SELECT FOR UPDATE` rules. Specifying `OF` makes explicit which table the program intends to modify and avoids unnecessary locking.

### 7.3. The column in OF is not the only column allowed to be updated

`FOR UPDATE OF e.monthly_salary` does not restrict `UPDATE` to modifying only `MONTHLY_SALARY`. It identifies `EMPLOYEE_LOCK_LAB` for row locking. The `UPDATE` statement can still modify other columns of that row if privileges and DML rules permit.

### 7.4. Limitations of FOR UPDATE with complex queries

`SELECT FOR UPDATE` has limitations. Under Oracle rules, `FOR UPDATE` cannot be applied arbitrarily to queries containing constructs such as:

- `DISTINCT`.
- `GROUP BY`.
- Set operators such as `UNION`, `UNION ALL`, `INTERSECT`, `MINUS`.
- Aggregate functions or certain query blocks/expressions that do not map to physical rows to lock.
- Certain views or subqueries whose structure does not support direct locking.

When a query needs aggregation to make a decision, you usually must identify the source table/rows to lock via a separate appropriate query rather than trying to lock aggregated results.

Do not assume that because a complex `SELECT` compiles or runs, `FOR UPDATE` locks the intended business object. Check your release's SQL Language Reference and verify the row source/execution plan.

## 8. NOWAIT, WAIT, and SKIP LOCKED

These three options define behavior when a row to be locked is already held by another transaction.

### 8.1. Default: wait

If none of `NOWAIT`/`WAIT`/`SKIP LOCKED` is specified, the session waits until the lock is released. This works when short waits are acceptable, though applications must understand wait times can become long.

### 8.2. NOWAIT: do not wait

~~~sql
SELECT employee_id, full_name
FROM employee_lock_lab
WHERE employee_id = 101
FOR UPDATE NOWAIT;
~~~

If the row is locked, Oracle returns an error immediately—typically `ORA-00054` for resource busy with `NOWAIT`. The application can:

- Inform the user the record is currently being processed.
- Pick another work item.
- Retry with bounded backoff.
- Log the event to monitor contention.

`NOWAIT` fits interactive flows where users should not wait, or workers needing immediate feedback when a resource is busy.

### 8.3. WAIT n: wait up to n seconds

~~~sql
SELECT employee_id, full_name
FROM employee_lock_lab
WHERE employee_id = 101
FOR UPDATE WAIT 5;
~~~

The session waits up to 5 seconds to acquire the lock. If the timeout expires before the lock is released, Oracle raises a timeout error, typically `ORA-30006`. The `WAIT` value must be an integer number of seconds per Oracle syntax.

`WAIT` is useful when contention is usually brief but the application needs a bounded wait time.

### 8.4. SKIP LOCKED: skip rows currently locked

~~~sql
SELECT job_id, payload
FROM job_queue_lock_lab
WHERE status = 'READY'
FOR UPDATE SKIP LOCKED;
~~~

If a `READY` row is already locked by another session, the query skips that row and returns other unlocked rows. This is useful when multiple workers pull jobs concurrently from a queue.

`SKIP LOCKED` does not wait on busy rows and does not guarantee strict fairness. If the first row is held for a long time, other workers continue picking up later rows; processing semantics must tolerate this.

### 8.5. Comparison

| Option | Behavior when row is locked | Scenario |
| --- | --- | --- |
| Unspecified | Wait until lock is released | Waiting is acceptable |
| `NOWAIT` | Raise error immediately | Interactive flow needing instant feedback |
| `WAIT n` | Wait up to `n` seconds | Bounded waiting is acceptable |
| `SKIP LOCKED` | Skip busy rows, take other rows | Multi-consumer worker queue |

Do not choose `SKIP LOCKED` for business logic that must process one specific row, because skipping that row could mislead the caller into thinking no data exists to process.

## 9. Worker queue pattern with SKIP LOCKED

A multi-worker queue usually needs to ensure a single job is not processed simultaneously by two workers. `SKIP LOCKED` lets a worker claim rows not currently locked by another worker.

### 9.1. Lab queue table

~~~sql
CREATE TABLE job_queue_lock_lab (
    job_id NUMBER PRIMARY KEY,
    payload VARCHAR2(200),
    status VARCHAR2(12) NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    claimed_by VARCHAR2(30),
    claimed_at TIMESTAMP,
    CONSTRAINT ck_job_status_lock_lab
        CHECK (status IN ('READY', 'RUNNING', 'DONE', 'FAILED'))
);

INSERT INTO job_queue_lock_lab(job_id, payload, status)
VALUES (1, 'Send invoice', 'READY');

INSERT INTO job_queue_lock_lab(job_id, payload, status)
VALUES (2, 'Generate report', 'READY');

INSERT INTO job_queue_lock_lab(job_id, payload, status)
VALUES (3, 'Refresh cache', 'READY');

COMMIT;
~~~

### 9.2. Claiming a job

~~~sql
DECLARE
    CURSOR c_job IS
        SELECT job_id, payload
        FROM job_queue_lock_lab
        WHERE status = 'READY'
        ORDER BY created_at, job_id
        FOR UPDATE SKIP LOCKED;

    l_job c_job%ROWTYPE;
BEGIN
    OPEN c_job;
    FETCH c_job INTO l_job;

    IF c_job%FOUND THEN
        UPDATE job_queue_lock_lab
        SET status = 'RUNNING',
            claimed_by = 'WORKER_A',
            claimed_at = SYSTIMESTAMP
        WHERE CURRENT OF c_job;

        DBMS_OUTPUT.PUT_LINE(
            'Claimed job ' || l_job.job_id ||
            ': ' || l_job.payload
        );
    END IF;

    CLOSE c_job;
    COMMIT;
END;
/
~~~

Committing after updating status to `RUNNING` releases the lock. Other workers see the job is no longer `READY` and will not re-claim it under this query.

### 9.3. Separating claim and work execution

Do not hold a transaction or row lock while executing slow external work like calling APIs, sending emails, or processing files. The typical workflow is:

1. Open a short transaction.
2. `SELECT FOR UPDATE SKIP LOCKED` to claim a job.
3. Update status to `RUNNING`, worker ID, and timestamp.
4. `COMMIT` to release the lock.
5. Execute the work outside the transaction.
6. Open a new short transaction to update status to `DONE` or `FAILED`.

This model requires a timeout/lease mechanism to recover abandoned jobs if a worker crashes after claiming. `claimed_at` helps a job scheduler identify jobs stuck in `RUNNING` too long and route them into recovery.

### 9.4. Claiming multiple jobs in batches

You can combine `FETCH BULK COLLECT LIMIT` with a `FOR UPDATE SKIP LOCKED` cursor:

~~~sql
DECLARE
    CURSOR c_job IS
        SELECT job_id
        FROM job_queue_lock_lab
        WHERE status = 'READY'
        ORDER BY created_at, job_id
        FOR UPDATE SKIP LOCKED;

    TYPE job_id_tab IS TABLE OF job_queue_lock_lab.job_id%TYPE
        INDEX BY PLS_INTEGER;

    l_job_ids job_id_tab;
BEGIN
    OPEN c_job;

    FETCH c_job
    BULK COLLECT INTO l_job_ids
    LIMIT 20;

    FOR i IN 1 .. l_job_ids.COUNT LOOP
        UPDATE job_queue_lock_lab
        SET status = 'RUNNING',
            claimed_by = 'WORKER_BATCH',
            claimed_at = SYSTIMESTAMP
        WHERE job_id = l_job_ids(i);
    END LOOP;

    CLOSE c_job;
    COMMIT;
END;
/
~~~

In the batch example, DML uses `job_id` instead of `WHERE CURRENT OF` because the collection holds IDs after bulk fetching. The cursor still locks the fetched rows; the transaction commits after updating statuses. If row-by-row processing with `WHERE CURRENT OF` is needed, fetch one row at a time or adjust logic accordingly.

### 9.5. SKIP LOCKED does not automatically guarantee exactly-once processing

`SKIP LOCKED` prevents two workers from simultaneously claiming a row that is locked at that moment. It does not guarantee external work executes only once:

- A worker might commit `RUNNING` and crash before doing the work.
- A worker might finish an external API call and crash before updating `DONE`.
- A job might be retried after a lease timeout.

Consumers and external side effects still need idempotency keys, controlled retries, and recovery workflows.

## 10. Deadlocks and lock ordering

### 10.1. Cursor FOR UPDATE does not eliminate deadlocks

Two sessions can lock multiple rows in opposite order:

~~~text
Session A: lock row 1 -> request row 2
Session B: lock row 2 -> request row 1
                     |
                     v
                 ORA-00060
~~~

`FOR UPDATE` acquires locks; it does not automatically coordinate lock ordering across transactions.

### 10.2. Maintain a consistent lock order

If business logic needs to lock multiple accounts, lock them in ascending `account_id` order across every code path. If one transaction locks `CUSTOMER` then `ORDER`, other transactions must follow the same lock hierarchy.

### 10.3. Keep transactions short

- Never call REST APIs or send emails while holding row locks.
- Never wait on user input.
- Lock only the rows that genuinely need updating.
- `COMMIT`/`ROLLBACK` as soon as the unit of work finishes.
- Avoid opening a `FOR UPDATE` cursor over an overly broad set when only a few rows are needed.

### 10.4. Handling ORA-00060

When a deadlock occurs, Oracle rolls back the statement chosen to break the cycle. Earlier successful DML statements in the transaction may still remain pending. For business operations requiring atomicity, the application typically must `ROLLBACK` the entire transaction and then consider retrying the full unit of work.

Never simply catch the error and `COMMIT` earlier partial changes if the business operation is incomplete.

## 11. Committing while a FOR UPDATE cursor is still open

This is a common mistake in cursor loops.

### 11.1. Never COMMIT between FETCH calls

Example to avoid:

~~~sql
DECLARE
    CURSOR c_employee IS
        SELECT employee_id, monthly_salary
        FROM employee_lock_lab
        FOR UPDATE;
BEGIN
    FOR r IN c_employee LOOP
        UPDATE employee_lock_lab
        SET monthly_salary = monthly_salary + 100
        WHERE CURRENT OF c_employee;

        COMMIT;
    END LOOP;
END;
/
~~~

`COMMIT` ends the transaction and releases row locks. The `FOR UPDATE` cursor is no longer in a valid locked state to continue fetching; the next `FETCH` can raise `ORA-01002: fetch out of sequence`. This approach also breaks batch atomicity because each row is committed individually.

### 11.2. Commit after completing the cursor

Simple pattern:

~~~sql
BEGIN
    FOR r IN c_employee LOOP
        UPDATE employee_lock_lab
        SET monthly_salary = monthly_salary + 100
        WHERE CURRENT OF c_employee;
    END LOOP;

    COMMIT;
END;
/
~~~

If the dataset is too large and requires committing in batches, you cannot simply add `COMMIT` inside a `FOR UPDATE` cursor loop and continue fetching. Redesign the workflow into independent batches:

- Select a batch key range or batch ID.
- Open a new transaction for the batch.
- Claim/lock a subset of rows.
- Update the batch's status or data.
- Commit and close the cursor.
- Start the next batch with a fresh query.

Or use a queue with `SKIP LOCKED` so each worker claims an independent work batch. Each batch must be a business unit of work that can commit safely on its own.

### 11.3. CLOSE cursor does not replace COMMIT

Closing a cursor and opening a new one does not release row locks from the prior transaction. If other sessions must process the rows, the transaction must end. Conversely, committing while a `FOR UPDATE` cursor is still open can prevent further fetching. Coordinate the sequence properly: finish the cursor, close the cursor, then commit or roll back.

## 12. SELECT FOR UPDATE vs. optimistic concurrency

Not every update requires pessimistic row locking.

### 12.1. Pessimistic locking

`SELECT FOR UPDATE` locks before modifying. The transaction holds locks while checking and updating. Suitable when:

- Write conflicts happen frequently.
- The workflow needs to read state and execute multi-step decisions.
- Conditions cannot be expressed cleanly in a single DML statement.

### 12.2. Optimistic locking

You can use a `version_no` column:

~~~sql
UPDATE employee_lock_lab
SET monthly_salary = :new_salary,
    version_no = version_no + 1
WHERE employee_id = :employee_id
  AND version_no = :old_version;
~~~

If `SQL%ROWCOUNT = 0`, the row was modified or no longer exists. The application re-reads and decides whether to retry. This avoids holding row locks during client think time, at the cost of handling conflicts.

### 12.3. Conditional UPDATE

If the business rule needs only a simple check, you can perform it atomically:

~~~sql
UPDATE inventory_lock_lab
SET available_qty = available_qty - :requested_qty
WHERE product_id = :product_id
  AND available_qty >= :requested_qty;
~~~

Check `SQL%ROWCOUNT = 1` to confirm the update succeeded. This is often shorter and more efficient than `SELECT FOR UPDATE` followed by a separate `UPDATE` when no intermediate reads are needed.

### 12.4. Choosing a strategy

| Requirement | Approach to consider |
| --- | --- |
| Read multiple attributes then decide row updates | `SELECT FOR UPDATE` |
| Simple update condition expressible in `WHERE` | Conditional `UPDATE` |
| Client reads for a long time before submitting update | Optimistic version column |
| Multiple workers pulling independent jobs | `FOR UPDATE SKIP LOCKED` |
| Need to lock multiple rows | Consistent lock order and short transactions |

## 13. Limitations and caveats when using SELECT FOR UPDATE

### 13.1. Not usable with every query shape

`SELECT FOR UPDATE` has restrictions on queries containing `DISTINCT`, `GROUP BY`, aggregate functions, and set operators. Queries returning aggregated results do not map one-to-one to physical rows to lock.

If you need to lock source rows, split into:

1. Query identifying the business keys.
2. `SELECT FOR UPDATE` on the source table for those keys.
3. Verify latest state.
4. Perform DML and end the transaction.

### 13.2. Views and joins

Locking through views/joins depends on view updatability and key-preserved table rules. For join queries, use `FOR UPDATE OF` to identify the table to lock. Never assume every view or join supports `FOR UPDATE`.

### 13.3. A FOR UPDATE cursor requires proper transaction management

A `FOR UPDATE` cursor belongs to the current transaction. When using a connection pool, never return a connection to the pool while a transaction is still open. Ensure `COMMIT`/`ROLLBACK` completes before the connection is reused.

### 13.4. Do not lock too early

If a cursor is opened and the program then performs heavy computation, calls APIs, or waits for user input, row locks are held far too long. Complete non-locking steps first, then open the `FOR UPDATE` cursor for the shortest possible duration.

### 13.5. Avoid locking an unnecessarily large set

The broader the predicate, the more rows get locked. Use precise filters, proper indexes, and business-appropriate batch limits. Never open a `FOR UPDATE` cursor over an entire table just to process a few rows.

## 14. Diagnosing blocking and lock waits

When a session is waiting on a lock, DBAs can inspect sessions and blockers (requires privileges on dynamic performance views):

~~~sql
SELECT
    sid,
    serial#,
    username,
    event,
    blocking_session,
    seconds_in_wait,
    wait_class
FROM v$session
WHERE blocking_session IS NOT NULL;
~~~

You can inspect `TX`/`TM` enqueues:

~~~sql
SELECT
    s.sid,
    s.serial#,
    s.username,
    l.type,
    l.id1,
    l.id2,
    l.lmode,
    l.request,
    l.block
FROM v$lock l
JOIN v$session s
  ON s.sid = l.sid
WHERE l.type IN ('TX', 'TM')
  AND (l.request > 0 OR l.block = 1)
ORDER BY s.sid, l.type;
~~~

These views show state at query time. They do not replace understanding SQL and the transaction timeline. In RAC, consider `GV$SESSION`/`GV$LOCK` and instance IDs.

Common wait events include enqueues related to `TX`/`TM`. Inspect `blocking_session`, SQL ID, module/action, and transaction duration to identify the true blocker.

## 15. Two-session hands-on lab: observing FOR UPDATE

### 15.1. Create lab table

~~~sql
CREATE TABLE employee_lock_lab (
    employee_id NUMBER PRIMARY KEY,
    full_name VARCHAR2(80 CHAR) NOT NULL,
    department_id NUMBER NOT NULL,
    monthly_salary NUMBER(12,2) NOT NULL,
    version_no NUMBER DEFAULT 0 NOT NULL
);

INSERT INTO employee_lock_lab VALUES (101, 'Nguyen An', 10, 2500, 0);
INSERT INTO employee_lock_lab VALUES (102, 'Tran Binh', 10, 3200, 0);
INSERT INTO employee_lock_lab VALUES (103, 'Le Chi', 20, 2800, 0);
COMMIT;
~~~

### 15.2. Session A opens a FOR UPDATE cursor

To observe blocking, use an interactive session and leave the transaction open. For example, in Session A:

~~~sql
SELECT employee_id, full_name
FROM employee_lock_lab
WHERE employee_id = 101
FOR UPDATE;
~~~

Do not `COMMIT`/`ROLLBACK` immediately after the statement. Session A is now holding a lock on row 101.

### 15.3. Session B tries to update the same row

~~~sql
UPDATE employee_lock_lab
SET monthly_salary = monthly_salary + 100
WHERE employee_id = 101;
~~~

Session B will wait because Session A holds the row lock. Once Session A runs `COMMIT` or `ROLLBACK`, Session B can proceed.

### 15.4. Test NOWAIT

In Session A, hold the lock on row 101. In Session B, run:

~~~sql
SELECT employee_id, full_name
FROM employee_lock_lab
WHERE employee_id = 101
FOR UPDATE NOWAIT;
~~~

Session B receives an error immediately if the row is locked, without waiting for Session A to finish.

### 15.5. Test WAIT

~~~sql
SELECT employee_id, full_name
FROM employee_lock_lab
WHERE employee_id = 101
FOR UPDATE WAIT 3;
~~~

Session B waits up to three seconds.

### 15.6. Test WHERE CURRENT OF

~~~sql
DECLARE
    CURSOR c_employee IS
        SELECT employee_id, monthly_salary
        FROM employee_lock_lab
        WHERE employee_id IN (101, 102)
        ORDER BY employee_id
        FOR UPDATE;

    l_employee c_employee%ROWTYPE;
BEGIN
    OPEN c_employee;

    LOOP
        FETCH c_employee INTO l_employee;
        EXIT WHEN c_employee%NOTFOUND;

        UPDATE employee_lock_lab
        SET monthly_salary = monthly_salary + 50
        WHERE CURRENT OF c_employee;
    END LOOP;

    CLOSE c_employee;
    COMMIT;
END;
/
~~~

Verify results:

~~~sql
SELECT employee_id, monthly_salary
FROM employee_lock_lab
ORDER BY employee_id;
~~~

### 15.7. Clean up lab table

Run only after both sessions have ended their transactions:

~~~sql
DROP TABLE employee_lock_lab PURGE;
~~~

`DROP TABLE` is DDL with an implicit commit under Oracle rules. Run it only when you are sure this is your lab table.

## 16. Common errors

| Error/Symptom | Common cause | Resolution |
| --- | --- | --- |
| `ORA-00054` with `NOWAIT` | Row/resource locked by another session | Pick another row, report busy, or retry with limit |
| `ORA-30006` with `WAIT` timeout | Timed out waiting to acquire lock | Increase timeout if justified or address contention |
| `ORA-01002` fetch out of sequence | `COMMIT` or action invalidated `FOR UPDATE` cursor fetching | Do not commit mid-fetch; finish cursor before committing |
| `ORA-00060` | Deadlock between transactions | Roll back whole unit of work if atomicity is needed; fix lock order |
| `ORA-01001` invalid cursor | Using a closed or unopened cursor | Check `OPEN`/`CLOSE` and cursor scope |
| Cannot apply `FOR UPDATE` to query | Query uses `DISTINCT`/`GROUP BY`/aggregate/set ops or unsupported structure | Split query to identify source rows to lock |
| Workers process duplicate jobs | Claim was not properly committed or external effects are non-idempotent | Claim state inside transaction, add idempotency and lease recovery |
| Other session still waits after `CLOSE` | `CLOSE` does not release transaction row locks | `COMMIT`/`ROLLBACK` to release locks |

## 17. Common misconceptions

| Misconception | Reality |
| --- | --- |
| Standard `SELECT` locks rows | Standard `SELECT` uses read consistency and acquires no row locks like `FOR UPDATE` |
| `FOR UPDATE` locks the entire table | It locks only the selected rows in the specified tables |
| `OF salary` locks only the `salary` column | `OF` identifies the table via the column; the row lock protects the entire row |
| Closing the cursor releases row locks | Locks are held until `COMMIT`/`ROLLBACK` |
| `WHERE CURRENT OF` works with any cursor | The cursor must be an open `FOR UPDATE` cursor positioned on a current row |
| `WHERE CURRENT OF` requires `SELECT ROWID` | No manual `ROWID` is needed; cursor position identifies the row |
| `NOWAIT` and `WAIT` behave the same | `NOWAIT` errors immediately; `WAIT` waits up to the specified seconds |
| `SKIP LOCKED` fits every query | It skips busy rows, which can break logic requiring specific rows |
| Committing inside a cursor loop is a safe batching pattern | `FOR UPDATE` cursors can fail subsequent fetches and transaction atomicity is broken |
| `FOR UPDATE` prevents deadlocks | Opposite lock ordering still creates deadlocks |
| `FOR UPDATE` always works with `GROUP BY` | Aggregate/grouping query shapes have restrictions and cannot directly lock result rows that way |
| `SKIP LOCKED` guarantees exactly-once execution | Separate idempotency, claim state, and recovery are still required |

## 18. Checklist for safe FOR UPDATE cursor usage

Before deploying:

1. Is pre-update locking truly needed, or is a conditional `UPDATE` sufficient?
2. Does the cursor select only the necessary rows?
3. Is `FOR UPDATE OF` specified to lock only the right table in a `JOIN`?
4. Does `WAIT`/`NOWAIT`/`SKIP LOCKED` match UX and business semantics?
5. Is the cursor fetched properly with `%NOTFOUND` checked?
6. Does `WHERE CURRENT OF` reference the right open cursor?
7. Does the transaction finish promptly after processing?
8. Is there any `COMMIT` between `FETCH` calls? If so, redesign batching.
9. Do all flows locking multiple rows follow the same lock order?
10. Are `ORA-00054`, `ORA-30006`, and `ORA-00060` handled?
11. Does a worker queue have idempotency and lease recovery?
12. Does the connection pool receive connections back only after `COMMIT`/`ROLLBACK`?

## 19. Self-check questions

1. How does a regular `SELECT` differ from `SELECT FOR UPDATE`?
2. Which rows does a `FOR UPDATE` cursor lock?
3. What does `FOR UPDATE OF column` mean?
4. Does `OF column` restrict which columns can be updated?
5. Which statements use `WHERE CURRENT OF`?
6. What state must a cursor be in to use `WHERE CURRENT OF`?
7. Why do you not need to manually `SELECT ROWID` to use `WHERE CURRENT OF`?
8. Does `CLOSE` cursor release row locks?
9. What releases row locks?
10. How does `NOWAIT` differ from `WAIT n`?
11. Which pattern is `SKIP LOCKED` suited for?
12. Why does `SKIP LOCKED` not guarantee fairness?
13. Why should you not `COMMIT` between `FETCH` calls of a `FOR UPDATE` cursor?
14. Under what situation can `ORA-01002` occur?
15. Can `FOR UPDATE` be used with `GROUP BY`/`DISTINCT`/aggregates?
16. Why is `FOR UPDATE OF` useful in `JOIN` queries?
17. Does a `FOR UPDATE` cursor eliminate deadlocks?
18. When is a conditional `UPDATE` better than `SELECT FOR UPDATE`?
19. What mechanisms does a worker queue need besides `SKIP LOCKED`?
20. After `ORA-00060`, why is rolling back the whole transaction usually necessary?

**Answer hints:**

1. Regular `SELECT` reads a snapshot; `FOR UPDATE` reads and locks selected rows.
2. Rows belonging to the result set in the tables designated for locking.
3. Identifies the table containing that column so Oracle locks its matching rows.
4. No; row locks protect the row, not individual columns.
5. `UPDATE` or `DELETE`.
6. An open `FOR UPDATE` cursor that has fetched onto a current row.
7. Cursor position already identifies the target row for DML.
8. No.
9. `COMMIT` or `ROLLBACK` of the transaction.
10. `NOWAIT` errors immediately; `WAIT n` waits up to `n` seconds.
11. Multiple workers concurrently claiming jobs from a queue.
12. Locked rows are skipped; another worker may process later rows first.
13. `COMMIT` ends the transaction and the `FOR UPDATE` cursor may fail subsequent fetches; batch atomicity is broken.
14. When fetching a cursor out of sequence, especially after committing inside a `FOR UPDATE` cursor.
15. Those query shapes have restrictions and typically cannot lock source rows directly with `FOR UPDATE`.
16. To specify the table to lock in a join, avoiding locking rows in tables that do not need updating.
17. No; reversed lock orderings can still form a cycle.
18. When the business condition can be expressed atomically in the `UPDATE`'s `WHERE` clause.
19. Idempotency, claim status, lease timeout, and recovery.
20. Because only the deadlocked statement may be rolled back individually while earlier DML remains pending.

## Oracle Reference Documentation

- [Oracle Database PL/SQL Language Reference — Cursors Overview](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/cursors-overview.html): declaring, opening, fetching, and closing cursors.
- [Oracle Database SQL Language Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): `SELECT FOR UPDATE`, `OF`, `WAIT`, `NOWAIT`, and `SKIP LOCKED`.
- [Oracle Database PL/SQL Language Reference — UPDATE Statement](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/UPDATE-statement.html): `UPDATE` and `WHERE CURRENT OF`.
- [Oracle Database PL/SQL Language Reference — DELETE Statement](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/DELETE-statement.html): `DELETE` and `WHERE CURRENT OF`.
- [Oracle Database Concepts — Data Concurrency and Consistency](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/data-concurrency-and-consistency.html): row locks, transactions, and concurrency control.
- [Oracle Database Concepts — Transactions](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/transactions.html): transaction boundaries, commit, and rollback.

**Principle to remember:** A `FOR UPDATE` cursor locks rows the workflow is about to read for update; `FETCH` positions on the current row; `WHERE CURRENT OF` updates or deletes that exact row. Row locks persist until `COMMIT`/`ROLLBACK` rather than disappearing on `CLOSE` cursor. Lock only the right rows, keep transactions short, never `COMMIT` mid-fetch, and choose `NOWAIT`/`WAIT`/`SKIP LOCKED` according to business semantics.
