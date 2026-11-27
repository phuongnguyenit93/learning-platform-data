# Slowly Changing Dimension Type 2: Creating Versions and Validity Intervals

## Learning Objectives

After this lesson, you will be able to:

- Explain **Slowly Changing Dimension Type 2 (SCD Type 2)** as a way to **preserve dimension attribute history using multiple row versions**, rather than overwriting old values.
- Distinguish between **business/natural keys**, **surrogate keys**, **version numbers**, and **effective time intervals**.
- Design non-overlapping **[effective_from, effective_to)** intervals, at most one current version, and rules for boundary timestamps.
- Write dimension changes in PostgreSQL with concurrency control; join facts to the **dimension version valid at event time**.
- Identify issues involving **late-arriving events, retroactive effectivity, entity deletion, reconciliation, schema changes**, and the difference between *valid time* and *recorded time*.
- Choose SCD Type 1, Type 2, Type 3, or a hybrid approach based on analytical questions; avoid creating versions automatically for every attribute.

This lesson belongs to the **Dimension Tables** chapter of **DATABASE_DATA_MODELING**. When translating business requirements into a clear data model, you must determine not only entities, relationships, keys, and indexes, but also **the point in time at which an attribute's value was true**. This is especially critical when joining fact tables with dimensions in an analytics warehouse, regardless of whether the initial operational source is relational, document-based, or another system.

## 1. The problem: a customer changes segment, past reports must preserve meaning

A sales system has customer **C-42**. During 2026:

| Business period | Customer segment |
| --- | --- |
| From 2026-01-01 until before 2026-06-15 | **BRONZE** |
| From 2026-06-15 until before 2026-09-01 | **SILVER** |
| From 2026-09-01 onward | **GOLD** |

There are three orders:

| Order | Confirmation time | Segment needed for "at purchase time" reporting |
| --- | --- | --- |
| **O-101** | 2026-05-31 | BRONZE |
| **O-102** | 2026-07-01 | SILVER |
| **O-103** | 2026-10-05 | GOLD |

If the **dim_customer** table has only one row per **customer_id** and always runs UPDATE **segment_code = 'GOLD'**, all earlier orders may be reclassified as GOLD when reports join on customer_id. That result might be right for **"Historical revenue by customer's current segment?"**, but **wrong** for **"Which segment did the customer belong to when purchasing?"**.

SCD Type 2 solves this by **keeping distinct dimension versions over time**. When a segment changes, the system **closes the validity of the old version** and **inserts a new version**, instead of overwriting historical attributes with an UPDATE.

> **SCD Type 2 does not freeze the customer entity: it preserves the history of attribute versions that reports need to look back on.**

## 2. Declare the dimension grain before creating tables

For SCD Type 2, the appropriate grain declaration is:

> **One row of dim_customer_version represents one analytical attribute version of one customer over a business validity interval.**

This means:

- One **customer_id** can correspond to **multiple dimension rows**.
- One **customer_sk** (surrogate key) identifies **one specific row version**, not the entire customer.
- Different versions of the same customer may carry the **same name** while differing in segment, region, or tracked attributes.
- Validity intervals across versions of the same customer **must not overlap** if the contract requires exactly one version at any point in time.
- The fact table must select the **version** matching the event's timestamp, rather than naively joining to the current record.

Illustration:

~~~text
Customer C-42 (stable natural key)
           |
           +-- customer_sk=1001 | BRONZE | [01/01, 06/15)
           |
           +-- customer_sk=1002 | SILVER | [06/15, 09/01)
           |
           +-- customer_sk=1003 | GOLD   | [09/01, +infinity)

Fact O-101 (05/31) --> 1001
Fact O-102 (07/01) --> 1002
Fact O-103 (10/05) --> 1003
~~~

Here **+infinity** denotes an open-ended effective interval with no end date yet. In the SQL below, we use **effective_to = NULL** to represent an unbounded upper bound, rather than using NULL to mean "missing data."

### 2.1. Business key, surrogate key, version: do not mix roles

| Component | Example | Role |
| --- | --- | --- |
| **tenant_id + customer_id** | (7, C-42) | Identifies **one customer** within the business scope |
| **customer_sk** | 1001, 1002, 1003 | Identifies **each dimension version row** |
| **version_no** | 1, 2, 3 | Sequential version number in the dimension, aiding checks/traceability |
| **source_revision** | 15, 21, 37 | Version in the source system; not necessarily equal to version_no |
| **effective_from** | 2026-06-15 00:00+07 | Time when this version begins business effectivity |
| **effective_to** | 2026-09-01 00:00+07 | Time when effectivity **ends**, exclusive upper bound |
| **recorded_at** | Timestamp when ETL received/stored | Technical metadata: when the warehouse learned of this version |

**Natural keys** must be stable, have a clear identification scope, and not be reused arbitrarily. In multi-tenant systems, **customer_id** alone may not be globally unique. **Surrogate keys** are technical keys for versions: if **customer_id** were used as a single-row primary key, multiple versions per customer could not exist.

**version_no** is not a time column: two versions must establish effectivity via time intervals and business rules. Do not use **MAX(version_no)** as a substitute for **as-of** lookups on an older order.

