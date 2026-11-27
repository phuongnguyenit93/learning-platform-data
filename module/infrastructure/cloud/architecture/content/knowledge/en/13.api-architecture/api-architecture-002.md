# Synchronous and Asynchronous Communication and Business-Flow Selection

## 1. Inter-component communication is an architectural decision

In a distributed system, one service often has to call another service to complete a business journey. The communication model determines **who has to wait for whom, when a result is considered complete, how far errors propagate, and how data state is coordinated**.

Two common communication models:

- **Synchronous communication:** the caller sends a request and waits for the operation's result within the same interaction. For example, a booking API calls an inventory service to check room availability and returns the result immediately to the customer.
- **Asynchronous communication:** the sender hands off a message or job to an intermediary mechanism or recipient; processing and response can happen later. For example, after confirming a booking, the system emits an event to send an email and update reports.

Synchronous and asynchronous are **interaction models**, not names of specific protocols. HTTP can be used to submit an asynchronous command and return 202 Accepted; a message broker can be used in a request/reply pattern, which inherently still involves waiting time and logical coupling. Semantics must be clearly described before choosing REST, gRPC, a queue, an event broker, or a callback.

In the **CLOUD_ARCHITECTURE** module, API communication choices must originate from business requirements and connect to networking, compute, data, and deployment models; then evaluate trade-offs across **reliability, security, performance, scalability, cost, and operations** following a Well-Architected mindset.

Running example: a booking platform needs to search for rooms, hold rooms, capture payments, and send notifications. The customer needs to know immediately which action succeeded; the system must also handle slow payment gateway responses, duplicate webhooks, or temporarily undeliverable emails.

## 2. Synchronous: when is an immediate result needed?

In synchronous interaction, a typical flow is:

~~~mermaid
sequenceDiagram
    actor U as Customer
    participant A as Booking API
    participant I as Inventory Service
    participant D as Database
    U->>A: POST /bookings
    A->>I: Check and hold room
    I->>D: Write reservation hold
    D-->>I: Result
    I-->>A: Held / sold out
    A-->>U: Request status
~~~

The caller can only complete its response after all mandatory steps return results. This fits when the user needs an immediate answer, the business logic requires validation/update results before proceeding, and dependencies can meet the end-to-end latency budget.

Advantages include an easy-to-understand model, direct results, and suitability for queries/commands needing instant feedback. The drawback is **temporal coupling**: a slow or disconnected recipient can cause the caller to wait, time out, or cascade failures.

### 2.1. Cost of a synchronous call chain

Suppose an API must call three services sequentially:

| Step | Illustrative time |
| --- | ---: |
| Check room availability | 80 ms |
| Calculate pricing | 60 ms |
| Verify permissions/conditions | 40 ms |
| API processing and network overhead | 70 ms |
| **Approximate total sequential time** | **250 ms** |

If steps run sequentially, response time tends to approach the sum of each step plus overhead. If one step takes 2 seconds, the entire request may have to wait accordingly. Independent steps can be run in parallel to reduce latency, but you must handle per-branch failures, cancel work when no longer needed, and avoid creating burst traffic against dependencies.

You must never add individual service p95 latencies together and claim that is the end-to-end p95. Latency distributions and correlations across calls must be measured from traces of the entire journey.

### 2.2. Timeouts and time budgets

Every synchronous call needs a finite timeout. The end-to-end time budget should be partitioned across steps:

~~~text
Client timeout:       2.0 s
Gateway budget:       1.8 s
Booking API budget:   1.5 s
Inventory call:       0.5 s
Pricing call:         0.3 s
~~~

These numbers are only examples. In practice, you must account for connections, DNS, TLS, internal queues, data processing, and response serialization. Outer-layer timeouts must be long enough to exceed the deadlines allocated to inner steps, yet not so long that resources are held for requests that are no longer valuable.

When a timeout occurs, **it does not mean the server-side operation was cancelled or not executed**. The client may lose the response after the server has already written the data. For write commands, an idempotency key or status-query mechanism is required so the client does not create duplicate operations on retry.

## 3. Asynchronous: when do you not need to keep the caller waiting?

In the asynchronous model, the sender hands a message to a queue/broker or a job-intake mechanism. The sender can receive an acknowledgment of receipt while processing completes later:

~~~mermaid
sequenceDiagram
    actor U as Customer
    participant A as Booking API
    participant DB as Database
    participant Q as Event Broker
    participant W as Notification Worker
    U->>A: Complete booking
    A->>DB: Write booking + outbox event
    DB-->>A: Commit
    A->>Q: Publish BookingConfirmed
    Q-->>A: Broker acknowledges message
    A-->>U: Booking confirmed
    Q-->>W: Deliver event
    W->>W: Send email / SMS
~~~

In a system using an outbox, the event is written to the database within the same business transaction and then a publisher forwards it to the broker. This avoids the gap between data commit and event publishing.

Asynchronous communication typically fits when work can complete later without making the user wait; when queue-based elasticity is needed; when eventual consistency latency is acceptable and status can be displayed; or when multiple independent recipients need to react to the same event.

Advantages include reducing temporal coupling, smoothing load spikes, and decoupling producers from consumers. Trade-offs include managing job states, duplicate handling, ordering, dead-lettering, queue observability, and the user experience while waiting for results.

### 3.1. Distinguishing commands, events, and queries

| Message type | Meaning | Example |
| --- | --- | --- |
| **Command** | Requests a party to perform an action | ReserveRoom, ChargePayment |
| **Event** | Announces that an occurrence has already happened | BookingConfirmed, PaymentCaptured |
| **Query** | Requests to read data and expects a result | GetBookingStatus, SearchRooms |

Commands usually target a single handler responsible for execution. Events describe facts that have already happened and can have multiple independent subscribers. Queries usually suit synchronous responses, though they can become asynchronous jobs if the query is long-running or exports large datasets.

Do not name an event like an unexecuted command. BookingConfirmed means the booking is already confirmed; ConfirmBooking is a request to confirm. This distinction helps consumers interpret state accurately and avoid acting on events with misleading semantics.

### 3.2. HTTP 202 Accepted is not a completed business outcome

An API can accept a report-generation or task-processing request and return:

~~~http
HTTP/1.1 202 Accepted
Location: /jobs/job-8342
Retry-After: 3
Content-Type: application/json

{
  "jobId": "job-8342",
  "status": "accepted",
  "statusUrl": "/jobs/job-8342"
}
~~~

202 Accepted indicates the request has been accepted for processing; it does not assert that the work is finished or guaranteed to succeed. The API should provide a way to view status, final error details, result retention duration, and cancellation if supported by business rules.

## 4. Choosing a model per business flow

Do not pick a single communication style for the entire system. Classify each step by asking: **who needs the answer, when do they need it, what are the consequences if it is slow or fails, and is delayed processing acceptable?**

| Business flow | Typically suitable model | Rationale and conditions |
| --- | --- | --- |
| Search rooms and return results | Synchronous | Customer needs to view results to select; can cache and bound queries |
| Check/temporarily hold room | Synchronous or stateful workflow | Needs immediate hold success/sold-out feedback; requires concurrency control and timeouts |
| Confirm payment transaction | Synchronous with provider or multi-step workflow | Needs status determination; timeouts can lead to unknown states requiring reconciliation/webhooks |
| Send confirmation email | Asynchronous | Should not make the customer wait on the email system |
| Generate large report | Asynchronous | Long execution time; uses job status and completion notification |
| Update search index | Asynchronous | Tolerates update lag; has replay/rebuild mechanisms |
| Check order access permission | Synchronous | Result is required before returning sensitive data |
| Sync data to analytics | Asynchronous | Decouples analytical load from transactions and processes in batches |

| Factor | Favors synchronous | Favors asynchronous |
| --- | --- | --- |
| User needs immediate result | Yes | Less suitable, unless returning processing status |
| Long/unpredictable duration work | Hard to manage timeouts | Fits well with job status |
| Low-availability dependency | Errors propagate easily | Can buffer load, though broker/consumers still need HA |
| Multiple independent subscribers | Can call sequentially/in parallel, but high coupling | Events fit distribution well |
| Needs immediately consistent state read | Usually easier to express | Requires explicit state/lag model |
| Needs to absorb bursts | Needs direct capacity, rate limiting, and backpressure | Bounded queues can buffer load |
| Debugging | Trace call chain | Correlation ID, event history, and consumer lag |
| Operations | Fewer components in small systems | Adds broker, DLQ, schemas, and replay procedures |

These are tendencies rather than rigid rules. A small system may use synchronous calls for most flows for operational simplicity; a large system may use asynchronous jobs for long tasks while still providing synchronous endpoints to look up status.

## 5. Data consistency and transactions across multiple services

