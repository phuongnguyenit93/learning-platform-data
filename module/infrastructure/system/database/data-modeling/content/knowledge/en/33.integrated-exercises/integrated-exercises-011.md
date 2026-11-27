# Executing a Model Change with Data Migration and Reconciliation

## Objectives and How to Use This Lab

In the **Integrated Exercises** chapter of the **DATABASE_DATA_MODELING** module, we practice turning business requirements into a clear data model: entities, relationships, invariants, normalization, keys, indexes, and physical schemas. Next, we need to know how to evolve relational, document, graph, or analytical models without **losing the meaning of existing data**. This lesson turns that goal into a hands-on exercise spanning requirements, design, data transformation, error detection, reconciliation, testing, and handoff.

By the end of this lesson, you should be able to:

1. State the change objective and the **grain, identity, invariants, and owner** of the data before and after the change.
2. Design a **target schema** moving from a JSONB document containing order lines to normalized OrderHeader and OrderLine tables; choose PKs, FKs, CHECK constraints, indexes, transactions, and monetary policies.
3. Build a **test dataset** containing both clean and faulty records, detecting ineligible data using explainable rules—without silently altering monetary amounts just to make the migration finish.
4. Migrate data following the **expand → assess/quarantine → backfill → catch-up → verify → switch → contract** stages and verify idempotent re-runs.
5. Reconcile Order counts, line counts, monetary totals, statuses, versions, and **one-to-one by business key**, rather than only comparing `COUNT(*)`.
6. Handle concurrent writers, retries, new data arriving during backfill, API/event contract changes, and analytical reports.
7. Design rollback/roll-forward plans, operational monitoring, tenant security, and test scenarios that others can verify.

This is a **worked lab exercise**, not a script to apply verbatim to production. Illustrative SQL uses PostgreSQL, and Java examples use Java 17 syntax. Snippets with colon-prefixed parameters represent SQL used in prepared statements or migration runners with bound variables; they cannot simply be pasted into psql as-is. Execute only in a test environment with synthetic data, appropriate backups, and restricted permissions.

## 1. Change Requirement: From Order with Embedded JSON to Order and Separately Keyed Lines

The sales system currently uses a source table named **sales.order_legacy**. Each row represents one Order. The list of line items is stored in the **items_jsonb** column:

~~~json
{
  "tenantId": "T1",
  "orderId": "O100",
  "customerId": "C1",
  "status": "CONFIRMED",
  "currency": "VND",
  "totalVnd": 310000,
  "version": 2,
  "items": [
    {
      "lineNo": 1, "skuId": "A",
      "quantity": 2, "unitPriceVnd": 120000,
      "discountPerUnitVnd": 10000
    },
    {
      "lineNo": 2, "skuId": "B",
      "quantity": 1, "unitPriceVnd": 90000,
      "discountPerUnitVnd": 0
    }
  ]
}
~~~

This JSON object illustrates the fields living inside a single row: Order metadata resides in dedicated columns, while the `items` array actually resides in `items_jsonb`. Thus it is a **hybrid physical storage model**: one row per Order and one JSONB document for lines—not a claim that PostgreSQL stores the entire JSON object above in a single column.

**Drivers for the change:**

- Need to enforce unique `lineNo` within an Order and proper types for quantity/price, preventing invalid data at write time.
- Need to query by SKU, date, and tenant across millions of lines, reducing JSONB array unpacking across many transactional queries.
- Need to link return/adjustment workflows to a controlled **per-line identity**.
- Need to preserve Order history, unit-price snapshots, and total-amount semantics while the legacy application may still run during part of the rollout.

**Goal:** create **sales.order_header** and **sales.order_line**; each Order has one header and many lines. The key `(tenant_id, order_id, line_no)` identifies each line. Totals are split into gross, discount, and payable. Reconciliation is performed before switching read/write authority to the new schema.

What does **not** change: the business meaning of Order, confirmed statuses, public IDs, VND currency, Sales ownership, and existing contracts promised to consumers. Do not assume that splitting tables requires an API to return the `lines` array under a different name or that the `OrderConfirmed` event must immediately change its format.

## 2. Locking Down Semantics: Grain, Calculations, and Authoritative Source

| Concept | Before | After | Preserved Invariant |
| --- | --- | --- | --- |
| Order | One legacy row / one Order | One `order_header` row | One Order within a tenant |
| OrderLine | One element in `items_jsonb` | One `order_line` row | Unique `lineNo` within an Order |
| Customer | `customer_id` | `customer_id` | Reference by ID only; do not embed the Customer aggregate |
| Product | `skuId` in JSON element | `sku_id` on the line | Unit price is a point-in-time purchase snapshot |
| Total | `total_vnd` from source | `gross_total_vnd`, `discount_total_vnd`, `payable_total_vnd` | Post-discount payable keeps the same meaning |
| Status | `DRAFT`, `CONFIRMED`, `CANCELLED` | Same statuses | Only Sales commands may transition status |
| Version | `version` of the Order | `version` of the Order root | Not used as an event `schemaVersion` |

Within the scope of this lesson, money is **integer VND**, with no tax or shipping fee, no refunds yet, and each line has a **per-unit** discount. If \(q_i\) is quantity, \(p_i\) is unit price, and \(d_i\) is discount per unit:

\[
g_i=q_ip_i,\qquad r_i=q_id_i,\qquad n_i=g_i-r_i.
\]

\[
q_i>0,\quad p_i\ge0,\quad 0\le d_i\le p_i,\quad
\mathrm{gross}=\sum_i g_i,\quad
\mathrm{discount}=\sum_i r_i,\quad
\mathrm{payable}=\mathrm{gross}-\mathrm{discount}.
\]

**Mandatory rules:**

- A `CONFIRMED` Order must have at least one valid line and a `confirmedAt` timestamp.
- A `DRAFT` Order may temporarily be empty; do not allow editing prices or lines on a `CONFIRMED` Order through normal commands.
- The same `tenantId + orderId` cannot have two Orders; the same Order cannot have two lines with the same `lineNo`.
- `customerId`, `status`, `total`, `currency`, `version`, and all price snapshots must retain their exact meaning after migration.
- A faulty source record **must not be silently skipped while reporting 100% success**; there must be a classification record, root cause, and handling owner.
- Header totals must equal recomputation from lines within the same version/transaction, not merely match a single aggregate number on a report.

**Sales owns** status, price snapshots, lines, and confirmation. **Payment** owns captured payment truth, **Inventory** owns stock reservation, and **Analytics** owns derived fact/metric definitions. Changing storage tables does not grant other systems permission to modify Orders.

### Before and After Diagram

~~~mermaid
flowchart LR
    subgraph Source["Legacy: JSONB inside Order"]
      A["order_legacy<br/>PK tenant_id + order_id"]
      J["items_jsonb<br/>array {lineNo, sku, qty, price, discount}"]
      A --> J
    end
    subgraph Target["Target: normalized relational"]
      H["order_header<br/>PK tenant_id + order_id"]
      L["order_line<br/>PK tenant_id + order_id + line_no"]
      H -->|"FK, 1 : N"| L
    end
    A -. "reconciled migration" .-> H
    J -. "each valid element" .-> L
~~~

The target diagram is **1:N logically**, but a `DRAFT` Order may have 0 lines. Therefore the enforced cardinality is **Order 0..N OrderLine**, and every OrderLine belongs to **exactly one** Order.

## 3. Sample Dataset and Pre-Computed Financial Answer Key

To establish an objective ground truth, use six Orders in tenant `T1`, comprising **three valid Orders** and three Orders requiring investigation:

| Order | Status | Summary of Contents | Source `total_vnd` | Assessment Verdict |
| --- | --- | --- | ---: | --- |
| O100 | CONFIRMED | A: 2×120,000 less 10,000/unit; B: 1×90,000 no discount | 310,000 | OK |
| O101 | DRAFT | A: 1×120,000 no discount | 120,000 | OK |
| O102 | CONFIRMED | B: 3×90,000 less 5,000/unit | 255,000 | OK |
| O103 | CONFIRMED | A: 1×100,000; B: 2×50,000, both without discount | **200,001** | AMOUNT_MISMATCH: lines = 200,000 |
| O104 | DRAFT | Two lines both with `lineNo=1`, priced 10,000 and 15,000 | 25,000 | DUPLICATE_LINE_NO |
| O105 | CONFIRMED | No lines, total=0 | 0 | EMPTY_CONFIRMED |

**Pre-migration answer key:**

- O100: gross 330,000, discount 20,000, payable **310,000**.
- O101: gross 120,000, discount 0, payable **120,000**.
- O102: gross 270,000, discount 15,000, payable **255,000**.
- **Three accepted Orders:** 3 headers, 4 lines, total gross **720,000**, discount **35,000**, payable **685,000**; the two `CONFIRMED` Orders alone have payable **565,000**.
- **Three quarantined Orders:** O103, O104, O105; must not be blended into the "successfully migrated" count.

Note that the total gross of the three valid Orders = 330,000 + 120,000 + 270,000 = **720,000**, and payable = 310,000 + 120,000 + 255,000 = **685,000**. The goal of reconciliation is to preserve totals both **for the record cohort** and per individual Order/line; checking only an aggregate total can mask one Order being over by 1 VND and another being under by 1 VND.

Do not overwrite O103's total from 200,001 to 200,000 based on calculation during migration. A 1 VND discrepancy may indicate missing historical pricing, rounding, or a legacy bug; the authoritative source must be verified before deciding on a fix.

## 4. Setting Up the Source Schema in PostgreSQL

~~~sql
CREATE SCHEMA IF NOT EXISTS sales;

CREATE TABLE sales.order_legacy (
    tenant_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    status VARCHAR(16) NOT NULL
        CHECK (status IN ('DRAFT', 'CONFIRMED', 'CANCELLED')),
    currency_code CHAR(3) NOT NULL DEFAULT 'VND'
        CHECK (currency_code = 'VND'),
    total_vnd BIGINT NOT NULL CHECK (total_vnd >= 0),
    version BIGINT NOT NULL DEFAULT 0 CHECK (version >= 0),
    items_jsonb JSONB NOT NULL
        CHECK (jsonb_typeof(items_jsonb) = 'array'),
    created_at TIMESTAMPTZ NOT NULL,
    confirmed_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, order_id),
    CHECK (status <> 'CONFIRMED' OR confirmed_at IS NOT NULL)
);
~~~

