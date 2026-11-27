# Choosing Business-Meaningful Event Names, Subjects, Data, and Timestamps

## 1. The Design Problem: Recording **What Happened** Unambiguously

A system can store the current state of an order, rental equipment, or transaction; however, when it needs to explain **why** state changed, **who** performed it, **which entity** was affected, and **when** it occurred, a single `status` column is usually insufficient.

Suppose the operations team of an equipment rental service states this requirement:

> “When a customer returns equipment, we want to know whether the customer submitted a return request or actually handed it over, who inspected and accepted it, whether there was any damage, whether it was overdue, and when the deposit was refunded.”

If you design a generic event named `RentalUpdated` with an arbitrary payload, the data can be stored technically, yet becomes very hard to understand and verify later. A high-quality event model must answer four groups of questions:

1. **Name:** which exact business occurrence completed?
2. **Subject and actors:** which entity does the occurrence belong to, and who/which system caused or confirmed it?
3. **Data:** which facts, identifiers, and context must be preserved to interpret the event years later?
4. **Timestamps:** at what times did the event occur, take effect, and get recorded?

These four decisions connect business requirements directly to the **entities, relationships, constraints, keys, and physical schema** of the data system. They apply whether you are building a business log, domain events, integration events, or an event-sourced model; the system does not have to adopt full event sourcing.

## 2. Defining the Boundary of a Business-Meaningful Event

A business event is a **fact accepted by the system** under explicit rules. Distinguish carefully:

| Information type | Example | Interpretation |
| --- | --- | --- |
| **Intent/command** | `RequestEquipmentReturn` | A request to initiate an equipment return; the request may be rejected. |
| **Event** | `ReturnRequested` | The system recorded a valid return request; does not mean the equipment is back in the warehouse. |
| **Event** | `EquipmentDroppedOff` | The equipment was handed over at a drop-off point under a confirmation workflow. |
| **Event** | `EquipmentReturnAccepted` | Staff inspected and accepted the equipment return. |
| **State** | `rental_status = RETURNED` | A projection of current status; by itself it does not convey the full progression sequence. |

Not every technical operation is a domain event. For example, **a user opening a page**, **an API being called**, or **a table row being updated** may be telemetry or technical audit records; they do not necessarily represent a fact that business stakeholders care about. Conversely, **the payment provider confirming completion of a deposit refund** carries value independent of how services are implemented and is usually worth naming as an event.

### Turning Descriptions Into an Event Catalog

An effective technique is to work with domain experts and fill out the following table:

| Business statement | Candidate event | When is it recognized? | Who needs this information? |
| --- | --- | --- | --- |
| “The customer requested an early return.” | `ReturnRequested` | A valid request is recorded. | Customer support, receiving dispatch. |
| “The kiosk received the equipment.” | `EquipmentDroppedOff` | Scan/intake proof at the kiosk exists. | Warehouse, late-fee calculation. |
| “Staff confirmed the equipment passed inspection.” | `EquipmentReturnAccepted` | The inspection report is approved. | Warehouse, deposit accounting. |
| “Equipment damage was discovered.” | `EquipmentDamageAssessed` | The damage assessment result has been approved. | Accounting, claims handling. |
| “The payment provider confirmed the deposit refund.” | `DepositRefundConfirmed` | Reliable refund confirmation is received. | Customer, accounting, reconciliation. |

Each event must have a **point of truth confirmation**. If stakeholders have not agreed on what “received”, “confirmed”, or “refunded” mean and who has authority to confirm them, event names will spark debate and data will be interpreted inconsistently.

### Choosing the Right Granularity

Avoid collapsing independent milestones into a single `ReturnProcessed` if they happen at different times, are performed by different parties, or can succeed/fail separately. Nor should you emit an event every time a form field loses focus. Split events when at least one of the following holds:

