# Do Not Blindly Retry the Entire Operation When the Commit Outcome Is Unknown

In Spring Framework Data Access, an exception during SQL execution or at the end of a transaction **does not always tell you for certain whether the business effect was committed or not**. The hardest case occurs when the database has received and processed `COMMIT`, yet the application loses connectivity, times out, or fails to receive the confirmation response. From the application's perspective, the outcome is **unknown** (*commit outcome unknown*): data may have been permanently written, or the transaction may have failed.

If the application immediately re-runs the entire business operation, actions like deducting funds, creating orders, booking reservations, or dispatching warehouse commands can happen **twice**. `@Transactional` and rollback mechanisms do not automatically prevent duplicates when the prior commit already completed and the client merely lost the return response.

This lesson focuses on recognizing unknown states, classifying exceptions appropriately, designing **idempotency keys** and **reconciliation** (verifying committed state), and only then deciding whether retrying is permitted.

## 1. What Happens If the COMMIT Response Is Lost?

Consider deducting 30 units from an account with an initial balance of 100:

~~~text
Application                   Database
   |                              |
   | BEGIN                        |
   |----------------------------->|
   | UPDATE balance = 100 - 30    |
   |----------------------------->|
   | COMMIT                       |
   |----------------------------->|
   |                    commit succeeded: balance = 70
   |         X connection lost / ACK not received
   |
   | timeout / exception
   |      |
   |      +-- Unknown whether database committed or rolled back
~~~

If the client retries with a **new** `UPDATE wallet_account SET balance = balance - 30` statement, the second transaction can succeed and reduce the balance to **40**. The database is not wrong: it processed two valid transactions. The bug is that the application lacks a mechanism to recognize this is **the same business intent** being resubmitted.

States to distinguish:

| State | Evidence | Appropriate action |
| --- | --- | --- |
| **Committed** | Found committed receipt/business outcome with matching request ID and valid payload | Return the prior result; **do not** apply the effect again |
| **Definitely rolled back** | Transaction manager/database has proof of successful rollback and no side effects outside the transaction | May retry if the error is genuinely recoverable and business preconditions still hold |
| **Unknown** | Connection drop, timeout at commit, process crash near commit boundary, no reliable confirmation | Reconcile by operation ID; not yet permitted to conclude "failed" |
| **In progress** | Prior call has not finished or another worker holds processing rights for the same ID | Return `PENDING`/check back later, or safely retry with the same key under deduplication |
| **Business rejected** | Final outcome such as insufficient balance or invalid request | Return the proper business outcome; do not retry the identical request in an endless loop |

**Not receiving an ACK does not mean the database did not commit.** Likewise, an HTTP timeout to a service does not prove the service did not run the transaction: the request may continue running after the client stops waiting.

### Why Can't ROLLBACK Rescue a Completed Commit?

`ROLLBACK` acts only on a transaction that is still rollback-capable. Once `COMMIT` has succeeded, calling rollback from the application **cannot undo** committed data. Spring's `PlatformTransactionManager` API documentation further emphasizes: after `commit(status)` returns or throws an exception, the transaction manager considers the transaction completed and cleaned up; **do not call `rollback(status)` again on the same `TransactionStatus`**. Doing so causes state errors and proves nothing about the commit outcome.

Therefore, recovery workflows must rely on **committed business evidence** and a safe repeatable API, rather than trying to roll back a transaction with an ambiguous outcome.

## 2. What Do Spring Exceptions Tell Us—and What Don't They?

`JdbcTemplate` converts many JDBC `SQLException`s into the `DataAccessException` hierarchy. Transaction managers can throw `TransactionException` when commit/rollback or transaction management fails. These class names are very helpful for diagnostics, yet **they do not automatically answer the question "has this business operation taken effect once or not?"**.

