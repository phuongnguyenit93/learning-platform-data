# Simulating Deadlocks, Pool Exhaustion, Timeouts, and Disconnections

Database incidents in a Java application rarely occur in isolation. Under rising load, a transaction holding locks for too long forces other queries to wait; waiting queries hold connections in the pool; an exhausted pool causes new requests to time out. If the application retries without restraint, request volume and connection demand escalate further. If a connection drops right around commit time, the client may not know whether the operation was persisted and retries can create duplicate data.

This lab sets up a MySQL/InnoDB environment and a JDBC/HikariCP application to simulate four failure categories: deadlocks, pool exhaustion, timeouts, and network disconnections. The goal is to reproduce errors in a controlled way, gather evidence from both the application and MySQL, handle transactions properly, and verify data integrity after recovery.

The examples assume MySQL 8.0.16 or later, InnoDB, Java JDBC, and HikariCP so that `CHECK` constraints in the schema are enforced. Only run scenarios that intentionally lock tables, exhaust pools, or sever connections against an isolated test database. Never run them against production data or endpoints.

## Practice Objectives

After this lesson, you will be able to:

- Build schemas and fixtures sufficient to reproduce concurrency failures.
- Trigger repeatable deadlocks using two sessions locking rows in opposite orders.
- Distinguish deadlock error `1213` from lock wait timeout `1205`.
- Exhaust HikariCP using latches and confirm unacquired requests never send SQL.
- Distinguish pool acquisition timeout, JDBC query timeout, socket timeout, and InnoDB lock wait timeout.
- Simulate connection drops before, during, and after DML/`COMMIT`.
- Resolve ambiguous commit outcomes via idempotency keys and reconciliation queries.
- Inspect process lists, active transactions, lock waits, Hikari metrics, and application logs.
- Design bounded retries and re-execute the entire transaction when appropriate.

## 1. Lab Architecture

The lab consists of a MySQL test instance, a Java application using HikariCP, and an optional network proxy to inject controlled connection failures.

```text
                 Test runner
                     |
                     v
             Java service / JDBC
                     |
                HikariCP pool
                     |
              (optional proxy)
                     |
                     v
              MySQL 8.0 / InnoDB
               |       |       |
             accounts orders operation_requests
```

Each scenario requires:

1. A deterministic initial state.
2. A repeatable failure trigger.
3. Observable symptoms on both client and server.
4. Recovery actions matching the transaction state.
5. Assertions confirming data and resources returned to the expected clean state.

Do not rely on `Thread.sleep()` to enforce worker ordering. Use latches/barriers in Java or explicitly step through two SQL sessions so you know with certainty which session holds a lock before the other runs.

## 2. Preparing the Schema and Data

Create a dedicated test database:

```sql
CREATE DATABASE mysql_incident_lab
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

USE mysql_incident_lab;

CREATE TABLE accounts (
  account_id BIGINT UNSIGNED NOT NULL,
  owner_name VARCHAR(100) NOT NULL,
  balance DECIMAL(18, 2) NOT NULL,
  PRIMARY KEY (account_id),
  CONSTRAINT chk_accounts_balance_nonnegative CHECK (balance >= 0)
) ENGINE = InnoDB;

CREATE TABLE orders (
  order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  customer_id BIGINT UNSIGNED NOT NULL,
  status VARCHAR(30) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (order_id),
  KEY idx_orders_customer_status (customer_id, status)
) ENGINE = InnoDB;

INSERT INTO accounts (account_id, owner_name, balance)
VALUES
  (1, 'Account A', 1000.00),
  (2, 'Account B', 1000.00);
```

The `accounts` table is used for deadlock and lock wait scenarios; `orders` is used for query timeout or DML experiments. Use InnoDB so transactions and row locks exhibit the expected behavior.

### 2.1. Idempotency tables for ambiguous commit experiments

Create `payments` and `operation_requests` tables:

```sql
CREATE TABLE payments (
  payment_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  request_id VARCHAR(64) NOT NULL,
  amount DECIMAL(18, 2) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (payment_id),
  UNIQUE KEY uk_payments_request (request_id)
) ENGINE = InnoDB;

CREATE TABLE operation_requests (
  request_id VARCHAR(64) NOT NULL,
  payload_hash BINARY(32) NOT NULL,
  payment_id BIGINT UNSIGNED NOT NULL,
  completed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (request_id),
  UNIQUE KEY uk_operation_payment (payment_id)
) ENGINE = InnoDB;
```

