# Choosing Between Storing Current State, Change History, or Both

## 1. The Problem: What Do You Need to Know About Data Over Time?

In **DATABASE_DATA_MODELING**, translating business requirements into a data schema does not stop at identifying entities, relationships, keys, and indexes. We must also decide **at what point in time the data has meaning** and **to what extent the system needs to answer questions about the past**. A design that serves the current screen well may not be able to prove why an order was refunded, which price was applied, or which shipping address was previously confirmed.

Consider order number 42 with the following status sequence:

~~~text
10:00  NEW       (created)
10:03  PAID      (paid)
10:15  PACKED    (packed)
11:20  SHIPPED   (handed over for shipping)
~~~

Three questions create three different storage requirements:

- **“What status is the order in right now?”** Requires current state: SHIPPED.
- **“What status was the order in at 10:10, and what steps did it go through?”** Requires historical data that can be queried by point in time.
- **“What did the system believe yesterday about an event that happened last week?”** Requires distinguishing when the event took effect from when the system learned/recorded the event; sometimes a two-timeline (*bitemporal*) model is required.

**State** is the value describing an entity at a point in time (for example, order status, membership tier). **State history** records value versions over time. A **business event** describes what happened (for example, “Payment succeeded”, “Order cancelled at customer request”), and can carry more information than a single state value. Not every application log, HTTP log, CDC message, or audit table is sufficient to accurately reconstruct business history.

Modeling decisions must stem from business questions, retention periods, reconciliation needs, error-correction methods, read/write frequency, and desired consistency guarantees; there is no single choice that is always right for every entity.

## 2. Three Core Approaches

| Approach | What is stored? | Best-suited queries | Key trade-offs | Suitable scenarios |
|---|---|---|---|---|
| **Current state only** (*current state*) | A single record or document holding the latest value; updates overwrite | Fast lookup for “what is it right now?” | Cannot natively answer “what was it before?”; no reliable change trail | Temporary shopping carts, replaceable configurations, cacheable/recreatable values |
| **History only** (*history as source of truth*) | An ordered sequence of immutable versions or events per entity | Reconstructing progression, querying the past, root-cause analysis | Getting the current state requires picking the latest version or rebuilding state; higher query and operational complexity | Ledgers, workflows requiring full traceability, event-sourced systems |
| **Both current and history** (*current + history*) | A current record for fast reads, alongside a history table for traceability | Both real-time screens and investigation/reconciliation | Costs more storage and requires keeping two representations consistent | Order statuses, subscription plans, permissions, list prices with audit/traceability requirements |

Do not equate “history only” with **event sourcing**: a full version table can simply select the latest row, whereas event sourcing stores domain events and applies processing logic to reconstruct state. Likewise, do not treat “both” as two independent sources of truth: you must specify which representation is authoritative, which is derived/copied, or how they are updated atomically so they do not drift out of sync.

### 2.1. Storing Current State Only

~~~sql
CREATE TABLE shopping_cart_item (
    cart_id      bigint NOT NULL,
    product_id   bigint NOT NULL,
    quantity     integer NOT NULL CHECK (quantity > 0),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (cart_id, product_id)
);
~~~

Each time the quantity changes, the existing row is updated; this design makes sense if the business only needs the active cart and has no requirement to investigate individual increments or decrements. The **updated_at** column indicates the most recent update time, **not** previous values. Once a cart becomes an order, the order data must be snapshotted separately so future price and quantity changes do not alter a confirmed transaction.

**Advantages:** simple structure and transactions, small storage footprint, easy unique constraints, and straightforward indexing for current-state queries.

**Limitations:** overwriting updates erase prior state; backups or transaction logs are not a history API with business guarantees. This approach is sufficient only when losing history is an accepted, well-justified decision.

### 2.2. Storing History Only as the Source of Truth

Example of storing order status transitions as immutable records:

