# Idempotency Across Multiple Instances

> **Chapter:** Idempotent receiver  
> **Module:** `SPRING_INTEGRATION_PATTERN` — learning to implement Enterprise Integration Patterns (EIP) with Spring Integration to build loosely coupled, extensible message flows. Practicing Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation, while testing and observing processing branches. This article focuses on **ensuring the same business operation does not produce additional side effects when messages are redelivered or processed concurrently across multiple instances**.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain **Idempotent Receiver** in message-driven systems and why `@Transactional` or `ConcurrentHashMap` alone fails to guarantee idempotency across multiple replicas.
2. Distinguish **delivery**, **processing attempt**, **business operation**, **correlation group**, **idempotency key**, and **business result**.
3. Design stable business keys with tenant namespaces that separate valid new operations from redeliveries of old ones.
4. Analyze failure windows: two instances processing concurrently, commit followed by lost ACK, mid-flight worker death, expired leases, redelivery/DLQ replays, and external timeouts.
5. Choose among **unique constraint + transaction**, **shared `ConcurrentMetadataStore`**, **Redis atomic operations**, **leases/fencing**, and **target-API idempotency**; understanding which boundary each mechanism protects.
6. Write Java 17, PostgreSQL SQL, and Spring Integration Java DSL examples for a receiver with **durable processing state and outcomes**.
7. Design tests for concurrent/multi-instance execution, restarts, conflicting duplicate payloads, idempotent replies, and outboxes to avoid emitting final outcomes twice.
8. Measure duplicate hits, conflicts, lock contention, retries/backpressure, and protect keys and data across service boundaries.

## 2. Context: Three Instances Receive the Same Stock-Reservation Command

A Spring Integration application runs three replicas behind a load balancer, all consuming requests from a broker. Command to reserve two books:

~~~json
{
  "tenantId": "shop-a",
  "commandId": "CMD-1001",
  "orderId": "ORD-981",
  "lineId": "LINE-02",
  "sku": "BOOK-42",
  "quantity": 2,
  "executionId": "RUN-01"
}
~~~

The first delivery reaches **instance A**. A writes the reservation successfully to the database, then dies before ACKing the broker. The broker redelivers the same command to **instance B**. Meanwhile, the producer retried and a second copy reaches **instance C**.

~~~mermaid
sequenceDiagram
    participant Q as Broker
    participant A as Instance A
    participant B as Instance B
    participant C as Instance C
    participant DB as Shared DB
    Q->>A: CMD-1001 / delivery #1
    A->>DB: Atomic claim + reserve stock
    DB-->>A: COMMITTED
    A--xQ: Crash before ACK
    Q->>B: CMD-1001 / redelivery
    Q->>C: CMD-1001 / duplicate publish
    B->>DB: Same operation key
    C->>DB: Same operation key
    DB-->>B: Existing committed result
    DB-->>C: Existing committed result
    B-->>Q: ACK after safe processing
~~~

**Goal:** Despite three attempts and three replicas, inventory is deducted **by two items once**, not two items per message delivery.

**It is insufficient** if A, B, and C each keep a `Set<String> processedIds` in RAM. Each instance cannot see the others' state, and after a restart, the set is also lost.

### 2.1. “Message Seen” Does Not Mean “Business Logic Committed”

A receiver can detect duplicates at ingress and still fail:

~~~text
1. Instance A saves key "processed" into cache.
2. A crashes BEFORE deducting stock.
3. B receives redelivery, sees key exists.
4. B skips it.
5. The reservation command is never executed.
~~~

Conversely, if marking processed **after** calling an external API:

~~~text
1. A calls reservation API; API commits.
2. A crashes BEFORE saving key "processed".
3. B sees no key and calls the API again.
4. Stock may be reserved twice.
~~~

These two windows show that **single-step deduplication non-atomic with the side effect is insufficient** to claim “exactly once”.

## 3. What Is Idempotent Receiver?

The **Idempotent Receiver** EIP guarantees that when a message representing **the same business operation** is sent repeatedly, the receiver produces no new side effects beyond those of the first valid execution.

For `reserveStock(commandId=CMD-1001)`:

~~~text
reserve(CMD-1001) 1st time -> RESERVED, stock -2
reserve(CMD-1001) 2nd time -> returns saved RESERVED, stock unchanged
reserve(CMD-1001) 3rd time -> returns saved RESERVED, stock unchanged
~~~

Whereas for `CMD-1002`, a **new business-authorized operation**:

~~~text
reserve(CMD-1002) -> may reserve another 2 items,
                     subject to available stock and policy.
~~~

Idempotency does not mean **every message with similar content is ignored**. It means **multiple attempts of the same business operation** yield an effect equivalent to executing once.

### 3.1. Three Distinct Layers

| Layer | Question | Appropriate Evidence |
| --- | --- | --- |
| **Transport delivery** | Was the record delivered/ACKed? | Broker offset, delivery tag, ACK/transaction |
| **Receiver processing** | Was the operation received/in progress/finalized? | Shared idempotency ledger/inbox |
| **Business effect** | Did stock/payment/order commit once? | Unique business operation at the mutation site |

A system can receive the same record multiple times and execute handlers multiple times while **committing the business effect only once**. That is a far more realistic goal than claiming every component across the entire system runs strictly once.

### 3.2. Idempotency Is Not Correlation

| Identifier | Purpose | Changes on Retry/Redelivery? |
| --- | --- | --- |
| `MessageHeaders.ID` | Message envelope ID | May change when message is reconstructed |
| Kafka topic/partition/offset | Transport record position | May change on republish |
| JMS/AMQP delivery metadata | Delivery attempt, redelivery flag | May change |
| `businessCorrelationId` | Traces steps of the same order | Usually kept, though may be too broad |
| `executionId` | Correlates replies belonging to one workflow run | May change on reprocess |
| **`operationId` / `commandId`** | Identifies a task with side effects | **Must remain unchanged** across retries of the same task |
| `traceId`, `spanId` | Distributed observability | Never replaces idempotency key |

An Aggregator may group by `executionId` while an Idempotent Receiver deduplicates by `commandId + lineId + operationType`. **Both are needed**; do not collapse them into one ID for convenience.

## 4. Precisely Scoped Idempotency Keys

For example, an order has three line items sharing one `commandId` for the batch. Using only `commandId` to deduplicate would accidentally drop the remaining two lines.

### 4.1. Scoped by Operation

~~~text
(tenantId, commandId, lineId, operationType)

(shop-a, CMD-1001, LINE-01, RESERVE_STOCK)
(shop-a, CMD-1001, LINE-02, RESERVE_STOCK)
(shop-a, CMD-1001, LINE-03, RESERVE_STOCK)
~~~

Each line is a separate operation. A `RELEASE_STOCK` command for the same line has a different `operationType` and **will not** be wrongly blocked as a reservation.

### 4.2. Fields That Must Not Enter the Key

