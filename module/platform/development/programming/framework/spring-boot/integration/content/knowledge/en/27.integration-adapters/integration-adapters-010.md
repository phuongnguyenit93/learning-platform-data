# Polling, event notification, and controlling data retrieval cadence

In system integration, not every data source can actively push events when data changes. An SFTP directory may only support file listing and a database table may only allow queries, whereas a message broker or webhook can notify immediately when work arises. Choosing **polling**, **event notification**, or **a combination of both** directly affects latency, system load, consistency, duplicate handling, and failure recovery.

This lesson belongs to the **Integration Adapters** chapter of the **SPRING_BOOT_INTEGRATION** course. Within the scope of integrating HTTP clients, databases, caches, message brokers, and **Spring Integration** adapters, the lesson focuses on ingestion contracts, retrieval cadence configuration, transaction boundaries, testing, error management, and observability of real-world integration flows.

## 1. Learning outcomes

After this lesson, you will be able to:

1. Distinguish fixed-delay polling, scheduled polling, event reception, and hybrid notification-plus-reconciliation models.
2. Describe the roles of **MessageSource**, **SourcePollingChannelAdapter**, **Poller**, **MessageChannel**, and handlers in Spring Integration.
3. Configure retrieval cadence, maximum messages per cycle, concurrency limits, and pause/backpressure policies when downstream is overloaded.
4. Design DB/SFTP/API ingestion so it remains safe across multiple application instances, restarts, and connection drops.
5. Separate **detecting available data**, **claiming/receiving data**, **business processing**, and **committing checkpoints**.
6. Choose transaction boundaries, idempotency keys, retries, dead-letter/quarantine paths, and metrics suited to the integration contract.

## 2. How do polling and event notification differ?

**Polling** means the application actively checks a source on a cadence or schedule to see if new data exists. Each check may yield one, many, or zero items. **Event notification** means the source actively signals that an event occurred, typically via HTTP webhook, broker, or callback. Notifications may carry the full payload or only a reference ID for the app to query additional state.

~~~mermaid
flowchart LR
    subgraph Pull["Polling: application actively fetches"]
      CLOCK["Scheduler / Poller"] --> SOURCE["DB / file / SFTP / HTTP API"]
      SOURCE --> ADAPTER["Inbound polling adapter"]
    end
    subgraph Push["Notification: source actively notifies"]
      EXTERNAL["External system"] --> WEBHOOK["Webhook / message listener"]
    end
    ADAPTER --> CHANNEL["MessageChannel"]
    WEBHOOK --> CHANNEL
    CHANNEL --> LOGIC["Validate / transform / handler"]
    LOGIC --> STORE[("Target DB / broker / service")]
~~~

| Criterion | Polling | Event notification |
| --- | --- | --- |
| Who controls receive timing | The integrating application | The emitting source or broker |
| Detection latency | Depends on poll interval and backlog | Usually low if notifications arrive promptly |
| Load on source when idle | Yes, because periodic checks still run | Usually lower when no events occur |
| Risk of missing data | Possible if checkpoints/filters are wrong or data vanishes before read | Possible if webhooks/brokers lack persistence and redelivery |
| Handling disconnects | Subsequent polls can catch up if source retains data | Requires retries, event logs, inbox, or reconciliation |
| Load throttling | Adjust schedule, batch size, concurrency, backoff | Broker consumer limits, prefetch, pause/resume, 429s, queues |
| Best fit | Pending DB tables, files/SFTP, pull-only APIs | Webhooks, queues, streams, source-emitted changes |

**Terminology note:** a Kafka consumer uses a **poll** loop at the client-library/protocol level, yet to a Spring Integration flow it typically delivers messages in a message-driven fashion. Never assume every class with a method named **poll()** requires a Spring Integration **Poller**. Classify by who drives calling the flow's **MessageSource**.

### 2.1. Three business scenarios

- **Partner drops files onto SFTP hourly:** the app is not notified of the exact moment upload finishes; use polling with filters, file-readiness checks, and processed-file tracking.
- **Partner sends an "order updated" webhook:** an endpoint receives the event, verifies signatures, records the event ID, and processes later; it may query the HTTP API by ID for the canonical state.
- **Webhooks can drop during network outages:** pair fast webhook intake with a periodic cursor-based reconciliation poller so updates are never missed.

