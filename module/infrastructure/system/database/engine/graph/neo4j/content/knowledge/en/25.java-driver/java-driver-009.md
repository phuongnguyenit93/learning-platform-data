# Automatic Retries, Idempotency, and External Side Effects

## 1. Why Can a Successful Transaction Still Be Executed Multiple Times?

Neo4j Java Driver lets you run Cypher queries through driver-managed transactions. When transient errors occur—such as deadlocks, dropped connections, or an unavailable cluster member—the driver can **re-execute the transaction** according to its retry policy.

This greatly improves availability, but introduces a design requirement: **a managed transaction callback can run multiple times**. Anything executed inside the callback must be controlled accordingly.

Suppose an API receives a request to credit 100 points to a customer:

~~~text
API /rewards
    |
    +-- executeWrite(callback)
            |
            +-- Cypher increments Account.points
            +-- call email API "You received 100 points"
            +-- return result
~~~

If Neo4j requires a retry after a transient error, the callback can be invoked again. At that point:

- The write inside the previously rolled-back transaction runs again and commits once.
- **The email already sent externally cannot be rolled back by Neo4j**; the user may receive two emails.
- If the commit status becomes **ambiguous** due to a lost acknowledgment, an already-committed write might still be retried by the application or caller, causing an unkeyed increment to apply a second time.

This is why we must distinguish three concepts:

1. **Retry:** re-running a transaction/operation when an eligible error occurs.
2. **Idempotency:** receiving the same logical request again does not multiply the business effect.
3. **External side effect:** actions like sending emails, calling payment APIs, publishing messages, or writing files that occur outside the Neo4j transaction boundary.

This lesson belongs to the **Java Driver** chapter of the Neo4j module, focusing on designing Java applications using Cypher and property graphs safely in the presence of faults, concurrent writes, and external integrations.

## 2. Three Ways to Execute Queries in the Java Driver

The Java Driver provides several session and transaction patterns. Retry behavior differs depending on your choice.

| Call style | Model | Driver automatic retry |
|---|---|---|
| `session.executeRead(work)` | Managed transaction for reads | Built-in retry for eligible errors |
| `session.executeWrite(work)` | Managed transaction for writes | Built-in retry for eligible errors |
| `session.beginTransaction()` then `tx.commit()` | Explicit transaction controlled by the application | Does not re-run an entire callback like managed transactions; application manages retries |
| `session.run(cypher, params)` | Auto-commit transaction | Does not use the managed-transaction callback retry mechanism; error handling and retries follow API contract |

Managed write transaction example:

~~~java
try (Session session = driver.session(
        SessionConfig.forDatabase("neo4j"))) {

    String accountId = "A-100";

    String updatedId = session.executeWrite(tx ->
        tx.run("""
            MATCH (a:Account {accountId: $accountId})
            SET a.lastTouchedAt = datetime()
            RETURN a.accountId AS accountId
            """, Values.parameters("accountId", accountId))
          .single()
          .get("accountId")
          .asString()
    );
}
~~~

In this example, **the driver is responsible for managing the transaction and eligible retries**. The Java callback receives `tx`, representing the transaction executing in the current attempt.

**Never treat** that callback as a function guaranteed to execute only once. Even for read queries, the callback can re-run, so incrementing a global counter, sending notifications, or writing files inside `executeRead` can also produce duplicate side effects.

### 2.1. Imports Guide for Java Examples

Short examples use standard Neo4j Java Driver APIs:

~~~java
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.Values;
~~~

In production applications, configure the `Driver`, URI, authentication, certificates, and target database for your runtime environment. **`Driver`** is normally created once and reused over the application lifecycle; **`Session`** should be short-lived and never shared indiscriminately across threads.

### 2.2. Why Use executeWrite for Writing Data

~~~java
session.executeWrite(tx -> {
    tx.run("""
        MATCH (u:User {userId: $userId})
        SET u.active = true
        """, Values.parameters("userId", userId)).consume();

    return null;
});
~~~

`executeWrite` expresses write intent and enables routing to the appropriate writer server in a cluster. Reserve `executeRead` for read-only transactions; never place `CREATE`, `MERGE`, `SET`, or `DELETE` inside a read callback.

For statements that do not return data to the caller, `consume()` finishes processing the result inside the transaction. When a DTO is needed, read and map `Record`s before the callback ends instead of returning a `Result` tied to a closed transaction.

## 3. How Automatic Retries Work

Simplified model:

~~~text
executeWrite(callback)
    |
    v
Start transaction, run callback
    |
    +-- Commit succeeds --------------------> return result
    |
    +-- Retryable transient error
             |
             +-- within retry limit? -- yes --> re-run callback
             |
             +-- limit exceeded or non-retryable --> throw error
    |
    +-- Non-retryable error --------------> throw error
~~~

The Java Driver recognizes and classifies certain retryable errors; exact policy depends on driver version, error type, configuration, and cluster state.

### 3.1. Error Categories

