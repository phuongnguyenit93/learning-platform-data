# Slowly Changing Dimension Type 3: Retaining Partial Prior Values

## Learning Objectives

After this lesson, you will be able to:

- Explain **Slowly Changing Dimension Type 3 (SCD Type 3)**: keeping the **current** value and one or more **previous** values in columns of the **same dimension row**.
- State the **grain**, business key, surrogate key, and change rules for a Type 3 dimension table.
- Distinguish **"the value immediately preceding the most recent change"** from **"the value actually effective at transaction time"**; understand why SCD3 does not replace the full history of SCD2.
- Choose SCD Type 1, 2, 3, or a hybrid design based on the exact analytical question, rather than choosing merely for simpler queries.
- Design an SCD3 load workflow with true-change checks, source versions, idempotency, and atomic updates in PostgreSQL.
- Write queries comparing **two groupings** of the same set of facts—by current region and by immediately previous region—while handling cases that have never changed regions.
- Handle history limits, late events, consecutive changes, multiple attributes, report republication, and correctness testing.

In **DATABASE_DATA_MODELING**, turning business requirements into dimension tables is not just creating a code column and a name column. Organizations often restructure sales territories, customer segments, or ownership; reports must answer: **is data categorized by today's organization or by a previous classification?** SCD Type 3 is a technique that retains **partial** prior information to compare these views without multiplying rows for the same entity. In return, it **cannot store full history**. Understanding that trade-off is the core of this lesson in the **Dimension Tables** chapter.

## 1. Scenario: a store changes management region

A retail chain has 200 stores. Each store has a stable code, yet is assigned to a **sales management region** that can change when the organization restructures. For example:

- Before 2026-10-15, store **S-101** belonged to the **North** region.
- Starting 2026-10-15, store S-101 was transferred to the **Central** region.
- Executive management wants to see sales for the same period by **current management region**, as well as **how figures would be distributed if the regional assignment prior to the latest restructuring were still used**.

These are two very different questions:

1. **Comparing distributions:** take the same set of transactions, group once by *current* region, and once by *immediately previous* region. This fits SCD3 well.
2. **Reconstructing exact history on sale date:** for every transaction on May 1, October 20, or December 1, determine the region **actually effective on that date**. This is a temporal history problem; if a store changes regions multiple times, standard SCD3 is **insufficient**.

Therefore, stating "we need to see the old region" is not yet specific enough to decide. You must clarify: **does "old" mean the value immediately before current, or any value at a past point in time?**

## 2. SCD Type 3 structure: one row, multiple value columns

**SCD3** stores selected versions of an attribute **horizontally** within one record, for example:

| store_key | store_id | store_name | current_region | previous_region | region_changed_at |
| ---: | --- | --- | --- | --- | --- |
| 501 | S-101 | Store A | Central | North | 2026-10-15 00:00+07 |
| 502 | S-102 | Store B | South | NULL | NULL |

**Grain:** one row represents **one store belonging to one tenant**. Region changes do not create new dimension rows.

**Keys:**

- **store_id** is the store's stable identifier in the operational source, potentially needing **tenant_id**.
- **store_key** is the *surrogate key* used to join with fact tables.
- **current_region** describes the current classification as of when the dimension row was loaded.
- **previous_region** stores the value immediately before the **most recent properly processed region change**.
- **region_changed_at** records the latest region change timestamp provided by the authoritative source; it is not the fact creation timestamp.

Transitioning **North → Central** happens **on the same row**:

~~~text
Before change:
store_key = 501
current_region = North
previous_region = NULL

After receiving region transfer:
store_key = 501                (unchanged)
current_region = Central       (new value)
previous_region = North        (immediately previous value)
region_changed_at = 2026-10-15
~~~

If a store has never changed regions within the tracked history window, **previous_region = NULL** means "no prior value recorded," not automatically that the store previously belonged to an UNKNOWN region.

### Why is it called "Type 3"?

In the standard SCD classification:

- **Type 1:** overwrites old values without storing history for that attribute in the dimension.
- **Type 2:** inserts a new **version row** for the same entity; rows carry validity intervals.
- **Type 3:** retains a **finite number of historical columns** on the **same row**: current/previous, or original/current, depending on the published policy.

Type 3 is not strictly restricted to **one** previous column; you can keep original_region, previous_region, and current_region if requirements only need those values. Still, it retains **a fixed number of checkpoints**, not unbounded history.

## 3. Multiple sequential changes and lost data

Suppose store S-101 goes through:

~~~mermaid
flowchart LR
    A["01/01<br/>current = North<br/>previous = NULL"]
    B["10/15<br/>current = Central<br/>previous = North"]
    C["11/20<br/>current = South<br/>previous = Central"]
    A -->|"Region change 1"| B
    B -->|"Region change 2"| C