The JSONB column is validated only at the **array level**, not yet protecting per-line `lineNo`, quantity, price, or total amount. Thus this is a realistic example of legacy storage with **weaker business invariants** than what the business wants to guarantee. The migration adds detection and constraints; one must not infer from the presence of JSONB that PostgreSQL cannot validate deeper structure.

### Sample Data: Three Clean Rows

~~~sql
INSERT INTO sales.order_legacy (
    tenant_id, order_id, customer_id, status, total_vnd,
    version, items_jsonb, created_at, confirmed_at
) VALUES
(
    'T1','O100','C1','CONFIRMED',310000,2,
    '[{"lineNo":1,"skuId":"A","quantity":2,
       "unitPriceVnd":120000,"discountPerUnitVnd":10000},
      {"lineNo":2,"skuId":"B","quantity":1,
       "unitPriceVnd":90000,"discountPerUnitVnd":0}]'::jsonb,
    TIMESTAMPTZ '2026-11-20 08:00:00+00',
    TIMESTAMPTZ '2026-11-20 09:00:00+00'
),
(
    'T1','O101','C1','DRAFT',120000,1,
    '[{"lineNo":1,"skuId":"A","quantity":1,
       "unitPriceVnd":120000,"discountPerUnitVnd":0}]'::jsonb,
    TIMESTAMPTZ '2026-11-21 08:00:00+00',NULL
),
(
    'T1','O102','C2','CONFIRMED',255000,3,
    '[{"lineNo":1,"skuId":"B","quantity":3,
       "unitPriceVnd":90000,"discountPerUnitVnd":5000}]'::jsonb,
    TIMESTAMPTZ '2026-11-21 10:00:00+00',
    TIMESTAMPTZ '2026-11-21 11:00:00+00'
);
~~~

### Sample Data: Three Problematic Rows Requiring Quarantine

~~~sql
INSERT INTO sales.order_legacy (
    tenant_id, order_id, customer_id, status, total_vnd,
    version, items_jsonb, created_at, confirmed_at
) VALUES
(
    'T1','O103','C3','CONFIRMED',200001,2,
    '[{"lineNo":1,"skuId":"A","quantity":1,
       "unitPriceVnd":100000,"discountPerUnitVnd":0},
      {"lineNo":2,"skuId":"B","quantity":2,
       "unitPriceVnd":50000,"discountPerUnitVnd":0}]'::jsonb,
    TIMESTAMPTZ '2026-11-21 12:00:00+00',
    TIMESTAMPTZ '2026-11-21 13:00:00+00'
),
(
    'T1','O104','C4','DRAFT',25000,1,
    '[{"lineNo":1,"skuId":"A","quantity":1,
       "unitPriceVnd":10000,"discountPerUnitVnd":0},
      {"lineNo":1,"skuId":"B","quantity":1,
       "unitPriceVnd":15000,"discountPerUnitVnd":0}]'::jsonb,
    TIMESTAMPTZ '2026-11-21 14:00:00+00',NULL
),
(
    'T1','O105','C5','CONFIRMED',0,2,
    '[]'::jsonb,
    TIMESTAMPTZ '2026-11-21 15:00:00+00',
    TIMESTAMPTZ '2026-11-21 15:30:00+00'
);
~~~

**Important:** these faulty rows are **intentionally** created for verification practice; they must never be inserted into production. The `INSERT` statements are one-time setup, not idempotent if re-run on the same table. Timestamps are UTC and purely synthetic; when loading real data, preserve exact instants or the published timezone policy.

## 5. Designing the Target Schema: Relations and Physical Constraints

~~~sql
CREATE TABLE sales.order_header (
    tenant_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    status VARCHAR(16) NOT NULL
        CHECK (status IN ('DRAFT', 'CONFIRMED', 'CANCELLED')),
    currency_code CHAR(3) NOT NULL CHECK (currency_code = 'VND'),
    gross_total_vnd BIGINT NOT NULL CHECK (gross_total_vnd >= 0),
    discount_total_vnd BIGINT NOT NULL CHECK (discount_total_vnd >= 0),
    payable_total_vnd BIGINT NOT NULL CHECK (payable_total_vnd >= 0),
    version BIGINT NOT NULL CHECK (version >= 0),
    migrated_from_version BIGINT NOT NULL CHECK (migrated_from_version >= 0),
    created_at TIMESTAMPTZ NOT NULL,
    confirmed_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, order_id),
    CHECK (discount_total_vnd <= gross_total_vnd),
    CHECK (gross_total_vnd - discount_total_vnd = payable_total_vnd),
    CHECK (status <> 'CONFIRMED' OR confirmed_at IS NOT NULL)
);

CREATE TABLE sales.order_line (
    tenant_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    sku_id TEXT NOT NULL CHECK (length(trim(sku_id)) > 0),
    quantity BIGINT NOT NULL CHECK (quantity > 0),
    unit_price_vnd BIGINT NOT NULL CHECK (unit_price_vnd >= 0),
    discount_per_unit_vnd BIGINT NOT NULL
        CHECK (discount_per_unit_vnd >= 0),
    PRIMARY KEY (tenant_id, order_id, line_no),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES sales.order_header (tenant_id, order_id),
    CHECK (discount_per_unit_vnd <= unit_price_vnd)
);

CREATE INDEX order_header_by_customer
    ON sales.order_header
        (tenant_id, customer_id, created_at DESC, order_id DESC);

CREATE INDEX order_line_by_sku
    ON sales.order_line (tenant_id, sku_id, order_id);
~~~

On the target side, **OrderHeader** has a grain of one Order, and **OrderLine** has a grain of one line of an Order. Including `tenant_id` in the composite PK and FK prevents a line in `T2` from mistakenly referencing a header in `T1`. The FK enforces header existence within the same database. The first index serves recent orders by customer, and the second supports queries by SKU, though actual query plans must be measured. Indexes carry write overhead, so not every added field warrants an index.

**Invariants not fully solved by CHECK constraints:**

- A `CONFIRMED` Order must have at least one line. A `CHECK` on a single header row cannot automatically inspect child rows.
- Header totals must equal **SUM(line.quantity × line.price)** and the sum of discounts across all lines.
- Lines of a `CONFIRMED` Order must not be modified.
- Every Order update request must enforce **tenant authorization, version checks, or locks**, including batch/import/admin paths.

These require domain behavior, consistent transaction/locking protocols, and data verification. If full DB-level enforcement is desired, triggers/procedures or stricter database privileges can be considered, but transaction semantics and performance must be reviewed rather than assuming simple `CHECK` constraints suffice.

### Why Keep `version` and `migrated_from_version` Separate?

**version** is the current version of the aggregate used to detect concurrent writes. **migrated_from_version** is lineage: the source version captured during initial backfill. After cutover, the Order's `version` can advance; the migration must never keep unconditionally syncing from an older legacy version and overwriting newer state.

**The goal is not two simultaneously writable databases.** During dual-read or catch-up phases, **one authoritative source** must be designated. `version` helps protect against races, but it cannot replace deciding who holds write authority in each phase.

## 6. Preflight: Catching Structural Errors Before Casting JSON to SQL Types

The fact that JSON is an array does not guarantee every element is an object with all required fields. A document where `quantity` is a string, price is negative, or `lineNo` overflows `INTEGER` can cause a bulk `CAST` statement to abort midway. Therefore, data assessment should proceed in **two passes**:

1. **Check JSON shape and data types**, ensuring monetary values are integers within supported bounds and identity keys are present.
2. **Once safe to parse**, check cross-line logic, status rules, monetary totals, and duplicate identities.

Example query to detect missing or mistyped fields before parsing:

~~~sql
SELECT o.tenant_id, o.order_id,
       e.ordinality AS item_position,
       e.value AS suspicious_item
FROM sales.order_legacy AS o
CROSS JOIN LATERAL
    jsonb_array_elements(o.items_jsonb)
    WITH ORDINALITY AS e(value, ordinality)
WHERE jsonb_typeof(e.value) IS DISTINCT FROM 'object'
   OR jsonb_typeof(e.value -> 'lineNo')
        IS DISTINCT FROM 'number'
   OR jsonb_typeof(e.value -> 'skuId')
        IS DISTINCT FROM 'string'
   OR jsonb_typeof(e.value -> 'quantity')
        IS DISTINCT FROM 'number'
   OR jsonb_typeof(e.value -> 'unitPriceVnd')
        IS DISTINCT FROM 'number'
   OR jsonb_typeof(e.value -> 'discountPerUnitVnd')
        IS DISTINCT FROM 'number';
~~~

On the six sample Orders, this query **returns no rows** because the planted defects are **logic** errors rather than JSON type mismatches. This is only a **preliminary type check**; production must also check integrality, `INTEGER`/`BIGINT` ranges, blank SKUs, negative quantities, array length limits, out-of-range money values, and source `schemaVersion`. For example, a JSON price of `1.5` has type `number` but is not integer VND; it must not be cast and implicitly rounded.

**Do not run the parsing pass while mistyped items remain**, because a `CAST` failure inside an assessment query can abort the entire batch. In a real pipeline, records failing pass 1 must be quarantined with reasons; only safe records proceed to pass 2. The SQL that follows **assumes parse readiness holds**, as is true for the six sample records.

## 7. Business Assessment and Classifying Records for Migration

This lab creates a **session-scoped temporary table** to snapshot classification results. In a live system accepting writes, simply running an arbitrary query while the source changes **does not produce a consistent snapshot for the whole migration**; production rollout covered later requires snapshot/cutoff alignment and CDC.

