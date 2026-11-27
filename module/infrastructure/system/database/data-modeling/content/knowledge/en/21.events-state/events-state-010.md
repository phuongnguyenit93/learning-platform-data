# Choosing a State Model or an Event Model Based on Real Requirements

## 1. Starting Point: Does the Business Need Current State or Progression History?

When modeling data, a seemingly simple requirement like “display order status” often hides several distinct questions:

- What status is the order **currently** in?
- Which steps has the order **gone through**, who decided them, and based on what evidence?
- Why did the status change; was it ever cancelled and reopened?
- If fee calculation formulas change, must outcomes be recalculated from history?
- When other systems receive notifications late or duplicated, is the final state still right?

No single data model optimizes every question. A **state-oriented model** prioritizes storing an entity's current values. An **event-oriented model** prioritizes recording meaningful occurrences. In one specialized variant—**event sourcing**—accepted events serve as the source of truth, while current state is derived from events.

The right choice does not depend on which architecture sounds more “modern”. It depends on **business invariants, the value of history, query patterns, consistency requirements, verifiability, and operational cost**. That is also the goal of data modeling: from business requirements, identify entities, relationships, keys, constraints, and an evolvable physical schema.

Our running example is an equipment rental platform:

- Customers create rental contracts, pay deposits, extend deadlines, and return equipment.
- Staff can adjust fees if an approved extension record was previously missed.
- The payment gateway confirms captures and refunds asynchronously.
- Operations needs fast lookup of active contracts; audit needs to explain history.

If you only need to know which contracts remain open, a `rental_contract` table may suffice. If you need to explain every decision and rebuild multiple data views from history, evaluate event storage more seriously.

## 2. Five Common Options, Not Just Two Extremes

In practice, several options sit between “store only state” and “make everything event sourced”.

| Option | Source of truth for state | History/exchange mechanism | Best suited when |
| --- | --- | --- | --- |
| **A. State-only** | Current row/document. | Possibly only `created_at`, `updated_at`. | Simple CRUD; no need to explain each transition. |
| **B. State + audit history** | Current row/document. | Audit log tracks who changed what and when. | Need action traceability without replaying events to compute state. |
| **C. State + domain/integration events + outbox** | Current state. | Records business facts and reliably delivers messages to other systems. | Need reliable integration without event sourcing. |
| **D. Event sourcing** | Sequence of accepted business events. | State and read models are derived data and replayable. | History and ability to reconstruct state are core requirements. |
| **E. Hybrid per bounded context** | Each domain picks an explicit source of truth. | Domains exchange data via integration contracts. | Large systems with sharply differing domain needs. |

**Important notes:**

- Having an **`events` table**, **Kafka**, **CDC**, or a **transactional outbox** does not automatically make a system event sourced.
- Having an **audit trail** does not prove the audit data carries enough semantics, order, and completeness to reconstruct state.
- **CQRS** (separating write and read models) pairs with either state-first or event sourcing; it does not force changing the source of truth to events.
- An immutable transaction ledger is a valuable design for finance, yet using an append-only ledger **does not imply** every product aggregate must use event sourcing.

Diagnostic rule: when data conflicts, which record is treated as **authoritative**? If the state table is authoritative and the event log is only for tracking, that is state-first. Only when the event sequence is authoritative and state can be discarded and rebuilt from events is it event sourcing in the architectural sense.

## 3. Translating Business Requirements Into Selection Criteria

Before picking a database or drawing schemas, ask business and operations owners clear questions.

| Question to clarify | Favors state-first | Favors event sourcing |
| --- | --- | --- |
| **What needs to be queried?** | Mostly current values and filtered lists. | Need progression timelines, multiple historical views, and recalculating outcomes from facts. |
| **What role does history play?** | Serves bounded investigations or action auditing. | Core business data affecting outcomes and explaining decisions. |
| **Is recalculation needed?** | State can be updated/migrated under clear rules. | Must rebuild multiple projections by replaying semantic history. |
| **Where do invariants live?** | Usually clear across one or two rows and constraints. | Must model an aggregate's transition sequence; still enforced in transactions. |
| **Is data corrected frequently?** | Editing state directly can be simpler. | Adjustments require new events and reversal/correction logic. |
| **Are current-state SLOs strict?** | Query indexed current tables directly. | Typically requires dedicated read models and defined projection lag. |
| **How long do schemas/history live?** | Migrations usually target current data and needed audits. | Requires readers/upcasters for old events, long-term storage, and suitable snapshots. |
| **Privacy/erasure requirements?** | Updating/deleting current records is more localized. | Append-only history requires dedicated strategies for sensitive data. |
| **What can the team operate?** | CRUD, transactions, and audits may suffice. | Must also operate replay, versioning, projections, checkpoints, rebuilds, and monitoring. |

