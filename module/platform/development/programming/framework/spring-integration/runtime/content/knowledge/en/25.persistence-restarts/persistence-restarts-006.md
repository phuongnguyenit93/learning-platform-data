# Duplicate Messages Caused by Post-Side-Effect Crashes in Spring Integration Runtime

## Lesson Objectives

In **SPRING_INTEGRATION_RUNTIME**, a message may travel through an inbound adapter, channel, poller, executor, service activator, and message store, and then produce a side effect in a database, broker, or external service. A **post-side-effect crash** occurs when the application has executed the business effect but dies **before recording completion or acknowledging the message**. Upon restart, the source may redeliver the same request and the handler may apply the effect a second time if idempotency is absent.

This lesson belongs to the **Persistence and Restarts** chapter. The goal is not to eliminate duplicate deliveries at all costs, but to ensure that **multiple deliveries of the same operation lead to only one valid business outcome**.

After this lesson, you will be able to:

- Draw the crash timeline across **side effect – transaction commit – checkpoint – acknowledgment – restart**.
- Distinguish **delivery**, **handler attempt**, and **business side effect** under multi-layer retries.
- Choose the right idempotency key: **eventId/operationId**, without confusing it with message ID or `correlationId`.
- Explain why marking a record processed **too early** drops business work, whereas marking it **too late** can cause duplicates.
- Apply **transactional inbox** for changes in the same DB and **transactional outbox** for emitting events.
- Design protections for payment/HTTP/email side effects using idempotency keys, reconciliation, and unknown-outcome states.
- Understand the limits of **MessageStore**, **MetadataStore**, **IdempotentReceiverInterceptor**, transactions, executors, and pollers.
- Test crash windows, broker redelivery, multi-instance concurrency, and persistent state after restart.

> **Principle:** Brokers may redeliver messages. What matters is that **the business operation is not applied twice**. Spring Integration provides orchestration tools; business idempotency must be designed where the side effect happens.

## 1. Timeline: Payment Succeeded, Message Not Yet Acknowledged

Suppose a consumer receives a `ChargePayment` command with **paymentId=PAY-42**.

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant C as Spring Integration consumer
    participant P as Payment provider
    B->>C: Deliver PAY-42 (delivery 1)
    C->>P: Charge PAY-42
    P-->>C: Charged successfully, response OK
    Note over C: Process crashes before ACK
    B->>C: Redeliver PAY-42 (delivery 2)
    C->>P: Charge PAY-42 again?
    Note over P: Risk of charging twice
~~~

A **side effect** is an observable change outside the handler: charging money, a committed DB write, sending an email, publishing an event, creating a file, or calling an API. Side effects cannot always be rolled back when the JVM dies.

Timeline:

~~~text
T0  Consumer receives message M1.
T1  Handler validates and starts processing.
T2  Payment provider receives and executes the charge.
T3  Application has not committed PROCESSED state or ACKed the source yet.
T4  Pod/process is killed.
T5  Broker redelivers the same paymentId in a new delivery.
T6  Handler runs again; if not idempotent, it may charge a second time.
~~~

The new delivery may be represented by the adapter as a **new Spring Message** with a **different `MessageHeaders.ID`**, even though `paymentId` is the same. Hence a Spring Message's technical ID is **unsuitable as a cross-restart deduplication key**.

**Read the commit concept accurately:** Calling `repository.save()` does not prove the DB committed; it may sit inside an open transaction. Likewise, a client calling `broker.send()` does not prove the broker durably confirmed publication. Crash-window design must anchor on **the exact moment a side effect actually commits** under each system's contract.

## 2. Crash and Consequence Matrix

| Crash Point | Side Effect | Completion Marker / Ack | Risk |
| --- | --- | --- | --- |
| Before side effect | Not yet occurred | Not completed | Can safely reprocess |
| **After effect commits, before marking processed** | **Already occurred** | Not marked | **Duplicate effect on replay** |
| After durable marker saved, before broker ack | Already occurred | Marker exists, ack missing | Delivery may repeat; dedup can block second effect |
| **After ack, before effect commits** | May not have occurred | Ack finished | **Lost business operation on crash** |
| After event publish, before marking outbox sent | Broker may have received it | Outbox still pending | Event publication may repeat |
| After marking outbox sent, before publish | Broker has not received it | Outbox thinks it was sent | **Lost event** |

Two symmetric errors to avoid:

1. **Acking/marking processed too early:** the next run skips business work that never finished.
2. **Acking/marking processed too late:** the next run repeats a side effect that already completed.

For resources **not sharing a transaction**, reordering two lines of code usually only trades **one failure mode for another**, rather than closing the gap. You need a crash-tolerant design pattern.

## 3. Deliveries, Retry Attempts, and Business Operations

| Concept | Unit | Example |
| --- | --- | --- |
| **Delivery** | One broker/poller delivery of a message to a consumer | Kafka record re-read after uncommitted offset; JMS/AMQP redelivery per config |
| **Handler attempt** | One invocation of handler logic | `RequestHandlerRetryAdvice` invokes handler 3 times within one delivery |
| **External call attempt** | One HTTP/DB client request | HTTP client retries a timed-out request |
| **Business operation** | One unique business action | `charge:PAY-42` |

