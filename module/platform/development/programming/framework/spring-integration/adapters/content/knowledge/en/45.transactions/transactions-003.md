# Commit After Successful Outbound Processing in Spring Integration Adapters

> **Chapter:** Transactions  
> **Lesson:** Commit After Successful Outbound Processing  
> **Scope:** SPRING_INTEGRATION_ADAPTERS — connecting external systems with Spring Integration via inbound/outbound adapters, gateways, pollers, and `MessageChannel`; implementing File, SFTP, HTTP, JMS, AMQP, Kafka, and databases; managing message contracts, errors, transactions, and connection lifecycles.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Precisely define **commit after outbound success** and identify which layer "success" refers to: dispatch, handler, remote acceptance, durable write, or final business outcome.
2. Distinguish **database transaction commit, JMS session commit, AMQP acknowledgement, Kafka offset commit, and producer broker acknowledgement**: they are not a single unified transaction.
3. Map out the **source receive → outbound operation → confirm → commit/ack source** boundary and recognize what happens if the process dies at each point.
4. Explain why placing an outbound call inside a **`@Transactional`** method does not make HTTP/SFTP/brokers members of the DB transaction.
5. Choose suitable patterns for **`DirectChannel`, `ExecutorChannel`, `QueueChannel`, polling consumer, inbound gateway, and outbound adapter/gateway**.
6. Apply **transactional outbox/inbox, idempotency keys, reconciliation, state machines, bounded retries, and DLQ/parking** to achieve reliability when atomic cross-system commits are impossible.
7. Design appropriate commit/ack policies for **File, SFTP, HTTP, JMS, AMQP, Kafka, and JDBC**, preventing message loss or duplicate side effects.
8. Configure Java/Spring Integration examples at synchronous and database/outbox boundaries while recognizing where separate API/container integration is required.
9. Measure **outbound success, source ack, uncertain outcome, retry, and backlog** independently; design tests with fault injection before/after every commit boundary.

## 2. Why Is This a Transaction Problem?

A common flow:

~~~text
Inbound JMS message
    -> validate/transform
    -> HTTP outbound gateway calling ERP
    -> JDBC updating processing status
    -> acknowledge JMS message
~~~

The business requires: acknowledge the source message only once mandatory work has been processed or **durably persisted for continued processing**. Yet the word "success" can refer to very different events:

- The handler was invoked without throwing an exception.
- The HTTP client finished writing bytes.
- The HTTP server returned 200/201/202.
- A message was accepted or durably written by a broker per configuration.
- A file was created locally/remotely without a ready marker yet.
- The target database committed its transaction.
- Downstream consumers completed the entire business workflow.
- An outbox record committed with a worker guaranteed to publish it later.

**Never substitute a low-level success signal for the higher-level commitment demanded by the business contract.**

### Message Loss Scenario

~~~text
1. JMS consumer receives order-882
2. Spring Integration dispatches to ExecutorChannel
3. Sender receives successful send-to-channel result
4. Container acknowledges source
5. Process dies before outbound HTTP handler runs
6. No durable copy of order-882 remains
~~~

Successful in-memory dispatch **does not mean outbound succeeded**. If the source has already acked, the message can be lost.

### Duplicate Processing Scenario

~~~text
1. JMS consumer receives order-883
2. Outbound HTTP POST creates the order in ERP successfully
3. Process dies before JMS commit/ack
4. Broker redelivers order-883
5. HTTP POST is sent again
~~~

If ERP lacks idempotency/reconciliation, two orders may be created. **Committing after outbound success** reduces message loss risk but **does not eliminate duplicates**.

## 3. Multi-Level Definition of "Outbound Success"

| Level | Signal | What it proves | What it does NOT prove |
|---|---|---|---|
| L0 — Dispatch | `MessageChannel.send` returns true | Message accepted by channel per channel semantics | Remote received or processed it |
| L1 — Handler | `MessageHandler` returns normally | Handler code finished without throwing | Side effects in external systems committed |
| L2 — Transport ack | HTTP response, SFTP command result, broker producer ack/confirm | A protocol-level acceptance by the target | Final consumer finished business logic |
| L3 — Durable acceptance | Outbox/inbox record committed, broker persisted per guarantee | Durable storage per contract exists | Downstream business effect completed |
| L4 — Business completion | ERP order state confirmed, downstream operation committed | Target business work confirmed within contract scope | Source and target committed atomically |
| L5 — End-to-end closure | Business completion and source state properly recorded/acked | Flow reached closed state per criteria | No future redelivery can ever happen |

### Three Questions to Settle in Design

1. **What commits?** DB transaction, JMS session, Kafka offset, AMQP ack, file archive, row claim, or outbox event state.
2. **What confirmation do we wait for?** Outbound handler return, broker confirm, remote business state, or durable outbox.
3. **If the process dies right now, where is the record?** Source broker, input file, database inbox, outbox, retry queue, parking, or nowhere at all.

**Pragmatic goal:** a required message must always reside in at least one recoverable state until business-contract completion is reached; if duplicate deliveries occur, processing must be idempotent.

## 4. Lifecycle: Source → Outbound → Commit/Ack

~~~mermaid
sequenceDiagram
    participant S as Inbound source/container
    participant F as Integration Flow
    participant O as Outbound dependency
    participant C as Commit / acknowledgement
    S->>F: Message eventId=order-882
    F->>F: Validate and resolve operation
    F->>O: Outbound request
    O-->>F: Success per contract
    F->>F: Persist outcome if required
    F->>C: Commit/ack source per semantics
    C-->>S: Progress recorded
~~~

The diagram expresses **intended ordering**, not a claim that Spring Integration automatically creates a cross-system transaction.

### A Conditionally Safe Ordering

~~~text
RECEIVED
 -> VALIDATED
 -> OUTBOUND_ATTEMPTED
 -> OUTBOUND_CONFIRMED
 -> LOCAL_STATE_RECORDED
 -> SOURCE_ACKNOWLEDGED
 -> DONE
~~~

Condition: **`OUTBOUND_CONFIRMED` must be defined per business needs**, and intermediate steps must provide idempotency/recovery mechanisms. If outbound means enqueuing into a **durable outbox**, the source commit condition may be **`DURABLY_ACCEPTED_FOR_PROCESSING`** instead of waiting for the final system to execute.

### Source Commit vs. Target Commit

A JMS source can commit its session after an outbound HTTP call returns success. However, if the HTTP server already committed and then the JMS session commit fails, the two systems are still out of sync. There is no single atomic commit unless a genuine distributed transaction mechanism covers all involved resources; HTTP APIs and SFTP normally do not join a DB/JMS transaction manager by default.

## 5. "Commit After Success" Does Not Mean Exactly-Once

**At-least-once**: messages may be redelivered to prevent loss; consumers must tolerate duplicates.

**At-most-once**: certain early-ack decisions avoid repetition at the cost of potential message loss.

**Effectively-once business effect**: multiple deliveries/attempts still produce **one business effect** through idempotency, unique constraints, an inbox, deduplication, or reconciliation.

### Minimal Crash Matrix

| Crash point | Source acked? | Outbound completed? | Risk | Protection |
|---|---|---|---|---|
| Before processing | No | No | Redelivery | Idempotency / source persistence |
| After validate | No | No | Repeated parse/validation | Deterministic validation |
| After outbound request, before response | No | **Unknown** | Remote may have committed | Idempotency / reconciliation |
| After remote commit, before ack | No | Yes | Duplicate on redelivery | Stable business key |
| After ack, before outbound completion | Yes | No | **Lost work** | Do not ack early; durable handoff |
| After outbox commit, before publish | Possibly yes | Not published yet | Outbox backlog | Publisher retries |
| After broker confirm, before outbox marked DONE | Possibly yes | Broker received | Duplicate publish | Event ID + dedupe |
| After full completion | Yes | Yes | Secondary audit/metric error | Never rerun side effects for telemetry |

**You cannot solve both "loss" and "duplication" merely by reordering two statements.** You need durable state and idempotency.

## 6. Transaction Boundaries in Spring Integration

Spring Integration combines **`MessageChannel`, endpoints, handlers, and transaction managers**. A transaction may be attached to a polling consumer, message-driven adapter, or business service, yet its actual scope depends on:

- **`PlatformTransactionManager`** and the resources it manages;
- The thread holding the transaction context;
- Synchronous vs. asynchronous channels;
- Transaction interceptors / advice chains;
- Container / listener modes;
- Poller and message store semantics;
- Whether the outbound operation itself participates in the transaction.

### Transactions Do Not Automatically "Follow the Message"

In Spring, a traditional transaction binds to the **execution context/thread** of the transaction manager. Crossing an `ExecutorChannel` or another async boundary does not automatically carry the context as one unified transaction.

~~~text
Thread A:
  BEGIN JDBC tx
  -> DirectChannel
     -> JDBC handler using same datasource/transaction manager
  COMMIT/ROLLBACK

Thread A:
  BEGIN JDBC tx
  -> ExecutorChannel.send(message)
  COMMIT tx A

Thread B:
  -> outbound HTTP/SFTP/JDBC handler runs later
  (not automatically inside tx A)
~~~

**`DirectChannel`** keeps the call stack synchronous, yet does not make HTTP/SFTP join a JDBC transaction. **`ExecutorChannel`** makes premature ack/commit gaps particularly important to watch.

### TransactionScope and "Success" in a Flow

A handler returning normally does not automatically mean:

- The transaction manager committed successfully.
- A publisher confirm was received.
- A remote transaction executed.
- An `ErrorMessage` was not swallowed.
- The message was durably persisted.
- A request–reply gateway received its response.

To commit the source based on outcome, verify the **actual completion point** and exception path of the endpoint/container.

## 7. DirectChannel, ExecutorChannel, QueueChannel: Choosing the Right Boundary