**No single row dictates the whole decision.** High compliance demands might require a digitally signed immutable audit log yet **not require** event sourcing if state never needs rebuilding from events. Conversely, a low-traffic system may still adopt event sourcing because business progression is the essence of its data, not because it needs throughput.

### Metrics You Should Gather

A useful architectural review needs verifiable numbers:

- Read/write frequency, entity counts, and lifecycle length per entity.
- Average and P95/P99 transition counts per aggregate.
- Read/write SLOs (latency, availability) and tolerable stale-read windows.
- Specific audit questions: who, what evidence, when; do you need before/after values only or semantic event explanations?
- Retention periods, erasure/anonymization mandates, consumer count, and existing data contracts.
- Expected number of event schemas, rule-change frequency, and ability to test replay.

If these inputs are missing, start with a minimal model with clear consistency boundaries, measure workload, and refine—avoid building a massive event store based purely on assumptions.

## 4. State Model: Choose When Current Entities Are Primary Data

A state table fits well when the business mostly manipulates and queries current entities such as equipment catalogs, warehouse addresses, notification settings, or short-lived requests.

Rental contract example:

~~~sql
CREATE TABLE rental_contract (
    rental_id           VARCHAR(64) PRIMARY KEY,
    customer_id         VARCHAR(64) NOT NULL,
    equipment_id        VARCHAR(64) NOT NULL,
    rental_status       VARCHAR(24) NOT NULL,
    due_at              TIMESTAMPTZ NOT NULL,
    deposit_minor       BIGINT NOT NULL
                        CHECK (deposit_minor >= 0),
    deposit_currency    CHAR(3) NOT NULL,
    version             BIGINT NOT NULL DEFAULT 0
                        CHECK (version >= 0),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (
        rental_status IN (
            'ACTIVE', 'RETURNED', 'CLOSED', 'CANCELLED'
        )
    )
);

CREATE INDEX ix_rental_status_due
    ON rental_contract (rental_status, due_at);
~~~

This table allows fetching state by primary key, filtering active contracts, and sorting by due date. The `CHECK` constraint blocks invalid status strings, yet does not by itself prove that every **transition** such as `CLOSED -> ACTIVE` is valid. Transition logic and transactions must still enforce business rules.

If two requests update the contract concurrently, use **optimistic concurrency**:

~~~sql
UPDATE rental_contract
SET due_at = :new_due_at,
    version = version + 1,
    updated_at = now()
WHERE rental_id = :rental_id
  AND version = :expected_version
  AND rental_status = 'ACTIVE'
RETURNING rental_id, version;
~~~

If zero rows return, data changed or preconditions failed. The application must reload state and re-evaluate from scratch rather than assuming success. This `version` is a **state-row version**, not an event-sourcing stream version.

### What This Model Does Well

- Fewer moving parts; primary keys, foreign keys, unique constraints, and check constraints are straightforward.
- Fast “current” queries with minimal transformation before reading.
- Easy to protect invariants using transactions and relational constraints.
- Migrating current data is usually simpler than maintaining many historical event versions.

### What It Does Not Provide on Its Own

The `rental_contract` table holds only the final `due_at`, so it **cannot tell on its own** who changed the deadline, what the old value was, or when it took effect. Adding `updated_at` does not replace business history; nor can you replay an event sequence that was never recorded.

When those questions arise, add audits or events; you do not automatically have to switch the source of truth to an event stream.

## 5. State + Audit Log: Explaining Actions Without Replaying for Recovery

Suppose operations needs to know which staff member edited a due date along with old/new values. You can persist an audit record inside the same transaction as the state update:

~~~sql
CREATE TABLE rental_audit (
    audit_id            UUID PRIMARY KEY,
    rental_id           VARCHAR(64) NOT NULL,
    action              VARCHAR(80) NOT NULL,
    actor_id            VARCHAR(64),
    old_values          JSONB,
    new_values          JSONB,
    reason_code         VARCHAR(80),
    recorded_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (rental_id) REFERENCES rental_contract(rental_id)
);

