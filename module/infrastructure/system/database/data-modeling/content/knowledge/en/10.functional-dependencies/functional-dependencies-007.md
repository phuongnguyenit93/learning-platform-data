# Join Dependencies and the Limits of Decomposing into Multiple Relations

## Learning Objectives

In the **DATABASE_DATA_MODELING** module, the goal is to turn business requirements into a clear, verifiable, and evolvable data model: identifying entities, relationships, keys, dependencies, normal forms, and appropriate physical structures. After studying functional dependencies (FDs) and multivalued dependencies (MVDs), we encounter a harder case: **a relation may be accurately reconstructed by joining three or more projections only when a very specific business rule holds**.

That is the subject of **join dependencies** (JDs). This lesson helps you:

- Explain JDs using **projection** and **natural join**, distinguishing a lossless-join decomposition from a join that produces spurious tuples.
- Show why simultaneously valid pairwise relations **do not necessarily** determine a valid ternary relation.
- Distinguish JDs, FDs, and MVDs; understand why a relation in **4NF** may still fail **5NF**.
- Verify a multi-relation decomposition using business rules, counterexample data, and SQL queries.
- Weigh decomposition against dependency preservation, constraint enforcement, join cost, and document, graph, and analytical models.

## 1. Business Problem: Three Entities and Three Pairwise Relations

Consider a supply-chain system with three entity types:

- **Supplier** (`supplier_id`).
- **Part** (`part_id`).
- **Project** (`project_id`).

The system manages triples `(supplier_id, part_id, project_id)`. A triple can carry **two completely different business meanings**:

1. **Supply eligibility:** a supplier is eligible to supply a part to a project if **all three independent pairwise conditions** hold simultaneously: the supplier is approved for the part, the supplier is approved for the project, and the part is approved for the project.
2. **Actual contracts:** a supplier **has been contracted** to supply a specific part to a specific project. Even when all three pairs are approved, not every eligible triple has become an actual contract.

Under the first meaning, the triple can be **derived from the three pairwise relations**. Under the second meaning, the triple is an **independent event** that must be stored explicitly.

This distinction determines whether splitting the table into multiple relations recovers the data **without fabricating nonexistent triples**.

## 2. Review of Projection, Join, and Lossless Join

Let \(R(U)\) be a relation schema with attribute set \(U\); let \(r\) be a valid data state of \(R\).

- **Projection** \(\pi_V(r)\) retains the attributes in \(V\subseteq U\) and, under relational set semantics, eliminates duplicate tuples.
- **Natural join** \(r_1\bowtie r_2\) combines tuples that share equal values on their common attributes.

If \(U\) is split into subsets \(R_1,R_2,\ldots,R_n\) such that:

\[
U=R_1\cup R_2\cup\cdots\cup R_n,
\]

then the decomposition has a **lossless join** under the confirmed constraints when, for **every** valid state \(r\):

\[
r=\pi_{R_1}(r)\bowtie\pi_{R_2}(r)\bowtie\cdots\bowtie\pi_{R_n}(r).
\]

Otherwise, joining the projections can produce **spurious tuples**: combinations generated after the join that never existed in the original data.

In the relational model under set semantics, if the projections cover all attributes of \(R\), joining the projections always contains the original tuples. The main risk is **generating extra tuples**. The term "lossy decomposition" refers to **losing information about which combinations were actually present**, not necessarily losing attribute values.

## 3. Definition of a Join Dependency

A join dependency on \(R(U)\), written:

\[
*\{R_1,R_2,\ldots,R_n\},
\]

where each \(R_i\subseteq U\) and \(\bigcup_iR_i=U\), states that **every valid state** \(r\) of \(R\) must satisfy:

\[
\boxed{\quad
r=\bowtie_{i=1}^{n}\pi_{R_i}(r)
\quad}
\]

In other words, the original relation **is completely determined** by its projections onto these attribute sets.

For example, with:

~~~text
SUPPLY(supplier_id, part_id, project_id)
~~~

we can consider the JD:

