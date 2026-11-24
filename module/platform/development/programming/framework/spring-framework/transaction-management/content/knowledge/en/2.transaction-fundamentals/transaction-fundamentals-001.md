# ACID: Atomicity, Consistency, Isolation, and Durability of Transactions

## 1. What problem do transactions solve?

A **transaction** is a unit of work consisting of one or more data operations processed as a single whole. For transferring 200 monetary units from account A to account B, the business logic must simultaneously debit 200 from A and credit 200 to B. If only A is debited without crediting B, the data becomes inconsistent.

A transaction typically ends with one of two outcomes:

- **COMMIT**: accepts all changes made by the transaction.
- **ROLLBACK**: discards the uncommitted changes of that transaction according to the guarantees provided by the database management system (DBMS).

**ACID** represents the four properties to understand when designing and verifying database transactions:

| Property | Question it answers | Practical meaning |
| --- | --- | --- |
| **A — Atomicity** | What if one step fails? | Changes within the same transaction are committed together or rolled back together. |
| **C — Consistency** | Is the data valid after the transaction? | A correct transaction must transition the database from one state that satisfies invariants/constraints to another state that also satisfies them. |
| **I — Isolation** | How do concurrent transactions see and affect one another? | The DBMS controls concurrent interactions according to the chosen isolation level; lower levels may allow certain anomalies. |
| **D — Durability** | What if the server crashes after reporting commit? | Once a commit succeeds, the data is preserved by the DBMS across failures within the scope guaranteed by its storage mechanism. |

ACID applies to transaction boundaries over **the resources that actually participate in the transaction**. Adding `@Transactional` to a Java method does not automatically turn HTTP calls, emails, Kafka messages, in-memory application state, and multiple independent databases into a single atomic transaction.

## 2. Atomicity — all or nothing

Suppose we have a table and initial data in PostgreSQL:

```sql
CREATE TABLE accounts (
    id BIGINT PRIMARY KEY,
    balance BIGINT NOT NULL CHECK (balance >= 0)
);

INSERT INTO accounts (id, balance)
VALUES (1, 1000), (2, 500);
```

Transferring 200 from account 1 to account 2 in **a single transaction**:

```sql
BEGIN;

UPDATE accounts SET balance = balance - 200 WHERE id = 1;
UPDATE accounts SET balance = balance + 200 WHERE id = 2;

COMMIT;
```

After `COMMIT`, the balances are 800 and 700 respectively; the total remains 1,500. If an error occurs before commit and the transaction is rolled back, both balances return to 1,000 and 500. Example demonstrating an explicit rollback:

```sql
BEGIN;
UPDATE accounts SET balance = balance - 200 WHERE id = 1;
-- Suppose the credit step cannot complete.
ROLLBACK;
SELECT id, balance FROM accounts ORDER BY id;
```

Expected result on the initial data:

```text
 id | balance
----+---------
  1 |    1000
  2 |     500
```

**Common misconception:** atomicity does not mean "every SQL statement in a transaction always succeeds." It is the ability not to expose a **partially committed result** when the overall transaction fails. Different DBMSs have different statement-error/savepoint handling mechanisms; you must understand the actual transaction state after an error and always end properly with `COMMIT` or `ROLLBACK`.

Without opening a transaction, each SQL statement may be auto-committed individually. In that case, a debit succeeding followed by a credit failing produces a persisted yet invalid business state. A Java method call is also not an atomic boundary if the SQL statements use different connections/transactions.

## 3. Consistency — preserving business invariants

An **invariant** is a condition that must hold true in accepted data states. For example:

- `accounts.id` has no duplicates: `PRIMARY KEY`.
- `balance >= 0`: `CHECK` constraint.
- Every transfer order must have a source account, a destination account, and a positive amount.
- For internal transfers with no fees, the total balance before and after must be equal.

The database can directly enforce many rules using `PRIMARY KEY`, `FOREIGN KEY`, `UNIQUE`, `NOT NULL`, and `CHECK`. Rules involving multiple rows, multiple tables, or business states may require conditional updates, locks, appropriate isolation levels, and application logic.

For example, checking in Java and then updating unconditionally is not enough:

```java
// Counter-example: two requests can both read balance 100 and both think
// they can withdraw 80. Unsynchronized read-then-write can cause discrepancies.
long balance = loadBalance(accountId);
if (balance >= amount) {
    saveBalance(accountId, balance - amount);
}
```

A SQL-level solution for a single debit operation is a conditional update **right inside the UPDATE statement**:

```sql
UPDATE accounts
SET balance = balance - 80
WHERE id = 1 AND balance >= 80;
```

