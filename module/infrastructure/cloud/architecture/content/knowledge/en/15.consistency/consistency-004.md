# Saga with Centralized Orchestration and Event-Driven Choreography

A single business transaction often spans multiple services. When a customer books an appointment, the system may need to hold a time slot, create a booking, record payment, emit events, and send notifications. Each service owns its own data and commits transactions inside its own database. There is no single ACID transaction spanning every database and external API. If the payment step succeeds but the booking confirmation step fails, what should the system do?

**Saga** is a design pattern for executing a long-lived business transaction across multiple services as a sequence of **local transactions**. Each step commits within the data boundary of its owning service. If a step cannot proceed, the workflow executes defined **compensation** actions to bring the business to an acceptable state. Sagas are typically organized in two ways: **orchestration** (centralized coordination) and **choreography** (services coordinating via events).

Both approaches handle distributed workflows without holding database transactions open across multiple services. They carry different trade-offs regarding logic centralization, coupling, observability, operations, event complexity, and recovery. A Saga does not turn a system into a global ACID transaction, and compensation does not guarantee completely undoing an action that already occurred externally.

This lesson belongs to the **Consistency** section of the cloud architecture module. The focus is on choosing service boundaries and implementation patterns to balance business correctness, reliability, security, scalability, cost, and operability using a Well-Architected mindset.

After this lesson, you will be able to:

- Explain Sagas and why local transactions and compensation are needed in multi-service workflows.
- Distinguish centralized orchestration from event-driven choreography.
- Design states, transitions, timeouts, retries, and error handling for a Saga.
- Apply transactional outbox/inbox, idempotency, and handling for duplicate or out-of-order events.
- Identify irreversible points, compensating actions, and reconciliation processes.
- Choose orchestration, choreography, or a hybrid approach based on complexity and service ownership boundaries.
- Test and observe distributed workflows while evaluating Well-Architected trade-offs.

## 1. Why are Sagas needed?

Consider a booking workflow consisting of these steps:

1. Booking Service confirms the time slot is available and holds it.
2. Payment Service executes payment or holds funds.
3. Booking Service confirms the booking.
4. Notification Service sends email/SMS.

Each service has its own database and transactions. If an application holds a database transaction open while making network calls to three other services, it may hold locks too long, increase connection usage, time out easily, and still cannot automatically roll back a transaction committed in another database or funds charged at a payment provider.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant B as Booking Service
    participant P as Payment Service
    participant N as Notification Service
    C->>B: Create booking
    B->>B: Local transaction: hold slot
    B->>P: Request payment
    P->>P: Local transaction/provider call
    P-->>B: Payment succeeded
    B->>B: Local transaction: confirm booking
    B->>N: Send notification request
    N-->>B: Request received
    B-->>C: Return result
~~~

The happy path looks simple. Yet if a service crashes after payment succeeds, a response is lost, an event is emitted twice, or the notification provider is temporarily down, the system must know which step the business process is in and how to proceed.

A Saga divides the workflow into **local steps with durable outcomes**. Each step executes idempotently; a coordinator or event handler tracks progress. On failure, the Saga triggers compensation for completed steps that can be compensated.

### A Saga is not a distributed transaction

| Approach | Mechanism | Main trade-offs |
| --- | --- | --- |
| Single database transaction | ACID within one database boundary | Simple atomicity, but cannot span multiple services/databases |
| Distributed transaction / 2PC | Coordinator asks participants to prepare, then commit/abort | Participants must support it; can hold resources and increase coupling |
| Saga | Multiple local transactions and compensations | Consistency is achieved gradually; requires state, retries, compensation, and operations |

Sagas fit when workflows are long-lived, multiple services own separate data, or external system calls are involved. If the entire business operation lives in one database and can be solved with a short transaction, adding a Saga introduces unnecessary complexity.

## 2. Local transactions, compensation, and business states

A Saga consists of business steps. Each step:

- Applies changes within the service's data ownership scope.
- Commits its local transaction before reporting the outcome.
- Has an operation ID or Saga ID for traceability.
- Can be retried safely using idempotency/deduplication.
- On failure, emits an outcome so the workflow decides whether to continue, retry, or compensate.

**Compensation** is a new business action designed to offset the effect of an earlier step. It does not necessarily erase old traces or restore the exact physical state as though the step never happened.

| Completed step | Possible compensation | Limits |
| --- | --- | --- |
| Hold time slot | Release hold | If the hold expired or the slot was reallocated, check owner/version |
| Create order | Mark cancelled | Keep history for audit; do not erase records |
| Hold funds (authorization) | Void/release authorization | Depends on provider state and expiration |
| Charge funds | Refund | A refund is a new transaction; it can be slow, incur fees, or require manual handling |
| Send email | Send correction/amendment notice | Cannot recall an email already read by the recipient |
| Grant permission | Revoke permission | Issued tokens may remain valid until expiration or revocation |

