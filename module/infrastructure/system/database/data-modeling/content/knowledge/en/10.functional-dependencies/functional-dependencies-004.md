# Minimal Cover and Its Role in Schema Decomposition

## Learning Objectives

In the **DATABASE_DATA_MODELING** module, the goal is not only to draw entities and relationships, but also to turn business rules into verifiable **keys, constraints, tables, and physical schemas**. A **minimal cover** (often called a *canonical cover*, with minor presentation differences) simplifies a set of functional dependencies while preserving everything the data must enforce. It is especially useful when analyzing normalization and synthesizing a Third Normal Form (3NF) schema.

After this lesson, you will be able to:

- Explain **equivalence of two sets of functional dependencies** and the definition of a minimal cover.
- Compute attribute closure to detect **extraneous left-hand attributes**, **redundant right-hand attributes**, and **redundant functional dependencies**.
- Construct a minimal cover step by step, then prove that the result is **equivalent** to the input.
- Use a minimal cover in the **3NF schema synthesis algorithm**.
- Distinguish the two criteria that must be checked during decomposition: **lossless join** and **dependency preservation**; understand the common trade-off with BCNF.

## 1. Context: Multiple Dependencies Can State the Same Fact

Consider the relation:

\[
R(A,B,C,D,E)
\]

with functional dependency set \(F\):

~~~text
F = {
    A  → BC,
    B  → C,
    AC → D,
    D  → E,
    A  → E
}
~~~

The notation `A → BC` means each `A` value determines both `B` and `C` together; `AC → D` means the **pair** `(A,C)` determines `D`.

In the set above, some facts are already guaranteed by other rules:

- `A → C` already follows from `A → B` and `B → C`.
- In `AC → D`, `C` is not actually needed on the left-hand side, because from `A` we derive `C`, and then use `AC → D` to derive `D`.
- `A → E` can be derived via `A → D` and `D → E` after the reduction step above.

Thus we can express the exact same constraints with a more compact set:

~~~text
G = {
    A → B,
    B → C,
    A → D,
    D → E
}
~~~

**Key question:** How do we know \(G\) preserves all rules in \(F\), rather than accidentally deleting a business constraint? We must use the definition of equivalence and closure computation, not intuition alone.

## 2. Foundations: Implied Dependencies, Closure, and Equivalence

Given a relation schema \(R(U)\), a dependency \(X\rightarrow Y\) holds when in **every valid data state**, two rows agreeing on attribute set \(X\) must agree on attribute set \(Y\).

The set \(F^+\) is **all functional dependencies derivable from \(F\)** via Armstrong's rules. The closure \(X_F^+\) is **the set of attributes derivable from \(X\)** based on \(F\):

\[
X_F^+=\{A\in U\mid F\models X\rightarrow A\}.
\]

To check whether \(F\models X\rightarrow Y\), simply check:

\[
Y\subseteq X_F^+.
\]

### Attribute Closure Algorithm

~~~text
ATTRIBUTE_CLOSURE(X, F):
    result := X
    repeat:
        previous := result
        for each dependency L → T in F:
            if L ⊆ result:
                result := result ∪ T
    until result = previous
    return result
~~~

The algorithm continuously adds attributes, never removes any, and stops when no more changes occur. Since the attribute set is finite, it always terminates.

### Equivalence of Two Dependency Sets

Two sets \(F\) and \(G\) are **equivalent** when:

\[
F^+=G^+.
\]

Equivalence also means: every dependency in \(F\) is derivable from \(G\), **and conversely** every dependency in \(G\) is derivable from \(F\).

To verify this without enumerating \(F^+\) or \(G^+\):

1. For each \(X\rightarrow Y\) in \(F\), verify \(Y\subseteq X_G^+\).
2. For each \(X\rightarrow Y\) in \(G\), verify \(Y\subseteq X_F^+\).
3. Only when **both directions** hold do we conclude \(F^+=G^+\).

Checking only one direction can cause you to **drop a dependency** or **introduce a constraint stronger than the business rule** without noticing.

## 3. What Is a Minimal Cover?

