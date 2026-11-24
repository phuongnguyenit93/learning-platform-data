# Restarting Flows and Verifying Zero Loss of Essential State

## 1. Problem Statement: A Restartable Flow Does Not Guarantee Proper Recovery

A Spring Boot **integration flow** typically links several steps: HTTP/JMS intake, reading from databases or files, transforming payloads, calling HTTP clients, updating caches, writing databases, and publishing messages to brokers. In Spring Integration, those steps span diverse channels, endpoints, pollers, aggregators, resequencers, and adapters.

When a Spring Boot process stops abruptly, a container is replaced, a broker connection drops, or a flow stops and restarts, state held purely in memory can vanish. An application **booting up cleanly** proves only that its beans and endpoints can run again; it does not prove work accepted prior to shutdown finished properly.

Example: a flow receives **OrderAccepted** events, waits for stock confirmation results, and emits **OrderReady**. Right before a restart, an aggregation group holds two of three events. If that group exists only in memory, the restarted application may have no way to complete the order. If the broker replays all inputs, a new group may form—yet also risks emitting **OrderReady** twice.

This lesson answers three questions:

1. **Which state must survive restarts?** Not every variable or in-memory message needs durable storage.
2. **At which boundaries can a message be lost or duplicated?** Examine transactions, acknowledgments, checkpoints, and external systems.
3. **How do you verify zero loss?** Reconcile business messages, persisted state, and recovery behavior across deliberate fault-injection points.

This is part of the **Flow Errors and State** topic in the **SPRING_BOOT_INTEGRATION** module: managing configuration, data contracts, transactions, errors, deduplication, testing, and observability across real integrations involving databases, HTTP, caches, brokers, and Spring Integration adapters.

## 2. Defining "Zero Loss of Essential State" Precisely

A system does not need to keep every Java object, thread, or RAM queue across restarts. It must retain **enough information to recover accurate business outcomes**.

For every event **durably accepted** by the system, recovery typically requires:

- Successfully processed events have recorded outcomes or processing markers to prevent duplicate side effects.
- Unfinished events remain in a **durable source** or durable intermediate queue/state to resume from.
- Unprocessable events move to an investigable failure state, such as a **dead-letter queue (DLQ)** or error table, rather than vanishing silently.
- Committed data, event-publishing intents, and external side effects are never misinterpreted when the flow resumes.
- Correlation IDs, required ordering, progress cursors, and aggregation groups are persisted whenever omitting them makes accurate reconstruction impossible.

A useful invariant for reconciliation:

> For every durably accepted **`eventId`**, the system must account for its completed outcome, pending processing state, or recoverable error location; no `eventId` vanishes unaccounted for.

This targets **zero lost business work**, which does not mean brokers never redeliver. In practice, coordinating multiple resources relies on **at-least-once delivery** paired with **idempotent processing**.

### Classifying State

| State Category | Examples | When Must It Be Durable? |
| --- | --- | --- |
| **Business state** | Paid order, reserved stock, payment transaction reference. | Almost always durable; must honor primary datastore integrity and transactions. |
| **Pending messages** | Received events not yet processed, internal queue messages. | When no upstream source guarantees replay after restart, or upstream was already acknowledged. |
| **Read progress / checkpoints** | Offsets, cursors, processed filenames, last poll timestamps, watermarks. | When re-reading from scratch is too costly or causes errors; must align with outcome commits. |
| **Correlation state** | Partial aggregator groups, sequence/correlation keys, active timeouts. | When groups can span restarts and cannot be safely rebuilt from source. |
| **Processing / idempotency markers** | Applied `eventId`, `paymentId`, or `operationId` keys. | Whenever redeliveries can occur and repeated processing mutates business state. |
| **Event-publish intent** | Unpublished outbox records. | Whenever database commits precede broker publishing. |
| **Error state** | Failure envelopes, retry counts, failure reasons, DLQ entries. | When post-restart retries, data fixes, or investigations are needed. |
| **Reconstructible transient state** | Recomputable caches, local variables, TCP sockets, active threads. | Usually disposable, provided reconstruction and consistency expectations are clear. |

