# Projecting Events Into Read Models and Rebuildability

## 1. From Event History to Data Users Need to Read

In an event-recording system, the sequence **OrderPlaced**, **PaymentCaptured**, **OrderCancelled**, **RefundConfirmed** explains what happened to an order. Yet customer-support screens usually need to see right away the **current status**, **captured amount**, **refunded amount**, and **last updated timestamp**; meanwhile, analytics needs **daily cancelled order totals**, **refund turnaround times**, or **post-payment refund rates**.

A **projection** is a rule that transforms one or more events into a read structure tailored to a specific question. A **read model** is the result of a projection: a relational table, document, search index, graph dataset, or analytical summary table. In an **event-sourced** system, the event stream is the source of truth, while read models are derived data that can be rebuilt whenever event data and interpretation rules remain complete.

Example with order `ORD-842`:

| Order in stream | Accepted event | Key information |
| ---: | --- | --- |
| 1 | `OrderPlaced` | Order total 850,000 VND; placement timestamp. |
| 2 | `PaymentCaptured` | Captured 850,000 VND from transaction `PAY-41`. |
| 3 | `OrderCancelled` | Order was cancelled prior to shipment. |
| 4 | `RefundConfirmed` | Refunded 850,000 VND, with payment provider confirmation code. |

A projection for the order screen produces:

~~~json
{
  "order_id": "ORD-842",
  "order_status": "CANCELLED",
  "payment_status": "REFUNDED",
  "total_minor": 850000,
  "captured_minor": 850000,
  "refunded_minor": 850000,
  "currency": "VND",
  "last_applied_version": 4
}
~~~

Another projection can build a four-event **timeline** for support staff. A third projection updates **daily refund totals by date and currency** for finance. The three structures may differ, yet each must have a well-defined **data source, calculation rule, and processing version**.

**Key distinction:** event sourcing does not require users to read the event log directly. On the contrary, good read-model design prevents turning every query into a full-history replay. Events can also be projected in systems where state is the source of truth; in that case, define explicitly which source takes precedence when state and event log disagree.

## 2. Choosing Projections From Business Questions, Not Event Structure

One event can serve multiple read needs. Start from **the question and acceptable latency**, then choose tables, keys, indexes, or update mechanisms.

| Consumer | Question | Suggested read model | Consistency requirement |
| --- | --- | --- | --- |
| Customer | Is the order cancelled yet, has the refund landed? | `order_current` keyed by `order_id`. | May need immediate visibility after a command. |
| Customer support | Which occurrence happened first, who confirmed it? | `order_timeline` ordered within stream. | History must be accurate with low lag. |
| Finance | By business day, how much was captured/refunded? | `daily_payment_summary` by date and currency. | Bounded lag acceptable, must reconcile. |
| Fulfillment manager | Which orders are overdue for handover? | `fulfillment_queue` by status and deadline. | Needs fast filtering/sorting. |
| Relationship analysis | Which orders share a transaction or shipment batch? | Business-relationship graph projection. | Requires reliable identifiers and link sources. |

A read model **should not cram every need** into one wide table merely because everything originates from events. Good read structures are often **intentionally denormalized**, provided source rules and rebuild procedures exist. For example, `order_current` redundantly stores totals to avoid JOINs on display; `daily_payment_summary` stores pre-aggregated numbers to avoid scanning all transactions.

### One Stream or Many?

- **Single-aggregate** projections like `order_current` easily guarantee ordering via `order_id + stream_version`.
- **Multi-aggregate** projections like total revenue must define per-event deduplication and whether the aggregation is commutative.
- **Multi-service** projections can encounter missing or out-of-order data: a payment confirmation event may arrive before the reporting service sees `OrderPlaced`. Staging, backfill, reconciliation, and clear consistency definitions are needed.

## 3. Projection Functions Must Be Deterministic With Their Own Contracts

A simple projector applies a function:

~~~text
state_0 = initial_state
state_1 = apply(state_0, event_1)
state_2 = apply(state_1, event_2)
...
state_n = apply(state_(n-1), event_n)
~~~

