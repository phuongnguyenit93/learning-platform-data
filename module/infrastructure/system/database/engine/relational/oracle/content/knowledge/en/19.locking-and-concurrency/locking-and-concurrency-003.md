# SELECT FOR UPDATE and the Scope of Locked Rows in Oracle Database

## 1. Why lock rows before updating?

In a multi-user application, multiple sessions may concurrently read and modify the same record. A common workflow is:

1. Read the account balance.
2. Check whether the balance is sufficient.
3. Calculate the new balance in the application.
4. Write the new balance back to the database.

If two sessions both read a value before either updates it, both can make decisions based on the same stale state. One update can overwrite the result of the other.

Oracle automatically locks rows when performing UPDATE or DELETE. However, if the application needs to **read a row, hold that row unchanged during validation or computation, and then update it**, it can use **SELECT ... FOR UPDATE**.

SELECT FOR UPDATE is an explicit locking mechanism following pessimistic locking:

- Selects the rows to protect.
- Acquires exclusive row locks before subsequent DML executes.
- Other sessions cannot update, delete, or acquire conflicting locks on those rows until the current transaction ends.
- Other rows outside the result set can still be updated by other sessions.

The key point of this lesson is **the scope of locked rows**. This scope depends on the SELECT result set, the tables participating in JOINs, and the OF clause. Locking rows does not mean locking the entire table.

> Examples use Oracle Database 19c. Create lab tables in a dedicated schema and run with two independent database sessions to observe locking. Do not run long-lock tests in production.

## 2. SELECT FOR UPDATE syntax

Common syntax:

~~~sql
SELECT select_list
FROM   table_or_join
WHERE  condition
ORDER BY sort_expression
FOR UPDATE [OF column [, column ...]]
           [NOWAIT | WAIT integer | SKIP LOCKED];
~~~

Components:

| Component | Meaning |
| --- | --- |
| SELECT ... FROM ... WHERE ... | Determines the set of rows to read and lock |
| FOR UPDATE | Locks the selected rows from the tables in the query |
| OF column | Specifies which table or view has rows to lock in a JOIN query |
| NOWAIT | Do not wait if rows are locked; return control immediately |
| WAIT n | Wait up to n seconds to acquire the lock |
| SKIP LOCKED | Skip rows currently locked by another transaction |

Simple example:

~~~sql
SELECT account_id, balance
FROM   accounts
WHERE  account_id = 1001
FOR UPDATE;
~~~

Oracle acquires a lock on account row 1001 if that row is found. The lock persists until the current transaction COMMITs or ROLLBACKs.

SELECT FOR UPDATE does not modify data. It only acquires locks to protect rows before a subsequent UPDATE/DELETE statement executes.

## 3. Locking scope in a single table

### 3.1. WHERE determines which rows are selected

Suppose table ACCOUNT_BALANCE_LAB has multiple accounts:

~~~sql
SELECT account_id, balance
FROM account_balance_lab
WHERE account_id = 10
FOR UPDATE;
~~~

Only the row with ACCOUNT_ID = 10 is in the result set and locked.

If the predicate selects multiple rows:

~~~sql
SELECT account_id, balance
FROM account_balance_lab
WHERE branch_id = 3
FOR UPDATE;
~~~

All rows matching BRANCH_ID = 3 are locked. Accounts belonging to other branches are not in the result set and are not locked by this statement.

If WHERE is omitted:

~~~sql
SELECT account_id, balance
FROM account_balance_lab
FOR UPDATE;
~~~

The query selects every row in the table, and therefore can lock all selected rows. That is why you must be careful when running SELECT FOR UPDATE without a limiting predicate.

### 3.2. Locks only selected rows, not every scanned row

Logically, Oracle locks the rows belonging to the SELECT result set. An execution plan may read or inspect more rows than those that ultimately satisfy the predicate; you should not assume that every row the engine inspected while searching for matches remains locked.

Example:

~~~sql
SELECT order_id, status
FROM orders
WHERE customer_id = 100
  AND status = 'READY'
FOR UPDATE;
~~~

The goal is to lock customer 100's orders that are in READY status. Orders that are SHIPPED or belong to other customers are not in the result.

If the predicate can change because another session is updating data while SELECT FOR UPDATE runs, Oracle may have to acquire locks on unchanged rows, reconstruct a consistent result set, and restart lock acquisition for the remainder. Therefore, applications must handle ORA-00060 deadlocks if concurrent operations can alter the locked result set.

### 3.3. No rows selected means no row locks

~~~sql
SELECT account_id, balance
FROM account_balance_lab
WHERE account_id = -1
FOR UPDATE;
~~~

If there is no account -1, the SELECT returns zero rows and locks no rows.

This has an important consequence: SELECT FOR UPDATE does not lock an empty gap to prevent another session from INSERTing a new row that matches the predicate. Oracle does not use next-key/gap locking like some other database engines for this statement.

