# Business Effective Time vs. System Recording Time

## 1. Why Can One Data Change Have Two Different Timestamps?

In the **Time and History** chapter of **DATABASE_DATA_MODELING**, a critical decision is determining when each value is **true in the business domain** and when **the system recorded or learned that value**. This is part of translating business requirements into verifiable entities, relationships, constraints, keys, indexes, and physical schemas. Simply adding an **updated_at** column usually fails to answer this question.

Suppose customer 501 is on the **BASIC** plan. On April 12, the system receives confirmation that the customer switched to the **PRO** plan with an **effective date of April 8**. There are at least two distinct questions:

- **“Which plan was the customer on as of April 10, according to currently confirmed information?”** The answer is **PRO**.
- **“If we stood at April 10, which plan did the system record the customer as having at that time?”** The answer is **BASIC**, because the decision effective from April 8 was not recorded until April 12.

Both answers are valid; they have **different temporal contexts**. If only the latest version is kept, the system can answer the first question but loses the basis to answer the second. If only an update history is kept without storing the effective date, the system knows a change occurred on April 12, but cannot determine that PRO applied on April 10.

This lesson focuses on how to separate these two time axes, represent them in relational data, and apply the same principles to document, graph, and analytical data.

### Learning Objectives

Learners should be able to:

1. Distinguish **valid time** from **recorded/system time** and avoid confusing them with event occurrence time or processing time.
2. Interpret the two questions **“when was it true?”** and **“since when did the system know it?”** in scenarios involving late-arriving data, erroneous entries, or retroactive changes.
3. Choose between a single-timeline model and a **bitemporal** model based on business requirements.
4. Design effective intervals, keys, non-overlap constraints, and **as-of** queries across both axes.
5. Identify limitations around transactions, consistency, time sources, legacy data, time zones, and operational cost.

## 2. Two Core Time Axes

### 2.1. Business Effective Time — Valid Time

**Valid time** is the time interval during which a fact is considered true in the business world being modeled. For example:

- A contract price applies from July 1 until before October 1.
- An employee belongs to department A from January 1 until before April 1.
- PRO membership takes effect on April 8, even though the system received this decision on April 12.
- A shipping address is the address confirmed by the customer for an order at the time the order was finalized.

Valid time can lie in the past, present, or future relative to the recording date. It is defined by **business rules**. A price taking effect at 00:00 in a branch's local time zone differs from one taking effect at 00:00 UTC; the interpretation rule must be chosen before storing data.

Many domains use **effective intervals** rather than a single instant:

~~~text
[valid_from, valid_to)
~~~

The notation **[a, b)** means inclusive of instant a and exclusive of b. If the BASIC plan ends at exactly 00:00 on April 8 and PRO begins at that instant, the two intervals do not overlap at the boundary.

### 2.2. System Recording Time — Recorded/System Time

**Recorded time** in application design is typically the time the system receives or persists a fact into an authoritative data store. It answers: **“Since when has the system had this information?”**

For versioned data, we usually need an entire **system recording interval**:

~~~text
[recorded_from, recorded_to)
~~~

- **recorded_from**: when the version began to be treated by the system as known/accepted information.
- **recorded_to**: when that version was superseded or invalidated in the system; it may be unset if it is still the latest known information.

Two levels of guarantee must be distinguished:

- **Application-recorded timestamps**, such as **recorded_at = now()**, indicate a timestamp captured by the application or database during processing.
- **Strict system/transaction time semantics** reflect when a version becomes visible according to the database's transaction history. If you must accurately reconstruct committed state at any instant, a timestamp captured prior to commit is not automatically sufficient.

In this document, **recorded/known time** is the “what the system had accepted as known” axis; in the custom PostgreSQL examples, values are **application-managed**. It should not be referred to as built-in automatic PostgreSQL system-versioning.

### 2.3. Comparison of Common Time Concepts

