# Acceptance Criteria Checklist for Approving a Model Before Implementation

A team has finished an ERD diagram, a data dictionary table, and a few `CREATE TABLE` SQL statements. The connecting lines look reasonable, column names are consistent, and every table has a primary key. Can implementation begin now?

**Not necessarily.** The model might still allow an order of tenant A to reference a customer of tenant B, double-count revenue upon a return, or oversell inventory when two requests run concurrently. A `BIGINT` column might hold syntactically valid monetary values in the wrong currency unit. An FK might be valid while a dashboard `JOIN` multiplies row counts. A document model might perform great on a test dataset yet collapse once documents or series grow manyfold.

Therefore, **approving a model before implementation** is not "agreeing with a drawing." It is an evidence-backed decision that the model is sufficiently explicit about **business semantics, grain, identity, relationships, constraints, lifecycle, access control, performance, data changes, and operability** so that the engineering team can implement it without guessing critical rules.

This lesson belongs to the **Design Validation** chapter of the **DATABASE_DATA_MODELING** module. Its goal is to build an **acceptance checklist**, tie each criterion to a measurement method and evidence, and compare acceptance requirements across relational, document, graph, and analytical models. SQL examples use PostgreSQL to illustrate turning business rules into verifiable conditions.

> **Principle:** Do not approve a model just because "we have an ERD, PKs, and it runs without errors." Approve only when **mandatory invariants have viable enforcement mechanisms**, unresolved options are documented, and remaining risks have designated owners and explicit remediation criteria.

## 1. What Does Accepting a Design Actually Mean?

Distinguish three distinct checkpoints:

| Checkpoint | What Can Be Concluded | What Cannot Yet Be Concluded |
| --- | --- | --- |
| **Pre-implementation design review** | The model has a business contract, planned protections, and a credible prototype/test plan | Production is guaranteed correct and fast enough |
| **Post-implementation testing in a representative environment** | DDL, queries, migrations, and concurrency work as planned | Production load/environment will never experience anomalies |
| **Post-release operational acceptance** | Live SLOs, data quality, and monitoring are passing | The design will never need to evolve |

At the **pre-implementation** stage, evidence may include confirmed business requirements, ERD and data dictionary, prototype DDL, sample datasets, prototype test results, a migration plan, sizing estimates, or load-test results at representative scale if available. Never report "production SLAs met" based solely on spreadsheet estimates.

A minimum acceptance record must answer:

1. **What is the model for?** Scope of the initial release and out-of-scope use cases.
2. **What does one row/document/node/edge represent?** Grain and lifetime.
3. **Which keys establish identity?** Uniqueness scope by tenant/source/time and mutation policy.
4. **Which invariants must hold?** How each invariant is enforced and verified.
5. **How does it behave when data changes, arrives late, or is deleted?**
6. **Who will read/write, and under what load, latency, and permissions?**
7. **What does the system do on duplicate writes, concurrency, and dependency failures?**
8. **Can legacy data be migrated and rolled back or recovered?**
9. **What evidence is required before release? Who signs off?**

### 1.1. Review Outputs Must Be Actionable

A good conclusion is not "Schema looks good," but rather:

~~~text
Decision: CONDITIONAL GO

Accepted scope:
  SalesOrder, OrderLine, Customer within tenant;
  pre-tax line sales revenue.

Required before migration:
  - Confirm how guest checkout is handled.
  - Verify CONFIRMED Orders always have at least one Line.
  - Add index for querying Orders by customer and created_at.
  - Run confirm/delete-last-line race test with two sessions.

Evidence:
  Model version v1.4
  SQL prototype revision r17
  Test cases VAL-001..VAL-020

Owner:
  Domain owner, DBA, security reviewer, application lead

Expiry:
  Must re-review when adding guest checkout or sharding by customer.
~~~

**CONDITIONAL GO** is only appropriate when open conditions **cannot allow risky actions to occur before those conditions are closed**. If a mandatory invariant lacks protection and the team still intends to open live write traffic, that must be a **NO-GO**, not dismissed as a "minor condition."

## 2. Classifying Criteria: Mandatory, Conditional, and Optimization

Not every criterion carries the same consequence on failure.

| Level | Meaning | Example |
| --- | --- | --- |
| **P0 — blocking gate** | If failed, the affected scope must not deploy | Broken tenant isolation, wrong transaction identity, no double-spend protection |
| **P1 — required before release** | Remediation plan and passing evidence required before live traffic | Unvalidated FKs, unhandled backfill exceptions, untested rollback |
| **P2 — owned optimization** | Conditionally acceptable if risk is measured and SLAs still pass | Adding a materialized view, tuning clustering, improving index naming |
| **N/A with rationale** | Does not apply to the model scope | No personal data present, so specific PII steps are N/A |

Priority levels must derive from **business obligations and impact**, not mechanical rules. For instance, a suboptimal index becomes P0 if latency is a safety condition of a mandatory workflow. A personal-data issue cannot be downgraded to P2 merely because the team ran out of time.

### 2.1. Go / No-Go Decision Rules

You can apply this policy:

- **GO:** all relevant P0/P1 criteria have passing evidence; remaining P2 items have documented risks, owners, and due dates.
- **CONDITIONAL GO:** scope is narrowed or rollout is gated behind explicit acceptance conditions; features needing unmet criteria remain unreleased.
- **NO-GO:** any P0 fails; any P1 fails without an approved risk mitigation; evidence is missing or contradictory.

Never use an **average score** to offset a P0 risk. A model scoring 95/100 that still lets one tenant read another tenant's data is still a **fail**.

## 3. Artifact Pack Required Before the Review

| Artifact | Minimum Content | Approver |
| --- | --- | --- |
| **Problem statement / scope** | User journeys, business decisions, out-of-scope | Domain/Product Owner |
| **Glossary / domain definitions** | Order, Line, Reservation, Payment, Refund, Customer, timestamps | Business Analyst/Domain |
| **Conceptual model** | Entities, relationships, and roles | Domain + Architect |
| **Logical model** | Grain, keys, cardinalities, constraints, lifecycle, versioning | Data Modeler |
| **Physical design proposal** | DDL/indexes/partitioning, query patterns, isolation, sizing | DBA/Data Engineer |
| **Data dictionary** | Meaning, type, unit, NULLs, owner, source, classification | Data Steward |
| **Invariant catalog** | Rules, scope, enforcement, tests, and severity | Domain + Engineering |
| **Workload/access matrix** | Who reads/writes what, frequency, SLOs, cardinality | Application + SRE |
| **Migration/rollout plan** | Expand/backfill/validate/contract, downtime, rollback | DBA + Release Owner |
| **Security/data lifecycle** | Tenant isolation, PII, roles, retention, deletion | Security/Privacy |
| **Verification pack** | Positive/negative tests, reconciliation queries, fixtures, acceptance report | QA/Data Engineering |
| **Decision log** | Choices, trade-offs, conditions, assumptions, and approvers | Review Board |

Twelve separate files are not strictly required. A single versioned document with structured tables can house these artifacts, provided there is **clear traceability** from requirements to design, verification, and owners.

### 3.1. Traceability: Every Requirement Must Lead to Evidence

Example:

~~~text
REQ-12:
  Do not sell quantity exceeding available stock for a warehouse/SKU.

Model:
  StockBalance(tenant, warehouse, sku, on_hand, reserved).

Invariant:
  0 <= reserved <= on_hand.

Write protocol:
  Atomic conditional UPDATE in the same transaction
  as the idempotent Reservation.

Tests:
  VAL-12A: valid reservation succeeds.
  VAL-12B: reservation exceeding stock is rejected.
  VAL-12C: two requests race for the last two units.
  VAL-12D: retry with same operation_id does not reserve more.

Evidence:
  DDL, stored procedure/contract, race test results,
  reconciliation query of Balance vs active Reservations.

Status:
  PASS / FAIL / NOT RUN / N/A with rationale.
~~~

If a requirement has no place in the model or no way to be verified, that is a **design gap**, even if the ERD looks complete.

## 4. Gate A — Accurate Business Understanding and Scope Boundaries

A review must begin with **real usage scenarios**, not by opening an IDE immediately.

### 4.1. Mandatory Acceptance Questions

- Are easily confused terms clearly defined, such as **order, transaction, reservation, payment, revenue, refund, inventory**?
- Does the model distinguish **business entities** from **events happening to those entities**?
- Does each status and transition have an unambiguous meaning, avoiding a single status column that mixes shipping and payment states?
- Are **tenants, regions, data sources, and ownership** defined?
- Does it state which workflows are **unsupported in v1** and how to avoid storing fabricated data for them?
- Are edge cases decided—such as guest checkout, split shipments, partial returns, currency changes, and late-arriving IDs?
- Is there an accountable owner **signing off on the rules** before developers implement them?