~~~

| Observation point | current_region | previous_region | What can be read? |
| --- | --- | --- | --- |
| After initial load | North | NULL | Only knows North is the current region |
| After 10/15 change | Central | North | Knows North was immediately before Central |
| After 11/20 change | South | Central | Knows Central was immediately before South; **North is lost from this row** |

If it changes again **South → North**, SCD3 becomes current=North, previous=South. Two columns cannot tell that the store also belonged to North **before moving to Central**.

**Decisive limitation:** standard SCD3 cannot answer "which region did S-101 belong to in May, October, and November?" after multiple changes, unless an **independent history source** exists for reconciliation. A single region_changed_at column for the **latest change** does not recover earlier overwritten changes.

Even if the business expects only one change per period, the interpretation of "previous/current region" must be documented in the data contract, because one unexpected extra change can erase the prior comparison baseline.

### Two common policy variants

| Storage pattern | Meaning | When appropriate |
| --- | --- | --- |
| current + **previous** | Value immediately before the **latest change** | Comparing the new state against the immediate prior step, accepting a sliding history window |
| current + **original** | Value at creation or at a locked baseline | Comparing every change against the original classification / baseline organization |

Do not name original_region as previous_region if it does not rotate on every change. These two column patterns look similar in SQL yet carry **different business semantics**. Both can be used together when the contract explicitly specifies how each column is maintained.

## 4. SCD3 does not automatically turn past data into "as-of" data

A frequent cause of reporting errors is confusing two operations:

**Re-grouping by current or prior classification:**

> "Take all September sales, calculate them once by each store's **current** region and once by the region **immediately before its latest transfer**."

**Grouping by actual state at transaction time:**

> "Take September sales and group them by the region each store **belonged to during September**, even if it has moved two or three regions since."

SCD3 handles the first operation well. The second generally requires:

- **SCD2** with multiple version rows and validity intervals;
- a region snapshot captured directly on the fact at transaction time, once recognition definitions are confirmed;
- a region-assignment history table detailed enough for temporal joins;
- or an explicitly designed hybrid.

**Do not use previous_region as a default substitute for "region_at_sale".** If a store changed regions twice, previous_region is the region before the **last** change, not the region valid when all historical transactions occurred.

### Comparison table of slowly changing types

| Question/characteristic | Type 1 | Type 2 | Type 3 |
| --- | --- | --- | --- |
| Current value in dimension? | Yes | In the current version row | Yes |
| Retains immediately prior value? | Not in that dimension | Yes, via historical rows | Yes, if previous column is designed |
| Stores full change chain? | No | Yes, within loaded/retained history scope | No, only selected checkpoints |
| Does change create a new row? | No | Yes | No |
| Fact surrogate key for an entity across versions? | Usually stable | Differs by version | Usually stable |
| Reports exact attribute at fact time? | Not sufficient on its own | Yes, if facts bind to the right valid version | Not sufficient after multiple changes |
| Compares **same fact set** under current vs. prior classification? | Lacks prior region | Requires logic to pick versions then group | Directly via two columns |
| Cost/caveats | Loses history | More rows, temporal mapping, and late events | Overwrites older history, previous/baseline definition |

No type is "universally best" for every case. Choosing a type depends on the historical questions you must preserve, data volume, and business contracts.

## 5. From requirements to dimension grain and ownership

Before creating tables, determine:

1. **What entity is changing?** In this example it is *store*, not a sales transaction.
2. **Which attribute needs versioning?** Sales management region; not every Store field needs Type 3.
3. **What does "previous" mean?** Value before every change, value before the latest major reorganization, or region at a baseline restructuring date?
4. **Where is the authoritative source?** The store/regional organization management system, not a manually edited mart table.
5. **What is the uniqueness scope?** Usually (tenant_id, store_id).
6. **How complete is the change stream?** Does the pipeline observe every region change or only a nightly latest snapshot?
7. **How do facts reference the dimension?** Is there a stable surrogate key so millions of facts need not be updated when regions change?
8. **Must reports reproduce a past run?** If so, pure SCD3 overwrites may be insufficient to freeze report outputs.

The output can be a **data contract**:

| Attribute | Illustrative convention |
| --- | --- |
| Dimension | Store |
| Grain | One row per (tenantId, storeId) |
| Fact key | (tenantId, storeKey) |
| Type 3 attributes | currentRegion, previousRegion |
| Meaning of previous | Value immediately before the **latest region change processed in proper source order** |
| Type 1 field | storeName may be fixed in place without rotating previousRegion |
| Change timestamp | regionChangedAt from the authoritative source, in UTC |
| Source version | sourceVersion monotonically increasing within Store scope |
| Data lacking history | previousRegion = NULL |
| Errors to handle | Out-of-order events, skipped versions, duplicate IDs, backdated corrections |
| Report type | Compares current vs. prior region classification; **does not** claim full as-of querying |

