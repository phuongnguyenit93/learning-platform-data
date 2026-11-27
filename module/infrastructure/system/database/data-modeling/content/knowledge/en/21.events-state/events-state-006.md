# Immutable Events, Corrections, and Compensating Actions

## 1. Why Does an Immutable Event Store Still Need a Correction Mechanism?

In an event model, a record like **PaymentCaptured** or **EquipmentReturned** typically represents an occurrence accepted by the system. When those records serve as the data source for reconstructing state, silently editing or deleting them causes the same history to yield different interpretations, breaking reconciliation against previously emitted notifications, reports, or decisions.

Yet the business world is imperfect. Staff may enter the wrong return due date, sensors may emit faulty readings, a policy may be applied erroneously, or an external transaction actually executed and now must be reversed. Data design must satisfy two requirements simultaneously:

- **Preserve the trail** of what the system recorded and used to make decisions.
- **Allow progression toward the right state** through confirmed correction events and compensating actions with clear authority, evidence, and timestamps.

Suppose an equipment rental system records:

| Order | Event | Meaning at the time recorded |
| ---: | --- | --- |
| 1 | **RentalStarted** | Contract begins, due back at 10:00. |
| 2 | **EquipmentDroppedOff** | Kiosk receives equipment at 10:30. |
| 3 | **LateFeeAssessed** | System assesses a 100,000 VND late fee. |
| 4 | **RentalDueDateCorrectionApproved** | Manager confirms the correct due time was 11:00, based on an extension record. |
| 5 | **LateFeeAssessmentReversed** | The 100,000 VND fee is reversed/waived per the new decision. |

The final state is **no remaining late fee owed**. Yet event 3 remains meaningful: the system once assessed the fee and may have notified the customer. Deleting event 3 erases the cause of the fee reversal in event 5. If the fee was already collected in cash or electronically, an **actual refund** workflow and corresponding confirmation event are also required.

**Core question of this lesson:** when old data is wrong or a business outcome must be undone, should we **correct information**, **record a new business progression**, or **execute a compensating action**? The decision must come from business semantics, not merely from the database's ability to run UPDATE/DELETE.

## 2. Understanding Event Immutability Properly

In event sourcing, the sequence of accepted events is typically designed around an **append-only** principle: every new change is recorded as a new event, and prior events are not arbitrarily modified. This immutability enables:

1. **Replay:** re-applying events in order to reconstruct state.
2. **Traceability:** explaining why state transitioned from A to B.
3. **Reconciliation:** comparing data with published messages, approved decisions, and external receipts.
4. **Projection rebuilds:** fixing bugs in aggregation logic while retaining necessary historical data.
5. **Temporal analytics:** measuring processing times, adjustment rates, compensation causes, and operational metrics.

However, **the scope of immutability** must be stated clearly. An event record may be the source of truth for *the fact that the system recorded/decided something*, while the facts inside it may later prove not to reflect reality. Therefore:

- **Record immutability** does not mean **every fact inside the record is permanently true**.
- **Historical fact of a decision** differs from **the fact after correction**.
- **Application-layer append-only** does not by itself guard against administrator edits, storage corruption, or direct privileged access.
- **Technical immutability** does not authorize retaining all personal data indefinitely. Retention, deletion, anonymization, and access regulations still apply.

For instance, **FeeAssessed** can be the fact “the system applied this fee” even when applied in error. **FeeAssessmentReversed** creates a valid progression so no receivable remains. Conversely, if an event's bytes were corrupted on disk, that is a **data integrity incident**, not something to treat as if the customer just executed a compensating transaction.

## 3. Distinguishing Three Kinds of Change: Correcting Facts, Reversing Decisions, and Compensating Effects

These three activities are closely related yet not identical:

| Situation | What must be recorded | Example | Expected outcome |
| --- | --- | --- | --- |
| **Source information is re-verified** | **Correction event** stating the correct value, evidence source, effective time. | **RentalDueDateCorrectionApproved** corrects due time from 10:00 to 11:00. | Projections interpret the due time using the new info while retaining edit history. |
| **A recorded business decision must be invalidated/adjusted** | **Reversal/adjustment event** referencing the prior decision and stating amount or scope adjusted. | **LateFeeAssessmentReversed** cancels the assessed late fee. | Effective financial obligation is recalculated. |
| **A real-world side effect occurred and needs an opposite action** | **Compensating action** executes; upon confirmation, emit an outcome event. | Payment provider captured 100,000 VND; execute refund and record **RefundConfirmed**. | Actual cash flow is adjusted with its own receipt. |

A business event like **OrderCancelled** only expresses that the order status is cancelled. It does not prove money has been refunded, a parcel has returned to the warehouse, or an email has been recalled. Those effects have their own preconditions, owners, and evidence.

### Correcting Data Does Not Mean Erasing the Trail

If staff entered the wrong due date and subsequent decisions depended on it, **DueDateCorrected** should capture old value, new value, reason, and evidence. Avoid simply updating the current `due_at` column while ignoring that earlier reports, penalties, and notifications relied on the wrong value.

### Compensation Does Not Necessarily “Rewind” the World

In distributed workflows, **compensation** is a business action that handles the consequences of an already-succeeded step when the overall workflow runs into trouble. It does not guarantee restoring the world to its initial state in a mathematical sense.

Examples:

- You can **refund captured funds**, yet both the capture and refund transactions still exist; provider processing fees may not be refunded.
- You can **issue a return pickup for delivered goods**, yet you cannot pretend shipping never happened.
- You can **send a correction email**, yet you cannot guarantee the recipient did not read the first email.
- You can **release a held seat**, yet the period the seat was locked may still have affected user experience.

Name events after actual outcomes: **RefundRequested**, **RefundApproved**, **RefundConfirmed**, and **RefundFailed** are distinct milestones. Avoid recording **RefundConfirmed** the moment you call the refund API.

## 4. Designing a Correction Event as a Business Contract

An adjustment event must be explicit enough for future readers to determine **what was corrected**, **to what extent**, **who had authority**, and **from when it applies**.

Commonly required information groups:

| Group | Example fields | Reason |
| --- | --- | --- |
| Event identity | `event_id`, `event_type`, `schema_version` | Distinguish the event and parse its structure accurately. |
| Subject and order | `tenant_id`, `aggregate_type`, `aggregate_id`, `stream_version` | Bind the adjustment to the stream and accepted ordering. |
| Adjustment reference | `corrects_event_id`, `reverses_event_id`, or decision/receipt ID | Identify exactly which event or obligation is affected. |
| Accepted data | `old_due_at`, `new_due_at`, `reversed_amount_minor`, `currency` | Enables deterministic application and value reconciliation. |
| Reason and evidence | `reason_code`, `evidence_id`, `policy_version` | Avoid an unverifiable free-text reason field. |
| Decision maker | `actor_type`, `actor_id`, `approved_by` | Trace authority; do not confuse requester with approver. |
| Timestamps | `occurred_at`, `recorded_at`, `effective_at` | Separate approval time, persistence time, and effective time. |
| Workflow correlation | `correlation_id`, `causation_id`, `idempotency_key` | Link workflow steps and prevent duplicate submissions. |

Illustrative JSON payload:

~~~json
{
  "event_id": "4e2c0ccf-805a-4ee4-9487-13094ba5c21d",
  "event_type": "RentalDueDateCorrectionApproved",
  "schema_version": 1,
  "tenant_id": "t-hcm",
  "aggregate_type": "Rental",
  "aggregate_id": "RENT-204",
  "stream_version": 4,
  "occurred_at": "2026-11-20T05:00:00Z",
  "recorded_at": "2026-11-20T05:00:02Z",
  "effective_at": "2026-11-19T10:00:00Z",
  "actor": {
    "type": "STAFF",
    "id": "MGR-18"
  },
  "payload": {
    "old_due_at": "2026-11-20T03:00:00Z",
    "new_due_at": "2026-11-20T04:00:00Z",
    "reason_code": "APPROVED_EXTENSION_OMITTED",
    "evidence_id": "EXT-559",
    "corrects_business_fact": "rental_due_at"
  }
}
~~~