### 4.2. Example: "Every Order Has a Customer" Is Not Enough

If the business supports unauthenticated purchases, that statement can be false. There are at least three distinct models:

1. Every Order references a registered Customer: FK `NOT NULL`, guest checkout is **out of scope**.
2. Orders can be guest orders: `customer_id` nullable **with a discriminator** and a valid guest contact snapshot.
3. Guest is a special business Customer type: must explain identity, privacy, and lifecycle, avoiding one dummy Customer record shared by all guests.

Choose an option only after defining **cardinality and NULL semantics**. Never attach an "Unknown" Customer to all guests merely to satisfy an FK if doing so destroys customer distinction, skews reconciliation, or breaks access rules.

### 4.3. Gate A Blocking Condition

**NO-GO** when two stakeholders still interpret a money- or permission-affecting fact/attribute differently, or when a critical field lacks unit and timestamp definitions. "We'll figure it out during coding" is not acceptance evidence.

## 5. Gate B — Grain and Identity of Every Object

### 5.1. Write Exactly One Grain Statement per Table

Examples:

| Component | Single-Row Grain | Common Confusion to Avoid |
| --- | --- | --- |
| Customer | One customer identity within one tenant | One email is not always one person |
| SalesOrder | One Order within a tenant | One payment attempt is not an Order |
| OrderLine | One line item within an Order | Same SKU may validly appear on two Lines |
| PaymentAttempt | One payment request with a stable source ID | Retrying the same attempt is not a new attempt |
| StockBalance | One SKU at one warehouse and tenant | Not the sum across warehouses |
| StockReservation | One accepted stock-hold operation | Not current on-hand stock |
| FactSalesLine | One sales line per reporting definition | Not an adjustment/Refund event |
| FactInventoryDaily | One product–warehouse–day snapshot | Must not SUM across days like a transaction |

### 5.2. Check Keys and Uniqueness Scope

Each entity must specify:

- **Candidate/business key:** why is that combination unique in the domain?
- **Primary key or physical identifier:** is it stable across the entire lifecycle?
- **Surrogate vs natural key:** does the choice lose business `UNIQUE` enforcement?
- **Scope:** global, tenant, `source_system`, warehouse, order, or time interval?
- **Mutation policy:** can the key change, be reused, merged, or split?
- **Retry identity:** does the source supply a stable `event_id`/`operation_id` to prevent duplicate ingestion?

Example:

~~~text
SalesOrder:
  PK: (tenant_id, order_id)
  AK: (tenant_id, order_code)

OrderLine:
  PK: (tenant_id, order_id, line_no)

PaymentAttempt:
  PK: (tenant_id, payment_attempt_id)
  AK: (tenant_id, provider_code, provider_attempt_ref)

StockReservation:
  AK: (tenant_id, operation_id)
~~~

If `order_id` can collide across tenants, **an FK on `order_id` alone is incomplete**. If `provider_attempt_ref` is only unique per provider+tenant, a system-wide `UNIQUE(provider_attempt_ref)` is overly restrictive.

### 5.3. Tests Proving Grain

- An Order has two Lines with the same SKU at different prices/promotions: both valid Lines are preserved, not merged.
- The same provider attempt is retried multiple times: no additional `PaymentAttempt` with financial effect is created.
- Two tenants use the same `order_code`: allowed when uniqueness is per-tenant.
- Same tenant/`order_code`: the second attempt is rejected, even under concurrent requests.
- An inventory snapshot is revised to a new version: it does not become an "additive delta."

**NO-GO** if you cannot state what one row represents, or if two rows with the same business identity can exist without a resolution mechanism.

## 6. Gate C — Relationships, Cardinality, and Referential Integrity

An ERD must be verified from both ends.

| Relationship | Child to Parent | Parent to Child | Special Rules |
| --- | --- | --- | --- |
| Order → Customer | 1..1 within registered scope | 0..N Orders | Same tenant |
| OrderLine → Order | 1..1 | 0..N when DRAFT | CONFIRMED must be 1..N |
| OrderLine → Product | 1..1 | 0..N Lines | Inactive Product still retains history |
| PaymentAttempt → Order | 1..1 | 0..N Attempts | Attempt has its own lifecycle |
| Order ↔ Label | 0..N | 0..N | Requires associative table with key |
| Category → parent Category | 0..1 parent | 0..N children | If a tree, multi-hop cycles must be forbidden |

### 6.1. Conditions That Must Be Documented

- Do min/max cardinalities depend on **status** or **effective time**?
- Do FKs include `tenant_id` and source scope where needed?
- Do optional relationships use meaningful NULLs, or need a discriminator and pending state?
- Does an M:N with its own attributes (role, quantity, `valid_from`) require an associative entity?
- Are historical relationships allowed to have overlapping effective intervals?
- When a parent is archived/deleted, are children retained, detached, or deleted?
- If references cross services, what is the owner/protocol for validating and handling orphans?

### 6.2. Cases an FK Alone Cannot Protect

An `OrderLine` having an FK to `Order` does not prove a **CONFIRMED Order has at least one Line**. In PostgreSQL, a child → parent FK ensures a child has a parent, not a "minimum child count."

If the invariant is mandatory at confirmation time, the **Order Owner** must check the Line count, lock the Order, and ensure every Line insert/update/delete follows the same protocol. If data lives in two independent databases, redesign the boundary or use a protocol with appropriate guarantees.

**NO-GO** when documentation simply says "covered by FK" while the real rule spans **multiple rows, multiple shards, or multiple states** with no enforcement mechanism.

## 7. Gate D — Constraints, Missing Data, and Attribute Semantics

### 7.1. Every Attribute Must Have a Contract

Monetary example:

~~~text
Attribute: unit_price_vnd
Type: BIGINT
Unit: VND whole dong
Nullability: NOT NULL
Valid range: >= 0 in the illustrative domain
Source: price locked when OrderLine is created
Lifecycle: not directly editable after CONFIRMED
History: preserves sold price, does not pull current Product price
Verification: negative insert fails; line total reconciles
~~~

The `BIGINT` type alone does not state whether it is **VND or USD**, pre-tax or post-tax, whether negative amounts are allowed, or how rounding works. Adding a `_vnd` suffix is only meaningful if every writer enforces the unit.

### 7.2. Do CHECK, NOT NULL, FK, and UNIQUE Protect at the Right Level?

- **NOT NULL:** is the value mandatory across every state of the object?
- **CHECK:** could three-valued logic accidentally let `NULL` pass?
- **FK:** did it pick the right parent key, tenant scope, and deletion policy?
- **UNIQUE:** does it cover the right scope, NULL rules, code normalization, and archived records?
- **DEFAULT:** does it reflect business truth or merely mask missing data?
- **Domain enum/status:** is the value set complete? Are state transitions enforced beyond `CHECK`?

For example, `CHECK(quantity > 0)` does not forbid `quantity = NULL` without `NOT NULL`. Standard `UNIQUE(tenant_id,external_reference)` allows multiple `NULL`s in `external_reference` in PostgreSQL; if a reference is mandatory, separate rules are needed.

### 7.3. Missing Data Is Not Zero

- No temperature measurement ≠ 0 °C.
- Missing selling price ≠ 0 VND selling price.
- Unknown Product ≠ a real product named "Unknown."
- Payment confirmation not yet received ≠ Payment `FAILED`.
- Missing inventory snapshot ≠ 0 units in stock.

**NO-GO** if the data dictionary fails to distinguish **unknown, not applicable, missing, invalid, and valid zero** for attributes affecting reports or decisions.

## 8. Gate E — History, Time, and Lifecycle

An accepted model must state explicitly **what is allowed to mutate** and **what must preserve history**.

### 8.1. Distinguish Time Axes

| Timestamp | Meaning | Sample Query |
| --- | --- | --- |
| `event_time` / `occurred_at` | When the event happened | What date was it sold? |
| `valid_from` / `valid_to` | Interval a value/relationship is effective | Which Category did Product belong to at sale time? |
| `posting_date` | Accounting/reporting period booked | Which period does the adjustment post to? |
| `received_at` / `loaded_at` | When the system received the message | What did the system know as of yesterday? |
| `calculation_version` | Version of the aggregation formula | Which rule produced this published KPI? |

If a Product changes Category, **as-sold** reporting may require SCD2 or a snapshot. If facts arrive late, never automatically assign the current dimension by load date and claim it was the category at transaction time.