## 6. PostgreSQL schema: one row per store

The following PostgreSQL schema is an illustration to clarify semantics and constraints; a columnar warehouse may use MERGE or another pipeline pattern instead of row-by-row UPDATEs.

~~~sql
CREATE SCHEMA IF NOT EXISTS mart;

CREATE TABLE mart.dim_store_scd3 (
    tenant_id UUID NOT NULL,
    store_key BIGINT GENERATED ALWAYS AS IDENTITY,
    store_id UUID NOT NULL,
    store_name TEXT NOT NULL,
    current_region TEXT NOT NULL,
    previous_region TEXT,
    region_changed_at TIMESTAMPTZ,
    source_version BIGINT NOT NULL CHECK (source_version >= 0),
    last_source_event_id UUID,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, store_key),
    UNIQUE (tenant_id, store_id),
    CHECK (length(trim(store_name)) > 0),
    CHECK (length(trim(current_region)) > 0),
    CHECK (
        previous_region IS NULL
        OR length(trim(previous_region)) > 0
    )
);

CREATE INDEX dim_store_current_region
    ON mart.dim_store_scd3 (tenant_id, current_region);

CREATE INDEX dim_store_previous_region
    ON mart.dim_store_scd3 (tenant_id, previous_region)
    WHERE previous_region IS NOT NULL;
~~~

**Reading the DDL by intent:**

- **UNIQUE (tenant_id, store_id)** enforces the grain of one row/store/tenant. It prevents inserting a new row on every region change like Type 2.
- **store_key** does not change when current_region changes; facts can keep referencing that key.
- **previous_region NULL** at initialization indicates the prior value is unknown. We do not force current_region to differ from previous_region via CHECK, because policies/sources may have exceptions (e.g., rotating back) and hard constraints can break migrations; what must be protected is the **update rule**.
- **source_version** helps prevent older records from overwriting newer ones when versions are issued consistently by the source; a single number by itself does not prove all intermediate versions were received.
- **region_changed_at** is a business milestone, not loaded_at. If the source only sends arrival time rather than effective date, document that limitation.
- The two region indexes illustrate common grouping and filtering queries. On specialized analytical warehouses, sorting, statistics, and columnar storage may make indexing unnecessary or different; do not blindly create both.

If regions have **official codes** while display names can change, store a stable region_id/region_code and join to an appropriate region dimension instead of using free-text names as identity. This example uses TEXT for readability, not because display names are reliable business keys.

### Fact table linked to the Type 3 dimension

~~~sql
CREATE TABLE mart.fact_paid_order_line (
    tenant_id UUID NOT NULL,
    order_id UUID NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    store_key BIGINT NOT NULL,
    paid_at TIMESTAMPTZ NOT NULL,
    gross_sales_vnd BIGINT NOT NULL CHECK (gross_sales_vnd >= 0),
    load_batch_id UUID NOT NULL,
    PRIMARY KEY (tenant_id, order_id, line_no),
    FOREIGN KEY (tenant_id, store_key)
        REFERENCES mart.dim_store_scd3 (tenant_id, store_key)
);

CREATE INDEX paid_line_by_store_date
    ON mart.fact_paid_order_line (tenant_id, store_key, paid_at);
~~~

**Fact grain:** one row is one OrderLine recorded as sold once the order is paid in full under the lesson's assumption. One Order has multiple lines, so COUNT(*) is the number of sales lines, not orders. If the business allows split payments, choose a different grain or expand keys to match reality instead of relying on this assumption.

When a region changes, facts do not need store_key updated; the same facts can be aggregated by current_region or previous_region via JOIN to that dimension row. **The strength of SCD3 is also its limitation:** when the dimension is updated, groupings of **old facts** change.

## 7. Initial load, region transfer, and value rotation rules

### 7.1. Initial load: do not fabricate a prior region

The source reports S-101 is currently in North with sourceVersion=1. Without reliable history, the new row has:

~~~sql
-- :tenant_id, :store_id, ... are parameters from the validated pipeline.
INSERT INTO mart.dim_store_scd3 (
    tenant_id, store_id, store_name,
    current_region, previous_region,
    region_changed_at, source_version, last_source_event_id
) VALUES (
    :tenant_id, :store_id, :store_name,
    :initial_region, NULL,
    NULL, :initial_source_version, :source_event_id
)
ON CONFLICT (tenant_id, store_id) DO NOTHING
RETURNING store_key;
~~~

