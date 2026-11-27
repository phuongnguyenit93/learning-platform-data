# Total or Partial Specialization

In data modeling, **specialization** is the representation of a general entity group (*supertype*, parent type) through more detailed groups (*subtypes*, child types). A crucial business question is:

> Must **every** entity of the supertype belong to **at least one** of the listed subtypes?

- **Total specialization:** every entity of the supertype must belong to **at least one** subtype.
- **Partial specialization:** an entity of the supertype **is allowed to belong to none** of the subtypes in the group.

This decision governs the ability to store unclassified states, key and constraint design, data entry workflows, update operations, and schema evolution. Within the **DATABASE_DATA_MODELING** module, the goal goes beyond drawing an ER diagram: requirements must be translated into verifiable constraints in relational, document, graph, or analytical systems while remaining easy to extend.

## 1. Business Intuition: "Must Have a Type" or "May Not Have a Type Yet"?

### Example 1: Completed Payments — Total

Suppose the system accepts only two forms of **completed payment**:

- **CardPayment:** payment by card.
- **BankTransferPayment:** payment by bank transfer.

Under this policy, **each completed payment** must belong to CardPayment or BankTransferPayment. There cannot be a completed payment without knowing which of the two defined forms was used. This is **total specialization**.

The "completed" qualifier matters greatly: a newly created payment request may not have a method selected yet. If the supertype represents **all payment requests, including drafts**, the total rule may no longer hold.

### Example 2: Employees and Special Roles — Partial

An HR system manages all employees (**Employee**), among whom only some are:

- **Manager:** authorized to approve team budgets.
- **SalesRepresentative:** assigned a sales quota.

Engineering or operations staff may belong to **neither** of these two groups. That is valid and does not mean the record is missing data. The Manager/SalesRepresentative classification group is **partial specialization**.

Whether one person can simultaneously be a Manager and a SalesRepresentative is a **separate** question related to disjointness/overlapping; it does not by itself determine total/partial completeness.

| Question | Completed Payments | Employees |
| --- | --- | --- |
| Supertype | Payment | Employee |
| Subtypes under consideration | CardPayment, BankTransferPayment | Manager, SalesRepresentative |
| Can a parent entity belong to no subtype? | No | Yes, e.g., engineering staff |
| Completeness rule | **Total** | **Partial** |
| What the system must enforce | Every Payment must have at least one valid type | An Employee with neither role remains valid |

The core distinction: **total** is a *mandatory classification* requirement, whereas **partial** *allows a parent entity to exist independently of the subtypes under consideration*.

## 2. Set-Theoretic Formulation and Participation Rules

Let **S** be the entity set of the supertype; let **T₁, T₂, …, Tₙ** be the entity sets of the subtypes. Every subtype is a subset of S.

- **Total:** **S = T₁ ∪ T₂ ∪ … ∪ Tₙ**. Every element in S lies in at least one subtype set.
- **Partial:** **T₁ ∪ T₂ ∪ … ∪ Tₙ ⊆ S** and the model **permits** elements of S outside the union of the subtypes. At a specific point in time, the data may happen to contain no elements outside that union.

Expressed in terms of membership cardinality, let **k(x)** be the number of subtypes in the group to which an entity x belongs:

- **Total:** k(x) ≥ 1 for all x in S.
- **Partial:** k(x) ≥ 0; the value 0 is permitted.

Note: this considers only **one specific specialization group**. An entity can participate in specialization group A under a total rule while simultaneously participating in specialization group B under a partial rule. It does not mean all subtypes across the entire system must apply the same rule.

### Completeness Differs from Disjointness/Overlapping

**Total/partial** specifies the **minimum number** of subtypes. **Disjoint/overlapping** specifies the ability to **belong to multiple subtypes simultaneously**.

