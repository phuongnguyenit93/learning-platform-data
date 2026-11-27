# Lossless-Join Decomposition and Criteria for Exact Data Reconstruction

## Learning Objectives

In the **DATABASE_DATA_MODELING** module, splitting a large relation into tables with clear grain reduces redundancy and enables better key and constraint design. However, a decomposition is safe only when **the child relations retain enough information to reconstruct the original relation accurately**. This is the **lossless-join decomposition** requirement.

After this lesson in the **Data Dependencies** chapter, you will be able to:

1. State the formal definition of a lossless-join decomposition and explain what a **spurious tuple** is.
2. Apply the criterion that **the attribute intersection determines one of the two child relations** for binary decompositions under functional dependencies (FDs).
3. Distinguish a **lossless-join** decomposition from a **dependency-preserving** decomposition.
4. Verify decompositions into three or more tables using step-by-step reasoning or the **tableau/chase** method.
5. Use SQL to find counterexamples in existing data, while understanding the limits of checking against sample data.
6. Connect the results to 3NF/BCNF/4NF normalization, physical schemas, and choosing among relational, document, graph, and analytical models.

## 1. Why Can Splitting a Table Corrupt Data?

Suppose a training management system has the relation:

~~~text
STUDENT_TUTOR(student_id, course_id, tutor_id)
~~~

Each row records **one student taking one course with a specific tutor**. Data:

| student_id | course_id | tutor_id |
|---|---|---|
| SV01 | C01 | GV01 |
| SV02 | C01 | GV02 |

A designer splits the relation into:

~~~text
STUDENT_COURSE(student_id, course_id)
COURSE_TUTOR(course_id, tutor_id)
~~~

Joining on `course_id` yields:

| student_id | course_id | tutor_id | Origin |
|---|---|---|---|
| SV01 | C01 | GV01 | Original row |
| SV01 | C01 | GV02 | **Spurious tuple** |
| SV02 | C01 | GV01 | **Spurious tuple** |
| SV02 | C01 | GV02 | Original row |

The two individual tables tell us **which student takes which course** and **which tutor teaches which course**, but they have lost the information about **which tutor coaches which student**. The join fabricated two pairings that were never assigned.

That is a **lossy decomposition**. The word "lossy" does not necessarily mean losing the values `SV01` or `GV01`; what is lost is **information about the true associations among attributes**.

If business rules dictate that **each course has exactly one tutor**, then `course_id → tutor_id` holds and the scenario above is no longer valid. In that case, the two-table decomposition can have a lossless join. The conclusion depends on **business rules**, not on the intuition that the tables share a column.

## 2. Formal Definition: Projecting and Joining Must Equal the Original Relation

Given a relation schema \(R(U)\), where \(U\) is the set of attributes. Suppose it is decomposed into \(R_1(U_1),R_2(U_2),\ldots,R_n(U_n)\), with:

\[
U_1\cup U_2\cup\cdots\cup U_n=U.
\]

Let \(\pi_{U_i}(r)\) denote **the projection** of a data state \(r\) of \(R\) onto attributes \(U_i\). Let \(\bowtie\) denote **natural join**, matching tuples with equal values on common attributes.

The decomposition is called **lossless-join with respect to constraint set \(\Sigma\)** when:

\[
\boxed{
\forall r\models\Sigma,\quad
r=\pi_{U_1}(r)\bowtie\pi_{U_2}(r)
\bowtie\cdots\bowtie\pi_{U_n}(r)
}
\]

Here \(r\models\Sigma\) means state \(r\) satisfies **all confirmed business constraints** in \(\Sigma\). The set \(\Sigma\) may contain FDs, MVDs, JDs, or other constraints depending on the problem.

The definition imposes two simultaneous requirements:

- **No missing original tuples:** every tuple in \(r\) must be reconstructed after joining.
- **No spurious tuples:** the join result must not create extra tuples not belonging to \(r\).

For projections of the **same original relation** under **set semantics** of the relational model where the attribute sets cover \(U\), all original tuples always appear in the join:

\[
r\subseteq \bowtie_i\pi_{U_i}(r).
\]

Therefore, in this setting, proving losslessness essentially means proving **no spurious tuples are generated**. If child tables are populated independently rather than as projections of one relation, you must also verify data completeness and consistency of the inputs.