- `retryCount`, `deliveryAttempt`, `JMSXDeliveryCount`: vary by attempt number.
- Timestamp of when a consumer **re-receives** the message.
- `MessageHeaders.ID`: may be regenerated on every envelope.
- `executionId` if the business contract states reprocessing the same command **must not** commit again.
- `traceId`, `spanId`: strictly for observability.
- Uncanonicalized raw payload hashes: field order/serializers can make the same command produce different hashes.

### 4.3. Scoping by Tenant and Trusted Sources

`commandId=CMD-1001` for `shop-a` and `shop-b` are not the same operation. On the other hand, a client must never self-declare `tenantId=shop-b` to read tenant B's cached result.

Keys must be constructed from **authenticated identity** and the business contract. If a consumer reads data from external headers, verify signatures/ACLs/tenant mappings before using the key.

### 4.4. Same Key with Different Payload Is a Conflict

Two requests:

~~~text
Key: (shop-a,CMD-1001,LINE-02,RESERVE_STOCK)
Original: sku=BOOK-42, quantity=2
Duplicate: sku=BOOK-42, quantity=20
~~~

Never:

1. Reserve another 20 items; or
2. Return `RESERVED` from the 2-item command and let the client believe 20 were reserved.

Store **business-significant immutable fields** or a **versioned canonical request fingerprint**; when the key matches yet contents differ, return `IDEMPOTENCY_CONFLICT` and audit. Never silently overwrite the ledger with the latest request.

## 5. Defining Correctness Across Multiple Replicas

A distributed receiver needs at least these invariants:

1. **At most one committed effect per operation key** within a defined consistency scope.
2. **All valid duplicates yield the same terminal outcome** or a response indicating the operation is still processing.
3. **Conflicting duplicates must not alter committed effects**.
4. **Pre-commit crashes** allow safe reprocessing; **post-commit crashes** allow retrieving the old outcome.
5. **Two instances contending for the same key** are resolved atomically, not via check-then-act on private caches.
6. **Operations with different keys** can still run concurrently; avoid pointless global system locks.
7. When business effects live in **external systems** outside the transaction, **target-side idempotency or reconciliation** is required; local locks are insufficient.

### 5.1. Race Condition of `contains → add`

~~~java
// UNSAFE for multi-instance, and already races within a single JVM
if (!processedIds.contains(key)) {
    reserveStock(command);
    processedIds.add(key);
}
~~~

Two instances can simultaneously see “key absent” and both invoke `reserveStock`.

Even with a thread-safe map, the two steps `contains` and `add` are not atomic as a single operation. And if the map lives only in one instance's RAM, process-level atomicity **does not** create cross-node atomicity.

### 5.2. Race Diagram

~~~mermaid
sequenceDiagram
    participant A as Instance A
    participant B as Instance B
    participant DB as Shared database
    A->>DB: key exists?
    B->>DB: key exists?
    DB-->>A: no
    DB-->>B: no
    A->>DB: reserve stock
    B->>DB: reserve stock
    Note over A,B: Two business effects unless one atomic claim/commit prevents it
~~~

The solution requires a **shared consistency boundary**: a unique index/transaction in the DB owning the mutation, or an idempotent backend that accepts the token and executes the mutation once itself.

## 6. Comparison Table of Distributed Idempotency Strategies

| Solution | What It Protects Well | What It Does Not Guarantee Alone |
| --- | --- | --- |
| **Unique constraint in same DB transaction as mutation** | Blocks two workers from committing the same effect in that DB | External APIs outside the transaction, broker publish/ACK |
| **Idempotent endpoint at target system** | Actual side-effect owner receives same key and returns saved outcome | Caller must preserve key and distinguish payload conflicts |
| **Shared `ConcurrentMetadataStore`** | Atomic key claim/selection across SI instances if backend supports it | Atomic commit with business DB/API; business completion |
| **Redis `SET NX` + TTL** | Time-bounded claim/lease contention across instances | Old worker may continue after lease expiry; rollback/side effects |
| **Database inbox + outbox** | Durable input dedup and retryable output emission | External side effects outside the consistency boundary |
| **Partition/order by business key** | Reduces contention when one owner is assigned | Failover/rebalance/redelivery can still duplicate |
| **Local `ConcurrentHashMap`** | Single-JVM demos/tests | Restarts, other replicas, durable correctness |

**Preferred option:** If the operation ledger and domain state reside in the same database with reliable transactions/unique indexes, start with **unique constraints + committing outcomes in the same transaction**. If the side effect is an **external HTTP API**, you need a target-supported idempotency token or an explicit reconciliation workflow.

### 6.1. “Use Redis to Lock” Is Not a Complete Answer

Redis can be very useful for reducing contention and coordinating workers, yet a TTL key alone **cannot** assert that an effect occurred only once. You must address lease expiration, stale workers, lock renewal, fencing, Redis disconnections, and consistency of the backend where the mutation truly occurs.

### 6.2. “Kafka Exactly-Once” Does Not Protect Every Side Effect

A messaging platform's transactional/exactly-once features have a specific scope, such as certain processing pipelines and record writes inside the broker. They **do not automatically extend** atomic transactions to arbitrary databases or HTTP payment gateways. When the requirement is “never charge twice”, checks at **the charging system** determine correctness.

## 7. Reliable Approach: Shared Transaction for Ledger and Mutation

Example using **PostgreSQL** and Spring JDBC to reserve stock. Data model:

~~~sql
CREATE TABLE inventory_stock (
    tenant_id       VARCHAR(80) NOT NULL,
    sku             VARCHAR(120) NOT NULL,
    available       BIGINT NOT NULL CHECK (available >= 0),
    PRIMARY KEY (tenant_id, sku)
);

CREATE TABLE reservation_operation (
    tenant_id       VARCHAR(80) NOT NULL,
    command_id      VARCHAR(120) NOT NULL,
    line_id         VARCHAR(120) NOT NULL,
    operation_type  VARCHAR(40) NOT NULL,
    sku             VARCHAR(120) NOT NULL,
    quantity        INTEGER NOT NULL CHECK (quantity > 0),
    state           VARCHAR(20) NOT NULL,
    outcome_code    VARCHAR(40),
    PRIMARY KEY (
        tenant_id, command_id, line_id, operation_type
    )
);
~~~

**Data invariants:**

- The primary key is the approved **operation identity**.
- `sku` and `quantity` are stored to verify duplicates do not alter the request contents.
- `state=PROCESSING` exists only inside the **uncommitted transaction** of this illustrative flow; when committed, it must be `COMPLETED`. Never intentionally commit `PROCESSING` and hope the next worker guesses whether it succeeded.
- `outcome_code` is the finalized business outcome: `RESERVED` or `OUT_OF_STOCK`.
- `executionId` is omitted from the primary key, since a retry/replay of the same command may run under a new execution.

### 7.1. Why Does `ON CONFLICT DO NOTHING` Help?

A database unique constraint acts as a **shared arbiter** across instances. Under PostgreSQL `READ COMMITTED`, when two transactions insert the same primary key, one must wait or hit a unique conflict per DB semantics; both can never commit two ledger rows for the same key.

More importantly: **the inventory mutation and the operation outcome update must commit in the same transaction**. If the process dies before commit, the DB rolls back both ledger and mutation. If it dies after commit, duplicates see the saved outcome.

