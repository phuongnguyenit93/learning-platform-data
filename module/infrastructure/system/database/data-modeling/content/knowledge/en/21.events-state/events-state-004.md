# Storing Events as the Data Source (Event Sourcing) and Its Applicability Limits

## 1. What Problem Does Event Sourcing Solve?

In traditional data modeling, a system typically stores a record representing the **latest state**. For instance, a `rental_contract` table may show that equipment rental contract `RENT-204` has status `CLOSED` and its deposit has been refunded. These values serve fast lookups, but do not on their own fully explain **what occurrences took place**, in what order they happened, and what led the system to the current state.

**Event sourcing** is an architectural choice in which the sequence of **accepted and durably stored events** becomes the **primary source of truth for an aggregate's state**. Instead of treating the final state as the authoritative record and merely appending auxiliary history, the system reconstructs state by applying events in their logical order.

Expressed concisely in terms of data relationships:

~~~text
Current state = fold(initial state, stored events in exact order)
~~~

Here, `fold` means sequentially applying a state-transition function to each event. A **projection** can materialize the result into a current-state table, search index, or analytical table to serve queries.

Distinguishing three design approaches:

| Design approach | Source of truth | Ability to review progression |
| --- | --- | --- |
| **State-only** | Current-state record, typically updated with `UPDATE`. | Depends on whether history is stored elsewhere. |
| **State + audit/event log** | State record remains authoritative; log is supplemental data. | Can trace some or many changes, but the log is not guaranteed sufficient to rebuild state. |
| **Event sourcing** | The accepted event sequence is the source of truth for the aggregate; state is derived. | Replayable if events, ordering, and interpreters remain complete and compatible. |

**The deciding factor is not having a table named `events`, using Kafka, or storing JSON.** It is **which data the system treats as authoritative when recovering or resolving discrepancies**. If the official state lives in `rental_contract` and the event table is only appended when convenient, the system has not implemented consistent event sourcing.

## 2. Running Example: Completing an Equipment Rental Contract

Suppose the equipment rental service's business requirements demand:

- Knowing when the customer picked up and returned the equipment, and whether the return due date was extended.
- Calculating deposit collected, accrued fees, and deposit refunded.
- Explaining why a contract closed and who/which actor approved inspection acceptance.
- Verifying that refunds never exceed the refundable amount.
- Being able to rebuild contract state if lookup tables are lost or reporting logic changes.

An illustrative **event stream** for the `Rental` aggregate with ID `RENT-204`:

| stream_version | Event | Core business data |
| ---: | --- | --- |
| 1 | `RentalStarted` | Equipment, return due date, deposit amount, and currency. |
| 2 | `DepositCaptured` | Captured amount and payment transaction identifier. |
| 3 | `RentalDueDateExtended` | Old due date, new due date, approved reason. |
| 4 | `EquipmentDroppedOff` | Equipment, drop-off location, and handover receipt. |
| 5 | `EquipmentReturnAccepted` | Inspection result, confirming actor, and timestamp. |
| 6 | `DepositRefunded` | Actual refunded amount and payment provider reference. |
| 7 | `RentalClosed` | Contract closed once all conditions are satisfied. |

From this sequence, the system can compute `rental_status = CLOSED`, final return deadline, deposit collected, deposit refunded, and columns for customer-facing screens. Yet **which events are accepted** must still be governed by business rules; for instance, `DepositRefunded` is emitted only after an authoritative source confirms the refund succeeded, not immediately when staff clicks “Refund deposit”.

This is a **per-contract** stream, so `stream_version = 5` means the fifth accepted event for `RENT-204`. It does not mean the fifth event across the entire database, and it defines no ordering between two different contracts.

### How Is State Reconstructed?

Suppose the computed state consists of:

~~~json
{
  "rental_id": "RENT-204",
  "status": "ACTIVE",
  "deposit_captured_minor": 0,
  "deposit_refunded_minor": 0,
  "due_at": null,
  "returned_at": null
}
~~~

During replay:

- `RentalStarted` sets `status = ACTIVE`, initializes the return due date and equipment details.
- `DepositCaptured` increases `deposit_captured_minor` by the **confirmed** capture amount, not when a capture request is merely submitted.
- `RentalDueDateExtended` updates the effective deadline to the value approved in the event.
- `EquipmentDroppedOff` records the handover timestamp; it does not automatically imply inspection passed.
- `EquipmentReturnAccepted` marks the equipment accepted back after inspection.
- `DepositRefunded` increases the actually refunded amount.
- `RentalClosed` transitions to `CLOSED` when all obligations under contract-closure rules are met.

Multiple statuses such as “active rental”, “equipment returned”, and “deposit refunded” should be modeled as **separate dimensions** when the business has independent steps. A single `status` field easily causes systems to drop financial or operational information.

## 3. Typical Architecture: Commands, Event Streams, and Read Models

~~~mermaid
flowchart TD
    C["Command: AcceptEquipmentReturn"] --> V{"Check invariants & Rental version"}
    V -->|Invalid| R["Reject command"]
    V -->|Valid| E["Append EquipmentReturnAccepted"]
    E --> ES[("Event store - source of truth")]
    ES --> RE["Replay/fold by stream_version"]
    RE --> S["Rental state"]
    ES --> P["Projector / Consumer"]
    P --> RM[("Read model: rental_current")]
    P --> A[("Read model: history and analytics")]
    ES --> O["Outbox / publish required messages"]
    O --> I["Integration events for other services"]
~~~

This is a logical structure; physical implementations may vary. Command handlers typically **load aggregate state** by replaying from events, or from a **valid snapshot + subsequent events**, validate invariants, and then append new events. Read models are built from events to serve queries efficiently.

Key concepts to separate clearly:

| Concept | Responsibility |
| --- | --- |
| **Command** | Request to change state: `AcceptEquipmentReturn`; can be rejected. |
| **Domain event** | Business fact after acceptance: `EquipmentReturnAccepted`. |
| **Aggregate** | Boundary for enforcing invariants and event ordering, e.g., `Rental`. |
| **Event store** | Persists events durably with order and identity to reconstruct state. |
| **Projection/read model** | Derived data serving queries; rebuildable. |
| **Snapshot** | Derived state at a specific stream version to reduce replay cost. |
| **Integration event** | Notification contract for other systems; may be produced from domain events without needing to be identical. |

**CQRS** (separating writes and reads) pairs well with event sourcing, yet the two are independent concepts. A system can use CQRS while keeping state as its source of truth; or use event sourcing with very simple readers. Brokers and CDC are likewise transport/change-capture mechanisms, not replacements for an event store.

## 4. Designing an Event Contract Fit for Long-Term Use

An event in an event store should express an **immutable business fact**. Typically, metadata and payload must suffice to identify:

| Field | Purpose | Caveat |
| --- | --- | --- |
| `event_id` | Unique identifier for a persisted event. | Used for tracing/deduplication on consumption; do not use in place of stream version. |
| `aggregate_type`, `aggregate_id` | Identifies the aggregate's event stream. | Specify tenant scope explicitly if IDs are only unique per tenant. |
| `stream_version` | Logical sequence number of the event in one stream. | Must be unique within the stream; does not imply system-wide order. |
| `event_type` | Name of the business fact. | Avoid technical names like `RowUpdated`. |
| `schema_version` | Structural version of the event type. | Distinct from `stream_version`. |
| `occurred_at` | When the business occurrence happened per confirming source. | May arrive late or reflect source clock skew. |
| `recorded_at` | When the event was persisted in the event store. | Used for lag monitoring; does not replace occurred_at. |
| `payload` | Facts needed to interpret/reconstruct business state. | Avoid referencing mutable data without proper versioning. |
| `correlation_id`, `causation_id` | Links steps in the same flow and immediate cause. | Does not replace aggregate ID or deduplication keys. |

Example `DepositRefunded`:

~~~json
{
  "event_id": "f615cb42-6f42-4b60-a0d5-4e57d45b44fb",
  "aggregate_type": "Rental",
  "aggregate_id": "RENT-204",
  "stream_version": 6,
  "event_type": "DepositRefunded",
  "schema_version": 1,
  "occurred_at": "2026-11-20T05:20:00Z",
  "recorded_at": "2026-11-20T05:20:03Z",
  "correlation_id": "1b21a7ce-a103-4d96-9499-9f8b1edfe286",
  "payload": {
    "refund_id": "REF-706",
    "payment_id": "PAY-903",
    "amount_minor": 400000,
    "currency": "VND",
    "provider_confirmation_id": "GATEWAY-888"
  }
}
~~~

`amount_minor` is an integer in the smallest currency unit defined for the currency code, avoiding binary floating-point errors. IDs and timestamps are illustrative. With multiple currencies, unit conversion rules must follow the corresponding currency code.

**Minimal yet self-contained:** if replay needs the approved amount, the event must contain that figure or a reference to **immutable** versioned data. Storing only `refund_id` and reading current details from a payment service can cause historical replays to yield different results. Conversely, do not embed an entire customer profile into an event when an ID suffices; long-lived personal data increases privacy risk.

## 5. Designing an Event Store in a Relational Database

Event sourcing is a **way of organizing the source of truth**, not the name of a database product. PostgreSQL, a document store, or a specialized event store can all work if they satisfy requirements for consistent writes, per-stream ordering, history reads, querying, and recovery.

The example below uses PostgreSQL. An `event_stream` table tracks the latest version to coordinate writes; `event_store` holds confirmed history. In multi-tenant systems, include tenant in keys and access control if aggregate IDs are unique only within a tenant.

~~~sql
CREATE TABLE event_stream (
    aggregate_type  VARCHAR(80) NOT NULL,
    aggregate_id    VARCHAR(80) NOT NULL,
    current_version BIGINT NOT NULL DEFAULT 0
                    CHECK (current_version >= 0),
    PRIMARY KEY (aggregate_type, aggregate_id)
);

CREATE TABLE event_store (
    event_id        UUID PRIMARY KEY,
    aggregate_type  VARCHAR(80) NOT NULL,
    aggregate_id    VARCHAR(80) NOT NULL,
    stream_version  BIGINT NOT NULL CHECK (stream_version > 0),
    event_type      VARCHAR(100) NOT NULL,
    schema_version  SMALLINT NOT NULL CHECK (schema_version > 0),
    occurred_at     TIMESTAMPTZ NOT NULL,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    correlation_id  UUID,
    causation_id    UUID,
    payload         JSONB NOT NULL
                    CHECK (jsonb_typeof(payload) = 'object'),
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb
                    CHECK (jsonb_typeof(metadata) = 'object'),
    FOREIGN KEY (aggregate_type, aggregate_id)
        REFERENCES event_stream (aggregate_type, aggregate_id),
    UNIQUE (aggregate_type, aggregate_id, stream_version)
);

CREATE INDEX ix_event_store_type_time
    ON event_store (event_type, occurred_at);
~~~

**Constraint explanation:**

- `PRIMARY KEY(event_id)` uniquely identifies events across the store assuming unique ID generation.
- `UNIQUE(aggregate_type, aggregate_id, stream_version)` guarantees two events cannot occupy the same position in a stream. This constraint's index also supports reading in version order.
- `current_version` is updated in the same transaction as new events, after locking the stream or checking the expected version. It detects two commands racing to modify the same aggregate.
- Checking `jsonb_typeof(payload)` is **insufficient** to guarantee a `DepositRefunded` carries a valid amount. Per-`event_type + schema_version` schemas, monetary rules, and invariants must be validated before appending.
- The `(event_type, occurred_at)` index helps when reporting frequently by type and time; it adds write cost. Base adding additional indexes or partitions on workload and `EXPLAIN`.

Reading a stream:

~~~sql
SELECT event_id, stream_version, event_type,
       schema_version, occurred_at, payload
FROM event_store
WHERE aggregate_type = 'Rental'
  AND aggregate_id = 'RENT-204'