### Two Terms to Distinguish

| Term | Exact meaning | Example |
|---|---|---|
| **Lossless join** | Projecting onto child tables and joining returns **the exact original tuple set** for every valid state | Splitting orders and order lines when order ID determines order details |
| **Lossy join** | There exists a valid state where joining produces **spurious tuples** | Splitting student–course–tutor assignments when there is no one-tutor-per-course rule |

"Lossless" is a **property of a decomposition under constraints**. A `JOIN` query that happens to return the right rows on a few sample records does not prove the entire design is lossless.

## 3. Necessary and Sufficient Condition for Binary Decomposition Under FDs

Consider the decomposition:

\[
R(U)\longrightarrow R_1(U_1), R_2(U_2),
\qquad U_1\cup U_2=U.
\]

Let \(I=U_1\cap U_2\) be the **intersection** attribute set. When the constraints under consideration **consist solely of functional dependencies \(F\)**, the two-relation decomposition is **lossless-join with respect to \(F\)** if and only if:

\[
\boxed{
F\models I\rightarrow U_1
\quad\text{or}\quad
F\models I\rightarrow U_2
}
\]

Put simply: **the shared columns must determine all columns of at least one child table**.

If \(I\) itself is a key of \(R_1\) or \(R_2\) under the dependencies implied by \(F\), the condition is satisfied. The condition does not require \(I\) to be a key of **both** tables.

### Why Does This Criterion Work?

Suppose \(I\rightarrow U_1\). When two tuples in \(R_1\) and \(R_2\) match on \(I\), the remaining part in \(R_1\) is already uniquely determined by \(I\). Hence the join cannot arbitrarily pair two different variants of \(U_1-I\) with a single value of \(I\). When the tables are projections of the same valid relation, every joined tuple must correspond to an original tuple.

### Testing with Attribute Closure

There is no need to enumerate every implied dependency in \(F^+\). Simply compute:

\[
I_F^+.
\]

Then check:

~~~text
If U1 ⊆ I+ or U2 ⊆ I+:
    the two-table decomposition is lossless under F
Otherwise:
    the decomposition is not guaranteed lossless by the FDs in F alone
~~~

When restricted **solely to FDs**, failing both checks means the decomposition is not lossless **for all relations satisfying F**: there exists a valid state that generates spurious tuples. If **MVD/JD** constraints also apply, a decomposition can still be lossless even if it fails this FD criterion.

## 4. Valid Example: Splitting Orders and Order Lines

Suppose the combined table is:

~~~text
ORDER_LINE_FLAT(
    order_id, customer_id,
    line_no, product_id, quantity
)
~~~

The grain of one row is **one line item in one order**. The business confirms:

~~~text
F = {
    order_id            → customer_id,
    (order_id, line_no) → product_id, quantity
}
~~~

Proposed decomposition:

~~~text
ORDERS(order_id, customer_id)
ORDER_ITEMS(order_id, line_no, product_id, quantity)
~~~

Check:

1. \(U_1=\{\text{order_id},\text{customer_id}\}\).
2. \(U_2=\{\text{order_id},\text{line_no},\text{product_id},\text{quantity}\}\).
3. Intersection \(I=U_1\cap U_2=\{\text{order_id}\}\).
4. From \(F\): \(\text{order_id}\rightarrow\text{customer_id}\).
5. By reflexivity and union, \(\text{order_id}\rightarrow\{\text{order_id},\text{customer_id}\}=U_1\).

Thus the decomposition is **lossless-join** under \(F\).

### Seeing It Clearly in Data

**ORDER_LINE_FLAT**

| order_id | customer_id | line_no | product_id | quantity |
|---|---|---:|---|---:|
| DH01 | KH01 | 1 | SP01 | 2 |
| DH01 | KH01 | 2 | SP02 | 1 |
| DH02 | KH02 | 1 | SP01 | 3 |

Project into:

~~~text
ORDERS:
    (DH01, KH01)
    (DH02, KH02)

ORDER_ITEMS:
    (DH01, 1, SP01, 2)
    (DH01, 2, SP02, 1)
    (DH02, 1, SP01, 3)
