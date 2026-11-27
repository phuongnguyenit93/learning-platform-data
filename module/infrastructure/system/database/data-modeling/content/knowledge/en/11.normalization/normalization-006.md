# Distinguishing 3NF from BCNF Using Multi-Candidate-Key Examples

A relation can **satisfy Third Normal Form (3NF)** yet **fail Boyce–Codd Normal Form (BCNF)**. The difference usually surfaces when a relation has **multiple candidate keys** and contains a functional dependency whose right-hand side belongs to a candidate key even though its left-hand side is not a superkey.

In the **Normalization** chapter of the **DATABASE_DATA_MODELING** module, distinguishing these two normal forms helps translate business requirements into verifiable keys, functional dependencies, and constraints. This lesson focuses on **directly comparing 3NF and BCNF through examples with multiple candidate keys**, explaining attribute closure calculation, decomposition, and why choosing a normal form also affects the preservation of business rules.

## 1. The Difference Hinges on One Condition, with Significant Design Consequences

Suppose **R** is a relation and **X → A** is a **non-trivial** functional dependency (A is not in X).

| Normal Form | Condition That Must Hold for **Every Non-Trivial X → A** | Practical Question |
| --- | --- | --- |
| **3NF** | **X is a superkey, or A is a prime attribute** | If X is not a superkey, does A belong to at least one candidate key? |
| **BCNF** | **X must be a superkey** | Does X determine the entire row? |

Key terms in these conditions:

- **Functional dependency X → A:** in every valid state, two rows with the same X must have the same A; this is a business rule, not a coincidence in sample data.
- **Superkey:** a set of attributes that uniquely determines the entire row.
- **Candidate key:** a minimal superkey; removing any component means it is no longer a superkey.
- **Prime attribute:** belongs to **at least one** candidate key, even if that key was not chosen as the primary key.
- **Non-prime attribute:** does not belong to any candidate key.

By definition, **BCNF is stronger than 3NF**: any relation in BCNF is in 3NF, while the reverse has exceptions. The 3NF condition accepts a dependency whose left-hand side is **not** a superkey provided **the right-hand attribute is prime**; BCNF does not allow that exception.

> Pitfall to avoid: "prime attribute" **does not mean** "in the primary key." A table can have several candidate keys; picking one as the PRIMARY KEY does not erase the other candidate keys.

## 2. Business Example: Students, Courses, and Mentors

In a training program **during a fixed term**, the system records each student paired with a mentor supervising a course:

| student_id | course_id | mentor_id |
| --- | --- | --- |
| S01 | C10 | M01 |
| S02 | C10 | M01 |
| S03 | C10 | M02 |
| S01 | C20 | M03 |

**Grain**: one **student – course – mentor** assignment in the given term. To determine keys and normal forms, the business confirms:

1. Each student can choose **only one mentor for a given course** in the term.
2. Each mentor handles **only one course** in the term, though they may mentor multiple students.
3. One course can have multiple mentors.
4. One student can take multiple courses.

Let **S = student_id**, **C = course_id**, **M = mentor_id**. We have:

~~~text
R(S, C, M)

F1: (S, C) -> M   -- student + course determines mentor
F2: M      -> C   -- mentor determines assigned course
~~~

Do not invent **C → M**: one course can have both M01 and M02. There is no **S → C** or **S → M** because a student can take multiple courses with multiple mentors.

### 2.1. Finding All Candidate Keys Using Closure

The **closure X⁺** is the set of attributes derivable from X via functional dependencies. X is a **superkey** if X⁺ contains every attribute of R. In this example:

| X | Closure Derivation | X⁺ | Superkey? |
| --- | --- | --- | --- |
| **S** | No dependency has S alone on the left-hand side | {S} | No |
| **C** | No dependency has C alone on the left-hand side | {C} | No |
| **M** | From M → C, add C | {M, C} | No, missing S |
| **(S, C)** | From SC → M, add M | {S, C, M} | Yes |
| **(S, M)** | From M → C, add C | {S, M, C} | Yes |
| **(C, M)** | From M → C, only recovers C | {C, M} | No, missing S |

**S must appear in every candidate key**, because S never appears on the right-hand side of any dependency and therefore cannot be inferred from C or M. Pairing S with either C or M suffices to determine the entire row. Both pairs are minimal because no single attribute suffices.

Thus, **all candidate keys** are:

~~~text
K1 = (S, C)
K2 = (S, M)
~~~

Prime attributes:

~~~text
S: prime because it belongs to K1 and K2
C: prime because it belongs to K1
M: prime because it belongs to K2
~~~

**All attributes of R are prime**. This result is decisive for 3NF. Even if the system picks **(S, M)** as the primary key, C is **still** a prime attribute because it belongs to candidate key **(S, C)**.

### 2.2. Checking Each Dependency Under 3NF

For **SC → M**, SC is a candidate key and thus satisfies 3NF.

For **M → C**:

- This dependency is **non-trivial**, since C is not in M.
- M is **not** a superkey: **M⁺ = {M, C}**, missing S.
- C **is a prime attribute**, since it belongs to candidate key SC.

Because the right-hand side is prime, **M → C is permitted in 3NF**. All non-trivial dependencies derivable from F1 and F2 also satisfy 3NF; hence relation **R is in 3NF** under the given rules.

### 2.3. Checking the Same Dependencies Under BCNF

BCNF accepts only superkeys on the left-hand side:

| Dependency | Left-Hand Side Is Superkey? | 3NF | BCNF |
| --- | --- | --- | --- |
| **SC → M** | Yes, SC is a candidate key | Satisfied | Satisfied |
| **M → C** | **No**, M⁺ lacks S | **Satisfied**, because C is prime | **Violated** |

**Conclusion for the example:** R satisfies **3NF but fails BCNF**. A single non-trivial dependency whose left-hand side is not a superkey disqualifies the relation from BCNF.

~~~mermaid
flowchart TD
    START["Non-trivial functional dependency X → A"]
    SUPER{"Is X a superkey?"}
    PRIME{"Does A belong to at least one candidate key?"}
    BOTH["Satisfies both 3NF and BCNF"]
    ONLY["Satisfies 3NF; violates BCNF"]
    NONE["Violates both 3NF and BCNF"]
    START --> SUPER
    SUPER -->|"Yes"| BOTH
    SUPER -->|"No"| PRIME
    PRIME -->|"Yes"| ONLY
    PRIME -->|"No"| NONE
~~~

The flowchart above applies **to each dependency individually**; the normal form of the whole relation is determined after checking **every non-trivial dependency**. One compliant dependency does not prove the entire relation meets the normal form.

## 3. Why Do Multiple Candidate Keys Often Lead Learners to Wrong Conclusions?

### 3.1. Picking a PRIMARY KEY Does Not Change Functional Dependencies

Suppose a table is declared as:

~~~sql
CREATE TABLE registrations_flat (
    student_id VARCHAR(10) NOT NULL,
    course_id  VARCHAR(10) NOT NULL,
    mentor_id  VARCHAR(10) NOT NULL,
    PRIMARY KEY (student_id, mentor_id),
    UNIQUE (student_id, course_id)
);
~~~

**PRIMARY KEY (student_id, mentor_id)** and **UNIQUE (student_id, course_id)** along with **NOT NULL** columns enforce uniqueness of the two pairs, yet they do not remove the rule **M → C**. At the same time, those two constraints alone **do not enforce** M → C: the same M can still appear with a different C for two different students.

For example, if the table initially contains **(S01, C10, M01)**, the following statement is accepted by the declared constraints:

~~~sql
-- Violates business rule M -> C, yet does not violate
-- PRIMARY KEY (student_id, mentor_id) or UNIQUE (student_id, course_id).
INSERT INTO registrations_flat (student_id, course_id, mentor_id)
VALUES ('S02', 'C20', 'M01');
~~~

To protect M → C, place the rule into a constrainable structure or add suitable write controls. **A primary key is a key selection for row identity; BCNF is evaluated over all active functional dependencies, not just the primary key.**

### 3.2. Adding a Surrogate ID Does Not Automatically Solve the Problem

If the table uses **registration_id** as its primary key while still enforcing **UNIQUE(S, C)** and **UNIQUE(S, M)** and preserving **M → C**, M still fails to uniquely identify the entire row. The dependency M → C still violates BCNF.

There is another important consequence: when adding a unique surrogate ID, S, C, and M might all appear **non-prime** unless the declared candidate keys and business rules are preserved; you must **recompute all true candidate keys** of the expanded relation before concluding 3NF. You cannot blindly carry over the 3NF status of R(S,C,M) to R(registration_id,S,C,M) without re-evaluating.

When constraints keep **(S, C)** and **(S, M)** as candidate keys, C and M remain prime; if you drop those business uniqueness rules and keep only the ID, that becomes **a different model and constraint set**, likely introducing worse anomalies.