## 3. Nature of a poller in Spring Integration

In a Spring Integration flow, a **polling inbound adapter** reads from a **MessageSource** on schedule and sends messages into a **MessageChannel** for processing. An **event-driven inbound adapter** or **message-driven adapter** emits messages when data arrives from external sources, so that flow does not require a Spring Integration poller.

~~~mermaid
flowchart TD
    TRIGGER["TaskScheduler + Trigger"] --> POLLER["Poller"]
    POLLER --> RECEIVE["MessageSource.receive()"]
    RECEIVE --> RETURN{"Message returned?"}
    RETURN -->|No: null| EMPTY["End current poll cycle"]
    RETURN -->|Yes| CHANNEL["MessageChannel"]
    CHANNEL --> FILTER["Filter / Transformer"]
    FILTER --> HANDLER["Service Activator / Handler"]
    HANDLER --> RESULT[("Target system")]
~~~

Key concepts to grasp:

| Component | Responsibility | Limits to remember |
| --- | --- | --- |
| **MessageSource** | `receive()` method fetches one message or returns `null` when none are ready | One call does not necessarily equal one DB row if the payload is a list |
| **SourcePollingChannelAdapter** | Connects a polling schedule to a `MessageSource` and sends results into the flow | Does not by itself create exactly-once guarantees |
| **Trigger / TaskScheduler** | Decides when to fire polling cycles | Scheduled intervals do not guarantee strict latency when threads are busy |
| **PollerMetadata / PollerSpec** | Configures poll cadence, max messages per cycle, and advice/transactions if needed | Configure per source rather than blindly applying a global default |
| **MessageChannel** | Delivers messages downstream | `DirectChannel` runs synchronously; async channels change thread/transaction boundaries |
| **Handler** | Executes business logic and produces results/exceptions | Must own idempotency, retries, and ack/checkpointing |

Within a single cycle, the poller invokes `receive()` up to **maxMessagesPerPoll** times, typically stopping early on `null`. If the `MessageSource` always returns items, an unbounded configuration can tie up a scheduler thread indefinitely. If the source returns a single **`Message<List<Item>>`**, that counts as **one message** to the poller; capping the record count inside that payload must happen at the query/source level.

### 3.1. Common cadences

- **Fixed delay:** waits a fixed interval after the previous cycle completes; good for avoiding piling onto a slow source.
- **Fixed rate:** aims to trigger at fixed time marks; delayed runs from busy schedulers or long handlers can skew real cadence. Do not assume fixed rate spawns unbounded parallel runs.
- **Cron:** runs at calendar times, e.g., syncing at the top of every five-minute window. Fits business hours or maintenance windows; define timezone and missed-fire behavior explicitly.
- **Adaptive throttling:** adjusts cadence dynamically based on **backlog**, 429/`Retry-After`, processing duration, downstream capacity, or consecutive empty polls. Usually requires a custom trigger or surrounding policy rather than a static fixed delay.

Polling cadence never replaces a data contract. Polling every 100 ms does not make a partner publish faster if they batch every 15 minutes; it only inflates load, logs, and connection churn.

## 4. Spring Boot example: polling from a work table

Suppose an ingestion system has an **`inbound_work`** table storing pending tasks. A repository provides **`claimNext()`**: atomically/transactionally selecting and claiming **one** task, returning **`Optional.empty()`** when no work is available. The repository also handles leases and reclaiming abandoned items if an instance dies.

The configuration below uses Spring Boot 3.x and Spring Integration Java DSL:

~~~java
import java.time.Duration;
import java.util.Optional;
import java.util.UUID;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.core.MessageSource;
import org.springframework.messaging.support.MessageBuilder;

record WorkItem(UUID id, String content) {}

interface WorkItemRepository {
    // Must be implemented via an atomic claim with a lease,
    // safe when multiple app instances poll concurrently.
    Optional<WorkItem> claimNext();
}

interface WorkItemProcessor {
    // Commit the result and complete the work item by idempotency key.
    void process(WorkItem workItem);
}

@Configuration
@EnableIntegration
class InboundWorkFlowConfig {

    @Bean
    MessageSource<WorkItem> inboundWorkSource(WorkItemRepository repository) {
        return () -> repository.claimNext()
                .map(item -> MessageBuilder.withPayload(item)
                        .setHeader("workId", item.id().toString())
                        .build())
                .orElse(null);
    }