The application must check the updated row count: `1` means the debit succeeded; `0` means the account was not found or funds were insufficient. For a transfer, place both the debit and credit operations into the same transaction.

**Consistency does not mean "all business rules are automatically checked by ACID."** The database knows the defined constraints and its isolation mechanism; developers must model, check, and protect the remaining invariants. "Consistency" in ACID is also not the distributed-systems concept of "every replica immediately reads the newest value."

## 4. Isolation — concurrent transactions and possible anomalies

Two transactions access the same dataset. Without an appropriate isolation mechanism, the outcome may depend on when they read and write. The **SERIALIZABLE** isolation level aims for an effect equivalent to a serial execution order for committed transactions, even though the DBMS may execute them concurrently. Lower levels trade off some guarantees to reduce contention or increase throughput.

### 4.1. Four anomalies to recognize

**Dirty read:** T1 updates the balance 100 → 20 without committing yet; T2 reads 20; then T1 rolls back. T2 relied on a value that never became a committed result.

**Non-repeatable read:** T1 reads balance 100; T2 updates it to 120 and commits; T1 reads the same row again within the same transaction and sees 120. T1 does not have a stable view allowing repeatable reads.

**Phantom read:** T1 runs `SELECT COUNT(*) FROM orders WHERE status = 'PENDING'` and gets 5; T2 inserts a row matching the condition and commits; T1 runs the query again and gets 6. The set of matching rows changed.

**Lost update:** T1 and T2 both read the value 100. T1 computes +10, T2 computes +20, and both write their precomputed values. Without proper protection, the final result may be 110 or 120 instead of 130. DBMSs, update syntaxes, and isolation levels differ in how they prevent or control this phenomenon.

There is also **write skew**: two transactions read the same overall condition, then update **two different rows**, violating a multi-row invariant even though neither row overwrites the other. For example, the rule "at least one doctor must always be on call": two doctors simultaneously see the other is on call and each removes themselves from the shift. Snapshot isolation/`REPEATABLE READ` in some DBMSs can still allow this situation.

### 4.2. Isolation levels and real-world caveats

| SQL Isolation Level | Dirty read | Non-repeatable read | Phantom read | Notes |
| --- | --- | --- | --- | --- |
| `READ UNCOMMITTED` | SQL standard may allow | Possible | Possible | PostgreSQL treats it as `READ COMMITTED`; do not assume uniform behavior across DBMSs. |
| `READ COMMITTED` | Prevented | Possible | Possible | Each statement may see a different committed snapshot. |
| `REPEATABLE READ` | Prevented | Prevented | Depends on DBMS/implementation | PostgreSQL also prevents phantoms at this level, but serialization anomalies can still occur. |
| `SERIALIZABLE` | Prevented | Prevented | Prevented | Committed transactions must be compatible with a serial schedule; the DBMS may abort a transaction to preserve correctness. |

This table summarizes the SQL standard with PostgreSQL-specific notes; it is **not a guarantee table for every database engine**. MySQL InnoDB, PostgreSQL, SQL Server, and Oracle differ in locking, MVCC, phantoms, snapshots, deadlocks, and how each level is implemented.

Example observed across two separate PostgreSQL connections:

```sql
-- Session T1:
BEGIN ISOLATION LEVEL READ COMMITTED;
SELECT balance FROM accounts WHERE id = 1;  -- 1000

-- Session T2, while T1 is still open:
BEGIN;
UPDATE accounts SET balance = 900 WHERE id = 1;
COMMIT;

-- Back to Session T1:
SELECT balance FROM accounts WHERE id = 1;  -- 900
COMMIT;
```

If T1 uses `REPEATABLE READ` instead of `READ COMMITTED`, the second read in T1 can still see 1,000 according to T1's own snapshot, assuming T1 has not modified that row itself. The `UPDATE` statement above is a standalone example for observing isolation, not a transfer operation.

### 4.3. Choosing tools to protect data

- **Constraints and conditional updates:** block invalid states and avoid check-then-update gaps, especially for balance checks.
- **Direct updates in the DB:** `SET balance = balance + ?` is usually safer than reading the value into the application, adding to it, and overwriting; you still must consider invariants and the enclosing transaction.
- **Pessimistic locking:** `SELECT ... FOR UPDATE` on supporting DBMSs when relevant records need to be locked; maintain a consistent lock ordering to reduce deadlocks.
- **Optimistic locking:** a `version` column and `UPDATE ... WHERE id = ? AND version = ?`; an updated row count of 0 signals a conflict, requiring a decision to retry or return an error.
- **`SERIALIZABLE` when logic depends on multi-row conditions:** accept the coordination overhead and handle `serialization_failure` by retrying the **entire transaction**, not just the failing statement.