Here `occurred_at` is when **the manager approved the correction**, `recorded_at` is when the event was stored, and `effective_at` is when **the earlier extension decision should have taken effect** according to the evidence. These three values carry different semantics. IDs and timestamps are illustrative.

Retroactive corrections **should not rewrite stream order**: the version 4 event is still appended at position 4, even if its `effective_at` predates earlier events. If you only want to reconstruct state by recording order, replay by `stream_version`; if you need history of “what was effective at time X” or “what did the system know at time Y”, define explicit temporal query rules.

### What Must Be Checked Before Accepting a Correction?

1. **Source/basis:** does valid evidence or policy authorize the correction?
2. **Authorization:** does the actor have permission to modify this fact and magnitude?
3. **Target:** does the referenced contract, event, or decision ID exist and lie within allowed scope?
4. **Current state:** has the correction already been applied or superseded by another correction?
5. **Downstream effects:** does fixing the due date require recalculating fees or other metrics? Do those adjustments need their own events?
6. **Consistency:** is the command based on the latest aggregate version and protected by an idempotency key?

Define an explicit policy when **an event is corrected multiple times**. For example, allow a subsequent correction only if it references the currently effective decision version, or use a multi-step correction approval workflow with explicit states.

## 5. Designing Dedicated Compensating Events and External Outcome Events

Suppose a payment gateway executed **two independent capture transactions** for the same obligation. The two transactions carry distinct real confirmation codes: `CAP-201` and `CAP-202`. These are two real occurrences at the payment provider, even though the second transaction was unintended.

Do not delete the second **PaymentCaptured** from history, because money was actually collected. A better flow:

~~~mermaid
flowchart TD
    A["PaymentCaptured: CAP-201"] --> B["PaymentCaptured: CAP-202"]
    B --> C["Detect over-collection; inspect and approve"]
    C --> D["RefundRequested: compensate CAP-202"]
    D --> E{"Payment provider returns result"}
    E -->|"Refund confirmed"| F["RefundConfirmed"]
    E -->|"Explicit failure"| G["RefundFailed / handle per policy"]
    E -->|"Unknown outcome"| H["Reconcile, do not emit success"]
~~~

Each step carries distinct meaning:

- **PaymentCaptured**: reflects that a trusted source confirmed payment capture. For duplicate callbacks of the **same** transaction, deduplicate rather than creating a second capture event.
- **RefundRequested**: a refund request was created for the excess capture; no proof yet that funds were returned.
- **RefundConfirmed**: the payment provider confirmed a refund with clear identifier and amount.
- **RefundFailed**: the refund request failed per known outcome; a new action may be needed after review.
- **Pending/unknown**: a timeout or network error is neither proof of failure nor success; query status/reconcile before deciding.

If the provider captured 2 × 100,000 VND and confirmed refunding 100,000 VND for the second transaction, **gross captured** is 200,000 VND, **total refunded** is 100,000 VND, and **net cash flow** is 100,000 VND. History still shows all three real monetary movements.

In a billing system, you may need both **reversing a receivable** in the accounting model and **refunding captured funds**. The two have different effects: reversing an obligation in the ledger does not execute a bank transaction on its own.

### Minimum Contract for a Confirmed Refund Event

~~~json
{
  "event_id": "5fd039dc-57b3-43bf-91f2-14e8be88ff8c",
  "event_type": "RefundConfirmed",
  "schema_version": 1,
  "aggregate_type": "Payment",
  "aggregate_id": "PAY-992",
  "stream_version": 5,
  "occurred_at": "2026-11-20T06:30:00Z",
  "recorded_at": "2026-11-20T06:30:03Z",
  "payload": {
    "refund_id": "REF-778",
    "compensates_capture_id": "CAP-202",
    "amount_minor": 100000,
    "currency": "VND",
    "provider_confirmation_id": "GW-REF-559"
  }
}
~~~

