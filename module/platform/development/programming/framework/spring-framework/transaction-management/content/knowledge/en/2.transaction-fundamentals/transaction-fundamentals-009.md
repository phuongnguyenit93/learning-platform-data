# Commit-Time Failures and Potentially Unknown Outcomes

## 1. Objectives and core problem

A failure while saving data does not always mean "no changes were persisted." In particular, **when a system loses its connection or receives no response during `commit`**, the caller may not know whether the DB committed successfully or not. This is an **unknown commit outcome** (ambiguous/unknown commit outcome, sometimes called an *in-doubt outcome*).

After this lesson, you will be able to:

- Identify when Spring performs commit relative to executing the `@Transactional` method body and sending a response to the client.
- Distinguish a **confirmed rollback**, a **confirmed commit**, and **insufficient evidence to conclude**.
- Understand why an exception at commit time or post-commit does not by itself prove the transaction rolled back.
- Design business operations with an `operationId` / idempotency key, status lookup, and safe retry when responses are lost.
- Write a test demonstrating that a call can report failure **after data has already committed**, while noting the test's limits compared to a physical failure right inside the commit command.

This topic belongs to Spring Framework's *Transaction Fundamentals*. The focus is accurately interpreting **the final outcome of a transaction** and how applications respond to uncertainty, rather than surveying all isolation levels or distributed transaction protocols.

## 2. Timeline: finishing the method does not mean the transaction committed

In Spring using **declarative transactions and imperative APIs** with `@Transactional` and proxies, an actual call looks like:

```text
Caller / Controller                Spring transaction interceptor                   Database
      |                                       |                                         |
      |------ call service via proxy -------->|                                         |
      |                                       |-- BEGIN / join transaction ------------>|
      |                                       |-- execute method body ----------------->|
      |                                       |     INSERT/UPDATE/DELETE statements     |
      |                                       |<-- method returns value ----------------|
      |                                       |-- flush/beforeCommit (if any) --------->|
      |                                       |-- COMMIT ------------------------------>|
      |                                       |<-- COMMIT result (if received) ---------|
      |                                       |-- afterCommit/afterCompletion ----------|
      |<---- return or exception -------------|                                         |
      |-- build HTTP response for client      |                                         |
```

**Common pitfall:** the `return` statement inside `@Transactional` only ends the Java method body; it does not necessarily deliver the result to the caller yet. Spring still must complete the transaction before the proxy returns. With `@Transactional(propagation = REQUIRED)` joining an existing transaction, an inner method can also finish before the **outer scope's physical transaction** commits.

Depending on the transaction manager (JDBC, JPA, JTA...), some SQL statements may be sent early; JPA changes are deferred until `flush` or commit; constraints or deadlocks may only surface late. Thus, "no error inside the business method" does not guarantee a successful commit.

### 2.1. Three distinct milestones

1. **Business body finishes:** the method may return a result, while the transaction interceptor has not completed yet.
2. **DB decides commit/rollback:** durable persistence state is decided according to the DB's mechanism.
3. **Caller receives confirmation:** the outcome seen by the transaction manager, HTTP server, or client. A response can fail or be lost after the data has already committed.

No simple `catch(Exception)` block turns these three milestones into a single atomic event. Losing a response is not the same as rolling back.

### 2.2. Example of a payment or credit

A client sends `credit(account=1, amount=100, operationId="op-001")`. The server increments the balance and saves an operation record, then the database commits. Right as the DB replies to `COMMIT`, the network drops:

- If the commit had not yet been accepted by the DB, the transaction may be rolled back when the connection aborts.
- If the DB already accepted the commit yet **the ACK was lost**, the data already exists even though the server sees an error.
- If the server received the ACK yet **the HTTP response was lost**, the client also does not know its request succeeded.

From a timeout or connection error on the caller side alone, **you cannot deduce** which branch occurred. Immediately resending an unidentified request can duplicate the operation.

## 3. Classifying outcomes by evidence, not intuition