- There is a distinct **business rule** for accepting or rejecting.
- There is a distinct **timestamp, confirmer**, or **evidence**.
- A consumer needs to know that milestone without inferring it from technical changes.
- The occurrence creates an obligation, entitlement, cost, or legal/operational status that must be traced.

For example: equipment is placed into a kiosk at 10:05, while staff inspect and accept it at 10:13. If late fees are calculated from **the handover time at the kiosk**, two separate events model the meaning far more clearly than an ambiguous `Returned` event.

## 3. Choosing **Event Names** in the Language of the Business

Good names describe a fact that has already happened, typically following **Entity + Completed Action**. In English, past tense is common, such as `OrderPlaced`, `InvoiceIssued`, `PaymentCaptured`, `ShipmentDispatched`; with irregular verbs or domain terms, prioritize clarity over rigid grammar rules.

| Problematic name | Clearer name | Reason |
| --- | --- | --- |
| `UpdateRental` | `RentalDueDateChanged` | States explicitly which change occurred. |
| `Returned` | `EquipmentDroppedOff` or `EquipmentReturnAccepted` | Distinguishes physical handover from inspection acceptance. |
| `PayDeposit` | `DepositPaymentCaptured` | `PayDeposit` sounds like a request; “captured” indicates a confirmed outcome. |
| `RefundDone` | `DepositRefundConfirmed` | Specifies the business action and confirmation point. |
| `RentalStatusChanged` | `RentalClosed` | Specifies the transition that actually matters to consumers. |
| `ErrorHappened` | `DepositRefundFailed` | Distinguishes a meaningful business failure from a generic system error. |

Practical naming rules:

1. **Use the ubiquitous language of domain practitioners.** If “inspection acceptance” differs from “counter drop-off”, the two event names must differ.
2. **Name after facts, not storage operations.** Avoid `InsertRow`, `ChangeField`, `SyncCompleted` when describing a business change.
3. **Never choose a name implying success before confirmation exists.** `RefundRequested`, `RefundInitiated`, and `RefundConfirmed` are distinct milestones.
4. **Maintain consistency.** Standardize spelling and terms such as `Cancelled`/`Canceled` or `Confirmed`/`Approved` in a domain glossary to prevent synonymous event types.
5. **Keep semantics stable over time.** If inspection criteria evolve structurally, use `event_version`; if the business definition fundamentally changes, consider a new event type.

**Quick test:** reading only the event name, can a domain owner tell what was confirmed? If someone has to inspect source code to know what `OrderUpdated` actually means, the name is not good enough.

## 4. Identifying **Subject**, **Aggregate**, and **Actor**

An event often involves multiple entities. Do not cram all of them into a single `user_id` field, as that loses semantic clarity.

| Role | Question | Example with `EquipmentReturnAccepted` |
| --- | --- | --- |
| **Aggregate/stream owner** | Which business object's ordered change stream does this event belong to? | Rental contract `RENT-204`. |
| **Subject** | Which entity is the direct target of the occurrence? | Equipment `EQ-042` being inspected and accepted. |
| **Actor** | Who or which system performed or decided it? | Warehouse staff `EMP-18`. |
| **Affected party** | Whose rights/obligations are impacted? | The customer on the rental contract. |
| **Source/authority** | Who provides evidence for the outcome? | Warehouse service along with the inspection receipt ID. |

**Aggregate** is the boundary for enforcing invariants and establishing local ordering. In one model, a `Rental` contract may contain multiple pieces of equipment; in another, each `RentedItem` is its own aggregate. Boundary choice depends on invariants: must the entire contract be accepted in one transaction, or does each piece of equipment have an independent lifecycle? Never assume the event's subject is always the aggregate itself.

**Actor** is also not necessarily the beneficiary, the record creator, or the aggregate owner:

