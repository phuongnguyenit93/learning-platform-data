# Data Normalization and Identifying Functional Dependencies in PostgreSQL

## 1. Goal and Design Problem

A database might store data and answer current `SELECT` queries accurately while still being poorly designed. As data changes, the application starts running into situations such as:

- Updating an instructor's name in one row while forgetting to update hundreds of other rows.
- Being unable to add a new course until at least one student enrolls.
- Deleting the last enrollment accidentally wiping out course information.
- Two rows carrying the same course code yet different course titles.
- Not knowing which columns should carry `PRIMARY KEY`, `UNIQUE`, and `FOREIGN KEY` constraints.

**Data normalization** helps analyze the facts each table should represent, identify dependency rules among attributes, and decompose data into consistent relations. A core tool for this is the **functional dependency (FD)**.

This lesson walks from identifying FDs, finding keys, and computing attribute closures to **1NF, 2NF, 3NF, and BCNF**, then implements the tables in PostgreSQL and verifies the migration.

After completing this lesson, you will be able to:

1. Distinguish FDs determined by business rules from coincidences in existing sample data.
2. Find superkeys, candidate keys, primary keys, and attribute closures.
3. Identify partial dependencies, transitive dependencies, and insertion/update/deletion anomalies.
4. Decompose relations while evaluating **lossless join** and **dependency preservation**.
5. Use PostgreSQL constraints to enforce the identified business rules.
6. Analyze special cases: historical data, `NULL`, surrogate keys, and intentional denormalization.

`CREATE`, `INSERT`, and `UPDATE` statements are meant only for a **practice database** with appropriate privileges. Never run schema-altering statements in production without a migration plan, testing, and a rollback strategy.

## 2. One Table Combining Too Many Facts

Suppose a training center stores all course enrollments in a `registrations_raw` table:

| student_id | student_name | course_id | course_title | instructor_id | instructor_name | grade |
|---|---|---|---|---|---|---|
| 1 | An Nguyen | 101 | Databases | 9 | Ms. Lan | 8.50 |
| 2 | Binh Tran | 101 | Databases | 9 | Ms. Lan | 7.50 |
| 1 | An Nguyen | 102 | Algorithms | 10 | Mr. Minh | 9.00 |
| 2 | Binh Tran | 102 | Algorithms | 10 | Mr. Minh | *no grade yet* |

Each row contains information about **four distinct kinds of facts**:

- Student: ID and name.
- Course: code and title.
- Instructor: ID and name.
- Enrollment: which student takes which course and the corresponding grade.

Rules for this example:

1. Each student ID identifies one student and their current name.
2. Each course ID identifies one course title and one currently assigned instructor.
3. Each instructor ID identifies their current name.
4. A student takes many courses; a course has many students.
5. Within this simplified model, each student–course pair has one enrollment and at most one grade.

These are **business assumptions for this lesson**, not universal rules for every educational system. If there are multiple sections, multiple instructors, terms, or retakes, the keys and FDs must change accordingly.

### 2.1. Update Anomaly

Instructor 9 changes their name. If that name is repeated across 500 enrollment rows, all 500 rows must be updated. Missing even one row creates a contradiction:

```text
course_id = 101, instructor_id = 9, instructor_name = "Ms. Lan"
course_id = 101, instructor_id = 9, instructor_name = "Lan Thi Nguyen"
```

At that point, the table no longer holds a single consistent truth about the instructor's name.

### 2.2. Insertion Anomaly

The center wants to create course 103 before any student enrolls. If the design only has an enrollment table requiring `student_id`, there is no independent place to store the new course without inserting a dummy row.

### 2.3. Deletion Anomaly

The last student drops course 102, and the application deletes the last enrollment row. If that was the only place storing course details, the course title and assigned instructor are accidentally lost.

Normalization aims to reduce anomalies caused by **an attribute being placed in the wrong owning table**.

## 3. What Is a Functional Dependency?

### 3.1. Definition

Given a relation `R`, a set of attributes `X` **functionally determines** a set of attributes `Y` if, in **every valid data state**, any two tuples with identical values across all attributes in `X` must also have identical values across all attributes in `Y`.

Notation:

```text
X → Y
```

Examples under the assumptions in section 2:

```text
student_id → student_name

course_id → course_title
course_id → instructor_id

instructor_id → instructor_name

(student_id, course_id) → grade
```

Each `student_id` corresponds to one current name; each `course_id` corresponds to one course title and currently assigned instructor; the grade belongs to the **student–course pair**.

Written in set notation:

```text
{student_id, course_id} → {grade}
```

which has the exact same meaning as the parenthesized notation above.

### 3.2. What an FD Does Not Say

If `student_id → student_name`, two students with **different IDs can still have the same name**. An FD does not require the reverse direction:

```text
student_name → student_id
```

Similarly:

```text
course_id → course_title
```

does not imply `course_title → course_id`, because two different course IDs could share the same title.

A dependency `X → Y` does not mean `X` **causes** `Y`. It is a constraint on **unique value determination**, not a statement of causality.

### 3.3. Examples of Invalid FDs

The following FDs are **false** under this problem's rules:

```text
student_id → grade
course_id → grade
grade → student_id
instructor_name → instructor_id
```

A student has many grades; a course has many students with different grades; multiple people can share the same grade or the same name.

### 3.4. FDs Are Rules for Valid Data, Not Statistical Observations

Suppose currently only one student is enrolled in course 101. The sample data does not yet falsify:

```text
course_id → grade
```

Yet that FD is still invalid under business rules because later multiple students can take the same course with different grades.

SQL can find FD violations **in existing data**, but you cannot infer every FD that must hold in the future from a finite dataset alone. FDs must be confirmed from business rules, temporal semantics, and design constraints.

### 3.5. FDs and the Time Dimension

In a table storing only **current assignments**, `course_id → instructor_id` may hold. However, in a table storing history across multiple terms, course 101 may be taught by different instructors in different terms.

In that case, a more accurate FD might be:

```text
(course_id, term_id) → instructor_id
```

If there are multiple sections in the same term:

```text
(course_id, term_id, section_id) → instructor_id
```

If a student can retake a course:

```text
(student_id, course_id, term_id, attempt_no) → grade
```

Choosing the right **grain** (what event/entity a single row represents) and time scope is a prerequisite for writing FDs accurately.

## 4. Identifying FDs from Business Rules

Ask the question: **"If two rows share the same X, must every valid dataset require them to have the same Y?"**

| Hypothesis | Business Question to Ask | Under Current Model |
|---|---|---|
| `student_id → student_name` | Does each student ID have one current name? | Yes |
| `student_name → student_id` | Can two students share the same name? | Cannot be inferred |
| `course_id → course_title` | Does course ID determine course title? | Yes |
| `course_id → instructor_id` | Can one course code have multiple sections/instructors? | Yes in the simple model |
| `instructor_id → instructor_name` | Does instructor ID determine current name? | Yes |
| `instructor_id → course_id` | Can an instructor teach only one course? | No |
| `(student_id, course_id) → grade` | Can a student retake the same course? | Yes in the simple model |
| `email → student_id` | Is email always unique and never reused? | Insufficient information |

Practical approach:

1. List entities: Student, Course, Instructor, Enrollment.
2. List attributes for each entity.
3. Find natural or surrogate identifiers.
4. Identify attributes that only have meaning for a **relationship** (such as enrollment grade).
5. Check edge cases: name changes, course retakes, multiple instructors, historical data.
6. Write down the FDs that can be enforced via table structure or constraints.