| Situation | What can be concluded? | Appropriate action |
| --- | --- | --- |
| Input validation fails before starting the transaction and definitely before any write | No changes were made in this transaction | Report input error; do not retry blindly |
| Spring knows the transaction was marked rollback-only and rolled back | Rollback occurred within that transaction scope | Fix root cause; controlled retry if appropriate |
| DB confirms commit succeeded, application receives confirmation | Commit succeeded under resource guarantees | Return success or proceed with post-commit workflow |
| Driver throws error during `Connection.commit()` / coordinator loses contact | **May be unknown** without definitive DB evidence | Assign temporary "unknown" status; verify via operation ID |
| `afterCommit()` throws, or sending HTTP response fails after transaction finished | Main transaction **may have committed**; entering `afterCommit()` means commit succeeded | Do not treat exception as proof of rollback; query status |
| Client times out after sending request | Client does not know how far the server processed | Query status and retry with the **same idempotency key** |

You must evaluate **the specific error and transaction manager**. Never claim that **every** exception at `commit` produces an UNKNOWN outcome. For example, Spring may throw `UnexpectedRollbackException` when a transaction was marked rollback-only and rolled back instead of committing. Meanwhile, `TransactionSystemException` can wrap resource/commit errors; inspect the root cause, DB signals, and logs. Constraint errors raised during flush can lead to a clear rollback; a connection drop right at commit time may lack sufficient evidence.

Especially with resources involving multiple participants or a coordinator, heuristic/mixed states can exist; do not apply local JDBC transaction reasoning to every system. Within a single DB transaction, DB-side atomicity **does not solve** client-side uncertainty over lost ACKs.

### 3.1. Distinguishing "transaction succeeded" from "request succeeded"

A DB transaction can commit, yet the HTTP request returns 500 because a **post-commit** step such as updating a cache, calling an external system, or writing the response failed. Conversely, a server might return success too early while actual work still sits in a queue. The API contract must specify which outcomes are guaranteed and how to query status.

### 3.2. "Record not found" does not always mean failure

Right after a timeout, a status query might read a lagging replica or the original operation may still be executing on another server. Not seeing `operationId` on one read is insufficient to declare rollback. Read from a source with appropriate consistency guarantees, inspect processing state, apply bounded waits/retries, and route unresolved cases to reconciliation or operations support.

## 4. Where do Spring exceptions sit in the commit process?

In Spring Framework, `PlatformTransactionManager` manages `getTransaction`, `commit`, and `rollback`. With Spring Boot + JDBC, the manager typically manages transactions on a JDBC connection from `DataSource`. With JPA, flushing can occur at commit time. The transaction manager finishes/cleans up the scope even when `commit` throws an error; **never call rollback on the same TransactionStatus after a failed commit** expecting to undo an already-completed commit.

Common symptom groups:

- **`UnexpectedRollbackException`:** an inner `REQUIRED` scope marked rollback-only, the outer scope expected to commit, and the manager rolled back. Spring intentionally raises this so the caller does not mistake it for a commit.
- **`TransactionSystemException`:** a system/transaction-manager-level error; inspect `cause`, actual commit state, and DB information.
- **`DataAccessException` / constraint error during flush/commit:** may come from SQL or delayed ORM synchronization; the exception type alone does not prove UNKNOWN—inspect how the DB concluded.
- **`HeuristicCompletionException`:** signals that a coordinator made a heuristic decision in environments supporting that transaction model; may require investigating participant states.
- **Exception from `TransactionSynchronization.afterCommit()`:** the callback runs after the main transaction has committed. A runtime exception from `afterCommit` can propagate to the caller, even though that callback cannot automatically roll back the already-committed data.

Hypothetical example:

```java
@Transactional
public Receipt pay(Command command) {
    savePayment(command);
    return new Receipt("ACCEPTED");
}
```

The snippet above is illustrative only, omitting `Receipt`, `Command`, and `savePayment`. `return` does not guarantee the caller received `Receipt`: the interceptor still runs commit/after-commit phases. Do not wrap `@Transactional` narrowly or send "success" from a controller before the transaction actually completes.

**Important proxy exception:** if a `@Transactional` method is called internally via `this.method()` in the same bean, advice may not run under default proxy mode. If a service joins an outer transaction, commit occurs in the outer scope. When analyzing failures, identify **which transaction** and **who** actually owns the commit step.

## 5. Why direct retries can corrupt data

Consider an "add 100" API:

```sql
UPDATE wallet SET balance = balance + 100 WHERE id = 1;
```

This command is **not idempotent**: running it twice adds 200. If the first attempt committed yet the response was lost, a blind retry corrupts the balance.

By contrast, an operation with a durable `operationId` can enforce: **one identified business intent is recorded at most once**, even if the client sends multiple requests:

```text
Client keeps the same operationId = op-001
      |
      v
Server starts transaction
      |
      +--> Check if operationId already has a result?
      |       +-- Yes, same parameters: return prior result (do not credit again)
      |       +-- Yes, different parameters: reject key reuse conflict
      |
      +--> Not found: update balance + insert operationId with result
                  (within the SAME DB transaction)
      |
      v
Commit: succeeded or uncertain response
      |
      +--> If response lost: client queries / retries with the SAME operationId
```

An **idempotency key** is not an in-memory flag. It must stay stable per business intent and be protected by a DB unique constraint or equivalent synchronization. Store the identifier, core parameters (or normalized hash), status, and returnable result. Requests with the same key and a different payload must be rejected to prevent reusing keys across intents.

### 5.1. Invariant when writing to a single DB

Within **one local DB transaction**, the financial mutation and the operation-tracking record commit together:

```text
BEGIN
    UPDATE wallet SET balance = balance + amount WHERE id = accountId;
    INSERT INTO credit_operation(operation_id, amount, state) VALUES (...);
COMMIT
```

If it rolls back, both the balance update and operation record disappear. If it commits, both exist. Querying the committed operation distinguishes "already applied" when the initial ACK is lost. Under concurrent contention, `UNIQUE(operation_id)`/primary key is the final barrier: a "SELECT sees none, then INSERT" pattern alone **is not enough to prevent races**.

Note that this guarantee applies only to changes **participating in that DB transaction**. Calling a payment gateway, sending an email, or publishing directly to another broker is not automatically part of the DB commit.

### 5.2. Do not treat "retry with a key" as an unbounded promise

Clients need deadlines, timeouts, exponential backoff + jitter, a maximum retry count, and a reconciliation path when uncertainty persists. Keys need sufficient format/uniqueness, retention periods suited to the domain, and protection against guessing/hijacking. Purging the key table too early allows duplicate effects if a client retries afterward. For payments, durable business IDs/ledgers may need to outlive short-lived idempotency caches.

## 6. Runnable example: post-commit exception yet data persists

**Purpose of this run:** reproduce an easily misunderstood state: the caller receives `IllegalStateException`, yet the DB **already committed successfully**; retrying with the same `operationId` does not credit money a second time.

The program uses Java 17+, Spring Boot 3.5.16, Spring JDBC, and in-memory H2. There is **one DB**, one Spring-managed service bean, and one `CommandLineRunner` invoking the service through its proxy. The example intentionally throws an exception inside `TransactionSynchronization.afterCommit()`. This is a **deterministic simulation of a post-commit failure**, **not** a reproduction of a lost ACK during `Connection.commit()`; handling physical UNKNOWN failures is covered afterward.

### 6.1. Project files

```text
commit-outcome-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/commit/
    │   ├── CommitOutcomeApplication.java
    │   └── CreditService.java
    └── resources/
        ├── schema.sql
        └── data.sql
```

**`settings.gradle`**

```groovy
rootProject.name = 'commit-outcome-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example.commit'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
```

Requires JDK 17+ and Gradle 8.x compatible with Spring Boot 3.5; the example requires no web server. Versions are pinned for reproducibility; real projects should track supported Spring Boot branches.

**`src/main/resources/schema.sql`**

```sql
CREATE TABLE wallet (
    id BIGINT PRIMARY KEY,
    balance BIGINT NOT NULL CHECK (balance >= 0)
);

CREATE TABLE credit_operation (
    operation_id VARCHAR(64) PRIMARY KEY,
    account_id BIGINT NOT NULL REFERENCES wallet(id),
    amount BIGINT NOT NULL CHECK (amount > 0),
    state VARCHAR(16) NOT NULL CHECK (state = 'SUCCEEDED')
);
```

**`src/main/resources/data.sql`**

```sql
INSERT INTO wallet (id, balance) VALUES (1, 1000);
```

