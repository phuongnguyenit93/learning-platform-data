# Distinguishing Full Transaction Retries from Commit Retries in MongoDB

## 1. Opening Scenario: Where Did the Error Occur and What Gets Retried?

An e-wallet system uses MongoDB to store two accounts and a transaction record. When a user transfers 100 currency units from account A to B, the system needs three changes to happen together:

1. Deduct 100 from A's balance.
2. Add 100 to B's balance.
3. Save a `transferLedger` record with a unique request ID.

MongoDB supports **multi-document transactions** so these changes commit as an atomic unit. However, transactions do not make the network infallible: the server may commit while the **commit response is lost**.

Compare two incidents:

**Scenario A — transient error while the transaction is still executing:**

```text
startTransaction
      |
      v
  Debit A
      |
      v
  Credit B
      |
      X  WriteConflict / transient error;
         transaction can no longer complete validly
      |
      v
  Discard this attempt, start a new transaction,
  and re-execute the ENTIRE logic.
```

**Scenario B — error while awaiting the commit response:**

```text
startTransaction
      |
      v
  Debit A --> Credit B --> Write ledger
      |
      v
commitTransaction  ----------------> MongoDB
                                     May HAVE COMMITTED
      X <---------------------------- Response lost
      |
      v
  Commit outcome is unknown.
  Resend COMMIT of the SAME transaction;
  DO NOT re-run the transfer logic.
```

Key takeaway:

> **Retrying the full transaction** means re-executing the read/write operations in a **new transaction attempt**, after determining that the prior attempt failed/cannot commit and the error is retryable.

> **Retrying the commit** means asking MongoDB to **confirm/complete the commit of the current transaction itself**, when the commit outcome is undetermined. The reads/writes inside the transaction **must not be re-executed** in this step.

Confusing these two actions risks **double transfers, duplicate orders, duplicate notifications, or double-recorded business data**, especially when applications build manual retry loops outside driver mechanisms.

## 2. Lesson Objectives

After this lesson, you will be able to:

- Distinguish **transaction body**, **`commitTransaction`**, and **business request retries**.
- Recognize the meaning of the **`TransientTransactionError`** and **`UnknownTransactionCommitResult`** error labels.
- Know when to **re-run the whole transaction** and when to **retry commit on the same session/transaction identity**.
- Explain why **a lost commit acknowledgment is not proof of rollback**.
- Use transaction callbacks like **`withTransaction()`** in MongoDB drivers with accurate expectations.
- Design **stable request IDs**, unique indexes, and reconciliation steps to prevent duplicate effects on API replays.
- Handle non-retryable exceptions and avoid unbounded retry loops.

The scope focuses on **MongoDB transactions** in the *Transactions* chapter, not every single-document write command. Retryable writes for individual commands are related, yet **do not replace** transaction retries.

## 3. Three Retry Layers to Separate

In a real application, at least three levels of “retry” are easily conflated under one name:

| Layer | Unit Retried | Example | Safety Requirement |
|---|---|---|---|
| **Commit retry** | `commitTransaction` of the **same transaction** | Commit response lost | Preserve exact session/transaction identity; use protocol/driver |
| **Transaction retry** | All operations inside the transaction, in a **new attempt** | Transaction aborted due to eligible transient error | Only when error permits restarting the transaction; body has no uncontrolled external side effects |
| **Business/API retry** | A client command like `POST /transfers` | Gateway returns 504, user retries | Use an **idempotency key** and reconciliation; never assume the prior transaction did not commit |

The first two layers are usually handled by the **MongoDB driver or transaction orchestration code**. The third belongs to **application business design** and cannot rely solely on connection-level error labels.

### 3.1. An API Can Be Called Twice Even When the First Transaction Succeeded

```text
Mobile App
   |
   | POST /transfers { requestId: "TR-001", amount: 100 }
   v
Backend
   |
   | transaction + commit succeeds
   v
MongoDB

Backend or gateway drops connection while returning HTTP response.
Mobile App sees no response, resends POST.
```

If the backend treats the second HTTP request as a **brand-new transfer**, the MongoDB transaction on each call can be **atomic and valid**, yet the customer gets debited **twice**.

Therefore:

- **Transaction atomicity** prevents “debit A without crediting B” within one valid commit.
- **Retry protocol** handles transient errors or unknown commit results for one transaction execution.
- **Business idempotency** prevents one transfer request from turning into **two distinct committed transactions**.

Never conflate these three layers of guarantees.

## 4. Lifecycle of a MongoDB Transaction

A multi-document transaction is managed through a **session**:

```text
Create session
      |
      v
startTransaction
      |
      +--> Read #1
      |
      +--> Write #1
      |
      +--> Write #2
      |
      v
commitTransaction
      |
      +--> Commit confirmed    ---> COMMITTED
      |
      +--> Outcome unknown     ---> retry commit / reconcile
      |
      +--> Clear error         ---> handle per error type

Or:

Error inside body prevents transaction from completing
      |
      v
abortTransaction / transaction aborted
      |
      v
If transient and eligible: new startTransaction + re-run body
```

### 4.1. What Is a Session?

A `ClientSession`/logical session enables driver and server to associate commands with a session context. Within a transaction, the driver also tracks transaction identity so the server knows which commands belong to the same transactional unit.

**Never create a new session** when your goal is retrying commit for an unknown transaction outcome. Doing so loses the link to the commit awaiting confirmation.

### 4.2. What Does the Transaction Body Contain?

The body may consist of multiple commands sharing the same session:

```javascript
// Business concept, not complete runnable code.
debit(A, 100, session);
credit(B, 100, session);
insertLedger("TR-001", session);
```

These commands execute inside a transaction, yet are not exposed as committed data until commit succeeds.

**Every MongoDB operation in the transaction must pass the exact same session**. A command accidentally run without the session can commit independently, breaking the atomicity you thought you had.

### 4.3. Commit Is a Separate Step

`commitTransaction` is not another call to `debit()`, `credit()`, or `insertLedger()`. It is the command asking the server to finalize the already-identified transaction.

When retrying commit, what must be preserved is **the same transaction identity**, not merely “the same JavaScript/Java statements”.

## 5. Error Classification: Two Crucial Error Labels

MongoDB drivers can attach **error labels** to exceptions to guide retry strategy. Two central labels are:

| Error Label | Guiding Meaning | Usually Appropriate Action |
|---|---|---|
| `TransientTransactionError` | Transient error while executing the transaction; this attempt may need to be re-run | **Retry the entire transaction** if no business rule forbids it |
| `UnknownTransactionCommitResult` | Client **does not know for sure** whether the commit succeeded | **Retry commit of the same transaction**; do not re-run the body |

**Not every exception carries an eligible label.** Errors like duplicate keys, validation failures, invalid business input, or bad system configuration will not be resolved by automatic retries.

### 5.1. `TransientTransactionError`

Suppose a transaction encounters a write conflict or failover event during execution. The driver is notified that the current attempt cannot finish normally and may start **a new transaction attempt**.

```text
Attempt #1
  startTransaction
  read A
  debit A
  [TransientTransactionError]
  abort/discard attempt

Attempt #2
  startTransaction
  read A again
  debit A again in new transaction
  credit B
  insert ledger
  commit
```