| Concept | Question Answered | Example | Can It Differ from Valid Time? |
|---|---|---|---|
| **Valid time** | Since when is this value effective in the business? | PRO takes effect on April 8 | Serves as the reference axis |
| **Recorded/known time** | Since when did the system record/accept this value? | System receives decision on April 12 | Yes |
| **Event/occurred time** | When did the real-world action occur? | Customer signs request on April 6 | Yes |
| **Received/ingestion time** | When did the data arrive at the API or pipeline? | API receives notification on April 11 | Yes |
| **Processing time** | When did a worker process the message? | Worker reprocesses on April 13 | Yes |
| **Commit time** | When did the transaction become durable/visible in the DBMS? | Transaction commits after validation | Yes |

In a simple workflow, these timestamps may be very close; in distributed systems, manual data entry, offline sync, and retroactive adjustments, they can diverge by many days. Do not conflate two concepts merely because initial tests produce nearly identical timestamps.

For example: at 09:00 on April 12, an operator enters a PRO decision effective April 8; the message was sent from a partner service at 08:55 and finished processing at 09:02. Those are distinct timestamps, even though all relate to the same change.

## 3. Tracing a Late-Recording Scenario

Express timestamps in UTC to avoid ambiguity in the example:

- **2026-04-01 00:00**: BASIC takes effect.
- **2026-04-01 08:00**: system records BASIC.
- **2026-04-08 00:00**: PRO takes effect per a decision confirmed later.
- **2026-04-12 09:00**: system finally records the switch to PRO, effective retroactively from April 8.

~~~mermaid
flowchart LR
    A["Apr 1 00:00<br/>BASIC takes effect"] --> B["Apr 8 00:00<br/>PRO takes effect"]
    B --> C["Apr 12 09:00<br/>System records PRO"]
~~~

<em>In the diagram, horizontal position illustrates chronological order only, not proportional time spacing.</em>

At different recording times, the system holds different versions of “currently known truth”:

| System Queried **As Known On** | Business Date to Inspect | Answer |
|---|---|---|
| Apr 10 at 12:00 | Apr 5 at 12:00 | BASIC |
| Apr 10 at 12:00 | Apr 10 at 12:00 | BASIC |
| Apr 13 at 12:00 | Apr 5 at 12:00 | BASIC |
| Apr 13 at 12:00 | Apr 10 at 12:00 | PRO |
| Apr 13 at 12:00 | Apr 13 at 12:00 | PRO |

The second and fourth rows share the same **business date Apr 10**, yet yield different answers because the **system's knowledge point** differs. If you omit the recorded-time axis, a query for Apr 10 can inadvertently apply data edited after the point in time the user intended to audit.

### 3.1. Three Version Intervals Must Be Stored

After the system records the April 12 change, the bitemporal history can be represented as follows:

| Version | Value | Business Validity | System Known Interval |
|---|---|---|---|
| v1 | BASIC | [Apr 1, ∞) | [Apr 1 08:00, Apr 12 09:00) |
| v2 | BASIC | [Apr 1, Apr 8) | [Apr 12 09:00, ∞) |
| v3 | PRO | [Apr 8, ∞) | [Apr 12 09:00, ∞) |

**v1** represents what the system previously believed: BASIC was effective from April 1 onward. Upon learning of the retroactive decision, the system **does not delete v1**, but closes its recorded interval. **v2** and **v3** represent the business facts currently accepted by the system.

Key takeaway: rows v1 and v3 **overlap in valid time** from April 8 onward, yet **do not overlap in recorded time**. This is the intended behavior of a bitemporal model: two versions refer to the same business date, but hold true under different states of system knowledge.

### 3.2. Two As-Of Query Dimensions

Let:

- **B** = the business instant being queried (*business time*).
- **K** = the point in time from which to inspect what the system knew (*knowledge/recorded time*).

A bitemporal query has the conceptual form:

~~~text
AS_OF(B, K)
= the version where valid_from <= B < valid_to
  and recorded_from <= K < recorded_to
~~~

If no row matches, the conclusion must be **no matching information exists within the retained data range**; do not infer BASIC or a default value. If more than one row matches when business rules state each customer has only one plan at a time, the model is violating its constraint or the amendment process is inconsistent.

## 4. When Is a Single Timeline Sufficient?

Not every table needs two time axes. Decide based on **the questions that must be answered and the evidence that must be retained**.

