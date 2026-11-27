# Designing Synchronous APIs and Asynchronous Event Processing

## 1. Choosing the Right Communication Model in Serverless Architecture

In a serverless architecture, requests typically pass through an API Gateway, functions, or managed services; events can be ingested by queues, event buses, streams, or workflow engines. Choosing **synchronous** vs. **asynchronous** communication determines user experience, component coupling, fault tolerance, latency, cost, and operational complexity.

Synchronous APIs fit when the caller needs a result to continue immediately—for example, validating input, querying status, or creating a booking request and receiving a confirmation code. The caller waits for a response within the combined timeout budget of all participating layers.

Asynchronous event processing fits when work can complete after the initial request—such as sending email, updating a search index, issuing an invoice, or syncing data to analytics. The producer hands the message or event to an intermediary; consumers process independently and scale according to backlog.

**Asynchronous does not mean no response is needed.** The API should still confirm request acceptance, returning a job or resource ID for the caller to track. **Synchronous does not mean all work must live inside one function**: a function can call other services synchronously, provided the dependency chain is bounded and measured.

In the **CLOUD_ARCHITECTURE** module, this decision must align with business requirements and trade-offs across reliability, security, scalability, cost, and operations. Do not pick an event bus just to appear "fully serverless," nor chain synchronous calls across every service when the user does not need to wait for the result.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish synchronous request/response APIs from asynchronous events and messages.
2. Design serverless API paths with appropriate timeouts, authentication, load limits, and responses.
3. Choose queues, pub/sub, event buses, or workflows based on delivery and orchestration needs.
4. Handle at-least-once delivery, duplicates, retries, dead-letter queues, and idempotency.
5. Identify the dual-write gap and apply transactional outbox or equivalent patterns.
6. Evaluate eventual consistency, observability, security, and cost in event-driven systems.

## 2. The Two Communication Models and Typical Flows

### 2.1. Synchronous API: Caller Waits for Response

Example of a customer checking booking status:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as API Gateway
    participant F as API Function
    participant D as Booking Store
    C->>G: GET /bookings/{id}
    G->>G: AuthN, quota, request validation
    G->>F: Invoke request
    F->>D: Read booking
    D-->>F: Booking status
    F-->>G: 200 + response
    G-->>C: HTTP response
~~~

The caller receives the outcome within the same request cycle. Intermediary layers can handle authentication, rate limiting, routing, and request transformation. Functions can scale with load, though concurrency quotas, execution duration, payloads, networking, and service limits all need evaluation.

### 2.2. Asynchronous Events: Producer Does Not Wait for Consumers

Example where, after confirming a booking, the system sends an email and updates analytics:

~~~mermaid
flowchart LR
    API["Booking API"] --> DB[("Booking DB + Outbox")]
    DB --> Relay["Outbox relay"]
    Relay --> Bus[["Event bus / Queue"]]
    Bus --> Mail["Notification consumer"]
    Bus --> Analytics["Analytics consumer"]
    Bus --> Search["Search index consumer"]
    Mail --> Provider["Email provider"]
~~~

The Booking API can return a confirmed status once business data commits successfully. Notification and search index updates are processed afterward. Each consumer has its own scaling profile, retry policy, permissions, and lifecycle.

### 2.3. Quick Comparison

| Criterion | Synchronous API | Asynchronous processing |
|---|---|---|
| Caller feedback | Result within the same request | Typically returns accepted/job ID; final outcome arrives later |
| Duration | Bounded by total and dependency timeouts | Supports longer work; still needs message TTL/age limits |
| Temporal coupling | Caller depends on responding components | Producer is decoupled from consumer execution timing |
| Traffic spikes | Hits functions, DBs, and dependencies directly | Queues buffer spikes so consumers drain at sustainable pace |
| Transactions | Reflects immediate outcome, though chained calls become fragile | Typically involves intermediate states and eventual consistency |
| Failures | Caller sees errors directly if returned in time | Requires retries, DLQs, replay, and status-query paths |
| Complexity | Manage timeouts, retries, auth, and dependencies | Adds event schemas, duplicates, ordering, backlog, and consumer lifecycles |
| User experience | Fits actions requiring an immediate answer | Fits tasks where deferred completion is acceptable |

## 3. Designing Synchronous APIs for Serverless Workloads

### 3.1. Separating Responsibilities Between API Gateway and Functions

A serverless HTTP flow typically spans these layers:

| Component | Common responsibilities | Watch out for |
|---|---|---|
| DNS / edge | Domain names, TLS termination, regional routing if needed | Certificates, caching, DNS failover, deployment regions |
| API Gateway / HTTP front door | Auth integration, routing, quotas/rate limits, request sizing, access logs | Gateway timeouts, payload limits, policies, per-request costs |
| Function / handler | Business validation, short orchestration, calling dependencies | Cold starts, concurrency, runtime limits, memory, networking |
| Data/service dependency | Persist state, enforce permissions, execute domain logic | Connection pools, transactions, rate limits, timeouts |
| Observability | Metrics, logs, traces, correlation IDs | Data redaction, cardinality, sampling, retention |

Do not stuff all business logic into gateway configuration. Gateways suit edge auth/authz, routing, rate limits, and lightweight technical transforms. Critical business rules must be enforced by the service owning the data and behavior.

### 3.2. Setting Timeouts Using an End-to-End Time Budget

Suppose the caller's maximum wait budget is 2 seconds. If the gateway timeout is 2 seconds, the function timeout is 10 seconds, and the dependency timeout is 8 seconds, the gateway may drop the client connection while the function keeps running. That creates **orphaned work**, client retries, and duplicate side-effect risks.

Design should specify:

1. **End-to-end deadline:** maximum time allowed by the business from request to response.
2. **Per-dependency timeout:** strictly smaller than remaining deadline, leaving margin for processing and serialization.
3. **Cancellation:** when the caller cancels or the deadline expires, define whether work stops or completes/reconciles.
4. **Retries:** retry only transient errors with bounded attempts and total duration; use backoff/jitter.
5. **Idempotency:** for write operations, ensure repeated caller intents never cause duplicate business effects.

Illustrative timeout allocation:

| Layer | Budget |
|---|---:|
| Total client journey | 2,000 ms |
| Gateway/API front door | 1,800 ms |
| Function processing and response | 1,500 ms |
| Single DB/API dependency call | 700 ms |
| Remaining margin | Validation, serialization, and buffer |

These values are not provider defaults. Derive them from SLOs, p95/p99 latency distributions, and actual platform limits.

### 3.3. Defining Clear HTTP Contracts

An API contract should specify:

- Method, path, request/response schemas, versioning, and required fields.
- HTTP status codes and error semantics; distinguish validation, auth, conflict, throttling, and dependency errors.
- Authentication/authorization, tenant scope, and resource access control.
- Idempotency key or equivalent mechanism for create/charge operations.
- Timeouts, rate limits, payload limits, pagination, and caching where appropriate.
- Correlation/request IDs to stitch gateway logs, function logs, and dependency traces.

Example request to create a reservation:

~~~http
POST /v1/reservations
Authorization: Bearer <access-token>
Idempotency-Key: 83c2d6f0-3c64-4c8e-a4fd-4bdfb1a8c5c2
Content-Type: application/json

{
  "propertyId": "home-25",
  "checkIn": "2026-12-10",
  "checkOut": "2026-12-14",
  "guestCount": 2
}
~~~

If the operation completes synchronously within budget, the API can return `201` with the created resource. If it only initiates a longer process, the API should return `202 Accepted` with a job/operation ID and status URL—never pretend business completion has occurred.

Example response accepting an asynchronous request:

~~~http
HTTP/1.1 202 Accepted
Location: /v1/operations/op-9f24
Content-Type: application/json

{
  "operationId": "op-9f24",
  "status": "ACCEPTED",
  "statusUrl": "/v1/operations/op-9f24"
}
~~~

Status APIs must define retention periods, update freshness, polling limits, and access permissions. Aggressive polling increases load; consider webhooks, authenticated callbacks, or notification channels when appropriate.

### 3.4. Protecting APIs Under Traffic Spikes

- **Authentication and authorization:** authenticate callers, verify tenant/owner and scopes. Token validation at the API Gateway does not replace object-level authorization.
- **Rate limiting / throttling:** by client, API key, tenant, or operation; return `429` with clear retry guidance when throttled.
- **Concurrency control:** cap function concurrency or DB connections; elastic function scaling does not mean infinite DB scaling.
- **Payload validation:** enforce size limits and schema validation; never trust client inputs.
- **WAF / network policy:** guard ingress according to the threat model without replacing application logic.
- **Secrets:** retrieve from secret management services via workload identity; never bake static credentials into images or source code.

## 4. Choosing Queues, Pub/Sub, Event Buses, or Workflows