CREATE INDEX ix_rental_audit_history
    ON rental_audit (rental_id, recorded_at, audit_id);
~~~

An extension transaction checks permissions, status, and version, updates `rental_contract`, inserts `rental_audit`, and commits atomically. Then:

- `rental_contract` is the source of truth for current state.
- `rental_audit` serves traceability and explains actions.
- Whether you can **reconstruct full state from audits** depends on completeness and audit-generation rules—never assume it by default.

Distinguish clearly:

| Trail type | Primary question | Example |
| --- | --- | --- |
| **Data-change audit log** | Who/what changed which field from which value to which value? | `due_at: 10:00 -> 11:00` by staff A. |
| **Domain event** | What business occurrence happened? | `RentalExtensionApproved` approved by authorized actor. |
| **CDC record** | Which `INSERT`/`UPDATE`/`DELETE` did the DB record? | Row in `rental_contract` modified some columns. |

You can persist both audit logs and domain events when they serve distinct goals. Avoid “writing two tables just in case” without defining which is authoritative, how they reconcile, and how long each is kept. Legal-grade audit logs also require tamper resistance, strict access control, retention, and evidence preservation beyond merely having a SQL table.

## 6. State + Events + Outbox: Reliable Notifications While Keeping State Authoritative

A service may need to publish `RentalClosed` to CRM and accounting while keeping `rental_contract` as the source of truth. A **transactional outbox** fits this scenario.

~~~mermaid
flowchart TD
    C["Command CloseRental"] --> V{"Check invariants"}
    V -->|"Invalid"| X["Reject"]
    V -->|"Valid"| T["DB transaction: update rental_contract + INSERT outbox"]
    T --> O[("Committed outbox row")]
    T --> S[("rental_contract: state source")]
    O --> R["Relay / CDC connector"]
    R --> E["Integration event RentalClosed.v1"]
    E --> A["CRM"]
    E --> B["Accounting"]
~~~

Illustrative outbox schema:

~~~sql
CREATE TABLE integration_outbox (
    message_id       UUID PRIMARY KEY,
    aggregate_id     VARCHAR(64) NOT NULL,
    event_type       VARCHAR(100) NOT NULL,
    schema_version   SMALLINT NOT NULL CHECK (schema_version > 0),
    payload          JSONB NOT NULL
                     CHECK (jsonb_typeof(payload) = 'object'),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at     TIMESTAMPTZ
);

CREATE INDEX ix_outbox_unpublished
    ON integration_outbox (created_at, message_id)
    WHERE published_at IS NULL;
~~~

The application writes **state** and **publishing intent** in the same transaction. A relay delivers messages after commit. If the relay sends successfully but crashes before marking the row published, the message may be redelivered; consumers must process **idempotently** by `message_id` or a suitable business key. Outbox prevents lost publishing intent caused by the gap between committing data and calling a broker, yet **does not create end-to-end exactly-once guarantees across all systems**.

This is a sound choice when reliable integration and notifications are needed without **replaying full history to build state**. Events published to consumers carry their own shared contract and do not have to mirror internal tables or CDC rows.

## 7. Event Sourcing: When Progression Is the Primary Data to Protect

In event sourcing, an aggregate is defined by **its sequence of accepted events**. State tables can be dropped, recreated, or projected differently from history as long as events remain complete, readers stay compatible, and recovery preconditions hold.

Example `Rental`:

| stream_version | Event | Core facts |
| ---: | --- | --- |
| 1 | `RentalStarted` | Equipment, due date, contract deposit. |
| 2 | `DepositCaptured` | Deposit captured and confirmed by payment provider. |
| 3 | `RentalDueDateExtended` | New due date and approval evidence. |
| 4 | `EquipmentDroppedOff` | Equipment dropped off at intake point. |
| 5 | `EquipmentReturnAccepted` | Inspection passed and accepted. |
| 6 | `DepositRefundConfirmed` | Refund confirmed in reality. |
| 7 | `RentalClosed` | Contract formally closed. |

Current state is the result of:

~~~text
state@version7 = fold(initial_state, event1 ... event7)
~~~

Example event envelope:

~~~json
{
  "event_id": "458a91ea-8537-446a-954c-c26cb802b1bc",
  "aggregate_type": "Rental",
  "aggregate_id": "RENT-204",
  "stream_version": 6,
  "event_type": "DepositRefundConfirmed",
  "event_schema_version": 1,
  "occurred_at": "2026-11-20T05:20:00Z",
  "recorded_at": "2026-11-20T05:20:02Z",
  "payload": {
    "refund_id": "REF-702",
    "amount_minor": 200000,
    "currency": "VND",
    "provider_confirmation_id": "GW-559"
  }
}
~~~

