# Slowly Changing Dimension Type 1: Overwriting Values

## 1. What is SCD Type 1 and what problem does it solve?

In analytical modeling, a **dimension** describes the context used to interpret an event in a fact table: which segment a customer belongs to, what a product is named, or which region a store is in. These attributes usually change more slowly than transactions, yet they can still be updated after being loaded into the data warehouse.

**Slowly Changing Dimension Type 1 (SCD Type 1)** manages changes by **overwriting the current attribute value directly on the existing dimension row**, rather than creating an additional historical row version for each change.

For example, customer `CUS-42` has a misspelled display name:

| Load time | customer_bk | display_name in dimension | segment |
| --- | --- | --- | --- |
| Before correction | CUS-42 | Jhon Nguyen | STANDARD |
| After correction | CUS-42 | John Nguyen | STANDARD |

With SCD Type 1, the dimension row holds the corrected name `John Nguyen` and **does not retain `Jhon Nguyen` as a prior dimension version**. Existing facts pointing to the same dimension key will display the new name when joined.

This property is very useful for fixing typos, standardizing labels, correcting misentered region codes, or attributes where the organization **intentionally wants all reports, including historical reports, to use the corrected current value**.

However, this is also the core trade-off: **SCD Type 1 does not preserve the change history of overwritten attributes within the dimension table itself**. If a report needs to know "what segment did the customer belong to at the time of purchase?", a current Type 1 row alone is generally not sufficient.

### What SCD Type 1 has and does not have

- Has: a single current representation per business key, a stable reference key, and relatively simple attribute updates.
- Has: the ability to **re-group historical facts** by the new dimension value when that is the business intent.
- Does not have: a sequence of prior values for overwritten attributes, unless the organization preserves history **in another source** such as an audit log, snapshot, CDC, or SCD2 table.
- Does not have: automatic guarantees that source data is accurate; normalization, update permissions, and validation are still required.
- Does not have: any justification to overwrite business events, financial transactions, identities, or fact keys.

The word "slowly" names a family of dimension design techniques; it does **not** dictate waiting some interval before updating, nor does it imply that every attribute changes slowly.

## 2. Defining the grain: who or what does one dimension row represent?

The question before writing SQL is:

> In this dimension, **which single business entity does one row represent**, and what makes two rows count as the same entity?

For a `dim_customer` using Type 1 throughout, assume each tenant has a canonical customer code confirmed by an identity management system:

**Grain:** one row per `(tenant_id, customer_bk)` pair.

For `dim_product`, the grain may be one product per `(tenant_id, product_bk)`. If an SKU is reused for a different product, the SKU is **not stable enough to serve as a business key**; a more durable identifier or a verified namespace/time rule is required.

### Three keys that must be kept separate

| Key | Role | Example |
| --- | --- | --- |
| **Business key (BK)** | Identifies the entity according to the authoritative source/business contract. | `customer_bk = CUS-42`. |
| **Surrogate key (SK)** | Warehouse-managed surrogate key referenced by facts. | `customer_sk = 1087`. |
| **Source record key** | Record identifier inside a source system, which may differ across systems. | `crm_customer_id = 42`, `app_user_id = U-918`. |

**Type 1 must preserve the SK when only updating attributes**: all facts before and after the change continue pointing to the same `customer_sk`. Deleting the old dimension row and inserting a new row with a different SK would orphan facts or require updating millions of fact rows, defeating the purpose of a simple overwrite.

Furthermore, **do not treat two source IDs with identical strings as the same customer** when they belong to different sources or tenants. Without a shared business key, you must define a namespace, a verified mapping table, or a stable canonical ID before building a unified dimension.

### A Type 1 dimension does not mean "only one field"

A `dim_customer` table may include name, segment, sales region, categorical age band, and other labels. Type 1 describes **how attributes are updated**, not the number of fields or how keys are assigned. Attributes on the same row can even follow **different SCD policies**, but mixing Type 1 and Type 2 requires explicit rules rather than overwriting fields indiscriminately.

## 3. The most important impact: historical facts get re-grouped

Consider this order data:

- On 2026-01-15, customer `CUS-42` belongs to segment `STANDARD` and places an order worth 2,000,000 VND.
- On 2026-03-01, CRM moves the customer to `VIP`.
- The dimension is updated using **SCD Type 1**, replacing `segment = 'STANDARD'` with `segment = 'VIP'`, keeping `customer_sk = 1087`.
- January's fact row remains an order of 2,000,000 VND, with neither amount nor key changed.

Data at the two points in time:

| Table/row | Before update | After Type 1 update |
| --- | --- | --- |
| `dim_customer(1087)` | `segment = STANDARD` | `segment = VIP` |
| January `fact_order_line` | `customer_sk = 1087`, `net_minor = 2,000,000` | Unchanged |
| January report **JOIN current dimension** | 2,000,000 in STANDARD group | 2,000,000 in VIP group |