~~~mermaid
flowchart TD
    IN["Receive ReserveCommand"] --> TX["BEGIN transaction"]
    TX --> I["INSERT operation key ON CONFLICT DO NOTHING"]
    I --> L["SELECT row FOR UPDATE"]
    L --> C{"Existing state and request?"}
    C -->|"Same key, same request, completed"| R["Return recorded outcome"]
    C -->|"Same key, different request"| ERR["IDEMPOTENCY_CONFLICT / ROLLBACK"]
    C -->|"New operation"| U["UPDATE stock atomically"]
    U --> O["Write outcome to ledger"]
    O --> COM["COMMIT"]
    R --> END["Reply for current execution"]
    COM --> END
~~~

**Transaction note:** this diagram protects the **internal database**. If the `UPDATE stock` step actually makes an external HTTP call, atomicity no longer holds as depicted.

## 8. Java 17: Command, Receipt, and Transacted Service

The code snippets below focus on core logic, omitting package/build/dependency declarations. They demonstrate **PostgreSQL + Spring JDBC + Spring Transaction** with the Section 7 schema, and must be invoked through a Spring bean so `@Transactional` takes effect.

### 8.1. Java Records

~~~java
record ReserveStockCommand(
    String tenantId,
    String commandId,
    String executionId,
    String orderId,
    String lineId,
    String sku,
    int quantity
) {
    ReserveStockCommand {
        require(tenantId, "TENANT");
        require(commandId, "COMMAND_ID");
        require(executionId, "EXECUTION_ID");
        require(orderId, "ORDER_ID");
        require(lineId, "LINE_ID");
        require(sku, "SKU");

        if (quantity <= 0) {
            throw new IllegalArgumentException("INVALID_QUANTITY");
        }
    }

    private static void require(String value, String name) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(name + "_MISSING");
        }
    }
}

record ReservationReceipt(
    String executionId,
    String orderId,
    String lineId,
    String outcomeCode
) {}

record OperationRow(
    String sku,
    int quantity,
    String state,
    String outcomeCode
) {}

final class IdempotencyConflict extends RuntimeException {
    IdempotencyConflict() {
        super("IDEMPOTENCY_CONFLICT");
    }
}
~~~

`ReserveStockCommand` represents data already authenticated at ingress of the demo flow. **Never** take a client-supplied `tenantId` while skipping HTTP/broker AuthN/AuthZ.

### 8.2. Transactional Service

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class JdbcReservationService {
    private final JdbcTemplate jdbc;

    JdbcReservationService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public ReservationReceipt reserve(ReserveStockCommand cmd) {
        String operation = "RESERVE_STOCK";

        // PostgreSQL: unique key arbitrates across all replicas.
        int inserted = jdbc.update("""
            INSERT INTO reservation_operation
              (tenant_id, command_id, line_id, operation_type,
               sku, quantity, state, outcome_code)
            VALUES (?, ?, ?, ?, ?, ?, 'PROCESSING', NULL)
            ON CONFLICT DO NOTHING
            """,
            cmd.tenantId(), cmd.commandId(), cmd.lineId(),
            operation, cmd.sku(), cmd.quantity());

        // SELECT after INSERT with FOR UPDATE to hold the row lock
        // in the transaction until business mutation completes.
        OperationRow row = jdbc.queryForObject("""
            SELECT sku, quantity, state, outcome_code
              FROM reservation_operation
             WHERE tenant_id = ? AND command_id = ?
               AND line_id = ? AND operation_type = ?
             FOR UPDATE
            """,
            (rs, index) -> new OperationRow(
                rs.getString("sku"),
                rs.getInt("quantity"),
                rs.getString("state"),
                rs.getString("outcome_code")),
            cmd.tenantId(), cmd.commandId(), cmd.lineId(), operation);

        if (row == null) {
            throw new IllegalStateException("OPERATION_ROW_MISSING");
        }

        // Same identity but different SKU/quantity: reject, do not reuse.
        if (!cmd.sku().equals(row.sku())
                || cmd.quantity() != row.quantity()) {
            throw new IdempotencyConflict();
        }

        // Redelivery after commit: return outcome, do not deduct stock again.
        if ("COMPLETED".equals(row.state())) {
            return new ReservationReceipt(
                cmd.executionId(), cmd.orderId(),
                cmd.lineId(), row.outcomeCode());
        }

        if (inserted != 1 || !"PROCESSING".equals(row.state())) {
            // Do not blindly run side effects for an inherited state
            // of unclear provenance; require reconciliation.
            throw new IllegalStateException(
                "OPERATION_STATE_REQUIRES_RECONCILIATION");
        }

        // Conditional, atomic mutation in the same database and transaction.
        int changed = jdbc.update("""
            UPDATE inventory_stock
               SET available = available - ?
             WHERE tenant_id = ? AND sku = ?
               AND available >= ?
            """,
            cmd.quantity(), cmd.tenantId(),
            cmd.sku(), cmd.quantity());

        String outcome = changed == 1
            ? "RESERVED"
            : "OUT_OF_STOCK";

        jdbc.update("""
            UPDATE reservation_operation
               SET state = 'COMPLETED', outcome_code = ?
             WHERE tenant_id = ? AND command_id = ?
               AND line_id = ? AND operation_type = ?
            """,
            outcome,
            cmd.tenantId(), cmd.commandId(), cmd.lineId(), operation);

        // Spring transaction proxy commits before the caller receives the result.
        return new ReservationReceipt(
            cmd.executionId(), cmd.orderId(), cmd.lineId(), outcome);
    }
}
~~~

### 8.3. Why Does This Version Prevent Duplicates Across Multiple Instances?

Within the same PostgreSQL database, using `READ_COMMITTED` transactions and a unique primary key:

1. **A** inserts the operation key, locks the row, and updates stock.
2. **B** inserting the same key must wait on PostgreSQL's unique-conflict/transaction logic.
3. If **A commits**, **B** sees the `COMPLETED` row and returns the saved outcome.
4. If **A rolls back** due to a crash, B can become the worker executing the operation.
5. If A commits and loses the ACK: redelivery reads the committed outcome instead of deducting again.

**Code limitations:** demonstrates one transaction on **one** database. It omits retries for SQL deadlocks/connection failures, outbox emission, cross-region active-active database replication, external APIs, and schema migrations/Gradle build files. The goal is clarifying **where to place the atomic constraint**.

### 8.4. Do Not Misapply `@Transactional` Boundaries

In Spring, `@Transactional` is typically applied via proxies. A **self-invocation** call `this.reserve(...)` inside the same class can bypass the proxy and transaction advice depending on configuration. With `IntegrationFlow`, inject the Spring-managed service bean and invoke the method via the appropriate endpoint/proxy, then test real transactions against a database.

If inventory lives in a **different database** or behind an HTTP call, this annotation **does not make both systems commit/roll back together**.

### 8.5. `OUT_OF_STOCK` Is Also an Outcome to Remember