ORDER BY stream_version;
~~~

When querying a contract's timeline, `stream_version` defines the logical order accepted by the system. Do not simply `ORDER BY occurred_at`: an event from a partner may arrive late, carry a skewed clock, or have an earlier business timestamp despite entering the stream later.

### Concurrent Writes: One Stream Must Have One Valid Sequence

When two commands both observe `current_version = 4`, both cannot independently succeed at writing “event 5”. Choose row locking or optimistic concurrency:

1. Initialize the `event_stream` row if the aggregate is new; handle concurrent-creation conflicts via the primary key.
2. Inside the transaction, use `SELECT ... FOR UPDATE` to lock the stream row, or `UPDATE ... WHERE current_version = expected_version` and inspect the updated row count.
3. Read the relevant state, validate invariants and authorization to execute the command.
4. Append events with consecutive versions, update `current_version`, and commit atomically.
5. On version conflict, reload state and re-evaluate the command from scratch; never blindly retry an old event while bypassing current conditions.

One command may emit **multiple events**; they must be appended with consecutive `stream_version` values in the same transaction, with `current_version` reflecting the final version of the batch. A unique constraint on version does not replace business validation or command deduplication.

## 6. Command Handling, Idempotency, and Invariants

Suppose a staff member confirms an equipment return; the processing flow can be expressed in pseudocode:

~~~text
handle(AcceptEquipmentReturn command):
    begin transaction
    ensure stream row exists
    lock stream row, read current_version
    check idempotency_key of this command
      if already committed: return previously recorded result

    state = load_snapshot_if_valid()
    state = replay_events_after_snapshot(state)

    check permissions, equipment identity, inspection evidence
    check not_already_accepted(state, equipment_id)
    new_event = EquipmentReturnAccepted(...)

    append new_event at current_version + 1
    update stream current_version
    save idempotency receipt / outbox records as needed
    commit transaction
    return recorded result
~~~

In principle, complete **validation and persistence** inside the same consistency boundary. If a command is retried after a client timeout, the system must not append a duplicate acceptance event simply because the prior response never reached the client.

**Idempotency** usually has two layers:

- **Command idempotency:** persist request keys within a clear scope (`caller_id + idempotency_key` or `tenant_id + operation + key`) along with a payload hash and processing outcome. Same key/same content returns the recorded outcome; same key/different content must raise a conflict. If one command produces multiple events, a dedicated receipt table fits better than a unique constraint on a single event row.
- **Event consumer idempotency:** each projection/consumer tracks which events or `last_version` per stream it has applied so redelivering the same message never double-counts money, attempts, or state transitions.

**Invariants** must remain explicit. For example, total `refunded_minor` cannot exceed total `captured_minor`, an equipment item cannot be accepted twice in the same rental cycle, and a contract cannot close while open obligations remain. Event sourcing does not automatically block invalid events; command-handling logic must prevent them upfront.

The replay function must be **deterministic** for the same inputs. It must not query **current** price lists, call payment APIs, read current system clock time, or emit external notifications. Side effects happen during command handling or in dedicated workflows; replay only transforms in-memory state or builds read models.

## 7. Projections: Leveraging History While Keeping Queries Fast

To display “currently active contracts and remaining refundable amount”, you should not scan the entire history of all contracts on every page load. Create **projections** tailored to read needs.

Example:

~~~sql
CREATE TABLE rental_current (
    rental_id             VARCHAR(80) PRIMARY KEY,
    rental_status         VARCHAR(24) NOT NULL,
    deposit_captured_minor BIGINT NOT NULL DEFAULT 0
                            CHECK (deposit_captured_minor >= 0),
    deposit_refunded_minor BIGINT NOT NULL DEFAULT 0
                            CHECK (deposit_refunded_minor >= 0),
    currency              CHAR(3) NOT NULL,
    last_applied_version  BIGINT NOT NULL DEFAULT 0
                          CHECK (last_applied_version >= 0),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (deposit_refunded_minor <= deposit_captured_minor)
);
~~~

