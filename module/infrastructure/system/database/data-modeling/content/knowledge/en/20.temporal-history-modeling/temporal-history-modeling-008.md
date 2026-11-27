# Distinguishing Audit Trails, Business History, and Domain Event Logs

## 1. Three Kinds of “History” Data Solve Three Different Questions

In the **DATABASE_DATA_MODELING** module, modeling history is never as simple as adding a table ending in **_history**. When translating business requirements into entities, relationships, keys, constraints, indexes, and physical schemas, you must first identify **which kind of past question the system needs to answer**.

Suppose a customer switches plans from **BASIC** to **PRO**. The exact same change can trigger three distinct questions:

1. **Who changed the plan, which API was called, when, and with what outcome?** This is a question for an **audit trail**.
2. **Was the customer entitled to PRO on March 5 under business rules?** This is a question for **business history** (*business/valid-time history*).
3. **Which business events occurred in sequence to produce the current state?** This is a question for a **domain event log** (which may serve as the source for event sourcing).

All three datasets can coexist, yet **they cannot substitute for one another by default**.

For example, an audit record stating “admin updated `plan_code` from BASIC to PRO on Mar 10” **does not reveal whether PRO took effect on Mar 1 or Mar 10** unless validity rules are persisted separately. A history row stating **PRO effective from Mar 1** does not necessarily tell which admin triggered it or via which API. A **PlanChangeApproved** event may confirm an upgrade decision was approved, without automatically proving the entitlement service succeeded in applying it.

This lesson belongs to the **Time and History** chapter and focuses on separating the purpose, semantics, and responsibilities of these three data categories, then coordinating them without creating three conflicting “sources of truth.”

**Learning objectives:** learners can distinguish audit, history, and domain events; design proper schemas and constraints for each; handle atomicity between business changes and history writes; write appropriate queries; and recognize when bitemporal modeling, CDC, outbox, or event sourcing is required.

## 2. Core Concepts and Scope of Each Category

### 2.1. Audit Trail

An **audit trail** records **traces of actions or decisions executed against the system**. The subjects being traced are typically **actions by users, services, background jobs, or administrative accounts**.

An audit record may capture:

- **Who:** `actor_id`, `actor_type`, service account, or authenticated principal.
- **What:** action, operation, command, or state transition.
- **On what:** `entity_type`, `entity_id`.
- **When:** `accepted_at` or `recorded_at` from a defined time source.
- **From where and how:** `request_id`, `trace_id`, `client_application`, and network/origin context where policy allows.
- **Before/after:** before/after values of allowed fields or a structured diff.
- **Why:** `reason_code`, `ticket_id`, `approval_ref`.
- **Outcome:** succeeded, rejected, failed, or final state of an async workflow.

Auditing supports investigations, accountability, unauthorized-action detection, permission reviews, and process controls. It can be **business append-only**, protected from arbitrary edits or deletes. However, simply having an audit table **does not automatically prove logs are tamper-proof**: tamper resistance requires access controls, separation of duties, protected storage, checksums/signatures, or equivalent safeguards calibrated to risk.

### 2.2. Business History

**Business history** records **the state, attribute value, or relationship considered true during a business period**.

Example:

~~~text
Customer 501, subscription plan:

[2026-01-01, 2026-03-01)  BASIC
[2026-03-01, unbounded)   PRO
~~~

It answers queries like: **“Which plan was effective on March 5?”** The answer is PRO, provided historical data reflects confirmed facts.

History can store:

- Attribute versions of an entity, such as plans, prices, staff grades, or contract statuses.
- Relationship versions, such as which department an employee belonged to, or which permission groups a user held.
- Effective intervals **[valid_from, valid_to)**.
- Decision sources, versions, and non-overlap constraints.

If you also need to answer **“on March 8, what had the system recorded for March 5?”**, a single valid-time axis is insufficient. You then need **bitemporal history** or an event source complete enough to reconstruct system knowledge over time.

### 2.3. Domain Event Log

A **domain event log** records **events meaningful in the business domain**, for example:

- **SubscriptionActivated** — service subscription activated.
- **PlanChangeApproved** — plan switch decision approved.
- **InvoiceIssued** — invoice issued.
- **PaymentCaptured** — payment successfully captured.
- **RefundAuthorized** — refund approved.

An event represents a **fact about something that happened**, named in the past tense, carrying an event identity, event type, schema version, subject references, stream sequence or version, business payload, and originating source.

In event sourcing, the event log is the **source of truth** and current state is derived by replaying ordered events. Yet **not every system with an event table is doing event sourcing**. If a subscription table remains the source of truth and events are emitted merely to notify downstream services, the event log serves integration or business messaging rather than full state reconstruction.

### 2.4. Further Distinction from Technical Logs and CDC

Two other mechanisms are often loosely lumped under “history”:

- **Application/technical logs:** record stack traces, latency, requests, health checks, connection errors, and metrics. They aid operations, yet usually lack data constraints and durability required for business history.
- **CDC — Change Data Capture:** captures database changes via DBMS/tooling mechanisms, usually from transaction logs. CDC knows which rows/columns changed, yet **does not intrinsically know the business meaning** of the change if source tables omit decisions and effective dates.

CDC can **transport** changes to build history, sync warehouses, or emit integration events. Never blindly call every CDC record a domain event: **UPDATE plan_code** differs semantically from **PlanChangeApproved**.

## 3. Comparison by Question and Data Guarantee