| Completeness | Combination rule | Valid subtype count per parent entity | State with zero subtypes |
| --- | --- | --- | --- |
| Total | Disjoint | **Exactly 1** | Forbidden |
| Partial | Disjoint | **0 or 1** | Permitted |
| Total | Overlapping | **At least 1** | Forbidden |
| Partial | Overlapping | **0, 1, or more** | Permitted |

For example, an account that **must** be Buyer or Seller but **is permitted to hold both simultaneously** falls under **total + overlapping**. An employee who may hold at most one of two special titles yet may also hold neither is **partial + disjoint**.

In **EER (Enhanced Entity–Relationship)** diagrams, total completeness is typically represented by a **double connecting line** from the supertype to the specialization circle; partial completeness by a **single connecting line**. The specialization circle can be labeled **d** (disjoint) or **o** (overlapping). Notations vary across tools, so model documentation should always state the rule explicitly in prose.

## 3. Determining Totalness Accurately from Requirements

Before creating tables, ask:

1. **Which entity does the supertype represent?** Confirmed transactions, transaction requests, active accounts, or all accounts? Changing the scope can change the constraint.
2. **Are there valid cases that do not belong to any subtype yet?** If so, the specialization must permit that state, or draft states must be cleanly separated from finalized states.
3. **Is the subtype list exhaustive under business policy?** If unmodeled types remain, asserting total completeness can cause data loss or force wrong labels.
4. **Is an entity only temporarily unclassified or permanently exempt from classification?** The two situations may share an initial representation but require different deadline/lifecycle checks.
5. **When does the constraint take effect?** Upon record creation, upon activation, upon approval, upon successful payment, or from a specific effective date?
6. **How is the 0-subtype state verified?** There must be a query or constraint producing results consistent with policy.

A good business statement specifies conditions, scope, and timing:

> "Every payment in the COMPLETED state must have at least one valid CardPayment or BankTransferPayment method. A payment still in the DRAFT state is allowed to have no method yet."

This statement expresses **conditional totalness**, which usually aligns closer to the business than an unqualified "every payment must have a subtype" rule ignoring lifecycle.

**Beware of an OTHER type:** adding an `Other` subtype merely to avoid unclassified records can mask modeling mistakes. `Other` is only a valid subtype if the business genuinely defines and accepts that category with clear meaning, data, and handling rules.

## 4. Mapping to a Single Relational Table

One table for both the supertype and subtypes (*single-table inheritance*) is often the most direct way to represent **total + disjoint**.

### 4.1. Total + Disjoint: Mandatory Discriminator Column

PostgreSQL example:

~~~sql
CREATE TABLE completed_payments (
    payment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    amount     NUMERIC(14, 2) NOT NULL CHECK (amount > 0),
    method     TEXT NOT NULL
               CHECK (method IN ('CARD', 'BANK_TRANSFER')),
    card_token TEXT,
    transfer_reference TEXT,
    CONSTRAINT payment_details_match_method CHECK (
        (method = 'CARD'
            AND card_token IS NOT NULL
            AND transfer_reference IS NULL)
        OR
        (method = 'BANK_TRANSFER'
            AND transfer_reference IS NOT NULL
            AND card_token IS NULL)
    )
);
~~~

The **NOT NULL** constraint on `method` together with the value-list **CHECK** ensures each payment has **at least one** type. A single-valued `method` column simultaneously makes the types **disjoint**. The second constraint prevents subtype-specific data from being written under the wrong type.

~~~sql
-- Valid: belongs to exactly one type with matching specific data.
INSERT INTO completed_payments
    (amount, method, transfer_reference)
VALUES
    (125000, 'BANK_TRANSFER', 'BANK-2026-001');

-- Invalid: completed payment has no method yet.
INSERT INTO completed_payments (amount)
VALUES (125000);

-- Invalid: CARD type but has bank transfer data.
INSERT INTO completed_payments
    (amount, method, transfer_reference)
VALUES
    (125000, 'CARD', 'BANK-2026-002');
~~~