Choosing synchronous or asynchronous affects when data becomes visible and how transactions are handled. Within a single service sharing one database, a transaction can update multiple records atomically. When business logic spans multiple services/databases, **you cannot assume a single local transaction covers every system**.

### 5.1. Eventual consistency

**Eventual consistency** means replicas or data views may temporarily differ after a change, but if no new updates occur and processing succeeds, they will converge according to a defined model.

For example, when a booking is confirmed:

1. Booking database records the CONFIRMED status.
2. BookingConfirmed event is emitted.
3. Search index updates the booked room count after a short lag.
4. Analytics receives the event and updates reports.

For a few seconds, the search UI may not yet reflect the change. This is only acceptable if the room hold/booking workflow at the authoritative data source still prevents double-booking. Never use a lagging search index as the final decision source for critical write transactions.

### 5.2. Sagas and multi-step workflows

If a transaction spans multiple services, it can be modeled as a **Saga**: each step has a local transaction, paired with a compensating action if a later step fails.

~~~mermaid
flowchart LR
    A["Hold room"] --> B["Authorize payment"]
    B --> C["Confirm booking"]
    C --> D["Emit notification event"]
    B -. failed .-> X["Release room hold"]
    C -. unrecoverable error .-> Y["Cancel/refund transaction per policy"]
~~~

For example: create a time-limited hold; request the payment gateway to authorize/capture funds per contract; transition the order to CONFIRMED. If payment fails, release the room hold. If the confirmation step fails after funds were captured, a refund/void and reconciliation process is needed.

Compensating actions do not necessarily physically reverse the original action or run instantaneously. Refunds may take minutes or manual intervention. The workflow must have explicit states such as PENDING_PAYMENT, CONFIRMED, PAYMENT_UNKNOWN, COMPENSATING, CANCELLED, and REQUIRES_RECONCILIATION where appropriate.

### 5.3. Transactional outbox

A classic event-publishing failure is: booking succeeds in the DB, then the process crashes before publishing the event; booking data changed, but consumers do not know to send emails or update indexes.

**Transactional outbox** closes this gap by writing the business change and the outbox event record inside **the same database transaction**. A separate publisher reads the outbox and sends messages to the broker; once sent, it marks them processed according to an appropriate strategy.

~~~mermaid
flowchart LR
    API["Booking API"] --> DB[("Booking DB: booking + outbox")]
    DB --> PUB["Outbox Publisher"]
    PUB --> Q["Message Broker"]
    Q --> C["Consumers"]
~~~

An outbox reduces the risk of losing events between commit and publish, but **does not automatically provide end-to-end exactly-once delivery**. The publisher can send a message and crash before marking it complete, resulting in duplicate delivery. Consumers still need idempotency/deduplication and outbox backlog monitoring.

## 6. Handling duplicate processing: idempotency and delivery semantics

In distributed systems, timeouts, retries, broker redeliveries, and consumer restarts mean a message can be processed more than once. Delivery semantics must be defined:

- **At-most-once:** delivered at most once; messages can be lost if failure happens at an inopportune time.
- **At-least-once:** delivered at least once when retry/recovery succeeds; duplicates may occur.
- **Exactly-once:** the scope of guarantee must be precisely defined; this property usually holds only within a bounded broker/transaction scope, and does not automatically extend across external databases, third-party APIs, and side effects.

Therefore, many production systems choose at-least-once delivery and design **idempotent** consumers.

### 6.1. Idempotency for write APIs

For a booking API, the client sends a unique Idempotency-Key for a single intent to create an order; the server stores the key along with the result/state so repeated calls return the prior outcome.

~~~http
POST /bookings
Idempotency-Key: 7f7c6a8d-example
Content-Type: application/json

{
  "roomId": "room-42",
  "checkIn": "2026-12-18",
  "checkOut": "2026-12-21"
}
~~~

The server must determine how the key is scoped by tenant/user/client and retained for how long; what error to return if the same key is sent with a different payload; whether a second request waits or receives status if the first is still in progress; what result a retry reads if the DB committed but the response was lost; and how business logic protects against retries after the key expires.

Idempotency is not just response caching. For write operations, transaction/database constraints must be strong enough that two concurrent requests with the same key cannot produce two outcomes.

### 6.2. Consumer deduplication

Event messages should carry a stable eventId. The consumer can record processed eventIds within the same transaction as its data updates. When the broker redelivers, the consumer recognizes the old event and avoids repeating side effects. For side effects outside the DB—such as sending emails or calling partners—you need strategies to minimize duplicates because not every provider supports idempotency.