A single business operation can span multiple deliveries and multiple attempts:

~~~text
operationId = charge:PAY-42
delivery #1
  handler attempt #1 -> HTTP timeout (provider may have charged)
  handler attempt #2 -> HTTP timeout
  process crashes before ack
delivery #2
  handler attempt #1 -> calls charge:PAY-42 again
~~~

There may be **3 HTTP calls, 2 deliveries, yet there must be only 1 business charge**. If the provider lacks idempotency or a status-query API, a timeout does not prove the charge did not happen.

### Message Delivery Guarantees Do Not Guarantee Side Effects

- **At-most-once** prioritizes avoiding duplicate deliveries, at the risk of losing messages on crash.
- **At-least-once** prioritizes redelivery when unconfirmed; duplicate deliveries must be expected.
- **Exactly-once** is meaningful only within the scope of specific resources and protocols that support it. Do not assume it extends automatically to HTTP, email, another DB, or every Spring Integration adapter.
- **Idempotent operation** recognizes the same command across multiple attempts and does not apply unintended side effects a second time.

A practical target for many flows is **at-least-once delivery + durable business idempotency**.

## 4. Deduplication Keys: What to Use and What Not to Use

| Field | Meaning | Suitable as Dedup Key? |
| --- | --- | --- |
| **`MessageHeaders.ID`** | Technical identifier of one Spring Message | **No**, may change when adapters construct new messages |
| **`eventId`** | Identifier of a unique source event | Yes, if producer guarantees stability |
| **`paymentId` / `operationId`** | Identifier of a specific business side effect | Yes, scoped by operation type |
| **`orderId`** | Entity identifier | Insufficient if the same order undergoes multiple distinct operations |
| **`correlationId`** | Links messages in the same workflow | Not by default; a workflow may contain many events |
| **`deliveryCount` / `attemptId`** | Attempt or delivery counter | No, they change on retries |
| **`traceId`** | Traces a distributed execution | Cannot replace an idempotency key |

**Good key examples:** `consumer=order-projection-v1, eventId=EV-42`; or `operation=payment-capture, paymentId=PAY-42`.

**Namespacing is critical:** Two independent consumers processing the same `eventId` to build two different projections must not block each other. Deduplication keys should include the **consumer/operation name**. If a key matches while the payload differs, record an **identity conflict** and investigate instead of silently ignoring a potentially altered command.

On retry, keep **`eventId`/`idempotencyKey`/`correlationId`** stable; generate new execution IDs, trace spans, or attempt numbers solely for diagnostics.

## 5. Three Anti-Patterns That Lose or Duplicate Side Effects

### A. Marking DONE Before Executing the Side Effect

~~~java
// Wrong when metadata commits independently from the side effect.
if (metadataStore.putIfAbsent(eventId, "DONE") != null) {
    return; // event already seen
}
paymentProvider.charge(paymentId);
~~~

If a crash occurs **after `putIfAbsent` but before `charge`**, the next delivery sees `DONE` and skips it. The business operation **never happened**, even though the store reports completion.

### B. Marking DONE After External API Returns Success

~~~java
paymentProvider.charge(paymentId);
metadataStore.put(eventId, "DONE");
~~~

If the provider already charged but the JVM crashes before writing `DONE`, the next run calls the provider again. **Risk of double charging.** Moving the write line afterward does not put two systems into a shared transaction.

### C. Using an In-Memory Set/HashMap for Deduplication

~~~java
Set<String> seen = ConcurrentHashMap.newKeySet();
if (seen.add(eventId)) {
    performBusinessEffect();
}
~~~

The set vanishes on restart, and each replica has its own copy; `add` also suffers from the same **claim-first, crash-before-effect** bug. `ConcurrentHashMap` only makes certain operations atomic **within one JVM**, not durable.

**Proper design depends on the resource:** DB side effects share a transaction with an inbox; broker events use an outbox; HTTP/payments use provider idempotency and reconciliation; file/FTP flows need durable checkpoints plus duplicate handling rules.

## 6. Transactional Inbox: Reprocessing Messages Without Updating the DB Twice

Suppose a consumer receives **`OrderConfirmed`**, updates a projection, and writes an outbox event. All three changes — **inbox + projection + outbox** — execute inside a single **PostgreSQL transaction**.

~~~mermaid
flowchart TD
    M["Inbound eventId=EV-42"] --> T["DB transaction"]
    T --> I{"INSERT inbox<br/>consumer + eventId"}
    I -- "Key already committed" --> D["Duplicate: skip update"]
    I -- "New key" --> U["UPDATE / INSERT business data"]
    U --> O["INSERT outbox event"]
    O --> C["COMMIT all three tables"]
    C --> A["ACK per adapter contract"]
    D --> A
~~~

If the process dies **before DB commit**, all changes roll back together. If it dies **after DB commit but before broker ack**, the broker may redeliver, but the inbox key already exists, so the handler does not reapply the changes.