Asynchronous patterns serve distinct purposes.

| Pattern | How it works | Use when | Watch out for |
|---|---|---|---|
| **Queue / work queue** | Messages are delivered to one consumer/worker in a pool | Work needs logical once-only processing despite redeliveries | Visibility timeouts, ack/delete, retries, DLQs, competing consumers |
| **Pub/Sub** | One message is broadcast to multiple subscriptions | Multiple systems need the same notification | Each subscription owns independent backlogs, retries, and permissions |
| **Event bus** | Events route by rules to targets/consumers | Integrating domains/services, filtering by event type/attributes | Schemas, rule ownership, ordering, and provider delivery behavior |
| **Stream** | Ordered/offset-indexed records retained in partitions for a window | High-volume continuous records, replay, offset/window processing | Partition keys, consumer lag, retention, throughput |
| **Workflow orchestration** | Multi-step state transitions are explicitly coordinated | Long processes with branches, waits, retries, compensation | State transitions, timeouts, per-step costs, permissions |

Service names vary by cloud provider; do not assume Queues, Event Buses, and Streams share identical semantics. Before selecting, clarify requirements for **fan-out, ordering, retention, replay, throughput, delivery guarantees, latency, DLQs, and cost**.

### 4.1. Choosing Queues for Task Processing

Example: an email worker consumes `SendReservationConfirmation` messages. The queue absorbs traffic bursts while multiple workers process in parallel. Consumers acknowledge/delete messages only after recording completion appropriately. If a worker crashes mid-flight, the message becomes eligible for redelivery.

### 4.2. Choosing Pub/Sub or Event Buses for Multiple Consumers

A `ReservationConfirmed` event may interest Notification, Loyalty, and Analytics services. The producer emits one event following a contract; independent consumers subscribe via subscriptions or routing rules. One slow consumer does not necessarily block others, depending on broker capabilities and configuration.

### 4.3. Choosing Workflows for Multi-Step Processes

Example: a flow that reserves inventory, requests payment, confirms the booking, and releases holds or issues refunds on failure. A workflow engine persists state and coordinates retries, waits, and branches. However, workflows do not remove the need for idempotent activities and reconciling indeterminate outcomes from external providers.

## 5. Designing Event Contracts and Ownership

### 5.1. Commands vs. Events

- **Command:** requests a component to perform an action, typically with one responsible owner. E.g., `CreateReservation` or `ChargePayment`.
- **Event:** announces a fact that has happened, named in past tense, potentially consumed by many subscribers. E.g., `ReservationConfirmed` or `PaymentCaptured`.

Never emit an event named `ReservationCreated` when the reservation is merely requested and still awaiting payment. Event names must reflect facts that have actually occurred and committed per business rules.

### 5.2. What Should an Event Contain?

~~~json
{
  "eventId": "evt-84ce",
  "eventType": "reservation.confirmed",
  "schemaVersion": 1,
  "occurredAt": "2026-11-18T03:00:00Z",
  "producer": "booking-service",
  "correlationId": "req-7ab2",
  "reservationId": "rs-1732",
  "propertyId": "home-25"
}
~~~

A contract typically needs:

- **eventId:** unique identifier allowing consumers to detect duplicates.
- **eventType and schemaVersion:** event meaning and schema version.
- **occurredAt:** when the business event occurred—do not confuse with consumer ingestion time.
- **producer/source:** component emitting the event.
- **correlationId/causationId:** ties processes and causal triggers together when useful.
- **Minimal business payload:** enough for consumers to act without unnecessarily copying sensitive data.

Events are contracts between components. Never publish raw database rows or internal entities directly if doing so couples consumers to internal schemas. Schema evolution requires backward-compatibility strategies, consumer verification, and deprecation windows for older versions.

### 5.3. Events Are Not Logs

Logs record diagnostics for troubleshooting. Events are integration contracts that consumers use to drive business state changes. Never use unstructured text logs as a message bus, and never dump all technical logs into business events.

## 6. Delivery Semantics: At-Most-Once, At-Least-Once, and Exactly-Once

Understand the semantics of both the intermediary broker and consumers before promising an event is processed once.

| Semantics | General meaning | Implication |
|---|---|---|
| **At-most-once** | Messages may be lost, but not redelivered within the scope modeled | Fits disposable signals; unsuitable for critical work without extra safeguards |
| **At-least-once** | Retries/redeliveries increase delivery assurance; duplicates possible | Consumers must implement idempotency and deduplication |
| **Exactly-once** | Meaningful only within specific mechanisms and transaction boundaries | Does not guarantee end-to-end business side effects across DB, broker, and external APIs occur once |