~~~sql
CREATE TABLE order_status_event (
    order_id       bigint NOT NULL,
    event_version  bigint NOT NULL CHECK (event_version >= 1),
    from_status    text,
    to_status      text NOT NULL,
    occurred_at    timestamptz NOT NULL,
    recorded_at    timestamptz NOT NULL DEFAULT now(),
    actor_id       bigint,
    reason         text,
    PRIMARY KEY (order_id, event_version)
);

CREATE INDEX ix_order_status_event_time
    ON order_status_event (order_id, occurred_at DESC, event_version DESC);
~~~

An order has version 1 = NEW, 2 = PAID, 3 = PACKED, 4 = SHIPPED. When it is guaranteed that all transitions are recorded in exact order, the current state can be retrieved from the highest version:

~~~sql
SELECT to_status
FROM order_status_event
WHERE order_id = 42
ORDER BY event_version DESC
LIMIT 1;
~~~

**event_version** determines the application order of changes for each order. **occurred_at** is the business time when the event occurred; **recorded_at** is the time the system recorded it—the two values can differ when data arrives late. Do not automatically infer current state by sorting on **occurred_at** if events can arrive late, take effect retroactively, or require adjustments; the application rules must be explicitly defined.

Storing status transitions like this example works well for reconstructing *state*, though it is not yet full event sourcing. If using event sourcing, events should carry domain semantics and schema versions (for example **PaymentCaptured**, **ShipmentDispatched**); you must control replay logic, legacy event handling, and how read projections are built.

**Advantages:** per-version audit trail, easy detection of abnormal transitions, well-suited to explaining “what happened.”

**Limitations:** bulk reads of current state require indexes, projections, or snapshots; data grows with the number of changes; fixing errors typically requires appending compensating/adjustment records and re-establishing order rather than arbitrarily overwriting the past.

### 2.3. Storing Both Current State and History

An entity can serve both goals simultaneously:

~~~mermaid
flowchart LR
    A["Status transition command"] --> B{"Validate transition and version"}
    B -->|Valid| C["Single data transaction"]
    C --> D[("orders: latest status")]
    C --> E[("order_status_history: change record")]
    D --> F["Current status read API"]
    E --> G["Historical lookup / audit"]
    B -->|Invalid| H["Reject or retry"]
~~~

In this pattern, current data and history must be synchronized through a clear mechanism. If both reside in the same relational database, a single transaction is usually the easiest approach to verify; if they span different services, you must define the source of truth, reliable event publishing, replay, and acceptable latency.

**Advantages:** low-overhead current-state queries while also meeting tracking and auditing needs.

**Limitations:** higher write cost, storage cost, and consistency testing effort; requires policies for data deletion, schema upgrades, and partial-failure handling.

## 3. Asking the Right Questions Before Choosing

When interviewing domain stakeholders, capture requirements in terms of **questions that must be answered**, **precision level**, **retention duration**, and **query frequency**.

| Discovery Question | Impact on the Data Model |
|---|---|
| Do users only view the current value, or do they frequently ask “as of date X”? | Current only vs. timestamped/versioned history |
| Are there disputes, refunds, audits, legal compliance, or decision-explainability needs? | Usually requires reliable history, actor, and reason |
| Can past values be edited retroactively? | Must distinguish valid time from recorded time; consider bitemporal |
| Does an entity change state a few times or thousands of times per day? | Impacts storage volume, partitioning, indexing, and snapshot strategy |
| Do current-state queries require low latency at large scale? | Should maintain a well-indexed current table or projection |
| Who has permission to view or delete history? How long is it retained? | Needs retention policies, masking, and personal data protection |
| What happens if events arrive late, duplicate, out of order, or are reprocessed? | Needs idempotency keys, versioning, ordering rules, and correction mechanisms |
| Can the operations team sustain replay, migrations, and drift monitoring? | Operational overhead may favor a simpler model |

You can use the following decision flow:

~~~mermaid
flowchart TD
    A["Does the business need to answer questions about the past?"] -->|No| B["Store current state"]
    A -->|Yes| C{"Need fast, frequent reads of the latest state?"}
    C -->|Yes| D["Store current + history"]
    C -->|No| E["Store history as source of truth"]
    D --> F{"Are there retroactive changes or need to know what the system knew back then?"}
    E --> F
    F -->|Yes| G["Design valid time + system time"]
    F -->|No| H["Single-timeline history may suffice"]
~~~

This is a starting framework, not an absolute algorithm. For example, a ledger may store immutable journal entries while also maintaining a balance projection for fast reads; physically that is “both,” but the **business source of truth** remains the journal entries.

## 4. Which Time Is Being Recorded?

A “history” table without clear time definitions can easily return wrong answers even when the SQL query runs cleanly.

- **Valid time**: when the value is true in the business world. For example, a subscription price takes effect on May 1.
- **System/transaction time**: when the system learned or stored that version. For example, the decision to apply the price starting May 1 was not received until May 3.
- **Event/occurred time**: when the actual action took place; may serve as valid time depending on semantics.
- **Processing time**: when a pipeline read or computed the event; do not treat it by default as valid time.

For instance, on May 5 support adjusts a plan's start date from May 3 back to May 1. When asked **“which plan was in effect on May 2 according to current knowledge?”**, the answer may be the new plan. When asked **“what did the system know on May 2?”**, the answer may still be the old plan. To answer both, storing a single **updated_at** timestamp is insufficient.

### 4.1. Effective-Interval History

Versioned models commonly use half-open intervals **[valid_from, valid_to)**:

~~~text
Plan A: [2026-05-01 00:00, 2026-05-10 00:00)
Plan B: [2026-05-10 00:00, infinity)
~~~

The exact instant May 10 00:00 belongs to Plan B, not simultaneously to A. Using half-open intervals prevents boundary overlap. You must standardize time zones (typically storing instants in UTC with **timestamptz** and displaying in the business time zone), how date-only values are interpreted, and how unbounded end times are represented.

An interval-based query for “value in effect at T”:

~~~sql
SELECT plan_code
FROM customer_plan_version
WHERE customer_id = 100
  AND valid_from <= TIMESTAMPTZ '2026-05-09 15:00:00+00'
  AND (
      valid_to IS NULL
      OR TIMESTAMPTZ '2026-05-09 15:00:00+00' < valid_to
  );
~~~

The example table must enforce a constraint preventing two versions for **the same entity and same validity type** from overlapping (unless the business genuinely allows it). In PostgreSQL you can use an **EXCLUDE** constraint with a range type and GiST index, or enforce overlap checks via transactions/locks; simply adding **UNIQUE(customer_id, valid_from)** is not enough to prevent overlapping intervals.

### 4.2. Bitemporal When You Need Both “When It Was True” and “When It Was Known”

A bitemporal record can carry the following columns:

| Column | Meaning |
|---|---|
| customer_id, plan_code | Entity and value |
| valid_from, valid_to | Interval during which the value is valid in the business |
| recorded_from, recorded_to | Interval during which the system considered this version accurate |
| correction_reason, source_id | Reason for correction and supporting reference |

Conceptual query with two parameters **business_time** and **knowledge_time**:

~~~sql
SELECT plan_code
FROM customer_plan_bitemporal
WHERE customer_id = 100
  AND valid_from <= :business_time
  AND (valid_to IS NULL OR :business_time < valid_to)
  AND recorded_from <= :knowledge_time
  AND (recorded_to IS NULL OR :knowledge_time < recorded_to);
~~~

The placeholders **:business_time** and **:knowledge_time** are application-bound parameters; they are not direct variable syntax in standard PostgreSQL SQL runners. When correcting a past point in time, you must preserve the version the system previously believed to be true, close the old recorded interval, and insert a newly recorded version; existing valid intervals may need to be split. You must define the behavior when a retroactive change affects multiple versions.

**Bitemporal modeling carries significant cost**: non-overlap constraints across time slices, retroactive validity updates, complex queries, and large storage volume. Use it only when both temporal questions are true business requirements. For an order workflow that only needs to know when each transition was recorded, a single-timeline history may be enough.