| Signal | Often suggests | Safety rule |
| --- | --- | --- |
| `TransientDataAccessException` / subclasses | Infrastructure or contention error that may disappear on a later try | "Recoverable by retry" **is different from** "retrying the whole business logic is safe"; you must know state and idempotency |
| `CannotGetJdbcConnectionException` before starting DB work | Could not obtain a connection to perform this attempt's work | Still check whether a **previous call** with the same request ID committed; do not infer from this exception alone |
| `DataAccessResourceFailureException` or connection drop while writing | DB resource failed; SQL may already have been sent | Individual statement outcomes, transactions, or non-DB side effects must be reconciled |
| `TransactionSystemException` at commit/rollback | Transaction manager hit a system error, e.g. SQLException from JDBC commit | Do not automatically conclude COMMIT failed; inspect cause and commit status |
| `UnexpectedRollbackException` | Transaction coordinator rolled back when caller expected commit | Signals rollback of the coordinator-managed transaction; still check external side effects or independent committed transactions |
| `DuplicateKeyException` | Unique constraint violation | For an idempotency key, may be a valid duplicate call, or **a different payload reusing the key**; query and compare requests |
| `OptimisticLockingFailureException` or similar concurrency error | A record no longer satisfies version/concurrency conditions | Must reload state and check validity before planning a retry |
| Validation, foreign key, or data type error | Invalid request or broken contract | Retrying as-is rarely helps; fix cause or return error to client |

`DataSourceTransactionManager` can wrap JDBC commit/rollback failures in `TransactionSystemException`; `JdbcTransactionManager` can also translate certain resource errors into corresponding `DataAccessException`s. Therefore, **do not write a rule like "catch TransactionSystemException for unknown outcome, while DataAccessException guarantees rollback"**. Look at *which phase the error occurred in*, whether commit/rollback evidence exists, and which backend is in use.

### Distinguishing Pre-COMMIT Errors from Errors Right at COMMIT

- **SQL error inside a transaction**, unchecked exception escapes and the transaction manager rolls back successfully: there is a basis to conclude changes **of that transaction** rolled back. Effects outside the transaction or a previously committed `REQUIRES_NEW` remain independent.
- **Error during commit**: the database may have received/written the commit before the connection dropped. An I/O error is not proof of a successful rollback.
- **Error after commit, before API response**: the transaction actually committed, yet the caller may see only a timeout or closed HTTP connection.
- **Process killed near commit**: after restart, the original exception is gone; query outcomes by a stable ID.

SQLState, vendor error codes, stack traces, and JDBC logs help pinpoint causes, but **do not replace reconciliation** in cases without final proof.

## 3. Retry Differs from Re-Running Operations with Side Effects

An **idempotent** operation given the same repeated intent still leads to the same final business effect. A pure read is usually easy to retry. An incremental or decremental update is different.

| Operation | What happens if executed twice | What to do |
| --- | --- | --- |
| Read-only `SELECT` from DB | Usually creates no side effect | May retry per read-timeout policy; watch consistency when reading replicas |
| `UPDATE balance = balance - 30` | Deducts 60 if both commit | Require business key + transaction/unique constraint to prevent duplicates |
| `INSERT` with fixed primary key | Second call may violate unique constraint | Use key to identify same intent, return stored result, and verify payload |
| `UPDATE status = 'CLOSED'` | Final value may still be `CLOSED` | Not necessarily safe if triggers, versions, audits, emails, events, or state-transition guards exist |
| Creating an order with a new server-generated ID each time | May create two different orders | Client generates/stabilizes operation ID, DB deduplicates |
| Sending email, calling payment gateway, or publishing message | May trigger two side effects in external systems | Use external system's idempotency API, outbox, deduplication, or two-way reconciliation |

The concept "safe to retry" always applies to the **entire set of effects** of a request, not just the main SQL statement. An `UPDATE` that is idempotent on row data might still insert extra audit rows or emit events on each execution.

Comparison example:

~~~sql
-- NOT safe for blind retry: each run reduces balance
UPDATE wallet_account SET balance = balance - 30 WHERE id = 1;

-- Guard prevents negative balance, yet does NOT prevent double deduction:
UPDATE wallet_account
SET balance = balance - 30
WHERE id = 1 AND balance >= 30;
~~~

The balance guard is a necessary business protection, **not idempotency**. If the account has enough funds for two deductions, both updates can still succeed.