~~~text
*{
    (supplier_id, part_id),
    (supplier_id, project_id),
    (part_id, project_id)
}
~~~

This JD holds only when **every triple permitted by the three pairwise relations must exist in the original relation**, and of course every triple in the original relation has the corresponding three pairs. This is a **strong rule** that requires confirmation from the business.

### Trivial and Non-Trivial JDs

A JD is **trivial** if at least one attribute set satisfies \(R_i=U\). In that case, one projection is already the entire original relation, so the join condition adds no new independent constraint.

A JD is **non-trivial** when no \(R_i\) equals \(U\). The three-projection dependency `(supplier_id,part_id)`, `(supplier_id,project_id)`, `(part_id,project_id)` above is a non-trivial JD because each projection drops one attribute.

**Note:** sample data that happens to satisfy the join is not enough to prove a JD is a valid constraint over **all future valid data**. Determination must still come from business requirements.

## 4. Counterexample: Three Pairwise Relations Create a Spurious Triple

Suppose the `SUPPLY` table stores **three actual contracts**:

| supplier_id | part_id | project_id |
|---|---|---|
| S1 | P1 | J2 |
| S1 | P2 | J1 |
| S2 | P1 | J1 |

Project onto the three pairwise attribute sets:

**SUPPLIER_PART**

| supplier_id | part_id |
|---|---|
| S1 | P1 |
| S1 | P2 |
| S2 | P1 |

**SUPPLIER_PROJECT**

| supplier_id | project_id |
|---|---|
| S1 | J2 |
| S1 | J1 |
| S2 | J1 |

**PART_PROJECT**

| part_id | project_id |
|---|---|
| P1 | J2 |
| P2 | J1 |
| P1 | J1 |

Now join all three pairwise tables:

~~~sql
SELECT sp.supplier_id, sp.part_id, sj.project_id
FROM supplier_part AS sp
JOIN supplier_project AS sj
  ON sj.supplier_id = sp.supplier_id
JOIN part_project AS pj
  ON pj.part_id = sp.part_id
 AND pj.project_id = sj.project_id;
~~~

In addition to the three original rows, the query produces:

~~~text
(S1, P1, J1)    -- spurious triple compared to original contracts
~~~

Because:

- `(S1,P1)` is in `SUPPLIER_PART`.
- `(S1,J1)` is in `SUPPLIER_PROJECT`.
- `(P1,J1)` is in `PART_PROJECT`.

Yet there is no actual contract `(S1,P1,J1)` in the initial table.

<details>
<summary>Why can joining three relations still generate spurious tuples?</summary>

The condition "**all three pairs exist**" is weaker than "**the actual triple exists**". A supplier–part pair may come from a contract for one project, the supplier–project pair from a contract for another part, and the part–project pair from a different supplier. The join combines separate pairwise evidence into a triple that does not exist in the system.

</details>

Thus under the **actual contracts** semantics, the JD `*{SP,SJ,PJ}` **does not hold**; decomposing into three pairwise tables **loses information about the triples**. This is why you cannot arbitrarily delete a ternary relation simply because three binary relations exist.

## 5. When Does a Ternary JD Actually Hold?

Keep the same three entities, but change the **business rule** to:

> A supplier **is eligible** to supply a part to a project **if and only if** all three corresponding pairs are approved. There are no additional constraints at the triple level.

Then the set of valid triples can **be defined** by the join:

~~~text
ELIGIBLE_SUPPLY =
    SUPPLIER_PART
    ⋈ SUPPLIER_PROJECT
    ⋈ PART_PROJECT
~~~

Suppose the three pairwise relations are as before. We **must accept** `(S1,P1,J1)` as an **eligible supply privilege**; even without a contract yet, it is still a valid eligibility.

The set of eligible triples now has four rows:

| supplier_id | part_id | project_id |
|---|---|---|
| S1 | P1 | J2 |
| S1 | P2 | J1 |
| S2 | P1 | J1 |
| S1 | P1 | J1 |

Projecting and rejoining produces no fifth row. The JD is satisfied in this example, and the **"if and only if"** rule is the basis for requiring the JD to hold over valid data in general.