For example, if account ID 500 does not exist yet, two sessions both running SELECT FOR UPDATE with ACCOUNT_ID = 500 may both find zero rows. Not finding a row does not prevent another session from INSERTing ID 500 afterward.

To enforce uniqueness, use a PRIMARY KEY or UNIQUE constraint. Do not use SELECT FOR UPDATE on an empty set as a substitute for a constraint.

## 4. SELECT FOR UPDATE in a JOIN: which table is locked?

This is the most important part when determining locking scope.

### 4.1. Default: locks selected rows from every table in the query

Suppose a query JOINs EMPLOYEES and DEPARTMENTS:

~~~sql
SELECT e.employee_id,
       e.salary,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id
WHERE e.job_id = 'SA_REP'
  AND d.location_id = 2500
FOR UPDATE;
~~~

Without an OF clause, Oracle locks the selected rows from both EMPLOYEES and DEPARTMENTS. This can prevent another session from updating the related department row, even though the application only intends to edit employees.

### 4.2. Using OF to limit which table's rows are locked

If you only want to lock employee rows:

~~~sql
SELECT e.employee_id,
       e.salary,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id
WHERE e.job_id = 'SA_REP'
  AND d.location_id = 2500
FOR UPDATE OF e.salary;
~~~

Oracle locks the selected rows from EMPLOYEES; rows in DEPARTMENTS are not locked by this statement.

If you only want to lock departments:

~~~sql
SELECT e.employee_id,
       e.salary,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id
WHERE e.job_id = 'SA_REP'
  AND d.location_id = 2500
FOR UPDATE OF d.department_name;
~~~

Now the selected rows from DEPARTMENTS are the locking target.

### 4.3. OF column does not lock only a single column

The column name in OF is only used to identify which table or view has rows to lock. Oracle locks the **row** of that table, not solely the column listed after OF.

For example:

~~~sql
FOR UPDATE OF e.salary
~~~

does not mean only the SALARY column is locked while other columns in the row can still be updated independently. The employee's row is locked; another session cannot update a different column of that same row until the lock is released.

Which column name you specify in OF does not restrict locking to that column; you must use a real column name, not a SELECT-list expression alias. Explicitly include the table alias such as e.salary so readers know which table is locked.

### 4.4. Multiple tables can be specified

In a JOIN query, you can specify columns belonging to each table you want to lock:

~~~sql
SELECT e.employee_id,
       d.department_id
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id
WHERE e.employee_id = 100
FOR UPDATE OF e.salary, d.department_name;
~~~

The selected rows from both tables are locked. Each column in the list designates its corresponding table; it does not restrict the lock to that specific column.

### 4.5. Locking scope comparison table

| Statement | Table whose rows are locked |
| --- | --- |
| Two-table JOIN, FOR UPDATE | Selected rows from both tables |
| Two-table JOIN, FOR UPDATE OF e.salary | Selected rows from EMPLOYEES |
| Two-table JOIN, FOR UPDATE OF d.department_name | Selected rows from DEPARTMENTS |
| Two-table JOIN, FOR UPDATE OF e.salary, d.department_name | Selected rows from both tables |

Do not use OF as a filter predicate. The WHERE clause determines which rows are selected; OF determines which table's rows in the result set are locked.

## 5. Row locks vs. full-table locks

SELECT FOR UPDATE acquires exclusive row locks on the selected rows. Oracle also manages table-level locks to protect DML operations, but this statement does not acquire an exclusive table lock on the entire table.

In practice:

- Other sessions can run regular SELECT on those same rows and read the committed version via Oracle's read consistency mechanism.
- Other sessions wanting to UPDATE or DELETE a locked row must wait for the lock-holding transaction to end.
- Other sessions can still update other unlocked rows in the same table.
- Other sessions cannot acquire a conflicting lock on the same row using SELECT FOR UPDATE.

For example, A locks account 10. B can update account 20, but when B updates account 10, it must wait for A to end its transaction.

This is why row-level locking supports much higher transaction concurrency than locking the entire table. If a query locks hundreds of thousands of rows, that benefit diminishes and the design should be re-evaluated.

## 6. How long do locks exist?

### 6.1. COMMIT releases locks

~~~sql
SELECT account_id, balance
FROM account_balance_lab
WHERE account_id = 10
FOR UPDATE;

UPDATE account_balance_lab
SET balance = balance - 100
WHERE account_id = 10;

COMMIT;
~~~

After COMMIT, the transaction's row locks are released. Other sessions can proceed to lock or update those rows.

### 6.2. ROLLBACK also releases locks

~~~sql
SELECT account_id, balance
FROM account_balance_lab
WHERE account_id = 10
FOR UPDATE;

-- After checking, decide not to make any change.
ROLLBACK;
~~~

ROLLBACK ends the transaction and releases the locks. If the transaction performed DML, its changes are also undone.

### 6.3. ROLLBACK TO SAVEPOINT

