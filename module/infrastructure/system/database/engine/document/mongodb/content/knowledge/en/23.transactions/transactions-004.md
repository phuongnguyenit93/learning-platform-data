# Read Concern, Write Concern, and Read Preference in MongoDB Transactions

Suppose an application transfers 50 currency units from account A to account B. If the debit succeeds while the credit fails, the system ends up in an invalid state. MongoDB supports **multi-document transactions** to group multiple read/write operations into an atomic unit: either the changes commit together, or the transaction's changes are aborted.

However, merely calling `startTransaction()` leaves key questions unanswered:

- When the transaction reads a balance, **which version of the data** is it allowed to see?
- Once `commitTransaction()` returns success, **how many replica set members must acknowledge** to reduce rollback risk on failover?
- Are reads inside the transaction routed to the **primary or a secondary**?

Three groups of options address these questions:

| Option | Question It Solves | Examples |
| --- | --- | --- |
| **Read concern** | What consistency and snapshot origin apply to data read by the transaction? | `"local"`, `"majority"`, `"snapshot"` |
| **Write concern** | At commit time, what level of write acknowledgment does MongoDB require? | `w: 1`, `w: "majority"`, `j`, `wtimeout` |
| **Read preference** | Which replica set member receives read operations? | `"primary"` in transactions with reads |

This lesson belongs to the **Transactions** chapter of the **Database Engine Document MongoDB** module. It focuses on coordinating these three settings at the **transaction level**, without confusing them with per-statement options or replica set primary election rules.

## 1. Prerequisite: Transactions and Sessions

MongoDB supports multi-document transactions on eligible **replica sets** and **sharded clusters**. A standalone `mongod` is not a full environment for practicing multi-document transactions. In real applications, use a server version, driver, and topology supporting transactions.

A transaction is bound to a **client session**:

```text
Application
   |
   v
ClientSession
   |
   +-- startTransaction(options)
   |      |
   |      +-- read #1 (with session)
   |      +-- update #1 (with session)
   |      +-- update #2 (with session)
   |      +-- insert #3 (with session)
   |
   +-- commitTransaction() or abortTransaction()
   |
   v
End session
```

Three foundational principles:

1. **Every operation belonging to the transaction must use the same session.** An `insertOne()` missing the session argument runs **outside the transaction** and is not protected by `abortTransaction()`.
2. **A session can have at most one open transaction at a time.** Do not run transaction operations concurrently on the same session as if they were independent transactions.
3. **Commit and acknowledgment are two distinct conceptual steps.** A transaction can reach committed state on the primary before the client receives full write concern acknowledgment; an acknowledgment wait error does not prove the transaction was aborted.

MongoDB guarantees atomicity for operations on **a single document** at the document level. Only use multi-document transactions when business logic requires synchronized updates across multiple documents/collections; do not open transactions reflexively for every CRUD command.

## 2. Setting All Three Options at the Transaction Level

A common illustrative configuration:

```javascript
{
  readConcern: { level: "snapshot" },
  writeConcern: {
    w: "majority",
    j: true,
    wtimeout: 10000
  },
  readPreference: { mode: "primary" }
}
```

Meaning:

- `readConcern.level: "snapshot"` requests snapshot mode for the transaction's reads.
- `writeConcern.w: "majority"` requires **commit** acknowledgment at majority level.
- `writeConcern.j: true` adds journaling requirement per server/storage engine capabilities.
- `writeConcern.wtimeout: 10000` caps waiting for write concern at 10,000 ms.
- `readPreference.mode: "primary"` routes the transaction's reads to the primary.

Although configured in one options object, these three settings **do not take effect at the exact same moment**:

```text
startTransaction
      |
      v
  Select read preference / server
      |
      v
  Execute operations using transaction-level read concern
      |
      v
 commitTransaction
      |
      v
  Wait for transaction write concern
      |
      v
  Confirm commit (or classify error)
```

Note that the server may initialize the transaction **lazily** on the first operation after `startTransaction()`; calling start client-side does not necessarily send an immediate open-transaction command to the server.

## 3. Read Concern in Transactions: `local`, `majority`, `snapshot`

**Read concern** describes the consistency guarantees for data read. Inside transactions, supported levels are:

1. `"local"`
2. `"majority"`
3. `"snapshot"`

`"available"` and `"linearizable"` are not valid read concern choices for transactions. Never assume they are “higher” levels and pass them to `startTransaction()`.

### 3.1. `readConcern: "local"`

```javascript
session.startTransaction({
  readConcern: { level: "local" },
  writeConcern: { w: "majority" }
})
```

`"local"` reads data currently present on the node per local read concern semantics; on its own, this level **does not guarantee the read data is majority-committed**, and non-majority-committed data can be rolled back on failover.

Inside a replica set transaction, reads may exhibit stronger isolation, such as observing a snapshot from transaction start depending on server execution. Still, **never equate `"local"` with `"snapshot"` across all topologies**.

Specifically, in a **sharded cluster**, read concern `"local"` does not guarantee that shards serve data from the same point-in-time snapshot. If reports or transactions need a consistent cross-shard snapshot, consider `"snapshot"`.

### 3.2. `readConcern: "majority"`

```javascript
session.startTransaction({
  readConcern: { level: "majority" },
  writeConcern: { w: "majority" }
})
```

Read concern `"majority"` relates to data acknowledged by a majority of replica set members. **Inside a transaction, the guarantee of reading majority-committed data is tied to committing the transaction with write concern `"majority"`.**

