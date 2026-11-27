# Transaction-Aware MessageStore in Spring Integration Adapters

## 1. The Problem: Message Received, Yet the Process Dies Before Processing Finishes

Suppose a Spring Integration application receives order events via an HTTP inbound gateway and pushes messages into a `QueueChannel` for asynchronous processing. A handler updates a database and calls an HTTP outbound gateway to a partner. If the application uses an in-memory queue and the JVM crashes after returning `202 Accepted` but before the handler picks up the message, the event can disappear. Using a **persistent `MessageStore`** lets messages survive restarts, yet raises harder questions:

- When is a message genuinely **committed to the durable store**?
- A poller pulls a message and the handler throws: does the message **return to the queue** or get deleted forever?
- Can **business state and dequeue** be persisted in the same database transaction?
- If the database commits yet broker ACK fails, can the message be redelivered?
- If outbound HTTP times out after the partner committed, can a local transaction rescue the situation?
- With an aggregator, are individual child messages and group state truly durable and consistent when multiple workers process concurrently?
- If the store hits schema, serialization, connection, or cleanup errors, should business flow halt, retry, or route to a DLQ?

A **transaction-aware `MessageStore`** organizes message or message-group storage so that **read/write/delete operations on messages participate in a managed transaction** when supported by the implementation and transaction boundary. The goal is avoiding states where "the message vanished from the queue while business effects never committed" or "the group was marked complete even though the result was not safely delivered."

In the **Transactions** chapter of the **SPRING_INTEGRATION_ADAPTERS** module, this lesson connects directly to inbound/outbound adapters, gateways, pollers, `MessageChannel`, and flows across **File, SFTP, HTTP, JMS, AMQP, Kafka, and databases**, addressing message contracts, errors, retries, and connection lifecycles.

> **Key takeaway:** storing messages in a database **does not automatically create end-to-end exactly-once**. What can be guaranteed atomically first and foremost are **changes inside the same transaction and resource manager**. Network calls, filesystems, broker ACKs, and remote APIs usually sit outside that scope.

### Learning Outcomes

After this lesson, you will be able to:

1. Distinguish `MessageStore`, `ChannelMessageStore`, `MessageGroupStore`, and aggregator stores.
2. Pinpoint where transactions **begin, which statements they cover, and when they commit/roll back**.
3. Design a persistent `QueueChannel`/polling consumer with a JDBC store and matching transaction manager.
4. Handle failures between `receive`, handlers, business DB commits, and external acknowledgments.
5. Design message group states, timeouts, reapers, and multi-instance concurrency.
6. Apply transaction-aware storage to File, SFTP, HTTP, JMS, AMQP, Kafka, and JDBC per their distinct semantics.
7. Test crashes/restarts, rollbacks, duplicates, ordering, schema migrations, and data security inside the store.

## 2. Vocabulary and Levels of "Processed"

| Term | Meaning | Notes |
|---|---|---|
| **Message** | Payload plus headers per Spring Messaging | ID/headers may change when creating new messages |
| **`MessageStore`** | Abstraction for storing and retrieving messages | Not every store is a queue |
| **`ChannelMessageStore`** | Store tailored for channels needing group/queue semantics | Check implementation/version |
| **`MessageGroupStore`** | Abstraction for storing/interacting with message groups | Suits aggregators, resequencers, group state |
| **`QueueChannel`** | Pollable channel holding messages for consumers to pull later | Default in-memory implementation is not durable |
| **Persistent channel** | Channel backed by a durable store | Durability depends on DB/commits/config |
| **Transaction boundary** | Operations participating in one transaction | Must verify thread, manager, and resource |
| **ACK/offset commit** | Broker/transport recording that delivery was handled | Not automatically identical to DB commit |
| **Redelivery** | Message delivered again after rollback or lost ACK | Receiver requires idempotency |
| **In-flight** | Message received but not yet finished per milestone | Not necessarily visible in the queue anymore |
| **Outbox** | Durable intent to send to another system | Complements rather than replaces receiver idempotency |

### 2.1. Five Easily Confused Milestones

~~~text
SOURCE_OBSERVED
    -> MESSAGE_CREATED
    -> STORED_AND_COMMITTED
    -> DEQUEUED_AND_PROCESSED
    -> BUSINESS_EFFECT_COMMITTED
    -> REMOTE_OUTCOME_CONFIRMED
~~~

This list illustrates a **sample journey**—not every adapter has all milestones or runs them inside one transaction. For example, an HTTP gateway may reply before business effects finish; a Kafka producer ACK does not prove a consumer wrote to its database.

### 2.2. Durable Storage Differs from Transactional Processing

A `JdbcChannelMessageStore` can persist messages durably, yet if a handler pulls messages **outside a transaction** or updates the DB with a **different transaction manager**, messages can still suffer logical loss or duplicate processing. To evaluate safety, check whether the **transaction starts before or after `receive`** and which resources actually enlist.

## 3. Overview of Related Store Types

Spring Integration provides abstractions to manage messages, groups, and channels. Usage and supported stores depend on your **Spring Integration version**.

| Component | Primary need | Implementation / concept example |
|---|---|---|
| `MessageStore` | Store/fetch/remove messages by ID | Persistent message repository |
| `MessageGroupStore` | Add/fetch/remove messages in a group | Aggregator, resequencer |
| `ChannelMessageStore` | Manage messages for a persistent channel | JDBC-backed queue/channel |
| `JdbcMessageStore` | JDBC storage for messages/groups per supported API | Aggregator/resequencer persistence |
| `JdbcChannelMessageStore` | JDBC-backed persistence for pollable channels | Durable `QueueChannel` |
| Metadata store | Store checkpoints, file filters, dedup metadata | Does not store full messages by default |
| Dead-letter queue | Store terminal failures per transport | Not automatically a transaction-aware `MessageStore` |
| Transactional outbox | Persist outbound intent alongside domain state | Ensures send intent survives DB commit |

**Do not swap blindly:** `JdbcMessageStore` targets message/group use cases while `JdbcChannelMessageStore` targets channel semantics by design. They can use different schemas, queries, and providers. Read your project version's contract/API before wiring a store bean into a channel.

### 3.1. Durable Stores Are Not JDBC-Only

Spring Integration includes implementations backed by other storage technologies depending on module/version, such as Redis or MongoDB for certain needs. However, **transaction semantics, atomicity, locking, TTL, and consistency differ by backend**. Never swap a JDBC store for a Redis store and assume SQL transaction rollback semantics carry over unchanged.

## 4. Overall Architecture: Transactional Local Queue with Remote Targets

~~~mermaid
flowchart LR
    EXT[HTTP / File / SFTP / Broker / DB] --> IN[Inbound Adapter / Gateway]
    IN --> CH[Persistent QueueChannel]
    CH <--> STORE[(Transactional Message Store)]
    CH --> POLLER[Transactional Polling Consumer]
    POLLER --> HANDLER[Business Handler]
    HANDLER --> DB[(Business Tables)]
    HANDLER --> OUTBOX[(Outbox Intent)]
    OUTBOX --> DISPATCH[Dispatcher + Retry]
    DISPATCH --> TARGET[HTTP / JMS / AMQP / Kafka / SFTP]
    TARGET --> VERIFY[ACK / Status / Reconciliation]
    STORE -. local DB transaction .-> DB
    DB -. local DB transaction .-> OUTBOX
~~~

The dotted lines indicate **updates that can share one local database transaction** when the store, business tables, and outbox truly use the **same `DataSource`/transaction manager and transaction context**. They **do not** mean `QueueChannel`, handler, outbox dispatcher, broker, and target all participate in a single distributed transaction.

### 4.1. Two Transactions Are Normally Distinct

**Transaction A — ingress/storing:** the adapter or handler writes the message to the persistent channel; commit marks the point where the message is durable. For HTTP `202`, ensure commit succeeds before reporting "accepted" if the contract means "durably accepted."

**Transaction B — consuming/processing:** the poller starts a transaction, dequeues the message from the store, updates business state/outbox, and commits; on rollback, removing the message **can roll back alongside the DB updates**.

Keeping these two transactions separate is normal. What matters is clearly defining **commit points, ownership, error propagation, and replay policies**.

## 5. ACID and Practical Boundaries of a Transaction-Aware Store

### 5.1. Atomicity