| Criterion | Audit Trail | Business History | Domain Event Log |
|---|---|---|---|
| **Primary question** | Who did what, when, with what outcome? | Which value/relationship held true at business time B? | Which domain events occurred, and in what order? |
| **Data unit** | An action, decision, attempt, or observed operation | A value/relationship version with an effective interval | An accepted domain event |
| **Typical time axes** | Recording/execution time | Valid time; optionally known time | Event time, recording time, stream order |
| **Identity/keys** | `audit_id`, actor, request/transaction ID | `entity_id`, `version_id`, `valid_period` | `event_id`, `aggregate_id`, `aggregate_version` |
| **Updates/corrections** | Typically append new trace, never delete old trace | Close/split intervals; bitemporal if knowledge history needed | Append corrective/cancelling/compensating event; replay or update projection |
| **Typical queries** | By actor, action, entity, request, recording window | As-of B, timeline, temporal join | By aggregate, event version, event type |
| **Self-reconstructs state?** | Not guaranteed | Returns state within designed scope | Possible, **only when** events are complete and replay is deterministic |
| **Proves action execution?** | Primary goal if designed reliably | Reflects only effective values | Proves event acceptance; not necessarily every attempt |
| **Typical risks** | Missing logs, leaked PII/secrets, unclear outcomes, tampering | Overlaps/gaps, retroactivity, lost prior history | Lost ordering, duplicate emission, insufficient payload, replay semantic drift |

**One action can produce all three records**, yet each models a distinct aspect. You do not need three identical copies of data just “to be safe.” Instead, designate the **authoritative source**, each table's responsibility, and reconciliation checks.

## 4. Running Example: A Retroactive Decision

Suppose customer **501** is on BASIC starting 2026-01-01. Billing computes charges from plan entitlements. On **2026-03-10 at 09:00 UTC**, agent CS-17 enters an approved decision: customer switches to PRO **effective March 1**.

Later, on March 12, an operations clerk notices the reason note was incomplete and submits an amendment updating the notes. The effective date of PRO **does not change**.

### 4.1. Audit Records the Action

An audit record might look like:

~~~json
{
  "auditId": "audit-001",
  "actorType": "USER",
  "actorId": "CS-17",
  "action": "CHANGE_SUBSCRIPTION_PLAN",
  "entityType": "CUSTOMER_SUBSCRIPTION",
  "entityId": "501",
  "requestId": "req-710",
  "decisionRef": "APPROVAL-77",
  "recordedAt": "2026-03-10T09:00:00Z",
  "outcome": "SUCCEEDED",
  "change": {
    "fromPlan": "BASIC",
    "toPlan": "PRO",
    "effectiveFrom": "2026-03-01"
  }
}
~~~

Audit answers **who performed the action**, **what they did**, **which object**, and **on what basis**. It does not define the complete historical plan timeline if before/after states or effective intervals are incomplete.

### 4.2. Business History Represents Effective Entitlement

After the operation, plan history per latest knowledge is:

~~~text
Customer 501:
  BASIC: [2026-01-01, 2026-03-01)
  PRO:   [2026-03-01, +∞)
~~~

For **B = 2026-03-05**, the result is **PRO**. If asked **“what did the system know on March 8 about March 5?”**, the pre-change answer was **BASIC**, assuming before March 10 the system still recorded BASIC as effective from the start of the year. Proving both slices requires storing **known/system time** or an event history sufficient to reconstruct knowledge.

### 4.3. Event Log Records the Domain Event

A domain event:

~~~json
{
  "eventId": "evt-501-2",
  "aggregateType": "SUBSCRIPTION",
  "aggregateId": "501",
  "aggregateVersion": 2,
  "eventType": "PlanChangeApproved",
  "schemaVersion": 1,
  "recordedAt": "2026-03-10T09:00:00Z",
  "decisionRef": "APPROVAL-77",
  "payload": {
    "newPlan": "PRO",
    "validFrom": "2026-03-01"
  }
}
~~~

The event records **an accepted business occurrence** carrying the effective date needed by projection builders. It does not necessarily include the actor or full security context like audit does; link them when needed via **decisionRef/correlationId**.

### 4.4. One Question, Three Different Query Sources

| Questioner | Question | Preferred Source |
|---|---|---|
| Compliance team | Who changed the plan at 09:00 on Mar 10, via which request? | Audit |
| Billing team | Which plan was effective on Mar 5 per currently accepted decisions? | Business history |
| Platform team | Which events changed subscription state along the stream? | Event log |
| Customer support | When the Mar 8 invoice was generated, which plan did the system know then? | Bitemporal/known-time history or reliable replay |
| Access investigation team | Did the customer actually open PRO content on Mar 6? | Access log or dedicated behavioral evidence |

The last row is critical: **entitlement that should have been effective** does not prove the application actually granted access or the customer used the feature. Each question requires the right kind of evidence.

## 5. Audit Trail Model: Recording Verifiable Activity

A solid audit trail supports queries like:

- “Over the past 30 days, who changed product 900's price?”
- “What did request `req-710` do, and was it accepted?”
- “Who granted ADMIN role to account X, and under which approval?”
- “Were any unauthorized deletes or access attempts rejected?”
- “Which operation reverted this change?”

Answering these requires **structured logs** rather than free-text lines like “user updated customer.”

### 5.1. Fields to Consider

| Group | Example Fields | Notes |
|---|---|---|
| Actor identity | `audit_id`, `actor_id`, `actor_type` | Humans, service accounts, and jobs carry distinct semantics |
| Subject | `entity_type`, `entity_id`, `tenant_id` | Guard multi-tenant queries |
| Action | `action`, `command_type`, `outcome` | Never overload one vague action across unrelated operations |
| Correlation | `request_id`, `correlation_id`, `trace_id` | One request may emit multiple audit records |
| Time | `recorded_at`, `attempted_at` | Log recording time differs from business effective time |
| Origin | `client_app`, `operation_source` | Avoid logging secrets or network addresses needlessly |
| Evidence | `before_data`, `after_data`, `diff`, `decision_ref` | Log only minimum permitted fields |
| Status | `SUCCEEDED`, `REJECTED`, `FAILED` | Define when status becomes final |

**A failed attempt** and **a committed change** are different objects. Writing audit inside the same transaction as the business update makes both commit or roll back together. Yet if a command is rejected before or rolls back the transaction, an in-transaction audit record disappears too. Recording rejected access attempts often requires a **separate security audit stream** outside the business transaction.