Suppose command `CMD-1001` returned `OUT_OF_STOCK` when inventory was depleted. An hour later stock is replenished, and the same command is redelivered. Strict idempotency for a **terminal result** in this example will **return `OUT_OF_STOCK` again**, rather than re-attempting reservation because conditions changed.

If the business wants to **retry reserving after restock**, issue a **new command** or define an explicit retryable state — never secretly mutate the outcome of a finalized command.

## 9. Spring Integration Java DSL: Idempotent Handler in a Flow

In this design, the **primary safeguard** is `JdbcReservationService` with the shared transaction from Section 8. Spring Integration handles receiving, routing, controlled retries, error channels, and replies.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
class IdempotentReservationFlowConfiguration {

    @Bean("reservations.commands.in")
    DirectChannel commandsIn() {
        return new DirectChannel();
    }

    @Bean("reservations.receipts.out")
    QueueChannel receiptsOut() {
        // Used for observation in lessons/tests.
        return new QueueChannel();
    }

    @Bean
    IntegrationFlow reserveEachCommand(JdbcReservationService service) {
        return IntegrationFlow.from("reservations.commands.in")
            .handle(service, "reserve")
            .channel("reservations.receipts.out")
            .get();
    }
}
~~~

~~~text
Broker / HTTP / Gateway
  -> Validate principal, tenant, schema, business IDs
  -> reservations.commands.in
  -> JdbcReservationService.reserve (transaction + unique ledger)
  -> reservations.receipts.out
  -> Adapter / Aggregator / caller
~~~

The code assumes `JdbcReservationService` and JDBC/transaction beans are configured by the Spring application, and that inbound adapters construct typed `ReserveStockCommand` payloads. **The demo's `QueueChannel` is in-memory** and neither replaces a durable broker nor proves receipts were processed downstream.

### 9.1. Retry with the Same Payload, Never Generate a New Command

An endpoint can attach `RequestHandlerRetryAdvice` to retry transient JDBC/transport errors per policy. However:

- `IDEMPOTENCY_CONFLICT`, invalid schemas, or missing permissions **must not** be retried.
- On SQL timeouts/connection resets, it may be uncertain whether the transaction committed; retrying with **the same operation key** is safe per the DB contract.
- Never generate a new `commandId` on each attempt.
- Use backoff and a bounded retry budget to avoid all instances hammering a struggling DB.

Exact retry configuration must be checked against your Spring Integration/Spring Retry version; test even exceptions occurring **after commit before response**.

### 9.2. Use Metadata Headers for Observability, Not as the Source of Correctness

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

ReserveStockCommand command = new ReserveStockCommand(
    "shop-a", "CMD-1001", "RUN-01",
    "ORD-981", "LINE-02", "BOOK-42", 2);

Message<ReserveStockCommand> message =
    MessageBuilder.withPayload(command)
        .setHeader("businessCorrelationId", "ORD-981")
        .setHeader("commandId", "CMD-1001")
        .setHeader("executionId", "RUN-01")
        .build();
~~~

Headers are convenient for Routers/tracing/correlation, yet **validated payloads and identities** are the source for deriving operation keys. Across Kafka/AMQP/JMS, header mappers can alter types or drop headers; round-trip contract tests are required.

## 10. `IdempotentReceiverInterceptor` and a Shared Metadata Store

Spring Integration offers **Idempotent Receiver** interceptor support for `MessageHandler`s. A common setup pairs `IdempotentReceiverInterceptor` with a `MessageSelector`, such as `MetadataStoreSelector`, to determine whether a message has been seen before.

For multiple instances to share state, a **shared backend** providing atomic metadata operations is required, such as a properly configured Redis or JDBC `ConcurrentMetadataStore` implementation. A `SimpleMetadataStore` or per-JVM map **does not** provide distributed deduplication.

~~~text
Instance A ----\
                \      atomic claim / putIfAbsent
Instance B -------> Shared ConcurrentMetadataStore
                /              |
Instance C ----/               v
                          Key exists?
~~~

### 10.1. “Duplicates” May Be Marked Rather Than Dropped

In Spring Integration, `IdempotentReceiverInterceptor` has configurable semantics for **marking duplicates in a header or discarding/routing messages**. Never simply attach the interceptor and assume duplicates are **always** skipped and the business handler cannot run.

Verify and test:

- **Which business identity** the key selector uses.
- Whether the store is a shared backend or per-JVM.
- Whether duplicates are **marked**, **discarded**, **thrown**, or **routed** per configuration.
- For request–reply duplicates, whether callers receive the **recorded result** or time out because the message was dropped.
- If a claim marker is written before the handler and the handler fails, how retries/recovery work.
- Whether TTL and cleanup policies cover DLQ replays and delayed messages.

### 10.2. Marking “Seen” Before Business Commit Risks Losing Work

A `MetadataStoreSelector` can block duplicates very early, yet because the metadata claim is created **before the handler finishes**, a receiver crash can leave a key with no business result. If duplicates are discarded based on that key, the message is treated as “processed” even though the effect never happened.

Therefore:

> **Use a shared metadata selector as a screening/coordination layer when appropriate; never replace transactions/idempotent operations where business effects commit.**

In flows requiring reliable data, it is usually better to let duplicates **enter the idempotent service** to retrieve the saved result, or design an explicit `IN_PROGRESS/COMPLETED` state machine with expiry/reconciliation.

### 10.3. When Is the Interceptor Very Useful?

- Blocking notifications that **have no side effects** or where duplicates may be dropped per business contract.
- Reducing duplicate work ahead of CPU-heavy handlers, provided a retry/repair path exists if a claimed key fails in the handler.
- Checking previously processed messages at the same boundary backed by the shared metadata store.
- Adding observability for duplicate hits to detect abnormal producer/broker retries.

Never use an interceptor flag to replace **idempotency at payment gateways**, reservation APIs, or the DB owning the mutation.

## 11. Redis Atomic Claims, TTL, Leases, and Fencing Tokens

A common pattern:

~~~text
SET operation-key worker-A NX PX 30000
~~~

Redis `SET NX PX` can ensure only one worker claims an existing-absent key. However, this Redis key is a **lease/claim**, not proof that the operation committed.

### 11.1. Race When a Lease Expires

~~~mermaid
sequenceDiagram
    participant A as Worker A
    participant R as Redis lease
    participant B as Worker B
    participant S as Storage/side-effect owner
    A->>R: Acquire lease, TTL=30s
    R-->>A: acquired
    Note over A: Pauses for 40s (GC/network)
    B->>R: Acquire after TTL expires
    R-->>B: acquired
    B->>S: Commit effect
    Note over A: Resumes after lease expiry
    A->>S: Also tries to commit effect
~~~

Worker A **receives no magical notification that its lease expired**. If A keeps calling the external API, two workers can produce two effects.

### 11.2. Fencing Tokens to Block Stale Workers

One technique is issuing a **monotonically increasing fencing token** on each claim acquisition, and having the **side-effect destination** reject tokens older than the latest accepted token.

~~~text
A acquires token 41
A pauses
B acquires token 42
B commits at protected storage with token 42
A resumes; storage rejects token 41
~~~

