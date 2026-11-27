# PRAGMA AUTONOMOUS_TRANSACTION for Logging and Inconsistency Risks

In Oracle PL/SQL, a transaction normally groups multiple statements that commit or roll back together as a single unit. When you need to log an error or record an event that must survive even if the business transaction rolls back, you can use an **autonomous transaction**.

A routine marked with `PRAGMA AUTONOMOUS_TRANSACTION` runs in a transaction independent of the transaction that called it. The autonomous routine can commit or roll back its own work; that operation neither commits nor rolls back the caller's transaction. Once the routine finishes, the caller's transaction resumes.

This mechanism is valuable for error logging, yet it introduces a data consistency boundary that must be designed carefully. A log row can be committed while the business change it describes is rolled back. If an autonomous transaction is used to write a "transaction succeeded" audit record, the log may state something the main data never confirms.

This lesson covers:

- Declaring an autonomous transaction and its lifecycle.
- Independence between the autonomous transaction and its calling transaction.
- Writing durable error logs when a business transaction rolls back.
- Using autonomous transactions in triggers and key limitations to understand.
- Risks of data inconsistency, deadlocks, locks, and foreign keys.
- Distinguishing attempt logs from committed-transaction audits.
- Testing commit/rollback behavior in a lab and choosing the right model.

Examples target Oracle Database 19c. Only use autonomous transactions when transaction independence is an intentional requirement.

## 1. Normal Transactions vs. Autonomous Transactions

A normal transaction begins when a session executes DML and ends with `COMMIT` or `ROLLBACK`. If a procedure called within that transaction runs `INSERT`, `UPDATE`, or `DELETE`, that DML normally participates in the caller's transaction.

Example:

~~~sql
BEGIN
    UPDATE accounts
    SET balance = balance - 100
    WHERE account_id = 10;

    INSERT INTO transaction_audit (
        account_id,
        event_name
    )
    VALUES (10, 'DEBIT');

    ROLLBACK;
END;
/
~~~

Without an autonomous transaction, both the `UPDATE` and the `INSERT` are rolled back. This is usually the desired behavior for business audits: the audit exists only if the business change commits.

An autonomous transaction creates an independent transaction:

~~~text
MAIN TRANSACTION
  UPDATE business row
       |
       | call autonomous routine
       v
  SUSPENDED
       |
       +-------------------------------+
                                       |
AUTONOMOUS TRANSACTION                 |
  INSERT error/event log               |
  COMMIT                               |
       |                               |
       +-------------------------------+
                                       |
MAIN TRANSACTION                       |
  RESUMES <----------------------------+
  COMMIT or ROLLBACK
~~~

When the autonomous routine commits, the log row is persisted independently. If the main transaction rolls back afterward, the log row remains.

### 1.1. An Autonomous Transaction Is Not a New Session

The autonomous routine still runs within the same database session and call stack. Oracle creates a separate transaction context for the routine. It does not open a new connection and does not change `SESSION_USER`.

This means:

- The transaction context is independent.
- Session identity and session settings still belong to the calling session.
- The autonomous routine can still contend on locks with the main transaction.
- Cursors, package state, and session resources do not belong to a separate session.

### 1.2. When Is Transaction Independence Needed?

Appropriate scenarios include:

- Logging an error before re-throwing an exception to the caller.
- Recording a rejected or failed operation attempt.
- Recording diagnostics when the main transaction may roll back.
- Recording an operational event that business rules require keeping regardless of the main transaction's outcome.
- Certain triggers needing to log an attempted change even if the outer DML later rolls back.

Never use an autonomous transaction merely to "enable `COMMIT` inside a procedure." If a procedure belongs to the caller's business transaction, let it use the caller's transaction and let the calling layer decide commit/rollback.

## 2. Declaring PRAGMA AUTONOMOUS_TRANSACTION

`PRAGMA AUTONOMOUS_TRANSACTION` declares a routine or trigger as autonomous. The pragma goes in the declarative section of the routine, before `BEGIN`.

### 2.1. Standalone Procedure

~~~sql
CREATE OR REPLACE PROCEDURE write_log (
    p_message IN VARCHAR2
)
AS
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO application_log (
        log_time,
        message
    )
    VALUES (
        SYSTIMESTAMP,
        p_message
    );

    COMMIT;
END;
/
~~~

The `COMMIT` inside this procedure commits only the autonomous transaction. It does not commit the caller's uncommitted DML.

### 2.2. Standalone Function

A function can also be declared autonomous:

~~~sql
CREATE OR REPLACE FUNCTION record_attempt (
    p_event IN VARCHAR2
) RETURN NUMBER
AS
    PRAGMA AUTONOMOUS_TRANSACTION;
    v_log_id NUMBER;