Many queue/serverless event integrations operate with **at-least-once** delivery or can redeliver under failure conditions. Timeouts can leave producers/consumers unsure whether the prior operation succeeded. If a consumer writes to the DB and crashes before acknowledging the message, the broker redelivers it.

Consequently, standard practice is **at-least-once delivery + idempotent processing**. For external providers, pass provider-supported idempotency keys, persist request/response state, and reconcile indeterminate outcomes.

## 7. Idempotency: Repeating Execution Without Repeating Side Effects

An idempotent operation can execute multiple times with the same request identifier without producing unintended duplicate business side effects.

Example: a consumer receives `ReservationConfirmed` twice. Simply sending an email on each receipt sends the customer two emails. Use a deduplication table keyed by `eventId` or an appropriate business key:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Logical flow:

1. Consumer opens a transaction.
2. Attempts to insert `(consumer, eventId)` into `processed_events`.
3. If the key already exists, treat it as an already-processed duplicate and skip side effects.
4. If new, perform the business DB update inside the same transaction.
5. Commit before acknowledging the message per broker semantics.

Illustrative pseudocode:

~~~text
handle(message):
    begin transaction
    if insert_processed_event(consumer, message.eventId) conflicts:
        commit
        acknowledge(message)
        return

    apply_business_update(message)
    commit
    acknowledge(message)
~~~

The transaction above covers only the database controlled by the consumer. When side effects call an email provider or payment API, a DB transaction cannot atomically span external networks. Use provider idempotency keys, operation state tracking, outboxes, or reconciliation—never claim end-to-end exactly-once merely because a dedup table exists.

Idempotency also requires defining **key scope and retention**. Purging processed-event records too early while the broker can still replay older messages reopens the window for duplicate execution.

## 8. Retries, Backoff, Visibility Timeouts, and DLQs

### 8.1. Distinguishing Transient vs. Unrecoverable Errors

| Error class | Examples | Typical handling |
|---|---|---|
| Transient | Network timeouts, 429, brief 5xx, overloaded dependency | Bounded retries with backoff/jitter |
| Permanent/business | Invalid schema payload, invalid account, missing business authorization | Do not retry indefinitely; record error and handle per contract |
| Unknown outcome | Provider processed request but response was lost | Query using idempotency key or reconcile |
| Poison message | Message consistently crashes consumer or fails parsing | Quarantine, route to DLQ, investigate and fix consumer/schema |

### 8.2. Exponential Backoff and Jitter

A common strategy increases delay exponentially between attempts while adding jitter so consumers do not retry simultaneously:

\[
delay_n = \min(maxDelay,\ baseDelay \times 2^n) + jitter
\]

This formula is illustrative. Define max attempts, max elapsed time, concurrency caps, and error-specific rules. Synchronized retries without jitter cause a **thundering herd** and prolong dependency overload.

### 8.3. Visibility Timeout / Message Lease

In queues with visibility timeouts, a message is hidden while a consumer processes it. If the consumer fails to ack/delete before timeout expiry, the message reappears. Set the timeout longer than normal processing duration, yet short enough that messages do not stall excessively if a worker dies.

If processing runs longer than expected, some services support extending the visibility/lease timeout; be careful with hung workers or retries. Visibility timeouts are not permanent locks and do not replace idempotency.

### 8.4. Dead-Letter Queues

After a configured number of receives/retries or error conditions, messages can move to a **dead-letter queue (DLQ)**. A DLQ isolates unprocessable messages so the main pipeline keeps flowing, while creating a backlog that must be actively managed:

- Alert on message count, oldest message age, and DLQ ingress rate.
- Preserve event ID, source, error category, retry count, and correlation ID.
- Replay only after fixing the root cause and verifying duplicate/ordering impact.
- Maintain triage procedures, small-batch redrive, rate limits, and authorized permissions.
- Configure appropriate retention; never leave sensitive data in DLQs indefinitely.

**A DLQ is not a place to throw errors away.** It requires an owner, runbook, dashboard, and business policy for messages that cannot be processed automatically.

## 9. The Dual-Write Problem: DB Commits and Event Publishing

A common bug in event-driven systems:

~~~text
1. Booking function writes the booking to the database.
2. Function publishes ReservationConfirmed to the event bus.
~~~

