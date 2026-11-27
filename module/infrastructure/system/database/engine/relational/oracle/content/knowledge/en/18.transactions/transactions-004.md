# SAVEPOINT and Partial Transaction Rollback in Oracle

Within a transaction, there are times when some steps have executed properly while a subsequent step does not meet requirements. You may want to discard only the recent work, preserve earlier valid changes, and continue the transaction. Oracle provides **SAVEPOINT** and **ROLLBACK TO SAVEPOINT** for this scenario.

SAVEPOINT marks a position inside a transaction. When you run ROLLBACK TO, Oracle undoes changes made after that position while keeping the transaction open. This is partial transaction rollback, distinct from rolling back the entire transaction with ROLLBACK.

This lesson uses Oracle Database to explain transaction boundaries, savepoint syntax, ordering of multiple savepoints, a multi-step transfer example, PL/SQL exception handling, the effects of DDL and autocommit, and key limitations to keep in mind when using savepoints in applications.

## 1. Transactions and the Need for Partial Rollback

A transaction is a logical unit of work consisting of one or more DML statements. Changes in a transaction are confirmed with COMMIT or discarded with ROLLBACK.

For example, an order placement workflow might consist of:

1. Creating the order record.
2. Decrementing inventory quantity.
3. Recording payment.
4. Recording processing history.

If steps 1 and 2 are valid but step 3 is rejected, the application may need to revert back before the payment step while keeping earlier changes to try an alternative approach. SAVEPOINT helps mark the position to return to.

~~~text
BEGIN TRANSACTION
       |
       v
    DML step 1
       |
       v
  SAVEPOINT sp_a
       |
       v
    DML step 2
       |
       v
  SAVEPOINT sp_b
       |
       v
    DML step 3  ----> invalid
       |
       v
ROLLBACK TO sp_b
       |
       v
Keep steps 1 and 2, discard work after sp_b
       |
       v
Continue DML or COMMIT
~~~

SAVEPOINT does not create an independent transaction. It merely marks a point inside the current transaction.

## 2. SAVEPOINT and ROLLBACK TO Syntax

### 2.1. Creating a Savepoint

~~~sql
SAVEPOINT savepoint_name;
~~~

Example:

~~~sql
SAVEPOINT before_update;
~~~

The statement above places a marker named `BEFORE_UPDATE` at the current position of the transaction.

### 2.2. Rolling Back to a Savepoint

~~~sql
ROLLBACK TO SAVEPOINT savepoint_name;
~~~

Oracle also accepts the short form:

~~~sql
ROLLBACK TO savepoint_name;
~~~

Example:

~~~sql
ROLLBACK TO SAVEPOINT before_update;
~~~

Oracle undoes changes made after `BEFORE_UPDATE`. The transaction remains open and can continue executing DML or end with COMMIT/ROLLBACK.

### 2.3. Ending the Entire Transaction

~~~sql
COMMIT;
~~~

COMMIT confirms all remaining changes in the transaction and clears the savepoints of that transaction.

~~~sql
ROLLBACK;
~~~

ROLLBACK does not revert only to a savepoint; it discards all uncommitted changes in the current transaction and ends the transaction.

| Command | Scope of Undo/Confirmation | Transaction After Command |
|---|---|---|
| SAVEPOINT name | Does not undo; only marks a position | Remains open |
| ROLLBACK TO name | Discards changes after the savepoint | Remains open |
| ROLLBACK | Discards all uncommitted changes | Ends |
| COMMIT | Confirms all remaining changes | Ends |

## 3. SAVEPOINT Is Not a Nested Transaction

A transaction can have multiple savepoints, but they are not independent child transactions.

- You cannot COMMIT only the part before a savepoint while keeping the part after uncommitted.
- You cannot roll back to a savepoint after the transaction has COMMITted.
- ROLLBACK TO does not start a new transaction.
- All savepoints belong to the same transaction and the same session.

Think of savepoints as milestones along a path. ROLLBACK TO returns to a milestone, whereas COMMIT or ROLLBACK finishes the entire path.

## 4. Preparing Practice Data

We use two tables:

- `LAB_TX_ACCOUNT`: accounts and balances.
- `LAB_TX_TRANSFER`: transfer history between two accounts.

One transfer operation consists of updating the source account balance, updating the destination account balance, and inserting history. Then we simulate a subsequent transfer being cancelled with ROLLBACK TO.

### 4.1. Create the Accounts Table

Run in a lab schema inside a practice PDB. If tables with the same names already exist, use a different schema or table names; do not overwrite data currently in use.

~~~sql
CREATE TABLE lab_tx_account (
    account_id   NUMBER(6) PRIMARY KEY,
    holder_name  VARCHAR2(60 CHAR) NOT NULL,
    balance      NUMBER(14,2) NOT NULL,
    CONSTRAINT ck_lab_tx_account_balance
      CHECK (balance >= 0)
);
~~~

### 4.2. Create the Transfer History Table

~~~sql
CREATE TABLE lab_tx_transfer (
    transfer_id       NUMBER(8) PRIMARY KEY,
    from_account_id   NUMBER(6) NOT NULL,
    to_account_id     NUMBER(6) NOT NULL,
    transfer_amount   NUMBER(14,2) NOT NULL,
    created_at        DATE NOT NULL,
    CONSTRAINT fk_lab_tx_transfer_from
      FOREIGN KEY (from_account_id)
      REFERENCES lab_tx_account (account_id),
    CONSTRAINT fk_lab_tx_transfer_to
      FOREIGN KEY (to_account_id)
      REFERENCES lab_tx_account (account_id),
    CONSTRAINT ck_lab_tx_transfer_amount
      CHECK (transfer_amount > 0),
    CONSTRAINT ck_lab_tx_transfer_accounts
      CHECK (from_account_id <> to_account_id)
);
~~~

### 4.3. Insert Initial Data

~~~sql
INSERT INTO lab_tx_account VALUES (1, 'An',   1000);
INSERT INTO lab_tx_account VALUES (2, 'Binh',  500);
INSERT INTO lab_tx_account VALUES (3, 'Chi',   200);
COMMIT;
~~~

Initial balances:

| ACCOUNT_ID | HOLDER_NAME | BALANCE |
|---:|---|---:|
| 1 | An | 1000 |
| 2 | Binh | 500 |
| 3 | Chi | 200 |

Total balance is 1700. The following examples assume data has been initialized exactly as shown in this table.

## 5. Main Example: Keep the First Transfer, Cancel the Second Transfer

Suppose we need to:

1. Transfer 200 from An to Binh.
2. Next, attempt to transfer 100 from Binh to Chi.
3. Discover the second transfer is not approved, so cancel only the second one.
4. Keep the first transfer and COMMIT.

### 5.1. Place a Savepoint Before the First Transfer

~~~sql
SAVEPOINT before_first_transfer;
~~~

This savepoint marks the state before starting the transfer changes.

### 5.2. Execute the First Transfer

~~~sql
UPDATE lab_tx_account
SET balance = balance - 200
WHERE account_id = 1
  AND balance >= 200;

UPDATE lab_tx_account
SET balance = balance + 200
WHERE account_id = 2;

INSERT INTO lab_tx_transfer (
    transfer_id,
    from_account_id,
    to_account_id,
    transfer_amount,
    created_at
)
VALUES (
    5001,
    1,
    2,
    200,
    DATE '2026-11-14'
);
~~~

After the three statements, the balances are:

| Account | Balance |
|---|---:|
| An | 800 |
| Binh | 700 |
| Chi | 200 |

The history has transfer 5001. These changes are not COMMITted yet; they only exist within the current transaction.

### 5.3. Mark After the First Transfer

~~~sql
SAVEPOINT after_first_transfer;
~~~

This is the marker we want to preserve if the second transfer fails.

### 5.4. Attempt the Second Transfer

~~~sql
UPDATE lab_tx_account
SET balance = balance - 100
WHERE account_id = 2
  AND balance >= 100;

UPDATE lab_tx_account
SET balance = balance + 100
WHERE account_id = 3;

