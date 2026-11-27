# TransientTransactionError, UnknownTransactionCommitResult, and Error Handling in MongoDB Transactions

## 1. Why Must Transactions Have an Error-Handling Strategy?

MongoDB supports **multi-document transactions** to group multiple read/write operations into a single transactional unit. When a transaction commits successfully, its changes take effect as a group; when it aborts, the transaction's uncommitted changes are discarded.

However, a transaction running on a replica set or sharded cluster does not only have two simple states: **success** and **definite failure**. During execution, several events can occur:

- Another transaction updates a document, causing a **write conflict**.
- The primary **steps down** or a new primary election occurs.
- The network between the application and MongoDB is interrupted.
- An operation times out or fails to acquire a lock.
- **`commitTransaction`** is sent, but the connection drops before the response returns.
- The transaction exceeds server lifetime, cache, or resource limits.

The hardest part is not merely catching an exception, but **knowing which step is safe to retry**.

MongoDB uses **error labels** to help applications decide:

| Error Label | Core Interpretation | Handling Approach |
|---|---|---|
| **TransientTransactionError** | The transaction hit a transient error and needs a new transaction attempt. | **Retry the entire transaction body** from scratch in a new transaction. |
| **UnknownTransactionCommitResult** | The outcome of the **commit** is unknown to the client. | **Retry `commitTransaction` itself**; do not immediately re-run the body. |
| Neither label present | Could be validation, duplicate key, authorization, resource limit, or non-retryable error. | Classify the error, report failure, or recover per specific rules; **no blind retry**. |

These two labels **are not separate exception classes**. A **`MongoException`** may carry one or more labels attached by the server or driver depending on the situation.

**Quick rule of thumb:**

~~~text
Error while executing the transaction
    |
    +-- TransientTransactionError
    |      -> ABORT / end old transaction
    |      -> START new transaction
    |      -> re-run ENTIRE body
    |
    +-- Permanent / non-retryable error
           -> stop, report appropriate error

Error during COMMIT
    |
    +-- UnknownTransactionCommitResult
    |      -> preserve transaction/session context
    |      -> retry COMMIT
    |      -> DO NOT re-run body immediately
    |
    +-- Other outcome
           -> classify based on actual details
~~~

### Lesson Objectives

After this lesson, you will be able to:

1. Distinguish **pre-commit errors** from **unknown commit results**.
2. Understand both error labels and the difference between **transaction retry** and **commit retry**.
3. Build a retry policy with time budgets, backoff, logging, and business idempotency.
4. Use **Java Sync Driver `withTransaction`** or the Core API appropriately.
5. Design error handling with **Spring Data MongoDB / `MongoTransactionManager`**.
6. Separate **unknown outcomes**, data errors, and system errors.
7. Test failovers, transaction conflicts, timeouts, and side effects outside MongoDB.

## 2. Lifecycle of a MongoDB Transaction

A transaction uses a **`ClientSession`** and goes through these phases:

~~~text
MongoClient
    |
    v
startSession()
    |
    v
startTransaction(options)
    |
    +--> Read / Write A
    |
    +--> Read / Write B
    |
    +--> Read / Write C
    |
    v
commitTransaction()
    |
    +--> Commit confirmed -> SUCCESS
    |
    +--> Commit outcome unknown -> UNKNOWN
    |
    +--> Transaction cannot continue -> ERROR/ABORT
~~~

If an operation inside the transaction hits an error preventing continuation, the application must end the old transaction and **start a new transaction** when the error is retryable.

If execution has already entered **commit** and receives **`UnknownTransactionCommitResult`**, the client cannot infer from the exception that the transaction failed to commit. Therefore, **never start a new transaction and re-run the body** merely because a success response was not received.

### 2.1. Why Is Retrying One Command Inside the Transaction Not Enough?

Balance transfer example:

~~~text
Transaction T1:
  1. Debit account A 200
  2. Credit account B 200
  3. Record transfer document
  4. Commit
~~~

If step 2 hits **`TransientTransactionError`**, the proper recovery is retrying **the entire transaction** against a fresh snapshot. Re-running step 2 alone inside the old transaction does not guarantee the transaction remains valid; running step 2 outside the transaction breaks atomicity.

### 2.2. Why Is Retrying Commit Safer Than Retrying the Body When Commit Is Unknown?

Suppose the entire body finished and the server may have already committed:

~~~text
Client                        MongoDB
  |                              |
  |---- commitTransaction ------>|
  |                              | COMMIT succeeded?
  |         X connection lost    |
  |<------ no reply received ----|
  |
  | Cannot know outcome for sure
~~~

If the client re-runs the body as a new transaction, a business operation can execute a second time. Resending **commit for the same transaction/session** is the proper handling for **`UnknownTransactionCommitResult`**.

## 3. Preparing Practice Data

Use a dedicated database in **`mongosh`**; never run labs on production data:

~~~javascript
use mongo_transaction_error_lab

db.accounts.insertMany([
  {
    _id: "ACC-A",
    ownerId: "USER-A",
    balanceCents: NumberLong(100000),
    version: NumberLong(1)
  },
  {
    _id: "ACC-B",
    ownerId: "USER-B",
    balanceCents: NumberLong(50000),
    version: NumberLong(1)
  }
]);

db.transfers.createIndex(
  { requestId: 1 },
  {
    unique: true,
    name: "uq_transfer_request_id"
  }
);
~~~

The **`insertMany`** command runs once on a fresh collection; re-running with the same `_id` triggers a duplicate key error. Independent error-handling examples typically assume the initial state:

| Account | `balanceCents` |
|---|---:|
| ACC-A | 100000 |
| ACC-B | 50000 |

The business operation transfers **20000 cents** from ACC-A to ACC-B while writing a transfer document:

~~~javascript
{
  _id: "TX-001",
  requestId: "REQ-001",
  fromAccount: "ACC-A",
  toAccount: "ACC-B",
  amountCents: NumberLong(20000),
  status: "COMPLETED"
}
~~~

After one transfer commits exactly once, the expected balances are:

~~~text
ACC-A = 80000
ACC-B = 70000
Total = 150000
~~~

**Total balance** is the example's invariant, though real monetary systems also account for fees, ledger accounting, reserved funds, authorization, transfer limits, and external integrations. This lesson focuses strictly on **transaction error handling**.

### 3.1. Configuring Session and Transaction

~~~javascript
const session = db.getMongo().startSession();

session.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" },
  readPreference: { mode: "primary" }
});
~~~

A transaction commonly uses:

- **`readConcern` `snapshot`** when a consistent multi-document view is needed.
- **`writeConcern` `majority`** when commits require majority durability.
- **`readPreference` `primary`** because transactional writes route through the primary.

These options do not automatically enable retry policies in the **Core API**. Applications must choose the **callback/convenient API** or implement explicit error handling.

## 4. Error Labels: Never Classify Solely by Message Text

MongoDB produces many error types: server errors, network errors, conflicts, resource exhaustion, timeouts, constraint violations, etc. Exceptions can carry an **error code**, **message**, and **`errorLabels`**.

Illustrative example:

~~~javascript
{
  code: 112,
  codeName: "WriteConflict",
  errmsg: "WriteConflict ...",
  errorLabels: [
    "TransientTransactionError"
  ]
}
~~~

This is an illustration; **never assume every error code 112, every driver, or every scenario has this exact structure**.

### 4.1. Why Inspect Labels?

An error code like **`NetworkTimeout`** can occur in multiple places:

- Before the transaction body executes.
- During a transaction operation.
- While committing the transaction.
- After the server applied the commit, before the client read the response.

**Error location determines handling.** Catching any exception named network timeout and retrying the entire transaction risks double execution.

### 4.2. Error Labels in Java

The MongoDB Java Driver provides:

~~~java
if (exception.hasErrorLabel("TransientTransactionError")) {
    // Retry the entire transaction if in the body phase.
}

if (exception.hasErrorLabel("UnknownTransactionCommitResult")) {
    // Retry commit of the same transaction.
}
~~~

This is a method on **`MongoException`**, not on every Java exception. If a framework wraps the exception, unwrap the cause/driver exception safely.

### 4.3. Error Labels in `mongosh`

Depending on the error object structure, you can inspect:

~~~javascript
try {
  // MongoDB operations ...
} catch (error) {
  printjson({
    name: error.name,
    message: error.message,
    code: error.code,
    labels: error.errorLabels
  });
}
~~~

In applications, prefer the driver's label-checking method; never parse message strings with regex to decide on retries.

### 4.4. Errors May Carry No Retryable Label

Errors such as schema validation, duplicate key, or unauthorized must be classified properly. Never write:

~~~text
catch ANY_EXCEPTION:
    retryTransactionForever()
~~~

Retrying the wrong error category adds heavy load, masks business errors, and can repeat dangerous operations.

## 5. `TransientTransactionError`: Retry the Entire Transaction

### 5.1. Meaning

The **`TransientTransactionError`** label indicates the transaction hit a transient failure where **starting a new transaction and re-running the entire body may succeed**.

