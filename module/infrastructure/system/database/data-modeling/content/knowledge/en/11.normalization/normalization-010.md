# Checking Lossless Joins and Dependency Preservation After Decomposition

**Schema decomposition** replaces one large relation with multiple smaller relations to limit duplicated data and insertion, update, and deletion anomalies. Yet splitting tables does not automatically improve a model: some splits cause JOINs to manufacture **records that never existed**, and others lose the ability to **check functional dependencies locally on each table**.

Therefore, before finalizing a decomposition in the **Normalization** chapter, you must answer two **independent** questions:

1. **Lossless join:** from the decomposed tables, can every valid original relation be reconstructed exactly via natural JOIN?
2. **Dependency preservation:** can the functional dependencies that must be protected in the original relation be inferred from the dependencies enforced locally on each new table?

This lesson belongs to the **DATABASE_DATA_MODELING** module: translating business requirements into a clear relational model with keys, constraints, verification checks, and design decisions defensible by both formal reasoning and real data. The examples use the formal relational model and PostgreSQL to highlight the difference between **theoretical soundness** and **production operability**.

## 1. Opening Problem: If We Split Tables and JOIN, Is It Guaranteed Correct?

Suppose an initial relation records which student takes which course and who teaches that course:

| student_id | course_id | instructor_id |
| --- | --- | --- |
| S01 | C10 | I07 |
| S02 | C10 | I07 |
| S01 | C20 | I09 |

The business states:

> Each **course_id** has exactly one assigned **instructor_id** within the scope under consideration.

The functional dependency is **course_id → instructor_id**. We can split the relation into:

**StudentCourses(student_id, course_id)**

| student_id | course_id |
| --- | --- |
| S01 | C10 |
| S02 | C10 |
| S01 | C20 |

**CourseInstructors(course_id, instructor_id)**

| course_id | instructor_id |
| --- | --- |
| C10 | I07 |
| C20 | I09 |

Joining the two tables on course_id recovers the exact three original tuples. That is a **lossless-join decomposition**. At the same time, the rule course_id → instructor_id can be enforced by a unique key on **CourseInstructors.course_id**; meaning this decomposition is also **dependency-preserving**.

However, both conclusions must be proven from **business rules**, not merely because one test dataset produces a matching JOIN result. A design might happen to JOIN cleanly on 100 rows today yet produce wrong results when a new valid record arrives tomorrow.

## 2. Notation and Precise Definitions

Let:

- **R(A, B, C, …)** be the original relation schema with attribute set R.
- **F** be the set of **functional dependencies (FDs)** confirmed by the business.
- **r** be any valid relation instance of R satisfying all FDs in F.
- **ρ = {R₁, R₂, …, Rₙ}** be the set of decomposed child schemas.
- **π_X(r)** be the projection of relation r onto the attributes in X.
- **⋈** be the natural join over identically named attributes.
- **F⁺** be the closure of F, i.e., all functional dependencies implied by F.
- **X⁺_F** be the attribute closure of X under F.

A baseline requirement is **R₁ ∪ R₂ ∪ … ∪ Rₙ = R**: every attribute of the original schema still appears in at least one child schema. If you drop an attribute the business still needs, information is already lost at the structural level.

### 2.1. Lossless Join

A decomposition ρ is **lossless-join with respect to F** when, **for every** instance r satisfying F:

~~~text
r = π_R1(r) ⋈ π_R2(r) ⋈ ... ⋈ π_Rn(r)
~~~

Meaning: decomposing and rejoining returns the exact original **set of tuples**, adding no *spurious tuples* and dropping no tuples.

With natural joins over projections derived from **the same r** under relational set semantics, the join always contains all original tuples. Thus, the primary risk of a flawed decomposition is **generating extra spurious tuple combinations**. This differs from physical tables diverging on updates or containing NULLs, where real-world SQL JOINs can also lose rows.

### 2.2. Dependency Preservation

Let **Fᵢ = π_Rᵢ(F)** be the set of all FDs implied by F that use only attributes in Rᵢ, namely:

~~~text
Fᵢ = { X → Y | X ∪ Y ⊆ Rᵢ and F ⊨ X → Y }
~~~

A decomposition is **dependency-preserving** if:

~~~text
(F₁ ∪ F₂ ∪ ... ∪ Fₙ)⁺ = F⁺
~~~

An equivalent test: **every FD in the original set F can be inferred from the union of local FDs**. The converse holds automatically because every local FD was already implied by F.

Crucial point: Fᵢ does **not** consist solely of FDs written verbatim in F that happen to sit inside Rᵢ. It also contains **derived FDs** via transitivity, such as A → C inferred from A → B and B → C.

If a dependency is **not preserved**, you can still enforce it via cross-table JOINs, triggers, or transactions, yet **you cannot rely solely on checking local FDs within individual tables**.

## 3. Core Tools: Functional Dependencies and Attribute Closure

A functional dependency **X → Y** states that in every valid relation instance, **two tuples with the same X value must have the same Y value**.

It is a rule of the business domain, **not** a statistical coincidence observed in current data.

Example:

~~~text
R(A, B, C)
F = { A → B, B → C }
~~~

Then:

- **A⁺ = {A, B, C}**: A implies B, and B implies C.
- **B⁺ = {B, C}**.
- **C⁺ = {C}**.
- **A** is a candidate key of R if no other constraints introduce another minimal key.