## 7. Ordering, partitions, and consumer scalability

Not every event requires global ordering. Ordering requirements must be defined per **business entity**.

For example, a booking has events BookingCreated → PaymentAuthorized → BookingConfirmed. If BookingConfirmed arrives before BookingCreated due to parallel processing or replay, the consumer must detect the version/state and handle it safely.

Common approaches:

- **Partition by entity key:** events for the same bookingId go to the same partition key to preserve ordering within the broker's guarantees.
- **Sequence/version numbers:** consumers compare versions to ignore stale events or detect missing events.
- **State machines:** accept only valid state transitions; out-of-order events are retried, parked, or sent to reconciliation.
- **Idempotent processing:** redelivering the same event does not duplicate effects.

Increasing partitions and consumers can raise throughput, but also complicates ordering, rebalancing, cost, and observability. A hot partition can cap throughput for a large tenant/entity.

## 8. Retries, backoff, circuit breakers, and dead-letter queues

Retries help overcome transient failures, but unbounded or synchronized retries can turn a small blip into a widespread outage.

| Error type | Common handling approach |
| --- | --- |
| Connection timeout or transient network error | Bounded retries with exponential backoff and jitter, only when operation is safe |
| HTTP 429 | Honor Retry-After if provided, slow down rate |
| Transient HTTP 5xx | Retry per policy, bounded by attempt count and deadline |
| HTTP 4xx due to invalid data/permissions | Do not auto-retry unless input/permissions change |
| Schema/serialization error | Quarantine or DLQ; fix consumer/schema before replaying |
| Permanent business error | Mark failed or require business handling; do not retry indefinitely |

Example of exponential backoff with jitter:

~~~text
delay(attempt) = random(0, min(maxDelay, baseDelay * 2^attempt))
~~~

Limit attempt counts, total retry duration, and job deadlines. Avoid having the client, API gateway, SDK, and worker all independently retry the same request, as call counts can multiply dramatically.

### 8.1. Circuit breakers and bulkheads

- **Circuit breaker** temporarily stops calling a dependency when error/timeout rates exceed a threshold; after a wait period, allows a few probe requests to test recovery.
- **Bulkhead** limits resources allocated to each dependency group or task type so one slow dependency does not exhaust threads, connections, or workers for everything else.
- **Timeouts/cancellation** limit how long resources are held for work that can no longer succeed.

These mechanisms are valuable for synchronous calls to payment providers or internal services with differing reliability levels.

### 8.2. Dead-letter queue (DLQ)

Messages that exceed retry limits or hit unprocessable errors can be routed to a DLQ/quarantine. A DLQ is not a place to dump data and forget it; you need alerts when message count/age rises, storage of failure reasons and correlation IDs, error classification, replay only after root causes are fixed, and access controls on reading/replaying because messages may contain customer data.

## 9. Designing queues, pub-sub, and event contracts

| Pattern | Model | Best fit |
| --- | --- | --- |
| Work queue | Each message is typically picked up by one worker in a group | Image processing jobs, sending emails, background tasks |
| Publish-subscribe | One event can have multiple independent subscribers | BookingConfirmed for notifications, analytics, and index updates |
| Stream/log | Stores ordered sequence of events with offsets/retention; consumers read by position | Event history, analytics, replay, and streaming |
| Request/reply over broker | Command sent via message and caller awaits correlated response | Integrations needing transport decoupling while still needing a reply; requires timeout consideration |

Do not send an event into a work queue if multiple consumer groups all need to receive it; depending on the broker, consumers in the same group typically compete for messages, whereas distinct groups/subscriptions receive independent copies per platform semantics.

An event should have a traceable envelope:

~~~json
{
  "eventId": "evt-9b4a",
  "eventType": "BookingConfirmed",
  "schemaVersion": 1,
  "occurredAt": "2026-12-18T08:30:00Z",
  "producer": "booking-service",
  "correlationId": "req-7a21",
  "aggregateId": "booking-42",
  "sequence": 3,
  "data": {
    "bookingId": "booking-42",
    "customerRef": "customer-18"
  }
}
~~~

Do not embed full payment details, tokens, or personal data in events if consumers do not need them. Prefer reference identifiers and enforce access control on detailed records. Message contracts need an owner, schema version, compatibility rules, and support windows for older versions.

### 9.1. Schema evolution