`stream_version` expresses **order within Rental**, not system-wide order. `event_schema_version` specifies how to parse the payload. `occurred_at` is the confirmed business timestamp; `recorded_at` is when the system persisted it. Monetary values require explicit units, currency codes, and confirming sources.

### Minimal Physical Model

~~~sql
CREATE TABLE rental_event_stream (
    rental_id        VARCHAR(64) PRIMARY KEY,
    current_version  BIGINT NOT NULL DEFAULT 0
                     CHECK (current_version >= 0)
);

CREATE TABLE rental_event (
    event_id             UUID PRIMARY KEY,
    rental_id            VARCHAR(64) NOT NULL
                         REFERENCES rental_event_stream(rental_id),
    stream_version       BIGINT NOT NULL CHECK (stream_version > 0),
    event_type           VARCHAR(120) NOT NULL,
    event_schema_version SMALLINT NOT NULL
                         CHECK (event_schema_version > 0),
    occurred_at          TIMESTAMPTZ NOT NULL,
    recorded_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload              JSONB NOT NULL
                         CHECK (jsonb_typeof(payload) = 'object'),
    UNIQUE (rental_id, stream_version)
);

CREATE INDEX ix_rental_event_type_date
    ON rental_event (event_type, occurred_at);
~~~

A command must read latest state, check invariants, and append events with **expected version** inside a transaction. Lock the `rental_event_stream` row or use conditional updates/CAS; updating `current_version` and inserting events must commit together. `UNIQUE(rental_id, stream_version)` alone does not stop a command from validating against stale state and simply incrementing the version to insert an invalid event.

### What Do You Gain and What Must You Carry?

**Potential benefits:** rich business history, explainable state provenance, multiple rebuildable projections, progression audits, explicit modeling of corrections and reversals.

**Mandatory costs:** long-lived event versioning, historical upcasters/readers, snapshots for long streams, projector deduplication/checkpoints, eventual consistency when using async read models, operational recovery, and privacy governance inside append-only history.

Event sourcing does **not** magically eliminate concurrency control, distributed transactions, provider failures, late-arriving data, or data-protection obligations. All still require explicit design.

## 8. Comparing Across Different Business Scenarios

### Scenario A — Equipment Catalog

Requirement: admins update equipment names, descriptions, categories, and rental availability; users search filtered lists. Changes rarely affect past contract decisions.

**Initial choice:** state-first with `equipment` and appropriate keys/constraints. Add auditing if tracking who edited fields is needed. Event sourcing an entire catalog usually adds complexity without commensurate value.

Exception: if historical prices and rental terms govern historical contracts, **version price tables or store price/policy snapshots at signing time**. Even then, the catalog does **not** need to become an event-sourced aggregate.

### Scenario B — Application Configuration Changes

Requirement: only the active configuration is needed, with rollback to recent versions and controlled deployments.

**Choice:** state or versioned configuration documents with author/version/approval metadata. Rollback is solved by versioned state; there is no need to model every edit as a domain event.

### Scenario C — Complex Contract Lifecycle

Requirement: multiple extensions, fee adjustments, inspections, deposit refunds, disputes; may need to explain pre- and post-adjustment history and rebuild reports under published rules.

**Choice:** consider event sourcing for `Rental` or `BillingLedger` if the event sequence and replayability deliver real value. If only a few confirmation milestones and fast status lookups are needed, `rental_contract + domain events/audit + outbox` may be simpler.

### Scenario D — Recording Money and Financial Obligations

Requirement: account for every capture, refund, adjustment, provider reconciliation, and distinguish receivables from actual cash received.

**Choice:** an **immutable double-entry or full-entry ledger** is a key foundation. The ledger can serve as the financial source of truth alongside state-first contracts and integration events. Event sourcing can fit at appropriate boundaries, yet **never assume one `PaymentCaptured` row equals a complete accounting entry** or that every aggregate needs event sourcing.

### Scenario E — Syncing to an Analytics Warehouse

Requirement: sync order/customer tables for reporting without reconstructing operational state from historical events.

