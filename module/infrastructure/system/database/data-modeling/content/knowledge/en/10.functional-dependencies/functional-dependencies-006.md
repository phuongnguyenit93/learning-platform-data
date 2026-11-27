# Multivalued Dependencies and Independent Value Sets in the Same Relation

## Learning Objectives

In the **DATABASE_DATA_MODELING** module, we turn business rules into verifiable data schemas: identifying entities, relationships, keys, constraints, normal forms, and physical storage. A **multivalued dependency** (MVD) helps detect a type of redundancy that **functional dependency** (FD) analysis alone often misses: two **mutually independent** sets of values stored together in one table.

After this lesson, you will be able to:

1. Read and explain the notation \(X\twoheadrightarrow Y\) using the tuple-exchange rule.
2. Distinguish **one-to-many** from **multiple independent values**; determine when data requires all combinations.
3. Identify **trivial** and **non-trivial** multivalued dependencies and relate them to functional dependencies.
4. Use multivalued dependencies to check **Fourth Normal Form (4NF)** and perform **lossless-join** decompositions.
5. Design relational tables and SQL queries at the right grain, avoiding false assumptions from sample data and unintended Cartesian products.

## 1. Business Scenario: One Person Has Multiple Skills and Multiple Languages

Suppose an HR profile system stores:

~~~text
EMPLOYEE_PROFILE(employee_id, skill, language)
~~~

Confirmed business rules:

- An employee can possess **multiple skills**.
- An employee can use **multiple languages**.
- The **skill list** and the **language list** are managed **independently**. An employee knows Java and Python, and uses Vietnamese and English; a language is not an attribute of a specific skill.

If the table above is required to represent **all combinations** of independent skills and languages, the data for employee `NV01` looks like this:

| employee_id | skill | language |
|---|---|---|
| NV01 | Java | vi |
| NV01 | Java | en |
| NV01 | Python | vi |
| NV01 | Python | en |

The two actual lists are:

~~~text
Skills(NV01)    = {Java, Python}
Languages(NV01) = {vi, en}
~~~

To represent them in a single three-column relation, the table must store:

\[
\{\text{Java},\text{Python}\}\times\{\text{vi},\text{en}\}.
\]

The number of tuples is \(2\times2=4\). If an employee has 8 skills and 5 languages, the combined table requires \(8\times5=40\) combinations just to express 13 values across **two lists**.

Problems immediately follow: adding a new language requires inserting multiple rows, deleting a skill requires deleting multiple rows, and a missing combination can mislead readers into thinking a skill is not paired with a language. **Multivalued dependencies** formalize this exact independence.

## 2. Formal Definition of a Multivalued Dependency

Consider relation \(R(U)\). Choose attribute sets \(X,Y\subseteq U\) and let:

\[
Z=U-(X\cup Y).
\]

For easier interpretation, treat \(X\), \(Y\), and \(Z\) as three disjoint parts (if \(X\) and \(Y\) overlap, consider \(Y-X\)). A multivalued dependency:

\[
X\twoheadrightarrow Y
\]

means: **once the value of \(X\) is fixed, the set of \(Y\) values is independent of the values of the remaining attributes \(Z\)**.

### Tuple-Exchange Condition

Given **any two tuples** \(t_1,t_2\) of a valid relation state \(r\), if:

\[
t_1[X]=t_2[X],
\]

then there must exist two tuples \(t_3,t_4\in r\) such that:

| Attribute part | \(t_3\) takes from | \(t_4\) takes from |
|---|---|---|
| \(X\) | Same \(X\) value of \(t_1,t_2\) | Same \(X\) value of \(t_1,t_2\) |
| \(Y\) | \(t_1[Y]\) | \(t_2[Y]\) |
| \(Z\) | \(t_2[Z]\) | \(t_1[Z]\) |

In other words, when two tuples agree on \(X\), you can **swap their \(Y\) parts** while keeping their \(Z\) parts, and **both swapped combinations must exist** in a valid relation.

In our example:

~~~text
X = {employee_id}
Y = {skill}
Z = {language}
~~~

We have:

\[
\text{employee\_id}\twoheadrightarrow\text{skill}.
\]

Take two tuples:

~~~text
t1 = (NV01, Java,   vi)
t2 = (NV01, Python, en)
~~~

then the cross-combination tuples must also exist:

~~~text
t3 = (NV01, Java,   en)
t4 = (NV01, Python, vi)
~~~

When the remainder is just `language`, the MVD **complementation rule** also implies:

\[
\text{employee\_id}\twoheadrightarrow\text{language}.
\]

This condition applies to **every business-valid data state**. A few rows that happen to look like a Cartesian product are not enough to prove a multivalued dependency; independence must be confirmed by domain experts.

## 3. "Having Multiple Values" Does Not Mean "Multivalued Dependency"

For instance, an `order_id` key can be associated with multiple `product_id` values; this is a **one-to-many** relationship. That **does not automatically** create a non-trivial MVD.

Multivalued dependencies become relevant when **the same \(X\)** relates to two groups of attributes where choices in one group **do not constrain** choices in the other. The following table compares three different situations:

| Situation | Actual rule | Should we assume a Cartesian product? |
|---|---|---|
| Employee has independent skills and languages | Knowing Python does not depend on knowing English | **Yes**, if a three-column table forces representing two lists via every combination |
| A class has many students | `class_id` relates to many `student_id` | **Insufficient information** to claim a non-trivial MVD |
| A store offers shirt variants by **color–size** only in certain combinations | There is a red size M shirt but no red size XL shirt | **No**: each pair can be a distinct real-world variant |

Counterexample: table `SKU_VARIANT(product_id, color, size)` contains:

| product_id | color | size |
|---|---|---|
| SP01 | red | M |
| SP01 | blue | XL |

If only these two variants are actually sold, we **must not** generate `(SP01, red, XL)` and `(SP01, blue, M)`. **Color and size here form a business-meaningful pairing**, not two independent lists.

By contrast, the employee profile table only stores a **skill list** and a **language list**, so pairing them is an artifact of combined storage, not a statement about using a specific language to practice a specific skill.

**Crucial diagnostic question:** "If a new \(Y\) value is added for an \(X\), does the business permit and require it to appear alongside **every** existing \(Z\) value for that \(X\)?" If the answer is no, revisit the MVD assumption.

## 4. Distinguishing FDs and MVDs

A functional dependency:

\[
X\rightarrow Y
\]

means **each value of \(X\) determines at most one value of \(Y\)**.

A multivalued dependency:

\[
X\twoheadrightarrow Y
\]

allows **one \(X\) to have an entire set of \(Y\) values**, provided that set **does not depend on the remaining attributes** of the same tuple.

| Criterion | FD: \(X\rightarrow Y\) | MVD: \(X\twoheadrightarrow Y\) |
|---|---|---|
| What is determined | One value \(Y\) per \(X\) | A **set of values** \(Y\) independent of \(Z\) per \(X\) |
| Check on a relation | Two tuples with the same \(X\) must share \(Y\) | Swapped \(Y,Z\) pairs must exist |
| Example | `employee_id → employee_name` on a current-state table | `employee_id ↠ skill` on an independent skills–languages table |
| Related normal forms | 2NF, 3NF, BCNF | **4NF** |

### FDs Imply MVDs, but the Converse Is False

If \(X\rightarrow Y\), then \(X\twoheadrightarrow Y\). This is a fundamental inference rule for MVDs.

Reason: for each \(X\), \(Y\) has only one value, so any exchange of \(Y\) between tuples sharing \(X\) leaves \(Y\) unchanged and cannot introduce missing combinations.

However:

~~~text
employee_id ↠ skill
~~~

does **not** imply:

~~~text
employee_id → skill
~~~

because an employee can have multiple skills.

### MVDs Are Independent of Non-Trivial Functional Dependencies

In `EMPLOYEE_PROFILE(employee_id, skill, language)`, suppose each employee has multiple skills and multiple languages, and each skill/language is shared by many employees. Then there is no non-trivial FD from `employee_id` to either of the other two columns.

