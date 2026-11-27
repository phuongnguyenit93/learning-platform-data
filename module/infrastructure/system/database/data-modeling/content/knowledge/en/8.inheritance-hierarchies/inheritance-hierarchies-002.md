# Disjoint or Overlapping Subtypes

When translating business requirements into a data model, a generalized entity (*supertype*, or parent type) can be specialized into multiple *subtypes*. The decisive question is not just "what are the subtypes?", but also: **can the same entity belong to multiple subtypes at the same point in time and within the same business scope?**

In the **Inheritance and Hierarchies** chapter of data modeling, the answer creates two very different rules:

- **Disjoint specialization:** each entity belongs to **at most one** subtype in the considered group.
- **Overlapping specialization:** an entity is permitted to belong to **multiple** subtypes in the considered group.

This is a business constraint that must be expressed in the conceptual model, translated accurately into the logical schema, and, when necessary, enforced by the database. Choosing wrongly leads to invalid data, redundant columns, confusing queries, or a design that is hard to evolve.

## 1. Understanding the Rule Through Two Examples

### Example A: Each Order Fulfillment Has Only One Method

Suppose the system specifies that **each order fulfillment** uses only one method:

- **Delivery:** requires a delivery address.
- **Pickup:** requires a pickup location.

A fulfillment record cannot simultaneously be Delivery and Pickup. These are **disjoint subtypes**.

Note that an order can be split into multiple separate fulfillments. In that case, a single order can have both a delivery fulfillment and a store pickup fulfillment; **the disjointness rule still holds at the level of each fulfillment**. Choosing the right entity and scope is essential for stating the constraint accurately.

### Example B: A User Can Both Buy and Sell

A commerce platform allows users to hold the following roles:

- **Buyer:** has information supporting the loyalty program.
- **Seller:** has a shop profile.

The same user can be a Buyer, a Seller, both, or not participate in either role yet. These are **overlapping subtypes**. If users were forced to pick only one type, the system would have to create duplicate accounts or reject a valid business state.

| Entity | Belongs to subtype A | Belongs to subtype B | Valid when disjoint? | Valid when overlapping? |
| --- | --- | --- | --- | --- |
| X | Yes | No | Yes | Yes |
| Y | No | Yes | Yes | Yes |
| Z | Yes | Yes | **No** | Yes |
| W | No | No | Depends on completeness rule | Depends on completeness rule |

Row W shows there is another independent question: must an entity belong to at least one subtype?

## 2. Precise Set-Theoretic Definition

Let \\(S\\) be the set of entities of the supertype; let \\(A, B\\) be the entity sets of two subtypes, with \\(A \\subseteq S\\) and \\(B \\subseteq S\\).

**Disjoint:** \\(A \\cap B = \\varnothing\\). With multiple subtypes, the condition applies to **every pair of subtypes** in the disjoint group.

**Overlapping:** no empty-intersection condition is imposed; \\(A \\cap B\\) **is allowed to be non-empty**. This rule does not require an entity belonging to both to exist: the two sets may simply happen not to intersect in current data.

If an entity has shared attributes and subtype-specific attributes, keep **one shared identity** in the supertype. For instance, the Buyer and Seller profiles of the same user share the same \\(user\_id\\), rather than being two independent users.

### Disjoint/Overlapping Differs from Total/Partial

**Disjoint/overlapping** answers "at most how many subtypes?", whereas **total/partial specialization** answers "at least how many subtypes?".

| Combined rule | Number of subtypes per entity | Example |
| --- | --- | --- |
| Disjoint + total | **Exactly 1** | A confirmed fulfillment must be either Delivery or Pickup |
| Disjoint + partial | **0 or 1** | A newly created fulfillment may not have a method selected yet |
| Overlapping + total | **At least 1** | An activated account must be Buyer, Seller, or both |
| Overlapping + partial | **0, 1, or more** | A newly registered user may not have bought or sold yet |

In EER (*Enhanced Entity–Relationship*) notation, the disjoint constraint is typically denoted **d**, overlapping is **o**; total/partial completeness typically uses a double/single line connecting the supertype to the specialization circle. Exact notation varies by tool, but **the two constraint axes must be specified separately**.