If step 1 succeeds and the function crashes before step 2, the booking is confirmed yet consumers never receive the event. Conversely, if the function publishes first and the DB transaction rolls back, consumers receive an event with no backing business state.

### 9.1. Transactional Outbox

An outbox records the business change and the event to publish inside the **same database transaction**:

~~~sql
BEGIN;

UPDATE reservations
SET status = 'CONFIRMED'
WHERE reservation_id = 'rs-1732';

INSERT INTO outbox_events (
    event_id, event_type, payload, created_at, published_at
) VALUES (
    'evt-84ce',
    'reservation.confirmed',
    '{"reservationId":"rs-1732"}',
    CURRENT_TIMESTAMP,
    NULL
);

COMMIT;
~~~

A publisher/relay reads unpublished outbox rows, delivers them to the broker, and marks them published. If the publisher crashes after publishing but before updating `published_at`, the event may be sent again; consumers still require idempotency.

### 9.2. Implementation Options

| Approach | Best when | Trade-offs |
|---|---|---|
| **Transactional outbox + polling** | Relational DB, moderate throughput, simple operational control | Polling latency, query load, and operating the publisher |
| **Outbox + CDC** | High event volumes requiring continuous change capture | Adds CDC infrastructure, schema/offset management, and monitoring |
| **Provider integration/transaction feature** | Platform ties event emission directly to transactions/streams | Tied to provider semantics and limits |
| **Direct dual-write** | Only when explicit loss/duplication tolerance is documented | Creates inconsistency windows; unsuitable for critical workflows |

Serverless does not automatically make dual-writes safe. Even a short-lived function can suffer timeouts, retries, process termination, or network failures between two side effects.

## 10. Long-Running Flows: Sagas and Workflow Orchestration

When a business process spans multiple services and cannot share a single transaction, use a **Saga**: a sequence of local transactions where each step has a compensating action if the flow cannot continue.

Booking example:

~~~mermaid
flowchart TD
    Start["Booking request"] --> Hold["Hold inventory"]
    Hold --> Charge["Request payment"]
    Charge --> Paid{"Payment succeeded?"}
    Paid -->|Yes| Confirm["Confirm booking"]
    Confirm --> Notify["Emit confirmation event"]
    Notify --> Done["Completed"]
    Paid -->|No| Release["Release hold"]
    Release --> Failed["Booking failed"]
    Confirm -->|Cannot confirm| Refund["Request refund"]
    Refund --> Compensated["Reconcile / compensate"]
~~~

This simplified diagram is illustrative. Production systems must model intermediate states, timeouts, indeterminate payment outcomes, retries, failed compensations, and manual intervention.

### 10.1. Orchestration vs. Choreography

- **Orchestration:** a workflow/state machine coordinates sequence, branches, waits, retries, and compensation. Provides clear centralized visibility, though the workflow itself becomes an artifact to maintain and can accumulate complex coordination logic.
- **Choreography:** services react to each other's events without a central coordinator. Reduces direct coordination coupling, yet overall flows become harder to trace, prone to event cycles, and difficult to assign ownership when state diverges.

Base the choice on step count, branching, wait durations, reconciliation needs, and auditability. You do not need a Saga for every two-service API call; if a domain fits within one local transaction boundary, keep it simple.

## 11. Combining Synchronous APIs and Asynchronous Events

Well-designed architectures frequently combine both:

- Client calls a synchronous API to authenticate, authorize, validate, accept the request, and receive an operation ID or result.
- The owning component commits business state and writes an outbox/event record.
- Queues/event buses distribute events to consumers.
- Consumers update read models, send notifications, or run secondary tasks.
- Clients poll status via an API or receive authenticated callbacks.

Example:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Booking API
    participant D as DB + Outbox
    participant B as Event Bus
    participant N as Notification
    participant S as Search Index
    C->>A: POST /reservations + idempotency key
    A->>D: Validate + write booking + outbox
    D-->>A: Commit
    A-->>C: 202 / 201 + operation URL
    D->>B: Relay ReservationConfirmed
    B-->>N: Deliver event
    B-->>S: Deliver event
    N->>N: Send confirmation (idempotent)
    S->>S: Update search read model
    C->>A: GET /operations/{id}
    A-->>C: Current business status
~~~

Statuses returned by the API must clearly distinguish **accepted**, **processing**, and **business confirmed**. Never return `201` if a resource is only queued and not yet created per API semantics; return `202` with an operation resource instead.