On conflict, the pipeline must inspect the existing row and version, never treating ON CONFLICT DO NOTHING as proof that source payloads match. When two workers load the same store concurrently, use consistent locking/UPSERT and version checks.

When starting tracking mid-lifecycle and the source only supplies the current value, previous_region NULL means **unknown**, not that the store has never changed regions.

### 7.2. A valid change: rotating current to previous

Suppose a source event arrives: version 2, newRegion=Central, effectiveAt=2026-10-15T00:00:00+07. Use **one atomic UPDATE**:

~~~sql
UPDATE mart.dim_store_scd3 AS d
SET previous_region = CASE
        WHEN d.current_region IS DISTINCT FROM :new_region
        THEN d.current_region
        ELSE d.previous_region
    END,
    region_changed_at = CASE
        WHEN d.current_region IS DISTINCT FROM :new_region
        THEN :effective_at
        ELSE d.region_changed_at
    END,
    current_region = :new_region,
    source_version = :source_version,
    last_source_event_id = :source_event_id,
    updated_at = CURRENT_TIMESTAMP
WHERE d.tenant_id = :tenant_id
  AND d.store_id = :store_id
  AND d.source_version < :source_version
RETURNING
    d.store_key,
    d.current_region,
    d.previous_region,
    d.region_changed_at,
    d.source_version;
~~~

**Why use IS DISTINCT FROM?** It returns a clean TRUE/FALSE even when values may be NULL. In this table current_region is NOT NULL; the operator still expresses "rotate only when the value actually changes."

In PostgreSQL, expressions in SET read **the row values before the UPDATE**. Thus previous_region receives the old current_region while current_region receives :new_region. Never split this into two separate UPDATEs where another session could interleave between them.

**When the value does not change:** an event updating storeName while keeping Central must not rotate previous_region to Central. The CASE above rotates only when the region genuinely differs. Still, the pipeline must ensure the event provides a **valid current region value**, never passing NULL just because a name-update payload omitted the region field.

**When an event is old or repeated:** WHERE source_version < :source_version stops an already-applied version from overwriting a newer current_region. However, if an event with the same version carries a different payload, that is a **data quality conflict** to detect in the event log/inbox, never ignored silently.

### 7.3. Do not lose intermediate changes

If the source emits:

~~~text
Version 5: North
Version 6: Central
Version 7: South
~~~

but the pipeline receives version 7 **before** version 6 and immediately updates the version 5 row, the result becomes **current=South, previous=North**. Version 6 is then skipped. The result is **not the "true previous"**, because Central immediately preceded South.

To preserve the **true immediately preceding value**, you need one of:

- ensure all region-change events are processed in exact order **per store**;
- detect sequence gaps and **buffer/replay** before updating;
- obtain from the source a **full snapshot containing the accurate previous value** or an authoritative change history;
- or rebuild the dimension from a complete change log ordered by business sequence.

If the pipeline only receives **nightly latest snapshots** without guaranteeing visibility of every change, explicitly name/document previous_region as **the value prior to the latest observed change**, rather than claiming it is always the true business previous region.

A sourceVersion that increments on **every Store edit**, not only regions, may have intermediate versions that only change names. When detecting gaps, identify which event types are missing; never assume every skipped version was a region change.

## 8. Queries comparing previous and current regions

Suppose in October two stores record sales:

| store_id | October sales | current_region | previous_region |
| --- | ---: | --- | --- |
| S-101 | 120,000,000 VND | Central | North |
| S-102 | 80,000,000 VND | South | NULL |

The fact set is unchanged. Yet grouping produces:

| Grouping | North | Central | South | Total |
| --- | ---: | ---: | ---: | ---: |
| By **current region** | 0 | 120M | 80M | 200M |
| By **immediately prior classification** (keeping unchanged stores) | 120M | 0 | 80M | 200M |

This is **re-allocating one set of sales** under two organizational structures, not actual revenue growth/decline or a month-over-month comparison.

### 8.1. Aggregating by current region

~~~sql
SELECT d.current_region AS region,
       SUM(f.gross_sales_vnd) AS sales_vnd
FROM mart.fact_paid_order_line AS f
JOIN mart.dim_store_scd3 AS d
  ON d.tenant_id = f.tenant_id
 AND d.store_key = f.store_key
WHERE f.tenant_id = :tenant_id
  AND f.paid_at >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND f.paid_at <  TIMESTAMPTZ '2026-11-01 00:00:00+07'
GROUP BY d.current_region
ORDER BY region;
~~~

### 8.2. Aggregating by the region immediately before the latest change

