# Modeling Events for What Happened Instead of Storing Only Final State

## 1. Why Is Final State Not Enough to Describe the Business Domain?

In data design, the familiar approach is to store the **current state** of an entity: what status an order is in, how much money remains in an account, or whether a subscription plan is active. This approach works well when the main question is “what does the entity look like right now?”. However, many business decisions also require knowing **what happened, in what order, at what time, and for what reason**.

Suppose the **orders** table has only one record:

| order_id | order_status | payment_status | total_minor | currency |
| --- | --- | --- | ---: | --- |
| ORD-731 | CANCELLED | REFUNDED | 125000 | VND |

The record tells us the order was cancelled and the money was refunded. It does not precisely answer: whether the customer cancelled before or after paying, how many times refunds were issued, how long it took from cancellation request to refund completion, or whether any operation was submitted more than once.

Instead of merely overwriting the old value, we can store the sequence of **events that actually happened**:

| Order in sequence | Event | Meaning |
| ---: | --- | --- |
| 1 | **OrderPlaced** | The order was validly created. |
| 2 | **PaymentCaptured** | The payment was successfully recorded. |
| 3 | **OrderCancelled** | The order was cancelled according to business rules. |
| 4 | **RefundIssued** | The refund was executed. |

From this sequence, the system can **derive the current state** while also answering questions about history and progression. The event order in the example is the order accepted by the system for **ORD-731 itself**, not implicitly a global order across all orders.

**Core idea:** state is an outcome at the time of observation; an event is a business fact that has occurred. When the model needs to preserve progression history, state can be built as a **projection** from events.

## 2. Distinguishing Command, Event, and State

These three concepts are related but carry distinct semantics:

| Concept | Question the data answers | Example | Can it be rejected? |
| --- | --- | --- | --- |
| **Command** | What do we want the system to do? | **CancelOrder** | Yes. A delivered order may not be cancellable under the standard workflow. |
| **Domain event** | What actually happened? | **OrderCancelled** | An accepted event itself is a fact; the request to produce an event can be rejected. |
| **State** | What condition is the entity currently in? | **order_status = CANCELLED** | It is the result computed or updated after valid changes. |

Event names should express **completed occurrences** (usually in past tense in English), such as **PaymentCaptured**, **ShipmentDispatched**, **SubscriptionRenewed**. Avoid vague names like **UpdateOrder**, because it does not indicate what happened or what it means to the business.

Distinguish between “user clicks the pay button”, “system sends a capture request”, and “payment provider confirms successful capture”. Only the last occurrence fits the **PaymentCaptured** event. If failed payment attempts need to be stored, define a separate event with clear semantics, such as **PaymentAttemptFailed**, instead of treating every request as a successful transaction.

Some common design terms:

- **Aggregate:** the consistency boundary of a business object, such as an **Order** and the invariants that must hold when changing that order.
- **Event stream:** the sequence of events belonging to an aggregate, read in a deterministic order, typically via an increasing **sequence_no** within each aggregate.
- **Projection/read model:** a structure computed from events to serve queries, such as a current order status table or a refund turnaround report.
- **Event sourcing:** a design approach that treats the stored sequence of events as the **primary source of truth** from which state is reconstructed. A system that emits domain events while still treating a state table as the source of truth is not necessarily event sourced.

## 3. Choosing the Right Events for the Problem

When reading business requirements, look for **meaningful state transitions** rather than listing every attribute assignment. For the orders domain, we can ask:

1. Which milestones does the business want to know happened? For example, order placement, payment capture confirmation, delivery, order cancellation, refund.
2. Which events require proof from an external system? For example, capture is only considered successful upon reliable confirmation.
3. Which rules forbid a transition? For example, you cannot refund more than the total captured amount; you cannot create the same order twice from the same request.
4. Which questions require tracing back history? For example, “how many orders were cancelled after payment capture?” or “how long after cancellation is a refund issued?”.
5. Does the consistency scope of an operation lie within a single aggregate or span multiple aggregates/services?

The following diagram illustrates the logical flow, without prescribing synchronous or asynchronous implementation:

~~~mermaid
flowchart LR
    C["Command: CancelOrder"] --> V{"Check rules"}
    V -->|Invalid| R["Reject and return reason"]
    V -->|Valid| E["Record OrderCancelled"]
    E --> L["Order event stream"]
    L --> P["Projection: current state"]
    L --> A["Projection: history / analytics"]
~~~

In the example, **OrderCancelled** only changes the order status. If the order was already captured, **payment_status** remains **PAID** until **RefundIssued** occurs. Do not merge operational order status and financial status into a single under-expressive **status** field.

## 4. Designing the Structure of an Event

An event needs enough information to identify **what occurrence it is**, **which entity it belongs to**, **in what order it happened**, **what business data it carries**, and **whether it can be safely processed if repeated**.

| Field | Role | Design notes |
| --- | --- | --- |
| **event_id** | Unique identifier of the event. | Use a UUID or guaranteed-unique ID; convenient for tracing and deduplication. |
| **aggregate_type**, **aggregate_id** | Locates the entity owning the event stream. | For example **Order** and **ORD-731**; aggregate boundaries must be clearly defined. |
| **sequence_no** | Logical order within an aggregate. | Unique per (**aggregate_id**, **sequence_no**) pair if the table stores only one aggregate type; does not imply system-wide global order. |
| **event_type** | Type of business occurrence. | Use specific, stable naming. |
| **event_version** | Payload schema version of the event type. | Supports reading older events as schemas evolve. |
| **occurred_at** | Timestamp when the occurrence actually happened according to the data source. | May arrive late or contain clock skew. |
| **recorded_at** | Timestamp when the system recorded the event. | Typically assigned by the storage server; distinct from **occurred_at**. |
| **payload** | Data needed to understand or handle the event. | Define a schema per event_type/version; avoid arbitrary payloads. |
| **producer**, **idempotency_key** | Originating source and key to prevent duplicate request processing. | The idempotency key has a specific scope, such as unique per producer. |
| **correlation_id**, **causation_id** | Links the event to a process and the action that caused it. | Useful when tracing processing flows across multiple services. |

Example of an event in JSON format:

~~~json
{
  "event_id": "a9f7c928-0196-40db-bbb8-f7fe87961dd7",
  "aggregate_type": "Order",
  "aggregate_id": "ORD-731",
  "sequence_no": 2,
  "event_type": "PaymentCaptured",
  "event_version": 1,
  "occurred_at": "2026-11-20T09:15:00Z",
  "recorded_at": "2026-11-20T09:15:02Z",
  "producer": "payment-service",
  "idempotency_key": "capture-PAY-904",
  "correlation_id": "92ed0fd4-9729-4a3e-8b1e-d3c6ae9021ca",
  "causation_id": "719f6535-0b65-4097-a64f-324fc8803acf",
  "payload": {
    "payment_id": "PAY-904",
    "amount_minor": 125000,
    "currency": "VND",
    "provider_reference": "PROVIDER-522"
  }
}
~~~

Here **amount_minor** is an integer in the smallest currency unit agreed upon alongside the currency code, avoiding binary floating-point rounding errors. For systems supporting multiple currencies, unit conversion rules per currency code must be explicitly defined. The IDs and timestamps in the example are illustrative data only.

**Two types of timestamps to keep separate.** A payment confirmation may occur at 09:15 but be received at 09:17 due to network latency. If a report groups by when the business event happened, use **occurred_at** according to authoritative-source rules; if reporting synchronization lag, use the difference between **recorded_at** and **occurred_at** with caution regarding clock drift. Do not use timestamps to replace logical order in the event stream.

## 5. From Events to State: Rules for Applying Events

Current state is the result of a function that applies events sequentially in a deterministic order:

~~~text
state = initial_state
for event in events_of_order_sorted_by_sequence_no:
    state = apply(state, interpret_event_version(event))
return state
~~~

With the ORD-731 example, a state model may include **order_status**, **payment_status**, **total_minor**, **currency**, **captured_minor**, and **refunded_minor**. Illustrative progression:

| Event | order_status | payment_status | captured_minor | refunded_minor |
| --- | --- | --- | ---: | ---: |
| OrderPlaced | PLACED | UNPAID | 0 | 0 |
| PaymentCaptured | PLACED | PAID | 125000 | 0 |
| OrderCancelled | CANCELLED | PAID | 125000 | 0 |
| RefundIssued | CANCELLED | REFUNDED | 125000 | 125000 |