When adding fields, changing types, or altering semantics, consider running older consumers and older messages still within retention. You can add optional fields with clear defaults, version incompatible changes, deploy compatible consumers first or follow expand-and-contract, and never reuse field names with new meanings.

## 10. Observing synchronous and asynchronous communication

Both models require different observability signals, yet should share **correlation/trace context** to connect the end-to-end journey:

| Aspect | Synchronous | Asynchronous |
| --- | --- | --- |
| Latency | End-to-end request time, per-dependency p95/p99 | Time from enqueue to completion, message age, and consumer processing time |
| Errors | HTTP statuses, timeouts, connection resets, circuit state | Publish failures, retry counts, redeliveries, poison messages, DLQ |
| Throughput | Requests/second, concurrent requests, connection pools | Messages/second, queue depth, consumer lag, partition utilization |
| Correlation | Trace ID, spans for each call | Correlation ID, event ID, causation ID, and context across consumers |
| SLOs | Percentage of requests completing within deadline | Percentage of jobs/events completing within business window |
| Operations | Dependency dashboards, timeout budgets, and runbooks | Backlog age, DLQ, replay procedures, and consumer ownership |

**Low queue depth does not always mean healthy.** If consumers are hung and messages are not being acknowledged, look at oldest message age, processing rate, consumer health, and delivery errors. Short-term queue spikes during campaigns may be normal if processing catches up within SLO.

For asynchronous communication, track the time from when the business event occurs until all critical side effects finish—not merely the time until the broker accepts the message.

## 11. Securing communication and managing permissions

Both synchronous and asynchronous paths must authenticate senders, check authorization, and protect data:

- Use TLS for network connections; mTLS when mutual authentication between workloads is required.
- Service identity and least-privilege IAM for publishing/consuming each queue/topic.
- Never treat being in the same VPC or cluster as sufficient trust.
- Encrypt data at rest in brokers/storage as required; manage keys and secret lifecycles.
- Validate payloads, schemas, sizes, and origins; defend against forged/replayed messages.
- Restrict permissions to read/replay DLQs and event histories; audit administrative actions.
- Avoid logging tokens, credentials, and sensitive payload contents.

For example, only booking-service is allowed to publish BookingConfirmed; notification-service and search-indexer have separate subscriptions. The notification worker does not need read access to the transactional database or permission to republish events to business topics. Scoped permissions reduce blast radius if a consumer is compromised.

## 12. Costs and operational trade-offs

Synchronous communication usually has fewer intermediary components, but increases direct coupling, connections, held threads, and timeout risks. Asynchronous adds brokers, message storage, network transfer, consumer runtimes, monitoring, DLQs, and late-data handling.

| Criterion | Synchronous | Asynchronous |
| --- | --- | --- |
| User response latency | Direct result when dependencies are fast | May only return an accepted status |
| Temporal coupling | Higher: recipient must be available at call time | Lower: can process later |
| Burst smoothing | Requires direct capacity, rate limits, and backpressure | Bounded queues can buffer load |
| Consistency | Easier to present immediate result in-flow, though multi-service still needs a transaction strategy | Often has convergence lag; needs state machines and consumer idempotency |
| Debugging | Direct call traces | Via correlation IDs across messages/retries |
| Operations | Fewer brokers/consumers | Adds backlog, DLQs, schemas, replay, and retention |
| Cost | Call-path compute and connections | Brokers, message storage, egress, workers, and observability |

When calculating total cost, do not compare just the price of a REST request against a message. Factor in retry counts, connection hold time, waiting compute, broker throughput, retention, message size, cross-zone/region traffic, and operational labor. A poorly handled asynchronous workflow can cost more than a simple synchronous call.

## 13. Selection workflow by business flow

~~~mermaid
flowchart TD
    A["Identify journey and business outcome"] --> B{"Does the caller need an immediate result?"}
    B -->|Yes| C["Synchronous: latency budget, timeouts, and fallback"]
    B -->|No| D["Asynchronous: command/event, queue, and job status"]
    C --> E{"Multiple services / side effects?"}
    D --> F["Design idempotency, ordering, retries, and DLQ"]
    E -->|Yes| G["Transaction strategy / Saga / outbox"]
    E -->|No| H["API contract and error handling"]
    G --> I["Security, observability, capacity, and DR"]
    H --> I
    F --> I
    I --> J["Load/failure testing and ADR"]
~~~