### 8.2. Lifecycle and Deletion

For Customer/Product/Order/PaymentAttempt, specify:

- Is hard delete allowed, or only archiving/soft delete?
- When a parent is deleted, do children `CASCADE`, `SET NULL`, or `RESTRICT`?
- Is there personal data requiring anonymization or erasure per policy?
- How are historical stores, search copies, analytics, and backups handled?
- Are before/after states and correction reasons recorded?
- Is replay from event logs or as-known-at reporting required?

Never blindly enable `ON DELETE CASCADE` on a Customer with Orders needed for accounting records. Conversely, never retain PII indefinitely just because of `FK RESTRICT`. **Historical integrity** and **personal data governance** must be solved together.

### 8.3. Snapshots and Events Cannot Be Summed Alike

A `FactInventoryDaily` row holds **end-of-day stock of 20 units** and a later revision holds **18 units**: never `SUM` them to 38. A `FactSalesMovement` contains +200,000, a -20,000 adjustment, and a -180,000 reversal: deltas can be `SUM`med to 0 within the same scope and additive measure.

**NO-GO** if grain and aggregation rules fail to separate transactional events, periodic snapshots, accumulating snapshots, revisions, and dimension versions.

## 9. Gate F — Write Correctness Under Concurrency and Distributed Systems

A schema can pass sequential tests yet fail when multiple requests execute concurrently.

### 9.1. Two Requests Competing for Remaining Capacity

Suppose `StockBalance` for a SKU has `on_hand = 10`, `reserved = 8`. Two requests simultaneously try to reserve 2 units. If both read "2 available" from a cache or replica and independently accept, overselling occurs.

A safe write path requires:

1. An owner defined by **tenant, warehouse, sku**.
2. An atomic condition on the current balance, such as `reserved + quantity <= on_hand`.
3. The reservation written in the same transaction as the balance update, or an equivalent invariant-preserving protocol.
4. An idempotency key so retries do not create another reservation.
5. Release/consume transitions state at most once, with reconciliation.
6. No other writer allowed to bypass the owner.

A dashboard query reading `available_stock` cannot substitute for the Stock Owner's atomic decision.

### 9.2. Where Must Concurrency Be Tested?

| Scenario | What Must Be Proven |
| --- | --- |
| Two `INSERT`s with the same business key | Only one valid row commits |
| Two `ReserveStock` calls for remaining units | No oversell; retries reserve no extra stock |
| `ConfirmOrder` concurrent with `DeleteLastLine` | No `CONFIRMED` Order without a Line |
| Two `RedeemVoucher` calls with the same code | Voucher cannot be redeemed twice |
| `PaymentAttempt` callback redelivered | Not captured/recorded twice |
| Two near-simultaneous SCD2 updates | No overlapping effective intervals created |
| Shard cutover with client using old route | Two owners cannot commit concurrently |
| Worker fails after DB commit but before ACK | Replay does not multiply effects |

Choosing an isolation level is insufficient without simulating real interleaved schedules. PostgreSQL `SERIALIZABLE` inside **one database** does not prove two independent databases maintain a global invariant together.

### 9.3. Transactions, Sagas, and Guarantee Limits

A checkout command touching Stock, Payment, and Order across three services does not automatically have all-or-nothing atomicity. If using a Saga, document **intermediate states, idempotent compensations, timeouts, unknown outcomes**, and when an Order is considered `CONFIRMED`.

If the business cannot tolerate temporary divergence and an action cannot be compensated, you need stronger coordination/transactions or redesigned boundaries. Never approve a model under the slogan "eventual consistency" when the invariant must hold at the exact moment success is returned.

**NO-GO** if a mandatory invariant can be violated by two valid concurrent requests lacking a designated owner, transaction, or protocol.

## 10. Gate G — Access Patterns, Indexing, and Scalability

Physical design must start from **critical queries**.

### 10.1. Workload Matrix Before Creating Indexes

| Access Path | Expected Filter/Join/Group | Desired Behavior | Required Evidence |
| --- | --- | --- | --- |
| List Customer Orders | `tenant_id`, `customer_id`, `created_at DESC` | Stable pagination | Proposed index + plan |
| Fetch Order and Lines | `tenant_id`, `order_id` | Small row count, right tenant | PK/FK + `EXPLAIN` |
| Daily revenue reconciliation | Business date, Product/Store | Accurate totals; heavy load may use mart | Grain/KPI test + plan |
| Process Payment callback | `tenant`, `provider`, `provider_attempt_ref` | Idempotent lookup | Unique key and race test |
| Query Product history | `product code` + event time | Right SCD version | Overlap/gap checks |
| Time-series data | `series_id`, `observed_at` range | Range scan / partition pruning | Realistic-scale sample data |
| Purge expired-retention data | tenant/time window | No long locks violating SLO | Retention/partition plan |

### 10.2. Which Indexes Are Needed, and Why?

A B-tree index on `(tenant_id, customer_id, created_at DESC)` can serve customer order lookups; the PK on `(tenant_id, order_id)` serves exact order lookups. Do not create a separate index for every column appearing in a `WHERE` clause without selectivity or matching key ordering.

On very large tables, the design may use tenant/time partitioning, BRIN on event time, clustering, or columnar OLAP engines. Check:

- Is data evenly distributed or are there **hot tenants / hot SKUs**?
- Are there cross-tenant queries, and are they security-approved?
- Will late-arriving events write back into old partitions?
- Can unique keys be enforced across partitions/shards?
- Do additional indexes degrade write throughput, locks, or bloat?
- Is there a retention, compression, and backfill plan as scale grows?

### 10.3. Capacity and Acceptance Thresholds

State explicit numeric assumptions, for example:

~~~text
Scenario (assumed for review, not yet measured in production):
  10 million existing Orders
  3 Lines/Order on average
  100 thousand Orders/day
  30% of Orders from largest tenant
  p95 GET /orders under 150 ms per approved SLO
  p95 ConfirmOrder under 300 ms per approved SLO
  Minimum Order retention per approved policy

Evidence required:
  Query plans on suitably skewed data
  Index sizes and write overhead
  Concurrency tests with hot tenant
  Backup/recovery and backfill estimates
~~~

These numbers are **illustrative assumptions only**, not benchmarks or universal rules. During an actual review, replace them with real product metrics, SLOs, and confirmed owners.

**NO-GO** if critical flows lack an access plan or if hotspot/full-scan risks exceeding limits are unquantified and unmitigated.

## 11. Gate H — Existing Data, Migration, and Evolvability

A great schema for greenfield tables may fail if **legacy data cannot be migrated** or if multiple active writer versions are unsupported.

### 11.1. Mandatory Pre-Migration Data Profiling

For existing data, know:

- Row counts, `NULL`s, out-of-domain values, overflows, and duplicate business keys.
- Orphan FKs and cross-tenant/source references.
- Legacy codes/statuses that do not map to new definitions.
- Whether currency units, timestamps, and timezones changed.
- Whether historical records and dimension versions have gaps or invalid intervals.
- Which tenant/source/time window owns each exception set and how it can be fixed.
- Which consumers and writers still depend on the old schema.

Never assume converting `TEXT` to `BIGINT` will succeed if legacy amounts contain `"1,000"`, `"-100"`, `NULL`, or mixed USD/VND. Classify by **semantics** before casting.

### 11.2. The Expand → Backfill → Validate → Contract Path

~~~mermaid
flowchart LR
    A["Profile"] --> B["Expand schema"]
    B --> C["Compatible writers/readers"]
    C --> D["Batched backfill"]
    D --> E["Validate and reconcile"]
    E --> F["Enforce constraints"]
    F --> G["Contract old schema"]
~~~

In PostgreSQL, `CHECK`/FK constraints can use `ADD ... NOT VALID` followed by `VALIDATE CONSTRAINT` to avoid scanning all existing rows at creation time; `UNIQUE`/PK constraints need a different path, such as building a unique index concurrently where appropriate. `CREATE INDEX CONCURRENTLY` cannot run inside a transaction block.

Backfills must be **idempotent**, checkpointed, resource-throttled, and never overwrite newer writer updates. If old writers continue writing legacy representations without syncing new columns, a one-time "100% migrated" check is insufficient.

### 11.3. Rollback Differs from Forward-Fix

Before dropping the old column, readers can revert to the old path if old data remains synchronized. After `DROP`ping the column or accepting values unrepresentable in the prior schema, **application rollback does not equal data rollback**. You need a valid restore, reverse backfill, or forward-fix plan, and must identify the point of no direct return.

### 11.4. Migration Is a Design Criterion