Key takeaway:

**Historical transaction amounts do not change on their own, but how historical transactions are categorized can change.**

This is not necessarily a bug. If the business asks "**What is the total historical sales of customers who are currently in the VIP group?**", Type 1 can be right. If it asks "**In January, how much sales did the VIP group at the time of sale generate?**", Type 1 alone **cannot recover** the overwritten STANDARD segment.

### Two SQL questions with different semantics

**Question A: customer's current segment when viewing historical sales**

~~~sql
SELECT date_trunc('month', f.ordered_at) AS order_month,
       c.segment AS current_segment,
       f.currency,
       SUM(f.net_minor) AS booked_net_minor
FROM fact_order_line f
JOIN dim_customer c
  ON c.tenant_id = f.tenant_id
 AND c.customer_sk = f.customer_sk
GROUP BY date_trunc('month', f.ordered_at),
         c.segment, f.currency;
~~~

This is an appropriate Type 1 analysis if the report title emphasizes **current segment**, not "segment at sale."

**Question B: exact segment at the time of the transaction**

This cannot be answered reliably from a single Type 1 row if historical values are not kept elsewhere. It requires **SCD Type 2**, a segment attribute frozen by policy on the fact, or a historical source with sufficient validity time to reconstruct it. Never assign the current segment to history and label it "at time of sale."

## 4. When should and shouldn't Type 1 be used?

### Cases where it is usually appropriate

| Attribute/event | Why Type 1 can make sense | Condition to verify |
| --- | --- | --- |
| Fixing typos in display names | All reports should show the right name. | Old name is not needed as a historical analytical attribute. |
| Standardizing region spelling | `HCMC` and `Ho Chi Minh City` are the same region by approved definition. | Do not conflate two distinct regions; maintain a canonical mapping table. |
| Fixing misentered product category descriptions | All reporting periods should use the canonical label. | This is a **data fix**, not a category change over time. |
| Backfilling missing attributes from a trusted source | Dimension row transitions from `UNKNOWN` to confirmed values. | Prior value was missing data, not a historical state to preserve. |
| Updating UI labels without affecting historical calculations | Queries need current metadata. | Overwriting does not break the explanation of past transactions. |

### Cases where Type 1 is usually insufficient

| Need | Why Type 1 alone falls short | Better alternative |
| --- | --- | --- |
| Customer segment **at order time** | Old value is overwritten when segment changes. | SCD2 or store segment snapshot at a valid fact grain. |
| Contract price effective by date | Overwriting prices makes invoice history hard to explain. | Price version / valid-time table, or price locked on the contract fact. |
| Tracking who changed an attribute and when | Type 1 does not keep before/after values. | Audit log, retained CDC, events, or history table. |
| Reconciling payments and refunds | This is a **business fact**, not a dimension label. | Ledger/movement fact with transaction ID and confirmation timestamp. |
| Retroactive adjustments with two timelines | Need to know what the system previously knew and when facts took effect. | Bitemporal/version history or suitable temporal model. |
| Analyzing state transition flows | Need state history, not just the final state. | Transaction fact/event timeline or suitable SCD. |

**Selection rule:** use Type 1 when **the new value should replace the old value for every read**. Use SCD2 or another history pattern when "the old value that was true at a past point in time" still holds analytical value.

Not every attribute change has one fixed choice. For instance, `customer_segment` might be handled as Type 1 in a "current cohort" dashboard, yet require Type 2 in a promotion policy report as of sale time. Both requirements must be documented as two distinct definitions, not hidden behind one shared column name.

## 5. Relational Type 1 table design with explicit keys and constraints

The following PostgreSQL example assumes **the canonical CRM is the single authoritative source** for `display_name`, `segment`, and `region_code`. `customer_bk` is stable and unique within each tenant. The source system provides an integer `source_revision` that strictly increases whenever a new record version is emitted for the same customer.

~~~sql
CREATE TABLE dim_customer (
    customer_sk       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id         UUID NOT NULL,
    customer_bk       VARCHAR(100) NOT NULL,
    display_name      TEXT NOT NULL,
    segment           VARCHAR(30) NOT NULL,
    region_code       VARCHAR(20),
    is_inferred       BOOLEAN NOT NULL DEFAULT FALSE,
    source_revision   BIGINT NOT NULL CHECK (source_revision >= 0),
    source_updated_at TIMESTAMPTZ,
    first_loaded_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_applied_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    attributes_changed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, customer_bk),
    UNIQUE (tenant_id, customer_sk),
    CHECK (btrim(display_name) <> '')
);

CREATE INDEX ix_dim_customer_segment_region
    ON dim_customer (tenant_id, segment, region_code);