**The deciding factor** is not "did we add a message store?" but **can we prove accepted work never vanishes if the system halts at any step?**

## 3. How Spring Integration Components Hold State

### 3.1. Channels and the Difference Between Dispatch, Queueing, and Durability

| Component / Usage | Key Restart Behavior |
| --- | --- |
| **DirectChannel** | Passes messages synchronously to subscribers on the calling thread; creates no durable queue. Safety depends on upstream sources and caller transactions. |
| **ExecutorChannel** | Offloads execution to an executor; tasks sitting in memory or executor queues vanish if the process dies. Thread switches can also sever caller transaction contexts. |
| **QueueChannel** with default in-memory store | Unconsumed messages can be lost when the JVM dies. |
| **QueueChannel** with a proper persistent message store | Stored messages can be retrieved after restart; still evaluate removal timing relative to downstream commits. |
| **PublishSubscribeChannel** | Broadcasts to subscribers; provides no built-in durability or replay for all subscribers. Under async dispatch, analyze each branch and ack rule separately. |
| **JMS/AMQP/Kafka adapters** | Can leverage durable brokers/logs, subject to delivery modes, acks/offsets, retention, consumer groups, and retry policies. |

Putting a **QueueChannel** between two handlers only buffers in-process by default. With an in-memory store, hard shutdowns drop buffered messages. Using **`JdbcChannelMessageStore`** persists queues in a database across restarts—provided schemas, serialization, and message retrieval are configured cleanly.

Persisting a queue **does not automatically** make the entire flow atomic. If a message is dequeued and its delete transaction commits **before** the handler persists results, crashing in between loses the work. Align poller/store transaction boundaries with business updates, or design replay with deduplication.

### 3.2. Aggregators, Resequencers, and Time-Delayed Work

**Aggregators** store messages arriving in a group, **correlation keys**, release conditions, timeouts, and group status. **Resequencers** hold out-of-order parts to restore sequence. With an in-memory message group store, incomplete groups disappear on restart.

Spring Integration offers **`MessageStore`** and **`MessageGroupStore`**, with JDBC implementations like **`JdbcMessageStore`** to persist group state in databases. Verify:

- Do group IDs and correlation keys stay stable across deployments and serialization/deserialization?
- Does the store retain payloads, headers, sequence numbers, and metadata needed to release?
- Do **release**, **expire**, **discard**, and timeout partial-result rules risk dropping needed data?
- Is marking/removing completed groups coordinated with durable downstream acceptance?
- Do parallel instances share the same store, proper locks, and ownership rules so a group cannot release twice or race?

Persisting groups alone fails if an aggregator deletes a group after emitting an output that never reached a durable destination. Conversely, if output succeeds before the group is marked complete, restarts may re-emit it. Analyze both **failure windows**.

Delayed tasks, in-process schedulers, and retries sleeping in RAM need scrutiny too. An in-JVM timer is not a durable job queue; when business deadlines must survive restarts, persist **`dueAt`**, business IDs, and processing state in durable storage for schedulers to query.

### 3.3. Metadata Stores and Inbound Adapter Checkpoints

File, remote-file, and polling adapters often use a **`MetadataStore`** to track seen keys, modification timestamps, cursors, or filters preventing duplicate reads. An in-memory **`SimpleMetadataStore`** wipes on restart. Depending on the task, use **`JdbcMetadataStore`** or another durable metadata store.

However, **a saved checkpoint does not prove processing finished**. Example:

1. File adapter records "file A seen".
2. Handler has not yet committed file A's business data.
3. JVM crashes.
4. On restart, the filter skips file A because metadata claims it was read.

That loses work despite durable metadata. Tie checkpoints to durable acceptance or completion, or deliberately allow re-reads backed by business-key deduplication. For files, use **`incoming / processing / completed / failed`** directories, stable filenames, manifests, or inbox tables, while checking for partially written files.