**NO-GO** if mandatory data cannot be migrated without a plan, orphans/duplicates lack remediation, or the migration risks creating **two writable sources of truth** during a shard/service cutover without a fencing/cutover protocol.

## 12. Gate I — Security, Access Control, and Sensitive Data

A schema with valid keys that still allows tenant A's user to read tenant B's data **fails acceptance**.

### 12.1. Tenant Isolation Checks

- Is tenant part of **keys and FKs** across every relevant table?
- Do APIs/ORMs always filter `tenant_id` from **verified auth context** rather than trusting client-supplied `tenant_id`?
- Do analytics queries, exports, search indexes, cache keys, and batch jobs enforce matching tenant isolation?
- Are DB roles, views, row-level security, or service authorization consistently applied across all read/write paths?
- Do super-admin and support operations have auditing, scoped access, expiry, and approval workflows?
- Do owner changes, tenant merges, or shard migrations risk exposing data?

A `(tenant_id, order_id)` key prevents wrong-tenant references, **but does not automatically ensure every `SELECT` includes `WHERE tenant_id`**. Those are two distinct layers of defense. When using PostgreSQL Row-Level Security (RLS), verify policies for each actual role; table ownership, `BYPASSRLS`, or configuration details can alter enforcement.

### 12.2. Data Classification and Lifecycle

The data dictionary must classify which attributes belong to each group:

| Group | Example | Acceptance Questions |
| --- | --- | --- |
| **Personal identifiers** | Email, phone, name, address | Who can read, for how long, is masking/anonymization needed? |
| **Payment data** | Provider tokens, status, references | Is sensitive data stored unnecessarily? |
| **Business confidential** | Cost price, budgets, contracts | Which roles and tenants may view it? |
| **Public data** | Public Product catalog | Is it genuinely public across all tenants? |
| **Derived data** | Risk scores, customer segments | Provenance, intended purpose, and access rights? |

Do not infer that all data must be kept forever just because of FKs or audit requirements. Nor blindly delete an Order still required for approved reconciliation obligations. Define **retention scope, backups, analytics copies, and erasure/anonymization workflows** under appropriate policies.

### 12.3. P0 Evidence

- Negative authorization tests: tenant A requesting tenant B's Order must be denied or return not-found per API contract.
- Tests verifying report/export queries never leak another tenant's rows.
- Tests verifying operational job DB roles lack permissions to mutate invariants outside their owner scope.
- Checklist for encryption in transit/at rest, secrets management, and policy-compliant PII-free logging.
- Operational owner and workflow ready to fulfill erasure/anonymization requests.

**NO-GO** if any supported read/write path can bypass authorization, or if the team does not know where sensitive data is replicated or retained.

## 13. Gate J — Data Quality, Operations, and Observability

A model does not end at `CREATE TABLE`. Once running, data will arrive corrupted, late, duplicated, missing from upstream, and jobs will crash midway.

### 13.1. Quality Rules Must Have Measurable Indicators

| Metric | Meaning | Signals to Observe |
| --- | --- | --- |
| **Completeness** | Did all mandatory objects/events arrive? | Missing IDs/partitions, expected vs accepted |
| **Uniqueness** | An event/key is not multiplied | Duplicate business keys, retry conflicts |
| **Validity** | Values fall in domain, right unit/format | `CHECK` failures, invalid amounts/currencies |
| **Referential integrity** | Child points to parent in right tenant and version | Orphan counts, pending references |
| **Freshness** | Is data updated within SLA? | Current lag, last successful load |
| **Consistency** | Do state tables and underlying events agree? | Balance vs reservations, Order vs Lines |
| **Accuracy** | Do values match an authoritative source? | Control totals, sample reconciliation |
| **History fidelity** | Can known/point-in-time results be reproduced? | As-of queries, revision completeness |

A pipeline may receive 100% of events **already sent** while the upstream source still holds 10% unsent events. Hence completeness must be measured against **source control totals/sequences/contracts**, not just target row counts.

### 13.2. Error Ownership and Recovery Procedures

The review must answer:

1. Do events have stable source IDs? When a retry carries the same ID with a different payload, how is it handled?
2. When an FK/Dimension is missing, do we **reject, pend, or use an unknown member**? When is it backfilled?
3. If an order is amended after period close, do we restate or post in the current period?
4. If an aggregate job fails between two marts, can dashboards show two conflicting versions?
5. Does threshold-breaching data block publishing automatically or merely alert?
6. Who receives alerts, what is the SLA to respond, and how is post-recovery reconciliation run?
7. Do backups/restores and replays preserve identities/versions sufficiently to prevent duplicate ingestion?

**NO-GO** if P0 discrepancies lack detection and recovery mechanisms or if nobody owns erroneous data. For invariants that must hold at command acceptance time, post-hoc checks are only a **secondary guardrail**, not a substitute for correct write logic.

## 14. Gate K — Model Selection: Relational, Document, Graph, Analytical

No single technology stack is optimal for every data shape. Validate **business logic first**, then evaluate how each paradigm maps it.

### 14.1. Trade-Off Table

| Model | Fits Best When | Key Acceptance Points | Commonly Overlooked Risks |
| --- | --- | --- | --- |
| **Relational** | PK/FKs, transactions, structured joins, normalization | Constraint enforcement, transactions, query plans | Cross-shard FKs aren't free; JOIN fan-out |
| **Document** | An aggregate is read/written mostly as a whole | Document size, atomic updates, versioning | Unbounded embedded arrays; cross-document references |
| **Graph** | Multi-hop traversals, heterogeneous relationships | Node/edge identity, cardinality, cycle constraints | Multi-path double counting; cross-shard cycle checks |
| **Time series** | Timestamped measurement streams with metric labels | Series key, sample grain, late data, retention | High-cardinality tags, duplicate timestamps |
| **OLAP/warehouse** | Historical aggregation across multiple dimensions | Fact grain, conformed dimensions, SCD, additive measures | Summing snapshots/gauges; drill-across multiplication |

### 14.2. Same Business Question, Different Representations

Suppose an Order consists of Lines.

**Relational:** `SalesOrder` and `OrderLine` are two tables with composite FKs. Within one database/owner, multiple rows are validated and committed in one transaction. Fits when Lines need individual updates, deep queries, and relational integrity.

**Document:** an Order document embeds a `Lines` array. Atomic per-document updates work when the DBMS supports them, but you must evaluate size if an Order can hold tens of thousands of Lines and how consumers query by Product.

**Graph:** Orders and Lines/Products are nodes/edges when complex relationship networks must be traversed; decide whether a Line is a distinct node with identity or a weighted edge, and guard against path-based double counting.

**Warehouse:** `FactOrderLine` and `DimProduct` serve analytics; never rely on a lagged mart to decide stock reservations at checkout. Define grain, version keys, and measure additivity.

Do not pick document DBs just for "no migrations"—when JSON shapes evolve, readers, indexes, and validators still require versioning and backfills. Do not pick graph DBs merely because FKs exist—most simple 1–N relationships do not justify a graph engine.

### 14.3. Technology Choice Acceptance Gate

The decision record must include:

- Representative read/write patterns; size, cardinality, and change estimates.
- How invariants are enforced in the chosen technology.
- Benchmarks/tests of at least one concurrent write path and one critical read path.
- Operational costs, backups, migrations, authorization, team expertise, and traceability.
- Evolution path: adding dimensions, increasing connectivity, changing retention, or historical reporting.

**NO-GO** if the model choice is driven merely by tech hype or a tidy diagram without proving critical constraints and queries.

## 15. End-to-End Acceptance Case: Multi-Tenant Ordering System

### 15.1. Finalized v1 Scope

This illustrative model describes an ordering system with the following rules:

- A **registered Customer** can place 0..N Orders; every Order must belong to 1 Customer in the same tenant. **Guest checkout is out of scope for v1**.
- A `DRAFT` Order may have 0..N Lines; a `CONFIRMED` Order must have at least one Line.
- Every Line belongs to exactly one Order and points to one Product in the same tenant.
- Products may become inactive; historical Lines are not deleted with the Product.
- Every Line retains **`unit_price_vnd`** at the time of sale; current Product prices are never retroactively used on historical records.
- Every Order has a display code **unique within its tenant**, not required to be globally unique across the SaaS.
- `PaymentAttempt` represents one **attempt** with a stable provider ID; retried callbacks do not create extra attempts.
- Version v1 uses only **whole VND**, with no refunds, multi-currency, split shipments, or cross-warehouse inventory allocation. Adding those requires re-review.