Do not describe compensation as a system-wide `ROLLBACK` statement. For example, once a "Booking successful" email is sent, you cannot delete that email from the customer's inbox. The system can send an amendment or cancellation notice, but that is a new event.

### Forward recovery and backward recovery

When an error occurs, there are two directions:

- **Forward recovery:** continue completing the workflow after resolving the cause, such as retrying a temporarily unavailable service.
- **Backward recovery / compensation:** compensate previously executed steps to terminate the Saga in a failed or cancelled state.

Not every error warrants immediate compensation. If Payment Service times out and you do not know whether the charge succeeded, blindly refunding or charging again can create discrepancies. First query the transaction status using the operation ID / provider reference.

### Designing clear states

~~~text
PENDING
  -> SLOT_HELD
  -> PAYMENT_PENDING
  -> PAYMENT_AUTHORIZED
  -> CONFIRMED
  -> COMPLETED

Failure branches:
  PAYMENT_FAILED
  PAYMENT_UNKNOWN
  CANCEL_PENDING
  COMPENSATING
  CANCELLED
  MANUAL_REVIEW
~~~

State names are illustrative. They should reflect what is known rather than concluding prematurely. `PAYMENT_UNKNOWN` is more useful than `PAYMENT_FAILED` when a provider request times out and the outcome is uncertain.

## 3. Two ways to organize a Saga

### 3.1. Orchestration — centralized coordination

In orchestration, a **Saga orchestrator/coordinator** owns the workflow definition and decides the next step based on state and received outcomes. It sends commands to participating services, receives responses/events, persists progress, and drives retries or compensation.

~~~mermaid
flowchart TD
    CLIENT["Client"] --> ORCH["Booking Saga Orchestrator<br/>State + transition"]
    ORCH -->|"ReserveSlot command"| BOOK["Booking Service"]
    BOOK -->|"SlotHeld / SlotRejected"| ORCH
    ORCH -->|"AuthorizePayment command"| PAY["Payment Service"]
    PAY -->|"PaymentAuthorized / PaymentDeclined"| ORCH
    ORCH -->|"ConfirmBooking command"| BOOK
    BOOK -->|"BookingConfirmed"| ORCH
    ORCH -->|"SendNotification command"| NOTIFY["Notification Service"]
    NOTIFY -->|"Accepted / Failed"| ORCH
    ORCH --> RESULT["Saga result / status"]
~~~

The orchestrator may be a managed state machine, workflow engine, dedicated service, or in-application library. It must persist state durably rather than relying solely on a single process's RAM.

**Advantages:**

- Workflow and step ordering are visible in one place.
- Timeouts, retries, deadlines, compensation, and manual review can be declared explicitly.
- Easy to inspect overall Saga state and see which step is waiting.
- Can manage long-running workflows with timers, human approvals, and conditional branches.

**Trade-offs:**

- The orchestrator is a critical component needing HA, backup/restore, access control, and monitoring.
- Participants depend on command contracts and semantics defined by the coordinator.
- The central workflow can bloat and absorb business logic belonging to other services.
- If the coordinator dispatches a command without persisting a checkpoint properly, duplicates or state divergence can occur.

The orchestrator should coordinate **progress**, not usurp ownership of participant data. Booking Service still decides whether a slot can be held; Payment Service still decides payment status based on its own data.

### 3.2. Choreography — event-driven coordination

In choreography, no single coordinator dictates every step. Each service receives relevant events, executes a local transaction, and emits outcome events. The workflow emerges from the chain of events and the reaction rules of participating services.

~~~mermaid
flowchart LR
    B["Booking Service"] -->|"BookingRequested"| E1[("Event Bus")]
    E1 --> P["Payment Service"]
    P -->|"PaymentAuthorized"| E2[("Event Bus")]
    E2 --> B
    B -->|"BookingConfirmed"| E3[("Event Bus")]
    E3 --> N["Notification Service"]
    P -->|"PaymentDeclined"| E4[("Event Bus")]
    E4 --> B
    B -->|"BookingCancelled"| E5[("Event Bus")]
    E5 --> N
~~~

Booking Service emits `BookingRequested`; Payment Service reacts and emits `PaymentAuthorized` or `PaymentDeclined`; Booking Service updates its state and emits the next event.

**Advantages:**

- Services can react independently and scale with event volume.
- Producers do not necessarily need to know every consumer.
- Suitable for simple workflows where events are natural integration boundaries.
- Reduces synchronous dependency on a central coordinator.