If the combinations are independent, the relation has a **non-trivial MVD** yet may still satisfy **BCNF** with respect to FDs alone. That is why **4NF** is needed.

## 5. Trivial and Non-Trivial MVDs

An MVD \(X\twoheadrightarrow Y\) on \(R(U)\) is **trivial** if **at least one** of these holds:

\[
Y\subseteq X
\quad\text{or}\quad
X\cup Y=U.
\]

Neither case imposes a new independence constraint with respect to remaining attributes.

Examples on `R(employee_id, skill, language)`:

~~~text
{employee_id, skill} ↠ {skill}               # Trivial: Y ⊆ X
{employee_id} ↠ {skill, language}             # Trivial: X ∪ Y = U
{employee_id} ↠ {skill}                       # Non-trivial
{employee_id} ↠ {language}                    # Non-trivial
~~~

Triviality/non-triviality conditions are evaluated over **the entire relation schema**, not just sample data.

A relation with **only two attribute groups \(X\) and \(Y\)**, such as `EMPLOYEE_SKILLS(employee_id, skill)`, always has \(X\cup Y=U\) for `employee_id ↠ skill`; thus this MVD is **trivial within that two-column relation itself**. That explains why splitting the two lists into two tables eliminates the original 4NF violation.

### Complementation Rule

If \(X\twoheadrightarrow Y\) on \(R(U)\), then:

\[
X\twoheadrightarrow U-(X\cup Y).
\]

In the three-column table, `employee_id ↠ skill` implies `employee_id ↠ language`. You do not need to treat both dependencies as two independent business assumptions when the remaining attributes form a single set.

## 6. From MVDs to Data Anomalies

Suppose employee `NV01` knows three skills and two languages:

~~~text
Skills = {Java, Python, SQL}
Languages = {vi, en}
~~~

The combined table requires \(3\times2=6\) rows. Adding language `fr` requires adding **three new rows**, one for each skill. Forgetting `(NV01, SQL, fr)` causes the combined data to stop accurately representing the two independent sets under the confirmed rules.

Anomalies:

- **Insertion:** adding language `ja` requires creating rows paired with every skill; if an employee has no recorded skills yet, the three-column table cannot naturally represent a standalone language list.
- **Update:** renaming a skill code or label requires updating every row paired with a language; missing a row leaves inconsistent values in the profile.
- **Deletion:** deleting a single `Java–en` row can break a required combination without meaning either "the employee lost the Java skill" or "no longer uses English".
- **Storage and querying:** row count per employee grows as the **product** of the two cardinalities rather than their **sum**, wasting space and making double-counting likely.

With \(m\) skills and \(n\) languages, the Cartesian model needs \(mn\) rows; after decomposing into two independent relations, it needs \(m+n\) link rows. With \(m=n=20\), that is **400 vs. 40** link rows for a single employee (excluding the employee entity table).

This is an MVD-driven redundancy problem; it can still occur even when FD analysis finds no BCNF violation.

## 7. Fourth Normal Form (4NF) and Violation Conditions

A relation \(R\) is in **Fourth Normal Form (4NF)** with respect to the confirmed dependencies if, for **every non-trivial multivalued dependency** \(X\twoheadrightarrow Y\) that holds on \(R\), **\(X\) is a superkey** of \(R\).

\[
R\text{ is in 4NF}
\iff
\forall (X\twoheadrightarrow Y)\text{ non-trivial}:
\ X\text{ is a superkey}.
\]

In `EMPLOYEE_PROFILE(employee_id, skill, language)`:

- `employee_id ↠ skill` is non-trivial because `skill` is not inside `employee_id` and the `language` column remains.
- `employee_id` is **not a superkey**, because one employee has multiple rows with different skills and languages.
- Therefore, the combined table **violates 4NF** under the confirmed independence rules.

### BCNF Is Not Always Enough

BCNF only requires every **non-trivial FD** to have a superkey on its left-hand side. Every FD implies an MVD, but not every MVD implies an FD. Consequently, a table can **satisfy BCNF** yet **fail 4NF**.

Do not try to invent a fake FD like `employee_id → skill` to explain the issue; that dependency is **false** if each employee can have multiple skills.