Each `operation_id` can exist at most once thanks to the PRIMARY KEY. Incrementing the balance and inserting into `credit_operation` must share the same transaction; if insertion fails (including concurrent key collisions), the balance update of the **failing call** must roll back.

### 6.2. Service executing and recording an operation

**`src/main/java/example/commit/CreditService.java`**

```java
package example.commit;

import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class CreditService {
    private final JdbcTemplate jdbc;

    public CreditService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public String credit(
            String operationId,
            long accountId,
            long amount,
            boolean failAfterCommitForDemo) {

        if (operationId == null || operationId.isBlank()
                || operationId.length() > 64 || amount <= 0) {
            throw new IllegalArgumentException("Invalid parameters");
        }

        List<RecordedCredit> previous = jdbc.query(
            "SELECT account_id, amount FROM credit_operation WHERE operation_id = ?",
            (rs, row) -> new RecordedCredit(
                rs.getLong("account_id"), rs.getLong("amount")),
            operationId
        );

        if (!previous.isEmpty()) {
            RecordedCredit old = previous.get(0);
            if (old.accountId() != accountId || old.amount() != amount) {
                throw new IllegalArgumentException(
                    "operationId already used for different parameters");
            }
            return "ALREADY_SUCCEEDED";
        }

        int rows = jdbc.update(
            "UPDATE wallet SET balance = balance + ? WHERE id = ?",
            amount, accountId
        );
        if (rows != 1) {
            throw new IllegalArgumentException("Account does not exist");
        }

        jdbc.update(
            "INSERT INTO credit_operation " +
            "(operation_id, account_id, amount, state) " +
            "VALUES (?, ?, ?, 'SUCCEEDED')",
            operationId, accountId, amount
        );

        if (failAfterCommitForDemo) {
            TransactionSynchronizationManager.registerSynchronization(
                new TransactionSynchronization() {
                    @Override
                    public void afterCommit() {
                        throw new IllegalStateException(
                            "Lost response after commit (simulated)");
                    }
                }
            );
        }

        return "SUCCEEDED";
    }

    private record RecordedCredit(long accountId, long amount) {}
}
```

Sequence explanation:

1. `@Transactional` opens or joins a transaction when invoked through the Spring proxy.
2. If `operationId` already exists with matching parameters, returns `ALREADY_SUCCEEDED` without modifying the balance.
3. If not found, updates the balance and inserts the result record in **the same transaction**.
4. In demo mode, registers an `afterCommit` callback that throws `IllegalStateException`. After `credit` returns from its method body, Spring commits the DB first, and then the callback throws to the caller.
5. Consequently, even though the caller catches an exception, both SQL changes have committed. Resending with the same key reads `credit_operation` and avoids crediting twice.

**Concurrency limitation:** two calls with the same `operationId` can both observe none at the SELECT step. The primary key prevents **both** from inserting successfully; the colliding call must roll back its entire transaction. In production, map unique/transient conflict errors to a policy of "finish the failed transaction → look up status in a new transaction → optionally return prior result"; never swallow an insert exception and continue using the failed connection/transaction. This example illustrates **sequential** retries and does not by itself resolve all concurrent contention.

### 6.3. Caller receives an error yet reads committed data

**`src/main/java/example/commit/CommitOutcomeApplication.java`**

```java
package example.commit;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class CommitOutcomeApplication {
    public static void main(String[] args) {
        SpringApplication.run(CommitOutcomeApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(CreditService service, JdbcTemplate jdbc) {
        return args -> {
            try {
                service.credit("op-001", 1L, 100L, true);
                System.out.println("First attempt: succeeded");
            } catch (IllegalStateException ex) {
                System.out.println("First attempt: " + ex.getMessage());
            }

            System.out.println("Balance after error: " + balance(jdbc));
            System.out.println("Operation status: " +
                jdbc.queryForObject(
                    "SELECT state FROM credit_operation " +
                    "WHERE operation_id = ?",
                    String.class, "op-001"));

            System.out.println("Retry: " +
                service.credit("op-001", 1L, 100L, false));
            System.out.println("Final balance: " + balance(jdbc));
        };
    }

    private static Long balance(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
            "SELECT balance FROM wallet WHERE id = 1", Long.class);
    }
}
```