## 3. Identifying the Right Rule from Business Requirements

Ask domain experts the following questions before choosing a table design:

1. **Which identity is being classified?** An account, a transaction, a product, or an order fulfillment? Do not mix order-level rules with per-fulfillment rules.
2. **At the same point in time, can A and B both be true?** If yes, the subtype group is not disjoint. Merely having "never seen" such a case is not sufficient grounds to conclude disjointness.
3. **Can an entity belong to no subtype?** This question determines total versus partial.
4. **Do roles change over time or by context?** An employee may be a manager in one project and a contributor in another. Classification may depend on project, effective period, or contract.
5. **Do the subtypes actually have distinct data and behaviors?** If they are merely permission labels, a role association table may make more sense than a multi-level inheritance structure.

A verifiable business statement should take the form:

> "For each fulfillment, at a given point in time, exactly one method—DELIVERY or PICKUP—applies; a delivery address exists only for DELIVERY and a pickup location exists only for PICKUP."

Or:

> "A user can simultaneously have a buyer profile and a seller profile; each profile type appears at most once per user."

These two statements are concrete enough to translate into keys, constraints, and tests.

## 4. Implementing Disjoint Subtypes in a Relational Database

### 4.1. One Table for the Entire Hierarchy (Single-Table Inheritance)

When the set of subtypes is fairly stable and each entity has **exactly one** type, you can use a single table with a type discriminator column (*discriminator*):

~~~sql
-- PostgreSQL
CREATE TABLE fulfillments (
    fulfillment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id       BIGINT NOT NULL,
    method         TEXT NOT NULL
                   CHECK (method IN ('DELIVERY', 'PICKUP')),
    delivery_address TEXT,
    pickup_location  TEXT,

    CONSTRAINT valid_fulfillment_details CHECK (
        (method = 'DELIVERY'
            AND delivery_address IS NOT NULL
            AND pickup_location IS NULL)
        OR
        (method = 'PICKUP'
            AND pickup_location IS NOT NULL
            AND delivery_address IS NULL)
    )
);
~~~

Here:

- \\(fulfillment\_id\\) identifies a fulfillment; \\(order\_id\\) links to the order (in a complete system, there should be a foreign key to the orders table).
- \\(method\\) is **NOT NULL** and accepts only two values, so the model expresses **total** specialization.
- The \\(CHECK\\) constraint forces the specific attributes to align with exactly one type, preventing entering both a delivery address and a pickup location for the same fulfillment.
- The constraint only clarifies the business fact; the application still needs user-friendly error messages when invalid data is written.

Example:

~~~sql
INSERT INTO fulfillments (order_id, method, delivery_address)
VALUES (901, 'DELIVERY', '12 Nguyen Hue, District 1');

-- Rejected: a fulfillment cannot carry both types of information.
INSERT INTO fulfillments (
    order_id, method, delivery_address, pickup_location
)
VALUES (902, 'PICKUP', '12 Nguyen Hue, District 1', 'Store A');
~~~

This design is simple to query and guarantees disjointness. In return, when there are many subtypes and each type has many specific attributes, the table accumulates many nullable columns; adding a new type may require changing the \\(CHECK\\) constraint, columns, and application code.

### 4.2. One Parent Table, One Table per Subtype (Class-Table Inheritance)

You can also place shared attributes in \\(fulfillments\\), delivery details in \\(delivery\_details\\), and pickup details in \\(pickup\_details\\). The primary key of each child table simultaneously serves as a foreign key to the parent table.

However, **having only two foreign keys pointing to the parent table is not enough to guarantee disjointness**: the same \\(fulfillment\_id\\) could still appear in both child tables. Enforcement options include:

- Keeping \\(method\\) in the parent table; in each child table, using a fixed discriminator and a **composite foreign key** referencing the unique pair \\((fulfillment\_id, method)\\) in the parent table, so the child record type must match the parent type.
- Or applying triggers/transactional constraints to enforce mutual exclusion across tables. Triggers must properly handle concurrent operations, not merely run naive pre-check queries.

Even after making the two child tables mutually exclusive, the requirement **"every parent must have exactly one child"** still requires completeness enforcement. A foreign key from child to parent only guarantees "every child has a parent"; it does not guarantee "every parent has a child". With multiple child tables, a total requirement typically needs writes within the same transaction paired with an appropriate verification mechanism, or a single-table design like the example above.