This is only safe if the target resource **actually checks the fencing token atomically alongside the mutation**. If the target is an API unaware of tokens, having a token in Redis **does not stop A's effect**.

### 11.3. Leases and Processed Results Are Two Kinds of State

| State | Meaning | TTL/Retention |
| --- | --- | --- |
| `PROCESSING_LEASE` | Who is processing and for how long | Short, governed by renewal/lease policy |
| `COMPLETED_RESULT` | What the operation committed and its outcome | Governed by business retention/replay/compliance |
| `FAILED_FINAL` | Which terminal error occurred | Per contract |
| `UNKNOWN_RECONCILE` | May have committed externally, unconfirmed | Never blindly retry side effect |

Never use **a single 30-second TTL Redis key** for both “worker ownership” and “operation completed”. After 30 seconds, the vanished key lets an old duplicate enter and trigger a new side effect.

## 12. Side Effects in External Services: Local DB Is Not Enough

Suppose `InventoryGateway` calls an external warehouse over HTTP. A worker records `operation_state=PROCESSING` in its local DB, calls the API, and plans to save the result afterward.

~~~text
A: INSERT local operation_state(PROCESSING)
A: HTTP reserve -> external inventory commits
A: network timeout / crash before local COMPLETED
B: redelivery -> sees PROCESSING/UNKNOWN
~~~

If B relies solely on the local DB and issues a new reservation, stock may be reserved twice. The local DB **does not share a transaction** with the external warehouse.

### 12.1. Preferred Option: External API with Idempotency Keys

~~~http
POST /inventory/reservations
Idempotency-Key: shop-a:CMD-1001:LINE-02:RESERVE_STOCK
Content-Type: application/json

{"sku":"BOOK-42","quantity":2}
~~~

This request/response is an **illustrative protocol**; actual headers, formats, and semantics depend on the real API. What must be ensured at the external service:

1. Idempotency keys are scoped by principal/tenant.
2. Same key and matching request return the **same terminal result**.
3. Same key with a different request returns a conflict.
4. Recording the key/result is **atomic with the mutation**.
5. Keys/results persist at least across the committed retry/replay window.

When a caller times out, it can retry with **the same key**, never issuing a new key.

### 12.2. If the External Service Does Not Support Idempotency

Pick a business-approved strategy:

- Query transaction status using a reconcilable request/reference ID.
- Use a reconciliation/settlement system to confirm whether the effect occurred.
- Split requests into prepare/confirm if supported by the external API.
- Route to manual review instead of retrying a charge/reservation that may have committed.

You **cannot** guarantee a single effect on an arbitrary external service using only a distributed lock in the calling system. Target-side coordination or explicit uncertainty-handling procedures are required.

### 12.3. “Exactly Once” Must Always State **Where**

An accurate statement should be:

> For operation key K, the inventory database executes at most one committed mutation per constraint and transaction X, while message transport may redeliver multiple times.

Avoid broadly claiming “the system processes exactly once” when brokers, DBs, HTTP, multiple DCs, and DLQ replays are involved without specifying the consistency boundary.

## 13. Outbox: Commit Business State Then Publish Events

After reserving stock, the service must publish `StockReserved` to a downstream Router/Aggregator. If the stock commit succeeds but publishing fails, the receiver has the business effect without an outcome event.

### 13.1. Transactional Outbox in the Same DB

~~~text
BEGIN TRANSACTION
  INSERT operation ledger (unique key)
  UPDATE inventory_stock
  MARK operation COMPLETED + recorded result
  INSERT outbox_event(eventId, operation key, payload)
COMMIT

Outbox publisher later:
  load unpublished event
  publish to broker
  retry if broker ACK lost
  mark published / reconcile
~~~

If the publisher crashes after the broker receives the event but before marking it published, the event may be published **again**. Event consumers need idempotency by **event ID or business operation**, depending on the contract. Outboxes prevent **losing notifications**, without promising the broker receives events strictly once.

### 13.2. Replies Can Be Reconstructed

When a message is redelivered after business commit, the receiver can:

- Return the saved `ReservationReceipt` for the **current `executionId`**.
- Or re-emit an idempotent event/outcome under a stable `eventId`.
- Without creating any new business mutation.

If the new receipt carries a new execution ID, an Aggregator may need to **collect replies under the new group**, while the underlying business effect remains unchanged. Reprocessing does not mean re-committing.

### 13.3. Never Emit Two Final Outcomes

If an Aggregator already closed a group and a duplicate result arrives later, a new group must not form into a second “completion”. Use **closed-execution state/tombstones** and finalization CAS so there is only one **final decision** per execution, unless the business contract permits **versioned updates**.

## 14. Retries, Redelivery, and DLQ Replays Across Multiple Instances

A command can be attempted at multiple layers:

~~~text
Producer publishes K
    |
Broker delivers to A
    |
A local retry: attempt #1,#2
    |
Broker redelivery to B
    |
B local retry: attempt #3,#4
    |
DLQ/replay to C later
    |
C attempts #5 ...
~~~

Nothing guarantees local retry counts, JMS delivery counts, Kafka offsets, or DLQ headers **stay intact across every layer**.

### 14.1. Immutable Identity Must Cross Transports

Fields to preserve:

- Verified `tenantId`.
- Immutable `commandId`/`operationId`.
- `lineId`/`subTaskId` if one command has multiple effects.
- `operationType` to separate reserve vs. release commands.
- `schemaVersion` to interpret content accurately on replay.
- `executionId` for workflow correlation.
- `originalEventId`/`replayOf` if needed for investigation.

Message envelope IDs, processing timestamps, trace spans, and delivery attempts can change and are strictly for **diagnostics**.

### 14.2. Redeliveries Can Run in Parallel

Even with a consumer group on a queue, network glitches, visibility timeouts, rebalances, or retry topics can cause the same business operation **to run in parallel** on two workers under certain patterns.

Never rely on “the broker delivers to only one consumer at a time” as your final correctness guarantee. The atomic ledger at the business owner must withstand contention.

### 14.3. DLQ Replays Preserve Business Intent

A replay of **the same command** preserves the operation key. A **new valid command** must receive a newly business-issued identity that is explicitly audited and authorized. If an operator changes `commandId` just to “rerun past dedup”, side effects can be duplicated.

If a DLQ holds old-version messages, use a versioned decoder and migration tests before replaying rather than reinterpreting payloads under a different new contract.

## 15. Retention Period of Idempotency Keys and Consequences of Short TTLs

Suppose:

~~~text
T0         CMD-1001 committed
T0 + 1 day Broker still has delayed retry
T0 + 2 day Ledger row deleted by short TTL
T0 + 3 day DLQ replays CMD-1001
~~~

Without evidence the operation committed, the receiver may treat `CMD-1001` as a new command and reserve stock again.

### 15.1. Retention Must Be Based on the Longest Replay Horizon

Sum or evaluate:

- How long messages can remain on the broker.
- Delays of retry topics/queues.
- How long DLQs allow manual replays.
- How long producers/partners may resend.
- Historical reconciliation/audit regulations.
- External API idempotency key TTLs.
- Tombstone retention once detailed results are deleted.