**Choice:** CDC or ETL/ELT pipelines handling initial snapshots, upserts/deletes, keys, and schema evolution. A CDC record describes a storage operation, **not** a confirmed business occurrence. When reports require “confirmed delivery success”, draw verified business events/evidence from an authoritative source.

## 9. Hybrid Strategy: Choose Models per Business Boundary, Not System-Wide

A real system might combine:

- `EquipmentCatalog` storing current state.
- `Rental` using event sourcing if contract lifecycles require rebuilds.
- `Payment` storing transactions and a ledger under strict financial constraints.
- `CRM` consuming integration events under stable contracts rather than reading internal tables directly.
- `Analytics` ingesting business events or CDC with clear deduplication and time rules.

~~~mermaid
flowchart LR
    CAT[("Equipment Catalog: state")] --> API["Rental workflow"]
    API --> EV[("Rental event store")]
    EV --> RP[("Rental read model")]
    EV --> OUT["Outbox / publisher"]
    OUT --> MSG["Integration contracts"]
    PAY[("Payment / ledger")] --> OUT2["Payment publisher"]
    OUT2 --> MSG
    MSG --> CRM["CRM"]
    MSG --> AN["Analytics"]
~~~

The diagram depicts **one logical layout**, not a single shared transaction spanning all databases. Payment/refund facts are recognized by `Payment` as authoritative source; `Rental` must ingest that outcome via a contracted, idempotent workflow rather than assuming “refunded” the moment a request goes out.

### Source-of-Truth Boundaries Must Be Written Into Contracts

| Concept | Authoritative source | Places holding derived copies only |
| --- | --- | --- |
| Equipment names and specs | EquipmentCatalog. | Display details in contracts, caches, search. |
| Rental progression and inspection | Rental aggregate/event store (if event sourced). | `rental_current`, timelines, dashboards. |
| Actual capture/refund | Payment/ledger and provider confirmation. | Payment status cached in Rental, CRM, reports. |
| Late-return metrics | Business events/sources + versioned KPI definitions. | Analytical summary tables. |

When an external system delivers data late, every party must separate **source truth**, **received message**, and **projected state**. Hybrid design limits complexity scope without eliminating integration challenges.

## 10. Consistency Rules and Concurrent Updates Determine Model Boundaries

A more important question than architecture buzzwords is: **which invariants must hold immediately inside a transaction?**

| Invariant | Example | Required enforcement point |
| --- | --- | --- |
| Do not inspect-accept the same equipment twice in one rental | Two staff click accept simultaneously. | Lock/version and preconditions on Rental, plus command idempotency. |
| Do not refund more deposit than captured | Two competing refund requests. | Obligation/ledger source, balance check, and suitable transaction locking. |
| Do not sell the same seat to two people | Two different Bookings select the same seat. | Unique constraint/lock/reservation at the seat-inventory source, not just per-Booking locks. |
| Do not re-trigger an external side effect causing double capture | Callback or API retry. | Provider-level idempotency key and internal deduplication. |

**Event sourcing does not automatically solve cross-aggregate invariants.** When multiple bookings share inventory, having separate event streams per `Booking` cannot prevent double-booking a seat; you need a shared inventory/seat owner or constraint/transaction at a common consistency point.

Regardless of state-first or event-first, you must handle:

1. **Concurrent commands:** version compare-and-swap, appropriate locking, or suitable transaction isolation.
2. **Same-request retries:** scoped idempotency keys and clear response policies.
3. **External side effects:** write intent to an outbox before sending, and reconcile outcomes before declaring success.
4. **Duplicate/out-of-order messages:** consumer deduplication and version/state preconditions.
5. **Late-arriving data:** separate occurrence time, recording time, and processing time.

### Choosing Event Sourcing Just to “Avoid Lost Updates” Misses the Point

Both state-first and event sourcing can use optimistic concurrency. `UPDATE state WHERE version = expected` and `append event WHERE current_stream_version = expected` both resolve local write contention when transactions are designed right. The distinct value of event sourcing is **business history as the source of truth**, not a magical locking trick.

## 11. Time, Corrections, and Interpreting Historical Data

State models make “what is the value **right now**?” easy. Event models shine at answering “**why** did that state form?” provided time is modeled explicitly.

A due-date correction case:

- 10:00: contract records due time as 10:00.
- 10:30: customer hands over equipment.
- 11:00: system assesses a late fee based on the stored due time.
- 12:00: manager approves an adjustment proving the valid due time was 11:00.

At least two views exist:

- **What the system knew at 11:00:** due time 10:00 and a late fee assessed.
- **What is recognized after adjustment:** due time 11:00 and the late fee may require reversal.

With state-first, update `due_at = 11:00` and record audit/correction records. With event sourcing, append `RentalDueDateCorrectionApproved` and `LateFeeAssessmentReversed` per business rules. **Regardless of model**, if cash was already collected, reversing a receivable does not automatically refund money; an actual refund action and confirmation event are still required.

Fields to keep distinct:

| Field | Meaning |
| --- | --- |
| `occurred_at` | When the occurrence happened per an authoritative source. |
| `recorded_at` | When the system persisted the occurrence. |
| `effective_at` | When the value/adjustment takes effect if different from recording time. |
| `stream_version` | Accepted logical order of events inside one stream, not calendar time. |

An event with an older `effective_at` is still appended at a new stream version. Answering both “what did the system know at time X?” and “what facts are recognized as effective at time X?” requires explicit temporal rules—possibly a **bitemporal model**. Switching from a state table to an event log does not automatically make historical queries right.

## 12. Performance, Queries, and Operational Cost

A common oversimplification claims “state is fast, events are slow”. That is inaccurate across real workloads.

**State-first** fetches current state with a primary-key lookup; for long histories, it still has to query audit logs. **Event sourcing** serves UI screens very quickly through tailored read models; latency depends on how projectors update and freshness guarantees. Conversely, rebuilding an aggregate by replaying thousands of events per command is expensive without snapshots and optimization.

| Dimension | State-first | Event sourcing |
| --- | --- | --- |
| Reading current state | Read authoritative row/document. | Read projection or snapshot + tail events. |
| Writing a change | Update state plus optional audit/outbox. | Append event, guard version, optionally update projection/outbox. |
| Querying history | Depends on completeness of audit/history. | Query semantic events; still needs dedicated schemas/indexes/read models. |
| Changing report formulas | Migrate or reprocess retained data. | Replay events if history and compatible readers exist. |
| Data evolution | Migrate current rows; version audits if needed. | Maintain multiple event schemas, upcasters/reducers/snapshot versions. |
| Operations and monitoring | Transactions, backups, indexes, audit/outbox if used. | Also replay, snapshots, projector lag, checkpoints, rebuilds, and drift. |
| Privacy | Govern current data/audits/backups. | Also govern append-only event history and derived copies. |

Never draw conclusions from unmatched benchmarks. A meaningful evaluation uses identical query and invariant requirements:

1. Build realistic datasets for aggregate counts and events/rows per aggregate.
2. Measure **P50/P95/P99** latency for state loading, command handling, and list/summary queries.
3. Simulate concurrent writes to measure conflict rates, retries, lock wait times, and error rates.
4. For event sourcing, measure projection lag, snapshot overhead, full replay, and read-model rebuild times.
5. Evaluate storage footprint, index counts, backup/restore times, operational burden, and schema-change frequency.
6. Compare against **real SLOs**, not just demo execution times.

Event sourcing is not automatically cheaper as data grows; neither is state-first automatically simpler if you end up hand-building rich history, strict audits, and multiple integration pipelines.

## 13. Rebuildability, Privacy, and Limits of “Append-Only”

“Rebuildable from events” is a conditional promise:

- Historical events must be **complete, semantically accurate, and properly ordered**.
- Readers must still understand old `event_type + schema_version` payloads.
- Reducers must be deterministic—never calling external APIs or reading live price tables to re-decide the past.
- Compatible snapshots are only starting checkpoints, not replacements for raw events when projections need granular history.
- Policy-driven erasure/anonymization can bound replayability; disclose and design for this upfront.

An append-only log does not mean data may be kept forever regardless of policy. Events can hold customer names, payment references, or sensitive attributes that should not be replicated to every consumer. Whichever model you choose, clarify:

- Who may read/write/edit/delete data; are permissions enforced at both application and database layers?
- Where does personal data live across state, events, audits, outboxes, projections, backups, and logs?
- Do retention, erasure, and anonymization policies align with legal mandates and recovery capabilities?
- What tamper-evidence controls are needed: access audits, backups, hash chains/signatures, and key management?
- Do schema migrations preserve historical semantics and prevent silent shifts in published KPIs?

If events cannot be retained intact long term, separate PII from events, store reference IDs, define key-destruction/anonymization policies, or narrow event sourcing's scope. No single trick can erase every sensitive trace while preserving full unrestricted replay without trade-offs.

