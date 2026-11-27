# Duplicate-Key MERGE Sources and Determinism of Synchronization Operations

> **Topic:** Database Engine Relational Oracle  
> **Chapter:** Data Manipulation  
> **Objective:** Understand uniqueness requirements for MERGE sources; identify duplicate keys, fanout, ORA-30926, and ORA-00001; normalize sources with ROW_NUMBER or GROUP BY; protect target keys with constraints; and design synchronization with explicit, repeatable, verifiable record-selection rules.

## 1. MERGE Synchronizes Source to Target by Key

Oracle MERGE combines UPDATE and INSERT logic in a single statement. The ON condition determines which source row matches which target row:

~~~sql
MERGE INTO customer_status t
USING customer_status_stage s
ON (t.customer_id = s.customer_id)
WHEN MATCHED THEN
    UPDATE SET
        t.status = s.status,
        t.updated_at = s.updated_at
WHEN NOT MATCHED THEN
    INSERT (customer_id, status, updated_at)
    VALUES (s.customer_id, s.status, s.updated_at);
~~~

In this example, CUSTOMER_ID is the join key and the business expects one current status per customer in the target table.

Before writing MERGE, you must answer:

1. For a given CUSTOMER_ID, which record does the source supply for synchronization?
2. In the target table, does one CUSTOMER_ID identify at most one row?
3. If the source has multiple records with the same key, are they copies, valid events, deltas to accumulate, or conflicts?

**Principle:** A MERGE source must be normalized by the matching key; the target table must enforce key uniqueness if business rules require one target row per key.

## 2. Source and Target Grain

Grain describes what a single row in a table or result set represents.

| Dataset | Example grain |
|---|---|
| CUSTOMER_STATUS | One current status per customer |
| CUSTOMER_STATUS_STAGE | One update event; possibly multiple events per customer |
| CUSTOMER_STATUS_SOURCE | One final selected status per customer |
| CUSTOMER_STATUS_HISTORY | One status version per customer and effective timestamp |

A staging table can validly store multiple events for the same customer. However, if staging is used to update a single current-state row, there must be a rule to pick or aggregate events before MERGE.

Duplicate keys in the source can arise from multiple valid events, multiple updates within a day, row-multiplying JOINs, duplicate loads, or multiple systems sending records. Understand the data semantics before choosing a resolution.

## 3. MERGE Determinism and ORA-30926

Oracle defines MERGE as a deterministic statement: the same row of the target table cannot be updated more than once within the same MERGE statement.

Suppose the target has one row:

~~~text
CUSTOMER_ID | STATUS
------------+--------
10          | ACTIVE
~~~

The source has two rows with the same key:

~~~text
CUSTOMER_ID | STATUS
------------+---------
10          | ACTIVE
10          | BLOCKED
~~~

Both source rows match the same target row via:

~~~sql
ON (t.customer_id = s.customer_id)
~~~

When MERGE attempts to update the same target row from multiple source rows, Oracle can raise:

~~~text
ORA-30926: unable to get a stable set of rows in the source tables
~~~

This is the typical situation when multiple source rows share a key matching one target row. ORA-30926 can also relate to an unstable source set or concurrent DML scenarios depending on the case; do not conclude every ORA-30926 error is caused by duplicate keys.

### 3.1. Do Not Rely on Source ORDER BY

Adding ORDER BY to the source subquery hoping the last row wins is not a safe synchronization rule. MERGE is a set-based operation; never assume Oracle processes source rows in display order or that a later row overwrites an earlier one.

If business logic requires the latest record, select that record in the source using an analytic function with a unique tie-breaker.

### 3.2. Duplicate Source Keys When Target Does Not Yet Have the Row

Suppose the target does not yet have CUSTOMER_ID = 20, and the source has two rows with that key. Both can enter the WHEN NOT MATCHED branch:

- If the target has PRIMARY KEY/UNIQUE on CUSTOMER_ID, the operation fails with ORA-00001: unique constraint violated.
- Without a protective constraint, two duplicate-key rows are inserted into the target.

This differs from multiple source rows updating the same existing target row. Therefore, check both MATCHED and NOT MATCHED paths.

## 4. Identifying Duplicate Types

### 4.1. Exact Duplicates

~~~text
CUSTOMER_ID | STATUS | CREDIT_LIMIT
------------+--------+-------------
10          | ACTIVE | 5000
10          | ACTIVE | 5000
~~~