## 5. Reference Design: Orders with Current State and History

Suppose the system needs to:

1. Display the current order status quickly.
2. Trace every status change, who performed it, and why.
3. Prevent two concurrent requests from losing a change.
4. Ensure the current state row and the history record succeed or fail together.

Below is a PostgreSQL example with simplified statuses to focus on the data model:

~~~sql
CREATE TABLE orders (
    order_id            bigint PRIMARY KEY,
    status              text NOT NULL
                        CHECK (status IN ('NEW', 'PAID', 'PACKED',
                                         'SHIPPED', 'CANCELLED')),
    status_version      bigint NOT NULL CHECK (status_version >= 1),
    status_changed_at   timestamptz NOT NULL
);

CREATE TABLE order_status_history (
    order_id       bigint NOT NULL REFERENCES orders(order_id),
    version        bigint NOT NULL CHECK (version >= 1),
    from_status    text,
    to_status      text NOT NULL
                   CHECK (to_status IN ('NEW', 'PAID', 'PACKED',
                                       'SHIPPED', 'CANCELLED')),
    changed_at     timestamptz NOT NULL,
    actor_id       bigint,
    reason         text,
    PRIMARY KEY (order_id, version),
    CHECK (from_status IS DISTINCT FROM to_status)
);

CREATE INDEX ix_order_history_as_of
    ON order_status_history (order_id, changed_at DESC, version DESC);
~~~

**The primary key (order_id, version)** uniquely identifies a single change on an order. **status_version** is the current state version used for concurrent write control. **changed_at** in this example is the system time when the transition occurred, not a retroactive effective time. **actor_id** may be null for system-triggered transitions; if auditing is needed, add execution source metadata such as **actor_type** and a correlation/request ID.

When creating an order, write the initial status and version 1 of history in the same transaction:

~~~sql
BEGIN;

INSERT INTO orders (order_id, status, status_version, status_changed_at)
VALUES (42, 'NEW', 1, statement_timestamp());

INSERT INTO order_status_history (
    order_id, version, from_status, to_status,
    changed_at, actor_id, reason
)
SELECT order_id, status_version, NULL, status,
       status_changed_at, NULL, 'Order created'
FROM orders
WHERE order_id = 42;

COMMIT;
~~~

When a request transitions from **PACKED** to **SHIPPED**, the application has read version 4 and uses a single atomic statement:

~~~sql
WITH transitioned AS (
    UPDATE orders
    SET status = 'SHIPPED',
        status_version = status_version + 1,
        status_changed_at = statement_timestamp()
    WHERE order_id = 42
      AND status = 'PACKED'
      AND status_version = 4
    RETURNING order_id, status_version, status_changed_at
)
INSERT INTO order_status_history (
    order_id, version, from_status, to_status,
    changed_at, actor_id, reason
)
SELECT order_id, status_version, 'PACKED', 'SHIPPED',
       status_changed_at, 1001, 'Handed over for shipping'
FROM transitioned
RETURNING order_id, version;
~~~

- If the version/status condition does not match, **transitioned** returns zero rows; no history row is inserted. The application must check for an empty result, report a conflict, or re-read and decide whether to retry.
- If the history insert violates a constraint, **the entire statement is rolled back**, including the status update. A single SQL statement like this is atomic in PostgreSQL.
- The condition **status = 'PACKED'** only guards this specific transition example. With richer business rules (such as cancellations, refunds, and fulfillment handling), full state-transition and authorization checks must be enforced in the service or via corresponding database constraints.
- The example assumes all status write paths go through this protocol. If another system updates **orders** directly, history completeness is no longer guaranteed. Write privileges can be restricted, or stored procedures/triggers can be used if centralized enforcement is needed.

Current state lookup:

~~~sql
SELECT status, status_version, status_changed_at
FROM orders
WHERE order_id = 42;
~~~

History sequence lookup:

~~~sql
SELECT version, from_status, to_status, changed_at, actor_id, reason
FROM order_status_history
WHERE order_id = 42
ORDER BY version ASC;
~~~

Lookup for the status **recorded by the system** no later than time T:

~~~sql
SELECT to_status
FROM order_status_history
WHERE order_id = 42
  AND changed_at <= TIMESTAMPTZ '2026-05-10 10:10:00+00'
ORDER BY changed_at DESC, version DESC
LIMIT 1;
~~~

If the query returns no rows, the order may not have existed at T or history may not have been retained far enough back; do not automatically interpret this as **NEW**. If you need to query by actual occurrence time or retroactive effective time, you must explicitly model **occurred_at/valid_from** following the semantics in section 4 rather than assuming **changed_at** covers every time axis.

This design also does not by itself guarantee that history always contains the final record for every row: the foreign key only protects references from history to **orders**. All write paths must be controlled, and periodic reconciliation should be run—for example checking **orders.status_version = MAX(history.version)** and the corresponding latest status value.

## 6. How to Maintain History Without Letting It Become Untrustworthy

### 6.1. Business Immutability and Auditable Corrections

History records treated as evidence of recorded changes should be **append-only** at the business level: do not delete or edit an old step just to make metrics look cleaner. If the **SHIPPED** status was entered by mistake, create a **corrective** transition with a reason and approver according to business rules. In bitemporal modeling, closing **recorded_to** on an old version is a defined history-management operation; it must not erase the fact that the system previously recorded that version.

However, “append-only” does not mean retaining personal data forever. Security policies and retention limits may require deleting, anonymizing, or separately encrypting sensitive data. Design identifiers and payloads minimally instead of copying all PII into every history record.

### 6.2. Concurrency, Duplicate Events, and Out-of-Order Arrival

Common failure modes:

- Two users edit the same order at version 4: without version checking, the last write can overwrite the earlier change. Use optimistic locking or appropriate row/transaction locking.
- A customer clicks “Pay” twice: if every request emits a new event, history may end up with two identical business operations. Use a unique **idempotency key** per business request; retries must return the appropriate result without duplicating the change.
- Events from external systems arrive late: **recorded_at** may be later than **occurred_at**. Define clear rules for accepting, ignoring, compensating, or adjusting subsequent states.
- Clock skew across machines: do not rely on **timestamp** alone to order concurrent events. Per-entity sequential versions or business sequences provide a reliable basis for application order.

When updating the database and publishing a message to a message broker, a successful database write followed by a failed message publish leaves services out of sync. A **transactional outbox** (storing the outbound message in the same transaction as the data update, then publishing with retries) usually closes this gap. Consumers still need idempotency; *at-least-once* delivery can produce duplicate deliveries.

### 6.3. Do Not Confuse Audit Logs, CDC, Snapshots, and Business History

| Mechanism | What It Solves Well | What It Does Not Guarantee |
|---|---|---|
| **Audit log** | Who acted, what action, from which source | Effective value at every point in time or exact business logic |
| **CDC / database log** | Streaming changed data to other systems | Infinite retention, business semantics, cross-service ordering |
| **Snapshot** | Fast reads or aiding reconstruction from a recent checkpoint | All intermediate changes between snapshots |
| **Temporal version table** | Entity value during defined time intervals | Why changes occurred unless reason/source are stored |
| **Event sourcing** | Storing domain events as source of truth, supporting replay | Easy schema upgrades for old events, operational simplicity, or ad-hoc querying |

They can be combined, but responsibilities must be clearly named. For instance, CDC can stream **order_status_history** to an analytics warehouse; the history table still defines status semantics, while CDC is merely the transport mechanism.

## 7. Keys, Constraints, Indexes, and Storage Volume

A conceptually sound history model can still be slow or fail to preserve integrity without physical rules.

**Keys and uniqueness.** For event history, **(entity_id, version)** is typically the natural key protecting per-entity ordering. For effective-dated versions, you can use a surrogate key (**version_id**) alongside a separate constraint on **entity_id + validity interval**. If multiple status types are stored in the same table, constraints must include **status_type**.