~~~

Joining on `order_id` recovers **the exact three original rows**. This illustrates the conclusion already proved from FDs; the three-row example itself is **not a general proof**.

### When a Business Condition Is Missing

If an `order_id` can be reused **across two stores**, the rule `order_id → customer_id` may fail across the system-wide dataset. In that case, clarify a global ID or use the pair `(store_id, order_id)` in both child tables and in the join condition.

Joining on a key missing its **identifier scope** can produce wrong results even when the table structure looks reasonable.

## 5. Invalid Example: Missing Attributes for a Proper Join

Consider relation \(R(A,B,C)\) with no guaranteed non-trivial FDs. Valid state:

| A | B | C |
|---|---|---|
| a1 | b1 | c1 |
| a2 | b1 | c2 |

Decompose into:

~~~text
R1(A,B) = {(a1,b1), (a2,b1)}
R2(B,C) = {(b1,c1), (b1,c2)}
~~~

The intersection is \(\{B\}\). Neither \(B\rightarrow A\) nor \(B\rightarrow C\) holds, so neither \(B\rightarrow AB\) nor \(B\rightarrow BC\) holds.

Joining on \(B\) yields:

~~~text
(a1, b1, c1)  -- original
(a1, b1, c2)  -- spurious tuple
(a2, b1, c1)  -- spurious tuple
(a2, b1, c2)  -- original
~~~

This is a **valid counterexample** proving the decomposition is not lossless under an empty FD set.

An important observation: having both child tables contain `B` **is not enough**. There must be a business constraint ensuring the shared attributes determine one side, or a more general constraint such as an MVD/JD.

## 6. A Decomposition Covering Only Part of the Columns Is a Different Issue

Given \(R(A,B,C)\), keeping only `R1(A,B)` and dropping `C` with no other table containing `C` is **not** a complete decomposition of \(R\), because:

\[
U_1\ne U.
\]

Values of \(C\) cannot be recovered by joining when that attribute does not appear in any child relation. Before testing the intersection criterion, verify:

\[
\bigcup_i U_i=U.
\]

This preliminary check is frequently forgotten when running the 3NF synthesis algorithm from functional dependencies.

## 7. Decomposing into Three or More Tables: Checking by Chain

With multiple child relations \(R_1,R_2,\ldots,R_n\), you cannot simply see pairs of tables sharing a column and conclude **the entire join** recovers the exact data. One practical proof method is building a **chain of lossless binary decompositions**.

### Three-Table Decomposition Example with Proof

Consider:

\[
R(A,B,C,D)
\]

with:

~~~text
F = {
    A → B,
    B → C,
    C → D
}
~~~

We want to form three relations:

~~~text
R1(A,B)
R2(B,C)
R3(C,D)
~~~

Instead of checking pairs in isolation, we prove:

**Step 1:** Split \(R(A,B,C,D)\) into \(T(A,B,C)\) and \(R_3(C,D)\).

The intersection is \(\{C\}\). Because \(C\rightarrow D\), we have \(C\rightarrow CD\). Thus this step is **lossless** under \(F\).

**Step 2:** Further split \(T(A,B,C)\) into \(R_1(A,B)\) and \(R_2(B,C)\).

The intersection is \(\{B\}\). Because \(B\rightarrow C\), we have \(B\rightarrow BC\). This step is also **lossless**.

Combining them:

\[
r=\pi_{ABC}(r)\bowtie\pi_{CD}(r)
=\pi_{AB}(r)\bowtie\pi_{BC}(r)\bowtie\pi_{CD}(r).
\]

Hence **the entire three-table decomposition is lossless**.

~~~mermaid
flowchart TD
  R["R(A,B,C,D)"] --> T["T(A,B,C)"]
  R --> R3["R3(C,D)"]
  T --> R1["R1(A,B)"]
  T --> R2["R2(B,C)"]
~~~

The diagram shows **two decomposition steps**. Each step must be proved lossless using dependencies that hold on the relation being split; when they are, the entire chain is lossless.

### When No Simple Chain Is Found

A multi-table decomposition can still be lossless via a **multi-projection JD**, even if no step-by-step FD proof is found. You can use the **tableau/chase** method with the known dependency set. Never jump from "the binary FD criterion doesn't apply" to concluding that every general decomposition is lossy.