If two rows are identical across all meaningful columns and business rules allow dropping copies, DISTINCT can eliminate them.

### 4.2. Duplicate Key with Different Values

~~~text
CUSTOMER_ID | STATUS
------------+---------
10          | ACTIVE
10          | BLOCKED
~~~

DISTINCT still keeps both rows. This is a conflict: there must be a business rule such as latest event wins, higher source priority wins, higher version wins, aggregate deltas, or reject the batch for manual handling.

Do not arbitrarily pick MAX(STATUS), MIN(STATUS), or any random value just to make MERGE run.

### 4.3. Duplicates Caused by Row-Multiplying JOINs

~~~sql
SELECT c.customer_id,
       c.status,
       p.phone_number
FROM customers c
JOIN customer_phones p
  ON p.customer_id = c.customer_id;
~~~

If a customer has three phone numbers, the source query produces three rows for the same CUSTOMER_ID. If merging by CUSTOMER_ID to update customer status, the source has the wrong grain.

If you need to sync each phone number, the key must include PHONE_ID or the phone's business key. If you only need customer status, drop the unnecessary JOIN or aggregate/select attributes according to explicit rules.

## 5. Checking Duplicate Keys Before MERGE

Run checks on the exact batch scope or source query that MERGE will consume.

### 5.1. Single Key

~~~sql
SELECT customer_id,
       COUNT(*) AS source_rows
FROM customer_status_stage
WHERE batch_id = :p_batch_id
GROUP BY customer_id
HAVING COUNT(*) > 1
ORDER BY customer_id;
~~~

### 5.2. Composite Key

If the business key consists of TENANT_ID and EXTERNAL_CUSTOMER_ID:

~~~sql
SELECT tenant_id,
       external_customer_id,
       COUNT(*) AS source_rows
FROM customer_stage
WHERE batch_id = :p_batch_id
GROUP BY tenant_id, external_customer_id
HAVING COUNT(*) > 1;
~~~

Check every column in the ON clause. Checking only part of a composite key can report false duplicates or miss real ones.

### 5.3. NULL Keys

~~~sql
SELECT COUNT(*) AS null_key_rows
FROM customer_status_stage
WHERE batch_id = :p_batch_id
  AND customer_id IS NULL;
~~~

With `t.customer_id = s.customer_id`, NULL does not equal NULL; the comparison returns UNKNOWN, so two NULL rows do not match. A NULL source row can fall into WHEN NOT MATCHED if the schema allows it.

If CUSTOMER_ID is the synchronization key, it should normally be NOT NULL. For composite keys, explicitly define whether each component is nullable.

### 5.4. Duplicates in Target

~~~sql
SELECT customer_id,
       COUNT(*) AS target_rows
FROM customer_status
GROUP BY customer_id
HAVING COUNT(*) > 1;
~~~

If business rules require one row per customer, this query should return zero rows and the table needs a constraint enforcing it.

## 6. Selecting One Row with ROW_NUMBER

When the source holds multiple versions for the same key and the rule is to keep the latest record, use ROW_NUMBER.

~~~sql
CREATE TABLE customer_status_stage (
    stage_row_id NUMBER PRIMARY KEY,
    batch_id NUMBER NOT NULL,
    customer_id NUMBER NOT NULL,
    status VARCHAR2(20 CHAR) NOT NULL,
    changed_at TIMESTAMP(6) WITH TIME ZONE,
    source_version NUMBER
);
~~~

Assign a rank within each CUSTOMER_ID:

~~~sql
SELECT stage_row_id,
       customer_id,
       status,
       changed_at,
       source_version,
       ROW_NUMBER() OVER (
           PARTITION BY customer_id
           ORDER BY changed_at DESC NULLS LAST,
                    source_version DESC NULLS LAST,
                    stage_row_id DESC
       ) AS rn
FROM customer_status_stage
WHERE batch_id = :p_batch_id;
~~~

PARTITION BY groups data per customer. CHANGED_AT prioritizes the newest event; SOURCE_VERSION is the next criterion; STAGE_ROW_ID is the final unique tie-breaker because it is the primary key.

Filter RN = 1 to get exactly one row per customer:

~~~sql
SELECT customer_id,
       status,
       changed_at,
       source_version