~~~sql
-- Run in a fresh test session after passing the type check.
CREATE TEMP TABLE migration_assessment AS
WITH line_stats AS (
    SELECT o.tenant_id, o.order_id,
           COUNT(*) AS line_count,
           COUNT(DISTINCT i."lineNo") AS distinct_line_count,
           BOOL_AND(
               COALESCE(
                   i."lineNo" > 0
                   AND length(trim(i."skuId")) > 0
                   AND i."quantity" > 0
                   AND i."unitPriceVnd" >= 0
                   AND i."discountPerUnitVnd" >= 0
                   AND i."discountPerUnitVnd" <= i."unitPriceVnd"
                   AND trunc(i."unitPriceVnd") = i."unitPriceVnd"
                   AND trunc(i."discountPerUnitVnd")
                       = i."discountPerUnitVnd",
                   FALSE
               )
           ) AS valid_lines,
           SUM(i."quantity"::NUMERIC * i."unitPriceVnd")
               AS gross_numeric,
           SUM(i."quantity"::NUMERIC * i."discountPerUnitVnd")
               AS discount_numeric
    FROM sales.order_legacy AS o
    CROSS JOIN LATERAL jsonb_to_recordset(o.items_jsonb) AS i(
        "lineNo" INTEGER,
        "skuId" TEXT,
        "quantity" BIGINT,
        "unitPriceVnd" NUMERIC,
        "discountPerUnitVnd" NUMERIC
    )
    GROUP BY o.tenant_id, o.order_id
),
assessed AS (
    SELECT o.*,
           COALESCE(s.line_count, 0)::BIGINT AS line_count,
           COALESCE(s.distinct_line_count, 0)::BIGINT
               AS distinct_line_count,
           COALESCE(s.valid_lines, FALSE) AS valid_lines,
           COALESCE(s.gross_numeric, 0)::NUMERIC AS gross_numeric,
           COALESCE(s.discount_numeric, 0)::NUMERIC
               AS discount_numeric
    FROM sales.order_legacy AS o
    LEFT JOIN line_stats AS s
      ON s.tenant_id = o.tenant_id
     AND s.order_id = o.order_id
)
SELECT a.*,
       a.gross_numeric - a.discount_numeric AS payable_numeric,
       CASE
           WHEN a.status = 'CONFIRMED' AND a.line_count = 0
               THEN 'EMPTY_CONFIRMED'
           WHEN a.line_count > 0 AND NOT a.valid_lines
               THEN 'INVALID_LINE'
           WHEN a.line_count <> a.distinct_line_count
               THEN 'DUPLICATE_LINE_NO'
           WHEN a.gross_numeric > 9223372036854775807::NUMERIC
             OR a.discount_numeric > 9223372036854775807::NUMERIC
             OR a.gross_numeric - a.discount_numeric
                   > 9223372036854775807::NUMERIC
               THEN 'AMOUNT_OVERFLOW'
           WHEN a.gross_numeric - a.discount_numeric
                    IS DISTINCT FROM a.total_vnd
               THEN 'AMOUNT_MISMATCH'
           ELSE 'OK'
       END AS verdict
FROM assessed AS a;

SELECT order_id, status, line_count, distinct_line_count,
       gross_numeric, discount_numeric, payable_numeric,
       total_vnd, verdict
FROM migration_assessment
ORDER BY order_id;
~~~

**How this works:**

- `LEFT JOIN` preserves **empty Orders** in the output. Using an `INNER JOIN` against JSON elements would make O105 vanish, causing the migration to underreport missing/invalid records.
- `COUNT(DISTINCT lineNo)` catches O104 having 2 lines but only 1 distinct `lineNo`.
- Using `NUMERIC` during summation detects values exceeding `BIGINT` before writing to the target. Target columns are `BIGINT`; overflow cases must be quarantined rather than letting a `CAST` fail mid-batch.
- For an empty `DRAFT` with `totalVnd=0`, the current rule permits it; an empty `DRAFT` with non-zero `totalVnd` gets `AMOUNT_MISMATCH`.
- `BOOL_AND` over at least one line validates per-line predicates; `COALESCE(..., FALSE)` ensures nulls never turn into valid records.

**Expected output:**

| Order | `line_count` | `distinct_line_count` | Recomputed `payable` | `verdict` |
| --- | ---: | ---: | ---: | --- |
| O100 | 2 | 2 | 310,000 | OK |
| O101 | 1 | 1 | 120,000 | OK |
| O102 | 1 | 1 | 255,000 | OK |
| O103 | 2 | 2 | 200,000 | AMOUNT_MISMATCH |
| O104 | 2 | 1 | 25,000 | DUPLICATE_LINE_NO |
| O105 | 0 | 0 | 0 | EMPTY_CONFIRMED |

If your result differs, do not proceed with backfill. First check the fixture, calculation logic, and business rules. **Check conditions** must live in test code/version control rather than being inspected by eye once and discarded.

### Scope of the Assessment Example

The temporary table above is **not a general-purpose JSON sanitizer**: `jsonb_to_recordset` requires parseable data with `lineNo` within `INTEGER` range and `quantity` within `BIGINT` range. Therefore, type and range preflight must run beforehand, or a production pipeline needs per-record parsing with error capture and isolated quarantine. An Order with multiple defects may receive **one priority verdict** based on `CASE` ordering; real investigations should also store the complete list of reasons.

## 8. Quarantine: Preserving Faulty Records with Identity and Reason

Avoid the two extremes of **arbitrarily patching data to pass CHECK constraints** or **silently dropping rows so nobody knows**. The system needs an exception inventory with counts, impact severity, decision owners, and resolution state.

~~~sql
CREATE TABLE sales.order_migration_reject (
    tenant_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    evaluated_source_version BIGINT NOT NULL,
    reason_code TEXT NOT NULL,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_total_vnd BIGINT,
    computed_payable_numeric NUMERIC,
    source_line_count BIGINT NOT NULL,
    PRIMARY KEY (tenant_id, order_id, evaluated_source_version)
);

INSERT INTO sales.order_migration_reject (
    tenant_id, order_id, evaluated_source_version,
    reason_code, source_total_vnd, computed_payable_numeric,
    source_line_count
)
SELECT tenant_id, order_id, version, verdict,
       total_vnd, payable_numeric, line_count
FROM migration_assessment
WHERE verdict <> 'OK'
ON CONFLICT (tenant_id, order_id, evaluated_source_version)
DO UPDATE
SET reason_code = EXCLUDED.reason_code,
    source_total_vnd = EXCLUDED.source_total_vnd,
    computed_payable_numeric = EXCLUDED.computed_payable_numeric,
    source_line_count = EXCLUDED.source_line_count;

SELECT order_id, reason_code
FROM sales.order_migration_reject
WHERE tenant_id = 'T1'
ORDER BY order_id;
~~~

On the fixture, the reject table holds three rows: O103, O104, and O105. The key `(tenant, order, sourceVersion)` ensures re-running the same assessment does not duplicate an exception. **Do not mutate source data** inside this `INSERT` statement.

In real production, a source record may be re-evaluated multiple times **at the same version** under updated rules; if lossless classification history is required, add an **assessmentRunId or immutable audit log**. This example table retains only the latest state for a given source version because the goal here is practicing a single batch.

### Remediation Workflow for the Three Defects

| Order | Action **Not** Permitted | Questions to Investigate |
| --- | --- | --- |
| O103 — 1 VND discrepancy | Changing source total to 200,000 or bumping one line's unit price by 1 on your own | Was there legacy rounding/tax/promotion? What was the actual legacy total contract? |
| O104 — duplicate `lineNo` | Renumbering the second `lineNo` to 2 without evidence | Is `lineNo` a real business ID or just array position? Do any returns reference the old `lineNo`? |
| O105 — empty `CONFIRMED` | Inserting a dummy 0-price line to pass CHECK, or deleting the Order from history | Is this a special service order, an order whose lines were erroneously deleted, or corrupted data? |

**Business stakeholders** and the Sales owner must confirm the resolution. Data may be reconstructed from audit logs, events, invoices, Payment reconciliations, or customer records; every correction requires evidence, an approver, and an effective timestamp. If sufficient evidence is missing, keep the record quarantined and report **incomplete coverage**—never treat all 6/6 as migrated.

Quarantine storage must carry the same access controls and retention policies as the source. Do not dump PII or full customer JSON payloads into broad-access debug logs; store error codes, hashes/IDs, and controlled pointers back to the source record.

## 9. Backfill: Migrating OK Records Within a Single Transaction

Lab assumption: all writes to the source are **paused** while capturing the assessment and running backfill, so the temp table corresponds to a sufficiently consistent snapshot. Later rollout sections address scenarios where writes cannot be stopped.

Goal: copy exactly the **three OK Orders** along with their lines, totals, status, version, and timestamps, leaving the three faulty Orders untouched. To illustrate **non-duplicating re-runs**, use target keys with `ON CONFLICT DO NOTHING`, followed by **mandatory reconciliation**, because ignoring conflicts does not prove existing rows match the source.

~~~sql
BEGIN;

-- 1. Header: take monetary amounts calculated during assessment,
-- matching source totals when verdict=OK.
INSERT INTO sales.order_header (
    tenant_id, order_id, customer_id, status, currency_code,
    gross_total_vnd, discount_total_vnd, payable_total_vnd,
    version, migrated_from_version, created_at, confirmed_at
)
SELECT tenant_id, order_id, customer_id, status, currency_code,
       gross_numeric::BIGINT, discount_numeric::BIGINT,
       payable_numeric::BIGINT,
       version, version, created_at, confirmed_at
FROM migration_assessment
WHERE verdict = 'OK'
ON CONFLICT (tenant_id, order_id) DO NOTHING;

-- 2. Individual lines: only from the snapshot assessed as OK.
INSERT INTO sales.order_line (
    tenant_id, order_id, line_no, sku_id,
    quantity, unit_price_vnd, discount_per_unit_vnd
)
SELECT a.tenant_id, a.order_id,
       i."lineNo", i."skuId",
       i."quantity", i."unitPriceVnd"::BIGINT,
       i."discountPerUnitVnd"::BIGINT
FROM migration_assessment AS a
JOIN sales.order_header AS h
  ON h.tenant_id = a.tenant_id
 AND h.order_id = a.order_id
 AND h.version = a.version
 AND h.migrated_from_version = a.version
CROSS JOIN LATERAL jsonb_to_recordset(a.items_jsonb) AS i(
    "lineNo" INTEGER,
    "skuId" TEXT,
    "quantity" BIGINT,
    "unitPriceVnd" NUMERIC,
    "discountPerUnitVnd" NUMERIC
)
WHERE a.verdict = 'OK'
ON CONFLICT (tenant_id, order_id, line_no) DO NOTHING;

