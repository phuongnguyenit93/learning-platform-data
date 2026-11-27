# Function Decomposition, Event Triggers, and Deployment Units

**Serverless** architecture enables development teams to focus on business logic while the platform manages most of the server provisioning, scaling, and execution environment. However, "no server management" does not mean an application is naturally decomposed properly or that responsibilities for reliability, security, cost, and operations disappear. When building a serverless system, three closely coupled decisions are **function decomposition, triggers/events, and deployment units**.

This lesson belongs to the **Serverless Architecture** chapter of the **Cloud Architecture** learning path. It covers how to translate business requirements into handlers, event flows, and deployment packages with sound boundaries. A function should represent a meaningful business operation or reaction, accept inputs through an explicit contract, execute within resource limits, and produce verifiable results or events. A deployment unit should balance release velocity, failure blast radius, access permissions, and level of independence.

After this lesson, you will be able to:

- Distinguish between a function, handler, trigger, event source, and deployment unit.
- Decompose an application into functions by business capability and operation, avoiding both monolithic functions and overly fragmented ones.
- Choose synchronous or asynchronous triggers based on response, durability, and fault-tolerance requirements.
- Design event contracts, retries, idempotency, ordering, dead-letter handling, and observability.
- Decide which functions should be deployed together and which require independent release units.
- Design IAM permissions, configuration, secrets, and resource limits per function.
- Evaluate serverless cost, performance, reliability, and operations with a Well-Architected mindset.

## 1. Foundational Concepts

In the Function-as-a-Service (FaaS) model, the provider initializes a function execution environment when a request or event arrives, manages the underlying execution infrastructure, and bills according to a service-specific pricing model. Naming and limits differ across platforms, but common concepts are as follows.

| Concept | Meaning | Example |
| --- | --- | --- |
| **Function** | A unit of logic that the platform can invoke to perform a task | CreateBooking, SendReceipt |
| **Handler** | Entry point that receives an invocation, validates input, and calls application logic | Function handling an HTTP request or message |
| **Trigger** | Configuration or source that invokes a function | HTTP route, queue message, object-created event, timer |
| **Event source** | Service or component that emits events/inputs to invoke a function | API gateway, message broker, object storage |
| **Event** | Record describing what happened or a request for work | BookingConfirmed, PaymentRequested |
| **Invocation** | A single call and execution of a function | One HTTP request or one message |
| **Runtime** | Language and code execution environment for the function | Java, Node.js, Python, or platform runtime |
| **Deployment unit** | Artifact and configuration released as a single version/lifecycle management unit | A function package or a group of functions |
| **Workflow/state machine** | Component orchestrating multiple steps, states, branches, and errors | Order placement, payment, and refund flow |

A function is a unit of logic, whereas a deployment unit is a release boundary. Depending on the platform or framework, one deployment unit may contain a single function or multiple handlers packaged together. Conversely, a large business process may span multiple independently deployed functions coordinated via queues, event buses, or workflows.

Do not confuse a trigger with an event contract. The trigger determines when and how a function is invoked; the event contract determines the data, semantics, and version of the message the function receives.

## 2. Decomposing Functions from Business Capabilities

A good starting point is business use cases and business events—not turning every method in code into a cloud function. For example, an equipment rental system includes operations such as creating a booking request, reserving inventory, confirming payment, sending receipts, expiring reservations, and generating reports.

Each operation can become a function or a step within a workflow. Boundaries depend on data requirements, transactions, latency, permissions, and operational patterns.

### 2.1. Criteria for a Well-Bounded Function

A function should have:

1. **Clear purpose:** describable as a single business action or reaction.
2. **Stable contract:** defined schema, validation, error semantics, and versioning.
3. **Testable responsibility:** verifiable success and failure conditions.
4. **Least privilege:** access only to the data, secrets, and services it actually needs.
5. **Appropriate trigger source:** intentional choice of HTTP, queue, event, schedule, or workflow.
6. **Realistic resource bounds:** duration, memory, concurrency, and payload within platform limits.
7. **Deterministic error behavior:** clear rules for what to retry, what to reject, and what requires manual intervention.

A function may invoke multiple internal domain/application layers. There is no need to turn every validation step or helper method into a separate cloud function, as doing so increases network hops, deployment count, and debugging complexity.

### 2.2. Decomposition Example for a Rental Platform