FROM (
    SELECT s.customer_id,
           s.status,
           s.changed_at,
           s.source_version,
           ROW_NUMBER() OVER (
               PARTITION BY s.customer_id
               ORDER BY s.changed_at DESC NULLS LAST,
                        s.source_version DESC NULLS LAST,
                        s.stage_row_id DESC
           ) AS rn
    FROM customer_status_stage s
    WHERE s.batch_id = :p_batch_id
)
WHERE rn = 1;
~~~

### 6.1. MERGE from the Normalized Source

~~~sql
MERGE INTO customer_status t
USING (
    SELECT customer_id,
           status,
           changed_at,
           source_version
    FROM (
        SELECT s.customer_id,
               s.status,
               s.changed_at,
               s.source_version,
               ROW_NUMBER() OVER (
                   PARTITION BY s.customer_id
                   ORDER BY s.changed_at DESC NULLS LAST,
                            s.source_version DESC NULLS LAST,
                            s.stage_row_id DESC
               ) AS rn
        FROM customer_status_stage s
        WHERE s.batch_id = :p_batch_id
    )
    WHERE rn = 1
) s
ON (t.customer_id = s.customer_id)
WHEN MATCHED THEN
    UPDATE SET
        t.status = s.status,
        t.changed_at = s.changed_at,
        t.source_version = s.source_version
WHEN NOT MATCHED THEN
    INSERT (
        customer_id,
        status,
        changed_at,
        source_version
    )
    VALUES (
        s.customer_id,
        s.status,
        s.changed_at,
        s.source_version
    );
~~~

The MERGE source has at most one row per CUSTOMER_ID. Selecting the winning row is determined by the analytic ordering, independent of arbitrary read order.

### 6.2. The Final Tie-Breaker Must Be Unique

If you only order by CHANGED_AT DESC and two rows share the same timestamp, their relative order is undefined. The row picked by ROW_NUMBER can vary across runs.

Add the unique STAGE_ROW_ID at the end of ORDER BY to establish a total order. If the source system provides a reliable event sequence, version, or transaction ID, prefer those as business ordering criteria. The technical tie-breaker only breaks ties that remain equal after business criteria.

If there is insufficient information to choose between two conflicting payloads, route that key to an error report rather than silently picking one row.

## 7. Aggregating the Source with GROUP BY

ROW_NUMBER fits when selecting one representative record. If multiple source rows are valid contributions that need combining, use GROUP BY.

Example balance-change events:

~~~text
ACCOUNT_ID | DELTA_AMOUNT
-----------+-------------
100        | 50
100        | -10
100        | 25
200        | 100
~~~

If the requirement is total net change per account:

~~~sql
SELECT account_id,
       SUM(delta_amount) AS net_delta,
       COUNT(*) AS event_count
FROM account_events_stage
WHERE batch_id = :p_batch_id
GROUP BY account_id;
~~~

You can use the aggregated set as the MERGE source:

~~~sql
MERGE INTO account_batch_totals t
USING (
    SELECT account_id,
           SUM(delta_amount) AS net_delta,
           COUNT(*) AS event_count
    FROM account_events_stage
    WHERE batch_id = :p_batch_id
    GROUP BY account_id
) s
ON (t.account_id = s.account_id)
WHEN MATCHED THEN
    UPDATE SET
        t.net_delta = s.net_delta,
        t.event_count = s.event_count
WHEN NOT MATCHED THEN
    INSERT (account_id, net_delta, event_count)
    VALUES (s.account_id, s.net_delta, s.event_count);
~~~

Choose aggregates according to data semantics:

| Source semantics | Potentially suitable handling |
|---|---|
| Multiple deltas to sum | SUM |
| Multiple events, count needed | COUNT |
| Business maximum value needed | MAX |
| Business minimum value needed | MIN |
| Latest record with multiple correlated columns needed | ROW_NUMBER then RN = 1 |
| All historical records must be preserved | Keep as-is, use event/version key |

Do not apply MAX to each column independently to simulate "getting the latest row". MAX(STATUS) and MAX(CHANGED_AT) can come from two different rows, fabricating a combination that never existed. To get the full latest row, use ROW_NUMBER and take all columns from that same row.

## 8. When Should a Batch Be Rejected?

Not every system is allowed to pick a winning record automatically. For financial data, access permissions, or legal status, two conflicting events may require manual intervention.

~~~sql
SELECT customer_id,
       COUNT(*) AS row_count
FROM customer_status_stage
WHERE batch_id = :p_batch_id
GROUP BY customer_id
HAVING COUNT(*) > 1;
~~~

If the query returns rows, the workflow can:

1. Mark the batch as VALIDATION_FAILED.
2. Save duplicate keys and related rows into an audit/quarantine table.
3. Skip running MERGE for that batch.
4. Request the source to resend or have an authorized person resolve the conflict.
5. Re-run only after the data is verified.

Determinism means the outcome is governed by explicit rules; it does not require automatically fixing every duplicate automatically.

## 9. Protecting Target Keys with Constraints

If CUSTOMER_STATUS must have one row per customer:

~~~sql
ALTER TABLE customer_status
MODIFY (customer_id NOT NULL);

ALTER TABLE customer_status
ADD CONSTRAINT uq_customer_status_customer
UNIQUE (customer_id);
~~~

Or declare CUSTOMER_ID as PRIMARY KEY if it is the true primary key.

Constraints protect the target table against duplicate data from every write path: MERGE, direct INSERT, another batch, or another application. Checks in application code cannot replace database constraints.

If the table already contains duplicates, adding the constraint will fail. Find and resolve legacy duplicates per business rules before adding UNIQUE; never arbitrarily delete a record just to make DDL succeed.

### 9.1. Composite Key

If the synchronization key is TENANT_ID and EXTERNAL_ID:

~~~sql
ALTER TABLE external_customer
ADD CONSTRAINT uq_external_customer
UNIQUE (tenant_id, external_id);
~~~

The MERGE source must be unique on both columns, and the ON condition must also use both:

~~~sql
ON (
    t.tenant_id = s.tenant_id
    AND t.external_id = s.external_id
)
~~~

Checking or joining only on EXTERNAL_ID can cross-match customers across tenants.

## 10. NULL Keys and the ON Condition

Equality comparison in SQL does not treat NULL as equal to NULL. `NULL = NULL` evaluates to UNKNOWN, not TRUE. Therefore:

~~~sql
ON (t.external_id = s.external_id)
~~~

does not match two rows with NULL EXTERNAL_ID. A NULL source row may be treated as unmatched and enter the INSERT branch.

If the business key must have a value, set NOT NULL on all key components. If the business genuinely treats two NULLs as the same key value, write an explicit null-safe condition:

~~~sql
ON (
       t.external_id = s.external_id
    OR (t.external_id IS NULL AND s.external_id IS NULL)
)
~~~

This condition must be paired with matching uniqueness protection. Do not assume a UNIQUE constraint on nullable columns automatically models every null-safe business key definition. You can use NOT NULL, a virtual column, or a function-based unique index with a carefully chosen normalization expression.

Do not use NVL(key, -1) or an arbitrary string sentinel if that value could occur legitimately; a sentinel can collapse two distinct keys into one.

## 11. Designing the Right ON Condition

ON defines which rows are considered MATCHED. It should describe a stable identifying key, typically the primary key or unique business key.

Example:

~~~sql
ON (
    t.tenant_id = s.tenant_id
    AND t.external_customer_id = s.external_customer_id
)
~~~

Avoid putting mutable state conditions into ON when they are not part of identity.

~~~sql
ON (
    t.customer_id = s.customer_id
    AND t.status = 'ACTIVE'
)
~~~

If the customer already exists with status BLOCKED, the target row is not considered a match. The source enters WHEN NOT MATCHED and attempts to INSERT an existing CUSTOMER_ID, causing ORA-00001 if a unique constraint exists.

If the goal is to update only ACTIVE customers, keep the identity key in ON and place the update filter in the UPDATE branch's WHERE clause:

~~~sql
MERGE INTO customer_status t
USING customer_status_source s
ON (t.customer_id = s.customer_id)
WHEN MATCHED THEN
    UPDATE SET t.status = s.status
    WHERE t.status = 'ACTIVE'
WHEN NOT MATCHED THEN
    INSERT (customer_id, status)
    VALUES (s.customer_id, s.status);
~~~

BLOCKED customers are still recognized as existing; the UPDATE filter only decides whether to update the matched row. Define separately how business logic handles matched rows ineligible for update.

### 11.1. Do Not Update Columns Used in ON

Oracle forbids updating columns referenced in MERGE's ON condition; doing so raises ORA-38104. If a key value needs to change, design a separate workflow for old and new keys rather than trying to UPDATE the identifying column inside the same MERGE.

## 12. Source Multiplied by JOINs

A source may appear unique before a JOIN yet become duplicated after the JOIN:

~~~sql
SELECT s.customer_id,
       s.status,
       a.attribute_value