`amount_minor` is an integer in the **smallest currency unit** of the stated currency. Never use binary floating-point numbers for money. `refund_id` and `provider_confirmation_id` must be deduplicated within the respective provider's scope; `compensates_capture_id` identifies the specific capture being compensated.

If obligations live in an **Invoice** aggregate while actual transactions live in **Payment**, define transaction boundaries and integration messages between the two sources. Never assume a transaction in Payment's event store automatically updates all read models of Invoice.

## 6. Complete Example: From Wrong Late Fee to Correct Balance

Revisit rental contract `RENT-204`:

- Initially entered due time: 10:00, though a valid extension record allowed until 11:00.
- Customer handed over the equipment at 10:30.
- System assessed a 100,000 VND late fee using the old due time.
- After review, the manager accepts the correct date/time and waives the late-fee obligation.
- If the fee was already paid, the system must refund the corresponding amount and confirm the outcome.

Example history:

| Version | Event | Interpreted business state |
| ---: | --- | --- |
| 1 | **RentalStarted** | Due time is recorded as 10:00. |
| 2 | **EquipmentDroppedOff** | Records actual handover at 10:30. |
| 3 | **LateFeeAssessed** | Creates a 100,000 VND receivable. |
| 4 | **RentalDueDateCorrectionApproved** | Correct due time is recognized as 11:00. |
| 5 | **LateFeeAssessmentReversed** | Reverses the 100,000 VND receivable from event 3. |
| 6* | **RefundConfirmed** | Present only if payment was captured and an actual refund later completed. |

*Event 6 is a conditional branch. If no money was collected, do not invent a fictional refund event. If refunds are managed in a separate Payment aggregate, it carries a **Payment stream version**, not necessarily version 6 in Rental. Rental's read model can ingest that information via integration events under defined consistency rules.*

### Distinguishing Ledger Balances From Cash Flow

Suppose a projection tracks four same-currency quantities:

| Metric | Calculation | After fee reversal, unpaid | After capturing 100,000 then refunding 100,000 |
| --- | --- | ---: | ---: |
| Gross fees assessed | Sum of **LateFeeAssessed** | 100,000 | 100,000 |
| Fees reversed | Sum of **LateFeeAssessmentReversed** | 100,000 | 100,000 |
| Net effective fee | Gross fees assessed − fees reversed | 0 | 0 |
| Net cash received | Total confirmed captures − total confirmed refunds | 0 | 0 |

Metrics such as “fees assessed in error” and “transactions requiring compensation” retain managerial value; overwriting the fee to 0 without storing corrections/reversals makes both questions hard to answer reliably.

**Never mix the two monetary axes:**

- **Obligations/receivables** are governed by policy; fee reversals change obligations.
- **Actual cash flow** is confirmed by the payment provider or authoritative ledger; refunds change cash flow.

While waiting for a refund, the two axes can temporarily differ. That very difference surfaces items needing reconciliation.

## 7. Relational Schema: Tracking Adjustment Trails and Referential Links

An event store can be implemented in PostgreSQL with stream/version locks alongside fields supporting correction/compensation verification. This is an **illustrative schema** to adapt per aggregate type and tenant policy.

~~~sql
CREATE TABLE event_stream (
    tenant_id        UUID NOT NULL,
    aggregate_type   VARCHAR(80) NOT NULL,
    aggregate_id     VARCHAR(100) NOT NULL,
    current_version  BIGINT NOT NULL DEFAULT 0
                     CHECK (current_version >= 0),
    PRIMARY KEY (tenant_id, aggregate_type, aggregate_id)
);