BEGIN
    INSERT INTO application_log (
        log_time,
        message
    )
    VALUES (
        SYSTIMESTAMP,
        p_event
    )
    RETURNING log_id INTO v_log_id;

    COMMIT;
    RETURN v_log_id;
END;
/
~~~

Functions with side effects and transaction control must be invoked in appropriate contexts. Do not call a logging function inside a `SELECT` expression simply because it is technically possible; side effects inside queries make behavior unpredictable, hard to optimize, and hard to control.

### 2.3. Autonomous Transactions in a Package

The pragma is declared in the declarative section of each individual subprogram in the package body that needs to be autonomous:

~~~sql
CREATE OR REPLACE PACKAGE app_logger AS
    PROCEDURE write_event (
        p_event_name IN VARCHAR2,
        p_detail     IN VARCHAR2
    );
END app_logger;
/
~~~

~~~sql
CREATE OR REPLACE PACKAGE BODY app_logger AS
    PROCEDURE write_event (
        p_event_name IN VARCHAR2,
        p_detail     IN VARCHAR2
    )
    AS
        PRAGMA AUTONOMOUS_TRANSACTION;
    BEGIN
        INSERT INTO application_log (
            log_time,
            event_name,
            detail
        )
        VALUES (
            SYSTIMESTAMP,
            p_event_name,
            p_detail
        );

        COMMIT;
    EXCEPTION
        WHEN OTHERS THEN
            ROLLBACK;
            RAISE;
    END write_event;
END app_logger;
/
~~~

The pragma applies to the subprogram where it is declared; it does not automatically make every other procedure in the package autonomous. When a package has multiple routines, mark only those that truly require an independent transaction.

### 2.4. Autonomous Triggers

A trigger can also be declared autonomous:

~~~sql
CREATE OR REPLACE TRIGGER trg_log_salary_attempt
AFTER UPDATE OF salary ON employees
FOR EACH ROW
DECLARE
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO salary_change_attempts (
        employee_id,
        old_salary,
        new_salary,
        attempted_at
    )
    VALUES (
        :OLD.employee_id,
        :OLD.salary,
        :NEW.salary,
        SYSTIMESTAMP
    );

    COMMIT;
END;
/
~~~

This logs an **attempted change**. The autonomous trigger commits the log independently of the transaction updating `EMPLOYEES`. If the main transaction rolls back, the row in `SALARY_CHANGE_ATTEMPTS` still remains.

Never name or interpret this record as "salary change committed," because the trigger cannot guarantee whether the outer transaction will commit afterward.

## 3. Autonomous Transaction Lifecycle

An autonomous routine must manage its own transaction using `COMMIT` or `ROLLBACK`.

### 3.1. Execution Steps

1. Main transaction is running.
2. Caller invokes a routine declared with `PRAGMA AUTONOMOUS_TRANSACTION`.
3. Oracle suspends the main transaction.
4. The autonomous routine begins executing DML in its own transaction.
5. The routine commits or rolls back its own transaction.
6. The routine exits.
7. The main transaction resumes from where it was suspended.

The main transaction is neither committed nor rolled back when the autonomous routine exits.

### 3.2. COMMIT in an Autonomous Routine

~~~sql
CREATE OR REPLACE PROCEDURE log_message (
    p_message IN VARCHAR2
)
AS
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO application_log (log_time, message)
    VALUES (SYSTIMESTAMP, p_message);

    COMMIT;
END;
/
~~~

`COMMIT` ensures the log is saved even if the caller rolls back afterward.

### 3.3. ROLLBACK in an Autonomous Routine

~~~sql
CREATE OR REPLACE PROCEDURE try_log (
    p_message IN VARCHAR2
)
AS
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO application_log (log_time, message)
    VALUES (SYSTIMESTAMP, p_message);

    ROLLBACK;
END;
/
~~~

In this example, the log row is rolled back. `ROLLBACK` affects only the autonomous transaction, not the main transaction.

### 3.4. A Routine Must End with Its Transaction Closed

If an autonomous routine exits while its own transaction is still active, Oracle raises:

~~~text
ORA-06519: active autonomous transaction detected and rolled back
~~~

Oracle rolls back the unfinished autonomous transaction and raises the error. Therefore, every normal path and exception path must execute an appropriate `COMMIT` or `ROLLBACK`.

Handling pattern:

~~~sql
CREATE OR REPLACE PROCEDURE write_event (
    p_message IN VARCHAR2
)
AS
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO application_log (log_time, message)
    VALUES (SYSTIMESTAMP, p_message);

    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
~~~

Never allow an `IF` branch or exception handler to exit the routine with the autonomous transaction still open.

### 3.5. Savepoints Between the Two Transactions Are Separate

An autonomous transaction has its own savepoint scope. It cannot roll back to a savepoint created by the main transaction; likewise, the main transaction cannot use savepoints created inside an autonomous routine.