If the transaction commits with `w: 1`, merely setting `readConcern: "majority"` **is not enough** to claim reads used majority-committed data under transaction guarantees.

In a **sharded cluster**, even when committing with `w: "majority"`, read concern `"majority"` **does not guarantee that shards are read from the same point-in-time snapshot**. This is a critical distinction when correlating data across two shards inside one transaction.

### 3.3. `readConcern: "snapshot"`

```javascript
session.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" }
})
```

`"snapshot"` is the clear choice when business logic needs reads inside a transaction to observe data from a **consistent snapshot**. When the transaction commits with `w: "majority"`, reads are guaranteed to come from a snapshot of **majority-committed** data.

In a sharded cluster, the transaction snapshot is **synchronized across shards**, unlike `"local"` or `"majority"` read concerns which do not guarantee cross-shard synchronization.

**Do not overlook this condition:** if the transaction commits with `w: 1` instead of `w: "majority"`, read concern `"snapshot"` no longer guarantees that the snapshot read reflects majority-committed data per transaction semantics.

### A Snapshot Is Not Necessarily the Very Latest Data at Every Moment

Example:

```text
t0: Transaction T1 starts, reads balance A = 500
t1: Transaction T2 changes A = 450 and commits
t2: T1 reads A again
```

Using a snapshot, T1 may continue seeing the older state matching its snapshot rather than automatically observing T2's new commit. This gives reads a consistent baseline without guaranteeing that every read inside a transaction always sees **every external update just committed**.

If T1 tries to modify a document that another transaction updated conflictingly, MongoDB can raise a **write conflict** and the transaction must retry per driver rules. `"snapshot"` does not prevent all data contention and should not be treated as strict serializable isolation for every pattern.

### 3.4. Comparing the Three Read Concern Levels

| Level in Transaction | Key Characteristics | In a Sharded Cluster | Commit Note |
| --- | --- | --- | --- |
| `"local"` | Current data on the node; no automatic majority-committed guarantee | Does not guarantee a synchronized snapshot across shards | Do not infer majority guarantees just from choosing `local` |
| `"majority"` | Guarantees reading majority-committed data under transaction conditions | Shards may not share the exact same point-in-time snapshot | Guarantee tied to **committing with `w:"majority"`** |
| `"snapshot"` | Requests a consistent snapshot; suited for multi-document/shard reads | Synchronized snapshot across shards | To guarantee a snapshot of majority-committed data, **commit with `w:"majority"`** |

When choosing, identify the real requirement: do you just need writes to commit atomically together, need to read majority-committed data, or need reads across multiple shards to share **the same point-in-time view**?

## 4. Transaction Read Concern Is Not Per-Read Read Concern

Inside a transaction, **read concern is specified at the transaction level**. Do not pass a different read concern to `find()`, `aggregate()`, or an individual read operation inside a transaction.

Example of proper configuration:

```javascript
session.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" }
})

// Reads via the session's database handle use
// the transaction's read concern.
const account = sessionDb.accounts.findOne({ _id: "A" })
```

A method or collection handle with its own read concern **cannot override the transaction-level read concern**. In drivers, a transaction's read concern can inherit from session/client defaults if not set explicitly, but per-operation read concerns inside a transaction cannot be used to switch read levels mid-transaction.

### Understanding the Inheritance Order

In MongoDB drivers, when read concern is omitted at the transaction level, it generally inherits as follows:

```text
transaction-level read concern (if set)
          |
          v
session default transaction options (if set)
          |
          v
client-level read concern / configured default
```

Read concern on a collection or database **cannot override transaction-level read concern**. MongoDB documentation specifies that operations inside a transaction use the transaction-level read concern; do not expect changing a collection handle from `majority` to `local` to give individual reads inside a transaction different read levels.

## 5. When Does Write Concern Apply in a Transaction?

Unlike read concern, **transaction-level write concern applies at commit time**, rather than as an independent write concern on each `insertOne()` or `updateOne()` inside the transaction.

```text
startTransaction(writeConcern = majority)
        |
        +-- update accounts[A]
        +-- update accounts[B]
        +-- insert transfers
        |
        v
commitTransaction()
        |
        v
MongoDB acknowledges commit per transaction-level write concern
```

**Do not pass an individual `writeConcern` to write commands inside a transaction.** Drivers/servers can raise errors if you try to assign a per-operation write concern inside a transaction.

### 5.1. Committing with `w: 1`

```javascript
session.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: 1 }
})
```

`w: 1` requests acknowledgment once the commit is applied on the **primary**. If the primary fails before the commit is majority-replicated, the transaction's changes **can be rolled back during failover**.

Important distinction:

- The transaction remains atomic: it will not intentionally “debit account A and forget B”.
- However, a commit acknowledged only by the primary may **not survive a failover** if not yet majority-committed.
- If pairing `readConcern: "majority"` or `"snapshot"` with `w: 1` commit, you cannot claim the majority-committed read guarantees that apply to majority commits.

### 5.2. Committing with `w: "majority"`

```javascript
session.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: {
    w: "majority",
    wtimeout: 10000
  }
})
```

`w: "majority"` requires the commit to be acknowledged by a majority of the replica set. In normal replica set transactions, this is essential when reducing the risk of acknowledged writes rolling back on a primary change.

In sharded transactions, committing can involve multiple steps and coordination across shards; MongoDB performs internal majority/journaling steps in distributed commits. Never oversimplify this whole process as “just sending one command to one primary”.

### 5.3. `j` and `wtimeout` at Commit