### Both Tables May Need to Coexist

In a real application, **both concepts** may well be needed:

~~~text
ELIGIBLE_SUPPLY   -- supply eligibility, derived from pairwise approvals
ACTUAL_CONTRACTS  -- signed contracts, storing independent triple events
~~~

`ACTUAL_CONTRACTS` can use a `contract_id` key and reference an eligible triple, while also storing contract attributes such as signing date, quantity, price, and validity period. Do not treat an eligibility privilege as an executed contract.

A small shift in business definition completely changes the answer about the JD. That is why you must clarify **the meaning of one row of data** before normalizing.

## 6. Diagram Illustrating Derived Triples

~~~mermaid
flowchart LR
    SP["Supplier – Part\n(S, P)"] --> J["Join on shared keys"]
    SJ["Supplier – Project\n(S, J)"] --> J
    PJ["Part – Project\n(P, J)"] --> J
    J --> E["Eligible triples\n(S, P, J)"]
~~~

The diagram applies only to the rule where **eligibility is determined by three pairwise approvals**. In the **actual contracts** model, a separate entity/event is required to record the triple; do not use the join result as proof of a contract.

## 7. How Do JDs Relate to FDs and MVDs?

### 7.1. Functional Dependencies (FDs)

An FD:

\[
X\rightarrow Y
\]

means each value of \(X\) determines **one value** of \(Y\) in every valid state.

For example, `order_id → customer_id` helps identify the single-order grain. FDs also provide a losslessness condition for decomposing into **two relations** under an FD set:

For \(R\rightarrow R_1,R_2\), the decomposition has a lossless join under \(F\) if and only if:

\[
(R_1\cap R_2)\rightarrow R_1
\quad\text{or}\quad
(R_1\cap R_2)\rightarrow R_2
\]

is implied by \(F\).

For instance, \(R(A,B,C)\), \(F=\{A\rightarrow B\}\), split into `R1(A,B)` and `R2(A,C)` is lossless, because the intersection \(\{A\}\) determines \(\{A,B\}\).

**Limitation:** this simple criterion applies directly to a **binary decomposition under FDs**. You must not test isolated pairs in a three- or four-table decomposition and automatically conclude that the entire join is lossless.

### 7.2. Multivalued Dependencies (MVDs)

An MVD:

\[
X\twoheadrightarrow Y
\]

states that, holding \(X\) fixed, the values of \(Y\) are **independent** of the remaining attributes \(Z=U-(X\cup Y)\).

On \(R(X,Y,Z)\), an MVD is equivalent to a two-projection JD:

\[
X\twoheadrightarrow Y
\quad\Longleftrightarrow\quad
*\{XY,XZ\}.
\]

For example, with `EMPLOYEE_PROFILE(employee_id,skill,language)`, when skill and language sets are **independent**, we have `employee_id ↠ skill` and can losslessly decompose into `(employee_id,skill)` and `(employee_id,language)` by the MVD.

### 7.3. General JDs

A general JD may require **three or more projections**. For `SUPPLY(S,P,J)`, the rule:

~~~text
*{ (S,P), (S,J), (P,J) }
~~~

requires **all three pairs to be present** for the triple to be present. This is not merely shorthand for an FD or any two-projection MVD.

| Constraint type | Core question | Related decomposition |
|---|---|---|
| **FD** \(X\rightarrow Y\) | Does one \(X\) uniquely determine \(Y\)? | Finding keys, 2NF/3NF/BCNF, many binary splits |
| **MVD** \(X\twoheadrightarrow Y\) | Is the set \(Y\) independent of \(Z\) when holding \(X\) fixed? | Two projections `XY` and `XZ`, 4NF |
| **JD** \(*\{R_1,\ldots,R_n\}\) | Does joining all projections recover the **exact** relation? | General decomposition, especially multi-projection, 5NF |

FDs can imply a particular JD, and MVDs are the two-projection special case of JDs, yet **not every JD can be derived from FDs or MVDs**. That remaining gap is the motivation for 5NF.