Never pick an FD simply because a column name sounds "key-like". `postal_code`, `full_name`, `product_name`, or `phone_number` may not be unique and can change over time.

## 5. Superkeys, Candidate Keys, and Primary Keys

### 5.1. Superkey

An attribute set `K` is a **superkey** of relation `R` if it determines **all attributes of R**.

```text
K → R
```

In the registrations table:

```text
(student_id, course_id)
```

determines student name, course title, instructor ID, instructor name, and grade under the assumed FDs.

The set:

```text
(student_id, course_id, student_name)
```

is also a superkey, but contains a redundant attribute.

### 5.2. Candidate Key

A **candidate key** is a **minimal** superkey: removing any attribute from it means it no longer determines all attributes.

In our example:

```text
Candidate key: (student_id, course_id)
```

`student_id` alone does not determine course or grade; `course_id` alone does not determine student or grade. Both are required.

A relation can have **multiple candidate keys**. Therefore, you should not only inspect the primary key chosen in SQL while ignoring other candidate keys.

### 5.3. Primary Key and Alternate Keys

The **primary key** is the candidate key chosen as the main key in the schema. Remaining candidate keys can be represented using `UNIQUE` and `NOT NULL` as dictated by business rules.

```sql
CREATE TABLE example_students (
    student_id BIGINT PRIMARY KEY,
    student_code TEXT NOT NULL UNIQUE,
    student_name TEXT NOT NULL
);
```

If both `student_id` and `student_code` are truly non-duplicate identifiers, the table above represents two candidate keys; `student_id` is chosen as the primary key.

### 5.4. Prime and Non-Prime Attributes

A **prime attribute** appears in **at least one candidate key**. A **non-prime attribute** does not appear in any candidate key.

In the registrations relation:

```text
Prime:
  student_id, course_id

Non-prime:
  student_name, course_title,
  instructor_id, instructor_name, grade
```

The prime attribute concept is essential in the formal definition of **3NF**, especially when a relation has multiple overlapping candidate keys.

## 6. Attribute Closure: Finding Implied Attributes

### 6.1. Definition

The **attribute closure** of `X`, denoted `X⁺`, is the set of all attributes derivable from `X` under a set of FDs `F`.

Algorithm:

```text
closure := X

repeat:
    for each FD (A → B):
        if A is a subset of closure:
            add attributes in B to closure
until no new attributes are added

return closure
```

This is an **inference algorithm over a set of FD rules**, not an SQL query that automatically discovers business rules.

### 6.2. Computing the Closure of a Composite Key

Given:

```text
F1: student_id → student_name
F2: course_id → course_title
F3: course_id → instructor_id
F4: instructor_id → instructor_name
F5: (student_id, course_id) → grade
```

Start with:

```text
X = {student_id, course_id}
```

| Step | FD Applied | Attributes Added |
|---|---|---|
| 0 | Initial | `student_id`, `course_id` |
| 1 | F1 | `student_name` |
| 2 | F2 | `course_title` |
| 3 | F3 | `instructor_id` |
| 4 | F4 | `instructor_name` |
| 5 | F5 | `grade` |

Result:

```text
{student_id, course_id}⁺
 = {student_id, student_name,
    course_id, course_title,
    instructor_id, instructor_name, grade}
```

This set contains all attributes of the relation, so `(student_id, course_id)` is a superkey.

Continuing:

```text
{student_id}⁺
 = {student_id, student_name}

{course_id}⁺
 = {course_id, course_title,
    instructor_id, instructor_name}
```

No proper subset is a superkey, so the pair is a **candidate key**.

### 6.3. Using Closure to Check Derived FDs

To test whether `course_id → instructor_name` is implied, compute:

```text
{course_id}⁺
 = {course_id, course_title, instructor_id, instructor_name}
```

Because it contains `instructor_name`, we derive:

```text
course_id → instructor_name
```

even though that FD did not appear explicitly in the initial list.

## 7. FD Inference Rules

**Armstrong's axioms** form the foundation of FD inference.

### 7.1. Reflexivity

If `Y ⊆ X`, then `X → Y`.

```text
(student_id, course_id) → student_id
```

This is a **trivial** FD: the right-hand side is already contained in the left-hand side.

### 7.2. Augmentation

If `X → Y`, then `XZ → YZ`.

```text
student_id → student_name
```

implies:

```text
(student_id, course_id)
    → (student_name, course_id)
```

### 7.3. Transitivity

If `X → Y` and `Y → Z`, then `X → Z`.

```text
course_id → instructor_id
instructor_id → instructor_name
```

implies:

```text
course_id → instructor_name
```

### 7.4. Additional Derived Rules

- **Union:** `X → Y` and `X → Z` imply `X → YZ`.
- **Decomposition:** `X → YZ` implies `X → Y` and `X → Z`.
- **Pseudotransitivity:** `X → Y` and `WY → Z` imply `WX → Z`.

These rules help verify indirect dependencies, find keys, and spot redundant FDs.

### 7.5. Minimal Cover

A **minimal/canonical cover** is a compact representation of an FD set that preserves the exact same implied dependencies.

Common practical steps:

1. Split FDs with multiple attributes on the right-hand side into FDs with a **single attribute** on the right.
2. Remove extraneous attributes from the left-hand side.
3. Remove FDs derivable from the remaining FDs.

Example:

```text
course_id → course_title, instructor_id
```

is written as:

```text
course_id → course_title
course_id → instructor_id
```

A minimal cover makes 3NF synthesis algorithms easier to apply; a given FD set can have multiple equivalent minimal covers.

## 8. 1NF: Understanding Single-Valued Attributes Properly

**First Normal Form (1NF)** in the classic relational model requires attribute values to belong to an appropriate atomic data type domain, rather than replacing independent business relationships with a hard-to-constrain delimited list.

Example:

| student_id | student_name | course_ids |
|---|---|---|
| 1 | An Nguyen | `101,102,103` |
| 2 | Binh Tran | `101,102` |

Storing course codes in a comma-separated string causes problems:

- Hard to enforce an FK to each course ID.
- Hard to attach an individual grade or enrollment date to each course.
- Hard to search accurately for code `10` without accidentally matching `101`.
- Hard to prevent duplicate codes within the same list.

Instead, design:

```text
Students(student_id, student_name)
Enrollments(student_id, course_id)
```

| student_id | course_id |
|---|---|
| 1 | 101 |
| 1 | 102 |
| 1 | 103 |
| 2 | 101 |
| 2 | 102 |

### 8.1. PostgreSQL ARRAY/JSONB and 1NF

PostgreSQL provides valid `integer[]`, `text[]`, `jsonb`, and composite types. Do not simplistically declare **every array or JSON column wrong**.

The critical question is: do the elements need **independent identity, constraints, updates, JOINs, and lifecycles**?

- A list of enrolled courses with individual grades and FKs: use a junction table.
- Flexible metadata where each key is not a relational entity: `JSONB` can fit well.
- An independent tag set with its own rules: consider relational tables rather than arrays alone.

A table in 1NF can still contain **redundancy that causes anomalies**. The `registrations_raw` table in section 2 has a single value per cell yet fails higher normal forms.

## 9. 2NF: Eliminating Partial Dependencies on Composite Keys