```javascript
{
  writeConcern: {
    w: "majority",
    j: true,
    wtimeout: 8000
  }
}
```

- `j: true`: requests acknowledgment satisfying the **journal** condition per storage engine/configuration. It does not replace majority replication.
- `wtimeout: 8000`: limits how long to **wait for write concern** (milliseconds). It does not force all network/driver timeouts and total transaction execution time to be eight seconds.
- If write concern is not met in time, a **write concern error** can occur. That alone does not prove the transaction failed to commit or rolled back.

Across MongoDB versions, settings like `writeConcernMajorityJournalDefault` affect journaling behavior with `w: "majority"`; verify your target version and settings rather than assuming a single journal rule for every deployment.

### 5.4. `w: 0` Is Unsuitable for Transactions

Multi-document transactions require acknowledged commits; the MongoDB Java Driver rejects **unacknowledged write concern** for transactions. Never use `WriteConcern.UNACKNOWLEDGED` or `{w:0}` to boost transaction throughput.

If a workload only needs best-effort logging without acknowledgment, use an appropriate standalone write path rather than combining `w:0` with a multi-document transaction.

### 5.5. Do Not Change Write Concern Mid-Transaction

A transaction keeps its options from when it starts. There is no concept of “writing account A with `w:1`, then writing account B with `w:majority` in the same transaction” via per-operation write concerns. The commit level determines how **the entire transaction** is acknowledged.

## 6. Commit Timeouts and Unknown State

This scenario must be handled carefully in every critical transaction:

```text
Client                          MongoDB
  |                               |
  | commitTransaction             |
  |------------------------------>|
  |                               | Apply commit decision
  |                               | Wait for majority acknowledgment
  |     network error or timeout  |
  |<------------------------------x
  |
  v
Client CANNOT conclude from timeout:
    "Definitely aborted"
    or "Definitely did not transfer money".
```

Distinguish **two error categories**:

1. **`TransientTransactionError`**: certain errors allow **re-running the entire transaction** per driver guidance, because the current transaction cannot proceed as intended.
2. **`UnknownTransactionCommitResult`**: the commit outcome is unknown to the client; the standard handling is **retrying the commit step of the same transaction**, rather than automatically initiating a brand-new transfer.

MongoDB drivers offer callback APIs like `withTransaction()` to manage common retry cases. Because callbacks can be **invoked again**, never send emails, deduct balances in an external system, or call non-idempotent payment APIs directly inside the callback without deduplication.

**A write concern timeout is not a rollback command.** If the transaction committed while the client missed the ACK, starting **a new transaction** with the same intent without an idempotency key can transfer money twice. Designing a unique `transferId` and checking transaction status is a business requirement independent of read/write concern.

## 7. Read Preference in Transactions: Why `primary` Matters

Normally, **read preference** lets the MongoDB driver route read queries to the primary or secondaries, such as:

```text
primary
primaryPreferred
secondary
secondaryPreferred
nearest
```

However, **transactions containing read operations must use read preference `primary`**. Operations within a transaction must route consistently to the appropriate member per transaction rules. You cannot use `readPreference: "secondary"` to offload the primary while keeping read/write transactions unchanged.

### 7.1. Valid Example

```javascript
const session = db.getMongo().startSession({
  readPreference: { mode: "primary" }
});
```

When a transaction starts on that session, reads will not be dispatched to an arbitrary secondary. In the Java Driver, configure explicitly on `TransactionOptions`:

```java
.readPreference(ReadPreference.primary())
```

### 7.2. Invalid Example

```javascript
// Illustrates an invalid configuration only
const session = db.getMongo().startSession({
  readPreference: { mode: "secondary" }
});

session.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" }
});

// A read operation inside a transaction with secondary read preference
// can be rejected by the driver or server.
```

Read concern `"snapshot"` **does not bypass the transaction read preference constraint**. The two options govern different aspects: snapshot defines **which data state**, while `primary` defines **which member serves reads**.

### 7.3. Read Preference Inheritance Behavior

When a transaction does not specify its own read preference:

```text
transaction-level read preference
           |
           v
session-level read preference
           |
           v
client-level read preference
           |
           v
default = primary (unless configured otherwise)
```

Suppose a service creates a `MongoClient` with `readPreference=secondaryPreferred` for reporting outside transactions. If a transaction session inherits this read preference without overriding it, reads inside the transaction may be rejected. **Fix at the transaction level:** set `ReadPreference.primary()` explicitly rather than depending on read-only client defaults.

### Can Read-Only Transactions Arbitrarily Read Secondaries?

Do not assume “read-only, no writes” always allows `secondary` inside a transaction. Under the transaction read preference rule above, **a transaction containing read operations must use `primary`**. If your sole goal is offloading the primary with secondary reads, run reads **outside multi-document transactions** using appropriate read preference/read concern instead of turning every report into a transaction.

## 8. Matrix of Combining the Three Settings

Assume the transactions below perform read operations with read preference `primary`.

| Read Concern | Write Concern at Commit | Read Preference | Notable Guarantee / Limitation |
| --- | --- | --- | --- |
| `local` | `w:1` | primary | Minimal acknowledgment requirements; reads do not guarantee majority, commit risks rollback on failover |
| `local` | `w:"majority"` | primary | Commit is majority-acknowledged; local read concern still does not provide a consistent cross-shard majority snapshot |
| `majority` | `w:1` | primary | **No** transaction-level guarantee that reads are majority-committed |
| `majority` | `w:"majority"` | primary | Reads from majority-committed data per transaction semantics; **does not** synchronize one snapshot across shards |
| `snapshot` | `w:1` | primary | Uses snapshot mechanics, yet **no guarantee** reads come from a majority-committed snapshot |
| `snapshot` | `w:"majority"` | primary | Majority-committed snapshot; on sharded clusters, snapshot is synchronized across shards |
| `snapshot` | `w:"majority"` | secondary | **Invalid** for transactions containing read operations |