COMMIT;
~~~

Putting both inserts in the same transaction prevents a state where **the header enters the target without its lines** due to a mid-batch failure. For a small dataset, one transaction suffices; with millions of orders, batch by **Order root**, ensuring each Order and all its lines commit within **a single transaction**, checkpointing by business key and reconciling per batch.

### Why `ON CONFLICT DO NOTHING` Is Not Enough

If a target line with the same `(tenant, order, lineNo)` already exists but carries a wrong price, the `INSERT` statement may **raise no error**. "Script finished cleanly" does not imply the target data is correct. Therefore:

- After each batch, reconcile **Order counts, line counts, per-line details, monetary totals, and versions**.
- Any conflict whose payload differs must be flagged as **data drift**, blocking cutover and triggering investigation.
- Never use unconditional `ON CONFLICT DO UPDATE` from legacy once the target begins accepting new commands. If an old `sourceVersion` overwrites a newer `targetVersion`, that is a **migration-induced lost update**.

In zero-downtime deployments, assessment snapshots and target writes must combine with **versioned or high-watermark CDC/replay**. The SQL above solves **point-in-time state backfill** only, not continuous source synchronization.

## 10. Layer 1 Reconciliation: Coverage, Row Counts, and Monetary Totals

**Never check only `source count = target count`**, because the source contains three quarantined records. First define the **eligible source cohort** and the **exception cohort**:

~~~sql
-- Every Order belongs to exactly one assessment verdict in the snapshot.
SELECT verdict,
       COUNT(*) AS order_count,
       SUM(line_count) AS source_line_count,
       SUM(payable_numeric) AS source_payable_numeric
FROM migration_assessment
GROUP BY verdict
ORDER BY verdict;

-- Coverage at Order and target line levels, for lab tenant T1.
SELECT
  (SELECT COUNT(*) FROM migration_assessment
   WHERE verdict = 'OK') AS expected_orders,
  (SELECT COUNT(*) FROM sales.order_header
   WHERE tenant_id = 'T1') AS actual_orders,
  (SELECT COALESCE(SUM(line_count),0)
   FROM migration_assessment
   WHERE verdict = 'OK') AS expected_lines,
  (SELECT COUNT(*) FROM sales.order_line
   WHERE tenant_id = 'T1') AS actual_lines;

-- Migrated monetary totals (excluding quarantined Orders).
SELECT COUNT(*) AS target_orders,
       SUM(gross_total_vnd) AS gross_vnd,
       SUM(discount_total_vnd) AS discount_vnd,
       SUM(payable_total_vnd) AS payable_vnd,
       SUM(payable_total_vnd)
           FILTER (WHERE status = 'CONFIRMED')
           AS confirmed_payable_vnd
FROM sales.order_header
WHERE tenant_id = 'T1';
~~~

Expected results for a clean test environment with no other data:

| Metric | Expected Result |
| --- | ---: |
| Source Orders | 6 |
| Source OK | 3 |
| Source Quarantined | 3 |
| Target Orders | **3** |
| Target OrderLines | **4** |
| Target gross | **720,000 VND** |
| Target discount | **35,000 VND** |
| Target payable | **685,000 VND** |
| Target CONFIRMED payable | **565,000 VND** |

Note that the `GROUP BY verdict` query may display a total payable for the faulty group, but **that number must not be treated as valid target money**. O103 is off by 1 VND; that is precisely why source amounts and recomputed amounts must be kept **in separate columns**, never blended into a single metric just to make a dashboard appear to tie out.

### Coverage Rate

In this fixture, **Order coverage** is \(3/6=50\%\). This low figure is deliberate due to the three planted faulty records used for training, **not** an acceptable threshold for commercial production. In practice, cutover gates require clear policies for quarantined data—often requiring **100% for active Orders**, even when archived history has separate exception handling.

**Matching aggregate totals do not prove individual Orders match**: opposite-sign errors can cancel out. Hence reconciliation must continue across two deeper layers.

## 11. Layer 2 and Layer 3 Reconciliation: Per Order, Per Line

### 11.1. Comparing Headers Against the Source Snapshot

~~~sql
SELECT a.order_id,
       a.status AS source_status,
       h.status AS target_status,
       a.total_vnd AS source_payable,
       h.payable_total_vnd AS target_payable,
       a.version AS source_version,
       h.version AS target_version
FROM migration_assessment AS a
LEFT JOIN sales.order_header AS h
  ON h.tenant_id = a.tenant_id AND h.order_id = a.order_id
WHERE a.verdict = 'OK'
  AND (
       h.order_id IS NULL
       OR h.customer_id IS DISTINCT FROM a.customer_id
       OR h.status IS DISTINCT FROM a.status
       OR h.currency_code IS DISTINCT FROM a.currency_code
       OR h.gross_total_vnd IS DISTINCT FROM a.gross_numeric
       OR h.discount_total_vnd IS DISTINCT FROM a.discount_numeric
       OR h.payable_total_vnd IS DISTINCT FROM a.total_vnd
       OR h.version IS DISTINCT FROM a.version
       OR h.created_at IS DISTINCT FROM a.created_at
       OR h.confirmed_at IS DISTINCT FROM a.confirmed_at
  );
~~~

This query must **return zero rows** when the target matches the snapshot. Using `LEFT JOIN` and `IS DISTINCT FROM` ensures it still catches missing target Orders or unexpected `NULL` discrepancies. You must also check for **target rows outside the expected set** (if not legitimately written after the snapshot); checking only from expected to target would miss extra rows.

### 11.2. Comparing Lines by Business Key

~~~sql
WITH expected_lines AS (
    SELECT a.tenant_id, a.order_id,
           i."lineNo" AS line_no,
           i."skuId" AS sku_id,
           i."quantity" AS quantity,
           i."unitPriceVnd"::BIGINT AS unit_price_vnd,
           i."discountPerUnitVnd"::BIGINT AS discount_per_unit_vnd
    FROM migration_assessment AS a
    CROSS JOIN LATERAL jsonb_to_recordset(a.items_jsonb) AS i(
        "lineNo" INTEGER, "skuId" TEXT, "quantity" BIGINT,
        "unitPriceVnd" NUMERIC, "discountPerUnitVnd" NUMERIC
    )
    WHERE a.verdict = 'OK'
),
target_lines AS (
    SELECT *
    FROM sales.order_line
    WHERE tenant_id = 'T1'
)
SELECT COALESCE(e.tenant_id, t.tenant_id) AS tenant_id,
       COALESCE(e.order_id, t.order_id) AS order_id,
       COALESCE(e.line_no, t.line_no) AS line_no,
       e.sku_id AS source_sku, t.sku_id AS target_sku,
       e.quantity AS source_qty, t.quantity AS target_qty
FROM expected_lines AS e
FULL OUTER JOIN target_lines AS t
  ON t.tenant_id = e.tenant_id
 AND t.order_id = e.order_id
 AND t.line_no = e.line_no
WHERE e.line_no IS NULL
   OR t.line_no IS NULL
   OR e.sku_id IS DISTINCT FROM t.sku_id
   OR e.quantity IS DISTINCT FROM t.quantity
   OR e.unit_price_vnd IS DISTINCT FROM t.unit_price_vnd
   OR e.discount_per_unit_vnd
        IS DISTINCT FROM t.discount_per_unit_vnd
ORDER BY 1,2,3;
~~~

This must **return zero rows** within the lab snapshot scope. `FULL OUTER JOIN` catches both **missing lines** and **extra lines**. In production, if the target already holds newer Orders created after the snapshot or spans multiple tenants, restrict both sides to the **same cohort and cutoff** so valid new records are not mislabeled as extraneous.

### 11.3. Recomputing Totals Directly from Target Tables

~~~sql
WITH line_totals AS (
    SELECT tenant_id, order_id,
           COUNT(*) AS lines,
           SUM(quantity::NUMERIC * unit_price_vnd) AS gross,
           SUM(quantity::NUMERIC * discount_per_unit_vnd)
               AS discount
    FROM sales.order_line
    WHERE tenant_id = 'T1'
    GROUP BY tenant_id, order_id
)
SELECT h.order_id, h.status, h.payable_total_vnd,
       t.lines, t.gross, t.discount,
       t.gross - t.discount AS computed_payable
FROM sales.order_header AS h
LEFT JOIN line_totals AS t
  ON t.tenant_id = h.tenant_id AND t.order_id = h.order_id
WHERE h.tenant_id = 'T1'
  AND (
      (h.status = 'CONFIRMED' AND t.lines IS NULL)
      OR h.gross_total_vnd IS DISTINCT FROM COALESCE(t.gross,0)
      OR h.discount_total_vnd
           IS DISTINCT FROM COALESCE(t.discount,0)
      OR h.payable_total_vnd
           IS DISTINCT FROM COALESCE(t.gross - t.discount,0)
  );
~~~

This query must also return zero rows. It proves the **target is internally self-consistent** at observation time, yet **does not prove the target preserves source semantics**: a buggy migration altering both header and lines together would still pass this check. Therefore, all three layers work together:

1. **Coverage and totals** over the eligible migration cohort.
2. **Per-Order and per-line comparison** against the authoritative snapshot.
3. **Target internal invariants** and physical constraints.

For critical data, store reconciliation evidence (`runId`, `batchKey`, `sourceVersion`/`cutoff`, discrepancy counts, quarantine counts, well-defined checksums, sign-offs) in a migration governance store—never dump such evidence into wide-access logs containing PII.

## 12. Optional Practice Branch: Fixing Faulty Data **After Approval**

Section 8 deliberately kept three Orders in quarantine. To practice the proper remediation workflow, assume **strictly in the lab environment** that the business team audited the records and confirmed:

1. O103 truly has a payable total of 200,000 VND; `total_vnd=200001` was a legacy data-entry bug, not a tax or fee.
2. O104 is not referenced externally; `lineNo` was merely array position inside a `DRAFT` order, and the second line should have `lineNo=2`.
3. O105 was erroneously marked `CONFIRMED` by legacy code without a real transaction; the true status is `CANCELLED` with amount 0. Any external side effects (if emitted) must be handled via separate correction/compensation workflows.

