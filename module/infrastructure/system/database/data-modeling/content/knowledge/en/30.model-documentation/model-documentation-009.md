# Model Management in Version Control and Reviewing Alongside Code Changes

## Learning Objectives

After this lesson, you will be able to:

- Treat data model documentation as **part of a version-controlled software change**, rather than standalone diagrams saved after code has been merged.
- Distinguish **conceptual, logical, physical, domain model, integration contract, and analytical model** artifacts; identify the authoritative source for each type.
- Store and link **definitions of grain, entities, relationships, keys, constraints, lifecycle, sensitive data, owners, and design decisions** with Java code, SQL migrations, APIs/events, and metrics.
- Design pull requests (PRs) where reviewers can read **changes in business meaning**, not just line-by-line diffs of DDL or classes.
- Organize a **propose → review → merge → deploy → verify** workflow when multiple versions of applications, databases, and consumers coexist.
- Combine automated checks (docs-as-code, schema migrations, contract tests, data quality) with **human expert review**.
- Manage ADRs, Mermaid diagrams, data dictionaries, breaking changes, drift between documentation and live environments, and transition/rollback plans.
- Apply similar practices to relational, document, graph, and analytical warehouse schemas; explain why an approved model does not automatically mean production data is correct.

In the **DATABASE_DATA_MODELING** module, data design must progress from business requirements to entities, relationships, constraints, normalization, keys, indexes, and physical schemas; thereafter, it must be clear enough to verify and evolve. The **Model Documentation** chapter adds an important operational question: **when Java code, the database, events, or reports change, how do we know the model documentation still reflects reality and that everyone reviewed the same change?**

The answer is not simply putting ERD images into Git. You need a **contract for how modeling artifacts are governed**: which document is the authoritative source, which changes must accompany a PR, who has approval authority, which criteria are checked automatically, and how to know which version is deployed in a live environment. Those practices turn a model from a reference drawing into **design knowledge with history and accountability**.

## 1. The Problem: Code Changed, Diagrams Did Not

Suppose a sales system previously assumed **each order had only one shipment**. Legacy documentation drew Order — 1:1 — Shipment; the Java `Order` class might hold a single `shipmentId`; the storage table had an `order_header.delivered_at` column; the `OrderDelivered` event carried `orderId`. When the business starts splitting orders into multiple shipments, a superficial change that merely adds a `shipment` table is not enough:

- **Domain:** an Order can have multiple deliveries, each shipment having its own lifecycle. When is an Order considered fully delivered?
- **Storage:** Shipment needs its own identity and a 1:N relationship with Order. Each ShipmentLine draws quantity from an OrderLine; over-allocating beyond the ordered quantity must be prevented.
- **Integration:** the `ShipmentDelivered` event needs `shipmentId`. The old `OrderDelivered` event, if retained, must have a clear meaning and an appropriate emission timing.
- **Reporting:** the number of delivered shipments and the number of fully delivered orders are no longer the same metric.
- **Operations:** legacy order data with only `delivered_at` may be insufficient to reconstruct which shipments were delivered; history must not be fabricated arbitrarily.

If a PR updates Java and SQL but leaves the ERD as 1:1, someone writing a new report might use `COUNT(shipment_id)` as the order count. If only the ERD is updated without migrations and tests, a pretty diagram will not make the database run correctly.

**Principle:** artifacts that change **semantics** together must be reviewed **within a unified review context**, even if released across multiple steps and sometimes residing in different repositories.

## 2. Which Models Need Documentation and Where Is the Authoritative Source?

| Documentation Layer | Core Question | Artifacts Manageable in Git | Authoritative Source |
| --- | --- | --- | --- |
| **Conceptual** | What do Order, Shipment, and Reservation mean? Who owns them? | Bounded context map, glossary, business rules | Approved business/domain owner |
| **Logical** | Which entities, relationships/cardinalities, and grain? | Text-based ERD, data dictionary, invariants | Approved logical design |
| **Physical** | PK/FK/UNIQUE/CHECK, indexes, partitions, data types? | SQL migrations, schema definitions, physical design notes | Deployed migrations together with actual schema metadata |
| **Java Domain** | Which commands are allowed to change state and when? | Aggregates/value objects, unit tests, application API | Approved domain code and rules |
| **Exchange** | Which IDs, statuses, events, and versions do consumers receive? | OpenAPI/AsyncAPI/JSON schemas, contract tests | Producer's published contract |
| **Analytical** | What is a fact row? Which measures and timestamps? | Semantic model, metric definitions, lineage | Metric owner + published pipeline/model version |
| **Decisions** | Why choose 1:N, drop cross-service FKs, or use SCD2? | ADR (Architecture Decision Record) | Decision with status and approvers |

This does not mean **every fact must be manually entered in seven places**. You should choose one place as the source and generate/aggregate views whenever possible. For example, DDL migrations manage the enforced column structure; physical diagrams can be generated from the schema. However, whether a field is **PII**, which state transitions are allowed, or what `OrderDelivered` means usually **cannot be inferred** from DDL and must be described explicitly in prose.

### Three Frequently Confused States

1. **Proposed/target design:** the contents of a PR branch, which may not yet be approved or deployed.
2. **Approved design:** a model that has been merged or approved, not necessarily existing in production yet.
3. **Deployed/observed state:** the structure and contracts actually running in a specific environment, which may differ between staging and production.

Do not state in documentation that an "FK has been added" just because the migration sits in a merged branch. To know whether it has been applied, check migration/deployment metadata and inspect the live schema. **A Git commit is not a database transaction.**

## 3. Documentation Structure: Focus on Traceability, Not Tool Names

A project may use the following reference layout. This is a **structural illustration** for discussion, not a requirement to create extra files outside the current lesson:

~~~text
repository/
  docs/
    data-model/
      context-map.md             # ownership, bounded context catalog
      sales/
        glossary.md              # business definitions
        logical-model.md         # grain, relationships, cardinality, invariants
        physical-model.md        # mapping to storage
        data-dictionary.md       # columns, NULL, source, sensitivity
      fulfillment/
        logical-model.md
        data-dictionary.md
      analytics/
        delivery-metrics.md      # metric, grain, timezone, lineage
    adr/
      0042-split-shipments.md    # design decision
  src/main/java/...              # Java domain
  db/migration/...               # versioned migrations
  contracts/...                  # API/event schemas and tests
  tests/...                      # domain, migration, and contract tests
~~~

You do not need to copy this exact structure. The required properties are:

- **Discoverable:** reviewers know where a bounded context's model lives and who is responsible.
- **Diffable:** text-based documentation (Markdown, Mermaid, DDL, JSON Schema, YAML) changes line by line; exported images are viewing renders only.
- **Linkable:** model docs point to related decision IDs, migrations, contracts, tests, and metrics via stable paths/identifiers.
- **Historical:** you can inspect who changed a grain's meaning, why, when, and alongside which version.
- **No duplicated authority:** if a schema tool generates DDL, state clearly which tool/schema is the source of truth, rather than having a design file, SQL file, and manual document all treated as authoritative without precedence.
- **No environment mixing:** production schema paths or snapshots cannot be used as target designs when the new release is not yet deployed.