## 3. Choose SCD Type 2 for the analytical question, not merely because an attribute changes

Common strategies:

| Strategy | When an attribute changes | Suitable question | Trade-off |
| --- | --- | --- | --- |
| **Type 0** | Keep original value | Attribute is truly immutable by contract | Does not reflect later changes |
| **Type 1** | UPDATE overwrites existing row | Reclassify all history by current value; fix errors without history | Old values cannot be reconstructed from the dimension |
| **Type 2** | Close old row, INSERT new version | Analyze **by state at event time** | More rows/versions, complex load logic and JOINs |
| **Type 3** | Keep previous and current values in a few columns | Compare two defined points like previous/current | Does not retain an arbitrary full history chain |
| **Hybrid** | Choose policy per attribute | Fix errors while preserving history of critical attributes | Requires clear per-field contracts |

Examples:

- **customer_segment**: can use Type 2 if you want to know which group the customer belonged to on the purchase date.
- **Fixing a typo in province name**: can use Type 1 if this is merely correcting data entry, not a business territory change.
- **Current display name**: can use Type 1 if reports do not require name history.
- **Sales management region**: can use Type 2 when territory transfers affect historical accountability and revenue targets.
- **User requests deletion of personal data**: must obey retention/deletion policies; do not blindly create unbounded versions of sensitive data.

A **Type 2 dimension** does not have to create a new version when **any** column changes. Explicitly specify **tracked attributes** that trigger versions and **Type 1 attributes** that can be updated in place per policy. Updating a Type 1 field across all historical versions is an intentional choice to standardize/correct data, not a Type 2 refresh mechanism for a new business event.

## 4. Validity intervals: half-open convention [from, to)

A simple and verifiable contract:

~~~text
[effective_from, effective_to)
  - Valid at effective_from.
  - No longer valid at effective_to.
  - effective_to = NULL: end time unknown, open into the future.
~~~

For customer C-42:

| Version | effective_from | effective_to | Segment |
| --- | --- | --- | --- |
| v1 | 2026-01-01 00:00+07 | 2026-06-15 00:00+07 | BRONZE |
| v2 | 2026-06-15 00:00+07 | 2026-09-01 00:00+07 | SILVER |
| v3 | 2026-09-01 00:00+07 | NULL | GOLD |

An order occurring at **exactly 00:00 on 2026-06-15** belongs to **v2**, not v1. Using **BETWEEN start AND end** (inclusive on both bounds) could match both v1 and v2 on the boundary timestamp. Therefore, the as-of lookup predicate is:

~~~sql
WHERE effective_from <= :event_time
  AND (
      effective_to > :event_time
      OR effective_to IS NULL
  )
~~~

In PostgreSQL, you can use the range type **tstzrange(effective_from, effective_to, '[)')**, where a NULL upper bound means unbounded. Choose **TIMESTAMPTZ** when storing absolute instants and specify the business timezone when defining "effective from which date." When converting dates by local timezone, convert exact local day boundaries to timezone-aware timestamps; never assume every day in every timezone is always 24 hours.

### 4.1. Do not swap the meanings of time fields

- **valid/effective time:** when the business considers the segment to be in effect.
- **source updated/commit time:** when the source system recorded the change.
- **warehouse loaded/recorded time:** when the pipeline wrote data into the warehouse.
- **fact event time:** when the order was confirmed, paid, or delivered according to the fact's grain.

For instance, an administrator enters on June 20 that a segment changed **effective June 15**. If ETL uses June 20 as effective_from, revenue for June 15–19 is misclassified. Equally, you cannot blindly trust every user-supplied timestamp; enforce effective-date approval rules and retroactive edit governance.

**Standard Type 2 typically stores history along one valid-time axis.** If you must answer both "on June 18, what did the system believe?" and "later, what did we confirm was effective on June 18?", that is **bitemporal** and requires dedicated modeling rather than coming automatically from effective_from/effective_to.

## 5. PostgreSQL design: protecting versions and preventing overlapping intervals

This illustrates a customer dimension keyed by **(tenant_id, customer_id)**. An identity table lets us lock a customer when writing versions, even before the customer has their first version.

### 5.1. Customer identity table and dimension version table

~~~sql
CREATE TABLE dim_customer_identity (
    tenant_id BIGINT NOT NULL,
    customer_id TEXT NOT NULL,
    PRIMARY KEY (tenant_id, customer_id)
);

CREATE TABLE dim_customer_version (
    customer_sk BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    customer_id TEXT NOT NULL,
    version_no INTEGER NOT NULL CHECK (version_no >= 1),
    segment_code TEXT NOT NULL,
    region_code TEXT NOT NULL,
    effective_from TIMESTAMPTZ NOT NULL,
    effective_to TIMESTAMPTZ,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_dim_customer_identity
        FOREIGN KEY (tenant_id, customer_id)
        REFERENCES dim_customer_identity (tenant_id, customer_id),
    CONSTRAINT ck_customer_valid_period
        CHECK (
            effective_to IS NULL
            OR effective_to > effective_from
        ),
    CONSTRAINT uq_customer_version_number
        UNIQUE (tenant_id, customer_id, version_no),
    CONSTRAINT uq_customer_valid_start
        UNIQUE (tenant_id, customer_id, effective_from)
);