## 8. Fifth Normal Form (5NF) and the Limits of 4NF

**Fifth Normal Form (5NF)**, also called **project-join normal form (PJNF)**, requires that **every non-trivial JD** that holds on the relation must **be implied by the candidate keys** of the relation.

Practical interpretation: there remains no **non-trivial, normalization-relevant** lossless-join decomposition whose validity relies on an independent JD rule not already guaranteed by the keys.

In `SUPPLY(S,P,J)` representing **eligibility** under the three-pair rule:

- Suppose there are no non-trivial FDs among `S`, `P`, and `J`: a supplier has many parts and projects; a part has many suppliers and projects; a project has many suppliers and parts.
- The candidate key of the ternary relation is `(S,P,J)`, since no smaller attribute set determines the whole triple under confirmed FDs.
- If there are no other non-trivial MVDs, the relation may already be in **4NF**.
- Yet the JD `*{SP,SJ,PJ}` still holds by business rule; it is **not implied by the key (S,P,J) alone**.

Therefore, the eligibility relation is not yet in **5NF** and can be decomposed into three pairwise relations to avoid storing redundant triples.

Key takeaway: **4NF handles non-trivial MVDs; 5NF also considers multi-projection JDs**. You cannot conclude a table is free of join-related redundancy merely because it satisfies BCNF or 4NF.

### Do Not Infer 5NF Simply by Counting Columns

A three-attribute table **does not automatically** have a non-trivial JD, and a table with more than three attributes **does not necessarily** need splitting. Only propose decomposition when the business rules genuinely guarantee that **projecting and rejoining produces no spurious tuples**.

## 9. Multi-Table Decomposition: What Can and Cannot Be Guaranteed?

With multiple child relations, there are three distinct groups of questions:

| Aspect | Question to answer | Approach |
|---|---|---|
| **Lossless join** | Does joining the tables produce spurious tuples? | Prove the JD from business constraints, inference rules, or the *chase* technique |
| **Dependency preservation** | Can the original FDs/JDs still be checked on the child tables? | Examine projected constraints on each table and any required cross-table constraints |
| **Operational cost** | Do reads, writes, indexes, and integrity checks meet workload needs? | Measure queries, intermediate row counts, update frequency, and join cost |

A **lossless** decomposition may still **fail to preserve functional dependencies** via local checks alone.

### Example: Lossless Yet Fails to Preserve an FD

Given \(R(A,B,C)\) with:

~~~text
F = {
    AB → C,
    C  → B
}
~~~

Decomposing into `R1(C,B)` and `R2(A,C)` is **lossless**, because their intersection is `C`, and `C → B`.

However, `AB → C` **is not preserved** solely by the FDs on each child table. We could have:

~~~text
R1(C,B) = {(c1,b1), (c2,b1)}   -- satisfies C → B
R2(A,C) = {(a1,c1), (a1,c2)}
~~~

Each child table is valid under its local dependencies, yet upon joining:

~~~text
(a1,b1,c1)
(a1,b1,c2)
~~~

we get the same `(A,B)` with two different `C` values, **violating `AB → C`**. Therefore, enforcing this rule may require cross-table validation or a different decomposition.

**Lossless reconstruction on join** and **preserving local dependency enforcement** are two separate requirements. In practical design, include both in your decision criteria.

### Why Binary Rules Are Not Enough for Multiple Tables

In `SUPPLY(S,P,J)`, the three pairs `SP`, `SJ`, and `PJ` all intersect pairwise. Simply sharing common columns does not guarantee the three-way combination is an actual tuple. If you treat the join as a sequence of steps, proving each step requires examining the **intermediate relation** and the **dependencies that truly hold** on it; checking each pair in isolation is insufficient.

For complex schemas, the **tableau/chase** method can test lossless join under a given constraint set. The test must include confirmed FDs, MVDs/JDs and a clear understanding of problem scope; never treat a clean join on a data sample as a general proof.

## 10. Verifying with SQL: Finding Triples Produced by Joining That Never Existed