### 3.4. Retries and Error Channels

**`RequestHandlerRetryAdvice`** or handler-level retries help survive brief glitches without restarts. However, attempt counters and backoff timers sit in memory; unless persisted separately, they do not survive process crashes.

**`errorChannel`** routes errors inside Spring Integration; having an error flow does not mean errors are durably stored. To reprocess after restarts, forward failures to a **DLQ**, error table, or equivalent durable store. Exception rules matter too: if a handler swallows an error and returns normally, upstream may acknowledge the message despite business failure.

## 4. Finding "Data-Loss Windows" via Commit and Acknowledge Boundaries

The diagram below shows a flow consuming from a broker and updating a database:

~~~mermaid
sequenceDiagram
    participant B as Durable broker
    participant A as Inbound adapter
    participant H as Integration handler
    participant D as Database
    B->>A: Deliver eventId=E-101
    A->>H: Message
    H->>D: BEGIN, business changes + E-101 marker
    D-->>H: COMMIT
    H-->>A: Processing succeeded
    A->>B: ACK/COMMIT receipt
    Note over A,B: Can crash after DB commit but before ACK
~~~

If the database commits before the adapter confirms with the source, the broker can redeliver **E-101**. Plan for this rather than treating it as an anomaly. When the **E-101** processed marker and business updates commit **in the same database transaction**, redelivery skips cleanly.

Far more dangerous is **ACKing or checkpointing the source before durable outcome persistence**. Crashes after ACK yet before database commit can prevent upstream redelivery, losing work.

| Crash Timing | Can Source Still Redeliver? | Business Outcome? | Recovery Design |
| --- | --- | --- | --- |
| Before source ack and before DB commit | Usually yes, if source is durable and ACK/offsets are configured properly. | Not committed. | Allow retry; input remains at source. |
| After DB commit, before ACK | May redeliver. | Committed. | Record idempotency marker in same TX; redelivery does not re-apply. |
| After ACK, before DB commit | Possibly **no**. | Uncertain. | Avoid this order; write payload to durable inbox first or move ACK boundary. |
| After DB commit, before outbound publish | Source may be acked. | Committed locally, downstream uninformed. | Transactional outbox for outbound event intent. |
| After outbound accepted by broker, before marking sent | Outbound may replay. | Downstream may see duplicates. | Stable `eventId` and downstream deduplication/idempotency. |

Whether the source can redeliver depends on real broker settings, retention, consumer offsets, retry policies, and commit state; never assume blindly from adapter names.

### Spring Transactions Do Not Span All Endpoints Automatically

A service `@Transactional` governs only resources managed by that transaction manager. **`DirectChannel`** dispatches synchronously and can carry the same thread's transaction context, whereas **`ExecutorChannel`**, task executors, async gateways, and broker hops create new boundaries.

JDBC/JPA transactions do not cover JMS ACKs, HTTP calls, or caches automatically. Coordinating JMS and database commits at the resource level may require **JTA/XA** across participating resources; even XA excludes standard HTTP calls or emails.

In most practical integrations, a clearer approach is **durable source + idempotent consumer + transactional inbox/outbox**, accepting eventual consistency across systems backed by reconciliation.

## 5. Recoverable Design Patterns

### Pattern A — Re-read from a Durable Source with Idempotent Processing

Sources include retained brokers, transaction logs, or database inbox tables. Embed stable business keys (**`eventId`**, **`paymentId`**, **`sourceId + sequence`**) in payloads to decide whether work already ran.

When retries construct a new message with a fresh **`MessageHeaders.ID`**, never rely on that runtime ID as the sole business key. Framework message IDs can change across reconstruction, transformation, and redelivery. Idempotency keys must stay invariant for **the same business operation**, across deployments and restarts.

### Pattern B — Persist to a Durable Inbox Before ACKing the Source

When the original adapter lacks reliable redelivery, an intake step writes **`payload + eventId + status`** into an inbox table or durable queue, ACKing the source only once the inbox commits. Workers pick up **`PENDING`** records and transition them to **`DONE/FAILED`** inside explicit transactions.