This table does not imply every valid combination has identical latency. `snapshot`, journaling, majority replication, shard placement, and write contention all affect cost. More importantly, choose settings only after defining the application's **durability**, **read consistency**, **fault tolerance**, and **performance** requirements.

## 9. Hands-On: Money Transfer Transaction Between Two Documents

This example uses the practice database `mongo_transaction_concern_lab` on an eligible replica set or sharded cluster. Never run against a database holding real money. Preparation commands must run **outside the transaction**.

```javascript
use mongo_transaction_concern_lab

db.accounts.insertMany([
  {
    _id: "A",
    owner: "An",
    balance: NumberDecimal("500.00"),
    currency: "VND"
  },
  {
    _id: "B",
    owner: "Binh",
    balance: NumberDecimal("100.00"),
    currency: "VND"
  }
])

db.createCollection("transfers")
```

Initial balances:

| Account | Balance |
| --- | ---: |
| A | 500.00 |
| B | 100.00 |
| **Total** | **600.00** |

Goal: transfer `50.00` from A to B while inserting a transaction history document with `_id: "transfer-001"`. After a successful commit, A has `450.00`, B has `150.00`, and the total remains `600.00`.

### 9.1. Open Session and Configure Transaction

```javascript
const session = db.getMongo().startSession({
  readPreference: { mode: "primary" }
});

const txDb = session.getDatabase(
  "mongo_transaction_concern_lab"
);

session.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: {
    w: "majority",
    j: true,
    wtimeout: 10000
  }
});
```

This is the session handle obtained from the MongoDB connection. **Every command below must use `txDb`**, never falling back to regular `db.accounts` and accidentally writing outside the transaction.

### 9.2. Perform Changes Inside the Transaction

```javascript
// 1. Deduct only if A has sufficient balance
const debit = txDb.accounts.updateOne(
  {
    _id: "A",
    balance: { $gte: NumberDecimal("50.00") }
  },
  { $inc: { balance: NumberDecimal("-50.00") } }
);

if (debit.matchedCount !== 1) {
  throw new Error("Account A has insufficient balance");
}

// 2. Credit account B
const credit = txDb.accounts.updateOne(
  { _id: "B" },
  { $inc: { balance: NumberDecimal("50.00") } }
);

if (credit.matchedCount !== 1) {
  throw new Error("Account B does not exist");
}

// 3. Record history in the same transaction
txDb.transfers.insertOne({
  _id: "transfer-001",
  from: "A",
  to: "B",
  amount: NumberDecimal("50.00"),
  status: "committed",
  createdAt: new Date()
});
```

These commands illustrate only the **happy path**. If any operation fails **before commit**, the transaction must be aborted (or handled by an abort-managing helper); never continue committing the remaining operations as if no error occurred.

### 9.3. Commit and End Session

```javascript
session.commitTransaction();
session.endSession();
```

Once the commit is confirmed under the configured options, all three changes belong to one transaction. To inspect data post-commit, use a regular read session:

```javascript
db.accounts.find(
  {},
  { _id: 1, balance: 1 }
).sort({ _id: 1 });

db.transfers.findOne({ _id: "transfer-001" });
```

**Important:** The `mongosh` snippets in 9.1–9.3 are split apart so learners can see each step clearly; they are **not a production error-handling structure**. If an exception occurs after `startTransaction()`, abort when appropriate and always release the session in `finally`. If `commitTransaction()` returns an unknown outcome, **do not blindly replay the entire transfer logic in a new session**; use driver transaction/retry helpers and a unique operation ID. Do not re-run the example on the same data without resetting the lab dataset in a controlled way.

## 10. Why Can a Transaction Read Its Own Writes?

Inside a transaction, if you update A's balance and then read A **using the same session and transaction**, the read sees the uncommitted modification of that transaction itself:

```javascript
// Used inside the transaction before commit
const currentA = txDb.accounts.findOne({ _id: "A" });
printjson(currentA.balance);
```

This does not mean another client outside the transaction can read those uncommitted changes. While the transaction is open, its writes are not exposed externally as committed data.

```text
Transaction T:
    update A: 500 -> 450
    read A inside T -> sees T's change
    update B: 100 -> 150

Client outside T:
    before commit -> does not see uncommitted changes
    after commit  -> sees data per read policy and timing
```

**Read-your-own-writes inside a transaction** must not be confused with `readConcern: "majority"` or `"snapshot"`: one describes **seeing the transaction's own modifications**, while the other describes **guarantees on the snapshot read from the system**.

## 11. Transactions and Read Preference Outside Transactions

Outside transactions, an application may use:

```javascript
db.getMongo().setReadPref("secondaryPreferred")
```

to serve reports with looser freshness requirements, or create a separate client with `ReadPreference.secondary()`. However, for transactions containing read operations, that setting does not turn secondaries into supported transaction execution targets.

A common architecture is:

```text
                         APPLICATION
                             |
           +-----------------+-----------------+
           |                                   |
           v                                   v
   Transfer Transaction                 Analytics Report
   readPref = primary                   readPref = secondaryPreferred
   readConcern = snapshot               readConcern = majority/local
   commit writeConcern = majority       Reads outside transaction
```

