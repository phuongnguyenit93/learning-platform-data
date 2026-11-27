# Attribute Closure and Identifying Candidate Keys

## Learning Objectives

In **DATABASE_DATA_MODELING**, turning business requirements into a trustworthy data model requires determining **which set of attributes suffices to identify a record**. Computing **attribute closure** answers that question by reasoning from functional dependencies, rather than guessing keys from column names or a few sample rows.

After this lesson, you will be able to:

- Explain \(X^+\) under a set of functional dependencies \(F\) and compute closures using a fixed-point iterative algorithm.
- Test whether a functional dependency is implied by \(F\).
- Distinguish **superkeys**, **candidate keys**, **primary keys**, and **alternate keys**.
- Find and prove **all candidate keys** of a small relation, even when multiple keys exist.
- Apply the results to SQL constraints, normalization, key selection, and evolvable schema design.

## 1. Why Do We Need Attribute Closure?

Suppose a sales system stores reporting export data at the line-item level:

~~~text
ORDER_LINE_FLAT(
    order_id, line_no, order_date,
    customer_id, customer_name,
    product_id, product_name,
    quantity, unit_price_at_sale
)
~~~

Each record represents **one line item in one order**. From the confirmed business rules:

1. An `order_id` determines exactly one order date and one customer.
2. `line_no` is unique only **within a single order**; the pair `(order_id, line_no)` determines the product, quantity, and unit price of the line item.
3. Each `customer_id` determines one current customer name; each `product_id` determines one current product name.
4. A customer can place multiple orders; an order has multiple lines; a product can be sold multiple times at different prices.

We have the set of functional dependencies \(F\):

~~~text
F1: order_id             → order_date, customer_id
F2: customer_id          → customer_name
F3: product_id           → product_name
F4: (order_id, line_no)  → product_id, quantity, unit_price_at_sale
~~~

**Question:** Does `(order_id, line_no)` determine *all* columns of the table? Can `order_id` or `line_no` be dropped from the key? If another key exists, how do we find it?

Computing attribute closure provides a verifiable answer.

## 2. Definition of \(X^+\) and Its Relationship to Dependency Inference

Consider a relation schema \(R(U)\), where \(U\) is the set of attributes, and a set of functional dependencies \(F\) confirmed to hold in every valid state of the relation.

**The closure of an attribute set \(X\) under \(F\)**, denoted \(X_F^+\) or simply \(X^+\), is **the set of all attributes that can be determined from \(X\)** using the dependencies in \(F\) and valid inference rules:

\[
X_F^+ = \{ A \in U \mid F \models X \rightarrow A \}.
\]

Here \(F \models X\rightarrow A\) means: in every data state satisfying \(F\), the dependency \(X\rightarrow A\) holds.

Two important properties:

1. **Reflexivity:** \(X\subseteq X^+\). The closure always contains the initial attributes.
2. **Dependency membership test:** \(F\models X\rightarrow Y\) **if and only if** \(Y\subseteq X^+\).

For example, if `order_id → customer_id` and `customer_id → customer_name`, then `customer_name` is in `{order_id}+`. Hence we infer `order_id → customer_name` via **transitivity**, even though this rule is not written explicitly in \(F\).

### Closure \(X^+\) vs. Closure \(F^+\)

| Notation | Meaning | Output |
|---|---|---|
| \(X_F^+\) | Closure of **an attribute set \(X\)** under \(F\) | A **set of attributes** |
| \(F^+\) | Closure of **the dependency set \(F\)** | All **functional dependencies** implied by \(F\) |

We usually **do not need to enumerate all of \(F^+\)** because the number of implied dependencies can be huge. To test a single dependency \(X\rightarrow Y\), we only need to compute \(X^+\) and check whether \(Y\) is contained in it.

## 3. Fixed-Point Algorithm for Computing Closure

The standard method starts with \(X\) and repeatedly adds the right-hand side of any dependency whose left-hand side is already contained in the result set:

~~~text
ATTRIBUTE_CLOSURE(X, F):
    closure := copy(X)

    repeat:
        changed := false

        for each dependency (L → R) in F:
            if L ⊆ closure and R ⊈ closure:
                closure := closure ∪ R
                changed := true

    until changed = false

    return closure
~~~

All operations here are **set operations**: subset check (\(\subseteq\)), union (\(\cup\)), and equality comparison. No fixed traversal order over the dependencies is required to obtain the right result.

Because `closure` **only grows** and cannot exceed \(|U|\) attributes, the algorithm is guaranteed to terminate. When no dependency can add any new attribute, we have reached a **fixed point**. The algorithm produces the exact set of attributes derivable from \(X\) under Armstrong's axioms.

With a straightforward implementation, each pass over \(F\) adds at least one new attribute unless it terminates; thus the number of attribute-adding iterations does not exceed \(|U|-|X|\). Actual cost depends on how sets are represented and how many dependencies are checked. There is no need to generate all dependencies in \(F^+\).

### Step-by-Step Closure on the Order Example

Take:

\[
X=\{\text{order_id},\text{line_no}\}.
\]

| Step | Rule applied | Newly added attributes |
|---|---|---|
| Initialize | Start from \(X\) | `order_id, line_no` |
| 1 | F1: `order_id → order_date, customer_id` | `order_date, customer_id` |
| 2 | F4: `(order_id, line_no) → product_id, quantity, unit_price_at_sale` | `product_id, quantity, unit_price_at_sale` |
| 3 | F2: `customer_id → customer_name` | `customer_name` |
| 4 | F3: `product_id → product_name` | `product_name` |
| Done | No new attributes | Closure reaches fixed point |

We obtain:

~~~text
{order_id, line_no}+ =
{
    order_id, line_no, order_date,
    customer_id, customer_name,
    product_id, product_name,
    quantity, unit_price_at_sale
}
~~~

That is **all nine attributes** of `ORDER_LINE_FLAT`. Hence the pair `(order_id, line_no)` determines every attribute of the relation.

Try smaller sets:

~~~text
{order_id}+ =
    {order_id, order_date, customer_id, customer_name}

{line_no}+ =
    {line_no}
~~~

Neither set covers \(U\). Therefore, neither `order_id` nor `line_no` can be dropped from the pair while still determining all columns.

## 4. From Closure to Superkeys and Candidate Keys

### Superkey

An attribute set \(K\subseteq U\) is a **superkey** of \(R(U)\) under \(F\) if:

\[
K^+=U.
\]

That is, from the values of \(K\) we can determine every attribute of a row. If `(order_id, line_no)` is a superkey, then `(order_id, line_no, product_id)` is also a superkey: adding attributes never destroys the ability to determine the rest.

### Candidate Key

A **candidate key** is a superkey that is **minimal under set inclusion**:

\[
K^+=U
\quad\text{and}\quad
\forall K'\subset K:\ (K')^+\ne U.
\]

In other words, **no attribute can be removed from \(K\)** while remaining a superkey. By the monotonicity of closure, it suffices to test dropping **one attribute at a time**: if no set \(K-\{a\}\) is a superkey, then no proper subset of \(K\) can be a superkey.

In the order example:

- `(order_id, line_no)` is a **superkey** because its closure equals \(U\).
- `order_id` alone and `line_no` alone are **not** superkeys.
- Thus `(order_id, line_no)` is a **candidate key** under the given rules.
- `(order_id, line_no, product_id)` is only a **non-minimal** superkey.

**"Minimal" does not mean "having the fewest columns among all keys."** A relation can have multiple candidate keys with different numbers of attributes. Minimality only requires that no key contains a smaller superkey within itself.

### Primary Key and Alternate Keys

A **primary key** is a candidate key chosen for implementation. The remaining candidate keys are often called **alternate keys**. Do not confuse an "alternate key" with a **surrogate key**, such as an auto-generated `id` column. An `id` can serve as the primary key, but it does not automatically eliminate the uniqueness requirement of a business key.