- The customer initiates the return request; staff perform inspection; a service emits the event. These can be **three distinct actors or information sources** across steps.
- The system automatically closes a contract: `actor_type = SYSTEM`, `actor_id = rental-scheduler`; do not misattribute it to the customer.
- An action performed by staff on a customer's behalf: may require **acting_on_behalf_of** or **requested_by** depending on traceability and authorization rules.
- A payment provider confirms a refund: record the provider's source/correlation ID; the actor is the payment system or relevant workflow, not the customer confirming it.

Identities inside events should be **stable, clearly scoped identifiers** such as `employee_id`, `customer_id`, `service_name`, or `provider_reference`. Display names, emails, and phone numbers can change and constitute personal data; copy them into events only with a clear business justification and proper privacy controls.

In multi-tenant systems, IDs such as `EQ-042` may only be unique **within each tenant**. Therefore, include `tenant_id` and scope keys, indexes, and access controls per tenant rather than assuming all IDs are globally unique.

## 5. Choosing **Event Data**: Minimal Yet Meaningful

Events are consumed long after the original code or current-state tables have changed. A good payload retains enough data to understand **the fact at the time it occurred**, verify related invariants, reconstruct required state, and answer agreed-upon historical questions.

Event data can be grouped into four categories:

| Group | Contents | Examples |
| --- | --- | --- |
| **Identity and linkage** | Event ID, aggregate ID, subject ID, event type, event version, causation/correlation. | `event_id`, `rental_id`, `equipment_id`. |
| **Business facts** | Outcome, quantity, monetary amount, inspection result, accepted changes. | `inspection_result = PASSED`, `damage_code = NONE`. |
| **Interpretive context** | Fee policy/schedule version, receiving location, coded reason, unit of measure. | `branch_id`, `policy_version`, `reason_code`. |
| **Provenance and time** | Actor, source, timestamps, request/correlation, evidence ID. | `actor_id`, `occurred_at`, `receipt_id`. |

Field selection principles:

- **Record unambiguous data.** `refund_amount_minor = 500000`, `currency = VND` is better than `amount = 500000` without units. For money, integers in the smallest currency unit defined for that currency are usually safer to control than floating-point numbers.
- **Capture values at the time of occurrence if they cannot be reliably inferred later.** For example, the fee schedule applied at billing time or the approved deposit amount; reading the **current** fee schedule can produce wrong historical results.
- **Distinguish references from intentional snapshots.** A `product_id` is useful for linking, but if the product name or category at transaction time governs obligations, capture a snapshot or reference an immutable version of the data.
- **Maintain a schema per event type and version.** Required fields, enums, units of measure, and cross-field relationships must be published; `payload: {}` is insufficient even though it is valid JSON.
- **Do not dump raw requests, database objects, or sensitive data without justification.** Putting an entire customer profile in the payload increases privacy risk and makes events harder to evolve.
- **Do not store derived results that can be computed from immutable facts just “to be safe”.** However, if the result is an **approved business decision** (such as the final damage fee), it may itself be the fact that must be stored.

### When Are Before and After Values Needed?

For `RentalDueDateChanged`, a payload like this is often easy to audit:

~~~json
{
  "old_due_at": "2026-11-20T10:00:00+07:00",
  "new_due_at": "2026-11-22T10:00:00+07:00",
  "reason_code": "CUSTOMER_EXTENSION_APPROVED",
  "approval_id": "APR-891"
}
~~~

In pure event sourcing, `old_due_at` can be derived from prior state. Still, including the old value when there is an explicit audit requirement is reasonable, provided **at write time you verify `old_due_at` matches the accepted state** to avoid storing two contradictory facts. `new_due_at` is the approved change and cannot be inferred from the event name alone.

### Events Do Not Replace the Entire Relational Model

Business relationships must still remain clear: which customer a `Rental` belongs to, which equipment a `RentalItem` references, and which deposit a `Refund` ties to. Events must retain identifiers linking those entities; read models can normalize relational tables, optimize aggregate-oriented documents, or build time-series analytical tables. That choice depends on each context's query and consistency needs.

## 6. Designing **Timestamps** Around Business Questions

