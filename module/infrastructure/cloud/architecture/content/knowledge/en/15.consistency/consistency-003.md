# Local Transactions and Limits of Distributed Transactions

## 1. Why is the transaction boundary an architectural decision?

A single business operation often touches multiple pieces of data: creating a rental booking, reserving equipment, deducting a quota, writing history, and sending notifications. If all the data lives in one database, you can use a single transaction so that changes either all succeed or all roll back together. However, in cloud architectures, data frequently belongs to multiple independent services or datastores. In that case, you cannot assume a single `COMMIT` statement spans every component.

In the **CLOUD_ARCHITECTURE** module, data and compute design must align with business requirements, reliability, security, scalability, cost, and operations. **Local transactions** help protect correctness inside a single transaction boundary. **Distributed transactions** attempt to coordinate multiple resources over a network, where timeouts, connection drops, node failures, retries, and ambiguous outcomes occur.

**API contract**, **transaction protocol**, and **business workflow** are three distinct concepts. A request calling multiple APIs does not automatically become a distributed transaction; the system needs either a protocol with real support or a workflow model with explicit states, retries, and compensation.

After this lesson, you will be able to explain ACID and isolation; distinguish local atomicity from cross-service consistency; compare 2PC, Sagas, transactional outbox/inbox, and eventual consistency; design idempotency, retries, timeouts, compensation, and reconciliation; and choose where strong atomicity is required versus where intermediate states are acceptable.

## 2. Local transactions and ACID

A transaction is a unit of data work managed by a database. For relational database management systems supporting ACID, the properties are commonly described as:

| Property | Meaning | Example in BookingCloud |
|---|---|---|
| **Atomicity** | Changes in a transaction commit or roll back together | Creating a booking and claiming a slot succeed together; if one fails, neither commits |
| **Consistency** | A transaction moves data from one valid state to another valid state according to constraints/rules enforced by the database and application | No two bookings can simultaneously occupy the same unique slot |
| **Isolation** | Concurrent transactions are isolated according to the chosen isolation level | Two customers competing for the same slot cannot both commit successfully |
| **Durability** | After a successful commit, data is persisted according to the database's durability guarantees | The API returns success only after the booking has been committed under the durability policy |

**Consistency in ACID** preserves database invariants/constraints; it does not automatically enforce every business rule across multiple external systems. For example, a transaction can guarantee that a booking and a slot are recorded properly in the database, but it cannot by itself guarantee that an email provider sent an email or a payment service collected funds.

### 2.1. Local transaction example

Suppose each slot is identified by `device_id` + `slot_id` and may be occupied by at most one booking. The schema might define a unique constraint on this pair or a reservation table with a corresponding unique key.

~~~sql
BEGIN;

INSERT INTO bookings (
    booking_id, customer_id, device_id, slot_id, status
) VALUES (
    :booking_id, :customer_id, :device_id, :slot_id, 'confirmed'
);

UPDATE device_slots
SET status = 'reserved',
    booking_id = :booking_id
WHERE device_id = :device_id
  AND slot_id = :slot_id
  AND status = 'available';

-- The application must verify that exactly one row was updated.
-- Otherwise, ROLLBACK and return conflict.

COMMIT;
~~~

The SQL above is a **logical pattern**; ordering and constraints must be adapted to the actual schema. One implementation uses conditional updates / unique constraints and checks affected row counts; another locks the relevant row. The goal is for the database to arbitrate concurrency contention, rather than relying on an earlier `SELECT` followed by an unprotected `INSERT` as two separate steps.

If the transaction detects that the slot is already taken, the application rolls back and returns an appropriate business error, such as HTTP 409. Do not return 201 merely because the API accepted the request.

### 2.2. Isolation and race conditions

Two requests can simultaneously read the slot status as `available` and then both try to create a booking. A plain read does not hold ownership of the slot until the write executes.