A narrow **inbox commit → ACK failure** window still exists, causing the source to redeliver the same `eventId`. Inbox unique constraints make that retry harmless.

### Pattern C — Persist Messages, Groups, and Checkpoints for Stateful Flows

When Spring Integration itself holds state, select durable stores by role:

- **`JdbcChannelMessageStore`** for queue channels holding messages that must survive restarts.
- **`JdbcMessageStore / MessageGroupStore`** for aggregations and groups spanning restarts.
- **`JdbcMetadataStore`** for metadata keys, cursors, or filter state surviving deployments.
- **`JdbcLockRegistry`** or equivalent coordination when multiple instances contend over shared work/stores.

Exact classes and wiring depend on Spring Integration version, database, and JDBC schema scripts matching your library version. Configure poller transactions carefully so dequeuing, processing, and persisting outcomes never create drop windows.

### Pattern D — Outbox for Outbound Events

When a flow updates a database and emits JMS/Kafka events or invokes outbound adapters, persist **business outcome + outbox event** in one database transaction. A relay reads the outbox and dispatches later, marking sent upon broker acceptance. Because crashes can cause the relay to resend, downstream consumers must remain idempotent.

An outbox protects **intent to send**; it does not mean a single physical transmission. When downstream requires per-order ordering, include **`aggregateId`** and **`version/sequence`** in payloads with order-checking rules.

### Pattern E — Compensation After External Calls

When a handler invokes a payment HTTP API, sends an email, or updates a non-transactional system, blind replay duplicates side effects. Pass API **idempotency keys**, query state after timeouts, and implement compensating actions (refunds, release reservations). Database rollbacks never undo remote calls.

## 6. Example: Restarting an Order Event Flow

### 6.1. Goal and Boundaries

Suppose a broker holds **`OrderReady`** events carrying a unique business **`eventId`**. Spring Integration uses an inbound adapter to deserialize payloads into Java records and routes them over a **`DirectChannel`** to a database-updating handler.

Target flow:

~~~mermaid
flowchart LR
    A[(Durable broker)] -->|OrderReady, eventId| B[Inbound adapter]
    B --> C[DirectChannel]
    C --> D[Processing service]
    D --> E[(orders)]
    D --> F[(processed_flow_events)]
    D --> G[(outbox_events)]
    G --> H[Event relay]
    H --> I[(Broker / downstream consumers)]
~~~

**`DirectChannel`** does not durably buffer inputs. The design relies on the broker holding un-acked messages and the service committing inside a database transaction. If splitting asynchronously later, never casually swap in `ExecutorChannel` assuming queued state survives restarts.

To commit business updates and processing markers in one transaction, create:

~~~sql
CREATE TABLE processed_flow_events (
    flow_name    VARCHAR(100) NOT NULL,
    event_id     VARCHAR(150) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (flow_name, event_id)
);
~~~

The **`orders`** table holds **`id`** and **`status`** (initially **`NEW`**, transitioning to **`READY`**). Each `OrderReady` carries a durable business ID:

~~~java
public record OrderReady(String eventId, long orderId) {}
~~~

### 6.2. Ingesting into Spring Integration

Annotation-based Spring Integration example (imports and source adapter config omitted):

~~~java
@Configuration
class OrderChannels {
    @Bean
    MessageChannel orderEvents() {
        return new DirectChannel();
    }
}

@Component
class OrderFlowHandler {
    private final OrderEventService service;

    OrderFlowHandler(OrderEventService service) {
        this.service = service;
    }

    @ServiceActivator(inputChannel = "orderEvents")
    public void handle(Message<OrderReady> message) {
        service.applyOnce(message.getPayload());
    }
}
~~~

The inbound adapter must deliver valid **`OrderReady`** payloads into **`orderEvents`** and be configured to **acknowledge the source only after the handler succeeds**. Verify this architectural requirement via integration tests against your real adapter and broker; the code above does not configure JMS/Kafka acknowledgment by itself.