### How Is the "Superkey" Condition Determined?

A set \(X\) is a superkey if \(X^+=U\) under the **valid functional dependencies** of the relation (in other words, \(X\rightarrow U\)). An MVD alone **does not** make \(X\) a superkey. In the example, the fact that both `employee_id ↠ skill` and `employee_id ↠ language` hold still does not give `employee_id → skill` or `employee_id → language`.

## 8. Schema Decomposition by MVD: Lossless Join

For \(R(X,Y,Z)\), if the multivalued dependency \(X\twoheadrightarrow Y\) is confirmed, we can decompose:

\[
R(X,Y,Z)\ \longrightarrow\ R_1(X,Y),\ R_2(X,Z).
\]

In the relational model under **set semantics**, this multivalued dependency is equivalent to the identity:

\[
r=\pi_{XY}(r)\bowtie\pi_{XZ}(r).
\]

This is a **lossless-join decomposition**: projecting onto the two relations and taking their natural join on \(X\) recovers the original valid data exactly, without generating spurious tuples.

### Applying to the Employee Data

Replace:

~~~text
EMPLOYEE_PROFILE(employee_id, skill, language)
~~~

with:

~~~text
EMPLOYEE_SKILLS(employee_id, skill)
EMPLOYEE_LANGUAGES(employee_id, language)
~~~

The data is now:

**EMPLOYEE_SKILLS**

| employee_id | skill |
|---|---|
| NV01 | Java |
| NV01 | Python |

**EMPLOYEE_LANGUAGES**

| employee_id | language |
|---|---|
| NV01 | vi |
| NV01 | en |

If we need to reconstruct the **independent combinations table**, we can join the two tables on `employee_id` and recover the exact four rows from the opening section. However, in normal operations, to retrieve an employee's skills or languages, **query the appropriate link table directly** without generating cross-product pairs.

### Caution: Decomposition Is Lossless Only When the MVD Truly Holds

With `SKU_VARIANT(product_id,color,size)` containing `(SP01,red,M)` and `(SP01,blue,XL)`, splitting into a color list and a size list and joining them back would fabricate two **non-existent** variants. Because no independent MVD holds, that is a **lossy decomposition**: spurious tuples appear after the join.

Do not decompose merely because an entity has two multi-valued attributes; you must verify whether **all cross combinations are required and allowed to exist**.

## 9. Physical Schema Design and Constraints

SQL example with primary keys, foreign keys, and two independent link tables:

~~~sql
CREATE TABLE employees (
    employee_id VARCHAR(30) PRIMARY KEY,
    display_name VARCHAR(200) NOT NULL
);

CREATE TABLE skills (
    skill_code VARCHAR(50) PRIMARY KEY,
    skill_name VARCHAR(200) NOT NULL
);

CREATE TABLE languages (
    language_code VARCHAR(10) PRIMARY KEY,
    language_name VARCHAR(100) NOT NULL
);

CREATE TABLE employee_skills (
    employee_id VARCHAR(30) NOT NULL REFERENCES employees(employee_id),
    skill_code VARCHAR(50) NOT NULL REFERENCES skills(skill_code),
    PRIMARY KEY (employee_id, skill_code)
);

CREATE TABLE employee_languages (
    employee_id VARCHAR(30) NOT NULL REFERENCES employees(employee_id),
    language_code VARCHAR(10) NOT NULL REFERENCES languages(language_code),
    PRIMARY KEY (employee_id, language_code)
);
~~~

Each link table has its own grain and key:

| Table | One row represents | Illustrative candidate key |
|---|---|---|
| `employees` | One employee | `employee_id` |
| `employee_skills` | One skill of one employee | `(employee_id, skill_code)` |
| `employee_languages` | One language of one employee | `(employee_id, language_code)` |

These primary keys prevent duplicate link rows. Foreign keys ensure referenced employees, skills, and languages exist. They do not automatically capture other rules such as **proficiency level**, **effective dates**, or **certification verification**; those rules must be modeled explicitly when required by the business.

### Querying the Independent Lists