Common triggers:

- **Write conflicts** between concurrent transactions/operations on the same document.
- **Primary stepdown** or election affecting an operation inside the transaction.
- Certain **network errors** while the transaction is executing.
- Other transient errors labeled by the server/driver in context.

**Not all write conflicts or timeouts are handled identically in every situation.** Decisions rely on the error label and transaction phase.

### 5.2. Timeline of Two Competing Transactions

~~~text
Tx A                           Tx B
  |                              |
  |-- READ account ACC-A -------|
  |                              |
  |-- UPDATE ACC-A               |-- UPDATE ACC-A
  |                              |
  |  Write conflict / abort <----+
  |
  v
MongoException
label=TransientTransactionError
  |
  v
Abort/end attempt T1
Start attempt T2 with fresh snapshot
Run ALL operations again
~~~

If the retried transaction succeeds, it runs against newer state; business preconditions (such as sufficient balance) **must be re-checked** rather than reusing results from the prior attempt.

### 5.3. Never Retry Only the Failed Operation

Wrong:

~~~text
Begin transaction
  debit account A
  credit account B -> TransientTransactionError
  retry only credit B
  insert transfer
Commit
~~~

Right:

~~~text
Begin transaction attempt 1
  debit account A
  credit account B -> TransientTransactionError
Abort attempt 1

Begin transaction attempt 2
  re-check balance
  debit account A
  credit account B
  insert transfer
Commit
~~~

A transient error does not guarantee the second attempt will succeed, so **enforce a retry budget**.

### 5.4. The Body Can Execute Multiple Times

The driver's callback API can re-invoke the entire callback on TTE. Everything inside the callback must therefore be **safe to re-execute**:

~~~text
transaction callback:
  read MongoDB
  update MongoDB
  insert MongoDB
  return result
~~~

Avoid placing non-transactional side effects directly inside the callback:

~~~text
transaction callback:
  call payment provider to charge card   <-- dangerous
  send confirmation email                <-- dangerous
  publish Kafka message                  <-- dangerous
  update MongoDB
~~~

The callback may execute repeatedly. MongoDB only rolls back writes inside the MongoDB transaction; it **does not automatically recall** emails, charges, or published messages.

### 5.5. Should You Abort the Old Attempt?

With the **Core API**, when an error occurs inside the body:

- If the transaction is still active, **abort** it or use driver mechanics to close the old attempt.
- Start a new transaction for the retry.
- Log any abort error if needed without letting it obscure the root cause.
- Never proceed to commit a body that already threw an error.

The Callback API handles abort/retry appropriately; avoid wrapping an extra outer retry loop around **`withTransaction`** without accounting for internal callback retries.

## 6. `UnknownTransactionCommitResult`: Unknown Whether Commit Succeeded

### 6.1. Meaning

The **`UnknownTransactionCommitResult`** label signals that the client **cannot determine the outcome of the commit** from the received response.

It **neither means the commit failed** nor **guarantees the commit definitely succeeded**.

~~~text
                 commitTransaction()
                          |
                +---------+---------+
                |                   |
                v                   v
        Server committed     Server did not commit /
        response was lost    result uncertain
                |                   |
                +---------+---------+
                          |
            Client cannot distinguish
            from available response
                          |
                          v
             UnknownTransactionCommitResult
~~~

### 6.2. Causes of an Unknown Result

- Connection dropped after sending commit.
- Primary changed while the client awaited commit.
- Client timed out before learning the actual outcome.
- Commit/write concern not confirmed within the relevant window.
- Other cases labeled by the driver/server.

Never assume a network error or timeout during commit means the commit rolled back.

### 6.3. Why Retry Only Commit?

For the same session and transaction identity, **`commitTransaction`** is designed to be retryable. The server and driver use the transaction identity to handle repeated commit attempts properly rather than starting a brand-new business operation.

**Wrong:**

~~~text
1. Body transfer A -> B ran.
2. commitTransaction -> UnknownTransactionCommitResult.
3. Start new transaction.
4. Debit A and credit B again.
~~~

If the first commit actually succeeded, this risks transferring money twice.

**Right:**

~~~text
1. Body transfer A -> B ran.
2. commitTransaction -> UnknownTransactionCommitResult.
3. Retry commitTransaction of the same session/transaction.
4. Report success only once commit outcome is confirmed.
5. If budget exhausts while still unknown, keep state IN_DOUBT
   and reconcile; do not declare failed or run a new body.
~~~

### 6.4. Do Not Use Abort to “Ensure Rollback” When Commit Is Unknown

Once a commit may have succeeded, **`abortTransaction` is not a commit undo operation**. When the outcome is unknown, calling abort does not prove changes were reverted.

Never return “transaction definitely did not run” just because the client called abort after an unknown commit result.

### 6.5. Commit Retry Differs from `retryWrites=true`

MongoDB documentation notes that **`commitTransaction` is a retryable write**, and drivers can retry commit **even when `retryWrites` is disabled**, depending on API/driver. This differs from write operations **inside** a transaction, which are not individually retried like standalone retryable writes.

The Callback API implements UCTR handling. The Core API requires the application to implement retry loops per error labels beyond finite driver-level commit retries.

### 6.6. What If Retries Expire?

A real-world system must cap retries so API calls do not block forever:

1. Assign a fixed **`requestId` / business operation ID**.
2. Retry **commit** within an allowed time window.
3. If still unknown, return **`PENDING` / `UNKNOWN`** rather than a definite failure.
4. Reconcile transaction state via the unique business/ledger record once majority-committed state can be read.
5. Define recovery workflows and notify users once the outcome is confirmed.

If a business operation needs an exactly-once effect, design **idempotency** alongside commit retries rather than relying solely on commit retries.

## 7. Error-Handling Decision Flowchart

~~~text
START TRANSACTION
       |
       v
RUN BODY
       |
       +-- Success -------------> COMMIT
       |                            |
       |                            +-- SUCCESS -> DONE
       |                            |
       |                            +-- UCTR
       |                            |    |
       |                            |    v
       |                            |  RETRY SAME COMMIT
       |                            |    |
       |                            |    +-- SUCCESS -> DONE
       |                            |    |
       |                            |    +-- DEADLINE -> IN_DOUBT
       |                            |
       |                            +-- Other error
       |                                 -> handle by category
       |
       +-- TransientTransactionError
       |         |
       |         v
       |    ABORT OLD ATTEMPT
       |         |
       |         v
       |    RETRY BUDGET?
       |         |
       |         +-- YES -> START NEW TRANSACTION -> RUN BODY
       |         |
       |         +-- NO -> RETRY_EXHAUSTED
       |
       +-- Non-retryable error
                 |
                 v
              ABORT / FAIL
~~~

This diagram shows the core rules. Certain **commit** errors have specific semantics and labels; consult the documentation for your exact driver/version. Never assume every commit exception means “retry the whole transaction”.

## 8. Detailed Classification Table by Phase

| Phase | Signal | Practical Meaning | Action |
|---|---|---|---|
| Body operation | **TransientTransactionError** | Current attempt cannot continue safely; error may be transient. | Abort/end attempt, retry **whole body** in a new transaction. |
| Body operation | **DuplicateKey** | Unique constraint violated or duplicate request. | Do not retry blindly; check data / idempotency. |
| Body operation | **Validation / Unauthorized** | Schema or permission violation. | Abort; return business or configuration error. |
| Body operation | **TransactionTooLargeForCache** | Transaction exceeds cache capacity. | Shrink scope / redesign; do not expect identical retries to succeed. |
| Commit | **UnknownTransactionCommitResult** | Unknown whether server committed. | Retry **same commit**; if unconfirmed, keep unknown and reconcile. |
| Commit | Commit confirmed | Transaction succeeded under configured write concern. | Return success; dispatch post-commit side effects safely. |
| Commit | Error not covered by general rule | Inspect labels, error codes, and driver semantics. | Classify explicitly; never guess failed/success. |
| Any | Timeout/cancel before sending | May not have executed, yet phase must be verified. | Do not apply the same retry policy to every timeout. |

**A single error code does not replace error labels**, and **phase** is essential context when implementing transaction error handling.

## 9. Core API Pattern in `mongosh`: Phase-Accurate Retries

The following example demonstrates a transfer between two documents **within the same MongoDB deployment**. It uses two distinct retry loops:

- Outer loop: retries the **whole transaction** when the body hits TTE.
- Inner loop: retries **commit of the same transaction** when commit hits UCTR.

This is an illustrative lab; real financial systems require proper ledgers, authorization, deadline-based retry limits, idempotency, reconciliation, and auditing.

### 9.1. Label Helper Function

~~~javascript
function hasLabel(error, label) {
  return Boolean(
    error &&
    Array.isArray(error.errorLabels) &&
    error.errorLabels.includes(label)
  );
}
~~~

In the Java Driver, use **`MongoException.hasErrorLabel()`**; in `mongosh`, the helper above inspects `errorLabels` for illustration.

### 9.2. Transaction Pattern with Bounded Retries