    @Bean
    IntegrationFlow inboundWorkFlow(
            MessageSource<WorkItem> inboundWorkSource,
            WorkItemProcessor processor) {

        return IntegrationFlow
                .from(inboundWorkSource, endpoint -> endpoint
                        .poller(Pollers.fixedDelay(Duration.ofSeconds(2))
                                .maxMessagesPerPoll(20)))
                .handle(WorkItem.class, (item, headers) -> {
                    processor.process(item);
                    return null; // Terminal handler: produces no reply
                })
                .get();
    }
}
~~~

**Why separate interfaces in the example?** Adapter config expresses schedule and message routing; claiming/leasing, committing, and deduplication belong to the persistence/business contract. Never treat a plain `SELECT` as `claimNext()` and assume it is safe across two pods. A DB implementation can use transactions with row locking and **`SKIP LOCKED`** where supported, or conditional status updates checking affected row counts. When a claimed item fails processing, lease expiry, retry state, or a failure table must bring the work back.

**How to read this config:**

1. Each schedule tick, the poller calls the source until `null` is returned or up to 20 **Messages** are fetched.
2. Each `WorkItem` payload flows into the handler; on the default synchronous path, handler execution time adds to the poll cycle duration.
3. If `processor` throws, you need an exception-handling policy and lease release/recovery for abandoned work; this code only shows the wiring hook, not the full job lifecycle.
4. With multiple instances, each instance runs its own scheduler. Duplicate prevention must rely on atomic claiming/idempotency at the source or an appropriate coordination mechanism.

### 4.1. Choosing where transactions sit

Separate three operations clearly:

- **Read and claim:** a short transaction claiming ownership and recording `claimed_by`, `lease_until`, status, and attempt count; avoid holding DB locks during slow HTTP calls.
- **Business processing:** may call HTTP/brokers or write to target DBs. Outcomes remain uncertain after timeouts; carry request IDs for reconciliation.
- **Completion/ack:** mark `DONE` only after required business effects commit or durable recovery state is established.

Pollers can use transaction advice/transaction managers. However, Spring transactions are generally bound to a thread and participating resources; switching to an `ExecutorChannel` or sending to a broker crosses a boundary. Wrapping `receive()` in a transaction does not automatically synchronize target DB writes, HTTP requests, and broker ACKs.

For high-durability systems, prefer **inbox/outbox** patterns and idempotent consumers. Never promise exactly-once simply because a Spring Integration transaction was configured.

## 5. Tuning retrieval cadence for operational goals

Four parameters must be designed together: **trigger cadence**, **batch size**, **concurrency**, and **downstream capacity**.

| Parameter | Effect of increasing | Risks and conditions |
| --- | --- | --- |
| **Poll frequency** | Detects data sooner when source updates often | Increases queries/API calls, quota burn, connections, and empty polls |
| **`maxMessagesPerPoll`** | Amortizes per-cycle overhead; can raise throughput | Longer cycles, starvation across sources, long-held threads |
| **Query batch size** | Fewer round trips for multiple records | Large reads inflate memory, transaction locks, packets, and recovery time |
| **Concurrency** | More items processed in parallel | Easy to exhaust connection pools or rate limits; can break ordering |
| **Backoff** | Reduces load during errors or empty runs | Increases recovery or detection latency |
| **Jitter** | Spreads poll instants across pods | Harder to predict exact fire times; measure rather than relying on theory |

### 5.1. Estimating throughput

For a synchronous flow fetching up to **B** messages per cycle with a **D**-second rest after completion and average processing time **L** seconds per message, throughput when batches are always full is roughly:

\[
R \approx \frac{B}{D + B \times L}
\]

For example, **B = 20**, **D = 2 seconds**, **L = 0.1 seconds** gives a theoretical throughput of about **5 messages/second** (20 messages in 4 seconds). Ignoring handler time and computing **B/D = 10 messages/second** overestimates real capacity. This formula excludes DB/network overhead, retries, scheduler jitter, queueing, and contention; always benchmark under load.

With asynchronous flows, ingestion speed can easily outrun processing speed. Add bounded queues, bounded task executors, and downstream limits; otherwise the poller merely shifts pressure from the source into application RAM.