Core point: **the first attempt is not treated as a committed transaction**. Its uncommitted writes do not become a completed transfer. The driver/helper can re-execute the body in a new transaction.

Because the new transaction may observe **updated data state**, the body must re-verify business preconditions rather than treating an earlier out-of-transaction read as immutable truth.

### 5.2. `UnknownTransactionCommitResult`

Suppose MongoDB executed the commit, but the client lost the response:

```text
Attempt #1
  startTransaction
  debit A
  credit B
  insert ledger
  commitTransaction  ------------> Server
                                     COMMIT succeeds
  X <------------------------------ response lost

Client receives UnknownTransactionCommitResult
  |
  +--> Retry commitTransaction of Attempt #1
       DO NOT call debit/credit/insertLedger again
```

The commit outcome could be:

- Already succeeded, only the response was lost.
- Not yet finished or not yet acknowledged as required.
- Undetermined under current network/failover conditions.

**These possibilities cannot be distinguished solely from the missing client response.** Therefore, retry the **commit command** per protocol or temporarily conclude **UNKNOWN** if unresolved within a reasonable deadline.

### 5.3. Error Labels Are Conditional Guidance, Not Magic

Do not write:

```java
// WRONG: retry entire transaction on any MongoException.
catch (MongoException e) {
    runBusinessTransactionAgain();
}
```

Nor should you write:

```java
// WRONG: every timeout means commit definitely failed.
catch (MongoException e) {
    return "NOT_COMMITTED";
}
```

Instead, classify based on **which command was executing**, **error labels**, **transaction state**, **attempt count**, and **business request idempotency**.

## 6. When Should You Retry the Full Transaction?

### 6.1. Mental Model

Retry the full transaction when there is proper evidence that **the current transaction attempt cannot validly commit** and the error is **transient**, such as receiving `TransientTransactionError` while executing the body.

Re-execution typically involves:

1. Ending/aborting the old attempt when necessary and possible.
2. Starting a new transaction.
3. Re-reading input state inside the new transaction.
4. Re-executing **the entire business body**.
5. Attempting to commit the new transaction.

**Do not merely resend the last failing statement** inside a transaction the server already marked aborted. The entire read/write state of the old attempt is no longer a valid commit context.

### 6.2. Write Conflict Example

Two transactions concurrently modify the same account document under contention. One transaction may receive a write conflict error, which the driver labels as transient:

```text
Transaction T1             Transaction T2
    |                           |
    | read balance              | read balance
    |                           |
    | update account A          | update account A
    |                           |
    |                           X write conflict
    | commit                    |
    |                           |
                                v
                         Retry transaction T2
                         re-read updated balance
```

This is a **possible execution pattern**, not a guarantee of which transaction will lose on every run.

T2 must re-read data in the fresh attempt; never retain a balance check from the previous attempt when data may have been changed by T1.

### 6.3. What Must Not Repeat Inside the Body?

The transaction callback can be invoked by the driver **multiple times**. Therefore, never place non-rollbackable side effects carelessly inside the callback:

```java
session.withTransaction(() -> {
    debitInMongoDB(session);
    creditInMongoDB(session);

    sendEmail("Transfer completed"); // Dangerous if body retries.
    chargeExternalGateway();         // Even more dangerous.

    return null;
});
```

A MongoDB transaction **does not roll back emails or external payment gateway charges**. If the body re-executes, both actions can happen twice.

An appropriate design may:

- Save an **outbox event** inside the same transaction.
- Trigger side effects only after commit status is verified.
- Have the outbox consumer deduplicate using an **event ID / idempotency key**.
- Use the external system's own idempotency key if supported.

Never simply move side effects right after `withTransaction()` and assume they are exactly-once: an application crash after commit and before sending the email still requires an outbox or recovery mechanism.

### 6.4. Random IDs and Timestamps Inside the Callback

If the callback generates a fresh transfer ID or request ID on every invocation:

```java
session.withTransaction(() -> {
    String requestId = UUID.randomUUID().toString(); // Different ID per body retry.
    // ...
    return null;
});
```

then different attempts carry different business identifiers. In pure transaction retries the prior attempt aborted so it might not double-commit, yet **unstable business identifiers break reconciliation and HTTP-layer deduplication**.

Instead, generate a **stable request ID outside the callback** or accept it from the client before starting the workflow:

```java
final String requestId = incomingRequestId;

session.withTransaction(() -> {
    insertTransferLedger(session, requestId);
    debitAccount(session);
    creditAccount(session);
    return null;
});
```

Business timestamps, exchange rates, or reference prices also need clear rules: re-read current state on each retry without accidentally turning the same request into one with altered business parameters.

## 7. When Should You Retry Only the Commit?

### 7.1. The Issue Appears at the Commit Decision Step

Suppose the entire body finished:

```text
debit A         OK in transaction
credit B        OK in transaction
insert ledger   OK in transaction
commit          UNKNOWN outcome
```

If you re-run debit/credit in a **new** transaction when the first commit actually succeeded, the operation can apply **twice**.

What must be resent is:

```text
commitTransaction of the original transaction
```

Not:

```text
new startTransaction
debit A
credit B
insert ledger
commit new transaction
```

### 7.2. Why Can Commit Be Resent?

The MongoDB protocol and drivers use session/transaction identifiers to recognize **commits of the exact same transaction**. As a result, resending commit can clarify or finalize the outcome **without re-executing business statements**.

This does not mean a client can start a brand-new transaction with identical contents and expect MongoDB to notice and skip it. **A new transaction is a distinct execution**, unless the business layer adds deduplication controls.

### 7.3. Do Not “Abort Just to Be Safe” After Unknown Commit

The following code is a bad idea:

```java
try {
    session.commitTransaction();
} catch (MongoException e) {
    session.abortTransaction(); // Cannot guarantee undoing the commit.
    throw e;
}
```

If the commit already succeeded, a late abort request **does not reverse committed data**. If the transaction state is still uncertain, aborting does not replace outcome verification either.

**Key distinction:** `abortTransaction` cancels an uncommitted transaction in the proper context; **it is not a post-commit rollback**.

### 7.4. Commit Retries Must Preserve Identity

In manual management, a commit retry must use:

- **The same `ClientSession`**.
- **The same transaction awaiting resolution**, without starting another transaction.
- **The same commit protocol** supported by the MongoDB driver.

Drivers normally manage protocol-level identifiers; applications **must never hand-craft protocol fields** or open a fresh session just to resend a commit command.

### 7.5. Never Retry Commit Infinitely

If the network is severed for a long period, an infinite loop holds resources and prevents the API from ever terminating:

```text
while (true) {
    try commit;
    catch any error -> retry immediately;
}
```

This is poor design. You need:

- **Error classification**: retry only when commit outcome is unknown and the protocol allows it.
- **Overall deadline** or reasonable limit per driver/workflow.
- **Backoff** where appropriate.
- **`UNKNOWN_OUTCOME` state** if confirmation cannot finish within the deadline.
- **Reconciliation by business key** before recreating the operation.

Commit retries resolve ambiguity in many cases, but cannot promise every network outage recovers immediately.

## 8. Decision Matrix: Retry Body or Retry Commit?

