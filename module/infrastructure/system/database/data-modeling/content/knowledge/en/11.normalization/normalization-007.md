# Fourth Normal Form and Eliminating Inappropriate Multivalued Dependencies

**Fourth Normal Form (4NF)** addresses a type of redundancy that even **BCNF** can miss: multiple **mutually independent** sets of values merged into a single relation. When an entity has multiple languages and multiple hobbies, storing every language–hobby pair in one table causes the row count to grow as the product of set sizes, even though there is no business relationship between the two sets.

To identify this situation properly, we use a **multivalued dependency (MVD)**, written **X ↠ Y** or **X ->> Y**. 4NF requires: **for every non-trivial multivalued dependency X ↠ Y, X must be a superkey**. This lesson belongs to the **Normalization** chapter of the **DATABASE_DATA_MODELING** module, helping you translate business rules into relations with clear keys and constraints, verify decompositions, and distinguish independent value sets from data with true associative semantics.

## 1. Scenario: A Student Has Multiple Languages and Hobbies

Suppose a student profile application manages:

- Each student is identified by **student_id**.
- Each student can use **multiple languages**.
- Each student can have **multiple hobbies**.
- The list of languages and the list of hobbies are **independent**: a language is not tied to a specific hobby.
- A student may not have declared any languages, any hobbies, or either yet.

An initial table has three attributes:

| student_id | language_code | hobby_code |
| --- | --- | --- |
| S01 | EN | CHESS |
| S01 | EN | CYCLING |
| S01 | JA | CHESS |
| S01 | JA | CYCLING |

For S01, the system only needs to represent **two language facts** (EN, JA) and **two hobby facts** (CHESS, CYCLING). Yet the table holds **four pairs**:

~~~text
Languages: {EN, JA}       Hobbies: {CHESS, CYCLING}

EN  × CHESS
EN  × CYCLING
JA  × CHESS
JA  × CYCLING
~~~

As item counts grow, repetition multiplies:

| Languages (m) | Hobbies (n) | Merged Table: m × n Rows | Two Independent Tables: m + n Rows |
| ---: | ---: | ---: | ---: |
| 2 | 2 | 4 | 4 |
| 3 | 4 | 12 | 7 |
| 5 | 8 | 40 | 13 |
| 10 | 10 | 100 | 20 |

This compares **association rows** for one student having both sets, excluding the student identity row. Actual storage cost also depends on row width and indexes; the key point is the **product m × n** versus the **sum m + n**.

### 1.1. The Merged Table Can Already Be in BCNF

PostgreSQL example:

~~~sql
CREATE TABLE student_interests_flat (
    student_id     VARCHAR(10) NOT NULL,
    language_code  VARCHAR(10) NOT NULL,
    hobby_code     VARCHAR(20) NOT NULL,
    PRIMARY KEY (student_id, language_code, hobby_code)
);

INSERT INTO student_interests_flat
    (student_id, language_code, hobby_code)
VALUES
    ('S01', 'EN', 'CHESS'),
    ('S01', 'EN', 'CYCLING'),
    ('S01', 'JA', 'CHESS'),
    ('S01', 'JA', 'CYCLING');
~~~

Within the rules above, there are **no non-trivial functional dependencies** such as **student_id → language_code**, **student_id → hobby_code**, or **language_code → hobby_code**. One student has multiple languages and multiple hobbies.

Assuming no additional business functional dependencies, the triple **(student_id, language_code, hobby_code)** is a candidate key. Because there is no non-trivial functional dependency whose left-hand side is not a superkey, the table **satisfies BCNF**, as well as all lower normal forms. Yet it still suffers from redundancy caused by **independent value sets**. Evaluating it requires 4NF.

## 2. What Is a Multivalued Dependency?

### 2.1. Intuition: A Set Y Is Independent of the Remainder Z

Given a relation **R(X, Y, Z)**, where X, Y, and Z are disjoint attribute sets that together form all of R, the multivalued dependency:

~~~text
X ->> Y
~~~

expresses that for a fixed value of X, **the set of Y values can combine independently with the set of Z values**. Whenever two tuples share the same X:

~~~text
(x, y1, z1)
(x, y2, z2)
~~~