| Channel | When `send` succeeds | When handler fails | Durability |
|---|---|---|---|
| **`DirectChannel`** | Handler may have already run on caller thread | Exception can propagate directly | None by default |
| **`ExecutorChannel`** | Work dispatched to an executor | Failure handled on worker thread / error flow | None by default |
| **`QueueChannel`** | Message enqueued per configuration | Consumer/poller requires failure handling | Depends on `MessageStore`/transaction |
| **`PublishSubscribeChannel`** | Dispatched per subscribers/config | Per-subscriber errors and successes need management | None by default |

### When Is DirectChannel Suitable?

When the **source consumer must wait for the outbound handler** before deciding to ack, a synchronous flow makes ordering easy to reason about. Even then, ensure:

- Per-attempt outbound timeouts and an overall deadline;
- Retry/backoff policies that do not pin threads indefinitely;
- Clarity on which exceptions propagate back to the container;
- Idempotency when outbound commits before source commit;
- A transaction manager matching local resources.

### ExecutorChannel: What If Async Is Mandatory?

Never ack the source based solely on **in-memory enqueuing** when at-least-once is required. Instead:

- **Durable handoff**: persist a message/outbox/job-store entry inside a verifiable transaction, then ack the source per protocol;
- Or withhold source acknowledgement until the worker reports **business/durable completion** via a supported coordination mechanism;
- Use error channels and durable retry records;
- Test app crashes, executor rejections, shutdowns, and backpressure.

### QueueChannel

`QueueChannel` is only durable when configured with a **`MessageStore`** and matching transactions/consumers. An in-memory `QueueChannel` does not survive restarts. If a consumer pulls a message from the queue and fails, define whether the message is requeued/rolled back or routed to parking.

## 8. Outbound Adapter vs. Outbound Gateway: Different Levels of Success

### Outbound Adapter: Usually One-Way

For example, File/SFTP/Kafka/AMQP outbound adapters can send a message without producing a **business reply**.

What the handler return means may simply be:

- The client API invocation finished;
- The message was submitted for async sending;
- Bytes were written to a local stream;
- The broker/remote acked at some level, **depending on configuration**.

**Never assume an outbound adapter returning equals final consumer business completion.**

### Outbound Gateway: Request–Reply

An HTTP outbound gateway typically sends a request, waits for a response, and returns the reply to the flow. However:

- HTTP 202 may mean **Accepted**, not job finished.
- HTTP 200 may confirm only request acceptance per contract, not the entire downstream pipeline.
- An HTTP timeout does not prove the target did not process the request.
- An error response can arrive **after a side effect already occurred**.

If the business contract requires **business completion**, the gateway may need a status query or final callback rather than checking only the HTTP status code.

## 9. Separating Outbound Success from Source Ack

A testable design should define two independent decisions:

~~~text
isOutboundAcceptedForBusinessContract(result)
canAcknowledgeSource(sourceContext, durableOutcome)
~~~

Examples:

| Outbound operation | Success per contract | Can ack source immediately? |
|---|---|---|
| JDBC update in matching transaction | Transaction commit confirmed | Yes when source ack coordinates properly and durable outcome suffices |
| HTTP POST creating order | Result reconciled by order ID | Yes if business state persisted or source protected |
| HTTP 202 async job | Job ID durably saved, workflow tracks it | Yes if contract permits accept-for-processing |
| Kafka publish | Future/producer ack succeeded at configured level | Depends on requirement: broker acceptance vs. consumer completion |
| AMQP publish | Publisher confirm per policy | Depends on requirement; confirm is not consumer DONE |
| JMS outbound send | JMS session send/commit per transaction | Depends on transaction boundaries and broker semantics |
| SFTP upload | Remote file confirmed/published per protocol | Yes if business state requires exactly that level |
| File outbound write | File safely published on filesystem | Yes if file delivery is the terminal goal |
| Async `ExecutorChannel` send | In-memory enqueue only | **No**, if durable outcome is required |

The answer to "can we ack?" must always tie back to the **specific source**, how the source retains messages, and the definition of the business outcome.

## 10. Pollers: Transactions and Commits During Periodic Polling

A polling consumer pulls messages from a `MessageSource` on a trigger and sends them to a handler/channel. Placing transaction advice properly around the poll operation enables a **local resource transaction** to govern receiving/marking the message.

However:

- A poller schedule **is not** a durable retry scheduler.
- Transaction advice applies only to resources supported by the transaction manager.
- A **File/SFTP poller** has no broker ack like JMS/Kafka.
- Metadata filters, remote file listings, and renames may lie outside DB transactions.
- If downstream handlers are async, the poll operation can finish before outbound runs.

### Ordering Example

~~~text
T0 poll row state NEW
T1 claim row -> PROCESSING
T2 route to HTTP outbound handler
T3 HTTP success (or durable job state)
T4 update row DONE
T5 commit JDBC transaction

If HTTP fails:
    roll back transaction when sharing the proper transaction boundary
    or persist RETRY_WAIT/PARKED per business policy
~~~

**Avoid holding a DB transaction open across slow HTTP calls whenever possible**: it increases lock duration, reduces throughput, and makes SLAs fragile. Usually prefer claim/lease + durable state + a separate outbound worker.

### Transaction Synchronization and Resource Lifecycle

Spring Integration offers **transaction synchronization** in suitable polling/adapter contexts to coordinate actions tied to transaction state, such as processing/moving resources on commit/rollback. Remember:

- Post-commit callbacks run within the local transaction lifecycle; they do not make SFTP renames or HTTP calls **atomic participants**.
- If a post-commit action fails, the preceding DB commit **is not rolled back by normal means**.
- Provide recovery, retries/idempotency, and auditing for post-commit actions.
- Exact API names and configuration depend on your Spring Integration version; verify the corresponding module/reference docs when implementing.

Do not treat transaction synchronization as magic that merges a file move and a JDBC commit into one distributed transaction.

## 11. Why Is `@Transactional` Insufficient for HTTP/SFTP?

Illustrative method:

~~~java
@Transactional
public void process(OrderMessage order) {
    orderRepository.save(order);
    httpClient.createErpOrder(order);
}
~~~

If HTTP already created the order and the database transaction rolls back, the remote order **is not automatically deleted**. If the database commits before HTTP, or HTTP times out after remote commit, the systems still end up out of sync.

### Two Orderings, Two Failure Modes

~~~text
A. DB first:
    BEGIN DB
    INSERT order
    COMMIT DB
    HTTP POST ERP   <-- can fail
    => local DONE while remote has no order

B. HTTP first:
    HTTP POST ERP success
    BEGIN DB
    INSERT status
    COMMIT DB       <-- can fail
    => remote has order, local has not recorded result
~~~

Do not just swap the order and call it "atomic." You need:

- A step-by-step state machine;
- Inbox/outbox depending on direction;
- Stable idempotency keys;
- Remote query/reconciliation;
- Step-appropriate retries;
- Compensation when business rules allow and genuinely support it.

**SAGA/compensation** is not ACID rollback. Compensation itself can fail and cannot undo every side effect, such as sent emails or settled fund transfers.

## 12. Commit After Outbound Success: Two Practical Strategies

### Strategy A — Synchronous Completion Before Source Ack

~~~text
Receive source message
    -> synchronous outbound handler
    -> receive success per contract
    -> persist local state
    -> ack/commit source
~~~

Suitable when:

- Outbound latency is predictable and fits within deadlines;
- The source container permits holding deliveries during processing;
- Threads/prefetch/consumer concurrency are sufficient;
- Idempotency handles source redelivery;
- Atomic cross-remote transactions are not demanded;
- Exceptions propagate cleanly back to the source on failure.

Limits: ties up source workers longer, dropped HTTP responses leave unknown outcomes, and source commit can still fail after remote success.

### Strategy B — Durable Acceptance Before Source Ack

~~~text
Receive source message
    -> validate
    -> persist inbox/job/outbox in local durable store
    -> confirm durable commit
    -> ack/commit source
    -> async outbound worker sends
    -> persist success / retry / unknown state
~~~

Suitable when:

- Outbound targets are slow or unstable;
- Work must survive restarts;
- Multiple destinations/brokers are involved;
- The source has strict timeouts or consumer limits;
- Retries need to span minutes or hours;
- Adequate storage, workers, and monitoring exist.

**Important:** Strategy B does not "ack after remote outbound success." It acks **after committing durable storage of the work obligation**. This can better satisfy reliability requirements if the business contract permits it.

## 13. Processing States and Terminal Outcomes Overview

~~~mermaid
flowchart TD
    A["RECEIVED"] --> V["VALIDATED"]
    V -->|"Invalid"| Q["INVALID / QUARANTINED"]
    V --> J["DURABLE_PENDING"]
    J --> O["OUTBOUND_ATTEMPT"]
    O -->|"Confirmed"| C["OUTBOUND_CONFIRMED"]
    O -->|"Retryable"| R["RETRY_WAIT"]
    R --> O
    O -->|"Outcome unknown"| U["OUTCOME_UNKNOWN"]
    U --> X["RECONCILE"]
    X -->|"Confirmed"| C
    X -->|"Not processed, safe retry"| R
    X -->|"Unresolved"| P["PARKED"]
    O -->|"Permanent"| Q
    C --> D["DONE"]
    D --> S["ACK / COMMIT source per contract"]
    J -.->|"Durable handoff policy"| S
~~~

These states are application-defined **domain states**, not a built-in Spring Integration enum. Commit/ack timing depends on Strategy A/B and source capabilities, and does not have to occur after `DONE` in every flow.

| State | Meaning | Can delete source copy? |
|---|---|---|
| `RECEIVED` | Newly received, not yet secured | No |
| `VALIDATED` | Data is valid | Not enough yet |
| `DURABLE_PENDING` | Work durably persisted with a recovering worker | Possible under Strategy B and source contract |
| `OUTBOUND_ATTEMPT` | Calling destination | Do not infer success |
| `OUTBOUND_CONFIRMED` | Verified success level | Persist state/ack accurately |
| `RETRY_WAIT` | Scheduled for durable retry | Possible if message durably saved |
| `OUTCOME_UNKNOWN` | Unclear if destination committed | Do not discard; must reconcile |
| `PARKED` | Stored for investigation, replayable | Possible when parking is durable and approved |
| `DONE` | Terminal business completion | Can ack/cleanup per contract |
| `INVALID/QUARANTINED` | Cannot process current payload | Cleanup source only when quarantine is durable and contract allows |