Note that in PostgreSQL, a **CHECK** expression is violated when it evaluates to **FALSE**, whereas **UNKNOWN/NULL** is accepted. Therefore, **NOT NULL** and **IS NULL / IS NOT NULL** checks must be explicitly defined; do not rely on a comparison with NULL to enforce totalness.

### 4.2. Partial + Disjoint: Nullable Discriminator Column

Suppose we model the special role group Manager/SalesRepresentative, where an employee is allowed to hold neither role and, under **this example's specific assumption**, cannot hold both simultaneously:

~~~sql
CREATE TABLE employees (
    employee_id  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    display_name TEXT NOT NULL,
    special_role TEXT
                 CHECK (special_role IN ('MANAGER', 'SALES_REP')),
    approval_limit NUMERIC(14, 2),
    sales_region   TEXT,
    CONSTRAINT employee_role_details CHECK (
        (special_role IS NULL
            AND approval_limit IS NULL
            AND sales_region IS NULL)
        OR
        (special_role = 'MANAGER'
            AND approval_limit IS NOT NULL
            AND approval_limit >= 0
            AND sales_region IS NULL)
        OR
        (special_role = 'SALES_REP'
            AND approval_limit IS NULL
            AND sales_region IS NOT NULL)
    )
);
~~~

~~~sql
-- An employee belonging to neither subtype is still valid.
INSERT INTO employees (display_name)
VALUES ('Lan - Operations Engineer');

-- Employee with the Manager role.
INSERT INTO employees
    (display_name, special_role, approval_limit)
VALUES
    ('Minh - Manager', 'MANAGER', 50000000);
~~~

Here, **special_role IS NULL** means "does not belong to any of the subtypes under consideration". It **does not necessarily mean unknown or missing input data**. Distinguish three meanings that may exist in the business: **not applicable**, **unknown**, and **undetermined**. If the system needs to distinguish them, do not collapse all three into a single NULL; add an explicit classification status if needed.

A single discriminator column fits only **disjoint** groups. If an employee is allowed to be both Manager and SalesRepresentative, the representation must change so both roles can be stored simultaneously.

### 4.3. Total Only in Specific Business States

For entities with a lifecycle, you can allow no classification while in draft, while requiring classification upon activation:

~~~sql
CREATE TABLE payment_requests (
    request_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    state      TEXT NOT NULL
               CHECK (state IN ('DRAFT', 'COMPLETED')),
    method     TEXT
               CHECK (method IN ('CARD', 'BANK_TRANSFER')),
    CONSTRAINT completed_needs_method CHECK (
        state <> 'COMPLETED' OR method IS NOT NULL
    )
);
~~~

When created as DRAFT, `method` can be NULL. Before transitioning to COMPLETED, the database requires `method` to be non-NULL. To enforce *all* payment rules, additional constraints on amounts, method-specific details, and state transitions are also required; the example above intentionally illustrates only the **onset of totalness**.

## 5. Parent–Child Table Mapping: Easy for Partial, Hard to Enforce Total

Each subtype is stored in its own table, using its primary key also as a foreign key to the parent table (*class-table inheritance*). Example of a **partial + overlapping** special employee group:

~~~sql
CREATE TABLE staff (
    staff_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name     TEXT NOT NULL
);

CREATE TABLE staff_managers (
    staff_id       BIGINT PRIMARY KEY
                   REFERENCES staff(staff_id) ON DELETE CASCADE,
    approval_limit NUMERIC(14, 2) NOT NULL
                   CHECK (approval_limit >= 0)
);

CREATE TABLE staff_sales_reps (
    staff_id     BIGINT PRIMARY KEY
                 REFERENCES staff(staff_id) ON DELETE CASCADE,
    sales_region TEXT NOT NULL
);
~~~

The structure above allows:

- A staff member existing with **no** row in either child table → valid under **partial**.
- A staff member having a row in **one** child table → valid.
- A staff member having rows in **both** child tables → valid under the **overlapping** assumption.
- No child table row referencing a non-existent staff member → enforced by foreign keys.