| Protection mechanism | Idea | Notes |
|---|---|---|
| Unique constraint | The database rejects duplicate records | Must define the right business key and handle duplicate key errors |
| Conditional update | Updates only if status is still `available` | Check row count and transaction outcome |
| Row lock | Locks the slot row during the transaction | Requires consistent lock ordering, timeouts, and deadlock handling |
| Serializable isolation | The database guarantees results equivalent to a valid serial order | May require retrying serialization failures; higher overhead and contention |

Not every API needs `SERIALIZABLE`. Choose isolation suited to your invariants and workload, then test under concurrency. With `READ COMMITTED`, unique constraints or conditional writes can still protect simple invariants; for more complex rules, prove safety against the specific transaction model.

### 2.3. Longer transactions carry higher costs

Keeping a transaction open while calling an email service, payment gateway, or another service is a common anti-pattern:

- Connections and locks are held while waiting on the network.
- A slow dependency increases latency and exhausts the connection pool.
- Timeouts leave the caller unsure whether the remote operation completed.
- Retries can duplicate side effects or create contending transactions.
- The database scales poorly when transactions are long-lived and lock-heavy.

Local transactions should wrap **only the data changes that must be atomic within the same storage boundary**, never spanning unnecessary network I/O steps.

## 3. What is a transaction boundary?

A **transaction boundary** is the scope of data and operations atomically controlled by a single transaction manager. The boundary may be a transaction in one relational database; some datastores provide transactions scoped to a single record, document, or partition. Do not assume all databases share the same scope or semantics.

In a service-oriented architecture, each service typically owns its own data. Other services interact through APIs or events rather than modifying an internal database directly. This establishes clear ownership boundaries, but it also means a cross-service business flow no longer fits inside a single local transaction.

~~~mermaid
flowchart TB
    subgraph S1["Booking service / transaction boundary A"]
      BA["Booking API"]
      BDB[("Booking DB")]
      BA --> BDB
    end
    subgraph S2["Inventory service / transaction boundary B"]
      IA["Inventory API"]
      IDB[("Inventory DB")]
      IA --> IDB
    end
    subgraph S3["Payment service / transaction boundary C"]
      PA["Payment API"]
      PDB[("Payment DB")]
      PA --> PDB
    end
    BA -->|"HTTP/event over network"| IA
    BA -->|"HTTP/event over network"| PA
~~~

Each DB manages transactions internally. HTTP/event arrows do not automatically extend Booking DB's transaction into Inventory DB or Payment DB.

### 3.1. Not every "multi-step" flow is a distributed transaction

A request calling three APIs sequentially is merely a workflow orchestrating multiple operations. To qualify as a distributed transaction in the strict sense, participants must take part in a coordinated commit/abort protocol with prepare and unified decision mechanisms. Many microservice systems do not use such a protocol; they use Sagas, event-driven workflows, or eventual consistency.

This distinction matters when claiming "the entire operation is atomic." If a system only makes sequential HTTP calls, the first operation may have already committed when the second call times out. The caller gets no automatic rollback for the committed change in the first service.

## 4. Why are distributed transactions harder?

When participants live across different processes, networks, or datastores, the system must handle:

- **Partial failure:** one service committed, but the response was lost; the caller does not know the outcome.
- **Network partition/timeout:** inability to distinguish whether a request never arrived, is still processing, or succeeded with a lost reply.
- **Coordinator failure:** the coordinator may crash after participants have prepared or partially committed.
- **Concurrent transactions:** multiple workflows may contend for the same resources across services.
- **Different storage semantics:** participants may use databases, queues, or external APIs that do not support the same protocol.
- **Long duration:** a business process can span minutes, hours, or days; holding locks across the entire duration is impractical.
- **Operational complexity:** requires logs, correlation IDs, workflow state, timeouts, retries, recovery, and reconciliation.

### 4.1. Example: booking requiring equipment hold and payment

The workflow consists of: Booking service creates `PENDING`; Inventory service holds a slot; Payment service authorizes/charges; Booking service transitions to `CONFIRMED`; Notification worker sends confirmation.

If the slot hold succeeds and payment fails, the system must release the slot. If payment succeeds but the confirm step times out, you cannot blindly create a new payment; you must query status or resume the workflow using the same operation identity.

