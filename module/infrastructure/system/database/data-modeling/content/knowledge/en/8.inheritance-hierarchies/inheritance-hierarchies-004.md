# Distinguishing IS-A, HAS-A, and PLAYS-A-ROLE Relationships

In data design, the three expressions **"A is a B" (IS-A)**, **"A has a B" (HAS-A)**, and **"A plays the role B" (PLAYS-A-ROLE)** describe three different kinds of business facts. They often appear right next to each other in the same system, yet lead to very different decisions regarding identity, keys, relationships, optionality, lifecycle, and extensibility.

Consider an e-commerce marketplace:

- **DigitalProduct is a Product**: a digital product is a specialized case of a product.
- **SalesOrder has OrderLines**: an order is composed of order lines.
- **AppUser plays the buyer role in SalesOrder**, and can **play the seller role on OrderLine**: one user participates in transactions under different roles.

This is a foundational topic of the **Inheritance and Hierarchies** chapter in the **DATABASE_DATA_MODELING** module: turning business statements into verifiable models, from conceptual diagrams to physical schemas; and distinguishing when to use subtype tables, foreign keys, association tables, and context-scoped constraints.

## 1. Quick Comparison of the Three Relationship Types

| Criterion | IS-A: "is a" | HAS-A: "has a / has many" | PLAYS-A-ROLE: "plays a role" |
| --- | --- | --- | --- |
| Question | Is A a specialized case of B? | Which Bs does A associate with or contain? | In what capacity does A participate in context C? |
| Meaning | Classification, specialization, attribute inheritance | Association, aggregation, composition, ownership depending on domain | Participation capacity, responsibility, or permission in context |
| Example | DigitalProduct is a Product | Order has OrderLine | User is the buyer of Order |
| Identity | Subtype inherits the **same entity identity** as the supertype | The two sides are usually **two entities** or an entity and a value component | **One principal** can hold multiple roles across transactions, groups, and points in time |
| Common relational mapping | Discriminator or parent–child tables sharing a key | Foreign key, junction table, sometimes embedded components in the same table | Role-named foreign key, scoped and time-bounded role assignment table |
| Common mistake | Using IS-A merely because things "are related" | Assuming every HAS-A requires cascading deletes | Turning a temporary role into a fixed entity type |

A quick test: **if every object A can be called a B while keeping the same object and identity**, it may be IS-A. **If A and B are distinct objects linked together**, it is usually HAS-A or a general association. **If A holds capacity B only while participating in an activity or context**, consider PLAYS-A-ROLE.

These tests help spot plausible models, but **do not replace confirming business rules**. A term like "Customer" may be a fixed customer type in one system, a transactional role in another, or a user profile with its own state.

## 2. IS-A: Generalization and Specialization Relationships

**IS-A** describes a relationship between a **supertype** (parent type) and a **subtype** (child type). Every entity belonging to a subtype also belongs to the supertype. The subtype shares the parent's identity and common attributes, and may have its own attributes, rules, and behaviors.

Business example:

> "Every DigitalProduct is a Product, having a shared product ID, title, and selling price; DigitalProduct also has a downloadable resource URL."

Here:

- Product is the supertype, DigitalProduct is the subtype.
- A DigitalProduct record and its Product record represent **the same product**, not two linked products.
- Relationships applying to Product, such as OrderLine referencing Product, must also work with DigitalProduct.
- A specialized case can have its own constraints, for instance the download URL must not be empty.

This is the meaning of **substitutability**: wherever the system needs to reference a Product, a DigitalProduct object is also a valid Product. In data modeling, do not interpret this as a promise about source-code inheritance; **inheritance in programming and entity specialization in a database do not necessarily share the same structure**.

### 2.1. IS-A Is More Than Just Two Tables with a Foreign Key

Consider:

~~~text
Product (product_id)
    ^
    | IS-A: same product_id
    |
DigitalProduct (product_id, download_url)
~~~

DigitalProduct's key can simultaneously be a foreign key to Product. It states "this child record elaborates **that very same product**". In contrast, OrderLine has its own key and references `product_id` because it is **a transaction line distinct from the product**; OrderLine is not a subtype of Product.

If two tables are used to represent IS-A, a one-to-one relationship between child and parent is still insufficient to enforce all hierarchy rules. You must also determine:

- **Total vs. partial:** must every Product belong to at least one subtype, or is an unspecialized Product permitted?
- **Disjoint vs. overlapping:** is a Product allowed to belong to multiple subtypes simultaneously?
- **Specific attributes:** fields valid only for the corresponding subtype.
- **Shared identity:** is changing subtypes allowed while keeping `product_id`?

An example with **DigitalProduct** and **PhysicalProduct** is disjoint only if the business truly mandates each product belongs to at most one of the two groups. If the business sells hybrid products containing both downloadable content and physical goods, the design may need to allow overlapping or model product bundles via separate components.

### 2.2. When Should You Not Choose IS-A?

The following statements **do not create a subtype relationship merely because they describe an attribute or participation**:

- "User has a shipping address" → relationship between user and address, or value attribute; Address is not a subtype of User.
- "Order has Product" → OrderLine references Product; Product is not a subtype of Order.
- "User is the buyer of an Order" → User participates in Order in the buyer role; Order itself is the context giving the term "buyer" meaning.
- "An employee is currently team lead of project X" → usually a project- and time-scoped role that can be lost or changed without turning the employee into a new object.

Conversely, if the business defines a **Manager** as a specialized Employee type with its own set of attributes and rules, IS-A may be valid. Naming alone does not decide the modeling; decisions must rest on **identity rules, stability, scope, and constraints**.

## 3. HAS-A: Ownership, Containment, or Association Relationships

**HAS-A** describes that an entity **has, consists of, contains, references, or associates with** another entity. These terms are easily conflated, yet lifecycle constraints can differ dramatically.

Example:

> "Each SalesOrder has multiple OrderLines; each OrderLine belongs to exactly one SalesOrder."

If an order contains three product lines, that is **one SalesOrder and three OrderLines**. The lines have their own identity or position within the order, quantity, and unit price at the time of purchase. OrderLine **is not** a kind of SalesOrder; it is a component of the order.

In the conceptual model, specify **cardinality** and **optionality** explicitly:

| Relationship | Cardinality on first side | Cardinality on second side | Interpretation |
| --- | --- | --- | --- |
| SalesOrder – OrderLine | One line belongs to exactly **1** order | One order has **0..N** lines while in draft | Lines can be added after creating a draft |
| OrderLine – Product | One line references **1** product | One product appears in **0..N** lines | Product exists independently of orders |
| AppUser – SalesOrder | One order has exactly **1** buyer | One user buys **0..N** orders | A user's existence does not depend on having placed orders |
| Department – Employee | Depending on policy, an employee may belong to **0..1** primary department | One department has **0..N** employees | Organizational link, not inheritance |

Do not infer that "HAS-A" always implies 1–1 cardinality from the phrase "has a". For instance, "User has a primary address" can coexist with "User has multiple delivery addresses". Always verify exact minimums, maximums, and effective scope.

### 3.1. Association, Aggregation, and Composition

In UML, a distinction is made between:

- **Association:** two objects are related, such as OrderLine referencing Product. Does not necessarily imply ownership or lifecycle dependency.
- **Aggregation:** loose whole–part relationship; parts can exist independently and may be shared. The scope of meaning must be stated clearly.
- **Composition:** parts usually depend on the whole and cannot belong to two wholes simultaneously; for example, OrderLine belongs to only one SalesOrder.

**Do not assume composition automatically means ON DELETE CASCADE.** If an order is a financial document that must be retained for years, deleting an order with lines may need to be **rejected** or replaced by archiving/marking as cancelled. Lifecycle dependency is a **business rule**; physical deletion behavior is a separate decision.

In ER/relational modeling, many HAS-A cases are implemented via **foreign keys**. Many-to-many relationships use **junction tables**. Small value components without independent identity are sometimes appropriate to store in the same row or embed in a document.

### 3.2. Example Distinguishing Product from Order Line

A Product can be purchased across many orders; an Order has many lines; each line records quantity and **the unit price locked at transaction time**. The unit price in OrderLine belongs to that **purchase instance**, so it cannot be replaced by the current price on Product. Storing both the current product price and the transaction price is not necessarily a normalization error: they describe **two facts at different times and contexts**.

This is why OrderLine should be an entity or relational component with its own attributes, rather than just an array of `product_id` values lacking quantity or unit price.

## 4. PLAYS-A-ROLE: Context-Dependent Roles

**PLAYS-A-ROLE** describes the capacity in which **an entity participates in a relationship, activity, organization, or time period**. A role is not necessarily a permanent subtype of the entity.