INSERT INTO lab_tx_transfer (
    transfer_id,
    from_account_id,
    to_account_id,
    transfer_amount,
    created_at
)
VALUES (
    5002,
    2,
    3,
    100,
    DATE '2026-11-14'
);
~~~

Immediately after these statements, the tentative balances are:

| Account | Tentative Balance |
|---|---:|
| An | 800 |
| Binh | 600 |
| Chi | 300 |

The history contains both transfer 5001 and 5002. Suppose during a business check step, transfer 5002 is rejected.

### 5.5. Roll Back Only the Second Transfer

~~~sql
ROLLBACK TO SAVEPOINT after_first_transfer;
~~~

Oracle discards the changes made after savepoint `AFTER_FIRST_TRANSFER`:

- Refunds the 100 debited from Binh.
- Reverses the 100 credited to Chi.
- Removes the transfer 5002 history row inserted after the savepoint.

The changes of transfer 5001 before the savepoint remain in the transaction.

Verify:

~~~sql
SELECT account_id, holder_name, balance
FROM lab_tx_account
ORDER BY account_id;

SELECT transfer_id, from_account_id, to_account_id, transfer_amount
FROM lab_tx_transfer
ORDER BY transfer_id;
~~~

Expected result:

| ACCOUNT_ID | HOLDER_NAME | BALANCE |
|---:|---|---:|
| 1 | An | 800 |
| 2 | Binh | 700 |
| 3 | Chi | 200 |

| TRANSFER_ID | FROM_ACCOUNT_ID | TO_ACCOUNT_ID | TRANSFER_AMOUNT |
|---:|---:|---:|---:|
| 5001 | 1 | 2 | 200 |

### 5.6. COMMIT the Remaining Work

If the first transfer is valid and verification passes:

~~~sql
COMMIT;
~~~

At this point, transfer 5001's changes become confirmed data. You cannot use ROLLBACK TO to go back to `BEFORE_FIRST_TRANSFER` after COMMIT.

## 6. If You Want to Cancel All Changes, Use ROLLBACK

In the previous example, if after undoing transfer 5002 you discover transfer 5001 is also wrong, you can revert to the initial savepoint:

~~~sql
ROLLBACK TO SAVEPOINT before_first_transfer;
~~~

This command undoes transfer 5001 and all changes after `BEFORE_FIRST_TRANSFER`, as long as the transaction has not ended.

If you want to discard the entire transaction without reverting to a savepoint:

~~~sql
ROLLBACK;
~~~

Comparison:

| Scenario | Command | Result |
|---|---|---|
| Cancel only the second transfer | ROLLBACK TO after_first_transfer | Keeps the first transfer |
| Cancel all changes from start of transaction | ROLLBACK TO before_first_transfer | Reverts to the initial marker, transaction stays open |
| Cancel the entire current transaction | ROLLBACK | Reverts to pre-transaction state and ends the transaction |
| Confirm remaining changes | COMMIT | Records all changes not rolled back |

If re-running the example, restore the lab data to its initial state appropriately before reusing existing transfer IDs.

## 7. Multiple Savepoints in One Transaction

A transaction can mark multiple positions:

~~~sql
SAVEPOINT step_0;

UPDATE lab_tx_account
SET balance = balance - 50
WHERE account_id = 1;

SAVEPOINT step_1;

UPDATE lab_tx_account
SET balance = balance + 50
WHERE account_id = 2;

SAVEPOINT step_2;

UPDATE lab_tx_account
SET balance = balance - 25
WHERE account_id = 2;

SAVEPOINT step_3;
~~~

At this point, the changes in order are:

| Marker | Changes Performed |
|---|---|
| STEP_0 | No changes yet |
| After STEP_0 | Debit 50 from account 1 |
| STEP_1 | Marker after debiting 50 |
| After STEP_1 | Credit 50 to account 2 |
| STEP_2 | Marker after crediting 50 |
| After STEP_2 | Debit 25 from account 2 |
| STEP_3 | Marker after debiting 25 |

If you run:

~~~sql
ROLLBACK TO step_1;
~~~

Oracle undoes the changes after `STEP_1`:

- Reverses the credit of 50 to account 2.
- Reverses the debit of 25 from account 2.
- Savepoints created after `STEP_1` (`STEP_2` and `STEP_3`) are erased.
- The debit of 50 from account 1 before `STEP_1` remains.
- `STEP_0` and `STEP_1` remain usable markers in the transaction.

Afterward, you can continue DML and COMMIT, or run `ROLLBACK TO STEP_0` to undo the debit of 50 as well.

### 7.1. Savepoints After the Rollback Target Are Removed

When rolling back to a savepoint, savepoints created **after** that marker are no longer valid. In the following example:

~~~sql
ROLLBACK TO step_1;
ROLLBACK TO step_3;
~~~

the second command cannot use `STEP_3` because that savepoint was erased when rolling back to `STEP_1`. Oracle may raise `ORA-01086` for a savepoint that no longer exists or is invalid.

### 7.2. The Target Savepoint Remains Valid After ROLLBACK TO

The savepoint you rolled back to remains active. You can perform additional DML and then roll back to that same marker again:

~~~sql
SAVEPOINT checkpoint_a;

UPDATE lab_tx_account
SET balance = balance + 10
WHERE account_id = 3;

ROLLBACK TO checkpoint_a;

UPDATE lab_tx_account
SET balance = balance + 20
WHERE account_id = 3;

ROLLBACK TO checkpoint_a;
~~~

Both balance increments are undone because both occurred after `CHECKPOINT_A`. The transaction remains open after each ROLLBACK TO.

## 8. Reusing the Same Savepoint Name

If you create a new savepoint with the same name as an older savepoint in the same transaction, Oracle moves that savepoint to the new position; the old marker of the same name is no longer kept.

~~~sql
SAVEPOINT progress;

UPDATE lab_tx_account
SET balance = balance + 10
WHERE account_id = 1;

SAVEPOINT progress;

UPDATE lab_tx_account
SET balance = balance + 20
WHERE account_id = 1;

ROLLBACK TO progress;
~~~

`ROLLBACK TO PROGRESS` reverts to the most recently created `PROGRESS`, so it only undoes the increase of 20. The increase of 10 before the new savepoint remains.

Therefore, choose meaningful savepoint names and avoid accidentally reusing a name already used by a procedure or another part of the application.

## 9. SAVEPOINT in PL/SQL and Exception Handling

A PL/SQL block can set a savepoint and roll back inside its exception handler. This technique is useful when a procedure executes multiple DML statements but only wants to undo its own work if an error occurs.

Example:

~~~sql
DECLARE
    v_rows PLS_INTEGER;
BEGIN
    SAVEPOINT before_account_change;

    UPDATE lab_tx_account
    SET balance = balance - 50
    WHERE account_id = 1
      AND balance >= 50;

    v_rows := SQL%ROWCOUNT;
    IF v_rows <> 1 THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Account 1 does not exist or has insufficient balance'
        );
    END IF;

    UPDATE lab_tx_account
    SET balance = balance + 50
    WHERE account_id = 2;

    v_rows := SQL%ROWCOUNT;
    IF v_rows <> 1 THEN
        RAISE_APPLICATION_ERROR(
            -20002,
            'Destination account does not exist'
        );
    END IF;

EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK TO before_account_change;
        RAISE;
END;
/
~~~

Execution flow:

1. Mark `BEFORE_ACCOUNT_CHANGE`.
2. Debit the source account and check the updated row count.
3. Credit the destination account and check the row count.
4. If any step raises an error, the exception handler rolls back to the savepoint.
5. `RAISE` propagates the error to the caller so the calling layer decides how to proceed.

The PL/SQL block does not auto-COMMIT when finished. The transaction still belongs to the calling session, and the caller can continue DML, COMMIT, or ROLLBACK.

### 9.1. Why Not COMMIT Inside a Procedure Sharing a Transaction?

A procedure is often invoked within a larger transaction managed by the application. If the procedure COMMITs on its own, it confirms earlier changes made by the caller in the same transaction, not just the procedure's DML.

The savepoint pattern lets a procedure undo its own work while keeping valid changes made before the procedure was called. However, transaction ownership and error-handling conventions must be clearly aligned with the caller.