**Relational constraints.** Statuses must belong to a valid set; transitions must not skip into forbidden steps; an initial version must exist; end time must be greater than start time; validity intervals must not unintentionally overlap. Not every rule can be expressed with CHECK constraints alone: transitions depending on prior rows or multiple records often require transactions, triggers, or service logic.

**Indexes driven by real queries.** Current reads use **order_id**. Per-entity history reads use **(order_id, version)** or **(order_id, changed_at DESC, version DESC)**. Reporting all changes in a single day across millions of orders may need a standalone time index, monthly partitioning, or an analytical store; an index leading with **order_id** does not automatically optimize date-range scans. More indexes increase INSERT/UPDATE overhead and storage usage.

**Storage and lifecycle.** Estimate capacity using:

~~~text
number of entities × average changes / entity / period
                   × size of one version
                   × number of retention periods
+ size of indexes, replicas, and backups
~~~

If prices for one million products change every hour, storing the entire product document on every change can be prohibitively expensive. Consider storing only changed columns, versioning only attributes that need querying, or coalescing by effective intervals. However, storing only *deltas* makes reconstruction harder and fragile if a step is missing; prove the benefit before optimizing.

**Deletion and retention.** Define separate retention periods for operational data, audit history, and analytical data; sensitive payloads may need to be separated from historical identifiers. Do not enable cascade deletes that accidentally wipe out historical evidence; with foreign keys like in the example, order deletion workflows must be designed alongside history retention/deletion policies.

**Schema migration strategy.** When adding new statuses or changing event structures, preserve the ability to read old data. Event sourcing requires handling event versions, upcasters, or backward-compatible replay logic; version tables may need backfills with clear source and confidence metadata. Never assign fake timestamps to historical data lacking time information.

## 8. Dependence on Database Type and Query Patterns

The same temporal requirement can lead to different physical structures:

| Data Model / System | Common Pattern | Key Considerations |
|---|---|---|
| **Relational database** | Current table, version table, event table; foreign keys, transactions, time indexes | Interval constraints, atomic writes, retention, and partitioning |
| **Document database** | Current document + history collection; occasionally small embedded change arrays | Unbounded document growth, document size limits, multi-document transactions, history querying |
| **Graph database** | Current nodes/edges or versioned edges with valid_from/valid_to | Relationships changing over time, path queries at T, cross-node consistency |
| **Analytical warehouse** | SCD Type 2 dimension tables and fact tables storing time-aligned version keys | Data load timing, late-arriving dimensions, impact on period joins |
| **Event stream / event store** | Immutable events, current projections, checkpoint snapshots | Replay, error handling, schema compatibility, ordering, and idempotency |

**SCD Type 1** overwrites attributes (close to current-only); **SCD Type 2** retains value versions across effective intervals (close to history). These are data-warehousing techniques, not proof that every change in the transactional system was captured. If data is batch-loaded nightly without capturing intraday changes, the analytical warehouse cannot reconstruct intermediate states that were overwritten.

In graphs, the history of **relationships** matters just as much: an employee belongs to team A from January to March and then moves to team B; if you only version the employee node without versioning the **MEMBER_OF** edge, org queries for February will be wrong. In document databases, an embedded **history** array inside a single document is convenient when changes are few, but must be split into a separate collection when history grows unboundedly.

## 9. Three Model-Selection Scenarios

### Scenario A: Temporary User Display Preferences

Requirement: only the latest UI layout is needed; old changes have no support or audit value. Read latency matters, and settings can be reset.

**Choice:** current state. You may add **updated_at** for synchronization or write-conflict handling; do not create a history table just because you can. If a requirement to restore previous versions emerges later, evaluate adding version history, version retention limits, and access permissions.

### Scenario B: Transaction Ledger

Requirement: prove money flow, reconcile every movement, never silently edit past entries. Balances must be verifiable from authoritative entries.