## 4. The Right Model: Request ID + Receipt + Transaction

Every **business intent** must have a stable identifier, e.g., `request_id = 'debit-2026-0042'`. The client **keeps the same ID when resending** after a lost response. Do not generate a fresh UUID on each retry, because the database would treat them as distinct requests.

Data stored in the same transaction includes:

~~~text
wallet_account
  id                 PRIMARY KEY
  balance

request_receipt
  request_id         PRIMARY KEY  <-- database-level deduplication
  account_id
  amount
  balance_after      <-- committed business outcome
~~~

Inside **one single** transaction:

1. Check `request_receipt` by `request_id`.
2. If it already exists, compare `account_id`, `amount`, and key fields with the current request. If they match, return the prior result; if they differ, reject ID reuse.
3. If it does not exist, execute business logic (e.g., check sufficient balance and debit), write the receipt and final outcome.
4. Commit **both the update and the receipt**. If the transaction rolls back, both roll back.

The `PRIMARY KEY(request_id)` constraint is the DB-level safeguard; do not rely solely on `if (!exists) insert` in Java. Under concurrency, **two transactions can both check and see "absent"**. The DB unique constraint must ensure only one receipt row commits for that key. The losing transaction must roll back, after which the caller checks the committed receipt and returns the appropriate result. Across isolation levels and drivers, test actual lock errors, lock waits, or deadlocks.

**Do not write the receipt in a separate transaction before updating the account**, because a "successful" receipt could appear even if the debit fails. Similarly, do not commit the debit and save the receipt in a later transaction; if the app crashes between the two steps, you can no longer tell from the receipt alone whether the debit occurred.

### One Request ID Must Not Be Used for Two Different Intents

For example, the same `request_id` is sent again with the amount changed from 30 to 80. That is **not a retry** but a different request. Return a conflict/validation error and never pretend the old result applies to the new request. For multi-field payloads, store a **fingerprint** from a canonical representation of the intent-defining fields (account, amount, currency, recipient, operation type, schema version); define stable ordering, string normalization, and fingerprint versioning.

Keys should be scoped to tenant/user if IDs are only unique within that scope: e.g., unique `(tenant_id, request_id)`. Payload comparison must avoid leaking another tenant's data. Receipt retention must span the retry window and business audit requirements; purging receipts too early can let a late retry produce a duplicate effect.

## 5. Runnable Java 17 Example: Simulating Lost Response After Commit

This example uses **Spring JDBC, `TransactionTemplate`, and in-memory H2**. The program demonstrates two scenarios:

- **Without deduplication**: calling debit twice drops the balance from 100 to 40.
- **With an in-transaction receipt**: debiting 30 leaves 70; simulating the client losing the response **after the commit actually succeeded**; reading the receipt and retrying with the **same request ID** performs no extra debit.

Important point: the example **does not fabricate a JDBC error inside `Connection.commit()`**. The simulated error sits solely at the response layer after the transaction finishes. It illustrates why the client state "UNKNOWN" can differ from the database state "COMMITTED".

Project structure:

~~~text
commit-unknown-demo/
├── pom.xml
└── src/main/java/example/CommitUnknownDemo.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>commit-unknown-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.4.240</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.6.4</version>
                <configuration>
                    <mainClass>example.CommitUnknownDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

File `src/main/java/example/CommitUnknownDemo.java`:

~~~java
package example;

import java.util.List;
import java.util.Optional;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

public final class CommitUnknownDemo {

    record Receipt(String requestId, long accountId,
                   int amount, int balanceAfter) {}

    record Result(boolean newlyApplied, int balanceAfter) {}

    static final class ReplyLostException extends RuntimeException {}

    static final class DebitService {
        private final JdbcTemplate jdbc;
        private final TransactionTemplate tx;

        DebitService(JdbcDataSource dataSource) {
            this.jdbc = new JdbcTemplate(dataSource);
            this.tx = new TransactionTemplate(
                    new DataSourceTransactionManager(dataSource));
        }