The **apply** function must have deterministic semantics: the same initial state and the same valid sequence of events must produce the same result. During replay, avoid depending on “current wall-clock time”, calling external APIs, or generating random numbers not present in the event data. If a value determines state, the event or versioned reference data must contain sufficient information to reconstruct it.

**Checking invariants before accepting an event:**

| Invariant | Example enforcement |
| --- | --- |
| An order can only be initialized once. | Reject a second **OrderPlaced** on the same aggregate. |
| Do not record the same payment capture twice. | Check **payment_id** and **idempotency_key** within the appropriate scope. |
| Refunded amount must not exceed captured amount. | Total **refunded_minor** after the event must be less than or equal to **captured_minor**. |
| Do not transition state against the workflow. | After shipment, a cancellation request may have to become a return workflow. |
| Progression version must not be overwritten by concurrent updates. | Use row locking or optimistic concurrency control on the aggregate. |

An event log by itself **does not guarantee** these invariants. The command-handling system must validate business conditions and append the event inside a transaction with concurrency control. For rules spanning multiple aggregates or services, design appropriate process orchestration, compensation, and consistency boundaries; do not assume a local transaction keeps every system synchronized.

## 6. Mapping to a Relational Schema

Events are a logical modeling style; a dedicated database engine is not mandatory. In PostgreSQL, events can be stored in a relational table with a JSONB payload. Below is an illustrative design for **a single Order aggregate type**, combining strictly constrained fixed columns with a payload that varies by event type.

~~~sql
CREATE TABLE order_stream (
    order_id       VARCHAR(64) PRIMARY KEY,
    last_sequence  BIGINT NOT NULL DEFAULT 0
                   CHECK (last_sequence >= 0)
);

CREATE TABLE order_event (
    event_id         UUID PRIMARY KEY,
    order_id         VARCHAR(64) NOT NULL
                     REFERENCES order_stream(order_id),
    sequence_no      BIGINT NOT NULL CHECK (sequence_no > 0),
    event_type       VARCHAR(80) NOT NULL,
    event_version    SMALLINT NOT NULL CHECK (event_version > 0),
    occurred_at      TIMESTAMPTZ NOT NULL,
    recorded_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    producer         VARCHAR(80) NOT NULL,
    idempotency_key  VARCHAR(160),
    correlation_id   UUID,
    causation_id     UUID,
    payload          JSONB NOT NULL
                     CHECK (jsonb_typeof(payload) = 'object'),
    UNIQUE (order_id, sequence_no)
);