### 11.1. Eventual Consistency and User Experience

After booking confirmation, search indexes or loyalty balances may lag by a few seconds. UIs should account for propagation delay:

- Return operation status and refresh using backed-off intervals.
- Display a "processing" state until terminal confirmation arrives.
- Read from the source of truth for critical actions rather than confirming transactions against stale read models.
- Publish event-to-consumer latency targets if required by the business.
- Reconcile if consumers miss events or DLQs retain messages too long.

## 12. Security for APIs and Event-Driven Systems

### APIs

- Authenticate caller identities; enforce authorization per resource and tenant.
- Enforce TLS and proper certificate management.
- Apply rate limiting, schema validation, request size limits, and WAF where appropriate.
- Never trust client-supplied API keys or headers without verification.
- Never log access tokens, secrets, payment details, or full sensitive payloads.
- Grant functions least-privilege workload identities/roles for DBs, queues, and secrets.

### Queues, Topics, and Event Buses

- Grant producers permission to publish only required event types; consumers subscribe only to needed topics/queues.
- Isolate permissions by environment and trust domain; avoid a single function role that can read every queue.
- Encrypt in transit and at rest; manage keys per data classification.
- Govern schema registries/event catalogs, rule edits, and consumer subscriptions.
- Avoid unnecessary sensitive payloads; pass controlled references/tokens when consumers must fetch data.
- Audit changes to policies, queue subscriptions, redrives, and replays.

An event bus is an integration surface. A producer can inadvertently expose personal data to more consumers than intended; enforce data minimization and subscription access control from day one.

## 13. Observability and Operations in Serverless

An event-driven architecture requires end-to-end visibility from request to events and consumers—not just function invocation counts.

| Scope | Metrics/logs to monitor | Operational question |
|---|---|---|
| API Gateway | Request count, 4xx/5xx, latency, throttling | Are callers receiving responses within SLO? |
| Function | Invocations, errors, duration, cold starts (where available), concurrency, throttles | Are functions timing out or hitting concurrency caps? |
| Queue | Visible/in-flight messages, oldest message age, receive count | Are consumers keeping pace with producers? |
| Event bus | Matched/delivered/failed invocations, retries, rule failures | Are events routing to the intended targets? |
| Consumer | Success/errors, duration, idempotency duplicate count | Are events processed accurately by business logic? |
| DLQ | Message count, age, error categories, redrives | Are stalled messages awaiting owner action? |
| Workflow | Execution state, duration, failed/timed-out steps | Which step is blocking the process? |
| Data/dependencies | DB connections, throttling, locks, provider health | Is the bottleneck in storage or downstream services? |

### 13.1. Tracing Across Asynchronous Boundaries

Propagate **correlation IDs / trace context** via message attributes or envelopes to link API requests to events and consumers. Never assume every broker or SDK automatically preserves distributed trace context; integrate and test end-to-end.

An asynchronous trace should reveal:

1. Which request produced the event.
2. When the event was committed and published.
3. When each consumer received and started processing it.
4. Downstream calls and their outcomes.
5. Event-to-consumer latency, retry counts, and terminal state.

### 13.2. Journey-Driven Alerting

Alerts on rising queue age are helpful only when tied to business impact: are confirmation emails arriving too late, or are invoices missing deadlines? Define SLIs/SLOs across both synchronous requests and async flows—such as percentage of events processed within latency targets, operation completion rates, and DLQ error counts.

Avoid paging on single failed invocations when controlled retries are active; instead alert on terminal failures, backlog growth, message age, and business outcomes.

## 14. Cost and Performance

Serverless pricing typically maps to requests/invocations, execution time, memory/compute, data transfer, queue/event operations, logging, and workflow transitions. Asynchronous processing absorbs spikes and scales consumers to backlog, while introducing costs for:

- Queues/topics/event buses, message storage, and publish/receive/delete operations.
- Function invocations and consumer execution time multiplied by retries.
- DLQs, replays, event retention, and observability.
- Cross-zone/cross-region data transfer or managed service traffic.
- Log/trace volume and retention.
- Engineering and on-call effort to operate pipelines, duplicates, and reconciliation.