A projector reads events for `RENT-204` in version order, applies the `apply` function, and updates `last_applied_version`. If it receives an already-processed version, it skips it; if it sees version 7 when only version 5 has been applied, it must fetch version 6 before updating. For asynchronous projectors, these updates must execute within the projection-update transaction so progress tracking is never lost.

Characteristics to communicate clearly to data consumers:

- **Latency:** after a command commits an event, asynchronous projections may not have updated yet. Never assume an eventually consistent read model reflects changes immediately.
- **Read-your-writes:** if the UI needs immediate command feedback, return the resulting state/version from the command, wait for the projection to reach the required version within an appropriate timeout, or update critical projections in the same transaction.
- **Query patterns:** you can build one projection for the contract screen, one for late-return rates, and one for deposit analytics. They have different schemas and indexes, yet require clear source and version rules.
- **Rebuilds:** if a projector has a bug, derived tables can be rebuilt from the event store using version-compatible readers. Rebuilds require a cutover plan, catching up on new events, and discrepancy checks; never arbitrarily drop a live production projection.

Also clarify whether a projection is computed from **a single aggregate's** events or multiple aggregates. Cross-aggregate requirements may need dedicated workflows and synchronization; never assume a local aggregate transaction makes all read models instantaneously consistent.

## 8. Snapshots, Replay, and Schema Evolution

### Snapshots Speed Up Reads While Remaining Derived Data

When a contract accumulates thousands of events, rebuilding state from version 1 for every command can become slow. A **snapshot** stores state after applying up to `stream_version = N`; subsequent handlers load the snapshot and replay events from `N + 1`.

~~~text
Snapshot(state@version=500)
    + event(501) + event(502) + ... + event(537)
    => current_state@version=537
~~~

A snapshot needs `aggregate_id`, `stream_version`, snapshot serialization/schema version, and state data. Verify that the snapshot belongs to the right stream, does not exceed the current stream version, and can always be discarded and rebuilt. Snapshots never replace the original event sequence and never fix missing or corrupted events.

### Old Events Must Remain Interpretable

Suppose `DepositRefunded.v1` only contained `amount_minor` and `currency`; version 2 adds `refund_method`. Options include:

1. Continuing to support readers for both `v1` and `v2`.
2. Using an **upcaster** to convert older representations into the canonical structure in memory during replay.
3. Planning a verified migration if historical events genuinely must be transformed.

Never silently change the meaning of `amount_minor` within the same schema version. If “refund” previously meant a request was submitted, and now must mean the bank confirmed it, that is a **semantic change**; it requires a new event or a well-founded conversion rule, not simply bumping a version number and pretending all old events completed.

Changing the `apply` function's code can cause historical replays to yield different results. That is valid only with an explicit business decision and data verification. Test replay on historical streams before deploying upgrades, include edge-case test fixtures, and check consistency between reconstructed state and expected state.

### Correcting History With Adjustment Events

If a fee was miscalculated, the standard approach is to append `RentalFeeCorrected` or `ChargeReversed` under business rules, preserving both the original trail and the corrective action. **Append-only** is a principle against erasing confirmed facts; it does not mean all data may be kept forever, or that erroneous events can never be corrected.

## 9. Limits When Integrating Multiple Services and External Side Effects

An event store can guarantee ordering and atomicity **within a single aggregate/database transaction**, but it does not automatically create distributed transactions across payment, warehouse, and shipping. Deposit refund example:

~~~mermaid
flowchart LR
    R["Rental: approve refund request"] --> O["Outbox: request deposit refund"]
    O --> P["Payment service calls provider"]
    P -->|Confirmed success| E["Payment: RefundConfirmed"]
    E --> I["Integration event"]
    I --> C["Rental records DepositRefunded"]
~~~

This is an illustrative flow. If the payment provider times out, the status may be **unknown outcome**; never emit `DepositRefunded` without evidence. Use a provider-level idempotency key, retry mechanism, and reconciliation before confirming.

