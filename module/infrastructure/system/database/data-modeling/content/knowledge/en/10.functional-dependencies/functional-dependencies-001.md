# Functional Dependencies and Deriving Them from Business Rules

## Learning Objectives

In the **DATABASE_DATA_MODELING** module, functional dependencies are the tool that connects business requirements to data design: from them, you identify keys, detect redundant data, normalize tables, and choose appropriate constraints when implementing a relational schema.

After this lesson, you will be able to:

- Explain precisely the meaning of a functional dependency \(X \rightarrow Y\).
- Read business rules and identify the left-hand side, right-hand side, and **scope of validity** of a dependency.
- Distinguish dependencies **guaranteed by business rules** from coincidences in a few sample rows.
- Use attribute closure and inference rules to verify keys and implied dependencies.
- Translate those results into verifiable table designs, keys, and constraints.

## 1. The Business Problem: One Table Holding Multiple Different Facts

Suppose an order management system exports order line-item data as a single relation:

~~~text
CHI_TIET_DON_HANG(
    order_id, line_no, order_date,
    customer_id, customer_name,
    product_id, product_name,
    quantity, unit_price_at_sale
)
~~~

**The grain of a row** is *one line item in one order*, not an order or a product. For example, here are some columns of the table:

| order_id | line_no | customer_id | product_id | quantity | unit_price_at_sale |
|---|---:|---|---|---:|---:|
| DH01 | 1 | KH01 | SP01 | 2 | 6000 |
| DH01 | 2 | KH01 | SP02 | 1 | 25000 |
| DH02 | 1 | KH02 | SP01 | 3 | 6500 |

The system enforces the following rules:

1. Each **order ID** determines exactly one order date and one customer.
2. Within each order, **line numbers** (`line_no`) do not repeat; line numbering can restart from 1 in another order. Each line determines one product, quantity, and unit price recorded at the time of placement.
3. Each **customer ID** looks up to one current name; each **product ID** looks up to one current name.
4. A product can be sold at **different prices** across different orders. An order can contain multiple lines, including two lines for the same product.

The statements above contain design information that is more important than the three sample rows themselves. They tell us which fields determine which other fields and at what **level**.

## 2. Definition of a Functional Dependency

Given a relation schema \(R(U)\), where \(U\) is the set of attributes, the notation:

\[
X \rightarrow Y
\]

is read as **\(X\) functionally determines \(Y\)**, where \(X, Y \subseteq U\). It means: for **every valid data state according to the business rules**, if two rows agree on all attributes in \(X\), they must agree on all attributes in \(Y\).

\[
\forall t_1,t_2 \in r,\quad
t_1[X]=t_2[X] \Rightarrow t_1[Y]=t_2[Y]
\]

Here \(r\) is any valid state of \(R\). For instance:

- `order_id → customer_id`: two rows with the same order ID **must** have the same customer ID.
- `(order_id, line_no) → quantity`: within the same order, each line number has exactly one quantity.
- `product_id ↛ unit_price_at_sale`: the same product **can** be sold at multiple prices.

The arrow expresses **the uniqueness of the determined value**, not that \(Y\) must be computed from \(X\) by a formula, nor that \(X\) and \(Y\) have a causal relationship. Multiple distinct values of \(X\) can still map to the same value of \(Y\): many orders can belong to the same customer.

**Key point:** sample data can help *refute* a dependency when two violating rows are found, but it cannot *prove* that a dependency holds for all future data. To assert a dependency, you need a confirmed business rule or constraint.

## 3. Turning Business Statements into Functional Dependencies

An effective way to read them is to rephrase the business statement into the form: **"For each value of \(X\), there is at most one valid value of \(Y\) within the same scope"**.

| Confirmed rule | Functional dependency | Condition to understand correctly |
|---|---|---|
| Each order has one order date and one customer | `order_id → order_date, customer_id` | `order_id` is globally unique across the system |
| Each line number is unique only *within an order* | `(order_id, line_no) → product_id, quantity, unit_price_at_sale` | `line_no` is allowed to repeat in other orders |
| Each customer ID has one current name | `customer_id → customer_name` | `customer_name` is the current name, not a snapshot captured at purchase time |
| Each product ID has one current name | `product_id → product_name` | Current names are managed consistently |

Conversely, the following dependencies **cannot** be inferred from the rules above:

| False or unsupported claim | Counterexample / reason |
|---|---|
| `customer_id → order_id` | One customer can place multiple orders |
| `order_id → product_id` | One order can contain multiple products |
| `line_no → product_id` | Line number 1 appears in many orders |
| `product_id → unit_price_at_sale` | Transaction price depends on each sale |
| `(order_id, product_id) → line_no` | One product can appear on multiple lines of the same order |
| `customer_name → customer_id` | Two customers can share the same name |

Notice the difference between an **identifying key** and a **descriptive attribute**: "customer ID determines name" does not imply "name determines customer ID".

### Scope and Time Can Change the Answer

Before writing down a dependency, always clarify:

- **Uniqueness scope:** if a product code is unique only *within a store*, the correct dependency may be `(store_id, product_code) → product_name`, instead of `product_code → product_name`.
- **Point in time:** `customer_id → customer_name` describes the *current name*. If the table stores `customer_name_at_order` (a snapshot taken when placing the order), the same customer can have multiple historical names. In that case `customer_id → customer_name_at_order` is not guaranteed; however, `order_id → customer_name_at_order` may hold.
- **Business exceptions:** if the system allows reassigning the customer attached to an order, you must decide whether the relation stores the **current state** or the **history of edits**. For history, a version or effective timestamp must be added to the left-hand side.
- **Grain:** a "line item" relation differs from a "price change event" relation. Choosing the wrong grain will make dependencies appear contradictory.

When a rule is unclear, record an **assumption to be confirmed** instead of prematurely adding the dependency to the model.

## 4. Process for Deriving Dependencies from Real Requirements

### Step 1 — Identify Entities, Attributes, and Grain

Ask: "What does *one row* of data represent?" In the example, it is one order line item. List the attributes belonging to the line item itself, to the order, to the customer, and to the product. This exposes information being repeated when multiple entities are combined into one table.

### Step 2 — Look for Uniqueness Statements

Read words like "each", "unique", "one", "within", and "at the time" especially carefully. For "each order has only one customer", try setting \(X = \{\text{order_id}\}\), \(Y = \{\text{customer_id}\}\).

Do not turn "a customer **has many** orders" into `customer_id → order_id`: it describes the possibility of multiple values on the right-hand side, which refutes that dependency.

### Step 3 — Verify Stability and Exceptions

Ask the business owner:

- Is this code globally unique, or only within an organization, a year, or a branch?
- Can a record change owner, change code, or have multiple versions over time?
- Is the stored value current data or a **historical snapshot**?
- Are there any valid exceptions that produce two \(Y\) values for the same \(X\)?

A single **business-valid** counterexample is enough to refute the dependency under consideration.

### Step 4 — Write the Dependency and Check the Reverse Direction

Write it in the form `X → Y`, along with a brief definition of \(X\), \(Y\), and the scope. Always check `Y → X` separately; the reverse direction does not automatically hold.

### Step 5 — Minimize and Identify Keys

If `(order_id, line_no) → quantity`, try removing each attribute on the left-hand side. Because one order has multiple lines and line numbers repeat across orders, neither `order_id` nor `line_no` can be removed. This is a **full** dependency on the composite key.

If a left-hand side still contains redundant attributes, remove them so the model reflects the minimal determinant. Then use **attribute closure** to verify keys.

### Step 6 — Cross-Check with Data and Design Enforcement

Inspect existing data for violations, confirm again with domain experts, and then decide which dependencies will be enforced via primary keys, unique constraints, foreign keys, or table decomposition. The result is a **verifiable set of rules and assumptions**, not just a list of arrows.

## 5. Inferring Dependencies: No Need to Re-Ask Every Rule

Suppose the set of dependencies guaranteed by the business on relation `CHI_TIET_DON_HANG` is:

~~~text
F = {
  order_id              → order_date, customer_id,
  customer_id           → customer_name,
  product_id            → product_name,
  (order_id, line_no)   → product_id, quantity, unit_price_at_sale
}
~~~

From `order_id → customer_id` and `customer_id → customer_name`, we infer:

~~~text
order_id → customer_name
~~~

That is an **inferred dependency**: no new business statement is needed, because it is a logical consequence of the known dependencies.

### Armstrong's Axioms

Three fundamental rules that hold for every set of functional dependencies:

| Rule | Statement | Example |
|---|---|---|
| **Reflexivity** | If \(Y \subseteq X\), then \(X \rightarrow Y\) | `(order_id, line_no) → order_id` |
| **Augmentation** | If \(X \rightarrow Y\), then \(XZ \rightarrow YZ\) | From `order_id → customer_id` infer `(order_id, line_no) → (customer_id, line_no)` |
| **Transitivity** | If \(X \rightarrow Y\) and \(Y \rightarrow Z\), then \(X \rightarrow Z\) | `order_id → customer_id → customer_name` |

Here \(XZ\) denotes the union of two attribute sets \(X \cup Z\), not multiplication. From these axioms follow the **decomposition** rule (\(X \rightarrow YZ\) implies \(X \rightarrow Y\)) and the **union** rule (if \(X \rightarrow Y\) and \(X \rightarrow Z\), then \(X \rightarrow YZ\)).

### Computing Closure \(X^+\)

The **closure of \(X\) under \(F\)** is the set of all attributes that can be inferred from \(X\). Algorithm:

~~~text
closure := X
Repeat:
  For each dependency A → B in F:
    If A ⊆ closure then add B to closure.
Until closure no longer changes.
~~~

With \(X = \{\text{order_id}, \text{line_no}\}\):

| Iteration | Attributes added | Why |
|---|---|---|
| Start | `order_id, line_no` | \(X\) itself |
| 1 | `order_date, customer_id` | `order_id → order_date, customer_id` |
| 2 | `customer_name` | `customer_id → customer_name` |
| 3 | `product_id, quantity, unit_price_at_sale` | `(order_id, line_no) → ...` |
| 4 | `product_name` | `product_id → product_name` |

The closure yields **all nine attributes** of `CHI_TIET_DON_HANG`. Therefore `(order_id, line_no)` is a **superkey**. Dropping either `order_id` or `line_no` fails to determine all attributes, so this is a **candidate key** (minimal key).

A set \(X\) is a superkey when \(X^+ = U\). It is a candidate key when no proper subset of \(X\) is still a superkey. A primary key is a candidate key chosen for implementation.

### Full, Partial, and Transitive Dependencies

With respect to the composite key `(order_id, line_no)` of the combined table:

- **Full:** `(order_id, line_no) → quantity`, because no proper subset on the left suffices to determine `quantity`.
- **Partial:** `order_id → order_date, customer_id`, because part of the composite key already determines those columns.
- **Transitive:** the composite key determines `customer_id`, and then `customer_id → customer_name`; similarly for `product_id → product_name`.

These cases explain why customer names, order dates, or product names repeat across line items and serve as clues for normalization.

When a dependency set needs to be simplified for algorithmic design, you can compute a **minimal cover**: split right-hand sides into single attributes; remove redundant attributes from left-hand sides; then remove dependencies that can be inferred from the remaining ones. A minimal cover may not be unique, but it must be equivalent in terms of implied dependencies.

## 6. Verifying Against Data: Look for Counterexamples, Do Not Over-Infer

Suppose initial imported data resides in `staging_order_lines`. To find orders appearing with multiple customer IDs, run:

~~~sql
SELECT
    order_id,
    COUNT(DISTINCT customer_id) AS different_customers
FROM staging_order_lines
GROUP BY order_id
HAVING COUNT(DISTINCT customer_id) > 1;
~~~

This query checks for **signs of violation** of `order_id → customer_id` when `customer_id` does not contain `NULL`. For example, two rows `DH01, KH01` and `DH01, KH02` are enough to show that the data does not match the rule "one customer per order".

If it returns no rows, we only know that **the sample data being checked shows no violations yet**. We must not conclude that the dependency always holds. For `NULL`, `COUNT(DISTINCT ...)` ignores missing values; a policy for handling `NULL` must be agreed upon or checked separately.

When a violation is detected, verify whether it is a data error, an incomplete business rule, or a table mixing multiple versions/points in time. Do not "fix" the business logic on your own by adding columns to the key without evidence.

## 7. From Functional Dependencies to a Physical Schema

The combined table causes the same `customer_name` and `product_name` to appear multiple times. If a customer name changes, multiple rows must be updated; if the last order line for a product is deleted, product information can be lost. These are **update, insertion, and deletion anomalies** caused by storing information at the wrong grain.

A relational design that fits the dependencies and assumptions stated above:

~~~sql
CREATE TABLE customers (
    customer_id   VARCHAR(30) PRIMARY KEY,
    customer_name VARCHAR(200) NOT NULL
);

CREATE TABLE products (
    product_id   VARCHAR(30) PRIMARY KEY,
    product_name VARCHAR(200) NOT NULL
);