### 6.3. Recording Markers and Updating Business State in One Transaction

Example using **`JdbcTemplate` + PostgreSQL** and a single database transaction manager:

~~~java
@Service
class OrderEventService {
    private final JdbcTemplate jdbc;

    OrderEventService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void applyOnce(OrderReady event) {
        if (event.eventId() == null || event.eventId().isBlank()) {
            throw new IllegalArgumentException("eventId is required");
        }

        int inserted = jdbc.update("""
            INSERT INTO processed_flow_events(flow_name, event_id)
            VALUES (?, ?)
            ON CONFLICT DO NOTHING
            """, "order-ready-flow", event.eventId());

        if (inserted == 0) {
            return; // Event already processed in an earlier transaction.
        }

        int updated = jdbc.update("""
            UPDATE orders
               SET status = 'READY'
             WHERE id = ?
               AND status = 'NEW'
            """, event.orderId());

        if (updated != 1) {
            throw new IllegalStateException(
                "Order not found or unexpected previous state");
        }

        // If publishing events, INSERT outbox record here
        // within the same database transaction.
    }
}
~~~

Critical conditions:

1. **`@Transactional`** must execute through a Spring proxy tied to the right database transaction manager; specify qualifiers if multiple managers exist.
2. Event marker insertion and **`UPDATE orders`** must share **the same transaction**. If the update fails, the marker rolls back so future redeliveries can reprocess.
3. **`ON CONFLICT DO NOTHING`** is PostgreSQL syntax. Other databases need unique constraints with equivalent insert syntax.
4. If distinct `eventId`s can represent the same business change, deduplicating solely by `eventId` is insufficient: add business-key constraints and state-transition checks.
5. Validate payload origin, order ownership, contract version, and business fields; never apply arbitrary state from untrusted events.

### 6.4. Proving Post-Restart Behavior

Consider these timeline points:

~~~text
T0: Broker has persisted OrderReady(E-101).
T1: Inbound adapter delivers E-101 to handler.
T2: Database transaction begins.
T3: INSERT processed_flow_events + UPDATE orders.
T4: Database commit succeeds.
T5: Adapter acknowledges E-101 to broker.
~~~

**Crash before T4:** uncommitted SQL transaction rolls back; broker can redeliver E-101 since the adapter did not ACK. Handler re-runs and applies once.

**Crash between T4 and T5:** order and E-101 marker committed; broker may redeliver. Next delivery hits the unique key, skips updates, and ACKs cleanly.

**Crash after T5:** source considers E-101 done; business result is committed so no replay is required.

If you cannot enforce **DB commit before ACK**, redesign boundaries or use a durable inbox instead of assuming this flow is safe.

### 6.5. When Data Must Be Aggregated Before Updating

If a flow awaits three separate messages for one `orderId`, storing **`processed_flow_events`** only for the final output cannot protect the two earlier arrivals. Pending aggregator state is also essential state:

~~~text
Order 42:
  inventory-confirmed  -> arrived
  fraud-reviewed       -> arrived
  payment-authorized   -> pending
  group-state          -> WAITING
~~~

Across restarts, a persistent **`MessageGroupStore`** must preserve incomplete groups, or sources must reliably replay all inputs. Once all three arrive, emit output across a durable boundary and update group state in aligned transactions/order. Deleting the group before output is durably accepted risks losing it; persisting output before marking the group complete risks re-emitting it, so downstream consumers still need idempotency.

## 7. Controlled Stop, Restart, and Resume Procedure

### Before a Planned Stop

1. **Stop new intake:** pause inbound adapters, pollers, or consumers using each source's lifecycle controls. Never stop databases or brokers while in-flight transactions are still committing.
2. **Drain in-flight work:** monitor active tasks, pending groups, queue depths, retries, and outboxes. Set a drain timeout; if forcing shutdown, know which sources will replay.
3. **Snapshot checkpoints and metrics:** capture timestamp, app version, received/committed counts, queued counts, open aggregations, and DLQ counts. Keep correlation IDs for reconciliation.
4. **Verify stores:** confirm durable databases, message stores, and metadata stores are healthy and preserve the same namespaces/schemas post-deploy.
5. **Close cleanly:** ensure transactions commit or roll back; avoid marking items processed before commit.