### 9.2. Savepoint Names in Procedures Do Not Have Local Scope

Savepoints belong to the session's transaction, not as local variables of a PL/SQL block. If a procedure creates a savepoint with the same name as one created by the caller, the previous marker with that name is replaced.

Example:

~~~sql
SAVEPOINT caller_checkpoint;

-- A procedure below accidentally reuses the name caller_checkpoint:
SAVEPOINT caller_checkpoint;
~~~

After the second statement, the caller can no longer revert to the old marker via `CALLER_CHECKPOINT`. When writing procedures, choose savepoint names with a dedicated prefix to avoid colliding with the caller.

### 9.3. Cases Where the Exception Handler Cannot Roll Back

If the transaction has already been ended by a COMMIT, a full ROLLBACK, or DDL causing an implicit commit, the savepoint may no longer exist. When the exception handler executes:

~~~sql
ROLLBACK TO before_account_change;
~~~

error `ORA-01086` may occur. Therefore, a procedure relying on savepoints should never unilaterally end the transaction or run DDL between setting the marker and handling errors.

## 10. Statement-Level Rollback vs. Transaction Rollback

Oracle guarantees statement-level atomicity: if a DML statement fails, Oracle undoes the effects of that failed statement itself. Earlier DML statements in the transaction remain active and uncommitted.

For example, suppose:

~~~sql
UPDATE lab_tx_account
SET balance = balance + 10
WHERE account_id = 1;

UPDATE lab_tx_account
SET balance = -100
WHERE account_id = 2;
~~~

The second UPDATE violates `CHECK CONSTRAINT BALANCE >= 0` and is rejected. Oracle rolls back the effect of the second UPDATE; the first UPDATE remains in the transaction.

You can check:

~~~sql
SELECT account_id, balance
FROM lab_tx_account
ORDER BY account_id;
~~~

If you want to undo the first UPDATE as well, you must ROLLBACK the entire transaction or ROLLBACK TO a savepoint placed before the first UPDATE.

These are two different scopes:

| Mechanism | What Is Undone |
|---|---|
| Statement failure | Effects of the failed SQL statement |
| ROLLBACK TO savepoint | All changes in the transaction after the savepoint |
| ROLLBACK | All uncommitted changes in the transaction |

You do not need to place a savepoint before every DML statement just to ensure a failed SQL statement does not leave half of its own result behind; statement-level atomicity handles that. Savepoints are useful when you want to undo multiple previously succeeded statements together as a group.

## 11. DDL Can Erase Savepoints

In Oracle, standard DDL statements perform an implicit commit before executing and commit after the DDL executes successfully. This has a critical consequence:

~~~sql
SAVEPOINT before_ddl;

UPDATE lab_tx_account
SET balance = balance + 10
WHERE account_id = 1;

CREATE TABLE lab_tx_demo (
    id NUMBER PRIMARY KEY
);

ROLLBACK TO before_ddl;
~~~

`CREATE TABLE` causes the preceding transaction to be implicitly committed; savepoint `BEFORE_DDL` no longer exists. The subsequent `ROLLBACK TO` cannot undo the UPDATE before the DDL and may raise `ORA-01086`.

Commands such as CREATE, ALTER, DROP, and TRUNCATE are DDL; never place them in the middle of a DML sequence that you intend to roll back to a savepoint.

### 11.1. Prepare the Schema Before the Transaction

Appropriate order for a lab:

1. Create tables using DDL.
2. Insert initial data and COMMIT.
3. Begin the DML transaction.
4. Set savepoints and execute changes.
5. ROLLBACK TO, COMMIT, or ROLLBACK as intended.

Never create tables or alter constraints between DML steps that must be undone together.

## 12. SAVEPOINT and Tool Autocommit

Some SQL clients or JDBC connection configurations enable autocommit. When autocommit is enabled, each successful DML statement may be automatically committed right after execution.

For example, if the client auto-commits after each statement:

~~~sql
SAVEPOINT before_change;

UPDATE lab_tx_account
SET balance = balance + 10
WHERE account_id = 1;

ROLLBACK TO before_change;
~~~