FROM customer_status_stage s
JOIN customer_attributes a
  ON a.customer_id = s.customer_id
WHERE s.batch_id = :p_batch_id;
~~~

If a customer has multiple attributes, the source has multiple rows for the same CUSTOMER_ID. Check the complete source query:

~~~sql
SELECT customer_id,
       COUNT(*) AS source_rows
FROM (
    SELECT s.customer_id,
           s.status,
           a.attribute_value
    FROM customer_status_stage s
    JOIN customer_attributes a
      ON a.customer_id = s.customer_id
    WHERE s.batch_id = :p_batch_id
)
GROUP BY customer_id
HAVING COUNT(*) > 1;
~~~

The fix depends on the goal: remove the unnecessary JOIN; pick one attribute by rule; aggregate attributes; or add the attribute key to ON if each attribute is an independent entity to sync.

Do not mechanically add DISTINCT to mask cardinality expansion after a JOIN.

## 13. Version-Based Synchronization and Idempotency

Sources can arrive out of order. A late older batch must not overwrite newer state in the target.

If SOURCE_VERSION increases monotonically, update only when the source version is newer:

~~~sql
MERGE INTO customer_status t
USING (
    SELECT customer_id,
           status,
           source_version
    FROM (
        SELECT s.customer_id,
               s.status,
               s.source_version,
               ROW_NUMBER() OVER (
                   PARTITION BY s.customer_id
                   ORDER BY s.source_version DESC,
                            s.stage_row_id DESC
               ) AS rn
        FROM customer_status_stage s
        WHERE s.batch_id = :p_batch_id
    )
    WHERE rn = 1
) s
ON (t.customer_id = s.customer_id)
WHEN MATCHED THEN
    UPDATE SET
        t.status = s.status,
        t.source_version = s.source_version
    WHERE s.source_version > t.source_version
WHEN NOT MATCHED THEN
    INSERT (customer_id, status, source_version)
    VALUES (s.customer_id, s.status, s.source_version);
~~~

The version condition prevents an older version from overwriting a newer one in the MATCHED branch. Version ordering must be guaranteed by the source system; do not treat unreliable client timestamps as absolute ordering if clocks can drift.

**Idempotent** in this context means re-running the same batch/source creates no duplicate records and causes no unintended target state changes beyond the defined rules. Supporting conditions include a UNIQUE target key, one source row per key, stable version selection rules, and clear batch identifiers.

You can avoid unnecessary updates when values have not changed:

~~~sql
MERGE INTO customer_status t
USING customer_status_source s
ON (t.customer_id = s.customer_id)
WHEN MATCHED THEN
    UPDATE SET
        t.status = s.status,
        t.credit_limit = s.credit_limit
    WHERE DECODE(t.status, s.status, 0, 1) = 1
       OR DECODE(t.credit_limit, s.credit_limit, 0, 1) = 1
WHEN NOT MATCHED THEN
    INSERT (customer_id, status, credit_limit)
    VALUES (s.customer_id, s.status, s.credit_limit);
~~~

In Oracle, DECODE treats two NULLs as equivalent when comparing. This example demonstrates skipping updates when values already match; ensure proper column data types and comparison rules. You can replace this with explicit null-safe conditions.

## 14. Multiple Sessions Running MERGE Concurrently

MERGE does not replace constraints or concurrency-handling strategies.

For example, two sessions nearly simultaneously MERGE the same nonexistent CUSTOMER_ID. Both can start seeing no matching target row and both attempt to INSERT. A UNIQUE constraint protects integrity; one session may wait and then receive a unique violation if the other session already inserted.

Therefore:

- Always have a PRIMARY KEY/UNIQUE constraint for business keys that must be unique.
- Define how the application handles ORA-00001 during retries/concurrent upserts.
- After a contention error, you can re-read the target row and apply version rules in a new transaction.
- If serialization per key is needed, design explicit locking or batch orchestration.
- Never rely on an application "does it exist yet?" check as the final guarantee; state can change before INSERT runs.

If multiple batches run in parallel, partition by key so two workers never process the same business key concurrently when ordering matters.

## 15. Multi-Step Synchronization Pipeline