Oracle can release row locks acquired after a savepoint when rolling back to that savepoint. Locks acquired before the savepoint still belong to the transaction and remain held.

~~~sql
SAVEPOINT before_lock;

SELECT account_id
FROM account_balance_lab
WHERE account_id = 10
FOR UPDATE;

ROLLBACK TO before_lock;
~~~

After rolling back to the savepoint, the lock acquired after the savepoint is released. The transaction remains active.

### 6.4. Closing a cursor does not release row locks

If SELECT FOR UPDATE is executed via an explicit cursor, running CLOSE on the cursor does not end the transaction and does not automatically release row locks. Locks persist until COMMIT, ROLLBACK, or an appropriate rollback to savepoint.

Therefore, never use closing a cursor as a substitute for ending a transaction.

## 7. NOWAIT, WAIT, and SKIP LOCKED

When a row to be locked is currently held by another session, Oracle needs to know whether the current session should wait, raise an error, or skip that row.

### 7.1. Default: wait until the lock is acquired

~~~sql
SELECT account_id, balance
FROM account_balance_lab
WHERE account_id = 10
FOR UPDATE;
~~~

If the row is already locked by another session, the statement waits until the lock is released. When the other session runs COMMIT or ROLLBACK, Oracle proceeds with acquiring the lock.

### 7.2. NOWAIT: do not wait

~~~sql
SELECT account_id, balance
FROM account_balance_lab
WHERE account_id = 10
FOR UPDATE NOWAIT;
~~~

If the row is currently locked, Oracle returns an error immediately, typically:

~~~text
ORA-00054: resource busy and acquire with NOWAIT specified
~~~

The application can inform the user that the record is being processed by someone else, or retry later according to policy.

NOWAIT fits interactive interfaces needing fast feedback without making users wait on an indeterminate lock.

### 7.3. WAIT n: wait for a bounded duration

~~~sql
SELECT account_id, balance
FROM account_balance_lab
WHERE account_id = 10
FOR UPDATE WAIT 5;
~~~

Oracle waits up to 5 seconds to acquire the lock. If the time expires while the row is still locked, you may receive:

~~~text
ORA-30006: resource busy; acquire with WAIT timeout expired
~~~

The value after WAIT is an integer number of seconds in Oracle 19c syntax. Choose the wait duration according to the application's SLA; do not set it excessively long just to mask a hung transaction.

### 7.4. SKIP LOCKED: skip rows currently locked

~~~sql
SELECT job_id, payload
FROM job_queue
WHERE status = 'READY'
FOR UPDATE SKIP LOCKED;
~~~

If some READY rows are already locked by other sessions, Oracle skips them and attempts to acquire unlocked rows. This mechanism fits multiple workers pulling work from a queue.

SKIP LOCKED does not mean the locked row has disappeared or become invalid. It is simply skipped during the current fetch; another worker may be processing it.

### 7.5. Comparing the three options

| Option | Row already locked | Suitable scenario |
| --- | --- | --- |
| Default | Waits until the row is available | Workflow requires that exact row and tolerates waiting |
| NOWAIT | Returns an error immediately | UI needing immediate feedback |
| WAIT n | Waits up to n seconds, then errors | Bounded wait time acceptable |
| SKIP LOCKED | Skips locked rows | Multi-worker queue, parallel processing |

### 7.6. Note when a table is locked in EXCLUSIVE mode

If a table is locked by another session in EXCLUSIVE mode, WAIT or SKIP LOCKED does not guarantee that SELECT FOR UPDATE returns immediately. Oracle may have to wait until that table lock is released; WAIT is not a timeout for every form of table-level blocking.

SKIP LOCKED only handles skipping contested row locks by design. Do not treat it as a mechanism to bypass all lock types or all database-busy states.

## 8. Cursor FOR UPDATE and WHERE CURRENT OF in PL/SQL

SELECT FOR UPDATE is often used when you want to iterate over a set of rows, read each row, and update or delete that exact current row.

### 8.1. Declaring a FOR UPDATE cursor

~~~sql
DECLARE
    CURSOR c_emp (p_department_id NUMBER) IS
        SELECT employee_id, salary
        FROM employees
        WHERE department_id = p_department_id
        FOR UPDATE OF salary;

    l_employee_id employees.employee_id%TYPE;
    l_salary      employees.salary%TYPE;
BEGIN
    OPEN c_emp(50);

    LOOP
        FETCH c_emp INTO l_employee_id, l_salary;
        EXIT WHEN c_emp%NOTFOUND;

        UPDATE employees
        SET salary = l_salary * 1.05
        WHERE CURRENT OF c_emp;
    END LOOP;

    CLOSE c_emp;
    COMMIT;
END;
/
~~~

FOR UPDATE OF salary specifies that EMPLOYEES rows are locked. WHERE CURRENT OF c_emp updates the cursor's current row without rewriting the primary key condition.

### 8.2. WHERE CURRENT OF