### 3.1. Algorithm for Computing Closure X⁺

~~~text
Input: attribute set X, dependency set F
Result: X_plus

X_plus := X
repeat
    changed := false
    for each (LHS → RHS) in F:
        if LHS ⊆ X_plus and RHS ⊄ X_plus:
            X_plus := X_plus ∪ RHS
            changed := true
until changed = false

return X_plus
~~~

To test **F ⊨ X → Y**, compute X⁺ using the algorithm above; if **Y ⊆ X⁺**, the FD is implied.

Example with F = {A → B, B → C}: test A → C by computing A⁺. Start with A; add B; then add C. Because C is in A⁺, conclude A → C.

### 3.2. Three Easy-to-Miss Caveats

1. **A candidate key** is a **minimal** attribute set determining all of R; a superkey with extra attributes is not a candidate key.
2. **An FD can have multiple attributes on the left-hand side**, e.g., (student_id, course_id) → grade. Never infer student_id → grade from it.
3. **An FD does not guarantee a child row exists.** A rule like "every confirmed Order has at least one OrderLine" is a cardinality constraint, not a simple FD.

## 4. Sign of a Lossy JOIN: Spurious Tuples

Consider R(A, B, C) with **no FD forcing B to determine A or C**. Original relation:

| A | B | C |
| --- | --- | --- |
| a1 | b1 | c1 |
| a2 | b1 | c2 |

Decompose into **R₁(A, B)** and **R₂(B, C)**:

**R₁**

| A | B |
| --- | --- |
| a1 | b1 |
| a2 | b1 |

**R₂**

| B | C |
| --- | --- |
| b1 | c1 |
| b1 | c2 |

Natural JOIN on B yields:

| A | B | C | Verdict |
| --- | --- | --- | --- |
| a1 | b1 | c1 | Original tuple |
| a1 | b1 | c2 | **Spurious tuple** |
| a2 | b1 | c1 | **Spurious tuple** |
| a2 | b1 | c2 | Original tuple |

Because both rows of R₁ have B = b1, they join with **both** rows of R₂. The information "which A goes with which C" has been erased from the child tables.

An illustrative PostgreSQL query:

~~~sql
WITH original(a, b, c) AS (
    VALUES
        ('a1', 'b1', 'c1'),
        ('a2', 'b1', 'c2')
),
r_ab AS (
    SELECT DISTINCT a, b FROM original
),
r_bc AS (
    SELECT DISTINCT b, c FROM original
),
reconstructed AS (
    SELECT r_ab.a, r_ab.b, r_bc.c
    FROM r_ab JOIN r_bc USING (b)
)
SELECT a, b, c
FROM reconstructed
EXCEPT
SELECT a, b, c
FROM original;
-- Two spurious tuples: (a1,b1,c2) and (a2,b1,c1).
~~~

This is a **lossy-join decomposition** even though **no column was dropped**: A, B, and C all still appear across the tables. What was "lost" is the **exact pairing between values**, leading to fabricated rows when rejoining.

**Never equate "more rows after JOIN" with an error in every case.** A valid one-to-many JOIN naturally multiplies rows legitimately. A decomposition error occurs when the result contains **tuples that cannot be corroborated by any valid original relation**.

## 5. Lossless-Join Criterion for Binary Decomposition

When decomposing R into **R₁ and R₂**, considering only FD constraints in F, the necessary and sufficient condition is:

~~~text
(R₁ ∩ R₂) → R₁    belongs to F⁺
          OR
(R₁ ∩ R₂) → R₂    belongs to F⁺
~~~

In other words: **the shared attribute set must determine all attributes of at least one of the two child relations**.

### 5.1. Testing via Closure

Let **X = R₁ ∩ R₂**.

1. Compute X⁺ using **F of the original schema**.
2. If **R₁ ⊆ X⁺** or **R₂ ⊆ X⁺**, the decomposition is **lossless** under FDs.
3. If neither is a subset of X⁺, the decomposition is **not guaranteed lossless** under F.

Example:

~~~text
R(A,B,C), F = { A → B, B → C }
R₁(A,B), R₂(B,C)

X = R₁ ∩ R₂ = {B}
B⁺ = {B,C}
R₂ = {B,C} ⊆ B⁺
⇒ Lossless join.
~~~

B is the shared attribute; thanks to **B → C**, each value of B pairs with only **one** valid value of C. Thus joining AB with BC cannot pair A with an arbitrary C.

### 5.2. Why Does the Criterion Work? Proof Intuition

Each tuple in the JOIN result is formed by pairing a tuple from π_R₁(r) and a tuple from π_R₂(r) that agree on X = R₁ ∩ R₂.

If X → R₂, every original tuple with the same X must have the exact same R₂ values. Therefore, the matched R₂ tuple cannot carry R₂ attributes different from the R₂ values of the very original tuple that produced the R₁ half. The resulting tuple must already exist in r.

The symmetric argument holds if X → R₁. If neither dependency holds, an instance satisfying F can exist whose projections, when joined, manufacture spurious tuples.

### 5.3. Scope of This Criterion

The criterion above is **necessary and sufficient when F contains only functional dependencies**. When stronger constraints such as **multivalued dependencies (MVDs)** hold, a decomposition can still be lossless thanks to an MVD even without an FD determining one side.