## 8. Tableau/Chase Method for Testing Losslessness Under FDs

**Chase** is a systematic reasoning procedure, especially useful when the number of child relations is large and manual inspection is error-prone. Below is the basic version using **functional dependencies**.

### Idea of Building the Symbol Table

Given original relation \(R(A_1,\ldots,A_m)\) and decomposition \(R_1,\ldots,R_n\):

1. Create **one tableau row for each child relation**.
2. For attribute \(A_j\) **present in** the child relation at row \(i\), enter the **distinguished symbol** \(a_j\).
3. For attribute \(A_j\) **absent from** the child relation at row \(i\), enter a distinct symbol \(b_{ij}\).
4. Apply FDs: if two rows agree on the entire left-hand side \(X\), equate their corresponding symbols on the right-hand side \(Y\); prefer distinguished symbols \(a_j\) when available.
5. Repeat until no changes occur. If **any row consists entirely of \(a_j\) symbols**, the decomposition is lossless under the given FDs.

When the constraints are **FDs**, this is the standard test; if MVDs/JDs are involved, appropriate chase rules for those dependency types must be used.

### Chase Example: \(R(A,B,C)\rightarrow R_1(A,B),R_2(A,C)\)

Given \(F=\{A\rightarrow B\}\). Initial tableau:

| Row | A | B | C |
|---|---|---|---|
| \(R_1(A,B)\) | \(a_A\) | \(a_B\) | \(b_{1C}\) |
| \(R_2(A,C)\) | \(a_A\) | \(b_{2B}\) | \(a_C\) |

Both rows share \(a_A\) in column \(A\). By \(A\rightarrow B\), column \(B\) must agree. Replace \(b_{2B}\) with \(a_B\):

| Row | A | B | C |
|---|---|---|---|
| \(R_1(A,B)\) | \(a_A\) | \(a_B\) | \(b_{1C}\) |
| \(R_2(A,C)\) | \(a_A\) | \(a_B\) | \(a_C\) |

Row \(R_2\) now consists entirely of distinguished symbols \((a_A,a_B,a_C)\). Therefore the decomposition is **lossless** under \(A\rightarrow B\).

If the FD `A → B` is removed and no other relevant constraints exist, the symbols never equate; no row contains all distinguished symbols. That aligns with the possibility of spurious tuples when joining the two projections.

### Notes When Using Chase

- Never equate two symbols arbitrarily without a valid dependency justifying it.
- The outcome depends on **the input constraint set**, not on sample row counts.
- With multiple dependency types, general chase can be complex; use tools/algorithms suited to the FDs, MVDs, or JDs in question.
- The goal is **proving over all valid states**, rather than merely test-running a `JOIN` on one export.

## 9. Relationship to MVDs and JDs

### Multivalued Dependencies Can Guarantee Losslessness Without FDs

Given:

~~~text
EMPLOYEE_PROFILE(employee_id, skill, language)
~~~

If the business confirms **each employee has two independent lists of skills and languages**, we have:

\[
\text{employee\_id}\twoheadrightarrow\text{skill}.
\]

Then the decomposition:

~~~text
EMPLOYEE_SKILLS(employee_id, skill)
EMPLOYEE_LANGUAGES(employee_id, language)
~~~

is **lossless under the MVD**, even though `employee_id` **does not uniquely determine** `skill` or `language`. The FD criterion that the intersection determines one child relation **does not hold**, yet the decomposition remains lossless thanks to multivalued independence.

This example shows that the FD criterion in Section 3 **does not cover all kinds of data constraints**.

### General Join Dependencies

A **join dependency**:

\[
*\{U_1,U_2,\ldots,U_n\}
\]

asserts that every valid state equals the join of its projections onto \(U_1,\ldots,U_n\). That statement itself is the losslessness guarantee for the corresponding decomposition.

For `SUPPLY(supplier_id,part_id,project_id)`, if triple supply eligibility is defined **solely by** three pairwise approvals:

~~~text
(supplier_id, part_id)
(supplier_id, project_id)
(part_id, project_id)
~~~