CREATE TABLE fact_order_line (
    tenant_id       UUID NOT NULL,
    order_id        VARCHAR(100) NOT NULL,
    line_id         VARCHAR(100) NOT NULL,
    customer_sk     BIGINT NOT NULL,
    ordered_at      TIMESTAMPTZ NOT NULL,
    net_minor       BIGINT NOT NULL CHECK (net_minor >= 0),
    currency        CHAR(3) NOT NULL,
    PRIMARY KEY (tenant_id, order_id, line_id),
    FOREIGN KEY (tenant_id, customer_sk)
        REFERENCES dim_customer (tenant_id, customer_sk)
);

CREATE INDEX ix_fact_order_line_customer_time
    ON fact_order_line (tenant_id, customer_sk, ordered_at);
~~~

**Physical design explanation:**

1. `customer_sk` is the table-wide SK; `UNIQUE(tenant_id, customer_bk)` enforces **one row per business key** at the declared grain. If multiple sources do not yet share a canonical BK, the key space must be expanded.
2. The additional `UNIQUE(tenant_id, customer_sk)` constraint lets the composite foreign key from the fact verify both **tenant and SK**, rather than merely checking that the SK exists in some arbitrary tenant.
3. `display_name` and `segment` are Type 1 attributes, without `valid_from/valid_to` for storing multiple versions. The `attributes_changed_at` column only shows **when the dimension content last changed**, without retaining prior values.
4. `source_revision` protects against updates from stale source records, **only when the source system guarantees reliable per-business-key ordering**. It is neither an SCD2 version nor an SK.
5. `is_inferred` indicates a placeholder row created to satisfy the FK when a fact arrives before customer details; when full data arrives, we **enrich that exact SK**.
6. `fact_order_line` has a grain of one item line in an order. `net_minor` here is the line amount under an agreed booking policy, not automatically synonymous with recognized revenue or actual cash flow.
7. The dimension index on `tenant_id, segment, region_code` is a hint for filtering queries; never assume all indexes are beneficial. Columnar warehouses use clustering/partitioning and scan strategies that differ from OLTP PostgreSQL.

**Identity note:** if the source can reuse `customer_bk` for another person, a one-row-per-BK design is unsafe. The identity contract must be fixed (e.g., adding a namespace or durable key), rather than using Type 1 to overwrite two different people into one.

## 6. Distinguishing timestamps in a Type 1 table

A dimension row often carries several time metadata columns that should not be treated as synonymous:

| Field | Meaning | Does it create attribute history? |
| --- | --- | --- |
| `source_updated_at` | Update timestamp supplied by the source; may suffer clock skew or arrive late. | No. |
| `first_loaded_at` | When the dimension first learned about the business key. | No. |
| `last_applied_at` | Most recent time a newer source version was applied per contract. | No. |
| `attributes_changed_at` | Most recent time Type 1 attribute values actually changed in the dimension. | No. |
| `ordered_at` in fact | Business timestamp of the order. | Belongs to the fact; never replaced by dimension update time. |

Even with all these timestamps, a Type 1 table still **cannot answer** "before the last edit, what value did the attribute have?". Answering that requires a history table, event log, audit log, or SCD2.

A source system without reliable revisions can use a **committed CDC/transaction log position** or another consistent ordering mechanism. Never blindly compare `source_updated_at` across two independent sources and assume the larger timestamp is authoritative truth.

## 7. ETL/ELT load workflow: normalization, key resolution, overwrite

A Type 1 pipeline can be structured into these steps:

~~~mermaid
flowchart TD
    A["Committed CRM snapshot / CDC"] --> B["Staging: schema, namespace, revision"]
    B --> C["Quality checks and dedup"]
    C --> D["Determine single latest valid version per BK"]
    D --> E{"Does BK already exist in dim_customer?"}
    E -->|"No"| F["INSERT new dimension row + SK"]
    E -->|"Yes, newer revision"| G["UPDATE attributes on same SK"]
    E -->|"Yes, older revision / retry"| H["Skip or reconcile conflict"]
    F --> I["Verify grain, version, reconciliation"]
    G --> I
    H --> I
~~~

### Step 1: the source must have a contract

You must know whether incoming records are:

- **Full-state record/snapshot:** includes all updatable attributes, where NULL means "current value is unknown."
- **Partial change/patch:** contains only changed fields; **absent** fields do not mean "set to NULL."
- **CDC/event stream:** data carries ordering and transaction/record identifiers, and may arrive multiple times or out of order at consumers.

The following SQL snippet **is strictly for cleaned full-state records already narrowed down to one valid row per business key**. If the input is a patch, merge it with source state per policy before running; do not confuse missing fields with NULL.

### Step 2: create clean staging, one row per BK