Do not assume a higher isolation level is always better: you must simultaneously verify correctness, latency, deadlocks, retryability, and throughput.

## 5. Durability — committed data must persist durably

When the DBMS confirms a successful `COMMIT`, the changes have passed through the DBMS's durability mechanism. Many systems use a **write-ahead log (WAL)**: writing recovery information before or alongside acknowledging commit according to the corresponding sync policy; after a process crash, the DB can recover the committed state.

Distinguish these milestones:

1. The `UPDATE` statement returns success: **does not mean** the whole transaction has committed.
2. The application calls `COMMIT`: the request is sent to the DBMS, and the result may not have been received yet.
3. The DBMS acknowledges commit: changes are guaranteed according to the DBMS's durability/storage configuration.
4. The service returns HTTP `200`: a separate event that can fail even when the DB has already committed.

Durability is **not a promise that data survives every kind of disaster**. Storage hardware failure, disabled sync settings, asynchronous replica infrastructure, region-wide outages, or accidental administrative operations still require separate backup, restore, replication, and recovery policies.

If the connection drops right at commit time, the application may **not know whether the commit occurred or not**. Blindly resending a transfer operation can execute the transfer twice. You need an **idempotency key** with a unique constraint and a status lookup before retrying; `@Transactional` does not automatically guarantee "exactly once" between client and server.

## 6. ACID working together in a transfer flow

With A=1,000, B=500, and a request to transfer 200:

1. Start transaction T.
2. Validate that the amount is positive, source differs from destination, and account conditions hold.
3. Debit 200 from A only if A has sufficient balance; verify exactly one row is updated.
4. Credit 200 to B; verify exactly one row is updated.
5. If an error occurs in step 3 or 4, roll back T; if all steps are valid, commit T.
6. After commit, the state is stored durably; other transactions see the changes according to their own isolation.

Role of each letter: **A** keeps the two changes together; **C** requires non-negative balances, valid accounts, and no money created/lost; **I** handles concurrent transfers; **D** preserves the committed outcome.

A transaction only protects operations that genuinely belong to it. If after debiting the DB, the application calls an external bank API or sends an email, a DB rollback **does not recall** an HTTP request or email already accepted externally. Cross-system workflows require additional designs such as transactional outbox, idempotency, saga/compensation, or distributed transactions when infrastructure truly supports them.

## 7. ACID in Spring Framework: what does `@Transactional` control?

In standard Spring transaction management, a call to a bean through a **Spring AOP proxy** is intercepted by a transaction interceptor. The interceptor coordinates with `PlatformTransactionManager` to create or join a transaction, execute the business logic, and commit/roll back depending on status, exceptions, and configuration. For JDBC, operations must use the connection bound to the transaction; for JPA, the transaction manager coordinates the `EntityManager` and the database.

```text
Caller -> Spring proxy -> TransactionInterceptor
                         -> PlatformTransactionManager
                         -> DataSource/JPA transaction
                         -> Service method -> SQL statements
                         -> commit or rollback
                         -> Caller
```