For example, with R(A, B, C) and **A ↠ B**, the model allows all B–C combinations for a given A, so decomposing into AB and AC is lossless under the MVD. Do not use "not lossless under FDs" to dismiss a proven MVD constraint.

Furthermore, the binary criterion **must not be applied mechanically** to three or more tables by arbitrarily checking isolated pairs. For multi-table decompositions, you need a global proof, a valid sequence of lossless binary joins, or the **chase** algorithm.

## 6. Lossless Does Not Mean Dependency-Preserving

Reusing:

~~~text
R(A,B,C)
F = { A → B, B → C }
~~~

Compare two different decompositions.

### 6.1. Good Decomposition: AB and BC

~~~text
R₁(A,B), R₂(B,C)
~~~

- **Lossless:** intersection is B; B → BC because B → C.
- **Preserving:** R₁ enforces A → B, R₂ enforces B → C.
- A → C follows transitively from the two local dependencies.
- Can use UNIQUE/PK on A in table AB and on B in table BC.

This is an example where **both properties hold**.

### 6.2. Lossless Yet Not FD-Preserving Decomposition: AB and AC

~~~text
R₁(A,B), R₂(A,C)
~~~

- **Lossless:** intersection is A; A → AB and A → AC (because A → B → C).
- **Local FD in AB:** A → B.
- **Local FD in AC:** A → C.
- **Original FD B → C:** cannot be inferred from {A → B, A → C} alone.

Prove the last point with closure:

~~~text
G = { A → B, A → C }
B⁺_G = {B}
C ∉ B⁺_G
⇒ G does not imply B → C.
~~~

You can have data that is **valid inside each child table**:

**AB**

| A | B |
| --- | --- |
| a1 | b1 |
| a2 | b1 |

**AC**

| A | C |
| --- | --- |
| a1 | c1 |
| a2 | c2 |

Joining on A produces exactly two tuples, with no spurious combinations:

~~~text
(a1, b1, c1)
(a2, b1, c2)
~~~

Yet these two tuples **violate B → C**: same B = b1 with different C values.

This is the core distinction:

- **Lossless** guarantees: *if the child tables are projections of a valid original relation*, rejoining does not fabricate extra tuples.
- **Preserving** guarantees: *when operating directly on each child table*, local FD checks suffice to prevent states violating the original FDs.

A decomposition can accurately reconstruct **valid initial data** while still permitting **new physical states that violate business rules** unless cross-table constraints are added.

### 6.3. Conversely: Dependency-Preserving Yet Lossy JOIN

Change the assumption to:

~~~text
R(A,B,C)
F = { A → B }
R₁(A,B), R₂(B,C)
~~~

A → B is fully enforced in R₁, so **the given dependency is preserved**. However:

~~~text
R₁ ∩ R₂ = {B}
B⁺_F = {B}
B does not determine A or C
⇒ Not lossless.
~~~

The two tuples (a1,b1,c1) and (a2,b1,c2) both satisfy A → B, yet joining AB and BC still creates two spurious tuples just as in section 4.

**Conclusion:** FD preservation **does not imply** lossless join; lossless join **does not imply** FD preservation.

## 7. Systematically Checking Dependency Preservation

Given decomposition ρ = {R₁,…,Rₙ}.

### 7.1. Step 1: List Business FDs and Compute a Cover

From business requirements, write F clearly; optionally compute a **minimal/canonical cover** to shrink the set of dependencies to check:

- Split FDs with multi-attribute right-hand sides into single-attribute RHS FDs.
- Remove extraneous attributes on the left-hand side while preserving closure equivalence.
- Drop redundant FDs still implied by the remaining FDs.

A minimal cover simplifies checking without **changing F⁺**. Never "simplify" by discarding an FD merely because it is rarely violated in sample data.

### 7.2. Step 2: Find FDs Projected onto Each Table

For Rᵢ, only dependencies having **both left-hand and right-hand attributes** inside Rᵢ are local FDs checkable within that table alone.

Crucial: you must account for **derived** FDs. With F = {A → B, B → C}:

~~~text
π_AB(F) contains A → B
π_AC(F) contains A → C   (even though A → C is not written explicitly in F)
π_BC(F) contains B → C
~~~

Computing all projected FDs explicitly can be expensive when there are many attributes; in practice, use a direct preservation-checking algorithm instead of enumerating every derivable FD.

### 7.3. Step 3: Check Each FD of F

Let **G = F₁ ∪ F₂ ∪ … ∪ Fₙ**. For each **X → Y** in F, compute X⁺ under G. If **Y ⊆ X⁺_G** holds every time, all FDs are preserved.

Summary table:

| Original F | Decomposition | FDs Enforced in Child Tables | Conclusion |
| --- | --- | --- | --- |
| A → B, B → C | AB, BC | A → B in AB; B → C in BC | **Preserved** |
| A → B, B → C | AB, AC | A → B in AB; A → C in AC | **Does not preserve B → C** |
| A → B | AB, BC | A → B in AB | **Preserved** yet potentially lossy |

### 7.4. Direct Checking Algorithm Without Enumerating Every Fᵢ

To check whether **X → Y** is preserved, iterate closures using the original F:

~~~text
Z := X
repeat
    old_Z := Z
    for each relation Rᵢ:
        T := (Z ∩ Rᵢ)⁺_F ∩ Rᵢ
        Z := Z ∪ T
until Z = old_Z