If business rules specify that **stores without a previous_region remain in their current group**, you can use COALESCE:

~~~sql
SELECT COALESCE(d.previous_region, d.current_region)
           AS baseline_region,
       SUM(f.gross_sales_vnd) AS sales_vnd
FROM mart.fact_paid_order_line AS f
JOIN mart.dim_store_scd3 AS d
  ON d.tenant_id = f.tenant_id
 AND d.store_key = f.store_key
WHERE f.tenant_id = :tenant_id
  AND f.paid_at >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND f.paid_at <  TIMESTAMPTZ '2026-11-01 00:00:00+07'
GROUP BY COALESCE(d.previous_region, d.current_region)
ORDER BY baseline_region;
~~~

**COALESCE is a reporting decision, not a historical fact.** A NULL previous_region can mean unchanged, unobserved, or missing history. If "unknown" must be a separate group, do not use COALESCE as above; display "No prior region" and include a data-quality column.

### 8.3. Comparing both options in a single summary

Avoid joining the fact table to itself and multiplying rows. First aggregate sales **once per store**, then produce two views:

~~~sql
WITH sales_by_store AS (
    SELECT tenant_id, store_key,
           SUM(gross_sales_vnd) AS sales_vnd
    FROM mart.fact_paid_order_line
    WHERE tenant_id = :tenant_id
      AND paid_at >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
      AND paid_at <  TIMESTAMPTZ '2026-11-01 00:00:00+07'
    GROUP BY tenant_id, store_key
),
regional_views AS (
    SELECT 'CURRENT' AS classification,
           d.current_region AS region,
           s.sales_vnd
    FROM sales_by_store AS s
    JOIN mart.dim_store_scd3 AS d
      ON d.tenant_id = s.tenant_id
     AND d.store_key = s.store_key

    UNION ALL

    SELECT 'PREVIOUS_OR_CURRENT' AS classification,
           COALESCE(d.previous_region, d.current_region) AS region,
           s.sales_vnd
    FROM sales_by_store AS s
    JOIN mart.dim_store_scd3 AS d
      ON d.tenant_id = s.tenant_id
     AND d.store_key = s.store_key
)
SELECT classification, region, SUM(sales_vnd) AS sales_vnd
FROM regional_views
GROUP BY classification, region
ORDER BY classification, region;
~~~

The two totals across classification **should match** if using the same fact set and each fact matches exactly one dimension row; this is a useful consistency check. However, matching totals **do not prove regions were assigned accurately**.

### Report execution-time issues

If S-101 transfers **Central → South** in November and a user re-runs October's query, current_region=South and previous_region=Central. October's report by **"region prior to current"** now yields a different result than the report run back in October. That is expected SCD3 behavior, yet it may fail requirements to **reproduce published historical reports**.

If you must keep figures "as published on October 31," freeze a dimension snapshot or classification results per report version, or use full history. Simply printing a run date on a report cannot restore an overwritten previous_region.

## 9. Avoiding three critical KPI pitfalls

### 9.1. "Previous region" does not mean "region on transaction date"

SCD3 current/previous cannot determine all validity intervals. Never apply November's previous_region to February transactions and label it "February transaction region."

### 9.2. Reclassification is not growth

Suppose October's total is 200 million and September's total is 180 million. Grouping 120 million from Central back to North via the previous column only **changes how the same revenue is categorized**; it does not turn the total into 320 million and does not by itself show regional growth. When comparing period-over-period growth, ensure **the same regional definition** across both periods and consistent attribute-change policies.

### 9.3. Do not confuse fact grain with dimension grain

fact_paid_order_line is **one sales line**; dim_store_scd3 is **one store**. Joining on store_key is many-facts-to-one-dimension. If someone accidentally creates multiple dimension rows for the same store_key/business key, sales double-count. Conversely, COUNT(*) after the JOIN remains **number of sales lines**, not number of stores or orders.

When comparing multi-currency sales, establish a currency conversion policy before summing; this lesson uses VND for consistency.

## 10. Type 3 with multiple independently changing attributes

A Store can change both **management region** and **store manager**. These two attributes need not change together. You can use:

| Column | Meaning |
| --- | --- |
| current_region / previous_region | Latest region / region immediately before the region change |
| region_changed_at | Latest region change timestamp |
| current_manager_id / previous_manager_id | Latest manager / manager immediately before the manager change |
| manager_changed_at | Latest manager change timestamp |

Processing rules:

- A **StoreRegionChanged** event rotates only current_region → previous_region; it does not alter previous_manager_id.
- A **StoreManagerChanged** event rotates only the manager columns.
- An event updating **store display name** can be handled as Type 1 on store_name without rotating either Type 3 column pair.
- If both fields change in the same event per business policy, update both atomically while preserving per-attribute timestamps/provenance per contract.