Separating these paths prevents accidentally inheriting reporting read preferences into transactions. If a multi-document report needs a consistent snapshot, evaluate non-transaction snapshot reads on supported versions and operations rather than opening long transactions by default.

## 12. Sharded Cluster Case: Why Does Read Concern Matter More?

On a single replica set, documents reside within the same replica set. In a sharded cluster, a transaction may read/write data across multiple distinct shards:

```text
        Transaction T
           /    \
          /      \
      Shard A   Shard B
      accounts  transfers
          \      /
           \    /
     Commit coordination
```

Three key points:

1. **`"local"`** does not guarantee shards return data from the same point in time.
2. **`"majority"`** can guarantee majority-committed data when committing with `w:"majority"`, yet shards may still present different point-in-time views.
3. **`"snapshot"`** provides a synchronized snapshot across shards per transaction semantics, with majority-committed guarantees when committing with `w:"majority"`.

### Example of Two Coupled Reads

A transaction reads total inventory on shard A and the reservation table on shard B. If both sources are only valid when observed at **the same point in time**, `readConcern:"snapshot"` expresses that intent better than `"majority"`, which does not guarantee cross-shard snapshot synchronization.

However, a snapshot **does not lock every document to block concurrent writes**. A transaction can read older data; under update contention, handle write conflicts or apply domain-appropriate synchronization techniques.

### Never Promise External Clients See Commits Simultaneously on Every Shard

A committed distributed transaction is atomic for its own changes. However, for reads **outside the transaction** using unsuitable read concerns, a client may observe updates appearing at slightly different times across shards while results become visible. Never infer from `commitTransaction()` succeeding that **every local read on every shard** instantaneously sees the exact same state.

When the system requires synchronized cross-shard observation, select matching read concerns and read mechanisms.

## 13. Java MongoDB Sync Driver Example with `TransactionOptions`

In Java, `TransactionOptions` bundles all three transaction-level decisions. With the synchronous driver:

```java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;

import java.util.concurrent.TimeUnit;

TransactionOptions options = TransactionOptions.builder()
    .readConcern(ReadConcern.SNAPSHOT)
    .writeConcern(
        WriteConcern.MAJORITY
            .withJournal(true)
            .withWTimeout(10, TimeUnit.SECONDS)
    )
    .readPreference(ReadPreference.primary())
    .build();
```

Conceptually equivalent to:

```javascript
{
  readConcern: { level: "snapshot" },
  writeConcern: {
    w: "majority",
    j: true,
    wtimeout: 10000
  },
  readPreference: { mode: "primary" }
}
```

**Do not** set an individual write concern on each `updateOne(session, ...)` inside the transaction. Even if the collection handle has a default write concern, the transaction still uses the **transaction-level write concern at commit**; never assume each individual update is majority-acknowledged before commit.

### 13.1. Complete Java Code: Transfer Using Callback API

The example below implements the workflow from Section 9 using the Java Sync Driver. It assumes `accounts` and `transfers` already exist outside the transaction, accounts A and B have `Decimal128` balances, and no document `transfer-java-001` exists yet.

```java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;
import org.bson.types.Decimal128;

import java.math.BigDecimal;
import java.util.Date;
import java.util.concurrent.TimeUnit;

public class MoneyTransferTransaction {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Missing MONGODB_URI");
        }

        Decimal128 amount =
            new Decimal128(new BigDecimal("50.00"));
        Decimal128 negativeAmount =
            new Decimal128(new BigDecimal("-50.00"));

        TransactionOptions options = TransactionOptions.builder()
            .readConcern(ReadConcern.SNAPSHOT)
            .writeConcern(
                WriteConcern.MAJORITY
                    .withJournal(true)
                    .withWTimeout(10, TimeUnit.SECONDS)
            )
            .readPreference(ReadPreference.primary())
            .build();

        try (MongoClient client = MongoClients.create(uri);
             ClientSession session = client.startSession()) {

            MongoDatabase db =
                client.getDatabase("mongo_transaction_concern_lab");
            MongoCollection<Document> accounts =
                db.getCollection("accounts");
            MongoCollection<Document> transfers =
                db.getCollection("transfers");

            String transferId = "transfer-java-001";

            session.withTransaction(() -> {
                UpdateResult debit = accounts.updateOne(
                    session,
                    Filters.and(
                        Filters.eq("_id", "A"),
                        Filters.gte("balance", amount)
                    ),
                    new Document("$inc",
                        new Document("balance", negativeAmount))
                );
                if (debit.getMatchedCount() != 1) {
                    throw new IllegalStateException(
                        "Account A has insufficient balance");
                }

                UpdateResult credit = accounts.updateOne(
                    session,
                    Filters.eq("_id", "B"),
                    new Document("$inc",
                        new Document("balance", amount))
                );
                if (credit.getMatchedCount() != 1) {
                    throw new IllegalStateException(
                        "Account B not found");
                }

                transfers.insertOne(session,
                    new Document("_id", transferId)
                        .append("from", "A")
                        .append("to", "B")
                        .append("amount", amount)
                        .append("status", "committed")
                        .append("createdAt", new Date())
                );

                return transferId;
            }, options);

            System.out.println("Transaction completed");
        }
    }
}
```

Explanation of key parts:

- `session.withTransaction(callback, options)` lets the driver initialize, commit/abort, and apply retry rules for eligible transaction errors.
- Every write receives **`session`** as its first argument.
- All three updates share the transaction-level **read concern, write concern, and read preference**.
- The `balance >= amount` condition avoids overdrawing at update time; concurrent transactions may trigger write conflicts handled via the retry policy.
- `transferId` acts as a unique business key. If **a new transaction** runs with the same ID after the first committed, the unique key blocks duplicate history, though the app must still handle duplicates per business rules.

**Note on `withTransaction`:** the callback may be re-invoked by the driver on certain transient errors. Never charge external fees, send emails, or emit irreversible events inside the callback unless guarded by idempotency. This code is for lab practice only; real financial systems require proper ledgers, deduplication, and comprehensive error handling.

### 13.2. Wrong Example: Forgetting to Pass `session`

```java
session.withTransaction(() -> {
    accounts.updateOne(
        Filters.eq("_id", "A"),
        new Document("$inc", new Document("balance", negativeAmount))
    );

    // ...
    return null;
}, options);
```

The `updateOne()` call above **omits `session`**. It runs as a regular standalone write **outside the transaction**, so if the rest of the callback fails, that write does not roll back with the transaction.

The correct way is:

```java
accounts.updateOne(
    session,
    Filters.eq("_id", "A"),
    new Document("$inc", new Document("balance", negativeAmount))
);
```

### 13.3. Wrong Example: Configuring a Collection to Change Concern Mid-Transaction

Never do this to try changing read concern for one statement inside a transaction:

```java
MongoCollection<Document> oneCollection =
    accounts.withReadConcern(ReadConcern.LOCAL);

oneCollection.find(session, Filters.eq("_id", "A")).first();
```

The effective read concern for operations in a transaction comes from **transaction-level configuration**, not a separate `local` level set on a collection handle to override mid-flight.

Likewise, never call `withWriteConcern(WriteConcern.W1)` on a collection to “relax requirements” for one write inside a transaction configured for majority commit.

## 14. `mongosh` Example: Three Configurations Leading to Three Guarantees

Suppose a replica set P–S1–S2 has three data-bearing voting members. The system runs the same workflow in three separate test setups:

### Case A — `local` + commit `w:1`

```javascript
{
  readConcern: { level: "local" },
  writeConcern: { w: 1 }
}
```

Prioritizes primary acknowledgment, but does not guarantee a snapshot of majority-committed data, and commits can roll back on failover.

### Case B — `majority` + commit `w:"majority"`

```javascript
{
  readConcern: { level: "majority" },
  writeConcern: { w: "majority" }
}
```

Majority-committed read guarantees pair with majority commit. However, when data spans multiple shards, `"majority"` does not guarantee a **time-synchronized** snapshot across shards.

### Case C — `snapshot` + commit `w:"majority"`

```javascript
{
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority", j: true },
  readPreference: { mode: "primary" }
}
```

This illustrates the configuration for transactions needing a consistent snapshot and majority commit acknowledgment. It still does not eliminate issues such as stale snapshots relative to newer external commits, write conflicts, transaction timeouts, or the need for idempotency.

**No combination of options automatically turns a transaction into a complete payment system.** ACID transactions organize atomic writes inside MongoDB; for side effects outside MongoDB, applications still need patterns such as outbox, idempotency keys, and reconciliation.

## 15. Distinguishing Snapshot Reads from Data Locking

A common misconception is that using `readConcern:"snapshot"` means MongoDB locks every document the transaction reads and blocks other transactions from modifying them.

That is **false**. Snapshot isolation allows a transaction to observe a consistent version of data; it does not prevent other transactions from modifying documents that were merely read. Example scenario:

```text
T1: reads account document A in snapshot
T2: updates account A and commits
T1: tries to update A based on old snapshot
    |
    v
  May hit write conflict -> must retry transaction
```

If business logic must enforce a condition on current data, use **conditional writes**, version checks, or appropriate locking/update techniques. For example:

```javascript
txDb.accounts.updateOne(
  {
    _id: "A",
    balance: { $gte: NumberDecimal("50.00") }
  },
  { $inc: { balance: NumberDecimal("-50.00") } }
)
```

is a conditional update, not just reading and deciding to deduct based on a value that might have changed.

### Stale Reads Can Occur Inside a Transaction

Because snapshots stay pinned, long transactions can read state that is stale relative to newer commits from other transactions. In cases where you must force a document to be locked/updated to protect an invariant, MongoDB documents patterns such as `findOneAndUpdate()` to perform a write and acquire the relevant lock. Evaluate this by business need, as it creates writes and contention; never use it merely to “refresh every snapshot”.

## 16. Transactions Do Not Automatically Guarantee Consistent External Reads

Suppose a transaction updates A and B and commits with `w:"majority"`. Another client reading from a secondary may still see old state depending on read preference, read concern, and replication lag.

```text
             T1 commit majority
                     |
          +----------+-----------+
          |                      |
     Read primary           Read secondary
   per read concern         which may lag
          |                      |
     State depends on       State depends on
     timing / concern       timing / concern
```

Majority write concern confirms commit durability; it **does not force every secondary to immediately return the latest version**. Coordinate read concern, read preference, and sessions on **subsequent reads** when the application requires read-your-writes or causal consistency.

Outside transactions, non-`primary` read preferences can be valid when the business tolerates stale reads. Inside transactions, read preference follows the specific rules in Section 7.

## 17. Notable Operational Limits

### 17.1. Long Transactions Increase Overhead