CREATE TABLE domain_event (
    event_id            UUID PRIMARY KEY,
    tenant_id           UUID NOT NULL,
    aggregate_type      VARCHAR(80) NOT NULL,
    aggregate_id        VARCHAR(100) NOT NULL,
    stream_version      BIGINT NOT NULL CHECK (stream_version > 0),
    event_type          VARCHAR(120) NOT NULL,
    schema_version      SMALLINT NOT NULL CHECK (schema_version > 0),
    occurred_at         TIMESTAMPTZ NOT NULL,
    recorded_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    effective_at        TIMESTAMPTZ,
    actor_type          VARCHAR(40) NOT NULL,
    actor_id            VARCHAR(100),
    reason_code         VARCHAR(80),
    evidence_id         VARCHAR(160),
    corrects_event_id   UUID REFERENCES domain_event(event_id),
    compensates_event_id UUID REFERENCES domain_event(event_id),
    payload             JSONB NOT NULL
                        CHECK (jsonb_typeof(payload) = 'object'),
    FOREIGN KEY (tenant_id, aggregate_type, aggregate_id)
        REFERENCES event_stream(tenant_id, aggregate_type, aggregate_id),
    UNIQUE (tenant_id, aggregate_type, aggregate_id, stream_version)
);

CREATE INDEX ix_domain_event_type_recorded
    ON domain_event (event_type, recorded_at);

CREATE INDEX ix_domain_event_corrects
    ON domain_event (corrects_event_id)
    WHERE corrects_event_id IS NOT NULL;
~~~

### What Does Each Constraint Protect?

- **Unique `event_id`**: identifies a single event write, preventing two records with the same ID.
- **`UNIQUE(tenant_id, aggregate_type, aggregate_id, stream_version)`**: protects each stream's ordering. Contiguous version increments still must be enforced by the append operation inside a transaction.
- **`corrects_event_id` and `compensates_event_id`**: allow direct tracing of the corrected/compensated event. A foreign key only guarantees the referenced event exists; it **does not** prove same tenant, valid event type, valid authority, valid amount, or single reversal.
- **`reason_code`, `evidence_id`, `actor_type`**: connect to policy and proof; the system must still verify actor permissions and evidence validity.
- **`payload`**: holds data per event type/version contract. The JSON constraint here does not validate specific schemas.
- **Indexes**: serve queries by type/timestamp and lookups of an event's adjustment history. Measure workload before adding too many indexes that raise append cost.

In multi-tenant systems, a global `event_id` reference does not automatically enforce same-tenant integrity; the write layer must check it or use composite foreign keys if policy requires. If a correction belongs to another stream and the event lives in another store, use business/correlation references instead of a local foreign key.

### A Correction Command Must Commit Atomically

Recommended workflow:

1. Receive command `CorrectRentalDueDate` with `idempotency_key`, evidence, requester, and expected aggregate version.
2. Begin transaction; lock the stream or check version via optimistic concurrency.
3. Load **latest** state; verify the target event/value being adjusted, permissions, evidence, and that the correction has not already been processed.
4. Determine which events to record: e.g., **RentalDueDateCorrectionApproved** and **LateFeeAssessmentReversed**.
5. Append events with consecutive `stream_version` values; update `current_version`; save deduplication receipt and required outbox rows **in the same transaction**.
6. Commit; return recorded outcome. If an external refund is needed, run that asynchronously with its own deduplication key, then ingest confirmation to record the refund event.

If one command produces two events, **do not put a unique constraint on command ID on each event row**, because it would block the second row. Instead, use a command receipt keyed by a unique request key storing the created event/version range; consumers use event IDs for deduplication.

### Permission to Update Records Is Not Permission to Append

In an append-only design, the event-writing application role should be granted **INSERT** through a controlled write path and restricted from direct **UPDATE/DELETE** on accepted events. Still, database privileges alone cannot enforce all invariants; combine transactions, privilege governance, access logs, verified backups/restores, and sensitive-data policies.

If persisted data must be corrected or erased for safety, legal, or system-bug reasons, follow a separate governed administrative procedure with documentation and impact assessment across replay, projections, and downstream consumers. Never casually disguise an infrastructure exception as a fake “business action”.

