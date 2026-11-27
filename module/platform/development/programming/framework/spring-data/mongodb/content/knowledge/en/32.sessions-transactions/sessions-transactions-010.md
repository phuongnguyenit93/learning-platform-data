# Distinguishing Whole-Transaction Retries from Commit Retries on Unknown Outcomes

> **Chapter:** Sessions and Transactions  
> **Module:** `SPRING_DATA_MONGODB`

In order-processing, money-transfer, reservation, or inventory systems, a MongoDB transaction can fail while executing write commands, or fail **at the exact moment `commitTransaction` is sent**. On the surface both look like "the command failed," yet their recovery mechanisms **are completely different**:

- When a transaction **aborted due to a transient error**, you must **open a new transaction and re-run the entire transactional body** per your retry policy.
- When **it is unknown whether commit succeeded**, you must prioritize **retrying only the commit command of that same transaction on the same session/transaction identity**, rather than re-executing business logic as a new transaction.

Confusing the two can cause **duplicate payment entries, double-credited points, duplicate shipments**, or reporting failure even though the database committed. Conversely, failing to retry when a transaction genuinely aborted lets temporary contention fail requests that would succeed on the next attempt.

In the `SPRING_DATA_MONGODB` module, we connect, map documents, and operate on data via `MongoTemplate` or repositories, practicing queries, aggregations, indexes, transactions, reactive access, testing, and performance diagnostics. This lesson focuses on **sessions, transaction state, error labels, and accurate retry algorithms** in the MongoDB Java Driver and Spring Data MongoDB.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish errors occurring **inside the transactional body** from errors occurring during **commit**.
2. Explain the error labels `TransientTransactionError` and `UnknownTransactionCommitResult`; never guess transaction outcomes solely because the client threw an exception.
3. Describe **whole-transaction retry**: discard the failed transaction attempt, start a new attempt, and re-run operations inside the transaction.
4. Describe **commit retry**: keep the same logical session and transaction identity, and **never re-run the transactional body** when the commit outcome is unknown.
5. Use the Java Driver's `ClientSession.withTransaction(...)`, build bounded manual retries when genuinely needed, and understand where Spring Data `MongoTransactionManager`/`@Transactional` differs from driver callbacks.
6. Distinguish internal transaction retries from **HTTP request retries**, idempotency keys, unique indexes, and outboxes.
7. Write tests for contention, network failures at commit, and failover, asserting invariants rather than callback execution counts.
8. Select timeouts, retry budgets, observability, reconciliation, and `COMMIT_UNKNOWN` states in real systems.

## 2. Which Phases Does a Transaction Go Through?

Standard path:

```text
Client / Application
      |
      v
Start ClientSession
      |
      v
Start Transaction
      |
      v
Transactional Body
  - insert payment record
  - debit account
  - credit account
      |
      +---- body error / aborted? ----> Abort / start NEW transaction
      |                                 and RETRY WHOLE BODY if transient
      v
commitTransaction()
      |
      +---- ACK success ----------> CONFIRMED COMMITTED
      |
      +---- outcome unknown ------> RETRY COMMIT on SAME transaction
      |
      +---- definite failure -----> Handle failure; do not guess
```

A **MongoDB session** carries context for related operations. A transaction is bound to a session and an internal identifier/`txnNumber` managed by the driver. When retrying **commit**, the driver must continue acting on **the exact transaction that executed the body**. When retrying the **whole transaction**, the driver starts a fresh transaction attempt and re-executes the logic.

Never treat every line after `startTransaction()` as a single atomic network call: network requests, retries, topology discovery, and acknowledgments can fail independently. What the client **knows for sure** differs from what the server **actually did**.

### 2.1. Error Timing Determines Recovery

| Timing | Knowable State | Primary Handling |
| --- | --- | --- |
| Before `startTransaction` | No transactional body ran yet | Handle connection/init failure; no business writes inside tx |
| While executing commands in body, labeled `TransientTransactionError` | Current attempt cannot complete normally | Abort/clean up attempt, **start a new transaction**, re-run body if safe |
| Inside body, non-transient validation/duplicate-key error | Business rule or schema precondition failed | Stop and return error; do not retry indefinitely |
| `commitTransaction` returns success | Commit acknowledged per chosen write concern | Return success; do not retry business logic |
| `commitTransaction` fails with `UnknownTransactionCommitResult` | **Cannot confirm whether commit succeeded or failed** | **Retry commit on the old transaction**, keep session, never re-run body |
| Cannot confirm commit after exhausting retry budget | Outcome at client **remains unknown** | Return/track unknown status, **reconcile** via operation ID |
| Commit returns another error | Classify accurately; never assume replay is safe | Follow driver spec and actual error; do not restart business flow blindly |

These are the **core handling rules**, not an exhaustive list of every branch across MongoDB versions. Always rely on error labels and actual driver/server APIs rather than exception message strings.

## 3. Error Labels: Classifying Instead of Guessing from Messages

The MongoDB Java Driver exposes error labels via `MongoException.hasErrorLabel(...)`. Two core labels:

```java
import com.mongodb.MongoException;

boolean transientTxn =
    mongoException.hasErrorLabel("TransientTransactionError");

boolean commitUnknown =
    mongoException.hasErrorLabel("UnknownTransactionCommitResult");
```

Here `mongoException` is a driver-thrown exception; this snippet illustrates a Java error-handling block, not a standalone Java program.

### 3.1. TransientTransactionError (TTE)

The `TransientTransactionError` label indicates a transient transaction-related failure where **retrying the entire transaction may be appropriate**. Common triggers:

- Write conflict between two concurrent transactions.
- Primary stepdown/election while the transaction is executing.
- Certain topology/network/transient errors when a command inside the transaction cannot finish.

**Strategy:** discard the failed transaction attempt; start a new transaction; re-run the **entire transactional body** after ensuring the code is safe to re-execute.

Never retry **only the final write** inside the transaction after a write conflict hoping the rest still commits. Once a transaction aborts, the entire attempt is invalid.

### 3.2. UnknownTransactionCommitResult (UTCR)

`UnknownTransactionCommitResult` means something different: the client **does not know the final outcome of `commitTransaction`**. A typical cause is a network drop after commit was sent — the server may have committed, while the acknowledgment never reached the client.

**Strategy:** re-invoke **`commitTransaction` for the exact same session/transaction**, without repeating insert/debit/credit as a new business attempt.

Because commit might already have succeeded, starting a new transaction and immediately re-running the body risks duplicate side effects. If retrying commit fails within the retry budget, **preserve the unknown outcome**, never treating it as guaranteed rollback.

### 3.3. The Two Labels Are Not a Binary "True/False" Model

Labels are only part of the error metadata. An exception lacking both labels **does not automatically mean** the transaction committed or aborted as business logic prefers. Validation errors, duplicate keys, expired sessions, or other failures require specific handling.

When drivers or frameworks wrap exceptions, inspect the **cause chain**; never parse log phrases like `"connection reset"` to guess transaction retry behavior.

## 4. Two Distinct Retry Algorithms

### 4.1. Retrying the *Whole Transaction*

```text
Attempt 1
  session.startTransaction()
  insert ledger(op-123)
  debit wallet A
  credit wallet B
      |
      +-- TransientTransactionError -> attempt aborted

Attempt 2 (NEW transaction)
  session.startTransaction()
  insert ledger(op-123)
  debit wallet A
  credit wallet B
  commitTransaction() -> SUCCESS
```

Because Attempt 1's writes were rolled back/aborted, Attempt 2 must re-execute **all steps inside the transaction**. If the logic reads balances, the new attempt must **re-read** to compute from fresh state rather than reusing cached values from the old attempt.

### 4.2. Retrying *Commit Only*

```text
Attempt 1
  session.startTransaction()
  insert ledger(op-123)       [ONLY ONCE in this attempt]
  debit wallet A             [ONLY ONCE in this attempt]
  credit wallet B            [ONLY ONCE in this attempt]
  commitTransaction()
      |
      +-- NETWORK ERROR; UNKNOWN commit result
      |
      +-- commitTransaction() AGAIN on SAME session + transaction
              |
              +-- SUCCESS / confirmed outcome
```

**Never** re-run the three business operations between two commit attempts. The driver uses the same session/transaction identity so the server handles repeated commit calls per protocol. If the callback runs a second time in a **new** transaction before commit outcome is known, that is no longer a commit retry.

### 4.3. Decision Table to Memorize

| Aspect | Retry Whole Transaction | Retry Commit |
| --- | --- | --- |
| Primary signal | `TransientTransactionError` on a tx operation requiring restart | `UnknownTransactionCommitResult` at commit |
| Transaction identity | **New** | **Preserved** |
| Re-run body? | **Yes**, from the start | **No** |
| Re-read data and re-check rules? | **Yes**, in the fresh attempt | **No** (only confirming prior commit) |
| External side effects inside callback | Risk duplicating; must remove or defer via outbox | Callback does not re-run, yet unknown outcome still needs handling |
| When budget is exhausted | Report transient/incomplete error per policy | Preserve `COMMIT_UNKNOWN`, reconcile via operation ID |
| Applies to deterministic schema errors | No | No |
| Purpose | Recover an attempt that definitely cannot proceed | Resolve **ambiguity of commit acknowledgment** |