## 4. Comparing via Abstract Relations with Multiple Candidate Keys

Business examples build intuition; algebraic examples verify conclusions independent of column names. Examine three cases on relations over attributes A, B, C.

### 4.1. Case A: Satisfies 3NF, Fails BCNF

~~~text
R(A, B, C)
F = { AB -> C, C -> B }
~~~

Compute closures:

~~~text
A+  = {A}
B+  = {B}
C+  = {C, B}
AB+ = {A, B, C}
AC+ = {A, C, B}
~~~

**AB** and **AC** are candidate keys; all attributes are prime. In **C → B**, the left-hand side **C is not a superkey**, yet B is prime because it belongs to AB. Therefore:

**3NF: satisfied. BCNF: violated.**

This is the exact same dependency structure as the student example if we map **A = S, B = C, C = M**. The value of the abstract example is that it can be solved purely via closure without guessing "which column feels more important."

### 4.2. Case B: Multiple Candidate Keys Yet Still in BCNF

~~~text
R(A, B, C)
F = { A -> B, A -> C, BC -> A }
~~~

**A⁺ = {A, B, C}** and **(BC)⁺ = {B, C, A}**, so the candidate keys are **A** and **BC**. Neither B nor C alone determines the entire relation. Checking the given dependencies:

- **A → B**: A is a candidate key, valid under BCNF.
- **A → C**: A is a candidate key, valid under BCNF.
- **BC → A**: BC is a candidate key, valid under BCNF.

Non-trivial dependencies derived from this set F also have a superkey on the left-hand side. Therefore:

**3NF: satisfied. BCNF: satisfied.**

This example refutes the claim **"having multiple candidate keys automatically violates BCNF."** What matters is **whether there exists a non-superkey determinant**, not the count of keys.

### 4.3. Case C: Fails 3NF and Therefore Also Fails BCNF

~~~text
R(A, B, C)
F = { A -> B, B -> C }
~~~

Under F, **A** is the sole candidate key; B and C are non-prime. For **B → C**, B is not a superkey and C is non-prime:

**3NF: violated. BCNF: violated.**

This is the familiar transitive dependency pattern. You do not even need BCNF to catch the issue.

| Case | Candidate Keys | Decisive Dependency | 3NF | BCNF |
| --- | --- | --- | --- | --- |
| A: **AB → C; C → B** | AB, AC | C → B; C not superkey, B is prime | Satisfied | Violated |
| B: **A → BC; BC → A** | A, BC | Every meaningful determinant is a superkey | Satisfied | Satisfied |
| C: **A → B; B → C** | A | B → C; B not superkey, C non-prime | Violated | Violated |

## 5. Decomposing the Student Example to Reach BCNF

Returning to **R(S, C, M)**, the dependency **M → C** violates BCNF. We decompose:

~~~text
R1(M, C)  -- each mentor handles one course
R2(S, M)  -- which mentor supervises a student
~~~

Comparison:

| Child Table | Core Projected Dependency | Candidate Key | BCNF? |
| --- | --- | --- | --- |
| **mentor_courses(M, C)** | M → C | M | Satisfied: M is a superkey |
| **student_mentors(S, M)** | No non-trivial dependency from original F in this two-column table | (S, M) | Satisfied |

### 5.1. Checking the Lossless-Join Property

The intersection of the two attribute sets is **{M}**. Because **M → C**, M determines **all of R1(M, C)**. By the binary decomposition condition, this decomposition is a **lossless join** for original data satisfying F:

~~~text
R(S, C, M)
   -> R1(M, C)
      R2(S, M)

R1 ∩ R2 = {M}
M -> C
=> Natural join of R1 and R2 recovers the exact valid original R.
~~~

Practical consequence: each mentor has only one course in **mentor_courses**, so joining enrollment rows on M will never multiply rows across different courses.

### 5.2. Runnable PostgreSQL Schema

~~~sql
CREATE TABLE students (
    student_id VARCHAR(10) PRIMARY KEY,
    student_name VARCHAR(100) NOT NULL
);

CREATE TABLE courses (
    course_id VARCHAR(10) PRIMARY KEY,
    course_title VARCHAR(100) NOT NULL
);

CREATE TABLE mentor_courses (
    mentor_id VARCHAR(10) PRIMARY KEY,
    course_id VARCHAR(10) NOT NULL
        REFERENCES courses(course_id)
);