| Situation | Handling |
|---|---|
| Deadlock or transient transaction error recognized by driver | Driver can retry the managed transaction |
| Connection drop or server change | Driver may retry depending on error and state determinability |
| Cypher syntax error | Fix the query; retrying the same statement will not help |
| Invalid parameter | Validate input; do not retry blindly |
| Uniqueness constraint violation | Check whether it is a duplicate request or data conflict; do not assume driver auto-retries |
| No node matched by `MATCH` | Handle not-found according to business logic |
| External API/email failure | Neo4j Driver cannot roll back external side effects that already happened |
| Ambiguous commit outcome after timeout/disconnect | Use an idempotency key and re-check persisted state |

Never catch every `Exception` and retry endlessly. That only increases database load, prolongs failures, and risks duplicate side effects.

### 3.2. Retry Time Limit

Managed transactions must not retry forever. The Driver configures a maximum retry window, such as `maxTransactionRetryTime` in Driver config; exact configuration syntax depends on your API version.

In several Java Driver versions, configuration looks like:

~~~java
Config config = Config.builder()
    .withMaxTransactionRetryTime(15, java.util.concurrent.TimeUnit.SECONDS)
    .build();
~~~

This is a **cap on retry duration**, not a guarantee that every operation finishes in exactly 15 seconds. Actual duration also depends on network timeouts, connections, transaction timeouts, and operational parameters. Verify exact API/config names against your driver version.

**Do not wrap `executeWrite` in a custom outer retry loop** unless you know exactly which errors it handles that the driver does not. Uncoordinated multi-layer retries multiply execution counts and mask underlying system problems.

## 4. Retrying a Transaction Differs from "Happening Exactly Once"

A Neo4j transaction guarantees **atomicity**: changes commit as one unit, and transactions failing before commit leave no partially committed changes behind.

However, two cases require separate attention:

**Case A — failure before commit is known:** the first attempt rolls back; the callback re-runs; only the later attempt may commit. External side effects outside Neo4j from the first attempt **do not automatically undo**.

**Case B — unclear whether commit occurred:** Neo4j may have committed while the acknowledgment was lost in transit back to the client. Callers must not conclude "definitely not written" simply because no response arrived. If the app or caller replays the same increment, it risks applying it twice.

Therefore, never call a counter increment "safe" merely because it runs inside `executeWrite`.

### 4.1. Absolute Assignment vs. Cumulative Increment

~~~cypher
// Reassigning the same value, typically idempotent with respect to target state.
MATCH (u:User {userId: $userId})
SET u.tier = 'GOLD';
~~~

~~~cypher
// Each successful run adds again.
MATCH (u:User {userId: $userId})
SET u.rewardPoints = coalesce(u.rewardPoints, 0) + 100;
~~~

With an increment, two commits yield **200 points** total. With setting `tier`, repeating the exact same statement does not add values; however, if an older event arrives after a newer one, it can still **overwrite state backward**. Idempotency of an assignment **does not replace event ordering or versioning**.

### 4.2. MERGE Only Handles Identity of the Merged Pattern

~~~cypher
MERGE (u:User {userId: $userId})
SET u.rewardPoints = coalesce(u.rewardPoints, 0) + 100;
~~~

`MERGE` finds or creates the User node by key. It **does not know** which request the 100 points came from or whether they were already credited. If the same request runs again, `SET` still adds 100 more.

To prevent duplicate User nodes under concurrent creation, put an appropriate constraint on `User.userId`. Yet **a User constraint alone** still cannot enforce "each credit command applies at most once".

## 5. Choosing an Idempotency Key for a Business Operation

An **idempotency key** uniquely identifies **one logical command** across retries. For example:

~~~json
{
  "commandId": "reward-api:cmd-20261125-0021",
  "accountId": "A-100",
  "operation": "CREDIT_POINTS",
  "delta": 100
}
~~~

If an HTTP client resends the same request after a timeout, `commandId` must **stay unchanged**. If the client generates a fresh UUID on every retry, each attempt looks like a distinct valid command.

Different key types to distinguish:

| Key | Identifies | Scope to watch |
|---|---|---|
| `accountId` | Account node | One account receives many point-credit commands |
| `commandId` | One logical credit command | Must stay identical across HTTP/API retries |
| `eventId` | One event in a broker/outbox | Must stay identical across publish/redelivery |
| `requestId` | One incoming API request | Use as business key only if contract guarantees stability |
| `aggregateVersion` | Version sequence of an aggregate | Not equivalent to a unique ID for every operation |

If IDs are only unique per service, namespace the key, e.g., `source + ":" + commandId`. In multi-tenant systems, decide whether `tenantId` must be part of the identifier.

### 5.1. Same Key, Different Payload

Two requests sharing `commandId` where one credits 100 and the other credits 1000 must not be treated as a "valid redelivery". Compare **accountId, operation, delta**, or a canonical payload hash to distinguish:

- **Same key, same content:** command already processed; return the stored result or check status.
- **Same key, different content:** key conflict; reject or investigate.
- **Unseen key:** attempt to apply the new command.

