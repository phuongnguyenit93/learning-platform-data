# Trivial, Full, Partial, and Transitive Functional Dependencies

## Learning Objectives

In the **DATABASE_DATA_MODELING** module, accurately identifying the types of functional dependencies helps turn business rules into a data model with clear keys, minimal redundancy, and verifiable structure. This is the foundation for normalization analysis, constraint selection, and building a physical schema in a relational database management system. Thinking in terms of which data depends on which is also useful when considering document, graph, or analytical models, even though those systems do not necessarily enforce functional dependencies the way SQL does.

After this lesson, you will be able to:

1. Distinguish **trivial**, **non-trivial**, **full**, **partial**, and **transitive** dependencies using exact definitions.
2. Verify dependencies using **attribute closure**, rather than merely inspecting a few rows of data.
3. Recognize how partial and transitive dependencies lead to update, insertion, and deletion anomalies.
4. Connect dependencies to candidate keys, **2NF**, **3NF**, and **BCNF**; translate the results into concrete tables and constraints.

## 1. Shared Context: Functional Dependencies Reflect Business Rules

Consider a table exporting order line-item details:

~~~text
ORDER_LINE_FLAT(
    order_id, line_no, order_date,
    customer_id, customer_name,
    product_id, product_name,
    quantity, unit_price_at_sale
)
~~~

**The grain** of the table is one line item in one order. Suppose the business team confirms:

- Each `order_id` identifies one order with one order date and one customer.
- Within **each order**, `line_no` is unique. Each `(order_id, line_no)` pair determines one product, quantity, and unit price at the time of sale.
- Each `customer_id` has one current name `customer_name`; each `product_id` has one current name `product_name`.
- An order has multiple lines; a product can be sold at multiple prices and can appear multiple times within the same order.

From this, we obtain the base set of functional dependencies \(F\):

~~~text
F1: order_id             → order_date, customer_id
F2: customer_id          → customer_name
F3: product_id           → product_name
F4: (order_id, line_no)  → product_id, quantity, unit_price_at_sale
~~~

The notation \(X \rightarrow Y\) means: for **every pair of valid rows**, if two rows match on all attributes in \(X\), they must match on all attributes in \(Y\).

\[
\forall t_1,t_2 \in r,\quad
t_1[X]=t_2[X]\Rightarrow t_1[Y]=t_2[Y].
\]

For example, `order_id → customer_id` states that the same order cannot have two different customer IDs. This is a rule over **all valid states of the data**, not just over the rows currently stored.

To classify dependencies, you must hold fixed the **schema, rule set \(F\), identifier scope, and data point-in-time**. If `order_id` is unique only within one store, you must consider `(store_id, order_id)`; if the table stores rename history, the assumption behind `customer_id → customer_name` may no longer hold.

## 2. Trivial Functional Dependencies

A dependency \(X\rightarrow Y\) is **trivial** when:

\[
Y\subseteq X.
\]

This means the attributes on the right-hand side are already contained in the left-hand side. For example:

~~~text
(order_id, line_no) → order_id
(order_id, line_no) → line_no
(order_id, line_no) → (order_id, line_no)
customer_id         → customer_id
~~~

They are **always logically true**, regardless of whether the system handles sales, inventory, or HR. If two rows agree on `(order_id, line_no)`, they naturally agree on `order_id`. This is Armstrong's **reflexivity axiom**.

### Non-Trivial and Completely Non-Trivial

A dependency is **non-trivial** when \(Y\nsubseteq X\). For instance:

~~~text
order_id                    → customer_id
(order_id, line_no)         → quantity
(order_id, customer_id)     → (customer_id, order_date)
~~~

The last example is **non-trivial** because `order_date` is not on the left-hand side, even though `customer_id` appears on both sides.

A dependency is **completely non-trivial** when \(X\cap Y=\varnothing\), such as `product_id → product_name`. This is a different concept from a **full functional dependency** in the next section: "completely non-trivial" describes **the intersection between the two sides**; "full" describes **whether attributes on the left-hand side can be dropped**.