then the three-projection JD can hold. If the original table stores **actual supply contracts**, three pairwise approvals do not suffice to determine contracted triples, and joining can generate **spurious contracts**.

Therefore, do not infer a JD merely because pairwise relations exist, nor split a ternary relation into three pairwise tables without a confirmed business rule stating **every valid triple is completely determined by the pairs**.

## 10. Lossless Differs from Dependency Preservation

The two criteria serve two different goals:

| Criterion | Question | If not satisfied |
|---|---|---|
| **Lossless join** | Does projecting and rejoining recover **the exact original tuples**? | Spurious tuples can appear, corrupting query answers |
| **Dependency preservation** | Can **all original FDs** be inferred from FDs checked locally within each child table? | Some rules must be checked across multiple tables or via other mechanisms |

For FDs \(F\) and child relations \(R_i\), dependency preservation can be stated as:

\[
\left(\bigcup_i \pi_{R_i}(F)\right)^+=F^+,
\]

where \(\pi_{R_i}(F)\) is the set of FDs in \(F^+\) **using only attributes of \(R_i\)**. This is a projection of the **dependency set**, distinct from a projection of data.

### Example: Lossless Yet Not FD-Preserving

Consider \(R(A,B,C)\) with:

~~~text
F = {
    AB → C,
    C  → B
}
~~~

Decomposition:

~~~text
R1(C,B)
R2(A,C)
~~~

The intersection is \(\{C\}\). Since \(C\rightarrow B\), \(\{C\}\rightarrow\{B,C\}=U_1\). Thus the decomposition is **lossless**.

However, `AB → C` is not preserved by local FDs:

~~~text
R1(C,B) = {(c1,b1), (c2,b1)}
R2(A,C) = {(a1,c1), (a1,c2)}
~~~

Each child table can satisfy its local constraints. Upon joining, we get:

~~~text
(a1,b1,c1)
(a1,b1,c2)
~~~

Two tuples with the same `(A,B)` but different `C` violate `AB → C`. This proves that enforcing each child table separately **is not enough** to guarantee the original FD.

### Consequences for Normalization

- The standard **3NF synthesis** algorithm produces decompositions that are both **lossless-join** and **dependency-preserving** for the input FDs.
- Standard binary **BCNF** decomposition with properly chosen steps guarantees **lossless join**, but **does not always preserve all FDs**.
- Decomposing by MVDs to achieve **4NF** must be checked for losslessness using a genuinely valid multivalued dependency. Constraints involving triples/contracts may require **JD** and **5NF** analysis.

These are **properties of specific algorithms and constraints**, not a promise that simply reaching a higher normal form in each child table automatically preserves every business rule.

## 11. Checking Counterexamples with SQL

SQL helps detect spurious tuples in the **current data state**. However, it cannot by itself prove a decomposition is lossless for **all valid states**.

Suppose `staging_student_tutor(student_id, course_id, tutor_id)` stores **actual assignments**. We want to test splitting into `(student_id, course_id)` and `(course_id, tutor_id)`.

~~~sql
WITH original AS (
    SELECT DISTINCT student_id, course_id, tutor_id
    FROM staging_student_tutor
    WHERE student_id IS NOT NULL
      AND course_id IS NOT NULL
      AND tutor_id IS NOT NULL
),
student_course AS (
    SELECT DISTINCT student_id, course_id
    FROM original
),
course_tutor AS (
    SELECT DISTINCT course_id, tutor_id
    FROM original
),
reconstructed AS (
    SELECT sc.student_id, sc.course_id, ct.tutor_id
    FROM student_course AS sc
    JOIN course_tutor AS ct
      ON ct.course_id = sc.course_id
),
spurious AS (
    SELECT student_id, course_id, tutor_id FROM reconstructed
    EXCEPT
    SELECT student_id, course_id, tutor_id FROM original
)
SELECT *
FROM spurious
ORDER BY course_id, student_id, tutor_id;
~~~

With the two-row data from the opening section, the query returns:

~~~text
SV01 | C01 | GV02
SV02 | C01 | GV01
~~~

These are two tuples present in the join result but absent from the original table. On this data, the decomposition produced **spurious tuples**. If that state is **business-valid**, it refutes the proposed lossless decomposition.

### Why Is Zero Rows Returned Still Not Enough?