| Error Location / Type | Interpretation | Appropriate Action |
|---|---|---|
| Inside body, labeled `TransientTransactionError` | Current transaction attempt did not finish; likely transient | Discard/abort attempt and **retry full transaction** |
| Inside body, validation/duplicate key error not labeled transient | Data or constraint issue | **Do not** retry endlessly; handle as business error |
| Inside body, unclear error with no eligible label | Insufficient basis to assume retryable | Classify via driver/error; do not blindly resend |
| Commit returns success | Transaction commit confirmed as requested | Finish; do not retry body |
| Commit labeled `UnknownTransactionCommitResult` | Client does not know if commit completed | **Retry commit of the same transaction** |
| Commit remains unknown past deadline | Neither commit nor abort proven | Return/record `UNKNOWN_OUTCOME` and **reconcile** |
| Commit error definitely non-retryable per protocol | Inappropriate to keep retrying commit | Report error / reconcile per scenario |
| HTTP response lost after driver returned commit success | Backend knows success, client does not | **Idempotent API retry** with same request ID; no new transaction |
| Client resends API after error with no business key | Cannot distinguish old vs. new request | Design idempotency before adding retries |

### 8.1. Never Rely Solely on Exception Class Names

A `MongoException` can be thrown:

- Before the driver sends a command.
- Inside the transaction body.
- During the commit step.
- During post-commit reconciliation reads.

Thus, the same exception class does not always lead to the same decision. You must know **which phase was active** and **what the error labels say**.

### 8.2. Never Infer “Definitely Not Committed” from a Network Error

If an exception occurs during commit, **a lost response can happen after the server already wrote and published the transaction**. The right branch is “outcome unknown”, not “rolled back”.

## 9. General Algorithm: Two Nested Retry Loops

To understand driver mechanics, picture two loops:

```text
OUTER LOOP: attempt a TRANSACTION
  |
  +-- startTransaction
  |
  +-- run business body
  |      |
  |      +-- TransientTransactionError
  |               |
  |               +-- abort/discard attempt if applicable
  |               +-- return to OUTER LOOP
  |
  +-- INNER LOOP: commitTransaction of SAME attempt
           |
           +-- success
           |      |
           |      +-- DONE
           |
           +-- UnknownTransactionCommitResult
           |      |
           |      +-- return to INNER LOOP
           |          (do not re-run body)
           |
           +-- other error
                  |
                  +-- handle per concrete classification
```

This is a **conceptual algorithm** explaining both retry types, not advice to replace MongoDB driver-supported behavior with an unbounded manual loop.

### 9.1. Illustrative Pseudocode

```text
function executeTransactionWithRetry(requestId):
    repeat until transactionDeadline:
        session.startTransaction()

        try:
            runBusinessBody(session, requestId)

        catch error:
            if error has TransientTransactionError:
                abort if applicable
                continue outer loop   // RETRY FULL BODY

            abort if applicable
            return REJECTED_OR_FAILED(error)

        repeat until commitDeadline:
            try:
                session.commitTransaction()
                return COMMITTED

            catch error:
                if error has UnknownTransactionCommitResult:
                    continue inner loop  // RETRY COMMIT ONLY

                return CLASSIFY_COMMIT_ERROR(error)

        return UNKNOWN_OUTCOME

    return RETRY_DEADLINE_EXCEEDED
```

In real applications, the driver may already implement automatic retry logic, while aborts, commit deadlines, and specific errors must adhere to your **API/driver version**. This pseudocode is not copy-paste runnable and intentionally exposes the `UNKNOWN_OUTCOME` branch.

### 9.2. Why Must the Outer and Inner Loops Never Be Merged into One?

This is an anti-pattern:

```text
repeat:
    startTransaction
    runBusinessBody
    commitTransaction
until no exception
```

If the first attempt committed and the response was lost, the second iteration is a brand-new transaction. There is no overall guarantee that MongoDB will automatically discard the duplicate business transfer.

### 9.3. Not Every Error Belongs in a Retry Loop

If `amount` is negative, permissions are missing, a unique index is violated, data fails schema validation, or the user has insufficient funds, retrying the body 100 times will never make the request valid. Retry loops must **classify errors and be bounded**.

## 10. Preparing a Transaction Lab on a Replica Set

Examples use the **`txn_retry_lab249`** database on a learning MongoDB replica set. Multi-document transactions require a supported deployment such as a replica set; an ordinary standalone `mongod` cannot be used for this lesson.

**Never run simulated transfer commands against real data.** Currency values in examples use small integers for easy observation.

### 10.1. Seeding Initial Data

In `mongosh`:

```javascript
const labDb = db.getSiblingDB("txn_retry_lab249");

// Use a fresh lab database without existing documents sharing _id.
labDb.accounts249.insertMany([
  { _id: "A", balance: 1000, currency: "UNIT" },
  { _id: "B", balance: 500, currency: "UNIT" }
]);

labDb.transferLedger249.createIndex(
  { requestId: 1 },
  { unique: true }
);
```

We want the invariant:

```text
Total balance A + B before transfer = 1500

Transfer 100 from A to B:
  A: 1000 -> 900
  B:  500 -> 600
Total after transfer = 1500
Ledger has exactly 1 record for the corresponding requestId.
```

Checking the sum detects certain bugs, yet **is insufficient** to catch duplicate transfers: if the same 100 transfer runs twice, A+B still equals 1500. That is why a **ledger and business ID** are required.

### 10.2. Choosing a Request ID Before Starting

```javascript
const requestId = "TR-249-001";
```

This identifies **one transfer intent**, not one transaction attempt. If the driver retries the body or the API receives the same request again, `requestId` stays unchanged.

### 10.3. Rules for Writing Data Inside a Transaction

- Use the same session for all read/write commands needing atomicity.
- Validate positive amount and valid source/destination before execution.
- Include `balance >= amount` when debiting.
- Check `matchedCount` or invariant conditions so a transfer missing a step never commits.
- Insert a ledger record with unique `requestId` in the same transaction.
- Set write concern at the **transaction/commit level**, never on individual operations inside the transaction.
- Never call external payment APIs inside the transaction body.

## 11. `mongosh`: Manual Transaction to See Where Commit Sits

This example shows **one successful attempt**, without automatic retries. It highlights the body and commit:

```javascript
const conn = db.getMongo();
const session = conn.startSession();
const txDb = session.getDatabase("txn_retry_lab249");
const requestId = "TR-249-MANUAL-001";

try {
  session.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  });

  // Ledger and both balance updates share the same session.
  txDb.transferLedger249.insertOne({
    _id: requestId,
    requestId,
    from: "A",
    to: "B",
    amount: 100,
    currency: "UNIT"
  });

  const debit = txDb.accounts249.updateOne(
    { _id: "A", balance: { $gte: 100 } },
    { $inc: { balance: -100 } }
  );
  if (debit.matchedCount !== 1) {
    throw new Error("SOURCE_NOT_FOUND_OR_INSUFFICIENT_BALANCE");
  }

  const credit = txDb.accounts249.updateOne(
    { _id: "B" },
    { $inc: { balance: 100 } }
  );
  if (credit.matchedCount !== 1) {
    throw new Error("DESTINATION_NOT_FOUND");
  }

  session.commitTransaction();
  print("Transaction commit acknowledged");
} catch (e) {
  // Only abort when the transaction has not committed or outcome is not unknown.
  // This lab example DOES NOT provide an unknown-commit resolution strategy.
  print("Error: " + e.message);
  throw e;
} finally {
  session.endSession();
}
```