~~~mermaid
sequenceDiagram
    autonumber
    actor C as Customer
    participant B as Booking service
    participant I as Inventory service
    participant P as Payment service
    participant N as Notification

    C->>B: Create booking
    B->>B: Local transaction: PENDING
    B->>I: Hold slot
    I-->>B: Hold accepted
    B->>P: Authorize payment
    alt Payment accepted
        P-->>B: Payment authorized
        B->>B: Local transaction: CONFIRMED
        B->>N: Publish confirmation event
        B-->>C: Booking confirmed
    else Payment declined
        P-->>B: Declined
        B->>I: Release held slot
        I-->>B: Slot released
        B->>B: Local transaction: FAILED
        B-->>C: Booking failed
    end
~~~

The diagram only shows the happy path and one decline branch. It does not yet address timeouts, crashes, or lost responses; that is why workflow state, idempotency, and recovery are required.

## 5. Two-phase commit (2PC)

**Two-phase commit** is a protocol that coordinates commits between a coordinator and supporting participants. It splits the process into two phases:

1. **Prepare:** the coordinator asks participants to prepare the transaction. Each participant checks whether it can commit, persists the required state to its log, and replies `YES`/`NO`. `YES` means the participant promises to commit if the final decision is `COMMIT`; it does not commit on its own yet.
2. **Commit/Abort:** if all participants reply `YES`, the coordinator decides `COMMIT`; if any replies `NO` or a condition fails, the coordinator decides `ABORT`. Participants execute the decision they receive.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Coordinator
    participant A as Participant A
    participant B as Participant B

    C->>A: PREPARE transaction
    C->>B: PREPARE transaction
    A->>A: Validate + persist prepare state
    B->>B: Validate + persist prepare state
    A-->>C: YES
    B-->>C: YES
    C->>C: Persist COMMIT decision
    C->>A: COMMIT
    C->>B: COMMIT
    A-->>C: ACK
    B-->>C: ACK
~~~

If a participant replies `NO`, the coordinator decides `ABORT` and notifies participants. If the coordinator fails after prepare, participants may have to hold locks/resources while waiting for the decision; 2PC can be **blocking** in certain failure scenarios. Recovery depends on durable logs and the ability of participants/coordinator to recover and finalize the decision.

### 5.1. Requirements to use 2PC

2PC can only be used when every participant supports the same protocol or a distributed transaction manager with a semantically valid adapter. An arbitrary HTTP API, third-party payment gateway, or email service does not automatically become a 2PC participant.

### 5.2. Trade-offs of 2PC

| Benefits | Costs / risks |
|---|---|
| Coordinated commit/abort decision across supporting participants | Coordinator and participants require protocol/log/recovery support |
| Can preserve atomicity across multiple resources within supported models | Participants hold locks/resources while awaiting the decision |
| Application gets a more unified transaction model | Blocking when coordinator/communication fails at an inopportune moment |
| Fits certain systems with strict requirements and homogeneous participants | Latency, coupling, operational complexity, and service limitations |

2PC does not make a system immune to network failures. It shifts part of the problem into protocol recovery; operations teams still need to understand prepared transactions, timeouts, coordinator logs, and handling stuck transactions.

### 5.3. When is 2PC worth considering?

2PC can fit when cross-resource atomicity is mandatory; all participants and infrastructure explicitly support the transaction protocol; transactions are short, participants are stable, and the latency/availability trade-off is acceptable; and the organization can operate the coordinator, recovery logs, and prepared transactions.

It is usually unsuitable for stitching together independent SaaS/HTTP APIs, payment providers, or long-running workflows. In those cases, Sagas and compensation are generally more practical.

## 6. Saga: a sequence of local transactions and compensating actions

A **Saga** models a distributed business process as a sequence of local transactions. Each participant commits in its own database; if a later step fails, the workflow runs **compensating actions** to bring business state to an acceptable outcome.