### A Minimum Model Profile

For each important model, documentation should answer:

| Field | Example | Reason |
| --- | --- | --- |
| Model ID | fulfillment.shipment | Stable lookup and linking |
| Business owner | Delivery Operations Team | Approves business meaning |
| Technical owner | Fulfillment Team | Responsible for implementation |
| Status | proposed / approved / deployed | Avoid confusing plans with current state |
| Grain | One fulfillment delivery of a shipment | Prevent miscounting |
| Identity | (tenantId, shipmentId) | Retries, linking, identity partitioning |
| Cardinality | Order 1:N Shipment | Validate join paths |
| Invariants | Total allocated quantity does not exceed OrderLine | Identify transaction/source-of-truth |
| Sensitive data | Shipping address, recipient | ACLs, retention, data minimization |
| Temporal meaning | deliveredAt is when delivery succeeded | Avoid confusing with publishedAt |
| Related artifacts | ADR-0042, migration, event schema, tests | Trace changes |
| Compatibility | Old writers and v1 consumers active until milestone X | Plan rollout |

**A document's version is not an arbitrary incrementing number.** You can use commit hashes, release tags, migration versions, and event `schemaVersion` for different purposes. More importantly, you should be able to show **which versions worked together** in a given configuration.

## 4. Logical Model Example: From Single Shipment to Multiple Shipments

Requirements clarified with the business:

- An Order can be fulfilled as multiple Shipments.
- A Shipment has ShipmentLines; each line points to its source OrderLine via a stable identifier and carries a positive quantity.
- Shipment has statuses `REQUESTED`, `PACKED`, `DISPATCHED`, `DELIVERED`, or `CANCELLED` following an appropriate lifecycle.
- **Fulfillment** manages Shipments and allocates item quantities to Shipments; **Sales** manages Orders. The two contexts communicate via IDs and contracts, without allowing Fulfillment to arbitrarily mutate Order status.
- Total quantity allocated across active Shipments for an OrderLine **must not exceed the ordered quantity** under the allocation policy; an authoritative arbitration/transaction point is required.
- An Order is only considered **fully delivered** under agreed criteria (for example, all deliverable quantities have been successfully delivered, with no open requests remaining). Do not infer this merely from the existence of a Shipment with `deliveredAt`.

### Old and New Logical Diagrams in the PR

~~~mermaid
flowchart LR
    subgraph Old["Before change"]
        O1["Order<br/>shipmentId? / deliveredAt?"]
        S1["Shipment<br/>at most one per Order"]
        O1 ---|"0..1"| S1
    end
    subgraph New["After change"]
        O2["Order<br/>Sales context"]
        S2["Shipment<br/>Fulfillment context"]
        SL["ShipmentLine<br/>quantity, orderLineId"]
        O2 ---|"0..N"| S2
        S2 ---|"1..N"| SL
    end
~~~

**Note on cardinality:** this example allows an Order with no Shipments created yet (`0..N`) and requires each active Shipment to have at least one line (`1..N`). Rules such as whether a `DRAFT` Shipment may be temporarily empty must be clarified; if allowed, annotate `0..N` for the `DRAFT` phase or distinguish by status. Do not draw `1..N` when the actual domain permits having no lines yet.

This is a **logical model**; it does not immediately dictate a cross-database FK from Shipment to `Sales.Order`. The 1:N relationship is defined by semantics and IDs; whether an FK can be enforced depends on storage boundaries.

### Data Dictionary Table for the New Model

| Concept/Field | Meaning and Grain | Constraints / Decision Source |
| --- | --- | --- |
| OrderId | Sales order identifier | Unique within tenant per Sales |
| ShipmentId | Identifier of a shipment/delivery fulfillment | Issued by Fulfillment, distinct from OrderId |
| Shipment.orderId | Reference to source Order | Does not grant authority to mutate Order |
| ShipmentLine.orderLineId | Reference to source order line | Must resolve against authoritative mapping |
| ShipmentLine.quantity | Quantity allocated to the shipment | >0; cross-shipment sum enforced by allocation owner |
| Shipment.status | Shipment lifecycle state | Has a valid set of transitions |
| Shipment.deliveredAt | Timestamp when a shipment was successfully delivered | NULL if undelivered; do not substitute ingest time |
| OrderDeliveryComplete | Order-level completion fact | Emitted only when completion criteria for *all deliverable items* are met |
| ShipmentDelivered | Fact of a single shipment's successful delivery | Carries shipmentId, orderId, eventId, schemaVersion |

The dictionary explains the **meaning** of the data. DDL will enforce part of it via `NOT NULL`, `CHECK`, and internal FKs; the cross-Shipment total allocation rule may require a Fulfillment transaction/aggregate or ledger and does not disappear simply because the ERD connects the boxes correctly.

## 5. Physical Documentation Accompanying Migrations: What Does the Database Protect?

Suppose Shipment is stored separately in Fulfillment's PostgreSQL database, while Order belongs to Sales. A **proposed** migration might look like:

~~~sql
CREATE SCHEMA IF NOT EXISTS fulfillment;

CREATE TABLE fulfillment.shipment (
    tenant_id UUID NOT NULL,
    shipment_id UUID NOT NULL,
    order_id UUID NOT NULL,  -- external reference to Sales
    status VARCHAR(16) NOT NULL
        CHECK (status IN (
            'REQUESTED', 'PACKED', 'DISPATCHED',
            'DELIVERED', 'CANCELLED'
        )),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    dispatched_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    version BIGINT NOT NULL DEFAULT 0 CHECK (version >= 0),
    PRIMARY KEY (tenant_id, shipment_id),
    CHECK (status <> 'DELIVERED' OR delivered_at IS NOT NULL),
    CHECK (delivered_at IS NULL OR delivered_at >= created_at)
);

CREATE TABLE fulfillment.shipment_line (
    tenant_id UUID NOT NULL,
    shipment_id UUID NOT NULL,
    shipment_line_no INTEGER NOT NULL CHECK (shipment_line_no > 0),
    order_line_id UUID NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (tenant_id, shipment_id, shipment_line_no),
    FOREIGN KEY (tenant_id, shipment_id)
        REFERENCES fulfillment.shipment(tenant_id, shipment_id),
    UNIQUE (tenant_id, shipment_id, order_line_id)
);

CREATE INDEX shipment_by_order
    ON fulfillment.shipment (tenant_id, order_id, created_at DESC);

CREATE INDEX shipment_open_by_status
    ON fulfillment.shipment (tenant_id, status, created_at)
    WHERE status NOT IN ('DELIVERED', 'CANCELLED');
~~~

**Review documentation must state what DDL cannot express:**