Never use savepoints to share state across the two transactions. Treat each transaction as a separate commit/rollback unit.

## 4. What Data Is Visible Between the Two Transactions?

Transaction independence does not mean each side automatically sees the other's uncommitted data.

### 4.1. Autonomous Transactions Cannot See the Caller's Uncommitted DML

Suppose the main transaction executes:

~~~sql
UPDATE orders
SET order_status = 'PROCESSING'
WHERE order_id = 500;
~~~

and then calls an autonomous routine to log. The autonomous routine does not see the main transaction's uncommitted change to `ORDER_STATUS` as committed data. Nor can it read an uncommitted version of the caller's data.

Therefore, if the logger needs details about the ongoing operation, pass the values explicitly via parameters:

~~~sql
write_event(
    p_event_name => 'ORDER_STATUS_ATTEMPT',
    p_detail     => 'order_id=500; new_status=PROCESSING'
);
~~~

Never require the logger to query uncommitted rows back to obtain data.

### 4.2. Does the Main Transaction See Committed Autonomous Data?

In the default `READ COMMITTED` isolation level, after the autonomous routine commits and returns control, subsequent SQL statements in the main transaction can see the newly committed data.

In `SERIALIZABLE`, the main transaction continues using its own transaction snapshot; changes committed by the autonomous transaction after the main transaction's snapshot began do not become visible within that snapshot.

Key point: visibility depends on isolation level and when statements start. Never build business logic assuming every main transaction immediately sees newly committed log rows.

### 4.3. Visibility Matrix

| Data | Visible to Autonomous Transaction? | Visible to Main Transaction? |
| --- | --- | --- |
| Data committed before autonomous query begins | Yes, per its snapshot | Yes, if part of main transaction's snapshot |
| Uncommitted DML of main transaction | No | Yes, inside main transaction itself |
| Committed autonomous DML | Yes, inside autonomous transaction | `READ COMMITTED`: subsequent SQL can see it; `SERIALIZABLE`: current snapshot does not |
| Uncommitted autonomous DML | Only inside autonomous transaction | No |
| Rolled-back main transaction DML | No longer committed data | Gone from main transaction after rollback |

Use logs as diagnostic records, not as an authoritative state source for business logic when the two transactions may reflect different outcomes.

## 5. Error Logging with Autonomous Transactions

This is a common, valid use case: when a business operation fails, the system rolls back the main data while preserving error diagnostics for investigation.

### 5.1. Creating the Log Table

~~~sql
CREATE TABLE app_error_log (
    log_id             NUMBER PRIMARY KEY,
    logged_at          TIMESTAMP WITH TIME ZONE NOT NULL,
    session_user_name  VARCHAR2(128),
    current_user_name  VARCHAR2(128),
    module_name        VARCHAR2(64),
    action_name        VARCHAR2(64),
    client_identifier  VARCHAR2(64),
    error_code         NUMBER,
    error_message      VARCHAR2(4000),
    error_stack        CLOB,
    error_backtrace    CLOB,
    context_text       CLOB
);

CREATE SEQUENCE app_error_log_seq;
~~~

The log table should record the details needed for investigation:

- Time the error occurred.
- User and application context.
- Module/action/client identifier if set.
- `SQLCODE` and `SQLERRM`.
- Error stack and backtrace.
- Business key or correlation ID passed from the caller.

Avoid storing excessive sensitive data or entire user payloads without genuine need and protective policies.

### 5.2. Creating the Logger Routine

~~~sql
CREATE OR REPLACE PROCEDURE write_error_log (
    p_error_code      IN NUMBER,
    p_error_message   IN VARCHAR2,
    p_error_stack     IN VARCHAR2,
    p_error_backtrace IN VARCHAR2,
    p_context         IN VARCHAR2
)
AS
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO app_error_log (
        log_id,
        logged_at,
        session_user_name,
        current_user_name,
        module_name,
        action_name,
        client_identifier,
        error_code,
        error_message,
        error_stack,
        error_backtrace,
        context_text
    )
    VALUES (
        app_error_log_seq.NEXTVAL,
        SYSTIMESTAMP,
        SYS_CONTEXT('USERENV', 'SESSION_USER'),
        SYS_CONTEXT('USERENV', 'CURRENT_USER'),
        SYS_CONTEXT('USERENV', 'MODULE'),
        SYS_CONTEXT('USERENV', 'ACTION'),
        SYS_CONTEXT('USERENV', 'CLIENT_IDENTIFIER'),
        p_error_code,
        SUBSTR(p_error_message, 1, 4000),
        p_error_stack,
        p_error_backtrace,
        p_context
    );

    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
~~~

The logger commits immediately after inserting. If the log insert fails, it rolls back its own transaction and raises the error to the caller. The caller must decide how to handle logger errors without losing the original business exception.