A single `timestamp` field easily hides multiple concepts. Agree explicitly on each timestamp:

| Timestamp | Meaning | Example |
| --- | --- | --- |
| **occurred_at** | When the occurrence described by the event actually happened per an authoritative source. | Staff approved inspection at 10:13. |
| **recorded_at** | When the system persisted the event into the event store. | The database wrote the event at 10:13:02. |
| **effective_at** (if applicable) | When the business outcome begins taking effect. | Extension approved today, but the new schedule takes effect tomorrow. |
| **source_observed_at** (if needed) | When a device or partner observed the occurrence prior to sending it to the system. | Kiosk scanned and confirmed receipt at 10:05. |
| **processed_at** (on read models/consumers) | When a worker processed the event. | Report updated at 10:15. |

Not every event needs all of these fields. Add a timestamp when the distinction alters business decisions, audit trails, or reporting outcomes.

### Example: Equipment Return and Inspection

On 2026-11-20 in Vietnam time (`Asia/Ho_Chi_Minh`):

1. **10:05:00:** kiosk confirms equipment handover → `EquipmentDroppedOff` with `occurred_at = 10:05:00`.
2. **10:13:00:** staff inspects and approves return → `EquipmentReturnAccepted` with `occurred_at = 10:13:00`.
3. **10:13:02:** system persists the acceptance event → `recorded_at = 10:13:02`.

If late fees are computed from **handover time at the kiosk**, use the verified timestamp of `EquipmentDroppedOff`. If warehouse quality measures inspection speed, use the delta from physical receipt to acceptance. Using database write time for both metrics produces incorrect results whenever processing lag occurs.

### Effective Time Does Not Mean Completion

On November 20, a customer schedules a plan change effective December 1. At schedule approval time, an appropriate event is `PlanChangeScheduled` with `effective_at = 2026-12-01...`. Do not emit `PlanActivated` while actual activation has not yet occurred. When activation conditions are met, the system emits a separate activation confirmation event or defines a well-specified scheduled-state model.

**Retroactive** effective times must also be modeled intentionally. For example, if policy allows correcting a rental start time: `RentalStartCorrected` has today's approval timestamp while `effective_at` lies in the past. Never silently edit `occurred_at` on an old event to make history look as if no discrepancy ever occurred.

### Time Normalization and Ordering

- Use timezone-aware types (`TIMESTAMPTZ` in PostgreSQL) or store UTC values with an explicit interpretation convention; convert to the appropriate business timezone when displaying or bucketing business days.
- Do not compare free-form date/time strings. If only a **business date** exists (no time of day), use a `DATE` type and dedicated rules rather than fabricating `00:00:00` as if time evidence existed.
- Clocks on external devices and partner systems can drift, and events can arrive late. Record the time source and reliability when needed; never infer absolute ordering by sorting `occurred_at` across multiple systems.
- Within an aggregate's event stream, use **sequence_no** or a guaranteed ordering mechanism to apply changes. `occurred_at` serves business semantics and temporal analytics, not persistence ordering.
- For “event-time” analytics, establish a late-data handling policy; for consumer operations, use recorded/processed timestamps to measure lag.

The distinction between **effective time in the business world** and **when the system learned/recorded it** is also the foundation of **bitemporal** design when you must simultaneously answer “what was actually in effect back then?” and “what did the system know at an earlier reporting date?”.

## 7. Complete Event Contract Example

Suppose contract `RENT-204` rents equipment `EQ-042`. After the kiosk records handover, staff member `EMP-18` inspects and accepts the equipment in good condition. The business event is **EquipmentReturnAccepted**; the emission condition is that inspection acceptance has been approved.