- DDL guarantees each Shipment has a unique ID and child lines belong to an existing Shipment in the same database.
- There is no FK from Fulfillment to `Sales.Order`, because the two contexts may reside in separate databases. You need a **contract to verify `orderId`/`orderLineId`**, tenant authorization, handling of deleted Orders, and late-arriving events.
- `UNIQUE` on `(tenant, shipment, orderLineId)` prevents repeating an OrderLine within the same Shipment under the example policy. It **does not prevent** the same OrderLine from appearing across two Shipments with a combined quantity exceeding the ordered amount.
- `CHECK` constraints on status and timestamps do not protect every state transition path, such as preventing `DELIVERED` from reverting to `PACKED`. The domain root and conditional/versioned `UPDATE` statements must enforce this.
- If a ShipmentLine needs multiple lots/batches for the same OrderLine within **one Shipment**, the `UNIQUE` constraint above may be inappropriate; clarify the grain before keeping it.
- The partial index for open shipments is only a candidate based on expected queries; measure actual workloads before concluding it is optimal.

### Protecting Against Over-Allocation Beyond Ordered Quantity

To prove that an OrderLine cannot be over-allocated, the model must specify **who the arbitrator is**. For example, Fulfillment owns an allocation ledger keyed by `(tenantId, orderLineId)` where the active allocated quantity is atomically checked and adjusted when creating or cancelling a Shipment. An illustrative SQL approach:

~~~sql
CREATE TABLE fulfillment.order_line_allocation (
    tenant_id UUID NOT NULL,
    order_line_id UUID NOT NULL,
    allowed_quantity INTEGER NOT NULL CHECK (allowed_quantity > 0),
    allocated_quantity INTEGER NOT NULL DEFAULT 0
        CHECK (allocated_quantity >= 0),
    version BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, order_line_id),
    CHECK (allocated_quantity <= allowed_quantity)
);

-- Transaction for the AllocateToShipment command:
UPDATE fulfillment.order_line_allocation
SET allocated_quantity = allocated_quantity + :quantity,
    version = version + 1
WHERE tenant_id = :tenant_id
  AND order_line_id = :order_line_id
  AND :quantity > 0
  AND allocated_quantity <= allowed_quantity - :quantity
RETURNING allocated_quantity;

-- Only when UPDATE returns exactly one row, within the same transaction
-- INSERT shipment_line. Otherwise, ROLLBACK the entire command.
~~~

**Assumption of the example:** `allowed_quantity` is obtained from an order snapshot/contract confirmed by Sales and maintained by Fulfillment under a clear ownership protocol. When Sales adjusts or cancels an OrderLine, the system must have a workflow to reconcile/adjust the allocated portion; checking this column **does not automatically stay in sync** with Sales in another database.

At review time, distinguish between:

1. **Invariant:** total allocation does not exceed the allowed limit.
2. **Enforcement strategy:** conditionally updating a single allocation row inside an internal transaction.
3. **Preconditions:** `allowed_quantity` is accurate, requests are idempotent, and release commands do not subtract twice.
4. **Evidence:** integration tests with two concurrent requests competing for the last remaining units, rollback test when `INSERT shipment_line` fails, retry tests, and tests for Sales reducing quantity.

A diagram with neat connecting lines cannot replace those four answers.

## 6. Creating a Semantic Diff: Review Meaning, Not Just ALTER TABLE Statements

`git diff` shows which lines of text changed, but **it does not explain business impact on its own**. A PR changing cardinality needs a summary table:

| Aspect | Before | After | Impact / Compatibility |
| --- | --- | --- | --- |
| Order–Shipment relationship | At most one Shipment/Order | 0..N Shipments/Order | Clients cannot assume a single shipmentId |
| Delivery identity | orderId sufficient to find shipment | Separate shipmentId required | Events, URLs, and idempotency keys change |
| Delivery status | deliveredAt at Order level | deliveredAt at Shipment level; Order aggregates | One old timestamp cannot represent all shipments |
| Item allocation | Implicit whole order in one shipment | Multiple ShipmentLines referencing OrderLine | Adds invariant against over-allocation |
| REST response | Single shipment object | shipments collection or dedicated endpoint | Potentially a breaking change |
| Event | OrderDelivered | ShipmentDelivered and/or OrderDeliveryCompleted | Two distinct facts; do not rename blindly |
| KPI | Delivered orders | Delivered shipments and completed orders | Grain and counting logic must be separated |
| Historical data | Single deliveredAt | Details of old shipments unknown | Backfill only with evidence |
| Ownership | Sales may hold deliveredAt | Fulfillment owns Shipment state | Shared writes prohibited |

A **semantic diff** is also needed for smaller changes such as:

- Changing `NULL` from "unknown" to "not applicable".
- Changing status `PAID` from "authorized" to "captured".
- Changing currency from VND to thousands of VND or changing the timezone used for daily grouping.
- Renaming a column while also changing its business scope.
- Changing a fact table's grain from "one order" to "one shipment".
- Adding a `UNIQUE` constraint that could reject valid historical data.
- Splitting an embedded document array into a separate collection with different atomicity guarantees.

A change that only adds a nullable column can still **break contracts** if its side effects alter the meaning of an existing field. Conversely, renaming an internal column may not affect APIs at all if repositories and contracts are properly decoupled.

### Categorizing Changes to Choose Review Depth

| Change Type | Example | Primary Reviewers |
| --- | --- | --- |
| Presentation/docs without meaning change | Fixing typos in field descriptions | Doc owner / technical owner |
| Backward-compatible addition | Adding an optional field with clear meaning, new index | Domain owner + DB owner |
| Invariant/cardinality change | 1:N Shipment, changing allocation rules | Business owner + domain + data/DB |
| Public contract change | Changing payload, enum, currency unit | Producer + consumer representatives |
| Grain/KPI change | Separating shipment count and order count | Data/BI owner + business |
| Security/data lifecycle change | Adding shipping address, changing retention | Security/privacy + data owner |
| Breaking migration | Dropping fields, changing data types, modifying PK | DB/platform + all dependent owners |

Not every PR requires a company-wide meeting. However, every change with **semantic impact** must be reviewed by the person **accountable for that meaning**.

## 7. A Pull Request Is an Evidence Package for a Model Change

A good PR answers **why it changes**, **what changes**, **who is affected**, and **how it is deployed and verified**. Illustrative template:

~~~markdown
# PR: Allow an Order to be split into multiple Shipments

## Context and Decisions
- Requirement: fulfill a single order across multiple warehouses/waves.
- Business owner: Fulfillment.
- Decision: ADR-0042; Order 0..N Shipment.
- Out of scope: merging multiple customers' orders into one Shipment.

## Model Changes
- Domain: dedicated ShipmentId; allocation authority belongs to Fulfillment.
- Logical: 1:N relationship; ShipmentLine references OrderLine.
- Storage: add shipment, shipment_line, allocation.
- Exchange: ShipmentDeliveredV1, API versioning per policy.
- Analytics: separate shipment_count and completed_order_count.

## Compatibility and Legacy Data
- Which old writers are currently running?
- Can old readers read multi-shipment data?
- Can history be backfilled? Which data must remain UNKNOWN?
- When can legacy fields safely be removed?

## Deployment and Verification
- Expand schema -> deploy readers/writers -> feature gate.
- Concurrency, retry, migration, contract, and KPI reconciliation tests.
- Monitoring metrics and rollback/roll-forward thresholds.
- Test environment evidence: migration version, test runs, query diff.