**Trade-offs:**

- The overall business sequence is harder to see when logic is scattered across event handlers.
- Implicit dependencies can grow when one event has many consumers.
- Debugging, replay, and identifying where a Saga is stuck become more complex.
- Harder to manage overall timeouts, multi-step compensation, and human intervention without tracking mechanisms.

Choreography does not mean workflow management is unnecessary. You still need Saga IDs, correlation, event schemas, durable state, timeouts, dead-letter handling, and progress observability tools.

### 3.3. Direct comparison

| Criterion | Orchestration | Choreography |
| --- | --- | --- |
| Where flow is defined | Centralized in the coordinator | Distributed across event handlers and contracts |
| Controlling the next step | Coordinator issues commands | Services react to events |
| End-to-end observability | Usually easier when the state machine stores full state | Requires correlation and aggregation tooling |
| Coupling | Participants depend on commands/contracts | Producers/consumers depend on event schemas and semantics |
| Timeouts / compensation | Explicitly declarable in the workflow | Must be distributed or use auxiliary tooling |
| Multi-branch workflows | Easier to express explicitly | Hard to follow when many services participate |
| Service autonomy | Coordinator directs flow; domains still own local data | Services decide reactions within their domain |
| Operations | Focus on operating coordinator and participants | Operate many consumers, event flows, and correlation |
| Best fit | Critical processes, many steps/branches, audit needs | Simple event flows, independent consumers |

Neither option is universally better. A system can combine them: an orchestrator manages the **core business transaction**, while notifications, analytics, or audits are emitted via events and run independently.

## 4. Designing Saga orchestration

An orchestrated Saga typically includes:

- **Saga ID:** unique identifier for a workflow execution.
- **State store:** current state, required data, and checkpoints.
- **Command dispatcher:** sends commands to participants.
- **Result/event handler:** receives outcomes, validates correlation, and updates state.
- **Timers/deadlines:** enforce overall or per-step timeouts.
- **Retry policy:** which errors are retryable, attempt limits, and intervals.
- **Compensation handler:** executes compensating actions in the appropriate order.
- **Operational controls:** cancellation, pause, resume, manual review, and auditing.

### Booking state machine example

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> SLOT_HELD: ReserveSlotSucceeded
    PENDING --> FAILED: ReserveSlotRejected
    SLOT_HELD --> PAYMENT_PENDING: AuthorizePayment
    PAYMENT_PENDING --> PAYMENT_AUTHORIZED: PaymentAuthorized
    PAYMENT_PENDING --> PAYMENT_UNKNOWN: ProviderTimeout
    PAYMENT_PENDING --> COMPENSATING: PaymentDeclined
    PAYMENT_UNKNOWN --> PAYMENT_AUTHORIZED: ReconcileAuthorized
    PAYMENT_UNKNOWN --> COMPENSATING: ReconcileNotAuthorized
    PAYMENT_AUTHORIZED --> CONFIRMING: ConfirmBooking
    CONFIRMING --> CONFIRMED: BookingConfirmed
    CONFIRMING --> COMPENSATING: ConfirmFailed
    COMPENSATING --> CANCELLED: CompensationCompleted
    COMPENSATING --> MANUAL_REVIEW: CompensationFailed
    CONFIRMED --> [*]
    CANCELLED --> [*]
    FAILED --> [*]
~~~

The state machine includes `PAYMENT_UNKNOWN` because a timeout lacks sufficient information to conclude payment failed. The orchestrator must query or receive a confirmation event before choosing compensation.

### Commands and events are two distinct message types

- **Command:** requests a service to perform an action, e.g., `AuthorizePayment` or `ReserveSlot`.
- **Event:** records a fact that has already happened, e.g., `PaymentAuthorized` or `SlotHeld`.

A command can be rejected or time out; an event describes an occurrence that already took place. Do not name events like unexecuted imperatives.

### State persistence and checkpoints

Each time an outcome arrives, the orchestrator should consistently update state and plan the next step. If using its own database:

1. Read the Saga's current version.
2. Verify the message belongs to the Saga and matches the expected step/version.
3. Update state using optimistic concurrency or a transaction.
4. Save the next command in the outbox.
5. Commit, and then have the dispatcher send the command.

If the dispatcher sends a command before committing the checkpoint, the orchestrator could crash and replay commands without a trace. If it commits the checkpoint first and crashes before sending the command, the workflow stalls. The outbox bridges the gap between state updates and message emission.

## 5. Designing Saga choreography

Each consumer in choreography must:

- Validate the event schema and emitter source.
- Check Saga ID, event ID, and event type.
- Execute its local transaction.
- Record the processed event / inbox entry to prevent duplicates.
- Write the next event to the outbox in the same local transaction.
- ACK the message only after durable processing according to broker semantics.
- Have retries, a DLQ, and a replay procedure.