Note that a payload hash must be computed over a canonical representation; JSON field ordering, numeric types, and string normalization can produce mismatched hashes without strict rules.

## 6. Combining Uniqueness Constraints with an Applied-Command Ledger

In Neo4j, you can record each command as an `AppliedCommand` node while updating the `Account` node inside **the same transaction**.

Model:

~~~text
(:AppliedCommand {
  commandId, accountId, delta, appliedAt, resultPoints
})
        |
    [:APPLIED_TO]
        |
        v
(:Account {accountId, rewardPoints})
~~~

Constraints:

~~~cypher
CREATE CONSTRAINT account_id_unique IF NOT EXISTS
FOR (a:Account)
REQUIRE a.accountId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT applied_command_id_unique IF NOT EXISTS
FOR (c:AppliedCommand)
REQUIRE c.commandId IS UNIQUE;
~~~

One constraint protects **Account** identity; the other enforces **single application per commandId**. Constraints must be created before concurrent writes begin. If duplicate data already exists, creating the constraint will fail and require data cleanup per business rules.

### 6.1. Cypher to Apply a New Command Exactly Once

~~~cypher
MATCH (a:Account {accountId: $accountId})
CREATE (cmd:AppliedCommand {
    commandId: $commandId,
    accountId: $accountId,
    delta: $delta,
    appliedAt: datetime()
})
SET a.rewardPoints = coalesce(a.rewardPoints, 0) + $delta
SET cmd.resultPoints = a.rewardPoints
CREATE (cmd)-[:APPLIED_TO]->(a)
RETURN cmd.commandId AS commandId,
       cmd.resultPoints AS resultPoints;
~~~

Points to understand:

1. `MATCH` requires the Account to exist. If no Account exists, the statement returns **0 rows**; the application must handle "not found".
2. `CREATE AppliedCommand` writes a receipt for a new command, with `commandId` guarded by the uniqueness constraint.
3. `SET` updates the account points and records the resulting balance on the receipt.
4. `CREATE relationship` links the receipt to the Account for traceability.
5. The receipt, point update, and relationship commit **atomically** in the same Neo4j transaction.

If two workers concurrently process the same `commandId`, **two AppliedCommand nodes with the same key cannot both commit** while the constraint is active. One worker may succeed while the other encounters contention or a uniqueness error. If a transaction fails, its point update and receipt both roll back.

**Precondition for correctness:** every write path capable of changing `rewardPoints` for commands must follow this mechanism; no other worker may add points directly while bypassing the receipt. Constraints enforce the declared invariant; they do not protect write paths that ignore the contract.

### 6.2. Do Not Put Unconditional Increments After MERGE Receipt

**Wrong** example:

~~~cypher
MERGE (cmd:AppliedCommand {commandId: $commandId})
WITH cmd
MATCH (a:Account {accountId: $accountId})
SET a.rewardPoints = coalesce(a.rewardPoints, 0) + $delta;
~~~

Even when `MERGE` matches an existing `AppliedCommand` node, the subsequent `SET` still runs. `MERGE` does not automatically create an "already processed, skip remaining clauses" branch.

Using `CREATE` on the constrained receipt as in Section 6.1 makes it explicit that **a new receipt must be created** for the command to apply. If you choose `MERGE`, you must explicitly distinguish a receipt **created in the current transaction** and only perform the business update in that case—never rely on a vague intuition that "`MERGE` = idempotent".

### 6.3. Reading the Receipt After an Ambiguous Error

~~~cypher
MATCH (cmd:AppliedCommand {commandId: $commandId})
RETURN cmd.accountId AS accountId,
       cmd.delta AS delta,
       cmd.resultPoints AS resultPoints,
       cmd.appliedAt AS appliedAt;
~~~

If the receipt exists and its business fields match the command being processed, the application can return the **already-applied result** without crediting points again.

If the receipt exists with a different `accountId` or `delta`, that is a **conflict**, not a safe duplicate. If no receipt is found, distinguish a transaction that genuinely never committed from read/consistency lag on the check; never guess blindly.

## 7. Java Driver: Write Callbacks Only Touch Neo4j

The example below illustrates the **apply new command** branch using a managed transaction. It assumes the constraints from Section 6 exist, inputs are valid, and the Account exists.