## Reviews
- [ ] Business/domain owner
- [ ] DB/platform owner
- [ ] API/event consumer owners
- [ ] Analytics/metric owner
- [ ] Security/privacy if sensitive data changes
~~~

**Note:** checkboxes in a PR description are not automatic proof that accountable owners actually approved. Use `CODEOWNERS`, branch protection, review approvals, and decision audit trails per organizational policy. Self-checked boxes by the author do not replace independent approval.

### Files That Should Travel Together in a Change

When changing relationships and invariants, the corresponding artifact groups are usually needed:

- **Design:** text-based ERD/diagrams, data dictionary, business glossary, ADR.
- **Implementation:** Java domain classes/behaviors, repository mappers, SQL migrations or document schemas.
- **Communication:** request/response schemas, integration event schemas, versioning/changelog.
- **Analytics:** fact grain, dim mappings, metric definitions, views/semantic layer.
- **Testing:** domain unit tests, DB integration tests, contract tests, migration tests, data quality checks.
- **Rollout:** feature flag plan, backfill, monitoring, rollback/roll-forward plan.

They do not all have to be in **one atomic commit** if doing so cannot be deployed safely. A shared **initiative/issue** can link multiple incremental PRs; each PR must be safe against currently running versions and clearly state the next step.

## 8. ADRs: Record the Reasons, Not Just the Outcome

Diagram documents answer **how it was designed**; ADRs explain **why it was chosen when alternatives existed**. Example:

~~~markdown
# ADR-0042: Fulfillment owns Shipment and item allocation
Status: Accepted
Date: 2026-11-22
Decision owners: Sales, Fulfillment, Data Platform

## Context
An Order can be split into multiple shipments; Sales and Fulfillment
have separate databases. We must not over-allocate beyond ordered quantity.

## Decision
- Shipment has its own shipmentId and references orderId.
- Fulfillment owns the allocation ledger.
- Sales does not write directly to Shipment tables.
- ShipmentDelivered is a shipment-level fact.
- OrderDeliveryCompleted has its own completion criteria.

## Alternatives
1. Embed a shipments array inside the Order aggregate.
2. Shared database with cross-context FKs/transactions.
3. Fulfillment manages Shipments and communicates via contracts.

## Consequences
- Intermediate/pending states, retries, and eventual consistency exist.
- Order modifications/cancellations while Shipments exist must be handled.
- Reporting must separate Order metrics from Shipment metrics.

## Validation
- Race test on the last remaining item units.
- Event contract tests and replay.
- Migration/backfill reconciliation against historical data.
~~~

ADRs can carry statuses such as **Proposed, Accepted, Superseded, Rejected**. When changing a decision, create a new ADR linking the old one or mark **Superseded by** per process; do not silently rewrite the context section to make it look as though the new decision existed from the start.

ADRs do not replace every detail in a data dictionary. A 1:N decision may only need an ADR once; columns, data types, and indexes continue to be maintained in the appropriate model/schema profile.

## 9. Git Workflow: Design Versions Are Not Database Versions

A practical workflow:

1. Create an issue and confirm business scope, owners, and data consumers.
2. Write a **model change proposal** and semantic diff on a feature branch; discuss hard-to-reverse changes upfront.
3. Add migrations, Java code, contracts, documentation, and tests for **one safe deployment step**.
4. Run automated checks, get owner reviews, and resolve comments directly in the PR.
5. Merge once review criteria are met; mark which steps remain **undeployed**.
6. Deploy in compatibility order, run controlled migrations, and reconcile results.
7. Record the migration version, artifact version, schema contract version, and deployment timestamp.
8. Observe and resolve discrepancies; update documentation status to match what is actually running.

### A Single Change Has Multiple Version Clocks

| Identifier | What Does It Version? | Example |
| --- | --- | --- |
| Git commit SHA | Source/docs content at a commit | Commit C123 |
| Application build/release | Deployed binary | sales-service 4.2 |
| DB migration version | Structure/data transformation step | V0042_create_shipments |
| Actual database schema | Constraints/tables/indexes present | Verified via catalog/migration history |
| API/event schemaVersion | Contract read by consumers | ShipmentDelivered v1 |
| Analytics transformVersion | Fact/metric loading logic | fulfillment-mart v3 |
| ADR ID/status | Decision and supersession history | ADR-0042 Accepted |

**Do not use a single version number across all layers.** One commit may contain multiple migrations; one API v1 may span many releases; an event v2 may be supported alongside v1; a data mart may rebuild with a new transform even when source tables have not changed.

To reproduce a report or investigate an incident, you need to know **which application build, migration, event schema, pipeline, and metric definition** were active at that time. Git history is only one part of that evidence.

### Guidelines for Large Pull Requests

If a PR bundles hundreds of unrelated changes, it is hard to verify results. You can split it into a sequence of PRs:

- **PR A — compatible expansion:** add tables/fields; readers support both formats.
- **PR B — backfill and reconciliation:** populate historical data using justified rules.
- **PR C — enable functionality:** write new data, emit new events/metrics.
- **PR D — clean up legacy structure:** only when no dependencies remain.

All PRs remain linked to the same issue/ADR and share a unified rollout plan. Do not drop constraints or old columns in PR A while old binaries are still running.

## 10. Docs-as-Code: What CI Can Check

**Docs-as-code** means documentation participates in the same version control, review, build, and release lifecycle as code. It does not mean all business correctness can be verified automatically.

A reference check pipeline:

~~~mermaid
flowchart LR
    PR["Pull request"] --> L["Markdown + links + diagram lint"]
    PR --> M["SQL migration<br/>schema diff / dry run"]
    PR --> C["Java + contract tests"]
    PR --> T["Data/metric tests"]
    L --> G{"Automated gates PASS?"}
    M --> G
    C --> G
    T --> G
    G -->|"Yes"| R["Owner review<br/>semantics + risk"]
    G -->|"No"| F["Fix and rerun"]
    R --> A["Approval + merge"]
~~~

Check groups:

| Gate | Automatically Verifiable | Still Needs Human Reviewer |
| --- | --- | --- |
| Markdown/diagram | Broken links, syntax, heading IDs, Mermaid rendering | Does the 1:N diagram match requirements? |
| Model metadata | Missing owner, status, grain, ADR reference | Is the listed owner actually accountable? |
| SQL migration | Syntax, migration ordering, DDL execution on test DB, schema diff | Will backfill lose history or overload production? |
| Schema constraints | Expected PK/FK/UNIQUE/CHECK present; migration catches dirty data | Could a constraint reject valid scenarios? |
| Java tests | Invariants, boundary errors, optimistic locking against real DB | Does the root own the right business rules? |
| API/event contract | Field/type/schema compatibility, consumer tests | Does the event still have the same meaning? |
| Data pipeline | Grain uniqueness, NOT NULL, relationships, reconciliation values | Does the KPI match the business definition? |
| Security check | Sensitive data exposed openly in schemas/contracts | Are access controls and retention fit for purpose? |

### Logical Gate Declaration Template