### During Restart

1. **Verify schema and contract compatibility:** payloads, classes, serializers, headers, outboxes, and message stores remain readable by the new version.
2. **Restore resources:** reconnect databases, brokers, message stores, and lock registries; verify stale locks/leases expire properly so two workers never claim ownership simultaneously.
3. **Restore stateful components:** verify persisted message groups, durable queues, metadata/cursors, due jobs, and incomplete failure records survived.
4. **Resume with bounded concurrency:** throttle initial intake if backlogs are large to avoid overwhelming downstream or triggering retry storms.
5. **Reconcile:** compare event counts and ID lists, business outcomes, queues/outboxes/DLQs; declare resume complete only when data invariants hold.

**Note:** stopping/starting a Spring Integration endpoint keeps beans alive in the same JVM, which is completely different from restarting processes or replacing containers. **Process-kill tests** are necessary to expose RAM-only state that endpoint stop/start tests overlook.

### Restarting After an Unexpected Crash

Never blindly purge queues, reset offsets, drop groups, regenerate IDs, or replay everything before inspecting source states. First classify:

- **Processed yet un-acked:** let redelivery and deduplication resolve.
- **Acked yet unprocessed:** recover from inbox, source logs, DLQ, or business records; investigate the broken commit boundary.
- **Messages stuck in persistent stores:** inspect locks, poison messages, timeouts, and worker ownership before resuming.
- **Incomplete groups:** retain groups or verify input replay; never force-release incomplete groups unless business rules permit.
- **Unpublished outbox rows:** resume relaying; treat downstream duplicates as normal.

## 8. Verifying "Zero Loss" Through Data Reconciliation

### 8.1. Count the Right Sets

Comparing raw **inbound message counts** against **handler invocation counts** is misleading due to retries and duplicates. Distinguish:

- **`accepted_unique`**: distinct `eventId`s durably accepted by sources or inboxes within a defined test window.
- **`processed_unique`**: distinct `eventId`s with valid, committed business outcomes.
- **`pending_unique`**: distinct `eventId`s still resumable from brokers, inboxes, durable queues, or group stores.
- **`quarantined_unique`**: distinct `eventId`s in DLQs/error tables with enough data to investigate and recover.

Set-based invariant to verify:

~~~text
Accepted IDs
    = Processed IDs ∪ Pending IDs ∪ Quarantined IDs

And no Accepted ID falls outside the union of those three sets.
~~~

An event can temporarily appear in both source and `processed` before ACK commits. Therefore **do not sum raw counters** when sets overlap; reconcile ID keys and states with clear precedence rules. Snapshot participating stores at a consistent watermark or quiet window so totals do not drift mid-query.

For repeated deliveries, add the invariant:

~~~text
Each valid eventId -> at most 1 committed business side effect.
Each accepted eventId -> identifiable final outcome or recovery queue.
~~~

When multiple events map to one order, enforce **business keys**, version checks, and valid state transitions; unique `eventId`s alone do not guard against out-of-order updates to an order.

### 8.2. Illustrative Database Reconciliation Queries

Count processed markers per flow:

~~~sql
SELECT flow_name, COUNT(*) AS processed_unique
FROM processed_flow_events
GROUP BY flow_name
ORDER BY flow_name;
~~~

With an **`inbox_events(event_id, status, accepted_at)`** table, find accepted events lacking processed markers:

~~~sql
SELECT i.event_id, i.status, i.accepted_at
FROM inbox_events i
LEFT JOIN processed_flow_events p
  ON p.event_id = i.event_id
 AND p.flow_name = 'order-ready-flow'
WHERE p.event_id IS NULL;
~~~