A relation is in **2NF** when:

1. It is in 1NF.
2. Every **non-prime attribute** is fully functionally dependent on the candidate keys—not dependent on a **proper subset** of any candidate key.

A **partial dependency** occurs when `X → A`, where `X` is a proper subset of a candidate key and `A` is a non-prime attribute.

In `registrations_raw`, the candidate key is:

```text
(student_id, course_id)
```

Yet:

```text
student_id → student_name

course_id → course_title
course_id → instructor_id
```

Each FD above uses **only part** of the composite key to determine a non-key attribute. That is a 2NF violation.

### 9.1. Decomposing to Reach 2NF

Split into:

```text
Students(student_id, student_name)

Courses(
    course_id,
    course_title,
    instructor_id,
    instructor_name
)

Enrollments(student_id, course_id, grade)
```

In `Enrollments`, grade depends on the entire student–course pair. Student and course details are no longer repeated on every enrollment row.

However, `Courses` still has:

```text
course_id → instructor_id
instructor_id → instructor_name
```

This is a **transitive dependency** to resolve in 3NF.

### 9.2. A Single-Column Surrogate PK Does Not Fix Everything

Adding a column:

```sql
registration_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY
```

to the combined table does not eliminate `course_id → course_title` or `instructor_id → instructor_name`. An artificial ID identifies the row but **does not remove business redundancy**.

Checking 2NF/3NF must evaluate **all meaningful FDs**, not only the single PK chosen for an ORM.

## 10. 3NF: Eliminating Non-Key Dependencies

### 10.1. Intuitive Understanding

3NF is often summarized as:

> Non-key attributes depend on the key, the whole key, and nothing but the key (no transitive dependency on another non-key attribute).

This mnemonic is helpful for relations with one simple candidate key, though formal definitions are needed when handling multiple candidate keys.

### 10.2. Formal Definition

A relation is in **3NF** if, for every **non-trivial** FD `X → A` (with single attribute `A`), at least one condition holds:

1. `X` is a **superkey**; or
2. `A` is a **prime attribute** (part of at least one candidate key).

This definition matters because 3NF includes an exception for prime attributes that BCNF does not allow.

### 10.3. Violation in Courses

Consider:

```text
Courses(
    course_id,
    course_title,
    instructor_id,
    instructor_name
)
```

We have:

```text
course_id → course_title
course_id → instructor_id
instructor_id → instructor_name
```

Because one instructor can teach **many courses**, `instructor_id` is not a superkey of `Courses`; `instructor_name` is also not a prime attribute. The FD:

```text
instructor_id → instructor_name
```

violates 3NF.

Every time an instructor changes their name, multiple course rows must be updated. The fix is extracting instructors into a separate entity.

### 10.4. 3NF Schema After Decomposition

```text
Students(
    student_id PK,
    student_name
)

Instructors(
    instructor_id PK,
    instructor_name
)

Courses(
    course_id PK,
    course_title,
    instructor_id FK → Instructors
)

Enrollments(
    student_id FK → Students,
    course_id FK → Courses,
    grade,
    PK(student_id, course_id)
)
```

Diagram:

~~~mermaid
erDiagram
    STUDENTS ||--o{ ENROLLMENTS : registers
    COURSES ||--o{ ENROLLMENTS : contains
    INSTRUCTORS ||--o{ COURSES : teaches
    STUDENTS {
        bigint student_id PK
        text student_name
    }
    INSTRUCTORS {
        bigint instructor_id PK
        text instructor_name
    }
    COURSES {
        bigint course_id PK
        text course_title
        bigint instructor_id FK
    }
    ENROLLMENTS {
        bigint student_id PK
        bigint course_id PK
        numeric grade
    }
~~~

Each table owns **one clear scope of facts**:

- Rename a student: edit `Students`.
- Rename an instructor: edit `Instructors`.
- Change a course's assigned instructor: edit `Courses`.
- Update a student's grade: edit `Enrollments`.

Adding a course with no students yet is now possible without dummy enrollment rows. Deleting an enrollment does not delete the course or instructor.

## 11. BCNF: When Every Determinant Must Be a Superkey

### 11.1. Definition

**Boyce–Codd Normal Form (BCNF)** requires:

> For every non-trivial FD `X → Y`, the left-hand side `X` must be a **superkey**.

BCNF is **stronger** than 3NF:

```text
BCNF ⇒ 3NF
```

but a relation in 3NF is not guaranteed to be in BCNF.

### 11.2. Example: 3NF but Not BCNF

Relation:

```text
Teaching(student_id, course_id, instructor_id)
```

Assumptions within this model:

- A student takes a given course with **at most one instructor**.
- An instructor teaches **only one course**, though multiple instructors may teach that course.
- An instructor can teach many students.

FDs:

```text
(student_id, course_id) → instructor_id
instructor_id → course_id
```

From closures we find two candidate keys:

```text
(student_id, course_id)
(student_id, instructor_id)
```

All three—`student_id`, `course_id`, `instructor_id`—are **prime attributes**.

The FD:

```text
instructor_id → course_id
```

does not violate 3NF because `course_id` is prime. However, `instructor_id` is **not** a superkey (an instructor teaches many students), so it violates BCNF.

### 11.3. Decomposition and Trade-offs

We can decompose into:

```text
InstructorCourse(instructor_id, course_id)

StudentInstructor(student_id, instructor_id)
```

`instructor_id` is the key of `InstructorCourse`; `(student_id, instructor_id)` is the key of `StudentInstructor`.

This decomposition reconstructs `Teaching` via a JOIN on `instructor_id` and is **lossless** under the given FDs.

However, the original FD:

```text
(student_id, course_id) → instructor_id
```

may **no longer be preserved by local constraints** on the two tables. If a student signs up with two different instructors both teaching course 101, each table remains locally valid, yet joining them yields two instructors for the same student–course pair.

This illustrates why practical designs sometimes prefer a **dependency-preserving 3NF** over forcing every relation into BCNF at the cost of complex cross-table checks.

## 12. Lossless-Join Decomposition

### 12.1. Meaning

A decomposition of `R` into sub-relations is **lossless** under a set of FDs if joining the projections of **every valid state of R** reconstructs `R` exactly, **without losing rows or generating spurious tuples**.

Never split tables merely because it "looks cleaner".

### 12.2. Example of a Decomposition Producing Spurious Tuples

Given:

| A | B | C |
|---|---|---|
| a1 | b1 | c1 |
| a2 | b1 | c2 |

Split into:

```text
R1(A, B)
R2(B, C)
```

R1:

| A | B |
|---|---|
| a1 | b1 |
| a2 | b1 |

R2:

| B | C |
|---|---|
| b1 | c1 |
| b1 | c2 |

Joining on B produces:

```text
(a1, b1, c1)
(a1, b1, c2)  <-- spurious tuple
(a2, b1, c1)  <-- spurious tuple
(a2, b1, c2)
```

The middle two tuples were not in the original data. If B does not uniquely determine either side, this decomposition **can be lossy**.

### 12.3. Condition for Binary Decompositions

For two sub-relations `R1` and `R2`, the decomposition is lossless under the FDs if at least one FD is implied:

```text
(R1 ∩ R2) → R1
```

or:

```text
(R1 ∩ R2) → R2
```

Example:

```text
Courses(course_id, course_title, instructor_id, instructor_name)

R1(course_id, course_title, instructor_id)
R2(instructor_id, instructor_name)
```

Intersection:

```text
R1 ∩ R2 = {instructor_id}
```

Because `instructor_id → instructor_name`, the intersection determines all of `R2`: the decomposition is **lossless** under the assumed FDs.

This condition is based on **FD rules**, not merely checking once whether joining sample data happens to match the old row count.

## 13. Dependency Preservation

### 13.1. Two Distinct Goals

**Lossless join:** Does joining the child tables reconstruct the original relation accurately?

**Dependency preservation:** Can the original FDs be enforced by FDs/constraints **on individual child tables**, without needing a multi-table JOIN to check them?

In our 3NF example schema:

| Dependency | Enforcing Table |
|---|---|
| `student_id → student_name` | `Students` |
| `instructor_id → instructor_name` | `Instructors` |
| `course_id → course_title, instructor_id` | `Courses` |
| `(student_id, course_id) → grade` | `Enrollments` |

Every dependency has an appropriate owning table.

### 13.2. Relationship Between 3NF and BCNF

- A **3NF** synthesis algorithm from a minimal cover produces a decomposition that is both **lossless** and **dependency preserving** with respect to FDs.
- A **BCNF** decomposition can be made lossless, yet is **not guaranteed** to preserve all FDs through single-table constraints.
- A strong design does not just chase the highest normal form name; it weighs **enforceability of data invariants**.

PostgreSQL has no general SQL syntax like `ASSERT FUNCTIONAL DEPENDENCY X -> Y` to automatically enforce cross-table FDs. You express them via PK/UNIQUE/FK constraints, or design additional mechanisms for complex rules.

## 14. Creating a Normalized PostgreSQL Schema

Run only in a **lab database**, never against a production schema.

### 14.1. Creating the Schema

```sql
CREATE SCHEMA IF NOT EXISTS normalization_lab;
```

If the schema/tables already exist from a prior lab run, use a clean lab database or follow your cleanup process; do not delete data of unknown origin.

### 14.2. Students and Instructors Tables

```sql
CREATE TABLE normalization_lab.students (
    student_id BIGINT PRIMARY KEY,
    student_name TEXT NOT NULL
);

CREATE TABLE normalization_lab.instructors (
    instructor_id BIGINT PRIMARY KEY,
    instructor_name TEXT NOT NULL
);
```

The PKs guarantee that the same ID cannot appear in two rows with two different names.

This **does not forbid** two students from sharing the same name. If the school issues student codes, you can also declare `UNIQUE` on that code when business rules clearly define it.

### 14.3. Courses Table

```sql
CREATE TABLE normalization_lab.courses (
    course_id BIGINT PRIMARY KEY,
    course_title TEXT NOT NULL,
    instructor_id BIGINT NOT NULL,
    CONSTRAINT fk_courses_instructors
        FOREIGN KEY (instructor_id)
        REFERENCES normalization_lab.instructors(instructor_id)
);
```

Each `courses` row holds the course ID, title, and a **reference** to the instructor. There is no need to duplicate `instructor_name`: when needed, join to `instructors`.

### 14.4. Enrollments Table

```sql
CREATE TABLE normalization_lab.enrollments (
    student_id BIGINT NOT NULL,
    course_id BIGINT NOT NULL,
    grade NUMERIC(4,2),

    CONSTRAINT pk_enrollments
        PRIMARY KEY (student_id, course_id),

    CONSTRAINT fk_enrollments_students
        FOREIGN KEY (student_id)
        REFERENCES normalization_lab.students(student_id),

    CONSTRAINT fk_enrollments_courses
        FOREIGN KEY (course_id)
        REFERENCES normalization_lab.courses(course_id),

    CONSTRAINT chk_enrollments_grade
        CHECK (grade BETWEEN 0 AND 10)
);
```

The key `(student_id, course_id)` ensures each pair has **at most one enrollment row**. Two FKs guarantee valid student and course records.

`grade` allows `NULL` to represent **not yet graded**. In PostgreSQL, a `CHECK` condition evaluating to `TRUE` or `UNKNOWN` is not treated as a violation, so `NULL` remains permitted unless `NOT NULL` is added.

### 14.5. Loading Sample Data

```sql
INSERT INTO normalization_lab.students
    (student_id, student_name)
VALUES
    (1, 'An Nguyen'),
    (2, 'Binh Tran');

INSERT INTO normalization_lab.instructors
    (instructor_id, instructor_name)
VALUES
    (9, 'Ms. Lan'),
    (10, 'Mr. Minh');

INSERT INTO normalization_lab.courses
    (course_id, course_title, instructor_id)
VALUES
    (101, 'Databases', 9),
    (102, 'Algorithms', 10);

INSERT INTO normalization_lab.enrollments
    (student_id, course_id, grade)
VALUES
    (1, 101, 8.50),
    (2, 101, 7.50),
    (1, 102, 9.00),
    (2, 102, NULL);
```

Run these `INSERT` statements **once** on empty lab tables. Do not re-run the whole block if those IDs already exist.

### 14.6. Joining to Reconstruct the Original View

```sql
SELECT
    s.student_id,
    s.student_name,
    c.course_id,
    c.course_title,
    i.instructor_id,
    i.instructor_name,
    e.grade
FROM normalization_lab.enrollments AS e
JOIN normalization_lab.students AS s
  ON s.student_id = e.student_id
JOIN normalization_lab.courses AS c
  ON c.course_id = e.course_id
JOIN normalization_lab.instructors AS i
  ON i.instructor_id = c.instructor_id
ORDER BY s.student_id, c.course_id;
```

The output matches the four rows of the original flat table, while student/course/instructor details are now stored in **one place each**.

## 15. Testing Anomalies That Are Now Resolved

### 15.1. Updating an Instructor's Name Once

```sql
BEGIN;

UPDATE normalization_lab.instructors
SET instructor_name = 'Lan Thi Nguyen'
WHERE instructor_id = 9;

SELECT
    c.course_id,
    c.course_title,
    i.instructor_name
FROM normalization_lab.courses AS c
JOIN normalization_lab.instructors AS i
  ON i.instructor_id = c.instructor_id
WHERE i.instructor_id = 9;

ROLLBACK;
```

The updated display name comes from a single `instructors` record without touching any enrollment rows. `ROLLBACK` keeps the lab data intact for the next exercises.

### 15.2. Adding a Course Without Dummy Enrollments

```sql
BEGIN;

INSERT INTO normalization_lab.courses
    (course_id, course_title, instructor_id)
VALUES
    (103, 'Computer Networks', 9);

SELECT course_id, course_title
FROM normalization_lab.courses
WHERE course_id = 103;

ROLLBACK;
```

Course 103 can exist before any student enrolls. This solves the insertion anomaly.

### 15.3. Deleting an Enrollment Without Deleting the Course

```sql
BEGIN;

DELETE FROM normalization_lab.enrollments
WHERE student_id = 2 AND course_id = 102;

SELECT course_id, course_title
FROM normalization_lab.courses
WHERE course_id = 102;

ROLLBACK;
```

Course 102 remains intact in `courses` because it is an independent entity from the deleted enrollment.

### 15.4. Preventing Duplicate Business Keys

When pair `(1, 101)` already exists, running:

```sql
INSERT INTO normalization_lab.enrollments
    (student_id, course_id, grade)
VALUES (1, 101, 10.00);
```

violates the primary key. This constraint holds under concurrent writes across connections, unlike an application-side `SELECT COUNT(*)` prone to race conditions.

If updating a grade is intended, use a conditional `UPDATE` or an **explicitly defined** upsert policy—never `ON CONFLICT DO NOTHING` to silently discard important updates.

## 16. PostgreSQL Constraints and Functional Dependencies

### 16.1. PRIMARY KEY

`PRIMARY KEY` combines **uniqueness** and **non-nullability**. With `student_id` as the PK of `students`, two rows with the same ID and different names cannot exist, so:

```text
student_id → student_name
```

is backed by the schema.

### 16.2. UNIQUE and NULL

In PostgreSQL, `UNIQUE` by default allows **multiple NULLs** according to standard constraint semantics. For example:

```sql
CREATE TABLE example_contacts (
    contact_id BIGINT PRIMARY KEY,
    email TEXT UNIQUE
);
```

can still contain many rows with `email IS NULL`. If email is a mandatory identifier, use:

```sql
CREATE TABLE required_emails (
    contact_id BIGINT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE
);
```

In PostgreSQL 15+, you also have:

```sql
CREATE TABLE example_nulls_not_distinct (
    id BIGINT PRIMARY KEY,
    external_code TEXT,
    CONSTRAINT uq_external_code
        UNIQUE NULLS NOT DISTINCT (external_code)
);
```

This constraint treats `NULL` as **not distinct** for uniqueness, allowing at most one `NULL` in that column. Still, if every row must carry a code, add `NOT NULL`.

### 16.3. FOREIGN KEY

An FK:

```sql
FOREIGN KEY (instructor_id)
REFERENCES normalization_lab.instructors(instructor_id)
```

protects the existence of the referenced entity. It **does not require** `instructor_name` to live in `courses`.

If a legacy table still duplicates `instructor_name` alongside `instructor_id`, adding an FK does not automatically keep the duplicated name synced with the master table. Normalize away the redundant column or explicitly mark it as an **intentional historical snapshot**.

### 16.4. CHECK

```sql
CHECK (grade BETWEEN 0 AND 10)
```

evaluates an expression on the row, but is not a general mechanism for enforcing cross-row/cross-table FDs. PostgreSQL does not automatically re-check old rows whenever another table changes simply because a function querying another table is embedded in `CHECK`.

Prefer PK/UNIQUE/FK constraints, proper schema design, and controlled transactional mechanisms for more complex invariants.

### 16.5. Alternate Keys and Expression Indexes

Suppose business rules treat email as case-insensitive:

```sql
CREATE UNIQUE INDEX uq_students_email_normalized
ON normalization_lab.students (lower(email));
```

This is a **unique expression index**, valid only once the table has an `email` column. Do not run it before adding that column. It differs from a plain column `UNIQUE` constraint and has limitations if you want an FK to target it directly.

Email normalization, whitespace, collation, and reuse rules must be defined upfront. Never assume `lower(email)` is the right identity rule for every domain.

### 16.6. Surrogate Keys Do Not Replace Business Keys

A table may add `registration_id BIGINT GENERATED ... AS IDENTITY` for convenient referencing, yet if business rules still allow only one enrollment per student–course pair, you **still need**:

```sql
UNIQUE (student_id, course_id)
```

An artificial key does not erase FD rules, nor does it fix update anomalies when descriptive attributes remain duplicated.

## 17. Preparing a Source Table to Practice Migration

To inspect legacy data, create a separate raw table in the lab:

```sql
CREATE TABLE normalization_lab.registration_raw (
    student_id BIGINT NOT NULL,
    student_name TEXT NOT NULL,
    course_id BIGINT NOT NULL,
    course_title TEXT NOT NULL,
    instructor_id BIGINT NOT NULL,
    instructor_name TEXT NOT NULL,
    grade NUMERIC(4,2)
);

INSERT INTO normalization_lab.registration_raw VALUES
    (1, 'An Nguyen', 101, 'Databases', 9, 'Ms. Lan', 8.50),
    (2, 'Binh Tran', 101, 'Databases', 9, 'Ms. Lan', 7.50),
    (1, 'An Nguyen', 102, 'Algorithms', 10, 'Mr. Minh', 9.00),
    (2, 'Binh Tran', 102, 'Algorithms', 10, 'Mr. Minh', NULL);
```

In real systems, source data may already hold contradictions; **detect them before introducing new keys**. Never mistake clean exercise data for a guarantee that production databases are clean.

## 18. Detecting FD Violations with SQL

### 18.1. student_id → student_name

```sql
SELECT student_id,
       COUNT(DISTINCT student_name) AS name_variations
FROM normalization_lab.registration_raw
GROUP BY student_id
HAVING COUNT(DISTINCT student_name) > 1;
```

If any rows return, the same student ID is linked to multiple names. You must determine the authoritative name, effective dates, and data source.

`COUNT(DISTINCT ...)` **ignores SQL NULLs**. The lab dataset uses `student_name NOT NULL`; on nullable sources, add explicit checks for missing values rather than treating a count of 1 as absolute proof.

### 18.2. course_id → course_title, instructor_id

```sql
SELECT
    course_id,
    COUNT(DISTINCT course_title) AS title_variations,
    COUNT(DISTINCT instructor_id) AS instructor_variations
FROM normalization_lab.registration_raw
GROUP BY course_id
HAVING COUNT(DISTINCT course_title) > 1
    OR COUNT(DISTINCT instructor_id) > 1;
```

If a course has multiple instructors, first ask whether **the model is missing terms/sections** or whether the data was truly misentered. Never arbitrarily pick `MAX(instructor_id)` to hide inconsistencies.

### 18.3. instructor_id → instructor_name

```sql
SELECT instructor_id,
       COUNT(DISTINCT instructor_name) AS name_variations
FROM normalization_lab.registration_raw
GROUP BY instructor_id
HAVING COUNT(DISTINCT instructor_name) > 1;
```

If names change over time, you may need a current directory and a name-history table rather than assuming names are permanently immutable.

### 18.4. Duplicate Candidate Keys

```sql
SELECT student_id, course_id,
       COUNT(*) AS duplicate_rows
FROM normalization_lab.registration_raw
GROUP BY student_id, course_id
HAVING COUNT(*) > 1;
```

Duplicate pairs might be technical duplicate records or **legitimate course retakes**. Understand the root cause before imposing `PRIMARY KEY (student_id, course_id)`.

### 18.5. Interpreting Check Queries

These queries can **disprove** an FD when real violations are found, yet they cannot prove an FD holds for **all future states** without constraints and business confirmation.

## 19. Migrating from Raw to Normalized Tables

Assuming source data is cleaned, FDs are confirmed, and target tables are **currently empty**, you can load in parent-to-child order:

```sql
-- Students table.
INSERT INTO normalization_lab.students
    (student_id, student_name)
SELECT DISTINCT student_id, student_name
FROM normalization_lab.registration_raw;

-- Instructors table.
INSERT INTO normalization_lab.instructors
    (instructor_id, instructor_name)
SELECT DISTINCT instructor_id, instructor_name
FROM normalization_lab.registration_raw;

-- Courses table.
INSERT INTO normalization_lab.courses
    (course_id, course_title, instructor_id)
SELECT DISTINCT course_id, course_title, instructor_id
FROM normalization_lab.registration_raw;

-- Enrollments table.
INSERT INTO normalization_lab.enrollments
    (student_id, course_id, grade)
SELECT student_id, course_id, grade
FROM normalization_lab.registration_raw;
```

**Do not run this load block against the same tables already holding the demo rows from section 14.5.** This is an **alternative load path** on a clean lab schema. Running it on top will trigger duplicate key errors.

For a consistent migration, use transactions and proper migration tooling, handle errors, verify datasets, and plan write cutover. Never slap `ON CONFLICT DO NOTHING` just to make all SQL statements "succeed" while silently dropping conflicting rows.

### 19.1. Parent → Child Order

- `Students` and `Instructors` have no FK dependencies on other tables in this model.
- `Courses` requires existing instructors.
- `Enrollments` requires existing students and courses.

Loading parent tables before child tables keeps FK constraints active throughout the migration.

### 19.2. Row Count Check

```sql
SELECT COUNT(*) AS raw_count
FROM normalization_lab.registration_raw;
```

And:

```sql
SELECT COUNT(*) AS reconstructed_count
FROM normalization_lab.enrollments AS e
JOIN normalization_lab.students AS s
  ON s.student_id = e.student_id
JOIN normalization_lab.courses AS c
  ON c.course_id = e.course_id
JOIN normalization_lab.instructors AS i
  ON i.instructor_id = c.instructor_id;
```

On clean sample data without duplicates, both counts should match. However, **matching row counts alone do not prove identical data**: one row could have been replaced by another.

### 19.3. Reconciling with EXCEPT

When both sides represent the **same data snapshot**:

```sql
WITH reconstructed AS (
    SELECT
        s.student_id, s.student_name,
        c.course_id, c.course_title,
        i.instructor_id, i.instructor_name,
        e.grade
    FROM normalization_lab.enrollments AS e
    JOIN normalization_lab.students AS s
      ON s.student_id = e.student_id
    JOIN normalization_lab.courses AS c
      ON c.course_id = e.course_id
    JOIN normalization_lab.instructors AS i
      ON i.instructor_id = c.instructor_id
)
SELECT *
FROM normalization_lab.registration_raw
EXCEPT
SELECT *
FROM reconstructed;
```

And the reverse direction:

```sql
WITH reconstructed AS (
    SELECT
        s.student_id, s.student_name,
        c.course_id, c.course_title,
        i.instructor_id, i.instructor_name,
        e.grade
    FROM normalization_lab.enrollments AS e
    JOIN normalization_lab.students AS s
      ON s.student_id = e.student_id
    JOIN normalization_lab.courses AS c
      ON c.course_id = e.course_id
    JOIN normalization_lab.instructors AS i
      ON i.instructor_id = c.instructor_id
)
SELECT *
FROM reconstructed
EXCEPT
SELECT *
FROM normalization_lab.registration_raw;
```

Empty results in both directions prove **set equivalence** on the compared snapshot. Note that `EXCEPT` defaults to set semantics and can **ignore multiplicity differences for exact duplicate rows**. When multiplicity matters, pair with group/count checks and consider `EXCEPT ALL`.

In production migrations, if both raw and target continue receiving writes, you need a consistent snapshot or cutover point; otherwise discrepancies may reflect timing rather than table-splitting bugs.

## 20. Transitioning Applications to the New Schema

Before splitting tables, an application might simply read:

```sql
SELECT *
FROM normalization_lab.registration_raw
WHERE student_id = 1;
```

After normalization, it needs proper JOIN queries or a compatibility view:

```sql
CREATE VIEW normalization_lab.v_registration_detail AS
SELECT
    e.student_id,
    s.student_name,
    e.course_id,
    c.course_title,
    c.instructor_id,
    i.instructor_name,
    e.grade
FROM normalization_lab.enrollments AS e
JOIN normalization_lab.students AS s
  ON s.student_id = e.student_id
JOIN normalization_lab.courses AS c
  ON c.course_id = e.course_id
JOIN normalization_lab.instructors AS i
  ON i.instructor_id = c.instructor_id;
```

Views help read queries, yet **do not automatically solve writes** across the new normalized tables. The application must interact with the proper entities and transactions.

### 20.1. Production Migration Steps

A typical workflow may include:

1. Take backups and verify restore capability.
2. Identify sources of truth, FDs, and application dependencies.
3. Run contradiction checks and agree on cleanup rules.
4. Create new tables and constraints via versioned migration scripts.
5. Backfill from a controlled snapshot/checkpoint.
6. Reconcile bidirectionally: row counts, aggregates, and FKs.
7. Switch application reads/writes inside an appropriate change window.
8. Catch up writes occurring during backfill/cutover.
9. Monitor errors, latency, locks, and correctness post-cutover.
10. Retire the legacy schema only after verified success and with a viable rollback plan.

With **dual-write**, a write can succeed on the old table and fail on the new tables. You need pre-designed transactions, idempotency, sync/reconciliation, and error handling.

PostgreSQL supports transactional DDL for many operations, yet altering PKs/FKs/indexes on large tables can take time and acquire locks. `CREATE INDEX CONCURRENTLY` helps in certain cases, yet **cannot run inside a normal transaction block**; production rollouts need an explicit runbook.

## 21. Normalization and Historical Data

### 21.1. Keys May Need a Time Dimension

The initial enrollment model used:

```text
(student_id, course_id) → grade
```

If terms and retakes exist, a revised design might be:

```sql
CREATE TABLE normalization_lab.enrollment_attempts (
    enrollment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    student_id BIGINT NOT NULL
        REFERENCES normalization_lab.students(student_id),
    course_id BIGINT NOT NULL
        REFERENCES normalization_lab.courses(course_id),
    term_code TEXT NOT NULL,
    attempt_no INTEGER NOT NULL CHECK (attempt_no >= 1),
    grade NUMERIC(4,2) CHECK (grade BETWEEN 0 AND 10),
    CONSTRAINT uq_enrollment_attempt
        UNIQUE (student_id, course_id, term_code, attempt_no)
);
```

Thus:

```text
(student_id, course_id, term_code, attempt_no) → grade
```

becomes a valid FD under the new rules. If the true business key differs, adapt the design accordingly.

### 21.2. Current Price vs. Transaction-Time Price

In e-commerce:

```text
product_id → current_price
```

may hold in the **current catalog**. Yet an order line must preserve the price **at order placement**, so:

```text
(order_id, line_no) → unit_price_at_purchase
```

is a separate fact. Storing `unit_price_at_purchase` in `order_items` is not inherently bad redundancy; it is historical data independent of current price.

Likewise, recipient name, shipping address, and tax rate on an invoice may require snapshots at document issuance.

### 21.3. Never Let Current Changes Accidentally Rewrite History

If last month's report must show the **customer name/segment at the time of purchase**, joining historical orders to the **current** customer record will alter past reports whenever a customer changes their name or segment.

Clarify whether reports demand **current** or **as-of** data. Systems often use effective-dated history tables, event logs, or slowly changing dimensions to address this.

## 22. Many-to-Many and Multivalued Dependencies

### 22.1. Junction Tables Represent N–N Relationships

Students take many courses and courses have many students. `enrollments` models **each enrollment relationship as one row** and holds relationship attributes such as `grade`.

Do not store a course list in `students.course_ids` when each enrollment needs its own FK, grade, and status.

### 22.2. Multivalued Dependencies and 4NF

Suppose:

```text
PersonSkillsLanguages(person_id, skill, language)
```

A person has two skills `{Java, SQL}` and two languages `{Vietnamese, English}` independently. Storing them in one table creates a Cartesian combination:

| person_id | skill | language |
|---|---|---|
| 1 | Java | Vietnamese |
| 1 | Java | English |
| 1 | SQL | Vietnamese |
| 1 | SQL | English |

This illustrates a **multivalued dependency (MVD)**:

```text
person_id ↠ skill
person_id ↠ language
```

If the two sets are completely independent, decompose into:

```text
PersonSkills(person_id, skill)
PersonLanguages(person_id, language)
```

That is the intuition behind **4NF**: handling independent MVDs that FDs alone cannot fully capture.

If each skill–language pair carries a **real business association** (e.g., which instructor teaches which skill in which language), splitting as above would lose that association. Once again, **semantics** dictate structure.

## 23. Intentional Denormalization

**Denormalization** stores extra duplicated or pre-aggregated data to reduce read cost. It is not automatically wrong, yet brings the responsibility of keeping data consistent.

For instance, a dashboard reporting student counts by course and day might use an aggregate table:

```sql
CREATE TABLE normalization_lab.daily_course_stats (
    course_id BIGINT NOT NULL
        REFERENCES normalization_lab.courses(course_id),
    report_day DATE NOT NULL,
    enrollment_count BIGINT NOT NULL CHECK (enrollment_count >= 0),
    PRIMARY KEY (course_id, report_day)
);
```

If this aggregate table is maintained from `enrollments`, you need:

- Exact metric definitions.
- Update/recompute mechanisms when source data changes.
- Reconciliation and handling for late writes or failures.
- Maximum acceptable staleness.
- A rebuild plan if out of sync.

PostgreSQL also offers **materialized views** that persist computed results, though core PostgreSQL materialized views **do not automatically refresh incrementally** on every source table change.

### 23.1. Do Not Denormalize Just Because of JOINs

Joins over properly indexed PKs/FKs are usually very fast. Copying `instructor_name` across millions of enrollment rows forces massive updates whenever a name changes.

Before duplicating data across tables, use `EXPLAIN` and realistic load testing to verify whether a bottleneck actually exists.

### 23.2. When a Snapshot Is the Ground Truth

The product name **on a finalized invoice**, shipping address **at delivery**, and unit price **at purchase** are historical data. They may intentionally differ from current catalog/master data and have clear semantics.

Normalization does not require deleting valid snapshots; it requires identifying **which business key and point in time they depend on**.

## 24. Normalization Decision Workflow

~~~mermaid
flowchart TD
    A["Gather business facts"] --> B["Define what one row represents"]
    B --> C["List FDs, exceptions, and time dimension"]
    C --> D["Compute closures, find candidate keys"]
    D --> E["Check 1NF / partial dependencies"]
    E --> F["Check transitive dependencies / 3NF"]
    F --> G{"Need BCNF?"}
    G -- "Yes" --> H["Evaluate determinants and decompose"]
    G -- "No" --> I["Keep 3NF design"]
    H --> J["Check lossless join and preservation"]
    I --> J
    J --> K["Design PK/UNIQUE/FK/CHECK"]
    K --> L["Audit source data, backfill, and reconcile"]
    L --> M["Benchmark workload and deploy safely"]
~~~

Questions to answer:

1. Which **entity** or **relationship** does each row belong to?
2. Which attributes uniquely determine which other attributes?
3. Do FDs still hold under name changes, instructor changes, retakes, or historical tracking?
4. Which attribute sets are candidate keys, and have they been checked for minimality?
5. Are there update, insertion, or deletion anomalies?
6. Is the table split lossless?
7. Can key FDs be enforced by local constraints on the decomposed tables?
8. Does the new schema fit how the application reads and writes?
9. Is there performance evidence before intentionally denormalizing?

## 25. Common Mistakes

### 25.1. Inferring FDs from Small Samples

An attribute having only one value today does not mean it is functionally determined in all valid states. Ask the business first; use data to find **counterexamples**, not to replace definitions.

### 25.2. Using Names or Descriptions as Keys

Two people can share a name, and two products can share a description. Choose keys based on true uniqueness rules and application constraints.

### 25.3. Checking Only the Primary Key and Ignoring Alternate Keys

A relation can have multiple candidate keys. Formal 2NF/3NF evaluate **all candidate keys**, not just the PK picked by a DBA.

### 25.4. Adding an Auto-Increment ID and Assuming It's 3NF

A surrogate ID helps referencing, yet does not remove the fact that `course_id` determines course title and instructor. Update anomalies remain if names stay duplicated.

### 25.5. Forgetting NULL Semantics in UNIQUE Constraints

`email TEXT UNIQUE` allows multiple `NULL`s by default. If a value is mandatory, add `NOT NULL`.

### 25.6. Using DISTINCT to Hide Inconsistent Data

`SELECT DISTINCT student_id, student_name` cannot fix a dataset where the same ID appears with two names. Find the root cause and apply cleanup policies.

### 25.7. Splitting Tables Where JOIN Creates Spurious Rows

Not every decomposition is lossless. Analyze overlapping attributes and FDs, then test against realistic edge cases.

### 25.8. Reaching BCNF While Losing Dependency Preservation

An FD that can no longer be enforced by local constraints becomes hard to guarantee under concurrent writes. Choose a design that can sustain real business rules.

### 25.9. Ignoring the Time Dimension

`course_id → instructor_id` may hold currently yet fail historically. Keys must reflect terms, sections, or versions when required.

### 25.10. Removing Historical Prices Because They Match Catalog Prices

Prices on documents depend on the order/purchase event, not necessarily on current product catalog prices. Separate historical facts from master data cleanly.

### 25.11. Denormalizing Without a Synchronization Mechanism

If you duplicate a name or total for read speed, someone/something must own updates, recovery, reconciliation, and lag monitoring.

### 25.12. Treating Equal Row Counts as a Successful Migration

Two datasets with identical row counts can still differ in content. Compare tuples bidirectionally, check multiplicities, verify constraints, and validate business aggregates at the same snapshot.

## 26. Practice Exercises

### Exercise 1 — Identifying FDs in a Library

Given:

```text
Borrow(
    borrower_id, borrower_name,
    book_copy_id, book_title,
    borrow_date, due_date
)
```

Assume each book copy has one current title, and a borrower can borrow the same copy again on different dates. Write reasonable FDs and explain why `(borrower_id, book_copy_id)` is not necessarily a candidate key for borrowing history.

### Exercise 2 — Computing Closures

Given relation `R(A,B,C,D,E)` and:

```text
A → B
C → D
D → E
(A,C) → E
```

Compute `{A,C}⁺`, `{A}⁺`, `{C}⁺`; identify the candidate key and one potentially redundant FD.

### Exercise 3 — 1NF and Phone Number Lists

Table `employees(employee_id, name, phones)` stores `phones = '090...,091...'`. Design a separate phones table with a key preventing an employee from storing the same number twice.

### Exercise 4 — 2NF

`order_items(order_id, product_id, product_name, quantity, unit_price_at_order)` has candidate key `(order_id, product_id)`. Assume `product_id → product_name`. Which attribute is partially dependent? How should it be decomposed?

### Exercise 5 — 3NF

In `Courses(course_id, course_title, instructor_id, instructor_name)`, identify the FD violating 3NF and design a separate instructors table.

### Exercise 6 — 3NF vs. BCNF

Given:

```text
Teaching(student_id, course_id, instructor_id)

(student_id, course_id) → instructor_id
instructor_id → course_id
```

Find the candidate keys; explain why it is 3NF but not BCNF; identify the FD that may lose dependency preservation after BCNF decomposition.

### Exercise 7 — Lossless Join

Relation `R(A,B,C)` splits into `R1(A,B)` and `R2(B,C)`. If `B → C` holds, is the decomposition lossless? If no FD guarantees it, construct two rows whose JOIN produces spurious tuples.

### Exercise 8 — SQL to Check FDs

Write SQL to find `course_id`s with multiple `course_title`s in the raw table. If no rows return, does that prove the FD holds for the future?

### Exercise 9 — UNIQUE and NULL

Why doesn't `email TEXT UNIQUE` mean email is a mandatory alternate key in PostgreSQL? Write DDL for a non-NULL, unique email.

### Exercise 10 — Four Normalized Tables

Write DDL for `students`, `instructors`, `courses`, and `enrollments`, including PKs/FKs and grades from 0 to 10 or ungraded.

### Exercise 11 — Retaking Courses

If students can take the same course across two terms, why is `PRIMARY KEY(student_id, course_id)` insufficient? Propose a new key or business constraint.

### Exercise 12 — Migration Verification

Both the raw source and the JOIN of new tables return 10,000 rows. List at least four extra checks to avoid missing bad rows, duplicates, or mid-migration changes.

### Exercise 13 — Denormalization

A dashboard frequently computes enrollment counts and average grades per instructor on a very large dataset. Should you duplicate instructor names onto every enrollment row to avoid JOINs? Propose a solution balancing performance and correctness.

## 27. Solution Hints

### Exercise 1

You can establish:

```text
borrower_id → borrower_name
book_copy_id → book_title
(borrower_id, book_copy_id, borrow_date) → due_date
```

The final FD holds only if each person borrows a given copy at most once per day. If multiple loans can occur on the same day, you need `borrow_id` or `attempt_no`. `(borrower_id, book_copy_id)` is insufficient when re-borrowing happens on later dates.

### Exercise 2

```text
{A,C}⁺ = {A,B,C,D,E}
{A}⁺   = {A,B}
{C}⁺   = {C,D,E}
```

`(A,C)` is the candidate key. FD `(A,C) → E` is redundant because `C → D` and `D → E` imply `C → E`, which implies `(A,C) → E`.

### Exercise 3

```sql
CREATE TABLE employees (
    employee_id BIGINT PRIMARY KEY,
    employee_name TEXT NOT NULL
);

CREATE TABLE employee_phones (
    employee_id BIGINT NOT NULL REFERENCES employees(employee_id),
    phone_number TEXT NOT NULL,
    PRIMARY KEY (employee_id, phone_number)
);
```

The PK prevents **one employee from having the same number twice**. Whether a number is forbidden from belonging to two different employees (`UNIQUE(phone_number)`) is a separate rule to confirm.

### Exercise 4

`product_id → product_name` is a partial dependency on the composite key. Split into:

```text
Products(product_id, product_name)
OrderItems(order_id, product_id, quantity, unit_price_at_order)
```

`unit_price_at_order` is the locked price for that order line, not synced automatically to current catalog price.

### Exercise 5

The FD `instructor_id → instructor_name` has a determinant that is not a superkey of `Courses` and a non-prime right-hand side. Split into:

```text
Instructors(instructor_id PK, instructor_name)
Courses(course_id PK, course_title, instructor_id FK)
```

### Exercise 6

Candidate keys: `(student_id, course_id)` and `(student_id, instructor_id)`. `course_id` is prime; `instructor_id → course_id` is allowed by 3NF yet violates BCNF since `instructor_id` is not a superkey. After splitting into `InstructorCourse` and `StudentInstructor`, `(student_id, course_id) → instructor_id` may no longer be enforceable locally.

### Exercise 7

If `B → C`, the intersection `R1 ∩ R2 = {B}` determines all of `R2`, so the decomposition is lossless. Without a supporting FD, take `(a1,b1,c1)` and `(a2,b1,c2)`; joining the two projections yields extra spurious tuples `(a1,b1,c2)` and `(a2,b1,c1)`.

### Exercise 8

```sql
SELECT course_id, COUNT(DISTINCT course_title) AS title_count
FROM normalization_lab.registration_raw
GROUP BY course_id
HAVING COUNT(DISTINCT course_title) > 1;
```

An empty result only means **no violations were detected** in observed data (under reasonable NULL assumptions); the FD still requires business confirmation and schema enforcement.

### Exercise 9

```sql
CREATE TABLE contacts (
    contact_id BIGINT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE
);
```

`NOT NULL` rejects missing values; `UNIQUE` enforces uniqueness under the column's comparison rules. If case-insensitivity is needed, add an appropriate design.

### Exercise 10

One solution is the four tables in section 14, notably:

```sql
CREATE TABLE normalization_lab.enrollments (
    student_id BIGINT NOT NULL
        REFERENCES normalization_lab.students(student_id),
    course_id BIGINT NOT NULL
        REFERENCES normalization_lab.courses(course_id),
    grade NUMERIC(4,2) CHECK (grade BETWEEN 0 AND 10),
    PRIMARY KEY (student_id, course_id)
);
```

Omit `NOT NULL` on `grade` when representing ungraded enrollments.

### Exercise 11

A suitable key could be `(student_id, course_id, term_id)` if only one attempt is allowed per term. If multiple attempts can occur within the same term, add `attempt_no` or an `enrollment_id` paired with an appropriate business unique constraint.

### Exercise 12

You need: bidirectional `EXCEPT` to compare tuples; `EXCEPT ALL` or grouping/counts to verify multiplicity; FK/UNIQUE/NULL checks; business aggregate comparisons; checking at the exact same data snapshot; smoke-testing the new application and tracking writes occurring during cutover.

### Exercise 13

Do not duplicate `instructor_name` by default just to avoid JOINs. Start with PKs/FKs, indexes, and `EXPLAIN` measurements. If aggregate queries remain heavy, consider an aggregate table or materialized view with refresh and reconciliation policies. If the name must reflect the name **at the time of teaching**, store a snapshot with explicit historical semantics.

## 28. Conclusion

**Functional dependencies** express `X → Y` rules across all valid data states. From them, we compute **attribute closures**, identify **candidate keys**, and spot columns placed in the wrong owning table.

**1NF** establishes proper attribute value representation; **2NF** removes partial dependencies; **3NF** removes improper non-key dependencies with a formal exception for prime attributes; **BCNF** requires every determinant of a non-trivial FD to be a superkey. Any decomposition must evaluate **lossless join** and **dependency preservation**, not merely table count.

In PostgreSQL, `PRIMARY KEY`, `UNIQUE`, `NOT NULL`, `FOREIGN KEY`, and `CHECK` enforce the model. Yet no constraint replaces understanding **business scope, the time dimension, and what each row represents**. Adding auto-increment IDs or sprinkling `SELECT DISTINCT` cannot fix misunderstood dependencies.

A sustainable workflow is: **identify facts and FDs → find keys → normalize → enforce constraints → audit source data → migrate with reconciliation → benchmark workloads → denormalize intentionally only when truly needed**.