If the logger lives in another schema, the logger owner needs appropriate direct privileges on the table and sequence to compile static SQL. The application should only be granted `EXECUTE` on the required API.

### 5.3. Calling the Logger Inside an Exception Handler

~~~sql
CREATE OR REPLACE PROCEDURE process_order (
    p_order_id IN NUMBER
)
AS
    l_error_code      NUMBER;
    l_error_message   VARCHAR2(4000);
    l_error_stack     VARCHAR2(4000);
    l_error_backtrace VARCHAR2(4000);
BEGIN
    UPDATE orders
    SET order_status = 'PROCESSING'
    WHERE order_id = p_order_id;

    -- Other business processing steps.
    -- On failure, the caller's transaction can roll back.
EXCEPTION
    WHEN OTHERS THEN
        l_error_code := SQLCODE;
        l_error_message := SQLERRM;
        l_error_stack := DBMS_UTILITY.FORMAT_ERROR_STACK;
        l_error_backtrace := DBMS_UTILITY.FORMAT_ERROR_BACKTRACE;

        BEGIN
            write_error_log(
                p_error_code      => l_error_code,
                p_error_message   => l_error_message,
                p_error_stack     => l_error_stack,
                p_error_backtrace => l_error_backtrace,
                p_context         => 'order_id=' || p_order_id
            );
        EXCEPTION
            WHEN OTHERS THEN
                -- Do not let logging failures mask the original business exception.
                NULL;
        END;

        RAISE;
END;
/
~~~

The caller can catch the exception and roll back the business transaction according to application policy. The independently committed log row still remains.

### 5.4. Why Capture SQLCODE and SQLERRM First?

`SQLCODE`, `SQLERRM`, `FORMAT_ERROR_STACK`, and `FORMAT_ERROR_BACKTRACE` must be captured right inside the exception handler processing the error. Save them into variables before calling the logger or another routine so the original exception's details are preserved.

The bare `RAISE` statement at the end of the exception handler re-throws the active exception. This preserves the original error rather than replacing it with a new error caused by logging.

### 5.5. Should a Logger Swallow Errors?

Two policies are common:

- **Best-effort logging:** if logging fails, still prioritize returning the original business exception. The caller catches logger errors as shown above.
- **Mandatory logging:** if logs cannot be written, the application refuses to continue or raises a dedicated operational error.

Choose the policy based on audit and operational requirements. For ordinary error loggers, never let a logging error mask the original error; simultaneously maintain a separate monitoring channel to detect when the logger stops working.

## 6. Autonomous Transactions in Triggers

Triggers normally execute inside the transaction that fired the DML. If a trigger writes audit records via normal DML, the audit row shares the same transaction as the main table change.

### 6.1. Same-Transaction Auditing

~~~sql
CREATE OR REPLACE TRIGGER trg_employee_audit
AFTER UPDATE OF salary ON employees
FOR EACH ROW
BEGIN
    INSERT INTO employee_audit (
        employee_id,
        old_salary,
        new_salary,
        changed_at
    )
    VALUES (
        :OLD.employee_id,
        :OLD.salary,
        :NEW.salary,
        SYSTIMESTAMP
    );
END;
/
~~~

If `UPDATE EMPLOYEES` rolls back, the `EMPLOYEE_AUDIT` row rolls back too. When the main transaction commits, both the salary change and the audit commit together. This is the right choice when auditing means "the change was committed in the same transaction."

### 6.2. Autonomous Trigger Logging Attempts

~~~sql
CREATE OR REPLACE TRIGGER trg_employee_attempt_log
AFTER UPDATE OF salary ON employees
FOR EACH ROW
DECLARE
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO employee_change_attempts (
        employee_id,
        old_salary,
        requested_salary,
        attempted_at
    )
    VALUES (
        :OLD.employee_id,
        :OLD.salary,
        :NEW.salary,
        SYSTIMESTAMP
    );

    COMMIT;
END;
/
~~~

If the outer transaction rolls back, the `EMPLOYEE_CHANGE_ATTEMPTS` row still persists. This records an attempted change, not proof that the change succeeded.

### 6.3. Choosing the Exact Meaning of Logs

| Requirement | Appropriate Mechanism |
| --- | --- |
| Write audit only when business change commits | Normal trigger/DML in the main transaction |
| Record attempts even if caller rolls back | Autonomous transaction |
| Record exceptions for post-rollback investigation | Autonomous logger |
| Record authoritative business state | Business transaction or outbox committed with business data |
| Write telemetry without impacting main transaction | Autonomous logger or dedicated telemetry pipeline, per data-loss tolerance |

Never use an autonomous trigger to create a "changed" audit record when the business DML can still roll back after the trigger commits.

## 7. Inconsistency Risks

Autonomous transactions create two independent commit histories. If events and data models are not named accurately, operators can misinterpret logs as confirmed business state.