Store operations and domain changes inside the same transaction on the **same resource** commit or roll back together. If code sends HTTP/Kafka/files inside that block, the remote side does not auto-rollback with the local transaction.

### 5.2. Consistency

Unique constraints, foreign keys, business invariants, and message lifecycle rules keep data valid. A transaction manager does not replace validation, idempotency, or business state checks.

### 5.3. Isolation

Two polling consumers can compete for the same message/group. Database locking/isolation, store implementation, message group locks, and transaction duration govern whether two workers ever receive the same message simultaneously.

### 5.4. Durability

After DB commit, messages/markers survive per the database's durability guarantees and replication/backup setup. Never treat an uncommitted write or in-memory cache as durable.

### 5.5. What ACID Does Not Cover

- Network transmission to an HTTP API outside the local transaction.
- Upload/rename operations on an SFTP server.
- JMS/AMQP/Kafka ACKs and offset commits without proper coordination.
- Local filesystem edits or user-facing side effects.
- Operations on another database using a different transaction manager.
- An async call scheduled after the transaction that has not yet been sent.

## 6. `MessageStore` vs. `MessageGroupStore`: Different Lifecycles

### 6.1. `MessageStore`

A general message store persists individual messages for lookup by ID. Whether it is transaction-aware depends on the implementation. **Do not infer FIFO dequeue** merely because a store exposes `addMessage(...)` or `removeMessage(...)`.

### 6.2. `MessageGroupStore`

A group store manages message groups: group ID, member messages, completion state, and release/expire/cleanup per implementation APIs. When an aggregator collects multiple parts, **correlation, release, and group-completion policies** dictate when output is produced.

### 6.3. `ChannelMessageStore`

Stores designed for pollable channels add queue semantics, group/channel identity, and next-message retrieval. For safe operation, verify:

- Which channels map to which group/key/store?
- Is dequeue/FIFO/priority ordering guaranteed under that configuration?
- Does a transaction open before `receive`?
- Are concurrent consumers or a polling task executor configured?
- On rollback, how does the message return to a ready state?
- On restart, what metadata remains and which messages were uncommitted?

### 6.4. Do Not Confuse with `MetadataStore`

A `MetadataStore` backing file accept-once filters, checkpoints, or idempotency selectors may hold only keys/values, **not full message payloads**. Even with a durable metadata store, a flow can lose messages between marking the source "seen" and committing the message into the queue.

## 7. Default `QueueChannel` vs. Persistent `QueueChannel`

### 7.1. In-Memory Queue

A `QueueChannel` without a persistent store holds messages in JVM memory. Pros: simple, low I/O overhead; cons: loses contents on process crash/restart, and cannot scale multiple replicas sharing one queue.

### 7.2. Queue with a Durable Store

~~~mermaid
sequenceDiagram
    participant I as Inbound Handler
    participant C as QueueChannel
    participant S as JDBC Channel Store
    participant P as Poller
    participant B as Business Database
    I->>C: send(message)
    C->>S: persist message
    S-->>C: write (transaction commit per boundary)
    C-->>I: send result
    Note over I,S: Treat as durably accepted only after commit
    P->>S: begin TX + receive/dequeue
    S-->>P: Message
    P->>B: business update in same TX if configured properly
    alt Handler finishes
        P->>S: commit TX
    else Exception forces rollback
        P->>S: rollback TX
        Note over P,S: Dequeue rolls back if sharing resource/TX
    end
~~~

This diagram shows the **expected transaction model**, not automatic behavior from declaring a JDBC store alone. If an async handler jumps to another executor or uses a different transaction manager, the transaction link breaks.

### 7.3. Sources and Targets Can Still Repeat

Even after a message commits into a persistent queue, upstream may miss an ACK and resend the same event. Alongside a transaction-aware queue, you need an **idempotent receiver** or unique business key. Durability solves **message loss**, not **duplicate source deliveries**.

## 8. Transaction Managers, Thread-Bound Context, and Propagation

In Spring, local JDBC transactions are typically managed by a `PlatformTransactionManager` such as `DataSourceTransactionManager`. A Spring Integration poller can configure **transaction advice**, or a service can use `@Transactional`; these two options are not equivalent in scope.

### 8.1. Three Critical Cases

| Configuration | Is dequeue in TX? | Is business update in TX? | Consequence |
|---|---|---|---|
| No transaction | Not guaranteed | Not guaranteed | Receiving then crashing can lose messages |
| `@Transactional` on handler only | Likely **no**, because receive happens before entering handler | Yes if proxy works | Message removal and domain update can split |
| Poller advice starts TX before `receive` | Yes, if store shares the same manager/resource | Yes if handler runs in same TX/thread | Rollback can restore message with domain state |

### 8.2. Thread Boundaries

Local Spring transactions typically bind to the managing thread/context. When `ExecutorChannel` or a custom async task moves work to another thread:

- The poller's transaction **does not follow the thread**.
- The handler on the new thread runs in a separate transaction or none at all.
- The poller may commit the dequeue before business effects finish.
- Redesign: process synchronously within the poller transaction, or write a **durable handoff/outbox** for async steps before committing.

### 8.3. Proxies and Self-Invocation

`@Transactional` takes effect only when invoked through the Spring AOP proxy/transaction infrastructure. Calling a transactional method from another method on **the same bean** bypasses the proxy in standard proxy setups. Never assume a transaction exists just because an annotation is present; test commits/rollbacks against a real DB.

## 9. Illustrative XML Configuration for a Transaction-Aware Poller

An **illustrative configuration using the Spring Integration XML namespace**:

~~~xml
<int:channel id="durableOrders">
    <int:queue message-store="ordersChannelStore"/>
</int:channel>

<bean id="ordersChannelStore"
      class="org.springframework.integration.jdbc.store.JdbcChannelMessageStore">
    <constructor-arg ref="dataSource"/>
</bean>

<int:service-activator input-channel="durableOrders"
                       ref="ordersHandler"
                       method="handle">
    <int:poller fixed-delay="1000">
        <int:transactional transaction-manager="transactionManager"/>
    </int:poller>
</int:service-activator>
~~~

**This is a fragment**, not a complete XML file: you still need `int` namespace declarations, `dataSource`, `transactionManager`, `ordersHandler` beans, SQL schemas, and compatible dialect/query provider settings. Verify attributes/constructors against your Spring Integration version before applying.

### 9.1. What This Fragment Means

1. `durableOrders` is a pollable channel backed by a store.
2. `ordersChannelStore` persists messages via JDBC instead of an in-memory queue.
3. The poller drives the consumer with configured transaction advice.
4. When `receive` and the synchronous handler update the **same JDBC resource**, exceptions rolling back the TX retain the message and leave business state uncommitted.
5. If the handler called remote HTTP before throwing, **HTTP side effects do not roll back**.

### 9.2. Checks Required in a Real Project

- Are the database DDL, permissions, and SQL dialect right for the JDBC channel store?
- Does the store's `DataSource` match the poller advice's transaction manager?
- Does the handler run synchronously without switching threads before commit?
- Could error handlers or retry advice **swallow exceptions**, causing unintended commits?
- What row-locking semantics govern multiple concurrent consumers/instances?
- Have you verified dequeue rollback with a real DB integration test?

## 10. Java Example: JDBC Transaction Manager and Persistent Store

~~~java
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.jdbc.store.JdbcChannelMessageStore;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class MessageStoreInfrastructure {
    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    JdbcChannelMessageStore ordersChannelStore(DataSource dataSource) {
        JdbcChannelMessageStore store =
                new JdbcChannelMessageStore(dataSource);
        // Configure query provider/schema/dialect if required by your version.
        return store;
    }
}
~~~

This code highlights **the store and local transaction manager sharing the same `DataSource`**. It is not yet enough to make the whole flow transactional: wire the store to a channel, enable transactions on the consumer poller, and implement business handlers inside the boundary. Verify `JdbcChannelMessageStore` constructors/APIs for your version; do not treat this snippet as a compiled/tested project.

### 10.1. Why Does "Same `DataSource`" Matter?

If the store uses `DataSource` A while the handler updates DB B under a different transaction manager, `@Transactional` on the handler does not roll back the dequeue in A. Even if two `DataSource`s point to the same database server, **two physical connections managed by two independent transaction contexts** commit and roll back independently.