The `staff_id` primary key in each child table ensures an employee has at most one profile of the same subtype.

### 5.1. Why Are Standard Foreign Keys Insufficient for Totalness?

Suppose two child tables `card_payments` and `bank_transfer_payments` both reference the `payments` table.

~~~sql
-- Diagnose data violating total completeness.
SELECT p.payment_id
FROM payments AS p
WHERE NOT EXISTS (
    SELECT 1 FROM card_payments AS c
    WHERE c.payment_id = p.payment_id
)
AND NOT EXISTS (
    SELECT 1 FROM bank_transfer_payments AS b
    WHERE b.payment_id = p.payment_id
);
~~~

The query finds **parent payments that have no subtype record at all**. A foreign key from child table to parent table only checks **child must have a parent**; it does **not** check the reverse direction **parent must have a child**.

This is also why a cross-table `NOT EXISTS` query cannot be turned into a simple **single-row CHECK** in PostgreSQL. When totalness is a hard requirement, you must proactively choose an enforcement mechanism:

1. **Restructure so the constraint sits on a single row**, such as the `completed_payments` table with `method NOT NULL` and subtype fields under a `CHECK`. This is usually the easiest option to maintain for small, disjoint hierarchies.
2. **Write parent and child within a single transaction**, paired with a constraint mechanism checking state when the transaction completes. In PostgreSQL, **DEFERRABLE constraint triggers** can be used when cross-table checks are required; trigger design must account for inserts, updates, deletes, and concurrent operations.
3. **Use bidirectional foreign key structures** or another mechanism ensuring a minimum of one child record, with well-defined handling for circular locks and writes. This is a complex design and must be evaluated per DBMS.
4. **Define the parent table as a derived set (VIEW)** over concrete type tables when appropriate, instead of allowing standalone parent records to be created. Shared identity, foreign keys to the general entity, and updatability through the view must be addressed; a plain `UNION` does not automatically enforce all constraints.

Having the application "always try to write both parent and child" may cover the normal path but is **not yet a complete data constraint**, since data import scripts, background jobs, or other systems can still write a parent without a child.

### 5.2. Controlling Updates/Deletes and Concurrent Transactions

Even when data is valid after an `INSERT`, **deleting the last child record** can break totalness. Checks are needed not only when creating a parent, but also when updating types, switching types, deleting subtypes, and changing statuses.

If cross-table verification relies solely on "read then write" without synchronization, two concurrent transactions can observe a different state than what exists after commit. Consider appropriate row locks on the parent record, data-layer managed constraints, and end-of-transaction checking. Do not assume a naive existence-checking trigger solves all race conditions.

## 6. Total + Overlapping: At Least One Required, Multiple Permitted

This case is easily confused with "must be exactly one type". For example, every member of a platform must hold at least one status—**BUYER** or **SELLER**—but a person can hold both.

If there are only a few stable roles, you can represent them in one table to enforce the **at least one** constraint:

~~~sql
CREATE TABLE platform_members (
    member_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email     TEXT NOT NULL UNIQUE,
    is_buyer  BOOLEAN NOT NULL DEFAULT FALSE,
    is_seller BOOLEAN NOT NULL DEFAULT FALSE,
    buyer_tier TEXT,
    shop_name  TEXT,
    CONSTRAINT at_least_one_membership CHECK (
        is_buyer OR is_seller
    ),
    CONSTRAINT buyer_data_consistent CHECK (
        (is_buyer AND buyer_tier IS NOT NULL)
        OR
        (NOT is_buyer AND buyer_tier IS NULL)
    ),
    CONSTRAINT seller_data_consistent CHECK (
        (is_seller AND shop_name IS NOT NULL)
        OR
        (NOT is_seller AND shop_name IS NULL)
    )
);
~~~

~~~sql
-- Valid: this member participates in both capacities.
INSERT INTO platform_members
    (email, is_buyer, is_seller, buyer_tier, shop_name)
VALUES
    ('member@example.test', TRUE, TRUE, 'SILVER', 'Member Shop');