### 7.1. Log Exists While Business Transaction Rolled Back

Example:

1. Main transaction deducts 100 from an account.
2. Autonomous logger writes "debited" and commits.
3. Main transaction encounters an error and rolls back.
4. The account balance did not change, yet the log claims money was debited.

This is a semantic mismatch. Prevent it by logging `DEBIT_ATTEMPT` or `DEBIT_PROCESSING` instead of `DEBIT_COMMITTED`.

### 7.2. Main Transaction Commits While Log Fails to Write

The reverse can also happen:

1. Main transaction executes business work.
2. Logger hits an error such as full tablespace, missing privilege, or constraint violation.
3. Application ignores the logger error to preserve the business flow/exception.
4. Business work commits with no log entry.

An autonomous transaction does not guarantee logs always succeed. It merely separates transactions. Monitor logger failures, privileges, storage capacity, and log table health.

If auditing is mandatory and must stay synchronized with business commits, write audits in the same transaction or use a transactional outbox. Never rely on a best-effort autonomous logger to replace mandatory auditing.

### 7.3. Logs Are Not an Authoritative Data Source

Never query an autonomous log table to decide whether an order was paid, an account was debited, or an application was approved. The authoritative source of state must be committed business data or an event/outbox committed alongside that change.

### 7.4. Do Not Create Foreign Keys to Uncommitted Rows

A common bug occurs when a logger inserts into a log table that has a foreign key referencing a row the main transaction just created but has not yet committed. The autonomous transaction cannot see that uncommitted row; foreign key validation can block waiting on the main transaction's lock or trigger a deadlock.

For error/attempt logs:

- Store business keys like `ORDER_ID` or `ACCOUNT_ID` as scalar reference values without necessarily enforcing a foreign key.
- If a real foreign key is required, reference only rows that are already committed and exist independently.
- Never require the logger to query the caller's uncommitted data.

### 7.5. Deadlocks Between Autonomous and Main Transactions

The main transaction is suspended when calling an autonomous routine, yet it still holds all locks it acquired. If the autonomous transaction tries to access a row or resource locked by the main transaction, it can block waiting for the suspended transaction itself—resulting in a deadlock.

Risky example:

~~~sql
-- Main transaction has locked this row.
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 10;

-- Autonomous routine tries to UPDATE the same row.
write_account_log_and_update(10);
~~~

Never let an autonomous routine update the same business rows held by the caller. Loggers should write to independent log tables and avoid reading or writing resources locked by the main transaction.

### 7.6. Autonomous Triggers Querying the Modifying Table

An autonomous trigger can also hit deadlocks if it accesses resources locked by the triggering statement. In particular, never design an autonomous trigger to query back the table currently being modified or wait on row locks held by the transaction that fired it.

If a trigger only needs to record row details, pass values from `:OLD` and `:NEW` into an independent log table; never query uncommitted rows.

## 8. Autonomous Transactions and Locks

An autonomous transaction can access other tables, but it must never be assumed to share access to resources locked by the main transaction.

Key rules:

- The main transaction is suspended, yet its locks remain held.
- The autonomous transaction does not inherit the main transaction's locks.
- The autonomous transaction can block when accessing rows locked by the parent.
- The parent cannot resume to release locks until the autonomous routine returns control.
- This situation can cause a deadlock.

Design loggers to only `INSERT` into an independent log table using a dedicated sequence and avoiding foreign keys to uncommitted rows. Avoid updating business tables, locked parent/child tables, or configuration tables on which the main transaction holds locks.

## 9. Transaction Isolation and Log Visibility

Oracle defaults to `READ COMMITTED`. At this level, each statement sees data committed before that statement began. Once the autonomous routine commits, the parent's next statement can see the new log entry.

In `SERIALIZABLE`, the main transaction maintains a transaction-consistent snapshot. Autonomous data committed after that snapshot was established will not appear in that snapshot.

This matters if main code intends to read the log back immediately after calling the logger to make a business decision. Never assume all isolation levels share identical visibility.

If a logger result must be returned to the caller, return the log ID or needed value via an `OUT` parameter. Never force the caller to query a log table back just to retrieve a value the logger created.

## 10. Operational Errors and Considerations

### 10.1. ORA-06519

Cause: an autonomous routine exited while its autonomous transaction was still active.

Resolution:

- `COMMIT` when logging succeeds.
- `ROLLBACK` when handling fails.
- Check every `IF` branch and exception handler.
- Never allow a helper called inside the autonomous routine to leave an uncommitted transaction open.

### 10.2. ORA-00060 or Lock Waits

Cause: typically the autonomous transaction accessed a resource locked by the parent transaction.

Resolution:

- Separate the log table from business tables.
- Never update the same row locked by the caller.
- Never create foreign keys to uncommitted data.
- Inspect the call stack and lock graph when deadlocks occur.