Returned rows are **not automatically lost data**: they may be `PENDING`, `RETRY`, or `FAILED` in queues/DLQs. When intake lives in an external broker rather than DB, export IDs from broker/logs or keep an acceptance ledger; **`processed_flow_events`** alone cannot prove events were not dropped prior to reaching the handler.

For aggregators, also reconcile **`groupId`**, expected vs. present counts, timeouts, release status, and output `eventId`. For file adapters, compare files across `incoming/processing/completed/failed` against metadata and DB records.

## 9. Fault-Injection Testing: Crashing at Dangerous Points

To prove recoverability, use **real or production-equivalent databases and brokers**, deterministic input sets, and pre-run `eventId` captures. Force-kill processes/pods at targeted checkpoints, restart, and reconcile everything.

| Fault-Injection Point | Outcome to Prove |
|---|---|
| Before adapter sends message to channel | Source retains event or replays cleanly; no accepted events lost. |
| After internal queue enqueue, before handler poll | In-memory queues expose loss; properly configured durable stores retain event. |
| After dequeue from persistent queue, before business commit | Message returns to processable state or replays; never vanishes via premature deletion. |
| Mid-database transaction | Business writes and idempotency markers roll back together; retries succeed cleanly. |
| After DB commit, before source ACK | Redelivery occurs; no duplicate business side effect occurs. |
| After 2/3 aggregation parts arrive | Final part completes group accurately after restart and reconciles. |
| After group release, before durable output acceptance | Output is not lost, or replays idempotently; never "group deleted yet output lost". |
| After file/checkpoint saved, before business commit | File/event is not permanently skipped; recovery re-processes cleanly. |
| After outbox publish succeeds, before marking published | Relay may resend, yet downstream ignores duplicate side effects. |
| Broker/DB disconnect across multi-instance deployment | Proper retry/backoff and locks/leases; no wiped progress or split-brain races. |
| Persisted payloads written by an older version | Newer version deserializes/migrates data cleanly per tested upgrade plan. |

### Sample Fault-Injection Test Procedure

1. Generate a finite input batch with fixed **`eventId`**s plus deliberate duplicates, saving the expected ID list.
2. Start the flow and abruptly kill the process at a controlled checkpoint or log/metric-confirmed boundary.
3. Restart against the same database, store, and broker; let the flow drain backlog or quarantine errors.
4. Reconcile **the full `eventId` set**, business invariants, and downstream side effects; distinguish duplicate deliveries from duplicate business effects.
5. Repeat across multiple instances, redeliveries, malformed payloads, timeouts, schema changes, and version upgrades.

Do not test only **graceful shutdowns**: clean shutdowns let frameworks drain RAM tasks, hiding the exact state losses real crashes trigger.

## 10. Observing Flows Before and After Restarts

To catch "silent losses", include these signals consistently across logs, traces, and metrics:

| Signal Group | Examples to Monitor |
|---|---|
| **End-to-end identifiers** | `eventId`, `correlationId`, business key, source partition/file, flow version, `traceId`. |
| **Inbound sources** | Offset/checkpoint, ready/unacked messages, oldest message age, ingest rate, redelivery count. |
| **Queues / persistent stores** | Queue depth, unprocessed count, backlog age, serialization errors, store access failures. |
| **Aggregators / resequencers** | Open groups, expired groups, incomplete groups, release/expiry counts, duplicate sequences. |
| **Business execution** | Committed `eventId`s, skipped duplicates, rollbacks, lock timeouts, unique conflicts, business rule errors. |
| **Outbound** | Pending/failed outbox counts, unpublished event age, retry counts, DLQs, downstream latency. |
| **Restart lifecycle** | Stop/start timestamps, pre/post-restart event counts, backlog catch-up duration, disconnect windows. |

Never use **`HTTP 200` health checks** as sole proof a flow recovered. Readiness checks dependencies, whereas completeness requires **reconciliation** of events and business state.

Alert on **rising pending age**, **groups stuck past SLA**, **growing DLQs**, **non-draining outbox backlogs**, **sustained consumer lag**, or mismatches between accepted and processed/pending/quarantined IDs. Keep sensitive payloads out of logs; `eventId` and `correlationId` generally suffice for controlled lookup.