### 10.2. Avoid Overly Long Transactions

Holding transactions across slow HTTP/SFTP calls keeps DB locks and connections pinned, cutting throughput and raising deadlocks. Prefer **domain update + outbox intent in one short transaction**, then let an external dispatcher send outside that transaction with idempotency and retries.

## 11. Persisting Ingress Before Replying to Clients

### 11.1. HTTP Inbound Gateway Returning `202 Accepted`

If the HTTP contract states "durably accepted for asynchronous processing," then **persisting the message or inbox/outbox intent must commit before replying**. If it was only placed into an in-memory queue or uncommitted transaction, returning `202` tells the client to stop retrying even though work would vanish on a JVM crash.

### 11.2. Suggested States

| State | Meaning | Response / ACK |
|---|---|---|
| `RECEIVED_NOT_COMMITTED` | Request seen, not yet durable | Never claim durable acceptance |
| `STORED_COMMITTED` | Work item durably persisted | May return `202` per API contract |
| `PROCESSING` | Worker executing | Status API can show in-progress |
| `COMPLETED` | Business effect reached confirmed milestone | Return status/result per contract |
| `FAILED_RETRYABLE` | Will retry per policy | Do not treat as finished |
| `UNKNOWN_OUTCOME` | Target may have committed | Reconcile before risky retries |

### 11.3. Never Confuse Ingress ACK with Egress Completion

Returning HTTP `202` on ingress can be valid once a message is durable, yet does not prove outbound JMS/Kafka/SFTP sends finished. Provide status endpoints or callbacks when callers need final business results.

## 12. Dequeue and Handler: The Transaction Must Span Both

A desirable sequence:

~~~text
BEGIN local JDBC transaction
  RECEIVE message from persistent queue
  VALIDATE payload / idempotency key
  APPLY business DB changes
  RECORD outbox intent (if outbound needed)
COMMIT local JDBC transaction

ACK/REPLY upstream per separate contract and boundary
~~~

If the handler throws **before `COMMIT`**, JDBC operations in the same transaction roll back. The message stays preserved for reprocessing **if the store's dequeue also joined that transaction**. If the handler called an external API between `BEGIN` and `COMMIT`, that remote call cannot be rolled back by the local JDBC transaction.