Spring Boot automatically runs `schema.sql` and `data.sql` against embedded H2 at startup. From the `commit-outcome-demo` directory, run Gradle 8.x:

```bash
gradle bootRun
```

If an appropriate Gradle Wrapper was generated, use `./gradlew bootRun` (Linux/macOS) or `gradlew.bat bootRun` (Windows). Omitting framework logs, the **five lines from the program** read:

```text
First attempt: Lost response after commit (simulated)
Balance after error: 1100
Operation status: SUCCEEDED
Retry: ALREADY_SUCCEEDED
Final balance: 1100
```

**Why is this output notable?**

- The caller caught `IllegalStateException`, yet the balance rose from 1000 to 1100; `credit_operation` contains `op-001`. The exception occurred **post-commit**.
- Retrying with the same `op-001` and same payload only returns the prior outcome; the balance does **not** become 1200.
- If the client generated `op-002` for the same intent on retry, the DB would treat it as a **new operation** and could credit another 100.
- `failAfterCommitForDemo` is an experimental toggle; never put such a flag in production business logic.

The test reproduces **the caller seeing an error despite a successful DB result**; it **does not prove** that every exception from JDBC `commit` represents a successful commit. Testing a genuine "lost commit ACK" requires network/DB/proxy fault injection at the exact moment, gathering evidence, and handling both outcomes.

## 7. Designing responses and state machines for unknown outcomes

A system should separate **internal processing state** from **client-observable state**. You can define:

- `SUCCEEDED`: evidence exists that the business transaction committed according to an authoritative source.
- `FAILED`: evidence exists that the operation was rejected or rolled back before any effect, with no remaining concurrent execution that could commit.
- `PENDING`: request was received or is in progress; no final outcome yet.
- `UNKNOWN`: observer lost confirmation signals, lacking sufficient basis to assign `SUCCEEDED` or `FAILED`.

This is a suggested **processing model**, not a built-in enum automatically persisted by Spring. A "PENDING" record written in another transaction can exist even if the business operation never commits; you must clearly define the source of truth. Typically you can use a DB operation record as in the example, or a ledger/workflow state table updated transactionally.

### 7.1. Suggested API

```http
POST /credits
Idempotency-Key: op-001
Content-Type: application/json

{"accountId": 1, "amount": 100}
```

If the transaction confirmed commit, the server can return `200 OK` or `201 Created` with `operationId` and status. If processing is still ongoing, `202 Accepted` with a status-lookup location is appropriate. If the server does not know the outcome due to an internal timeout, it should reflect **uncertainty** per the API contract rather than asserting rollback; if the client connection is still open, it can return details enabling status polling. If the connection dropped completely, the client must retain `operationId` itself.

```http
GET /operations/op-001
```

Return state read from an authoritative source and enforce suitable access controls. Upon seeing `SUCCEEDED` with a matching payload, the client stops retrying the business effect. When inconclusive, keep the same key to retry **the same intent**, or hand off to a reconciliation process. Never treat a single HTTP status code as proof about DB commit when errors occur after DB processing.

### 7.2. Retry handling pseudocode (conceptual design)

```text
operationId = stable ID generated by client for ONE intent
payload     = immutable data for that intent

send POST with operationId and payload
  if confirmed SUCCEEDED:
      done
  if confirmed permanent failure:
      report failure with evidence
  if timeout / lost response / server reports unknown:
      query GET status by operationId on an appropriate read source
      if SUCCEEDED:
          done, DO NOT perform a new operation
      if PENDING/UNKNOWN or temporarily unreadable:
          backoff + jitter, continue polling or resend
          THAT SAME operationId + payload
      if threshold exceeded:
          escalate to reconciliation/alerting, DO NOT generate a new operationId
```

Do not automatically use `REQUIRES_NEW` to "confirm" a just-failed transaction: an independent transaction can create misleading records or write "FAILED" even though the original transaction committed. Reconciliation state must be designed around **the reliability of the data source**.

## 8. When is rollback certain, and when must you reconcile?

### 8.1. Confirmed rollback cases