## 11. Common Misconceptions

**"`QueueChannel` means messages survive restarts."** No. In-memory `QueueChannel` is volatile; only durable stores paired with aligned transactions recover persisted messages.

**"Having `JdbcMessageStore` makes the whole flow crash-safe."** No. Removing messages before downstream commits, or clearing groups before durable output acceptance, still leaves drop windows.

**"Saving offsets/checkpoints immediately on read prevents duplicates."** It avoids re-reads at the cost of dropping uncommitted work. Reliability favors replay + deduplication over premature checkpoints.

**"Switching to an async channel only affects performance."** Async boundaries alter threads, transaction scopes, and in-flight state. You must verify replay sources or durable handoffs.

**"In-memory retries cover all outages."** Crashes wipe retry state. Post-restart recovery requires messages to remain at the source, in a DLQ, or in a durable work queue.

**"Framework message IDs make durable dedup keys."** IDs regenerate when messages are rebuilt. Use stable business keys and durable unique constraints.

**"Seeing an order marked `READY` proves no events were lost."** Other events may have vanished silently; reconcile **the complete set of accepted `eventId`s**, not a few sample orders.

**"Stopping/starting flows in one JVM proves crash recovery."** No. Many beans and RAM structures survive stop/start; test real JVM/pod kills and mid-commit disconnects.

## 12. Recovery Runbook and Handover Checklist

### Runbook When a Flow Must Restart

1. **Isolate:** identify flow ID, instance, source adapter, failure time, schema/contract versions, and involved dependencies.
2. **Preserve state:** capture queue depths, group counts, source checkpoints, inbox/outbox/DLQs, in-flight transactions, and error logs. Never reset offsets or wipe metadata before inspecting.
3. **Identify commit boundaries:** determine which events were ACKed, which business writes committed, and which outputs reached downstream; cross-check by business key.
4. **Select recovery path:** broker redelivery, inbox/log replay, persistent queue/group resumption, outbox retry, or compensating external side effects.
5. **Resume throttled:** apply bounded concurrency and backoff; watch locks/leases, backlogs, duplicate rates, and recurring errors.
6. **Confirm reconciliation:** verify every accepted `eventId` is accounted for in processed/pending/quarantine, with zero duplicate side effects and no SLA-breaching stale groups/outboxes.
7. **Document:** record root cause, failure window, recovery steps, and preventive design updates.

### Pre-Production Checklist

- [ ] Listed all business and technical states that must survive restarts.
- [ ] Every accepted message is backed by a durable source or inbox; ACKs never precede durable persistence.
- [ ] Durable queues/channels, aggregators, and metadata stores use matching schemas, namespaces, and multi-instance locks.
- [ ] Stable idempotency keys; processed markers and DB business updates commit in the same transaction wherever possible.
- [ ] Outbox or recovery mechanisms cover outbound events emitted after database commits.
- [ ] Retries, timeouts, DLQs, and replays never silently drop error data or spin indefinitely.
- [ ] Compatibility or migration plans cover persisted payloads, headers, and state from previous versions.
- [ ] Fault-injection tests verified crashes before/after commits, ACKs, checkpoints, group releases, and outbound publishes.
- [ ] Reconciliation tracks `eventId` sets and business keys; dashboards monitor backlogs, job age, duplicates, and errors.
- [ ] Runbooks define who may reset checkpoints, reopen flows, drain DLQs, and sign off on recovery.

## 13. Conclusion

**Safely restarting a flow is about recovering business work and proving outcomes, not merely restarting Spring Integration beans.** To preserve essential state, map where messages and progress live at every step, persist non-reconstructible state durably, align ACKs and checkpoints with commit boundaries, and embrace redelivery paired with idempotency. After any restart, prove correctness via **`eventId` reconciliation, business state checks, and side-effect audits**, backed by abrupt crash tests at every dangerous boundary.
