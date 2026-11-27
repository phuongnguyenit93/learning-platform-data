# Fifth Normal Form and Decomposition by Join Dependency

**Fifth Normal Form (5NF)**, also known as **Project-Join Normal Form (PJNF)**, addresses relations that can be decomposed into smaller projections and rejoined **losslessly** thanks to a business rule called a **join dependency (JD)**. In some systems, a three-column table represents combinations of three binary relationships; when those three binary relationships are independent facts and **every combination satisfying all three conditions is valid**, storing the full triples introduces redundancy and increases inconsistency risk.

In the **Normalization** chapter of the **DATABASE_DATA_MODELING** module, this topic builds on candidate keys, functional dependencies, BCNF, and the multivalued dependencies of 4NF. The goal is to read business rules accurately, verify whether a decomposition is genuinely a **lossless join**, and choose a model verifiable through keys, constraints, and queries. **Never decompose merely because a table has three foreign keys or because a JOIN runs cleanly**; combination semantics are the deciding factor.

## 1. The Problem: Suppliers, Parts, and Projects

A company manages part allocations across projects. Define three identifiers:

- **supplier_id (S):** supplier;
- **part_id (P):** part type;
- **project_id (J):** project.

In the first version of the business rules, a triple **(S, P, J)** is permitted if and only if **all three** conditions hold simultaneously:

1. Supplier S **is capable of supplying** part P.
2. Supplier S **is approved to participate in** project J.
3. Project J **requires** part P.

There is no separate approval per triple. If all three pairs hold, the triple **must be considered valid**. This is the crucial assumption that gives rise to a JD.

The initial design stores valid triples in one table:

| supplier_id | part_id | project_id |
| --- | --- | --- |
| S1 | P1 | J1 |
| S1 | P1 | J2 |
| S1 | P2 | J2 |
| S2 | P1 | J2 |

According to this data:

- S1 can supply P1, P2; S2 can supply P1.
- S1 participates in J1, J2; S2 participates in J2.
- J1 needs P1; J2 needs P1, P2.

Each row is **a permitted combination**, yet carries no extra attributes specific to that combination. If you only want to know whether S1 supplies P1, the fact **(S1, P1)** appears across two rows, corresponding to J1 and J2. Other pairs can likewise be repeated.

## 2. What Is a Join Dependency?

### 2.1. Definition via Projection and Join

Given a relation **R** and attribute sets **R1, R2, ..., Rn** whose union equals all attributes of R, the notation:

~~~text
*(R1, R2, ..., Rn)
~~~

is a **join dependency (JD)** if every valid state of R satisfies:

~~~text
R = π_R1(R) ⋈ π_R2(R) ⋈ ... ⋈ π_Rn(R)
~~~

Where:

- **π** (projection) selects columns and, under the set semantics of the relational model, eliminates duplicate tuples.
- **⋈** is the natural join on identically named attributes sharing the same meaning and domain.
- The **=** sign requires the join result **neither to omit any original tuple nor to generate any spurious tuple**.
- A JD is a rule that must hold across **every valid data state**, not just one current sample table.

Over the three attributes S, P, J, consider the dependency:

~~~text
*(SP, SJ, PJ)

R(S, P, J)
  = π_(S,P)(R)
    ⋈ π_(S,J)(R)
    ⋈ π_(P,J)(R)
~~~

It states that the complete set of triples is fully determined by **three sets of pairs**: supplier–part, supplier–project, and project–part.

### 2.2. Trivial vs. Non-Trivial Join Dependencies

A JD is **trivial** if among its component attribute sets **at least one set contains all attributes of R**. For example:

~~~text
*(SPJ, SP)
~~~

does not indicate a useful decomposition because one component is already the entire original relation.

Conversely:

~~~text
*(SP, SJ, PJ)
~~~

is **non-trivial**: no single component set contains all of S, P, and J. If this JD holds under the business rules, it opens the possibility of decomposing R into three smaller relations.

**Note:** having primary key **(S, P, J)**, or simply seeing three pair sets in sample data, **does not prove** a JD. You must verify the rule "every triple satisfying all three pairs is valid."

## 3. Definition of 5NF and the Role of Candidate Keys

A relation satisfies **5NF (PJNF)** when **every non-trivial join dependency holding on the relation is implied by the candidate keys of the relation**. In other words, there remains no non-trivial JD independent of key constraints that could be used to decompose the relation further to avoid redundancy.

