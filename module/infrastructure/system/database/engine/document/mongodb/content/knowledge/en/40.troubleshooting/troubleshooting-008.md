# Not Primary, Write Conflicts, and Transient Transaction Errors in MongoDB

## 1. When the Primary Changes Mid-Write: What Do the Errors Mean?

An ordering application uses a MongoDB replica set to store **orders**, **inventory**, and **payment intents**. While a request is creating an order, the MongoDB driver receives:

~~~text
MongoCommandException: Command failed with error 10107
(NotWritablePrimary): not primary
~~~

Another request executing a transaction fails with:

~~~text
WriteConflict (code 112)
Write conflict during plan execution and yielding is disabled.
Please retry your operation or multi-document transaction.
~~~

At commit time, yet another request encounters:

~~~text
MongoException
errorLabels: ["UnknownTransactionCommitResult"]
~~~

All three can appear when a MongoDB system experiences resource contention or topology changes, yet **they must not be handled as the same type of error**.

- **Not primary / `NotWritablePrimary`** relates to topology or write routing: the node receiving the command is no longer a primary capable of accepting writes at that moment.
- **`WriteConflict`** relates to contention between concurrent operations modifying data, especially inside transactions.
- **Transient transaction errors** are flagged by the driver/server via **error labels** and require retrying the exact right scope: the transaction body or only the commit.

The goal of troubleshooting is not "keep retrying until errors stop." The goal is **recovering service without double-writing data, losing records, or misreporting commit outcomes**.

### 1.1. A Typical Timeline

~~~text
Application                Driver               Replica set
     |                        |                        |
     | insert/order           |                        |
     |----------------------->|                        |
     |                        |---- write to P1 ------>|
     |                        |                P1 steps down
     |                        |<-- NotWritablePrimary -|
     |                        |                        |
     |                        | topology refresh       |
     |                        | discover P2 primary    |
     |                        |                        |
     |                        |---- retry if allowed ->|
     |                        |                        |
     |<--- response ----------|                        |
~~~

If the command is inside a **multi-document transaction**, you cannot simply take the retry logic of a standalone write and apply it to every step: a transaction carries its own state and transaction number.

### 1.2. Learning Objectives

After this lesson, you will be able to:

1. Classify **`NotWritablePrimary`/not primary** messages, server selection errors, and related network errors.
2. Understand primary elections, stepdowns, client topology discovery, and the failover gap.
3. Identify common causes of **`WriteConflict`** and ways to reduce contention.
4. Distinguish errors inside the transaction body from errors during **`commitTransaction`**.
5. Understand **`TransientTransactionError`** and **`UnknownTransactionCommitResult`**.
6. Choose the right retry scope, backoff, retry budget, and timeouts.
7. Prevent transient failures from turning into **double business effects** during client/HTTP retries.
8. Verify **`MongoClient` URI**, read/write concern, replica set health, and driver versions.
9. Implement error handling with the MongoDB Java Sync Driver and Spring Data MongoDB.
10. Design fault-injection tests and runbooks without impacting production.
11. Monitor write conflicts, elections, retry attempts, p95/p99, replication lag, and pending reconciliations.
12. Separate genuinely transient errors from schema, permission, input, and business conflicts that must not be retried.

## 2. Fundamentals: Primary, Replication, and Driver

### 2.1. Replica Sets and Write Routing

A MongoDB replica set consists of a **primary** and **secondaries**. Normal write operations must go to the replica set's primary.

~~~text
                         Java service
                              |
                       MongoDB driver
                              |
           +------------------+------------------+
           |                  |                  |
         node01             node02             node03
         PRIMARY           SECONDARY          SECONDARY
           |                  ^                  ^
           +------ oplog ---->+------ sync ------+
~~~

Diagram is illustrative; a secondary may sync from the primary or an eligible sync source. During failover:

~~~text
T0: node01 = primary
T1: node01 steps down or becomes unavailable
T2: election / temporary no-primary window
T3: node02 = new primary
T4: driver detects and routes writes to node02
~~~

Between **T1–T4**, writes may fail, wait on server selection, or be retried per supported rules.

### 2.2. Having No Primary Differs from Client Targeting the Wrong Node

Two scenarios produce similar messages yet have different causes:

**Case A — Valid primary election:**

- The driver knows the replica set.
- The old primary steps down.
- The driver refreshes topology and discovers the new primary.

**Case B — Misconfigured application connection:**

- The URI points to a secondary and forces **`directConnection=true`**.
- The application uses a hardcoded host instead of a replica set URI.
- A reverse proxy/DNS mapping shows the driver the wrong node.
- Client topology metadata fails because hostnames cannot resolve.

Retrying against the same secondary forever **cannot turn it into a primary** if the connection configuration remains wrong.

### 2.3. Replica Set URI Example

~~~text
mongodb://mongo1.example.test:27017,mongo2.example.test:27017,mongo3.example.test:27017/orders?replicaSet=rsOrders&retryWrites=true&w=majority
~~~

This is an illustrative lab URI. Production requires TLS, authentication, and secrets per policy. Member hostnames in **`rs.conf()`** must be resolvable and reachable by clients per the network topology.

**Do not set `directConnection=true`** for a normal replica set application if you want the driver to select the primary and handle failovers automatically. Direct connections fit specific intentional admin/tooling cases, not fixing write routing errors.

### 2.4. Server Selection Differs from Server Write Errors

The driver may fail to find a primary before even sending the command:

~~~text
MongoTimeoutException:
  Timed out while waiting for a server
  that matches WritableServerSelector
~~~

Or the command reached a node, and the node replied:

~~~text
NotWritablePrimary (10107)
~~~

Differences:

| Category | Where it occurs | Investigation direction |
|---|---|---|
| **Server selection timeout** | Driver could not find an eligible server to send the command. | Replica set topology, DNS, ports, elections, connect/server-selection settings. |
| **`NotWritablePrimary`** | Node received the command yet cannot accept writes as primary. | Stepdown, stale topology, `directConnection`, routing. |
| **Network/socket timeout** | Connection dropped or waited too long. | Network, node liveness, pool, TLS, load balancer/proxy. |
| **`WriteConflict`** | Storage/concurrency conflict during execution. | Contended documents, transaction duration, retry strategy. |
| **Write concern failure** | Requested acknowledgment level was not satisfied. | Majority availability, replication lag, disk/network. |

A network timeout can also leave **the write/commit outcome ambiguous**, depending on the command and execution stage. Never assume every timeout means the server executed nothing.

## 3. Not Primary and Related Messages

### 3.1. `NotWritablePrimary`

A common error code:

~~~text
Code 10107: NotWritablePrimary
Legacy text: "not primary" / "not master"
~~~

Practical meaning: the node receiving the command **is not a primary capable of accepting writes** at the time the command is evaluated.

Older messages used the term **not master**, whereas newer MongoDB versions use **primary**. Never rely solely on a single error string when classifying.

### 3.2. Related Error Codes

Common codes/names across MongoDB versions:

| Code or name | Typical context |
|---|---|
| **`NotWritablePrimary` (10107)** | Write sent to a node unable to accept primary writes. |
| **`NotPrimaryNoSecondaryOk` (13435)** | Read or operation requires primary while the server is ineligible. |
| **`PrimarySteppedDown` (189)** | Primary just stepped down or changed state. |
| **`InterruptedDueToReplStateChange` (11602)** | Operation interrupted due to replication state change. |
| **`ShutdownInProgress` (91)** | Server is shutting down. |
| **`HostUnreachable` (6)**, **`NetworkTimeout` (89)** | Network/host reachability failures. |
| **`WriteConflict` (112)** | Write contention or transaction write conflict. |
| **`NoSuchTransaction` (251)** | Server no longer recognizes the transaction number/state per command. |

**Do not treat this code table as exhaustive or immutable across all MongoDB server/driver versions.** Driver exception types and error labels are the primary authority for application retry decisions.

### 3.3. Situations Producing `NotWritablePrimary`

1. **Election:** the previous primary no longer holds the role.
2. **Maintenance stepdown:** an operator transitions the primary.
3. **Node loses majority connectivity:** cannot remain a valid primary.
4. **Client connects directly to a secondary:** wrong URI or hardcoded address.
5. **Application uses cached/stale topology:** driver has not yet discovered the new primary.
6. **Network partition or wrong proxy routing:** request lands on an ineligible node.
7. **Long-running transaction spans failover:** old primary can no longer execute the prior attempt.

This error **does not always mean data is corrupted**, and should not be "treated" by restarting all nodes.

### 3.4. Does One Failed Request Mean the Cluster Is Down?

Not necessarily:

~~~text
Request 1 at T1 -> NotWritablePrimary
Election completes at T3
Request 2 at T4 -> success
~~~

However, if errors persist for minutes, check:

- Was a primary elected?
- Can the driver reach all member hostnames?
- Replica set member states and majority votes?
- DNS/TLS/authentication?
- Server selection/connection pool saturation?
- Is `directConnection` or stale client config in use?

### 3.5. Read-Only Checks in `mongosh`

On a connection to the relevant replica set:

~~~javascript
db.adminCommand({ hello: 1 });
~~~

When connected directly to a member with sufficient privileges:

~~~javascript
rs.status();
~~~

To inspect topology configuration in an authorized environment:

~~~javascript
rs.conf();
~~~

Never modify **`rs.conf()`**, votes, priorities, or call **`rs.stepDown()`** in production just because `NotWritablePrimary` appeared without an approved procedure.

### 3.6. Fields to Inspect

In **`hello`** or topology monitoring:

- **`setName`:** replica set identifier.
- **`isWritablePrimary`:** whether this server is currently a writable primary.
- **`secondary`:** whether this server is in secondary state.
- **`primary`:** primary address known to the topology.
- **`hosts`/`passives`/`arbiters`** when present.
- **`topologyVersion`** or version-equivalent metadata.

Do not infer cluster-wide health solely from an old snapshot taken before an election.

### 3.7. Why Use an Up-to-Date Compatible Driver?

MongoDB drivers implement **SDAM (Server Discovery and Monitoring)** to track servers/topology and select an eligible primary. Outdated drivers, misconfigured URIs, or networks blocking member hostnames make failover unreliable.

Tweaking retry loops in business services **cannot replace** keeping drivers current and connectivity properly configured.

## 4. What Is `WriteConflict`?

**`WriteConflict`** signals a conflict in the storage engine and transaction execution when writes contend concurrently; MongoDB may require retrying the operation or transaction attempt.

~~~text
Session T1              Session T2
   |                       |
startTransaction       startTransaction
   |                       |
read account A         read account A
   |                       |
update A               update A
   |                       |
success?               write conflict?
   |                       |
commit                 abort/retry
~~~

Two transactions updating the same document is a classic example, yet write conflicts are not limited to two users explicitly editing one account: concurrency, storage/page state, index updates, and transaction snapshots can all contribute depending on the operation.

### 4.1. A Simple Account Example

Fixture:

~~~javascript
{
  _id: "wallet-A",
  currency: "VND",
  balanceUnits: NumberLong("200")
}
~~~

T1 and T2 both want to debit **150 units**. If both merely read **200** and then perform an unconditional update, the application faces a business race condition. MongoDB's transaction/write-conflict handling aborts one attempt; the retried attempt must **re-read** the balance.

The debit precondition should sit directly inside the write:

~~~javascript
db.accounts.updateOne(
  {
    _id: "wallet-A",
    currency: "VND",
    balanceUnits: { $gte: NumberLong("150") }
  },
  { $inc: { balanceUnits: NumberLong("-150") } }
);
~~~