## 5. Concrete Scenario: Transferring Funds Between Two Wallets

Suppose tenant A owns two wallets:

```javascript
db.wallets.insertMany([
  {
    _id: "WALLET-A",
    tenantId: "TENANT-A",
    balanceMinor: NumberLong(100000),
    version: NumberLong(1)
  },
  {
    _id: "WALLET-B",
    tenantId: "TENANT-A",
    balanceMinor: NumberLong(20000),
    version: NumberLong(1)
  }
])
```

Request to transfer `30000` from A to B with `operationId = "TRANSFER-123"`. On success, we expect:

```text
WALLET-A: 100000 -> 70000
WALLET-B:  20000 -> 50000

Total before = 120000
Total after  = 120000

transfers: exactly one record with _id = "TRANSFER-123"
```

The application must perform inside **one MongoDB transaction**:

1. Insert a transfer record with `_id` set to the stable operation ID.
2. Deduct wallet A's balance **when balance is sufficient**.
3. Credit wallet B within the same tenant.
4. Commit all changes atomically.

### 5.1. Why Do We Need operationId?

Beyond driver retries, users or API gateways can **resend the entire HTTP request** after a timeout. That is **not** a commit retry on the same session; the server receives a brand-new HTTP request/business invocation.

`operationId` enables **idempotency** through existing-record lookups, unique indexes, and transaction states. MongoDB's `_id` already carries a unique index; you can use `_id` as a **system-wide unique** operation ID. If IDs are unique only per tenant, use a composite `tenantId + operationId` key with a unique compound index.

Operation IDs **do not replace** commit retries when outcomes are unknown, yet they form a vital line of defense when sessions are lost, requests repeat, or reconciliation is needed.

### 5.2. Why Are Transactions Insufficient to Prevent Duplicate Transfers?

A transaction protects atomicity **for a single execution**. It does not stop external clients from submitting two identical transfer requests carrying two different operation IDs. For payments, design:

- Caller-supplied idempotency keys verified and bound to request content.
- Duplicate prevention via database unique keys.
- Payload mismatch detection for reused keys -> **never silently reuse**.
- Audit trails and reconciliation when commit outcomes are unknown.

Specifically, **never call third-party payment APIs, send emails, or publish messages directly inside a transaction callback**, as the callback can run multiple times after transient failures. Use a transactional outbox or post-transaction workflow with idempotent delivery.

## 6. Java Driver: Prefer the `withTransaction` Callback When Possible

The MongoDB Java Driver offers `ClientSession.withTransaction(...)`, managing transaction lifecycle and implementing retry rules per the driver transaction specification. This is usually a better starting point than hand-rolling `while` loops around `commitTransaction` and catching network exceptions yourself.

### 6.1. Preparing Collections and Data

Using test database `shop`:

```javascript
use shop

db.wallets.insertMany([
  { _id: "WALLET-A", tenantId: "TENANT-A",
    balanceMinor: NumberLong(100000), version: NumberLong(1) },
  { _id: "WALLET-B", tenantId: "TENANT-A",
    balanceMinor: NumberLong(20000), version: NumberLong(1) }
])

db.transfers.createIndex(
  { tenantId: 1, operationId: 1 },
  { unique: true, name: "uq_transfer_tenant_operation" }
)
```

The Java example below uses a globally unique, stable transfer `_id` (or an unambiguous encoding of tenant + operationId), while also storing `tenantId` and `operationId` fields for verification. The unique index on tenant/operationId provides an extra layer of protection.

**Never run `insertMany` repeatedly against an unreset database**: seeding runs once on a fresh test database. Failure and retry experiments must use isolated test data or ID-scoped cleanup.

### 6.2. TransactionOptions

```java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;

TransactionOptions options = TransactionOptions.builder()
    .readPreference(ReadPreference.primary())
    .readConcern(ReadConcern.SNAPSHOT)
    .writeConcern(WriteConcern.MAJORITY)
    .build();
```

- `ReadPreference.primary()`: directs transaction operations to primary per MongoDB requirements.
- `ReadConcern.SNAPSHOT`: sets the transaction read visibility rule; does not automatically prevent all write skew or replace business constraints.
- `WriteConcern.MAJORITY`: applies to commit/acknowledgment per supported rules; never pass individual per-statement write concerns inside a transaction.

Driver and session coordinate these options with topology; options do not guarantee success if network, nodes, or data conflict.

### 6.3. Java Code Using withTransaction

File `WalletTransferService.java`:

```java
package com.example.shop.wallet;

import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import java.util.Objects;
import org.bson.Document;

public final class WalletTransferService {

    private final MongoClient client;
    private final MongoDatabase db;

    public WalletTransferService(MongoClient client) {
        this(client, "shop");
    }

    // Allows integration tests to use an isolated database.
    public WalletTransferService(
            MongoClient client, String databaseName) {
        this.client = Objects.requireNonNull(client);
        this.db = client.getDatabase(
            Objects.requireNonNull(databaseName));
    }

    public record TransferRequest(
        String tenantId,
        String operationId,
        String fromWalletId,
        String toWalletId,
        long amountMinor
    ) {}

    public record TransferReceipt(
        String operationId, String status) {}

    public TransferReceipt transfer(TransferRequest req) {
        validate(req);

        MongoCollection<Document> wallets =
            db.getCollection("wallets");
        MongoCollection<Document> transfers =
            db.getCollection("transfers");

        TransactionOptions txnOptions =
            TransactionOptions.builder()
                .readPreference(ReadPreference.primary())
                .readConcern(ReadConcern.SNAPSHOT)
                .writeConcern(WriteConcern.MAJORITY)
                .build();

        try (ClientSession session = client.startSession()) {
            return session.withTransaction(() -> {
                // Callback may run MULTIPLE times when the driver
                // retries the ENTIRE transaction.
                transfers.insertOne(
                    session,
                    new Document("_id", req.operationId())
                        .append("tenantId", req.tenantId())
                        .append("operationId", req.operationId())
                        .append("fromWalletId", req.fromWalletId())
                        .append("toWalletId", req.toWalletId())
                        .append("amountMinor", req.amountMinor())
                        .append("state", "COMMITTED"));

                UpdateResult debit = wallets.updateOne(
                    session,
                    Filters.and(
                        Filters.eq("_id", req.fromWalletId()),
                        Filters.eq("tenantId", req.tenantId()),
                        Filters.gte(
                            "balanceMinor", req.amountMinor())
                    ),
                    Updates.combine(
                        Updates.inc(
                            "balanceMinor", -req.amountMinor()),
                        Updates.inc("version", 1L)
                    ));

                if (debit.getMatchedCount() != 1) {
                    throw new IllegalStateException(
                        "Source wallet missing or insufficient balance");
                }

                UpdateResult credit = wallets.updateOne(
                    session,
                    Filters.and(
                        Filters.eq("_id", req.toWalletId()),
                        Filters.eq("tenantId", req.tenantId())
                    ),
                    Updates.combine(
                        Updates.inc(
                            "balanceMinor", req.amountMinor()),
                        Updates.inc("version", 1L)
                    ));

                if (credit.getMatchedCount() != 1) {
                    throw new IllegalStateException(
                        "Destination wallet does not exist");
                }

                // Record stays INSIDE transaction; visible only
                // after commit succeeds.
                return new TransferReceipt(
                    req.operationId(), "COMMITTED");
            }, txnOptions);
        }
    }

    private static void validate(TransferRequest req) {
        Objects.requireNonNull(req, "req");
        if (req.tenantId() == null || req.tenantId().isBlank()
                || req.operationId() == null
                || req.operationId().isBlank()
                || req.fromWalletId() == null
                || req.toWalletId() == null
                || req.fromWalletId().equals(req.toWalletId())
                || req.amountMinor() <= 0
                || req.amountMinor() == Long.MIN_VALUE) {
            throw new IllegalArgumentException(
                "Invalid transfer request");
        }
    }
}
```

**Permission note:** `tenantId` in `TransferRequest` must be derived from or verified against server-side authentication. A client merely sending `tenantId="TENANT-A"` must not be trusted to transfer tenant A's funds.

`TransferReceipt("COMMITTED")` is instantiated **inside the body**, yet only returned by `transfer(...)` after `withTransaction(...)` finishes cleanly. If commit is unknown and the driver throws an exception, callers **must not send a success receipt** just because the callback built that object.

The code uses the MongoDB Java Driver sync API; `withTransaction` method availability/signatures may differ on very old driver releases. It illustrates transaction mechanics, not a complete production transfer system: you still need amount limits, overflow guards, destination validation, payload idempotency, observability, and reconciliation.

### 6.4. What Does `withTransaction` Do During Retries?

The driver callback API follows the specification's error-label retry rules, including:

1. Running the body inside a transaction.
2. If the body hits an error labeled `TransientTransactionError` within retry budget, **starting a new transaction and re-invoking the callback**.
3. Once the body completes, invoking commit.
4. If commit returns `UnknownTransactionCommitResult` and remains eligible to retry, **retrying commit** without re-running the callback merely because acknowledgment was unclear.
5. When unrecoverable, throwing an exception for the application to handle/reconcile.

**Do not treat `withTransaction` as an "exactly once" engine for code inside the callback.** The callback can execute multiple times. The driver also enforces retry limits and time budgets; never wrap an outer retry loop **around `withTransaction`** when exceptions report an unknown commit outcome.