~~~json
{
  "event_id": "13773c4c-66d7-44a7-9d25-c37a53e2a8ce",
  "aggregate_type": "Rental",
  "aggregate_id": "RENT-204",
  "sequence_no": 7,
  "event_type": "EquipmentReturnAccepted",
  "event_version": 1,
  "subject_type": "Equipment",
  "subject_id": "EQ-042",
  "actor_type": "STAFF",
  "actor_id": "EMP-18",
  "source_system": "warehouse-service",
  "occurred_at": "2026-11-20T03:13:00Z",
  "recorded_at": "2026-11-20T03:13:02Z",
  "idempotency_key": "inspection-REC-992",
  "correlation_id": "b0d7e384-d4eb-40ab-9733-e43999f4280b",
  "causation_id": "e3b535d0-823c-4ae3-b79f-64d8fcbec7e4",
  "payload": {
    "equipment_id": "EQ-042",
    "inspection_receipt_id": "REC-992",
    "inspection_result": "PASSED",
    "condition_code": "GOOD",
    "branch_id": "HCM-03",
    "dropoff_event_id": "6f5f5915-d94e-4cf9-aa81-1d5c1c8f3b44"
  }
}
~~~

**How to read this contract:**

- `event_id` identifies the **event occurrence**; `aggregate_id + sequence_no` represents its position in the history of `Rental`. The number 7 in the example is the order **within RENT-204**, not a system-wide sequence number.
- `subject_id = EQ-042` clearly names the inspected equipment, while `actor_id = EMP-18` is the confirming staff member.
- `occurred_at` and `recorded_at` are stored in UTC: 03:13Z corresponds to 10:13 Vietnam time.
- `dropoff_event_id` links to the prior kiosk receipt; do not infer handover time from inspection acceptance time.
- `inspection_result` and `condition_code` are values from a governed **business code dictionary**, avoiding arbitrary descriptive strings.
- `correlation_id` links steps belonging to one process; `causation_id` in the example is the ID of the command or message that triggered the event, with clearly defined type and management rules.
- `idempotency_key` detects resubmitted inspection requests. The key's uniqueness scope must be specified, e.g., per `source_system`; it does not replace `event_id`.

An event contract does not have to duplicate the entire contract state, billing history, or customer profile. If a projection needs data absent from the event, specify whether it comes from **prior events in the same stream**, from **versioned reference data**, or is added to the payload so replay does not depend on mutable external state.

## 8. From Event Contract to Tables, Keys, and Indexes

In a relational model, stable metadata can be separated into strongly typed columns while event-specific payloads remain in `JSONB`. The PostgreSQL example below is scoped to **streams of Rental contracts**:

~~~sql
CREATE TABLE rental_stream (
    rental_id       VARCHAR(64) PRIMARY KEY,
    last_sequence   BIGINT NOT NULL DEFAULT 0
                    CHECK (last_sequence >= 0)
);

CREATE TABLE rental_event (
    event_id         UUID PRIMARY KEY,
    rental_id        VARCHAR(64) NOT NULL
                     REFERENCES rental_stream (rental_id),
    sequence_no      BIGINT NOT NULL CHECK (sequence_no > 0),
    event_type       VARCHAR(100) NOT NULL,
    event_version    SMALLINT NOT NULL CHECK (event_version > 0),
    subject_type     VARCHAR(50) NOT NULL,
    subject_id       VARCHAR(80) NOT NULL,
    actor_type       VARCHAR(40) NOT NULL,
    actor_id         VARCHAR(100),
    source_system    VARCHAR(80) NOT NULL,
    occurred_at      TIMESTAMPTZ NOT NULL,
    recorded_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    effective_at     TIMESTAMPTZ,
    idempotency_key  VARCHAR(160),
    correlation_id   UUID,
    causation_id     UUID,
    payload          JSONB NOT NULL
                     CHECK (jsonb_typeof(payload) = 'object'),
    UNIQUE (rental_id, sequence_no)
);