A uniform 24-hour TTL may be insufficient if business rules permit reprocessing within 30 days.

### 15.2. Deleting Sensitive Data While Still Preventing Duplicates

Retention rules may require deleting payloads/PII while keeping a **minimal tombstone** with an opaque operation identity and `COMPLETED` state, if lawful and policy-compliant. Never retain keys containing raw PII longer than necessary. Decide jointly with security/compliance.

### 15.3. Key Reuse

If a producer reuses `commandId` after some time, is that **a new command or a protocol error**? A solid contract forbids reusing IDs within the retention window and enforces explicit namespaces/versions. If reuse is valid, use a managed epoch/operation version rather than silently purging the ledger and hoping old redeliveries do not arrive.

## 16. Unit Testing: Simulating Two Replicas with a Shared Ledger

Before using real PostgreSQL, an in-JVM model lets you test the **shared state store** principle. This is a fake strictly for unit tests and does not replace multi-process DB testing.

### 16.1. Shared Fake Operation Ledger

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

record Key(String tenant, String commandId, String lineId, String op) {}

record FakeStoredResult(String sku, int quantity, String outcome) {}

final class SharedFakeInventory {
    private final ConcurrentMap<Key, FakeStoredResult> completed =
        new ConcurrentHashMap<>();

    private final AtomicInteger commits = new AtomicInteger();

    ReservationReceipt reserve(ReserveStockCommand command) {
        Key key = new Key(
            command.tenantId(), command.commandId(),
            command.lineId(), "RESERVE_STOCK");

        FakeStoredResult result = completed.compute(key, (k, old) -> {
            if (old != null) {
                if (!old.sku().equals(command.sku())
                        || old.quantity() != command.quantity()) {
                    throw new IdempotencyConflict();
                }
                return old;
            }

            commits.incrementAndGet();
            return new FakeStoredResult(
                command.sku(), command.quantity(), "RESERVED");
        });

        return new ReservationReceipt(
            command.executionId(),
            command.orderId(),
            command.lineId(),
            result.outcome());
    }

    int committedOperations() {
        return commits.get();
    }
}
~~~

`ConcurrentHashMap.compute` makes operations on **one key within the same JVM** atomic enough for a fake. Two separate Spring application processes **do not** share this object; production still needs a database/remote backend with real guarantees.

### 16.2. JUnit 5 Concurrent Test

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.junit.jupiter.api.Test;

class SharedFakeInventoryTest {

    private static ReserveStockCommand command(String execution) {
        return new ReserveStockCommand(
            "shop-a", "CMD-1001", execution,
            "ORD-981", "LINE-02", "BOOK-42", 2);
    }

    @Test
    void concurrentCallsForSameKeyHaveOneFakeCommit()
            throws Exception {
        SharedFakeInventory shared = new SharedFakeInventory();
        int workers = 20;
        CountDownLatch start = new CountDownLatch(1);

        ExecutorService executor = Executors.newFixedThreadPool(workers);
        try {
            List<Callable<ReservationReceipt>> jobs = new ArrayList<>();
            for (int i = 0; i < workers; i++) {
                String execution = "RUN-" + i;
                jobs.add(() -> {
                    start.await();
                    return shared.reserve(command(execution));
                });
            }

            List<Future<ReservationReceipt>> futures = new ArrayList<>();
            for (Callable<ReservationReceipt> job : jobs) {
                futures.add(executor.submit(job));
            }
            start.countDown();

            for (Future<ReservationReceipt> future : futures) {
                assertEquals("RESERVED", future.get().outcomeCode());
            }
            assertEquals(1, shared.committedOperations());
        } finally {
            executor.shutdownNow();
        }
    }

    @Test
    void sameKeyDifferentRequestIsAConflict() {
        SharedFakeInventory shared = new SharedFakeInventory();
        shared.reserve(command("RUN-1"));

        ReserveStockCommand changed = new ReserveStockCommand(
            "shop-a", "CMD-1001", "RUN-2",
            "ORD-981", "LINE-02", "BOOK-42", 20);

        assertThrows(IdempotencyConflict.class,
            () -> shared.reserve(changed));

        assertEquals(1, shared.committedOperations());
    }

    @Test
    void sameCommandInDifferentTenantsIsNotSameKey() {
        SharedFakeInventory shared = new SharedFakeInventory();
        shared.reserve(command("RUN-1"));
        shared.reserve(new ReserveStockCommand(
            "shop-b", "CMD-1001", "RUN-2",
            "ORD-981", "LINE-02", "BOOK-42", 2));

        assertEquals(2, shared.committedOperations());
    }
}
~~~

**Limitation:** the test proves the shared fake map prevents contention across 20 threads **in one process**. It does not prove PostgreSQL isolation, network partitions, transaction rollbacks, crashes/restarts, or atomicity with the inventory database. Those belong to integration tests.

## 17. Integration Tests: Two Spring Instances, One PostgreSQL

This is a **mandatory test suite** before deploying multiple replicas. Tests must use **two service beans/application contexts or two JVMs/containers** connected to **the same PostgreSQL instance**, rather than two in-RAM maps.

### 17.1. 50-Request Race Test for One Operation

~~~text
Given:
  inventory_stock(shop-a, BOOK-42).available = 100
  reservation_operation = empty
  2 independent application instances -> same PostgreSQL
  Same validated ReserveStockCommand sent 50 times concurrently

When:
  Start requests together using a barrier
  Wait for all requests or bounded errors/retries

Then:
  Exactly one ledger row for operation key
  Row state=COMPLETED, outcome_code=RESERVED
  Inventory available = 98, not 0 or -2
  All successful replies report same business outcome
  No cross-tenant data leak
~~~

### 17.2. Commit Succeeded, ACK Lost

~~~text
1. Send command to A.
2. Allow DB transaction to COMMIT.
3. Simulate lost response / consumer crash before ACK.
4. Broker redelivers same command to B.
5. Assert stock is decremented only once.
6. Assert B reads existing result and can ACK safely.
~~~

To test accurately, **inject failures at the post-commit boundary**. Do not merely throw an exception **before** repository commit, since that test fails to exercise the hardest failure window.

### 17.3. Crash Before Commit

~~~text
1. A starts DB transaction and reserves operation row.
2. A fails before COMMIT; DB rolls back.
3. B receives same command.
4. B can perform the transaction.
5. Exactly one committed inventory mutation and ledger result.
~~~

### 17.4. Concurrency Across Different Operations

Verify `CMD-1001` and `CMD-1002` are **two valid operations**, not serialized globally across the entire system. If they update the same SKU, the database must keep stock non-negative via conditional updates. A design locking the whole table might satisfy some invariants yet have poor throughput; measure **lock contention** and actual latency.

### 17.5. Contract Conflict

Same operation key, but:

~~~text
Original: quantity=2, sku=BOOK-42
Replay:   quantity=20, sku=BOOK-42
~~~

Assert `IDEMPOTENCY_CONFLICT`, no extra commit, and never return the old outcome as if the new request were valid.