### 10.3. Logger Failure Masking the Original Error

Cause: an exception during log `INSERT` replaces the active business exception.

Resolution:

- Capture `SQLCODE`, `SQLERRM`, and backtrace before calling the logger.
- Catch logger exceptions separately.
- Preserve and re-`RAISE` the original business exception.
- Monitor logger failures via metrics or another operational channel.

### 10.4. Unbounded Log Growth

Error logging can generate heavy DML volume. Make sure to:

- Partition and apply retention policies to log tables at scale.
- Maintain just enough indexes for diagnostic queries.
- Archive or purge according to policy.
- Limit context and payload sizes.
- Avoid logging full sensitive data.
- Monitor tablespace usage, redo, undo, and growth rate.

### 10.5. Committing Too Frequently

Autonomous loggers typically commit on every call. At very high frequencies, commits and redo incur significant overhead. For high-volume logging, consider batching, queues, or dedicated telemetry pipelines. However, batching changes the guarantee that "logs exist immediately after every call"; balance durability requirements against throughput.

## 11. Comparison Example: Same-Transaction Audit vs. Autonomous Log

### 11.1. Creating Lab Tables

~~~sql
CREATE TABLE lab_accounts (
    account_id NUMBER PRIMARY KEY,
    balance NUMBER(12, 2) NOT NULL
);

INSERT INTO lab_accounts VALUES (10, 1000);
COMMIT;

CREATE TABLE lab_event_log (
    log_id NUMBER PRIMARY KEY,
    event_name VARCHAR2(40) NOT NULL,
    account_id NUMBER NOT NULL,
    event_time TIMESTAMP WITH TIME ZONE NOT NULL,
    detail VARCHAR2(200)
);

CREATE SEQUENCE lab_event_log_seq;

CREATE TABLE lab_business_audit (
    account_id NUMBER NOT NULL,
    event_name VARCHAR2(40) NOT NULL,
    event_time TIMESTAMP WITH TIME ZONE NOT NULL
);
~~~

`LAB_EVENT_LOG` intentionally omits a foreign key to `LAB_ACCOUNTS`. This lets attempt logs persist even when the main transaction is creating or updating uncommitted rows.

### 11.2. Creating the Autonomous Logger

~~~sql
CREATE OR REPLACE PROCEDURE lab_log_event (
    p_event_name IN VARCHAR2,
    p_account_id IN NUMBER,
    p_detail IN VARCHAR2
)
AS
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO lab_event_log (
        log_id,
        event_name,
        account_id,
        event_time,
        detail
    )
    VALUES (
        lab_event_log_seq.NEXTVAL,
        p_event_name,
        p_account_id,
        SYSTIMESTAMP,
        p_detail
    );

    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
~~~

### 11.3. Testing Rollback of the Main Transaction

~~~sql
BEGIN
    UPDATE lab_accounts
    SET balance = balance - 100
    WHERE account_id = 10;

    lab_log_event(
        p_event_name => 'DEBIT_ATTEMPT',
        p_account_id => 10,
        p_detail => 'Requested debit amount=100'
    );

    ROLLBACK;
END;
/
~~~

Check:

~~~sql
SELECT account_id, balance
FROM lab_accounts
WHERE account_id = 10;

SELECT log_id, event_name, account_id, detail
FROM lab_event_log
ORDER BY log_id;
~~~

Expected result:

- `BALANCE` remains `1000` because the main transaction rolled back.
- `LAB_EVENT_LOG` contains the `DEBIT_ATTEMPT` row because the autonomous routine committed.

This is the right behavior when the requirement is recording debit attempts. Calling that log row `DEBIT_SUCCESS` would be misleading.

### 11.4. Comparing Same-Transaction Auditing

~~~sql
BEGIN
    UPDATE lab_accounts
    SET balance = balance - 100
    WHERE account_id = 10;

    INSERT INTO lab_business_audit (
        account_id,
        event_name,
        event_time
    )
    VALUES (
        10,
        'DEBIT',
        SYSTIMESTAMP
    );

    ROLLBACK;
END;
/
~~~

Check:

~~~sql
SELECT COUNT(*) AS audit_rows
FROM lab_business_audit
WHERE account_id = 10;
~~~

The result is `0` because the audit belonged to the main transaction and rolled back alongside the `UPDATE`.

### 11.5. Testing Commit of the Main Transaction

~~~sql
BEGIN
    UPDATE lab_accounts
    SET balance = balance - 100
    WHERE account_id = 10;

    INSERT INTO lab_business_audit (
        account_id,
        event_name,
        event_time
    )
    VALUES (
        10,
        'DEBIT',
        SYSTIMESTAMP
    );

    lab_log_event(
        p_event_name => 'DEBIT_ATTEMPT',
        p_account_id => 10,
        p_detail => 'Debit request processed'
    );

    COMMIT;