### 5.2. Using fixed delay, fixed rate, and cron

~~~java
// Wait 2 seconds after the previous poll run completes.
Pollers.fixedDelay(Duration.ofSeconds(2))
       .maxMessagesPerPoll(20);

// Target trigger every 5 seconds;
// actual timing depends on scheduler load and execution duration.
Pollers.fixedRate(Duration.ofSeconds(5))
       .maxMessagesPerPoll(10);

// Runs at second 0 of every 5-minute mark.
// Configure timezone when a local schedule is required.
Pollers.cron("0 */5 * * * *")
       .maxMessagesPerPoll(100);
~~~

These expressions are **sample `PollerSpec` builders** attached to endpoints; they are not three concurrent pollers on one source. Verify overload signatures against your Spring Integration version. When flows need different schedules, configure pollers per endpoint rather than letting an aggressive default poller overwhelm small sources.

### 5.3. Cadence design rules

1. Choose a **latency SLO**: must data appear within 2 seconds, 30 seconds, or 15 minutes?
2. Measure **data generation rates** and burst sizes; peak hours differ sharply from averages.
3. Identify **source quotas**: API calls/minute, max DB connections, reasonable SFTP scan rates.
4. Identify **downstream throughput**: DB writes/sec, broker quotas, HTTP RPS, thread pools.
5. Set **batches, timeouts, retries, backoff, and concurrency limits** within that budget.
6. Measure backlog/lag and end-to-end p95/p99; tune from real metrics instead of shrinking fixed delay blindly.

## 6. Backpressure: when sources outpace processing

**Backpressure** is the ability to slow down or pause ingestion when downstream cannot keep up. This matters even for active pollers because multiple threads or pods may pull from the same DB or API.

~~~mermaid
flowchart LR
    SRC["DB / API / SFTP"] --> POLL["Bounded polling"]
    POLL --> QUEUE["Bounded buffer / durable queue"]
    QUEUE --> WORK["Bounded worker pool"]
    WORK --> DEST[("DB / external service")]
    MON["Measure queue depth, backlog age, errors, latency"] -.-> POLL
    MON -.-> WORK
    DEST -. "429, 503, timeout" .-> MON
~~~

With **`DirectChannel`**, handlers run synchronously on the sender thread, creating natural throttling tied to handler latency while keeping scheduler threads occupied. With **`QueueChannel`** or executor channels, the poller can keep reading while handlers lag. In that case, define:

- Maximum queue capacity and full-queue behavior; in-memory queues lose data on pod termination.
- Thread/connection limits per downstream dependency, separating CPU-bound from I/O-bound work.
- Polling pause/resume cadence; retries with jitter and error-specific backoff.
- Recovery for items claimed before a crash but never completed.
- Whether increasing workers breaks per-account or per-order sequencing.

Never use an unbounded internal queue and call it load handling. When bounded queues fill up, choose **blocking further reads**, **controlled rejection**, or **persisting to a durable queue** per contract; never drop critical records silently.

### 6.1. Adaptive backoff and HTTP quotas

Suppose an adapter polls a partner API by cursor. On **429 Too Many Requests**, respect **`Retry-After`** when valid and permitted; otherwise apply bounded exponential backoff with jitter. On **5xx** or transient network errors, retry within limits; on **401/403**, investigate credentials/permissions rather than hot-retrying. Avoid sharing an unbounded retry schedule across both fetching and DB writes.

When paging APIs, persist cursors or checkpoints safely. Response timeouts leave query execution ambiguous, yet re-reading pages via a stable cursor is safe if downstream writes are idempotent.

## 7. Event notification: fast intake still demands reliability contracts

Common event-driven sources in Spring Boot systems:

| Mechanism | How adapters receive | Requirements to avoid losing critical events |
| --- | --- | --- |
| HTTP webhook | Spring MVC/WebFlux endpoint or Spring Integration HTTP inbound gateway | Authenticate source, persist durable inbox before ACKing if at-least-once needed, support replay and dedup |
| Broker queue (RabbitMQ, JMS, etc.) | Listener/message-driven inbound adapter | Choose ack mode, retry/requeue, DLQ, consumer concurrency, and idempotency |
| Kafka/stream | Consumer inbound adapter | Commit offsets at the right time, deduplicate, partition ordering, lag management |
| Spring application event | In-app listener or adapter | Never treat in-process events as durable queues across restarts |
| File system watcher | OS notifications or watcher-backed adapters | File change events can drop or coalesce; pair with reconciliation scans and completion checks |