-- Rejected because the member has no capacity.
INSERT INTO platform_members (email)
VALUES ('unclassified@example.test');
~~~

Advantage: checking for at least one role sits on a single row, so a `CHECK` expression works directly. Drawback: adding a new subtype may force adding columns, expanding `CHECK` constraints, and changing related queries; the table also becomes unwieldy when roles carry many specific attributes.

If roles may grow or carry large sets of specific attributes, a **member_roles table** or **child profile tables** are better suited to store overlapping data. However, with a multi-table model, an independent solution is still needed to enforce **at least one** role. A `UNIQUE` constraint or composite primary key `(member_id, role_code)` only prevents **duplicating a single role**; it does not automatically guarantee **that a role exists**.

### Partial + Overlapping

This is the opposite variant: 0, 1, or multiple memberships are permitted. In a role model, a parent table and a `member_roles` junction table with a composite primary key suffice; newly registered users with no roles remain valid. When the business requires transitioning from **PENDING** to **ACTIVE**, a separate totalness rule can be applied to the ACTIVE state rather than across the entire lifecycle.

## 7. Totalness Rules in Multi-Level Hierarchies

A system can have multi-layer hierarchies:

~~~text
Asset
├── TangibleAsset
│   ├── Vehicle
│   └── Building
└── IntangibleAsset
~~~

We might state:

- Every **Asset** must be a **TangibleAsset** or an **IntangibleAsset** → specialization from Asset is **total**.
- A **TangibleAsset** might be neither a **Vehicle** nor a **Building** (e.g., machinery) → specialization from TangibleAsset is **partial**.

The two statements do not contradict each other. Totalness **must be evaluated at each specialization point** and based on the **direct** subtype set of that point.

If the requirement is "every tangible asset must be a Vehicle or a Building", you must confirm that machinery, equipment, and other tangible assets are already modeled according to policy. You cannot infer from the parent Asset branch being total that every lower-level branch is also total.

An entity can also participate in multiple parallel classifications, such as Asset by **asset nature** and Asset by **intended use**. Total/partial must be determined **for each group** rather than applying one blanket totalness property to the entire entity.

## 8. Relationship with Normalization, Keys, and Indexes

Completeness constraints and normalization solve two different problems:

- **Normalization:** places attributes correctly according to functional dependencies, reducing redundancy and update anomalies.
- **Total/partial completeness:** defines the set of valid states, specifically whether parent rows without subtype information are permitted.

A schema can be well-normalized with separate parent–child tables and still **violate a totalness requirement** due to missing existence checks in child tables. Conversely, a single table with a NOT NULL discriminator can enforce totalness yet accumulate many nullable columns when each subtype has a large attribute set.

Regarding keys and indexes:

- The supertype needs a durable identity key. A subtype's primary key is usually the foreign key to the supertype to preserve a one-to-one relationship per type.
- Indexes on subtype primary keys support **EXISTS/NOT EXISTS** queries for diagnosing completeness.
- If the application filters heavily by classification status or payment method, consider indexes tailored to **actual queries**; a NOT NULL constraint does not automatically make type-filtering queries fast.
- For a subtype junction table, the composite key typically uses `(parent_id, subtype_code)`. If querying by `subtype_code` to fetch many `parent_id` values is frequent, an inverted index `(subtype_code, parent_id)` may be needed.

Do not duplicate an "is_specialized" flag in the parent table while simultaneously using child record existence as the source of truth, unless a mechanism keeps both representations strictly consistent.

## 9. Expressing the Same Rule in Document, Graph, and Analytical Models

Completeness rules are **data semantics**, not a feature unique to relational databases.