CREATE TABLE student_mentors (
    student_id VARCHAR(10) NOT NULL
        REFERENCES students(student_id),
    mentor_id VARCHAR(10) NOT NULL
        REFERENCES mentor_courses(mentor_id),
    PRIMARY KEY (student_id, mentor_id)
);

INSERT INTO students (student_id, student_name) VALUES
    ('S01', 'An'), ('S02', 'Bình'), ('S03', 'Chi');

INSERT INTO courses (course_id, course_title) VALUES
    ('C10', 'Databases'), ('C20', 'Java');

INSERT INTO mentor_courses (mentor_id, course_id) VALUES
    ('M01', 'C10'), ('M02', 'C10'), ('M03', 'C20');

INSERT INTO student_mentors (student_id, mentor_id) VALUES
    ('S01', 'M01'), ('S02', 'M01'), ('S03', 'M02'), ('S01', 'M03');

-- Reconstruct (S, C, M) tuples.
SELECT sm.student_id, mc.course_id, sm.mentor_id
FROM student_mentors AS sm
JOIN mentor_courses AS mc
  ON mc.mentor_id = sm.mentor_id
ORDER BY sm.student_id, mc.course_id;
~~~

The **students** and **courses** tables manage independent reference entities. The core BCNF decomposition here consists of **mentor_courses(M,C)** and **student_mentors(S,M)**.

### 5.3. Lossless Joins Can Still Fail to Preserve Dependencies

The decomposition preserves **M → C** inside **mentor_courses**, yet **(S, C) → M** cannot be checked from any single child table alone:

- **student_mentors** knows only S and M.
- **mentor_courses** knows only M and C.
- Knowing whether a student has two mentors for the same course requires combining both tables.

This is the distinction between:

**Lossless join:** joining the projections of a valid original relation reconstructs that original relation.

**Dependency preservation:** original dependencies can be inferred from the dependencies on the child relations without checking across joins.

This decomposition is **lossless yet does not preserve SC → M**.

### 5.4. Concrete Counterexample for Lost Constraint Enforcement

In the sample data, both M01 and M02 teach C10, while S01 is already studying C10 with M01. The primary key of **student_mentors** still allows inserting:

~~~sql
INSERT INTO student_mentors (student_id, mentor_id)
VALUES ('S01', 'M02');
~~~

The join result now contains two rows:

~~~text
student_id | course_id | mentor_id
-----------+-----------+----------
S01        | C10       | M01
S01        | C10       | M02
~~~

This **violates SC → M** in the original relation, even though every primary key and foreign key on both child tables is satisfied. The join did not become "lossy"; the issue is that **the decomposed schema permits a data state violating the original business rule**.

Detection query:

~~~sql
SELECT
    sm.student_id,
    mc.course_id,
    COUNT(DISTINCT sm.mentor_id) AS mentor_count
FROM student_mentors AS sm
JOIN mentor_courses AS mc
  ON mc.mentor_id = sm.mentor_id
GROUP BY sm.student_id, mc.course_id
HAVING COUNT(DISTINCT sm.mentor_id) > 1;
~~~

The query above only **detects** violations; it does not block writes. If you want to keep the BCNF schema, you may need business-level enforcement, triggers, or transactions designed to handle write concurrency; do not rely solely on an unguarded "check-then-INSERT" in application code.

## 6. When Is Keeping 3NF Easier for Preserving Rules?

One option is to keep the registration relation containing **S, C, M**, declare its candidate keys, and build an enforcement mechanism for **M → C**. The registration relation remains in **3NF** under the stated business dependencies because all attributes are prime; it **violates BCNF** because M is not a superkey.

Example implementation in PostgreSQL using a mentor-assignment catalog table:

~~~sql
CREATE TABLE mentor_course_catalog (
    mentor_id VARCHAR(10) PRIMARY KEY,
    course_id VARCHAR(10) NOT NULL,
    UNIQUE (mentor_id, course_id)
);

CREATE TABLE student_course_mentor_3nf (
    student_id VARCHAR(10) NOT NULL,
    course_id  VARCHAR(10) NOT NULL,
    mentor_id  VARCHAR(10) NOT NULL,
    PRIMARY KEY (student_id, course_id),
    UNIQUE (student_id, mentor_id),
    FOREIGN KEY (mentor_id, course_id)
        REFERENCES mentor_course_catalog(mentor_id, course_id)
);
~~~

Explanation of enforced invariants:

- **PRIMARY KEY (student_id, course_id)**: enforces **SC → M**, i.e., each student–course pair has at most one mentor.
- **UNIQUE (student_id, mentor_id)**: expresses candidate key **SM** in the model, with non-NULL attributes.
- **PRIMARY KEY (mentor_id)** in the catalog combined with **FOREIGN KEY (mentor_id, course_id)** on the registration table: ensures every row with a given mentor_id uses the catalog's course_id, thereby enforcing **M → C** across the two tables.
- **UNIQUE (mentor_id, course_id)** in the catalog: provides a unique target for the composite foreign key in PostgreSQL; it does not mean a mentor has multiple courses, because **mentor_id** is already the primary key.

This option keeps **course_id** in the registration table alongside the mentor assignment, so changes to a mentor's assigned course must stay synchronized. In return, the independent invariants are easily expressed with primary keys, unique constraints, and foreign keys. This is a **concrete storage design**, not to be confused with the theoretical claim "3NF automatically enforces every dependency."

Trade-offs:

| Criterion | Keeping 3NF Registration Relation with S,C,M | Core BCNF Decomposition into (M,C) and (S,M) |
| --- | --- | --- |
| Dependency **SC → M** | Directly enforceable via key on S,C | Requires cross-table control across two tables |
| Dependency **M → C** | Needs extra protection, e.g., catalog + composite FK | Directly enforced by key M on table M,C |
| Redundant **course_id** per mentor | Can repeat in registration table | Not repeated in table S,M |
| Joins when querying a student's courses | S,C,M already in registration record | Must join table S,M with M,C |
| Expressing all rules in simple SQL constraints | Easier for SC → M, but M → C needs handling | Easier for M → C, but SC → M needs handling |

In normalization theory, the **3NF synthesis** algorithm always yields a decomposition that is both **lossless-join** and **dependency-preserving**. Conversely, **not every set of dependencies** admits a BCNF decomposition that preserves both properties simultaneously. Therefore, choosing BCNF or a controlled 3NF design must be guided by constraint enforcement requirements, not just normal form labels.

## 7. Workflow for Distinguishing 3NF and BCNF on a New Problem

1. **Lock down grain and effective time.** Does a row represent a term registration, a single session booking, or full history? Functional dependencies change when context changes.
2. **Collect business-accurate functional dependencies.** Ask whether each left-hand side can map to multiple right-hand values; avoid inferring rules from a few sample rows.
3. **Compute closures to find all candidate keys.** Start with attributes that never appear on the right-hand side of any dependency, then add needed attributes and prune redundant ones.
4. **Mark prime attributes.** Any attribute inside **any** candidate key is prime, even if it is not part of the chosen primary key.
5. **Check 3NF.** For each non-trivial X → A, if X is not a superkey, is A prime?
6. **Check BCNF.** For the same dependency, X must be a superkey; there is no exception for prime A.
7. **If decomposing, verify lossless join.** For two child relations, the shared attribute intersection must determine all attributes of at least one side; never split tables simply because column names look related.
8. **Verify dependency preservation and enforcement.** Try inserting rows that pass primary/foreign keys yet violate old business rules; determine whether extra constraints, transactions, or model changes are needed.
9. **Evaluate physical design last.** Assess indexes, joins, read/write volume, and reporting or document copies. If intentionally denormalizing, specify the source of truth and synchronization rules.

### Do Not Overlook the Time Dimension

The dependency **mentor_id → course_id** holds only in the **single fixed term** example. If the system stores multiple terms, a person may teach C10 in one term and C20 in the next. Then the rule may become:

~~~text
(mentor_id, term_id) -> course_id
~~~

If one person teaches multiple courses in the same term, even that new dependency does not hold; you must model **sections**, **teaching assignments**, or **enrollments** according to the real domain. You cannot declare a table in violation of BCNF based on a functional dependency that **no longer holds**.

Likewise, across relational, document, graph, or analytical models, repeated values can represent historical facts at different points in time or read-optimized copies. Evaluating them properly requires distinguishing **copies of the same current fact** from **distinct facts across time**.

## 8. Verification Exercises

### Exercise 1. Computing Keys and Normal Forms

Given **R(A, B, C, D)** with functional dependencies:

~~~text
AB -> C
C  -> B
AB -> D
~~~

Assume no additional business dependencies beyond logical consequences of the set above.

**Tasks:**

1. Find all candidate keys and identify the prime attributes.
2. Does R satisfy 3NF? Does R satisfy BCNF?
3. Does attribute D affect the conclusion that "C → B is permitted in 3NF"?
4. If decomposing along C → B, propose R1 and R2 and check the lossless condition.