Inside a transaction, check **`matchedCount`**. When the new attempt sees only 50 remaining, the retry must not debit 150.

### 4.2. `WriteConflict` vs. `DuplicateKey`

| `WriteConflict` | `DuplicateKey` |
|---|---|
| Concurrency/storage conflict; often eligible for attempt retry. | Unique constraint violated; may be a persistent business/data conflict. |
| Inside transactions may carry **`TransientTransactionError`**. | Not automatically retryable, especially when the key genuinely collides. |
| Retried attempt must re-read snapshot/preconditions. | Check existing record and business idempotency. |
| Reducing contention and transaction duration helps. | Fix duplicate data/unique-key policy; never randomize keys blindly. |

A duplicate ID from a client resending the same request can be **resolved** via receipt lookup; a duplicate ID from two distinct business actions is **`409 Conflict`**, not a transient error to retry forever.

### 4.3. `WriteConflict` vs. `LockTimeout`

**`WriteConflict`** reflects concurrent write/transaction state contention; **`LockTimeout`** typically indicates an operation failed to acquire a lock within the allowed window.

Both can rise together when transactions run too long or load spikes, yet **do not lump every lock timeout into `TransientTransactionError`** unless the driver/server labels it accordingly.

### 4.4. MongoDB Automatically Retries Some Internal Conflicts

Certain single-document operations outside transactions have storage/query-engine conflicts retried internally by MongoDB. When an application sees `WriteConflict`, do not assume nothing executed or that resending arbitrarily is always safe.

**The application rule is to classify by command, transaction phase, error label, and idempotency contract**—not just the word "conflict."

### 4.5. When Can `WriteConflict` Spike?

- Many transactions updating the same **hot document**.
- Transactions holding snapshots open for long durations while data mutates rapidly.
- Workflows reading many records before writing.
- Batch updates contending over a narrow set of IDs.
- Aggressive retry rates amplifying contention.
- Index builds or storage-heavy tasks competing for resources.

Do not conclude "MongoDB does not support concurrency" when conflicts appear: the solution is often reducing contention and refining the data model.

## 5. Why Do Transactions Have Transient Errors?

A MongoDB multi-document transaction is **stateful**, requiring multiple commands to commit or abort atomically as a unit. During a transaction:

~~~text
startTransaction
       |
       v
read/update/insert
       |
       +--> transient error?
       |        |
       |        v
       |     abort/stop attempt
       |        |
       |        v
       |     retry whole transaction
       |
       v
commitTransaction
       |
       +--> unknown commit result?
       |        |
       |        v
       |     retry same commit
       |
       v
confirmed committed
~~~

**A transient error does not mean it is safe to re-send any arbitrary command.** It points to a defined retry protocol that must be applied at the right phase.

### 5.1. Error Codes, Error Labels, and Exception Classes

In the MongoDB ecosystem:

- **Error code** identifies the server error type, e.g., `WriteConflict`, `NotWritablePrimary`.
- **Error labels** provide handling metadata, e.g., `TransientTransactionError` or `UnknownTransactionCommitResult`.
- **Driver exception type** indicates command error, timeout, network failure, or transaction exception.
- **Operation phase** identifies when it happened: before transaction, in body, during commit, or post-commit.

Applications should rely on the driver's **label-aware retry policy** whenever possible rather than parsing exception message text.

### 5.2. `TransientTransactionError`

The **`TransientTransactionError`** label typically marks a temporary failure during transaction execution that prevents the current attempt from continuing normally.

Examples may include:

- `WriteConflict` inside a transaction.
- Primary stepdown while a transaction is in flight.
- Certain network errors during the body.
- Certain server interruptions per the transaction specification.

Exactly which errors receive this label depends on **server/driver version, command, and phase**. Never assume every `NotWritablePrimary` always carries this label.

Conceptual action:

~~~text
TransientTransactionError during body
         |
         v
discard/abort current attempt if applicable
         |
         v
start a new transaction attempt
         |
         v
rerun reads/writes with current state
~~~

Retrying the body in a new attempt ensures business preconditions are re-evaluated against fresh data.

### 5.3. `UnknownTransactionCommitResult`

The **`UnknownTransactionCommitResult`** label is critical when a commit was sent yet the client cannot determine its outcome.

~~~text
Client                         MongoDB
  |                               |
  | commitTransaction             |
  |------------------------------>|
  |                               | commit may happen
  |          response lost        |
  X<------------------------------X
  |
  | commit outcome UNKNOWN
~~~

Correct action while still within the same session/transaction context and permitted by error semantics:

~~~text
Retry commitTransaction
for the SAME transaction
~~~

**Do not immediately re-run the transaction body**; the original attempt may already have committed.

### 5.4. `NoSuchTransaction`

**`NoSuchTransaction`** occurs when the server does not recognize the transaction by session/number in that context. Causes include an already-aborted transaction, an obsolete transaction number, or changed client/server state.

Do not jump to a simplistic conclusion:

~~~text
NoSuchTransaction => definitely safe to debit again
~~~

Inspect the phase, error labels, driver behavior, and business idempotency. An ambiguous commit outcome may require reconciliation even if a retry attempt returns another error.

### 5.5. `TransactionTooLargeForCache` and Errors Not to Retry Blindly

In MongoDB versions enforcing transaction resource caps, errors tied to **transaction size/cache** cannot be resolved by blindly re-running the exact same transaction. Shrink the transaction size/duration or redesign batching.

Never use the same retry loop for:

~~~text
WriteConflict under contention
    vs
Invalid schema
    vs
Out-of-memory/transaction too large
    vs
Unauthorized
~~~

### 5.6. Summary of the Three Outcomes

| What the application knows | Permitted action |
|---|---|
| **Definitely aborted / not committed** | Retry the whole transaction if the error is transient and the request remains valid. |
| **Definitely committed** | Return success; do not debit/credit again. |
| **Unknown commit outcome** | Retry the same transaction commit while possible; if context is lost, reconcile via business key. |

This is the most important **tri-state model** for business correctness around commits.

## 6. Choosing the Right Retry Scope

### 6.1. Retrying Standalone Requests

For a single command eligible for retryable writes:

~~~text
Application issues one write
  -> driver may retry according to retryable write protocol
  -> application receives result/error
~~~

This mechanism uses session/statement identity to limit double execution per server rules, which **is not the same** as writing:

~~~java
while (true) {
    collection.updateOne(...);
}
~~~

If the update is **`$inc`**, an application loop issuing fresh commands can increment the balance multiple times if the earlier attempt executed and only the response was lost.

### 6.2. Retrying the Whole Transaction

When an error in the transaction body carries **`TransientTransactionError`**:

~~~text
Attempt #1:
  read A
  debit A
  credit B -> WriteConflict
  attempt aborted

Attempt #2:
  read A again
  recheck balance
  debit A
  credit B
  commit
~~~

Never treat reads from attempt #1 as authoritative in attempt #2. Data may already have changed.

### 6.3. Retrying Commit

When the commit result is unknown:

~~~text
Attempt #2 body already completed
  |
  v
commit call #1 -> network timeout
  |
  v
commit call #2 FOR SAME transaction
  |
  v
known committed / still unknown / other error
~~~

A commit retry does not re-issue debit/credit commands. The driver manages session identity and transaction numbers; applications must not hand-craft `lsid`/`txnNumber`.

### 6.4. Retrying the Entire HTTP Request

An HTTP client may resend:

~~~http
POST /wallet/transfers
Idempotency-Key: trx-2026-001
~~~

When the service receives the second call, it starts a **new business invocation** with a different session. The MongoDB driver does not know this is "the same money transfer" unless the application maintains a persistent idempotency key.

### 6.5. Decision Table

| Scenario | Retry scope | Condition |
|---|---|---|
| Retryable single write error | Driver-managed write retry | Supported command, `retryWrites`/config valid. |
| `TransientTransactionError` in body | Whole transaction attempt | Retry budget remaining, body safe to replay. |
| `UnknownTransactionCommitResult` on commit | Same transaction commit | Session/context intact, driver permits. |
| HTTP response lost after commit | Same logical business request | Stable idempotency key, persistent receipt. |
| `DuplicateKey` for same request | No blind retry; lookup | Verify immutable request fields. |
| `DuplicateKey` for different request | No retry | Return conflict and audit. |
| Data validation failure | No retry | Fix request/data. |
| Authentication/authorization error | No retry | Fix identity/configuration. |
| Transient server selection | Bounded retry/circuit breaker | Check replica availability/topology. |
| Persistent `WriteConflict` on hot key | Bounded retry + redesign | Reduce contention; avoid retry storms. |

### 6.6. Do Not Use Error Message String Matching

Anti-pattern:

~~~java
if (ex.getMessage().contains("not primary")) {
    retry();
}
~~~

Messages change across versions, get wrapped by frameworks, or vary by context. Use error codes, labels, exception types, and driver APIs—alongside business-level context.

### 6.7. A Retry Budget Is a Safety Boundary

A retry policy includes:

~~~text
maxAttempts or deadline
backoff with jitter
read/write timeout
idempotency/reconciliation
metrics and logging
~~~

Never stack retries across the driver, repository wrapper, service, controller, and gateway without bounding total attempts:

~~~text
3 gateway retries
 x 3 service retries
 x 3 driver attempts
 = up to 27 attempts in an unlucky path
~~~

Retry layers must share a **unified budget or coordinated limits** to avoid amplifying outages.

## 7. Java Sync Driver: Configure the Client Before Fixing Retry Logic

A **`MongoClient`** is designed to be reused, is thread-safe, and manages connection pools and server discovery. Never create a new `MongoClient` per request to work around `NotWritablePrimary`.

### 7.1. Initializing the Client with a Replica Set URI

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

public final class MongoClientProvider {
    private final MongoClient client;

    public MongoClientProvider(String uri) {
        // URI from environment/secret manager, not hardcoded credentials.
        this.client = MongoClients.create(uri);
    }

    public MongoClient client() {
        return client;
    }

    public void close() {
        client.close();
    }
}
~~~

Example URI:

~~~text
mongodb://mongo1:27017,mongo2:27017,mongo3:27017/app?replicaSet=rsApp&retryWrites=true&w=majority
~~~

### 7.2. Connection Strings Do Not Replace Monitoring

Parameters such as:

- **`serverSelectionTimeoutMS`**
- **`connectTimeoutMS`**
- **`socketTimeoutMS`**
- **`maxPoolSize` / `minPoolSize`**
- **`retryWrites`**
- **`w` / `journal`**, per write concern

serve distinct roles. Raising **`serverSelectionTimeoutMS`** gives elections extra breathing room, yet **cannot fix** a replica set lacking majority or broken DNS.

Too long a timeout breaches HTTP SLOs; too short a timeout breaks legitimate failovers. Tune them around application deadlines and high-availability requirements.

### 7.3. Specify Primary for Transactions

~~~java
TransactionOptions options = TransactionOptions.builder()
    .readPreference(ReadPreference.primary())
    .readConcern(ReadConcern.SNAPSHOT)
    .writeConcern(WriteConcern.MAJORITY)
    .build();
~~~

Never try to force transaction writes onto a secondary using another read preference. Transaction options and write concern must align with driver/server versions.

### 7.4. Read-Only Query to Check Connectivity

In `mongosh` against a replica set:

~~~javascript
db.adminCommand({ hello: 1 });
~~~

In Java:

~~~java
Document hello = client
    .getDatabase("admin")
    .runCommand(new Document("hello", 1));

System.out.println(
    "setName=" + hello.getString("setName")
);
System.out.println(
    "isWritablePrimary=" + hello.getBoolean("isWritablePrimary")
);
~~~

An application client sends the admin command to whichever server the driver picks per operation semantics; the output is a **point-in-time observation**, not a health report of the whole replica set. Use SDAM monitoring and appropriate commands to inspect topology.

### 7.5. Do Not Pin a Fixed Primary

Anti-pattern:

~~~text
mongodb://node01:27017/?directConnection=true
~~~

When `node01` steps down, retrying will never move writes to the new primary. Use the host seed list/`replicaSet` parameter or the connection string provided by your managed service.

## 8. Java Sync Driver: Handling Transactions with `withTransaction`

The **`ClientSession.withTransaction(...)`** API in the MongoDB Java Sync Driver coordinates start, commit, and supported retries per the transaction specification. For many workflows, it is safer than hand-rolling nested body/commit loops.

### 8.1. Two-Account Point Transfer Problem

Fixtures:

~~~javascript
// app_test.accounts
{ _id: "A", balanceUnits: NumberLong("1000") }
{ _id: "B", balanceUnits: NumberLong("300") }
~~~

A transaction intends to:

1. Debit 200 units from A if balance suffices.
2. Credit 200 units to B if B exists.
3. Insert a receipt whose **`_id`** is the stable `requestId`.

### 8.2. Java Sync Driver Code

~~~java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

import java.util.Date;
import java.util.Objects;

public final class TransferService {

    private static final TransactionOptions TX_OPTIONS =
            TransactionOptions.builder()
                    .readPreference(ReadPreference.primary())
                    .readConcern(ReadConcern.SNAPSHOT)
                    .writeConcern(WriteConcern.MAJORITY)
                    .build();

    private final MongoClient client;
    private final MongoCollection<Document> accounts;
    private final MongoCollection<Document> receipts;

    public TransferService(MongoClient client) {
        this.client = Objects.requireNonNull(client);
        var database = client.getDatabase("app_test");
        accounts = database.getCollection("accounts");
        receipts = database.getCollection("transfer_receipts");
    }

    public Document transfer(
            String requestId,
            String fromId,
            String toId,
            long amountUnits) {

        if (requestId == null || requestId.isBlank()
                || fromId == null || fromId.isBlank()
                || toId == null || toId.isBlank()
                || fromId.equals(toId) || amountUnits <= 0) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        try (ClientSession session = client.startSession()) {
            return session.withTransaction(() -> {
                Document existing = receipts.find(
                        session,
                        Filters.eq("_id", requestId)
                ).first();

                if (existing != null) {
                    assertSameRequest(
                            existing, fromId, toId, amountUnits);
                    return existing;
                }

                UpdateResult debit = accounts.updateOne(
                        session,
                        Filters.and(
                                Filters.eq("_id", fromId),
                                Filters.gte("balanceUnits", amountUnits)
                        ),
                        Updates.inc("balanceUnits", -amountUnits)
                );

                if (debit.getMatchedCount() != 1) {
                    throw new IllegalStateException(
                            "Account missing or insufficient balance");
                }

                UpdateResult credit = accounts.updateOne(
                        session,
                        Filters.eq("_id", toId),
                        Updates.inc("balanceUnits", amountUnits)
                );

                if (credit.getMatchedCount() != 1) {
                    throw new IllegalStateException(
                            "Destination account missing");
                }

                Document receipt = new Document("_id", requestId)
                        .append("fromId", fromId)
                        .append("toId", toId)
                        .append("amountUnits", amountUnits)
                        .append("state", "COMMITTED")
                        .append("createdAt", new Date());

                receipts.insertOne(session, receipt);
                return receipt;
            }, TX_OPTIONS);
        }
    }

    private static void assertSameRequest(
            Document receipt,
            String fromId,
            String toId,
            long amountUnits) {

        Object value = receipt.get("amountUnits");
        boolean same = fromId.equals(receipt.getString("fromId"))
                && toId.equals(receipt.getString("toId"))
                && value instanceof Number
                && amountUnits == ((Number) value).longValue();

        if (!same) {
            throw new IllegalStateException(
                    "Idempotency key reused with another request");
        }
    }
}
~~~

**Limitations:** this code illustrates transactions/idempotency and is not a production financial ledger. Real systems need currencies, overflow checks, account ownership/authorization, ledgers, audits, and reconciliation.

### 8.3. Must Pass the Same `ClientSession`

All operations:

~~~java
receipts.find(session, ...);
accounts.updateOne(session, ...);
accounts.updateOne(session, ...);
receipts.insertOne(session, ...);
~~~

participate in the transaction. If an update uses:

~~~java
accounts.updateOne(filter, update);
~~~

**without the `session` argument**, it executes outside the transaction and can commit independently; aborting the transaction will not undo it.

### 8.4. Why Check `matchedCount`?

Predicate:

~~~java
Filters.gte("balanceUnits", amountUnits)
~~~

prevents debiting when the balance is insufficient. However, an unmatched `updateOne` **does not throw an exception automatically**; skipping the `matchedCount` check would credit B even though A was never debited.

### 8.5. The Callback Can Execute Multiple Times

~~~text
Attempt #1:
  debit A
  credit B -> write conflict
  transaction aborts

Attempt #2:
  check receipt again
  debit A with current balance
  credit B
  insert receipt
  commit
~~~

Never send emails, HTTP payment requests, Kafka events, or external side effects inside the callback. **`requestId` must remain stable** across transaction attempts and HTTP retries.

### 8.6. `withTransaction` Does Not Provide HTTP Idempotency

~~~text
Transaction with requestId=T1 committed
            |
            v
HTTP response lost
            |
            v
Client retries POST /transfers with T1
~~~

The new HTTP call opens a new session/transaction. Looking up the receipt by stable `requestId` and unique **`_id`** prevents debiting a second time.

### 8.7. Concurrent Requests with the Same ID

Two concurrent requests may both see the receipt missing. The unique ID prevents duplicate receipts; a failed transaction leaves no partial debit/credit behind. However, the losing request may hit a duplicate key or write conflict, so the service should re-read the receipt and **compare immutable request parameters** rather than returning success blindly.

### 8.8. When the Whole Cluster Is Unavailable

`withTransaction` enforces retry rules yet cannot make a request succeed if the primary loses majority. The application needs deadlines, backoff/overload protection, and an **unknown/pending reconciliation** state when the commit outcome remains unresolved.

## 9. Java: Reading Error Codes and Labels Properly

### 9.1. `MongoException` and Error Labels

~~~java
import com.mongodb.MongoException;

public final class MongoFailureReporter {

    public static void report(MongoException exception) {
        int code = exception.getCode();

        boolean transientTransaction =
                exception.hasErrorLabel(
                        "TransientTransactionError");

        boolean unknownCommitResult =
                exception.hasErrorLabel(
                        "UnknownTransactionCommitResult");

        System.out.println("mongodb.error.code=" + code);
        System.out.println("mongodb.error.transientTx="
                + transientTransaction);
        System.out.println("mongodb.error.unknownCommit="
                + unknownCommitResult);
    }
}
~~~

This illustrates classification, not a recommendation to log every exception/payload in production. Log sanitized error categories, trace IDs, and redacted details per policy.

### 9.2. Error Code Is Only Part of the Context

Examples:

~~~text
Code: NotWritablePrimary
Phase: single retryable write
  -> driver topology selection / retryable-write rules

Code: NotWritablePrimary
Phase: transaction body
Label: TransientTransactionError
  -> retry whole transaction

Phase: commit
Label: UnknownTransactionCommitResult
  -> retry same transaction commit
~~~

**These are illustrative branches, not a guarantee that every `NotWritablePrimary` always carries that label.** Labels vary by server/driver version and command.

### 9.3. Never Retry by Message String

Anti-pattern:

~~~java
if (exception.getMessage().contains("not primary")) {
    while (true) {
        retry();
    }
}
~~~

Problems:

- Message text can change.
- Exceptions get wrapped by Spring/frameworks.
- Some errors are persistent configuration issues.
- Retry storms slow cluster failover recovery.
- This pattern ignores unknown commit outcomes.

### 9.4. Two-Loop Retry Pseudocode

~~~text
deadline = now + retryBudget

OUTER: while before deadline:
    start new transaction attempt

    try:
        execute all reads and writes
    catch error:
        abort attempt when appropriate

        if TransientTransactionError:
            backoff and continue OUTER

        throw error

    INNER: while before deadline:
        try:
            commit SAME transaction
            return COMMITTED
        catch error:
            if UnknownTransactionCommitResult:
                retry commit in INNER
                continue INNER

            handle known failure / reconcile

    return UNKNOWN_NEEDS_RECONCILIATION

return RETRY_BUDGET_EXHAUSTED
~~~

**This is a mental model**, not a verified production implementation. Real code must handle session state, driver-specific retry semantics, cancellation, transaction numbers, and error labels. Prefer **`withTransaction`** whenever suitable.

### 9.5. Never Manually Manipulate `lsid` or `txnNumber`

Commit retries for the **same transaction** must preserve the driver-managed transaction identity. Never hand-craft commands with `lsid`/`txnNumber` or open a new session and call it a commit retry.

### 9.6. Never Compensate Immediately When Outcome Is Unknown

If a commit call times out, the original transaction **may already have committed**. Immediately issuing a reversal transfer or a new debit can corrupt balances. Resolve the durable receipt and business state before acting.

## 10. Spring Data MongoDB: `@Transactional` and Transaction Errors

Spring Data MongoDB provides **`MongoTransactionManager`** to coordinate transactions on service methods annotated with **`@Transactional`**.

### 10.1. Configuring the Transaction Manager

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration
public class MongoTransactionConfiguration {

    @Bean
    MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory factory) {
        return new MongoTransactionManager(factory);
    }
}
~~~

Across Spring Boot/Spring Data versions, auto-configuration and APIs may differ. Verify which transaction manager is actually registered in the application context.

### 10.2. Spring Transaction Boundary

~~~java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryService {

    private final MongoTemplate template;

    public InventoryService(MongoTemplate template) {
        this.template = template;
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public void reserve(String itemId, long quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be > 0");
        }

        Query query = Query.query(
                Criteria.where("_id").is(itemId)
                        .and("available").gte(quantity)
        );

        var result = template.updateFirst(
                query,
                new Update().inc("available", -quantity),
                "inventory"
        );

        if (result.getMatchedCount() != 1) {
            throw new IllegalStateException(
                    "Inventory item unavailable");
        }

        // Further MongoDB writes here can join this transaction.
    }
}
~~~

This example demonstrates **session binding and conditional updates**. A real service must also include order ID/idempotency, reservation receipts, expirations, and related writes inside the transaction when atomicity is required.

### 10.3. `@Transactional` Does Not Automatically Retry Every Error

`MongoTransactionManager` primarily manages **begin, commit, and rollback** of a Spring transaction. Do not assume this annotation provides identical retry semantics to **Java Sync Driver `withTransaction`** across all versions.

A misplaced `RetryTemplate` or **`@Retryable`** can retry **inside an already-failed transaction** or re-run a **`@Transactional` method after an unknown commit** without idempotency.

### 10.4. Place Retries Outside the Transaction Boundary

Pattern:

~~~text
Outer orchestration service:
  classify exception
  enforce retry budget/idempotency
  call transactional service through Spring proxy