With a normal `UnexpectedRollbackException` caused by rollback-only in a manager-controlled transaction, Spring indicates commit did not happen and the transaction rolled back. A business error thrown before commit and successfully rolled back by the manager also has a known outcome. Still, ensure evidence that rollback completed, not merely "rollback() was called."

**Do not lump every exception into UNKNOWN**: doing so forces unnecessary waiting and reconciliation.

### 8.2. Cases of failure right at COMMIT

Suppose the JDBC driver sends `COMMIT`, the DB writes the commit record, yet the connection drops before the driver reads the ACK. Spring may see an exception, yet cannot reverse already-committed data with a new `rollback` call. You must query durable effects once connectivity recovers, using the business operation ID, transaction ledger, or an appropriate reconciliation source.

Conversely, if the DB definitively returns a constraint error during pre-commit flush and the transaction rolls back cleanly, the outcome differs from the lost-ACK scenario. Analysis requires **timestamps, transaction IDs if available, root stack traces, driver details, DB logs, and data state**. A generic message string like "commit failed" alone is insufficient.

### 8.3. Transactions with multiple resources

Local `@Transactional` with a `DataSourceTransactionManager`/JPA transaction manager does not mean "update DB + publish Kafka + send email" commit together. If an external step succeeds while the DB fails, or vice versa, partial state can occur. For business events, a common pattern is **transactional outbox**: save business state and an outbox event in the same DB transaction; a worker publishes messages afterward, and consumers deduplicate via event ID. Outbox typically provides at-least-once delivery, so listeners still need idempotency.

If using multi-resource JTA/XA, heuristic failures or lost coordinator contact require dedicated recovery and reconciliation procedures. Never infer all participants' statuses solely from one service's exception.

## 9. Common operational mistakes

**Mistake 1 — Automatically retrying every exception.** When the outcome may have committed, re-running `UPDATE balance = balance + amount` applies the effect twice. Fix: stable operationId, persist outcome in the same transaction, query status, and retry safely.

**Mistake 2 — Generating a new idempotency key per attempt.** The server sees distinct requests and cannot recognize the same business intent. Fix: the client/producer generates the ID once and preserves it across timeouts/restarts, bound to an immutable payload.

**Mistake 3 — Assuming `SELECT` before `INSERT` prevents duplicates.** Two threads can both observe non-existence. Fix: DB unique constraints plus conflict/rollback/re-query handling; never continue a transaction after SQL errors.

**Mistake 4 — Catching exceptions in the controller and recording "FAILED".** If the exception came from `afterCommit`, the effect already succeeded. Fix: classify based on evidence and use UNKNOWN when unclear.

**Mistake 5 — Recording success in a separate transaction.** The status record can diverge from the business update if the two transactions have different outcomes. Fix: update business effect and operation record atomically on the same DB; handle non-DB steps separately.

**Mistake 6 — Sending external notifications right before commit.** Emails/webhooks may arrive while the DB rolls back. Fix: after-commit callbacks when message loss is acceptable under defined conditions; if high reliability is required, prefer outbox with idempotent consumers. `afterCommit` is not a durable queue; callback errors do not roll back the main transaction.

**Mistake 7 — Reading only from a replica right after timeout.** The replica may lag behind the commit. Fix: status endpoints should read from a source with sufficient consistency guarantees, or report inconclusive rather than "does not exist."

**Mistake 8 — Auto-compensating immediately upon timeout.** Debiting back funds that were credited while another retry is in flight makes business state harder to control. Fix: reconcile first; compensation must be a distinct operation with its own ID, audit log, and rules.

**Mistake 9 — Logging without correlation keys.** Impossible to link the initial request, retries, transaction exception, and committed record. Fix: log `operationId`, correlation ID, failure timestamp, query outcome, and transaction manager, while avoiding logging sensitive data.

## 10. Testing and observability to prove the design

Tests should distinguish four categories:

1. **Known rollback:** inject a runtime error before commit and verify both business and operation tables remain unchanged after the scope ends.
2. **Successful commit:** same `operationId` and payload must record exactly one effect, repeated calls return the prior result; different payloads must be rejected.
3. **Post-commit error:** like `afterCommit` in the demo; verify the caller observes an exception yet the DB holds both the effect and receipt. Retrying the same key does not repeat the effect.
4. **Commit-time error / real lost ACK:** in an integration environment with a real DB and appropriate fault-injection/network proxy; test both commit and rollback possibilities and reconcile. You cannot faithfully simulate this merely with `throw new RuntimeException()` at the end of a business method.