| Capability/use case | Suggested function | Responsibility |
| --- | --- | --- |
| Booking API | CreateBooking | Validate request, check permissions, and create initial request state |
| Asset reservation | ReserveInventory | Check availability and reserve assets while enforcing business invariants |
| Payment | RequestPayment | Call payment provider with an idempotency key, record pending state |
| Payment callback | HandlePaymentResult | Verify webhook, update payment state, and emit event |
| Notification | SendBookingNotification | Send email/SMS after confirmation event |
| Reservation expiration | ExpireReservation | Check expiration and release eligible reservations |
| Reporting | BuildDailyReport | Aggregate data outside the transactional path |

This is a starting point. ReserveInventory may need to share the same transaction boundary as the booking write if both use the same database and the business requires an atomic commit. If deployed separately over the network, state transitions and compensation steps must be designed; two independent functions cannot be assumed to share an ACID transaction.

### 2.3. Avoiding the Two Extremes

**Overly large function:** a single handler receives the booking request, verifies the customer, reserves inventory, charges payment, sends email, and generates a report. As a result, minor changes impact multiple capabilities; IAM permissions are overly broad; execution times are long; retries can re-run the entire chain; and isolating per-step failures becomes difficult.

**Overly small function:** one function per validation check or database query. As a result, invocations, network hops, configurations, permissions, logs, and deployments proliferate; orchestration latency and overhead can outweigh the benefits of splitting.

The goal is to draw boundaries where **business semantics, data ownership, scaling patterns, or operational lifecycles genuinely differ**.

## 3. Choosing Triggers Based on How Work Needs to Execute

A trigger is where an invocation begins. Choosing the wrong trigger can make it hard to meet latency targets, lose retry capabilities, or unintentionally let a single client consume excessive resources.

| Trigger | Invocation model | Use when | Design considerations |
| --- | --- | --- | --- |
| HTTP/API gateway | Synchronous request–response | Client needs an immediate answer | Auth, timeouts, payload limits, rate limits, status codes |
| Queue/message | Asynchronous, typically with retries | Deferred work, need to absorb bursts | Visibility/ack, retries, deduplication, DLQ, backpressure |
| Event bus | Publish–subscribe | Multiple independent consumers react to an event | Schema, routing, filtering, fan-out, versioning |
| Object storage event | Asynchronous on object change | Processing files, images, documents | Duplicates/ordering, object key/version, size |
| Scheduler/timer | Time-based or periodic invocation | Reports, cleanup, expiration, reconciliation | Time zone, missed schedules, duplicate runs, overlap |
| Stream | Continuous by record/batch | Telemetry, clickstreams, high-volume events | Partitions, ordering scope, checkpoints, lag |
| Workflow/state machine | Multi-step orchestration | Long-running or stateful processes | State persistence, timeouts, retries, compensation |

A specific service may use polling or push to connect an event source to a function. You must verify the platform's delivery semantics, especially delivery guarantees, wait times, acknowledgment behavior, and batch limits. Never assume every event trigger guarantees exactly-once delivery.

## 4. Choosing Synchronous vs. Asynchronous Execution

**Synchronous** execution fits when the caller needs a result to continue an interaction, such as validating a request or fetching current state. **Asynchronous** execution fits when work can complete later, needs to absorb traffic bursts, or has multiple independent consumers.

### 4.1. Synchronous Path

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as API Gateway
    participant F as CreateBooking
    participant D as Database
    C->>G: POST /bookings
    G->>F: Invoke synchronously
    F->>D: Validate and save booking
    D-->>F: Commit
    F-->>G: Booking ID + status
    G-->>C: 201 Created
~~~

The advantages are a straightforward request–response model, immediate feedback for the client, and fewer intermediate components. The risks are that response time is constrained by stacked timeouts across layers; functions waiting on a database or external service tie up concurrency; and client retries on timeout can create duplicate requests if the endpoint is not idempotent.

### 4.2. Asynchronous Path

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as API
    participant Q as Queue
    participant W as Worker Function
    participant D as Database
    C->>A: Send processing request
    A->>Q: Publish job
    Q-->>A: Accepted
    A-->>C: 202 Accepted + jobId
    Q->>W: Deliver message
    W->>D: Process and write status
    D-->>W: Commit
    W-->>Q: Ack
    C->>A: GET /jobs/{jobId}
    A-->>C: Processing status
~~~

The caller receives **job acceptance**, which does not mean the job has succeeded. The API should return `202 Accepted` with a tracking identifier when semantics fit, and provide a status endpoint or callback. You must ensure the message is durably persisted before responding, and define message TTL, failure notification, and terminal states.

### 4.3. Selection Matrix