Long transactions hold snapshots and storage resources longer than necessary, increasing cache pressure and write conflict rates. MongoDB enforces transaction time limits; `transactionLifetimeLimitSeconds` typically defaults to 60 seconds in standard setups, though it can vary or be tuned per version and deployment.

Never hold a transaction open while calling HTTP APIs, waiting for user form input, or running multi-minute reports. Precompute whatever can be computed outside the transaction, keeping only the reads/writes that require atomicity inside.

### 17.2. Do Not Run Parallel Operations Within the Same Transaction

Never have multiple threads operate concurrently on one `ClientSession` or run arbitrary parallel batches inside one transaction. MongoDB drivers enforce serialization rules on session/transaction operations. With the Java Sync Driver, execute operations **sequentially** inside the callback.

### 17.3. Certain Commands Are Invalid Inside Transactions

You cannot arbitrarily run every command (such as certain administrative/DDL operations or aggregations with `$out`/`$merge`) inside a transaction like regular CRUD. When explicitly creating collections/indexes inside a transaction on supported versions, read concern restrictions apply, including requiring `"local"` for explicit creation. Verify documentation for your version, collection type, and sharding setup.

### 17.4. Never Substitute Majority Commits for Backups

Majority commits reduce rollback risk during failovers per protocol. They do not protect against human error, accidental deletion of committed data, simultaneous loss of multiple failure domains, or point-in-time recovery requirements. Backup and recovery are a separate architectural layer.

### 17.5. `wtimeout` Differs from Transaction Lifetime and Commit Deadlines

`wtimeout` belongs to write concern; it is not the maximum duration of the entire transaction callback. Drivers may also have transaction timeouts or `maxCommitTimeMS` depending on API/version, alongside server transaction lifetime limits. When investigating timeouts, identify **which layer timed out** rather than blindly increasing every timeout parameter.

## 18. Common Misconceptions

| Misconception | Why Is It Wrong? | Correct Understanding |
| --- | --- | --- |
| “Transactions don't need read concern” | Read level determines what data may be observed | Choose `local`, `majority`, or `snapshot` per requirements |
| “`majority` read concern always guarantees majority reads in transactions” | Guarantee depends on committing with `w:"majority"` | Check both read concern **and** commit write concern |
| “`snapshot` guarantees majority-committed data even with `w:1` commit” | Majority commit condition is essential | Pair `snapshot + majority` when that guarantee is needed |
| “`majority` provides a synchronized cross-shard snapshot” | Majority does not align point-in-time views across shards | Use `snapshot` for a synchronized cross-shard view |
| “Can read secondaries in a transaction to offload the primary” | Transactions with reads require `primary` read preference | Move secondary reporting outside transactions when appropriate |
| “Collection-level read concern overrides the transaction” | Transactions use transaction-level read concern | Configure at session/transaction level |
| “Can set `w:1` for update A and `w:majority` for update B in one transaction” | Per-operation write concern is unsupported in transactions | Set transaction-level write concern at commit |
| “Every update in a transaction is majority-acked before commit” | Write concern applies at commit time | Distinguish internal writes from commit acknowledgment |
| “`commitTransaction` timeout means the transaction aborted” | Commit may have succeeded while ACK was lost/delayed | Distinguish unknown commit from abort |
| “Callback retries are always safe for any operation” | Callbacks can execute multiple times | Avoid non-idempotent external side effects inside callbacks |
| “Forgetting to pass session to one update is harmless” | That update can run outside the transaction | Pass the same session to every operation |
| “Snapshots always contain the absolute latest data” | Snapshots can be stale relative to concurrent writes | Handle stale reads and write conflicts |
| “Use `j:true` instead of majority replication” | Journaling and replica acknowledgment are different guarantees | Combine according to durability goals |
| “Client-level `readPreference:secondaryPreferred` works fine in transactions” | Transactions with reads must use primary | Override `ReadPreference.primary()` on the transaction |
| “Multi-document transactions replace good document design” | Transactions carry operational overhead and limits | Prefer single-document atomicity when data modeling fits |

## 19. Practice Exercises

### Exercise 1. Choosing Read Concern to Synchronize Time Across Shards

A transaction reads two datasets on two different shards. The report must rely on **the same point-in-time view** and guarantee a snapshot of majority-committed data.

**Answer:** Use read concern `"snapshot"` at the transaction level and commit with write concern `w:"majority"`. Read concern `"majority"` does not guarantee a synchronized snapshot across shards.

### Exercise 2. Spotting the Flaw in Commit Configuration

```javascript
session.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: 1 }
})
```

The developer claims: “Because we used snapshot, the transaction definitely reads a majority-committed snapshot and the commit cannot roll back on failover.”

**Answer:** Incorrect conclusion. With a `w:1` commit, snapshot read concern **does not guarantee a majority-committed snapshot** per MongoDB documentation. The commit is acknowledged only by the primary and can still roll back if it has not reached majority before failover.

### Exercise 3. Misplaced Write Concern

```javascript
session.startTransaction({
  readConcern: { level: "snapshot" }
})

txDb.accounts.updateOne(
  { _id: "A" },
  { $inc: { balance: -10 } },
  { writeConcern: { w: "majority" } }
)
```

What is wrong?

**Answer:** Do not specify a separate write concern on an individual update command inside a transaction. Declare `writeConcern: {w:"majority"}` at the **transaction level** on start so MongoDB applies it at commit.

### Exercise 4. Inherited Read Preference from Client

An application uses a `MongoClient` with `secondaryPreferred` read preference for reporting. It reuses the same client to open a transaction performing `findOne()` and `updateOne()`, without specifying a read preference on the transaction.

