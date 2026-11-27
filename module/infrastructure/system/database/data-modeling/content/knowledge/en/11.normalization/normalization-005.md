# Boyce–Codd Normal Form (BCNF) and the Role of Superkeys

**Boyce–Codd Normal Form (BCNF)** imposes a stricter requirement than Third Normal Form (3NF): **in every non-trivial functional dependency, the left-hand side must be a superkey**. This concise rule uncovers structures that still permit data redundancy even after satisfying 3NF, especially in tables with multiple overlapping candidate keys.

In the **Normalization** chapter of the **DATABASE_DATA_MODELING** module, the aim is not merely to memorize normal form names. A designer must translate business rules into functional dependencies, find candidate keys, decide which entity owns each fact, decompose tables without generating spurious results, and verify that constraints remain enforceable after decomposition. BCNF is a tool for clarifying those decisions; it must be weighed alongside update patterns, query needs, foreign keys, indexes, and schema evolvability.

## 1. Problem Setup: A Table Already in 3NF That Still Repeats Information

Suppose a training system manages students studying with instructors in **a given term**, under these rules:

1. Each **instructor** teaches only **one course** in this term.
2. One course can have **multiple instructors**.
3. Each student chooses **at most one instructor per course**.
4. An instructor can supervise many students, and a student can take many courses.

The initial table stores each row as an enrollment with an instructor:

| student_id | course_id | instructor_id |
| --- | --- | --- |
| S01 | C10 | I01 |
| S02 | C10 | I01 |
| S03 | C10 | I02 |
| S01 | C20 | I03 |

In the data above, **I01** teaching **C10** appears twice. If instructor I01 switches to teaching a different course, I01's course must be updated across all enrollments. Missing one row during an update causes the same instructor to be assigned to two courses. Deleting I02's last enrollment also erases the fact that instructor I02 teaches course C10, even though that teaching assignment is still active.

This is an instructive case for studying BCNF because **every attribute belongs to at least one candidate key**; under the formal definition, the table satisfies 3NF yet fails BCNF.

> **Business scope of this example:** the assumption "each instructor teaches one course" holds only **within the current term**. If managing multiple terms or allowing an instructor to teach multiple courses, the functional dependencies must change, likely requiring **term_id**, **section_id**, or an explicit teaching-assignment entity.

## 2. Concepts to Distinguish Before Evaluating BCNF

### 2.1. A Functional Dependency Is a Rule, Not a Coincidence

We write **X → Y** when, in every valid data state, two rows with the same X value must have the same Y value. Both X and Y can be sets of attributes.

In the example:

~~~text
(student_id, course_id) -> instructor_id
instructor_id             -> course_id
~~~

The first dependency comes from the rule that each student has at most one instructor per course. The second comes from the rule that each instructor teaches only one course. There is **no** dependency **course_id → instructor_id** because a course can have multiple instructors.

A few sample rows are not enough to prove a functional dependency: you must confirm with the business that the rule holds across all other valid scenarios.

### 2.2. Superkeys and Candidate Keys Differ in Minimality

- **Superkey:** a set of attributes that uniquely determines all attributes of a row; need not be minimal.
- **Candidate key:** a **minimal superkey**, meaning removing any attribute loses unique row identification.
- **Primary key:** a candidate key selected as the primary identifier in the SQL schema.
- **Prime attribute:** belongs to at least one candidate key; all remaining attributes are **non-prime**.

For instance, if **(student_id, course_id)** is a candidate key, then **(student_id, course_id, instructor_id)** is still a superkey, but not a candidate key because it contains an extra attribute.

The BCNF condition requires a **superkey**—it does not require the left-hand side to be strictly a candidate key. Any superkey suffices, including one with extra attributes.

### 2.3. Finding Keys Using Attribute Closure

The **closure of X**, denoted **X⁺**, is the set of attributes that can be derived from X through functional dependencies. A set X is a superkey if **X⁺** contains every attribute of the relation.

Using short names for the three attributes:

~~~text
S = student_id
C = course_id
I = instructor_id

R(S, C, I)
F = { SC -> I, I -> C }
~~~

We obtain:

| Attribute Set X | Closure X⁺ | Is Superkey? |
| --- | --- | --- |
| {S} | {S} | No |
| {C} | {C} | No |
| {I} | {I, C} | No: missing S |
| {S, C} | {S, C, I} | Yes |
| {S, I} | {S, I, C} | Yes |

Both **SC** and **SI** are minimal superkeys, making them **two candidate keys**. They overlap on attribute S. S, C, and I are all **prime attributes** because each appears in at least one candidate key.