## 14. HTTP Outbound: A Response Is Not Necessarily a Business Commit

HTTP is a request–response protocol and does not directly join an internal database transaction in the usual way.

| Signal | Possible meaning | Handling decision |
|---|---|---|
| 200 OK | API returned success per contract | Inspect response/business state |
| 201 Created | Resource created per API semantics | Save remote ID and idempotency key |
| 202 Accepted | Request accepted for later processing | Save job ID, track completion |
| 204 No Content | Success with empty body | Treat as DONE only when contract permits |
| 409 Conflict | Possible duplicate or conflict | Reconcile business key/version |
| 429/503 | Rate-limited or unavailable | Backoff/rate limit/durable retry |
| 400/401/403 | Invalid input/auth/permission | Fix payload or credentials; do not blindly retry |
| Connect timeout | Connection likely not established | Conditional retry |
| Read timeout after POST | Server may have committed | `OUTCOME_UNKNOWN`, query/idempotency |

**HTTP 200 does not automatically prove** every async workflow at the target finished; the API contract defines the meaning of the response.

### POST Timeout After Remote Commit

~~~mermaid
sequenceDiagram
    participant S as Inbound source
    participant I as Integration handler
    participant E as ERP
    participant D as ERP DB
    S->>I: Order event-882
    I->>E: POST + Idempotency-Key=event-882
    E->>D: Commit order
    D-->>E: OK
    Note over E,I: Response lost
    I-->>S: Handler uncertain or failed
    S->>I: Redelivery event-882
    I->>E: Query status / retry same key if supported
    E-->>I: Existing confirmed result
    I->>S: Ack after local business contract met
~~~

If ERP does not support idempotency or status queries, transition to `OUTCOME_UNKNOWN` and reconcile before re-sending a side-effecting POST. **Never increase blind retries to solve unknown outcomes.**

### When to Commit the Source After HTTP?

Only after verifying:

1. The HTTP response satisfies the **business contract**, not merely client return.
2. Event ID/remote ID and state are saved or recoverable.
3. No mandatory follow-up obligation remains unsecured.
4. The source container supports ack/commit at that point.
5. If a crash occurs before source commit, idempotency prevents duplicates.

With an HTTP inbound gateway, source commit is not a broker ack; applications usually return a reply or `202 Accepted` with a **job ID + durable job record** for deferred processing.

## 15. JMS Inbound → Outbound: Session Commit After Handler

A JMS listener can use a transacted session or another acknowledgement mode. When the container receives a message, it can invoke the flow synchronously and commit the session after the handler completes normally; if the handler throws an error under proper transaction settings, the container rolls back and the broker redelivers.

~~~text
JMS broker
  -> transacted listener/container
  -> Spring Integration message
  -> DirectChannel
  -> outbound handler
       success -> container commits JMS session
       failure -> exception propagated -> rollback/redelivery
~~~

**This is a reference topology.** Actual behavior depends on the container factory, transaction manager, session mode, message-driven adapter, error flow, and how the handler exits. Not every JMS inbound setup exhibits identical rollback/redelivery behavior.

### Transaction Types

- **JMS local transaction** governs receive/send operations within a supported JMS session.
- **JDBC local transaction** governs the database for its transaction manager.
- With only two separate local transactions, commits are not atomic.
- **JTA/XA** can coordinate resource managers that genuinely support distributed transactions when properly configured; weigh recovery and operational complexity. **HTTP/SFTP do not automatically become XA participants.**
- An error flow or `RecoveryCallback` that **swallows exceptions** can trick the container into treating the message as handled even when outbound failed.

### Checkpoints

| Situation | What to verify |
|---|---|
| Handler returns normally | Under which mode does the container ack/commit? |
| Handler throws `MessagingException` | Does the exception reach the container or get intercepted? |
| JMS rollback | Under which policy does the broker redeliver/DLQ? |
| JMS commit fails after HTTP success | Does remote idempotency prevent duplicates? |
| Sending JMS outbound in same session | Do they truly share the same transaction manager/session? |
| DB commits, then JMS commit fails | Is there an inbox/outbox or reconciliation? |

For slow HTTP calls, **JMS → durable inbox/outbox → ack JMS → outbound worker** avoids tying up the source transaction for long durations. Still, acking after DB commit leaves a crash window; inbox deduplication makes redelivery safe.

## 16. AMQP Inbound: Consumer Ack Differs from Publisher Confirm

With AMQP/RabbitMQ:

- **Consumer ack:** acknowledges an inbound delivery per container mode.
- **Consumer nack/reject/requeue:** rejects the delivery; the broker may redeliver or dead-letter per configuration.
- **Publisher confirm:** broker confirms an outbound publish per guarantee/config.
- **Business completion:** final consumer applied the side effect and committed business state.

**Publisher confirm does not equal business completion.**

### Publish Flow Model

~~~text
AMQP source delivery
  -> validate + normalize
  -> outbound publish
  -> observe broker confirm as required
  -> durable local outcome
  -> ack source
~~~

If the client uses async callbacks/futures, a send call returning without throwing **does not mean** publisher confirm has arrived. Never ack the source on assumption when the contract requires broker acceptance.

### Crash Window

~~~text
1. Outbound publish reached target broker.
2. Process dies before AMQP source ack.
3. Source broker redelivers.
4. Same event is published again.
~~~

Solution: stable event IDs, outbox/inbox, and consumer deduplication. Publishing to broker B and acking broker A **is not automatically atomic**.

### Error Classification

- Transient: bounded retry/backoff or delayed queue.
- Invalid: quarantine/DLQ; avoid tight infinite requeue loops.
- Unknown outcome: reconciliation/parking.
- Verified duplicate already `DONE`: intentional no-op/ack.

If a handler makes four attempts per delivery and the broker redelivers three times total, there can be **12 handler invocations**. Per-invocation retry counts are not total delivery counts.

## 17. Kafka Inbound: Commit Offsets After the Right Guarantee Point

A **Kafka offset commit** only records consumer group read progress. It is neither an outbound HTTP/JDBC commit nor proof that the remote system finished processing.

| Layer | Role |
|---|---|
| Kafka consumer/client | Poll, heartbeat, partitions, offsets |
| Kafka listener container | Ack mode, error handler, seek/retry/DLT |
| Spring Integration inbound adapter | Converts records into Spring Messages |
| `MessageChannel` + handler | Route/transform/process |
| Producer/outbound adapter | Publish or call external systems |
| Business database | Persist business state |
| Inbox/outbox | Durable handoff/dedupe |

### Offsets and Outbound

~~~text
offset 100: invoice.created
offset 101: invoice.updated
offset 102: invoice.cancelled
~~~

If offset 100 is sent into an `ExecutorChannel` and the listener/offset commits before the handler calls HTTP, a crash loses the task. Approaches:

- **Synchronous processing** if latency and poll constraints allow; ack upon success.
- **Durable handoff** into inbox/outbox/job store, then commit the offset.
- **Container error handler / retry topology / DLT** per config when outbound fails.

### Kafka Transactions Do Not Cover Every Adapter

Kafka transactional producers/consumers support read-process-write within managed Kafka transactions. That **does not automatically include** HTTP POSTs, SFTP uploads, AMQP, or separate DB transactions.

### Ordering

If offset 100 is retrying HTTP while 101 completes quickly on another branch, business ordering can invert. You need partitioning/key strategies, sequential processing, aggregate-version guards, or orchestration. Retry topics/DLTs can also alter ordering.

### Async Producers

When a handler merely submits a send to the producer and returns, offset commit can happen before broker acknowledgement. You must track **future/callback completion** per your API/version and contract, or use an outbox so the source acks at **durable acceptance**.

## 18. JDBC Inbound/Outbound: Database Commits and Worker Leases

### JDBC Outbound Within the Same Database Transaction

When all mandatory side effects live in **one database managed by the same transaction manager**, they can commit atomically:

~~~text
BEGIN JDBC transaction
  validate rows
  UPDATE order_state
  INSERT processed_events(eventId)
  INSERT outbox_events(eventId, target, state=PENDING)
COMMIT JDBC transaction
~~~

If the transaction rolls back, none of those DB updates commit. However, an HTTP/SFTP call placed inside that block **does not roll back automatically**.

### JDBC Inbound Polling

A poller can fetch `NEW` rows and claim them:

~~~text
NEW -> CLAIMED -> PROCESSING -> DONE
                  |
                  +-> RETRY_WAIT -> PROCESSING
                  |
                  +-> OUTCOME_UNKNOWN
                  |
                  +-> PARKED
~~~

Requirements:

- Atomic claim using DB transactions, row locks, or leases;
- Worker owner and lease expiry;
- Durable `attemptCount` and `nextAttemptAt`;
- Stable `businessEventId` and unique constraints;
- Business deadline;
- Manual reconciliation;
- Never mark `DONE` before the business outcome is secured.

### Why Avoid Keeping DB Transactions Open Around Slow HTTP Calls?

Long lock durations hurt throughput and invite timeouts/deadlocks. Even if HTTP commits and JDBC fails to commit, reconciliation is still required. Usually **separate the transaction recording intent** from the worker making HTTP calls using an outbox/job state.

### Deadlock Retries

A transaction hitting a deadlock or marked rollback-only must roll back and retry in a fresh transaction. Do not blindly retry the whole workflow if an already-succeeded HTTP call would be repeated.

## 19. File Inbound: Commits Differ from Broker Acknowledgements

File inbound adapters and pollers **do not share the consumer ack semantics** of JMS/Kafka. "Acknowledgement" usually means file metadata, rename/move/archive/delete, or an application-defined business state store.

### Risk of Premature Archiving

~~~text
1. Poller sees invoice-882.ready.
2. App moves file to /processed.
3. HTTP outbound calls ERP and fails.
4. File is no longer in the inbound directory.
5. No durable retry record exists.
~~~