## 8. Replay and Projections: Fixing State Without Mutating History

In event sourcing, read models can be computed from the version-ordered event sequence:

~~~text
state = initial_state
for event in events_of_stream_ordered_by_stream_version:
    state = apply(state, upcast_if_required(event))
return state
~~~

The `apply` function must be **deterministic**: identical events and interpretation rules yield identical results. It must never call payment gateways, send emails, trigger new refunds, or read current wall-clock time during replay. Side effects happen only in controlled workflows when valid events are accepted or compensating processes are initiated.

Example projector aggregating fees:

~~~text
on LateFeeAssessed(event):
    assessed_minor += event.amount_minor

on LateFeeAssessmentReversed(event):
    require not already_reversed(event.reverses_event_id)
    require event.currency matches target fee
    reversed_minor += event.amount_minor
    mark target as reversed

net_fee_minor = assessed_minor - reversed_minor
~~~

The `require` checks highlight that data **must be validated before writing** and projectors need mechanisms to detect inconsistent history. When replaying an accepted history, a projector typically errors and halts on an invalid event for investigation rather than silently “fixing it up”.

### Which Fee Must a Fee-Reversal Event Reference?

If a contract had two fee assessments, each reversal event must point to the target **fee_assessment_id** or **event_id**. Recording only `LateFeeAssessmentReversed { amount: 100000 }` cannot reliably identify which charge was reversed, whether it was a partial reversal, or whether it was reversed twice.

A model may permit **partial reversals**, in which case the invariant is that cumulative reversed amount for each assessment does not exceed its assessed amount. Do not force uniqueness of one reversal per target if the business requires multiple partial adjustments. Where only a single full reversal is allowed, uniqueness per target may fit well.

### Handling Duplicate or Out-of-Order Events

Asynchronous read models should store `last_applied_version` per stream, or a set of processed event IDs when receiving multi-stream data. Basic rules:

- Already-applied version: skip or reconcile if needed.
- Next expected version: apply the event and update the checkpoint in the **same transaction** as the derived data.
- Version greater than expected: fetch missing events before continuing rather than computing wrong balances.

Projections answering **what was known at a point in time** may separate recorded time from effective time; never simply re-sort all events by `effective_at` during replay.

## 9. Compensation in Distributed Workflows: Sagas and Intermediate States

A business process spanning multiple services cannot be rolled back with a single database rollback command.

Hotel booking example:

~~~mermaid
flowchart LR
    A["ReservationConfirmed"] --> B["PaymentCaptured"]
    B --> C{"Room still guaranteed?"}
    C -->|"Yes"| D["BookingCompleted"]
    C -->|"No"| E["CancelReservationRequested"]
    E --> F["ReservationCancelled"]
    F --> G["RefundRequested"]
    G --> H{"Confirmation from payment gateway"}
    H -->|"Refunded"| I["RefundConfirmed"]
    H -->|"Unknown / error"| J["Reconcile or follow up"]
~~~

This is only **one illustrative compensation order**. Depending on policy, room cancellation and refunding may occur in a different order, yet each step needs its own preconditions, idempotency, and pending state. **ReservationCancelled** does not mean money has been refunded. **RefundRequested** does not mean the refund succeeded.

A saga or process manager should track:

| Field | Role |
| --- | --- |
| `process_id` | Identifies a compensation process instance. |
| `step_id`, `step_status` | Which step is pending, succeeded, failed, or has unknown outcome. |
| `original_action_id` | Original action/transaction requiring compensation. |
| `compensation_request_id` | Idempotency key when calling external systems. |
| `attempt_count`, `last_error` | Supports retries and monitoring; never decide outcome solely by attempt count. |
| `correlation_id` | Links events across services to the same business workflow. |

Never automatically retry a step with an **unknown outcome** if retrying could cause a double charge or double refund. Query the authoritative source via `provider_reference`/`idempotency_key` and mark the outcome only after reconciliation.