CREATE TABLE orders (
    order_id    VARCHAR(30) PRIMARY KEY,
    order_date  DATE NOT NULL,
    customer_id VARCHAR(30) NOT NULL REFERENCES customers(customer_id)
);

CREATE TABLE order_items (
    order_id           VARCHAR(30) NOT NULL REFERENCES orders(order_id),
    line_no            INTEGER NOT NULL CHECK (line_no > 0),
    product_id         VARCHAR(30) NOT NULL REFERENCES products(product_id),
    quantity           INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_at_sale DECIMAL(12, 2) NOT NULL CHECK (unit_price_at_sale >= 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

This schema expresses:

| Dependency / rule | How it is represented |
|---|---|
| `customer_id → customer_name` | `customers.customer_id` is the primary key |
| `product_id → product_name` | `products.product_id` is the primary key |
| `order_id → order_date, customer_id` | `orders.order_id` is the primary key |
| `(order_id, line_no) → product_id, quantity, unit_price_at_sale` | Composite primary key of `order_items` |
| A line item must belong to an order and reference a real product | Foreign keys in `order_items` |
| Quantity must be positive, price non-negative | `CHECK` constraints |

**Do not** add `UNIQUE(order_id, product_id)`, because the business rules allow the same product to appear on multiple lines within the same order. **Do not** place the sale-time price in `products`, because the same product can be sold at multiple prices.

Functional dependencies help identify **partial** and **transitive** dependencies that must be addressed when advancing to 2NF and 3NF. For BCNF, the requirement is stronger: in every non-trivial functional dependency \(X \rightarrow Y\), \(X\) must be a superkey. However, functional dependencies themselves **do not replace** foreign keys, domain constraints, cardinality rules, or existence conditions. Nor can a dependency whose left-hand side is not a key be properly enforced simply by arbitrarily slapping `UNIQUE` onto the left-hand side; entity decomposition and table design must be revisited.

Beyond the relational model, thinking in terms of "which attribute determines which attribute, within what scope" is also useful when choosing document keys, designing nodes/edges in a graph, or defining the grain of analytical tables. Those data systems have different constraint mechanisms; you should not assume all SQL constraints are supported.

## 8. Self-Check Exercises

**Exercise 1.** The operations team confirms: "Each invoice has one issue date; each invoice has multiple lines; line numbers are unique only within an invoice." Consider `HOA_DON(invoice_id, issue_date, line_no, item_id, qty)`, where each line determines one item and quantity. Write the guaranteed dependencies and identify the key.

<details>
<summary>Suggested Answer</summary>

- `invoice_id → issue_date`.
- `(invoice_id, line_no) → item_id, qty`.
- `(invoice_id, line_no)` is a candidate key under the given rules.
- Do not infer `line_no → item_id` or `invoice_id → item_id`.

</details>

**Exercise 2.** "Within each store, each item SKU has one current display name; two stores may use the same SKU for two different products." Can we write `sku → display_name`?

<details>
<summary>Suggested Answer</summary>

No. The appropriate dependency is `(store_id, sku) → display_name` within the scope of current data, assuming each SKU corresponds to only one name within a store.

</details>

**Exercise 3.** A table has two rows with the same `product_id = SP01` but `unit_price_at_sale` values of 6000 and 6500 respectively. What can be concluded?

<details>
<summary>Suggested Answer</summary>

This is a counterexample refuting `product_id → unit_price_at_sale` on the relation containing those transactions. It does not refute `product_id → product_name`, nor does it prove `(product_id, order_date) → unit_price_at_sale`; a single day can still have multiple prices.

</details>

## 9. Checklist Before Finalizing the Model

- [ ] Accurately described what each row of the relation represents.
- [ ] Every dependency is backed by a confirmed business rule, not just sample data.
- [ ] Clarified identifier scope, effective time, and how historical data is stored.
- [ ] Tested counterexamples, checked the reverse direction, and removed redundant attributes on the left-hand side.
- [ ] Computed closures to identify superkeys and candidate keys.
- [ ] Reviewed partial dependencies, transitive dependencies, data anomalies, and normalization needs.
- [ ] Mapped the rules to keys, foreign keys, `UNIQUE`, `CHECK`, or other control logic aligned with the business rules.

**Takeaway:** Deriving functional dependencies is the process of clarifying **what must hold true for all valid data**. Mathematical inference is only trustworthy when the input dependencies come from accurate business rules with clearly defined scopes.