**Do not infer those three decisions from data shape alone.** In production, such assumptions are **valid only with evidence and formal approval**. An empty `CONFIRMED` order might actually be a service order without physical lines; in that case the **target model** must be adapted or granted an explicit exception rather than forcing it to `CANCELLED`.

### Updating via `originalVersion` and Recording Audit

~~~sql
BEGIN;

-- LAB ONLY, after evidence confirms O103's true amount.
UPDATE sales.order_legacy
SET total_vnd = 200000,
    version = version + 1
WHERE tenant_id = 'T1'
  AND order_id = 'O103'
  AND version = 2
  AND total_vnd = 200001;

-- O104: after confirming lineNo has no external references.
UPDATE sales.order_legacy
SET items_jsonb = jsonb_set(
        items_jsonb, '{1,lineNo}', '2'::jsonb, FALSE
    ),
    version = version + 1
WHERE tenant_id = 'T1'
  AND order_id = 'O104'
  AND status = 'DRAFT'
  AND version = 1;

-- O105: only when business confirms no real confirmation ever occurred.
UPDATE sales.order_legacy
SET status = 'CANCELLED',
    confirmed_at = NULL,
    version = version + 1
WHERE tenant_id = 'T1'
  AND order_id = 'O105'
  AND status = 'CONFIRMED'
  AND version = 2;

-- Before COMMIT, verify each UPDATE affects exactly one row.
-- If any returns 0: ROLLBACK and inspect version/source state.
COMMIT;
~~~

This SQL demonstrates **approved** remediation in the lab; bare SQL alone does not record who made the audit decision. In a real system, audit records must reference ticket/evidence/actor, before-and-after state, and rationale; if a correction alters previously published facts, appropriate notification/correction contracts apply. Never emit `OrderConfirmed` as if the order were newly confirmed just because migration patched a row.

After patching, **re-assess from the modified source** rather than reusing the `migration_assessment` temp table captured **before the patch**. To retain history from the first pass, track `assessmentRunId` and create a new assessment snapshot using the exact same rules. In the lab, open a new session or drop the temp table and re-run the assessment creation query from Section 7.

Updated expectations **if all three assumptions and all three `UPDATE`s succeed**:

| Metric | Before Correction | After Correction |
| --- | ---: | ---: |
| OK source Orders | 3 | **6** |
| Current Quarantine | 3 | **0** |
| Eligible OrderLines | 4 | **8** |
| Valid Gross | 720,000 | **945,000** |
| Valid Discount | 35,000 | **35,000** |
| Valid Payable | 685,000 | **910,000** |
| Payable of `CONFIRMED` Orders | 565,000 | **765,000** |

O103 adds 200,000 VND to the `CONFIRMED` cohort; O104 adds 25,000 VND to the overall total while remaining `DRAFT`; O105 is `CANCELLED` with zero lines and adds 0. **Do not confuse the 910,000 total across all Orders with the 765,000 belonging to `CONFIRMED` Orders.**

### Quarantine Is Detection History, Not a Flag to Wipe Clean

The reject table recorded failures at older `sourceVersion`s. Once the source is patched and advances its version, historical reject rows **may remain** for traceability. Reporting "current quarantine = 0" must derive from the **latest assessment**, not `COUNT(*)` over the entire historical reject table. For exception management, use `OPEN`/`RESOLVED` statuses audited by run/version rather than deleting detection evidence and pretending data was always clean.

## 13. When Writes Cannot Stop: Snapshot, CDC, and Catch-Up

In production, the system may continue accepting `DRAFT` Orders during a backfill lasting several hours. A naive "read whole table, then flip write authority" approach loses changes committed after the read timestamp unless a catch-up mechanism captures them.

### Cutover Diagram Maintaining a Single Authoritative Writer

~~~mermaid
sequenceDiagram
    participant W as Old Writer
    participant S as Legacy Source
    participant C as Change Log / CDC
    participant M as Migration Worker
    participant T as Normalized Target
    participant R as Reconciler

    W->>S: Write Order v5
    S->>C: Committed change with offset/LSN
    M->>S: Consistent snapshot at watermark W0
    M->>T: Backfill eligible Orders
    C->>M: Replay changes after W0
    M->>T: Apply by Order + sourceVersion
    R->>S: Read source at cutoff W1
    R->>T: Read target caught up to W1
    R-->>M: Coverage, detail, totals, lag, quarantine
~~~

**Technical requirement that must hold:** the snapshot point and the log/CDC position must be **tightly correlated** so no gap opens between the snapshot and the change stream. Merely noting the wall-clock time when `SELECT` starts and saying "fetch newer events afterward" is insufficient, because an earlier transaction may start before that timestamp and commit after it. Implementation depends on PostgreSQL logical decoding, replication slots, snapshot protocols, and the actual CDC tooling; configuration, WAL retention, and permissions must all be verified.

### Version-Aware Rollout Steps

1. **Expand:** add target schema, constraints, and appropriate indexes; keep legacy source authoritative.
2. **Capture:** establish a committed change stream with checkpoints and snapshot/stream gap protection.
3. **Backfill:** migrate each Order atomically by `sourceVersion`; route invalid ones to quarantine without blocking the entire stream indefinitely if policy permits.
4. **Catch-up:** apply post-watermark changes; deduplicate, enforce ordering **within a single Order**, and distinguish corrections from business events.
5. **Shadow read:** serve one request by reading both legacy and target through a canonical mapper, comparing meaningful values; return only one path to the user.
6. **Read switch:** gradually shift read use cases once reconciliation, tenant permissions, latency, and performance pass gates.
7. **Write cutover:** use a single coordination protocol that definitively **transfers write authority from legacy to target**. Block/stop any old writer still hitting the source, drain or adjudicate in-flight commands, and verify zero data gaps.
8. **Contract:** drop `items_jsonb`/legacy columns only after all readers, writers, exports, consumers, and recovery paths are cleared.

### Safely Applying an Order Update

Suppose the snapshot saw O101 `version=1`; during backfill, a legitimate old writer adds a line and commits `version=2`. The target may already hold `version=1`. A catch-up handler must do:

~~~text
Receive committed change for (tenant=T1, order=O101, version=2).

If target sourceVersion=1:
    verify source v2 passes completeness, auth, and invariants;
    in a single transaction, replace O101's line set and totals
    to match v2, preserving line identities, advancing version to 2;
    commit target state + change processing checkpoint.

If target already has sourceVersion=2:
    compare meaningful payload/hash; if identical, deduplicate;
    if different, raise drift alert—never pick a side blindly.

If target is at sourceVersion>2:
    do not overwrite with version 2;
    handle ordering/gaps and reconcile against the authoritative source.

If source v2 fails validation:
    quarantine version v2 and halt write cutover
    for the affected Order according to policy.
~~~

The flow above is a **protocol**, not a simple SQL `UPSERT`. Replacing all lines must preserve Order atomicity and never erase changes **legitimately created by the new target writer after cutover**. While the source remains the writer, the target acts strictly as a replica/projector; after cutover, legacy replay **must be disabled or fenced**.

### CDC Is Not an Integration Event

A row `UPDATE` caused by backfill, schema cleanup, or cache recomputation is not itself an **OrderConfirmed** event. Emitting `OrderConfirmed` whenever CDC observes a change on `order_legacy` could cause Inventory to reserve stock a second time. Separate **state replication streams** from **domain events**, emitting integration events only when a real business transition occurs at the authoritative source.

## 14. Separating Java Domain, Persistence Mapping, and API Contracts

A common architectural mistake is letting the exact same Java class serialize to JSONB, act as the ORM entity, serve HTTP requests, and double as an integration event. After migration, changing storage can accidentally strip fields from clients or let callers write `total`/`status` directly.

The domain model must keep **behavior and invariants** independent of storage layout:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

record Line(int lineNo, String skuId, long quantity,
            long unitPriceVnd, long discountPerUnitVnd) {
    Line {
        Objects.requireNonNull(skuId);
        if (lineNo <= 0 || skuId.isBlank() || quantity <= 0
                || unitPriceVnd < 0 || discountPerUnitVnd < 0
                || discountPerUnitVnd > unitPriceVnd) {
            throw new IllegalArgumentException("Invalid line");
        }
    }
    long gross() {
        return Math.multiplyExact(quantity, unitPriceVnd);
    }
    long discount() {
        return Math.multiplyExact(quantity, discountPerUnitVnd);
    }
}

record Totals(long gross, long discount, long payable) {}
enum OrderStatus { DRAFT, CONFIRMED, CANCELLED }

final class Order {
    private final String orderId;
    private final List<Line> lines = new ArrayList<>();
    private OrderStatus status = OrderStatus.DRAFT;
    private long version;

    Order(String orderId) {
        this.orderId = Objects.requireNonNull(orderId);
    }

    void addLine(Line line) {
        if (status != OrderStatus.DRAFT)
            throw new IllegalStateException("Order not editable");
        Objects.requireNonNull(line);
        if (lines.stream().anyMatch(l -> l.lineNo() == line.lineNo()))
            throw new IllegalArgumentException("Duplicate lineNo");
        var current = totals();
        Math.addExact(current.gross(), line.gross());
        Math.addExact(current.discount(), line.discount());
        lines.add(line);
        version++;
    }

    Totals totals() {
        long gross = 0, discount = 0;
        for (Line line : lines) {
            gross = Math.addExact(gross, line.gross());
            discount = Math.addExact(discount, line.discount());
        }
        return new Totals(
            gross, discount, Math.subtractExact(gross, discount));
    }

    void confirm() {
        if (status != OrderStatus.DRAFT || lines.isEmpty())
            throw new IllegalStateException("Cannot confirm");
        totals();
        status = OrderStatus.CONFIRMED;
        version++;
    }

    List<Line> lines() { return List.copyOf(lines); }
    long version() { return version; }
    OrderStatus status() { return status; }
}
~~~

This is **stripped-down** Java 17 code illustrating domain rules; it omits a rehydration factory, tenant scoping, command idempotency, and Payment/Inventory integration. A **production repository** needs a controlled rehydration path that restores persisted status, version, and lines directly—**never replaying `addLine`/`confirm` to load history**, which would bump versions and trigger spurious side effects.