### Event flow example

~~~text
BookingRequested (sagaId, bookingId)
    -> Payment Service:
         authorize payment
         emit PaymentAuthorized or PaymentDeclined

PaymentAuthorized
    -> Booking Service:
         confirm booking
         emit BookingConfirmed

PaymentDeclined
    -> Booking Service:
         release slot
         emit BookingCancelled

BookingConfirmed
    -> Notification Service:
         send confirmation notification
~~~

This is a flow summary, not a replacement for real schemas and transitions. You must define clearly what happens if `PaymentAuthorized` arrives twice, `BookingRequested` is emitted late, or an event arrives after the booking was already cancelled.

### When one event has multiple consumers

For example, `BookingConfirmed` is emitted by Booking Service; Notification Service sends email, Analytics updates reports, and Audit Service writes logs. The producer does not need to know every consumer, yet each consumer maintains its own processing state. A notification failure should not force a booking back to `PENDING` if the business has already confirmed it and notification is merely an auxiliary task.

Distinguish the **core transaction** from **auxiliary side effects**. Do not let a secondary consumer failure reverse the core transaction unless the business contract requires it.

## 6. Transactional outbox and inbox

A common bug in event-driven Sagas:

1. Service commits database changes.
2. Service sends a message to the broker.
3. Process crashes between the two steps.

If the message is sent before commit, consumers may receive events for uncommitted data. If committed first and then crashed, the event is never sent. The **transactional outbox** solves this by writing business data and the event record in the same local transaction.

~~~mermaid
flowchart TD
    S["Service command/event handler"] --> TX["Local database transaction"]
    TX --> DATA["Business data update"]
    TX --> OUT["Outbox event record"]
    OUT --> RELAY["Outbox relay / CDC"]
    RELAY --> BROKER["Message broker"]
    BROKER --> CONSUMER["Consumer"]
    CONSUMER --> ITX["Consumer local transaction"]
    ITX --> INBOX["Inbox / processed message"]
    ITX --> NEXT["Business update + next outbox event"]
~~~

The outbox relay may publish the same event more than once if it published before recording the sent status. Therefore, consumers need **inbox/deduplication** by event ID or an equivalent idempotent mechanism.

### Minimal event structure

~~~json
{
  "eventId": "evt-01J9X...",
  "eventType": "PaymentAuthorized",
  "eventVersion": 1,
  "occurredAt": "2026-11-18T04:30:00Z",
  "sagaId": "saga-8a31",
  "correlationId": "req-71f2",
  "causationId": "cmd-229a",
  "aggregateId": "booking-9281",
  "producer": "payment-service",
  "data": {
    "paymentReference": "pay-5512",
    "amountMinor": 250000,
    "currency": "VND"
  }
}
~~~

This schema is illustrative. Events should include references and only enough data for consumers, avoiding card details, secrets, or unnecessary personal payloads. Versioning, backward compatibility, validation, and domain-scoped publish/subscribe permissions are required.

### Inbox duplicate handling

A consumer can insert `eventId` into an inbox table with a unique constraint. If the event ID already exists and the prior transaction committed, the consumer skips the business side effect and ACKs. If the same message is processed concurrently, the unique claim ensures only one consumer proceeds.

The inbox record and business update should commit in the same transaction when they live in one database. If the side effect calls an external provider, you need a provider idempotency key or reconciliation.

## 7. Retries, timeouts, and backoff

Not every error requires immediate compensation. Classifying errors helps choose the right response:

| Error type | Examples | Appropriate behavior |
| --- | --- | --- |
| Transient | 503, network reset, temporary rate limit | Bounded retries with backoff and jitter |
| Permanent / business | No slots left, card explicitly declined, insufficient permissions | Mark business failure and compensate prior committed steps |
| Ambiguous | Timeout after sending payment command; unknown if provider processed it | Query/reconcile using operation reference |
| Poison message / schema | Malformed payload, unsupported version | DLQ, alert, fix data/consumer, then replay |
| Resource exhaustion | DB connection pool exhausted, quota depleted | Backpressure, reduce concurrency, fix capacity/quota |

### Exponential backoff with jitter

An illustrative policy:

~~~text
delay(n) = random(0, min(maxDelay, baseDelay * 2^n))
~~~

Jitter prevents many Sagas from retrying simultaneously after an outage. Cap both attempt count and total deadline; never retry a broken service infinitely.

### Per-step and whole-workflow timeouts

A Saga should define:

- **Step timeout:** maximum time one step waits for a response.
- **Retry deadline:** maximum duration for retrying transient errors.
- **Saga deadline:** business completion deadline, such as holding a slot for at most 10 minutes.
- **Compensation deadline:** window to finish compensating actions.
- **Manual review SLA:** time limit for humans to handle cases that cannot be resolved automatically.

Numbers must come from business requirements. Timeouts that are too short cause false workflow failures; timeouts that are too long tie up reserved resources and degrade customer experience.

## 8. Compensation and irreversible actions

Design compensation before going to production. For every step, know:

1. Where did side effects occur?
2. Which action can compensate for them?
3. Is the compensating action idempotent?
4. Can it fail or time out?
5. If the outcome is unclear, how is it queried?
6. If compensation fails persistently, who handles it?

| Local action | Compensation | How to verify |
| --- | --- | --- |
| Hold slot | Release hold by booking/Saga ID | Who owns the slot and whether the hold is still active |
| Authorize payment | Void authorization | Provider status and reference |
| Capture payment | Refund by payment operation ID | Reconcile refund state, amount, and currency |
| Confirm booking | Cancel booking if policy allows | Check status, notifications, and cancellation policy |
| Send email | Send correction/cancellation notice | Delivery status; sent email cannot be recalled |
| Send partner webhook | Send adjustment or cancellation event | Event reference and acknowledgment |

### Compensation may run in reverse order

If a workflow is A → B → C, compensation usually executes as C → B → A because later steps may depend on earlier resources. However, this is not an absolute rule. Business needs may call for parallel compensation or prioritizing one compensating action to limit losses.

For example, a refund may need to start immediately, while slot release runs only after the provider confirms funds are no longer held. Document ordering according to actual dependencies.

### Compensation failures

Never mark a Saga `CANCELLED` if a critical compensation has not completed. Transition to `COMPENSATION_PENDING`, `RECONCILIATION_REQUIRED`, or `MANUAL_REVIEW`. Record the attempted compensation step, attempt count, error, timestamp, provider reference, still-held resources, assigned owner, and deadline.

A workflow marked complete while funds remain unrefunded or slots remain unreleased creates hard-to-diagnose discrepancies.

## 9. Event ordering, concurrency, and stale messages

A Saga can receive duplicate, delayed, or out-of-order events. Broker ordering usually holds only within a scope (partition, key, session, or group) and does not automatically synchronize across all services.

Cases to handle:

- `PaymentAuthorized` arrives after the Saga already transitioned to `CANCELLED`.
- `BookingRequested` is redelivered after the booking was already confirmed.
- `PaymentDeclined` and `PaymentAuthorized` appear nearly simultaneously due to provider retries/timeouts.
- A consumer processes an older-version event after the aggregate moved to a newer version.
- Two commands operate concurrently on the same booking or payment reference.

Protection mechanisms:

- Use **Saga ID**, **event ID**, **correlation ID**, and **causation ID** for traceability.
- Use **aggregate version/sequence** or optimistic concurrency to detect stale events.
- Validate allowed state transitions before updating state.
- Use inbox / unique constraints to prevent duplicates.
- Use locks/leases with fencing tokens if operations on the same aggregate must be serialized.
- Design idempotent handlers and safe event replay.
- Provide dead-lettering and quarantine for events that cannot be processed automatically.

Do not silently drop an event just because it arrived out of order without leaving a trace. You may need to wait, re-read source state, or route to reconciliation.

## 10. Long-running workflows, user interaction, and cancellation

A Saga may take seconds, minutes, or days—for example, a booking waiting for user payment confirmation, staff approval, or a third-party response. Do not keep an HTTP request open for the entire duration of the workflow.

The API typically returns an operation resource:

~~~http
HTTP/1.1 202 Accepted
Location: /v1/operations/saga-8a31
Retry-After: 2
Content-Type: application/json

{
  "sagaId": "saga-8a31",
  "status": "PAYMENT_PENDING"
}
~~~

Clients can poll the status endpoint, receive a webhook/callback, or use an appropriate notification channel. The status endpoint must enforce authentication and tenant authorization.

Cancelling a workflow is also a conditional command:

- If no side effects have occurred, it can transition to `CANCELLED`.
- If a slot is held, release it by booking ID/version.
- If payment is in flight, query and decide void/refund once an outcome exists.
- If the booking is already confirmed, apply cancellation policy, fees, and notifications.
- If the service was already fulfilled, a separate refund/dispute workflow may be needed.

Never let cancellation overwrite state unconditionally. Use version/transition rules to prevent cancellation racing with confirmation.

## 11. When to choose orchestration vs. choreography?

### Choose orchestration when:

- The workflow has many sequential steps, conditions, branches, and compensations.
- There are overall timeouts, waiting schedules, approvals, or human intervention.
- You need an easily auditable view of a transaction's state.
- The business wants one place clearly expressing the end-to-end flow.
- You can operate the coordinator/state machine as a reliable platform capability.

### Choose choreography when:

- The event flow is relatively simple and services hold domain autonomy.
- One event has multiple independent consumers such as analytics, notifications, and auditing.
- You want to reduce reliance on a central coordinator.
- Teams can manage schemas, consumers, replay, and observability.
- Complex multi-branch coordination and compensations are unnecessary.

### Combining both patterns

A common pattern uses an orchestrator to manage the **core business transaction**, while post-processing tasks emit events. For example, the orchestrator coordinates slot hold, payment authorization, and booking confirmation; after `BookingConfirmed`, independent consumers update search indexes, run analytics, send emails, and notify partners.

This hybrid avoids letting notification failures roll back bookings while keeping core workflow state clear.

## 12. Sagas and eventual consistency

Because local transactions commit over time, there is a window where services observe unsynchronized states. This is **eventual consistency** at the workflow level.

For example, Payment Service has authorized funds while Booking Service has not yet confirmed the reservation. For a few seconds, the user may see `PAYMENT_PENDING` or `CONFIRMING`. The API should not return "booking succeeded" before the business reaches `CONFIRMED`.

Not all data requires system-wide strong consistency:

- Booking status is authoritative in Booking Service.
- Payment status is authoritative in Payment Service.
- Search projections update asynchronously with acceptable lag.
- Notification history is a delivery record, not what determines booking validity.

A UI screen can display the latest known status with a timestamp or a "processing" state to avoid misrepresenting progress.

If a Saga holds a slot while awaiting payment, the hold needs a TTL and bounded renewal mechanism. If the user abandons the flow, expiration must trigger compensation or reconciliation. Hold TTLs and Saga deadlines must align; deleting a hold while payment is still processing can charge for a reservation that no longer has capacity.

### Business metrics to monitor

- Percentage of Sagas completing before deadline.
- p50/p95/p99 time from request to `CONFIRMED`.
- Number of Sagas in `PAYMENT_UNKNOWN` or `MANUAL_REVIEW`.
- Age of slot holds and expired hold count.
- Compensation success rate and retry counts.
- Payment/booking mismatches detected via reconciliation.
- Late events, duplicate events, DLQ counts, and aged backlogs.

## 13. Security and data in Sagas

Sagas often involve multiple services and brokers, expanding the access surface:

- Each service uses its own service identity and can publish/subscribe only to its authorized topics/queues.
- Commands must validate producer identity, tenant, and permissions within the owning domain.
- Never trust `tenantId`, `amount`, `ownerId`, or payment status solely because they appear in an event.
- Payment Service reads/validates data itself and applies its own rules; other consumers cannot unilaterally declare a payment valid.
- Events should carry minimal data; secrets, tokens, and card data must not be broadcast broadly.
- Logs/traces must mask personal data and enforce access control and retention.
- An orchestrator's state store containing sensitive data also requires encryption and auditing.
- Compensation endpoints need authorization, unintended-replay protection, and audit trails.

A common mistake is granting the orchestrator overly broad access to every service's database. That breaks ownership boundaries. The coordinator should send commands and receive outcomes via controlled contracts rather than directly querying or mutating participant databases.

## 14. Observability, operations, and reconciliation

A successful Saga is not merely a dispatched message or a handler returning 200. You must see **a transaction end-to-end**, even as it crosses services and queues.

Every command/event should carry appropriate identifiers:

- Saga ID: identifies the workflow execution.
- Correlation ID: links requests/events in the same flow.
- Causation ID: indicates which command/event caused the current message.
- Event ID / command ID: prevents duplicates and traces individual messages.
- Aggregate ID and version: identifies the object and update order.
- Trace context: links distributed traces across services.

| Signal | Operational meaning |
| --- | --- |
| Saga count by state | Spot workflows stuck or spiking unusually at a step |
| Saga age / deadline overdue | Identify operations exceeding business deadlines |
| Retry count by dependency | Detect unstable downstream services |
| Compensation success/failure | Measure recovery capability and residual risk |
| Outbox lag / publish failure | Detect unpublished events |
| Inbox duplicate count | Observe redelivery and deduplication activity |
| DLQ depth / oldest age | Identify poison messages and required backlog work |
| Payment/booking mismatch | Detect critical business discrepancies |
| Orchestrator execution error | Monitor coordinator or workflow runtime health |

### Reconciliation is a core part of the workflow

Even well-designed Sagas can encounter unknown states due to timeouts, outages, or integration errors. Periodic reconciliation compares state across systems:

1. Fetch bookings overdue in `PAYMENT_PENDING` or `PAYMENT_UNKNOWN`.
2. Query Payment Service/provider using the payment reference.
3. Compare payment state against booking state and hold state.
4. Execute the safe next step: confirm, void, refund, release, or manual review.
5. Record an audit entry and reconciliation outcome.

Reconciliation requires approved policies and permissions—not arbitrary direct database edits. It is the mechanism for detecting and resolving discrepancies that automatic retries cannot determine.

## 15. Comparing the two models on a booking example

### Option A — Orchestration

Booking Saga Orchestrator persists state. It sends `ReserveSlot`, waits for `SlotHeld`, sends `AuthorizePayment`, waits for the outcome, and then sends `ConfirmBooking`. If payment is declined, it sends `ReleaseSlot`. If payment times out, it queries status before deciding.

If the notification service fails after the booking is confirmed, the orchestrator can record a pending notification task or emit a separate event. It does not need to reverse the booking.

### Option B — Choreography

Booking Service emits `BookingRequested`. Payment Service receives it, performs authorization, and emits `PaymentAuthorized`. Booking Service receives the event and confirms the booking. Notification Service receives `BookingConfirmed` and sends the notification. If `PaymentDeclined`, Booking Service releases the slot and emits `BookingCancelled`.

Services use outbox/inbox, Saga IDs, event IDs, and local state. A dashboard or workflow tracker must aggregate progress so staff can see where a booking is waiting.

| Scenario | Orchestration | Choreography |
| --- | --- | --- |
| Payment timeout | Coordinator sets `PAYMENT_UNKNOWN`, queries, and decides | Payment handler/reconciliation emits status; Booking reacts to event |
| Booking confirm fails after payment | Coordinator drives void/refund and slot release | Payment/Booking event flow coordinates compensation |
| Notification error | Coordinator records auxiliary task or separate event | Notification consumer retries / DLQs independently |
| Duplicate event arrives | Coordinator deduplicates command/result; participants remain idempotent | Each consumer uses inbox/dedup |
| Staff need to inspect a Saga | State machine can show current step and deadline | Must aggregate events/state across services |

Choreography does not necessarily have fewer components: it may require an event bus, inbox/outbox, tracker, reconciliation, and operational tooling. Nor is orchestration automatically a single point of failure if the coordinator uses an appropriately HA state store and runtime.

## 16. Common mistakes

**Keeping a database transaction open while calling multiple services.** Slow networks hold locks and connections for too long; transactions do not cover external side effects.

**Treating compensation as an exact rollback.** Refunds, corrective notices, or order cancellations are new transactions; you cannot honestly erase history.

**Blindly retrying a payment command after a timeout.** The provider may already have charged; use the same idempotency key and reconciliation.

**Missing Saga IDs or correlation.** Makes it hard to stitch logs, events, commands, and states end-to-end.

**Storing workflow state only in orchestrator memory.** Process restarts lose progress; durable checkpoints are required.

**Publishing events and committing the database as two unlinked actions.** Crashing between them drops events or emits events for uncommitted data; use an outbox.

**Having an outbox without consumer deduplication.** Relays can redeliver; consumers need an inbox or idempotent handling.

**Letting notification failure cancel bookings unnecessarily.** Separate core transactions from auxiliary side effects per business requirements.

**Not handling late or out-of-order events.** Use state transitions, version/sequence checks, fencing, or reconciliation.

**Marking `CANCELLED` while compensation is still unfinished.** Business state must reflect incomplete work and the responsible owner.

**Choosing choreography thinking no coordinator or monitoring is needed.** Distributed flows still require ownership, correlation, timeouts, and dashboards.

**Putting participant domain logic inside the orchestrator.** The coordinator should direct flow; each service still owns its decisions and data.

## 17. Practice exercise: designing a Saga for booking and payment

**Hypothetical context:** A booking platform has Booking Service, Payment Service, and Notification Service, each with its own database. Users select a slot, pay, and then receive a notification. The payment provider may respond slowly or time out. The event broker delivers messages with at-least-once semantics and may redeliver. A booking hold has a 10-minute TTL. The target SLO is 99.9% of valid bookings completed or reporting a clear processing status over 30 days.

These numbers are for practice only. Verify actual provider, broker, and datastore capabilities in real deployments.

### Tasks