## 14. Scoring Options With Evidence, Not Preference

Use a **decision scorecard** per bounded context. Scores are a discussion aid, not an automated formula to pick an architecture.

| Criterion | 0 = minimal/not needed | 1 = moderate | 2 = core requirement |
| --- | --- | --- | --- |
| Need to recover state via replay | Not needed. | Useful in a few cases. | Mandatory for operations/analytics. |
| Semantically meaningful history | Only latest state matters. | Some milestones must be kept. | Every major decision/transition is core data. |
| Need multiple historical projections | Reports rarely change. | A few views needed. | Frequent recomputations under new definitions. |
| Hard to prove correctness from state alone | Invariants fit constraints easily. | Some decisions need trails. | Event sequence and proof govern correctness. |
| Capacity to operate event sourcing | Not yet available. | Ready for small pilot. | Team and tooling exist for replay/rebuild/monitoring. |

**How to interpret:** high scores across the four demand criteria justify **evaluating event sourcing**, while a low operational-readiness score signals a risk to address—not a reason to inflate points. Even when total score is “high”, non-negotiable constraints like privacy, compliance, or cross-system transactions must still be solved explicitly.

### Sample Decision

For `Rental` with requirements: customers view instant status; operations needs extension/inspection history; accounting needs deposit-refund reconciliation; audit mandates 5-year evidence retention; only a handful of events per contract; team lacks replay infrastructure.

You might start with **state + domain history + audit/outbox** because:

- Current state is the primary query.
- History must be retained, yet reconstructing all state from events is not required.
- Transition counts are low, so snapshot/replay performance gains are minor.
- The team can cleanly manage transactions and well-keyed history tables.

If future requirements demand recomputing multiple projections from complete history and standardized semantic events, you can evaluate **event sourcing for that specific sub-domain**. There is no need to declare a whole-system rewrite.

### What Should a Decision Artifact Contain?

A concise **Architecture Decision Record (ADR)** should document: business requirements, source of truth, invariants, aggregate scope, evaluated alternatives, benefits/costs, SLOs, retention, risks, migration plan, re-evaluation triggers, and verification tests. That way, even as team members change, the rationale remains grounded.

## 15. Migrating Between Models: Avoid Fake History or Dual Sources of Truth

### From State-First to Event Sourcing

This is not merely “create an event table and dump every state row as past events”.

1. **Define boundaries** of the aggregate/source of truth being migrated. Do not convert unrelated tables just for technological uniformity.
2. **Define event contracts** with business confirmation points, keys, versions, timestamps, and schema policies.
3. **Inventory existing history.** If only current state exists, you cannot know every past event that occurred. Create an **initialization/baseline event** meaning “this is the state at cutover” or a well-sourced snapshot; **never fabricate fake prior business events**.
4. **Pick a controlled source-of-truth cutover point.** Never let state and event store accept independent authoritative writes long-term without proving consistency.
5. **Execute consistent sync/migration:** handle writes occurring during copy via a commit-ordered cursor or a guarded, reconcilable dual-write bridge.
6. **Build read models, verify, and cut over.** Reconcile cutover state against legacy data, and test concurrency, idempotency, and rollback.

If historical events are reconstructed from high-quality audit logs, verify semantics, ordering, missing records, and transformation rules. CDC of a row after multiple updates cannot reconstruct past business occurrences if the original facts were never captured.

### From Event Sourcing to State-First

Sometimes **simplification** is warranted: event sourcing imposes operational overhead disproportionate to current needs.

1. Establish state at a cutover checkpoint and conversion rules for all relevant events.
2. Build the new state table and verify via replay/reconciliation.
3. During transition, process newly arriving events so no changes are lost.
4. Declare explicitly which state becomes authoritative after cutover.
5. Retain or archive raw events per audit, compliance, and lookup mandates; never delete history merely because writes stopped reading it.
6. Ensure downstream consumers previously reading event streams receive suitable replacement contracts.

**The most dangerous mistake is running two uncoordinated sources of truth.** If one service treats `rental_contract` as authoritative while another treats `rental_events` as authoritative and both write independently, recovery and conflict resolution become ambiguous.