CREATE UNIQUE INDEX ux_rental_event_idempotency
    ON rental_event (source_system, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

CREATE INDEX ix_rental_event_type_time
    ON rental_event (event_type, occurred_at);
~~~

Explanation of design choices:

- **Primary key `event_id`** distinguishes every event; **UNIQUE(`rental_id`, `sequence_no`)** guarantees a unique position within each stream. When generating sequence numbers, the application must lock or verify the aggregate version inside a transaction, rather than merely computing `MAX(sequence_no) + 1` outside a transaction.
- **Deduplication key `(source_system, idempotency_key)`** works if each source commits never to reuse keys across different operations. If the real deduplication scope is per contract, the key design should include `rental_id`; align with the producer contract.
- **`subject_type + subject_id`** describes the direct target; polymorphic referential integrity does not arise automatically from two columns. If strict foreign keys are required, use dedicated tables or relations per subject type.
- **`actor_type + actor_id`** represents the executing person or service. `actor_id` may be null in well-defined cases (such as an unidentified system background job), but `NULL` should not be used whenever the actor is simply unknown.
- **`payload JSONB`** allows per-`event_type` schemas, but `CHECK(jsonb_typeof(payload) = 'object')` only checks JSON object shape. Required fields, enums, relationships, and version rules must be verified at the event-writing layer or via additional constraint mechanisms.
- **Type-and-time indexes** speed up certain reports at the cost of write overhead. Verify query frequency and execution plans before adding many indexes. For large datasets, consider partitioning and archiving strategies aligned with query/retention requirements.

A reporting query based on **business occurrence time** rather than database write date:

~~~sql
SELECT
    (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        AS business_day,
    COUNT(*) AS returns_accepted
FROM rental_event
WHERE event_type = 'EquipmentReturnAccepted'
GROUP BY 1
ORDER BY 1;
~~~

This query counts only **accepted inspections**. It does not count return requests, kiosk drop-offs, or contracts with refunded deposits; each metric must be tied to its own events and its own deduplication/adjustment exclusion rules.

## 9. Recording Events Correctly Under Concurrency, Retries, and Multiple Services

A well-chosen name and payload can still yield corrupt data if the recording mechanism fails to protect business semantics. Command processing typically follows:

~~~mermaid
flowchart TD
    C["Command: AcceptEquipmentReturn"] --> I{"Request already processed?"}
    I -->|Yes| O["Return previous result"]
    I -->|No| L["Lock/check Rental version"]
    L --> V{"Business invariants valid?"}
    V -->|No| R["Reject, do not emit success event"]
    V -->|Yes| E["Write EquipmentReturnAccepted with next sequence"]
    E --> T["Commit with data needing consistency"]
    T --> P["Update projection / publish via outbox"]
~~~

For example, if equipment `EQ-042` has already been inspected and accepted, a retried API call must not create a second `EquipmentReturnAccepted` that causes reports to double-count. Unique constraints on request keys, aggregate state checks, and idempotent consumers work together to prevent errors.

When events are delivered to other systems:

- **Domain events** express facts within internal business boundaries; **integration events** are externally published contracts that may be filtered or transformed to reduce coupling.
- Services that persist data and publish messages to a broker can fail between the two steps. A **transactional outbox** stores the message payload to publish inside the same transaction as the source change; the relay process and receivers must still handle duplicate delivery.
- **Correlation** ties an entire process together, while **causation** points to the immediate cause; neither replaces `aggregate_id` or `event_id`.
- If a change spans payment, warehouse, and contract services, define the confirmed fact at each service along with compensation or orchestration mechanisms; never treat one local event as proof that all systems have completed.

## 10. Verifying Contract Quality and Managing Change

Before putting an event into production, maintain an **event contract** for each `event_type` covering: a one-sentence definition; emission conditions; aggregate, subject, actor, authority; payload/version schema; timestamp rules; idempotency; constraints; and consumers that depend on it.

Abbreviated contract example:

| Component | `EquipmentReturnAccepted` |
| --- | --- |
| Definition | Inspection acceptance of a returned equipment item under a rental contract has been approved. |
| Emission condition | Valid inspection record, authorized approver, equipment has not already been accepted. |
| Aggregate | `Rental`; ordered by `sequence_no` within each `rental_id`. |
| Subject | The inspected equipment, identified by `equipment_id`. |
| Actor/authority | Approving staff member and warehouse service confirming the result. |
| Minimum payload | `inspection_receipt_id`, `equipment_id`, `inspection_result`, `branch_id`, appropriate condition code. |
| Timestamps | `occurred_at` when inspection was approved; `recorded_at` when persisted. |
| Deduplication | A valid inspection receipt can be accepted only once within the defined scope. |

### Evolving Schemas Without Losing Historical Meaning

Suppose version 2 of the event adds `damage_assessment_version`. Readers must understand both v1 and v2 events via explicit versions and conversion rules. Never silently alter the calculation or code meaning of an old field while historical events remain. Use an **upcaster** during replay or deploy multi-version-compatible readers depending on your architecture.

If an event was recorded erroneously, consider a **traceable adjustment event** (`EquipmentReturnAcceptanceCorrected`, `DamageAssessmentRevised`) governed by authorization and business rules, rather than mutating historical payloads without trace. Where personal data must be deleted or anonymized by policy, storage design and access controls must support that requirement from day one; append-only does not mean retaining all data indefinitely.

### Review Checklist

| Verification question | Passing sign |
| --- | --- |
| Does reading the event name tell you what completed? | Distinguishes “requested”, “received”, “approved”, “refunded”. |
| Is it clear who decided and who was affected? | Actor, subject, aggregate, and affected party have distinct roles when needed. |
| Does replay need to query mutable current data? | Required data or immutable versioned references are captured. |
| Are timestamps accurate for late-return reporting? | Source and rules for choosing `occurred_at`/`effective_at`/`recorded_at` are defined. |
| Can two real events be distinguished from a retry? | Has event ID, scoped idempotency key, and deduplication rules. |
| Can concurrent writes corrupt history? | Aggregate boundaries, locking/versioning, and invariants are checked in a transaction. |
| Can future readers interpret old events? | Has a version contract and compatibility strategy. |
| Is sensitive data properly controlled? | Minimal payload, stable identifiers, clear access and retention policies. |

## 11. Practice Exercise: Designing Events for Delivery Orders

**Requirement:** a store needs to know when staff finish packing an order, when the carrier actually picks it up, who confirmed handover, when the customer successfully receives it, and the reason if delivery fails. An order may have multiple delivery attempts.

**Tasks:**

1. Propose at least four event names and define the **confirmation point** of each event. Distinguish a redelivery request from an actual delivery attempt.
2. For the handover-to-carrier event, identify **aggregate**, **subject**, **actor**, **authoritative source**, related identifiers, and minimum payload.
3. If a driver delivers at 14:30 while the device is offline and syncs at 16:00, specify values and sources for `occurred_at`, `recorded_at`, and how to handle untrusted device clocks.
4. Design how to count **actual delivery attempts** so retries from the device do not inflate the count; specify the deduplication key and rule for distinguishing two separate attempts.
5. State one invariant and one reporting query the model must support; identify the indexes needed based on that query.

**Reference hints:** `OrderPacked`, `ShipmentHandedOver`, `DeliveryAttempted`, `DeliverySucceeded`, `DeliveryFailed` are candidate names. Specify clearly whether `DeliveryAttempted` is emitted for successful deliveries as well or only once before an outcome; if both `DeliveryAttempted` and `DeliveryFailed` are used, never sum both as two delivery attempts. Each attempt record should have a stable `attempt_id` and evidence from a trusted source. If delivery success becomes known late, do not blindly set `occurred_at = recorded_at` when reports require actual delivery time.

A strong model for this scenario does not merely have a valid schema—it answers: **what happened, to whom/which entity, with what facts, at what time, and how can the system verify it?** Those answers determine event names, linking keys, payload structure, constraints, and trustworthy queries.