return (Y ⊆ Z)
~~~

Explanation: at each table Rᵢ, you may only use attributes **already known and present in that table** to derive additional attributes **also present in that table**. Repeat until no further attributes can be added.

If the algorithm returns TRUE for every FD in an equivalent cover of F, the decomposition preserves F. If any FD fails, enforce it via cross-table constraints or change the design.

Example **AB + AC** with F = {A → B, B → C}, testing **B → C**:

~~~text
Z = {B}
R_AB: (Z ∩ AB) = {B}; B⁺_F ∩ AB = {B}
R_AC: (Z ∩ AC) = ∅; no new attributes added
Fixed point Z = {B}; missing C.
⇒ B → C is not preserved.
~~~

Example **AB + BC**, same FDs:

~~~text
Z = {B}
R_BC: B⁺_F ∩ BC = {B,C}
Fixed point contains C.
⇒ B → C is preserved.
~~~

This algorithm tests **derivability via local dependencies**, rather than trying to force every business rule into one table. Aggregate totals, at-least-one-child existence, or state-based authorization rules may not be FDs at all.

## 8. The Chase Algorithm for Testing Lossless Join

When there are **more than two** child schemas, or you want a systematic proof procedure, you can use a **chase tableau** under the set of functional dependencies.

### 8.1. Idea

Build a symbolic table:

- **One row** for each child relation Rᵢ.
- **One column** for each attribute Aⱼ of R.
- If attribute Aⱼ **is present** in Rᵢ, place the distinguished symbol **aⱼ**.
- If attribute Aⱼ **is absent**, place a unique subscripted symbol **bᵢⱼ** (distinct from all other b symbols).
- For each FD X → Y, if two rows have **identical symbols on X**, equate their symbols on Y.
- When equating symbols, if one of them is **aⱼ**, prefer replacing with aⱼ; all cells matching the replaced symbol must update consistently.
- Repeat until no changes occur. If **at least one row consists entirely of a-symbols across all columns**, the decomposition is **lossless under the FDs**.

In the FD chase, obtaining an all-a row is the success criterion; if the process terminates with no all-a row, the decomposition is not guaranteed lossless under the given FDs.

### 8.2. Step-by-Step Example: R(A,B,C) → AB, BC

Given **F = {A → B, B → C}**. Initialize:

| Row | A | B | C |
| --- | --- | --- | --- |
| R_AB | a_A | a_B | b_1C |
| R_BC | b_2A | a_B | a_C |

Both rows share **a_B** in column B. Because **B → C**, their C values must match, so replace **b_1C** with **a_C**:

| Row | A | B | C |
| --- | --- | --- | --- |
| R_AB | **a_A** | **a_B** | **a_C** |
| R_BC | b_2A | a_B | a_C |

Row R_AB is now all a-symbols ⇒ **lossless join**.

### 8.3. What If There Is No Strong Enough FD?

With R(A,B,C) → AB,BC and empty F, no chase step modifies the initial tableau. No all-a row appears ⇒ the decomposition is **not lossless** under known FDs, matching the spurious-tuple example.

### 8.4. Limitations to Keep in Mind

- The chase here uses **functional dependencies**; when MVDs, join dependencies, or general constraints are involved, the chase rules and assumptions change.
- If you can prove a **step-by-step** join sequence is lossless at each step under the relevant dependencies, that is a sufficient proof for multi-table decomposition; you do not strictly have to build a tableau.
- Never check arbitrary pairs of tables in isolation and jump to concluding the entire multi-way join is valid.
- Counting JOIN rows on live data never substitutes for a proof across **all valid instances**.

## 9. Dependency Preservation When Choosing Between 3NF and BCNF

Normalization usually targets **3NF** or **BCNF** to curb update anomalies. However, **BCNF does not always preserve every FD upon decomposition**, even when lossless.

### 9.1. A Lossless BCNF Decomposition That Loses One Dependency

Consider:

~~~text
R(A,B,C)
F = { AB → C, C → B }
~~~

Find keys:

- **(AB)⁺ = ABC** ⇒ AB is a candidate key.
- **(AC)⁺ = ABC** via C → B ⇒ AC is also a candidate key.
- A, B, and C are all **prime attributes** because each lies in at least one candidate key.

The FD **C → B** violates BCNF because **C is not a superkey** of R. One decomposition along C → B is:

~~~text
R₁(C,B)
R₂(A,C)
~~~

**Lossless:**

~~~text
R₁ ∩ R₂ = {C}
C → B ⇒ C → CB = R₁
⇒ Lossless join.
~~~

**Does not preserve AB → C:**

- R₁ has **C → B**.
- R₂ has no required non-trivial FD between A and C under F.
- From local constraints on CB and AC alone, **AB → C** cannot be inferred.

You can insert:

**CB**

| C | B |
| --- | --- |
| c1 | b1 |
| c2 | b1 |

**AC**

| A | C |
| --- | --- |
| a1 | c1 |
| a1 | c2 |

Joining on C produces:

~~~text
(a1, b1, c1)
(a1, b1, c2)
~~~

Both child tables satisfy their local FDs, yet the same **AB = (a1,b1)** now maps to two different C values ⇒ **violating AB → C**. Enforcing that FD on the decomposed schema requires multi-table coordination or a different design.