Even if the file still sits in the archive, **the next poll will not pick it up again**. Treating archiving as `DONE` can silently drop tasks.

### Reference Workflow

1. Pick up only fully published files (`.ready`/manifest).
2. Verify checksum, schema, and size; generate a stable event ID.
3. Stage the file in a recoverable location and create an inbox/job record.
4. Execute outbound synchronously or via a worker.
5. If `DONE`, archive; if failed, transition to `RETRY_WAIT`/`PARKED`/quarantine.
6. If moving the file after DB commit fails, handle via separate reconciliation/retry.
7. Never delete the source until at least one durable copy guarantees continued processing.

### Transaction Synchronization with Files

Spring Integration provides **transaction synchronization** mechanisms for suitable polling/flow contexts to execute actions tied to commit/rollback. Still, file renames/moves **are not atomic participants in a database transaction**.

If the DB commits and the post-commit action fails, you cannot roll back the DB commit normally. Persist state, support retries and idempotency, and maintain an operational runbook.

### Accept-Once Filters

Accept-once/metadata filters help avoid picking the same file twice at the adapter layer; they are not a business `DONE` flag. If the filter marks a file before an outbound failure, use controlled reset/recovery or replay from the job store.

## 20. SFTP Inbound/Outbound: Remote Outcomes Can Be Ambiguous

### SFTP Inbound

An SFTP poller lists/downloads files and emits messages. Never infer:

- Downloaded locally = downstream business `DONE`.
- Remote accept-once filter = transaction committed.
- Remote rename/delete = committed atomically with DB/broker.
- Session reconnect = source broker redelivery like JMS.

You need staging, stable file/record keys, checksums, metadata stores, and job state.

### SFTP Outbound Upload

~~~text
Render file
  -> upload remote temp name
  -> verify size/checksum/manifest if available
  -> remote rename/publish final name
  -> record OUTBOUND_CONFIRMED
  -> source ack/archive according to contract
~~~

If remote upload/rename succeeded yet the response dropped, the outcome is unknown. Before retrying, **query remote file status** by stable filename/checksum instead of unconditionally overwriting.

Remote renames can be atomic within a specific filesystem/protocol, yet **SFTP renames and DB/JMS source commits are not one atomic transaction**.

### When Remote Verification Fails

- Transition the event to `OUTCOME_UNKNOWN`/`PARKED`;
- Retain the source or durable job;
- Never auto-delete the file while obligations remain;
- Perform manual reconciliation or retry with idempotency guards if the contract allows;
- Log correlation IDs instead of credentials;
- Never disable host-key verification to work around errors.

## 21. One Outbound Event with Multiple Recipients: What Do We Commit?

An invoice must reach:

1. HTTP ERP;
2. Kafka analytics;
3. SFTP audit export.

If HTTP and Kafka succeed while SFTP fails, can we ack the source?

**There is no universal answer.** Your completion policy decides:

- **All required recipients confirmed:** `DONE` only when all mandatory recipients reach defined success levels.
- **Durable fan-out accepted:** ack source once all recipient jobs are durably saved; workers execute afterward.
- **Optional best-effort:** skip non-mandatory branches only if business policy allows and audits it.
- **Any-one success:** only if targets are genuinely interchangeable per contract.

### Per-Recipient State

~~~json
{
  "businessEventId": "tenant-A:invoice-882:v3",
  "requiredDestinations": [
    "ERP_HTTP",
    "ANALYTICS_KAFKA",
    "AUDIT_SFTP"
  ],
  "recipients": {
    "ERP_HTTP": "DONE",
    "ANALYTICS_KAFKA": "DONE",
    "AUDIT_SFTP": "RETRY_WAIT"
  },
  "overallState": "PARTIALLY_DELIVERED"
}
~~~

Retrying the entire fan-out can re-invoke HTTP/Kafka and cause duplicates. Store **per-recipient status**; retry only non-`DONE` recipients with stable event IDs and pinned route policies.

**Never represent a multi-destination workflow with a single `outboundSuccessful` boolean.** It cannot express `PARTIALLY_DELIVERED`, `OUTCOME_UNKNOWN`, `OPTIONAL_FAILED`, or `RETRY_WAIT`.

## 22. Transactional Outbox: Committing a Durable Handoff Before Source Ack

**Transactional outbox** solves the case where local data must change and a message must eventually be sent, without an atomic transaction spanning the database and HTTP/SFTP/brokers.

~~~mermaid
sequenceDiagram
    participant C as Inbound consumer
    participant DB as Local DB
    participant W as Outbox worker
    participant O as Outbound destination
    C->>DB: BEGIN transaction
    C->>DB: Write inbox, business state, outbox(PENDING)
    DB-->>C: COMMIT successful
    C->>C: Ack source per container contract
    W->>DB: Claim outbox job with lease
    W->>O: Send + stable idempotency key
    O-->>W: Confirm per protocol/contract
    W->>DB: Mark outbox DONE
~~~

### What Is Guaranteed and What Is Not

- **Source ack occurs after the database commit** of the durable inbox/outbox, not necessarily after remote business completion.
- The outbox worker can recover across restarts.
- If remote processing finished and the worker died before marking `DONE`, the job may be resent → requires idempotency/reconciliation.
- If source commit fails after DB commit, the broker may redeliver; the inbox unique key guards against duplicates.
- The database transaction is atomic only across resources **participating in that transaction**.

### Example Schema for PostgreSQL