A Saga is not an atomic rollback in the database sense. Compensation is a new business operation that can fail, may need retries, and does not necessarily erase effects that already occurred externally.

### 6.1. Booking Saga example

| Step | Local transaction | If a later step fails, possible compensation |
|---|---|---|
| 1. Create pending booking | Booking DB writes `PENDING` | Cancel pending booking |
| 2. Hold slot | Inventory DB writes `HELD` | Release slot |
| 3. Authorize payment | Payment DB/provider writes `AUTHORIZED` | Void authorization |
| 4. Confirm booking | Booking DB transitions to `CONFIRMED` | If business rules allow, transition to `CANCELLATION_PENDING` and process cancellation |
| 5. Capture payment | Payment writes `CAPTURED` | Refund; this is a new transaction, not deleting the charge |
| 6. Send notification | Notification system writes `SENT`/`ACCEPTED` | May send a follow-up correction; a sent email cannot be reliably "recalled" |

Sagas should generally order steps so failure-prone or less-reversible steps occur before hard-to-compensate side effects. For payments, authorizing first and capturing only after booking confirmation can reduce refunds, provided the provider and business workflow support it.

~~~mermaid
flowchart TD
    START["Start booking saga"] --> S1["T1: Create PENDING booking"]
    S1 --> S2["T2: Hold inventory slot"]
    S2 --> S3["T3: Authorize payment"]
    S3 --> S4["T4: Confirm booking"]
    S4 --> S5["T5: Capture payment / notify"]
    S5 --> DONE["Completed"]
    S2 -->|"Failure"| C1["C1: Cancel pending booking"]
    S3 -->|"Failure"| C2["C2: Release slot"]
    C2 --> C1
    S4 -->|"Failure"| C3["C3: Void authorization"]
    C3 --> C2
    C1 --> FAIL["Compensated / Failed"]
    C2 --> FAIL
    C3 --> FAIL
~~~

This simplified diagram only illustrates reversal steps. A real system must represent timeouts, unknown outcomes, compensation retries, manual intervention, and `PARTIALLY_COMPENSATED` states.

### 6.2. Orchestration and choreography

| Style | How it works | Advantages | Trade-offs |
|---|---|---|---|
| **Orchestration** | A saga orchestrator persists state and calls participants per workflow | Clear sequencing, timeouts, retries, and compensation; easy to observe business flow | Orchestrator needs HA, persistence, and governance; flow logic is more centralized |
| **Choreography** | Participants emit events and other services react to events | Fewer central coordinators; services remain relatively decoupled | Harder to see the full workflow, easy to create complex event cycles, harder tracing and compensation |

For workflows with branching, timeouts, conditions, and compensation steps, orchestration is usually easier to control. Choreography fits simple reactive flows with few steps and clear ownership. Neither approach automatically eliminates distributed failures.

### 6.3. Saga state machine

Every Saga needs a stable identifier and recoverable state:

~~~text
CREATED
  -> BOOKING_PENDING
  -> INVENTORY_HELD
  -> PAYMENT_AUTHORIZED
  -> BOOKING_CONFIRMED
  -> COMPLETED

Failure paths:
  -> COMPENSATING
  -> COMPENSATED
  -> MANUAL_REVIEW
  -> FAILED
~~~

The state machine must record the current step, participant results, attempt counts, deadlines, required compensations, and correlation ID. An orchestrator restart must read durable state and resume rather than relying on in-memory process state.

### 6.4. Compensation is not history rollback

If a payment already captured 500,000 VND, a compensating refund of 500,000 VND creates a new financial transaction. There may be delays, fees, pending refund states, or provider rejections. You cannot erase the charge event as though it never happened.

Similarly, a held slot may have expired or been allocated to someone else after release; a sent email cannot be guaranteed to be recalled; an event already processed by an external consumer may have triggered hard-to-reverse side effects. Therefore, compensation requires **business semantics**, not just a technical inverse function.

## 7. Transactional outbox and inbox