The example below uses **Java 17+, Spring Boot with JDBC (`JdbcTemplate`), and PostgreSQL**. This is a service class placed inside an application that has already configured a `DataSource`, PostgreSQL driver, and transaction manager; it is **not a standalone Java program that can run with `javac` alone**.

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TransferService {
    private final JdbcTemplate jdbc;

    public TransferService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public void transfer(long sourceId, long destinationId, long amount) {
        if (amount <= 0 || sourceId == destinationId) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        int debited = jdbc.update(
            "UPDATE accounts SET balance = balance - ? " +
            "WHERE id = ? AND balance >= ?",
            amount, sourceId, amount
        );
        if (debited != 1) {
            throw new IllegalStateException("Missing source or insufficient funds");
        }

        int credited = jdbc.update(
            "UPDATE accounts SET balance = balance + ? WHERE id = ?",
            amount, destinationId
        );
        if (credited != 1) {
            throw new IllegalStateException("Missing destination");
        }
    }
}
```

**Reading the code properly:**

- `@Transactional` is applied when another object calls a **public method through the Spring proxy** and an appropriate transaction manager is present. Default is `Propagation.REQUIRED`: joins an existing transaction or starts a new one if none exists.
- `JdbcTemplate` uses the connection participating in the Spring-managed transaction. Debiting and crediting share **one physical transaction** in standard JDBC configuration.
- `UPDATE ... WHERE balance >= ?` puts the sufficient-funds check into the write operation to avoid a gap between check and update. You must check `debited`/`credited` (the number of updated rows).
- If the destination account does not exist, `IllegalStateException` exits the method: Spring rolls back the earlier debit as well. If both statements succeed, Spring requests a commit when the method finishes.
- `Isolation.READ_COMMITTED` configures a **new** transaction; when `REQUIRED` joins an existing transaction, do not assume the inner annotation upgrades the isolation level of the already-open transaction. Specific support and behavior are determined by the transaction manager/DBMS.
- `CHECK (balance >= 0)`, primary keys, and DB atomicity are additional layers of protection. In real-world applications, you must also handle overflow, currency units, idempotency, authorization, deadlocks, and the possibility that bidirectional transfers can cross-lock each other.

If `transferService.transfer(1, 2, 200)` is called through the Spring bean with initial data as in section 2, after commit A=800 and B=700. If `transferService.transfer(1, 999, 200)` is called, account 999 does not exist, the exception triggers a rollback, and the result is A=1,000 and B=500. These outcomes assume each run starts from the initial data state with no concurrent transactions.

### 7.1. Rollback rules and common pitfalls

Common defaults of Spring `@Transactional`:

| Scenario | Default outcome |
| --- | --- |
| Method returns normally | Transaction is committed, unless already marked rollback-only or commit fails. |
| `RuntimeException` or `Error` exits the method | Spring marks/performs rollback. |
| Checked exception (e.g. `IOException`) exits the method | By default does not force rollback, unless configured with a rollback rule or different global default. |
| Exception is caught and swallowed inside the method | The interceptor sees the method return normally; the transaction **may commit**. |
| Calling an annotated method via `this.method()` in the same bean in proxy mode | Internal call bypasses the proxy, so the annotation on the called method does not automatically create a new transaction. |

Example when a checked exception must also roll back:

```java
@Transactional(rollbackFor = Exception.class)
public void importAndValidate() throws Exception {
    // Perform operations on resources participating in the same transaction.
    // Throw a checked Exception when business logic requires aborting the transaction.
}
```

`rollbackFor = Exception.class` is a choice for a specific rule and should not be copied mechanically; which conditions roll back or commit must reflect business requirements. Newer versions of Spring Framework also provide mechanisms to configure **default rollback for all exceptions**; check your project's version and configuration before inferring from default behavior. If you must catch an exception inside a transaction, you should usually rethrow an appropriate exception or explicitly mark rollback-only, rather than logging and continuing as if it succeeded.

### 7.2. Propagation can change atomicity boundaries

- **`REQUIRED` (default):** shares the same physical transaction with the caller if one exists; an exception in the inner block may mark it rollback-only, causing the caller to receive `UnexpectedRollbackException` when attempting to commit.
- **`REQUIRES_NEW`:** suspends the outer transaction and starts an independent physical transaction; the inner transaction can commit even if the outer rolls back. Useful for certain independent operations, but **does not guarantee overall atomicity**; it may require an extra connection, risking connection pool exhaustion under heavy use.
- **`NESTED`:** typically maps to a JDBC savepoint when supported by the transaction manager and driver; partial rollback to a savepoint is not the same as a completely independent transaction. Do not assume it works across all JPA/DBMS setups.

Specify propagation for a clear goal. For instance, writing an audit log with `REQUIRES_NEW` can preserve the log even if a transfer rolls back, but the audit data and transfer data **no longer share the same commit decision**; you must accept and document this consequence.

### 7.3. Proxy, thread, and resource boundaries

- Place transactions at the service layer encompassing **the entire business unit**; call from another bean through the proxy. `private` methods, self-invocation, and instantiating objects manually with `new` usually prevent the annotation from being applied as expected in proxy mode.
- Imperative JDBC transactions are typically bound to the executing thread's context. They do not automatically propagate to `new Thread`, `@Async`, or background tasks. Reactive transactions use a different context mechanism and must follow `ReactiveTransactionManager`.
- `readOnly = true` is usually a **hint/optimization**, not a guarantee that all writes will be blocked. Nor does it automatically select a safe isolation level.
- A very long `@Transactional` method waiting on network or user input holds the transaction/connection/locks too long. Move external HTTP calls outside the lock-holding section whenever design allows.
- With multiple `DataSource`s/transaction managers, clarify which manager coordinates which operations. A single local transaction manager does not automatically provide atomicity across multiple DBs.

## 8. Verifying ACID with concrete scenarios

| Test case | What to observe | Related properties |
| --- | --- | --- |
| Successfully transfer 200 from A=1,000 to B=500 | A=800, B=700, total=1,500 | A, C, D |
| Destination account does not exist after debiting source | Exception thrown; A remains 1,000, B remains 500 after rollback | A, C |
| Withdraw more than balance | Source `UPDATE` returns 0; neither account changes | C, A |
| Two concurrent requests withdraw from the same account | Balance must never go negative; updated row count/constraints behave properly | I, C |
| Two transactions read the same row before/after a commit | Results match the actual isolation level | I |
| Stop DB process after commit is acknowledged and recover | Committed changes persist per DB guarantees/configuration | D |
| Client loses connection right when server commits | Do not assume commit did not happen; use request-id to reconcile | D and application-level idempotency |

In Spring integration tests, you can invoke the service through a bean and observe the data after an exception. The following JUnit snippet illustrates the idea (placed inside a `@SpringBootTest` with schema/fixture as in section 2, injecting `TransferService` and `JdbcTemplate`; this is a **test snippet**, not a standalone Java class):

```java
@Test
void missingDestinationRollsBackDebit() {
    assertThrows(IllegalStateException.class,
        () -> transferService.transfer(1L, 999L, 200L));

    Long after = jdbc.queryForObject(
        "SELECT balance FROM accounts WHERE id = ?",
        Long.class, 1L
    );
    assertEquals(1000L, after);
}
```

**Testing note:** test methods annotated with `@Transactional` in Spring Test normally auto-roll back at the end. To prove the service's real commit/rollback behavior, structure test setup/teardown and test transaction boundaries clearly; if needed, observe using an independent connection/transaction and use real concurrency tests for race conditions. Sequential tests cannot prove the absence of lost updates or write skew.

## 9. Clarifying common misconceptions

**"Having `@Transactional` gives you full ACID?"** No. The annotation coordinates transactions supported by the transaction manager. Atomicity and durability are primarily guaranteed by the DBMS, persistence configuration, and resource scope; consistency requires proper constraints/logic; isolation depends on the configured level.

**"If the method returns success, are all changes committed?"** If the method was called through a proxy and started the transaction there, commit usually occurs when the interceptor finishes the call. If the method only **joined an outer transaction**, the final commit is decided by the outer transaction. JPA's `flush()` synchronizes changes to the DB but does not mean commit.

**"Is `READ COMMITTED` enough to prevent all races?"** No. It prevents dirty reads, yet reads can see different snapshots, and read-check-write logic can still race. Use atomic SQL, constraints, locks, versions, or higher isolation depending on the invariant.

**"Does Serializable mean the DB runs one transaction at a time?"** No. The DB may run them concurrently and abort a conflicting transaction so that the result of committed transactions is equivalent to serial execution. The application must have a retry strategy for the transaction upon serialization/deadlock errors where appropriate.

**"Once committed, backups aren't needed?"** No. Durability and backup/disaster recovery are two different layers of protection. You still need a recovery policy and actual restore testing.

**"Does a DB rollback cancel published events or sent emails?"** No, unless that resource genuinely participates in the same appropriate transaction protocol. To keep DB and messaging in sync, consider transactional outbox: write an outbox record in the same DB transaction, then let an event publisher send it and have consumers handle it idempotently.

## 10. Checklist for designing transactions in Spring

1. Identify which **business unit** must commit/roll back together and which resources actually participate in the transaction.
2. State business invariants; enforce as many DB constraints as possible, and supplement with atomic SQL/locking/versioning for the rest.
3. Put `@Transactional` on public service methods called through a Spring proxy; verify the transaction manager and DataSource/JPA configuration.
4. Choose isolation based on which anomalies are unacceptable; observe the specific engine rather than relying solely on generic isolation tables.
5. Decide rollback rules for checked/unchecked exceptions; never swallow errors in a way that causes accidental commits.
6. Check propagation, internal calls, `@Async`, and external service operations before assuming everything is in one transaction.
7. Keep transactions short, handle retries for transient errors on the **entire transaction** when appropriate, and ensure requests are idempotent.
8. Test happy paths, mid-way failures, concurrency contention, and post-commit recovery; inspect transaction/SQL logs alongside actual database state.

## References

- Spring Framework — Using `@Transactional`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — Rolling Back a Declarative Transaction: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework — Transaction Propagation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- PostgreSQL — Transaction Isolation: https://www.postgresql.org/docs/current/transaction-iso.html
- PostgreSQL — SET TRANSACTION: https://www.postgresql.org/docs/current/sql-set-transaction.html