~~~java
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Result;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class RewardCommandWriter {
    public record AppliedReward(String commandId, long resultPoints) {}

    private final Driver driver;

    public RewardCommandWriter(Driver driver) {
        this.driver = driver;
    }

    public AppliedReward creditPoints(
            String commandId, String accountId, long delta) {
        if (commandId == null || commandId.isBlank()
                || accountId == null || accountId.isBlank()
                || delta <= 0) {
            throw new IllegalArgumentException("Invalid reward command");
        }

        String cypher = """
            MATCH (a:Account {accountId: $accountId})
            CREATE (cmd:AppliedCommand {
                commandId: $commandId,
                accountId: $accountId,
                delta: $delta,
                appliedAt: datetime()
            })
            SET a.rewardPoints = coalesce(a.rewardPoints, 0) + $delta
            SET cmd.resultPoints = a.rewardPoints
            CREATE (cmd)-[:APPLIED_TO]->(a)
            RETURN cmd.commandId AS commandId,
                   cmd.resultPoints AS resultPoints
            """;

        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            return session.executeWrite(tx -> {
                Result result = tx.run(cypher, Map.of(
                    "commandId", commandId,
                    "accountId", accountId,
                    "delta", delta
                ));

                if (!result.hasNext()) {
                    throw new IllegalStateException(
                        "Account was not found: " + accountId
                    );
                }

                var row = result.single();
                return new AppliedReward(
                    row.get("commandId").asString(),
                    row.get("resultPoints").asLong()
                );
            });
        }
    }
}
~~~

**Notes on this example:**

- `commandId` is passed **from the caller**, generated once before any retries; never generated inside the callback.
- Cypher uses parameters rather than string concatenation from request data.
- The callback returns a pure value DTO after reading results, never leaking `Result` or `TransactionContext` outside.
- No emails, REST calls, event publishing, or writes to other systems occur inside the callback.
- Constraint violations when a command was already processed are **not yet translated into a duplicate response in this snippet**; the application service must add the recovery step in Section 7.1.

### 7.1. Recovery Strategy After Duplicate or Ambiguous Commit Outcomes

Calling flow around `creditPoints(...)`:

~~~text
Receive (commandId, accountId, delta)
    |
    v
Attempt creditPoints via managed transaction
    |
    +-- Commits and returns AppliedReward ---> return success
    |
    +-- Error possibly due to already-applied command
    |       |
    |       +-- Read AppliedCommand by commandId
    |               |
    |               +-- Receipt found, payload matches ---> return stored result
    |               +-- Receipt found, payload differs ---> conflict error
    |               +-- No receipt found -----------------> classify original error/retry
    |
    +-- Other error -------------------------> handle by error type
~~~

Never catch **every exception**, look up the receipt, and blindly treat it as success—unrelated errors like permissions, syntax, cluster configuration, or other constraints must be reported accurately.

On uniqueness errors, determine **which constraint** was violated. After a lost commit acknowledgment, read through a fresh session with appropriate routing and consistency. In a cluster, bookmarks/session consistency and database selection affect read-after-write visibility; do not treat an arbitrary read from a lagging replica as definitive proof that no receipt exists.

### 7.2. Why Not Generate a UUID Inside executeWrite?

Counterexample:

~~~java
session.executeWrite(tx -> {
    String commandId = java.util.UUID.randomUUID().toString();
    tx.run("""
        CREATE (:AppliedCommand {commandId: $commandId})
        """, Map.of("commandId", commandId)).consume();
    return null;
});
~~~

If the callback re-runs, a new UUID is generated. The uniqueness constraint on `commandId` cannot recognize these as **the same logical command**, because each retry uses a different key.

**Fix:** generate `commandId` at the request boundary and pass/store it stably across retries:

~~~java
String commandId = request.commandId(); // stably provided by caller
session.executeWrite(tx -> {
    tx.run("""
        CREATE (:AppliedCommand {commandId: $commandId})
        """, Map.of("commandId", commandId)).consume();
    return null;
});
~~~

This is a simplified ID-lifecycle illustration; the minimal `CREATE` does not replace the receipt + business update pattern from earlier sections.

### 7.3. Watch Out for Every Non-Deterministic Source in Callbacks

The following easily produce different behavior across attempts:

- `UUID.randomUUID()` used as a command identifier.
- Calling external APIs that return changing data.
- Reading/writing mutable state shared across threads.
- Incrementing an in-memory counter to track "commands processed".
- Using `System.currentTimeMillis()` to decide command uniqueness logic.
- Emitting broker events or sending notifications.

If timestamps must be stored, clarify whether they represent **attempt execution time** or **command occurrence time**. For example, Cypher `datetime()` reflects the successful attempt's execution time, whereas business occurrence time should come from a stable payload provided by the producer.

A callback may emit debug logs multiple times without corrupting business data, but when using logs/metrics to count "successful commands", measure at **confirmed commits or receipts** so failed attempts are not overcounted.

## 8. External Side Effects: Why Callbacks Are Dangerous

### 8.1. Sending Emails Inside a Transaction

~~~java
session.executeWrite(tx -> {
    tx.run("""
        MATCH (a:Account {accountId: $accountId})
        SET a.rewardPoints = coalesce(a.rewardPoints, 0) + $delta
        """, parameters).consume();

    emailClient.sendRewardEmail(accountId, delta); // Side effect outside Neo4j
    return null;
});
~~~

If the transaction subsequently rolls back, the email may already have been sent. If the callback is retried, the email may be sent again. Neo4j has no way to roll back an SMTP server that already accepted an email.

### 8.2. Is Sending the Email After executeWrite Enough?