In the theoretical relational model, a key must identify a row and contain no unknown values. When implementing in SQL, pay attention to `NULL`: `UNIQUE` constraints on nullable columns behave differently across DBMSs. If you use `UNIQUE` to represent a candidate key, ensure the key columns satisfy a **non-NULL** policy.

## 5. Multi-Candidate-Key Example: Do Not Stop at the First Key Found

Consider the abstract relation:

\[
R(A,B,C,D,E)
\]

with dependency set:

~~~text
F = {
    A  → B,
    B  → A,
    BC → D,
    D  → E
}
~~~

Suppose \(F\) is confirmed by the business. We want to find **all** candidate keys.

### Step 1 — Identify Mandatory Attributes

Attribute `C` **does not appear on the right-hand side of any dependency**. Without `C` from the start, no rule can add `C` to the closure. Therefore, **every candidate key must contain `C`**.

This is a search-space pruning technique; note that an attribute *appearing* on a right-hand side **does not mean** it definitely stays out of every key.

### Step 2 — Test Sets Containing `C`

| Candidate set | Computed closure | Superkey? |
|---|---|---|
| `{C}` | `{C}` | No |
| `{A,C}` | `{A,B,C,D,E}` | Yes |
| `{B,C}` | `{A,B,C,D,E}` | Yes |
| `{C,D}` | `{C,D,E}` | No |
| `{C,E}` | `{C,E}` | No |

Derivation of `{A,C}+`:

~~~text
Start:        {A, C}
By A → B:     {A, B, C}
By BC → D:    {A, B, C, D}
By D → E:     {A, B, C, D, E}
~~~

Derivation of `{B,C}+`:

~~~text
Start:        {B, C}
By B → A:     {A, B, C}
By BC → D:    {A, B, C, D}
By D → E:     {A, B, C, D, E}
~~~

### Step 3 — Check Minimality and Completeness

- `{A}+` contains only `A,B`; `{C}+` contains only `C`. Thus `{A,C}` is a candidate key.
- `{B}+` contains only `A,B`; `{C}+` contains only `C`. Thus `{B,C}` is a candidate key.
- There is no single-attribute key because `C` is mandatory yet `{C}+\ne U`.
- Any combination containing `C` plus either `A` or `B` along with other attributes is **not minimal**, because it contains `{A,C}` or `{B,C}`.
- Combinations that only add `D` and/or `E` to `C` cannot derive `A` or `B`.

Therefore, **all candidate keys** are:

\[
\boxed{\{A,C\}\quad\text{and}\quad\{B,C\}}
\]

Both keys are equally valid; we can choose one as the primary key and preserve the other via an appropriate unique constraint.

### Visualizing the Inference Paths

~~~mermaid
flowchart LR
  A["A"] --> B["B"]
  B --> A
  B --> BC["BC (requires both B and C)"]
  C["C"] --> BC
  BC --> D["D"]
  D --> E["E"]
~~~

The diagram helps visualize inference paths but **does not replace closure computation**: the edge `BC → D` applies only when **both B and C are already present**, not just one of them.

## 6. Procedure to Find All Candidate Keys

Given schema \(U\) and dependencies \(F\), you can follow these steps:

1. **Lock down the business rules.** Confirm key scope, uniqueness over time, and exceptions. Sample data is not enough to prove a dependency.
2. **Split right-hand sides if helpful.** You can rewrite `A → B,C` as `A → B`, `A → C` for easier reading and processing; closure computation yields the same result either way.
3. **Find mandatory attributes.** The set \(M=U-\operatorname{RHS}(F)\) (attributes not appearing on any right-hand side) must belong to every candidate key.
4. **Compute \(M^+\).** If \(M^+=U\), then \(M\) is already the sole candidate key; otherwise, test combinations adding attributes from \(U-M\).
5. **Test from smaller additions to larger ones.** For each subset \(S\), compute \((M\cup S)^+\). If it equals \(U\) and contains no already-found key, check minimality and record the key.
6. **Prune supersets of found keys.** They may be superkeys, but they are definitely not candidate keys.
7. **Verify completeness.** Ensure remaining combinations cannot yield minimal keys before concluding the list is complete.