Example:

> "In order 1001, User A plays the buyer role. In another transaction line, the same User A can play the seller role."

The same User A still uses **one `user_id`**. Having the buyer role does not mean a Buyer entity independent of User is needed; nor does it mean User can only be Buyer or Seller.

### 4.1. Roles Bound to a Relationship

In the relational model, foreign key naming is often how roles are recorded:

- **SalesOrder.buyer_user_id** → User participates in SalesOrder in the buyer role.
- **OrderLine.seller_user_id** → User participates in a transaction line in the seller role.
- **Task.assignee_user_id** and **Task.reporter_user_id** → the same User table participates in Task under two roles; one person may hold both if business rules allow.

An event can have **multiple participating roles** and **one entity can assume multiple roles**, depending on constraints. Do not automatically add a CHECK preventing `buyer` and `seller` from having the same `user_id` just because the role names differ; add that condition only when an explicit anti-self-trading policy exists.

### 4.2. Roles Bound to Organizations, Time, or Permissions

Not every role needs only a single foreign key column. For instance, a User holds the **EDITOR** role in Workspace A but is a **VIEWER** in Workspace B; roles change over time and can coexist.

In that case, use a role assignment relation with **at least three components**:

~~~text
RoleAssignment(
    user_id,
    workspace_id,
    role_code,
    valid_from,
    valid_to,
    ...role assignment attributes
)
~~~

The identity of a role assignment can be an appropriate composite key or surrogate key. You must decide whether one person can hold multiple roles in the same workspace, whether two overlapping effective intervals for the same role are permitted, and whether history must be retained upon role revocation.

**Transaction participation role** and **permission to perform a transaction** also differ. A User appearing in OrderLine as seller is a historical fact; current selling eligibility may be governed by a verification profile and account status. Do not use "has sold before" as proof that the User is currently authorized to sell.

### 4.3. When Can a Role Become a Subtype?

A role *can* be represented as a subtype if the business genuinely builds a specialization with its own data and invariants, such as a **SellerAccount** with identity verification records, tax ID, and an approval workflow. However, you must answer:

1. Does `SellerAccount` share the same identity as `AppUser`, or is it a separate profile entity?
2. Can an `AppUser` simultaneously have a `BuyerProfile` and a `SellerProfile`?
3. Can a User stop being a Seller while still retaining historical sold orders?
4. Does the role apply system-wide or per store, group, or transaction?

If the rule depends on **a relationship or context**, a role assignment table usually expresses it more accurately than trying to force a `User → Buyer → Seller` hierarchy.

## 5. A Scenario Combining All Three Relationship Types

Design a system selling digital and physical products under these assumptions:

- Every Product is classified into **exactly one** of two groups: DIGITAL or PHYSICAL.
- A SalesOrder has one buyer and can be in the DRAFT state before having lines.
- An OrderLine belongs to exactly one SalesOrder, referencing exactly one Product and one seller.
- An AppUser can participate in many orders, both buying and selling across different transactions.

Simplified conceptual diagram:

~~~mermaid
flowchart LR
    DP["DigitalProduct"] -->|"IS-A"| P["Product"]
    PP["PhysicalProduct"] -->|"IS-A"| P
    O["SalesOrder"] -->|"HAS-A: many lines"| L["OrderLine"]
    L -->|"references"| P
    U["AppUser"] -->|"plays buyer role"| O
    U -->|"plays seller role"| L
~~~

IS-A arrows indicate specialization; the HAS-A arrow indicates a whole–part relationship; the two arrows from AppUser show **relationship participation roles**. The diagram conveys only primary semantics; cardinalities and optionality are explicitly defined in the DDL below.

### 5.1. Illustrative SQL Schema (PostgreSQL)

The example uses **a single Product table with a discriminator** to store a small, disjoint hierarchy. The BUYER/SELLER roles are expressed directly on the business relationships; `OrderLine` is a separate component table.

~~~sql
-- User identity is unique regardless of participated roles.
CREATE TABLE app_users (
    user_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email   TEXT NOT NULL UNIQUE
);