Transactional service:
  one attempt
  MongoDB writes
  commit/rollback
~~~

When retrying the whole body, each attempt must start a **fresh Spring transaction**, never reusing a failed transaction context.

If the commit outcome is unknown, **do not blindly retry the whole `@Transactional` method** without transaction-aware handling and business reconciliation.

### 10.5. Spring Proxy / Self-Invocation

~~~java
@Service
class BadService {
    public void call() {
        this.saveInTransaction(); // Bypasses proxy interception.
    }

    @Transactional
    public void saveInTransaction() {
        // May not run in a transaction when self-invoked.
    }
}
~~~

In standard proxy-based AOP, calling a method on the same bean via **`this`** bypasses the Spring proxy, so transaction advice is skipped.

Fix the design by invoking the transactional method through an injected **Spring-managed bean/proxy** and verify with an integration test.

### 10.6. Swallowed Exceptions

~~~java
@Transactional
public void badTransfer() {
    try {
        debit();
        credit();
    } catch (RuntimeException ex) {
        // Dangerous: method exits without propagating failure.
    }
}
~~~

If an exception is swallowed, the Spring transaction manager may attempt to commit. To roll back, propagate unchecked exceptions or apply explicit rollback rules. For checked exceptions, Spring's default behavior differs; configure **`rollbackFor`** when needed.

### 10.7. Do Not Mix MongoDB and SQL Transaction Managers

A `@Transactional` bound to **`JpaTransactionManager`** does not make MongoDB writes atomic with PostgreSQL; conversely, **`MongoTransactionManager`** does not commit Kafka or HTTP gateways.

Across heterogeneous systems, consider **outbox, saga, and compensation** patterns with explicit consistency boundaries.

### 10.8. When Spring Wraps MongoDB Errors

Spring Data may translate MongoDB exceptions into **`DataAccessException`** subclasses depending on version and API. Never drive retry logic solely from exception messages, and never assume every `DataAccessException` is transient.

An adapter can:

1. Preserve root causes and MongoDB error labels when present.
2. Classify retryable transaction attempts.
3. Identify commit-phase and unknown outcomes.
4. Enforce idempotency and retry budgets.
5. Log sanitized error categories.

### 10.9. Reactive Transactions

`ReactiveMongoTemplate`/`ReactiveMongoRepository` use dedicated reactive transaction APIs/`ReactiveMongoTransactionManager`. Never copy synchronous retry or `ThreadLocal` assumptions directly into Reactor pipelines.

In reactive code, pay attention to:

- Session/transaction context propagation via Reactor `Context`.
- Backpressure and cancellation.
- `retry` operators re-subscribing to the entire pipeline.
- External side effects inside re-subscribed pipelines.
- Never blocking event-loop threads for backoff or auxiliary network calls.

**A misplaced re-subscription can re-execute the body after an unknown commit.** Design recovery strictly around the reactive driver/framework's transaction protocol.

## 11. Idempotency: Never Let Retries Become Double Writes

### 11.1. A Single Write with `$inc`

Example:

~~~javascript
db.counters.updateOne(
  { _id: "checkout" },
  { $inc: { count: 1 } }
);
~~~

If the response is lost after server execution, a fresh `$inc` issued by application code **will increment the counter again**. Retryable writes carry specific protocol guarantees, whereas a custom retry loop does not reuse the original statement identity.

### 11.2. Stable Idempotency Keys

An HTTP request:

~~~http
POST /orders HTTP/1.1
Idempotency-Key: order-create-c4a7
Content-Type: application/json

{
  "customerId": "C-17",
  "items": [{"sku": "SKU-1", "quantity": 2}]
}
~~~

The application should persist the business order/receipt under a stable key tied to the request. When the client resends after a timeout, the server reads the committed state instead of creating another order.

### 11.3. Unique Indexes as a Database Safeguard

Example:

~~~javascript
db.orders.createIndex(
  { clientRequestId: 1 },
  { unique: true }
);
~~~

When two concurrent requests carry the same key, only one record can exist normally. Still, you must:

- Validate and compare immutable request inputs.
- Keep related updates inside the same transaction.
- Re-read after a duplicate-key race.
- Distinguish committed records from pending requests.

Never generate a random new `clientRequestId` on duplicate key errors "to help the retry pass."

### 11.4. Same Key, Different Payload

~~~text
Key = k-100
First request: quantity=2
Second request: quantity=100
~~~

Never return the first request's success to the second request without checking for mismatch. Bind the key to a **canonicalized request fingerprint/immutable parameters** and return a conflict per API contract.

### 11.5. Reading After an Unknown Commit

If the retry budget is exhausted:

~~~text
Business request may have committed
       |
       v
Lookup durable receipt by original key
       |
       +--> COMMITTED + matching params: return recorded result
       |
       +--> CONFLICT: reject different request
       |
       +--> No record yet / uncertain: pending reconciliation
~~~

**Not seeing the receipt on a read from a lagging secondary does not prove an abort.** Use appropriate read preference/read concern and bounded polling.

### 11.6. Idempotency Retention

If TTL deletes idempotency records after 24 hours while a client can replay events after 7 days, an old request may execute a second time.

Retention of business deduplication records must cover the **replay horizon, audit requirements, and side-effect risk**.

### 11.7. Transactional Outbox for Kafka/Email

A MongoDB transaction cannot roll back an email already sent or an HTTP call already delivered to a payment gateway.

~~~text
MongoDB transaction:
  create order
  reserve inventory
  insert outbox event
  commit

Background dispatcher:
  read outbox
  send event
  mark dispatched
~~~

The dispatcher can publish an event more than once if it crashes after sending and before marking dispatched, so consumers need event IDs and deduplication. **Outbox patterns typically deliver at-least-once semantics, not automatic exactly-once across every boundary.**

## 12. Runbook 1 — Handling `NotWritablePrimary` on a Replica Set

### 12.1. Defining the Symptoms

~~~text
2026-11-14T11:00:00Z checkout-api
  MongoCommandException: NotWritablePrimary, code=10107

2026-11-14T11:00:02Z checkout-api
  MongoTimeoutException: Timed out while selecting primary
~~~

Two consecutive errors may stem from the same primary election, yet you must inspect topology and logs to confirm.

### 12.2. Gather Data Before Touching the Cluster

Record:

1. Timestamps in a consistent timezone.
2. Namespace/operation and driver exception class.
3. Error code, labels, and transaction phase.
4. MongoDB driver/server versions.
5. Connection URI topology parameters with credentials redacted.
6. Replica set members and primary/election events.
7. Application timeouts, retry, and pool settings.
8. Duration and frequency of errors.
9. Successful requests, error rate, and p95/p99.

A restart that temporarily succeeds can mask persistent network/DNS root causes.

### 12.3. Inspect the Primary

In `mongosh`:

~~~javascript
db.adminCommand({ hello: 1 });
~~~

On an authorized replica set member:

~~~javascript
rs.status();
~~~

Determine whether a `PRIMARY` exists, which members are healthy, recent elections, host reachability, and majority availability. Never alter replica set config during read-only triage.

### 12.4. Inspect the Connection String

~~~text
mongodb://mongo1:27017,mongo2:27017,mongo3:27017/orders?replicaSet=rsOrders
~~~

Fix if:

- Pointing only at a secondary via `directConnection`.
- Wrong `replicaSet` name.
- Members advertise hostnames unresolvable by clients.
- Wrong port/TLS/SRV configuration.
- DNS/network policies block hosts listed in `rs.conf()`.

For managed deployments, prefer the official provider-issued URI.

### 12.5. Server-Selection Timeout

Example:

~~~text
serverSelectionTimeoutMS = 1000
primary election/discovery takes several seconds
~~~

The application times out before the driver discovers the new primary. Raising the timeout may fit some SLOs, yet **cannot fix** lost majority, wrong DNS, or blocked firewalls. Coordinate with HTTP deadlines, circuit breakers, and request retry budgets.

### 12.6. Connection Pool

If the primary is healthy yet the app still times out, check pool checkout waits, post-failover connection creation, socket exhaustion, thread starvation, and `MongoClient` instance counts.

Do not crank up `maxPoolSize` without measuring pool waits and server headroom.

### 12.7. Errors Only During Maintenance

~~~text
02:00:00 maintenance begins
02:00:03 primary election
02:00:04 NotWritablePrimary spike
02:00:08 new primary discovered
02:00:09 traffic recovered
~~~

A brief spike may be normal failover behavior. Still, if SLOs disallow request errors, inspect retries, buffering, and idempotency rather than ignoring user impact.

### 12.8. Never Do These Before Knowing Root Cause

- Restart all `mongod` nodes simultaneously.
- Repeatedly call `stepDown` in production.
- Alter priorities/votes to force a primary.
- Switch to `directConnection` pointing at a fixed node.
- Route writes to secondaries.
- Lower write concern regardless of durability requirements.
- Spin up infinite retry loops.

### 12.9. Sample Incident Report

~~~text
Symptom: NotWritablePrimary spike 7 seconds
Scope: checkout-api writes to replica set rsOrders
Evidence: election T1, new primary T2
Impact: 0.8% request errors, p99 doubled
Mitigation: bounded retry and idempotency
Follow-up: verify member reachability and election rate
~~~

## 13. Runbook 2 — Sudden Spike in `WriteConflict`

### 13.1. Recognition Pattern

~~~text
MongoCommandException: WriteConflict (112)
errorLabels: ["TransientTransactionError"]
~~~

When occurring inside a transaction body with `TransientTransactionError`, the driver can retry the attempt. Dense recurring conflicts signal a capacity or contention problem that must be addressed.

### 13.2. Investigation Questions

1. How many transaction attempts failed?
2. How many logical business operations succeeded?
3. Is there a hot document such as a global counter or stock record?
4. Have transaction durations grown?
5. Are there unindexed scans/aggregations inside the callback?
6. Did concurrency or peak traffic jump?
7. Are batch jobs updating the same documents?
8. Is a retry storm compounding contention?
9. Do errors occur in the body or commit?
10. Do business invariants hold after retries?

### 13.3. Hot Documents

~~~javascript
db.globalCounters.updateOne(
  { _id: "all-orders" },
  { $inc: { count: 1 } }
);
~~~

If every request contends to update one document, it is a hotspot. Consider sharded/distributed counters where semantics permit, asynchronous analytics, or conditional atomic updates within throughput limits.

Sharding a collection does not distribute a hot key if all writes still hit the same document/range.

### 13.4. Overly Long Transactions

~~~text
T1 begins
  -> find 1M documents
  -> CPU-heavy aggregation
  -> wait for REST API
  -> update hot inventory document
  -> commit
~~~

Shorten transactions:

- Use targeted indexed predicates.
- Move external I/O outside the callback.
- Project only required fields.
- Reduce documents touched per attempt.
- Keep reports/batch jobs off the hot path.
- Use conditional writes to enforce invariants.

### 13.5. Contention on an Inventory Document

~~~text
SKU-X available=100
100 concurrent transactions each reserves one unit
~~~

Measure throughput/latency under concurrency and compare:

- Single atomic update per document when only one document changes.
- Short transaction for order + reservation when atomicity is required.
- Partitioned inventory by location/batch if business rules allow.
- Queueing/serializing by hot SKU where appropriate.

Never weaken consistency to dodge conflicts if doing so causes overselling.

### 13.6. Optimistic Concurrency via Version