**Note:** the original R in this example already satisfies **3NF**, because B is a prime attribute. Thus a valid option is **keeping R in 3NF** to preserve dependencies, rather than forcing a BCNF split that makes enforcing AB → C harder.

### 9.2. Why Is 3NF Often the Balanced Choice?

There exists a **3NF schema synthesis** algorithm based on a minimal cover of F that creates relations for FDs and adds a relation containing a candidate key when needed. Executed properly, it guarantees:

- **Lossless join**.
- **Dependency preservation**.
- Every resulting relation satisfies **3NF**.

Typical steps:

1. Compute a minimal/canonical cover of F.
2. For each FD of the form X → A (or grouped by common left-hand side), create a relation with X ∪ {A}.
3. Drop any relation completely contained inside another generated relation unless design needs dictate otherwise.
4. If no generated relation contains **a candidate key of the original R**, add one relation containing that key.
5. Re-verify lossless join and preservation; select PK/FKs and related business rules.

Example:

~~~text
R(A,B,C,D)
F = { A → B, B → C, C → D }
~~~

Natural 3NF decomposition:

~~~text
R_AB(A,B)
R_BC(B,C)
R_CD(C,D)
~~~

- **Preserving:** each original FD lives intact inside one child table.
- **Lossless:** AB ⋈ BC is lossless because B → BC; joining next with CD on C is lossless because C → CD.
- Each child table has a key on the left-hand side of its FD.
- A is a candidate key of the original R and appears in R_AB, so no extra key-only table is needed.

This example also achieves BCNF. The trade-off arises only for **specific FD sets**—not every BCNF decomposition loses a dependency.

### 9.3. How to Decide

If BCNF loses a critical business FD that cannot be enforced cheaply and reliably across separate tables, **3NF may be the better choice**. Conversely, if duplication risk is severe and the lost dependency can be safely enforced through a dedicated mechanism, BCNF decomposition remains worthwhile.

**Never choose a normal form just because its name sounds "higher."** Weigh total cost across correctness enforcement, business changes, queries, and transactions.

## 10. PostgreSQL Implementation: Illustrating Enforceable FDs

### 10.1. Lossless and FD-Preserving Decomposition

Given R(StudentID, CourseID, InstructorID) and FD CourseID → InstructorID:

~~~sql
CREATE TABLE course_instructors (
    course_id BIGINT PRIMARY KEY,
    instructor_id BIGINT NOT NULL
);

CREATE TABLE student_courses (
    student_id BIGINT NOT NULL,
    course_id BIGINT NOT NULL
        REFERENCES course_instructors(course_id)
        ON DELETE RESTRICT,
    PRIMARY KEY (student_id, course_id)
);

-- Sample data:
INSERT INTO course_instructors (course_id, instructor_id)
VALUES (10, 7), (20, 9);

INSERT INTO student_courses (student_id, course_id)
VALUES (1, 10), (2, 10), (1, 20);

-- Reconstruct relation at three-attribute level:
SELECT sc.student_id, sc.course_id, ci.instructor_id
FROM student_courses AS sc
JOIN course_instructors AS ci USING (course_id)
ORDER BY sc.student_id, sc.course_id;
~~~

**course_id PRIMARY KEY** in course_instructors enforces CourseID → InstructorID. The foreign key in student_courses ensures every enrolled course **has a matching CourseInstructor row**, preventing lost rows in physical JOINs due to orphaned references. The composite key in student_courses prevents duplicate student–course pairs.

These choices illustrate **physical schema constraints**, complementing the formal lossless proof. The formal proof assumes child tables are genuinely **projections of one valid original relation**; a system writing two separate tables also needs PKs, FKs, transactions, and update rules to maintain that consistency.

If the business changes so that a course can have different instructors per term or section, **CourseID → InstructorID** no longer holds. Redesign the dependency—for instance **(CourseID, TermID, SectionID) → InstructorID** if the new policy fits—rather than keeping the old key and forcing invalid data.

### 10.2. Lossless Yet Missing FD Preservation in SQL

With R(A,B,C), F = {A → B, B → C}, splitting into AB and AC might look like:

~~~sql
CREATE TABLE demo_ab (
    a TEXT PRIMARY KEY,
    b TEXT NOT NULL
);

CREATE TABLE demo_ac (
    a TEXT PRIMARY KEY REFERENCES demo_ab(a),
    c TEXT NOT NULL
);

INSERT INTO demo_ab (a,b)
VALUES ('a1','b1'), ('a2','b1');

INSERT INTO demo_ac (a,c)
VALUES ('a1','c1'), ('a2','c2');

SELECT ab.a, ab.b, ac.c
FROM demo_ab AS ab
JOIN demo_ac AS ac USING (a)
ORDER BY ab.a;
~~~

Both tables pass their keys and FKs:

- **A → B** is enforced by PK A on demo_ab.
- **A → C** is enforced by PK A on demo_ac.
- Yet **B → C is not enforced**.

The JOIN returns two rows with the same B = b1 and different C values. **No FK in this example can enforce B → C**, because B and C do not reside together in one table with a corresponding UNIQUE/FD. This is a concrete SQL illustration of **a dependency not being preserved**.

If B → C is a mandatory business rule, a better design uses:

~~~sql
CREATE TABLE demo_bc (
    b TEXT PRIMARY KEY,
    c TEXT NOT NULL
);