For **rebuild** to yield identical results, `apply` must be **deterministic**: the same initial state and the same valid event sequence must produce the same final state under the same rule version.

Essential practices:

1. **Draw facts only from events or immutable versioned reference data.** Never read the *current* fee schedule to interpret an invoice issued a year ago.
2. **Produce no side effects during replay.** `apply` must not call capture/refund APIs, send emails, create new orders, or publish integration events.
3. **Do not use the current wall clock as part of historical calculations.** Business timestamps belong in events, or are passed as query parameters/definition versions.
4. **Define explicitly how unsupported event types are handled.** Skip only when the projection contract permits; if an event mutates relevant state, fail and handle the error.
5. **Manage versions.** The same event name may have multiple payload versions; use matching versioned readers or verified upcasters.
6. **Guard invariants.** Projectors detect invalid history and surface errors; the event writer holds primary responsibility for pre-commit business validation.

Simplified logic example for `order_current`:

~~~text
apply(state, event):
  switch event.type:
    OrderPlaced:
      require state does not exist yet
      return OrderState(
          order_status=PLACED,
          payment_status=UNPAID,
          total_minor=event.total_minor,
          captured_minor=0,
          refunded_minor=0,
          currency=event.currency
      )

    PaymentCaptured:
      require event.currency == state.currency
      require same payment_id not already processed
      state.captured_minor += event.amount_minor
      state.payment_status = PAID
      return state

    OrderCancelled:
      state.order_status = CANCELLED
      return state

    RefundConfirmed:
      require event.currency == state.currency
      require state.refunded_minor + event.amount_minor
              <= state.captured_minor
      require same refund_id not already processed
      state.refunded_minor += event.amount_minor
      state.payment_status =
          (state.refunded_minor == state.captured_minor)
          ? REFUNDED : PARTIALLY_REFUNDED
      return state
~~~

This is **pseudocode** for an illustrative event set, not a complete state machine for all orders. If an order supports multiple captures, multiple refunds, or multiple currencies, model full transaction keys, currencies, and intermediate states rather than relying on a single `payment_status` value. Deduplication rules for `payment_id`/`refund_id` can be enforced at the command writer or inside a projection tracking applied IDs, rather than embedding every ID set inside every summary row.

### Projection Versions Matter Too

Changing the definition of “revenue” from **gross captures** to **captures minus refunds** is a **metric semantics change**, not just a SQL tweak. Assign explicit identifiers/versions to projections—such as `daily_cashflow_v1` and `daily_net_cashflow_v2`—documenting calculation rules, event scope, units, and time policies. Otherwise, a rebuild with new logic can silently change the meaning of published figures.

## 4. Physical Model: Event Streams, Read Models, and Checkpoints

The PostgreSQL example below illustrates storing domain events for **Order** and building read projections. Real systems may use a dedicated event store or broker, yet the logical constraints remain similar.

~~~sql
CREATE TABLE order_event (
    event_id        UUID PRIMARY KEY,
    order_id        VARCHAR(64) NOT NULL,
    stream_version  BIGINT NOT NULL CHECK (stream_version > 0),
    event_type      VARCHAR(100) NOT NULL,
    schema_version  SMALLINT NOT NULL CHECK (schema_version > 0),
    occurred_at     TIMESTAMPTZ NOT NULL,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload         JSONB NOT NULL
                    CHECK (jsonb_typeof(payload) = 'object'),
    UNIQUE (order_id, stream_version)
);

CREATE TABLE order_current (
    order_id              VARCHAR(64) PRIMARY KEY,
    order_status          VARCHAR(24) NOT NULL,
    payment_status        VARCHAR(24) NOT NULL,
    total_minor           BIGINT NOT NULL CHECK (total_minor >= 0),
    captured_minor        BIGINT NOT NULL DEFAULT 0
                          CHECK (captured_minor >= 0),
    refunded_minor        BIGINT NOT NULL DEFAULT 0
                          CHECK (refunded_minor >= 0),
    currency              CHAR(3) NOT NULL,
    last_applied_version  BIGINT NOT NULL
                          CHECK (last_applied_version > 0),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (refunded_minor <= captured_minor)
);