END;
/
~~~

After `COMMIT`:

- Balance drops to `900`.
- Both the business audit and the balance update commit together.
- The autonomous event log also committed independently.

This lab shows that two log tables can carry two different semantics: committed-transaction auditing versus attempt logging. Name events and tables so readers never confuse them.

## 12. Log Table Design and Data Policy

A solid log table supports investigation without turning into an uncontrolled copy of business data.

### 12.1. Commonly Useful Columns

| Column | Purpose |
| --- | --- |
| `LOG_ID` | Unique log identifier |
| `LOGGED_AT` | Timestamp of logging |
| `SESSION_USER_NAME` | Logged-in user |
| `CURRENT_USER_NAME` | Current user in privilege context |
| `MODULE_NAME`/`ACTION_NAME` | Identifies application flow |
| `CLIENT_IDENTIFIER` | Identifies user or request |
| `ERROR_CODE` | Oracle/application error code |
| `ERROR_MESSAGE` | Summary error message |
| `ERROR_STACK` | Error stack |
| `ERROR_BACKTRACE` | Error origin location |
| `CONTEXT_TEXT` | Correlation ID or business key |

You can use `DBMS_APPLICATION_INFO` to set `MODULE`/`ACTION` and `DBMS_SESSION.SET_IDENTIFIER` to assign `CLIENT_IDENTIFIER` before executing business logic. The logger reads these values using `SYS_CONTEXT`.

### 12.2. Correlation IDs

A request may pass through many procedures, triggers, and services. Propagating a correlation ID along the call chain lets you correlate logs without guessing by nearby timestamps.

A correlation ID is request metadata, not a mandatory foreign key. An autonomous logger can store it as a string even when related business rows have not committed.

### 12.3. Retention and Access Control

- Grant only necessary `INSERT`/`EXECUTE` privileges to the logger.
- Restrict `SELECT` on log tables to appropriate operations teams.
- Prevent application users from modifying or deleting written logs if audit integrity is required.
- Define retention and archiving rules.
- Monitor insert errors, tablespace usage, and growth rate.
- Comply with personal data and sensitive information policies.

## 13. When Should You NOT Use Autonomous Transactions?

Do not use them in the following cases unless transaction independence is an explicit requirement:

- Writing success audits that must roll back together with business changes.
- Updating rows currently locked by the main transaction.
- Relying on the caller's uncommitted data.
- Working around mutating table errors without understanding locks and consistency.
- Replacing the service layer's transaction boundaries.
- Committing step-by-step inside a business workflow that requires atomicity.
- Recording a "completed" status before the main transaction actually commits.

If an event must be emitted only after the transaction commits, consider a transactional outbox: write business data and the outbox row in the same transaction, then let a separate worker publish the event post-commit. This preserves strict consistency between business state and emitted events.

## 14. Investigation Workflow When Logs and Main Data Diverge

When logs report an action yet the business table shows no matching change, inspect log semantics first:

1. Identify which routine or trigger uses `PRAGMA AUTONOMOUS_TRANSACTION`.
2. Determine whether the log is written before or after which business step.
3. Check whether the routine commits before the caller finishes.
4. Check whether the main transaction rolled back, raised an exception, or timed out.
5. Verify whether the log represents `ATTEMPT`, `ERROR`, `PROCESSING`, or `COMMITTED`.
6. Check whether the autonomous routine reads uncommitted data or has foreign keys to uncommitted rows.
7. Inspect locks/deadlocks and the call stack.
8. Check isolation level if parent queries do not see newly written logs.
9. Verify whether the logger can fail independently and how the application handles logger errors.
10. Update event names, contracts, and transaction design to reflect accurate semantics.

Never delete a log row simply because no matching business row exists. For an attempt or error log, the absence of a business commit is exactly the diagnostic fact you need to keep.

## 15. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `ORA-06519` when routine exits | Autonomous transaction not committed or rolled back | Close the transaction on every path |
| Log persists after caller `ROLLBACK` | Logger committed its own transaction | Expected behavior; name log as attempt/error if appropriate |
| Audit says success while business row unchanged | Autonomous audit committed before main transaction | Use same-transaction audit or transactional outbox |
| Autonomous routine hangs or deadlocks | Contended on resource locked by parent | Isolate log table and avoid locked business rows |
| Logger cannot see newly inserted row | Parent's row is still uncommitted | Pass data via parameters; do not query uncommitted rows |
| Log insert blocks on foreign key | FK references parent's uncommitted row | Avoid FKs to uncommitted data in attempt/error logs |
| Logger error masks root error | Logger exception replaced business exception | Catch logger errors separately and re-`RAISE` root error |
| Parent does not see new log immediately | `SERIALIZABLE` snapshot or already-open statement | Understand isolation/snapshots; do not query logs back as API output |
| Trigger logged a rolled-back change | Autonomous trigger committed independently | Distinguish `ATTEMPT` from `COMMITTED` |
| Logs grow too rapidly | Every error/trigger creates a separate transaction and redo | Limit data, apply retention, partition, and monitor |
| Assuming pragma creates a new session | Confusing transaction context with session | Remember the session is still the caller's session |
| Using autonomous to bypass commit boundaries | Unclear transaction ownership | Keep business commit/rollback in the service layer |