-- Each customer has at most one version open to the future.
CREATE UNIQUE INDEX ux_dim_customer_current
    ON dim_customer_version (tenant_id, customer_id)
    WHERE effective_to IS NULL;

CREATE INDEX ix_dim_customer_asof
    ON dim_customer_version
       (tenant_id, customer_id, effective_from DESC);
~~~

**Key explanation:**

- **customer_sk** is unique per version row, convenient for facts referencing a specific version.
- **(tenant_id, customer_id)** in the **identity** table identifies the business customer.
- **(tenant_id, customer_id, version_no)** prevents duplicate version numbers.
- **(tenant_id, customer_id, effective_from)** prevents duplicate start timestamps.
- The **unique partial index** prevents two concurrent versions from both having **effective_to IS NULL**.
- **CHECK** prevents empty or inverted ranges when an end timestamp exists.

However, there is a critical gap: the constraints above **do not automatically prevent two finite intervals from overlapping**. For example, v1 [01/01, 08/01) and v2 [06/01, 09/01) both have non-NULL effective_to values, so the UNIQUE constraints above do not reject them.

### 5.2. Exclusion constraint protecting time intervals

PostgreSQL can use a **GiST exclusion constraint** to forbid two validity intervals for the same customer from intersecting. In environments where the **btree_gist** extension is permitted:

~~~sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

ALTER TABLE dim_customer_version
ADD CONSTRAINT ex_customer_no_overlap
EXCLUDE USING gist (
    tenant_id WITH =,
    customer_id WITH =,
    (tstzrange(effective_from, effective_to, '[)')) WITH &&
);
~~~

Meaning: for the **same tenant_id and customer_id**, two **tstzrange** intervals must not **&&** (overlap). Adjacent intervals **[A,B)** and **[B,C)** remain valid. When **effective_to = NULL**, the upper bound is unbounded, so two current versions cannot coexist either.

**Operational note:** extensions require system privileges and approval; GiST/exclusion constraints add index and write overhead. In warehouses that do not support this constraint, the pipeline must check for overlaps, serialize writes by business key, and run reconciliation jobs. **Single-row CHECK constraints cannot prove that intervals across multiple rows do not overlap.**

Exclusion constraints prevent **overlaps**, but **do not force intervals to be contiguous**. If every moment from first appearance to present must have a version, you must check for **gaps**. A system may also intentionally allow gaps when a customer did not exist or was inactive; this should be documented in the contract.

## 6. Writing the initial version and subsequent changes

### 6.1. Adding the initial version

Example creating customer C-42 for tenant 7 at the start of the year:

~~~sql
BEGIN;

INSERT INTO dim_customer_identity (tenant_id, customer_id)
VALUES (7, 'C-42');

INSERT INTO dim_customer_version (
    tenant_id, customer_id, version_no,
    segment_code, region_code,
    effective_from, effective_to
)
VALUES (
    7, 'C-42', 1,
    'BRONZE', 'SOUTH',
    TIMESTAMPTZ '2026-01-01 00:00:00+07',
    NULL
);

COMMIT;
~~~

Having a **current** version does not imply all history existed before it. If the system only started collecting data on Jan 1, reports before that date may have **unknown customer segment**; do not backfill BRONZE into unverified historical gaps.

### 6.2. Transitioning BRONZE to SILVER in the same transaction

Suppose the next effective date is **June 15**, the change is validated, and the source confirmed it. To prevent two workers from simultaneously creating versions for one customer, write paths can **lock the customer's identity row** before closing/opening versions.

~~~sql
BEGIN;

-- All version write paths for a customer must obey this lock.
SELECT tenant_id, customer_id
FROM dim_customer_identity
WHERE tenant_id = 7 AND customer_id = 'C-42'
FOR UPDATE;

-- Before executing: validate source revision, effective date,
-- current version, and attribute changes per contract.
WITH closed AS (
    UPDATE dim_customer_version
    SET effective_to = TIMESTAMPTZ '2026-06-15 00:00:00+07'
    WHERE tenant_id = 7
      AND customer_id = 'C-42'
      AND effective_to IS NULL
      AND effective_from <
          TIMESTAMPTZ '2026-06-15 00:00:00+07'
      AND segment_code = 'BRONZE'
    RETURNING tenant_id, customer_id, version_no
)
INSERT INTO dim_customer_version (
    tenant_id, customer_id, version_no,
    segment_code, region_code,
    effective_from, effective_to
)
SELECT
    tenant_id, customer_id, version_no + 1,
    'SILVER', 'SOUTH',
    TIMESTAMPTZ '2026-06-15 00:00:00+07',
    NULL
FROM closed
RETURNING customer_sk, version_no;

-- Only COMMIT if INSERT returns exactly one version as expected.
COMMIT;
~~~

**Important:** this is an example of a **forward-moving transition**, not a general algorithm for all events. The application or stored procedure must:

1. Verify that the **identity lock** returned the right customer and enforce the same protocol across all writers; if it does not yet exist, create the identity and handle initialization races.
2. Verify the source record is newer or the event is authorized, tracked attributes actually changed, and **new effective_from > current effective_from**.
3. Verify that **INSERT ... RETURNING returns exactly one row** before committing; if it returns 0, **ROLLBACK/reconcile** instead of reporting success.
4. Handle deadlocks, constraint violations, retries, and duplicate events idempotently.
5. Do not use this procedure for **retroactive changes falling between already-closed versions** without applying a dedicated interval-splitting algorithm.

Doing **UPDATE + INSERT inside the same transaction** ensures no temporary gap state between closing the old version and creating the new one is exposed to concurrent readers under PostgreSQL's rules. Locking the identity serializes writers **following the same protocol** per customer; constraints remain the safety net against programming bugs.

For the transition from SILVER to GOLD, apply the same rule at **2026-09-01**, creating the next version. Afterward, C-42 has three rows as shown in section 1.

### 6.3. When tracked attributes don't change, should a version be created?

Suppose the source emits **CustomerUpdated** changing only the phone number — a field outside the analytical dimension. Creating a new version with identical segment/region bloats data and makes version numbers confusing.

Define **tracked columns** for Type 2: e.g., **segment_code** and **region_code**. The pipeline can compare normalized values or hash only the tracked fields. Note:

- Normalize **NULLs, letter case, whitespace, and region codes** according to business rules.
- Hashing is only a change-detection aid; if collision risk matters or exact correctness is required, compare raw values appropriately.
- Type 1 fields must take their own update path; never create versions because metadata like **loaded_at** changed.
- If an event has the same **source revision** but a different payload, treat it as a data conflict to investigate.

## 7. Joining facts to the dimension version at event time

Consider a sales fact with grain **one confirmed order** (a simplified example; line-item facts have their own grain). The table can reference the resolved version:

~~~sql
CREATE TABLE fact_order (
    order_id TEXT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    customer_id TEXT NOT NULL,
    customer_sk BIGINT NOT NULL
        REFERENCES dim_customer_version(customer_sk),
    confirmed_at TIMESTAMPTZ NOT NULL,
    order_amount NUMERIC(18, 2) NOT NULL,
    currency CHAR(3) NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_fact_order_customer_sk
    ON fact_order(customer_sk);
~~~

**customer_id** retains the natural ID for traceability; **customer_sk** binds the fact to **one dimension version**. When loading the fact, the pipeline must locate the version matching **confirmed_at**:

~~~sql
SELECT
    d.customer_sk,
    d.version_no,
    d.segment_code,
    d.region_code
FROM dim_customer_version AS d
WHERE d.tenant_id = $1
  AND d.customer_id = $2
  AND d.effective_from <= $3::TIMESTAMPTZ
  AND (
      d.effective_to > $3::TIMESTAMPTZ
      OR d.effective_to IS NULL
  );
~~~

**Query contract: return exactly one row** if history is complete and non-overlapping. Returning 0 means: fact arrived before dimension, missing history, wrong natural key/tenant, or timestamp out of range. Returning more than 1 means: dimension history overlaps. Never use **LIMIT 1** as a silent workaround.

Querying revenue by segment at purchase time:

~~~sql
SELECT
    d.segment_code,
    f.currency,
    COUNT(*) AS order_count,
    SUM(f.order_amount) AS booked_order_amount
FROM fact_order AS f
JOIN dim_customer_version AS d
    ON d.customer_sk = f.customer_sk
GROUP BY d.segment_code, f.currency
ORDER BY d.segment_code, f.currency;
~~~

This represents **confirmed order value**, not automatically **collected cash**. Analyzing captures or refunds requires payment sources and facts at their own grain. Group by **currency** to avoid directly adding VND and USD.

### 7.1. Why not join on customer_id and is_current?

~~~sql
-- Wrong for the question "segment at purchase":
SELECT
    f.order_id,
    d.segment_code
FROM fact_order AS f
JOIN dim_customer_version AS d
    ON d.tenant_id = f.tenant_id
   AND d.customer_id = f.customer_id
WHERE d.effective_to IS NULL;
~~~

This query classifies **all of C-42's orders as GOLD** after September 1. It is only valid for a different question: "What are the historical orders of customers who are **currently GOLD**?".

Name the two metrics clearly:

- **sales_by_segment_at_purchase**: fact joined to the version valid at event time.
- **historical_sales_by_current_segment**: fact grouped by current dimension; historical values are **reclassified as of today** intentionally.

If reports do not distinguish these two meanings, numbers shift after every segment update without users understanding why.

### 7.2. Is range lookup different from storing the surrogate key in the fact?

Two common approaches exist:

1. **Resolve customer_sk when loading the fact**, then join facts directly via surrogate FK. Queries are usually clean and convenient; however, when a dimension change is entered **retroactively**, affected facts may need their customer_sk restated.
2. **Dynamic JOIN on natural key + event time** at query time. Avoids updating FKs in some cases, but queries cost more, risk row multiplication if history overlaps, and require consistent as-of logic.

Many analytics warehouses use approach 1. Either way, you must define rules for **late-arriving dimensions**, **boundary times**, and **historical corrections**.

## 8. Late-arriving dimension events and retroactive changes

In practice, sources do not always emit changes in order. A worker may receive a GOLD event before SILVER; an operational system may notify late that SILVER actually took effect on June 15.

### 8.1. Distinguishing "late-arriving" from "retroactive effectivity"

- **Late-arriving event:** the business event happened earlier, but the warehouse received it late. The event's effective time remains the verified business timestamp.
- **Retroactive correction:** the business later **revises its knowledge of history**, e.g., discovering the segment was valid from June 10 rather than June 15.
- **Out-of-order arrival:** events for the same entity reach consumers out of order. Requires **source revision/sequence** and a reorder/replay policy, never ordering solely by arrival time.

Never handle all three situations by simply "closing the current row and inserting a new current row at NOW()." Doing so can corrupt all historical reports.

### 8.2. Example of splitting intervals when discovering a change in the past

Suppose the warehouse currently records:

~~~text
BRONZE: [01/01, 06/15)
SILVER: [06/15, 09/01)
GOLD:   [09/01, +infinity)
~~~

Upon verification, the source reports that the customer moved to SILVER on **June 10**, not June 15. The correct effective timeline must be:

~~~text
BRONZE: [01/01, 06/10)
SILVER: [06/10, 09/01)
GOLD:   [09/01, +infinity)
~~~

This is **adjusting the boundary between two versions**, not merely adding a current version. Lock the natural key, inspect affected intervals, update transactionally, and **review facts with confirmed_at from June 10 until before June 15**. Such facts, if pointing to BRONZE, must be moved to SILVER (or reports using dynamic as-of joins reflect the new history).

If the source inserts a **PLATINUM** status valid only for **[06/10, 06/12)**, you must **split the BRONZE interval** into before and after segments if the contract confirms returning to BRONZE, giving each segment an appropriate version/key. Simply updating **effective_from** on an existing row without considering preceding/following segments can lose history.

**Principle:** editing history requires milestones, rules, recording the source of the adjustment, and a strategy for updating affected facts/aggregates; never edit the dimension alone and assume all facts remain properly classified.

### 8.3. Facts arriving before dimensions

An order dated June 18 enters the pipeline, but the SILVER update has not arrived yet. Options:

- **Hold the fact in staging** and retry within a defined time threshold.
- Bind to an **unknown/inferred dimension member** with clear identification, followed later by **restatement** to the true customer_sk.
- If requirements permit, query an authoritative historical source as-of before deciding classification.

Never assign **current GOLD** to the June 18 fact without evidence. Using an unknown key may temporarily omit detail in reports, but it is **more honest** than fabricating wrong history. Monitor unresolved fact counts, oldest unresolved age, and load latency.

## 9. "What we know today" vs. "what was valid then": limits of SCD Type 2

Standard SCD Type 2 models **valid time**: the interval over which a version is valid in the business. **recorded_at** only states when a row was written into the warehouse; alone, it cannot reconstruct the entire state the warehouse believed on every past date, especially if older rows were edited.

If the audit requirement is:

> "On June 20, how did the report present the customer's segment as of June 10, and on June 25 how did the business revise that understanding?"

...then you must separate two axes:

| Axis | Question |
| --- | --- |
| **Valid time** | When was the attribute considered effective in the business? |
| **Recorded/system time** | From when to when was this historical interpretation known/recorded by the system? |

A **bitemporal model** can store both **valid_from/valid_to** and **recorded_from/recorded_to**, or store append-only events/revisions sufficient to reconstruct known states. This design increases complexity and is not mandatory for every Type 2 dimension.

**Do not equate SCD Type 2 history with transaction document history.** For instance, **order_items.unit_price_at_confirmation** is the locked price of the order and must not change when catalog price lists or category versions change. Category SCD2 analyzes context at sale time; it does not re-determine transaction prices.

## 10. CDC, ETL, and idempotency: creating each version once

A pipeline bringing source changes into **dim_customer_version** typically has these stages:

~~~text
Authoritative source
   |
   | CDC / outbox / checkpointed batch
   v
Staging + schema, tenant, natural key checks
   |
   | Normalize tracked attributes, valid time, source revision
   v
Detect meaningful changes
   |
   | Lock on (tenant_id, customer_id)
   v
Close/split old interval + create/adjust new version
   |
   | Within appropriate transaction boundary
   v
Reconcile dimension -> map/restate facts if needed
   |
   v
Publish data for reporting
~~~

**Idempotency** spans multiple layers:

1. **Source redelivers same event ID:** do not create two identical versions.
2. **Events with same natural key but different source revisions:** process by sequence and effectivity policy; never arbitrarily let later-arriving messages win.
3. **Changes to untracked fields:** do not create needless Type 2 versions.
4. **Retroactive edits:** do not merely overwrite current; recompute affected intervals.
5. **Pipeline restart/backfill:** do not drop or duplicate versions, and do not leave facts pointing to the wrong customer_sk.

Store metadata in staging/control tables such as **source_event_id**, **source_revision**, checkpoints, processing status, and payload fingerprints. If event sources feed two different databases, enforce dedicated deduplication and replay contracts; **UNIQUE (tenant,customer,version_no)** alone does not prove each event was processed once.

### 10.1. Source versions and dimension versions are not always equal

Suppose the customer source has revisions 100, 101, 102:

- r100: segment BRONZE, region SOUTH.
- r101: changes only phone number, which is not tracked in SCD2.
- r102: changes segment to SILVER.

The dimension may have **v1 = BRONZE**, **v2 = SILVER**. Thus **source_revision = 102** can correspond to **version_no = 2**, not 102. If the pipeline uses revisions for ordering, never assume dimension version numbers equal or stay contiguous with source revisions.

### 10.2. Handling inactive customers

There are two valid policies with different meanings:

- **Close the final version with no current row:** after the closing date, as-of lookups find no version; fits when the entity is no longer in tracked scope.
- **Create a new version with status = INACTIVE/DELETED:** preserves a version representing the inactive state; reporting by status and duration can be easier.

Do not physically delete historical versions if old facts reference them. Equally, do not treat SCD2 as an excuse to retain personal data indefinitely: retention limits, erasure/masking, and access permissions must follow applicable policies.

## 11. Reconciling SCD Type 2: more than checking the current row

A dimension can have exactly one current row and still contain **gaps**, **overlaps**, wrong timestamps, or facts pointing to the wrong version. Therefore, check at every level.

### 11.1. Duplicate current rows

~~~sql
SELECT
    tenant_id, customer_id,
    COUNT(*) AS current_rows
FROM dim_customer_version
WHERE effective_to IS NULL
GROUP BY tenant_id, customer_id
HAVING COUNT(*) > 1;
~~~

With the unique partial index from section 5, this query must return zero rows. However, **having no current row** can also be an anomaly if the customer is still active and the contract requires a current row; cross-check against source/identity to tell bugs from closed customers.

### 11.2. Overlaps and gaps

With an exclusion constraint, overlapping ranges are rejected on write. To check staging or a warehouse without exclusion constraints, test intersection of half-open ranges:

~~~sql
SELECT
    a.tenant_id,
    a.customer_id,
    a.customer_sk AS version_a,
    b.customer_sk AS version_b
FROM dim_customer_version AS a
JOIN dim_customer_version AS b
  ON b.tenant_id = a.tenant_id
 AND b.customer_id = a.customer_id
 AND b.customer_sk > a.customer_sk
WHERE tstzrange(a.effective_from, a.effective_to, '[)')
      &&
      tstzrange(b.effective_from, b.effective_to, '[)');
~~~

The **surrogate primary key** avoids comparing a row to itself, though pairwise joins can be expensive over deep history. In operations, choose appropriate reconciliation scopes, indexes, and verification mechanisms.

Check for gaps between consecutive versions:

~~~sql
WITH sequenced AS (
    SELECT
        tenant_id,
        customer_id,
        customer_sk,
        effective_from,
        effective_to,
        LEAD(effective_from) OVER (
            PARTITION BY tenant_id, customer_id
            ORDER BY effective_from, customer_sk
        ) AS next_from
    FROM dim_customer_version
)
SELECT *
FROM sequenced
WHERE effective_to IS NOT NULL
  AND next_from IS NOT NULL
  AND effective_to <> next_from;
~~~

If **effective_to < next_from**, there is a **gap**. If **effective_to > next_from**, there is an overlap (even though the constraint forbids it). A gap is **not automatically a bug** if the customer had an out-of-scope period; conversely, if the contract requires continuous coverage, raise an alert.

### 11.3. Do facts reference the right point in time?

When facts store **customer_sk**, a foreign key proves the dimension row **exists**, not that it was **valid when the fact occurred**.

~~~sql
SELECT
    f.order_id,
    f.confirmed_at,
    f.customer_sk,
    d.effective_from,
    d.effective_to
FROM fact_order AS f
JOIN dim_customer_version AS d
    ON d.customer_sk = f.customer_sk
WHERE d.tenant_id <> f.tenant_id
   OR d.customer_id <> f.customer_id
   OR f.confirmed_at < d.effective_from
   OR (
       d.effective_to IS NOT NULL
       AND f.confirmed_at >= d.effective_to
   );
~~~

If the query returns rows, facts are pointing to the **wrong customer or wrong validity interval**. When using surrogate keys, this is a vital check after backfills, retroactive edits, or dimension updates.

Another check looks for facts missing a dimension row, though enforced hard FKs and **NOT NULL** block this in local relational tables. Analytics warehouses without physical FKs must run this check explicitly.

### 11.4. Do not reconcile history against current attributes

A job that sees order O-101 has **segment BRONZE** while the customer's current profile says **GOLD**, and then "fixes" past facts to GOLD, enforces the wrong invariant. You must compare against the **dimension version valid at confirmed_at**, under the defined time rule.

Beyond row-level checks, measure **versions per customer**, gap/overlap rates, facts awaiting version resolution, retried events, checkpoint lag, restatement counts, and rebuild duration. A pipeline can succeed with zero errors while producing wrong history if effective time semantics are misunderstood.

## 12. SCD Type 2 in document, graph, and analytical models

The principle of storing multiple point-in-time versions does not depend exclusively on SQL.

| Model | How dimension history is represented | Pros and risks |
| --- | --- | --- |
| **Relational OLTP** | Customer history table with version/valid period, appropriate FKs | Clear constraints and transactions; multi-writer setups require access governance |
| **Dimensional warehouse** | **dim_customer_version** with surrogate key, facts pointing to version | Easy "as sold" reporting; needs ETL, SCD matching, and restatement |
| **Document** | **customerVersions** collection with per-version documents, or bounded version array | Easy retrieval of one customer's history; long/complex arrays, as-of uniqueness needs custom logic |
| **Graph** | Vertices/edges carrying valid_from/valid_to or historical state nodes | Traverses relationships at time t; must avoid counting both old and new edges |
| **Event log** | CustomerSegmentChanged events with ID/time/revision | Can reconstruct dimension; replay requires idempotency, ordering, and retroactive handling |

In a **document model**, a customer can have multiple version documents, each carrying **customerId**, **effectiveFrom**, **effectiveTo**, and attributes. An as-of query still must pick exactly one document; missing interval-overlap guards can yield two results. Embedding all history inside one document is not automatically better: it can grow unbounded, cause update contention, and complicate temporal indexing.

In a **graph**, storing both old and new **Customer–BELONGS_TO–Segment** edges means a traversal without valid-time filtering may return multiple segments. SCD2 requires queries/edges with explicit validity bounds, not merely historical presence.

In **analytics**, SCD2 is typically used when the organization needs "sales by segment/region at event time." If only current-state grouping is needed, Type 1 can be simpler and cheaper. An architecture may also maintain a **current table** for daily operations alongside a **versioned dimension** for reporting; the two serve different contracts.

## 13. Safe implementation and migration process

### 13.1. Migrating from Type 1 to Type 2

Suppose a warehouse previously had only **dim_customer(customer_id, segment_code)** and wants to begin tracking history:

1. **Lock down reporting questions:** analyze by current segment, at purchase time, or both.
2. **Define the natural key** including tenant and ID reuse policy.
3. **List Type 2 tracked attributes**, Type 1 attributes, and privacy policies.
4. **Set temporal conventions:** valid time, timezone, cutover point, and NULL handling.
5. **Create the version table** with surrogate key, period constraints, unique current row, and source markers.
6. **Load initial versions** from verified sources, clearly recording when history tracking began; never fabricate past segments.
7. **Build the change pipeline:** idempotent, checkpointed/replayable, locked by natural key, with retroactive handling.
8. **Map facts to customer_sk** by event time where history exists; mark unknown/inferred where missing.
9. **Shadow reports:** compare revenue, fact counts, and point-in-time segments, explaining valid differences caused by the reporting logic change.
10. **Cut over queries in a controlled way** and monitor gaps, overlaps, unmatched facts, lag, and control totals.

**You cannot accurately recover past segments for every historical day from a single current Type 1 row** if reliable historical data no longer exists. Backfilling today's value with a synthetic effective_from makes reports look complete while being fundamentally wrong.

### 13.2. Changing the policy for a tracked attribute

If **region_code** previously did not trigger versions, and the business now needs revenue by region at sale date, you may need to:

- Verify whether full region history exists in the source.
- Add region to the Type 2 tracked list.
- Decide how to mark periods that cannot be verified.
- Reconstruct the dimension from substantiated history, update customer_sk on affected facts, and reconcile reports.
- Version the transformation logic and assess impact on existing reports.

Never retroactively update all past versions with the current region and call it history.

## 14. Choosing designs using operational evidence

A Type 2 dimension is normally **smaller than facts**, yet can grow rapidly if too many frequently changing attributes are tracked. Suppose a customer has dozens of profile edits per day; creating a new version for every edit balloons row counts and JOIN costs while serving no report.

### 14.1. Metrics worth measuring

| Metric | What you need to know |
| --- | --- |
| **Versions per natural key** | Distribution of versions/customer, p95/p99, and max |
| **Change events per day** | Throughput, peak windows, ratio of Type 1-only changes |
| **SCD load latency** | From source commit/valid event until dimension update |
| **Fact dimension match rate** | Share of facts resolving to a valid version; pending facts |
| **Overlap/gap count** | Any broken intervals or missing history |
| **Retroactive correction rate** | Frequency of interval splits/edits, facts needing restatement |
| **Query p95/p99** | Performance of surrogate-key JOINs and as-of lookups |
| **Rebuild/restate duration** | Whether recovery and recomputation fit within required SLAs |

### 14.2. Physical tuning does not replace a sound temporal model

- **Index on (tenant_id, customer_id, effective_from)** helps look up a customer at a point in time; measure against real version distributions.
- **GiST exclusion constraint** enforces non-overlap but adds write/index cost; test in target deployment environments.
- **Partitioning** can help very large dimensions, though cross-partition unique/exclusion constraints depend on the DBMS; never assume global constraint enforcement if the physical schema lacks support.
- **Surrogate-key fact FKs** usually make reports faster than repeated range JOINs, at the trade-off of needing restatement when history changes.
- **Materialized views by segment** require rebuilds or refreshes when history changes; updating the dimension alone may leave aggregated reports stale.

A design is only sound when it **has exact "as-of" semantics**, is reconcilable, and meets read/write SLOs under representative data volumes, timestamps, and change rates.

## 15. Case-study exercises

### Case 1 — Boundary effective timestamp

Customer C-42 has two versions: BRONZE **[01/01, 06/15)** and SILVER **[06/15, 09/01)**. An order is confirmed at **exactly 2026-06-15 00:00+07**.

**Question:** Which version does the order belong to? Why shouldn't BETWEEN with two inclusive bounds be used?

### Case 2 — Surrogate key and natural key

The dimension table has **customer_sk** 1001, 1002, and 1003 all matching **customer_id = C-42**. One team proposes UNIQUE(customer_id) because "a customer only has one ID."

**Question:** Does that constraint match the grain? What should be unique instead?

### Case 3 — Report shifts when a customer upgrades

In May a customer was BRONZE and spent 2,000,000 VND. In September the customer upgraded to GOLD. The "sales by segment at purchase" report suddenly shifts May's 2,000,000 VND into GOLD.

**Question:** Which JOIN likely caused the bug? Restate the version-lookup rule.

### Case 4 — Late-arriving event with retroactive effectivity

On June 20 the system receives a notice: the customer became SILVER on June 10, whereas the warehouse stores BRONZE until June 15 and SILVER from June 15. Orders exist from June 11 to June 14.

**Question:** Which intervals must be adjusted? What happens to facts already bound to the old customer_sk?

### Case 5 — Type 1 or Type 2?

An administrator fixes a typo in **region_name** from "Northen" to "Northern" with no actual territory change. Another customer is transferred from Northern to Southern management effective the first of the month.

**Question:** Should both changes follow the same history policy? Why?

### Case 6 — Two overlapping intervals

A customer has version A **[01/01, 08/01)** and version B **[06/01, 09/01)**. Both have non-NULL effective_to, so the unique current index raises no error.

**Question:** Where is the bug, and which PostgreSQL constraint protects against it?

### Case 7 — Recording events with unchanged values

The source emits revision 11 with segment SILVER, revision 12 changing only phone number, and revision 13 again sending segment SILVER. The pipeline creates new versions for all three events.

**Question:** Which fields/metadata must be separated to prevent dimension bloat?

### Case 8 — Non-existent historical data

The business only began collecting segments on October 1; prior to that, only customer IDs existed without segment history. A team plans to assign November's current segment to all orders from the previous two years so reports look complete.

**Question:** Is this approach trustworthy? How should missing historical data be presented?

### Case 9 — Two timelines

On June 20 the warehouse reported that a June 12 order belonged to BRONZE. On June 25 the business approved a retroactive correction stating the customer had been SILVER since June 10. An auditor asks **what the report knew on June 20**.

**Question:** Are the edited SCD2 effective_from/effective_to columns alone sufficient to answer? What else must be stored?

### Solution hints

1. **SILVER**, because **[06/15, 09/01)** includes the start boundary; BRONZE ends at 06/15 and is no longer valid. Inclusive BETWEEN could match both versions on the boundary.
2. **No**. The natural key identifies a customer and can appear across many versions. The PK is **customer_sk**; use UNIQUE(tenant_id, customer_id, version_no), UNIQUE on effective_from, unique current, and an overlap-prevention constraint.
3. Joining on the **current version** (effective_to IS NULL) reclassified history. Use the fact's properly bound **customer_sk**, or join on customer_id with **confirmed_at inside the validity interval**.
4. Change BRONZE to end on **June 10** and SILVER to start on **June 10**, per verified source; inspect adjacent intervals. Facts from **June 10 until before June 15** pointing to BRONZE need **restatement** to the right version or dynamic as-of lookup. Reconcile precomputed aggregates.
5. Fixing a typo can be **Type 1** since business state did not change. Actual territory transfer should be **Type 2** if reporting by region at sale time is needed; the tracked-attributes contract governs this.
6. The overlapping range **06/01–08/01** creates two concurrently valid versions. Use **GiST EXCLUDE ... tstzrange(...) WITH &&** per natural key (may require **btree_gist**) or equivalent enforcement.
7. Only create a new version when **Type 2 tracked attributes** actually change; separate source_revision/event IDs from dimension versions, normalize values, and deduplicate events. Phone number, if untracked, needs no version.
8. **Not trustworthy**. You cannot infer segments two years ago from November's value without evidence. Use **unknown/unverified history** per policy, inspect source logs/invoices/events if available, and disclose reporting limitations.
9. **Insufficient** if editing the SCD2 row erased the prior state of knowledge. You need **recorded/system time** history or an append-only event/audit log capable of reconstruction alongside valid time; this is a bitemporal requirement.

## 16. Key takeaways

**SCD Type 2 stores multiple version rows for the same entity to preserve dimension attributes across effective time.** The grain is no longer "one row per customer," but **one row per version of a customer over a time interval**. Natural keys link versions together, while surrogate keys identify individual versions for facts to reference.

Three vital invariants are **no overlapping intervals**, **at most one current version**, and **facts pointing to the version valid at event time**. Adding CHECK/UNIQUE alone does not guarantee all invariants; range constraints or corresponding verification workflows are needed.

When late-arriving data or retroactive edits occur, **do not simply close the current row and insert a new row with processing time**. Verify the business effective time, adjust affected intervals, and audit previously classified facts and reports. Only with clear contracts for time, provenance, and recovery can SCD Type 2 keep historical data models explainable and safe to evolve.