CREATE TABLE demo_ab_preserving (
    a TEXT PRIMARY KEY,
    b TEXT NOT NULL REFERENCES demo_bc(b)
);
~~~

B → C is enforced by the PK of demo_bc; A → B by the PK of demo_ab_preserving; and the AB, BC split is also lossless because B → BC.

### 10.3. Even Preserved FDs Still Need Explicit Constraint Implementation

"Dependency preservation" is a **property of a schema decomposition**; it does not mean the DBMS automatically generates UNIQUE/FKs or knows business FDs on its own. If a local dependency X → Y must be enforced, you must explicitly build keys, UNIQUE constraints, triggers, or validation logic.

An FD like **CourseID → InstructorID** maps cleanly to a key on CourseID. A complex FD over a table with many rows and status-dependent exceptions may require additional modeling. Never equate every mathematical FD with a single simple UNIQUE statement.

## 11. Checking on Sample Data: Helpful, Not a Proof

Given a real source table, you can compare **the original relation** against **the joined projections**.

Suppose a table **enrollment_source(student_id, course_id, instructor_id)** exists with non-NULL columns and distinct tuples. Query:

~~~sql
WITH student_course AS (
    SELECT DISTINCT student_id, course_id
    FROM enrollment_source
),
course_instructor AS (
    SELECT DISTINCT course_id, instructor_id
    FROM enrollment_source
),
rebuilt AS (
    SELECT sc.student_id, sc.course_id, ci.instructor_id
    FROM student_course AS sc
    JOIN course_instructor AS ci USING (course_id)
),
spurious AS (
    SELECT student_id, course_id, instructor_id FROM rebuilt
    EXCEPT
    SELECT student_id, course_id, instructor_id FROM enrollment_source
),
missing AS (
    SELECT student_id, course_id, instructor_id FROM enrollment_source
    EXCEPT
    SELECT student_id, course_id, instructor_id FROM rebuilt
)
SELECT
    (SELECT COUNT(*) FROM spurious) AS spurious_count,
    (SELECT COUNT(*) FROM missing) AS missing_count;
~~~

If both counts equal **0**, the JOIN currently recovers the exact **tuple set on the tested dataset**. Yet that **does not prove the decomposition is lossless for all valid future data**. You still need an argument grounded in FDs or business constraints.

To spot an FD already violated in existing data, such as **CourseID → InstructorID** (non-NULL columns):

~~~sql
SELECT course_id
FROM enrollment_source
GROUP BY course_id
HAVING COUNT(DISTINCT instructor_id) > 1;
~~~

Zero returned rows only tells you **no violation appeared in the inspected data**. It does not replace confirming the FD with the business. When NULLs or missing-value semantics exist, COUNT(DISTINCT ...) may miss cases needing review.

### A Key Difference Between Relational Algebra and SQL

The lossless definition relies on **set semantics**: each tuple appears once. SQL by default allows **duplicate rows** (bag/multiset semantics), and JOINs can multiply rows when keys are non-unique. That is why the verification query uses **DISTINCT** and **EXCEPT** to compare tuple sets.

In addition, standard SQL JOIN equality **does not treat NULL = NULL as TRUE**. Classical FD theory and natural joins in the relational model do not assume SQL's three-valued NULL logic. Therefore, specify NULL/NOT NULL policies, keys, and referential presence separately when moving from formal proofs to real data.

## 12. Update Complications: Why Does Dependency Preservation Matter?

An FD can be enforced within one table using an appropriate PK/UNIQUE, yet if its determinant and dependent attributes live in **different tables**, validating every new row may require a JOIN or cross-table transaction logic.

### 12.1. Scenario Where B → C Is Not Preserved

In the AB + AC decomposition, to insert a tuple with a new A, the application must verify:

- Whether B already appears in AB;
- If B already appears, which C all existing A values linked to B have in AC;
- Whether the new tuple's C matches the C required by B.

That is checking **B → C via a JOIN**, not within a single table. Without appropriate locking or constraints, two concurrent transactions could both observe B absent and insert two different A rows sharing the same B with conflicting C values.

**Failing FD preservation does not automatically corrupt data**, yet it makes correctness enforcement **more expensive and easier to miss** if implemented inconsistently.

### 12.2. Redesigning Rather Than Patching After a JOIN

If B → C is a true invariant, placing **(B,C)** into one table where B is the key is usually far clearer:

~~~text
BC(B PRIMARY KEY, C)
AB(A PRIMARY KEY, B FOREIGN KEY REFERENCES BC)
~~~

Then:

- Two different C values cannot exist for one B.
- Creating a new A must reference an existing B.
- Updating B/C facts happens in one place instead of across many A rows.

Still, not every cross-table rule is an FD or reducible to UNIQUE. For example, "every CONFIRMED order has at least one line" is an existence constraint; "sum of line totals equals invoice amount" is an aggregate invariant. Dependency preservation does not replace designing those invariants.

## 13. Trade-Offs Between Normalization, Performance, and Constraints

A decomposition can achieve both lossless join and preservation yet require extra JOINs for queries; conversely, a wide table avoids JOINs at the cost of duplicated data and update anomalies.