### 17.6. Restart/Multi-Instance

After A commits and then its process is **killed/restarted**, B must still retrieve the result from PostgreSQL. If a test only restarts one bean while keeping the same Java fake ledger, the result **proves nothing** about durability.

## 18. Testing Spring Integration Flows and Errors

Unit tests on `JdbcReservationService` do not prove DSL routing works. For `IdempotentReservationFlowConfiguration`, you must:

- Send a message into `reservations.commands.in`.
- Receive one `ReservationReceipt` on `reservations.receipts.out` for each demo request.
- Assert `executionId`/`orderId`/`lineId` match.
- Resend the same command: the handler may return **a new receipt for the second request**, yet the DB effect still happens only once.
- For conflicting duplicates: no fake `RESERVED` receipt is emitted; errors follow the proper error/rejection contract.
- If using `IdempotentReceiverInterceptor`, test **actual duplicate handling configuration** (mark/discard/throw) rather than merely counting DB updates.
- If switching to a request–reply Gateway, duplicates must not be dropped leaving the caller to time out; they must receive a cached outcome or an explicit status.

### 18.1. Where Are Retries Attached?

In Spring Integration, advice can run at the **message handler**. That differs from retries in inbound adapters, consumer containers, or outbox publishers. Test total attempts across layers to avoid retry storms:

~~~text
2 broker deliveries
× 3 handler attempts per delivery
= up to 6 attempts for the same business key
~~~

This multiplication is illustrative, not a framework default. Even with six attempts, only **one business effect** is allowed to commit for the operation key.

### 18.2. Error Channel Does Not Equal Retry/Deduplication

An `ErrorMessage` can appear depending on poller/executor/adapter configuration. However, sending an exception to `errorChannel` **does not automatically clear a claimed key** or roll back an external operation. Map error handling accurately by state:

- `INVALID_REQUEST`/`UNAUTHORIZED`: terminal rejection.
- `IDEMPOTENCY_CONFLICT`: reject/quarantine + audit.
- `DATABASE_TEMPORARY_UNAVAILABLE`: bounded retry with backoff.
- `ALREADY_COMPLETED`: return persisted outcome.
- `IN_PROGRESS`: defer/wait/retry later; never execute side effect concurrently.
- `EXTERNAL_OUTCOME_UNKNOWN`: reconcile; never re-charge/re-commit under a new key.

## 19. Comprehensive Test Matrix

| Scenario | What Must Be Proven |
| --- | --- |
| One new message | One operation row + one business effect |
| Local retry after transient error | Stable key, no repeated commit |
| A commits, ACK lost, B receives redelivery | B returns cached result, no extra stock deduction |
| A rolls back before commit | B can execute the operation |
| Two replicas call same key concurrently | Unique row and one mutation |
| Two replicas call different keys | Both valid commands processed |
| Same key, different quantity | Conflict, no erroneous outcome issued |
| Same `commandId` in another tenant | No false blocking or data leak |
| Both replicas restart | Durable ledger still active |
| DB unavailable | Never ACKs as success when execution uncertain |
| DB deadlock/serialization failure | Retries same key within bounded budget |
| Broker duplicate publish | No double effect |
| DLQ replay after many days | Retention suffices or reconciliation handles it |
| Redis lease expires, worker A resumes | Fencing at effect owner or safe fallback |
| Redis/store network partition | Never claims exactly-once lacking guarantees |
| External API committed, local response lost | Target idempotency/status lookup |
| Outbox publishes then ACK lost | Downstream consumer handles duplicate event idempotently |
| Aggregator receives duplicate reply | Does not count as two distinct item results |
| Late reply after group closes | Does not emit a second final outcome |
| Message headers lost across broker | Stable key/correlation preserved in contract |
| Schema version upgrade | Old commands interpreted properly on replay |
| Ledger TTL expires too early | Tests expose duplicate-effect risk |
| Spoofed request key | Tenant AuthN/AuthZ and conflict detection |
| 0 replies from downstream | Deadline watcher handles it; never waits forever |
| Load test 10k ops/s | Lock contention, queue depth, latency, and DB hot keys |

**Do not assert only “API returned 200” or “output contains receipt”.** Verify via **committed data** and prohibited behaviors such as a second inventory decrement.

## 20. Observability for Multi-Instance Idempotency

Metrics and traces should separate **deliveries**, **handler executions**, and **actually committed business operations**.

| Signal | Purpose |
| --- | --- |
| `messages_received_total` | Counts inbound deliveries/republishes |
| `handler_attempts_total` | Reveals local retries |
| `idempotency_claim_new_total` | New operations |
| `idempotency_hit_completed_total` | Duplicates returning saved results |
| `idempotency_conflict_total` | Same key with differing data |
| `idempotency_inflight_total` | Operations still processing/waiting |
| `business_effect_committed_total` | Effects actually committed |
| `db_unique_conflict_total` | Concurrent contention |
| `db_transaction_retry_total` | Deadlock/serialization/network retries |
| `outbox_pending_age` | Committed events not yet emitted |
| `external_outcome_unknown_total` | Operations needing reconciliation |
| `late_reply_total` | Replies arriving after execution closed |
| `dlq_replay_total` | Recoveries from DLQ |
| `idempotency_ledger_age` | Monitors retention/cleanup |

A log entry for a duplicate:

~~~json
{
  "event": "idempotency_reused",
  "tenant": "shop-a",
  "commandId": "CMD-1001",
  "lineId": "LINE-02",
  "operationType": "RESERVE_STOCK",
  "executionId": "RUN-02",
  "result": "RESERVED",
  "source": "broker_redelivery"
}
~~~

**Never** use `commandId`, `executionId`, `orderId`, or arbitrary tenants as high-cardinality time-series metric tags. For logs/traces, apply masking, access control, and proper retention; never log payment data, PII, or tokens.

### 20.1. Operational Alerts

- Unusual jump in duplicate hit rate → producer retry loop or broken broker ACK.
- Operations stuck `IN_PROGRESS` too long → wedged lease/recovery.
- Rising lock waits → hot keys, DB contention.
- Rising outbox age → publisher/broker issues.
- Same-key conflicting payloads → producer contract bug or suspicious activity.
- Many `UNKNOWN` outcomes at target systems → prioritize reconciliation.
- `business_effect_committed_total` exceeding unique operation keys → risk of duplicate effects.

### 20.2. Observing a Request–Reply Chain

~~~text
HTTP/Message Gateway
  -> validated command
  -> idempotent handler (new/reused/conflict)
  -> DB commit / existing outcome
  -> reply with current executionId
  -> Aggregator if fan-in
  -> finalizer once per execution
~~~

A duplicate receipt can be valid if the caller genuinely re-sent the request; what must be avoided is a **new business effect** or an **unversioned second final business result**.

## 21. Anti-Patterns to Avoid