A sample with only **one tutor per course** can let the join reconstruct accurately by accident, even if the business later allows multiple tutors. Proving losslessness requires one of these foundations:

1. **FDs** satisfying the binary decomposition criterion.
2. **Confirmed MVDs or JDs** if relying on multivalued independence.
3. **Step-by-step proof or chase** for complex decompositions.

Do not draw a conclusion from a single empty `EXCEPT` query.

### Differences Between Relational Theory and SQL to Watch Out For

- Theoretical relational model uses **sets**: a tuple never appears twice. SQL generally uses **multisets (bags)**. Hence the example uses `SELECT DISTINCT` and `EXCEPT` to compare **sets of tuple values**.
- These queries exclude rows with `NULL`; missing data must be handled separately, because SQL `NULL` semantics can prevent `JOIN` or counts from reflecting full business meaning.
- Across DBMSs, the set-difference operator may be `EXCEPT` or `MINUS`. Adjust for the DBMS in use.
- If child tables are populated by **separate update workflows**, the fact that they were once projections of a single source does not guarantee they stay in sync later. Foreign keys, transactions, and consistency mechanisms are required.

## 12. From Losslessness Proof to Physical Schema

Once the rules:

~~~text
order_id            → customer_id
(order_id, line_no) → product_id, quantity
~~~

are confirmed by the business, we can implement:

~~~sql
CREATE TABLE customers (
    customer_id VARCHAR(30) PRIMARY KEY,
    customer_name VARCHAR(200) NOT NULL
);

CREATE TABLE products (
    product_id VARCHAR(30) PRIMARY KEY,
    product_name VARCHAR(200) NOT NULL
);

CREATE TABLE orders (
    order_id VARCHAR(30) PRIMARY KEY,
    customer_id VARCHAR(30) NOT NULL REFERENCES customers(customer_id)
);