Test **concurrency** with multiple requests sharing the same key and amount to confirm a single effect; test same key with different amounts; test restarts, multiple retries, timeouts, and lock expirations. When reconciling after disconnects, verify the status endpoint does not return "FAILED" prematurely while an invocation could still finish. For non-DB resources, test duplicate events and outbox replay.

In Spring Test, a test marked `@Transactional` typically rolls back at completion. When testing that "commit occurred," do not wrap the entire call in a test transaction and draw conclusions from temporary state; use non-transactional tests or `TestTransaction` to control transaction completion, then read fresh DB state.

Operational metrics should drive action: counts of commit/after-commit failures, operations stuck in UNKNOWN past SLA, idempotency conflicts (same key, different payload), reconciliation latency, retried events, and reconciled outcomes. Without a process to resolve UNKNOWN, merely catching exceptions and logging "failed" is insufficient.

## 11. Checklist for handling commit-time failures

When encountering an error near commit time:

- **Identify scope:** which method owns the transaction, what propagation, which transaction manager, and which resources participate?
- **Identify failure point:** SQL/flush/beforeCommit, the commit command itself, afterCommit, or HTTP response after commit?
- **Gather evidence:** DB commit/rollback confirmation, Spring rollback-only, driver error code/`cause`, operation record, database logs?
- **If evidence is insufficient:** mark outcome UNKNOWN from the caller's perspective; **do not assume rollback**.
- **Prevent duplication:** preserve operationId and payload, use unique constraints, and enclose both effect and receipt in one transaction.
- **Reconcile:** read from a sufficiently consistent source, handle in-flight work, set wait bounds and escalation.
- **Extend beyond DB:** outbox, duplicate delivery, idempotent consumers, or multi-step state workflows.
- **Verify:** run commit success, known rollback, after-commit failure, lost response, and concurrent duplicate cases.

## 12. Self-check questions

**Question 1.** A `@Transactional` method finishes and returns `"OK"`, yet the caller receives `TransactionSystemException`. Is it definitely rolled back?  
**Answer:** No. The method body can finish before commit. You must identify which phase failed and whether there is DB commit/rollback evidence; otherwise treat the outcome as unknown.

**Question 2.** When is `UnexpectedRollbackException` typically more specific than a connection drop during `COMMIT`?  
**Answer:** In Spring's standard rollback-only case, the manager deliberately rolls back and throws so the caller does not mistakenly assume commit. In a lost-ACK failure at COMMIT, the caller may not know whether the DB accepted the commit or not.

**Question 3.** If the server returns HTTP 500 after `afterCommit` throws an exception, should the client resend the credit request with a new operation ID?  
**Answer:** No. Committed data may already exist; query status and keep the **same operationId** for the same intent.

**Question 4.** Why is `PRIMARY KEY(operation_id)` still required if code runs a `SELECT` check first?  
**Answer:** Two concurrent requests can both read "not found"; a DB-enforced unique constraint ensures they cannot both insert receipts with the same ID. Roll back and re-query after a conflict.

**Question 5.** What does the `afterCommit` example prove and what does it not prove?  
**Answer:** It proves an exception can reach the caller **after the main transaction has committed**. It does not simulate a connection failure inside `Connection.commit()`, so do not conclude that every commit exception represents a successful outcome.

## References

- Spring Framework — Declarative transaction management: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html
- Spring Framework — Transaction propagation and `UnexpectedRollbackException`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework 6.1 Javadoc — `PlatformTransactionManager.commit`: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/transaction/PlatformTransactionManager.html
- Spring Framework 6.1 Javadoc — `TransactionSynchronization.afterCommit`: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html
- Spring Boot — Database initialization: https://docs.spring.io/spring-boot/how-to/data-initialization.html

**Point to remember:** An exception is not a receipt for rollback. A transaction may have committed even when the caller receives an error; when the outcome is unknown, the solution is to **preserve business identity, query authoritative status, design for idempotency, and reconcile**, rather than repeating side effects by guesswork.