~~~javascript
db.products.updateOne(
  { _id: "SKU-X", version: 9 },
  {
    $set: { priceCents: NumberLong("12000") },
    $inc: { version: 1 }
  }
);
~~~

If `matchedCount=0`, the version changed or the record does not exist; the application re-reads and decides whether to retry or return a conflict. Version predicates provide optimistic concurrency, yet do not replace transactions when multi-document atomicity is needed.

### 13.7. Should You Increase Retry Attempts?

Track:

~~~text
successful business operations/second
body attempts per successful operation
transaction p95/p99
CPU/cache/disk pressure
failure rate after bounded retries
~~~

If attempts/s rise while successful throughput stays flat, fix contention instead of adding retries.

### 13.8. Technical Conflict vs. Business Conflict

Business conflict:

~~~text
matchedCount=0 because balance is insufficient
~~~

need not carry a server error code. The application must return a business rejection. `WriteConflict` is a technical error retryable per label/protocol. Keep separate metrics and alerts for both categories.

## 14. Runbook 3 — `UnknownTransactionCommitResult`

### 14.1. Risky Scenario

~~~text
Transfer T-1001:
  debit source
  credit destination
  insert receipt
  send commitTransaction
  socket timeout
~~~

Here you cannot conclude from the exception alone that **the commit failed**. The server may have committed while the response was lost in transit.

### 14.2. While Still in the Same Session

If the Java Driver still holds the **`ClientSession`/transaction** and the error carries **`UnknownTransactionCommitResult`**, retry the commit per driver rules:

~~~text
Same session
Same transaction identity
Retry commitTransaction
Do not rerun debit/credit body
~~~

Prefer **`withTransaction`** so the driver executes the protocol rather than hand-issuing commands.

### 14.3. When the HTTP Request/Session Is Gone

Suppose the server process crashed after sending commit. You cannot open a new session and resume the old session's commit.

Use a **durable business receipt / idempotency key**:

1. Extract the transfer ID from the original request.
2. Read the receipt from the primary with appropriate consistency.
3. Compare immutable payload fields: amount, currency, source, and destination.
4. If `COMMITTED` and matching, return the stored result.
5. If mismatched, report idempotency key misuse.
6. If no record exists yet and outcome remains uncertain, mark pending reconciliation with deadline/backoff.
7. Never generate a different transfer ID to debit immediately again.

### 14.4. One Missing Receipt Read Is Insufficient

A single read against a lagging secondary or during an election does not prove the transaction aborted. Implement **bounded polling, majority/primary read consistency, and a reconciliation policy**; if unresolved, keep the state `UNKNOWN`.

### 14.5. Status API Example

~~~http
GET /transfers/T-1001
~~~

Possible responses:

~~~json
{
  "transferId": "T-1001",
  "state": "COMMITTED",
  "amountUnits": 150000
}
~~~

or:

~~~json
{
  "transferId": "T-1001",
  "state": "PENDING_RECONCILIATION"
}
~~~

Do not collapse "commit not yet observed" and "confirmed failed" into a single `FAILED` state if business flows distinguish them.

### 14.6. Never Compensate Solely Because of a Timeout

Compensating/reversal transactions require **confirmed business state**, authorization, and auditing. If the initial transfer never committed yet the system immediately reverses it, balances become wrong.

### 14.7. After Resolution

Verify:

~~~text
Exactly one transfer receipt
Source balance changed once
Destination balance changed once
No unexpected compensating transfer
No unowned pending reconciliation
~~~

## 15. Runbook 4 — Server Selection Timeout, Network Timeout, and Write Concern

### 15.1. Server Selection Timeout

~~~text
MongoTimeoutException:
  Timed out while selecting a server
  matching WritableServerSelector
~~~

The driver could not locate an eligible primary. Investigate:

- Does the replica set have a `PRIMARY`?
- Is the driver topology snapshot stale?
- Are member hosts in `rs.conf()` reachable?
- DNS/TLS/authentication or firewalls?
- Network partitions or proxy interference?
- Timeout/pool configuration?

Do not weaken durability or retry `$inc` indefinitely.

### 15.2. Network Timeout After Sending a Write

~~~text
Client sent write
Network lost before response
~~~

The write outcome may be unknown. With driver-supported retryable writes, the driver retries per protocol. HTTP/gateways may resend the logical business operation, so business idempotency remains mandatory.

### 15.3. Write Concern Timeout

Writes with **`w: majority`** may fail to receive acknowledgment within the deadline due to replication lag/availability. **A write concern timeout does not prove the primary did not apply the write.**

Inside transactions, inspect commit results and error labels; never fire a brand-new business transaction immediately after a write concern timeout.

### 15.4. Loss of Majority

If a three-voting-member replica set has only one reachable node, elections and majority writes cannot proceed.

Check member states/connectivity, replication lag, disk/network, and write concern errors, then recover per approved runbook. Never drop **`w: majority`** to `w:1` if the business requires majority durability.

### 15.5. Distinguishing Client Failure from Server Failure

If one application service hits server selection timeouts while another stays healthy, suspect app-specific DNS, network segments, driver versions, URIs/pools, or proxies/TLS.

Never declare the entire cluster down based on a single client instance.

## 16. Read-Only Diagnostics in `mongosh`

The following commands require appropriate privileges. Output varies by MongoDB version and may contain hostnames/infrastructure metadata, so redact sensitive details before sharing.

### 16.1. `hello`

~~~javascript
const hello = db.adminCommand({ hello: 1 });

printjson({
  setName: hello.setName,
  isWritablePrimary: hello.isWritablePrimary,
  secondary: hello.secondary,
  primary: hello.primary,
  hosts: hello.hosts
});
~~~

`hello` provides a point-in-time snapshot of that server's state, not cluster-wide replica set monitoring.

### 16.2. `rs.status()`

~~~javascript
const status = rs.status();

printjson({
  set: status.set,
  myState: status.myState,
  members: status.members && status.members.map(member => ({
    name: member.name,
    stateStr: member.stateStr,
    health: member.health,
    optimeDate: member.optimeDate
  }))
});
~~~

Fields vary/may be absent across versions. Never infer commit outcomes from a single member's `optime` without understanding replication consistency.

### 16.3. `serverStatus()`

~~~javascript
const s = db.adminCommand({ serverStatus: 1 });

printjson({
  uptime: s.uptime,
  connections: s.connections,
  opcounters: s.opcounters,
  transactions: s.transactions,
  wiredTigerCache: s.wiredTiger
    ? s.wiredTiger.cache
    : undefined
});
~~~

`serverStatus` exposes transaction and WiredTiger cache counters/gauges depending on version/storage engine. Do not assume every field is always present.

### 16.4. Current Operations and Profiler

**`currentOp`/`$currentOp`** inspects active operations per server version. Note:

- Output is a brief snapshot.
- It may expose sensitive query text/namespaces.
- Avoid unbounded full scans at tight scrape intervals.
- Profiling incurs overhead and must follow change/monitoring policies.

Prefer properly sampled logs, traces, and query-shape metrics.

### 16.5. Java Driver Command Monitoring

The Java Sync Driver supports **`CommandListener`** and connection/server monitoring. Use those APIs to distinguish:

~~~text
Command: update
Command: insert
Command: commitTransaction
Command: abortTransaction
~~~

Never log raw commands containing PII, tokens, or balances. Log only command name, duration, sanitized request trace ID, and error class/code/labels.

### 16.6. Rates Instead of Cumulative Counters

Illustrative counter calculation:

~~~text
writeConflicts(t0) = 1000
writeConflicts(t1) = 1120
elapsed = 60 seconds
rate = (1120 - 1000) / 60 = 2 conflicts/s
~~~

Counters reset on `mongod` restarts; collectors must detect resets and correlate timestamps/source nodes. Exact metric names come from your dashboard/provider/server version.

### 16.7. Attempts Differ from Business Successes

~~~text
One logical checkout:
  attempt 1 = aborted
  attempt 2 = aborted
  attempt 3 = committed

Transaction attempts = 3
Business orders created = 1
~~~

Never report retry or transaction attempt counts as created business orders.

## 17. Metrics and Alerts for Transient Errors

### 17.1. Application Metrics

| Conceptual metric | Meaning | Bounded labels |
|---|---|---|
| **`mongo.tx.attempts`** | Transaction body attempts. | `service`, `operation`. |
| **`mongo.tx.committed`** | Confirmed committed attempts. | `operation`. |
| **`mongo.tx.aborted`** | Aborted attempts. | `operation`, `error category`. |
| **`mongo.tx.body.retries`** | Body retries. | `operation`, `error category`. |
| **`mongo.tx.commit.retries`** | Commit retries. | `operation`. |
| **`mongo.tx.unknown.outcomes`** | Unknown commit outcomes. | `operation`. |
| **`mongo.write.conflicts`** | Observed technical write conflicts. | `collection`/`operation` where appropriate. |
| **`mongo.server.selection.timeouts`** | Failed waits for writable server. | `service`, `cluster`. |
| **`mongo.not.primary`** | `NotWritablePrimary` occurrences. | `service`, `cluster`. |
| **`mongo.tx.duration`** | Transaction p50/p95/p99. | `operation`. |
| **`business.idempotency.hits`** | Replays returning stored records. | `operation`. |
| **`business.reconcile.pending`** | Unresolved unknown-outcome requests. | `service`. |

These are **application-defined metric names**, not built-in MongoDB fields. Never use `transferId`/`customerId` with millions of values as metric labels; they cause cardinality explosions and leak data.

### 17.2. Tracking Attempts Per Successful Business Operation

~~~text
bodyAttempts = 10000
successes = 8000
averageAttemptsPerSuccess = 1.25
~~~

Interpret carefully when failed business requests exist; compute per trace/request ID rather than blindly dividing total counters. If attempts/s climb while successful throughput stalls, retries are overloading the system.

### 17.3. Alert on Trends Rather Than Single Errors

~~~text
NotWritablePrimary short spike
  + election
  + fast automatic recovery
  -> operational event; assess SLO impact

NotWritablePrimary persistent
  + no primary observed
  -> high-severity availability investigation

WriteConflict sustained increase
  + transaction p99 increase
  -> contention/root-cause investigation

UnknownTransactionCommitResult
  + reconciliation pending increasing
  -> protect business consistency and expedite resolution
~~~

Do not trigger Critical pages just because a transaction legitimately aborted on a business validation rule.

### 17.4. Layered Dashboards

~~~text
Application SLO:
  successful requests/sec, errors, p95/p99

MongoDB Driver:
  server-selection, pool waits, network failures

Replica Set:
  elections, primary health, replication lag

Transaction:
  duration, commit/abort, retries, unknown outcomes

Data Correctness:
  unique receipts, idempotency, reconciliation backlog
~~~

A dashboard showing only CPU and disk cannot diagnose unknown commit errors.

### 17.5. Correlation IDs and Logs

Log:

~~~text
traceId=trace-123
operation=reserveInventory
phase=transaction-body
attempt=2
errorCode=112
errorLabel=TransientTransactionError
outcome=RETRYING
~~~

Separate **transaction attempt number**, **commit attempt number**, and **logical request ID** in instrumentation. Never use MongoDB's raw `lsid`/transaction number as a business idempotency key.

### 17.6. Privacy Guardrails

Logs and error reports must exclude:

- Raw passwords or connection strings.
- JWTs/access tokens.
- Full BSON documents containing PII.
- Account balances where policy forbids.
- Raw merchant/customer IDs as metric labels.