        Result debitOnce(String requestId, long accountId, int amount) {
            if (requestId == null || requestId.isBlank() || amount <= 0) {
                throw new IllegalArgumentException("Invalid request");
            }

            return tx.execute(status -> {
                Optional<Receipt> prior = findReceipt(requestId);
                if (prior.isPresent()) {
                    Receipt saved = prior.get();
                    if (saved.accountId() != accountId
                            || saved.amount() != amount) {
                        throw new IllegalArgumentException(
                                "Same key, different intent");
                    }
                    return new Result(false, saved.balanceAfter());
                }

                int changed = jdbc.update("""
                        UPDATE wallet_account
                        SET balance = balance - ?
                        WHERE id = ? AND balance >= ?
                        """, amount, accountId, amount);
                if (changed != 1) {
                    throw new IllegalStateException(
                            "Account missing or insufficient balance");
                }

                int balance = jdbc.queryForObject(
                        "SELECT balance FROM wallet_account WHERE id = ?",
                        Integer.class, accountId);

                jdbc.update("""
                        INSERT INTO request_receipt
                            (request_id, account_id, amount, balance_after)
                        VALUES (?, ?, ?, ?)
                        """, requestId, accountId, amount, balance);

                return new Result(true, balance);
            });
        }

        Optional<Receipt> findReceipt(String requestId) {
            List<Receipt> rows = jdbc.query("""
                    SELECT request_id, account_id, amount, balance_after
                    FROM request_receipt
                    WHERE request_id = ?
                    """,
                    (rs, rowNum) -> new Receipt(
                            rs.getString(1), rs.getLong(2),
                            rs.getInt(3), rs.getInt(4)),
                    requestId);
            return rows.stream().findFirst();
        }

        int balance(long accountId) {
            return jdbc.queryForObject(
                    "SELECT balance FROM wallet_account WHERE id = ?",
                    Integer.class, accountId);
        }
    }

    private static void applyThenLoseReply(DebitService service) {
        service.debitOnce("debit-2026-0042", 1L, 30);
        // TransactionTemplate.execute completed and COMMIT succeeded.
        // Simulate response lost on the way back to the client.
        throw new ReplyLostException();
    }

    public static void main(String[] args) {
        JdbcDataSource dataSource = new JdbcDataSource();
        dataSource.setURL("jdbc:h2:mem:commit_unknown;DB_CLOSE_DELAY=-1");
        dataSource.setUser("sa");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.execute("""
                CREATE TABLE wallet_account (
                    id BIGINT PRIMARY KEY,
                    balance INT NOT NULL
                )
                """);
        jdbc.execute("""
                CREATE TABLE request_receipt (
                    request_id VARCHAR(80) PRIMARY KEY,
                    account_id BIGINT NOT NULL,
                    amount INT NOT NULL,
                    balance_after INT NOT NULL
                )
                """);
        jdbc.update("INSERT INTO wallet_account(id, balance) VALUES (1,100)");
        jdbc.update("INSERT INTO wallet_account(id, balance) VALUES (2,100)");

        // Control: blind retry on account 2.
        jdbc.update("""
                UPDATE wallet_account
                SET balance = balance - 30 WHERE id = 2
                """);
        jdbc.update("""
                UPDATE wallet_account
                SET balance = balance - 30 WHERE id = 2
                """);
        int naiveBalance = jdbc.queryForObject(
                "SELECT balance FROM wallet_account WHERE id = 2",
                Integer.class);
        System.out.println("naive balance=" + naiveBalance);

        // Account 1 has a receipt saved in the same transaction.
        DebitService service = new DebitService(dataSource);
        try {
            applyThenLoseReply(service);
        } catch (ReplyLostException ex) {
            System.out.println("client result=UNKNOWN");
        }

        // Reconcile using the stable key after the transaction ended.
        String key = "debit-2026-0042";
        System.out.println("reconcile="
                + (service.findReceipt(key).isPresent()
                        ? "APPLIED" : "ABSENT"));

        // If the caller still needs to resend, use the SAME key and payload.
        Result retry = service.debitOnce(key, 1L, 30);
        System.out.println("same-key retry newlyApplied="
                + retry.newlyApplied());
        System.out.println("safe balance=" + service.balance(1L));
        int count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM request_receipt",
                Integer.class);
        System.out.println("receipts=" + count);
    }
}
~~~