| Dimension | Design Question |
| --- | --- |
| Lossless join | Do the new tables accurately reconstruct **valid original relations**? |
| FD preservation | Can every critical FD be checked on **individual tables** without cross-table JOIN checks? |
| Normalization | Is each table in 3NF or BCNF? Does any duplicated data cause update/delete anomalies? |
| Keys and references | Do candidate keys, UNIQUE, PK, and FK enforce the FDs and relationships? |
| Queries | Are the extra JOINs acceptable given data volume and SLAs? |
| Transactions | Do inserts/updates/deletes of one logical entity require atomic multi-table writes? |
| History | Do FDs vary over time, version, or tenant scope? |
| Evolution | When a new entity type, state, or rule arrives, will schema changes break old FDs? |

### 13.1. Context- and Time-Dependent FDs

The statement "CourseID → InstructorID" can hold **within one term** yet fail across multiple terms. A more accurate FD may be:

~~~text
(CourseID, TermID) → InstructorID
~~~

If a course has multiple sections, **SectionID** may also be required. Decomposing on a wrong FD creates overly tight constraints or a schema incapable of representing real data.

Similarly, in multi-tenant systems:

~~~text
(TenantID, ExternalCustomerCode) → CustomerID
~~~

is completely different from a global **ExternalCustomerCode → CustomerID**. Keys and projections must preserve tenant boundaries, or records from different tenants could collide on joins.

### 13.2. Denormalization and Derived Structures

In reporting systems, you may intentionally maintain summary tables, dimensions, or denormalized snapshots to accelerate reads. Keeping multiple representations of the same fact raises further questions:

- Which table is the **source of truth**?
- When source data changes, are derived tables updated **synchronously or asynchronously**?
- What is the acceptable staleness window?
- What checks verify that derived data does not contradict source invariants?
- If a JOIN multiplies metrics, is the **grain** of the fact table properly defined?

Denormalizing **does not change** the definitions of lossless join or preservation, yet it introduces consistency invariants between source and derived copies.

## 14. Connections to Document, Graph, and Analytical Models

Both criteria stem from relational theory and functional dependencies. In other paradigms, you still need to protect **information recoverability** and **consistency rules**, though you should not treat every representation as a relational decomposition under the same formula.

| Storage Model | Counterpart to Recoverability | Counterpart to Rule Preservation |
| --- | --- | --- |
| **Relational** | Joining projections produces no spurious tuples | Local FDs imply all original FDs |
| **Document** | Splitting/embedding data while preserving IDs and object links | Schema validation, cross-document consistency rules, concurrency controls |
| **Graph** | Splitting nodes/edges while preserving edge types, directions, and IDs | Edge type constraints, uniqueness, multiplicity, path constraints |
| **Analytical/Warehouse** | Fact–dimension/bridge JOINs neither inflate nor drop events unintentionally | Keys, grain, dimension history, metric aggregation rules |

### Document: Splitting Parallel Arrays Loses Correlation

Suppose an order has two line items, each with **productId** and **unitPrice**. Splitting them into two independent arrays `productIds` and `prices` without a line identifier makes re-pairing them risk assigning the wrong price to a product. That mirrors **correlation loss during decomposition**.

A safer approach stores **each line as a complete object**, or uses a line key to correlate separated collections. Attribute rules and transactions still need protection.

### Graph: Multiple Paths Do Not Mean Multiple Events

If a Category node has multiple parents, multiple paths can lead from a product to the same ancestor group. When traversing or joining edges to sum revenue, failing to deduplicate by the right fact and ancestor double-counts a single transaction. This resembles **spurious tuples or join multiplication**, governed by multi-path graph semantics.

### Analytics: Lock Down Grain Before Joining

A fact at the **OrderLine** grain may reference Customer, Product, and multiple product tags. Joining the fact directly to many tags multiplies rows. If the goal is allocating revenue across tags, explicit weights or attribution rules are needed; if the goal is total revenue, avoid multiplication. **SUM(DISTINCT amount)** does not fix the bug because distinct events can share identical amounts.

## 15. Practical Checklist Before Accepting a Decomposition

1. **Define R and F from the business.** Check tenant scope, time, statuses, and exceptions; never guess FDs from sample data alone.
2. **Find candidate keys.** Use attribute closure X⁺ to find superkeys and minimize them into candidate keys.
3. **Propose child schemas.** Specify each table's attributes; verify their union equals R.
4. **Verify lossless join.** For two tables use R₁∩R₂ and F⁺; for three or more use the chase or a step-by-step join proof.
5. **Verify dependency preservation.** Identify local FDs or run the per-table closure algorithm; check all critical FDs.
6. **Check 3NF/BCNF of each table.** Weigh redundancy reduction against any dependency lost if forcing BCNF.
7. **Design enforcement mechanisms.** Translate keys and FDs into PK, UNIQUE, FK, or supplemental controls. Never assume "FD-preserving" means physical constraints already exist.
8. **Write counterexample queries.** Look for inputs that could generate spurious tuples, orphaned records, or FD violations after independent updates.
9. **Test with data and concurrent transactions.** Test INSERT, UPDATE, DELETE, state transitions, and migration; ensure all writers uphold the same invariants.
10. **Document the design decision.** Record why 3NF/BCNF was chosen, which dependencies are preserved, which rules require JOINs/triggers, and accepted risks.

### Verification Summary Template

~~~text
Original relation: R(A, B, C)
Business FDs: { A → B, B → C }
Proposed decomposition: { R_AB(A,B), R_BC(B,C) }