CREATE UNIQUE INDEX ux_order_event_idempotency
    ON order_event (producer, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

CREATE INDEX ix_order_event_type_occurred
    ON order_event (event_type, occurred_at);
~~~

**Role of keys and indexes:**

- **event_id** ensures each event has a distinct identifier; **UNIQUE(order_id, sequence_no)** prevents two events at the same position in a stream.
- **order_stream.last_sequence** can be locked when appending events to serialize updates on the same order. If using optimistic concurrency control, the write must succeed only if the expected version still matches.
- The **(producer, idempotency_key)** index prevents a request with the same key from being recorded twice; the application must return the previous outcome or handle the conflict properly. This key must be bound to stable command content, avoiding reuse across two different requests.
- The **(event_type, occurred_at)** index is only useful when querying by event type and time range frequently enough. Verify with actual queries, data volume, and execution plans before adding many indexes.
- The **CHECK** constraint on JSONB only verifies that the payload is a JSON object; it **does not** validate structure by **event_type** and **event_version**. Schema validation must be added at the application layer or an equivalent validation mechanism.

An event-appending transaction can follow this sequence:

1. Begin transaction; ensure the **order_stream** row for the order exists, then lock that row with **SELECT ... FOR UPDATE**.
2. Check idempotency; read the state or required events and evaluate the command's business rules.
3. If valid, insert the event with **sequence_no = last_sequence + 1**; update **last_sequence** accordingly.
4. If updating a synchronous projection or outbox in the same database, perform it inside the transaction; **COMMIT** when all required writes succeed. If an error occurs, **ROLLBACK** everything.

Locking the existing row prevents two commands from writing to the same position. For a new order, creating the **order_stream** row must be protected by the primary key and concurrent-creation conflict handling. When receiving a duplicate command with the same idempotency key, read the prior result instead of incrementing the sequence and creating a new event.

For fast queries on current state, an additional projection can be stored:

~~~sql
CREATE TABLE order_current (
    order_id        VARCHAR(64) PRIMARY KEY,
    order_status    VARCHAR(24) NOT NULL,
    payment_status  VARCHAR(24) NOT NULL,
    total_minor     BIGINT NOT NULL CHECK (total_minor >= 0),
    currency        CHAR(3) NOT NULL,
    captured_minor  BIGINT NOT NULL DEFAULT 0
                    CHECK (captured_minor >= 0),
    refunded_minor  BIGINT NOT NULL DEFAULT 0
                    CHECK (refunded_minor >= 0),
    last_sequence   BIGINT NOT NULL CHECK (last_sequence > 0),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (refunded_minor <= captured_minor)
);
~~~

This is a **derived table**, not an independent source of truth in an event sourcing design. If the business only needs current state, the state table can serve as the source of truth while selectively storing events for history. The decision depends on auditability, traceability, rebuild requirements, and acceptable operational complexity.

## 7. Querying History and Rebuilding Read Models

With event data, the question “which orders were cancelled **after** payment capture?” becomes an order comparison:

~~~sql
SELECT DISTINCT c.order_id
FROM order_event AS c
JOIN order_event AS p
  ON p.order_id = c.order_id
WHERE c.event_type = 'OrderCancelled'
  AND p.event_type = 'PaymentCaptured'
  AND p.sequence_no < c.sequence_no;
~~~

The illustrative query assumes an order's events reside in a single stream and **sequence_no** represents accepted business order. It answers “whether a payment capture ever occurred before a cancellation”, **not** automatically proving the remaining refundable balance or the validity of every transition. Those conclusions require corresponding rules and events.

To rebuild a projection from scratch, read each stream by **sequence_no**, convert event versions if necessary, and apply the **apply** function. Multiple projections can be built from the same source: a current-state table for display, a stage-duration processing table, or an analytics table measuring post-payment cancellation rates.

When projections are updated asynchronously, three situations must be handled explicitly:

- **Duplicate events:** if **sequence_no** has already been applied, ignore it or acknowledge the prior result; do not add money twice.
- **Missing or out-of-order events:** if the next event has **sequence_no** greater than **last_sequence + 1**, pause that stream and fetch the missing gap before applying.
- **Projection lag:** readers may observe stale state for a period of time. When the business requires immediate feedback right after a command, update the projection in the same transaction or read from a source with appropriate consistency guarantees.

For long streams, a **snapshot** stores state at a specific sequence number to replay from a closer checkpoint. A snapshot is rebuildable derived data; it does not replace events and should not become a place to hide gaps in event history.

## 8. Hard Problems When Putting Into Production

### Concurrent Updates and Deduplication

Two tasks may concurrently read the state “not cancelled” and both request cancellation. If both pick the same **sequence_no**, one operation must be blocked and re-evaluated; otherwise, the history will be corrupted. Aggregate locking, expected-version comparison, and unique constraints are common mechanisms. Deduplication is needed at both **command ingress** and **event consumers**, because many messaging systems provide at-least-once delivery.

### Writing Data and Publishing Messages

If you save an event to the database and then publish directly to a broker, the system can fail between the two steps: saved but not published, or published while the database transaction rolled back. A **transactional outbox** stores the record to be published in the **same transaction** as the event or source change; a separate publisher relays the message and can retry. Consumers still need idempotent handling. Outbox solves reliable message delivery; it does not by itself turn a state-table system into event sourcing.

### Event Schema Evolution

Recorded events can outlive the current version of the codebase. When changing **PaymentCaptured** from version 1 to 2, keep **event_version**, define rules to read old versions (such as an **upcaster** transforming old representations into the canonical form in memory), and test replay against historical data. Never silently change the meaning of the same event name; if the business meaning genuinely changes, consider a new event type.

### Late-Arriving Events and Correcting History

An event from an external system may carry an older **occurred_at** while being recorded after other events. The system must specify whether it alters state according to **stream insertion order**, or requires a deliberate business adjustment workflow. Do not simply re-sort already committed events by timestamp. When an event was recorded in error, typically create a business-meaningful **adjustment/compensation** event rather than silently mutating old payloads; exceptions for modifying or deleting data must follow policy and legal requirements.

### Storage, Privacy, and Operations

Storing history increases storage footprint, index overhead, recovery complexity, and projection monitoring effort. Minimize personal data inside payloads; consider referencing a sensitive-data store with separate deletion and anonymization policies. “Append-only” is a design principle to avoid overwriting business facts, **not** an excuse to ignore retention periods, data-deletion requests, or security regulations. Protect write privileges to prevent arbitrary UPDATE/DELETE, enforce access control, and maintain compliant change-handling procedures.

## 9. Comparing History Modeling Approaches

| Approach | Source of truth | Best suited when | Trade-offs |
| --- | --- | --- | --- |
| **Store current state only** | Latest state record. | Primarily CRUD and current-state queries. | Progression history is lost without another history source. |
| **State + selective business log** | State remains the source of truth. | Need to inspect certain historical milestones without reconstructing full state. | Must clearly define which cases the log covers and ensure consistent writes. |
| **Event sourcing + projections** | Event stream is the source of truth. | Progression history, replay, root-cause analysis, and multiple data views are core requirements. | Increases complexity in schema evolution, versioning, synchronization, deduplication, and operations. |

Do not conflate concepts that frequently appear together:

- **Audit log** typically records who acted, when, and before/after values to inspect changes; it does not necessarily carry enough semantic information to reconstruct state.
- **Change Data Capture (CDC)** captures row/column-level changes from the database; updating a **status** column does not by itself express the business reason equivalent to **OrderCancelled**.
- **Integration event** is an information contract published to other systems; it may be a filtered or transformed version of a domain event and requires separate compatibility management.
- **CQRS** separates writes from reads; it can be used with or without event sourcing. **Kafka** or a message broker can transport events, but using a broker alone does not automatically create an event store capable of long-term replay.

Event modeling is also not synonymous with any specific database type. Streams can be stored in relational tables, documents with embedded/separate event arrays, or specialized stores; data can then be projected into a **graph** to inspect causal relationships or into an **analytical store** to compute time-series metrics. Choose physical storage based on consistency, query, volume, retention, and operational requirements.

## 10. Design Exercise and Self-Verification

**Scenario:** an equipment rental system currently stores only **rental_status = CLOSED**. Operations wants to know which rentals closed after late return, which staff member confirmed receiving the equipment back, and how long afterward the security deposit was refunded.

Try designing:

1. Events expressing completed actions, such as **RentalStarted**, **ReturnDueDateChanged**, **EquipmentReturned**, **LateFeeAssessed**, **DepositRefunded**. Distinguish “customer submitted a return request” from “equipment was confirmed received back by staff”.
2. A stream on the **Rental** aggregate with logical ordering and deduplication identifiers. Record **occurred_at** and **recorded_at**, along with the appropriate actor for business confirmations.
3. A current-state projection containing rental status, return due date, actual return timestamp, and refunded deposit amount; an analytics projection measuring latency between **EquipmentReturned** and **DepositRefunded**.
4. Invariants: cannot refund more than the remaining deposit, cannot confirm the same return twice, cannot close a contract while a mandatory step remains incomplete.

A model is considered well-verified when it passes the following tests:

- **Replay:** from the same event history and same interpretation version, reconstructs the exact expected state.
- **Deduplication:** resending the same command or same event does not cause amounts or quantities to change again.
- **Concurrency:** two commands modifying the same aggregate concurrently do not produce duplicate sequence numbers or lose events.
- **Validity:** rule-violating transitions are rejected before being recorded as successful events.
- **Compatibility:** new code can still read older event versions; rebuilding projections yields consistent results.
- **Queryability:** the stated historical questions can be answered from actual data, with clearly defined order and timestamps.

**Design takeaway:** storing only final state is sufficient for many simple workflows. When **progression** itself carries business value, model what happened as events with clear semantics, constraints, and ordering. From there, choose the appropriate level of history retention, projection mechanism, and physical model, rather than assuming every system must adopt event sourcing.