In the project root directory, with JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java
~~~

Lines printed by the program with H2 and the data above:

~~~text
naive balance=40
client result=UNKNOWN
reconcile=APPLIED
same-key retry newlyApplied=false
safe balance=70
receipts=1
~~~

Walkthrough:

1. Two "naive" updates subtract 30 on account 2, so the balance goes 100 → 70 → 40.
2. The first `debitOnce` call with a stable ID on account 1 updates 100 → 70 and writes the receipt in the **same transaction**. `TransactionTemplate.execute` returning means the transaction completed successfully in the example.
3. `ReplyLostException` is thrown only **after** the first commit. It represents the client failing to receive the response, not evidence of rollback.
4. Querying the receipt in a subsequent read returns `APPLIED`.
5. Retrying with the same ID and payload reads the receipt and returns `newlyApplied=false`; no extra debit runs. Balance stays 70, with only one receipt.

What the example **does not prove**: durability of in-memory H2 across process restarts, all lock/concurrency strategies of production DBs, or how a JDBC driver handles a disconnect mid-`COMMIT`. H2 only simulates application logic when an ACK is lost. Test with your target DBMS and proper fault-injection tests before using for high-value transactions.

### Why Must Data and Receipt Use the Same DataSource?

`TransactionTemplate` uses `DataSourceTransactionManager(dataSource)` and `JdbcTemplate` uses **that exact same DataSource**. While the transaction callback runs, `JdbcTemplate` obtains the connection bound by Spring to the active transaction. Thus `UPDATE wallet_account` and `INSERT request_receipt` participate in the same transaction.

If one operation opens its own connection via `DriverManager.getConnection`, uses a different DataSource, or opens `REQUIRES_NEW` and commits independently, the receipt and debit may **no longer be atomic**. Design must rely on real transaction boundaries, not just proximity of Java lines.

### Concurrent Contention Still Needs a Unique Constraint

In the sequential demo, checking for the receipt before inserting looks sufficient. In production, two requests with the same key can hit two instances:

~~~text
Instance A               Instance B
  SELECT receipt: none     SELECT receipt: none
  UPDATE account           UPDATE account (may wait on lock)
  INSERT receipt           INSERT receipt (hits unique)
  COMMIT                   rolls back or gets duplicate-key
~~~

Let the database enforce the unique key. When `DuplicateKeyException` or lock timeout occurs, handle it **outside the failed transaction**, then look up the committed receipt and compare payloads. Do not catch the unique error inside the callback and try to commit as if all preceding SQL was valid. Transaction behavior after an SQL error varies across databases and isolation levels; let the transaction roll back when needed.

When the receipt is not yet visible because the first transaction is still running, the outcome may still be `IN_PROGRESS/UNKNOWN`. You can retry with the **same key** if all writes and deduplication are solid and retry budget, timeout, and backoff are set; or return an in-progress status so the client polls later. Never change the key to "dodge duplicate key".

## 6. Workflow for Handling Unknown Commits in a Spring Application

A practical workflow can be illustrated as follows:

~~~text
Receive request with stable request_id + normalized payload
            |
            v
Look up receipt/business state by request_id
            |
       +----+-------------------+
       |                        |
   Result exists            No result yet
       |                        |
Compare payload             Determine if in-flight?
       |                        |
  +----+----+                 +--+----------------+
  |         |                 |                   |
Match     Mismatch         Running          Definitely not running?
  |         |                 |                   |
Return   CONFLICT       PENDING/RECONCILE     Invoke safe attempt
result                    (await state)       with same request_id
                                                  |
                                                  v
                                        DB transaction + unique key
                                                  |
                                        +---------+---------+
                                        |                   |
                                      Commit            Error/timeout
                                        |                   |
                                    Return result    Classify and reconcile
~~~