CREATE INDEX ix_order_current_status
    ON order_current (order_status, payment_status);

CREATE TABLE order_timeline (
    event_id         UUID PRIMARY KEY
                     REFERENCES order_event (event_id),
    order_id         VARCHAR(64) NOT NULL,
    stream_version   BIGINT NOT NULL,
    event_type       VARCHAR(100) NOT NULL,
    occurred_at      TIMESTAMPTZ NOT NULL,
    display_summary  TEXT NOT NULL,
    UNIQUE (order_id, stream_version)
);
~~~

**Meaning of keys and indexes:**

- `order_event.event_id` distinguishes events; `UNIQUE(order_id, stream_version)` uniquely establishes order within each stream while supporting version-ordered reads.
- `order_current.order_id` is the lookup key for current state; `last_applied_version` is this projection's **per-stream checkpoint**.
- `order_timeline` holds display-ready summaries without parsing JSON on every screen load; the `(order_id, stream_version)` pair preserves timeline order.
- The `ix_order_current_status` index fits only if queries filter by those two statuses. If queries commonly filter by date and status, measure workload and design indexes for actual predicates.
- Monetary `CHECK` constraints only protect invariants **on projection rows**; they do not ensure source events are valid. The event-writing layer must validate schemas, permissions, totals, and duplicate transactions.

This simple schema assumes `order_id` is globally unique within the system. For multi-tenant systems, add `tenant_id` to keys, relations, and query filters per isolation rules. Foreign keys from timeline to event work when both live in the same database; with separate read stores, use source identifiers and suitable reconciliation mechanisms.

## 5. Synchronous or Asynchronous Projection Updates?

Not every read model requires the same consistency level.

### Synchronous Updates Inside the Source Transaction

When the event store and read model reside in the same database, a system can **append the source event and update critical projections in one transaction**. Right after commit, current state already reflects the new event.

The advantage is achieving *read-your-writes* easily when querying the same consistent store. The trade-off is that every command bears the latency of updating synchronous projections. Updating a large aggregate report inside an order-write transaction can create hotspots and raise contention.

### Asynchronous Updates

A worker reads committed events and updates read models. This pattern suits analytical tables, search indexes, and views that can tolerate lag. However, define **acceptable latency** and how users observe command outcomes:

- Return `event_id` and `stream_version` after a successful write.
- For UIs requiring immediate updates, render the state accepted by the command or query a source with appropriate consistency guarantees.
- If waiting for a projection is necessary, poll `last_applied_version >= accepted_version` **for that specific order**, with a timeout and handling for worker failures.
- Never assume all projections reach the same version simultaneously; each projection maintains its own checkpoint and lag.

~~~mermaid
flowchart LR
    C["Valid command"] --> E["Append source event"]
    E --> S[("Event store")]
    S --> P1["Projector order_current"]
    S --> P2["Projector order_timeline"]
    S --> P3["Projector daily_payment_summary"]
    P1 --> R1[("Order state table")]
    P2 --> R2[("Timeline")]
    P3 --> R3[("Daily summary")]
~~~

The diagram shows three independent projections. When relying on a message broker, ensure events are reliably delivered from the source—for instance via a transactional outbox or properly designed log tailing. **At-least-once delivery** normally means consumers must tolerate duplicate events.

## 6. Ordering, Deduplication, and Checkpoints Are the Projector's Responsibility

Suppose `order_current` for `ORD-842` has applied up to version 2. A broker might deliver:

~~~text
Received: version 2 (duplicate)
Received: version 4 (version 3 has not arrived yet)
Received: version 3
Received: version 4 (duplicate)
~~~

A correct projector must handle this as follows:

| Received event | last_applied_version | Action |
| --- | ---: | --- |
| 2 | 2 | Ignore or verify already-recorded outcome. |
| 4 | 2 | Detect missing version 3; pause/buffer or fetch the missing gap. |
| 3 | 2 | Apply and advance checkpoint to 3. |
| 4 | 3 | Apply and advance checkpoint to 4. |
| 4 duplicate | 4 | Do not apply again. |