A **minimal cover** is commonly defined as a dependency set \(G\) satisfying these conditions:

1. **Equivalence:** \(G^+=F^+\).
2. **Singleton right-hand sides:** every dependency in \(G\) has the form \(X\rightarrow A\), where \(A\) is a **single attribute**.
3. **No extraneous attributes on the left-hand side:** no attribute can be removed from the left-hand side of any dependency while preserving equivalence.
4. **No redundant dependencies:** no entire dependency can be deleted from \(G\) while preserving equivalence.

Some textbooks call the form where **dependencies sharing the same left-hand side are merged** a *canonical cover*; others use the two terms interchangeably. When discussing or writing exams, state clearly whether the convention requires **single-attribute right-hand sides or allows merging**. Merging `A → B` and `A → D` into `A → BD` does not change dependency semantics.

**"Minimal"** here means minimal with respect to the redundancy-elimination steps just described. It does **not** necessarily mean the representation with the fewest characters or fewest lines. A dependency set can have **multiple different minimal covers** that are all equivalent.

## 4. Three Reduction Operations and How to Verify Them

### 4.1. Splitting Right-Hand Sides

By the decomposition rule for functional dependencies:

\[
X\rightarrow YZ \iff
(X\rightarrow Y)\land(X\rightarrow Z).
\]

Therefore:

~~~text
A → BC
~~~

is replaced by:

~~~text
A → B
A → C
~~~

This is a **representation normalization** step; no business content is removed yet.

### 4.2. Detecting Extraneous Attributes on the Left-Hand Side

For a dependency \(XA\rightarrow B\), attribute \(A\) is **extraneous on the left-hand side** if the remaining part \(X\) alone also derives \(B\):

\[
B\in X_F^+.
\]

In that case, `XA → B` can be replaced by `X → B` while preserving equivalence.

For example, with `AC → D` in \(F\), to check if `C` is extraneous, compute `{A}+` using the current dependency set:

~~~text
Start:          {A}
By A → B:       {A, B}
By B → C:       {A, B, C}
By AC → D:      {A, B, C, D}
By D → E:       {A, B, C, D, E}
~~~

Since `D ∈ {A}+`, we have `A → D`. Thus `C` is extraneous in `AC → D`.

**Do not confuse this with checking whether an entire dependency is redundant.** Here we test whether we can **drop one attribute from the left-hand side**, not whether we can delete **the entire dependency**. Closure is computed over the **current set** that still contains the dependency being simplified. When replacing `AC → D` with `A → D`, the reverse direction `A → D ⇒ AC → D` holds by Armstrong's augmentation axiom.

### 4.3. Removing Redundant Functional Dependencies

For a dependency \(f=(X\rightarrow A)\) in \(G\), \(f\) may be removed only if:

\[
A\in X_{G-\{f\}}^+.
\]

That is, **remove the dependency being tested completely**, and compute closure using only the **remaining** dependencies.

For example, with:

~~~text
G = {
    A → B,
    B → C,
    A → D,
    D → E,
    A → E
}
~~~

Test `A → E`: remove `A → E` from the set; `A → D → E` is still derivable, so `A → E` is **redundant** and can be deleted.

If you compute `{A}+` **while still keeping** `A → E` when testing that very dependency, finding `E` is circular and proves nothing. This is a very common mistake when computing minimal covers.

## 5. Complete Minimal Cover Example

Returning to:

~~~text
F = {
    A  → BC,
    B  → C,
    AC → D,
    D  → E,
    A  → E
}
~~~

### Step 1 — Split Right-Hand Sides into Single Attributes

~~~text
F1 = {
    A  → B,
    A  → C,
    B  → C,
    AC → D,
    D  → E,
    A  → E
}
~~~

### Step 2 — Reduce Left-Hand Sides

`AC → D` has a composite left-hand side. Try dropping `C`:

- From `A`, derive `B` via `A → B`.
- From `B`, derive `C` via `B → C`.
- With `A,C` present, derive `D` via `AC → D`.

Thus `D ∈ {A}+`, so replace `AC → D` with `A → D`:

~~~text
F2 = {
    A → B,
    A → C,
    B → C,
    A → D,
    D → E,
    A → E
}
~~~

### Step 3 — Remove Redundant Dependencies One by One

Test `A → C`: if removed, `A → B` and `B → C` still imply `A → C`. Delete it.

Test `A → E`: if removed, `A → D` and `D → E` still imply `A → E`. Delete it.

Result:

~~~text
G = {
    A → B,
    B → C,
    A → D,
    D → E
}
~~~

No dependency in \(G\) can be deleted while still being derivable from the other three dependencies. All left-hand sides consist of a single attribute with no extraneous attributes (under the given rules, there are no dependencies from the empty set to the right-hand attributes).

### Step 4 — Prove Equivalence Between \(F\) and \(G\)

**Direction \(G\models F\):** using set \(G\), check all original dependencies:

| Dependency in \(F\) | How it is derived from \(G\) |
|---|---|
| `A → BC` | `A → B`; then `B → C`; combine to get `A → BC` |
| `B → C` | Already present |
| `AC → D` | `A → D`; adding `C` to the left-hand side preserves the dependency |
| `D → E` | Already present |
| `A → E` | `A → D → E` |

**Direction \(F\models G\):**

| Dependency in \(G\) | How it is derived from \(F\) |
|---|---|
| `A → B` | Decomposed from `A → BC` |
| `B → C` | Already present |
| `A → D` | `A → C` from `A → BC`; combine with `AC → D` |
| `D → E` | Already present |

Since derivation holds in **both directions**, \(F^+=G^+\). That is what must be preserved when moving from a business description to a more compact constraint set.

## 6. Algorithm for Finding a Minimal Cover

An easy-to-verify implementation:

~~~text
MINIMAL_COVER(F):
    G := split_every_rhs_into_single_attributes(F)

    # Reduce left-hand sides; replace each dependency with its reduced form.
    for each dependency (X → A) in G:
        for each attribute b in X:
            if A ∈ ATTRIBUTE_CLOSURE(X - {b}, G):
                replace (X → A) in G with ((X - {b}) → A)
                X := X - {b}

    # Remove redundant dependencies; can repeat until stable.
    for each dependency f = (X → A) in a copy of G:
        if A ∈ ATTRIBUTE_CLOSURE(X, G - {f}):
            remove f from G

    return G
~~~

**Application notes:**

- After each reduction or deletion, compute closure using the **most recent set \(G\)**.
- In the left-hand side check, you may use the set currently containing the dependency; in the step that **deletes an entire dependency**, you must use `G - {f}`.
- A reduction can affect whether other attributes are extraneous; a general implementation should keep scanning until no changes occur and verify final equivalence.
- If a left-hand side becomes the **empty set**, the dependency \(\varnothing\rightarrow A\) means \(A\) has the same value in every valid row. That is a formally valid edge case; do not discard it automatically just because it looks unusual.
- The resulting cover can vary depending on the order in which dependencies are processed, but any valid minimal cover must be **equivalent** to \(F\).

For models with many attributes and dependencies, closure computation is much easier to automate than enumerating all of \(F^+\). However, **a minimal cover does not validate the correctness of the input rules**: if \(F\) came from a wrong assumption, the equivalent output still reflects that very mistake.

## 7. Role of a Minimal Cover in Schema Decomposition

A combined table can hold information at multiple levels: order details, customer details, product details, and individual line items. Functional dependencies tell us which attributes belong together with an identifying key; normalization uses that information to reduce **update, insertion, and deletion anomalies**.

A minimal cover helps in three ways:

1. **Clarifying which dependencies actually need representation:** avoids handling rules that are merely consequences of other rules multiple times.
2. **Guiding attribute grouping by shared left-hand sides:** for instance, `A → B` and `A → D` can be grouped into `A → BD` to form a relation containing `A,B,D`.
3. **Driving the 3NF synthesis algorithm:** builds relations from the minimal cover, then ensures lossless join and dependency preservation.