~~~javascript
function transferWithRetry({
  requestId,
  fromId,
  toId,
  amountCents,
  maxBodyAttempts = 4,
  maxCommitAttempts = 5
}) {
  if (!requestId || fromId === toId) {
    throw new Error("Invalid transfer identity");
  }

  if (!Number.isSafeInteger(amountCents) || amountCents <= 0) {
    throw new Error("amountCents must be a positive safe integer");
  }

  const session = db.getMongo().startSession();
  const txDb = session.getDatabase("mongo_transaction_error_lab");
  const accounts = txDb.accounts;
  const transfers = txDb.transfers;

  try {
    for (
      let bodyAttempt = 1;
      bodyAttempt <= maxBodyAttempts;
      bodyAttempt++
    ) {
      session.startTransaction({
        readConcern: { level: "snapshot" },
        writeConcern: { w: "majority" },
        readPreference: { mode: "primary" }
      });

      try {
        const debit = accounts.updateOne(
          {
            _id: fromId,
            balanceCents: { $gte: amountCents }
          },
          {
            $inc: { balanceCents: -amountCents }
          }
        );

        if (debit.matchedCount !== 1) {
          throw new Error("INSUFFICIENT_FUNDS_OR_SOURCE_MISSING");
        }

        const credit = accounts.updateOne(
          { _id: toId },
          {
            $inc: { balanceCents: amountCents }
          }
        );

        if (credit.matchedCount !== 1) {
          throw new Error("DESTINATION_MISSING");
        }

        transfers.insertOne({
          _id: "TX-" + requestId,
          requestId,
          fromAccount: fromId,
          toAccount: toId,
          amountCents: NumberLong(amountCents),
          status: "COMPLETED"
        });
      } catch (error) {
        // Abort only when the body failed before entering commit.
        try {
          session.abortTransaction();
        } catch (abortError) {
          // Log abortError; preserve body error as primary cause.
        }

        if (
          hasLabel(error, "TransientTransactionError") &&
          bodyAttempt < maxBodyAttempts
        ) {
          print("Transient body failure; restart transaction");
          continue;
        }

        throw error;
      }

      // Body completed. Never re-run body solely for unknown commit.
      for (
        let commitAttempt = 1;
        commitAttempt <= maxCommitAttempts;
        commitAttempt++
      ) {
        try {
          session.commitTransaction();

          return {
            status: "COMMITTED",
            requestId
          };
        } catch (error) {
          if (hasLabel(error, "UnknownTransactionCommitResult")) {
            if (commitAttempt < maxCommitAttempts) {
              print("Unknown commit result; retry same commit");
              continue;
            }

            // Never conclude the transaction aborted.
            return {
              status: "IN_DOUBT",
              requestId,
              message: "Commit outcome needs reconciliation"
            };
          }

          throw error;
        }
      }
    }
  } finally {
    session.endSession();
  }
}
~~~

Invoke once on the sample dataset:

~~~javascript
transferWithRetry({
  requestId: "REQ-001",
  fromId: "ACC-A",
  toId: "ACC-B",
  amountCents: 20000
});
~~~

### 9.3. Limitations of the Sample Above

The example intentionally focuses on **TTE/UCTR branching**, not a production financial solution:

1. Loops cap attempt counts, yet **lack a global deadline and backoff**.
2. A **`DuplicateKey`** when reusing `requestId` does not automatically become success; inspect the committed transfer document and compare payloads.
3. If commit throws an error **other than UCTR**, the code surfaces it to the caller for classification rather than assuming every commit error means abort.
4. If `status` = **`IN_DOUBT`**, the caller **must not issue a new transfer**; it must reconcile.
5. Balance arithmetic uses `NumberLong` in the database and small numeric literals in the lab; production requires strict numeric domain bounds, overflow checks, validation, and consistent schemas.
6. If the session closes while commit remains unknown, you cannot simply retry commit on a new session; use business reconciliation by `requestId`.
7. No emails, card charges, or broker messages appear in the body since the body can re-run.
8. Secondary abort errors must never mask the primary error that broke the body.

### 9.4. Never Retry Forever in `mongosh`

Reference docs sometimes show **`while(true)`** loops to illustrate the algorithm. In production, enforce:

- **Request or operation deadlines**.
- Maximum retry counts / budgets.
- **Jittered backoff** on transient retries per policy.
- Cancellation and shutdown handling.
- Per-phase metrics.
- **`IN_DOUBT`** state so clients do not wait indefinitely.

## 10. Java Sync Driver: Callback API or Core API?

The MongoDB Java Sync Driver offers two ways to control transactions:

| Style | APIs | TTE / UCTR Retries |
|---|---|---|
| **Callback / Convenient API** | **`ClientSession.withTransaction(...)`** | Driver integrates full-transaction retries on TTE and commit retries on UCTR per driver policy. |
| **Core API** | **`startTransaction`, `commitTransaction`, `abortTransaction`** | Application builds phase/label-specific retry loops beyond driver-level commit retries. |

To avoid implementation bugs, **`withTransaction`** should generally be the default when your logic fits. Choose the Core API when you need fine-grained control over state machines, retry schedules, telemetry, or custom unknown-outcome handling.

### 10.1. Java: Basic `withTransaction`

~~~java
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
import org.bson.Document;

public final class TransferService {
    private final MongoClient client;

    public TransferService(MongoClient client) {
        this.client = client;
    }

    public void transfer(
            String requestId,
            String fromId,
            String toId,
            long amountCents) {

        if (requestId == null || requestId.isBlank()) {
            throw new IllegalArgumentException("Missing requestId");
        }
        if (fromId.equals(toId) || amountCents <= 0) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        MongoDatabase database = client.getDatabase(
                "mongo_transaction_error_lab"
        );

        MongoCollection<Document> accounts =
                database.getCollection("accounts");

        MongoCollection<Document> transfers =
                database.getCollection("transfers");

        TransactionOptions options = TransactionOptions.builder()
                .readConcern(ReadConcern.SNAPSHOT)
                .writeConcern(WriteConcern.MAJORITY)
                .readPreference(ReadPreference.primary())
                .build();

        try (ClientSession session = client.startSession()) {
            session.withTransaction(() -> {
                UpdateResult debit = accounts.updateOne(
                        session,
                        Filters.and(
                                Filters.eq("_id", fromId),
                                Filters.gte("balanceCents", amountCents)
                        ),
                        Updates.inc("balanceCents", -amountCents)
                );

                if (debit.getMatchedCount() != 1) {
                    throw new IllegalStateException(
                            "Insufficient funds or source missing"
                    );
                }

                UpdateResult credit = accounts.updateOne(
                        session,
                        Filters.eq("_id", toId),
                        Updates.inc("balanceCents", amountCents)
                );

                if (credit.getMatchedCount() != 1) {
                    throw new IllegalStateException(
                            "Destination account missing"
                    );
                }

                transfers.insertOne(
                        session,
                        new Document("_id", "TX-" + requestId)
                                .append("requestId", requestId)
                                .append("fromAccount", fromId)
                                .append("toAccount", toId)
                                .append("amountCents", amountCents)
                                .append("status", "COMPLETED")
                );

                return null;
            }, options);
        }
    }
}
~~~

**Step-by-step explanation:**

1. Build **`TransactionOptions`** with snapshot read, majority write, and primary read preference.
2. Create **`ClientSession`** from the same `MongoClient`.
3. Invoke **`withTransaction(callback, options)`**.
4. Pass the same **`session`** to every **`updateOne`/`insertOne`** inside the body.
5. If an operation throws with TTE, the callback API retries the **whole transaction**.
6. If commit receives UCTR, the callback API retries **commit**, without re-running the body just because commit is unknown.
7. If the body throws a business exception like insufficient funds, it is not a `MongoException` with TTE and will not be retried pointlessly.

**Important:** this method alone does not distinguish a previously processed `requestId` from a new request; **`DuplicateKey`** on the transfer ID requires service/API-level reconciliation. A unique ID in code alone does not produce a complete exactly-once API.

### 10.2. Common Mistakes with `withTransaction`

**Omitting `session` on an operation:**

~~~java
session.withTransaction(() -> {
    accounts.updateOne(
            Filters.eq("_id", "ACC-A"),
            Updates.inc("balanceCents", -20000L)
    ); // Missing session!
    return null;
}, options);
~~~

The call above **does not automatically join the transaction** just because it runs inside the callback; the Java Driver requires the overload taking **`ClientSession`**. The operation writes outside the transaction and will not roll back with the body.

**Wrapping an outer retry loop around a callback that already retries:**

~~~text
for each retry:
    session.withTransaction(callback)
~~~

Without an explicit purpose, this multiplies retry budgets unexpectedly. Understand the driver's built-in policy and avoid stacking uncontrolled nested retry loops.

**Doing work outside MongoDB inside the callback:**

~~~java
session.withTransaction(() -> {
    paymentGateway.charge(...);  // Side effect outside transaction.
    accounts.updateOne(session, ...);
    return null;
});
~~~