-- IS-A: same product_id; only one product kind in this example.
CREATE TABLE products (
    product_id  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title       TEXT NOT NULL,
    kind        TEXT NOT NULL
                CHECK (kind IN ('DIGITAL', 'PHYSICAL')),
    download_url TEXT,
    weight_grams INTEGER,
    CONSTRAINT product_details_match_kind CHECK (
        (kind = 'DIGITAL'
            AND download_url IS NOT NULL
            AND weight_grams IS NULL)
        OR
        (kind = 'PHYSICAL'
            AND download_url IS NULL
            AND weight_grams IS NOT NULL
            AND weight_grams > 0)
    )
);

-- PLAYS-A-ROLE: buyer_user_id points to User in the buyer role.
CREATE TABLE sales_orders (
    order_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    buyer_user_id  BIGINT NOT NULL
                   REFERENCES app_users(user_id),
    status         TEXT NOT NULL DEFAULT 'DRAFT'
                   CHECK (status IN ('DRAFT', 'CONFIRMED', 'CANCELLED')),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- HAS-A: OrderLine belongs to SalesOrder.
-- PLAYS-A-ROLE: seller_user_id is the seller of the order line.
CREATE TABLE order_lines (
    order_id       BIGINT NOT NULL REFERENCES sales_orders(order_id),
    line_no        INTEGER NOT NULL CHECK (line_no > 0),
    product_id     BIGINT NOT NULL REFERENCES products(product_id),
    seller_user_id BIGINT NOT NULL REFERENCES app_users(user_id),
    quantity       INTEGER NOT NULL CHECK (quantity > 0),
    unit_price     NUMERIC(14, 2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

Explanation of notable design decisions:

| Design element | Business rule expressed | Primary mechanism |
| --- | --- | --- |
| `products.kind` | Every Product belongs to exactly one group under consideration | NOT NULL, CHECK, validating type-specific fields |
| `order_lines.order_id` | Each line must belong to an existing order | FK + NOT NULL; composite key prevents duplicate `line_no` within an order |
| `order_lines.product_id` | Line references an independent product | FK; Product can appear in many lines |
| `sales_orders.buyer_user_id` | User plays the buyer role for the Order | FK to `app_users`; no separate Buyer table needed |
| `order_lines.seller_user_id` | User plays the seller role on the OrderLine | FK to `app_users`; same User can buy and sell |
| `order_lines.unit_price` | Price at transaction time | Line attribute, not using current Product price |

**Limitation to note explicitly:** The schema permits an Order in the `CONFIRMED` state to have **0 order lines**, because the FK from `OrderLine` to `Order` does not check the reverse direction. If the business requires a confirmed order to have at least one line, enforcement must be added at confirmation time via transactional workflows and an appropriate data verification mechanism (for example, a deferred constraint trigger in PostgreSQL). Deleting the last line of a confirmed order must also be guarded; checking only at order creation is insufficient.

The example also does not yet enforce **valid selling eligibility** of `seller_user_id`; if only verified sellers may sell, a separate profile/relation and verification constraint are required. The foreign key to `app_users` only confirms the seller **exists**, not that they are **eligible**.

### 5.2. Querying to See the Different Meanings

Fetching order lines along with product and seller:

~~~sql
SELECT o.order_id,
       o.buyer_user_id,
       l.line_no,
       l.quantity,
       l.unit_price,
       p.product_id,
       p.kind,
       p.title,
       l.seller_user_id
FROM sales_orders AS o
JOIN order_lines AS l ON l.order_id = o.order_id
JOIN products AS p ON p.product_id = l.product_id
WHERE o.order_id = 1001
ORDER BY l.line_no;
~~~

The `JOIN` between `Order` and `OrderLine` represents **HAS-A**; the `JOIN` to `Product` represents **the line referencing a product**; the names `buyer_user_id` and `seller_user_id` record **roles**. The `products.kind` value distinguishes **IS-A** `DigitalProduct`/`PhysicalProduct` in a single-table design.

Finding Users who have participated in **both roles**, while still returning each User only once:

~~~sql
SELECT u.user_id, u.email
FROM app_users AS u
WHERE EXISTS (
    SELECT 1
    FROM sales_orders AS o
    WHERE o.buyer_user_id = u.user_id
)
AND EXISTS (
    SELECT 1
    FROM order_lines AS l
    WHERE l.seller_user_id = u.user_id
);
~~~

Using `EXISTS` instead of joining the two transaction lists avoids multiplying result rows when a User has many purchased orders and many sold lines. **A User holding both roles does not mean an order is self-bought and self-sold**; the two relationships may belong to different transactions.

### 5.3. Indexes Supporting the Relationships

Primary keys automatically create indexes on `product_id`, `user_id`, `order_id`, and `(order_id, line_no)`. However, in PostgreSQL, creating **a foreign key on the referencing table does not automatically create an index on that table's FK column**. If queries by buyer, seller, or product are needed, consider:

~~~sql
CREATE INDEX idx_sales_orders_buyer
    ON sales_orders (buyer_user_id, order_id);

CREATE INDEX idx_order_lines_seller
    ON order_lines (seller_user_id, order_id);

CREATE INDEX idx_order_lines_product
    ON order_lines (product_id);
~~~

The index on `(order_id, line_no)` already supports querying lines by order. Additional indexes should be based on actual queries and data volumes; do not assume every foreign key needs the same kind of index.

## 6. When Roles Need a Context-Scoped Association Table

Another example is users participating in a **Workspace** with the `EDITOR` or `VIEWER` role. Do not create independent `UserEditor` and `UserViewer` entities if the same person can hold different roles across multiple workspaces.

~~~sql
CREATE TABLE workspaces (
    workspace_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workspace_name TEXT NOT NULL
);

CREATE TABLE workspace_role_assignments (
    user_id       BIGINT NOT NULL REFERENCES app_users(user_id),
    workspace_id  BIGINT NOT NULL REFERENCES workspaces(workspace_id),
    role_code     TEXT NOT NULL CHECK (role_code IN ('EDITOR', 'VIEWER')),
    valid_from    TIMESTAMPTZ NOT NULL,
    valid_to      TIMESTAMPTZ,
    CONSTRAINT valid_role_period CHECK (
        valid_to IS NULL OR valid_to > valid_from
    ),
    PRIMARY KEY (user_id, workspace_id, role_code, valid_from)
);
~~~

The `workspace_role_assignments` table models **the relationship among User, Workspace, and role over an effective period**. One User can be `EDITOR` in workspace A, `VIEWER` in workspace B, and change roles while keeping the same `user_id`.

The schema above **allows two concurrent roles in the same workspace** and allows multiple overlapping effective periods for the **same role**. If the business forbids that, an additional constraint on `(user_id, workspace_id, role_code)` and the time period must be added, such as a suitable exclusion constraint or consistent transactional write mechanism. A simple `UNIQUE` on the three columns would block historical role re-grants, so it is unsuitable if roles can be revoked and later re-granted.

The decision "a User in a Workspace has only one active role" differs from "a User can have multiple roles across the entire system". Always attach cardinality limits to a **specific scope**.

## 7. Choosing a Representation When Boundaries Are Unclear

Natural-language statements can be misleading:

| Statement | Possible interpretations | What to confirm |
| --- | --- | --- |
| "Customer is a User" | Customer is a subtype or a purchasing role | Must a User create a separate Customer profile? Can they stop buying while keeping history? |
| "Manager is an Employee" | Manager is a subtype or a role per project/department | Are there long-lived specialized attributes, or is it just a time-bound assignment? |
| "Order has Product" | Direct relationship or via OrderLine | Do we need quantity, unit price, discount, and multiple lines for the same Product? |
| "Account has Address" | Embedded value component, or an Address entity with identity | Can one address be shared? Are address history and address types needed? |
| "Seller sells Product" | Relationship between Seller and Product/Listing, or a role on transaction lines | Can one Product have multiple sellers? Does the Seller vary per Listing? |
| "Vehicle is an Asset" | IS-A hierarchy | Can any Asset be both a Vehicle and another subtype? |

Some situations require **combining two patterns** rather than picking just one of the three labels:

- `SellerProfile` may be a **specialized profile** tied to a User (IS-A or 1–1 relationship depending on identity).
- A User can **play the seller role** in an order line (PLAYS-A-ROLE).
- `SellerProfile` can **have** bank details, address, and verification documents (HAS-A).

Thus, calling someone a "seller" does not by itself prove a `Seller` subtype table is needed. Separate **object identity**, **component structure**, and **participation capacity** before designing tables.

## 8. Impact on Normalization, Keys, Constraints, and Lifecycle

### 8.1. Identity and Keys

- **IS-A:** has one shared entity identity. If using parent–child tables, the subtype's primary key is usually a foreign key to the supertype; no independent duplicate entity is created.
- **HAS-A:** each component/association has a key structure following its own rules. `OrderLine` uses `(order_id, line_no)` because `line_no` is unique only **within one Order**.
- **PLAYS-A-ROLE:** define keys based on **principal + context + role type + point in time** if history is needed. Using only `user_id` as the primary key for role assignments would prevent a User from having multiple roles/contexts.

### 8.2. Normalization and Duplicate Data

Do not create `Buyer` and `Seller` tables duplicating the full name, email, and phone of the same User merely because they hold two roles. Shared identifying information belongs on `AppUser`; role-specific information can live in a profile or role assignment relation.

On the other hand, attributes tied to **an instance of relationship participation** must reside where they originate: `OrderLine` holds `quantity` and `unit_price`; `RoleAssignment` holds `valid_from` and `valid_to`. Pushing them onto `Product` or `User` creates wrong dependencies and leads to update anomalies.

### 8.3. Deletion and State Transitions

- Deleting a `DigitalProduct` must comply with requirements on the parent `Product` and referenced transactions; transitioning to a discontinued state may be needed instead of deleting historical records.
- Deleting an `Order` may be prohibited when financial records must be preserved, even though `OrderLine` is a component of `Order`.
- Revoking `EDITOR` permission does not mean deleting the `User`, nor should `RoleAssignment` history be deleted.
- If changing a `Product` type from `DIGITAL` to `PHYSICAL`, consider how to migrate type-specific attributes, historical transaction data, and business limits. Changing types after sales have occurred may be invalid.

A useful design principle: **entity lifespan, component lifespan, and role validity are three distinct temporal axes**.

### 8.4. Rules Beyond Single-Row CHECK Constraints

A `CHECK` on `Product` can validate `kind` and specific attributes because they sit on **the same row**. However, "every Order in state CONFIRMED has at least one OrderLine", or "the user assigned as seller must hold an active selling license", may require **cross-table** querying and enforcement.

For such rules, you may need design adjustments, atomic transactions, deferred constraint triggers, or consistent validation mechanisms. An FK only verifies existence of the referenced row; it does not automatically express full eligibility, state, or permissions over time.

## 9. The Same Semantics in Document, Graph, and Analytical Data

The three relationship types still exist outside relational databases; the differences lie mainly in representation mechanisms and how constraints are enforced.

| Storage model | IS-A | HAS-A | PLAYS-A-ROLE |
| --- | --- | --- | --- |
| **Relational** | Discriminator or subtype tables sharing key with parent | FK, junction table, component table | Role-named FK or context-scoped role assignment table |
| **Document** | Type field and schema for specific variants | Embed components or use references to independent documents | Store principal ID in a specific role field, or an array of role assignment records |
| **Graph** | Controlled type labels or classification relationships | `HAS_PART`/`CONTAINS`/`REFERENCES` edges | Participation edges with role names and temporal properties |
| **Analytical** | Dimension with clear types/specializations | Detailed fact and appropriate dimensions/bridges | Role of a dimension in each fact or permission/participation bridge |

### Document: Embed Only What Truly Depends on the Parent

An order can store its order lines directly inside the document if they are usually read/updated together with the order and do not need independent sharing:

~~~json
{
  "orderId": 1001,
  "buyerUserId": 7,
  "status": "CONFIRMED",
  "lines": [
    {
      "lineNo": 1,
      "productId": 501,
      "sellerUserId": 18,
      "quantity": 2,
      "unitPrice": 49000
    }
  ]
}
~~~

In this document:

- **lines** is an embedded HAS-A.
- **buyerUserId** and **sellerUserId** indicate roles of the same `User` object type in different contexts.
- **productId** is a reference to an independent `Product`, rather than turning `Product` into a component living and dying with `Order`.
- The `DIGITAL`/`PHYSICAL` kind of `Product` can be stored in the separate `Product` document with a schema validating subtype fields.

Embedding all `User` and `Product` data into every order typically causes duplication and synchronization difficulties. Certain transactional attributes like locked unit price or historical display name may be snapshotted at purchase time for audit requirements; distinguish intentional snapshots from uncontrolled duplication.

### Graph: Classification, Structure, and Capacity Are Different Edges

In a graph model:

- A `Product` node carries a `DigitalProduct` label when representing IS-A with multiple labels (if the model requires it).
- An edge from `Order` to `OrderLine` can carry `CONTAINS` semantics.
- A relationship from `User` to `Order` can represent `BOUGHT`; from `User` to `OrderLine` can represent `SOLD`.
- A relationship from `User` to `Workspace` can hold `role` and effective-period properties.

A label or edge **does not automatically enforce** all subtype, cardinality, temporal, and lifecycle rules. Use technology-supported constraints or enforce them in write workflows.

### Analytics: Avoid Multiplying Metrics Due to Multiple Roles

Suppose a User both buys and sells across many transactions. If a revenue fact table is joined to every `RoleAssignment` of the User without restricting role and effective time, each fact row can be duplicated and total revenue wrongly inflated.

In analytical models, explicitly specify the **grain**: is one fact row **one OrderLine**, one Order, or one payment? Buyer and Seller can be **two foreign keys referencing the same User dimension** (*role-playing dimension*), yet representing two **distinct roles within the same event**. When analyzing permissions over time, JOIN on the exact workspace scope and effective interval.

## 10. Practical Workflow When Reading Business Requirements

You can make decisions in this sequence:

1. **Identify objects and identity:** are A and B the same entity viewed at two abstraction levels, or two distinct entities?
2. **Test the statement "every A is a B":** if true and the subtype has distinct properties, evaluate IS-A. Determine disjointness/overlapping and total/partial before choosing tables.
3. **Check containment/association relationships:** if A has B, determine two-sided cardinality, lifecycle dependency, sharing, and whether relationship attributes must be stored.
4. **Check context-scoped roles:** if A "is B" only while participating in C, ask about context, permissions, timing, single vs. multiple roles, and history.
5. **Choose schema mapping:** discriminator/parent–child tables for IS-A; FK/junction table for HAS-A; role-named FK or role assignment table for PLAYS-A-ROLE.
6. **Write verifiable constraints:** PK/FK, UNIQUE, NOT NULL, CHECK, and cross-table mechanisms if needed; define deletion, update, and state-transition handling.
7. **Test counterexamples:** a User who both buys and sells; a Product appearing in multiple OrderLines; an Order with no lines yet; an expired RoleAssignment; a subtype with invalid attributes.
8. **Evaluate evolution:** does adding subtypes, adding roles, changing cardinality rules, storing history, or changing DBMS require changing identities or duplicating information?

### Self-Check Exercises

**Question 1.** A school manages `Person`, `Student`, and `Teacher`. A `Person` can both study and teach. How should `Student` and `Teacher` be modeled?

**Hint:** If Student/Teacher are **roles within a term/program**, use `Enrollment` and `TeachingAssignment` relations with context and duration. If the business defines `Student` and `Teacher` profiles with distinct attributes and rules, use specialized subtypes/profiles **allowing overlapping**. Either way, do not create two different `Person` records for the same individual.

**Question 2.** Does "Vehicle has an Engine" mean Vehicle IS-A Engine? If an Engine has its own serial ID and can be moved between multiple Vehicles over time, what needs to be stored?

**Hint:** This is **HAS-A**. `Engine` and `Vehicle` have two separate identities. Store an installation relationship with an effective time interval; it can include install date, removal date, and the rule "one engine resides in at most one vehicle at a time". Simply adding an `engine_id` column on `Vehicle` makes retaining full history difficult.

**Question 3.** The system has User A as both the creator and assignee of Task X. Are two tables `CreatorUser` and `AssigneeUser` needed?

**Hint:** Not necessarily. Two foreign keys `creator_user_id` and `assignee_user_id` both pointing to `User` can describe the two **roles**. A `CHECK` forbidding them from being equal is only appropriate if the business prohibits self-assignment.

**Question 4.** A `DigitalProduct` is purchased 100 times. Should 100 `DigitalProduct` records be created to represent the 100 purchases?

**Hint:** No. **DigitalProduct IS-A Product** carries one product identity; the purchases are represented by **OrderLine** or transaction events linking to `product_id`. Separating product identity from transaction entities avoids duplicating attributes and keeps reference keys stable.

## 11. Takeaways

- **IS-A:** an entity is a specialized case of a generalized type, **keeping the same identity**.
- **HAS-A:** entities or components **have a structural/associative relationship**, whose cardinality and lifecycle must be defined.
- **PLAYS-A-ROLE:** an entity **participates in a context in a specific capacity**, can hold multiple roles simultaneously, and can change over time.

Distinguishing these three concepts helps a data model reflect the business accurately, choose the right keys and constraints, avoid duplicating identities, and smoothly translate across relational schemas, documents, graphs, and analytical models as the system grows.