### 12.1. Service Updating Domain Inside an Existing Transaction

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderDatabaseHandler {
    private final JdbcTemplate jdbc;

    public OrderDatabaseHandler(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void handle(OrderEvent event) {
        int updated = jdbc.update(
                """
                UPDATE orders
                   SET state = ?
                 WHERE order_id = ?
                """,
                event.newState(), event.orderRef());

        if (updated != 1) {
            throw new IllegalStateException("ORDER_ROW_NOT_FOUND");
        }
    }
}
~~~

Here `OrderEvent` is a project-defined business DTO. The handler **does not start its own transaction**; the intent is that it runs **synchronously inside the poller's transaction**, using a `JdbcTemplate` backed by the same `DataSource`. For domains that can receive duplicate events, add an **idempotent receiver / unique business marker** rather than only updating a row.

### 12.2. Why Must Handlers Let Rollback Errors Propagate?

If code does:

~~~java
try {
    orderHandler.handle(event);
} catch (Exception ex) {
    log.warn("Failed but ignored");
}
~~~

the transaction interceptor sees the method finish **normally** and commits the dequeue. To trigger retry/rollback, errors must **propagate** or explicitly mark the transaction rollback-only per policy, paired with error handling, a retry budget, and a DLQ to prevent poison messages from looping forever.

## 13. Time Boundaries and Crash Points

### 13.1. Local Queue + Database Matrix

| Crash point | Message in store | Business DB | Recovery path |
|---|---|---|---|
| Before ingress commit | Not reliably persisted | Unchanged | Upstream retries or source retains it |
| After ingress commit, before poll | Durably stored | Unchanged | Poller picks up after restart |
| After dequeue, before handler, TX uncommitted | Dequeue uncommitted | Unchanged | Rolls back and redelivers if same TX |
| Handler update done, before TX commit | Dequeue/update uncommitted | Uncommitted | Both roll back if same DB TX |
| After TX commit, before source ACK | Removed from queue | Committed | Upstream may redeliver; requires idempotency |
| After outbound HTTP commit, before TX commit | Dequeue may roll back | Remote may have changed | Reconciliation / remote idempotency |

### 13.2. "Rollback" Must Always Name Its Target

Ask precisely: roll back **message dequeue**, **business update**, **outbox row**, **broker offset**, or **remote API**? Only operations enlisted with the corresponding transaction manager roll back together.

## 14. When a Message Is Received Yet the Transaction Rolls Back

A retry policy must distinguish:

1. **Transient errors:** deadlocks, temporary DB disconnects, rate limits; retry with backoff.
2. **Permanent errors:** invalid schemas, unsupported messages, unrecoverable missing domain prerequisites.
3. **Unknown outcomes:** remote timeouts after sending a request; never retry blindly.
4. **Store failures:** unknown whether dequeue/commit succeeded; read back DB state.
5. **Poison messages:** records failing consistently and blocking queue progress.

### 14.1. Infinite Rollback Loops

If a poller keeps picking up the same message, the handler throws the same exception, and the transaction rolls back, the message cycles endlessly, starving workers and blocking later messages. Add **bounded retries, delays/backoff, parking lots/DLQs**, and state transitions with matching transactions/acks.

### 14.2. A DLQ Is Not Automatically Part of a JDBC Transaction

Publishing an error to a broker DLQ and committing a DB dequeue are not automatically atomic. Crashes between them can lose messages or duplicate DLQ entries. Usually **write a durable failure/outbox intent inside the same DB transaction**, then route to the DLQ asynchronously with idempotency.

## 15. `MessageGroupStore` in Aggregators and Resequencers

Not every persistent message store acts as a queue. An **aggregator** stores **message group state** while waiting for parts; a **resequencer** holds out-of-order messages until ready to release in sequence. On restart, a durable store prevents losing buffered messages, yet release and cleanup must be designed atomically within the right scope.

### 15.1. Batch Flow Example

~~~mermaid
flowchart LR
    IN[File / Kafka / JMS Input] --> SPLIT[Splitter]
    SPLIT --> A[Part A]
    SPLIT --> B[Part B]
    SPLIT --> C[Part C]
    A --> AGG[Aggregator]
    B --> AGG
    C --> AGG
    AGG <--> GROUP[(Persistent MessageGroupStore)]
    AGG --> RESULT[Aggregate Result]
    RESULT --> QUEUE[Durable Outbound Queue]
    QUEUE --> TARGET[Remote Target]
~~~

### 15.2. States to Observe

| State | Meaning | Failure mode |
|---|---|---|
| **Group created** | First part arrived | Batch may still be incomplete |
| **Part added** | Message part stored | Duplicate parts may arrive |
| **Group complete** | Release strategy satisfied | Result may not have reached target yet |
| **Result released** | Output message created/dispatched | Crash after release loses output if non-durable |
| **Group expired** | Timed out / cleaned up per policy | May represent an incomplete batch |
| **Group removed** | Store cleaned up entry | May lose ability to spot late arrivals unless retained |

### 15.3. Group Keys Are Not Item Idempotency Keys

`correlationId` groups related parts; idempotency may require **group ID + stable item ID + operation**. Using only group ID as a deduplication key on the part handler causes the first part to suppress all subsequent parts. Without item-level idempotency, redelivering one part corrupts the group with duplicates.

## 16. Transaction-Aware Aggregators: Released Results Must Be Delivered Safely

A flawed design: the group reaches `complete` in the persistent store, the aggregator emits the result onto an in-memory output channel, and the JVM crashes before outbound runs. On restart, the group is already marked complete so it **never re-emits the result**.

### 16.1. Boundary Analysis

~~~text
Persist part
   -> Mark group complete
   -> Release aggregated result
   -> Send output
   -> External target ACK
~~~

These steps **do not automatically share one transaction**. Even when `MessageGroupStore` uses JDBC, emitting onto a `MessageChannel` or calling remote HTTP/Kafka may happen outside the DB transaction.

### 16.2. Strategies to Consider

1. **Transactional group update + durable output intent:** persist group completion and an outbox row in the same DB transaction; a dispatcher sends afterward.
2. **Durable output channel:** persist output durably before treating release as complete, using transaction synchronization where applicable.
3. **Idempotent result consumers:** if recovery releases twice, the target recognizes the same `aggregate_result_id`.
4. **Completed-group retention:** retain completion metadata long enough to detect late or duplicate parts.
5. **Recovery scanner:** detect stuck groups/intents and reconcile against the state machine.

### 16.3. Late Arrivals

A message arriving after its group already released requires an explicit policy: ignore, start a new group, amend the result, or emit a correction event. Depending on framework/config, aggregators behave differently. **Define business rules explicitly** rather than inferring them from whether a DB table purged the group.

### 16.4. Transactions Do Not Fix Bad Release Strategies

Even with atomic group persistence, a buggy release strategy emits early or never emits. Test correlation, sequence numbers/sizes, missing parts, duplicate items, group timeouts, and restarts with representative data.

## 17. `MessageGroupStoreReaper`, Expiration, and Cleanup

Some flows use reapers/expiration to remove or handle incomplete message groups past a deadline. Spring Integration supports **`MessageGroupStoreReaper`** and timeout/expiration strategies depending on version.

### 17.1. Set Policy Before Enabling Cleanup

| Question | Why it matters |
|---|---|
| Which groups count as stale? | Do some batches legitimately arrive once a day? |
| What starts the timeout clock? | Group creation, last update, or event timestamp? |
| Should partial results be released? | Might violate downstream data contracts |
| Do expired groups enter error/parking state? | Avoid losing audit trails |
| Is cleanup transactional? | Avoid deleting groups while results are still sending |
| How are late parts handled? | Avoid phantom groups or duplicate outputs |
| Who owns retries/reconciliation? | Prevent expiration from causing silent data loss |

### 17.2. Never Use Expiration to Fix Backlog Incidents

Deleting old groups to shrink row counts can drop unfinished business work. Before running bulk cleanups, classify groups as **completed, abandoned, awaiting parts, or unknown outcome**, with approvals and audit evidence per policy.

## 18. JDBC `MessageStore`: Schema, Dialect, and Migrations

Persistent JDBC stores require **tables, indexes, constraints, and SQL matching your library version and database dialect**. Never guess table definitions from an unrelated tutorial.

### 18.1. Database Foundation Checklist

1. Use the **official DDL/schema scripts for your exact Spring Integration JDBC version**.
2. Verify **dialects/query providers** match PostgreSQL, MySQL, Oracle, SQL Server, or your target DB.
3. Ensure unique constraints, indexes, and ordering/locking mechanics expected by the implementation.
4. Separate database schemas/user permissions per application when required.
5. Test upgrades when bumping Spring Integration: can new code still read older persisted messages?
6. Evaluate payload serializer / header converter compatibility across Java class/schema changes.
7. Plan backup/restore, HA, retention, purging, and disk monitoring.
8. Prepare migration rollbacks—but **never delete pending messages** just to roll back a release.

### 18.2. Indexes and Capacity

Store size grows at **ingress − committed processing**. When downstream slows down, pending rows and transaction contention spike. Measure:

- Message count, pending age, and add/remove rates.
- Query latency, DB connection waits, and lock waits/deadlocks.
- Storage bytes, index bloat, write amplification, and checkpoint/backup impact.
- Poller/concurrent consumer counts, batch sizes, and actual throughput.
- Message size distributions, serialization/deserialization costs, and mapping errors.

### 18.3. Application Version Upgrades

If a queue holds messages serialized from Java class version A, deploying version B may fail to deserialize them. Use **backward-compatible message contracts**, appropriate converters, or planned drain/migrate procedures. Never rely solely on default Java serialization for messages spanning deployments without compatibility testing.

## 19. Serialization: Persisted Messages Differ from In-Memory Objects

A Spring `Message<?>` has payload and headers, which may include:

- Java DTOs, records, maps, `byte[]`, XML/JSON, or file references.
- Runtime objects like `replyChannel`/`errorChannel` unsuitable for serialization.
- `InputStream` or unmaterialized resources that cannot be stored directly depending on store/converter.
- Trace baggage, sensitive metadata, and application headers.
- Class schemas evolving across deployments.

### 19.1. Payload Design Rules

1. Prefer **stable data contracts** (versioned JSON/Avro/Protobuf/DTOs) over classpath-coupled objects for long-lived stores.
2. Persist only necessary, serializable, approved headers.
3. Never persist raw passwords/tokens, session objects, or file streams in a persistent store.
4. For oversized payloads, consider storing a **reference to an ACL-protected object store** while the message carries metadata and content hashes/versions.
5. Test converter failures before/after commit; never mark unreadable messages complete.
6. Audit deserialization risks for untrusted inputs; enforce type allowlists and up-to-date libraries.

### 19.2. "Serialized Successfully" Does Not Mean "Processable"

Messages written cleanly by version A can still hit class/schema incompatibility in version B. Run **compatibility tests reading messages persisted by the prior version**, not only unit tests writing and reading inside one JVM.

### 19.3. Sensitive Data Resides in the Store

Unlike RAM queues, a persistent `MessageStore` can store **full payloads and headers** inside the database—flowing into backups, replicas, SQL debug logs, audits, and support exports. Enforce data classification, encryption at rest, TLS to DB, RBAC, access audits, retention, and purge/backup policies. A `MessageStore` **is not automatically a safe vault for secrets**.

## 20. Concurrency and Transaction Isolation with Multiple Consumers

A persistent queue may be polled by multiple threads or instances. Safe operation requires understanding how the implementation guarantees **atomic take/dequeue**.

### 20.1. Race Conditions

- Two pollers try to claim the same message concurrently.
- Worker A receives inside a long transaction; worker B blocks on locks or skips records.
- Worker A rolls back; the message becomes eligible again.
- Worker B commits results ahead of A, reordering output.
- Database deadlocks when message/group tables and business tables are locked in opposite orders.
- Poller timeouts/cancellations close connections mid-commit.

### 20.2. Isolation Does Not Guarantee Strict Ordering

Implementations may use row locks, paging, or group keys; "first stored, first completed" is not guaranteed under multiple workers. When per-entity ordering is required, enforce **partition/group keys, version/sequence guards, or proper serialization**.

### 20.3. Long-Running Transactions Stall the Queue

If a poller opens a JDBC transaction and calls an API taking tens of seconds:

- Row locks and DB connections remain held.
- Other consumers suffer lower throughput or contention.
- Deadlocks and timeouts rise.
- Queue depth and oldest age climb.

Good designs limit transactions to **local DB effects + durable outbound intent**, moving external I/O to a separate step with retries and idempotency.

## 21. Transaction Synchronization and Post-Commit Actions

Some flows need to trigger work **after** a local transaction commits, such as emitting events or waking a dispatcher. Spring provides transaction synchronization, and Spring Integration integrates it across supported versions.

### 21.1. A Common Mistake

~~~text
BEGIN TX
  UPDATE business DB
  SEND remote API
ROLLBACK business DB due to later error
~~~

The remote API may already have processed the call, so rolling back the local DB **does not cancel the remote effect**.

### 21.2. What Good Are After-Commit Callbacks?

Deferring remote calls to **after-commit** avoids calling them when the local transaction rolls back; however, **the process can crash after commit and before the callback executes**. An in-memory callback is not a durable outbound handoff.

### 21.3. When to Use an Outbox?

When outbound events must never be lost, insert an **outbox row inside the same local transaction** as the business update. After commit, a dispatcher reads the row, sends to the target, and updates state. `afterCommit` may **wake the dispatcher** for speed, while the outbox row provides durable evidence.

## 22. File Adapter: Filesystems Do Not Roll Back with JDBC Stores

A File inbound adapter may read a file and enqueue a message into a persistent queue. If the database transaction rolls back, file renames/moves/deletes on the filesystem **do not revert automatically**.

### 22.1. Real Boundaries

| Action | Inside local JDBC TX? | Notes |
|---|---|---|
| Insert queue message into JDBC store | Possibly, if manager/store share context | Verify commit |
| Update business table in same DB | Possibly | Same transaction |
| Move/rename file | No | Filesystems do not auto-rollback |
| Mark accept-once metadata in external store | Depends on implementation | May be a separate transaction |
| Send HTTP/Kafka | Not automatically | Needs target idempotency/outbox |

### 22.2. Safe Organization

1. Ensure files are **complete/stable** before reading; never parse partially written files.
2. Define file identities/manifests and **idempotency** per logical file/batch.
3. Mark a file "processed" only after durable processing reaches the contractual checkpoint.
4. If moving before processing, keep a recoverable source or reliable persistent queue with a recovery plan.
5. For multi-record files, use per-item completion ledgers rather than just a single file flag.
6. Never log raw sensitive file paths or payloads when troubleshooting.

## 23. SFTP Adapter: Remote Sessions and Local Transactions Are Independent

SFTP inbound/outbound has session/connection lifecycles, remote listings, transfers, renames, and metadata filters. **Remote SFTP operations do not join a JDBC transaction** simply because messages are stored in `JdbcChannelMessageStore`.

### 23.1. Potential Failure Points

~~~text
REMOTE_FILE_DISCOVERED
  -> DOWNLOAD_ATTEMPTED
  -> LOCAL_FILE_READY
  -> MESSAGE_STORED_AND_COMMITTED
  -> BUSINESS_PROCESSED_AND_COMMITTED
  -> REMOTE_ARCHIVE_OR_ACKNOWLEDGED
~~~

If crashing after download and before queue commit, the file needs a retry path. If crashing after local DB commit and before remote archiving, the source may resend the file; the receiver must deduplicate business events. If outbound SFTP times out, the target may hold a **partial file**.

### 23.2. Design Rules

- Define remote file generation IDs instead of relying solely on filenames/mtimes.
- Use temporary names + atomic rename/handoff where supported by the remote contract.
- Distinguish **downloaded**, **queued**, **processed**, **uploaded**, and **confirmed**.
- Be careful when multiple replicas poll the same remote source; coordinate filters/locks.
- Check remote status/size/checksum per policy before retrying uploads.
- Never span a database transaction across long transfers.

## 24. HTTP Inbound/Outbound Gateways: Responses and Transactions Differ

### 24.1. HTTP Inbound

HTTP clients retry on timeouts or connection resets. A persistent message store ensures **after commit** work items survive restarts; however, replying before commit tricks clients into thinking requests are safe when they are not yet durable.

When receiving side-effecting requests:

1. Authenticate, authorize, and validate the request.
2. Check idempotency keys scoped by tenant/operation.
3. Commit the durable work item/inbox marker before returning `202` if the contract requires it.
4. Return an opaque reference/status URL per policy.
5. Have workers process later, persist business completion, and expose status/callbacks.

### 24.2. HTTP Outbound

Placing a remote HTTP call inside a JDBC transaction **does not** enroll the remote server into that transaction. If timing out after remote commit:

- Local transaction may roll back and the message be redelivered.
- Retries may call the remote API a second time.
- Use **remote idempotency keys**, readbacks/reconciliation, or compensating workflows.

### 24.3. `200`/`202` Responses Do Not Automatically Mean Business Done

HTTP `200` can carry business error payloads; `202` usually means accepted asynchronously. SLIs and completion markers must follow the **target's contract**, not merely HTTP status classes.

## 25. JMS: Local Message Stores and Broker ACKs Are Two Separate Resources

A JMS consumer may receive a message, write it to a local persistent `MessageStore`, and ACK the broker. To avoid losing messages, **the local store commit must complete before the broker ACK** by design. If the store commits and broker ACK fails, JMS redelivers → the local receiver needs an idempotency key.

### 25.1. Two Strategies Easily Confused

| Strategy | Benefit | Risk |
|---|---|---|
| ACK JMS before DB store commits | Fewer redeliveries | DB failure after ACK loses the message |
| Commit DB store before ACK JMS | No lost durable work from premature ACK | Failed ACK causes duplicates; needs dedup |
| Coordinate transactions via supported mechanism | Shrinks discrepancy window | Complex setup; guarantees must be tested |

### 25.2. When Handlers Also Update Business DBs

If a JMS consumer calls a domain service inside one local DB transaction and acks afterward, examine **container transaction/ack modes, exception handling, and synchronization**. `@Transactional` does not automatically make JMS ACK and JDBC atomic. Redelivered consumers need **unique business event markers** to avoid duplicate side effects.

### 25.3. Redelivery and DLQs

JMS redeliveries must not be counted as distinct business events. Design retry budgets, backoff, and DLQs per provider; when the DB store already persisted a message and the broker redelivers, idempotent ingress prevents inserting duplicate work items.

## 26. AMQP/RabbitMQ: Publisher Confirms Differ from Consumer ACKs

With AMQP, distinguish:

- **Publish attempt** on the outbound adapter.
- **Publisher confirm** per broker protocol.
- **Consumer delivery** and prefetch.
- **ACK/NACK/requeue** from the consumer.
- **Business transaction commit** in the database.

A Spring Integration persistent message store protects only **messages in the local DB**. Broker ACKs/NACKs do not automatically join local SQL transactions. If the DB commits and the consumer crashes before ACK, RabbitMQ redelivers; maintain **business idempotency keys**.

### 26.1. Poison-Message Loops

If schema errors cause handlers to roll back endlessly, the same message requeues forever. Add **bounded retries, DLQs, and error classification** rather than scaling consumers. Never log raw bodies; error messages can contain sensitive data.

### 26.2. Outbound Transactional Handoffs

Insert an outbox row in the same DB transaction as business effects, let a dispatcher publish AMQP with a stable outbound command ID, and track confirms/returns. If the dispatcher crashes after confirm and before updating outbox status, it may resend; target consumers need idempotent receivers.

## 27. Kafka: Offset Commits Do Not Auto-Sync with JDBC `MessageStore`

A Kafka consumer can receive a record, save it to a local message store, and commit its offset. Crash windows:

| Timing | Possible outcome |
|---|---|
| Before store commit | Record not durable locally; should not be treated as received |
| Store committed, offset uncommitted | Kafka may redeliver, causing duplicate enqueues |
| Offset committed, store commit uncertain | Risk of lost work item if store fails |
| Worker finishes DB, local dequeue uncommitted | Local queue redelivers; needs idempotency |
| Outbound Kafka publish succeeds, DB/outbox status un-updated | Retries may publish duplicates |

### 27.1. Kafka Transactions Do Not Replace Database Transactions

Kafka transactions and idempotent producers offer guarantees within Kafka and matching consumer/producer setups. **A `MessageStore`'s local JDBC transaction is not a Kafka transaction**. If using custom coordination/synchronization, test failure windows instead of inferring "exactly-once" from feature names.

### 27.2. Practical Design

- Use stable business event IDs on inbound when producers can resend.
- Commit durable inbox/store before offset ACK per policy.
- Apply idempotent receivers at both handler and target.
- For consume–DB update–produce, consider **transactional inbox/outbox**.
- Monitor Kafka topic/partition/offsets, lag, rebalances, and DLQs separately from local queue metrics.
- Never use trace IDs or Spring Message IDs as logical event deduplication keys.

## 28. JDBC Inbound/Outbound: The Most Natural Fit for Shared Transactions

When the JDBC source, message store, and business tables live in **the same database with the same transaction manager**, updating source status/markers, persisting durable messages, and updating domain state can all share one transaction.

### 28.1. Polling Design Sketch

~~~text
BEGIN TX
  SELECT eligible rows with claim/lock strategy
  INSERT durable work item / inbox if not processed
  UPDATE source row as enqueued
COMMIT

Later:
BEGIN TX
  DEQUEUE durable work item
  APPLY domain operation idempotently
  INSERT outbox intent if needed
COMMIT
~~~

This is a **logical transaction sketch**, not concrete SQL/APIs. `SELECT FOR UPDATE`/`SKIP LOCKED` mechanics and transaction scheduling vary by database; test races across concurrent pollers.

### 28.2. What If the JDBC Source Lives in Another Database?

Do not assume the business DB's transaction manager covers another JDBC source. You may need reliable polling with idempotency, inbox/ledgers, and reconciliation; consider **XA/JTA** only if strictly required and supported by all resources after weighing cost and complexity.

### 28.3. Watermarks Do Not Replace Completion Markers

`last_processed_id` or `updated_at` helps scan sources, yet late-arriving events, transaction rollbacks, or reordered rows cause watermarks to miss or re-read data. **Store transactions + idempotency + versioning** solve different requirements.

## 29. Combining Transactional Inbox/Outbox with `MessageStore`

A **transaction-aware `MessageStore`** handles durable in-app message storage and retrieval, yet when business rules demand "once an event is received, another command must definitely be emitted," **Inbox/Transactional Outbox** is usually simpler to verify than holding transactions open across networks.

### 29.1. Local Transaction Design

~~~mermaid
flowchart TD
    IN[Inbound Delivery] --> KEY[Validate business event key]
    KEY --> TX[Begin local DB TX]
    TX --> INBOX[Insert unique inbox marker]
    INBOX --> DOMAIN[Update domain state]
    DOMAIN --> OUTBOX[Insert outbound intent]
    OUTBOX --> COMMIT[Commit DB TX]
    COMMIT --> ACK[ACK ingress or return accepted]
    COMMIT --> D[Outbox Dispatcher]
    D --> REMOTE[External Target]
    REMOTE --> CONFIRM[ACK / Status / Reconcile]
    CONFIRM --> DONE[Mark outbound outcome]
~~~

### 29.2. Illustrative PostgreSQL Schema

~~~sql
CREATE TABLE integration_inbox (
    tenant_ref     varchar(80)  NOT NULL,
    event_id       varchar(160) NOT NULL,
    operation      varchar(80)  NOT NULL,
    processed_at   timestamptz  NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_ref, event_id, operation)
);