During transition:

- **LegacyOrderRepository:** reads `items_jsonb` and maps it into validated domain `Line`s.
- **NormalizedOrderRepository:** reads header/lines, reconstructs the exact same domain `Order`, and verifies totals.
- **OrderCommandService:** enforces auth/tenant checks, `expectedVersion`, and state transitions; only the authoritative writer persists changes.
- **OrderViewMapper:** builds HTTP responses per contract without leaking internal `row_version` columns or raw JSONB simply because storage has them.
- **EventMapper:** emits properly versioned integration events (`schemaVersion`) once a business transition commits.

For any read request, both repositories must return the same **canonical OrderView** required by the contract. For example, Order O100 always returns `payable=310,000 VND` and two lines, whether stored in JSONB or normalized tables. New fields such as `gross`/`discount` can be exposed under separate API versioning policies; **storage migration never forces clients to change simultaneously**.

### Events and Backfill Are Two Different Kinds of Change

A `CONFIRMED` Order from last week copied from legacy to target **was not just confirmed again**. Therefore, migration **must not emit a new `OrderConfirmed`** for each copied record. If Analytics needs a rebuild, use a snapshot/CDC stream or a dedicated backfill event carrying distinct semantics and stable ID/lineage—never tricking Notification or Inventory into seeing a brand-new order.

When an actual command confirms an Order after cutover, write **state + outbox in the same transaction**, preserving the same `eventId` across relay retries. Event `occurredAt` reflects business occurrence time, not when migration or CDC ingested the row.

## 15. Reconciling Reports and Downstream Projections

Analytics already runs a report on **confirmed orders and revenue by SKU**. After switching from JSONB to relational tables, you must prove **identical cohort, identical definitions, and identical cutoff**, not merely that the new table contains rows.

Assuming each `CONFIRMED` Order holds a valid line snapshot and partial confirmation does not yet exist, a fact table can use the grain:

> **One fact row = one confirmed OrderLine belonging to one Order, within a specific tenant**, carrying price snapshot, discount, and confirmation timestamp.

~~~sql
CREATE SCHEMA IF NOT EXISTS mart;

CREATE TABLE mart.fact_confirmed_order_line (
    tenant_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    line_no INTEGER NOT NULL,
    sku_id TEXT NOT NULL,
    confirmed_at TIMESTAMPTZ NOT NULL,
    business_date DATE NOT NULL,
    quantity BIGINT NOT NULL CHECK (quantity > 0),
    gross_vnd BIGINT NOT NULL CHECK (gross_vnd >= 0),
    discount_vnd BIGINT NOT NULL CHECK (discount_vnd >= 0),
    net_vnd BIGINT NOT NULL CHECK (net_vnd >= 0),
    source_order_version BIGINT NOT NULL,
    transform_version INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, order_id, line_no),
    CHECK (discount_vnd <= gross_vnd),
    CHECK (gross_vnd - discount_vnd = net_vnd)
);
~~~

On the **uncorrected** fixture, the OK Orders are O100, O101, and O102; O101 is still `DRAFT`. Thus the confirmed fact contains **three rows**: two lines from O100 and one line from O102. Query against the normalized target:

~~~sql
SELECT l.sku_id,
       SUM(l.quantity) AS units,
       SUM(l.quantity::NUMERIC * l.unit_price_vnd) AS gross,
       SUM(l.quantity::NUMERIC * l.discount_per_unit_vnd)
           AS discount,
       SUM(l.quantity::NUMERIC *
           (l.unit_price_vnd - l.discount_per_unit_vnd))
           AS net
FROM sales.order_header AS h
JOIN sales.order_line AS l
  ON l.tenant_id = h.tenant_id AND l.order_id = h.order_id
WHERE h.tenant_id = 'T1'
  AND h.status = 'CONFIRMED'
GROUP BY l.sku_id
ORDER BY l.sku_id;
~~~

Expected output:

| SKU | Units | Gross | Discount | Net |
| --- | ---: | ---: | ---: | ---: |
| A | 2 | 240,000 | 20,000 | **220,000** |
| B | 4 | 360,000 | 15,000 | **345,000** |
| **Total** | **6** | **600,000** | **35,000** | **565,000** |

**BI reconciliation rule:** for the same tenant, business date/cutoff, status, and schema/transform version, total net in the confirmed fact must match total payable of `CONFIRMED` Orders **within the successfully migrated cohort**. Never compare 565,000 against a source total containing faulty O103 and blame the discrepancy on the new database. Surface **coverage/quarantine** labels or metadata so viewers do not mistake interim numbers for complete totals.

**OrderConfirmed does not equal PaymentCaptured.** If the question asks for **collected revenue**, use the authoritative Payment source, accounting for failed attempts, partial captures, refunds, currencies, and recognition policies. Never substitute `status = CONFIRMED` for collected cash or accounting revenue.

### Grain Traps During Schema Migration

If an Order has two lines and two `PaymentAttempt`s, joining all three sources and summing line net can double-count revenue per attempt. To count Orders, use `COUNT(DISTINCT order_id)` over the proper grain and cohort; to count items sold, use `SUM(quantity)`; for collected money, use a dedicated capture/allocation fact at its own grain.

If Analytics previously read JSONB directly, you can swap the adapter to query normalized tables while **preserving the semantic model and metric version** when meaning is unchanged. If date or status policies change at the same time, that is a **separate KPI change** requiring independent review and announcement.

## 16. Performance and Sizing: Backfill Must Not Disrupt OLTP

Suppose production holds **5 million Orders averaging 8 lines/Order**. Logical line count is roughly **40 million**, excluding audit, outbox, and error tables. Never wrap all 5 million Orders inside one giant transaction during peak hours.

| Risk | Potential Impact | Control |
| --- | --- | --- |
| Oversized transactions | Locks, WAL spikes, timeouts, slow rollbacks | Batch by `(tenant, order)` and commit bounded Orders/batches |
| Continuous JSONB scans | CPU/I/O spikes degrading checkout latency | Throttle throughput and monitor p95/p99 under live load |
| Bulk index builds | Disk/temp consumption, write stalls | Choose engine-appropriate index build strategies and rollout windows |
| CDC lag | Retained WAL/logs, target falling behind | Monitor offset/lag, throttle backfill, maintain catch-up capacity |
| High faulty-record volume | Quarantine bloat, slow coverage convergence | Classify by reason, owner, and remediation workflow |
| Unversioned UPSERT | Stale records overwriting newer state | Conditional updates guarded by version, single authoritative writer |
| Full-scan reconciliation | Heavy I/O warming unneeded pages | Reconcile by batch/key; use sampling only as a supplement, not a replacement |
| Sensitive data in logs | Data exposure during debugging | Log IDs, error codes, and summaries under strict access controls |

### A Safe Order-Level Batch Algorithm

~~~text
checkpoint = (lastTenantId, lastOrderId, sourceWatermark)

while eligible Orders remain in snapshot:
    fetch next N Orders in stable keyset order;
    classify using versioned rules;
    for each OK Order:
        BEGIN target transaction
        write header + all lines at source version
        verify line count, amounts, and state at that point
        COMMIT
    for each faulty Order:
        record quarantine with version, reason, owner
    reconcile batch totals and persist result
    persist checkpoint only after the batch is durable

after snapshot:
    apply committed CDC changes starting from safe watermark;
    wait until lag < approved threshold;
    re-reconcile at the same cutoff;
    only then consider read/write cutover
~~~

Batch size `N` should not be guessed from a neat constant. Benchmark against source p95 latency, lock waits, WAL generation, Order size distribution, and actual CDC throughput. Extremely large Orders may warrant special handling, yet must remain **aggregate-consistent** rather than splitting one Order across two transactions and exposing half-migrated data to readers.

### Observability Metrics

- Source read latency, transaction lock waits, deadlocks, and timeout rates.
- Batch throughput (Orders/s, Lines/s), source/target disk usage, and WAL/CDC retention.
- Counts of evaluated, OK, quarantined, migrated, and verified Orders—never conflating states.
- Line mismatches, amount discrepancies, and per-batch version skews.
- CDC offset lag and time lag, retry counts, and target write failures.
- Shadow-read discrepancy rates and pre-/post-switch p95/p99 latency.
- Duplicate event rates, outbox backlog depth, and state-transition conflicts.

Real benchmark reports must state PostgreSQL version, hardware resources, indexes, dataset sizes, and workload profile. This article **does not claim to have executed these queries or benchmarks**; the SQL is provided as a template to run in a test environment.

## 17. Phased Rollback and Roll-Forward Plan

Rolling back a migration **before new writes occur** differs fundamentally from rolling back **after switching write authority**. Plan this before enabling feature flags.

| Phase | Authoritative Writer | How to Revert | What to Avoid |
| --- | --- | --- | --- |
| Expand (target tables created) | Legacy | Stop backfill, keep source intact | Dropping schema while jobs still run |
| Backfill (target is a replica only) | Legacy | Disable projector, read from legacy | Treating an unverified target as truth |
| Read switch (writes still on legacy) | Legacy | Point reads back to legacy, fix projector | Dismissing shadow mismatches as harmless |
| Active write cutover | Clear arbitration required | Pause writes, adjudicate in-flight requests, roll forward/hotfix if needed | Allowing two writers to accept commands asynchronously |
| Target accepting new writes | Target | Prefer roll-forward or a controlled reverse-migration with reconciliation | Restarting old writers to overwrite new state with stale legacy rows |
| Contract (legacy schema dropped) | Target | Restore via pre-tested backups/transforms | Assuming `DROP TABLE` can be rolled back via Git |

**Irreversibility hazard:** once live, the target may hold columns, statuses, or line items created after cutover that legacy `items_jsonb` cannot represent or older binaries cannot understand. Simply "redeploying the old binary" can cause **data or semantic loss**. Temporarily halting writes or rolling forward is safer than blind rollback.

### Prerequisites Before Removing Legacy