1. **Draw both architectures:** one orchestration diagram and one choreography diagram for the same workflow; mark data-owning services, where next-step decisions are made, commands/events, Saga ID, and state stores.
2. **Design the state machine:** use states such as `PENDING`, `SLOT_HELD`, `PAYMENT_PENDING`, `PAYMENT_UNKNOWN`, `PAYMENT_AUTHORIZED`, `CONFIRMED`, `COMPENSATING`, `CANCELLED`, and `MANUAL_REVIEW`. For each transition, specify valid events/commands, timeouts, and conditions.
3. **Design compensation:** define compensating actions for holding slots, authorizing/capturing payment, confirming bookings, and notifications. Explicitly mark actions that cannot be completely undone.
4. **Design outbox/inbox and idempotency:** draft schemas/pseudocode for outbox, inbox, and Saga state. Ensure local transactions update business state alongside outbox/inbox where appropriate.
5. **Classify failures:** handle payment decline, timeout where provider captured funds, transient booking confirmation failure, hold expiration while payment is pending, notification redelivery, failed refunds, and late events arriving after Saga cancellation.
6. **Observability and operations:** propose dashboards for Saga state/age, timeouts, retries, outbox lag, DLQ, compensation, and payment mismatches. Write a reconciliation procedure for `PAYMENT_UNKNOWN` and `MANUAL_REVIEW`.
7. **Choose a model:** select orchestration, choreography, or a hybrid; state reasons, risks, operational costs, required capabilities, and review triggers.

### Acceptance criteria

| Goal | Evidence |
| --- | --- |
| No duplicate payment charges due to retries | Provider operation ID / idempotency key and transaction reconciliation |
| Booking state never contradicts payment state | Concurrency/failure tests and reconciliation reports |
| Event redelivery creates no duplicate side effects | Inbox / unique event ID and replay tests |
| Crash between DB commit and publish loses no events | Outbox relay recovery tests |
| Compensation reflects true state | Failed refund/release tests and manual review |
| Overdue workflows are detected | Alerts on Saga age/deadline and runbooks |
| End-to-end traceability | Traces/logs linking Saga ID, correlation ID, and event ID |
| Clients understand asynchronous states | Clear operation/status API endpoint and contract |

## 18. Well-Architected assessment

| Pillar | Questions for Sagas |
| --- | --- |
| **Operational Excellence** | Are there state dashboards, runbooks, DLQ replay, reconciliation, audits, and owners for every step? |
| **Security** | Do commands/events enforce identity, least privilege, tenant validation, data minimization, and state store protection? |
| **Reliability** | Are timeouts, retries, duplicates, out-of-order events, crashes, compensations, and provider ambiguity handled? |
| **Performance Efficiency** | Do per-step wait times, locks/queues, orchestration overhead, and event fan-out meet SLOs? |
| **Cost Optimization** | Are long-running workflows, state retention, message storage, retries, and reconciliation budgeted? |
| **Sustainability** | Do we avoid continuous polling, retry storms, redundant events, and retaining unnecessary payloads? |

## 19. Checklist before moving a Saga to production

- [ ] The workflow genuinely requires multiple local transactions; a single transaction is insufficient.
- [ ] Saga ID, operation ID, command/event ID, and correlation are defined.
- [ ] Every participant owns its own data and transactions; no other service modifies its database directly.
- [ ] Orchestration/choreography is chosen based on complexity, ownership, and operational capability.
- [ ] The state machine defines valid transitions, unknown states, and manual review states.
- [ ] Every local transaction commits durably and handles duplicates safely.
- [ ] Outbox/inbox or an equivalent mechanism handles commit/publish gaps and redelivery.
- [ ] Per-step timeouts, overall Saga deadlines, and retries/backoff are bounded.
- [ ] Compensation is defined for each side effect; irreversible actions are explicitly noted.
- [ ] Payments/external providers have idempotency keys and reconciliation for ambiguous outcomes.
- [ ] Event schemas include version, producer, event ID, Saga ID, and publish/subscribe permissions.
- [ ] Delayed, out-of-order, duplicate, and stale-version events are tested.
- [ ] Hold/resource TTLs align with workflow deadlines and cancellation.
- [ ] Dashboards track Saga age/state, retries, compensation, outbox lag, DLQ, and mismatches.
- [ ] Manual review/reconciliation procedures and assigned owners exist.
- [ ] Crashes have been tested at commit, publish, provider-call, and compensation boundaries.
- [ ] Security, retention, data minimization, cost, and access controls have been reviewed.

Sagas enable multiple services to achieve a shared business goal without holding long-lived distributed transactions. **Orchestration** centralizes progress in a coordinator to drive steps, timeouts, and compensation; **choreography** lets services coordinate via events along domain boundaries. Whichever you choose, reliability depends on local transactions, durable state, idempotency, outbox/inbox, handling ambiguous outcomes, realistic compensation, and reconciliation. A Saga is trustworthy only when the system can accurately answer: what step is the transaction on, which side effects have occurred, what still needs compensation, and who is responsible when automatic recovery is not enough.