| Requirement | Sufficient Model | Example |
|---|---|---|
| Read latest value only; past does not need querying | Current table, **updated_at** for sync | Instant UI display preferences |
| Inspect history of system changes with no retroactive effect | Versions ordered by recorded time | Internal processing status timeline |
| Know the value applicable on a business date; decisions never need “when was it known?” | Versions keyed by valid time | Finalized fee schedule |
| Check both the value effective at X and what the system knew at Y | **Bitemporal** | Retroactively adjusted contracts, disputed invoice reconciliation |
| Only reproduce batch-processed reports | Store periodic snapshots or report versions; consider bitemporal if needed | Closed monthly financial reports |

A subtle point: **storing separate valid_from and recorded_at columns on each row does not automatically make a model bitemporal**. To answer “what did the system know at K?”, you must also retain superseded versions along with when they ceased to be current in the system, or an ordered immutable event stream rich enough to reconstruct historical knowledge.

Similarly, a table logging every **UPDATE** can answer “when did the column change?” but cannot reliably answer “which value was effective for which billing period?” without valid time.

## 5. Relational Schema Design with Two Time Intervals

This section uses PostgreSQL to illustrate an **application-managed history table**. The concepts apply to other relational databases as well, though range type syntax, indexes, and constraints may vary.

### 5.1. Choosing Data Types and Interval Representation

Choose the time granularity explicitly before writing DDL:

- If plan entitlements take effect down to the **second or microsecond**, store **timestamptz** and define UTC/display time zone rules.
- If the business only uses **calendar dates in a specific region**, a **date** type or local date paired with a business time zone may be clearer. Do not silently convert “May 1 in Hanoi” into 00:00 UTC when the rule specifies a local calendar date.
- Use half-open intervals **[start, end)** for every range. **NULL/unbounded upper** can represent no known end date yet; it means “unterminated according to current information,” not necessarily “will exist forever.”
- Avoid mixing units and precision across sources; rounding timestamps to whole seconds can make two changes within one second indistinguishable unless a sequence or operation ID is also stored.

PostgreSQL provides the **tstzrange** type for storing time-zone-aware timestamp intervals:

~~~sql
SELECT tstzrange(
    TIMESTAMPTZ '2026-04-01 00:00:00+00',
    TIMESTAMPTZ '2026-04-08 00:00:00+00',
    '[)'
) AS basic_effective_period;
~~~

A **tstzrange** value holds both bounds in a single column; the **@>** operator tests whether the range contains an instant, while **&&** tests whether two ranges overlap.

### 5.2. Bitemporal Table and Non-Overlap Constraint

Assume a customer may have at most **one** active plan for any **(B, K)** pair. Structure:

~~~sql
-- btree_gist allows using = on bigint together with range operators in GiST.
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE customer_plan_bitemporal (
    version_id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id       bigint NOT NULL,
    plan_code         text NOT NULL,
    valid_period      tstzrange NOT NULL,
    known_period      tstzrange NOT NULL,
    source_ref        text NOT NULL,
    correction_reason text,

    CONSTRAINT ck_valid_period_bounds
        CHECK (
            NOT isempty(valid_period)
            AND NOT lower_inf(valid_period)
            AND lower_inc(valid_period)
            AND NOT upper_inc(valid_period)
        ),
    CONSTRAINT ck_known_period_bounds
        CHECK (
            NOT isempty(known_period)
            AND NOT lower_inf(known_period)
            AND lower_inc(known_period)
            AND NOT upper_inc(known_period)
        ),

    CONSTRAINT ex_one_plan_per_business_and_known_time
        EXCLUDE USING gist (
            customer_id WITH =,
            valid_period WITH &&,
            known_period WITH &&
        )
);
~~~

Meaning of the **EXCLUDE** constraint:

> For the same **customer_id**, two rows are not allowed to simultaneously overlap in both **valid_period** and **known_period**.

If two rows overlap only in valid time but belong to **different knowledge periods**, they are permitted to coexist; that is the very basis of retroactive recording. If the business allows a customer to hold multiple plan types concurrently, include **plan_category** or relationship type in the constraint rather than accidentally forbidding valid data.