Attribute coverage: PASS
Candidate key of R: A
Lossless-join check:
  R_AB ∩ R_BC = {B}
  B+_F = {B,C}
  B+ contains R_BC → PASS
Dependency preservation check:
  A → B enforced on R_AB
  B → C enforced on R_BC
  → PASS
Planned keys/FKs:
  R_BC: PK(B)
  R_AB: PK(A), FK(B) → R_BC(B)
Rules outside FD scope:
  Verify NULLs, lifecycle, concurrent writes, and update permissions.
~~~

Such documentation clarifies what has been **proven**, what is merely **assumed**, and what still requires physical-level verification.

## 16. Self-Check Exercises with Guided Solutions

### Exercise 1. Is the Binary Decomposition Lossless?

**Prompt:**

~~~text
R(A,B,C,D)
F = { A → B, B → C }
R₁(A,B), R₂(A,C,D)
~~~

**Guided Solution:** The intersection is {A}; A⁺_F = {A,B,C}. This set contains R₁={A,B}, so **the decomposition is lossless** even though D is not derived from A. The intersection only needs to determine **one** side.

### Exercise 2. Dependency Preservation?

**Prompt:** With the same R(A,B,C,D), F = {A → B, B → C}, does decomposing into **AB** and **ACD** preserve B → C?

**Guided Solution:** AB enforces A → B; ACD has A → C. No local FD enforces **B → C**. The closure of B under the union of local FDs is just {B}, so B → C is **not preserved**. This decomposition is lossless (Exercise 1) yet not dependency-preserving.

### Exercise 3. Is One Shared Attribute Enough?

**Prompt:** R(Student, Course, Grade), FD (Student, Course) → Grade. Proposed split: StudentCourse(Student,Course) and StudentGrade(Student,Grade). Is it lossless?

**Guided Solution:** The intersection is {Student}. Under F, Grade is determined only by the **pair (Student,Course)**; neither Student → Course nor Student → Grade holds. Because the intersection determines neither side, the decomposition is **not lossless under F**. A student taking two courses with two different grades will produce spurious course–grade pairs when joined.

### Exercise 4. Mini Chase

**Prompt:** R(A,B,C) → AB and BC; F = {B → C}. Fill the tableau and run the chase.

**Guided Solution:** Row AB = (a_A,a_B,b_1C); row BC = (b_2A,a_B,a_C). Both rows match on B, so B → C turns b_1C into a_C. Row AB becomes all a-symbols ⇒ **lossless**.

### Exercise 5. 3NF or BCNF?

**Prompt:**

~~~text
R(A,B,C), F = { AB → C, C → B }
~~~

Find keys, check BCNF, and decompose along C → B.

**Guided Solution:** The two candidate keys are **AB and AC**. FD C → B violates BCNF because C is not a superkey, yet R still satisfies 3NF because B is prime. Decomposing into **CB and AC** is lossless via C → B, yet **does not preserve AB → C**. Keeping 3NF avoids needing cross-table JOIN checks for AB → C.

### Exercise 6. Can You Prove Losslessness from Test Data?

**Prompt:** After splitting a large table, joining the child tables in staging returns the exact 10,000 rows, neither extra nor missing. Can you conclude the decomposition is lossless?

**Guided Solution:** **Not yet.** That only shows the result matches on **the test dataset**. Losslessness requires every valid instance r satisfying F to reconstruct accurately; you must prove it from confirmed dependencies. Future data may share join-column values and expose a flawed decomposition.

### Exercise 7. Time-Dependent FD

**Prompt:** A Course can have different instructors across different terms. The old design used CourseID → InstructorID. What must change before checking losslessness?

**Guided Solution:** Confirm the exact scope where the FD holds—for example, **(CourseID, TermID) → InstructorID** if each course has one instructor per term, or add SectionID if multiple sections exist. Keys and decompositions built on an outdated FD no longer reflect real data. Any proof based on a false FD is unreliable.

### Exercise 8. Preserving FDs Yet Lossy

**Prompt:** R(A,B,C), F = {A → B}; split into AB and BC. Is the dependency preserved? Is the JOIN lossless?

**Guided Solution:** FD A → B lies completely in AB and is therefore **preserved**. Yet the intersection is B; B⁺={B}, which determines neither AB nor BC. The decomposition is **not lossless**, demonstrating that the two criteria are independent.

## 17. Key Takeaways

- **Lossless join:** projecting a valid original relation onto child tables and rejoining **neither adds spurious tuples nor drops original tuples**.
- **Dependency preservation:** the original business FDs can be inferred from the union of **local FDs** after decomposition, enabling enforcement without multi-table JOIN checks.
- For a **binary decomposition under FDs**, the intersection R₁∩R₂ must determine **all of R₁ or all of R₂**.
- **Lossless join and preservation are independent.** A design can satisfy one without satisfying the other.
- **The chase** checks losslessness for multi-table decompositions; **attribute closure** checks FDs and dependency preservation.
- **3NF synthesis** guarantees both lossless join and preservation; **BCNF decomposition** is lossless yet can sometimes lose preservation of certain FDs.
- The theory rests on **business-accurate FDs** and relational set semantics. In real SQL systems, also manage **NULLs, duplicate records, PK/FKs, transactions, concurrent writes, and history**.

An acceptable decomposition does more than cut down repeated columns. It preserves **business truth under JOINs**, keeps **enforceable integrity rules intact**, and balances query and update costs as the system evolves.