Suppose a staging table stores triples:

~~~text
staging_supply(supplier_id, part_id, project_id)
~~~

To check whether the **current data state** satisfies the JD `*{SP,SJ,PJ}`, run:

~~~sql
WITH triples AS (
    SELECT DISTINCT supplier_id, part_id, project_id
    FROM staging_supply
    WHERE supplier_id IS NOT NULL
      AND part_id IS NOT NULL
      AND project_id IS NOT NULL
),
sp AS (
    SELECT DISTINCT supplier_id, part_id
    FROM triples
),
sj AS (
    SELECT DISTINCT supplier_id, project_id
    FROM triples
),
pj AS (
    SELECT DISTINCT part_id, project_id
    FROM triples
)
SELECT
    sp.supplier_id,
    sp.part_id,
    sj.project_id
FROM sp
JOIN sj
  ON sj.supplier_id = sp.supplier_id
JOIN pj
  ON pj.part_id = sp.part_id
 AND pj.project_id = sj.project_id
WHERE NOT EXISTS (
    SELECT 1
    FROM triples AS t
    WHERE t.supplier_id = sp.supplier_id
      AND t.part_id = sp.part_id
      AND t.project_id = sj.project_id
)
ORDER BY sp.supplier_id, sp.part_id, sj.project_id;
~~~

Each returned row is a **new triple generated by the three projections that is missing from the original table**. For the three-contract table in Section 4, the query returns:

~~~text
S1 | P1 | J1
~~~

From a theoretical viewpoint, this is a **counterexample to the JD on the inspected state**. From a business viewpoint, decide:

- If `staging_supply` records **actual contracts**, the missing row is valid; decomposing into three pairwise tables is the wrong assumption.
- If `staging_supply` is required to contain **every triple eligible under the three pairs**, the missing row may reflect a sync bug or incomplete data; investigate before fixing.

**Query limitations:**

- It excludes rows with `NULL` and uses `DISTINCT` to approximate set semantics. Missing and duplicate data must be checked separately.
- Returning zero rows **does not prove** the JD holds for all future data.
- On large datasets, a three-way join can produce large intermediate combinations; choose a test scope and inspect the query plan.
- SQL generally uses **multiset (bag) semantics**; relational JDs use **set semantics**. Distinguish duplicate rows created by joins from triples with distinct values.

### Checking Join Fan-Out

An auxiliary check:

~~~sql
WITH sp AS (
    SELECT DISTINCT supplier_id, part_id FROM staging_supply
    WHERE supplier_id IS NOT NULL AND part_id IS NOT NULL
),
sj AS (
    SELECT DISTINCT supplier_id, project_id FROM staging_supply
    WHERE supplier_id IS NOT NULL AND project_id IS NOT NULL
),
pj AS (
    SELECT DISTINCT part_id, project_id FROM staging_supply
    WHERE part_id IS NOT NULL AND project_id IS NOT NULL
)
SELECT COUNT(*) AS joined_triples
FROM sp
JOIN sj ON sj.supplier_id = sp.supplier_id
JOIN pj
  ON pj.part_id = sp.part_id
 AND pj.project_id = sj.project_id;
~~~

This query is useful for **estimating result volume**; if the source contains `NULL`s, the filtering on individual projections can differ from the JD check query above. For an **exact** tuple-count comparison, use the same non-NULL `triples` CTE for all three projections and the base set.

## 11. SQL Schema When the Business Truly Only Needs Three Pairwise Approvals

If only **eligibility** needs to be determined, we can store three base relations:

~~~sql
CREATE TABLE suppliers (
    supplier_id VARCHAR(30) PRIMARY KEY,
    supplier_name VARCHAR(200) NOT NULL
);

CREATE TABLE parts (
    part_id VARCHAR(30) PRIMARY KEY,
    part_name VARCHAR(200) NOT NULL
);

CREATE TABLE projects (
    project_id VARCHAR(30) PRIMARY KEY,
    project_name VARCHAR(200) NOT NULL
);