Minimize data while preserving diagnostic fields: error category/code/label, service, operation, latency, and anonymized trace ID.

## 18. Designing a Lab Environment to Reproduce Errors

To prove the application handles errors properly, test against a **real replica set**, not just mocks throwing exceptions.

### 18.1. Test Levels by Capability

| Environment | What it tests well | Limitations |
|---|---|---|
| Unit test/mock | Error label classification, backoff, idempotency decisions. | Does not prove MongoDB transaction atomicity or elections. |
| Single-node replica set | Commit/abort, session wiring, app-level write conflicts. | Cannot test primary failover to another node. |
| Three-member replica set | Elections, majority availability, secondary lag, connection recovery. | Three containers on one host do not simulate losing a datacenter. |
| Network proxy/fault-injector lab | Dropping/delaying connections, partial network faults. | Exact timing of commit/ACK loss can be hard to pin down. |

Test fixtures need dedicated databases, pre-created indexes, unique request IDs, explicit timeouts, and cleanup restricted to lab resources.

### 18.2. Setting Up a Test Single-Node Replica Set

Example on an **isolated** Unix-like host with `mongod`:

~~~bash
mkdir -p /tmp/mongodb-errors-lab

mongod \
  --replSet rsErrorLab \
  --bind_ip localhost \
  --port 27018 \
  --dbpath /tmp/mongodb-errors-lab
~~~

In `mongosh` connected to port 27018:

~~~javascript
rs.initiate({
  _id: "rsErrorLab",
  members: [{ _id: 0, host: "localhost:27018" }]
});
~~~

Wait for `PRIMARY` via polling/`rs.status`. Never use the `dbpath` or port of a MongoDB instance holding real data. In Docker/Kubernetes, hostnames must resolve from the **process running the driver**, not only inside the container.

### 18.3. Seeding Test Accounts and Receipt Collections

~~~javascript
const lab = db.getSiblingDB("app_test");

lab.createCollection("accounts");
lab.createCollection("transfer_receipts");

lab.accounts.insertMany([
  { _id: "A", balanceUnits: NumberLong("1000") },
  { _id: "B", balanceUnits: NumberLong("300") }
]);
~~~

Seed only into empty lab-owned collections/databases. For re-runs, use fresh IDs/prefixes or isolated fixtures; never drop an entire shared database.

### 18.4. Testing Application-Level Abort

In `mongosh`:

~~~javascript
const session = db.getMongo().startSession();
const sdb = session.getDatabase("app_test");

session.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" }
});

try {
  sdb.accounts.updateOne(
    { _id: "A" },
    { $inc: { balanceUnits: NumberLong("-200") } }
  );

  throw new Error("Injected lab failure before credit");

} catch (error) {
  session.abortTransaction();
} finally {
  session.endSession();
}
~~~

After aborting, read from the primary and confirm A is still 1000 and B is still 300. This tests atomic abort—**not `NotWritablePrimary` or server `WriteConflict`**.

### 18.5. Testing `WriteConflict` Across Two Sessions

Test outline:

~~~text
T1 startTransaction
T2 startTransaction
T1 read account A
T2 read account A
T1 update A
T2 try update A
Observe conflict/abort/retry behavior
~~~

Note: pending writes and transaction snapshots can vary in timing across versions/drivers. To keep tests deterministic, use **barriers/latches** and **deadlines**, not arbitrary sleeps.

After the test, verify **accurate balances and zero double effects**. Error labels may vary by scenario; record actual observations.

### 18.6. Fault Injection with `failCommand`

MongoDB provides **`configureFailPoint` / `failCommand`** for test environments on supported builds/deployments.

**Lab-only** example:

~~~javascript
db.adminCommand({
  configureFailPoint: "failCommand",
  mode: { times: 1 },
  data: {
    failCommands: ["commitTransaction"],
    closeConnection: true
  }
});
~~~

This experiment breaks the connection on the commit command while the failpoint is active. **It does not guarantee the server committed and then dropped the response**; the failpoint may intercept before command execution.

Tests should verify:

- Driver exceptions/labels.
- Retry behavior.
- Durability/invariants after recovery.
- Business request idempotency.

Never claim "server committed before failure" unless timing was controlled and observed.

### 18.7. Disabling the Failpoint After Testing

~~~javascript
db.adminCommand({
  configureFailPoint: "failCommand",
  mode: "off"
});
~~~

If failpoints are unsupported or blocked by a managed provider, use a test harness or network proxy instead. **Never grant broad production privileges** just to enable failpoints.

### 18.8. Primary Stepdown in a Multi-Node Lab

When primary and secondaries are healthy:

~~~javascript
rs.stepDown(15);
~~~

This instructs the primary to step down per supported behavior, triggering an election. Run only in an **isolated lab**, expecting brief test connection drops and requiring appropriate privileges.

Inspect:

1. When do clients observe `NotWritablePrimary`/server-selection errors?
2. Is a new primary elected?
3. How long does driver reconnection take?
4. Do in-flight transactions abort/retry or report unknown commit?
5. After recovery, are persisted state and receipts accurate?

Never run `stepDown` on a production or shared replica set for practice.

### 18.9. Network Proxy for Testing Retries

~~~text
Java test app
     |
     v
Fault injection proxy
     |
     v
Replica set
~~~

A proxy can inject packet loss, delayed responses, or closed connections per scenario. Still, "dropping the response after commit completes" requires tight synchronization. Without proof, report only **network fault near commit**.

### 18.10. Do Not Mix Three Faults at Once

Each new test should inject a single fault type:

~~~text
Test A: application exception after debit
Test B: write conflict during transaction
Test C: primary stepdown during body
Test D: connection interruption around commit
~~~

Only after verifying each failure individually should you run combined chaos/soak tests. Document timeouts and preconditions for reproducibility.

## 19. Test Matrix: Faults, Expectations, and Verification

| Test | Fault injection | Expected |
|---|---|---|
| Happy path | None | Account A debited, B credited, exactly one receipt. |
| Business reject | Insufficient funds | No commit, no infinite retries. |
| Explicit abort | Throw after debit | Debit rolled back, no receipt. |
| Missing session | Write outside session | Negative test showing un-rolled-back write. |
| `WriteConflict` | Two transactions update same doc | Retry attempt per label, no double update. |
| `NotWritablePrimary` | Stepdown in lab | Driver recovers topology, retries right scope. |
| Server selection timeout | No writable primary in lab | Bounded failure, no infinite loop. |
| Unknown commit result | Network fault near commit | Retry commit when possible; durable outcome reconciliation. |
| Duplicate business key | Same request sent twice | No double debit; return existing result. |
| Key reused with different payload | Keep key, change amount | Conflict; do not commit new request. |
| Two concurrent same-key requests | Barrier + unique receipt | Single business effect; race reconciled. |
| Write concern timeout | Majority unavailable in lab | Do not treat response timeout as proof of abort. |
| Secondary stale read | Read from lagging secondary | Do not conclude commit rolled back from stale data. |
| Pool exhaustion | Controlled load generator | Bounded wait/timeout with metrics. |
| External side effect | Callback retries | No duplicate external publish; outbox/dedup. |

### 19.1. Assertions Must Verify Committed State

~~~text
Before:
  A = 1000
  B = 300
  Sum = 1300

After committed transfer of 200:
  A = 800
  B = 500
  Sum = 1300
  ReceiptCount(requestId) = 1
~~~

After abort:

~~~text
  A = 1000
  B = 300
  ReceiptCount(requestId) = 0
~~~

**A thrown exception is not proof of rollback** if an update accidentally ran outside the session. Re-read persisted data using appropriate read consistency.

### 19.2. Test Retries at Both Levels

- **Internal driver retry:** body/commit logic per error labels.
- **External business retry:** HTTP/message replay with stable idempotency keys.

A test verifying only internal retries does not prove the endpoint is safe when an HTTP response drops after commit.

### 19.3. `UNKNOWN` Can Be a Valid Expected Outcome

If a lab network outage outlasts the request deadline, the application cannot determine the commit outcome immediately. An API returning **pending/unknown** with reconciliation is far safer than falsely reporting failure and re-executing the business effect.

### 19.4. Use Polling with Deadlines

Never write:

~~~text
sleep(100 milliseconds)
assert election completed
~~~

Election and network recovery times vary. Poll until the condition is observed or the deadline expires, capturing diagnostics on timeout.

### 19.5. Observe the Right Primary

Reading from a lagging secondary returns stale state. Specify read preference/read concern for test assertions; for durability tests, use observation policies consistent with majority commits.

## 20. Common Implementation Mistakes

### 20.1. Retrying Every `MongoException`

~~~java
catch (MongoException ex) {
    return retryEverything();
}
~~~

Wrong because `MongoException` covers `DuplicateKey`, `Unauthorized`, invalid schema, `WriteConflict`, server-selection timeout, and unknown commit. Each requires different retry scopes.

### 20.2. Retrying `$inc` with a Fresh Command

~~~text
First $inc executed, response lost
Application sends independent $inc again
Counter increases twice
~~~

The driver's retryable-write protocol differs from an application loop firing fresh commands. Use driver-managed retries or business idempotency.

### 20.3. Ignoring `TransientTransactionError`

If a transaction body fails with a transient `WriteConflict`, never continue the old attempt as if nothing happened. Retry the **entire transaction** in a fresh attempt, re-reading conditions.

### 20.4. Retrying Body on Unknown Commit

~~~text
commitTransaction -> response lost
application immediately reruns debit and credit
~~~

The first transaction may have committed. Retry **the same transaction commit** or reconcile the receipt; never debit again.

### 20.5. Generating Idempotency Keys Inside the Callback

~~~java
session.withTransaction(() -> {
    String requestId = UUID.randomUUID().toString();
    // ...
});
~~~

Replaying the callback generates a new ID, breaking deduplication. Generate stable business keys before the callback and reuse them across HTTP retries.

### 20.6. Catching Exceptions and Letting Spring Commit

~~~java
@Transactional
public void badOperation() {
    try {
        updateOne();
        updateTwo();
    } catch (Exception ex) {
        // Swallowed: transaction manager may commit.
    }
}
~~~

Propagate exceptions or mark rollback per Spring transaction policy. Checked vs. unchecked exceptions have different default rollback rules.

### 20.7. Mixing Clients/Sessions

~~~text
ClientSession created from client A
Repository/driver operation uses client B without that session
~~~

Operations must bind to the exact session context. Creating a separate `MongoClient` inside a transactional method causes writes outside the transaction.

### 20.8. Hardcoding the Primary

A `directConnection` URI to `node01` may run fine for months and then constantly fail with `NotWritablePrimary` when `node01` steps down. Use a replica set URI and driver SDAM.

### 20.9. Raising Timeouts Without Fixing DNS

If the driver cannot resolve member hosts, raising `serverSelectionTimeoutMS` only makes users wait longer. Fix the URI/network.

### 20.10. Arbitrarily Lowering Write Concern

Replacing `majority` with `w:1` alters durability and failover guarantees. Never do it as a default workaround without business risk analysis.

### 20.11. Measuring Only Retry Attempts, Not Successful Throughput

~~~text
Retries/sec: 1000
Successful orders/sec: 50
~~~

More retries do not mean more successful business work. Measure p95/p99, successful QPS, and error budgets.

### 20.12. Testing Elections with Short Sleeps

Election timing varies. Poll for `PRIMARY`/recovery with deadlines and diagnostics.

### 20.13. Reading Stale Secondary and Assuming Rollback