Notice that **I → C** is a valid functional dependency, yet **I is not a superkey**: an instructor can teach many students, so the same I can appear across multiple rows with different S values.

## 3. Formal Definition of BCNF

A relation **R is in BCNF** when, for **every non-trivial functional dependency X → A** that holds on R (where A is an attribute), **X is a superkey of R**.

- **Non-trivial** means **A is not in X**. For instance, **(S, C) → S** is a trivial dependency and need not be checked.
- If the right-hand side has multiple attributes, it can be split into single-attribute dependencies on the right-hand side for checking.
- "Every dependency" includes dependencies **inferred** from business rules, not only those explicitly listed at first.
- The notion of **superkey of R** must always be evaluated with respect to **the relation currently under inspection**, because decomposing into child relations can change attribute sets and keys.

An equivalent wording: **every determinant of a non-trivial functional dependency must be a superkey**.

In the enrollment table:

| Dependency | Left-Hand Side Is Superkey? | BCNF Result |
| --- | --- | --- |
| **(S, C) → I** | Yes, SC is a candidate key | Satisfied |
| **I → C** | No, I⁺ = {I, C} lacks S | **Violates BCNF** |

**A single violating dependency is enough to conclude that the entire relation is not in BCNF.**

## 4. Why Does 3NF Permit a Case That BCNF Forbids?

Formal definition of **3NF**: for each non-trivial functional dependency **X → A**, at least one condition holds:

1. X is a **superkey**; **or**
2. A is a **prime attribute**.

**BCNF keeps only the first condition.**

In relation R(S, C, I):

- **SC → I** is valid in both 3NF and BCNF because SC is a superkey.
- **I → C** is valid in **3NF** because C belongs to candidate key SC and is a prime attribute, **even though I is not a superkey**.
- **I → C** violates **BCNF** because BCNF has no exception for "the right-hand side is a prime attribute."

| Normal Form | Core Criterion | Evaluation of R(S, C, I) |
| --- | --- | --- |
| **1NF** | Every attribute represents a domain-appropriate value, avoiding hidden independently managed repeating groups | Can satisfy |
| **2NF** | Non-prime attributes are fully dependent on every candidate key | Satisfied: all attributes are prime |
| **3NF** | For non-trivial X → A: X is a superkey **or** A is prime | **Satisfied** |
| **BCNF** | For non-trivial X → A: **X must be a superkey** | **Violated**, due to I → C |

Thus, **BCNF is strictly stronger than 3NF**. Every relation in BCNF satisfies 3NF; the converse does not always hold. Do not memorize only "3NF removes transitive dependencies": in relations with multiple candidate keys, that rule of thumb is not precise enough to decide correctly.

## 5. Decomposing a Relation into BCNF Tables

Given a dependency **X → Y** violating BCNF, a standard binary decomposition is:

~~~text
R1 = X ∪ Y
R2 = R − (Y − X)
~~~

Applying this to **I → C** in R(S, C, I):

~~~text
R1(I, C)     -- assigning a course to an instructor
R2(S, I)     -- students enrolling with an instructor
~~~

Relational diagram after decomposition:

~~~mermaid
erDiagram
    COURSES ||--o{ INSTRUCTORS : "taught by"
    INSTRUCTORS ||--o{ STUDENT_INSTRUCTORS : "teaches"
    STUDENTS ||--o{ STUDENT_INSTRUCTORS : "enrolls with"
    COURSES {
        varchar course_id PK
        varchar course_title
    }
    INSTRUCTORS {
        varchar instructor_id PK
        varchar course_id FK
    }
    STUDENTS {
        varchar student_id PK
        varchar student_name
    }
    STUDENT_INSTRUCTORS {
        varchar student_id PK, FK
        varchar instructor_id PK, FK
    }
~~~

At the core of the decomposition:

- **R1(I, C)** has the dependency **I → C**, where I is a candidate key of R1. R1 is in BCNF.
- **R2(S, I)** has no non-trivial functional dependency whose left-hand side is not a superkey under the given rules; the pair **(S, I)** is the candidate key. R2 is in BCNF.

Adding the lookup tables **STUDENTS** and **COURSES** in the SQL implementation helps manage entities independently. They do not alter the decomposition reasoning for the three attributes R(S, C, I).

### 5.1. SQL Implementation Example After Decomposition

The following example uses PostgreSQL syntax; tables can be created and populated in order:

~~~sql
CREATE TABLE students (
    student_id   VARCHAR(10) PRIMARY KEY,
    student_name VARCHAR(100) NOT NULL
);

CREATE TABLE courses (
    course_id    VARCHAR(10) PRIMARY KEY,
    course_title VARCHAR(100) NOT NULL
);

CREATE TABLE instructors (
    instructor_id VARCHAR(10) PRIMARY KEY,
    course_id     VARCHAR(10) NOT NULL
        REFERENCES courses(course_id)
);

CREATE TABLE student_instructors (
    student_id    VARCHAR(10) NOT NULL
        REFERENCES students(student_id),
    instructor_id VARCHAR(10) NOT NULL
        REFERENCES instructors(instructor_id),
    PRIMARY KEY (student_id, instructor_id)
);

INSERT INTO students (student_id, student_name) VALUES
    ('S01', 'An'),
    ('S02', 'Bình'),
    ('S03', 'Chi');

INSERT INTO courses (course_id, course_title) VALUES
    ('C10', 'Databases'),
    ('C20', 'Java Programming');

INSERT INTO instructors (instructor_id, course_id) VALUES
    ('I01', 'C10'),
    ('I02', 'C10'),
    ('I03', 'C20');

INSERT INTO student_instructors (student_id, instructor_id) VALUES
    ('S01', 'I01'),
    ('S02', 'I01'),
    ('S03', 'I02'),
    ('S01', 'I03');
~~~

When enrollments need to be viewed in the form R(S, C, I), join on **instructor_id**:

~~~sql
SELECT
    e.student_id,
    i.course_id,
    e.instructor_id
FROM student_instructors AS e
JOIN instructors AS i
    ON i.instructor_id = e.instructor_id
ORDER BY e.student_id, i.course_id;
~~~

The fact **which instructor teaches which course** is stored once in the **instructors** table. Reassigning an instructor updates one row; instructors with zero enrollments yet can also be stored.

### 5.2. Checking the Lossless-Join Property

The decomposition **R(S, C, I) → R1(I, C), R2(S, I)** has the intersection:

~~~text
R1 ∩ R2 = {I}
~~~

Because **I → C**, the intersection **{I}** determines all attributes of **R1(I, C)**. By the binary decomposition criterion, this is a **lossless-join** decomposition for every valid original relation satisfying the given dependencies.

On the initial data, each **(S, I)** row matches one **(I, C)** row to reconstruct **(S, C, I)** exactly. There is no risk of one instructor teaching two courses multiplying rows in the join, because **I** is the key of R1.

**Lossless join** answers the question: "Can the original relation be reconstructed accurately from a valid decomposition?" It **does not automatically guarantee** that every state writable into the new tables still satisfies all original business rules.

## 6. Key Trade-Off: BCNF May Not Preserve Functional Dependencies

After decomposition, **I → C** resides completely within **instructors(I, C)** and is enforced by the primary key **instructor_id**.

However, the original dependency **(S, C) → I** does not reside entirely within any single table:

~~~text
instructors(I, C):          I -> C
student_instructors(S, I):  (S, I) is the key
~~~

From the individual dependencies of the two tables, you cannot infer that a student has at most **one** instructor per course. This is an example of a decomposition that is **lossless yet not dependency-preserving**.

### 6.1. Concrete Counterexample

Suppose in the sample data, **I01** and **I02** both teach course **C10**. Execute:

~~~sql
-- Two different instructors, same course C10.
-- Primary key (student_id, instructor_id) still allows the new row.
INSERT INTO student_instructors (student_id, instructor_id)
VALUES ('S01', 'I02');
~~~

Now the join returns:

| student_id | course_id | instructor_id |
| --- | --- | --- |
| S01 | C10 | I01 |
| S01 | C10 | I02 |

These two rows violate **(student_id, course_id) → instructor_id**. They do not violate any primary key or foreign key in the BCNF schema from section 5.1. That does not contradict the *lossless* property of the decomposition: the data **after the insert** violates a business rule of the original R that single-table constraints on the child tables did not prevent.

Violations can be detected with a query:

~~~sql
SELECT
    e.student_id,
    i.course_id,
    COUNT(DISTINCT e.instructor_id) AS instructor_count
FROM student_instructors AS e
JOIN instructors AS i
    ON i.instructor_id = e.instructor_id
GROUP BY e.student_id, i.course_id
HAVING COUNT(DISTINCT e.instructor_id) > 1;
~~~

A query only **detects** bad data. To **prevent** bad data, you need an additional enforcement mechanism for **(student_id, course_id) → instructor_id**—such as an alternative design enabling a unique constraint, or write logic protecting concurrency with suitable constraints, triggers, or transactions. Pre-checking in application code without write-concurrency protection remains vulnerable to a *race condition*.

### 6.2. When Should 3NF Be Preferred?

For any set of functional dependencies, the **3NF synthesis** algorithm produces a decomposition that is both **lossless-join** and **dependency-preserving**. Conversely, not every relation has a BCNF decomposition that is simultaneously lossless and preserves all dependencies.

| Goal | 3NF | BCNF |
| --- | --- | --- |
| Limiting redundancy-causing dependencies | Good; permits exceptions when RHS is prime | Stricter: every determinant must be a superkey |
| Lossless decomposition | Achievable via standard algorithm | Achievable via standard decomposition algorithm |
| Preserving all functional dependencies | Guaranteed via 3NF synthesis algorithm | **Not always guaranteed** |
| Constraint enforcement cost | Often easier if dependencies are preserved | Some dependencies may require cross-table checks or redesign |

**Note:** *dependency preservation* is a formal property of a decomposition and **does not mean** every dependency can be expressed by a simple **PRIMARY KEY**, **UNIQUE**, or **CHECK** statement in SQL. For instance, in the flat table where multiple students share an instructor, **I → C** cannot be enforced simply by **UNIQUE(I)**, since that would forbid an instructor from appearing in multiple enrollments. Concrete enforcement still requires appropriate constraint or write-path design.

## 7. When Is BCNF Necessary, and When Is Deeper Analysis Needed?

### 7.1. Tables Already in 3NF That Violate BCNF

Focus on relations with **multiple overlapping candidate keys** or dependencies whose **right-hand side is a prime attribute**. That is where 3NF's exception can mask redundancy risks.

List every non-trivial functional dependency and compute the closure of its left-hand side. If a left-hand side fails to determine every attribute of the relation, that dependency violates BCNF.

### 7.2. Tables Not Yet in 3NF

Example table:

~~~text
employees(employee_id, employee_name, department_id, department_name)

employee_id  -> employee_name, department_id
department_id -> department_name
~~~

If **employee_id** is the sole candidate key, **department_id → department_name** violates **both 3NF and BCNF**: department_id is not a superkey and department_name is non-prime. Splitting into **departments(department_id, department_name)** and **employees(employee_id, employee_name, department_id)** is the direct fix.

BCNF subsumes fixing cases that fail 3NF, yet BCNF's distinct contribution is removing **even those dependencies that 3NF allows because the right-hand side is prime**.

### 7.3. Surrogate Keys Do Not Erase Business Dependencies

If you add **registration_id** as the primary key to R(S, C, I), the rules **SC → I** and **I → C** still hold. A single-column **registration_id** key does not magically make every dependency's left-hand side a superkey.

Moreover, if you add **UNIQUE(student_id, course_id)** with both columns **NOT NULL**, the pair **(S, C)** remains a candidate key alongside **registration_id**. You must evaluate **all candidate keys and all functional dependencies**, not merely the column named in **PRIMARY KEY**.

### 7.4. Changing Context Changes Dependencies

The rule **I → C** may hold within one term yet break when managing multi-term history. If an instructor teaches a different course in the following term, the dependency may become:

~~~text
(instructor_id, term_id) -> course_id
~~~

If an instructor teaches multiple sections of multiple courses in the same term, the dependency might require **section_id**, or cease to exist in that form altogether. Clarify grain and time dimension before labeling something a "BCNF violation" so you do not decompose around a rule that no longer matches the business.

## 8. BCNF Evaluation and Decomposition Workflow

1. **Confirm grain and domains.** Does one row represent an enrollment, a teaching assignment, an attempt, or an exam result? Identify which attributes belong to each fact.
2. **Gather functional dependencies.** Base them on business rules that hold stably across the scope and timeframe being modeled, not solely on sample data.
3. **Find candidate keys via closure.** From the dependencies, find the minimal attribute sets that determine the whole table.
4. **Check BCNF.** For each non-trivial **X → A**, compute **X⁺**. If X⁺ does not include all attributes of the relation, record a violation.
5. **Decompose on a violating dependency.** Use **R1 = X ∪ Y** and **R2 = R − (Y − X)**, then recursively check BCNF on each child relation.
6. **Verify lossless join.** For a binary split, check that the intersection determines all attributes of one of the two child relations; for multi-step splits, verify every step is lossless.
7. **Evaluate dependency preservation.** Re-list the original dependencies and check whether they are enforceable within individual child tables or require cross-table verification.
8. **Finalize keys and write mechanisms.** Add **PRIMARY KEY**, **FOREIGN KEY**, **UNIQUE**, **CHECK**, transactions, or appropriate advanced constraints; test concurrent write scenarios too.
9. **Assess query cost and evolution.** Analyze joins, indexes, and data volumes. If a denormalized read model or document view is needed, document the source of truth, sync rules, and invariants to protect.

There is no rule saying "more tables is always better." A BCNF decomposition that makes an essential business rule hard to enforce may call for an additional safeguard or a different design choice, including 3NF. The decision must align with verification and operational requirements.

## 9. Practice Exercises

### Exercise 1. Finding Keys and Normal Forms

Given relation **R(A, B, C)** and functional dependencies:

~~~text
AB -> C
C  -> B
~~~

Assume no other part of the schema introduces additional functional dependencies beyond the logical consequences of these two rules.

**Tasks:**

1. Compute **A⁺**, **C⁺**, **(AB)⁺**, and **(AC)⁺**.
2. Find all candidate keys.
3. Determine whether R satisfies **3NF** and **BCNF**.
4. Decompose R into BCNF relations; prove the join is lossless.
5. Check whether the dependency **AB → C** is preserved across the child relations.

<details>
<summary>Suggested Solution for Exercise 1</summary>

~~~text
A+  = {A}
C+  = {C, B}
AB+ = {A, B, C}
AC+ = {A, C, B}
~~~

The candidate keys are **AB** and **AC**; A, B, and C are all prime attributes. **AB → C** satisfies 3NF/BCNF because AB is a superkey. **C → B** satisfies 3NF because B is prime, yet violates BCNF because C is not a superkey.

Decompose into **R1(C, B)** and **R2(A, C)**. The intersection is **C**, and **C → B**, so the decomposition is lossless. Both child relations satisfy BCNF under the projected dependencies.

The dependency **AB → C** is not preserved by the local dependency **C → B** in R1 and trivial dependencies in R2. An extra mechanism is needed to enforce this dependency on writes to the new tables.

</details>

### Exercise 2. Evaluating a Requirement Change

In the training system from the start of the lesson, the business team adds a requirement that **each instructor can teach multiple courses, but each instructor leads only one section per course per term**.

Answer the following:

- Does the dependency **instructor_id → course_id** still hold?
- What additional details about **term**, **section**, and **enrollment** must be clarified before defining keys?
- Can you still conclude that **(student_id, course_id, instructor_id)** violates BCNF based solely on the old rule?

**Hint:** the dependency **I → C** no longer holds once an instructor is allowed to teach multiple courses. You need to model **term_id**, **section_id**, and constraints on how many sections or instructors a student can select per course. Never diagnose a BCNF violation using a dependency that the business has invalidated.

## 10. Common Misconceptions

| Misconception | Accurate Understanding |
| --- | --- |
| "The left-hand side just needs to be the primary key." | BCNF accepts **any superkey**, including other candidate keys and non-minimal superkeys. |
| "Satisfying 3NF automatically satisfies BCNF." | 3NF permits **X → A** when A is a prime attribute even if X is not a superkey; BCNF allows no such exception. |
| "Having an ID column as primary key puts the table in BCNF." | You must inspect **all business functional dependencies**; adding an ID does not erase existing dependencies. |
| "A table with multiple rows sharing the same course_id is wrong." | Repeating a foreign key or course code is normal; what matters is which dependency forces other facts to be copied. |
| "A lossless decomposition means all constraints are preserved." | Lossless join and dependency preservation are **two distinct properties**. |
| "BCNF is always better than 3NF in every project." | BCNF eliminates an extra class of redundancy but can make certain constraints harder to enforce; evaluate business and integrity needs. |
| "Having no duplicate data in sample rows means BCNF is met." | Normal forms are determined by **valid functional dependencies**, not by a sample data state. |
| "An instructor always teaches exactly one course." | That is a context-specific assumption; multi-term history and multiple sections can alter the dependencies. |

## 11. Key Takeaways

BCNF requires: **for every non-trivial functional dependency X → A, X must be a superkey**. To evaluate it, find **all candidate keys**, use **attribute closure** to test left-hand sides, and rely on business-confirmed functional dependencies. This is how BCNF eliminates dependencies that 3NF still permits when the right-hand side is a prime attribute.

Decomposing on a violating dependency yields a **lossless-join** BCNF schema, yet it **does not always preserve every functional dependency**. In real system design, verify whether write-time business rules remain enforceable, finalize keys and constraints, and then weigh query costs, indexes, and historical needs. Choosing BCNF or a well-governed 3NF design is a decision grounded in correctness and operability, not merely chasing the highest normal form.