WHERE CURRENT OF is a PL/SQL extension for UPDATE and DELETE. It references the row most recently FETCHed from an explicit FOR UPDATE cursor.

Example of deleting the current row:

~~~sql
DELETE FROM employees
WHERE CURRENT OF c_emp;
~~~

Only a cursor declared with FOR UPDATE can be used in CURRENT OF.

### 8.3. When are rows locked?

With a regular FOR UPDATE cursor, Oracle locks the rows in the result set when the cursor is OPENed, before the first FETCH. Locking does not wait until the application fetches each row.

This means:

- A cursor returning 10,000 rows may acquire locks on all 10,000 rows immediately upon OPEN.
- The application may have only FETCHed 1 row, yet the remaining rows in the result set are already locked.
- CLOSE cursor does not release row locks.
- Only COMMIT or ROLLBACK releases the locks.

Therefore, avoid opening a FOR UPDATE cursor on a large result set if you only intend to process a few rows.

### 8.4. Do not COMMIT inside a FETCH loop

After COMMIT or ROLLBACK, row locks are released. An already open FOR UPDATE cursor cannot continue FETCHing; Oracle may raise:

~~~text
ORA-01002: fetch out of sequence
~~~

Anti-pattern to avoid:

~~~sql
LOOP
    FETCH c_emp INTO ...;
    EXIT WHEN c_emp%NOTFOUND;

    UPDATE employees
    SET salary = salary * 1.05
    WHERE CURRENT OF c_emp;

    COMMIT; -- Do not commit inside a FOR UPDATE cursor FETCH loop.
END LOOP;
~~~

Define transaction boundaries before opening the cursor. If you need to process in batches and commit per batch, design a separate batch-fetching approach rather than committing and continuing to fetch from the same FOR UPDATE cursor.

## 9. SKIP LOCKED in cursors: a different locking time

There is a special distinction:

- A regular FOR UPDATE cursor locks the rows in the result set at OPEN.
- A FOR UPDATE cursor with SKIP LOCKED acquires locks during the FETCH phase; rows currently locked by other sessions are skipped during fetch.

This lets multiple consumers read from a queue without waiting on one another. Each consumer receives rows that can still be locked.

Example of a worker claiming one job:

~~~sql
DECLARE
    CURSOR c_ready IS
        SELECT job_id, payload
        FROM job_queue
        WHERE status = 'READY'
        ORDER BY priority DESC, created_at, job_id
        FOR UPDATE SKIP LOCKED;

    l_job_id job_queue.job_id%TYPE;
    l_payload job_queue.payload%TYPE;
BEGIN
    OPEN c_ready;
    FETCH c_ready INTO l_job_id, l_payload;

    IF c_ready%FOUND THEN
        UPDATE job_queue
        SET status = 'PROCESSING',
            started_at = SYSTIMESTAMP
        WHERE CURRENT OF c_ready;
    END IF;

    CLOSE c_ready;
    COMMIT;

    -- After COMMIT, process payload outside the locking transaction.
    IF l_job_id IS NOT NULL THEN
        process_job(l_job_id, l_payload);
    END IF;
END;
/
~~~

In the example:

1. The cursor searches for READY rows in priority order.
2. The first FETCH retrieves one row not locked by another worker.
3. WHERE CURRENT OF transitions that row to PROCESSING.
4. CLOSE cursor and COMMIT release the row lock.
5. The worker processes the payload after recording the PROCESSING status.

This is an illustrative skeleton. Production applications need error handling inside PROCESS_JOB, recording FAILED or RETRY status, and a mechanism to recover abandoned PROCESSING jobs if a worker crashes after COMMIT.

### 9.1. Lease or timeout to recover jobs

If a worker COMMITs PROCESSING status and then terminates abruptly, the row is no longer locked yet still carries PROCESSING status. A durable queue mechanism typically needs:

- started_at or lease_until.
- Retry counter attempt_count.
- Statuses FAILED/READY/PROCESSING/DONE.
- A recovery process for jobs whose lease has expired.
- Idempotent processing so retries do not produce duplicate side effects.

SKIP LOCKED distributes rows across workers; it does not by itself build a retry system or guarantee that a job produces side effects exactly once.

### 9.2. Do not use SKIP LOCKED when a complete result is required

If the question is "list all open orders," SKIP LOCKED may omit orders currently locked by other sessions. The result is then no longer the full set of open orders.

Only use SKIP LOCKED when business logic accepts that rows currently being processed by another worker will be picked up later.

## 10. SELECT FOR UPDATE and read consistency

Oracle supports consistent reads for regular SELECT statements using undo. Thus, SELECT normally does not need to wait for a writer just to read a committed version.

SELECT FOR UPDATE has a different purpose:

- Read rows.
- Place locks to protect rows from conflicting changes.
- Allow the current transaction to perform DML after validation.

Example:

~~~sql
-- Regular SELECT: reads snapshot, does not lock row for update.
SELECT balance
FROM account_balance_lab
WHERE account_id = 10;