Here "definitely not running" cannot always be proven by a single `SELECT`. A write might be in-flight, uncommitted, or lagging on a read replica. Therefore, **re-invoking an idempotently designed operation** is usually more practical than trying to infer "absence = failed" from one query.

Sequence to apply:

1. **Classify the error:** is it invalid input, confirmed rollback, concurrency failure, transient resource issue, or commit/response unknown? Did any side effects already run outside the transaction?
2. **Preserve identity:** reuse the exact same `request_id`, tenant, and payload fingerprint of the original intent.
3. **Query the source of truth:** prefer reading committed state from the primary DB/authoritative source; avoid reading a lagging replica and jumping to conclusions.
4. **Match semantics:** a receipt with the same key but a different payload is a conflict; do not return "success".
5. **Decide:** `APPLIED` → return prior result; final `REJECTED` → return prior error; `PENDING/UNKNOWN` → continue reconciling; start a new attempt only when proper deduplication is in place.
6. **Bound retries:** overall timeout, max attempts, exponential backoff with jitter, DB health monitoring. If still unclear, keep the request in a pending recovery/reconciliation state and provide a tracking ID rather than reporting "definitely failed".
7. **Structured logging:** `request_id`, attempt number, error phase, SQLState/vendor code (if any), known transaction status, reconciliation outcome. Never log passwords or sensitive payloads.

### Deciding the API Response

For HTTP APIs, example rules:

| Internal state | Possible HTTP response | Meaning returned to client |
| --- | --- | --- |
| `APPLIED` | `200 OK` or `201 Created` per contract | Succeeded; return the same operation ID/result on repeat calls |
| `PENDING/UNKNOWN` | `202 Accepted` with status-check URL or "pending" response per contract | No final outcome yet; client **must not create a new request** |
| `SAME_KEY_DIFFERENT_PAYLOAD` | `409 Conflict` | Request ID is already bound to a different intent |
| Valid `REJECTED` | Appropriate `4xx` per contract | Final business rejection; do not retry identically |
| Infrastructure temporarily unrecovered | `503 Service Unavailable` or timeout per contract | Retry only if endpoint is idempotent, keeping the same key and honoring `Retry-After` if provided |

These HTTP codes are **API design suggestions**, not automatic mappings from `DataAccessException` to HTTP. Most importantly, the contract must let clients know the same ID will be handled/queried safely even when the initial response is lost.

## 7. Why Adding `@Transactional` or `@Retryable` Alone Is Not Enough

`@Transactional` ensures transaction boundaries for operations **that actually participate in the proper transaction**, when the call goes through a Spring proxy (with default proxy-based transaction management). It helps roll back if an exception matches rollback rules. Yet if the commit succeeded and the ACK was lost, a **new** service call with the identical payload starts a new transaction and can debit a second time.

A snippet like this is **insufficient to prevent duplicate writes**:

~~~java
@Service
class WalletService {
    private final JdbcTemplate jdbc;

    WalletService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void debit(long id, int amount) {
        jdbc.update("""
                UPDATE wallet_account
                SET balance = balance - ?
                WHERE id = ?
                """, amount, id);
    }
}
~~~

This example is **placed in a Spring application** with transaction configuration and imports; it illustrates the lack of a request ID/receipt, not a complete program. Calling `debit(1, 30)` twice commits two transactions and deducts twice.

Adding a retry annotation to retry on `TransientDataAccessException` **does not fix this property by itself**. If retry advice wraps outside the transaction boundary, each attempt can create its own transaction; if it sits inside, you can hit a rollback-only transaction or one that is no longer valid. Advice/proxy ordering also affects behavior. Configure where retries execute intentionally, test in reality, and more importantly: **make the endpoint/operation idempotent first**.

Similarly, do not put `@Transactional` over an entire retry loop in the same method expecting rollback to "reset" state after a commit failure. When a transaction ends ambiguously, **recreate a valid transaction scope for the new attempt** and check the receipt; never reuse a completed `TransactionStatus`.

## 8. Multi-Step Work, External Services, and Transactional Outbox