<details>
<summary>Suggested Solution for Exercise 1</summary>

Because **A** never appears on any right-hand side, every key must contain A. We have:

~~~text
AB+ = {A, B, C, D}
AC+ = {A, C, B, D}
C+  = {C, B}
~~~

The candidate keys are **AB** and **AC**. Attributes **A, B, C** are prime; **D** is non-prime.

**AB → C** and **AB → D** have a key on the left-hand side. **C → B** has C not a superkey, yet B is prime, so **R satisfies 3NF**, while **R fails BCNF**. Adding D does not take away B's primality; D is determined by key AB and introduces no new 3NF violation.

Decomposing on **C → B** produces **R1(C, B)** and **R2(A, C, D)**. The intersection is {C}, and **C → B**, so the decomposition is lossless. You must still check projected dependencies on each table and whether **AB → D** remains preserved.

</details>

### Exercise 2. Comparing Two Designs with the Same Three Columns

Given two tables sharing the attribute set **R(P, Q, R)**:

~~~text
Design X: { PQ -> R, R -> Q }
Design Y: { P -> Q, P -> R, QR -> P }
~~~

For each design, find candidate keys, check 3NF and BCNF. Explain why the statement "multiple candidate keys cause BCNF violations" is inaccurate.

<details>
<summary>Suggested Solution for Exercise 2</summary>

- **Design X:** candidate keys are **PQ** and **PR**. For **R → Q**, R is not a superkey while Q is prime. The table satisfies **3NF** and fails **BCNF**.
- **Design Y:** candidate keys are **P** and **QR**. Every meaningful non-trivial dependency has a superkey on the left-hand side. The table satisfies **BCNF**, and therefore also **3NF**.

Both designs have multiple candidate keys; only X has a dependency violating BCNF.

</details>

### Exercise 3. Counterexample After Decomposition

Given **mentor_courses(M,C)** and **student_mentors(S,M)**:

- Write two rows in **student_mentors** and rows in **mentor_courses** that cause the join to violate **SC → M** while still satisfying the keys of both tables.
- Explain why querying **COUNT(DISTINCT mentor_id) > 1** grouped by **(student_id, course_id)** detects the error but is not a preventive constraint.
- Propose how to handle this if "a student chooses at most one mentor per course" is a critical invariant that must never be violated, even under two concurrent writes.

**Approach:** pair the same S with two different M values that both map to the same C. To prevent the error, use a model keeping a unique key on (S, C), or a write/constraint mechanism capable of locking the contention scope; simply running a pre-check SELECT in the application layer is insufficient under concurrent writes.

## 9. Common Misconceptions

| Misconception | What to Check |
| --- | --- |
| "Both 3NF and BCNF just require every left-hand side to be a key." | 3NF includes the extra case where **the right-hand side is a prime attribute**. |
| "An attribute outside the PRIMARY KEY is non-prime." | You must check **all candidate keys**, including candidate keys not chosen as PRIMARY KEY. |
| "Having two candidate keys guarantees BCNF fails." | Multiple keys can still satisfy BCNF if every non-trivial determinant is a superkey. |
| "Adding an ID as PRIMARY KEY eliminates BCNF violations." | An ID does not remove functional dependencies dictated by the business. |
| "Splitting on a violating dependency always solves all constraints." | You must verify **lossless join**, child-table normal forms, and **dependency preservation**. |
| "Lossless means invalid data cannot be inserted after decomposition." | Lossless concerns reconstructing valid original relations; write-time rules may still lose preservation. |
| "UNIQUE(M) in the registration table solves M → C." | That would also forbid multiple students from sharing one mentor, breaking business rules; pick the right structure. |
| "A 4-row example is enough to confirm a functional dependency." | Rules must come from the business domain and hold across all valid states. |

## 10. Key Takeaways

To distinguish 3NF from BCNF, do not start from the primary key; **find all candidate keys**, identify **prime attributes**, and then test **every non-trivial functional dependency X → A**. If X is a superkey, the dependency satisfies both 3NF and BCNF. If X is not a superkey yet A is prime, the dependency **is permitted in 3NF but violates BCNF**. If both conditions fail, the dependency violates both normal forms.

The **SC → M** and **M → C** example yields two candidate keys **SC** and **SM**; every attribute is prime so the relation satisfies **3NF**, yet **M → C** violates **BCNF**. Decomposition removes mentor–course duplication while making **SC → M** harder to enforce. Thus, final modeling decisions must verify **functional dependencies, lossless join, constraint preservation, and real write paths**.