~~~text
External source / CDC / API
          |
          v
      STAGING
  keep raw data + batch_id
          |
          v
     VALIDATION
  - NULL keys?
  - duplicate keys?
  - conflicting data?
  - valid datatypes/domains?
          |
          +---- error ----> QUARANTINE / report
          |
          v
   SOURCE NORMALIZATION
  - ROW_NUMBER picks version
  - or GROUP BY aggregates
  - one row per target key
          |
          v
        MERGE
  - match by business key
  - update/insert by version
  - unique constraint protects target
          |
          v
        AUDIT
  - batch ID
  - source/selected row counts
  - insert/update counts
  - errors and runtime
~~~

The audit table can store BATCH_ID, source name, start/end times, raw row count, distinct key count, rows dropped due to duplicates or conflicts, insert/update counts if measured, status, and error codes. Do not log unnecessary sensitive data.

After source normalization, confirm there are no remaining duplicate keys by running GROUP BY on the final source query itself. If the source includes JOINs, check after the JOIN, not just on the raw staging table.

## 16. When Should History Be Used Instead of Picking One Latest Row?

If you need to preserve every state change, do not discard older rows with ROW_NUMBER. Design a history table with its own grain:

~~~sql
CREATE TABLE customer_status_history (
    event_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    status VARCHAR2(20 CHAR) NOT NULL,
    effective_at TIMESTAMP(6) WITH TIME ZONE NOT NULL,
    source_version NUMBER
);
~~~

Each event is a row. If current state is needed, create a query or view selecting the latest version.

| Need | Design |
|---|---|
| One current state per customer | MERGE from a one-row-per-key source |
| Keep every change event | INSERT history with unique event key |
| Reconstruct state at a point in time | History with effective time/version |
| Summarize multiple transactions | GROUP BY target key |
| Conflicts requiring human review | Quarantine, do not auto-pick a winner |

If data is an event log, each event has its own identity. Do not use CUSTOMER_ID as the unique key of event history because multiple events per customer are valid.

## 17. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Merging directly from staging with multiple rows per business key | One target row hit by multiple source rows; ORA-30926 | Normalize source first |
| Thinking ORDER BY in source decides the winner | Outcome depends on execution plan | ROW_NUMBER with tie-breaker |
| Using DISTINCT to remove all duplicate keys | Rows with differing values still remain | Pick by rule or GROUP BY |
| Using MAX per column to fetch latest row | Values may come from different source rows | ROW_NUMBER and take entire row |
| Duplicate source keys when target lacks the row | Multiple INSERTs; ORA-00001 or silent duplicates | Unique constraint and source normalization |
| Target lacks unique constraint | One business key can accumulate multiple target rows | PRIMARY KEY/UNIQUE |
| ON omits part of composite key | Cross-matches tenants/entities | Include full business key |
| Putting mutable status/filter into ON | Existing row treated as NOT MATCHED | Match identity in ON; place update filter in UPDATE branch |
| Key in ON is NULL | Equality does not match NULL | NOT NULL or null-safe key contract |
| Updating column used in ON | ORA-38104 | Design key-change as separate operation |
| Not handling two sessions merging the same key | INSERT race, ORA-00001 | Unique constraint, retry/serialize |
| Picking latest record without tie-breaker | Selected row unstable when timestamps match | Add unique event ID/sequence |
| Collapsing historical events into one row | Loss of business history | Separate current-state and history models |

## 18. Practice Exercises

Exercises use a dedicated lab schema or staging area; run DDL/DML only in authorized environments.

### Exercise 1 — Identify Duplicate Source Keys

Create staging with two rows sharing CUSTOMER_ID but having different STATUS values. Write GROUP BY/HAVING to find duplicate keys. Explain why DISTINCT does not eliminate both.

### Exercise 2 — Observe the MERGE Error

Create a target with one row CUSTOMER_ID = 10 and a source with two rows sharing that CUSTOMER_ID. Try MERGE updating the same target row. Observe the Oracle error and explain why both source rows match one target row. Do not use production data for testing.

### Exercise 3 — Source Duplicate When Target Lacks the Key

Use a target key that does not exist yet, keeping two source rows with the same key. Try MERGE with a unique constraint and explain the difference between a multi-update error and an insert unique violation.

### Exercise 4 — Pick the Winner with ROW_NUMBER

Add CHANGED_AT, SOURCE_VERSION, and STAGE_ROW_ID. Use ROW_NUMBER PARTITION BY CUSTOMER_ID ORDER BY CHANGED_AT DESC, SOURCE_VERSION DESC, STAGE_ROW_ID DESC. Verify the final source has at most one row per customer.

### Exercise 5 — Tie-Breaker