A common bug in event-driven architecture is writing to the DB and publishing an event as two separate operations. If the DB commit succeeds and the process crashes before publishing, data changed while consumers never receive the event. Conversely, publishing first and then rolling back the DB can leave consumers processing an event for a transaction that never existed.

### 7.1. Transactional outbox

The **Outbox pattern** writes the business change and the event to be published within **the same local DB transaction**. A relay later reads committed outbox records and publishes them to the broker.

~~~mermaid
sequenceDiagram
    autonumber
    participant API as Booking API
    participant DB as Booking DB
    participant Relay as Outbox relay
    participant Q as Message broker
    participant W as Consumer

    API->>DB: BEGIN
    API->>DB: INSERT booking
    API->>DB: INSERT outbox event
    API->>DB: COMMIT
    Relay->>DB: Read committed outbox rows
    DB-->>Relay: event_id + payload
    Relay->>Q: Publish event
    Q-->>Relay: Publish acknowledged
    Relay->>DB: Mark published / record offset
    Q-->>W: Deliver event
~~~

The outbox guarantees that **the booking and the intent to emit the event** commit together in the DB. It does not guarantee a message is published only once. If the relay publishes successfully but crashes before marking the row published, it may republish after restarting.

Therefore, consumers must handle duplicate delivery via idempotency/deduplication. The outbox requires appropriate polling or change-data-capture, indexes by status/time, retries, retention, cleanup, and backlog alerting.

### 7.2. Inbox / deduplication at the consumer

A consumer can record `event_id` into an inbox/dedup table together with the business update in a single local transaction:

~~~sql
BEGIN;

INSERT INTO processed_events (event_id, processed_at)
VALUES (:event_id, CURRENT_TIMESTAMP)
ON CONFLICT (event_id) DO NOTHING;

-- Process the event only if the new insert succeeds.
-- Update business state in the same transaction.

COMMIT;
~~~

This is pseudo-SQL following PostgreSQL-like syntax. Check the insert result to know whether the event was already processed. If the business update and processed marker are not in the same transaction, a crash between them can still cause lost or duplicate processing.

For side effects outside the DB, such as calling a payment provider, a database dedup marker alone does not guarantee exactly-once execution. You need provider-supported idempotency keys or workflow state/reconciliation to handle unknown outcomes.

### 7.3. Outbox does not replace Saga

Outbox solves **reliably writing data and publishing events** from a single local transaction. Saga solves **coordinating multiple local transactions and compensations** across services. They are often used together:

- The orchestrator writes saga state and commands/events to its outbox.
- Participants receive commands, handle them idempotently, and record results.
- Participants write reply events to their outbox within the same local update.
- The orchestrator receives events, transitions state, and decides the next step.

## 8. Idempotency, retries, and timeouts

Distributed workflows cannot completely avoid duplicates or ambiguous outcomes. Designs must assume requests/messages can be redelivered.

### 8.1. Idempotency key

An operation can carry a key unique within its business scope:

~~~http
POST /payments/authorize
Idempotency-Key: saga-7812-payment-authorize
Content-Type: application/json

{
  "bookingId": "bkg-8124",
  "amount": 500000,
  "currency": "VND"
}
~~~

The provider/payment service stores the outcome associated with the key. When receiving the same key and the same request semantics again, it returns the previous result or an appropriate response; the same key with a different payload must be rejected per the contract. Key retention must be long enough to cover the retry/reconciliation window.

Do not reuse the same key for two independent operations. Namespace keys by tenant/customer/operation if uniqueness scope is not global.

### 8.2. A timeout does not mean the operation failed

Suppose the orchestrator sends an authorize payment request. The payment service commits successfully, but the response is lost. The orchestrator times out:

- You cannot conclude the payment did not occur.
- Resending with a new key can create duplicate authorizations/charges.
- Ignoring the outcome can leave a booking unconfirmed even though funds were held.

Safe recovery:

1. Retry with the same idempotency key if the provider contract permits.
2. Query operation status by payment ID/key when the API supports it.
3. If the outcome remains unclear, mark the Saga as awaiting verification instead of blindly running compensation.
4. Escalate to reconciliation/manual review once the deadline passes.