The callback may re-run and charge again. Move external side effects to a post-commit idempotent workflow or a **transactional outbox**.

### 10.3. Java Core API: Phase-Accurate Retry Skeleton

When manual control is needed, you can structure a state machine:

~~~java
// PSEUDOCODE: illustrates the algorithm, not a complete Java class.
for (int bodyAttempt = 0; bodyAttempt < maxBodyAttempts; bodyAttempt++) {
    session.startTransaction(transactionOptions);

    try {
        executeEntireBusinessBody(session);
    } catch (MongoException e) {
        safeAbort(session);

        if (e.hasErrorLabel("TransientTransactionError")
                && retryBudgetLeft()) {
            backoff();
            continue; // NEW transaction; re-run body.
        }

        throw e;
    } catch (RuntimeException e) {
        safeAbort(session);
        throw e; // E.g. non-retryable business error.
    }

    // Body succeeded.
    while (true) {
        try {
            session.commitTransaction();
            return; // SUCCESS
        } catch (MongoException e) {
            if (e.hasErrorLabel("UnknownTransactionCommitResult")) {
                if (commitRetryBudgetLeft()) {
                    backoff();
                    continue; // ONLY retry commit.
                }

                throw new CommitOutcomeUnknownException(e);
            }

            throw e; // Classify per error semantics.
        }
    }
}

throw new RetryBudgetExceededException();
~~~

Helper methods **`safeAbort`**, **`retryBudgetLeft`**, **`backoff`**, and custom exceptions in this pseudocode are application responsibilities, **not built-in driver APIs**. The goal is showing exact retry placement.

In the real Core API, **`commitTransaction` may already undergo internal driver-level retries**; applications must still inspect error labels on exceptions surfaced by the driver. State-machine correctness matters more than raw network attempt counts.

### 10.4. Java: Identifying Error Labels

~~~java
import com.mongodb.MongoException;

public final class TransactionErrorClassifier {
    public static boolean isTransient(MongoException error) {
        return error.hasErrorLabel("TransientTransactionError");
    }

    public static boolean isUnknownCommit(MongoException error) {
        return error.hasErrorLabel("UnknownTransactionCommitResult");
    }
}
~~~

Never write logic matching **`message.contains("WriteConflict")`**, because messages change across versions/locales and omit full context.

### 10.5. One Session Is Not for Parallel Operations

The MongoDB Java Driver does not support running parallel operations inside **the same transaction**. Never share one **`ClientSession`** across multiple threads executing commands concurrently.

Sharing one `MongoClient` across the application is normal; logical sessions must be scoped cleanly per request/workflow.

## 11. Spring Data MongoDB: `@Transactional` and `MongoTransactionManager`

Spring Data MongoDB supports transactions via **`MongoTransactionManager`** and **`@Transactional`**, or programmatic APIs like **`TransactionTemplate`**.

Crucial point: **Spring `@Transactional` is not automatically identical to the Java Driver `withTransaction` retry policy**. Spring manages the transaction boundary, while error labels and retry behavior must be properly configured and implemented.

### 11.1. Configuring `TransactionManager`

~~~java
import com.mongodb.ReadConcern;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration
public class MongoTransactionConfig {
    @Bean
    MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory databaseFactory) {

        TransactionOptions options = TransactionOptions.builder()
                .readConcern(ReadConcern.SNAPSHOT)
                .writeConcern(WriteConcern.MAJORITY)
                .build();

        return new MongoTransactionManager(databaseFactory, options);
    }
}
~~~

With Spring Data MongoDB, transaction support must be properly enabled/configured; never assume every `MongoTemplate` call is automatically transactional just because MongoDB is present.

### 11.2. Service with `@Transactional`

~~~java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class SpringTransferService {
    private final MongoTemplate mongoTemplate;

    public SpringTransferService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    @Transactional
    public void transfer(
            String requestId,
            String fromId,
            String toId,
            long amountCents) {

        if (amountCents <= 0 || fromId.equals(toId)) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        var debit = mongoTemplate.updateFirst(
                Query.query(
                        Criteria.where("_id").is(fromId)
                                .and("balanceCents").gte(amountCents)
                ),
                new Update().inc("balanceCents", -amountCents),
                "accounts"
        );

        if (debit.getMatchedCount() != 1) {
            throw new IllegalStateException(
                    "Insufficient funds or source missing"
            );
        }

        var credit = mongoTemplate.updateFirst(
                Query.query(Criteria.where("_id").is(toId)),
                new Update().inc("balanceCents", amountCents),
                "accounts"
        );

        if (credit.getMatchedCount() != 1) {
            throw new IllegalStateException(
                    "Destination missing"
            );
        }

        mongoTemplate.insert(
                new org.bson.Document("_id", "TX-" + requestId)
                        .append("requestId", requestId)
                        .append("amountCents", amountCents)
                        .append("status", "COMPLETED"),
                "transfers"
        );
    }
}
~~~

**Notes:**

- **`@Transactional`** coordinates the MongoDB session/transaction once an appropriate transaction manager is registered.
- If an operation throws an exception and Spring triggers rollback, MongoDB writes inside the transaction abort accordingly.
- **Never place non-DB side effects inside a transactional method** expecting Spring to roll them back too.
- **Self-invocation** of a `@Transactional` method via **`this.method()`** bypasses Spring proxies under standard proxy AOP configurations.
- The method above is a simplified accounting illustration without complete reconciliation/idempotency.

### 11.3. Spring Retry for `TransientTransactionError`

Spring Data documentation recommends **Spring Retry** when an application needs to retry transient transaction errors.

However, **retry placement** is critical:

~~~text
Retry aspect / service layer
      |
      +--> Transaction attempt 1
      |       begin -> body -> error/rollback
      |
      +--> Transaction attempt 2
              begin -> body -> commit
~~~

To retry an entire transaction, each attempt needs **a fresh transaction boundary**, rather than re-calling a DAO method inside **the same aborted transaction**.

In proxy-based Spring AOP, interceptor ordering between the **Retry interceptor** and **Transaction interceptor** determines whether each retry opens a fresh transaction. Never simply place **`@Retryable`** and **`@Transactional`** side by side assuming their order and behavior are automatically right.

### 11.4. On `UnknownTransactionCommitResult`, Do Not Retry the Whole Service

A common mistake:

~~~text
@Retryable(for = MongoException.class)
@Transactional
public void transfer(...) { ... }
~~~

If the error occurs at **commit** and carries **`UnknownTransactionCommitResult`**, retrying the entire method can re-execute an already-committed business action.

Therefore:

- Separate **pre-commit TTE retries** from **unknown commit retries**.
- Never attach a blanket retry configuration for every `MongoException`.
- When using Spring's transaction manager, inspect customizing/retrying **`doCommit`** per Spring Data documentation instead of replaying the business method on unknown commit.
- If still unknown after budget exhaustion, preserve the business `requestId` for reconciliation rather than assuming definite rollback.

### 11.5. Spring Data `MongoTransactionManager` and `doCommit`

Spring Data documentation notes you can override **`MongoTransactionManager#doCommit(MongoTransactionObject)`** to implement commit retries per MongoDB guidelines.

This is an **extension point for commit retries**, not a place to re-run business logic. When extending it, make sure you understand:

1. Spring Data version and visibility of the transaction object.
2. Propagation and rollback rules of `PlatformTransactionManager`.
3. The MongoDB `ClientSession` context of the committing transaction.
4. Handling unknown state once retry budget expires.
5. Telemetry and integration tests for failovers and network faults.

Never rewrite commit logic casually without testing against your real driver/server versions.

### 11.6. `TransactionTemplate` and `TransactionalOperator`

Beyond `@Transactional`, Spring supports:

- **`TransactionTemplate`** for imperative Java.
- **`TransactionalOperator`** for Reactive MongoDB.

These APIs manage transaction boundaries, yet **do not turn an unknown commit error into a guaranteed abort**. Reactive code must also ensure the session stays bound to the **Reactor Context** and avoid using sessions/connections outside the transactional stream.

## 12. Retry Policy: Always Enforce a Budget and Deadline

Beyond retrying the right phase, you must bound retries reasonably.

### 12.1. Components to Define

| Component | Role |
|---|---|
| **Max body attempts** | Caps full transaction re-executions. |
| **Max commit attempts** | Caps commit retries on UCTR. |
| **Overall deadline** | Prevents an API request from hanging too long. |
| **Backoff** | Avoids hammering a contended system immediately. |
| **Jitter** | Reduces thundering-herd retries across clients. |
| **Cancellation policy** | Distinguishes client disconnects from unknown commit state. |
| **Idempotency key** | Identifies the same business intent across HTTP requests. |
| **Reconciliation** | Confirms final outcome when the client missed the commit response. |

### 12.2. Illustrative Backoff

~~~text
attempt 1: run immediately
attempt 2: short randomized wait
attempt 3: bounded increased wait
attempt 4: final attempt before deadline
~~~