| Model | Total | Partial | Things to watch |
| --- | --- | --- | --- |
| **Relational** | Discriminator NOT NULL or subtype existence constraint | Parent type can exist without child rows | CHECK only validates single-row data; cross-table totalness requires additional mechanisms |
| **Document** | Require classification field or at least one valid subtype structure via JSON Schema/validation | Allow documents without subtype extension blocks | Distinguish missing fields, NULL fields, and empty lists; validate state-dependent logic |
| **Graph** | Parent node must have at least one corresponding subtype label/relationship | Parent node may lack subtype labels/edges | Do not assume the DB auto-enforces "at least one edge"; use write policies or suitable constraints |
| **Analytical data warehouse** | Every event/object belongs to at least one valid group in dimension/bridge | May belong to none of the currently specialized groups | Distinguish "unassigned", "not applicable", "unknown"; avoid metric duplication in overlapping models |

Example document representing a fully classified payment:

~~~json
{
  "paymentId": 2201,
  "state": "COMPLETED",
  "method": "CARD",
  "card": {
    "token": "tok_example_001"
  }
}
~~~

To enforce totalness, a validator can require `method` for documents in the `COMPLETED` state and validate the method-specific data block. If two structures are disjoint, JSON Schema can use **oneOf** with non-overlapping branch conditions; if the subtype group is allowed to overlap while requiring at least one, **anyOf** can be used. Both require clearly defining which properties make a document satisfy each branch.

For analytical data, do not automatically interpret "belongs to no subtype" as **UNKNOWN**. A partial record can be **business-valid** and simply outside the specialized groups being studied. Mixing that state with missing data distorts data quality ratios or segmentation reports.

## 10. Lifecycle and Temporal Evolution Rules

Many systems follow a rule: upon creation, an entity is allowed to be unclassified; from a certain business milestone onward, classification becomes mandatory.

Example:

~~~text
PaymentRequest[DRAFT]
    └── allowed to have no method yet
              |
              v
PaymentRequest[COMPLETED]
    └── must have at least one valid method
~~~

There are two important approaches:

1. **Apply conditional totalness by status** using a constraint like the `payment_requests` example. The system keeps the same identity across states.
2. **Separate entity types** if drafts and completed objects have significantly different lifecycles, keys, responsibilities, or constraints; for instance, `PaymentRequest` turns into `CompletedPayment` upon completion.

In both approaches, agree on what happens when changing status or removing a type. Switching a Payment from CARD to BANK_TRANSFER should not leave stale old subtype data behind; if updated across multiple steps, atomicity and constraint-checking timing must be managed.

If querying classification **at a historical point in time** is required, storing only the current subtype is insufficient. A history table with `effective_from`/`effective_to` may be needed along with clear definitions of totalness over closed intervals or at approval milestones. Do not infer a past totalness violation solely from current state.

## 11. Validating Model and Data Quality

From the business rules, write a test matrix before choosing a structure:

| Case | Total + disjoint | Partial + disjoint | Total + overlapping | Partial + overlapping |
| --- | --- | --- | --- | --- |
| 0 subtypes | **Reject** | Allow | **Reject** | Allow |
| 1 subtype | Allow | Allow | Allow | Allow |
| 2 concurrent subtypes | **Reject** | **Reject** | Allow | Allow |
| Delete last subtype | **Reject** | Allow | **Reject** | Allow |
| Missing mandatory subtype attribute | Reject | Reject if that subtype is applied | Reject | Reject if that subtype is applied |

Each real design should also test:

- **Creating parent entity:** is creating it before a subtype allowed or must both happen in the same transaction?
- **State transitions:** is updating from DRAFT to ACTIVE/COMPLETED without a subtype blocked?
- **Deleting/updating subtype:** does removing the last child record break the constraint?
- **Overlapping:** if rules allow 2 subtypes, can the database store and read both?
- **Concurrent writes:** can two transactions changing membership leave an out-of-policy state?
- **Identity:** does deleting or adding a subtype alter the supertype's identity key?
- **Historical data:** is classification needed point-in-time or only current state?

A useful quality indicator when auditing data is the **count of parent entities lacking a subtype**. In a partial model, that can be a normal operational metric. In a total model, it is an anomaly requiring investigation or an invariant that must equal 0:

~~~sql
-- Example on the staff tables from section 5:
SELECT COUNT(*) AS staff_without_special_role
FROM staff AS s
WHERE NOT EXISTS (
    SELECT 1 FROM staff_managers AS m
    WHERE m.staff_id = s.staff_id
)
AND NOT EXISTS (
    SELECT 1 FROM staff_sales_reps AS r
    WHERE r.staff_id = s.staff_id
);
~~~

The same query cannot by itself conclude whether data is "good" or "broken"; the conclusion depends on the **confirmed completeness rule**.

## 12. Common Mistakes

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Thinking total means exactly one subtype | Total only requires **at least one**; overlapping is still possible | Determine disjointness/overlapping independently |
| Thinking partial means no subtypes exist | Partial only **permits** a count of 0 | Still represent and enforce subtypes when applied |
| Assuming an FK from child to parent enforces totalness | A one-way FK does not require parents to have children | Add a completeness enforcement strategy |
| Using a NOT NULL discriminator for valid unclassified drafts | Forces wrong type entry or dummy types | Set conditional constraints by lifecycle |
| Using NULL without defining its meaning | Mixes "not applicable", "unclassified", and "missing data" | Separate states by business semantics |
| Turning an incomplete subtype list into a total model | Other genuinely valid types have nowhere to live | Add missing subtypes or define partial scope |
| Checking totalness only on INSERT | Deleting the last child row still breaks totalness | Check UPDATE, DELETE, and state transitions too |
| Mixing classification constraints with global NOT NULL attributes | Forces non-Manager employees to also have an approval limit | Make required attributes **per subtype** |

## 13. Case Studies with Solutions

**Case A — Product Catalog:** A `Product` table stores phones, laptops, tables/chairs, and food items. Two subtypes are designed: `ElectronicProduct` and `FurnitureProduct`. Each electronic product has a warranty code; each furniture product has a material. Should specialization be set to total?

**Analysis:** With **only the two listed subtypes**, totalness is wrong because valid food Products belong to neither. Choose **partial**, or design an exhaustive subtype group if the business truly wants every Product classified under a covering taxonomy. Do not force food items into Electronics or Furniture just to satisfy a constraint.

**Case B — Support Tickets:** A new Ticket may not be assigned to any team yet; a Ticket in the `ASSIGNED` state must belong to `TechnicalTicket` or `BillingTicket`. A Ticket can belong to only one group at a time.

**Analysis:** The specialization group is **disjoint**. Regarding completeness, a new Ticket **is allowed to have no subtype**; an `ASSIGNED` Ticket must have **exactly one** subtype. A nullable `ticket_type` column can be used together with a condition:

~~~sql
-- Illustrating the constraint when status and ticket_type already exist:
ALTER TABLE support_tickets
ADD CONSTRAINT assigned_ticket_needs_type CHECK (
    status <> 'ASSIGNED' OR ticket_type IS NOT NULL
);
~~~

This constraint assumes the columns already exist and `status` is NOT NULL; additionally, you must verify `ticket_type` only takes valid values along with type-specific details. If a Ticket can return to an unassigned state, confirm whether the business permits clearing previous classification details or requires retaining history.

**Case C — Member Platform:** Every activated member must be a Consumer or a Partner, or both; accounts pending verification may belong to neither type yet.

**Analysis:** This is **overlapping** with **conditional totalness upon activation**. The schema must allow both roles to coexist and block transitioning an account to `ACTIVE` when it has no role. A single type column with two values Consumer/Partner is insufficient because it forbids holding both simultaneously.

### Takeaways When Translating Requirements into Schemas

**Total = every parent entity has at least one subtype. Partial = subtypes are optional for the parent entity.** These two rules govern **completeness**; to know the maximum number of subtypes, you must also consider disjointness vs. overlapping. Only when the model clearly defines **entity, scope, timing, and lifecycle** can we build reliable constraints on tables, keys, indexes, and other storage mechanisms.