### 8.3. Bounded retries

Retries should have proper timeouts; exponential backoff and jitter; maximum attempts/deadlines; retryable vs. non-retryable classification; circuit breakers/bulkheads or rate limits where appropriate; idempotency/deduplication for side effects; and DLQs or failed states requiring human handling.

Never infinitely retry validation errors, insufficient funds, or permission denied. Do not unconditionally retry all 5xx responses when an operation has non-idempotent side effects.

## 9. Eventual consistency and intermediate states

In a Saga, services commit at different times. For a period, the system may observe `Booking=PENDING`, `Inventory=HELD`, and `Payment=AUTHORIZING`. This is not necessarily an error if intermediate states are modeled and handled properly by consumers. Once the workflow completes, read models are updated and state converges to the final outcome.

**Eventual consistency** means that if no new updates arrive and propagation/application steps finish, related replicas/read models eventually converge according to system rules. It does not mean "data becomes correct automatically," nor does it specify a fixed convergence time.

### 9.1. Design explicit business states

| State | Meaning | What consumers/UI should do |
|---|---|---|
| `PENDING` | Workflow started, not yet complete | Show processing; do not claim booking confirmed |
| `INVENTORY_HELD` | Slot temporarily held | Track payment/confirmation deadline |
| `PAYMENT_PENDING` | Awaiting payment outcome determination | Do not create a new payment; check the same operation ID |
| `CONFIRMED` | Required business conditions met | Display confirmed booking |
| `COMPENSATING` | Releasing/reversing prior effects | Show cancellation/refund in progress if appropriate |
| `COMPENSATED` | Required compensations completed | Display failure/cancellation and relevant details |
| `MANUAL_REVIEW` | Outcome cannot be automatically verified | Route to support/ops handling |
| `FAILED` | Workflow terminated in failure per definition | Stop automatic retries unless policy dictates |

The UI should not show `CONFIRMED` just because a booking record was created if business policy requires inventory and payment to succeed first.

### 9.2. Read-your-writes and read models

If a client creates a booking and immediately reads from a read replica or event-projected view, the data may not appear yet. You can read from the write source briefly after a command; return an operation ID and `PENDING` status for the client to poll; use event cursors or versions so consumers know how far the projection has processed; and clearly state the read endpoint's consistency guarantee.

Never use an eventually consistent read replica as the sole decision source for booking invariants.

## 10. Choosing a strategy by requirements

| Situation | Mechanism typically considered | Reason |
|---|---|---|
| Multiple tables in one relational DB must commit together | Local ACID transaction + constraints | Simple, clear atomicity |
| Two datastores share a distributed transaction protocol, strict atomicity required | 2PC/XA if platform supports it and trade-offs are acceptable | Coordinated commit protocol |
| Long workflow, multiple services, business compensation needed | Saga orchestration/choreography | Avoids holding distributed locks throughout |
| DB write and event emission | Transactional outbox | Prevents dropped events between DB commit and publish |
| Consumer may receive duplicate messages | Inbox/deduplication + idempotent handler | Protects against duplicate processing |
| Reports/read models can update with delay | Event-driven projection / eventual consistency | Improves decoupling and scalability |
| Side effects not easily reversible | Pending state, authorize-before-capture, reconcile/manual review | Avoids promising fake rollbacks |

### 10.1. Decision questions

1. Which invariants must hold at all times, and which can hold after the workflow completes?
2. Can data be grouped into a single transaction boundary without breaking service ownership or scaling?
3. Do participants support a distributed transaction protocol? If not, do not pretend you are using 2PC.
4. Does compensation have real business meaning, or is it just a reverse API call?
5. On timeout, can outcomes be queried by operation ID / idempotency key?
6. Can users accept `PENDING`/`PROCESSING` states, or do they require an immediate final decision?
7. Who monitors stuck Sagas, DLQs, and reconciliation?
8. Is the operational cost of a distributed workflow justified by the benefits of splitting services?