For streams with contiguous versions, the rule is:

~~~text
if incoming_version <= last_applied_version:
    ignore_or_verify_duplicate()
elif incoming_version == last_applied_version + 1:
    apply_event_and_advance_checkpoint_atomically()
else:
    recover_missing_versions_before_continuing()
~~~

**Atomic guarantee:** if `PaymentCaptured` increments `captured_minor` and updates `last_applied_version`, both updates must commit together. If the worker crashes between adding the amount and saving the checkpoint, reprocessing could double-count the money. Use transactions and/or version-conditional `UPDATE` statements to prevent corruption.

### Across Multiple Streams: Per-Stream Checkpoints May Not Be Enough

A daily summary table ingests events from thousands of orders. A single `last_applied_version = 20` cannot work because each order can have its own version 20. Use an **event_id deduplication table** per projection:

~~~sql
CREATE TABLE projection_applied_event (
    projection_name VARCHAR(100) NOT NULL,
    event_id        UUID NOT NULL,
    applied_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (projection_name, event_id)
);

CREATE TABLE daily_payment_summary (
    business_day     DATE NOT NULL,
    currency         CHAR(3) NOT NULL,
    captured_minor   BIGINT NOT NULL DEFAULT 0,
    refunded_minor   BIGINT NOT NULL DEFAULT 0,
    capture_count    BIGINT NOT NULL DEFAULT 0,
    refund_count     BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (business_day, currency)
);
~~~

A consumer can execute **within the same read-database transaction**:

1. `INSERT` the `(projection_name, event_id)` pair into `projection_applied_event` with conflict handling. If the event is already recorded, stop processing.
2. If a brand-new event was just inserted, compute its contribution by event type and business day, then `INSERT ... ON CONFLICT DO UPDATE` into the summary table.
3. Commit both the processed marker and the metric update. If the transaction rolls back, the event marker is not kept either.

The example below handles only **PaymentCaptured**, with parameters already validated by schema and policy:

~~~sql
BEGIN;

INSERT INTO projection_applied_event (projection_name, event_id)
VALUES ('daily_payment_summary_v1', :event_id)
ON CONFLICT DO NOTHING
RETURNING event_id;

-- Only execute the aggregation below if the INSERT above returned 1 row.
INSERT INTO daily_payment_summary
    (business_day, currency, captured_minor, capture_count)
VALUES
    (:business_day, :currency, :amount_minor, 1)
ON CONFLICT (business_day, currency)
DO UPDATE SET
    captured_minor =
        daily_payment_summary.captured_minor + EXCLUDED.captured_minor,
    capture_count =
        daily_payment_summary.capture_count + EXCLUDED.capture_count;

COMMIT;
~~~

**Note:** this SQL is a sequence orchestrated by the application; never run `INSERT ... ON CONFLICT DO UPDATE` if the deduplication insert returned 0 rows. Otherwise, duplicate deliveries will still inflate totals. `RefundConfirmed` follows the same pattern for `refunded_minor` and `refund_count`; net amount can be computed as `captured_minor - refunded_minor`.

Key by **date and currency** so VND is never added directly to USD. If multi-currency consolidated reporting is needed, manage exchange rates and effective timestamps/versions as explicit facts.

### When Aggregation Is Non-Commutative

Summing daily monetary amounts is generally commutative if each event contributes a fixed delta and is deduplicated. However, **final state**, **elapsed time between two milestones**, or **state-transition rules** can depend on order. For those computations, projectors must read events in stream-version order and resolve missing steps; deduplicating by event ID **does not replace** order control.

## 7. Late Events, Corrections, and Temporal Data

`occurred_at` is when the business occurrence happened per an authoritative source; `recorded_at` is when the system stored it; `processed_at` is when the projector applied it. These three timestamps can differ:

| Milestone | Example |
| --- | --- |
| Payment confirmed at provider | 10:05, belongs to `occurred_at`. |
| System receives callback and saves event | 10:12, belongs to `recorded_at`. |
| Daily report applies event | 10:14, belongs to projection processing time. |