Create two source rows with identical CHANGED_AT and SOURCE_VERSION but different STAGE_ROW_ID. Run the winner-selection query multiple times. Explain why a unique stage_row_id makes ordering deterministic.

### Exercise 6 — Aggregate Deltas

Create multiple transaction rows for one ACCOUNT_ID. Use GROUP BY and SUM to produce one row per account, then MERGE the net delta. Compare with simply picking one row via ROW_NUMBER.

### Exercise 7 — Protect the Target

Find duplicates in the target, clean up data per lab rules, then add a UNIQUE constraint on the business key. Try inserting the same key twice to see the constraint protect every write path.

### Exercise 8 — The ON Condition

Write two MERGE statements: one placing status inside ON, the other keeping only the business key in ON and placing the update condition in UPDATE WHERE. Use a target row with status BLOCKED to observe the difference in MATCHED/NOT MATCHED.

### Exercise 9 — Idempotency and Version

Run the same batch twice. Then test a batch with an older SOURCE_VERSION than the target. Confirm the version condition prevents older data from overwriting newer data.

### Exercise 10 — Source Multiplied by JOIN

Create a customer with multiple attribute rows, JOIN staging with attributes, then check COUNT(*) per customer. Fix the source to preserve the right grain and explain why DISTINCT is not the default fix.

## 19. Checklist Before Running MERGE

- [ ] Define the grain of target and source.
- [ ] Include the full business key in ON.
- [ ] Check whether the source contains NULL keys.
- [ ] Count duplicate keys within the exact batch/source scope.
- [ ] If duplicates exist, determine whether they are copies, valid events, deltas, or conflicts.
- [ ] If picking a winner, use ROW_NUMBER with business ordering and a unique tie-breaker.
- [ ] If accumulating, GROUP BY the target key and use semantically valid aggregates.
- [ ] Check the source after the final JOIN, not only the initial staging table.
- [ ] Protect target keys with an appropriate PRIMARY KEY/UNIQUE constraint.
- [ ] Verify ON contains no filters that break entity matching and does not update ON columns.
- [ ] Define behavior when source does not match and multiple rows might INSERT.
- [ ] Have policies for ORA-30926, ORA-00001, and concurrent retries.
- [ ] If data is versioned, prevent older batches from overwriting newer batches.
- [ ] Maintain batch auditing, row counts, and quarantine workflows.
- [ ] Test re-running the same batch and two competing sessions in a lab schema.

## 20. Core Takeaways

- MERGE synchronizes source to target using ON; composite keys must reflect true business identity.
- Oracle forbids updating the same target row multiple times in one MERGE. Multiple source rows sharing a key matching one target row typically cause ORA-30926.
- If the target does not yet have the key while the source has multiple rows with that key, the INSERT branch attempts multiple inserts; a unique constraint raises ORA-00001.
- **ORDER BY in the source is not a winner-selection rule.** Use ROW_NUMBER with business criteria and a unique tie-breaker.
- Use GROUP BY when source rows are components to aggregate; never misuse MAX to fabricate a synthetic row.
- DISTINCT only removes rows identical across all SELECT expressions; it does not solve business key conflicts.
- Targets need PRIMARY KEY/UNIQUE constraints to enforce uniqueness across all write paths.
- ON should identify rows by a stable key; additional update filters belong in the UPDATE branch when appropriate.
- NULL does not equal NULL in standard equality comparisons; define nullable key policies explicitly.
- MERGE does not replace multi-session concurrency strategies; constraints, retries, or serialization are still needed.
- If every event must be preserved, use a history/event table with its own key instead of collapsing everything into one current row.
- Determinism comes from clear data rules, keys, and source selection, not from a MERGE statement happening to succeed once.

### Oracle Reference Documentation

- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/) — MERGE, analytic functions, ROW_NUMBER, joins, and constraints.
- [Oracle Database Error Messages](https://docs.oracle.com/en/database/) — ORA-30926, ORA-00001, and ORA-38104.
- [Oracle Database Concepts](https://docs.oracle.com/en/database/) — primary keys, unique constraints, transactions, and read consistency.
- [Oracle Database Data Warehousing Guide](https://docs.oracle.com/en/database/) — staging, data loading, and batch data processing.

MERGE syntax and specific error details can vary across Oracle releases and source query shapes. When deploying, consult the documentation for your exact version, verify duplicates on the final source query itself, and protect business keys with database constraints.