the relation must also contain the two swapped tuples:

~~~text
(x, y1, z2)
(x, y2, z1)
~~~

For each X, the relation's tuples form the **Cartesian product** between the Y values and Z values recorded for X.

In the student table:

~~~text
X = student_id
Y = language_code
Z = hobby_code
~~~

Given **(S01, EN, CHESS)** and **(S01, JA, CYCLING)**, independence requires **(S01, EN, CYCLING)** and **(S01, JA, CHESS)** as well. The four sample rows satisfy this condition.

**Note:** simply having a "list of languages" for a student is not enough to establish an MVD. An MVD is a stronger rule about **independent pairing** between Y and the remaining attributes Z across **every valid state**.

### 2.2. Two Complementary Multivalued Dependencies

From the independence in the example:

~~~text
student_id ->> language_code
student_id ->> hobby_code
~~~

The two dependencies are linked by the **complementation rule**: in relation R, if **X ↠ Y** then **X ↠ R − (X ∪ Y)**. With the three columns S, L, H, **S ↠ L** implies **S ↠ H**.

Conversely, the functional dependency **student_id → language_code** is **false** if a student speaks two languages. An MVD does not say X determines **one** Y; it describes the independence of **the Y values** from the rest of the relation.

### 2.3. Comparing Functional Dependencies and Multivalued Dependencies

| Criterion | Functional Dependency **X → Y** | Multivalued Dependency **X ↠ Y** |
| --- | --- | --- |
| Meaning | Each X has **at most one** Y | The Y values for X combine independently with the remaining attributes |
| Example | **department_id → department_name** | **student_id ↠ language_code** in the example |
| Can there be multiple Y for the same X? | No | Yes |
| Typical risk | Copying an attribute of another entity across many rows | Multiplying combinations between two independent sets |
| Related normal forms | 2NF, 3NF, BCNF | 4NF |

**Every functional dependency X → Y also implies the multivalued dependency X ↠ Y**, though the converse does not hold. Consequently, 4NF also covers issues caught by BCNF via functional dependencies and is strictly stronger than BCNF.

## 3. Definition of 4NF and the "Non-Trivial" Condition

A relation **R is in Fourth Normal Form (4NF)** if, for **every non-trivial MVD X ↠ Y** holding on R, **X is a superkey of R**.

Specifically:

- **Superkey:** a set of attributes determining the entire row under the relation's functional dependencies; need not be minimal.
- **Candidate key:** a minimal superkey.
- **Trivial MVD** if **Y ⊆ X** or **X ∪ Y = R** (where R denotes the attribute set).
- **Non-trivial MVD** if **Y is not a subset of X** and **X ∪ Y does not cover all attributes of R**.

Distinguishing them in R(S, L, H):

| Multivalued Dependency | Trivial? | Explanation |
| --- | --- | --- |
| **S ↠ S** | Yes | Right-hand side is contained in left-hand side |
| **S ↠ (L, H)** | Yes | Union of S, L, H is all of R |
| **S ↠ L** | **No** | S and L exclude H |
| **S ↠ H** | **No** | S and H exclude L |

In **student_interests_flat**, **S is not a superkey** because one student has multiple rows. **S ↠ L** and **S ↠ H** are non-trivial MVDs whose left-hand side is not a superkey. Thus the relation **violates 4NF**, even though it **satisfies BCNF** under the assumed functional dependencies.

## 4. Anomalies Caused by Merging Two Independent Sets

### 4.1. Insertion Anomaly

S01 learns a new language **FR**. Because the student currently has two hobbies, to keep representing every valid combination, the application must insert **two rows**:

~~~sql
INSERT INTO student_interests_flat
    (student_id, language_code, hobby_code)
VALUES
    ('S01', 'FR', 'CHESS'),
    ('S01', 'FR', 'CYCLING');
~~~

Inserting only one row leaves the table missing valid combinations required by the domain. If a student has **no hobbies yet**, **NOT NULL** columns prevent recording a language without inventing a dummy hobby.

### 4.2. Update Anomaly

If hobby code **CYCLING** is standardized to **BIKING** for S01, the application must update every row containing CYCLING for that student, regardless of language. Missing one row leaves the same student–hobby relationship inconsistently represented.