### 5.2. Illustrative Audit Schema in PostgreSQL

~~~sql
CREATE TABLE audit_activity (
    audit_id         uuid PRIMARY KEY,
    tenant_id        bigint NOT NULL,
    actor_type       text NOT NULL,
    actor_id         text,
    action_code      text NOT NULL,
    entity_type      text NOT NULL,
    entity_id        text NOT NULL,
    outcome          text NOT NULL
                     CHECK (outcome IN ('SUCCEEDED', 'REJECTED', 'FAILED')),
    request_id       text NOT NULL,
    decision_ref     text,
    diff_data        jsonb,
    recorded_at      timestamptz NOT NULL DEFAULT statement_timestamp()
);

CREATE INDEX ix_audit_entity_time
    ON audit_activity (
        tenant_id, entity_type, entity_id, recorded_at DESC
    );

CREATE INDEX ix_audit_actor_time
    ON audit_activity (
        tenant_id, actor_type, actor_id, recorded_at DESC
    );
~~~

**audit_id** identifies the record. Do not mechanically put UNIQUE on **request_id**: a single request can trigger multiple auditable operations. **diff_data** must contain only permitted fields. Never write passwords, access tokens, secret keys, payment card details, or unnecessary personal data into audit logs.

This table illustrates **data structure**; it does not by itself satisfy every audit compliance mandate. If operators hold direct database write privileges, enforce write/delete restrictions, stream audit logs to isolated storage, or add tamper-evidence controls. Also verify whether `recorded_at` from `statement_timestamp()` satisfies temporal analysis needs—it is not exact commit time.

### 5.3. Diff-Based Audits Must Carry Semantics

A diff showing **fromPlan = BASIC, toPlan = PRO** captures a column change accurately, yet if a record is **re-normalized**, identical values can represent different decisions.

For instance, a retroactive PRO decision from Mar 1 is corrected to PRO from Mar 5; **`plan_code` did not change**, only **`valid_from`** changed. An audit diff inspecting only `plan_code` would miss a crucial change.

Thus audits must track **fields and decisions that matter to the business**, not merely convenient DTO columns. For soft deletes, explicitly record the transition to `DELETED` rather than conflating it with physical deletion.

## 6. Business History Model: Storing Values by Effective Interval

Business history answers different questions from audit:

- “Which plan did customer 501 belong to on March 5?”
- “Which price applied during Mar 1–Mar 31?”
- “Which department did the employee belong to on February 15?”
- “Were two values simultaneously effective at a given instant?”

Records need an **entity key**, **version value**, **effective interval**, **decision source**, and **non-overlap invariants** scoped to business rules.

### 6.1. Using Half-Open Intervals

~~~text
[valid_from, valid_to)

BASIC: [2026-01-01, 2026-03-01)
PRO:   [2026-03-01, +∞)
~~~

March 1 belongs to PRO, not BASIC. Half-open intervals eliminate “subtract one second” hacks at transition boundaries and work consistently for both dates and timestamps when appropriate types are chosen.

If plans apply by **calendar date in a market**, `date`/`daterange` fits well. If validity requires sub-day precision, use `timestamptz`/`tstzrange` with explicit time zone rules.

### 6.2. History Schema with a Single Valid-Time Axis

~~~sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE subscription_plan_history (
    plan_version_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id     bigint NOT NULL,
    plan_code       text NOT NULL,
    valid_period    daterange NOT NULL,
    decision_ref    text NOT NULL,

    CONSTRAINT ck_subscription_valid_interval
        CHECK (
            NOT isempty(valid_period)
            AND NOT lower_inf(valid_period)
            AND lower_inc(valid_period)
            AND NOT upper_inc(valid_period)
        ),

    CONSTRAINT ex_subscription_one_plan_at_a_time
        EXCLUDE USING gist (
            customer_id WITH =,
            valid_period WITH &&
        )
);
~~~

The **EXCLUDE** constraint forbids two versions for the same customer from overlapping in valid time, assuming at most one primary plan per customer per day. If customers may hold multiple plan types simultaneously (such as BASE and ADDON), add **plan_kind** or the proper scope key rather than blocking valid data.

**Exclusion constraints guarantee at most one**, not **always one**. If subscriptions must remain gapless across a contract term, check for **gaps** against active contract dates.

### 6.3. Data and As-Of Query

~~~sql
INSERT INTO subscription_plan_history (
    customer_id, plan_code, valid_period, decision_ref
)
VALUES
(
    501, 'BASIC',
    daterange(DATE '2026-01-01', DATE '2026-03-01', '[)'),
    'REGISTRATION-501'
),
(
    501, 'PRO',
    daterange(DATE '2026-03-01', NULL, '[)'),
    'APPROVAL-77'
);

SELECT plan_code, decision_ref
FROM subscription_plan_history
WHERE customer_id = 501
  AND valid_period @> DATE '2026-03-05';
-- PRO
~~~

This is an **as-of query at business date B**. The table cannot answer “before the decision was entered, what did the system believe about date B?” if it stores only the latest accepted effective timeline without a knowledge-history layer.

### 6.4. Relationship History Also Requires Versions

If an employee is assigned:

~~~text
Employee 42 -- Department A: [Jan 1, Apr 1)
Employee 42 -- Department B: [Apr 1, +∞)
~~~

then history belongs on the **Employee–Department relationship**, not only on employee attribute columns. An employee can join multiple projects in parallel, so overlap constraints should key on **employee_id + project_id + relationship kind** where appropriate rather than forbidding all concurrent links.

When joining attribute history and relationship history, verify both versions **simultaneously contain date B**. Joining by ID alone without temporal filtering can pair values that were never true together.

## 7. Business History and Bitemporal: What Was True vs. What Was Known?

An easily overlooked case:

- Before Mar 10, the system recorded customer 501 on BASIC from Jan 1 onward.
- On Mar 10, the system receives a PRO decision effective retroactively from Mar 1.

There are two answers for **B = Mar 5**:

| Knowledge Evaluation Time K | What the System Believed About B = Mar 5 |
|---|---|
| K = Mar 8 | BASIC |
| K = Mar 12 | PRO |

History storing only **valid_period** per latest knowledge returns PRO and loses the fact that on Mar 8 the system believed BASIC.

**Bitemporal** adds a second axis **known_period = [known_from, known_to)**:

~~~text
BASIC: valid [Jan 1, +∞)
       known [Jan 1 08:00, Mar 10 09:00)

BASIC: valid [Jan 1, Mar 1)
       known [Mar 10 09:00, +∞)

PRO:   valid [Mar 1, +∞)
       known [Mar 10 09:00, +∞)
~~~

Two versions can overlap in **valid time** while staying disjoint in **known time**, because they belong to different knowledge eras.

The conceptual PostgreSQL constraint sketch is:

~~~sql
EXCLUDE USING gist (
    customer_id WITH =,
    valid_period WITH &&,
    known_period WITH &&
)
~~~

It rejects two rows for the same `customer_id` only when they overlap in **both valid and known periods**—a distinct rule from a valid-time-only table.

**Known time is not automatically commit time** when timestamps are application-managed. Define the recording point clearly and ensure all interval close/open operations within one transaction share one logical cutover. When proving exact committed transaction state at arbitrary instants, stricter DBMS system-time mechanisms are required.

## 8. Domain Event Log: Modeling What Happened Instead of Column Edits

Well-designed events use names expressing **domain occurrences**:

~~~text
SubscriptionActivated
PlanChangeRequested
PlanChangeApproved
PlanChangeRejected
InvoiceIssued
RefundApproved
~~~

Each carries distinct semantics:

- **PlanChangeRequested:** customer submitted a request, not yet approved.
- **PlanChangeApproved:** decision approved, possibly with a future or retroactive effective date.
- **SubscriptionPlanBecameEffective:** a projection or workflow confirms the plan transitioned into effect, if modeled as its own domain event.
- **InvoiceIssued:** document issued, distinct from “API received invoice generation request.”

Event names alone are insufficient: define **emission preconditions**, **payloads**, **authority**, **ordering**, **idempotency**, and **retry semantics**.

### 8.1. Illustrative Event Store Schema

~~~sql
CREATE TABLE subscription_domain_event (
    event_id          uuid PRIMARY KEY,
    aggregate_id      bigint NOT NULL,
    aggregate_version bigint NOT NULL CHECK (aggregate_version >= 1),
    event_type        text NOT NULL,
    schema_version    integer NOT NULL CHECK (schema_version >= 1),
    event_payload     jsonb NOT NULL,
    decision_ref      text,
    occurred_at       timestamptz,
    recorded_at       timestamptz NOT NULL DEFAULT statement_timestamp(),

    CONSTRAINT uq_subscription_aggregate_version
        UNIQUE (aggregate_id, aggregate_version)
);

CREATE INDEX ix_subscription_event_type_time
    ON subscription_domain_event (event_type, recorded_at);
~~~

**aggregate_version** is the confirmed sequence within an **aggregate_id** stream, catching two writers attempting to append the next event concurrently. **event_id** uniquely identifies the event for deduplication. **schema_version** supports payload evolution.

Do not conflate **event_id** with **request_id**: one request can produce multiple events; conversely, one event can be delivered across a broker multiple times with the same `event_id`. Clearly define **occurred_at** and **recorded_at**, as neither necessarily equals commit time.

### 8.2. Example Subscription Event Sequence

~~~json
[
  {
    "aggregateId": 501,
    "aggregateVersion": 1,
    "eventType": "SubscriptionActivated",
    "schemaVersion": 1,
    "payload": {"plan": "BASIC", "validFrom": "2026-01-01"}
  },
  {
    "aggregateId": 501,
    "aggregateVersion": 2,
    "eventType": "PlanChangeApproved",
    "schemaVersion": 1,
    "payload": {"plan": "PRO", "validFrom": "2026-03-01",
                "decisionRef": "APPROVAL-77"}
  }
]
~~~

Both events describe **what happened along the stream**, yet building accurate effective history requires applying domain rules: when a plan switch is approved, keep BASIC up to before Mar 1 and start PRO on Mar 1. If an event arrives late with retroactive validity, the projection must re-split intervals.

**Event streams and business history are two representations of domain knowledge.** The stream can be the source of truth while history serves as an as-of-optimized projection—or history can be authoritative while events notify downstream consumers. Choose the direction of authority explicitly.

## 9. When Is an Event Log Sufficient to Reconstruct State?

**Event sourcing** stores accepted events as the authoritative source to rebuild state. Conceptually:

~~~text
state_0 = verified initial state

state_1 = apply(state_0, event_1)
state_2 = apply(state_1, event_2)
...
state_N = apply(state_(N-1), event_N)
~~~

Accuracy requires all of the following simultaneously:

1. **Complete events** from a verified baseline state through the target version.
2. **Deterministic ordering** within each aggregate or across required dependencies.
3. **Deterministic replay:** identical events and rule versions produce identical outputs.
4. **Self-contained semantic payloads** that do not depend on mutable current tables.
5. **Schema evolution** backward-compatible with historical events.
6. **Idempotency** when events are redelivered or reapplied.
7. **Correction workflows:** append compensating/corrective events and recompute projections rather than erasing past facts without evidence.

If you record `PlanChangeApproved` events while missing the initial activation event, or drop events during outages, full replay is impossible.

### 9.1. Event Logs Differ from Technical Change Logs

A technical change log says:

~~~text
UPDATE subscription SET plan = 'PRO' WHERE customer_id = 501
~~~

This fails to explain **why** it changed and **since when PRO took effect** if decision context is absent. A domain event:

~~~text
PlanChangeApproved(
    customerId=501,
    newPlan=PRO,
    validFrom=2026-03-01,
    decisionRef=APPROVAL-77
)
~~~

carries richer business semantics. Also note that **an event having occurred** does not guarantee every side effect succeeded: `PlanChangeApproved` does not prove a notification email was delivered. Tracking email delivery requires events/states from the messaging workflow itself.

### 9.2. Snapshots Only Accelerate Replay

If a stream holds millions of events, persisting a **snapshot at version N** speeds up reconstructing state N+K. Snapshots never replace events after N, nor guarantee state at an arbitrary wall-clock timestamp without a reliable time-to-version mapping.

Define **snapshot_version**, choose a baseline **<= target_version**, replay events in **(base_version, target_version]**, and check for missing events.

## 10. For the Same Decision, What Should Be Written Where?

For customer 501's upgrade, data may flow through:

~~~mermaid
flowchart TD
    A["Change-plan command + approved decision"] --> B["Business transaction"]
    B --> C["Active plan state/history"]
    B --> D["Audit of successful action"]
    B --> E["Outbound outbox event"]
    E --> F["Event publisher worker/broker"]
    F --> G["Projections, emails, reports"]
~~~

Arrows depict logical flow; **transactions** must have realistic boundaries. If history, success audit, and outbox live in the same PostgreSQL database, they can commit **atomically in one transaction**. Email delivery or another service's database cannot join that local transaction; they require retries, idempotency, and reconciliation.

### 10.1. Standard Transaction When History Is the Source of Truth

A common pattern:

1. Receive **ChangePlan** command with **command_id** and approval metadata.
2. Validate permissions, expected version, and effective date.
3. Lock the customer/subscription scope to prevent competing timeline writes.
4. Close/split valid-time history and insert appropriate versions.
5. Insert **SUCCEEDED** audit record with request/decision identifiers.
6. Insert **outbox event** with validated payload.
7. Commit atomically.
8. Outbox publisher delivers events, tracks progress, and retries on failure.
9. Consumers deduplicate idempotently; reconcile projections if publishing lags.

Rejected unauthorized attempts can be written to **security audit** outside the state-mutating transaction if security policies require keeping failed attempts.

**Avoid dual writes:** never commit history in database A and publish directly to broker B assuming “both will surely succeed.” The DB can commit while the broker fails, or the broker can receive the message before the DB rolls back. A transactional outbox bridges the gap between DB commit and message emission, though consumers must still handle duplicates.

### 10.2. Minimal Outbox Schema

~~~sql
CREATE TABLE domain_outbox (
    outbox_id    uuid PRIMARY KEY,
    aggregate_id bigint NOT NULL,
    event_type   text NOT NULL,
    payload      jsonb NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT statement_timestamp(),
    published_at timestamptz,
    attempts     integer NOT NULL DEFAULT 0 CHECK (attempts >= 0)
);

CREATE INDEX ix_domain_outbox_pending
    ON domain_outbox (created_at)
    WHERE published_at IS NULL;
~~~

A broker may accept an event right before the worker loses connection and fails to update **published_at**, causing redelivery. That is why consumers must deduplicate by `event_id`/`outbox_id`. Never assume **exactly-once end-to-end** simply because an outbox table exists.

When the **event store is the source of truth**, the transaction persists the event and corresponding audit, while business-history projections update asynchronously. APIs must then disclose **projection lag** and support rebuilds—never treat projections as a second competing authority.

## 11. Should Failed Operations Be Recorded?

Here, audit and event logs diverge sharply.

Suppose an unauthorized user submits a plan change:

- **Security audit** can record the **attempted action**, actor, target, request, rejection reason, and timestamp per security policy.
- **Business history** adds no new plan version, since the decision was rejected.
- **Domain event log** normally **has no PlanChangeApproved**. A distinct **PlanChangeRejected** event may exist if rejection is a meaningful domain workflow event, though not every validation error belongs in a domain event log.

When an async workflow spans minutes, **SUBMITTED**, **APPROVED**, **APPLIED**, and **FAILED** are distinct milestones. Audit must not log **SUCCEEDED** upon command receipt before business execution finishes. Clarify whether an audit outcome refers to **command acceptance** or **workflow completion**.

One request may produce multiple staged audit records and several domain events. Link them with **correlation_id** or **workflow_id** rather than forcing a 1:1 relationship per request.

## 12. Ordering, Concurrency, and Time Sources

Explaining history requires separating:

- **event/occurred time:** when the real-world action took place.
- **valid time:** when the value holds true in business rules.
- **recorded/accepted time:** when the system accepted the information.
- **commit time/order:** how transactions ordered and became visible in the authoritative store.
- **processing/published time:** when downstream pipelines processed or emitted data.

An event with an earlier **occurred_at** may be **accepted** after another event. Sorting solely by timestamp fails under clock skew, equal timestamps, late arrivals, and retroactive edits.

### 12.1. Aggregate Versioning and Concurrency

When an event store is the source of truth, key by:

~~~text
(aggregate_id, aggregate_version)
~~~

and append new events with **expected_version**. If two writers both read version 2 and attempt to write version 3 for the same aggregate, the UNIQUE constraint forces one to fail or retry after reloading state. **event_id** deduplicates retried requests.

In a history-as-source-of-truth model, entity locks or optimistic revisions guard interval splitting. Exclusion constraints stop illegal final overlaps, though they do not define precedence rules among competing decisions.

### 12.2. Bitemporal and Event Ordering

If a March 20 correction changes the effective date of a March 10 decision, the event store may contain:

~~~text
v1 SubscriptionActivated(...)
v2 PlanChangeApproved(validFrom=2026-03-01)
v3 PlanEffectiveDateCorrected(validFrom=2026-03-05)
~~~