| Design lever | Potential improvement | Risks/trade-offs |
|---|---|---|
| Message batching | Fewer invocations and lower per-record cost | Partial batch failures require per-record isolation; higher latency |
| Concurrency tuning | Protects DBs and downstream dependencies | Backlog grows if capped too low |
| Memory/runtime tuning | Cuts duration or lowers cost per execution model | Higher memory can raise unit rates; requires benchmarking |
| Bounded retries | Recovers transient failures | Multiplies compute charges and downstream load |
| Event filtering | Eliminates unnecessary invocations | Misconfigured rules can silently drop business events |
| Region/placement choices | Lowers latency and cross-region transfer | Impacts data residency, availability, and cost |
| Log sampling/retention | Controls observability spend | Over-aggressive pruning loses forensic evidence |

Never optimize solely for cost per invocation. Measure **cost per completed business transaction**, factoring in retries, downstream usage, logs, queues, and manual error remediation.

## 15. Case Study: Booking Confirmation and Notifications

**Context:** A lodging rental platform accepts booking requests via API. Bookings must verify/confirm availability, persist data, and then send emails and update a search index. The email provider is occasionally slow; promotional campaigns create sharp traffic bursts.

### 15.1. Selecting the Synchronous Path

Critical-path work:

- Authenticate caller and verify booking authorization for the property.
- Validate pricing/eligibility rules.
- Enforce the invariant preventing double bookings.
- Persist booking state and return the result or operation ID.

Work that does not need to block the request:

- Sending confirmation emails.
- Updating the search index.
- Updating analytics or loyalty points if policy allows slight delay.

### 15.2. Proposed Architecture

~~~mermaid
flowchart TD
    Client["Web / Mobile"] --> Gateway["API Gateway"]
    Gateway --> Function["Booking function"]
    Function --> DB[("Booking DB")]
    Function --> Outbox[("Outbox in same transaction")]
    Outbox --> Publisher["Outbox publisher"]
    Publisher --> Bus[["Event bus / Queue"]]
    Bus --> Email["Notification function"]
    Bus --> Index["Search index function"]
    Email --> Provider["Email provider"]
    Function --> Status["Operation/status API"]
~~~

*This is a logical diagram. In an implementation, the DB and outbox must be written in the same transaction; the publisher can be a function, scheduled worker, or CDC pipeline. The status API can read the business DB directly or query a dedicated read model.*

### 15.3. Failure Scenarios to Handle

| Scenario | Desired behavior | Mechanism |
|---|---|---|
| Client times out and retries same intent | No duplicate booking created | Durable idempotency key returning stored result |
| DB commits before publisher runs | Event is still published later | Outbox relay and oldest-unpublished-event metric |
| Publisher sends event then crashes before marking published | Consumer may receive a duplicate | `eventId` and idempotent consumer |
| Email provider returns 429/5xx | Bounded retries with backoff; valid booking is never rolled back | Queue retry policy, DLQ, and alerting |
| Search consumer hits schema error | Booking keeps valid business state | Schema compatibility, DLQ, fix consumer then replay |
| Queue backlog grows | Protect downstream dependencies, signal delay | Concurrency caps, backlog/age-based autoscaling |
| Payment provider times out with unknown outcome | Never blindly recharge | Provider idempotency key and reconciliation |

### 15.4. Acceptance Criteria

- Concurrent requests with the same idempotency key never create two bookings.
- An email provider outage never loses committed bookings.
- Outbox rows are never abandoned; unpublished events exceeding age thresholds trigger alerts.
- Consumers receiving the same event multiple times produce no unintended duplicate side effects.
- DLQs have owners, dashboards, and controlled replay procedures.
- API statuses accurately distinguish accepted, processing, confirmed, and failed states.
- Event payloads carry only minimal required fields, and consumers hold least-privilege permissions.
- Dashboards track request latency, event processing latency, backlog, terminal errors, and cost per transaction.

## 16. Common Pitfalls

| Pitfall | Consequence | How to improve |
|---|---|---|
| Using synchronous APIs for all secondary steps | Long requests, timeouts, cascading dependency failures | Keep critical path short; move secondary work to async when business allows |
| Making everything asynchronous | Callers lack clear outcomes, complex distributed state | Use async only when deferred completion is acceptable; expose operation status |
| Assuming queues guarantee single execution | Duplicates cause double charges, emails, or updates | Implement idempotency, deduplication, and reconciliation |
| Committing DB then publishing directly | Risk of lost events or publishing uncommitted state | Use transactional outbox/CDC |
| Unbounded retries | Poison messages, surging costs and load | Bounded retries, backoff/jitter, DLQs |
| Ownerless DLQs | Messages pile up, business workflows never complete | Age/count alerts, runbooks, controlled replay |
| Putting entire DB records in events | Schema coupling, data leaks, hard versioning | Business-contract payloads with data minimization |
| Ignoring consumer lag | API looks healthy while downstream falls behind | Track message age and event-to-effect latency |
| Scaling function concurrency without bounds | Overloads DBs, NAT gateways, and providers | Concurrency caps, queue buffering, load testing |
| Promising end-to-end exactly-once | Mismatched expectations and hard reconciliation | Document per-boundary semantics and design idempotent effects |