~~~java
AppliedReward result = rewardWriter.creditPoints(
    commandId, accountId, delta
);
emailClient.sendRewardEmail(accountId, delta);
~~~

This is **better than sending inside the callback** because the email is only triggered after the method confirms transaction success. Yet two failure modes remain:

- **Crash after DB commit, before sending email:** points are updated, but no email is sent.
- **Email sent, then connection drops or crash before recording "sent":** a retry may send a second email.

This is the classic **dual-write** problem between Neo4j and a non-transactional external system. Moving the send after the callback eliminates duplicate sends from internal driver retries, but still does not guarantee exactly-once or zero-loss delivery.

### 8.3. Other External Side Effects to Watch

| Action | Risk when callback re-runs |
|---|---|
| Email / SMS | Duplicate notifications, user confusion |
| Calling a payment API | Risk of duplicate charges/transactions if API lacks idempotency |
| Publishing to Kafka / RabbitMQ | Emits event even if Neo4j transaction rolls back |
| Writing files or object storage | Overwritten files, duplicate objects, hard to roll back |
| Writing to cache | Cache reflects uncommitted or stale state |
| Calling fulfillment services | Creates two shipping orders |
| Recording business metrics | Overcounts successful transactions |

Separate **transactional data writes** from **emitting side effects to the outside world**. Actions inside the callback should be restricted to Neo4j mutations backed by proper deduplication.

## 9. Transactional Outbox: Recording Event Intent Alongside Data

The **transactional outbox** is a standard pattern to avoid losing messages between database commit and broker publishing.

Idea:

1. Inside the **same Neo4j transaction**, update the Account, create the `AppliedCommand`, and create an **`OutboxEvent`** node recording the intent to publish.
2. Commit atomically.
3. A **separate dispatcher** queries unsent `OutboxEvent`s, calls the broker/email service, and marks progress.
4. The dispatcher can retry; downstream consumers must support idempotency.

Illustrative model:

~~~text
(:AppliedCommand {commandId})
    |
    +--[:APPLIED_TO]-->(:Account {rewardPoints})
    |
    +--[:EMITTED]---->(:OutboxEvent {
                           eventKey, eventType, status,
                           accountId, delta, createdAt
                       })
~~~

Create a constraint for the outbox:

~~~cypher
CREATE CONSTRAINT outbox_event_key_unique IF NOT EXISTS
FOR (e:OutboxEvent)
REQUIRE e.eventKey IS UNIQUE;
~~~

Derive a deterministic `eventKey` from `commandId`, e.g., `eventKey = commandId + ":reward-applied"`. Build this string **before the transaction** so retrying the same command does not generate a new event key.

### 9.1. Creating the Outbox Entry in the Same Update Transaction

~~~cypher
MATCH (a:Account {accountId: $accountId})
CREATE (cmd:AppliedCommand {
    commandId: $commandId,
    accountId: $accountId,
    delta: $delta,
    appliedAt: datetime()
})
SET a.rewardPoints = coalesce(a.rewardPoints, 0) + $delta
SET cmd.resultPoints = a.rewardPoints
CREATE (cmd)-[:APPLIED_TO]->(a)
CREATE (outbox:OutboxEvent {
    eventKey: $eventKey,
    eventType: 'RewardPointsCredited',
    status: 'PENDING',
    accountId: $accountId,
    delta: $delta,
    createdAt: datetime()
})
CREATE (cmd)-[:EMITTED]->(outbox)
RETURN cmd.resultPoints AS resultPoints,
       outbox.eventKey AS eventKey;
~~~

This executes as **one Neo4j transaction**. On rollback, no point update, receipt, or outbox node commits. On commit, both business state and publishing intent persist together.

**Limitation:** the Neo4j transaction only covers mutations **inside Neo4j**. It does not enlist the message broker or email service in a distributed transaction.

### 9.2. The Dispatcher Can Send Duplicates

Suppose:

~~~text
Dispatcher reads PENDING OutboxEvent
    |
    +-- publishes to broker successfully
    |
    X crashes before marking SENT
    |
Dispatcher restarts, still sees PENDING
    |
    +-- republishes the same eventKey
~~~

This is why an outbox normally provides **at-least-once delivery**, not automatic exactly-once receipt by consumers. Consumers should use `eventKey` to deduplicate. For email/SMS, you may need provider-supported idempotency keys or a dedicated dispatch/receipt ledger.

With multiple dispatchers, design **claim/lease/lock** rules and status transitions so two workers do not concurrently pick up the same outbox item. Simply running:

~~~cypher
MATCH (e:OutboxEvent {status: 'PENDING'})
RETURN e LIMIT 10;
~~~

does not "exclusively claim" events. A read query does not lock them for a single dispatcher. Claiming, timeouts, lease expiration, and crashed-worker recovery must be designed as an explicit workflow.

### 9.3. What Should an Outbox Entry Contain?

An outbox record typically needs:

- A stable, unique `eventKey`.
- `eventType` and schema version.
- Aggregate key, such as `accountId`.
- The payload to send, or sufficient immutable data to reconstruct it deterministically.
- `createdAt`, delivery status/progress, attempt count.
- Metadata for tracing and diagnostics.

Do not write only `status = 'PENDING'` and have the dispatcher later read the **current Account state** assuming it matches the moment the event occurred. The Account may have changed between commit and dispatch. If an event describes a specific mutation, the payload should capture a **snapshot of that change** or its corresponding version.

## 10. When Is External-Service Idempotency Needed?

Even when Neo4j holds `AppliedCommand` and `OutboxEvent`, downstream services can still receive duplicate calls.

### 10.1. Payment APIs

A payment provider supporting idempotency keys lets the application resend **the same payment operation** without creating two charges. The key sent externally must be a stable identifier for **one logical charge**, not a fresh UUID generated per retry.

Read the provider contract carefully: key scope, retention window, behavior when the same key is sent with a different payload, and ambiguous outcomes. Never assume all payment APIs behave identically.

### 10.2. Emails and Notifications

Some email services do not guarantee strict request-level deduplication. You can maintain an internal dispatch ledger and idempotency/correlation keys to minimize duplicates, while recognizing the gap between "provider accepted send" and "result persisted".

Product requirements should distinguish:

- **At-least-once delivery** (accepting rare duplicates).
- **Best-effort duplicate avoidance** (potentially accepting occasional unsent messages under ambiguity).
- **Exactly-once business effect** (typically requiring idempotency contracts from the target system).

Never promise "exactly-once email" simply because Neo4j transactions are used.

## 11. Retries, Uniqueness, and Concurrency When Two Requests Share commandId

Consider two Java threads concurrently receiving the same `commandId` `cmd-77`.

~~~text
Thread A                    Neo4j                  Thread B
    |                          |                        |
    |-- CREATE AppliedCommand ->|<- CREATE AppliedCommand|
    |                          |                        |
    |             constraint: unique commandId          |
    |                          |                        |
    |    at most one transaction commits the receipt    |
    |    the other transaction handles conflict/error   |
~~~

The uniqueness constraint on `AppliedCommand.commandId` guarantees **two receipts with the same key cannot both commit**. Because the point update occurs in the same transaction that creates the receipt, concurrent transactions processing the same key cannot both commit point updates under this pattern.

In practice, the losing thread may wait or receive different errors depending on query plans and scheduling. The application must classify the failure and **read the receipt in a fresh session/transaction** to confirm the command was already processed.

Never claim that every competing request **succeeds on the first try**. The guaranteed invariant is **no duplicate application for the defined key**.

### 11.1. Multi-Node Mutations

A command transferring 50 points from A to B must update both nodes and write a receipt in **the same transaction**, while checking balances and handling write contention. The receipt prevents **the same command from applying twice**; it does not automatically solve **non-negative balance checks**, **multi-account locking**, or **deadlocks**.

When two transactions touch Accounts in opposite orders, deadlocks can occur. The Driver can retry eligible transient errors; keep transactions short and free of external side effects inside callbacks.

## 12. Redelivered Events and Update Ordering Are Separate Problems

Suppose two events arrive for the same Account:

~~~text
E-41: status = ACTIVE,    version = 41
E-42: status = SUSPENDED, version = 42
~~~

If E-42 commits first and E-41 arrives later, checking `eventId`/receipt alone will not prevent a backward overwrite if E-41 had never been processed before. You must inspect `version`.

- **Full snapshots:** events with a version lower than the applied version can be skipped, per source contract.
- **History-dependent deltas:** you may have to process every version in order; do not skip an unapplied delta merely because a newer version arrived.

Do not rely on `occurredAt` as the sole ordering key across multiple servers, clock skew, or replays. If business logic requires ordering, use a per-**aggregate** sequence/version or an appropriate coordinator.

An idempotency key answers **"has this exact operation already been processed?"**; a version answers **"where does this operation sit in the state progression?"**. They complement rather than replace each other.

## 13. Spring Data Neo4j and the Scope of @Transactional

With Spring Data Neo4j, services often use `@Transactional` to group repository/`Neo4jClient` operations inside a Spring-managed transaction.

However:

- `@Transactional` **does not automatically re-run callbacks like `Session.executeWrite`**. If retries are needed, understand your Spring transaction manager, any external retry wrapper, and retryable error classes.
- Spring or HTTP-layer retries can re-invoke **the entire service method**, so idempotency keys and outboxes remain essential.
- `repository.save(entity)` does not automatically generate a command-deduplication receipt.
- A Spring transaction managing Neo4j **does not automatically commit atomically** with a SQL database, broker, email, or payment API.
- Do not arbitrarily nest direct Java Driver managed transactions inside an active Spring transaction without understanding session sharing and transaction scoping.

When an application uses multiple data stores, explicitly document each system's **transaction manager**, commit boundaries, and event flow. This is integration architecture and cannot be solved with a single annotation.