Projections can derive **latest-known** effective history after v3. To inspect what the system understood after v2, replay up to v2 if events are complete, legacy interpretation rules are preserved, and a reliable version-to-system-time mapping exists. For heavy two-axis as-of workloads, persisting a **materialized bitemporal table** is usually faster than replaying from scratch every time.

Thus **event sourcing can underpin a bitemporal model**, yet does not automatically provide a bitemporal query API, exact commit-time guarantees, or freedom from locking and schema evolution.

## 13. Integrity Constraints Differ by Data Category

### 13.1. Audit

- **Unique `audit_id`**; unambiguous actor, action, entity, and outcome.
- Sensitive fields **filtered/masked**.
- Distinguish logs of **committed changes** from **rejected attempts**.
- Enforce edit/delete restrictions and loss detection if required by compliance.
- Avoid forcing UNIQUE on `request_id` when one request generates multiple actions.

### 13.2. Business History

- Stable **`entity_id`** and distinct **`version_id`**.
- Non-empty effective intervals with **[from, to)** bounds.
- Non-overlapping within the business key when at most one value may hold at a time.
- Check **gaps** if continuous coverage is mandatory.
- Every version links to a decision source.
- Multi-interval updates execute **atomically** with concurrency control.

### 13.3. Event Log

- Unique **`event_id`**; unique **`aggregate_version`** within each aggregate.
- Defined event schemas/versions and self-contained payloads.
- Guard event emitters and acceptance preconditions.
- Persist in logical order sufficient for replay; detect **missing versions** before rebuilding.
- Replays do not duplicate side effects; consumers are idempotent.
- Explicit policies for corrections, replay, and migrations.

### 13.4. Cross-Category Linking Constraints

When one decision produces both history versions and events:

- **`decision_ref`** should point to the same approval decision for reconciliation.
- **`event_id`** or **`outbox_id`** must remain constant across retries.
- Success audit records are written only when the action succeeded at the level claimed by `outcome`.
- Write paths must not update the source of truth while skipping mandatory evidence records.

Do not force direct foreign keys across every audit, history, and event row by default: one decision can create multiple effective versions, multiple audit rows, and multiple events. Links must reflect true **cardinality** instead of inventing a false 1:1 constraint.

## 14. Typical Queries and Indexes

### 14.1. “Who Changed Customer 501's Plan?”

~~~sql
SELECT
    audit_id,
    actor_type,
    actor_id,
    action_code,
    outcome,
    request_id,
    decision_ref,
    recorded_at
FROM audit_activity
WHERE tenant_id = 1
  AND entity_type = 'CUSTOMER_SUBSCRIPTION'
  AND entity_id = '501'
ORDER BY recorded_at, audit_id;
~~~

This is an **audit** query. When multiple operations share a timestamp, **audit_id** merely stabilizes presentation order—not necessarily true commit order. Use sequences or transaction metadata when strict ordering is required.

### 14.2. “Which Plan Did the Customer Have on March 5?”

~~~sql
SELECT plan_code, decision_ref
FROM subscription_plan_history
WHERE customer_id = 501
  AND valid_period @> DATE '2026-03-05';
~~~

This queries **business history** at business date B. The non-overlap constraint in the history table guarantees at most one matching row when rules permit one primary plan.

### 14.3. “Which Events for Customer 501 Led to This State?”

~~~sql
SELECT
    aggregate_version,
    event_id,
    event_type,
    schema_version,
    event_payload,
    recorded_at
FROM subscription_domain_event
WHERE aggregate_id = 501
ORDER BY aggregate_version;
~~~

This queries the **event stream**. When the event store is the source of truth, `aggregate_version` defines the logical order for rebuilding aggregate state. It does not establish causal order across **multiple aggregates** without additional coordination.

### 14.4. Indexes Serving Three Different Query Shapes

| Need | Index Strategy |
|---|---|
| Audit by actor/time | `tenant`, `actor`, `recorded_at` |
| Audit by entity | `tenant`, `entity_type`, `entity_id`, `recorded_at` |
| History as-of | `entity_id` + range/time bounds; GiST where appropriate |
| History timeline | `entity_id` + `valid_from` |
| Event replay | `aggregate_id` + `aggregate_version` |
| Events by type/period | `event_type` + `recorded_at` or analytical projection |
| Pending outbox | Partial index on unpublished status |

Indexes add write and storage cost. For high-throughput audit/event tables, test with **EXPLAIN (ANALYZE, BUFFERS)**, partitioning, and retention rules before adding indexes. Never pick a partition key that breaks required uniqueness or ordering scopes.

## 15. Finalized Records and Evidence Must Not Be Silently Rewritten

Effective history can change under retroactive decisions, yet an already-issued invoice or posted ledger entry must retain proof of **the values actually applied**.

Example:

- On Mar 8, an invoice billed BASIC because the system had not yet received the PRO switch.
- On Mar 10, a PRO decision effective Mar 1 is accepted.
- Under current business history, PRO was effective on Mar 8.
- Yet the Mar 8 invoice **was actually billed at BASIC**; never simply join latest history and pretend the invoice used PRO back then.

Invoice lines should store **actual applied price/tax/discount/billing period**, decision version or reference, finalization time, and document ID. Bitemporal or event replay **explains** the discrepancy; it does not replace finalized financial records.

If a refund or revenue adjustment is warranted, issue **credit/debit memos** and corresponding business events, audited with approver details. Never overwrite finalized transaction amounts via a history update.

## 16. Security, Privacy, and History Retention

Audit and event logs risk over-collecting sensitive data: tokens, credentials, payment payloads, HR records, addresses, health data, or customer PII. “Trace as much as possible” must be balanced against **data minimization**.

### 16.1. Protection Rules