Pseudocode for small problems:

~~~text
FIND_CANDIDATE_KEYS(U, F):
    mandatory := U - union_of_all_right_hand_sides(F)
    optional  := U - mandatory
    keys := empty_set_of_sets

    for each subset S of optional in ascending subset size:
        candidate := mandatory ∪ S

        if any known key K ⊆ candidate:
            continue

        if ATTRIBUTE_CLOSURE(candidate, F) = U:
            keys.add(candidate)

    return keys
~~~

Because subsets are explored in **ascending attribute count**, whenever a superkey is found that does not contain any already-known key, we can immediately record it as a candidate key: all smaller subsets have already been checked. In the case \(M=\varnothing\), the algorithm still tests the empty set first; this is a formally valid edge case.

**Complexity:** A single closure can be computed efficiently on finite sets, but **enumerating all candidate keys** can take exponential time because the number of combinations and candidate keys can grow very large. Use mandatory attributes and superset pruning to cut down the search; do not brute-force all combinations on a schema with hundreds of columns without first analyzing dependency structure.

## 7. Using Closure for Three Other Tasks

### 7.1. Checking Whether a Dependency Is Implied

Rule:

\[
F\models X\rightarrow Y\iff Y\subseteq X^+.
\]

In the order example, `customer_name` is in `{order_id}+`, so `order_id → customer_name` is implied. Conversely, `product_id` is not in `{order_id}+`; from the current \(F\), we **cannot infer** `order_id → product_id`. This also aligns with the business rule that an order can have multiple product lines.

"Not implied by \(F\)" does not by itself prove a dependency is false in the business domain. If rules are incomplete, ask the business owner and update \(F\) accurately.

### 7.2. Finding Redundant Attributes on the Left-Hand Side

Given relation \(R(A,B,C,D,E)\) with:

~~~text
F = {
    A  → B,
    B  → C,
    AC → D,
    D  → E
}
~~~

Consider the dependency `AC → D`. To see whether `C` is redundant on the left-hand side, compute `{A}+`:

~~~text
{A}
  → {A,B}         by A → B
  → {A,B,C}       by B → C
  → {A,B,C,D}     by AC → D
  → {A,B,C,D,E}   by D → E
~~~

Since `D ∈ {A}+`, we infer `A → D`; therefore `C` is **redundant** on the left-hand side of `AC → D` with respect to \(F\). This is useful when finding a **minimal cover**, reducing the number of dependencies to consider and clarifying the true determinants.

Note: the algorithm for checking redundant attributes must use the **exact dependency set under consideration** and handle replacing dependencies consistently. Do not arbitrarily delete entire dependencies just because several arrows appear related.

### 7.3. Normalization Analysis

Closure helps:

- Find all candidate keys to know which attributes are **prime attributes** (*prime*: belonging to at least one candidate key).
- Check **partial** dependencies: whether a proper subset of a key already suffices to determine a non-prime attribute.
- Identify dependencies violating **3NF**: for non-trivial `X → A`, `X` is not a superkey and `A` is not a prime attribute.
- Identify dependencies violating **BCNF**: for non-trivial `X → A`, `X` is not a superkey.

In `ORDER_LINE_FLAT`, `order_id → order_date` reflects information at the **order** level, not the **line-item** level; `customer_id → customer_name` reflects information at the **customer** level. Those dependencies explain the data redundancy, though decomposing relations also requires checking **lossless join** and **dependency preservation**.

## 8. Mapping Candidate Keys to a SQL Schema

### Composite Key from Order Rules

