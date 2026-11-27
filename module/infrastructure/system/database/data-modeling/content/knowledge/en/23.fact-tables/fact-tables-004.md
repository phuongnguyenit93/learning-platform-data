# Factless Fact Tables for Modeling Participation and Coverage

**A factless fact table** is a type of **fact table** in analytical data modeling where **the mere existence of a row is the fact being recorded**. The table holds foreign keys to dimensions and may include a date, event ID, or traceability attributes, yet **does not need an additive numeric measure column such as revenue, quantity, or cost**. Analytical value comes from **counting rows** and, more importantly, comparing **what was expected or eligible to happen** against **what was actually recorded**.

For instance, a **(student, session)** record can state "the student attended this session" without needing to store **attendance_count = 1**. Another table records "the student was on the expected roster for the session." Analyzing the difference between the two tables reveals who **has not been recorded as attending** and attendance rates by course, session, or cohort.

This lesson belongs to the **Fact Tables** chapter of the **DATABASE_DATA_MODELING** module. It focuses on choosing the right *grain* (what one row represents), designing dimensions and constraints, computing rates with valid denominators, avoiding row multiplication in JOINs, and preserving historical meaning as data changes.

## 1. Why Can a Fact Table Have No Measures?

A typical fact table stores events with quantities:

~~~text
fact_order_line(
    order_key,
    product_key,
    customer_key,
    date_key,
    quantity,
    sales_amount_vnd
)
~~~

Each row is a **sales order line**, with measures that can be summed under appropriate rules. However, many business questions do not involve a monetary amount or raw quantity:

- Who **attended** which training session?
- Which customers **visited a store** on which days?
- Which employees were **assigned** to which projects?
- Which products were **listed** in which promotional campaigns?
- Which patients **showed up** for their appointments?
- Which accounts were **eligible to receive** a campaign, and which accounts responded?

The primary fact here is a **relationship or an occurrence**. At a defined grain, **row presence** generally means "the event/relationship occurred"; **row absence** does not automatically mean "did not occur," because data might still be uningested, out of scope, delayed, or canceled.

### 1.1. Distinguishing Stored Measures from Derived Measures

A table without measure columns can still yield analytical metrics:

~~~sql
SELECT COUNT(*) AS recorded_participations
FROM fact_attendance;
~~~

**COUNT(*)** is a measure **derived from row counts**. Being able to write `COUNT(*)` does not turn the table into a measure-bearing fact table. Conversely, if each row is a badge scan and one person scans three times, **COUNT(*) = 3 scans**, not **3 attendees**. What a count means depends on the grain.

### 1.2. How Factless Facts Differ from Dimensions and Ordinary Junction Tables

| Structure Type | Example Grain | Primary Purpose |
| --- | --- | --- |
| **Dimension** | One student or one historical version of a student | Describes attributes used for filtering/grouping such as department, cohort, location |
| **Measure-bearing fact** | One order line | Records quantities, amounts, durations, etc. |
| **Event factless fact** | One student actually attending one session | Records **occurrence/participation** |
| **Coverage factless fact** | One student expected/eligible to attend one session | Records the **opportunity or eligibility set** |
| **OLTP junction table** | One student enrolling in one course | Enforces transactional relationships and constraints; may serve as a **source** for analytical facts |

A transactional two-foreign-key table is **not automatically** a factless fact table. In an analytical warehouse, you must define **grain, time dimension, measurement purpose, loading rules, and history**. Two tables can have identical columns yet serve completely different purposes.

## 2. Two Key Types of Factless Facts

### 2.1. Event/Participation Fact: An Event That Occurred

An **event factless fact** records an occurrence or participation:

~~~text
fact_attendance(
    student_key,
    session_key
)
~~~

One row means "the student is recorded as **having attended** that session," assuming source processing stores only **one confirmed attendance record per pair**. The table supports:

- Counting participations by session or by course.
- Counting distinct students who attended at least one session.
- Viewing a student's session history.
- Checking participation within an activity sequence.

If the goal is to record **every badge scan**, the grain must be **one scan event** and requires **scan_event_id** (or source event key), scan timestamp, and event type; in that case, the student–session pair cannot be the unique key.

### 2.2. Coverage/Eligibility Fact: Conditions or Opportunities That Exist

A **coverage factless fact** describes the set where an event is **expected, permitted, or eligible to occur** under business rules:

~~~text
fact_expected_attendance(
    student_key,
    session_key
)
~~~

One row means "the student is on the **expected roster** for the session." This is **not** a record confirming presence.

Coverage provides the **denominator**:

- How many student–session participations were expected?
- Out of expected participations, how many attended?
- Which expected participations **have no attendance record yet**?
- Were any attendance records **outside the expected roster**?

With only the event table, you cannot distinguish someone who **did not attend** from someone who **was never on the roster**.

### 2.3. "Event" and "Coverage" Are Not Interchangeable Labels

| Question | Event Fact | Coverage Fact |
| --- | --- | --- |
| Does it record that the student showed up? | **Yes** | No |
| Was the student on the expected roster? | Insufficient | **Yes** |
| Count recorded participations | Count rows at the right grain | Cannot substitute |
| Compute participation rate in expected cohort | Must combine with coverage | Provides the denominator |
| Identify people without an event | Cannot define the target cohort | Serves as the baseline to match events against |

**Semantic note:** "eligible," "invited," "enrolled," "assigned," and "mandatory" are **different** rules. When building coverage, choose **one** definition and state its effective timestamp. Never use a generic name like **fact_coverage** and implicitly assume everyone in it was required to attend.

## 3. Running Example: Training Schedule and Attendance

A training center runs learning sessions. Business requirements for this example:

1. Each student has a business identifier **student_code**.
2. Each session has a **session_code**, belongs to a course, and has a scheduled date.
3. A student may appear on the expected roster for multiple sessions; a session may have multiple expected students.
4. **Coverage** is locked before the session starts: one row per **student–session** pair on the expected roster.
5. **Attendance** is confirmed after ingesting check-in data: **each student–session pair counts as at most one attendance**, even if the source records multiple badge scans.
6. Walk-in students outside the roster may attend. Those events are retained in the event data for auditing, but **are not automatically included in the expected cohort's rate**.
7. Canceled sessions, session transfers, excused absences, and late check-ins are excluded here. If required, add policies and redefine measurement scope.