## 5. Implementing Overlapping Subtypes in a Relational Database

### 5.1. Independent Child Profiles Sharing the Parent Key

For the case where a user can both buy and sell, a single-valued discriminator is **insufficient to represent**. The design below lets each account have each profile type:

~~~sql
-- PostgreSQL
CREATE TABLE app_users (
    user_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email   TEXT NOT NULL UNIQUE
);

CREATE TABLE buyer_profiles (
    user_id        BIGINT PRIMARY KEY
                   REFERENCES app_users(user_id) ON DELETE CASCADE,
    loyalty_points INTEGER NOT NULL DEFAULT 0
                   CHECK (loyalty_points >= 0)
);

CREATE TABLE seller_profiles (
    user_id   BIGINT PRIMARY KEY
              REFERENCES app_users(user_id) ON DELETE CASCADE,
    shop_name TEXT NOT NULL
);
~~~

Each child table has \\(user\_id\\) as its primary key, so **each user has at most one buyer profile and one seller profile**. Two independent foreign keys allow the same \\(user\_id\\) to appear in both tables; this is the essence of overlapping.

~~~sql
INSERT INTO app_users (email)
VALUES ('minh@example.test')
RETURNING user_id;

-- Assume the statement above returns user_id = 1.
INSERT INTO buyer_profiles (user_id, loyalty_points)
VALUES (1, 120);

INSERT INTO seller_profiles (user_id, shop_name)
VALUES (1, 'Minh Store');

-- The user has both subtypes simultaneously.
SELECT u.user_id, u.email, b.loyalty_points, s.shop_name
FROM app_users AS u
JOIN buyer_profiles  AS b ON b.user_id = u.user_id
JOIN seller_profiles AS s ON s.user_id = u.user_id;
~~~

The query result includes users who have both a Buyer profile and a Seller profile. To retrieve all users along with their roles (including users with no roles), use \\(LEFT JOIN\\) from \\(app\_users\\) to the child tables.

This example is **overlapping + partial**: a user may not have either profile yet. If the business requires **overlapping + total**, additional checks are needed so every eligible user has at least one profile; the foreign keys above alone will not satisfy that.

### 5.2. If Roles Are Just Labels, Use an Association Table

Not every role needs a subtype table. If Buyer and Seller are merely classifications or permissions without specific attributes yet, a many-to-many association model is cleaner:

~~~sql
CREATE TABLE user_roles (
    user_id   BIGINT NOT NULL
              REFERENCES app_users(user_id) ON DELETE CASCADE,
    role_code TEXT NOT NULL
              CHECK (role_code IN ('BUYER', 'SELLER')),
    PRIMARY KEY (user_id, role_code)
);

-- A user having both roles is valid.
INSERT INTO user_roles (user_id, role_code)
VALUES (1, 'BUYER'), (1, 'SELLER');
~~~

The composite primary key prevents duplicate role records, but **does not prohibit multiple distinct roles for the same user**. When a role gains its own data, a role-specific profile table can be added. If combining \\(user\_roles\\) and profile tables, you must decide the **authoritative source of truth** for membership to avoid cases where a role exists without a profile, or vice versa.

Do not create two columns \\(is\_buyer\\), \\(is\_seller\\) alongside independent child tables and update them separately without constraints keeping them synchronized.

## 6. Choosing How to Map a Hierarchy to Tables

| Mapping strategy | Best suited for | Advantages | Considerations |
| --- | --- | --- | --- |
| **One table for the entire hierarchy** (*single table*) | Few types, especially disjoint ones | Simple queries, easy row-level \\(CHECK\\) | Many nullable columns; adding types may alter table structure |
| **Parent table + child tables** (*class table*) | Subtypes with specific attributes, especially overlapping ones | Reuses parent identity, normalizes specific attributes, expresses multiple concurrent roles | Requires JOINs; disjoint or total requires additional constraints |
| **One table per concrete type** (*concrete table*) | Relatively independent types, few queries on the supertype | Each table contains exact attributes of the type | Easily duplicates shared columns; hard to create shared FKs and query the full supertype |
| **Membership/role association table** | Many combinable labels or roles | Flexible when adding roles, composite key prevents duplicates | Role-specific attributes require additional design |