Do not treat these steps as default MongoDB SLAs. Design policy around **request timeouts**, latency budgets, transaction lifetime, and workload characteristics.

### 12.3. Transaction Lifetime

MongoDB commonly sets **`transactionLifetimeLimitSeconds` to 60 seconds by default**, configurable in supported deployments.

Transactions exceeding this limit expire and abort to protect storage cache/snapshot history. Keep the body **short and tightly scoped**, without slow queries or waiting on user input.

### 12.4. Retry Budgets Can Be Consumed by the Driver

The Callback API has its own internal retries; the Core API may perform driver-level commit retries. When adding service-layer retries, account for **total actual attempts** rather than only counting outer controller loops.

### 12.5. Never Use Retries to Fix Invalid Data

Cases like duplicate keys, schema validation failures, authorization failures, missing destinations, or insufficient funds **cannot become valid merely by repeating the exact same request**.

Retries must target **error label/phase** and **recoverability**, not “keep trying until it works”.

## 13. Specific Error Types to Distinguish

### 13.1. `WriteConflict`

Two transactions may concurrently attempt to update the same document. One must abort when isolation cannot be maintained due to the conflict.

~~~text
Tx A reads account balance
Tx B updates balance and commits
Tx A attempts update based on old snapshot
             |
             v
        WriteConflict
             |
             v
       Abort/retry Tx A
       if TTE label present
~~~

Not every write conflict manifests as the exact same exception across every phase and server version. Inside the transaction body, **rely on error labels** to decide full-body retries.

On a new attempt, **re-read** balances, statuses, versions, and business preconditions; never reuse the prior attempt's snapshot.

### 13.2. `NoSuchTransaction`

The server may return an error indicating the transaction number/state no longer exists in a given context, such as when a transaction aborted or session/transaction lifecycle was misused.

Never handle every **`NoSuchTransaction`** by retrying commit endlessly. Check:

- Did it occur in the **body or commit**?
- Is **`TransientTransactionError`** or **`UnknownTransactionCommitResult`** present?
- Did the transaction already abort, expire, or suffer session misuse?
- Did the driver retry commit and update session state properly?

This error can signal a lifecycle bug rather than just a transient network glitch.

### 13.3. `DuplicateKey`

A unique index violation usually indicates two writes trying to insert or update the same business key.

~~~javascript
db.transfers.createIndex(
  { requestId: 1 },
  { unique: true }
);
~~~

If the application already recorded transfer **REQ-001** and another request reuses that ID, **`DuplicateKey` must not automatically be treated as success**. Read the committed record and compare:

- `fromAccount`;
- `toAccount`;
- `amountCents`;
- `tenantId`/`currency` if applicable;
- business status;
- checksum or request fingerprint.

If the payload differs, it is an **idempotency-key reuse conflict**, not “this request already completed”.

**Version note:** starting in MongoDB **8.1**, an **upsert inside a multi-document transaction** encountering a duplicate key **is no longer automatically retried under updated behavior**. In MongoDB **6.2+**, behavior also changed for `TransactionTooLargeForCache`. Therefore, never apply a static “all retryable errors” list across all server versions.

### 13.4. `TransactionTooLargeForCache`

When a transaction exerts heavy pressure on the WiredTiger cache or cannot fit within server cache constraints, MongoDB can return **`TransactionTooLargeForCache`**.

Starting in MongoDB **6.2**, the server does not retry this error as transient because retrying the exact same data volume will usually fail again.

Remediation:

1. Reduce the number of documents/bytes touched per transaction.
2. Narrow the business unit scope.
3. Avoid reading or pinning unnecessary data inside the transaction.
4. Tune indexes and query plans to minimize scanned data.
5. Split large batches into independent business units where invariants allow.

Never use infinite retry loops to compensate for an oversized transaction design.

### 13.5. Timeouts and Network Errors

Timeouts stem from multiple sources:

- **Client-side deadline** or socket timeout.
- **Server `maxTimeMS`** on an operation.
- **`maxCommitTime`** on transaction commit.
- **`wtimeout`** when write concern is not yet satisfied.
- Transaction lifetime exceeded.

Not all timeouts carry the same label or have the same final outcome.

In particular, a **commit write concern timeout** can happen while the server already completed part or all of the commit work. When the outcome is unknown, avoid reporting “definitely aborted” without proof.

### 13.6. Authentication and Authorization

If the database user lacks read/write permissions on a required collection, authorization errors cannot be fixed by retries. Fix roles, collection names, and tenant policies.

### 13.7. Schema Validation and Business Validation

An error like:

~~~text
Cannot insert transfer because amountCents is negative
~~~

will never become valid if retried 100 times. Validate inputs in the domain service before opening the transaction or at the proper check inside the body; never treat business errors as TTE.

### 13.8. Transaction Already Aborted by a Failed Operation

When an operation fails and aborts the transaction, **do not keep running subsequent business commands as if everything were fine** and then try to commit.

With the Core API, check status, abort as needed, and start a fresh attempt if retryable. The Callback API manages this lifecycle for you.

## 14. Transactional Outbox: Safer Post-Commit Side Effects

A transaction often pairs with an event emission requirement:

~~~text
Transfer committed -> send "TransferCompleted" event
~~~

If you emit the event **before commit**:

~~~text
Send Kafka event
       |
       v
MongoDB transaction aborts
       |
       v
Consumer processed a transaction that never committed!
~~~

If you emit the event **after commit**, the process can crash between committing and publishing:

~~~text
MongoDB commit succeeds
       |
       v
Process crashes
       |
       v
Event never sent
~~~

### 14.1. Outbox Pattern

A common solution:

~~~text
MongoDB transaction:
  UPDATE account A
  UPDATE account B
  INSERT transfer record
  INSERT outbox event

COMMIT
   |
   v
Background dispatcher:
  READ outbox event
  PUBLISH to broker
  MARK dispatched / checkpoint
~~~

Writes inside the MongoDB transaction commit or abort together. The outbox event exists only if the transaction committed.

Example inserting into outbox **within the same transaction**:

~~~javascript
// Inside the transaction body, using the same session.
txDb.outbox.insertOne({
  _id: "EVENT-REQ-001",
  eventType: "TransferCompleted",
  requestId: "REQ-001",
  aggregateId: "TX-REQ-001",
  payload: {
    amountCents: NumberLong(20000)
  },
  dispatched: false
});
~~~

**Every operation must use the same session**. You can add the outbox insert to the Java transaction body shown earlier, e.g., **`outbox.insertOne(session, eventDocument)`**.

### 14.2. Outbox Consumers Still Need Idempotency

A dispatcher can publish successfully and crash before marking the event dispatched. On restart, it may publish the event a second time.

Consumers must deduplicate by **`eventId`** or business key; never assume an outbox provides exactly-once delivery across Kafka, email, and payment systems automatically.

### 14.3. Never Call Payment Providers Inside the Callback

Integrations with payment providers should use **provider idempotency keys** or an appropriate saga/process manager. A MongoDB transaction cannot roll back an external HTTP charge.

## 15. Idempotency Keys: Separating Transaction Retries from Business Request Retries

### 15.1. Two Different Kinds of Retries

**Transaction-level retry:**

~~~text
One HTTP request REQ-001
    |
    +-- Tx attempt 1 -> TTE
    +-- Tx attempt 2 -> COMMIT
~~~

**Application/business-level retry:**

~~~text
HTTP request REQ-001 -> timeout

Later client resends:
HTTP request REQ-001 -> external retry
~~~

Even when drivers handle both error labels cleanly, the system must still distinguish **repeated HTTP requests** from **new business operations**.

### 15.2. Unique Business Key Inside the Transaction

Set a stable **`requestId`** before executing the body:

~~~javascript
{
  _id: "TX-REQ-001",
  requestId: "REQ-001",
  fromAccount: "ACC-A",
  toAccount: "ACC-B",
  amountCents: NumberLong(20000)
}
~~~

And a unique index:

~~~javascript
db.transfers.createIndex(
  { requestId: 1 },
  { unique: true }
);
~~~

When the transaction retries due to TTE, the body re-executes in a new transaction. **Uncommitted writes from the old attempt are rolled back**, so reusing the same business ID keeps identification stable.

If another transaction already committed that `requestId`, a new attempt hits **`DuplicateKey`**. That signals the need to **reconcile** the already-processed request's outcome, not debit again.

### 15.3. Checking Existing Records Is Unsafe Without a Unique Constraint

The pattern:

~~~text
if transfers.findOne({requestId}) == null:
    debit and credit
    insert transfer
~~~

is unsafe if two concurrent requests both read “not found” and proceed. Unique indexes, transactions, and invariants must be designed so races are rejected or handled cleanly.

### 15.4. One `requestId` Must Bind to an Immutable Intent

If REQ-001 originally asked for:

~~~json
{
  "from": "ACC-A",
  "to": "ACC-B",
  "amountCents": 20000
}
~~~

then a later request with:

~~~json
{
  "from": "ACC-A",
  "to": "ACC-C",
  "amountCents": 50000
}
~~~