### 6.5. Callbacks Must Have No Side Effects Outside Transactions

**Anti-pattern:**

```java
session.withTransaction(() -> {
    wallets.updateOne(session, filter, update);
    emailService.sendTransferSuccessEmail(userEmail);
    return null;
});
```

If the callback re-runs due to TTE, the email gets sent twice even though MongoDB commits only one attempt. If commit ultimately fails, the email may be sent even though no transfer committed.

Solution: write an **outbox event** inside the same MongoDB transaction, then let a worker dispatch emails/messages **after commit** with its own idempotency/retry mechanism. Outbox preserves atomicity between business data and event intent; it **does not** make network delivery strictly once unless consumers also deduplicate.

## 7. Writing Custom Retries: Two Loops and Two Invariants

Sometimes custom retry budgets, metrics, or exception mappings are needed. You can implement custom loops, though you should **prefer the driver helper** unless specific requirements and thorough tests justify a custom implementation.

### 7.1. Correct Pseudocode for Both Branches

```text
function runTransactionWithRetry(body, operationId):
  for transactionAttempt in boundedAttempts:
    session = newSession()
    session.startTransaction()

    try:
      result = body(session)
    catch error:
      abortCurrentTransactionBestEffort(session)
      close(session)
      if error has "TransientTransactionError"
         and overallBudgetAllowsRetry:
         applyBackoff()
         continue  # retry WHOLE TRANSACTION
      raise error

    for commitAttempt in boundedCommitAttempts:
      try:
        session.commitTransaction()
        close(session)
        return result  # confirmed
      catch error:
        if error has "UnknownTransactionCommitResult":
          if overallBudgetAllowsCommitRetry:
            applyBackoff()
            continue  # retry COMMIT of SAME txn

          close(session)
          raise CommitOutcomeUnknown(operationId)

        # Do not blindly re-run business body on commit error.
        close(session)
        raise error

  raise RetryBudgetExhausted(operationId)
```

**Two invariants to verify during code review:**

1. `continue` in the **transaction loop** opens a fresh transaction and re-invokes the body **only when allowed**.
2. `continue` in the **commit loop** re-invokes commit on the **exact same session and transaction**, never jumping out to the transaction loop to re-run the body.

A single `while(true)` loop wrapping `insert/debit/credit/commit` is **wrong** for `UnknownTransactionCommitResult`, because it fails to separate commit ambiguity from an aborted transaction.

### 7.2. Why Keep the Session When Commit Is Unknown?

Commit is part of the transaction protocol; transaction identity binds to the logical session and transaction number. On an unknown commit outcome, the client cannot open a brand-new session and call `commitTransaction()` to "finish committing" the old transaction. A fresh session does not carry the old transaction identity.

Closing the session and creating a new transaction forfeits the chance to retry-commit the original transaction. If the session or process is lost, switch to **reconciliation by operation ID**; never assume the old transaction rolled back.

### 7.3. Retry Budgets Must Be Finite

Never loop indefinitely simply because an error carries a label:

- Cap attempt counts and **overall request elapsed time**.
- Respect MongoDB transaction deadlines, server selection timeouts, and business SLAs.
- Apply backoff + jitter sensibly so clients do not stampede during primary failover.
- When commit retry budget is exhausted, preserve unknown status and transition to lookup/reconciliation.
- Never mask validation, duplicate key, configuration, or business precondition errors with infinite retries.

Illustrative retry limits must be tuned by measurement; there is no universal "3 retries is always enough" setting across workloads.

### 7.4. A Dangerous Anti-Pattern

```java
// ANTI-PATTERN: NEVER do this when commit success is unknown.
while (true) {
    try {
        performBusinessTransaction();
        break;
    } catch (RuntimeException e) {
        // Every error, including UnknownTransactionCommitResult,
        // re-runs the ENTIRE business operation.
    }
}
```

If the first request actually committed while the response got lost, the second iteration can debit funds a second time — especially if the caller generated a **new `operationId`** each iteration. Catching all exceptions and retrying indiscriminately is not fault tolerance.

## 8. Spring Data MongoDB: @Transactional Manages Transactions, Not Full Retry Policies

Spring Data MongoDB integrates with Spring Transaction Management via `MongoTransactionManager` (imperative) and `ReactiveMongoTransactionManager` (reactive). For repositories or `MongoTemplate` to participate, they must share the **database factory/session managed by the corresponding transaction manager**.

### 8.1. Configuring MongoTransactionManager

File `MongoTransactionConfiguration.java`:

```java
package com.example.shop.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration(proxyBeanMethods = false)
public class MongoTransactionConfiguration {

    @Bean("mongoTransactionManager")
    public MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory factory) {
        return new MongoTransactionManager(factory);
    }
}
```

MongoDB multi-document transactions require a transaction-capable deployment such as a properly configured replica set or sharded cluster. **A regular standalone MongoDB does not support multi-document transactions.** Never assume creating the manager bean alone suffices; verify topology, sessions, privileges, and read/write concerns.

### 8.2. `@Transactional` Service Example

File `WalletTransferWriter.java`:

```java
package com.example.shop.wallet;

import com.mongodb.client.result.UpdateResult;
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class WalletTransferWriter {

    private final MongoTemplate template;

    public WalletTransferWriter(MongoTemplate template) {
        this.template = template;
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public void writeOnce(
            String tenantId,
            String operationId,
            String fromWalletId,
            String toWalletId,
            long amountMinor) {

        // Input and tenant permissions must be validated
        // BEFORE calling the service in a real app.
        template.insert(
            new Document("_id", operationId)
                .append("tenantId", tenantId)
                .append("operationId", operationId)
                .append("fromWalletId", fromWalletId)
                .append("toWalletId", toWalletId)
                .append("amountMinor", amountMinor)
                .append("state", "COMMITTED"),
            "transfers");

        Query debitQuery = Query.query(
            Criteria.where("_id").is(fromWalletId)
                .and("tenantId").is(tenantId)
                .and("balanceMinor").gte(amountMinor));

        Update debitUpdate = new Update()
            .inc("balanceMinor", -amountMinor)
            .inc("version", 1L);

        UpdateResult debit = template.updateFirst(
            debitQuery, debitUpdate, "wallets");

        if (debit.getMatchedCount() != 1) {
            throw new IllegalStateException(
                "Source wallet missing or insufficient balance");
        }

        Query creditQuery = Query.query(
            Criteria.where("_id").is(toWalletId)
                .and("tenantId").is(tenantId));

        Update creditUpdate = new Update()
            .inc("balanceMinor", amountMinor)
            .inc("version", 1L);

        UpdateResult credit = template.updateFirst(
            creditQuery, creditUpdate, "wallets");

        if (credit.getMatchedCount() != 1) {
            throw new IllegalStateException(
                "Destination wallet missing");
        }

        // Spring transaction interceptor commits after the
        // method body returns cleanly.
    }
}
```

This assumes all `MongoTemplate` operations use the **same database factory** managed by `mongoTransactionManager`, and `writeOnce(...)` is invoked through the Spring transactional proxy. When an exception triggers rollback per Spring rules, changes inside the transaction do not commit individually.

**Important caveats:**

- `@Transactional` does not mean Spring automatically re-runs the entire method when the server returns `TransientTransactionError`.
- `@Transactional` also does not automatically retry `commitTransaction` for `UnknownTransactionCommitResult` across all versions/configs.
- If invoked via **self-invocation** within the same object bypassing the proxy, proxy-mode `@Transactional` will not fire.
- Spring's default rollback rules target unchecked exceptions; checked exceptions need explicit rollback configuration if required.
- Never swallow exceptions inside the transaction and return normally if that lets the interceptor commit an invalid business state.

### 8.3. Commit Can Fail *After the Method Body Returns*

With `@Transactional`, the sequence is:

```text
Caller
  |
  v
Spring transaction proxy
  |
  +-- begin transaction
  |
  +-- call writeOnce(...) method body
  |      |
  |      +-- method body returns normally
  |
  +-- commit transaction  <-- ERROR CAN OCCUR HERE
  |
  +-- return to Caller only after commit processing
```

Hence a `try/catch` **inside `writeOnce`** wrapping only body statements will never catch exceptions occurring **when the interceptor commits outside**. To handle unknown outcomes, error handling must sit at the **commit boundary**, not just around `template.updateFirst(...)`.

### 8.4. `TransactionTemplate` Also Does Not Turn Into `withTransaction`

`TransactionTemplate` runs a callback inside a Spring transaction:

```java
import org.springframework.transaction.support.TransactionTemplate;

// transactionTemplate configured with mongoTransactionManager.
transactionTemplate.execute(status -> {
    // MongoTemplate/repository calls sharing the factory
    // participate in the Spring-managed transaction.
    return transferWriterLogic.runBusinessSteps();
});
```

When `execute(...)` returns cleanly, the transaction manager has completed commit. Still, it remains a **Spring transaction callback**, not a full equivalent to `ClientSession.withTransaction`'s whole-body and commit-retry state machine.

Adding an outer loop around `TransactionTemplate.execute(...)` that retries on **any** exception still risks executing the body twice on unknown commit outcomes. Allow whole-transaction retries only when you confirm the attempt is safely retryable and the old transaction is aborted/cleaned up.