For publishing messages after commit, use a **transactional outbox** or equivalent mechanism: write the outbound message record in the same transaction as the source event; a separate relay publishes afterward. The relay may emit duplicates on retry. Consumers must handle duplicates idempotently, because “published successfully once” does not mean “processed once by every consumer”.

Events across different aggregates/services have **no default global order**. Kafka partitions, database offsets, `recorded_at`, and `occurred_at` each apply to their own scope. To coordinate multi-step workflows, design orchestration/choreography, timeouts, compensation, correlation tracking, and latency monitoring. Event sourcing does not eliminate the need for **sagas** or other coordination mechanisms when workflows span multiple services.

## 10. Practical Limits and Costs of Event Sourcing

Event sourcing shines in problems that need **progression as primary data**. Yet it demands many decisions that traditional CRUD can avoid.

| Limit/cost | Common consequence | How to evaluate or mitigate |
| --- | --- | --- |
| **Modeling complexity** | Every change needs event semantics and replay logic. | Select only aggregates whose history genuinely carries business value. |
| **Proliferation of derived data** | Read models, projectors, checkpoints, and caches need monitoring. | Define acceptable lag, rebuild playbooks, and projection-drift checks. |
| **Growing stream length** | Replay from start slows down; storage and index sizes grow. | Snapshots, sensible partitioning/archival, benchmark real replay times. |
| **Long-lived schemas** | New code must read old events; semantic changes are hard. | Version contracts and run replay tests against historical data. |
| **Persisted bad data** | Fixing via compensating events is harder than `UPDATE` on a row. | Enforce invariants, validate inputs, build evidenced correction workflows. |
| **Eventual consistency** | Users may observe stale state on read models. | Define latency SLAs, read-your-writes, show processing state where appropriate. |
| **Security and privacy** | Long-term history may retain sensitive data subject to deletion. | Minimize payloads, encrypt, restrict access, enforce retention, anonymize, or separate PII. |
| **Cross-service communication** | Events do not guarantee completion of external side effects. | Outbox, idempotency, reconciliation, monitoring, compensation. |
| **Hard to query ad hoc** | Event logs are not optimized for arbitrary aggregations. | Design purpose-built projections/analytics; do not use event store as default OLAP. |
| **Incomplete history from migration date** | Legacy systems only have state and cannot “reconstruct” unrecorded events. | Mark initial snapshots/loads clearly; never fabricate past events. |

### Event Sourcing Is Not Automatically a “Time Machine”

Replaying up to version 20 shows state **reconstructed under current interpretation for the first 20 events**, assuming code and reference data stayed compatible. It does not inherently tell you every real-world fact at a calendar date, or “what the system knew” at that moment.

When you need both **when a fact took effect** and **when the system learned/recorded it**, model separate timestamps (`effective_at`, `occurred_at`, `recorded_at`) and evaluate bitemporal requirements if the business needs them. A late-arriving event with an earlier `occurred_at` but a later `stream_version` should not be arbitrarily spliced back into confirmed history.

### Right to Erasure and Limits of Append-Only

Never use “immutable log” as an excuse to bypass data deletion policies, retention limits, or legal mandates. Depending on the domain, separate personal data from events (storing only reference IDs), apply subject-scoped encryption, enforce access control, and implement key destruction or authorized erasure workflows. Evaluate these options for feasibility, replayability, and specific legal obligations; no single trick fits every system.

## 11. When Should You Use Event Sourcing, and When Should You Not?

### Signals in Favor

Event sourcing may be worth considering when **several of the following requirements are central**, and operational costs are acceptable:

- The business needs to explain **chains of decisions** and state transitions (finance, business audit, contracts, complex workflows).
- Multiple data views must be rebuilt from the same semantic history, such as period balances, permission progression, or step durations.
- Projections must be recomputed when fixing logic bugs, and event schemas can be preserved long enough to replay.
- Consistency rules align with well-defined aggregate boundaries, and the team can design commands, events, versioning, and idempotency.
- Business traceability outweighs CRUD simplicity, and monitoring/recovery plans are in place.