A shared Store-level sourceVersion can order updates for the whole entity. If different systems have independent authority and sequences for region vs. manager, a pipeline-generated global version **does not guarantee** ordering across both sources. Model ownership and version/sequence per field or per authoritative source.

### Can you keep more than one old value?

You can design:

~~~text
current_region
previous_region
previous_2_region
~~~

but this is **finite history bounded by column count**. Every subsequent change must rotate in exact order, and you must weigh schema-evolution costs if more checkpoints are requested later. A requirement to **"query every change over 5 years"** is a strong signal to use a history table or Type 2 instead of adding previous_3, previous_4...

If the requirement is a fixed comparison between "pre-2025 reorganization structure" and "current structure," a baseline_2025_region column can be clearer than a sliding previous_region.

## 11. Late events, corrections, and effective time

A **late-arriving** event is not necessarily an **older business change**. For example, the source sends a correction: on October 15 the true region should have been **South** instead of **Central**, though the correction is only sent on November 20.

Two types of ordering must be distinguished:

- **Source version/commit order:** which value is the latest record accepted by the source.
- **Business effective time:** when the change takes effect, which may be corrected retroactively.

SCD3 with current/previous and one latest timestamp is **insufficient to reconstruct all changes across effective time**. If *as-of* updates are needed after corrections, define an effective-history table, fact restatement rules, or proper Type 2. Never edit previous_region to "guess" missing historical chains.

### Safer pipeline design

~~~mermaid
flowchart LR
    S["Store Management Source"] --> C["CDC / domain events"]
    C --> R["Raw change log<br/>eventId, sourceVersion, eventTime"]
    R --> V["Validate + deduplicate<br/>check gaps and ordering"]
    V --> P["SCD3 projection<br/>current + previous"]
    P --> BI["Current / previous grouping reports"]
    R -.->|"When replay/correction needed"| V
~~~

A processing chain should:

1. Receive entity IDs with **tenant namespace** and verify permissions/source.
2. Validate eventType, schema, version, effectiveAt, and region values.
3. Deduplicate by eventId per **source**; handle conflicts if matching ID/version carries differing content.
4. Check whether all region changes were observed in order. On gaps or reordering, wait, fetch history, or flag previous as incomplete.
5. Compare **actual region values** before rotating; never rotate on a name-edit event.
6. Update current/previous/timestamp/version **atomically** and log load metadata.
7. Check store counts, valid regions, grouping metrics, and post-load completeness.
8. Publish reports along with **data-as-of / dimension-as-of** or snapshot version.

The raw change log can be stored separately in the pipeline for replay, yet the log's existence **does not mean** the Type 3 dimension table supports temporal queries. When warehouse historical joins are needed, build the corresponding historical model from the log.

## 12. Atomicity and contention when multiple workers update the same store

In PostgreSQL, two UPDATEs targeting the same row contend for the row lock. Under READ COMMITTED, when one statement waits for another transaction and resumes, its condition is re-evaluated against the appropriate row version. WHERE source_version < :source_version prevents an older version from overwriting a newer value.

However, distinguish:

- **Never overwrite current with an older record:** can be guarded by a version condition.
- **previous is always the source's true immediately preceding value:** requires a complete/ordered change stream or a source payload providing it directly.

These two properties are not equivalent. A single-row UPDATE that is safe in atomicity can still yield a **semantically wrong previous** if an intermediate change was skipped.

In warehouses supporting batch MERGE, gather all changes for a store within a batch, sort by **authoritative source order**, apply the rotation rules sequentially, and write the final row. Never pick the "last by receivedAt" if receivedAt is merely pipeline ingestion time.

**Idempotency on batch rerun:** replaying the same sourceVersion must never rotate previous a second time. When retrying a batch after the transaction committed but the response was lost, check stored versions and state. If a duplicate differs in payload, route it to investigation rather than silently ignoring it.

## 13. When to choose Type 2, Type 3, or a hybrid design?

Use the reporting questions to decide:

| Requirement | Suitable candidate | Why |
| --- | --- | --- |
| Only need latest store name; old names don't matter | Type 1 for store_name | Simple overwrite, no history needed |
| Need to view the same sales set by **current region** and **immediately prior region** | Type 3 for region | Two direct views on the same store_key |
| Need store region on **every sale date** over three years | Type 2 or valid-time history table | Multiple versions and validity intervals |
| Need to keep "original opening-day region" and "today's region" | Type 3 with original_region + current_region | Fixed baseline instead of sliding previous |
| Need both "as-of sale" and "grouped by current region" | Type 2 combined with current region lookup, or hybrid | Two inherently different views |
| Only two locked org points, need fixed comparison report | Baseline Type 3 with locked period version, or separate snapshot | Reduces risk of previous rotating unexpectedly |
| Hundreds of changes per day, need per-change replay/audit | Event history/Type 2, optionally adding Type 3 as a projection | Pure Type 3 loses detail |