| Requirement | Synchronous | Asynchronous |
| --- | --- | --- |
| Need immediate response to continue UI | Suitable | Only suitable if a pending state is acceptable |
| Long-running or unpredictable tasks | Prone to timeouts | Better suited |
| Burst absorption | Limited by concurrency/API quotas | Queue can buffer |
| Multiple independent consumers | Caller must coordinate | Event bus supports fan-out |
| Transaction needing immediate result | Suitable if short and transaction is sound | Requires a state model |
| Tolerance for temporary dependency outage | Caller is impacted while waiting | Retries, DLQ, and retention decouple timing |
| Observing long-running progress | Difficult if holding an HTTP request open | Can persist job state |

Both models can be combined: synchronous execution to validate and record the request, and asynchronous execution for heavy work or fan-out. There is no need to force an entire use case into a single communication style.

## 5. Designing Event Contracts

A well-designed event represents **something that has happened**, carrying an identifier, timestamp, source, and schema version. Avoid vague names like `UpdateData` when it is unclear what occurred or who owns the change.

Example business event:

~~~json
{
  "eventId": "evt-7f239a",
  "eventType": "BookingConfirmed",
  "schemaVersion": 1,
  "occurredAt": "2026-11-18T08:30:00Z",
  "producer": "booking-module",
  "correlationId": "req-18273",
  "subject": {
    "bookingId": "bk-100582",
    "customerId": "cus-207"
  },
  "data": {
    "reservationId": "rs-8041",
    "confirmedAt": "2026-11-18T08:29:58Z"
  }
}
~~~

The fields above are illustrative:

- **eventId:** unique identifier allowing consumers to detect duplicates.
- **eventType:** business-meaningful event name.
- **schemaVersion:** schema version enabling consumer compatibility as the contract evolves.
- **occurredAt:** timestamp when the business event occurred; receivers may also record ingestion time.
- **producer:** module/service responsible for emitting the event.
- **correlationId/trace context:** links the event back to the originating request.
- **Payload:** contains only the data consumers need; avoid broadcasting full records and PII.

### 5.1. Events vs. Commands

- **Event:** notifies that a fact has occurred, e.g., `BookingConfirmed`.
- **Command:** requests that a party perform an action, e.g., `RequestRefund`.

An event can have multiple subscribers and typically does not require the producer to know each consumer. A command has a single responsible target or a workflow managing its outcome. Clear naming prevents mistaking a pending payment request for a "payment confirmed" event.

### 5.2. Schema Evolution and Compatibility

Consumers may deploy slower than producers. When adding a new field, specify whether it is optional, its default value, and how older consumers handle unrecognized fields. When changing types or removing fields, establish a versioning roadmap and measure how many consumers still rely on the older schema.

Do not use internal classes or runtime-coupled object serialization as an event contract. Payloads should follow a validatable, versioned, and documented schema, commonly using JSON, Avro, Protobuf, or a platform-supported format.

## 6. Retries, Duplicates, and Idempotency

Event-driven systems generally must assume a message can be delivered more than once. For example, a worker might update the database successfully but fail before acknowledging; the queue may redeliver the message and the consumer receives the same work again.

**Idempotency** is the property where processing the same request or event multiple times produces no unintended side effects beyond the first execution.

Common implementation pattern:

1. Producer attaches a stable `eventId` or `idempotencyKey`.
2. Consumer stores processed IDs in durable storage with an appropriate unique constraint.
3. Record the idempotency marker and business outcome within an appropriate transaction.
4. If the same ID arrives again, return or preserve the previous result instead of re-applying side effects.
5. Set retention for deduplication markers longer than the retry/replay window.

Pseudocode example:

~~~text
handle(event):
    begin transaction

    if processed_event exists for event.eventId:
        return previous_result

    validate business preconditions
    apply business change
    insert processed_event(event.eventId, result)

    commit transaction
    acknowledge message
~~~

The check-and-record step must guard against race conditions. If two invocations receive the same ID nearly simultaneously, an application-level check alone may not suffice; use a unique key, atomic insert, or appropriate locking mechanism. If the side effect calls an external payment API, use the provider's idempotency key or reconciliation, because an internal database transaction cannot roll back an external transaction that already occurred.

### 6.1. Retries and Backoff

Unbounded, immediate retries can trigger a retry storm when a dependency is degraded. You should:

- Retry transient errors such as timeouts, throttling, or service unavailability according to policy.
- Do not retry permanent input errors such as invalid schemas or permission denials without changes.
- Use exponential backoff with jitter and cap total attempts or duration.
- Monitor retry counts, queue age, error rates, and DLQ depth.
- Distinguish transient errors from business errors requiring manual handling.

### 6.2. Dead-Letter Queues

After a configured number of attempts or time limit, a message can be routed to a **Dead-Letter Queue (DLQ)**. A DLQ is a quarantine queue for investigation and controlled replay—not a place to forget messages.

Operational procedures should alert when messages arrive, retain error metadata without exposing secrets/PII, restrict view/replay permissions, verify idempotency and schema compatibility before replay, and assign retention and an owner.

## 7. Ordering, Consistency, and Long-Running Workflows

Not every queue or event bus guarantees global ordering. Ordering may only be guaranteed within a partition, message group, or session; other platforms may deliver messages concurrently.

If business state depends on order—for example, `PaymentAuthorized` before `PaymentCaptured`—choose an appropriate partition key such as `bookingId`, sequence number, or aggregate version. Consumers must also detect late-arriving or out-of-version events.

Producer timestamps can suffer from clock skew. Two events with close timestamps are not guaranteed to reflect the true business order. You may need aggregate versions, sequence numbers, partition ordering, state validation before applying changes, and distinguishing event time from ingestion time.

### 7.1. Workflows / State Machines

A rental booking process may involve reserving inventory, requesting payment, receiving a callback, confirming the order, and sending notifications. When steps can wait for extended periods, a workflow/state machine persists state to track progress, timeouts, per-step retries, and branching.

~~~mermaid
flowchart TD
    A["Receive booking request"] --> B["Reserve inventory"]
    B --> C{"Reservation succeeded?"}
    C -- "No" --> X["Reject request"]
    C -- "Yes" --> D["Request payment"]
    D --> E{"Payment succeeded?"}
    E -- "Yes" --> F["Confirm booking"]
    F --> G["Emit BookingConfirmed"]
    G --> H["Send notification"]
    E -- "No / expired" --> I["Release reservation"]
    I --> J["Order failed or pending review"]
~~~

When a workflow lacks cross-service transactions, you must define **compensation** for completed steps if a subsequent step fails. For example, if payment was authorized but the booking cannot be confirmed, the payment must be voided/refunded or reconciled—not merely marked locally.

## 8. Deployment Units: One Function or Multiple Functions per Artifact?

Function decomposition and deployment boundaries are not the same thing. Making every function its own deployment unit gives teams clearer release independence and fine-grained permissions, but increases the number of artifacts, pipelines, IAM policies, and observability configs to manage. Bundling multiple functions into one unit can simplify releases, though functions may share configuration, runtime, or artifact-level permissions depending on the platform.

| Model | Characteristics | Best when |
| --- | --- | --- |
| **One function / one deployment unit** | Each handler has an independent artifact, version, and config | Permissions, scaling, dependencies, release schedules, or owners differ |
| **Multiple handlers per package** | Multiple entry points in one codebase/artifact | Small capabilities, shared dependencies/runtime, released together |
| **Function + workflow** | Functions execute steps; workflow orchestrates state | Long processes, branching, timeouts, retries, or compensation |
| **Function + shared library** | Multiple functions reuse versioned code | Stable core logic while keeping handlers independent |
| **Function group/module** | IaC manages a group of functions in one stack | Related resources need to be managed as a single unit |

Terminology and packaging capabilities depend on the platform. Some services deploy only one handler per function resource, yet multiple functions can still be defined within the same project or stack. Be precise in distinguishing the artifact, cloud resource, and release unit.

### 8.1. When to Bundle?

Functions can be bundled when they share the same runtime and dependencies, have aligned release cadences, share an owner, can share configuration and permissions without over-privileging, exhibit similar scaling behavior, and changes to one pose low risk to other handlers.

For instance, two internal handlers for reading metadata and formatting responses can share a package if released together. However, `SendNotification` and `ProcessPayment` should likely remain separate because their permissions, data sensitivity, and incident impacts differ drastically.

### 8.2. When to Split?

Consider separate deployment units if function A requires sensitive IAM permissions that function B must not have; scaling profiles differ; runtimes or dependencies conflict; teams, release schedules, or SLOs differ; blast radius must be minimized; or data regulations require infrastructure-level isolation.

Do not split solely because a function has a different name. Each additional unit adds permissions, pipelines, logs, alarms, configurations, versions, retries, and operational overhead to maintain.

## 9. Deployment Pipelines and Version Management