### 8.5. Structuring Retries with Spring

A clear separation of responsibilities:

```text
HTTP Controller
    |
    v
TransferCoordinator (validate + idempotency + retry classification)
    |
    +-- fresh transaction attempt only for retryable abort
    |
    v
WalletTransferWriter (single @Transactional invocation)
    |
    v
MongoTransactionManager
    |
    +-- commit handling at transaction boundary
```

When you specifically need `UnknownTransactionCommitResult` commit retries on the active session, consider:

1. Using `ClientSession.withTransaction(...)` in a Java Driver component where the callback algorithm is natively supported, **or**
2. Inspecting the extension points and implementation of your `MongoTransactionManager` version to implement **commit retry in the right hook** without losing transaction identity, tested against a real server, **or**
3. When commit outcome cannot be verified, **reporting unknown status** and running reconciliation/idempotency rather than re-invoking the entire service method.

Never copy an override of `MongoTransactionManager.doCommit(...)` from a different version without verifying protected/internal APIs of your actual Spring Data version. A flawed override can turn an unknown commit branch into a whole-transaction retry — the exact bug this lesson warns against.

### 8.6. `@Retryable` and AOP Ordering

If your project uses Spring Retry:

```java
// ANTI-PATTERN unless conditions, proxy ordering, and labels are verified.
@Retryable
@Transactional
public void transfer(...) {
    // business writes
}
```

Both annotations together **do not prove**:

- A fresh transaction is created per retry attempt.
- Unknown commits retry commit only.
- Retries avoid duplicating external side effects.
- Retries only fire for matching transient error labels.

Advice/proxy ordering and exception translation can shift retry boundaries. If using Spring Retry, write integration tests proving **each whole retry opens a fresh transaction**, and **unknown commits never re-trigger the body**.

### 8.7. With `ReactiveMongoTemplate`

In the reactive stack, `ReactiveMongoTransactionManager` pairs with `TransactionalOperator`/reactive `@Transactional`:

```java
import org.springframework.data.mongodb.ReactiveMongoTransactionManager;
import org.springframework.data.mongodb.ReactiveMongoDatabaseFactory;
import org.springframework.context.annotation.Bean;

@Bean("reactiveMongoTransactionManager")
ReactiveMongoTransactionManager reactiveMongoTransactionManager(
        ReactiveMongoDatabaseFactory factory) {
    return new ReactiveMongoTransactionManager(factory);
}
```

With `TransactionalOperator`:

```java
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

Mono<TransferReceipt> operation = executeBusinessWritesReactive()
    .as(transactionalOperator::transactional);
```

These variables/methods illustrate usage inside a configured reactive component. **Never** attach an unconditional `retryWhen(...)` outside the transaction-wrapped publisher: it can **re-subscribe and re-run the entire business operation** after an unknown commit outcome. Apply the same error classification, Reactor context/session lifecycle, retry budgets, and side-effect hygiene as in imperative APIs.

## 9. Retries at Different Layers

A system may have multiple layers retrying independently:

```text
Mobile/Web client    -> retries HTTP request
API Gateway          -> retries upstream request
Service              -> retries business method
Spring Transaction   -> begin/commit/rollback
MongoDB Driver       -> retries eligible commands / transaction commit
MongoDB replica set  -> network, elections, replication
```

Never stack these layers blindly assuming they form a "safe default." For example:

- Driver handles `UnknownTransactionCommitResult` by retrying commit.
- The API gateway still times out and dispatches a **brand-new request**.
- The service on that new request generates a **new `operationId`**.
- The transfer executes twice even though the driver's commit retry on the first request worked properly.

### 9.1. Retryable Writes Differ from Retrying Transactions

MongoDB provides **retryable writes** for eligible single write operations outside transactions. That mechanism does not replace multi-document transaction retry algorithms; statements inside transactions follow transaction semantics.

Never infer from `retryWrites=true` in the URI that **every transaction automatically re-runs from scratch**. Retrying `commitTransaction` and `abortTransaction` follows the driver's dedicated transaction rules.

### 9.2. What Must Be Enforced at the HTTP Boundary?

For a transfer API, a request should carry:

```json
{
  "operationId": "TRANSFER-123",
  "fromWalletId": "WALLET-A",
  "toWalletId": "WALLET-B",
  "amountMinor": 30000
}
```

When a client retries with the same operation ID:

1. Verify the actor is authorized for the tenant/wallet.
2. Look up any committed transfer record by **verified operation ID**; if found, check payload parity and return the same result.
3. If the operation is in an unknown-outcome state, return pending-reconciliation status instead of launching a new transfer immediately.
4. Only when confirmed absent and permitted, execute the new flow with idempotency guards.
5. Never generate a random `operationId` **per retry attempt** of the same business request.

Not seeing a record on a secondary **is not proof the transaction aborted**: replication lag can hide a newly committed record. Use reads/reconciliation with appropriate read concern and freshness guarantees, typically reading the primary; even an instant "not found" on the primary is not conclusive proof while another commit might still be resolving.

## 10. Idempotency: Closing the Loop on Unknown Outcomes

**Idempotency** is a business contract: executing the same valid operation ID multiple times does not apply the resulting state change multiple times.

### 10.1. Unique Index and Payload Fingerprint

```javascript
db.transfers.createIndex(
  { tenantId: 1, operationId: 1 },
  { unique: true, name: "uq_tenant_operation" }
)
```

For `operationId="TRANSFER-123"`, store:

```javascript
{
  _id: "TRANSFER-123",
  tenantId: "TENANT-A",
  operationId: "TRANSFER-123",
  fromWalletId: "WALLET-A",
  toWalletId: "WALLET-B",
  amountMinor: NumberLong(30000),
  requestFingerprint: "hash-of-canonical-request",
  state: "COMMITTED"
}
```

`requestFingerprint` must use a **stable canonicalization rule** and hashing algorithm; never hash an arbitrary JSON string whose field ordering can vary. If the same operation ID arrives with a different amount or wallet, return a conflict rather than returning the prior request's result for a non-equivalent request.

### 10.2. Unique Indexes Do Not Immediately Resolve All Unknown Commits

When transaction A has an unknown commit outcome, running a new transaction B with the same key can:

- Hit a duplicate key if A committed.
- Contend/wait/behave differently while A is still resolving.
- Conflict or raise other errors depending on topology/conditions.

Thus a unique index **prevents double-application during application retries**, rather than granting permission to skip **retrying commit on the old session** or declaring "missing record means uncommitted."

### 10.3. Outbox and End-to-End Exactly-Once

```text
MongoDB transaction:
  - debit wallet A
  - credit wallet B
  - insert transfer ledger(opId)
  - insert outbox event(eventId)
             |
             v
Commit confirmed
             |
             v
Outbox dispatcher -> broker / email / payment integration
             |
             v
Consumer deduplicates by eventId / operationId
```

If the transaction callback retries due to TTE, outbox inserts from aborted attempts are never committed. On unknown commit, **never** publish the event directly hoping it represents a committed transaction; the dispatcher must read only truly committed outbox records.

Message delivery can be at-least-once. Consumers require idempotency; MongoDB transactions cannot atomically wrap sending an email or calling a third-party API outside the transaction.

## 11. When Commit Outcome Remains Unknown After Exhausting the Retry Budget

This is the scenario requiring the utmost caution:

```text
Transaction T (operationId = TRANSFER-123)
    |
    +-- body completed
    |
    +-- commitTransaction() sent
    |       |
    |       +-- server MIGHT have committed
    |       +-- acknowledgment lost
    |
    +-- retry commit on same transaction
            |
            +-- still UnknownTransactionCommitResult
            +-- deadline exceeded

Client outcome: COMMIT_UNKNOWN
Database outcome: MAY BE COMMITTED OR NOT
```

**Never silently turn `COMMIT_UNKNOWN` into `ABORTED` or `FAILED` merely because a timeout expired.** "The client timed out" does not prove "MongoDB rolled back."

### 11.1. Distinguishing Client Outcome from Business Status

| Outcome Known by Client | Business Response to Return | May Re-Run Body Immediately? |
| --- | --- | --- |
| Commit ACK succeeded | `COMMITTED` | No |
| Body definitely aborted and whole-retry budget spent | `NOT_COMMITTED` / error retryable in a new request per policy | Only once confirmed safe, using the same operation ID |
| Unknown commit outcome | `PENDING_CONFIRMATION` / `COMMIT_UNKNOWN` | **Do not** blindly re-run |
| Data reconciled and confirmed committed | `COMMITTED`, return original receipt | No |
| Data reconciled with sufficient grounds as uncommitted | Allow idempotent request to proceed per system rules | Conditionally, using same operation ID without duplicating side effects |

`COMMIT_UNKNOWN` is an **application-level certainty status**, not necessarily a state stored inside the transaction record itself. If the transaction never committed, the transfer record inside it does not exist yet. You may need an out-of-transaction request tracker or controlled coordinator log to track pending status.

### 11.2. Reconciliation by Operation ID

When the original session is no longer available for commit retries (e.g., process crash or shutdown), run reconciliation:

1. Keep `operationId` stable alongside tenant, operation type, and payload fingerprint.
2. Read from a source with **appropriate freshness/durability**, typically the primary with suitable read concern — never rely on a lagging secondary by default.
3. If the transfer record exists with matching operation ID and payload, confirm committed state and return that same result.
4. If the record is absent, **do not immediately conclude aborted**: a commit might still be completing, or network/election/another request on the key may be in flight.
5. Enforce retry/backoff/time budgets and orchestration locking/idempotency rules.
6. If certainty cannot be established, hold the state for investigation/reconciliation or route to manual review per business policy.

### 11.3. Why "Record Not Found" May Not Be Enough

Suppose one session is still attempting commit while another API reads the ledger. Not seeing the record yet does not prove the earlier transaction **cannot** still commit afterward. Even a primary read with `readConcern:majority` is not magic proof that **every in-flight unknown transaction has finished**.

For sensitive systems, reconciliation combines:

- Operation IDs and unique indexes.
- Request state registered before the transaction begins (when architecture requires).
- Deadlines/timestamps and transaction coordination metadata.
- Reads with suitable read concern and bounded polling/re-checks.
- Reconciling business event sources of truth rather than a single negative snapshot read.

Without conclusive proof, returning "processing / confirming" is far safer than re-executing a transfer that might already have succeeded.

### 11.4. API Response for Unknown Status

An API can return a response with tracking ID and processing state:

```json
{
  "operationId": "TRANSFER-123",
  "status": "PENDING_CONFIRMATION",
  "message": "Confirming transaction outcome",
  "statusUrl": "/transfers/TRANSFER-123/status"
}
```

Exact HTTP status and contract belong to API/product design. Never return **"transfer succeeded"** before commit is confirmed. Nor return "failed, please create a new transfer" prompting users to generate a new operationId and risk double-charging.

### 11.5. Warning About Background Retries and Session Closing

When a request hits its budget while the session is still alive, driver helpers may already have attempted commit retries per policy. Applications should not finish the HTTP request while leaving an **unmonitored** background loop retrying commit on a session that may close as the request exits.

To continue processing outside the request, build a **durable workflow** (operation status, queue, reconciliation, ownership, and timeouts). Never promise callers a definite outcome backed only by an unmanaged background thread.

## 12. Three Timelines to Know by Heart

### 12.1. Body Hits Write Conflict; Transaction Aborts

```text
t0: startTransaction(T1)
t1: insert transfer ledger inside T1
t2: update wallet A inside T1
t3: concurrent write conflict -> TransientTransactionError
t4: abort/cleanup T1 (no commit)
t5: startTransaction(T2)
t6: rerun entire body: insert, debit, credit
t7: commit T2 -> success

Result:
  only writes committed in T2 take effect
  steps inside T1 are never committed
```

### 12.2. Commit Succeeded; ACK Lost

```text
t0: startTransaction(T1)
t1: insert transfer ledger inside T1
t2: debit and credit inside T1
t3: commitTransaction(T1) reaches server
t4: server commits T1
t5: connection drops before client sees success
t6: client gets UnknownTransactionCommitResult
t7: client retries commitTransaction(T1), same session / identity
t8: commit retry resolves outcome

Result:
  business body executes ONCE in T1
  no T2 is created merely because commit ACK was lost
```

### 12.3. Commit Outcome Remains Unknown After Multiple Retries

```text
t0: startTransaction(T1)
t1: body completes
t2: commitTransaction(T1) sent
t3: UnknownTransactionCommitResult
t4: retry commit T1
t5: UnknownTransactionCommitResult
t6: request budget exhausted / session unavailable
t7: API returns PENDING_CONFIRMATION
t8: reconciliation uses stable operationId

Result:
  must NOT guess COMMITTED or ABORTED at t6
```

**Common principle:** error-handling code must reflect **the phase where the failure happened and what is known about transaction state**, not just string-matching `"timeout"` or `"network error"`.

## 13. Retry Budget, Transaction Lifetime, and Exponential Backoff

Retries are not free:

- Each transaction attempt re-reads and re-computes from scratch.
- Long transactions retain server resources, increase conflict odds, and pressure replication/locks.
- During a primary election, hundreds of clients retrying simultaneously can trigger load spikes.
- Commit retries awaiting acknowledgment extend user-facing tail latency.

### 13.1. Two Separate Budgets

| Budget | Applies To | When Exhausted |
| --- | --- | --- |
| Transaction retry budget | Number of **whole-body** attempts after valid transient errors | Stop creating new attempts; return error or escalate per policy |
| Commit retry budget | Attempts to confirm commit outcome **on the same transaction** | Preserve `COMMIT_UNKNOWN` if outcome stays unresolved |

Also enforce an **overall operation deadline**. Illustrative structure:

```text
Business SLA:       10 seconds
Transaction tries:  bounded and backoff
Commit retries:     bounded and backoff
On commit unknown:  stop guessing, reconcile
```

Exact numbers are examples; derive them empirically alongside transaction/server limits. Never design a retry loop running longer than several times the transaction lifetime or client timeout without intention.

### 13.2. Apply Backoff Only Where Retries Are Valid

Backoff/jitter helps under write conflicts or elections, yet **never** turns a non-retryable error into a retryable one. For `UnknownTransactionCommitResult`, backoff sits **between commit retries**; for `TransientTransactionError` in the body, backoff sits **between fresh transaction attempts**.

Never put `Thread.sleep` arbitrarily on a Java reactive event loop. In reactive code, use controlled retry/cancellation operators aligned to the exact phase and error label.

### 13.3. Choose TransactionOptions Deliberately

Verify:

1. Does `readPreference` fit transactions (usually primary)?
2. Does `readConcern` meet snapshot/consistency needs?
3. Does commit `writeConcern` require majority?
4. Do server selection and network timeouts stay within the application SLA?
5. Could the session close while commit retries are still running?
6. Does the transaction run any operation unsupported by your deployment/version?

Never switch to `writeConcern: 1` just to shave latency when business needs failover-durable commits; nor assume `majority` guarantees commit ACKs always succeed during outages.

## 14. MongoDB Error Labels and Driver Exception Translation

With the Java Driver, classify via `MongoException.hasErrorLabel`:

```java
import com.mongodb.MongoException;

public static boolean hasMongoErrorLabel(
        Throwable error, String label) {
    for (Throwable current = error;
            current != null;
            current = current.getCause()) {
        if (current instanceof MongoException mongo
                && mongo.hasErrorLabel(label)) {
            return true;
        }
    }
    return false;
}
```

In a Spring Data application, exceptions may be wrapped/translated by Spring's exception translator. Walking the cause chain detects MongoDB labels **when the driver cause is preserved**; if a wrapper strips the cause, inspect translation behavior and emit structured logs at the transaction boundary.

**Note:** never implement a naive rule like:

```java
// ANTI-PATTERN: relies only on exception class, ignorant of phase.
if (ex instanceof java.net.SocketTimeoutException) {
    retryEntireBusinessTransaction();
}
```

A timeout can happen before commit or after the server committed yet before ACK. Without phase and error labels, **retrying the whole business logic is dangerous**.

### 14.1. Other Labels May Exist

MongoDB defines additional error labels for retryable writes and other conditions depending on version. `RetryableWriteError` is not equivalent to `TransientTransactionError`, and raw error codes alone do not replace transaction label semantics.

Avoid hardcoding an error-code table like "if 91 or 11600 then retry transaction" while ignoring error labels, failure phase, and transaction state. For compatibility across server/driver versions, use the driver API and official transaction error-handling guidelines.

### 14.2. Write Concern Errors at Commit

Commit may already have succeeded on the server while the client receives a durability/write-concern error. When the driver attaches `UnknownTransactionCommitResult`, **never assume all changes rolled back**. This differs from body validation or duplicate-key errors prior to commit.

That is why outcome reporting must separate **"commit ACK not received"** from **"server confirmed abort"** and **"server rejected business command."**

## 15. Integration Testing Transactions on a Real Replica Set

Mocking `MongoTemplate` or `MongoCollection` checks method call order, yet **cannot prove** the transaction is truly atomic, commits reached majority, or error labels behave properly across failovers. You need a **dedicated test MongoDB replica set**; a plain standalone server is insufficient.

### 15.1. Test Structure

| Scenario | What Must Be Proven |
| --- | --- |
| Successful transaction | Both wallets update together, total balance preserved, exactly one ledger record |
| Exception thrown mid-way | No one-sided debit, no committed transfer record |
| Retrying same `operationId` as a new request | No double credit/debit; service/coordinator resolves duplicate via idempotency |
| Transient write conflict | **Whole body** can re-run in a fresh transaction |
| Unknown commit result | Retries commit **of the active transaction only**; never re-runs body for lost ACK |
| Driver/process loses session | Transitions to reconciliation using `operationId` |
| Another tenant uses similar ID | Never reads/writes across tenants without permission |
| Exhausted retry budget | Unknown commit outcome stays reported as unresolved |

### 15.2. JUnit 5 Example Checking Atomicity and Idempotency

The following test uses the MongoDB driver directly. It requires the `TX_REPLICA_TEST_URI` environment variable pointing to an **authorized test replica set**, never production. Test IDs are randomized and cleaned up **strictly by ID** so other tests' data is untouched.

File `WalletTransferTransactionIntegrationTest.java`:

```java
package com.example.shop.wallet;

import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.bson.Document;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class WalletTransferTransactionIntegrationTest {

    @Test
    void transferCommitsBothWalletsAndAbortsOnMissingDestination() {
        String uri = System.getenv("TX_REPLICA_TEST_URI");
        Assumptions.assumeTrue(
            uri != null && !uri.isBlank(),
            "Requires a dedicated TEST MongoDB replica set");

        // This database must be isolated and strictly for CI.
        String databaseName = "tx_retry_lesson_it";
        String suffix = UUID.randomUUID().toString();
        String fromId = "SRC-" + suffix;
        String toId = "DST-" + suffix;
        String operationId = "TRANSFER-" + suffix;
        String failingId = "FAILED-" + suffix;
        String nonexistentId = "MISSING-" + suffix;

        try (MongoClient client = MongoClients.create(uri)) {
            var db = client.getDatabase(databaseName);
            // Prepare collection BEFORE the first transaction.
            if (!db.listCollectionNames()
                    .into(new ArrayList<String>())
                    .contains("transfers")) {
                db.createCollection("transfers");
            }
            MongoCollection<Document> wallets =
                db.getCollection("wallets");
            MongoCollection<Document> transfers =
                db.getCollection("transfers");

            wallets.insertMany(List.of(
                new Document("_id", fromId)
                    .append("tenantId", "TENANT-TEST")
                    .append("balanceMinor", 100000L)
                    .append("version", 1L),
                new Document("_id", toId)
                    .append("tenantId", "TENANT-TEST")
                    .append("balanceMinor", 20000L)
                    .append("version", 1L)
            ));

            try {
                WalletTransferService service =
                    new WalletTransferService(
                        client, databaseName);

                WalletTransferService.TransferRequest request =
                    new WalletTransferService.TransferRequest(
                        "TENANT-TEST", operationId,
                        fromId, toId, 30000L);

                var receipt = service.transfer(request);
                assertThat(receipt.operationId())
                    .isEqualTo(operationId);
                assertThat(receipt.status())
                    .isEqualTo("COMMITTED");

                assertThat(wallets.find(
                    Filters.eq("_id", fromId))
                    .first().getLong("balanceMinor"))
                    .isEqualTo(70000L);

                assertThat(wallets.find(
                    Filters.eq("_id", toId))
                    .first().getLong("balanceMinor"))
                    .isEqualTo(50000L);

                assertThat(transfers.countDocuments(
                    Filters.eq("_id", operationId)))
                    .isEqualTo(1L);

                // Missing destination wallet: transaction must abort.
                var invalidDestination =
                    new WalletTransferService.TransferRequest(
                        "TENANT-TEST", failingId,
                        fromId, nonexistentId, 1000L);

                assertThatThrownBy(
                    () -> service.transfer(invalidDestination))
                    .isInstanceOf(IllegalStateException.class);

                // Debit in the failed transaction must not commit.
                assertThat(wallets.find(
                    Filters.eq("_id", fromId))
                    .first().getLong("balanceMinor"))
                    .isEqualTo(70000L);
                assertThat(transfers.countDocuments(
                    Filters.eq("_id", failingId)))
                    .isZero();

                // HTTP retry with the same operationId is NOT
                // a commit retry. Raw service fails with duplicate;
                // an idempotency coordinator must fetch the old
                // receipt instead of debiting again.
                assertThatThrownBy(
                    () -> service.transfer(request))
                    .isInstanceOf(RuntimeException.class);

                assertThat(wallets.find(
                    Filters.eq("_id", fromId))
                    .first().getLong("balanceMinor"))
                    .isEqualTo(70000L);

            } finally {
                // Never drop collections or run deleteMany({}).
                wallets.deleteMany(Filters.in(
                    "_id", fromId, toId));
                transfers.deleteMany(Filters.in(
                    "_id", operationId, failingId));
            }
        }
    }
}
```

**Explicit limitations:** this test verifies atomicity, sum preservation, and duplicate prevention via operation ID. It **does not actively inject `TransientTransactionError` or `UnknownTransactionCommitResult`**, so it is **not** proof of all retry branches. Dedicated fault-injection tests are required for those branches.

**Safety warning:** run only when the supplied URI points to a **TEST replica set**. Even with ID-scoped cleanup, writing to the wrong database is risky. Verify CI deployment config and use MongoDB credentials restricted strictly to the test database; never default to a production URI.

### 15.3. Controlled TTE and UTCR Fault Testing

To accurately reproduce both branches, a test environment can use MongoDB **failpoints** or privileged fault injection on an isolated test cluster. Failpoints require explicit fixture setup/cleanup and must never run on shared clusters.

**Scenario A — `TransientTransactionError` in the body:**

1. Start transaction T1.
2. Trigger a write conflict or a transient error labeled TTE on a **statement inside the body**.
3. Verify T1 did not commit.
4. Observe the callback/body re-executing **in a fresh transaction attempt** when the helper permits retries.
5. Verify final state reflects **exactly one business operation**, with no duplicate ledger entries.

**Scenario B — `UnknownTransactionCommitResult`:**

1. T1's body finishes.
2. Controlled fault injection at `commitTransaction` triggers an error labeled UTCR.
3. Verify callback invocation count **does not increase due to UTCR**; commit is retried on the same transaction identity.
4. Once the final ACK succeeds, verify ledger and both balances match.
5. When deliberately keeping commit unknown past the budget, verify the app **does not report `"ABORTED"`** and **never restarts the transfer with a new ID**.

**Never treat an arbitrary network disconnect as a guaranteed UTCR test.** The failure might lack the target label or occur before commit was even transmitted. Tests must verify the **error label and exact phase**, not merely that an exception occurred.

### 15.4. Do Not Assert Callback Invocation Count Always Equals 1

When the transaction body hits TTE, the callback **may run multiple times**, and that is correct behavior. What actually matters:

- **Committed state:** each valid transfer appears once and total funds are conserved.
- **Callback invocations:** may exceed 1 during whole-transaction retries.
- **Commit invocations:** may exceed 1 during UTCR, without repeating the callback for an ambiguous commit.
- **External side effects:** never executed inside a repeating callback; verify outbox/idempotency.

Focus on invariants and final state; avoid writing tests asserting "callback called once" that break valid driver retries.

## 16. Conditions That Cannot Be Fixed by Re-Running the Transaction

Not every transaction failure is transient:

| Failure | Retry Whole Transaction Automatically? | Reason |
| --- | --- | --- |
| Clear `TransientTransactionError` when body aborted | **Conditionally** | Transient failure; a fresh attempt may succeed |
| Duplicate `operationId` | **Never automatically** | Likely an already-processed request; check idempotency/payload |
| MongoDB `$jsonSchema` validation error | No | Invalid schema or data will keep failing |
| Insufficient balance or missing source wallet | No | Business precondition not met |
| Other unique index violation | No | Business/key collision; retrying won't fix it |
| Unknown commit outcome | **No** | Retry **commit**, never replay body |
| Session lost after unknown commit | Never blindly | Reconcile by operation ID |
| Auth/permission error | No | Fix permissions/configuration |
| Transaction exceeded lifetime/resource limits | Never loop infinitely | Optimize transaction or split work |
| Network timeout without phase/label info | Never guess by exception name | Must account for possible prior commit |

### 16.1. Transactions Do Not Replace Business Invariants

Multi-document transactions provide **atomicity**, yet concurrent transactions still require checking predicates right on the **write command**:

```java
// Right idea: debit only when balance >= amount.
Filters.and(
    Filters.eq("_id", fromWalletId),
    Filters.eq("tenantId", tenantId),
    Filters.gte("balanceMinor", amountMinor)
)
```

Avoid:

```text
1. read balance = 100000
2. compute new balance = 70000
3. update without conditioning on current balance/version
```

When concurrent writers hit the same account, conflicts and retries may occur, yet **a transaction never turns missing predicate logic into valid business logic**. Use atomic conditional updates, unique constraints, expected versions, and proper account/ledger modeling.

### 16.2. Never Hold Transactions Open Across External Service Calls

```text
startTransaction
  -> call external payment API (possibly seconds)
  -> wait for human approval
  -> update MongoDB
commitTransaction
```

This is a risky design: transactions stay open too long, hold resources, time out/abort easily, and external side effects never roll back with the database. For long workflows, use **sagas/workflows and outboxes** instead of keeping MongoDB transactions open.

## 17. A Small Classifier to Test Retry Reasoning

When implementing retry logic in a framework or library, separating **"what to do next"** from executing side effects is helpful. The example below is an **illustrative classifier**, not a replacement for the driver's transaction callback.

```java
package com.example.shop.tx;

public final class TransactionRetryDecision {

    public enum Phase { BODY, COMMIT }

    public enum Action {
        RETRY_WHOLE_TRANSACTION,
        RETRY_SAME_COMMIT,
        RECONCILE_UNKNOWN_COMMIT,
        STOP_AND_HANDLE
    }

    private TransactionRetryDecision() {}

    public static Action decide(
            Phase phase,
            boolean hasTransientTransactionError,
            boolean hasUnknownCommitResult,
            boolean retryBudgetRemaining) {

        if (phase == Phase.COMMIT
                && hasUnknownCommitResult) {
            return retryBudgetRemaining
                ? Action.RETRY_SAME_COMMIT
                : Action.RECONCILE_UNKNOWN_COMMIT;
        }

        if (phase == Phase.BODY
                && hasTransientTransactionError
                && retryBudgetRemaining) {
            return Action.RETRY_WHOLE_TRANSACTION;
        }

        return Action.STOP_AND_HANDLE;
    }
}
```