## 14. Monitoring and Analyzing Retries

A pipeline can yield correct final state while suffering heavy contention or excessive retries, inflating latency.

Metrics to track:

| Metric | Meaning |
|---|---|
| Incoming commands by distinct `commandId` | True business load |
| Callback/transaction attempts | Reveals retry rate and contention |
| Newly created receipts | Commands actually applied |
| Confirmed duplicates | Redelivery or caller retry rate |
| Same-key, different-payload conflicts | Idempotency contract violations |
| Transient errors / deadlocks / timeouts | Transaction and connection pressure |
| Oldest pending outbox item | Unfinished publishing intents |
| Publish attempts vs. distinct `eventKey` | Dispatcher redelivery rate |
| Commit-to-dispatch latency | Eventual delivery health |
| Downstream duplicate deliveries | Validates end-to-end idempotency |

Never measure "successful commands" by counting callback invocations: a callback can run multiple times for the same `commandId`. Base reconciliation on confirmed commits and receipts.

### 14.1. Queries for Inspecting Receipts

~~~cypher
MATCH (cmd:AppliedCommand {commandId: $commandId})
RETURN cmd.accountId AS accountId,
       cmd.delta AS delta,
       cmd.resultPoints AS resultPoints,
       cmd.appliedAt AS appliedAt;
~~~

~~~cypher
MATCH (cmd:AppliedCommand)
WITH cmd.commandId AS commandId, count(cmd) AS occurrences
WHERE occurrences > 1
RETURN commandId, occurrences
LIMIT 20;
~~~

With an active uniqueness constraint and supplied `commandId` values, two committed `AppliedCommand` nodes cannot share the same key. If anomalies appear, inspect database/schema/labels/properties or data-ingestion paths.

### 14.2. Checking Pending Outbox Items

~~~cypher
MATCH (e:OutboxEvent {status: 'PENDING'})
RETURN e.eventKey AS eventKey,
       e.eventType AS eventType,
       e.createdAt AS createdAt
ORDER BY createdAt ASC
LIMIT 50;
~~~

This is an **observability** query. It does not claim events for a worker or handle concurrency across multiple dispatchers.

## 15. Testing Failure Scenarios Deliberately

Test in an **isolated database** with production-like constraints. Start with an Account having `rewardPoints = 0` and a command crediting 100 points.

| Scenario | Simulation | Expected result |
|---|---|---|
| New command | Send `cmd-1` once | 1 receipt created, +100 points |
| HTTP retry of same command | Resend `cmd-1` | No second credit; duplicate detected |
| Two threads with same command | Run `cmd-2` concurrently | At most one write commits per key |
| Duplicate key, different delta | Send `cmd-1` with delta 900 | Conflict error, no extra credit |
| Transient error before commit | Force rollback on first attempt | Callback may re-run; no duplicate emails |
| Commit succeeds, response lost | Simulate disconnect after commit | Read receipt to confirm result, no double credit |
| Crash after commit, before publish | Outbox remains PENDING | Dispatcher picks it up and publishes |
| Crash after publish, before SENT | Dispatcher republishes | Consumer/downstream handles duplicate |
| Account does not exist | Use invalid key | No fake receipt created; returns error |
| Two distinct commands | `cmd-3` and `cmd-4` | Each command applied once |
| Expired receipt, old request returns | Replay after retention | Must not misapply if business requires strict once-only effect |

### 15.1. Verify Values, Not Just Responses

After sending the same `commandId` twice, check:

~~~cypher
MATCH (a:Account {accountId: $accountId})
OPTIONAL MATCH (cmd:AppliedCommand {commandId: $commandId})
RETURN a.rewardPoints AS points,
       count(cmd) AS receipts;
~~~

Starting from 0 with one valid +100 command and no other updates, the expected result is **points = 100**, **receipts = 1**.

**Note:** the query above only checks for a receipt with that key; it does not prove the receipt belongs to the right Account unless you also check `cmd.accountId` or the `APPLIED_TO` relationship. In business verification, check target keys, payload, and actual mutations.

### 15.2. Testing Repeated Callback Invocations

Use a test double or fault condition to inject a retryable error before commit, then measure:

- Number of callback invocations.
- Final receipt count.
- Final point balance.
- Number of email calls or message publishes on the normal path.

The expected outcome is **zero external side effects inside callbacks**; the separate dispatcher may republish, identified by `eventKey`. Never rely solely on sequential tests to declare a design safe under multiple concurrent workers.

## 16. Common Misconceptions

**"executeWrite runs the callback exactly once."** False. A managed transaction callback may be invoked again when the driver retries eligible errors.

**"Transaction rollback also undoes emails or payments."** False. Neo4j only rolls back changes inside its own transaction scope.

**"With MERGE on the node, repeating point credits is harmless."** False. `MERGE` does not know whether the +100 command was already applied.

**"A UUID generated inside the callback is a good idempotency key."** No. Retries generate new UUIDs, preventing attempts from sharing one business identity.