must not be treated as “the same already-processed request” just because `requestId` matches. Return a conflict for **key reuse with a different payload**.

### 15.5. Never Generate a Fresh `requestId` per Retry

If client or server generates a random ID on each retry:

~~~text
First request: REQ-001
Next retry:    REQ-002
~~~

the unique index cannot recognize that both requests represent the same intent. The business `requestId` must stay invariant across retries.

## 16. Reconciliation When Commit Remains UNKNOWN After the Retry Budget

A serious financial application cannot have only **SUCCESS** and **FAILED**. It often needs:

~~~text
PENDING
   |
   +-- COMMITTED
   |
   +-- NOT_APPLIED / verified FAILED
   |
   +-- IN_DOUBT (requires reconciliation)
~~~

### 16.1. What Happens After UCTR?

When commit becomes unknown and commit retries exhaust the deadline:

1. Never return **“transaction rolled back”**.
2. Never start a new transaction with a new business `requestId`.
3. Log correlation/request IDs and **`unknown`** status in a durable workflow store.
4. Return a response per API contract, such as **202 Accepted** with a status endpoint if supported.
5. Have a worker reconcile once the database recovers.

### 16.2. Checking the Transfer Record

If the transfer record was inserted **in the same transaction as debit/credit**:

~~~javascript
db.transfers.findOne({
  requestId: "REQ-001"
});
~~~

When the document is majority-committed and its payload matches, that is strong evidence **the transfer transaction committed**, because the record lived in the same transaction as the balance updates.

**Never read locally from a lagging secondary** and conclude the record does not exist. Choose proper read concern/routing for reconciliation.

### 16.3. Not Finding the Record Does Not Prove It Never Committed

If a read misses the transfer after the client lost the commit response, it could mean:

- The transaction genuinely did not commit.
- The transaction is still committing or its outcome is not yet visible.
- The read observed an older snapshot or lagging secondary.
- The cluster has not recovered sufficiently for reconciliation.

Thus, absence of the record at one instant **does not justify re-running the operation with a new ID**. Use an outcome verification policy or idempotent replay with **the same `requestId`** and unique constraint.

### 16.4. Never Use a Compensating Transaction While Outcome Is Unknown

If you are unsure whether a transfer committed and immediately send a reverse transfer:

~~~text
TX-001 unknown
  |
  v
Send TX-002 reversal
~~~

you can corrupt balances if TX-001 never actually committed. Compensation in **saga/reconciliation** workflows requires knowing verified states and business IDs, not guessing on UCTR.

### 16.5. A Helpful Status Endpoint

Example:

~~~http
GET /transfers/requests/REQ-001
~~~

Response might be:

~~~json
{
  "requestId": "REQ-001",
  "status": "IN_DOUBT",
  "message": "Commit is being verified"
}
~~~

After reconciliation:

~~~json
{
  "requestId": "REQ-001",
  "status": "COMMITTED",
  "transferId": "TX-REQ-001"
}
~~~

Exact HTTP codes and field names can vary; what matters is **never conflating unknown with failed**.

## 17. Transactions and Write Concern: Commit Durability

### 17.1. Write Concern Is Set at the Transaction Level

~~~java
TransactionOptions options = TransactionOptions.builder()
        .readConcern(ReadConcern.SNAPSHOT)
        .writeConcern(WriteConcern.MAJORITY)
        .build();
~~~

Write concern applies at transaction commit per MongoDB semantics. **Never specify per-operation write concerns inside a transaction**; MongoDB disallows per-operation write concern overrides inside transactions.

### 17.2. Limitations of `w:1` at Commit

If a transaction commits with **`w:1`**, the client can receive acknowledgment before the transaction is majority-committed. During a failover, the transaction can roll back under replica set mechanics.

When strong durability is needed, configure **`w:"majority"`** aligned with your topology and journaling setup.

### 17.3. Retried Commits May Use Majority

MongoDB documentation notes that drivers can apply **`w:"majority"` when retrying `commitTransaction`**, even if the transaction originally specified a different write concern. This is part of commit-retry semantics, not an excuse to skimp on initial durability settings.

### 17.4. `wtimeout` Does Not Prove Rollback

If commit raises a write concern timeout error, the server may have already applied the commit decision without reaching the requested acknowledgment count before the deadline. Classify by **label and context**, rather than returning “transaction failed” and creating a new transaction.

### 17.5. Transaction Read Concern

Common read concerns:

- **`snapshot`** for consistent point-in-time reads inside a transaction.
- **`majority`** when requesting majority-committed data per commit semantics.
- **`local`** when weaker guarantees are acceptable.

Inside a transaction, write concern is configured at the transaction/commit level. To guarantee a majority-committed snapshot per documentation, pair **`readConcern` `snapshot`** with **`writeConcern` `majority` at commit**.

Never use **`linearizable`** or **`available`** read concerns in multi-document transactions.

## 18. Performance and Transaction Limits

### 18.1. Transactions Should Not Carry Too Much Work

Long operations increase risks of:

- Transaction lifetime exceeded.
- WiredTiger cache pressure.
- Write conflicts from holding documents too long.
- Snapshot history pressure.
- Lock acquisition timeouts.
- Chunk migration/metadata interactions on sharded clusters.

Aim for **short transactions aligned to the exact business atomic unit**.

### 18.2. Redesign Instead of Increasing Retries Infinitely

Suppose a transaction processes 50,000 line items and hits **`TransactionTooLargeForCache`**. Re-running the same monolithic block 100 times will not fix the root cause.

Consider:

1. Embedding cohesive data into one document to leverage single-document atomicity.
2. Splitting batches into smaller units where domain invariants allow.
3. Persisting checkpoints for recoverable workflows.
4. Improving indexes/queries so transactions read and pin less state.
5. Using sagas/outbox when workflows span multiple systems.

### 18.3. The 16 MiB Limit

MongoDB enforces a **16 MiB size limit per BSON document**. In transactions, operations can generate multiple oplog entries rather than capping an entire transaction at 16 MiB in a single oplog entry, yet **individual entries/documents still have their own limits**.

Never treat transactions as a way to write documents arbitrarily larger than the BSON limit.

### 18.4. Parallel Operations Inside One Transaction

The Java Sync Driver does not support parallel operations inside the same transaction. Never use **`parallelStream()`**, **`CompletableFuture.allOf()`**, or share one `ClientSession` across threads issuing concurrent commands.

### 18.5. Read Sets and Stale Reads

A transaction with snapshot read concern reads a fixed version while another transaction commits newer state. Consistent snapshot reads **do not guarantee seeing every latest write**.

When business invariants depend on rapidly changing data, use conditional writes, guard documents, or appropriate protocols. Never use snapshot reads as a substitute for all concurrency control mechanisms.

## 19. Observability: What to Log When Transactions Retry?

Retries are meaningful operational signals. Under load, metrics distinguish routine transient conflicts from hot documents, failovers, or misconfigurations.

### 19.1. Recommended Log Fields

| Field | Meaning |
|---|---|
| **`businessRequestId`** | Stable ID across retries of one business request. |
| **`transactionAttempt`** | Attempt number of the full body. |
| **`commitAttempt`** | Attempt number of commit. |
| **`phase`** | `start`/`body`/`commit`/`abort`/`reconcile`. |
| **`errorLabels`** | TTE, UCTR, or other labels. |
| **`errorCode/codeName`** | Supplemental detail from driver/server. |
| **`elapsedMs`** | Elapsed time spent in the request/transaction. |
| **`finalOutcome`** | `COMMITTED`, `ABORTED`, `IN_DOUBT`, `FAILED_VALIDATION`... |
| **`clusterTopology`** | Replica set/sharded cluster and node context where relevant. |
| **`correlationId`** | Links to HTTP/message queue tracing. |

Never log raw bank account details, personal information, tokens, or full sensitive payloads.

### 19.2. Useful Metrics

- **`transaction_body_retry_total`**
- **`transaction_commit_retry_total`**
- **`transaction_transient_error_total`**
- **`transaction_unknown_commit_total`**
- **`transaction_in_doubt_total`**
- **`transaction_outcome_reconciliation_latency`**
- **`transaction_duration_p95/p99`**
- **`transaction_abort_total`**
- **`transaction_write_conflict_total`**
- **`transaction_cache_errors_total`**
- **`transaction_duplicate_request_total`**

These names are suggested custom application metrics, not mandatory built-in MongoDB metric names.

### 19.3. Monitoring the MongoDB Server

In environments with sufficient privileges:

~~~javascript
db.serverStatus().transactions;
~~~

The output exposes metrics on current, committed, and aborted transactions depending on server version. Check exact documentation for your version and monitor replication lag, primary elections, cache, locks, and latency.

### 19.4. Operational Alerts

Example alert rules:

~~~text
If UnknownTransactionCommitResult spikes:
  Check network, primary elections, write concern latency.

If TransientTransactionError spikes:
  Check write conflicts, hot documents, transaction duration.

If TransactionTooLargeForCache rises:
  Check transaction design and WiredTiger cache pressure.