However, distinguish carefully: **reducing a dependency set** is a logical operation on \(F\); **decomposing a schema** is an operation on the column set \(U\). A more compact dependency set **does not automatically** yield a valid set of tables. You must verify the properties of the decomposition.

## 8. Two Mandatory Criteria: Lossless Join and Dependency Preservation

### 8.1. Lossless-Join Decomposition

Suppose \(R(U)\) is decomposed into schemas \(R_1,\ldots,R_n\). A decomposition has a **lossless join with respect to \(F\)** if for **every valid relation \(r\) satisfying \(F\)**:

\[
r = \Join_{i=1}^{n}\pi_{R_i}(r).
\]

In other words, when projecting the original table onto the child tables and taking their **natural join**, we recover the exact rows of the original table; no spurious rows appear from accidental matching.

For a **binary** decomposition \(R\to R_1,R_2\), a necessary and sufficient condition in terms of functional dependencies is that at least one of the following two dependencies is implied by \(F\):

\[
(R_1\cap R_2)\rightarrow R_1
\qquad\text{or}\qquad
(R_1\cap R_2)\rightarrow R_2.
\]

For example, with \(R(A,B,C)\), \(F=\{A\rightarrow B\}\), decomposing into \(R_1(A,B)\) and \(R_2(A,C)\) is **lossless** because the intersection of the two column sets is \(\{A\}\), and `A → AB` follows from `A → B`.

An easy counterexample: with \(R(A,B,C)\), no non-trivial dependencies, and the data:

| A | B | C |
|---|---|---|
| a1 | b1 | c1 |
| a2 | b1 | c2 |

If split into \(R_1(A,B)\) and \(R_2(B,C)\), and then joined on `B`, we also get `(a1,b1,c2)` and `(a2,b1,c1)` **which were not in the original data**. This is a **lossy decomposition**; the input data was not necessarily deleted, but the split lost information about which values belonged together.

### 8.2. Dependency Preservation

For sub-relations \(R_i\), let \(\pi_{R_i}(F)\) denote **the set of dependencies in \(F^+\) all of whose attributes lie within \(R_i\)**.

A decomposition is **dependency-preserving** when:

\[
\left(\bigcup_i\pi_{R_i}(F)\right)^+=F^+.
\]

Practical meaning: all original dependencies can be inferred from rules enforced **individually within each sub-relation**, without needing to join all tables to detect violations.

These two criteria are **distinct**:

| Criterion | Question answered | If not satisfied |
|---|---|---|
| **Lossless join** | Does projecting and joining recover the exact data? | Spurious rows can be generated upon joining |
| **Dependency preservation** | Can the original functional rules be checked through the sub-relations? | Some dependencies require cross-table checks or checks during joins |

Do not equate **theoretical dependency preservation** with being able to enforce every dependency in a DBMS using only `PRIMARY KEY` and `FOREIGN KEY`. Some dependencies require proper table layout, extra constraints, or dedicated validation logic.

## 9. Synthesizing a 3NF Schema from a Minimal Cover

The **3NF synthesis algorithm** typically proceeds as follows:

1. Find a **minimal cover** \(G\) of \(F\), with single-attribute right-hand sides.
2. For each left-hand side \(X\), create relation \(R_X\) containing \(X\) and all attributes \(A\) such that \(X\rightarrow A\) is in \(G\). Group dependencies **sharing the same left-hand side** to avoid creating unnecessary tables.
3. Any sub-relation whose attribute set is completely contained within another sub-relation may be dropped, per the standard algorithm.
4. If **no sub-relation contains a candidate key of the original schema**, add a relation consisting solely of the attributes of one candidate key.

When carried out properly, the algorithm yields a decomposition that **achieves 3NF, preserves dependencies, and has a lossless join**. The step of adding a candidate-key relation is essential for guaranteeing a lossless join.

### Applying to the Example \(R(A,B,C,D,E)\)

The minimal cover already found is:

~~~text
G = {
    A → B,
    B → C,
    A → D,
    D → E
}
~~~

Group by left-hand side:

| Dependency group | Created relation | Key of sub-relation from kept dependencies |
|---|---|---|
| `A → B`, `A → D` | \(R_1(A,B,D)\) | `A` |
| `B → C` | \(R_2(B,C)\) | `B` |
| `D → E` | \(R_3(D,E)\) | `D` |

In the original relation, we have:

~~~text
{A}+ = {A, B, C, D, E}
~~~

Because `A` **does not appear on any right-hand side** and the closure of `A` is all of \(U\), `A` is a candidate key of \(R\). Relation \(R_1(A,B,D)\) already contains `A`, so no separate key relation needs to be added.

**Dependency preservation:** every dependency in \(G\) lies wholly within one of the three relations:

~~~text
R1(A,B,D): A → B, A → D
R2(B,C):   B → C
R3(D,E):   D → E
~~~

Since \(G^+=F^+\), the original dependencies are preserved in terms of inference.

**Lossless join:** joining \(R_1(A,B,D)\) with \(R_2(B,C)\) on `B` is lossless, because `B → C` and the intersection is `B`. Joining next with \(R_3(D,E)\) on `D` is also lossless, because `D → E`. Therefore, from the three projections we can reconstruct the original relation under the given rules.

**3NF:** each sub-relation is built around a left-hand side that determines the remaining attributes, and in this example that left-hand side is the key of the sub-relation itself; hence all three relations also satisfy **BCNF**. This is a property of **this specific example**, not a general guarantee that 3NF synthesis always produces BCNF.

### When a Key-Holding Table Must Be Added

Consider \(R(A,B,C)\) with \(F=\{A\rightarrow B\}\). The minimal cover is \(F\) itself. If we only create \(R_1(A,B)\), attribute **\(C\) would be omitted**.

The candidate key of the original relation is \(\{A,C\}\), because:

~~~text
{A,C}+ = {A,B,C}
{A}+   = {A,B}
{C}+   = {C}
~~~

We must add \(R_2(A,C)\). The decomposition \(R_1(A,B),R_2(A,C)\) is lossless because `A → AB`; `A → B` is also preserved in \(R_1\).

This is why **you must never skip checking for a relation containing a candidate key**, even when all dependencies in the minimal cover already have a home.

## 10. Why BCNF Can Trade Off Dependency Preservation

**BCNF** requires the left-hand side of **every non-trivial functional dependency** \(X\rightarrow Y\) to be a superkey. This condition is stronger than 3NF, yet some BCNF decompositions **do not preserve all dependencies**.

Consider the relation:

~~~text
ASSIGNMENT(student_id, course_id, instructor_id)
~~~

Suppose:

- Each `(student_id, course_id)` pair is assigned **one** instructor.
- Each instructor teaches only **one course**, though they may teach many students.

We have:

~~~text
F = {
    (student_id, course_id) → instructor_id,
    instructor_id           → course_id
}
~~~

Both `(student_id, course_id)` and `(student_id, instructor_id)` are candidate keys. Because `course_id` belongs to the first candidate key, the dependency `instructor_id → course_id` has a prime attribute on the right-hand side, so the table **satisfies 3NF**. However, `instructor_id` is not a superkey, so the table **violates BCNF**.

A BCNF decomposition:

~~~text
INSTRUCTOR_COURSE(instructor_id, course_id)
STUDENT_INSTRUCTOR(student_id, instructor_id)
~~~

This decomposition has a **lossless join**, because the intersection of the two tables is `instructor_id` and `instructor_id → course_id` determines all of `INSTRUCTOR_COURSE`.

However, the dependency:

~~~text
(student_id, course_id) → instructor_id
~~~

**is not preserved by dependencies restricted to individual sub-tables**. Both tables can be individually valid yet yield a student having two different instructors teaching the same course when joined. To enforce "one instructor per student-course", the system may need cross-table checks or another design solution.

| Goal | 3NF synthesis | BCNF decomposition |
|---|---|---|
| Reduce FD-driven redundancy | Yes, achieves 3NF | Stronger, achieves BCNF |
| Lossless join | Yes with standard algorithm | Achievable with standard decomposition algorithm |
| Preserve all functional dependencies | Guaranteed with standard synthesis algorithm | **Not always guaranteed** |