**EXCLUDE** prevents overlaps, but **does not automatically guarantee there are no gaps**. If business rules require every customer to have a continuous plan without gaps, continuity across valid intervals must also be verified. A **version_id** primary key only identifies the row; it does not replace temporal semantic constraints.

Write privileges to the table and transactional modification rules must be controlled; DDL constraints cannot detect a missing history record for an event that was never written at all.

### 5.3. Initial Recording

Suppose the system knows customer 501 has BASIC starting April 1 and records that fact at 08:00 the same day:

~~~sql
INSERT INTO customer_plan_bitemporal (
    customer_id, plan_code, valid_period, known_period, source_ref
)
VALUES (
    501,
    'BASIC',
    tstzrange(
        TIMESTAMPTZ '2026-04-01 00:00:00+00',
        NULL, '[)'
    ),
    tstzrange(
        TIMESTAMPTZ '2026-04-01 08:00:00+00',
        NULL, '[)'
    ),
    'registration-501'
);
~~~

Timestamps in the example are hardcoded for easy verification. In a production system, **recorded_from** must be generated consistently from a trustworthy system clock when the version is persisted, while **valid_from** is taken from the validated business decision.

### 5.4. Retroactive Modification While Preserving Prior Knowledge

At 09:00 on April 12, the decision to switch to PRO starting April 8 is approved. The system must:

1. Close **known_period** on the versions currently representing latest knowledge.
2. Create a BASIC version valid only up to before April 8.
3. Create a PRO version valid from April 8 onward.
4. Execute the changes atomically in a single transaction, accompanied by the decision source.

Given **illustrative data with only a single prior interval**, the following statements produce the exact table shown in section 3:

~~~sql
BEGIN;

UPDATE customer_plan_bitemporal
SET known_period = tstzrange(
    lower(known_period),
    TIMESTAMPTZ '2026-04-12 09:00:00+00',
    '[)'
)
WHERE customer_id = 501
  AND upper_inf(known_period);

INSERT INTO customer_plan_bitemporal (
    customer_id, plan_code, valid_period,
    known_period, source_ref, correction_reason
)
VALUES
(
    501, 'BASIC',
    tstzrange(
        TIMESTAMPTZ '2026-04-01 00:00:00+00',
        TIMESTAMPTZ '2026-04-08 00:00:00+00',
        '[)'
    ),
    tstzrange(
        TIMESTAMPTZ '2026-04-12 09:00:00+00',
        NULL, '[)'
    ),
    'decision-2026-04-12', 'Finalized effective date'
),
(
    501, 'PRO',
    tstzrange(
        TIMESTAMPTZ '2026-04-08 00:00:00+00',
        NULL, '[)'
    ),
    tstzrange(
        TIMESTAMPTZ '2026-04-12 09:00:00+00',
        NULL, '[)'
    ),
    'decision-2026-04-12', 'Finalized effective date'
);

COMMIT;
~~~

This is an **illustrative example of a single edit with known input data**, not a general-purpose stored procedure ready for arbitrary edits. In production, you must read existing intervals, recompute **all affected segments**, guard against concurrent updates (locking the parent entity row or using an appropriate transaction/version strategy), check affected row counts, and handle retries. If two competing edits target customer 501 simultaneously, neither transaction may blindly assume it is the latest decision.

The **UPDATE known_period** operation does not erase the old version: it “closes” the interval during which the system considered that version current. However, if audit requirements demand that every byte of the history table remain physically immutable, also persist an append-only event/audit log or use a DBMS versioning mechanism that satisfies that requirement rather than assuming metadata updates are physically immutable.

**Transaction timing limitation:** in the example, **09:00** is an application-assigned recording timestamp. It may not equal the commit timestamp. If you must prove exactly “when a transaction committed and became readable,” you need sufficiently strict system-versioning/commit-ordering guarantees rather than merely calling **NOW()** and assuming commit time was captured.

## 6. Querying Along One or Two Time Axes

### 6.1. By Business Time B and Current Knowledge

Problem: “According to currently accepted information, which plan did the customer have on April 10?”