If IN_DOUBT accumulates:
  Check reconciliation workers and replica set health.
~~~

Never crank retries up indefinitely just to make dashboard error counts look smaller.

## 20. Controlled Testing of Transaction Errors

### 20.1. Testing Is More Than One Happy-Path Transaction

A single unit/integration test calling `transfer` once and checking two balances does not prove error handling works.

At minimum, test:

1. Body succeeds and commit succeeds.
2. Body hits **`TransientTransactionError`**, then a subsequent attempt succeeds.
3. Commit hits **`UnknownTransactionCommitResult`**, then commit retry succeeds.
4. Commit hits consecutive UCTR errors until budget exhaustion.
5. Body hits **`DuplicateKey`** without infinite retries.
6. Business precondition **insufficient funds** is never turned into a transient retry.
7. A `requestId` resent after an unknown outcome does not transfer twice.
8. Callback re-execution does not emit duplicate emails/charges outside the transaction.
9. Oversized transactions fail without looping endlessly on the same payload.
10. Process crash after commit and before external publish still leaves an outbox event to process.

### 20.2. Mocking States at the Business Layer

You do not need real network outages to unit test the state machine. Abstract:

~~~text
TransactionBodyExecutor
CommitExecutor
TransactionErrorClassifier
RetryBudget
OutcomeReconciler
~~~

Then inject outcomes sequentially:

~~~text
Scenario A:
  executeBody attempt 1 -> TTE
  executeBody attempt 2 -> success
  commit attempt 2      -> success

Assert:
  bodyExecutionCount = 2
  commitExecutionCount = 1
~~~

~~~text
Scenario B:
  executeBody attempt 1 -> success
  commit attempt 1      -> UCTR
  commit attempt 2      -> UCTR
  commit attempt 3      -> success

Assert:
  bodyExecutionCount = 1
  commitExecutionCount = 3
~~~

~~~text
Scenario C:
  executeBody attempt 1 -> success
  commit -> UCTR until retry budget exhausted

Assert:
  outcome = IN_DOUBT
  bodyExecutionCount = 1
  No duplicate payment initiated
~~~

These are the core assertions of this lesson: **TTE re-runs the body**, whereas **UCTR does not re-run the body**.

### 20.3. Integration Testing with Two Competing Transactions

On a test replica set:

1. Seed accounts with fixed balances/versions.
2. Open **two separate sessions**.
3. Start two transactions.
4. Have both update the same document under controlled contention.
5. Observe one transaction hitting write conflict/abort with the corresponding error label.
6. Allow full-body retry when labeled TTE.
7. Assert balance invariants after final outcomes.

Exact conflict errors depend on timing, locking, and server version, so synchronize threads deterministically or use fault injection rather than hoping a natural race triggers reliably every run.

### 20.4. Failover and Network Faults in Staging Environments

Use chaos engineering or a controlled test harness to simulate:

- Primary stepdown.
- Brief network partition.
- Latency or failure during commit response.
- Commit write concern timeout.

Some server/test deployments support **`failCommand` failpoints** and other failpoints for fault injection; availability and permissions depend on your MongoDB/Atlas setup.

**Never enable failpoints or step down a production primary just to test this lesson.** Only test in authorized environments with clean rollback plans.

### 20.5. Verifying Correctness After an Unknown Commit

Simulate:

~~~text
Server commits transfer REQ-001 successfully
Network drops response
Client observes UCTR
~~~

Tests must verify:

- The service **does not** start a new debit/credit transaction.
- The service **retries commit** while the session remains valid.
- If still unverified, status becomes **`IN_DOUBT`**.
- Reconciliation uses `requestId` and majority-committed reads to determine the outcome.
- When the client resends `requestId`, no duplicate transfer occurs.

Do not merely assert exception counts; verify **the final state of documents**.

## 21. Phase-by-Phase Safety Checklist

### 21.1. Before Starting the Transaction

- Authenticate caller, tenant, and access permissions.
- Validate amounts, IDs, currencies, and business states.
- Establish a stable **business `requestId`** across retries.
- Ensure required collections/indexes already exist if DDL is disallowed in transactions.
- Select appropriate write concern, read concern, and timeouts.
- Set request duration and retry budgets.

### 21.2. Inside the Transaction Body

- Pass the **same `ClientSession`** to every MongoDB operation.
- Re-check preconditions against fresh data on **each attempt**.
- Never trigger direct external side effects outside the database.
- Never run parallel operations on the same session.
- On TTE, abort/end the attempt and retry the full body in a new transaction.
- On non-retryable errors, stop and propagate the root cause.

### 21.3. During Commit

- Never call commit if the transaction body failed.
- On UCTR, retry **commit of the same transaction**.
- Never start a new body merely because the commit response was lost.
- Pay attention to majority write concern, max commit time, and deadlines.
- If confirmation fails, preserve **`IN_DOUBT`** for reconciliation.

### 21.4. After Commit

- Report **`COMMITTED`** only with valid confirmation.
- Dispatch external effects via an outbox or idempotent protocol.
- Never return success for a reused `requestId` with a different payload.
- Log metrics/traces with `requestId` and attempt counts without leaking secrets.
- Maintain a reconciliation workflow capable of running even after the API client disconnected.

## 22. Mapping Transaction Outcomes to API Responses

An API usually needs more than two boolean states.

| Outcome | Suggested HTTP | Meaning |
|---|---|---|
| **`COMMITTED`** | 200/201/204 | Transaction confirmed. |
| **`INVALID_REQUEST`** | 400/422 | Invalid payload; do not retry unchanged. |
| **`BUSINESS_CONFLICT`** | 409 | Insufficient balance, invalid state, or `requestId` reuse conflict. |
| **`RETRY_EXHAUSTED`** | 503/500 depending on error | Transient errors retried properly without success. |
| **`IN_DOUBT`** | 202 or domain-specific status | Commit outcome unknown; query status endpoint. |
| **`UNAUTHORIZED/FORBIDDEN`** | 401/403 | Permission issue; never retry to bypass. |

HTTP codes are suggestions; API designs vary. Most importantly, **never report definite failure when commit may have succeeded**.

### 22.1. Client Retry Policy

If the server returns **`IN_DOUBT`**, the client should:

1. Keep the same `requestId`.
2. Poll a status endpoint or await asynchronous notification.
3. Never submit a brand-new transfer with a different ID.
4. When retrying HTTP over network errors, reuse the same idempotency key per server protocol.

### 22.2. HTTP Timeouts Differ from MongoDB Timeouts

An API gateway may drop the connection after 10 seconds while the MongoDB operation is still running. Never conclude “HTTP 504 = transaction aborted” unless the server confirmed it.

Design cancellation, transaction deadlines, and reconciliation so the system recovers cleanly even after the caller stops waiting.

## 23. Common Mental Traps

### 23.1. “TTE Means Retry the Single Failed Operation”

**False.** When an operation inside a transaction hits **`TransientTransactionError`**, retry the **whole transaction** in a new attempt; never just re-run one update statement.

### 23.2. “UCTR Means Commit Failed”

**False.** The commit outcome is **unknown**; it may have succeeded.

### 23.3. “After UCTR, Just Call the Business Service Again”

**Dangerous.** The business service may open a new transaction, causing double execution. Retry the **same commit** while the session is valid or reconcile the outcome.

### 23.4. “`retryWrites=true` Automatically Retries Every Operation Inside a Transaction”

**False.** Individual writes inside a transaction are not retried independently like standalone retryable writes. The Callback API handles transaction-level retries; commits have their own retry semantics.

### 23.5. “Spring `@Transactional` Automatically Retries Just Like `withTransaction`”

**False.** A Spring transaction boundary does not automatically install the same error-label retry loop as the Java Driver callback API.

### 23.6. “`@Retryable` on Every `MongoException` Is Safe”

**False.** If an exception arises from an unknown commit, retrying the entire service method can duplicate business effects. Separate phases, error labels, and transaction boundaries.

### 23.7. “`DuplicateKey` Can Be Retried Until It Succeeds”

**False.** Unique constraints do not vanish by repeating code. For duplicate `requestId`, reconcile the prior request; for real data conflicts, fix the data.

### 23.8. “Calling Abort After Unknown Commit Will Undo It”

**False.** Abort never undoes an already-committed transaction; when outcome is unknown, never use abort as proof of failure.

### 23.9. “Reading No Record Proves Commit Never Happened”

**False.** Reads can be stale or commit may not yet be visible. Reconciliation needs proper consistency, routing, and retry policies.

### 23.10. “A Unique `requestId` Automatically Gives Exactly-Once Email/Kafka”

**False.** A unique index is only one piece. External side effects require their own idempotency/outbox and deduplication rules.

### 23.11. “Transactions Can Stay Open Indefinitely”

**False.** Transaction lifetime, cache, locks, and snapshot history are bounded. Keep transactions short.

### 23.12. “Insufficient Funds Should Retry Dozens of Times”

**False.** Insufficient funds is a business precondition failure unless valid new state or a new request arrives; retrying unchanged adds load without creating money.