CREATE TABLE integration_outbox (
    command_id     varchar(160) PRIMARY KEY,
    event_ref      varchar(160) NOT NULL,
    target_alias   varchar(80)  NOT NULL,
    payload_json   jsonb        NOT NULL,
    state          varchar(32)  NOT NULL,
    attempt_count  integer      NOT NULL DEFAULT 0,
    created_at     timestamptz  NOT NULL DEFAULT now()
);
~~~

This is an **application-specific schema**, not Spring Integration JDBC's internal tables. `payload_json` may hold PII requiring encryption/ACLs/retention; production needs indexes, versions, leases/retries, audits, business uniqueness constraints, and tested schema migrations.

### 29.3. Transaction Pseudocode

~~~text
processInbound(event):
    validateAuthSchemaBusinessKey(event)
    BEGIN local DB transaction
        if not insertUniqueInboxKey(event.key):
            return ALREADY_COMMITTED
        applyBusinessChange(event)
        insertOutboxCommand(stableCommandId, approvedPayload)
    COMMIT
    acknowledgeInboundAccordingToTransport()

dispatchOutbox(command):
    claimPendingCommandWithLease(command.id)
    sendToRemoteUsingStableIdempotencyKey(command.id)
    if remoteConfirmed:
        markConfirmed()
    else if timeoutAndUnknown:
        markUnknownAndReconcile()
    else:
        retryWithBoundedBackoff()