~~~sql
-- Temporary table populated by the pipeline before the upsert step.
-- Example applies only to a single canonical CRM source, revision >= 1.
CREATE TEMP TABLE stg_customer_clean (
    tenant_id         UUID NOT NULL,
    customer_bk       VARCHAR(100) NOT NULL,
    display_name      TEXT NOT NULL,
    segment           VARCHAR(30) NOT NULL,
    region_code       VARCHAR(20),
    source_revision   BIGINT NOT NULL CHECK (source_revision >= 1),
    source_updated_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, customer_bk)
) ON COMMIT DROP;
~~~

**Execution note:** A temporary table with `ON COMMIT DROP` must be created, populated, conflict-checked, and used for the upsert **within the same transaction and the same connection**. If `CREATE TEMP TABLE` runs standalone with autocommit enabled after each statement, the table may be dropped immediately once creation completes. For multi-step or multi-connection pipelines, use a persistent staging table keyed by `batch_id` with its own cleanup policy.

The **one row per BK** invariant comes from a principled latest-version selection step, such as a CDC cursor or contracted `source_revision`. Do not pick arbitrarily by `MAX(ingested_at)` if messages arrive out of order. If the same BK and same revision have different payloads, that is a **data conflict** to quarantine/investigate, not a tie to break randomly.

### Step 3: detect same-revision conflicts

Before writing, compare staging data against loaded rows:

~~~sql
SELECT s.tenant_id, s.customer_bk, s.source_revision
FROM stg_customer_clean s
JOIN dim_customer d
  ON d.tenant_id = s.tenant_id
 AND d.customer_bk = s.customer_bk
WHERE s.source_revision = d.source_revision
  AND (
       ROW(s.display_name, s.segment, s.region_code)
       IS DISTINCT FROM
       ROW(d.display_name, d.segment, d.region_code)
  );
~~~

If the query returns rows, **halt or route to an error stream** according to policy. If two workers run concurrently, a separate check outside the transaction **does not replace** concurrency coordination; restrict to one writer per key/batch, or keep the check and upsert inside a coordinated transaction/ingestion stream.

### Step 4: INSERT or UPDATE while keeping SK unchanged

~~~sql
INSERT INTO dim_customer (
    tenant_id, customer_bk, display_name,
    segment, region_code, source_revision,
    source_updated_at, is_inferred
)
SELECT
    tenant_id, customer_bk, display_name,
    segment, region_code, source_revision,
    source_updated_at, FALSE
FROM stg_customer_clean
ON CONFLICT (tenant_id, customer_bk)
DO UPDATE SET
    attributes_changed_at =
        CASE
            WHEN dim_customer.is_inferred
              OR ROW(
                    dim_customer.display_name,
                    dim_customer.segment,
                    dim_customer.region_code
                 ) IS DISTINCT FROM ROW(
                    EXCLUDED.display_name,
                    EXCLUDED.segment,
                    EXCLUDED.region_code
                 )
            THEN now()
            ELSE dim_customer.attributes_changed_at
        END,
    display_name = EXCLUDED.display_name,
    segment = EXCLUDED.segment,
    region_code = EXCLUDED.region_code,
    source_revision = EXCLUDED.source_revision,
    source_updated_at = EXCLUDED.source_updated_at,
    is_inferred = FALSE,
    last_applied_at = now()
WHERE dim_customer.source_revision < EXCLUDED.source_revision;
~~~

**Why does this upsert express Type 1 semantics?**

- The `(tenant_id, customer_bk)` pair is unique, locating the exact existing row.
- `UPDATE` modifies attributes on the **same row**, without inserting a new SCD2 row and **without reissuing `customer_sk`**.
- The condition `source_revision < EXCLUDED.source_revision` prevents **same-revision retries** and **late stale messages** from overwriting a newer version.
- `ROW(...) IS DISTINCT FROM ROW(...)` compares nullable fields cleanly, avoiding surprises from `<>` with NULL.
- `attributes_changed_at` updates only when attributes actually differ (or an inferred placeholder is completed); `last_applied_at` updates whenever a higher revision is accepted, even if display values did not change.
- The example avoids `COALESCE(EXCLUDED.region_code, dim_customer.region_code)`: with a **full-state record**, NULL may intentionally clear or indicate an unknown region. Using COALESCE would prevent a new NULL from overwriting the old value, producing stale data.

**Limitation:** `source_revision` is only comparable within a single defined source version sequence. If CRM resets revisions, merges profiles, or two systems update the same field, a new policy for identity, source precedence, and ordering is required; the SQL above does not resolve those conflicts on its own.

### Step 5: commit and record load outcomes

Log load metadata, insert/update/skip/conflict counts, and source checkpoints. If checkpoints and target data live in the same DB, update them **in the same transaction** where appropriate. If the source resides in another system, design checkpointing/retries so committed data is neither skipped nor left half-processed.