CREATE TABLE supplier_parts (
    supplier_id VARCHAR(30) NOT NULL REFERENCES suppliers(supplier_id),
    part_id VARCHAR(30) NOT NULL REFERENCES parts(part_id),
    PRIMARY KEY (supplier_id, part_id)
);

CREATE TABLE supplier_projects (
    supplier_id VARCHAR(30) NOT NULL REFERENCES suppliers(supplier_id),
    project_id VARCHAR(30) NOT NULL REFERENCES projects(project_id),
    PRIMARY KEY (supplier_id, project_id)
);

CREATE TABLE project_parts (
    project_id VARCHAR(30) NOT NULL REFERENCES projects(project_id),
    part_id VARCHAR(30) NOT NULL REFERENCES parts(part_id),
    PRIMARY KEY (project_id, part_id)
);
~~~

The list of eligible triples is computed by:

~~~sql
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
~~~

Advantages of this structure:

- Each pairwise approval is stored **once**.
- Composite primary keys prevent duplicate pairs.
- Foreign keys ensure referenced values exist.
- Triple supply eligibility **is derived consistently** from the three pairwise sources under the confirmed rule.

However, if **signed contracts** must be recorded, do not treat the join above as the contract record. Add a dedicated entity/event table, for example:

~~~sql
CREATE TABLE supply_contracts (
    contract_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    supplier_id VARCHAR(30) NOT NULL REFERENCES suppliers(supplier_id),
    part_id VARCHAR(30) NOT NULL REFERENCES parts(part_id),
    project_id VARCHAR(30) NOT NULL REFERENCES projects(project_id),
    signed_on DATE NOT NULL
);
~~~

If policy states each contract must belong to a **triple approved at the time of signing**, design a mechanism to validate all three pairs at that point in time — via transactions, triggers, domain services, or additional structures. Individual foreign keys to the three entity tables **do not automatically check** the three pairwise approvals.

### Physical Schema Considerations

Decomposition can reduce redundant storage while increasing joins on reads. Indexes on composite keys support certain access paths; reverse lookups, such as finding all suppliers for a part, may need secondary indexes. Benchmark with realistic data and workloads rather than assuming 5NF is always faster.

For read-heavy reports, consider a **view** or **materialized view** for eligible triples; when materializing, ensure refresh mechanisms and consistency with source data. Storing precomputed triples for speed does not change their **business definition**.

## 12. Limits of Decomposition and Choosing a Data Model

### A Multi-Dimensional Relation Can Have an Indivisible Meaning

For example, `DOCTOR_PATIENT_TREATMENT(doctor_id,patient_id,treatment_id)` may represent the event **a doctor administers a treatment to a patient**. Three pairwise relations:

~~~text
DOCTOR_PATIENT
DOCTOR_TREATMENT
PATIENT_TREATMENT
~~~

are not enough to prove a treatment triple actually occurred. When recording real events, keep the ternary relation or an event entity with attributes such as time, location, and encounter ID.

### Over-Decomposition Can Introduce Complexity

Even when theoretically lossless, a large number of tables can:

- Increase join cost, intermediate data volume, and query complexity.
- Make it harder to enforce business constraints that must be checked **across tables**.
- Complicate transactional updates, concurrency locking, and history management.
- Distort data interpretation if **grain** and effective dates are not aligned.

Therefore, evaluate **correctness first**, then query requirements, indexes, and operational cost. Do not split every three-column table into pairs merely to chase a higher normal form on paper.

### Relational, Document, Graph, and Analytical Models

| Model | How ternary relationships / JDs are represented | Risks to avoid |
|---|---|---|
| **Relational** | Three pairwise tables when the business confirms the JD; keep the ternary table if it is an independent event | Spurious tuples on join, missing cross-table dependency checks |
| **Document** | Contract documents can contain the triple; pairwise approvals can be stored separately or embedded per query needs | Treating embedded/aggregated data as proof of all valid combinations |
| **Graph** | Three edge types represent pairwise relationships; actual triples may need an event node or relationship reification | Three pairwise edges do not prove an actual ternary event |
| **Analytical** | Fact table holds the exact event grain; bridge tables record many-to-many rules clearly | Joining multiple bridges creates spurious combinations and inflates measures |