- Log **necessary IDs or references**, not full entity profiles copied into every audit/event row.
- Mask sensitive fields in **`diff_data`** and **`event_payload`** using allowlists rather than fragile field-name denylists.
- Separate read permissions for history; users allowed to view current state are not automatically cleared to view all historical states.
- Restrict modification/deletion privileges and isolate administration for audit/event stores when accountability requires it.
- Apply encryption, retention limits, and deletion/anonymization per policy.
- Audit audit-log exports and reads of audit data itself if compliance demands.
- Upon account deletion, decouple evidentiary identifiers that must remain from personal payloads that must be anonymized.

**Append-only does not mean keeping all personal data forever.** When regulations mandate erasure or retention caps, design events with indirect references, surrogate IDs, lifecycle-bound encryption keys, or audited redaction. Never let replay convenience become an excuse to keep secrets indefinitely.

### 16.2. Retention Must Align with Historical Queries

| Data Type | What Capability Is Lost If Purged Early? |
|---|---|
| Audit | Cannot investigate old actions, actors, or operation causes |
| Business history | Cannot determine effective values prior to retention cutoff |
| Event log | Cannot replay from genesis or explain old event chains |
| Snapshot | Event replay becomes slower; if events are also purged, baseline is lost |
| Bitemporal history | Cannot reconstruct “what the system knew at K” in the purged window |

Define a **guaranteed query horizon**. When retention no longer covers an old date, APIs must return “outside retained history range” rather than returning “did not exist” or “zero.”

## 17. Choosing Models Across Relational, Document, Graph, and Analytical Systems

A core goal of **DATABASE_DATA_MODELING** is comparing storage paradigms before picking technology. All three history types can appear in any database; the challenge lies in **semantics and constraints**, not syntax alone.

| Paradigm | Audit Trail | Business History | Domain Event Log |
|---|---|---|---|
| **Relational** | Audit table indexed by actor/entity/time | Version table with ranges/FK/exclusion | Aggregate/version event table, outbox |
| **Document** | Activity collection with metadata and diffs | Version collection with `validFrom`/`To` | Event documents with `schemaVersion` and sequence |
| **Graph** | Node/edge operation logs | Nodes/edges with effective intervals | Node/relationship change events, graph projections |
| **Analytical warehouse** | Action fact tables for trend analysis | SCD Type 2 dimensions, snapshot facts, temporal joins | Event facts for behavior and state-transition analysis |

### 17.1. Relational: Strong Constraints, Still Needs Domain Logic

PostgreSQL provides **CHECK**, **UNIQUE**, **FOREIGN KEY**, **GiST exclusion**, and transactions, making constrained history straightforward. Yet the database does not know whether an upgrade decision was properly authorized; permissions and workflows belong in the domain layer.

### 17.2. Document: Flexible Payloads, Harder Overlap Enforcement

Event documents easily evolve new fields, yet **flexible schema** does not mean no schema. Enforce `schemaVersion`, validation, event identity, and logical locks. For history, a unique index on **`validFrom`** fails to block overlapping intervals with different start dates; use transactions or appropriate locking.

### 17.3. Graph: Relationships Have Their Own History

In an org graph, an **EMPLOYEE MEMBER_OF DEPARTMENT** edge can carry `valid_period`; audit logs record who edited the edge; **EmployeeTransferred** events express the transfer decision. Those three are not interchangeable. When querying paths on date D, filter **all traversed edges by the same date D**.

### 17.4. Analytical Warehouses: Do Not Confuse “Events” with “Period-End State”

A **transaction fact** records actions/events; a **periodic snapshot fact** records end-of-period state; an **SCD Type 2 dimension** stores attribute versions over time. These complement one another. If trying to compute a customer's plan on date D from audit facts, ensure audits contain initial state, every transition, and effective semantics—otherwise join business history or the proper dimension.

## 18. Strategy Selection: You Do Not Always Need All Three at Full Depth

Different systems have different needs.

### 18.1. Current State + Minimal Audit

Fits apps needing **current configuration** and who changed it, **without** querying effective values on past dates—e.g., user UI preferences that allow overwrites plus admin action auditing.

Risk: if “value on date X” is needed later, an audit lacking before/after states or late-arrival semantics will be insufficient.

### 18.2. Current State + Business History

Fits domains needing effective timelines, such as pricing, contracts, memberships, and staff assignments. Add audits for high-accountability actions.

Risk: if business history is updated via UPDATE without retaining `known_period` or rich audits, explaining what the system believed before a correction becomes difficult.

### 18.3. Event Sourcing + Projections + Selective Audit

Fits when **the sequence of decisions/events is the source of truth**, multiple projections need rebuilding, and domain logic can run deterministically.

Risk: event schemas are hard to evolve if poorly designed; replay is resource-intensive; security audits of failed attempts do not appear automatically; requires versioning, snapshots, concurrency, and idempotency strategies.

### 18.4. Bitemporal History + Audit + Domain Events

Fits domains with frequent **retroactive adjustments** needing to explain both **effective validity** and **system knowledge**, plus action accountability and downstream event propagation.

Risk: storage overhead, update complexity, two-dimensional constraints, projection sync, and commit-time subtleties.

**Selection principle:** start from required questions, evidentiary obligations, and data invariants—never from a technology buzzword or a “one-size-fits-all history pattern.”

## 19. Testing the Distinctions Between Audit, History, and Events

Using customer 501 and decision APPROVAL-77, test:

| Scenario | Audit | Business History | Event Log |
|---|---|---|---|
| Switch BASIC → PRO effective Mar 1, committed Mar 10 | Records actor, request, SUCCEEDED | BASIC ends before Mar 1; PRO from Mar 1 | `PlanChangeApproved` accepted |
| Unauthorized user attempts plan switch | Records attempted/rejected per policy | Unchanged | No `PlanChangeApproved` |
| Resend already-processed request | Not logged as a spurious new success decision | No duplicate version | No duplicate business event; redelivery keeps `event_id` |
| Decision correcting effective date | Records editor, reason, linked decision | Re-splits intervals, keeps history per rules | New correction event; projection rebuilt |
| Broker publish fails after DB commit | Change audit still exists | History remains accurate | Outbox unpublished, retry pending |
| Consumer receives event twice | Does not duplicate business action | Projection remains accurate | Idempotent by `event_id`/version |
| Invoice closed at BASIC on Mar 8 | Audit proves prior decision/recording | Current history says PRO valid on Mar 8 | Events explain decision; invoice keeps own snapshot |
| Query B = Mar 5, K = Mar 8 | Audit alone cannot guarantee answer | Bitemporal/reliable replay returns BASIC | Replay to matching version if data complete |
| Query B = Mar 5 per Mar 12 info | Audit helps investigate action only | PRO | Projection after `PlanChangeApproved` returns PRO |