For each flow, document the business goal, query/command/event semantics, p95/p99 targets and deadlines, source of truth, consistency, ordering, idempotency, errors/retries/fallbacks, security, SLIs/SLOs, owner, runbook, and cost. Do not force asynchronous communication just because modern microservices are supposed to use events; nor force clients to wait for emails, reports, or analytics to finish when the work can run independently.

## 14. Practice lab: designing communication for a booking journey

**Context:** a customer selects a room, the system checks availability, requests payment, confirms the order, and sends an email. The payment gateway sometimes responds slowly and sends duplicate webhooks. The search index and reporting do not require instant updates.

### Tasks

1. Draw a sequence diagram for the room booking journey, distinguishing synchronous and asynchronous segments.
2. Define the POST /bookings API, a status resource for incomplete operations, and the idempotency contract.
3. Design the BookingConfirmed event including event ID, schema version, correlation ID, aggregate ID, and minimal required data.
4. Choose queue vs. pub/sub for email, search index, and analytics; explain consumer groups/subscriptions and retention.
5. Build a state machine for payment timeouts, duplicate webhooks, late webhooks, and refunds.
6. Choose outbox/inbox, retry, backoff, DLQ, and reconciliation strategies.
7. Define SLIs for synchronous APIs and asynchronous jobs; specify p95/p99, oldest message age, retry count, DLQ, and business completion.
8. Compare at least two options across reliability, latency, security, cost, and operations; record an ADR with conditions that trigger a revisit.

### Design matrix template

| Flow | Communication type | Completion criteria | Critical failure safeguards |
| --- | --- | --- | --- |
| Search rooms | Synchronous query | Results returned or explainable error | Timeouts, caching, rate limiting |
| Reserve room | Stateful synchronous command | Hold succeeded or rejected | Idempotency, transactions, concurrency control |
| Payment | Synchronous initiation + async webhook/event | Payment state verified | Idempotency, signature verification, reconciliation |
| Send confirmation email | Asynchronous | Provider/worker processed or final failure recorded | Bounded retries, DLQ, duplicate prevention |
| Update search index | Asynchronous event | Index reaches corresponding data version | Ordering/versioning, replay, and rebuild |
| Analytics | Asynchronous/stream/batch | Data processed within allowed window | Backlog monitoring, schema evolution |

### Completion criteria

- Do not confuse 202 Accepted with completed business processing.
- Write operations have idempotency and handling for unknown timeout outcomes.
- Events have appropriate schemas/identities/ordering and consumers handle duplicates safely.
- There is a plan for publish failures after commit, prolonged retries, and DLQs.
- User experience accurately reflects pending, succeeded, failed, or needs-reconciliation states.
- Load and failure test evidence is present; broker/consumer/observability costs are accounted for.

## 15. Well-Architected checklist before finalizing communication

- [ ] Each flow has clearly defined business requirements and outcomes.
- [ ] Synchronous calls are used only where the caller truly needs the result in the same interaction; timeouts stay within the latency budget.
- [ ] Asynchronous work has status tracking, deadlines, owners, and a way to notify outcomes.
- [ ] Commands, queries, and events are semantically distinguished.
- [ ] Cross-service transactions have a clear strategy (local transactions, Sagas, outbox/inbox, or reconciliation).
- [ ] Write APIs/message consumers have idempotency, duplicate handling, and deduplication rules.
- [ ] Ordering/partitioning/versioning is defined per entity when required by business logic.
- [ ] Bounded retries, exponential backoff/jitter, timeouts, circuit breakers, and DLQs have runbooks.
- [ ] Queues have size limits, backlog/oldest-age alerts, and plans for slow consumers.
- [ ] Schema evolution is compatible with older consumers and messages still in retention.
- [ ] TLS, workload identity, publish/consume IAM, DLQ read access, and data protection are defined.
- [ ] Correlation IDs and traces/logs/metrics span both requests and events.
- [ ] Broker, retention, message size, retry, compute, and data-transfer costs are estimated.
- [ ] Slow/disconnected dependencies, unavailable brokers, consumer crashes, and replays have been tested.
- [ ] An ADR documents trade-offs across reliability, security, performance, cost, and operations.

**Key takeaway:** synchronous communication fits when business logic needs direct feedback and dependencies can meet the time budget; asynchronous communication fits when work can finish later, needs decoupling, or must absorb bursts. Good architectures usually **combine both per flow**, while designing state, idempotency, transactions, observability, and recovery so the system behaves correctly even when networks or dependencies are imperfect.