## 16. Practice Exercises

Use the `LAB_ACCOUNTS`, `LAB_EVENT_LOG`, and `LAB_BUSINESS_AUDIT` tables from section 11.

### Exercise 1 — Independent Transaction

Create a procedure with `PRAGMA AUTONOMOUS_TRANSACTION` that inserts a log row and commits. Call it between an `UPDATE` and a `ROLLBACK` in the caller. Inspect both tables.

### Exercise 2 — Forgetting COMMIT

Create an autonomous procedure that only runs `INSERT` without committing or rolling back. Call it and observe `ORA-06519`. Explain how the autonomous transaction was handled when the routine exited.

### Exercise 3 — Logger with Exception Handler

Create a logger that rolls back on insert failure and re-raises the error. In the caller, catch logger errors separately so the original business exception is preserved. Verify which error reaches the client.

### Exercise 4 — Same-Transaction Auditing

Write a normal audit trigger and an autonomous trigger on two separate lab tables. Run DML and then roll back. Compare audit row counts.

### Exercise 5 — Foreign Key Risk

In the lab, test designing a log table with a foreign key to a row inserted by the main transaction but not yet committed. Observe lock waits or deadlocks. Then replace the foreign key with a scalar business key.

### Exercise 6 — Lock Risk

In the main session, lock a row. Call an autonomous routine that tries to update that same row. Observe the lock wait/deadlock and explain why the parent cannot resume to release the lock while the autonomous routine is still running.

### Exercise 7 — READ COMMITTED vs. SERIALIZABLE

Set up both isolation scenarios in the lab environment. Call an autonomous logger and then query the log from the parent. Compare visibility of the newly committed row across snapshots.

### Exercise 8 — Event Classification

Design event names and status columns for three cases: operation attempted, operation failed, and operation committed. Decide which cases use an autonomous transaction and which share the main transaction.

## 17. Lab Cleanup

Run only in the lab schema you created, after finishing all exercises:

~~~sql
DROP PROCEDURE lab_log_event;
DROP TABLE lab_business_audit PURGE;
DROP TABLE lab_event_log PURGE;
DROP SEQUENCE lab_event_log_seq;
DROP TABLE lab_accounts PURGE;
~~~

If you created additional triggers or routines during the exercises, drop those lab objects before dropping the tables. Never run cleanup commands on business data.

## Summary

`PRAGMA AUTONOMOUS_TRANSACTION` creates an independent transaction within the same session. The main transaction is suspended while the autonomous routine executes; `COMMIT`/`ROLLBACK` inside the routine affects only its own transaction. The routine must exit with its autonomous transaction either committed or rolled back, or `ORA-06519` can occur.

This mechanism is well-suited for error logging or attempt logging that must survive even when the business transaction rolls back. It is unsuitable for writing "committed" business audits that must remain consistent with main data changes. An autonomous transaction cannot see the caller's uncommitted DML and can deadlock if it touches resources locked by the caller. Pass context through parameters, use independent log tables, avoid foreign keys to uncommitted rows, preserve root exceptions, and name events accurately. If events must only be emitted after a business commit, use same-transaction auditing or a transactional outbox.

## Oracle Reference Documentation

- [Oracle Database PL/SQL Language Reference — Autonomous Transactions (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/autonomous-transactions.html) — pragma, transaction context, commit, and rollback.
- [Oracle Database PL/SQL Language Reference — AUTONOMOUS_TRANSACTION Pragma (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/AUTONOMOUS_TRANSACTION-pragma.html) — placement and pragma behavior.
- [Oracle Database PL/SQL Language Reference — Exception Handlers (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/exception-handling.html) — exception handling and `RAISE`.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_UTILITY (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_UTILITY.html) — `FORMAT_ERROR_STACK` and `FORMAT_ERROR_BACKTRACE`.
- [Oracle Database Concepts — Data Concurrency and Consistency (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/data-concurrency-and-consistency.html) — read consistency, isolation, and locking.
- [Oracle Database PL/SQL Language Reference — Triggers (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/triggers.html) — triggers and transaction behavior.

When deploying on Oracle releases other than 19c, check the PL/SQL Language Reference and Database Concepts for that exact release, especially regarding isolation-level visibility, trigger behavior, lock/deadlock behavior, and errors for unclosed autonomous transactions.