### Signals Against Broad Adoption

Simple catalog management, UI configuration, or frequently updated data that does not need progression history rarely justifies event sourcing's cost. If you only need a report of who edited which field, **state + audit log** may suffice. If the goal is replicating tables to an analytics warehouse, **CDC** may fit better. If the goal is notifying downstream services upon completion, **integration events + outbox** can work without converting the source of truth into an event store.

| Decision question | If the answer is “Yes” | If the answer is “No” |
| --- | --- | --- |
| Must exact state be reconstructed from progression? | Consider event streams as the source of truth. | Current state + selective history may suffice. |
| Do events carry semantics agreed upon by domain stakeholders? | Strong foundation for defining event contracts. | Clarify business semantics first; avoid turning every update into a vague event. |
| Do you have capacity to manage versioning, replay, projections, and operations? | Trial within a narrowly scoped aggregate. | Reduce scope or pick a simpler approach. |
| Can privacy and history retention be handled compliantly? | Build storage policies alongside the design. | Avoid immutable long-term history without a clear solution. |
| Does the value of history outweigh the added complexity? | Event sourcing may be a good fit. | Favor direct state/relational modeling. |

**Pragmatic strategy:** you can apply event sourcing to **a single bounded context or aggregate**, such as a transaction ledger or contract lifecycle, while keeping the rest CRUD. What matters is clearly defining source-of-truth boundaries, data exchange contracts, and consistency guarantees between them—not forcing one storage style across the entire system.

## 12. Design Exercise and Verification Criteria

**Scenario:** an event ticketing system stores each order with `booking_status`. Users can reserve seats, pay, cancel, and receive refunds; payment gateway timeouts and duplicate callbacks can happen. Operations needs to explain each booking's history, actual captured/refunded amounts, and rebuild reports when metric definitions change.

Perform the following:

1. Identify aggregates (e.g., `Booking` and `Payment` may belong to different bounded contexts). State **invariants**: never confirm seats beyond capacity, never refund more than captured, never process the same callback twice.
2. Propose completed events such as `SeatsReserved`, `PaymentCaptured`, `BookingCancelled`, `RefundConfirmed`. Distinguish `CapturePaymentRequested` from `PaymentCaptured`.
3. Design a JSON envelope including `event_id`, `aggregate_id`, `stream_version`, `event_type`, `schema_version`, `occurred_at`, `recorded_at`, and a payload sufficient to interpret ticket prices/currency under a versioned policy.
4. Describe the expected-version append transaction, callback idempotency handling, and outbox publishing integration events to the notification service.
5. Define at least two projections: a booking-status table for UI screens and an analytics table for post-payment cancellation rates. Specify keys, indexes, and acceptable update lag.
6. Explain how to rebuild projections from the event stream and snapshots; describe how to read an old event after schema evolution.
7. Propose a **non-event-sourcing alternative** (`bookings` + audit log + outbox) and demonstrate which requirements it satisfies and which it falls short on.

**Self-assessment checklist:**

| Test | Expected result |
| --- | --- |
| **Replay** | Same events + same interpretation rules produce identical state; no side effects emitted. |
| **Concurrent commands** | Never two events at the same stream version; failed commands are re-evaluated. |
| **Idempotency** | Duplicate callbacks never capture/refund twice and never double-count projections. |
| **Source-of-truth separation** | Clearly distinguishes event store, projections, outbox, and external service data. |
| **Backward compatibility** | New readers still understand events written under older schema versions. |
| **Recovery** | Read models can be rebuilt with proper checkpoints and reconciled against expected results. |
| **Data protection** | Payloads, access control, and retention align with business and compliance needs. |
| **Cost/value** | Clear justification for choosing event sourcing over state + audit/outbox. |

Storing events as the data source is a **modeling decision**: choosing to capture what happened as primary data and derive state and required views from it. Its value lies in semantic history, replayability, and read-model flexibility; its limits lie in complexity, consistency coordination, schema evolution, operations, and data governance. Apply it only when those benefits directly solve business requirements and can be rigorously verified.