You do not need to tie this to one specific CI tool. A conceptual specification can be written as:

~~~yaml
# Example workflow concept; job/command names must be mapped to the actual project.
model_change_checks:
  required:
    - markdown_and_link_validation
    - diagram_render_validation
    - migration_on_disposable_database
    - migration_schema_diff
    - domain_unit_tests
    - database_concurrency_tests
    - api_event_contract_compatibility
    - analytical_grain_and_metric_tests
  human_approvals:
    - fulfillment_domain_owner
    - database_owner
    - integration_consumer_owner
    - analytics_metric_owner
~~~

This is an **illustrative checklist**, not syntax for GitHub Actions, GitLab CI, or any particular pipeline engine. In real implementation, use actual runners, authentication, test databases, and artifacts.

### Should Diagrams Be Source Text or Image Files?

Prefer storing **diagrams as text** such as Mermaid/PlantUML/DBML when appropriate so you can:

- Diff individual relationships/cardinalities in Git.
- Re-render when themes or UI change.
- Validate syntax in CI.
- Link cleanly with data dictionaries and PRs.

PNG images can serve readers, but if they are the **sole source**, reviewers struggle to tell which relationship changed, and images easily go stale when code changes. Conversely, a diagram auto-generated from the database only shows what the database knows—it cannot know business rules, bounded contexts, or event contracts on its own.

**Therefore, there is no "single diagram to replace all documentation."** Maintain meaningful logical models and generate physical diagrams from schemas where reliable tooling exists; make the relationship between them explicit.

## 11. Reviews Must Address Concurrency and Historical Data

In the Shipment example, reviewers do not merely confirm the table has a primary key; they also ask what happens when two workers concurrently allocate the last remaining units.

### Contention Scenario

OrderLine `L` has `allowedQuantity=5` and `allocated=3`. Two independent concurrent requests each request an additional `quantity=2` for two different Shipments.

If the code executes:

~~~text
SELECT allocated_quantity  -- both A and B see 3
IF 3 + 2 <= 5:
    INSERT shipment_line    -- A inserts 2, B also inserts 2
    UPDATE allocated_quantity ...
~~~

without proper locking, versioning, or transactions, a total of 7 units could be granted against an allowance of 5.

A conditional `UPDATE` on the **same ledger row** combined with inserting the shipment line within the **same transaction** allows only one request to succeed under contention. With appropriate PostgreSQL mechanisms, the second request must re-evaluate the condition after the first commits, rather than relying on a stale `SELECT`.

### Test Results to Include in the PR

| Test | Setup | PASS Condition |
| --- | --- | --- |
| Two competing requests | allocated=3, allowed=5, each requests 2 | Only one allocation of 2 succeeds |
| Failure after ledger UPDATE | Simulate `INSERT shipment_line` failure | Ledger update rolls back |
| Retry with same requestId | Repeat an already succeeded command | Does not create a second ShipmentLine or allocation |
| Cancel a Shipment | Send Cancel twice | Ledger releases quantity exactly once |
| Sales reduces quantity | allowed_quantity drops from 5 to 4 when 5 already allocated | Has rejection/adjustment workflow; never forces CHECK by deleting data |
| Cross-tenant mismatch | Tenant A's shipmentId used by B | Rejected |
| Non-existent OrderLine reference | Event/command arrives before source data | Wait/reconcile or contract error; never fabricate data |

**A sequential mock repository does not prove race-condition safety.** Concurrency tests must run against a real database or an environment with equivalent isolation/locking semantics and verify post-commit state, not just HTTP status codes.

### Model Documentation Must Explain Exceptions

If an OrderLine is intentionally allowed to over-allocate quantity in a backorder/pre-allocation workflow, the `allocated<=allowed` constraint is no longer valid. Reviewers must clarify the **over-allocation** policy before applying a `CHECK` constraint; do not secretly alter rules just to pass tests.

If a Shipment can be reopened or transition backward from `DELIVERED` to `RETURNED`, a state machine treating `DELIVERED` as terminal will be incomplete. Documentation should list **supported states and exception cases** before writing enums/constraints.

## 12. Versioning Integration Contracts and Reporting Models in the Same Review

Suppose the legacy **OrderDelivered** event has the payload:

~~~json
{
  "eventType": "sales.order-delivered",
  "schemaVersion": 1,
  "eventId": "0f9cd680-b371-4d67-95b3-2e6092814ced",
  "tenantId": "76cf77e5-a024-4e2d-8e2b-fb571b6416ad",
  "orderId": "e99b0311-3c0a-45f2-bb59-a2be1bb29f47",
  "deliveredAt": "2026-11-02T10:00:00Z"
}
~~~

After supporting multiple shipments, a new **ShipmentDelivered** fact might be:

~~~json
{
  "eventType": "fulfillment.shipment-delivered",
  "schemaVersion": 1,
  "eventId": "f4f5ed38-4a6d-4711-a9ae-2a868ad0baf6",
  "tenantId": "76cf77e5-a024-4e2d-8e2b-fb571b6416ad",
  "orderId": "e99b0311-3c0a-45f2-bb59-a2be1bb29f47",
  "shipmentId": "0e4ea4f8-dff9-4950-bc8c-388f219dce14",
  "deliveredAt": "2026-11-02T10:00:00Z"
}
~~~

The two JSON payloads cannot be treated as equivalent just because both carry `deliveredAt`:

- **OrderDelivered** previously could be interpreted as **the entire Order was delivered**.
- **ShipmentDelivered** only proves **one Shipment** was delivered, not that the remaining items were delivered.
- Changing `eventType` while keeping the same payload does not preserve the old meaning.
- If v1 consumers are still served, a separate workflow must emit **OrderDeliveryCompleted** only once Order-level completion criteria are actually met, or provide a contract-compliant adapter, rather than firing `OrderDelivered` every time a single Shipment succeeds.
- **eventId** identifies a specific fact that occurred and must not be regenerated on broker redelivery; deduplication and stream ordering must be designed accordingly.

### Analytical Models Must Not Change Grain While Keeping the Same Metric Name

A fact for delivered Shipments has the grain **one delivered Shipment**. An Order completion fact or projection has the grain **one completed Order delivery**. Consider the query:

~~~sql
-- Assume mart.fact_delivered_shipment has exactly one row per Shipment.
SELECT delivery_business_date,
       COUNT(*) AS delivered_shipments,
       COUNT(DISTINCT order_id) AS orders_with_a_delivered_shipment
FROM mart.fact_delivered_shipment
WHERE tenant_id = :tenant_id
  AND delivery_business_date >= DATE '2026-11-01'
  AND delivery_business_date <  DATE '2026-12-01'
GROUP BY delivery_business_date
ORDER BY delivery_business_date;
~~~

**`orders_with_a_delivered_shipment` is not the count of fully delivered Orders.** An Order with two shipments, where only one has been delivered, is still counted in that column. To count completed Orders, you need an authoritative source determining that **all required deliverable quantities are finished** and recording a separate Order-level event/state.