1. All reads, writes, batch jobs, exports, and admin scripts are migrated and verified.
2. API/event consumers and Analytics no longer depend directly on `items_jsonb`.
3. Active quarantine records are resolved or governed by an approved unmigratable-data policy.
4. Backup/restore and replay procedures have been tested—not merely checked for file existence.
5. Final reconciliation evidence includes cutoff, version, and owner sign-off.
6. No CDC or catch-up jobs still read legacy, and retention/audit obligations are satisfied.

**A Git commit containing `DROP COLUMN` is not proof those prerequisites were met.** Deployment readiness must be verified from migration history, live schema state, active app releases, and dependent pipelines.

## 18. Mandatory Test Suite for Model Changes

| Category | Scenario | Expected Behavior |
| --- | --- | --- |
| Source schema | JSONB array with missing fields, wrong types, oversized numbers | Classified/quarantined prior to `CAST` |
| Valid sample | O100–O102 | Verdict OK, exact monetary values |
| Total mismatch | O103 | `AMOUNT_MISMATCH`, not silently modified |
| Duplicate line key | O104 | `DUPLICATE_LINE_NO` |
| Empty confirmed | O105 | `EMPTY_CONFIRMED` |
| PK/FK/CHECK | Duplicate PK line, `quantity=0`, `discount > unitPrice` | Target rejects at the appropriate constraint |
| Idempotent backfill | Run twice on the same snapshot | No duplicate Orders/Lines; all fields match |
| Mid-transaction failure | Line `INSERT` fails after header succeeds | Entire Order transaction rolls back |
| Domain rehydration | Restore `CONFIRMED` Order from target tables | Does not re-run `confirm` or emit new events |
| Versioning | Legacy update v2 after v1 snapshot | Applied cleanly in order; never overwrites newer state |
| Concurrent commands | Two workers modify same Order version | One update wins; the other conflicts |
| Tenant isolation | T2 tries to read/write T1's O100 | Rejected; no price/order leakage |
| Reconciliation | Alter one target line's price by 1 VND in test env | Caught by line-level and total checks |
| Event replay | Relay redelivers `OrderConfirmed` with same `eventId` | Consumer does not execute duplicate business effects |
| Event vs. backfill | Copy already-`CONFIRMED` Order from legacy | Does not emit `OrderConfirmed` as a new event |
| Analytics | Order with two lines, Payment with two attempts | Join does not multiply revenue |
| Cutover | Old and new binaries overlap during switch | Zero uncoordinated dual writes |
| Rollback | Target wrote new data unsupported by legacy | Preservation plan enforced before binary change |
| Large payloads | Order with very many lines | Respects published batch/transaction limits |

### Pass/Fail Reconciliation Gates—Not Just Pretty Charts

Automate these gates:

~~~text
assert evaluated_orders = ok_orders + quarantined_orders
assert target_orders_for_snapshot = ok_orders
assert target_lines_for_snapshot = SUM(ok_source.line_count)
assert header_differences_for_snapshot = 0
assert line_differences_for_snapshot = 0
assert target_internal_amount_mismatch = 0
assert target_conflict_unresolved = 0
assert consumer_schema_contract_tests = PASS
assert historical_migration_replayed_as_new_event = 0
~~~

In production, every metric and scope must be qualified by **tenant, snapshot watermark, `sourceVersion`, and `batch/runId`**. If the source produces new Orders after cutoff, exclude them from `target_orders_for_snapshot` when reconciling the snapshot. **Comparing mismatched timeframes and seeing a difference is not automatically a bug**, yet the system must prove whether the delta comes from late arrivals or genuine errors.

## 19. Deliverable Exercise Set

Perform these exercises **on a test database** using the Section 4 fixture. Document any missing business decisions as explicit **assumptions**—never fabricate observed outputs or ignore faulty rows. Produce a short design report including SQL queries/tables and test plans.

### Part A — Modeling and Migration

**Exercise 1. Grain and identity.** Describe the grain of `order_legacy`, `order_header`, and `order_line`. Why can `lineNo` not serve as a database-wide PK? Must the FK from line to header include `tenantId`? Why?

**Exercise 2. Enforcing invariants.** Build a matrix covering `quantity>0`, `discount<=price`, header totals matching lines, non-empty `CONFIRMED` Orders, and immutability of lines on `CONFIRMED` Orders. Indicate which are enforced by PK/FK/CHECK and which require transaction/domain logic.

**Exercise 3. Hand-calculating sample data.** Without peeking at the answer table, compute gross, discount, and payable per Order, totals across the three valid Orders, totals across the two valid `CONFIRMED` Orders, and accepted line count. Identify quarantined rows and their reasons.

**Exercise 4. Structural validation.** Suppose a JSONB element has `unitPriceVnd` as string `"120000"`, or a number exceeding `BIGINT`. Does the Section 6 preflight catch both? What rules must be added before parsing?

**Exercise 5. Backfill and re-runs.** Execute the SQL from Sections 5–9 on a clean test database. Re-run the backfill from the same assessment. What must stay unchanged? If a target row already has the same key but `unitPriceVnd` off by 1 VND, does `ON CONFLICT DO NOTHING` raise an error?

### Part B — Reconciliation and Remediation

**Exercise 6. Three reconciliation layers.** Write/explain the count query, header comparison, and line-level `FULL OUTER JOIN`. Why do matching aggregate totals still fail to prove correctness?

**Exercise 7. Quarantine.** O103 is off by 1 VND, O104 has duplicate `lineNo`, and O105 is an empty `CONFIRMED` order. Propose required evidence before patching; how should data be re-assessed post-correction?

**Exercise 8. Deliberate drift.** In the test DB, alter one target OrderLine's `unit_price_vnd` away from source after disabling application write paths. Which checks catch it, and which might miss it? How should it be restored?

**Exercise 9. Analytical reporting.** From the three OK Orders, compute net by SKU and count of `CONFIRMED` Orders. Can 685,000 VND be reported as collected revenue? If O100 has two `PaymentAttempt`s, how does a naive join distort the numbers?

### Part C — Rollout, Architecture, and Operations

**Exercise 10. Changes during backfill.** Snapshot captures O101 at `version=1`, source adds a line and commits `version=2`, then a v2 event arrives ahead of a retried v1 event. Diagram how target apply/replay handles this and explain how version regression is prevented.

**Exercise 11. Cutover and rollback.** Design the deployment sequence when legacy web, batch, and admin writers exist; when can they be shut down? If the target already accepted an Order with a new field unknown to legacy, why is rolling back to the old binary dangerous?

**Exercise 12. Events and downstream consumers.** A relay sent `OrderConfirmed` and then crashed; migration later moves that Order to the new tables. Should another `OrderConfirmed` fire due to backfill? Distinguish `commandId`, `eventId`, `sourceVersion`, and `schemaVersion`.

**Exercise 13. Choosing storage technology.** If targeting **one document per Order** instead of normalized tables, what parts of the process stay the same and what changes regarding transactions, validators, and concurrent updates? If using a **graph** to traverse customer–order–SKU links, should the graph hold authority to confirm Orders?

**Exercise 14. Verification plan.** Propose at least 10 test cases, a monitoring dashboard list, and three pre-cutover gates. Give an example of an **unsafe rollback** and a safer alternative.

### Submission Report Template

| Section | Required Content |
| --- | --- |
| Model decision | Business rules, grain, PK/FK, JSONB → rows mapping |
| Source quality | Type preflight outcome, assessment verdicts, quarantine |
| Backfill | OK records, checkpoint/batch keys, INSERT/commit results |
| Reconciliation | Order/line counts, totals, header diffs, line diffs |
| Compatibility | Old/new readers, old/new writers, API/events, and KPIs |
| Deployment | Expand, snapshot, catch-up, shadow, switch, contract |
| Failure handling | Retries/versions, quarantine, rollback/roll-forward |
| Verification | Test cases, results, environment, versions, limitations |

If no test database is available to execute queries, mark SQL outputs as **not run** and clearly state **expected** results from the fixture. Never mark an unexecuted query or benchmark as `PASS`.

## 20. Solution Guide and Verification Key

### 20.1. Exercises 1–3: Modeling and Arithmetic

**Exercise 1:** Both `order_legacy` and `order_header` have a grain of **one Order**. Each element of `items_jsonb` and each `order_line` row represents **one OrderLine**, requiring `(tenantId, orderId, lineNo)` for identity. Every Order can have `lineNo=1`; using `lineNo` alone as a system-wide PK collides immediately. The FK must include `tenantId` to prevent a `T2` OrderLine from referencing a `T1` header. Keys must still pair with authorization checks, since a PK alone does not prove caller permission.

**Exercise 2:** Line-level `CHECK`s protect `quantity>0`, `unitPrice>=0`, and `discount` within price bounds. The PK prevents duplicate `lineNo` **once parsed into the target**; the FK protects parent header existence. Header-vs-line totals span multiple rows, and keeping `CONFIRMED` Orders non-empty and immutable requires domain/transaction logic or carefully designed triggers/procedures. Invariants must hold across **all write paths**, including batch jobs and scripts.

**Exercise 3:** Three clean Orders:

| Order | Gross | Discount | Payable | Lines |
| --- | ---: | ---: | ---: | ---: |
| O100 | 330,000 | 20,000 | 310,000 | 2 |
| O101 | 120,000 | 0 | 120,000 | 1 |
| O102 | 270,000 | 15,000 | 255,000 | 1 |
| **Total OK** | **720,000** | **35,000** | **685,000** | **4** |

The two valid `CONFIRMED` Orders (O100 + O102) have payable **565,000 VND**. O103 has a source total of 200,001 vs. lines totaling 200,000; O104 duplicates `lineNo`; O105 is `CONFIRMED` yet empty. **Never count the three quarantined Orders toward target coverage or valid cohorts**.

### 20.2. Exercises 4–5: Parse Safety and Idempotency

**Exercise 4:** A `jsonb_typeof` preflight catches prices encoded as strings; however, an oversized JSON number still reports type `number`, so **type checks alone are insufficient**. You must check integrality/scale and bounds for `lineNo` (`INTEGER`), `quantity` (`BIGINT`), monetary `BIGINT` ranges, array length/depth, and missing keys prior to `CAST`. Application/decoder parsing can also trap per-record errors and quarantine offenders without halting the whole stream blindly.