A webhook may fire multiple times if the external sender misses the HTTP response even after the app processed the first call. Events can also arrive out of order. Thus **`eventId`**, **`resourceId`**, **`eventVersion`**, **`eventTimestamp`**, and **canonical state reconciliation** matter far more than shaving a few milliseconds off latency.

### 7.1. Safe webhook flow example

~~~mermaid
sequenceDiagram
    participant Ext as External partner
    participant API as Spring Boot webhook
    participant DB as Inbox DB
    participant Worker as Integration worker
    participant Target as Business DB/service
    Ext->>API: POST event (eventId, resourceId)
    API->>API: Verify signature, schema, replay window
    API->>DB: Insert inbox by unique eventId
    DB-->>API: Committed / duplicate known
    API-->>Ext: 2xx acknowledgment
    Worker->>DB: Claim pending inbox items
    Worker->>Target: Idempotent business operation
    Target-->>Worker: Committed / reconciled
    Worker->>DB: Mark inbox DONE
~~~

In this scenario, **`2xx`** confirms **durable receipt**, not that all business processing finished. If the partner contract demands synchronous completion before acknowledging, adjust HTTP semantics, timeouts, and error codes accordingly. When signature or schema checks fail, never return a fake `2xx`; distinguish auth errors from retryable failures. When persisting to the inbox fails, return a retryable error per the partner's contract.

This diagram deliberately uses an inbox and worker to separate **notification** from **execution**. Spring Integration adapters can receive via HTTP inbound gateways, RabbitMQ/Kafka adapters, or internal channels; whichever mechanism is used must pair with matching ack, error-handling, and persistence configs.

### 7.2. When to combine webhooks with polling

Notifications can act purely as **signals**: "resource X changed". The app logs the signal and pulls the latest state from an API by resource ID. This helps when event payloads are thin, though it does not recover events dropped during network outages.

A more resilient pattern:

1. Webhooks provide low-latency detection of new changes.
2. A periodic reconciliation poller fetches all changes since the committed cursor or an overlapping lookback window.
3. Inbox/idempotency keys ensure that seeing the same resource via both webhook and poller triggers business side effects only once.
4. Checkpoints advance only after corresponding data is durably persisted or queued.
5. Monitor **webhook-to-processed lag** and **reconciliation lag** to spot dropped events.

## 8. Cursors, checkpoints, and avoiding missed data

Polling is unsafe if you simply ask "what's new since last time?" without defining page boundaries, sort order, source commit lag, and checkpoint timing.

### 8.1. Avoid blind offset pagination

In a work queue table, rows transition from `PENDING` to `DONE` as they are processed. Using `OFFSET 100` over a shrinking `PENDING` set shifts row positions and skips records. Time-evolving paginated APIs exhibit the same flaw.

Prefer:

- **Status/lease-based atomic claiming** on queue tables.
- **Keyset pagination** over a stable tuple such as `(updated_at, id)` when supported by the contract.
- **Source-provided cursors** when cursors guarantee ordering and resumability.
- **Overlap windows** to re-read recent intervals for late-arriving commits, backed by idempotent downstream processing.

### 8.2. High-watermark vs. committed checkpoint vs. item state

- **High-watermark:** the highest value seen from the source, such as an update timestamp or sequence.
- **Committed checkpoint:** the position from which the system can safely resume without missing data under the contract.
- **Per-item state:** `PENDING`, `CLAIMED`, `DONE`, `FAILED`, or `QUARANTINED`.

Never advance the checkpoint before the batch is durably stored or processed per contract. Advancing early and crashing drops data past the checkpoint on subsequent polls. Advancing late causes re-reads—which is why idempotency is mandatory.

For example, when a source's `updated_at` is not strictly monotonic in visibility order, filtering `updated_at > lastSeen` can skip late-committing rows. A lookback window paired with `(updated_at, id)` and deduplication mitigates this; size the lookback based on source commit-lag SLAs or cursor guarantees rather than guessing.

### 8.3. File/SFTP requires a "readiness" criterion

A file appearing in a directory does not guarantee the partner finished writing it. Practical conventions include:

- Partner uploads to a temp name and renames atomically on completion.
- A `.done` marker file or manifest listing files and checksums.
- Poller checking stable size/mtime across multiple cycles (heuristic only; does not replace producer contracts).
- Marking files processed only after target data commits; retaining file identity, digest/checksum, or business IDs for deduplication.

Inbound file filters need persistent state stores when restart safety is required; in-memory filters allow re-reading files after restarts. Re-reading is harmless only when downstream processing is idempotent.

## 9. Multiple instances polling together: contention and processing guarantees

When Spring Boot runs across three pods, each pod runs its own poller. Three instances with `fixedDelay(2s)` run three independent loops; Spring Integration does not automatically turn a flow into a single distributed cron job.

~~~mermaid
flowchart TD
    A["Pod A: poller"] --> Q[("Shared work table / source")]
    B["Pod B: poller"] --> Q
    C["Pod C: poller"] --> Q
    Q --> CLAIM["Atomic claim / partition ownership"]
    CLAIM --> HANDLE["Process idempotently"]
    HANDLE --> CHECK["Commit business effect + completion"]
~~~

Three common coordination patterns:

| Pattern | Idea | When it fits |
| --- | --- | --- |
| Every pod polls, **claims atomically** | Workers share load; each item has a lease/owner | DB work queues, sources supporting independent item claims |
| **Single active leader** polls | Leader election or distributed lock limits active scheduler | Legacy sources lacking concurrency, ultra-low API quotas |
| **Partition/cursor sharding** | Each consumer owns a distinct partition/key range | High volume with stable partitions and ordering needs |

**A distributed lock alone does not guarantee exactly-once processing:** locks can expire while the old holder keeps running, and failovers leave ambiguous states. Critical side effects still need target idempotency, DB transactions, fencing tokens where needed, and reconciliation.

**A claim only grants temporary ownership:** if a pod dies, the lease expires so another can take over. An item can run twice if a pod dies after committing side effects and before marking `DONE`; downstream must recognize stable idempotency keys.

## 10. Errors, retries, and cadence control after failures

Policies should differ across source-poll failures, data transformation errors, and downstream failures:

| Error | Appropriate action | What to avoid |
| --- | --- | --- |
| Cannot reach source DB/SFTP/API | Bounded timeouts, bounded backoff, alert on SLO breach | Tight polling causing log storms or overwhelming source |
| HTTP 429 / quota | Respect `Retry-After`, slow down or pause | Immediate retries across every pod |
| Bad config, 401/403, invalid schema | Classify as non-hot-retryable; alert and fix config/data | Treating as transient network error |
| One bad record while source has healthy items | Quarantine/DLQ with error code and ID; keep processing per policy | Letting one poison message stall the entire pipeline indefinitely |
| Downstream timeout after side effect | Record uncertain state; query/check idempotency before retrying | Blindly re-sending POST without a request ID |
| Queue/buffer full | Pause intake, throttle source, or reject cleanly | Unbounded RAM queues or silent drops |

In Spring Integration, poller errors can route via `errorChannel`/error flows and combine with retry, transaction, and circuit-breaker advice. Check both **per-poll** and **per-item** error behavior; an exception from a synchronous handler can abort the rest of the current poll cycle. Across async channels, worker-thread exceptions cannot roll back the poller's source transaction.

### 10.1. Three retry layers must not multiply infinitely

1. **Connection/read retries:** handle transient source access errors with bounded time and attempts.
2. **Business processing retries:** use per-item idempotency keys and attempt tracking with backoff delays.
3. **Cycle/scheduled retries:** subsequent poll ticks or reconciliation jobs picking up unfinished work.

Stacking retries at all three levels multiplies execution counts dramatically. Assign **one retry owner** per boundary and budget total timeouts, max attempts, cooldowns, retention, and idempotency marker TTLs.

### 10.2. Ordering and duplicate arrival

Multi-worker polling rarely preserves global order. If one order produces `CREATED`, `PAID`, and `CANCELLED` updates, out-of-order execution can overwrite newer state with older state.

Mitigations depending on source:

- Partition by `orderId` and process serially within each partition.
- Compare source version/sequence numbers before applying updates.
- Turn thin events into "fetch current state" calls when the contract permits.
- Enforce unique keys on event ID and business version checks in the target DB.