### How Type 2 differs from Type 3

With Type 2, a Store changing North → Central → South can be modeled as:

| store_key | store_id | region | valid_from | valid_to |
| ---: | --- | --- | --- | --- |
| 501 | S-101 | North | 2026-01-01 | 2026-10-15 |
| 803 | S-101 | Central | 2026-10-15 | 2026-11-20 |
| 950 | S-101 | South | 2026-11-20 | NULL |

Validity intervals use the **[valid_from, valid_to)** convention — inclusive start, exclusive end. A fact on Oct 1 needing the region **at sale time** links to version 501; Nov 1 to 803; Dec 1 to 950. A single-row Type 3 cannot represent this on its own after multiple changes.

With Type 3, the single S-101 row keeps **store_key=501, current=South, previous=Central**. All facts sharing store_key can be grouped by those two columns when reports run, regardless of sale date.

Do not conclude Type 2 is always better simply because it keeps more history. It increases row counts, requires exact validity mapping and late-arriving handling, and complicates queries. Type 3 is a deliberate choice when **only a finite number of checkpoints are needed**.

### Hybrids do not automatically solve everything

A hybrid combining Type 1/2/3 is sometimes called **Type 6** in literature, keeping current values alongside historical Type 2 rows. Yet a label does not replace a contract: specify which fields overwrite, which create rows, which version facts bind to, and how corrections update history.

If most reports only compare two groupings, you can build a **Type 3 projection** from a Type 2 historical source. Then Type 3 serves convenient queries while the history source preserves reconstructability when new changes occur.

## 14. Transitioning from Type 1 to Type 3

An organization initially stores only current_region in dim_store. Later comes a requirement to compare against the prior region. Migration workflow:

1. Verify the **meaning of previous** with report owners: most recent, baseline, or a specific period?
2. Add nullable previous_region, region_changed_at, and version/source metadata if missing.
3. **Never copy current_region into previous_region** and call it history. If no past source exists, leave it NULL and disclose completeness.
4. If an audit log, historical CDC, or reliable region-assignment table exists, backfill previous accurately by rule.
5. Update the pipeline to rotate fields only on **actual region changes**, handling ordering and idempotency.
6. Update the semantic layer with clear names: Current Sales Region, Previous Observed Sales Region, or Baseline 2025 Region.
7. Test existing reports to confirm current_region and store_key did not shift unexpectedly.
8. Attach report versions/cutoffs if comparisons must be reproducible after subsequent changes.

During backfill, NULL previous_region may exist on part of the dataset and mean **unknown**. Prevent dashboards from treating all NULLs as "never changed region" if historical coverage is incomplete.

### Permissions and access rules

Analytical dimensions can aggregate data across multiple tenants. All JOINs, UPDATEs, and queries must preserve tenant_id and corresponding access controls. A store ID does not grant permission to read sales. If the previous attribute is a manager or customer segment, apply HR/personal-data safeguards, data minimization, and retention policies.

Keeping only one prior value in a dimension does not exempt it from reconciliation and access governance. Analytical groupings can still leak sensitive information if groups are tiny or users query outside their authorized scope.

## 15. Edge-case testing

| Scenario | Expected outcome |
| --- | --- |
| Initial load of S-101 with North | current=North, previous=NULL, one row per store |
| Region North → Central, higher sourceVersion | current=Central, previous=North, store_key unchanged |
| Redelivery of the just-applied event | Does not rotate previous again |
| Event changes storeName only, region still Central | previous=North, region_changed_at unchanged |
| Central → South afterward | current=South, previous=Central; recognize North is no longer in the row |
| South version arrives before Central version | Cannot claim exact previous if Central was skipped |
| Same sourceVersion with differing payload | Raise conflict alert, investigate source |
| Region changed then reverted back to original | Following real change order, current/previous reflect the latest two steps |
| Two tenants have colliding store_id | Never merge data across tenants |
| Region renamed while assignment unchanged | Do not rotate region for pure label edits per policy |
| October report rerun after November region change | Recognize results may reclassify; verify freeze/as-of requirements |
| Fact JOIN on store_key | Each fact matches at most one dimension row of the same tenant |
| Incomplete history source during migration | previous NULL/quality flag; do not invent fake values |

### Suggested unit/integration tests for rotation

Given initial state:

~~~text
store = S-101
version = 10
current = North
previous = NULL