Practical interpretation:

1. Identify **candidate keys** from business functional dependencies.
2. Identify non-trivial JDs that may hold under the data's combination rules.
3. If there is a JD **not implied solely by the keys**, consider decomposing along its component projections.
4. Accept the decomposition only if rejoining is **lossless** across all valid states.

In the supply example, assume the business imposes **no non-trivial functional dependencies** on S, P, J. Each of **(S,P)**, **(S,J)**, and **(P,J)** can appear on multiple rows. Hence the candidate key of the three-column relation is **(S, P, J)**.

This key prevents duplicate triples, yet it **does not require** valid S–P, S–J, and P–J pairs to produce all combinations simultaneously. Thus the JD ***(SP, SJ, PJ)** is **an additional business constraint**, not a consequence of the three-column key. If that JD holds, the original relation **violates 5NF**.

### 3.1. Quick Comparison with Lower Normal Forms

| Normal Form | Dependency Type Examined | Core Condition |
| --- | --- | --- |
| **3NF** | Functional dependency X → A | X is a superkey **or** A belongs to a candidate key |
| **BCNF** | Functional dependency X → A | Every non-trivial dependency has X as a superkey |
| **4NF** | Multivalued dependency X ↠ Y | Every non-trivial MVD has X as a superkey |
| **5NF** | Join dependency across multiple projections | Every non-trivial JD must be implied by the candidate keys |

**An MVD is a special case of a two-component JD.** For R(X,Y,Z), the multivalued dependency **X ↠ Y** is equivalent to the lossless join condition:

~~~text
R = π_(X,Y)(R) ⋈ π_(X,Z)(R)
~~~

5NF is therefore stricter than 4NF: 4NF handles cases decomposable via an MVD, whereas 5NF also covers JDs requiring **three or more projections**. A relation can satisfy both BCNF and 4NF while still having a three-way JD requiring decomposition.

## 4. From Triples to Three Pair Sets

Take the projections of the initial table:

**Supplier–Part (SP):**

| supplier_id | part_id |
| --- | --- |
| S1 | P1 |
| S1 | P2 |
| S2 | P1 |

**Supplier–Project (SJ):**

| supplier_id | project_id |
| --- | --- |
| S1 | J1 |
| S1 | J2 |
| S2 | J2 |

**Project–Part (PJ):**

| project_id | part_id |
| --- | --- |
| J1 | P1 |
| J2 | P1 |
| J2 | P2 |

Under the stated business rule, a triple **(S,P,J)** is valid whenever (S,P) is in SP, (S,J) is in SJ, and (P,J) is in PJ.

~~~mermaid
flowchart LR
    SP["SP: supplier can supply part"]
    SJ["SJ: supplier is approved for project"]
    PJ["PJ: project needs part"]
    JOIN{"Same S, P, J and all three pairs hold?"}
    RESULT["Valid triple (S, P, J)"]
    SP --> JOIN
    SJ --> JOIN
    PJ --> JOIN
    JOIN -->|"Yes"| RESULT
~~~

When joining the three pair tables, we get back the exact four original rows:

| supplier_id | part_id | project_id | Qualifying Pair Reasons |
| --- | --- | --- | --- |
| S1 | P1 | J1 | S1–P1; S1–J1; J1–P1 |
| S1 | P1 | J2 | S1–P1; S1–J2; J2–P1 |
| S1 | P2 | J2 | S1–P2; S1–J2; J2–P2 |
| S2 | P1 | J2 | S2–P1; S2–J2; J2–P1 |

There is no **(S2,P2,J2)** because SP does not contain (S2,P2). There is no **(S1,P2,J1)** because PJ does not contain (J1,P2). The exact result follows from the **three business conditions**, not from luck in the join.

### 4.1. A Join Dependency Can Exist Even Without Any Multivalued Dependency

In the relation R(S,P,J) under consideration, **S ↠ P** is false. From the two rows:

~~~text
(S1, P1, J1)
(S1, P2, J2)
~~~

if S ↠ P held, then **(S1,P2,J1)** would have to exist, yet that triple is invalid because project J1 does not need P2. Similarly, MVDs like **P ↠ S** or **J ↠ S** are not business rules of this system.