If the UPDATE was autocommitted, the transaction containing `BEFORE_CHANGE` ended and the savepoint was cleared. ROLLBACK TO cannot undo a committed change.

When practicing SAVEPOINT:

- Use manual commit mode / autocommit OFF.
- Verify the client does not auto-commit after each DML statement.
- Do not click the Commit button before checking.
- Use one consistent session from SAVEPOINT through ROLLBACK TO.

In JDBC, applications typically call `setAutoCommit(false)`, execute DML statements, and explicitly call `commit`/`rollback`. If an application uses the JDBC `Savepoint` API, the `Savepoint` object is scoped to the current connection and transaction; do not reuse it after the transaction ends.

## 13. Savepoints Are Tied to a Session and Transaction

A savepoint is only valid within the transaction of the session that created it:

- If Session A creates `SAVEPOINT SP_A`, Session B cannot roll back to `SP_A`.
- COMMIT or a full ROLLBACK ends the transaction and clears savepoints.
- If the connection drops or the transaction ends, old savepoints can no longer be used.
- Savepoints are not durable data persisted inside a table.

In connection-pool applications, never assume a later request will receive the exact connection still holding the previous request's transaction. Manage the transaction on the same connection and never return a connection to the pool while a transaction is incomplete.

## 14. Impact of ROLLBACK TO on Locks

Oracle uses locks to coordinate concurrent changes. When rolling back to a savepoint:

- Data changes after the savepoint are undone.
- Savepoints created after that marker are erased.
- Oracle releases table/row locks acquired after the savepoint according to rollback rules.
- Locks acquired before the savepoint may still be held until the transaction ends.
- The transaction stays open.

Therefore, ROLLBACK TO does not mean releasing every lock held by the session. If a transaction updated a row before a savepoint, the associated lock may still be held after rolling back to a marker created later.

Example:

~~~sql
UPDATE lab_tx_account
SET balance = balance + 10
WHERE account_id = 1;

SAVEPOINT after_account_1;

UPDATE lab_tx_account
SET balance = balance + 10
WHERE account_id = 2;

ROLLBACK TO after_account_1;
~~~

The change to account 2 is undone; locks acquired after the marker are handled according to rollback rules. The change to account 1 before the savepoint remains, and the transaction has not ended.

Do not leave a transaction open for long merely because you performed a partial rollback. Once work is done, COMMIT or ROLLBACK the whole transaction to release transaction resources.

## 15. Limitations and Rules to Remember

### 15.1. Cannot Roll Back to a Savepoint After the Transaction Ends

~~~sql
SAVEPOINT before_commit;

UPDATE lab_tx_account
SET balance = balance + 10
WHERE account_id = 1;

COMMIT;

ROLLBACK TO before_commit;
~~~

After COMMIT, the transaction has ended and the savepoint is cleared. The last statement cannot restore the pre-commit state.

### 15.2. Cannot Roll Back to a Non-Existent Savepoint

~~~sql
ROLLBACK TO missing_savepoint;
~~~

If a savepoint was never created in the current transaction, was erased by rolling back to an earlier marker, or the transaction already ended, Oracle typically raises:

~~~text
ORA-01086: savepoint 'MISSING_SAVEPOINT' never established
~~~

Check the spelling, session, and transaction state.

### 15.3. Oracle Does Not Use RELEASE SAVEPOINT Like Some Other DBMSs

Do not use:

~~~sql
RELEASE SAVEPOINT before_update;
~~~

This is not valid Oracle SQL syntax for releasing a savepoint. Savepoints are managed by the transaction: full COMMIT/ROLLBACK clears them; ROLLBACK TO a marker removes savepoints after that marker; recreating the same name replaces the older marker with that name.

### 15.4. Savepoints Have No Independent Lifetime

There is no way to use a savepoint after a transaction ends, nor can you save a savepoint for use in another session. If data recovery is needed after COMMIT, you must use another mechanism such as audit/history tables, backups, Flashback, or an appropriate business compensation workflow.

## 16. SAVEPOINT in Procedures and Caller-Managed Transactions

A common application convention:

- The caller starts and ends the transaction.
- The procedure executes a group of DML statements.
- The procedure sets a savepoint before its DML group.
- On error, the procedure rolls back to its savepoint and re-raises the error.
- The caller decides whether to continue, roll back further, or commit.

Pattern:

~~~sql
CREATE OR REPLACE PROCEDURE lab_apply_adjustment (
    p_account_id IN NUMBER,
    p_delta      IN NUMBER
)
AS
BEGIN
    SAVEPOINT lab_apply_adjustment_sp;

    UPDATE lab_tx_account
    SET balance = balance + p_delta
    WHERE account_id = p_account_id;

    IF SQL%ROWCOUNT <> 1 THEN
        RAISE_APPLICATION_ERROR(-20010, 'Account not found');
    END IF;

EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK TO lab_apply_adjustment_sp;
        RAISE;
END;
/
~~~

This procedure does not COMMIT. If the update succeeds, the change remains part of the caller's transaction. If an error occurs, the DML after the savepoint is undone and the exception is propagated outward.

This is a design convention, not a requirement that every procedure must create a savepoint. For a procedure executing only a single DML statement, statement-level atomicity may already suffice. Consider savepoints when a procedure performs multiple DML statements that must be undone as a single unit.

## 17. Autonomous Transactions Are a Different Case

PL/SQL can declare an autonomous transaction using `PRAGMA AUTONOMOUS_TRANSACTION`. An autonomous transaction has its own transaction separate from the caller's transaction; it must COMMIT or ROLLBACK on its own before exiting.

Savepoints of the caller's transaction are not savepoints of the autonomous transaction and vice versa. `ROLLBACK TO` inside an autonomous transaction only affects that autonomous transaction. Do not use autonomous transactions as a substitute for savepoints in ordinary business logic; they have a specific purpose, typically independent logging when the caller rolls back.

## 18. Checking State Before and After ROLLBACK TO

For the money transfer lab, you can use SELECT to observe:

~~~sql
SELECT
    account_id,
    holder_name,
    balance
FROM lab_tx_account
ORDER BY account_id;

SELECT
    transfer_id,
    from_account_id,
    to_account_id,
    transfer_amount,
    created_at
FROM lab_tx_transfer
ORDER BY transfer_id;
~~~

A way to verify total balance:

~~~sql
SELECT SUM(balance) AS total_balance
FROM lab_tx_account;
~~~

When only transferring money between accounts in the same table, total balance must be conserved. Both before and after a partial rollback, the total remains 1700. This is a simple invariant that helps detect bugs where one side of an update was missed.

However, a conserved total balance alone does not prove each individual account or history row is correct. Verify both balances by `account_id` and the corresponding transfer rows.

## 19. Common Errors

| Symptom | Cause | Resolution |
|---|---|---|
| ORA-01086 on ROLLBACK TO | Savepoint not created, misspelled, erased, or transaction ended | Check command order, session, and COMMIT/ROLLBACK/DDL |
| Data did not revert as expected | Savepoint was placed after the change needing rollback | Place the savepoint before the DML group that may need undoing |
| ROLLBACK TO undid part meant to be kept | Marker placed too early | Create the savepoint at a more accurate business boundary |
| Cannot roll back after COMMIT | COMMIT ended the transaction | Use another recovery mechanism; savepoints do not exist after commit |
| Caller's savepoint was lost | Procedure reused the caller's savepoint name | Use a distinct naming prefix and align on conventions |
| DDL erased the savepoint | DDL caused an implicit commit | Separate DDL from DML transactions |
| Client cannot roll back | Autocommit committed the DML statement | Turn off autocommit and manage transactions on the same connection |
| One DML statement failed but prior DML remains | Oracle rolls back at the statement level, not the whole transaction automatically | Use ROLLBACK TO or ROLLBACK if earlier work must be cancelled |
| Locks remain after ROLLBACK TO | Locks acquired before the savepoint still remain | End the transaction when done to release all locks |

## 20. Practice Exercises

### Exercise 1 — Create a Savepoint and Roll Back One UPDATE

Increase account 1's balance by 100, set a savepoint before updating account 2, then roll back to the savepoint.