~~~sql
-- Retrieve the skill list without duplicating across languages.
SELECT es.skill_code
FROM employee_skills AS es
WHERE es.employee_id = 'NV01'
ORDER BY es.skill_code;

-- Retrieve the language list without duplicating across skills.
SELECT el.language_code
FROM employee_languages AS el
WHERE el.employee_id = 'NV01'
ORDER BY el.language_code;
~~~

When intentionally generating all combinations for display:

~~~sql
SELECT
    es.employee_id,
    es.skill_code,
    el.language_code
FROM employee_skills AS es
JOIN employee_languages AS el
    ON es.employee_id = el.employee_id
WHERE es.employee_id = 'NV01';
~~~

This `JOIN` query is an **intentional Cartesian combination**, not proof that the employee exercises every skill in every language. Using its result to count skills or languages with `COUNT(*)` will overcount; count directly in each base table or use `COUNT(DISTINCT ...)` as appropriate.

For performance, the composite primary key usually provides a convenient access path by `employee_id`, though depending on the DBMS and query patterns, secondary indexes on `skill_code` or `language_code` may be needed for reverse lookups. **MVDs govern logical structure; indexes govern physical access strategy.**

## 10. SQL to Check MVD Counterexamples in Existing Data

An MVD cannot always be deduced by glancing at a few tuples. However, given an independence assumption, we can use existing data to detect **missing combinations**.

Suppose `staging_employee_profile(employee_id, skill_code, language_code)` is expected to store **every combination**. The query below generates all skill–language pairs observed for the same employee and finds pairs missing from the table:

~~~sql
WITH observed AS (
    SELECT DISTINCT employee_id, skill_code, language_code
    FROM staging_employee_profile
    WHERE employee_id IS NOT NULL
      AND skill_code IS NOT NULL
      AND language_code IS NOT NULL
),
missing_combinations AS (
    SELECT DISTINCT
        s.employee_id,
        s.skill_code,
        l.language_code
    FROM observed AS s
    JOIN observed AS l
      ON l.employee_id = s.employee_id
    WHERE NOT EXISTS (
        SELECT 1
        FROM observed AS o
        WHERE o.employee_id = s.employee_id
          AND o.skill_code = s.skill_code
          AND o.language_code = l.language_code
    )
)
SELECT employee_id, skill_code, language_code
FROM missing_combinations
ORDER BY employee_id, skill_code, language_code;
~~~

For example, if staging has `(NV01,Java,vi)` and `(NV01,Python,en)` but lacks the two cross pairs, the query returns `(NV01,Java,en)` and `(NV01,Python,vi)`. That is a **counterexample to closure under tuple exchange** on the inspected staging dataset.

**Important limitations:**

- The query ignores rows with `NULL`; missing-value semantics must be handled separately.
- Returning zero rows only tells you the **current sample** has no missing combinations; it does not prove an MVD is a business rule.
- If the missing pairs are **genuinely disallowed** (such as SKU color–size), the mistake lies in the **independence assumption**, not the data.
- If the two lists do not always have to be non-empty simultaneously, the three-column relation and its join cannot accurately represent "has a skill but no language yet"; two independent tables plus a parent table represent that cleanly.
- In SQL, duplicate tuples and `NULL` handling do not match theoretical set-based relations identically. The CTE uses `DISTINCT` to check value combinations across non-NULL rows.

This is a **supporting check** after business rules are confirmed; it does not replace asking the rule owner.

## 11. Workflow to Identify MVDs in Real Requirements

### Step 1 — Identify Entities and Grain

"Does each row represent an independent fact or a pairing of two lists?" In `EMPLOYEE_PROFILE`, a row `(employee, skill, language)` is not a distinct business event if skills and languages have no pairwise relationship.

### Step 2 — List Value Sets Belonging to the Same Entity

For example:

~~~text
employee_id ↦ set of skills
employee_id ↦ set of languages
~~~

Listing them is **not enough** to assert an MVD; you must check independence.

### Step 3 — Ask Whether Adding/Removing Values Affects the Other Set

Useful questions:

- When adding a language for an employee, must it automatically form a combination with **every existing skill**?
- Is there a concept of "**practicing this skill in that language**" that must be recorded per pair?
- Are any combinations **forbidden** or **non-existent** even though each individual value appears?
- Can one list be empty while the other has entries?
- Does time range, branch, or version change the independence?

If a genuine pairwise relationship exists between \(Y\) and \(Z\), model that relationship explicitly; do not split merely because columns are multivalued.

### Step 4 — Lock In MVDs, Check 4NF, and Decompose

When \(X\twoheadrightarrow Y\) is a **non-trivial** MVD and \(X\) is not a superkey, the relation violates 4NF. Split `R(X,Y,Z)` into `R1(X,Y)` and `R2(X,Z)` when the MVD holds; verify **losslessness** and the constraints to enforce.

### Step 5 — Validate Against Business Cases and Data

After decomposition, walk through operations: adding a language, removing a skill, employees with no skills yet, and historical cases. Verify queries do not fabricate rows or double-count. Review keys, foreign keys, `NULL` policies, indexes, migrations, and cross-table integrity.

## 12. MVDs, 5NF, and Other Data Models

**4NF** addresses redundancy caused by **non-trivial MVDs** whose left-hand side is not a superkey. More generally, a **join dependency** (JD) describes when a relation can be reconstructed by joining **more than two projections**. **5NF** (project-join normal form) deals with non-trivial JDs not yet resolved by earlier normal forms; do not assume every three-column problem is an MVD or 4NF issue.

In other storage models:

| Model | How two independent lists are represented | What to watch out for |
|---|---|---|
| **Relational** | Two link tables `employee_skills`, `employee_languages` | Composite keys, foreign keys, 4NF, join queries |
| **Document** | Two arrays `skills[]`, `languages[]` in the employee document | Confirm independence, document size, array updates, and querying |
| **Graph** | `HAS_SKILL` and `USES_LANGUAGE` edges from the employee node | Do not fabricate edges linking each skill to each language |
| **Analytical** | Two corresponding bridge tables / factless facts or two dimension links | Avoid many-to-many two-way joins inflating metrics; clarify grain |

In a document model, multiple value sets **can live inside a single document** if it suits the workload; physical separation like in relational tables is not always necessary. Still, the rule of **semantic independence** must be stated clearly to avoid fabricating meaningless combinations.

## 13. Common Misconceptions

**Misconception 1: "One-to-many means there is definitely an MVD to split."** Not sufficient. A non-trivial MVD arises when a group \(Y\) is independent of **the remaining attributes \(Z\)** in the same relation.

**Misconception 2: "An MVD is an FD with multiple columns on the right-hand side."** False. `X → YZ` still states **one determined value** per right-hand column for each \(X\). `X ↠ Y` states a **set of \(Y\) values** independent of \(Z\).

**Misconception 3: "A table in BCNF has no remaining redundancy."** False. Non-trivial multivalued dependencies can exist without any non-trivial FD violating BCNF; 4NF handles this case.

**Misconception 4: "Missing combinations are data errors regardless of business rules."** False. If a color–size pair genuinely does not exist, you must not fabricate rows to satisfy a fake MVD.

**Misconception 5: "After splitting, joining the two lists produces meaningful detail records."** False. Joining generates **all pairwise combinations**; for independent lists, those pairs are not real-world facts. Read each table according to the question being asked.

**Misconception 6: "An MVD always needs to be expressed in both directions as two separate constraints."** For the remaining attributes \(Z=U-(X\cup Y)\), the complementation rule shows \(X\twoheadrightarrow Y\) implies \(X\twoheadrightarrow Z\).

## 14. Practice Exercises with Solutions

### Exercise 1 — Two Independent Sets

An author has **writing genres** `{mystery, science}` and **contact channels** `{email, phone, social media}`. The two lists are independent. If stored in `AUTHOR_PROFILE(author_id, genre, contact_channel)`, how many rows does each author need when both lists are fully populated?

**Solution:** \(2\times3=6\) combination rows. Because `author_id ↠ genre` is a non-trivial MVD and `author_id` is not a superkey, the table violates 4NF. We can decompose into `AUTHOR_GENRES(author_id,genre)` and `AUTHOR_CONTACT_CHANNELS(author_id,contact_channel)` to store \(2+3=5\) link rows.