### 4.3. Deletion Anomaly

If S01 drops **CHESS** while still knowing EN and JA, deleting all rows with **hobby_code = CHESS** works only if another hobby keeps the language facts alive—otherwise deleting the last hobby wipes out all record of the student's languages, even though the student only wanted to remove a hobby.

The core issue is that the lifecycle of the **student–language** association is forced to move together with the **student–hobby** association.

## 5. Decomposing into Relations That Store Independent Facts

Given R(S, L, H) and the violating MVD **S ↠ L**, apply the decomposition:

~~~text
R1 = S ∪ L = (S, L)
R2 = R − (L − S) = (S, H)
~~~

Two new relations:

- **student_languages(student_id, language_code)**: each row states that the student uses **one language**.
- **student_hobbies(student_id, hobby_code)**: each row states that the student has **one hobby**.

Add a **students** table to store students independently, even when both sets are empty.

~~~mermaid
erDiagram
    STUDENTS ||--o{ STUDENT_LANGUAGES : "speaks"
    STUDENTS ||--o{ STUDENT_HOBBIES : "has hobby"
    STUDENTS {
        varchar student_id PK
        varchar student_name
    }
    STUDENT_LANGUAGES {
        varchar student_id PK, FK
        varchar language_code PK
    }
    STUDENT_HOBBIES {
        varchar student_id PK, FK
        varchar hobby_code PK
    }
~~~

### 5.1. SQL Schema

~~~sql
CREATE TABLE students (
    student_id VARCHAR(10) PRIMARY KEY,
    student_name VARCHAR(100) NOT NULL
);

CREATE TABLE student_languages (
    student_id VARCHAR(10) NOT NULL
        REFERENCES students(student_id),
    language_code VARCHAR(10) NOT NULL,
    PRIMARY KEY (student_id, language_code)
);

CREATE TABLE student_hobbies (
    student_id VARCHAR(10) NOT NULL
        REFERENCES students(student_id),
    hobby_code VARCHAR(20) NOT NULL,
    PRIMARY KEY (student_id, hobby_code)
);

INSERT INTO students (student_id, student_name) VALUES
    ('S01', 'An'), ('S02', 'Bình'), ('S03', 'Chi');

INSERT INTO student_languages (student_id, language_code) VALUES
    ('S01', 'EN'), ('S01', 'JA'), ('S02', 'FR');

INSERT INTO student_hobbies (student_id, hobby_code) VALUES
    ('S01', 'CHESS'), ('S01', 'CYCLING'),
    ('S02', 'PIANO'), ('S03', 'DRAWING');
~~~

Each association table captures **one kind of one-to-many relationship**. Composite primary keys prevent duplicating the same element for a student, and foreign keys block links to nonexistent students. **S03 having a hobby without any declared languages yet** is stored cleanly.

### 5.2. Operations Without Multiplying Combinations

**Adding a language:** insert just one row.

~~~sql
INSERT INTO student_languages (student_id, language_code)
VALUES ('S01', 'FR');
~~~

**Deleting a hobby:** leaves the language list untouched.

~~~sql
DELETE FROM student_hobbies
WHERE student_id = 'S01'
  AND hobby_code = 'CYCLING';
~~~

**Reading each list independently:**

~~~sql
SELECT language_code
FROM student_languages
WHERE student_id = 'S01'
ORDER BY language_code;

SELECT hobby_code
FROM student_hobbies
WHERE student_id = 'S01'
ORDER BY hobby_code;
~~~

A UI displaying two lists does not need to join the two tables. When all combinations are genuinely needed:

~~~sql
SELECT
    l.student_id,
    l.language_code,
    h.hobby_code
FROM student_languages AS l
JOIN student_hobbies AS h
    ON h.student_id = l.student_id
WHERE l.student_id = 'S01'
ORDER BY l.language_code, h.hobby_code;
~~~

The query materializes combinations **at read time**, instead of duplicating every pair in storage.

### 5.3. Counting Items Without Double-Counting Combinations

~~~sql
SELECT
    s.student_id,
    (SELECT COUNT(*)
     FROM student_languages AS l
     WHERE l.student_id = s.student_id) AS language_count,
    (SELECT COUNT(*)
     FROM student_hobbies AS h
     WHERE h.student_id = s.student_id) AS hobby_count
FROM students AS s
ORDER BY s.student_id;
~~~

Subqueries return separate counts of languages and hobbies, including **0**. Joining both child tables together on S produces **m × n** intermediate rows; **COUNT(*)** on that join would count combinations instead. Pre-aggregate before joining or use **COUNT(DISTINCT ...)** when appropriate.

## 6. Why Is a Valid Decomposition Lossless?

**Lossless-join decomposition** means the original relation can be reconstructed exactly from its projections, for every valid original state satisfying the dependencies under consideration.

For R(S,L,H), if **S ↠ L** holds, then:

~~~text
R = π(S,L)(R) ⋈ π(S,H)(R)
~~~

Joining on S reconstructs every L–H combination. It **does not generate spurious tuples** because the MVD definition already requires **every combination** for each S to exist in the original R; nor does it drop any original tuple because each tuple contributes to both projections.

Example:

~~~text
π(S,L):                  π(S,H):
S01, EN                 S01, CHESS
S01, JA                 S01, CYCLING
~~~

Joining the two projections recovers the exact four original rows.

**Boundary:** if an L–H pair represents a specific combined fact where not all combinations are valid, joining can generate spurious tuples. In that case, the assumed MVD is **false** and you must not decompose along it.

### 6.1. Under Which Rules Do the Two Child Tables Satisfy 4NF?

Per the problem statement:

- **student_languages(S,L)** manages one student–language pair.
- **student_hobbies(S,H)** manages one student–hobby pair.
- No additional non-trivial functional dependencies or MVDs with a non-superkey left-hand side are confirmed by the business on either child table.

Therefore, the child relations **satisfy 4NF under the assumed dependencies**. Never conclude a table is in 4NF merely because it has few columns; evaluate the dependencies that hold on that specific relation.

## 7. Counterexample: Multiple Values That Are Not Independent

Suppose you manage **product–color–size**, where a product exists only in specific variants:

| product_id | color | size |
| --- | --- | --- |
| P01 | Red | S |
| P01 | Red | M |
| P01 | Blue | L |

Variants **(P01, Blue, S)**, **(P01, Blue, M)**, and **(P01, Red, L)** do not exist.

If split into two sets:

~~~text
product_colors:
  (P01, Red)
  (P01, Blue)

product_sizes:
  (P01, S)
  (P01, M)
  (P01, L)
~~~

and joined on product_id, you generate **2 × 3 = 6 combinations**, including three variants **that do not exist**.

Reason: **color and size are not independent**, because each pair is a meaningful variant of its own. The multivalued dependency **product_id ↠ color is false** on this relation: from **(P01, Red, S)** and **(P01, Blue, L)**, if the MVD held, **(P01, Red, L)** and **(P01, Blue, S)** would also have to exist.

A better design:

~~~text
products(product_id, ...)
product_variants(variant_id, product_id, color, size, ...)
~~~

Here each row in **product_variants** is a sellable variant. If the business ensures each color–size pair occurs at most once per product, add **UNIQUE(product_id, color, size)**. A production schema may also need SKU, inventory, and price per variant.

| Business Question | Independent Sets, Safe to Split | Meaningful Association, Keep Together |
| --- | --- | --- |
| Is a language tied to a specific hobby of the student? | No | — |
| Is every color sold in every available size? | Only if the business confirms so | Otherwise, store each valid variant |
| Which skills does a student use **in each project**? | Cannot split by student alone if skill depends on project | Store **(student_id, project_id, skill_id)** per combination |
| Does adding a new Y mean it automatically pairs with every existing Z? | Yes, per MVD semantics | No, valid combinations must be stated explicitly |

**Never infer an MVD from how sample data happens to look.** Seeing two columns with multiple values is not enough to prove independence. Confirm the business rule and check whether a join could manufacture invalid combinations.

## 8. Connections to BCNF, Surrogate Keys, and Document Models

### 8.1. Relationship Between Normal Forms

| Normal Form | Primary Dependency Class Controlled | Strictness |
| --- | --- | --- |
| **1NF** | Domain-appropriate values, avoiding hidden independently managed collections in one cell | Foundation |
| **2NF** | Partial functional dependencies of non-prime attributes on candidate keys | Stricter than 1NF |
| **3NF** | Functional dependencies X → A; allows exception when A is prime | Stricter than 2NF |
| **BCNF** | Every non-trivial functional dependency has a superkey on the left-hand side | Stricter than 3NF |
| **4NF** | Every **non-trivial multivalued dependency** has a superkey on the left-hand side | Stricter than BCNF |

Because every FD implies an MVD, any relation in 4NF is also in BCNF. The table in section 1 is a counterexample to the converse: **satisfying BCNF does not guarantee 4NF**.

### 8.2. Adding an ID Does Not Solve an MVD

Suppose you add **id** as the primary key to **student_interests_flat**. Each student still has multiple items in each set and the application still has to store every combination. A surrogate key only identifies each row; **it does not create a business relationship between languages and hobbies**.

4NF evaluation must start from functional dependencies, MVDs, and **grain**. Renaming columns, adding indexes, or changing the primary key does not alter the underlying combination rules.

### 8.3. Does Every JSON Array Violate 4NF?

**4NF is a criterion for the relational model**, whereas a document DBMS can represent two independent sets as two arrays:

~~~json
{
  "studentId": "S01",
  "languages": ["EN", "JA"],
  "hobbies": ["CHESS", "CYCLING"]
}
~~~

This storage pattern can fit well when the application routinely reads and updates the whole profile and enforces validation, deduplication, write permissions, and concurrency controls. Modern SQL also supports JSON or ARRAY, yet **storing an array in a column does not automatically provide foreign keys or per-element uniqueness constraints**.

When each language or hobby must be searched, referenced, validated, and managed independently across its lifecycle, two relational tables are usually easier to verify. If a flattened analytical table is needed, define the **source of truth**, the semantics of each combination, and the synchronization mechanism.

## 9. Process for Detecting and Resolving 4NF Violations

1. **Define the grain.** Does each row represent an independent pair, a genuinely coupled triple, or an event record?
2. **List functional dependencies and candidate keys.** Check 1NF through BCNF first; a table in BCNF can still contain an MVD violating 4NF.
3. **Spot multi-valued sets.** For the same X, are there multiple Y and multiple Z values? Are the two sets independent, or are only certain pairs valid?
4. **Verify the MVD semantically.** Given two tuples with the same X, must the swapped Y and Z tuples necessarily exist in every valid state?
5. **Check non-triviality.** If **Y ⊆ X** or **X ∪ Y = R**, the MVD is trivial and creates no 4NF violation.
6. **Check superkey status.** Use closure over the functional dependencies to check whether X determines all attributes of R.
7. **Decompose on violations.** Apply **R1 = X ∪ Y** and **R2 = R − (Y − X)**; continue checking the child relations.
8. **Prove lossless join and protect constraints.** A valid MVD makes joining the projections lossless; add keys, foreign keys, and element-level rules.
9. **Test edge cases.** Empty Y, empty Z, one or many elements, inserting a new item, deleting the last item, and cases where a specific combination is forbidden.
10. **Optimize after the model is sound.** Evaluate indexes, joins, document models, or analytical models according to actual read/write workloads.

Querying existing combinations only spots missing swapped tuples and **does not prove an MVD**: current data might happen to be complete by coincidence. The decisive authority must be **business rules**, not a data sample alone.

## 10. Practice Exercises

### Exercise 1. Projects with Members and Tools

A project management system records:

| project_id | member_id | tool_id |
| --- | --- | --- |
| P01 | U01 | T01 |
| P01 | U01 | T02 |
| P01 | U02 | T01 |
| P01 | U02 | T02 |

Rule: assigning members to a project is **independent** of the approved tool list for the project; every project member is permitted to use every tool approved for that project. A project can have multiple members and multiple tools; there are no other non-trivial business functional dependencies.

**Tasks:**

1. Write the MVDs on project_id.
2. Find candidate keys; evaluate BCNF and 4NF.
3. Decompose into tables and specify primary keys.
4. Prove the decomposition is lossless and consider a project that has not been assigned any tools yet.

<details>
<summary>Suggested Solution for Exercise 1</summary>

~~~text
project_id ->> member_id
project_id ->> tool_id
~~~

Because there are no non-trivial FDs, the candidate key is **(project_id, member_id, tool_id)**. The table satisfies **BCNF** yet fails **4NF**: the non-trivial MVDs have project_id on the left-hand side, which is not a superkey.

Decompose into **project_members(project_id, member_id)** and **project_tools(project_id, tool_id)**, each with its respective attribute pair as primary key. Add **projects(project_id, ...)** to store projects independently, including projects with no tools yet.

Because every member–tool combination is valid under the rule, joining the two child tables on project_id recovers the exact original relation whenever both sets are non-empty. A project with no tools yet can still store its members without creating a dummy tool_id row.

</details>

### Exercise 2. When an MVD Is False

An e-commerce system stores variants:

~~~text
P01, RED, S
P01, RED, M
P01, BLUE, L
~~~

**Task:** check **product_id ↠ color**; if split into product_colors and product_sizes and then joined, which spurious tuples appear? Redesign to store only valid variants.

<details>
<summary>Suggested Solution for Exercise 2</summary>

The MVD **product_id ↠ color** is **false**. From **(P01, RED, S)** and **(P01, BLUE, L)**, swapping under the MVD would require **(P01, RED, L)** and **(P01, BLUE, S)**, neither of which is permitted.

Splitting and joining would manufacture **(P01, RED, L)**, **(P01, BLUE, S)**, and **(P01, BLUE, M)**. Instead, keep **product_variants(product_id, color, size, ...)** for combinations that genuinely exist, and declare keys or **UNIQUE** constraints per business rules.

</details>

### Exercise 3. Does an FD Create an MVD?

Given the relation:

~~~text
employees(employee_id, department_id, department_name)
department_id -> department_name
~~~

Determine whether **department_id ↠ department_name** follows, whether it is non-trivial, and whether the relation can satisfy BCNF/4NF when each department has multiple employees.

**Hint:** an FD implies an MVD. That MVD is non-trivial because **employee_id** remains outside the union of X and Y. When a department has multiple employees, department_id is not a superkey, so the dependency violates **BCNF** as an FD and violates **4NF** as an MVD. Extract **departments(department_id, department_name)** and keep **department_id** as a foreign key in **employees**.

## 11. Common Mistakes to Avoid

| Misconception | Accurate Evaluation |
| --- | --- |
| "Satisfying BCNF guarantees satisfying 4NF." | BCNF checks FDs; 4NF also checks **non-trivial MVDs**. |
| "Two columns repeating multiple values means there is an MVD." | You must verify the sets **combine independently** under business rules. |
| "An MVD is like an FD: each X has only one Y." | An MVD allows **multiple Y values** and governs how they combine with the remaining columns. |
| "Every MVD violates 4NF." | Only **non-trivial** MVDs where **X is not a superkey** violate 4NF. |
| "Joining two child tables produces many rows, so the split is lossy." | Under a valid MVD, the join equals the exact original relation; combinations appear at read time. |
| "Splitting color and size is always safe for any product." | If only specific color–size pairs are sold, joining **generates spurious variants**. |
| "Adding a surrogate ID brings the table into 4NF." | An ID does not change the independence between multi-valued sets. |
| "You must JOIN both child tables in every query." | When you only need one list, query that table alone; join only when combinations are needed. |

## 12. Key Takeaways

**4NF requires the left-hand side of every non-trivial multivalued dependency to be a superkey.** In the student example, **student_id ↠ language_code** and **student_id ↠ hobby_code** are two non-trivial MVDs: languages and hobbies are independent yet get multiplied into every pair when combined in one table. That table can satisfy BCNF and still require decomposition into **student_languages** and **student_hobbies**.

Decomposition decisions must rest on **combination semantics**. When sets are independent, splitting along a valid MVD keeps joins lossless and reduces insertion, update, and deletion anomalies. When specific combinations carry distinct meaning—like color and size of a product variant—splitting the two sets fabricates invalid data. Confirm business rules, check superkeys, and prove lossless join before optimizing indexes or selecting relational, document, or analytical models.