In a graph model, a triangle of three edges can represent **three pairwise relationships** without meaning "a three-way transaction occurred". In an analytical model, joining bridge tables requires checking row counts and grain before computing `SUM`, `COUNT`, or business KPIs.

## 13. Workflow to Evaluate a Multi-Relation Decomposition

### Step 1 — Write the Exact Business Statement

Ask: "Is a triple real whenever **each pair is valid**, or does it require a separate triple-level event/approval?" This question decides whether a JD holds.

### Step 2 — Identify Grain, Scope, and Time

Is each row an **eligibility**, a **contract**, an **execution**, or a **historical record**? Are the pairs approved for the **same point in time**? If approvals have expiration dates, model effective time intervals properly; joining pairs from different time periods can fabricate invalid eligibility.

### Step 3 — Build and Confirm Dependencies

List FDs, MVDs, and JDs from confirmed rules. For a JD, state the attribute set of **each projection** and require that **every permitted combination be present**. Do not infer a JD just because joining a few sample rows yields no spurious tuples.

### Step 4 — Test Counterexamples

Construct a scenario where all pairs exist yet **the triple does not**. If the business considers that state valid, the proposed JD is **wrong**. If the triple must be valid, ensure the system has a mechanism to derive or represent it.

### Step 5 — Prove Losslessness and Check Dependency Preservation

For two tables under FDs, you can use the rule that the intersection determines one table. For multiple projections or complex JDs, prove losslessness using real constraints or appropriate inference tools such as the *chase*. Separately verify whether FDs/JDs requiring enforcement can still be checked across the decomposed tables.

### Step 6 — Physical Design and Query Testing

Choose primary keys, foreign keys, indexes, and change-control mechanisms aligned with the business. Measure join costs with representative data; test permitted, forbidden, empty, duplicate, and historical cases. If denormalizing for reporting, document the **source of truth** and synchronization strategy.

## 14. Common Misconceptions

| Misconception | Consequence | How to fix |
|---|---|---|
| "Three pairwise relations suffice to represent any ternary relation" | Generates spurious triples | Verify the JD rule; if the triple is an event, keep the ternary relation |
| "A join produced no spurious tuples on the sample, so the decomposition is always lossless" | Fails when new data arrives | Prove across all valid states and search for counterexamples |
| "Already in BCNF/4NF means no need to check JDs" | Misses 5NF-related redundancy | Evaluate non-trivial JDs not implied by keys |
| "A JD is an MVD with extra attributes on the right-hand side" | Misunderstands multi-projection constraints | An MVD is the special case of a **two-projection** JD |
| "Lossless equals dependency-preserving" | Constraints require cross-table checking | Verify the two properties independently |
| "Foreign keys to three entity tables guarantee the three pairs are approved" | Accepts unapproved triples | Validate the pairwise relations or apply corresponding business constraints |
| "5NF always performs better" | Too many joins or update complexity | Measure workload and design appropriate indexes and views |
| "Pairs valid at different times still form a valid triple" | Fabricates invalid privileges/contracts across time | Account for effective time intervals across all three relations |

## 15. Practice Exercises with Solutions

### Exercise 1 — Detecting a Spurious Triple

Given `R(S,P,J)`:

~~~text
(S1,P1,J2)
(S1,P2,J1)
(S2,P1,J1)
~~~

Decompose `R` into `SP`, `SJ`, `PJ` and rejoin them. Which new triple appears?

**Solution:** `(S1,P1,J1)`. The pairs `S1–P1`, `S1–J1`, and `P1–J1` all appear in the three projections, so the join produces this triple even though it was not in the original \(R\). The decomposition is **not lossless** on that state.

### Exercise 2 — When Is the New Triple Valid?

Rule: "A supplier is eligible to supply a part to a project **if and only if** the supplier is approved for the part, the supplier is approved for the project, and the part is allowed in the project." Triple `(S1,P1,J1)` has all three pairs approved, but no purchase order exists yet.