In a production design, the payment and request marker must be written inside the same InnoDB transaction. Both tables enforce unique keys so one request ID can never create two payments. The lab schema is kept minimal to focus on commit and retry behavior.

Verify initial data:

```sql
SELECT * FROM accounts ORDER BY account_id;
SELECT COUNT(*) AS payment_count FROM payments;
SELECT COUNT(*) AS request_count FROM operation_requests;
```

Between runs, reset state only after all workers and transactions have stopped:

```sql
DELETE FROM operation_requests;
DELETE FROM payments;
UPDATE accounts SET balance = 1000.00 WHERE account_id IN (1, 2);
```

## 3. Capturing Baseline State Before Injecting Faults

Before each scenario, capture a baseline so you can distinguish healthy state from post-incident state.

```sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
  'Threads_connected',
  'Threads_running',
  'Max_used_connections',
  'Connection_errors_max_connections',
  'Aborted_connects',
  'Aborted_clients'
);

SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
  'max_connections',
  'innodb_lock_wait_timeout',
  'wait_timeout',
  'max_execution_time'
);

SHOW FULL PROCESSLIST;
```

On MySQL 8.0, you can inspect active transactions and lock waits:

```sql
SELECT
  trx_id,
  trx_state,
  trx_started,
  trx_mysql_thread_id,
  trx_rows_locked,
  trx_rows_modified
FROM information_schema.innodb_trx
ORDER BY trx_started;

SELECT
  REQUESTING_ENGINE_TRANSACTION_ID,
  REQUESTING_THREAD_ID,
  BLOCKING_ENGINE_TRANSACTION_ID,
  BLOCKING_THREAD_ID
FROM performance_schema.data_lock_waits;
```

If your monitoring account lacks permission to view all sessions or Performance Schema, use an appropriately privileged monitoring account in the lab.

On the HikariCP side, record `active`, `idle`, `pending`, `total`, acquisition time, usage time, and timeout counts. Attach a request ID or scenario ID to logs to correlate Java events with MySQL process lists and timestamps.

## 4. Scenario A — Creating a Deadlock with Two Sessions

A deadlock occurs when two transactions hold locks that the other needs, forming a wait cycle. InnoDB detects the cycle and picks one transaction as the victim; the typical error is `1213` (`ER_LOCK_DEADLOCK`, SQLState `40001`).

### 4.1. Preparing two sessions

Open two independent SQL connections to `mysql_incident_lab`. Run the commands in the sequence below, synchronizing between the two sessions at the indicated steps.

**Session A**

```sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 10.00
WHERE account_id = 1;
```

Session A now holds an exclusive row lock on account 1.

**Session B**

```sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 20.00
WHERE account_id = 2;
```

Session B now holds an exclusive row lock on account 2.

After both initial updates succeed, have each session update the other row:

**Session A**

```sql
UPDATE accounts
SET balance = balance + 10.00
WHERE account_id = 2;
```

**Session B**

```sql
UPDATE accounts
SET balance = balance + 20.00
WHERE account_id = 1;
```

Session A waits for account 2 held by B; Session B waits for account 1 held by A. InnoDB detects the deadlock and rolls back one transaction. The victim session receives error `1213`; the surviving transaction can proceed once the victim's locks are released.

### 4.2. Observing the deadlock

Immediately after the error occurs:

```sql
SHOW ENGINE INNODB STATUS\G
```

Locate the `LATEST DETECTED DEADLOCK` section to examine both transactions, held locks, and waiting locks. In the lab, you can enable logging for all deadlocks to capture evidence:

```sql
SET GLOBAL innodb_print_all_deadlocks = ON;
```

This setting is for observation; if modifying global variables in a shared environment, ensure authorization and restore the setting after the lab. In real environments, weigh log volume before enabling it.

### 4.3. Handling deadlocks properly

- Identify which transaction was rolled back; never assume only the final statement was undone.
- In InnoDB, a deadlock error typically rolls back the entire victim transaction.
- The application must re-execute the whole business unit of work in a fresh transaction if the operation is safe to retry.
- Use idempotency keys to avoid duplicate side effects when outcomes are uncertain.
- Reduce deadlocks by acquiring row locks in a consistent order across all code paths.

Never retry only the failed SQL statement if earlier statements in the same transaction were part of the same business operation. Doing so risks partial state or broken invariants.

### 4.4. Verifying results

Once both sessions finish with appropriate commits/rollbacks:

```sql
SELECT account_id, balance
FROM accounts
ORDER BY account_id;
```

Verify no dangling transactions remain, total balance equals the pre-test sum (if all changes were transfers between the two accounts), and the victim session terminated its transaction cleanly. After both sessions finish, reset the fixture to `1000.00` before re-running:

```sql
UPDATE accounts
SET balance = 1000.00
WHERE account_id IN (1, 2);
```

## 5. Scenario B — Distinguishing Deadlock from Lock Wait Timeout

A lock wait timeout does not necessarily involve a deadlock cycle. One transaction simply waits on a row lock longer than the configured limit.

**Session A — holding the lock**

```sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 5.00
WHERE account_id = 1;
```

Keep the transaction open without committing.

**Session B — setting a short timeout and waiting**

```sql
SET SESSION innodb_lock_wait_timeout = 2;
START TRANSACTION;

UPDATE accounts
SET balance = balance + 5.00
WHERE account_id = 1;
```

Session B waits on account 1. After the configured duration, it receives error `1205` (`ER_LOCK_WAIT_TIMEOUT`). By default, InnoDB rolls back only the timed-out statement; the transaction itself may remain open with earlier modifications intact. The application should roll back the entire transaction if it intends to retry the business operation from scratch.

Finish Session A:

```sql
COMMIT;
```

Then Session B:

```sql
ROLLBACK;
```

Comparison with deadlocks:

| Characteristic | Deadlock | Lock Wait Timeout |
|---|---|---|
| Condition | Cyclic lock wait graph | Waiting on a single lock exceeds timeout |
| Detection | InnoDB deadlock detector | `innodb_lock_wait_timeout` |
| Typical error code | `1213` | `1205` |
| Default rollback scope | Entire victim transaction | Timed-out statement; transaction may stay open |
| Retry | New transaction, entire business operation | Explicit full-transaction rollback in app before retry |

## 6. Scenario C — Controlled HikariCP Pool Exhaustion

Pool exhaustion occurs in the application when no idle connections remain to serve incoming requests. It can be reproduced without exhausting MySQL's `max_connections`.

### 6.1. Configuring a small test pool

```yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 2
      minimum-idle: 2
      connection-timeout: 1000
```

Use this configuration solely for the test profile. Spawn three workers where only the first two borrow connections and hold them; the third worker requests a connection only after a latch confirms the first two have acquired theirs.

### 6.2. Java pseudocode using latches

```java
CountDownLatch bothConnectionsBorrowed = new CountDownLatch(2);
CountDownLatch releaseConnections = new CountDownLatch(1);
ExecutorService executor = Executors.newFixedThreadPool(3);

Runnable holder = () -> {
    try (Connection connection = dataSource.getConnection()) {
        bothConnectionsBorrowed.countDown();
        releaseConnections.await();
    } catch (Exception e) {
        throw new RuntimeException(e);
    }
};

Future<?> first = executor.submit(holder);
Future<?> second = executor.submit(holder);

try {
    if (!bothConnectionsBorrowed.await(5, TimeUnit.SECONDS)) {
        throw new AssertionError("Pool holders did not acquire both connections");
    }

    long startedAt = System.nanoTime();
    try (Connection ignored = dataSource.getConnection()) {
        throw new AssertionError("Third borrower unexpectedly acquired a connection");
    } catch (SQLException expected) {
        long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
            System.nanoTime() - startedAt);
        // Verify this is a pool acquisition timeout and duration is near connectionTimeout.
    }
} finally {
    releaseConnections.countDown();
    executor.shutdownNow();
}

first.get();
second.get();
```

This pseudocode illustrates synchronization; cleanup releases the latch and shuts down the executor in `finally` so connections are not leaked if an assertion fails. Inspect the specific HikariCP exception/cause for your version to distinguish pool timeouts from MySQL connection errors. Do not assert elapsed time against an exact millisecond value because OS schedulers and CI environments introduce jitter; use a reasonable bounded range.

### 6.3. Expected results to verify

- The first two workers acquire both connections and hold them.
- The third worker times out inside `getConnection()`.
- The third worker never sends any SQL to MySQL.
- Hikari metrics show `active=2`, `idle=0`, and `pending` rising while waiting.
- After the two holders close their connections, the pool recovers and new requests acquire connections normally.
- Zero pending threads or active connections remain after cleanup.

This is a pool acquisition timeout, not MySQL error `1040`. MySQL itself may still have plenty of available connections.

## 7. Scenario D — Query Timeout vs. Lock Wait Timeout over JDBC