-- SELECT FOR UPDATE: reads and locks the row.
SELECT balance
FROM account_balance_lab
WHERE account_id = 10
FOR UPDATE;
~~~

Other sessions can still run regular SELECT on the locked row and read a committed version matching their snapshot. However, UPDATE/DELETE on the same row must wait for the lock.

Do not use SELECT FOR UPDATE just to produce consistent reports. If multiple queries need the same snapshot, consider READ ONLY transactions, SERIALIZABLE transactions, or Flashback Query AS OF SCN.

## 11. SELECT FOR UPDATE vs. atomic UPDATE statements

Not every problem requires SELECT FOR UPDATE.

### 11.1. When a single UPDATE is enough

Example of deducting balance if sufficient:

~~~sql
UPDATE account_balance_lab
SET balance = balance - :amount
WHERE account_id = :account_id
  AND balance >= :amount;
~~~

Check the number of affected rows:

~~~plsql
IF SQL%ROWCOUNT = 1 THEN
    -- Transaction deducted funds successfully.
ELSE
    -- Account does not exist or balance is insufficient.
    NULL;
END IF;
~~~

The predicate BALANCE >= :amount and the subtraction are in the same statement. Oracle automatically locks the row during UPDATE. This is usually the simplest and safest way to conditionally update a value.

### 11.2. When SELECT FOR UPDATE is needed

Use SELECT FOR UPDATE if:

- You must read multiple columns to decide on a multi-step workflow.
- You must inspect a state and then execute multiple related DML statements.
- You need to keep a parent row stable while validating and updating child rows.
- The application has an edit screen for a record and needs to prevent others from editing the same row while the user acts, with appropriately managed transactions.

Example:

~~~sql
SELECT status, available_quantity, reserved_quantity
FROM inventory
WHERE product_id = :product_id
FOR UPDATE;
~~~

The application reads the status and calculates the reservable amount, then updates the relevant columns within the same transaction.

### 11.3. Keep transactions short

You should never lock a row and then:

- Wait several minutes for a user to fill out a form.
- Call an external payment API.
- Send an email or perform long network tasks.
- Wait on another unrelated process.

These actions prolong lock hold times, cause other sessions to wait, and increase the risk of deadlocks or timeouts. Prepare data beforehand, open the transaction right before the protected operation, lock the rows, validate, update, and COMMIT/ROLLBACK quickly.

## 12. SELECT FOR UPDATE does not lock non-existent rows or predicate ranges

This is an important limitation when designing business rules.

Suppose an application wants to ensure each customer has at most one OPEN order:

~~~sql
SELECT order_id
FROM orders
WHERE customer_id = 100
  AND status = 'OPEN'
FOR UPDATE;
~~~

If there is currently no OPEN order, the SELECT locks no rows. Two sessions running the same statement can both get zero rows, and then both INSERT an OPEN order.

SELECT FOR UPDATE does not lock index gaps to block INSERTs. Therefore, it cannot be used alone to guarantee "no other row matches the predicate."

Appropriate safeguards:

- Use a unique constraint if the rule can be expressed through uniqueness.
- Lock a parent row that always exists, such as the CUSTOMER row, before checking and creating the order.
- Use a SERIALIZABLE transaction if business semantics require it and the application handles ORA-08177.
- Design a status or reservation table with a unique key.

Example of locking an always-existing customer row before checking orders:

~~~sql
SELECT customer_id
FROM customers
WHERE customer_id = 100
FOR UPDATE;

SELECT order_id
FROM orders
WHERE customer_id = 100
  AND status = 'OPEN';

-- Validate and INSERT within the same transaction.
~~~

Every code path creating an OPEN order must follow the same rule of locking the CUSTOMER row. If one program bypasses locking the parent row, this concurrency rule is no longer guaranteed.

## 13. Limitations of SELECT FOR UPDATE in Oracle 19c

According to the 19c SQL Language Reference, keep these limitations in mind:

### 13.1. Only valid in top-level SELECT

FOR UPDATE can only be specified in a top-level SELECT, not inside a subquery:

~~~sql
-- Conceptually invalid:
SELECT *
FROM employees
WHERE employee_id IN (
    SELECT employee_id
    FROM employee_requests
    FOR UPDATE
);
~~~

### 13.2. Cannot be combined with certain query constructs

FOR UPDATE cannot be used with:

- DISTINCT.
- CURSOR expressions.
- Set operators such as UNION, INTERSECT, MINUS.
- GROUP BY.
- Aggregate functions.

The general reason is that such constructs can produce aggregated or transformed results where Oracle cannot identify the underlying base rows to lock as requested.

### 13.3. Cannot be combined with FETCH FIRST / row limiting clause

In Oracle 19c, the row limiting clause cannot be used together with FOR UPDATE:

~~~sql
-- Invalid in Oracle 19c:
SELECT job_id
FROM job_queue
WHERE status = 'READY'
ORDER BY created_at
FETCH FIRST 10 ROWS ONLY
FOR UPDATE SKIP LOCKED;
~~~

If you need to pull rows one by one from a queue, you can use an explicit cursor with FETCH and SKIP LOCKED as shown earlier. Do not copy regular SELECT's FETCH FIRST syntax into SELECT FOR UPDATE on Oracle 19c.

### 13.4. Views

In general, FOR UPDATE is not supported directly on views. Some queries against views may succeed if the optimizer merges the view into the outer query block, but behavior depends on view structure and transformations.

Oracle recommends avoiding FOR UPDATE on views due to the complexity of view merging. If you need to lock rows, query the base table directly or explicitly verify updatability and the execution plan in your real environment.

### 13.5. Other limitations

- Tables locked in the statement must reside in the same database.
- Nested table rows are not automatically locked when only the parent table row is locked; if needed, lock nested table rows separately.
- For LOB data, you must lock the row containing the LOB before updating the LOB as required by Oracle.
- In tables using Hybrid Columnar Compression, certain DML operations may lock a compression unit rather than individual rows in the conventional logical sense.

## 14. Deadlocks and locking order

A deadlock occurs when two transactions hold locks needed by the other, creating a wait cycle.

Example:

~~~text
Session A                         Session B
---------                         ---------
Locks account 10
                                  Locks account 20
Wants to lock account 20
                                  Wants to lock account 10
        |                                  |
        +--------- wait cycle -------------+
~~~

Oracle detects the deadlock and selects one statement to abort, typically reporting:

~~~text
ORA-00060: deadlock detected while waiting for resource
~~~

The transaction must handle the error and decide on an appropriate ROLLBACK. Do not simply retry the failed statement while ignoring the state of prior steps.

To reduce deadlocks:

1. Lock multiple rows in the same business order across all code paths.
2. Keep transactions short.
3. Lock only the rows truly needed.
4. Avoid calling external services while holding row locks.
5. Catch and log ORA-00060; implement bounded retries with backoff if business logic allows.

ORDER BY can clarify the desired ordering of the result set, but it should not be relied upon alone as an absolute guarantee of internal locking order across every execution plan. Consistent locking rules must be designed across all competing transactions.

## 15. Common errors

| Error / Symptom | Cause | Resolution |
| --- | --- | --- |
| ORA-00054 | NOWAIT used while row/table resource is busy | Report busy or retry according to policy |
| ORA-30006 | WAIT n timed out | Inspect lock-holding transaction, adjust timeout with justification |
| ORA-00060 | Two transactions acquire locks in an order causing a cycle | Standardize locking order, controlled rollback/retry |
| ORA-01002 | FETCH on a FOR UPDATE cursor after COMMIT/ROLLBACK | Do not commit inside fetch loop; close cursor/transaction in proper order |
| ORA-02014 | FOR UPDATE on an unmergeable view or unsupported view construct | Query base tables; avoid locking complex views |
| Rows in JOINed table locked unexpectedly | Omitted OF, so Oracle locked rows from all selected tables | Specify FOR UPDATE OF alias.column |
| Another session can still read a locked row | Regular SELECT uses consistent read without row locks | This is normal behavior |
| Another session cannot update a row | Row is held by a transaction with FOR UPDATE | Wait for COMMIT/ROLLBACK or handle timeout |
| Query locks nothing | WHERE returns no rows | Check predicate; remember SELECT FOR UPDATE does not lock gaps |
| Many rows locked even though only one was FETCHed | Regular FOR UPDATE cursors usually lock the result set at OPEN | Narrow query; use SKIP LOCKED cursor when appropriate |
| Queue skips some jobs | Jobs are locked by another worker or no longer match condition | Re-read later; have recovery/lease for abandoned jobs |

## 16. Self-contained lab dataset

This section creates a balance table to test locking between two sessions. Run only in a lab schema.

### 16.1. Create table and data

~~~sql
CREATE TABLE account_balance_lab (
    account_id NUMBER PRIMARY KEY,
    branch_id  NUMBER NOT NULL,
    balance    NUMBER(12,2) NOT NULL
);

INSERT INTO account_balance_lab VALUES (10, 1, 1000);
INSERT INTO account_balance_lab VALUES (20, 1, 2000);
INSERT INTO account_balance_lab VALUES (30, 2, 3000);
COMMIT;
~~~

### 16.2. Lab A — Lock a single row

Session A:

~~~sql
SELECT account_id, balance
FROM account_balance_lab
WHERE account_id = 10
FOR UPDATE;
~~~

Session B:

~~~sql
UPDATE account_balance_lab
SET balance = balance + 100
WHERE account_id = 10;
~~~

B will wait because A holds the lock on row 10. A runs:

~~~sql
COMMIT;
~~~

Then B proceeds and can COMMIT.

### 16.3. Lab B — Other rows remain updatable

Session A locks account 10:

~~~sql
SELECT account_id
FROM account_balance_lab
WHERE account_id = 10
FOR UPDATE;
~~~

Session B updates account 20:

~~~sql
UPDATE account_balance_lab
SET balance = balance + 50
WHERE account_id = 20;

COMMIT;
~~~

B can update row 20 because A only locked row 10. Afterward, A runs ROLLBACK or COMMIT to release the lock on 10.

### 16.4. Lab C — NOWAIT

Keep row 10 locked in Session A. Session B runs:

~~~sql
SELECT account_id
FROM account_balance_lab
WHERE account_id = 10
FOR UPDATE NOWAIT;
~~~

B receives a resource busy error immediately instead of waiting.

### 16.5. Lab D — WAIT

Keep row 10 locked in A. B runs:

~~~sql
SELECT account_id
FROM account_balance_lab
WHERE account_id = 10
FOR UPDATE WAIT 3;
~~~

If A does not release within 3 seconds, B receives a timeout error. Retry by having A run COMMIT before the timeout expires.

### 16.6. Lab E — Locking scope in JOIN

Create orders and customers tables:

~~~sql
CREATE TABLE customers_lock_lab (
    customer_id NUMBER PRIMARY KEY,
    customer_name VARCHAR2(50 CHAR)
);

CREATE TABLE orders_lock_lab (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER REFERENCES customers_lock_lab(customer_id),
    status VARCHAR2(20 CHAR)
);

INSERT INTO customers_lock_lab VALUES (1, 'An');
INSERT INTO customers_lock_lab VALUES (2, 'Binh');
INSERT INTO orders_lock_lab VALUES (101, 1, 'READY');
INSERT INTO orders_lock_lab VALUES (102, 1, 'READY');
INSERT INTO orders_lock_lab VALUES (201, 2, 'READY');
COMMIT;
~~~

Query locking both tables:

~~~sql
SELECT o.order_id, c.customer_name
FROM orders_lock_lab o
JOIN customers_lock_lab c
  ON c.customer_id = o.customer_id
WHERE c.customer_id = 1
FOR UPDATE;
~~~

Query locking only orders:

~~~sql
SELECT o.order_id, c.customer_name
FROM orders_lock_lab o
JOIN customers_lock_lab c
  ON c.customer_id = o.customer_id
WHERE c.customer_id = 1
FOR UPDATE OF o.status;
~~~

While A holds the lock, use Session B to test UPDATE on CUSTOMERS_LOCK_LAB and ORDERS_LOCK_LAB to observe the difference. With OF o.status, the customer row is not locked by that SELECT; the matching order rows are locked.

### 16.7. Lab F — SKIP LOCKED

Create a small queue:

~~~sql
CREATE TABLE job_queue_lab (
    job_id NUMBER PRIMARY KEY,
    status VARCHAR2(20 CHAR) NOT NULL,
    payload VARCHAR2(100 CHAR)
);

INSERT INTO job_queue_lab VALUES (1, 'READY', 'Job A');
INSERT INTO job_queue_lab VALUES (2, 'READY', 'Job B');
INSERT INTO job_queue_lab VALUES (3, 'READY', 'Job C');
COMMIT;
~~~

Session A:

~~~sql
SELECT job_id, payload
FROM job_queue_lab
WHERE job_id = 1
FOR UPDATE;
~~~

Session B:

~~~sql
SELECT job_id, payload
FROM job_queue_lab
WHERE status = 'READY'
ORDER BY job_id
FOR UPDATE SKIP LOCKED;
~~~

B can pick up jobs 2 and 3 without waiting for job 1 held by A. A runs COMMIT/ROLLBACK; B's next read can pick up job 1 if it is still READY.

### 16.8. Clean up lab tables (optional)

~~~sql
DROP TABLE job_queue_lab PURGE;
DROP TABLE orders_lock_lab PURGE;
DROP TABLE customers_lock_lab PURGE;
DROP TABLE account_balance_lab PURGE;
~~~

DDL performs an implicit commit. Drop only the exact lab tables you created.

## 17. Checklist before using SELECT FOR UPDATE

1. **What is the set of rows to lock?** Check WHERE and how many rows may be returned.
2. **Which tables does the query JOIN?** Without OF, selected rows from all tables may be locked.
3. **Do you need to lock every table?** If only updating one table, use OF to narrow the scope.
4. **Is OF identifying the table, or are you assuming it locks only a column?** OF identifies the table; the row is locked.
5. **If no rows exist, is the business logic still safe?** SELECT FOR UPDATE does not lock non-existent rows or gaps.
6. **How long should the wait be?** Choose default, NOWAIT, or WAIT based on application experience.
7. **Is SKIP LOCKED needed?** Only use when locked rows may be processed later.
8. **Could a cursor return too many rows?** Regular FOR UPDATE cursors lock the result set at OPEN.
9. **Are transactions ended promptly?** Commit/roll back soon after completion; never commit inside a fetch loop.
10. **Can a single atomic UPDATE be used?** If so, an UPDATE statement is usually simpler.
11. **Are multiple rows or multiple tables involved?** Standardize locking order to reduce deadlocks.
12. **Are lock errors handled?** Prepare for ORA-00054, ORA-30006, ORA-00060, and ORA-01002.