### 3.1. Sample Data

**Student dimension:**

| student_key | student_code | student_name |
| ---: | --- | --- |
| 1 | S01 | An |
| 2 | S02 | Binh |
| 3 | S03 | Chi |
| 4 | S04 | Dung |

**Session dimension:**

| session_key | session_code | course_code | session_date |
| ---: | --- | --- | --- |
| 101 | T101 | C10 | 2026-11-19 |
| 102 | T102 | C10 | 2026-11-20 |
| 201 | T201 | C20 | 2026-11-21 |

**Expected roster (coverage):**

| student_key | session_key |
| ---: | ---: |
| 1 | 101 |
| 2 | 101 |
| 1 | 102 |
| 2 | 102 |
| 3 | 201 |

**Recorded attendance (event):**

| student_key | session_key |
| ---: | ---: |
| 1 | 101 |
| 2 | 101 |
| 1 | 102 |
| 3 | 201 |

There are **5 expected participations**, **4 recorded participations**, and pair **(S02, T102)** has no attendance event. Student **S04** has no rows in either fact: **you must not conclude S04 was absent**, because S04 was not on the expected roster in this example.

### 3.2. Grain Is the Most Critical Decision

| Table | One Row Represents | Natural Key at Grain |
| --- | --- | --- |
| **dim_student** | One student in the current simplified model scope | student_code |
| **dim_training_session** | One defined training session | session_code |
| **fact_expected_attendance** | One expected participation of a student in a session | (student_key, session_key) |
| **fact_attendance** | One confirmed attendance of a student in a session | (student_key, session_key) |

**Grain** must be locked down **before** choosing primary keys, JOINs, or metrics. In this example, the same student attending two sessions counts as **two participations**, not one unique person. Hence:

~~~text
COUNT(*) on fact_attendance                    = 4 participations
COUNT(DISTINCT student_key) on fact_attendance = 3 distinct students
~~~

Neither count is "more correct" until you know whether the question asks for **participations** or **distinct students**.

### 3.3. Star Schema Diagram with Two Factless Facts