~~~sql
SELECT plan_code, source_ref
FROM customer_plan_bitemporal
WHERE customer_id = 501
  AND valid_period @> TIMESTAMPTZ '2026-04-10 12:00:00+00'
  AND known_period @> statement_timestamp();
~~~

Using the example data after April 12, the result is **PRO**. The **source_ref** column traces back to the confirmed decision. Do not omit the **known_period** predicate: without it, both the old BASIC version and the new PRO version could match April 10.

### 6.2. By Business Time B and Knowledge Time K

Problem: “If we stood at 12:00 on April 10, which plan did the system then believe was effective at 12:00 on April 10?”

~~~sql
SELECT plan_code, source_ref
FROM customer_plan_bitemporal
WHERE customer_id = 501
  AND valid_period @> TIMESTAMPTZ '2026-04-10 12:00:00+00'
  AND known_period @> TIMESTAMPTZ '2026-04-10 12:00:00+00';
~~~

The result is **BASIC**; the decision recorded on April 12 was not yet in the system's knowledge at time K.

If we keep querying business date April 10 but change K to April 13:

~~~sql
SELECT plan_code, source_ref
FROM customer_plan_bitemporal
WHERE customer_id = 501
  AND valid_period @> TIMESTAMPTZ '2026-04-10 12:00:00+00'
  AND known_period @> TIMESTAMPTZ '2026-04-13 12:00:00+00';
~~~

The result is **PRO**. The two queries differ **only in time K**, illustrating the core value of bitemporal modeling.

### 6.3. Single-Axis Queries and Semantic Loss

Suppose a table only has **customer_id, plan_code, valid_from, valid_to**. We can find the plan effective on April 10 per current data, but cannot tell that up until April 10 the system had thought it was BASIC. Conversely, a table with only **changed_at, old_value, new_value** shows the update event on April 12, but without recording that the decision took effect on April 8 it cannot determine when PRO applied.

In a bitemporal table, the two query predicates **valid_period contains B** and **known_period contains K** form a “slice” across both axes. Queries that simply grab the latest row via **ORDER BY recorded_at DESC LIMIT 1** do not fully solve this problem when data spans multiple business intervals or multiple retroactive versions.

### 6.4. Do Not Equate “Known” with “Published”

A table may record an approved decision on April 12 without notifying the customer until April 13. If a requirement asks “what had the customer **been notified of** at K?”, a separate publication/delivery timestamp is needed. A database's **known time** axis reflects only knowledge confirmed by that system; it does not automatically capture communication state, sent emails, or when a partner received the data.

## 7. Scenarios That Must Be Clarified During Modeling

### 7.1. Late-Arriving Data

An offline device records inspection completion at 14:00, but only syncs to the server at 17:00. If the business needs to report completed work by actual hour, **valid/event time = 14:00** is meaningful; if an audit requires proving “since when did the server know?”, **recorded time = 17:00** must be stored.

Late data must be distinguished from erroneous data. A device may have a wrong clock, or a user may manually backdate an effective timestamp; the system needs source verification, trust levels, event signatures/IDs, and authorization for retroactive edits.

### 7.2. Recorded in Advance, Effective in the Future

On June 10, pricing approves a new price list effective July 1. Then:

~~~text
recorded_from = June 10
valid_from    = July 1
~~~

On June 15, the system already **knows** the future price, yet must not apply it to transactions occurring on June 15. A common bug is treating the most recently inserted row in the database as the “current price” without filtering by valid time.

For scheduled changes, clarify whether activation is synonymous with effective date: a record can become active to queries starting July 1 even without a worker running at exactly 00:00; if notifications or projection updates must fire, a scheduler and late-execution handling are required.

### 7.3. Corrections, Amendments, and Retroactive Changes

Three distinct events require distinct representations:

- **Data-entry error correction:** the true effective date was April 8, but an operator typed April 9. History preserves what the system previously believed, followed by the amended version.
- **New business decision with retroactive effect:** on April 12 it is decided to switch the plan starting April 8. Store the approval source and evaluate the impact on already-occurred transactions.
- **Revoking a prior decision:** a previously accepted change is withdrawn. Clarify whether the new status applies from the revocation date forward or rewrites the entire past validity interval.