## 11. Security at distributed transaction boundaries

Distributed workflows increase the number of services that can view or modify parts of the data. Essential controls include:

- Service identity and least privilege for every command/event.
- Authenticate publishers/consumers; do not trust a message solely because it arrived from the broker.
- Validate schemas, tenant IDs, event IDs, versions, and correlation fields.
- Protect the idempotency store from unauthorized access or tampering.
- Never put access tokens, payment credentials, or unnecessary PII into event payloads.
- Encrypt data in transit and at rest; restrict read access to DLQs, outboxes, and workflow histories.
- Audit compensations, manual overrides, and replay operations.
- Prevent unintended replay using event IDs, timestamps/nonces, or state transition rules; do not confuse business deduplication with identity authentication.

A Saga orchestrator may hold sensitive state and hold permissions to invoke multiple services. Protect it as a high-blast-radius component: strict RBAC, secret rotation, auditing, state backups, and workflow change control.

## 12. Observability, recovery, and reconciliation

A distributed transaction/workflow must be observable across services. Fields to propagate in a controlled manner:

| Field | Purpose |
|---|---|
| `saga_id` | Identifies a business workflow |
| `operation_id` | Identifies a specific step/operation |
| `correlation_id` | Links logs/traces across services |
| `event_id` | Deduplicates events |
| `causation_id` | Identifies which event/command led to the current event |
| `attempt` | Tracks retries |
| `deadline` | Tracks the workflow's business deadline |
| `state` | Current state and pending step |

Avoid using `saga_id` as a metric label if cardinality is very high; record it in logs/traces while aggregating metrics by operation/state/service.

### 12.1. Useful metrics

- Number of Sagas in `PENDING`/`COMPENSATING`/`MANUAL_REVIEW`.
- Oldest workflow age and deadline breach rate.
- Success rate, compensation success/failure rate, and manual intervention rate.
- Unpublished outbox count and oldest outbox message age.
- Consumer lag, duplicate event rate, retry count, and DLQ depth.
- Payment/booking mismatches and count of operations with unknown outcomes.
- p95/p99 latency per participant and end-to-end workflow completion time.
- Queue, database, network, and orchestration cost per successful workflow.

### 12.2. Reconciliation

Some external systems cannot provide reliable synchronous outcomes. For example, a payment gateway may have charged a card even though the callback was lost. Reconciliation jobs should fetch operations stuck in pending/unknown past their deadline; query status from the provider by transaction/reference ID; compare against the internal booking/payment ledger; decide whether to resume the workflow, capture/void/refund, or escalate to manual review; then log an audit record and update state via a local transaction.

Reconciliation is a normal part of distributed transaction architecture, not a rare emergency patch.

## 13. Well-Architected assessment

| Perspective | Review question | Evidence |
|---|---|---|
| **Operational Excellence** | Can stuck Sagas be located and recovered after an orchestrator restart? | Persistent state, runbooks, replay/repair, dashboards, and audits |
| **Security** | Who is allowed to send commands, inspect payloads, read DLQs, and run compensations? | Service identity, least privilege, encryption, audits |
| **Reliability** | Do participant failures/timeouts or duplicate events corrupt business state? | Idempotency tests, outbox/inbox, fault injection, reconciliation |
| **Performance Efficiency** | Are transactions too long, lock contention high, or workflows making excessive network round trips? | DB lock metrics, p95 participant/workflow latency, throughput |
| **Cost Optimization** | How much do the coordinator, broker, retries, storage, and reconciliation cost? | Cost/workflow, message volume, retry rate, retention |
| **Sustainability** | Are there retry loops, duplicate events, overly frequent polling, or unbounded state retention? | Duplicate rate, polling efficiency, retention/lifecycle |

An architecture passes review only when trade-offs are stated and tests prove the desired behavior. Adding a Saga does not automatically make a system reliable; it increases the number of states and recovery mechanisms that must be operated.

## 14. Practice exercise: booking across three services