CREATE TABLE order_items (
    order_id VARCHAR(30) NOT NULL REFERENCES orders(order_id),
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id VARCHAR(30) NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

At the logical level, decomposing `ORDER_LINE_FLAT` into `ORDERS` and `ORDER_ITEMS` is lossless under `order_id → customer_id`. In implementation:

- `orders.order_id` is the **primary key**, ensuring each order has one order header row.
- `order_items(order_id,line_no)` is the **composite primary key**, expressing unique line numbers within an order.
- The foreign key `order_items.order_id → orders.order_id` prevents creating line items for nonexistent orders.
- `quantity > 0` is a **domain constraint**, not derived from FDs.
- If fast lookup of orders per customer is needed, consider an index on `orders.customer_id` based on workload.

A join query to reconstruct the detail view:

~~~sql
SELECT
    o.order_id,
    o.customer_id,
    i.line_no,
    i.product_id,
    i.quantity
FROM orders AS o
JOIN order_items AS i
  ON i.order_id = o.order_id;
~~~

However, **independently existing child tables** enable new states absent from the old flat table, such as an order with no line items yet. The `INNER JOIN` above will not return that order. This **does not invalidate** the losslessness proof for projections of `ORDER_LINE_FLAT`: the lossless property concerns only **exact reconstruction of an original relation from projections of itself**. Practical design must decide whether empty orders are allowed and how independent entities are stored and queried.

### Lossless Decomposition Alone Does Not Guarantee Implementation Quality

You still need to:

- Confirm **identifier scope**: whether order IDs are globally unique or per store/tenant.
- Design rules for **changing customers, deleting orders, returns, and history** if applicable.
- Enforce **foreign keys, NOT NULL, UNIQUE, CHECK**, and transactions across multi-table writes.
- Measure `JOIN` cost and select appropriate indexes.
- If building summary tables / materialized views, establish refresh rules and avoid inconsistent sources.

**Losslessness is a correctness condition of the relational model; it does not by itself dictate performance or all business policies.**

## 13. Practical Method to Validate a Proposed Decomposition

A reliable workflow when turning business requirements into a design:

### Step 1 — Define Grain and Attribute Sets

State clearly whether each row of the original table is **an entity, a link, or an event**. Verify that all attributes of the original table appear in at least one child relation:

\[
\bigcup_i U_i=U.
\]

### Step 2 — Confirm Dependencies from the Business

Record FDs/MVDs/JDs along with their scope and effective time. **Do not** assume an identifier unique in a small sample is always a key. If a rule is unconfirmed, mark it as an assumption and ask the business owner.

### Step 3 — Check Each Binary Split

Compute intersection \(I=U_1\cap U_2\) and closure \(I_F^+\). If \(U_1\subseteq I_F^+\) or \(U_2\subseteq I_F^+\), that split step is lossless under FDs.

### Step 4 — For Multiple Tables, Prove the Full Join

Find a chain of lossless binary steps or use chase/JDs appropriately. Do not inspect isolated pairs of child tables while ignoring intermediate relations.

### Step 5 — Check Dependency Preservation and Normal Forms

Evaluate whether original FDs hold across child tables; check whether tables meet 3NF, BCNF, or 4NF according to the actual dependency types. Losslessness and dependency preservation are **two separate criteria**.

### Step 6 — Test Counterexamples and Physical Acceptance

Use SQL to search for spurious tuples in staging data; add tough cases such as multiple rows sharing join keys, multi-tenant data, historical data, missing links, `NULL`, and independent sources. Finally add keys, referential constraints, indexes, and update workflows.

## 14. Common Mistakes

| Mistake | Why it is wrong | How to fix |
|---|---|---|
| "Two tables share a column so joining will be accurate" | The shared column may not uniquely determine either side | Check `(R1∩R2) → R1` or `→ R2` under FDs |
| "With multiple tables, checking arbitrary pairs suffices" | The overall join can create spurious combinations at later steps | Prove a **decomposition chain** or use chase/JDs |
| "Running JOIN on sample data produced no spurious rows, so it's proved" | Sample data may omit valid business cases | Prove across **all valid states** |
| "Failing the FD criterion means definitely lossy" | MVDs/JDs can guarantee losslessness without a corresponding FD | Check the right **type of dependency** |
| "Lossless means preserving all dependencies" | Some FDs may still require cross-table verification | Verify dependency preservation separately |
| "Adding foreign keys is enough" | Foreign keys check referential existence, not that all join combinations are real tuples | Identify keys and business dependencies; evaluate spurious tuples |
| "Tables in BCNF/4NF automatically reconstruct data accurately" | Normal form of individual tables does not replace proving the decomposition | Check the lossless condition of the **split itself** |
| "INNER JOIN misses empty orders so the decomposition is lossy" | Post-implementation tables can hold new states absent from flat projections | Distinguish **losslessness of projections** from **semantics of storing independent entities** |

## 15. Choosing Among Relational, Document, Graph, and Analytical Models

| Model | Relation to accurate data reconstruction | What to check |
|---|---|---|
| **Relational** | Decompose into child tables and join by keys | FDs/MVDs/JDs, losslessness, dependency preservation, foreign keys |
| **Document** | Separate or embed attribute groups inside documents | Reference IDs, syncing embedded data, historical snapshots |
| **Graph** | Express objects and links as nodes/edges | Do not infer **ternary relationships** from three pairwise relationships alone |
| **Analytical** | Join fact–dimension and bridge tables at the proper grain | Avoid multiplying measures or fabricating combinations in many-to-many joins |

For example, in a graph model, having student–course and course–tutor edges **does not prove** that tutor coached that student. In an analytical model, joining an order fact with two many-to-many tables without aligning grain can multiply `SUM(revenue)` severalfold. The lesson of **accurately reconstructing data associations** remains vital even when storage mechanisms differ from classical relations.

## 16. Practice Exercises with Solutions

### Exercise 1 — Checking the Intersection Criterion

Given \(R(A,B,C,D)\) with \(F=\{A\rightarrow B,\ B\rightarrow C\}\). Is the decomposition `R1(A,B,C)`, `R2(A,D)` lossless under \(F\)?

**Solution:** The intersection is \(\{A\}\). From `A → B` and `B → C`, we derive \(\{A\}^+=\{A,B,C\}\), which determines all of `R1(A,B,C)`. Therefore, the decomposition is **lossless**.

### Exercise 2 — Lossy Decomposition

Given \(R(A,B,C)\), \(F=\varnothing\), and tuples `(a1,b1,c1)`, `(a2,b1,c2)`. Split into `R1(A,B)` and `R2(B,C)`. Which tuples does the join create that are not in \(R\)?

**Solution:** The two spurious tuples are `(a1,b1,c2)` and `(a2,b1,c1)`. The intersection \(\{B\}\) determines neither `A` nor `C`; the decomposition is **not lossless**.

### Exercise 3 — Three-Table Decomposition Chain

Given \(R(A,B,C,D)\), \(F=\{A\rightarrow B,\ B\rightarrow C,\ C\rightarrow D\}\). Prove `{AB,BC,CD}` is a lossless decomposition.

**Solution:** Split `ABCD` into `ABC` and `CD`: intersection `C`, `C→D`, so lossless. Further split `ABC` into `AB` and `BC`: intersection `B`, `B→C`, so lossless. Combining both steps proves the final decomposition is **lossless**.

### Exercise 4 — Can It Be Lossless When FDs Are Insufficient?

Relation `R(employee_id,skill,language)` stores two independent lists. An employee has multiple skills and languages, with neither `employee_id → skill` nor `employee_id → language`. Is splitting into `(employee_id,skill)` and `(employee_id,language)` lossless?

**Solution:** Yes, **if** the business genuinely guarantees `employee_id ↠ skill`, because that MVD corresponds to a two-projection JD. The binary **FD** criterion does not apply to refute this decomposition. If skills and languages are actually paired per occurrence, splitting will produce spurious tuples.

### Exercise 5 — Lossless Differs from Dependency Preservation

Given \(R(A,B,C)\), \(F=\{AB\rightarrow C,\ C\rightarrow B\}\). Split into `R1(C,B)`, `R2(A,C)`.

**Solution:** Intersection \(\{C\}\) determines `R1(C,B)`, so it is **lossless**. However, `AB→C` is not preserved by local FDs: the two child tables can allow the same `AB` pair to match two different `C` values.

### Exercise 6 — Key Missing Scope

In a multi-store platform, order number `order_no` is unique only **within each store**. Should we split `ORDER_LINE(store_id,order_no,line_no,customer_id,product_id)` into an order table with `order_no,customer_id` and a line table with `order_no,line_no,product_id`, then join on `order_no`?

**Solution:** No, because two stores can reuse the same `order_no` for different customers and products, causing erroneous joins. You must establish a scoped key, such as `(store_id,order_no)`, and include **that same key** in both child tables and the join condition.

### Exercise 7 — An Order with No Line Items Yet

After splitting `ORDERS` and `ORDER_ITEMS`, order `DH99` is created with no line items yet. An `INNER JOIN` query does not return this order. Can we conclude the decomposition failed losslessness?

**Solution:** No such conclusion can be drawn. **Losslessness** is defined on projections from **the same original relation**. An order with no line items is an additional state that the two-entity design allows representing. If the business needs to view empty orders, query `ORDERS` directly or use `LEFT JOIN`. If the business **forbids** empty orders, enforce a corresponding control rule.

## 17. Checklist Before Finalizing a Decomposition

- [ ] Identified the grain and business meaning of each row.
- [ ] Child relations cover all original attributes.
- [ ] Confirmed FDs/MVDs/JDs along with identifier scope and effective time.
- [ ] For two tables under FDs, computed intersection and closure to test the lossless criterion.
- [ ] For multiple tables, proved a **lossless chain** or applied chase/JDs appropriately.
- [ ] Tested counterexamples with multiple rows sharing join keys to catch spurious tuples.
- [ ] Checked **dependency preservation** separately from lossless join.
- [ ] Distinguished projecting a single relation from storing two independent tables post-implementation.
- [ ] Reviewed `NULL`, duplicates, foreign keys, and update transactions.
- [ ] Evaluated join cost, indexes, schema evolution, and actual workload.

**Takeaway:** A decomposition is **lossless-join** when every valid data state is **reconstructed exactly by joining its projections**, without generating spurious tuples. For two tables under FDs, check whether **the attribute intersection determines one child table**. For multivalued dependencies, join dependencies, and multiple tables, apply the corresponding reasoning. Proving **losslessness** is mandatory before locking in a data structure, and **dependency preservation** must be evaluated separately.