This is an **intentionally scoped classifier**: it does not interpret every label possible in the commit phase, handle session cleanup, or replace session-outcome verification. It tests one minimal invariant: **UTCR at commit must never map to `RETRY_WHOLE_TRANSACTION`**.

### 17.1. Classifier Unit Tests

```java
package com.example.shop.tx;

import org.junit.jupiter.api.Test;

import static com.example.shop.tx.TransactionRetryDecision.Action.*;
import static com.example.shop.tx.TransactionRetryDecision.Phase.*;
import static org.assertj.core.api.Assertions.assertThat;

class TransactionRetryDecisionTest {

    @Test
    void transientBodyErrorStartsFreshTransaction() {
        assertThat(TransactionRetryDecision.decide(
            BODY, true, false, true))
            .isEqualTo(RETRY_WHOLE_TRANSACTION);
    }

    @Test
    void unknownCommitDoesNotReplayBusinessBody() {
        assertThat(TransactionRetryDecision.decide(
            COMMIT, false, true, true))
            .isEqualTo(RETRY_SAME_COMMIT);
    }

    @Test
    void exhaustedUnknownCommitMustBeReconciled() {
        assertThat(TransactionRetryDecision.decide(
            COMMIT, false, true, false))
            .isEqualTo(RECONCILE_UNKNOWN_COMMIT);
    }

    @Test
    void validationAndBusinessErrorsDoNotAutoRetry() {
        assertThat(TransactionRetryDecision.decide(
            BODY, false, false, true))
            .isEqualTo(STOP_AND_HANDLE);
    }

    @Test
    void exhaustedBodyBudgetDoesNotLoopForever() {
        assertThat(TransactionRetryDecision.decide(
            BODY, true, false, false))
            .isEqualTo(STOP_AND_HANDLE);
    }
}
```

This is a **pure Java unit test**, needing no MongoDB. It verifies **decision logic only**, not whether the driver resends commit with the same `lsid`/`txnNumber` or whether Spring's transaction manager initializes sessions properly. Those still require integration/fault-injection tests.

## 18. Observability: Logs and Metrics Must Separate Both Retry Types

If a system logs `"transaction retry"` identically for all cases, on-call engineers can misdiagnose incidents:

- A burst of write conflicts spikes **transaction attempts**.
- Network instability during commit spikes **commit retries**.
- Both have different impacts, alert thresholds, and fixes.

### 18.1. Recommended Metrics

| Metric | Meaning |
| --- | --- |
| `transaction_attempts_total` | Number of transaction attempts started |
| `transaction_body_retries_total` | Decisions to re-run whole body after transient errors |
| `transaction_commit_retries_total` | Commit retries on existing transactions |
| `transaction_commit_unknown_total` | Unknown commit outcomes received |
| `transaction_commit_unknown_unresolved` | Operations needing reconciliation |
| `transaction_aborts_total` | Aborted attempts categorized by reason |
| `transaction_duration_seconds` | Total duration from transaction start to attempt end |
| `transaction_commit_latency_seconds` | Commit processing/acknowledgment latency |
| `transaction_retry_budget_exhausted_total` | Budget exhaustion count by phase |
| `transaction_reconciliation_age_seconds` | Age of operations pending confirmation |
| `duplicate_operation_key_total` | Frequency of client/API retries carrying existing operation IDs |

Never put operation IDs or user IDs in **high-cardinality metric labels**. Use controlled correlation IDs in traces/logs; in metrics, use bounded labels like phase, error label, service, collection, and outcome.

### 18.2. Structured Log Example

```json
{
  "event": "mongo_transaction_retry",
  "operationType": "wallet_transfer",
  "operationRef": "safe-correlation-id",
  "phase": "COMMIT",
  "errorLabel": "UnknownTransactionCommitResult",
  "action": "RETRY_SAME_COMMIT",
  "transactionAttempt": 1,
  "commitAttempt": 2,
  "outcome": "UNCONFIRMED"
}
```

Never log real account numbers, tokens, credentials, PII payloads, or raw session data in ways that create security exposure. `operationRef` should be a safe tracking reference rather than sensitive payment data.

### 18.3. Useful Operational Alerts

- TTE rate rises: inspect write conflicts, long transactions, lock contention, elections, and hot-document access patterns.
- UTCR rate rises: inspect network between client and MongoDB, commit latency, write concern timeouts, elections, and server logs.
- Pending reconciliations grow: check reconciliation jobs, ledger data, idempotency health, and outcome-confirmation bottlenecks.
- Duplicate operation IDs spike: inspect gateway/client retries and UX; do not assume all duplicates are attacks.
- Transaction duration climbs: reduce operations inside transactions, optimize indexes, and remove external calls.

## 19. Diagnosing Real-World Scenarios

### 19.1. "I see MongoWriteException inside the body — should I retry?"

First determine:

1. Does the error carry the `TransientTransactionError` label?
2. Is the active transaction attempt still valid, or did the server abort it?
3. Did any external non-MongoDB side effect already execute?
4. Do you still have retry budget and a stable operation ID?

If the error is a duplicate key on the operation ID, run idempotency lookup. If it carries TTE per driver rules, retry the **whole body** in a fresh transaction. Never decide based solely on the exception class name.

### 19.2. "Commit timed out; I don't see the transfer record on a secondary"

You cannot conclude the transaction failed. The secondary may simply lag while commit actually succeeded. Keep `COMMIT_UNKNOWN`, prefer retrying commit on the same session if possible; if the session is gone, reconcile on a read path with proper freshness/read concern and operation ID, never treating a single negative read as proof of abort.

### 19.3. "The @Transactional method ran once — why was the user charged twice?"

Inspect layers outside the Spring transaction:

- Did the API gateway retry the `POST` after a timeout?
- Did the client retry with a **new** operation ID?
- Did service code catch all exceptions and re-invoke the method?
- Did two application instances process the same request?
- Were the unique key and request fingerprint saved and verified?

Two atomically committed transactions **across two separate requests** still cause a business bug if idempotency keys are missing.

### 19.4. "I added @Retryable around @Transactional; commit errors dropped yet the ledger has duplicates"

This signals you may be retrying the **whole business operation** after an unknown commit. Check:

- How retry advice wraps the transaction boundary.
- Whether commit errors carried `UnknownTransactionCommitResult` and were classified properly.
- Whether each callback invocation generated a new operation ID.
- Whether external side effects sit inside the callback.

Fix it at the **commit boundary and idempotency layer**, not merely by lowering retry counts.

### 19.5. "`withTransaction` still threw an exception despite driver retries"

Retries do not guarantee eventual success. Causes include:

- Exhausting the helper's retry budget/deadline.
- Non-transient errors such as validation, duplicate key, or business exceptions.
- Unrecovered server or network outages.
- Transaction exceeding resource/time limits.
- Commit outcome remaining unknown.

Never "fix" this by wrapping `while(true)` around `withTransaction`. Classify the exception, establish provable final state, and hand off to reconciliation when needed.

### 19.6. "Wallet balances match, yet the email went out twice"

The MongoDB transaction likely retried the body after TTE, sending the email **inside the callback** on each run. Move email emission to an **outbox record inside the transaction** and let an idempotent dispatcher/consumer handle sending. Database abort cannot unsend emails.

### 19.7. "Calling abort also threw an exception"

`abortTransaction` is best-effort cleanup. During network/election failures, abort can also fail; never let the secondary abort error swallow the original failure without logging. If the body definitely aborted per reliable info, retry a new attempt on TTE; if commit outcome was unknown, **never call abort and claim the transaction rolled back**.

## 20. Code Review Checklist Before Shipping Retries to Production

### 20.1. Transactions and Sessions

1. **Right deployment:** MongoDB runs a transaction-capable replica set/sharded cluster, never mistaken for standalone.
2. **Same session:** body operations share the **exact same transaction/session**; Spring repositories and `MongoTemplate` share factory/session binding.
3. **Clear boundaries:** you know exactly where transactions begin and commit, especially with `@Transactional` proxies.
4. **Right transaction options:** read preference, read concern, write concern, and timeouts match contract.
5. **Keep it short:** transactions never wait on HTTP calls, emails, or external APIs.
6. **Do not mix clients:** a Spring transaction never automatically spans a separate client/factory.
7. **Proper cleanup:** abort/close sessions on body failures; never call abort to "prove" an unknown commit failed.

### 20.2. Retry Classification

8. **Classify by phase:** did the error happen in the body or at commit?
9. **Check labels:** handle `TransientTransactionError` and `UnknownTransactionCommitResult` differently.
10. **TTE in body:** retry the whole body on a **fresh transaction attempt** after cleanup.
11. **UTCR at commit:** retry **commit on the active session/transaction**, never re-running the body.
12. **Business/schema errors:** stop immediately; never loop infinitely.
13. **Bounded retries:** enforce attempt limits, overall deadline, and sensible backoff/jitter.
14. **Budget spent on unknown commit:** hold `PENDING_CONFIRMATION`, never assume abort.
15. **No blind HTTP retries:** gateway, client, and service must share the idempotency key.

### 20.3. Data and Business Impact