BookingCloud is split into Booking, Inventory, and Payment services, each with its own database. Users create a rental order through the flow: Booking creates `PENDING`; Inventory holds the slot; Payment authorizes the amount; Booking confirms; Payment captures; Notification sends an email.

Scenarios to handle:

- Inventory holds the slot successfully, but the response times out.
- Payment authorizes successfully, but the callback is lost.
- Booking confirms successfully, but the orchestrator crashes before persisting state.
- Payment captures successfully, but the notification service is unavailable.
- Slot-release compensation fails because the Inventory service is undergoing maintenance.
- The queue delivers the same event twice.
- A Saga stays pending for over 10 minutes and the slot hold is about to expire.

Complete the following:

**Task 1 — Transaction boundaries:** identify which data lives in each local transaction and which invariants must be preserved in each service.

**Task 2 — Choosing a protocol:** explain why sequential HTTP calls are not 2PC; under what conditions 2PC could be used; and propose a Saga for this workflow.

**Task 3 — Designing the Saga state machine:** list states, commands, events, timeouts, retries, and compensations for the six steps.

**Task 4 — Ambiguous outcomes:** design how to query payment using the same idempotency key/reference on timeout. Never create a second charge just because a response was missing.

**Task 5 — Outbox/inbox:** identify which events are written via outbox, which consumers deduplicate, and which states update in the same local transaction.

**Task 6 — Compensation failure:** if slot release fails, what state does the workflow enter, how long should it retry, when does it escalate to `MANUAL_REVIEW`, and who is authorized to resolve it?

**Task 7 — Measurement:** propose metrics for workflow age, compensation success, duplicate events, payment mismatches, p95 latency, and cost per booking.

### Sample analysis framework

| Step | Local commit | Simulated failure | Recovery / compensation |
|---|---|---|---|
| Create booking | Booking `PENDING` + outbox command | Response lost | Query by booking/idempotency key |
| Hold slot | Inventory `HELD` + expiry | Timeout with unknown outcome | Query hold ID or retry with same key |
| Authorize payment | Payment `AUTHORIZED` | Callback lost | Query provider by reference |
| Confirm booking | Booking `CONFIRMED` | Orchestrator restart | Resume from persisted saga state |
| Capture payment | Payment `CAPTURED` | Response lost | Query status; avoid duplicate charges |
| Notification | Notification event accepted | Worker failure | Idempotent retry; DLQ/manual review |

This is a structural suggestion, not the only answer. Clarify the states of each participant and the semantics of external providers.

## 15. Checklist before choosing a transaction strategy

- [ ] Business invariants are listed and enforcement locations are defined.
- [ ] Local transactions are as short as possible and stay within a single supported storage boundary.
- [ ] Isolation, unique constraints, locks, and concurrency behavior have been tested.
- [ ] Multiple HTTP calls are not assumed to be an atomic transaction.
- [ ] If using 2PC, every participant supports the protocol and a coordinator recovery plan exists.
- [ ] If using a Saga, every local transaction and compensating action has clear semantics.
- [ ] Saga state is durably persisted with timeouts/deadlines and a manual review path.
- [ ] Outbox writes occur in the same transaction as business changes; consumers handle duplicates via inbox/idempotency.
- [ ] External side effects use idempotency keys, status queries, and reconciliation where possible.
- [ ] Eventual consistency and intermediate states are reflected in the API/UI.
- [ ] DLQ, replay, compensation failures, and reconciliation have owners and runbooks.
- [ ] Logs/traces correlate workflows without exposing sensitive data.
- [ ] Fault-injection tests cover crashes, timeouts, duplicates, partial commits, and participant outages.
- [ ] Cost/latency/availability of the chosen strategy have been evaluated against Well-Architected criteria.

Local transactions are a powerful tool for protecting invariants inside a single data boundary. When a business workflow spans multiple services, you cannot assume atomicity propagates across network calls. Choose a genuinely supported protocol, or model the workflow with Sagas, outbox/inbox, idempotency, and reconciliation—while transparently exposing intermediate states and recovery limits. That is how to build correct and operable distributed systems.