Bitemporal storage records **versions of knowledge about validity**; it does not automatically dictate issuing refunds, credit memos, or ledger adjustments. Financial impacts should be modeled as documented compensating business operations rather than arbitrarily rewriting finalized transactions.

### 7.4. Conflicts Between Two Data Sources

One partner feed reports PRO effective April 8, while the digitally signed contract states April 9. Never blindly assume the source with the latest **recorded_at** is correct. Define source precedence, approval workflows, disputed statuses, and how unverified information is stored. Recorded time tells you **when** the system received/accepted a value, not that the value is **true**.

### 7.5. Imprecise Effective Dates

Legacy records only state “applies in April” or “starting at the beginning of the quarter” without an exact day. Do not fabricate precise timestamps. You can store **timestamp precision** or an **unknown** status alongside source and inference rules. Uncertain intervals must be distinguished from verified effective intervals.

## 8. Constraints, Integrity, and Concurrent Writes

### 8.1. Invariants to Define

A temporal subscription system might require the following invariants:

1. A customer has at most one primary plan for any **(B, K)** pair.
2. Every valid and known interval has a defined start bound, is non-empty, and ends after it starts.
3. Every adjustment references a traceable data source or decision.
4. Currently recognized intervals do not illegally overlap; if rules require continuity, no date gaps exist.
5. Pre-adjustment versions remain queryable by recorded time.
6. All related edits commit atomically; never leave “old version closed without new version inserted.”
7. Duplicate writes from retries do not create duplicate equivalent history rows.

In the SQL illustration, **CHECK** prevents empty ranges and **EXCLUDE** prevents two-axis overlaps, while rules covering **gapless coverage**, **decision approval**, **source completeness**, **modification ordering**, and **business deduplication** still require handling in the transaction/application layer or additional database mechanisms.

### 8.2. Logical Locking When Rewriting a Timeline

Two concurrent transactions editing customer 501 may read the same history and compute conflicting valid segments. Relying solely on individual INSERT checks may cause one transaction to fail on **EXCLUDE**, yet the application still needs to retry or resolve the conflict.

One approach is to lock the parent entity row **customer 501** for the duration of the transaction, read the currently known versions, recompute intervals, close old versions, and insert new ones. This can be combined with an optimistic version on the parent entity, an appropriate isolation level, and a decision **idempotency key**. Check behavior when no parent row exists to lock or when multiple systems write.

Avoid generating independent timestamps per statement when closing and opening versions for a single decision if doing so creates a gap between the old version's **recorded_to** and the new version's **recorded_from**. Use one shared logical timestamp for the entire decision, while remaining aware of the commit-time limitation noted in section 2.

### 8.3. History Tables and Current-State Tables

Repeatedly running bitemporal queries over entities with many versions can be costly. A **current_plan** table/projection or cache for real-time APIs can help, provided you define which store is authoritative. If current_plan is a projection, you need transactions/outbox/sync, replay, and reconciliation for late or amended data.

A minimal reconciliation check is: for each customer at the current instant, query the bitemporal record at **(B = now, K = now)** and compare it against the read projection. Divergences may be valid within committed lag bounds or indicate data corruption; measure and alert clearly.

## 9. Indexing, Partitioning, and Performance

Two time axes mean queries can filter by **entity_id + B + K**, which is usually harder to optimize than a standard state table.

- **GiST / SP-GiST for ranges:** PostgreSQL supports containment and overlap operators; the **EXCLUDE USING gist** constraint in section 5 both enforces integrity and provides an index structure for certain query shapes.
- **B-tree for lookup keys:** primary keys like **version_id** or entity IDs remain useful; measure real queries with **EXPLAIN (ANALYZE, BUFFERS)** before adding extra indexes.
- **Finding currently recorded versions:** the predicate **upper_inf(known_period)** isolates current-knowledge versions; consider a partial index if workloads frequently read this subset.
- **Partitioning history:** high modification volume may warrant partitioning by recorded time or entity; verify how non-overlap constraints are preserved **across partitions**. Never assume a per-partition exclusion constraint applies globally.
- **Retention and cold storage:** define retention per data category, deletion/anonymization workflows for PII, and evidence-retention obligations. If old versions are purged, **as-of K** queries predating the retention cutoff can no longer return complete answers; APIs should expose the queryable time horizon.