A serverless deployment unit typically comprises source/compiled artifacts, runtime, handler entry point, memory/timeout/concurrency settings, environment configuration, IAM roles, trigger bindings, observability setup, and data source connections.

Capture most reproducible configuration in **Infrastructure as Code (IaC)** for controlled review and release. Do not rely solely on manual console edits.

~~~mermaid
flowchart LR
    C["Commit / Pull Request"] --> T["Unit, contract, and integration tests"]
    T --> S["Build artifact"]
    S --> Q["Scan dependencies and policies"]
    Q --> I["Deploy to staging"]
    I --> V["Trigger, load, and failure tests"]
    V --> P["Approve and promote version"]
    P --> R["Alias / traffic rollout"]
    R --> M["Monitor SLOs and rollback"]
~~~

The pipeline should compile/package and pin dependencies; unit test business logic; contract test event/request schemas; scan dependencies, artifacts, IaC, and secrets; deploy to staging; verify IAM, networking, timeouts, memory, concurrency, and observability; promote tested artifacts/versions; execute canary rollouts; monitor errors, latency, throttles, retries, DLQs, and cost; and roll back if thresholds are breached.

Function versions and event schema versions are two distinct things. Deploying a new function version does not automatically change upstream payloads; schema changes require a compatibility rollout plan between producers and consumers. Prefer adding optional fields first, updating consumers to support both old and new shapes, monitoring adoption, and only then deprecating old fields. For breaking changes, use versioned event types/topics or adapters as supported by the system.

## 10. Security per Function and Deployment Unit

Serverless reduces server administration, but does not eliminate responsibility for code, data, identity, trigger, and configuration security.

### 10.1. Least Privilege

A function handling payment webhooks may need to read a signature verification secret and update the Payment table. A function sending emails only needs to read permitted notification data and call the email provider. If both share an execution role with access to all customer data and refund operations, the blast radius of a credential compromise is unnecessarily large.

Principles:

- Assign a dedicated execution identity per function/deployment unit when the platform supports it and isolation yields meaningful benefit.
- Grant permissions scoped to specific resources and actions; avoid broad wildcards.
- Separate publish/subscribe, database read/write, and secret retrieval permissions.
- Never place credentials in source code, artifacts, event payloads, or logs.
- Authenticate callers on HTTP triggers, and validate JWT/claims, tenant context, and business authorization.
- Verify webhook signatures before trusting external payloads.
- Restrict publish/subscribe permissions on queues and event sources to necessary principals only.
- Audit changes to IAM policies, triggers, secrets, and network configurations.

### 10.2. Event Payloads Are Not a Trust Boundary

Even internal events can be mis-emitted, duplicated, malformed, or influenced by a compromised producer. Consumers must validate schemas, enforce payload limits, verify the source, and check authorization for the action. A `customerId` field in a message is not proof that the producer is authorized to act on that customer's data.

### 10.3. Networking and Data

Functions accessing private databases may need VPC/VNet attachment or platform private endpoints. In such cases, evaluate IP addressing, DNS, security groups, connection pooling, egress rules, subnet IP exhaustion, and cold starts caused by network setup. Attaching a VPC does not automatically make a function secure; routes and network permissions must still be enforced.

If events or logs contain PII, minimize included fields, enforce encryption, set retention policies, and restrict access. Avoid forwarding raw payloads across multiple queues or log sinks when consumers only need an identifier and a few business attributes.

## 11. Performance: Cold Starts, Timeouts, and Concurrency

### 11.1. Cold Starts

A **cold start** is the initialization time incurred when the platform must prepare a new execution environment. It can include provisioning the runtime, downloading code/dependencies, initializing frameworks, opening connections, or loading configuration.

Cold start duration depends on runtime, package size, framework, network attachment, initialization logic, usage patterns, and provider features. There is no universal number across all functions.

To keep cold starts under control, trim unnecessary dependencies and initialization work; initialize clients intentionally; reuse connections within the same execution environment when safe without assuming the environment lives forever; measure p95/p99 instead of benchmarking only warm calls; consider provisioned/warm capacity when justified by SLOs and cost; and assess the impact of VPC/network integration.

### 11.2. Timeouts and Memory

Each function requires a timeout longer than expected execution duration yet bounded to avoid tying up resources indefinitely. Timeouts do not replace cancellation or idempotency. If the platform times out after a side effect has already occurred, callers may retry and duplicate the operation.

Memory limits may scale CPU and network allocation depending on the platform. Increasing memory can sometimes increase throughput and cut execution time enough to lower total cost; benchmark against real workloads rather than always picking the smallest tier.