**Intentional limitation of this example:** the snippet shows session/transaction structure, **not a production retry orchestrator**. If `commitTransaction()` throws with an unknown commit result, `finally` closes the session; in production, the application needs a retry/reconciliation process and cannot conclude “rolled back”.

Do not copy this template and blindly add `session.abortTransaction()` to every `catch` branch, because the commit may have already succeeded. Section 9 and the Java section below explain proper helper usage.

### 11.1. Verifying Results After a Successful Run

```javascript
labDb.accounts249.find().sort({ _id: 1 });
labDb.transferLedger249.find({ requestId: "TR-249-MANUAL-001" });
```

After running successfully once on the initial data:

```javascript
{ _id: "A", balance: 900, currency: "UNIT" }
{ _id: "B", balance: 600, currency: "UNIT" }

{
  _id: "TR-249-MANUAL-001",
  requestId: "TR-249-MANUAL-001",
  from: "A",
  to: "B",
  amount: 100,
  currency: "UNIT"
}
```

If you run subsequent examples on the same database, balances change; do not compare against the values above without resetting initial state.

### 11.2. `mongosh` Session Helpers

`mongosh` exposes session and transaction APIs; if orchestrating retries manually, maintain the session carefully. In real applications, the recommended practice is using the driver's **convenient transaction API**, such as `ClientSession.withTransaction()` in the Java driver, to leverage supported retry logic and avoid commit-handling bugs.

## 12. Java Sync Driver: Using `withTransaction()`

In Java projects, the MongoDB Sync Driver provides the `ClientSession.withTransaction()` convenient transaction API. This helper can **re-invoke the body callback** on transient transaction errors, and **retry commit** when commit has an unknown result, per driver mechanics.

### 12.1. Preparing Transaction Options

```java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;
import com.mongodb.TransactionOptions;

TransactionOptions options = TransactionOptions.builder()
    .readConcern(ReadConcern.SNAPSHOT)
    .writeConcern(WriteConcern.MAJORITY)
    .readPreference(ReadPreference.primary())
    .build();
```

Meaning:

- `ReadConcern.SNAPSHOT`: requests snapshot reads inside the transaction.
- `WriteConcern.MAJORITY`: configures majority commit acknowledgment.
- `ReadPreference.primary()`: routes transaction reads to the primary.

Actual support depends on deployment and version. Transactions cannot turn a standalone `mongod` into a replica set.

### 12.2. Complete Java Transfer Example

This example uses `Document` and `MongoCollection` so passing `session` to every command is explicit. It requires a compatible MongoDB Sync Driver and test replica set.

```java
import com.mongodb.MongoException;
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

public class TransferWithTransaction {

    public static void main(String[] args) {
        String uri =
            "mongodb://localhost:27117,localhost:27118,localhost:27119/" +
            "?replicaSet=rsLab&retryWrites=true";

        // One transfer request -> one stable business ID.
        final String requestId = "TR-249-JAVA-001";
        final long amount = 100L;

        TransactionOptions options = TransactionOptions.builder()
            .readConcern(ReadConcern.SNAPSHOT)
            .writeConcern(WriteConcern.MAJORITY)
            .readPreference(ReadPreference.primary())
            .build();

        try (MongoClient client = MongoClients.create(uri);
             ClientSession session = client.startSession()) {

            MongoDatabase database =
                client.getDatabase("txn_retry_lab249");
            MongoCollection<Document> accounts =
                database.getCollection("accounts249");
            MongoCollection<Document> ledger =
                database.getCollection("transferLedger249");

            String outcome = session.withTransaction(() -> {
                // Driver may re-invoke callback when retrying the full transaction.
                // Do not send emails, call payment gateways, or change requestId here.

                ledger.insertOne(session,
                    new Document("_id", requestId)
                        .append("requestId", requestId)
                        .append("from", "A")
                        .append("to", "B")
                        .append("amount", amount)
                        .append("currency", "UNIT"));

                UpdateResult debit = accounts.updateOne(
                    session,
                    new Document("_id", "A")
                        .append("balance",
                            new Document("$gte", amount)),
                    new Document("$inc",
                        new Document("balance", -amount)));

                if (debit.getMatchedCount() != 1) {
                    throw new IllegalStateException(
                        "Insufficient balance or source not found");
                }

                UpdateResult credit = accounts.updateOne(
                    session,
                    new Document("_id", "B"),
                    new Document("$inc",
                        new Document("balance", amount)));

                if (credit.getMatchedCount() != 1) {
                    throw new IllegalStateException(
                        "Destination account not found");
                }

                return "COMMITTED";
            }, options);

            System.out.println(outcome);

        } catch (MongoException e) {
            System.err.println("MongoDB transaction error: " +
                e.getMessage());

            // If helper could not resolve, DO NOT automatically re-run
            // the business transfer with a new requestId.
            // Reconcile the ledger by requestId with proper read concern.
        }
    }
}
```

### 12.3. Prerequisites for the Example

Before running:

- Database `txn_retry_lab249` already contains documents `A` and `B`.
- Collection `transferLedger249` has unique index `{ requestId: 1 }`.
- Replica set `rsLab` is running and has a primary.
- The URI matches your actual hosts and ports.
- The example uses integer units; real financial systems need proper numeric/decimal models.
- Do not re-run the same `requestId` as a new transfer once the ledger already has a record from a previous run.

### 12.4. Multiple Callback Executions Do Not Mean Multiple Commits

If the first attempt hits `TransientTransactionError` before commit, the driver can:

1. Discard/abort that attempt.
2. Start a new transaction.
3. Re-execute the callback.
4. Commit the successful attempt.

This does not mean uncommitted changes from the first attempt were “left behind” and applied a second time.

If the commit outcome is unknown, the helper can **retry commit** without invoking the callback again. Recognizing this difference is essential.

### 12.5. `withTransaction()` Does Not Make Every HTTP Request Exactly-Once

Suppose `withTransaction()` returns `"COMMITTED"`, but the backend crashes before sending the HTTP response to the frontend. The frontend resends the same API call and the backend invokes a **new** `withTransaction()`:

- The new transaction will not automatically be recognized as a commit retry of the previous transaction.
- If the ledger uses a stable `requestId` and unique index, the new run will hit a duplicate key error.
- The application must **reconcile against the ledger** and return the corresponding result, never swapping `requestId` to transfer again.

Driver retries resolve errors within **a single transaction execution**; business idempotency resolves **independent API calls**.

## 13. Java: Inspecting Error Labels When Orchestrating Manually

When using the **core transaction API** instead of the convenient helper, Java can inspect error labels:

```java
catch (MongoException e) {
    if (e.hasErrorLabel("TransientTransactionError")) {
        // During body execution:
        // Consider retrying the full transaction in a new attempt.
    } else if (e.hasErrorLabel("UnknownTransactionCommitResult")) {
        // During commit phase:
        // Retry commit of the same transaction/session.
    } else {
        // Do not retry blindly.
    }
}
```