Storage cost grows with the number of **knowledge changes**, not only with actual entity state transitions. Amending a decision spanning many valid intervals may require closing and recreating multiple rows. Long-lived data should have compression, archiving, or analytical offloading strategies driven by real requirements—avoid making every column bitemporal just because the DBMS supports it.

## 10. How Other Data Models Represent Two Axes

Within **DATABASE_DATA_MODELING**, the same business question can be implemented across multiple database types. Never pick a technology before defining the temporal semantics.

| Model | Common Representation | What to Control |
|---|---|---|
| **Relational** | Each version is a row; valid/known ranges; keys, exclusion, and transactions | Overlap checks, atomicity, two-axis query performance |
| **Document** | Version collection, each document having **validFrom/To** and **knownFrom/To**, linked by entity ID | Avoiding unbounded embedded history arrays in one document, multi-version update consistency |
| **Graph** | Versioned nodes **and** edges, each relationship carrying validity and recording intervals | Path queries at (B, K) must filter every node and edge consistently |
| **Analytical warehouse** | Versioned dimensions (**SCD Type 2**) and load/adjustment timestamps; can add second axis | Late batch loads, late-arriving dimensions, impact on finalized fact joins |
| **Event store** | Decision-acceptance events with valid time and storage timestamp; projections rebuilt by rule | Event time vs. recording order, replay logic, schema evolution, corrections |

**SCD Type 2** typically manages versions by effective interval. Having **effective_from/to** alone does not automatically make it bitemporal; to know which version an old report actually used, you also need a knowledge axis or persisted report versions.

**CDC** can transport changes from a database to an analytical warehouse, yet CDC history does not invent valid time if the application never recorded business effective dates. Conversely, an event store holding both occurred_at and recorded_at still needs explicit rules for computing effective state; sorting events by receipt time does not automatically handle retroactive decisions properly.

## 11. Common Mistakes and Design Fixes

| Mistake | Consequence | Fix |
|---|---|---|
| Using **updated_at** to represent effective date | Incorrect billing for retroactive or future-dated changes | Store valid time separately per business rules |
| Overwriting old rows when fixing an effective date | Cannot reconstruct what the system previously knew | Retain versions by recorded/known time |
| Storing only **recorded_from**, omitting when superseded | Hard to run as-of queries directly; easy to pick wrong version | Maintain known intervals or an ordered event log sufficient to reconstruct |
| Sorting by timestamp to resolve all conflicts | Late events or clock skew drop valid decisions | Precedence rules, versioning, idempotency, and authoritative sources |
| Inconsistent closed intervals **[from, to]** | Duplicate values at transition boundaries | Half-open convention **[from, to)** |
| Treating **NOW()** as exact commit time | Can misreport when proving committed state at an instant | Pick clear recorded-time semantics; use strict transaction-time guarantees if required |
| Enforcing only **UNIQUE(customer_id, valid_from)** | Two intervals with different starts can still overlap | Full-interval overlap checks along the appropriate axis |
| Versioning entities while forgetting relationships | Past org/ownership queries return wrong results | Attach validity to relationships/edges or join tables |
| Deleting history after retention without exposing limits | Historical queries silently miss records | Return “out of retention range” status and store range metadata |
| Rewriting finalized invoices based on new valid time | Loss of financial audit trail | Adjust via compensating business transactions, linking decision and invoice |

## 12. Two-Axis Data Test Suite

Using the dataset from section 3, verify queries across both time variables. All timestamps are in UTC.

| B: Business Date | K: System Knowledge Time | Expected Result |
|---|---|---|
| 2026-03-31 12:00 | 2026-04-13 12:00 | No plan in data |
| 2026-04-05 12:00 | 2026-04-10 12:00 | BASIC |
| 2026-04-10 12:00 | 2026-04-10 12:00 | BASIC |
| 2026-04-10 12:00 | 2026-04-13 12:00 | PRO |
| 2026-04-08 00:00 | 2026-04-13 12:00 | PRO (exact start bound) |
| 2026-04-07 23:59:59 | 2026-04-13 12:00 | BASIC |
| 2026-04-10 12:00 | 2026-04-01 07:00 | No recorded information yet |
| 2026-04-10 12:00 | 2026-04-12 09:00 | PRO (exact new recording bound) |