A revision-idempotent upsert can be retried after failure without inflating dimension row counts or changing SKs. Never assume that because a batch "ran," every row in it succeeded if partial errors occurred earlier.

## 8. Late-arriving records, out-of-order delivery, and retroactive corrections

### When an older update arrives later

Consider three full-state records for `CUS-42`:

| Arrival order at warehouse | source_revision | segment | Type 1 handling |
| ---: | ---: | --- | --- |
| First | 7 | STANDARD | Recorded. |
| Second | 9 | VIP | Updated on same SK. |
| Third | 8 | PREMIUM | **Ignored** because revision is lower than 9. |
| Fourth | 9 | VIP | Duplicate retry, no change. |

If only ingestion time were used, revision 8 would overwrite `VIP` with `PREMIUM`, rolling the dimension back to an obsolete state. Therefore, compare **committed source order**, not ingestion time.

### When historical data was entered erroneously and fixed retroactively

For example, management confirms that January's `STANDARD` segment was entered by mistake and should have been `VIP` from the start. Type 1 can overwrite it to `VIP`, and historical reports use the corrected value under a **restatement policy**.

This differs from a customer **actually upgrading in March**, where reports want "customer was STANDARD in January, VIP from March," for which SCD2 or valid-time history fits better.

The difference is not in the SQL syntax: both payloads may carry `segment=VIP`. It lies in **business meaning**:

- **Correction:** the old value is acknowledged to have been wrong.
- **Change over time:** the old value was once true; the new value only became true from a certain point.

You cannot choose Type 1 or Type 2 properly without distinguishing these two cases.

## 9. Facts arriving before dimensions: inferred members and unknown members

In multi-source systems, orders can arrive before customer details. Fact foreign keys still require a dimension row.

Two common approaches exist:

**Inferred member:** create a placeholder dimension row **for that exact business key**, with `is_inferred = TRUE` and a durable SK. When CRM sends full details, the Type 1 upsert updates that row and sets `is_inferred = FALSE`, **keeping the SK intact**. This works well when the BK itself is already verified as reliable.

**Unknown member:** bind the fact to a special "unknown" key when the business key is not yet known or an inferred row cannot be established. Later, you may need to **backfill facts** to the real SK once the source provides evidence. An unknown member should never be treated as a real customer; separate unknowns by tenant/reason code under policy if needed.

Example inferred state:

| customer_sk | customer_bk | display_name | segment | is_inferred |
| ---: | --- | --- | --- | --- |
| 1087 | CUS-42 | UNKNOWN | UNKNOWN | true |
| 1087 (after enrichment) | CUS-42 | John Nguyen | VIP | false |

The two rows in the table are simply **two observation points of the same row**, not two concurrent rows.

### Notes on creating inferred members

The sample schema reserves `source_revision = 0` for inferred rows; valid CRM sources use revisions 1 and above. When an early event arrives, creating an inferred member must use the **same unique business key** and proper transactions/concurrency control to avoid creating two rows for `CUS-42`.

Only infer **the existence of a confirmed BK**. Never guess a real name, region, or segment from an incomplete source. The `UNKNOWN` label is a technical contract value, not a business fact.

## 10. Type 1, Type 2, Type 0, and hybrid models

Comparison table:

| Type | When an attribute changes | Ability to answer history | Use case |
| --- | --- | --- | --- |
| **Type 0** | Keep the attribute's original value. | Knows the originally fixed value; does not capture later changes. | Locked attributes prohibited from overwriting by policy. |
| **Type 1** | Overwrite on the current row. | Only current value exists in that dimension. | Label fixes, error corrections, intentional historical re-grouping. |
| **Type 2** | Insert a new dimension version with a new SK or clearly identified valid version. | Query attributes effective at a business point in time if historized properly. | Segment at sale, sales region at transaction time. |
| **Hybrid Type 1 + Type 2** | Some attributes overwrite, others create versions. | Differs per attribute policy. | Misspelled name fixed via Type 1; time-varying segment tracked via Type 2. |

In typical SCD2, multiple rows per BK carry `valid_from`, `valid_to`, or version numbers. Facts reference the **SK of the dimension version at transaction time**. With pure Type 1, **one BK has one SK**, and all related facts point to the same row being overwritten.

### Combining Type 1 and Type 2 in one dimension

Suppose `dim_customer` historizes `segment` with Type 2 while `display_name` is Type 1. When fixing the name from `Jhon Nguyen` to `John Nguyen`, determine:

- If **the corrected name should replace all historical copies**, update the name column across **all SCD2 rows sharing that BK**, not just the current row. Segment version SKs remain unchanged.
- If the old name had meaning at a past point in time and must remain queryable, name **should not** be a Type 1 attribute in this design.
- Retroactive corrections to segment may require splitting/adjusting Type 2 intervals and reconciling fact keys; do not turn those into Type 1 overwrites, as doing so erases valuable history.