### 19.1. Transaction and Authorization Tests

1. When the history-update transaction fails, the **SUCCEEDED** audit and outbox event in that transaction roll back together.
2. Security audits for failed attempts survive independently of rolled-back business transactions.
3. Two commands editing the same timeline serialize or detect conflicts via optimistic revisions and database constraints.
4. Replaying an event never sends two emails, generates two invoices, or credits money twice when actions must be idempotent.
5. Tenant A's data cannot be queried merely by knowing an `entity_id` belonging to tenant B.
6. Fields masked in business APIs never leak raw into `diff_data` or `event_payload`.

### 19.2. Historical Query Tests

- Exact **`valid_from`** and **`valid_to`** boundaries under half-open intervals.
- Two overlapping history versions on the same day are rejected when rules allow at most one.
- Many-to-many relationship history permits distinct links to coexist simultaneously.
- Event logs with missing `aggregate_version` values are detected before claiming accurate replay.
- Queries asking “what did the system know at K?” never read known time from an overwritten **`updated_at`** column.
- Queries outside retention report insufficient history rather than returning current state.

## 20. Practice Exercise: Managing Order Refunds

An e-commerce platform requires:

> “When an order is cancelled, we need to know who clicked cancel and who approved the refund; we need to know the order status and refund eligibility effective on each date; and we must emit events for the payment service to refund without double-refunding.”

Scenario:

- **Aug 1:** order 700 is confirmed, status **CONFIRMED**.
- **Aug 3:** customer submits a cancellation request, not yet approved.
- **Aug 4:** operations staff approves cancellation effective **Aug 4** and authorizes refund eligibility.
- **Aug 5:** payment service records refund completion.
- **Aug 6:** staff enters a correction stating the policy cancellation date should be **Aug 3**, though finalized invoices/amounts do not automatically change.

Design:

1. **Audit trail** for `REQUEST_CANCEL`, `APPROVE_CANCEL`, `APPROVE_REFUND`, `CORRECT_CANCELLATION_DATE`; capture actor, request, `decision_ref`, outcome. How should a rejected request be logged if required by audit rules?
2. **Business history** for order status and refund eligibility by `valid_period`. If status holds only one value per day, what keys and overlap constraints apply?
3. **Bitemporal** if you must explain why on Aug 5 the system considered the order cancelled only from Aug 4, while after the Aug 6 correction it regards cancellation as effective from Aug 3.
4. **Event log** with events like `OrderConfirmed`, `CancellationRequested`, `CancellationApproved`, `RefundAuthorized`, `RefundCompleted`, `CancellationEffectiveDateCorrected`; specify which are domain events and when each is recorded.
5. **Outbox** publishing `RefundAuthorized` after the approval transaction. Payment consumers use `event_id`/`command_id` to prevent double refunds on broker redelivery.
6. **Queries:** “Who approved?”, “Was the order effectively CANCELLED on Aug 3 per current knowledge?”, “Which events were processed prior to `RefundCompleted`?”
7. **Finalized evidence:** persist actual refunded amounts and payment transaction IDs rather than inferring paid amounts solely from current order status.
8. **Tests:** duplicate cancel requests, two concurrent approvers, redelivered events, transaction rollback between history and outbox, retroactive correction.

**Guidance:** audit accounts for actions; history models effective state/entitlement; event logs record accepted domain occurrences and coordinate workflows. Bitemporal is needed when system knowledge prior to a correction must also be reconstructed. None of these tables replaces actual payment-service refund transaction records.

## 21. Design Checklist and Concluding Principles

Before approving a history storage system, engineering and domain stakeholders should verify:

- **Primary question:** do we need to know **who acted**, **when values took effect**, or **which event sequence occurred**?
- **Source of truth:** is the state/history table or the event store authoritative? Which projections are read-only?
- **Keys:** are audit actor/request keys, history entity/version keys, and event-log aggregate/version keys cleanly separated?
- **Time:** are occurred, valid, known/recorded, and commit times clearly defined; are business dates, time zones, and `[from, to)` bounds agreed upon?
- **Integrity:** is history free of invalid overlaps; are events free of duplicates/gaps; are mandatory actions never missed by audits; do all trace to trusted sources?
- **Atomic writes:** do state changes, success audits, and outbox rows share one transaction where needed? How are failed attempts logged separately?
- **Replay:** do events carry enough payload and `schemaVersion` for deterministic state reconstruction, snapshot baselines, and gap detection?
- **Retroactivity:** on corrections, does the system preserve old knowledge slices if required while never silently mutating finalized records?
- **Service integration:** are outbox, retries, idempotency, watermark/projection lag, and reconciliation designed?
- **Security/retention:** do logs avoid unnecessary secrets or PII; are read permissions, tamper protections, retention windows, and deletion/anonymization agreed upon?
- **Evolution:** when moving to document/graph/analytics stores or evolving event schemas, do business answers remain equivalent and verifiable?

**Final principle:** an **audit trail** is evidence of **activity and accountability**, **business history** models **effective values and relationships**, and a **domain event log** records **accepted business events**. They complement each other, yet each requires its own data contract, time source, keys, and constraints. Good design does not store everything three times—it stores **the right kind of truth for the right question**, coordinates them consistently, and keeps everything verifiable as the system evolves.