### Exercise 2 — Is the Multivalued Dependency Real?

Table `CAR_VARIANT(model_id,color,engine)` contains `(M1,red,gasoline)` and `(M1,blue,electric)`. The manufacturer **does not offer** a `red,electric` variant. Can we conclude `model_id ↠ color`?

**Solution:** No. If the MVD held, from two tuples with the same `model_id` the swapped tuples `(M1,red,electric)` and `(M1,blue,gasoline)` would have to exist. Since one of those combinations is disallowed, the MVD is **false under the given business rules**. Keep the variant relation for actual color–engine pairs.

### Exercise 3 — Trivial MVDs

On `R(employee_id,skill,language)`, classify:

1. `(employee_id,skill) ↠ skill`.
2. `employee_id ↠ (skill,language)`.
3. `employee_id ↠ skill`.

**Solution:** (1) **Trivial** because the right-hand side is contained in the left-hand side. (2) **Trivial** because the union of left- and right-hand sides covers the whole schema. (3) **Non-trivial**; holds only when the skill and language sets are independent by business rule.

### Exercise 4 — FDs and MVDs

In a current employee table, `employee_id → display_name`. Can we infer `employee_id ↠ display_name`? Conversely, from `employee_id ↠ skill` can we infer `employee_id → skill`?

**Solution:** **Yes** to the first question, because an FD implies an MVD. **No** to the second question, because an employee can have multiple skills while that list remains independent of the remaining attributes.

### Exercise 5 — Checking 4NF

Given `R(student_id,club_id,hobby_id)`. Each student joins multiple clubs and has multiple hobbies **independently**, with no other non-trivial FDs. Is `student_id` a superkey? Does the relation satisfy 4NF?

**Solution:** `student_id` is not a superkey because one student has multiple values in the other two columns. By the business rules, `student_id ↠ club_id` is a non-trivial MVD; hence the relation **fails 4NF** even though it may satisfy BCNF. Split into `STUDENT_CLUBS(student_id,club_id)` and `STUDENT_HOBBIES(student_id,hobby_id)`.

### Exercise 6 — Missing Data or Wrong Rule?

Staging stores:

~~~text
(NV02, SQL, vi)
(NV02, Java, en)
~~~

The owner confirms skills and languages are **two independent lists** for each employee. State the outcome of the MVD check.

**Solution:** The staging data is **missing** `(NV02,SQL,en)` and `(NV02,Java,vi)` if the combined table requires all combinations. Cross-check source data or migrate to two independent tables. If in reality the two columns represent **skills practiced in specific languages**, missing cross pairs may be valid and the assumed MVD does not hold. Only fix after confirming the table's semantics.

## 15. Checklist Before Finalizing the Model

- [ ] Identified the **grain** of each row and the meaning of each attribute group.
- [ ] Confirmed the two value sets are genuinely **independent by business rules**; adding a value to one set does not constrain the other.
- [ ] Checked the tuple-exchange condition and whether any combinations are disallowed.
- [ ] Distinguished FDs \(X\rightarrow Y\) from MVDs \(X\twoheadrightarrow Y\).
- [ ] Distinguished trivial vs. non-trivial MVDs over the **entire schema**.
- [ ] Checked whether the left-hand side of any non-trivial MVD is a superkey to evaluate 4NF.
- [ ] Decomposed into \(R(X,Y)\) and \(R(X,Z)\) only when justified for a **lossless join**.
- [ ] Designed composite keys, foreign keys, query patterns, and indexes for each link table.
- [ ] Checked cases where one list is empty, historical data, `NULL`, and exceptions.
- [ ] Avoided joining independent lists as though they represented real paired events.

**Takeaway:** A **multivalued dependency** \(X\twoheadrightarrow Y\) describes a **set of \(Y\) values** independent of the remaining attributes when \(X\) is fixed. It is this independence — not merely a column having multiple values — that creates the need to decompose for **4NF**. When modeling, confirm the tuple-exchange condition from business rules first, then use decomposition and SQL to verify.