Redelivery after a timeout is a normal occurrence under **at-least-once** delivery. Logs should distinguish handled duplicates from genuine system errors.

## 11. Observability: measuring actual cadence and business effectiveness

Reporting that a job "runs every 2 seconds" does not show whether data is processed on time. Measure from source update time to target commit time.

| Group | Metrics to track | Meaning |
| --- | --- | --- |
| Scheduler | Poll counts, actual inter-poll interval, trigger delay | Detecting scheduler starvation, overlapping runs, or drift |
| Source | Messages/poll, empty poll ratio, fetch duration, errors/timeouts, quota | Polling too aggressively or slow source? |
| Backlog | Pending count, oldest record age, checkpoint lag, estimated drain time | Is the pipeline keeping up with incoming volume? |
| Processing | Success throughput, p95/p99 duration, concurrency, queue depth | Are handlers or downstream the bottleneck? |
| Reliability | Retry attempts, duplicate count, expired leases, DLQ/quarantine, unknown outcomes | Are duplicates, drops, or stuck jobs occurring? |
| Downstream | DB connection pool, broker lag, HTTP 429/503, circuit-breaker opens | Is polling overloading downstream services? |

Use **Micrometer/Actuator** for metrics and structured logs carrying **correlation ID**, **source name**, **poll cycle ID**, **record ID**, attempt count, and checkpoint state. Keep metric tags low-cardinality such as adapter name or error category; never tag full cursors, URLs with tokens, or individual record IDs.

**Alerts should target outcomes:** backlog age exceeding SLO, zero processed items despite pending source work, consecutive failed polls, or near-full queues. A high empty-poll ratio alone does not necessarily signal an incident if the source simply has quiet periods.

## 12. Testing polling and notification

Test flows at three levels minimum: policy unit tests, adapter integration tests, and fault-injection tests for multi-instance or external failures.

| Scenario | Injected condition | Expectation |
| --- | --- | --- |
| Empty `MessageSource` | `receive()` returns `null` | Poll ends cleanly, no phantom messages, no error increment |
| Batch larger than limit | Stage more than `maxMessagesPerPoll` ready items | Single cycle stops at the limit; next cycle processes the rest |
| Slow handler | Inject latency into handler | Fixed delay measured accurately; no unbounded queue growth |
| Overloaded downstream | Exhaust DB pool or return HTTP 429/503 | Backoff/bulkheads engage; backlog grows in a controlled way |
| Crash after claim, before `DONE` | Stop instance at checkpoint | Lease/recovery allows re-claiming without losing the item |
| Crash after side effect, before ACK | Commit target DB then stop | Idempotency blocks duplicate side effects |
| Two pods polling concurrently | Run two instances against shared source | Atomic claiming or partitioning prevents duplicate business effects |
| Duplicate or reordered webhooks | Replay same `eventId`, swap version order | Deduplication, version checks, or reconciliation keep state accurate |
| Dropped notification | Suppress webhook briefly while source retains state | Reconciliation poller backfills completely |
| Timezone/schedule changes | Test cron under target timezone | Fires at expected wall-clock times; missed-schedule behavior defined |
| Incomplete SFTP file | Upload in multiple chunks | Incomplete files skipped; no missed files across restarts |

**For pollers, never write tests that just sleep a few seconds and hope it ran.** Prefer deterministic triggers, fake `MessageSource`s, latches/events, or controllable test schedulers, and assert exact `receive()` counts, processed messages, and checkpoint states. Integration tests using mocked handlers alone cannot verify leases, failover, multi-pod safety, or broker ACKs.

## 13. Synthesis scenario: syncing partner shipment statuses

A Spring Boot service updates delivery statuses. The partner sends webhooks on changes and also exposes a cursor-based HTTP polling API. Requirement: updates show within seconds while webhooks are healthy, and zero updates are missed even if webhooks drop temporarily.

~~~mermaid
flowchart TD
    EXT["Partner shipping system"] -->|Webhook eventId| WEB["HTTP inbound / validate"]
    EXT -->|GET changes?cursor=...| POLL["Scheduled reconciliation poller"]
    WEB --> INBOX[("Inbox / dedupe by event ID")]
    POLL --> INBOX
    INBOX --> WORK["Idempotent worker"]
    WORK --> API["Fetch canonical shipment state if needed"]
    API --> DB[("Shipment DB with version check")]
    DB --> DONE["Mark DONE / advance committed cursor"]
    METRIC["Lag, errors, retry, pending age"] -.-> POLL
    METRIC -.-> WORK