~~~

### 29.4. Key Distinctions

- Inbox markers block **duplicate domain updates** inside the same transaction.
- Outbox rows protect **send intent**, even if the JVM dies right after commit.
- Dispatchers may still send **more than once** if crashing after remote ACK and before updating the outbox.
- Remotes require idempotency keys/correlation or reconciliation to prevent **external duplicate effects**.
- You can use a persistent `QueueChannel` as a durable handoff layer, while avoiding **writing to two places outside one transaction** without knowing which is authoritative.

## 30. XA/JTA, Local Transactions, and Transaction Synchronization

Occasionally a system requires one transaction spanning multiple resource managers. **XA/JTA** can coordinate standards-compliant resources, though not every adapter, broker, or API supports it. Distributed transactions require weighing throughput, recovery logs, timeouts, in-doubt failures, and operational complexity.

### 30.1. Pattern Selection Table

| Model | Atomic within which scope? | When appropriate |
|---|---|---|
| **Local JDBC TX** | Enlisted JDBC resource/manager | DB-backed queue + domain tables |
| **Local TX + Outbox** | Domain state + durable send intent | Safe post-commit event/HTTP/broker delivery |
| **Remote idempotency + reconciliation** | Remote side effects per contract | Payment APIs, file handoffs, resource creation |
| **XA/JTA** | Participating XA resources | Specialized requirements with tested failure recovery |
| **Saga/compensation** | Multiple local TXs with compensating steps | Long-running distributed workflows or non-XA systems |
| **Best-effort sync** | Execution ordering, no global atomicity | Only when inconsistency risks are acceptable and handled |

### 30.2. Pick the Simplest Design That Meets Requirements

If the requirement is simply "don't lose messages on JVM restart," a persistent queue may suffice. If it is "don't charge twice on HTTP timeouts," you need **remote idempotency and domain ledgers**. If it is "DB updates and event publishes must stay aligned," use an outbox. Never turn on XA/JTA across every connector just because the lesson title mentions transactions.

## 31. Defining Error Contracts and States for Persistent Work Items

For safe operations, model persistent messages/work items with explicit meaningful states:

~~~mermaid
stateDiagram-v2
    [*] --> RECEIVED
    RECEIVED --> STORED: Commit ingress
    STORED --> PROCESSING: Poll/claim
    PROCESSING --> COMPLETED: Local effect commits
    PROCESSING --> STORED: Transaction rolls back, retry
    PROCESSING --> UNKNOWN: External timeout
    UNKNOWN --> COMPLETED: Target confirms
    UNKNOWN --> STORED: Reconciled safe to retry
    PROCESSING --> FAILED_TERMINAL: Permanent error per policy
    FAILED_TERMINAL --> REPLAY_PENDING: Approved replay
    REPLAY_PENDING --> STORED: New controlled attempt
~~~

**This is an illustrative application state machine**, not states created by `JdbcChannelMessageStore` out-of-the-box. The store manages rows/transactions without tracking `UNKNOWN`, `FAILED_TERMINAL`, or remote receipts; maintain those states in a separate business ledger/side table when needed.

### 31.1. Never Treat Disappearance of a Queue Row as Completion

A row vanishing from a persistent queue after dequeue commit does NOT prove:

- The handler successfully sent an HTTP request.
- A downstream Kafka consumer persisted to its database.
- A File/SFTP output was accepted by the partner.
- A DLQ publish succeeded.
- The business operation was not duplicated.

Completion requires a **completion marker** in the authoritative store defined by your contract.

## 32. Performance and Capacity Planning for `MessageStore`

Persistent stores trade disk I/O, serialization, connection usage, and transaction contention for durability. Measure this **trade-off** under realistic workloads.

### 32.1. Key Metrics

| Metric | Question |
|---|---|
| **Ingress committed/s** | Rate at which messages persist durably |
| **Committed dequeue/s** | Rate at which messages complete processing |
| **Pending message count** | How many work items are waiting |
| **Oldest pending age** | How delayed the oldest event is |
| **Transaction duration p95/p99** | Are transactions holding locks too long? |
| **DB pool wait/active** | Is the connection pool saturated? |
| **Deadlock/lock timeout rate** | Is there contention across consumers/groups? |
| **Serialization failures** | Can messages serialize/deserialize across versions? |
| **Store error rate** | SQL/schema/permission/network issues |
| **Outbox unknown outcomes** | Remote calls that may have committed without reconciliation |
| **Duplicate/retry attempts** | Are transport or business layers redelivering? |
| **Cleanup/retention lag** | Expired rows/messages not yet purged per policy |

### 32.2. Apply Backpressure in the Right Places

When ingress outpaces dequeue:

~~~text
pending_next ≈ pending_current + stored_committed - processed_committed
~~~

This is an **approximation**; factor in retries, poison messages, re-enqueues, expirations, group releases, and parallel flows. Never scale poller concurrency unboundedly: it can worsen DB lock contention, remote rate limits, or executor saturation.

### 32.3. Safe Optimization

1. Keep transactions short; avoid remote I/O inside local DB locks.
2. Alert on backlog age rather than queue depth alone.
3. Choose schemas, indexes, and query providers tuned to your database.
4. Cap message sizes; store oversized payloads in an ACL-protected object store.
5. Measure retry storms, deadlocks, and pool usage before adding consumers.
6. Use store-compatible pagination, batching, and retention policies.
7. Set quota/capacity alerts before disk or DB pools run dry.
8. Purge only **safely settled states**—never delete pending items to "free disk space."

## 33. Securing Data in Stores and Administrative Access