## 17. API and Event-Driven Design Review Checklist

### Synchronous APIs

- [ ] Request paths define deadlines and timeouts aligned with SLOs.
- [ ] Authentication, resource/tenant authorization, TLS, and rate limits are enforced.
- [ ] Request/response contracts, versioning, and error codes are explicitly defined.
- [ ] Write operations implement idempotency when callers can retry.
- [ ] Concurrency is bounded to match database and dependency capacity.
- [ ] Logs/traces carry request IDs without leaking secrets or unnecessary data.
- [ ] Long operations use an async operation model instead of holding connections open indefinitely.

### Events and Consumers

- [ ] Queue/pub-sub/event bus/stream/workflow choice matches fan-out, ordering, replay, and latency needs.
- [ ] Events include `eventId`, type, schema version, timestamp, source, and minimal payload.
- [ ] Producers/consumers enforce contract evolution and least-privilege publish/subscribe permissions.
- [ ] Delivery semantics are understood; duplicates and idempotency are handled.
- [ ] Retries are bounded with backoff/jitter, sensible visibility/lease timeouts, and an owned DLQ.
- [ ] DB commit–event publish gaps are closed using outbox/CDC or equivalent mechanisms.
- [ ] Consumers support safe replay and reconciliation without duplicate side effects.
- [ ] Backlog age, consumer lag, failed invocations, and event-to-effect latency are monitored.
- [ ] Payloads, retention, and logs comply with security and cost requirements.

### Business Processes

- [ ] Accepted, processing, succeeded, and failed states have clear meaning to users.
- [ ] Timeouts, indeterminate outcomes, compensation, and human intervention are modeled.
- [ ] SLOs and costs are measured per completed business flow, not only per invocation.
- [ ] Runbooks and owners exist for DLQs, stalled workflows, and reconciliation.

## 18. Hands-On Exercise

**Context:** A lodging rental platform exposes a booking API. After placing a hold, the system must charge payment, send email, update a search index, and stream data to analytics. The payment gateway may take several seconds or time out with an unknown result; the email provider occasionally returns 429; marketing campaigns multiply request volume severalfold.

Design a hybrid synchronous and asynchronous architecture:

1. Decide which steps must complete before responding and which can run asynchronously. Justify using business rules.
2. Define the API contract so callers can poll status when processing takes longer.
3. Choose queues, event buses, or workflows for each workload; explain where fan-out vs. orchestration is needed.
4. Propose event schemas for `ReservationConfirmed` and `PaymentCaptured`; identify sensitive data to exclude from payloads.
5. Design idempotency for callers, consumers, and the payment provider.
6. Describe how to solve the DB commit–event publish gap using outbox/CDC.
7. Define retries, backoff, DLQs, backlog alerts, and replay procedures.
8. Set timeouts/concurrency caps to protect the database, functions, and external providers.
9. Define SLIs/SLOs for API response time, workflow completion time, email latency, and payment success rate.
10. Analyze costs, security boundaries, and recovery when a consumer stops operating.

**Self-check hints:** The API can acknowledge requests or booking state per clear semantics; payment may require a stateful workflow and reconciliation for unknown results; email and analytics can typically run asynchronously. Never treat event publication as proof that consumers succeeded. Test failure scenarios: function crash right after DB commit, message delivered twice, consumer failing continuously, and provider charging successfully while the response is lost.

## 19. Takeaways

Synchronous APIs fit interactions needing an immediate answer and require proper deadlines, timeouts, auth, rate limits, and idempotency. Asynchronous processing fits deferred work, decoupling execution timing and absorbing load, while requiring disciplined management of **event contracts, delivery semantics, duplicates, retries, DLQs, eventual consistency, and observability**.

Strong serverless architectures combine both: APIs accept requests and communicate clear states; events drive post-commit work; consumers execute independently and recover safely. Designs must protect business invariants, close dual-write gaps, prevent unintended duplicate side effects, and validate outcomes with metrics covering user experience, reliability, security, performance, and cost.