~~~mermaid
erDiagram
    DIM_STUDENT ||--o{ FACT_EXPECTED_ATTENDANCE : "expected"
    DIM_TRAINING_SESSION ||--o{ FACT_EXPECTED_ATTENDANCE : "session roster"
    DIM_STUDENT ||--o{ FACT_ATTENDANCE : "attended"
    DIM_TRAINING_SESSION ||--o{ FACT_ATTENDANCE : "recorded"
    DIM_STUDENT {
        bigint student_key PK
        varchar student_code UK
        varchar student_name
    }
    DIM_TRAINING_SESSION {
        bigint session_key PK
        varchar session_code UK
        varchar course_code
        date session_date
    }
    FACT_EXPECTED_ATTENDANCE {
        bigint student_key PK, FK
        bigint session_key PK, FK
    }
    FACT_ATTENDANCE {
        bigint student_key PK, FK
        bigint session_key PK, FK
    }
~~~

Both facts share **conformed dimensions** with identical key semantics, enabling accurate comparison of the same student and the same session. In a larger analytical model, session dates might reference **dim_date**, courses might have **dim_course**, and students might have a historical dimension; such extensions do not change the fundamental grain of these two facts.

## 4. SQL Design: Storing Row Presence Instead of Measure Columns

The following example uses **PostgreSQL** and a minimal illustrative schema. It uses integer keys as dimension keys to keep focus on grain semantics, without implying every system must share this exact key structure.

### 4.1. Creating Dimensions and Both Facts

~~~sql
CREATE TABLE dim_student (
    student_key BIGINT PRIMARY KEY,
    student_code VARCHAR(20) NOT NULL UNIQUE,
    student_name VARCHAR(100) NOT NULL
);

CREATE TABLE dim_training_session (
    session_key BIGINT PRIMARY KEY,
    session_code VARCHAR(20) NOT NULL UNIQUE,
    course_code VARCHAR(20) NOT NULL,
    session_date DATE NOT NULL
);

-- Coverage: one expected student participation in a session.
CREATE TABLE fact_expected_attendance (
    student_key BIGINT NOT NULL
        REFERENCES dim_student(student_key),
    session_key BIGINT NOT NULL
        REFERENCES dim_training_session(session_key),
    PRIMARY KEY (student_key, session_key)
);

-- Event: one recorded attendance in a session.
CREATE TABLE fact_attendance (
    student_key BIGINT NOT NULL
        REFERENCES dim_student(student_key),
    session_key BIGINT NOT NULL
        REFERENCES dim_training_session(session_key),
    PRIMARY KEY (student_key, session_key)
);
~~~

Neither fact has an `attendance_count`, `eligible_count`, or `amount` column. Each row records one fact at its exact grain:

- **PRIMARY KEY (student_key, session_key)** prevents duplicate pairs within each fact.
- **FOREIGN KEY** validates that referenced dimension members exist.
- We omit a **FOREIGN KEY fact_attendance → fact_expected_attendance** in this example because we need to **observe walk-in attendances outside the roster** for auditing; if the business strictly forbids walk-ins, constraints and write paths must be designed differently.
- The two facts have **no parent–child relationship**; they are two peer fact sets to be compared.

### 4.2. Loading Sample Data

~~~sql
INSERT INTO dim_student
    (student_key, student_code, student_name)
VALUES
    (1, 'S01', 'An'),
    (2, 'S02', 'Binh'),
    (3, 'S03', 'Chi'),
    (4, 'S04', 'Dung');

INSERT INTO dim_training_session
    (session_key, session_code, course_code, session_date)
VALUES
    (101, 'T101', 'C10', DATE '2026-11-19'),
    (102, 'T102', 'C10', DATE '2026-11-20'),
    (201, 'T201', 'C20', DATE '2026-11-21');

INSERT INTO fact_expected_attendance
    (student_key, session_key)
VALUES
    (1, 101),
    (2, 101),
    (1, 102),
    (2, 102),
    (3, 201);

INSERT INTO fact_attendance
    (student_key, session_key)
VALUES
    (1, 101),
    (2, 101),
    (1, 102),
    (3, 201);
~~~

Queries in the following sections use this dataset, assuming no subsequent edits or extra events.

## 5. Counting Participation, Counting People, and Computing Rates

### 5.1. Counting Rows at the Right Grain

~~~sql
SELECT COUNT(*) AS expected_participations
FROM fact_expected_attendance;
-- 5

SELECT COUNT(*) AS recorded_participations
FROM fact_attendance;
-- 4

SELECT COUNT(DISTINCT student_key) AS distinct_attendees
FROM fact_attendance;
-- 3
~~~

These three numbers answer **three different questions**. There are 5 **expected participations**, 4 **recorded participations**, and 3 **distinct students** who attended at least one session.

**Do not** subtract 3 from 4 to infer absent people. One student can attend multiple sessions, and the distinct expected student count can differ from expected participations.

### 5.2. Identifying Missing Attendance Records: LEFT JOIN

The target cohort starts from **coverage**:

~~~sql
SELECT
    st.student_code,
    st.student_name,
    ts.session_code,
    ts.course_code,
    ts.session_date
FROM fact_expected_attendance AS expected
JOIN dim_student AS st
  ON st.student_key = expected.student_key
JOIN dim_training_session AS ts
  ON ts.session_key = expected.session_key
LEFT JOIN fact_attendance AS attended
  ON attended.student_key = expected.student_key
 AND attended.session_key = expected.session_key
WHERE attended.student_key IS NULL
ORDER BY ts.session_date, st.student_code;
~~~

The single result from the sample:

| student_code | session_code | course_code | session_date |
| --- | --- | --- | --- |
| S02 | T102 | C10 | 2026-11-20 |

This is a **participation without a recorded attendance event**. Only after confirming that the attendance feed is completely ingested, the session has ended, and attendance policy rules are applied can the business formally classify this person as "absent."

If `fact_attendance` later receives a late-arriving check-in record, the query output automatically changes. If reports must preserve "absent **as known at 20:00 on Nov 20**," the model must also track **ingestion timestamps and report snapshots**.

### 5.3. Equivalent Expression Using NOT EXISTS

~~~sql
SELECT
    expected.student_key,
    expected.session_key
FROM fact_expected_attendance AS expected
WHERE NOT EXISTS (
    SELECT 1
    FROM fact_attendance AS attended
    WHERE attended.student_key = expected.student_key
      AND attended.session_key = expected.session_key
);
~~~

**NOT EXISTS** clearly expresses the set difference **coverage \ event** and avoids accidental row multiplication if joined to a multi-scan source. When the event table enforces its composite key, both approaches are valid. Choose whichever is readable, semantically sound, and verify its query plan on real data.

### 5.4. Participation Rates Must Have an Explicit Denominator

Let:

~~~text
C = set of expected (student_key, session_key) pairs
E = set of pairs with a recorded attendance event

In-scope attendance set: C ∩ E
Unrecorded within expected scope: C − E
Out-of-roster event set: E − C

Expected-cohort participation rate =
    |C ∩ E| / |C| × 100%
~~~

When **|C| = 0**, the rate is **undefined under this formula**, not 0% by default. Define a reporting rule for zero-denominator cases.

PostgreSQL query:

~~~sql
SELECT
    ts.course_code,
    COUNT(*) AS expected_participations,
    COUNT(attended.student_key) AS attended_in_coverage,
    ROUND(
        100.0 * COUNT(attended.student_key)
        / NULLIF(COUNT(*), 0),
        2
    ) AS attendance_rate_pct
FROM fact_expected_attendance AS expected
JOIN dim_training_session AS ts
  ON ts.session_key = expected.session_key
LEFT JOIN fact_attendance AS attended
  ON attended.student_key = expected.student_key
 AND attended.session_key = expected.session_key
GROUP BY ts.course_code
ORDER BY ts.course_code;
~~~

Results:

| course_code | expected_participations | attended_in_coverage | attendance_rate_pct |
| --- | ---: | ---: | ---: |
| C10 | 4 | 3 | 75.00 |
| C20 | 1 | 1 | 100.00 |

Across the entire sample, **4/5 = 80%** of expected participations were recorded.

Here **COUNT(*)** is valid for the denominator because the query starts from **coverage rows** and joins only to **uniquely keyed dimensions**, while **fact_attendance** is also uniquely keyed on the same pair. **COUNT(attended.student_key)** counts matched event rows, ignoring NULLs from the LEFT JOIN.

Replacing **COUNT(attended.student_key)** with **COUNT(*)** would count every unmatched expected row once too, inflating the rate to a **false 100%**.

### 5.5. Want to Display Sessions with Zero Expected Students?

The query above groups from coverage, so it **omits sessions that have no expected roster at all**. To report every session (including zero denominators), start from the **session dimension**:

~~~sql
SELECT
    ts.session_code,
    COUNT(expected.student_key) AS expected_count,
    COUNT(attended.student_key) AS attended_in_coverage,
    ROUND(
        100.0 * COUNT(attended.student_key)
        / NULLIF(COUNT(expected.student_key), 0),
        2
    ) AS attendance_rate_pct
FROM dim_training_session AS ts
LEFT JOIN fact_expected_attendance AS expected
  ON expected.session_key = ts.session_key
LEFT JOIN fact_attendance AS attended
  ON attended.student_key = expected.student_key
 AND attended.session_key = expected.session_key
GROUP BY ts.session_code
ORDER BY ts.session_code;
~~~

For a session without coverage: **expected_count = 0**, **attended_in_coverage = 0**, and **attendance_rate_pct = NULL**. That is intentional: there is no denominator to compute a rate. To exclude canceled or future sessions, filter by status/time provided by the dimension or source system.

## 6. Recording Participation Outside the Expected Scope

An event factless fact may contain rows absent from coverage—for example, auditing students, wrong-classroom check-ins, or unsynced rosters.

The set difference **event \ coverage** checks for them:

~~~sql
SELECT
    st.student_code,
    ts.session_code
FROM fact_attendance AS attended
JOIN dim_student AS st
  ON st.student_key = attended.student_key
JOIN dim_training_session AS ts
  ON ts.session_key = attended.session_key
LEFT JOIN fact_expected_attendance AS expected
  ON expected.student_key = attended.student_key
 AND expected.session_key = attended.session_key
WHERE expected.student_key IS NULL
ORDER BY ts.session_code, st.student_code;
~~~

On the initial sample data, this query returns no rows. You can test an out-of-roster case and roll it back:

~~~sql
BEGIN;

INSERT INTO fact_attendance (student_key, session_key)
VALUES (4, 101); -- S04 attended T101 without being in coverage

-- Re-run the out-of-roster check query above.
-- Result will contain (S04, T101).

ROLLBACK;
~~~

This row **should not automatically increment the numerator** of the "expected-cohort attendance rate" while the denominator stays unchanged. If walk-ins are allowed, report **unrostered attendances** separately; if forbidden, run an investigation/data-correction workflow. Automatically backfilling every event into coverage hides input discrepancies and distorts the denominator.

### 6.1. Distinguishing Similar-Looking Metrics

| Metric | Set Formula | Meaning |
| --- | --- | --- |
| **Expected participations** | \(|C|\) | Opportunity or obligation to attend |
| **Recorded participations** | \(|E|\) | Events across the entire dataset scope |
| **In-roster attendances** | \(|C \cap E|\) | Numerator for expected-cohort rate |
| **Unrecorded expected participations** | \(|C - E|\) | Missing events relative to the roster |
| **Out-of-roster participations** | \(|E - C|\) | Facts outside expected scope |
| **Students attending at least one session** | \(|\pi_{student}(E)|\) | Distinct people, not participations |

If a report simply labels a column **attendance_count** without stating grain and source set, readers can confuse participations, distinct people, and badge scans.

## 7. JOINs That Easily Corrupt Figures

### 7.1. CROSS JOINing Full Dimensions Is Not Coverage

From four students and three sessions in our example:

~~~sql
SELECT COUNT(*) AS possible_pairs
FROM dim_student AS st
CROSS JOIN dim_training_session AS ts;
-- 4 × 3 = 12
~~~

The result 12 is merely **all mathematically possible combinations**, **not** 12 expected participations. Coverage has **5** participations per the business roster. Treating 12 combinations as the denominator manufactures phantom "absences" that were never expected.

**Only use CROSS JOIN** to generate coverage when a verified rule states: **every entity in set A is eligible/required for every element in set B**, with scope, timing, and exceptions properly applied. For instance, every full-time employee at a branch must attend every mandatory safety session at that branch during the period—with terminations, exemptions, and cancellations handled.

### 7.2. Joining Through Multi-Version Dimensions Can Multiply Rows

Suppose a student is stored in a historical dimension with two versions:

~~~text
student_code = S01, version 1, department = A
student_code = S01, version 2, department = B
~~~

Joining the fact on **student_code** against both versions turns one attendance into **two output rows**. The right approach resolves which dimension version was effective at the fact's timestamp and joins via the **surrogate dimension key** or proper effective-interval predicates.

In the basic SQL example, **student_key** is unique in `dim_student`, so this risk does not occur. When adopting **Slowly Changing Dimension (SCD) Type 2**, join conditions and as-of mappings must be redesigned; you cannot simply insert new versions while keeping **UNIQUE(student_code)**.

### 7.3. Joining Two Facts Only on `session_key` Multiplies Participations

**Wrong:** joining `fact_expected_attendance` and `fact_attendance` **solely on `session_key`**:

~~~sql
-- Anti-pattern illustration; DO NOT use to count participations.
SELECT
    e.session_key,
    COUNT(*) AS joined_rows
FROM fact_expected_attendance AS e
JOIN fact_attendance AS a
  ON a.session_key = e.session_key
GROUP BY e.session_key;
~~~

In session T101, with **2 expected** and **2 attended**, joining solely on `session_key` yields **2 × 2 = 4 rows**, even though only 2 pairs match.

**Right:** join on the **full grain `(student_key, session_key)`** when comparing two facts. When facts involve more dimensions—such as session, student, cohort, and offering—match on the complete semantic key, not a subset of keys that merely look alike.

### 7.4. Avoid Relying on `COUNT(DISTINCT)` to Mask Grain Bugs

**COUNT(DISTINCT student_key)** is useful when asking for **distinct students**, but it is not a blanket fix for every multiplying JOIN. If one person is expected at 10 sessions, taking `DISTINCT` by `student_key` collapses 10 participations into 1 and breaks attendance metrics.

The first step is always **re-verifying grain and JOIN cardinality**, then choosing `COUNT(*)`, `COUNT(column)`, or `COUNT(DISTINCT ...)` to match the exact question.

## 8. Loading Data, Deduplicating, and Protecting Event Semantics

### 8.1. One Badge Scan Is Not Necessarily One Participation

The attendance source system may emit:

~~~text
event_001: S01 badged in for session T101 at 08:00
event_002: S01 badged in again for session T101 at 08:05
event_003: S02 badged in for session T101 at 08:01
event_004: S01 badged in for session T102 at 09:00
event_005: S03 badged in for session T201 at 14:00
~~~

There are **5 scan records** yet only **4 distinct student–session pairs**. If `fact_attendance` is defined as **one confirmed attendance**, you must deduplicate and apply source rules before loading. If you also want to analyze scan counts, create a **separate event fact** at the individual scan grain.

A staging table can preserve raw source events intact:

~~~sql
CREATE TABLE staging_attendance_scan (
    source_event_id VARCHAR(30) PRIMARY KEY,
    student_code VARCHAR(20) NOT NULL,
    session_code VARCHAR(20) NOT NULL,
    scanned_at TIMESTAMPTZ NOT NULL
);

INSERT INTO staging_attendance_scan
    (source_event_id, student_code, session_code, scanned_at)
VALUES
    ('event_001', 'S01', 'T101', TIMESTAMPTZ '2026-11-19 08:00:00+07'),
    ('event_002', 'S01', 'T101', TIMESTAMPTZ '2026-11-19 08:05:00+07'),
    ('event_003', 'S02', 'T101', TIMESTAMPTZ '2026-11-19 08:01:00+07'),
    ('event_004', 'S01', 'T102', TIMESTAMPTZ '2026-11-20 09:00:00+07'),
    ('event_005', 'S03', 'T201', TIMESTAMPTZ '2026-11-21 14:00:00+07');
~~~

Once the business confirms these scans constitute valid evidence of attendance, load the fact:

~~~sql
INSERT INTO fact_attendance (student_key, session_key)
SELECT DISTINCT
    st.student_key,
    ts.session_key
FROM staging_attendance_scan AS scan
JOIN dim_student AS st
  ON st.student_code = scan.student_code
JOIN dim_training_session AS ts
  ON ts.session_code = scan.session_code
ON CONFLICT (student_key, session_key) DO NOTHING;
~~~

The SQL uses **DISTINCT** to aggregate from the **scan** grain to the **participation** grain, and **ON CONFLICT DO NOTHING** makes reloads idempotent on the composite key. On the sample data already loaded in Section 4, this statement inserts zero extra rows; the total remains 4.

However, **being loadable does not mean an event is valid**. Production systems must check allowed check-in windows, authorized scanners, cancellations, manual overrides, faulty devices, and minimum-duration attendance rules. **DISTINCT** does not replace those business validations.

### 8.2. Keep Source Events for Auditing Without Losing Information

If scans matter for auditing or investigation, do not delete staging/raw events after building the factless fact. Separate:

~~~text
raw_scan_events:
    grain = one source event (source_event_id)

fact_attendance:
    grain = one student–session pair recognized as attended
~~~

A source data correction can change the factless fact's contents. You need a **rebuild/idempotent load** strategy that tracks rule versions and row lineage.

### 8.3. Unmapped Source Codes in Dimensions Must Be Handled

Example detecting scans with an unmapped **student_code**:

~~~sql
SELECT scan.source_event_id, scan.student_code
FROM staging_attendance_scan AS scan
LEFT JOIN dim_student AS st
  ON st.student_code = scan.student_code
WHERE st.student_key IS NULL;
~~~

If dimensions are missing, an INNER JOIN during load **silently drops unmatched events**. Production warehouses need **quarantine**, **late-arriving dimension**, or placeholder/unknown member policies—and must ensure that once missing dimensions arrive, facts can be reconciled and reprocessed.

Never map all unrecognized student codes to a single generic `student_key` and then run **COUNT(DISTINCT student_key)** to count people: distinct individuals would collapse into one. Treat mapping failures as data quality defects and surface them clearly.

### 8.4. Coverage Also Needs an Authoritative Source and Cutoff Time

Coverage sources may be enrollment lists or session assignments. A critical step is **defining when the roster freezes**:

- Roster locked **before start time**?
- Roster of everyone eligible **at end time**?
- Roster of anyone **ever invited**, including those who declined?
- Roster reconciled **after the session**, reflecting class transfers?

Different choices yield different denominators. To report rates against the **original expected cohort**, never silently overwrite historical coverage with **current** enrollments.

## 9. Time, Slowly Changing Dimensions, and Late-Arriving Data

### 9.1. When Did the Event Occur vs. When Was It Recorded?

An attendance may physically occur on Nov 19 while its log reaches the warehouse on Nov 21:

| Time Field | Example | Question |
| --- | --- | --- |
| **occurred_at** | 2026-11-19 08:00 +07 | When did the event actually take place? |
| **ingested_at** | 2026-11-21 02:00 +07 | When did the warehouse learn about the event? |
| **eligibility_as_of** | 2026-11-18 18:00 +07 | Which roster snapshot locked coverage? |

When analyzing "attendance rate of the Nov 19 session" after sync completes, group events by **occurred_at**. When analyzing "what the report published on the morning of Nov 20 knew," you also need **ingested_at** or historical report snapshots.

A **factless event** can store a date key or timestamp for querying and auditing. It remains factless as long as it has **no quantity/amount measure**; timestamps are contextual metadata for the event, not measures like revenue.

### 9.2. Snapshot Coverage vs. Effective-Interval Coverage

`fact_expected_attendance(student_key, session_key)` in our example describes **one locked roster per session**. If the business needs to know the expected roster at **multiple points in time**, there are two other strategies:

1. **Periodic coverage snapshot:** grain is **(snapshot_date_key, student_key, session_key)**, where each snapshot captures the expected cohort on that date; compare events strictly against the selected snapshot.
2. **Effective-interval coverage:** relationship records carry **valid_from/valid_to** with interval rules; queries retrieve the set effective **as-of** the analysis timestamp.

**Never sum `COUNT(*)` across all daily snapshots and call it total expected people.** One student can appear in 10 snapshots for the same session yet still represent **one expected participation** at any single cutoff.

### 9.3. Historical Dimensions Require Point-in-Time Keys

If a student transfers departments between semesters and reports require grouping by **department at the time of attendance**, an SCD Type 2 dimension can look like:

~~~text
student_key | student_code | department | valid_from | valid_to
------------+--------------+------------+------------+----------
1001        | S01          | Dept A     | ...        | ...
1002        | S01          | Dept B     | ...        | ...
~~~

When loading facts, resolve **student_code and event/coverage timestamp** to the exact historical **student_key**. When two facts are reconciled at the **same business grain**, align versioning rules so one side does not point to an old version while the other points to a new version, breaking the JOIN.

In large systems, you may need both a **stable student identity key** to link events across time and a **student SCD surrogate key** for historical attributes. That is an explicit modeling decision—simply converting a current dimension table to SCD Type 2 will not keep existing joins working automatically.

### 9.4. Dates, Timezones, and Session Status

A session starting at 23:30 UTC falls on a different calendar date in Vietnam. If reporting by **local date**, define the timezone for **session_date** and events. If a session is canceled, postponed, or rescheduled, locked coverage may need to be excluded from denominators or tracked as a separate status.

The rule "no event = absent" is meaningful only when **the session has finished**, relevant data feeds are completely synced, and the person genuinely belongs to the **mandatory-attendance cohort**.

## 10. Other Application Scenarios

| Domain | Event Factless Fact | Coverage Factless Fact | Analytical Question |
| --- | --- | --- | --- |
| **Training** | Student attended session | Student expected at session | Who has not been recorded attending? |
| **Marketing** | Customer received/engaged per definition | Customer targeted by campaign | How many targeted customers engaged? |
| **Retail promotions** | Product purchased under promo definition | Store–product in promo rollout scope | Which promoted combinations had zero sales? |
| **Healthcare** | Patient checked in for appointment | Confirmed, active scheduled appointment | What is the appointment show-up rate? |
| **HR** | Employee completed safety training | Employee required to complete course in period | Who lacks a valid completion record? |
| **Manufacturing** | Machine inspected in period | Machine required for inspection in period | Which equipment lacks inspection evidence? |

In each domain, **each coverage row expresses a distinct obligation or opportunity**. For instance, someone who **received an email** differs from someone **selected to receive an email**; "email sent" also differs from "user opened email." Define explicitly **which event** forms the numerator.

### 10.1. Promotion Example: Sales Opportunity vs. Actual Sales

Suppose promo scope is locked at grain:

~~~text
(promotion_key, store_key, product_key, date_key)
~~~

Each coverage row represents "this product was on promotion at this store on this date." Sales transactions sit at the **order-line** grain and carry **quantity** and **revenue**—so they are **measure-bearing facts**, not necessarily factless events.

To find promoted combinations that **sold zero units**, you can:

1. Start with coverage as the base set.
2. Bring sales transactions to the matching **promotion–store–product–date** grain via aggregation or **EXISTS**.
3. Use **NOT EXISTS** to find coverage combinations with no matching sales transaction.

Never join coverage rows directly to all sales lines and run `COUNT(*)` to count opportunities; a combination with 20 sales lines multiplies coverage 20-fold. Also verify that the sales transaction actually used that promotion rather than merely selling the same product on the same day.

### 10.2. Factless Facts Differ from Accumulating Snapshots

An **accumulating snapshot fact** typically has **one row per progressing process**, with milestone date columns like `ordered_date, shipped_date, delivered_date` updated as milestones complete. It answers **which stage a process is at and how long it took**.

A **factless event** records events that occurred at a chosen grain. A **coverage fact** records expected scope; comparing the two answers **whether evidence of occurrence exists**.

Choose based on the question:

- "Did the student attend the session?" → factless event.
- "Which students were expected yet did not attend?" → coverage paired with event.
- "How long did an order take from placement to delivery?" → accumulating snapshot or timestamped event fact, depending on the model.
- "How many minutes did an attendance session last?" → measure-bearing fact with `duration_minutes` or interval calculation from appropriate events.

Do not dump every purpose into a single table generically named **fact_events**.

## 11. Verifying Data Correctness Before Publishing Metrics

### 11.1. Invariants and Data Quality Checks

| Check | Example Rule | Action on Violation |
| --- | --- | --- |
| **Coverage grain** | At most one row per locked student–session | Primary key blocks duplicates; audit source roster logic |
| **Attendance grain** | At most one confirmed attendance row per student–session | Deduplicate multiple scans per confirmation rule |
| **Dimension references** | `student_key` and `session_key` must exist | Check foreign keys and unmapped source codes |
| **Check-in window** | Event must fall within policy-accepted window | Quarantine or apply approved exception handling |
| **Out-of-scope events** | Events outside coverage must be clearly identified | Report separately; never auto-promote into expected roster |
| **Canceled sessions** | Exclude canceled sessions from denominator if policy requires | Use session status and rule version |
| **Late-arriving data** | Reports specify whether retroactive updates are allowed | Record ingestion timestamps and restatement mechanism |
| **Rate never exceeds 100%** | Numerator must be **C ∩ E**, denominator is C | Never use global event counts when walk-ins exist |
| **Unrecorded definition** | Conclude absence only after sync/check-in deadline | Distinguish **unrecorded** from **confirmed absent** |

These constraints take multiple forms. **PRIMARY KEY** and **FOREIGN KEY** in SQL protect uniqueness and key existence; checking time windows, canceled sessions, exceptions, and lateness requires business logic or pipeline checks. A valid SQL schema does not guarantee data is ready for every metric.

### 11.2. Verifying Reconciliation Queries in SQL

On the sample data, these verification queries yield expected counts:

~~~sql
-- 5 participations in the expected roster.
SELECT COUNT(*) FROM fact_expected_attendance;

-- 4 recorded participations.
SELECT COUNT(*) FROM fact_attendance;

-- 1 expected participation without attendance.
SELECT COUNT(*)
FROM fact_expected_attendance AS expected
WHERE NOT EXISTS (
    SELECT 1
    FROM fact_attendance AS attended
    WHERE attended.student_key = expected.student_key
      AND attended.session_key = expected.session_key
);

-- 0 recorded participations outside the expected roster.
SELECT COUNT(*)
FROM fact_attendance AS attended
WHERE NOT EXISTS (
    SELECT 1
    FROM fact_expected_attendance AS expected
    WHERE expected.student_key = attended.student_key
      AND expected.session_key = attended.session_key
);
~~~

Expected results are **5, 4, 1, 0**, respectively. This is strictly a **check on the sample dataset**. In production systems, filter by course, date, status, and load-completion scope.

### 11.3. Do Not Take Simple Averages of Rates

In our sample:

~~~text
Course C10: 3 / 4 = 75%
Course C20: 1 / 1 = 100%
~~~

The simple average **(75% + 100%) / 2 = 87.5%** answers "average rate across two courses when **each course has equal weight**." It is **not** the attendance rate across all expected participations.

The pooled participation rate across expected participations is:

~~~text
(3 + 1) / (4 + 1) × 100% = 80%
~~~

For a pooled rate, **sum numerators and denominators before dividing**; never average rates when denominators differ. Also confirm whether the desired reporting unit is **participations**, **distinct people**, **sessions**, or **courses**.

### 11.4. Zero, NULL, and Missing Data Are Three Distinct Concepts

- **0 events after check-in closes:** may indicate zero recorded participation.
- **NULL rate when coverage is empty:** no meaningful denominator exists to calculate a rate.
- **Event data not yet ingested:** cannot yet conclude 0; requires pipeline status or watermark.
- **Canceled session:** do not default to 0%; usually excluded from the expected set or reported separately per policy.

Using **COALESCE(rate, 0)** everywhere can make reports look tidy while **equating "insufficient denominator" with "nobody attended."** Replace NULL with 0 only when the metric definition genuinely requires it.

## 12. Physical Design and Scalability

### 12.1. Primary Keys and Query-Driven Indexes

The primary key in the example is **(student_key, session_key)**, which favors looking up sessions attended by a given student. If common queries ask "how many people were expected / attended a session?", consider reverse-ordered indexes:

~~~sql
CREATE INDEX idx_expected_session_student
ON fact_expected_attendance (session_key, student_key);

CREATE INDEX idx_attendance_session_student
ON fact_attendance (session_key, student_key);
~~~

These two indexes help queries filtering by **session_key** and scanning pairs in **session–student** order under suitable conditions. They also increase storage and write overhead. **Never claim they will be faster** without inspecting data distribution, query plans, and actual workload.

When filtering frequently by **course_code**, the SQL in this lesson uses **dim_training_session** to map sessions to courses. Large analytical systems can split out **dim_course**, add appropriate foreign keys and indexes; never mechanically copy `course_code` into the fact without a clear need.

### 12.2. Partitioning, Time, and Snapshots

When an event table grows very large, consider partitioning by **event date key** or a date stored directly on the fact. In the illustrative design, however, the date resides only in **dim_training_session**; a SQL DBMS generally cannot partition a fact table directly by a column on a dimension table.

If you add **event_date_key** to the fact, define whether it means event occurrence date or session date, enforce consistency, and verify whether it changes the grain. When storing daily coverage snapshots, include **snapshot_date_key** as part of the grain rather than aggregating across snapshots arbitrarily.

### 12.3. Materialized Views and Precomputed Metrics

A dashboard may need faster query response than joining two large facts on every page load. You can create an aggregate table or **materialized view** at the **(course_key, reporting_date)** grain containing:

~~~text
expected_participations
attended_in_coverage
coverage_outliers
data_as_of_timestamp
~~~

This is a **measure-bearing summary fact table**, **derived** from the two source factless facts; it does not alter the nature of the two source tables. Retain recomputation rules and load-completion timestamps to explain why dashboard numbers can change after late-arriving events.

### 12.4. Avoid Counting by Creating Dummy Rows

There is no need to insert a row with **attendance = 0** for every student–session pair lacking an event. Doing so bloats data and, if expected scope is undefined, fabricates nonexistent "absences."

The factless model works naturally:

~~~text
EVENT ROW PRESENT       -> event recorded at grain
COVERAGE ROW PRESENT    -> within expected scope at grain
COVERAGE, NO EVENT      -> no event recorded yet within expected scope
NO COVERAGE             -> insufficient basis to conclude absence
~~~

If the business needs a **three-state attendance outcome** (present, excused absence, unexcused absence) or scores, model an explicit **attendance outcome/status**; do not force every outcome into presence/absence of an event row.

## 13. Process for Designing Factless Facts from Business Requirements

1. **Define the analytical question.** Are you counting participations, distinct people, or finding unfulfilled events in an expected cohort?
2. **Lock the grain in one exact sentence.** "One row is one student recorded attending one session" differs from "one row is one badge scan."
3. **Separate events from coverage.** Actual occurrences differ from cohorts invited, enrolled, eligible, or mandated.
4. **Confirm effective timestamps.** When did the event occur? When did coverage freeze? Do reports use local date or UTC?
5. **Select dimensions and keys.** Are dimensions conformed with shared semantics and historical versions? Are degenerate IDs needed for traceability?
6. **Add grain constraints.** Enforce uniqueness of key combinations per fact; handle unmapped dimension codes and duplicate source events.
7. **Design the pipeline.** Choose idempotent loading, grain-appropriate deduplication, and handling for late-arriving facts/dimensions.
8. **Define metrics.** Specify numerator, denominator, filters, completeness state, 0/NULL handling, and out-of-coverage items.
9. **Test with counterexamples.** Walk-in students; canceled sessions; double badge scans; late events; student department transfers.
10. **Optimize after correctness.** Evaluate indexes, partitions, aggregates, and workloads; keep clear source facts for recomputation and auditing.

### 13.1. Alignment Checklist Before Implementation

| Question | If Unclear, Leads To |
| --- | --- |
| Does one row represent an event or a unique participant? | Confusing scans, participations, and people |
| Who is included in coverage, and as of when? | Wrong denominators and phantom "absences" |
| Can valid events happen outside coverage? | Numerators exceeding denominators or lost exception data |
| What happens if a session is canceled or rescheduled? | Stale coverage, meaningless rates |
| When events arrive late, are reports restated? | Unexplained metric shifts |
| Do dimensions have multi-version history? | Row multiplication in JOINs or dropped matches |
| Can the source emit multiple events per participation? | Inflated attendance counts |
| Do we need to distinguish excused vs. unexcused absence? | Simple factless presence cannot express it |
| Who owns the definition of "valid attendance"? | Different teams computing different numbers |

## 14. Practice Exercises

### Exercise 1. Computing Metrics from Two Factless Sets

Suppose a workshop has expected roster and attendance records:

~~~text
Coverage (student, session):
(A, X1), (B, X1), (C, X1), (A, X2), (B, X2)

Event (student, session):
(A, X1), (C, X1), (A, X2), (D, X2)
~~~

**Tasks:**

1. Find expected participations, recorded events, and distinct event students.
2. Find **coverage − event** and **event − coverage**.
3. Calculate the participation rate **within coverage scope**.
4. Explain why **4 / 5 = 80%** should not be used as the expected-cohort participation rate.

<details>
<summary>Suggested solution for Exercise 1</summary>

- There are **5 expected participations**, **4 event participations**, and **3 distinct event students** (A, C, D).
- **Coverage − event = {(B,X1), (B,X2)}**: two unrecorded participations.
- **Event − coverage = {(D,X2)}**: one out-of-roster event.
- **Coverage ∩ event = {(A,X1), (C,X1), (A,X2)}**, so the true rate is **3/5 = 60%**.
- Using **4/5** lets the out-of-roster event **(D,X2)** inflate the numerator despite not belonging to the denominator, distorting the metric and masking scope definition issues.

</details>

### Exercise 2. One or Two Fact Tables?

A system mandates safety training for employees. Fields available:

~~~text
employee_id
course_id
assigned_at
completion_scan_id
completed_at
~~~

An employee can be assigned a course without having completed it yet; the completion scan source can emit two duplicate events for the same completion.

**Tasks:** propose grains for coverage and event, duplicate-prevention keys, and how to identify "incomplete." If employees must re-certify annually, what attribute must be added to the grain?

<details>
<summary>Suggested solution for Exercise 2</summary>

Coverage can use grain **(employee_id, course_id, required_period_id)**: one employee's obligation to complete a course in a period. Event shares the same grain if we only need to record **having completed validly at least once** in the period.

The scan source keeps the **completion_scan_id** grain, which may have multiple rows for the same obligation. After validating the event, load at most one event per grain key. **Incomplete** is **coverage − event** for periods past due / eligible for reconciliation.

If annual recertification is required, add the **compliance year/period** or a business-defined **assignment_instance_id**; never rely solely on `(employee_id, course_id)`, or last year's completion will be mistaken for next year's requirement.

</details>

### Exercise 3. Detecting Row Multiplication from a Bad JOIN

Session X has 3 expected students and 2 attending students, all events within coverage. The team joins both facts **solely on `session_key`**, then takes `COUNT(*)`.

**Tasks:** predict the joined row count, state the true attendance count, and propose a fix.

<details>
<summary>Suggested solution for Exercise 3</summary>

Joining on `session_key` produces **3 × 2 = 6 rows**, not 2 attendances. Join on **(student_key, session_key)** to match each participation individually, starting from coverage and LEFT JOINing events.

When both facts enforce pair uniqueness, **COUNT(attended.student_key) = 2**, **COUNT(expected.student_key) = 3**, and the rate is **2/3 ≈ 66.67%**.

</details>

### Exercise 4. Choosing a Semantically Valid Expected Set

A university has 10,000 students and 200 sessions in a semester, yet each student enrolls in only a subset of sessions. A report author uses **CROSS JOIN dim_student × dim_session** as coverage, then applies `NOT EXISTS` against attendance to find absences.

**Tasks:** explain why this is wrong, propose an appropriate coverage source, and explain how to handle late enrollments or section transfers.

<details>
<summary>Suggested solution for Exercise 4</summary>

**CROSS JOIN** generates 2,000,000 theoretical combinations, even though no business rule requires every student to attend every session. Most rows flagged as absent are **combinations never on any schedule**.

Coverage should come from the **enrolled student roster per session** at a defined cutoff and enrollment policy. For late enrollments and section transfers, specify what **as-of** snapshot time reports use, propagate changes to dimensions, and retain history if past metrics must be reproduced.

</details>

### Exercise 5. Late Data and Concluding Absence

Check-in for session T101 closes at 10:00 on Nov 19. At 11:00, the analytics warehouse has not yet received S02's scan, so the report shows **(S02, T101)** without an event. On Nov 21, S02's log is backfilled with **occurred_at** on Nov 19.

**Tasks:** what status is accurate at 11:00 on Nov 19 vs. in the recomputed report on Nov 21? What extra information must be retained to explain the change?

**Solution approach:** at 11:00 on Nov 19, given ingested data, S02 is **"not yet recorded,"** not necessarily truly absent. After ingesting the valid Nov 19 event, the updated reconciliation shows S02 attended. Retain **occurred_at**, **ingested_at**, coverage lock time, and pipeline completeness or report snapshots to explain why the two reports produced different figures.

## 15. Misconceptions to Avoid

| Misconception | Accurate Understanding |
| --- | --- |
| "No measure column means it's not a fact table." | Row presence at a defined grain is itself the fact; rows can be counted to produce derived measures. |
| "`COUNT(*)` always equals participant count." | It counts **rows at the grain**, which may be participations, scans, or relationships. |
| "No attendance row means definitely absent." | You must verify the person is in coverage, the session happened, and data finished loading. |
| "All subjects × all sessions equals coverage." | True only when the business genuinely mandates **every combination**. |
| "Only an event fact is needed to compute attendance rates." | You need a meaningful denominator, typically from a coverage fact. |
| "Out-of-coverage events are automatically invalid." | They may be walk-ins or roster errors; define policy before accepting or discarding. |
| "Joining two facts on the same date/session is enough." | Join on the **entire grain** to avoid multiplying rows. |
| "`COUNT(DISTINCT)` always fixes wrong counts." | `DISTINCT` can collapse distinct legitimate participations. |
| "If a dimension row exists, a fact row must exist." | Dimensions describe entities; facts only record defined occurrences. |
| "Current coverage works for all historical reports." | Expected scope changes over time; use appropriate as-of/snapshot points. |
| "Treating NULL as 0 makes dashboards more accurate." | NULL may mean **no denominator**, not a 0% rate. |
| "Course-level rate equals the average of individual course rates." | For a pooled participation rate, **sum numerators and denominators before dividing**. |

## 16. Takeaways

**A factless fact table** records a fact through **row existence**, usually without numeric measures. Two common patterns are:

- **Event/participation fact:** a recorded event or participation.
- **Coverage/eligibility fact:** an entity belonging to the expected, eligible, or opportunity set under explicit rules.

To find **who has not been recorded participating**, examine **coverage − event**, not all combinations across dimensions. To compute **participation rates**, the numerator is events **within coverage**, and the denominator is valid **coverage participations**; both sets must share grain, time anchor, and scope. Late-arriving events, roster changes, historical dimensions, and mis-keyed JOINs can alter figures without a single measure column existing.

Reliable design starts with **business definition → grain → dimensions/keys → events and coverage → pipeline/verification → metrics → physical optimization**. That is how factless facts accurately model participation or occurrence with clear meaning, clean reconciliation, and evolvability in an analytical system.