This is why you should define **attribute-level SCD policies** with owners and definitions, rather than merely labeling "customer table uses SCD2" and updating columns ad hoc.

## 11. What should NOT be overwritten with Type 1?

Some data looks like an "attribute" but is actually a finalized fact of a transaction:

- **Unit price at sale:** a product's current catalog price can be Type 1 for display, but the agreed price on an order line must be preserved on the fact/contract per policy.
- **Delivery address of a completed order:** a customer changing their contact address does not change where a past order was physically delivered. If reports need historical delivery location, preserve actual delivery facts.
- **Segment determining discount tier on purchase date:** if discounts depended on the segment at that time, overwriting with the current segment makes it impossible to explain the applied policy.
- **Captured/refunded amount:** must come from source-confirmed transactions; a refund request is not equivalent to a completed refund.
- **Timestamps of occurred events:** overwriting `last_status` on a dimension does not replace a fact/event table for event lifecycles.

You can display "current customer details" alongside old documents, provided column/report names clearly state those are current details rather than implying past documents originally carried those values.

### Changing a business key is not an ordinary Type 1 attribute edit

If CRM changes a customer ID or discovers two codes must merge, an identity reconciliation, mapping, and lineage workflow is required. Directly updating `customer_bk` can break staging/dedup linkage, and merging two SKs may require re-evaluating fact references. Do not casually use `ON CONFLICT DO UPDATE SET customer_bk = ...` to solve master-data merges.

## 12. Testing and reconciling Type 1 dimension tables

A pipeline running without errors does not mean the data is right. Test these invariants:

| Category | Check | Expected outcome |
| --- | --- | --- |
| **Grain** | Each `(tenant_id, customer_bk)` has one dimension row. | No duplicate BKs. |
| **Stable key** | Changing `display_name` or `segment` does not alter `customer_sk`. | Fact references remain valid. |
| **Newer source wins** | Revision 9 arrives before revision 8. | Revision 8 does not overwrite 9. |
| **Idempotency** | Re-running the same batch/revision. | No added rows, no unexpected attribute changes. |
| **Conflict** | Two differing payloads share BK and revision. | Halt/route to error queue, never pick randomly. |
| **NULL** | Full-state record sends `region_code = NULL`. | Old value is cleared if that is valid semantics. |
| **Partial payload** | Patch omits `region_code`. | Does not silently set region to NULL. |
| **Inferred member** | Fact arrives before dim, then CRM updates. | Initial SK persists and gets enriched. |
| **Reporting impact** | Segment changes via Type 1. | Historical reports use current segment per contract; never mislabeled as as-of. |
| **Tenant** | Fact in tenant A does not reference dim in tenant B. | Composite FK/isolation checks block errors. |

### Verification SQL queries

~~~sql
-- Duplicate business keys: must return 0 rows.
SELECT tenant_id, customer_bk, COUNT(*) AS n
FROM dim_customer
GROUP BY tenant_id, customer_bk
HAVING COUNT(*) > 1;

-- Remaining inferred members: tracks completeness.
SELECT tenant_id, COUNT(*) AS inferred_count
FROM dim_customer
WHERE is_inferred = TRUE
GROUP BY tenant_id;

-- Check facts missing dimension match (FK usually blocks this on local tables).
SELECT f.tenant_id, f.order_id, f.line_id
FROM fact_order_line f
LEFT JOIN dim_customer d
  ON d.tenant_id = f.tenant_id
 AND d.customer_sk = f.customer_sk
WHERE d.customer_sk IS NULL;

-- Customer distribution by current segment.
SELECT tenant_id, segment, COUNT(*) AS customer_count
FROM dim_customer
WHERE is_inferred = FALSE
GROUP BY tenant_id, segment;
~~~

`UNIQUE` and FKs in the sample DDL prevent many errors at write time; check queries remain valuable when data is imported via special paths, served from separate read stores, or monitored for quality ratios.

### Reconciling against the source

For a confirmed complete set of business keys:

1. Count valid BKs in CRM versus matching BKs in the dimension per tenant.
2. Compare display values, segments, regions, and `source_revision` of the latest records.
3. Classify discrepancies: source record not yet received, quarantined record, stale revision, mapping bug, or differing rules.
4. Track latency from source commit until dimension application.
5. Test with NULLs, Unicode characters, identifier format shifts, duplicate messages, and failure recovery cases.

Reconciliation is only valid under **the same source scope and consistency snapshot**. Never compare a 10:00 source snapshot against a warehouse updated through 10:30 and declare an error because row counts differ.