Apply version 11, newRegion=Central:
  current=Central, previous=North, version=11

Apply version 11 again:
  no change

Apply version 12, newRegion=Central:
  current=Central, previous=North, version=12

Apply version 13, newRegion=South:
  current=South, previous=Central, version=13
~~~

Tests should verify not just that an UPDATE succeeds, but also **previous semantics**, source ordering, business key uniqueness, zero fact multiplication, and report output behavior across execution times.

## 16. Exercise: customer segments before and after a campaign

**Context:** A business runs a Bronze, Silver, Gold loyalty program. Each Customer has a stable customerId, current segment status, and tier-change date. Marketing wants to view **purchase value of the same customer cohort** by **current tier** and by **immediately previous tier**. Within one quarter, a customer may upgrade two tiers; some customers have never changed.

**Questions:**

1. Propose grain, business/surrogate keys, and columns for dim_customer SCD3. Use clear names current_tier and previous_tier.
2. For customer C-01 going Bronze → Silver → Gold, fill in current_tier and previous_tier after each change. After the final change, can C-01's entire tier history be queried from this dimension table?
3. Propose how to group fact_purchase by current_tier and previous_tier. Handle previous_tier=NULL for unchanged customers under two distinct policies: **keep current tier** and **unknown group**.
4. Marketing requests "revenue **at each point in time** while customers were Bronze/Silver/Gold over 3 years." Is Type 3 still suitable? Explain what Type 2, history, or snapshot is required.
5. If the Gold upgrade event arrives before the Silver upgrade event, what wrong previous_tier can an UPDATE taking the highest sourceVersion produce? Propose how to handle it.
6. Suppose a customer is downgraded Gold → Silver after the quarter-end report was published. How will the Type 3 report change if re-run? How can published numbers be frozen?
7. Design at least four tests covering tier changes, retries, unrelated attribute edits, and out-of-order events.

### Solution guide

- **dim_customer grain:** one row per (tenantId, customerId). Keep customer_key stable for fact_purchase references.
- After C-01 starts Bronze: current=Bronze, previous=NULL; after Silver upgrade: current=Silver, previous=Bronze; after Gold upgrade: current=Gold, previous=Silver. Bronze is no longer present in standard Type 3 columns.
- Querying by previous_tier requires a NULL policy. If using COALESCE(previous_tier, current_tier), label it "prior or unchanged classification" rather than "historical tier on purchase date."
- The "at each point in time over 3 years" requirement needs **effective-time history**, typically Type 2 or a transaction-time fact snapshot. Single-row Type 3 is insufficient across multiple upgrades/downgrades.
- When Gold arrives before Silver, previous recorded from the known state may become Bronze instead of Silver. Processing solely by higher version does not guarantee true previous; use replay/enforced ordering or a source snapshot carrying accurate previous.
- Reporting by current/previous is a **reclassification comparison**, not transaction value by tier at sale time. If locked quarterly reports must be reproduced, store a separate dimension/baseline version or published output.

## 17. Checklist and conclusion

- Which entity is **one row** of the dimension, and does the unique key include tenant/namespace?
- Does previous mean **immediately preceding**, **original value**, or a **fixed baseline**? Do column names state this accurately?
- Does previous rotate only when **tracked attributes actually change**, rather than on retries or unrelated field edits?
- Does the pipeline handle eventId, sourceVersion, gaps/out-of-order events, and corrections per authoritative source?
- Does a change update current, previous, timestamp, and version **atomically**?
- Can NULL previous mean either unchanged or unknown history; does reporting policy distinguish them?
- Do facts retain stable surrogate keys and join each fact to **one** dimension row without multiplying sales?
- Are **reclassification comparisons of the same fact set** distinguished from **attributes at fact time**?
- When current/previous change, old-period reports can shift; are locked snapshots needed for reproducibility?
- If **all changes** are needed, have you chosen Type 2 or a history table instead of cramming into a previous column?
- Do other attributes like display name, manager, and region have distinct Type 1/2/3 policies and clear ownership?
- Has the design been tested against double changes, reversals, duplicate events, late events, missing history, and multiple tenants?

**Conclusion:** **SCD Type 3** models **selected partial history** directly on **one dimension row**. Current/previous columns make it easy to compare the same set of transactions under two classifications while keeping fact foreign keys stable. In return, each rotation can overwrite older values and reclassify previously run reports. Therefore, use Type 3 only when the business genuinely needs **a finite set of perspectives**, define previous/baseline explicitly, protect update ordering, and choose Type 2 or separate history whenever requirements demand querying **accurately at every historical point in time**. That turns reporting needs into a transparent, verifiable, and evolvable data model.