### 11.3. Concurrency and Downstream Capacity

If a queue releases 1,000 messages simultaneously and a function scales to high concurrency, the database can be overwhelmed with connections. A function scaling faster than its database does not mean the overall system is scalable.

Coordinate function concurrency limits, in-flight message/batch sizes, connection pools/DB proxies, third-party rate limits, retries/backoff, backpressure, and circuit breakers at appropriate dependencies. The goal is to **keep the entire chain within safe load limits**, not just the function itself.

## 12. Serverless Cost

Serverless pricing typically depends on one or more factors such as invocations, execution duration, memory/CPU, data transfer, queues/events, API gateways, workflows, and storage. Pricing formulas, free tiers, quotas, and rates vary by provider, region, and time.

**Total use-case cost = invocations/compute + triggers/orchestration + storage/data transfer + observability + downstream services.**

A short function invoked billions of times may not be cheap. A function with heavy dependencies and slow cold starts can cost more than anticipated. Conversely, bursty or intermittent workloads often save money by avoiding continuously running VMs.

Splitting a single use case into 8 functions communicating via events/APIs can introduce extra invocations, queue/event requests, workflow state transitions, network/data transfers, logs/traces, and operational effort. Splitting can still be the right choice when it provides isolation, independent scaling, and smaller blast radius. Always compare **end-to-end TCO**, not just per-invocation price.

## 13. Observability from Trigger to Outcome

A serverless system with multiple functions can span dozens of steps for a single transaction. Without propagating correlation IDs and trace context, operators struggle to see which request produced which message, which consumer processed it, which retry failed, and what final business state was reached.

| Layer | Metrics/signals |
| --- | --- |
| API trigger | Request count, 4xx/5xx, latency p95/p99, throttling |
| Function | Invocations, duration, errors, timeouts, cold starts (if observable), concurrency |
| Queue/stream | Age of oldest message, backlog, retries, DLQ depth, consumer lag |
| Event bus | Delivery failures, matched/unmatched rules, target latency |
| Workflow | Failed states, retry counts, elapsed time, stuck executions |
| Downstream | DB connections, query latency, provider errors/rate limits |
| Cost | Invocations, compute duration, workflow transitions, and log volume |

Logs should be structured and avoid recording tokens, secrets, or full payloads containing personal data. Every invocation should log a correlation ID, function name/version, event ID, outcome, and duration. For long workflows, record per-step states and terminal errors in a consistent format.

Define outcome-based SLOs—such as the percentage of booking requests accepted within target latency and notifications delivered within a threshold after confirmation—rather than only tracking zero function error rates.

## 14. Implementation Example: Serverless Rental Booking Flow

Suppose an application needs to accept booking requests, reserve assets, process payments, send notifications, and update reports.

~~~mermaid
flowchart TB
    U["Web / Mobile"] --> API["API Gateway"]
    API --> CREATE["CreateBooking"]
    CREATE --> DB[("Booking DB")]
    CREATE --> Q["Booking workflow / queue"]
    Q --> RESERVE["ReserveInventory"]
    RESERVE --> PAY["RequestPayment"]
    PAY --> PSP["Payment provider"]
    PSP --> WEBHOOK["PaymentCallback"]
    WEBHOOK --> EVT["Event bus: BookingConfirmed"]
    EVT --> N["SendNotification"]
    EVT --> R["UpdateReport"]
    TIMER["Scheduler: reservation expiry"] --> EXPIRE["ExpireReservation"]
~~~

| Function | Trigger | Response | Primary permissions | Suggested deployment unit |
| --- | --- | --- | --- | --- |
| CreateBooking | HTTP/API | Synchronous | Create booking, read required customer info | booking-api |
| ReserveInventory | Workflow/queue | Asynchronous or workflow step | Read/write inventory reservation | inventory-reservation |
| RequestPayment | Workflow/queue | Asynchronous | Call payment provider, access related credentials | payment-request |
| PaymentCallback | HTTP/webhook | Acknowledge receipt | Verify webhook, update payment state | payment-callback |
| SendNotification | Event bus/queue | Asynchronous | Send email/SMS | notification-worker |
| UpdateReport | Event/stream/schedule | Asynchronous | Write read model/reporting store | reporting-worker |
| ExpireReservation | Scheduler/queue | Asynchronous | Check and release reservations | reservation-expiry |