These are **scope decisions**, not claims that excluded features are unimportant. If the real product must support guests, foreign currencies, or multiple captures, update the contract and test fixtures before acceptance.

### 15.2. Logical Model and Cardinality

~~~mermaid
erDiagram
    TENANT ||--o{ CUSTOMER : owns
    TENANT ||--o{ PRODUCT : owns
    CUSTOMER ||--o{ SALES_ORDER : places
    SALES_ORDER ||--o{ ORDER_LINE : contains
    PRODUCT ||--o{ ORDER_LINE : referenced_by
    SALES_ORDER ||--o{ PAYMENT_ATTEMPT : has
~~~

The diagram shows only structure. Accompanying mandatory annotations:

~~~text
Order -> Customer:         1..1, same tenant
Customer -> Order:         0..N
Line -> Order:             1..1, same tenant
Order DRAFT -> Line:       0..N
Order CONFIRMED -> Line:   1..N
Line -> Product:           1..1, same tenant
Product -> Line:           0..N, even when inactive
PaymentAttempt -> Order:   1..1
Order -> PaymentAttempt:   0..N
~~~

### 15.3. Prioritized Invariants

| ID | Invariant | Priority | Planned Mechanism |
| --- | --- | --- | --- |
| INV-01 | No cross-tenant Customer/Product/Order references | P0 | Composite FKs and authorization |
| INV-02 | No duplicate `order_code` within a tenant | P0 | `UNIQUE(tenant_id,order_code)` |
| INV-03 | No Line with `quantity <= 0` or negative price | P0 | `CHECK` + `NOT NULL` |
| INV-04 | `CONFIRMED` Order has at least one Line | P0 | Order owner transaction and shared locking across all writers |
| INV-05 | No Line edits after Order is `CONFIRMED` | P0 | Write owner and DB permissions |
| INV-06 | Retried `PaymentAttempt` callbacks do not duplicate | P0 | Unique provider reference, payload validation |
| INV-07 | Inactive Products cannot be added to new Lines | P1 | Transactional owner check |
| INV-08 | Historical queries never use current Product price as past sold price | P1 | Snapshot `unit_price_vnd` and tests |
| INV-09 | No hard delete of Products/Customers referenced by Lines/Orders | P1 | `FK RESTRICT` + archive policy |
| INV-10 | Order list queries meet SLO on representative workload | P1 | Indexes/query plans/load tests |
| INV-11 | Ingest lag/quality metrics and recovery procedures exist | P1 | Metrics, audits, runbooks |
| INV-12 | Schema can evolve for guest checkout / multi-currency | P2 | ADRs and change triggers |

**P0/P1 tiers here are illustrative classifications for this case study.** In a real project, business owners, security, and SRE must jointly approve priority levels.

## 16. PostgreSQL Prototype DDL and Enforcement Boundaries

This design is **intentionally small for testing**, not a complete production order/payment system. Run it on a test database, never on live production data.

### 16.1. Identity Tables

~~~sql
CREATE TABLE dv_tenants (
    tenant_id BIGINT PRIMARY KEY,
    tenant_code TEXT NOT NULL UNIQUE
);

CREATE TABLE dv_customers (
    tenant_id BIGINT NOT NULL REFERENCES dv_tenants(tenant_id),
    customer_id BIGINT NOT NULL,
    customer_code TEXT NOT NULL,
    archived_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, customer_id),
    UNIQUE (tenant_id, customer_code)
);

CREATE TABLE dv_products (
    tenant_id BIGINT NOT NULL REFERENCES dv_tenants(tenant_id),
    product_id BIGINT NOT NULL,
    sku TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (tenant_id, product_id),
    UNIQUE (tenant_id, sku)
);
~~~

**Note:** Customer and Product both have tenant-scoped composite PKs, and business codes are protected per tenant. `archived_at` / `is_active` do not trigger `ON DELETE` and do not automatically forbid new Orders/Lines; that is a write-time invariant.

### 16.2. Order, Line, and PaymentAttempt

~~~sql
CREATE TABLE dv_sales_orders (
    tenant_id BIGINT NOT NULL REFERENCES dv_tenants(tenant_id),
    order_id BIGINT NOT NULL,
    order_code TEXT NOT NULL,
    customer_id BIGINT NOT NULL,
    status TEXT NOT NULL DEFAULT 'DRAFT'
        CHECK (status IN ('DRAFT','CONFIRMED','CANCELLED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    confirmed_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ,

    PRIMARY KEY (tenant_id, order_id),
    UNIQUE (tenant_id, order_code),
    FOREIGN KEY (tenant_id, customer_id)
        REFERENCES dv_customers(tenant_id, customer_id)
        ON DELETE RESTRICT,
    CHECK (status <> 'CONFIRMED' OR confirmed_at IS NOT NULL),
    CHECK (status <> 'CANCELLED' OR cancelled_at IS NOT NULL)
);

CREATE TABLE dv_order_lines (
    tenant_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_vnd BIGINT NOT NULL CHECK (unit_price_vnd >= 0),

    PRIMARY KEY (tenant_id, order_id, line_no),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES dv_sales_orders(tenant_id, order_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (tenant_id, product_id)
        REFERENCES dv_products(tenant_id, product_id)
        ON DELETE RESTRICT
);

CREATE TABLE dv_payment_attempts (
    tenant_id BIGINT NOT NULL,
    payment_attempt_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    provider_code TEXT NOT NULL,
    provider_attempt_ref TEXT NOT NULL,
    amount_vnd BIGINT NOT NULL CHECK (amount_vnd > 0),
    status TEXT NOT NULL CHECK (
        status IN ('INITIATED','AUTHORIZED','CAPTURED','FAILED')
    ),

    PRIMARY KEY (tenant_id, payment_attempt_id),
    UNIQUE (tenant_id, provider_code, provider_attempt_ref),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES dv_sales_orders(tenant_id, order_id)
        ON DELETE RESTRICT
);
~~~

### 16.3. Query Indexes

~~~sql
-- List Orders for a Customer, newest first.
CREATE INDEX idx_dv_orders_customer_created
ON dv_sales_orders (tenant_id, customer_id, created_at DESC, order_id DESC);

-- Look up PaymentAttempts by Order; UNIQUE provider ref serves
-- the callback path, while this index serves reading by Order.
CREATE INDEX idx_dv_payment_attempts_order
ON dv_payment_attempts (tenant_id, order_id);

-- PK(tenant_id,order_id,line_no) already supports fetching Lines by Order.
-- Add an index on Product only if actual queries require it.
~~~

In PostgreSQL, child tables with FKs do not automatically get every needed index. Indexes carry write and storage overhead; approve them only when backed by proven query patterns and capacity estimates.

### 16.4. Tenant-Distinctive Test Data

~~~sql
INSERT INTO dv_tenants(tenant_id,tenant_code)
VALUES (1,'SHOP-A'), (2,'SHOP-B');

INSERT INTO dv_customers
    (tenant_id,customer_id,customer_code)
VALUES (1,11,'C-11'), (2,11,'C-11');

INSERT INTO dv_products
    (tenant_id,product_id,sku)
VALUES (1,101,'P-101'), (2,101,'P-101');

INSERT INTO dv_sales_orders
    (tenant_id,order_id,order_code,customer_id,status)
VALUES (1,1001,'O-1001',11,'DRAFT');

INSERT INTO dv_order_lines
    (tenant_id,order_id,line_no,product_id,quantity,unit_price_vnd)
VALUES
    (1,1001,1,101,2,150000),
    (1,1001,2,101,1,130000);
~~~

Two Lines sharing Product 101 **are not duplicates**: the grain is each Line within an Order, carrying different transaction-time prices. Total line value in the sample data is **2 × 150,000 + 1 × 130,000 = 430,000 VND**. Never look up current Product prices to overwrite locked unit prices.

### 16.5. Identify Which Constraints the DBMS Actually Enforces

| Invariant | Enforced by DDL? | What Is Still Missing |
| --- | --- | --- |
| Composite tenant references | Yes, within one PostgreSQL DB | Does not replace API authorization |
| `UNIQUE order_code` per tenant | Yes | Business normalization of `order_code` |
| Valid quantity/price | Yes, within stated column ranges | Currency and tax rules omitted in example |
| `CONFIRMED` Order has a Line | **Not yet** | Cross-row transaction/owner check |
| Product active when adding Line | **Not yet** | Product state check on write |
| No Line edits after `CONFIRMED` | **Not yet** | Write path/roles/triggers if needed |
| Duplicate provider ref callbacks | Unique key enforces | Same ID with differing payload must classify conflict |
| Payment captured once at gateway | **Not yet** | Provider protocol and idempotency |
| Product name/category history | **Not yet** | Snapshot/versioned dimension where needed |

**Never** mark INV-01..INV-12 as PASS solely because the DDL above ran successfully. DDL is only **part** of the evidence pack.

## 17. Reconciliation Queries and Pre-Implementation Tests

### 17.1. Detecting `CONFIRMED` Orders Missing Lines

~~~sql
SELECT o.tenant_id, o.order_id
FROM dv_sales_orders AS o
WHERE o.status = 'CONFIRMED'
  AND NOT EXISTS (
      SELECT 1
      FROM dv_order_lines AS l
      WHERE l.tenant_id = o.tenant_id
        AND l.order_id = o.order_id
  );
-- Expected: zero rows.
~~~

This is a **reconciliation check**, not a write-time guard. If two sessions update status and delete the last Line without a shared locking convention, this query only catches the bug after it happened.

### 17.2. Conditional Order Confirmation Protocol

~~~sql
BEGIN;

-- Step 1: lock the Order as the serialization point for the decision.
SELECT status
FROM dv_sales_orders
WHERE tenant_id = 1 AND order_id = 1001
FOR UPDATE;

-- Step 2: check whether at least one Line exists.
SELECT EXISTS (
    SELECT 1
    FROM dv_order_lines
    WHERE tenant_id = 1 AND order_id = 1001
) AS has_line;

-- Step 3: ONLY IF current status = DRAFT,
-- has_line = true, and other business rules pass:
UPDATE dv_sales_orders
SET status = 'CONFIRMED',
    confirmed_at = CURRENT_TIMESTAMP
WHERE tenant_id = 1
  AND order_id = 1001
  AND status = 'DRAFT'
RETURNING tenant_id, order_id, status;

-- If conditions fail or wrong row count updated: ROLLBACK.
-- If conditions verified and exactly one row updated: COMMIT.
COMMIT;
~~~

**This is a conditional workflow template, not a script to blindly run straight through to `COMMIT`.** Implement it in the application service or stored procedure, and ensure **every writer inserting/updating/deleting Lines** locks the Order first, checks its state, and commits in the same transaction. If `ConfirmOrder` acquires the lock while `DeleteLine` ignores the convention, the invariant can still break.

### 17.3. Reconciling Line Value Totals

~~~sql
SELECT tenant_id, order_id,
       SUM(quantity * unit_price_vnd) AS line_total_vnd,
       COUNT(*) AS line_count
FROM dv_order_lines
GROUP BY tenant_id, order_id
ORDER BY tenant_id, order_id;
-- For Order (1,1001): 430000 VND, 2 Lines.
~~~

Never join Lines directly with `PaymentAttempt` and `SUM` both at once when both are 1–N children of Order. Two `PaymentAttempt`s and two Lines produce four joined rows, multiplying totals. When drilling across, **aggregate each child set to the parent grain before joining**.

### 17.4. Detecting Invalid Lifecycle States

~~~sql
SELECT tenant_id, order_id, status,
       confirmed_at, cancelled_at
FROM dv_sales_orders
WHERE (status = 'CONFIRMED' AND confirmed_at IS NULL)
   OR (status = 'CANCELLED' AND cancelled_at IS NULL);
-- These rows are already blocked by CHECK while the DDL is active.
~~~

However, that query **cannot catch** every invalid transition such as `CANCELLED → CONFIRMED` if a writer sets `confirmed_at`. State machine tests and transition auditing are still required.

### 17.5. Checking Logical FKs When Physical FKs Are Absent

If a distributed model separates Customer and Order across two services, build a cleaned reconciliation dataset from both sources:

~~~sql
-- Verification query over copies gathered in a reconciliation
-- environment; there is no native distributed FK across two independent DBs.
SELECT o.tenant_id, o.order_id, o.customer_id
FROM dv_sales_orders AS o
LEFT JOIN dv_customers AS c
  ON c.tenant_id = o.tenant_id
 AND c.customer_id = o.customer_id
WHERE c.customer_id IS NULL;
~~~

The validator must account for **lag between the two sources**: transient orphans from late-arriving Customer events are not the same severity as orphans past a committed cutoff. Define timing and classification rules explicitly.

### 17.6. Verifying SQL Interprets Tenant Scope Properly

~~~sql
-- CORRECT scope: an Order ID is identified by both tenant and order.
SELECT *
FROM dv_sales_orders
WHERE tenant_id = 1
  AND order_id = 1001;
~~~

A query filtering only by `order_id` can return multiple Orders across tenants when each tenant has an ID `1001`. Never assume `order_id` is globally unique just because a small sample dataset only has one Order.

### 17.7. EXPLAIN and Performance Measurement

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT tenant_id, order_id, status, created_at
FROM dv_sales_orders
WHERE tenant_id = 1
  AND customer_id = 11
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
~~~

On tiny test tables, PostgreSQL may choose a `Seq Scan` because reading the entire small table is cheaper than an index lookup. That **does not prove the index is wrong**. Test on sufficiently representative data with realistic large/small tenant skew and compare actual plans, buffers, rows, and latency.

`EXPLAIN ANALYZE` **actually executes the statement**; only run `INSERT`/`UPDATE`/`DELETE` with `EXPLAIN ANALYZE` when intentionally testing writes in a safe environment. Never extrapolate production SLAs from a single `EXPLAIN` on a ten-row fixture.

## 18. Pre-Approval Testing Matrix

A checkbox list is insufficient unless it specifies **input data, operations, expected results, and evidence**.

### 18.1. Positive, Negative, and Concurrency Tests

| ID | Scenario | Expected Result | Evidence |
| --- | --- | --- | --- |
| T01 | Create valid Order in tenant 1 | Succeeds | Integration result |
| T02 | Create Order with duplicate `order_code` in tenant 1 | Rejected by `UNIQUE` | Negative SQL test |
| T03 | Two tenants use the same `order_code` | Allowed per policy | Positive test |
| T04 | Line references an Order existing only in another tenant | Rejected by composite FK | Negative SQL test |
| T05 | Line with `quantity = 0` | Rejected by `CHECK` | Negative SQL test |
| T06 | Line with negative `unit_price_vnd` | Rejected by `CHECK` | Negative SQL test |
| T07 | Delete Product that already has Lines | Rejected by `FK RESTRICT` | Negative SQL test |
| T08 | Archive Product that already has Lines | Historical Lines remain intact | Lifecycle test |
| T09 | Confirm Order with no Lines | Rejected by owner | Domain test |
| T10 | Confirm Order with Lines | Commits exactly once | Domain test |
| T11 | Confirm concurrently with deleting last Line | No `CONFIRMED` Order without Line | Two-session race test |
| T12 | Payment callback retry with same ID/payload | No multiplied effect | Idempotency test |
| T13 | Callback with same ID but different payload | Reports conflict; never silently overwrites | Conflict test |
| T14 | Tenant A API tries reading Tenant B's Order | Denied / not found | Authorization test |
| T15 | Join Order with multiple Lines and Attempts | Totals are not multiplied | Reconciliation |
| T16 | Backfill encounters orphans/duplicates | Quarantined; not declared clean | Migration dry run |
| T17 | Old writer runs concurrently with backfill | No divergence after cutoff | Compatibility test |
| T18 | Worker fails after DB commit before ACK | Replay does not multiply impact | Failure injection |
| T19 | Product changes Category and late fact arrives | Uses right version for as-sold if needed | Temporal test |
| T20 | Restore/replay after incident | Preserves identity and approved RTO/RPO | Recovery drill |

**Test status must be `PASS`, `FAIL`, `NOT RUN`, or `N/A` with rationale.** Having written a test case does not count as `PASS`. Likewise, before a runnable prototype exists, you may mark `"DESIGNED"` or `"READY TO TEST"`, but never claim empirical verification.

### 18.2. Negative Tests Must Isolate Transactions

~~~sql
-- Run in a test database using Section 16 sample data.
-- Tenant 2 has Product 101 but does not yet have Order 1001.
INSERT INTO dv_order_lines
    (tenant_id, order_id, line_no, product_id,
     quantity, unit_price_vnd)
VALUES (2, 1001, 1, 101, 1, 150000);
-- Expected: foreign_key_violation.
~~~

If a test harness runs multiple intentionally failing SQL statements inside **one PostgreSQL transaction** without `SAVEPOINT`, the first failure puts the transaction into an aborted state. Subsequent statements no longer verify individual invariants. Run each negative test in its own managed transaction or use savepoints and roll back to each savepoint.

### 18.3. Race Tests Must Have Interleaved Schedules

~~~text
Session A:
  BEGIN
  Lock Order 1001
  Check Line exists
  PAUSE

Session B:
  BEGIN
  Attempt delete last Line
  Must follow same parent-lock protocol
  Wait or reject based on Order state

Session A:
  Commit transition to CONFIRMED

Session B:
  Re-check state
  Reject deletion when illegal
  ROLLBACK / business error

Final validation:
  No CONFIRMED Order without Line.
~~~

Also test the reverse order: `DeleteLine` acquires the lock and commits first, then `ConfirmOrder` re-checks and rejects once no Lines remain. Running two transactions sequentially in one session is **not** concurrency testing.

### 18.4. Test Datasets Must Include Edge Cases

A minimal fixture should include two tenants sharing the same numeric IDs, two Lines with the same SKU at different prices, a `DRAFT` Order without Lines, an inactive Product referenced by historical `OrderLine`s, two distinct `PaymentAttempt`s on one Order, callback retries, NULL/duplicate/orphan legacy cases, and a hot-tenant dataset. Never build one tenant–one Order–one Line and declare the model verified.

## 19. Review Minutes and the GO / NO-GO Gate

### 19.1. Reusable Acceptance Record Template

~~~text
MODEL ACCEPTANCE RECORD

Model:
  Multi-tenant Sales Order v1

Model revision:
  [version / DDL revision]

Review date:
  [review date]

Scope:
  Registered Customer, Order, Line, Product,
  PaymentAttempt; VND; guest/multi-currency not yet supported.

Decision:
  GO | CONDITIONAL GO | NO-GO

P0 evidence:
  Tenant FK + authorization
  Grain and uniqueness
  Order/Line lifecycle and concurrency
  Payment idempotency

P1 evidence:
  Migration and rollback
  Representative workload/query plans
  Retention/access controls
  Quality/observability and recovery

Supporting artifacts:
  Domain glossary, ERD, data dictionary,
  invariant catalog, test logs, migration dry run,
  security approval, query/capacity estimates.

Open issues:
  [ID, severity, impact, owner, due date,
   exact release-blocking condition]

Reason for decision:
  [which evidence passed / failed]

Permitted activities:
  [prototype only / staging / canary / production]

Prohibited activities:
  [write paths / features not yet enabled]

Sign-off:
  Domain Owner; Data Modeler; DBA;
  Application Owner; Security; Release Owner

Triggers for re-review:
  Guest checkout, currency/refund expansion,
  sharding changes, history/retention changes,
  significant workload increase.
~~~

If nobody has genuinely signed off on **business semantics**, keys/modeling, or security, never fill in `PASS` just to make the record look complete.

### 19.2. Example of an Honest Conclusion When Tests Have Not All Run

Suppose the team has prototype DDL but **has not yet run race test T11** and has not measured SLOs on skewed data:

~~~text
Decision:
  NO-GO for production write traffic.

Accepted for prototype work:
  Identity/grain of Order and Line.
  Composite tenant-aware FK/UNIQUE proposal.
  Data dictionary for money and lifecycle.

Pending:
  T11 concurrency: NOT RUN.
  T18 failure/retry: NOT RUN.
  p95 under hot-tenant load: NOT MEASURED.
  PII retention: OWNER APPROVAL PENDING.

Allowed:
  Continue implementation in isolated environment.
  Run concurrency/load/security/migration tests.

Not allowed:
  Open production traffic for CONFIRMED Order.
  Claim end-to-end invariants are proven.

Re-review:
  After required evidence and sign-offs exist.
~~~

A **pre-implementation** review may authorize **prototype construction**, while still withholding approval for **production release**. State explicitly which activities the decision authorizes. `CONDITIONAL GO` is only valid if scope restrictions **genuinely prevent unmitigated risks**.

### 19.3. When Does an Approval Expire?

Re-review is required when changing:

- Cardinalities: e.g., adding guest checkout.
- Uniqueness scope: `order_code` from per-tenant to global.
- Units: from VND-only to multi-currency.
- Lifecycle rules: adding refunds, partial captures, or split fulfillment.
- Consistency boundaries: splitting Order/Line or Customer into separate databases.
- Fact grain or SCD/late-correction versioning.
- Scale: hot tenants, partitioning/sharding, or multi-fold data volume growth.
- Security, data erasure, or retention policies.
- Storage engine or DBMS/version with different constraint/index behavior.

An "Approved" stamp on v1 **does not apply indefinitely** to a v2 whose contract changed.

## 20. Ready-to-Use Acceptance Checklist

In a real record, add columns for **Severity, Owner, Evidence ID, Status, Due Date** to every item. Mark `PASS` only with passing evidence.

### A. Scope and Business Semantics

- [ ] A01. Use cases, v1 scope, and out-of-scope features are confirmed.
- [ ] A02. Key terminology and KPIs have consistent, non-contradictory definitions.
- [ ] A03. Business exceptions, states, and transitions are explicitly specified.
- [ ] A04. Invariants have IDs, scopes, enforcement timing, and severity levels.
- [ ] A05. Accountable owners signed off on semantics before coding.

### B. Grain, Keys, and Relationships

- [ ] B01. Every table/document/fact has a clear grain statement.
- [ ] B02. Candidate/business/surrogate keys, tenant/source/time scopes, and mutation rules are stated.
- [ ] B03. Retrying the same event does not become two business events.
- [ ] B04. `PK`/`FK`/`UNIQUE`/`CHECK`/`NOT NULL` accurately reflect scope and NULL logic.
- [ ] B05. Relationships specify predicates, roles, and min..max cardinalities on both ends.
- [ ] B06. M:N, optional 1:1, and self-referencing relationships have appropriate safeguards.
- [ ] B07. Cross-service/shard references are documented as logical when physical FKs are absent.
- [ ] B08. Multi-row invariants have clear owners, transactions, or protocols.
- [ ] B09. Mechanisms exist to detect orphans, duplicates, wrong tenants, and dimension version drift.

### C. Semantics, Time, and Lifecycle

- [ ] C01. Fields specify type, unit, valid domain, NULL semantics, and authoritative source.
- [ ] C02. Missing, zero, invalid, unknown, and not-applicable are distinguished.
- [ ] C03. Event/valid/posting/ingest times and timezones match the business questions.
- [ ] C04. History, SCDs, revisions, late events, and as-of queries have defined policies.
- [ ] C05. Transaction/snapshot/delta facts and measure aggregation rules are separated.
- [ ] C06. `ON DELETE`/`UPDATE`, archiving, anonymization, and retention have clear justifications.
- [ ] C07. Corrections/restatements do not silently alter published numbers without an audit trail.

### D. Writes and Concurrency

- [ ] D01. All P0 invariants are enforced at the exact time commands are accepted.
- [ ] D02. Each critical decision has an authoritative owner.
- [ ] D03. Race tests simulating true contention have passed or are release blockers.
- [ ] D04. Retries after timeout or commit do not multiply effects.
- [ ] D05. Sagas/2PC/compensations accurately describe what is actually supported.
- [ ] D06. Partition/shard keys do not break global uniqueness or cross-row invariants.
- [ ] D07. Batch/admin/CDC jobs and all other writers adhere to the same contract.

### E. Performance and Operations

- [ ] E01. Access matrix covers primary queries, filters, joins, sorts, and SLOs.
- [ ] E02. Indexes/partitions/clustering have justifications and measurement plans.
- [ ] E03. Data skew, hot keys, late arrivals, and high-cardinality labels are accounted for.
- [ ] E04. Volume, growth, storage, and write overhead are estimated.
- [ ] E05. Plans exist for backups, restores, backfills, migrations, and rollbacks.
- [ ] E06. Monitoring covers freshness, completeness, duplicates, orphans, and consistency.
- [ ] E07. Runbooks and owners exist for error handling, replay, and RTO/RPO recovery.

### F. Security, Migration, and Evidence

- [ ] F01. Tenant isolation is verified across DB, APIs, caches, exports, and BI.
- [ ] F02. Sensitive data, access rights, masking, and erasure/retention are explicit.
- [ ] F03. Negative tests for constraints, authorization, and lifecycles have recorded results.
- [ ] F04. Data profiling and legacy exceptions are resolved or formally bounded.
- [ ] F05. Expand–backfill–validate–contract can run alongside live writers.
- [ ] F06. Rollback/forward-fix and points of no direct return are approved.
- [ ] F07. Requirements trace cleanly to models, enforcement, tests, and evidence.
- [ ] F08. Every `FAIL`/`NOT RUN` item has an owner, severity, and release-blocking status.
- [ ] F09. `GO`/`CONDITIONAL GO`/`NO-GO` states scope, expiration, and sign-offs.
- [ ] F10. Change triggers requiring re-review are explicitly documented.

**Evaluation rule:** one P0 failure cannot be offset by completing many P2 items. `N/A` items require justification. If only planned descriptions exist without executed tests, mark **NOT RUN**; you may approve the design for prototyping, but never declare release readiness.

## 21. Warning Signs That a Model Is Not Ready

| Plausible-Sounding Claim | Why It Is Insufficient |
| --- | --- |
| "We have an ERD and every table has an ID" | Grain and business uniqueness remain undefined |
| "There's an FK, so CONFIRMED definitely has Lines" | Child → parent FK does not force a parent to have children |
| "Leave it NULL for flexibility" | NULL can mask states and missing data |
| "The same ID across two tenants probably won't happen" | Key uniqueness scope is unproven |
| "Use current `Product.price` for historical reporting" | Historical amounts break whenever `Product` changes |
| "Sum all numeric metrics" | Gauges, snapshots, and ratios are not always additive |
| "SELECT to check stock then UPDATE is safe" | Two concurrent requests can oversell |
| "Each shard is SERIALIZABLE so global totals are right" | No cross-shard conflict validation exists |
| "Read from a replica to approve orders" | Replicas can lag |
| "99% backfilled is good enough" | The remaining 1% may be the most critical records |
| "More indexes definitely make things faster" | Write/bloat overhead and missing workload analysis |
| "Backups exist so rollback is easy" | New data may not be backward-convertible |
| "Test cases are written so it PASSes" | No execution evidence exists yet |
| "v1 was approved so v2 is automatically approved" | Business rules and technology conditions may have changed |

A sharp reviewer challenge is: **"Show me concrete data and an execution schedule that breaks this design, then show which constraint or protocol prevents it."**

## 22. Scenario Exercises with Solution Guides

### Exercise 1. Technical Key Without Grain

**Prompt:** `OrderLine` has an auto-incrementing ID, but it is undecided whether the same SKU can appear twice in one Order. Can the grain check PASS?

**Hint:** No. A technical PK does not define "what one row represents." Finalize the business rule and key/reconcile at the true grain.

### Exercise 2. Tenant-Scoped Keys

**Prompt:** Order `O-1001` is allowed to appear in two tenants. Is a table-wide `UNIQUE(order_code)` valid?

**Hint:** No. If codes are unique only per tenant, use `UNIQUE(tenant_id,order_code)`, test that same-tenant duplicates fail, and cross-tenant duplicates succeed.

### Exercise 3. State-Dependent Cardinality

**Prompt:** A `DRAFT` Order can have no Lines, while `CONFIRMED` must have Lines. Is an FK from `Line → Order` sufficient?

**Hint:** No. You need an owner/transaction checking at confirmation time, coordination across all Line writers, and race tests.

### Exercise 4. Redelivered Payment Callback

**Prompt:** The provider sends the same callback three times with the same attempt ID. Can we create three new `PaymentAttempt` rows and deduplicate later?

**Hint:** You may log three receipts in an audit table, but never create three payment effects. Unique provider references and idempotency must distinguish retries from new events.

### Exercise 5. Zero vs Missing

**Prompt:** A Product has no price yet, so the team fills `unit_price_vnd=0` to satisfy `NOT NULL`. Does this PASS?

**Hint:** Only if 0 is an accepted, meaningful price. Missing prices must be handled differently from zero; never assign fake defaults.

### Exercise 6. Security Differs from FK

**Prompt:** Composite FKs prevent `OrderLine` from referencing the wrong tenant, yet the `GET Order` API filters only by `order_id`. Does the security gate PASS?

**Hint:** No. Authorization must enforce the caller's tenant, include cross-tenant read tests, and optionally use DB roles/RLS.

### Exercise 7. Unknown Timezone

**Prompt:** A source stores `"2026-11-22 08:00"` with no offset/timezone. Can we cast it straight to `TIMESTAMPTZ`?

**Hint:** Not yet. Determine whether the source is UTC, store local time, or another zone; if unknown, handle as an exception rather than guessing via session timezone.

### Exercise 8. Inventory Snapshot

**Prompt:** End-of-day stock snapshot revision 1 = 20, revision 2 = 18. Is KPI `SUM = 38` correct?

**Hint:** No. Select the latest valid revision as of the cutoff, rather than summing two state versions.

### Exercise 9. Inventory Reservation Race

**Prompt:** Two requests simultaneously ask for the last two units, both reading two available from cache. Which gate did this fail?

**Hint:** Gate F on concurrency correctness. Requires an owner executing atomic, idempotent reservation operations.

### Exercise 10. Cross-Service Relationships

**Prompt:** Customer is in DB A, Order is in DB B, and the doc states "FK guarantees referential integrity." Is this acceptable?

**Hint:** No, unless an actual distributed FK exists. Document logical references, owners, protocols, and orphan reconciliation.

### Exercise 11. Currency Mismatch in Migration

**Prompt:** `amount_text="100"` has `currency=USD`, and the new column is `total_amount_vnd BIGINT`. Does casting directly to `100` pass?

**Hint:** No. Preserve the original currency or apply documented exchange rates/sources/timestamps; a valid numeric type does not guarantee the right unit.

### Exercise 12. Multiplication from JOINs

**Prompt:** An Order has 3 Lines and 2 `PaymentAttempt`s. How can directly `JOIN`ing and `SUM`ming `PaymentAttempt` go wrong?

**Hint:** The `JOIN` produces 6 rows, tripling each Attempt. Aggregate each child subset to one row per tenant/order before joining.

### Exercise 13. Indexing by Gut Feel

**Prompt:** The team indexes every column because the table will grow large, with no workload matrix. Does the physical gate PASS?

**Hint:** No. Define query/access patterns and measure plans plus write/storage overhead on representative data.

### Exercise 14. Backfill Done While Old Writers Still Run

**Prompt:** `amount_text` was migrated to `total_amount_vnd`, yet an old batch job still writes only `amount_text`. Can the old column be `DROP`ped?

**Hint:** No. The old writer introduces divergence; upgrade writers/bridges, reconcile, and contract only when zero dependencies remain.

### Exercise 15. Unexecuted Tests

**Prompt:** `T11 Confirm/DeleteLastLine` is planned but not yet executed. Can the reviewer mark it PASS?

**Hint:** No. Mark `NOT RUN`; you may approve prototyping, but cannot `GO` for production traffic if it is a P0 invariant.

### Exercise 16. Missing Retention Approval

**Prompt:** All SQL tests PASS, yet the personal data retention policy lacks approval. Can we `GO` to production?

**Hint:** Not if it is a mandatory gate. Establish clear owners/scope and release blockers rather than writing "fix later."

### Exercise 17. Choosing a Graph DB Out of Preference

**Prompt:** A team picks a graph DB because Orders relate to Customers and Products, without traversal queries or transaction tests. Does the technology gate PASS?

**Hint:** No. Compare access patterns and invariant enforcement across relational/document/graph with rationale and testing.

### Exercise 18. Enabling Guest Checkout After Approval

**Prompt:** v1 required Orders to have a Customer; v2 adds guests and makes `customer_id` nullable. Is a re-review needed?

**Hint:** Yes. Address discriminators, PII/retention, APIs, cardinalities, permissions, reporting, and history; making a column nullable alone is not enough.

## 23. Final Takeaways and Decision

Before signing off on acceptance, a reviewer needs clear answers to:

1. **What does one record represent; which key distinguishes it within which scope?**
2. **How do cardinalities and relationships change across states and time?**
3. **Who protects invariants when multiple commands run concurrently?**
4. **Do values have accurate types, units, NULL semantics, and timestamps?**
5. **Do history and aggregations preserve grain without multiplying or dropping numbers?**
6. **With what evidence do read/write flows meet security, load, SLO, and growth targets?**
7. **Can migrations, backfills, replays, restores, and error handling execute as planned?**
8. **Which tests have actually run versus merely been designed?**
9. **For open issues, are blockers, owners, deadlines, and rollout limits transparent?**

**Approving a design does not mean the model is perfect or will never evolve.** It means **scope and invariants are clear, choices of grain/keys/relationships/lifecycle are justified, enforcement mechanisms are viable, remaining risks are transparent, and every critical gate has evidence and an accountable owner**.

A model ready for implementation is one where engineers can turn it into code without inventing rules, QA can prove correctness/failure with concrete scenarios, DBAs/SREs can verify operational cost, and business owners can confirm **data is stored, mutated, and consumed faithfully to the system's commitments**.