~~~

A clean separation of responsibilities:

1. **Webhook inbound:** verifies signatures, timestamps/replay windows, and schema; inserts into the inbox by unique event ID; acknowledges only after durable persistence.
2. **Reconciliation poller:** runs on a schedule respecting partner quotas; reads by cursor or lookback window with bounded page sizes; writes items into the inbox and commits checkpoints safely.
3. **Handler:** reconciles canonical state using shipment ID and version to ignore stale updates; target DB transactions prevent backward state transitions.
4. **Error handling:** backs off on 429 per partner rules; bounded retries on 5xx; alerts on 401/403; quarantines malformed/poison events; looks up status on side-effect timeouts before re-sending.
5. **Backpressure:** durable buffers, bounded workers, and capped HTTP concurrency; when backlog spikes, slows polling or prioritizes draining the inbox first.
6. **Monitoring:** event-time-to-DB-commit latency, pending age, backfilled event counts, duplicate rates, API quota usage, and checkpoint lag.

Seeing the same event arrive via both webhook and poller is normal here: **deduplication/idempotency** ensures target updates occur once logically. If an outage lasts longer than the API's retention window, runbooks must cover full backfills or reconciling all active shipments.

## 14. Common design mistakes

| Design mistake | Consequence | Fix |
| --- | --- | --- |
| Polling aggressively to cut latency | Overloads source, wastes empty polls, triggers 429s | Tune by SLO, source update cadence, backlog, and quotas |
| Leaving `maxMessagesPerPoll` unbounded | One cycle hogs the scheduler when data is plentiful | Cap messages/batches and share scheduler capacity |
| Reading via `SELECT` across multiple pods | Same record processed multiple times | Atomic claiming/partitioning/leader + idempotency |
| Marking `DONE` before side effects | Crashes permanently lose work | Commit at clear boundaries; use inbox/outbox if needed |
| Treating webhook `2xx` as business completion | Partner thinks data synced while workers still lag | Distinguish "accepted" from "processed"; track state separately |
| Retrying every exception | Amplifies failures or repeats business actions | Classify errors, enforce idempotency, bounded retries, DLQs |
| Using `OFFSET` over changing status tables | Skips rows as positions shift | Atomic claims, keyset/cursors, and checkpoints |
| Unbounded in-memory queues | RAM exhaustion, crashes, lost uncommitted work | Bounded buffers or durable brokers |
| Monitoring only trigger counts | Misses lag, backlogs, and corrupted data | Measure end-to-end lag, checkpoints, successes, and duplicates |
| Treating cron as distributed HA | Every pod runs the same job simultaneously | Separate scheduling from ownership; verify multi-pod safety |

## 15. Pre-implementation checklist

- [ ] Identified which sources use **polling**, which use **notification**, and which combine reconciliation.
- [ ] Contract specifies event ID, message ID, ordering, cursor, retention, retries, and delivery guarantees.
- [ ] Pollers define cadence, batch/`maxMessagesPerPoll`, timeouts, and concurrency caps.
- [ ] Retrieval cadence balanced against source quotas, downstream throughput, and end-to-end SLOs.
- [ ] Backpressure, bounded queues, or durable buffers exist; full-queue behavior is defined.
- [ ] Claim/checkpoint/ACK boundaries match transactions; crash recovery exists.
- [ ] Critical business effects enforce idempotency and reconciliation for uncertain outcomes.
- [ ] Multi-instance execution tested against missed or duplicated records.
- [ ] Webhooks/brokers enforce authentication, replay protection, retries, and DLQs.
- [ ] Metrics cover backlog age, poll duration, effective throughput, errors, retries, duplicates, and end-to-end lag.
- [ ] Tested network failures, 429/503s, incomplete files, late data, dropped webhooks, and mid-processing restarts.

**Business takeaway:** polling creates a cadence to **go find data**, while event notification lets sources **signal changes**. Spring Integration provides adapters, pollers, and channels to connect those steps, yet flow reliability still depends on rate control, safe claiming, accurate checkpoint timing, deduplication, and backlog observability under both normal and failure conditions.