A real request may involve:

~~~text
1. Write order status to DB
2. Deduct inventory in DB
3. Send Kafka event
4. Call payment service
5. Send email
~~~

A local JDBC transaction controls only SQL statements on the DB resource participating in that transaction. It **does not automatically roll back** Kafka events, HTTP requests, emails, or transactions in another DB. Even when the DB part has a deduplicating receipt, retrying the whole workflow can still replay non-DB steps.

### Transactional Outbox for Events

A common option is writing **business state + outbox event** in the **same DB transaction**:

~~~sql
CREATE TABLE outbox_event (
    event_id VARCHAR(80) PRIMARY KEY,
    request_id VARCHAR(80) NOT NULL,
    event_type VARCHAR(80) NOT NULL,
    payload VARCHAR(4000) NOT NULL,
    published BOOLEAN NOT NULL DEFAULT FALSE
);
~~~

Inside the business transaction, insert an outbox record with `request_id`; after commit, a separate publisher reads and sends the event. If the publisher sends successfully yet crashes before marking `published`, it may resend the event. Thus consumers must also be idempotent by `event_id`. The outbox prevents a DB commit succeeding without information to emit the event; **it does not turn the whole workflow into exactly-once**.

When calling a payment gateway, use the **gateway-supported idempotency key**, and query transaction/payment status by transaction ID or provider reconciliation mechanisms. Never issue a new charge with a fresh ID just because the app timed out. Any compensating action (refund, reverse, cancel) is a **new business operation with its own ID and audit trail**; do not treat it as a technical rollback of a committed transaction.

### Do Not Confuse Exactly-Once Effect with Exactly-Once Delivery

A message can be delivered multiple times in an at-least-once system, yet the consumer checks the key and records only one business effect. Use precise phrasing: **at-most-once effect within the scope of the implemented deduplicating resource/contract**, whereas message or request delivery itself does not necessarily happen only once.

## 9. Common Implementation Mistakes

| Mistake | Why it is dangerous | How to fix |
| --- | --- | --- |
| Client generates a new UUID on each HTTP retry | DB treats them as separate requests | Keep the **original intent's** ID across all attempts |
| Only checking `SELECT ... WHERE request_id=?` before INSERT | Two concurrent requests both see "absent" | DB unique constraint + transaction rollback/receipt lookup |
| Receipt commits separately, debit commits separately | App crash between commits creates inconsistent state | Write receipt and debit in the same transaction |
| Receipt exists without storing original payload | Fails to detect same key reused for different intent | Store payload fingerprint/immutable fields and compare |
| Catching `DuplicateKeyException` and immediately returning success | Duplicate may be wrong-intent ID reuse or another unique error | Read the exact receipt and compare requests before returning |
| Catching exception inside `@Transactional` and only logging | Method may return normally and commit unintentionally | Propagate the error or mark rollback-only when needed |
| Reading only a replica right after a timeout | Replica lag causes false "absent" | Read authoritative source; accept `UNKNOWN` without enough proof |
| Retrying every `TransientDataAccessException` | Error type indicates recoverability, not that side effects did not occur | Retry only when the operation is designed to be idempotent |
| Keeping receipts for minutes while clients retry hours/days later | Key purged, causing a second execution | Set retention to match contract, retry deadline, and audit obligations |
| DB idempotency exists, yet emails/charges run outside transaction in same method | Retries still produce external side effects | Use outbox and external-service idempotency/reconciliation |
| Calling `rollback(status)` a second time when commit fails | `TransactionStatus` is already completed/cleaned up; solves no ambiguity | Read business outcome; retry new attempt with stable key |
| Configuring retries simultaneously at HTTP client, service, and DB layers | Amplifies call volume and load during outages | Pick one layer to own the retry budget and backoff |

**Decisive point:** a technically neat catch/retry block has no value unless you clearly define how "the same business operation" is identified and which state confirms the outcome after commit.

## 10. Testing Unknown Commit Outcome Scenarios

Do not test only the happy path. A reasonably thorough test suite should include:

1. **Lost response after commit:** let the DB transaction succeed, then simulate an API timeout/disconnect before returning the response. Retry with the **same ID**; assert only one debit and one receipt.
2. **Pre-commit error:** trigger a constraint violation inside the transaction and let it roll back; confirm no partial debit or receipt remains.
3. **Two callers with the same key:** run concurrently against the target DB/driver. One caller succeeds, the other handles the collision/lock properly; final result is a single effect. Do not rely on sequential tests to reason about concurrency.
4. **Same key, different payload:** rejected; balance and receipt remain unchanged.
5. **Status read while transaction is in-flight:** do not return "FAILED" just because status has not committed; handle `PENDING/UNKNOWN`, bounded timeouts, and later reconciliation.
6. **DB restart/disconnect near COMMIT:** fault injection must observe real database state after recovery; simulating a lost ACK after commit tests only *one* branch.
7. **External side effects:** resend the same event/payment request ID and verify consumer/gateway deduplicates safely.
8. **Retention and late retries:** resend after a long delay, verify the published policy; do not accidentally treat an old key as a new request.
9. **Traffic measurement during widespread failures:** confirm retry counts, exponential backoff, jitter, deadlines, and circuit breakers do not overload the DB.
10. **Multi-table transactions:** verify receipt, primary data rows, and outbox all commit/roll back together in one transaction.

With pure unit tests, you can verify fingerprint comparison logic and state classification. For real commit failures/lost ACKs, you need **integration tests** at the Spring/JDBC layer, a real DB, or a network fault proxy. Tests annotated with `@Transactional` on the test class may auto-rollback and hide the commit boundary you intend to test; structure tests from outside the service's transaction.

## 11. Self-Check Questions

**Question 1.** A `TransactionSystemException` is thrown when `commit()` hits a network error. Is it certain the DB rolled back?

**Answer:** No. The database may have committed while the ACK was lost. Reconcile using a reliable key and state; do not re-run business logic without deduplication.

**Question 2.** Is adding `WHERE balance >= amount` enough to safely retry a debit?

**Answer:** Not yet. That condition only prevents negative balances; if funds cover two debits, the same operation gets deducted twice. You need a stable key and uniqueness/transaction protection.

**Question 3.** Does `@Transactional` guarantee that retrying the same API request will not create two orders?

**Answer:** No. Each call can commit in a new transaction. `@Transactional` protects atomicity *within a single transaction*; it does not recognize two separate calls as one intent.

**Question 4.** Querying the receipt by ID finds no row. Can you conclude the prior attempt never ran?

**Answer:** Not necessarily. The prior attempt might still be uncommitted, the read connection may hit a lagging replica, or the system may not have recovered yet. Keep checking the authoritative source, in-flight status, or use an idempotently designed retry with the same key.

**Question 5.** Does `DuplicateKeyException` when inserting a receipt mean the entire business operation already succeeded?

**Answer:** Insufficient. It indicates a uniqueness conflict; you must read the original record and compare payloads while ensuring the failed transaction rolled back. If the same key has a different payload, return conflict.

**Question 6.** Do DB writes and outbox records in the same transaction guarantee a Kafka consumer processes an event exactly once?

**Answer:** No. The publisher may resend the message, so the consumer still needs deduplication by event ID.

## References

- [Spring Framework — PlatformTransactionManager Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/PlatformTransactionManager.html) — commit/rollback contract and completed transactions.
- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/programmatic.html) — `TransactionTemplate` and transaction boundaries.
- [Spring Framework — JDBC Connections and Transaction Managers](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/connections.html) — `DataSourceTransactionManager`/`JdbcTransactionManager` and exception translation.
- [Spring Framework — JDBC Exception Translation](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/core.html) — `SQLExceptionTranslator`/`DataAccessException`.
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html) — rollback rules.
- [AWS Builders' Library — Making Retries Safe with Idempotent APIs](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/) — client request IDs, equivalent outcomes, late requests, and same key with different payload.
- [PostgreSQL — COMMIT](https://www.postgresql.org/docs/current/sql-commit.html) — transaction commit semantics.