**The goal of compensation is restoring business invariants and obligations**, not guaranteeing the external world returns to its exact initial state. Sent emails, shipped parcels, or incurred bank fees may require additional measures while keeping full audit trails.

## 10. Fixing Processing Logic, Correcting Source Facts, and Repairing Corrupt Data Are Three Different Procedures

Identify the root cause before “fixing events”:

| Root cause | Appropriate action | Is a new event needed? |
| --- | --- | --- |
| **Bug in projection calculation** while source events are accurate | Fix projector code, rebuild projection, reconcile state. | Usually no new business event, because no new business occurrence happened. |
| **Accepted business fact is later amended** | Record a correction event with evidence, authority, and timestamps. | Usually yes, to preserve the correction progression. |
| **Fee/allocation decision must be reversed** | Record a reversal/adjustment event; protect amounts and targets. | Yes, if it is an approved business change. |
| **Money captured, goods shipped, external service completed** | Execute compensating action; record events on real outcomes. | Yes, events represent each milestone needing traceability. |
| **Event record corrupted by storage bug or migration** | Data recovery/repair procedure under infrastructure governance and audit. | Should not fabricate fake business events to mask corruption. |
| **Duplicate command/callback for the same transaction** | Deduplicate by source key and idempotency. | Do not emit another identical success event without a new occurrence. |

For example, suppose a projector miscomputed total fees because it added `LateFeeAssessmentReversed` as a new fee. When fixing the projector and rebuilding, do not emit a new `RentalFeeFixed` event for every contract if source events were already accurate. Doing so injects a read-layer bug into business history.

Conversely, if a fee was **genuinely approved at the wrong amount** and sent to the customer, a business-meaningful change is needed even if the right formula could recalculate it. The timing of approval/reversal itself carries audit value.

## 11. Time, Retroactive History, and Post-Adjustment Reporting

When past events are corrected, at least two historical questions usually arise:

1. **At time X, what did the system know/record?** For instance, at 11:00 the system believed the customer returned late.
2. **After receiving new evidence, what fact is recognized as effective at time X?** For instance, the valid due time was 11:00, so the 10:30 handover was not late.

The two answers can differ without contradicting each other. A correction event recorded at 12:00 can adjust information **effective** earlier. Therefore separate:

- **`occurred_at`**: when the correction/compensating decision actually happened per confirming source.
- **`recorded_at`**: when the system stored the event.
- **`effective_at`**: when the corrected value or new policy takes effect, if different from recording time.
- **`stream_version`**: accepted event order within the aggregate; always increases along the stream, even for retroactive corrections.

When you need to query both “when a fact was in effect” and “when the system knew what”, a **bitemporal** model may fit. Having `occurred_at` and `recorded_at` alone does not automatically solve all retroactive queries; you must define correction links, how effective intervals are constructed, and how data versions are selected.

### Impact on Analytics

Suppose a dashboard counts late returns:

- **As-recorded reporting:** counts returns the system *assessed* as late at the time. The version 3 late-fee event still counts in this metric.
- **As-effective post-adjustment reporting:** excludes reversed fees and evaluates against the corrected due time. The contract is no longer late under confirmed policy.
- **Operational quality reporting:** counts how many adjustments occurred, root causes, time from detection to correction, and amounts requiring refunds.

If a report only reads final state without knowing about corrections, it cannot answer the first or third metric. If a report sums all `LateFeeAssessed` while ignoring `LateFeeAssessmentReversed`, it will overstate remaining receivables.

## 12. Limits of Immutability: Security, Retention, and Integrity Verification

Event logs are high-value assets that need protection, yet **append-only is not a complete security solution**. What must be designed:

- **Authorization:** applications append only through controlled paths; read/write, admin, and audit roles are separated by need.
- **Integrity:** verified backups, restore drills, anomaly monitoring for unauthorized edits, and reconciliation against external receipts/authorities. Hash chains/signatures can help detect tampering if keys and trust anchors are managed well; they do not by themselves prove event content is true.
- **Privacy:** minimize emails, phone numbers, and payment details in payloads; prefer IDs and access-controlled reference stores where possible.
- **Retention and erasure requests:** define retention, anonymization, encryption, or controlled deletion policies by data class and regulation. Long-lived events can conflict with erasure obligations unless planned from the outset.
- **Event schema evolution:** new code must read old events by `event_type` and `schema_version`. Never silently alter old field semantics; test replay against historical data.
- **Stream limits:** never assume a single aggregate transaction atomically handles external systems. For reliable messaging, use a transactional outbox or equivalent; consumers still need deduplication.

Corrections, reversals, and compensations can live in **relational tables** with foreign-key and unique constraints; fast-read projections can be materialized in a **document store**; causal links of “which event led to which event” can be projected into a **graph**; adjustment metrics can be aggregated in an **analytical warehouse**. Choosing physical structures depends on queries, consistency, write cost, privacy, and operability—not pattern names.

## 13. Practice Exercise: Overcharge Transaction and Refund

**Context:** an online learning service charges 500,000 VND for a course. After payment confirmation, staff discover a valid voucher had been approved prior to the transaction but was not applied; the right amount is 400,000 VND. The system already granted course access and issued an invoice. The payment gateway supports partial refunds.

Design the following:

1. **Distinct occurrences:** payment captured, voucher verified, invoice/price adjusted, 100,000 VND refund requested, refund confirmed. Distinguish internal domain events from payment-gateway confirmation outcomes.
2. **Event names:** propose `PaymentCaptured`, `DiscountCorrectionApproved`, `InvoiceAdjustmentPosted`, `PartialRefundRequested`, `PartialRefundConfirmed`, or better names per domain boundaries. Each name must define its success milestone.
3. **Entities and keys:** determine whether `Enrollment`, `Invoice`, and `Payment` are independent aggregates; design `event_id`, `aggregate_id`, `stream_version`, `provider_payment_id`, `refund_id`, and correlation for the adjustment flow.
4. **Payload:** store original amount, adjustment, currency, voucher/policy code, approval basis, and transaction references. Avoid embedding unnecessary personal data.
5. **Concurrency and retries:** two staff members approve the same adjustment concurrently; the refund callback fires twice. Specify keys, transactions, and conditions ensuring only one adjustment/refund per eligible charge.
6. **Projections:** compute **net invoice value**, **captured amount**, **refunded amount**, and **remaining variance to resolve**; demonstrate state while the refund is pending and once confirmed.
7. **Temporal reporting:** distinguish reporting when the initial invoice was issued from post-adjustment reporting; retain voucher effective time and actual refund completion time.
8. **Failure scenario:** provider times out immediately on the refund call; explain why `PartialRefundConfirmed` must not be emitted and how to reconcile before retrying.

**Self-assessment checklist:**

| Check | Expected outcome |
| --- | --- |
| **Audit trail** | Previously emitted payment and invoice events do not vanish after adjustment. |
| **Semantics** | Separates price/invoice adjustment from external cash-flow refunding. |
| **Authoritative confirmation** | Refund-success event emits only upon trustworthy evidence. |
| **Idempotency** | Command and callback retries never create two refunds or two invoice adjustments. |
| **Replay** | Reconstructs exact net values from events without re-calling payment APIs or resending emails. |
| **Time** | Distinguishes approval date, effective date, and system-recorded date. |
| **Consistency** | Each aggregate enforces local invariants; multi-service flows have explicit coordination. |
| **Data hygiene** | Events carry IDs, versions, references, evidence, authorization, and proper retention policies. |

**Key takeaway:** immutable events preserve the progression previously confirmed by the system; **corrections** record amended facts or decisions; **reversals/adjustments** alter active obligations; **compensating actions** handle real-world side effects that already happened. A solid data model clarifies each type, preserves links, and enforces concurrency control, deduplication, reconciliation, and authorization so final state is right while history remains explainable.