## 13. Query and update optimization: don't turn a simple problem into overload

One advantage of Type 1 is that dimension row counts stay relatively compact: one BK has one row rather than potentially dozens of SCD2 versions. For "current customer by segment" queries, JOINs and filters can be straightforward.

Yet Type 1 is not always cheap:

- **Large-scale upserts** still generate heavy data page writes, WAL, locks, and index maintenance.
- **Indexes on frequently changing attributes** like `segment` or `region_code` must be maintained on overwrites, which can be costly.
- **Full hourly snapshots resent by sources** can rewrite millions of rows if unchanged records are not filtered out.
- **Historical re-grouping** can invalidate caches, materialized aggregates, or dashboards storing precomputed figures.
- **BK changes/identity merges** are not solved by running a simple upsert.

Distinguish **new source transactions** from **rebuilding derived tables**. With Type 1, updating a name/segment in the dim changes direct JOIN results immediately; however, a materialized `monthly_sales_by_segment` aggregate built from the old segment does not update itself. You must design invalidation/rebuilds or recompute affected partitions/periods, then reconcile.

### Which indexes are necessary?

- `UNIQUE(tenant_id, customer_bk)` is mandatory at this grain to prevent duplicates.
- `PRIMARY KEY(customer_sk)` and composite referenced keys protect fact linkage.
- An index on `(tenant_id, segment, region_code)` can help if queries frequently filter customer cohorts per tenant.
- A fact index on `(tenant_id, customer_sk, ordered_at)` fits per-customer analysis or selective JOINs; neither replaces workload testing.
- In columnar/MPP systems, partitioning/clustering/encoding strategies differ from PostgreSQL; do not copy every row-store index verbatim.

Measure P95/P99 query latency by workload, rows actually updated with differing attributes, bloat, lock contention, backfill time, and aggregate refresh cost. Doing less work on history in Type 1 **does not mean** operations need no monitoring.

## 14. Schema evolution, lineage, and privacy

### Adding fields to a dimension

Suppose `loyalty_tier` needs to be added. First determine: is this **current classification** or **tier at the time a promotion occurred**? If only current is needed, a Type 1 attribute can be added. If last year's discount must be explained, store history in the proper place rather than adding only a current column.

Execute migrations in a controlled manner: add the column with a meaningful missing-value representation, backfill from authoritative sources, update ETL tests, adjust the semantic layer, and verify affected reports. Do not blindly assign `UNKNOWN` = `STANDARD` just to eliminate NULLs or satisfy sample queries.

### Lineage: overwriting does not mean losing all provenance

A Type 1 table can keep `source_revision`, load metadata, and **source references** to trace where current data originated. If auditing before/after values is required, store them in a **separate history store with dedicated access controls and retention**; Type 1 itself is not a full history archive.

For multi-source integration, add rules for **per-attribute authoritative source**, source precedence, sync timing, cross-checks, and conflict-free identification. The same customer may have a CRM name and an invoice name serving different purposes; avoid applying a blanket "latest record wins" rule across all fields.

### Privacy

- Dimensions may hold names, addresses, sensitive segments, or personally identifiable data. Only ingest data genuinely needed for analytics.
- Overwriting a name in the dimension **does not delete the old name** from staging, backups, exports, audits, caches, aggregate tables, or downstream warehouses.
- Apply read-access policies per tenant/group, retention limits, and deletion/anonymization procedures when properly requested.
- Do not treat hashed surrogate or business keys as **absolute anonymization**: they can still link back to an individual via mapping tables and facts.
- If data must be deleted/anonymized, do not merely update `display_name = 'REDACTED'` in one table and declare completion. Assess all copies and recovery boundaries.

**Architectural takeaway:** Type 1 serves **current interpretation** of facts, but does not by itself govern retention, security, or system-wide history erasure.

## 15. Common mistakes when implementing Type 1

| Mistake | Consequence | Remedy |
| --- | --- | --- |
| Inserting a new dimension row on every name edit | Becomes non-Type-1 versioning; facts may point to wrong SK. | UPDATE on the same business key/SK. |
| Changing `customer_sk` when `segment` changes | Old facts are orphaned or require massive updates. | Keep SK immutable for Type 1 updates. |
| Overwriting all attributes because "the table is Type 1" | Loses segment/address/cost history that was needed. | Assign SCD policies per attribute. |
| Using `MAX(ingested_at)` to pick the winner | Late messages overwrite newer data. | Use source versions/cursors with an ordering contract. |
| Treating missing patch fields as NULL | Accidentally wipes valid attributes. | Distinguish missing fields from explicit NULLs. |
| Using `COALESCE` to retain all old values when source sends NULL | Cannot intentionally clear expired values. | Base NULL rules on full-state vs. patch contract. |
| Ignoring differing payloads with the same revision | Conflicting data is silently dropped. | Detect and quarantine conflicts. |
| Editing business keys like ordinary labels | Mislinks two people or breaks fact joins. | Use master-data mapping and identity verification. |
| Calling a current-segment report "at time of purchase" | Misrepresents history. | Use Type 2/historical facts or clear metric naming. |
| Overwriting fact sale prices with new catalog prices | Alters historical transaction records. | Transaction facts store price locked at booking. |
| Forgetting inferred members when facts arrive early | Orphaned facts or lingering unknowns. | Use inferred/unknown members with a backfill process. |
| Using Type 1 while claiming full auditability | No before/after values remain in the dimension. | Maintain separate audit/history if required. |
| Updating the dimension without refreshing aggregates | Materialized dashboards still reflect old groups. | Trigger invalidation/recompute and reconcile KPIs. |