**Choice:** immutable entries/events as the source of truth; a current-balance table can be built as a projection for fast queries. Adjusting entries are appended with references to the entries being corrected; the balance table must never replace transaction evidence.

**Note:** a ledger model requires domain-specific invariants such as balanced Debit/Credit totals, currencies, posting order, and period-closing rules; these cannot be inferred solely from a generic status table.

### Scenario C: Order Status and Customer Support

Requirement: staff view current status thousands of times per day, customers need a delivery timeline, and support needs to know who changed a status and why.

**Choice:** current + history, written consistently. If a shipping partner sends a “delivered” milestone late, record the actual delivery timestamp separately from the system receipt timestamp; check whether a late update is allowed to overwrite the latest status. If retroactive adjustments cause disputes, determine whether single-timeline or bitemporal history is required.

## 10. Validating the Design Before Deployment

Data testing must verify **the meaning of the answers**, not merely that INSERT/SELECT statements run without error:

| Scenario | What Must Hold True |
|---|---|
| Initial entity creation | Initial state exists; if full history is required, initial version exists |
| Valid status transition | Version increments by exactly one, current state matches final history version |
| Two requests editing the same version | Only one succeeds; the other detects a conflict |
| Failure while writing history | Current state must not change without the corresponding history record |
| Retried request | Does not duplicate the same business change |
| Querying state at T, before creation, and at interval boundaries | Returns accurate results; distinguishes “did not exist yet” from “no longer retained” |
| Late-arriving or retroactively corrected data | Distinguishes valid/effective time from system recording time |
| Deletion/anonymization per retention | Complies with retention limits while protecting mandatory evidence |
| Schema upgrade | Old data/versions remain readable or replayable under defined rules |

One reconciliation check for the **orders + order_status_history** model is to fetch the history record with the highest **version** for each order and compare it with **orders.status_version** and **orders.status**. If they diverge, raise an alert and remediate through an auditable workflow; never run blind bulk fixes without understanding the root cause.

## 11. Practice Exercise: Turning Vague Requirements into Clear Decisions

A subscription management system states the requirement: “Need to see the customer's active plan and investigate complaints about last month's billed plan.”

Clarify four groups of questions:

1. **Queries:** do we need the **current** plan, the plan **effective on the billing date**, or the plan **the system believed to be true when generating the invoice**? Those three answers can differ.
2. **Changes:** do plan switches take effect immediately or at the start of the next cycle? Is backdating the effective date into the past allowed? When edited, by what business process are finalized invoices adjusted?
3. **Invariants:** can one customer hold multiple plans of the same type at the same time? Which versions are allowed to overlap? Who is permitted to edit, and what reasons must be recorded?
4. **Operations:** change volume, retention period, customer/date indexes, billing-system synchronization, and how to verify no history records are missing?

Suppose the product requires fast current-state queries, 24 months of history, allows adjusting a plan's effective date after a dispute, and needs to know what data the system recorded at invoice generation time. Then **current table + bitemporal history** is a strong candidate. Include the test case “subscribe to Plan A on May 1, switch to B effective May 10, on May 12 adjust B to take effect May 8” and verify both questions: the plan effective on May 9 according to the latest knowledge, and what the system knew on May 9.

If the retroactive requirement is dropped and only a timeline of plan switches at action time is needed, a **current + single-timeline versioned history** model becomes considerably simpler.

## 12. Concluding Principles

Choose the model based on **the questions the system is required to answer** and **the changes the system must prove**:

- Only need the latest value and overwrites are acceptable: **store current state**.
- History is the source of truth and progression must be reconstructed: **store history**, and build projections/snapshots when speed is needed.
- Heavy current reads plus past explainability: **store both** with a consistency protocol, version locking, and reconciliation checks.
- Retroactive values exist or you need to know “what the system knew back then”: add **two timelines** when the business genuinely demands it.

For each choice, complete the model with keys, constraints, indexes, concurrency behavior, retention periods, access controls, and sample queries. A good data schema produces accurate answers over time, is straightforward to verify, and can evolve as business rules change.