Whether to prioritize 3NF or BCNF depends on **which rules must be enforced**, acceptable redundancy, and operational cost. Do not pick a higher normal form by name alone.

## 11. Translating Results into a Business Model and Physical Schema

Suppose a sales system starts from the combined table:

~~~text
ORDER_LINE_FLAT(
    order_id, line_no, order_date,
    customer_id, customer_name,
    product_id, product_name,
    quantity, unit_price_at_sale
)
~~~

With the rules:

~~~text
order_id             → order_date, customer_id
customer_id          → customer_name
product_id           → product_name
(order_id, line_no)  → product_id, quantity, unit_price_at_sale
~~~

Splitting the right-hand sides gives a minimal cover representation; with no additional rules, the left-hand sides in the rule set above contain no extraneous attributes, and no dependency in the split version is wholly derivable from the remaining ones.

Synthesizing by dependency groups produces four schemas:

~~~text
ORDERS(order_id, order_date, customer_id)
CUSTOMERS(customer_id, customer_name)
PRODUCTS(product_id, product_name)
ORDER_ITEMS(order_id, line_no, product_id, quantity, unit_price_at_sale)
~~~

The candidate key of the original relation is `(order_id, line_no)`; `ORDER_ITEMS` contains this entire key. Every rule in the minimal cover belongs to a corresponding table. The new tables store information at the right **grain**: order, customer, product, or line item.

Example DDL consistent with the assumption that customer and product names are **current values**:

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
    order_date DATE NOT NULL,
    customer_id VARCHAR(30) NOT NULL REFERENCES customers(customer_id)
);