~~~sql
CREATE TABLE inbox (
    event_id VARCHAR(180) PRIMARY KEY,
    payload_hash VARCHAR(128) NOT NULL,
    state VARCHAR(32) NOT NULL,
    accepted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE outbox (
    id BIGSERIAL PRIMARY KEY,
    event_id VARCHAR(180) NOT NULL,
    destination_alias VARCHAR(120) NOT NULL,
    payload_bytes BYTEA NOT NULL,
    state VARCHAR(32) NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMP,
    lease_owner VARCHAR(120),
    lease_until TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (event_id, destination_alias)
);
~~~

`BIGSERIAL`/`BYTEA` and the `UPSERT` syntax below are **PostgreSQL-specific**. If one event requires multiple operations to the same destination, the unique key must include operation/version/recipient identity; do not use an overly broad constraint that drops valid events.

### Responsibilities of Database State

- **Inbox** deduplicates source redeliveries.
- **Outbox** preserves the intent to send.
- **Lease/`nextAttemptAt`** lets workers recover jobs after crashes.
- **Unique business/recipient keys** prevent duplicate job creation.
- **Retention** never purges unfinished pending/retry items.
- **Encryption/ACL** protects payloads or payload references.

## 23. Java: Writing Inbox and Outbox in the Same Transaction

Example using Spring Framework `JdbcTemplate` with `@Transactional`:

~~~java
import java.util.Objects;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InboundAcceptanceService {

    private final JdbcTemplate jdbc;

    public InboundAcceptanceService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void accept(CanonicalEvent event) {
        int inserted = jdbc.update(
            """
            INSERT INTO inbox(event_id, payload_hash, state)
            VALUES (?, ?, 'ACCEPTED')
            ON CONFLICT (event_id) DO NOTHING
            """,
            event.eventId(), event.payloadHash()
        );

        if (inserted == 0) {
            String previousHash = jdbc.queryForObject(
                "SELECT payload_hash FROM inbox WHERE event_id = ?",
                String.class,
                event.eventId()
            );
            if (!Objects.equals(previousHash, event.payloadHash())) {
                throw new IllegalStateException(
                    "Same eventId but conflicting content");
            }
            return; // duplicate already accepted previously
        }

        jdbc.update(
            """
            INSERT INTO outbox(
                event_id, destination_alias, payload_bytes, state)
            VALUES (?, ?, ?, 'PENDING')
            """,
            event.eventId(),
            event.destinationAlias(),
            event.payloadBytes()
        );
    }

    public record CanonicalEvent(
            String eventId,
            String payloadHash,
            String destinationAlias,
            byte[] payloadBytes) {
    }
}
~~~

### Commit Boundary Explanation

- If `@Transactional` is invoked through a Spring proxy and the transaction manager matches the `DataSource`, both `INSERT`s share one JDBC transaction.
- If inserting into `outbox` fails, the transaction rolls back including the `inbox` insert.
- Duplicate `eventId`/hash can be treated as already accepted, **but** production code should verify the existing record has valid state/outbox entries and handle inconsistent states.
- Same `eventId` with a different payload hash is a conflict requiring investigation, not silent deduplication.
- Validate tenant, schema, `destinationAlias`, and payload prior to calling this method.
- Multiple recipients require inserting all corresponding outbox records in the same transaction, not just one as shown in the snippet.
- This snippet uses Java text blocks and PostgreSQL syntax; ensure compatible Java and dependency versions.

### Wiring into Spring Integration

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
public class DurableIngressFlow {

    @Bean
    IntegrationFlow acceptIngress(InboundAcceptanceService acceptance) {
        return IntegrationFlow.from("validatedInboundEvents")
            .handle(acceptance, "accept")
            .get();
    }
}
~~~

This flow does not manage **JMS/AMQP acknowledgement or Kafka offset commit** on its own. Configure the consumer/container so it acknowledges the source only after the **local database transaction commits** under the durable-acceptance contract.

### Practical Warnings

- Self-invocation bypasses `@Transactional` proxies in standard proxy-based transactions.
- `ExecutorChannel` does not carry the transaction context across worker threads automatically.
- A transaction manager wired to the wrong datasource causes DB writes outside the intended transaction.
- Catching a DB exception and returning normally can cause the container to ack without an outbox entry.
- Never store plaintext credentials/secrets in `payloadBytes`.

## 24. Outbox Worker: Send First, Then Mark DONE

A publisher runs decoupled from the inbound listener, picking up due `PENDING`/`RETRY_WAIT` outbox rows.

~~~text
Transaction 1 — Claim:
    select eligible jobs
    -> lease job / state IN_PROGRESS
    -> COMMIT DB

Outside DB transaction — Outbound:
    send HTTP/SFTP/JMS/AMQP/Kafka
    -> wait/observe confirmation required by business contract

Transaction 2 — Finalize:
    if confirmed -> mark DONE and remote reference
    if retryable -> increment attempts, RETRY_WAIT, nextAttemptAt
    if unknown -> OUTCOME_UNKNOWN, schedule reconciliation
    if permanent -> INVALID/PARKED with reason and owner
    -> COMMIT DB
~~~

### Why Keep Claims Short?

Never hold database transactions or row locks across slow HTTP calls. Doing so degrades throughput, raises contention, and causes transaction timeouts. **Claiming via a lease in a short transaction**, then performing network calls independently, is crash-recoverable across restarts.

### Multiple Workers Polling Concurrently

Use row locks / atomic `UPDATE` / leases supported by your database (such as `SELECT FOR UPDATE SKIP LOCKED` on supported engines) to prevent two workers from processing the same job. Never simply `SELECT PENDING` and send without claiming.

### Crash Windows

| Crash point | Durable state | Recovery |
|---|---|---|
| Before claim | `PENDING` | Another worker claims it |
| After claim, before send | `IN_PROGRESS` + lease | Lease expires → re-drive |
| After remote success, before `DONE` | Still `IN_PROGRESS` or `UNKNOWN` | Query/idempotency; possible duplicate attempt |
| After `DONE` commit | `DONE` | Never resend to completed recipient |
| During retry-state update | Depends on DB commit | Re-evaluate from durable state |

**An outbox does not guarantee exactly-once HTTP/SFTP delivery.** It preserves send intent and enables at-least-once attempts; idempotency/reconciliation ensures a single business effect.

## 25. Outcome Unknown: It May Have Succeeded Without an ACK

Common ambiguous failures:

- HTTP POST committed, then client read timed out.
- SFTP rename completed, then connection dropped before response.
- AMQP publish reached broker, then publisher confirm was lost.
- Kafka record reached broker, then process died before callback.
- JDBC commit persisted on server, then client lost connection waiting for result.
- JMS send/commit interrupted by network drop.

### Classification Flow

~~~text
OUTBOUND_ATTEMPT
    |
    +-- confirmed failure before side effect -> RETRY_WAIT
    |
    +-- confirmed success per contract -> OUTBOUND_CONFIRMED
    |
    +-- uncertain outcome -> OUTCOME_UNKNOWN
                                |
                                +-> query remote status
                                +-> confirmed -> DONE
                                +-> confirmed not processed -> safe retry
                                +-> still unknown -> PARKED/triage
~~~

Never classify every timeout as having had no side effect. Each protocol and business operation needs an **outcome reconciliation contract**.

### Event Identity

~~~json
{
  "businessEventId": "tenant-17:order-882:v3",
  "destinationAlias": "billing-erp",
  "idempotencyKey": "tenant-17:order-882:v3",
  "operation": "order.upsert",
  "lastAttempt": 4,
  "lastOutcome": "UNKNOWN",
  "reconciliationState": "QUERY_REMOTE",
  "deadlineAt": "2026-11-24T00:00:00Z"
}
~~~

An idempotency key only works if the **partner supports it** per contract. Sending an `Idempotency-Key` header cannot force a non-idempotent API to behave idempotently.

## 26. Retry, BackOffPolicy, and RequestHandlerRetryAdvice

| Mechanism | Purpose | Caution |
|---|---|---|
| `RetryTemplate`/`RetryPolicy` | Select retryable exceptions and `maxAttempts` | Do not blindly retry invalid/auth errors |
| `BackOffPolicy` | Control delay between attempts | Does not replace timeouts/deadlines |
| `RequestHandlerRetryAdvice` | Retry invocation of the attached handler | Does not retry the whole flow unless handler spans too much |
| Broker redelivery | Source delivers message again | Multiplies nested attempts |
| Durable delayed retry | Retry via DB/queue after an interval | Requires leases and idempotency |
| `RecoveryCallback` | Handle exhausted retries | Returning normally may trigger ack |
| Circuit breaker / bulkhead | Isolate failing dependencies | Does not replace durable recovery |

### Exception-Swallowing Anti-Pattern

~~~java
// Illustrative snippet; not complete standalone code.
advice.setRecoveryCallback(context -> {
    log.error("Remote failed", context.getLastThrowable());
    return null; // May be treated as handler success.
});
~~~

If the container sees only a normal handler return, it may ack/commit the source **before the message is safely preserved**.

Propagate terminal failures back to the container when the source needs rollback/redelivery, or **successfully persist `PARKED`/DLQ/durable retry state** before allowing the source to complete per contract.

### Multi-Layer Retries

~~~text
Broker deliveries: 5
  -> handler advice attempts: 4
      -> HTTP client attempts: 2
~~~

This can produce up to **5 × 4 × 2 = 40 HTTP requests** for one business event in the worst case. Set an overall retry budget, per-attempt timeouts, a business deadline, and a stable event ID. Never mistake one handler's `maxAttempts` for total attempts across all layers.

## 27. Transaction Synchronization Does Not Replace Distributed Commits

Spring Integration supports transaction-aware polling/advice and transaction synchronization in appropriate contexts. Use them to coordinate:

- Moving/renaming files when a local DB transaction succeeds;
- Waking up an outbox publisher after commit;
- Recording post-commit telemetry;
- Cleaning up separate resources on rollback.

### Illustrative Sequence

~~~text
BEGIN DB transaction
   INSERT inbox and outbox
COMMIT DB transaction
   afterCommit callback: trigger publisher or move file
~~~

**A failing after-commit callback does not roll back an already-committed local DB transaction.** Relying solely on callbacks to publish risks losing outbound events if the process crashes after DB commit and before the callback executes.

### Stronger Design

1. Persist the **durable outbox row before commit**.
2. `afterCommit` may wake the worker for lower latency.
3. Outbox/recovery polling must still work even if the callback never runs.
4. File moves/renames have their own retries and reconciliation.
5. Never view `afterCommit` as an atomic transaction spanning JDBC and HTTP/SFTP.

### XA/JTA and 2PC

When resource managers support JTA/XA and a transaction coordinator is properly configured, certain JMS/DB operations can commit atomically within the **participating resource scope**. However:

- Operational recovery and heuristic outcomes are complex;
- Timeouts, throughput, and provider support must be verified;
- HTTP/SFTP and most external APIs **are not XA participants**;
- External business completion may still require reconciliation.

**Outbox/inbox is usually more practical across heterogeneous protocols**, provided you embrace at-least-once delivery and guard against duplicates.

## 28. Security, Privacy, and Reliability of Transactional Messages

- Never log bearer tokens, passwords, SFTP private keys, or broker credentials.
- If inbox/outbox tables store payloads containing PII, enforce encryption, ACLs, and retention policies.
- Use payload references and redacted metadata in error logs.
- Keep idempotency keys deterministic without leaking secrets.
- Validate tenant and `destinationAlias` prior to outbound execution.
- Secure reconciliation endpoints with least privilege and rate limiting.
- Filter headers when bridging HTTP/JMS/Kafka; do not leak `Authorization`/cookies.
- Apply strict access control and retention to DLQ/parking matching sensitive business data.
- Never clean up source copies before completion or durable recovery is assured.
- Assign owners, deadlines, alerts, and valid closure/cancellation paths to `OUTCOME_UNKNOWN`; never leave items hanging forever.

### Governance Process

For financial or compliance-critical operations, changes to `DONE`/source-ack criteria require review and regression tests. Never alter an error handler to swallow exceptions just to show zero errors on a dashboard; that causes silent data loss.

## 29. Observability: Measuring Commit, Ack, and Outbound Separately

A dashboard counting only "handlers that did not throw" cannot prove commits are sound. Separate **source receipt**, **durable acceptance**, **outbound send**, **broker/remote confirmation**, **source commit**, and **business `DONE`**.

| Metric | Definition | Purpose |
|---|---|---|
| **`inbound_received_total`** | Total source deliveries per adapter | Compare against business events |
| **`durable_acceptance_total`** | Events/jobs committed to inbox/outbox | Verify durable handoff |
| **`source_ack_total`** | Confirmed source acks/commits | Detect premature acks |
| **`source_ack_failures_total`** | Failed ack/commit attempts | Predict redeliveries |
| **`outbound_attempts_total`** | Total operation invocations | Measure retry load |
| **`outbound_transport_success_total`** | Transport confirms per contract | Avoid confusing with business success |
| **`outbound_business_confirmed_total`** | Confirmed business effects | Completion metric |
| **`outbox_pending_count`** | Jobs in `PENDING`/`RETRY_WAIT` | Backlog size |
| **`outbox_oldest_age_seconds`** | Age of oldest pending job | SLO aging |
| **`outcome_unknown_total`** | Unverified remote outcomes | Reconciliation queue |
| **`reconciled_total`** | Unknown outcomes resolved | Recovery effectiveness |
| **`dead_letter_or_parked_total`** | Durably persisted terminal failures | Operational triage |
| **`duplicate_delivery_total`** | Redeliveries from source | Duplicate message tracking |
| **`idempotency_dedupe_hits_total`** | Duplicate operations prevented | Replay safety |
| **`duplicate_business_effect_total`** | Verified duplicated side effects | Critical quality indicator |
| **`commit_latency_seconds`** | Wait time for local transaction commit | Find DB bottlenecks |
| **`destination_ack_latency_seconds`** | Publisher/remote ack latency | Spot dependency issues |
| **`delivery_to_done_latency_seconds`** | Source receipt → business `DONE` latency | Measure SLO |
| **`ack_without_durable_outcome_total`** | Acks lacking `DONE` or valid durable obligation | Silent-loss alarm |

### Correlation and Structured Logs

Each event should capture:

- Stable `businessEventId`;
- `correlationId`/`traceId`;
- Source protocol/topic/queue/file alias (without exposing secrets);
- `destinationAlias`/operation;
- `attemptIndex`, `brokerDeliveryCount` where known;
- Distinct `sourceAckState` and `outboundState`;
- Transaction ID or appropriate logical processing ID;
- `routePolicyVersion`/`idempotencyKeyRef`;
- `terminalOutcome` and `reasonCode`;
- Timestamps for `COMMIT`, `ACK`, `CONFIRM`, and `DONE`.

### Cardinality

Never use `eventId`/`orderId`/`traceId` as metric labels; put those in logs/traces. Keep metric labels to adapter, bounded-cardinality destination aliases, `errorCategory`, and `finalOutcome`.

### Key Alerts

**Increasing outbound attempts** without **rising business `DONE`** means retries are masking failures. **Rising source acks** without matching **durable acceptance + business `DONE`** indicates premature source acks. **Aging unknown-outcome backlogs** indicate reconciliation is falling behind.

## 30. Error Handling: Do Not Ack Just Because an Error Flow Ran

Spring Integration provides **`ErrorMessage`**, **`errorChannel`**, endpoint advice, and distinct exception propagation across sync vs. async boundaries.

### Common Misconceptions

- An `ErrorMessage` sent to `errorChannel` **does not mean** the error was durably persisted.
- An error flow logging a message **does not mean** the source message can be acked.
- A `RecoveryCallback` returning null **does not mean** outbound completed.
- `NullChannel` simply discards messages; it is not a DLQ or business recovery.
- A message enqueued onto an in-memory `QueueChannel` **is not guaranteed** to survive restarts.
- An async HTTP callback reporting accepted **does not prove** remote business `DONE`.

### Error Classification Before Commit

~~~mermaid
flowchart TD
    A["Outbound attempt"] --> D{"Result category?"}
    D -->|"Confirmed success"| S["Persist DONE or confirmed reference"]
    D -->|"Transient fail"| R["Bounded retry or durable RETRY_WAIT"]
    D -->|"Permanent invalid"| Q["Quarantine / manual repair"]
    D -->|"Outcome unknown"| U["Reconciliation state"]
    D -->|"Security/config"| X["Escalation, pause destination"]
    S --> C{"Source completion contract met?"}
    R --> C
    Q --> C
    U --> C
    X --> C
    C -->|"Durable obligation or DONE"| K["Ack/commit per protocol"]
    C -->|"Not safely preserved"| E["Propagate/rollback; source recovery"]
~~~

**Note:** This diagram does not endorse acking when `RETRY_WAIT`/`UNKNOWN` exists only in memory. A **durable record must be committed** before taking the ack branch per contract.

### Failures When Writing to Parking/DLQ

If persisting to durable parking fails, never swallow the exception and ack the source. Propagate so the source redelivers, or use a verified fallback store. An `ErrorMessage` on an in-memory channel **is not enough**.

## 31. End-to-End Commit/Ack Test Matrix

Every test must track **when the source commits, outbound effects, durable state, and crash points**. Below is a multi-adapter test suite.

| ID | Scenario | Expected outcome |
|---|---|---|
| T01 | `DirectChannel` handler outbound succeeds | Source acks properly after business/durable outcome |
| T02 | `DirectChannel` handler throws exception | No false ack; rollback/recovery per source |
| T03 | `ExecutorChannel` enqueues in memory, then process dies | Test detects message-loss window |
| T04 | Durable inbox/outbox commits before source ack | Outbound job survives restart |
| T05 | DB commits inbox, source ack fails | Redelivery is deduplicated |
| T06 | DB `INSERT` outbox fails | Inbox transaction rolls back, source unacked |
| T07 | Duplicate `eventId` with matching hash | No duplicate outbox job created |
| T08 | Duplicate `eventId` with differing payload/hash | Conflict raised for investigation |
| T09 | Outbox worker claims job then crashes before send | Lease expiry enables retry |
| T10 | Outbox worker calls remote then crashes before `DONE` | Idempotency/reconcile prevents duplicate business effect |
| T11 | Two workers poll same job concurrently | Atomic claim prevents unintended double-send |
| T12 | Outbox record `DONE`, then restart | Not resent automatically |
| T13 | HTTP 200 per synchronous contract | Persist completion, then ack source |
| T14 | HTTP 202 async job | Persist job ID; do not mark final business `DONE` |
| T15 | HTTP POST commits, then response times out | `OUTCOME_UNKNOWN`, query/idempotency |
| T16 | HTTP 503/429 | Backoff/rate limit, budgeted retries |
| T17 | HTTP 401/403 | No infinite retries; owner triage |
| T18 | JMS transacted listener succeeds | Session commits per verified mode |
| T19 | JMS handler fails | Rollback/redelivery per container contract |
| T20 | JMS commit fails after HTTP success | Duplicates prevented |
| T21 | JMS + DB as two separate local TXs | Test crash window between the two commits |
| T22 | AMQP inbound handler succeeds | Acks per expected mode/timing |
| T23 | AMQP error flow swallows exception | Negative test catches ack lacking outcome |
| T24 | AMQP publisher confirm delayed | Do not treat send return as confirm if contract requires it |
| T25 | AMQP publish succeeds, confirm lost | Outcome reconciliation and dedupe |
| T26 | AMQP continuously requeues invalid payload | No tight infinite hot loop |
| T27 | Kafka offset commits before async outbound completion | Negative test exposes silent loss |
| T28 | Kafka offset commits after durable handoff | Safe replay across restarts |
| T29 | Kafka producer async callback fails | Outbox transitions to `RETRY_WAIT`/`ERROR` |
| T30 | Kafka partition ordering | Version/order guard across branches |
| T31 | Kafka transaction handles Kafka→Kafka | Does not extrapolate to HTTP/JDBC |
| T32 | JDBC deadlock | Retries in fresh transaction properly |
| T33 | JDBC transaction marked rollback-only | Never falsely marked `DONE` |
| T34 | JDBC poller claims row then crashes | Lease expiry/recovery |
| T35 | JDBC commits, HTTP not yet sent | Outbox publisher picks it up |
| T36 | File inbound marked accept-once before outbound failure | Source metadata does not lose job |
| T37 | File archive/move fails after DB commit | Separate reconciliation; no fake DB rollback |
| T38 | File not yet completely published | `.part` not treated as ready |
| T39 | SFTP download interrupted | Partial staging/transfer retry |
| T40 | SFTP upload completes, rename response lost | Remote state reconciliation |
| T41 | SFTP host-key mismatch | Security failure; no ack/data loss |
| T42 | Multiple recipients: two `DONE`, one `RETRY_WAIT` | Retry only the pending recipient |
| T43 | `RecoveryCallback` returns null before parking saved | Negative test must fail |
| T44 | Writing DLQ/parking fails | Does not ack and drop source |
| T45 | Nested broker/handler/client retries | Total attempts counted and capped |
| T46 | Business deadline expires before next retry | `CANCELLED`/`PARKED` per contract |
| T47 | Unknown outcome lingers too long | Alert/owner/runbook triggered |
| T48 | Outbox payload contains PII | Encryption, ACL, retention enforced |
| T49 | Error logs contain tokens | Redacted, no credentials leaked |
| T50 | Source ack and business `DONE` metrics diverge | Alert catches boundary mismatch |
| T51 | Recovery after faulty deployment | Jobs preserved and route policy pinned |
| T52 | Outbound destination disabled | Event not dropped; durable pause/parking |
| T53 | Partner idempotency key TTL expires | No blind retry past TTL; reconcile |
| T54 | `TransactionSynchronization` `afterCommit` never runs | Outbox poller still publishes |
| T55 | Local DB commits, JVM crashes immediately | Outbox durable; source replay deduped |
| T56 | Consumer concurrency scales 10x | No duplicates from race/claim |
| T57 | Unexpected broker redelivery | Single business effect via inbox/idempotency |
| T58 | Source acked, audit metric not written yet | Never rerun side effect solely for telemetry |
| T59 | Outbox schema migration during deploy | Backward-compatible job processing |
| T60 | Manual redrive from `PARKED` | Approval, audit, idempotent outcome |

### Detailed Crash-Point Testing

Inject faults at:

1. After source receive, before inbox acceptance;
2. After inbox insert, before outbox insert;
3. After outbox DB commit, before source ack;
4. After source ack, before outbox worker claim;
5. After worker claim, before remote call;
6. After remote commit, before response;
7. After response success, before outbox marked `DONE`;
8. After outbox `DONE`, before source cleanup/metrics;
9. After DLQ write, before source ack;
10. After source redelivery, before inbox dedupe decision.

At each point, answer: **where does the message still exist, can it be redelivered, can it produce a duplicate effect, and what terminal state must result?**

### Suitable Test Harness

- Unit tests for `RetryPolicy`, state transitions, and idempotency classification.
- Integration tests for DB transactions with rollbacks and unique constraints.
- Integration tests for JMS/AMQP/Kafka container ack modes and failure handlers.
- Fake HTTP server for post-commit timeouts, 202, 429, and 503.
- SFTP test server for partial uploads and unknown rename outcomes.
- Fault-injection/chaos tests for crashes at commit boundaries.
- Contract tests with partners covering idempotency keys, responses, and confirm semantics.
- Load tests covering backpressure, long-running retries, and worker leases.

Do not assert only mock call counts; inspect **durable database state, source redeliveries/offsets, and remote business effects**.

## 32. Case Study: JMS → HTTP ERP → JDBC → AMQP

### Context

A Spring Integration application receives orders from a JMS broker, calls an ERP HTTP service, updates PostgreSQL, and publishes a notification over AMQP.

~~~text
JMS inbound (transacted listener)
    -> validate/normalize
    -> HTTP outbound gateway ERP
    -> JDBC update status
    -> AMQP notification
    -> JMS source commit/ack
~~~

Business requirements:

- One business event creates at most **one** ERP order.
- No lost messages when ERP, DB, or AMQP is down.
- Do not block JMS consumer threads for hours.
- AMQP failure must never cause ERP to be called again.
- Trace any source event through to `DONE`/`PARKED`.
- Ack the source per contract, not merely on in-memory channel send.
- Restarts/deployments must not lose pending work.

### Incident Timeline

| Time | Event | What to analyze |
|---|---|---|
| 09:00 | JMS receives `order-882` | Source session/ack boundary |
| 09:01 | ERP POST commits | Remote business state |
| 09:02 | HTTP response lost | `OUTCOME_UNKNOWN` / idempotency |
| 09:03 | JMS handler throws exception | Rollback / redelivery |
| 09:04 | JMS redelivers old `eventId` | Deduplication |
| 09:05 | JDBC update deadlocks | Retry in fresh transaction |
| 09:06 | AMQP broker unavailable | Outbox `RETRY_WAIT` |
| 09:07 | App restarts while outbox `IN_PROGRESS` | Lease / recovery |
| 09:10 | Publisher confirm arrives late | Do not mark `DONE` prematurely |
| 09:11 | Publish succeeds, process dies before `DONE` | Duplicate publish |
| 09:12 | Manual replay | Approval / idempotency / route policy |

### Exercise 1: Find Flaws in the Synchronous Flow

A proposed flow:

~~~text
JMS message
  -> HTTP POST ERP
  -> JDBC UPDATE order_status
  -> AMQP publish
  -> return success
~~~

List at least six crash windows or unexpected behaviors: HTTP timeout after commit, JMS ack failure, lost AMQP confirm, database deadlock, error handler swallowing exceptions, and async publisher handling.

**Hint:** No single atomic transaction spans HTTP + JDBC + AMQP + JMS. When a later step fails, retrying the whole flow repeats earlier steps. Handler return does not guarantee broker confirm arrived.

### Exercise 2: Designing Durable Acceptance

~~~mermaid
flowchart TD
    J["JMS inbound"] --> V["Validate + normalize eventId"]
    V --> I["DB transaction: inbox + outbox"]
    I -->|"Commit success"| ACK["JMS ack per container contract"]
    I -->|"Commit fail"| RB["Exception propagated / rollback"]
    I --> W["Outbox worker claim"]
    W --> E["ERP HTTP step"]
    E --> C{"Outcome?"}
    C -->|"Confirmed"| S["ERP_CONFIRMED"]
    C -->|"Transient"| R["RETRY_WAIT"]
    C -->|"Unknown"| U["RECONCILE / PARKED"]
    S --> O["DB transaction: status + AMQP outbox"]
    O --> A["AMQP publisher"]
    A -->|"Confirm"| D["AMQP_DONE"]
    A -->|"Fail"| P["Delayed retry"]
    P --> A
    D --> F["Business DONE"]
~~~

Conceptual diagram—this does not mean everything runs in one JDBC transaction. If JMS source ack fails after DB commit, inbox deduplication must recognize the redelivery.

### Exercise 3: Comparing Two Commit Policies

**Policy A — JMS commits after ERP and AMQP succeed:** aligns closely with synchronous completion contracts, yet holds deliveries open longer; an AMQP outage can force rollback and redelivery, re-invoking already-succeeded HTTP calls. Requires idempotency and per-step state.

**Policy B — JMS commits after durable inbox/outbox DB commit:** source is acknowledged once the processing obligation is durably stored; workers handle outbound afterward. Requires leases, monitoring, retry limits, retention, and manual replay controls.

**Question:** Which policy should you choose if ERP regularly takes 8–15 seconds and AMQP occasionally goes down for 30 minutes? State the business contract and operational controls that make Policy B acceptable.

**Hint:** Policy B is usually suitable when a reliable durable job store and runbook are approved; this is not acking after remote completion, but acking after **durable acceptance**.

### Exercise 4: Timeout After ERP Commit

1. Preserve stable `businessEventId` across retries/redeliveries.
2. Send the same idempotency key if ERP supports it.
3. On read timeout, transition to `OUTCOME_UNKNOWN`.
4. Worker queries ERP by idempotency key / order ID.
5. If confirmed, persist remote order ID and `ERP_CONFIRMED`.
6. If confirmed not processed, retry POST per contract.
7. If still unknown, transition to `PARKED` with owner/deadline; do not blindly send a create-order command.

### Exercise 5: AMQP Outage Without Re-Triggering ERP

After `ERP_CONFIRMED`, insert a **notification outbox** row in the DB. The AMQP publisher uses a stable `eventId` and tracks publisher confirms. When the broker is down, record `RETRY_WAIT` without calling ERP again.

If publishing to the broker succeeds yet the confirm is lost, the publisher may resend; downstream consumers must deduplicate. A broker confirm verifies broker acceptance per contract, not consumer business completion.

### Exercise 6: Top Ten Priority Tests

1. ERP returns 503, then succeeds.
2. ERP commits, then response drops.
3. JMS redelivery after ack failure.
4. Inbox duplicate with matching hash.
5. Inbox duplicate with differing hash.
6. JDBC deadlock.
7. AMQP down for 30 minutes.
8. Lost publisher confirm.
9. Process crashes between outbox claim and send.
10. Process crashes after remote success before `DONE`.

Also include manual redrive, cross-tenant access control, invalid schemas, retention policies, and concurrency.

### Expected Results

You do not have to prove duplicate deliveries are impossible; you must prove:

- Every source event has a durable record or remains at the source until the obligation is secured.
- No business effect is duplicated thanks to idempotency/reconciliation.
- Jobs are not lost on restart.
- `OUTCOME_UNKNOWN` has an owner and closure mechanism.
- Source ack/commit matches durable acceptance.
- Exceptions are never swallowed before recovery is persisted.

## 33. Anti-Patterns of "Commit After Outbound"

| Anti-pattern | Consequence | Fix |
|---|---|---|
| Ack source after sending to `ExecutorChannel` | Messages lost on crash | Durable handoff / await completion |
| Equating handler return with remote commit | False success | Verify protocol/contract |
| Treating HTTP 202 as business `DONE` | Async job unfinished | Persist job ID and track |
| Blindly retrying HTTP POST timeouts | Duplicate orders | Idempotency / reconcile |
| Holding JDBC TX across slow HTTP calls | Locks/timeouts, still non-atomic | Outbox and worker |
| Retrying whole flow on AMQP failure | Re-calls ERP | Per-recipient/per-step states |
| `RecoveryCallback` returning null before parking | False ack | Rethrow or durable recovery |
| Treating `ErrorMessage` to `NullChannel` as DLQ | Cannot replay | Durable DLQ/parking |
| Committing Kafka offset before send future completes | Lost tasks | Await ack or durable handoff |
| Assuming Kafka exactly-once = HTTP exactly-once | Misunderstood TX scope | Remote idempotency |
| Equating AMQP publisher confirm with consumer `DONE` | Wrong completion metrics | Multi-level contracts |
| Treating JMS session commit = JDBC commit | Two non-atomic local TXs | Proper XA or inbox/outbox |
| Moving file to processed before outbound | Cannot re-poll source | Staging/state/late archive |
| Treating accept-once metadata as `DONE` flag | Record lost on downstream error | Inbox/business state |
| Assuming SFTP rename timeout means definite failure | Remote may have published | Reconcile remote state |
| Writing outbox solely in `afterCommit` callback | Crash window loses event | Insert outbox before commit |
| Outbox lacking leases/atomic claims | Two workers process same job | Claim inside transaction |
| Deleting outbox on send attempt before confirm | Loses reconciliation ability | `UNKNOWN`/`RETRY_WAIT` |
| Deduplicating by `MessageHeaders.ID` | UUID can change on replay | Stable business event ID |
| Ignoring payload mismatch on matching `eventId` | Corrupt data masked | Hash/version checks |
| Infinite retries inside source transaction | Thread/partition starvation | Bounded + delayed retries |
| Missing deadlines | Unbounded aging backlog | Expiry/cancel policy |
| Logging full `ErrorMessage` headers | Leaks credentials/PII | Redact and log safely |
| Skipping crash tests after remote commit | Duplicate effects in prod | Fault-injection testing |
| Counting broker ack as `DONE` when consumer work is required | Misleading SLO reporting | Contract-aligned completion metrics |
| Multi-layer retries without an overall budget | Retry amplification | End-to-end budget |
| Unapproved manual redrive | Duplicate or misrouted sends | Audit/permissions/idempotency |

### A Design Review Gate

Before any change to ack/commit semantics, require a **source → handler → outbound → durable state → source ack** diagram paired with at least one crash test between every adjacent pair of steps. If you cannot point to where a surviving copy lives on crash, the design is not reliable enough.

## 34. Runbook: Outbound Succeeded, Source Commit Failed

### Symptoms

- Remote ERP already created the order.
- JMS/AMQP delivery remains unacked or Kafka offset uncommitted.
- Broker redelivers the same `businessEventId`.
- Logs show commit/ack exceptions.
- Remote order exists while local state or source progress disagrees.

### Resolution Steps

1. **Preserve evidence:** `eventId`, `correlationId`, `destinationAlias`, source metadata, timestamp, remote ID.
2. **Stop blind retries:** do not issue new POSTs just because the source redelivered.
3. **Query remote state:** using stable order ID/idempotency key; persist confirmed outcome.
4. **Inspect inbox/outbox:** verify matching `eventId`/version/hash and current job state.
5. **Classify:** source redelivery, remote duplicate, uncertain local DB commit, or source ack failure.
6. **Recover:** if `DONE` is verified → dedupe/no-op; if a step is missing → retry that specific step; if unknown → `PARKED`.
7. **Reconcile source:** ack/offset/lease per protocol; never reset offsets blindly.
8. **Verify end-to-end:** one business effect, no orphaned jobs.
9. **Audit:** owner, reason, decision, remote reference, and approval for any manual redrive.
10. **Post-mortem:** add negative/crash-point tests and refine transaction boundaries if needed.

Never delete broker messages just to make dashboards green, never mistake error logs for recovery, and never mark `DONE` merely because a handler ran once.

## 35. Safe Commit/Ack Implementation Checklist

- [ ] Clearly defined **outbound success level** per business contract, not merely handler return.
- [ ] Identified **which resources commit**: JDBC, JMS session, Kafka offset, AMQP consumer ack, File/SFTP lifecycle, outbox state.
- [ ] Drawn source → processing → outbound → durable state → source acknowledgement flow.
- [ ] Identified `DirectChannel`/`ExecutorChannel`/`QueueChannel` and transaction thread boundaries.
- [ ] When async, source never acks based on in-memory enqueuing if at-least-once is required.
- [ ] When sync, timeouts/deadlines and source consumer concurrency are sufficient.
- [ ] JDBC local transactions are not mistaken for distributed HTTP/SFTP transactions.
- [ ] JMS transactions/acks/rollbacks tested under the actual container mode.
- [ ] AMQP ack/nack/requeue/DLX distinguished from publisher confirms.
- [ ] Kafka offsets, error handlers, retry topics, DLTs, and producer ack semantics tested.
- [ ] File/SFTP include staging, ready markers, accept-once metadata, stable names, and reconciliation.
- [ ] JDBC polling uses atomic claims, lease expiry, `nextAttemptAt`, and durable state.
- [ ] `@Transactional` uses the proper transaction manager, proxy, and rollback policy.
- [ ] Transactional outbox/inbox in place if source acks under durable-acceptance semantics.
- [ ] Unique business/recipient IDs enforce deduplication.
- [ ] Idempotency keys or status queries/reconciliation handle unknown outbound outcomes.
- [ ] Outbox publisher uses atomic claims, leases, bounded retries with deadlines, and marks `DONE` after confirmation.
- [ ] Crash handling tested across all commit and source ack boundaries.
- [ ] Error flows / `RecoveryCallback` never swallow errors without durable recovery.
- [ ] DLQ/parking is durable with ownership, retention, auditing, and controlled replay.
- [ ] Multi-recipient fan-out tracks per-recipient status and required/optional policy.
- [ ] Total retry budget spans source redelivery, client retries, handler retries, and durable redrive.
- [ ] Metrics separate source ack, durable acceptance, outbound transport ack, and business `DONE`.
- [ ] Secrets/PII excluded from logs; inbox/outbox storage protected with ACLs/encryption and retention.
- [ ] Tested that outbox poller recovers even if post-commit callback never runs.
- [ ] Tested that remote commit + lost response produces no duplicate business effects.
- [ ] Tested that deadlocks / rollback-only states never commit falsely.
- [ ] Runbooks prepared for `OUTCOME_UNKNOWN`, stuck leases, expired jobs, and source-ack failures.
- [ ] Transaction review documents XA/JTA limits if used.
- [ ] Never mark `DONE` solely because outbound `channel.send` returned true without durable/business evidence.

## 36. Glossary and Further Reading

| Term | Meaning |
|---|---|
| **Commit** | Confirmation of a transaction within the scope of its managed resources |
| **Source acknowledgement (ack)** | Confirmation that a delivery was processed or accepted per source protocol |
| **Kafka offset commit** | Records consumer group progress; does not prove external operations are `DONE` |
| **AMQP publisher confirm** | Broker confirmation of outbound publish acceptance per configuration |
| **JMS session commit** | Commits a JMS session transaction when using a transacted session |
| **JDBC transaction commit** | Durably persists DB changes participating in the same transaction |
| **Transport acceptance** | Target received/responded at the protocol level per contract |
| **Business completion** | Target business operation reached confirmed terminal state |
| **Durable acceptance** | Work durably stored so the system can continue processing later |
| **Transactional outbox** | Persisting send intent in the same database transaction as source updates |
| **Inbox / deduplication** | Storing business event IDs and outcomes to handle redeliveries safely |
| **Idempotency key** | Stable key ensuring retrying the same operation avoids duplicate effects |
| **Unknown outcome** | Uncertainty whether the remote target committed the side effect |
| **Retry / backoff** | Retrying recoverable failures / delay interval between attempts |
| **Redelivery** | Source/broker re-delivering a message lacking proper acknowledgement |
| **DLQ/DLT/PARKED** | Storage for failed items awaiting investigation or replay |
| **Lease** | Temporary worker ownership; expiration enables recovery |
| **Transaction synchronization** | Callbacks bound to local transaction lifecycle, not atomic externally |
| **XA/JTA** | Mechanism coordinating resources that support distributed transactions |
| **`DirectChannel`** | Channel dispatching synchronously on the caller thread per topology |
| **`ExecutorChannel`** | Channel backed by an executor, introducing an async boundary |
| **`QueueChannel`** | Queued channel whose durability depends on `MessageStore`/config |
| **At-least-once** | Deliveries may repeat to prevent message loss |
| **Effectively-once effect** | Duplicate deliveries producing a single valid business effect via idempotency |
| **Compensation** | Compensating business action, not equivalent to ACID rollback |

### Conceptual References

- **Spring Integration Reference — Transactions:** transaction boundaries, polling consumers, transaction synchronization, and advice.
- **Spring Integration Reference — Message Channels:** `DirectChannel`, `ExecutorChannel`, `QueueChannel`, and asynchronous handoff implications.
- **Spring Integration Reference — Error Handling:** `errorChannel`, `ErrorMessage`, synchronous vs. asynchronous errors.
- **Spring Integration Reference — JMS, AMQP, Kafka, JDBC, HTTP, File, SFTP adapters/gateways:** per-protocol and endpoint behavior.
- **Spring Framework Reference — Transaction Management:** `PlatformTransactionManager`, propagation, rollbacks, and synchronization.
- **Spring Retry Reference:** `RetryTemplate`, `RetryPolicy`, `BackOffPolicy`, and `RecoveryCallback`.
- **Spring for Apache Kafka Reference:** consumer ack modes, Kafka transactions, error handlers, offsets, and DLT.
- **Spring AMQP Reference:** listener acknowledgements, nack/requeue, publisher confirms, and dead-lettering.
- **Enterprise Integration Patterns:** Transactional Client, Idempotent Receiver, Guaranteed Delivery, Dead Letter Channel, and Message Store.

These references provide topic guidance; verify exact APIs against your project's **Spring Integration/Spring Framework/client versions** before copying specific configuration syntax.

## 37. Self-Assessment Questions

1. Why does an outbound HTTP handler returning normally not necessarily mean the ERP business operation completed?
2. How does a Kafka offset commit differ from a JDBC transaction commit?
3. Why can acknowledging the source **after** outbound success still produce duplicates?
4. Is an `ExecutorChannel` returning `true` from `send` sufficient to ack the source? When, if ever?
5. In the durable handoff strategy, is the source acked before or after remote outbound business completion?
6. Why must a transactional outbox row be written **inside** the database transaction rather than sending solely from a post-commit callback?
7. Why does an outbox still need idempotency even when each row has a unique `eventId`?
8. When might HTTP `202 Accepted` permit acknowledging the source?
9. Why doesn't an AMQP publisher confirm prove the downstream consumer is `DONE`?
10. If a Kafka consumer sends a record over HTTP and crashes before offset commit, what issue occurs?
11. What risks can file accept-once filters and archiving introduce when outbound fails?
12. When an SFTP rename executed yet the response dropped, how should you handle it?
13. Why doesn't `@Transactional` on a method containing an HTTP call roll back the remote POST?
14. When is JTA/XA helpful, and why doesn't it directly solve HTTP/SFTP?
15. If a JMS handler retries four attempts and the broker redelivers three times, how many total handler invocations can occur?
16. With a three-recipient fan-out where two are `DONE` and one is `RETRY_WAIT`, should you resend the entire fan-out?
17. When can a normal return from `ErrorMessage`/`RecoveryCallback` cause a false source ack?
18. Which metrics help detect rising source acks while business events remain incomplete?
19. When an outbox job gets stuck `IN_PROGRESS` because a worker died, what mechanism is needed?
20. What minimum evidence is required before marking business state `DONE`?

### Short Answers and Explanations

1. Handler return is only a local signal; HTTP 202 or async remote workflows may still be unfinished; inspect responses and the business contract.
2. Kafka offset tracks consumer group progress; JDBC commit persists DB changes in a transaction; they do not share a scope.
3. The remote target can commit, followed by source ack failure/crash; broker redelivery re-executes the operation.
4. Not if it only enqueued in memory. You may ack after committing durable job state or verifying completion per contract.
5. **After durable local acceptance**, which can be **before remote business completion** when the design and SLA allow.
6. Post-commit callbacks may never run if the process crashes; the outbox must survive commit durably to be polled/recovered.
7. A worker may succeed remotely and die before marking `DONE`; retries will resend, requiring remote idempotency/reconciliation.
8. When a durable job ID/state exists and the business contract permits accepted-for-processing; do not call it final `DONE`.
9. Confirm reflects broker publish acceptance, not downstream consumer side effects.
10. Consumer redelivers the record; HTTP may have already processed it → duplicate without idempotency.
11. The file may be marked/moved and never re-polled; use staging/metadata and durable replay.
12. Query remote state/checksum/filename and classify as `OUTCOME_UNKNOWN` if uncertain; never overwrite blindly.
13. A JDBC transaction does not encompass HTTP APIs; remote side effects do not participate in rollback.
14. XA helps when resource managers genuinely support coordination; HTTP/SFTP do not participate by default.
15. **4 × 3 = 12** invocations, excluding client retries.
16. No; retry only the pending recipient with its own state and idempotency.
17. When exceptions are swallowed before durable recovery; the container treats the message as successful.
18. `ack_without_durable_outcome` and correlating `sourceAck` against `durableAcceptance`/`businessDONE`.
19. Lease/expiry, atomic reclaim, durable attempt counts, and idempotent resume.
20. Business result per contract, remote reference/outcome or durable accepted-for-processing state, and verified source ack/transaction.

---

**Conclusion:** "**Commit after successful outbound processing**" in Spring Integration is not a single one-line setting across every adapter. What is true must be stated in terms of **which resource commits, what outbound success level is awaited, when source ack occurs, and where an event remains recoverable if the process crashes**. For synchronous flows, you can await outbound completion before acking the source when containers and timeouts allow; for multi-protocol integrations and prolonged failures, it is usually better to commit a **durable inbox/outbox** before source ack and complete outbound work via workers with idempotency and reconciliation. Either way, verify **ack/commit boundaries, unknown outcomes, duplicate side effects, and crash recovery** with integration and fault-injection tests rather than relying on a handler not throwing an exception.