### 23.13. “If the Callback Runs Twice, MongoDB Debited Twice”

Not necessarily. An aborted attempt leaves no uncommitted writes in final state. However, **external side effects** inside the callback truly repeat, so keep them out.

### 23.14. “A Transaction Committed with `w:1` Can Never Roll Back”

False under certain failovers. When majority durability is required, configure majority commit write concern appropriately.

### 23.15. “Every `WriteConflict` Always Carries TTE”

Never infer from error names alone. Always check error labels, phase, driver, and server version.

### 23.16. “If the Retry Budget Runs Out, Just Return 500”

Insufficient. Distinguish **retry-exhausted transient body errors** from **unknown commit outcomes**; the latter usually requires `IN_DOUBT` and reconciliation.

## 24. Hands-On Exercises

### Exercise 1 — Identifying the Right Retry

A transaction has three commands:

~~~text
1. debit ACC-A
2. credit ACC-B
3. insert transfer
~~~

Step 2 hits `TransientTransactionError`. Draw the restart diagram and explain why step 1 must re-run inside a new transaction.

### Exercise 2 — Unknown Commit Error

All body operations succeed. The client sends commit, loses the response, and receives `UnknownTransactionCommitResult`.

Tasks:

1. List the two states the server could be in.
2. Identify which command should be retried.
3. Explain why you must not open a new transaction and re-run debit/credit.

### Exercise 3 — Decision Tree

Design a function accepting **phase**, **error labels**, and **retry budget** to return one of:

~~~text
RETRY_WHOLE_TRANSACTION
RETRY_SAME_COMMIT
FAIL_NON_RETRYABLE
IN_DOUBT
~~~

### Exercise 4 — Java Driver `withTransaction`

Write Java code using **`ClientSession.withTransaction`** for all three transfer operations on the same session. Ensure:

- `readConcern` `SNAPSHOT`;
- `writeConcern` `MAJORITY`;
- every collection operation receives `session`.

### Exercise 5 — Spotting a Missing Session

Given:

~~~java
session.withTransaction(() -> {
    accounts.updateOne(
            Filters.eq("_id", "ACC-A"),
            Updates.inc("balanceCents", -20000L)
    );
    return null;
});
~~~

Find the bug and fix it using the overload accepting **`ClientSession`**.

### Exercise 6 — Spring Retry Boundary

A service uses both **`@Retryable`** and **`@Transactional`**. Explain why you must verify interceptor ordering so each TTE retry gets a fresh transaction.

### Exercise 7 — Do Not Retry the Service When Commit Is Unknown

Propose how to isolate commit retries in **`MongoTransactionManager#doCommit`** or a custom transaction layer instead of blanket-retrying the whole method.

### Exercise 8 — Duplicate `requestId`

Two HTTP requests share `REQ-001` and the same payload. Design:

- Unique index;
- business request fingerprint;
- `DuplicateKey` handling;
- reconciliation when the first request's commit outcome was unknown.

### Exercise 9 — Idempotency Key Reuse Conflict

A client sends `REQ-001` a second time, changing **`toAccount`** and **`amountCents`**. What must the API return and why must it not be treated as the same request?

### Exercise 10 — Transactional Outbox

Add an outbox event to the transfer transaction and design a publisher worker. Describe what happens if the worker publishes and crashes before marking dispatched; how does the consumer handle duplicates?

### Exercise 11 — Retry Budget

Design `maxBodyAttempts`, `maxCommitAttempts`, deadline, and backoff for a latency-bounded API. Contrast the consequences of exhausting the body budget vs. exhausting the commit budget.

### Exercise 12 — `TransactionTooLargeForCache`

A transaction writes tens of thousands of documents and hits `TransactionTooLargeForCache`. Explain why retrying the exact same workload is ineffective and propose at least three design improvements.

### Exercise 13 — Integration Testing

Write a test plan with two sessions concurrently updating one account. Expect `WriteConflict`/TTE; describe how to synchronize threads and assert invariants after retries.

### Exercise 14 — Commit Failover

A replica set test simulates losing the commit response. Assert:

~~~text
bodyExecutionCount = 1
commitExecutionCount >= 2
~~~

when UCTR occurs and the commit retry succeeds. Why is checking only the returned error count insufficient?

### Exercise 15 — Mapping API Outcomes

Design **`GET /transfers/requests/REQ-001`** for the `IN_DOUBT` case. Describe how clients poll without creating new business transfers.

### Exercise 16 — Metrics

Pick five metrics that detect primary elections, contention, and unknown commit outcomes. Describe an alert policy that avoids triggering retry storms.

## 25. Review Questions

1. Is `TransientTransactionError` an error code or an error label?
2. Why does TTE require retrying the full transaction rather than just the failing statement?
3. Does `UnknownTransactionCommitResult` mean the commit definitely failed?
4. When receiving UCTR, should you retry the body or commit?
5. When must you keep the `IN_DOUBT` state?
6. Why is calling abort after UCTR not a guaranteed rollback?
7. How does Java Sync Driver `withTransaction` handle TTE and UCTR?
8. How does the Core API differ from the Callback API in retry responsibilities?
9. Are individual writes inside a transaction retried independently via `retryWrites=true`?
10. Why must Java Driver methods inside a transaction receive the same `ClientSession`?
11. Does Spring `@Transactional` automatically implement `withTransaction`-style retry semantics?
12. How can `@Retryable` be dangerous during the commit phase?
13. Why must non-DB side effects never sit directly inside a retryable callback?
14. What gap between commit and publish does a transactional outbox close?
15. Why do outbox consumers still need idempotency?
16. How should `DuplicateKey` on `requestId` be handled?
17. Why must the same `requestId` with a different payload return a conflict?
18. Should `TransactionTooLargeForCache` be addressed by retries or redesign?
19. How does `transactionLifetimeLimitSeconds` constrain retry policies?
20. Why is majority write concern needed for commit durability?
21. When a commit response is lost, can an HTTP timeout prove rollback?
22. When can a reconciler confirm a transfer committed based on a majority-committed record?
23. Why is failing to see a transfer record on one read insufficient to prove it never committed?
24. Which metrics distinguish normal transient conflicts from configuration bugs?
25. What test proves UCTR retries commit without re-executing the body?

## 26. Summary: Remembering the Two Retry Types

The core lesson revolves around **two errors with distinct recovery semantics**:

~~~text
TransientTransactionError
  -> Transient transaction error inside the body.
  -> Abort old attempt if needed.
  -> Start a new transaction.
  -> Re-run the entire body and business checks.

UnknownTransactionCommitResult
  -> Unknown whether the current transaction's commit succeeded.
  -> Retry commit of the same transaction/session.
  -> DO NOT re-run the body solely due to a lost commit response.
  -> If unconfirmable: IN_DOUBT and reconcile.
~~~

Key production principles:

1. **Use error labels and phases**, never parse message strings or retry every exception.
2. **Driver Callback API** automates TTE/UCTR retries; **Core API** requires explicit application orchestration.
3. **Spring `@Transactional`** does not automatically equal driver `withTransaction`; align transaction and retry boundaries carefully.
4. **Retries need budgets, deadlines, and telemetry**; validation, duplicate key, and resource errors do not vanish on retry.
5. **Stable business `requestId` and unique constraints** identify replayed requests, paired with reconciliation and payload checks.
6. **External side effects** must be idempotent or routed via outbox/sagas, never placed directly inside a re-executable callback.
7. **Unknown commit outcomes differ from definite failures**; APIs need an `IN_DOUBT`/reconciliation state instead of false failure reports.
8. **Keep transactions short and focused**; test failovers and contention on real replica sets/sharded clusters.

### Official MongoDB and Spring Data References

- [MongoDB — Handle Transactions in Applications with the Drivers API](https://www.mongodb.com/docs/manual/core/transactions-in-applications/) — Callback API, Core API, TTE, and UCTR.
- [MongoDB — Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — atomicity, write concern, and transaction limits.
- [MongoDB — Production Considerations for Transactions](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/) — lifetime, cache, locks, conflicts, and sharding.
- [MongoDB — `commitTransaction` Command](https://www.mongodb.com/docs/manual/reference/command/commitTransaction/) — commit semantics and write concern.
- [MongoDB — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/) — distinguishing retryable writes from transaction semantics.
- [MongoDB — Java Sync Driver Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/) — `ClientSession`, `withTransaction`, and `TransactionOptions`.
- [MongoDB — Read/Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — `w:majority` and durability.
- [Spring Data MongoDB — Sessions & Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html) — `MongoTransactionManager`, `@Transactional`, and retry guidance.

Whenever MongoDB reports a transaction error, ask **“did it happen before commit or right at commit?”** If the body hit **`TransientTransactionError`**, retry the **whole transaction**. If commit hit **`UnknownTransactionCommitResult`**, retry **the same commit** and retain reconciliation if the outcome stays uncertain. Separating these two paths cleanly is the foundation for recovering from transient faults without creating duplicate business transactions.