If an Order has one Shipment delivered on Nov 02 and another on Nov 03, the count of orders with a delivered shipment includes it **on both days**; summing daily `COUNT(DISTINCT order_id)` does not yield unique orders for the month. Reviewers must see this calculation clearly in the semantic diff to prevent broken dashboards.

### Finalizing Contracts with Consumers and BI

In the PR or linked issue, determine:

- Which consumers receive `OrderDelivered` v1, and which fields/statuses do they still depend on?
- Will the producer continue emitting the v1 event with accurate semantics, or must a new contract be published?
- When recomputing history, which old events lack `shipmentId` and must retain an `unknown` value?
- Does BI change denominators, cohorts, or time granularity?
- When upgrading reports, are `metricVersion` and effective dates recorded, and do previously published figures need restatement?

**Adding a field in JSON may be syntactically compatible without guaranteeing semantic compatibility.** Correctness does not stop at the schema registry.

## 13. Verifying Changes Across All Four Layers

A strong model PR should include a **cross-layer verification matrix**:

| Layer | Checks | Evidence Examples |
| --- | --- | --- |
| **Java Domain** | Prevent empty Shipments when status forbids it; valid transitions | Unit/property tests |
| **Database** | PK/FK, CHECK, rollback, contention, index performance | Integration tests + query plans |
| **Mapper** | Read legacy and new data; preserve identity/tenant/NULL properly | Round-trip tests |
| **API** | Single Order with multiple Shipments returns unambiguous responses | Consumer-driven contract tests |
| **Event** | `ShipmentDelivered` is not misinterpreted as `OrderDelivered` | Contract + semantic scenarios |
| **Pipeline** | Duplicate/late events do not multiply fact rows | Replay/idempotency tests |
| **Analytics** | Shipment count and completed Order count match grain | Metric reconciliation |
| **Security** | Tenant A cannot read/write Tenant B's Shipments | Authorization tests |
| **Migration** | Legacy data preserves meaning without losing history | Backfill report + diff |
| **Operations** | New schema still works while old/new binaries coexist | Mixed-version integration |

Not every change needs every single test type. However, **whichever layer a change touches must have evidence proving that layer is correct**. A conceptually approved model does not prove DDL runs cleanly on PostgreSQL or that fact ETL avoids duplicating rows.

### Verification Reports with Concrete Numbers

Illustrative quality gates:

- **Identity:** `COUNT(DISTINCT (tenantId, shipmentId))` matches Shipment count, with zero duplicate business keys.
- **Validity:** count of `ShipmentLine` rows with `quantity<=0` equals 0.
- **Allocation bounds:** zero `OrderLine` rows where active allocated quantity exceeds `allowedQuantity`.
- **Migration completeness:** legacy Orders clearly classified as backfilled, skipped with reason, or needing reconciliation; never turn skipped into "no data".
- **Contract:** producer v1/v2 events tested against supported consumers or schema fixtures.
- **Freshness:** BI projections carry watermarks and handle late data without publishing provisional numbers as finalized.
- **Conservation of totals:** when changing grouping, shipment/order counts reconcile at their respective grains; do not assume they must be equal.

For large systems, thresholds should be **risk-based**. For example, a 1-VND discrepancy in payment data should not be deemed acceptable just because it is a tiny percentage of the monthly total, whereas ingestion latency on a BI event may be acceptable within published SLAs.

## 14. Detecting Drift: Documentation, Migrations, and Environments Are Not Identical

**Model drift** occurs when one or more representations no longer match the approved meaning or structure:

- Someone creates an index directly in production without a migration in Git.
- DDL is merged, but the migration failed in one environment.
- An ORM auto-modifies the schema on startup outside the migration workflow.
- Consumers still interpret a status using old semantics even though the event producer changed.
- The data dictionary claims an Order has one Shipment while production data already contains multiple shipments.
- A dashboard still `SUM`s shipment counts while labeling the metric "order count".

### Comparing Physical Structure

PostgreSQL can be inspected via live metadata:

~~~sql
SELECT table_schema, table_name, column_name,
       data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'fulfillment'
  AND table_name IN ('shipment', 'shipment_line')
ORDER BY table_name, ordinal_position;
~~~

Metadata shows **actual columns present**, but does not prove indexes, `CHECK` constraints, FKs, partitions, or business rules. Full schema diffing requires inspecting catalog/migration metadata and using comparison tools capable of representing those objects.

A drift detection mechanism should:

1. Determine the **expected schema** from approved migrations.
2. Read **applied migration versions** and the live schema from the target environment.
3. Compare meaningful differences; distinguish unapplied migrations from out-of-band changes.
4. Include **semantic checks** from model documentation, not just column name comparisons.
5. Open issues/incidents for discrepancies with owners and reconciliation plans; do not blindly patch production before source/ownership is clear.

**Schema drift is not always an error requiring immediate rollback.** For example, an index added during an incident might be reducing load; it should be documented, formalized into a migration, or dropped upon approval rather than leaving Git unaware indefinitely.

### Tracking Deployment Status Across Environments

| Environment | App Release | Applied Migration | Event Contract | Fact Transform | Documentation Status |
| --- | --- | --- | --- | --- | --- |
| Development | Fulfillment 4.2 | V0042 | v1 | v3 | Proposed/Testing |
| Staging | Fulfillment 4.2 | V0042 | v1 | v3 | Verified staging |
| Production | Fulfillment 4.1 | V0041 | Legacy v1 | v2 | Legacy deployed |

This table is a **hypothetical example**, not a real environment. It illustrates why merging a PR cannot be equated with a completed rollout. Environments may roll out incrementally, consumers may upgrade slowly, and data marts may still have lag/backfill pending.

## 15. Reviewing Alongside Code: Who Owns Which Question?

To avoid "everyone reviewed, nobody took responsibility," clarify boundaries:

| Role | Questions to Verify | Expected Evidence |
| --- | --- | --- |
| **Business/domain owner** | Do grain, cardinality, statuses, and exceptions match real business operations? | Approved decisions/semantics |
| **Developer/aggregate owner** | Does the Java root protect invariants? Can data load/rehydrate cleanly? | Unit tests, command flows |
| **Database/data modeler** | Are keys, FKs, CHECKs, indexes, isolation, and partitions suitable? | Schema review, migration tests |
| **Integration/API owner** | Do consumers understand fields/events accurately? Are versioning and idempotency handled? | Contract tests, consumer acknowledgments |
| **Analytics/metric owner** | Are fact grain, dimensions, KPIs, history, and freshness accurate? | Metric specs and reconciliation |
| **Security/privacy owner** | Are sensitive data, tenant access, and retention appropriate? | Access/lifecycle review |
| **Operations/platform** | Are deploy, backfill, and rollback/roll-forward safe and observable? | Runbooks, rollout plan |

On small projects, the model author may wear multiple hats. Still, **at minimum, the person defining business semantics and the person safeguarding data correctness must understand the change together**. A reviewer looking only at migration files may miss that `OrderDelivered` changed meaning; a reviewer looking only at APIs cannot evaluate database locking.

### Verification-Oriented Review Questions

Instead of asking "Does the ERD look nice?", ask:

1. **Grain and identity:** what does one row/entity represent, and are IDs unique and stable across retries?
2. **Cardinality:** `0..N` or `1..N`? Do transient states or missing data invalidate assumptions?
3. **Invariants:** which rules must hold at `COMMIT` and who is the authoritative arbitrator?
4. **Migration:** how will old rows be read? Can we tell with certainty what a legacy Shipment corresponds to?
5. **Compatibility:** do old binaries, old clients, and v1 event consumers still work with the new data?
6. **Traceability:** if a metric is wrong, can we trace back from the metric to events, source records, migrations, and code versions?
7. **Privacy:** are unnecessary personal/address fields being added to events or reports?
8. **Measurement:** is `COUNT(*)` counting orders, shipments, or `ShipmentLine` rows? Which metrics shift after rollout?
9. **Testing:** which test fails if the design is right but the implementation is wrong?
10. **Rollout:** at what point can we roll back to old binaries, and at what point must we only roll forward?

If any question lacks evidence, the PR should explicitly document **open assumptions and risks**, the accountable owner, and conditions to resolve before enabling the feature. Do not rubber-stamp an unverified constraint just because CI is green.

### Resolving Conflicts Between Reviewers

Suppose Sales argues **an Order can be marked `DELIVERED` once one shipment succeeds**, while Fulfillment argues all quantities must be delivered. This is a **semantic conflict**, not an enum naming debate. Teams must agree on:

- shipment-level status vs. order-level status;
- the meaning of partial delivery;
- who owns the decision for `OrderDeliveryCompleted`;
- which legacy reports must be updated or renamed;
- how in-flight orders will transition.

Only after agreement should contracts/transitions and tests be written; never let two teams quietly apply two different interpretations to the same enum.

## 16. Documenting by Storage Paradigm: Relational, Document, Graph, Analytical

There is no single mandatory ERD template for every technology. **Common questions** cover grain, identity, relationships, invariants, lifecycle, access patterns, and versioning. **Physical representations** vary:

| Physical Model | Artifacts to Review | Paradigm-Specific Pitfalls |
| --- | --- | --- |
| **Relational** | DDL/migrations, logical ERD, PK/FK/UNIQUE/CHECK, indexes, transactions | Locking, isolation, constraint validation, existing dirty data failing new UNIQUE/FK |
| **Document** | Document JSON Schema, embed/reference decisions, version/TTL policies | Old readers missing fields, full-document replacement wiping new fields, single vs. multi-doc atomicity |
| **Graph** | Node/edge types, direction/cardinality, traversal queries, constraints | Wrong edge direction, ownership boundaries, cycles and supernodes/high cardinality |
| **Time-series** | Series identity, event time, buckets, retention, rollups | Changing cadence/resolution, late-arriving data, history loss on TTL |
| **Analytical** | Fact grain, dimensions/SCD, metric formulas, lineage | Fan-out double counting from JOINs, changing recognition dates, report version drift |

### Document Stores: Also Review Backward Reading

Suppose an old Order document had a single `shipmentId`, while the new document has `shipments[]`:

~~~json
{
  "orderId": "O-1001",
  "modelVersion": 2,
  "shipmentIds": ["S-11", "S-12"]
}
~~~

If an old writer only understands a single `shipmentId`, reading a new document and **overwriting the whole document** can erase the second Shipment. The PR must explain **when old writers are blocked**, how new readers handle v1 documents, and whether historical conversion has been validated. Do not treat a JSON `schemaVersion` field as concurrency control if the database lacks conditional updates/version checks.

### Graph Stores: Review Edge Direction and Constraints

An `Order → Shipment` relationship may be stored as a `HAS_SHIPMENT` edge. An edge alone does not guarantee total allocation limits or valid delivery states. When moving from single to multiple edges, update:

- edge semantics and direction;
- edge/node identity and deduplication during ingestion;
- queries for "all shipments of an Order" and "Orders with at least one shipment";
- counting/distinct logic after traversals;
- temporal properties and relationship versioning;
- cross-context node write/access permissions.

### Data Warehouses: Review the Semantic Model in the Same PR

A 1:N change can cause a `JOIN` from `fact_order` to `shipment` to fan out rows. If a dashboard still runs `SUM(order_total)` after the `JOIN`, order totals may be multiplied by the number of shipments. You must **aggregate at the proper grain before joining**, or maintain separate Shipment and Order facts as required. Tests should include **an Order with two Shipments**, since test fixtures with only one Shipment per Order will not catch this bug.

## 17. Documentation Governance, Security, and Lifecycle Policies

### 17.1. Never Put Real Sensitive Data into the Repository

Model documentation needs to describe data categories, not include real home addresses, card numbers, tokens, or customer records:

- Use synthetic IDs/addresses or non-identifiable mock data in examples.
- Tag sensitive fields in the data dictionary and specify who may read those tables/fields.
- Events and DTOs must expose only the minimum data needed by consumers and use cases.
- Production connection strings, secrets, and keys do not belong in Markdown model docs.
- If production screenshots or query plans must be attached, scrub identifying data and check repository access permissions.

A version-controlled repository retains commit history and clones; **deleting a secret in a newer commit does not remove it from history**. Test-data policies and secret scanning must be enforced before merge.

### 17.2. Update Policy When a PR Does Not Change the Schema

It is not only PRs containing migrations that require model updates:

- Changing an **enum's meaning** in Java may require updating the glossary/contract even if the DB schema is unchanged.
- Changing **how net revenue is calculated** may only touch the pipeline/semantic layer without adding tables.
- Changing **retention/TTL** on documents or time-series may leave the ERD unchanged.
- Changing **aggregate ownership** may require updating the context map and ACLs.
- Adding an **index** may only need a rationale/query workload note rather than editing the conceptual model.

A practical rule is: **every PR must check which model artifacts are impacted**, and when no edits are needed for significant changes, briefly state why. Do not mechanically enforce "edit every diagram in every PR."

### 17.3. Legacy Documentation: Supersede, Do Not Erase Decision Trails

An older target ERD may no longer reflect the present but remains necessary to understand historical migrations and incidents. You can:

- Mark it **Superseded/Archived**, pointing to its replacement and effective date.
- Keep old ADRs to preserve why choices made sense in that historical context.
- Maintain clear **current** documentation so newcomers do not confuse archived versions with live designs.
- Set retention rules for data dictionaries, schema snapshots, and doc copies per organizational policy.

If an accepted decision is revisited, do not edit the `Accepted` ADR to make it look as though it never existed; create a new decision and link it back to the prior one.

### 17.4. When Multiple Repositories Cannot Merge Simultaneously

Sales, Fulfillment, and Analytics may live in separate repositories. A single PR is impossible; use a shared **change initiative ID**:

~~~text
CHANGE-ID: DM-2026-042
ADR: ADR-0042
Sales PR:        add capability to read multi-shipment status
Fulfillment PR:  add Shipment and allocation ledger
Contracts PR:    ShipmentDeliveredV1, consumer compatibility
Analytics PR:    delivery metrics v3
Rollout plan:    expand -> readers -> writers -> feature -> cleanup
Evidence:        migration versions, tests, reconciliation report
~~~