| Anti-Pattern | Consequence | Replacement |
| --- | --- | --- |
| Each instance keeps a `HashSet` | Instance B unaware A committed | Shared durable ledger |
| `containsKey` then call external API | Race between two workers | Atomic claim at owner or idempotent backend |
| Redis lock TTL as an exactly-once solution | Lease expires, stale worker still runs | Fencing / idempotent resource |
| Mark processed before commit then drop duplicates | Crash loses the task | Same-transaction commit or recoverable state |
| Mark processed after external commit | Crash duplicates the effect | External idempotency / reconciliation |
| Use `MessageHeaders.ID` as business key | Envelope changes on redelivery | Stable operation ID |
| Use `orderId` alone as key | Valid lines/commands get dropped | Scope by line + command + operation |
| Same key, different quantity returns cached success | Masks serious request conflicts | Compare immutable request fields |
| Retry with a new command ID | Turns retries into new operations | Preserve key across attempts |
| `@Transactional` over an external HTTP call | DB rollback does not roll back HTTP | Target idempotency, saga/reconciliation |
| Relying on Kafka exactly-once for HTTP payments | Wrong consistency boundary | Idempotency at payment owner |
| Deleting ledger too early | DLQ replay creates a new effect | Retention matching replay window |
| Not persisting terminal failures | Redelivery accidentally flips result | Persist outcome per contract |
| Dropping duplicates without replying | Gateway times out | Return stored result or clear status |
| Outbox without idempotent subscribers | Publisher retries duplicate events | Stable event ID / downstream dedup |
| Completed group lets duplicate reply spawn new group | Emits final output twice | Closed execution registry |
| Global system lock for all operations | Poor throughput and latency | Per-key uniqueness / row locks |
| Single-JVM tests used to validate multi-node | Misses distributed races/restarts | Two processes/contexts sharing database |
| Skipping tenant principal verification | Cross-tenant result leak | AuthN/AuthZ before dedup |
| Infinite retries when DB is overloaded | Retry storm | Bounded budget, jitter, monitoring |

## 22. Pre-Production Deployment Checklist

- [ ] Idempotency key accurately identifies **one business operation**, not one delivery.
- [ ] Key is scoped by tenant/principal/command/line/operation type as needed.
- [ ] Identity is issued once and preserved across retries, broker redeliveries, and DLQ replays.
- [ ] Same key with different payloads is detected and rejected.
- [ ] State store is shared across all instances with proper atomic uniqueness/compare-and-set.
- [ ] Side effects and ledger share a consistency boundary, or external APIs have idempotency/reconciliation.
- [ ] Shared metadata selectors are not confused with business transactions.
- [ ] Redis leases handle stale workers/fencing if used for execution rights.
- [ ] `IN_PROGRESS`, `COMPLETED`, `FAILED_FINAL`, and `UNKNOWN` are distinguished.
- [ ] Recovery outcomes for crashes before and after commit are tested.
- [ ] Duplicates return persisted results per contract rather than silently dropping and timing out callers.
- [ ] Transaction proxies/DB isolation/unique constraints are verified on target versions.
- [ ] Outbox/inbox and broker ACK ordering are designed for redeliveries.
- [ ] DLQ replays preserve operation keys, policy/schema versions, and authorization.
- [ ] Ledger retention outlasts the longest delayed delivery/replay window.
- [ ] Aggregators correlate by execution and deduplicate by item, with a late-reply path.
- [ ] Bounded retry budget, error classification, and backoff/jitter exist.
- [ ] Integration tests run with **two instances** on the same database, not just in-memory fakes.
- [ ] Metrics separate deliveries, attempts, dedup hits, and committed effects.
- [ ] Security: no cross-tenant cached result leaks, no sensitive IDs in metric tags.

## 23. Applied Exercise

A ticketing platform runs **5 replicas** of the `TicketReservation` service. Kafka sends `ReserveSeatCommand`:

~~~json
{
  "tenantId": "event-a",
  "commandId": "RSV-2026-55",
  "eventId": "EVT-123",
  "seatId": "A-07",
  "accountId": "ACC-88",
  "executionId": "RUN-1"
}
~~~

Multiple copies of the same command may arrive via retry topics and DLQs. When seat reservation succeeds, the system emits `SeatReserved` for an Aggregator to combine with payment results.

**Requirements:**

1. Design the idempotency key, explaining why `seatId` alone cannot distinguish retries from new operations.
2. Diagram the race between replicas A and B both receiving `RSV-2026-55`. Pick a consistency boundary so only one reservation commits.
3. Write a PostgreSQL schema with a unique operation key and a business-lifecycle constraint preventing a seat from being reserved for two owners (requires a separate constraint/schema, **not just the idempotency key**).
4. Write a `@Transactional` Java service with atomic operation insertion, seat update, and persisted result.
5. Describe handling the same key with a different `accountId` or `seatId`.
6. Simulate A committing the seat then crashing before Kafka offset commit; prove B's redelivery returns the old result.
7. If an external Payment Gateway times out after charging, explain why the local ticket DB alone cannot guarantee charging once. Propose target idempotency/reconciliation.
8. Design an outbox for `SeatReserved` and an idempotent subscriber at the Aggregator.
9. With DLQ replays after 15 days, how should ledger TTL be determined?
10. Design an integration test using **at least two Spring processes/contexts** sharing PostgreSQL, concurrently sending 100 copies of one command.
11. If using Redis leases to reduce contention, add fencing or explain why DB constraints remain necessary.
12. Specify metrics/alerts for duplicates, conflicts, retained operations, lock waits, and replays.

**Hints:** use stable business operation IDs, database unique indexes + transactions on seat resources, outboxes for emitting events, and **seat business constraints independent of dedup**. Distinguish “each command reserves a seat at most once” from “one seat cannot be sold to two people”: these are **two separate invariants**.

## 24. Summary

**Idempotency across multiple instances** does not come from checking an ID in local memory. It requires **stable business operation identification, a shared atomic arbiter, and protection right where the side effect commits**. When multiple replicas, retries, broker redeliveries, outboxes, and DLQ replays coexist, handlers may execute more than once, yet **business mutations must uphold a clear at-most-once contract**.

In Spring Integration, `IdempotentReceiverInterceptor` and `ConcurrentMetadataStore` aid duplicate detection and routing, yet do not automatically turn external APIs or database mutations into a single shared transaction. For same-DB data, prefer **unique operation keys, atomic transactions, and persisted outcomes**; for external services, use **target-side idempotency keys or reconciliation**, plus leases/fencing where appropriate. Combine Router, Filter, Transformer, Gateway, retry/error channels, correlation, Aggregator, inbox/outbox, durable stores, and multi-instance testing to guarantee **retries create no new operations, outcomes do not falsely repeat, and the system remains accurate across crashes and restarts**.

**References:** Gregor Hohpe & Bobby Woolf, *Enterprise Integration Patterns* (Idempotent Receiver, Correlation Identifier, Guaranteed Delivery, Message Store); Spring Integration Reference on Idempotent Receiver, Message Selector, Metadata Stores, Java DSL, Message Channels, Error Handling, and Testing; Spring Framework on Transaction Management and JDBC; PostgreSQL documentation on transactions, `ON CONFLICT`, and row-level locking; Java SE documentation on records and concurrency.
