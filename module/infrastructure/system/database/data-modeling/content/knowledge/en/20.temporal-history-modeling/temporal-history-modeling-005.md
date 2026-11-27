# Storing Attribute History and Relationship History

## 1. An Entity Can Change Attributes and Relationships at Different Cadences

In **DATABASE_DATA_MODELING**, a requirement to “view data at a point in the past” is only solved properly when you identify **what changed**: an attribute value of an entity, a relationship between entities, or both. This belongs to the **Time and History** chapter and connects directly to turning business requirements into verifiable entities, relationships, keys, constraints, indexes, and physical schemas.

Consider employee number **42**. HR needs to answer three questions:

- On **2026-02-15**, was the employee's grade **JUNIOR** or **SENIOR**?
- On that same date, **which department** did the employee belong to?
- On **2026-08-20**, what was the employee's grade, which department were they in, and were both values effective simultaneously at that point in time?

Suppose the confirmed business data is as follows:

| Attribute or Relationship | Effective Period | Value |
|---|---|---|
| Employee grade | [2026-01-01, 2026-07-01) | JUNIOR |
| Employee grade | [2026-07-01, unbounded) | SENIOR |
| Primary department assignment | [2026-01-01, 2026-04-01) | Department A |
| Primary department assignment | [2026-04-01, 2026-10-01) | Department B |
| Primary department assignment | [2026-10-01, unbounded) | Department C |

The employee does not change identity across these periods. **Grade** is a time-varying attribute. **Department membership** is a time-varying relationship between two entities. If you store only one employee row with the latest grade and department, the current data shows **SENIOR, Department C**, leaving no basis to answer questions about February or August.

This lesson explains how to design both kinds of history, how to combine them via **temporal joins**, how to avoid losing data on updates, and how to choose appropriate mechanisms across relational, document, graph, and analytical databases.

**Learning objectives:** after this lesson, learners can distinguish attribute history from relationship history; split versions by change cadence; choose keys and effective intervals; write “as-of” queries; preserve history integrity under concurrent updates; and recognize when to extend to bitemporal history.

## 2. What Is Attribute History?

**Attribute history** records the values that one or a group of attributes on an entity held during each period. Examples:

- An employee changes professional grade from JUNIOR to SENIOR.
- A product changes list price or warranty duration.
- A customer changes membership tier.
- A contract changes credit limit or billing cycle.
- An account transitions ACTIVE → SUSPENDED → ACTIVE.

For the employee entity, **employee_id = 42** remains a stable identifier. Grade history can consist of separate versions:

~~~text
employee_id = 42

[2026-01-01, 2026-07-01)  grade = JUNIOR
[2026-07-01, +∞)          grade = SENIOR
~~~

A version record typically includes:

| Component | Responsibility |
|---|---|
| **entity_id** | Identifies the logical entity being versioned |
| **version_id** | Unique identifier for a single version |
| **attribute value(s)** | Values effective in that version |
| **valid_from / valid_to** or **valid_period** | Business effective interval |
| **source_ref** | Source decision or supporting document |
| **recorded_at** | Timestamp when the version was written to the system, for observability |

**version_id** does not replace **entity_id**. Nor should auto-incrementing version numbers be used to infer effective dates: a decision can be entered early for the future or arrive late with retroactive effect.

### 2.1. Choosing the Granularity of Versioned Attributes

Not every attribute of an entity changes on the same cycle. Suppose an employee has **grade**, **contact address**, **payroll payment method**, and **profile photo**. If every photo update generated a full snapshot copying every field, history would bloat rapidly and produce many duplicate rows carrying no meaningful change to grade.

Three common patterns exist:

| Organization Pattern | Advantages | Trade-offs |
|---|---|---|
| **Full-entity versioning** | Easy to read a complete snapshot at date D if every change is captured | Large data duplication; unrelated attributes share one history |
| **Grouped-attribute versioning (shared rules)** | Preserves clear semantics, suits per-domain keys and constraints | Requires temporal joins to assemble a full-entity snapshot |
| **Per-attribute EAV/attribute-value** | Flexible when attributes are highly dynamic | Hard to enforce types, constraints, and multi-attribute atomic changes; complex queries |

Pragmatic rule: **group attributes that change and are confirmed together** into one version, and separate attributes with different lifecycles or integrity rules. For example, **grade_code** and **grade_allowance** can live in the same version if a grade decision always changes both together. Conversely, an employee's department is a **relationship to the Department entity** and should have its own model.

### 2.2. Historical Snapshots Differ from Change Logs

A version row stores **the value effective over an interval**. A change log recording **“who changed what value on which day”** helps auditing, but does not automatically replace an effective-time model when decisions arrive late or are scheduled for the future.

For example, SENIOR grade is approved on June 20 but **takes effect on July 1**. Using the approval date as the version boundary would corrupt late-June HR reports. Records must separate **effective date** from **system recording date** whenever the business requires it.

## 3. What Is Relationship History?

**Relationship history** records when a link between entities is effective. While attributes answer **“what values did the entity have?”**, relationships answer **“which other entities was it linked to, in what role, and during which period?”**

Examples:

- Which department did an employee belong to in March?
- Which account manager owned a customer when a contract was signed?
- Which categories did a product belong to when an order was finalized?
- Which permission groups did a user belong to on the day access was approved?
- Which projects did a member join, in what role, and at what allocation?
- Which legal entity owned a subsidiary during each period?

Suppose employee 42 transfers departments:

~~~text
Employee(42)
  ├── MEMBER_OF Department(A): [Jan 1, Apr 1)
  ├── MEMBER_OF Department(B): [Apr 1, Oct 1)
  └── MEMBER_OF Department(C): [Oct 1, +∞)
~~~

If the **employee** table only held **department_id = C**, links to A and B would be overwritten. Deleting the Employee–Department link row on every transfer likewise makes past queries impossible.

### 3.1. Relationships Also Have Attributes

An “employee participates in project” relationship can carry **project role**, **time allocation percentage**, and **participation period**. Those attributes belong to the **Employee–Project link**, not intrinsically to the employee or the project alone.

~~~text
Employee(42) --[PROJECT_MEMBER, role=Reviewer,
                 allocation=40%, valid=[Apr 1, Jul 1))--> Project(900)
~~~

If the role changes from Reviewer to Lead on July 1, the relationship version may need to split into two intervals. If the employee participates in both Project 900 and Project 901 simultaneously, those intervals may overlap because **the relationship key includes project_id**; never enforce a blind “one project per employee” constraint.

### 3.2. Relationships Can Be One-to-Many or Many-to-Many Over Time

For **primary department**, the rule may be **each employee has at most one primary department on any given day**. That constraint keys on **employee_id + assignment_kind=PRIMARY**.

For **projects**, an employee can participate in many projects simultaneously, yet cannot have two overlapping versions for **the same employee, same project, and same role category** if the business treats that as the same link.

Overlap-prevention keys must come from the question **“which two links actually compete with each other?”**, rather than applying one uniform rule to every relationship.

## 4. Entities, Relationships, and Versions in the Logical Model

To avoid cramming all changing information into a single table, structure the model as follows:

~~~mermaid
erDiagram
    EMPLOYEE ||--o{ EMPLOYEE_GRADE_HISTORY : "has grade history"
    EMPLOYEE ||--o{ EMPLOYEE_DEPARTMENT_HISTORY : "has assignment history"
    DEPARTMENT ||--o{ EMPLOYEE_DEPARTMENT_HISTORY : "assigned to"
    EMPLOYEE ||--o{ PROJECT_MEMBERSHIP_HISTORY : "participates in"
    PROJECT ||--o{ PROJECT_MEMBERSHIP_HISTORY : "has members"
    EMPLOYEE {
        bigint employee_id PK
        text employee_code UK
    }
    EMPLOYEE_GRADE_HISTORY {
        bigint grade_version_id PK
        bigint employee_id FK
        text grade_code
        daterange valid_period
    }
    DEPARTMENT {
        bigint department_id PK
        text department_name
    }
    EMPLOYEE_DEPARTMENT_HISTORY {
        bigint assignment_id PK
        bigint employee_id FK
        bigint department_id FK
        text assignment_kind
        daterange valid_period
    }
    PROJECT {
        bigint project_id PK
    }
    PROJECT_MEMBERSHIP_HISTORY {
        bigint membership_id PK
        bigint employee_id FK
        bigint project_id FK
        text project_role
        daterange valid_period
    }
~~~

This model separates:

- **Employee**: logical entity whose ID stays constant across grade and department changes.
- **EmployeeGradeHistory**: grade value versions, independent of any specific department.
- **EmployeeDepartmentHistory**: versions of a **relationship** between Employee and Department, with **assignment_kind** distinguishing primary from secondary assignments.
- **ProjectMembershipHistory**: a many-to-many relationship with its own lifecycle and link attributes.

At the physical schema level, we must choose primary keys for version records, foreign keys to parent entities, overlap rules, and indexes tailored to historical queries.

Never make Department part of Employee's identity. Transferring departments **does not create a new employee**.

## 5. Choosing Time Granularity and Interval Conventions

The example history tables use half-open date intervals:

~~~text
[valid_from, valid_to)

valid_from is inclusive.
valid_to is exclusive.
~~~

An assignment **[2026-01-01, 2026-04-01)** remains active through the end of March 31, and the next assignment **[2026-04-01, 2026-10-01)** begins on April 1. Adjacent intervals do not overlap.

If the domain uses **hours/minutes** (such as shift scheduling), replace **date/daterange** with **timestamptz/tstzrange** and standardize the business time zone. Never subtract “one final second” to approximate an exclusive bound, since timestamp precision can be finer than whole seconds.

**An unbounded upper limit** means no end date is currently known. For example, **[2026-10-01, +∞)** reflects the currently known ongoing assignment, not a permanent commitment.

Typical integrity rules include:

1. Intervals must be non-empty.
2. Start bounds must be explicit and inclusive.
3. End bounds, when present, must be exclusive; never create two versions both active at a transition boundary.
4. Within the same business scope, effective intervals must not intersect when rules allow at most one value.
5. Whether **gaps** are permitted must be specified separately. **Non-overlapping** does not imply **always having a value**.

**recorded_at** captures when information was entered, while **valid_period** defines when it takes effect. Any system needing both **“which value was true on date D?”** and **“what did the system believe about D on date K?”** requires a bitemporal model or a sufficiently rich event sequence; a single `recorded_at` timestamp on an updated row is not enough.

## 6. PostgreSQL Schema: Attribute History

Here is a runnable PostgreSQL example for a test database. We use **daterange** because employee grade assignments take effect by **calendar date**.

~~~sql
-- btree_gist provides equality operators for bigint/text in GiST.
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE employee (
    employee_id   bigint PRIMARY KEY,
    employee_code text NOT NULL UNIQUE
);

CREATE TABLE department (
    department_id   bigint PRIMARY KEY,
    department_name text NOT NULL
);

CREATE TABLE employee_grade_history (
    grade_version_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    employee_id      bigint NOT NULL
                     REFERENCES employee(employee_id),
    grade_code       text NOT NULL
                     CHECK (grade_code IN ('JUNIOR', 'MIDDLE', 'SENIOR')),
    valid_period     daterange NOT NULL,
    source_ref       text NOT NULL,
    recorded_at      timestamptz NOT NULL DEFAULT statement_timestamp(),

    CONSTRAINT ck_grade_valid_period
        CHECK (
            NOT isempty(valid_period)
            AND NOT lower_inf(valid_period)
            AND lower_inc(valid_period)
            AND NOT upper_inc(valid_period)
        ),

    CONSTRAINT ex_grade_one_at_a_time
        EXCLUDE USING gist (
            employee_id WITH =,
            valid_period WITH &&
        )
);
~~~

**Design rationale:**

- **employee_id** in Employee is the logical entity key.
- **grade_version_id** uniquely identifies each grade version record.
- **grade_code** can be replaced with a foreign key to a grade lookup table if grades carry managed metadata.
- **valid_period** defines the effective date range.
- **source_ref** references the authorizing HR decision.
- **recorded_at** records insertion time and **does not** automatically make the history bitemporal.
- **ex_grade_one_at_a_time** enforces **at most one grade** per employee on any given day. Two overlapping ranges for the same employee_id are rejected, even if grade_code is identical.

**EXCLUDE USING gist** prevents overlaps that **UNIQUE(employee_id, lower(valid_period))** cannot catch—two intervals with different start dates can still overlap.

Using a CHECK constraint for `grade_code` fits a small example. When grade catalogs evolve or are shared across modules, a reference table with a foreign key and its own validity rules is usually easier to govern.

## 7. PostgreSQL Schema: Employee–Department Relationship History

For department assignments, the relationship carries **assignment_kind**:

- **PRIMARY**: main department, at most one per employee on any day.
- **SECONDARY**: concurrent/dotted-line departments, allowed alongside the primary department and across multiple departments.

~~~sql
CREATE TABLE employee_department_history (
    assignment_id   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    employee_id     bigint NOT NULL REFERENCES employee(employee_id),
    department_id   bigint NOT NULL REFERENCES department(department_id),
    assignment_kind text NOT NULL
                    CHECK (assignment_kind IN ('PRIMARY', 'SECONDARY')),
    valid_period    daterange NOT NULL,
    decision_ref    text NOT NULL,
    recorded_at     timestamptz NOT NULL DEFAULT statement_timestamp(),

    CONSTRAINT ck_department_valid_period
        CHECK (
            NOT isempty(valid_period)
            AND NOT lower_inf(valid_period)
            AND lower_inc(valid_period)
            AND NOT upper_inc(valid_period)
        ),

    -- No two concurrent PRIMARY departments for the same employee.
    CONSTRAINT ex_one_primary_department
        EXCLUDE USING gist (
            employee_id WITH =,
            valid_period WITH &&
        )
        WHERE (assignment_kind = 'PRIMARY'),

    -- No duplicate overlapping records of the same relationship kind.
    CONSTRAINT ex_duplicate_department_membership
        EXCLUDE USING gist (
            employee_id WITH =,
            department_id WITH =,
            assignment_kind WITH =,
            valid_period WITH &&
        )
);
~~~

**Two exclusion constraints protect two distinct rules.** The first governs *competing primary departments* regardless of department_id. The second blocks overlapping versions of **the same employee + same department + same assignment kind**.

Without the first constraint, an employee could hold two active PRIMARY rows for different department_ids. With only the first constraint, identical SECONDARY links could accidentally be inserted multiple times.

The example allows an employee to be PRIMARY in Department B and SECONDARY in Department C during the same period. If company policy forbids **being both PRIMARY and SECONDARY in the same department on the same day**, add a corresponding invariant; the schema above does not forbid that because it treats the two assignment kinds as distinct roles.

Note that **forbidding overlaps** does not guarantee an employee always has a primary department. If business rules require continuous primary assignment throughout active employment, also check for **no gaps** against employment tenure.

## 8. Seeding Sample Data for Attributes and Relationships

~~~sql
INSERT INTO employee (employee_id, employee_code)
VALUES (42, 'E-0042');

INSERT INTO department (department_id, department_name)
VALUES
    (10, 'Department A'),
    (20, 'Department B'),
    (30, 'Department C');

INSERT INTO employee_grade_history (
    employee_id, grade_code, valid_period, source_ref
)
VALUES
(
    42, 'JUNIOR',
    daterange(DATE '2026-01-01', DATE '2026-07-01', '[)'),
    'HR-GRADE-001'
),
(
    42, 'SENIOR',
    daterange(DATE '2026-07-01', NULL, '[)'),
    'HR-GRADE-002'
);

INSERT INTO employee_department_history (
    employee_id, department_id, assignment_kind,
    valid_period, decision_ref
)
VALUES
(
    42, 10, 'PRIMARY',
    daterange(DATE '2026-01-01', DATE '2026-04-01', '[)'),
    'HR-DEPT-001'
),
(
    42, 20, 'PRIMARY',
    daterange(DATE '2026-04-01', DATE '2026-10-01', '[)'),
    'HR-DEPT-002'
),
(
    42, 30, 'PRIMARY',
    daterange(DATE '2026-10-01', NULL, '[)'),
    'HR-DEPT-003'
);
~~~

The assignment rows here are **versions of a relationship**, not copies of the employee. When switching from Department B to C, **employee_id = 42** stays 42. Department metadata continues to be managed independently in the Department table.

Based on the inserted intervals:

| Query Date | Grade | Primary Department |
|---|---|---|
| 2026-02-15 | JUNIOR | Department A |
| 2026-05-15 | JUNIOR | Department B |
| 2026-08-20 | SENIOR | Department B |
| 2026-10-20 | SENIOR | Department C |

Notice that **grade changed on July 1 while department did not**; department changed on April 1 and October 1 while grade did not. The two histories evolve independently, so combining grade and department into one unified history table would generate redundant versions or obscure what actually changed.

## 9. Querying Attribute History

### 9.1. Grade Effective on a Given Date

~~~sql
SELECT
    grade_version_id,
    grade_code,
    valid_period,
    source_ref
FROM employee_grade_history
WHERE employee_id = 42
  AND valid_period @> DATE '2026-08-20';
~~~

Result: **SENIOR**. PostgreSQL's **@>** operator returns true when the range on the left contains the date on the right.

When the one-grade-per-employee-per-day rule is enforced by an exclusion constraint, valid queries return at most one row. Zero rows may mean the employee had no grade yet on that date, had left the company, or historical records do not extend that far back. Never substitute the latest grade as a fallback.

### 9.2. Listing an Attribute's Timeline

~~~sql
SELECT
    grade_version_id,
    grade_code,
    lower(valid_period) AS valid_from,
    upper(valid_period) AS valid_to,
    source_ref
FROM employee_grade_history
WHERE employee_id = 42
ORDER BY lower(valid_period), grade_version_id;
~~~

In PostgreSQL, an unbounded upper limit causes **upper(valid_period)** to return NULL even though **valid_period** itself is not SQL NULL. The UI can display this as “no end date yet.”

Never use **ORDER BY grade_version_id DESC LIMIT 1** to determine “today's active grade” if the system allows pre-entering future-dated promotions.

## 10. Querying Relationship History

### 10.1. Primary Department on Date D

~~~sql
SELECT
    d.department_id,
    d.department_name,
    a.valid_period,
    a.decision_ref
FROM employee_department_history a
JOIN department d
  ON d.department_id = a.department_id
WHERE a.employee_id = 42
  AND a.assignment_kind = 'PRIMARY'
  AND a.valid_period @> DATE '2026-05-15';
~~~

Result: **Department B**. This queries the effective relationship rather than joining from a current **employee.department_id** column.

### 10.2. All Departments Ever Assigned

~~~sql
SELECT
    a.assignment_kind,
    d.department_name,
    lower(a.valid_period) AS valid_from,
    upper(a.valid_period) AS valid_to
FROM employee_department_history a
JOIN department d
  ON d.department_id = a.department_id
WHERE a.employee_id = 42
ORDER BY lower(a.valid_period), a.assignment_kind, d.department_name;
~~~

An employee may hold SECONDARY assignments overlapping PRIMARY assignments. Hence when building a **primary department timeline**, filtering **assignment_kind = 'PRIMARY'** is an essential part of query semantics.

### 10.3. Finding Employees in a Department on Date D

This queries the relationship in the reverse direction:

~~~sql
SELECT e.employee_id, e.employee_code
FROM employee_department_history a
JOIN employee e
  ON e.employee_id = a.employee_id
WHERE a.department_id = 20
  AND a.assignment_kind = 'PRIMARY'
  AND a.valid_period @> DATE '2026-08-20'
ORDER BY e.employee_id;
~~~

The result includes employee 42. For workloads frequently asking “which employees belonged to Department B on date D?”, an index on **department_id + valid_period** may be necessary; the index used to enforce one primary department per **employee_id** will not automatically optimize reverse lookups.

## 11. Temporal Join: Combining Attribute and Relationship History

To find **the grade and department active simultaneously on date D**, you cannot join every grade version with every department version and pick arbitrarily. You must filter **both tables for the same business date**.

~~~sql
SELECT
    e.employee_id,
    e.employee_code,
    g.grade_code,
    d.department_name
FROM employee e
JOIN employee_grade_history g
  ON g.employee_id = e.employee_id
JOIN employee_department_history a
  ON a.employee_id = e.employee_id
JOIN department d
  ON d.department_id = a.department_id
WHERE e.employee_id = 42
  AND a.assignment_kind = 'PRIMARY'
  AND g.valid_period @> DATE '2026-08-20'
  AND a.valid_period @> DATE '2026-08-20';
~~~

Expected result:

~~~text
employee_id | employee_code | grade_code | department_name
42          | E-0042        | SENIOR     | Department B
~~~

Omitting the temporal filter on either table can fabricate combinations like **“SENIOR, Department A”** even though those two values were never active together.

### 11.1. Merging Two Timelines into Jointly Valid Slices

To reconstruct the full combined grade + department history, you cannot simply concatenate start dates or take a Cartesian product; you must compute the **intersection of the two intervals**.

PostgreSQL supports the **\*** operator to compute the intersection of two ranges after checking overlap with **&&**:

~~~sql
SELECT
    g.grade_code,
    d.department_name,
    g.valid_period * a.valid_period AS jointly_valid_period
FROM employee_grade_history g
JOIN employee_department_history a
  ON a.employee_id = g.employee_id
 AND a.assignment_kind = 'PRIMARY'
 AND g.valid_period && a.valid_period
JOIN department d
  ON d.department_id = a.department_id
WHERE g.employee_id = 42
ORDER BY lower(g.valid_period * a.valid_period);
~~~

Result on sample data:

| Grade | Primary Department | Jointly Effective Interval |
|---|---|---|
| JUNIOR | Department A | [2026-01-01, 2026-04-01) |
| JUNIOR | Department B | [2026-04-01, 2026-07-01) |
| SENIOR | Department B | [2026-07-01, 2026-10-01) |
| SENIOR | Department C | [2026-10-01, unbounded) |

This query produces **time-aligned slices** across two independent histories. It extends to more attributes and relationships, though intersections and row counts can grow quickly. Each time you add another history table, specify which attributes/relationships are mandatory at query time.

**Note on missing data:** an INNER JOIN only returns intervals where both grade and department have records. If June has a grade record but lacks a department assignment, June vanishes from the output. When the goal is spotting missing data, use gap queries or an appropriate point-in-time LEFT JOIN rather than treating missing rows as “no employee.”

### 11.2. Temporal Joins with Finalized Transactions

When an invoice, order, or document is finalized at time D, the attributes and relationships used in calculation can be looked up via temporal join. Yet if effective data is later adjusted retroactively, re-running that temporal join against the latest data may yield a different result than when the transaction closed.

Therefore, auditable transactional records should persist **the values or snapshot actually used at finalization**, along with references to the applied decision or version ID. Never let a dynamic join against current history silently change amounts or entitlements on already-issued documents.

## 12. Historical Many-to-Many Relationships and Link Attributes

Primary department assignment behaves like a **point-in-time one-to-many** relationship. By contrast, Employee–Project is **many-to-many**: one employee can join many projects, and one project has many employees.

~~~sql
CREATE TABLE project (
    project_id bigint PRIMARY KEY,
    project_name text NOT NULL
);

CREATE TABLE project_membership_history (
    membership_version_id bigint
        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    employee_id     bigint NOT NULL REFERENCES employee(employee_id),
    project_id      bigint NOT NULL REFERENCES project(project_id),
    project_role    text NOT NULL,
    allocation_pct  numeric(5, 2) NOT NULL
                    CHECK (allocation_pct > 0 AND allocation_pct <= 100),
    valid_period    daterange NOT NULL,
    decision_ref    text NOT NULL,

    CONSTRAINT ck_membership_period
        CHECK (
            NOT isempty(valid_period)
            AND NOT lower_inf(valid_period)
            AND lower_inc(valid_period)
            AND NOT upper_inc(valid_period)
        ),

    CONSTRAINT ex_membership_version_nonoverlap
        EXCLUDE USING gist (
            employee_id WITH =,
            project_id WITH =,
            valid_period WITH &&
        )
);
~~~

The invariant here is **at most one assignment version per Employee–Project pair on any day**; each version includes both **project_role** and **allocation_pct**. The same employee can still belong to Project 900 and Project 901 concurrently because those rows differ in **project_id**.

If business rules allow holding **two parallel roles within the same project**, the business key must include a **role or assignment type** identifier rather than constraining strictly on Employee–Project.

A rule like “total project allocation for an employee never exceeds 100% on any day” is harder than non-overlap: intervals across different projects are allowed to intersect, yet **the sum of allocation_pct across each time slice** must stay ≤ 100. A single-row CHECK constraint cannot enforce a multi-row sum; it requires transactions/locking plus boundary-sweep validation or a dedicated enforcement mechanism.

### 12.1. Symmetric vs. Directed Relationships

Relationships such as **“owns,” “manages,” and “depends on”** are directed and have distinct roles. Junction tables must distinguish **from_entity_id** from **to_entity_id** or use explicit role-named foreign keys.

For symmetric relationships—such as “two accounts linked bidirectionally”—canonicalize the key pair so you do not accidentally store A–B and B–A as two independent links. Rules for **duplicate relationships over time** depend on symmetry/directionality, not timestamps alone.

## 13. Writing Changes: Closing the Old Interval and Opening the New One

Sample INSERTs illustrate static history; in practice, changes arrive continuously and concurrently. When transferring from Department A to B on **April 1**, the initial active state might be:

~~~text
Employee 42 — PRIMARY — Department A
[2026-01-01, +∞)
~~~

After the transfer, it must become:

~~~text
Employee 42 — PRIMARY — Department A
[2026-01-01, 2026-04-01)

Employee 42 — PRIMARY — Department B
[2026-04-01, +∞)
~~~

An illustrative transaction assuming **an initial state containing only an unbounded Department A row**, independent of the three-department sample data in section 8:

~~~sql
BEGIN;

-- Lock the parent entity to serialize changes for Employee 42.
SELECT employee_id
FROM employee
WHERE employee_id = 42
FOR UPDATE;

UPDATE employee_department_history
SET valid_period = daterange(
    lower(valid_period),
    DATE '2026-04-01',
    '[)'
)
WHERE employee_id = 42
  AND assignment_kind = 'PRIMARY'
  AND lower(valid_period) < DATE '2026-04-01'
  AND upper_inf(valid_period)
RETURNING assignment_id;

-- Application must verify UPDATE affected exactly one row.
-- Otherwise, ROLLBACK, re-read timeline, and handle conflict.

INSERT INTO employee_department_history (
    employee_id, department_id, assignment_kind,
    valid_period, decision_ref
)
VALUES (
    42, 20, 'PRIMARY',
    daterange(DATE '2026-04-01', NULL, '[)'),
    'HR-TRANSFER-APR'
);

COMMIT;
~~~

This pattern **only applies when it is verified that exactly one unbounded PRIMARY interval precedes the transfer date**. If future transfers are already scheduled, or the transfer lands inside a finite interval, **split the affected intervals** by explicit rules—never blindly truncate pre-scheduled decisions.

Both UPDATE and INSERT must execute in the **same transaction** to prevent closing the old department without inserting the new one. If INSERT fails on an exclusion constraint, the transaction must roll back. If UPDATE affects zero or multiple rows, application logic must never commit as if it succeeded.

### 13.1. Concurrency and Idempotency

Two concurrent transfer requests can read the same old history and propose two different target departments. Combine:

- **Entity-level locking**, such as `SELECT ... FOR UPDATE` on Employee before recomputing the timeline.
- **Database constraints** to prevent illegal final overlaps even if a write path has a bug.
- **Revisions or expected versions** to reject requests computed against stale history.
- **Idempotency keys** or unique HR decision IDs so retries do not duplicate history rows.
- **Conflict resolution rules** and affected-row checks; never blindly let “last request wins” define business truth.

Locking the Employee row can create contention if every attribute and relationship shares the exact same lock. At scale, use finer-grained locks or coordinator entities per **domain**, provided competing operations remain fully protected.

### 13.2. Append-Only Semantics and Error Correction

A valid-time version table often updates **valid_period** to close an open interval. If requirements mandate that every persisted record remain **strictly immutable**, complement the model with an **append-only event log**, database-managed system history, or bitemporal history rather than letting UPDATE overwrite prior knowledge states.

The event “department transfer decision approved” differs from “assignment effective from date X.” You can persist events as decision evidence while maintaining effective-interval tables as a read model, updating both through a consistent protocol.

## 14. Late Data, Retroactivity, and Two Time Axes

A change can take effect **before the date the system records it**. Example:

- July 1: employee physically moves to Department B.
- July 5: HR system receives the decision effective back to July 1.
- July 10: auditors ask, “on July 3, which department did the system record the employee as belonging to?”

If only the latest valid-time relationships are stored, the system can answer “Department B was effective on July 3 per current knowledge,” yet **cannot reliably answer** “on July 3, which department did the system think the employee belonged to?” Those are two different questions.

To separate them, a **bitemporal** model adds:

| Time Axis | Meaning |
|---|---|
| **valid_period** | Interval during which the relationship or attribute is valid in the business |
| **known_period / recorded_period** | Interval during which the system accepted that version as current knowledge |

Under retroactive edits, an old version and a new version may intersect in **valid_period**, while remaining disjoint in **known_period**. Bitemporal constraints therefore inspect both axes:

~~~sql
-- Constraint sketch for the corresponding bitemporal table:
EXCLUDE USING gist (
    employee_id WITH =,
    valid_period WITH &&,
    known_period WITH &&
)
~~~

For **relationship** history, keys must reflect relationship cardinality. For example, if at most one PRIMARY department is allowed per (business date, system knowledge time) pair, the constraint must cover employee_id, assignment_kind=PRIMARY, valid range, and known range—do not add department_id to the PRIMARY overlap check, or two different departments could still overlap.

A standalone **recorded_at** without **recorded_to** or preserved superseded versions is insufficient to query every historical knowledge state. Also distinguish application-generated **now()** from actual transaction commit time if audits require exact visibility timestamps.

## 15. Common Modeling Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Keeping only latest **employee.department_id** | Historical departments are lost | Effective-interval relationship table |
| Creating a new Employee row on every department transfer | Breaks stable identity; corrupts transaction links | One Employee ID, many relationship versions |
| Updating department without recording transfer date | Cannot answer “in which department on D?” | Add `valid_period` with clear date semantics |
| Using one snapshot table for all attributes and relationships | Versions multiply whenever unrelated fields change | Separate attribute/relationship groups by lifecycle |
| Putting UNIQUE solely on start date | Two intervals with different starts still overlap | Exclusion constraints or safe overlap checks |
| Preventing Employee–Project overlap on employee_id alone | Blocks employees from joining multiple projects | Scope constraints to the exact relationship pair |
| Constraining PRIMARY Employee–Department on both employee_id and department_id | Two different PRIMARY departments can overlap | Constrain PRIMARY separately per employee_id |
| Running INNER JOIN across histories without gap checks | Unmatched intervals disappear silently from reports | Check gaps and define missing-data presentation |
| Picking highest version ID as the value at D | Fails with future-dated and retroactive versions | Filter strictly by `valid_period` containing D |
| Overwriting history and using `recorded_at` as pseudo-bitemporal | Cannot reconstruct what was known at K | Store `known_period` or full event history |
| Enabling cascade delete from entity to history | Erases evidence required for retention | Explicit retention policies, foreign keys, and deletion workflows |
| Editing timeline and recalculating issued invoices | Mutates historical financial records | Snapshot finalized results; adjust via new business entries |

## 16. Indexing and Query Performance for History

Attribute history and relationship history have distinct access patterns:

| Common Query | Primary Lookup Dimensions | Optimization Direction |
|---|---|---|
| Grade of one employee at D | employee_id + grade.valid_period | GiST exclusion or tailored composite index |
| Primary department of one employee at D | employee_id + kind + assignment.valid_period | GiST on employee and range, leveraging partial constraints |
| List of employees in Department B at D | department_id + assignment.valid_period | Additional index on department/range for heavy workloads |
| All projects of an employee at D | employee_id + membership.valid_period | Index by employee and interval |
| Company-wide periodic reports | Date range + multi-table joins | Analytical warehouse, partitioning, query plan and stats tuning |
| High-volume current-state APIs | Many entities, current date | Synchronized current projection when justified |

Example secondary index for reverse lookups from department to employees:

~~~sql
CREATE INDEX ix_department_history_lookup
ON employee_department_history
USING gist (department_id, valid_period);
~~~

Because **btree_gist** is installed, PostgreSQL can build a GiST index combining **department_id** and **daterange**. You do not need to create every possible index upfront: measure real queries with **EXPLAIN (ANALYZE, BUFFERS)** and weigh write amplification on version inserts.

### 16.1. Current-State Tables and History Tables

For APIs serving current departments across millions of employees, an **employee_current_department** projection or cache can reduce range scans. If adopted, designate which history table or event stream is the **source of truth** and maintain updates or reconciliation checks against the projection.

A reconciliation check compares the projection against querying **valid_period contains current business date** from the history table. Never assume **the row with the largest valid_from** is current, as future-dated versions may already exist.

### 16.2. Partitioning and Retention

For very large history tables, partitioning or archiving helps. However, partitioning by recording time can place overlapping intervals for the same entity in **different partitions**. Never assume per-partition exclusion constraints enforce global uniqueness across partitions; verify against your PostgreSQL version and partition layout.

HR and access-control history often contains personal data, requiring read permissions, retention windows, anonymization, and deletion policies. Business **append-only** semantics do not mean personal data must be retained forever.

## 17. Attribute and Relationship History in Other Data Models

The same requirement—“which attributes/relationships were effective on date D?”—can be implemented across paradigms; the choice depends on invariant enforcement and query patterns.

### 17.1. Document Databases

Attribute and link versions can be stored as separate documents:

~~~json
{
  "employeeId": 42,
  "versionId": "grade-42-2026-07",
  "gradeCode": "SENIOR",
  "validFrom": "2026-07-01",
  "validTo": null,
  "sourceRef": "HR-GRADE-002"
}
~~~

~~~json
{
  "employeeId": 42,
  "departmentId": 20,
  "assignmentKind": "PRIMARY",
  "validFrom": "2026-04-01",
  "validTo": "2026-10-01",
  "decisionRef": "HR-DEPT-002"
}
~~~

Embedding all history inside a single Employee document risks unbounded document growth and heavy write amplification. A dedicated history collection is easier to paginate, index, and archive. However, document databases may lack schema-level overlap constraints; rely on multi-document transactions, entity-level logical locks, or conditional updates.

Do not pick a document store merely because history records “look like JSON.” What matters is preventing relationship history drift under concurrent writes and answering date-based queries reliably.

### 17.2. Graph Databases

Graphs typically represent Employee and Department as nodes and **MEMBER_OF** as edges. Because the **relationship** is time-bound, edges themselves must carry `valid_from`/`valid_to` or separate edge versions.

~~~text
(Employee:42)
  -[MEMBER_OF, PRIMARY, Jan 1..before Apr 1]-> (Department:A)
  -[MEMBER_OF, PRIMARY, Apr 1..before Oct 1]-> (Department:B)
  -[MEMBER_OF, PRIMARY, Oct 1..onward]-> (Department:C)
~~~

To determine organizational structure on date D, every traversed node and edge along the path must be filtered by D. Versioning only Employee node properties produces wrong answers whenever an employee changes departments.

In multi-hop graphs—such as **employee → team → department → legal entity**—you must also define path-level temporal semantics: whether all edges must hold simultaneously at D, or whether certain queries require a non-empty common intersection interval.

### 17.3. Analytical Warehouses and SCD Type 2

In analytical warehouses, **SCD Type 2** is the standard way to store dimension attribute versions, using **employee_sk**, **employee_id**, **grade_code**, **effective_from**, and **effective_to**. Transaction facts join to the dimension version active at the fact's business timestamp.

Employee–Department relationships can likewise be modeled with **effective-dated bridge tables** for many-to-many or role-bearing links. If facts join across two history tables without filtering on the same date D, reports can multiply rows and inflate metrics.

A warehouse loaded only nightly may **miss intermediate states** if the transactional source overwrites values during the day. Capturing history at the source or streaming full CDC/event changes is essential when reporting must trace every transition.

### 17.4. Event Stores and Audit Logs

Event stores persist domain events such as **GradePromoted** or **EmployeeTransferredToDepartment**, while projections materialize effective intervals for fast queries. This fits domains needing full causal traceability and replay, at the cost of managing ordering, idempotency, schema evolution, and retroactive amendments.

**Audit logs** record who performed which administrative or access action and when. Audit logs do not automatically provide **business effective intervals**; a log entry stating “changed department on July 5” does not reveal that the transfer took effect July 1 unless the payload records the effective date.

## 18. Migrating from a Current-State-Only Model

Suppose an organization previously stored only:

~~~text
employee(employee_id, grade_code, department_id, updated_at)
~~~

Now history is required. You cannot accurately deduce all past values solely from the current row. During migration, explicitly tag source, confidence, and historical horizon.

A practical migration plan:

1. **Confirm business questions:** from which point onward must grade and department history be answerable?
2. **Audit legacy sources:** HR decisions, contracts, input logs, reporting extracts; identify trusted sources for effective dates.
3. **Design history tables and keys:** separate entity IDs, attribute version IDs, and relationship assignment IDs.
4. **Evidence-based backfill:** if only the current value is known, do not project it backward across all past time; record the verified start date and decision source.
5. **Check overlaps/gaps** before enabling constraints; resolve conflicts per domain rules.
6. **Cut over write paths** through standard services/transactions, blocking direct column updates that bypass history tables.
7. **Reconcile** current values against as-of queries and alert on drift.
8. **Publish query horizon:** dates predating complete history must return “insufficient history,” never silently assume the entity did not exist.

If historical queries are needed during migration, you can dual-write new history tables and legacy projections under a consistent protocol. Note that **dual writes** across two services without a shared transaction require outbox, idempotency, retries, and reconciliation.

## 19. Test Matrix for Attributes, Relationships, and Temporal Joins

Use employee 42 data from section 8. Dates are business calendar dates, not UTC timestamps.

| Scenario | Query Date | Expected Outcome |
|---|---|---|
| Before all history starts | 2025-12-31 | No grade/assignment found |
| Start date of first grade version | 2026-01-01 | JUNIOR |
| Final day before grade change | 2026-06-30 | JUNIOR |
| Exact promotion boundary | 2026-07-01 | SENIOR |
| Final day in Department A | 2026-03-31 | PRIMARY in Department A |
| Exact transfer boundary to B | 2026-04-01 | PRIMARY in Department B |
| After grade change, before department change | 2026-08-20 | SENIOR, Department B |
| Exact transfer boundary to C | 2026-10-01 | SENIOR, Department C |
| Two different projects same day | Any permitted date | Both Project links coexist |
| Two overlapping PRIMARY departments | Any intersecting interval | Rejected by database |
| Overlapping PRIMARY and SECONDARY | A day in both | Valid if distinct scopes/rules allow |
| Empty interval | [2026-07-01, 2026-07-01) | Rejected by database |

Additional operational test cases:

- **Atomicity:** closing old assignment succeeds then inserting new assignment fails; entire transaction rolls back.
- **Concurrency:** two concurrent transfer requests for the same employee never commit overlapping primary departments.
- **Retry/idempotency:** replaying the same decision creates no duplicate history rows.
- **Future write:** entering next month's promotion does not alter today's active grade.
- **Retroactive correction:** either recorded-time reconstruction is verified, or valid-time-only limits are explicitly documented.
- **Temporal join:** every grade + department result corresponds to a date D inside both intervals.
- **Gap detection:** when grade exists but primary department is missing, never silently pair grade with an expired department.
- **Decision source:** every version traces to an authoritative document/decision.
- **Current-state reconciliation:** current projection matches the as-of slice within defined lag bounds.
- **Time zones/granularity:** when migrating from `date` to `timestamptz`, business-date semantics stay consistent.

## 20. Practice Exercise: Product Attribute History and Category History

An e-commerce platform needs:

> “Know the warranty period applied to a product on the order confirmation date; know which categories the product belonged to when sold; a product may belong to multiple categories simultaneously, yet may never have two different active warranty policies at the same time.”

Design the model:

1. **Product** is the stable entity keyed by **product_id**.
2. **ProductWarrantyHistory** stores **warranty_months** and **valid_period**, allowing at most one active warranty policy per product per day if required by business rules.
3. **ProductCategoryHistory** is the Product–Category link table with **valid_period**. One product can belong to multiple distinct categories simultaneously; prevent duplicates for the same Product–Category pair over overlapping periods.
4. **OrderLine** stores product, confirmation timestamp, applied warranty terms, and document fields that must be frozen.
5. Write an as-of query retrieving the warranty period at date D and active categories at D. Because multiple categories may match, aggregate categories before joining to OrderLine to avoid multiplying quantities or totals.
6. Test a case where a product changes warranty on July 1 yet changes categories on June 15. Identify the time slices during which both warranty policy and category set remain constant.
7. Suppose on August 10 a retroactive warranty decision takes effect back on July 1. Distinguish “what is the currently known policy for July 15?” from “when the order closed on July 16, which policy had the system recorded?” Specify additional requirements for recorded time or order-line snapshots.

**Evaluation criteria:** proper business keys per table; consistent half-open intervals; non-overlap enforced on warranty attributes; multiple concurrent categories permitted; date-D joins across both histories; preserved amounts, entitlements, and evidence on finalized orders.

## 21. Design Sign-Off Checklist

- **Entities:** do entity IDs stay stable across attribute and relationship changes?
- **Attribute history:** are attributes sharing change rules grouped sensibly without unnecessary full-entity snapshots?
- **Relationship history:** do link foreign keys and link attributes live on relationship tables rather than overwriting parent entities?
- **Business keys:** which scopes require temporal uniqueness, and which relationships permit concurrent records?
- **Effective intervals:** are `date` vs. `timestamp`, `[from, to)` bounds, start/end semantics, and gap rules clearly defined?
- **Constraints:** does the database block overlaps, empty ranges, and invalid relationship scopes under concurrent writes?
- **Write protocol:** are attribute transitions, relationship transfers, future schedules, interval splits, rollbacks, retries, and retroactive edits clearly specified?
- **Temporal joins:** are all history tables in a query filtered to **the same date D** or properly intersected?
- **Audit and bitemporal:** must we know **what the system had recorded at K**, or only the currently confirmed value effective at D?
- **Finalized records:** do orders/invoices persist actually applied values so history amendments do not silently alter past totals?
- **Performance and security:** are indexes for both entity-forward and relationship-reverse queries, retention, access control, and personal-data policies addressed?

**Core principle:** attributes changing over time produce **entity value history**; links between entities changing over time produce **relationship history**. Both histories must share clear temporal conventions while maintaining separate keys and invariants. Whenever combining them to explain the past, require all versions to be **simultaneously effective at the queried instant**. That keeps business semantics intact, queries verifiable, and schemas evolvable without distorting core system relationships.