This snippet **illustrates classification**, not a complete runnable algorithm. Specifically:

- Do not handle `TransientTransactionError` inside the body by merely re-running the last statement.
- Do not handle `UnknownTransactionCommitResult` by starting a fresh session/transaction.
- Do not wrap an unbounded loop outside `withTransaction()` when the helper already provides retry handling.
- Never equate every network exception with one fixed label; the driver/server determines labels based on specific conditions.

### 13.1. Do Not Inspect Error Messages by Substring Matching

For example:

```java
if (e.getMessage().contains("timeout")) {
    retryWholeTransaction();
}
```

is unreliable. A message containing “timeout” could describe:

- Server selection timeout.
- Network timeout during body execution.
- Write concern timeout during commit.
- Another operation that already completed before the response was lost.

The certainty level and retry strategy differ. Rely on **error labels and driver protocol**, while keeping a business ID for reconciliation when needed.

## 14. Comparing Three Critical Timelines

### 14.1. Timeline A — Transaction Body Hits a Transient Error

```text
T0  Start transaction X
T1  Read balance A = 1000
T2  Debit A inside X
T3  Concurrent update causes write conflict
T4  Driver receives TransientTransactionError
T5  X is aborted / not committed
T6  Start transaction Y
T7  Re-read balance A
T8  Debit + credit + ledger inside Y
T9  Commit Y succeeds
```

At T6, you must **retry the entire body**, not continue using transaction X's state.

### 14.2. Timeline B — Commit Has an Unknown Result

```text
T0  Start transaction X
T1  Debit A inside X
T2  Credit B inside X
T3  Insert ledger inside X
T4  Client sends commit(X)
T5  Server may have committed X
T6  Response lost
T7  Client receives UnknownTransactionCommitResult
T8  Client resends commit(X)
T9  Server returns commit outcome per protocol
```

At T8, **do not re-run the body**. The goal is resolving or completing X's commit.

### 14.3. Timeline C — An HTTP API Request Is Resent

```text
T0  Client sends POST /transfers, requestId=TR-001
T1  Backend runs transaction X
T2  Commit X succeeds
T3  HTTP response lost
T4  Client retries POST /transfers, requestId=TR-001
T5  Backend checks ledger / idempotency key
T6  Returns processed status; does not transfer a second time
```

Here T4 is a **business-layer retry**, not a commit retry of transaction X. That is why **a stable request identifier** checked across requests is required.

## 15. Why Is “Re-Running the Body After `UnknownTransactionCommitResult`” Dangerous?

Suppose initial balances are:

```javascript
{ _id: "A", balance: 1000 }
{ _id: "B", balance: 500 }
```

Transaction X transfers 100:

```text
After commit X:
A = 900
B = 600
```

The client misses the commit response for X, **assumes X failed**, and runs a new transaction Y with the same two `$inc` updates:

```text
After commit Y:
A = 800
B = 700
```

We still have:

```text
A + B = 1500
```

yet the user transferred **200 instead of 100**. The invariant “total money in the system is conserved” is insufficient to detect this bug.

### 15.1. What About a Unique Ledger?

If both X and Y use **the same `requestId`** and insert into the ledger inside the same transaction before modifying balances, Y hits a duplicate key conflict once X has committed. That is a valuable safeguard.

However, upon encountering a duplicate key:

- **Do not automatically treat every duplicate key as success.**
- Read the ledger by `requestId`.
- Verify `from`, `to`, `amount`, `currency`, and status.
- If the payload differs, return conflict instead of transferring.

A stable request ID prevents multiple distinct committed transactions from recording **the same business action twice**, though it does not replace proper commit error classification.

### 15.2. If You Accidentally Generate a New Request ID

If the API retry generates `TR-002` instead of `TR-001`, the unique ledger cannot tell this is the same transfer intent. Both X and Y commit validly in MongoDB while being **wrong for the business**.

Therefore, separate:

```text
Transaction identity managed by the driver
                 +
Business requestId managed by the application
```

The two identifiers prevent **two different kinds of duplication**.

## 16. When Retrying the Full Transaction, Input Data May Change

MongoDB transactions have specific read isolation and concurrency controls. When retrying the body in a **new** transaction, reads must execute again.

Example:

```text
Attempt X:
  Read A = 1000
  Check >= 100 -> Yes
  Hits TransientTransactionError, X does not commit

Meanwhile, another transaction withdraws 950 from A.

Attempt Y:
  Read A = 50
  Check >= 100 -> No
  Y must reject per business rules
```

If the callback captured a variable `balanceAtFirstAttempt = 1000` outside and reused it on retry, it would make decisions on stale state.

### 16.1. Separating Stable Inputs from State That Must Be Re-Read

| Data Category | Standard Rule on Body Retry |
|---|---|
| User's `requestId` | **Keep stable** across attempts |
| Confirmed transfer amount | **Keep unchanged** for the same request |
| Source/destination accounts | **Keep unchanged** for the same request |
| Current balance | **Re-read** in the new transaction |
| Account lock flags | **Re-read** in the new transaction |
| Document version | **Re-read/re-check** via optimistic concurrency |
| Meaningful business timestamp | Explicitly define as request time vs. processing time |
| External email/SMS | Never emit directly inside a retryable body |

This separation preserves business intent while ensuring decisions reflect the current MongoDB state of the new attempt.

## 17. Errors That Must Not Automatically Retry the Full Transaction

### 17.1. Duplicate Keys and Unique Indexes

If the unique ledger already contains the `requestId`, it may mean:

- The previous request already committed successfully.
- A conflicting request reused the same key with a different payload.
- Another actor created the record.

Retrying the full transaction repeatedly will not make the unique constraint disappear. **Reconcile** and decide per business rules.

### 17.2. Validation or Schema Errors

An invalid document, such as `amount: "abc"` when schema requires a number, must be fixed at the source. Retrying the same payload is futile.

### 17.3. Insufficient Balance

If the transaction body observes insufficient funds, that is a business rejection:

```java
if (debit.getMatchedCount() != 1) {
    throw new IllegalStateException("INSUFFICIENT_BALANCE");
}
```

Never auto-retry 50 times hoping the account receives a deposit. If waiting for top-up exists, that is a **different workflow**, not a transient transaction retry.

### 17.4. Permission or Configuration Errors

Missing collection privileges, misconfigured replica sets, invalid sessions, or unsupported server versions must be fixed through **configuration and operations**, not infinite retries.

### 17.5. Retry Deadline Exceeded

A transaction may repeatedly suffer write conflicts under extreme contention. If it cannot finish within a reasonable budget, return an appropriate status and investigate the root cause rather than pinning request threads forever.

### 17.6. Transaction Lifetime Expiration

MongoDB enforces a transaction lifetime limit via server configuration. Transactions held open too long are aborted, wasting resources and worsening conflict resolution. Never put long `sleep` calls or slow HTTP requests inside the transaction body and assume raising retry counts fixes the root cause.

## 18. Transaction Write Concern and Commit Acknowledgment Errors

### 18.1. Setting Write Concern at the Transaction Level

For multi-operation transactions, write concern applies to the **commit** and its associated guarantees; do not assign arbitrary per-operation write concerns inside the body.

Java example:

```java
TransactionOptions options = TransactionOptions.builder()
    .readConcern(ReadConcern.SNAPSHOT)
    .writeConcern(WriteConcern.MAJORITY)
    .readPreference(ReadPreference.primary())
    .build();
```

`mongosh` example:

```javascript
session.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority", wtimeout: 5000 }
});
```

The goal is ensuring commits achieve the acknowledgment level required by system policy.

### 18.2. Write Concern Timeouts Can Create Commit Ambiguity

Suppose:

```text
Transaction body finishes
       |
       v
commitTransaction
       |
       +-- Primary processes commit
       |
       +-- Majority acknowledgment not met before wtimeout
       |
       v
Client receives write concern error / unknown commit result
```

An acknowledgment error does not prove the transaction aborted. When the driver returns `UnknownTransactionCommitResult`, the right action is **retrying commit** per protocol.

### 18.3. `w: 1` and `w: "majority"` Are Not Equivalent

A commit acknowledged with `w: 1` may not provide the durability/replication guarantee critical workflows need. In certain failover scenarios, writes that have not reached majority risk rolling back under deployment guarantees.

**Never equate:**

- “Client received commit success”.
- “Transaction has the durability level required by the business”.

Choose the right write concern **at design time**, then classify retry errors under that policy.

### 18.4. Commit Retries Differ from Single-Document Retryable Writes

Retryable writes for eligible `insertOne`/`updateOne` calls and transaction commit retries both rely on session/protocol tracking, yet **the unit retried is different**.

Never take an example of a retryable `insertOne` and conclude you can replay the whole transaction body after a commit error.

## 19. When Commit Outcome Remains Undetermined

### 19.1. Commit Retries Do Not Always Resolve Immediately

If the primary is lost, the network partitions, or the driver exceeds its deadline, the application may fail to get a definitive commit response for some time.

Instead of returning an arbitrary guess:

```text
COMMITTED
ABORTED / REJECTED
UNKNOWN_OUTCOME
```

allow an explicit **`UNKNOWN_OUTCOME`** state in the business workflow.

### 19.2. Handling After Session Loss or Request Termination

If the application restarts, the old session is no longer available to retry commit directly via the same object. That **does not prove the transaction failed to commit**. Upon recovery:

1. Retrieve the **`requestId`** recorded prior to execution.
2. Read business state from the authoritative source.
3. Verify payload, ledger, and commit indicators.
4. If still undetermined, continue reconciling per policy.
5. Only initiate a new business attempt when justified as a new intent or protected against duplication.

**Never try reconstructing internal protocol session/transaction identities manually** from logs using fields not supported by driver APIs.

### 19.3. Using Majority Reads When Appropriate

If the transaction was expected to commit with majority write concern, reading the ledger from the primary with read concern `majority` can be a useful reconciliation step.

`mongosh` example:

```javascript
db.getSiblingDB("txn_retry_lab249").runCommand({
  find: "transferLedger249",
  filter: { requestId: "TR-249-JAVA-001" },
  limit: 1,
  readConcern: { level: "majority" }
});
```

However, **not finding the ledger on a single read** does not prove the previous transaction “never committed or never executed on the server”. Consider read timing, replication/failover status, in-progress states, network issues, and driver error reporting.

### 19.4. Never Inspect Balances Alone

Two transfers of 100 from A to B change balances predictably, yet if a concurrent transfer sent 100 back in the opposite direction, final balances could look as expected.

Therefore, reconcile via **ledger/`requestId`**, never solely by balance deltas.

## 20. Designing Business Idempotency Alongside Transaction Retries

### 20.1. Assign a Unique Request ID Before the Transaction

A transfer API should accept or generate **one idempotency key per transfer intent**:

```json
{
  "requestId": "TR-2026-000123",
  "fromAccount": "A",
  "toAccount": "B",
  "amount": 100,
  "currency": "UNIT"
}
```

When the frontend retries **the same intent**, reuse `requestId`. When the user genuinely wants to transfer another 100, use a **different request ID**.

### 20.2. Unique Index

```javascript
db.getSiblingDB("txn_retry_lab249")
  .transferLedger249
  .createIndex({ requestId: 1 }, { unique: true });
```

The unique index prevents two ledger records from sharing the same `requestId`. Inserting the ledger **in the same transaction as the balance updates** ensures both commit or abort together under transaction guarantees.

### 20.3. Verify Payload on Duplicate Requests

Suppose the ledger already has:

```javascript
{
  requestId: "TR-001",
  from: "A",
  to: "B",
  amount: 100,
  currency: "UNIT"
}
```

A new request with the same `requestId` but `amount: 500` must not be treated as a valid retry. The API should return a **conflict** or controlled error status, never treating it as a success.

Systems may store a **canonical payload hash** for quick comparison, provided encoding, compared fields, and conflict rules are clearly defined.

### 20.4. Do Not Rely on Duplicate Key Errors Alone

If transaction Y hits a duplicate key because X's ledger already committed, aborting Y is right. To build the final API response, the application must still:

- Read the existing ledger record.
- Confirm it matches **the exact transfer** requested.
- Check committed status and downstream steps.
- Avoid automatically re-triggering external side effects.

### 20.5. Define a Request State Machine

```text
RECEIVED
   |
   v
PROCESSING
   |              \
   |               \  Commit/response uncertain
   v                v
COMPLETED       UNKNOWN_OUTCOME
                     |
                     v
                 RECONCILING
                 /        \
                v          v
           COMPLETED   NEEDS_REVIEW
```

These states are illustrative; real systems must define which transaction updates which state, when, and how crash recovery runs. The goal is never lying to users with “failed” when the server may have committed.

## 21. Emails, Events, and External Payments

### 21.1. External Side Effects Problem

Suppose a callback contains:

```java
session.withTransaction(() -> {
    saveOrder(session);
    chargeCardViaHttp();
    return null;
});
```

If the MongoDB transaction hits a transient error and the callback re-runs, **`chargeCardViaHttp()` can be called twice**, even though the first MongoDB attempt aborted. This causes duplicate charges even while MongoDB transactions behave correctly.

### 21.2. Transactional Outbox

A common solution:

```text
MongoDB transaction:
  - update order
  - write ledger
  - insert outboxEvent { eventId, type, payload }
  - commit

Separate worker:
  - read committed outboxEvent
  - send email / payment event
  - mark processed status
  - consumer deduplicates using eventId
```

An outbox organizes event emission; for true deduplication, **consumers/downstream services also need idempotency or reconciliation**. If the worker crashes after sending and before marking sent, it may send again.

### 21.3. Separating Commit Retries from Side-Effect Retries

Even if the driver only retries `commitTransaction`, an application might have called a payment gateway **before commit**. When commit is unknown, never assume the gateway is also unknown under MongoDB's protocol. Both systems have **separate confirmation mechanisms** and need independent reconciliation.

## 22. Concurrency Issues During Transaction Retries

### 22.1. New Transaction Attempts Must Re-Check Business Preconditions

If a transaction aborts due to a write conflict, the new attempt must not reuse prior reads. Specifically:

- Balances may have changed.
- Order status may have moved from `CREATED` to `CANCELLED`.
- Limits may have been adjusted.
- Documents may have been inserted or deleted.