Unlike in-memory queues, a persistent `MessageStore` stores full messages inside the database—flowing into backups, replicas, SQL debug logs, audits, and support exports.

### 33.1. Primary Risks

- Payloads/headers containing PII, payment details, tokens, or sensitive file contents.
- `replyChannel`, `errorChannel`, or runtime objects unsuitable for serialization.
- SQL bind-parameter logging copying payloads into log pipelines.
- Admins purging/deleting unprocessed rows.
- Store DB accounts granted overly broad schema privileges.
- Snapshots/backups outliving business data retention limits.
- `ErrorMessage`/DLQ entries retaining sensitive original payloads.
- Messages from untrusted sources triggering unsafe deserialization.

### 33.2. Recommended Controls

1. Classify payloads/headers **before storing**.
2. Use versioned, schema-validated serializers/converters with type validation.
3. Enforce encryption in transit/at rest and store DB credentials in a secret manager.
4. Apply RBAC / least privilege across apps, DBAs, backups, and monitoring.
5. Enforce retention per business/compliance rules and securely purge eligible data.
6. Log metadata—flow, opaque correlation, attempt, error class—**never dump raw messages**.
7. Protect DLQs, outboxes, and group stores at the same level as source messages.
8. Require ownership, auditing, and approval for production purges, replays, or repairs.

## 34. Testing: Verify Failure Boundaries, Not Only Happy Paths

A test using a persistent store is insufficient if it merely sends and receives one message. Verify **commits, rollbacks, restarts, multi-instance concurrency, schemas, and external side effects**.

### 34.1. Test Matrix

| Test case | Action / fault | Expected outcome to verify |
|---|---|---|
| **Store commit** | Send a message and commit | Still readable in a fresh context |
| **Ingress rollback** | Store-writing TX throws before commit | No phantom durable work item left |
| **Dequeue rollback** | Poller TX receives message; handler throws | Message remains/restores per store TX |
| **Dequeue commit** | Handler local DB succeeds | Message removed exactly once at boundary |
| **Different `DataSource`s** | Store and domain DB use separate managers | Proves rollback is **not** atomic; test detects split |
| **Self-invocation** | `@Transactional` bypasses proxy | Verifies transaction actually opens |
| **Async boundary** | `ExecutorChannel` splits handler to another thread | Does not assume poller TX still applies |
| **DB deadlock** | Two consumers contend for locks | Retries/backoff without losing messages |
| **Process crash** | Kill JVM before/after commit | Survives or redelivers per matrix |
| **Restart with old DTO** | Read message serialized by previous release | Migration/compatibility succeeds or fails safely |
| **Group timeout** | Aggregator misses parts | Expiration / partial result matches policy |
| **Group release crash** | Crash between complete and outbound | Output not lost or safely replayable |
| **JMS redelivery** | ACK fails after DB commit | No duplicate side effects applied |
| **AMQP NACK** | Consumer rolls back / requeues | Retries/DLQ match policy |
| **Kafka rebalance** | Offset uncommitted | Business idempotency prevents duplicates |
| **HTTP timeout after commit** | Remote committed, client missed response | Reconciles/idempotent; no double effect |
| **SFTP interrupted upload** | Remote holds partial file | Recovery/handoff avoids corrupt final files |
| **Store unavailable** | DB connection failure | Never ACKs success before durable commit |
| **Multi-pod** | Two instances poll/claim concurrently | No double commits or broken ordering contract |
| **Retention cleanup** | Old messages/markers purged | Never deletes critical pending/unknown rows |

### 34.2. Choosing the Right Test Types

- **Unit tests:** business keys, release strategies, error classification.
- **Integration tests:** JDBC store/schema, poller transaction advice, rollbacks against a real database.
- **Failure tests:** process kills, network partitions, crashes at checkpoints, and restarts.
- **Protocol tests:** broker ACKs/commits, HTTP timeouts, SFTP transfers, DB transactions.
- **Compatibility tests:** messages persisted by the prior version read by the new version.
- **Security tests:** sensitive payloads/headers never leak into logs/metrics/exports, and ACLs hold.

`SimpleMetadataStore` or an in-memory `QueueChannel` cannot substitute for persistence/JDBC rollback tests when validating transaction-aware storage.

## 35. Contract-Level Transaction Rollback Test Example

### 35.1. Test Specification

~~~text
Given:
  - JDBC-backed QueueChannel and polling consumer configured
  - Store and business tables share the same DataSource + transaction manager
  - One valid message is persisted and committed in the queue
  - Synchronous handler will throw RuntimeException after updating the business table

When:
  - Poller receives the message and invokes the handler inside a transaction

Then:
  - Business update is NOT committed
  - Transactional dequeue does NOT permanently lose the message
  - Retries observe the message again per queue/store semantics
  - Error logs do not dump raw payloads

When:
  - Fault condition is cleared and poller reprocesses

Then:
  - Business update commits exactly once per idempotency policy
  - Queue state reflects message processed
~~~

This is a **test specification**, not an executed JUnit suite. Use proper queue inspection APIs/counters and avoid fragile timing races. When retries use backoff or async pollers, use synchronization/eventual assertions instead of fixed `Thread.sleep` calls.

### 35.2. Local Transaction Verification with Spring JDBC

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class LocalStoreAndDomainWriter {
    private final JdbcTemplate jdbc;

    public LocalStoreAndDomainWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void writeTwoDomainRowsThenFail() {
        jdbc.update("INSERT INTO demo_a(id) VALUES (?)", 901);
        jdbc.update("INSERT INTO demo_b(id) VALUES (?)", 901);
        throw new IllegalStateException("INTENTIONAL_TEST_FAILURE");
    }
}
~~~

This snippet illustrates **rollback of two JDBC updates in one transaction** when invoked via a Spring proxy with a matching transaction manager. It **does not test `QueueChannel`**. To prove a `MessageStore` participates in the transaction, include actual store add/dequeue operations in the same integration test.

### 35.3. Testing "Remote Committed, Local Rolled Back"

Have a fake HTTP server persist a command ID and intentionally **drop the response**. The local handler times out, the local DB transaction rolls back, and the message is redelivered. Verify:

1. Receiver records `UNKNOWN_OUTCOME` instead of assuming the remote failed.
2. Retries reuse the **same remote idempotency key** or read back status first.
3. Remote applies only one business effect across multiple attempts.
4. Logs/Micrometer track attempt counts separately from unique completed counts.

## 36. Runbook TXSTORE-01 — Message Vanishes After Handler Error

**Trigger:** an inbound event was accepted, yet is gone from the queue and missing from the business DB/target.

1. Locate the **opaque correlation/event reference**, confirming source, instance, and time window.
2. Distinguish whether ingress stayed in RAM, called `send()`, or **committed to the JDBC store**.
3. Inspect store schema/queries/provider, SQL exceptions, connection pool, transaction logs, and pending rows.
4. Check whether the consumer poller has **transaction advice starting before `receive`** or only `@Transactional` on the handler.
5. Verify store and domain updates share the same `DataSource`/manager/thread.
6. Look for swallowed exceptions in error handlers or retry advice causing unintended commits.
7. Check whether an async handoff to another executor/queue broke the transaction boundary.
8. Check whether the message moved to DLQ, parking lot, expired group, or outbox.
9. Reconcile broker ACK/offsets, file/SFTP state, and external target outcomes before replaying.
10. Never blindly purge/delete DB rows or inject duplicates; draft an approved recovery plan if side effects are unknown.
11. Fix the boundary/config and add a crash/rollback integration test reproducing the exact fault.
12. Close the incident with evidence of **durable recovery + business completion**, not merely an empty queue.

### 36.1. Common Root Causes

| Symptom | Suspect |
|---|---|
| In-memory queue empty after restart | Missing persistent store |
| DB removed message while domain rolled back | Receive outside TX or different resource managers |
| Handler threw yet message removal committed | Exception caught/swallowed without rollback-only |
| State exists in store yet fails to deserialize | DTO/schema/serializer incompatibility |
| Aggregator complete yet no output seen | Group release and output send not durable in same boundary |
| Source JMS/Kafka ACKed yet store lacks row | Ingress ACK happened before durable commit |

## 37. Runbook TXSTORE-02 — Backlog and DB Locks Spiking

**Trigger:** pending rows/queue age climbing, DB pool saturated, deadlocks, or poller timeouts.