Assuming **no additional non-trivial FDs or MVDs**, the three-column relation is already in **4NF**, yet fails **5NF** due to the JD ***(SP,SJ,PJ)**. That is why checking only up to 4NF is insufficient for all three-way combination problems.

## 5. Physical Design: Store Pairs and Derive Triples When Needed

Each new table has a clear grain and key:

~~~text
supplier_parts(supplier_id, part_id)
supplier_projects(supplier_id, project_id)
project_parts(project_id, part_id)
~~~

These tables represent **supply capability**, **project participation approval**, and **project part demand**, respectively. There is no need for a table solely to multiply out combinations if the triple has no independent facts of its own.

~~~mermaid
erDiagram
    SUPPLIERS ||--o{ SUPPLIER_PARTS : "can supply"
    PARTS ||--o{ SUPPLIER_PARTS : "supplied by"
    SUPPLIERS ||--o{ SUPPLIER_PROJECTS : "approved for"
    PROJECTS ||--o{ SUPPLIER_PROJECTS : "has supplier"
    PROJECTS ||--o{ PROJECT_PARTS : "needs part"
    PARTS ||--o{ PROJECT_PARTS : "used by"
    SUPPLIER_PARTS {
        varchar supplier_id PK
        varchar part_id PK
    }
    SUPPLIER_PROJECTS {
        varchar supplier_id PK
        varchar project_id PK
    }
    PROJECT_PARTS {
        varchar project_id PK
        varchar part_id PK
    }
~~~

The diagram includes lookup tables SUPPLIERS, PARTS, and PROJECTS to illustrate independent entities; the core of the JD decomposition is the **three binary association tables**.

### 5.1. DDL and Sample Data in PostgreSQL

The minimal example below defines only the three association tables; in production, add foreign keys to the supplier, part, and project catalog tables:

~~~sql
CREATE TABLE supplier_parts (
    supplier_id VARCHAR(10) NOT NULL,
    part_id     VARCHAR(10) NOT NULL,
    PRIMARY KEY (supplier_id, part_id)
);

CREATE TABLE supplier_projects (
    supplier_id VARCHAR(10) NOT NULL,
    project_id  VARCHAR(10) NOT NULL,
    PRIMARY KEY (supplier_id, project_id)
);

CREATE TABLE project_parts (
    project_id VARCHAR(10) NOT NULL,
    part_id    VARCHAR(10) NOT NULL,
    PRIMARY KEY (project_id, part_id)
);

INSERT INTO supplier_parts (supplier_id, part_id) VALUES
    ('S1', 'P1'),
    ('S1', 'P2'),
    ('S2', 'P1');

INSERT INTO supplier_projects (supplier_id, project_id) VALUES
    ('S1', 'J1'),
    ('S1', 'J2'),
    ('S2', 'J2');

INSERT INTO project_parts (project_id, part_id) VALUES
    ('J1', 'P1'),
    ('J2', 'P1'),
    ('J2', 'P2');
~~~

Create a **VIEW** to query valid combinations:

~~~sql
CREATE VIEW eligible_supplier_part_projects AS
SELECT
    sp.supplier_id,
    sp.part_id,
    sj.project_id
FROM supplier_parts AS sp
JOIN supplier_projects AS sj
    ON sj.supplier_id = sp.supplier_id
JOIN project_parts AS pp
    ON pp.project_id = sj.project_id
   AND pp.part_id = sp.part_id;

SELECT supplier_id, part_id, project_id
FROM eligible_supplier_part_projects
ORDER BY supplier_id, part_id, project_id;
~~~

The result matches the exact four tuples from section 1. Each pair table manages an independent business fact; the VIEW uses joins to materialize triples **at read time**.

### 5.2. Update Operations After Decomposition

**Adding a new capability** for S2 to supply P2:

~~~sql
INSERT INTO supplier_parts (supplier_id, part_id)
VALUES ('S2', 'P2');
~~~

Because S2 already participates in J2 and J2 needs P2, the VIEW automatically surfaces **(S2,P2,J2)** per the business rule.

**Revoking S1's approval on J2:**

~~~sql
DELETE FROM supplier_projects
WHERE supplier_id = 'S1' AND project_id = 'J2';
~~~

Now the VIEW no longer emits **(S1,P1,J2)** or **(S1,P2,J2)**. Losing both combinations is **correct per the business rules** because the supplier is no longer approved for J2. Splitting the tables lets you update the exact underlying fact without hunting down every affected triple row by row.

If you run these two examples in order on the sample data, the second change does not erase S1's capabilities S1–P1/S1–P2 or J2's part demands. The tables preserve each relationship's independent lifecycle.

## 6. Verifying Lossless Join and Detecting Spurious Tuples

### 6.1. A Single Clean JOIN Does Not Prove a JD

A JOIN that runs without SQL errors **does not prove** the decomposition is valid. There are two distinct questions:

- **Lossless join:** from projections of a valid original relation, does the join recover the exact original tuples?
- **Business dependency:** what rule guarantees that every combination satisfying all three pairs is also a valid tuple? That is what justifies concluding the JD holds across **all valid states**.

For the three projections SP, SJ, PJ of relation R, any tuple **(S,P,J)** present in R will always appear in the join, because it contributes all three pairs. The main risk of the join is generating **spurious tuples**—combinations formed from three pairs that never existed in the original relation.

In the section 1 example, there are no spurious tuples because the business rules state that every triple meeting all three pair conditions is valid. Still, we can use SQL to detect mismatches in **a given data state**.

### 6.2. Creating Reference Data and Joining from Projections

So that the verification queries below can run independently of changes to the three tables in section 5, create a temporary table representing the original triples:

~~~sql
CREATE TEMP TABLE supply_triples (
    supplier_id VARCHAR(10) NOT NULL,
    part_id     VARCHAR(10) NOT NULL,
    project_id  VARCHAR(10) NOT NULL,
    PRIMARY KEY (supplier_id, part_id, project_id)
);

INSERT INTO supply_triples (supplier_id, part_id, project_id) VALUES
    ('S1', 'P1', 'J1'),
    ('S1', 'P1', 'J2'),
    ('S1', 'P2', 'J2'),
    ('S2', 'P1', 'J2');

CREATE TEMP VIEW reconstructed_triples AS
SELECT
    sp.supplier_id,
    sp.part_id,
    sj.project_id
FROM (
    SELECT DISTINCT supplier_id, part_id
    FROM supply_triples
) AS sp
JOIN (
    SELECT DISTINCT supplier_id, project_id
    FROM supply_triples
) AS sj
    ON sj.supplier_id = sp.supplier_id
JOIN (
    SELECT DISTINCT project_id, part_id
    FROM supply_triples
) AS pj
    ON pj.project_id = sj.project_id
   AND pj.part_id = sp.part_id;
~~~

A **two-way** check using the set operator **EXCEPT**:

~~~sql
-- Tuples in the join not in original R: spurious tuples.
SELECT supplier_id, part_id, project_id
FROM reconstructed_triples
EXCEPT
SELECT supplier_id, part_id, project_id
FROM supply_triples;

-- Original tuples missing from the join: lost tuples.
SELECT supplier_id, part_id, project_id
FROM supply_triples
EXCEPT
SELECT supplier_id, part_id, project_id
FROM reconstructed_triples;
~~~

With the four initial rows, **both queries return zero rows**. This confirms the join is exact **for the current sample**; to adopt the design long-term, you still need the business rule backing the JD.

### 6.3. Testing Deleting One Triple While Keeping All Three Pairs

Test deleting **(S1,P1,J2)** from the flat table while keeping the other three rows:

~~~sql
BEGIN;

DELETE FROM supply_triples
WHERE supplier_id = 'S1'
  AND part_id = 'P1'
  AND project_id = 'J2';

SELECT supplier_id, part_id, project_id
FROM reconstructed_triples
EXCEPT
SELECT supplier_id, part_id, project_id
FROM supply_triples;

ROLLBACK;
~~~

The query returns **(S1,P1,J2)**. The reason is that all three underlying pairs still exist in the data:

- **(S1,P1)** remains in row (S1,P1,J1).
- **(S1,J2)** remains in row (S1,P2,J2).
- **(J2,P1)** remains in row (S2,P1,J2).

Joining the projections regenerates the deleted tuple. If the business rule confirms the three pairs are sufficient, "deleting a single triple alone" is **not** a valid business change: to invalidate the triple, **at least one pair fact** must change. Conversely, if the business allows forbidding a specific triple even while all three pairs remain true, that signals the **assumed JD is false** and you cannot store only the three pair tables.

This is the critical difference between **replaying one state** and **evaluating all valid states**. A mismatch between data and join output can mean either a missing triple under the JD rule, or proof that the rule must be modeled differently.

## 7. Counterexample: Per-Triple Approval

Suppose management changes the requirement:

> Supplier S can supply part P, is approved for project J, and project J needs P; **however, each (S,P,J) combination must also receive separate technical approval**.

In that case, the three pairs are only **necessary conditions**. They are **not sufficient** to declare a triple valid.

Suppose the approved triples are:

| supplier_id | part_id | project_id |
| --- | --- | --- |
| S1 | P1 | J1 |
| S1 | P2 | J2 |
| S2 | P1 | J2 |

The three projections of this set still contain:

~~~text
SP: (S1,P1), (S1,P2), (S2,P1)
SJ: (S1,J1), (S1,J2), (S2,J2)
PJ: (J1,P1), (J2,P2), (J2,P1)
~~~

When joined, you also obtain **(S1,P1,J2)**. This triple satisfies all three pairs, yet **has not been individually approved**. It is a **spurious tuple** for the new relation; the JD equation ***(SP,SJ,PJ)** is **false**.

A suitable design can maintain an **approved_supply_combinations** table at the one-triple grain alongside the three pair tables representing the prerequisites:

~~~sql
CREATE TABLE approved_supply_combinations (
    supplier_id VARCHAR(10) NOT NULL,
    part_id     VARCHAR(10) NOT NULL,
    project_id  VARCHAR(10) NOT NULL,
    PRIMARY KEY (supplier_id, part_id, project_id),
    FOREIGN KEY (supplier_id, part_id)
        REFERENCES supplier_parts(supplier_id, part_id),
    FOREIGN KEY (supplier_id, project_id)
        REFERENCES supplier_projects(supplier_id, project_id),
    FOREIGN KEY (project_id, part_id)
        REFERENCES project_parts(project_id, part_id)
);
~~~

The three composite foreign keys ensure **an approved triple can only be chosen from currently valid pairs**. Yet there is no rule requiring "every triple formed from the three pairs is approved": the three-column table exists to record those explicit decisions.

You must not conclude that **approved_supply_combinations** should be split further under the old JD. When each triple is an independent decision not derivable from pairs, it is a **genuine business fact**, not a redundant copy.

**Note on evolving rules:** if per-triple approval carries a status, effective date, or approver, those attributes make the triple's independent grain even clearer. When history is needed, you may need versioning, effective intervals, or approval event records.

## 8. How Does JD Decomposition Differ from FD or MVD Decomposition?

| Situation | Confirmed Dependency | Typical Decomposition |
| --- | --- | --- |
| Each department has one current name | FD: **department_id → department_name** | Extract departments table, keep department ID on employees |
| Students have independent languages and hobbies | MVD: **student_id ↠ language_code** | Separate **student_languages** and **student_hobbies** |
| Supplier–part–project is fully determined by three pair conditions | JD: ***(SP,SJ,PJ)** | Separate **supplier_parts**, **supplier_projects**, **project_parts** |
| Each three-way combination requires individual approval | Stated three-pair JD does not hold | Keep the triple table as a relation with its own semantics |

A binary MVD decomposition has the form:

~~~text
R(X,Y,Z) = π_(X,Y)(R) ⋈ π_(X,Z)(R)
~~~

In the supply example, joining **SP** and **SJ** alone is insufficient: they could pair S1–P2–J1 even though J1 does not need P2. **PJ** is also required. That requirement to intersect **three** pair sets makes this JD fundamentally different from two independent multi-valued sets.

### 8.1. Does 5NF Force Every Table to Have Only Two Columns?

**No.** 5NF places no limit on column count. A table with three, four, or more attributes can still satisfy 5NF if there are no non-trivial JDs requiring further decomposition beyond those implied by candidate keys.

For example, **order_lines(order_id, line_no, product_id, quantity, unit_price_at_order)** can be a table at the single-line-item grain holding independent line-item facts. There is no basis to split a table just because it has many columns. Keys, price history, transaction rules, and actual dependencies determine its normal form.

### 8.2. A Trivial JD Is Not a Violation

A dependency where one component contains **all attributes of R** is trivial, e.g., ***(SPJ, SP)**. It yields no useful decomposition. When checking 5NF, focus on **non-trivial** JDs and whether they follow from the keys.

### 8.3. Adding a Surrogate Key Does Not Remove Combination Rules

If you add **id** as the primary key to the three-way table, the three pairs remain the business facts capable of determining triples in the first model. A surrogate key identifies rows, yet it does not change whether every combination satisfying the three conditions is valid.

Evaluating the normal form of the **expanded relation** requires recomputing candidate keys and active dependencies. You cannot conclude "having an ID satisfies 5NF," nor should you drop pair constraints just to add an ID.

## 9. Applying This in Production Systems: Data Integrity and Performance

### 9.1. Checklist for Verifying a JD Decomposition

1. **Identify the grain:** is a row a three-way association, an independent transaction, or merely a consequence of smaller conditions?
2. **List candidate keys and FDs:** do not infer keys from sample data; establish minimal identifying rules.
3. **Check MVDs:** is there already a two-component decomposition justified by independent multi-valued sets?
4. **Propose the JD:** write out the exact projection sets, e.g., ***(SP,SJ,PJ)**.
5. **Confirm the biconditional with the business:** every valid triple satisfies all three pairs, and **every triple satisfying all three pairs is valid**.
6. **Verify on data:** use projections, joins, and set differences in both directions to catch spurious or missing tuples in the current state.
7. **Decompose and set keys:** each component table must represent an independent fact with proper grain, primary keys, and foreign keys.
8. **Test write scenarios:** does adding a new pair surface the exact expected new combinations; does removing a pair drop the exact dependent combinations?
9. **Check write-rule feasibility:** if per-triple exceptions exist, model explicit exception/approval records instead of assuming a JD.
10. **Optimize queries after the model is sound:** evaluate indexes, join order, result cardinality, and whether views or materialized views are needed.

### 9.2. Separate Read Indexes and Views Can Be Added

The composite primary keys of the three tables in section 5 enforce unique pairs. In an SQL engine, consider index column order based on query access patterns:

- **supplier_parts(supplier_id, part_id)** favors filtering by supplier_id.
- **supplier_projects(supplier_id, project_id)** favors filtering by supplier_id.
- **project_parts(project_id, part_id)** favors filtering by project_id.

If you frequently look up **suppliers by part** or **suppliers by project**, evaluate secondary indexes placing the filter column first, depending on the DBMS and execution plans:

~~~sql
CREATE INDEX idx_supplier_parts_part_supplier
ON supplier_parts (part_id, supplier_id);

CREATE INDEX idx_supplier_projects_project_supplier
ON supplier_projects (project_id, supplier_id);
~~~

Indexes must be validated against real queries, row counts, and write overhead. If three-way results are read very frequently while pairs rarely change, consider a **materialized view** or a read table derived from the three authoritative sources, backed by refresh and consistency checks. Accelerating reads does not erase the underlying JD or business rules.

### 9.3. Do Not Equate Lossless Join with Preserving Every Constraint

**Lossless join** concerns reconstructing original tuples when tables are projected from a valid relation. **Dependency preservation** concerns being able to infer and enforce dependencies from constraints on the decomposed tables. These are two distinct properties.

In a design with only the three pair tables and the rule "all three pairs suffice," the view enforces the JD automatically. However, newly emerging **triple-level** rules—such as requiring a dedicated permit for a supplier–part–project combination—are not enforced by the three pair primary keys. When requirements evolve, update the schema or enforcement logic accordingly.

In particular, foreign keys from the pair tables to master catalogs protect code existence, yet **do not prove** the "every combination is valid" rule. That rule must be confirmed directly with the business.

## 10. Practice Exercises

### Exercise 1. Consultants, Skills, and Regions

A consulting system stores **(consultant_id, skill_id, region_id)** triples. The business states:

- Consultant C has skill K in **consultant_skills**.
- Consultant C is authorized to work in region R in **consultant_regions**.
- Skill K is offered in region R in **region_skills**.
- **Every** C–K–R triple meeting all three conditions is a valid service combination, with no separate per-triple approval needed.

Data:

~~~text
consultant_skills:  (C1,K1), (C1,K2), (C2,K1)
consultant_regions: (C1,R1), (C1,R2), (C2,R2)
region_skills:     (R1,K1), (R2,K1), (R2,K2)
~~~

**Tasks:**

1. Write the JD on the original relation **R(C,K,Rg)**, using Rg for region to avoid confusion with relation name R.
2. List all permitted triples.
3. Assuming no additional non-trivial business FDs/MVDs, does the three-column table satisfy 4NF and 5NF?
4. Propose three storage tables and explain why the join is lossless under the business rules.

<details>
<summary>Suggested Solution for Exercise 1</summary>

The JD is ***(CK, CRg, KRg)**. Permitted triples:

~~~text
(C1,K1,R1)
(C1,K1,R2)
(C1,K2,R2)
(C2,K1,R2)
~~~

With no non-trivial FDs or MVDs, the candidate key of the original relation is **(C,K,Rg)**; it satisfies **4NF**. The three-pair JD is non-trivial and not implied by the three-column key, so the original table **violates 5NF**.

Store **consultant_skills(C,K)**, **consultant_regions(C,Rg)**, and **region_skills(Rg,K)**. Each pair table has a composite primary key. Joining on C, K, and Rg reconstructs the exact triples because the business confirms there is no separate per-triple condition.

</details>

### Exercise 2. One Exception Changes the Model

Keep the data from Exercise 1, except the regulator now requires **C1 providing K1 in R2 to hold a separate certificate, which is not yet approved**. Pairs C1–K1, C1–R2, and K1–R2 remain valid.

**Questions:** are the three pair tables still sufficient to represent the exact set of permitted combinations? Which spurious tuple will the join produce? At what grain must the new information be stored?

<details>
<summary>Suggested Solution for Exercise 2</summary>

The three pair tables still produce **(C1,K1,R2)** even though that combination is not yet permitted. Thus the three-pair JD **no longer holds** for the relation of approved combinations.

You must add a triple-grain relation such as **approved_consultant_skill_regions(C,K,Rg)**, potentially with status and certificate attributes. Composite foreign keys to the three pair tables can enforce the necessary conditions. Splitting everything into three pairs and discarding per-triple decisions would lose information.

</details>

### Exercise 3. Why Is 4NF Not Enough?

Given **R(S,P,J)** with the assumptions from the opening problem, explain:

- Why is **S ↠ P** false when J1 does not need P2?
- Why does that not invalidate the JD ***(SP,SJ,PJ)**?
- Why can the relation still satisfy 4NF yet violate 5NF?

**Hint:** the MVD S ↠ P would force every part of S to pair with every project J of S. The business rule instead requires the additional condition **J needs P**, so the join must involve **three pair relations**. A three-component JD can hold even when no suitable two-component MVD exists.

## 11. Common Misconceptions to Avoid

| Misconception | Accurate Evaluation |
| --- | --- |
| "Having three foreign keys means you must split into three tables." | Split only when **business rules guarantee the JD** and do not lose a triple-level fact. |
| "Three projections that can be JOINed means it is lossless." | Compare against the original relation and verify across **all valid states**. |
| "Satisfying 4NF guarantees satisfying 5NF." | A three-component JD can hold even when no two-component MVD violates 4NF. |
| "5NF forces every table to have only two columns." | Column count does not determine normal form; evaluate JDs and candidate keys. |
| "Having a three-column PRIMARY KEY prevents redundancy." | The key stops duplicate triples; it does not eliminate repetition of pair conditions. |
| "Splitting into more tables always means better normalization." | Groundless decomposition can manufacture **spurious tuples** or discard triple-level rules. |
| "Seeing no spurious tuples in current data is enough." | Checking data validates only one state; a JD is a **rule for all valid states**. |
| "Adding a surrogate ID solves the 5NF issue." | An ID does not alter combination origins or replace dependency analysis. |
| "Optimizing JOINs equals optimizing the data structure." | Indexes and views optimize reads; you still must clarify authoritative sources and constraints. |

## 12. Key Takeaways

**5NF requires every non-trivial join dependency to be implied by the candidate keys.** The classic case is a three-way relation fully determined by **three pair sets**: S can supply P, S is approved for J, and J needs P. Whenever **every triple satisfying all three pairs is valid**, the JD ***(SP,SJ,PJ)** holds and the relation can be decomposed into three pair tables and rejoined losslessly.

The business **"if and only if"** condition is the linchpin. If a three-way combination requires separate approval or carries its own attributes, three pairs are insufficient and joining would produce spurious tuples. Establish grain, candidate keys, and true dependencies, verify **lossless join**, protect constraints after decomposition, and only then tune indexes or denormalized read models.