**Requirement:** determine which account keeps its change and which account reverts to its old balance.

**Hint:**

~~~sql
SAVEPOINT before_account_2;
~~~

Place the savepoint right before the UPDATE that needs to be undoable, then use ROLLBACK TO.

### Exercise 2 — Two Rollback Markers

In one transaction, create two savepoints A and B, execute one UPDATE after each marker, then roll back to A.

**Question:** Which UPDATEs are undone? Is savepoint B still usable?

**Guided Answer:** all changes after A are undone; B was created after A so it is no longer valid.

### Exercise 3 — Reusing a Savepoint Name

Create a savepoint named `PROGRESS`, update one row, recreate `PROGRESS`, update another row, then roll back to `PROGRESS`.

**Question:** Which marker does the rollback return to?

**Answer:** the most recently created `PROGRESS` marker; the earlier marker with the same name was replaced.

### Exercise 4 — Comparing ROLLBACK TO and ROLLBACK

Execute two UPDATEs after a savepoint. Run ROLLBACK TO, check the data, then execute one more UPDATE and run a full ROLLBACK.

**Question:** Why does the final result revert to the state before the transaction?

**Guided Answer:** ROLLBACK TO only discards changes after the savepoint and keeps the transaction open; the subsequent ROLLBACK discards all remaining uncommitted changes.

### Exercise 5 — Exception in PL/SQL

Write a PL/SQL block that sets a savepoint, updates the source account, then tries to update a non-existent account. If the updated row count does not equal 1, call `RAISE_APPLICATION_ERROR`; the exception handler rolls back to the savepoint and re-raises the error with `RAISE`.

**Requirement:** do not COMMIT inside the block.

### Exercise 6 — DDL and Savepoints

Create a savepoint, run an UPDATE, then attempt `CREATE TABLE` and `ROLLBACK TO savepoint`.

**Question:** Why is rolling back to the savepoint no longer valid?

**Guided Answer:** DDL causes an implicit commit, ending the transaction that held the savepoint.

### Exercise 7 — Autocommit

Try the same `SAVEPOINT/UPDATE/ROLLBACK TO` sequence in a client with autocommit turned on and turned off.

**Question:** What is the difference in rollback capability?

**Guided Answer:** when DML is autocommitted, the transaction ends and the savepoint is cleared; under manual commit, you can roll back to the savepoint.

### Exercise 8 — Transfer Workflow

Write a transaction consisting of two transfers, each having two UPDATEs and one history INSERT. Set a savepoint after the first transfer, then roll back the second one. Verify total balance and history before COMMITting.

**Expected result with sample data:** An 800, Binh 700, Chi 200; only transfer 5001 remains; total balance 1700.

## 21. Process for Deciding Where to Place SAVEPOINT

Before setting a savepoint, identify the business boundaries:

1. Which group of DML must be kept if a later step fails?
2. Which group of DML must be undone together?
3. The savepoint should be placed right before the first step of the group that might be cancelled.
4. Does any DDL, COMMIT, or full ROLLBACK occur between the savepoint and the error-handling point?
5. Could a procedure overwrite a caller's savepoint with the same name?
6. Does the client have autocommit enabled or use a different connection?

Diagram:

~~~text
Identify the business transaction
             |
             v
Split into valid DML groups
             |
             v
Place SAVEPOINT before a group that may need cancellation
             |
             v
Execute DML and check results
             |
       Did step fail?
        /       \
      No         Yes
       |          |
       v          v
Continue to    ROLLBACK TO
next step      appropriate savepoint
       |          |
       |          v
       |      Transaction stays open
       |          |
       +-----+----+
             |
             v
         Completed?
        /       \
      Yes        No
      |           |
      v           v
   COMMIT     Continue DML
      |
      v
Transaction ends
~~~

SAVEPOINT marks a point you can return to inside a transaction. ROLLBACK TO discards changes after the marker and keeps the transaction open so the application can continue processing; ROLLBACK discards all uncommitted changes; COMMIT confirms the remaining work. By placing markers right before controlled DML groups, checking state after each step, and managing the transaction on the same session, you can partially undo work without losing earlier valid changes.