1. Measure ingress committed/s, dequeue committed/s, oldest pending age, and retry/error rates.
2. Inspect store query durations, lock waits, deadlocks, and connection pool saturation.
3. Check whether handlers hold transactions open across slow HTTP/SFTP/Kafka calls.
4. Check whether concurrency/poller batch size exceeds DB or remote target capacity.
5. Classify poison messages and retry loops; move to parking/DLQ per policy if needed.
6. Check indexes, query plans, and JDBC store schema version.
7. If throttling ingress, evaluate HTTP responses/ACKs and upstream backlogs; never silently accept and drop work.
8. Never blindly raise consumer threads or truncate queue tables.
9. Apply bounded concurrency, short transactions, outbox dispatchers, backoff, and capacity reviews.
10. Monitor backlog age, error rates, remote confirmed events, and unique completions post-remediation.

## 38. Twelve Practical Scenarios

### Scenario A — HTTP Returned `202`, Then JVM Crashed

An HTTP inbound gateway returns `202` right after placing the message in an in-memory `QueueChannel`; the JVM crashes before any consumer pulls it.

**Analysis:** `202` promised durable processing that an in-memory queue cannot deliver. Commit a persistent store/inbox before returning `202` or revise the contract; verify requests via opaque references and idempotency rather than assuming messages survive restarts.

### Scenario B — Persistent `QueueChannel`, Dequeue Outside TX

The handler has `@Transactional`, receives the message, updates the DB, and throws. The DB rolls back, yet the queue message never comes back.

**Analysis:** the handler's transaction opened **after `receive`**. Attach poller transaction advice before dequeue, share `DataSource`/manager, write a rollback integration test, and eliminate transaction-breaking async boundaries.

### Scenario C — JMS Redelivery After Local DB Commit

A consumer commits domain state, then misses the JMS ACK so the broker redelivers the message.

**Analysis:** local DB transactions do not guarantee JMS ACKs; an idempotent receiver / unique event marker skips repeating the side effect on the second delivery and ACKs cleanly.

### Scenario D — Kafka Offset Commits Before Durable Enqueue

A consumer commits its offset while the SQL insert into the message store has not yet committed; the DB disconnects.

**Analysis:** the record risks being skipped with no durable local copy. Reorder/coordinate commits properly, test the crash window, and inspect broker retention before recovering.

### Scenario E — SFTP File Moved Before Store Commit

An inbound file is moved to archive, then the JDBC store fails and rolls back.

**Analysis:** file moves do not roll back with JDBC TX. Restore/requeue from archive per policy, enforce clear checkpoints/handoffs, and avoid moving/deleting source files prematurely.

### Scenario F — HTTP Outbound Times Out After Remote Commit

A message is dequeued from a persistent queue inside a JDBC TX, calls a remote API, and times out. The TX rolls back so the message is redelivered.

**Analysis:** the remote target may have committed. Use stable remote idempotency keys and reconciliation; never mistake local rollback for reversing a remote payment.

### Scenario G — Aggregator Completes, Result Lost

Group state is persisted as `complete`; the aggregator dispatches the result to a RAM channel and the process crashes.

**Analysis:** group persistence does not make output delivery durable. Add a transactional outbox / durable result handoff with result idempotency, and test crashing across that exact gap.

### Scenario H — Two Replicas Process One Group Concurrently

Two JVMs share a group store without concurrency/release control; both emit the aggregate result.

**Analysis:** inspect `LockRegistry`/DB isolation/claiming and release semantics alongside result IDs and idempotent downstream receivers; test races across multiple instances.

### Scenario I — Old Messages Fail Deserialization After Deploy

The queue holds serialized Java objects from version A. Deploy B changes class structure and workers fail to read them.

**Analysis:** adopt version-aware serializers/schema migrations, backward compatibility, or planned drains; never delete pending rows as a "quick fix."

### Scenario J — Database Poller Holds Locks Too Long

A polling consumer opens a transaction and makes a 45-second SFTP upload; other consumers hit lock timeouts.

**Analysis:** move external I/O outside local DB transactions using an outbox and dispatcher, cap concurrency, and monitor lock waits and queue age.

### Scenario K — DLQ Publish Succeeds, Dequeue Rolls Back

A handler publishes to an AMQP DLQ, then a SQL statement throws; the local transaction rolls back. On the next poll, the message is sent to the DLQ again.

**Analysis:** DLQ sending is outside the JDBC transaction. Persist a durable failure intent/outbox and make DLQ consumers idempotent; never assume a message appears once just because the error handler ran once.

### Scenario L — File Batch Deleted by Group Reaper

An aggregator waits for 20 parts; only 18 arrive, the reaper cleans up the group, and troubleshooting context vanishes.

**Analysis:** define timeouts/expiry, retention, partial-failure policies, DLQ/parking, audits, and recovery. Never treat expiration as business success.

## 39. Transaction-Aware `MessageStore` Implementation Checklist

### 39.1. Message and Store Contracts

- [ ] Clarified purpose: durable queue, message group, inbox, or outbound intent?
- [ ] `MessageStore`, `ChannelMessageStore`, and `MessageGroupStore` used in the right scopes?
- [ ] Schema/dialect/query provider compatible with your Spring Integration version?
- [ ] Safe, versioned, approved serializers used for payloads/headers?
- [ ] Message size, retention, encryption, ACLs, and backups specified?
- [ ] Idempotent business keys in place distinguishing delivery attempts from processing attempts?

### 39.2. Transactions and ACKs

- [ ] Transaction opens **before `receive`/dequeue** when message removal must roll back?
- [ ] Store and business DB genuinely share the same `DataSource`/manager/transaction?
- [ ] Handlers execute synchronously inside the boundary with no accidental async thread breaks?
- [ ] Exceptions trigger rollback per policy without being swallowed?
- [ ] Ingress responses/ACKs emitted only after durable commit per contract?
- [ ] JMS/AMQP ACKs and Kafka offsets tested independently of DB transactions?
- [ ] Long remote API calls moved out of DB locks via outbox where possible?
- [ ] Timeouts transition to `UNKNOWN_OUTCOME` and reconcile before retrying?

### 39.3. Aggregation and Concurrency

- [ ] Policies defined for group IDs, release strategies, duplicate parts, and late arrivals?
- [ ] Completed groups and released outputs use durable handoffs?
- [ ] Locking/transaction strategy handles multiple pollers/instances?
- [ ] Reapers/expiration never silently delete pending or unknown business states?
- [ ] Queue ordering/priority understood accurately without assuming strict global FIFO?

### 39.4. Testing and Operations

- [ ] Tested ingress commit, dequeue rollback, handler failures, and crashes/restarts?
- [ ] Tested mismatched DB managers, async handoffs, and self-invocation?
- [ ] Tested broker redeliveries, HTTP timeouts after remote commit, and SFTP partial transfers?
- [ ] Tested schema migrations and reading messages serialized by prior releases?
- [ ] Tested multi-instance races and aggregation release failures?
- [ ] Dashboards track pending count/age, DB locks/pools, retries/DLQs, and remote outcomes?
- [ ] Runbooks ready for lost messages, jammed backlogs, and unknown outcomes?
- [ ] No incident-time purging/deleting of records without auditing and approval?

## 40. Summary

A **transaction-aware `MessageStore`** enables Spring Integration to persist and process messages durably and consistently within **verifiable transaction boundaries**. With a `QueueChannel` or aggregator backed by a JDBC store, the critical question is not merely "was it saved to the database?"—it is **whether store operations, receive/dequeue, business updates, group states, and completion markers commit and roll back across the right boundary**.

Across **File, SFTP, HTTP, JMS, AMQP, Kafka, and JDBC** flows, each adapter maintains its own ACK, transaction, retry, and connection lifecycle. **A local JDBC rollback does not trigger remote HTTP, file, or broker rollbacks.** Combine **persistent stores, transaction-aware pollers/handlers, stable idempotency keys, Inbox/Transactional Outbox, target confirmation/reconciliation, backlog monitoring, and fault-injection tests**.

A sound system does more than "never lose a queue row"—it proves **which messages were durably accepted, which side effects committed, which redeliveries are safe, and who owns unknown outcomes**. That is how to use a transaction-aware `MessageStore` to build recoverable, auditable, scalable integration flows without making false end-to-end exactly-once claims.