**Answer:** Transactions containing read operations must use `primary`. If `secondaryPreferred` is inherited, the driver may reject reads inside the transaction. Specify `ReadPreference.primary()` in `TransactionOptions` or use an appropriately configured session/client.

### Exercise 5. Commit Timeout and Retry Handling

An application transfers money in a transaction, calls `commitTransaction()`, and receives an error labeled `UnknownTransactionCommitResult`. Should it immediately start a new transaction and debit again?

**Answer:** No. The commit of the previous transaction may have succeeded. Retry **the commit of the same transaction** per driver guidance, or use `withTransaction` alongside business idempotency. Never initiate a new transfer without checking/deduplicating.

### Exercise 6. Distinguishing `local`, `majority`, and `snapshot`

Match each requirement to the right level:

1. Only needs data currently on the node, without majority guarantee.
2. Needs majority-committed read guarantees when committing the transaction with majority.
3. Needs a synchronized snapshot when reading data across multiple shards and committing with majority.

**Answer:** (1) `local`; (2) `majority`; (3) `snapshot`.

### Exercise 7. Java: Which Operation Runs Outside the Transaction?

```java
session.withTransaction(() -> {
    accounts.updateOne(session, Filters.eq("_id", "A"), debit);
    accounts.updateOne(Filters.eq("_id", "B"), credit);
    return null;
}, options);
```

**Answer:** The update on B **omits `session`**, so it can run outside the transaction. Use `accounts.updateOne(session, Filters.eq("_id","B"), credit)`.

### Exercise 8. Does Snapshot Lock All Read Data?

T1 starts a snapshot transaction and reads account A. T2 modifies A and commits. T1 continues and attempts to update A. Can you guarantee T1 will always succeed in updating because it read a snapshot?

**Answer:** No. T1 may be reading stale data and hit a **write conflict** when updating. Handle transaction retries and use appropriate update conditions to enforce business rules.

### Exercise 9. Read-Your-Own-Writes Inside a Transaction

T1 updates A from 500 to 450 without committing yet. T1 reads A using the same session; client B outside the transaction reads A at that exact moment. What can be concluded?

**Answer:** T1 sees its own uncommitted change inside the transaction. Client B does not see T1's uncommitted modification as published data; B's read result depends on committed state and read policy. These two behaviors do not contradict each other.

### Exercise 10. Configuration for a Money Transfer Operation

You need to transfer money between two accounts in the same replica set; reading balances must rely on a majority-committed snapshot and changes must be majority-acknowledged at commit. Propose the three options.

**Reference Answer:**

```javascript
{
  readConcern: { level: "snapshot" },
  writeConcern: {
    w: "majority",
    j: true,
    wtimeout: 10000
  },
  readPreference: { mode: "primary" }
}
```

`j:true` and `wtimeout` should be chosen based on journal settings, latency, and real error-handling needs. Beyond these three options, the business flow still needs idempotency, balance checks, write conflict handling, and safe retries.

## 20. Transaction Implementation Checklist

When writing MongoDB transactions in an application, check these questions:

1. **Is a multi-document transaction really needed?** A single document holding related data may already satisfy atomicity.
2. **Connected to a supported replica set or sharded cluster?** Standalone instances cannot substitute for real transaction environments.
3. **Do all operations use the same session?** No write command accidentally runs outside the session due to a missing parameter.
4. **Is read concern configured on the transaction?** Choose only `local`, `majority`, or `snapshot` matching required semantics.
5. **If a majority-committed snapshot is required, does commit use `w:"majority"`?** Never pair `snapshot` with `w:1` and claim majority-committed guarantees.
6. **Is read preference `primary`?** Especially important when reporting clients default to reading from secondaries.
7. **Is write concern set on the transaction, not individual commands?** Verify `w`, `j`, and `wtimeout` at commit.
8. **Are unknown commit errors handled?** Distinguish `UnknownTransactionCommitResult` from errors requiring full transaction retries.
9. **Does the callback contain external side effects?** If so, use idempotency/outbox since callbacks can retry.
10. **Is the transaction short and sequential?** Avoid holding snapshots during external API calls, user waits, or long jobs.
11. **How fresh must post-commit reads be?** Configure read concern, read preference, and sessions appropriately for operations outside transactions.
12. **Have server/driver versions and deployment limits been verified?** Especially regarding sharding, journaling, DDL, and production constraints.

## 21. Conclusion

In MongoDB, these three options play **distinct yet tightly coupled roles**:

- **Read concern** defines guarantees on data read inside the transaction: `"local"`, `"majority"`, or `"snapshot"`.
- **Write concern** defines **commit** acknowledgment: `w:1` provides primary acknowledgment only, while `w:"majority"` provides required majority durability; `j` and `wtimeout` add journal and wait-time controls.
- **Read preference** defines where read operations are routed. **Transactions containing read operations must use `primary`**, never secondaries.

The combination `readConcern:"snapshot"` + `writeConcern:{w:"majority"}` + `readPreference:"primary"` is a primary pattern when needing a majority-committed snapshot and strong commit acknowledgment. Still, proper configuration must always pair with **consistent session passing**, **conditional writes**, **retry/unknown commit handling**, **idempotency**, and replication monitoring in real environments.

### Official Documentation for Version Verification

- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Manual — Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Manual — Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/)
- [MongoDB Java Sync Driver — Configure Read and Write Operations](https://www.mongodb.com/docs/drivers/java/sync/current/crud/read-write-config/)