These two timeouts should be tested separately because one bounds statement execution on the JDBC client side while the other bounds row-lock waits inside InnoDB.

### 7.1. Query timeout with `SELECT SLEEP`

Example using a test connection:

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
         "SELECT SLEEP(10)")) {
    statement.setQueryTimeout(2);

    try (ResultSet resultSet = statement.executeQuery()) {
        resultSet.next();
    }
}
```

The driver is instructed to cancel the statement after roughly two seconds. Actual behavior depends on the driver and cancellation mechanism; tests should record the exception class, SQLState, elapsed duration, and connection state. A query timeout does not automatically roll back an entire transaction. If the connection remains valid with an open transaction, roll back per application logic; if the connection is no longer reliable, evict it from the pool.

### 7.2. Lock wait timeout over JDBC

Open Session A holding a row lock as in Scenario B. From another connection, run:

```sql
SET SESSION innodb_lock_wait_timeout = 2;
```

Then update the same row via JDBC. Verify the driver surfaces vendor error code `1205`, the transaction rolls back according to application policy, and the connection returns cleanly to the pool.

### 7.3. Do not confuse request-level timeouts with SQL timeouts

An HTTP gateway may time out a request before a JDBC query timeout fires. Stopping the HTTP client wait does not automatically cancel the running statement on the database server. Applications must propagate deadlines/cancellations downward while still governing transaction and resource lifecycles.

Order timeouts intentionally: request deadline large enough for the service to finish or abort cleanly; pool acquisition timeout shorter than the remaining deadline; connect/query/socket timeouts tuned to each operation. Never set them all to the same value and assume they coordinate cleanly.

## 8. Scenario E — Disconnection Before and During DML

To inject controlled network faults, place a test proxy between the application and MySQL, such as Toxiproxy. Point JDBC at the proxy; the proxy forwards traffic normally until the test enables faults.

Failure points:

| Breakpoint | How to Trigger | What to Observe |
|---|---|---|
| Before connect | Proxy stops accepting/forwarding new connections | Connect timeout/refused; zero SQL sent |
| While connection idle | Reset an idle TCP socket | Pool validation detects stale connection and discards it |
| During read query | Inject latency then cut response | JDBC throws socket/communications error; connection may close |
| During DML | Sever network after sending request to server | Client cannot tell whether statement finished; in InnoDB individual statements are atomic, yet the transaction may remain uncommitted |
| After DML, before commit | Drop session before `COMMIT` reaches server | Uncommitted transaction rolls back once the server detects session closure |

Do not use `KILL QUERY` as a substitute for disconnection tests: it tests server-side statement cancellation rather than socket/network states. Likewise, simply shutting down MySQL does not cover every network failure mode.

After a connection drops, never reuse that connection for further statements. It must be closed/evicted from the pool. If the transaction never committed, the server normally rolls back upon session teardown; however, if the client does not know whether the request reached the server, reconcile by request ID before retrying.

## 9. Scenario F — Lost Response Around `COMMIT`

This is the most critical scenario because the client can receive an exception even though MySQL already committed the transaction successfully.

### 9.1. Writing the business row and idempotency record in the same transaction

Every operation carries a stable `request_id`. Inside the same InnoDB transaction:

1. Insert the payment with the request ID.
2. Insert the operation request record containing the payload hash and payment ID.
3. Commit.

Processing flow example:

```java
PaymentResult createPayment(PaymentCommand command) throws SQLException {
    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);
        try {
            long paymentId = insertPayment(connection, command);
            insertOperationRequest(
                connection,
                command.requestId(),
                command.payloadHash(),
                paymentId
            );
            connection.commit();
            return new PaymentResult(paymentId);
        } catch (SQLException e) {
            try {
                connection.rollback();
            } catch (SQLException rollbackError) {
                e.addSuppressed(rollbackError);
            }
            throw e;
        }
    }
}
```

This is a skeleton for the first execution attempt. In real implementations, handle duplicate request IDs by reading the stored outcome and comparing payload hashes; never generate a fresh request ID when retrying the same business action. If rollback fails or the connection broke, never reuse a connection whose state is indeterminate.

### 9.2. Reconciliation after a commit error

If the socket breaks during `commit()`:

1. Log the request ID, timestamp, and operation type; treat the outcome as indeterminate.
2. Evict the broken connection from the pool.
3. Open a fresh connection to the authoritative primary—never rely on an asynchronous replica to conclude absence.
4. Query `operation_requests` by request ID.
5. If a record exists, verify the payload hash and return the already-created payment.
6. If no record is visible yet, do not immediately assume the old transaction rolled back: the server may not yet have detected the dropped session.
7. Retry using the exact same request ID and unique keys. If the earlier transaction committed, unique constraints surface a duplicate; if it rolled back, the retry creates the record cleanly. Handle lock waits/duplicates according to idempotency rules.

Unique indexes on `payments.request_id` and `operation_requests.request_id` serialize concurrent attempts sharing a key. If two requests share a key with different payload hashes, reject the request rather than returning the other payload's outcome.

### 9.3. Reproducing a committed transaction whose ACK is lost

To test ambiguous commits accurately, the proxy must let the `COMMIT` reach MySQL and drop the server response back to the client only after the server has processed the commit. A raw TCP proxy does not natively understand MySQL packet boundaries; without protocol inspection, use a test hook or server-side synchronization to confirm commit completion before dropping the response.

Two distinct cases must be tested:

**Case 1 — commit already completed:**

- Client sends the transaction and `COMMIT`.
- Test confirms the server committed.
- Proxy drops the response to the client.
- JDBC raises a communications error.
- Client reconnects with the same request ID.
- Outcome must return the existing payment; payment count for that request ID stays equal to one.

**Case 2 — `COMMIT` never reached the server:**

- Client sends DML, then proxy blocks `COMMIT` before it reaches the server and resets/closes the socket so MySQL detects session loss.
- Server closes the session and rolls back the uncommitted transaction.
- Client retries with the same request ID.
- The retry creates exactly one payment and one operation record.

Merely pulling the network cable or killing the server randomly leaves it unclear which case a test actually exercised. Explicit synchronization points and post-attempt data verification are required.

## 10. Scoping Retries Appropriately

Never retry every exception. Classify errors first:

| Error | Handling Strategy |
|---|---|
| Deadlock `1213` | InnoDB rolled back the victim transaction; re-run the entire transaction in a new transaction if idempotent |
| Lock wait timeout `1205` | Statement timed out; roll back the full transaction in the application before retrying |
| Pool acquisition timeout | No connection acquired so no SQL ran; investigate pool/DB health and apply backpressure |
| Connect failure prior to connecting | Bounded connect retries acceptable if endpoint/network recovers |
| Query timeout | Inspect transaction and connection state; roll back if needed—never assume query cancel rolled back the whole transaction |
| Socket failure during DML | Client outcome uncertain; reconcile via idempotency key prior to retry |
| Socket failure during `COMMIT` | Ambiguous outcome; never mint a new request ID, reconcile on primary |
| Duplicate key | Read existing record and compare payload hash; never retry infinitely |
| Missing privileges / bad SQL / invalid data | Fix the root cause; retrying will not help |

Retry policies should define maximum attempts, exponential backoff, jitter, and an overall deadline. Full-transaction retries must sit outside the failed transaction; in Spring, place retry logic outside the `@Transactional` method or start a fresh transaction per attempt. Never re-run statements inside an already rolled-back or indeterminate transaction.

## 11. Integrated Diagnostic Runbook

When tests or production surface errors, follow this sequence:

1. **Pinpoint where it failed:** `getConnection()`, `executeQuery/executeUpdate`, `commit()`, or request deadline.
2. **Capture error details:** exception class, SQLState, vendor code, request/scenario ID, and timestamp.
3. **Inspect the pool:** active, idle, pending, total, acquire time, usage time, and leak warnings.
4. **Inspect MySQL:** `Threads_connected`, `Threads_running`, process list, and error log.
5. **Inspect transactions/locks:** `innodb_trx`, `data_lock_waits`, and `SHOW ENGINE INNODB STATUS`.
6. **Classify the transaction:** confirmed rolled back, still open, confirmed committed, or indeterminate.
7. **Recover:** roll back active transactions; evict broken connections; reconcile idempotency keys; retry full transactions when safe.
8. **Verify:** row counts, balances, payments per request ID, pool metrics, and absence of dangling transactions.

Quick diagnostic queries:

```sql
SHOW FULL PROCESSLIST;
SHOW ENGINE INNODB STATUS\G
SELECT *
FROM information_schema.innodb_trx
ORDER BY trx_started;