If the business wants reports **by actual payment time**, group data by confirmed `occurred_at`. If measuring **sync latency**, use the difference between recorded/received time and processing time, mindful of clock skew. Never substitute receipt time for `occurred_at` when devices or partners submit late.

For business dates, choose the timezone intentionally:

~~~sql
SELECT (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS business_day
FROM order_event
WHERE event_type = 'PaymentCaptured';
~~~

This is an example of Vietnam-date bucketing, not an assumption that every business uses this timezone. Multi-country systems may require business dates per transaction locale, tenant, or contract, and those rules must be stored/versioned sufficiently for rebuilds.

### Corrections and Reversals Need Explicit Rules

If a fee or amount was assessed and later reversed, metrics must clearly distinguish:

- **Gross**: total value ever confirmed.
- **Adjustment/reversal**: total recognized adjustments.
- **Net**: total after adjustments per reporting policy.

With `FeeAssessed` and `FeeAssessmentReversed`, a projection can track total assessed and total reversed, with `net_fee = assessed - reversed`. If a reversal targets a specific event, the reversal event must include the target ID or equivalent business identifier so the same charge is never reversed twice. Avoid silently erasing an old event's contribution when the business requires retaining an audit trail.

If policy assigns transactions by **retroactive effective date**, the projection must define how figures reallocate across dates and how late arrivals are handled. Source time, recording time, and effective time are not interchangeable.

## 8. Rebuild: Reconstructing Read Models From Stored Events

A major benefit of event sourcing is the ability to **rebuild read models** when logic changes or derived data is corrupted. Yet safe rebuilding in production requires far more than `TRUNCATE` followed by replay.

### Prerequisites

- **Complete, trustworthy event history:** required events have not been lost, deleted, or semantically altered.
- **Compatible readers:** new code can accurately read older `event_type + schema_version` payloads, applying upcasters when needed.
- **Ordering guaranteed within required scope:** typically by `aggregate_id + stream_version`; if a projection spans multiple streams, define explicit join/merge rules.
- **Published semantics:** what projection v2 computes, which date/currency rules it uses, and how it differs from v1.
- **Adequate capacity and runbook:** reading large event volumes, populating new tables, catching up with live events, and reconciling outputs.

### Safe Rebuild Procedure

Suppose we need to change logic from `order_current_v1` to `order_current_v2`:

1. **Create a separate new read model** with an explicit schema and name/version. Keep `v1` serving users.
2. **Establish the starting position and live catch-up mechanism.** The system needs a consistent way to read history and tail subsequently committed events—for example, a snapshot + reliably checkpointed change stream, or an event store cursor ordered by commit order.
3. **Replay history** into `v2` using the new projector, detecting gaps and skipping duplicates. Persist checkpoints so the job can pause and resume safely.
4. **Catch up with incoming live updates**, ensuring no event committed during replay is missed. Never naively use `MAX(id)` from a pre-commit sequence as a “committed watermark” unless the source guarantees commit-order visibility.
5. **Reconcile v2 data** against source truth using independent checks: count of streams processed, final version per stream, monetary totals across events, sample orders with cancellations/refunds/corrections, error row counts, and lag.
6. **Cut over read traffic to v2** using a controlled versioning switch—such as a view/route or configuration updated atomically at the read tier. Retain the ability to roll back to v1 if discrepancies appear.
7. **Monitor after cutover**, and decommission v1 only after confirming rollback needs, rebuildability, and data retention policies.

~~~mermaid
flowchart TD
    ES[("Event store receiving writes")] --> V1["Projector v1"]
    ES --> B["Replay history into v2"]
    ES --> T["Tail new events for v2"]
    B --> V2[("Read model v2")]
    T --> V2
    V1 --> OLD[("Live read model v1")]
    V2 --> CHECK{"Reconciled and caught up?"}
    CHECK -->|"Not yet"| FIX["Investigate errors / keep catching up"]
    CHECK -->|"Passed"| CUT["Switch read traffic to v2"]
~~~

The diagram emphasizes **building in parallel, verifying, then cutting over**. Never assume a freshly rebuilt table that “read all history as of start time” is already current with events committed afterward.

### Why Is Choosing a Watermark Non-Trivial?

Suppose two transactions append events concurrently:

- Transaction A obtains sequence ID 101 but has not committed yet.
- Transaction B obtains sequence ID 102 and commits first.
- A worker reads “all events with ID ≤ 102”, sees 102 but misses 101; it records checkpoint 102.
- Transaction A commits later. If the worker resumes at ID > 102, **event 101 is permanently skipped**.

A sequence/identity value **allocated** prior to commit does not automatically reflect commit order. To ensure rebuilds never drop events, use a source cursor/checkpoint contract that is transaction-safe—such as a transaction log/CDC position reflecting commit order, or a consistent snapshot coordinated with a change stream. Exact mechanics depend on your database and event-delivery architecture.

## 9. Verifying a Rebuilt Projection

“The rebuild script finished without errors” is not enough to declare data correct. Verify across multiple layers:

| Verification layer | Question | Example |
| --- | --- | --- |
| **Coverage** | Were all streams/events in scope read? | Stream counts, source event counts, and matching checkpoints. |
| **Ordering** | Are there version gaps or unhandled duplicates? | `last_applied_version` matches each order's final version at the reconciliation point. |
| **Arithmetic** | Are monetary amounts aggregated accurately? | Total refunded ≤ total captured per constraints; reconcile gross/refund/net by currency. |
| **Business accuracy** | Are edge cases handled right? | Pre-shipment cancellation, partial refunds, multiple captures, retroactive corrections. |
| **Compatibility** | Were historical events interpreted properly? | Test `v1` and `v2` events against readers/upcasters. |
| **Freshness** | Has the projection caught up with the source? | Lag and stream/cursor position at cutover time. |
| **Resilience** | Can it pause/resume after a crash? | Mid-transaction crashes cause neither double counting nor lost checkpoints. |

You can run a **shadow projection** v2 alongside v1 long enough to cover representative production traffic, compare differences, and classify causes. If v1 had a bug that v2 fixes, **never use “v2 matches v1” as the sole acceptance criterion**. Reconcile independently against source events and expected business outcomes.

If v2 intentionally changes a KPI definition, compare **metric definitions** too: for instance, `gross_captured` and `net_revenue` cannot be expected to equal each other. Announce the version cutover milestone to dashboards and downstream users.

### Snapshots Do Not Solve Every Rebuild

An aggregate snapshot at version N helps **load current state quickly**, yet a new projection needing detailed milestones (such as elapsed time from payment to cancellation) may still need to read **events prior to N**. Milestone details cannot be inferred from a snapshot's final state alone.

If old events have been purged under retention policies, some projections cannot be fully reconstructed. State that limitation explicitly, rely on retained versioned data and appropriate recovery policies, and never call it a “rebuild from scratch” when historical source data is gone.

## 10. Common Mistakes When Projecting and Rebuilding Data

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Adding money on every message received | Retries double totals. | Deduplicate events and record processed markers in the same transaction as total updates. |
| Keeping one shared `last_version` across all orders | Per-stream versions cause missed or skipped events. | Per-stream checkpoints or a commit-ordered source cursor. |
| Applying version 6 before version 5 arrives | Inconsistent state; missed transition preconditions. | Detect gaps, wait/fetch missing events, and apply in order. |
| Calling payment APIs directly during replay | Can trigger real duplicate transactions. | Pure apply functions; side effects belong in separate workflows. |
| Rebuilding by truncating the live table | Users see empty or partial data. | Build v2 in parallel, verify, then switch read traffic. |
| Using timestamps or pre-commit IDs for commit order | Skips late-committing events. | Choose a cursor/change stream with commit-order guarantees. |
| Computing revenue by summing all `PaymentCaptured` ignoring refunds | Wrong net revenue figures. | Define gross/refund/net and track adjustments by rule. |
| Changing projector code without versioning KPI definitions | Historical reports silently shift meaning. | Projection contracts, versions, and migration notes. |
| Reconciling v2 only against the buggy old projection | Rebuild is not independently verified. | Reconcile against source events, business fixtures, and invariants. |
| Assuming all read models are consistent at the same instant | Users temporarily observe mismatched status and reports. | Document lag, use checkpoints and clear reconciliation cutoffs. |

## 11. Choosing Target Storage Models by Query Pattern

A single event source can feed multiple types of read models:

| Read technology/model | Example projection | Strengths | Considerations |
| --- | --- | --- | --- |
| **Relational** | `order_current`, `daily_payment_summary`. | JOINs, keys/constraints, well-defined filtering and aggregations. | Index selection and row contention when many events increment one total. |
| **Document** | `order_detail_document` holding status and short timeline. | Fetch an entire dossier in minimal round trips. | Document size limits, update concurrency, bounded embedded history. |
| **Search index** | Search orders by product name, status, description snippet. | Full-text search and flexible faceting. | Eventual consistency, mapping/index rebuilds, deduplication. |
| **Graph** | Linking orders, transactions, accounts, and causal chains. | Relationship traversal and path queries. | Must keep reliable IDs/links and manage edge updates/deletes. |
| **Analytical warehouse** | Event facts, daily/cohort summary tables. | Large-scale scans and aggregations. | Ingestion lag, late arrivals, KPI definitions, recomputation cost. |

Selection is not based on read speed alone. Ask **when data becomes effective**, **how a projector bug is detected and fixed**, **how far back rebuilds can go**, **retention rules**, **privacy**, and **which source is authoritative**. If a read model cannot be rebuilt due to missing events or incompatible code, it is no longer purely derived data under the original assumption.

## 12. Practice Exercise: Designing Two Projections and a Rebuild Workflow

**Scenario:** an online course platform stores `EnrollmentCreated`, `PaymentCaptured`, `AccessActivated`, `RefundConfirmed`, and `AccessRevoked` events. Failed payments followed by retries, partial refunds, late callbacks, and free promotional access grants can all occur.

Requirements:

- Learners want to see **courses they currently have access to** and activation timestamps.
- Finance wants **daily captured, refunded, and net cash totals**.
- After a bug in refund calculation, the data team wants to rebuild reports without disrupting the learner screen.

**Design tasks:**

1. **Identify sources and keys:** `Enrollment` and `Payment` may be two aggregates; specify `aggregate_id`, `event_id`, `stream_version`, `payment_id`, and how the two sources relate.
2. **Projection A:** design `enrollment_access_current` keyed by `enrollment_id`, including `access_status`, `activated_at`, and `last_applied_version`. Distinguish payment events from actual access-grant events.
3. **Projection B:** design `daily_cashflow` keyed by `(business_day, currency)`; define gross, refunded, and net; specify event deduplication and which timestamp defines the grouping day.
4. **Duplicate events:** simulate `PaymentCaptured` delivered three times. Show the transaction ensuring funds are added only once.
5. **Out-of-order events:** `AccessRevoked` version 5 arrives before `AccessActivated` version 4 in the same stream. Show how the projector detects and recovers.
6. **Rebuild v2:** propose a parallel build, live event catch-up, reconciliation, and cutover process without blanking out live reports.
7. **Safe cursor:** explain why `MAX(event_id)` or a pre-commit `BIGSERIAL` is not automatically a safe watermark.
8. **Limits:** if first-year payment events were purged, which projection cannot be rebuilt and what archival/data-agreement approach is required?
9. **Verification:** propose at least three independent reconciliation checks from source events, including partial refunds and zero-payment promotional access grants.

**Passing criteria:** read models have clear keys and update rules, track processed versions/IDs, avoid duplicate side effects, use accurate business timestamps, reconcile against source events, and support zero-downtime rebuilds.

**Conclusion:** projecting events is the process of **turning progression data into purpose-built read structures**; rebuildability holds value only when source events are complete, interpretation rules are deterministic and versioned, ordering and deduplication are properly handled, checkpoints never drop events, and read-model cutovers are verifiable. That is how event modeling connects with relational, document, graph, and analytical designs so data stays both easy to read and safe to evolve.