**Solution:** This triple **is eligible**, because the rule defines eligibility in terms of the three pairs; it is **not yet an actual purchase order or contract**. You can join the three pairwise tables to derive eligibility; a separate transaction table is needed to record executed events.

### Exercise 3 — Distinguishing FDs, MVDs, and JDs

On \(R(A,B,C)\), the business asserts \(A\twoheadrightarrow B\). Which relations can it be losslessly decomposed into?

**Solution:** By the equivalence between an MVD and a two-projection JD, \(*\{AB,AC\}\) holds; thus decomposing into `R1(A,B)` and `R2(A,C)` has a **lossless join**. This does not mean \(A\rightarrow B\); one \(A\) can still have multiple \(B\) values.

### Exercise 4 — Checking 5NF

Given `PERMISSION(S,P,J)`, with only `(S,P,J)` as a candidate key under confirmed FDs, and the non-trivial JD \(*\{SP,SJ,PJ\}\) holding by business rule.

**Solution:** This JD **is not implied by the key `SPJ` alone**, so the table is not yet in **5NF**. It can be split into `SP`, `SJ`, and `PJ` according to the confirmed JD. Do not draw the same conclusion for an actual contracts table if the JD does not hold.

### Exercise 5 — Lossless Yet Not FD-Preserving

Given \(R(A,B,C)\), \(F=\{AB\rightarrow C,\ C\rightarrow B\}\), split into `R1(C,B)` and `R2(A,C)`. Is the decomposition lossless? Does it preserve `AB → C`?

**Solution:** **Lossless**, because `C` is the intersection of the two tables and `C → B`. **Does not preserve `AB → C`** using local dependencies on each table alone; for instance, `R1={(c1,b1),(c2,b1)}` and `R2={(a1,c1),(a1,c2)}` yield two tuples with the same `(a1,b1)` but different `C`.

### Exercise 6 — Effective Time

A supplier was approved for part `P1` in January, approved for project `J1` in February, while the project only permitted `P1` in March. Can we join the three approval records by ID alone and assert supply eligibility at a given point in time?

**Solution:** No. The approvals were not necessarily **active at the same point in time**. You need to model effective date intervals or a rule specifying the evaluation timestamp; a JD on the three IDs alone cannot express this temporal condition.

### Exercise 7 — Sample Data Producing No Spurious Tuples

A table `R(S,P,J)` has only one triple, and projecting into `SP`, `SJ`, `PJ` and rejoining still yields only one tuple. Can we conclude the JD always holds?

**Solution:** No. A single row satisfies many coincidental dependencies. To conclude the JD is a schema constraint, you must confirm that **every triple having all three pairs must exist** in every valid state.

## 16. Checklist Before Decomposing into Multiple Relations

- [ ] Defined accurately whether each row is an **eligibility**, **event**, **contract**, or **historical record**.
- [ ] Confirmed the JD with the **attribute sets of each projection**, not just from sample data.
- [ ] Tested the case where all pairs exist yet the actual triple does not.
- [ ] Proved the decomposition is **lossless-join** under business constraints.
- [ ] Checked **dependency preservation** independently of losslessness.
- [ ] Distinguished FDs, two-projection MVDs, and general JDs.
- [ ] Evaluated whether any non-trivial JD exists that is **not implied by candidate keys** before concluding 5NF.
- [ ] Designed keys, foreign keys, and cross-table constraint enforcement mechanisms where needed.
- [ ] Reviewed effective time, duplicate data, `NULL`, indexes, and intermediate row counts during joins.
- [ ] Tested queries at the proper grain to avoid inflating quantities, revenue, or fabricating events.

**Takeaway:** A **join dependency** states that a relation can be reconstructed **exactly from multiple projections**. When business rules truly specify that combinations are completely determined by pairwise relations, decomposition eliminates redundancy and supports 5NF. When the triple carries its own event semantics, joining the pairs can fabricate spurious data. Business rules and a **lossless-join** proof must come before the decision to split tables.