### Sample SQL (PostgreSQL)

~~~sql
CREATE TABLE processed_message (
    consumer_name TEXT NOT NULL,
    event_id TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE order_projection (
    order_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    last_event_id TEXT NOT NULL
);

CREATE TABLE outbox_message (
    outbox_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    published_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

**`processed_message`** does not merely mean "I saw the event"; it means **the transaction processing that event has committed**. Never move the `DONE` write into a separate transaction and call it a transactional inbox.

### Service Activator Example Using JdbcTemplate

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

record OrderConfirmed(String eventId, String orderId) {}

@Component
class OrderProjectionHandler {
    private final JdbcTemplate jdbc;

    OrderProjectionHandler(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @ServiceActivator(inputChannel = "confirmedOrders")
    @Transactional(transactionManager = "transactionManager")
    public void handle(Message<OrderConfirmed> incoming) {
        OrderConfirmed event = incoming.getPayload();
        if (event.eventId() == null || event.eventId().isBlank()
                || event.orderId() == null || event.orderId().isBlank()) {
            throw new IllegalArgumentException("Missing business ID");
        }

        int claimed = jdbc.update("""
                INSERT INTO processed_message(consumer_name, event_id)
                VALUES (?, ?)
                ON CONFLICT (consumer_name, event_id) DO NOTHING
                """,
                "order-projection-v1", event.eventId());

        if (claimed == 0) {
            return; // Already processed and committed in this DB.
        }

        jdbc.update("""
                INSERT INTO order_projection(order_id, status, last_event_id)
                VALUES (?, 'CONFIRMED', ?)
                ON CONFLICT (order_id)
                DO UPDATE SET status = EXCLUDED.status,
                              last_event_id = EXCLUDED.last_event_id
                """,
                event.orderId(), event.eventId());

        jdbc.update("""
                INSERT INTO outbox_message(
                    outbox_id, order_id, event_type, payload_json)
                VALUES (?, ?, 'ORDER_CONFIRMED',
                    jsonb_build_object(
                        'orderId', CAST(? AS TEXT),
                        'sourceEventId', CAST(? AS TEXT)))
                """,
                "order-confirmed:" + event.eventId(),
                event.orderId(),
                event.orderId(),
                event.eventId());
    }
}
~~~

**Conditions for this example to hold:**

1. Uses PostgreSQL for **`ON CONFLICT`** and **`jsonb_build_object`**; other DBs require different syntax.
2. All three SQL statements execute in **the same transaction** with one transaction manager/`DataSource`; **`@Transactional`** must actually be applied via a Spring proxy/advice.
3. If any update throws an exception before commit, **inbox, projection, and outbox** all roll back. Never catch the exception and return success.
4. The **unique constraint** guards two consumers processing the same `eventId` concurrently; never replace it with a separate `SELECT` then `INSERT`.
5. The example does not handle **event versions/out-of-order arrivals**; multiple distinct `eventId`s for the same order require separate ordering/versioning rules.
6. If the same `eventId` arrives with different content, compare fingerprints/investigate conflict; this minimal code does not yet do so.
7. Source ACK happens per adapter behavior and **must not be assumed** to share the DB transaction. Redeliveries can still occur and are handled safely by the inbox.

### Four Crash Scenarios with a Transactional Inbox

~~~text
A. Crash after INSERT inbox but before COMMIT
   -> ROLLBACK inbox + business + outbox.
   -> Next delivery processes it again.

B. Crash after UPDATE business but before COMMIT
   -> ROLLBACK both business change and inbox.
   -> Next delivery processes it again, no lost work.

C. Crash after COMMIT but before source ACK
   -> Inbox marker and business/outbox are committed.
   -> Redelivery is recognized; effect is not applied a second time.

D. Crash after ACK in this topology
   -> DB already committed earlier.
   -> No replay needed to finish the DB part.
~~~

**Important:** Never use a test transaction that always rolls back at the end of every test and conclude state survives restarts. Verify with real commits, and spawn a fresh process when proving durability.

## 7. Transactional Outbox: Publish Side Effects Can Still Repeat

For events that must be sent to a broker **after DB commit**, an outbox closes the gap between DB updates and publishing. The handler **writes the event to the outbox inside the transaction**; a separate publisher reads pending events and publishes them.

~~~mermaid
sequenceDiagram
    participant D as Business DB
    participant W as Outbox publisher
    participant B as Broker
    participant C as Consumer
    W->>D: Read pending EV-42
    D-->>W: Event EV-42
    W->>B: Publish EV-42
    B-->>W: Ack accepted
    Note over W: Crash before marking published
    W->>D: After restart: EV-42 still pending
    W->>B: Publish EV-42 again
    B->>C: May receive same eventId twice
    Note over C: Idempotent consumer
~~~

**Never mark published before sending** just to avoid duplicates: crashing before publishing **loses the event**. The publisher should:

- Use safe claiming/leasing or DB locking when multiple publishers run concurrently; for example **`FOR UPDATE SKIP LOCKED`** when targeting PostgreSQL.
- Send the exact same **stable `outbox_id`/`eventId`** across all publish attempts.
- Wait for broker confirmation per the producer contract before updating status to published.
- Use bounded retries/backoff, backlog alerts, and safe post-restart replay.
- Rely on idempotent downstream consumers because events may be published more than once.

An **`afterCommit` callback** can wake up the publisher sooner, but it does not replace the outbox table: the app can still crash between DB commit and callback execution.

## 8. External Side Effects: Payments, Emails, and HTTP

When the side effect lives in an HTTP API or payment provider, a local DB transaction is not atomic with the external outcome:

~~~text
DB: save CHARGE_REQUESTED
HTTP: provider accepts and charges successfully
PROCESS: crashes before saving CONFIRMED
RESTART: sees only CHARGE_REQUESTED
~~~

You cannot tell from the internal DB alone whether the provider charged. You need a **provider-enforced idempotency key** and/or a **status lookup API**.

~~~java
record ChargeCommand(String paymentId, long amountMinor, String currency) {}

// Pseudocode: actual payment SDK signatures may vary.
String idempotencyKey = "charge:" + command.paymentId();
ChargeResult result = paymentClient.charge(
        command.amountMinor(),
        command.currency(),
        idempotencyKey);
~~~

Mandatory questions before enabling automatic retries:

1. **How long** does the provider retain the idempotency key, and does it require payloads to match?
2. Is the key scoped to the **charge operation** or only to a specific request/endpoint?
3. Can a timeout occur **after provider commit**? Is there a query API by `paymentId`/reference?
4. Once the key expires, could an old replayed message create a brand-new charge?
5. If the provider does not support idempotency, is there a reconciliation/human review step before retrying?

### Unknown-Outcome State

~~~mermaid
stateDiagram-v2
    [*] --> RECEIVED
    RECEIVED --> REQUESTED: Record command + key
    REQUESTED --> CONFIRMED: Provider confirms success
    REQUESTED --> FAILED: Provider confirms definite failure
    REQUESTED --> UNKNOWN: Timeout / crash / lost response
    UNKNOWN --> RECONCILING: Query provider
    RECONCILING --> CONFIRMED: Already charged
    RECONCILING --> FAILED: Proven not charged
    RECONCILING --> REQUESTED: Safe to retry per contract
~~~

Persist **`paymentId`/`idempotencyKey`/`provider reference`/`correlationId`/`attempt`/`status`** in a durable store. **`UNKNOWN_OUTCOME` does not equal `FAILED`**. Immediately re-charging after a timeout when the outcome is unknown risks double charging.

**Email has a similar gap:** SMTP may accept the email before the process crashes prior to marking it sent; replay can send it again. If the email platform lacks idempotency or deduplication, accept the possibility of duplicates and design the user experience/effects to minimize harm.

## 9. IdempotentReceiverInterceptor and MetadataStore in Spring Integration

Spring Integration provides **`IdempotentReceiverInterceptor`** to implement the **Idempotent Receiver** pattern at an endpoint. It uses a **`MessageSelector`**; a common setup uses **`MetadataStoreSelector`** backed by a **`ConcurrentMetadataStore`**.

~~~text
Inbound message
  -> IdempotentReceiverInterceptor
      -> MetadataStoreSelector(eventId)
          -> accepted / duplicate
      -> MessageHandler
~~~

The critical distinction is between **filtering duplicates** and **guaranteeing the side effect actually committed**.

| Mechanism | When Is It Useful? | Limitations |
| --- | --- | --- |
| **`IdempotentReceiverInterceptor`** | Blocks or marks redelivered messages before the handler | Does not make the side effect atomic with the marker |
| **`MetadataStoreSelector`** | Key generation/lookup rules and metadata comparison | Key-write policy must align with transactions |
| **`ConcurrentMetadataStore`** | Atomic put-if-absent/compare-and-set per implementation | Atomicity on keys does not mean atomicity with HTTP/payments |
| **`SimpleMetadataStore`** | Demos, single JVM, minimal durability needs | Loses markers on restart |
| **Persistent `MetadataStore`** | Preserves recognition state across restarts | Crash window can still exist between metadata write and side effect |

Per the interceptor contract, if neither a **discard channel** nor **throw-on-rejection** is configured, a duplicate may be **marked with header `duplicateMessage=true`** and still forwarded to the handler; the handler must decide what to do. Never assume all duplicates are automatically dropped.

### The "Claim-First" Trap with Persistent Metadata

Suppose the selector writes the key into the store **before the handler executes**. If the key commits and the JVM dies before the side effect, replay may be treated as a duplicate and skipped. That causes **lost business work**; swapping **`SimpleMetadataStore`** for **`JdbcMetadataStore`** does not fix it if the checkpoint remains decoupled from the effect.

To handle this safely:

- If the side effect lives in **the same DB**, use transactions/unique constraints binding **inbox and effect** as shown in Section 6.
- If the side effect lives in **another system**, use a **`REQUESTED/UNKNOWN/CONFIRMED`** state machine, provider idempotency, and reconciliation.
- If metadata stores **file/FTP source checkpoints**, evaluate **flushing**, durability, and "seen" vs. "fully processed."

**`PropertiesPersistingMetadataStore`**, for instance, persists metadata to a file; actual durability depends on its flush behavior. Never assume every `put` is safe against a **hard crash** without verifying the configuration.

## 10. MessageStore, Channels, and Thread/Transaction Boundaries

Spring Integration provides **`MessageStore`** to hold messages for EIPs such as `QueueChannel`, aggregators, and delayers. Persistent stores reduce the risk of losing **durably persisted messages**, yet they cannot tell whether an out-of-DB HTTP call already produced its side effect.

### Thread Boundaries Can Shift Ack Timing

~~~mermaid
flowchart TD
    B["Inbound adapter"] --> T["Source / transaction A"]
    T --> E["ExecutorChannel"]
    E --> H["Handoff succeeds"]
    H --> A["Source may complete per contract"]
    E -. "Different worker thread" .-> W["Handler / transaction B"]
    W --> D[("Business DB")]
    W --> F["ErrorMessage on async error"]
~~~

**Spring transactions typically bind to threads.** Crossing an **`ExecutorChannel`** or `PollableChannel` to another consumer means transaction A does not automatically propagate to thread B. If the producer is considered successful immediately upon handoff, a crash before the worker commits can leave business work unfinished; recovery depends on queue durability and ack semantics.

| Component | Questions to Verify for Crash/Restart |
| --- | --- |
| **`DirectChannel`** | Does the handler share the producer's thread/transaction? Do exceptions propagate back to roll back? |
| **`ExecutorChannel`** | Are enqueued but unexecuted tasks durably stored? When does the producer's transaction/ack end? |
| **`QueueChannel` + `PollingConsumer`** | Is the queue backing store persistent? Do receive/remove run inside an appropriate transaction? |
| **JMS/AMQP/Kafka inbound** | Where are ack/nack/offsets and redelivery decided, and by which container and transaction? |
| **`RequestHandlerRetryAdvice`** | Can one delivery invoke the handler multiple times; does it stack with client/broker retries? |
| **`MessageGroupStore`** | Does aggregator completion/release survive restarts, and can it emit duplicate outputs? |
| **`errorChannel`** | Do async errors reach the error consumer? Are `failedMessage`/`correlationId` preserved to identify failed business work? |

**You cannot conclude a message will be redelivered just because the handler threw an exception.** If the error happens after an async handoff, the source already acked, or a recovery callback consumed the exception, the outcome differs. Always test against the **actual adapter, version, and config**.

### A Persistent MessageStore Is Not a Global Transaction

Stores like **`JdbcMessageStore`, `RedisMessageStore`, or `MongoDbMessageStore`** can preserve messages/groups across restarts provided durability and serializers are compatible. However:

- Not all **payloads/headers** are serializable. Object-valued **`replyChannel`/`errorChannel`** headers referencing in-JVM objects may be lost or need mapping to channel names.
- Whether a message removed from a queue/store is recovered after a crash depends on transaction and **`receive/remove`** semantics.
- A released aggregator may still have metadata while downstream side effects may or may not have occurred; business idempotency is still required.
- When multiple instances share a store, coordination/locking and duplicate handling are needed; persistence alone does not turn outputs into exactly-once.

To prevent lost business work, identify the **source of truth** at each stage: broker/queue holds delivery state, DB holds effect/inbox, outbox holds unpublished events, and provider holds payment state.

## 11. Retries, Correlation, and Error Handling Across a Crash

Each retry may create a new technical message or tracing span:

~~~text
delivery #1: springMessageId=M1, eventId=EV-42, correlationId=checkout-O-42
    handler attempt #1: timeout
    handler attempt #2: timeout
JVM crashes before ACK
delivery #2: springMessageId=M2, eventId=EV-42, correlationId=checkout-O-42
~~~

Every attempt must preserve:

- **`eventId`/`operationId`/`idempotencyKey`** unchanged, to prevent duplicate side effects.
- **`correlationId`** to link workflow events, outcomes, retries, and errors.
- **`attempt`/`delivery count`** separately for observability, never as a deduplication key.
- **`source coordinates`** such as topic/partition/offset when supplied by the adapter; never treat them as cross-source business identity.
- **`failedMessage` or `originalMessage`** inside `ErrorMessage` when present, to trace back to the original `eventId`.

### Do Not Hot-Retry Every Error

| Error Type | Example | Right Decision |
| --- | --- | --- |
| Transient error before effect | Temporary DB disconnect, HTTP 503 under idempotency contract | Bounded retry + backoff |
| Malformed payload | Invalid JSON, missing `eventId` | Quarantine/DLQ, never loop infinitely |
| Committed duplicate | Inbox key exists and payload matches | Skip side effect, ack delivery per contract |
| Unknown external outcome | Provider timeout when charge may have succeeded | Reconcile before concluding FAILED or retrying |
| Outbox publish failure | Broker has not confirmed | Keep pending, retry publish; downstream idempotent |
| Identity conflict | Same `eventId` with different payload | Alert/quarantine for investigation |

Do not independently configure retries across **HTTP client + handler + broker + scheduler** and accidentally multiply call counts exponentially. An end-to-end retry policy needs a clear **retry owner**, max attempts, deadline, backoff, recovery, and stable idempotency keys.

### Error Flows Do Not Automatically Decide ACK

`ErrorMessage` may carry `MessagingException`/`failedMessage` depending on the error origin. It only reflects an error published to the error channel. **An error handler logging and returning normally** may cause some topologies to treat processing as successful. For redelivery, obey adapter semantics; for quarantine, persist to a **durable `FailureJournal`/DLQ** before confirming resolution.

## 12. Testing Crash Windows: Kill at the Exact Moment

A test that merely calls the handler twice in the same process **cannot verify post-crash behavior**. You must inject faults when the business DB has committed while the source has not yet acked, and then restart the consumer against **the same data stores**.

### Test Matrix

| Case | Crash/Failure Point | Expected Result |
| --- | --- | --- |
| A | Before side effect | Replay executes cleanly; zero lost work |
| B | After INSERT inbox, before DB commit | Both inbox and DB work roll back; replay succeeds |
| C | After UPDATE projection, before commit | No half-committed data exists |
| D | **After DB commit, before broker ack** | Broker may redeliver; inbox blocks second effect |
| E | After outbox publish, before marking published | Publisher may republish; downstream skips duplicate side effect |
| F | After provider charge, before saving CONFIRMED | Retry/reconciliation uses same `paymentId`; zero double charge |
| G | After independent metadata write, before side effect | Business operation is not falsely treated as DONE |
| H | Two consumers with same `eventId` | Unique constraint/atomic claim blocks two effective commits |
| I | Persistent `QueueChannel` with pending message, then restart | Message readable per store contract |
| J | Aggregator ready to release, crash before/during output | Group state and downstream idempotency verified |
| K | `ExecutorChannel` handoff then worker failure | Actual error flow/transaction/ack verified |
| L | Idempotency key retention expires, old event replayed | Policy blocks or reconciles late replay |

### Integration Test Procedure with Real Restarts

1. Provision a **broker/test queue** and **PostgreSQL** whose data persists when the worker is killed.
2. Send **`eventId=EV-42`** and configure the consumer with an observable point after commit but before adapter ack.
3. At that checkpoint, **kill the process/container** — do not use graceful shutdown (graceful shutdown may finish in-flight messages).
4. Start a new worker connected to **the same broker and DB**.
5. Verify the source may redeliver, yet **`processed_message`** still has only one row and **`outbox`/`projection`** reflect only one logical effect.
6. Repeat fault injection at the outbox publish and payment API steps; observe recovery and idempotency.

**Testing limitation:** Inserting a checkpoint genuinely **between commit and ack** depends on the adapter. Simply putting `Thread.sleep()` in a handler and restarting the app may miss the exact crash window. Use a test seam/fault hook or a controlled consumer process, and document clearly what was proven.

### Assert on Outcomes, Not Just Handler Invocation Counts

~~~text
processed_message:
    1 row for (order-projection-v1, EV-42)
order_projection:
    expected final business state
outbox_message:
    1 logical outbox_id for EV-42
broker:
    may deliver EV-42 multiple times per at-least-once contract
provider:
    1 payment per paymentId if provider supports idempotency
logs/traces:
    same eventId/correlationId across restarts
~~~

Never use "handler was called exactly once" as the sole metric: **the handler may run twice, while the effect must happen once**.

## 13. Example Test: Duplicate Delivery with Two Spring Messages of Different IDs

The snippet below illustrates test logic against the transactional handler from Section 6. It must run in a Spring test context with a real **`JdbcTemplate`/transaction manager and PostgreSQL**, since mocked-repository tests cannot prove transaction durability.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class InboxReplayTest {
    @Autowired OrderProjectionHandler handler;
    @Autowired JdbcTemplate jdbc;

    @Test
    void redeliveryDoesNotApplyProjectionTwice() {
        OrderConfirmed event = new OrderConfirmed("EV-42", "O-42");

        Message<OrderConfirmed> delivery1 =
                MessageBuilder.withPayload(event).build();
        Message<OrderConfirmed> delivery2 =
                MessageBuilder.withPayload(event).build();

        handler.handle(delivery1);
        handler.handle(delivery2);

        Integer inboxCount = jdbc.queryForObject("""
                SELECT count(*) FROM processed_message
                 WHERE consumer_name='order-projection-v1'
                   AND event_id='EV-42'
                """, Integer.class);

        Integer outboxCount = jdbc.queryForObject("""
                SELECT count(*) FROM outbox_message
                 WHERE outbox_id='order-confirmed:EV-42'
                """, Integer.class);

        assertEquals(1, inboxCount);
        assertEquals(1, outboxCount);
    }
}
~~~

**Test fragment, not standalone:** Requires `@SpringBootTest`/`@SpringJUnitConfig`, fixture schemas, transaction proxies, and cleanup between tests. If the test method runs inside a test-framework transaction that rolls back at the end, it does not prove state committed across restarts. For crash tests, commit for real and use another process.

### Testing Two Concurrent Consumers

Two threads/replicas receive `eventId=EV-42` simultaneously:

- Both may reach `INSERT processed_message` at nearly the same moment.
- **`PRIMARY KEY (consumer_name, event_id)`** prevents two committed rows with the same key.
- One transaction may wait for the other to commit/roll back. If the first transaction rolls back, the second can proceed and process it.
- Once both finish, there is only **one logical projection update and one outbox event** for that key.
- If they update the same order from **two different `eventId`s**, that is a separate ordering/versioning problem, not solved by `eventId` deduplication.

A `ConcurrentHashMap` test in a single JVM does not prove behavior across two replicas sharing a DB.

## 14. Persistence and Restarts: Multiple Sources of Truth Must Reconcile

~~~mermaid
flowchart LR
    Q[("Broker / ChannelMessageStore<br/>delivery state")] --> H["Consumer"]
    H --> I[("Business DB / Inbox<br/>applied state")]
    I --> O[("Outbox / FailureJournal<br/>publication state")]
    O --> E["External broker / API"]
~~~

Layers can **temporarily disagree** after a crash:

- The broker knows a message was not acked and wants to redeliver.
- The business DB knows the effect already committed.
- The outbox knows an event has not been published or marked published.
- The provider knows payment succeeded, while the internal DB still records `UNKNOWN`.

A sound recovery workflow typically follows:

1. Broker redelivers unacknowledged messages.
2. Consumer checks the **inbox** and applies business logic if not yet committed.
3. Outbox publisher scans **pending** rows and republishes under control.
4. Reconciliation worker queries **`UNKNOWN_OUTCOME`** at the provider.
5. Monitoring flags stale pending items, identity conflicts, and unreconcilable side effects.

### Caution When Keeping Messages in Persistent Stores

Spring Integration supports JDBC, Redis, and MongoDB message stores depending on the component. For a persistent `MessageStore`:

- Check whether payloads and headers **can serialize/deserialize across upgrades**.
- Object-valued `replyChannel`/`errorChannel` headers may only make sense in the old JVM; consider **channel names** and mapping.
- Check aggregator group state, release/expiry, post-restart timers, and late-message policies.
- Two instances sharing a store still require locking/concurrency control and business idempotency.
- Whether a message fetched from the store before a crash is recovered depends on **transactions and `receive/remove` semantics**.

**Persistent state does not create exactly-once by itself.** It only preserves part of committed truth; you still must define when markers are written and whether they are atomic with the effect.

## 15. Observing and Diagnosing Post-Crash Duplicates

An at-least-once system expects occasional duplicate deliveries as normal. What warrants alerting is **duplicate business effects**, not every replay.

| Metric / Event | Operational Question |
| --- | --- |
| **`delivery attempts`** | How often is the broker/poller redelivering messages? |
| **`handler retry attempts`** | Are `RetryAdvice` or client retries amplifying call counts? |
| **`inbox duplicate count`** | How many messages were safely blocked by durable keys? |
| **`business duplicate effect count`** | Were any updates/charges/sends actually duplicated? |
| **`outbox pending age`** | How long have committed events waited before publishing? |
| **`unknown payment count`** | How many side effects need reconciliation? |
| **`correlation missing count`** | How many errors cannot be traced back to an `eventId`/`operationId`? |
| **`queue depth / consumer lag`** | Is backlog growing due to crashes, retry storms, or downstream overload? |
| **`identity conflict count`** | Same `eventId` with differing content? |

Example application-defined log:

~~~text
flow=orderPersistence endpoint=orderProjectionHandler
eventId=EV-42 orderId=O-42 correlationId=checkout-O-42
deliveryAttempt=2 handlerAttempt=1
inboxResult=DUPLICATE businessEffect=SKIPPED
source=kafka partition=3 offset=10852
decision=ACK_AFTER_VERIFIED_COMMIT
~~~

**Never log sensitive payment details** or raw secret payloads. Keep **`eventId`, `paymentId`** in controlled traces/logs; avoid using per-request IDs as high-cardinality metric tags.

### Checklist When a Side Effect Occurs Twice

1. Were there two distinct `eventId`s, or was one `eventId` redelivered?
2. Where did the side effect commit prior to ack?
3. Did the idempotency key change across a restart, transformer, or retry?
4. Was the `DONE` marker committed **before, after, or inside the same transaction** as the business effect?
5. Does the provider actually enforce the idempotency key, and is it still within retention?
6. Are nested retries configured across HTTP client, handler, broker, and scheduled replay?
7. Did `ExecutorChannel` cause the source to confirm handoff before the worker finished?
8. Did the outbox publisher replay after a crash, and is the downstream consumer deduplicating?
9. Was the store/metadata reset during a deploy, namespace change, or schema change?
10. Was `UNKNOWN_OUTCOME` mistakenly treated as `FAILED` and automatically re-charged?

## 16. Comprehensive Lab Exercise

**Problem:** A flow receives `OrderConfirmed` from a broker, updates PostgreSQL, emits `OrderReady`, and calls a payment provider. The application runs two replicas. The broker delivers at-least-once; containers occasionally die right after DB commit or payment charge.

**Requirements:** Never create two projection/outbox events for the same `eventId`; never charge twice for the same `paymentId` when the provider supports idempotency; the outbox must recover after crashes; `UNKNOWN` states must be reconciled; correlation must remain traceable across restarts.

Design guidance:

1. **Inbound:** Validate `eventId`, `correlationId`, `orderId`, and `paymentId`, and preserve them across every transformer/retry.
2. **Business DB:** Write inbox keyed by `consumer + eventId`, update order, and write outbox in **the same transaction**; enforce unique constraints.
3. **Outbox publisher:** Poll pending rows, claim safely, publish with a fixed `eventId`, mark published after confirmation; downstream consumers must be idempotent.
4. **Payment:** Use `paymentId`/idempotency key, `REQUESTED/UNKNOWN/CONFIRMED` states, and provider lookup after timeouts.
5. **Error flow:** Never swallow exceptions and fake-ack; persist to `FailureJournal`/DLQ on unrecoverable failures with business correlation.
6. **Restart:** DB, outbox, and provider state are the sources of truth; do not rely on RAM or `afterCommit` callbacks alone.
7. **Concurrency:** Test two replicas receiving the same `eventId` and crashing after commit before ack.
8. **Observability:** Record `eventId`, `operationId`, delivery/attempt counts, commit points, acks, outbox publications, and reconciliation status.

### Self-Check Questions

**1.** DB commit succeeded, the app died before broker ack, and the broker redelivered. Is that a broker bug?

**No.** That is valid at-least-once behavior when ack did not finish. The inbox/idempotency layer must block duplicate effects.

**2.** Is using a persistent `MetadataStore` to write `DONE` before an HTTP call safe enough?

**No.** Crashing after writing `DONE` but before the effect causes replays to skip it; the side effect never happens.

**3.** Does `@Transactional` wrapping a DB write and an HTTP payment call roll back the payment if the DB rolls back?

**Not with standard HTTP.** You need provider idempotency, status queries, and reconciliation.

**4.** An outbox event was published, but the app died before marking it published; should you delete the outbox row to prevent duplicates?

**No.** Doing so can drop events in cases where publication did not actually succeed. Accept duplicate publications and deduplicate downstream.

**5.** Can `correlationId` serve as the deduplication key for every event on the same order?

**Not by default.** A workflow/order has multiple valid operations; deduplication must identify **a specific event or specific business operation**.

## 17. Production Checklist

- Mapped all crash windows across **receive -> effect -> commit -> ack -> restart**?
- Separated **delivery count**, **handler attempts**, and **business effects**?
- Deduplication keys stable across redeliveries and namespaced by consumer/operation?
- **Inbox + DB effect + outbox** commit/roll back in **the same real transaction**?
- Unique constraints/atomic claims protecting concurrent consumers?
- Avoided acking sources too early or swallowing exceptions into success?
- Outbox recovers publishing after crashes, and downstream is idempotent?
- External APIs/payments have target-enforced keys and an **`UNKNOWN_OUTCOME` reconciliation** workflow?
- Verified transactions/acks per adapter and **`ExecutorChannel` / `QueueChannel`** boundaries?
- `MetadataStore`/`MessageStore` survive restarts with compatible serializers/headers?
- Dedup retention exceeds broker redelivery and delayed replay windows?
- Bounded retries without accidental multi-layer stacking, plus explicit recovery/DLQ?
- Failed/original messages, `eventId`, `correlationId`, and `idempotencyKey` preserved in error paths?
- Tested **hard crashes after DB commit before ack**, after payment effects, and after outbox publish?
- Measured **safe duplicate deliveries** separately from **duplicate business effects**?

## Conclusion

**Duplicate messages caused by post-side-effect crashes** are one of the core risks when a message flow coordinates multiple resources with different commit/ack points. Spring Integration orchestrates channels, endpoints, pollers, executors, retries, error flows, and persistence, yet **it does not automatically guarantee an HTTP/DB/broker side effect happens only once**.

The durable strategy is to **expect redeliveries and block duplicates at the business boundary**: transactional inbox for DB updates, transactional outbox for events to publish, and idempotency keys plus reconciliation for external side effects. Combined with **persistent state, correlation, bounded retries, and hard-crash testing at exact windows**, systems can recover from restarts without duplicating or losing business outcomes.

## References

- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html)
- [Spring Integration Reference — Metadata Store](https://docs.spring.io/spring-integration/reference/meta-data-store.html)
- [Spring Integration Reference — Idempotent Receiver Enterprise Integration Pattern](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html)
- [Spring Integration Reference — Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html)
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
- [Spring Integration Reference — Polling Consumer](https://docs.spring.io/spring-integration/reference/endpoint/polling-consumer.html)