**"Every uniqueness error is a safe duplicate."** False. It could violate another constraint or carry a conflicting payload for the same key.

**"Sending email right after commit is guaranteed once-only."** Insufficient. Crashes before/after sending can lose or duplicate messages; use an outbox and receiver deduplication as required.

**"An outbox makes the broker receive exactly one event."** No. A dispatcher can republish after a crash. An outbox guarantees publishing intent is not lost with the transaction; consumers still need idempotency.

**"No success response means the database definitely did not commit."** False. Network failures can drop the acknowledgment after commit succeeded.

**"With a receipt, versioning is unnecessary."** No. Receipts prevent duplicate commands; versions enforce update ordering rules.

**"Spring's @Transactional replaces all of these mechanisms."** No. One annotation cannot span Neo4j, brokers, email, SQL, and HTTP services atomically.

**"Retrying every exception endlessly improves reliability."** No. Persistent data errors never vanish on retry; excessive retries add load and latency.

## 17. Practice Exercises

### Exercise 1. Email Inside a Callback

Code snippet:

~~~java
session.executeWrite(tx -> {
    tx.run("""
        MATCH (a:Account {accountId: $accountId})
        SET a.active = true
        """, parameters).consume();
    mailer.send("Updated"); 
    return null;
});
~~~

**Question:** Why can multiple emails be sent even though the transaction ultimately commits only once?

**Answer:** The callback re-runs on eligible retryable errors, while sending an email is an external side effect outside Neo4j that cannot roll back. Record the send intent in an outbox within the transaction and let a dispatcher send post-commit.

### Exercise 2. Generating a UUID in the Wrong Place

A worker generates `UUID.randomUUID()` inside the callback and uses it for `AppliedCommand`.

**Question:** Why does the uniqueness constraint fail to stop the same command from running again?

**Answer:** Each retry produces a fresh UUID; the constraint cannot tell both attempts represent the same key. Command IDs must be stable before the first attempt.

### Exercise 3. MERGE Account Yet Credited Twice

An application receives `commandId = C5` twice. Each time it runs:

~~~cypher
MERGE (a:Account {accountId: 'A100'})
SET a.rewardPoints = coalesce(a.rewardPoints, 0) + 100;
~~~

**Question:** How much can the Account increase in total?

**Answer:** Up to 200 if both commit. `MERGE Account` does not remember that C5 was already applied. You need a receipt/constraint keyed by `commandId` and must write the receipt and point update in the same transaction.

### Exercise 4. Outbox and Crashes

A dispatcher publishes an event successfully, then crashes before marking `SENT`.

**Question:** Can the next run republish it, and what is required?

**Answer:** Yes. Keep `eventKey` stable, and ensure consumers/downstream systems deduplicate or support idempotency keys. Dispatchers also need claim/lease locking when running multiple workers.

### Exercise 5. Lost Commit Acknowledgment

A caller times out, yet the database may have committed `cmd-77`.

**Question:** Should you generate a new `commandId` and retry to be sure?

**Answer:** No. Check the receipt by the original `commandId` and payload, determine whether it applied, and only then decide on retrying. Generating a new `commandId` turns one operation into two distinct operations.

### Exercise 6. Old Event Arriving Late

Event version 12 with status `PAID` arrives after event version 13 with status `SHIPPED`.

**Question:** If the two events have distinct `eventId`s, is a receipt alone enough to prevent a backward overwrite?

**Answer:** No. Enforce version/ordering rules per source contract; idempotency only handles re-delivery of the same logical event.

### Exercise 7. Should You Use executeRead or executeWrite?

You need to find a customer's 20 most recent orders without modifying any data.

**Question:** Which API should you use, and can the callback run multiple times?

**Answer:** Use `executeRead` with read-only Cypher. Read callbacks can still be retried; avoid external side effects inside the callback.

### Exercise 8. Two Distinct Valid Commands

`cmd-11` and `cmd-12` each credit 100 points to the same account.

**Question:** Should they be treated as duplicates merely because they share the same `accountId` and `delta`?

**Answer:** No, if they are two independent business commands. Idempotency keys distinguish individual commands; if both are valid and commit, +200 total is right. Never use identical payloads alone as proof that two requests are the same command.

## 18. Key Takeaways

In Neo4j Java Driver, **`executeRead` and `executeWrite` can automatically retry managed transactions**, so callbacks must be designed as **re-executable** units. Transactions only govern state inside Neo4j; external emails, payments, published messages, or files do not roll back with them.

For **cumulative increments or once-only effects**, use **stable `commandId`/`eventId` keys**, uniqueness constraints, and receipts written **atomically alongside business updates**. On errors or lost commit acknowledgments, **inspect the receipt and compare payloads** before retrying rather than minting new IDs. When emitting events to external systems, consider the **transactional outbox**, a dispatcher, and consumer-side idempotency. Combining error classification, bounded retries, ordering controls, and concurrency testing ensures the Java Driver behaves reliably under real-world failures.