There is no rule saying "disjoint always uses one table" or "overlap always must use multiple tables". What decides is whether **the set of valid business states can be stored and enforced consistently** with the chosen structure.

## 7. Data Constraints, Keys, and Indexes

### Constraints at the Conceptual and Physical Levels

- **Subtype membership:** members of every subtype must correspond to an existing parent entity. In child tables, represent this with a foreign key.
- **Uniqueness within a subtype:** if each user has at most one profile per role, place a primary/unique key on the parent identifier in each child table.
- **Disjointness:** prohibit the same entity from belonging to two subtypes forbidden from combining. Single-row constraints like \\(CHECK\\) are easy when data lives in one table; if split across tables, design appropriate keys and cross-table constraints.
- **Completeness:** ensure at least one subtype when the model is total. Standard foreign keys from child to parent **do not automatically enforce** this.
- **Specific attributes:** require fields only for the subtype that actually applies; avoid requiring all records to have all fields.

In PostgreSQL, \\(CHECK\\) only rejects expressions evaluating to **FALSE**; **NULL/UNKNOWN** results are not automatically rejected. Therefore, when a constraint involves nullable columns, explicitly write \\(IS NULL\\)/\\(IS NOT NULL\\) or add \\(NOT NULL\\), as in the fulfillment example.

If checking cross-table conditions via triggers, you must consider **concurrent transactions**: two transactions can both read "does not exist yet" and simultaneously insert two incompatible types. Reliable options include locking the parent row to serialize changes, composite foreign key constraints with a discriminator, or appropriate transactional mechanisms; checking only in the application before writing is generally insufficient.

### Query-Driven Indexes

- For \\(buyer\_profiles.user\_id\\) and \\(seller\_profiles.user\_id\\), the primary key already creates an index supporting JOINs and existence checks.
- The \\(user\_roles\\) table has primary key \\((user\_id, role\_code)\\), suited for listing roles of **one** user. If frequently querying all users by \\(role\_code\\), consider an additional index on \\((role\_code, user\_id)\\).
- With a shared table, you can index by the discriminator combined with filter/status columns actually appearing in queries. Avoid adding indexes simply because each subtype has its own name.

~~~sql
-- Useful when querying by role and then fetching user_ids.
CREATE INDEX idx_user_roles_role_user
ON user_roles (role_code, user_id);

-- Count accounts that have both roles simultaneously:
SELECT COUNT(*)
FROM user_roles AS b
JOIN user_roles AS s ON s.user_id = b.user_id
WHERE b.role_code = 'BUYER'
  AND s.role_code = 'SELLER';
~~~

## 8. When Classification Relationships Change Over Time

Modeling current state and modeling history are two different problems. For example, a user is only a Buyer today, becomes a Seller next month, and stops selling the month after. If the business needs to know **what roles a user held on date X**, a current-state \\(user\_roles\\) table is insufficient.

In that case, you can model effective periods:

~~~sql
CREATE TABLE user_role_periods (
    role_period_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id        BIGINT NOT NULL REFERENCES app_users(user_id),
    role_code      TEXT NOT NULL
                   CHECK (role_code IN ('BUYER', 'SELLER')),
    valid_from     TIMESTAMPTZ NOT NULL,
    valid_to       TIMESTAMPTZ,
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);
~~~

In this example, two **different roles** can have overlapping effective intervals. If each user must not have two concurrently effective intervals **for the same role**, add an anti-overlap constraint on \\((user\_id, role\_code)\\) and the time range, such as an appropriate PostgreSQL exclusion constraint or an equivalent transactional mechanism.

In particular, an entity having *previously* belonged to two subtypes at **two different points in time** does not prove an overlapping hierarchy at **the same point in time**. Temporal semantics must be agreed upon before drawing conclusions.

## 9. Perspectives on Document, Graph, and Analytical Models

Disjoint/overlapping rules belong to the **business domain**, not solely to the storage technology:

| Storage paradigm | Representing disjoint | Representing overlapping | What needs control |
| --- | --- | --- | --- |
| **Relational** | Discriminator paired with \\(CHECK\\), or child tables with matching constraints | Multiple child tables with same parent key, or role association table | Keys, completeness, disjointness, transactions |
| **Document** | Single-valued \\(type\\) field and schema validating type-dependent fields | Role array and role-specific subdocuments | Duplicate values, missing role data, document updates |
| **Graph** | A node is assigned exactly one label/type within the disjoint group per business rules | A node has multiple labels or role relationships | Constraints on label/edge combinations, scope, and time |
| **Analytics/warehouse** | Dimension with a single type when truly disjoint | Bridge table between entity and multiple classifications | Avoid duplicating metrics when JOINing across multiple roles |

For example, in a document database, a user might have:

~~~json
{
  "userId": 1,
  "email": "minh@example.test",
  "roles": ["BUYER", "SELLER"],
  "buyerProfile": { "loyaltyPoints": 120 },
  "sellerProfile": { "shopName": "Minh Store" }
}
~~~

This document expresses overlapping, but schema validation or write logic must still ensure \\(roles\\) contains no duplicate values and profile data matches the roles. An arbitrary array **does not automatically enforce** business constraints.

In an analytical model, for example a revenue transaction joined to a user who is both Buyer and Seller, JOINing directly across two role records can **double-count transaction rows** if the query aggregates at the wrong *grain*. You must identify the role being analyzed or use an appropriate bridge/filter condition before aggregating.

## 10. Common Modeling Mistakes

| Mistake | Consequence | How to handle |
| --- | --- | --- |
| Using a single column \\(user\_type = 'BUYER'/'SELLER'\\) for someone who can hold both roles | Cannot store overlapping states | Use child profiles or a multi-role association |
| Creating two child tables for a disjoint group with only FKs to the parent | Same ID can appear in both tables | Add disjointness rules via suitable data structure/constraints |
| Confusing "exactly one" with "at most one" | Accepts records with no subtype when business requires classification | Specify an additional total completeness constraint |
| Inferring from current data that types are disjoint | Fails to support valid new business cases | Confirm rules with the business rather than inferring from sample data |
| Confusing multiple roles of one person with multiple user entities | Duplicates identity and shared attributes | Use one parent key and multiple memberships |
| Storing role flags alongside profile tables without synchronization | Flag indicates role exists while profile is missing | Choose one source of truth or consistency constraints |
| Ignoring time dimension or scope | Wrongly forbids role combinations, loses history | Specify effective validity by time/context if needed |
| Using role \\(JOIN\\) to compute metrics without checking grain | Inflates revenue, counts, or frequencies | Aggregate at the proper entity/event level, filter roles explicitly |

## 11. Decision Workflow and Self-Check

When encountering a new hierarchy, you can follow this order:

1. **Identify the supertype and identity key:** what object does a parent row represent?
2. **List subtypes and specific attributes:** which types truly have distinct data?
3. **Check each pair of subtypes:** is any concurrent, same-scope combination valid? If not, mark *disjoint*; if yes, mark *overlapping* or build a compatibility matrix for specifically forbidden pairs.
4. **Check completeness:** is at least one subtype mandatory?
5. **Choose physical mapping:** single table, parent–child tables, or role association; ensure all valid states can be represented.
6. **Define and test constraints:** test single-type, two-type, zero-type, missing child data, and role transition cases; also test concurrent writes if cross-table rules exist.
7. **Check queries and evolvability:** querying per subtype, intersections of types, changing types, adding new subtypes, and handling history.

**Self-check exercise:** An HR management system has an \\(Employee\\) group with two types: \\(FullTime\\) and \\(PartTime\\). Each employee has only one active contract, but a person may have signed both types of contracts in different periods. Is this hierarchy disjoint or overlapping?

**Solution hint:** If the entity being classified is **an active contract**, FullTime and PartTime are disjoint under the given rule. The fact that the person held multiple contract types at different times does not change disjointness at the evaluated point in time. If classifying **a person across their entire contract history**, that person can appear in both groups. Choose the right entity and time axis before deciding on the model.

The core rule to preserve in every implementation is: **disjoint limits concurrent subtypes to at most one; overlapping permits multiple subtypes; and requiring membership in at least one subtype is an independent constraint**.