16. **Stable operation ID:** the same business request reuses the exact same key across attempts and requests.
17. **Proper unique keys:** prevent double-application and tenant leaks.
18. **Payload fingerprint:** same ID with different content must return conflict.
19. **No external side effects in callback:** use outboxes and consumer deduplication.
20. **Conditional writes:** sufficient balance, matching tenant, expected version — never rely solely on reads at transaction start.
21. **Amount checks:** prevent overflow, invalid negatives, and currency mismatches.
22. **Durable reconciliation:** look up by operation ID after restarts.
23. **Distinguish confirmed vs unknown:** HTTP responses and audits never lie about commit status.

### 20.4. Validation and Operations

24. **Atomicity tests:** failure mid-way leaves zero partial updates.
25. **TTE tests:** callback can run multiple times while business outcome occurs once.
26. **UTCR tests:** commit retries never repeat the body, even when ACK is lost.
27. **Request idempotency tests:** same operation ID returns stable result or explicit conflict.
28. **Never test on production:** failpoints, elections, and collection drops belong strictly on test clusters.
29. **Separate observability:** track transaction attempts, commit retries, unknown outcomes, timeouts, and reconciliation age.
30. **Controlled rollouts:** feature flags/monitoring when altering retry policies or transaction managers.

## 21. Quick Decision Matrix

| Observation | Right Action | Wrong Action to Avoid |
| --- | --- | --- |
| Write conflict in body, server/driver reports `TransientTransactionError` | Abort/clean up and **retry whole transaction** in a fresh attempt | Retrying only the conflicting statement inside the aborted tx |
| `commitTransaction` loses ACK and reports `UnknownTransactionCommitResult` | **Retry commit on the same session/txn identity** | Re-running debit/credit in a new transaction |
| Commit stays unknown past deadline | `PENDING_CONFIRMATION`, reconcile via operation ID | Declaring definite failure and encouraging a new operation ID |
| Duplicate transfer operation ID | Verify payload and committed state | Treating as transient and creating another transfer |
| MongoDB validation error | Fix request/schema/migration | Retrying identically forever |
| API gateway retries POST after timeout | Reuse same idempotency key and inspect ledger | Generating a new operation ID per request |
| Callback re-runs after TTE | Keep callback purely rollbackable/idempotent | Sending emails or calling third-party payments directly |
| Spring `@Transactional` method reaches body return | Remember commit runs in the interceptor afterward | Catching commit errors via `try/catch` inside the body |
| Missing compliant replica set | Provision topology/transaction support first | Assuming a transaction manager bean suffices |
| Tests only assert service response succeeded | Assert BSON state and invariants after commit/abort | Claiming commit-retry coverage without fault injection |

## 22. Hands-on Exercises

A reservation service uses `seats` and `reservations` collections. Every booking request carries an application-stabilized `reservationId`; users may retry HTTP calls over flaky networks.

### Exercise 1 — Error Classification

Evaluate each situation:

1. The transaction decremented `availableSeats`, then inserting the reservation hits `TransientTransactionError` due to a write conflict.
2. Body commands succeed; `commitTransaction` disconnects and the driver attaches `UnknownTransactionCommitResult`.
3. A second commit attempt still hits `UnknownTransactionCommitResult` and the overall deadline expires.
4. `reservationId` triggers duplicate key.
5. Filter `availableSeats >= 1` matches nothing.
6. HTTP POST times out **after commit actually succeeded**.

For each situation, determine:

- Was the body confirmed aborted, or is commit outcome unknown?
- Should you retry the whole transaction, retry commit, or stop/reconcile?
- Must `reservationId` remain unchanged?
- What should the API return so no double booking happens?

**Hints:**

| Situation | Decision |
| --- | --- |
| 1 | Abort/clean up attempt and retry **whole body** if TTE and within budget |
| 2 | Retry **commit of the same transaction**, keeping the session |
| 3 | `PENDING_CONFIRMATION` and reconcile; never blindly re-run booking |
| 4 | Verify idempotency/payload; never silently swap `reservationId` |
| 5 | Business sold-out error; no reason to keep retrying |
| 6 | HTTP retry with the **same `reservationId`**, look up committed result |

### Exercise 2 — Find Bugs in the Code

```java
// BUGGY: fails to distinguish unknown commit from aborted transaction.
for (int i = 0; i < 5; i++) {
    try {
        createReservation(UUID.randomUUID().toString());
        break;
    } catch (Exception e) {
        Thread.sleep(100);
    }
}
```

Identify at least five flaws:

1. Generates a different `reservationId` on every attempt.
2. Retries every exception, including business failures.
3. Fails to classify body vs commit phase.
4. Fails to distinguish `TransientTransactionError` from `UnknownTransactionCommitResult`.
5. Lacks reconciliation state when commit outcome is unknown.
6. Lacks error-specific backoff, overall deadline, and proper `InterruptedException` handling.
7. If `createReservation` sends emails inside the transaction callback, it can send them multiple times.

Write accurate **pseudocode** with **two separate retry loops**, rather than merely replacing `UUID.randomUUID()` with a fixed ID.

### Exercise 3 — Designing Spring `@Transactional`

Build:

- `ReservationWriter` with `@Transactional` managing one reservation insert and inventory decrement.
- `ReservationCoordinator` taking an idempotency key and deciding whether to return existing result, retry transient failure, or return pending confirmation.
- `MongoTransactionManager` bound to the right `MongoDatabaseFactory`.
- Unique index on `tenantId + reservationId`.
- A `ReservationConfirmed` outbox event written **in the same transaction**.

Explain:

1. Why catching commit errors inside `ReservationWriter`'s method body is insufficient.
2. Why slapping `@Retryable` arbitrarily outside `@Transactional` risks replaying the body on unknown commit.
3. If protocol-level commit retry is required, what keeps the **same `ClientSession`**?
4. If the process crashes after sending commit without an ACK, where does the coordinator get reconciliation data?

### Exercise 4 — Fault-Injection Testing

On a dedicated test replica set:

1. Seed 2 wallets or 5 available seats.
2. Test transaction success and verify totals/invariants.
3. Inject a real TTE inside the body; verify the body can re-run and only one record commits.
4. Inject UTCR **right at commit**; count commit retries and verify the body does not re-run just for UTCR.
5. Intentionally keep commit outcome unresolved past retry budget; assert the app does not report definite failure.
6. Test HTTP retries with the same operation ID and with a new operation ID to demonstrate why idempotency matters.
7. Enable an idempotent outbox dispatcher and verify events never cause duplicate business effects.

**Never run failpoints or simulate elections on production**; use an isolated environment with proper permissions, guaranteed failpoint cleanup, and timing/trace measurements.

### Exercise 5 — Production Incident

One night, metrics show:

```text
transaction_body_retries_total     slight increase
transaction_commit_retries_total   sharp spike
transaction_commit_unknown_total   sharp spike
duplicate_operation_key_total      climbs a few minutes later
```

Prioritized diagnostics:

- Inspect network/commit latency, write concern, elections, and driver/server logs.
- Check whether clients/gateways started retrying whole HTTP requests after timeouts.
- Check whether all requests reuse the **same `operationId`** across retries.
- Check whether reconciliation has a growing `PENDING_CONFIRMATION` backlog.
- Never increase **whole-transaction retry** counts just to suppress commit exceptions.

## 23. References

- MongoDB Manual — [Transactions](https://www.mongodb.com/docs/manual/core/transactions/): scope and prerequisites for multi-document transactions.
- MongoDB Manual — [Transactions and Applications](https://www.mongodb.com/docs/manual/core/transactions-in-applications/): rules for transaction and commit retries in applications.
- MongoDB Manual — [Transactions and Sessions](https://www.mongodb.com/docs/manual/core/transactions/): session/transaction identity, write concerns, and limitations.
- MongoDB Manual — [Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/): distinguishing retryable single writes from transactions.
- MongoDB Java Driver — [Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/): `ClientSession`, `withTransaction`, transaction options, and error handling.
- MongoDB Java Driver — [ClientSession API](https://mongodb.github.io/mongo-java-driver/5.6/apidocs/mongodb-driver-sync/com/mongodb/client/ClientSession.html): session methods/transaction callback; check your project's driver version.
- Spring Data MongoDB — [Client Session & Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html): `MongoTransactionManager`, sessions, and transaction integration.
- Spring Data MongoDB — [MongoTransactionManager API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/MongoTransactionManager.html): how Spring manages sessions/commits.
- Spring Framework — [Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction proxies, `@Transactional`, and `TransactionTemplate`.

## Key Takeaways

**Errors inside the transactional body labeled `TransientTransactionError` usually call for retrying the entire transaction in a fresh attempt. Errors on `commitTransaction` labeled `UnknownTransactionCommitResult` mean the client does not know whether commit succeeded or failed, so you must retry commit alone on the old transaction without re-executing the business body.** When commit cannot be confirmed before the deadline, return an unresolved state and reconcile via operation ID. `ClientSession.withTransaction` handles retries per driver semantics; `@Transactional`/`TransactionTemplate` must not be assumed equivalent to a complete retry policy. For end-to-end safety from database to HTTP, combine stable idempotency keys, unique constraints, outboxes for side effects, bounded retries, real replica-set testing, and separate monitoring for **body retries** vs **commit retries**.