Re-running the body is not simply **replaying write commands**, but **re-evaluating business decisions against a fresh snapshot**.

### 22.2. Enforcing Conditions via Filters

For example:

```javascript
{
  _id: "A",
  balance: { $gte: 100 }
}
```

used as the debit update filter enforces an invariant directly at write time; if `matchedCount = 0`, the callback must stop and let the transaction abort instead of crediting B anyway.

### 22.3. Transactions Do Not Permit Arbitrary Parallel Operations on One Session

MongoDB drivers do not allow arbitrary parallel operations within **the same transaction/session**. In Java, never spawn multiple threads sharing one `ClientSession` to parallelize debit, credit, and ledger writes.

Commands in the body should execute sequentially on the same session to adhere to the driver contract.

### 22.4. Transaction Duration and Contention

A transaction holding locks/resources for a long time raises conflict and timeout probabilities. Mitigations include:

- Limiting the number of documents/operations per transaction.
- Avoiding network calls or heavy CPU work inside the body.
- Maintaining proper indexes for queries inside transactions.
- Using tight conditional queries and explicit request IDs.
- Tuning retries/backoff only when truly needed, instead of stretching transaction durations.

## 23. Practical Scenario: Body Retries Yield a Different Business Result

Suppose the callback logic is:

```java
session.withTransaction(() -> {
    int available = readInventory(session, sku);

    if (available < quantity) {
        throw new OutOfStockException();
    }

    reserveInventory(session, sku, quantity);
    return "RESERVED";
});
```

On the first attempt, 10 items are available, enough for an order of 8. The transaction aborts due to a conflict. Meanwhile, someone else buys 5 items.

The retried body reads 5 items remaining and throws `OutOfStockException`. That is **not a retry bug**: state changed and the business precondition no longer holds.

If the error was **`UnknownTransactionCommitResult` after the body completed**, the driver must not re-run `readInventory` and `reserveInventory` in a new transaction; it must first resolve the commit outcome of the attempt already executed.

## 24. A Production Retry Loop Needs Bounds and Observability

### 24.1. Bound Both Loops

A system can:

- Retry the transaction a few times on transient errors.
- Retry commit within a time budget when the result is unknown.
- Transition the request to `UNKNOWN_OUTCOME` when the deadline expires.
- Continue reconciling asynchronously via the request ID.

Never pick an arbitrary fixed retry count and assume every transaction finishes within it. Base bounds on expected latency, SLAs, operation criticality, and driver behavior.

### 24.2. What Should Be Logged?

An orchestration log entry might contain:

```javascript
{
  requestId: "TR-001",
  operation: "transferFunds",
  phase: "COMMIT",
  errorLabel: "UnknownTransactionCommitResult",
  transactionAttempt: 1,
  commitAttempt: 2,
  outcome: "UNKNOWN_OUTCOME",
  observedAt: ISODate("2026-11-14T09:00:00Z")
}
```

This is an **application-designed log schema**. MongoDB does not automatically generate these fields.

Do not log credentials, sensitive data, or full request payloads unnecessarily. If logging internal session/transaction fields, follow security policies and be aware of driver stability guarantees.

### 24.3. Metrics and Alerts

| Signal | Operational Question |
|---|---|
| High `TransientTransactionError` | Are there write conflicts, overly long transactions, or frequent failovers? |
| High `UnknownTransactionCommitResult` | Are network, primary health, or write concern delaying commit confirmations? |
| High commit retries | Is latency or replication lag rising? |
| Transaction success rate after retry | Are retries aiding recovery or masking infrastructure problems? |
| `UNKNOWN_OUTCOME` volume | Is there a reconciliation backlog? |
| Duplicate business keys | Are clients resending API calls or is the system double-processing? |
| Replica set lag | Is majority write concern waiting too long? |
| Duplicate side effects | Are outbox/consumers missing idempotency? |

Interpret metrics by **time window, topology, and workload**. A retry spike during failover looks different from a spike caused by concurrent transactions hitting one hot document.

## 25. Common Misconceptions

| Misconception | Correct Understanding |
|---|---|
| Any error in a transaction means re-run the whole body | Separate pre-commit transient errors from commit confirmation errors |
| `UnknownTransactionCommitResult` means rolled back | Server may have already committed; client is uncertain |
| Retrying commit means re-calling debit and credit | Retry **`commitTransaction` itself** for the same transaction |
| Retrying the full transaction reuses the old snapshot | The fresh attempt must re-read data and re-check conditions |
| Calling `abortTransaction` after a commit timeout guarantees rollback | A late abort never undoes a committed transaction |
| Opening a new session and committing counts as a commit retry | Does not preserve transaction identity; not a commit retry |
| `TransientTransactionError` is a permanent data error | Indicates a transient error eligible for transaction retry |
| Every `MongoException` is transient | Duplicate key, validation, auth, or business errors are often non-retryable |
| Driver `withTransaction()` executes the callback only once | The helper can invoke the callback multiple times across retries |
| If callback runs multiple times, MongoDB ensures emails send once | MongoDB does not roll back external side effects |
| Retrying commit means the callback also retries | They are two separate retry loops |
| A new transaction is always a safe retry for an old transaction | Can cause duplicate business actions if the old transaction committed |
| A unique ledger key removes the need to check payloads | Same key with different payload is a business conflict |
| Constant total balance proves no duplicate transfer occurred | Two transfers in one run still conserve total balance |
| Not immediately seeing the ledger means commit didn't happen | Could reflect read concern, replication lag, or read timing |
| Using transactions makes HTTP requests exactly-once | Business idempotency is still needed across independent API calls |
| Retryable writes and transaction retries are the same | Their scope and protocol differ |
| Infinite retries will always resolve incidents | Can exhaust resources or mask configuration failures |
| Outbox guarantees emails never duplicate without consumer logic | Downstream consumers still need idempotency/deduplication |

## 26. Practice Exercises

### Exercise 1 — Error Classification

Consider these scenarios:

1. `updateOne` inside a transaction hits `WriteConflict` and the driver attaches `TransientTransactionError`.
2. Body succeeds, `commitTransaction` throws `UnknownTransactionCommitResult`.
3. Ledger insert hits a duplicate key error.
4. `commitTransaction` returns success.
5. Application server crashes after commit succeeds, before returning the HTTP response.

For each scenario, determine:

- Should the full transaction be retried?
- Should only commit be retried?
- Is reconciliation by business key required?
- Is generating a new request ID allowed?

### Exercise 2 — Choosing the Right Retry Loop

A system has pseudocode:

```text
repeat until success:
    startTransaction()
    debit(100)
    credit(100)
    insertLedger()
    commitTransaction()
```

Identify the risk if the first commit succeeds while the response is lost. Redraw the algorithm with an **outer loop for the transaction body** and an **inner loop for commit**. Add an `UNKNOWN_OUTCOME` branch.

### Exercise 3 — Transient Error After Reading

Transaction attempt X reads balance A as 1000, then hits `TransientTransactionError`. Before the retry runs, another transaction withdraws 950.

- Which balance must the new attempt read?
- Can it keep assuming `balance >= 100` from the earlier attempt?
- If only 50 remains, what should the business logic do?
- How does this differ from X having an unknown commit result?