**Exercise 5:** Re-running backfill on the **same snapshot** must not increase header/line counts or monetary totals. `ON CONFLICT DO NOTHING` **silently skips a target row holding corrupted content** under a matching key, so per-Order and per-line reconciliation is needed to catch drift and block cutover. Never use unconditional overwriting `UPSERT`s once the target accepts live writes.

### 20.3. Exercises 6–8: Three Ways to Prove Data Correctness

**Exercise 6:** Coverage counts show whether Orders/lines exist, not whether prices match. Aggregate totals can mask offsetting errors. Header comparison checks IDs, status, customer, money, version, and timestamps. Line-level `FULL OUTER JOIN` surfaces **missing, extra, and mismatched fields**. Target-internal recomputation catches header-line drift even without source access, yet misses coordinated corruption of both header and lines. All three are required.

**Exercise 7:** O103 needs invoices/ledgers/historical pricing rules; O104 needs proof of `lineNo` semantics and external references; O105 needs business truth verified across Payment, Inventory, and audit logs. Once a correction is approved, create a new source version, log the audit trail, capture a fresh assessment, and migrate **the records that transitioned from quarantine to OK** per protocol. Never erase historical reject entries without traceability.

**Exercise 8:** Altering a line's `unitPriceVnd` in test may trigger a `CHECK` violation if negative or below discount; if valid yet off by 1 VND, **line-level `FULL OUTER JOIN`** catches it. **Target-internal recomputation** usually catches it too because the header hasn't changed, though someone altering both header and line together would slip past it—at which point line-by-line comparison against the source still catches it. Restore from the **authoritative source via controlled, audited correction**, never by hiding a 1 VND adjustment on another line.

### 20.4. Exercise 9: Analytical Grain and Metrics

| SKU | Confirmed Quantity | Gross | Discount | Net |
| --- | ---: | ---: | ---: | ---: |
| A | 2 | 240,000 | 20,000 | **220,000** |
| B | 4 | 360,000 | 15,000 | **345,000** |
| **Total** | **6** | **600,000** | **35,000** | **565,000** |

The OK source cohort has **three Orders**, of which **only two are `CONFIRMED`**; `DRAFT` O101 contributes to the 685,000 all-Order total, not the 565,000 `CONFIRMED` cohort. Confirmed Order count is `COUNT(DISTINCT order_id)` per tenant/cutoff, not `COUNT(*)` of fact rows. Without `PaymentCaptured` evidence, **neither 685,000 nor 565,000 represents collected revenue**. Joining two `PaymentAttempt`s directly onto O100's two lines multiplies amounts; use dedicated capture/attempt facts at the proper grain, handling duplicates and refunds.

### 20.5. Exercises 10–12: CDC, Cutover, and Events

**Exercise 10:** Snapshot puts O101 v1 into target; when CDC v2 arrives, apply it in a single Order-wide transaction provided target is at v1 and source v2 passes validation. A subsequent retried v1 is ignored or reconciled because versions cannot regress. If v2 arrives before v1 reaches the target, either reconstruct full state or wait/read from the authoritative snapshot—**never fabricate partial lines**. Update checkpoints only after target commit, never before.

**Exercise 11:** Upgrade readers and writers using a **version compatibility matrix**, executing cutover only once web, batch, admin, and all other legacy write paths are revoked, in-flight commands are adjudicated, target is caught up, and reconciliation is `PASS`. If the target holds new fields or statuses unsupported by legacy, an old writer can overwrite and destroy them. Prefer pausing writes, hotfixing, or rolling forward; reverting backwards requires its own reconciled migration.

**Exercise 12:** Do not emit a new `OrderConfirmed` due to backfill. **commandId / idempotency key** identifies a retryable command intent; **eventId** identifies a committed business occurrence and stays constant across broker redeliveries; **sourceVersion** tracks the copied Order version; **schemaVersion** describes the event payload format. Each plays a distinct role and must never be conflated.

### 20.6. Exercises 13–14: Technology Choices and Deployment Gates

**Exercise 13:** Targeting one document per Order still requires locking down grain, money math, identity, `sourceVersion`, quarantine, CDC, reconciliation, security, and cutover. However, relational FKs/constraints change: schema validators inspect document structure, atomicity spans **one document**, outbox in another collection requires separate transaction/protocol handling, and huge line counts create oversized documents or write hotspots. If using a graph to query Customer→Order→SKU paths, treat the graph as a **read projection**—never let it confirm Orders merely because nodes/edges exist.

**Exercise 14:** Minimum test coverage includes bad JSON parsing, duplicate `lineNo`, money mismatches, empty confirmed Orders, FK/CHECK violations, backfill retries, header/line rollback, full outer joins, concurrent version conflicts, out-of-order CDC, event deduplication, tenant isolation, shadow reads, BI cohorts, and mixed-version rollbacks. Monitor coverage, quarantine counts, key/money mismatches, CDC lag, conflicts, p95 latency, outbox backlog, and `transformVersion`. Three pre-cutover gates could be:

1. **Correctness:** all active Orders satisfy policy; header/line diffs = 0; totals and versions match at the cutoff (`PASS`); quarantines are signed off.
2. **Operational consistency:** CDC catch-up within lag limits, zero unresolved in-flight commands, transaction/version/idempotency tests `PASS`.
3. **Compatibility and recoverability:** all writers/readers/consumers ready, shadow-read and security tests `PASS`, backup/restore and roll-forward/rollback proven.

These three gates require **named owners and hard evidence**. A "green CI" build while active Orders remain unresolved in quarantine or an old writer still runs is never enough to flip write authority.

## 21. Grading Rubric, Checklist, and Conclusion

### Reference Rubric — 100 Points

| Criterion | Points | Passing Standard |
| --- | ---: | --- |
| Requirements, grain, IDs, boundaries, and invariants | 15 | Accurate Order/Line design; clear separation of Sales/Payment/Inventory ownership |
| Target schema and JSONB → row mapping | 15 | Clear PK, FK, CHECK constraints, indexes, totals, statuses, and versions |
| Preflight, classification, and quarantine | 15 | Catches O103/O104/O105 without auto-patching amounts or IDs |
| Safe backfill, retries, and version guards | 15 | Per-Order atomic transactions; never overwrites newer state |
| Comprehensive reconciliation | 20 | Coverage, totals, headers, lines, diffs, and cutoff aligned |
| Rollout/CDC, events, and rollback | 10 | Single authoritative writer; outbox/idempotency; viable recovery plan |
| Analytics, security, and testing | 5 | Proper grain, tenant isolation, late data, and concurrency tests |
| Reasoning and evidence | 5 | Distinguishes executed results from expected ones; states assumptions |
| **Total** | **100** | |

### Change Handoff Checklist

- **Source:** Is pre-migration Order/Line semantics understood, including what `total_vnd` covers and who owns the data?
- **Target:** Does the new relational model enforce proper grain, identity, FKs, CHECKs, indexes, and invariants—rather than merely exploding JSON into rows?
- **Keys:** Do all joins and authorization checks carry tenant namespaces, with `lineNo` unique only within an Order?
- **Snapshots:** Are locked-in prices and discounts preserved rather than recomputed from the current Catalog?
- **Money:** Are gross, discount, and payable exact integers without floating-point math or implicit rounding?
- **Preflight:** Were JSON shape, numeric types, and value ranges verified prior to `CAST` on real data?
- **Quarantine:** Does every exception record business key, `sourceVersion`, reason, owner, and evidence without counting toward successful migration?
- **Migration:** Are checkpoints, Order-level transactions, idempotent re-runs, and guards against overwriting newer versions in place?
- **Reconciliation:** Does it match cohorts, headers, lines, totals, statuses, versions, timestamps, and missing/extra records at a fixed cutoff?
- **CDC:** Are snapshot and committed change streams gap-free, committing offsets only after target writes are durable?
- **Writers:** Does exactly one authoritative source exist before and after cutover, with no batch/admin jobs bypassing protocols?
- **API:** When only storage changes, do legacy clients continue receiving their contracted responses, or are versioned changes communicated properly?
- **Events:** Does historical copying avoid emitting new `OrderConfirmed` events, while live events commit atomically with outbox rows and stable `eventId`s?
- **Analytics:** Do facts define clear grain without equating confirmed with paid, publishing metrics only when coverage/quality meets policy?
- **Security:** Are tenant boundaries, sensitive data in logs, snapshots, and backups/quarantine access-controlled?
- **Operations:** Have p95/p99 latency, WAL/CDC lag, index footprint, rollback/restore times, and large-batch costs been measured?
- **Recovery:** Once new target writes exist, can you roll forward safely instead of letting old writers strip fields or statuses?
- **Evidence:** Are actual SQL outputs, migration code, tests, source watermarks, transform versions, and sign-offs properly archived?

### Lessons Learned on Choosing Data Models

A single row embedding JSONB works well when Orders are usually loaded whole, line counts stay small, per-line FKs/indexes are unnecessary, and commands stay within aggregate boundaries. A normalized relational target expresses **per-OrderLine keys**, child-row constraints, and SKU queries more clearly, yet **never replaces domain transactions**. Even if choosing a document database over two tables, the same tests for **identity, invariants, historical snapshots, idempotency, access control, and reconciliation** still apply—only the storage engine and physical transaction scope change. Graph models or analytical facts should be treated as **query-driven projections** when warranted, never as excuses to blur business ownership boundaries.

**Conclusion:** A data model change succeeds only when **before-and-after semantics are faithfully preserved or intentionally evolved**, legacy data is **classified and transformed by explainable rules**, and results are **reconciled over identical keys and timestamps**. In this exercise, three clean Orders become **3 headers, 4 lines, and 685,000 VND total payable**, while **3 faulty Orders sit in quarantine with documented evidence**; the valid `CONFIRMED` cohort totals **565,000 VND**. Never treat 50% coverage as production-cutover-ready simply because a script exits cleanly. Adding snapshots/CDC, writer fencing, contracts, analytics alignment, rollback plans, and concurrency tests turns **expand → assess/quarantine → backfill → catch-up → reconcile → switch → contract** into an **accountable, evidence-backed, verifiable** method of model evolution rather than a risky one-off `ALTER TABLE`.