Beyond the table tests, verify:

1. **Overlap:** insert another plan whose valid and known periods both overlap for the same customer; the constraint must reject it.
2. **Non-overlap:** two rows sharing valid period with disjoint known periods must be accepted.
3. **Atomicity:** simulate a failure while inserting new versions; the transaction must not leave old versions half-closed.
4. **Concurrency:** two requests editing the same customer must serialize, conflict, or retry safely per rules.
5. **Idempotency:** replaying the same decision must not generate duplicate intervals or a spurious “amendment” version.
6. **Time zones:** contracts define validity by local calendar date; conversion to UTC instants must remain accurate across DST transitions where applicable.
7. **Late recording and multiple edits:** after two effective-date adjustments, queries at each historical K must faithfully reproduce what had been accepted then.
8. **Projection reconciliation:** current table/cache must match the latest slice within lag SLAs.
9. **Retention:** queries outside the retained history window must return an explicit missing-data status.

This test suite acts as a **contract for temporal semantics**: if storage changes from a version table to an event store or document collection, the business answers must remain consistent.

## 13. Practice Exercise: Designing Time-Aware Price History

A company applies regional service pricing. Pricing analysts routinely approve price tables today to take effect at the start of next month; occasionally, an incorrectly entered price is discovered and must be corrected for a prior period. Support needs to answer:

> “For contract 9001, which price is effective on July 15 according to current information? And when the invoice was issued on July 16, which price did the system record at that time?”

Design the solution in steps:

1. Identify the **contract_price** entity, identifying key (contract + price type/region), approval source, and invoicing reference.
2. Specify business time **B = July 15** and knowledge time **K = when the system created or finalized the invoice**, which may differ from the date printed on the invoice.
3. Choose representations for **valid_period** and **known_period**, half-open start/end conventions, time zone, and precision.
4. Describe scheduling a future-dated price change followed by a retroactive correction; each change must preserve the prior knowledge slice.
5. Define invariants preventing two prices from being simultaneously effective at a **(B, K)** pair for the same price type, and clarify whether a price must always exist.
6. Write two as-of queries with the same B and different K, expected outputs, and missing-data handling.
7. Propose how to preserve proof of the price used to finalize the invoice: store a reference to the applied price version or snapshot of terms rather than recalculating historical invoices from the latest price history.

**Extension prompt:** if on July 20 the system learns that a price effective July 10 was lower than initially entered, the query **(B = July 15, K = July 16)** must still explain the price the system used when generating the invoice. The query **(B = July 15, K = July 21)** reflects the newly amended effective price. Handling the difference is **a separate invoice-adjustment process**, not an automatic side effect of the query.

## 14. Design Sign-Off Checklist

Before approving a temporal schema, engineering and domain stakeholders should agree on:

- **Definitions:** which value is effective at B, and which system is authoritative when asking “known at K?”
- **Time sources:** which decision provides valid time, which component supplies recorded time, and is strict commit-time ordering needed?
- **Schema:** how are intervals and time zones represented, and are prior versions and correction sources preserved?
- **Constraints:** are gaps or overlaps permitted; which keys identify an entity and value type over time?
- **Transactions:** how do retroactive edits split intervals and commit atomically, and how are retries and concurrent writes handled?
- **Queries:** are **(B, K)** as-of semantics, retention boundaries, and missing-data responses tested?
- **Business impact:** do new decisions alter finalized reports/invoices or require separate compensating operations?
- **Evolvability:** when schemas change, storage engines migrate, or history moves, are answers for B and K preserved?

The essence of **time and history** is separating **facts effective in the business world** from **information the system had recorded at a given point in time**. The two axes may coincide, yet when they diverge, a model with only **updated_at** or only **valid_from** cannot express both. Good design clarifies the temporal questions first, then selects the structure, constraints, indexes, and write mechanisms that keep answers consistently verifiable.