An appropriate relational design:

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
    unit_price_at_sale DECIMAL(12, 2) NOT NULL
        CHECK (unit_price_at_sale >= 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

In `order_items`, the composite key `(order_id, line_no)` expresses the exact rule "each line number is unique within an order". Do not create `UNIQUE(line_no)`, because line number 1 can repeat across many orders. Also do not create `UNIQUE(order_id, product_id)` if the same product is allowed on multiple lines within the same order.

Foreign keys and `CHECK` constraints are **additional constraints** that cannot be derived purely from functional dependencies. Primary keys are usually backed by an index structure, though index type and query efficiency also depend on the DBMS and workload.

### An Entity with Both a Surrogate Key and a Business Key

Suppose each student can enroll **only once** in a given course:

~~~sql
CREATE TABLE students (
    student_id BIGINT PRIMARY KEY,
    full_name VARCHAR(200) NOT NULL
);

CREATE TABLE courses (
    course_id BIGINT PRIMARY KEY,
    course_title VARCHAR(200) NOT NULL
);

CREATE TABLE enrollments (
    enrollment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    student_id BIGINT NOT NULL REFERENCES students(student_id),
    course_id BIGINT NOT NULL REFERENCES courses(course_id),
    enrolled_at DATE NOT NULL,
    UNIQUE (student_id, course_id)
);
~~~

In the `enrollments` table, both `{enrollment_id}` and `{student_id, course_id}` are **candidate keys** under the stated constraints. `enrollment_id` is chosen as the primary key, while the business key pair is preserved using `UNIQUE` and `NOT NULL`.

If the business rules allow **retaking the same course**, the `UNIQUE(student_id, course_id)` constraint would be wrong. In that case, you must clarify the new business key, such as adding `attempt_no` if enrollment attempts are explicitly identified. Do not add attributes to a key merely to dodge duplicate data without verifying the requirements.

### Checking Imported Data for Key Violations

In a staging table `staging_order_lines`, you can find duplicate order-ID and line-number pairs:

~~~sql
SELECT order_id, line_no, COUNT(*) AS occurrences
FROM staging_order_lines
GROUP BY order_id, line_no
HAVING COUNT(*) > 1;
~~~

The query detects **counterexamples** to the uniqueness rule if the data should have at most one record per pair. It cannot prove the key holds for future data; correctness must come from business requirements and be enforced by appropriate constraints. `NULL` values in staging data must be handled separately before finalizing keys.

## 9. Situations Where Key Identification Easily Goes Wrong

| Mistake | Problem | How to handle |
|---|---|---|
| Seeing no duplicate `email` in sample data and picking it as a key | A small dataset does not prove email is always unique and immutable | Confirm the rule and how email changes or shared accounts are handled |
| Seeing `X^+=U` and immediately concluding \(X\) is a candidate key | \(X\) is only guaranteed to be a **superkey** and may contain extra columns | Test dropping each attribute of \(X\) |
| Finding one key and stopping | Multiple candidate keys may exist | Enumerate minimal sets or prove all cases are covered |
| Mistaking a multi-column superkey for a "stronger" key | A superset of a key only adds redundant columns | Choose keys based on minimality and business stability |
| Treating a store-local code as globally unique | Missing identifier scope | Include `store_id` or `tenant_id` in the rule if required by the business |
| Mixing current data with historical data | Dependencies can change over time | Separate versions/effective times or use snapshots at the proper grain |
| Using `UNIQUE` on a nullable column as a theoretical candidate key | SQL `NULL` semantics differ from the classical relational model | Enforce `NOT NULL` and DBMS-compatible constraint semantics |

Similar issues arise when comparing relational, document, graph, and analytical models:

- For **documents**, document keys must match the uniqueness scope while avoiding confusion between embedded snapshots and current attributes.
- For **graphs**, vertex/edge identifiers and uniqueness properties depend on the rules for each object type; do not assume internal storage IDs are business keys.
- For **analytics**, the fact table grain and dimension keys (including historical versions where applicable) determine which attribute combination truly identifies a row.

Closure is a formal tool for **functional dependencies in relations**; for other models, translate identification and dependency reasoning into the corresponding constraint mechanisms without assuming they behave like SQL.

## 10. Practice Exercises with Solutions

### Exercise 1 — Closure and Single-Attribute Key

Given \(R(A,B,C,D)\) and:

~~~text
F = { A → B, B → C, AC → D }
~~~

**Task:** Compute `{A}+`. Is `A` a candidate key?

**Solution:** Start with `{A}`; add `B` by `A → B`; add `C` by `B → C`; since `A,C` are now present, add `D` by `AC → D`. Thus `{A}+ = {A,B,C,D} = U`. The single-attribute set `{A}` is a superkey, and has no non-empty proper subset to drop. Under the given dependencies, `A` is a candidate key. `A` is also a mandatory attribute because it does not appear on the right-hand side of \(F\).

### Exercise 2 — Two Candidate Keys

Given \(R(P,Q,R,S)\) and:

~~~text
F = { P → Q, Q → P, R → S }
~~~

**Task:** Find all candidate keys.

**Solution:** `R` is not on any right-hand side, so it must be in every key. `{P,R}+` gains `Q` by `P→Q` and `S` by `R→S`, so it equals \(U\). Similarly `{Q,R}+=U` because `Q→P`. `R` alone is insufficient; neither `P` nor `Q` works without `R`. Therefore, the candidate keys are **`{P,R}` and `{Q,R}`**. `{P,Q,R}` is a superkey but not minimal.

### Exercise 3 — Distinguishing Superkeys from Candidate Keys

Given \(R(A,B,C)\), \(F=\{A\rightarrow B,\ B\rightarrow C\}\). Evaluate the set `{A,B}`.

**Solution:** `{A,B}+=\{A,B,C\}`, so it is a **superkey**. However, `{A}+=\{A,B,C\}` also equals \(U\), so `{A,B}` is **not** a candidate key. The candidate key is **`{A}`**.

### Exercise 4 — Testing Implied Dependencies

Given \(R(A,B,C,D,E)\), \(F=\{A\rightarrow BC,\ C\rightarrow D,\ D\rightarrow E\}\). Are `A → E` and `B → E` implied?

**Solution:** `{A}+` successively receives `B,C`, then `D`, then `E`, so `A → E` **is** implied. Meanwhile `{B}+ = {B}` under \(F\), so `B → E` **cannot be inferred**. Do not infer the reverse of `A → B` without an additional rule.

### Exercise 5 — Missing Key Scope

A multi-store platform uses `order_no` incrementing from 1 in each store. Each order has multiple `line_no` values unique within that order. How should the line-item key be chosen?

**Solution:** If `order_no` is allowed to repeat across stores, an appropriate business key could be **`(store_id, order_no, line_no)`**, provided that combination is genuinely unique and stable. `(order_no, line_no)` alone does not suffice for system-wide identification. If the system has a global `order_id`, `(order_id, line_no)` can still be used according to the corresponding rule. Always confirm identifier scope before locking in the key.

## 11. Practice Checklist

- [ ] Confirmed what entity/event each data row represents and at what grain.
- [ ] Built dependency set \(F\) from business rules, specifying scope and effective time.
- [ ] Ran the closure algorithm starting from \(X\), scanning dependencies until reaching a fixed point.
- [ ] Used \(Y\subseteq X^+\) to test implied dependencies.
- [ ] Distinguished `X+ = U` (superkey) from the **minimality** check (candidate key).
- [ ] Checked mandatory attributes and remaining combinations to find **all** candidate keys.
- [ ] Separated primary key, other business keys, and surrogate keys; did not overlook valid unique constraints.
- [ ] Cross-checked keys against `NULL`, tenant/store scope, historical versions, and exceptions.
- [ ] Applied the results to normalization, foreign keys, `UNIQUE`, and actual query needs.

**Takeaway:** Computing closure answers "**from set \(X\), which attributes can we derive?**". If \(X^+=U\), \(X\) is a superkey. Only when **no component can be removed** while still maintaining \(X^+=U\) is it a candidate key. For accurate data design, inference must start from **functional dependencies genuinely guaranteed by the business**.