## 16. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| “We need auditing, so we must use event sourcing.” | Change audits may suffice; event sourcing is warranted only when events are the source of truth and replay adds value. |
| “Using Kafka means we already have event sourcing.” | Kafka may only transport integration events while state tables remain the source of truth. |
| “Every UPDATE in CDC is a domain event.” | CDC captures storage mutations; it does not know business intent or confirmation milestones. |
| “Event sourcing is always faster than CRUD.” | Loading state may need replay/snapshots; reads need projections. Always benchmark your workload. |
| “Event sourcing solves exactly-once.” | Retries and duplicate messages still happen; idempotency, transactions, and reconciliation remain essential. |
| “Append-only means you never need corrections.” | You need business-meaningful corrections, reversals, compensations, and data governance policies. |
| “Once you have snapshots, delete all old events.” | Snapshots do not replace granular history for audits and new projections. |
| “Updating JSON schema alone guarantees compatibility.” | You must also preserve old event meaning, readers/upcasters, and consumer contracts. |
| “Every bounded context must share one model.” | Hybrid models aligned to domain boundaries are usually more practical. |
| “Splitting aggregates smaller for throughput is always safe.” | Wrong boundaries can break cross-stream invariants. |

## 17. Design Exercise: Choosing Approaches for Three Domains in One System

**Scenario:** an event ticketing and management platform has three requirement groups.

**Group A — Event Catalog:** admins update event names, descriptions, banners, and listed prices; admins want to know who changed prices. Users need fast search across on-sale events.

**Group B — Bookings and Seats:** customers hold seats, pay, cancel, and swap seats. Two customers can compete for the same seat; payment callbacks can arrive late or duplicated. Support wants to view booking progression and disputes.

**Group C — Payments and Reconciliation:** handles captures, partial refunds, failed refunds, provider fees, and daily cash-flow reports. Reconciliation requires provider evidence, lossless history, and rebuildable reports.

### Practice Tasks

1. **Choose a distinct source of truth** for A, B, and C: state-only, state + audit/outbox, event sourcing, ledger, or hybrid. State **reasons rooted in requirements**, not technology preference.
2. **Identify aggregates and invariants:** `SeatInventory` or `SeatReservation` must prevent selling the same seat twice; `Booking` can hold its own version. Explain why locking one booking alone cannot protect all seats.
3. **Design keys and schemas:** specify PKs, FKs, UNIQUE constraints, and indexes serving Catalog, Booking, and cash-flow queries. Propose a transaction pattern checking seats and recording consistent results.
4. **Audit trails:** distinguish price-change audits, domain event `BookingCancelled`, notification integration events, and Catalog CDC sync.
5. **Money handling:** describe `RefundRequested` and `RefundConfirmed` milestones; never credit refunded totals on request submission; handle provider timeouts via reconciliation.
6. **Integration:** propose outbox and idempotency keys when Booking must notify email or Payment; separate committed outcomes from processed messages.
7. **History and KPIs:** define “cancellation rate”, “gross captures”, “total refunds”, and “net cash”; choose authoritative sources and late-event handling.
8. **Performance:** state expected workload and P95/P99 measurements, seat-contention bottlenecks, projection lag, index overhead, and rebuild costs.
9. **Data governance:** specify where personal data lives; decide what happens to audits/events/outboxes/backups under retention or erasure requests.
10. **ADR:** write a one-page decision record per domain, including rejected alternatives and triggers to revisit the choice.

### Self-Assessment Checklist

| Check | Passing criterion |
| --- | --- |
| **Source of truth** | Each domain has one clear authoritative source, never two independent writers. |
| **Invariants** | Never holds/sells one seat twice; refunds never exceed valid captures and reconcile cleanly. |
| **Semantics** | Clearly separates current state, domain facts, audits, CDC, and integration events. |
| **Concurrency** | Transactions/locking/versioning/idempotency resolve competing commands and retries. |
| **Historical data** | Answers committed historical questions without fabricating history from current state. |
| **Queries** | Keys, indexes, and read models align with real query patterns and SLOs. |
| **Evolution** | Has schema/version/migration plans and verified cutovers when changing sources of truth. |
| **Operations/privacy** | Covers backups, monitoring, error handling, and compliant retention. |

**Conclusion:** choosing a state model or an event model is deciding **where to place the source of truth and what must be recoverable, explainable, and verifiable**. State-first fits when current values are primary data; state + audit/outbox fits when traceability and integration are needed without replay; event sourcing is worth considering when meaningful progression is primary data requiring long-term retention and rebuildability. A bounded-context hybrid design usually meets requirements at more sensible cost than forcing one model across the entire system.