CREATE TABLE order_items (
    order_id VARCHAR(30) NOT NULL REFERENCES orders(order_id),
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id VARCHAR(30) NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_at_sale DECIMAL(12,2) NOT NULL
        CHECK (unit_price_at_sale >= 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

**Do not** place `UNIQUE(order_id, product_id)` if business rules allow the same product to appear on two lines in one order. **Do not** move `unit_price_at_sale` into `products` if the same product is sold at different prices. Functional dependencies help **identify grain and keys**; **foreign key, value domain, mandatory, and change-history** constraints still need to be designed separately.

In a **document** model, line items can be embedded in the order document to read an entire order at once, but you must clearly distinguish which embedded fields are **historical snapshots** and which must be kept updated from current sources. In a **graph** model, entity identity and relationship constraints are needed on nodes/edges. In an **analytical** model, fact grain and dimension versioning determine which dependencies remain valid. Minimal cover is a formal tool for **relational schemas**, while the mindset of eliminating redundant constraints and checking consistency helps compare modeling approaches.

## 12. Common Mistakes

| Mistake | Consequence | How to fix |
|---|---|---|
| Deleting `X → A` after computing `X+` while that very dependency is still in the set | Falsely concludes every dependency is redundant | Compute closure using **the set with the tested dependency removed** |
| Only splitting right-hand sides and calling it a minimal cover | Extraneous left-hand attributes and redundant dependencies remain | Reduce left-hand sides, remove redundant dependencies, verify equivalence |
| Proving only that the new set implies the old set | May have added constraints stronger than the business rules | Prove **both directions** \(F\models G\) and \(G\models F\) |
| Expecting the minimal cover to be unique | Overlooks multiple valid answers | Check attributes, redundancy, and equivalence rather than exact textual match |
| Creating tables from all dependencies while forgetting a candidate-key table | May lose attributes or fail lossless join | Execute the full 3NF synthesis algorithm |
| Thinking lossless equals dependency-preserving | Can join cleanly yet lose the ability to check dependencies locally | Verify each criterion independently |
| Always converting to BCNF without checking business needs | May require cross-table dependency enforcement | Weigh dependency preservation against operational cost |
| Inferring dependencies from existing data without asking business owners | Model breaks when new data arrives | Confirm identifier scope, exceptions, and changes over time |

## 13. Practice Exercises with Solutions

### Exercise 1 — Compute a Minimal Cover

Given \(R(A,B,C,D)\):

~~~text
F = { A → BC, B → C, AC → D, A → D }
~~~

**Task:** Find a minimal cover.

**Solution:** Split `A → BC` into `A → B` and `A → C`. Because `A → B` and `B → C`, `A → C` is redundant. `AC → D` is redundant because `A → D` is already present (or by recognizing `C` is extraneous on the left-hand side). Result:

~~~text
G = { A → B, B → C, A → D }
~~~

\(G\) is equivalent to \(F\) and has no remaining redundant dependencies under the given rules.

### Exercise 2 — Why Must the Redundancy Test Remove the Dependency?

Given \(F=\{A\rightarrow B,\ B\rightarrow C\}\). Can `A → B` be deleted?

**Solution:** No. Computing `{A}+` under **`F - {A → B}`** yields only `{A}`. Attribute `B` is not in this closure, so `A → B` is not redundant. Keeping `A → B` itself during the test renders the result meaningless.

### Exercise 3 — Adding a Candidate-Key Table in 3NF Synthesis

Given \(R(A,B,C,D)\), \(F=\{A\rightarrow B,\ C\rightarrow D\}\).

**Task:** Identify the candidate key and the tables produced by 3NF synthesis.

**Solution:** `A` and `C` do not appear on any right-hand side, so every key must contain both. `{A,C}+=\{A,B,C,D\}`, so the candidate key is `{A,C}`. Create `R1(A,B)` and `R2(C,D)` from the minimal cover, but neither table contains the key `AC`; add `R3(A,C)`. The decomposition then preserves the original dependencies and has a lossless join.

### Exercise 4 — Recognizing Lossless Join and Dependency Preservation

Given \(R(A,B,C)\), \(F=\{A\rightarrow B\}\). Decompose into `R1(A,B)` and `R2(A,C)`. Is it lossless? Is it dependency-preserving?

**Solution:** It is **lossless** because the intersection `{A}` determines `R1(A,B)`. It is **dependency-preserving** because `A → B` can be checked directly inside `R1`.

### Exercise 5 — Which Dependency Is Lost in BCNF Decomposition?

With `ASSIGNMENT(student_id, course_id, instructor_id)` and:

~~~text
(student_id, course_id) → instructor_id
instructor_id           → course_id
~~~

Decompose into `INSTRUCTOR_COURSE(instructor_id,course_id)` and `STUDENT_INSTRUCTOR(student_id,instructor_id)`.

**Solution:** The decomposition is **lossless** thanks to `instructor_id → course_id`. The dependency `(student_id, course_id) → instructor_id` **is not preserved on individual sub-tables**: neither table contains all of `student_id,course_id,instructor_id`, and the projected dependencies do not imply this rule. You must weigh keeping 3NF or implementing cross-table business validation.

## 14. Checklist Before Finalizing Decomposition

- [ ] Confirmed initial dependencies using **business rules**, not just sample data.
- [ ] Split right-hand sides, checked extraneous left-hand attributes, and removed redundant dependencies.
- [ ] Verified **two-way equivalence** between the reduced set and the original set.
- [ ] Identified candidate keys via closure computation.
- [ ] During 3NF synthesis, grouped dependencies with the same left-hand side and verified a relation contains a **candidate key of the original relation**.
- [ ] Verified **lossless join** and **dependency preservation** of the decomposition.
- [ ] If choosing BCNF, evaluated dependencies that can no longer be checked within individual tables alone.
- [ ] Mapped keys and relationships to `PRIMARY KEY`, `UNIQUE`, `FOREIGN KEY`; added `NOT NULL`, `CHECK` as required.
- [ ] Clarified current data, historical data, identifier scope, and the grain of each table.

**Takeaway:** A minimal cover is a **logically equivalent compact representation** of a set of functional dependencies, not a new set of business rules. Use it to synthesize and check schemas systematically; a good decomposition must preserve **data upon joining** and, where needed, preserve **the ability to enforce dependencies**.