### Exercise 4 — Unknown Commit Result

Timeline:

```text
12:00:00 start transaction X
12:00:01 debit A
12:00:02 credit B
12:00:03 insert ledger
12:00:04 commit(X) sent
12:00:05 server commits X
12:00:06 network drops response
12:00:07 driver receives UnknownTransactionCommitResult
```

Answer:

1. Can you assert X did not commit?
2. At 12:00:08, what should be resent?
3. Why not create transaction Y to re-run debit/credit?
4. If confirmation cannot finish before the API deadline, what status should be returned?

### Exercise 5 — `withTransaction()` Callback

Inspect:

```java
session.withTransaction(() -> {
    updateInventory(session);
    sendEmail();
    return null;
});
```

- Can the callback be invoked multiple times?
- If the first run sent an email and the transaction aborted, what happens when the body retries?
- Propose an outbox event design with a dedicated `eventId`.
- Why do consumers still need idempotency?

### Exercise 6 — Request ID Outside the Callback

Compare:

```java
session.withTransaction(() -> {
    String id = UUID.randomUUID().toString();
    insertTransfer(session, id);
    return null;
});
```

with:

```java
final String id = incomingRequestId;
session.withTransaction(() -> {
    insertTransfer(session, id);
    return null;
});
```

Explain why the second approach supports reconciliation and business idempotency better. If the client resends the HTTP request using a new ID, what risk remains?

### Exercise 7 — Duplicate Ledger Key

Request `TR-17` transferring 100 from A to B committed. The client resends `TR-17`, but this time with payload amount 300.

- How does the unique index on `requestId` help?
- Should you return “transferred 300 successfully” on duplicate key?
- Which fields must be compared?
- How should the conflict be reported?

### Exercise 8 — Two Transfers, Total Balance Still Matches

A starts at 1000, B starts at 500. Transaction X transfers 100, but the commit response is lost. The app starts transaction Y and transfers another 100.

- Balances after X?
- Balances after Y?
- Total balance before and after?
- Why does checking total balance fail to prove the request executed only once?
- How does a ledger/`requestId` detect the bug?

### Exercise 9 — Non-Retryable Errors

Given three errors:

```text
DuplicateKey
DocumentValidationFailure
TransientTransactionError
```

Classify which can trigger a driver-guided full transaction retry and which require fixing data or business resolution. Why not retry every error every 100 ms until it succeeds?

### Exercise 10 — Read Concern During Reconciliation

The previous commit had an unknown result. The app reads the ledger from a secondary and finds no record.

1. Can you conclude the transaction did not commit?
2. How does replication lag affect this?
3. What signal does reading the primary with read concern `majority` provide?
4. Why is one empty read still not absolute proof that it “never executed”?
5. What state should the request hold while awaiting confirmation?

### Exercise 11 — Designing a Transfer with the Java Sync Driver

Write a Java method:

```java
TransferResult transfer(
    MongoClient client,
    String requestId,
    String from,
    String to,
    long amount
);
```

Requirements:

- Transaction options include snapshot read concern and majority write concern.
- All MongoDB commands in the body share the same session.
- Insert a ledger entry with unique `requestId`.
- Debit A conditionally on sufficient balance.
- Credit B only if debiting A succeeded.
- Use `withTransaction()`.
- Do not send emails inside the callback.
- After an unknown commit exception, do not automatically run a new transaction with a different request ID.

Explain what happens if the driver re-invokes the transaction callback.

### Exercise 12 — Comparing Retryable Writes vs. Transaction Retries

Suppose:

```javascript
db.accounts.updateOne(
  { _id: "A" },
  { $inc: { balance: -100 } }
);
```

and:

```text
startTransaction
  debit A
  credit B
  insert ledger
commit
```

Describe:

- The retry unit for a retryable single-document write.
- The retry unit when a transaction body hits `TransientTransactionError`.
- The retry unit when commit hits `UnknownTransactionCommitResult`.
- Why these three mechanisms cannot be swapped interchangeably.

### Exercise 13 — Operating During an Unstable Network

During a failover, the system logs numerous `TransientTransactionError` and `UnknownTransactionCommitResult` events. Design an incident log table tracking:

- Request ID.
- Phase where error occurred.
- Error label.
- Body retry count.
- Commit retry count.
- Final confirmed outcome.
- Reconciliation status.

Propose deadlines, backoff, metrics, and safeguards against users clicking retry and generating duplicate transfers.

### Exercise 14 — Designing an API with Uncertain Responses

Client sends:

```http
POST /transfers
Idempotency-Key: TR-2026-0001

{"from":"A","to":"B","amount":100}
```

The backend commits successfully, yet the gateway returns a timeout. The client resends the same request.

- What evidence allows the backend to identify this as a retry?
- Should it immediately start a new transaction to debit/credit?
- If a ledger entry with the exact payload already exists, what status should be returned?
- If the ledger cannot be read due to a network outage, should it return `UNKNOWN_OUTCOME`?
- If the same idempotency key arrives with a different amount, how should it be handled?

## 27. Concise Operational Rules

When a MongoDB transaction throws an error, ask in order:

1. **Did the error occur in the body or at commit?** Do not look only at the exception class name.
2. **Is `TransientTransactionError` present?** If it occurred in the body and meets retry conditions, retry **the full transaction** in a new attempt.
3. **Is `UnknownTransactionCommitResult` present at commit?** Retry **the commit of the same transaction**; do not re-run the business body.
4. **Is it duplicate key, validation, or a business rule error?** Do not auto-retry; inspect the cause and business state.
5. **Has the deadline expired or commit stayed unresolved?** Record **`UNKNOWN_OUTCOME`**, keep the request ID unchanged, and reconcile.
6. **Can the API or external side effects be replayed?** Enforce idempotency across independent calls, not only inside the driver.

These are guiding principles, not a substitute for the API docs of your driver and version. When using a convenient transaction API like `withTransaction()`, follow its contract and **avoid stacking an unclassified application-level full-body retry loop on top of it**.

## 28. Summary

**Retrying a full transaction and retrying a commit solve two completely different problems.** When the body hits a transient error preventing the current attempt from committing, you can start a **new transaction** and re-run the full logic. When commit has an unknown result, you must resend **`commitTransaction` of that exact transaction** to clarify or finalize the commit, rather than starting a new business transfer.

**Two error labels to remember:** `TransientTransactionError` typically triggers a full transaction retry; `UnknownTransactionCommitResult` triggers a commit retry. Both must be interpreted according to **error phase, driver semantics, and context**, as not every exception is retryable.

**Transaction atomicity does not equal business exactly-once.** Drivers can retry callbacks, servers can commit before responses are lost, and frontends can replay API calls after HTTP timeouts. Therefore, you need **a stable `requestId`/idempotency key, a unique ledger, payload verification, and reconciliation states**, along with mechanisms like an outbox for external side effects.

**If you do not know whether the commit occurred, do not guess.** Maintain an `UNKNOWN_OUTCOME` state, bound retries, reconcile using an appropriate consistency policy, and never debit or credit a second time automatically. Mastering the difference between **retrying the body** and **retrying the commit** is foundational for building MongoDB transactions that remain safe across write conflicts, failovers, and lost network acknowledgments.