## 16. Practice exercise: Type 1 loading and explaining report shifts

**Context:** a course platform has `fact_enrollment` (one row per enrollment) and `dim_student` (one row per student). CRM provides student data by `student_bk` and increasing `source_revision`. Analysts want enrollment counts by the student's **current region**. Operations also needs to know which region a student belonged to **at enrollment time**.

Dataset:

| Record | student_bk | source_revision | region | Notes |
| --- | --- | ---: | --- | --- |
| A | ST-07 | 12 | NORTH | Present in dimension at start of period. |
| B | ST-07 | 14 | SOUTH | Subsequent CRM update. |
| C | ST-07 | 13 | CENTRAL | Message arriving late after B. |
| D | ST-07 | 14 | SOUTH | Callback/duplicate load. |
| E | ST-09 | 5 | NULL | CRM confirms region is unknown. |

Before B, student `ST-07` has `student_sk = 305` and 20 enrollments from last month.

### Tasks

1. **Choose grain and keys:** define `(tenant_id, student_bk)` and `student_sk`, how facts reference the dimension, and explain why no new SK is issued when B loads.
2. **Define Type 1 behavior:** after B, C, and D, what should ST-07's region be, and why?
3. **Compute dashboard impact:** which group do last month's 20 enrollments move to when queried by current region? Do fact values change?
4. **Distinguish historical questions:** to answer region at enrollment time, propose SCD2 or a validly defined attribute-at-event; explain why Type 1 is insufficient.
5. **DDL:** write the `dim_student` table with unique tenant/BK, surrogate key, `source_revision`, and metadata; create the fact with a tenant-protecting FK.
6. **Upsert:** write `INSERT ... ON CONFLICT DO UPDATE` conditioned on a newer revision; use `IS DISTINCT FROM` to detect when attributes truly change.
7. **NULL handling:** the source sends a full-state record for ST-09 with NULL region. Why shouldn't `COALESCE` retain an old region? What changes if this were a partial patch?
8. **Faulty data:** two payloads share `student_bk + source_revision` but differ in region; propose handling instead of picking by arrival time.
9. **Early-arriving fact:** an enrollment arrives before ST-11's profile; choose between inferred or unknown member and specify the backfill policy.
10. **Materialized reports:** `monthly_enrollments_by_region` holds old totals. Choose how to refresh and reconcile after the dimension changes regions.
11. **Testing:** list checks for retries, concurrency, uniqueness, SK stability, NULL region, tenant isolation, and KPI totals.
12. **ADR:** select which student attributes use Type 1 and which require Type 2, justified by concrete business questions.

### Self-assessment checklist

| Criterion | Correct outcome |
| --- | --- |
| **One row/BK** | One `(tenant_id, student_bk)` has one Type 1 dimension row. |
| **Stable SK** | Old and new facts continue referencing the same `student_sk` after updates. |
| **Prevent rollback updates** | Revision 13 arriving after 14 must not overwrite 14. |
| **Prevent duplicate processing** | Repeated revision 14 causes no changes and adds no rows. |
| **NULL semantics** | Distinguishes full-state NULL from missing patch fields. |
| **Historical reporting** | Recognizes Type 1 re-categorizes old facts by current attributes. |
| **Preserved history** | Maintains a history/Type 2 source if as-of queries are needed. |
| **Reconciliation** | Avoids fact multiplication on JOINs; reconciles materialized aggregates. |
| **Governance** | Enforces lineage, deletion policy, conflict handling, and tenant access control. |

**Conclusion:** SCD Type 1 is the choice to **overwrite descriptive attributes of an entity on the same dimension row**, keeping the surrogate key stable and updating historical JOINs to reflect current groupings. It fits when old data should be **replaced**, and does not fit when old values remain **true and meaningful at a prior point in time**. For a resilient model, start from reporting questions, define grain/keys, establish source and concurrency rules, and then design ETL, indexes, tests, and supplemental history to the exact level required.