Secondary lag can return old state even after the primary committed. Use appropriate read consistency.

### 20.14. Skipping `matchedCount` Checks

A transaction can commit even when an update matched nothing. For balance or inventory checks, `matchedCount=0` must trigger business rejection and abort.

### 20.15. Treating `DuplicateKey` as Transient

Read the existing record and compare immutable parameters; the same request can return the prior result, whereas a different request is a conflict.

### 20.16. Changing the ID on Every Retry Despite a Unique Index

If every HTTP retry mints a new request ID, the unique index cannot detect duplicate business requests.

### 20.17. Publishing Messages Inside the Callback

Callbacks can replay after `WriteConflict`; Kafka/email cannot roll back with MongoDB. Use an outbox and consumer deduplication.

### 20.18. Long Transactions

Long transactions increase snapshot/cache pressure, timeouts, and conflicts. Keep callbacks short, indexed, and free of external I/O waits.

### 20.19. Retry Storms

~~~text
100 service replicas
x 500 in-flight requests
x 5 immediate retries
= up to 250000 operation attempts
~~~

This illustrates an upper-bound workload calculation; actual numbers depend on controls. Use deadlines, jitter, backpressure, and circuit breakers.

### 20.20. Routing Writes to Secondaries

Secondaries do not accept normal application writes in a replica set. Fix topology/driver/election issues instead of bypassing the primary.

### 20.21. Ignoring Write Concern Failures Because "The Document Was Seen"

A write concern timeout does not prove majority durability was reached, even if the primary applied the write. Reconcile and verify durability per contract.

### 20.22. Collapsing `UNKNOWN` into `FAILED`

If an API exposes only `SUCCESS`/`FAILED` and timeouts become `FAILED`, callers may resend with a new ID. Expose pending/unknown states with reconciliation.

### 20.23. Unscoped Failpoint Testing

`failCommand`, network proxies, and `rs.stepDown` impact availability. Run only in isolated labs and clean up failpoints immediately afterward.

### 20.24. Failing to Retain Diagnostic Context

Elections can last mere seconds. Log redacted error codes, labels, phases, driver versions, and timestamps for post-incident analysis.

## 21. Error-Handling Decision Flowchart

~~~text
MongoDB operation failed
           |
           v
Is it inside a transaction?
       |
   +---+----+
   |        |
  NO       YES
   |        |
   v        v
Check     Which phase?
retryable    |
write     +--+-------+
protocol  |          |
          v          v
        Body       Commit
          |          |
          v          v
    TransientTx?  UnknownCommit?
       |             |
    +--+--+       +--+---+
    |     |       |      |
   YES    NO     YES     NO
    |     |       |      |
    v     v       v      v
   Retry Classify Retry   Classify
   whole business same   failure/
   body  /config  commit reconcile
         issue

Always:
  stable business key
  bounded retry/deadline
  observable outcomes
  persisted correctness checks
~~~

**COMMITTED:** return result; do not debit again.

**ABORTED:** retry the whole transaction if transient and the request remains valid.

**UNKNOWN:** retry commit for the same transaction while context exists, or reconcile via durable business receipt.

### 21.1. Transient Errors Can Still Cause Major Incidents

~~~text
Without retry: p95 30 ms
With 3 attempts: p95 400 ms
~~~

Technically successful retries can still violate SLOs. Retries are a recovery mechanism, **not a substitute for root-cause remediation**.

## 22. Investigation and Prevention Checklists

### 22.1. Incident Triage

- [ ] Recorded timestamp, time zone, service name, operation, and environment.
- [ ] Captured exception class, error code, labels, and transaction phase.
- [ ] Distinguished server-selection errors from server command errors.
- [ ] Checked whether a primary exists or an election is occurring.
- [ ] Verified member hostnames/DNS/TLS/network reachability.
- [ ] Verified `replicaSet` name and driver connection URI.
- [ ] Checked majority availability and replication lag.
- [ ] Recorded driver/server versions and supported retry behaviors.
- [ ] Captured app-layer error/timeout/p95/p99 and successful QPS.
- [ ] Avoided blindly modifying topology before gathering evidence.

### 22.2. Investigating `WriteConflict`

- [ ] Measured conflict rate, total attempts, and business successes.
- [ ] Identified hot documents/keys and top query shapes.
- [ ] Measured transaction p50/p95/p99 duration.
- [ ] Checked indexes for reads/updates inside transactions.
- [ ] Checked for long-running transactions and batch jobs.
- [ ] Separated business validation failures from technical conflicts.
- [ ] Tested concurrent updates using barriers/deadlines.
- [ ] Verified conditional predicates and `matchedCount` checks.
- [ ] Configured bounded retries/backoff instead of infinite retries.
- [ ] Considered schema/partitioning/queueing if conflicts persist.

### 22.3. Investigating Transaction Retries

- [ ] Distinguished `TransientTransactionError` from `UnknownTransactionCommitResult`.
- [ ] Transient body errors retried in a fresh transaction attempt.
- [ ] Unknown commit outcomes retried on the same transaction while context exists.
- [ ] Callbacks invoke no external side effects.
- [ ] Request IDs remain stable across attempts and HTTP retries.
- [ ] Unique receipt key checks matching parameters.
- [ ] Concurrent same-key races handled properly.
- [ ] `UNKNOWN`/pending outcome returned when deadline expires.
- [ ] Reconciliation worker/status endpoint implemented.
- [ ] Unknown outcomes never treated directly as definitely aborted.

### 22.4. Spring Data

- [ ] `MongoTransactionManager` registered properly.
- [ ] `@Transactional` names the right manager if multiple exist.
- [ ] Calls go through the Spring proxy, avoiding self-invocation.
- [ ] Exception propagation and `rollbackFor` rules are explicit.
- [ ] `MongoTemplate`/repositories use session-bound operations.
- [ ] No separate raw `MongoClient` created inside transactions.
- [ ] Outer retries start fresh transaction attempts when appropriate.
- [ ] Never blindly retry whole `@Transactional` methods after unknown commits.
- [ ] Reactive code does not accidentally re-subscribe side-effect pipelines.

### 22.5. Testing and Operations

- [ ] Commit/abort tests run against a real replica set.
- [ ] `WriteConflict` and duplicate race tests implemented.
- [ ] Failover tested in a multi-node lab when needed.
- [ ] Fault injection never executed in production.
- [ ] Failpoints/proxy faults cleaned up afterward.
- [ ] Persisted state read back with explicit read consistency.
- [ ] Recovery never asserted using fixed `sleep` calls.
- [ ] Logs redacted; metrics keep low label cardinality.
- [ ] Alerts based on error rate + SLO impact + reconciliation backlog.
- [ ] Runbooks and owners assigned for pending outcomes.

## 23. Hands-On Practice

These exercises use an isolated lab replica set. Without a three-member environment, complete the modeling/test-design portions instead of forcing a primary stepdown.

### Exercise 1 — Classify Three Errors

Given:

~~~text
NotWritablePrimary (10107)
WriteConflict (112)
UnknownTransactionCommitResult
~~~

Describe the origin, retry scope, and diagnostic data to inspect for each case.

### Exercise 2 — Election Lifecycle

Draw the timeline: P1 primary → P1 stepdown → no-primary window → P2 primary → driver discovers P2. Why can a request fail during the transition?

### Exercise 3 — Direct Connection

An application URI targets one secondary with `directConnection=true`. Why won't retrying with the same URI fix `NotWritablePrimary`?

### Exercise 4 — Replica Set URI

Write a URI with three seed hosts and `replicaSet=rsApp`; list the DNS/TLS/port prerequisites that must hold.

### Exercise 5 — Server Selection Timeout

Describe a scenario where the driver fails to find a writable primary before sending a command. How does this differ from a `mongod` returning `NotWritablePrimary`?

### Exercise 6 — `hello`

Write a read-only `mongosh` command returning `isWritablePrimary`, `setName`, `secondary`, and `primary`. Why is that output only a snapshot?

### Exercise 7 — `rs.status`

In a lab replica set, use `rs.status()` to inspect member states. Which clues indicate the cluster currently lacks a writable primary?

### Exercise 8 — `NotPrimaryNoSecondaryOk`

Explain why read-eligibility errors do not always share the same root cause as `NotWritablePrimary` on the write path.

### Exercise 9 — `WriteConflict` on the Same Document

Create two sessions, each running a transaction updating Account A. Outline a barrier-synchronized test harness, capturing error labels and final persisted balances.

### Exercise 10 — Business Conflict

Account A holds 100 units; a request wants to debit 150. Write a conditional update checking `balance >= amount`. How must `matchedCount=0` be handled?

### Exercise 11 — Hot Counter

1,000 concurrent checkout requests all update document `_id=all-orders`. Why does contention spike? Compare one atomic counter against distributed counters/event aggregation.

### Exercise 12 — Long Transaction

A callback scans 1 million documents, calls a REST service, and then updates inventory. List four reasons this increases conflicts and how to shorten it.

### Exercise 13 — Adding an Index

A transaction updates orders by `tenantId`, `status`, and `createdAt`. If the query scans 500,000 documents, show how `explain`/index design shrinks transaction duration.

### Exercise 14 — Optimistic Version

Write an `updateOne` using `version=7`, `$set` price, and `$inc` version. When `matchedCount=0`, should you retry unconditionally without re-reading?

### Exercise 15 — Error Label

In Java, write code checking `exception.hasErrorLabel("TransientTransactionError")`. When this label appears in the body, what is the right retry action?

### Exercise 16 — Unknown Commit Label

Write code classifying `UnknownTransactionCommitResult`. Why can immediately re-running the body cause a double debit?

### Exercise 17 — Two-Loop Retry

Sketch the `OUTER` loop for the body and `INNER` loop for the commit. Specify which error label triggers each loop.

### Exercise 18 — `retryWrites`

Distinguish `retryWrites=true` for a supported command from a custom `while` loop independently firing `$inc`.

### Exercise 19 — Timeout Does Not Prove Failure

An insert/update reaches the server, yet the response is lost. What must you verify before re-issuing a business request?

### Exercise 20 — Write Concern Timeout

Replica set majority acknowledgment times out. Can you conclude the primary never applied the document? Why or why not?

### Exercise 21 — Java `withTransaction`

Write Java Sync Driver code opening a `ClientSession` and using `withTransaction` with `ReadConcern.SNAPSHOT`, `WriteConcern.MAJORITY`, and `ReadPreference.primary()`.

### Exercise 22 — Missing Session Argument

Inside a transaction body, one `updateOne` omits `ClientSession`. Upon abort, what happens? Design a negative integration test for this.

### Exercise 23 — Duplicate Business Key

Two transfers share the same `requestId` but differ in `amount`. Should the server return the existing result or a conflict? Explain.

### Exercise 24 — Resending the Same Request

Transfer T1 committed, yet the HTTP response was lost. The client resends the same idempotency key. Specify the database outcome and correct HTTP response.

### Exercise 25 — Concurrent Same-Key Race

Two clients with the same `requestId` start concurrently and neither sees a receipt yet. How do unique `_id` and transactions help? What must the app still reconcile?

### Exercise 26 — Callback Side Effects

Why does publishing a Kafka event inside a `withTransaction` callback risk duplicates or out-of-sync state? Propose a transactional outbox.

### Exercise 27 — Event Deduplication

An outbox dispatcher publishes successfully and crashes before marking `SENT`. How many times might the consumer receive the event? Design deduplication using `eventId`.

### Exercise 28 — Spring Transaction Manager