Deployment unit names are illustrative. `PaymentRequest` and `PaymentCallback` may be deployed separately due to different triggers and attack surfaces, even with the same owner. If a function holds sensitive payment permissions, avoid bundling it with notifications merely to share an IAM role.

### 14.1. Error Handling at Each Step

| Step | Failure | Recommended behavior |
| --- | --- | --- |
| CreateBooking | Duplicate client request due to timeout | Idempotency key to return the same result |
| ReserveInventory | No inventory available | Business rejection, do not retry indefinitely |
| RequestPayment | Provider timeout, transaction outcome unclear | Query/reconcile by provider reference before retrying |
| PaymentCallback | Duplicate webhook | Verify signature, deduplicate event/reference |
| SendNotification | Temporary provider outage | Bounded retries, DLQ; do not alter payment state |
| UpdateReport | Consumer lag or duplicate message | Idempotent update, monitor lag and replay |
| ExpireReservation | Scheduler fires twice | Check booking status and expiry before releasing |

Splitting functions does not automatically handle these failures. They must be modeled explicitly in contracts, persisted state, and retry policies.

## 15. When to Use a Workflow?

Orchestration can be written in code inside a function, but long-running processes are hard to track if state only lives in memory or control flow. A workflow/state machine is suitable when you need long callback waits, step-specific retry policies, timeouts and conditional branching, parallel fan-out/join, compensation, state auditing, and controlled flow updates.

Workflows also introduce their own costs, state/payload size limits, and retry semantics. Do not store large payloads in state history when they can be saved in object storage and passed by reference. Choose a workflow based on orchestration needs—not just to make an architecture diagram look more serverless.

## 16. Testing and Protecting Boundaries

Serverless testing must cover handler logic, trigger contracts, and platform semantics.

- **Unit tests:** business rules, validation, state transitions, and idempotency logic.
- **Contract tests:** HTTP schemas, event schemas, version compatibility, and invalid input handling.
- **Integration tests:** queues, databases, secret managers, event buses, webhooks, and IAM permissions.
- **Trigger tests:** batch sizes, duplicates, retries, timeouts, ordering, and scheduler overlaps.
- **Failure tests:** unavailable dependencies, throttling, DLQ routing, malformed events, and timeouts after side effects.
- **Load tests:** concurrency bursts, cold starts, downstream saturation, and queue lag.
- **Security tests:** overly broad IAM, webhook spoofing, tenant boundaries, secret leakage, and unauthorized access.

Local emulators are helpful for business logic but do not replace testing on the real platform for retries, timeouts, concurrency, visibility timeouts, and IAM enforcement. Platform-specific behaviors must be verified in a staging environment that mirrors production.

Functions can reuse libraries for schema validation, domain logic, or tracing, but large shared libraries can force mass redeployments for minor changes. Share stable, semantically versioned logic with clear contracts; never share execution roles just to reduce configuration.

## 17. Design Process from Requirements to Release

1. **Decompose use cases:** identify actions, events, invariants, data, and expected outputs.
2. **Determine triggers:** must the client wait, or can it accept a job ID? Does a queue, event, timer, or workflow fit?
3. **Split functions:** select logical units with clear purpose, contracts, and failure behavior.
4. **Choose deployment units:** evaluate runtime, IAM, scaling, owner, release cadence, blast radius, and dependencies.
5. **Design event semantics:** schema, event ID, ordering, retries, deduplication, retention, and DLQ.
6. **Define business states:** distinguish accepted, processing, succeeded, failed, expired, and manual-review states.
7. **Design security:** execution roles, trigger permissions, secrets, networking, data access, and auditing.
8. **Size for operations:** timeouts, memory, concurrency, batch sizes, queues, quotas, and downstream capacity.
9. **Build IaC/CI/CD:** build, scan, test, publish versions, roll out, and roll back.
10. **Measure outcomes:** end-to-end traces, error budgets, latency, backlog, cost, and completion rates.
11. **Review and adjust:** merge or split deployment units when operational data justifies the change.

## 18. Common Design Pitfalls