**Design implication:** trivial dependencies do not help discover new business attributes determined by a key, so when finding keys, minimal covers, or performing normalization analysis, we usually focus on non-trivial dependencies.

## 3. Full Functional Dependencies

Suppose \(X\rightarrow Y\) holds under \(F\). It is a **full functional dependency** if **no proper subset** \(X'\subset X\) still determines \(Y\):

\[
X\rightarrow Y
\quad\text{and}\quad
\forall X'\subset X:\; X'\not\rightarrow Y.
\]

With \(X=\{\text{order_id},\text{line_no}\}\), consider:

~~~text
(order_id, line_no) → quantity
~~~

This is a full dependency in the given example:

- The pair `(order_id, line_no)` uniquely identifies one row, so it determines `quantity`.
- Knowing only `order_id`, an order can have multiple lines with different quantities.
- Knowing only `line_no`, line number 1 of two different orders can have different quantities.

No shorter left-hand side suffices to determine `quantity`.

### Verifying with Attribute Closure

The closure \(X^+\) under \(F\) is all attributes that can be inferred from \(X\). From F1–F4:

~~~text
{order_id}+ =
  {order_id, order_date, customer_id, customer_name}

{line_no}+ = {line_no}

{order_id, line_no}+ =
  {order_id, line_no, order_date, customer_id, customer_name,
   product_id, product_name, quantity, unit_price_at_sale}
~~~

Because `quantity` is in `{order_id, line_no}+` but not in the closure of either proper subset `{order_id}` or `{line_no}`, this dependency is **full** under \(F\). The closure of the pair also contains all nine attributes in the table, so the pair is a **superkey**; since both components are necessary, it is a **candidate key**.

Note: with a multi-attribute left-hand side, you must test every way of dropping attributes, not just one. When the right-hand side has multiple attributes, you should **decompose it into single attributes** before normalization analysis; one attribute may be partially dependent while another is fully dependent.

## 4. Partial Functional Dependencies

A dependency \(X\rightarrow Y\) is **partial** if there exists **at least one proper subset** \(X'\subset X\) that also determines \(Y\):

\[
\exists X'\subset X:\; X'\rightarrow Y.
\]

In the combined table, the candidate key is `(order_id, line_no)`. Consider:

~~~text
(order_id, line_no) → order_date
~~~

This dependency holds, but it is **partial**, because:

~~~text
order_id → order_date
~~~

`order_id` alone, a part of the composite key, already suffices to determine the order date. Similarly:

~~~text
(order_id, line_no) → customer_id
~~~

is a partial dependency because `order_id → customer_id`.

Conversely, `(order_id, line_no) → quantity` is full under the given rules. You must not conclude that all attributes of a table are fully dependent on the key merely because they sit on the same row.

### Why Do Partial Dependencies Cause Redundancy?

| order_id | line_no | order_date | customer_id | quantity |
|---|---:|---|---|---:|
| DH01 | 1 | 2026-11-01 | KH01 | 2 |
| DH01 | 2 | 2026-11-01 | KH01 | 1 |
| DH02 | 1 | 2026-11-02 | KH02 | 3 |

The `order_date` and `customer_id` values for `DH01` are repeated on **every line item**. If you update the order date on only one line, the table contradicts `order_id → order_date`. If an order has no product lines yet, it is difficult to store order information without creating a dummy line.

### Partial Dependencies and Second Normal Form (2NF)

A relation is in **2NF** when it is already in 1NF and **every non-prime attribute** (an attribute not belonging to any candidate key) **is fully functionally dependent on every candidate key**.

In the example, `order_date` and `customer_id` are non-prime attributes yet depend on `order_id` — part of the key `(order_id, line_no)`. Therefore, the combined table **violates 2NF**.

Common pitfalls:

- You must evaluate **every candidate key**, not only the primary key chosen for implementation.
- A partial dependency violates **2NF** under the criterion above only when the right-hand side is a **non-prime** attribute. A dependency onto a *prime attribute* must be evaluated strictly according to the normal form's definition.
- With a single-attribute candidate key, you cannot drop a **non-empty** component to create an ordinary partial dependency; however, you still need to check other candidate keys and dependencies from the empty set if the model has constant attributes.

## 5. Transitive Functional Dependencies

If \(X\rightarrow Y\) and \(Y\rightarrow Z\), then \(X\rightarrow Z\) follows. This is the **transitivity rule** in Armstrong's axioms.

Example:

~~~text
order_id → customer_id
customer_id → customer_name
--------------------------------
order_id → customer_name
~~~

Each order ID determines a customer, and each customer ID determines a current name; therefore, the order ID determines the customer's current name. Similarly:

~~~text
(order_id, line_no) → product_id
product_id          → product_name
-----------------------------------
(order_id, line_no) → product_name
~~~

These chains have an **intermediate** attribute or set of attributes. They show why a customer name or product name can appear multiple times across order lines.

~~~mermaid
flowchart LR
  A["order_id"] --> B["customer_id"]
  B --> C["customer_name"]
  D["(order_id, line_no)"] --> E["product_id"]
  E --> F["product_name"]
~~~

### Distinguishing Transitive Inference from 3NF Violations

**Transitivity** is a very broad inference property. **Not every transitive chain causes a relation to violate 3NF.** When evaluating normalization, you must check whether the intermediate attribute is a superkey and whether the right-hand attribute belongs to a candidate key.

In the combined table example, `customer_id` is **not** a superkey of the line-item table and `customer_name` does **not** belong to any candidate key. Thus the non-trivial dependency `customer_id → customer_name` is a concrete reason why the combined table **fails 3NF**.

Definition of 3NF in terms of functional dependencies: for **every non-trivial dependency** \(X\rightarrow A\) (with a single attribute on the right-hand side) implied by \(F\), **at least one** condition must hold:

1. \(X\) is a **superkey**; or
2. \(A\) is a **prime attribute**, meaning it belongs to at least one candidate key.

For example, even if a transitive dependency exists, if every non-trivial dependency satisfies one of the two conditions above, the relation can still satisfy 3NF.

Advanced example with `R(A, B, C)` and `F = {AB → C, C → B}`: the candidate keys are `AB` and `AC`. The dependency `C → B` has a left-hand side that is **not** a superkey, but `B` is a prime attribute because it appears in the candidate key `AB`; thus the relation satisfies **3NF but not BCNF**. BCNF requires the left-hand side of **every non-trivial dependency** to be a superkey.

## 6. Comparison Table: Four Types Reflect Different Questions

| Dependency type | Diagnostic question | Example cue |
|---|---|---|
| **Trivial** | Is the right-hand side already wholly contained in the left-hand side? | `(order_id, line_no) → order_id` |
| **Full** | If any part of the left-hand side is removed, does it still determine the right-hand side? **No** | `(order_id, line_no) → quantity` |
| **Partial** | Does a proper subset of the left-hand side still determine the right-hand side? **Yes** | `(order_id, line_no) → order_date` |
| **Transitive** | Can it go through an intermediate attribute \(Y\), as in \(X→Y→Z\)? | `order_id → customer_id → customer_name` |

**The four types do not form four mutually exclusive categories.** "Trivial / non-trivial" examines the set relationship between the two sides; "full / partial" examines the **minimality of the left-hand side**; "transitive" examines the **inference path**. For example, `(order_id, line_no) → customer_name` is both a **partial** dependency (because `order_id → customer_name`) and derivable via **transitivity** `order_id → customer_id → customer_name`.

With a multi-attribute right-hand side, such as `(order_id, line_no) → (quantity, order_date)`, there is a subtlety:

- No subset of `(order_id, line_no)` determines **both** `quantity` and `order_date` simultaneously, so the dependency with the **entire** right-hand side can be considered full by the set definition.
- However, once the right-hand side is decomposed, `(order_id, line_no) → order_date` is **partial**, while `(order_id, line_no) → quantity` is **full**.

Therefore, when analyzing 2NF or finding a minimal cover, **decompose the right-hand side into single attributes** before classifying.

## 7. A Verifiable Classification Workflow

### Step 1 — List Confirmed Dependencies

Ask domain experts: "Under what circumstances could this identifier point to two different values?" Clarify the scope (system-wide, store, year), current vs. historical status, and valid exceptions.

### Step 2 — Find Keys Using Attribute Closure

Set `closure = X`; iterate over dependencies \(L\rightarrow R\) in \(F\), and if \(L\subseteq closure\) then add \(R\) to `closure`, until no new attributes are added. If \(X^+\) contains all attributes of the relation, \(X\) is a **superkey**; proceed to test dropping each attribute to verify minimality for a **candidate key**.

~~~text
attributeClosure(X, F):
    result := X
    repeat:
        previous := result
        for each (L → R) in F:
            if L ⊆ result:
                result := result ∪ R
    until result = previous
    return result
~~~

### Step 3 — Decompose and Test the Left-Hand Side

Split `X → A,B` into `X → A` and `X → B`. For each `X → A`:

1. If \(A\in X\), record it as **trivial**.
2. If non-trivial, check \(A\in (X-\{x\})^+\) for each \(x\in X\).
3. If at least one \(x\) can be dropped, it is a **partial** dependency under \(F\); otherwise, it is **full**.
4. Check inference paths \(X\rightarrow Y\rightarrow A\) when searching for **transitive** dependencies and sources of redundancy.

Note that the rule for testing each element of the left-hand side applies only after confirming that the dependency itself holds; for dependencies with multiple attributes on the right-hand side, decompose as shown above.

### Step 4 — Connect to Normalization

| Check | Core question |
|---|---|
| **1NF** | Are column values atomic under the chosen model, with no repeating groups? |
| **2NF** | Does a non-prime attribute depend on only part of **any** candidate key? |
| **3NF** | Is there a non-trivial dependency `X → A` where `X` is not a superkey and `A` is not a prime attribute? |
| **BCNF** | Is there any non-trivial dependency `X → A` where `X` is not a superkey? |

These are distinct evaluation criteria, not alternate labels for dependency types. When decomposing tables, you must also consider **lossless join** and, where important, **dependency preservation**.

## 8. From Classification to Table Design

In `ORDER_LINE_FLAT`, two groups of information are mixed:

- The **partial** dependency `order_id → order_date, customer_id` indicates that order information should be stored at the single-order grain.
- The dependencies `customer_id → customer_name` and `product_id → product_name` indicate that current names belong to the customer and product entities; repeating them on every line item creates transitive dependency paths through the identifiers.

Assuming each identifier is globally unique and names are **current names**, we can decompose into:

~~~text
CUSTOMERS(customer_id PK, customer_name)
PRODUCTS(product_id PK, product_name)
ORDERS(order_id PK, order_date, customer_id FK)
ORDER_ITEMS((order_id, line_no) PK, product_id FK,
            quantity, unit_price_at_sale)
~~~

Example DDL:

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

Primary keys ensure each identifier uniquely determines one row in its corresponding table. Foreign keys express relationships between entities; `CHECK` constraints express domain value rules that functional dependencies themselves **do not** describe.

`unit_price_at_sale` lives on the **transaction line**, because business rules allow the same product to have multiple sale prices. Do not add `UNIQUE(order_id, product_id)` if an order is allowed to have two lines for the same product; that would be an incorrect business constraint. Additional indexes for queries by `customer_id` or `product_id` should be decided based on query patterns and execution plans, not derived automatically from functional dependency notation.

In a document model, line items can be embedded inside an order to read the whole order at once, but you must still clearly distinguish which data is a **transaction-time snapshot** and which data is read from the current source. In an analytical model, fact grain and how dimension history is stored directly affect which dependencies hold at each point in time.

## 9. Common Misconceptions

**Misconception 1 — "A long left-hand side means a full dependency."** Incorrect. `(order_id, line_no) → order_date` has two attributes on the left-hand side yet is still partial because `order_id` alone suffices.

**Misconception 2 — "A transitive dependency always violates 3NF."** Incorrect. You must check non-trivial dependencies for whether the left-hand side is a superkey or the right-hand side is a prime attribute. The 3NF-but-not-BCNF example above illustrates the difference.

**Misconception 3 — "Trivial means false or useless."** Trivial dependencies are **always logically true**. They are useful for formal inference, even though by themselves they do not supply an additional business rule.

**Misconception 4 — "No violations in the data means the dependency holds."** A small sample does not prove a dependency holds across all valid states; a business rule is required. Sample data can only supply a **counterexample** when two rows share \(X\) but differ on \(Y\).

**Misconception 5 — "Only the primary key needs to be checked."** Normalization must examine **all candidate keys**. An attribute is *prime* if it belongs to at least one candidate key, not necessarily the primary key.

**Misconception 6 — "Dependency types are mutually exclusive."** A dependency can be both partial and derivable transitively. Do not try to force every arrow into exactly one bucket.

## 10. Practice Exercises with Solutions

### Exercise 1 — Classify Dependencies

Given the relation `ENROLLMENT(student_id, course_id, student_name, course_title, grade)`, suppose:

~~~text
student_id → student_name
course_id  → course_title
(student_id, course_id) → grade
~~~

Each student can take multiple courses, and each course has multiple students. Classify:

1. `(student_id, course_id) → student_id`
2. `(student_id, course_id) → grade`
3. `(student_id, course_id) → student_name`

**Solution:** (1) **trivial** because the right-hand side belongs to the left-hand side. (2) **full** under the given dependencies, because a student has multiple grades and a course has grades for multiple students. (3) **partial** because `student_id → student_name`. When evaluating 2NF, `student_name` and `course_title` should be split out into separate entity tables.

### Exercise 2 — Find the Transitive Path

Given:

~~~text
employee_id   → department_id
department_id → department_name
~~~

Infer a new dependency and state the condition under which a combined table `(employee_id, department_id, department_name)` violates 3NF.

**Solution:** We infer `employee_id → department_name` via transitivity. If `employee_id` is the candidate key of the table, `department_id` is not a superkey, and `department_name` is a non-prime attribute, then `department_id → department_name` violates the 3NF criterion. We can decompose into `EMPLOYEES(employee_id, department_id)` and `DEPARTMENTS(department_id, department_name)`, linked by a foreign key between the two tables.

### Exercise 3 — Do Not Classify the Entire Right-Hand Side Too Early

Given `(order_id, line_no) → (quantity, order_date)` along with the rules at the start of the lesson, how does each attribute on the right-hand side depend?

**Solution:** `quantity` is **fully** dependent on the composite key; `order_date` is **partially** dependent because `order_id → order_date`. You must decompose the right-hand side to uncover the 2NF issue.

### Exercise 4 — Check Time Assumptions

The system allows customers to change their names and stores the **name at the time of order** in `customer_name_at_order`. Can we assert `customer_id → customer_name_at_order`?

**Solution:** No. The same customer can have multiple names at different order times. If each order stores only one name snapshot, `order_id → customer_name_at_order` can hold under that rule. Concluding a dependency depends on **attribute meaning** and **time scope**.

## 11. Checklist for Applying to a Data Model

- [ ] Correctly identified the grain of each relation and the scope of identifiers.
- [ ] Built the dependency set from confirmed business rules, clarifying current vs. historical data.
- [ ] Identified all candidate keys using attribute closure.
- [ ] Decomposed the right-hand side into single attributes before testing full vs. partial dependencies.
- [ ] Distinguished trivial dependencies from dependencies carrying business meaning.
- [ ] Found transitive dependencies and checked 3NF/BCNF conditions accurately.
- [ ] Evaluated data anomalies, lossless join, and dependency preservation when decomposing tables.
- [ ] Mapped rules to primary keys, foreign keys, `UNIQUE`, `CHECK`, and indexes purposefully.

**Takeaway:** **Trivial** dependencies ask "is the right-hand side already inside the left-hand side?"; **full** and **partial** dependencies ask "can the left-hand side be shortened?"; **transitive** dependencies ask "through which intermediate attribute is this value determined?". Distinguishing these three questions helps you accurately spot redundancy risks and choose the right data structure.