Write a `@Bean MongoTransactionManager` and `@Transactional` service. State the conditions required for the Spring proxy to apply transactions.

### Exercise 29 — Self-Invocation

A method calls `this.reserve()` on the same bean; `reserve()` has `@Transactional`. Why might no transaction open?

### Exercise 30 — Swallowed Exception

A `@Transactional` method catches `RuntimeException` and returns normally. Why does data risk committing? Fix via propagation or rollback marking.

### Exercise 31 — Retryable vs. Permanent Spring Exceptions

Spring wraps MongoDB exceptions into `DataAccessException`. How do you preserve root causes/codes/labels without retrying every `DataAccessException`?

### Exercise 32 — Reactive Retry

A reactive transaction pipeline places `retry()` over the entire stream. Which side effects can re-run? Why is proper context/session handling essential?

### Exercise 33 — Request Deadline

The API deadline is 2 seconds, while primary election takes 8 seconds. Design bounded failure/pending statuses and reconciliation instead of infinite retries.

### Exercise 34 — Retry Storm

50 instances, each with 200 in-flight requests retrying 5 times. Compute maximum attempts if all trigger; propose backpressure and budgets.

### Exercise 35 — Three-Node Failover

Design a lab test triggering primary stepdown mid-transaction body. How do you observe topology recovery and final data invariants?

### Exercise 36 — Commit Fault Injection

Explain why `failCommand` with `closeConnection` on commit does not reliably simulate "server committed then dropped response." Which expectations can still be verified?

### Exercise 37 — Failpoint Cleanup

Write the `mode:"off"` command for `failCommand` and explain why cleanup immediately after lab tests is critical.

### Exercise 38 — Secondary Lag

After a confirmed commit, a secondary read returns stale state. Why can't you conclude the transaction rolled back? Propose proper read observation.

### Exercise 39 — Counter Rate

A MongoDB counter rises from 3,000 to 3,180 in 60 seconds. Compute the rate. What must be handled if the process restarts between samples?

### Exercise 40 — App Dashboard

Design a dashboard separating `NotWritablePrimary`/sec, `WriteConflict`/sec, body retries, commit retries, p99 latency, successful orders/sec, and pending reconciliations.

### Exercise 41 — DNS vs. Database

Only one application in subnet X cannot resolve member hostnames; other apps are healthy. Which investigation path takes priority?

### Exercise 42 — Majority Durability

Someone proposes lowering `writeConcern` from `majority` to `w:1` to fix timeouts. Which durability and business risks must be analyzed?

### Exercise 43 — Retry vs. Schema

A transaction fails repeatedly due to a missing required field or invalid BSON. Why shouldn't an infinite retry be attached?

### Exercise 44 — Abort vs. Compensation

A transfer already committed, yet the business wants a refund. Why can't `abortTransaction` do this? Propose a compensating transaction.

### Exercise 45 — Incident Review

An incident shows:

~~~text
NotWritablePrimary spike: 20 seconds
WriteConflict rate: 100/s
HTTP p99: 4 seconds
Unknown commit outcomes: 120
Reconciliation backlog: 80
~~~

Outline the investigation and mitigation sequence: replica set health, driver/URI, contention, retry policy, idempotency, and reconciliation. Do not propose mass restarts or direct edits to replica set metadata.

## 24. Review Questions

1. What does `NotWritablePrimary` mean in a replica set?
2. Why can `NotWritablePrimary` appear briefly during an election?
3. What is the responsibility of driver SDAM?
4. What write problem does a `directConnection` URI to a secondary cause?
5. How does a server selection timeout differ from MongoDB returning `NotWritablePrimary`?
6. Which DNS/network factors can stop the driver from finding a primary?
7. Why doesn't raising `serverSelectionTimeoutMS` fix a replica set lacking majority?
8. Does seeing a `PRIMARY` in `rs.status` prove every application routes writes properly?
9. What is the standard MongoDB error code for `WriteConflict`?
10. Why can `WriteConflict` happen when two transactions update the same document?
11. How do long transactions raise contention and write-conflict risks?
12. How can a hot counter document bottleneck throughput?
13. Does adding shards automatically fix a single hot document?
14. How does optimistic concurrency via a version predicate work?
15. How does `WriteConflict` differ from `DuplicateKey` in retry semantics?
16. How does `WriteConflict` differ from a business predicate yielding `matchedCount=0`?
17. Should `LockTimeout` and `WriteConflict` be collapsed into one exception type?
18. What kinds of write conflicts can MongoDB retry automatically at the storage/operation level?
19. How do error codes, error labels, and driver exception types differ?
20. What does `TransientTransactionError` generally signify?
21. Upon seeing `TransientTransactionError` in the body, should you continue the old attempt?
22. Why must transaction retries re-execute reads and business checks?
23. Does `UnknownTransactionCommitResult` guarantee the commit failed?
24. When the commit result is unknown, should you retry the body or retry the commit?
25. Why must a commit retry preserve the same transaction identity?
26. Is `NoSuchTransaction` absolute proof that debiting again is safe?
27. How does `retryWrites=true` differ from application-level business request retries?
28. What risk arises if an application resends `$inc` after a timeout?
29. Why is a stable idempotency key needed across HTTP requests?
30. Does a unique index automatically compare payloads of two requests sharing a key?
31. How should an app handle the same key with a different payload?
32. During concurrent duplicate requests, why might one call get `DuplicateKey` even for the same business request?
33. What does not seeing a receipt on a lagging secondary prove?
34. Why are three states (`COMMITTED`/`ABORTED`/`UNKNOWN`) necessary?
35. Can Java `ClientSession.withTransaction` invoke the callback multiple times?
36. Why must you avoid sending emails/Kafka events inside a transaction callback?
37. What happens if an operation inside a callback omits the `session` argument?
38. What role does `matchedCount` play in conditional debits?
39. Which phases does `MongoTransactionManager` coordinate?
40. Does Spring `@Transactional` automatically guarantee commit retries identically to `withTransaction`?
41. Why can self-invocation stop Spring `@Transactional` from working?
42. When do checked exceptions need `rollbackFor` in Spring?
43. Can a Spring Data transaction commit SQL and Kafka atomically alongside MongoDB?
44. What problem does a transactional outbox solve, and what risk remains?
45. When should `failCommand` or `rs.stepDown` be used for testing?
46. Why doesn't `failCommand` `closeConnection` prove the commit happened before the network drop?
47. Which metrics separate server health issues from business idempotency?
48. How do retry storms hinder cluster recovery after failover?
49. Why measure p95/p99 and successful throughput alongside retry counts?
50. What evidence and safety bounds must a solid runbook require before modifying production?

## 25. Summary and Safe Handling Principles

### 25.1. One Incident Can Produce Multiple Exception Types

~~~text
Primary election
     |
     +--> Old primary rejects writes
     |       -> NotWritablePrimary
     |
     +--> Driver cannot find writable server
     |       -> Server selection timeout
     |
     +--> In-flight transaction interrupted
     |       -> TransientTransactionError on eligible errors
     |
     +--> Commit response lost
     |       -> UnknownTransactionCommitResult when labeled
     |
     +--> Applications aggressively retry
             -> Increased contention / WriteConflict
~~~

This is **one possible causal chain**, not a fixed sequence for every election. Investigate using real timestamps, topology changes, error labels, and metrics.

### 25.2. Four Main Remediation Directions

| Issue | Remediation direction |
|---|---|
| **`NotWritablePrimary`** | Check elections, replica set health, URI, and SDAM; let the driver discover the new primary with bounded retries. |
| **`WriteConflict`** | Retry whole transaction when labeled; reduce hot documents, transaction duration, and concurrency contention. |
| **`TransientTransactionError`** | Re-run the whole transaction in a new attempt; re-read and re-validate business preconditions. |
| **`UnknownTransactionCommitResult`** | Retry the same commit while session/protocol permits; otherwise look up durable receipts and reconcile. |

### 25.3. Protecting Applications from Double Business Effects

~~~text
Every business request:
  stable idempotency key
  immutable request payload
  unique database constraint
  transaction boundaries
  correct retry semantics
  persistent outcome record
  bounded reconciliation
~~~

Driver-level automatic retries alone are **insufficient** for business-level resends from HTTP gateways, queues, or users.

### 25.4. Five Questions Before Retrying

1. **Was the command actually sent to the server?**
2. **Is this a single write, a transaction body, or a commit?**
3. **What do the error code, labels, and driver exception say?**
4. **Is the outcome definitely failed/aborted, confirmed committed, or unknown?**
5. **If re-executed, how does business idempotency protect state?**

If you cannot answer these, **do not write an infinite retry loop**.

### 25.5. Short Investigation Workflow

~~~text
Capture symptoms and time window
      |
      v
Identify operation phase and error labels
      |
      v
Check replica set topology and application URI
      |
      v
Check write conflicts/transaction duration/pool/network
      |
      v
Choose retry/reconciliation by protocol
      |
      v
Validate persisted business invariants
      |
      v
Improve alerts, budgets, idempotency, and root-cause fixes
~~~

### 25.6. Official Documentation

- [MongoDB Replica Set Elections](https://www.mongodb.com/docs/manual/core/replica-set-elections/) — elections and primary failover.
- [MongoDB Replication](https://www.mongodb.com/docs/manual/replication/) — replica set architecture, primary/secondaries.
- [MongoDB Error Codes](https://www.mongodb.com/docs/manual/reference/error-codes/) — server error codes/names.
- [MongoDB Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/) — conditions and semantics for retryable writes.
- [MongoDB Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — multi-document atomicity.
- [MongoDB Transactions in Applications](https://www.mongodb.com/docs/manual/core/transactions-in-applications/) — transaction APIs and retry guidance.
- [MongoDB Transactions Production Considerations](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/) — resource limits and operations.
- [MongoDB Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/) — read consistency levels.
- [MongoDB Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — acknowledgment and durability.
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/) — `MongoClient`, error handling, and server discovery.
- [MongoDB Java Sync Driver Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/) — `ClientSession.withTransaction`, commit/abort.
- [Spring Data MongoDB Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html) — `MongoTransactionManager` and transactional workflows.
- [Spring Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html) — `@Transactional`/proxy/rollback.
- [MongoDB `hello` Command](https://www.mongodb.com/docs/manual/reference/command/hello/) — member/topology info.
- [MongoDB `replSetGetStatus` Command](https://www.mongodb.com/docs/manual/reference/command/replSetGetStatus/) — replica set status.
- [MongoDB `serverStatus` Command](https://www.mongodb.com/docs/manual/reference/command/serverStatus/) — node/transaction statistics.
- [MongoDB `configureFailPoint` Command](https://www.mongodb.com/docs/manual/reference/command/configureFailPoint/) — fault injection in supported test environments.

**Version note:** Error codes/labels, automatic retry policies, transaction limitations, driver behavior, and Spring Data integration may evolve across MongoDB server, driver, and framework versions. Cross-check version-specific docs and test appropriately before production rollout. Fault-injection examples here are strictly for authorized lab environments.

**Conclusion:** Not primary, write conflicts, and transient transaction errors are not just exceptions to catch. They are signals about **topology, concurrency, and transaction outcomes**. Safe handling requires identifying the exact phase, letting the driver manage topology and retry protocols where appropriate, bounding retries to avoid load storms, maintaining idempotency at the business boundary, and verifying committed state before reporting results or compensating. A resilient system does not merely suffer fewer errors—it **never creates duplicate or incorrect business effects when errors happen**.