| Pitfall | Consequence | Prevention |
| --- | --- | --- |
| One function handles an entire large workflow | Broad permissions, timeouts, retries repeat multiple side effects | Split by business operations and workflows |
| One function per helper method | Excessive hops, invocations, IAM, and pipelines | Split only at genuine business/operational boundaries |
| Making every step synchronous | Callers wait too long, cascading timeouts | Use queues/events for deferred processing |
| Returning 202 before the message is durable | Client assumes job is accepted, but job is lost | Confirm durability semantics before acknowledging |
| Assuming exactly-once delivery | Duplicates cause double charges or duplicate notifications | Implement idempotency and reconciliation |
| Retrying all errors | Retry storms and inflated costs | Classify errors, use backoff, max attempts, and DLQs |
| Missing event schema versions | Producer payload changes break consumers | Contract versioning and backward-compatible rollouts |
| Sharing overly broad IAM roles | Compromised function inherits another function's privileges | Enforce least privilege per function/unit |
| Bundling functions with mismatched SLOs/permissions | Unacceptable blast radius and risky rollouts | Deliberately separate deployment boundaries |
| Putting every function in its own pipeline | Release and operational overhead | Group units by owner, runtime, and lifecycle |
| Not monitoring queue age/DLQs | Messages pile up while API looks healthy | Outcome-driven metrics and alerts |
| Unbounded concurrency | Downstream services get overwhelmed | Tune function concurrency, queue batching, and DB capacity |
| Logging raw payloads/secrets | Data leakage | Data minimization, masking, and retention |
| Ignoring duplicate/late callbacks | Inconsistent business state | Deduplication, versioning, transitions, and reconciliation |

## 19. Well-Architected Evaluation

| Perspective | Questions to answer |
| --- | --- |
| **Reliability** | Are retries and timeouts safe? Can events be lost or duplicated? Are DLQ and replay procedures in place? Does the workflow handle recovery/compensation? |
| **Security** | Does each function follow least privilege? Are triggers authenticated? Do events/secrets/logs leak sensitive data? Do deployment units have clear blast radii? |
| **Performance Efficiency** | Do cold starts, p95/p99 latency, concurrency, batching, and downstream capacity meet SLOs? |
| **Cost Optimization** | Are invocations, compute, queues, workflows, APIs, logs, and data transfer accounted for? Does fine-grained splitting inflate total cost? |
| **Operational Excellence** | Is tracing available from request to consumer? Are versions, owners, alerts, rollout/rollback, and DLQ runbooks defined? |

### Acceptance Checklist

- [ ] Each function has a clear purpose, contract, owner, and failure behavior.
- [ ] Triggers match synchronous/asynchronous requirements and delivery semantics are verified.
- [ ] Events include an ID, schema version, timestamp/correlation, and minimal payload.
- [ ] Consumers are idempotent; rules exist for duplicates, retries, timeouts, and ordering.
- [ ] DLQs have retention, alerts, an owner, and a replay procedure.
- [ ] Deployment units are chosen based on permissions, scaling, release cadence, and blast radius.
- [ ] Execution identities follow least privilege; secrets are absent from artifacts, payloads, and logs.
- [ ] Timeouts, memory, concurrency, and downstream quotas are load tested.
- [ ] Workflows define states, retries, timeouts, and appropriate compensation.
- [ ] IaC/CI/CD manages versions, trigger bindings, rollouts, and rollbacks.
- [ ] Tracing/correlation enables tracking across the entire business flow.
- [ ] SLOs and TCO are measured at the use-case level, not just per individual function.

## 20. Applied Exercise

A ticketing application has the following business flow: receive a booking request, hold seats for 5 minutes, process payment via a third-party provider, send a confirmation email, and update revenue reports. Payment webhooks occasionally arrive in duplicate; the email provider can experience outages lasting a few minutes; reports can lag by up to 15 minutes.

Design:

1. The required functions and each function's responsibility.
2. The trigger for each function: HTTP, queue, event bus, or scheduler.
3. Which steps must be synchronous for user feedback and which can run asynchronously.
4. The event contract upon payment completion; which idempotency key handles duplicate webhooks?
5. Which deployment units and IAM roles should be separated to reduce privileges and blast radius?
6. Retry, DLQ, and replay policies for email, reporting, and payment callbacks.
7. Metrics proving the booking flow completes accurately and within SLO.

A sound approach might immediately return a booking ID in `PENDING_PAYMENT` state, use a workflow to manage seat-hold expiration, process webhooks idempotently, emit events after commit, and run email and reporting asynchronously. What matters most is clearly distinguishing between **request accepted**, **seats reserved**, **payment completed**, and **ticket confirmed**.

**Key takeaway:** function decomposition defines which work owns distinct logic and responsibility; triggers define when work starts and under which delivery semantics; deployment units govern how code is released, authorized, scaled, and fault-isolated. All three decisions must be designed together from business contracts, data boundaries, and state models so that serverless systems achieve high development velocity while maintaining verifiable reliability, security, performance, cost efficiency, and operability.