SELECT *
FROM performance_schema.data_lock_waits;
```

## 12. End-of-Lab Test Matrix

| ID | Scenario | Trigger | Expected Error / Symptom | Data / Resource Assertions |
|---|---|---|---|---|
| A1 | Deadlock | Two sessions lock two accounts in opposite orders | One transaction receives `1213` | Victim rolls back; survivor finishes; total balance conserved |
| B1 | Lock wait timeout | A holds row lock, B waits with 2s timeout | B receives `1205` | App rolls back full transaction; no dangling locks |
| C1 | Pool exhaustion | Pool size 2, two holders keep connections, third waits | Hikari acquisition timeout | Zero SQL sent by third borrower; pool recovers after release |
| D1 | Query timeout | `SELECT SLEEP(10)` with short query timeout | JDBC reports query timeout/cancel | Connection/transaction cleaned up; no leaked resources |
| E1 | Disconnect during DML | Proxy resets socket mid-query | Communications/socket error | No blind retry; request ID and data state reconciled |
| F1 | Commit ACK lost | Forward `COMMIT`, drop response after commit | Client sees connection error | Retry with same key returns existing payment; no duplicate rows |
| F2 | Commit never reached server | Proxy blocks `COMMIT` before server | Client sees connection error | Old transaction rolls back; retry with same key creates one payment |

Every test must clean up inside `finally` or lifecycle hooks. If a test breaks a connection, close/evict it; if a test holds a lock, always roll back/close Session A; if a proxy fault is active, restore the proxy before the next test. The suite must finish with zero abnormal active/pending pool counts and the database restored to its baseline fixture.

## 13. Integrated Practice Exercise

A money transfer service runs on MySQL 8.0/InnoDB and HikariCP. Two workers update accounts in different orders; the pool has `maximumPoolSize=4`. An endpoint starts timing out under rising load, and logs show `1213`, `1205`, and `Communications link failure`. Some clients retry and create duplicate payments.

Execute the lab in sequence:

1. Create the schema, seed two accounts, and create the idempotency tables.
2. Run the two-session deadlock; capture `SHOW ENGINE INNODB STATUS` and identify the victim.
3. Run the lock wait timeout separately; explain why its rollback scope differs from deadlocks.
4. Run pool exhaustion with two connection holders and a third borrower on a size-2 pool; verify MySQL has not necessarily hit `max_connections`.
5. Run query timeout using `SELECT SLEEP()` and inspect transaction/connection state after the error.
6. Use a proxy to simulate disconnects before sending DML and while DML is executing.
7. Trigger a synchronized ambiguous commit: server commits, client loses the ACK.
8. Retry with the same request ID, verify payload hash, and prove only one payment exists.
9. Repeat with `COMMIT` blocked before reaching the server and prove the old transaction leaves no payment behind.
10. Collect Hikari metrics, process lists, transactions, lock waits, and application logs for each scenario.
11. Add a bounded retry policy and backpressure; re-run load tests to confirm no retry storm forms.
12. Reset fixtures, shut down proxies and executors, and confirm zero leaked connections or transactions remain.

### Assessment Questions

1. What conditions produce a deadlock, and why does InnoDB roll back only one victim transaction?
2. What is the key difference between error `1213` and error `1205`?
3. Why can pool acquisition timeouts occur while MySQL still has free connections?
4. What does Hikari `active=max`, `idle=0`, `pending>0` tell you, and what does it not prove?
5. Why should you never hold a transaction open while making HTTP calls or waiting on a latch?
6. Does a query timeout automatically roll back the entire transaction?
7. When a socket drops during DML or `COMMIT`, why can't the exception tell you for certain whether data committed?
8. Why must the idempotency record commit in the same transaction as the payment?
9. Why should reconciliation read from the authoritative primary rather than an asynchronous replica?
10. Where should retry logic live so each attempt runs in a fresh transaction?
11. Which assertions prove the connection pool and database recovered cleanly after a test?

## Conclusion

An effective integrated lab triggers each failure at the exact right layer and verifies state afterward. Deadlock `1213` typically rolls back the entire victim transaction; lock wait timeout `1205` defaults to rolling back only the waiting statement, requiring the application to decide transaction rollback. Pool exhaustion happens during connection borrowing and can occur long before MySQL hits `max_connections`. Query timeouts, socket timeouts, and request deadlines also govern distinct scopes. In particular, lost responses around `COMMIT` leave clients with ambiguous outcomes; idempotency keys and unique constraints enable safe reconciliation and retries without creating duplicate transactions. Use synchronized latches and fault injection, observe both HikariCP and MySQL, and finish the lab only after data, transactions, and pools are verified clean.