## 18. Self-check questions

**Question 1.** What is SELECT FOR UPDATE used for?

**Question 2.** If SELECT FOR UPDATE has a WHERE clause that selects a single row, which rows are locked?

**Question 3.** If WHERE is omitted, how can the locking scope change?

**Question 4.** When JOINing two tables and omitting OF, which table's rows does Oracle lock?

**Question 5.** Does FOR UPDATE OF e.salary mean only the SALARY column is locked?

**Question 6.** Is FOR UPDATE OF used to filter rows or to specify which table has rows to lock?

**Question 7.** If SELECT FOR UPDATE finds no rows, does it lock the gap to prevent INSERT?

**Question 8.** When are row locks released?

**Question 9.** Does CLOSE on a FOR UPDATE cursor automatically release row locks?

**Question 10.** Does a regular FOR UPDATE cursor lock rows at OPEN or at FETCH?

**Question 11.** How does SKIP LOCKED differ from WAIT?

**Question 12.** Why should you not COMMIT inside the FETCH loop of a FOR UPDATE cursor?

**Question 13.** Does Oracle 19c allow combining FETCH FIRST with FOR UPDATE?

**Question 14.** When should you use an atomic UPDATE instead of SELECT FOR UPDATE?

<details>
<summary>Answer hints</summary>

1. Pre-locks selected rows so other sessions cannot update/delete or acquire conflicting locks until the transaction ends.
2. The single row matching the condition and belonging to the table(s) locked per the query.
3. Every row in the table can belong to the result set and be locked.
4. By default, selected rows from both tables are locked.
5. No. SALARY only identifies the EMPLOYEES table; the employee's row is locked.
6. Specifies the table or view whose rows should be locked; WHERE determines which rows are selected.
7. No. No rows means no row locks; SELECT FOR UPDATE does not lock gaps.
8. On COMMIT or ROLLBACK; rollback to a savepoint can release locks acquired after the savepoint.
9. No. Locks persist until the transaction ends or an appropriate rollback occurs.
10. A regular FOR UPDATE cursor locks the result set at OPEN, before the first FETCH. With SKIP LOCKED, rows are locked during the FETCH phase.
11. WAIT waits up to the specified duration; SKIP LOCKED skips rows currently locked.
12. COMMIT releases row locks and the FOR UPDATE cursor can no longer FETCH; ORA-01002 may occur.
13. No. The row limiting clause is incompatible with FOR UPDATE in Oracle 19c.
14. When the business condition and update expression can be combined into a single UPDATE statement, such as deducting balance only when balance is sufficient.

</details>

## 19. Official Oracle documentation

1. [Oracle Database 19c SQL Language Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): FOR UPDATE, OF, NOWAIT, WAIT, SKIP LOCKED syntax, restrictions, and row-locking examples in JOINs.
2. [Oracle Database 19c Database Development Guide — Locking Tables Explicitly](https://docs.oracle.com/en/database/oracle/oracle-database/19/adfns/sql-processing-for-application-developers.html): explicit row locks, cursor locking timing, lock hold durations, and deadlocks when the result set changes.
3. [Oracle Database 19c PL/SQL Language Reference — Transaction Processing and Control](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/transaction-processing-and-control.html): FOR UPDATE cursors, WHERE CURRENT OF, SKIP LOCKED, and row lock lifecycle.
4. [Oracle Database 19c Error Messages — ORA-00054](https://docs.oracle.com/en/error-help/db/ora-00054/): resource busy when using NOWAIT.
5. [Oracle Database 19c Error Messages — ORA-30006](https://docs.oracle.com/en/error-help/db/ora-30006/): timeout while waiting for a lock.
6. [Oracle Database 19c Error Messages — ORA-00060](https://docs.oracle.com/en/error-help/db/ora-00060/): deadlock detected.
7. [Oracle Database 19c Error Messages — ORA-01002](https://docs.oracle.com/en/error-help/db/ora-01002/): fetch out of sequence.

**Key rule to remember:** SELECT FOR UPDATE locks rows belonging to the SELECT result set. In a JOIN, without OF, Oracle locks selected rows from every table; OF alias.column designates which table's rows to lock and does not lock only a single column. Row locks persist until transaction COMMIT/ROLLBACK. Use NOWAIT, WAIT, or SKIP LOCKED according to how your application handles contention; with FOR UPDATE cursors, remember that a regular cursor locks the entire result set at OPEN, whereas SKIP LOCKED acquires locks during FETCH. If you only need to check and update a simple condition, prefer an atomic DML statement; use SELECT FOR UPDATE when you need to keep rows stable across a multi-step workflow.