Not merging simultaneously does not mean the PRs cannot be reviewed for shared semantics. What matters is specifying **dependencies, deployment order, old/new compatibility**, and who authorizes enabling the feature. When a producer deploys ahead of consumers, there must be a compatibility path, or new events must not be emitted to consumers that do not yet understand them.

## 18. Practice Exercise: From Single Instructor to Multiple Instructors

**Context:** An online learning platform has `Course`, `Instructor`, `Enrollment`, and `Payment`. Initially each `Course` has one `instructorId`. Starting next term, a `Course` can have **multiple instructors**, each responsible within a date range and some teaching only part of the content. Academic operations want to view currently assigned instructors; Analytics wants to compare enrollments and revenue by instructor across past terms.

### Tasks

1. **Conceptual model:** state the new Course–Instructor relationship, the business owner, and ambiguous questions to clarify before drawing 1:N or N:M.
2. **Logical model and grain:** propose a `CourseInstructorAssignment` table/collection. What does one row represent? Are effective dates and roles needed?
3. **Physical model:** choose PK/UNIQUE/FK and `CHECK` constraints for date ranges. Should overlapping date ranges for the same Instructor/Course be forbidden? If not, why?
4. **Migration:** describe how to handle legacy `course.instructorId` when some Courses lack an instructor, an Instructor has left, or legacy data only reflects the **current assignee**.
5. **API/events:** what should the `CourseDetail` response and `CourseInstructorAssigned` event contain? How can a v1 consumer expecting a single `instructorId` continue reading?
6. **Reporting:** a Course has two Instructors; joining `Enrollment` with assignments and summing tuition can cause what bug? Propose a safe allocation method or metric definition.
7. **PR:** list which artifacts must change and which reviewers must approve. Propose two automated gates and two mandatory human review questions.
8. **Rollout:** split the work into small PRs following expand–migrate–switch–contract; how do you know when the schema is deployed while old binaries are still running?

### Reference Solution Guide

**Model:** Course and Instructor can be a **time-bounded N:M** relationship if each instructor teaches multiple Courses and one Course has multiple instructors. The business owner must clarify whether "responsible" means course owner, live lecturer, or revenue-sharing participant, and whether a Course can temporarily have zero instructors.

**Grain:** one `CourseInstructorAssignment` represents **a single assignment of an Instructor to a Course with a specific role and effective period**. The key can use a dedicated `assignmentId` to allow the same Course–Instructor pair across multiple terms; an unconditional `UNIQUE(courseId, instructorId)` would block valid historical re-assignments.

A candidate design:

~~~sql
CREATE TABLE learning.course_instructor_assignment (
    tenant_id UUID NOT NULL,
    assignment_id UUID NOT NULL,
    course_id UUID NOT NULL,
    instructor_id UUID NOT NULL,
    role_code VARCHAR(24) NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, assignment_id),
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);
~~~

This illustrative DDL **assumes the `learning` schema already exists**; FKs to Course/Instructor are omitted because in real systems you must check whether those tables live in the same database/context. A non-negative range `CHECK` does not prevent **overlapping assignments**. Whether overlaps must be blocked is a business question: two instructors might co-teach, or the same person might hold two roles; do not impose `EXCLUDE`/`UNIQUE` before confirming the rule.

**Migration:** from legacy `instructorId`, you can only backfill a **currently active** assignment if current data is trustworthy and has a valid start timestamp. Do not claim the legacy `instructorId` taught the Course in all past terms; historical attribution requires a separate audit/assignment source. If history is missing, explicitly document the limitation.

**Exchange:** `CourseDetail` can expose `instructors[]` in API v2; v1 consumers need an adapter or a clearly defined `principalInstructor` field rather than arbitrarily picking the first array element. `CourseInstructorAssigned` carries `assignmentId`, `courseId`, `instructorId`, `role`, effective time, `eventId`, `schemaVersion`, and tenant scope; omit unnecessary personal data.

**Analytics:** joining an `Enrollment` worth 1,000,000 VND with two Instructors produces **two rows**, inflating `SUM` to 2,000,000 unless governed by a rule. Define metrics such as **enrolled learners participating in a course with an instructor** (which can be counted per instructor group without summing across groups to get a unique total), or **allocated revenue** using weights summing to 100% with clear attribution source and history.

**PR and rollout:** update glossary, ERD, dictionary, migrations, Java behaviors/mappers, API/event contracts, tests, and metrics; reviewed by academic, developer/DB, consumer, and BI owners. Deploy via schema expansion, reader upgrades, evidence-based backfill, enabling multi-assignment writes, migrating consumers/reports, and finally removing legacy `instructorId`. Track migration versions and actual deployed app/consumer versions rather than inferring deployment from merge status.

## 19. Adoption Checklist and Conclusion

Before merging a data-model-related change, verify:

- **Context:** are the user story, bounded context scope, business owner, and authoritative source clear?
- **Semantics:** do entities, grain, IDs, statuses, cardinalities, timestamps, and currency units share the same definition across docs and code?
- **Artifacts:** which glossaries, ERDs, data dictionaries, ADRs, migrations, Java code, APIs/events, and metrics are affected?
- **History:** are the rationale for change and links to deployed versions preserved?
- **Diagrams:** are text sources easy to diff with cardinality/exceptions noted, and are generated images in sync with schemas?
- **SQL/schema:** do PK/FK/UNIQUE/CHECK constraints, indexes, and transactions enforce what is actually promised?
- **Compatibility:** can old writers/readers/consumers handle new data, fields, and statuses?
- **Migration:** can legacy data be migrated with evidence, handling NULL/unknown without fabricating history?
- **Review:** have business, database, integration, analytics, and security owners reviewed their respective areas?
- **Automation:** are docs linting, diagram rendering, migration tests, contract tests, and data quality checks sufficient for the scope?
- **Testing:** are edge cases covered for concurrent writes, retries, late data, duplicates, and tenant isolation errors?
- **Reporting:** do metrics preserve grain and recognition dates, with before/after numbers reconciled at the same cutoff?
- **Deployment:** is it clearly tracked that a merged PR's migration/consumer might not yet be deployed?
- **Recovery:** once new data exists, would rolling back old binaries strip new fields/meanings? Is there a roll-forward plan?
- **Drift:** are live schemas/contracts checked against designs, with a process for handling out-of-band changes outside Git?
- **Security:** are docs free of secrets/real PII, and are event/DTO payloads and repo permissions appropriate?

**Conclusion:** Managing data models in version control is not simply **putting ERDs into Git**. You must place **business semantics, logical designs, physical constraints, Java behaviors, exchange contracts, and reporting definitions** in the same traceability stream. Git and CI provide history, diffs, and automated verification evidence; PRs and business owners confirm those changes are **semantically sound**. When semantic diffs, ADRs, ordered migrations, contract tests, reconciliations, and drift detection work together, a model is not only documented accurately at design time, but can also be **safely reviewed, deployed, traced, and evolved** alongside the source code.
